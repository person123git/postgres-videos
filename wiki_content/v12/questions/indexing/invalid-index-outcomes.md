---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# All Outcomes That Leave an Invalid Index in PostgreSQL 12, Including a Failed CREATE INDEX CONCURRENTLY (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [The five outcomes at a glance](#the-five-outcomes-at-a-glance)
  - [What makes an index invalid](#what-makes-an-index-invalid)
  - [1. A failed, cancelled, or crashed CREATE INDEX CONCURRENTLY](#1-a-failed-cancelled-or-crashed-create-index-concurrently)
  - [2. A failed or cancelled REINDEX CONCURRENTLY](#2-a-failed-or-cancelled-reindex-concurrently)
  - [3. A failed or interrupted DROP INDEX CONCURRENTLY](#3-a-failed-or-interrupted-drop-index-concurrently)
  - [4. An incomplete partitioned index](#4-an-incomplete-partitioned-index)
  - [5. pg_upgrade from PostgreSQL 9.6 or earlier](#5-pg_upgrade-from-postgresql-96-or-earlier)
  - [Operations that do not leave an invalid index](#operations-that-do-not-leave-an-invalid-index)
  - [What an invalid index costs, and what rejects it](#what-an-invalid-index-costs-and-what-rejects-it)
  - [How to clear an invalid index](#how-to-clear-an-invalid-index)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

All possible outcomes that leave an invalid index, including a failed CREATE INDEX CONCURRENTLY.

Prompt note: the original prompt was filed lowercase (`all possible outcomes that leave an invalid index, including a failed create index concurrently`). Per `MANDATORY Prompt Hygiene`, the user approved a light cleanup before drafting — capitalize the `CREATE INDEX CONCURRENTLY` command and the leading word, and add a closing period — with no change to meaning.

## Answer

In PostgreSQL 12 an index is **invalid** when its `pg_index.indisvalid` flag is
`false`. The planner never uses such an index for query plans, though the
executor still maintains it on writes when `indisready` is true
([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L199-L210),
[execIndexing.c#skip-not-ready](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L330-L332)).

### The five outcomes at a glance

Only a **small, closed set** of operations can persist `indisvalid = false` on
the table, because only a handful of code paths ever write that flag false.
There are exactly five:

1. A **`CREATE INDEX CONCURRENTLY`** that fails, is cancelled, or is interrupted by a crash after its first commit.
2. A **`REINDEX CONCURRENTLY`** operation over one or more indexes that fails, leaving an invalid `_ccnew` (before the swap) or `_ccold` (after it).
3. A **`DROP INDEX CONCURRENTLY`** that fails or is interrupted after it has marked the index invalid.
4. An **incomplete partitioned (parent) index** — created with `ON ONLY`, or built while a partition's matching index is itself invalid.
5. **`pg_upgrade` from PostgreSQL 9.6 or earlier**, which marks every hash index invalid in the new v12 cluster.

Every one of these is a `CONCURRENTLY`/multi-commit operation, a partitioned
metadata operation, or an upgrade step. A plain single-transaction
`CREATE INDEX`, `REINDEX`, or `DROP INDEX` never leaves an invalid index, because
its failure rolls the whole catalog change back.

### What makes an index invalid

The single source of truth is `pg_index.indisvalid`, one of three boolean state
flags on each index row
([pg_index.h#flags](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L40-L43)):

- `indislive` — the index is alive enough for backends to consider touching it
  at all; `RelationGetIndexList` omits a non-live index, and HOT-safety checks
  still consider live indexes even when they are not ready or valid
  ([relcache.c#omit-not-live](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4388-L4395),
  [relcache.c#HOT-safety](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4864-L4869)).
- `indisready` — new tuples are inserted into it on `INSERT`/non-HOT `UPDATE`.
- `indisvalid` — the planner may use it to answer queries.

A new index's initial flags are set by `UpdateIndexRelation` from the
`index_create` call: `isvalid = !concurrent && !invalid` and
`isready = !concurrent`
([index.c#UpdateIndexRelation](../../../../raw/postgres-12/src/backend/catalog/index.c#L990-L996),
[index.c#flag-store](../../../../raw/postgres-12/src/backend/catalog/index.c#L610-L615)).
A normal `CREATE INDEX` is therefore born `(t,t,t)`; the concurrent and
partitioned-invalid forms are born with `indisvalid = false`.

After creation, only these code paths write `indisvalid = false`, and they are
the complete set of "invalid index" producers:

| Path | Operation | Where |
|---|---|---|
| `index_create` with the concurrent flag | `CREATE INDEX CONCURRENTLY` | [index.c:990-996](../../../../raw/postgres-12/src/backend/catalog/index.c#L990-L996) |
| `index_create` with `INDEX_CREATE_INVALID` | partitioned `CREATE INDEX ON ONLY` | [indexcmds.c:988-998](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L988-L998), [index.h:53](../../../../raw/postgres-12/src/include/catalog/index.h#L53) |
| direct `CatalogTupleUpdate` to `indisvalid=false` | partitioned build that attached an invalid child | [indexcmds.c:1243-1265](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1243-L1265) |
| `index_concurrently_swap` flips old `indisvalid=false` | `REINDEX CONCURRENTLY` swap | [index.c:1531-1537](../../../../raw/postgres-12/src/backend/catalog/index.c#L1531-L1537) |
| `index_set_state_flags(INDEX_DROP_CLEAR_VALID)` | `DROP INDEX CONCURRENTLY` | [index.c:3367-3383](../../../../raw/postgres-12/src/backend/catalog/index.c#L3367-L3383) |
| `UPDATE pg_index SET indisvalid=false` for hash AM | `pg_upgrade` from ≤ 9.6 | [version.c:367-376](../../../../raw/postgres-12/src/bin/pg_upgrade/version.c#L367-L376) |

The persistent states these produce are:

| `indislive` | `indisready` | `indisvalid` | Name | Produced by |
|---|---|---|---|---|
| `t` | `f` | `f` | invalid, not ready | CIC failed before set-ready |
| `t` | `t` | `f` | invalid, ready (still maintained) | CIC failed after set-ready; DROP INDEX CONCURRENTLY after clear-valid; a ready `_ccnew`/`_ccold`; `pg_upgrade` hash index; invalid partitioned parent (no storage) |
| `f` | `f` | `f` | dead (invalid and not live) | DROP INDEX CONCURRENTLY / REINDEX CONCURRENTLY after set-dead |

The `indisready = false, indisvalid = true` combination never occurs:
`index_set_state_flags` asserts the ladder live→ready→valid for creation and
the reverse for drops
([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3351-L3396)).

### 1. A failed, cancelled, or crashed CREATE INDEX CONCURRENTLY

This is the canonical case. `CREATE INDEX CONCURRENTLY` (CIC) splits its work
across four transactions: it first creates the catalog row marked
**not-ready and not-valid**, then in later transactions flips `indisready`, then
`indisvalid`
([index.c#concurrent-overview](../../../../raw/postgres-12/src/backend/catalog/index.c#L3114-L3168)).
Because the row only becomes durable at the first commit, **a failure before
commit 1 leaves no index at all** — the transaction rolls back
([indexcmds.c#commit1](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1318-L1320)).
Any failure *after* commit 1 leaves the half-built index behind as **invalid**,
in one of two sub-states depending on whether the build had set `indisready`:

| Failure window | Leftover |
|---|---|
| Wait 1 or the first (build) scan, before set-ready | **invalid, not ready** |
| Wait 2, `validate_index`, or Wait 3, after set-ready | **invalid, ready** |

The flips are written by `index_set_state_flags` with a **non-transactional**
in-place update, so they cannot roll back, and a server crash or `immediate`
shutdown lands on the same set of states — never a half-applied flag flip and
never a valid index missing rows
([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403)).
The documentation describes exactly this leftover and the `\d ... INVALID`
listing
([create_index.sgml#invalid-index](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L574-L606)).
The v12 regression suite stages it: a unique CIC over duplicate data fails in
the build scan and leaves `concur_index3` marked `INVALID`
([create_index.out#concur_index3](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1383-L1417)).

The full mechanism — every failure phase, the build-vs-validate split, lock
release, and the crash/recovery analysis — is on the dedicated page:
[How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 12](create-index-concurrently.md).

### 2. A failed or cancelled REINDEX CONCURRENTLY

`REINDEX CONCURRENTLY` (RIC) can be reached through `INDEX`, `TABLE`, `SCHEMA`,
or `DATABASE` forms in v12; `SYSTEM CONCURRENTLY` is parsed but rejected because
system catalogs cannot be reindexed concurrently
([reindex.sgml#synopsis](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L22-L25),
[indexcmds.c#ReindexMultipleTables](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2525-L2533)).
The supported concurrent forms feed one or more target indexes into
`ReindexRelationConcurrently`, which reuses CIC's build/validate state machine
on a **fresh copy** named `<original>_ccnew` that it creates next to the
original, then swaps in
([indexcmds.c#ReindexIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2333-L2382),
[indexcmds.c#ReindexTable](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2455-L2484),
[indexcmds.c#ReindexMultipleTables](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2672-L2686),
[indexcmds.c#RIC-phases](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2957-L3261)).
An ordinary ERROR, cancel, or timeout therefore leaves an invalid copy, not
necessarily the original
([reindex.sgml#failure-recovery](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L363-L390)):

| Failure point | Invalid leftover |
|---|---|
| Phase 1 (create copies / lock) | none — the phase-1 transaction rolls back, no `_ccnew` persists |
| Phase 2 (build) or phase 3 (validate) | an invalid `_ccnew` (not-ready if it failed in the build, ready after) |
| Phase 4 (swap) before commit | the swap transaction rolls back: `_ccnew` still invalid, original untouched |
| Phase 5 or 6 (after the swap commits) | the renamed `_ccold` old index (invalid, possibly dead) |

The key correctness point is that the **swap is the only step that touches the
original's name or `indisvalid`, and it does both in one transaction**:
`index_concurrently_swap` renames `_ccnew` to the original name and the original
to `_ccold`
([index.c#swap-names](../../../../raw/postgres-12/src/backend/catalog/index.c#L1490-L1492)),
while flipping `new.indisvalid = true` and `old.indisvalid = false`
together with the transactional `CatalogTupleUpdate`
([index.c#index_concurrently_swap](../../../../raw/postgres-12/src/backend/catalog/index.c#L1531-L1537)).
So a healthy `index_name` is **never** left invalid by a RIC failure; the invalid
leftover is always the differently named `_ccnew` or `_ccold`. The sole exception
is an index that was **already invalid before** RIC ran (for example, left by a
failed CIC), which the suite demonstrates by leaving **both**
`concur_reindex_ind5` and `concur_reindex_ind5_ccnew` `INVALID`
([create_index.out#both-invalid](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2317-L2333)).

The six phases, five waits, and per-phase ordinary failure table are on the
dedicated page:
[How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 12](reindex-index-concurrently.md).
That page keeps RIC's exact crash or `immediate`-shutdown recovered flag state
under [Open Questions](reindex-index-concurrently.md#open-questions) rather than
asserting it here.

### 3. A failed or interrupted DROP INDEX CONCURRENTLY

`DROP INDEX CONCURRENTLY` is "more or less the reverse" of CIC
([index.c#dic-overview](../../../../raw/postgres-12/src/backend/catalog/index.c#L2058-L2067))
and also commits several times, so an interruption can leave the index invalid
even though you were trying to remove it. The sequence inside `index_drop`
(concurrent branch) is
([index.c#index_drop](../../../../raw/postgres-12/src/backend/catalog/index.c#L2089-L2192)):

1. `index_set_state_flags(INDEX_DROP_CLEAR_VALID)` — set `indisvalid = false`
   (keeping `indisready = true` so in-flight scans still see correct contents),
   then **commit** ([index.c#clear-valid-call](../../../../raw/postgres-12/src/backend/catalog/index.c#L2109-L2112)).
2. `WaitForLockers(AccessExclusiveLock)`.
3. `index_concurrently_set_dead` → `index_set_state_flags(INDEX_DROP_SET_DEAD)` —
   clear `indisready` and `indislive`, then **commit**
   ([index.c#set-dead](../../../../raw/postgres-12/src/backend/catalog/index.c#L1719-L1761),
   [index.c#DROP_SET_DEAD](../../../../raw/postgres-12/src/backend/catalog/index.c#L3384-L3396)).
4. `WaitForLockers(AccessExclusiveLock)` again, then the physical delete.

A deadlock, cancel, `lock_timeout`, statement error, or crash **after step 1's
commit but before the physical delete** leaves the index present and invalid:

- after step 1, before step 3 → **invalid, ready** (`t,t,f`);
- after step 3, before the delete → **dead** (`f,f,f`), which
  `RelationGetIndexList` then omits from every index list so nothing touches it
  ([relcache.c#omit-not-live](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4388-L4395)).

The clear-valid step is deliberately written to be **retryable**: it does not
assert the index's starting flags, "since we want to be able to retry a
`DROP INDEX CONCURRENTLY` that failed partway through"
([index.c#INDEX_DROP_CLEAR_VALID](../../../../raw/postgres-12/src/backend/catalog/index.c#L3367-L3383)).
So the fix for a stuck `DROP INDEX CONCURRENTLY` is simply to run it again. (A
plain, non-concurrent `DROP INDEX` cannot produce this: it deletes the index in
one `AccessExclusiveLock` transaction that either succeeds or rolls back.)

### 4. An incomplete partitioned index

An index on a **partitioned table** is a metadata-only parent that has no storage
of its own; the real indexes live on the partitions. The parent's
`indisvalid` tracks whether **every partition already has a matching valid
index**. Two operations can leave the parent invalid:

- **`CREATE INDEX ON ONLY <partitioned_table>`** when the table already has
  partitions. `DefineIndex` sets `INDEX_CREATE_INVALID` precisely in this case —
  "recursion was declined but partitions exist"
  ([indexcmds.c#partitioned-invalid](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L988-L998)).
  The docs state it plainly: with `ONLY`, "no recursion is done, and the index is
  marked invalid"
  ([create_index.sgml#partitioned-only](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L671-L689)).
- **A recursing `CREATE INDEX` that attaches a pre-existing child index that is
  itself invalid.** `DefineIndex` notices the attached child is invalid and marks
  the parent invalid to match
  ([indexcmds.c#invalidate-parent](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1163-L1164),
  [indexcmds.c#parent-set-invalid](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1243-L1265)).

The parent flips to valid only when `validatePartitionedIndex` counts a valid
matching index on **every** partition; until then it stays invalid
([tablecmds.c#validatePartitionedIndex](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16682-L16769)).
That validation is driven by `ALTER INDEX ... ATTACH PARTITION`
([tablecmds.c#attach-validate](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16636-L16643)),
and it recurses upward so a multi-level partition hierarchy becomes valid in one
chain once the last leaf is attached
([tablecmds.c#validate-recurse](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16744-L16768)).

The regression suite shows the full lifecycle: `CREATE INDEX ON ONLY` on two
levels yields "two invalid indexes" (`indisvalid = f`), attaching an *invalid*
child does not validate the parent, and attaching a *valid* child finally flips
the whole chain valid
([indexing.out#partitioned-invalid](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L404-L439)).
A single-level `ON ONLY` build likewise lists the parent as `INVALID` in `\d`
([indexing.out#only-invalid](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L256-L277)).

This case differs from the others: the planner already ignores **all**
partitioned indexes regardless of validity
([plancat.c#skip-partitioned](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L212-L219)),
so an invalid parent does not change query plans directly. What it signals is an
**incomplete rollout** — not every partition is covered yet — and the
`ATTACH PARTITION` validation is the normal way it resolves, not an error to
repair.

### 5. pg_upgrade from PostgreSQL 9.6 or earlier

`pg_upgrade` is the one path that produces invalid indexes without any failure at
all. The on-disk format of **hash** indexes changed in PostgreSQL 10, so when the
old cluster is 9.6 or older, `pg_upgrade` runs `old_9_6_invalidate_hash_indexes`
against the **new** (v12) cluster
([check.c#hash-reindex-gate](../../../../raw/postgres-12/src/bin/pg_upgrade/check.c#L218-L220)).
That function executes
`UPDATE pg_catalog.pg_index i SET indisvalid = false ...` for every hash index
and writes a `reindex_hash.sql` script of `REINDEX INDEX` statements
([version.c#old_9_6_invalidate_hash_indexes](../../../../raw/postgres-12/src/bin/pg_upgrade/version.c#L296-L406)).

So immediately after upgrading a ≤ 9.6 cluster to v12, every hash index is
present but invalid (and still `indisready`, so writes still maintain it), and
"until then, none of these indexes will be used." Running the generated
`reindex_hash.sql` rebuilds them and clears the flag.

### Operations that do not leave an invalid index

It is worth stating the negative space, because it is a common worry:

| Operation | On failure |
|---|---|
| `CREATE INDEX` (non-concurrent) | whole transaction rolls back — **no leftover index** |
| `REINDEX` / `REINDEX TABLE` (non-concurrent) | rolls back — the original index is unchanged and stays valid |
| `DROP INDEX` (non-concurrent) | rolls back — the index stays present and valid |
| recursing `CREATE INDEX` on a partitioned table (no `ONLY`, all children valid) | either fully succeeds with a valid parent, or rolls back entirely |

The dividing line is the number of commits. The `CONCURRENTLY` variants and the
partitioned `ON ONLY` metadata path deliberately commit intermediate states so
that ordinary DML keeps running; that is exactly why an interruption can leave a
durable invalid index. Single-transaction DDL has no such window.

### What an invalid index costs, and what rejects it

While an index is invalid:

- **The planner never uses it** for query paths
  ([plancat.c#skip-invalid](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L199-L210)).
- **The executor still maintains it on writes when `indisready`** is true — this
  is the documented "update overhead" of a ready-but-invalid leftover; a
  not-ready leftover is opened but receives no entries
  ([execIndexing.c#skip-not-ready](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L330-L332)).
- **VACUUM still processes it** as long as it is `indisready`, so uniqueness
  checks do not hit dangling pointers
  ([vacuum.c#vac-open-indexes](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1869-L1880)).

Several commands explicitly **reject** an invalid index:

| Command | Behavior on an invalid index | Source |
|---|---|---|
| `CLUSTER ... USING <index>` | error: "cannot cluster on invalid index" | [cluster.c:489-493](../../../../raw/postgres-12/src/backend/commands/cluster.c#L489-L493) |
| `REFRESH MATERIALIZED VIEW CONCURRENTLY` | will not pick an invalid index as the required unique key | [matview.c:862-876](../../../../raw/postgres-12/src/backend/commands/matview.c#L862-L876) |
| `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX` | error: "index is not valid" | [parse_utilcmd.c:2068-2072](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L2068-L2072) |
| `ALTER TABLE ... REPLICA IDENTITY USING INDEX` | error: "cannot use invalid index as replica identity" | [tablecmds.c:13976-13981](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L13976-L13981) |
| bulk `REINDEX (TABLE/SCHEMA/DATABASE) CONCURRENTLY` | skips it with a WARNING | [indexcmds.c:2819-2824](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2819-L2824) |

### How to clear an invalid index

The fix depends on which outcome produced it:

- **CIC / RIC leftover:** `DROP INDEX [CONCURRENTLY] <name>` and retry, or rebuild
  with `REINDEX INDEX [CONCURRENTLY] <name>` — a directly named invalid index may
  be reindexed (that is the repair path), even though bulk REINDEX skips invalid
  ones
  ([create_index.sgml#invalid-index](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L574-L606)).
- **Stuck `DROP INDEX CONCURRENTLY`:** re-run it; the clear-valid step is
  retryable by design
  ([index.c#INDEX_DROP_CLEAR_VALID](../../../../raw/postgres-12/src/backend/catalog/index.c#L3367-L3383)).
- **Invalid partitioned parent:** create matching indexes on the partitions and
  `ALTER INDEX ... ATTACH PARTITION` them; the parent validates automatically when
  all partitions are covered
  ([tablecmds.c#validatePartitionedIndex](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16682-L16769)).
- **`pg_upgrade` hash indexes:** run the generated `reindex_hash.sql`
  ([version.c#reindex-script](../../../../raw/postgres-12/src/bin/pg_upgrade/version.c#L394-L402)).

## Context Reviewed

- `pg_index` flag definitions and creation-time defaults:
  [pg_index.h#flags](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L40-L43),
  [index.c#UpdateIndexRelation](../../../../raw/postgres-12/src/backend/catalog/index.c#L990-L996),
  [index.c#flag-store](../../../../raw/postgres-12/src/backend/catalog/index.c#L610-L615).
- The complete set of `indisvalid` writers, found by scanning the whole `src`
  tree for both direct `indisvalid =` assignments and the `UpdateIndexRelation`
  tuple build (`Anum_pg_index_indisvalid` / `BoolGetDatum(isvalid)`): the
  `false`-writers are
  `index_create`/`UpdateIndexRelation` (born-invalid),
  `index_set_state_flags(INDEX_DROP_CLEAR_VALID)`, `index_concurrently_swap`, the
  partitioned-parent invalidation in `DefineIndex`, and
  `old_9_6_invalidate_hash_indexes`; `validatePartitionedIndex` and the CIC
  set-valid / non-concurrent reindex paths only ever set `true`.
- CIC state machine and failure outcomes:
  [index.c#concurrent-overview](../../../../raw/postgres-12/src/backend/catalog/index.c#L3114-L3168),
  [index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403),
  and the sibling page
  [create-index-concurrently.md](create-index-concurrently.md).
- RIC swap atomicity:
  [index.c#index_concurrently_swap](../../../../raw/postgres-12/src/backend/catalog/index.c#L1531-L1537),
  and the sibling page
  [reindex-index-concurrently.md](reindex-index-concurrently.md).
- DROP INDEX CONCURRENTLY sequence:
  [index.c#index_drop](../../../../raw/postgres-12/src/backend/catalog/index.c#L2089-L2192),
  [index.c#index_concurrently_set_dead](../../../../raw/postgres-12/src/backend/catalog/index.c#L1719-L1761).
- Partitioned-index validity:
  [indexcmds.c#partitioned-recursion](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1040-L1276),
  [tablecmds.c#validatePartitionedIndex](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16682-L16769),
  [indexing.out](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L256-L439).
- `pg_upgrade` hash handling:
  [check.c](../../../../raw/postgres-12/src/bin/pg_upgrade/check.c#L218-L220),
  [version.c](../../../../raw/postgres-12/src/bin/pg_upgrade/version.c#L296-L406).
- Consumers of `indisvalid`: planner, executor, VACUUM, CLUSTER, materialized
  views, constraint creation, replica identity, and `RelationGetIndexList`
  (cited inline above).

## Evidence Map

| Claim | Evidence |
|---|---|
| Invalid means `indisvalid = false`; planner skips it; executor maintains it when ready | [plancat.c:199-210](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L199-L210), [execIndexing.c:330-332](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L330-L332) |
| Initial flags: `isvalid = !concurrent && !invalid`, `isready = !concurrent` | [index.c:990-996](../../../../raw/postgres-12/src/backend/catalog/index.c#L990-L996) |
| The `indisready = false, indisvalid = true` state is impossible (state-flag asserts) | [index.c:3351-3396](../../../../raw/postgres-12/src/backend/catalog/index.c#L3351-L3396) |
| CIC creates not-ready/not-valid, flips ready then valid; failure after commit 1 leaves invalid | [index.c:3114-3168](../../../../raw/postgres-12/src/backend/catalog/index.c#L3114-L3168), [indexcmds.c:1318-1320](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1318-L1320) |
| CIC invalid leftover is shown in regression as `concur_index3 ... INVALID` | [create_index.out:1383-1417](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1383-L1417) |
| RIC can be reached by supported `INDEX`, `TABLE`, `SCHEMA`, and `DATABASE` concurrent forms; `SYSTEM CONCURRENTLY` is rejected | [reindex.sgml:22-25](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L22-L25), [indexcmds.c:2525-2533](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2525-L2533), [indexcmds.c:2672-2686](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2672-L2686) |
| RIC swap flips new-valid/old-invalid in one transactional update; healthy name stays valid | [index.c:1531-1537](../../../../raw/postgres-12/src/backend/catalog/index.c#L1531-L1537) |
| RIC over an already-invalid index leaves both it and `_ccnew` invalid | [create_index.out:2317-2333](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2317-L2333) |
| DROP INDEX CONCURRENTLY marks invalid (clear-valid), then dead (set-dead), across commits | [index.c:2089-2192](../../../../raw/postgres-12/src/backend/catalog/index.c#L2089-L2192), [index.c:3367-3396](../../../../raw/postgres-12/src/backend/catalog/index.c#L3367-L3396) |
| Clear-valid is retryable (no starting-flag assert) | [index.c:3367-3383](../../../../raw/postgres-12/src/backend/catalog/index.c#L3367-L3383) |
| Dead (`indislive=false`) indexes are omitted from index lists | [relcache.c:4388-4395](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4388-L4395) |
| `CREATE INDEX ON ONLY` with partitions sets `INDEX_CREATE_INVALID` | [indexcmds.c:988-998](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L988-L998), [index.h:53](../../../../raw/postgres-12/src/include/catalog/index.h#L53) |
| Docs: `ONLY` marks the partitioned index invalid until all partitions match | [create_index.sgml:671-689](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L671-L689) |
| Attaching an invalid child marks the parent invalid | [indexcmds.c:1163-1164](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1163-L1164), [indexcmds.c:1243-1265](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1243-L1265) |
| Parent becomes valid when every partition has a valid match (recurses upward) | [tablecmds.c:16682-16769](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16682-L16769) |
| Regression: two invalid `ON ONLY` parents validate only when a valid leaf is attached | [indexing.out:404-439](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L404-L439) |
| Planner ignores all partitioned indexes regardless of validity | [plancat.c:212-219](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L212-L219) |
| `pg_upgrade` from ≤ 9.6 marks new-cluster hash indexes invalid + writes reindex script | [check.c:218-220](../../../../raw/postgres-12/src/bin/pg_upgrade/check.c#L218-L220), [version.c:296-406](../../../../raw/postgres-12/src/bin/pg_upgrade/version.c#L296-L406) |
| Invalid indexes rejected by CLUSTER / REFRESH MV CONCURRENTLY / ADD CONSTRAINT USING INDEX / REPLICA IDENTITY / bulk REINDEX CONCURRENTLY | [cluster.c:489-493](../../../../raw/postgres-12/src/backend/commands/cluster.c#L489-L493), [matview.c:862-876](../../../../raw/postgres-12/src/backend/commands/matview.c#L862-L876), [parse_utilcmd.c:2068-2072](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L2068-L2072), [tablecmds.c:13976-13981](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L13976-L13981), [indexcmds.c:2819-2824](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2819-L2824) |
| VACUUM still processes invalid-but-ready indexes | [vacuum.c:1869-1880](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1869-L1880) |

## Open Questions

None for v12 source behavior — the writers of `indisvalid = false` enumerated
above are the complete set in the pinned checkout. A whole-source-tree scan
confirms it, covering both direct `indisvalid =` assignments and the
`UpdateIndexRelation` tuple build (`Anum_pg_index_indisvalid` /
`BoolGetDatum(isvalid)`) for the born-invalid case: the only sites that write the
catalog flag to `false` are the paths in the producers table above; every other
match either sets it `true` (`validatePartitionedIndex`, the CIC set-valid, the
`index_concurrently_swap` new index, and the non-concurrent reindex paths) or is
a non-write read into a local or relcache copy (`describe.c`, `relcache.c`,
`tablecmds.c`). Two scoping notes:

- **Out of scope: manual catalog edits.** A superuser can `UPDATE pg_index SET
  indisvalid = false` directly; that is catalog tampering, not an outcome of a
  normal operation, and is not analyzed here.
- **Out of scope: physical corruption.** A structurally damaged-but-`indisvalid`
  index is a different failure mode (detected by tools such as `amcheck`), not an
  `indisvalid = false` state, and is not covered.
- The CIC crash/`immediate`-shutdown recovery analysis is detailed on
  [create-index-concurrently.md](create-index-concurrently.md): the relevant
  flag updates use `index_set_state_flags`, and `heap_xlog_inplace` physically
  replays a durable in-place tuple update
  ([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403),
  [heapam.c#heap_xlog_inplace](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L8797-L8835)).
  RIC's exact recovered flag state around set-ready, swap, and set-dead remains
  scoped under
  [reindex-index-concurrently.md Open Questions](reindex-index-concurrently.md#open-questions).

## Source References

- [index.c#UpdateIndexRelation](../../../../raw/postgres-12/src/backend/catalog/index.c#L990-L996)
- [index.c#index_concurrently_swap](../../../../raw/postgres-12/src/backend/catalog/index.c#L1447-L1716)
- [index.c#index_concurrently_set_dead](../../../../raw/postgres-12/src/backend/catalog/index.c#L1719-L1761)
- [index.c#index_drop](../../../../raw/postgres-12/src/backend/catalog/index.c#L2007-L2276)
- [index.c#concurrent-overview](../../../../raw/postgres-12/src/backend/catalog/index.c#L3114-L3168)
- [index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403)
- [heapam.c#heap_xlog_inplace](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L8797-L8835)
- [indexcmds.c#partitioned-recursion](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1040-L1276)
- [indexcmds.c#ReindexIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2333-L2382)
- [indexcmds.c#ReindexTable](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2455-L2484)
- [indexcmds.c#ReindexMultipleTables](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2525-L2705)
- [indexcmds.c#reindex-skip-invalid](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2819-L2824)
- [tablecmds.c#attach-validate](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16636-L16643)
- [tablecmds.c#validatePartitionedIndex](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16682-L16769)
- [tablecmds.c#replica-identity-invalid](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L13976-L13981)
- [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L199-L219)
- [execIndexing.c#skip-not-ready](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L330-L332)
- [relcache.c#RelationGetIndexList](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4385-L4398)
- [vacuum.c#vac_open_indexes](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1869-L1880)
- [cluster.c#invalid-reject](../../../../raw/postgres-12/src/backend/commands/cluster.c#L489-L493)
- [matview.c#unique-index-pick](../../../../raw/postgres-12/src/backend/commands/matview.c#L862-L876)
- [parse_utilcmd.c#constraint-using-index](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L2068-L2072)
- [pg_index.h#flags](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L40-L43)
- [index.h#INDEX_CREATE_INVALID](../../../../raw/postgres-12/src/include/catalog/index.h#L47-L53)
- [reindex.sgml#synopsis](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L22-L25)
- [version.c#old_9_6_invalidate_hash_indexes](../../../../raw/postgres-12/src/bin/pg_upgrade/version.c#L296-L406)
- [check.c#hash-reindex-gate](../../../../raw/postgres-12/src/bin/pg_upgrade/check.c#L218-L220)
- [create_index.sgml#invalid-index](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L574-L606)
- [create_index.sgml#partitioned-only](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L671-L689)
- [create_index.out#cic-invalid](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1383-L1417)
- [create_index.out#ric-both-invalid](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2317-L2358)
- [indexing.out#partitioned-invalid](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L256-L439)

## Navigation

- [How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 12](create-index-concurrently.md)
- [How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 12](reindex-index-concurrently.md)
- [PostgreSQL 12 Codebase Navigation Guide](../../codebase-navigation-guide.md)
- [v12 index](../../index.md)
- [Wiki index](../../../index.md)
