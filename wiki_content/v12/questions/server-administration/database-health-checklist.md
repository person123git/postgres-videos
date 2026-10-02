---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: claude-opus-5-max 2026-07-29T16:53:15Z
---

# PostgreSQL 12 Database Health Checklist (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [How to use this checklist](#how-to-use-this-checklist)
  - [Production query guardrails](#production-query-guardrails)
  - [Observability prerequisites](#observability-prerequisites)
  - [SQL health checklist](#sql-health-checklist)
  - [Database log checklist](#database-log-checklist)
  - [Issue interpretation and response](#issue-interpretation-and-response)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Prompt note: The user approved correcting typos and grammar before filing.

Produce a document with a checklist to check the health of the database. Include
what to check in the database log. For each possible issue found in the
checklist and/or log, explain the repercussions of the finding and possible root
causes. For each log item or internal stats data point, explain what needs to be
enabled, installed, or configured to produce the data.

## Answer

Use this as a layered health check. First confirm that PostgreSQL is collecting
the required data. Then inspect current activity, cumulative counters,
maintenance state, WAL and replication state, and optional query or bloat
extensions. Finally, correlate the findings with the server log. PostgreSQL 12
provides built-in dynamic views for current sessions and replication, and
collected views for database, table, archiver, and background-writer counters.
[monitoring.sgml#DynamicStatisticsViews](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L284-L360)
[monitoring.sgml#CollectedStatisticsViews](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L375-L425)

Treat cumulative values as rates over a known interval, not as isolated raw
totals. In `pg_stat_database`, only `numbackends` is current state; the other
columns accumulate until `stats_reset`. PostgreSQL sends collected statistics
asynchronously and caches the fetched snapshot until the end of the current
transaction. Collect comparison samples in separate autocommit transactions,
or call `pg_stat_clear_snapshot()` before a repeat read in the same
transaction.
[monitoring.sgml#pg_stat_database](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2510-L2528)
[monitoring.sgml#pg_stat_database_stats_reset](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2625-L2638)
[monitoring.sgml#statistics-lag-and-snapshots](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L229-L260)

### How to use this checklist

1. Run the observability query and resolve disabled, missing, or
   `pending_restart` settings before interpreting empty data.
2. Use a superuser for the complete cluster-wide capture on this exact pin. A
   role with `pg_monitor` can read most settings and statistics, but
   `pg_stat_get_progress_info()` publishes only the PID and database OID to
   every caller and gates `relid` plus all progress parameters behind
   `has_privs_of_role(GetUserId(), <the reporting role>)`; that test never
   consults `pg_read_all_stats`. On this pin a `pg_monitor` member watching a
   superuser's `VACUUM` therefore saw the row's `pid` and `datname` while
   `relid`, `phase`, and every counter were null. Confirm that another user's
   activity is visible before trusting an empty or null result.
   [user-manag.sgml#predefined-monitoring-roles](../../../../raw/postgres-12/doc/src/sgml/user-manag.sgml#L524-L538)
   [pgstatfuncs.c#pg_stat_get_progress_info-access](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L490-L531)
3. Run the core SQL checks in every application database. Run cluster-wide
   checks such as `pg_database`, `pg_stat_bgwriter`, `pg_stat_archiver`, and
   replication checks once from a database where the monitoring account can
   read them.
4. Compare each cumulative result with a previous capture from the same reset
   epoch. `pg_stat_database`, `pg_stat_bgwriter`, and `pg_stat_archiver` expose
   reset timestamps; the per-table views do not expose a per-row reset time.
   Record deliberate resets with the capture. `pg_stat_activity` and the
   replication views expose current state rather than cumulative history.
   [monitoring.sgml#DynamicStatisticsViews](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L294-L360)
   [monitoring.sgml#CollectedStatisticsViews](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L386-L425)
   [monitoring.sgml#pg_stat_all_tables-columns](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2704-L2845)
5. Search the server log over the same interval and correlate sessions by PID
   or session identifier. PostgreSQL recommends including PID or session ID in
   `log_line_prefix` when statement and duration messages need to be joined.
   [config.sgml#log_min_duration_statement](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5931-L5968)

If a diagnostic transaction must refresh collected statistics before another
read, clear its cached snapshot explicitly:

```sql
SELECT /* wiki_db_health_clear_stats_snapshot */ pg_stat_clear_snapshot();
```

The next statistics read fetches a new snapshot and no longer belongs to the
transaction's original stable capture.
[pg_proc.dat#pg_stat_clear_snapshot](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L5451-L5455)

### Production query guardrails

Start a diagnostic session with finite timeouts:

```sql
SET /* wiki_db_health_guardrails */ statement_timeout = '30s';
SET /* wiki_db_health_guardrails */ lock_timeout = '2s';
```

Both settings are `PGC_USERSET`, so they are session/transaction-scope changes;
zero disables each timeout.
[guc.c#statement_timeout-lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2396)
[guc.c#GucContext_Names](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L594-L603)

The catalog and statistics queries below do not intentionally take
table-changing locks. The optional `pgstattuple` checks read relation pages and
acquire a read lock; their results can also change during concurrent updates.
Run those checks only for selected relations, preferably outside peak traffic,
and raise `statement_timeout` only for that diagnostic session if required.
[pgstattuple.sgml#pgstattuple-locking](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L123-L142)

### Observability prerequisites

| Data or signal | What must be enabled, installed, or configured | Apply scope |
|---|---|---|
| Complete cross-role monitoring | Use a superuser for a complete capture on this exact PostgreSQL 12 pin. Without the predefined read roles, ordinary activity and `pg_stat_statements` fields are redacted and superuser-only `pg_settings` rows are filtered. `pg_monitor` is granted `pg_read_all_settings`, `pg_read_all_stats`, and `pg_stat_scan_tables`, removing those ordinary restrictions; however, `pg_stat_get_progress_info()` still tests role membership in the reporting role instead of consulting `pg_read_all_stats`. [user-manag.sgml#predefined-monitoring-roles](../../../../raw/postgres-12/doc/src/sgml/user-manag.sgml#L524-L538) [system_views.sql#pg_monitor-role-grants](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L1349-L1351) [pgstatfuncs.c#activity-access](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L625-L655) [guc.c#pg_settings-access](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L8998-L9008) [pgstatstatements.sgml#access](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L228-L234) [pgstatfuncs.c#progress-access](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L490-L531) | Role membership controls access; it is not a restart or reload setting. Re-run the capture after changing the monitoring role. |
| PostgreSQL-managed text or CSV log files | Use `stderr` or `csvlog` in `log_destination`. CSV requires `logging_collector`. `current_logfiles` records the active file path when the collector manages `stderr` or `csvlog`. If the deployment uses `syslog` or Windows `eventlog`, inspect that destination instead. [config.sgml#log_destination](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5439-L5486) | `logging_collector` is `PGC_POSTMASTER`: restart. `log_destination` is `PGC_SIGHUP`: reload. [guc.c#logging_collector](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1617-L1623) [guc.c#log_destination](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3849-L3858) |
| Correlatable log lines | Configure `log_line_prefix` with at least PID or a session identifier so statement, duration, lock, and disconnect messages can be joined. [config.sgml#log_min_duration_statement](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5956-L5968) | `log_line_prefix` is `PGC_SIGHUP`: reload. [guc.c#log_line_prefix](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3593-L3599) |
| Server-log severity and diagnostic detail | Ensure `log_min_messages` admits the built-in severities being searched. `log_min_error_statement` controls whether an error's SQL text is included, and `log_error_verbosity` controls diagnostic detail. [config.sgml#server-log-levels](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5877-L5927) | All three are `PGC_SUSET`: superuser session/transaction scope. Set cluster defaults for consistent coverage. [guc.c#log-level-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4287-L4315) |
| Current sessions, transaction age, query text, and waits | Keep `track_activities` enabled. `pg_stat_activity` exposes session state, transaction/query start times, waits, query text, and `backend_xmin`. Increase `track_activity_query_size` if 1024 bytes is too short for useful query text. [system_views.sql#pg_stat_activity](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L732-L756) [config.sgml#track_activity_query_size](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6820-L6834) | `track_activities` is `PGC_SUSET`: superuser session/transaction scope. `track_activity_query_size` is `PGC_POSTMASTER`: restart. [guc.c#track_activities](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1382-L1390) [guc.c#track_activity_query_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3164-L3172) |
| Database and table counters used by autovacuum and health checks | Keep `track_counts` enabled. It enables database activity statistics and is required for normal autovacuum operation. [config.sgml#track_counts](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6838-L6850) [config.sgml#autovacuum](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6985-L7005) | `track_counts` is `PGC_SUSET`: superuser session/transaction scope. Configure it as the cluster default when all sessions and autovacuum must collect data. [guc.c#track_counts](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1392-L1399) |
| Database, `EXPLAIN (BUFFERS)`, and `pg_stat_statements` I/O time | Enable `track_io_timing` when the platform overhead is acceptable. It is off by default and supplies `blk_read_time` and `blk_write_time`. [config.sgml#track_io_timing](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6854-L6871) | `track_io_timing` is `PGC_SUSET`: superuser session/transaction scope. Set it as a cluster default if complete workload timing is required. [guc.c#track_io_timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1401-L1408) |
| Slow statements, lock waits, temp files, checkpoints, autovacuum, connection lifecycle, and replication commands in the log | Configure the corresponding logging GUC. `deadlock_timeout` controls when `log_lock_waits` emits detail as well as when the deadlock check starts. [config.sgml#log_min_duration_statement](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5931-L5949) [config.sgml#logging-operational-events](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6165-L6222) [config.sgml#lock-and-temp-logging](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6477-L6574) [config.sgml#log_autovacuum_min_duration](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7010-L7033) | `log_checkpoints` and `log_autovacuum_min_duration` are `PGC_SIGHUP`: reload. `log_connections` and `log_disconnections` are `PGC_SU_BACKEND`: reload a file change; the postmaster passes it only to subsequently started sessions, while existing sessions keep the old value. The other listed logging GUCs and `deadlock_timeout` are `PGC_SUSET`: superuser session/transaction scope. [guc.c#logging-booleans](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1217-L1251) [guc.c#log_lock_waits](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1489-L1497) [guc.c#deadlock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2062-L2071) [guc.c#logging-thresholds](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2703-L2724) [guc.c#log_temp_files](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3153-L3161) [guc.c#PGC_SU_BACKEND-reload](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L6811-L6858) |
| Per-statement workload totals | Install the PostgreSQL 12 `pg_stat_statements` contrib module, add it to `shared_preload_libraries`, restart, and run `CREATE /* wiki_enable_pgss */ EXTENSION pg_stat_statements;` in each database where its SQL view is needed. Confirm that `pg_stat_statements.track` is not `none`; other users' `queryid` and query text require superuser or `pg_read_all_stats`. [pgstatstatements.sgml#loading](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L10-L30) [pgstatstatements.sgml#access](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L228-L234) | `shared_preload_libraries` and `pg_stat_statements.max` require restart. `pg_stat_statements.track` and `pg_stat_statements.track_utility` are superuser session/transaction settings; `pg_stat_statements.save` is a reload setting. [guc.c#shared_preload_libraries](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3768-L3775) [pg_stat_statements.c#module-GUCs](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L365-L410) |
| Exact or approximate heap bloat and B-tree structure | Install the PostgreSQL 12 `pgstattuple` contrib module and run `CREATE /* wiki_enable_pgstattuple */ EXTENSION pgstattuple;` in the target database. Use a superuser or membership in `pg_stat_scan_tables`; the version 1.5 update revokes public execution and grants these inspection functions to that predefined role. [pgstattuple.sgml#module-and-privileges](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L10-L23) [pgstattuple--1.4--1.5.sql#scan-role-grants](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L6-L119) | Extension creation is per database. The SQL scripts bind the functions to the contrib shared library when the extension is created or updated. [pgstattuple--1.4.sql#functions](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L3-L20) [pgstattuple--1.4--1.5.sql#version-1.5-functions](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L6-L119) |
| Checksum failures | `data_checksums` is a read-only `PGC_INTERNAL` preset that reports whether checksums are enabled. PostgreSQL verifies a checksum when it reads a page, so a zero counter does not prove that every stored page has been read and verified. Also inspect `ignore_checksum_failure` and `zero_damaged_pages`; both alter failure handling and should be false during normal operation. [bufmgr.c#checksum-read-path](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L897-L925) [bufpage.c#PageIsVerified](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L145-L161) [guc.c#data_checksums](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1826-L1835) [guc.c#damaged-page-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1135-L1161) [monitoring.sgml#checksum_failures](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2599-L2611) | Enabling checksums requires `initdb --data-checksums` at cluster creation or a clean shutdown followed by offline `pg_checksums --enable`. The two failure-handling GUCs are `PGC_SUSET`: superuser session/transaction scope. [initdb.sgml#data-checksums](../../../../raw/postgres-12/doc/src/sgml/ref/initdb.sgml#L212-L225) [pg_checksums.sgml#operation](../../../../raw/postgres-12/doc/src/sgml/ref/pg_checksums.sgml#L38-L51) [pg_checksums.sgml#notes](../../../../raw/postgres-12/doc/src/sgml/ref/pg_checksums.sgml#L204-L225) |
| Archiving, physical replication, logical replication, and slots | Define the expected topology first. Physical streaming needs `wal_level = replica` or higher, sender capacity, an authorized replication connection, and standby connection/recovery settings. Logical replication needs `wal_level = logical` on the publisher plus slot, sender, logical-worker, and background-worker capacity. Empty views are expected only when that component is not part of the intended topology. `pg_stat_replication` lists directly connected consumers only. [high-availability.sgml#physical-replication-setup](../../../../raw/postgres-12/doc/src/sgml/high-availability.sgml#L666-L715) [logical-replication.sgml#logical-replication-config](../../../../raw/postgres-12/doc/src/sgml/logical-replication.sgml#L545-L573) [monitoring.sgml#direct-replication-connections](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L1978-L1983) | `wal_level`, `archive_mode`, `max_wal_senders`, `max_replication_slots`, `primary_conninfo`, `primary_slot_name`, `hot_standby`, `max_worker_processes`, and `max_logical_replication_workers` require restart. Archive commands/timeouts, `wal_keep_segments`, standby feedback/delays, receiver status/timeouts, `synchronous_standby_names`, and `max_sync_workers_per_subscription` reload. `wal_sender_timeout` and `synchronous_commit` are session/transaction settings. [guc.c#archive_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1964-L1974) [guc.c#standby-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1752-L1769) [guc.c#replication-timeouts](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2062-L2126) [guc.c#wal_keep_segments](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2533-L2541) [guc.c#sender-capacity-and-timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2635-L2665) [guc.c#logical-worker-capacity](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2788-L2821) [guc.c#archive_command](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3454-L3462) [guc.c#standby-connection-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3550-L3578) [guc.c#synchronous_standby_names](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4086-L4095) [guc.c#synchronous_commit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4353-L4361) [guc.c#archive_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4363-L4371) [guc.c#wal_level](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4409-L4417) |

Check the effective settings before collecting evidence:

```sql
SELECT /* wiki_db_health_observability */
       name,
       CASE
         WHEN name = 'primary_conninfo' AND setting = '' THEN '(empty)'
         WHEN name = 'primary_conninfo' THEN '(set; redacted)'
         ELSE setting
       END AS setting,
       unit,
       context,
       source,
       pending_restart
FROM pg_settings
WHERE name IN (
    'archive_command',
    'archive_mode',
    'archive_timeout',
    'autovacuum',
    'autovacuum_freeze_max_age',
    'autovacuum_multixact_freeze_max_age',
    'checkpoint_warning',
    'data_checksums',
    'deadlock_timeout',
    'hot_standby',
    'hot_standby_feedback',
    'idle_in_transaction_session_timeout',
    'ignore_checksum_failure',
    'log_autovacuum_min_duration',
    'log_checkpoints',
    'log_connections',
    'log_destination',
    'log_disconnections',
    'log_error_verbosity',
    'log_line_prefix',
    'log_lock_waits',
    'log_min_duration_statement',
    'log_min_error_statement',
    'log_min_messages',
    'log_replication_commands',
    'log_temp_files',
    'logging_collector',
    'max_connections',
    'max_locks_per_transaction',
    'max_logical_replication_workers',
    'max_prepared_transactions',
    'max_replication_slots',
    'max_standby_archive_delay',
    'max_standby_streaming_delay',
    'max_sync_workers_per_subscription',
    'max_wal_senders',
    'max_wal_size',
    'max_worker_processes',
    'pg_stat_statements.max',
    'pg_stat_statements.save',
    'pg_stat_statements.track',
    'pg_stat_statements.track_utility',
    'primary_conninfo',
    'primary_slot_name',
    'shared_preload_libraries',
    'superuser_reserved_connections',
    'synchronous_commit',
    'synchronous_standby_names',
    'temp_file_limit',
    'track_activities',
    'track_activity_query_size',
    'track_counts',
    'track_io_timing',
    'wal_level',
    'wal_keep_segments',
    'wal_receiver_status_interval',
    'wal_receiver_timeout',
    'wal_sender_timeout',
    'zero_damaged_pages'
)
ORDER BY name;
```

`pg_settings` is backed by `pg_show_all_settings()`, and `pending_restart`
identifies a file change that has not taken effect because a restart is still
required.
[system_views.sql#pg_settings](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L512-L524)
[guc.c:9211](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L9211)
[catalogs.sgml#pg_settings_pending_restart](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10494-L10498)

Absence is not proof that a signal is healthy. A `GUC_SUPERUSER_ONLY` setting is
filtered out of `pg_settings` for an unprivileged reader: on this pin an
ordinary role saw only `archive_command` out of the three names
`shared_preload_libraries`, `data_directory`, and `archive_command`, while both
a superuser and a `pg_monitor` member saw all three. Activity and extension
fields can also be null or replaced by a placeholder because of access checks:
without role membership or `pg_read_all_stats`, `pg_stat_statements` nulls
`queryid` and, when query text was requested, substitutes
`<insufficient privilege>` for it. Finally, an event-specific log can be absent
simply because no qualifying event occurred during the interval. Resolve
configuration and access first.
[guc.c#pg_settings-access](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L8998-L9008)
[pg_stat_statements.c#query-redaction](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1588-L1601)

### SQL health checklist

**1. Current sessions, old transactions, and waits**

```sql
SELECT /* wiki_db_health_activity_summary */
       backend_type,
       state,
       wait_event_type,
       wait_event,
       count(*) AS processes,
       min(xact_start) AS oldest_xact_start,
       min(query_start) FILTER (WHERE state = 'active') AS oldest_active_query_start
FROM pg_stat_activity
GROUP BY backend_type, state, wait_event_type, wait_event
ORDER BY processes DESC, backend_type, state, wait_event_type, wait_event;

SELECT /* wiki_db_health_connection_capacity */
       count(*) FILTER (WHERE backend_type = 'client backend') AS client_backends,
       current_setting('max_connections')::integer AS max_connections,
       current_setting('superuser_reserved_connections')::integer AS reserved_connections,
       current_setting('max_connections')::integer
         - current_setting('superuser_reserved_connections')::integer
         AS ordinary_client_capacity
FROM pg_stat_activity;

SELECT /* wiki_db_health_long_transactions */
       pid,
       usename,
       application_name,
       backend_type,
       state,
       now() - xact_start AS transaction_age,
       backend_xmin,
       wait_event_type,
       wait_event,
       query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

`pg_stat_activity` defines `xact_start`, `query_start`, state-change time, and
wait-event fields. Its rows include client backends, autovacuum processes,
WAL processes, background workers, and other server processes. A `Lock` wait
is a heavyweight lock wait; a `BufferPin` wait can be prolonged by another
process holding an open cursor.
[monitoring.sgml#pg_stat_activity-timestamps-and-waits](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L659-L718)
[monitoring.sgml#backend_type](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L839-L860)
[pgstat.c#backend-type-names](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L4273-L4312)

Checklist:

- [ ] Compare only `client backend` rows with `max_connections`, and preserve
  the `superuser_reserved_connections` margin. Do not count autovacuum,
  background workers, or WAL senders as client connections; PostgreSQL sizes
  those process classes separately in `MaxBackends`.
  [guc.c#max_connections-reserved](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2130-L2147)
  [postinit.c#InitializeMaxBackends](../../../../raw/postgres-12/src/backend/utils/init/postinit.c#L528-L539)
  [postinit.c#reserved-connections](../../../../raw/postgres-12/src/backend/utils/init/postinit.c#L818-L828)
- [ ] Investigate old active or `idle in transaction` sessions, especially rows
  with old `backend_xmin`. VACUUM warns when the oldest xmin is far in the past
  and points to open transactions, old prepared transactions, and stale
  replication slots as possible causes.
  [vacuum.c#vacuum_set_xid_limits](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L933-L949)
- [ ] Investigate sustained `Lock`, `BufferPin`, or `IO` waits. These identify
  different wait classes and should be correlated with the lock and log checks
  below.
  [monitoring.sgml#wait_event_type](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L687-L760)

**2. Blocking locks and deadlocks**

```sql
SELECT /* wiki_db_health_blockers */
       waiter.pid AS waiting_pid,
       waiter.usename AS waiting_user,
       waiter.application_name AS waiting_application,
       waiter.wait_event AS waiting_event,
       now() - waiter.query_start AS waiting_query_age,
       blocker_pid.pid AS blocking_pid,
       CASE WHEN blocker_pid.pid = 0 THEN 'prepared transaction'
            ELSE blocker.backend_type
       END AS blocking_type,
       blocker.usename AS blocking_user,
       blocker.application_name AS blocking_application,
       blocker.state AS blocking_state,
       waiter.query AS waiting_query,
       blocker.query AS blocking_query
FROM pg_stat_activity AS waiter
CROSS JOIN LATERAL
     unnest(pg_blocking_pids(waiter.pid)) AS blocker_pid(pid)
LEFT JOIN pg_stat_activity AS blocker
  ON blocker.pid = NULLIF(blocker_pid.pid, 0)
WHERE waiter.wait_event_type = 'Lock'
ORDER BY waiting_query_age DESC, waiting_pid, blocking_pid;

SELECT /* wiki_db_health_prepared_transactions */
       transaction,
       gid,
       prepared,
       now() - prepared AS prepared_age,
       owner,
       database
FROM pg_prepared_xacts
ORDER BY prepared;

SELECT /* wiki_db_health_prepared_transaction_locks */
       p.transaction,
       p.gid,
       p.prepared,
       now() - p.prepared AS prepared_age,
       p.owner,
       p.database,
       l.locktype,
       l.mode,
       l.granted,
       l.database AS lock_database_oid,
       l.relation AS relation_oid
FROM pg_prepared_xacts AS p
JOIN pg_locks AS l
  ON l.virtualtransaction = '-1/' || p.transaction::text
WHERE l.granted
ORDER BY p.prepared, p.gid, l.locktype, l.mode;
```

`pg_blocking_pids()` reports both hard blockers and sessions ahead of the
waiter in the lock queue. It returns PID zero when a prepared transaction is
the blocker. A prepared transaction cannot itself be waiting, but it continues
holding acquired locks; its `pg_locks.pid` is null and its virtual transaction
is represented as `-1/<transaction>`. Keep cluster-wide database and relation
identifiers as OIDs rather than casting them in the current database.
[func.sgml#pg_blocking_pids](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L17584-L17604)
[catalogs.sgml#prepared-transaction-locks](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L9300-L9331)
[catalogs.sgml#pg_prepared_xacts](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L9627-L9710)

On this pin one prepared transaction holding `AccessExclusiveLock` on a table
made a waiting `SELECT` report `blocking_pid = 0` with
`blocking_type = prepared transaction`, and the prepared-lock query returned
that retained relation lock plus the transaction's own `ExclusiveLock` under
`virtualtransaction = '-1/<transaction>'`.

The prepared-lock query lists possible prepared blockers; when several
prepared transactions exist, PID zero alone does not map a waiter to one GID.
Exact matching would also need lock tags, conflict modes, and queue order.
Poll `pg_blocking_pids()` at a reasonable interval because it briefly takes
exclusive access to shared lock-manager state.
[func.sgml#pg_blocking_pids-locking](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L17584-L17604)

Checklist:

- [ ] Investigate each reported blocker and the waiter's requested operation.
  Do not infer blockers by self-joining `pg_locks`: PostgreSQL's queue order,
  parallel query groups, and prepared transactions make that incomplete.
  [catalogs.sgml#pg_locks-blocker-identification](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L9309-L9345)
- [ ] Enable `log_lock_waits` to obtain holder and waiter detail after
  `deadlock_timeout`. `deadlock_timeout` controls both that logging delay and
  when PostgreSQL runs the deadlock check; it is `PGC_SUSET`, so it has
  superuser session/transaction scope.
  [config.sgml#log_lock_waits](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6477-L6490)
  [guc.c#deadlock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2062-L2071)
  [proc.c#lock-wait-log](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1377-L1497)
- [ ] Treat any increase in `pg_stat_database.deadlocks` as an application or
  operational concurrency defect. PostgreSQL detects the deadlock, reports it
  to statistics, and aborts one transaction with `deadlock detected`.
  [deadlock.c#DeadLockReport](../../../../raw/postgres-12/src/backend/storage/lmgr/deadlock.c#L1139-L1146)
  [monitoring.sgml#deadlocks](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2594-L2598)

**3. Database-wide counters**

```sql
SELECT /* wiki_db_health_database_counters */
       datname,
       numbackends,
       xact_commit,
       xact_rollback,
       conflicts,
       temp_files,
       temp_bytes,
       deadlocks,
       checksum_failures,
       checksum_last_failure,
       blk_read_time,
       blk_write_time,
       stats_reset
FROM pg_stat_database
ORDER BY datname NULLS LAST;

SELECT /* wiki_db_health_standby_conflicts */
       datname,
       confl_tablespace,
       confl_lock,
       confl_snapshot,
       confl_bufferpin,
       confl_deadlock
FROM pg_stat_database_conflicts
ORDER BY datname;
```

Checklist:

- [ ] Capture deltas for rollbacks, temporary-file counts and bytes, deadlocks,
  checksum failures, and I/O time. Temporary-file counters include all temp
  files regardless of `log_temp_files`; I/O time requires `track_io_timing`;
  checksum counters are `NULL` when checksums are disabled. For normal buffer
  reads, a zero checksum delta covers only pages read during the interval;
  PostgreSQL verifies and reports the checksum on that page-read path. See
  `Open Questions` for a separate base-backup accounting defect in this pin.
  [monitoring.sgml#pg_stat_database-counters](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2524-L2628)
  [bufmgr.c#checksum-read-path](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L897-L925)
  [bufpage.c#PageIsVerified](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L145-L161)
- [ ] On a standby, capture recovery-conflict deltas by reason. The view records
  cancellations needed so WAL replay can proceed after tablespace drops,
  conflicting locks, obsolete snapshots, buffer pins, or recovery deadlocks.
  Those are exactly the five `PROCSIG_RECOVERY_CONFLICT_*` reasons that the
  collector counts; a sixth reason, a dropped database, is deliberately not
  counted. These counters are not application `lock_timeout` events or the
  primary `pg_stat_database.deadlocks` counter. The view contains useful data
  only on standby servers. On this pin a repeatable-read standby query whose
  rows the primary then removed and vacuumed produced `confl_snapshot = 1`
  together with a client `canceling statement due to conflict with recovery`
  error.
  [monitoring.sgml#pg_stat_database_conflicts](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2640-L2702)
  [procsignal.h#ProcSignalReason](../../../../raw/postgres-12/src/include/storage/procsignal.h#L37-L43)
  [pgstat.c#pgstat_recv_recoveryconflict](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6330-L6362)
  [standby.c#ResolveRecoveryConflictWithLock](../../../../raw/postgres-12/src/backend/storage/ipc/standby.c#L388-L423)

**4. Vacuum, analyze, dead rows, and progress**

```sql
SELECT /* wiki_db_health_vacuum_candidates */
       schemaname,
       relname,
       n_live_tup,
       n_dead_tup,
       last_vacuum,
       last_autovacuum,
       vacuum_count,
       autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC, schemaname, relname
LIMIT 50;

SELECT /* wiki_db_health_analyze_candidates */
       schemaname,
       relname,
       n_live_tup,
       n_mod_since_analyze,
       last_analyze,
       last_autoanalyze,
       analyze_count,
       autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC, schemaname, relname
LIMIT 50;

SELECT /* wiki_db_health_partitioned_parents */
       n.nspname AS schemaname,
       c.relname,
       c.oid::regclass AS partitioned_parent
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind = 'p'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname !~ '^pg_toast'
ORDER BY n.nspname, c.relname;

SELECT /* wiki_db_health_toast_maintenance */
       u.relid::regclass AS owning_relation,
       ts.relid::regclass AS toast_relation,
       ts.n_live_tup,
       ts.n_dead_tup,
       ts.last_vacuum,
       ts.last_autovacuum,
       ts.vacuum_count,
       ts.autovacuum_count
FROM pg_stat_user_tables AS u
JOIN pg_class AS c ON c.oid = u.relid
JOIN pg_stat_sys_tables AS ts ON ts.relid = c.reltoastrelid
ORDER BY ts.n_dead_tup DESC, owning_relation
LIMIT 50;

SELECT /* wiki_db_health_vacuum_progress */
       pid,
       datname,
       relid::regclass AS relation,
       phase,
       heap_blks_total,
       heap_blks_scanned,
       heap_blks_vacuumed,
       index_vacuum_count,
       max_dead_tuples,
       num_dead_tuples
FROM pg_stat_progress_vacuum
WHERE datname = current_database()
ORDER BY pid;
```

Rank vacuum and analyze pressure independently. PostgreSQL computes the two
thresholds independently from a base threshold plus a scale factor multiplied
by `pg_class.reltuples`; per-relation storage parameters can override the GUC
defaults. The tuple counts are discovery signals, not proof that maintenance
is overdue.
[autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2920-L2956)
[autovacuum.c#effective-thresholds](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2995-L3067)

`pg_stat_user_tables` exposes estimated live/dead rows, modifications since
analyze, and maintenance timestamps and counts, but it omits partitioned
parents and filters out the `pg_toast` schemas. PostgreSQL 12 autovacuum
examines regular/materialized tables and their TOAST relations, but it does not
select partitioned parents. `ANALYZE` can recurse through partitions and update
parent statistics, so deployments that use parent-level planning need an
explicit parent `ANALYZE` policy.
[system_views.sql#table-statistics-views](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L552-L616)
[autovacuum.c#first-pass-relkind-filter](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2035-L2067)
[autovacuum.c#second-pass-TOAST-scan](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2140-L2191)
[analyze.c#analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L231-L268)
[ref/analyze.sgml#partitioned-tables](../../../../raw/postgres-12/doc/src/sgml/ref/analyze.sgml#L112-L121)

`pg_stat_progress_vacuum` exposes one row for each running regular or autovacuum
worker, but not `VACUUM FULL`. The view includes workers in every database;
filtering to `current_database()` makes the `regclass` cast resolve in the
correct database.
[monitoring.sgml#pg-stat-progress-vacuum-view](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3738-L3849)
[pgstatfuncs.c#progress-backend-loop](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L490-L525)
[regproc.c#regclassout](../../../../raw/postgres-12/src/backend/utils/adt/regproc.c#L969-L1022)

Checklist:

- [ ] Investigate tables whose dead-row or modification counts grow while
  autovacuum/analyze timestamps do not advance. Autovacuum compares dead tuples
  and changes-since-analyze with base-plus-scale-factor thresholds, skips
  per-table-disabled relations unless wraparound forces a vacuum, and skips
  ordinary threshold work when statistics are unavailable.
  [autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2920-L2956)
  [autovacuum.c#threshold-decision](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L3026-L3091)
- [ ] Confirm `autovacuum` and `track_counts` are enabled before treating missing
  automatic maintenance as a table-level problem. `autovacuum` is a reload
  setting; per-table storage parameters can still disable normal autovacuum.
  [config.sgml#autovacuum](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6985-L7005)
  [guc.c#autovacuum](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1426-L1432)
- [ ] Review partitioned parents separately and schedule recursive `ANALYZE`
  where queries depend on parent statistics. Review TOAST maintenance by its
  owning relation instead of assuming `pg_stat_user_tables` covers it.

**5. Transaction-ID and MultiXact age**

```sql
SELECT /* wiki_db_health_database_xid_mxid_age */
       datname,
       age(datfrozenxid) AS xid_age,
       mxid_age(datminmxid) AS mxid_age
FROM pg_database
ORDER BY datname;

SELECT /* wiki_db_health_relation_xid_age */
       c.oid::regclass AS relation,
       greatest(age(c.relfrozenxid), age(t.relfrozenxid)) AS xid_age,
       c.reloptions AS relation_options,
       t.reloptions AS toast_options
FROM pg_class AS c
LEFT JOIN pg_class AS t ON t.oid = c.reltoastrelid
WHERE c.relkind IN ('r', 'm')
ORDER BY xid_age DESC NULLS LAST
LIMIT 50;

SELECT /* wiki_db_health_relation_mxid_age */
       c.oid::regclass AS relation,
       greatest(mxid_age(c.relminmxid), mxid_age(t.relminmxid)) AS mxid_age,
       c.reloptions AS relation_options,
       t.reloptions AS toast_options
FROM pg_class AS c
LEFT JOIN pg_class AS t ON t.oid = c.reltoastrelid
WHERE c.relkind IN ('r', 'm')
ORDER BY mxid_age DESC NULLS LAST
LIMIT 50;
```

PostgreSQL stores table and database freeze cutoffs in `relfrozenxid` and
`datfrozenxid`; `age()` measures transactions from that cutoff. `datminmxid`
is the database-level MultiXact horizon, while `relminmxid` is the relation
horizon. Run the database query cluster-wide and the two relation rankings in
each database. Keeping the XID and MultiXact rankings separate prevents one
top-50 limit from concealing the other risk.
[catalogs.sgml#pg_database-horizons](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L2662-L2687)
[maintenance.sgml#xid-age-queries](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L557-L585)
[maintenance.sgml#multixact-age](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L655-L686)

Checklist:

- [ ] Treat `autovacuum_freeze_max_age` and
  `autovacuum_multixact_freeze_max_age` as early alert ceilings, not exact
  remaining capacity. Per-relation options can lower both limits, and
  MultiXact member-space pressure can lower the effective MultiXact threshold
  further, including to zero. The two cluster max-age GUCs require restart.
  [autovacuum.c#effective-freeze-ages](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L3018-L3041)
  [multixact.c#MultiXactMemberFreezeThreshold](../../../../raw/postgres-12/src/backend/access/transam/multixact.c#L2785-L2844)
  [config.sgml#autovacuum-freeze-max-age](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7156-L7179)
  [config.sgml#autovacuum-multixact-freeze-max-age](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7184-L7208)
- [ ] Escalate XID and MultiXact warnings independently. PostgreSQL has
  distinct warning and stop-limit paths for transaction IDs, MultiXact IDs,
  and MultiXact member space.
  [maintenance.sgml#wraparound-warning-shutdown](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L608-L635)
  [multixact.c#MultiXact-emergency-limits](../../../../raw/postgres-12/src/backend/access/transam/multixact.c#L920-L1140)

**6. Checkpoints and background writes**

```sql
SELECT /* wiki_db_health_bgwriter */
       checkpoints_timed,
       checkpoints_req,
       checkpoint_write_time,
       checkpoint_sync_time,
       buffers_checkpoint,
       buffers_clean,
       maxwritten_clean,
       buffers_backend,
       buffers_backend_fsync,
       buffers_alloc,
       stats_reset
FROM pg_stat_bgwriter;
```

Checklist:

- [ ] Compare two samples that share `stats_reset`. `checkpoints_req` counts
  requested checkpoints generally. Only the specific `checkpoints are
  occurring too frequently` message identifies the WAL-caused path and
  suggests increasing `max_wal_size`.
  [monitoring.sgml#pg_stat_bgwriter](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2399-L2484)
  [checkpointer.c#checkpoint-warning](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L447-L462)
- [ ] A `maxwritten_clean` delta means the background writer stopped a pass
  after reaching `bgwriter_lru_maxpages`. `buffers_backend` counts buffers
  written directly by backends; a nonzero value alone is not a failure, so
  compare its delta with workload and the other write counters.
  [bufmgr.c#BgBufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2260-L2300)
- [ ] Treat `buffers_backend_fsync` as the stronger signal. PostgreSQL
  increments it when a backend must perform its own fsync because no
  checkpointer exists or the fsync-request queue remains full after
  compaction.
  [checkpointer.c#ForwardSyncRequest](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1086-L1159)
- [ ] Investigate repeated `checkpoints are occurring too frequently` messages.
  PostgreSQL emits that warning for WAL-caused checkpoints inside
  `checkpoint_warning` and explicitly suggests increasing `max_wal_size`.
  Both settings are reload settings.
  [checkpointer.c#CheckpointerMain](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L447-L462)
  [guc.c#checkpoint-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2555-L2587)
- [ ] Enable `log_checkpoints` when buffer counts and checkpoint write/sync
  duration are needed per checkpoint, rather than only as cumulative counters.
  [config.sgml#log_checkpoints](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6165-L6178)
  [xlog.c#LogCheckpointEnd](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L8408-L8453)
- [ ] If measured deltas justify tuning `bgwriter_lru_maxpages`,
  `bgwriter_lru_multiplier`, or `bgwriter_delay`, all three settings reload;
  they do not require restart.
  [guc.c#bgwriter-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2728-L2755)
  [guc.c#bgwriter_lru_multiplier](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3351-L3359)

**7. Archiving, replication, and retained WAL**

```sql
SELECT /* wiki_db_health_archiver */
       archived_count,
       last_archived_wal,
       last_archived_time,
       failed_count,
       last_failed_wal,
       last_failed_time,
       stats_reset
FROM pg_stat_archiver;

SELECT /* wiki_db_health_archive_backlog */
       count(*) FILTER (WHERE name LIKE '%.ready') AS ready_files,
       min(modification) FILTER (WHERE name LIKE '%.ready') AS oldest_ready_time
FROM pg_ls_archive_statusdir();

SELECT /* wiki_db_health_wal_directory */
       count(*) AS wal_directory_entries,
       coalesce(sum(size), 0) AS wal_directory_bytes,
       min(modification) AS oldest_entry_time,
       max(modification) AS newest_entry_time
FROM pg_ls_waldir();

SELECT /* wiki_db_health_replication */
       pid,
       application_name,
       client_addr,
       backend_xmin,
       state,
       sent_lsn,
       write_lsn,
       flush_lsn,
       replay_lsn,
       CASE WHEN NOT pg_is_in_recovery()
            THEN pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn)
       END AS source_to_sent_bytes,
       pg_wal_lsn_diff(sent_lsn, write_lsn) AS sent_to_write_bytes,
       pg_wal_lsn_diff(write_lsn, flush_lsn) AS write_to_flush_bytes,
       pg_wal_lsn_diff(flush_lsn, replay_lsn) AS flush_to_replay_bytes,
       write_lag,
       flush_lag,
       replay_lag,
       sync_state,
       reply_time
FROM pg_stat_replication
ORDER BY application_name, pid;

SELECT /* wiki_db_health_replication_slots */
       slot_name,
       plugin,
       slot_type,
       database,
       temporary,
       active,
       active_pid,
       xmin,
       catalog_xmin,
       restart_lsn,
       confirmed_flush_lsn,
       CASE WHEN NOT pg_is_in_recovery()
            THEN pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
       END AS current_to_restart_bytes,
       age(xmin) AS xmin_age,
       age(catalog_xmin) AS catalog_xmin_age
FROM pg_replication_slots
ORDER BY current_to_restart_bytes DESC NULLS LAST, slot_name;

SELECT /* wiki_db_health_wal_receiver */
       pid,
       status,
       receive_start_lsn,
       received_lsn,
       pg_last_wal_replay_lsn() AS replay_lsn,
       pg_wal_lsn_diff(received_lsn, pg_last_wal_replay_lsn())
         AS receive_replay_gap_bytes,
       last_msg_send_time,
       last_msg_receipt_time,
       now() - last_msg_receipt_time AS time_since_last_message,
       latest_end_lsn,
       latest_end_time,
       slot_name,
       sender_host,
       sender_port
FROM pg_stat_wal_receiver;

SELECT /* wiki_db_health_standby_replay */
       pg_is_in_recovery() AS in_recovery,
       pg_last_wal_receive_lsn() AS received_lsn,
       pg_last_wal_replay_lsn() AS replayed_lsn,
       pg_wal_lsn_diff(pg_last_wal_receive_lsn(),
                       pg_last_wal_replay_lsn()) AS receive_replay_bytes,
       pg_last_xact_replay_timestamp() AS last_replayed_transaction_time;

SELECT /* wiki_db_health_subscription */
       d.datname,
       st.subid,
       st.subname,
       sub.subenabled,
       sub.subslotname,
       st.pid,
       st.relid,
       CASE
         WHEN st.pid IS NULL THEN 'worker not running'
         WHEN st.relid IS NULL THEN 'main apply worker'
         ELSE 'table synchronization worker'
       END AS worker_state,
       st.received_lsn,
       st.last_msg_send_time,
       st.last_msg_receipt_time,
       now() - st.last_msg_receipt_time AS time_since_last_message,
       st.latest_end_lsn,
       st.latest_end_time
FROM pg_stat_subscription AS st
JOIN pg_subscription AS sub ON sub.oid = st.subid
LEFT JOIN pg_database AS d ON d.oid = sub.subdbid
ORDER BY d.datname, st.subname, st.relid NULLS FIRST;
```

Checklist:

- [ ] Treat `pg_stat_archiver` as command-exit-status telemetry, not proof that
  an archive object exists, is durable, or is restorable. PostgreSQL counts a
  command exit status of zero as success; a command that returns zero without
  copying the file creates a false success. Some fatal command-exit paths end
  the archiver before it reports a failed attempt to the collector.
  [config.sgml#archive-command-success](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L3110-L3133)
  [pgarch.c#archive-statistics](../../../../raw/postgres-12/src/backend/postmaster/pgarch.c#L466-L540)
  [pgarch.c#archive-command-exits](../../../../raw/postgres-12/src/backend/postmaster/pgarch.c#L623-L680)
- [ ] Interpret `last_archived_time` against WAL activity, the recovery-point
  objective, and `archive_timeout`. An old timestamp is expected on an idle
  system when no segment has completed and `archive_timeout` is zero. Use the
  privileged archive-status and WAL-directory aggregates plus host free-space
  monitoring to measure persistent `.ready` backlog and growth rather than
  inferring either from a timestamp alone.
  [config.sgml#archive_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L3138-L3168)
  [func.sgml#pg_ls_waldir](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L21770-L21876)
  [system_views.sql#monitor-file-functions](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L1322-L1345)
  [xlogarchive.c#archive-status-files](../../../../raw/postgres-12/src/backend/access/transam/xlogarchive.c#L500-L539)
- [ ] On a primary or publisher, investigate byte gaps from the local current
  WAL position through sent, written, flushed, and replayed positions. On a
  cascading standby, `source_to_sent_bytes` is deliberately null: the sender's
  safe ceiling combines replay and receiver-write positions only when their
  timelines match, which these SQL functions cannot reproduce exactly. The
  remaining stage gaps still apply. The lag intervals describe recent
  synchronous-commit stages, not predicted catch-up time. They can persist
  briefly after catch-up and then become null; a logical output plugin can omit
  them entirely.
  [monitoring.sgml#pg_stat_replication](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L1877-L2020)
  [walsender.c#GetStandbyFlushRecPtr](../../../../raw/postgres-12/src/backend/replication/walsender.c#L2927-L2960)
- [ ] Inspect every slot, not only inactive slots. PostgreSQL applies WAL and
  XID retention to every in-use slot without consulting `active_pid`; `active`
  says whether a process currently owns the slot, not whether the consumer is
  healthy. An unexpected null `restart_lsn` means the slot has never reserved
  WAL. PostgreSQL 12 has no slot-size bound. The query calculates the logical
  LSN distance from the current position to `restart_lsn` only on a
  non-recovery node; it is not the exact physical bytes retained in `pg_wal`,
  whose files are managed in whole segments under additional retention rules.
  Use the WAL-directory aggregate for physical directory bytes.
  [slot.c#ComputeRequiredXmin-and-LSN](../../../../raw/postgres-12/src/backend/replication/slot.c#L690-L775)
  [catalogs.sgml#pg_replication_slots-columns](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L9914-L9968)
  [high-availability.sgml#replication-slot-retention](../../../../raw/postgres-12/doc/src/sgml/high-availability.sgml#L914-L930)
  [xlogfuncs.c#pg_current_wal_lsn](../../../../raw/postgres-12/src/backend/access/transam/xlogfuncs.c#L340-L361)
- [ ] On a physical standby, an empty `pg_stat_wal_receiver` means no receiver
  is currently running. Inspect receiver status, stale message receipt times,
  and the receive-to-replay byte gap. Compare each standby separately because
  a primary reports only directly connected consumers.
  [monitoring.sgml#pg_stat_wal_receiver](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2024-L2132)
  [monitoring.sgml#direct-replication-connections](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L1978-L1983)
- [ ] On a logical subscriber, expect one main row per subscription. A null PID
  means its main worker is not running; `subenabled = false` explains an
  intentionally disabled worker, while `subenabled = true` with a null main
  PID needs investigation. Non-null `relid` rows are initial table-synchronization
  workers; investigate stale receipt times or table-copy rows that do not
  progress.
  [system_views.sql#pg_stat_subscription](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L803-L816)
  [monitoring.sgml#pg_stat_subscription](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2134-L2205)
  [catalogs.sgml#pg_subscription](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L6699-L6797)
- [ ] Investigate an old `backend_xmin` on a sender. It can expose a retention
  horizon reported by a standby, including one produced by
  `hot_standby_feedback`, and should be correlated with vacuum delay.
  [monitoring.sgml#pg_stat_replication-backend_xmin](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L1835-L1840)
  [config.sgml#hot_standby_feedback](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4139-L4161)
- [ ] On synchronous replication, correlate commit latency and lock contention
  with `sync_state` and lag. Transactions retain their locks until the required
  transfer is confirmed.
  [high-availability.sgml#synchronous-replication-impact](../../../../raw/postgres-12/doc/src/sgml/high-availability.sgml#L1238-L1244)

**8. Optional query and relation diagnostics**

```sql
SELECT /* wiki_db_health_pgss_capture */
       dbid,
       userid,
       queryid,
       calls,
       total_time,
       rows,
       shared_blks_hit,
       shared_blks_read,
       temp_blks_written,
       blk_read_time,
       blk_write_time,
       left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY dbid, userid, queryid;

SELECT /* wiki_db_health_pgstattuple */
       *
FROM pgstattuple_approx('schema.table_name'::regclass);

SELECT /* wiki_db_health_pgstatindex */
       *
FROM pgstatindex('schema.index_name'::regclass);
```

Checklist:

- [ ] Take two complete, un-`LIMIT`ed captures of the current
  `pg_stat_statements` view within the same reset/restart epoch. These are not
  atomic workload snapshots: the view iterates the shared hash while copying
  each entry's counters under that entry's spinlock, so active rows can be
  sampled at slightly different instants. Compare captures with full-outer-join
  semantics on `dbid`, `userid`, and `queryid`. Use nonnegative deltas for rows
  present in both. Treat a second-only row's counters as a lower bound for the
  interval; a first-only row or negative delta means eviction, reset, or entry
  recreation made that delta unreliable. Then rank reliable deltas separately
  by `total_time`, `shared_blks_read`, and `temp_blks_written`. Limiting or
  ranking cumulative rows before subtraction can hide a statement that
  dominated only the measurement interval. I/O timing fields require
  `track_io_timing`.
  [pgstatstatements.sgml#view](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L22-L41)
  [pgstatstatements.sgml#query-identity](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L274-L291)
  [pg_stat_statements.c#view-iteration](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1500-L1615)
  [pgstatstatements.sgml#entry-eviction](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L399-L410)
  [pgstatstatements.sgml#reset](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L333-L357)
  [config.sgml#track_io_timing](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6867-L6871)
- [ ] Verify `pg_stat_statements.track`,
  `pg_stat_statements.track_utility`, `pg_stat_statements.max`, and
  `pg_stat_statements.save` before interpreting sparse results. Entry eviction,
  reset, or restart can break a comparison interval, and other users' query
  identifiers and text are redacted without the required monitoring access.
  [pgstatstatements.sgml#access](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L228-L234)
  [pgstatstatements.sgml#settings](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L399-L474)
- [ ] Use `pgstattuple_approx` to shortlist heap relations with large dead-tuple
  or free-space fractions. It can still scan every page not marked all-visible;
  use exact `pgstattuple` only when the extra scan is justified.
  [pgstattuple.sgml#pgstattuple](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L39-L58)
  [pgstattuple.sgml#pgstattuple_approx](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L484-L538)
- [ ] Use `pgstatindex` for a selected B-tree index when index size, deleted or
  empty pages, average leaf density, and leaf fragmentation are needed. It
  visits every B-tree block and observes a concurrently changing relation; it
  is not a complete index-integrity check.
  [pgstattuple.sgml#pgstatindex](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L161-L186)
  [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L216-L315)

### Database log checklist

The table below assumes the server log destination is already accessible. The
"possible root causes" column contains operational inferences constrained by
the cited PostgreSQL mechanism; confirm them with current activity, counters,
and operating-system evidence.

| Log pattern or event | Repercussion | Possible root causes and next checks | Required data/configuration |
|---|---|---|---|
| `sorry, too many clients already` or `remaining connection slots are reserved...` | New clients are refused; ordinary users are refused before the reserved superuser slots. [proc.c#InitProcess](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L347-L363) [postinit.c#reserved-connections](../../../../raw/postgres-12/src/backend/utils/init/postinit.c#L818-L828) | Compare only `client backend` rows with `max_connections`; inspect pool limits, abandoned sessions, and bursts. Both connection-capacity GUCs require restart. [guc.c#max_connections-reserved](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2130-L2147) | The FATAL messages are built in. Enable `log_connections` and `log_disconnections` before new sessions start for attempt and duration context. [config.sgml#log_connections-disconnections](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6182-L6222) |
| `no pg_hba.conf entry`, password/authentication failure, or SSL negotiation failure | The client cannot establish the requested session. Repetition can represent a deployment error, stale credential, incompatible TLS setup, or unwanted access attempts. [auth.c#auth_failed](../../../../raw/postgres-12/src/backend/libpq/auth.c#L255-L323) [auth.c#no-pg_hba.conf-entry](../../../../raw/postgres-12/src/backend/libpq/auth.c#L494-L528) [be-secure-openssl.c#SSL-errors](../../../../raw/postgres-12/src/backend/libpq/be-secure-openssl.c#L444-L459) | Correlate client address, database, user, and TLS state with the expected application inventory; review HBA order and certificate/credential rotation. | Authentication errors are built in. `log_connections` adds connection-attempt context; ensure `log_line_prefix` carries useful session/client context. [config.sgml#log_connections](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6182-L6203) |
| `duration: ... statement: ...` or repeated slow-duration records | User latency, resource occupancy, and longer lock holding can rise while slow statements run. PostgreSQL logs a completed statement when its duration reaches `log_min_duration_statement`. [config.sgml#log_min_duration_statement](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5931-L5949) [postgres.c#check_log_duration](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2194-L2247) [postgres.c#exec_simple_query-duration-log](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1281-L1298) | Correlate with `pg_stat_statements`, lock waits, I/O timing, and temp-file messages. Possible mechanisms are expensive execution, lock waits, I/O, or sort/hash spills. | Set `log_min_duration_statement` as a superuser session/transaction setting; use a cluster default for full coverage. `0` logs all completed statements and `-1` disables it. [guc.c#log_min_duration_statement](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2703-L2712) |
| `temporary file: path ..., size ...` or `temporary file size exceeds temp_file_limit` | Temp I/O consumes storage and can fail a statement when the per-process limit is exceeded. [fd.c#ReportTemporaryFileUsage](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1272-L1286) [fd.c#temp_file_limit](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1942-L1956) | PostgreSQL creates temporary files for sorts, hashes, and temporary query results. Correlate the PID with the statement and compare `pg_stat_database.temp_bytes` and `pg_stat_statements.temp_blks_written`. [config.sgml#log_temp_files](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6555-L6574) | `log_temp_files` and `temp_file_limit` are superuser session/transaction settings. `log_temp_files = 0` logs every temp file; `-1` disables logging. [guc.c#log_temp_files](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3153-L3161) [guc.c#temp_file_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2271-L2278) |
| `process ... still waiting for ...`, `acquired ... after ...`, or `deadlock detected` | A statement waited for a lock; a detected hard deadlock aborts one transaction. The optional detailed wait LOG and the built-in deadlock ERROR are separate signals. [proc.c#lock-wait-log](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1377-L1497) [deadlock.c#DeadLockReport](../../../../raw/postgres-12/src/backend/storage/lmgr/deadlock.c#L1139-L1146) | Use `pg_blocking_pids()` and the holder/waiter PIDs. Check inconsistent lock order and prepared transactions retaining locks. [mvcc.sgml#Deadlocks](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L1358-L1423) | Enable `log_lock_waits`; it logs waits exceeding `deadlock_timeout`. Both are superuser session/transaction settings. [config.sgml#log_lock_waits](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6477-L6490) [guc.c#deadlock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2062-L2071) |
| `canceling statement due to lock timeout`, `canceling statement due to statement timeout`, or `terminating connection due to idle-in-transaction timeout` | PostgreSQL cancels the statement or terminates the idle transaction session. Intentional guardrails can produce these records, so escalate repeated, unexpected, or service-impacting events rather than every occurrence. [postgres.c#ProcessInterrupts-timeouts](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L3070-L3136) | Compare the configured limit with expected work and inspect blockers or transaction handling. | `statement_timeout`, `lock_timeout`, and `idle_in_transaction_session_timeout` are user session/transaction settings; zero disables each. [guc.c#client-timeouts](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2407) |
| `canceling statement due to conflict with recovery` or `terminating connection due to conflict with recovery` | Recovery cancels a standby query or session so WAL replay can continue. [postgres.c#recovery-conflict-interrupts](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2990-L3041) | Use `pg_stat_database_conflicts` to distinguish tablespace, lock, snapshot, buffer-pin, and recovery-deadlock causes; long standby queries and primary cleanup can conflict. [monitoring.sgml#pg_stat_database_conflicts](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2640-L2702) | Reporting is built in on a standby. `max_standby_archive_delay` and `max_standby_streaming_delay` are reload settings. [guc.c#standby-conflict-delays](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2075-L2093) |
| Successful `automatic vacuum of table ...`, `automatic aggressive vacuum of table ...`, or `automatic aggressive vacuum to prevent wraparound of table ...` completion summary | This is evidence that vacuum completed, not evidence of a failure. PostgreSQL 12 reports duration/system usage, index scans, pages and tuples, buffer hits/misses/dirties, and average read/write rates; this message has no WAL-usage field. [vacuumlazy.c#autovacuum-message-prefixes](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L401-L412) [vacuumlazy.c#autovacuum-summary](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L380-L441) | Compare duration, work, and remaining dead tuples with prior successful runs and current table size. Do not group this row with skipped actions or ERROR context. | Set `log_autovacuum_min_duration` to a nonnegative value and reload; zero logs all qualifying actions and `-1` disables them. [config.sgml#log_autovacuum_min_duration](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7010-L7029) [guc.c#log_autovacuum_min_duration](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2715-L2724) |
| Successful `automatic analyze of table ...` completion summary | This is evidence that analyze completed, not evidence of a failure. In this pin its completion message contains system-usage detail, but not vacuum's page, tuple, index-scan, or buffer fields. [analyze.c#autoanalyze-summary](../../../../raw/postgres-12/src/backend/commands/analyze.c#L667-L678) | Compare run frequency and system usage with prior runs, table change rate, and current planner-statistics freshness. | The same reloaded `log_autovacuum_min_duration` threshold controls qualifying autoanalyze completion messages. [config.sgml#log_autovacuum_min_duration](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7010-L7029) |
| `skipping vacuum ... lock not available`, `skipping analyze ... lock not available`, autovacuum ERROR plus `automatic vacuum of table ...` or `automatic analyze of table ...` context, `oldest xmin is far in the past`, or `oldest multixact is far in the past` | Maintenance can remain incomplete, and an old horizon can delay tuple cleanup or freezing. The `automatic vacuum...` or `automatic analyze...` context following an ERROR describes the failed worker; it is not a success summary. [vacuum.c#automatic-vacuum-and-analyze-skips](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L558-L649) [autovacuum.c#autovacuum-error-context](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2480-L2493) [vacuum.c#old-horizon-warnings](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L933-L988) | Check relation reloptions, blockers, old sessions, prepared transactions, slots, and row-lock-heavy activity. [autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2932-L2955) | Keep `autovacuum` and `track_counts` enabled. Configure `log_autovacuum_min_duration` for success/skip detail, while ERROR and WARNING paths remain built in. [config.sgml#log_autovacuum_min_duration](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7010-L7029) |
| `database ... must be vacuumed within ... transactions` or `database is not accepting commands to avoid wraparound data loss` | This is an emergency. Ignored warnings progress to refusal of new commands, while uncontrolled wraparound would make old data appear to be in the future. `GetNewTransactionId()` raises the ERROR at the stop limit and the WARNING at the warn limit, both naming the oldest database. [varsup.c#GetNewTransactionId-wraparound-limits](../../../../raw/postgres-12/src/backend/access/transam/varsup.c#L118-L158) [maintenance.sgml#wraparound-impact](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L391-L405) [maintenance.sgml#wraparound-warning-shutdown](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L608-L635) | Autovacuum has not advanced old XIDs. Check blocked/failed anti-wraparound vacuum, old transactions, prepared transactions, stale slots, and affected database/table ages. | The warnings are built in; no optional logging GUC produces them. Ensure the configured log destination captures WARNING and ERROR messages. |
| `must be vacuumed before ... more MultiXactIds are used`, `database is not accepting commands that generate new MultiXactIds to avoid wraparound data loss`, or `multixact "members" limit exceeded` | PostgreSQL can force maintenance, stop commands, or fail tuple-locking work before the configured MultiXact age alone appears exhausted. [multixact.c#MultiXact-emergency-limits](../../../../raw/postgres-12/src/backend/access/transam/multixact.c#L920-L1140) | Inspect `datminmxid`, separate relation MultiXact ages, long-lived row lockers, prepared transactions, and the effective member-space threshold. [multixact.c#MultiXactMemberFreezeThreshold](../../../../raw/postgres-12/src/backend/access/transam/multixact.c#L2785-L2844) | These warnings/errors are built in. `autovacuum_multixact_freeze_max_age` requires restart, but member-space pressure can lower the effective threshold. [guc.c#autovacuum_multixact_freeze_max_age](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2978-L2986) |
| `checkpoint starting`, `checkpoint complete`, or `checkpoints are occurring too frequently` | Frequent requested checkpoints increase write pressure; long write/sync phases can align with latency spikes. The frequency warning is specifically tied to WAL-caused checkpoints. [xlog.c#LogCheckpointStart](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L8356-L8372) [xlog.c#LogCheckpointEnd](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L8374-L8454) [checkpointer.c#checkpoint-warning](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L447-L462) | Compare `checkpoints_req`, checkpoint times, WAL generation, and `max_wal_size`. The built-in warning recommends increasing `max_wal_size`. | Enable `log_checkpoints` and reload for start/complete detail. `checkpoint_warning` and `max_wal_size` are reload settings. [config.sgml#log_checkpoints](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6165-L6178) [guc.c#checkpoint-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2555-L2587) |
| `archive_mode enabled, yet archive_command is not set`, archive-command failures, or `archiving write-ahead log file ... failed too many times` | Required WAL is not archived; WAL can accumulate in `pg_wal` and break the intended archive chain or recovery-point objective. [pgarch.c#archive-failures](../../../../raw/postgres-12/src/backend/postmaster/pgarch.c#L466-L540) [pgarch.c#archive-command-exits](../../../../raw/postgres-12/src/backend/postmaster/pgarch.c#L623-L680) | Check command exit status, destination capacity/permissions, and generation versus archive throughput. Verify the destination independently because a zero exit status is not proof of an archived object. | `archive_mode` requires restart. `archive_command` and `archive_timeout` reload; the command must return zero only after success. [config.sgml#archive-mode-command](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L3072-L3133) |
| WAL sender/receiver timeout, lost WAL stream, or requested WAL segment already removed | Replication disconnects or cannot continue from the requested point; if the required WAL is unavailable from both `pg_wal` and archive, the replica or subscriber may need a new starting point or rebuild. [walsender.c#walsender-timeout](../../../../raw/postgres-12/src/backend/replication/walsender.c#L2125-L2148) [walreceiver.c#receiver-errors](../../../../raw/postgres-12/src/backend/replication/walreceiver.c#L420-L529) [xlog.c#requested-WAL-removed](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L3863-L3869) | Check network continuity, sender/receiver timeouts, slot retention, archive availability, and whether the expected worker is running. | `wal_receiver_timeout` reloads; `wal_sender_timeout` is user session/transaction scope. Sender, receiver, and archive log messages are built in. [guc.c#replication-timeouts](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2119-L2127) [guc.c#wal_sender_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2657-L2665) |
| `PANIC`/`FATAL` from WAL write or fsync, backend crash, postmaster reinitialization, or unclean recovery | WAL I/O PANIC can terminate the server; a backend crash makes the postmaster terminate other server processes and reinitialize shared state, followed by crash recovery. [xlog.c#WAL-write-failures](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2494-L2510) [xlog.c#WAL-fsync-failures](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L10081-L10124) [postmaster.c#backend-crash-reinitialization](../../../../raw/postgres-12/src/backend/postmaster/postmaster.c#L3378-L3407) | Treat this as an availability and durability incident. Preserve the complete message chain; check storage, filesystem, kernel/OOM, extension/native crashes, and recovery completion before restoring traffic. [postmaster.c#reinitialize-after-crash](../../../../raw/postgres-12/src/backend/postmaster/postmaster.c#L3900-L3918) [xlog.c#unclean-recovery](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L6256-L6268) | PANIC/FATAL and restart messages are built in. Ensure the log destination and `log_min_messages` retain them; collect host/kernel evidence separately. |
| `could not extend file ... Check free disk space` or a short-write variant | The statement that needs relation growth fails. Continued lack of space can also prevent WAL, temp, or other database writes. [md.c#mdextend](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L398-L418) | Check filesystem free space, inode availability, quotas, storage errors, and whether WAL retention, temp files, or relation growth consumed the volume. PostgreSQL directly identifies free disk space as the first check. | The ERROR is built in; no optional logging GUC produces it. PostgreSQL does not expose general filesystem free-space health in the views used by this checklist, so add operating-system monitoring. |
| `out of shared memory` with `You might need to increase max_locks_per_transaction` | The lock request fails, so the current statement or transaction cannot continue normally. [lock.c#LockAcquireExtended](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L918-L930) | Check transactions touching many relations/partitions, concurrent lock demand, and prepared transactions. The lock table estimate is `max_locks_per_transaction * (MaxBackends + max_prepared_transactions)`, plus internal hash-table margin; it is not a hard per-transaction cap. [lock.c#NLOCKENTS](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L53-L57) [lock.c#lock-hash-margin](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L3438-L3457) [config.sgml#max_locks_per_transaction](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L8615-L8642) | `max_locks_per_transaction` and `max_prepared_transactions` require restart. Standbys need compatible capacity for replay. [guc.c#max_prepared_transactions](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2341-L2352) [guc.c#max_locks_per_transaction](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2460-L2472) [config.sgml#standby-lock-capacity](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L8639-L8642) |
| `page verification failed, calculated checksum ... but expected ...`, base-backup checksum failure, or a nonzero checksum counter | PostgreSQL detected a page checksum mismatch on a page it read, which is evidence of possible data-page corruption. A zero counter does not verify unread pages. [bufpage.c#PageIsVerified](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L82-L161) [basebackup.c#backup-checksum-failures](../../../../raw/postgres-12/src/backend/replication/basebackup.c#L1543-L1622) | Preserve evidence, identify the relation/block, investigate storage and I/O, and validate independent backups or replicas before repair. | Checksums must be enabled for counters. Verify that `ignore_checksum_failure` and `zero_damaged_pages` are false; both are superuser session/transaction settings that alter damaged-page handling. [guc.c#damaged-page-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1135-L1161) |
| `using stale statistics instead of current ones because stats collector is not responding` | Collected database/table counters can be stale or unavailable, so health conclusions based on them are unreliable. [pgstat.c#collector-not-responding](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L5741-L5764) | Check the collector process, log chain, local socket/filesystem state, and whether a crash/restart is in progress. Re-capture after the collector resumes and after the asynchronous update interval. | The LOG message is built in. Configure `log_min_messages` to retain LOG when this evidence is required; no optional statistics view can repair missing collector updates. |
| Connection/disconnection churn or unexpected replication commands | Short sessions can add connection overhead; unexpected replication commands should match the expected replication clients. `log_disconnections` includes session duration. [config.sgml#log-connections-disconnections](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6182-L6222) [config.sgml#log_replication_commands](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6539-L6551) | Check pool behavior, authentication retries, restart loops, and replication inventory. Duplicate connection messages can be normal during password handling. | Reload file changes to `log_connections` and `log_disconnections`; only subsequently started sessions receive the new values. Enable `log_replication_commands` as a superuser session/transaction setting or cluster default. [guc.c#PGC_SU_BACKEND-reload](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L6811-L6840) |

### Issue interpretation and response

The root-cause directions below are operational inferences from the mechanisms
and fields cited in each row.

| Priority | Finding | Repercussion | Root-cause direction |
|---|---|---|---|
| Immediate | XID/MultiXact stop warning, WAL write/fsync PANIC, checksum mismatch, disk-extension failure, measured uncontrolled `pg_wal` growth, or required WAL already removed | Commands, writes, or replication can fail; WAL I/O can terminate the server; checksum findings indicate possible page corruption. [varsup.c#GetNewTransactionId-wraparound-limits](../../../../raw/postgres-12/src/backend/access/transam/varsup.c#L118-L158) [maintenance.sgml#wraparound-warning-shutdown](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L608-L635) [multixact.c#MultiXact-emergency-limits](../../../../raw/postgres-12/src/backend/access/transam/multixact.c#L920-L1140) [xlog.c#WAL-fsync-failures](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L10081-L10124) [bufpage.c#PageIsVerified](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L145-L161) | Preserve evidence and administrative access, reduce nonessential load, identify old transactions/prepared transactions/slots, verify storage, and determine whether required WAL/archive/backup evidence still exists. |
| High | Connection exhaustion, sustained lock waits, deadlocks, repeated unexpected timeout cancellations, stopped expected replication workers, or synchronous-replication delay | Clients are refused, work waits or aborts, replication falls behind, and synchronous commits can retain locks longer. [proc.c#InitProcess](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L347-L363) [deadlock.c#DeadLockReport](../../../../raw/postgres-12/src/backend/storage/lmgr/deadlock.c#L1139-L1146) [high-availability.sgml#synchronous-replication-impact](../../../../raw/postgres-12/doc/src/sgml/high-availability.sgml#L1238-L1244) | Identify the exact client backends, blockers, configured timeout, worker/topology expectation, and replication stage. A single intentional timeout is a guardrail event, not automatically a health incident. |
| Sustained degradation | Growing dead rows, stale analyze timestamps, repeated temp files, slow statements, frequent requested checkpoints, or backend writes/fsyncs | Table/index space and query cost can grow, plans can use stale statistics, temp and checkpoint I/O can compete with workload I/O, and latency can rise. [monitoring.sgml#pg_stat_all_tables](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2773-L2831) [monitoring.sgml#pg_stat_bgwriter](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2412-L2475) | Check autovacuum thresholds and blockers, the top `pg_stat_statements` entries, temp-file-producing sorts/hashes, and WAL/checkpoint sizing. [autovacuum.c#threshold-decision](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L3060-L3080) [config.sgml#log_temp_files](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6562-L6573) [checkpointer.c#checkpoint-warning](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L447-L462) |
| Observability gap | Redacted activity/query fields, truncated query text, disabled I/O timing, missing expected extension/topology view, collector warning, or `pending_restart = true` | The database may be unhealthy while evidence is unavailable or incomplete. Empty event-specific logs and zero I/O time are not gaps by themselves when no qualifying event or timed I/O occurred. [config.sgml#track_activity_query_size](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6820-L6834) [config.sgml#track_io_timing](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6854-L6871) [catalogs.sgml#pg_settings_pending_restart](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10494-L10498) | Verify access, effective GUCs, topology expectations, extension loading, and reset epoch first. Apply the required restart/reload/session setting, then begin a new measurement interval before drawing conclusions. |

## Context Reviewed

- Monitoring-role access checks for activity, settings, progress, WAL sender,
  WAL receiver, and `pg_stat_statements` fields.
- PostgreSQL 12 logging destinations, severity filters, collector and snapshot
  behavior, logging/statistics/autovacuum/replication GUCs, and their
  `GucContext` definitions.
- Built-in `pg_stat_activity`, `pg_locks`, `pg_stat_database`,
  `pg_stat_database_conflicts`, `pg_stat_user_tables`,
  `pg_stat_progress_vacuum`, `pg_stat_bgwriter`, `pg_stat_archiver`,
  `pg_stat_replication`, `pg_stat_wal_receiver`, `pg_stat_subscription`, and
  `pg_replication_slots` surfaces, including their implementation callers and
  redaction boundaries.
- Connection exhaustion, prepared locks, lock waits, deadlocks, timeouts,
  authentication, temp files, checkpoints, archiving, replication disconnects,
  backend crashes, WAL I/O failures, disk extension, lock-table exhaustion,
  statistics-collector failure, and page-checksum message paths.
- Autovacuum table/TOAST selection, partitioned-parent analysis, threshold
  decisions, XID and MultiXact anti-wraparound behavior, effective member-space
  limits, and warning/shutdown paths.
- PostgreSQL 12 `pg_stat_statements` and `pgstattuple` contrib documentation and
  implementation, SQL installation, access, scan, and regression-test
  boundaries.
- Generated-catalog inputs, installed system-view definitions, rules output,
  statistics/prepared-transaction regression tests, and recovery/subscription
  TAP tests relevant to the checklist.

The view shapes are handwritten in `system_views.sql` and installed by
`initdb`. Built-in signatures such as `age()` and `mxid_age()` originate in
`pg_proc.dat`, which the catalog build consumes to produce bootstrap and
generated catalog artifacts. These diagnostic queries do not themselves
change a generated header. Upstream regression tests cover view definitions,
statistics refresh, and prepared-lock survival. Recovery, archiving, logical
decoding, synchronous replication, and subscription tests cover their
individual facilities; there is no upstream test for this compound checklist
as a whole.
[pg_proc.dat#age-and-mxid_age](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L2265-L2272)
[catalog/Makefile#catalog-generation](../../../../raw/postgres-12/src/backend/catalog/Makefile#L51-L109)
[initdb.c#setup_sysviews](../../../../raw/postgres-12/src/bin/initdb/initdb.c#L1651-L1671)
[rules.out#statistics-views](../../../../raw/postgres-12/src/test/regress/expected/rules.out#L1760-L1805)
[stats.sql#wait_for_stats](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L27-L78)
[prepared_xacts.sql#view-and-lock-tests](../../../../raw/postgres-12/src/test/regress/sql/prepared_xacts.sql#L110-L153)
[001_stream_rep.pl#streaming-test](../../../../raw/postgres-12/src/test/recovery/t/001_stream_rep.pl#L1-L20)
[002_archiving.pl#archiving-test](../../../../raw/postgres-12/src/test/recovery/t/002_archiving.pl#L1-L20)
[006_logical_decoding.pl#logical-decoding-test](../../../../raw/postgres-12/src/test/recovery/t/006_logical_decoding.pl#L1-L27)
[007_sync_rep.pl#synchronous-replication-test](../../../../raw/postgres-12/src/test/recovery/t/007_sync_rep.pl#L1-L20)
[004_sync.pl#subscription-sync-test](../../../../raw/postgres-12/src/test/subscription/t/004_sync.pl#L1-L20)

## Evidence Map

| Claim area | Primary evidence |
|---|---|
| Monitoring access and setting visibility | [user-manag.sgml#predefined-monitoring-roles](../../../../raw/postgres-12/doc/src/sgml/user-manag.sgml#L519-L538), [pgstatfuncs.c#activity-and-progress-access](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L490-L655), [guc.c#pg_settings-access](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L8998-L9008) |
| Logging destinations, filters, and apply scopes | [config.sgml#log_destination](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5439-L5486), [config.sgml#server-log-levels](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5877-L5927), [guc.c#GucContext_Names](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L594-L603) |
| Current, cumulative, and snapshot statistics | [monitoring.sgml#statistics-snapshot](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L229-L268), [system_views.sql#activity-through-database](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L732-L887), [system_views.sql#archiver-bgwriter-vacuum](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L924-L965) |
| Connections, prepared locks, deadlocks, and timeouts | [postinit.c#InitializeMaxBackends](../../../../raw/postgres-12/src/backend/utils/init/postinit.c#L527-L539), [func.sgml#pg_blocking_pids](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L17584-L17604), [proc.c#lock-wait-log](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1377-L1497), [postgres.c#ProcessInterrupts](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L2990-L3136) |
| Vacuum, analyze, TOAST, partitions, and wraparound | [autovacuum.c#do_autovacuum-table-and-TOAST-passes](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2035-L2191), [autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2920-L3096), [analyze.c#analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L231-L268), [varsup.c#GetNewTransactionId-wraparound-limits](../../../../raw/postgres-12/src/backend/access/transam/varsup.c#L118-L158), [multixact.c#MultiXactMemberFreezeThreshold](../../../../raw/postgres-12/src/backend/access/transam/multixact.c#L2785-L2844) |
| Checkpoints and background writes | [bufmgr.c#BgBufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2260-L2300), [checkpointer.c#ForwardSyncRequest](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1086-L1159), [checkpointer.c#checkpoint-warning](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L447-L462), [xlog.c#LogCheckpointEnd](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L8374-L8454) |
| WAL archiving, replication, subscriptions, and slots | [pgarch.c#archive-command-result](../../../../raw/postgres-12/src/backend/postmaster/pgarch.c#L466-L680), [system_views.sql#replication-views](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L758-L816), [slot.c#retention-horizons](../../../../raw/postgres-12/src/backend/replication/slot.c#L690-L775), [monitoring.sgml#replication-lag](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L1978-L2020) |
| Query and relation extensions | [pg_stat_statements.c#module-GUCs-and-access](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L365-L410), [pgstatstatements.sgml#view](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L22-L41), [pgstattuple.sgml#pgstattuple_approx](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L484-L538), [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L216-L315) |
| Crashes, checksums, and storage errors | [postmaster.c#backend-crash-reinitialization](../../../../raw/postgres-12/src/backend/postmaster/postmaster.c#L3378-L3407), [xlog.c#WAL-fsync-failures](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L10081-L10124), [bufpage.c#PageIsVerified](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L82-L161), [md.c#mdextend](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L398-L418) |
| Tests and build/generated boundary | [stats.sql#wait_for_stats](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L27-L78), [prepared_xacts.sql#view-and-lock-tests](../../../../raw/postgres-12/src/test/regress/sql/prepared_xacts.sql#L110-L153), [catalog/Makefile#catalog-generation](../../../../raw/postgres-12/src/backend/catalog/Makefile#L51-L109), [initdb.c#setup_sysviews](../../../../raw/postgres-12/src/bin/initdb/initdb.c#L1651-L1671) |

## Open Questions

- Numeric alert thresholds for sessions, transaction age, dead rows, temp
  bytes, checkpoint rates, and replication lag depend on workload capacity and
  service objectives. The pinned source defines the counters and safety limits,
  but not a universal healthy production threshold.
- Which standbys, cascading downstreams, subscriptions, slots, archive
  destinations, synchronous standbys, and recovery-point/recovery-time
  objectives are expected? An empty component view is healthy when that
  component is absent and an outage when it is required.
- What measurement window and reset policy applies to cumulative counters and
  `pg_stat_statements`? PostgreSQL 12 does not attach a reset timestamp to each
  table or statement row, so the capture system must preserve its own epoch.
- PostgreSQL's internal views do not replace host monitoring for free space,
  inodes, filesystem or device errors, CPU, memory pressure, and network health.
  The source explicitly sends relation-extension failures to the log with a
  free-space hint.
  [md.c#mdextend](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L404-L418)
- What external evidence proves archive-object existence and durability,
  backup freshness, and successful restore? `pg_stat_archiver` reports command
  exit status and cannot prove those outcomes.
  [config.sgml#archive-command-success](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L3110-L3133)
- The predefined-role documentation describes `pg_read_all_stats` as reading
  all `pg_stat_*` views, but this pinned implementation's progress function
  tests only `has_privs_of_role(GetUserId(), <the reporting role>)` and never
  checks `pg_read_all_stats`, unlike `pg_stat_get_activity`, which accepts
  either. This page follows the implementation and requires superuser for
  complete cross-role progress; the measured `pg_monitor` result on this pin
  was `pid` and `datname` only.
  [user-manag.sgml#pg_read_all_stats](../../../../raw/postgres-12/doc/src/sgml/user-manag.sgml#L524-L538)
  [pgstatfuncs.c#progress-access](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L490-L531)
  [pgstatfuncs.c#activity-access](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L625-L655)
- The PostgreSQL 12 documentation describes lock-table sizing with
  `max_connections + max_prepared_transactions`, while `NLOCKENTS()` uses
  `MaxBackends + max_prepared_xacts`. This page follows the implementation.
  [config.sgml#max_locks_per_transaction](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L8615-L8636)
  [lock.c#NLOCKENTS](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L53-L57)
- The documentation describes `pg_stat_database.checksum_failures` without a
  base-backup exception, but this pin reports a file's base-backup failures to
  the statistics collector only when that file has more than one mismatch. A
  file with exactly one mismatch still makes the base backup fail, but that
  path does not increment the counter. Treat the log and backup result as
  authoritative for that case; this page does not infer that a zero counter
  rules it out.
  [monitoring.sgml#checksum_failures](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2599-L2611)
  [basebackup.c#per-file-checksum-report](../../../../raw/postgres-12/src/backend/replication/basebackup.c#L1543-L1619)
  [basebackup.c#backup-checksum-failure](../../../../raw/postgres-12/src/backend/replication/basebackup.c#L621-L631)

## Source References

- [guc.c#GucContext_Names](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L594-L603)
- [config.sgml#Logging](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5439-L5534)
- [config.sgml#WhatToLog](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5931-L6574)
- [config.sgml#StatisticsAndAutovacuum](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6818-L7033)
- [monitoring.sgml#StatisticsViews](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L284-L425)
- [system_views.sql#StatisticsViews](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L732-L887)
- [pgstatfuncs.c#activity-and-progress-access](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L490-L655)
- [func.sgml#pg_blocking_pids](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L17584-L17604)
- [maintenance.sgml#TransactionIdWraparound](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L391-L705)
- [autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2925-L3080)
- [vacuum.c#vacuum_set_xid_limits](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L896-L996)
- [multixact.c#MultiXact-limits](../../../../raw/postgres-12/src/backend/access/transam/multixact.c#L920-L1140)
- [pgarch.c#archive-command-result](../../../../raw/postgres-12/src/backend/postmaster/pgarch.c#L430-L680)
- [slot.c#retention-horizons](../../../../raw/postgres-12/src/backend/replication/slot.c#L690-L775)
- [pgstatstatements.sgml#pg_stat_statements](../../../../raw/postgres-12/doc/src/sgml/pgstatstatements.sgml#L10-L41)
- [pgstattuple.sgml#pgstattuple](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L10-L23)
- [bufpage.c#PageIsVerified](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L82-L161)
- [postmaster.c#backend-crash-reinitialization](../../../../raw/postgres-12/src/backend/postmaster/postmaster.c#L3378-L3407)
- [stats.sql#wait_for_stats](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L17-L77)

## Navigation

- [PostgreSQL 12 index](../../index.md)
- [Wiki index](../../../index.md)
- [Version manifest](../../../versions.md)
