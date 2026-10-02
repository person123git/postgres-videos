---
type: question
version: 18
pinned_commit: baa7b142aace6821ce085906f314a75bcc4d95c8
verified: false
verified_by_agent: not yet
---

# Extension Hooks for VACUUM and Autovacuum in PostgreSQL 18 (unverified)

## Question

> Follow AGENTS.md.
> In PostgreSQL 18, provide comprehensive documentation of all hooks available
> to an extension in the vacuum and autovacuum paths.

## Answer Up Front

PostgreSQL 18 has no dedicated `vacuum_hook` or `autovacuum_hook`. Vacuum-aware
extensions reach into vacuum and autovacuum through four kinds of extension
points: (1) general in-process hook variables (function pointers in core C
code) that happen to fire on vacuum's path, (2) shared-memory init hooks that
let an extension stand up its own state alongside vacuum, (3) per-relation
access-method callbacks invoked by `vacuum()` and `do_analyze_rel()`, and (4)
adjacent extension surfaces such as background-worker registration and custom
cumulative statistics.

Two paths matter and they differ. A user-issued `VACUUM`/`ANALYZE` goes through
the parser, `ProcessUtility`, then `ExecVacuum -> vacuum()`; autovacuum workers
call `vacuum()` directly from `autovacuum_do_vac_analyze`, bypassing parser
and `ProcessUtility`
([utility.c#ProcessUtility](../../../../raw/postgres-18/src/backend/tcop/utility.c#L499),
[vacuum.c#ExecVacuum](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L162),
[autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L3173)).
Hooks that sit on the parser/utility path therefore see only manual VACUUM and
ANALYZE; hooks that sit deeper in `vacuum()`, in the table or index AM, in
`elog()`, or in pgstat reporting fire for autovacuum as well.

The summary table below maps each hook to the paths that fire it. Detailed
semantics and call sites follow.

| Extension point | Manual VACUUM/ANALYZE | Autovacuum worker | Where it fires |
|---|---|---|---|
| `ProcessUtility_hook` | yes | no | utility dispatch |
| `post_parse_analyze_hook` | yes | no | after parse-analyze |
| `emit_log_hook` | yes | yes | every server log line |
| `shmem_request_hook` / `shmem_startup_hook` | postmaster startup only | postmaster startup only | shared-memory sizing and init |
| `TableAmRoutine.relation_vacuum` | yes (non-FULL) | yes (non-FULL) | per-relation vacuum |
| `TableAmRoutine.scan_analyze_next_block` / `scan_analyze_next_tuple` | yes (ANALYZE) | yes (ANALYZE) | per-block / per-tuple ANALYZE |
| `IndexAmRoutine.ambulkdelete` / `amvacuumcleanup` | yes | yes | per-index VACUUM |
| `FdwRoutine.AnalyzeForeignTable` | yes (foreign table ANALYZE) | yes (foreign table ANALYZE) | start of ANALYZE on a foreign table |
| `pg_type.typanalyze` (per-column) | yes | yes | column-stats setup in ANALYZE |
| Custom background worker | n/a | n/a | extension-defined process |
| Custom cumulative statistics | yes | yes | extension-defined counters |

PostgreSQL 18 does not expose any other in-process hook on the vacuum or
autovacuum code paths. There is no autovacuum scheduling hook, no
relation-selection hook, no per-vacuum-pass callback in core C
([vacuum.c](../../../../raw/postgres-18/src/backend/commands/vacuum.c),
[autovacuum.c](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c),
[vacuumlazy.c](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c)).

## Two Code Paths

### Manual VACUUM/ANALYZE

A user-issued `VACUUM` or `ANALYZE` statement reaches the backend as a raw
parse tree, runs through parse-analyze, and is dispatched as a utility
statement. `ProcessUtility` calls `ProcessUtility_hook` if set, otherwise
`standard_ProcessUtility`, which routes `T_VacuumStmt` to `ExecVacuum`
([utility.c#ProcessUtility](../../../../raw/postgres-18/src/backend/tcop/utility.c#L499),
[utility.c](../../../../raw/postgres-18/src/backend/tcop/utility.c)).
`ExecVacuum` parses options, builds a `VacuumParams` value, and calls
`vacuum()`
([vacuum.c#ExecVacuum](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L162)).

### Autovacuum worker

The autovacuum launcher and worker are PostgreSQL processes, not SQL
statements. The worker connects to the target database, scans `pg_class` for
candidates, and then calls `autovacuum_do_vac_analyze`, which sets up
`VacuumParams` and calls `vacuum()` directly with `VacuumRelation` entries
identified by OID
([autovacuum.c#do_autovacuum](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L1885),
[autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L3173)).
No `RawStmt` is created and no `ProcessUtility` is invoked, so hooks that fire
during parser dispatch never fire for autovacuum.

The autovacuum launcher initializes itself through `InitPostgres(NULL,
InvalidOid, NULL, InvalidOid, 0, NULL)`, with the flags argument set to `0`;
the worker uses `INIT_PG_OVERRIDE_ALLOW_CONNS`. Neither call passes
`INIT_PG_LOAD_SESSION_LIBS`, so autovacuum processes do not load
`session_preload_libraries`; only `shared_preload_libraries`, which is
processed in the postmaster before fork, contributes hook installations to
autovacuum
([autovacuum.c#AutoVacLauncherMain](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L368),
[autovacuum.c#AutoVacWorkerMain](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L1376),
[postinit.c](../../../../raw/postgres-18/src/backend/utils/init/postinit.c),
[miscinit.c#process_shared_preload_libraries](../../../../raw/postgres-18/src/backend/utils/init/miscinit.c#L1903)).

## In-Process Hook Variables

### `ProcessUtility_hook`

Type:

```c
typedef void (*ProcessUtility_hook_type) (PlannedStmt *pstmt,
                                          const char *queryString,
                                          bool readOnlyTree,
                                          ProcessUtilityContext context,
                                          ParamListInfo params,
                                          QueryEnvironment *queryEnv,
                                          DestReceiver *dest,
                                          QueryCompletion *qc);
```

([utility.h](../../../../raw/postgres-18/src/include/tcop/utility.h)).

`ProcessUtility` calls the hook in place of `standard_ProcessUtility` when set,
and the comment block explicitly tells plugins to chain forward by calling
`standard_ProcessUtility` to keep core dispatch working
([utility.c#ProcessUtility](../../../../raw/postgres-18/src/backend/tcop/utility.c#L499)).
For VACUUM/ANALYZE, `standard_ProcessUtility` dispatches `T_VacuumStmt` to
`ExecVacuum`
([utility.c](../../../../raw/postgres-18/src/backend/tcop/utility.c)).

Use this hook to observe or wrap user-issued VACUUM and ANALYZE statements.
This hook does not fire for autovacuum: autovacuum's
`autovacuum_do_vac_analyze` calls `vacuum()` directly, never going through
`ProcessUtility`
([autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L3173)).

### `post_parse_analyze_hook`

Type:

```c
typedef void (*post_parse_analyze_hook_type) (ParseState *pstate,
                                              Query *query,
                                              JumbleState *jstate);
```

([analyze.h](../../../../raw/postgres-18/src/include/parser/analyze.h)).

`parse_analyze_fixedparams`, `parse_analyze_varparams`, and
`parse_analyze_withcb` all call the hook after producing the `Query` and after
optional jumbling
([analyze.c#parse_analyze_fixedparams](../../../../raw/postgres-18/src/backend/parser/analyze.c#L105),
[analyze.c#parse_analyze_varparams](../../../../raw/postgres-18/src/backend/parser/analyze.c#L145),
[analyze.c#parse_analyze_withcb](../../../../raw/postgres-18/src/backend/parser/analyze.c#L186)).
VACUUM and ANALYZE are utility statements wrapped in a `CMD_UTILITY` Query,
so this hook sees the statement when a user issues it
([analyze.c](../../../../raw/postgres-18/src/backend/parser/analyze.c)).
Autovacuum has no `RawStmt` to analyze and never reaches these functions.

### `emit_log_hook`

Type:

```c
typedef void (*emit_log_hook_type) (ErrorData *edata);
```

([elog.h](../../../../raw/postgres-18/src/include/utils/elog.h)).

`EmitErrorReport` calls the hook before the message is sent to the server log,
once `errstart` has decided the message is interesting. The header comment
warns that the hook may turn off `edata->output_to_server` but is not
supposed to mutate other fields; `EmitErrorReport` rechecks `output_to_server`
afterwards
([elog.c#EmitErrorReport](../../../../raw/postgres-18/src/backend/utils/error/elog.c#L1692)).
Vacuum and autovacuum emit log lines through `ereport()` like every other
subsystem, so this hook is the one general-purpose extension point that fires
on both paths. For example, `vacuum_error_callback` and per-phase progress
logging all flow through `EmitErrorReport`
([vacuumlazy.c#vacuum_error_callback](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L3782)).

### `shmem_request_hook` and `shmem_startup_hook`

Types:

```c
typedef void (*shmem_request_hook_type) (void);
typedef void (*shmem_startup_hook_type) (void);
```

([miscadmin.h](../../../../raw/postgres-18/src/include/miscadmin.h),
[ipc.h](../../../../raw/postgres-18/src/include/storage/ipc.h)).

Extensions that need their own shared memory to track vacuum-related state
install both hooks from `_PG_init` while
`process_shared_preload_libraries_in_progress` is true.
`process_shmem_requests` is called twice in startup (from the postmaster and
from each non-postmaster backend in EXEC_BACKEND/single-user mode) with
`process_shmem_requests_in_progress = true`, so an extension may only call
`RequestAddinShmemSpace` or `RequestNamedLWLockTranche` from inside
`shmem_request_hook`; `CreateOrAttachShmemStructs` later invokes
`shmem_startup_hook` after core shared structures are created
([miscinit.c#process_shmem_requests](../../../../raw/postgres-18/src/backend/utils/init/miscinit.c#L1931),
[ipci.c](../../../../raw/postgres-18/src/backend/storage/ipc/ipci.c),
[lwlock.c](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c),
[postmaster.c](../../../../raw/postgres-18/src/backend/postmaster/postmaster.c)).

These hooks are not vacuum-specific. They are the only supported way for a
loadable module to allocate persistent backend-shared state, which is
typically how an extension keeps cross-vacuum counters or queues. See the
worked example pattern in
[xfunc.sgml](../../../../raw/postgres-18/doc/src/sgml/xfunc.sgml).

### Hooks that do NOT fire on vacuum's path

For completeness: `object_access_hook`, `ExecutorStart_hook`,
`ExecutorRun_hook`, `ExecutorFinish_hook`, `ExecutorEnd_hook`,
`ExecutorCheckPerms_hook`, the planner and path hooks, and the `explain_*`
hooks do not fire from the vacuum/autovacuum/analyze paths.
A grep across `raw/postgres-18/src/backend/commands/vacuum.c`,
`raw/postgres-18/src/backend/commands/vacuumparallel.c`,
`raw/postgres-18/src/backend/commands/analyze.c`,
`raw/postgres-18/src/backend/access/heap/vacuumlazy.c`, and
`raw/postgres-18/src/backend/postmaster/autovacuum.c` finds no
`Invoke*Hook` macro calls and no `ExecutorStart`/`CreateQueryDesc`
invocations, and the analyze path does not run SPI
([analyze.c](../../../../raw/postgres-18/src/backend/commands/analyze.c),
[vacuum.c](../../../../raw/postgres-18/src/backend/commands/vacuum.c)).

The `get_relation_stats_hook`, `get_index_stats_hook`, and
`get_attavgwidth_hook` are read hooks consulted by the planner when it reads
`pg_statistic` rows that ANALYZE wrote; they do not fire during ANALYZE itself
([selfuncs.c](../../../../raw/postgres-18/src/backend/utils/adt/selfuncs.c),
[lsyscache.c](../../../../raw/postgres-18/src/backend/utils/cache/lsyscache.c)).

## Access-Method Callbacks

### Table AM

Vacuum and analyze dispatch through the table access-method routine in three
places. The relevant callbacks live in `TableAmRoutine`
([tableam.h](../../../../raw/postgres-18/src/include/access/tableam.h)):

- `relation_vacuum(Relation rel, struct VacuumParams *params,
  BufferAccessStrategy bstrategy)`. Called by `table_relation_vacuum` from
  `vacuum_rel` on non-FULL VACUUM. The header comment explicitly notes that
  VACUUM may be triggered by a user or by autovacuum, that ShareUpdateExclusive
  is held on entry, and that VACUUM FULL and ANALYZE do not go through this
  callback
  ([tableam.h](../../../../raw/postgres-18/src/include/access/tableam.h),
  [vacuum.c](../../../../raw/postgres-18/src/backend/commands/vacuum.c)).
- `scan_analyze_next_block(TableScanDesc scan, ReadStream *stream)`. Called
  per block by `acquire_sample_rows` through `table_scan_analyze_next_block`,
  during `do_analyze_rel`
  ([analyze.c](../../../../raw/postgres-18/src/backend/commands/analyze.c),
  [tableam.h](../../../../raw/postgres-18/src/include/access/tableam.h)).
- `scan_analyze_next_tuple(TableScanDesc scan, TransactionId OldestXmin,
  double *liverows, double *deadrows, TupleTableSlot *slot)`. Called per tuple
  by `acquire_sample_rows` through `table_scan_analyze_next_tuple`
  ([analyze.c](../../../../raw/postgres-18/src/backend/commands/analyze.c),
  [tableam.h](../../../../raw/postgres-18/src/include/access/tableam.h)).

A custom table AM that wants to react to vacuum or change vacuum semantics for
its relations implements these three callbacks.

### Index AM

Vacuum calls into the index AM through two callbacks in `IndexAmRoutine`
([amapi.h](../../../../raw/postgres-18/src/include/access/amapi.h)):

- `ambulkdelete(IndexVacuumInfo *info, IndexBulkDeleteResult *istat,
  IndexBulkDeleteCallback callback, void *callback_state)`. Bulk-removes index
  tuples whose heap TIDs the callback declares dead. `vac_bulkdel_one_index`
  wraps `index_bulk_delete`, which dispatches to `ambulkdelete` and emits the
  per-index `scanned index ... to remove` log line
  ([vacuum.c#vac_bulkdel_one_index](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L2651),
  [indexam.c#index_bulk_delete](../../../../raw/postgres-18/src/backend/access/index/indexam.c#L795)).
- `amvacuumcleanup(IndexVacuumInfo *info, IndexBulkDeleteResult *istat)`.
  Performs post-VACUUM cleanup and returns optionally updated index
  statistics. `vac_cleanup_one_index` wraps `index_vacuum_cleanup`, which
  dispatches to `amvacuumcleanup`
  ([vacuum.c#vac_cleanup_one_index](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L2672),
  [indexam.c#index_vacuum_cleanup](../../../../raw/postgres-18/src/backend/access/index/indexam.c#L816)).

Parallel VACUUM is opt-in per index AM via the bitmask
`amparallelvacuumoptions` on `IndexAmRoutine`. The flags
`VACUUM_OPTION_PARALLEL_BULKDEL`, `VACUUM_OPTION_PARALLEL_COND_CLEANUP`, and
`VACUUM_OPTION_PARALLEL_CLEANUP` describe which phases an AM may run in
parallel workers
([amapi.h](../../../../raw/postgres-18/src/include/access/amapi.h),
[vacuum.h](../../../../raw/postgres-18/src/include/commands/vacuum.h),
[vacuumparallel.c](../../../../raw/postgres-18/src/backend/commands/vacuumparallel.c)).
Parallel vacuum runs the bulk-delete and cleanup callbacks in parallel
workers and copies each index's `IndexBulkDeleteResult` back through a DSM
segment at the end
([vacuumparallel.c](../../../../raw/postgres-18/src/backend/commands/vacuumparallel.c)).

A custom index AM implements the two vacuum callbacks (and declares its
parallel-vacuum capability) to participate in VACUUM.

### Foreign Data Wrapper

Foreign tables get one ANALYZE-specific FDW callback in `FdwRoutine`:

```c
typedef bool (*AnalyzeForeignTable_function) (Relation relation,
                                              AcquireSampleRowsFunc *func,
                                              BlockNumber *totalpages);
```

([fdwapi.h](../../../../raw/postgres-18/src/include/foreign/fdwapi.h)).

`analyze_rel` recognizes `RELKIND_FOREIGN_TABLE`, calls
`GetFdwRoutineForRelation`, and invokes `AnalyzeForeignTable`; if the FDW does
not implement analysis it returns false and `analyze_rel` emits a
"skipping ... cannot analyze this foreign table" warning and returns
([analyze.c#analyze_rel](../../../../raw/postgres-18/src/backend/commands/analyze.c#L109),
[fdwhandler.sgml#fdw-callbacks-analyze](../../../../raw/postgres-18/doc/src/sgml/fdwhandler.sgml#L1367)).
There is no FDW callback for VACUUM proper; the table AM `relation_vacuum`
callback is not called for foreign tables.

### Per-Type analyze function (`pg_type.typanalyze`)

A type can supply a `typanalyze` function in `pg_type`; ANALYZE calls it from
`examine_attribute` via `OidFunctionCall1` with a populated `VacAttrStats *`,
falling back to `std_typanalyze` when none is set. The function must fill in
`compute_stats`, `minrows`, and optionally `extra_data` to take part in
per-column statistics
([analyze.c#examine_attribute](../../../../raw/postgres-18/src/backend/commands/analyze.c#L1036),
[analyze.c#std_typanalyze](../../../../raw/postgres-18/src/backend/commands/analyze.c#L1891),
[vacuum.h](../../../../raw/postgres-18/src/include/commands/vacuum.h)).
An extension that defines a new SQL data type can plug into ANALYZE by
shipping a `typanalyze` function in its CREATE TYPE definition.

## Adjacent Extension Surfaces

### Read-stream strategy clearing (new extension-visible API in 18.6)

The 18.4/18.6 range adds one exported function to the read-stream API that
extensions and out-of-core table AMs can call:
`read_stream_clear_strategy(ReadStream *stream)`. It sets
`op.strategy = NULL` on every one of the stream's `ReadBuffersOperation`s,
including in-flight ones, so subsequent reads use the whole shared buffer pool
instead of a ring; the caller still owns freeing the strategy's memory, and the
function's comment notes that an IO whose strategy was cleared mid-flight may
have a small part of its read time attributed to `IOCONTEXT_NORMAL`
([read_stream.c#read_stream_clear_strategy](../../../../raw/postgres-18/src/backend/storage/aio/read_stream.c#L1046-L1066),
[read_stream.h:102](../../../../raw/postgres-18/src/include/storage/read_stream.h#L102)).

The only in-tree caller is VACUUM's heap scan. When `VacuumFailsafeActive` is
set — the wraparound failsafe — `lazy_scan_heap()` calls it once and records
that it did, so the rest of the vacuum may use all of shared buffers
([vacuumlazy.c#failsafe-clear-strategy](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L1311-L1323)).
Commits `585181e0774` and `7c25cdb1ebf` restored that behavior, which a v18
refactor had accidentally broken, and made the clearing happen only once
([release-18.sgml#failsafe-buffer-pool](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L2036-L2062)).
This is a buffer-access-strategy change only: the failsafe's other effects,
including skipping further index vacuuming and cleanup, are unchanged, and no
new hook or callback is introduced.

Separately, `4cc49cb7039` fixed the autovacuum launcher's database ordering:
`db_comparator()` was sorting databases from lowest to highest score, when the
launcher should process the highest-scoring database first. Extensions that
infer launcher behavior from observed per-database ordering should note the
change
([autovacuum.c#db_comparator](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L1070-L1076),
[release-18.sgml#autovacuum-db-order](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L2016-L2034)).

### Background workers

`shared_preload_libraries`'s `_PG_init` may call `RegisterBackgroundWorker`
to register a static background worker; the function rejects calls outside
`process_shared_preload_libraries_in_progress` when in a postmaster
environment
([bgworker.c#RegisterBackgroundWorker](../../../../raw/postgres-18/src/backend/postmaster/bgworker.c#L940),
[bgworker.h](../../../../raw/postgres-18/src/include/postmaster/bgworker.h)).
Extensions that want to add behavior alongside autovacuum (for example, a
maintenance scheduler or a custom retention policy) typically run as their
own background worker rather than trying to hook into the launcher.

### Custom cumulative statistics

An extension can register a `PgStat_KindInfo` to define new shared cumulative
counters that report on vacuum-related events. The flow, validation, and
shared-memory layout are documented separately and are not duplicated here;
see [How Custom Cumulative Statistics Work in PostgreSQL 18 (unverified)](../observability/custom-cumulative-statistics.md)
([pgstat.c#pgstat_register_kind](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1465),
[pgstat_internal.h#PgStat_KindInfo](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L202)).

The built-in vacuum/autovacuum reporters that an extension can read from
shared cumulative stats are `pgstat_report_vacuum`, `pgstat_report_analyze`,
and `pgstat_report_autovac`. They write into per-table and per-database
cumulative entries used by `pg_stat_all_tables`, `last_vacuum`,
`last_autovacuum`, `last_analyze`, and `last_autoanalyze`
([vacuumlazy.c](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c),
[autovacuum.c](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c)).

### Progress reporting

Vacuum and analyze publish progress through the cumulative-stats progress
API; the field numbers and phase constants are exposed in
`commands/progress.h` and surfaced as `pg_stat_progress_vacuum` and
`pg_stat_progress_analyze`. Extensions that want to display vacuum progress
read these views instead of installing a hook
([progress.h](../../../../raw/postgres-18/src/include/commands/progress.h),
[vacuum.c](../../../../raw/postgres-18/src/backend/commands/vacuum.c),
[vacuumlazy.c](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c)).

## Registration Notes

- A hook is installed by assigning to its global variable from `_PG_init` of a
  loadable library. `_PG_init` runs during `process_shared_preload_libraries`,
  `process_session_preload_libraries`, or on the first call into the library;
  shared-memory and background-worker registrations are only valid while
  `process_shared_preload_libraries_in_progress` is true, so vacuum-tracking
  extensions belong in `shared_preload_libraries`
  ([miscinit.c#process_shared_preload_libraries](../../../../raw/postgres-18/src/backend/utils/init/miscinit.c#L1903),
  [bgworker.c#RegisterBackgroundWorker](../../../../raw/postgres-18/src/backend/postmaster/bgworker.c#L940),
  [ipci.c](../../../../raw/postgres-18/src/backend/storage/ipc/ipci.c)).
- `shared_preload_libraries` has GUC context `PGC_POSTMASTER`, so changing it
  requires a server restart
  ([guc_tables.c](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c),
  [config.sgml#guc-shared-preload-libraries](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L11004)).
- Plugins that install in-process hooks must save and call the previous hook
  value so multiple extensions can chain; the `ProcessUtility_hook` block
  comment in `utility.c` documents the chaining pattern for that hook
  ([utility.c#ProcessUtility](../../../../raw/postgres-18/src/backend/tcop/utility.c#L499)).

## Context Reviewed

- VACUUM/ANALYZE command path:
  [utility.c#ProcessUtility](../../../../raw/postgres-18/src/backend/tcop/utility.c#L499),
  [vacuum.c#ExecVacuum](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L162),
  [vacuum.c](../../../../raw/postgres-18/src/backend/commands/vacuum.c),
  [analyze.c](../../../../raw/postgres-18/src/backend/commands/analyze.c),
  [vacuumlazy.c](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c),
  [vacuumparallel.c](../../../../raw/postgres-18/src/backend/commands/vacuumparallel.c).
- Autovacuum process path:
  [autovacuum.c#AutoVacLauncherMain](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L368),
  [autovacuum.c#AutoVacWorkerMain](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L1376),
  [autovacuum.c#do_autovacuum](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L1885),
  [autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L3173).
- In-process hook variables:
  [utility.c](../../../../raw/postgres-18/src/backend/tcop/utility.c),
  [analyze.c](../../../../raw/postgres-18/src/backend/parser/analyze.c),
  [elog.c](../../../../raw/postgres-18/src/backend/utils/error/elog.c),
  [miscinit.c](../../../../raw/postgres-18/src/backend/utils/init/miscinit.c),
  [ipci.c](../../../../raw/postgres-18/src/backend/storage/ipc/ipci.c).
- AM and FDW callbacks:
  [tableam.h](../../../../raw/postgres-18/src/include/access/tableam.h),
  [amapi.h](../../../../raw/postgres-18/src/include/access/amapi.h),
  [fdwapi.h](../../../../raw/postgres-18/src/include/foreign/fdwapi.h),
  [vacuum.h](../../../../raw/postgres-18/src/include/commands/vacuum.h),
  [indexam.c](../../../../raw/postgres-18/src/backend/access/index/indexam.c).
- Adjacent extension surfaces:
  [bgworker.h](../../../../raw/postgres-18/src/include/postmaster/bgworker.h),
  [bgworker.c#RegisterBackgroundWorker](../../../../raw/postgres-18/src/backend/postmaster/bgworker.c#L940),
  [progress.h](../../../../raw/postgres-18/src/include/commands/progress.h),
  [read_stream.h](../../../../raw/postgres-18/src/include/storage/read_stream.h),
  [read_stream.c](../../../../raw/postgres-18/src/backend/storage/aio/read_stream.c),
  [How Custom Cumulative Statistics Work in PostgreSQL 18 (unverified)](../observability/custom-cumulative-statistics.md).
- Target evidence checkout: `raw/postgres-18/` at pinned commit
  `baa7b142aace6821ce085906f314a75bcc4d95c8` (`REL_18_6-10-gbaa7b142aac`),
  re-checked for the 18.4/18.6 range against the previous pin
  `6cb307251c5c6261286c1566496920976640108e`. The hook and AM-callback inventory
  above is unchanged by that range; the only extension-visible addition is
  `read_stream_clear_strategy()`
  ([read_stream.h:102](../../../../raw/postgres-18/src/include/storage/read_stream.h#L102)).
- Documentation cross-checks:
  [xfunc.sgml](../../../../raw/postgres-18/doc/src/sgml/xfunc.sgml),
  [fdwhandler.sgml#fdw-callbacks-analyze](../../../../raw/postgres-18/doc/src/sgml/fdwhandler.sgml#L1367),
  [config.sgml#guc-shared-preload-libraries](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L11004).

## Evidence Map

| Claim | Source |
|---|---|
| `ProcessUtility_hook` is called in place of `standard_ProcessUtility` | [utility.c#ProcessUtility](../../../../raw/postgres-18/src/backend/tcop/utility.c#L499) |
| `standard_ProcessUtility` routes `T_VacuumStmt` to `ExecVacuum` | [utility.c](../../../../raw/postgres-18/src/backend/tcop/utility.c) |
| Autovacuum worker calls `vacuum()` directly, bypassing `ProcessUtility` | [autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L3173) |
| Autovacuum launcher/worker `InitPostgres` does not load session preload libraries | [autovacuum.c#AutoVacLauncherMain](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L368), [autovacuum.c#AutoVacWorkerMain](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L1376), [postinit.c](../../../../raw/postgres-18/src/backend/utils/init/postinit.c) |
| `post_parse_analyze_hook` fires from the three `parse_analyze_*` entry points | [analyze.c#parse_analyze_fixedparams](../../../../raw/postgres-18/src/backend/parser/analyze.c#L105), [analyze.c#parse_analyze_varparams](../../../../raw/postgres-18/src/backend/parser/analyze.c#L145), [analyze.c#parse_analyze_withcb](../../../../raw/postgres-18/src/backend/parser/analyze.c#L186) |
| `emit_log_hook` fires from `EmitErrorReport` for every server log line | [elog.c#EmitErrorReport](../../../../raw/postgres-18/src/backend/utils/error/elog.c#L1692) |
| `shmem_request_hook` runs inside `process_shmem_requests` | [miscinit.c#process_shmem_requests](../../../../raw/postgres-18/src/backend/utils/init/miscinit.c#L1931) |
| `shmem_startup_hook` runs from `CreateOrAttachShmemStructs` | [ipci.c](../../../../raw/postgres-18/src/backend/storage/ipc/ipci.c) |
| `relation_vacuum`, `scan_analyze_next_block`, `scan_analyze_next_tuple` are table AM callbacks invoked from VACUUM/ANALYZE | [tableam.h](../../../../raw/postgres-18/src/include/access/tableam.h), [vacuum.c](../../../../raw/postgres-18/src/backend/commands/vacuum.c), [analyze.c](../../../../raw/postgres-18/src/backend/commands/analyze.c) |
| `ambulkdelete` and `amvacuumcleanup` are index AM callbacks invoked from `vac_bulkdel_one_index`/`vac_cleanup_one_index` | [vacuum.c#vac_bulkdel_one_index](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L2651), [vacuum.c#vac_cleanup_one_index](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L2672), [indexam.c#index_bulk_delete](../../../../raw/postgres-18/src/backend/access/index/indexam.c#L795), [indexam.c#index_vacuum_cleanup](../../../../raw/postgres-18/src/backend/access/index/indexam.c#L816) |
| `amparallelvacuumoptions` controls per-AM parallel VACUUM participation | [amapi.h](../../../../raw/postgres-18/src/include/access/amapi.h), [vacuum.h](../../../../raw/postgres-18/src/include/commands/vacuum.h) |
| `AnalyzeForeignTable` is the FDW ANALYZE entry; no FDW hook for VACUUM | [fdwapi.h](../../../../raw/postgres-18/src/include/foreign/fdwapi.h), [analyze.c#analyze_rel](../../../../raw/postgres-18/src/backend/commands/analyze.c#L109) |
| `pg_type.typanalyze` is invoked per attribute during ANALYZE | [analyze.c#examine_attribute](../../../../raw/postgres-18/src/backend/commands/analyze.c#L1036) |
| `RegisterBackgroundWorker` is only valid in `shared_preload_libraries` | [bgworker.c#RegisterBackgroundWorker](../../../../raw/postgres-18/src/backend/postmaster/bgworker.c#L940) |
| Custom cumulative statistics already covered in another page | [How Custom Cumulative Statistics Work in PostgreSQL 18 (unverified)](../observability/custom-cumulative-statistics.md) |

## Source References

- [utility.h](../../../../raw/postgres-18/src/include/tcop/utility.h) - `ProcessUtility_hook_type`.
- [utility.c#ProcessUtility](../../../../raw/postgres-18/src/backend/tcop/utility.c#L499) - `ProcessUtility_hook` dispatch and `T_VacuumStmt -> ExecVacuum` route.
- [analyze.h](../../../../raw/postgres-18/src/include/parser/analyze.h) - `post_parse_analyze_hook_type`.
- [analyze.c](../../../../raw/postgres-18/src/backend/parser/analyze.c) - hook fires from `parse_analyze_fixedparams`/`parse_analyze_varparams`/`parse_analyze_withcb`.
- [elog.h](../../../../raw/postgres-18/src/include/utils/elog.h) - `emit_log_hook_type`.
- [elog.c#EmitErrorReport](../../../../raw/postgres-18/src/backend/utils/error/elog.c#L1692) - hook fires for every log line.
- [miscadmin.h](../../../../raw/postgres-18/src/include/miscadmin.h), [ipc.h](../../../../raw/postgres-18/src/include/storage/ipc.h) - `shmem_request_hook_type` and `shmem_startup_hook_type`.
- [miscinit.c#process_shmem_requests](../../../../raw/postgres-18/src/backend/utils/init/miscinit.c#L1931), [ipci.c](../../../../raw/postgres-18/src/backend/storage/ipc/ipci.c) - hook invocation sites.
- [miscinit.c#process_shared_preload_libraries](../../../../raw/postgres-18/src/backend/utils/init/miscinit.c#L1903) - `_PG_init` is run from here when `process_shared_preload_libraries_in_progress` is true.
- [vacuum.c](../../../../raw/postgres-18/src/backend/commands/vacuum.c), [vacuum.c#ExecVacuum](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L162), [vacuum.c#vac_bulkdel_one_index](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L2651), [vacuum.c#vac_cleanup_one_index](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L2672) - VACUUM dispatch, per-index AM calls.
- [vacuumparallel.c](../../../../raw/postgres-18/src/backend/commands/vacuumparallel.c) - parallel VACUUM workers calling `ambulkdelete`/`amvacuumcleanup` and copying `IndexBulkDeleteResult` through DSM.
- [read_stream.c#read_stream_clear_strategy](../../../../raw/postgres-18/src/backend/storage/aio/read_stream.c#L1046-L1066), [read_stream.h:102](../../../../raw/postgres-18/src/include/storage/read_stream.h#L102) - the 18.6 exported strategy-clearing entry point.
- [vacuumlazy.c#failsafe-clear-strategy](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L1311-L1323) - the only in-tree caller, in VACUUM's wraparound failsafe.
- [autovacuum.c#db_comparator](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L1070-L1076) - launcher database-ordering comparator fixed by `4cc49cb7039`.
- [release-18.sgml](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L2016-L2062) - 18.6 release notes for the autovacuum database ordering and failsafe buffer-pool fixes.
- [vacuumlazy.c](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c) - lazy vacuum implementation, including `vacuum_error_callback`.
- [analyze.c](../../../../raw/postgres-18/src/backend/commands/analyze.c), [analyze.c#analyze_rel](../../../../raw/postgres-18/src/backend/commands/analyze.c#L109), [analyze.c#examine_attribute](../../../../raw/postgres-18/src/backend/commands/analyze.c#L1036), [analyze.c#std_typanalyze](../../../../raw/postgres-18/src/backend/commands/analyze.c#L1891) - ANALYZE driver and per-attribute `typanalyze`.
- [tableam.h](../../../../raw/postgres-18/src/include/access/tableam.h) - `relation_vacuum`, `scan_analyze_next_block`, `scan_analyze_next_tuple`, `table_relation_vacuum` wrapper.
- [amapi.h](../../../../raw/postgres-18/src/include/access/amapi.h) - `IndexAmRoutine`, `ambulkdelete`, `amvacuumcleanup`, `amparallelvacuumoptions`.
- [indexam.c#index_bulk_delete](../../../../raw/postgres-18/src/backend/access/index/indexam.c#L795), [indexam.c#index_vacuum_cleanup](../../../../raw/postgres-18/src/backend/access/index/indexam.c#L816) - generic dispatchers.
- [vacuum.h](../../../../raw/postgres-18/src/include/commands/vacuum.h) - parallel VACUUM option flags, `VacAttrStats`, type analyze callback types.
- [fdwapi.h](../../../../raw/postgres-18/src/include/foreign/fdwapi.h) - `AnalyzeForeignTable_function`.
- [fdwhandler.sgml#fdw-callbacks-analyze](../../../../raw/postgres-18/doc/src/sgml/fdwhandler.sgml#L1367) - FDW analyze callback documentation.
- [autovacuum.c](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c), [autovacuum.c#AutoVacLauncherMain](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L368), [autovacuum.c#AutoVacWorkerMain](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L1376), [autovacuum.c#do_autovacuum](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L1885), [autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L3173) - autovacuum process model.
- [bgworker.h](../../../../raw/postgres-18/src/include/postmaster/bgworker.h), [bgworker.c#RegisterBackgroundWorker](../../../../raw/postgres-18/src/backend/postmaster/bgworker.c#L940) - extension background workers.
- [progress.h](../../../../raw/postgres-18/src/include/commands/progress.h) - vacuum/analyze progress field constants.
- [guc_tables.c](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c), [config.sgml#guc-shared-preload-libraries](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L11004) - `shared_preload_libraries` GUC context.
- [xfunc.sgml](../../../../raw/postgres-18/doc/src/sgml/xfunc.sgml) - documentation pattern for `shmem_request_hook` and `shmem_startup_hook`.
- [How Custom Cumulative Statistics Work in PostgreSQL 18 (unverified)](../observability/custom-cumulative-statistics.md) - companion page for the cumulative-stats extension surface.

## Open Questions

- This page enumerates the in-process hook variables and AM/FDW callbacks
  observable on the vacuum/autovacuum/analyze paths in pinned
  `raw/postgres-18/` source. It does not exhaustively enumerate every minor
  per-callsite extension surface that vacuum-adjacent code shares with the
  rest of the backend (for example, `MemoryContextCallback`, error context
  callbacks, or `ErrorContextCallback`-based instrumentation in
  `vacuumlazy.c`); those are not pluggable extension hooks in the same sense
  ([vacuumlazy.c](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c)).
- This page documents existing PostgreSQL 18 behavior. It does not propose
  new vacuum or autovacuum hooks, nor a design for the future "separate
  callback to integrate with autovacuum's scheduling" suggested in the
  `relation_vacuum` header comment
  ([tableam.h](../../../../raw/postgres-18/src/include/access/tableam.h)).
