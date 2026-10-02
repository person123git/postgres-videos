# PostgreSQL 18.6

## Source Pin

- Branch: `REL_18_STABLE`
- Commit: `baa7b142aace6821ce085906f314a75bcc4d95c8`
- Status: `primary`
- Source path: `raw/postgres-18/`
- Added: 2026-04-30
- Repinned: 2026-08-17

## Coverage

Behavioral claims cite the matching pinned checkout under `raw/postgres-18/`. The 2026-08-17 repin from the 18.3 line `6cb307251c5` to 18.6 `baa7b142aac` reviewed all 294 commits in the range, which crosses the 18.4 and 18.6 releases; 18.5 was stamped (`17fae4fbdd6`) but never released, as the checkout's own release notes record. Claim-changing commits: `0b12f56bfac` (CVE-2026-14666) registers `PlanCacheRoleCallback` so role, role-attribute and database-ownership changes invalidate role-dependent saved plans; `2a29b607dbb` (CVE-2026-6471) adds the `output_plugin_libraries` GUC that every logical-replication publisher must list `pgoutput` in; `cb35d730689` (CVE-2026-6638) quotes the publisher-side origin-check identifiers and so answers the bidirectional page's open question; `8a31ffc2d4c` (CVE-2026-14676) rebuilds `pg_stat_statements` query normalization on an expansible `StringInfo` without adding a length cap; `2780538433f` (CVE-2026-6470) requires `USAGE` on types used by index, policy and partition-key expressions; `e4527519b77` propagates `INDEX_CREATE_DEFERRABLE` to the `REINDEX CONCURRENTLY` copy; `fe464e9e686`/`5cc59834b86` move the custom-statistics drop entry point to `pgstat_drop_entry_ext()`; and `585181e0774`/`7c25cdb1ebf` add the extension-visible `read_stream_clear_strategy()`. No GUC present in both v12 and 18 changed its default in the range, and measurements taken on the previous pin are labelled as such rather than re-run.

- [PostgreSQL 18 Codebase Navigation Guide (unverified)](codebase-navigation-guide.md) - Mandatory root-level question-style map for navigating the pinned v18 source tree: layout, SQL statement flow, utility dispatch, generated/catalog artifacts, key structs, contrib boundaries, tests, and docs.
- [Wiki Glossary (unverified)](../glossary.md) - The one glossary shared by every version. PostgreSQL jargon, acronyms and source-code terms, each entry citing the pinned checkout it was checked on (PostgreSQL 12, 14, 17, 18 and 19; 319 terms).

## Questions

### Indexing

- [How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 18 (unverified)](questions/indexing/create-index-concurrently.md) - Comprehensive walkthrough of the v18 `CREATE INDEX CONCURRENTLY` path: utility dispatch and restrictions, four internal transactions, two heap scans, three waits, table/session `ShareUpdateExclusiveLock`, `indislive`/`indisready`/`indisvalid` progression, failure outcomes, tests, and changes from PostgreSQL 17 (`pg_index` TOAST snapshot handling, parallel GIN build, virtual-generated-column rejection, and temporal `WITHOUT OVERLAPS` shared plumbing).
- [Computing and Storing avg_leaf_density During (Auto)VACUUM of a B-Tree Index (unverified)](questions/indexing/avg-leaf-density-during-vacuum.md) - Reviewed design and evidence-backed cons for computing `pgstatindex`-style `avg_leaf_density` inside B-tree VACUUM, with metapage/statistics storage options and explicit caveats for skipped scans and page deletion.

### Storage and Vacuum

- [Extension Hooks for VACUUM and Autovacuum in PostgreSQL 18 (unverified)](questions/storage-and-vacuum/extension-hooks-vacuum-autovacuum.md) - Enumerates every extension point on the VACUUM/ANALYZE and autovacuum code paths in v18: in-process hook variables, table/index AM and FDW callbacks, and adjacent extension surfaces, with the manual-vs-autovacuum coverage of each.
- [Usage of NUM_BUFFER_PARTITIONS in PostgreSQL 18 (unverified)](questions/storage-and-vacuum/num-buffer-partitions.md) - How PostgreSQL 18 uses the fixed `NUM_BUFFER_PARTITIONS` count for shared buffer mapping hash partitions, `BufferMapping` LWLocks, read/allocation, extension, and invalidation paths, plus the macro's source commit history (16->128).

### Replication and WAL

