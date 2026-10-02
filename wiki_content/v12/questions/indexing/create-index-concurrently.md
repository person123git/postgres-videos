---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Parser, utility dispatch, and generated catalog artifacts](#parser-utility-dispatch-and-generated-catalog-artifacts)
  - [Concurrent-specific preconditions, restrictions, and early exits](#concurrent-specific-preconditions-restrictions-and-early-exits)
  - [The three pg_index state flags](#the-three-pg_index-state-flags)
  - [Step-by-step implementation](#step-by-step-implementation)
  - [The first build scan's tuple-visibility rule](#the-first-build-scans-tuple-visibility-rule)
  - [Index access-method and contrib boundary](#index-access-method-and-contrib-boundary)
  - [How maintenance_work_mem is used and where increases stop helping](#how-maintenance_work_mem-is-used-and-where-increases-stop-helping)
  - [GUCs that affect CIC performance](#gucs-that-affect-cic-performance)
  - [All steps and locks required on the table](#all-steps-and-locks-required-on-the-table)
  - [How concurrent index builds interact with each other](#how-concurrent-index-builds-interact-with-each-other)
  - [All operations that can block CREATE INDEX CONCURRENTLY](#all-operations-that-can-block-create-index-concurrently)
  - [Is skipping prepared transactions in the writer waits safe?](#is-skipping-prepared-transactions-in-the-writer-waits-safe)
  - [Can walsenders or replication-slot xmin holders appear in the Wait 3 set?](#can-walsenders-or-replication-slot-xmin-holders-appear-in-the-wait-3-set)
  - [Why two scans and three waits](#why-two-scans-and-three-waits)
  - [Failure scenarios and the outcome on the table](#failure-scenarios-and-the-outcome-on-the-table)
  - [Test coverage](#test-coverage)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

give a comprehensive explanation of how create index concurrently is
implemented, add a section with all steps and locks required on the table.

Follow-up (2026-06-10): also add all the possible operations that could block
a `CREATE INDEX CONCURRENTLY`.

Follow-up (2026-06-10): does a running `pg_dump` block it? How about another
open transaction that will not commit for 1 hour? How about a session that is
idle in transaction?

Follow-up (2026-06-12): also add a new section with a comprehensive list of all
failure scenarios and the outcome on the table, like invalid indexes, etc.

Follow-up (2026-07-13): Investigate how `maintenance_work_mem` is used during
`CREATE INDEX CONCURRENTLY`, and at what point increasing it stops improving
the index creation process.

Follow-up (2026-07-17): What GUCs have a performance impact on it?

(The follow-up wording was corrected from "what GUCs have performance impact on
it." for grammar and capitalization at the user's request; meaning preserved.)

## Answer

`CREATE INDEX CONCURRENTLY` (CIC) builds an index without taking a heap-table
lock that blocks ordinary `INSERT`/`UPDATE`/`DELETE`: v12 DML uses
`RowExclusiveLock`, and CIC's `ShareUpdateExclusiveLock` does not conflict with
that lock mode. The concurrent path pays for this with more total work: it uses
**four internal transactions**, performs **two full table scans**, and has
**three deliberate transaction-set waits**
([lockdefs.h#lockmodes](../../../../raw/postgres-12/src/include/storage/lockdefs.h#L36-L46),
[lock.c#LockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L65-L103),
[indexcmds.c#concurrent-phases](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1472)).
Those three waits are not every place the backend can sleep; they are the three
transaction handoff barriers in the CIC state machine. The whole dance keeps
the index correct while concurrent writes continue
([index.c#validate_index-overview](../../../../raw/postgres-12/src/backend/catalog/index.c#L3112-L3174)).

The four-phase orchestration lives in `DefineIndex()`'s concurrent branch. It
creates not-built catalog entries with `INDEX_CREATE_CONCURRENT` and
`INDEX_CREATE_SKIP_BUILD`, then runs the post-commit build, validation, and
mark-valid phases
([indexcmds.c#flags](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L974-L986),
[indexcmds.c#concurrent-phases](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1472)).
Those phases call helpers in `index.c` (`index_create`,
`index_concurrently_build`, `validate_index`, `index_set_state_flags`) and wait
via `WaitForLockers` / `WaitForOlderSnapshots`.

The heap-table lock chosen for a concurrent build is
**`ShareUpdateExclusiveLock`**, both at utility dispatch and inside
`DefineIndex`. Its conflict mask includes another `ShareUpdateExclusiveLock`,
`ShareLock`, `ShareRowExclusiveLock`, `ExclusiveLock`, and
`AccessExclusiveLock`, but not `RowExclusiveLock`. That is why another CIC,
`VACUUM`, `ANALYZE`, plain `CREATE INDEX`, and conflicting DDL must wait while
normal DML can proceed
([utility.c#CIC-dispatch](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1311-L1326),
[indexcmds.c#table-lock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L548-L564),
[lock.c#SUE-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L78-L81)).

### Parser, utility dispatch, and generated catalog artifacts

The grammar turns `CREATE [UNIQUE] INDEX [CONCURRENTLY]` into an `IndexStmt` and
sets its `concurrent` boolean from `opt_concurrently`; `IndexStmt` also carries
the relation, access method, keys, included columns, predicate, uniqueness, and
`IF NOT EXISTS` state
([gram.y#IndexStmt](../../../../raw/postgres-12/src/backend/parser/gram.y#L7333-L7407),
[parsenodes.h#IndexStmt](../../../../raw/postgres-12/src/include/nodes/parsenodes.h#L2738-L2775)).
The parser build compiles `gram.o`; its makefile makes `gram.c` the Bison target
with `-d` and makes `gram.h` depend on that generated C output
([parser/Makefile#generated-grammar](../../../../raw/postgres-12/src/backend/parser/Makefile#L15-L54)).

`ProcessUtilitySlow` fires any `ddl_command_start` event trigger before dispatch.
Its `T_IndexStmt` arm then rejects an explicit transaction block, resolves and
locks the target relation once, transforms expression/predicate syntax, and
calls `DefineIndex`. After `DefineIndex` returns, utility code collects the
command, closes its ALTER-style command collection, and later fires
`ddl_command_end` before the outer command transaction commits
([utility.c#DDL-start](../../../../raw/postgres-12/src/backend/tcop/utility.c#L960-L975),
[utility.c#IndexStmt-dispatch](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1301-L1393),
[utility.c#DDL-end](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1701-L1713)).
That caller boundary matters for both blocking and the late-failure outcome
described below.

The three persistent state booleans are catalog schema, not private
`DefineIndex` fields. `pg_index.h` is an input to PostgreSQL's catalog generator,
includes the generated `pg_index_d.h`, and declares the catalog OID and columns
([pg_index.h#catalog-input](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L12-L29),
[pg_index.h#state-flags](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L40-L43)).
The catalog makefile includes `pg_index.h` in `CATALOG_HEADERS`, derives every
`*_d.h` name, and runs `genbki.pl`; that script emits the per-catalog definition
headers used by compiled code
([catalog/Makefile#generated-headers](../../../../raw/postgres-12/src/backend/catalog/Makefile#L28-L57),
[catalog/Makefile#genbki](../../../../raw/postgres-12/src/backend/catalog/Makefile#L71-L99),
[genbki.pl#definition-headers](../../../../raw/postgres-12/src/backend/catalog/genbki.pl#L368-L398)).
There is no separate generated CIC state machine: generated parser/catalog
artifacts expose the `IndexStmt` boolean and `pg_index` identities, while the C
code implements the transitions.

### Concurrent-specific preconditions, restrictions, and early exits

These are the concurrent-specific cases. The ordinary `CREATE INDEX` ownership,
relation-kind, access-method, operator-class, option, expression, and predicate
checks in `DefineIndex` still apply
([indexcmds.c#DefineIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L429-L1288)).

| Restriction or early exit | Where enforced |
|---|---|
| Cannot run inside a transaction block (`BEGIN; ... COMMIT;`) | `PreventInTransactionBlock(isTopLevel, "CREATE INDEX CONCURRENTLY")` ([utility.c:1307-1309](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1307-L1309)) |
| Temporary tables use a non-concurrent build, but only after the utility-level transaction-block check; therefore the `CONCURRENTLY` spelling on a temp table inside `BEGIN` is still rejected | [indexcmds.c#temp-fallback](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L489-L499), [create_index.sql#temp-ordering](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L504-L525) |
| `IF NOT EXISTS` with an already-used relation name returns an invalid OID and exits `DefineIndex` before the four-phase branch | [index.c#IF-NOT-EXISTS](../../../../raw/postgres-12/src/backend/catalog/index.c#L844-L859), [indexcmds.c#early-return](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1025-L1034) |
| Partitioned tables cannot be built concurrently | [indexcmds.c#partitioned-error](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L604-L616) |
| System catalog tables cannot be indexed concurrently | [index.c#system-catalog](../../../../raw/postgres-12/src/backend/catalog/index.c#L813-L817) |
| Exclusion constraints cannot be built concurrently | [index.c#exclusion](../../../../raw/postgres-12/src/backend/catalog/index.c#L823-L826) |

The four-transaction description therefore applies only when the request
reaches the real concurrent branch. The transaction-block ban is structural:
the implementation must commit its own phases, which it cannot do inside a
user-opened transaction
([indexcmds.c#phase-commits](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1435)).

### The three pg_index state flags

CIC is driven by three boolean flags on the index's `pg_index` row. The catalog
declares them as "valid for queries", "ready for inserts", and "alive at all";
the initial row is written by `UpdateIndexRelation`
([pg_index.h#flags](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L40-L43),
[index.c#UpdateIndexRelation](../../../../raw/postgres-12/src/backend/catalog/index.c#L612-L615)):

- `indislive` — backends may touch the index at all. `RelationGetIndexList`
  omits indexes where this is false, which keeps them out of searching,
  insertion, and HOT-safety decisions; CIC sets this `true` from the start so
  new transactions examine the index for HOT-safety even before it is ready for
  inserts
  ([relcache.c#RelationGetIndexList-live](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4388-L4395),
  [relcache.c#HOT-safety-live-indexes](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4861-L4870)).
- `indisready` — new tuples (from `INSERT` and non-HOT `UPDATE`) should be
  inserted into the index. `BuildIndexInfo` copies it into
  `ii_ReadyForInserts`, and `ExecInsertIndexTuples` skips indexes where that
  flag is false
  ([index.c#BuildIndexInfo-ready](../../../../raw/postgres-12/src/backend/catalog/index.c#L2337-L2339),
  [execIndexing.c#ready-for-inserts](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L328-L332)).
- `indisvalid` — the planner may use the index to answer queries; `plancat.c`
  ignores invalid indexes for planner paths while noting that the executor can
  still insert into invalid indexes if `indisready` is true
  ([plancat.c#invalid-index-skip](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L199-L210)).

A normal non-concurrent, non-invalid `CREATE INDEX` is born with all three
`true`. CIC instead creates the catalog row with `indisvalid = false` and
`indisready = false`
(`!concurrent && !invalid` and `!concurrent` respectively at
[index.c:990-996](../../../../raw/postgres-12/src/backend/catalog/index.c#L990-L996)),
then flips `indisready`, and finally `indisvalid`, at carefully chosen points.
The transitions are applied by `index_set_state_flags` using a
**non-transactional in-place update** so they cannot roll back
([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403)).

### Step-by-step implementation

The concurrent branch of `DefineIndex` runs as four transactions. The first
three boundaries are the explicit `CommitTransactionCommand()` /
`StartTransactionCommand()` pairs inside `DefineIndex`; the fourth transaction
returns to the normal command-end commit path after `DefineIndex` returns
([indexcmds.c#concurrent-phases](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1472),
[postgres.c#finish_xact_command](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2569-L2578)).

**Transaction 1 — create the catalog entry (no build).** `index_create` makes
the `pg_index`/`pg_class` rows with `INDEX_CREATE_CONCURRENT` and
`INDEX_CREATE_SKIP_BUILD`, so the index has a catalog identity but is not built
yet, and is marked not-ready/not-valid
([indexcmds.c#flags](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L974-L986),
[indexcmds.c#index_create-call](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1005-L1014),
[index.c#index_create-skip-build](../../../../raw/postgres-12/src/backend/catalog/index.c#L1198-L1222)).
Before committing, CIC takes a **session-level** `ShareUpdateExclusiveLock` on
the table so it survives across the upcoming commits and nobody can drop the
table or index
([indexcmds.c#session-lock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1320)).
The commit makes the cataloged-but-unbuilt index visible, so future transactions
include it in HOT-safety decisions and cannot make new incompatible HOT chains
for this index
([indexcmds.c#catalog-visible-hot-safety](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1295-L1304),
[indexcmds.c#post-wait1-hot-safety](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1348-L1363)).

**Wait 1**, then **Transaction 2 — first scan, build the index.** CIC waits for
every transaction that could still have the table open without the new index in
its list, using `WaitForLockers(heaplocktag, ShareLock, true)`
([indexcmds.c#wait1](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1328-L1346)).
It then takes a fresh snapshot and calls `index_concurrently_build`, which scans
the heap, builds the index, and sets `indisready = true`
([indexcmds.c#build](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1366-L1370),
[index.c#index_concurrently_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L1399-L1439)).
This scan indexes only tuples valid as of the scan's snapshot; rows written by
still-running or later transactions are handled differently (see below). The
following commit makes the `indisready` update visible, so new writers start
maintaining the index.

**Wait 2**, then **Transaction 3 — second scan, validate.** CIC waits again with
`WaitForLockers(..., ShareLock, ...)` until no transaction can still have the
table open with the index marked read-only for updates
([indexcmds.c#wait2](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1382-L1389)).
It registers a **reference snapshot**, then calls `validate_index`
([indexcmds.c#validate](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1391-L1412)).
`validate_index` collects all TIDs already in the index (via an
`index_bulk_delete` callback that only records, never deletes), sorts them, then
scans the heap and "merge-joins" against that sorted TID list, inserting any
tuple that is visible to the reference snapshot but missing from the index
([index.c#validate_index](../../../../raw/postgres-12/src/backend/catalog/index.c#L3176-L3298)).
Before committing, CIC saves the reference snapshot's `xmin` as `limitXmin` and
**drops the snapshot** — deliberately, to avoid deadlocking against other CIC
runs that would otherwise wait on it
([indexcmds.c#drop-snapshot](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1414-L1424)).

**Wait 3**, then **Transaction 4 — mark valid.** In a fresh transaction (so no
snapshot is held), CIC calls `WaitForOlderSnapshots(limitXmin, true)`. That
helper gathers same-database VXIDs whose advertised `xmin` is at or before the
saved `limitXmin` and waits for them, excluding autovacuum/lazy-VACUUM backends;
those are the transactions that could have snapshots old enough to expect rows
the index does not contain
([indexcmds.c#wait3](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1437-L1448),
[indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L307-L402),
[procarray.c#GetCurrentVirtualXIDs](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2471-L2540)).
Then it sets `indisvalid = true`, sends a relcache invalidation on the parent
table so cached plans get re-planned to use the new index, and releases the
session lock
([indexcmds.c#set-valid](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1450-L1472)).
This last transaction's commit happens when the surrounding utility command
finishes
([postgres.c#finish_xact_command](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2569-L2578)).

The canonical narrative of why this ordering is correct is in the
`validate_index` header comment
([index.c#validate_index-overview](../../../../raw/postgres-12/src/backend/catalog/index.c#L3112-L3174))
and the user docs
([ref/create_index.sgml#concurrent-narrative](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L545-L572)).

### The first build scan's tuple-visibility rule

The first scan (Transaction 2) feeds the index-build path **only heap tuples
visible to one fresh MVCC snapshot taken at the start of that transaction**,
after Wait 1, before any partial-index predicate or AM-specific callback
filtering
([indexcmds.c#build-snapshot](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1358-L1370),
[snapshot.h#SNAPSHOT_MVCC](../../../../raw/postgres-12/src/include/utils/snapshot.h#L37-L50),
[heapam_handler.c#mvcc-branch](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1595-L1665)).
It does *not* run the `SnapshotAny` / `HeapTupleSatisfiesVacuum` time-qual
logic a normal `CREATE INDEX` uses to add tuples merely because they are
`HEAPTUPLE_RECENTLY_DEAD`. That rule lives in the heap table AM, not in
`DefineIndex`; the steps below trace it from the concurrent flag down to the
per-tuple visibility test.

**Where the choice is made.** `index_concurrently_build` rebuilds the
`IndexInfo`, sets `ii_Concurrent = true`, then calls `index_build`
([index.c#ii_Concurrent](../../../../raw/postgres-12/src/backend/catalog/index.c#L1421-L1427)).
`index_build` calls the access method's `ambuild`
([index.c#ambuild-call](../../../../raw/postgres-12/src/backend/catalog/index.c#L2902-L2903)).
For hash, GiST, SP-GiST, GIN, BRIN, and serial B-tree builds, the `ambuild`
path calls `table_index_build_scan` directly — B-tree
([nbtsort.c#build-scan](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L487-L494)),
hash ([hash.c:166](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L166)),
GiST ([gistbuild.c:196](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L196)),
SP-GiST ([spginsert.c:126](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L126)),
GIN ([gininsert.c:382](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L382)),
and BRIN ([brin.c:723](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L723)).
Only B-tree has parallel build support in v12; when B-tree runs parallel, worker
processes copy the shared concurrent flag into `ii_Concurrent`, join the
parallel heap scan, and then call `table_index_build_scan` with that scan
descriptor
([index.c#btree-parallel-only](../../../../raw/postgres-12/src/backend/catalog/index.c#L2844-L2854),
[nbtsort.c#parallel-worker-scan](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1779-L1786)).
So the visibility rule is AM-independent: it is decided in the heap AM and
inherited by every core index type built concurrently. `table_index_build_scan`
dispatches to the heap AM's `heapam_index_build_range_scan` and always passes
`anyvisible = false`
([tableam.h#table_index_build_scan](../../../../raw/postgres-12/src/include/access/tableam.h#L1512-L1533),
[heapam_handler.c#tableam-routine](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2644)).

**The MVCC-vs-`SnapshotAny` fork.** Inside `heapam_index_build_range_scan`,
`ii_Concurrent` picks the snapshot. `OldestXmin` is left invalid for a
concurrent build because the `GetOldestXmin` call is guarded by
`!indexInfo->ii_Concurrent`; a non-concurrent build instead computes
`OldestXmin` and scans with `SnapshotAny`
([heapam_handler.c#snapshot-choice](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1212-L1223)).
With `OldestXmin` invalid, the non-parallel scan case registers a regular MVCC
transaction snapshot (`RegisterSnapshot(GetTransactionSnapshot())`) and begins
the scan with it via `table_beginscan_strat`
([heapam_handler.c#mvcc-snapshot](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1233-L1246)).
This is the transaction-2 MVCC snapshot `DefineIndex` set up for: just before
calling the build it pushes a fresh `GetTransactionSnapshot()` and comments that
it will "build the index using all tuples that are visible in this snapshot"
([indexcmds.c#build-snapshot](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1358-L1370)).
For a parallel B-tree CIC build, `_bt_begin_parallel` chooses an MVCC snapshot
when `isconcurrent` is true and initializes the parallel table scan with it;
`heapam_index_build_range_scan` then uses the snapshot carried by that parallel
heap scan rather than registering its own
([nbtsort.c#parallel-build-snapshot](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1360-L1427),
[heapam_handler.c#parallel-snapshot](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1248-L1260)).

**What "visible to the snapshot" means, line by line.** The scan calls
`heap_getnext`, which in page-at-a-time mode filters each page in `heapgetpage`:
every normal line pointer is passed to `HeapTupleSatisfiesVisibility`, and only
tuples that pass are recorded in `rs_vistuples`
([heapam.c#heapgetpage](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L444-L453)).
For an MVCC snapshot, `HeapTupleSatisfiesVisibility` dispatches to
`HeapTupleSatisfiesMVCC`
([heapam_visibility.c#dispatch](../../../../raw/postgres-12/src/backend/access/heap/heapam_visibility.c#L1690-L1696)).
So by the time a tuple reaches the build loop, its MVCC visibility is already
decided. The build loop reflects that: because `snapshot != SnapshotAny`, it
takes the `else` branch — "heap_getnext did the time qual check" — marks the
tuple alive, counts it, and (after any partial-index predicate) hands it to the
AM callback
([heapam_handler.c#mvcc-branch](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1595-L1665)).

**What the concurrent scan therefore skips.** The entire
`switch (HeapTupleSatisfiesVacuum(...))` time-qual block runs only on the
`SnapshotAny` path and is never entered for a concurrent build
([heapam_handler.c#vacuum-switch](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1364-L1388)).
Two consequences follow directly:

- **No `SnapshotAny` recently-dead inclusion.** A normal build indexes
  `HEAPTUPLE_RECENTLY_DEAD` tuples to preserve MVCC semantics for old
  snapshots; the concurrent build cannot reach that case, so it does not add a
  tuple merely because the `HeapTupleSatisfiesVacuum` state is
  `HEAPTUPLE_RECENTLY_DEAD`
  ([heapam_handler.c#recently-dead](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1402-L1428)).
  A tuple that is visible to the build MVCC snapshot can still be indexed even
  if another transaction deletes it while the scan is running; the eligibility
  rule is snapshot visibility, not current vacuum status
  ([snapshot.h#SNAPSHOT_MVCC](../../../../raw/postgres-12/src/include/utils/snapshot.h#L37-L50),
  [heapam_visibility.c#HeapTupleSatisfiesMVCC](../../../../raw/postgres-12/src/backend/access/heap/heapam_visibility.c#L940-L963)).
  CIC compensates with Wait 3, which waits out every transaction old enough to
  have needed those omitted rows before it sets `indisvalid`.
- **No `ii_BrokenHotChain` from the scan.** `ii_BrokenHotChain` is set only
  inside that `SnapshotAny` switch
  ([heapam_handler.c#broken-hot](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1364-L1588)),
  so a concurrent build never flags a broken HOT chain during the first scan,
  and `index_build` accordingly skips the `indcheckxmin` write for concurrent
  builds
  ([index.c#concurrent-indcheckxmin](../../../../raw/postgres-12/src/backend/catalog/index.c#L2939-L2952)).

**Why MVCC and not `HeapTupleSatisfiesVacuum`.** The `validate_index` header
gives the reason this page previously only summarized: using
`HeapTupleSatisfiesVacuum` could make two versions of the same
concurrently-updated row both look valid, producing a bogus unique-index
failure; one MVCC snapshot sees exactly one version
([index.c#validate_index-why-mvcc](../../../../raw/postgres-12/src/backend/catalog/index.c#L3124-L3132)).
The price is that the first scan "does not contain any tuples added to the
table while we built the index," which is exactly why CIC then sets
`indisready`, waits again, and runs the second `validate_index` scan to
backfill the rest
([index.c#validate_index-second-scan](../../../../raw/postgres-12/src/backend/catalog/index.c#L3134-L3168)).

### Index access-method and contrib boundary

Core code owns the catalogs, snapshots, locks, and state transitions, but an
index access method (AM) owns the index's physical contents. `index_build`
dispatches the first build through `rd_indam->ambuild`. During validation,
`validate_index` calls `index_bulk_delete`, which dispatches to the AM's
`ambulkdelete` callback to enumerate existing TIDs, and the heap validation scan
calls `index_insert`, which dispatches each missing tuple to `aminsert`
([index.c#ambuild-dispatch](../../../../raw/postgres-12/src/backend/catalog/index.c#L2899-L2904),
[index.c#validation-AM-calls](../../../../raw/postgres-12/src/backend/catalog/index.c#L3228-L3280),
[indexam.c#index_insert](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L165-L189),
[indexam.c#index_bulk_delete](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L672-L693),
[heapam_handler.c#validation-insert](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1873-L1934)).

`IndexAmRoutine` therefore requires `ambuild`, `ambuildempty`, `aminsert`, and
`ambulkdelete`; the AM documentation requires `ambuild` to fill a new index and
says it ordinarily uses `table_index_build_scan`, while every AM must handle
concurrent index updates correctly
([amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L160-L229),
[indexam.sgml#ambuild](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L232-L265),
[indexam.sgml#index-locking](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L891-L911)).
The first-scan trace above is exact for the six core AMs because all six call the
heap table-AM helper. A third-party AM can implement `ambuild` differently, so
its internal scan, waiting, and crash-durability behavior cannot be established
from core source alone.

The in-tree contrib `bloom` extension demonstrates that boundary. Its SQL
registers an index AM, and `blbuild` uses `table_index_build_scan`; it writes its
metapage and built pages through shared buffers with `GenericXLog` full-page
images
([bloom--1.0.sql#access-method](../../../../raw/postgres-12/contrib/bloom/bloom--1.0.sql#L8-L13),
[blinsert.c#blbuild](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L44-L159),
[blutils.c#BloomInitMetapage](../../../../raw/postgres-12/contrib/bloom/blutils.c#L445-L470),
[generic_xlog.c#GenericXLogFinish](../../../../raw/postgres-12/src/backend/access/transam/generic_xlog.c#L263-L435)).
It participates in the same core CIC phases, but its own callbacks remain
extension code.

### How maintenance_work_mem is used and where increases stop helping

There is **no universal `maintenance_work_mem` value at which CIC stops getting
faster**. PostgreSQL 12 can use the setting during two separate, sequential
phases of a concurrent build:

1. the access-method-specific first build in transaction 2, if that AM reads
   the setting; and
2. the common serial TID sort in transaction 3's validation. GIN first invokes
   forced pending-list cleanup in that phase; it selects the same GUC but
   allocates cleanup state only if a pending list exists.

An increase helps only while it changes an AM-specific threshold or algorithm,
reduces an external sort's runs or temporary I/O, or allows another useful
parallel B-tree worker. Once those effects stop changing, more memory cannot
remove CIC's two heap scans, index-page construction, or transaction waits
([index.c#index_concurrently_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L1399-L1438),
[index.c#validate_index-sort](../../../../raw/postgres-12/src/backend/catalog/index.c#L3228-L3283),
[ginvacuum.c#ginbulkdelete-cleanup](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L583-L594),
[ginfast.c#cleanup-memory-selection](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L807-L840),
[indexcmds.c#concurrent-phases](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1472)).

**Setting and application scope.** In v12, `maintenance_work_mem` is a
`PGC_USERSET` integer measured in kilobytes. Its default is 64 MB and its allowed
range starts at 1 MB. It can be changed for a session or transaction and needs
neither a reload nor a restart
([guc.c#maintenance_work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2243-L2252),
[config.sgml#maintenance_work_mem](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1686-L1712)).
For one CIC run, a regular session `SET` is the practical choice: its value
persists across CIC's internal commits. `SET LOCAL` lasts only for its current
transaction, has no effect when issued outside a transaction block, and cannot
enclose CIC because CIC is rejected inside an explicit transaction block
([ref/set.sgml#SET-scope](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L33-L115),
[utility.c#CIC-transaction-block](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1305-L1309)).
Parallel workers receive the launching backend's serialized GUC state, so a
session value also reaches a parallel B-tree build
([parallel.c#serialize-GUC-state](../../../../raw/postgres-12/src/backend/access/transam/parallel.c#L349-L352),
[parallel.c#restore-GUC-state](../../../../raw/postgres-12/src/backend/access/transam/parallel.c#L1349-L1361)).
The value is a working limit or threshold, not memory reserved in advance: for
example, tuplesort charges allocations against its allowed bytes as input
arrives, while GIN checks a growing accumulator after each heap tuple
([tuplesort.c#sort-memory-initialization](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L700-L762),
[gininsert.c#GIN-build-threshold](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L245-L314)).

A high value is not free. The v12 docs warn that setting it above genuinely
available memory can make the machine swap and slow the build. Different
sessions can each run a maintenance operation, and when autovacuum runs, up to
`autovacuum_max_workers` workers can each allocate this memory; each such worker
uses `maintenance_work_mem` only while its `autovacuum_work_mem` stays at the
default `-1`
([ref/create_index.sgml#memory-warning](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L707-L713),
[config.sgml#maintenance-memory-concurrency](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1693-L1712),
[config.sgml#autovacuum_work_mem](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1716-L1731)).
That autovacuum multiplication warning applies when a shared/default value is
raised. A session-only CIC setting affects the current session and its parallel
workers, not separate autovacuum sessions or unrelated client sessions
([ref/set.sgml#SET-session](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L33-L56),
[parallel.c#serialize-GUC-state](../../../../raw/postgres-12/src/backend/access/transam/parallel.c#L349-L352)).

**Where the memory-sensitive phases occur.** The first-build memory state and
the validation sort do not coexist. Inside `index_concurrently_build`,
`index_build` completes the AM's first build before the function marks the index
`indisready` and returns. CIC commits that phase, completes the next writer wait,
and only then lets `validate_index` create, consume, and destroy a separate
tuplesort
([index.c#index_concurrently_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L1399-L1438),
[indexcmds.c#build-to-validation](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1366-L1412),
[index.c#validate_index-sort](../../../../raw/postgres-12/src/backend/catalog/index.c#L3245-L3283)).
The validation sort encodes every TID reported by the AM's `ambulkdelete`
callback as an `int8`, sorts those values, and merge-scans them against the heap.
It receives the full `maintenance_work_mem` value and is serial. BRIN's
`ambulkdelete` reports no TIDs, so the sort exists but is empty for that AM
([index.c#validate_index-sort](../../../../raw/postgres-12/src/backend/catalog/index.c#L3228-L3283),
[heapam_handler.c#validation-merge](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1705-L1947),
[brin.c#brinbulkdelete](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L766-L784)).

**B-tree first build and parallelism.** A serial B-tree build gives its primary
index-tuple sort the full setting
([nbtsort.c#primary-sort](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L378-L445)).
A serial unique build also creates a dead-tuple sort using `work_mem`, not
`maintenance_work_mem`; a parallel participant caps that secondary sort at the
smaller of its primary-sort share and `work_mem`. In CIC's MVCC build scan, the
heap AM first filters tuples by snapshot visibility; every tuple that then
reaches the B-tree callback is marked alive, so no dead tuple enters that spool.
A serial unique CIC build therefore discards it as unnecessary; parallel
participants still have to finalize their empty secondary sorts
([nbtsort.c#secondary-sort](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L447-L520),
[nbtsort.c#parallel-secondary-sort](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1739-L1768),
[heapam_handler.c#concurrent-tuples-are-alive](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1595-L1665),
[nbtsort.c#build-callback](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L592-L619),
[nbtsort.c#parallel-empty-secondary-sort](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1788-L1797)).

B-tree is the only v12 AM that can parallelize the first build. CIC supports
that parallel build, but its validation scan remains serial
([index.c#index-build-workers](../../../../raw/postgres-12/src/backend/catalog/index.c#L2844-L2868),
[ref/create_index.sgml#CIC-parallel-scope](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L766-L771)).
For automatic worker choice, the planner requires a budget share of at least
32 MB for every sort participant, counting the leader. The memory cap
therefore permits zero workers below 64 MB, one at 64 MB, and two at 96 MB;
each additional worker requires another 32 MB. Parallel safety can reduce the
request to zero. The generic size model starts at
`min_parallel_table_scan_size` (8 MB by default) and increases its request as
the estimated table size crosses successive threefold thresholds; the worker
pool can still launch fewer processes than were requested
([planner.c#worker-prerequisites](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6257-L6343),
[planner.c#memory-worker-cap](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6344-L6362),
[allpaths.c#compute_parallel_worker](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L3563-L3653),
[guc.c#min_parallel_table_scan_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3119-L3127),
[config.sgml#parallel-maintenance-worker-availability](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2283-L2303)).
`max_parallel_maintenance_workers` caps the request and defaults to two. It is
`PGC_USERSET`, so session or transaction changes need neither reload nor restart;
as with `maintenance_work_mem`, session scope is the practical per-CIC scope
([guc.c#max_parallel_maintenance_workers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2997-L3004),
[utility.c#CIC-transaction-block](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1305-L1309)).
With that default two-worker cap, 96 MB is the last automatic
memory-based worker-count threshold, but only when the size and safety checks
request two workers and the worker pool launches them. It is not the overall
memory plateau because the B-tree build sort or the validation sort can still
spill above that value
([planner.c#memory-worker-cap](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6344-L6362),
[tuplesort.c#spill-transition](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1641-L1700)).
An explicit table `parallel_workers` value bypasses the memory-based worker cap,
though not `max_parallel_maintenance_workers`
([planner.c#parallel_workers-override](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6317-L6329),
[ref/create_index.sgml#parallel_workers-override](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L744-L753)).

Requested and launched workers are different quantities. In the normal build,
the leader participates as a worker; only a source build with
`DISABLE_LEADER_PARTICIPATION` avoids that role. Each launched background worker
then divides the budget by the planned count (requested workers plus the
leader). The leader's worker-role sort divides by the actual count (launched
workers plus the leader), so only that share grows when some requested workers
do not launch. If DSM setup fails or no worker launches, the code abandons
parallel state and uses the serial full-budget path
([nbtsort.c#parallel-setup-and-fallback](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1328-L1485),
[nbtsort.c#BTLeader-participants](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L177-L205),
[nbtsort.c#leader-participant-share](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1595-L1605),
[nbtsort.c#worker-share](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1693-L1696)).

The later coordinator sort receives the full setting and consumes significant
memory only after participants have released most of their sort memory. This
makes `maintenance_work_mem` the intended primary-sort budget for the parallel
build, not an exact cap on every command allocation: a unique build has separate
secondary sorts, tuplesort floors every passed share at 64 kB, and DSM plus
non-tuplesort allocations sit outside `Tuplesortstate.allowedMem`
([nbtsort.c#parallel-memory-lifetimes](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L421-L485),
[nbtsort.c#participant-memory-release](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1788-L1819),
[tuplesort.c#worker-memory-release](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L4462-L4490),
[tuplesort.c#minimum-sort-budget](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L733-L740),
[config.sgml#parallel-utility-memory](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2306-L2316)).

In that normal leader-participating path, every primary-sort scan participant,
including the leader's worker-role sort, must emit one tape run even when its
partial input fits in memory. The
coordinator takes over one run per actual participant. For a unique CIC, each
participant also finalizes an empty secondary run, but the coordinator destroys
that secondary spool because the scan found no dead tuples and does not merge
those runs. Required participant output can therefore keep parallel-build
temporary-file activity nonzero after all partial inputs fit their shares
([nbtsort.c#BTLeader-participants](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L177-L205),
[nbtsort.c#discard-empty-secondary-spool](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L514-L520),
[tuplesort.c#parallel-participant-run](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1802-L1833),
[tuplesort.c#leader-takes-participant-runs](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L4510-L4561)).

**First-build behavior by index AM.** The common validation sort above follows
every first build, but the first build itself uses the setting differently:

| Index AM | First-build use of `maintenance_work_mem` | Where that AM-specific gain plateaus |
|---|---|---|
| B-tree | Sorts full index tuples. Serial gets the full budget; parallel scan participants divide it, followed by the leader merge ([nbtsort.c#primary-sort](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L378-L445), [nbtsort.c#parallel-worker-sort](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1693-L1768)). | When more memory neither adds a useful worker nor reduces initial runs/merge work; the separate validation TID sort must be checked too ([tuplesort.c#spill-and-merge](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1641-L1700), [tuplesort.c#performsort](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1786-L1866)). |
| Hash | For a CIC that remains truly concurrent (temporary-table requests have already fallen back), computes the block-valued threshold `min((maintenance_work_mem * 1024) / BLCKSZ, NBuffers)`. It pre-sorts by target bucket when the estimated bucket count reaches that threshold; the same routine uses `NLocBuffer` for a temporary, non-concurrent fallback. If sorting is selected, its tuplesort gets the full setting ([indexcmds.c#temp-fallback](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L489-L499), [hash.c#hashbuild-sort-choice](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L126-L177), [hashsort.c#_h_spoolinit](../../../../raw/postgres-12/src/backend/access/hash/hashsort.c#L54-L90)). | Raising memory can first make the estimated bucket count fall below that code-level proxy and avoid pre-sorting; this is not a measurement of available RAM. The path-choice threshold stops rising when the `NBuffers` cap wins. If sorting remains selected, more memory can still reduce its external runs and merges ([hash.c#hashbuild-sort-rationale](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L132-L159), [tuplesort.c#spill-and-merge](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1641-L1700)). |
| GiST | With `buffering=on`, after collecting enough tuple-size statistics, or with `auto`, after the index outgrows `effective_cache_size`, uses the setting together with `effective_cache_size` to choose the buffered build's `levelStep`; insufficient memory disables buffering and falls back to plain inserts. `buffering=off` bypasses this path ([gistbuild.c#buffering-option](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L126-L151), [gistbuild.c#gistInitBuffering](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L312-L417), [gistbuild.c#buffering-switch](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L508-L526)). | With buffering off, or before `on`/`auto` has switched, there is no first-build gain. After a switch, when `effective_cache_size`, rather than maintenance memory, limits the next `levelStep`, more `maintenance_work_mem` does not improve this decision. The buffer hash table is outside the calculation, so this is not a strict total-memory cap. Buffered GiST also uses a temporary file and can cost extra CPU; the docs say ordered input can be faster with buffering off, so its elapsed-time response need not be monotonic ([gistbuild.c#buffer-memory-boundary](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L345-L399), [gistbuildbuffers.c#temporary-buffer-file](../../../../raw/postgres-12/src/backend/access/gist/gistbuildbuffers.c#L48-L62), [gist.sgml#buffering-build](../../../../raw/postgres-12/doc/src/sgml/gist.sgml#L962-L993)). |
| GIN | Accumulates key/posting-list entries in an in-memory red-black tree. After processing each heap tuple, it dumps the accumulator if tracked allocation has reached the setting; one final dump handles what remains. Because the check is after a whole tuple, this is a soft flush threshold, not a hard cap ([gininsert.c#GIN-build-threshold](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L245-L314), [gininsert.c#GIN-final-dump](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L359-L400), [ginbulk.c#BuildAccumulator](../../../../raw/postgres-12/src/backend/access/gin/ginbulk.c#L108-L140)). | Larger memory can mean fewer accumulator dumps. That gain ends when the build reaches one final dump, or when fewer dumps no longer dominate. Validation has the separate, conditional pending-list use described below. |
| SP-GiST | Its first build inserts tuples directly with a per-tuple temporary context; it does not read this setting ([spginsert.c#spgbuild](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L71-L149)). | No first-build gain from this GUC. Its `ambulkdelete` visits live leaf TIDs, so its ordinary CIC validation TID sort can still benefit ([spgvacuum.c#validation-callback](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L147-L168), [spgvacuum.c#spgbulkdelete](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L893-L916)). |
| BRIN | Its first build summarizes heap page ranges directly and does not read this setting ([brin.c#brinbuild](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L658-L743)). | No first-build or validation-sort gain: BRIN has no per-heap-tuple index tuples, and its `ambulkdelete` does not call the TID callback, so the common validation tuplesort is empty. The second heap scan still runs and can call `brininsert` for visible tuples missing from the index snapshot ([brin.c#brinbulkdelete](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L766-L784), [heapam_handler.c#BRIN-validation-heap-scan](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1768-L1934), [brin.c#brininsert](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L131-L328)). |
| contrib Bloom | Keeps one cached index page plus a per-tuple context and does not read this setting during its first build ([blinsert.c#blbuild](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L35-L159)). | No first-build gain from this GUC. Its `ambulkdelete` reports every stored tuple, so its ordinary CIC validation TID sort can still benefit ([blvacuum.c#blbulkdelete](../../../../raw/postgres-12/contrib/bloom/blvacuum.c#L26-L107), [index.c#validate_index_callback](../../../../raw/postgres-12/src/backend/catalog/index.c#L3228-L3312)). |

During CIC validation, GIN's `ambulkdelete` invokes forced pending-list cleanup.
The normal CIC backend selects `maintenance_work_mem`, but an empty list returns
before allocating the cleanup accumulator. For a nonempty list, `full_clean`
makes it continue until the list is empty; it flushes at end-of-list or when a
full-row boundary finds tracked allocation at the threshold, then resets the
accumulator between batches. Its cleanup-specific gain therefore plateaus when
the list is empty or fits in one batch, subject to concurrent fast-update
inserts changing that input
([ginvacuum.c#ginbulkdelete-cleanup](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L563-L594),
[ginfast.c#empty-pending-list](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L807-L840),
[ginfast.c#cleanup-batching](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L843-L1009),
[gininsert.c#fast-update-inserts](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L484-L529)).

GIN also has an extreme error boundary: if one in-memory posting list has already
grown beyond `INT_MAX` slots and needs to grow again, either the initial-build or
validation-cleanup accumulator raises
`ERRCODE_PROGRAM_LIMIT_EXCEEDED` with the hint to reduce
`maintenance_work_mem`. A larger setting is therefore not unconditionally safer
for a pathological single-key accumulator
([ginbulk.c#posting-list-limit](../../../../raw/postgres-12/src/backend/access/gin/ginbulk.c#L28-L51),
[ginfast.c#cleanup-accumulator](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L859-L904)).

Third-party AM behavior is not fixed by the AM API. `ambuild` receives the heap,
index, and `IndexInfo`, but no memory argument. The in-tree AMs that use this GUC
read the exported global declared in `miscadmin.h`; extension AMs can choose a
different policy. Core's validation tuplesort still belongs to `validate_index`
([amapi.h#ambuild_function](../../../../raw/postgres-12/src/include/access/amapi.h#L58-L65),
[miscadmin.h#maintenance_work_mem](../../../../raw/postgres-12/src/include/miscadmin.h#L243-L247),
[index.c#ambuild-dispatch](../../../../raw/postgres-12/src/backend/catalog/index.c#L2899-L2904)).
The budget itself is a handwritten global. The B-tree-only parallel-build gate
compares the AM OID with `BTREE_AM_OID`, which catalog generation derives from
`pg_am.dat` into `pg_am_d.h`
([index.c#B-tree-parallel-gate](../../../../raw/postgres-12/src/backend/catalog/index.c#L2844-L2854),
[pg_am.dat#btree](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L20),
[catalog/Makefile#generated-catalog-headers](../../../../raw/postgres-12/src/backend/catalog/Makefile#L32-L69)).

**What “enough memory” means for either tuplesort.** A serial tuplesort keeps
accepting tuples in memory until input ends or its memory checks force tape
mode. If input ends first, it performs one in-memory quicksort. Otherwise it
writes sorted runs to temporary tapes and merges them; extra memory can make
runs larger, increase merge fan-in, and provide larger sequential-read buffers
([tuplesort.c#algorithm](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1-L75),
[tuplesort.c#spill-transition](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1641-L1700),
[tuplesort.c#performsort](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1786-L1866),
[tuplesort.c#merge-memory](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L2639-L2668)).
Once a **serial** sort's complete input fits, a further increase does not change
that sort's one-quicksort path. It can still affect another CIC phase or the
parallel worker choice.

There is no reliable conversion from index size to that fit point. B-tree input
width and comparison support vary, while hash has a separate path-selection
threshold; the validation sort holds encoded TIDs and its input cardinality
depends on the AM and index predicate. GIN, for example, invokes the validation
callback for every item pointer in its per-key posting lists, so one heap row
represented under several GIN keys contributes repeated TIDs; BRIN contributes
none
([tuplesort.c#SortTuple-model](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L138-L175),
[index.c#encoded-TIDs](../../../../raw/postgres-12/src/backend/catalog/index.c#L3239-L3248),
[ginvacuum.c#posting-list-callback](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L47-L83),
[gin/README#index-structure](../../../../raw/postgres-12/src/backend/access/gin/README#L17-L26),
[brin.c#brinbulkdelete](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L766-L784)).
That is why a fixed rule such as “set it to the index size” is not supported by
v12 source.

**How to find the practical plateau.** Keep the data, index definition, and
concurrent workload comparable, then raise the session value in steps and watch
both memory-sensitive phases:

- `pg_stat_progress_create_index.phase` distinguishes `building index`,
  `index validation: sorting tuples`, and the surrounding waits, but it does not
  report sort memory, temporary bytes, or parallel participant counts. The
  building backend must have `track_activities=on`; that GUC defaults to on and
  is `PGC_SUSET`, so a superuser session change needs neither reload nor restart
  ([monitoring.sgml#progress-view-columns](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3488-L3620),
  [monitoring.sgml#create-index-phases](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3651-L3704),
  [pgstat.c#progress-requires-track-activities](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L3192-L3259),
  [guc.c#tracking-GUCs](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1381-L1399)).
- `trace_sort` is `PGC_USERSET`; a session `SET` needs no reload or restart and
  is the practical CIC scope. It identifies internal versus external sorts at
  sort end. Its `finished writing run N` and merge-step messages are more useful
  for a parallel build: one initial primary run per participant is mandatory,
  while multiple runs or participant merge steps demonstrate spill beyond that
  participant's share. V12 enables the compile-time trace support by default
  ([guc.c#trace_sort](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1635-L1645),
  [tuplesort.c#sort-end-report](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1225-L1279),
  [tuplesort.c#run-trace](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L2924-L3022),
  [tuplesort.c#merge-trace](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L2837-L2841),
  [pg_config_manual.h#TRACE_SORT](../../../../raw/postgres-12/src/include/pg_config_manual.h#L316-L320)).
- `log_temp_files` is `PGC_SUSET`; a superuser session `SET` needs no reload or
  restart and is the practical CIC scope. It logs final temporary-file size at
  deletion. `pg_stat_database.temp_files` and `temp_bytes` count final file size
  when `track_counts=on`; that GUC defaults to on, and a `PGC_SUSET` session
  change needs neither reload nor restart. These figures are
  temporary-space volume, not cumulative reads, writes, merge passes, or wait
  time. They include all database temporary files, and buffered GiST creates its
  own same-command temporary file, so even an otherwise isolated CIC delta is
  not necessarily tuplesort spill
  ([guc.c#log_temp_files](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3153-L3162),
  [config.sgml#log_temp_files](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6555-L6574),
  [fd.c#ReportTemporaryFileUsage](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1272-L1287),
  [pgstat.c#temp-file-accounting](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L1560-L1576),
  [pgstat.c#temp-byte-counter](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6397-L6412),
  [guc.c#tracking-GUCs](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1381-L1399),
  [gistbuildbuffers.c#temporary-buffer-file](../../../../raw/postgres-12/src/backend/access/gist/gistbuildbuffers.c#L48-L62)).

Sort tracing covers only tuplesort-backed work. It does not expose GiST's
`levelStep` memory decision or GIN accumulator batches. GiST emits `DEBUG1` when
buffering cannot start or does start; for GiST and GIN, controlled elapsed-time
comparisons remain necessary
([gistbuild.c#buffering-decision-log](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L390-L417),
[gininsert.c#GIN-build-flush](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L290-L311),
[ginfast.c#GIN-cleanup-flush](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L898-L995)).

Stop increasing when the automatic B-tree request and actual participant count
are stable, every serial tuplesort is internal, each primary parallel
participant produces only its required output run without a merge step,
temporary-space volume no longer shrinks, and controlled phase and total elapsed
times no longer improve. Stop earlier if the host begins swapping. Even then,
CIC still reads the table twice, invokes the AM's validation enumeration, writes
the completed index, and waits for writers and old snapshots. For B-tree, that
enumeration scans every index page and calls the callback for each leaf item;
BRIN's enumeration is a no-op, but its second heap scan remains.
`maintenance_work_mem` cannot remove those fixed costs
([ref/create_index.sgml#memory-and-parallelism](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L707-L741),
[index.c#validate_index-overview](../../../../raw/postgres-12/src/backend/catalog/index.c#L3112-L3283),
[nbtree.c#btvacuumscan](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L848-L1041),
[nbtree.c#validation-callback](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1197-L1270),
[brin.c#brinbulkdelete](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L766-L784)).

The only direct `CREATE INDEX` regression case found by a whole-checkout test
input search that changes `maintenance_work_mem` lowers it to 1 MB to force the
**non-concurrent hash** tuplesort path and checks correctness. A separate
`CLUSTER` regression block also sets 1 MB for a `CLUSTER` operation whose
implementation later rebuilds the relation's indexes, so the broader claim that
only one index-rebuilding test changes it would be false.
The direct CIC regression and isolation blocks do not vary this setting or
parallel-maintenance settings. V12 therefore has no direct CIC performance,
spill, worker-threshold, or plateau test
([create_index.sql#hash-tuplesort](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L379-L387),
[cluster.sql#maintenance_work_mem](../../../../raw/postgres-12/src/test/regress/sql/cluster.sql#L207-L225),
[cluster.c#rebuild-indexes](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1374-L1410),
[create_index.sql#CIC-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L460-L525),
[index_including.sql#CIC](../../../../raw/postgres-12/src/test/regress/sql/index_including.sql#L161-L168),
[index_including_gist.sql#CIC](../../../../raw/postgres-12/src/test/regress/sql/index_including_gist.sql#L37-L44),
[multiple-cic.spec](../../../../raw/postgres-12/src/test/isolation/specs/multiple-cic.spec#L1-L40)).

### GUCs that affect CIC performance

For a typical PostgreSQL 12 B-tree CIC, examine `maintenance_work_mem`,
`max_parallel_maintenance_workers`, `min_parallel_table_scan_size`,
`max_parallel_workers`, and `max_worker_processes` first. The first setting
controls the build and validation memory paths. The other four determine
whether the first heap scan requests parallel workers and whether those workers
can launch. B-tree is the only v12 access method with a parallel build path
([index.c#B-tree-parallel-boundary](../../../../raw/postgres-12/src/backend/catalog/index.c#L2844-L2854),
[planner.c#plan_create_index_workers](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6226-L6362)).

This section uses a bounded meaning of “performance impact”: a setting must
change a core CIC phase, a shipped access method, worker availability, heap or
temporary I/O, index placement, WAL/commit latency, or a command wait. A
third-party access method owns its `ambuild` callback and can read additional
GUCs, so the core source cannot provide a closed list for extension code
([amapi.h#ambuild_function](../../../../raw/postgres-12/src/include/access/amapi.h#L58-L65),
[index.c#ambuild-dispatch](../../../../raw/postgres-12/src/backend/catalog/index.c#L2899-L2904)).

**Application scope used below.** “Session” means a `PGC_USERSET` setting, or a
`PGC_SUSET` setting changed by a superuser, with no reload or restart. Although
those contexts can also be transaction-local, a session value is the usable
per-run scope: CIC cannot run inside an explicit transaction, and each internal
commit ends a `SET LOCAL` value. Parallel workers restore the launching
backend's serialized GUC state
([ref/set.sgml#SET-scope](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L33-L115),
[utility.c#CIC-transaction-block](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1301-L1321),
[parallel.c#serialize-GUC-state](../../../../raw/postgres-12/src/backend/access/transam/parallel.c#L349-L352),
[parallel.c#restore-GUC-state](../../../../raw/postgres-12/src/backend/access/transam/parallel.c#L1349-L1361)).

**Build, scan, and storage settings.**

| GUC | Exact CIC effect and boundary | Default and application |
|---|---|---|
| `maintenance_work_mem` | The main direct control. Transaction 2 passes through the AM's build algorithm; transaction 3 uses the setting for the serial encoded-TID validation sort. The automatic B-tree worker request also reserves at least 32 MB per participant, including the leader. See [How maintenance_work_mem is used and where increases stop helping](#how-maintenance_work_mem-is-used-and-where-increases-stop-helping) ([index.c#index_concurrently_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L1399-L1438), [index.c#validation-sort](../../../../raw/postgres-12/src/backend/catalog/index.c#L3228-L3283), [planner.c#memory-worker-cap](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6344-L6356)). | 64 MB, with a 1 MB minimum; session; no reload or restart ([guc.c#maintenance_work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2243-L2252)). |
| `max_parallel_maintenance_workers` | Caps the B-tree workers requested for the first build. Zero disables parallel maintenance workers. It is a request cap, not a guarantee that workers launch ([planner.c#worker-request-cap](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6257-L6356)). | 2; session; no reload or restart ([guc.c#max_parallel_maintenance_workers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2997-L3005)). |
| `min_parallel_table_scan_size` | The automatic model rejects a heap below this threshold, then adds workers as heap size crosses successive threefold thresholds. A table `parallel_workers` reloption bypasses both this size model and the 32 MB request test, but remains capped by `max_parallel_maintenance_workers` ([allpaths.c#compute_parallel_worker](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L3562-L3653), [planner.c#parallel_workers-override](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6317-L6329)). | 8 MB; session; no reload or restart ([guc.c#parallel-scan-thresholds](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3119-L3139)). |
| `max_parallel_workers`; `max_worker_processes` | The first caps active parallel workers when CIC registers them. The second sizes the shared background-worker slot array. Pool pressure can launch fewer workers than requested; B-tree then continues with the workers that launched or falls back to a serial build ([bgworker.c#worker-slot-pool](../../../../raw/postgres-12/src/backend/postmaster/bgworker.c#L138-L173), [bgworker.c#parallel-and-slot-caps](../../../../raw/postgres-12/src/backend/postmaster/bgworker.c#L931-L1005), [nbtsort.c#parallel-fallback](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1396-L1485)). | Both default to 8. `max_parallel_workers` is session-scoped; `max_worker_processes` is `postmaster` context and needs restart ([guc.c#max_worker_processes](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2788-L2797), [guc.c#max_parallel_workers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3018-L3026)). |
| `effective_cache_size` | Only GiST's buffered build reads it. Together with `maintenance_work_mem`, it limits the buffered subtree depth; it does not reserve cache or control the other shipped AM build algorithms ([gistbuild.c#gistInitBuffering](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L311-L417)). | 524,288 blocks, normally 4 GB at 8 kB per block; session; no reload or restart ([cost.h#DEFAULT_EFFECTIVE_CACHE_SIZE](../../../../raw/postgres-12/src/include/optimizer/cost.h#L21-L32), [guc.c#effective_cache_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3117)). |
| `shared_buffers` | Its `NBuffers` value changes two direct decisions. A heap scan gets a nominal 256 kB bulk-read ring, capped at `NBuffers / 8`, only when the heap exceeds `NBuffers / 4`; a permanent hash-index build also caps its sort-selection threshold at `NBuffers`. Raising shared buffers can therefore move either threshold and is not a monotonic CIC speed control ([heapam.c#bulk-and-sync-threshold](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L296), [freelist.c#BAS_BULKREAD](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L537-L587), [hash.c#hashbuild-sort-choice](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L132-L159)). | The compiled boot default is 1,024 blocks, normally 8 MB; `postmaster` context; restart ([guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2162)). |
| `synchronize_seqscans` | On a sufficiently large heap, the first scan can start at another synchronized scan's location and wrap around; it still reads every page. B-tree, hash, GiST, SP-GiST, and Bloom permit this. GIN and BRIN require physical order and disable it. Validation always disables it ([heapam.c#syncscan-choice](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L267-L296), [gininsert.c#no-syncscan](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L378-L384), [brin.c#physical-order](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L719-L724), [heapam_handler.c#validation-order](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1751-L1763)). | On; session; no reload or restart ([guc.c#synchronize_seqscans](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1732-L1740)). |
| `temp_tablespaces`; `temp_file_limit` | `temp_tablespaces` places serial tuplesort spills, parallel B-tree worker tapes, and GiST buffered-build files. `temp_file_limit` does not throttle CIC: each process errors when its accounted temporary files cross the limit. A build-phase error can leave an invalid, not-ready index; a validation-phase error can leave an invalid, ready index ([tuplesort.c#PrepareTempTablespaces](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L2468-L2475), [sharedfileset.c#parallel-temp-tablespaces](../../../../raw/postgres-12/src/backend/storage/file/sharedfileset.c#L36-L68), [gistbuildbuffers.c#temporary-buffer-file](../../../../raw/postgres-12/src/backend/access/gist/gistbuildbuffers.c#L44-L62), [fd.c#temp-file-limit](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1933-L1958), [indexcmds.c#build-and-validation-phases](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1328-L1453)). | `temp_tablespaces` defaults to the database default tablespace and is session-scoped. `temp_file_limit` defaults to unlimited (`-1`), is `PGC_SUSET`, and is session-scoped for a superuser; neither needs reload or restart ([guc.c#temp_file_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2270-L2278), [guc.c#temp_tablespaces](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3646-L3655)). |
| `default_tablespace` | If `CREATE INDEX` omits `TABLESPACE`, this setting selects the new index's tablespace. It changes where index pages are written, not the CIC state machine; an explicit `TABLESPACE` overrides it ([indexcmds.c#tablespace-selection](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L658-L675), [ref/create_index.sgml#tablespace](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L335-L344)). | Empty string, meaning the database default; session; no reload or restart ([guc.c#default_tablespace](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3635-L3644)). |
| `backend_flush_after` | When a CIC backend or worker must flush dirty shared-buffer victims, this setting controls when it schedules writeback advice. It can affect shared-buffer pressure from hash, GiST, GIN, SP-GiST, BRIN, Bloom, and validation inserts. B-tree's transaction-2 bulk output is written outside shared buffers, so this mechanism does not govern that output path ([buf_init.c#BackendWritebackContext](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L146-L152), [bufmgr.c#backend-writeback](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1088-L1156), [nbtsort.c#direct-build-sync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307)). | 0, disabling the advice; session; no reload or restart ([guc.c#backend_flush_after](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2777-L2786), [pg_config_manual.h#writeback-defaults](../../../../raw/postgres-12/src/include/pg_config_manual.h#L147-L163)). |
| Writer-side `gin_pending_list_limit`; `work_mem` | Neither sizes transaction 2's initial GIN build. After `indisready` commits, concurrent writers using GIN fast update can append to the pending list. Their `gin_pending_list_limit`, unless an index reloption overrides it, decides when regular cleanup starts; regular cleanup uses the writer's `work_mem`. CIC validation later forces full cleanup with the CIC backend's `maintenance_work_mem`, so writer settings can change how much work transaction 3 inherits ([gin_private.h#pending-list-limit](../../../../raw/postgres-12/src/include/access/gin_private.h#L21-L39), [ginfast.c#regular-cleanup-threshold](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L438-L461), [ginfast.c#cleanup-memory-selection](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L807-L828), [ginvacuum.c#validation-cleanup](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L563-L594)). | Both default to 4 MB and are session-scoped with no reload or restart; the relevant values belong to concurrent writer sessions, and the per-index `gin_pending_list_limit` reloption takes precedence ([guc.c#work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2230-L2241), [guc.c#gin_pending_list_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3175-L3184), [ginutil.c#GIN-reloptions](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L602-L628)). |

The AM-specific first-build memory boundaries are detailed in the preceding
section. B-tree sorts index tuples; hash conditionally sorts by bucket; GiST
uses `maintenance_work_mem` with `effective_cache_size`; and GIN bounds its
build accumulator. SP-GiST, BRIN, and contrib Bloom do not read
`maintenance_work_mem` during their first build. Transaction 3 still creates
the common validation sort, although BRIN reports no per-tuple TIDs and leaves
it empty
([nbtsort.c#primary-sort](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L378-L445),
[hash.c#hashbuild-sort-choice](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L132-L177),
[gistbuild.c#buffer-memory-boundary](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L311-L417),
[gininsert.c#build-threshold](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L245-L314),
[spginsert.c#spgbuild](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L71-L149),
[brin.c#brinbuild-and-bulkdelete](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L658-L784),
[blinsert.c#blbuild](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L119-L159)).

PostgreSQL 12 has no heap read-stream layer. Both heap passes use ordinary table
scans; `heapgetpage` advances through buffers, and validation explicitly starts
at block zero. `effective_io_concurrency` drives bitmap-heap prefetch and an
index-deletion horizon helper, but CIC's sequential passes call neither path and
its validation callback never deletes an index TID. It is therefore not a
direct v12 CIC control
([heapam_handler.c#build-scan](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1212-L1247),
[heapam_handler.c#validation-scan](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1751-L1772),
[heapam.c#sequential-next-block](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L702-L766),
[nodeBitmapHeapscan.c#effective_io_concurrency](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L797-L817),
[heapam.c#deletion-horizon-prefetch](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L6970-L7040),
[index.c#validation-callback](../../../../raw/postgres-12/src/backend/catalog/index.c#L3300-L3312)).

**WAL, checkpoints, and the four transactions.** A permanent CIC creates WAL.
B-tree writes transaction-2 pages outside shared buffers, emits forced page
images when `XLogIsNeeded()` is true, and immediately syncs the completed
permanent index file. GiST, GIN, and SP-GiST log completed page ranges; hash and
BRIN use their buffered WAL paths; contrib Bloom uses shared-buffer
`GenericXLog`
([nbtsort.c#build-WAL-and-sync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L576-L662),
[nbtsort.c#immediate-sync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307),
[gistbuild.c#build-WAL](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L217-L226),
[gininsert.c#build-WAL](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L408-L417),
[spginsert.c#build-WAL](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L134-L143),
[hashpage.c#hash-build-WAL](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L346-L402),
[brin.c#build-WAL](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L683-L709),
[blinsert.c#Bloom-build](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L44-L159)).

| GUC | Exact CIC effect and boundary | Default and application |
|---|---|---|
| `synchronous_commit`; `synchronous_standby_names` | CIC has four phase transactions. Transaction 1 inserts the index's catalog rows and therefore has an XID-bearing WAL commit. The later in-tree core phases can write WAL without assigning an XID: build statistics and state flags use in-place updates, while validation writes index pages. For CIC phases without a forced commit or pending relation deletion, `RecordTransactionCommit`'s normal synchronous flush and its synchronous-replication wait require both WAL and an assigned XID; xidless WAL takes the asynchronous path even with `synchronous_commit = on`. B-tree still performs its separate data-file sync before transaction 2 returns. These settings change qualifying commit confirmation, not scan or sort work ([index.c#transaction-1-catalog-inserts](../../../../raw/postgres-12/src/backend/catalog/index.c#L950-L996), [index.c#pg_index-insert](../../../../raw/postgres-12/src/backend/catalog/index.c#L593-L639), [index.c#xidless-build-stats](../../../../raw/postgres-12/src/backend/catalog/index.c#L2676-L2805), [index.c#xidless-state-updates](../../../../raw/postgres-12/src/backend/catalog/index.c#L3314-L3403), [xact.c#xidless-and-sync-commit](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1206-L1426), [syncrep.c#SyncRepWaitForLSN](../../../../raw/postgres-12/src/backend/replication/syncrep.c#L131-L182)). | `synchronous_commit` defaults to `on`; session; no reload or restart. `synchronous_standby_names` defaults empty; `sighup` context; reload ([guc.c#synchronous_commit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4353-L4361), [guc.c#synchronous_standby_names](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4086-L4095)). |
| `wal_compression` | Forced and ordinary full-page images can be compressed, trading CPU for fewer WAL bytes when pages compress well. B-tree's build records use forced images, so their presence does not depend on `full_page_writes` ([xloginsert.c#full-page-compression](../../../../raw/postgres-12/src/backend/access/transam/xloginsert.c#L539-L630), [xloginsert.c#forced-page-image](../../../../raw/postgres-12/src/backend/access/transam/xloginsert.c#L971-L995)). | Off; `PGC_SUSET`; session for a superuser; no reload or restart ([guc.c#wal_compression](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1187-L1195)). |
| `wal_level` | B-tree explicitly logs its privately built pages only when `XLogIsNeeded()` is true. At `minimal`, it skips those page records and relies on the final file sync. This is a restart-level cluster architecture choice, not a practical per-run CIC setting; `minimal` cannot support WAL archiving or streaming replication ([xlog.h#XLogIsNeeded](../../../../raw/postgres-12/src/include/access/xlog.h#L177-L181), [nbtsort.c#build-WAL](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L576-L580), [nbtsort.c#immediate-sync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307), [config.sgml#wal_level](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2446-L2479)). | `replica`; `postmaster` context; restart ([guc.c#wal_level](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4409-L4417)). |
| `wal_buffers`; `wal_sync_method` | These are generic WAL-path controls: the first sizes shared WAL buffering for CIC's WAL stream; the second selects how WAL is forced to disk. Neither changes worker count or scan shape ([guc.c#wal_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2602-L2611), [guc.c#wal_sync_method](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4438-L4447)). | `wal_buffers` defaults to `-1` (automatic), is `postmaster` context, and needs restart. `wal_sync_method` uses the platform default, is `sighup` context, and needs reload. |
| `max_wal_size`; `checkpoint_timeout`; `checkpoint_completion_target`; `checkpoint_flush_after` | The first two influence automatic checkpoint frequency; the latter two pace checkpoint writes and writeback. They can change concurrent background I/O and the full-page-image pattern of ordinary buffered modifications during the command. B-tree's private build performs its final immediate relation sync regardless of checkpoint timing ([guc.c#checkpoint-size-time-flush](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2542-L2600), [guc.c#checkpoint_completion_target](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3413-L3421), [xloginsert.c#full-page-image-decision](../../../../raw/postgres-12/src/backend/access/transam/xloginsert.c#L539-L561), [nbtsort.c#immediate-sync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307)). | Normally 1 GB, 5 minutes, `0.5`, and 32 blocks on systems with `sync_file_range` (otherwise 0); all are `sighup` context and need reload, not restart ([pg_config_manual.h#writeback-defaults](../../../../raw/postgres-12/src/include/pg_config_manual.h#L147-L163)). |
| `commit_delay`; `commit_siblings` | When enabled and enough other transactions are active, the WAL flush path deliberately sleeps before group commit. It can improve aggregate throughput while adding latency to an affected XID-bearing CIC commit; xidless phase commits do not enter the synchronous flush path, and defaults add no delay ([xlog.c#group-commit-delay](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2891-L2915), [xact.c#xidless-commit](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1228-L1272)). | `commit_delay = 0`; `PGC_SUSET`, superuser session. `commit_siblings = 5`; session. Neither needs reload or restart ([guc.c#commit-delay](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2667-L2688)). |

Disabling `fsync` or `full_page_writes` is not a safe production CIC tuning
method. Both are `sighup` settings and need reload. `fsync = off` also makes
B-tree's final `pg_fsync` call a no-op, while `REGBUF_FORCE_IMAGE` makes its
build page images independent of `full_page_writes`
([guc.c#fsync](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1122-L1133),
[guc.c#full_page_writes](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1163-L1175),
[fd.c#pg_fsync](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L329-L355),
[xloginsert.c#forced-page-image](../../../../raw/postgres-12/src/backend/access/transam/xloginsert.c#L539-L545)).

**Wait and cancellation settings.** These settings do not make either heap scan
faster. They bound or expose the initial table lock and CIC's three deliberate
transaction-set waits:

| GUC | CIC behavior | Default and application |
|---|---|---|
| `statement_timeout` | Covers the client statement across all internal commits, scans, and three waits. CIC calls `StartTransactionCommand` directly, so it does not restart the statement timer; the normal command-end path disables it. Expiry cancels the command and is an end-to-end cap, not a per-phase budget ([postgres.c#statement-timeout-lifetime](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2546-L2578), [postgres.c#enable_statement_timeout](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4680-L4716)). | 0 (disabled); session; no reload or restart ([guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2385)). |
| `lock_timeout` | Applies to the initial table-lock acquisition and to each individual VXID lock used by both writer waits and `WaitForOlderSnapshots`. It restarts for each lock acquisition, so it is not an aggregate limit for a wait phase, blocker set, or whole command ([utility.c#initial-table-lock](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1311-L1326), [lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L850-L934), [indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L339-L402), [lock.c#VirtualXactLock](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L4361-L4458), [proc.c#lock-timeout-timer](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1233-L1264)). | 0 (disabled); session; no reload or restart ([guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2396)). |
| `deadlock_timeout`; `log_lock_waits` | The first controls when a blocked lock acquisition runs deadlock detection; lowering it does not end a non-deadlocked wait and can run checks more often. The second logs waits that survive that interval. They are detection and observability controls, not throughput controls ([proc.c#deadlock-and-lock-timeouts](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1229-L1298), [proc.c#long-wait-logging](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1377-L1469)). | 1 second and off; both are `PGC_SUSET`, so a superuser can use session scope with no reload or restart ([guc.c#deadlock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2062-L2072), [guc.c#log_lock_waits](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1489-L1497)). |
| Blocker-side `idle_in_transaction_session_timeout` | It does not fire in the actively running CIC backend. In another session it can terminate an idle-in-transaction writer or old-snapshot holder that blocks CIC; that is blocker policy, not a scan-speed setting ([postgres.c#idle-in-transaction-timer](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4126-L4152), [postgres.c#idle-timer-stop](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4203-L4210)). | 0 (disabled); session in the blocker; no reload or restart ([guc.c#idle_in_transaction_session_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2399-L2407)). |

PostgreSQL 12 has no `transaction_timeout` GUC, so there is no per-internal-
transaction timeout counterpart to the end-to-end `statement_timeout`. It also
has no `maintenance_io_concurrency`, `io_combine_limit`,
`track_wal_io_timing`, or `wal_skip_threshold`; those names have no definitions
in the v12 GUC registry, and the heap-scan path above has no read-stream
interface
([guc.c#timeout-GUCs](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2407),
[guc.c#I/O-GUCs](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2759-L2786),
[guc.c#I/O-timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1381-L1408),
[heapam_handler.c#table-scan-interface](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1212-L1247)).

A timeout or cancellation after transaction 1 commits can leave the new index
behind. Before `SET_READY` it is invalid and not ready; from `SET_READY` until
`SET_VALID` it is invalid and ready; after the non-transactional `SET_VALID`, a
late command-end error can leave it valid. Timeouts are therefore completion
policy, not free acceleration
([indexcmds.c#phase-boundaries](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1316-L1453),
[index.c#index-state-transitions](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403),
[utility.c#DDL-command-end](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1701-L1719)).

**Commonly confused settings and practical priority.**

- `min_parallel_index_scan_size` does not participate: CIC's worker planner
  passes `index_pages = -1`, so only `min_parallel_table_scan_size` supplies a
  size threshold. `max_parallel_workers_per_gather` and
  `parallel_leader_participation` govern query `Gather` nodes, not B-tree's
  private maintenance machinery; B-tree hard-codes leader participation unless
  a compile-time test macro disables it. Planner cost GUCs likewise do not
  choose the worker count in this size-based function
  ([planner.c#heap-only-worker-model](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6317-L6356),
  [allpaths.c#index-threshold-guard](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L3591-L3647),
  [guc.c#query-leader-participation](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1857-L1866),
  [nbtsort.c#build-leader-participation](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1326-L1356)).
- The CIC backend's `work_mem`, `autovacuum_work_mem`, `vacuum_cost_*`
  settings, and `temp_buffers` do not size the primary build or the common
  validation sort. Validation uses `maintenance_work_mem`; forced GIN cleanup
  selects that value for a normal CIC backend. A unique B-tree allocates a
  secondary `work_mem` spool, but the concurrent MVCC scan supplies no dead
  tuples and the serial leader discards it empty. `vacuum_delay_point()` returns
  without delaying when `VacuumCostActive` is false. Temporary-table requests
  have already fallen back to non-concurrent index creation
  ([index.c#validation-sort](../../../../raw/postgres-12/src/backend/catalog/index.c#L3228-L3283),
  [ginfast.c#forced-cleanup-memory](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L807-L828),
  [nbtsort.c#secondary-sort](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L447-L520),
  [heapam_handler.c#concurrent-tuples-are-alive](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1595-L1665),
  [vacuum.c#vacuum_delay_point](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1939-L1971),
  [indexcmds.c#temp-fallback](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L489-L499)).
- `track_activities`, `trace_sort`, `log_temp_files`, and `track_counts` expose
  progress or spills rather than changing CIC's correctness algorithm.
  `track_io_timing` adds measurements but can add significant clock-call
  overhead on some systems; it is `PGC_SUSET`, defaults off, and can use
  superuser session scope without reload or restart
  ([pgstat.c#progress-tracking](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L3191-L3259),
  [guc.c#trace_sort](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1635-L1645),
  [fd.c#temp-file-reporting](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1272-L1287),
  [guc.c#I/O-timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1381-L1408),
  [config.sgml#I/O-timing-overhead](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6854-L6870)).

In practice, tune and measure in this order: (1) `maintenance_work_mem`; (2) for
B-tree, the full worker request-and-availability chain; (3) AM-specific GiST or
GIN behavior; (4) heap, index, and temporary I/O on the selected tablespaces;
and (5) WAL, checkpoints, and commit confirmation. Diagnose the three blocker
waits separately, because memory and workers cannot shorten them
([ref/create_index.sgml#memory-and-parallelism](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L707-L771),
[indexcmds.c#CIC-waits](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1328-L1448)).
There is no source-derived universal best combination. The direct CIC
regression and isolation tests check lifecycle and concurrency, not comparative
GUC performance
([create_index.sql#CIC-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L460-L525),
[index_including.sql#CIC](../../../../raw/postgres-12/src/test/regress/sql/index_including.sql#L161-L168),
[index_including_gist.sql#CIC](../../../../raw/postgres-12/src/test/regress/sql/index_including_gist.sql#L37-L44),
[multiple-cic.spec](../../../../raw/postgres-12/src/test/isolation/specs/multiple-cic.spec#L1-L40)).
At the build boundary, v12 compiles the GUC registry directly in `guc.c`; its
makefile lists `guc.o` and the generated `guc-file.c` scanner only as that
object's dependency
([utils/misc/Makefile#guc](../../../../raw/postgres-12/src/backend/utils/misc/Makefile#L17-L33)).

### All steps and locks required on the table

Two distinct lock layers act on the **heap table**:

1. A **transaction-level** `ShareUpdateExclusiveLock`, acquired by `table_open`
   at the start of the command and re-acquired inside `index_concurrently_build`
   and `validate_index`; standard transaction locks are released at main
   transaction commit
   ([indexcmds.c#initial-lock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L550-L564),
   [index.c#index_concurrently_build-locks](../../../../raw/postgres-12/src/backend/catalog/index.c#L1407-L1414),
   [index.c#validate_index-locks](../../../../raw/postgres-12/src/backend/catalog/index.c#L3203-L3206),
   [proc.c#ProcReleaseLocks](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L772-L798)).
2. A **session-level** `ShareUpdateExclusiveLock`
   (`LockRelationIdForSession`) that spans the gaps between transactions so the
   table cannot be dropped mid-build; released by `UnlockRelationIdForSession`
   at the very end
   ([indexcmds.c#session-lock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1319),
   [lmgr.c#LockRelationIdForSession](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L356-L389),
   [indexcmds.c#unlock-session-lock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1465-L1468)).

`ShareUpdateExclusiveLock` is the same level `VACUUM (non-FULL)` and `ANALYZE`
use. The command examples below come from v12's lock-mode definitions and lock
documentation
([lockdefs.h:36-46](../../../../raw/postgres-12/src/include/storage/lockdefs.h#L36-L46),
[mvcc.sgml#table-level-locks](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L890-L1039)).
Its conflict row shows what it lets through and what it blocks
([lock.c#LockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L65-L103)):

| Other lock (command) | Conflicts with CIC's `ShareUpdateExclusiveLock`? |
|---|---|
| `AccessShareLock` (`SELECT`) | No — reads continue |
| `RowShareLock` (`SELECT FOR UPDATE/SHARE`) | No |
| `RowExclusiveLock` (`INSERT`/`UPDATE`/`DELETE`) | No — **writes continue** |
| `ShareUpdateExclusiveLock` (another CIC, `VACUUM`, `ANALYZE`) | **Yes** — only one at a time |
| `ShareLock` (plain `CREATE INDEX`) | **Yes** |
| `ShareRowExclusiveLock` (`CREATE TRIGGER`, some `ALTER TABLE`) | **Yes** |
| `ExclusiveLock` (`REFRESH MATERIALIZED VIEW CONCURRENTLY`) | **Yes** |
| `AccessExclusiveLock` (`DROP TABLE`, `TRUNCATE`, `VACUUM FULL`, many `ALTER TABLE` / `ALTER INDEX` forms) | **Yes** — schema changes blocked |

Because `ShareUpdateExclusiveLock` is **self-conflicting**, only one concurrent
build can run on a given table at a time
([lock.c#self-conflict](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L194-L196)).

The three "waits" are **not** table locks. `WaitForLockers` does not acquire any
lock on the table; it reads the current set of conflicting lock holders with
`GetLockConflicts` and then sleeps on each one's virtual transaction ID until it
ends. New transactions that start after the holder list is taken are not waited
for, and lock waiters are not reported
([lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L850-L949),
[lock.c#GetLockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2804-L2821)).
Waits 1 and 2 pass `ShareLock`; the `ShareLock` conflict row includes
`RowExclusiveLock`, and the surrounding `DefineIndex` comments describe these
waits as waiting out transactions with the table open for write / with the index
still marked read-only for updates
([lock.c#ShareLock-row](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L83-L86),
[indexcmds.c#wait1](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1328-L1346),
[indexcmds.c#wait2](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1381-L1389)).
Wait 3 (`WaitForOlderSnapshots`) instead waits on transactions holding old
snapshots, excluding autovacuum workers and lazy `VACUUM` (which cannot be
confused by missing index entries), but it does **not** exclude other CIC
operations
([indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L307-L402)).

End-to-end table lock timeline:

| Phase | Heap/table lock state | Other relation locks | Wait performed | Catalog effect |
|---|---|---|---|---|
| Txn 1: create catalog row | Txn `ShareUpdateExclusiveLock` from command start; session `ShareUpdateExclusiveLock` taken before commit ([indexcmds.c#initial-lock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L550-L564), [indexcmds.c#session-lock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1319)) | — | — | `indislive=t`, `indisready=f`, `indisvalid=f` |
| (commit 1) | Txn lock released; session lock held | — | — | cataloged-but-unbuilt index now visible |
| Txn 2: wait, then build | During Wait 1: session lock only; during build: heap `ShareUpdateExclusiveLock` ([index.c#index_concurrently_build-locks](../../../../raw/postgres-12/src/backend/catalog/index.c#L1407-L1414)) | Target index `RowExclusiveLock` during build | Wait 1: `WaitForLockers(ShareLock)` waits on current conflicting holders, notably writers | first scan; then `indisready=t` |
| (commit 2) | Txn lock released; session lock held | — | — | `indisready` visible |
| Txn 3: wait, then validate | During Wait 2: session lock only; during validation: heap `ShareUpdateExclusiveLock` ([index.c#validate_index-locks](../../../../raw/postgres-12/src/backend/catalog/index.c#L3203-L3206)) | Target index `RowExclusiveLock` during validation | Wait 2: `WaitForLockers(ShareLock)` waits on current conflicting holders, notably writers | second scan inserts missing tuples |
| (commit 3) | Txn lock released; session lock held | — | — | reference snapshot dropped |
| Txn 4: mark valid | Session `ShareUpdateExclusiveLock` still held; no heap transaction lock is opened in this phase ([indexcmds.c#set-valid](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1446-L1468)) | `pg_index` is opened `RowExclusiveLock` inside `index_set_state_flags` ([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403)) | Wait 3: `WaitForOlderSnapshots(limitXmin)` | `indisvalid=t`; relcache inval; session lock released |

Throughout, the **only** lock the table ever carries is
`ShareUpdateExclusiveLock` (transaction-level within each phase, session-level
across the gaps). DML conflicts with none of these, which is the whole point of
CIC
([lock.c#LockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L78-L86)).

### How concurrent index builds interact with each other

PostgreSQL 12 does **not** have a special safe-concurrent-index-build exclusion
in `WaitForOlderSnapshots`: the call passes only `PROC_IS_AUTOVACUUM |
PROC_IN_VACUUM` as its exclusion mask
([indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L307-L348)).
Concurrent index builders interact through two ordinary mechanisms: relation
locks and database-wide old-snapshot waits.

- **Same table: the lock serializes them before the snapshot wait.**
  `DefineIndex` opens the heap with `ShareUpdateExclusiveLock` for a concurrent
  build and then keeps a session-level `ShareUpdateExclusiveLock` across the
  phase commits
  ([indexcmds.c#heap-lockmode](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L563-L564),
  [indexcmds.c#session-lock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1316)).
  That lock conflicts with itself
  ([lock.c#SUE-self-conflict](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L78-L81)),
  and the v12 docs state that only one concurrent index build can occur on a
  table at a time
  ([ref/create_index.sgml#one-concurrent-build-per-table](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L614-L621)).
  So a second CIC on the same heap waits at the initial table-lock acquisition;
  it does not reach a same-table mutual `WaitForOlderSnapshots` cycle.

- **Different tables: writer waits are table-local, but the old-snapshot wait is
  database-wide.** Waits 1 and 2 call `WaitForLockers(heaplocktag, ShareLock,
  true)` for the target heap only
  ([indexcmds.c#wait1](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1328-L1346),
  [indexcmds.c#wait2](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1381-L1389)).
  `WaitForLockersMultiple` waits only for the lock holders it collects from the
  passed lock tags; it does not acquire the heap lock itself, and later holders
  are outside that wait set
  ([lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L850-L860)).
  Wait 3 is different: `WaitForOlderSnapshots` calls
  `GetCurrentVirtualXIDs(limitXmin, true, false, PROC_IS_AUTOVACUUM |
  PROC_IN_VACUUM, ...)`, so it filters by same database, nonzero `xmin`, and
  `xmin <= limitXmin`, not by table
  ([indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L307-L348),
  [procarray.c#GetCurrentVirtualXIDs-filters](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2471-L2490),
  [procarray.c#GetCurrentVirtualXIDs-loop](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2508-L2540)).
  The only v12 exclusion mask there is autovacuum plus manual lazy `VACUUM`
  (`PROC_IS_AUTOVACUUM | PROC_IN_VACUUM`)
  ([proc.h#vacuumFlags](../../../../raw/postgres-12/src/include/storage/proc.h#L53-L63)).
  Therefore a different-table CIC, or a `REINDEX CONCURRENTLY` build using the
  same helper, can be in the Wait 3 set if it is in the same database and is
  still advertising an old `xmin`.

- **The deadlock-avoidance step clears the builder's own advertised `xmin` before
  waiting.** After validation, CIC saves the reference snapshot's `xmin`, pops
  and unregisters that snapshot, commits, starts a new transaction, asserts that
  `MyPgXact->xmin` is invalid, and only then calls `WaitForOlderSnapshots`
  ([indexcmds.c#drop-reference-snapshot](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1414-L1424),
  [indexcmds.c#no-xmin-before-wait](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1426-L1438),
  [indexcmds.c#wait3](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1440-L1448)).
  The source comment names other CIC processes as the reason to drop the
  reference snapshot before waiting
  ([indexcmds.c#drop-reference-snapshot](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1415-L1419)).
  This does not make other builders invisible. It makes the waiting builder stop
  being an old-snapshot holder before it waits on anyone else.

- **`REINDEX CONCURRENTLY` follows the same boundary.**
  `ReindexRelationConcurrently` takes analogous `ShareUpdateExclusiveLock`
  relation locks on the heap, old index, and new index, records heap lock tags
  for the writer waits, registers and drops a reference snapshot for validation,
  commits into a new transaction, and then calls `WaitForOlderSnapshots`
  ([indexcmds.c#RIC-locks](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2957-L3077),
  [indexcmds.c#RIC-build-validate-wait](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3080-L3198)).
  So the snapshot-wait interaction is not a CIC-only code path.

- **The direct inter-CIC isolation test covers different tables.**
  `multiple-cic.spec` creates two tables, starts two simultaneous CIC commands,
  and uses an advisory-lock predicate to make the first command wait while the
  second command runs. That wait is test-induced; the point of the test is that
  a CIC on a different table can proceed while the first CIC is still open
  ([multiple-cic.spec](../../../../raw/postgres-12/src/test/isolation/specs/multiple-cic.spec#L1-L40)).
  The expected output shows the first CIC waiting, the second CIC executing, and
  then the first completing
  ([multiple-cic.out](../../../../raw/postgres-12/src/test/isolation/expected/multiple-cic.out#L3-L19)).

Resolved conclusion: the old open question was too narrow. In the traced v12
paths, inter-builder behavior consists of same-table serialization by
`ShareUpdateExclusiveLock`, same-database old-snapshot waiting through
`GetCurrentVirtualXIDs`, and the final-phase rule that the builder must clear
its own advertised `xmin` before calling `WaitForOlderSnapshots`
([indexcmds.c#heap-lockmode](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L563-L564),
[procarray.c#GetCurrentVirtualXIDs-loop](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2508-L2540),
[indexcmds.c#no-xmin-before-wait](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1426-L1448)).
The traced `DefineIndex`, `WaitForLockers`, `WaitForOlderSnapshots`,
`GetCurrentVirtualXIDs`, and `ReindexRelationConcurrently` paths show those
mechanisms, not a separate v12 CIC-specific exclusion flag or side channel
([lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L850-L860),
[indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L307-L348),
[indexcmds.c#RIC-build-validate-wait](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3080-L3198)).

### All operations that can block CREATE INDEX CONCURRENTLY

The core CIC phase choreography has four deliberate transaction-synchronization
barriers: the initial table-lock acquisition, the two
`WaitForLockers(ShareLock)` waits, and the `WaitForOlderSnapshots` wait. The
four barriers give a complete lock-mode/VXID account of the handoffs between
CIC phases. They are **not** every place the command can wait: DDL event
triggers, index predicates and expressions, index-AM code, unique validation,
and parallel-worker coordination can also block inside a phase, as detailed
after the four barriers.

#### Point 1 — acquiring `ShareUpdateExclusiveLock` at command start

After any `ddl_command_start` event trigger has run, the `T_IndexStmt` dispatch
looks up and locks the table in `ShareUpdateExclusiveLock` mode
([utility.c#DDL-start](../../../../raw/postgres-12/src/backend/tcop/utility.c#L960-L975),
[utility.c#CIC-lockmode](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1311-L1326)).
CIC queues until every conflicting `ShareUpdateExclusiveLock`, `ShareLock`,
`ShareRowExclusiveLock`, `ExclusiveLock`, or `AccessExclusiveLock` is released
([lock.c#SUE-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L78-L81)).
The listed SQL commands normally release transaction-level locks at transaction
end; another CIC's session-level lock instead survives its internal commits and
is released when that CIC finishes or errors
([indexcmds.c#session-lock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1319),
[indexcmds.c#session-unlock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1465-L1468)).
The v12 lock documentation gives these command examples:

| Lock mode held by another session | Example operations (v12) |
|---|---|
| `ShareUpdateExclusiveLock` | `VACUUM` (non-FULL), autovacuum, `ANALYZE`, another `CREATE INDEX CONCURRENTLY`, `REINDEX CONCURRENTLY`, `CREATE STATISTICS`, certain `ALTER TABLE`/`ALTER INDEX` variants ([mvcc.sgml#SHARE-UPDATE-EXCLUSIVE](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L912-L936)) |
| `ShareLock` | plain `CREATE INDEX` ([mvcc.sgml#SHARE](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L938-L956)) |
| `ShareRowExclusiveLock` | `CREATE TRIGGER`, some `ALTER TABLE` forms ([mvcc.sgml#SHARE-ROW-EXCLUSIVE](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L958-L978)) |
| `ExclusiveLock` | `REFRESH MATERIALIZED VIEW CONCURRENTLY` ([mvcc.sgml#EXCLUSIVE](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L980-L1000)) |
| `AccessExclusiveLock` | `DROP TABLE`, `TRUNCATE`, `REINDEX`, `CLUSTER`, `VACUUM FULL`, `REFRESH MATERIALIZED VIEW` (non-concurrent), many `ALTER TABLE`/`ALTER INDEX` forms, and `LOCK TABLE` without an explicit mode ([mvcc.sgml#ACCESS-EXCLUSIVE](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L1002-L1030)) |

`LOCK TABLE` naming any of these five modes explicitly blocks the acquisition
the same way, per the conflict table
([lock.c#LockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L65-L105)).
Plain reads and writes never block this point: `AccessShareLock`,
`RowShareLock`, and `RowExclusiveLock` are absent from
`ShareUpdateExclusiveLock`'s conflict mask
([lock.c#SUE-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L78-L81)).

Two special blockers at this point:

- **Autovacuum** holding the table's `ShareUpdateExclusiveLock` normally
  yields: after CIC has waited `deadlock_timeout`, the lock manager detects
  `DS_BLOCKED_BY_AUTOVACUUM` and sends the worker `SIGINT`
  ([proc.c#autovacuum-cancel](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1308-L1375)).
  The exception is an anti-wraparound autovacuum
  (`PROC_VACUUM_FOR_WRAPAROUND`), which is never cancelled and must finish
  ([proc.c#wraparound-exception](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1319-L1324)).
- **Prepared transactions** keep their locks after `PREPARE TRANSACTION`; the
  locks are transferred to the primary lock table and stay held until
  `COMMIT PREPARED` / `ROLLBACK PREPARED`
  ([lock.c#prepared-locks](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2873-L2876)).
  A prepared transaction holding a conflicting mode blocks CIC indefinitely.

The session-level lock taken just before commit 1 never blocks, because the
same lock is already held at transaction level
([indexcmds.c#session-lock-noblock](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1310)).

#### Points 2 and 3 — Wait 1 (before build) and Wait 2 (before validation)

`WaitForLockers(heaplocktag, ShareLock, true)` collects the virtual
transaction IDs of transactions **currently holding** table locks that
conflict with `ShareLock`, then sleeps on each one until its whole transaction
ends ([lmgr.c#wait-loop](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L896-L918)).
`ShareLock` conflicts with `RowExclusiveLock` plus every mode from
`ShareUpdateExclusiveLock` up
([lock.c#ShareLock-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L83-L86)),
but CIC's own `ShareUpdateExclusiveLock` already keeps out every holder at
that level or above, so in practice these waits block on one thing: **open
transactions that hold `RowExclusiveLock`**, i.e. any transaction that ran
`INSERT`, `UPDATE`, `DELETE`, or any other data-modifying command on the table
([mvcc.sgml#ROW-EXCLUSIVE](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L890-L910)).
The wait is for the transaction, not the statement: a session that wrote one
row and then sits idle in transaction blocks CIC until it commits or rolls
back.

Not waited for at these two points:

- Plain `SELECT` (`AccessShareLock`) and `SELECT FOR UPDATE/SHARE`
  (`RowShareLock`) — neither mode is in `ShareLock`'s conflict mask
  ([lock.c#ShareLock-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L83-L86)).
- Transactions merely **waiting** for a conflicting lock; only current
  holders are reported
  ([lock.c#GetLockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2804-L2818)).
- Writers that start after the holder list is collected; they already see the
  index ([lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L855-L860)).
- **Prepared transactions**: `GetLockConflicts` ignores them
  ([lock.c#GetLockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2815-L2818)),
  and `WaitForLockersMultiple` states this is fine "since they certainly
  aren't going to do anything anymore"
  ([lmgr.c#prepared-comment](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L890-L894)).
  This skip is **not** sufficient for index correctness on its own — see
  [Is skipping prepared transactions in the writer waits safe?](#is-skipping-prepared-transactions-in-the-writer-waits-safe).

These waits use real lock acquisition on each holder's virtual transaction ID
precisely so that deadlock detection applies; a cycle errors out instead of
hanging forever
([indexcmds.c#wait-deadlock-note](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1338-L1342)).

#### Point 4 — Wait 3 (before marking valid): old snapshot holders

`WaitForOlderSnapshots(limitXmin, true)` is the broadest wait. At the start of
the wait it collects every backend **in the same database** whose advertised
`xmin` is at or below the reference snapshot's `xmin` — regardless of which
tables that backend touches
([indexcmds.c#wait3-filter](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L346-L348),
[procarray.c#GetCurrentVirtualXIDs](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2467-L2548)).
Operations that block here:

- Any already-running long-running query in the same database whose advertised
  `xmin` passes that filter, even a single-statement `SELECT` against an
  unrelated table — the filter is "oldest live snapshot older than ours", not
  "uses this table"
  ([procarray.c#xmin-filter](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2480-L2482),
  and the docs describe the phase as waiting for "transactions that can
  potentially see the table to release their snapshots"
  ([monitoring.sgml#wait-old-snapshots](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3699-L3708))).
- Open `REPEATABLE READ` / `SERIALIZABLE` transactions whose first snapshot
  predates the reference snapshot: the first snapshot "must live until end of
  xact"
  ([snapmgr.c#GetTransactionSnapshot](../../../../raw/postgres-12/src/backend/utils/time/snapmgr.c#L336-L356)).
- `READ COMMITTED` sessions idle in transaction while still holding a
  registered snapshot (for example an open cursor); only backends whose
  `xmin` is zero are skipped
  ([procarray.c#xmin0-skip](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2525-L2526)).
- Manual `ANALYZE`, which the wait explicitly cannot exclude because it may
  run inside a transaction that does arbitrary work later
  ([indexcmds.c#analyze-not-excluded](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L322-L326)).
- Another `CREATE INDEX CONCURRENTLY` or `REINDEX CONCURRENTLY` in the same
  database while it holds a snapshot (its build or validation scan): the v12
  exclusion mask covers only vacuum flags, not other index builds
  ([indexcmds.c#wait3-filter](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L346-L348)).
- A running `pg_dump` of the same database — see the worked example below.

Not waited for at this point:

- Autovacuum workers and backends running manual lazy `VACUUM`
  (`PROC_IS_AUTOVACUUM | PROC_IN_VACUUM`
  [proc.h#vacuumFlags](../../../../raw/postgres-12/src/include/storage/proc.h#L53-L56),
  filtered at
  [indexcmds.c#wait3-filter](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L346-L348)).
- Sessions attached to **other databases**, which can never see the index
  ([indexcmds.c#other-dbs](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L318-L320),
  [procarray.c#same-db](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2520)).
- Backends with no live snapshot (`xmin` = 0). The wait also re-checks the
  list between sleeps and drops any backend whose `xmin` has since cleared
  ([indexcmds.c#idle-recheck](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L331-L338),
  [indexcmds.c#recheck-loop](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L357-L383)).
- Backends whose `xmin` is newer than `limitXmin`
  ([procarray.c#limitXmin](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2532-L2533)).
- **Prepared transactions**: their dummy `PGPROC` carries
  `xmin = InvalidTransactionId` and `backendId = InvalidBackendId`
  ([twophase.c#MarkAsPreparingGuts](../../../../raw/postgres-12/src/backend/access/transam/twophase.c#L465-L472)),
  so both the xmin filter and the virtual-transaction-ID validity check skip
  them
  ([procarray.c#vxid-check](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2525-L2539)).
- **Walsenders and replication-slot xmin holders**: a standby using
  `hot_standby_feedback`, and any physical or logical replication slot, hold
  back the cluster's dead-row *removal* horizon, but never as a per-backend
  snapshot the wait can see — see
  [Can walsenders or replication-slot xmin holders appear in the Wait 3 set?](#can-walsenders-or-replication-slot-xmin-holders-appear-in-the-wait-3-set).

#### Worked example: a running pg_dump

A `pg_dump` of the **same database** can block CIC at exactly one point — Wait
3 — and when it is in the Wait 3 set it blocks for the dump's entire remaining
duration. `pg_dump` wraps the whole dump in a single transaction: `BEGIN`
followed by
`SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY` (or
`SERIALIZABLE, READ ONLY, DEFERRABLE` under `--serializable-deferrable`)
([pg_dump.c#dump-transaction](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L1166-L1194)),
so its advertised `xmin` stays pinned from start to finish
([snapmgr.c#GetTransactionSnapshot](../../../../raw/postgres-12/src/backend/utils/time/snapmgr.c#L336-L356)).
It also disables `statement_timeout`, `lock_timeout`, and
`idle_in_transaction_session_timeout` on its connection, so no timeout will
end it early
([pg_dump.c#disable-timeouts](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L1140-L1147)).

The other three points never see it: the only table locks `pg_dump` takes are
`ACCESS SHARE`
([pg_dump.c#lock-table](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L6646-L6671)),
which is in neither `ShareUpdateExclusiveLock`'s nor `ShareLock`'s conflict
mask ([lock.c#SUE-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L78-L81),
[lock.c#ShareLock-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L83-L86))
— even when it is dumping the very table being indexed. Two boundary cases
follow from the Wait 3 filters above: a dump of **another database** is
skipped entirely, and a same-database dump is skipped only if it is absent from
the initial Wait 3 list or its advertised `xmin` is newer than `limitXmin`.
Starting after CIC's reference snapshot is not, by itself, the test; the code
checks the advertised `xmin` and VXID list
([indexcmds.c#wait3-recheck](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L346-L383),
[procarray.c#limitXmin](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2532-L2539)).
The blocking is also one-way: CIC never blocks `pg_dump`, since
`ShareUpdateExclusiveLock` does not conflict with `AccessShareLock`.

#### Worked example: a transaction held open for an hour (idle in transaction)

An open transaction — including a session sitting `idle in transaction` —
blocks CIC only through what it has already done, never through its age:

| What the open transaction did | Blocks CIC at | For how long |
|---|---|---|
| `BEGIN;` only, no statements yet | nothing | — |
| Wrote the **target table** (`INSERT`/`UPDATE`/`DELETE`), now idle | Wait 1 (or 2) | until it commits or rolls back ([mvcc.sgml#ROW-EXCLUSIVE](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L890-L910), [lmgr.c#wait-loop](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L896-L918)) |
| `REPEATABLE READ`/`SERIALIZABLE`, snapshot taken before the reference snapshot, same database | Wait 3 | until transaction end ([snapmgr.c#GetTransactionSnapshot](../../../../raw/postgres-12/src/backend/utils/time/snapmgr.c#L336-L356)) |
| `READ COMMITTED`, only reads (or writes to **other** tables), idle, no open cursors | nothing | — ([snapmgr.c#SnapshotResetXmin](../../../../raw/postgres-12/src/backend/utils/time/snapmgr.c#L989-L1028)) |
| `READ COMMITTED` holding a portal/cursor snapshot, or mid-statement on an old snapshot | Wait 3 | until the cursor closes / the snapshot is released ([pquery.c#CreateQueryDesc](../../../../raw/postgres-12/src/backend/tcop/pquery.c#L68-L83), [pquery.c#PortalRunSelect](../../../../raw/postgres-12/src/backend/tcop/pquery.c#L924-L932)) |
| Took a conflicting lock on the target table (DDL, `LOCK TABLE`) | initial acquisition | until transaction end |

The writer row is the operationally painful one. A transaction that touched
even one row of the target table holds `RowExclusiveLock` until transaction
end, and `WaitForLockers` sleeps on its virtual transaction ID until the
**whole transaction** finishes — there is no recheck or escape at Waits 1/2
([lmgr.c#wait-loop](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L896-L918)).
Because Wait 1 runs before the build scan even starts, one idle-in-transaction
session that ran a single `UPDATE` an hour ago stalls CIC at its first phase
for the remaining hour.

The reads-only row is the counter-intuitive one: an idle-in-transaction
`READ COMMITTED` session that only ran `SELECT`s does **not** block CIC at
all. Once its statement finished and no registered snapshots remained,
`SnapshotResetXmin` cleared its advertised `xmin`
([snapmgr.c#SnapshotResetXmin](../../../../raw/postgres-12/src/backend/utils/time/snapmgr.c#L989-L1028)),
so Wait 3 skips it — and would drop it mid-wait if it went idle later
([indexcmds.c#idle-recheck](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L331-L338)).
Its leftover `AccessShareLock` matters at no blocking point. Writes to
**other** tables are equally irrelevant at Waits 1/2, because
`WaitForLockers` examines only the target table's lock tag
([indexcmds.c#wait1](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1346)).

A transaction that starts after CIC has collected a wait's holder/VXID list
never extends that specific wait: the Waits 1/2 holder list is a point-in-time
snapshot
([lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L855-L860)),
and Wait 3's initial VXID list is only rechecked to remove entries that no
longer qualify, not to add new ones
([indexcmds.c#wait3-recheck](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L346-L383)).

#### Other waits outside the four orchestration barriers

The four barriers above are the complete CIC-specific transaction handoffs, but
they are not a closed list of backend waits:

- **DDL event triggers can wait before the initial relation lock and after the
  index is marked valid.** `ProcessUtilitySlow` invokes `ddl_command_start`
  before `T_IndexStmt` dispatch and `ddl_command_end` after `DefineIndex`
  returns; each event trigger is a user function invoked by `FunctionCallInvoke`
  ([utility.c#event-trigger-boundary](../../../../raw/postgres-12/src/backend/tcop/utility.c#L960-L975),
  [utility.c#DDL-end](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1701-L1713),
  [event_trigger.c#EventTriggerInvoke](../../../../raw/postgres-12/src/backend/commands/event_trigger.c#L1031-L1092)).
- **Index predicates and expressions can wait in user code.** v12 rejects
  functions that are not marked `IMMUTABLE`, but that marking does not prevent
  a function from taking a lock. The `multiple-cic` isolation test deliberately
  marks PL/pgSQL functions immutable and calls `pg_advisory_lock_shared` from a
  partial-index predicate to suspend one CIC while another proceeds
  ([indexcmds.c#immutable-expressions-and-predicates](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1476-L1660),
  [multiple-cic.spec#predicate-lock](../../../../raw/postgres-12/src/test/isolation/specs/multiple-cic.spec#L3-L40)).
- **Unique validation can wait for a conflicting writer.** The second heap scan
  inserts a missing tuple with `UNIQUE_CHECK_YES`; B-tree insertion waits on a
  conflicting transaction or speculative insertion before retrying
  ([heapam_handler.c#validation-insert](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1873-L1934),
  [nbtinsert.c#unique-waits](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L252-L274)).
- **A parallel B-tree first scan waits for its workers.** The leader waits for
  workers to attach and finish and sleeps on a condition variable until all
  participating tuple sorts report completion
  ([nbtsort.c#parallel-worker-waits](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1473-L1506),
  [nbtsort.c#parallel-scan-wait](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1521-L1561)).
- **An index AM can have additional internal waits.** Core dispatches to
  `ambuild`, `ambulkdelete`, and `aminsert`; an extension AM owns those callback
  bodies, so no finite list of SQL operations can describe waits introduced by
  arbitrary third-party AM code
  ([amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L160-L229),
  [indexam.sgml#index-locking](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L891-L911)).

These waits do not add catalog phases. If one errors or is cancelled, the
leftover state still depends on whether `SET_READY` or `SET_VALID` has already
run.

#### Watching the waits

The three core transaction-set waits are visible in
`pg_stat_progress_create_index` as the phases
`waiting for writers before build`, `waiting for writers before validation`,
and `waiting for old snapshots`, with `lockers_total`, `lockers_done`, and
`current_locker_pid` identifying who CIC is waiting on
([monitoring.sgml#create-index-phases](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3639-L3708),
[indexcmds.c#wait-progress](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L385-L395),
[lmgr.c#wait-progress](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L887-L916)).

### Is skipping prepared transactions in the writer waits safe?

**Not on its own.** Skipping prepared transactions in Waits 1 and 2 is safe for
the narrow thing the comment claims: a prepared transaction runs no more
statements, so after the wait it cannot start a new write or a new
index-incompatible HOT update
([lmgr.c#prepared-comment](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L890-L894)).
It is **not** sufficient for full index correctness. A transaction that wrote
the table and then ran `PREPARE TRANSACTION` has already made changes that are
not yet committed, are invisible to both concurrent scans, and are never
backfilled — yet they become live later at `COMMIT PREPARED` with no index
entry. The pinned source's own correctness invariant is not satisfied for such
a transaction.

**The invariant the waits are supposed to establish.** The `validate_index`
header states the rule the two writer waits enforce: CIC waits "for all
transactions that could have been modifying the table to terminate" (twice), so
the build and validate scans see a settled writer set, and it then relies on the
claim that "Any tuples committed live after the snap will be inserted into the
index by their originating transaction"
([index.c#validate_index-overview](../../../../raw/postgres-12/src/backend/catalog/index.c#L3117-L3144)).
The Wait 1 comment in `DefineIndex` says the same thing concretely: after the
wait, "any updates made by transactions that didn't know about the index are now
committed or rolled back"
([indexcmds.c#wait1-hot-safety](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1348-L1364)).
A prepared transaction is the one writer that has neither "terminated" nor been
"committed or rolled back," and that will not insert its tuples "by their
originating transaction." It falls outside both halves of the invariant.

**Why a prepared transaction is skipped at every wait.** `PREPARE TRANSACTION`
builds a dummy `PGPROC` whose `xid` is still the real, in-progress XID, but whose
`xmin` and `backendId` are invalid
([twophase.c#MarkAsPreparingGuts](../../../../raw/postgres-12/src/backend/access/transam/twophase.c#L465-L472)).
Two consequences:

- Waits 1 and 2 collect conflicting lock holders with `GetLockConflicts`. Both
  of its scan phases — the fast-path array scan and the primary lock-table scan
  — read each conflicting holder's virtual transaction ID and discard any
  invalid VXID
  ([lock.c#fast-path-skip](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2930-L2936),
  [lock.c#primary-table-skip](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2995-L3001)).
  At prepare the prepared xact's `RowExclusiveLock` was transferred to the
  primary lock table
  ([lock.c#prepared-locks](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2873-L2876)),
  so `GetLockConflicts` meets it only in the primary-table scan, where its dummy
  proc yields an invalid VXID (invalid `backendId`) and is dropped; the prepared
  xact is never waited on.
- Wait 3 (`WaitForOlderSnapshots`) filters on `xmin` and a valid VXID, both of
  which the dummy proc lacks, so it is skipped there too
  ([procarray.c#vxid-check](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2525-L2539))
  — as already noted under Point 4.

**Why the scans never index its tuples.** The prepared xact's `xid` stays in the
proc array as in-progress until `COMMIT PREPARED` removes it
([procarray.c#prepared-in-array](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L15-L18),
[twophase.c#commit-prepared-procarray](../../../../raw/postgres-12/src/backend/access/transam/twophase.c#L1514-L1534)).
Both CIC scans use ordinary MVCC snapshots, so they treat the prepared xact as
in-progress and never see the row versions it inserted. The concurrent build
takes the `else` "heap_getnext did the time qual check" branch and never runs
the `SnapshotAny` `INSERT_IN_PROGRESS` logic, the only path that indexes
in-progress tuples
([heapam_handler.c#insert-in-progress](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1429-L1494),
[heapam_handler.c#mvcc-branch](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1595-L1600)).

**Why `COMMIT PREPARED` does not fix it.** `COMMIT PREPARED` records the commit,
marks the XID committed, removes the proc from the proc array, and runs only the
two-phase resource-manager callbacks (which release locks, predicate locks, and
update stats). It does no executor work and inserts into no index
([twophase.c#FinishPreparedTransaction](../../../../raw/postgres-12/src/backend/access/transam/twophase.c#L1455-L1534)).
The index entries a transaction makes are created when it runs its DML, for the
indexes that exist then; an index created afterward gets nothing — and a
not-yet-ready index is skipped by writers in any case
([execIndexing.c#skip-not-ready](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L330-L332)).

**A concrete sequence (plain `INSERT`).** With `max_prepared_transactions > 0`:

| Step | Action | Effect on the new index |
|---|---|---|
| 1 | Session A: `BEGIN; INSERT INTO t(c) VALUES (1);` | tuple X written, `xmin` = A, in-progress |
| 2 | Session A: `PREPARE TRANSACTION 'p';` | A's lock moves to a dummy proc; X still invisible |
| 3 | Session B: `CREATE INDEX CONCURRENTLY i ON t(c);` Txn 1 | empty `i` committed (`indislive`, not ready, not valid) |
| 4 | Wait 1 | A skipped (invalid VXID); returns at once |
| 5 | Txn 2 build scan (MVCC) | A in-progress -> X invisible -> X not indexed; `indisready` set |
| 6 | Wait 2 | A skipped; returns at once |
| 7 | Txn 3 `validate_index` (reference snapshot) | A in-progress -> X invisible -> X not backfilled |
| 8 | Wait 3 | A skipped (invalid `xmin`); returns at once |
| 9 | Txn 4 | `indisvalid` set — `i` is valid but lacks X |
| 10 | `COMMIT PREPARED 'p';` | X becomes live; no index entry is ever created for it |

After step 10, `SELECT c FROM t WHERE c = 1` answered by `i` returns no row,
while a sequential scan returns X. The same outcome applies to the new live
version produced by an `UPDATE` (HOT or not) that a prepared transaction
performed before the index became ready. A prepared `DELETE` is harmless: it
leaves at most a dead index entry, which is normal and reclaimed by VACUUM. The
gap does not depend on how long the transaction stays prepared — any
`COMMIT PREPARED` after the index is built, of writes the scans could not see,
exposes it.

**Contrast: a non-concurrent `CREATE INDEX` is not exposed this way.** A plain
build takes `ShareLock` on the heap
([utility.c:1320-1321](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1320-L1321)),
which conflicts with the prepared xact's `RowExclusiveLock`
([lock.c#ShareLock-conflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L83-L86)),
so it blocks at lock acquisition until `COMMIT PREPARED` / `ROLLBACK PREPARED`,
then scans the resolved heap with `SnapshotAny`. CIC takes only
`ShareUpdateExclusiveLock`, which does not conflict with `RowExclusiveLock`, and
replaces lock-blocking with the VXID waits that skip prepared xacts — which is
exactly where the gap enters.

**Scope of this assessment.** The pinned source establishes the mechanism. A
temporary build of that exact 12.2 pin also reproduced it: after preparing an
`INSERT`, CIC reached `(indislive, indisready, indisvalid) = (t,t,t)`; after
`COMMIT PREPARED`, a forced index scan found zero rows while a sequential scan
found one. The source itself flags the underlying choice as questionable:
`GetLockConflicts` notes that ignoring prepared transactions "is a bit more
debatable but is appropriate for current uses of the result"
([lock.c#GetLockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2815-L2818)).
Nothing in this checkout's CIC code or `CREATE INDEX` documentation guards
against, or warns about, building an index concurrently while a conflicting
prepared transaction is outstanding.

### Can walsenders or replication-slot xmin holders appear in the Wait 3 set?

**No — not through replication's xmin-holdback machinery.** A standby using
`hot_standby_feedback`, and any physical or logical replication slot, hold back
the cluster's dead-row removal horizon, but they do so in a way
`WaitForOlderSnapshots` never observes. Three independent facts keep these
backends out of the Wait 3 set; the only walsender that can appear is one that
is, at that moment, running an ordinary in-database transaction — already
covered by the lists above.

**1. A replication slot's reserved xmin is a global, not a per-backend xmin.**
Each slot's `effective_xmin` / `effective_catalog_xmin` is aggregated across all
slots by `ReplicationSlotsComputeRequiredXmin` and stored in two *global*
`ProcArrayStruct` fields — `replication_slot_xmin` and
`replication_slot_catalog_xmin` — via `ProcArraySetReplicationSlotXmin`
([slot.c#ReplicationSlotsComputeRequiredXmin](../../../../raw/postgres-12/src/backend/replication/slot.c#L701-L742),
[procarray.c#slot-xmin-fields](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L90-L93),
[procarray.c#ProcArraySetReplicationSlotXmin](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2982-L2992)).
`GetCurrentVirtualXIDs` — the function behind Wait 3 — only ever reads each
backend's own `pgxact->xmin` in its proc-array loop and never consults those
slot globals
([procarray.c#GetCurrentVirtualXIDs-xmin](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2520-L2523)).
So a slot can pin the removal horizon arbitrarily far back without ever
contributing a VXID to the Wait 3 set. The slot globals *are* consulted
elsewhere: `GetOldestXmin` folds them into the VACUUM removal horizon
([procarray.c#GetOldestXmin-slots](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L1425-L1441)),
and `GetSnapshotData` folds them into `RecentGlobalXmin`
([procarray.c#GetSnapshotData-slots](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L1727-L1741)).
Wait 3 is simply not one of those call sites.

**2. A physical walsender is filtered out by database, even when it advertises
its own xmin.** With `hot_standby_feedback` on and no slot, the walsender writes
the standby's reported xmin straight into its own `MyPgXact->xmin` "so that the
xmin will be taken into account by GetOldestXmin"
([walsender.c#hs-feedback-xmin](../../../../raw/postgres-12/src/backend/replication/walsender.c#L2026-L2065)).
But a plain (physical) walsender connects to no database: `InitPostgres`
returns early for `am_walsender && !am_db_walsender` without ever setting
`MyDatabaseId`, so its `proc->databaseId` keeps the `InvalidOid` it was given at
`InitProcess`
([postinit.c#walsender-no-db](../../../../raw/postgres-12/src/backend/utils/init/postinit.c#L841-L867),
[proc.c#InitProcess-databaseId](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L394-L396)).
`GetCurrentVirtualXIDs`'s same-database test is `proc->databaseId ==
MyDatabaseId`
([procarray.c#GetCurrentVirtualXIDs-db](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2520)),
and — unlike `GetOldestXmin` — it has **no** `|| proc->databaseId == 0 /* always
include WalSender */` clause
([procarray.c#GetOldestXmin-walsender-clause](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L1348-L1350)).
So the physical walsender is skipped by database. When it uses a slot instead,
it clears `MyPgXact->xmin` to `InvalidTransactionId` and reserves through the
slot, so there is no per-backend xmin to find at all
([walsender.c#slot-clears-xmin](../../../../raw/postgres-12/src/backend/replication/walsender.c#L1872-L1909)).

**3. The VXID gate matches xmin's own lifecycle: no transaction, no xmin, no
VXID.** Even a backend that passed the database and xmin filters is recorded
only when `VirtualTransactionIdIsValid(vxid)` holds
([procarray.c#vxid-gate](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2537-L2539)),
which requires a valid `lxid`
([lock.h#VirtualTransactionIdIsValid](../../../../raw/postgres-12/src/include/storage/lock.h#L69-L82)).
A backend's `lxid` is assigned in `StartTransaction`
([xact.c#StartTransaction-lxid](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1981-L1994))
and cleared, together with `pgxact->xmin`, in `ProcArrayEndTransaction`
([procarray.c#ProcArrayEndTransaction](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L433-L456)).
Because an ordinary backend only advertises an xmin from within a transaction,
and that xmin is cleared together with the local transaction id when the
transaction ends, a backend that is *not* in a transaction has both an invalid
`lxid` and a zero xmin — there is no normal "old xmin but no transaction" state
for the wait to miss. The only two code paths that set `pgxact->xmin` *outside*
a normal transaction are the physical-walsender feedback path (excluded by item
2) and the prepared-transaction dummy proc, which sets `xmin =
InvalidTransactionId` anyway
([twophase.c#MarkAsPreparingGuts](../../../../raw/postgres-12/src/backend/access/transam/twophase.c#L465-L472)).

**The one walsender that can be in the set is a logical walsender
mid-transaction.** When a logical slot is created with an exported snapshot,
`SnapBuildInitialSnapshot` runs inside a `REPEATABLE READ` transaction (it
asserts `XactIsoLevel == XACT_REPEATABLE_READ`) and sets `MyPgXact->xmin =
snap->xmin`
([snapbuild.c#SnapBuildInitialSnapshot](../../../../raw/postgres-12/src/backend/replication/logical/snapbuild.c#L543-L583)).
A logical walsender connects to a real database (`replication=database` sets
`am_db_walsender`,
[postmaster.c#replication-database](../../../../raw/postgres-12/src/backend/postmaster/postmaster.c#L2103-L2124)),
so in that window it has a matching `databaseId`, an old xmin, and a valid
`lxid`, and it *is* eligible for Wait 3 — but only because it is then an
ordinary in-database `REPEATABLE READ` snapshot holder, indistinguishable from
the open `REPEATABLE READ` / `SERIALIZABLE` transactions already listed under
Point 4. It is not a "non-transaction backend." Routine logical *streaming*
(after the slot exists) protects catalogs through the slot's `catalog_xmin`
global, not through `MyPgXact->xmin`, so it falls back under item 1.

Net: the `hot_standby_feedback` / replication-slot horizon is real, but it
reaches CIC only through `GetOldestXmin` (what may be vacuumed) and
`GetSnapshotData`'s `RecentGlobalXmin`, never through `WaitForOlderSnapshots`.
Wait 3 waits on local, in-database, snapshot-holding transactions, and the
slot/feedback machinery does not, by itself, create one.

### Why two scans and three waits

The build cannot stop the world, so it has to reason about three groups of
writers: those that ran before the index existed, those that wrote while it was
ready-but-not-valid, and those holding old snapshots. The ordering — visible
empty index, wait, build, wait, validate, wait, mark valid — guarantees:

- After Wait 1, no transaction can do a HOT update that is incompatible with the
  new index, so the first build's scan is safe
  ([index.c#validate_index-overview](../../../../raw/postgres-12/src/backend/catalog/index.c#L3118-L3132)).
- After `indisready` and Wait 2, every live writer inserts its own new tuples
  into the index, so `validate_index` only has to backfill tuples that existed
  but were not indexed by the first scan
  ([index.c#validate_index-overview](../../../../raw/postgres-12/src/backend/catalog/index.c#L3134-L3152)).
- Wait 3 ensures no surviving transaction has a snapshot old enough to expect a
  row the index intentionally omitted, so it is finally safe to set `indisvalid`
  ([index.c#validate_index-overview](../../../../raw/postgres-12/src/backend/catalog/index.c#L3163-L3168)).

For a unique index, the uniqueness constraint is enforced from the moment the
second scan begins, so violations can surface in other sessions before the index
is even usable, and a failed second scan leaves an invalid index that still
enforces uniqueness
([ref/create_index.sgml#unique-caveat](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L598-L606)).

### Failure scenarios and the outcome on the table

Because CIC commits several times and changes its two later state flags in
place, the outcome depends on the **last persistent state transition reached**, not
just the internal transaction number:

- The catalog row is created in transaction 1 and only becomes durable at the
  first commit. **Any failure before commit 1 leaves no index at all** — the
  transaction simply rolls back
  ([indexcmds.c#commit1](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1318-L1320)).
- After commit 1 but before `SET_VALID`, a leftover is **invalid**, so the planner
  does not use it. Whether it is ready — and therefore maintained by writes and,
  for a unique index, enforcing uniqueness — depends on whether
  `index_concurrently_build` reached its final `SET_READY` action
  ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L200-L210),
  [index.c#build-set-ready](../../../../raw/postgres-12/src/backend/catalog/index.c#L1426-L1438)).
- Once `SET_VALID` runs, the index remains valid even if later command-end work
  errors, because the in-place update cannot roll back
  ([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3314-L3366),
  [utility.c#DDL-end](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1701-L1719)).

#### The three persistent pg_index states

| Leftover state | `indislive` | `indisready` | `indisvalid` | How you reach it | Example (v12 regression suite) |
|---|---|---|---|---|---|
| no index | — | — | — | failure before commit 1 | `concur_index7` — rejected inside a `BEGIN; ... COMMIT;` block, so it never appears in `\d` ([create_index.out:1391-1395](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1391-L1395)) |
| invalid, not ready | `t` | `f` | `f` | failure after commit 1, before `indisready` is set | `concur_index3` — its unique build over duplicate `f2` values failed in the build scan, leaving it `INVALID` ([create_index.out:1383-1385](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1383-L1385), [create_index.out:1415](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1415)) |
| invalid, ready | `t` | `t` | `f` | failure after `indisready` is set, before `indisvalid` | none named in the v12 suite; cancellation, timeout, deadlock, an expression error, or a concurrent duplicate after `SET_READY` can produce it ([indexcmds.c:1375-1453](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1375-L1453)), and the docs describe the unique-index case ([create_index.sgml:598-606](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L598-L606)) |
| valid | `t` | `t` | `t` | `index_set_state_flags(SET_VALID)` ran; normally success, but a later command-end error cannot roll the flag back ([index.c:3314-3366](../../../../raw/postgres-12/src/backend/catalog/index.c#L3314-L3366), [utility.c:1701-1719](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1701-L1719)) | `concur_index1` / `concur_index2` — built concurrently and listed without `INVALID` ([create_index.out:1413-1420](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1413-L1420)); no in-tree late-error test |

The `index_set_state_flags` asserts encode this exact ladder: `SET_READY`
requires live / not-ready / not-valid, and `SET_VALID` requires live / ready /
not-valid
([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3353-L3366)).

#### The same states under REINDEX INDEX CONCURRENTLY

`REINDEX INDEX CONCURRENTLY` reuses the build/validate state machine, but runs
it on a **new copy** (`<original>_ccnew`) created next to the original, then swaps
it in. Its phase loop calls `index_concurrently_build` and `validate_index` on
the copy; failures leave an invalid `_ccnew` before the swap or `_ccold` after it
([indexcmds.c#RIC-copy](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2990-L3001),
[indexcmds.c#RIC-build-validate](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3080-L3198),
[indexcmds.c#RIC-swap-and-drop](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3199-L3342)).
The full six-phase walkthrough — including the two extra `AccessExclusiveLock`
"wait for readers" phases, the swap, and the per-phase failure table — has its
own page:
[How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 12](reindex-index-concurrently.md).

#### What each leftover costs the table

| Leftover | Planner uses it? | INSERT/UPDATE/DELETE | Uniqueness | HOT |
|---|---|---|---|---|
| invalid, **not ready** | no ([plancat.c:206-210](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L206-L210)) | index is still opened and `RowExclusiveLock`-ed on every write ([execIndexing.c#ExecOpenIndices](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L185-L192)), but **no entries are inserted** ([execIndexing.c#skip-not-ready](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L330-L332)) | **not** enforced — the unique check is skipped for not-ready indexes ([execIndexing.c#unique-skip](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L537-L539)) | still counted in HOT-safety, so an update touching its columns is forced non-HOT (extra bloat) even though it receives no entries ([relcache.c#omit-not-live](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4388-L4395), [relcache.c#HOT-all-live](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4861-L4870)) |
| invalid, **ready** | no ([plancat.c:206-210](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L206-L210)) | **entries inserted on every write** — the documented "update overhead" ([execIndexing.c#skip-not-ready](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L330-L332), [ref/create_index.sgml#invalid-overhead](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L574-L580)) | **enforced** for a unique index, even while invalid ([ref/create_index.sgml#unique-caveat](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L598-L606), [nbtinsert.c#dup-key](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L563-L568)) | counted in HOT-safety |

A "dead" index (`indislive = false`) is a different thing: it appears only during
`DROP INDEX CONCURRENTLY`, and `RelationGetIndexList` drops it from every list so
nothing touches it
([relcache.c#omit-not-live](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4388-L4395),
[index.c#INDEX_DROP_SET_DEAD](../../../../raw/postgres-12/src/backend/catalog/index.c#L3384-L3396)).
CIC never leaves this state.

#### Failure by phase

| Failure point | Example causes | Leftover on the table |
|---|---|---|
| Preconditions / parse / catalog insert (transaction 1, before commit 1) | an error or wait in `ddl_command_start`; runs inside a `BEGIN; ... COMMIT;` block; partitioned, system-catalog, or exclusion-constraint table; index-name collision; `lock_timeout` while acquiring the initial `ShareUpdateExclusiveLock`; any error inside `index_create` | **none** — transaction 1 rolls back |
| Wait 1 or the build scan (transaction 2, before `indisready` is set) | deadlock / cancel (`SIGINT`) / `statement_timeout` in `WaitForLockers`; a **pre-existing duplicate** caught by the unique build sort ([tuplesort.c#dup](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L4048-L4056)); an error or wait in an index expression, predicate, AM callback, or parallel worker; out-of-space during the build | **invalid, not ready** index |
| Wait 2, `validate_index`, or Wait 3 (after `indisready` committed, before `indisvalid`) | deadlock / cancel / timeout in `WaitForLockers`, unique insertion, or `WaitForOlderSnapshots`; a **duplicate that appears concurrently** and is hit by the second scan's `index_insert` ([nbtinsert.c#dup-key](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L563-L568)); an expression, predicate, or AM error in the second scan | **invalid, ready** index |
| After `index_set_state_flags(SET_VALID)` (transaction 4, before command-end commit) | an error or cancel after the in-place flip; concretely, a `ddl_command_end` event-trigger function can raise an error after `DefineIndex` returns ([utility.c#post-DefineIndex](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1384-L1393), [utility.c#DDL-end](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1701-L1719), [event_trigger.c#EventTriggerInvoke](../../../../raw/postgres-12/src/backend/commands/event_trigger.c#L1031-L1092)) | **valid** index — `SET_VALID` cannot roll back ([index.c#set-valid](../../../../raw/postgres-12/src/backend/catalog/index.c#L3314-L3366)) |

The final row is not theoretical. A temporary build of the exact pin reproduced
it with a `ddl_command_end` trigger that raised an exception for `CREATE INDEX`:
the client received an error, while the surviving index had
`(indislive, indisready, indisvalid) = (t,t,t)` and answered a forced index scan.
The result follows from the caller order above: `DefineIndex` performs the
non-transactional `SET_VALID`, releases its session lock, and returns before
utility dispatch invokes the command-end trigger
([indexcmds.c#after-valid](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1450-L1472),
[utility.c#post-DefineIndex](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1384-L1393),
[utility.c#DDL-end](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1701-L1719)).

The not-ready-vs-ready split is exactly the build-scan-vs-validation-scan split,
because `index_concurrently_build` sets `indisready` only after `index_build`
returns ([index.c#build-set-ready](../../../../raw/postgres-12/src/backend/catalog/index.c#L1426-L1438));
the second scan in `validate_index` runs in the next transaction, with
`indisready` already true.

#### Worked regression examples

- **Pre-existing duplicate fails the build (first scan).** With two `f2 = 'b'`
  rows present, `CREATE UNIQUE INDEX CONCURRENTLY concur_index3 ON concur_heap(f2)`
  errors `could not create unique index "concur_index3" ... Key (f2)=(b) is
  duplicated`
  ([create_index.out#concur_index3](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1383-L1385)),
  and `\d` later shows the index retained but `INVALID`
  ([create_index.out#invalid-listing](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1413-L1417)).
  The error comes from the build sort
  ([tuplesort.c#dup](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L4048-L4056)),
  i.e. before `indisready` is set, so this leftover is invalid **and not ready**.
- **The leftover survives maintenance.** `VACUUM FULL` keeps the invalid index,
  and `REINDEX TABLE` re-runs the same build and fails identically until the
  duplicate row is deleted
  ([create_index.out#vacuum-reindex](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1400-L1406)).
- **Repairing the leftover.** Once the underlying cause is gone, the invalid
  index can be rebuilt. The non-concurrent path shown in the suite is
  `REINDEX TABLE`: after the duplicate row is deleted, `REINDEX TABLE concur_heap`
  clears `concur_index3`'s `INVALID` marker
  ([create_index.out#reindex-repair](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1422-L1436)).
  Rebuilding it *concurrently* runs through `REINDEX INDEX CONCURRENTLY`, which
  builds a separate `_ccnew` copy and can itself stack another invalid index if
  the cause persists, then makes the index valid once the cause is gone
  ([create_index.out#cic-repair](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L2323-L2358)) — see
  [How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 12](reindex-index-concurrently.md).

#### A failed CIC does not leak its session lock

For ordinary ERROR/cancel paths, a failure before commit 1 leaves no index; a
failure after commit 1 and before `SET_VALID` leaves an invalid index. In either
case, the session-level `ShareUpdateExclusiveLock` is released.
`LockRelationIdForSession` is documented to be removed "if an `ereport(ERROR)` occurs"
([lmgr.c#session-lock-doc](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L356-L363)),
because main-transaction **abort** releases session locks too: `ProcReleaseLocks`
calls `LockReleaseAll(DEFAULT_LOCKMETHOD, !isCommit)`, and on abort `!isCommit` is
true
([proc.c#ProcReleaseLocks](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L772-L798)).
So a failed CIC never leaves a lock that blocks `VACUUM`, `ANALYZE`, DDL, or
another CIC on the table.

#### Server crash or immediate shutdown

A crash or `immediate`-mode shutdown can recover the same four catalog outcomes
as an ERROR or cancel: no index, invalid/not-ready, invalid/ready, or valid. WAL
replay cannot produce a half-applied flag flip. For the reviewed in-tree AMs, it
also cannot lose completed build data while retaining a later durable
`SET_VALID` record. This is a **crash-durability** statement, not a claim that
every valid v12 index is logically complete: the prepared-transaction defect
above can already create a valid-but-incomplete index before any crash.

An unclean stop leaves `pg_control` in a state other than `DB_SHUTDOWNED`, so the
next startup forces `InRecovery` and replays WAL automatically
([xlog.c#crash-recovery](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L6740-L6766)).
Recovery is pure physical WAL replay: the recovered `pg_index` flags are
whatever that replay produces, and v12 runs no CIC-aware repair pass. It neither
repairs an invalid interrupted build nor repairs the prepared-transaction gap;
the documented response to an interrupted invalid build is manual `DROP INDEX`
/ retry or `REINDEX`
([ref/create_index.sgml#invalid-index](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L574-L596)).

**Why a flip's durability is decoupled from its phase commit.**
`index_set_state_flags` runs with no assigned transaction id — it asserts
`GetTopTransactionIdIfAny() == InvalidTransactionId` — and writes the flag
through `heap_inplace_update`
([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403)).
`heap_inplace_update` overwrites the tuple in a critical section, emits one
`XLOG_HEAP_INPLACE` record, sets the page LSN, and returns **without** flushing
WAL
([heapam.c#heap_inplace_update](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L5746-L5774)).
Because the phase transaction holds no XID, `RecordTransactionCommit` writes no
commit record and takes the **asynchronous** branch — `XLogSetAsyncXactLSN`, not
`XLogFlush` — even under `synchronous_commit = on`; its own comment notes that
losing such a WAL-writing-but-xidless transaction on crash "will be irrelevant"
([xact.c#RecordTransactionCommit](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1232-L1392)).
`XLogSetAsyncXactLSN` only nudges the WAL writer
([xlog.c#XLogSetAsyncXactLSN](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2630-L2670)).
So a flip turns durable only once the WAL writer, a checkpoint, or a later
synchronous commit flushes WAL past its LSN — possibly well after
`CommitTransactionCommand` has already returned.

This cuts both ways, but safely:

- A flip can **survive even though its phase wrote no commit record**:
  `heap_xlog_inplace` redoes the byte overwrite physically and unconditionally
  whenever its record is durable
  ([heapam.c#heap_xlog_inplace](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L8797-L8835)).
  ("Will not roll back on error" concerns the ERROR path, where the surrounding
  transaction aborts but the in-place row stays; a crash only asks whether the
  record was durable.)
- A flip can be **lost even though the phase commit returned**, because that
  commit was asynchronous; recovery then shows the prior, more-conservative
  flag.

**The recovered state is monotone.** SET_READY (Txn 2) has a lower LSN than
SET_VALID (Txn 4)
([index.c#build-set-ready](../../../../raw/postgres-12/src/backend/catalog/index.c#L1426-L1438),
[indexcmds.c#set-valid](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1448-L1463)),
and `XLogFlush` flushes all WAL through a position
([xlog.c#XLogFlush](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2791-L2798)).
Durable SET_VALID therefore implies durable SET_READY, so recovered
`(indisready, indisvalid)` is always `(f,f)`, `(t,f)`, or `(t,t)`, never
`(f,t)`:

| Last record durable at crash | Recovered `pg_index` | Failure-table row |
|---|---|---|
| commit-1 catalog row not yet durable | (no row) | no index |
| catalog row only | `indislive=t, indisready=f, indisvalid=f` | invalid, not ready |
| + SET_READY (`XLOG_HEAP_INPLACE`) | `indisready=t, indisvalid=f` | invalid, ready |
| + SET_VALID (`XLOG_HEAP_INPLACE`) | `indisready=t, indisvalid=t` | valid |

**A durable `SET_VALID` cannot outrun completed in-tree build data.** This
claim assumes the index was logically complete when `SET_VALID` ran; it does
not erase the prepared-transaction defect. For the six core AMs and contrib
Bloom, two facts prevent a crash from turning an otherwise complete valid index
into an incomplete one.

First, `XLogFlush` flushes WAL through a position
([xlog.c#XLogFlush](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2791-L2798)).
A durable `SET_VALID` therefore makes every earlier WAL record durable too,
including the reviewed `validate_index` backfill insert paths. Those paths use
shared buffers, whose WAL-before-data rule flushes WAL through a buffer's page
LSN before writing that buffer to disk
([bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2712-L2736)).

Second, each in-tree first-build path makes its pages durable before the later
flag records can be durable:

- **B-tree builds outside shared buffers**, so a concurrent checkpoint cannot
  flush those pages. It `smgrimmedsync`s the index file before the build
  transaction may commit, and WAL-logs the built pages when `XLogIsNeeded()`
  and `RelationNeedsWAL()` are both true
  ([nbtsort.c#build-durability](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L34-L44),
  [nbtsort.c#use-wal](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L576-L580),
  [nbtsort.c#immedsync](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307)).
- **Hash, GiST, SP-GiST, GIN, and BRIN build through shared buffers** and
  WAL-log their pages. GiST, SP-GiST, and GIN emit a build-end
  `log_newpage_range` over the main fork
  ([gistbuild.c#build-wal](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L217-L226),
  [spginsert.c#build-wal](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L134-L143),
  [gininsert.c#build-wal](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L408-L417));
  hash and BRIN WAL-log through their ordinary buffered build paths
  ([hash.c#hashbuild](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L129-L168),
  [hashpage.c#_hash_init-wal](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L346-L402),
  [brin.c#build-wal](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L683-L709)).
- **Contrib Bloom also builds through shared buffers.** Its metapage and cached
  build pages use `GenericXLog` with full-page images, which sets each page LSN
  and marks each buffer dirty after inserting the WAL record
  ([blinsert.c#blbuild](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L44-L159),
  [blutils.c#BloomInitMetapage](../../../../raw/postgres-12/contrib/bloom/blutils.c#L445-L470),
  [generic_xlog.c#GenericXLogFinish](../../../../raw/postgres-12/src/backend/access/transam/generic_xlog.c#L328-L435)).

For these permanent in-tree indexes, `RelationNeedsWAL` is true
([rel.h#RelationNeedsWAL](../../../../raw/postgres-12/src/include/utils/rel.h#L515-L520)).
The ordering above means no crash window can lose their completed build or
backfill while preserving a later durable `SET_VALID`. Core code does not prove
that property for an arbitrary third-party AM: it delegates physical build and
insert durability to that AM's callbacks
([index.c#ambuild-dispatch](../../../../raw/postgres-12/src/backend/catalog/index.c#L2899-L2904),
[amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L160-L229)).

An **unlogged** table is reset to its empty init fork on crash recovery — heap
and indexes together — so recovery does not leave its index populated
inconsistently with its heap
([xlog.c#reset-unlogged-cleanup](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L6878-L6884),
[xlog.c#reset-unlogged-init](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L7323-L7331),
[reinit.c#ResetUnloggedRelations](../../../../raw/postgres-12/src/backend/storage/file/reinit.c#L36-L46)).

#### Recovery

The documented fix is to `DROP INDEX` (optionally `CONCURRENTLY`) the invalid
index and retry, or rebuild it with `REINDEX INDEX CONCURRENTLY`
([ref/create_index.sgml#invalid-index](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L574-L596)).
A `DROP INDEX CONCURRENTLY` that itself fails partway can simply be re-run: its
`INDEX_DROP_CLEAR_VALID` step deliberately does not assert its starting flags, so
the drop is retryable
([index.c#drop-clear-valid](../../../../raw/postgres-12/src/backend/catalog/index.c#L3367-L3383)).

### Test coverage

- `create_index.sql` builds empty-table, unique, expression, and partial indexes
  concurrently, defaults the index name, checks the explicit-transaction ban and
  temp-table ordering, and tests a failed unique build. Its own header warns
  that this covers only about half the paths because no concurrent updates run
  against the table
  ([create_index.sql#CIC-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L460-L525)).
- Separate regression blocks cover concurrent B-tree and GiST indexes with
  included columns
  ([index_including.sql#CIC](../../../../raw/postgres-12/src/test/regress/sql/index_including.sql#L161-L168),
  [index_including_gist.sql#CIC](../../../../raw/postgres-12/src/test/regress/sql/index_including_gist.sql#L37-L44)).
- `multiple-cic.spec` runs two CIC operations simultaneously on different tables
  and uses advisory-locking predicates to interleave their builds; the isolation
  schedule includes that spec
  ([multiple-cic.spec](../../../../raw/postgres-12/src/test/isolation/specs/multiple-cic.spec#L1-L40),
  [isolation_schedule:66](../../../../raw/postgres-12/src/test/isolation/isolation_schedule#L66)).
- Failure outcomes are exercised too: `create_index.sql` builds a unique index
  concurrently over duplicate rows and checks that the failed build is left
  `INVALID`, survives `VACUUM FULL`, and is repaired only after the duplicate is
  removed
  ([create_index.out#concurrent-invalid](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1382-L1436)).
- A whole-checkout search of executable test inputs found no direct CIC test for
  hash, GIN, SP-GiST, BRIN, or contrib Bloom; no prepared-transaction/CIC test;
  no command-end-event-trigger failure after `SET_VALID`; and no crash or
  immediate-shutdown CIC recovery test. Bloom's own SQL uses only plain
  `CREATE INDEX`
  ([bloom.sql#index-builds](../../../../raw/postgres-12/contrib/bloom/sql/bloom.sql#L1-L95)).
  The exact-pin temporary reproductions described above cover the prepared-write
  gap and the late event-trigger error, but not crash timing.

## Context Reviewed

- `wiki/versions.md`, `wiki/index.md`, `wiki/v12/index.md`, and the last ~20
  `wiki/log.md` entries (navigation only).
- Pinned checkout `raw/postgres-12/` at commit
  `45b88269a353ad93744772791feb6d01bc7e1e42` ("Stamp 12.2.").
- Parser and generated-artifact path: `IndexStmt` grammar in
  `src/backend/parser/gram.y`, `IndexStmt` in `src/include/nodes/parsenodes.h`,
  generated grammar targets in `src/backend/parser/Makefile`, `pg_index.h` as a
  catalog-generator input, and the `genbki.pl` / catalog Makefile path that emits
  `pg_index_d.h`.
- Utility caller boundary in `src/backend/tcop/utility.c`, including
  `ddl_command_start`, the `T_IndexStmt` transform/lock/`DefineIndex` dispatch,
  post-`DefineIndex` command collection, and `ddl_command_end`; event-trigger
  function invocation in `src/backend/commands/event_trigger.c`.
- `DefineIndex` concurrent branch and `WaitForOlderSnapshots` in
  `src/backend/commands/indexcmds.c`.
- `pg_index` flag declarations in `src/include/catalog/pg_index.h`;
  `index_create`/`UpdateIndexRelation`, `BuildIndexInfo`,
  `index_concurrently_build`, `validate_index`, and `index_set_state_flags` in
  `src/backend/catalog/index.c`.
- Index-AM boundary: `IndexAmRoutine` in `src/include/access/amapi.h`, AM
  dispatch in `src/backend/access/index/indexam.c`, the AM contract in
  `doc/src/sgml/indexam.sgml`, all six core `ambuild` paths, and contrib Bloom's
  handler/build/`GenericXLog` paths in `contrib/bloom/` plus
  `src/backend/access/transam/generic_xlog.c`.
- Surrounding command-end commit path in `finish_xact_command` in
  `src/backend/tcop/postgres.c`.
- `WaitForLockers`/`WaitForLockersMultiple` in
  `src/backend/storage/lmgr/lmgr.c`; the `LockConflicts` table and self-conflict
  note in `src/backend/storage/lmgr/lock.c`; lock-mode definitions in
  `src/include/storage/lockdefs.h`.
- `PreventInTransactionBlock` dispatch in `src/backend/tcop/utility.c`.
- `doc/src/sgml/ref/create_index.sgml` (CONCURRENTLY narrative).
- For the blocking-operations section: `GetLockConflicts` in
  `src/backend/storage/lmgr/lock.c`; `GetCurrentVirtualXIDs` in
  `src/backend/storage/ipc/procarray.c`; the autovacuum-cancel branch of
  `ProcSleep` in `src/backend/storage/lmgr/proc.c`; `vacuumFlags` in
  `src/include/storage/proc.h`; `MarkAsPreparingGuts` in
  `src/backend/access/transam/twophase.c`; `GetTransactionSnapshot` in
  `src/backend/utils/time/snapmgr.c`; the lock-mode/command table in
  `doc/src/sgml/mvcc.sgml`; the `pg_stat_progress_create_index` phase table in
  `doc/src/sgml/monitoring.sgml`; predicate/expression evaluation and the
  advisory-locking `multiple-cic` test; B-tree validation waits in `nbtinsert.c`;
  and parallel B-tree worker waits in `nbtsort.c`.
- For the worked examples: the dump-transaction setup, timeout disabling, and
  `LOCK TABLE ... IN ACCESS SHARE MODE` statements in
  `src/bin/pg_dump/pg_dump.c`; `SnapshotResetXmin` in
  `src/backend/utils/time/snapmgr.c`; and portal/cursor snapshot registration
  and execution in `src/backend/tcop/pquery.c`.
- For the failure-scenarios section: the planner's invalid-index skip in
  `src/backend/optimizer/util/plancat.c`; `ExecOpenIndices` /
  `ExecInsertIndexTuples` ready-for-inserts handling in
  `src/backend/executor/execIndexing.c`; `RelationGetIndexList` index-list
  filtering and HOT-attribute collection in
  `src/backend/utils/cache/relcache.c`; the unique-violation `ereport`s in
  `src/backend/utils/sort/tuplesort.c` (build sort) and
  `src/backend/access/nbtree/nbtinsert.c` (`_bt_check_unique`); `index_drop` and
  the `INDEX_DROP_*` branches of `index_set_state_flags` in
  `src/backend/catalog/index.c`;
  `heap_inplace_update` in `src/backend/access/heap/heapam.c`;
  `LockRelationIdForSession` in
  `src/backend/storage/lmgr/lmgr.c` and `ProcReleaseLocks` in
  `src/backend/storage/lmgr/proc.c`; the post-`SET_VALID` caller path through
  `ddl_command_end`; and the invalid-index regression evidence in
  `src/test/regress/expected/create_index.out`.
- For the crash / immediate-shutdown recovery trace: `heap_inplace_update` and
  its redo `heap_xlog_inplace` (`XLOG_HEAP_INPLACE`) in
  `src/backend/access/heap/heapam.c`; the xidless-transaction asynchronous-commit
  path of `RecordTransactionCommit` in `src/backend/access/transam/xact.c`;
  `XLogFlush`, `XLogSetAsyncXactLSN`, and the `StartupXLOG` crash-recovery
  determination in `src/backend/access/transam/xlog.c`; the WAL-before-data rule
  in `FlushBuffer` in `src/backend/storage/buffer/bufmgr.c`; the B-tree build's
  WAL gating and final `smgrimmedsync` in
  `src/backend/access/nbtree/nbtsort.c`; the through-shared-buffers build and
  build-end WAL of the other core AMs (`gistbuild`/`spgbuild`/`ginbuild`
  `log_newpage_range`, `hashbuild`/`_hash_init`, and `brinbuild`) under
  `src/backend/access/{gist,spgist,gin,hash,brin}/`; contrib Bloom's
  shared-buffer `GenericXLog` build; the `index_concurrently_build` SET_READY and
  `DefineIndex` SET_VALID commit boundaries in `src/backend/catalog/index.c` and
  `src/backend/commands/indexcmds.c`; the `RelationNeedsWAL` macro in
  `src/include/utils/rel.h`; the third-party-AM boundary; and the crash-recovery
  unlogged-relation reset (`ResetUnloggedRelations` CLEANUP/INIT calls in
  `StartupXLOG`) in `src/backend/access/transam/xlog.c` and
  `src/backend/storage/file/reinit.c`.
- Tests: `src/test/regress/sql/create_index.sql`, concurrent-INCLUDE blocks in
  `index_including.sql` and `index_including_gist.sql`,
  `src/test/isolation/specs/multiple-cic.spec`, its expected output and schedule,
  plus a whole-checkout executable-test-input search for the explicitly recorded
  CIC coverage absences.
- Exact-pin temporary-build reproductions kept under `.wiki-runtime/`: the
  prepared-`INSERT` gap (valid index scan returned zero, forced sequential scan
  returned one after `COMMIT PREPARED`) and a failing `ddl_command_end` trigger
  (command error with a surviving valid, ready, live index). No crash timing was
  reproduced.
- Source history at and before the pin: the original CIC implementation
  (`e093dcdd2853`), VXID-based waiting foundation (`295e63983d75`), the
  `indislive`/in-place-state fix (`3c84046490be`), the no-advertised-`xmin`
  transaction boundary (`1dec82068b3b`), and progress reporting
  (`ab0dfc961b6a`); each commit is an ancestor of the pin.
- For the inter-builder follow-up: the `ReindexRelationConcurrently` adjacent
  caller in `src/backend/commands/indexcmds.c`; the `GetCurrentVirtualXIDs`
  filter contract in `src/backend/storage/ipc/procarray.c`; the v12
  `vacuumFlags` definitions in `src/include/storage/proc.h`; and a whole-checkout
  search confirming `PROC_IN_SAFE_IC` is absent in the pinned v12 source.
- For the first-build-scan tuple-visibility trace: `index_concurrently_build`
  and `index_build` in `src/backend/catalog/index.c`; the `ambuild` heap-scan
  callers and the B-tree serial/parallel build helpers in `nbtsort.c`, plus
  `hash.c`, `gistbuild.c`, `spginsert.c`, `gininsert.c`, and `brin.c` under
  `src/backend/access/`; the `table_index_build_scan` inline wrapper and
  `index_build_range_scan` callback in `src/include/access/tableam.h`;
  `heapam_index_build_range_scan` and the `TableAmRoutine` registration in
  `src/backend/access/heap/heapam_handler.c`; `heapgetpage` in
  `src/backend/access/heap/heapam.c`; `HeapTupleSatisfiesVisibility` /
  `HeapTupleSatisfiesMVCC` in `src/backend/access/heap/heapam_visibility.c`;
  the `SNAPSHOT_MVCC` contract in `src/include/utils/snapshot.h`; the
  build-snapshot setup in `DefineIndex` in
  `src/backend/commands/indexcmds.c`; and the `validate_index` header comment
  in `src/backend/catalog/index.c`.
- For the prepared-transaction writer-wait safety assessment: the
  `validate_index` correctness narrative and the Wait 1 HOT-safety comment in
  `src/backend/catalog/index.c` and `src/backend/commands/indexcmds.c`;
  `GetLockConflicts`'s invalid-VXID skip (fast-path and primary-table loops) in
  `src/backend/storage/lmgr/lock.c`; `MarkAsPreparingGuts` and
  `FinishPreparedTransaction` in `src/backend/access/transam/twophase.c`; the
  prepared-xacts-in-the-proc-array note in
  `src/backend/storage/ipc/procarray.c`; the `SnapshotAny`
  `INSERT_IN_PROGRESS` branch versus the MVCC `else` branch in
  `heapam_index_build_range_scan` in
  `src/backend/access/heap/heapam_handler.c`; and the not-ready-index insert
  skip in `src/backend/executor/execIndexing.c`.
- For the walsender / replication-slot Wait 3 assessment: `GetCurrentVirtualXIDs`
  versus `GetOldestXmin` versus `GetSnapshotData`, the
  `replication_slot_xmin`/`replication_slot_catalog_xmin` global fields, and
  `ProcArrayEndTransaction`/`ProcArraySetReplicationSlotXmin` in
  `src/backend/storage/ipc/procarray.c`; `ReplicationSlotsComputeRequiredXmin`
  in `src/backend/replication/slot.c`; `ProcessStandbyHSFeedbackMessage` and
  `PhysicalReplicationSlotNewXmin` in `src/backend/replication/walsender.c`; the
  physical-walsender no-database early return in `InitPostgres` in
  `src/backend/utils/init/postinit.c` and the `InitProcess` `databaseId`
  initialization in `src/backend/storage/lmgr/proc.c`; the
  `VirtualTransactionIdIsValid`/`GET_VXID_FROM_PGPROC` macros in
  `src/include/storage/lock.h`; `StartTransaction`'s `lxid` assignment in
  `src/backend/access/transam/xact.c`; `SnapBuildInitialSnapshot` in
  `src/backend/replication/logical/snapbuild.c`; and the `replication=database`
  startup-packet parsing in `src/backend/postmaster/postmaster.c`.
- For the `maintenance_work_mem` follow-up: the GUC definition, `SET` lifetime,
  exported global, defaults, and docs in `guc.c`, `set.sgml`, `miscadmin.h`,
  `config.sgml`, and `create_index.sgml`; GUC serialization/restoration in
  `parallel.c`; `Tuplesortstate` accounting, its 64 kB floor, in-memory/external
  transitions, run/merge trace messages, participant output, leader takeover,
  and memory release in `tuplesort.c`; B-tree `BTSpool`, `BTShared`, `BTLeader`,
  planned-versus-launched shares, zero-worker fallback, unique secondary spool,
  and coordinator merge in `nbtsort.c`; worker planning in `planner.c` and
  `allpaths.c`; hash sort selection in `hash.c`/`hashsort.c`; GiST buffered-build
  state and temporary `BufFile` in `gistbuild.c`/`gistbuildbuffers.c`; GIN
  `BuildAccumulator`, soft build flushes, the empty and batched validation
  pending-list paths, and posting-list callbacks in `gininsert.c`, `ginbulk.c`,
  `ginfast.c`, and `ginvacuum.c`; the SP-GiST, BRIN, and contrib Bloom build and
  validation callbacks; BRIN's no-op enumeration plus validation heap scan; the
  `ambuild_function` API and generated `BTREE_AM_OID` boundaries; progress and
  temp counters plus their tracking prerequisites in `monitoring.sgml`,
  `pgstat.c`, and `fd.c`; `trace_sort` and `log_temp_files`; and a whole-checkout
  executable-test search including `create_index.sql`, `cluster.sql`, the CIC
  INCLUDE tests, and `multiple-cic.spec`. Commit objects, subjects, changed paths,
  and ancestry were checked for parallel B-tree build commit `9da0cc35284`,
  faster encoded-TID validation sort commit `b648b70342f`, the original hash
  pre-sort commit `787eba734be`, and the current hash memory/buffer threshold plus
  regression commit `9563d5b5e4c`; missing historical blobs in the promisor
  checkout were not fetched. The pinned current source independently supports
  the behavioral claims, and each named commit is an ancestor of the pin.
- For the broader performance-GUC follow-up: whole-checkout use-site searches
  for build, parallelism, heap I/O, storage, GIN, WAL, checkpoint, commit,
  timeout, and observability settings; their definitions, defaults, and apply
  contexts in `src/backend/utils/misc/guc.c`; and `SET` plus parallel-worker GUC
  lifetime in `ref/set.sgml` and `parallel.c`.
- Parallel request and launch paths in `planner.c`, `allpaths.c`, `bgworker.c`,
  and `nbtsort.c`; heap scan strategy and synchronization in `heapam.c`,
  `heapam_handler.c`, `tableam.c`, and `freelist.c`; index and temporary
  tablespace selection in `indexcmds.c`, `tuplesort.c`, `sharedfileset.c`, and
  `fd.c`; and backend writeback in `buf_init.c`/`bufmgr.c`.
- WAL and commit paths in `nbtsort.c`, the other in-tree AM build callbacks,
  `generic_xlog.c`, `xloginsert.c`, `xlog.c`, `xact.c`, and `syncrep.c`, plus
  checkpoint and durability documentation in `config.sgml`. Lock and timeout
  paths in `utility.c`, `lmgr.c`, `lock.c`, `proc.c`, and `postgres.c`.
- Whole-checkout definition searches confirmed that PostgreSQL 12 has no
  `transaction_timeout`, `maintenance_io_concurrency`, `io_combine_limit`,
  `track_wal_io_timing`, or `wal_skip_threshold`. Direct CIC regression and
  isolation inputs were checked and do not sweep the broader GUC matrix.
- Build boundary for the registry: `src/backend/utils/misc/Makefile` compiles
  the handwritten `guc.c` registry and makes `guc.o` depend on the generated
  `guc-file.c` configuration-file scanner.

## Evidence Map

| Claim | Source |
|---|---|
| Grammar sets `IndexStmt.concurrent`; parser C/header and `pg_index_d.h` are generated build artifacts | [gram.y:7333-7407](../../../../raw/postgres-12/src/backend/parser/gram.y#L7333-L7407), [parsenodes.h:2738-2775](../../../../raw/postgres-12/src/include/nodes/parsenodes.h#L2738-L2775), [parser/Makefile:15-54](../../../../raw/postgres-12/src/backend/parser/Makefile#L15-L54), [pg_index.h:12-29](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L12-L29), [catalog/Makefile:28-99](../../../../raw/postgres-12/src/backend/catalog/Makefile#L28-L99), [genbki.pl:368-398](../../../../raw/postgres-12/src/backend/catalog/genbki.pl#L368-L398) |
| Utility dispatch runs DDL-start before relation locking and DDL-end after `DefineIndex` returns | [utility.c:960-975](../../../../raw/postgres-12/src/backend/tcop/utility.c#L960-L975), [utility.c:1301-1393](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1301-L1393), [utility.c:1701-1719](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1701-L1719) |
| Core delegates physical build/validation to `IndexAmRoutine`; contrib Bloom uses the same phase machinery through its own shared-buffer/`GenericXLog` callbacks | [index.c:2899-2904](../../../../raw/postgres-12/src/backend/catalog/index.c#L2899-L2904), [indexam.c:165-189](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L165-L189), [indexam.c:672-693](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L672-L693), [amapi.h:160-229](../../../../raw/postgres-12/src/include/access/amapi.h#L160-L229), [blinsert.c:44-159](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L44-L159), [generic_xlog.c:328-435](../../../../raw/postgres-12/src/backend/access/transam/generic_xlog.c#L328-L435) |
| The memory value is a handwritten global, while the B-tree-only parallel gate uses generated `BTREE_AM_OID` catalog metadata | [miscadmin.h:243-247](../../../../raw/postgres-12/src/include/miscadmin.h#L243-L247), [index.c:2844-2854](../../../../raw/postgres-12/src/backend/catalog/index.c#L2844-L2854), [pg_am.dat:18-20](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L20), [catalog/Makefile:32-69](../../../../raw/postgres-12/src/backend/catalog/Makefile#L32-L69) |
| `maintenance_work_mem` is a 64 MB-default, 1 MB-minimum, kilobyte `PGC_USERSET` GUC; it needs no reload/restart. A session `SET` persists across CIC's commits, while `SET LOCAL` cannot enclose CIC; parallel workers restore the leader's serialized GUC state | [guc.c:2243-2252](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2243-L2252), [config.sgml:1686-1712](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1686-L1712), [set.sgml:33-115](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L33-L115), [utility.c:1305-1309](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1305-L1309), [parallel.c:349-352](../../../../raw/postgres-12/src/backend/access/transam/parallel.c#L349-L352), [parallel.c:1358-1361](../../../../raw/postgres-12/src/backend/access/transam/parallel.c#L1358-L1361) |
| CIC can use the budget in two sequential phases: AMs differ on whether the first build reads it, while validation passes the full value to a serial TID sort; GIN also selects it for forced cleanup, but allocates cleanup state only for a nonempty pending list | [index.c:1399-1438](../../../../raw/postgres-12/src/backend/catalog/index.c#L1399-L1438), [indexcmds.c:1366-1412](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1366-L1412), [index.c:3228-3283](../../../../raw/postgres-12/src/backend/catalog/index.c#L3228-L3283), [ginvacuum.c:563-594](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L563-L594), [ginfast.c:807-840](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L807-L840) |
| B-tree uses the GUC as its intended primary-sort budget; automatic planning requires 32 MB per planned participant, runtime launch failures redistribute an absent worker's share only to the normal leader worker-role sort, zero launches fall back to serial, and every actual participant emits one required tape run | [nbtsort.c:378-445](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L378-L445), [planner.c:6257-6362](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6257-L6362), [nbtsort.c:177-205](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L177-L205), [nbtsort.c:1328-1485](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1328-L1485), [nbtsort.c:1595-1605](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1595-L1605), [nbtsort.c:1693-1696](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1693-L1696), [tuplesort.c:1802-1833](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1802-L1833), [tuplesort.c:4510-4561](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L4510-L4561) |
| Memory cannot remove the validation scans: B-tree's enumeration visits every index page and every leaf item, while BRIN's no-op enumeration skips its index scan but not the following heap scan | [nbtree.c:848-1041](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L848-L1041), [nbtree.c:1197-1270](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1197-L1270), [brin.c:766-784](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L766-L784), [heapam_handler.c:1768-1934](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1768-L1934) |
| Hash uses the GUC for a buffer-capped path-selection proxy and sort memory; GiST uses it in the enabled buffering `levelStep` calculation but also has non-monotonic CPU/temp-file tradeoffs; GIN checks its soft accumulator-flush threshold after each heap tuple | [hash.c:126-177](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L126-L177), [hashsort.c:54-90](../../../../raw/postgres-12/src/backend/access/hash/hashsort.c#L54-L90), [gistbuild.c:312-417](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L312-L417), [gistbuildbuffers.c:48-62](../../../../raw/postgres-12/src/backend/access/gist/gistbuildbuffers.c#L48-L62), [gist.sgml:962-993](../../../../raw/postgres-12/doc/src/sgml/gist.sgml#L962-L993), [gininsert.c:245-314](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L245-L314) |
| Either GIN accumulator can hit the extreme posting-list growth error, which explicitly hints to reduce `maintenance_work_mem` | [ginbulk.c:28-51](../../../../raw/postgres-12/src/backend/access/gin/ginbulk.c#L28-L51), [ginfast.c:859-904](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L859-L904) |
| SP-GiST, BRIN, and contrib Bloom do not read the GUC during first build. SP-GiST and Bloom enumerate validation TIDs; BRIN's no-op `ambulkdelete` leaves the sort empty, though the validation heap scan still runs | [spginsert.c:71-149](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L71-L149), [spgvacuum.c:147-168](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L147-L168), [spgvacuum.c:893-916](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L893-L916), [brin.c:658-784](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L658-L784), [heapam_handler.c:1768-1934](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1768-L1934), [blinsert.c:35-159](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L35-L159), [blvacuum.c:26-107](../../../../raw/postgres-12/contrib/bloom/blvacuum.c#L26-L107) |
| A serial tuplesort moves from one in-memory quicksort to temporary runs and merges when charged memory is exhausted; once all input fits, more memory does not change that sort path | [tuplesort.c:1-75](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1-L75), [tuplesort.c:1641-1700](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1641-L1700), [tuplesort.c:1786-1866](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1786-L1866) |
| No universal plateau follows from index size: build tuple widths vary, validation sorts encoded TIDs, GIN may report one heap TID under several keys, and BRIN reports none | [tuplesort.c:138-175](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L138-L175), [index.c:3239-3248](../../../../raw/postgres-12/src/backend/catalog/index.c#L3239-L3248), [ginvacuum.c:47-83](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L47-L83), [gin/README:17-26](../../../../raw/postgres-12/src/backend/access/gin/README#L17-L26), [brin.c:766-784](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L766-L784) |
| Progress phases require `track_activities` and expose no sort-space or participant field. `trace_sort` reveals runs/merges; final temp-file sizes and `temp_bytes` require `track_counts` and measure file volume, not cumulative I/O. GiST can add its own temporary file | [monitoring.sgml:3488-3704](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3488-L3704), [pgstat.c:3192-3259](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L3192-L3259), [tuplesort.c:1225-1279](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1225-L1279), [tuplesort.c:2837-2841](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L2837-L2841), [tuplesort.c:2924-3022](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L2924-L3022), [fd.c:1272-1287](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1272-L1287), [pgstat.c:1560-1576](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L1560-L1576), [pgstat.c:6397-6412](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6397-L6412), [gistbuildbuffers.c:48-62](../../../../raw/postgres-12/src/backend/access/gist/gistbuildbuffers.c#L48-L62) |
| A whole-checkout test-input search found one direct `CREATE INDEX` setting case (nonconcurrent hash), a separate CLUSTER case whose implementation rebuilds indexes, and no CIC memory, spill, worker-threshold, or plateau test | [create_index.sql:379-387](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L379-L387), [cluster.sql:207-225](../../../../raw/postgres-12/src/test/regress/sql/cluster.sql#L207-L225), [cluster.c:1374-1410](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1374-L1410), [create_index.sql:460-525](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L460-L525), [index_including.sql:161-168](../../../../raw/postgres-12/src/test/regress/sql/index_including.sql#L161-L168), [index_including_gist.sql:37-44](../../../../raw/postgres-12/src/test/regress/sql/index_including_gist.sql#L37-L44), [multiple-cic.spec:1-40](../../../../raw/postgres-12/src/test/isolation/specs/multiple-cic.spec#L1-L40) |
| CIC's automatic B-tree worker request uses the heap-size threshold, maintenance-worker cap, and 32 MB participant shares; actual launch is then limited by the parallel-worker and background-worker pools | [planner.c:6226-6362](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6226-L6362), [allpaths.c:3562-3653](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L3562-L3653), [bgworker.c:931-1005](../../../../raw/postgres-12/src/backend/postmaster/bgworker.c#L931-L1005), [nbtsort.c:1396-1485](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1396-L1485) |
| `shared_buffers` changes the heap bulk-read/sync threshold and ring cap plus hash build's sort threshold; first-build synchronized scans are AM-dependent, and validation disables synchronization | [heapam.c:233-296](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L296), [freelist.c:537-587](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L537-L587), [hash.c:132-159](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L132-L159), [heapam_handler.c:1751-1763](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1751-L1763) |
| `temp_tablespaces` places sort/parallel/GiST files, `temp_file_limit` errors per process, `default_tablespace` places an index without explicit `TABLESPACE`, and `backend_flush_after` controls backend writeback advice | [tuplesort.c:2468-2475](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L2468-L2475), [sharedfileset.c:36-68](../../../../raw/postgres-12/src/backend/storage/file/sharedfileset.c#L36-L68), [gistbuildbuffers.c:44-62](../../../../raw/postgres-12/src/backend/access/gist/gistbuildbuffers.c#L44-L62), [fd.c:1933-1958](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1933-L1958), [indexcmds.c:658-675](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L658-L675), [bufmgr.c:1088-1156](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1088-L1156) |
| GiST uniquely reads `effective_cache_size`; GIN writer sessions can shape the pending list inherited by validation through `gin_pending_list_limit` and `work_mem` | [gistbuild.c:311-417](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L311-L417), [gin_private.h:21-39](../../../../raw/postgres-12/src/include/access/gin_private.h#L21-L39), [ginfast.c:438-461](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L438-L461), [ginfast.c:807-828](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L807-L828), [ginvacuum.c:563-594](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L563-L594) |
| PostgreSQL 12 CIC heap passes have no read-stream layer and do not call the bitmap/deletion-horizon prefetch paths that read `effective_io_concurrency` | [heapam_handler.c:1212-1247](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1212-L1247), [heapam_handler.c:1751-1772](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1751-L1772), [nodeBitmapHeapscan.c:797-817](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L797-L817), [heapam.c:6970-7040](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L6970-L7040), [index.c:3300-3312](../../../../raw/postgres-12/src/backend/catalog/index.c#L3300-L3312) |
| CIC's WAL path exposes forced-image compression, B-tree's `wal_level` gate and immediate sync, generic WAL/checkpoint controls, and XID-bearing versus xidless phase-commit behavior | [nbtsort.c:576-662](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L576-L662), [nbtsort.c:1288-1307](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307), [xloginsert.c:539-630](../../../../raw/postgres-12/src/backend/access/transam/xloginsert.c#L539-L630), [xact.c:1206-1426](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1206-L1426), [syncrep.c:131-182](../../../../raw/postgres-12/src/backend/replication/syncrep.c#L131-L182) |
| `statement_timeout` spans CIC; `lock_timeout` restarts per table/VXID lock acquisition; deadlock settings detect/log lock waits; idle-transaction timeout acts in a blocker session | [postgres.c:2546-2578](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2546-L2578), [lock.c:4361-4458](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L4361-L4458), [proc.c:1229-1298](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1229-L1298), [proc.c:1377-1469](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1377-L1469), [postgres.c:4126-4152](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4126-L4152) |
| v12's handwritten GUC registry has no `transaction_timeout`, `maintenance_io_concurrency`, `io_combine_limit`, `track_wal_io_timing`, or `wal_skip_threshold`; `guc.o` depends on the generated configuration-file scanner | [guc.c:2377-2407](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2407), [guc.c:2759-2786](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2759-L2786), [guc.c:1381-1408](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1381-L1408), [utils/misc/Makefile:17-33](../../../../raw/postgres-12/src/backend/utils/misc/Makefile#L17-L33) |
| Table lock is `ShareUpdateExclusiveLock` for concurrent, `ShareLock` otherwise | [indexcmds.c:563-564](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L563-L564), [utility.c:1320-1321](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1320-L1321) |
| CIC cannot run in a transaction block | [utility.c:1307-1309](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1307-L1309) |
| Temp tables fall back to non-concurrent only after the utility transaction-block check; `CONCURRENTLY` on a temp table inside `BEGIN` still errors | [utility.c:1307-1309](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1307-L1309), [indexcmds.c:489-499](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L489-L499), [create_index.sql:504-525](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L504-L525) |
| `IF NOT EXISTS` name collision exits before the four concurrent phases | [index.c:844-859](../../../../raw/postgres-12/src/backend/catalog/index.c#L844-L859), [indexcmds.c:1025-1034](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1025-L1034) |
| Partitioned / system-catalog / exclusion restrictions | [indexcmds.c:604-616](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L604-L616), [index.c:813-817](../../../../raw/postgres-12/src/backend/catalog/index.c#L813-L817), [index.c:823-826](../../../../raw/postgres-12/src/backend/catalog/index.c#L823-L826) |
| `pg_index` state flags mean valid-for-queries / ready-for-inserts / alive-at-all; initial CIC row is live but not ready or valid | [pg_index.h:40-43](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L40-L43), [index.c:612-615](../../../../raw/postgres-12/src/backend/catalog/index.c#L612-L615), [index.c:990-996](../../../../raw/postgres-12/src/backend/catalog/index.c#L990-L996) |
| `indislive` controls whether backends may touch the index at all and whether it participates in HOT-safety decisions | [relcache.c:4388-4395](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4388-L4395), [relcache.c:4861-4870](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4861-L4870) |
| `indisready` gates executor insertion into an index; `indisvalid` gates planner use | [index.c:2337-2339](../../../../raw/postgres-12/src/backend/catalog/index.c#L2337-L2339), [execIndexing.c:328-332](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L328-L332), [plancat.c:199-210](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L199-L210) |
| CIC uses four transactions; the first three boundaries are explicit in `DefineIndex`, and the final one commits at utility command end | [indexcmds.c:1307-1472](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1472), [postgres.c:2569-2578](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2569-L2578) |
| Transaction 1 creates catalog rows and skips the AM build until a later phase | [indexcmds.c:974-986](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L974-L986), [indexcmds.c:1005-1014](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1005-L1014), [index.c:1198-1222](../../../../raw/postgres-12/src/backend/catalog/index.c#L1198-L1222) |
| Catalog visibility plus Wait 1 makes future transactions include the new index in HOT-safety decisions before it is ready for inserts | [indexcmds.c:1295-1304](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1295-L1304), [indexcmds.c:1348-1363](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1348-L1363) |
| Transaction-level heap locks are acquired at command start/build/validate and released at commit; the session-level heap lock spans transaction gaps and is released at the end | [indexcmds.c:550-564](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L550-L564), [index.c:1407-1414](../../../../raw/postgres-12/src/backend/catalog/index.c#L1407-L1414), [index.c:3203-3206](../../../../raw/postgres-12/src/backend/catalog/index.c#L3203-L3206), [proc.c:772-798](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L772-L798), [indexcmds.c:1307-1319](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1319), [lmgr.c:356-389](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L356-L389), [indexcmds.c:1465-1468](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1465-L1468) |
| Wait 1 / build / set indisready (txn 2) | [indexcmds.c:1328-1379](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1328-L1379), [index.c:1399-1439](../../../../raw/postgres-12/src/backend/catalog/index.c#L1399-L1439) |
| Wait 2 / reference snapshot / validate (txn 3) | [indexcmds.c:1382-1424](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1382-L1424), [index.c:3176-3298](../../../../raw/postgres-12/src/backend/catalog/index.c#L3176-L3298) |
| Wait 3 gathers same-database VXIDs with advertised `xmin <= limitXmin`, excluding autovacuum/lazy VACUUM, then sets `indisvalid` and invalidates the heap relcache | [indexcmds.c:307-402](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L307-L402), [procarray.c:2471-2540](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2471-L2540), [indexcmds.c:1437-1472](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1437-L1472) |
| `index_set_state_flags` is non-transactional in-place | [index.c:3331-3403](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403) |
| `WaitForLockers` waits on current holders' VXIDs, takes no table lock, and does not report lock waiters; `ShareLock` conflicts with `RowExclusiveLock` | [lmgr.c:850-949](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L850-L949), [lock.c:2804-2821](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2804-L2821), [lock.c:83-86](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L83-L86) |
| `ShareUpdateExclusiveLock` allows `AccessShareLock`, `RowShareLock`, and `RowExclusiveLock`, conflicts with schema-maintenance lock modes, and is self-conflicting | [lock.c:78-81](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L78-L81), [lock.c:194-196](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L194-L196), [lockdefs.h:36-46](../../../../raw/postgres-12/src/include/storage/lockdefs.h#L36-L46), [mvcc.sgml:890-1039](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L890-L1039) |
| Wait 3 excludes autovacuum and lazy VACUUM only; v12 has no safe-CIC exclusion in that mask | [indexcmds.c:307-402](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L307-L402), [proc.h:53-63](../../../../raw/postgres-12/src/include/storage/proc.h#L53-L63) |
| Same-table concurrent index builds serialize on self-conflicting `ShareUpdateExclusiveLock` | [indexcmds.c:563-564](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L563-L564), [indexcmds.c:1307-1316](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1307-L1316), [lock.c:78-81](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L78-L81), [ref/create_index.sgml:614-621](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L614-L621) |
| Different-table concurrent builders can meet in the same-database old-snapshot wait, while Waits 1/2 remain heap-lock-tag-local | [indexcmds.c:1328-1346](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1328-L1346), [indexcmds.c:1381-1389](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1381-L1389), [lmgr.c:850-860](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L850-L860), [indexcmds.c:307-348](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L307-L348), [procarray.c:2471-2540](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2471-L2540) |
| CIC clears its own advertised xmin before Wait 3 to avoid inter-CIC deadlock | [indexcmds.c:1414-1448](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1414-L1448) |
| `REINDEX CONCURRENTLY` uses analogous heap/index `ShareUpdateExclusiveLock` locks, saved heap lock tags for writer waits, and the same concurrent-build snapshot-wait boundary | [indexcmds.c:2957-3077](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2957-L3077), [indexcmds.c:3080-3198](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3080-L3198) |
| `multiple-cic` tests two simultaneous CIC commands on different tables; the visible wait is advisory-lock-induced, and the second CIC still completes while the first is open | [multiple-cic.spec:1-40](../../../../raw/postgres-12/src/test/isolation/specs/multiple-cic.spec#L1-L40), [multiple-cic.out:3-19](../../../../raw/postgres-12/src/test/isolation/expected/multiple-cic.out#L3-L19) |
| The four core synchronization barriers are not every backend wait: predicates can take advisory locks, unique validation can wait for transactions/speculative inserts, and parallel B-tree build waits for workers | [multiple-cic.spec:3-40](../../../../raw/postgres-12/src/test/isolation/specs/multiple-cic.spec#L3-L40), [heapam_handler.c:1873-1934](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1873-L1934), [nbtinsert.c:252-274](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L252-L274), [nbtsort.c:1473-1561](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1473-L1561) |
| Correctness narrative (two scans, three waits) | [index.c:3112-3174](../../../../raw/postgres-12/src/backend/catalog/index.c#L3112-L3174), [ref/create_index.sgml:545-572](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L545-L572) |
| First build scan sets `ii_Concurrent` then builds via `index_build` -> `ambuild`; serial core AM paths call `table_index_build_scan` directly, and B-tree parallel workers call it with a parallel heap scan descriptor | [index.c:1421-1427](../../../../raw/postgres-12/src/backend/catalog/index.c#L1421-L1427), [index.c:2902-2903](../../../../raw/postgres-12/src/backend/catalog/index.c#L2902-L2903), [index.c:2844-2854](../../../../raw/postgres-12/src/backend/catalog/index.c#L2844-L2854), [nbtsort.c:487-494](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L487-L494), [nbtsort.c:1779-1786](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1779-L1786), [hash.c:166](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L166), [gistbuild.c:196](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L196), [spginsert.c:126](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L126), [gininsert.c:382](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L382), [brin.c:723](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L723) |
| `table_index_build_scan` passes `anyvisible = false` and dispatches to `heapam_index_build_range_scan` | [tableam.h:1512-1533](../../../../raw/postgres-12/src/include/access/tableam.h#L1512-L1533), [heapam_handler.c:2644](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2644) |
| Concurrent build keeps `OldestXmin` invalid and uses an MVCC snapshot; non-concurrent uses `SnapshotAny` + `GetOldestXmin`; B-tree parallel CIC initializes the parallel scan with the concurrent MVCC snapshot | [heapam_handler.c:1212-1223](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1212-L1223), [heapam_handler.c:1233-1260](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1233-L1260), [indexcmds.c:1358-1370](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1358-L1370), [nbtsort.c:1360-1427](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1360-L1427) |
| Heap scan applies the MVCC visibility test itself (`heapgetpage` -> `HeapTupleSatisfiesVisibility` -> `HeapTupleSatisfiesMVCC`); build loop trusts it via the `else` branch before partial-index predicate and callback filtering | [heapam.c:444-453](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L444-L453), [heapam_visibility.c:1690-1696](../../../../raw/postgres-12/src/backend/access/heap/heapam_visibility.c#L1690-L1696), [snapshot.h:37-50](../../../../raw/postgres-12/src/include/utils/snapshot.h#L37-L50), [heapam_handler.c:1595-1665](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1595-L1665), [tableam.h:1495-1500](../../../../raw/postgres-12/src/include/access/tableam.h#L1495-L1500) |
| Concurrent scan skips the `SnapshotAny` `HeapTupleSatisfiesVacuum` switch, so it does not use the normal-build `HEAPTUPLE_RECENTLY_DEAD` inclusion branch; `ii_BrokenHotChain` assignments are inside that switch, and `index_build` skips `indcheckxmin` for concurrent | [heapam_handler.c:1364-1588](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1364-L1588), [index.c:2939-2952](../../../../raw/postgres-12/src/backend/catalog/index.c#L2939-L2952) |
| MVCC (not `HeapTupleSatisfiesVacuum`) avoids bogus unique failures; omitted tuples are backfilled by the second `validate_index` scan | [index.c:3124-3132](../../../../raw/postgres-12/src/backend/catalog/index.c#L3124-L3132), [index.c:3134-3168](../../../../raw/postgres-12/src/backend/catalog/index.c#L3134-L3168) |
| Invalid index left on failure; unique-constraint caveat | [ref/create_index.sgml:574-606](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L574-L606) |
| Failure before commit 1 leaves no index (commit-1 boundary) | [indexcmds.c:1318-1320](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1318-L1320) |
| Planner ignores `indisvalid = false` indexes (executor still inserts if `indisready`) | [plancat.c:200-210](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L200-L210) |
| Not-ready index is opened + `RowExclusiveLock`ed but receives no entries, and its unique check is skipped | [execIndexing.c:185-192](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L185-L192), [execIndexing.c:330-332](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L330-L332), [execIndexing.c:537-539](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L537-L539) |
| Every `indislive` index counts for HOT-safety; not-live indexes are omitted from the index list | [relcache.c:4388-4395](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4388-L4395), [relcache.c:4861-4870](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4861-L4870) |
| Build sets `indisready` as its last action (build-scan vs validate-scan split); state-ladder asserts | [index.c:1426-1438](../../../../raw/postgres-12/src/backend/catalog/index.c#L1426-L1438), [index.c:3353-3396](../../../../raw/postgres-12/src/backend/catalog/index.c#L3353-L3396) |
| Build-scan dup is "could not create unique index ... is duplicated"; concurrent second-scan dup is "duplicate key ... already exists" | [tuplesort.c:4048-4056](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L4048-L4056), [nbtinsert.c:563-568](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L563-L568) |
| Regression: failed unique build left INVALID, retained through `VACUUM FULL`, then made valid by non-concurrent `REINDEX TABLE` once the duplicate is deleted | [create_index.out:1383-1417](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1383-L1417), [create_index.out:1400-1406](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1400-L1406), [create_index.out:1422-1436](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1422-L1436) |
| Named example index per `pg_index` state: `concur_index7` (none), `concur_index3` (invalid, not ready), `concur_index1`/`concur_index2` (valid) | [create_index.out:1391-1395](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1391-L1395), [create_index.out:1413-1420](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1413-L1420) |
| A post-`SET_VALID` error can report CIC failure while leaving a valid index: utility dispatch invokes `ddl_command_end` after `DefineIndex` returns, and the in-place flag cannot roll back | [index.c:3314-3366](../../../../raw/postgres-12/src/backend/catalog/index.c#L3314-L3366), [indexcmds.c:1450-1472](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1450-L1472), [utility.c:1384-1393](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1384-L1393), [utility.c:1701-1719](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1701-L1719), [event_trigger.c:1031-1092](../../../../raw/postgres-12/src/backend/commands/event_trigger.c#L1031-L1092) |
| A failed CIC releases its session lock (removed on `ereport(ERROR)`; abort releases session locks) | [lmgr.c:356-363](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L356-L363), [proc.c:772-798](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L772-L798) |
| `DROP INDEX CONCURRENTLY` is retryable: `INDEX_DROP_CLEAR_VALID` does not assert its starting flags | [index.c:3367-3383](../../../../raw/postgres-12/src/backend/catalog/index.c#L3367-L3383) |
| Crash / `immediate` shutdown triggers automatic WAL-replay recovery; recovered `pg_index` flags are whatever physical replay produces (no CIC repair pass), so the documented fix stays manual `DROP`/`REINDEX` | [xlog.c:6740-6766](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L6740-L6766), [ref/create_index.sgml:574-596](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L574-L596) |
| Flag flips run with no XID and are written by `heap_inplace_update` (`XLOG_HEAP_INPLACE`, page LSN set, no `XLogFlush`) | [index.c:3331-3403](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403), [heapam.c:5746-5774](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L5746-L5774) |
| An xidless WAL-writing transaction commits asynchronously (`XLogSetAsyncXactLSN`, not `XLogFlush`) regardless of `synchronous_commit`, so a flip's durability is decoupled from its phase commit | [xact.c:1232-1392](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1232-L1392), [xlog.c:2630-2670](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2630-L2670) |
| `heap_xlog_inplace` redoes the flip physically and unconditionally whenever its record is durable, so a flip can survive a phase that wrote no commit record | [heapam.c:8797-8835](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L8797-L8835) |
| `XLogFlush` flushes all WAL through a position, so durable SET_VALID implies durable SET_READY; recovered `(indisready, indisvalid)` is monotone, never `(f,t)` | [xlog.c:2791-2798](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2791-L2798), [index.c:1426-1438](../../../../raw/postgres-12/src/backend/catalog/index.c#L1426-L1438), [indexcmds.c:1448-1463](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1448-L1463) |
| For an otherwise complete index using a reviewed in-tree AM, durable SET_VALID cannot outrun build/backfill durability: B-tree `smgrimmedsync`s its outside-buffer build; hash/GiST/SP-GiST/GIN/BRIN use shared-buffer WAL paths; Bloom uses shared-buffer `GenericXLog`; buffer flush obeys WAL-before-data. This is not a proof for third-party AM callbacks or a repair for the prepared-transaction gap | [nbtsort.c:1288-1307](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307), [gistbuild.c:217-226](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L217-L226), [spginsert.c:134-143](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L134-L143), [gininsert.c:408-417](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L408-L417), [hash.c:129-168](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L129-L168), [hashpage.c:346-402](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L346-L402), [brin.c:683-709](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L683-L709), [blinsert.c:44-159](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L44-L159), [generic_xlog.c:328-435](../../../../raw/postgres-12/src/backend/access/transam/generic_xlog.c#L328-L435), [bufmgr.c:2712-2736](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2712-L2736), [amapi.h:160-229](../../../../raw/postgres-12/src/include/access/amapi.h#L160-L229) |
| An unlogged table's heap and indexes reset together to their empty init fork on crash recovery, so recovery does not leave them physically inconsistent | [xlog.c:6878-6884](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L6878-L6884), [xlog.c:7323-7331](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L7323-L7331), [reinit.c:36-46](../../../../raw/postgres-12/src/backend/storage/file/reinit.c#L36-L46) |
| Direct tests cover B-tree functional/failure cases, B-tree/GiST INCLUDE builds, and different-table interleaving; the base regression file explicitly says it lacks concurrent updates | [create_index.sql:460-525](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L460-L525), [index_including.sql:161-168](../../../../raw/postgres-12/src/test/regress/sql/index_including.sql#L161-L168), [index_including_gist.sql:37-44](../../../../raw/postgres-12/src/test/regress/sql/index_including_gist.sql#L37-L44), [multiple-cic.spec:1-40](../../../../raw/postgres-12/src/test/isolation/specs/multiple-cic.spec#L1-L40) |
| Initial lock acquisition point and its conflict set | [utility.c:1311-1326](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1311-L1326), [lock.c:78-81](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L78-L81) |
| Which v12 commands take each conflicting lock mode | [mvcc.sgml:890-1030](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L890-L1030) |
| Autovacuum blocking CIC is sent SIGINT after `deadlock_timeout`, except anti-wraparound | [proc.c:1308-1375](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1308-L1375), [proc.c:1319-1324](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1319-L1324) |
| Prepared transactions hold table locks until COMMIT/ROLLBACK PREPARED but are ignored by Waits 1/2 | [lock.c:2873-2876](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2873-L2876), [lock.c:2815-2818](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2815-L2818), [lmgr.c:890-894](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L890-L894) |
| Waits 1/2 sleep until each holder's whole transaction ends; lock waiters and later writers are skipped | [lmgr.c:896-918](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L896-L918), [lock.c:2804-2807](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2804-L2807), [lmgr.c:855-860](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L855-L860) |
| Wait 3 filters: same database, xmin ≤ limitXmin, xmin=0 skipped, vacuum flags excluded; later rechecks remove old entries but do not add new wait targets | [indexcmds.c:346-383](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L346-L383), [procarray.c:2508-2541](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2508-L2541), [proc.h:53-56](../../../../raw/postgres-12/src/include/storage/proc.h#L53-L56) |
| REPEATABLE READ / SERIALIZABLE first snapshot lives until transaction end | [snapmgr.c:336-356](../../../../raw/postgres-12/src/backend/utils/time/snapmgr.c#L336-L356) |
| Prepared transactions invisible to Wait 3 (invalid xmin and backendId) | [twophase.c:465-472](../../../../raw/postgres-12/src/backend/access/transam/twophase.c#L465-L472), [procarray.c:2525-2539](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2525-L2539) |
| The three waits are visible in `pg_stat_progress_create_index` | [monitoring.sgml:3639-3708](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3639-L3708), [indexcmds.c:385-395](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L385-L395) |
| `pg_dump` runs one `REPEATABLE READ, READ ONLY` (or `SERIALIZABLE, READ ONLY, DEFERRABLE`) transaction, disables the three timeouts, and takes only `ACCESS SHARE` table locks; same-database dumps block only when included by the Wait 3 VXID/xmin filter | [pg_dump.c:1166-1194](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L1166-L1194), [pg_dump.c:1140-1147](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L1140-L1147), [pg_dump.c:6646-6671](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L6646-L6671), [indexcmds.c:346-383](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L346-L383), [procarray.c:2532-2539](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2532-L2539) |
| An idle backend with no active or registered snapshots clears its advertised xmin | [snapmgr.c:989-1028](../../../../raw/postgres-12/src/backend/utils/time/snapmgr.c#L989-L1028) |
| Portal/cursor execution can keep a registered snapshot visible to Wait 3 until the cursor/snapshot is released | [pquery.c:68-83](../../../../raw/postgres-12/src/backend/tcop/pquery.c#L68-L83), [pquery.c:924-932](../../../../raw/postgres-12/src/backend/tcop/pquery.c#L924-L932), [portalmem.c:520-525](../../../../raw/postgres-12/src/backend/utils/mmgr/portalmem.c#L520-L525) |
| Skipping prepared xacts in the writer waits is not sufficient for index correctness: it violates the stated "wait for all modifying transactions to terminate" / "inserted by their originating transaction" invariant | [index.c:3117-3144](../../../../raw/postgres-12/src/backend/catalog/index.c#L3117-L3144), [indexcmds.c:1348-1364](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1348-L1364) |
| Prepared xacts are skipped at the writer waits because their dummy proc has an invalid VXID, dropped by `GetLockConflicts` | [twophase.c:465-472](../../../../raw/postgres-12/src/backend/access/transam/twophase.c#L465-L472), [lock.c:2930-2936](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2930-L2936), [lock.c:2995-3001](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2995-L3001) |
| A prepared xact's tuples stay in-progress (invisible to the MVCC build/validate scans) until `COMMIT PREPARED`; the concurrent build never runs the `SnapshotAny` `INSERT_IN_PROGRESS` path that would index them | [procarray.c:15-18](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L15-L18), [twophase.c:1514-1534](../../../../raw/postgres-12/src/backend/access/transam/twophase.c#L1514-L1534), [heapam_handler.c:1429-1494](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1429-L1494), [heapam_handler.c:1595-1600](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1595-L1600) |
| `COMMIT PREPARED` records the commit and releases locks but performs no executor work and inserts into no index | [twophase.c:1455-1534](../../../../raw/postgres-12/src/backend/access/transam/twophase.c#L1455-L1534) |
| A non-concurrent `CREATE INDEX` instead blocks at lock acquisition on a prepared xact's `RowExclusiveLock`, because its `ShareLock` conflicts with it | [utility.c:1320-1321](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1320-L1321), [lock.c:83-86](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L83-L86) |
| A replication slot's reserved xmin is a global `procArray->replication_slot_xmin`/`replication_slot_catalog_xmin` (set by `ProcArraySetReplicationSlotXmin`), which `GetCurrentVirtualXIDs` never reads — so a slot never puts a VXID in the Wait 3 set | [procarray.c:90-93](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L90-L93), [procarray.c:2982-2992](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2982-L2992), [slot.c:701-742](../../../../raw/postgres-12/src/backend/replication/slot.c#L701-L742), [procarray.c:2520-2523](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2520-L2523) |
| The slot xmin globals are consulted by `GetOldestXmin` and `GetSnapshotData` (`RecentGlobalXmin`), not by `WaitForOlderSnapshots` | [procarray.c:1425-1441](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L1425-L1441), [procarray.c:1727-1741](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L1727-L1741) |
| A physical walsender sets its own `MyPgXact->xmin` from `hot_standby_feedback` (no slot) or clears it and reserves via the slot | [walsender.c:2026-2065](../../../../raw/postgres-12/src/backend/replication/walsender.c#L2026-L2065), [walsender.c:1872-1909](../../../../raw/postgres-12/src/backend/replication/walsender.c#L1872-L1909) |
| A physical walsender connects to no database (`proc->databaseId` stays `InvalidOid`); `GetCurrentVirtualXIDs`'s same-db test lacks `GetOldestXmin`'s "always include WalSender" clause, so it is filtered by database | [postinit.c:841-867](../../../../raw/postgres-12/src/backend/utils/init/postinit.c#L841-L867), [proc.c:394-396](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L394-L396), [procarray.c:2520](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2520), [procarray.c:1348-1350](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L1348-L1350) |
| Wait 3 records a backend only with a valid VXID; `lxid` is set in `StartTransaction`, and `lxid` and `xmin` are cleared together in `ProcArrayEndTransaction`, so an idle (non-transaction) backend has neither | [procarray.c:2537-2539](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2537-L2539), [lock.h:69-82](../../../../raw/postgres-12/src/include/storage/lock.h#L69-L82), [xact.c:1981-1994](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1981-L1994), [procarray.c:433-456](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L433-L456) |
| A logical walsender sets `MyPgXact->xmin` only inside the `REPEATABLE READ` initial-snapshot transaction (slot creation/export) and connects to a real database; routine streaming uses the slot's catalog_xmin global | [snapbuild.c:543-583](../../../../raw/postgres-12/src/backend/replication/logical/snapbuild.c#L543-L583), [postmaster.c:2103-2124](../../../../raw/postgres-12/src/backend/postmaster/postmaster.c#L2103-L2124) |

## Open Questions

None for the reviewed in-tree source behavior at the pinned PostgreSQL 12
commit. The prepared-transaction correctness defect and the post-`SET_VALID`
`ddl_command_end` failure outcome were both source-traced and reproduced on a
temporary build of the exact 12.2 pin.

Three evidence boundaries remain explicit:

- The exact fastest safe GUC combination cannot be computed from the source tree
  alone. It depends on the AM, tuple cardinality and width, partial-index
  selectivity, parallel participants and pool pressure, concurrent writes before
  validation, tablespace and WAL devices, checkpoint timing, blockers,
  available CPU/I/O, and whether the host swaps. The source defines the
  transitions and limits; finding the workload-specific
  `maintenance_work_mem` plateau and the broader optimum requires controlled
  measurements
  ([tuplesort.c#algorithm](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1-L75),
  [ref/create_index.sgml#memory-and-parallelism](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L707-L741),
  [create_index.sql#CIC-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L460-L525)).
- The [crash / immediate-shutdown analysis](#server-crash-or-immediate-shutdown)
  is a static source trace, not a live crash-timing reproduction. It establishes
  monotone flag replay and build/backfill durability for the six core AMs and
  contrib Bloom. It does not claim that recovery repairs the independently
  demonstrated prepared-transaction gap.
- Arbitrary third-party index AM code is outside this checkout's evidence. Core
  dispatches physical build, validation enumeration, and inserts to AM
  callbacks, so this page does not claim to prove a third-party AM's internal
  waits or crash durability
  ([amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L160-L229),
  [index.c#ambuild-dispatch](../../../../raw/postgres-12/src/backend/catalog/index.c#L2899-L2904)).

## Source References

- [gram.y#IndexStmt](../../../../raw/postgres-12/src/backend/parser/gram.y#L7333-L7407)
- [parser/Makefile#generated-grammar](../../../../raw/postgres-12/src/backend/parser/Makefile#L15-L54)
- [parsenodes.h#IndexStmt](../../../../raw/postgres-12/src/include/nodes/parsenodes.h#L2738-L2775)
- [catalog/Makefile#generated-headers](../../../../raw/postgres-12/src/backend/catalog/Makefile#L28-L99)
- [genbki.pl#definition-headers](../../../../raw/postgres-12/src/backend/catalog/genbki.pl#L368-L398)
- [pg_am.dat#BTREE_AM_OID](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L20)
- [utility.c#IndexStmt-dispatch-and-events](../../../../raw/postgres-12/src/backend/tcop/utility.c#L960-L975)
- [utility.c#IndexStmt-dispatch](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1301-L1393)
- [utility.c#DDL-command-end](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1701-L1719)
- [event_trigger.c#EventTriggerInvoke](../../../../raw/postgres-12/src/backend/commands/event_trigger.c#L1031-L1092)
- [amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L160-L229)
- [indexam.c#index_insert](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L165-L189)
- [indexam.c#index_bulk_delete](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L672-L693)
- [indexam.sgml#ambuild](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L232-L265)
- [indexam.sgml#index-locking](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L891-L911)
- [indexcmds.c#DefineIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L429-L1473)
- [indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L307-L402)
- [postgres.c#finish_xact_command](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2569-L2578)
- [pg_index.h#flags](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L40-L43)
- [index.c#index_create-skip-build](../../../../raw/postgres-12/src/backend/catalog/index.c#L1198-L1222)
- [index.c#index_concurrently_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L1399-L1439)
- [index.c#BuildIndexInfo](../../../../raw/postgres-12/src/backend/catalog/index.c#L2315-L2344)
- [index.c#index_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L2824-L2952)
- [tableam.h#table_index_build_scan](../../../../raw/postgres-12/src/include/access/tableam.h#L1485-L1533)
- [snapshot.h#SNAPSHOT_MVCC](../../../../raw/postgres-12/src/include/utils/snapshot.h#L37-L50)
- [nbtsort.c#parallel-build-snapshot](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1360-L1427)
- [nbtsort.c#parallel-worker-waits](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1473-L1561)
- [nbtsort.c#parallel-worker-scan](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1779-L1786)
- [heapam_handler.c#heapam_index_build_range_scan](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1150-L1703)
- [heapam.c#heapgetpage](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L351-L461)
- [heapam_visibility.c#HeapTupleSatisfiesVisibility](../../../../raw/postgres-12/src/backend/access/heap/heapam_visibility.c#L1679-L1718)
- [heapam_visibility.c#HeapTupleSatisfiesMVCC](../../../../raw/postgres-12/src/backend/access/heap/heapam_visibility.c#L940-L963)
- [index.c#validate_index](../../../../raw/postgres-12/src/backend/catalog/index.c#L3112-L3298)
- [guc.c#maintenance_work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2243-L2252)
- [set.sgml#SET-scope](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L33-L115)
- [parallel.c#serialize-GUC-state](../../../../raw/postgres-12/src/backend/access/transam/parallel.c#L349-L352)
- [parallel.c#restore-GUC-state](../../../../raw/postgres-12/src/backend/access/transam/parallel.c#L1349-L1361)
- [guc.c#max_parallel_maintenance_workers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2997-L3004)
- [config.sgml#parallel-maintenance-workers](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2283-L2316)
- [guc.c#trace_sort](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1635-L1645)
- [guc.c#log_temp_files](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3153-L3162)
- [config.sgml#maintenance_work_mem](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1686-L1712)
- [config.sgml#autovacuum_work_mem](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1716-L1731)
- [ref/create_index.sgml#memory-and-parallelism](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L707-L771)
- [miscadmin.h#maintenance_work_mem](../../../../raw/postgres-12/src/include/miscadmin.h#L243-L247)
- [planner.c#plan_create_index_workers](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L6227-L6362)
- [allpaths.c#compute_parallel_worker](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L3563-L3653)
- [nbtsort.c#build-sort-memory](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L378-L520)
- [nbtsort.c#BTLeader](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L177-L205)
- [nbtsort.c#parallel-setup-and-fallback](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1328-L1485)
- [nbtsort.c#parallel-sort-memory](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1550-L1797)
- [nbtree.c#validation-enumeration](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L848-L1041)
- [nbtree.c#validation-callback](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1197-L1270)
- [tuplesort.c#algorithm](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1-L83)
- [tuplesort.c#sort-memory-initialization](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L700-L762)
- [tuplesort.c#performsort](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1641-L1866)
- [tuplesort.c#sort-end-report](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L1225-L1279)
- [tuplesort.c#run-and-merge-trace](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L2837-L3022)
- [tuplesort.c#worker-memory-release](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L4462-L4490)
- [tuplesort.c#leader-takes-participant-runs](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L4510-L4561)
- [hash.c#hashbuild-sort-choice](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L126-L177)
- [hashsort.c#_h_spoolinit](../../../../raw/postgres-12/src/backend/access/hash/hashsort.c#L54-L90)
- [gistbuild.c#gistInitBuffering](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L312-L417)
- [gistbuildbuffers.c#temporary-buffer-file](../../../../raw/postgres-12/src/backend/access/gist/gistbuildbuffers.c#L48-L62)
- [gist.sgml#buffering-build](../../../../raw/postgres-12/doc/src/sgml/gist.sgml#L962-L993)
- [gininsert.c#GIN-build-memory](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L245-L314)
- [ginbulk.c#posting-list-limit](../../../../raw/postgres-12/src/backend/access/gin/ginbulk.c#L28-L51)
- [ginfast.c#cleanup-memory-and-batches](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L779-L1009)
- [ginvacuum.c#ginbulkdelete](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L563-L594)
- [spginsert.c#spgbuild](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L71-L149)
- [spgvacuum.c#spgbulkdelete](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L893-L916)
- [brin.c#brinbuild-and-bulkdelete](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L658-L784)
- [blvacuum.c#blbulkdelete](../../../../raw/postgres-12/contrib/bloom/blvacuum.c#L26-L107)
- [monitoring.sgml#create-index-progress](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3488-L3704)
- [monitoring.sgml#temp-file-counters](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2577-L2592)
- [fd.c#ReportTemporaryFileUsage](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1272-L1287)
- [pgstat.c#temp-file-accounting](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L1560-L1576)
- [pgstat.c#progress-tracking](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L3192-L3259)
- [pgstat.c#temp-byte-counter](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6397-L6412)
- [create_index.sql#hash-tuplesort](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L379-L387)
- [cluster.sql#maintenance_work_mem](../../../../raw/postgres-12/src/test/regress/sql/cluster.sql#L207-L225)
- [index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3331-L3403)
- [lmgr.c#WaitForLockers](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L850-L949)
- [lock.c#LockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L65-L103)
- [lock.c#GetLockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L2804-L2821)
- [lockdefs.h#lockmodes](../../../../raw/postgres-12/src/include/storage/lockdefs.h#L36-L46)
- [utility.c#CIC-dispatch](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1305-L1321)
- [procarray.c#GetCurrentVirtualXIDs](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2467-L2548)
- [indexcmds.c#ReindexRelationConcurrently](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L2739-L3342)
- [proc.c#ProcSleep-autovacuum-cancel](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1308-L1375)
- [proc.h#vacuumFlags](../../../../raw/postgres-12/src/include/storage/proc.h#L53-L63)
- [twophase.c#MarkAsPreparingGuts](../../../../raw/postgres-12/src/backend/access/transam/twophase.c#L446-L490)
- [twophase.c#FinishPreparedTransaction](../../../../raw/postgres-12/src/backend/access/transam/twophase.c#L1455-L1618)
- [procarray.c#prepared-xacts-in-array](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L13-L18)
- [snapmgr.c#GetTransactionSnapshot](../../../../raw/postgres-12/src/backend/utils/time/snapmgr.c#L305-L373)
- [snapmgr.c#SnapshotResetXmin](../../../../raw/postgres-12/src/backend/utils/time/snapmgr.c#L989-L1028)
- [pquery.c#CreateQueryDesc](../../../../raw/postgres-12/src/backend/tcop/pquery.c#L68-L83)
- [pquery.c#PortalRunSelect](../../../../raw/postgres-12/src/backend/tcop/pquery.c#L924-L932)
- [portalmem.c#PortalDrop](../../../../raw/postgres-12/src/backend/utils/mmgr/portalmem.c#L520-L525)
- [pg_dump.c#dump-transaction](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L1140-L1194)
- [pg_dump.c#lock-table](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L6646-L6671)
- [mvcc.sgml#table-level-locks](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L890-L1039)
- [monitoring.sgml#create-index-phases](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3630-L3709)
- [ref/create_index.sgml#CONCURRENTLY](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L545-L631)
- [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L200-L210)
- [execIndexing.c#ready-for-inserts](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L185-L539)
- [relcache.c#RelationGetIndexList](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4348-L4435)
- [index.c#index_drop](../../../../raw/postgres-12/src/backend/catalog/index.c#L2007-L2166)
- [heapam.c#heap_inplace_update](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L5692-L5774)
- [heapam.c#heap_xlog_inplace](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L8797-L8835)
- [xact.c#RecordTransactionCommit](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1206-L1401)
- [xlog.c#XLogFlush](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2791-L2798)
- [xlog.c#XLogSetAsyncXactLSN](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2630-L2670)
- [xlog.c#StartupXLOG-crash-recovery](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L6740-L6766)
- [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2712-L2736)
- [nbtsort.c#build-durability](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307)
- [rel.h#RelationNeedsWAL](../../../../raw/postgres-12/src/include/utils/rel.h#L519-L520)
- [gistbuild.c#gistbuild-wal](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L217-L226)
- [spginsert.c#spgbuild-wal](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L134-L143)
- [gininsert.c#ginbuild-wal](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L408-L417)
- [hash.c#hashbuild](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L129-L168)
- [hashpage.c#_hash_init](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L346-L402)
- [brin.c#brinbuild](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L683-L709)
- [bloom--1.0.sql#access-method](../../../../raw/postgres-12/contrib/bloom/bloom--1.0.sql#L8-L13)
- [blinsert.c#blbuild](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L44-L159)
- [blutils.c#BloomInitMetapage](../../../../raw/postgres-12/contrib/bloom/blutils.c#L445-L470)
- [generic_xlog.c#GenericXLogFinish](../../../../raw/postgres-12/src/backend/access/transam/generic_xlog.c#L263-L435)
- [xlog.c#reset-unlogged-cleanup](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L6878-L6884)
- [xlog.c#reset-unlogged-init](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L7323-L7331)
- [reinit.c#ResetUnloggedRelations](../../../../raw/postgres-12/src/backend/storage/file/reinit.c#L36-L46)
- [tuplesort.c#unique-violation](../../../../raw/postgres-12/src/backend/utils/sort/tuplesort.c#L4040-L4056)
- [nbtinsert.c#unique-waits](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L252-L274)
- [nbtinsert.c#_bt_check_unique](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L563-L568)
- [lmgr.c#LockRelationIdForSession](../../../../raw/postgres-12/src/backend/storage/lmgr/lmgr.c#L356-L389)
- [proc.c#ProcReleaseLocks](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L772-L798)
- [create_index.sql#CIC-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L460-L525)
- [create_index.out#concurrent-invalid](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1382-L1436)
- [index_including.sql#CIC](../../../../raw/postgres-12/src/test/regress/sql/index_including.sql#L161-L168)
- [index_including_gist.sql#CIC](../../../../raw/postgres-12/src/test/regress/sql/index_including_gist.sql#L37-L44)
- [bloom.sql#index-builds](../../../../raw/postgres-12/contrib/bloom/sql/bloom.sql#L1-L95)
- [multiple-cic.spec](../../../../raw/postgres-12/src/test/isolation/specs/multiple-cic.spec#L1-L40)
- [multiple-cic.out](../../../../raw/postgres-12/src/test/isolation/expected/multiple-cic.out#L3-L19)
- [procarray.c#GetOldestXmin](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L1306-L1443)
- [procarray.c#GetSnapshotData-slots](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L1700-L1743)
- [procarray.c#ProcArraySetReplicationSlotXmin](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L2976-L2993)
- [procarray.c#ProcArrayEndTransaction](../../../../raw/postgres-12/src/backend/storage/ipc/procarray.c#L433-L464)
- [slot.c#ReplicationSlotsComputeRequiredXmin](../../../../raw/postgres-12/src/backend/replication/slot.c#L695-L742)
- [walsender.c#ProcessStandbyHSFeedbackMessage](../../../../raw/postgres-12/src/backend/replication/walsender.c#L1872-L2066)
- [postinit.c#InitPostgres-walsender](../../../../raw/postgres-12/src/backend/utils/init/postinit.c#L841-L867)
- [proc.c#InitProcess](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L386-L398)
- [lock.h#VirtualTransactionId](../../../../raw/postgres-12/src/include/storage/lock.h#L55-L82)
- [xact.c#StartTransaction](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L1981-L1996)
- [snapbuild.c#SnapBuildInitialSnapshot](../../../../raw/postgres-12/src/backend/replication/logical/snapbuild.c#L543-L583)
- [postmaster.c#ProcessStartupPacket-replication](../../../../raw/postgres-12/src/backend/postmaster/postmaster.c#L2103-L2124)
- [bgworker.c#parallel-worker-pools](../../../../raw/postgres-12/src/backend/postmaster/bgworker.c#L138-L173)
- [bgworker.c#RegisterDynamicBackgroundWorker](../../../../raw/postgres-12/src/backend/postmaster/bgworker.c#L920-L1014)
- [heapam.c#scan-strategy-and-syncscan](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L207-L301)
- [freelist.c#GetAccessStrategy](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L537-L587)
- [nodeBitmapHeapscan.c#effective_io_concurrency](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L797-L817)
- [sharedfileset.c#temp-tablespaces](../../../../raw/postgres-12/src/backend/storage/file/sharedfileset.c#L36-L68)
- [fd.c#temp_file_limit](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1933-L1958)
- [buf_init.c#BackendWritebackContext](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L146-L152)
- [bufmgr.c#backend-writeback](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1088-L1156)
- [gin_private.h#pending-list-limit](../../../../raw/postgres-12/src/include/access/gin_private.h#L21-L39)
- [ginutil.c#GIN-reloptions](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L602-L628)
- [cost.h#DEFAULT_EFFECTIVE_CACHE_SIZE](../../../../raw/postgres-12/src/include/optimizer/cost.h#L21-L32)
- [xloginsert.c#full-page-images-and-compression](../../../../raw/postgres-12/src/backend/access/transam/xloginsert.c#L539-L630)
- [xloginsert.c#log_newpage](../../../../raw/postgres-12/src/backend/access/transam/xloginsert.c#L959-L995)
- [xlog.c#group-commit-delay](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2891-L2915)
- [syncrep.c#SyncRepWaitForLSN](../../../../raw/postgres-12/src/backend/replication/syncrep.c#L131-L219)
- [lock.c#VirtualXactLock](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L4361-L4458)
- [proc.c#lock-timeout-and-wait-logging](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1229-L1469)
- [postgres.c#statement-timeout](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4680-L4717)
- [postgres.c#idle-in-transaction-timeout](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4126-L4152)
- [vacuum.c#vacuum_delay_point](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1939-L1971)
- [pg_config_manual.h#writeback-defaults](../../../../raw/postgres-12/src/include/pg_config_manual.h#L147-L163)
- [config.sgml#wal_level](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2446-L2479)
- [config.sgml#track_io_timing](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6854-L6870)
- [ref/create_index.sgml#tablespace](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L335-L344)
- [utils/misc/Makefile#guc](../../../../raw/postgres-12/src/backend/utils/misc/Makefile#L17-L33)

## Navigation

- [How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 12](reindex-index-concurrently.md)
- [v12 index](../../index.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
