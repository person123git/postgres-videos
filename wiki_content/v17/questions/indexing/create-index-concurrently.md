---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Preconditions and restrictions](#preconditions-and-restrictions)
  - [The three pg_index state flags](#the-three-pg_index-state-flags)
  - [Step-by-step implementation](#step-by-step-implementation)
  - [How maintenance_work_mem is used and where increases stop helping](#how-maintenance_work_mem-is-used-and-where-increases-stop-helping)
  - [GUCs that affect CIC performance](#gucs-that-affect-cic-performance)
  - [All steps and locks required on the table](#all-steps-and-locks-required-on-the-table)
  - [What changed from PostgreSQL 12](#what-changed-from-postgresql-12)
  - [Failure handling](#failure-handling)
  - [Test coverage](#test-coverage)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

give a comprehensive explanation of how create index concurrently is
implemented, add a section with all steps and locks required on the table, and
add a section with what has changed from postgresql 12.

Follow-up: Investigate how `maintenance_work_mem` is used during `CREATE INDEX
CONCURRENTLY`, and at what point increasing it stops improving the index
creation process.

Follow-up: What GUCs have a performance impact on it?

## Answer

`CREATE INDEX CONCURRENTLY` (CIC) builds an index without ever taking a lock
that blocks `INSERT`/`UPDATE`/`DELETE` on the table. In PostgreSQL 17, as in
PostgreSQL 12, it splits the build across **four internal transactions**, does
**two full table scans**, and **waits out other transactions three times**. The
core lock/scan/wait shape remains recognizable from v12. The main behavioral
optimization is `PROC_IN_SAFE_IC` (added in PostgreSQL 14), which lets a CIC
build on a plain index skip waiting for other concurrent index builds in its
final snapshot wait; v17 also differs in catalog-update and security plumbing
inside the same phases. See [What changed from PostgreSQL 12](#what-changed-from-postgresql-12).

All orchestration lives in `DefineIndex()` in the concurrent branch
([indexcmds.c#DefineIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L540)),
which calls helpers in `index.c` (`index_create`, `index_concurrently_build`,
`validate_index`, `index_set_state_flags`) and waits via `WaitForLockers` and
`WaitForOlderSnapshots`. The table lock used throughout is
**`ShareUpdateExclusiveLock`** — strong enough to keep out a second CIC,
`VACUUM`, `ANALYZE`, and schema changes, but weak enough to let normal DML
proceed
([lockdefs.h:36-46](../../../../raw/postgres-17/src/include/storage/lockdefs.h#L36-L46)).

### Preconditions and restrictions

| Restriction | Where enforced |
|---|---|
| Cannot run inside a transaction block (`BEGIN; ... COMMIT;`) | `PreventInTransactionBlock(isTopLevel, "CREATE INDEX CONCURRENTLY")` ([utility.c:1461-1463](../../../../raw/postgres-17/src/backend/tcop/utility.c#L1461-L1463)) |
| Temporary tables silently fall back to a non-concurrent build | [indexcmds.c:612](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L612) |
| Partitioned tables cannot be built concurrently | [indexcmds.c:729](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L729) |
| System catalog tables cannot be indexed concurrently | [index.c:859-860](../../../../raw/postgres-17/src/backend/catalog/index.c#L859-L860) |
| Exclusion constraints cannot be built concurrently | [index.c:868-869](../../../../raw/postgres-17/src/backend/catalog/index.c#L868-L869) |
| The invoking role must hold `USAGE` on every type the index expression or predicate depends on | `DefineIndex` calls `CheckUsageOnTypesInSingleRelExpr` on `ii_Expressions` and `ii_Predicate` before `index_create()` ([indexcmds.c:931-945](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L931-L945), [dependency.c#CheckUsageOnTypesInSingleRelExpr](../../../../raw/postgres-17/src/backend/catalog/dependency.c#L1741-L1767)) |

The type check is new in 17.11 (commit `d1c8aa0b09f`, "Check for USAGE privilege
on types used by stored expressions", CVE-2026-6470, back-patched through v14).
It fails the statement **before** `index_create()`, whose header now states the
contract that the caller must check `USAGE` for the types
`indexInfo->ii_{Expressions,Predicate}` depend on
([index.c:726-728](../../../../raw/postgres-17/src/backend/catalog/index.c#L726-L728)).
The scope is exactly the `check_rights` argument of `DefineIndex`: a user-issued
`CREATE INDEX` (concurrent or not) arrives from `standard_ProcessUtility` with
`check_rights = true`
([utility.c:1543-1553](../../../../raw/postgres-17/src/backend/tcop/utility.c#L1543-L1553)),
while the `ALTER TABLE ... ATTACH PARTITION` path that clones a parent index into
the new partition passes `check_rights = false` and so skips it
([tablecmds.c:19011-19015](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L19011-L19015)).
Tests: `CREATE INDEX ON test9a ((a::priv_testdomain1));` fails with
`permission denied for type public.priv_testdomain1`
([privileges.sql:959](../../../../raw/postgres-17/src/test/regress/sql/privileges.sql#L959),
[privileges.out:1357-1358](../../../../raw/postgres-17/src/test/regress/expected/privileges.out#L1357-L1358)),
and the companion block asserts that rebuilds of existing stored expressions need
no `USAGE`
([privileges.sql:1030-1038](../../../../raw/postgres-17/src/test/regress/sql/privileges.sql#L1030-L1038),
[privileges.out:1417-1428](../../../../raw/postgres-17/src/test/regress/expected/privileges.out#L1417-L1428)).

### The three pg_index state flags

CIC is driven by three boolean flags on the index's `pg_index` row, set by
`UpdateIndexRelation`
([index.c:645-648](../../../../raw/postgres-17/src/backend/catalog/index.c#L645-L648)):

- `indislive` — the index exists and must be maintained. CIC sets this `true`
  from the start.
- `indisready` — new tuples (from `INSERT`/non-HOT `UPDATE`) must be inserted
  into the index.
- `indisvalid` — the planner may use the index to answer queries.

A normal `CREATE INDEX` is born with all three `true`. CIC instead creates the
catalog row with `indisvalid = false` and `indisready = false`
(`!concurrent && !invalid` and `!concurrent` at
[index.c:1056-1057](../../../../raw/postgres-17/src/backend/catalog/index.c#L1056-L1057)),
then flips `indisready`, and finally `indisvalid`, using `index_set_state_flags`.
In v17, that helper edits a writable copy of the `pg_index` tuple and stores it
with transactional `CatalogTupleUpdate`, so other sessions hear about the flag
change after the transaction commits
([index.c#index_set_state_flags](../../../../raw/postgres-17/src/backend/catalog/index.c#L3469-L3547)).

### Step-by-step implementation

The concurrent branch runs as four transactions, separated by
`CommitTransactionCommand()` / `StartTransactionCommand()` pairs.

**Transaction 1 — create the catalog entry (no build).** `index_create` makes
the `pg_index`/`pg_class` rows with `INDEX_CREATE_CONCURRENT` and
`INDEX_CREATE_SKIP_BUILD`, so the index has a catalog identity but no data and is
marked not-ready/not-valid. CIC also computes `safe_index` — true only when the
index has no expressions and no predicate
([indexcmds.c:1144-1146](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1144-L1146)).
Before committing, it takes a **session-level** `ShareUpdateExclusiveLock` on the
table so it survives the upcoming commits and nobody can drop the table or index
([indexcmds.c:1615-1619](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1615-L1619)).
The commit makes the empty index visible so other backends stop making
incompatible HOT updates.

**Wait 1, then Transaction 2 — first scan, build.** After the commit (and, if
`safe_index`, a call to `set_indexsafe_procflags()` —
[indexcmds.c:1621-1623](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1621-L1623)),
CIC waits for every transaction that could still have the table open without the
new index, using `WaitForLockers(heaplocktag, ShareLock, true)`
([indexcmds.c:1642-1658](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1642-L1658)).
It then takes a fresh snapshot and calls `index_concurrently_build`, which scans
the heap, builds the index, and sets `indisready = true`
([indexcmds.c:1679-1682](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1679-L1682),
[index.c#index_concurrently_build](../../../../raw/postgres-17/src/backend/catalog/index.c#L1499-L1556)).
The commit publishes `indisready` so new writers start maintaining the index.

**Wait 2, then Transaction 3 — second scan, validate.** After another
`set_indexsafe_procflags()` (if safe) it waits again with
`WaitForLockers(..., ShareLock, ...)`
([indexcmds.c:1693-1705](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1693-L1705)),
registers a **reference snapshot**, and calls `validate_index`
([indexcmds.c:1722-1728](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1722-L1728)).
`validate_index` collects the TIDs already in the index, sorts them, scans the
heap, and inserts any tuple visible to the reference snapshot but missing from
the index
([index.c#validate_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3325-L3353)).
Before committing, CIC saves the snapshot's `xmin` as `limitXmin` and **drops the
snapshot** to avoid deadlocking against other CIC runs
([indexcmds.c:1737-1740](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1737-L1740)).

**Wait 3, then Transaction 4 — mark valid.** In a fresh transaction (so no
snapshot is held; the `Assert(MyProc->xmin == InvalidTransactionId)` enforces
this), and after a final `set_indexsafe_procflags()` if safe, CIC calls
`WaitForOlderSnapshots(limitXmin, true)` to wait out any transaction whose
snapshot predates the reference snapshot
([indexcmds.c:1753-1768](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1753-L1768)).
Then it sets `indisvalid = true`, sends a relcache invalidation on the parent
table so cached plans re-plan to use the new index, and releases the session lock
([indexcmds.c:1773-1788](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1773-L1788)).
This last transaction commits in the caller when the utility command finishes.

### How maintenance_work_mem is used and where increases stop helping

There is **no universal `maintenance_work_mem` value at which CIC stops getting
faster**. PostgreSQL 17 can use the setting in two separate parts of the
command:

1. transaction 2's access-method-specific first build, when that index access
   method reads the setting; and
2. transaction 3's common, serial sort of index tuple identifiers (TIDs) during
   validation. GIN can also use the setting for forced pending-list cleanup at
   the start of its validation scan
   ([indexcmds.c#build-to-validation](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1678-L1728),
   [index.c#validate_index-sort](../../../../raw/postgres-17/src/backend/catalog/index.c#L3325-L3434),
   [ginvacuum.c#ginbulkdelete-cleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L571-L602)).

An increase helps only while it changes an access-method threshold, reduces an
external sort's runs or merge work, lets a useful B-tree or BRIN worker be
requested, or reduces GIN accumulator batches. Once those effects and measured
elapsed time stop changing, more memory cannot remove the first heap scan, the
index scan and second heap scan used for validation, index-page writes, the two
writer waits, or the old-snapshot wait
([indexcmds.c#CIC-build-and-validation](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1642-L1773),
[index.c#validate_index-overview](../../../../raw/postgres-17/src/backend/catalog/index.c#L3262-L3324)).

**Setting and application scope.** In v17, `maintenance_work_mem` is a
`PGC_USERSET` integer measured in kilobytes. Its default is 64 MB and its range
starts at 64 kB. It can be changed for a session or transaction and needs
neither reload nor restart
([guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2460-L2474),
[config.sgml#maintenance_work_mem](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L1922-L1948)).
For one CIC run, a regular session setting is the practical scope: it survives
CIC's internal commits. A transaction-local setting ends at commit, has no
effect when issued outside a transaction block, and cannot enclose CIC because
CIC is rejected inside an explicit transaction block
([ref/set.sgml#SET-scope](../../../../raw/postgres-17/doc/src/sgml/ref/set.sgml#L35-L60),
[ref/set.sgml#LOCAL](../../../../raw/postgres-17/doc/src/sgml/ref/set.sgml#L100-L117),
[utility.c#CIC-transaction-block](../../../../raw/postgres-17/src/backend/tcop/utility.c#L1453-L1463)).
Parallel build workers restore the launching backend's serialized GUC state, so
the session value also reaches a parallel B-tree or BRIN build
([parallel.c#serialize-GUC-state](../../../../raw/postgres-17/src/backend/access/transam/parallel.c#L376-L385),
[parallel.c#restore-GUC-state](../../../../raw/postgres-17/src/backend/access/transam/parallel.c#L1449-L1458)).

The value is a working budget or threshold, not memory reserved in advance.
Tuplesort charges allocations against an allowed-byte counter as input arrives;
GIN checks its tracked accumulator only after processing a complete heap tuple,
so GIN can overshoot the nominal threshold
([tuplesort.c#sort-memory-initialization](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L680-L715),
[tuplesort.c#spill-check](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1225-L1294),
[gininsert.c#GIN-build-threshold](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L246-L314)).
The v17 docs warn that setting it above genuinely available memory can cause
swapping and make index creation slower. A shared/default increase can also be
multiplied across maintenance sessions and autovacuum workers; a session-only
value applies to the current session and the parallel workers it launches, not
to unrelated sessions
([ref/create_index.sgml#memory-warning](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L798-L804),
[config.sgml#maintenance-memory-concurrency](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L1930-L1948),
[ref/set.sgml#SET-session](../../../../raw/postgres-17/doc/src/sgml/ref/set.sgml#L35-L51),
[parallel.c#serialize-GUC-state](../../../../raw/postgres-17/src/backend/access/transam/parallel.c#L376-L385)).

**The transaction-2 and transaction-3 memory windows do not coexist.**
`index_concurrently_build()` completes `index_build()` and its AM callback,
marks the index ready, and returns. CIC commits that transaction, performs the
second writer wait, and only then lets `validate_index()` create and consume a
new tuplesort. The validation tuplesort is destroyed before that transaction
commits
([index.c#index_concurrently_build](../../../../raw/postgres-17/src/backend/catalog/index.c#L1499-L1557),
[indexcmds.c#build-to-validation](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1678-L1728),
[index.c#validation-sort-lifetime](../../../../raw/postgres-17/src/backend/catalog/index.c#L3390-L3437)).
Validation encodes each TID reported by the AM's `ambulkdelete` callback as an
`int8`, sorts those values with the full `maintenance_work_mem`, and merge-scans
them against the heap. The `NULL` sort coordinate makes this phase serial; the
documentation likewise limits CIC parallelism to its first table scan
([index.c#validate_index-sort](../../../../raw/postgres-17/src/backend/catalog/index.c#L3390-L3434),
[heapam_handler.c#validation-merge](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1747-L1975),
[ref/create_index.sgml#CIC-parallel-scope](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L855-L862)).

**B-tree first build and the automatic worker thresholds.** A serial B-tree
build gives its primary index-tuple sort the full setting. A parallel build
splits the scan work among participants and later lets a leader tuplesort merge
their output. PostgreSQL intends the setting as the whole parallel-build sort
budget: workers receive fractions, and the leader's significant allocation
happens after workers have released almost all of theirs
([nbtsort.c#primary-sort](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L362-L431),
[nbtsort.c#parallel-memory-lifetimes](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L407-L425)).
It is not an exact cap on every byte allocated by the command: tuplesort floors
each passed share at 64 kB, unique builds have a separate secondary sort, and
parallel coordination plus AM allocations sit outside the primary
`Tuplesortstate.allowedMem`
([tuplesort.c#minimum-sort-budget](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L694-L742),
[nbtsort.c#secondary-sort](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L433-L471),
[config.sgml#parallel-utility-memory](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L2887-L2898)).

For automatic worker choice, `plan_create_index_workers()` requires at least
32 MB for each requested worker **and** another 32 MB for the leader. The memory
cap therefore permits no worker below 64 MB, up to one worker at 64 MB, up to
two at 96 MB, and each additional worker at another 32 MB. With the default
`max_parallel_maintenance_workers = 2`, 96 MB is the last memory-derived
worker-count threshold, not the overall performance plateau: the first-build or
validation sort can still spill above 96 MB
([planner.c#memory-worker-cap](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6993-L7018),
[guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417),
[tuplesort.c#serial-and-external-sort](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L31-L80)).
`max_parallel_maintenance_workers` is also `PGC_USERSET`; session or transaction
changes need neither reload nor restart. Its default is two
([guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417)).

Those thresholds only cap an automatic request. Table size and parallel safety
can request fewer workers, and the worker pool can launch fewer than requested.
A table-level `parallel_workers` reloption bypasses the size model and the
memory-based 32 MB cap, though `max_parallel_maintenance_workers` still caps the
request
([planner.c#worker-prerequisites-and-override](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6908-L6985),
[config.sgml#parallel-worker-availability](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L2864-L2884),
[ref/create_index.sgml#parallel_workers-override](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L835-L844)).
In the normal source build the leader participates. Each launched background
worker divides by the planned participant count, while the leader's worker role
divides by the actual launched count; if no worker launches or no dynamic shared
memory segment is available, B-tree falls back to a serial full-budget build
([nbtsort.c#parallel-setup-and-fallback](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1390-L1594),
[nbtsort.c#leader-participant-share](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1683-L1725),
[nbtsort.c#background-worker-share](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1823-L1829)).

A unique B-tree build allocates a secondary dead-tuple sort using `work_mem`,
or the smaller of `work_mem` and a participant's primary share. In CIC's MVCC
build scan, however, the heap scan filters by snapshot and marks every tuple
that reaches the callback alive, so no tuple enters that secondary spool; the
leader discards it as unnecessary
([heapam_handler.c#concurrent-build-snapshot](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1237-L1296),
[heapam_handler.c#concurrent-tuples-are-alive](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1621-L1629),
[nbtsort.c#build-callback](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L573-L600),
[nbtsort.c#discard-empty-secondary-spool](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L500-L518),
[nbtsort.c#parallel-secondary-sort](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1886-L1908)).

**First-build behavior by shipped index AM.** The common validation phase comes
after every first build, but transaction 2 uses the setting differently:

| Index AM | First-build use of `maintenance_work_mem` | Where that first-build gain stops |
|---|---|---|
| B-tree | Sorts full index tuples. Serial gets the full budget; parallel scan participants divide it before the leader merge ([nbtsort.c#primary-sort](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L362-L431), [nbtsort.c#parallel-worker-sort](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1861-L1939)). | When more memory neither adds a useful worker nor reduces participant run/merge work. The separate serial validation sort must also be checked ([planner.c#memory-worker-cap](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6993-L7018), [tuplesort.c#performsort](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1381-L1465)). |
| Hash | Computes a block-valued sort threshold `min((maintenance_work_mem * 1024) / BLCKSZ, NBuffers)` for a true CIC, and pre-sorts by target bucket when the estimated bucket count is at least that threshold. A selected sort receives the full setting. A temporary-table request has already fallen back to non-concurrent build and uses `NLocBuffer` instead ([hash.c#hashbuild-sort-choice](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L111-L183), [hashsort.c#_h_spoolinit](../../../../raw/postgres-17/src/backend/access/hash/hashsort.c#L56-L92), [indexcmds.c#temp-fallback](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L605-L615)). | Raising memory can make the threshold exceed the estimated bucket count and disable pre-sorting. The threshold itself stops rising when `NBuffers` wins; if the bucket count still reaches that cap, sorting remains selected and more memory can still reduce its runs and merge work ([hash.c#hashbuild-sort-rationale](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L139-L166), [tuplesort.c#serial-and-external-sort](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L31-L80)). |
| GiST | If every key opclass supplies `sortsupport` and buffered mode was not forced on, GiST uses a serial tuplesort with the full setting. Otherwise it inserts directly and may switch to buffered build; that path uses `maintenance_work_mem` with `effective_cache_size` to choose `levelStep`, and insufficient memory disables buffering ([gistbuild.c#strategy-selection](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L175-L248), [gistbuild.c#sorted-build](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L257-L315), [gistbuild.c#gistInitBuffering](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L617-L777)). | The sorted path plateaus like another serial sort. The direct-insert path has no gain. In buffered mode, the memory decision plateaus when `effective_cache_size`, rather than maintenance memory, prevents the next `levelStep`; the buffer hash table is not included in that calculation. Buffered GiST also creates its own temporary file and can use extra CPU, so elapsed time need not improve monotonically ([gistbuild.c#buffer-memory-boundary](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L670-L757), [gistbuildbuffers.c#temporary-buffer-file](../../../../raw/postgres-17/src/backend/access/gist/gistbuildbuffers.c#L40-L81), [gist.sgml#build-methods](../../../../raw/postgres-17/doc/src/sgml/gist.sgml#L1184-L1234)). |
| GIN | Accumulates keys and posting lists in an in-memory red-black tree. After each heap tuple, it dumps when tracked allocation reaches the setting; one final dump handles what remains ([gininsert.c#GIN-build-threshold](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L246-L314), [gininsert.c#GIN-final-dump](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L316-L400), [ginbulk.c#BuildAccumulator](../../../../raw/postgres-17/src/backend/access/gin/ginbulk.c#L83-L121)). | Larger memory can reduce accumulator dumps. That first-build gain ends when all input reaches the single final dump, or earlier when dump work no longer dominates. The exact point depends on extracted keys and posting lists, not just heap or final-index size ([gin/README#index-structure](../../../../raw/postgres-17/src/backend/access/gin/README#L17-L26), [gin.sgml#maintenance_work_mem](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L584-L592)). |
| SP-GiST | Inserts tuples directly and resets a per-tuple temporary context; its first build does not read this setting ([spginsert.c#spgbuild](../../../../raw/postgres-17/src/backend/access/spgist/spginsert.c#L55-L147)). | No transaction-2 gain. Its validation `ambulkdelete` does enumerate live TIDs, so the common transaction-3 sort can still benefit ([spgvacuum.c#validation-callback](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L149-L165), [spgvacuum.c#spgbulkdelete](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L908-L932)). |
| BRIN | A serial first build summarizes page ranges directly and does not create a maintenance-memory sort. A parallel first build sorts per-worker summary tuples, dividing the setting among participants and using the full value for the leader merge ([brin.c#serial-and-parallel-build](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1091-L1245), [brin.c#parallel-participant-sort](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2764-L2847), [brin.c#background-worker-share](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2904-L2919)). | More memory can pass the shared 32 MB worker-request thresholds or reduce summary-sort work. It stops helping the first build once useful worker count and sort work are stable. The source itself notes that the 32 MB rule is stricter than BRIN needs. BRIN's validation sort is empty because `brinbulkdelete` reports no per-heap-tuple TIDs, so transaction 3 gets no sort-memory benefit ([brin.c#worker-threshold-caveat](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1153-L1163), [brin.c#brinbulkdelete](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1283-L1301)). |
| contrib Bloom | Keeps a cached page plus a per-tuple context and does not read the setting in its first build ([blinsert.c#blbuild](../../../../raw/postgres-17/contrib/bloom/blinsert.c#L117-L157)). | No transaction-2 gain. Bloom's `ambulkdelete` visits every stored heap TID, so its common validation sort can still benefit ([blvacuum.c#blbulkdelete](../../../../raw/postgres-17/contrib/bloom/blvacuum.c#L26-L103), [index.c#validate_index_callback](../../../../raw/postgres-17/src/backend/catalog/index.c#L3454-L3466)). |

**GIN has an additional validation-time use.** `validate_index()` passes `NULL`
statistics to `ginbulkdelete()`, which first invokes a forced cleanup. In the
ordinary CIC backend that cleanup selects `maintenance_work_mem`; if the pending
list is empty, it returns before allocating the cleanup accumulator. Otherwise
it flushes at the list end or when a complete-row boundary finds tracked memory
at the threshold, resets its temporary context between batches, and in
`full_clean` mode continues until the list is empty
([ginvacuum.c#ginbulkdelete-cleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L571-L602),
[ginfast.c#cleanup-memory-selection](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L780-L840),
[ginfast.c#cleanup-batching](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L843-L1009)).
Its cleanup-specific gain therefore ends when there is no pending list or the
list fits one batch, subject to concurrent fast-update inserts changing that
input. GIN then enumerates posting-list and posting-tree TIDs into the common
validation sort; one heap row represented under several GIN keys can contribute
more than one sort item
([ginvacuum.c#posting-list-callback](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L52-L68),
[gin/README#index-structure](../../../../raw/postgres-17/src/backend/access/gin/README#L17-L26)).

GIN also has an extreme error boundary. If one accumulator posting list has
already grown beyond `INT_MAX` slots and must grow again, the build or cleanup
raises `ERRCODE_PROGRAM_LIMIT_EXCEEDED` and explicitly hints to reduce
`maintenance_work_mem`; a larger value is therefore not unconditionally safer
for a pathological single-key workload
([ginbulk.c#posting-list-limit](../../../../raw/postgres-17/src/backend/access/gin/ginbulk.c#L28-L51)).

**Extension and build boundary.** Core dispatches the first build through the
AM's `ambuild(heap, index, IndexInfo)` callback; the callback API has no memory
argument. In-tree AMs that need the value read the exported global, and a
third-party AM can define a different memory policy. Core's validation
`tuplesort`, however, remains in `validate_index()`
([amapi.h#ambuild_function](../../../../raw/postgres-17/src/include/access/amapi.h#L98-L108),
[miscadmin.h#maintenance_work_mem](../../../../raw/postgres-17/src/include/miscadmin.h#L266-L270),
[index.c#ambuild-dispatch](../../../../raw/postgres-17/src/backend/catalog/index.c#L2976-L3054),
[index.c#validate_index-sort](../../../../raw/postgres-17/src/backend/catalog/index.c#L3390-L3434)).
The similarly named `IndexAmRoutine.amusemaintenanceworkmem` flag does not
control `CREATE INDEX`; parallel VACUUM consults it when dividing worker memory
([amapi.h#amusemaintenanceworkmem](../../../../raw/postgres-17/src/include/access/amapi.h#L249-L260),
[vacuumparallel.c#amusemaintenanceworkmem](../../../../raw/postgres-17/src/backend/commands/vacuumparallel.c#L331-L363)).
The GUC entry and AM API are handwritten source. `guc_tables.c` is compiled
directly by both supported build systems, so this path has no generated catalog
or generated-header dependency
([utils/misc/Makefile#guc_tables](../../../../raw/postgres-17/src/backend/utils/misc/Makefile#L17-L27),
[utils/misc/meson.build#guc_tables](../../../../raw/postgres-17/src/backend/utils/misc/meson.build#L1-L12)).

**What “enough memory” means for a tuplesort.** A serial tuplesort accepts input
in memory until it either finishes or crosses its accounting limit. If all
input fits, it runs one in-memory quicksort. Otherwise it writes sorted runs to
temporary tapes and merges them; more memory can enlarge runs, increase merge
fan-in, and enlarge sequential-read buffers
([tuplesort.c#algorithm](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L9-L80),
[tuplesort.c#spill-transition](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1225-L1331),
[tuplesort.c#performsort](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1381-L1465)).
Once a serial sort's complete input fits, another increase cannot change that
sort's one-quicksort path, although it can still affect another CIC phase or an
automatic worker decision.

Parallel tuplesort has a different endpoint. Every actual scan participant,
including the leader's worker role in a normal build, must emit exactly one tape
run even when its partial input fits in memory; the coordinator then imports one
run per participant and merges them. Nonzero parallel-build temporary-file
activity therefore does not by itself prove that more memory will help
([tuplesort.c#parallel-sort-contract](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L82-L88),
[tuplesort.c#parallel-in-memory-output](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1397-L1428),
[tuplesort.c#leader-takes-worker-runs](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L3095-L3160)).
There is no source-backed conversion such as “set it to the index size”:
B-tree and GiST sort full index tuples, validation sorts pass-by-value encoded
TIDs, BRIN sorts range summaries only in parallel, and GIN uses accumulator
thresholds rather than tuplesort for its first build
([index.c#encoded-validation-TIDs](../../../../raw/postgres-17/src/backend/catalog/index.c#L3390-L3404),
[brin.c#serial-and-parallel-build](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1091-L1245),
[gininsert.c#GIN-build-threshold](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L246-L314)).

**How to find the practical plateau.** Keep the data, index definition,
concurrent workload, storage state, and worker availability comparable. Raise
the session value in steps and observe both memory-sensitive phases:

- `pg_stat_progress_create_index.phase` distinguishes `building index`,
  `index validation: sorting tuples`, the two writer waits, and the final
  old-snapshot wait. It reports blocks, tuples, and lockers, but not sort memory,
  temporary bytes, or participant counts. Progress reporting requires
  `track_activities`; that setting defaults on and is `PGC_SUSET`, so an
  authorized session/transaction change needs neither reload nor restart
  ([monitoring.sgml#progress-columns](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L5832-L6016),
  [monitoring.sgml#create-index-phases](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L6018-L6105),
  [backend_progress.c#track_activities](../../../../raw/postgres-17/src/backend/utils/activity/backend_progress.c#L21-L60),
  [guc_tables.c#track_activities](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1400-L1409)).
- `trace_sort` is `PGC_USERSET`; a session/transaction change needs neither
  reload nor restart. It identifies internal versus external sorts, worker IDs,
  and disk blocks. PostgreSQL 17 compiles this support in by default. For a
  parallel first build, distinguish the one mandatory output run per
  participant from additional run and merge work
  ([guc_tables.c#trace_sort](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1659-L1669),
  [pg_config_manual.h#TRACE_SORT](../../../../raw/postgres-17/src/include/pg_config_manual.h#L376-L380),
  [tuplesort.c#sort-end-report](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L890-L940),
  [tuplesort.c#performsort-trace](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1468-L1483)).
- `log_temp_files` is `PGC_SUSET`; an authorized session/transaction change
  needs neither reload nor restart. It logs each temporary file's final size at
  deletion. `pg_stat_database.temp_files` and `temp_bytes` count those files
  when `track_counts` is on; `track_counts` defaults on and is also `PGC_SUSET`,
  with session/transaction scope and no reload or restart. The database counters
  aggregate all causes and record file volume, not merge passes or wait time
  ([guc_tables.c#log_temp_files](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3554-L3563),
  [config.sgml#log_temp_files](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L7957-L7977),
  [fd.c#ReportTemporaryFileUsage](../../../../raw/postgres-17/src/backend/storage/file/fd.c#L1524-L1538),
  [pgstat_database.c#temp-file-accounting](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_database.c#L170-L185),
  [monitoring.sgml#database-temp-counters](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L3360-L3381),
  [guc_tables.c#track_counts](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1411-L1418)).

Sort tracing does not expose GIN accumulator batch counts or GiST's buffered
`levelStep` choice. GiST emits `DEBUG1` when buffering starts or cannot start,
and buffered GiST creates its own temporary file, so controlled elapsed-time
comparisons remain necessary for those methods
([gistbuild.c#buffering-decision](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L743-L777),
[gistbuild.c#buffering-switch](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L878-L900),
[gistbuildbuffers.c#temporary-buffer-file](../../../../raw/postgres-17/src/backend/access/gist/gistbuildbuffers.c#L40-L81),
[gininsert.c#GIN-build-threshold](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L276-L314)).

Stop increasing when all of the following remain stable across comparable runs:

- the requested and actual useful parallel participant count;
- every serial sort is internal;
- parallel participants produce only their required output runs, without extra
  run/merge work caused by exceeding their shares;
- temporary-file volume attributable to the run no longer falls; and
- validation-phase and total elapsed times no longer improve.

Stop earlier if the host starts swapping. Even at the practical plateau, CIC
still performs its scans, page construction and writes, and transaction waits
([ref/create_index.sgml#memory-warning](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L798-L804),
[indexcmds.c#CIC-build-and-validation](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1642-L1773)).

**Test coverage.** The direct `CREATE INDEX` regression case that changes
`maintenance_work_mem` sets it to 1 MB to force the **non-concurrent hash** sort
and checks correctness. A separate `pageinspect` test uses 128 MB to permit four
workers in a **non-concurrent parallel BRIN** build and tests serial fallback
when workers are unavailable
([create_index.sql#hash-tuplesort](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L364-L380),
[pageinspect/brin.sql#parallel-build](../../../../raw/postgres-17/contrib/pageinspect/sql/brin.sql#L80-L144)).
The direct CIC regression block and CIC isolation/TAP tests exercise lifecycle,
concurrency, and correctness but do not vary this setting or test spill,
worker-memory thresholds, or a performance plateau
([create_index.sql#CIC-tests](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L481-L582),
[multiple-cic.spec](../../../../raw/postgres-17/src/test/isolation/specs/multiple-cic.spec#L1-L43),
[prepared-transactions-cic.spec](../../../../raw/postgres-17/src/test/isolation/specs/prepared-transactions-cic.spec#L1-L37),
[amcheck/002_cic.pl](../../../../raw/postgres-17/contrib/amcheck/t/002_cic.pl#L1-L88)).

### GUCs that affect CIC performance

For a normal PostgreSQL 17 B-tree CIC, the first settings to examine are
`maintenance_work_mem`, `max_parallel_maintenance_workers`,
`min_parallel_table_scan_size`, and the two cluster worker-pool limits. The
first setting controls the build and validation memory paths; the others decide
whether the B-tree first scan can use workers and whether the requested workers
actually launch. BRIN shares the parallel-worker controls. GiST adds
`effective_cache_size`; GIN has a separate concurrent-writer boundary described
below
([planner.c#plan_create_index_workers](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6876-L7018),
[ref/create_index.sgml#memory-and-parallelism](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L798-L844),
[gistbuild.c#gistInitBuffering](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L617-L777)).

This section uses a bounded meaning of “affect CIC performance”: a setting must
change a core CIC phase, a shipped access method, worker availability, storage
placement or I/O, WAL/commit latency, or the command's waits. An index expression
can call arbitrary user code, and a third-party access method receives the
`ambuild` callback and can read its own GUCs, so no core-source list can cover
those extensions
([amapi.h#ambuild_function](../../../../raw/postgres-17/src/include/access/amapi.h#L98-L108),
[index.c#ambuild-dispatch](../../../../raw/postgres-17/src/backend/catalog/index.c#L2976-L3054)).

**Application scope used below.** “Session” means a `PGC_USERSET` setting, or a
`PGC_SUSET` setting changed by an authorized role, with no reload or restart.
Although those contexts also permit transaction-local values, a session value
is the usable per-run scope for CIC: `SET LOCAL` ends at a commit, while CIC
cannot run inside an explicit transaction and commits internally. Parallel
workers restore the leader's serialized GUC state
([ref/set.sgml#SET-scope](../../../../raw/postgres-17/doc/src/sgml/ref/set.sgml#L35-L60),
[ref/set.sgml#LOCAL](../../../../raw/postgres-17/doc/src/sgml/ref/set.sgml#L100-L117),
[utility.c#CIC-transaction-block](../../../../raw/postgres-17/src/backend/tcop/utility.c#L1453-L1463),
[parallel.c#GUC-state](../../../../raw/postgres-17/src/backend/access/transam/parallel.c#L376-L385),
[parallel.c#restore-GUC-state](../../../../raw/postgres-17/src/backend/access/transam/parallel.c#L1449-L1458)).

**Build, scan, and storage settings.**

| GUC | Exact CIC effect and boundary | Default and application |
|---|---|---|
| `maintenance_work_mem` | The primary direct control. It can size the access-method build in transaction 2, caps automatic B-tree/BRIN worker requests at 32 MB per participant including the leader, and sizes transaction 3's serial validation-TID sort. See [How maintenance_work_mem is used and where increases stop helping](#how-maintenance_work_mem-is-used-and-where-increases-stop-helping). | 64 MB; session; no reload or restart ([guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2460-L2474), [planner.c#memory-worker-cap](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6993-L7012), [index.c#validate_index-sort](../../../../raw/postgres-17/src/backend/catalog/index.c#L3390-L3434)). |
| `max_parallel_maintenance_workers` | Caps the number requested by a B-tree or BRIN first build. Zero disables parallel utility workers. It is a request cap, not a guarantee that workers launch ([planner.c#worker-request-cap](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6908-L7018)). | 2; session; no reload or restart ([guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417)). |
| `min_parallel_table_scan_size` | The automatic worker model rejects a heap smaller than this threshold, then adds workers as the estimated heap size crosses successive threefold thresholds. A table `parallel_workers` reloption bypasses this size model and the 32 MB worker-request test, but remains capped by `max_parallel_maintenance_workers` ([allpaths.c#compute_parallel_worker](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4202-L4278), [planner.c#parallel_workers-override](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6973-L7012)). | 8 MB; session; no reload or restart ([guc_tables.c#parallel-scan-thresholds](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3520-L3539)). |
| `max_parallel_workers`; `max_worker_processes` | The first is the live parallel-worker cap checked when CIC registers workers. The second sizes the shared background-worker slot pool. Pool contention can make a request launch fewer workers, and B-tree/BRIN can fall back to serial execution ([bgworker.c#worker-slot-pool](../../../../raw/postgres-17/src/backend/postmaster/bgworker.c#L146-L174), [bgworker.c#parallel-and-slot-caps](../../../../raw/postgres-17/src/backend/postmaster/bgworker.c#L969-L1039), [nbtsort.c#parallel-fallback](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1390-L1594)). | Both default to 8. `max_parallel_workers` is session-scoped; `max_worker_processes` is `postmaster` context and needs restart ([guc_tables.c#worker-pools](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3163-L3172), [guc_tables.c#parallel-worker-pool](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3430-L3438)). |
| `effective_cache_size` | Only GiST's buffered build reads it. It helps choose when `auto` switches to buffering and the largest `levelStep` whose subtree should fit in cache. It neither reserves cache nor affects the other shipped AM build algorithms ([gistbuild.c#gistInitBuffering](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L670-L757), [gistbuild.c#auto-switch](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L878-L900)). | 524,288 blocks, normally 4 GB at 8 kB per block; session; no reload or restart ([cost.h#DEFAULT_EFFECTIVE_CACHE_SIZE](../../../../raw/postgres-17/src/include/optimizer/cost.h#L31-L35), [guc_tables.c#effective_cache_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3518)). |
| `shared_buffers` | Its `NBuffers` value directly changes two CIC decisions: a heap scan gets the bulk-read/synchronized-scan path only above `NBuffers / 4`, and a permanent hash-index build caps its sort-selection threshold at `NBuffers`. The effect is therefore AM- and table-size-dependent, not “more is always faster” ([heapam.c#bulk-and-sync-threshold](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L433-L496), [hash.c#hashbuild-sort-choice](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L139-L166)). | 16,384 blocks, normally 128 MB; `postmaster` context; restart ([guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2257-L2270)). |
| `io_combine_limit` | Both heap scans use v17's sequential read stream. This setting caps how many adjacent blocks the stream can combine into one read operation; the stream captures the value when each scan starts ([heapam.c#sequential-read-stream](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1233-L1259), [read_stream.c#combined-read-limit](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L360-L376), [read_stream.c#captured-GUCs](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L522-L537)). | 128 kB on the normal 8 kB build, subject to the platform maximum; session; no reload or restart ([guc_tables.c#io_combine_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3138-L3150), [bufmgr.h#DEFAULT_IO_COMBINE_LIMIT](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L157-L170)). |
| `effective_io_concurrency` | The heap read stream selects the tablespace's `effective_io_concurrency`, not `maintenance_io_concurrency`, because the heap AM passes `READ_STREAM_SEQUENTIAL` without `READ_STREAM_MAINTENANCE`. It still derives `max_ios` and queue size from the effective setting, but sequential mode disables explicit prefetch advice and drives look-ahead toward `io_combine_limit`; treat this as a secondary, platform-dependent control ([read_stream.c#I/O-setting-selection](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L407-L478), [read_stream.c#sequential-advice-boundary](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L508-L536), [read_stream.c#sequential-distance](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L704-L728)). | 1 on builds with prefetch support, otherwise 0; session; no reload or restart. A tablespace reloption of the same name overrides the GUC ([bufmgr.h#I/O-concurrency-defaults](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L157-L166), [guc_tables.c#effective_io_concurrency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3109-L3121), [spccache.c#tablespace-I/O-override](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L215-L236)). |
| `synchronize_seqscans` | For a sufficiently large heap, it can make the first scan start at the location of another synchronized scan and wrap around, sharing I/O. It does not reduce the number of pages read. B-tree, hash, GiST, SP-GiST, Bloom, and parallel BRIN permit it; GIN and serial BRIN explicitly require physical TID/range order and disable it. Validation also disables it ([heapam.c#syncscan-choice](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L467-L496), [gininsert.c#no-syncscan](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L376-L384), [brin.c#serial-scan-order](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1217-L1224), [heapam_handler.c#validation-order](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1791-L1806)). | On; session; no reload or restart ([guc_tables.c#synchronize_seqscans](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1765-L1774)). |
| `temp_tablespaces`; `temp_file_limit` | `temp_tablespaces` chooses storage for tuplesort spills, parallel worker tapes, and GiST's buffered-build temporary file. `temp_file_limit` does not throttle work: each process errors when its accounted temporary files exceed the limit, which can leave CIC's already-created index invalid ([tuplesort.c#PrepareTempTablespaces](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1956-L1966), [fileset.c#parallel-temp-tablespaces](../../../../raw/postgres-17/src/backend/storage/file/fileset.c#L42-L72), [fd.c#temp-file-limit](../../../../raw/postgres-17/src/backend/storage/file/fd.c#L2211-L2236), [indexcmds.c#post-catalog-commit](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1594-L1658)). | `temp_tablespaces` defaults to the database default tablespace and is session-scoped. `temp_file_limit` defaults to unlimited (`-1`), is `PGC_SUSET`, and is session-scoped for an authorized role; neither needs reload or restart ([guc_tables.c#temp_file_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2504-L2513), [guc_tables.c#temp_tablespaces](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4148-L4156)). |
| `default_tablespace` | If `CREATE INDEX` omits `TABLESPACE`, this setting selects the target index tablespace. It changes where index pages are written and therefore their I/O cost, not the CIC algorithm; an explicit `TABLESPACE` overrides it ([indexcmds.c#tablespace-selection](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L755-L784), [ref/create_index.sgml#tablespace](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L363-L370)). | Empty string, meaning the database default; session; no reload or restart ([guc_tables.c#default_tablespace](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4137-L4146)). |
| `gin_pending_list_limit`; writer-side `work_mem` | Neither sizes GIN's transaction-2 bulk build. After `indisready` commits, concurrent writers using GIN fast update can append to the pending list. Their backend's `gin_pending_list_limit` (unless the index reloption overrides it) decides when regular cleanup starts, and that regular cleanup uses the writer's `work_mem`. CIC validation later forces a complete cleanup with the CIC backend's `maintenance_work_mem`, so these writer-side values can change how much cleanup transaction 3 inherits ([gin_private.h#pending-list-limit](../../../../raw/postgres-17/src/include/access/gin_private.h#L26-L45), [ginfast.c#regular-cleanup-threshold](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L448-L471), [ginfast.c#cleanup-memory-selection](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L807-L840), [ginvacuum.c#validation-cleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L591-L602)). | Both default to 4 MB and are session-scoped with no reload or restart; the relevant values belong to concurrent writer sessions, while the per-index `gin_pending_list_limit` reloption takes precedence ([guc_tables.c#work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2447-L2458), [guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585)). |

**WAL, checkpoints, and the four commits.** Permanent CIC builds generate WAL.
For example, B-tree's bulk writer logs batches as forced page images, while
GiST, GIN, and SP-GiST can log their built page ranges after the first build
([bulk_write.c#bulk-WAL](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L243-L310),
[gistbuild.c#build-WAL](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L328-L337),
[gininsert.c#build-WAL](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L408-L417),
[spginsert.c#build-WAL](../../../../raw/postgres-17/src/backend/access/spgist/spginsert.c#L132-L141)).
These settings can therefore move elapsed time without changing the CIC state
machine:

| GUC | Exact CIC effect and boundary | Default and application |
|---|---|---|
| `synchronous_commit`; `synchronous_standby_names` | Each of CIC's four transaction boundaries uses the ordinary commit path. A phase that wrote WAL can flush and wait there; transaction 3 might have no WAL to flush when validation inserts nothing. `synchronous_commit = off` permits asynchronous local commit; other modes retain local flush and can request increasing levels of synchronous-standby confirmation. `synchronous_standby_names` matters only when synchronous replication is requested. These settings change commit latency and durability/confirmation semantics, not scan or sort work ([indexcmds.c#internal-commits](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1615-L1773), [xact.c#sync-versus-async-commit](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L1462-L1521), [syncrep.c#SyncRepWaitForLSN](../../../../raw/postgres-17/src/backend/replication/syncrep.c#L133-L181)). | `synchronous_commit` defaults to `on`; session; no reload or restart. `synchronous_standby_names` defaults empty; `sighup` context; reload ([guc_tables.c#synchronous_commit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4925-L4933), [guc_tables.c#synchronous_standby_names](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4571-L4580)). |
| `wal_compression` | B-tree and sorted-GiST bulk writes, plus the end-of-build page-range paths above, force full-page images. Enabling WAL compression can trade compression CPU for fewer WAL bytes when those images compress; the result is data- and codec-dependent ([xloginsert.c#forced-image](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L598-L688), [xloginsert.c#log_newpages](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L1170-L1217)). | Off; `PGC_SUSET`; session for an authorized role; no reload or restart ([guc_tables.c#wal_compression](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4976-L4983)). |
| `wal_buffers`; `wal_sync_method` | These are generic WAL-path controls. The former sizes shared WAL buffering for the build's WAL stream; the latter chooses the local flush method used by synchronous commits. Neither determines CIC worker count or scan shape ([guc_tables.c#wal_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2891-L2900), [guc_tables.c#wal_sync_method](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L5026-L5033)). | `wal_buffers` defaults to `-1` (automatic); `postmaster` context; restart. `wal_sync_method` uses the platform default; `sighup` context; reload. |
| `max_wal_size`; `checkpoint_timeout`; `checkpoint_completion_target`; `checkpoint_flush_after` | The first two influence automatic checkpoint frequency; `checkpoint_completion_target` paces checkpoint writes, while `checkpoint_flush_after` controls periodic writeback requests. This matters directly to AM paths using the bulk writer: if a checkpoint starts after bulk writing began, `smgr_bulk_finish()` performs an immediate relation sync because that checkpoint missed earlier writes. The settings are cluster-wide and the effect is not monotonic ([bulk_write.c#checkpoint-crossing-sync](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L124-L223), [config.sgml#checkpoint-settings](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L3605-L3662), [config.sgml#max_wal_size](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L3702-L3719)). | 1 GB, 5 minutes, `0.9`, and a platform default respectively; all are `sighup` context and need reload, not restart ([guc_tables.c#checkpoint-size-and-time](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2842-L2888), [guc_tables.c#checkpoint_completion_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3916-L3924)). |
| `commit_delay`; `commit_siblings` | When enabled, the WAL flush path deliberately sleeps before a group-commit flush if enough other transactions are active. It can improve aggregate commit throughput while increasing each affected CIC transaction's latency; the defaults do not add a delay ([xlog.c#group-commit-delay](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L2869-L2888)). | `commit_delay = 0`; `PGC_SUSET`, authorized session. `commit_siblings = 5`; session. Neither needs reload or restart ([guc_tables.c#commit-delay](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2980-L3001)). |

`fsync` and `full_page_writes` can change generic durability I/O, but disabling
either is not a production CIC tuning method. Both are `sighup` settings and
need reload. In particular, `REGBUF_FORCE_IMAGE` makes bulk-build page images
independent of `full_page_writes`; turning that GUC off does not remove those
records. PostgreSQL's own documentation warns that disabling these protections
can produce unrecoverable or silent corruption after a system failure
([xloginsert.c#force-image-wins](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L598-L610),
[guc_tables.c#fsync-and-full_page_writes](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1096-L1107),
[guc_tables.c#full_page_writes](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1156-L1168),
[config.sgml#durability-warning](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L3022-L3080),
[config.sgml#full-page-write-warning](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L3294-L3329)).

**Wait and cancellation settings.** These settings do not make the build path
faster. They bound how long it may run or wait, change deadlock detection and
logging, or move time into commit confirmation:

| GUC | CIC behavior | Default and application |
|---|---|---|
| `statement_timeout` | Covers the client statement across the internal commits, scans, and three waits. Expiry cancels the command; it is an end-to-end cap, not a per-phase budget ([postgres.c#statement-timeout-lifetime](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L2778-L2807), [postgres.c#enable_statement_timeout](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L5247-L5278)). | 0 (disabled); session; no reload or restart ([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620)). |
| `transaction_timeout` | CIC starts a new timer for each internal transaction and disables it at each commit. It is therefore a per-internal-transaction cap, not a cap on the whole command. Expiry terminates the connection with `FATAL` ([xact.c#transaction-timeout-start](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L2168-L2178), [xact.c#transaction-timeout-stop](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L2308-L2318), [postgres.c#transaction-timeout-error](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L3453-L3463)). | 0 (disabled); session; no reload or restart ([guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653)). |
| `lock_timeout` | Applies to the initial table-lock acquisition and to each individual VXID lock used by both writer waits and `WaitForOlderSnapshots`. It restarts per lock acquisition, so it is not an aggregate cap across all blockers or all three waits ([lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-17/src/backend/storage/lmgr/lmgr.c#L889-L972), [indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L433-L492), [lock.c#VirtualXactLock](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L4550-L4662), [proc.c#lock-timeout-timer](../../../../raw/postgres-17/src/backend/storage/lmgr/proc.c#L1273-L1307)). | 0 (disabled); session; no reload or restart ([guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)). |
| `deadlock_timeout`; `log_lock_waits` | The first controls when PostgreSQL checks a lock wait for deadlock; a shorter value does not end a non-deadlocked wait and can run checks more often. The second logs waits that survive the deadlock-timeout interval. These are detection/observability controls, not throughput controls ([proc.c#deadlock-check-timer](../../../../raw/postgres-17/src/backend/storage/lmgr/proc.c#L1273-L1325), [proc.c#long-wait-logging](../../../../raw/postgres-17/src/backend/storage/lmgr/proc.c#L1491-L1525)). | 1 second and off; both are `PGC_SUSET`, so an authorized role can use session scope with no reload or restart ([guc_tables.c#deadlock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2146-L2157), [guc_tables.c#log_lock_waits](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1512-L1521)). |
| `idle_in_transaction_session_timeout` | It does not fire in the actively running CIC backend. In a different session, it can eventually terminate an idle-in-transaction blocker and thereby shorten a CIC wait; that is blocker-side policy, not a CIC speed setting ([postgres.c#idle-in-transaction-timer](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L4619-L4646)). | 0 (disabled); session in the blocker; no reload or restart ([guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2632-L2642)). |

A timeout after transaction 1 has committed can leave the already-created index
invalid, just like another post-commit error; see [Failure handling](#failure-handling).
The timeout is therefore a completion policy, not free acceleration
([indexcmds.c#post-catalog-commit](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1594-L1658),
[index.c#index-state-transitions](../../../../raw/postgres-17/src/backend/catalog/index.c#L3469-L3547)).

**Settings that are easy to confuse with CIC controls.**

- `min_parallel_index_scan_size` does not affect the worker request. CIC passes
  `index_pages = -1` to `compute_parallel_worker()`, so only
  `min_parallel_table_scan_size` participates. Likewise,
  `max_parallel_workers_per_gather` and `parallel_leader_participation` control
  `Gather`/`Gather Merge` query execution, not the utility build's private
  parallel machinery
  ([planner.c#heap-only-worker-model](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6987-L7012),
  [allpaths.c#index-threshold-guard](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4216-L4269),
  [config.sgml#query-parallel-settings](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L2822-L2860),
  [config.sgml#parallel_leader_participation](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L2923-L2941)).
- `maintenance_io_concurrency` is not selected by the v17 CIC heap read streams:
  they pass `READ_STREAM_SEQUENTIAL`, not `READ_STREAM_MAINTENANCE`. The
  implementation instead reaches the effective-I/O branch described above
  ([heapam.c#CIC-read-stream-flags](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1237-L1259),
  [read_stream.c#I/O-setting-selection](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L425-L439)).
- `work_mem` does not size the common CIC validation sort. A unique B-tree build
  creates a secondary `work_mem` spool, but the concurrent MVCC scan supplies no
  dead tuples to it and the leader discards it empty. Its relevant exception is
  the concurrent-writer GIN cleanup described above
  ([nbtsort.c#secondary-sort](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L433-L505),
  [heapam_handler.c#concurrent-tuples-are-alive](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1621-L1629)).
- `autovacuum_work_mem`, the `vacuum_cost_*` delay settings, and `temp_buffers`
  do not size or throttle CIC's own core build. Temporary tables have already
  fallen back to non-concurrent creation; validation's forced GIN cleanup
  chooses `maintenance_work_mem` in the ordinary CIC backend; and
  `vacuum_delay_point()` returns without a cost delay when `VacuumCostActive` is
  false
  ([indexcmds.c#temp-fallback](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L605-L615),
  [ginfast.c#forced-cleanup-memory](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L807-L828),
  [vacuum.c#vacuum_delay_point](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2383-L2419)).
- `wal_level = minimal` does not unlock the usual “new relation in this
  transaction” WAL skip. CIC creates the index in transaction 1 but builds it
  in transaction 2; at build time the permanent relation is no longer new in
  the current transaction, so `RelationNeedsWAL()` remains true. Consequently,
  `wal_skip_threshold` is not a CIC build-memory or WAL-volume lever
  ([indexcmds.c#catalog-then-build-transactions](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1594-L1682),
  [rel.h#RelationNeedsWAL](../../../../raw/postgres-17/src/include/utils/rel.h#L617-L631)).

The observation settings already described in the memory section —
`track_activities`, `trace_sort`, `log_temp_files`, and `track_counts` — expose
progress and spills but do not alter CIC's correctness algorithm. Enabling
`track_io_timing` or `track_wal_io_timing` adds I/O measurements and may itself
have significant timing-call overhead on some platforms. Both are `PGC_SUSET`,
default off, and available to an authorized session without reload or restart
([guc_tables.c#I/O-timing](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1420-L1436),
[config.sgml#I/O-timing-overhead](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L8451-L8499)).

**Practical priority.** Tune and measure in this order:

1. `maintenance_work_mem`, while checking the separate first-build and
   validation phases and avoiding swapping
   ([ref/create_index.sgml#memory-warning](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L798-L804)).
2. For B-tree or BRIN, the request and availability chain:
   `min_parallel_table_scan_size`, `max_parallel_maintenance_workers`,
   `max_parallel_workers`, and `max_worker_processes`; stop adding workers when
   CPU or I/O is already saturated
   ([config.sgml#parallel-maintenance](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L2864-L2898)).
3. Apply the AM-specific boundary: keep `effective_cache_size` representative
   of usable cache for buffered GiST, and measure writer-side pending-list
   settings for a write-heavy GIN CIC
   ([gistbuild.c#gistInitBuffering](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L670-L757),
   [ginfast.c#pending-list-threshold](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L448-L471)).
4. Put index output and sort spills on suitable storage, then measure
   `io_combine_limit`, checkpoint crossings, WAL volume, and commit waits rather
   than weakening durability settings
   ([ref/create_index.sgml#tablespace](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L363-L370),
   [bulk_write.c#checkpoint-crossing-sync](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L124-L223)).
5. Diagnose blockers separately. Memory and workers cannot shorten either
   `WaitForLockers` call or the old-snapshot wait
   ([indexcmds.c#CIC-waits](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1642-L1768)).

The in-tree tests establish lifecycle and correctness, not comparative GUC
performance. The direct CIC regression, isolation, and TAP tests do not sweep
this matrix, so workload-specific elapsed-time and resource measurements remain
necessary
([create_index.sql#CIC-tests](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L481-L582),
[multiple-cic.spec](../../../../raw/postgres-17/src/test/isolation/specs/multiple-cic.spec#L1-L43),
[prepared-transactions-cic.spec](../../../../raw/postgres-17/src/test/isolation/specs/prepared-transactions-cic.spec#L1-L37),
[amcheck/002_cic.pl](../../../../raw/postgres-17/contrib/amcheck/t/002_cic.pl#L1-L88)).

### All steps and locks required on the table

Two distinct lock layers act on the **heap table**:

1. A **transaction-level** `ShareUpdateExclusiveLock`, acquired by `table_open`
   at the start of the command
   ([indexcmds.c:678-679](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L678-L679))
   and re-acquired inside `index_concurrently_build` and `validate_index`;
   released at each `CommitTransactionCommand`.
2. A **session-level** `ShareUpdateExclusiveLock`
   (`LockRelationIdForSession`) that spans the gaps between transactions so the
   table cannot be dropped mid-build; released by `UnlockRelationIdForSession`
   at the very end.

`ShareUpdateExclusiveLock` is the same level `VACUUM (non-FULL)` and `ANALYZE`
use ([lockdefs.h:36-46](../../../../raw/postgres-17/src/include/storage/lockdefs.h#L36-L46)).
Its conflict row determines what it lets through and what it blocks
([lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L64-L103)):

| Other lock (command) | Conflicts with CIC's `ShareUpdateExclusiveLock`? |
|---|---|
| `AccessShareLock` (`SELECT`) | No — reads continue |
| `RowShareLock` (`SELECT FOR UPDATE/SHARE`) | No |
| `RowExclusiveLock` (`INSERT`/`UPDATE`/`DELETE`) | No — **writes continue** |
| `ShareUpdateExclusiveLock` (another CIC, `VACUUM`, `ANALYZE`) | **Yes** — only one at a time |
| `ShareLock` (plain `CREATE INDEX`) | **Yes** |
| `ShareRowExclusiveLock` / `ExclusiveLock` / `AccessExclusiveLock` (most `ALTER TABLE`, `DROP`) | **Yes** — schema changes blocked |

Because `ShareUpdateExclusiveLock` is **self-conflicting**
([lock.c:77-81](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L77-L81)),
only one concurrent build can run on a given table at a time.

The three "waits" are **not** table locks. `WaitForLockers` calls
`WaitForLockersMultiple`, which obtains the current conflicting lock holders and
waits on their virtual transaction IDs; it explicitly does not try to acquire the
relation locks itself
([lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-17/src/backend/storage/lmgr/lmgr.c#L889-L900),
[lmgr.c:914-923](../../../../raw/postgres-17/src/backend/storage/lmgr/lmgr.c#L914-L923),
[lmgr.c:935-952](../../../../raw/postgres-17/src/backend/storage/lmgr/lmgr.c#L935-L952)).
Waits 1 and 2 pass `ShareLock`, which conflicts with `RowExclusiveLock`, so they
wait out all current **writers**
([lock.c:82-86](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L82-L86)).
Wait 3 (`WaitForOlderSnapshots`) waits on transactions holding old snapshots,
excluding autovacuum workers, lazy `VACUUM`, and — present in v17 but absent in
v12 — other safe concurrent index builds
(`PROC_IS_AUTOVACUUM | PROC_IN_VACUUM | PROC_IN_SAFE_IC`)
([indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L439-L442)).

End-to-end table lock timeline:

| Phase | Table (heap) locks | Wait performed | Catalog effect |
|---|---|---|---|
| Txn 1: create catalog row | Txn `ShareUpdateExclusiveLock` + session `ShareUpdateExclusiveLock` taken ([:678-679](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L678-L679), [:1599](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1615)) | — | `indislive=t`, `indisready=f`, `indisvalid=f` |
| (commit 1) | Txn lock released; session lock held | — | empty index visible |
| Txn 2: build | Heap `ShareUpdateExclusiveLock`; index `RowExclusiveLock` ([index.c:1513-1526](../../../../raw/postgres-17/src/backend/catalog/index.c#L1513-L1526)) | Wait 1: `WaitForLockers(ShareLock)` waits out writers | first scan; then `indisready=t` |
| (commit 2) | Txn lock released; session lock held | — | `indisready` visible |
| Txn 3: validate | Heap `ShareUpdateExclusiveLock`; index `RowExclusiveLock` ([index.c:3353](../../../../raw/postgres-17/src/backend/catalog/index.c#L3353)) | Wait 2: `WaitForLockers(ShareLock)` waits out writers | second scan inserts missing tuples |
| (commit 3) | Txn lock released; session lock held | — | reference snapshot dropped |
| Txn 4: mark valid | Session `ShareUpdateExclusiveLock` still held | Wait 3: `WaitForOlderSnapshots(limitXmin)` (ignores safe CIC/RIC) | `indisvalid=t`; relcache inval; session lock released |

Throughout, the **only** lock the table ever carries is
`ShareUpdateExclusiveLock` (transaction-level within each phase, session-level
across the gaps). DML conflicts with none of these — the whole point of CIC.

### What changed from PostgreSQL 12

The CIC algorithm — four transactions, two scans, three waits, the
`ShareUpdateExclusiveLock` footprint, and the `indislive`/`indisready`/`indisvalid`
progression shape — remains recognizable from v12. (For the v12 trace, see
[How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 12](../../../v12/questions/indexing/create-index-concurrently.md).)
PostgreSQL 17 differs in one snapshot-wait optimization and in catalog/security
plumbing around the same phases.

**1. `PROC_IN_SAFE_IC`: a CIC build can be ignored by other concurrent builds
(PostgreSQL 14).** In v12, the final snapshot wait `WaitForOlderSnapshots`
excluded only autovacuum and lazy `VACUUM`, so two CIC builds running on
different tables would wait on each other's snapshots, wasting time and risking
deadlock. PostgreSQL 14 added the `PROC_IN_SAFE_IC` status flag
([proc.h:57-62](../../../../raw/postgres-17/src/include/storage/proc.h#L57-L62)):
a CIC (or REINDEX CONCURRENTLY) on a **plain** index — no expressions, no partial
predicate — advertises it via `set_indexsafe_procflags()`
([indexcmds.c#set_indexsafe_procflags](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L4473-L4505)),
called once per internal transaction after each commit
([:1605-1607](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1621-L1623),
[:1677-1679](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1693-L1695),
[:1737-1739](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1753-L1755)).
`WaitForOlderSnapshots` then adds `PROC_IN_SAFE_IC` to the processes it ignores
([:439-442](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L439-L442)),
because such a process "won't examine any data outside the table they're
indexing"
([:412-419](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L412-L419)).
The v17 docs spell this out: after the second scan the build waits for snapshots
predating it "including transactions used by any phase of concurrent index builds
on other tables, **if the indexes involved are partial or have columns that are
not simple column references**"
([ref/create_index.sgml:627-643](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L627-L643)).
Introduced by commit `c98763bf` (2020-11-25, "Avoid spurious waits in concurrent
indexing"; first shipped in PostgreSQL 14), extended to REINDEX CONCURRENTLY by
`f9900df5` (2021-01-15, "Avoid spurious wait in concurrent reindex").

Scope of the optimization: it only shortens **Wait 3** (the snapshot wait) and
only when the *other* builds are on safe indexes. Waits 1 and 2 use
`WaitForLockers`, which is lock-based (`GetLockConflicts`) and is **not** affected
by `PROC_IN_SAFE_IC` — they still wait out all writers. The v17 `multiple-cic`
isolation test deliberately uses **partial** indexes (`WHERE ...`), which are not
safe, so the two builds still interact and one is expected to wait
([multiple-cic.spec](../../../../raw/postgres-17/src/test/isolation/specs/multiple-cic.spec#L1-L43)).

**2. A `VACUUM`-ignores-CIC attempt was added and then reverted — so this did
NOT change.** PostgreSQL 14 also tried to let `VACUUM` advance its xmin horizon
past safe CIC/RIC processes, but that was reverted by commit `e28bb885`
(2022-05-31, "Revert changes to CONCURRENTLY that \"sped up\" Xmin advance"),
which is present in the v17 tree, because it could let a concurrently-built index
miss heap tuples that were HOT-pruned during the build. So in v17, exactly as in
v12, a running CIC still holds back `VACUUM`'s horizon; `PROC_IN_SAFE_IC` only
affects other *concurrent index* operations' snapshot waits, not `VACUUM`.

**3. `index_set_state_flags` is transactional in v17 (PostgreSQL 14).**
PostgreSQL 14 commit `83158f74d3a` (2020-09-14, "Make
index_set_state_flags() transactional") changed the state-flag helper used by
CIC. In v17, `index_set_state_flags` fetches a writable copy of the `pg_index`
tuple, mutates `indisready` or `indisvalid`, and stores the result with
`CatalogTupleUpdate`
([index.c#index_set_state_flags](../../../../raw/postgres-17/src/backend/catalog/index.c#L3469-L3547)).
That means the phase-2 ready flip and phase-4 valid flip follow normal
transaction commit/abort semantics in v17. It does not change the number of CIC
transactions, scans, waits, or table locks.

**4. The flag lives in `PGPROC`, not `PGXACT` (mechanical, PostgreSQL 14).**
v12 kept per-backend vacuum state in `MyPgXact->vacuumFlags` (the `PGXACT`
array). PostgreSQL 14's snapshot-scalability work (commit `5788e258`, 2020-08-14)
moved that state to `PGPROC`/`ProcGlobal`, and `set_indexsafe_procflags` now sets
`MyProc->statusFlags` and mirrors it into `ProcGlobal->statusFlags[]`
([indexcmds.c:4501-4503](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L4501-L4503)).
This is why DefineIndex's final-phase assertion reads `MyProc->xmin` in v17 where
v12 read `MyPgXact->xmin`.

**5. The concurrent build runs index/predicate functions under the owner with a
restricted search path (security hardening, post-v12).** v17's
`index_concurrently_build` switches to the table owner's userid and calls
`RestrictSearchPath()` before building
([index.c:1520-1524](../../../../raw/postgres-17/src/backend/catalog/index.c#L1520-L1524));
v12's `index_concurrently_build` did neither. This does not change the lock or
transaction structure.

### Failure handling

If the build or validation fails, CIC leaves behind an **invalid** index: it has
a catalog row but `indisvalid = false`, so the planner ignores it while it still
adds write overhead. The documented recovery is to `DROP INDEX` and retry, or
rebuild with `REINDEX INDEX CONCURRENTLY`
([ref/create_index.sgml:645-667](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L645-L667)).
For a unique index, the uniqueness constraint is enforced from the start of the
second scan, so violations can surface in other sessions before the index is
usable, and a failed second scan leaves an invalid index that still enforces
uniqueness
([ref/create_index.sgml:669-677](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L669-L677)).

### Test coverage

- Regression: `create_index.sql` builds empty-table, unique, partial, and
  expression indexes concurrently, defaults the index name, and asserts that CIC
  fails inside a `BEGIN; ... COMMIT;` block
  ([create_index.sql:488-525](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L488-L525)).
- Isolation: `multiple-cic.spec` runs two concurrent builds (on partial indexes)
  simultaneously
  ([multiple-cic.spec](../../../../raw/postgres-17/src/test/isolation/specs/multiple-cic.spec#L1-L43)),
  and `prepared-transactions-cic.spec` verifies CIC waits correctly for a prepared
  (two-phase-commit) transaction
  ([prepared-transactions-cic.spec](../../../../raw/postgres-17/src/test/isolation/specs/prepared-transactions-cic.spec#L1-L37)).

## Context Reviewed

- `wiki/versions.md`, `wiki/index.md`, `wiki/v17/index.md`, and the latest 20
  `wiki/log.md` entries (navigation only).
- Pinned checkout `raw/postgres-17/` at commit
  `786db8dcf168bd9df8f55047337525ac19118b1c` (PostgreSQL 17.11,
  `REL_17_11-7-g786db8dcf16`); repinned from
  `54eeefaedbee0385529f3edf321bb99e49232aaa` (17.10) on 2026-08-17.
- 2026-08-17 repin review: `d1c8aa0b09f` (CVE-2026-6470, back-patched through
  v14) is the one commit in the `54eeefaed..786db8dcf16` range that changed a
  claim on this page; it adds the type-`USAGE` precondition recorded above,
  reached only when `DefineIndex` is called with `check_rights = true`. The four
  transactions, two scans, three waits, flag progression, and GUC material are
  unchanged in the range. A pre-existing `index.c#index_create` anchor pointed
  into that function's header comment and now spans its contract note and
  signature.
- `DefineIndex`'s concurrent branch, `WaitForOlderSnapshots`, and
  `set_indexsafe_procflags` in `src/backend/commands/indexcmds.c`.
- `UpdateIndexRelation`/`index_create`, `index_concurrently_build`,
  `index_build`, `validate_index`, and `index_set_state_flags` in
  `src/backend/catalog/index.c`; heap build/validation scans in
  `src/backend/access/heap/heapam_handler.c`.
- Whole-checkout use-site searches for the follow-up's build, parallelism, I/O,
  storage, GIN, WAL, checkpoint, commit, timeout, and observation GUCs, followed
  through their handwritten `guc_tables.c` entries and exported globals.
- Parallel request and launch paths in `planner.c`, `allpaths.c`, `parallel.c`,
  `bgworker.c`, and the B-tree/BRIN leader and worker implementations, including
  the table `parallel_workers` reloption and query-parallel exclusions.
- Heap scan initialization and read-ahead in `heapam_handler.c`, `heapam.c`,
  `read_stream.c`, `spccache.c`, and `fd.c`, including `NBuffers` thresholds,
  synchronized scans, combined I/O, tablespace overrides, and temp-file limits.
- First-build and validation callbacks for B-tree, hash, GiST, GIN, SP-GiST,
  BRIN, and contrib Bloom, including GIN writer-side pending-list cleanup and
  BRIN's parallel summary sort and empty validation enumeration.
- WAL and commit paths in `bulk_write.c`, `xloginsert.c`, `xlog.c`, `xact.c`,
  and `syncrep.c`; checkpoint-crossing sync; forced page images; compression;
  local and synchronous-replication waits; transaction and lock timeout paths.
- AM interfaces and flags in `src/include/access/amapi.h`, `IndexInfo` in
  `src/include/nodes/execnodes.h`, and relevant globals/macros in
  `miscadmin.h`, `bufmgr.h`, `rel.h`, `cost.h`, and `gin_private.h`.
- `PROC_IN_SAFE_IC` in `src/include/storage/proc.h`; `LockConflicts`,
  `VirtualXactLock`, and `ProcSleep`; lock-mode definitions in
  `src/include/storage/lockdefs.h`.
- Docs: `config.sgml`, `ref/set.sgml`, `ref/create_index.sgml`,
  `monitoring.sgml`, `gist.sgml`, `gin.sgml`, and the GIN README.
- Tests: direct CREATE INDEX/CIC regression and isolation inputs, contrib
  `pageinspect`'s parallel BRIN test, and contrib `amcheck`'s CIC TAP test. The
  direct CIC tests were checked for, but do not contain, a comparative sweep of
  the follow-up's GUC matrix.
- v12 vs v17 deltas established by the earlier review from the
  `raw/postgres-17/` checkout's own commit history (`c98763bf`, `f9900df5`,
  `e28bb885`, `83158f74d3a`, `5788e258`), each verified present with `git show`
  / `git tag --contains`.

## Evidence Map

| Claim | Source |
|---|---|
| Table lock is `ShareUpdateExclusiveLock` for concurrent | [indexcmds.c:678-679](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L678-L679) |
| `safe_index` true only for non-expression, non-partial indexes | [indexcmds.c:1144-1146](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1144-L1146) |
| Since 17.11 (`d1c8aa0b09f`), an expression or predicate type the role lacks `USAGE` on fails before `index_create()`; only `check_rights = true` callers check it | [indexcmds.c:931-945](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L931-L945), [index.c:726-728](../../../../raw/postgres-17/src/backend/catalog/index.c#L726-L728), [utility.c:1543-1553](../../../../raw/postgres-17/src/backend/tcop/utility.c#L1543-L1553), [tablecmds.c:19011-19015](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L19011-L19015), [privileges.out:1357-1358](../../../../raw/postgres-17/src/test/regress/expected/privileges.out#L1357-L1358) |
| Four-transaction structure; session lock; three waits | [indexcmds.c:1615-1788](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1615-L1788) |
| Build sets `indisready`; validate inserts missing tuples | [index.c:1499-1556](../../../../raw/postgres-17/src/backend/catalog/index.c#L1499-L1556), [index.c:3325-3431](../../../../raw/postgres-17/src/backend/catalog/index.c#L3325-L3431) |
| `maintenance_work_mem` is `PGC_USERSET`, defaults to 64 MB, and has a 64 kB minimum | [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2460-L2474) |
| CIC's AM build and validation memory windows are separated by a commit and writer wait | [indexcmds.c:1678-1728](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1678-L1728), [index.c:1499-1557](../../../../raw/postgres-17/src/backend/catalog/index.c#L1499-L1557) |
| Validation uses a full-budget serial encoded-TID sort | [index.c:3390-3434](../../../../raw/postgres-17/src/backend/catalog/index.c#L3390-L3434) |
| Automatic B-tree/BRIN workers require 32 MB per requested participant, leader included | [planner.c:6993-7018](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6993-L7018) |
| B-tree planned-vs-launched shares and serial fallback | [nbtsort.c:1390-1594](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1390-L1594), [nbtsort.c:1683-1725](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1683-L1725), [nbtsort.c:1823-1829](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1823-L1829) |
| Parallel participants always emit one tape run | [tuplesort.c:1397-1428](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1397-L1428), [tuplesort.c:3095-3160](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L3095-L3160) |
| Hash has a separate memory/buffer-capped sort-selection threshold | [hash.c:139-166](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L139-L166) |
| GiST can use sorted, direct-insert, or maintenance-memory-limited buffered build | [gistbuild.c:175-315](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L175-L315), [gistbuild.c:617-777](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L617-L777) |
| GIN first-build accumulator and validation pending-list cleanup both use the setting | [gininsert.c:246-314](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L246-L314), [ginvacuum.c:571-602](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L571-L602), [ginfast.c:780-840](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L780-L840) |
| BRIN's first-build memory effects are common worker planning and, if parallel, a summary sort; validation reports no TIDs | [planner.c:6993-7018](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6993-L7018), [brin.c:1091-1245](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1091-L1245), [brin.c:1283-1301](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1283-L1301) |
| SP-GiST and Bloom do not read the setting in their first builds but enumerate TIDs in validation | [spginsert.c:55-147](../../../../raw/postgres-17/src/backend/access/spgist/spginsert.c#L55-L147), [spgvacuum.c:149-165](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L149-L165), [blinsert.c:117-157](../../../../raw/postgres-17/contrib/bloom/blinsert.c#L117-L157), [blvacuum.c:26-103](../../../../raw/postgres-17/contrib/bloom/blvacuum.c#L26-L103) |
| Serial tuplesort reaches its memory plateau at the one-quicksort path | [tuplesort.c:31-80](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L31-L80), [tuplesort.c:1381-1465](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1381-L1465) |
| Progress, sort traces, and temp-file accounting expose different parts of a tuning run | [monitoring.sgml:5832-6105](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L5832-L6105), [tuplesort.c:890-940](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L890-L940), [fd.c:1524-1538](../../../../raw/postgres-17/src/backend/storage/file/fd.c#L1524-L1538) |
| The only direct CREATE INDEX memory regression forces non-concurrent hash sorting; direct CIC tests do not test a plateau | [create_index.sql:364-380](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L364-L380), [create_index.sql:481-582](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L481-L582) |
| CIC's automatic worker request uses the heap-size threshold, maintenance-worker cap, and 32 MB participant shares; launch is then limited by the worker pools | [planner.c:6876-7018](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6876-L7018), [allpaths.c:4202-4278](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4202-L4278), [bgworker.c:969-1039](../../../../raw/postgres-17/src/backend/postmaster/bgworker.c#L969-L1039) |
| CIC heap scans use sequential read streams: `io_combine_limit` applies, the effective-I/O setting is selected, and maintenance I/O advice is not | [heapam.c:1233-1259](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1233-L1259), [read_stream.c:407-536](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L407-L536) |
| GiST uniquely reads `effective_cache_size`; GIN writer sessions can shape the pending list inherited by validation | [gistbuild.c:670-757](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L670-L757), [ginfast.c:448-471](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L448-L471), [ginfast.c:807-840](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L807-L840) |
| Temp storage placement and per-process limit affect spill location or failure, not CIC correctness phases | [tuplesort.c:1956-1966](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1956-L1966), [fileset.c:42-72](../../../../raw/postgres-17/src/backend/storage/file/fileset.c#L42-L72), [fd.c:2211-2236](../../../../raw/postgres-17/src/backend/storage/file/fd.c#L2211-L2236) |
| CIC's WAL path can expose forced-image compression, commit synchronization, and checkpoint-crossing relation sync | [bulk_write.c:124-223](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L124-L223), [xloginsert.c:598-688](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L598-L688), [xact.c:1462-1521](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L1462-L1521) |
| `statement_timeout` spans the command; `transaction_timeout` restarts per internal transaction; `lock_timeout` applies per VXID acquisition | [postgres.c:2778-2807](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L2778-L2807), [xact.c:2168-2178](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L2168-L2178), [lock.c:4550-4662](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L4550-L4662) |
| v17 state-flag flips use transactional `CatalogTupleUpdate` | [index.c#index_set_state_flags](../../../../raw/postgres-17/src/backend/catalog/index.c#L3469-L3547) |
| `index_set_state_flags` transactional change came in PG14 | commit `83158f74d3a` (2020-09-14) |
| `WaitForLockers` reads current lock holders and waits on VXIDs without taking the relation lock itself | [lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-17/src/backend/storage/lmgr/lmgr.c#L889-L900), [lmgr.c:914-923](../../../../raw/postgres-17/src/backend/storage/lmgr/lmgr.c#L914-L923), [lmgr.c:935-952](../../../../raw/postgres-17/src/backend/storage/lmgr/lmgr.c#L935-L952) |
| `WaitForLockers(ShareLock)` waits out writers; `ShareLock` vs `RowExclusiveLock` | [lock.c:82-86](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L82-L86) |
| `ShareUpdateExclusiveLock` conflict set + self-conflict | [lock.c:77-81](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L77-L81) |
| Wait 3 ignores autovacuum, VACUUM, and safe CIC (`PROC_IN_SAFE_IC`) | [indexcmds.c:439-442](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L439-L442) |
| `PROC_IN_SAFE_IC` flag definition | [proc.h:57-62](../../../../raw/postgres-17/src/include/storage/proc.h#L57-L62) |
| `set_indexsafe_procflags` sets `MyProc->statusFlags` | [indexcmds.c:4473-4505](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L4473-L4505) |
| Doc: snapshot wait ignores other builds unless partial/expressional | [ref/create_index.sgml:627-643](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L627-L643) |
| PROC_IN_SAFE_IC added PG14 | commit `c98763bf` (2020-11-25), `f9900df5` (2021-01-15) |
| VACUUM-ignores-CIC reverted (present in v17) | commit `e28bb885` (2022-05-31) |
| PGXACT->PGPROC statusFlags move (PG14) | commit `5788e258` (2020-08-14) |
| v17 restricts search path during build | [index.c:1520-1524](../../../../raw/postgres-17/src/backend/catalog/index.c#L1520-L1524) |
| Tests | [create_index.sql:481-582](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L481-L582), [multiple-cic.spec](../../../../raw/postgres-17/src/test/isolation/specs/multiple-cic.spec#L1-L43), [prepared-transactions-cic.spec](../../../../raw/postgres-17/src/test/isolation/specs/prepared-transactions-cic.spec#L1-L37) |

## Open Questions

- The exact fastest safe value for a particular table, index definition,
  concurrent workload, storage device, and worker pool cannot be derived from
  source alone. It requires controlled measurements of both the first-build and
  validation phases on that workload.
- `read_stream.h` names `CREATE INDEX` as an example user of
  `READ_STREAM_MAINTENANCE`, but the v17 heap scan implementation passes only
  `READ_STREAM_SEQUENTIAL`. The executable path therefore selects
  `effective_io_concurrency`; the pinned source does not establish whether the
  stale-looking example is intentional or an omitted flag
  ([read_stream.h#READ_STREAM_MAINTENANCE](../../../../raw/postgres-17/src/include/storage/read_stream.h#L19-L35),
  [heapam.c#read-stream-flags](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1237-L1259),
  [read_stream.c#I/O-setting-selection](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L425-L439)).
- PostgreSQL 17 also refined REINDEX CONCURRENTLY's own `safe` determination for
  indexes with predicates/expressions (commit `cd6b2ae3`, "Fix waits of REINDEX
  CONCURRENTLY for indexes with predicates or expressions"); that is REINDEX
  CONCURRENTLY scope, not `CREATE INDEX CONCURRENTLY`, and was not traced here.
- The v12 behavioral claims in [What changed from PostgreSQL 12](#what-changed-from-postgresql-12)
  are anchored to the v17 checkout's commit history and the companion
  [v12 page](../../../v12/questions/indexing/create-index-concurrently.md); they are not
  re-cited against the PostgreSQL 12 source checkout here, per the
  one-version-per-page citation rule.

## Source References

- [utility.c#T_IndexStmt](../../../../raw/postgres-17/src/backend/tcop/utility.c#L1453-L1463)
- [indexcmds.c#DefineIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L540-L1793)
- [indexcmds.c#WaitForOlderSnapshots](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L397-L479)
- [indexcmds.c#set_indexsafe_procflags](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L4473-L4505)
- [index.c#UpdateIndexRelation](../../../../raw/postgres-17/src/backend/catalog/index.c#L630-L648)
- [index.c#index_create](../../../../raw/postgres-17/src/backend/catalog/index.c#L726-L752)
- [index.c#index_create-flags](../../../../raw/postgres-17/src/backend/catalog/index.c#L1050-L1057)
- [index.c#index_concurrently_build](../../../../raw/postgres-17/src/backend/catalog/index.c#L1499-L1557)
- [index.c#index_build](../../../../raw/postgres-17/src/backend/catalog/index.c#L2976-L3054)
- [index.c#validate_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3262-L3434)
- [index.c#index_set_state_flags](../../../../raw/postgres-17/src/backend/catalog/index.c#L3469-L3547)
- [heapam_handler.c#heapam_index_build_range_scan](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1171-L1744)
- [heapam_handler.c#heapam_index_validate_scan](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1747-L1986)
- [nbtsort.c#_bt_spools_heapscan](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L351-L509)
- [nbtsort.c#parallel-build](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1390-L1956)
- [hash.c#hashbuild](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L111-L194)
- [hashsort.c#_h_spoolinit](../../../../raw/postgres-17/src/backend/access/hash/hashsort.c#L56-L103)
- [gistbuild.c#gistbuild](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L175-L355)
- [gistbuild.c#gistInitBuffering](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L617-L777)
- [gistbuildbuffers.c#gistInitBuildBuffers](../../../../raw/postgres-17/src/backend/access/gist/gistbuildbuffers.c#L40-L105)
- [gininsert.c#ginbuild](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L246-L427)
- [ginbulk.c#BuildAccumulator](../../../../raw/postgres-17/src/backend/access/gin/ginbulk.c#L24-L121)
- [ginvacuum.c#ginbulkdelete](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L571-L651)
- [ginfast.c#ginInsertCleanup](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L780-L1017)
- [gin/README#index-structure](../../../../raw/postgres-17/src/backend/access/gin/README#L15-L53)
- [spginsert.c#spgbuild](../../../../raw/postgres-17/src/backend/access/spgist/spginsert.c#L55-L147)
- [spgvacuum.c#spgbulkdelete](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L149-L165)
- [brin.c#brinbuild](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1091-L1261)
- [brin.c#brinbulkdelete](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1283-L1301)
- [brin.c#parallel-build](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2337-L2929)
- [blinsert.c#blbuild](../../../../raw/postgres-17/contrib/bloom/blinsert.c#L117-L157)
- [blvacuum.c#blbulkdelete](../../../../raw/postgres-17/contrib/bloom/blvacuum.c#L26-L103)
- [planner.c#plan_create_index_workers](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6876-L7019)
- [allpaths.c#compute_parallel_worker](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4202-L4278)
- [bgworker.c#worker-pools](../../../../raw/postgres-17/src/backend/postmaster/bgworker.c#L146-L174)
- [bgworker.c#RegisterDynamicBackgroundWorker](../../../../raw/postgres-17/src/backend/postmaster/bgworker.c#L969-L1040)
- [parallel.c#GUC-state](../../../../raw/postgres-17/src/backend/access/transam/parallel.c#L376-L385)
- [parallel.c#restore-GUC-state](../../../../raw/postgres-17/src/backend/access/transam/parallel.c#L1449-L1458)
- [tuplesort.c#algorithm](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1-L88)
- [tuplesort.c#memory-and-performsort](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L680-L742)
- [tuplesort.c#puttuple-and-performsort](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L1225-L1486)
- [tuplesort.c#leader_takeover_tapes](../../../../raw/postgres-17/src/backend/utils/sort/tuplesort.c#L3078-L3160)
- [heapam.c#scan-strategy-and-read-stream](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L417-L496)
- [heapam.c#heap_beginscan](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1151-L1262)
- [read_stream.c#read_stream_begin_relation](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L379-L570)
- [read_stream.h#flags](../../../../raw/postgres-17/src/include/storage/read_stream.h#L19-L42)
- [spccache.c#I/O-concurrency](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L215-L236)
- [fileset.c#temp-tablespaces](../../../../raw/postgres-17/src/backend/storage/file/fileset.c#L42-L72)
- [bulk_write.c#smgr_bulk_finish](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L124-L223)
- [bulk_write.c#smgr_bulk_flush](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L239-L313)
- [xloginsert.c#forced-images-and-compression](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L598-L735)
- [xact.c#commit-flush](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L1462-L1546)
- [xact.c#transaction-timeout](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L2168-L2178)
- [xlog.c#group-commit-delay](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L2869-L2888)
- [syncrep.c#SyncRepWaitForLSN](../../../../raw/postgres-17/src/backend/replication/syncrep.c#L133-L204)
- [lock.c#VirtualXactLock](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L4550-L4662)
- [proc.c#lock-timeout](../../../../raw/postgres-17/src/backend/storage/lmgr/proc.c#L1273-L1325)
- [postgres.c#statement-and-transaction-timeouts](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L3374-L3463)
- [vacuum.c#vacuum_delay_point](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2383-L2419)
- [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2460-L2474)
- [guc_tables.c#timeouts](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2653)
- [guc_tables.c#worker-pools](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3163-L3172)
- [guc_tables.c#parallel-workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3438)
- [guc_tables.c#I/O-settings](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3109-L3160)
- [guc_tables.c#planner-and-GIN-settings](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3585)
- [guc_tables.c#tablespaces](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4137-L4156)
- [guc_tables.c#WAL-size-checkpoint-and-commit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2842-L3001)
- [guc_tables.c#WAL-commit-and-compression](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4925-L4983)
- [guc_tables.c#observability-GUCs](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1400-L1436)
- [guc_tables.c#trace_sort](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1659-L1669)
- [guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417)
- [guc_tables.c#log_temp_files](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3554-L3563)
- [miscadmin.h#maintenance_work_mem](../../../../raw/postgres-17/src/include/miscadmin.h#L266-L270)
- [bufmgr.h#I/O-GUCs](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L155-L174)
- [cost.h#effective-cache-default](../../../../raw/postgres-17/src/include/optimizer/cost.h#L31-L35)
- [gin_private.h#GIN-options](../../../../raw/postgres-17/src/include/access/gin_private.h#L23-L45)
- [rel.h#RelationNeedsWAL](../../../../raw/postgres-17/src/include/utils/rel.h#L617-L631)
- [amapi.h#ambuild-and-AM-flags](../../../../raw/postgres-17/src/include/access/amapi.h#L98-L108)
- [amapi.h#IndexAmRoutine](../../../../raw/postgres-17/src/include/access/amapi.h#L230-L296)
- [execnodes.h#IndexInfo](../../../../raw/postgres-17/src/include/nodes/execnodes.h#L155-L211)
- [vacuumparallel.c#amusemaintenanceworkmem](../../../../raw/postgres-17/src/backend/commands/vacuumparallel.c#L331-L375)
- [backend_progress.c#progress-reporting](../../../../raw/postgres-17/src/backend/utils/activity/backend_progress.c#L21-L60)
- [fd.c#ReportTemporaryFileUsage](../../../../raw/postgres-17/src/backend/storage/file/fd.c#L1524-L1538)
- [pgstat_database.c#pgstat_report_tempfile](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_database.c#L170-L185)
- [proc.h#PROC_IN_SAFE_IC](../../../../raw/postgres-17/src/include/storage/proc.h#L54-L78)
- [lmgr.c#WaitForLockersMultiple](../../../../raw/postgres-17/src/backend/storage/lmgr/lmgr.c#L889-L988)
- [lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L64-L103)
- [lockdefs.h#lockmodes](../../../../raw/postgres-17/src/include/storage/lockdefs.h#L36-L46)
- [utils/misc/Makefile#guc_tables](../../../../raw/postgres-17/src/backend/utils/misc/Makefile#L17-L27)
- [utils/misc/meson.build#guc_tables](../../../../raw/postgres-17/src/backend/utils/misc/meson.build#L1-L12)
- [pg_config_manual.h#TRACE_SORT](../../../../raw/postgres-17/src/include/pg_config_manual.h#L376-L380)
- [config.sgml#maintenance_work_mem](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L1922-L1970)
- [config.sgml#parallel-maintenance](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L2864-L2898)
- [config.sgml#checkpoint-settings](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L3605-L3719)
- [config.sgml#durability-settings](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L3022-L3329)
- [config.sgml#I/O-timing](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L8451-L8499)
- [ref/set.sgml#SET-scope](../../../../raw/postgres-17/doc/src/sgml/ref/set.sgml#L35-L60)
- [ref/set.sgml#LOCAL](../../../../raw/postgres-17/doc/src/sgml/ref/set.sgml#L100-L117)
- [ref/create_index.sgml#CONCURRENTLY](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L612-L702)
- [ref/create_index.sgml#memory-and-parallelism](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L790-L862)
- [monitoring.sgml#create-index-progress](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L5832-L6105)
- [monitoring.sgml#database-temp-counters](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L3360-L3381)
- [gist.sgml#build-methods](../../../../raw/postgres-17/doc/src/sgml/gist.sgml#L1184-L1234)
- [gin.sgml#maintenance_work_mem](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L584-L592)
- [create_index.sql#hash-tuplesort](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L364-L380)
- [create_index.sql#concurrent-indexes](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L481-L582)
- [pageinspect/brin.sql#parallel-build](../../../../raw/postgres-17/contrib/pageinspect/sql/brin.sql#L80-L144)
- [multiple-cic.spec](../../../../raw/postgres-17/src/test/isolation/specs/multiple-cic.spec#L1-L43)
- [prepared-transactions-cic.spec](../../../../raw/postgres-17/src/test/isolation/specs/prepared-transactions-cic.spec#L1-L37)
- [amcheck/002_cic.pl](../../../../raw/postgres-17/contrib/amcheck/t/002_cic.pl#L1-L88)

## Navigation

- [v17 index](../../index.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
- [v12: CREATE INDEX CONCURRENTLY](../../../v12/questions/indexing/create-index-concurrently.md)