- [How Bi-Directional Logical Replication Works in PostgreSQL 18, and New Logical Replication Features Since PostgreSQL 17 (unverified)](questions/replication-and-wal/bidirectional-logical-replication.md) - How two v18 nodes replicate to each other without loops via mutual `origin = none` subscriptions (apply-worker origin tagging into WAL, `pgoutput`/decode-time origin filtering, the `copy_data` initial-sync WARNING, setup pattern, limitations), plus the new v18 conflict detection (`update_origin_differs`/`delete_origin_differs` and friends, logged and counted in `pg_stat_subscription_stats`); with a verified section on all logical replication features new since v17: conflict logging/stats, generated-column replication (`publish_generated_columns`), `streaming = parallel` default, alterable `two_phase`, the `max_active_replication_origins` and `idle_replication_slot_timeout` GUCs, `pg_createsubscriber` `--all`/`--clean`/`--enable-two-phase`, `pg_recvlogical` improvements, and contrib `pg_logicalinspect`.

### Observability

- [How Custom Cumulative Statistics Work in PostgreSQL 18 (unverified)](questions/observability/custom-cumulative-statistics.md) - How extension-defined `PgStat_KindInfo` entries register through `shared_preload_libraries`, store variable or fixed custom stats, flush and snapshot counters, and persist across clean shutdowns.
- [EXPLAIN ANALYZE BUFFERS Output in PostgreSQL 18 (unverified)](questions/observability/explain-analyze-buffers-output.md) - Detailed explanation of shared, local, temp, planning, serialization, parallel-worker, and I/O timing fields in `EXPLAIN (ANALYZE, BUFFERS)` output.
- [How pg_stat_statements Works and Which Settings Affect It in PostgreSQL 18 (unverified)](questions/observability/pg-stat-statements.md) - How `pg_stat_statements` hooks parse analysis, planning, execution, utility commands, shared memory, query-text files, reset/save paths, permissions, and the direct plus adjacent settings that affect its output.
- [Limiting Query Text Size in pg_stat_statements in PostgreSQL 18 (unverified)](questions/observability/pg-stat-statements-query-text-size.md) - Why v18 has no GUC to cap individual query-text length, that `track_activity_query_size` does not apply, full-length external-file storage, the wholesale-discard garbage collection edge path, and the `pg_stat_statements.max`/`showtext`/`left()` workarounds.
- [How track_activity_query_size Is Used in PostgreSQL 18 (unverified)](questions/observability/track-activity-query-size.md) - How PostgreSQL 18 uses the postmaster-context `track_activity_query_size` GUC to reserve per-backend activity text storage, truncate `pg_stat_activity.query`, clip multibyte text, report activity in deadlock/crash paths, and leave `pg_stat_statements.query` storage separate.

### Server Administration

- [Changes to Declarative Partition Bound Syntax and pg_class.relpartbound Since Partitioning Was Introduced, as of PostgreSQL 18 (unverified)](questions/server-administration/declarative-partition-bound-syntax-and-relpartbound.md) - Bound syntax changed three times and has been frozen since v12 (`MINVALUE`/`MAXVALUE` for `UNBOUNDED` pre-10.0, `DEFAULT` and hash `WITH (MODULUS, REMAINDER)` in v11, general `partition_bound_expr` in v12); the `pg_class.relpartbound` column definition never changed, but the stored `pg_node_tree` gained three fields in v11 and lost real parse locations in v17; the deparsed `pg_get_expr` text never changed; exposure surfaces only gained additions. Includes the v18-only grammar commit (error cursors on two hash-bound errors), the reverted MERGE/SPLIT PARTITION, the write-once/clear-once `relpartbound` lifecycle, the three engine read paths, and measurements taken on the previous 18.3-line pin `6cb307251c5` of the stored node text, DDL-time bound evaluation, quoted-sentinel asymmetry, and the no-TOAST size cliff.
- [GUC Default-Value Changes Since PostgreSQL 12 (unverified)](questions/server-administration/guc-default-changes-since-v12.md) - Summarizes settings present in both PostgreSQL 12 and 18 whose built-in defaults changed: eight semantic default changes plus the v18 `log_connections` type/default-spelling change that keeps disabled-by-default behavior.
- [Row-Level Security (RLS) in PostgreSQL 18: Implementation, Performance, Settings, and Fixes Since PostgreSQL 14 (unverified)](questions/server-administration/row-level-security-rls.md) - Rewrite/relcache/planner/executor walkthrough of v18 RLS: command-layered policies (non-target tables get SELECT policies; SELECT-policy write checks whenever SELECT rights are needed), WCO order and error-raising paths, owner/FORCE/no-force bypass, statistics limited to leakproof operators, policy sublinks that never become joins, plan-time pruning only for constant policy values, locks, partitions/views/COPY/replication, settings including `LEAKPROOF`, and 24 scoped changes not in PostgreSQL 14.0. The plan-cache answer covers 18.6's `PlanCacheRoleCallback` (CVE-2026-14666) and its cost: any role-catalog change in the cluster, or a `VACUUM` that advances the current database's `datfrozenxid`, replans saved RLS statements. A published bash+SQL script measures on 18.6 the five same-role cases, those replans, InitPlan helper call counts (101 bare vs 1 wrapped) and skewed-column estimates.
