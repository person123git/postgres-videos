---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# How VACUUM and Autovacuum Truncation Works in PostgreSQL 17, Whether It Covers TOAST, and What Changed Since PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [What truncation means here](#what-truncation-means-here)
  - [How the heap scan sets nonempty_pages](#how-the-heap-scan-sets-nonempty_pages)
  - [The three gates in should_attempt_truncation](#the-three-gates-in-should_attempt_truncation)
  - [Inside lazy_truncate_heap](#inside-lazy_truncate_heap)
  - [The backwards verification scan](#the-backwards-verification-scan)
  - [What RelationTruncate does on disk and in WAL](#what-relationtruncate-does-on-disk-and-in-wal)
  - [Keeping the AccessExclusiveLock short](#keeping-the-accessexclusivelock-short)
  - [Where autovacuum differs from a manual VACUUM](#where-autovacuum-differs-from-a-manual-vacuum)
  - [TOAST tables](#toast-tables)
  - [Everything that can turn truncation off](#everything-that-can-turn-truncation-off)
  - [How to observe it](#how-to-observe-it)
  - [Test coverage in the pinned tree](#test-coverage-in-the-pinned-tree)
  - [What changed since PostgreSQL 12](#what-changed-since-postgresql-12)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Follow AGENTS.md. In PostgreSQL 17, question: how does VACUUM and autovacuum truncation work? Does it also handle TOAST? What changed since version 12?

## Answer

### Short answer

Truncation is the last thing a lazy `VACUUM` does before it updates `pg_class`. It gives
empty pages at the **physical end** of the heap back to the operating system, and it is the
only part of plain `VACUUM` that takes an `AccessExclusiveLock`
([vacuumlazy.c:518-520](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L518-L520),
[vacuumlazy.c:2570-2608](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2570-L2608)).
Autovacuum runs exactly the same code — it reaches `heap_vacuum_rel` through the same
`vacuum_rel` path — and differs only in how the on/off decision is sourced and in how the
worker can be cancelled while it holds that lock.

**Yes, TOAST is covered**, because a TOAST table is an ordinary heap that gets its own
`vacuum_rel` call
([vacuum.c:2289-2301](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2289-L2301)).
The nuance is *whose* setting decides: since **17.6** the TOAST table reads its own
`toast.vacuum_truncate` reloption, because commit `2e0b5d252b1` stopped `vacuum_rel` from
scribbling the resolved value onto the shared `VacuumParams` before recursing
([vacuum.c:1995-1999](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1995-L1999)).
Autovacuum never recurses into TOAST at all; it schedules TOAST tables as independent
targets in a second catalog pass
([autovacuum.c:2035-2040](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2035-L2040)).

Since v12 the algorithm is recognizably the same — same two constants, same conditional
lock loop, same backwards verification scan — but five behavioral things changed: the
`old_snapshot_threshold` veto disappeared (v17), the wraparound failsafe became a new veto
(v14), the lock wait became interruptible and visible as a wait event (v15), `PROCESS_TOAST`
and `PROCESS_MAIN` arrived as user options (v14, v16), and the parameter-scribbling bug that
made TOAST inherit its parent's setting was fixed (17.6).

### What truncation means here

Three unrelated things in the vacuum code are called "truncation". This page is about the
first:

| Meaning | Where | Effect |
|---|---|---|
| **Relation truncation** | `lazy_truncate_heap` -> `RelationTruncate` | Shortens the relation's files; disk space returns to the OS |
| Line pointer array truncation | `PageTruncateLinePointerArray` in `lazy_vacuum_heap_page` ([vacuumlazy.c:2231-2232](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2231-L2232)) | Shrinks `pd_lower` inside one page; no file shrinks |
| CLOG/MultiXact truncation | `vac_truncate_clog` ([vacuum.c:1804-1809](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1804-L1809)) | Removes `pg_xact`/`pg_multixact` segments |

Relation truncation only ever removes a **suffix**. A single live tuple on the last page
blocks the whole thing, no matter how empty the rest of the heap is. Reclaiming interior
free space requires a rewrite (`VACUUM FULL`/`CLUSTER`), not this path.

### How the heap scan sets nonempty_pages

`LVRelState.nonempty_pages` is "last nonempty page + 1"
([vacuumlazy.c:190-196](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L190-L196)).
It is the only input to the truncation target, and it is set during the main heap scan by
whichever per-page routine ran:

- **`lazy_scan_prune`** copies `presult.hastup` out of `heap_page_prune_and_freeze`
  ([vacuumlazy.c:1514-1516](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1514-L1516)).
  Pruning sets `hastup` for any surviving normal tuple and for any redirect line pointer
  ([pruneheap.c:1337](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1337),
  [pruneheap.c:1241](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1241)).
- **`lazy_scan_noprune`** — the path taken when the cleanup lock could not be acquired —
  sets `hastup` for every non-dead item
  ([vacuumlazy.c:1711](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1711),
  [vacuumlazy.c:1840-1842](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1840-L1842)),
  and also sets it when it has to leave `LP_DEAD` items behind
  ([vacuumlazy.c:1805-1814](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1805-L1814)).
- **New and empty pages** are handled by `lazy_scan_new_or_empty`, which `continue`s without
  touching `nonempty_pages`
  ([vacuumlazy.c:934-940](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L934-L940)),
  so all-zero and empty pages remain truncatable
  ([vacuumlazy.c:1263-1265](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1263-L1265)).

`LP_DEAD` items are the deliberate exception: pruning does **not** set `hastup` for them, on
the optimistic assumption that the second heap pass will turn them into `LP_UNUSED` before
truncation is reached. Without that assumption, truncation could only happen on every other
`VACUUM`
([pruneheap.c:1513-1521](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1513-L1521)).
This makes `nonempty_pages` **provisional**, which is why the truncation code re-verifies.

One skipping rule exists purely to serve truncation: the visibility-map skip logic always
treats the **last block** of the relation as unskippable, so that the scan gets the chance to
set `nonempty_pages` and the truncation code is not sent to take an `AccessExclusiveLock`
that will fail immediately
([vacuumlazy.c:1213-1224](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1213-L1224)).

### The three gates in should_attempt_truncation

```c
if (!vacrel->do_rel_truncate || VacuumFailsafeActive)
    return false;

possibly_freeable = vacrel->rel_pages - vacrel->nonempty_pages;
if (possibly_freeable > 0 &&
    (possibly_freeable >= REL_TRUNCATE_MINIMUM ||
     possibly_freeable >= vacrel->rel_pages / REL_TRUNCATE_FRACTION))
    return true;
```

([vacuumlazy.c#should_attempt_truncation](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2529-L2544))

1. **`do_rel_truncate`** is `params->truncate != VACOPTVALUE_DISABLED`, decided once at the
   top of `heap_vacuum_rel`
   ([vacuumlazy.c:376-391](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L376-L391)).
2. **`VacuumFailsafeActive`** — the wraparound failsafe also clears `do_rel_truncate`
   directly when it fires
   ([vacuumlazy.c:2323-2326](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326)).
   The rationale is spelled out in the function comment: under XID exhaustion the
   `AccessExclusiveLock` acquisition itself could fail and block the very `VACUUM` that would
   fix the problem
   ([vacuumlazy.c:2517-2528](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2517-L2528)).
3. **A size threshold**: at least `REL_TRUNCATE_MINIMUM` = 1000 trailing pages, *or* at
   least `rel_pages / REL_TRUNCATE_FRACTION` = 1/16 of the relation
   ([vacuumlazy.c:64-72](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L64-L72)).
   Because the two are OR-ed, the 1/16 rule is what fires on relations smaller than 16,000
   blocks (128 MB at the default `BLCKSZ`), and the flat 1000-page rule is what fires on
   larger ones. Neither constant is user-tunable.

The stated reason for the threshold is that the `AccessExclusiveLock` "must be replayed on
any hot standby, where it can be particularly disruptive"
([vacuumlazy.c:2509-2516](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2509-L2516)).

### Inside lazy_truncate_heap

`lazy_truncate_heap` runs after index cleanup and after the indexes are closed, and before
the `pg_class` update
([vacuumlazy.c:506-520](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L506-L520)).
It reports `PROGRESS_VACUUM_PHASE_TRUNCATE` and sets the error-context phase, then loops
([vacuumlazy.c#lazy_truncate_heap](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2549-L2673)):

1. **Acquire `AccessExclusiveLock` conditionally.** `ConditionalLockRelation` never blocks.
   On failure it waits 50 ms on its latch and retries, up to
   `VACUUM_TRUNCATE_LOCK_TIMEOUT / VACUUM_TRUNCATE_LOCK_WAIT_INTERVAL` = 5000/50 = **100
   retries**, i.e. about five seconds. Then it gives up and logs *"stopping truncate due to
   conflicting lock request"*
   ([vacuumlazy.c:2579-2608](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2579-L2608),
   [vacuumlazy.c:74-83](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L74-L83)).
   Blocking is deliberately avoided: `VACUUM` already holds `ShareUpdateExclusiveLock`, so
   waiting for a lock upgrade risks deadlock.
2. **Re-check the relation size.** If `RelationGetNumberOfBlocks` differs from the size the
   scan saw, someone extended the relation; give up and release the lock without updating
   `rel_pages`, on the reasoning that the new pages probably have the same tuple density as
   the old ones
   ([vacuumlazy.c:2610-2627](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2610-L2627)).
3. **Verify with a backwards scan.** `count_nondeletable_pages` re-reads the trailing pages;
   this is *necessary*, not an optimization, because `nonempty_pages` is provisional and
   other backends may have inserted since
   ([vacuumlazy.c:2629-2643](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2629-L2643)).
4. **Truncate.** `RelationTruncate(vacrel->rel, new_rel_pages)`, then release the
   `AccessExclusiveLock` immediately
   ([vacuumlazy.c:2645-2657](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2645-L2657)).
5. **Account and log.** `removed_pages += orig - new`, `rel_pages = new`, and an
   `INFO`-under-`VERBOSE`, otherwise-`DEBUG2` message *"table \"%s\": truncated %u to %u
   pages"*
   ([vacuumlazy.c:2659-2670](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2659-L2670)).
   Note that `reltuples` is deliberately **not** adjusted — no tuples were removed.
6. **Loop only if suspended.** The `do ... while` repeats only when the backwards scan bailed
   out early because a lock waiter appeared *and* there is still something left to remove
   ([vacuumlazy.c:2672](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2672)).

`pg_class.relpages` is written afterwards from the post-truncation `rel_pages`, with
`relallvisible` clamped to it
([vacuumlazy.c:556-575](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L556-L575)).

### The backwards verification scan

`count_nondeletable_pages` walks from `rel_pages` down to `nonempty_pages`
([vacuumlazy.c#count_nondeletable_pages](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2680-L2813)):

- It **prefetches forwards** in windows of `PREFETCH_SIZE` = 32 blocks so OS readahead can
  help a backwards walk
  ([vacuumlazy.c:113-117](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L113-L117),
  [vacuumlazy.c:2749-2762](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2749-L2762)).
- It reads through **the vacuum's buffer access strategy ring**, not the whole buffer pool
  ([vacuumlazy.c:2764-2765](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2764-L2765)),
  and takes only a **share** lock on each buffer.
- A page counts as nonempty if **any** item is used — `ItemIdIsUsed`, not "has a live tuple".
  Even an `LP_DEAD` item stops the scan, since its index entries may not have been removed
  ([vacuumlazy.c:2786-2797](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2786-L2797)).
  This is the moment where the optimistic `LP_DEAD` assumption from pruning is checked for
  real.
- There is **no `vacuum_delay_point`** in this loop, on purpose: the `AccessExclusiveLock` is
  held, so the cost-based delay is skipped and only `CHECK_FOR_INTERRUPTS` runs
  ([vacuumlazy.c:2740-2745](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2740-L2745)).
  `vacuum_cost_delay` and `autovacuum_vacuum_cost_delay` therefore do not slow this scan
  down.

### What RelationTruncate does on disk and in WAL

`RelationTruncate` is the callee boundary; it is shared with `TRUNCATE` and is not
vacuum-specific
([storage.c#RelationTruncate](../../../../raw/postgres-17/src/backend/catalog/storage.c#L287-L439)):

1. Invalidates `smgr_targblock` and every cached fork length.
2. Builds a single fork batch: `MAIN_FORKNUM`, plus `FSM_FORKNUM` via
   `FreeSpaceMapPrepareTruncateRel` and `VISIBILITYMAP_FORKNUM` via
   `visibilitymap_prepare_truncate`, when those forks exist
   ([storage.c:308-339](../../../../raw/postgres-17/src/backend/catalog/storage.c#L308-L339)).
3. Calls `RelationPreTruncate`, which marks the relation's pending-sync entry as truncated
   under `wal_level = minimal`
   ([storage.c#RelationPreTruncate](../../../../raw/postgres-17/src/backend/catalog/storage.c#L441-L461)).
4. Sets `DELAY_CHKPT_START | DELAY_CHKPT_COMPLETE` so a concurrent checkpoint can neither
   complete before the files shrink nor miss the sync request
   ([storage.c:343-370](../../../../raw/postgres-17/src/backend/catalog/storage.c#L343-L370)).
5. In a **critical section**, WAL-logs `XLOG_SMGR_TRUNCATE` with `SMGR_TRUNCATE_ALL`,
   `XLogFlush`es it, then calls `smgrtruncate2`, which drops the affected buffers and
   shortens the files
   ([storage.c:372-423](../../../../raw/postgres-17/src/backend/catalog/storage.c#L372-L423)).
6. Outside the critical section, refreshes upper FSM pages with `FreeSpaceMapVacuumRange`,
   because the removed pages were probably advertised as all-free
   ([storage.c:428-438](../../../../raw/postgres-17/src/backend/catalog/storage.c#L428-L438)).

On a standby the record is replayed by `smgr_redo`
([storage.c#smgr_redo](../../../../raw/postgres-17/src/backend/catalog/storage.c#L965-L1079)).
The `AccessExclusiveLock` that the primary took is itself replayed on hot standbys, which is
the disruption the size threshold exists to limit
([vacuumlazy.c:2509-2516](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2509-L2516)).

### Keeping the AccessExclusiveLock short

Two independent mechanisms stop truncation from freezing a busy table:

- **Self-suspension.** Every 32 blocks, and at most once per
  `VACUUM_TRUNCATE_LOCK_CHECK_INTERVAL` = 20 ms, the backwards scan calls
  `LockHasWaitersRelation`. If anyone is queued behind the `AccessExclusiveLock`, it logs
  *"suspending truncate due to conflicting lock request"*, sets `lock_waiter_detected`, and
  returns the block number reached so far — so the work done so far is still committed as a
  partial truncation, and the outer loop will retry
  ([vacuumlazy.c:2708-2738](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2708-L2738)).
- **External cancellation.** A backend blocked on the lock will, after `deadlock_timeout`,
  reach the `DS_BLOCKED_BY_AUTOVACUUM` branch of `ProcSleep` and `SIGINT` the blocking
  autovacuum worker — unless that worker is running a for-wraparound vacuum
  (`PROC_VACUUM_FOR_WRAPAROUND`)
  ([proc.c:1412-1443](../../../../raw/postgres-17/src/backend/storage/lmgr/proc.c#L1412-L1443)).
  This applies to autovacuum only; a manual `VACUUM` is never cancelled this way.

### Where autovacuum differs from a manual VACUUM

The truncation code is identical. Four things around it differ:

| Aspect | Manual `VACUUM` | Autovacuum |
|---|---|---|
| Source of the decision | `TRUNCATE` option if given, else the reloption | Always the reloption; `at_params.truncate` starts `VACOPTVALUE_UNSPECIFIED` ([autovacuum.c:2832-2838](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2832-L2838)) |
| TOAST | Recursed into from the parent ([vacuum.c:2289-2301](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2289-L2301)) | Never recursed into; scheduled separately ([autovacuum.c:2035-2040](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2035-L2040)) |
| Cancellable while holding the lock | No | Yes, via `ProcSleep` ([proc.c:1412-1443](../../../../raw/postgres-17/src/backend/storage/lmgr/proc.c#L1412-L1443)) |
| Log visibility | `INFO` only under `VERBOSE`, else `DEBUG2` ([vacuumlazy.c:2667-2670](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2667-L2670)) | Same `DEBUG2`; the page count surfaces as `pages: %u removed` in the `log_autovacuum_min_duration` report ([vacuumlazy.c:653-658](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L653-L658)) |

Autovacuum also never asks for parallel workers (`nworkers = -1`), but parallelism is an
index-vacuuming property and does not touch truncation, which is always leader-only
([autovacuum.c:2839-2840](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2839-L2840)).

### TOAST tables

**A TOAST table is truncated by exactly the same code.** It is a `RELKIND_TOASTVALUE` heap,
`vacuum_rel` accepts that relkind
([vacuum.c:2099-2102](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2099-L2102)),
and `table_relation_vacuum` dispatches to the same `heap_vacuum_rel`
([vacuum.c:2262-2263](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2262-L2263)).

**How it is reached from a manual `VACUUM`.** `vacuum_rel` remembers `reltoastrelid` when
`VACOPT_PROCESS_TOAST` is set, and skips it under `FULL` unless `PROCESS_MAIN` is off,
because `cluster_rel` rebuilds the TOAST table itself
([vacuum.c:2212-2223](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2212-L2223)).
After the parent's transaction commits, it calls `vacuum_rel` recursively on the TOAST relid
with `VACOPT_PROCESS_MAIN` forced on and `toast_parent` set, still protected by the
session-level lock taken on the parent
([vacuum.c:2142-2153](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2142-L2153),
[vacuum.c:2289-2301](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2289-L2301)).
`toast_parent` exists so the privilege check is made against the parent table
([vacuum.c:2069-2077](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2069-L2077)).

**Whose setting decides.** In the recursive call `params->truncate` is
`VACOPTVALUE_UNSPECIFIED` again — that is the whole point of the early
`memcpy(&toast_vacuum_params, params, ...)`
([vacuum.c:1991-1999](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1991-L1999)) —
so the TOAST relation resolves it from **its own** `rd_options`
([vacuum.c:2190-2201](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2190-L2201)).
Those options are what `ALTER TABLE ... SET (toast.vacuum_truncate = ...)` writes, since
`vacuum_truncate` is registered for both `RELOPT_KIND_HEAP` and `RELOPT_KIND_TOAST` with a
default of `true`
([reloptions.c:150-158](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L150-L158),
[reloptions.c:1888-1893](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L1888-L1893)).
A TOAST table with no reloptions has `rd_options == NULL`, which resolves to
`VACOPTVALUE_ENABLED`.

Consequences worth stating precisely:

- `vacuum_truncate = false` on the **main** table does **not** propagate to its TOAST table.
  There is no main-table fallback for this reloption; the only fallback in autovacuum is for
  the `AutoVacOpts` scheduling knobs
  ([autovacuum.c:2754-2770](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2754-L2770)),
  and `vacuum_truncate` is not part of that struct
  ([rel.h:342-346](../../../../raw/postgres-17/src/include/utils/rel.h#L342-L346)).
- An explicit `VACUUM (TRUNCATE FALSE) tab` **does** cover the TOAST table, because the
  explicit value is never `VACOPTVALUE_UNSPECIFIED` and so survives the copy
  ([vacuum.c:253-254](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L253-L254),
  [vacuum.c#get_vacoptval_from_boolean](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2532-L2536)).
- `VACUUM (PROCESS_TOAST FALSE) tab` leaves the TOAST table entirely alone, truncation
  included; `VACUUM (PROCESS_MAIN FALSE) tab` does the opposite
  ([ref/vacuum.sgml:35-37](../../../../raw/postgres-17/doc/src/sgml/ref/vacuum.sgml#L35-L37)).
- Under autovacuum the parent and its TOAST table are two independent jobs, each with its own
  reloption lookup, so a TOAST table can be truncated in a run where the parent is not, and
  vice versa
  ([autovacuum.c:2072-2079](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2072-L2079)).
- Autovacuum never analyzes a TOAST table, but that is orthogonal
  ([autovacuum.c:2902-2904](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2902-L2904)).

The tree proves the per-relation isolation directly. The injection-point test creates one
table with `vacuum_truncate=true, toast.vacuum_truncate=false` and one with the reverse, and
a single `VACUUM a, b` produces four `vacuum-truncate-*` notices in the order
enabled / disabled / disabled / enabled — main, its TOAST, main, its TOAST
([injection_points/sql/vacuum.sql:13-23](../../../../raw/postgres-17/src/test/modules/injection_points/sql/vacuum.sql#L13-L23),
[injection_points/expected/vacuum.out:45-63](../../../../raw/postgres-17/src/test/modules/injection_points/expected/vacuum.out#L45-L63)).

### Everything that can turn truncation off

| Lever | Scope | Effect |
|---|---|---|
| `VACUUM (TRUNCATE FALSE)` | One command, main relation and its TOAST table | `params.truncate = VACOPTVALUE_DISABLED` ([vacuum.c:253-254](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L253-L254)) |
| `vacuum_truncate` reloption | Per relation, read at each `VACUUM` | Overridden by the command option ([ref/create_table.sgml:1578-1597](../../../../raw/postgres-17/doc/src/sgml/ref/create_table.sgml#L1578-L1597)) |
| `toast.vacuum_truncate` reloption | The TOAST relation only | Same, on the TOAST relation's own row |
| `VACUUM (PROCESS_TOAST FALSE)` / `(PROCESS_MAIN FALSE)` | One command | Skips one side entirely ([vacuum.c:2218-2223](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2218-L2223)) |
| `VACUUM FULL` | One command | The option is ignored; the relation is rewritten instead ([ref/vacuum.sgml:262-272](../../../../raw/postgres-17/doc/src/sgml/ref/vacuum.sgml#L262-L272)) |
| Wraparound failsafe | Automatic, mid-run | Clears `do_rel_truncate` ([vacuumlazy.c:2323-2326](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326)) |
| Fewer than 1000 and fewer than 1/16 trailing empty pages | Automatic | Threshold not met ([vacuumlazy.c:2537-2541](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2537-L2541)) |
| A conflicting lock request | Automatic | Gives up after ~5 s, or suspends partway ([vacuumlazy.c:2590-2601](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2590-L2601)) |

**Apply scope of the reloption.** `vacuum_truncate` is a storage parameter, not a GUC. There
is no `vacuum_truncate` setting in `guc_tables.c` in this branch, so nothing here needs a
restart or a reload: `ALTER TABLE ... SET (vacuum_truncate = ...)` takes only
`ShareUpdateExclusiveLock` and takes effect at the next `VACUUM`
([reloptions.c:87-91](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L87-L91)).
The command-level `TRUNCATE` option is per-statement.

### How to observe it

- **Progress view.** `pg_stat_progress_vacuum.phase` reads `truncating heap` while
  `lazy_truncate_heap` runs
  ([system_views.sql:1212-1220](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1212-L1220),
  [monitoring.sgml:6376-6383](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L6376-L6383)).
- **Wait event.** A worker retrying the conditional lock reports
  `wait_event_type = Timeout`, `wait_event = VacuumTruncate`
  ([wait_event_names.txt:181](../../../../raw/postgres-17/src/backend/utils/activity/wait_event_names.txt#L181)).
- **Error context.** Any error raised during the phase carries
  *"while truncating relation \"%s.%s\" to %u blocks"*
  ([vacuumlazy.c:3154-3158](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3154-L3158)).
- **Logs.** `VACUUM VERBOSE` prints the `truncated %u to %u pages` line at `INFO`; otherwise
  it is `DEBUG2`. The autovacuum/verbose summary reports the total as the first number of
  `pages: %u removed, %u remain, %u scanned`, which counts **only** pages removed by
  truncation
  ([vacuumlazy.c:190-192](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L190-L192),
  [vacuumlazy.c:653-658](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L653-L658)).

### Test coverage in the pinned tree

| What is covered | Where |
|---|---|
| `TRUNCATE FALSE` leaves the file non-empty; a plain `VACUUM` then shrinks it to zero; `TRUNCATE FALSE, FULL TRUE` is accepted | [regress/sql/vacuum.sql:191-200](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L191-L200), [regress/expected/vacuum.out:226-246](../../../../raw/postgres-17/src/test/regress/expected/vacuum.out#L226-L246) |
| `vacuum_truncate=false` suppresses truncation; `RESET` restores it; `toast.vacuum_truncate` is stored on the TOAST row | [regress/sql/reloptions.sql:62-84](../../../../raw/postgres-17/src/test/regress/sql/reloptions.sql#L62-L84), [regress/expected/reloptions.out:101-148](../../../../raw/postgres-17/src/test/regress/expected/reloptions.out#L101-L148) |
| Main and TOAST resolve the option independently, and two relations in one command do not contaminate each other | [injection_points/sql/vacuum.sql:13-26](../../../../raw/postgres-17/src/test/modules/injection_points/sql/vacuum.sql#L13-L26), [injection_points/expected/vacuum.out:45-65](../../../../raw/postgres-17/src/test/modules/injection_points/expected/vacuum.out#L45-L65) |

**Explicit gaps.** Nothing in `src/test/` asserts the *"stopping truncate due to conflicting
lock request"* or *"suspending truncate due to conflicting lock request"* messages, so the
lock-retry and self-suspension paths, the `lock_waiter_detected` retry loop, and the
relation-grew bailout are uncovered. The four vacuum isolation specs
(`vacuum-concurrent-drop`, `vacuum-conflict`, `vacuum-no-cleanup-lock`,
`vacuum-skip-locked`) do not exercise truncation. No test asserts that the failsafe
suppresses truncation.

### What changed since PostgreSQL 12

The shape of the algorithm did not change: `REL_TRUNCATE_MINIMUM` = 1000,
`REL_TRUNCATE_FRACTION` = 16, `VACUUM_TRUNCATE_LOCK_CHECK_INTERVAL` = 20 ms,
`VACUUM_TRUNCATE_LOCK_WAIT_INTERVAL` = 50 ms and `VACUUM_TRUNCATE_LOCK_TIMEOUT` = 5000 ms
all hold the same values in the pinned v17 tree that the v12 source used, the conditional
lock loop and backwards verification scan are structurally the same, and the `TRUNCATE`
command option and the `vacuum_truncate` / `toast.vacuum_truncate` reloptions already existed
in v12 (`b84dbc8eb80b`, 2019-05-08, Fujii Masao, "Add TRUNCATE parameter to VACUUM";
`119dcfad988`, 2019-04-08, Fujii Masao, "Add vacuum_truncate reloption"; both first tagged
`REL_12_0`). What follows are the differences, each attributed to a commit in this
checkout's history and to the release tag that first contains it.

**Behavioral changes**

1. **The `old_snapshot_threshold` veto is gone (v17).** v12's `should_attempt_truncation`
   ended with `&& old_snapshot_threshold < 0`, so enabling "snapshot too old" disabled heap
   truncation outright. Commit `f691f5b80a8` (2023-09-05, Thomas Munro, "Remove the
   \"snapshot too old\" feature.", first tag `REL_17_0`) removed the feature and with it that
   condition; v17's gate list is `do_rel_truncate` and `VacuumFailsafeActive` only
   ([vacuumlazy.c:2529-2544](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2529-L2544)).
   This is the only v17-specific behavior change in the list.
2. **The wraparound failsafe suppresses truncation (v14).** `1e55e7d1755` (2021-04-07, Peter
   Geoghegan, "Add wraparound failsafe to VACUUM.") added the failsafe and `60f1f09ff44`
   (2021-04-13, same author, "Don't truncate heap when VACUUM's failsafe is in effect.")
   extended it to truncation; both first tagged `REL_14_0`. `71a825194fd` (2023-04-07, Daniel
   Gustafsson, "Make vacuum failsafe_active globally visible", `REL_16_0`) turned the flag
   into the global `VacuumFailsafeActive` that `should_attempt_truncation` now reads. v12 has
   no failsafe at all.
3. **The lock retry became interruptible and observable (v15).** v12 slept with
   `pg_usleep(VACUUM_TRUNCATE_LOCK_WAIT_INTERVAL * 1000L)`, which reports no wait event and
   ignores latch wakeups. `70685385d70` (2021-07-02, Michael Paquier, "Use WaitLatch()
   instead of pg_usleep() at end-of-vacuum truncation", first tag `REL_15_0`) replaced it
   with `WaitLatch(..., WAIT_EVENT_VACUUM_TRUNCATE)`, which is why `VacuumTruncate` appears in
   `pg_stat_activity` in v17
   ([vacuumlazy.c:2603-2607](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2603-L2607),
   [wait_event_names.txt:181](../../../../raw/postgres-17/src/backend/utils/activity/wait_event_names.txt#L181)).
4. **`VacuumParams` is no longer scribbled across relations or into TOAST (17.6).**
   `2e0b5d252b1` (2025-06-25, Michael Paquier, author Nathan Bossart, "Avoid scribbling of
   VACUUM options", backpatched through 13, first tag on this branch `REL_17_6`) added a
   per-relation `memcpy` in `vacuum()`'s loop and moved the TOAST copy to the top of
   `vacuum_rel`. Before it, the reloption-derived value written into `params->truncate` for
   one relation was still there when the TOAST table and the next relation in
   `VACUUM a, b` were processed, so `toast.vacuum_truncate` was effectively ignored. v12 is
   the worst case: it passes the caller's `params` pointer straight down with no copy at all.
   The same commit added the six `vacuum-index-cleanup-*` / `vacuum-truncate-*` injection
   points and the test module that exercises them
   ([vacuum.c:2203-2210](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2203-L2210)).
5. **`PROCESS_TOAST` (v14) and `PROCESS_MAIN` (v16) can now steer which side is truncated.**
   `7cb3048f38e` (2021-02-09, Michael Paquier, "Add option PROCESS_TOAST to VACUUM",
   `REL_14_0`) replaced v12's internal-only `VACOPT_SKIPTOAST` with a user-visible option;
   `4211fbd8413` (2023-03-06, "Add PROCESS_MAIN to VACUUM", `REL_16_0`) plus `ee56048b0ec`
   (2023-03-08, "Improve readability of code PROCESS_MAIN in vacuum_rel()") added the
   converse and the `FULL`-plus-`PROCESS_MAIN`-off exception now visible at
   [vacuum.c:2212-2223](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2212-L2223).
6. **TOAST privilege checks moved to the parent (v17).** `ecb0fd33720` (2024-03-13, Nathan
   Bossart, "Reintroduce MAINTAIN privilege and pg_maintain predefined role.", `REL_17_0`)
   added `VacuumParams.toast_parent`
   ([vacuum.h:226-232](../../../../raw/postgres-17/src/include/commands/vacuum.h#L226-L232)),
   so the recursive TOAST vacuum re-checks privileges against the main relation
   ([vacuum.c:2069-2077](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2069-L2077)).
7. **`BUFFER_USAGE_LIMIT` now sizes the ring the verification scan reads through (v16).**
   `1cbbee03385` (2023-04-07, David Rowley, "Add VACUUM/ANALYZE BUFFER_USAGE_LIMIT option",
   `REL_16_0`); the strategy is what `count_nondeletable_pages` passes to
   `ReadBufferExtended`
   ([vacuumlazy.c:2764-2765](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2764-L2765)).

**Changes in `RelationTruncate`, the physical layer**

8. **The three forks are truncated in one batched `smgrtruncate` (v13).** `6d05086c0a7`
   (2019-09-24, Fujii Masao, "Speedup truncations of relation forks.", first tag `REL_13_0`)
   replaced v12's separate `FreeSpaceMapTruncateRel` and `visibilitymap_truncate` calls with
   the `forks[]`/`blocks[]` batch now at
   [storage.c:308-339](../../../../raw/postgres-17/src/backend/catalog/storage.c#L308-L339).
9. **A pending-sync hook for `wal_level = minimal` (v13).** `c6b92041d38` (2020-04-04, Noah
   Misch, "Skip WAL for new relfilenodes, under wal_level=minimal.", `REL_13_0`) added
   `RelationPreTruncate`
   ([storage.c:441-461](../../../../raw/postgres-17/src/backend/catalog/storage.c#L441-L461)).
10. **A critical section and a checkpoint interlock (v15, extended in 17.3).** v12 explicitly
    refused a critical section here. `412ad7a5563` (2022-03-24, Robert Haas, "Fix possible
    recovery trouble if TRUNCATE overlaps a checkpoint.", `REL_15_0`) added
    `START_CRIT_SECTION` and `DELAY_CHKPT_COMPLETE`; `d4ffbf47b2d` (2024-12-03, Thomas Munro,
    "RelationTruncate() must set DELAY_CHKPT_START.", first tag `REL_17_3`) added the second
    flag. `66aaabe7a18` (2025-01-08, Thomas Munro, "Restore smgrtruncate() prototype in
    back-branches.", `REL_17_3`) is why the call site reads `smgrtruncate2` in this branch
    ([storage.c:369-423](../../../../raw/postgres-17/src/backend/catalog/storage.c#L369-L423)).
    v17 also flushes the WAL record unconditionally, where v12 flushed only when an FSM or VM
    fork existed.

**Refactors and reporting**

11. **The ternary option type was renamed (v14).** `VACOPT_TERNARY_DEFAULT/ENABLED/DISABLED`
    became `VACOPTVALUE_UNSPECIFIED/AUTO/ENABLED/DISABLED` in `3499df0dee8` (2021-06-18,
    Peter Geoghegan, "Support disabling index bypassing by VACUUM.", `REL_14_0`)
    ([vacuum.h:192-206](../../../../raw/postgres-17/src/include/commands/vacuum.h#L192-L206)).
    `AUTO` exists only for `index_cleanup`; `heap_vacuum_rel` asserts that `truncate` is
    never `AUTO`
    ([vacuumlazy.c:379-381](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L379-L381)).
12. **Per-run state moved into `LVRelState` (v14).** `b4af70cb210` (2021-04-05, Peter
    Geoghegan, "Simplify state managed by VACUUM.", `REL_14_0`) turned v12's `LVRelStats` and
    file-scope `elevel` into `LVRelState` with `do_rel_truncate`, `verbose` and
    `removed_pages`; `lock_waiter_detected` became a local passed by reference
    ([vacuumlazy.c:154-157](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L154-L157)).
13. **The last-page rule became unconditional (v15).** v12 forced a scan of the final block
    only when `should_attempt_truncation` already returned true (`FORCE_CHECK_PAGE`);
    `44fa84881ff` (2022-02-11, Peter Geoghegan, "Simplify lazy_scan_heap's handling of
    scanned pages.", `REL_15_0`) made the last block always unskippable
    ([vacuumlazy.c:1213-1224](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1213-L1224)).
14. **An error context for the phase (v13/v14).** `b61d161c146` (2020-03-30, Amit Kapila,
    "Introduce vacuum errcontext to display additional information.", `REL_13_0`) and
    `7e453634bb6` (2020-08-26, same author, "Add additional information in the vacuum error
    context.", `REL_14_0`) added `VACUUM_ERRCB_PHASE_TRUNCATE` and the block number now
    reported at
    [vacuumlazy.c:3154-3158](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3154-L3158).
15. **Log text changed (v15).** `b175b9cde72` (2021-08-31, Peter Geoghegan, "VACUUM VERBOSE:
    Don't report \"pages removed\".", `REL_15_0`) gave the message its `table "%s":` prefix
    and dropped the `pg_rusage_show` detail v12 attached to it; `872770fd6cc` (2022-02-11,
    same author, "Add VACUUM instrumentation for scanned pages, relfrozenxid.", `REL_15_0`)
    replaced v12's `pages: %u removed, %u remain, %u skipped due to pins, %u skipped frozen`
    summary line with today's `pages: %u removed, %u remain, %u scanned (%.2f%% of total)`
    ([vacuumlazy.c:653-658](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L653-L658)).
16. **A second, unrelated "truncation" appeared (v14/v15).** `3c3b8a4b268` (2021-04-07, Peter
    Geoghegan, "Truncate line pointer array during VACUUM.", `REL_14_0`) and `10a8d138235`
    (2022-04-07, "Truncate line pointer array during heap pruning.", `REL_15_0`) added
    `PageTruncateLinePointerArray`
    ([vacuumlazy.c:2231-2232](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2231-L2232)).
    It reclaims space **inside** a page and never shortens a file, so it does not affect
    anything described above.

**What did not change.** The two size constants and the three timing constants; the use of
`ConditionalLockRelation` rather than a blocking upgrade; the relation-grew bailout; the
`ItemIdIsUsed` (not "is live") test in the backwards verification scan; the deliberate
absence of a cost-delay point while the `AccessExclusiveLock` is held; the 32-block prefetch
window; the `truncating heap` progress phase; and the fact that `reltuples` is left alone
while `relpages` is rewritten.

## Context Reviewed

- Truncation implementation: `heap_vacuum_rel`, `should_attempt_truncation`,
  `lazy_truncate_heap`, `count_nondeletable_pages`, `lazy_check_wraparound_failsafe`,
  `find_next_unskippable_block`, `lazy_scan_prune`, `lazy_scan_noprune`,
  `lazy_scan_new_or_empty`, `vacuum_error_callback` in
  `src/backend/access/heap/vacuumlazy.c`.
- Page-level `hastup` semantics in `src/backend/access/heap/pruneheap.c`.
- Command and TOAST plumbing: `ExecVacuum`, `vacuum`, `vacuum_rel`,
  `get_vacoptval_from_boolean` in `src/backend/commands/vacuum.c`; `VacOptValue` and
  `VacuumParams` in `src/include/commands/vacuum.h`.
- Physical layer: `RelationTruncate`, `RelationPreTruncate`, `smgr_redo` in
  `src/backend/catalog/storage.c`.
- Reloptions: `boolRelOpts`, `default_reloptions` in
  `src/backend/access/common/reloptions.c`; `StdRdOptions` in `src/include/utils/rel.h`.
- Autovacuum: `do_autovacuum` (both catalog passes), `extract_autovac_opts`,
  `table_recheck_autovac`, `autovacuum_do_vac_analyze` in
  `src/backend/postmaster/autovacuum.c`.
- Lock cancellation: `ProcSleep` in `src/backend/storage/lmgr/proc.c`.
- Observability: `wait_event_names.txt`, `system_views.sql` (`pg_stat_progress_vacuum`),
  `monitoring.sgml`.
- Documentation: `ref/vacuum.sgml`, `ref/create_table.sgml`, `maintenance.sgml`.
- Tests: `regress/sql/vacuum.sql`, `regress/sql/reloptions.sql`,
  `src/test/modules/injection_points/{sql,expected}/vacuum.{sql,out}`, and the four
  `src/test/isolation/specs/vacuum-*.spec` files.
- Source history of the v17 checkout, restricted to `vacuumlazy.c`, `vacuum.c`, `storage.c`
  and `reloptions.c`, over `REL_12_0..786db8dcf16`, with first-containing release tags read
  from `git tag --contains`.
- Confirmed absent in this branch: any `vacuum_truncate` entry in
  `src/backend/utils/misc/guc_tables.c`.

## Evidence Map

| Claim | Source |
|---|---|
| Truncation is the last step before the `pg_class` update | [vacuumlazy.c:506-575](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L506-L575) |
| Thresholds are 1000 pages or 1/16 of the relation, OR-ed | [vacuumlazy.c:64-72](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L64-L72), [vacuumlazy.c:2537-2541](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2537-L2541) |
| Failsafe and the reloption/option are the two other gates | [vacuumlazy.c:2534](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2534), [vacuumlazy.c:2323-2326](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326) |
| ~100 conditional-lock retries over ~5 s, then give up | [vacuumlazy.c:74-83](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L74-L83), [vacuumlazy.c:2579-2608](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2579-L2608) |
| Backwards scan is mandatory re-verification, not an optimization | [vacuumlazy.c:2629-2635](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2629-L2635) |
| Any used line pointer, including `LP_DEAD`, blocks truncation | [vacuumlazy.c:2786-2797](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2786-L2797) |
| Pruning deliberately does not set `hastup` for `LP_DEAD` | [pruneheap.c:1513-1521](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1513-L1521) |
| No cost-based delay while the lock is held | [vacuumlazy.c:2740-2745](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2740-L2745) |
| Self-suspension on a detected lock waiter, every 32 blocks / 20 ms | [vacuumlazy.c:2708-2738](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2708-L2738) |
| Retry loop only when suspended | [vacuumlazy.c:2672](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2672) |
| `relpages` updated, `reltuples` left alone | [vacuumlazy.c:2659-2665](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2659-L2665), [vacuumlazy.c:556-575](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L556-L575) |
| Main, FSM and VM forks truncated together, WAL-logged in a critical section | [storage.c:287-439](../../../../raw/postgres-17/src/backend/catalog/storage.c#L287-L439) |
| Replay path | [storage.c:965-1079](../../../../raw/postgres-17/src/backend/catalog/storage.c#L965-L1079) |
| Autovacuum leaves `truncate` unspecified so the reloption decides | [autovacuum.c:2832-2838](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2832-L2838) |
| Autovacuum does not recurse into TOAST; second pass schedules them | [autovacuum.c:2035-2040](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2035-L2040), [autovacuum.c:2072-2079](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2072-L2079) |
| A blocked backend can `SIGINT` a non-wraparound autovacuum worker | [proc.c:1412-1443](../../../../raw/postgres-17/src/backend/storage/lmgr/proc.c#L1412-L1443) |
| TOAST is vacuumed by a separate `vacuum_rel` call under the parent's session lock | [vacuum.c:2142-2153](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2142-L2153), [vacuum.c:2289-2301](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2289-L2301) |
| The early `memcpy` is what lets TOAST read its own reloption | [vacuum.c:1991-1999](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1991-L1999), [vacuum.c:2190-2201](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2190-L2201) |
| `vacuum_truncate` is registered for HEAP and TOAST, default true | [reloptions.c:150-158](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L150-L158) |
| Main-table reloption fallback for TOAST covers `AutoVacOpts` only | [autovacuum.c:2754-2770](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2754-L2770), [rel.h:342-346](../../../../raw/postgres-17/src/include/utils/rel.h#L342-L346) |
| Per-relation and per-TOAST isolation is tested | [injection_points/expected/vacuum.out:45-63](../../../../raw/postgres-17/src/test/modules/injection_points/expected/vacuum.out#L45-L63) |
| Progress phase and wait event | [system_views.sql:1218](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1218), [wait_event_names.txt:181](../../../../raw/postgres-17/src/backend/utils/activity/wait_event_names.txt#L181) |
| `TRUNCATE` is ignored under `FULL`, and the reloption is the default source | [ref/vacuum.sgml:259-274](../../../../raw/postgres-17/doc/src/sgml/ref/vacuum.sgml#L259-L274), [ref/create_table.sgml:1578-1597](../../../../raw/postgres-17/doc/src/sgml/ref/create_table.sgml#L1578-L1597) |

## Open Questions

1. **The `vacuum-truncate-auto` injection point is unreachable.** `vacuum_rel` can attach a
   notice to it
   ([vacuum.c:2203-2210](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2203-L2210)),
   but nothing ever sets `params->truncate` to `VACOPTVALUE_AUTO` — the command parser maps
   only booleans
   ([vacuum.c:253-254](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L253-L254)),
   the reloption path maps only to `ENABLED`/`DISABLED`
   ([vacuum.c:2194-2201](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2194-L2201)),
   and `heap_vacuum_rel` asserts it never arrives
   ([vacuumlazy.c:379-381](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L379-L381)).
   The test attaches and detaches it and it never fires
   ([injection_points/expected/vacuum.out:27-31](../../../../raw/postgres-17/src/test/modules/injection_points/expected/vacuum.out#L27-L31)).
   Whether that is defensive symmetry with `index_cleanup` or dead code is not settled here.
2. **No measurements were taken.** The asker chose source-and-history scope, so no v17 or v12
   server was built. Every number above is a constant or a formula read from source; none of
   the timing claims (how long a five-second retry budget takes in practice, how often
   self-suspension fires under real contention) has been observed.
3. **The v12 side is described from v12 source but cited only through v17.** Per the
   repository's citation rule this page cites the v17 checkout only. Statements about what v12
   did were read from the pinned v12 checkout's `vacuumlazy.c`, `vacuum.c` and `storage.c`, and
   are supported here by the v17 checkout's own commit history and release tags rather than by
   v12 line citations. A reader who wants v12 line numbers needs a v12-version page; none exists
   for this topic yet.
4. **Whether an inherited TOAST setting was ever intended is not resolved.** `2e0b5d252b1`
   calls the old behavior a bug, but the tree contains no test from before 17.6 asserting
   either behavior, so how long TOAST tables silently used their parent's `vacuum_truncate`
   in the field cannot be established from this checkout.
5. **Interaction with `REL_TRUNCATE_FRACTION` on very large relations is untested here.** For
   a relation above 16,000 blocks the 1000-page rule dominates, meaning a 1 TB heap with 999
   trailing empty pages is never truncated. That follows arithmetically from
   [vacuumlazy.c:2537-2541](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2537-L2541),
   but no test or documentation in the tree states the consequence.
6. **The standby-side disruption is asserted by comments, not measured.** The size threshold's
   stated rationale is `AccessExclusiveLock` replay on hot standbys
   ([vacuumlazy.c:2509-2516](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2509-L2516)),
   and the recovery-conflict machinery that would cancel standby queries was not traced on
   this page.

## Source References

- Lazy vacuum and truncation: [vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L64-L120), [vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2509-L2813)
- Page pruning and `hastup`: [pruneheap.c](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L110-L130), [pruneheap.c](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1230-L1525)
- Command plumbing and TOAST recursion: [vacuum.c](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L160-L270), [vacuum.c](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1979-L2310)
- Parameter types: [vacuum.h](../../../../raw/postgres-17/src/include/commands/vacuum.h#L180-L250)
- Physical truncation and replay: [storage.c](../../../../raw/postgres-17/src/backend/catalog/storage.c#L280-L461), [storage.c](../../../../raw/postgres-17/src/backend/catalog/storage.c#L960-L1079)
- Reloptions: [reloptions.c](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L84-L160), [reloptions.c](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L1870-L1900), [rel.h](../../../../raw/postgres-17/src/include/utils/rel.h#L330-L350)
- Autovacuum: [autovacuum.c](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2000-L2100), [autovacuum.c](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2730-L2905)
- Lock cancellation: [proc.c](../../../../raw/postgres-17/src/backend/storage/lmgr/proc.c#L1380-L1500)
- Observability: [wait_event_names.txt](../../../../raw/postgres-17/src/backend/utils/activity/wait_event_names.txt#L170-L185), [system_views.sql](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1205-L1235), [monitoring.sgml](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L6340-L6395)
- Documentation: [ref/vacuum.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/vacuum.sgml#L25-L280), [ref/create_table.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/create_table.sgml#L1545-L1600)
- Tests: [regress/sql/vacuum.sql](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L185-L205), [regress/sql/reloptions.sql](../../../../raw/postgres-17/src/test/regress/sql/reloptions.sql#L58-L90), [injection_points/sql/vacuum.sql](../../../../raw/postgres-17/src/test/modules/injection_points/sql/vacuum.sql#L1-L35)

## Navigation

- [v17/index](../../index.md) - PostgreSQL 17 landing page.
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md) - Map of the pinned v17 source tree.
- [How Much I/O a VACUUM FULL Performs on a Multi-GB, Near-Empty Heap in PostgreSQL 17 (unverified)](vacuum-full-io-on-near-empty-heap.md) - The rewrite path that reclaims interior space, which this page's suffix-only truncation cannot.
- [v12/index](../../../v12/index.md) - PostgreSQL 12 landing page, for the legacy baseline this page compares against.
- [wiki index](../../../index.md) - Global catalog.
- [versions](../../../versions.md) - Source pin manifest.
