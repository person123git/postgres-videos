---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [How it differs from CREATE INDEX CONCURRENTLY](#how-it-differs-from-create-index-concurrently)
  - [Dispatch, preconditions, and restrictions](#dispatch-preconditions-and-restrictions)
  - [The six phases](#the-six-phases)
  - [GUCs that affect REINDEX INDEX CONCURRENTLY performance](#gucs-that-affect-reindex-index-concurrently-performance)
  - [All steps and locks required on the table](#all-steps-and-locks-required-on-the-table)
  - [State flags for the old and new index](#state-flags-for-the-old-and-new-index)
  - [Failure scenarios and the outcome on the table](#failure-scenarios-and-the-outcome-on-the-table)
  - [Can a failure leave an invalid index with the original index name?](#can-a-failure-leave-an-invalid-index-with-the-original-index-name)
  - [Running REINDEX INDEX CONCURRENTLY on an invalid index](#running-reindex-index-concurrently-on-an-invalid-index)
  - [Multiple indexes in one command](#multiple-indexes-in-one-command)
  - [Watching the phases](#watching-the-phases)
  - [Test coverage](#test-coverage)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

give a comprehensive explanation of how REINDEX INDEX CONCURRENTLY is
implemented in PostgreSQL 12, including the steps, locks, and failure scenarios

(Filed 2026-06-12 by splitting the prior combined page
[How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 12](create-index-concurrently.md)
into one page per command.)

Follow-up (2026-06-12): Can a failure leave an invalid index with the original
index name? Confirm whether `REINDEX INDEX CONCURRENTLY index_name;` can, on
failure, leave the table with an index called `index_name` that is marked invalid
— so query plans can no longer use it. Before, the index was only bloated; after
such a failure the table would effectively have no usable index.

(The follow-up wording was corrected from the original prompt for grammar at the
user's request; meaning preserved.)

Follow-up (2026-07-17): What GUCs have a performance impact on it?

(The follow-up wording was corrected from "what GUCs have performance impact on
it." for grammar and capitalization at the user's request; meaning preserved.)

## Answer

`REINDEX INDEX CONCURRENTLY` (RIC) rebuilds an index without ever blocking
`INSERT`/`UPDATE`/`DELETE`, and without making the index unavailable to queries
in between. It does this by building a **brand-new copy** of the index next to
the original, catching that copy up to concurrent writes, atomically **swapping**
the copy in for the original, and only then marking the original dead and
dropping it. The build and catch-up reuse the exact `CREATE INDEX CONCURRENTLY`
(CIC) machinery; the swap-and-drop tail is what makes a reindex.

All of it runs in `ReindexRelationConcurrently()`, which lays out **six phases**
across many short transactions
([indexcmds.c#ReindexRelationConcurrently](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2738-L2955)):

1. create the new index copies in the catalog (not built),
2. build each new copy,
3. let each new copy catch up and validate it,
4. swap each new copy in for its old index (new becomes valid, old invalid),
5. mark the old indexes dead, and
6. drop the old indexes.

The table lock used throughout is **`ShareUpdateExclusiveLock`** — the same level
CIC, `VACUUM` (non-FULL), and `ANALYZE` use, weak enough to let DML proceed but
strong enough to keep out a second concurrent build, `VACUUM`, `ANALYZE`, and
schema changes
([lockdefs.h:36-46](../../../../raw/postgres-12/src/include/storage/lockdefs.h#L36-L46),
[lock.c#LockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L78-L81)).

### How it differs from CREATE INDEX CONCURRENTLY

RIC is CIC plus a swap and a drop. The build (`index_concurrently_build`) and
the validation (`validate_index`) functions are literally the same as CIC's; see
the [CIC page](create-index-concurrently.md) for that shared core. The
differences:

| Aspect | CREATE INDEX CONCURRENTLY | REINDEX INDEX CONCURRENTLY |
|---|---|---|
| Target | a new index that did not exist | a fresh copy `<name>_ccnew` of an existing index |
| Phases | build, validate, mark valid (3 waits) | create copy, build, validate, swap, set-dead, drop (**5 waits**) |
| Extra waits | none beyond the snapshot wait | two `AccessExclusiveLock` waits that **wait out readers** of the old index before set-dead and drop ([indexcmds.c:3272-3304](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3272-L3304)) |
| Names | the index keeps its name | new copy takes the original's name; the old index is renamed `<name>_ccold` ([index.c#swap-names](../../../../raw/postgres-12/src/backend/catalog/index.c#L1490-L1492), [indexcmds.c#ccold](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3230-L3235)) |
| On failure | leaves the **target** index invalid | leaves an invalid `_ccnew` (before swap) or `_ccold` (after swap); a healthy original is preserved until the swap |

The "wait out readers" difference is the operationally important one. CIC's two
lock-based waits use `ShareLock` conflict checks and do not wait for
`AccessShareLock` readers, though its old-snapshot wait can still wait for a
plain `SELECT` that holds an old snapshot
([indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L339-L402)).
RIC adds two later `AccessExclusiveLock` conflict checks on the heap lock tag, so
current table lock holders, including `AccessShareLock` readers, can delay marking
the old index dead and dropping it
([indexcmds.c:3272-3304](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3272-L3304),
[lock.c#AccessExclusive-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L99-L103),
[reindex.sgml#concurrent-steps](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L334-L359)).

### Dispatch, preconditions, and restrictions

`REINDEX ... CONCURRENTLY` is dispatched in `standard_ProcessUtility`. Because the
implementation commits many times, it cannot run inside a transaction block, and
it is forbidden during recovery
([utility.c#reindex-dispatch](../../../../raw/postgres-12/src/backend/tcop/utility.c#L773-L807)):

```c
if (stmt->concurrent)
    PreventInTransactionBlock(isTopLevel, "REINDEX CONCURRENTLY");
PreventCommandDuringRecovery("REINDEX");
```

`REINDEX INDEX` routes through `ReindexIndex`, which locks the index in
`ShareUpdateExclusiveLock` for the concurrent case (vs `AccessExclusiveLock` for a
plain reindex) and then calls `ReindexRelationConcurrently` — unless the index is
on a **temporary** table, in which case it silently does a non-concurrent
`reindex_index` instead
([indexcmds.c#ReindexIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2336-L2382)).
`REINDEX TABLE` behaves the same way via `ReindexTable`, emitting
`table "..." has no indexes that can be reindexed concurrently` when nothing
qualifies
([indexcmds.c#ReindexTable](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2458-L2499)).

The full restriction set, with where each is enforced:

| Restriction | Behavior | Where enforced |
|---|---|---|
| Inside a transaction block | error: `REINDEX CONCURRENTLY cannot run inside a transaction block` | [utility.c:777-779](../../../../raw/postgres-12/src/backend/tcop/utility.c#L777-L779) |
| During recovery (standby) | error: `REINDEX` cannot run during recovery | [utility.c:782](../../../../raw/postgres-12/src/backend/tcop/utility.c#L782) |
| Temporary table/index | falls back to a **non-concurrent** reindex | [indexcmds.c:2377-2381](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2377-L2381), [indexcmds.c:2477-2491](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2477-L2491) |
| System catalog direct target, or `REINDEX SYSTEM CONCURRENTLY` | error: `cannot reindex system catalogs concurrently` | [indexcmds.c:2804-2807](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2804-L2807), [indexcmds.c:2897-2900](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2897-L2900), [indexcmds.c:2530-2533](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2530-L2533) |
| System catalogs reached by `REINDEX SCHEMA/DATABASE CONCURRENTLY` | warning, skipped | [indexcmds.c:2641-2650](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2641-L2650) |
| Partitioned table target | warning, skipped (no-op) | [indexcmds.c:2917-2923](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2917-L2923) |
| Partitioned index named directly | error: `REINDEX is not yet implemented for partitioned indexes` | [indexcmds.c:2368-2371](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2368-L2371), [indexcmds.c#ReindexPartitionedIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3390-L3396) |
| Exclusion-constraint index named directly | error: `concurrent index creation for exclusion constraints is not supported` | [index.c:1268-1271](../../../../raw/postgres-12/src/backend/catalog/index.c#L1268-L1271) |
| Exclusion-constraint index reached via a table | warning, skipped | [indexcmds.c:2825-2830](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2825-L2830) |
| Invalid index reached via a table | warning, skipped | [indexcmds.c:2819-2824](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2819-L2824) |
| Invalid index named directly | **allowed** (this is how you repair one) | [indexcmds.c:2908-2912](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2908-L2912) |

When the target is a table, matview, or toast relation, RIC gathers every valid,
non-exclusion index plus the relation's **toast** indexes, processing them all
together; when the target is an index, it processes just that one
([indexcmds.c#gather-indexes](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2784-L2916)).

### The six phases

The phase comment in the source is the canonical map
([indexcmds.c#phase-overview](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2941-L2955)).
Each phase loops over **all** indexes before the next phase begins.

#### Phase 1: create the catalog copies and take session locks

For each index, RIC chooses a temporary name `<orig>_ccnew`
([indexcmds.c#ccnew](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2993-L2998))
and calls `index_concurrently_create_copy`, which rebuilds the new index's
`IndexInfo` from the old index's catalog rows (class, options, reloptions,
expressions, predicates) and creates the catalog entry with
`INDEX_CREATE_SKIP_BUILD | INDEX_CREATE_CONCURRENT` — so it has identity but no
data and is **not ready, not valid**
([index.c#index_concurrently_create_copy](../../../../raw/postgres-12/src/backend/catalog/index.c#L1240-L1388)).
Exclusion constraints are rejected here
([index.c:1268-1271](../../../../raw/postgres-12/src/backend/catalog/index.c#L1268-L1271)).

RIC then takes a **session-level** `ShareUpdateExclusiveLock` on the old index,
the new index, and the heap table (including toast). It records the two index
lock relids during the phase-1 loop
([indexcmds.c#index-session-locks](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3024-L3029)),
records each heap relid and saves a `LOCKTAG` per heap for the later waits
([indexcmds.c#locktags](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3042-L3066)),
then takes the session lock on every recorded relation
([indexcmds.c#session-locks](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3068-L3074))
and commits. These session locks survive the upcoming commits so nobody can drop
the relations mid-rebuild.

#### Phase 2: wait, then build each new index

**Wait 1** is `WaitForLockersMultiple(lockTags, ShareLock, true)`: it waits out
the current transactions holding locks that conflict with `ShareLock`, so no
running writer or stronger table operation can still have the table open without
the new index in its index list
([indexcmds.c#wait1](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3090-L3093),
[lock.c#ShareLock-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L83-L86)).
Then, in a **separate transaction per index**, RIC takes a fresh snapshot and calls
`index_concurrently_build`, which scans the heap, builds the new copy, and sets
`indisready = true`
([indexcmds.c#build-loop](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3095-L3128),
[index.c#index_concurrently_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L1399-L1439)).
This is the same build CIC uses.

#### Phase 3: wait, validate, then wait for old snapshots

**Wait 2** is another `WaitForLockersMultiple(lockTags, ShareLock, true)`, so
that every current `ShareLock`-conflicting transaction finishes before the
validation pass assumes new writers see the new copy as ready-for-inserts
([indexcmds.c#wait2](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3139-L3142),
[lock.c#ShareLock-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L83-L86)).
Then, per new index, RIC registers a **reference snapshot**, runs `validate_index`
to backfill any tuples the build scan missed, saves the snapshot's `xmin` as
`limitXmin`, drops the snapshot, commits, and in a fresh transaction does **Wait 3**
= `WaitForOlderSnapshots(limitXmin, true)` to wait out transactions whose snapshot
predates the reference snapshot
([indexcmds.c#validate-loop](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3144-L3199)).
At the end of phase 3 the new copy contains every interesting tuple but is **still
invalid** — its `indisvalid` is not flipped here.

#### Phase 4: swap each old index with its new copy

In a single transaction, RIC chooses a name `<orig>_ccold` for the old index and
calls `index_concurrently_swap`, then invalidates the table's relcache and issues
a `CommandCounterIncrement` so the next index in the loop sees the new names
([indexcmds.c#swap-loop](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3212-L3262)).
`index_concurrently_swap` does the heavy lifting atomically
([index.c#index_concurrently_swap](../../../../raw/postgres-12/src/backend/catalog/index.c#L1447-L1716)):

- swaps the `relname`s — the new copy takes the original's name, the old index
  becomes `<orig>_ccold`
  ([index.c:1490-1492](../../../../raw/postgres-12/src/backend/catalog/index.c#L1490-L1492));
- copies the constraint flags `indisprimary`, `indisexclusion`, `indimmediate`
  from old to new
  ([index.c:1524-1529](../../../../raw/postgres-12/src/backend/catalog/index.c#L1524-L1529));
- marks the **new index valid and the old index invalid** at the same time, and
  clears `indisclustered` on the old
  ([index.c:1531-1534](../../../../raw/postgres-12/src/backend/catalog/index.c#L1531-L1534));
- moves constraints and their triggers, the comment, the partition inheritance
  link, and all dependencies from the old index to the new
  ([index.c:1542-1680](../../../../raw/postgres-12/src/backend/catalog/index.c#L1542-L1680));
- copies the cumulative statistics counters (scans, tuples returned/fetched,
  blocks fetched/hit) from old to new so per-index stats survive the rebuild
  ([index.c#stats-copy](../../../../raw/postgres-12/src/backend/catalog/index.c#L1683-L1705)).

The relcache invalidation makes every session re-plan against the rebuilt index
after this commit.

#### Phase 5: wait for readers, then mark old indexes dead

**Wait 4** is `WaitForLockersMultiple(lockTags, AccessExclusiveLock, true)`
([indexcmds.c#wait4](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3272-L3274)).
Because `AccessExclusiveLock` conflicts with every lock mode including
`AccessShareLock`, this waits out current table lock holders, including
**readers**. The wait is conservative: a reader need not actually use the old
index to be in the wait set, because the wait is on the heap relation lock tag
([lock.c#AccessExclusive-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L99-L103)).
Then `index_concurrently_set_dead` transfers predicate locks to the heap and sets
`indisready = false, indislive = false` (dead) on each old index
([indexcmds.c#set-dead-loop](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3276-L3290),
[index.c#index_concurrently_set_dead](../../../../raw/postgres-12/src/backend/catalog/index.c#L1727-L1761)).

#### Phase 6: wait for readers, then drop old indexes

After another `WaitForLockersMultiple(lockTags, AccessExclusiveLock, true)`
([indexcmds.c#wait5](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3302-L3304)),
RIC drops the old indexes with
`performMultipleDeletions(objects, DROP_RESTRICT, PERFORM_DELETION_CONCURRENT_LOCK | PERFORM_DELETION_INTERNAL)`
([indexcmds.c#drop-loop](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3306-L3329)).
`PERFORM_DELETION_CONCURRENT_LOCK` becomes `concurrent_lock_mode` in the
dependency deletion path. That makes `index_drop` take
`ShareUpdateExclusiveLock` (not `AccessExclusiveLock`) on the heap and index,
while skipping the `if (concurrent)` set-dead/two-wait branch because RIC already
did the dead-marking and reader waits itself
([dependency.c#deleteOneObject-index](../../../../raw/postgres-12/src/backend/catalog/dependency.c#L1345-L1352),
[index.c#index_drop-concurrent-lock-mode](../../../../raw/postgres-12/src/backend/catalog/index.c#L2001-L2197)).
Finally RIC releases all the session locks
([indexcmds.c#release-session-locks](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3337-L3342)).

### GUCs that affect REINDEX INDEX CONCURRENTLY performance

For a typical B-tree RIC, examine `maintenance_work_mem`,
`max_parallel_maintenance_workers`, `min_parallel_table_scan_size`,
`max_parallel_workers`, and `max_worker_processes` first. The first setting
controls build and validation memory. The other four determine whether the first
heap scan requests parallel workers and whether those workers can launch. In
PostgreSQL 12, B-tree is the only access method with a parallel build path
([index.c#B-tree-parallel-boundary](../../../../raw/postgres-12/src/backend/catalog/index.c#L2844-L2854),
[planner.c#plan_create_index_workers](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6226-L6362)).

Within one `ReindexRelationConcurrently` invocation over `N` indexes, the source
has six fixed internal commits plus three per index: one after each build, one
after each validation scan, and one after each old-snapshot wait. A one-index
RIC therefore executes nine internal commits, then starts the transaction that
the utility-command caller finishes. It also has five blocker waits, including
two reader waits that CIC lacks
([indexcmds.c#build-and-validation-commits](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3076-L3199),
[indexcmds.c#swap-set-dead-drop-commits](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3212-L3345),
[postgres.c#command-end-commit](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2569-L2578)).

This section uses a bounded meaning of “performance impact”: the setting must
change a core RIC phase, a shipped access method, worker availability, heap or
temporary I/O, WAL/commit latency, or a command wait. Index expressions and
third-party access methods can execute arbitrary code and read additional GUCs;
the core path delegates the physical build to the access method's `ambuild`
callback, so no core-source list can cover those additions
([amapi.h#ambuild_function](../../../../raw/postgres-12/src/include/access/amapi.h#L97-L107),
[index.c#ambuild-dispatch](../../../../raw/postgres-12/src/backend/catalog/index.c#L2899-L2904)).

**Application scope used below.** “Session” means a `PGC_USERSET` setting, or a
`PGC_SUSET` setting changed by a superuser, with no reload or restart.
Although those contexts can also be transaction-local, a session value is the
usable per-run scope: RIC cannot run inside an explicit transaction, and its own
commits end transaction-local values. Parallel workers restore the leader's
serialized GUC state
([utility.c#RIC-transaction-block](../../../../raw/postgres-12/src/backend/tcop/utility.c#L773-L782),
[ref/set.sgml#SET-scope](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L33-L115),
[parallel.c#serialize-GUC-state](../../../../raw/postgres-12/src/backend/access/transam/parallel.c#L349-L352),
[parallel.c#restore-GUC-state](../../../../raw/postgres-12/src/backend/access/transam/parallel.c#L1349-L1361)).

**Build, scan, and storage settings.**

| GUC | Exact RIC effect and boundary | Default and application |
|---|---|---|
| `maintenance_work_mem` | The main direct control. Phase 2 passes through the AM's build algorithm; phase 3 uses the setting for the serial encoded-TID validation sort. The automatic B-tree worker request also reserves at least 32 MB per participant, including the leader ([index.c#index_concurrently_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L1399-L1438), [index.c#validation-sort](../../../../raw/postgres-12/src/backend/catalog/index.c#L3228-L3283), [planner.c#memory-worker-cap](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6344-L6356)). | 64 MB, with a 1 MB minimum; session; no reload or restart ([guc.c#maintenance_work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2243-L2252)). |
| `max_parallel_maintenance_workers` | Caps the B-tree workers requested for the first build. Zero disables parallel maintenance workers. It is a request cap, not a guarantee that workers launch ([planner.c#worker-request-cap](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6257-L6356)). | 2; session; no reload or restart ([guc.c#max_parallel_maintenance_workers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2997-L3005)). |
| `min_parallel_table_scan_size` | The automatic model rejects a heap below this threshold, then adds workers as heap size crosses successive threefold thresholds. A table `parallel_workers` reloption bypasses both this size model and the 32 MB request test, but remains capped by `max_parallel_maintenance_workers` ([allpaths.c#compute_parallel_worker](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L3562-L3653), [planner.c#parallel_workers-override](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6317-L6329)). | 8 MB; session; no reload or restart ([guc.c#parallel-scan-thresholds](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3119-L3139)). |
| `max_parallel_workers`; `max_worker_processes` | The first caps active parallel workers when RIC registers them. The second sizes the shared background-worker slot array. Pool pressure can launch fewer workers than requested; B-tree then continues with the workers that launched or falls back to a serial build ([bgworker.c#worker-slot-pool](../../../../raw/postgres-12/src/backend/postmaster/bgworker.c#L138-L173), [bgworker.c#parallel-and-slot-caps](../../../../raw/postgres-12/src/backend/postmaster/bgworker.c#L931-L1005), [nbtsort.c#parallel-fallback](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1447-L1485)). | Both default to 8. `max_parallel_workers` is session-scoped; `max_worker_processes` is `postmaster` context and needs restart ([guc.c#max_worker_processes](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2788-L2797), [guc.c#max_parallel_workers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3018-L3026)). |
| `effective_cache_size` | Only GiST's buffered build reads it. Together with `maintenance_work_mem`, it limits buffered subtree depth; it does not reserve cache or control the other shipped AMs ([gistbuild.c#gistInitBuffering](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L311-L417)). | 524,288 blocks, normally 4 GB at 8 kB per block; session; no reload or restart ([cost.h#DEFAULT_EFFECTIVE_CACHE_SIZE](../../../../raw/postgres-12/src/include/optimizer/cost.h#L21-L32), [guc.c#effective_cache_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3117)). |
| `shared_buffers` | Its `NBuffers` value changes two decisions: each heap scan gets a nominal 256 kB bulk-read ring, capped at `NBuffers / 8`, only when the heap exceeds `NBuffers / 4`, and a permanent hash-index build caps its sort-selection threshold at `NBuffers`. More shared buffers can move either threshold; it is not a monotonic RIC speed control ([heapam.c#bulk-and-sync-threshold](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L296), [freelist.c#BAS_BULKREAD](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L537-L587), [hash.c#hashbuild-sort-choice](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L132-L159)). | The compiled boot default is 1,024 blocks, normally 8 MB; `postmaster` context; restart ([guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2162)). |
| `synchronize_seqscans` | On a sufficiently large heap, the first scan can start at another synchronized scan's location and wrap around; it still reads every page. B-tree, hash, GiST, SP-GiST, and Bloom permit this. GIN and BRIN require physical order and disable it. Validation always disables it ([heapam.c#syncscan-choice](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L267-L296), [gininsert.c#no-syncscan](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L378-L384), [brin.c#physical-order](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L720-L724), [heapam_handler.c#validation-order](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1751-L1763)). | On; session; no reload or restart ([guc.c#synchronize_seqscans](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1732-L1740)). |
| `temp_tablespaces`; `temp_file_limit` | `temp_tablespaces` places tuplesort spills, parallel B-tree worker tapes, and GiST buffered-build files. `temp_file_limit` does not throttle RIC: each process errors when its accounted temporary files cross the limit. Such an error occurs before the swap and can leave an invalid `_ccnew` while preserving the original index ([tuplesort.c#PrepareTempTablespaces](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L2468-L2475), [sharedfileset.c#parallel-temp-tablespaces](../../../../raw/postgres-12/src/backend/storage/file/sharedfileset.c#L36-L68), [gistbuildbuffers.c#temporary-buffer-file](../../../../raw/postgres-12/src/backend/access/gist/gistbuildbuffers.c#L44-L62), [fd.c#temp-file-limit](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1933-L1958), [indexcmds.c#pre-swap-phases](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3080-L3210)). | `temp_tablespaces` defaults to the database default tablespace and is session-scoped. `temp_file_limit` defaults to unlimited (`-1`), is `PGC_SUSET`, and is session-scoped for a superuser; neither needs reload or restart ([guc.c#temp_file_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2270-L2278), [guc.c#temp_tablespaces](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3646-L3655)). |
| `backend_flush_after` | For hash, GiST, GIN, SP-GiST, BRIN, and Bloom output built through shared buffers, this setting can trigger writeback advice after this backend flushes dirty victim buffers under pressure. It does not apply to B-tree's direct-outside-shared-buffers output path, and zero disables the advice ([buf_init.c#BackendWritebackContext](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L146-L152), [bufmgr.c#backend-writeback](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1125-L1156), [nbtsort.c#direct-build-sync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307)). | 0; session; no reload or restart ([guc.c#backend_flush_after](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2777-L2786), [pg_config_manual.h#writeback-defaults](../../../../raw/postgres-12/src/include/pg_config_manual.h#L147-L163)). |
| Writer-side `gin_pending_list_limit`; `work_mem` | Neither sizes the initial GIN build. After phase 2 makes the new copy ready, concurrent writers can append to its pending list. Their `gin_pending_list_limit`, unless the copied index reloption overrides it, decides when regular cleanup starts; regular cleanup uses the writer's `work_mem`. Phase 3 forces cleanup with the RIC backend's `maintenance_work_mem`, so writer settings can change how much work validation inherits ([index.c#copy-reloptions](../../../../raw/postgres-12/src/backend/catalog/index.c#L1287-L1293), [index.c#apply-reloptions](../../../../raw/postgres-12/src/backend/catalog/index.c#L1362-L1376), [gin_private.h#pending-list-limit](../../../../raw/postgres-12/src/include/access/gin_private.h#L21-L39), [ginfast.c#regular-cleanup-threshold](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L438-L461), [ginfast.c#cleanup-memory-selection](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L807-L828), [ginvacuum.c#validation-cleanup](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L583-L594)). | Both default to 4 MB and are session-scoped with no reload or restart; the relevant values are in concurrent writer sessions ([guc.c#work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2230-L2241), [guc.c#gin_pending_list_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3175-L3184)). |

The phase-2 `maintenance_work_mem` effect depends on the access method. B-tree
sorts index tuples; hash conditionally sorts by bucket; GiST uses the setting
with `effective_cache_size` for buffered build; and GIN bounds its build
accumulator. SP-GiST, BRIN, and contrib Bloom do not read it during their first
build. Phase 3 still creates the common TID sort, although BRIN's
`ambulkdelete` reports no per-tuple TIDs and therefore leaves that sort empty
([nbtsort.c#primary-sort](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L378-L445),
[hash.c#hashbuild-sort-choice](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L132-L177),
[gistbuild.c#buffer-memory-boundary](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L311-L417),
[gininsert.c#build-threshold](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L245-L314),
[spginsert.c#spgbuild](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L71-L149),
[brin.c#brinbuild](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L658-L743),
[blinsert.c#blbuild](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L119-L159),
[brin.c#brinbulkdelete](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L766-L784)).

PostgreSQL 12 has no heap read-stream layer. Both heap passes use ordinary table
scans; a large heap gets the bulk-read ring above, and `heapgettup` fetches the
next block with the ordinary buffer path. `effective_io_concurrency` drives
bitmap-heap prefetch and a tuple-deletion horizon helper, but neither concurrent
index heap pass calls those paths; the validation callback never deletes an
index TID
([heapam_handler.c#build-scan](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1212-L1247),
[heapam_handler.c#validation-scan](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1751-L1772),
[heapam.c#sequential-next-block](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L702-L766),
[nodeBitmapHeapscan.c#effective_io_concurrency](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L797-L817),
[heapam.c#deletion-horizon-prefetch](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L6970-L7040),
[index.c#validation-callback](../../../../raw/postgres-12/src/backend/catalog/index.c#L3300-L3312)).
Thus `effective_io_concurrency` is not a direct v12 RIC control
([guc.c#effective_io_concurrency](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2759-L2775)).

`default_tablespace` also does **not** place the rebuilt copy. RIC always passes
the old index's `reltablespace` into `index_create`, and v12 `REINDEX` has no
`TABLESPACE` clause. Output-storage performance therefore follows the old index
placement; changing it requires a separate operation, not a per-run GUC
([index.c#RIC-tablespace](../../../../raw/postgres-12/src/backend/catalog/index.c#L1355-L1376),
[ref/reindex.sgml#syntax](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L22-L25),
[guc.c#default_tablespace](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3635-L3644)).
RIC processes each index build and validation in its own transaction rather than
building all selected indexes in parallel, so one command does not multiply
`maintenance_work_mem` by its number of indexes at a single instant; a B-tree
build can still divide that one operation's budget among parallel participants
([indexcmds.c#per-index-builds](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3080-L3128),
[indexcmds.c#per-index-validations](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3131-L3199),
[ref/create_index.sgml#parallel-memory](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L716-L753)).

**WAL, checkpoints, and commit latency.** B-tree builds pages outside shared
buffers, WAL-logs each page as a forced image when `XLogIsNeeded()` is true, and
immediately syncs the permanent index file before returning. Hash, GiST, GIN,
SP-GiST, BRIN, and Bloom build through shared buffers; GiST, GIN, and SP-GiST
log the completed page range, while hash, BRIN, and Bloom use their ordinary
buffered WAL paths
([nbtsort.c#build-WAL](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L576-L580),
[nbtsort.c#page-WAL](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L656-L662),
[nbtsort.c#immediate-sync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307),
[gistbuild.c#build-WAL](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L217-L226),
[gininsert.c#build-WAL](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L408-L417),
[spginsert.c#build-WAL](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L134-L143),
[hash.c#hashbuild](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L126-L177),
[hashpage.c#hash-build-WAL](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L346-L402),
[brin.c#build-WAL](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L683-L709),
[blinsert.c#Bloom-build](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L44-L159),
[rel.h#RelationNeedsWAL](../../../../raw/postgres-12/src/include/utils/rel.h#L515-L520)).

| GUC | Exact RIC effect and boundary | Default and application |
|---|---|---|
| `synchronous_commit`; `synchronous_standby_names` | Only internal transactions that assign an XID and write WAL can take the ordinary local-flush and synchronous-standby commit path. The v12 build, validation, and state-only phases can write WAL without an XID and therefore take the asynchronous branch even when `synchronous_commit = on`; B-tree still performs its separate data-file sync before its build returns. Phase 6's non-temporary relation deletion forces a local WAL flush even when the GUC is off ([index.c#xidless-state-updates](../../../../raw/postgres-12/src/backend/catalog/index.c#L3314-L3403), [index.c#xidless-build-stats](../../../../raw/postgres-12/src/backend/catalog/index.c#L2676-L2805), [xact.c#xidless-and-sync-commit](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1220-L1426), [indexcmds.c#phase-6-drop](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3296-L3332), [nbtsort.c#immediate-sync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307)). | `synchronous_commit` defaults to `on`; session; no reload or restart. `synchronous_standby_names` defaults empty; `sighup` context; reload ([guc.c#synchronous_commit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4353-L4361), [guc.c#synchronous_standby_names](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4086-L4095)). |
| `wal_compression` | Forced and ordinary full-page images can be compressed, trading CPU for fewer WAL bytes when pages compress well. B-tree's build records use forced images, so their presence does not depend on `full_page_writes` ([xloginsert.c#full-page-compression](../../../../raw/postgres-12/src/backend/access/transam/xloginsert.c#L578-L630), [xloginsert.c#forced-page-image](../../../../raw/postgres-12/src/backend/access/transam/xloginsert.c#L960-L995)). | Off; `PGC_SUSET`; session for a superuser; no reload or restart ([guc.c#wal_compression](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1187-L1195)). |
| `wal_level` | B-tree explicitly WAL-logs its privately built pages only when `XLogIsNeeded()` is true. At `minimal`, it skips those page records and relies on its final file sync. This is a restart-level cluster architecture choice, not a practical per-run RIC setting; `minimal` cannot support WAL archiving or streaming replication ([xlog.h#XLogIsNeeded](../../../../raw/postgres-12/src/include/access/xlog.h#L177-L181), [nbtsort.c#build-WAL](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L576-L580), [nbtsort.c#immediate-sync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307), [config.sgml#wal_level](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2446-L2479)). | `replica`; `postmaster` context; restart ([guc.c#wal_level](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4409-L4417)). |
| `wal_buffers`; `wal_sync_method` | These are generic WAL-path controls: the first sizes shared WAL buffering for RIC's WAL stream; the second selects how WAL is forced to disk. Neither changes worker count or scan shape ([guc.c#wal_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2602-L2611), [guc.c#wal_sync_method](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4438-L4447)). | `wal_buffers` defaults to `-1` (automatic), is `postmaster` context, and needs restart. `wal_sync_method` uses the platform default, is `sighup` context, and needs reload. |
| `max_wal_size`; `checkpoint_timeout`; `checkpoint_completion_target`; `checkpoint_flush_after` | The first two influence automatic checkpoint frequency; the latter two pace checkpoint writes and writeback. They can change concurrent background I/O and the ordinary buffered AMs' full-page-image pattern, but B-tree's private build always performs its final immediate relation sync regardless of whether a checkpoint crossed the build ([guc.c#checkpoint-size-time-flush](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2542-L2600), [guc.c#checkpoint_completion_target](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3413-L3421), [nbtsort.c#immediate-sync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307)). | Normally 1 GB, 5 minutes, `0.5`, and 32 blocks on systems with `sync_file_range` (otherwise 0); all are `sighup` context and need reload, not restart ([pg_config_manual.h#writeback-defaults](../../../../raw/postgres-12/src/include/pg_config_manual.h#L147-L163)). |
| `commit_delay`; `commit_siblings` | When enabled and enough other transactions are active, the WAL flush path deliberately sleeps before group commit. It can improve aggregate throughput while adding latency to affected XID-bearing RIC commits; xidless phase commits do not enter this flush path, and defaults add no delay ([xlog.c#group-commit-delay](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2893-L2903), [xact.c#xidless-commit](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1228-L1272)). | `commit_delay = 0`; `PGC_SUSET`, superuser session. `commit_siblings = 5`; session. Neither needs reload or restart ([guc.c#commit-delay](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2667-L2688)). |

Disabling `fsync` or `full_page_writes` is not a safe production RIC tuning
method. Both are `sighup` settings and need reload. `fsync = off` also makes
B-tree's final `pg_fsync` call a no-op, while `REGBUF_FORCE_IMAGE` makes its
build page images independent of `full_page_writes`
([guc.c#fsync](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1122-L1133),
[guc.c#full_page_writes](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1163-L1175),
[fd.c#pg_fsync](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L329-L355),
[xloginsert.c#forced-page-image](../../../../raw/postgres-12/src/backend/access/transam/xloginsert.c#L960-L995)).

**Wait and cancellation settings.** These settings do not make either heap scan
faster. They bound or expose the initial relation lock and RIC's five waits:

| GUC | RIC behavior | Default and application |
|---|---|---|
| `statement_timeout` | Covers the client statement across all internal commits, scans, and five waits. RIC calls `StartTransactionCommand` directly, so it does not restart the statement timer; the normal command-end path disables it ([postgres.c#statement-timeout-lifetime](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2546-L2578), [postgres.c#enable_statement_timeout](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4680-L4716)). | 0 (disabled); session; no reload or restart ([guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2385)). |
| `lock_timeout` | Applies to initial relation-lock acquisition and to each individual VXID lock used by all five waits. It restarts for each lock acquisition, so it is not an aggregate limit for a wait phase, blocker set, or whole command ([indexcmds.c#initial-index-lock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2336-L2360), [lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L850-L934), [indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L339-L402), [lock.c#VirtualXactLock](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L4361-L4458), [proc.c#lock-timeout-timer](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1235-L1264)). | 0 (disabled); session; no reload or restart ([guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2396)). |
| `deadlock_timeout`; `log_lock_waits` | The first controls when a blocked lock acquisition runs deadlock detection; lowering it does not end a non-deadlocked wait. The second logs waits that survive that interval. They are detection and observability controls, not throughput controls ([proc.c#deadlock-and-lock-timeouts](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1235-L1298), [proc.c#long-wait-logging](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1377-L1469)). | 1 second and off; both are `PGC_SUSET`, so a superuser can use session scope with no reload or restart ([guc.c#deadlock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2062-L2072), [guc.c#log_lock_waits](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1489-L1497)). |
| Blocker-side `idle_in_transaction_session_timeout` | It does not fire in the actively running RIC backend. In another session it can terminate an idle-in-transaction reader or writer that blocks RIC; that is blocker policy, not a scan-speed setting ([postgres.c#idle-in-transaction-timer](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4126-L4152), [postgres.c#idle-timer-stop](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4203-L4210)). | 0 (disabled); session in the blocker; no reload or restart ([guc.c#idle_in_transaction_session_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2399-L2407)). |

PostgreSQL 12 has no `transaction_timeout` GUC, so there is no per-internal-
transaction timeout counterpart to the end-to-end `statement_timeout`. It also
has no `maintenance_io_concurrency`, `io_combine_limit`, or
`track_wal_io_timing`; those names have no definitions in the v12 GUC registry,
and the heap-scan path above has no read-stream interface
([guc.c#timeout-GUCs](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2407),
[guc.c#I/O-GUCs](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2759-L2786),
[guc.c#I/O-timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1381-L1408),
[heapam_handler.c#table-scan-interface](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1212-L1247)).

A timeout or cancellation after phase 1 can leave the committed transient index
behind. Before the atomic swap it is the invalid `_ccnew`; after the swap the
rebuilt index has the original name and an invalid `_ccold` can remain. Timeouts
are therefore completion policy, not free acceleration
([indexcmds.c#phase-boundaries](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3076-L3332),
[index.c#atomic-swap](../../../../raw/postgres-12/src/backend/catalog/index.c#L1490-L1537)).

**Commonly confused settings and practical priority.**

- `min_parallel_index_scan_size` does not participate: RIC's worker planner
  passes `index_pages = -1`, so only `min_parallel_table_scan_size` supplies a
  size threshold. `max_parallel_workers_per_gather` and
  `parallel_leader_participation` govern query executor nodes, not the private
  B-tree maintenance build; B-tree hard-codes leader participation unless a
  compile-time test macro disables it. Planner cost GUCs likewise do not choose
  the worker count in this size-based function
  ([planner.c#heap-only-worker-model](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6317-L6356),
  [allpaths.c#index-threshold-guard](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L3591-L3647),
  [guc.c#query-leader-participation](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1857-L1866),
  [nbtsort.c#build-leader-participation](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1345-L1362)).
- The RIC backend's `work_mem`, `autovacuum_work_mem`, and `vacuum_cost_*`
  settings do not size or throttle the common validation path. Validation uses
  `maintenance_work_mem`; its forced GIN cleanup selects that value for a normal
  RIC backend. A unique B-tree allocates a secondary `work_mem` spool during the
  first build, but the concurrent MVCC scan supplies no dead tuples and discards
  it empty. `vacuum_delay_point()` returns without delaying when
  `VacuumCostActive` is false
  ([index.c#validation-sort](../../../../raw/postgres-12/src/backend/catalog/index.c#L3228-L3283),
  [ginfast.c#forced-cleanup-memory](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L807-L828),
  [nbtsort.c#secondary-sort](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L447-L520),
  [heapam_handler.c#concurrent-tuples-are-alive](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1595-L1665),
  [vacuum.c#vacuum_delay_point](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1939-L1971)).
- `track_activities`, `trace_sort`, `log_temp_files`, and `track_counts` expose
  progress or spills rather than changing RIC's correctness algorithm.
  `track_io_timing` adds measurements but can add significant clock-call
  overhead on some systems; it is `PGC_SUSET`, defaults off, and can use
  superuser session scope without reload or restart
  ([pgstat.c#track_activities](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L3191-L3231),
  [guc.c#trace_sort](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1635-L1645),
  [fd.c#temp-file-reporting](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1271-L1286),
  [guc.c#I/O-timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1381-L1408),
  [config.sgml#I/O-timing-overhead](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6854-L6870)).

In practice, tune and measure in this order: (1) `maintenance_work_mem`; (2) for
B-tree, the full worker request-and-availability chain; (3) AM-specific GiST or
GIN behavior; (4) heap and temporary I/O on the existing tablespaces; and (5)
WAL, checkpoints, and commit confirmation. Diagnose the five blocker waits
separately, because memory and workers cannot shorten them
([ref/create_index.sgml#memory-and-parallelism](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L707-L771),
[ref/reindex.sgml#concurrent-cost](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L283-L296),
[indexcmds.c#RIC-waits](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3080-L3304)).
There is no source-derived universal best value; the direct RIC regression and
isolation tests check lifecycle and concurrency, not comparative GUC performance
([create_index.sql#RIC-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L786-L986),
[reindex-concurrently.spec](../../../../raw/postgres-12/src/test/isolation/specs/reindex-concurrently.spec#L1-L40)).
At the build boundary, v12 compiles the GUC registry directly in `guc.c`; its
makefile lists `guc.o` and the generated `guc-file.c` scanner only as that
object's dependency
([utils/misc/Makefile#guc](../../../../raw/postgres-12/src/backend/utils/misc/Makefile#L17-L33)).

### All steps and locks required on the table

Two lock layers act on each **heap table**, exactly as in CIC: a
**transaction-level** `ShareUpdateExclusiveLock` re-taken inside each helper, and a
**session-level** `ShareUpdateExclusiveLock` that spans the commit gaps. RIC
additionally holds session `ShareUpdateExclusiveLock` on both the **old and new
index** relations — their lock relids are registered in the phase-1 loop
([indexcmds.c#index-session-locks](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3024-L3029))
and locked alongside the heaps
([indexcmds.c#session-locks](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3068-L3074)).
DML never conflicts with any of these
([lock.c#SUE-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L78-L81)).

The waits are **not** table locks. `WaitForLockersMultiple` reads the current set
of conflicting lock holders and sleeps on each holder's virtual transaction ID
until it ends; later transactions are not waited for
([lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L850-L949)).
The conflict mode passed to the wait decides who is waited out:

| Phase | Relation locks held by RIC | Wait | Conflict mode | Who it waits out |
|---|---|---|---|---|
| 1: create copies | transaction, then session `ShareUpdateExclusiveLock` on heap and indexes | — | — | — |
| 2: before build | session `ShareUpdateExclusiveLock`; build later takes heap `ShareUpdateExclusiveLock` and new-index `RowExclusiveLock` | Wait 1 | `ShareLock` | current holders conflicting with `ShareLock`, usually open writers, plus stronger table operations ([lock.c:83-86](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L83-L86)) |
| 3: before validation | session `ShareUpdateExclusiveLock`; validation later takes heap `ShareUpdateExclusiveLock` and new-index `RowExclusiveLock` | Wait 2 | `ShareLock` | same `ShareLock` conflict set |
| 3: after validation | session `ShareUpdateExclusiveLock` | Wait 3 | `WaitForOlderSnapshots` | same-database **old-snapshot** holders ([indexcmds.c:339-402](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L339-L402)) |
| 5: before set-dead | session `ShareUpdateExclusiveLock`; set-dead later takes heap and old-index `ShareUpdateExclusiveLock` | Wait 4 | `AccessExclusiveLock` | current table lock holders, including **readers** ([lock.c:99-103](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L99-L103)) |
| 6: before drop | session `ShareUpdateExclusiveLock`; drop later takes heap and old-index `ShareUpdateExclusiveLock` | Wait 5 | `AccessExclusiveLock` | current table lock holders, including **readers** |

So RIC has the same three CIC waits (`ShareLock`, `ShareLock`, old snapshots)
**plus** two reader-capable waits that CIC does not have. Those two reader waits
exist because the old index may still be usable by transactions that planned
before the swap, so RIC cannot remove it until current table lock holders that
might touch it have finished
([reindex.sgml#concurrent-steps](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L334-L359)).

Because `ShareUpdateExclusiveLock` is self-conflicting, only one concurrent build
(CIC or RIC), `VACUUM`, or `ANALYZE` can run on a given table at a time
([lock.c#self-conflict](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L194-L196)).

### State flags for the old and new index

RIC drives the same three `pg_index` flags as CIC — `indislive`, `indisready`,
`indisvalid` — but on **two** indexes at once. They progress like this:

| Step | New copy (`_ccnew`) | Old index |
|---|---|---|
| after phase 1 | live, not ready, **not valid** | live, ready, valid |
| after phase 2 build | live, **ready**, not valid | unchanged |
| after phase 3 validate | live, ready, not valid (data complete) | unchanged |
| after phase 4 swap | live, ready, **valid** (takes original name) | **invalid** (renamed `_ccold`) |
| after phase 5 set-dead | unchanged | **dead** (`indisready=false`, `indislive=false`) |
| after phase 6 drop | the surviving index | gone |

The new copy's flags are set by the shared `index_set_state_flags` ladder
(`INDEX_CREATE_SET_READY`); its `indisvalid` is flipped by the swap, not by
`index_set_state_flags`
([index.c#swap-mark-valid](../../../../raw/postgres-12/src/backend/catalog/index.c#L1531-L1534)).
The old index is set dead by `index_set_state_flags(INDEX_DROP_SET_DEAD)`, whose
assert requires the index already be invalid — which the swap guarantees
([index.c#INDEX_DROP_SET_DEAD](../../../../raw/postgres-12/src/backend/catalog/index.c#L3384-L3396)).
All `index_set_state_flags` writes are **non-transactional in-place** updates that
cannot roll back
([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403)).

### Failure scenarios and the outcome on the table

Like CIC, RIC commits many times, so the outcome depends on **which phase failed**.
The single most important property: a RIC failure on a **healthy** index never
leaves you without a working index, because the swap (phase 4) is the only step
that touches the original, and it runs only after the new copy is fully built and
validated.

| Failure point | Leftover on the table | Recovery |
|---|---|---|
| Phase 1 (gather / create copies / initial lock) | **none** — phase 1's single transaction rolls back, so no `_ccnew` persists; original untouched | retry |
| Phase 2 (Wait 1 or build) | one or more **invalid `_ccnew`** copies (the failing one **not ready**, any earlier-built ones **ready**); original state unchanged | `DROP INDEX <name>_ccnew`, then retry |
| Phase 3 (Wait 2 / validate / Wait 3) | **invalid, ready `_ccnew`** copy; original state unchanged | `DROP INDEX <name>_ccnew`, then retry |
| Phase 4 (swap), before its commit | swap transaction rolls back: `_ccnew` still invalid, original state unchanged and normally named | `DROP INDEX <name>_ccnew`, then retry |
| Phase 5 or 6 (after swap committed) | the **new** index is already valid and carries the original name; the **old** `_ccold` index lingers (invalid, possibly dead) | `DROP INDEX <name>_ccold` |

Invalid leftovers are ignored for query planning: `get_relation_info` closes and
skips an index whose `indisvalid` flag is false. They can still matter for
writes, because `RelationGetIndexList` omits only indexes with `indislive =
false`, and executor insertion skips only indexes whose `ii_ReadyForInserts` is
false. That means a ready-but-invalid `_ccnew` or `_ccold` can still impose
write/HOT-safety overhead even though the planner will not choose it
([plancat.c#skip-invalid-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L199-L210),
[relcache.c#RelationGetIndexList](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4327-L4329),
[relcache.c#RelationGetIndexAttrBitmap](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4864-L4869),
[execIndexing.c#ExecInsertIndexTuples](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L330-L400)).
RIC's failure paths are ordinary ERROR/cancel/timeout aborts. Each phase loop
runs inside a transaction precisely so that an abort cleans up session locks
rather than leaking them
([indexcmds.c#abort-cleanup](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3105-L3110)).

The regression suite stages the phase-2 case directly. Starting from an index left
invalid by a failed CIC over duplicate data,
`REINDEX INDEX CONCURRENTLY concur_reindex_ind5` fails its build with
`could not create unique index "concur_reindex_ind5_ccnew" ... Key (c1)=(1) is
duplicated`, leaving **both** the original and a new `_ccnew` marked `INVALID`
([create_index.out#ccnew-invalid](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2323-L2333)).
The spare is removed with `DROP INDEX concur_reindex_ind5_ccnew`, and after the
duplicate row is deleted, `REINDEX INDEX CONCURRENTLY` repairs the original — `\d`
then shows it without `INVALID`
([create_index.out#repair](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2335-L2358)).
The docs describe the same `_ccnew` / `_ccold` leftovers and recommend dropping the
invalid index and retrying
([reindex.sgml#failure-recovery](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L363-L390)).

A unique `_ccnew` that reaches phase 3 enforces uniqueness while it is ready but
invalid, just like any ready index — so a duplicate appearing during the second
scan surfaces as a `duplicate key value violates unique constraint` error from
`_bt_check_unique`
([execIndexing.c#unique-check](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L371-L400),
[nbtinsert.c#dup-key](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L563-L568)).

### Can a failure leave an invalid index with the original index name?

**For a healthy index, no.** A `REINDEX INDEX CONCURRENTLY index_name` failure
never leaves the table with `index_name` marked invalid and therefore no usable
index. The name `index_name` always ends up on a **valid** index, so query plans
can still use it. `index_name` itself is left invalid only if it was **already
invalid before** the command ran — the repair case below.

Why the name is safe: the **swap in phase 4 is the only step that touches the
original index's name or its `indisvalid` flag**, and it does both together. In a
single transaction, `index_concurrently_swap` renames the rebuilt copy to
`index_name` and the old index to `index_name_ccold`, and in the same call flips
`new.indisvalid = true`, `old.indisvalid = false`
([index.c#swap-names](../../../../raw/postgres-12/src/backend/catalog/index.c#L1490-L1492),
[index.c#swap-mark-valid](../../../../raw/postgres-12/src/backend/catalog/index.c#L1531-L1537)).
Those validity writes use the **transactional** `CatalogTupleUpdate` — not the
in-place `index_set_state_flags` — and all swaps run inside one phase-4
transaction, so the rename and the validity flip commit or roll back together
([indexcmds.c#phase4-txn](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3212-L3261)).
The source comment states the intent: mark the new valid and the old invalid "at
the same time to make sure we only get constraint violations from the indexes
with the correct names"
([indexcmds.c:3207-3209](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3207-L3209)).

So every committed outcome keeps a valid `index_name`:

| When the failure happens | What `index_name` is | Invalid leftover |
|---|---|---|
| Phases 1-3, or phase 4 **before** it commits | the **original** index — name and `indisvalid` untouched, still valid even if bloated | a separate `index_name_ccnew` build copy, invalid |
| Phases 5-6, **after** the swap commits | the **rebuilt** index — already marked valid under `index_name` | the renamed `index_name_ccold` old index, invalid |

A pre-swap abort discards the `_ccnew` copy's catalog work with its transaction
and never renamed or invalidated the original; a post-swap failure can only
happen once the rebuilt index is already valid under `index_name`. The invalid
leftover is therefore always a **differently named** index (`_ccnew` or
`_ccold`), never the bare `index_name`. RIC's ordinary ERROR/cancel/timeout
aborts run inside each phase's transaction precisely so the abort rolls back
cleanly and frees the session locks
([indexcmds.c#abort-cleanup](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3105-L3110)).

This directly answers the bloat worry: you do **not** go from "one bloated but
valid `index_name`" to "no usable index." Before the swap the planner still has
the original (bloated) `index_name`; after the swap it has the fresh rebuild. The
planner skips only indexes whose `indisvalid` is false
([plancat.c#skip-invalid-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L199-L210)),
and in neither committed state is `index_name` the invalid one. A leftover
`_ccnew`/`_ccold` that is ready but invalid can still add write/HOT overhead until
you drop it, as the
[failure table](#failure-scenarios-and-the-outcome-on-the-table) notes, but it
does not remove your usable index.

**The one exception — repairing an already-invalid index.** If `index_name` was
invalid before you ran RIC (for example, left invalid by a failed
`CREATE INDEX CONCURRENTLY` or an earlier failed RIC), a new pre-swap failure
leaves it invalid — but only because it started that way, not because RIC broke a
healthy index. The v12 regression suite stages exactly this: a unique index made
invalid by a failed CIC over duplicate data, then
`REINDEX INDEX CONCURRENTLY concur_reindex_ind5` fails its build with
`could not create unique index "concur_reindex_ind5_ccnew"`, and `\d` shows
**both** `concur_reindex_ind5` and `concur_reindex_ind5_ccnew` as `INVALID`
([create_index.out#both-invalid](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2317-L2333)).
Dropping the `_ccnew` spare, deleting the duplicate, and re-running RIC makes
`concur_reindex_ind5` valid again
([create_index.out#repair](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2335-L2358)).

A crash or immediate shutdown mid-rebuild is a separate question. The swap's
validity flip is transactional, but the phase-2 set-ready and phase-5 set-dead
writes go through the non-transactional `index_set_state_flags` /
`heap_inplace_update` path, so the exact recovered flag state at a crash
instruction boundary is scoped under [Open Questions](#open-questions), not
asserted here
([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403)).

### Running REINDEX INDEX CONCURRENTLY on an invalid index

**It depends on how RIC reaches the invalid index.** Named directly, RIC
reindexes it — this is the supported way to repair an invalid index. Reached
through `REINDEX TABLE`/`SCHEMA`/`DATABASE CONCURRENTLY`, the invalid index is
**skipped with a warning**, so a bulk concurrent reindex never repairs one.

| How RIC reaches the invalid index | Outcome |
|---|---|
| `REINDEX INDEX CONCURRENTLY index_name` (named directly) | **allowed**: runs all six phases and, if the rebuild succeeds, leaves `index_name` valid again |
| `REINDEX TABLE`/`SCHEMA`/`DATABASE CONCURRENTLY` (reached via a relation) | **skipped**: `WARNING: cannot reindex invalid index "...", skipping`, leaving it invalid |

Why naming it directly works: in `ReindexRelationConcurrently`'s index-gathering
switch, the `RELKIND_INDEX` arm appends the target OID with **no validity test** —
the comment is explicit, "Note that invalid indexes are allowed here"
([indexcmds.c#index-arm](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2893-L2916)) —
and `ReindexIndex` has no validity gate either
([indexcmds.c#ReindexIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2336-L2382)).
The relation arm is the opposite: it walks `RelationGetIndexList` and, for any
index whose `indisvalid` is false, emits
`cannot reindex invalid index "%s.%s" concurrently, skipping` and drops it from
the work list
([indexcmds.c#skip-invalid-via-table](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2819-L2824));
toast indexes are skipped the same way, with `ERRCODE_INDEX_CORRUPTED`
([indexcmds.c:2865-2870](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2865-L2870)).

The repair does not depend on the old index's state. `index_concurrently_create_copy`
derives the `_ccnew` copy's definition — access method, operator classes,
collations, columns, expressions, predicate, and uniqueness — from the old
index's **catalog definition**, never from its `indislive`/`indisready`/`indisvalid`
flags, and always creates the copy not-ready and not-valid; the copy's data then
comes from a fresh heap scan, not from the (invalid) old index
([index.c#index_concurrently_create_copy](../../../../raw/postgres-12/src/backend/catalog/index.c#L1240-L1388)).
So an index that is invalid **and** not ready — for instance one left behind by a
failed `CREATE INDEX CONCURRENTLY` — rebuilds exactly like a healthy one. When the
rebuild succeeds, the phase-4 swap flips the new copy to valid under the original
name (and the old, already-invalid index to `_ccold`), so `index_name` is valid
again
([index.c#swap-mark-valid](../../../../raw/postgres-12/src/backend/catalog/index.c#L1531-L1534)).

Naming the invalid index does **not guarantee** repair. If the condition that made
it invalid still holds, the rebuild fails the same way, and because the failure is
**pre-swap** the original index is untouched and stays invalid — you end up with
**two** invalid indexes (the original plus the half-built `_ccnew`) and must drop
`_ccnew`, remove the cause, and retry. The v12 regression suite walks this exact
sequence on a unique index made invalid by a failed CIC over duplicate data:

1. `REINDEX INDEX CONCURRENTLY concur_reindex_ind5` (named directly) re-runs the
   build, hits the same duplicate, and fails with
   `could not create unique index "concur_reindex_ind5_ccnew" ... Key (c1)=(1) is
   duplicated`; `\d` then shows **both** `concur_reindex_ind5` and
   `concur_reindex_ind5_ccnew` as `INVALID`
   ([create_index.out#both-invalid](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2314-L2333)).
2. `REINDEX TABLE CONCURRENTLY concur_reindex_tab4` (reaching the index via the
   table) warns
   `cannot reindex invalid index "public.concur_reindex_ind5" concurrently, skipping`
   and — since that was the only index — adds
   `NOTICE: table "concur_reindex_tab4" has no indexes that can be reindexed
   concurrently`; the index stays `INVALID`
   ([create_index.out#skip-via-table](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2338-L2348)).
3. After `DROP INDEX concur_reindex_ind5_ccnew` and deleting the duplicate,
   `REINDEX INDEX CONCURRENTLY concur_reindex_ind5` (named directly) finally
   succeeds and `\d` shows it without `INVALID`
   ([create_index.out#repaired](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2350-L2358)).

This is why the failure-recovery guidance is to repair an invalid index by
**naming it** in `REINDEX INDEX CONCURRENTLY` (or a plain blocking `REINDEX INDEX`),
not by reindexing the whole table. The contrast with a *healthy* `index_name` —
which a failure never converts into the invalid leftover — is the
[previous section](#can-a-failure-leave-an-invalid-index-with-the-original-index-name);
the broader, cross-command catalog of how an index becomes invalid and how to
clear each case is on the
[invalid-index outcomes page](invalid-index-outcomes.md).

### Multiple indexes in one command

`REINDEX TABLE CONCURRENTLY` (and reindex of a matview or toast relation) rebuilds
every qualifying index of the relation in one run. RIC processes **each phase for
all indexes before moving to the next phase**, and runs each index's build and
validation in its own transaction, to bound how long any single transaction stays
open
([indexcmds.c#phase-overview](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2941-L2955),
[reindex.sgml#steps-loop](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L299-L302)).
The regression suite confirms a table reindex preserves index dependencies and
comments and rebuilds toast indexes, with the `pg_depend` listing identical before
and after
([create_index.out#deps-preserved](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2052-L2091),
[create_index.out#comment-preserved](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2110-L2115)).

### Watching the phases

RIC reports through `pg_stat_progress_create_index` with `command` =
`REINDEX CONCURRENTLY`
([indexcmds.c#progress-command](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2984-L2991)).
The wait phases map to the view's `phase` text via the integer codes in
`progress.h`
([progress.h#phases](../../../../raw/postgres-12/src/include/commands/progress.h#L73-L82),
[system_views.sql#create-index-view](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L1004-L1016)):
`waiting for writers before build`, `waiting for writers before validation`,
`waiting for old snapshots`, and `waiting for readers before marking dead`. See
[Open Questions](#open-questions) for the unused `waiting for readers before dropping`
text.

### Test coverage

- Functional coverage is in the main regression suite, in the `REINDEX CONCURRENTLY`
  block of `create_index.sql`: it reindexes tables, matviews, a single index, and
  toast indexes, checks dependency and comment preservation, and exercises the
  no-index `NOTICE`
  ([create_index.sql#ric-block](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L786-L905)).
  A later sub-test rebuilds expression and predicate indexes and verifies their
  definitions are unchanged with `pg_get_indexdef` before and after
  ([create_index.sql#exprs-preds](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L966-L986)).
- Restriction coverage, each with its own test: transaction-block and
  system-catalog rejection
  ([create_index.out#restrictions](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2278-L2296)),
  partitioned no-op/skip
  ([create_index.out#partitioned](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2152-L2163)),
  exclusion-constraint error-vs-skip
  ([create_index.out#exclusion](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2029-L2032)),
  invalid-index skip-vs-allow
  ([create_index.out#invalid-handling](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2314-L2358)),
  and temporary-table fallback
  ([create_index.out#temp](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2439-L2460)).
- Failure coverage: the invalid `_ccnew` leftover, its manual drop, and the eventual
  repair
  ([create_index.out#invalid-handling](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2314-L2358)).
- Isolation coverage: `reindex-concurrently.spec` runs one transaction that reads,
  one transaction that updates/inserts/deletes, and a `REINDEX TABLE
  CONCURRENTLY` session across six permutations; the expected output shows the
  reindex waiting in the permutations where an open read or write transaction is
  still relevant, then completing after those transactions commit
  ([reindex-concurrently.spec](../../../../raw/postgres-12/src/test/isolation/specs/reindex-concurrently.spec#L1-L40),
  [reindex-concurrently.out](../../../../raw/postgres-12/src/test/isolation/expected/reindex-concurrently.out#L1-L78)).

## Context Reviewed

- `wiki/versions.md`, `wiki/index.md`, `wiki/v12/index.md`, and the last ~20
  `wiki/log.md` entries (navigation only).
- The sibling page
  [How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 12](create-index-concurrently.md),
  which documents the shared build/validate core and the wait semantics this page
  reuses.
- Pinned checkout `raw/postgres-12/` at commit
  `45b88269a353ad93744772791feb6d01bc7e1e42` ("Stamp 12.2.").
- `ReindexRelationConcurrently`, `ReindexIndex`, `ReindexTable`,
  `ReindexMultipleTables`, and `WaitForOlderSnapshots` in
  `src/backend/commands/indexcmds.c`.
- `index_concurrently_create_copy`, `index_concurrently_build`,
  `index_concurrently_swap`, `index_concurrently_set_dead`, `index_drop`, and
  `index_set_state_flags` in `src/backend/catalog/index.c`.
- `WaitForLockersMultiple` in `src/backend/storage/lmgr/lmgr.c`; the `LockConflicts`
  table in `src/backend/storage/lmgr/lock.c`; lock-mode definitions in
  `src/include/storage/lockdefs.h`.
- REINDEX dispatch and `PreventInTransactionBlock`/`PreventCommandDuringRecovery`
  in `src/backend/tcop/utility.c`.
- The CREATE INDEX progress phase codes in `src/include/commands/progress.h` and the
  `pg_stat_progress_create_index` view in
  `src/backend/catalog/system_views.sql`; the phase descriptions in
  `doc/src/sgml/monitoring.sgml`.
- `doc/src/sgml/ref/reindex.sgml` (CONCURRENTLY steps, restrictions, recovery).
- GUC definitions and apply contexts in `src/backend/utils/misc/guc.c`, with its
  Makefile dependency on the generated `guc-file.c` scanner.
- Build and validation in `index.c` and `heapam_handler.c`; B-tree, hash, GiST,
  GIN, SP-GiST, BRIN, and contrib Bloom build and bulk-delete callbacks.
- B-tree worker planning and launch in `planner.c`, `allpaths.c`, `nbtsort.c`,
  `bgworker.c`, and `parallel.c`, including table reloptions and GUC restoration.
- Heap scan strategy, synchronized scans, buffer-ring and writeback behavior,
  tablespace placement, tuplesort and temporary-file placement/limits, WAL
  insertion, B-tree immediate sync, checkpoints, commit synchronization, and
  timeout/lock paths.
- Whole-checkout searches for `transaction_timeout`,
  `maintenance_io_concurrency`, `io_combine_limit`, and `track_wal_io_timing`;
  none is defined in PostgreSQL 12.
- Same-checkout configuration, `CREATE INDEX`, and `REINDEX` documentation.
- Tests: `src/test/regress/sql/create_index.sql`,
  `src/test/regress/expected/create_index.out`,
  `src/test/isolation/specs/reindex-concurrently.spec`, and
  `src/test/isolation/expected/reindex-concurrently.out`; none directly sweeps
  the RIC GUC matrix.

## Evidence Map

| Claim | Source |
|---|---|
| RIC runs as six phases (create copy, build, catch up, swap, set dead, drop), each phase looping all indexes | [indexcmds.c:2941-2955](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2941-L2955) |
| CONCURRENTLY cannot run in a transaction block or during recovery | [utility.c:773-807](../../../../raw/postgres-12/src/backend/tcop/utility.c#L773-L807) |
| `REINDEX INDEX` locks `ShareUpdateExclusiveLock` for concurrent; temp falls back to non-concurrent | [indexcmds.c:2336-2382](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2336-L2382) |
| `REINDEX TABLE` no-qualifying-index NOTICE | [indexcmds.c:2477-2499](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2477-L2499) |
| System catalogs rejected directly, but skipped with warning during concurrent schema/database sweeps | [indexcmds.c:2804-2807](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2804-L2807), [indexcmds.c:2530-2533](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2530-L2533), [indexcmds.c:2641-2650](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2641-L2650) |
| Partitioned table warns and skips; partitioned index named directly errors before the concurrent path | [indexcmds.c:2917-2923](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2917-L2923), [indexcmds.c:2368-2371](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2368-L2371), [indexcmds.c:3390-3396](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3390-L3396) |
| Invalid index skipped via table, allowed when named directly | [indexcmds.c:2819-2824](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2819-L2824), [indexcmds.c:2908-2912](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2908-L2912) |
| A directly-named invalid index runs the full RIC rebuild because `index_concurrently_create_copy` derives the `_ccnew` copy from the old index's catalog definition (AM/opclass/collation/columns/exprs/predicate/uniqueness), not its `indisvalid`/`indisready` flags, and always creates the copy not-ready/not-valid; data comes from a fresh heap scan | [index.c:1240-1388](../../../../raw/postgres-12/src/backend/catalog/index.c#L1240-L1388), [indexcmds.c:2336-2382](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2336-L2382) |
| Repairing a directly-named invalid index can fail again pre-swap if the invalidity cause persists, leaving both the original and `_ccnew` invalid; reaching it via `REINDEX TABLE` only warns/skips (toast: `ERRCODE_INDEX_CORRUPTED`); a directly-named retry succeeds once the cause is removed | [indexcmds.c:2865-2870](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2865-L2870), [create_index.out:2314-2358](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2314-L2358) |
| Exclusion index: error if named directly, skip if via table | [index.c:1268-1271](../../../../raw/postgres-12/src/backend/catalog/index.c#L1268-L1271), [indexcmds.c:2825-2830](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2825-L2830) |
| Toast indexes are gathered and rebuilt with the table | [indexcmds.c:2844-2888](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2844-L2888) |
| Phase 1 creates `_ccnew` copy not-ready/not-valid via `index_concurrently_create_copy` | [indexcmds.c:2993-3003](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2993-L3003), [index.c:1240-1388](../../../../raw/postgres-12/src/backend/catalog/index.c#L1240-L1388) |
| Session `ShareUpdateExclusiveLock` taken on old index, new index, and heap(s) (index relids registered, then heap relids + `LOCKTAG`, then locked) | [indexcmds.c:3024-3029](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3024-L3029), [indexcmds.c:3042-3074](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3042-L3074) |
| Phase 2: Wait 1 (`ShareLock`) then per-index build sets `indisready` | [indexcmds.c:3090-3128](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3090-L3128), [index.c:1399-1439](../../../../raw/postgres-12/src/backend/catalog/index.c#L1399-L1439) |
| Phase 3: Wait 2 (`ShareLock`), `validate_index`, then Wait 3 (`WaitForOlderSnapshots`) | [indexcmds.c:3139-3199](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3139-L3199) |
| One invocation has six fixed internal commits plus three per index; a one-index RIC has nine before the final caller-owned transaction | [indexcmds.c:3076-3199](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3076-L3199), [indexcmds.c:3212-3345](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3212-L3345), [postgres.c:2569-2578](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2569-L2578) |
| Direct build controls are AM-dependent `maintenance_work_mem` plus the B-tree-only worker request and pool chain | [index.c:2844-2854](../../../../raw/postgres-12/src/backend/catalog/index.c#L2844-L2854), [index.c:3228-3283](../../../../raw/postgres-12/src/backend/catalog/index.c#L3228-L3283), [planner.c:6226-6362](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6226-L6362), [bgworker.c:931-1005](../../../../raw/postgres-12/src/backend/postmaster/bgworker.c#L931-L1005) |
| Large RIC heap passes can use `BAS_BULKREAD` and synchronized scanning, but v12 has no heap read streams and `effective_io_concurrency` does not drive these sequential passes | [heapam.c:233-296](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L296), [heapam_handler.c:1212-1247](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1212-L1247), [heapam_handler.c:1751-1763](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1751-L1763) |
| RIC always preserves the old index tablespace; v12 has no `REINDEX (TABLESPACE ...)`, and `default_tablespace` does not place the copy | [index.c:1355-1376](../../../../raw/postgres-12/src/backend/catalog/index.c#L1355-L1376), [reindex.sgml:22-25](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L22-L25) |
| B-tree has private page writes, forced-image WAL when needed, and a final immediate data-file sync; the other in-tree AMs build through shared buffers | [nbtsort.c:576-662](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L576-L662), [nbtsort.c:1288-1307](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307), [rel.h:515-520](../../../../raw/postgres-12/src/include/utils/rel.h#L515-L520) |
| `synchronous_commit` affects XID-bearing WAL commits, while xidless WAL-writing phases commit asynchronously and phase 6 deletion forces a local flush | [index.c:2676-2805](../../../../raw/postgres-12/src/backend/catalog/index.c#L2676-L2805), [index.c:3314-3403](../../../../raw/postgres-12/src/backend/catalog/index.c#L3314-L3403), [xact.c:1220-1426](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1220-L1426) |
| `statement_timeout` spans RIC, and `lock_timeout` applies per VXID acquisition; v12 has no `transaction_timeout` | [postgres.c:2546-2578](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2546-L2578), [lock.c:4361-4458](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L4361-L4458), [guc.c:2377-2407](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2407) |
| Phase 4 swap: new valid + old invalid, names swapped, constraints/triggers/comment/deps/stats moved | [indexcmds.c:3212-3262](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3212-L3262), [index.c:1447-1716](../../../../raw/postgres-12/src/backend/catalog/index.c#L1447-L1716) |
| Old index renamed `_ccold`; new takes original name | [indexcmds.c:3230-3235](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3230-L3235), [index.c:1490-1492](../../../../raw/postgres-12/src/backend/catalog/index.c#L1490-L1492) |
| Per-index cumulative stats copied old->new during swap | [index.c:1683-1705](../../../../raw/postgres-12/src/backend/catalog/index.c#L1683-L1705) |
| Phase 5: Wait 4 (`AccessExclusiveLock`) then `index_concurrently_set_dead` (clears indisready+indislive) | [indexcmds.c:3272-3290](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3272-L3290), [index.c:1727-1761](../../../../raw/postgres-12/src/backend/catalog/index.c#L1727-L1761) |
| Phase 6: Wait (`AccessExclusiveLock`) then `performMultipleDeletions` drops old | [indexcmds.c:3302-3329](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3302-L3329) |
| Drop uses `PERFORM_DELETION_CONCURRENT_LOCK` -> `index_drop` takes SUE, skips its own concurrent set-dead/two-wait branch | [dependency.c:1345-1352](../../../../raw/postgres-12/src/backend/catalog/dependency.c#L1345-L1352), [index.c:2001-2197](../../../../raw/postgres-12/src/backend/catalog/index.c#L2001-L2197) |
| `AccessExclusiveLock` conflicts with `AccessShareLock`, so phases 5/6 wait out readers | [lock.c:99-103](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L99-L103) |
| `ShareLock` waits (Waits 1/2) wait out current holders of `RowExclusiveLock`, `ShareUpdateExclusiveLock`, `ShareRowExclusiveLock`, `ExclusiveLock`, or `AccessExclusiveLock` (not other `ShareLock` holders — `ShareLock` is not self-conflicting) | [lock.c:83-86](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L83-L86) |
| `WaitForLockersMultiple` waits on VXIDs, not later transactions | [lmgr.c:850-949](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L850-L949) |
| Invalid indexes are skipped by the planner but can still affect writes/HOT decisions while live/ready | [plancat.c:199-210](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L199-L210), [relcache.c:4327-4329](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4327-L4329), [relcache.c:4864-4869](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4864-L4869), [execIndexing.c:330-400](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L330-L400) |
| `index_set_state_flags` non-transactional in-place; `INDEX_DROP_SET_DEAD` asserts not valid | [index.c:3331-3403](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403) |
| Abort inside each phase loop cleans up session locks | [indexcmds.c:3105-3110](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3105-L3110) |
| Docs: two table scans, wait for transactions, six steps, `_ccnew`/`_ccold`, recovery | [reindex.sgml:283-390](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L283-L390) |
| Regression: failed `_ccnew` left INVALID, dropped, then repaired | [create_index.out:2323-2358](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2323-L2358) |
| A RIC failure keeps `index_name` on a valid index; only `_ccnew` (pre-swap) or `_ccold` (post-swap) is left invalid, because phase 4 atomically renames and flips `indisvalid` in one transaction via `CatalogTupleUpdate` | [indexcmds.c:3207-3261](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3207-L3261), [index.c:1490-1537](../../../../raw/postgres-12/src/backend/catalog/index.c#L1490-L1537) |
| `index_name` itself ends up invalid only when it was already invalid before RIC ran (repair case) | [create_index.out:2317-2358](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2317-L2358) |
| Regression: deps and comments preserved across reindex | [create_index.out:2052-2115](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2052-L2115) |
| Regression: txn-block, system-catalog, partitioned, exclusion, temp restrictions | [create_index.out:2029-2032](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2029-L2032), [create_index.out:2152-2163](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2152-L2163), [create_index.out:2278-2296](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2278-L2296), [create_index.out:2439-2460](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2439-L2460) |
| Isolation test covers concurrent read/write transactions around RIC | [reindex-concurrently.spec:1-40](../../../../raw/postgres-12/src/test/isolation/specs/reindex-concurrently.spec#L1-L40), [reindex-concurrently.out:1-78](../../../../raw/postgres-12/src/test/isolation/expected/reindex-concurrently.out#L1-L78) |
| Progress command is `REINDEX CONCURRENTLY`; phase codes/text | [indexcmds.c:2984-2991](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2984-L2991), [progress.h:73-82](../../../../raw/postgres-12/src/include/commands/progress.h#L73-L82), [system_views.sql:1004-1016](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L1004-L1016) |

## Open Questions

- The fastest safe values for a particular heap, index definition, access method,
  concurrent workload, storage system, and worker pool cannot be derived from
  source. They require controlled measurements of build, validation, commit, and
  wait phases.
- **The "waiting for readers before dropping" phase string is never emitted in
  v12.** `progress.h` defines `PROGRESS_CREATEIDX_PHASE_WAIT_5 = 9`, which the
  `pg_stat_progress_create_index` view and `monitoring.sgml` map to
  `waiting for readers before dropping`
  ([progress.h:81-82](../../../../raw/postgres-12/src/include/commands/progress.h#L81-L82),
  [system_views.sql:1014-1015](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L1014-L1015),
  [monitoring.sgml:3721-3730](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3721-L3730)).
  But phase 6 sets `PROGRESS_CREATEIDX_PHASE_WAIT_4` (value 8 =
  `waiting for readers before marking dead`), the same code phase 5 uses
  ([indexcmds.c:3272-3274](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3272-L3274),
  [indexcmds.c:3302-3304](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3302-L3304)).
  Per the source, the drop wait is reported as "waiting for readers before marking
  dead" and the `WAIT_5` text is unused. Source wins; this is recorded as a
  source-vs-view/docs discrepancy rather than a behavioral claim that the "before
  dropping" text appears.
- The first build scan's exact tuple-visibility rule lives inside `index_build` ->
  `table_index_build_scan` (via `ii_Concurrent`), which this page summarizes from
  the shared CIC core rather than tracing line-by-line into the table AM
  ([index.c:1426-1427](../../../../raw/postgres-12/src/backend/catalog/index.c#L1426-L1427)).
- The exact crash / immediate-shutdown outcome at each instruction boundary was not
  traced through crash recovery; as on the CIC page, `index_set_state_flags` is a
  non-transactional WAL-logged in-place overwrite, so the recovered flag state
  around the set-ready / swap / set-dead boundaries was not isolated
  ([index.c:3316-3324](../../../../raw/postgres-12/src/backend/catalog/index.c#L3316-L3324),
  [heapam.c#heap_inplace_update](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L5755-L5773)).
- Whether reindexing multiple indexes that share a long base name can collide on
  the `_ccnew` / `_ccold` names is mitigated by `ChooseRelationName` plus the
  per-iteration `CommandCounterIncrement`
  ([indexcmds.c:3250-3257](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3250-L3257)),
  but the exact truncation/uniqueness behavior of `ChooseRelationName` was not
  traced.

## Source References

- [indexcmds.c#ReindexRelationConcurrently](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2715-L3382)
- [indexcmds.c#ReindexIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2336-L2382)
- [indexcmds.c#ReindexTable](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2458-L2499)
- [indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L339-L402)
- [dependency.c#deleteOneObject-index](../../../../raw/postgres-12/src/backend/catalog/dependency.c#L1345-L1352)
- [index.c#index_concurrently_create_copy](../../../../raw/postgres-12/src/backend/catalog/index.c#L1240-L1388)
- [index.c#index_concurrently_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L1399-L1439)
- [index.c#index_concurrently_swap](../../../../raw/postgres-12/src/backend/catalog/index.c#L1447-L1716)
- [index.c#index_concurrently_set_dead](../../../../raw/postgres-12/src/backend/catalog/index.c#L1719-L1761)
- [index.c#index_drop](../../../../raw/postgres-12/src/backend/catalog/index.c#L2001-L2197)
- [index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403)
- [index.c#index_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L2810-L3005)
- [index.c#validate_index](../../../../raw/postgres-12/src/backend/catalog/index.c#L3112-L3298)
- [heapam_handler.c#heapam_index_build_range_scan](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1149-L1702)
- [heapam_handler.c#heapam_index_validate_scan](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1705-L1947)
- [nbtsort.c#B-tree-build](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L378-L662)
- [hash.c#hashbuild](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L110-L187)
- [gistbuild.c#gistbuild](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L110-L226)
- [gininsert.c#ginbuild](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L245-L427)
- [spginsert.c#spgbuild](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L71-L149)
- [brin.c#brinbuild](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L658-L743)
- [blinsert.c#blbuild](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L119-L159)
- [planner.c#plan_create_index_workers](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6226-L6363)
- [allpaths.c#compute_parallel_worker](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L3562-L3653)
- [bgworker.c#RegisterDynamicBackgroundWorker](../../../../raw/postgres-12/src/backend/postmaster/bgworker.c#L920-L1009)
- [heapam.c#scan-strategy](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L203-L296)
- [freelist.c#GetAccessStrategy](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L535-L587)
- [sharedfileset.c#SharedFileSetInit](../../../../raw/postgres-12/src/backend/storage/file/sharedfileset.c#L36-L72)
- [nbtsort.c#B-tree-immediate-sync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307)
- [xact.c#commit-flush](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1220-L1426)
- [xlog.c#group-commit-delay](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2893-L2903)
- [heapam.c#heap_inplace_update](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L5692-L5773)
- [plancat.c#skip-invalid-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L199-L210)
- [relcache.c#RelationGetIndexList](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4318-L4420)
- [relcache.c#RelationGetIndexAttrBitmap](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4841-L4869)
- [execIndexing.c#ExecInsertIndexTuples](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L330-L400)
- [lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L850-L949)
- [lock.c#LockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L65-L103)
- [lockdefs.h#lockmodes](../../../../raw/postgres-12/src/include/storage/lockdefs.h#L36-L46)
- [lock.c#VirtualXactLock](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L4361-L4458)
- [proc.c#lock-timeouts](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1235-L1298)
- [postgres.c#statement-timeout](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2546-L2578)
- [guc.c#maintenance_work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2243-L2252)
- [guc.c#timeouts](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2407)
- [guc.c#worker-pools](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2788-L2797)
- [guc.c#parallel-workers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2997-L3026)
- [guc.c#I/O-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2759-L2786)
- [guc.c#planner-and-GIN-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3184)
- [guc.c#WAL-size-checkpoint-and-commit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2542-L2688)
- [guc.c#WAL-commit-and-level](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4338-L4447)
- [utility.c#reindex-dispatch](../../../../raw/postgres-12/src/backend/tcop/utility.c#L773-L807)
- [progress.h#create-index-phases](../../../../raw/postgres-12/src/include/commands/progress.h#L73-L82)
- [system_views.sql#pg_stat_progress_create_index](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L1004-L1016)
- [monitoring.sgml#create-index-phases](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3630-L3731)
- [ref/reindex.sgml#CONCURRENTLY](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L283-L414)
- [nbtinsert.c#_bt_check_unique](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L563-L568)
- [create_index.sql#ric-block](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L786-L905)
- [create_index.out#ric-coverage](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2005-L2360)
- [reindex-concurrently.spec](../../../../raw/postgres-12/src/test/isolation/specs/reindex-concurrently.spec#L1-L40)
- [reindex-concurrently.out](../../../../raw/postgres-12/src/test/isolation/expected/reindex-concurrently.out#L1-L78)

## Navigation

- [How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 12](create-index-concurrently.md)
- [v12 index](../../index.md)
- [versions](../../../versions.md)
