---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: claude-fable-5 2026-06-10T18:58:30Z
---

# How pg_stat_statements Works and Which Settings Affect It in PostgreSQL 12 (unverified)

## Question

> Follow AGENTS.md.
> In PostgreSQL 12, explain how `pg_stat_statements` works and give a comprehensive explanation of all configuration settings that affect `pg_stat_statements`.

## Short Answer

`pg_stat_statements` is a shared-preload contrib module that totals execution statistics for each distinct query across the whole server cluster and exposes them through the `pg_stat_statements` view [pg_stat_statements.c#header](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1-L34) [pgstatstatements.sgml#intro](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L10-L30). The SQL objects are installed per database with `CREATE EXTENSION pg_stat_statements`, but the statistics are server-wide because they live in shared memory [pgstatstatements.sgml#tracks-all-dbs](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L22-L30).

In PostgreSQL 12 the module computes its own query identifier. The v12 tree has no `compute_query_id` GUC and no in-core query jumble: `pgss_post_parse_analyze()` jumbles the parse-analysis tree itself, hashes it with `hash_any_extended()`, and stores the result in `Query.queryId` [pg_stat_statements.c#pgss_post_parse_analyze](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L778-L844) [pg_stat_statements.c#JumbleQuery-decls](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L332-L342). The only requirements for active collection are `shared_preload_libraries = 'pg_stat_statements'` and a tracking level other than `none`; `_PG_init()` returns without installing hooks unless it runs during shared-preload processing [pg_stat_statements.c#_PG_init](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L348-L439).

There are exactly four direct `pg_stat_statements.*` settings in v12: `max`, `track`, `track_utility`, and `save` [pg_stat_statements.c#custom-GUCs](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L365-L410) [pgstatstatements.sgml#config-params](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L393-L468). There is no `track_planning`, and the module records no planning-time, WAL, JIT, or parallel-worker columns. The other PostgreSQL settings that directly change visible output are `shared_preload_libraries` (enables the module) and `track_io_timing` (enables the `blk_read_time`/`blk_write_time` columns); ordinary planner and workload settings change the observed numbers only indirectly by changing plans, execution paths, row counts, and I/O.

## How Collection Works

### Query identification

PostgreSQL 12 calculates the query ID inside the extension at the end of parse analysis. The `post_parse_analyze_hook` runs `pgss_post_parse_analyze()`, which gives utility statements `queryId` zero and, for plannable statements, builds a query jumble (selectively serialized parse-tree fields that ignore constant values), then sets `query->queryId` to the 64-bit `hash_any_extended()` of the jumble; a zero hash is forced to 1 to avoid colliding with the utility-statement marker [pg_stat_statements.c#pgss_post_parse_analyze](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L778-L844). Because this hook is installed unconditionally when the module is shared-preloaded, there is no setting to turn query-ID computation on or off in v12 short of unloading the module.

Utility commands keep `queryId` zero through parse analysis; `pgss_store()` then derives their identity by hashing the query *text* with `pgss_hash_string()` (forcing a zero result to 2), which is why the docs say utility commands are compared on their textual strings rather than their parse trees [pg_stat_statements.c#utility-hash](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1081-L1086) [pg_stat_statements.c#pgss_store-utility-id](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1148-L1162) [pgstatstatements.sgml#normalization](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L236-L264).

### Entry identity and storage

The hash key is `(userid, dbid, queryid)`, so the same normalized query produces separate rows for different users and databases [pg_stat_statements.c#pgssHashKey](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L135-L140). (v12 has no top-level/nested flag in the key.) Each entry holds a fixed `Counters` struct: call count, total/min/max/mean execution time plus a running variance accumulator, rows, shared/local/temp block counters, block read/write times, and a usage factor [pg_stat_statements.c#Counters](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L145-L184).

The shared hash table is capped by `pg_stat_statements.max`; the shared memory is sized from that value in `pgss_memsize()` [pg_stat_statements.c#pgss_memsize](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1677-L1686). When the table is full, `entry_alloc()` repeatedly calls `entry_dealloc()`, which sorts entries by usage, applies a decay factor, and discards the least-used `USAGE_DEALLOC_PERCENT` (5%, minimum 10) of them [pg_stat_statements.c#entry_alloc](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1705-L1737) [pg_stat_statements.c#entry_dealloc](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1761-L1829). v12 has no `pg_stat_statements_info` view or `dealloc` counter; deallocations are not exposed in SQL.

Representative query text is **not** kept in shared memory. It lives in an external file `PG_STAT_TMP_DIR/pgss_query_texts.stat`; the shared entry stores only the offset, length, and encoding [pg_stat_statements.c#text-file-comment](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L29-L34) [pg_stat_statements.c#file-path](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L88-L96) [pg_stat_statements.c#pgssEntry](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L176-L184). This is why `track_activity_query_size` does not truncate `pg_stat_statements.query`: that GUC sizes `pg_stat_activity.query`, not this external file [guc.c#track_activity_query_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3164-L3173) [config.sgml#track_activity_query_size](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6820-L6836). New text is appended by `qtext_store()` under shared lock [pg_stat_statements.c#qtext_store](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1847-L1896). If the file grows too large, `gc_qtexts()` garbage-collects it, and on failure it drops texts by setting `query_len = -1`, so affected rows then show a null `query` while their statistics survive [pg_stat_statements.c#gc_qtexts](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L2081-L2145) [pgstatstatements.sgml#external-file](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L318-L330).

### Normalization and sticky entries

When parse analysis finds ignorable constants, `pgss_post_parse_analyze()` immediately calls `pgss_store()` with a non-NULL jumble state to create an early "sticky" entry, so the normalized representative text (constants replaced by `$n`) can be saved before execution finishes [pg_stat_statements.c#post-parse-sticky-store](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L828-L844) [pg_stat_statements.c#entry_alloc-sticky](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1694-L1737). Sticky entries get a median usage value and are skipped in output until they record a real call [pgstatstatements.sgml#norm-display](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L247-L316).

### Hooks and counter recording

`_PG_init()` installs the shared-memory startup hook plus the post-parse-analyze, `ExecutorStart`, `ExecutorRun`, `ExecutorFinish`, `ExecutorEnd`, and `ProcessUtility` hooks [pg_stat_statements.c#install-hooks](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L422-L439). The `pgss_enabled()` macro gates recording: it is true when `track = all`, or when `track = top` and `nested_level == 0` [pg_stat_statements.c#pgss_enabled](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L275-L277).

- `pgss_ExecutorStart()` allocates per-query instrumentation (`InstrAlloc`) when the statement has a nonzero `queryId` and tracking is enabled [pg_stat_statements.c#pgss_ExecutorStart](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L849-L878).
- `pgss_ExecutorRun()` and `pgss_ExecutorFinish()` only maintain `nested_level` so nested statements are attributed correctly [pg_stat_statements.c#run-finish](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L883-L925).
- `pgss_ExecutorEnd()` calls `pgss_store()` with elapsed time (converted to msec), `es_processed` rows, and the accumulated `BufferUsage` [pg_stat_statements.c#pgss_ExecutorEnd](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L930-L957).
- `pgss_ProcessUtility()` records utility commands only when `track_utility` is on and tracking is enabled; it explicitly excludes `EXECUTE`, `PREPARE`, and `DEALLOCATE`, and parses a `COPY` completion tag to count affected rows [pg_stat_statements.c#pgss_ProcessUtility](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L962-L1074).

`pgss_store()` looks up or creates the entry, then updates all counters under the per-entry spinlock: it bumps calls, total time, the Welford min/max/mean/variance state, rows, the shared/local/temp block counters, the block read/write times, and the usage factor [pg_stat_statements.c#pgss_store-counters](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1238-L1296).

### Reading the view

The view `pg_stat_statements` selects from the C function `pg_stat_statements(showtext boolean)`, which runs `pg_stat_statements_internal()` [pg_stat_statements--1.4.sql#view](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements--1.4.sql#L12-L45). That function errors if the module was not shared-preloaded, loads the query-text file when `showtext` is true, iterates the hash table, copies counters under the spinlock, computes the population standard deviation, and emits rows; sticky (unexecuted) entries are skipped [pg_stat_statements.c#internal-load-check](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1409-L1413) [pg_stat_statements.c#internal-readout](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1480-L1672).

Privilege filtering: only superusers and members of `pg_read_all_stats` can see the `queryid` and SQL text of other users' entries. Other users see the numeric statistics but get a null `queryid` and the literal text `<insufficient privilege>` for rows they do not own [pg_stat_statements.c#privacy-filter](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1406-L1407) [pg_stat_statements.c#privacy-rows](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1551-L1602) [pgstatstatements.sgml#security](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L228-L234).

### Reset, persistence, and crashes

`pg_stat_statements_reset(userid, dbid, queryid)` (the v12 1.7 signature) discards entries matching the supplied non-zero parameters, or all entries when every parameter is 0; it is superuser-only by default [pg_stat_statements--1.6--1.7.sql#reset](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements--1.6--1.7.sql#L13-L22) [pg_stat_statements.c#entry_reset](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L2265-L2354) [pgstatstatements.sgml#reset-doc](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L336-L359). On a clean shutdown, `pgss_shmem_shutdown()` dumps statistics to `PGSTAT_STAT_PERMANENT_DIRECTORY/pg_stat_statements.stat`, and `pgss_shmem_startup()` reloads them and then unlinks the dump file [pg_stat_statements.c#dump-file-path](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L85-L86) [pg_stat_statements.c#shmem_startup](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L463-L674) [pg_stat_statements.c#shmem_shutdown](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L682-L719). A crash is not dumped because `pgss_shmem_shutdown()` returns immediately when its exit code is nonzero [pg_stat_statements.c#crash-no-dump](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L692-L694).

## Direct pg_stat_statements Settings

| Setting | Scope | Effect |
|---|---|---|
| `pg_stat_statements.max` | `PGC_POSTMASTER`; restart required. Default `5000`, min `100`, max `INT_MAX` [pg_stat_statements.c#max-GUC](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L365-L376) [catalogs.sgml#context-postmaster](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10523-L10536). | Maximum number of tracked statements and therefore maximum normal rows in the view; shared memory is sized in proportion to this value even when `track = none`. Excess distinct statements trigger least-used deallocation [pg_stat_statements.c#pgss_memsize](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1677-L1686) [pg_stat_statements.c#entry_dealloc](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1761-L1829) [pgstatstatements.sgml#max-doc](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L397-L413) [pgstatstatements.sgml#memory-note](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L470-L475). |
| `pg_stat_statements.track` | `PGC_SUSET`; superusers can change it in-session with `SET` (no restart). Default `top` [pg_stat_statements.c#track-GUC](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L378-L388) [catalogs.sgml#context-superuser](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10588-L10600). | Values `top`, `all`, `none`. `top` records only nesting-level-zero statements, `all` also records nested statements (e.g. inside functions), `none` disables statistics recording while shared memory stays allocated [pg_stat_statements.c#track-options](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L254-L277) [pgstatstatements.sgml#track-doc](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L415-L432). |
| `pg_stat_statements.track_utility` | `PGC_SUSET`; superuser-changeable in-session. Default `on` [pg_stat_statements.c#track_utility-GUC](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L390-L399) [catalogs.sgml#context-superuser](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10588-L10600). | When on, the utility hook records commands other than `SELECT`, `INSERT`, `UPDATE`, and `DELETE`; when off, utility commands are passed through with no utility-level storage [pg_stat_statements.c#pgss_ProcessUtility](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L962-L1074) [pgstatstatements.sgml#track_utility-doc](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L434-L449). |
| `pg_stat_statements.save` | `PGC_SIGHUP`; reload required for config-file changes. Default `on` [pg_stat_statements.c#save-GUC](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L401-L410) [catalogs.sgml#context-sighup](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10537-L10551). | When on, a clean shutdown writes `pg_stat_statements.stat` and startup reloads it; when off, startup skips loading old statistics and shutdown skips dumping [pg_stat_statements.c#shmem_startup-save](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L546-L550) [pg_stat_statements.c#shmem_shutdown-save](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L700-L702) [pgstatstatements.sgml#save-doc](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L451-L467). |

## Core Settings That Directly Matter

`shared_preload_libraries` must include `pg_stat_statements` before the server starts. The GUC is `PGC_POSTMASTER`, the docs say it can only be set at server start, and `_PG_init()` installs no hooks unless shared-preload processing is in progress [guc.c#shared_preload_libraries](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3768-L3776) [config.sgml#shared_preload_libraries](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L8412-L8436) [pg_stat_statements.c#_PG_init-load-boundary](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L351-L360). If the SQL functions exist but the module was never shared-preloaded, reads and resets error with `pg_stat_statements must be loaded via shared_preload_libraries` [pg_stat_statements.c#internal-load-check](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1409-L1413) [pg_stat_statements.c#entry_reset-load-check](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L2274-L2277).

`track_io_timing` controls whether the `blk_read_time` and `blk_write_time` columns can be nonzero. The GUC is `PGC_SUSET`, defaults to `off`, and its docs explicitly list `pg_stat_statements` as a consumer of I/O timing [guc.c#track_io_timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1402-L1408) [config.sgml#track_io_timing](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6854-L6874). The module simply accumulates the timing fields already present in `BufferUsage`, so the two time columns reflect whether the core counters were populated [pg_stat_statements.c#blk-times](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1291-L1292) [pgstatstatements.sgml#blk-time-columns](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L204-L222).

No other setting changes the *set* of recorded fields in v12. Settings such as `work_mem`, `temp_buffers`, the planner cost/enable GUCs, and `search_path` change only the *values* the module records (temp-block usage, plans chosen, row counts) or how queries are grouped (`search_path` can split identical texts into different `queryid` entries) [pgstatstatements.sgml#queryid-stability](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L266-L304). These are indirect effects, not configuration of the module itself.

## Configuration Scope Cheat Sheet

| Context | Change requirement | Settings in this page |
|---|---|---|
| `postmaster` | Restart required [catalogs.sgml#context-postmaster](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10523-L10536). | `shared_preload_libraries`, `pg_stat_statements.max`. |
| `sighup` | Reload required; the postmaster rereads config and forwards SIGHUP to children [catalogs.sgml#context-sighup](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10537-L10551). | `pg_stat_statements.save`. |
| `superuser` / `PGC_SUSET` | Set in config or via `SET` in-session by superusers; config changes affect sessions with no session-local value [catalogs.sgml#context-superuser](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10588-L10600). | `pg_stat_statements.track`, `pg_stat_statements.track_utility`, `track_io_timing`. |

## v12 Specifics

- Query jumbling and the `queryId` hash are computed **inside the extension**, not in core; there is no `compute_query_id` GUC [pg_stat_statements.c#pgss_post_parse_analyze](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L778-L844).
- Only four module GUCs exist; there is no `pg_stat_statements.track_planning` [pg_stat_statements.c#custom-GUCs](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L365-L410).
- The hash key has three fields `(userid, dbid, queryid)` with no top-level flag [pg_stat_statements.c#pgssHashKey](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L135-L140).
- The view has 23 columns (extension version 1.7 / API 1.3): timing, rows, and shared/local/temp block counters plus block read/write times. There are no planning-time, WAL, or JIT columns [pg_stat_statements.control#version](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.control#L1-L5) [pg_stat_statements.c#col-counts](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1336-L1341) [pg_stat_statements--1.4.sql#columns](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements--1.4.sql#L12-L39).
- There is no `pg_stat_statements_info` view and no `dealloc` counter: the install scripts define only the `pg_stat_statements` view, and `Counters` has no deallocation field [Makefile#DATA](../../../../raw/postgres-12/contrib/pg_stat_statements/Makefile#L7-L11) [pg_stat_statements--1.4.sql#view](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements--1.4.sql#L41-L45) [pg_stat_statements.c#Counters](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L145-L167).

## Tests And Coverage

The v12 regression suite is a single `pg_stat_statements` test run with a temp config that preloads the extension [Makefile#REGRESS](../../../../raw/postgres-12/contrib/pg_stat_statements/Makefile#L16-L17). The script exercises simple and compound statements, multi-statement strings, CTEs, `PREPARE`/`EXECUTE`, CRUD counting, constant normalization (with and without an `IN` list), the three `track` levels (`none`, `top`, `all`) including PL/pgSQL and SQL functions, utility commands, and `pg_stat_statements_reset()` filtering by user, database, and queryid [pg_stat_statements.sql#coverage](../../../../raw/postgres-12/contrib/pg_stat_statements/sql/pg_stat_statements.sql#L1-L254). Installcheck is disabled because the tests require `shared_preload_libraries = pg_stat_statements` [Makefile#NO_INSTALLCHECK](../../../../raw/postgres-12/contrib/pg_stat_statements/Makefile#L18-L20).

## Context Reviewed

- [pg_stat_statements.c#header-and-structs](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1-L233)
- [pg_stat_statements.c#GUCs-and-hooks](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L252-L439)
- [pg_stat_statements.c#shmem-startup-shutdown](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L457-L719)
- [pg_stat_statements.c#hook-paths](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L775-L1074)
- [pg_stat_statements.c#store-and-readout](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1088-L1672)
- [pg_stat_statements.c#entry-text-reset-lifetime](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1677-L2354)
- [pgstatstatements.sgml#extension-docs](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L1-L597)
- [pg_stat_statements--1.4.sql#view-def](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements--1.4.sql#L1-L48)
- [pg_stat_statements--1.6--1.7.sql#reset-def](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements--1.6--1.7.sql#L1-L22)
- [pg_stat_statements.control](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.control#L1-L5)
- [pg_stat_statements.conf](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.conf#L1)
- [guc.c#related-GUCs](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1402-L1408)
- [catalogs.sgml#pg_settings-contexts](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10505-L10614)

## Evidence Map

| Claim | Source |
|---|---|
| Module is shared-preload-only and installs hooks from `_PG_init()` | [pg_stat_statements.c#_PG_init](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L348-L439) |
| Query ID is jumbled and hashed inside the extension at parse analysis; no `compute_query_id` GUC | [pg_stat_statements.c#pgss_post_parse_analyze](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L778-L844) |
| Utility statements are identified by hashing the query text | [pg_stat_statements.c#pgss_store-utility-id](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1148-L1162) |
| Entry identity is `(userid, dbid, queryid)` | [pg_stat_statements.c#pgssHashKey](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L135-L140) |
| `max` caps the hash table and drives deallocation | [pg_stat_statements.c#pgss_memsize](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1677-L1686) [pg_stat_statements.c#entry_dealloc](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1761-L1829) |
| Four GUCs: `max`, `track`, `track_utility`, `save` with their defaults/contexts | [pg_stat_statements.c#custom-GUCs](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L365-L410) [pgstatstatements.sgml#config-params](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L393-L468) |
| Execution and utility collection paths | [pg_stat_statements.c#pgss_ExecutorEnd](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L930-L957) [pg_stat_statements.c#pgss_ProcessUtility](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L962-L1074) |
| Query text lives in an external file, not shared memory | [pg_stat_statements.c#text-file-comment](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L29-L34) [pg_stat_statements.c#qtext_store](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1847-L1896) |
| Privilege filtering of `queryid` and query text | [pg_stat_statements.c#privacy-rows](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1551-L1602) [pgstatstatements.sgml#security](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L228-L234) |
| `track_io_timing` controls the two block-time columns only | [config.sgml#track_io_timing](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6854-L6874) [pg_stat_statements.c#blk-times](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1291-L1292) |
| `save`/crash persistence behavior | [pg_stat_statements.c#shmem_shutdown](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L682-L719) |
| 23-column view, extension version 1.7 | [pg_stat_statements.control#version](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.control#L1-L5) [pg_stat_statements--1.4.sql#columns](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements--1.4.sql#L12-L39) |

## Source References

- [pg_stat_statements.c](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c) - shared state, GUCs, hooks, query jumbling, storage, readout, reset, and query-text file lifetime.
- [pgstatstatements.sgml](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml) - same-version documentation for the view columns, normalization, security, functions, and configuration parameters.
- [pg_stat_statements--1.4.sql](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements--1.4.sql) and [pg_stat_statements--1.6--1.7.sql](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements--1.6--1.7.sql) - the 23-column function/view and the 1.7 reset signature.
- [pg_stat_statements.control](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.control) and [pg_stat_statements.conf](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.conf) - default extension version and the sample preload line.
- [guc.c](../../../../raw/postgres-12/src/backend/utils/misc/guc.c) and [catalogs.sgml#pg_settings-contexts](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10505-L10614) - core GUC contexts and the change-scope meanings.
- [Makefile](../../../../raw/postgres-12/contrib/pg_stat_statements/Makefile) and [pg_stat_statements.sql](../../../../raw/postgres-12/contrib/pg_stat_statements/sql/pg_stat_statements.sql) - same-checkout regression coverage.

## Open Questions

- Which later major release added each feature absent from v12 (`compute_query_id`, `pg_stat_statements.track_planning`, the top-level hash-key flag, `pg_stat_statements_info`/`dealloc`) cannot be evidenced from the v12 checkout, whose commit history predates those changes. This page states only the v12 absences; the v18 state is documented in [the v18 pg_stat_statements page](../../../v18/questions/observability/pg-stat-statements.md).
- The page remains `(unverified)` in the title because `verified:` is human-only.
