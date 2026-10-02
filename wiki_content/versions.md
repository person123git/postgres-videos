# PostgreSQL Versions

This page indexes the PostgreSQL versions covered by the wiki.

Shared vocabulary for every version lives in the [Wiki Glossary (unverified)](glossary.md). Each entry names the pinned checkout it was checked on.

## Supported Versions

| Version | Status | Wiki Home | Branch | Pinned Commit | Coverage |
|---|---|---|---|---|---|
| 19 | active | [v19/index](v19/index.md) | `REL_19_STABLE` | `dae3463fa969931458f1488f9b7af11e3741cd54` | Behavioral claims cite the matching pinned checkout under `raw/postgres-19/`; filed coverage includes a comprehensive walkthrough of the new `pg_plan_advice` contrib module (core `pgs_mask` strategy mask and planner hooks, per-index disabling, advice language including underscore-separated occurrence numbers, generation, clear-only enforcement in which `PGS_CONSIDER_PARTITIONWISE` is never cleared, feedback/EXPLAIN, GUCs, the plan-cache boundary that keeps `EXPLAIN (PLAN_ADVICE) EXECUTE` empty, and three test layers) and its scoped source history (21 core planner foundation/enabling/fix commits, 34 direct module commits, and test/doc/build support commits), all re-verified claim by claim on 2026-09-01, plus a comprehensive walkthrough of the new in-core `REPACK` / `REPACK (CONCURRENTLY)` command (blocking new-heap rewrite/swap, lock-free multi-table candidate discovery followed by locked per-table open/recheck, partitioned-target discovery hardening, concurrent online rewrite via logical decoding with a decoding `bgworker`, the `pgrepack` output plugin, a temporary replication slot, race-safe on-demand decoding activation, change spill/replay, lock upgrade and swap, the `max_repack_replication_slots` GUC, `pg_stat_progress_repack`, generic `MAINTAIN` / `pg_maintain` documentation, and tests) with 79 feature-scope source-history commits, its I/O section deepened on 2026-09-02 to answer whether `REPACK` can be throttled (it cannot: three options, none about I/O; no `vacuum_delay_point()` on the rewrite path; the blocking rewrite bypasses shared buffers through `bulk_write.c`, `BAS_BULKWRITE` covering only the CONCURRENTLY copy; both modes dirty the old heap and rewrite TOAST; a 13-row settings table with apply scopes; and the reference page's stale `enable_sort` advice filed as an Open Question); and a comprehensive, commit-backed walkthrough of three v19 autovacuum/VACUUM features (parallel autovacuum via the `autovacuum_max_parallel_workers` GUC and `autovacuum_parallel_workers` reloption, autovacuum table scoring via `AutoVacuumScores`/the five `*_score_weight` GUCs/`pg_stat_autovacuum_scores` plus the post-beta1 MXID-score division-by-zero fix `1f2297b5487`, and read-only query scans setting pages all-visible in the visibility map through on-access pruning, including the post-beta1 `e9eaeb04248` fix that records free space when a page becomes all-visible so its FSM entry does not go stale, plus the `b01c31eef9c` VM-clear WAL/incremental-backup correction, `9171f77db23` TAP test, and `3180ce3d7a8` wrong-buffer error-path hardening); all three v19 question histories are pinned to the `REL_19_STABLE` commit `dae3463f`, stamped `19beta4` (`REL_19_BETA4-17-gdae3463fa96`, no RC or GA tag yet); the 2026-09-24 repin reviewed all 159 commits after `135b867a` (crossing the `REL_19_BETA4` stamp) and added 21 REPACK feature-scope commits (invalid-index refusal, `CONCURRENTLY` restrictions to heap AM, non-catalog, non-matview tables with an intact replica-identity index, worker lifecycle/timeout/`CONNECT` fixes, progress-reporting fixes), six `pg_plan_advice` module commits and one core GEQO commit, and four autovacuum/VM changes (`13243ae44cf` safety-valve correction and first regression test, `b3609cd2db8`, `41a8548ad41`, `1bda0b23bce` freeze-score scaling), while the online-checksum, SQL/PGQ, FOR PORTION OF, `pg_get_*_ddl` and `CREATE SCHEMA` reverts reshaped the guide and glossary; `verified_by_agent` is `not yet` on every v19 page; the 2026-09-01 repin reviewed all 104 commits after `67342a148` and added three REPACK feature-scope commits (`9bb8e16bd53` `already_locked` ACL split, `f23de46e15b` `ONLY`/`*` rejection, `dc8628e55d4` rewrite/progress/lock documentation), a 28th `pg_plan_advice` module commit (`400c810ddbd`, empty `FOREIGN_JOIN(())`), and two autovacuum fixes (`4af0528a0e4` rebalanced-cost-limit propagation to parallel workers, `7ddb9c41a13` TOAST reloption fallback in `pg_stat_autovacuum_scores`); the earlier 2026-08-17 repin reviewed the 152 commits after `99e47536` and added five REPACK feature-scope commits, a 27th `pg_plan_advice` module commit, and the role-change plan-cache invalidation `567286b762b` (CVE-2026-14666). Filed on 2026-09-24: a commit-by-commit history of online data checksum enabling and disabling, 85 commits from the 2018 attempt `1fde38beaa0` to the 2026-09-16 `REL_19_STABLE` revert `c05d5ce1236` and its two cleanups. The feature is absent at the pin. |
| 18 | primary | [v18/index](v18/index.md) | `REL_18_STABLE` | `baa7b142aace6821ce085906f314a75bcc4d95c8` | Behavioral claims cite the matching pinned checkout under `raw/postgres-18/`; filed coverage includes B-tree VACUUM density design, custom cumulative statistics, extension hooks for VACUUM/autovacuum, `EXPLAIN (ANALYZE, BUFFERS)` output, `pg_stat_statements` mechanics and configuration, `track_activity_query_size` activity text storage, `NUM_BUFFER_PARTITIONS` buffer mapping usage, GUC default-value changes since v12 through v18 (`effective_io_concurrency` and `log_connections` included), a walkthrough of bi-directional logical replication (mutual `origin = none` subscriptions, apply-worker origin tagging, `pgoutput`/decode-time origin filtering, the `copy_data` initial-sync WARNING, setup pattern, limitations, and the new v18 origin-differs conflict logging) with a source-verified section on all logical replication features new since v17 (conflict detection/logging/statistics, generated-column replication, `streaming = parallel` default, alterable `two_phase`, `max_active_replication_origins`, `idle_replication_slot_timeout`, `pg_createsubscriber` and `pg_recvlogical` options, contrib `pg_logicalinspect`), and a fully reviewed Row-Level Security walkthrough covering rewrite-time command-layered security quals and WCOs, relcache/generated-catalog plumbing, policy recursion and permissions, WCO execution order, RI and whole-table boundaries, planner selectivity/cost/index/pruning/parallel effects, DDL locks, partitions/views/COPY/logical replication, direct and adjacent settings, and five PostgreSQL 14-derived performance follow-ups covering plan caching, MultiXact, aggregation, whether RLS filters must be repeated in the query, and scalar-InitPlan versus index-runtime-key behavior; exact-pin tests reproduce stale prepared results under the same effective-role OID after membership-edge `inherit_option`, `BYPASSRLS`, superuser, and current-database-owner changes until `DISCARD PLANS`; release-based history evidence covers 21 scoped RLS fixes/improvements not already present in PostgreSQL 14.0, with the 14.0-shipped pg_dump bulk-query improvement excluded, four previously omitted changes added, and the exact cross-branch first-release matrix omitted, and a comprehensive walkthrough of the `CREATE INDEX CONCURRENTLY` implementation (four internal transactions, two heap scans, three waits, table/session `ShareUpdateExclusiveLock`, `indislive`/`indisready`/`indisvalid` progression, invalid-index failure outcomes, regression/isolation coverage, and v18 changes from v17: `pg_index` TOAST snapshot handling, parallel GIN build, virtual-generated-column rejection, and temporal `WITHOUT OVERLAPS` shared plumbing), and a declarative-partition-bound analysis answering whether the bound syntax or `pg_class.relpartbound` changed since partitioning was introduced (three syntax changes, all landed by v12; the column definition never changed; the stored `pg_node_tree` gained `is_default`/`modulus`/`remainder` in v11 and lost real parse locations in v17; the deparsed `pg_get_expr` text never changed; exposure surfaces only gained additions; the v18-only grammar commit `2d8bff603c9`; the reverted MERGE/SPLIT PARTITION; the write-once/clear-once lifecycle and three engine read paths; and measurements taken on the previous 18.3-line pin `6cb307251c5` of the stored node text, DDL-time bound evaluation, the quoted-sentinel asymmetry, and the no-TOAST size cliff). The 2026-08-17 repin from the 18.3 line `6cb307251c5` to 18.6 `baa7b142aac` reviewed all 294 commits in the range, which crosses the 18.4 and 18.6 releases; 18.5 was stamped (`17fae4fbdd6`) but never released, as the checkout's own release notes record. Claim-changing commits: `0b12f56bfac` (CVE-2026-14666) registers `PlanCacheRoleCallback` so role, role-attribute and database-ownership changes invalidate role-dependent saved plans; `2a29b607dbb` (CVE-2026-6471) adds the `output_plugin_libraries` GUC that every logical-replication publisher must list `pgoutput` in; `cb35d730689` (CVE-2026-6638) quotes the publisher-side origin-check identifiers and so answers the bidirectional page's open question; `8a31ffc2d4c` (CVE-2026-14676) rebuilds `pg_stat_statements` query normalization on an expansible `StringInfo` without adding a length cap; `2780538433f` (CVE-2026-6470) requires `USAGE` on types used by index, policy and partition-key expressions; `e4527519b77` propagates `INDEX_CREATE_DEFERRABLE` to the `REINDEX CONCURRENTLY` copy; `fe464e9e686`/`5cc59834b86` move the custom-statistics drop entry point to `pgstat_drop_entry_ext()`; and `585181e0774`/`7c25cdb1ebf` add the extension-visible `read_stream_clear_strategy()`. No GUC present in both v12 and 18 changed its default in the range, and measurements taken on the previous pin are labelled as such rather than re-run. |
| 17 | active | [v17/index](v17/index.md) | `REL_17_STABLE` | `786db8dcf168bd9df8f55047337525ac19118b1c` | Behavioral claims cite the matching pinned checkout under `raw/postgres-17/`; filed coverage includes a sixteen-chapter tutorial of the whole query planner (pipeline, working model, transformations, row, width and cost estimates, scan, index and join paths, subqueries, upper operations, partitioning, parallel query and the JIT boundary, writes, plan construction and caching, extension interfaces and diagnosis) with a coverage matrix and a staged measurement script, the complete contrib extension inventory, explanations for all 53 control-file-backed contrib extensions, partial-index pros/cons with ordinary expression indexes as the baseline, partial expression indexes, planner predicate implication, expression-key matching, operational restrictions, `ANALYZE` row-count and expression-statistics behavior, planner costing, regression coverage, and a what-changed-from-v12 section covering the post-v12 documentation warning, concurrent-build safe-wait exclusion for partial/expression indexes, MERGE target rechecks, expression statistics, `NULLS NOT DISTINCT`, partial-unique proof restriction, and partial-hash planning fix, the COMMENT-stored non-B-tree inflation heuristic re-run end to end on 2026-09-16 under both bloat protocols *including* the `### The maintenance must not be defeated` rule they gained after its previous run - the first consumer page brought onto that rule, where the two held-snapshot fixtures were found never to have pinned the horizon because the snapshot was opened after the churn committed, and now report 240,000 and 960,000 tuples dead but not yet removable with no index page touched, then 2,330 of 2,970 GiST and 375 of 479 GIN pages deleted at FSM count 0 after release, with four new invariants reading 27 of 27, 33 of 33, 0 overlaps and 62 of 66 and the decision still right on 30 of 31, a GIN wasted-space page whose whole measurement programme was re-run on 2026-09-16 under the wiki's mandatory GIN bloat-test protocol, from one published script, with the declared kinds filed first (19 scored fixtures: upper bound 19 of 19, lower bound 17 of 19 and demoted to a level), reproducing every scored cell of the 2026-09-15 pass on two fresh clusters while correcting a metapage cross-check to 24 of 27, an f8 VACUUM sequence attributed to f5, a standby block count, a shortfall list and four timings, and gaining a `probe_after` stage so the after-`REINDEX` entry-tuple column is measured, and a reviewed summary of the seven GUC default-value changes since v12 (old/new value, introducing major version, apply scope, exclusions, and test-coverage notes, grounded in `guc_tables.c`/`config.sgml` and the checkout's own commit history), and a comprehensive walkthrough of the `CREATE INDEX CONCURRENTLY` implementation (four internal transactions, two heap scans, three waits, the `indislive`/`indisready`/`indisvalid` progression, a dedicated steps-and-locks section on `ShareUpdateExclusiveLock` + the `WaitForLockers`/`WaitForOlderSnapshots` waits, and a "what changed from v12" section centered on the PG14 `PROC_IN_SAFE_IC` snapshot-wait optimization, the reverted VACUUM-ignores-CIC attempt, and the `PGXACT`->`PGPROC` `statusFlags` move, anchored to the checkout's own commit history), two performance follow-ups covering `maintenance_work_mem` and the broader GUC matrix (build/parallel controls, AM and read-stream I/O boundaries, storage, WAL/checkpoint/commit costs, waits/timeouts, apply scopes, and commonly confused non-controls), including the separate AM-build and serial-validation budgets, B-tree/BRIN planned-versus-launched participants and mandatory worker tapes, hash/GiST/GIN/SP-GiST/BRIN/contrib-Bloom boundaries, conditional GIN pending-list cleanup, scoped observability, and the workload-specific plateau, a comprehensive walkthrough of the `REINDEX INDEX CONCURRENTLY` implementation with a source-backed GUC-performance follow-up covering build and validation memory, B-tree/BRIN worker request and availability, AM-specific GiST/GIN boundaries, v17 read streams, temporary and explicit output storage, WAL/checkpoint/commit costs across nine internal commits for one index, all five timeout-sensitive waits, exact apply scopes, and commonly confused non-controls, while the implementation covers (`ReindexRelationConcurrently`'s six phases and five waits, the atomic phase-4 `index_concurrently_swap` new-valid/old-invalid flip via the transactional `CatalogTupleUpdate`, the `_ccnew`/`_ccold` naming with a per-phase failure table showing a healthy `index_name` is never left invalid, a dedicated "can a failure leave an invalid index with the original index name?" section confirming a RIC failure never converts a bloated-but-valid `index_name` into no usable index (the phase-4 swap renames and flips validity in one transaction; only an already-invalid `index_name` stays invalid, the `concur_reindex_ind5` repair case), and a since-v12 section: partitioned REINDEX support via `ReindexPartitions` leaf recursion, `REINDEX (TABLESPACE ...)`, transactional `index_set_state_flags`, `PROC_IN_SAFE_IC` for RIC, the progress-view `WAIT_5` fix, the v15 shared-memory stats rework, and the v17 `MAINTAIN` privilege, anchored to the checkout's own commit history), and a fully reviewed analysis of whether `ALTER TABLE ... ATTACH PARTITION` can drop indexes (the built-in path cannot, but event triggers and `ProcessUtility_hook` can issue independent DDL; core coverage includes parser/utility dispatch, parent/child lock serialization with DROP, rollback, exact `CompareIndexInfo` matching—including reusable partial/expression indexes and, since 17.11 (`1d6c654c818`), element-wise exclusion-operator comparison instead of a blanket exclusion-index refusal—catalog/dependency re-parenting, physical and multilevel creation, generated/catalog/AM/contrib boundaries, tests and gaps, and meaningful changes since v12; exact-pin execution also exposed an open multilevel validity edge where recursive creation absorbs an invalid leaf while the pre-existing top parent stays valid), and a walkthrough of bi-directional logical replication (mutual `origin = none` subscriptions, apply-worker origin tagging into WAL, `pgoutput`/decode-time origin filtering, the `copy_data` initial-sync WARNING, setup pattern, and limitations) with its commit history grouped by minor version (16-cycle core commits `366283961a`/`8756930190`/`0324651573`, 17.0 `54ccfd6586`, 17.5 `0ae1245e04`, 17.10 CVE-2026-6638 `f0f59b658e`, plus foundations and adjacent origin-infrastructure commits), and a table-partitioning optimizations page covering v17 planning/execution optimizations per partitioning type (legacy inheritance: plan-time constraint exclusion only; declarative: plan-time + run-time pruning with per-HASH/LIST/RANGE bound matching, partitionwise join with merged non-identical bounds, partitionwise aggregate FULL/PARTIAL, and executor tuple routing/row movement/COPY batching, plus the four `PGC_USERSET` GUCs) with an "optimizations since v12" section attributing v13 advanced partitionwise join (`c8434d64ce0`), v14 run-time pruning for `UPDATE`/`DELETE` (`86dc90056df`) + `DETACH PARTITION CONCURRENTLY` (`71f4c8c6f74`), v15 `live_parts`/run-time-prune refactor/`MERGE` (`475dbd0b718`/`297daa9d435`/`7103ebb7aae`), v16 cached tuple routing (`3592e0ff98b`), and v17 `boolcol IS [NOT] UNKNOWN` pruning (`07c36c1333e`) + concurrent-detach robustness (`11f1218ce81`) to the checkout's own Stamp-bracketed commit history, plus a follow-up section on per-optimization locking reduction and random-I/O sensitivity (only plan-time pruning removes read locks; run-time pruning and constraint exclusion keep the locks `AcquireExecutorLocks`/`find_all_inheritors` already took; scan-eliminating optimizations gain most on slow random storage because avoided per-partition fetches are priced at `random_page_cost`; and, unlike v12, v17 partitionwise aggregate gains by avoiding a hash-agg spill whose writes `cost_agg` prices at `random_page_cost`, while hash-join spills stay `seq_page_cost`). Filed coverage also includes a planner-penalties-for-bloated-indexes walkthrough establishing that v17 penalizes a bloated B-tree only through four inputs, of which only the first two are `IndexOptInfo` fields that `get_relation_info()` fills, the other two being expressions the cost code derives from `pages` at costing time, while GIN and BRIN price bloat from metapage counters no `IndexOptInfo` field carries (`IndexOptInfo.pages` from a live `RelationGetNumberOfBlocks()` call for non-partial indexes or `estimate_rel_size()`'s `pg_class` density for partial ones, the fast-root `tree_height` charge of `DEFAULT_PAGE_CPU_MULTIPLIER` (50) `* cpu_operator_cost` per level, `index->pages` in `index_pages_fetched()`'s cache model together with the touched-pages estimate `numIndexPages` that `compute_parallel_worker()` reads, and the v17-only clamp `num_sa_scans = Min(num_sa_scans, ceil(index->pages * 0.3333333))`), that `pgstatindex`'s `avg_leaf_density` and `leaf_fragmentation` are read by nothing on the cost path, eight bloat shapes with a per-query-shape sensitivity matrix, and a since-v12 history in which `index_pages_fetched()`/`cost_index()` are byte-identical to `REL_12_0` while v13 deduplication, v14 bottom-up deletion/same-VACUUM recycling/index-vacuum bypass/failsafe/`reltuples = -1`, v16 macro extraction and partitioned-index zeroing, and the v17 SAOP clamp are attributed to their first major versions by branch-point ancestry, the checkout carrying no tags; exact-pin measurements, all re-taken on the 17.11 pin on 2026-09-19 from the page's published script, reproduced the cost closed form to the cent on 7 of 7 scans, an identical `4.44` point lookup across a 9.62x size difference that rises to `12.29` once pages outnumber rows, a `1616.00` gap equal to exactly `404 * random_page_cost` between 49.87% and 0% `leaf_fragmentation`, two 2,745-block indexes at an identical `12730.42` with 9.27% versus 89.18% `avg_leaf_density`, a forged `pg_class.relpages = 1` that changed nothing for a non-partial index, a 25%-selectivity `Seq Scan` flip, an index dropped from a `BitmapAnd`, 4 versus 6 parallel workers on whole-index scans and 2 versus 5 on 20% scans, a repeated inner scan at `0.66` versus `2.50` per loop, `tree_level` 2 against a planner-visible `fastlevel` of 1 after page deletion alone, a SAOP descent plateau at 3 on the dense index (the bloated twin's cap of 19 computed, not reached at 10 elements), 852 versus 2,749 blocks with `deduplicate_items = off`, and 543 versus 1,173 blocks of version-churn growth without and with a held `REPEATABLE READ` snapshot on a 1,000-value column against 1,020 either way on a 100-value one; a filed follow-up on that page answers when a GIN index is discarded and a B-tree used instead, establishing three gates (clause matching against the GIN opfamily with `btree_gin` as the escape hatch, plan shape from GIN's AM flags, then `gincostestimate()` cost plus `add_path()`/`choose_bitmap_and()` pruning), the 4X stale-metapage fallback and the `gin_clean_pending_list()` staleness trap, the keyless full-index path on a partial GIN index, the four `CREATE INDEX`/`CLUSTER` rejections, where GIN still wins, and the v17-specific fact that a bare boolean `Var` does match a `btree_gin` bool opclass; exact-pin measurements priced `n = 42` at `12.97` through GIN versus `4.52` through a B-tree on identical statistics with both closed forms reproduced to the cent, proved two no-GIN-path cases through `disable_cost` plus one where GIN keeps the index and loses only the index-only scan, moved a GIN scan from `13.01` to `3141.12` at 736 pending pages with the index still kept in the `BitmapAnd`, then to `6264.98` at 1,471 pages and out of it, recovered the charged page count exactly in eight states (including `739.00`, `1474.00` and `1001.00` on a 10-block index), and measured a multicolumn `gin (tsv, cat)` beating the `BitmapAnd` at `21.51` versus `240.13`. A second 2026-09-19 pass fixed fourteen reported defects on that page, each confirmed against the pin before it was fixed: one P1 in the published script, where `stage_check()` and the stage dispatcher both discarded exit statuses so a run whose four test suites all failed still exited 0, now fixed along with an `EXIT`/`INT`/`TERM` teardown trap and a per-stage server start that makes the documented selective re-run work; a rebuilt `BitmapAnd` fixture, whose `c = g % 20` against `a = g % 2000` had made `a = 5 AND c = 7` impossible because 20 divides 2,000, now an independent seeded draw that moves 428 blocks at 89.59% density to 427 at 89.81% and the `BitmapAnd` total `332.49` to `328.51` and records estimate against truth at 250/250, 24,971/24,971 and 12/12; and eleven source readings, among them the planner's `tree_height` being a stale per-backend `rd_amcache` copy that `_bt_getrootheight()` never refreshes, `leaf_fragmentation` counting backward sibling links only, an `UPDATE` not always writing into every index because a HOT update of summarizing-only columns yields `TU_Summarizing` and a predicate-failing partial index takes nothing, VACUUM's 2% bypass clearing only `do_index_vacuuming` and still running `amvacuumcleanup` so that it flushes a GIN pending list, `fillfactor` and `deduplicate_items` reaching existing pages at their next split, GIN and BRIN reading metapage counters beyond `IndexOptInfo`, `FormData_pg_class` being cpp output of the `CATALOG()` macro rather than a `genbki.pl` product, a serial GIN bitmap still being able to feed a `Parallel Bitmap Heap Scan`, `gin_pending_list_limit` triggering a non-forced cleanup after the insert rather than capping the list, and `enable_bitmapscan = off` adding `disable_cost` rather than removing the path. Three passes re-measured every number, the second and third reproducing the first byte for byte apart from their run timestamps. A 2026-09-20 pass fixed ten more reported defects, again each confirmed against the pin: a P1 in the script where `pg()` and `pgq()` returned their status to callers that never looked at it, so a failed fixture build or `UPDATE` round mid-stage passed as a run (reproduced: 0 before the fix, 1 after); fixture D rebuilt on independent populations, because marking every 5,000th row against `cat = i % 20` made `zebracorn AND cat = 7` impossible for the same reason L3's clauses were, and a 4,999-row period reproduced every filed cost to the cent while the true count moved from 0 to 4; and eight source readings, among them the four-input table being a B-tree-family summary rather than an all-index one, `_bt_getroot()` and `_bt_gettrueroot()` also clearing the cached tree height, a table `parallel_workers` reloption skipping the page-based worker calculation while inheritance children are exempt from the minimum-size rejection, HOT requiring `newbuf == buffer` so that a row that no longer fits on its page churns every index through `TU_All`, the two-`random_page_cost` page-charge probe being invalid under a tablespace `random_page_cost` override, the one-page rule being bounded below by `tuples <= 1` as well as above by `pages > tuples`, `n IN (1,2,3)` taking GIN's array cache adjustment at `arrayScans = 3`, and gate 1 rejecting a clause rather than the index. New fixture F-one measures the lower bound: a 551-block index stripped to one live leaf page is charged one page and prices a whole-index scan at `4.14`. Filed coverage also includes the current recommended core-SQL B-tree wasted-space estimator, rewritten on 2026-09-08 to implement all ten of its repair plans and measured on an isolated 17.11 server built out of tree from the pin (`make check` 225/225, `pageinspect` and `pgstattuple` checks passing): it now reports exactly `0 bytes` on 10 of 10 freshly built indexes with keys from 8 to 2000 bytes, reproduces `relpages` in 78 of 78 (key width, fillfactor) geometry cells, and equals the `REINDEX INDEX` outcome in 6 of 7 insertion-pattern fixtures, after fixing three deterministic defects (inheritance-parent double counting at `-550.8 %`, an expression index silently dropped for a non-owner, and `ERROR: bigint out of range` aborting the whole report) and three found under measurement (the missing hard-fit reservation, the internal-level minus-infinity item and never-closed rightmost page, and a three-byte-too-wide expression width), with a three-state `equalimage` column, two-size posting-tail pricing, `numeric` output and a companion probe generator; four measured residuals remain open. Re-verified on 2026-09-09 against the same pin on an independently built 17.11 server (`--with-icu --enable-debug`; `make check` 225/225 plus the `pageinspect`, `pgstattuple` and `amcheck` checks): all 476 citations re-read and every measured figure reproduced (78/78 geometry cells, `0 bytes` on 10 of 10 fresh builds, the three deterministic defects, the equal-image matrix against `bt_metap`, 132 TIDs at 808 bytes, posting mean absolute error 16.06 % to 5.77 %, the seven-pattern calibration digit for digit, 367 against 10,003 compression blocks, and both probes), the deduplication gate scored against the current statement for the first time (27 fixtures, zero over-credits, `equalimage` matching the metapage on all 20 `recognized`/`ineligible` rows, `i_multi_bad` at exactly 28.8 %, the `text` fixtures fixed from `+7.8 %` to `-0.2 %`), and the nondeterministic-collation branch measured for the first time. Six reporting defects were corrected in place - the published `relpages` comparison (26/52/15, not 53/71/5), the non-owner row count (8 of 10, not 9), the posting table's inverted sign convention, the barrier artifact's unstated 1-second flush-interval precondition, a 32-byte datum described as a 32-byte tuple, and the platform question, settled as `Linux x86_64` at `max_data_alignment` 8 - and one open question was added: a duplicate-heavy multicolumn index with correlated keys and no `ndistinct` statistics object reads `-320.0 %` to `-562.1 %`, which `CREATE STATISTICS` takes to `0.0 %`. Also filed: a measured answer to how to tell, after a `pg_upgrade` from v12 to 17, whether a B-tree index must be rebuilt to enable deduplication - deduplication safety lives only in the metapage field `btm_allequalimage`, which v12 never wrote and `pg_upgrade` never sets (`btm_version` is 4 on both sides, so version is not the discriminator), plus a core-SQL-only probe (byte 64 of block 0 through `pg_read_binary_file` + `get_byte`, no `pageinspect`), a catalog mirror of `_bt_allequalimage`, the exact `GRANT EXECUTE` required, a platform self-test, priority ordering and snapshot/twin fallbacks; reviewed and re-measured on 2026-09-15 on the 17.11 pin, with the whole measurement published as one Bash-and-SQL script that builds both majors from their pins, runs one `pg_upgrade --copy` and tears itself down (`make check` All 225 plus `pageinspect` All 8, and All 192 on 12.2): 26 carried-over index files, 26 of 26 digests identical with OID and relfilenode preserved, all 26 reading the flag false, the 22 in `public` at `pd_lower = 64` and version 4, the filed check printing 189 rows and flagging 20 of the 26 while refusing 6, `bt_metap()` agreeing in 189 of 189 rows and 23 of 23 after the rebuilds, the gate matching the metapage on 17 of 17 shapes including nondeterministic and deterministic ICU collations, 17 concurrent rebuilds reclaiming 67.4% to 69.1% on eight duplicate-heavy indexes and 0.00% on the six refused plus the unique, `uuid` and empty ones, a carried-over index equal to the byte to a fresh `deduplicate_items = off` twin with a 48.5%-bloat-over-69.1%-deduplication split after one update of every row, and a 0.0%/9.8%/48.1%/65.4%/69.5%/67.4% savings curve at 1/2/5/20/100/1000 rows per key; that review corrected five claims - the `btm_oldest_btpo_xact` repurposing belongs to `e5d8a999030` rather than `9f3665fbfc3`, the relfilenode-snapshot fallback must join on schema and name because `REINDEX ... CONCURRENTLY` moves the name to a new `pg_class` OID and the OID join silently dropped 17 of 20 rebuilds, the post-upgrade statistics are missing because `index_update_stats` skips them under `IsBinaryUpgrade` and the carried-over `pg_largeobject` index reads `reltuples = -1`, the old "relfilenodes continued from the old cluster's NextOID" claim is withdrawn after `NextOID` read 16449 against 24576, and the `INCLUDE`-index page loss did not reproduce - and files `pgupgrade.sgml`'s "all rebuild and reindex cases will be reported" as a documentation discrepancy; still including the `deduplicate_items` trap, `VACUUM FULL`/`CLUSTER` versus plain `VACUUM`, and `pg_largeobject_loid_pn_index` as the only carried-over catalog index; reviewed again on 2026-09-16 at the unchanged pin, where all 175 citations (73 ranges over 35 files) were re-read and every one held in bounds and on label (8 ranges added, none corrected) and the script was re-run four times with every scored cell identical on all four, and which found the one shape the page had wrong: an `interval` index carried over from a pre-fix 13-16 cluster arrives with the flag true where v17 says false, because `5f27b5f848a` withdrew `interval_ops`'s support function 4 while v17's `btequalimage()` still returns true unconditionally and only a rebuild rewrites the field, which `amcheck` reports as "metapage incorrectly indicates that deduplication is safe" - so the filed check gained a `rebuild for correctness: metapage says safe, catalogs disagree` branch that matches 0 rows on a 12 → 17 leg, the refusal list became the 16 rows of `opr_sanity`'s expected output (adding `interval`, `tsquery` and `tsvector` to the scalar refusals), the partial-index triage row was corrected from "9,986.7 against an actual 99,867 rows over 10 keys" to 9,673.4 printed against an exact 100,000 rows over one distinct key value with `reltuples` sampling 101,667/104,734/98,700/96,734 across the four runs, and the page gained `_bt_first`, the posting-list asserts, both metapage WAL copies and `amcheck` as flag readers plus an itemized server-log audit of 6 deliberate `ERROR` lines on 17.11 and 0 on 12.2. The 2026-08-17 repin from 17.10 `54eeefaedbee` to 17.11 `786db8dcf16` reviewed all 193 commits in the range: `1d6c654c818` made `CompareIndexInfo` compare exclusion operators instead of refusing every exclusion index, `f67b9dd8fc7` rewrote the ATTACH index documentation, `28269fed661` propagates `INDEX_CREATE_DEFERRABLE` to the `REINDEX CONCURRENTLY` `_ccnew` copy and adds the `reindex-conc-index-built` injection point, `d1c8aa0b09f` (CVE-2026-6470) requires `USAGE` on types used by index expressions and predicates, `31f2acde53d` stopped RANGE pruning from wrongly discarding the DEFAULT partition, `01992176e08` (CVE-2026-6471) added the `output_plugin_libraries` GUC, `14810cc0d96` rebuilt replication-command quoting, and four refint commits documented its PostgreSQL 20 removal and secure-schema requirements. No GUC default moved in 17.11, and measurements taken on the previous pin are labelled as such rather than re-run. Filed coverage also includes a pgstatindex-only B-tree bloat report that runs unchanged on 12 and 17: one statement whose only measurement function is `pgstatindex`, which prefilters nothing and prints every candidate index including the catalog's own (365 rows on 17.11 and 350 on 12.2 in its current run), reporting wasted space beside estimated reclaimable space, both measured against a rebuild at the index's own fillfactor, with every candidate filter justified by a shape `pgstatindex` raises on -- non-B-tree access methods, partitioned indexes, another session's temp index, and an invalid index, which 17.11 refuses (`13503eb5905`, back-patched according to its own message) and the pinned 12.2 reports. Re-ported on 2026-09-13 to the shared mandatory B-tree bloat tests as they then stood, 113 numbered tests with the maintenance assumption, and reviewed again on 2026-09-16 as the last of that concept page's three consumers to come onto `### The maintenance must not be defeated`: all 328 citations were re-read against the pin and none was wrong, the harness gained the `maint`, `horizon` and `pageclass` tables with their four functions, the fixture file's 33 maintenance statements and the drain's 38 each became one bracketed `VACUUM (VERBOSE, ANALYZE)` in a session with every settable timeout at 0, and the churn stage now dies rather than score a defeated fixture. Both legs were rebuilt and re-run in one invocation each on Linux x86_64: 67 maintenance statements per leg, all completed, `dead but not yet removable` 0 on every one, 73 of 73 horizon probes clean on each, 0 skip or cancellation lines, and 10,340 and 11,868 deleted index pages; 126 fixtures scored on 17.11 and 117 on 12.2, with 0 and 9 recorded skips, `PASS` on all of them with no false positive or false negative of either severity, 93 and 100 estimates within one point of a measured `REINDEX INDEX`, worst over-estimate `+10.0` and `+6.3`, and worst under-estimate `-4.1` where it had been `-9.8` before the maintenance step removed the dead index entries behind the old `b93`/`b95` under-read. Rule 3's census analyzed only `f85t` and `x108t`, 2 of 88 tables, on both legs. The page files as open questions that the suite no longer builds the unvacuumed or deduplication-off shapes that defeat `pgstatindex`, and its undrained `i_dedup_off` guard fixture still misses by `-69.4` points. Also covered: the `NaN` trap, the `pg_stat_scan_tables` grant and the OID form's freedom from schema `USAGE`, the bulk-read ring, a `lock_timeout` cancellation, the concurrent-drop abort, and the earlier reviews of 2026-09-10 and 2026-09-12, whose history the page keeps. The bloat-method page's mandatory suite is now 92 tests: test 113 drains a partial index completely (1,000,000 `state = 'pending'` rows updated to `'done'`) and the recommended statement failed all three states on a 100.0% reclaim, fixed by change E — believe a `reltuples` of 0 when it is provably current, v14 or later and `n_mod_since_analyze = 0` — with the auto-analyze-trigger variant rejected because it reports 99.3% on a live 1.1 MB index, one measured false positive of its own when an `ANALYZE` sample misses the whole predicate subset, a 4-of-119-rows `EXCEPT` regression check, and a measured no-op on 12.2. That guard was then removed outright at the asker's request, so every `reltuples = 0` is priced as an empty index on 12 through 17 and the unreachable `unmeasured: reltuples 0` status arm went with it; re-scored on both servers, the removal moves 3 of 118 rows on 17.11 (buying nothing and costing one critical false positive, fixture 118 at 99.3% on a live 1.1 MB index with no caveat) and 7 of 103 on 12.2 (three genuinely 99.6-100.0% reclaimable indexes reported on that major for the first time, against two new false positives), with a new non-partial fixture reading `unmeasured` on 17.11 and 100.0% on 12.2 because a new relfilenode leaves `reltuples = -1` there and 0 here. A GIN wasted-space procedure is filed: no single contrib function can do it, since `pgstattuple` refuses GIN (`(gin index) is not supported`, and refuses an invalid GIN index earlier as `is not valid`) and `pgstatginindex` reads only `version`/`pending_pages`/`pending_tuples` from block 0, so the answer is a `pageinspect` page census - blocks 1..relpages-1 read once each through an `OFFSET 0` lateral (1234 buffer hits against 2468 for the naive two-call form), the same `bytea` into `gin_page_opaque_info` and `page_header`, classification by the flags array with a NULL result identifying `PageIsNew` (`pd_upper = 0`), and three separately reported numbers - whole-page waste, live-page slack split entry-tree versus posting-tree, and pending-list bytes - beside one derived `bloat_pct` column that sums the first two as page accounting without a guaranteed bound on a rebuild, cross-checked against `pg_freespace`, `VACUUM VERBOSE`'s fourth index number and the metapage's `n_entry_pages`/`n_data_pages`. It corrects two premises on evidence - a free index page reads **8160** from `pg_freespace`, not 8191, because the FSM keeps one byte per page and category 255 maps back to `MaxHeapTupleSize`; and GIN's `pages_deleted` is a per-run counter, not a census. The page was reviewed end to end on 2026-08-26 against a server rebuilt from the pin, with its seven fixtures now published as SQL and three of them reproducing the first run's figures byte for byte. Scored against `REINDEX INDEX` over those seven fixtures, `waste + slack` bounded the truth from above 7 of 7 while `waste` alone did **not** bound it from below: 64.64% dead pages against 58.05% reclaimed, because `entrySplitPage` halves entry pages so a fresh build is only half to two-thirds full and a 268-block in-use core rebuilt to 318 blocks. Entry-page slack is growth room - a fresh control reads 48.05% slack and reclaims nothing, and a rebuilt index absorbed 50,000 rows with zero growth in either tree - while posting-tree slack tracked the truth (51.34% against 46.33%). The review also measured the payload-and-fill model's failure mode (+19.94% when churn replaces the key population against +0.07% when it does not, because the entry tree never deletes tuples), dead-page reuse (491 dead pages absorbed a 50k-row pending list for +26 blocks), a flush that left the file size unchanged, and the recovery refusals on a physical standby where `VACUUM` is refused too while the census answers. Also filed: the four-state pending-list lifecycle, 768 deleted pages staying non-reusable across two VACUUMs until three xids were consumed, the superuser-versus-`pg_stat_scan_tables` split, invalid/partitioned/other-session-temp behaviour including `pg_freespace` answering where the other two refuse, the absent GIN verifier in v17 amcheck, and cancellations at 2001.272 ms and 1500.477 ms. A third pass attacked the eleven open questions with measurements and left ten (two closed, six narrowed, one new): the published fixture SQL reproduces every filed number byte for byte in two virgin databases, with `prune_xid` the only figure that moves; a five-point churn sweep puts the payload-and-fill model's error on a straight line (+12.53 points per 25% of the key population replaced); an entry-tuple probe read out of `pd_lower` on entry-leaf pages equals the index's key count exactly and measures the dead-key population (50,028 against 1 on the two churn shapes), though the correction needs a dead-tuple size no contrib function exposes; `fh2_gin` breaks the lower bound a second time (21.66% dead against 19.25% reclaimed) and the bound proves to be an identity - waste under-reports exactly when the aged in-use core is smaller than its own rebuild; flush growth gets a mechanism, since a flush can never reuse the pages it frees (`RecordPageWithFreeSpace` writes only the bottom FSM level while `fsm_search` starts at the root) and the pending list spends the free stock first (0 free -> +736 blocks, 736 free -> +0 on four consecutive rounds); a concurrent VACUUM defeats every cross-check, reporting 0 to 2,294 dead pages against a truth of 2,368 on an unchanging file, while re-reading the file size after the census catches writers 13 of 14 where the metapage check catches 0 of 14; `REINDEX CONCURRENTLY` matches plain `REINDEX` byte for byte under a 100,000-row insert stream; four more opclasses and a 16x scale check take the tally to 26 fixtures at 26 of 26 upper bound and 24 of 26 lower; and the eviction claim is corrected - a 26,195-block census left a hot 3,704-page working set fully resident while destroying a once-read set of the same size, because the clock sweep spends usage count rather than pages. A two-major follow-up then makes all four published statements run on PostgreSQL 12 and re-runs the entire programme on 12.2 and 17.11: three edits suffice (a `::int` block number, a `pagesize = 0` page class, and the same guard on the probe), the FSM check and size bracket need none and derive 8160 on both, and 26 of 27 scored fixtures plus the lifecycle, horizon, flush, privilege, timeout, standby and rebuild-equivalence readings come out byte-identical, with identical bound tallies of 24 / 25 / 26 of 27. The decisive difference is that 12.2 returns `flags = {}` rather than a NULL row for an all-zero page (the fix is `Backpatch-through: 10` and first tagged `REL_12_11`), so the unpatched text counts zeroed blocks as entry pages and reports 0 waste bytes, and a zeroed metapage aborts the whole census there; 12.2's `pgstatginindex` also answers for an invalid index where 17.11 refuses. Two headline claims are corrected - `waste + slack` is not an upper bound with a large dead-key population (43.43% against 50.00% reclaimed) or a live pending list, and a census does evict a hot working set once the target exceeds the cache - and a fresh GIN build's size turns out to be a function of `maintenance_work_mem`, 34,611,200 bytes at 64MB against 50,814,976 at 96MB and up on both majors. Open question 7 is closed: the round-five entry-tree explosion is slack exhaustion. Filed coverage now also answers how a SQL query reads an index's entry count from the catalogs for every index type: `pg_class.reltuples` on the index's own row is the only catalog column that ever holds it, its unit is decided by the access method (B-tree heap TIDs pre-deduplication, hash omitting NULL-keyed rows, GIN entries summed over rows and columns, BRIN summarized page ranges, GiST/SP-GiST/bloom one per row), and it is byte-exact against `pageinspect` and plain-SQL ground truth on 14 of 14 indexes immediately after a serial rebuild (reproduced from scratch in a second database) but is overwritten by the next `ANALYZE` with `ceil(tupleFract * totalrows)` for every access method; includes a published catalogs-plus-`pg_stat`-views statement with only catalog-decidable verdicts, a forgery probe establishing per-AM which access methods refresh a stale count during a plain VACUUM, four different BRIN readings for one index (116 serial / 319 parallel / 12 partial / 115 after VACUUM against 116 on disk), the GIN metapage distinct-key count that never reaches `pg_class`, the `0` versus `-1` sentinel asymmetry between a new index and its table, the `float4` 2^24 ceiling measured at 20,000,001 entries, and a proof that ordering `pg_stat_all_tables` timestamps cannot decide provenance. Filed coverage also includes a GIN-only `REINDEX CONCURRENTLY` candidate heuristic whose only persistent state is a 137-byte `@ginbase:` JSON payload inside the index's own `COMMENT ON INDEX`, normalized by the *table's* `reltuples` because the GIN index's own reads 994200 / 200000 / 100000 / 500000 / 500000 / 100000 across `CREATE INDEX`, `ANALYZE`, `DELETE` + `VACUUM`, `REINDEX`, a second plain `VACUUM` and `VACUUM (DISABLE_PAGE_SKIPPING)`; reviewed and re-run end to end on 2026-09-17 under the mandatory GIN bloat-test protocol - the last consumer page brought onto that protocol's no-defeating-the-maintenance rule, which it gained after the page's previous run - from one published 1,902-line script over 24 scored fixtures, where the decision was right 19 of 24 with 1 false positive and 0 false negatives, all 79 settle and maintenance steps ran with the four settable timeouts forced to 0 and 78 of 78 reported 0 tuples dead but not yet removable with 0 skips and 0 cancellations while the one declared held-snapshot step reported exactly 500,000, the page's single declared upper bound `est_reclaimable` was violated on 8 of 21 and demoted to a level (the mover, `c02`, flips on an `ANALYZE` sample measured at 1,001,233 to 1,002,633 against a true 1,000,000), the settle step the protocol mandates was measured to *add* bytes on 8 of 23 fixtures (up to 4,849,664, 16,310,272 in total, 0 shrank), a rebuild made one fixture 21.01% larger than its churned file, the fresh-build curve grew 2.67x across the posting-tree conversion and then 1.38x, the `fastupdate = on` twin carried a 515-page `gin_pending_list_limit`-sized high-water mark where the `fastupdate = off` twin added no bytes, a 64MB build came out 20.3% larger than a 256MB one with the metapage identity exact on 9 builds and 25 baselines, and the `n_mod_since_analyze` staleness veto stayed withdrawn after the `PGSTAT_MIN_INTERVAL` flush race misreported 15,000 dead and 15,000 modified rows on 4 of 4 attempts where the truth was 0; all 154 citations it carried were re-read against the pin and every one held, taking the page to 208 occurrences over 96 ranges in 32 files. Filed coverage also includes a measured answer to how much I/O a `VACUUM FULL` performs on a multi-GB, near-empty heap: reads scale with the heap's full physical size and writes with the live data only, because the rewrite's `SnapshotAny` sequential scan never consults the visibility map, and on four byte-identical 200-million-row fixtures (7,249,559,552 bytes / 884,956 blocks, all pages all-visible and all-frozen) it read 884,956 blocks with zero hits and exactly 7,249,559,552 bytes against a plain `VACUUM`'s 0 blocks, in 55,361 read system calls (15.985 blocks each) because v17 routes the scan through the read stream at `io_combine_limit = 128kB` - a six-point sweep moved the call count 28,179 -> 976 with the block count fixed at 44,248 - plus the 885-block new heap, 28 batched `XLOG/FPI` records, `wal_level = minimal` dropping WAL 7,353,992 -> 110,008 with reads unchanged, the zero-row heap read in full to produce a 0-byte file, `heap_blks_scanned` stalling at 0 for 427 of 434 samples yet ending at 884,956, and emptied pages left with zero line pointers at `pd_lower = 24`. Filed coverage also includes a source-and-history walkthrough of relation truncation by `VACUUM` and autovacuum: `nonempty_pages`, the three gates in `should_attempt_truncation` (1000 pages or 1/16 of the relation, plus the failsafe), the ~5 s conditional-lock budget, the mandatory backwards `count_nondeletable_pages` verification and its self-suspension on a lock waiter, `RelationTruncate`'s batched main/FSM/VM truncation inside a critical section, TOAST coverage including the 17.6 `2e0b5d252b1` fix that lets a TOAST table read its own `toast.vacuum_truncate`, autovacuum's separate TOAST scheduling and its cancellability while holding the `AccessExclusiveLock`, and 16 commit-attributed changes since v12 headed by the v17 removal of the `old_snapshot_threshold` veto (`f691f5b80a8`); and a built-and-measured, release-dated inventory of the improvements since v12 across storage performance, query planning, index bloat and vacuum, run on isolated 17.11 and 12.2 servers built from this repo's own pins with identical settings, whose release dating uses per-tag symbol presence rather than `git tag --contains` (which would misdate `MAINTAIN` to v16 and `recovery_prefetch` to v14, both reverted and re-landed, and would admit the never-shipped eager/lazy freezing strategies) and whose headline measurements are deduplication at -69.0%/-93.9% with all-distinct indexes byte-identical, bottom-up deletion isolated at -64.3% via `deduplicate_items = off` and worth nothing where keys change, the v17 TidStore cutting index passes 18 -> 2 at `maintenance_work_mem = 1MB`, the v14 bypass reducing a VACUUM to 22 buffer hits and 391 bytes of WAL, Memoize at 977x fewer buffer hits, incremental sort at 7,447 -> 11 buffers, the v17 SAOP rework at 1,504 -> 5 buffers on clustered keys and nothing on spread ones, and the v17 read stream at 53,210 -> 3,346 read syscalls with an 8 kB control that reproduces 12.2 exactly, plus three expectation-contradicting results (v13 disk hash aggregation slower than v17's own sort, and v16 page-level freezing freezing nothing at default settings on either major until `wal_log_hints` is on), and a comprehensive source-and-history mechanism walkthrough of bottom-up index deletion and B-tree deduplication as two of the three page-split-avoidance strategies `_bt_delete_or_dedup_one_page` runs in a fixed order (the four booleans that select a strategy including the `checkingunique && !uniquedup` early return; the `indexUnchanged` hint's key-columns-only derivation in `index_unchanged_by_update`; the `TM_IndexDeleteOp` contract with its `Max(BLCKSZ/16, newitemsz)` target and `Max(BLCKSZ/24, newitemsz)` success bar; heapam's promising-TID bucketing, `BOTTOMUP_MAX_NBLOCKS` = 6 / `BOTTOMUP_TOLERANCE_NBLOCKS` = 3 favorable blocks and three give-up rules; the dedup pass, posting list format, single value strategy at 5/6 `nmaxitems` and posting list splits; the `!btspool->isunique` build-time gate; why dedup needs `allequalimage` and bottom-up "deliberately omit[s]" that test; bottom-up being B-tree-only; WAL, locking, error paths, a VACUUM comparison, the total absence of any counter or wait event, and the absence of any test naming bottom-up deletion), dated by presence test at release tags to 14 commits from `0d861bbb702` (v13) and `d168b666823` (v14), with the finding that v17 changed nothing behavioral in either mechanism. The 2026-09-05 source review of the GIN census plan adds seven findings and a revised six-step plan covering metric definitions, recycling eligibility, completed index cleanup, scan consistency, FSM interpretation, format guards, and the main-fork size denominator; the SQL is unchanged and the historical experiments were not rerun. The 2026-09-07 B-tree estimator cleanup retains one current statement and its supporting explanation and limitations; superseded variants, alternate methods and historical follow-up material are no longer part of that page. Executable SQL and source pins are unchanged; no server measurements were rerun. The 2026-09-08 GIN pass implemented the last three open questions on the census page: every literal size is derived from `pg_control_init()` or measured on the build by a layout probe that reads `SizeOfPageHeaderData` 24, `sizeof(ItemIdData)` 4 and the 8-byte GIN special area off an empty GIN index's root and reaches the FSM's 8160 from that pair, with the derived census matching the guarded one in 240 of 240 cells on two databases at the same 7,890 buffers; a `SHARE ROW EXCLUSIVE` measurement protocol replaces detection with enforcement, blocking eight concurrent commands while readers run and turning 40 censuses that read nine different dead-page counts across one VACUUM into 20 identical ones, with its one hole (an owner's `gin_clean_pending_list()`, which locks only the index) measured at `bloat_pct` 8.66 -> 82.74 inside a locked transaction; and the acceptance cases that needed more than SQL: the wraparound failsafe, reached with `autovacuum_freeze_max_age` at its 100000 minimum (restart) plus 120,000 burned xids, leaving the census and metapage untouched while `vacuum_count` advances and being the one bypass VACUUM's own output names, four `-m immediate` crashes yielding 0, 0, 2 and 6 byte-for-byte-zero pages at the file tail that the FSM cannot see, and three corruption shapes including one the buffer manager refuses before any SQL guard runs. The core programme reproduced a fifth time and the churn sweep digit for digit; the published extended fixture SQL does not reproduce the first corpus's extended scoring table, filed as open question 20. The 2026-09-09 mandatory-test review on the B-tree estimator page found that its numbered suite (tests 1-17, 18-91, fixtures 92-121) has never been scored against the revised statement, derived the expected verdicts from the two SQL texts, listed eleven test gaps including ICU, the 12.2 leg, role coverage, block size and parallel, concurrent and partitioned builds, and filed a runnable rerun protocol with pass criteria; no server was built and the four SQL blocks re-hashed to their baselines. On 2026-09-09 the whole suite became two Bash-and-SQL scripts filed in the B-tree estimator page, one for 17 and one for the 12 leg, and both were run: they extract the four SQL blocks from the page itself (all five SHA-256 baselines still match after the edit that added them), build 17.11 (`make check` All 225 plus 8/1/3 for `pageinspect`, `pgstattuple`, `amcheck`) and 12.2 (All 192 plus 5/1/2), and reproduce 78 of 78 geometry cells, `0 bytes` on 10 of 10 fresh builds against the superseded text's 6, a 28-fixture gate with zero over-credits, posting-tail mean absolute error 11.38 % to 0.38 %, and the previously unscored partial-index half of the mandatory suite: 112 numbered fixtures scored against a measured `REINDEX INDEX`, 59 reported and 53 withheld with every withheld row naming its term, 0 contract failures, and three reported critical false positives that survive the page's own reading rule (a forged stale partial `reltuples` at 94.2 %, `i103` at 84.1 %, `x109` at 62.5 %, all against a measured 0.0). The cross-version open question was answered no on 2026-09-09 — the exact text was refused on the pinned 12 server with `ERROR: column se.inherited does not exist` — and fixed on 2026-09-10, when the `extstat` CTE started reading that flag as `coalesce((row_to_json(se) ->> 'inherited')::boolean, false) = false`: the exact filed text is now accepted unmodified on 12.2 with `transform_edits=0`, `EXCEPT` in both directions returns 0 rows over 186 rows in six 17.11 databases, the previous text rebuilt from the filed one still hashes to `8acd531b…` and is still refused there at `LINE 116`, and a new `extstat` stage in each script scores three texts on four extended-statistics fixtures, closing the widening question by measuring the old delete-the-line transformer at 2.3, 60.1 and `-33.7` against measured reclaims of 0.0, 59.7 and 0.0; 19 fixtures still score on 12.2 with every gate verdict `ineligible` and `nzb_k`/`i_trunc` reading 99.9 % where 17.11 reports `unmeasured`. Two new open questions: fixture 120 flips verdict run to run with the 300-row ANALYZE sample, and the probe generator's 1 MB filter skips the small subsets whose readings most need validating. On 2026-09-09 the same page's measurement-script section was audited read-only against `MANDATORY Measurement Script` and restructured to comply: the two suite scripts now sit under a top-level `## Measurement Script` section with the eight-item usage information (per-stage tables naming each stage's prerequisites, every environment variable and its default, build/extension/locale prerequisites, output, runtime and cleanup), and thirteen defects were repaired in place — an `awk`/`shasum` recipe the Bash-and-SQL-only rule forbids, a missing `cost` stage in the 17 script's stage list, a documented-but-unread `KEEP` variable, `listen_addresses`/`port`/`logging_collector` written without apply scopes, `psql` helpers without `ON_ERROR_STOP`, an unguarded `rm -rf "$SANDBOX"`, missing page and checkout preconditions, unmarked disposable fixtures, and the undocumented positional dependency of `md_block sql N` on the page's fenced-block order. Four script-scope open questions were filed, including that the repaired scripts have not been re-run. On 2026-09-10 both scripts were re-run end to end, twice, from an empty sandbox on Darwin arm64 under the repaired text, reproducing every verdict count of the Linux run (`make check` 225 of 225 and 192 of 192; 2 min 26 s and 1 min 52 s for the two legs), after the `stop` stages were repaired from `pg_ctl -m immediate` to `-m fast -w` with a confirmed teardown; that closed two of those questions and opened one on the attribution row count, 31 per direction against the filed 26. Later that day the last commit's script changes (a server-error check and build-log copies) were reviewed with both legs re-run under that text on Darwin arm64 (clean runs pass, a restart adds nothing counted, one injected stray error per leg fails the checking stage) and six script defects were filed as proposed repairs without changing the script text. The six were then repaired in the script text without a re-run, at the asker's instruction, so the filed numbers predate the script text now filed., and a filed COMMENT-stored baseline B-tree index-maintenance heuristic for versions 12 through 17: two texts (a read-only plan statement and a top-level `DO` block) that execute unmodified on both 12.2 and 17.11, an 86-byte `@btmaint:` v2 payload in the index's own comment as the only persistent state, a three-part gate of 20% index growth, 20% movement either way in the table's `reltuples` or 20% movement either way in the index's own `reltuples`, and a rebuild decision above 40% wasted space measured against the index's own fillfactor; re-ported on 2026-09-14 to the mandatory suite as the concept page defines it, which deleted tests 11, 38, 65, 67, 69, 106, 117 and 121 and legs 113a and 113c with their recipes and, at the asker's direction, removed every page-local acceptance fixture, and then **re-run end to end on 2026-09-16** as the first pass under that page's maintenance assumption in full and under `### The maintenance must not be defeated`, the rule it gained on 2026-09-15 - the second consumer page brought onto that rule - closing the departure the previous pass had recorded: a maintenance step now runs `VACUUM (VERBOSE, ANALYZE)` on every table the churn touched, the set computed from the engine's own `pg_stat_all_tables` write counters rather than listed (66 tables on 17.11 and 65 on 12.2, removing 18,066,916 and 17,617,051 dead tuples in 6.4 s and 6.9 s), while every churn-free table is deliberately left alone so that family 3's stale statistics survive; the rule's four proofs are recorded per table, every statement completed with `dead but not yet removable` 0 on all 66 and all 65, 69 of 69 and 68 of 68 horizon probes entirely clean with 0 replication slots and 0 prepared transactions, 0 skip or cancellation lines in either log, and page classes of 10,340 and 11,868 deleted pages, with every `VACUUM`/`ANALYZE` session forcing its four timeouts to 0 as an autovacuum worker does to itself where the previous run left `lock_timeout = '5s'` in the churn sessions; neither filed text changed and the score did not move, `PASS` on 125 of 126 fixtures on 17.11 with 1 `UNMET PRECONDITION` and 112 of 112 on 12.2, 0 false negatives, 0 false positives of either severity, 0 gate disagreements against independently recomputed arithmetic, 8 of 8 false-positive constructions never rebuilt, 95 and 81 rebuilds at a mean 86.2% and 87.1% measured reclaim, 126 of 126 and 112 of 112 stored index counts equal to the catalog's, and a mean reading error of `+7.6` points over 103 scored measurements; what the maintenance step did change is the four threshold-calibration controls whose trailing `UPDATE` nobody had vacuumed, `b93` and `b95` under-reading the oracle by 9.4 points instead of 18.2; the clean sheet is still the suite narrowing rather than the method improving, since the fixtures this method fails are the retired dead-but-unvacuumed ones and the page files that as its first open question; the third gate still opens 20 fixtures on 17.11 and 19 on 12.2 that two gates would skip, 15 of them genuinely bloated at a mean 86.7% and 86.3% reclaim; rule 3's census now decides only the tables no churn touched, 12 of 88 and 4 of 87, with 12 of 12 and 4 of 4 counters verified reset from a later session; fixture 120's precondition is asserted rather than assumed after the previous run credited it a `PASS` it had not earned, and over four complete passes its post-census estimate read 2,034 / 1,667 / 0 / 1,800 / 1,600 on 17.11 and 0 / 13,335 / 3,334 / 0 / 0 on 12.2, so its state arrived on 4 of 10 fixture builds; three harness defects were fixed (the missing precondition check, a publication invariant that mistook a recipe's own `ANALYZE` for an unpublished counter, and a `check` stage that wrote into a directory that did not exist from a built tree), 125 of 126 and 112 of 112 per-fixture result tuples match the preceding pass on a separate cluster from the same pin, and the harness's server-error check, repaired on 2026-09-14 after being found unable to match the default `%m [%p] ` log prefix, reports 4 logged and 4 deliberate on 17.11 and 8 and 8 on 12.2; and the eleven measurement losses the page-local removals cost - comment parsing and preservation, the candidate filters and their refusals, the gate boundaries, the unknown-count states, the threshold curve, comment survival across both `REINDEX` forms, privileges, the `COMMENT` lock, dry runs, idempotence and `pg_dump` - are each named under Open Questions; the wiki's first common concept page, [Mandatory B-Tree Bloat Tests](v17/common-concepts/mandatory-btree-bloat-tests.md), now holds that suite's shared definition source-only - 113 numbered tests in six families after the 2026-09-12 removal of the withheld-maintenance fixtures and explicit deduplication controls, the five phases, the three porting rules including the engine-driven simulated auto-analyze, the measured-`REINDEX INDEX` oracle, the four verdict bands, a per-family fixture catalogue tied to the v17 behavior each targets, and six named limits - so the heuristic page keeps its measurements and deviations and stops restating the protocol; the estimator page [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17](v17/questions/indexing/btree-index-bloat-core-sql-only.md) stopped defining that suite on 2026-09-11 too, was re-scored against it on both legs, and was re-ported to it on 2026-09-14 after the retirements and the maintenance assumption: the scored population is now **126 fixtures on 17.11 (25 in the gate, 101 numbered) and 13 on 12.2**, reading 91 `PASS`, 4 critical false positives, 0 false positives and 31 false negatives on 17.11 and 11 `PASS` with 2 false negatives on 12.2, still with **not one false negative lost to the threshold** - 22 withheld by an exclusion term, 8 under the 1 MB report filter and 1 behind a caveat, on files a rebuild emptied by a mean 83.3%, 86.3% and 100.0% - `expected_stage` agreeing with the statement on all 101, 0 build-contract failures, 0 unexpected server errors, rule 3's census analyzing only 2 of 86 tables because the maintenance step had already analyzed every churned one, and the page's page-local geometry, calibration and acceptance fixtures deleted with the claims they backed; the page's older number-only bands shown beside the shared ones (91 `PASS` / 12 critical / 6 false negatives on the same rows, 8 of the 12 on rows the report never shows); on 2026-09-13 the concept page gained the maintenance assumption at the asker's direction - `VACUUM ANALYZE` on every churned table before the decide phase, with the launcher's vacuum and insert-vacuum thresholds recorded from the pin but not applied - and files its cost on fixtures 92 to 95 and 118 as open questions, and a second common concept page, [Mandatory GIN Bloat Tests](v17/common-concepts/mandatory-gin-bloat-tests.md), which is protocol-scoped rather than corpus-scoped: extracted on 2026-09-15 out of the GIN contrib-extensions question page, it fixes the five phases, the settle step and its proof obligations, the `SHARE ROW EXCLUSIVE` measurement lock, the `REINDEX INDEX` oracle bracketed by `pg_relation_size(index, 'main')`, the declare-a-bound-before-the-run rule, the four cross-checks and the reading rules, while deliberately defining no fixture corpus; on 2026-09-15 that page also took every autovacuum, VACUUM, ANALYZE and auto-analyze rule from its B-tree sibling as binding protocol - a three-part maintenance assumption ending each churn in `VACUUM ANALYZE`, the launcher's three threshold formulas recorded with their GUC contexts and reloption precedence but not applied, and a simulated auto-analyze census with two statistics-publication points - and resolved the one place the port could not be a copy, since `analyze_rel` reaches ANALYZE-only index cleanup only outside a `VACUUM ANALYZE` and names GIN as the only core AM that is not a no-op there, so the auto-analyze-only state is stood in for by `ANALYZE` plus `gin_clean_pending_list()` with three differences named and a stale metapage census by construction, and a third common concept page filed on 2026-09-15, the mandatory non-B-tree, non-GIN bloat tests, which scores hash, GiST, SP-GiST and BRIN under one protocol plus an admission rule for a non-core AM, carries over every autovacuum, VACUUM, ANALYZE and auto-analyze assumption from the B-tree page, and adds the two things those assumptions mean here - a BRIN maintenance step that summarizes every unsummarized range and therefore grows the index, with a `brin_summarize_new_values()` stand-in for the worker-only autosummarize work item, against an auto-analyze stand-in that is a plain `ANALYZE` because all four AMs no-op in ANALYZE-only mode - beside a per-AM instrument matrix in which `pgstattuple` refuses SP-GiST and BRIN, `pageinspect` has no SP-GiST decoder at all, and no `amcheck` verifier exists for any of the four, and the COMMENT-stored non-B-tree inflation heuristic was re-run end to end on 2026-09-15 under **both** protocols from one published 2,364-line script: 31 scored fixtures across all five access methods, the decision right on **30 of 31** with no false positive and one false negative created by `VACUUM (INDEX_CLEANUP OFF)`, the declared `est_reclaim_pct` upper bound violated on 12 of 31 and therefore **demoted to a level**, both auto-analyze stand-ins producing a refusal because `vacuum_count` never moves, all four BRIN fixtures reclaiming 0 bytes with three of them **grown** by the mandatory maintenance step, a hash rebuild shown to be sized from the heap's estimate and a GIN rebuild from `maintenance_work_mem`, and the old 13-cell matrix, its pre-`VACUUM` evaluation and its six-run reproducibility claim removed with the claims they backed; on 2026-09-15 all three bloat-protocol concept pages also gained one shared rule, `The maintenance must not be defeated`, after a review found they enforced issuing the maintenance but never its effect: five forbidden states (a held snapshot or open transaction other than a lazy `VACUUM`, a prepared transaction, a replication-slot `xmin`, a lock conflicting with `ShareUpdateExclusiveLock`, and a `statement_timeout`/`transaction_timeout`/`lock_timeout` that can fire inside the maintenance statement), a per-fixture proof obligation, and the declared exceptions each page's own coverage already requires; on 2026-09-24, at the asker's request, the GIN and non-B-tree protocol pages stopped requiring a `VACUUM` whose index cleanup did not run and stopped declaring that fixture an exception, and now name it as a limit; plus a measured walkthrough of a very large `shared_buffers` on a 1 TiB-class host, reviewed against 16 listed defects and re-measured on 2026-09-17 under a **4 GiB cap on every `shared_buffers` its script may name**, in a running server and in a non-allocating `postgres -C` probe alike, so nothing is measured above 524,288 buffers and every 256 GiB figure is arithmetic on a model of the pinned sizing formulas fitted to four segments measured exactly in bytes from `pg_shmem_allocations` (**267,499 MB** and **133,750** 2 MiB huge pages at 33,554,432 buffers, all three fit checks off by one constant 8 kB page; a marginal cost of 8426-8451 that decomposes into 8292 + 32 + 40 + **64.94 of still-growing SLRUs** which cap at exactly `NBuffers = 524,288`; and a 257 MiB bucket-array step measured at 2^18 and computed at 2^25), with slopes of **11.0 ns/buffer** per whole `CHECKPOINT` over a pool proved clean (0 dirty, 0-6 written per six), **71 ns/buffer** of server start from minima over ten restarts each, and **6.6**/**9.6 ns/buffer** per `DROP`/`TRUNCATE` at `synchronous_commit = off` - the last unavoidable on a primary because `smgrnblocks_cached()` answers only `InRecovery`, and then only for relations under `NBuffers / 32` blocks - together with the `NBuffers / 4` bulk-read line (32 resident blocks against 18,692, 0 evictions), the `NBuffers / 8` ring cap read back at exactly 16,384 main-fork blocks against a 16 GiB setting maximum, 17.6's 10,000,000-slot checkpointer queue cap and its `e4b8f925a929` autoprewarm allocation fix, the PostgreSQL 13 commit `6d05086c0a79` that made one pool pass cover every fork (measured 1.15x, not 3x, for three forks), and a 24-row since-v12 delta table, and an integer-to-bigint column-widening walkthrough measured on both 17.11 and 12.2 from one published two-leg script: the rewrite is mandatory because `pg_cast` records a function cast, and it costs the old heap once plus the new heap once per index rebuild (**72,413** blocks = 25,469 + 2 x 25,536), **427,512,848** bytes of WAL against 12.2's **484,674,144**, a **+327,442,432**-byte disk peak returned at commit and **3,951 ms** of `AccessExclusiveLock`, while the same bytes took **4,576** read calls on 17.11 against **72,373** on 12.2 and a controlled pair read 341 against **5,407** at `io_combine_limit = '8kB'`; plus **111,148,848** bytes of WAL for a 417,792-byte heap with a 109 MB TOAST table, one seq scan over all **8,850** pages of a foreign-key child whose `conpfeqop` became `{416}`, row growth of 0 or 8 bytes but never 4, `wal_level = minimal` at 161,016 bytes against 26,315,416 with `wal_skip_threshold = '4GB'`, and an add-column/backfill/CIC/swap alternative that cut the exclusive lock to a **305 ms** window for **1,634,508,136** bytes of WAL and a 2.15x heap, and a scoring of the `pgstatindex` `REINDEX_SCORE` B-tree maintenance heuristic on 17.11 and 12.2 from one two-leg published script, where the score - `(deleted_pages + empty_pages + leaf_pages * max(0, 1 - avg_leaf_density / fillfactor)) / (index_size / block_size)` against the index's own `fillfactor` - tracks a measured `REINDEX INDEX` to **0.94** and **0.75** points of mean absolute error over 125 and 116 deterministic fixtures of the shared mandatory B-tree bloat suite (0.99 on 17.11 with the probabilistic test 120 included, whose precondition the latest 12.2 run did not meet), at 0.999 correlation, with no false positive and no false negative at a 50 % cut, and where the residual decomposes into an exact three-term identity whose internal term pulled the score down on every fixture measured and whose leaf term cannot be negative wherever a rebuild keeps the leaf count; re-measured 2026-09-21 on Darwin arm64 with the error decomposition, an `i_alldel` guard fixture and an in-run unguarded baseline added, establishing that a `NaN` `avg_leaf_density` means a metapage-only file and nothing else - nbtree never deletes a rightmost page - so the statement's two `CASE` guards agree on every index that can exist and together withdraw 138 of 233 and 133 of 219 rebuild orders that no rebuild could have paid for, while by the suite's own bands every threshold from 35 % to 65 % on 17 and 35 % to 70 % on 12 is equally admissible because no fixture's rebuild lands between 49.9 % and 60.0 %, and a COMMENT-stored non-B-tree maintenance heuristic for 12 through 17 whose two tests - index size up 30 %, table `reltuples` moved 30 % either way - score 22 / 7 / 0 (pass / false positive / false negative) on 17.11 and 22 / 6 / 0 on 12.2 against a measured `REINDEX INDEX` over the non-B-tree inflation page's fixtures less the two `INDEX_CLEANUP OFF` ones the asker removed, 29 on 17.11 and 28 on 12.2, every false positive being legitimate growth, with the no-defeat rule enforced by a run that dies rather than scores; revised the same day for twelve reported defects - sandbox containment, failure propagation and build provenance in both scripts, step 2 locking and re-deciding under `REINDEX INDEX`'s two locks, a whole-line payload grammar, an attempt-counting rebuild cap, count-by-count `VACUUM VERBOSE` and page-by-page BRIN free-space cross-checks, and unrounded scoring - and re-measured with the same scores, 18 of 18 invariants and 158 of 158 edge-case verdicts on each leg; filed 2026-09-23, a B-tree leaf-density versus fragmentation comparison of index scan I/O, measured on 17.11 from a published script: density moves buffer counts and plan cost by the page count, order moves neither, no B-tree read path prefetches or stream-reads, and `synchronous_commit = off` still keeps visibility-map bits off; revised 2026-09-24, the GIN contrib waste page: the index-cleanup-disabled fixture `f9c_cleanup` removed, four script defects fixed, a 12.2 portability script added, and both legs re-run on Darwin 27 arm64, reproducing every scored cell of the 2026-09-16 filing; revised 2026-09-24, the COMMENT-baseline GIN heuristic page: the index-cleanup-disabled fixture `i01` removed, three script defects fixed, and the script re-run on Darwin 27 arm64, reproducing every scored cell of the 2026-09-17 filing except `c02`'s sample-decided bound; revised 2026-09-24, the COMMENT-stored non-B-tree inflation page: the two index-cleanup-disabled fixtures `h06` and `n11` removed, two coverage rows it had filed as reached refiled as not reached, three script defects fixed, and the script re-run on Darwin 27 arm64, reproducing every recommendation, decision and bound verdict of the 2026-09-16 filing on the 29 fixtures kept; revised 2026-09-24, the non-B-tree COMMENT-baseline maintenance heuristic page: the two coverage rows both leg scripts still declared for the index-cleanup-disabled case removed, every census reading now written to `meas.csv`, and both legs re-run on Darwin 27 arm64, reproducing every decision, score, prediction and invariant of the 2026-09-22 filing |
| 14 | active | [v14/index](v14/index.md) | `REL_14_STABLE` | `a92fbdfb830046e907813e9067b2c9de9708d600` | Behavioral claims cite the matching pinned checkout under `raw/postgres-14/`; source version 14.24, pinned to the `REL_14_STABLE` tip `a92fbdfb830` (`REL_14_24-6-ga92fbdfb830`, six commits past the 14.24 release stamp; repinned from 14.23 `5c00f4e2e3b` on 2026-08-17). Filed coverage so far is the mandatory codebase navigation guide: source-tree layout from the top-level and backend makefiles, the normal SQL statement path through `tcop`/rewrite/planner/executor (`exec_simple_query` -> `pg_parse_query` -> `pg_analyze_and_rewrite`/`QueryRewrite` -> `pg_plan_queries`/`planner` -> `PortalRun`/executor entry points), utility-command dispatch via `ProcessUtility`, generated catalog/header artifacts (backend `generated-headers` target, the backend catalog `generated-header-symlinks`/`genbki.pl` path, and the `pg_index.h` catalog header), key parser/planner/executor/relcache/AM data structures, and contrib and test/doc surfaces. Filed question coverage adds a Row-Level Security walkthrough: RLS as a rewrite-time feature (`pg_policy` storage, `relrowsecurity`/`relforcerowsecurity`, relcache `rd_rsdesc`, `check_enable_rls` bypass logic, `get_row_security_policies` security-barrier `USING` quals and `WITH CHECK` options, permissive-OR/restrictive-AND with default-deny, the planner `security_level`/leakproof ordering, executor `ExecWithCheckOptions`, plan-cache `dependsOnRLS` re-planning, partition/inheritance and view-owner handling, generated catalog/header implications, and COPY/CTAS/whole-table/RI/logical-replication/error-detail boundaries), its source-evident scalability/performance issues (including a dedicated RLS-and-the-plan-cache section: RLS-aware plan caching keyed on role + `row_security`, where 14.24's `PlanCacheRoleCallback` (CVE-2026-14666, `f4174aa84a3`) now invalidates role-dependent saved plans on `pg_auth_members`/`pg_authid`/`pg_database` changes, closing the former same-role membership, `INHERIT`, `BYPASSRLS`, `SUPERUSER`, intermediate-role, and database-owner staleness window for saved plans, with `DISCARD PLANS` retained as a blunt manual reset, the role-independent relcache `rd_rsdesc` policy cache, the scenarios where caching does not help — role/`row_security` mismatch at reuse, the never-applicable simple-validity fast path, un-cached simple-protocol and one-shot SPI queries, the conditional first-five custom-plan opportunities, DDL invalidation — and the no-cache re-analyze/rewrite/re-plan cost; a query-vs-policy planning subsection showing RLS policy conditions need not be restated in the query — `USING` quals are transferred into `baserestrictinfo` at ordered security levels (the first sublist is level 0; restrictive quals precede the permissive OR in mixed sets), safely promotable clauses can match indexes, partition pruning sees the full restriction list, and query-text copies land at the maximum security level; a sub-SELECT-wrapping subsection showing that wrapping an uncorrelated function call in a scalar `(SELECT ...)` (e.g. `(SELECT auth.uid())`) can make each generated InitPlan occurrence lazy, at most once per execution, and cached in a `PARAM_EXEC` parameter, avoiding repeated function-expression work when the unwrapped expression would remain a per-tuple filter, with caveats (only uncorrelated sub-SELECTs qualify, exact index runtime keys can avoid per-row calls but lossy paths recheck, and rewrite copies and separate occurrences are not generally memoized together); an RLS-and-aggregation mitigation section showing that `Agg` nodes consume RLS-filtered subplans and mitigations focus on indexable policy predicates, leakproof/indexable filters, partition pruning/partitionwise aggregation (`enable_partitionwise_aggregate` is session-scoped), stable plan-cache environments, or deliberately trusted/pre-aggregated reporting paths; plus the FK-validation/two MultiXact paths (policy-authored `FOR SHARE` locking subqueries and RLS-induced FK validation fallback) where RLS disables the bulk RI path and per-row `FOR KEY SHARE` checks can create/read MultiXacts on hot referenced rows), and the RLS control/inspection surface (`row_security`, general `plan_cache_mode` and aggregation-adjacent `enable_partitionwise_aggregate` scopes, table flags, `BYPASSRLS`, policy options, extension hooks, `row_security_active`, catalog/psql views, and pg_dump/pg_restore controls), with explicit core/hook test coverage. Filed question coverage also adds a MultiXact walkthrough: how MultiXact backs shared row locks (a `MultiXactId` in `xmax` for a set of `(xid, MultiXactStatus)` members, the offsets/members SLRUs under `pg_multixact/`, `MultiXactStateData` + per-backend oldest arrays, the `MultiXactIdCreate`/`Expand`/`CreateFromMembers` -> `GetNewMultiXactId`/`RecordNewMultiXact` write path, and the `GetMultiXactIdMembers` read path), the backend-local 256-entry per-transaction LRU cache whose tail eviction only frees memory rather than spilling an entry (`mXactCacheEnt`/`MAX_CACHE_ENTRIES`/`MXactContext`/`mXactCachePut`), and the separate miss path through the shared 8-offset/16-member SLRU pools to a possible filesystem `pg_pread`/`SLRURead` that may still hit the OS page cache; the distinction between system-wide MXID/member allocation and one backend's cache pressure; foreign keys (RI `FOR KEY SHARE` -> `heap_lock_tuple` -> `compute_new_xmax_infomask`, including null/partition/committed-updater edges), compatible explicit locks, UPDATE/DELETE/update chains, executor/trigger/logical-apply callers, and exact VACUUM replacement branches; three degradation paths (hot-row/full-member-array creation work, exclusive SLRU control/per-buffer/file-I/O waits after cache misses, and ID/member growth driving aggressive vacuum plus separate hard stops); observability (`pg_stat_slru`, exact generated wait names, `mxid_age`, targeted member decoding) with attribution limits; the four vacuum GUC scopes (three `PGC_USERSET` settings and restart-only `autovacuum_multixact_freeze_max_age`), per-table autovacuum MultiXact reloptions, build/generated/WAL/tool/contrib boundaries, verified diagnostic SQL, the seven MultiXact isolation specs passing on the previous 14.23 pin, and explicit cache/SLRU performance-test absence. Filed question coverage also adds a fully source-reviewed functions/procedures-in-a-WHERE-clause performance walkthrough: procedures (`prokind='p'`) are rejected in expressions and run through utility `CALL`, whose arguments still use standalone expression evaluation; set-returning, aggregate, and window functions are also rejected directly in `WHERE`; scalar residual quals scale with candidate scan tuples or join pairs, subject to short-circuiting, `STRICT` null skips, SQL inlining, constant folding, pseudoconstant gating and rescans, and index runtime-key placement; the volatility effects (`VOLATILE` per row where needed, `STABLE` single-eval as an index-scan runtime key or no-`Var` one-time qual, `IMMUTABLE` constant-folded with constant args), the cost model (`add_function_cost` = `procost * cpu_operator_cost`, with omitted `CREATE FUNCTION COST` defaults of 1 for C/internal functions and 100 otherwise) and bare-Boolean-function fallback selectivity (`function_selectivity` 0.3333333), the narrower no-statistics `boolvarsel` 0.5 fallback, and expression-index/extended-expression statistics, plain-index search-key limits, expression-index/generated-column matching, post-planning immutability checks, non-volatile runtime keys, and support-generated index conditions, the separate leakproof security-promotion/index-pushdown rule and same-node `< 10 * cpu_operator_cost` ordering cutoff, plus `PARALLEL UNSAFE`/`RESTRICTED` plan effects; plus the mitigations (reduce candidate tuples/pairs, expression indexes/generated columns or estimate-only expression statistics, uncorrelated scalar sub-SELECT -> lazy once-per-execution InitPlan, truthful volatility/`STRICT`/`COST`, SQL-function inlining, planner `SUPPORT`, truthful `LEAKPROOF`/`PARALLEL SAFE`, and measured JIT/function tracking), with `ROWS` explicitly excluded for direct WHERE functions; generated `pg_proc_d.h`, fmgr/contrib-`sepgsql`, extension-bitcode, GUC-scope, and regression/absence boundaries are included; the RLS page is agent-verified by `GPT-5` at `2026-07-20T18:13:13Z`, the functions/procedures page at `2026-07-13T19:41:59Z`, and the MultiXact page at `2026-07-13T20:08:07Z`; only the codebase navigation guide remains `not yet`. The 2026-08-17 repin from 14.23 `5c00f4e2e3b` to 14.24 `a92fbdfb830` reviewed all 133 commits in the range. Claim-changing commits: `f4174aa84a3` (CVE-2026-14666) registers `PlanCacheRoleCallback` on `pg_auth_members`/`pg_authid`/`pg_database`, which closes the former same-role RLS plan-cache staleness window for saved plans; `1a358b8f2a2` (CVE-2026-6470) requires `USAGE` on types used by policy, index, default, CHECK and partition-key expressions; `155dacbc547` (CVE-2026-14680) rejects calls to functions taking or returning type `internal`; `802dc79df63` removed replication-slot advice from the MultiXact wraparound hints and documented that slots do not hold back multixact cleanup; and `2bb60eb4fea` moved `RecordNewMultiXact()`'s SLRU lock acquisition later to fix a replay self-deadlock. Nothing was re-measured on 14.24, so previous-pin measurements are labelled as such. |
| 12 | legacy | [v12/index](v12/index.md) | `REL_12_STABLE` | `45b88269a353ad93744772791feb6d01bc7e1e42` | Behavioral claims cite the matching pinned checkout under `raw/postgres-12/`; the reviewed mandatory codebase navigation guide covers build ownership, backend/standalone entry, simple and extended protocol including Sync, parse/analyze/RIR rewrite/planner/portal/full executor flow, utility and error boundaries, generated catalog/parser/fmgr/LWLock artifacts, core hooks, packaged extensions, custom AM registration/dispatch/tests, key data structures, and test/doc surfaces; filed coverage includes two `CREATE INDEX CONCURRENTLY` performance follow-ups: a `maintenance_work_mem` analysis (AM-dependent first-build and common validation-sort uses, B-tree planned-versus-launched participant shares and required tape runs, conditional GIN cleanup, BRIN's empty enumeration, GiST's buffered temporary-file path, scoped observability, and the workload-specific plateau) plus a broader CIC GUC matrix (B-tree worker request and pool limits, AM-specific settings, v12 heap-scan and storage boundaries, WAL/checkpoint/commit costs, waits/timeouts, exact apply scopes, absent later-version controls, and commonly confused non-controls), foreign-key join selectivity, partial-index pros/cons with ordinary expression indexes as the baseline, partial expression indexes, planner predicate implication, expression-key matching, operational restrictions, `ANALYZE` row-count and expression-statistics behavior, planner costing, and regression coverage, a source-reviewed declarative-partitioning indexing comparison (`CREATE INDEX ON parent` versus independent leaf indexes; storage-less parent and unchanged leaf scan candidates, hierarchy pre-locking, concurrent rollout, parent constraints and targeted `ON CONFLICT`, untargeted `DO NOTHING` with independent leaf indexes, matching-field limits rather than identical definitions, owning-constraint drops, DETACH child/default-partition locks, separate INSERT/UPDATE/planning index-opening paths, and invalid-leaf adoption without parent invalidation during table attachment), including data structures, generated catalog/parser headers, extension boundaries, regression evidence and explicit source-only measurement gaps, a fully reviewed planner-statistics-source analysis (`pg_stat_all_tables`, `pg_stats`, and `pg_stats_ext` excluded as direct feedback; `pg_class` plus physical size, `pg_statistic`, built extended data, ordinary/partial index sizing, inherited/expression statistics including partial-index correlation, defaults/security/errors, indirect auto-analyze and planner endpoint counter increments, estimate/cost metadata, AM/FDW/hook/contrib/generated-cache boundaries, and direct tests included), `EXPLAIN (ANALYZE, BUFFERS)` output, `pg_stat_statements` mechanics and configuration, a production database-health checklist covering observability prerequisites and apply scopes, activity/connections/locks, cumulative database and table counters, vacuum and wraparound, checkpoints, WAL archiving, replication, checksums, query and relation diagnostics, and database-log issue interpretation, `psql` environment variables and session timeout behavior, reviewed full non-snapshot `pgstatindex` behavior (extension install/API and privileges, true-root metadata, one-time main-fork scan, half-dead/deleted/live classification, size/density/fragmentation formulas and two-decimal formatting, physical `LP_DEAD` occupancy, concurrency and integrity-check limits, generated-header boundary, and test gaps), planner penalties for bloated B-tree indexes through physical pages and tree height including the storage-manager path and I/O/CPU boundary for `RelationGetNumberOfBlocks()`, a proposed `avg_leaf_density` / `leaf_fragmentation` triage heuristic for REINDEX candidates, B-tree leaf density (60% vs 90%) impact on planner page-count costs and executor leaf-page walking, now fully reviewed at the pin with exact-pin measurements (2733 versus 4116 leaf pages, 2738 versus 4121 warm index-only scan buffers, a 5552.01 cost gap equal to 1388 extra blocks at `random_page_cost = 4`, an unchanged probe cost on narrow keys against a wide-key fixture where 90-to-60 raised `tree_level` from 2 to 3, and a random-insert index that reached 65.58% density with no deletions), a density-versus-fragmentation comparison for index scan I/O with level estimates and cache/storage sensitivity, and a three-stage REINDEX triage heuristic that shortlists candidates from `pg_class`/`pg_stat_*`/`pg_relation_size()` signals, confirms density with gated `pgstatindex` runs, prioritizes by configured-fillfactor reclaimable pages times paired-window scan rate with `REINDEX (CONCURRENTLY)` execution notes, measures post-REINDEX improvement via size/shape deltas, per-scan counter rates (per-index plain REINDEX keeps its OID while concurrent REINDEX copies the published collector entry, with pending-count continuity treated as an open boundary, including the v12 `index_concurrently_swap` stats copy), and `EXPLAIN (ANALYZE, BUFFERS)` / `pg_stat_statements` before/after windows, and documents the cited rationale for excluding `leaf_fragmentation` from the REINDEX priority score, and a comprehensive walkthrough of the `CREATE INDEX CONCURRENTLY` implementation in `DefineIndex` (four internal transactions, two heap scans, three deliberate transaction-set waits, the `indislive`/`indisready`/`indisvalid` progression set non-transactionally by `index_set_state_flags`; the reviewed CIC page now also covers parser/utility/generated-catalog artifacts, the core-vs-index-AM/contrib-Bloom boundary, four deliberate transaction barriers versus additional event-trigger/predicate/AM/unique-validation/parallel-worker waits, temp and `IF NOT EXISTS` early-exit ordering, a post-`SET_VALID` `ddl_command_end` failure that leaves a valid index, and crash durability scoped to reviewed in-tree AMs rather than arbitrary third-party callbacks; it also retains the preconditions/restrictions and full failure-state coverage, and a dedicated steps-and-locks section covering transaction- and session-level `ShareUpdateExclusiveLock`, the `WaitForLockers(ShareLock)` writer waits, `WaitForOlderSnapshots`, and the `LockConflicts` rationale for why DML proceeds while another CIC/`VACUUM`/`ANALYZE`/DDL is blocked, plus a reviewed blocker-by-blocker enumeration of the four deliberate core transaction barriers separately from additional event-trigger/predicate/AM/unique-validation/parallel-worker waits; the four barriers cover conflicting-lock holders at acquisition with the autovacuum-cancel and prepared-transaction nuances, open writers at the two lock waits, and same-database old-snapshot holders at the snapshot wait, with the `pg_stat_progress_create_index` wait phases and worked examples for a running `pg_dump` and an hour-long open / idle-in-transaction session, plus a failure-scenarios section mapping each CIC phase to the leftover on the table — no index, an invalid not-ready index, an invalid ready index that still takes writes and enforces uniqueness, or a valid index after a post-`SET_VALID` command-end error — with each leftover's planner/write/uniqueness/HOT cost, session-lock release on ordinary ERROR/cancel paths, a resolved crash/immediate-shutdown recovery outcome (xidless `heap_inplace_update` flag flips commit asynchronously and are redone by `heap_xlog_inplace`, so recovery lands on one of the four documented leftovers without losing completed in-tree build data while retaining a later durable `SET_VALID`; this crash-durability result does not repair the separate prepared-transaction gap or prove arbitrary third-party AM callbacks), `DROP`/`REINDEX` recovery), a companion comprehensive walkthrough of the v12 `REINDEX INDEX CONCURRENTLY` implementation with a source-backed GUC-performance follow-up covering AM-dependent build/validation memory, B-tree-only worker controls, v12 bulk-read/synchronized-scan boundaries, temporary and fixed output storage, B-tree immediate sync plus WAL/checkpoint/commit costs, all five timeout-sensitive waits, exact apply scopes, absent later-version controls, and commonly confused non-controls in `ReindexRelationConcurrently` (its six phases — create the `_ccnew` copy, build, validate, swap, set-dead, drop — and five wait points, namely the three shared CIC waits plus two extra `AccessExclusiveLock` "wait for readers" waits before marking the old index dead and before dropping it; the atomic `index_concurrently_swap` that marks the new index valid and the old invalid, renames `_ccnew`→original and original→`_ccold`, and moves constraints/triggers/comment/dependencies and per-index cumulative stats; `ShareUpdateExclusiveLock` held at transaction and session level on the old index, new index, and heap; the no-transaction-block/temp-fallback/system-catalog/partitioned/exclusion/invalid restrictions and toast rebuild; the two-index state-flag progression; a per-phase failure table leaving an invalid `_ccnew` before the swap or `_ccold` after, with regression evidence; multi-index batching; and the source-vs-view progress-phase discrepancy where phase 6 reports `WAIT_4` so `waiting for readers before dropping` is never emitted), and an analysis of whether `ALTER TABLE ... ATTACH PARTITION` can drop indexes from the attached table (it cannot: `AttachPartitionEnsureIndexes` is strictly match-or-create via `IndexSetParentIndex`/`DefineIndex`, incompatible/extra indexes are kept, no `performDeletion`/`RemoveInheritance` runs in the attach path and the pre-index `CreateInheritance` merges CHECK constraints only; v12's looser matching — no `indisvalid` skip, existence-only constraint check — still never drops; covering the three look-alikes, the `ALTER INDEX ... ATTACH PARTITION` re-parent/error path, and the docs' plain-`CREATE INDEX` pre-build workflow), and a comprehensive enumeration of all outcomes that leave an invalid index (`indisvalid=false`) derived from the full set of `indisvalid=false` writers in the checkout: a failed/cancelled/crashed `CREATE INDEX CONCURRENTLY`, a failed `REINDEX CONCURRENTLY` (`_ccnew`/`_ccold`), a failed/interrupted `DROP INDEX CONCURRENTLY` (retryable clear-valid step), an incomplete partitioned parent (`CREATE INDEX ON ONLY` / attached invalid child, validated by `validatePartitionedIndex` on `ATTACH PARTITION`), and `pg_upgrade` from <= 9.6 invalidating hash indexes in the new cluster, with the persistent state table, the single-transaction-DDL contrast, the planner/executor/VACUUM cost and the commands that reject invalid indexes, and per-outcome repair, and the partitioning optimizations and configuration during query planning and execution (partition pruning plan-time before child expansion in `expand_partitioned_rtentry` and run-time initial + per-scan pruning on `Append`/`MergeAppend`, with per-strategy HASH/LIST/RANGE bound-matching and tuple routing; constraint exclusion `relation_excluded_by_constraints` modes for legacy inheritance; partitionwise join `build_joinrel_partition_info`/`have_partkey_equi_join` and partitionwise aggregate `group_by_has_partkey`; executor tuple routing, cross-partition UPDATE row movement, and per-partition COPY multi-insert; the four session-scoped GUCs with defaults; and the v12 limitation that execution-time pruning covers only `Append`/`MergeAppend`, not `ModifyTable`; plus a follow-up locking/random-I/O analysis per optimization: only plan-time pruning removes read locks (it prunes before `expand_partitioned_rtentry` locks partitions, while `find_all_inheritors` locks all inheritance children before constraint exclusion runs and `AcquireExecutorLocks` locks every plan-time-surviving partition despite run-time pruning; write-path routing takes `RowExclusiveLock` lazily per touched partition), and the scan-eliminating optimizations gain most on slow random storage because avoided per-partition index heap fetches are priced at `random_page_cost` = 4× `seq_page_cost`, whereas partitionwise join/aggregate cut CPU/memory/locality (v12 costs hash-join spill as sequential and keeps hash aggregation in memory)). Filed coverage also includes a fully reviewed `plan_cache_mode` analysis: the enum/`PGC_USERSET`/`GUC_EXPLAIN` definition and its session/transaction apply scope, the eight ordered rules in `choose_custom_plan` with `force_generic_plan`/`force_custom_plan` sitting behind the one-shot, no-parameter, and transaction-statement rules, the `auto` cost comparison and its custom-only `1000 * cpu_operator_cost * (nrelations + 1)` planning charge, the `GetCachedPlan` correction step, `PARAM_FLAG_CONST` folding and the `var_eq_const`/`var_eq_non_const` selectivity split, the `CachedPlanSource` heuristic fields and every caller that reaches the decision, cost-history retention across invalidation and `DISCARD PLANS`, the per-execution `AcquireExecutorLocks` footprint of a generic plan, v12 observability limits and error paths, build/extension boundaries, the single direct regression test with explicit gaps, and five ancestor commits from `e6faf910d75` to `ca0b3828504`; fourteen exact-pin measurements reproduce the execution-6 switch, the cached-but-unexecuted generic plan, the ignored `force_*` overrides, PL/pgSQL static versus dynamic behavior, `pgbench -M prepared` versus `-M extended`, 2 versus 5 partition locks, and 0.65 ms versus 0.006 ms of planning per execution. B-tree coverage now also includes a core-SQL-only bloat measurement proposal that models the size a rebuild would produce from v12's own `_bt_buildadd` fillfactor rule and subtracts it from `pg_relation_size()`, ranked across four no-contrib methods (catalog sweep, `pg_column_size` slot measurement, index-only-scan `BUFFERS` census, `CREATE INDEX CONCURRENTLY` rebuild probe) with exact-pin accuracy against real rebuilds on 14 fixtures, plus a filed follow-up that scores those methods against `pgstatindex` over a 54-index bloat-type/scale/partial matrix and shows an `avg_leaf_density` rebuild-size predictor losing in 16 of 18 cells. Filed `indexing` coverage also includes a calibration of the COMMENT-stored bytes-per-table-tuple rebuild trigger for all five core non-btree access methods: `pg_relation_size(index) / table pg_class.reltuples` stamped into each index comment at build time, scored over 132 exact-pin cells (22 insert/update/delete workloads x 6 index shapes) against `REINDEX INDEX` ground truth, finding GiST the only access method that calibrates cleanly (any threshold in 20-30%, 14/0/0/8, with only -0.29% to +3.84% fresh-build drift across 25k-1.6M rows), hash (9-11%) and SP-GiST (29-32%) usable only at a stable row count because a fresh build alone spans -20.31% to +49.42% and up to +33.08%, GIN needing 50-75%, and BRIN unusable at any threshold (0.00% reclaimed in 22/22 cells against readings from -87.50% to +9900.00%); with the delete-only `1/(1-f)-1` identity, the GIN pending-list trap where a flush moves the reading from +261.73% to +388.78% while delivering the whole 3,779 -> 1,336 block win, hash's 10.3% baseline spread from `estimate_rel_size`, its splitpoint staircase and 87 filesystem-unallocated pages counted by `pg_relation_size`, BRIN's 6.3x `pages_per_range` baseline spread and precision-only degradation, the stale-`reltuples` +84.71%/-7.64% inversion, a partial-index false negative (-5.02% reading, 44.59% reclaimable), per-access-method rebuild costs and query-block payoffs (none for hash or BRIN), and `COMMENT ON INDEX` mechanics verified on the pin. Filed coverage also includes a no-regex extraction of declarative range partition bounds: v12 exposes no typed bound, so the deliverable decomposes the `pg_get_expr(relpartbound, oid)` text that `psql \d` and `pg_dump` consume, using the deparser's fixed grammar from `get_rule_expr`/`get_range_partbound_string`/`get_const_expr` (`FOR VALUES FROM (` … `) TO (`, `, ` separators, bare `MINVALUE`/`MAXVALUE`, `DEFAULT`, no `::type` or `COLLATE` at `showtype = -1`, `simple_quote_literal` quoting that follows `standard_conforming_strings`) plus a quote-masking pass over `string_to_array(bound_def, '''')` so `strpos`/`substr` see only real separators; with a gated `split_part` variant, the qualifying-relation rules (`relispartition` + `partstrat = 'r'`, `relkind` r/p/f, multi-level, cross-schema, DEFAULT rows, detached and index partitions excluded), cast-back semantics and the `boolean`/`char(3)` exceptions, rejected alternatives (`relpartbound::text` byte dump, `pg_get_partition_constraintdef`, `pg_partition_tree`), and exact-pin measurements (41/41 reconstructed deparse match, 95/95 recipe versus 9/41 partitions wrong for the obvious split, 45/45 for `pg_get_expr(…, 0)` and `pretty = true`, 78/81 exact round trips, six output GUCs swept, 14 catalog locks and zero partition locks at 1048 partitions in 39.9-44.9 ms, full visibility to an unprivileged role, the NULL-deparse drop race, and the untoastable-`pg_class` `row is too big` ceiling). The core-SQL B-tree bloat page's statements now report `wasted_space` and `wasted_space_pct` under the tag `wiki_btree_wasted_space_sweep`, with the Method C probe index renamed `wiki_wasted_space_probe`, filed as a source-only correction that moves no measured number: v12 defines a bloated index as one with "many empty or nearly-empty pages" (`ref/reindex.sgml`) — per-page state that file-size-minus-model arithmetic cannot see — while `ref/copy.sgml` supplies "wasted space" for what a maintenance command recovers, no v12 SQL interface names a column `bloat`, and this checkout has no glossary; `AS` labels cannot reach the expression `ORDER BY` key or the contrib-computed query ID (`resname` is not jumbled and the lexer drops the comment), whereas the probe rename is an object name that does re-key the two utility statements, which v12 hashes by text. Coverage also includes a measured `VACUUM FULL` I/O accounting for a multi-GB near-empty heap, run on a 12.2 server built from this pin: a 200,000,000-row heap of 884,956 blocks (7,249,559,552 bytes) had 99.9% of its rows deleted with the physically last rows kept so `VACUUM` could not truncate, and after `VACUUM` plus `VACUUM FREEZE` left all 884,956 pages all-visible and all-frozen, `VACUUM FULL` read every one of the 884,956 blocks with 0 hits while the block layer delivered exactly 7,249,559,552 bytes, against a plain `VACUUM` on the identical heap reading 0 blocks; the same 6.75 GB heap holding zero rows still read all 884,956 blocks to write a 0-byte new heap, `pg_waldump` counted 885 `XLOG/FPI` records for 885 new pages, `heap_blks_scanned` reported 0 of 884,956 for 49 of 51 samples, the index rebuild read only the new 885-block heap, a cost delay left the rewrite at 2.05 s against a throttled 57.27 s for the same bytes, and every emptied page kept 226 of 226 line pointers. The source analysis holds: reads track the physical file (`RelationGetNumberOfBlocks`, one `ReadBufferExtended` per block, no visibility-map skip and no prefetch anywhere in `cluster.c`/`heapam_handler.c`/`rewriteheap.c`) while writes, WAL, the closing `heap_sync` and the index rebuilds track surviving rows, and freeing the old file is metadata work; the review corrected `heap_blks_scanned` (updated per returned tuple as `rs_cblock + 1`, never squared up, so it under-reports this shape and `pg_statio_all_tables.heap_blks_read` is the honest counter), the "empty page" claim (`PageRepairFragmentation` never removes unused line pointers, so vacuumed-empty pages keep their arrays and `heapgettup` walks them skipping on `ItemIdIsNormal`), the `MAXALIGN(500) + 4 = 508` worked-example cell, two under-wide citation ranges, and the published monitoring statements, which needed `BEGIN`/`COMMIT` because a top-level `SET LOCAL` only warns. A companion storage page files one runnable statement that measures heap and TOAST bloat together: `pgstattuple_approx` accepts only `RELKIND_RELATION`/`RELKIND_MATVIEW`, so the TOAST row uses the exact `pgstattuple` and a fillfactor hard-coded to 100 because `heap_reloptions()` forces that value for `RELKIND_TOASTVALUE`; tested against `VACUUM FULL` over ten fixtures, the requested reserve-subtraction formula matches the rewrite-matching ratio form exactly at `fillfactor = 100` (12 of 12 rows) but understates by 15.54 points on a bloated `fillfactor = 70` table, and TOAST free space proved to be mostly chunk geometry - 19.58% free on a never-deleted TOAST relation that `VACUUM FULL` shrank by 0.00%, reconciled to the byte from `TOAST_MAX_CHUNK_SIZE` = 1,996, against 0.24% for a payload sized to an exact chunk multiple - while `f_toastonly` hid 24 MB of reclaimable TOAST behind a healthy 200 kB heap. A third storage page reviews and scores the widely circulated `pg_stats`/`pg_class` catalog-statistics bloat-estimate statement against exact `pgstattuple` and against a real `VACUUM FULL`: over 21 scored fixtures it lands within 1 point of the rewrite on 13 and averages 9.47 points of absolute error (better than `pgstattuple`'s own 10.79 against the same rewrites, which includes a −86.41 miss on a dropped column), and as a screen it scores 9 true positives, 2 false positives, 5 false negatives and 9 true negatives; the named failures are 0 against a 50.00% rewrite on stale statistics, −25.05 from the `MAX(null_frac)` second aligned header, −11.98 when TOAST chunks pack 6 to a page instead of 4, −9.00 from inherited statistics doubling `datawidth`, +21.00 from column alignment padding, +33.00 from unfloored page packing, and +31.00 from ignoring `fillfactor`, plus five relation classes that never get a number (matviews, partitioned parents, `STATISTICS 0`, never-analyzed, empty) and the proof that no `can_estimate = false` row can pass the published `WHERE` clause. The 2026-09-07 source follow-up supports the v12/v17 open-question review with v12-local evidence for the ordinary tuple build, three support procedures, reloptions, count/statistics writers, collector publication, statistics visibility, build capabilities and signed formatting. It proposes a bounded writer/observer test protocol and qualifies catalog-only size as an approximation; SQL and historical measurements are unchanged. On 2026-09-07 the B-tree leaf-density question was re-measured end to end against a server rebuilt from the pin, and its fixture SQL is now published on the page: the cost rows were relabelled to name plan nodes rather than plan totals (the `count(*)` wrapper adds 2500 above the `Index Only Scan`), warm buffers were corrected from 2738/4121 to 2736/4119 with one block shown to be the heap's visibility map rather than the index, default parallel plan totals from 22647.09/28199.09 to 22188.97/27740.97, the statistics-refresh claim was corrected because a plain `ANALYZE` and the index build also write an index's `pg_class` row (551 to 1648 `relpages` with no VACUUM), the 50:50 leaf-split summary was corrected for the `SPLIT_SINGLE_VALUE` override (95.98 density for one repeated key against 90.05 for distinct keys), and the prefetch claim was widened to all four heap-fork call sites plus the `pg_prewarm` index exception; four new fixtures hold the row estimate fixed on one table (31 versus 45 buffers, a 52.00 cost gap), bound the `tree_level` flip to a 104-to-112-byte key band at 100,000 rows, match backward to forward page counts, and convert the penalty into 2735 versus 4118 shared-buffer misses under a 1MB pool. Both leaf-density pages had claimed a retained sandbox that was deleted earlier the same day; that claim is now corrected on both. Later the same day the density-versus-fragmentation page was re-measured end to end on a fresh 12.2 build and its own fixture SQL published: the density rows moved to 2736/4119 warm plan buffers with a measured 2735/4118 index-side split, the cost column was relabelled and refiled as a 25980.42/31532.42 serial scan-node pair and a 22188.97/27740.97 parallel total, the fragmentation fixture was reseeded under `setseed(0.5)` to 3684 leaf pages at 66.89 density and 49.84 `leaf_fragmentation` against a `fillfactor = 67` rebuild at 3677 and 67.02, moving buffers only 3687 to 3680, and a published `pageinspect` census showed the metric is a lower bound: 1836 of 3683 links point backward but **none** point to the next physical block, so the order-cost model now takes the non-adjacent share rather than `leaf_fragmentation`. The dead-space row was re-derived as 550/1435/550 plan buffers with a 549-index-plus-886-heap split, correcting the claim that 20,000 heap fetches inflate it: the fetches collapse onto the heap's 885 pages because `ReleaseAndReadBuffer` keeps the pinned buffer. The pass also resolved a discrepancy both pages had left open, showing the previously filed 2738/4121 are exactly the default parallel plan's buffer totals, and narrowed the matching cost offset of 458.12 to a heap that was not fully all-visible. The physical-index-statistics page was re-reviewed on 2026-09-10 at the unchanged pin and now carries the mandatory `## Measurement Script` section: all 354 of its source citations were re-read in bounds with no claim corrected, and an isolated 12.2 build (192 of 192 engine tests passing) supplied a per-writer `reltuples` matrix over all seven access methods (one BRIN index reading 14 / 100000 / 13 and keeping 13 through `VACUUM ANALYZE`, hash 80000 before the 100000-row estimate, GIN 300000 extracted keys), an empty-heap BRIN at 1 then 0 with its summary item intact, `btm_last_cleanup_num_heap_tuples` at -1 then 74961 against the index's own 75000, `hashm_ntuples` 60000 against `reltuples` 75000, a GIN pending list counting 50 heap tuples for 150 keys and a `VACUUM` that wrote no index `reltuples` at all, both GiST `pgstattuple` defects quantified (0 items on a five-row single-page index, and a 42-item overcount that is exactly twice the 21 pages marked `F_LEAF|F_DELETED`, with no truncation and no FSM entry), the full dispatch and privilege matrix with exact refusals, 16/24/16-byte item payloads including MAXALIGN padding against 54 excluded high keys, a `main_bytes / reltuples` swing of 90.28 to 22.57 on a byte-identical file, and FSM read-backs of 8,160 for a reclaimed index page and 7,936 for BRIN, plus a reviewed source-only assessment of very large `shared_buffers`: conditional memory arithmetic including the derived ~1.75 GiB buffer-mapping hash and the ~6.13 GiB non-page total, the power-of-two bucket cliff that makes 2^25 buffers pessimal, full-pool scan costs with the tree's own sequential-search comment and a closed five-function list, checkpoint and eviction qualifications, the `NBuffers`-scaled sync-queue drain and compaction allocations, three hard limits above 256 GB (8 TiB minus a block, 409.6 GiB, 341.3 GiB), strict scan-strategy thresholds, per-fork truncation passes and the below-threshold linear drop walk, contrib allocation limits and the 300-second autoprewarm dump period, 22 settings with exact apply scopes, and correctly scoped monitoring guidance. No large-pool performance result is claimed. |

## Coverage Notes

- 2026-09-26: **review and fix v12**, [How pgstatindex Calculates B-Tree Index Statistics in PostgreSQL 12 (unverified)](v12/questions/indexing/how-pgstatindex-calculates-information.md), unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42` (12.2).
  - Corrected schema-name permission checks and the special-pointer assertion boundary; added value, decision, and lifecycle maps, glossary links, and worked calculations.
  - Published one staged Bash/SQL measurement script. Both extension installcheck suites passed, all six page censuses matched the worker's counts and formulas, and schema/function/OID permission probes passed. Retained dead-item storage left density unchanged; VACUUM produced deleted pages without shrinking the captured main-fork byte size. The isolated server was stopped and its build/cluster sandbox deleted.
- 2026-09-26: **answer v17**, [How the PostgreSQL 17 Query Planner Works: A Comprehensive Tutorial (unverified)](v17/questions/query-planning/query-planner-comprehensive-tutorial.md) at unchanged pin `786db8dcf16` (17.11).
  - Sixteen chapters, audited against the pinned source and extended beyond the requested outline: each has a value table, logic map, walkthrough, eligibility and exception tables, worked calculations, a planning-versus-execution section, lifecycle and test coverage, and a causal summary. A coverage matrix of about 300 rows ties every planner responsibility, path and plan family, setting and hook to its source, conditions, tests and an example or a stated gap.
  - Every estimate and measurement comes from one staged script (build, check, schema, fifteen experiment stages, platform, summary, stop, clean) run from an empty sandbox on an isolated 17.11 server, byte-identical across runs apart from timestamps. Verification gaps of this build are recorded: no LLVM (JIT compilation itself), no ICU (nondeterministic collations), no libxml (`XMLTABLE`), and no in-core custom-scan provider or path-hook user.
  - The shared glossary gained 39 planner entries checked on 17 only, for 319 terms.
- 2026-09-25: **review v17**, [Planner Penalties for Bloated Indexes in PostgreSQL 17 (unverified)](v17/questions/query-planning/bloated-indexes-query-planner.md) at unchanged pin `786db8dcf16` (17.11), for adherence to `AGENTS.md`.
  - The review found no wrong engine behavior and no wrong number; its findings were against rules added after the page's last revision. The answer was restructured to the Technical Explanations shape, with a value table, a logic map, six mechanism steps, branch and lifecycle tables, formulas, worked measurements and a causal summary, and the GIN follow-up likewise.
  - The since-v12 history now rests on the v17 checkout's own history from the v12 branch point `9e1c9f9594`; the 12.x-release attribution of the endpoint-probe limit moved to Open Questions, and `3d351d916b2`'s `tableam.c` change, `29cf61ade3` and `587b6aa3f3` were added.
  - The script gained sandboxed `TMPDIR` and `PG_REGRESS_SOCK_DIR`, `ON_ERROR_STOP` for `grej`, a checked exit-trap teardown and a validated `WIKI_ROOT`, and ran identically under bash 5.3.15 and 3.2.57 with every number unchanged.
  - The shared glossary gained 13 entries checked on 17 only, for 280 terms, and the Hash splitpoint alias no longer collides with B-tree split points.

- 2026-09-25: **review v17**, [Planner Penalties for Bloated Indexes in PostgreSQL 17 (unverified)](v17/questions/query-planning/bloated-indexes-query-planner.md) at unchanged pin `786db8dcf16` (17.11).
  - The filed script, re-run unchanged, reproduced every number; 138 of 157 review findings survived an adversarial check and were fixed, none of them a change to a recorded measurement.
  - Two mechanisms the page had missed are now explained and measured. A partial index takes its tuple count from its last recorded density, so its growth since that `pg_class` row was written is charged only in step with the table's (fixture Q: 113 pages charged at 331 live blocks, 331 after `ANALYZE`). The planner reads the ends of a B-tree while planning and gives up after 100 heap pages of dead entries (`9c6ad5eaa9`, first in 16, back-patched; fixture E).
  - GIN gained a gate 0 (invalid, not-yet-usable and unproven partial indexes), and the since-v12 history gained `19d8e2308b`, `4b754d6c16e`, `71b66171d0` and the `pg_upgrade` deduplication caveat. The script gained two stages and four safety fixes and ran identically under bash 5.3.15 and 3.2.57; numbers the current script does not produce were removed.
  - The shared glossary gained BitmapAnd, Mackert-Lohman formula, Nested loop join, Partial path, Planner support function, ScalarArrayOpExpr and Summarizing index, each checked on 17 only, for 267 terms. The page gained its glossary links and links to the B-tree and GIN bloat-test protocol pages; no concept page was edited.
- 2026-09-24: **revise v17**, [A COMMENT-Stored Baseline Non-B-Tree Index-Maintenance Heuristic for PostgreSQL 12 Through 17 (unverified)](v17/questions/indexing/non-btree-comment-baseline-maintenance-heuristic.md) at unchanged pins `786db8dcf16` (17.11) and `45b88269a35` (12.2).
  - Removed the two coverage rows each leg script still declared, skipped, for "a `VACUUM` whose index cleanup did not run", with every sentence that called the case a requirement of both protocols, including open question 11. Both protocols dropped the case earlier the same day; this page had removed its fixtures, `h06` and `n11`, on 2026-09-22.
  - Fixed a script defect the re-run exposed: two readings the coverage table quotes, `h01`'s overflow and bitmap counts and `g07`'s leaf count, were kept only in the fixture database that `clean` deletes. The `score` stage of both legs now writes every census reading to `meas.csv`.
  - Re-ran both legs end to end three times on Darwin 27 arm64, starting with a baseline pass of the filed scripts. Every decision, score, prediction, invariant and edge verdict reproduced: 22 / 7 / 0 on 17.11 and 22 / 6 / 0 on 12.2. Only `g09`'s sizes and the `ANALYZE`-sampled tuple ratios moved.
  - The shared glossary gained an Isolation level entry checked on 17 only, and its Back-patch entry a 17 check, for 260 terms. The page gained its glossary links.

- 2026-09-24: **revise v17**, [Detecting Inflated Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17 (unverified)](v17/questions/indexing/non-btree-index-inflation-comment-baseline.md) at unchanged pin `786db8dcf16` (17.11).
  - Removed fixtures `h06` and `n11`, whose maintenance step was `VACUUM (ANALYZE, INDEX_CLEANUP OFF)`, with their declared exceptions X3 and X4, their coverage rows and every claim they backed, including the page's one false negative. Both protocols stopped allowing such a `VACUUM` earlier the same day.
  - Refiled two coverage rows as not reached: `g08` deletes no GiST page while its snapshot is held, and `n04` holds no posting tree. Corrected the coverage count (it had read 31 of 34; it was 30 of 33, and is now 24 reached, 2 partly, 2 not reached, 3 skipped of 31) and one limitation's fixture count.
  - Fixed three script defects a run on macOS exposed: a BSD `grep` pattern that never counted a `VACUUM` command tag, a `pgrep -a` process check, and a port check that could not fire.
  - Re-ran the whole script on Darwin 27 arm64, after a baseline pass of the filed script. On the 29 fixtures kept, every recommendation, decision and bound verdict of the 2026-09-16 Linux filing reproduced: 29 of 29 right, 14 flagged, the bound held on 18 and was violated on 11. Only `g09`'s churned file moved, as on every pass.
  - The shared glossary gained four entries checked on 17 only: BRIN summarization, Hash splitpoint, Index page recycling and SP-GiST placeholder, for 259 terms.

- 2026-09-24: **revise v17**, [A COMMENT-Stored Baseline and Normalized Index Growth for Finding GIN Indexes That Need REINDEX CONCURRENTLY in PostgreSQL 17 (unverified)](v17/questions/indexing/gin-reindex-normalized-growth-comment-baseline.md) at unchanged pin `786db8dcf16` (17.11).
  - Removed fixture `i01`, whose `VACUUM (INDEX_CLEANUP OFF)` ran between its writes and its settle step. The GIN protocol stopped requiring or declaring such a `VACUUM` earlier the same day.
  - Fixed three script defects that a run on macOS exposed: a BSD `grep` pattern that never counted a bare `VACUUM` command tag (I8 read 3 of 76), a teardown port check that could not fire, and quoted numbers that lived only in the database, now dumped to `meas.csv` and `maint.csv`.
  - Re-ran the whole script four times on Darwin 27 arm64. The recorded run reproduced every scored cell of the 2026-09-17 Linux filing except `c02`'s bound, which an `ANALYZE` sample decides: 23 scored fixtures, 18 / 1 / 0 / 4, and the upper bound held on 13 of 20.
  - Corrected the claim that the `ANALYZE` sample error is one-directional: 25 readings over five passes came out 18 high and 7 low. Of the fixture tables, only `c02`'s, at 30,928 pages, is large enough to be sampled.
  - The shared glossary gained two entries checked on 17 only: Command tag, and transaction_timeout and idle_in_transaction_session_timeout.

- 2026-09-24: **revise v17**, [Measuring Wasted and Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17 (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md) at unchanged pins `786db8dcf16` (17.11) and `45b88269a35` (12.2).
  - Removed `f9c_cleanup`, the fixture that ran a `VACUUM` with index cleanup off, which the GIN protocol stopped allowing earlier the same day. The asker chose not to bring the rest of the script onto the protocol's no-defeat rule; that gap is now an open question on the page.
  - Fixed four script defects a run on macOS exposed: BSD `dd` has no `oflag=append`, the corrupt stage's probe never ran, the teardown check could not fire, and five kinds of reported numbers were written by no stage.
  - Added a 12.2 leg script and a matching `portability` stage in the 17.11 script. The 12.2 re-check corrected three claims, including that the invalid-index refusal is not v17-only: it was back-patched and reached 12.17.
  - The recorded run on Darwin 27 arm64 reproduced every scored cell of the 2026-09-16 Linux filing. One other pass the same day moved `g50_gin` by one page through VACUUM's index-vacuum bypass.
  - The shared glossary's Base backup entry gained a PostgreSQL 17 check.

- 2026-09-24: **concept v17**, removed the index-cleanup-disabled test from [Mandatory GIN Bloat Tests (unverified)](v17/common-concepts/mandatory-gin-bloat-tests.md) and [Mandatory Non-B-Tree, Non-GIN Bloat Tests (unverified)](v17/common-concepts/mandatory-non-btree-non-gin-bloat-tests.md) at the asker's request, at unchanged pin `786db8dcf16`.
  - Each page dropped the coverage row for "a `VACUUM` whose index cleanup did not run" and the declared exception for that fixture, so two exceptions remain on each. Each page now names that `VACUUM` under `What the protocol does not cover`.
  - [Mandatory B-Tree Bloat Tests (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md) has no such test and was not edited. The held-snapshot coverage rows on the other two pages stay required.
  - Four v17 question pages still describe the removed row. They were reported to the asker and not edited.

- 2026-09-24: **answer v19**, [History of Online Data Checksum Enabling and Disabling in PostgreSQL 19, and All Its Commits (unverified)](v19/questions/storage-and-vacuum/online-data-checksums-history.md) at pin `dae3463fa96`, no repin.
  - The page lists 85 commits: the 2018 attempt and its revert, the 2019 barrier infrastructure, the 2026 preparation and main commit, 51 follow-ups (29 on master, 22 on `REL_19_STABLE`), 7 release-note commits, 12 tree-wide commits, 4 translation imports, and the revert with 2 cleanups. It also lists 27 commits that were checked and excluded.
  - `raw/postgres-19` is a shallow clone (history from `0ef891e5417`, 2025-08-07). The asker chose not to fetch, so the ancestry of the 2018 and 2019 commits and the unseen 2025 gap are recorded as Open Questions.
  - The shared glossary gained ten entries checked on 19 only, for 253 terms.

- 2026-09-24: **repin v19**, `135b867a530cac2e3796d87c852b53bef40f0077` -> `dae3463fa969931458f1488f9b7af11e3741cd54`
  (`REL_19_BETA3-130-g135b867a530` -> `REL_19_BETA4-17-gdae3463fa96`), at the asker's request to move v19 to the
  newest source. `configure.ac` and `meson.build` now read **`19beta4`** (`b73d13c32c8`, tag `REL_19_BETA4`,
  2026-09-21); upstream has no RC or GA tag, so the pin is the branch tip, 17 commits past the beta4 stamp. The old
  pin remains an ancestor. **All 159 commits were reviewed** per page. **REPACK page 58 -> 79 feature-scope
  commits**: `REPACK` in either mode fails on any invalid index (`e14a2354d9f`, `0cabab44f12`); `CONCURRENTLY`
  rejects non-heap table AMs (`fe7b6072342`), `user_catalog_table` tables (`04bb1500253`), materialized views
  (`40d811540a5`) and a dropped `REPLICA IDENTITY USING INDEX` index (`434bde9ce6b`, not yet in `ref/repack.sgml`,
  filed as an Open Question); the decoding worker no longer needs `CONNECT` (`9bf3a414560`), copies the leader's
  `lock_timeout`/`transaction_timeout` (`746a507a391`), starts and stops through a two-stage handshake
  (`47b5b23a780`) and waits for the initial snapshot's transactions (`4a4bf490dc5`); progress reporting was fixed
  (`e418e8eb92a`, `d1f742d5d12`, `ccbea44294b`, `8a1b5b3d438`); `REPACK (ANALYZE)` is rejected in a transaction
  block (`24dd8c369e5`). **`pg_plan_advice` page 28 -> 34 module commits, 20 -> 21 core**: partition names need a
  schema (`3201ea8f171`), empty `JOIN_ORDER` sublists are parse errors (`88cbbcb253a`), `JOIN_ORDER` feedback
  matching was reworked (`0f433a6b357`), GEQO fitness ranks `disabled_nodes` before cost (`d22961bca2c`) and join
  advice under GEQO is probabilistic (`9ed2684b89a`); its 2026-09-01 agent timestamp was reset to `not yet`.
  **Autovacuum page, 9 claims**: `13243ae44cf` rewrote the on-access VM safety valve (only a dirty heap buffer that
  needs a full-page image, on a WAL-logged relation with logged hint bits, skips setting the VM) and added the first
  regression test; `b3609cd2db8`, `40cc0662ed7`, `41a8548ad41`, `1bda0b23bce` (freeze-score `pow()` needs a
  component above 1.0), `XLOG_PAGE_MAGIC` 0xD121 -> 0xD122 (`4a9a6c5a69c`) and the release-note rewording
  (`f94f8b18d3b`). **Navigation guide**: `19beta4` stamp, no routing change, and the SQL/PGQ, FOR PORTION OF,
  online-checksum and `pg_get_*_ddl` reverts. **Glossary**: every v19 citation re-checked; Data checksums, Hint
  bits, Page, Foreign key trigger, Relation, pg_class, Range table, Progress reporting and HOT pruning corrected for
  the reverts and fixes; GEQO added (243 terms); v19 Source Pins row moved. 629 citation fragments re-anchored by
  `scripts/repin_citations`, which gained `--include-glossary` and path-prefixed label sync; the remaining changed
  or missing blocks were relocated by hand. `verified:` untouched.

- 2026-09-24: Reviewed and revised [Row-Level Security (RLS) in PostgreSQL 18: Implementation,
  Performance, Settings, and Fixes Since PostgreSQL 14
  (unverified)](v18/questions/server-administration/row-level-security-rls.md) at unchanged pin
  `baa7b142aace6821ce085906f314a75bcc4d95c8`, with a published measurement script run on 18.6. The
  page now covers 18.6's plan-cache role invalidation and its replans after unrelated role changes
  and `datfrozenxid` advances, the statistics and sublink limits RLS puts on the planner, and when a
  policy value can prune partitions. It also fixes an inverted owner-bypass sentence and about 40 other
  claims and citations. The shared glossary gained Role membership, Security invoker view, SubLink and
  WithCheckOption, for 242 terms.
- 2026-09-23: Filed [B-Tree Leaf Density vs Fragmentation Impact on Index Scan I/O in PostgreSQL 17
  (unverified)](v17/questions/indexing/leaf-density-vs-fragmentation-index-scan-io.md) at pin
  `786db8dcf168bd9df8f55047337525ac19118b1c`, measured on 17.11 from a published script. Density
  decides what PostgreSQL counts and prices: 90 % to 60 % raised warm index-only buffers by 50.5 %,
  while a rebuild that removed 49.45 % `leaf_fragmentation` moved them by 0.65 %, its 24 fewer pages.
  No B-tree read path in 17 prefetches or stream-reads, and the 17.11 `random_page_cost` docs carry
  no SSD value since 17.7. The shared glossary gained Asynchronous commit, Hint bits, Prefetch,
  Sibling link and WAL writer, each checked on all five versions, for 238 terms.
- 2026-09-23: Reviewed [Planner Penalties for Bloated Indexes in PostgreSQL 17
  (unverified)](v17/questions/query-planning/bloated-indexes-query-planner.md) at unchanged
  pin `786db8dcf168bd9df8f55047337525ac19118b1c` and fixed what the review found. The filed
  script, re-run unchanged, reproduced every number; the prose had about fifty defects,
  fifteen of them about PostgreSQL behavior. Corrected: the one-page rule was stated backwards
  between one row and `pages` rows; VACUUM's statistics update reaches a planning backend as a
  relcache invalidation, so a stale cached tree height survives only a root split or a VACUUM
  that writes no statistics; split policy is not a density ceiling; `5bf748b86bc` made
  `GenericCosts.num_sa_scans` an input, a field `REL_12_0` already had; `INDEX_CLEANUP ON`
  forces index vacuuming, not cleanup; BRIN charges every index page on every scan; index
  builds deduplicate too; the statistics hooks feed every selectivity; generated catalog
  headers are on the cost path; the GIN cost recipe was missing two terms; and the v17 descent
  clamp is a discount against v12, not a surcharge. The answer now sits under `## Answer`, the
  closing sections follow the template, and the script checks its pin and sandbox, checks
  every stage name before running any, records every quoted value in `summary.txt`, and gives
  the snapshot holder the session timeouts. A full run from an empty sandbox and a
  fixture-stage pass on PostgreSQL 17.11, Darwin arm64, agreed byte for byte on 35 index rows,
  11 GIN rows, 7 of 7 predictions, 29 facts and 126 plans. Fourteen open questions;
  `verified_by_agent` stays `not yet`.
- 2026-09-22: Reviewed
  [How Accurate Is the pgstatindex REINDEX_SCORE B-Tree Maintenance Heuristic, on
  PostgreSQL 17 and 12 (unverified)](v17/questions/indexing/btree-reindex-score-heuristic.md)
  and fixed the 26 defects the review found, plus five more found while fixing them, at
  unchanged pins. The headline numbers reproduced exactly; the text around them did not
  hold. Corrected: the 96 % single-value fillfactor applies to page splits, not to the
  rebuild; `BTEQUALIMAGE_PROC` came from `612a1ab767`, one commit before deduplication;
  `GREATEST(0, NaN)` is decided by `float8_lt`; the threshold range is set by two
  fixtures' scores, not by a gap in the rebuilds; 41 of the 98 cross-leg differences are
  the run's own objects, not catalog indexes. Both leg scripts now check the pinned commit,
  fail the run on a failed regression suite, refuse a second `score` or `guard` pass, and
  delete only a sandbox they marked, the 17 leg only after the 12 leg's `clean`. Both legs
  were re-run from an empty sandbox on Darwin arm64: every fixture figure unchanged,
  `p120` scored on 17.11 and not on 12.2.
- 2026-09-22: Fixed twelve reported defects on
  [A COMMENT-Stored Baseline Non-B-Tree Index-Maintenance Heuristic for PostgreSQL 12
  Through 17 (unverified)](v17/questions/indexing/non-btree-comment-baseline-maintenance-heuristic.md)
  at unchanged pins. Both leg scripts now refuse any sandbox but their own marked
  directory under `.wiki-runtime/tmp`, stop on any failed stage or check, and build only
  from the pin, recording a manifest. Step 2 takes `REINDEX INDEX`'s two locks, checks the
  index's identity and decides again under them, counts a rebuild against `max_reindex`
  before it starts, and keeps the human text byte for byte around one reserved payload
  line matched whole. The cross-checks now compare `VACUUM VERBOSE`'s index line count by
  count and BRIN's free space page by page, and the score applies the pay-off to the
  unrounded fraction. Both legs were re-measured end to end: **22 / 7 / 0 on 17.11 and
  22 / 6 / 0 on 12.2**, every decision as before, 18 of 18 invariants and 158 of 158
  edge-case verdicts on each leg. The run still skips "a `VACUUM` whose index cleanup did
  not run" and now files the GiST held-snapshot row as not reached.
- 2026-09-22: Removed fixtures `h06` and `n11`, the two whose maintenance step was
  `VACUUM (ANALYZE, INDEX_CLEANUP OFF)` and the page's only false negatives, from
  [A COMMENT-Stored Baseline Non-B-Tree Index-Maintenance Heuristic for PostgreSQL 12
  Through 17 (unverified)](v17/questions/indexing/non-btree-comment-baseline-maintenance-heuristic.md)
  at the asker's request, at unchanged pins. Both leg scripts were edited in place and both
  legs re-measured end to end: **22 / 7 / 0 on 17.11 over 29 fixtures and 22 / 6 / 0 on
  12.2 over 28**, every other fixture decided and scored as before. The run no longer
  reaches "a `VACUUM` whose index cleanup did not run", which both mandatory protocols list
  as required coverage; the page records the row as skipped.
- 2026-09-22: Filed [A COMMENT-Stored Baseline Non-B-Tree Index-Maintenance Heuristic for
  PostgreSQL 12 Through 17 (unverified)](v17/questions/indexing/non-btree-comment-baseline-maintenance-heuristic.md)
  at pin `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11), with a 12.2 leg built from
  `45b88269a353ad93744772791feb6d01bc7e1e42`. Two texts that run unchanged on both servers
  store a version-2 `@nbmaint:` payload (index size, table `reltuples`) in the index
  comment and rebuild when the index grew 30 % or the table count moved 30 %. Scored on the
  31 numbered fixtures of the non-B-tree inflation page, 30 on 12.2 because `b11` needs
  `int8_minmax_multi_ops`, under both mandatory protocols,
  at a declared 23.08 % pay-off: **22 / 7 / 2 on 17.11 and 22 / 6 / 2 on 12.2**, every
  prediction filed before the run held, and step 1 equalled the tests recomputed
  independently on every fixture. Both legs were built and measured end to end on Darwin
  arm64 from empty sandboxes, `make check` All 225 and All 192, and both leg scripts are
  published in full. The run found one version-local instrument difference: 12.2's
  `pgstattuple` refuses a hash index holding an all-zero page, which 17 reads as free space
  since commit `036decbba2` (17.7).
- 2026-09-20: Fixed ten more reported defects in [Planner Penalties for Bloated Indexes in
  PostgreSQL 17 (unverified)](v17/questions/query-planning/bloated-indexes-query-planner.md) at
  unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`. Each was checked against the pin
  before it was fixed and each was confirmed; none was a false report. **The P1 was in the
  published measurement script**, and it was deeper than the one the 2026-09-19 pass closed:
  `pg()` and `pgq()` handed their exit status back to callers that never looked at it, so only
  a stage function's last command decided the stage's status. A failed fixture build or a
  failed `UPDATE` round in the middle of a stage was therefore reported as a pass. Reproduced
  by injecting both kinds of failure: the pre-fix text exited 0 and the filed text exits 1,
  naming the stage and the statement, with the `EXIT` trap leaving no postmaster behind.
  **Fixture D was rebuilt on independent populations**: it marked every 5,000th row with the
  rare lexeme while `cat` was `i % 20`, and 20 divides 5,000, so `zebracorn AND cat = 7` could
  not match a row - the same defect fixture L3 had. A 4,999-row period makes the two
  populations independent and reproduced every one of D's recorded costs to the cent while the
  true count moved from 0 to 4. **Eight source readings were corrected**: the opening
  four-input table is a B-tree-family summary rather than an all-index one, and only two of its
  rows are stored fields; `_bt_getroot()` and `_bt_gettrueroot()` also clear the cached tree
  height; a table `parallel_workers` reloption skips the page-based worker calculation and the
  minimum-size rejection exempts inheritance children; HOT needs `newbuf == buffer` as well as
  untouched hot-blocking columns; the page-charge probe is invalid under a tablespace
  `random_page_cost` override, and the filed block now checks for one; the one-page rule is
  bounded at both ends, by `tuples <= 1` below and by scan repetition above; `n IN (1,2,3)`
  does take GIN's array cache adjustment at `arrayScans = 3`; and gate 1 rejects a clause, not
  the index. New fixture F-one measures the lower bound: a 551-block index stripped to one live
  leaf is charged one page and prices a whole-index scan at `4.14`. Three passes on
  PostgreSQL 17.11, Darwin arm64, agreed byte for byte on 35 index rows, 11 GIN rows, 7 of 7
  predictions and 121 plans, with `make check` All 225 and All 1 / 8 / 30 on `pgstattuple`,
  `pageinspect` and `btree_gin`. Twelve open questions; `verified_by_agent` stays `not yet`.
- 2026-09-19: Reviewed, corrected and re-measured [Planner Penalties for Bloated Indexes in
  PostgreSQL 17 (unverified)](v17/questions/query-planning/bloated-indexes-query-planner.md) at
  unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`. The asker first scoped the review
  **report only**, read the findings, then asked for them to be fixed. **All 340 citations
  (177 ranges, 46 files) were re-read against the pin**: all in bounds, all v17; six ranges
  were tightened, one label pointed at a legacy entry point, five behavioral claims had no
  citation, and the page now carries 406 citations over 199 ranges in 53 files. **Nine source
  readings were wrong and are corrected**: `compute_parallel_worker()` reads the AM's
  touched-pages estimate, not `index->pages`; `cost_index()` has three
  `index_pages_fetched()` call sites, not four; contrib `bloom` is a fifth
  `genericcostestimate()` caller; `get_relation_info_hook` can rewrite `pages`, `tuples` and
  `tree_height`, so "an extension cannot change the height charge" was false; the planner's
  height is `btm_fastlevel`, which page deletion lowers without a rebuild; a point lookup is
  blind to bloat only while `pages <= tuples`; the filed closed form carried a `qual_op_cost`
  term the source does not have, which is what produced the page's one-cent open question;
  `num_sa_scans` multiplies the page charge and not the per-tuple charge; and GIN's
  startup/total split never reaches a plan because `cost_bitmap_heap_scan()` takes the index
  total as startup. **The history method was replaced**: this host's v17 checkout carries no
  tags, so `git tag --contains` cannot run; attributions now rest on ancestry against the
  `Stamp HEAD as NNdevel.` and `Stamp 17.N.` commits and on `REL_12_0` text read from the v12
  checkout, and every attribution survived. **The page gained its `## Measurement Script`**
  (833 lines, Bash and SQL only, `default_statistics_target = 10000` so statistics are exact):
  `make check` All 225 plus All 1 / 8 / 30 on `pgstattuple`, `pageinspect` and `btree_gin`,
  and two complete passes agreeing on all 33 index rows, 11 GIN rows, 7 of 7 closed-form
  predictions and 116 plans. Every deterministic number of the unpublished 17.10 filing
  reproduced to the cent on a different OS and architecture; the sample-dependent ones were
  replaced. New measured findings: `12.29` against `4.44` for a one-row lookup on 2,745
  blocks over 1,000 rows; `tree_level` 2 against `fastlevel` 1 after a delete and two
  VACUUMs; 6 / 5 / 5 against 4 / 3 / 2 parallel workers at 100% / 50% / 20%; `0.66` against
  `2.50` per loop for a repeated inner scan; version churn that doubles under a held
  snapshot on a 1,000-value column (543 against 1,173 blocks) and not at all on a 100-value
  one (1,020 both); and a GIN index kept in a `BitmapAnd` at 25 times the price with 736
  pending pages and dropped at 1,471, the comparison that decides it being the two-index
  plan against the B-tree-only plan. Open questions stay at 10: two closed, two narrowed
  to their unmeasured halves, two added. Agent verification stays `not yet`.
- 2026-09-17: Filed [The I/O Consequences of Changing a Column From integer to bigint in
  PostgreSQL 17, Whether a Very Large Table Needs a Migration Strategy, and What Changed
  Since PostgreSQL 12
  (unverified)](v17/questions/storage-and-vacuum/alter-column-int-to-bigint-io.md) at
  unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, measured on **both** legs
  from one published two-script `## Measurement Script` (`make check` **All 225** on
  17.11 and **All 192** on 12.2, exit status 0 on both, 0 unexpected `ERROR`/`FATAL`
  lines). `int` -> `bigint` can never be catalog-only: `pg_cast` records a function cast
  and `ATColumnChangeRequiresRewrite` exempts only `Var`, `RelabelType`, unconstrained
  domains and the timestamp pair, so the statement rewrites the table and rebuilds every
  index under `AccessExclusiveLock` held to commit - and takes `AccessExclusiveLock` on
  every *other* table whose constraints it rebuilds. Headline measurements on a
  208,642,048-byte, 4,000,000-row table with two indexes: **72,413 blocks read**, which
  is exactly 25,469 + 2 x 25,536 (the old heap once, the new heap once per index
  rebuild), **427,512,848 bytes of WAL** against 12.2's **484,674,144**, a
  **+327,442,432-byte** data-directory peak matching new heap plus new indexes to
  8,192 bytes and returned at commit, and **3,951 ms** of exclusive lock. The v17 delta
  is the read *shape*: the same 593,007,616 bytes took **4,576** read calls on 17.11 and
  **72,373** on 12.2, and a controlled pair on identical 5,406-block tables measured
  **341** calls at the default `io_combine_limit` against **5,407** at `8kB` - 12.2's
  5,406 to the call. Also filed: a 417,792-byte heap with a 109,232,128-byte TOAST table
  cost **111,148,848 bytes of WAL** because the insert path fetches every external value
  back and re-toasts it; widening a referenced primary key moved `conpfeqop` to `{416}` =
  `=(int8,int4)` and drove **one seq scan over all 8,850 pages** of the 2,000,000-row
  child, which is never rewritten; row width grew by **0 bytes** on `(int,float8)` and
  `(int,int,text)` and by 8 bytes on `(int,text)` and `(int,int)`, so "4 bytes per row"
  is never the answer; `wal_level = minimal` cut WAL to **161,016** bytes while
  `SET wal_skip_threshold = '4GB'` put it back to **26,315,416** (12.2: 151,928 either
  way, having no such GUC); and the add-column/batched-backfill/`CREATE UNIQUE INDEX
  CONCURRENTLY`/catalog-swap route cut the exclusive lock to a **305 ms** window but cost
  **1,634,508,136 bytes of WAL**, 3.8x the single `ALTER`, leaving the heap at 2.15x with
  `n_tup_hot_upd` **0 of 4,000,000**. Logical replication into an already-widened copy
  works (100,000 rows copied `integer` -> `bigint`) because columns map by name and text
  values go through the *local* type's input function, but `binary = true` broke apply
  with **6** `insufficient data left in message` errors - an option 12.2 rejects
  outright. Twelve since-v12 changes are attributed to commits and first-release tags by
  presence tests at `REL_12_0`..`REL_17_0`, including `wal_skip_threshold` (v13),
  deduplication shrinking the rebuilt indexes from 179,855,360 to 118,243,328 bytes
  (v13), `reltuples = -1` (v14), extended statistics dropped and recreated so their data
  is gone where 12.2 kept ndistinct (v14), bulk relation extension (v16, and the 34
  extra blocks every 17.11 rewrite left behind), `pg_stat_io` (v16) and the read stream
  (v17); unchanged are the one-WAL-record-per-row copy and the absence of any progress
  view. **Nine open questions** lead with those 34 unattributed blocks and with the fact
  that the "680 GB is about 2.3 hours" figure is arithmetic from one 3,951 ms run at
  `fsync = off`. `verified:` untouched; agent verification stays `not yet`. Both servers
  were stopped and the sandbox deleted.

- 2026-09-17: Reviewed, corrected and re-measured [Pros and Cons of a Very Large
  shared_buffers Such as 256 GB on a 1 TB RAM System in PostgreSQL 17, and What Changed
  Since PostgreSQL 12
  (unverified)](v17/questions/storage-and-vacuum/very-large-shared-buffers.md) at
  unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, against a review that listed
  **16 defects** in the filing below: nine wrong or overstated source claims, four script
  defects, and three omissions from the since-v12 history. The same review **capped every
  `shared_buffers` the page's script may name at 4 GiB**, in a running server and in a
  non-allocating `postgres -C` probe alike, so the ladder became 1/2/3/4 GiB and **no
  number on the page is measured above 524,288 buffers**. The script is now 1,111 lines
  and ran end to end from a wiped sandbox: core regression **All 225 tests passed**,
  `pg_buffercache` **All 1 tests passed** (both checked on exit status as well as on the
  result line), **0** `ERROR`/`FATAL` lines. **Every 256 GiB figure is now arithmetic**:
  a model of `BufferShmemSize`, `StrategyShmemSize`, `hash_estimate_size`,
  `CheckpointerShmemSize` and the 8 kB round-up, fitted to four segments measured
  *exactly in bytes* as `sum(allocated_size)` over `pg_shmem_allocations`, reproduces all
  three checks to within one constant 8,192-byte page and then gives
  **280,492,630,016 bytes** at 33,554,432 buffers - **267,499 MB** as
  `shared_memory_size` would print it, with **133,750** 2 MiB or **262** 1 GiB huge pages,
  the same values the earlier uncapped `-C` run had measured. The marginal cost now
  decomposes exactly: 8292 for the four arrays + 32 for a sync slot + 40 for a
  mapping-table element + **64.94 for three still-growing SLRUs** = 8428.9 against
  **8426-8451** measured, and because those SLRUs cap at exactly `NBuffers = 524,288` -
  the cap itself - the 8364 and 8332 figures above it are arithmetic too. The 257 MiB
  mapping-table step was measured at the **2^18** boundary (+2 MB) and computed at 2^25
  as 256 MiB of bucket segments plus 1 MiB of directory. New slopes: **11.0 ns/buffer**
  per whole `CHECKPOINT` (6.09 to 10.42 ms median, with **0** dirty buffers before each
  sequence and **0-6** written across six checkpoints - the first filing's timer had been
  inserting its result row *between* checkpoints, inflating the 1 GiB median from 6.09 to
  9.5 ms), **71 ns/buffer** of server start (25 to 53 ms, minima over **10** restarts per
  size with medians printed beside them, because at these sizes one trial cannot see the
  slope), **6.6 ns/buffer** per `DROP` and **9.6** per `TRUNCATE` timed with
  `synchronous_commit = off`, and batching 30 drops into one transaction **11x** cheaper.
  **The fork claim is reversed**: `DropRelationBuffers()` takes a fork array and has one
  `NBuffers` loop, `RelationTruncate()` hands it every fork in one `smgrtruncate2()`
  call, a 222/3/1-block three-fork `TRUNCATE` cost **1.15x** not 3x, and the
  one-pass-per-fork behaviour the first filing described is PostgreSQL 12's - commit
  `6d05086c0a79`, first in 13.0, now a since-v12 row beside 17.6's `e4b8f925a929`
  autoprewarm `MCXT_ALLOC_HUGE` fix, without which a pool over ~53.7 million buffers
  cannot be dumped at all. Eight further corrections: `evictions`/`reuses` count claiming
  any valid victim rather than writing (37,352 reuses with 0 evictions and no writes);
  the background writer's `NBuffers / (120000 / bgwriter_delay)` target counts
  already-clean reusable buffers, so it is not comparable with the 100-page write cap;
  `num_requested` includes manual and DDL checkpoints and `buffers_written` counts
  performed writes; an ordinary buffer lookup shares a cached page whatever
  `synchronize_seqscans` says; the `CREATE DATABASE` `DropDatabaseBuffers()` caller is
  `createdb_failure_callback()`; the sync queue keeps its queue-full and
  no-checkpointer fallbacks; `backend_flush_after` is `PGC_USERSET`, not `PGC_SIGHUP`;
  and a `VACUUM` ring can be *asked* for at most 16 GiB even where `NBuffers / 8` is
  32 GiB. The floor probe now **starts a real server** (128 kB, 8 MB of shared memory,
  415 rows answered) because `-C` exits before shared memory is created. Re-measured:
  the ring at exactly **16 / 256 / 16,384 / 41,122** main-fork blocks on a fixture
  rebuilt per limit with a fork filter, `pg_buffercache` rows at **103.1 ms** against
  1.8 ms, a **controlled** direct-I/O pair at 511.7 against 31.2 ms on one fixture at one
  `io_combine_limit`, and **37,495 reads at all four** combine limits while `read_time`
  moved 39.0 -> 27.9 ms. The script gained a 4 GiB cap guard, an `EXIT` trap, checked
  exit statuses throughout, array-buffered timers, and a teardown that asserts both
  clusters down; **11 open questions** now lead with the cap itself and include an
  unexplained `TRUNCATE`-versus-`DROP` gap. 257 citation occurrences over 51 files, all
  in bounds. `verified:` untouched; agent verification stays `not yet`. Both clusters
  were stopped and the sandbox deleted.

- 2026-09-17: Filed [Pros and Cons of a Very Large shared_buffers Such as 256 GB on a
  1 TB RAM System in PostgreSQL 17, and What Changed Since PostgreSQL 12
  (unverified)](v17/questions/storage-and-vacuum/very-large-shared-buffers.md) at
  unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, the v17 counterpart to the
  v12 page of the same name. **The asker chose to build and measure**, so the page
  carries a 695-line published script that ran end to end on 2026-09-17: core regression
  **All 225 tests passed**, `pg_buffercache` **All 1 tests passed**, and **0**
  `ERROR`/`FATAL` lines in the measurement cluster's log. The host has 31 GiB of RAM, so
  **no figure was measured at 33,554,432 buffers**; instead `postgres -C
  shared_memory_size` prices a 256 GiB pool exactly - **267,499 MB**, 5,355 MB of it
  bookkeeping, **133,750** 2 MiB huge pages or 262 1 GiB pages - because that option
  exits before `CreateSharedMemoryAndSemaphores()`. The sweep also found a **257 MB**
  step between 33,554,304 and 33,554,305 blocks, where `NBuffers +
  NUM_BUFFER_PARTITIONS` pushes the mapping table's bucket array from 2^25 to 2^26, so
  `'255GB'` is cheaper than `'256GB'`; and marginal cost of **8331** bytes per buffer
  away from boundaries against **8364** below 10,000,000 blocks, which is 17.6's new
  `MAX_CHECKPOINT_REQUESTS` cap made visible. Measured slopes between 16,384 and
  2,097,152 buffers: **10.7 ns/buffer** for a checkpoint's full-header scan, **90
  ns/buffer** for shared-memory creation plus `InitBufferPool`, and **5.9 ns/buffer** for
  every `DROP`/`TRUNCATE`. The drop figure needed two corrections during the run: the
  buffer-pool pass happens in `smgrDoPendingDeletes()` at commit, so the timer had to
  become a procedure that commits inside the measured interval, and the v14
  `BUF_DROP_FULL_SCAN_THRESHOLD` shortcut turns out to be unreachable on a primary
  because `smgrnblocks_cached()` answers only `InRecovery`. Batching 30 drops into one
  transaction measured 10x cheaper than one transaction each, and `TRUNCATE` did **not**
  multiply with fork count. Also filed: the `NBuffers / 4` line measured as 18,692 of
  18,692 blocks resident below it against **32** - exactly the 256 kB ring - above it,
  the `NBuffers / 8` ring cap read back as 16,399 blocks, SLRU auto-sizing 32 -> 256 ->
  1024 blocks, `pg_buffercache` rows at 445.8 ms against 8.0 ms for
  `pg_buffercache_summary()`, `debug_io_direct = data` at 522.2 ms against 43.7 ms of
  `read_time`, four startup error paths, a 22-row since-v12 delta table attributed to
  commits and first release tags, eight unchanged mechanisms, 26 settings with apply
  scopes, and **nine open questions** led by the unmeasured 256 GiB case and an
  inconclusive `io_combine_limit` result. 253 citation occurrences over 159 distinct
  ranges in 50 files, all in bounds. `verified:` untouched; agent verification stays `not yet`. The
  server was stopped and the sandbox deleted.

- 2026-09-17: Reviewed [A COMMENT-Stored Baseline and Normalized Index Growth for Finding
  GIN Indexes That Need REINDEX CONCURRENTLY in PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-reindex-normalized-growth-comment-baseline.md) end
  to end at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, as the **last consumer
  page brought onto** [Mandatory GIN Bloat
  Tests](v17/common-concepts/mandatory-gin-bloat-tests.md)'s **`### The maintenance must not
  be defeated`**, the rule that page gained on 2026-09-15 *after* this page's own run. **All
  154 citations (73 distinct ranges over 29 files) were re-read against the pin and every one
  is in bounds and supports its label**, so the pass corrected no citation and added 23
  ranges instead, taking the page to 208 occurrences over 96 ranges in 32 files. The filed
  script was edited in place: every settle and maintenance statement now runs through one
  helper that forces `statement_timeout`, `lock_timeout`, `transaction_timeout` and
  `idle_in_transaction_session_timeout` to `0` and prints them back, and one that parses the
  statement's own `VERBOSE` output and **dies rather than score** a defeated fixture, with a
  horizon reading on each side of every step and the three progress views counted at both
  ends of every page census. The programme was then run **twice** on Linux x86_64 (`make
  check` All 225 plus All 8 / 1 / 1 / 30 / 4 on `pageinspect`, `pgstattuple`,
  `pg_freespacemap`, `btree_gin` and `pg_trgm`, on both). **Nothing was defeated**: 79
  maintenance steps, **all four timeouts 0 on 79 of 79**, **`dead but not yet removable` 0 on
  78 of 78**, **0** skip lines, **0** cancellations, 158 horizon readings with 0 slots and 0
  prepared transactions, and the one declared exception — `s01`'s settling `VACUUM` under a
  held snapshot — reporting exactly **500,000**, which is the check that proves the snapshot
  pinned the horizon rather than merely existing. **Every scored cell of the 2026-09-15 pass
  reproduced**: the 24 decide and rebuilt sizes, all 24 `truth` values, the 19 `PASS` / 1
  `FALSE POSITIVE` / 0 `FALSE NEGATIVE` / 4 refusals, the six original invariants (24/24,
  25/25, 23/23, 23/23, 21/21, 21/23), the `reltuples` swing, the linearity curve, the
  `fastupdate` twins, the 64MB budget row, the pgstat race, the eleven edge cases and the
  verbatim lifecycle. **One verdict moved and two findings are new.** `c02`'s upper bound
  went from `HELD` (+0.01) to `VIOLATED` (−0.03 then −0.01), taking `est_reclaimable` to **13
  held / 8 violated**, and the cause is not the model but the method's own denominator: new
  probe P6 read `pg_class.reltuples` as 1,002,033 / 1,001,233 / 1,002,333 / 1,001,433 /
  1,002,633 over five `ANALYZE`s of an unchanged 1,000,000-row table, so the bound's verdict
  on that fixture sits inside its input's sampling noise. And the settle step the protocol
  mandates was measured to **add** bytes on **8 of 23** fixtures — 4,849,664 on `c01` and
  `c12`, 16,310,272 in total, 0 shrank — so part of what the method reads as growth is the
  `VACUUM`'s own allocation. The page gained three new declared invariants (I7 no-defeat, I8
  timeouts-and-completion, I9 progress views: 76/76, 76/76 and 27/27), five new open
  questions, and `verified_by_agent` stays `not yet`. `scripts/wiki_lint` reports 0 errors and
  0 warnings; the published 1,902-line script block is byte-identical (md5
  `188138052edd939818c5aeb46fffa660`) to the file that ran; the server was stopped and the
  sandbox deleted, with no `postmaster.pid`, no `postgres` process and port 55417 free.

- 2026-09-16: Reviewed and re-ran [Checking Whether an Index Needs a Rebuild to
  Enable Deduplication After pg_upgrade From PostgreSQL 12 to 17
  (unverified)](v17/questions/indexing/btree-deduplication-after-pg-upgrade.md) at
  unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`. **All 175 citations (73
  distinct ranges over 35 files) were re-read against the pin and every one is in
  bounds and supports its label**, so the pass corrected no citation and added 8
  ranges instead, taking the page to 203 occurrences over 81 ranges in 39 files.
  Every source-history claim held too: the four commits and their first release
  tags, the 193-commit repin range with `8434c938598` as its only `nbtree` change,
  and `git log -S allequalimage -- src/bin/pg_upgrade` still empty. The script was
  **re-run four times** on Linux x86_64 (`make check` All 225 plus `pageinspect`
  All 8, and All 192 on 12.2, on every run), and **every scored cell reproduced on
  all four**: the 26 carried-over files at 26 of 26 identical digests, the 189-row
  check at 162/15/6/5/1 verdicts with 27 flags false, the offsets (48/72 against
  40/64), the gate at 17 of 17, the curve, the twins, the churn, the 17 rebuild
  rows, the trap, the flag matrix, the fallback joins and the counters.
  **The review's main finding is a wrong verdict, not a wrong number**:
  `interval_ops` lost its equalimage support function in `5f27b5f848a` while v17's
  `btequalimage()` still returns true unconditionally, so an `interval` index built
  on a pre-fix 13-16 cluster carries the flag **true** into v17, where
  `_bt_allequalimage()` says false and `amcheck` raises "metapage incorrectly
  indicates that deduplication is safe" - and the filed check answered "no rebuild
  needed". The check now carries a `rebuild for correctness: metapage says safe,
  catalogs disagree` branch, which matched 0 rows on the measured 12 → 17 leg and is
  filed as source-verified and unexercised. Three further corrections: the refusal
  list is the 16 rows of `opr_sanity`'s expected output, so `interval`, `tsquery`
  and `tsvector` join the containers and `numeric`/`jsonb`/`float`; the partial
  index's triage row was wrong twice over, printing **9,673.4** rows per key against
  an exact **100,000 rows over one distinct key value** (the superseded "actual
  99,867 rows over 10 keys" was a sample and a table-wide `n_distinct`), with
  `reltuples` reading 101,667, 104,734, 98,700 and 96,734 across the four runs; and
  the XID sentence now says the restore consumed 487 up to 552 rather than being
  "one transaction past 487". The page also gained `_bt_first`, the posting-list
  asserts, both metapage WAL copies and `amcheck` as readers of the flag, a 176-row
  after-rebuild self-check, and the note that nothing upstream tests a carried-over
  metapage. Four script edits were made in place and then re-run: the new check
  branch, an exact-population probe for the partial index, per-run truncation of the
  server logs in `reset`, and an itemized `ERROR` audit in `summary` (6 lines on
  17.11, all deliberate; 0 on 12.2). `scripts/wiki_lint` reports 0 errors and 0
  warnings; the published script is byte-identical to the 1,148-line file that ran;
  both servers were stopped and the sandbox deleted, with no `postmaster.pid`, no
  `postgres` process and both ports free; human `verified:` is untouched and agent
  verification stays `not yet`.

- 2026-09-16: Reviewed [B-Tree Bloat and Wasted Space From pgstatindex Alone, on
  PostgreSQL 12 and 17
  (unverified)](v17/questions/indexing/btree-bloat-with-pgstatindex.md) end to end at
  unchanged pins `786db8dcf168bd9df8f55047337525ac19118b1c` and
  `45b88269a353ad93744772791feb6d01bc7e1e42`, as the **last of the three consumer
  pages brought onto** [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md)'s
  **`### The maintenance must not be defeated`**, the rule that page gained on
  2026-09-15, after this page's previous run. **All 328 citations (109 distinct
  ranges over 47 files) were re-read against the pin, content and all, and every one
  is in bounds and supports its label**, so the pass corrected no citation and added
  13 ranges instead, taking the body to 254 occurrences over 122 ranges in 50 files.
  Four of the five suite `sql` blocks were repaired in place: the harness gained the
  `maint`, `horizon` and `pageclass` tables and the `maint_begin()`, `maint_end()`,
  `maint_after()` and `horizon_probe()` functions; the 33 maintenance statements of
  the fixture file and the 38 of rule 2's drain each became one bracketed
  `VACUUM (VERBOSE, ANALYZE)`; and the census session, like the other two, now runs
  with every settable timeout at 0 and probes the horizon on both sides. Both leg
  scripts gained a per-leg `parse_verbose`, a `maint_proofs` that **dies rather than
  score**, a skip-line check reading from a maintenance mark the suite stage writes,
  and a per-invocation run mark for the error audit. Both legs were rebuilt from
  their pins and re-run in **one invocation each** on Linux x86_64 (`make check`
  All 225 plus All 1; All 192 plus All 1). **Nothing was defeated**: 67 maintenance
  statements per leg - 38 `drain`, 28 `fixture`, 1 `prebuild` - all completed,
  **`dead but not yet removable` 0 on every one**, **73 of 73** horizon probes clean
  on each leg, one timeout set per leg (four zeros on 17.11, three and `n/a` on
  12.2), **0** skip or cancellation lines, and 10,340 and 11,868 deleted index pages
  recorded over 126 and 117 page-classed indexes. The score reproduces the
  2026-09-13 run fixture for fixture - **`PASS` on 126 of 126 on 17.11 and 117 of
  117 on 12.2**, 0 false positives, 0 false negatives, the same three `want_stage`
  misses, `+10.0` and `+6.3` worst over-estimate, `−4.1` worst under-estimate on
  both - and moves only where test 120's probabilistic precondition held on both
  legs this time, taking the 17 leg from 125 scored to 126 and from 92 to 93 within
  one point of the oracle. One new honest reading: the `decide` stage's
  report-versus-view check found **one** shared row disagreeing on 17.11,
  `pg_toast.pg_toast_2618_index`, which the harness view's own creation wrote
  between the two readings; no fixture disagreed on either leg. Two open questions
  were added for the proofs' limits - the horizon probe is a read beside the
  statement rather than an interlock, and the `bl` guard fixtures are outside the
  rule. `scripts/wiki_lint` reports 0 errors and 0 warnings; the published script
  and `sql` blocks are byte-identical to the files that ran; both servers were
  stopped and the sandbox deleted, with no `postmaster.pid`, no `postgres` process
  and both ports free; human `verified:` is untouched and agent verification stays
  `not yet`.

- 2026-09-16: Reviewed [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on
  PostgreSQL 17 (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md)
  end to end at unchanged pins `786db8dcf168bd9df8f55047337525ac19118b1c` and
  `45b88269a353ad93744772791feb6d01bc7e1e42`, as the **third consumer page brought
  onto** [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md)'s
  **`### The maintenance must not be defeated`**, a rule that page gained after this
  page's previous run. **All 717 citations (238 distinct ranges over 88 files) were
  re-read against the pin and every one is in bounds and supports its label**, so the
  pass corrected no citation. Both scripts were repaired in place: the 33 maintenance
  statements of the 17 leg's fixture file, its two drains, the 12 leg's three fixture
  statements, its drain and its `extstat` fixture each became one
  `VACUUM (VERBOSE, ANALYZE)` between `maint_begin()` and `maint_end()`, in a session
  with all four settable timeouts at `0` (three on 12.2, which has no
  `transaction_timeout`), with new `maint`, `horizon` and `pageclass` tables, a Bash
  `VERBOSE` parse per server, a skip-line check, a page-class read and a proofs check
  that **dies rather than score**. Both legs were rebuilt from their pins and run once
  each from a fresh `initdb` (`make check` All 225 plus 8, 1 and 3; All 192 plus 5, 1
  and 2). **Nothing was defeated**: 68 maintenance statements on 17.11 and 9 on 12.2,
  all completed, **`dead but not yet removable` 0 on every one**, 76 of 76 and 11 of 11
  horizon probes clean, 0 skip or cancellation lines, one timeout set per leg, and
  9,626 + 714 + 15,794 deleted index pages recorded. The report shape reproduces the
  2026-09-14 filing to the row - **68 rows against the superseded text's 20, 45 of them
  1 MB or smaller, and 19 on 12.2** - which required removing the proof tables' primary
  keys, since a harness index in `public` enters the report under test and took it to
  70. The score moves by one fixture, **97/4/0/25 against 96/4/0/26**, and the mover is
  the `ANALYZE` sample: `p41` crossed the deduplication-credit boundary that had
  withheld it and repaid 75.2 % against a reading of 74.4 % in both runs, while its
  `ndistinct`-carrying twin `p45` stayed withheld. One repair improved the 12 leg
  outright: rule 3's census now analyzes **0 of 9** tables rather than 2, because the
  bracketed maintenance restores the publication order rule 3 requires on a server with
  no `pg_stat_force_next_flush()`. Two Markdown table rows with a stray leading pipe
  were repaired. `scripts/wiki_lint` reports 0 errors and 0 warnings; the published
  script blocks are byte-identical to the files that ran; both servers were stopped and
  the sandbox deleted, with no `postmaster.pid`, no `postgres` process and both ports
  free; human `verified:` is untouched and agent verification stays `not yet`.

- 2026-09-16: Reviewed and re-ran [Measuring Wasted and Reclaimable Bytes in a GIN
  Index With Contrib Extensions on PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md) at
  unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`. Scope was source
  re-verification **plus** a full re-run of the page's own published script.
  **All 605 citations (284 distinct ranges over 79 files) were re-read against the
  pin and every one is in bounds and supports its claim**; the page's two repo-wide
  greps were re-run too. 17.11 was rebuilt out of tree and the whole default stage
  order ran **twice** (`make check` All 225 plus All 8 / 1 / 1 / 30 / 4). **Every
  scored cell reproduced**: the 27-index page census, all byte and percentage
  columns, the 19 `truth_pct` values, the payload model's 19 errors, the baseline
  phase, the pending-list lifecycle, the horizon sequence, the 102-table simulated
  census, the privileges, the refusals, the standby and all eight corruption shapes
  came out identical to the 2026-09-15 filing, on two freshly initdb'd clusters, so
  the bound verdicts stand at **19 of 19 upper, 17 of 19 lower**. Eight filed items
  did not survive and were corrected in place: the metapage entry-page cross-check
  is **24 of 27, not 25** (`l1_lock_gin` 9 against 34 is a third stale-metapage
  index), a `0 / 0 / 0` VACUUM line attributed to `f5` belongs to the held-snapshot
  fixture `f8`, a standby census quoted 482 blocks for an 898-block fixture, an FSM
  shortfall list of four was called five, four timing figures moved (172 ms of lock,
  3395 ms of queued VACUUM, the three cost columns, one cancellation), a
  `PageAddItem` was credited to `entryPreparePage` instead of
  `entryExecPlaceToPage`, one function was cited at two line ranges, and two
  Markdown defects (a heading with no blank line, a table row split across two
  lines) were repaired. One script change closes a `MANDATORY Measurement Script`
  hole rather than a claim: the *after `REINDEX`* entry-tuple column had no stage
  producing it, so a **`probe_after`** stage now re-runs the probe on the rebuilt
  indexes, and it returned the filed dead-key counts exactly. New open question 21
  records that run-to-run stability is now measured on one machine only.
  `scripts/wiki_lint` reports 0 errors and 0 warnings; the published script is
  byte-identical to the file that ran; the sandbox was stopped and deleted, with no
  `postmaster.pid`, no `postgres` process and both ports free; human `verified:` is
  untouched and agent verification stays `not yet`.

- 2026-09-16: Re-verified and extended the PostgreSQL 12.2
  [very-large-shared-buffers review](v12/questions/storage-and-vacuum/very-large-shared-buffers.md)
  at unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`. Every claim and all
  **163** citation ranges were re-read against the pin: **none was wrong**, so this pass
  added the omissions instead of corrections, taking the page to **188** ranges. It
  **supersedes the "19 settings" and "all nine `NBuffers`-derived values" counts** in the
  original filing note below; the settings table now carries **22** rows, gaining
  `pg_prewarm.autoprewarm` (restart) and `pg_prewarm.autoprewarm_interval` (reload).
  The headline addition closes the page's own open question: the buffer-mapping hash is
  **≈1.75 GiB** by arithmetic on `hash_estimate_size()`, making it the largest non-page
  consumer and raising the overhead beyond the pages from 4.375 GiB to **≈6.13 GiB** —
  and because `StrategyShmemSize()` asks for `NBuffers + NUM_BUFFER_PARTITIONS` entries,
  **2^25 buffers sits 128 past a power-of-two bucket cliff**, so `shared_buffers = 33554304`
  gives up one MiB of cache and saves about **257 MiB**. Also new: the `NBuffers`-scaled
  `AbsorbSyncRequests()` copy (768 MiB at a full queue) and `CompactCheckpointerRequestQueue()`
  allocations, both under an exclusive lock; a `## Hard limits above 256 GB` section
  (**8 TiB minus one block**, autoprewarm's dump from **409.6 GiB**, a full-queue drain from
  **341.3 GiB**); `DROP_RELS_BSEARCH_THRESHOLD` = 20 and its **671,088,640** comparisons;
  three full-pool passes for a both-forks truncation; the 300-second autoprewarm dump period;
  the tree's own **`XXX currently it sequentially searches the buffer pool`** comment with a
  census proving the five-function list closed; the `NBuffers`-relative checkpoint-log
  percentage; and `buffers_alloc` excluding ring-recycled buffers. Open questions went from
  6 to **9**. Still source-only with no `## Measurement Script`: no server was built,
  nothing was measured, nothing needed tearing down. `scripts/wiki_lint` reports 0 errors and
  0 warnings; human `verified:` stays false and agent verification stays `not yet`.

- 2026-09-16: Corrected the PostgreSQL 12.2 [very-large-shared-buffers review](v12/questions/storage-and-vacuum/very-large-shared-buffers.md). This review supersedes the original coverage summary below where it asserted fixed write counts, an allocation sweep bound, universal layouts, or overly broad monitoring semantics. The revised page distinguishes source-derived arithmetic from measurements, documents contrib allocation limits, corrects database/DDL callers and counter meanings, and adds build/generated-header context. Human verification remains false; no measurements or services were run.

- 2026-09-16: Filed [Pros and Cons of a Very Large shared_buffers Such as 256 GB on a
  1 TB RAM System in PostgreSQL 12
  (unverified)](v12/questions/storage-and-vacuum/very-large-shared-buffers.md) at
  unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`. **Source-only by the
  asker's choice**: no server was built, nothing was measured, and there is no
  `## Measurement Script` section. The asker also chose **correct and restate** for the
  prompt's seven defects and **v12-only framing**, all three recorded under the page's
  `## Question`. The answer's spine is that 256 GB is legal (`PGC_POSTMASTER`, ceiling
  `INT_MAX / 2` blocks) and inside the shipped docs' own 25 %-of-RAM starting point,
  but at the default block size it is **33,554,432 buffers**, and v12 has several
  O(`NBuffers`) paths whose cost tracks the pool while the work does not. Six pros and
  thirteen cons, each cited: the hit path returns before `smgr`, a dirty victim is
  written by the requesting backend after an `XLogFlush`, `BufferSync()` spinlocks
  every buffer per checkpoint, and the five "find all buffers of X" functions carry the
  tree's own **`XXX currently it sequentially searches the buffer pool`** comment, with
  a table mapping each to the commands that reach it - `DROP`, VACUUM truncation and
  its redo, `ALTER TABLE ... SET TABLESPACE`, `heap_sync`, `CREATE`/`DROP DATABASE`.
  The finding most likely to surprise an operator is the **`NBuffers / 4`** bulk-read
  and synchronized-scan threshold, which at this size rises to **64 GiB** and withdraws
  the buffer-ring's cache-flood protection from every smaller sequential scan. Also
  filed: the five per-buffer shared-memory arrays plus the `NBuffers`-long checkpointer
  fsync queue, the clock sweep's stated `BM_MAX_USAGE_COUNT + 1` pass bound, the 100-page
  `bgwriter_lru_maxpages` cap that does not scale, all nine `NBuffers`-derived values,
  what a big pool does **not** buy (temp tables, VACUUM's 256 kB ring, planner costing,
  the CLOG and commit-timestamp SLRUs, `wal_buffers`), **19 settings with exact
  restart/reload/session scopes**, and three catalog-verified monitoring statements.
  Eight open questions, led by the fact that the per-buffer byte totals are arithmetic
  on the struct definitions rather than a reading from a server, and that **no test in
  the checkout exercises a large pool** - the largest test setting found is 1 MB.
  `scripts/wiki_lint` reports 0 errors and 0 warnings. Nothing was started, so nothing
  needed tearing down, and **agent verification stays `not yet`**. v12 still has no
  `common-concepts/` directory, so the buffer manager, clock sweep and buffer access
  strategies are explained inline and named as proposed concept pages.

- 2026-09-16: Re-ran [A COMMENT-Stored Baseline B-Tree Index-Maintenance Heuristic for
  PostgreSQL 12 Through 17
  (unverified)](v17/questions/indexing/btree-comment-baseline-maintenance-heuristic.md)
  end to end on both legs at unchanged pins `786db8dcf168bd9df8f55047337525ac19118b1c`
  and `45b88269a353ad93744772791feb6d01bc7e1e42`, as the **second consumer page**
  brought onto **`### The maintenance must not be defeated`** and the **first** brought
  onto the full maintenance assumption of [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md). The 2026-09-14
  departure is closed: a maintenance step runs `VACUUM (VERBOSE, ANALYZE)` on every table
  the churn touched - the set taken from the engine's own write counters, **66 tables on
  17.11 and 65 on 12.2**, **18,066,916** and **17,617,051** dead tuples removed - and
  every churn-free table is left alone so that family 3's deliberately stale statistics
  survive. The rule's four proofs are recorded per table: every statement completed,
  **`dead but not yet removable` 0 on all 66 and all 65**, **69 of 69 and 68 of 68**
  horizon probes entirely clean with 0 slots and 0 prepared transactions, **0 skip or
  cancellation lines**, and 10,340 and 11,868 deleted index pages; every `VACUUM`/`ANALYZE`
  session now forces its timeouts to **0**, as the autovacuum launcher and worker do to
  themselves, where the previous run's churn sessions ran at `lock_timeout = '5s'`.
  **Neither filed text changed and the score did not move**: **125 of 126 `PASS` on 17.11
  with 1 `UNMET PRECONDITION`, 112 of 112 on 12.2**, 0 false negatives, 0 false positives,
  95 and 81 rebuilds at 86.2 % and 87.1 % mean reclaim, mean reading error `+7.6` over 103
  scored measurements. What moved is `b93`/`b95`, now under-reading the oracle by **9.4**
  points instead of 18.2, because the maintenance removes the dead entries their trailing
  `UPDATE` left. **Fixture 120's precondition is asserted rather than assumed** - the
  previous run credited a `PASS` to a fixture whose state never arrived - and across five
  complete passes it read 2,034 / 1,667 / 0 / 1,800 / 1,600 on 17.11 and 0 / 13,335 /
  3,334 / 0 / 0 on 12.2, arriving on 4 of 10 fixture builds. Three harness defects were fixed: the missing
  precondition check, a publication invariant that mistook a recipe's own `ANALYZE` for an
  unpublished counter, and a `check` stage that wrote into a directory that did not exist
  when a run started from a built tree. Rule 3's census now decides only unchurned tables,
  12 of 88 and 4 of 87, with 12 of 12 and 4 of 4 counters verified reset. **125 of 126 and
  112 of 112 per-fixture result tuples are identical to the preceding pass** on a separate
  cluster from the same pin, the exception being `p120`. Open questions went from 15 to
  **18**: the horizon proof is a pair of reads rather than an interlock, forcing the
  timeouts to 0 leaves the cut-short maintenance state unmeasured, the maintained set is
  derived from counters a `TRUNCATE` would not move, and `clean` is not leg-local -
  the two legs share `$SANDBOX`, so cleaning one leg deletes the other's cluster, which
  an earlier teardown in this review did to a still-running 12 postmaster before the
  published pass was torn down in the documented order.
  `scripts/wiki_lint` reports 0 errors and 0 warnings; 193 citation links over 82
  distinct ranges in 34 files all resolve and are in bounds; both published leg scripts
  were verified byte-identical to the files that ran; the 9 GB sandbox is deleted and no
  `postgres` process, data directory or socket survives; **the concept page was read and
  not edited**, and **agent verification stays `not yet`**.

- 2026-09-16: Re-ran [Detecting Inflated Non-B-Tree Indexes From Catalogs and a
  COMMENT-Stored Baseline in PostgreSQL 17
  (unverified)](v17/questions/indexing/non-btree-index-inflation-comment-baseline.md)
  end to end at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, this time
  under **`### The maintenance must not be defeated`** - the rule
  [Mandatory Non-B-Tree, Non-GIN Bloat Tests
  (unverified)](v17/common-concepts/mandatory-non-btree-non-gin-bloat-tests.md) and
  [Mandatory GIN Bloat Tests (unverified)](v17/common-concepts/mandatory-gin-bloat-tests.md)
  both gained on 2026-09-15, *after* this page's last run, and which the concept-page
  entries named it as never having been checked against. It is the **first consumer
  page brought onto that rule**, and the review's finding is that **the page's two
  held-snapshot fixtures had never pinned the horizon at all**: `g08` and `n10` opened
  their snapshot *after* the churn committed, so its `xmin` was already past the
  deleting xid and nothing was held back. The previous run had blamed the recipe shape
  and proposed a contiguous key band as the next attempt; that was half the defect and
  not the decisive half. With the snapshot opened **before** the churn and the delete
  changed to a contiguous id band, the maintenance `VACUUM` now reports **240,000** and
  **960,000 tuples dead but not yet removable** and deletes **no index page** (`pages:
  2970 in total, 0 newly deleted` and `479 in total, 0 newly deleted`), while the
  `VACUUM` after release deletes **2,330 of 2,970** GiST pages and **375 of 479** GIN
  posting-tree pages, both at FSM count **0** - the deleted-but-not-recyclable behavior
  both protocols require and neither fixture had reached. **On GIN the defeat is
  reassuring rather than merely silent**, exactly as the GIN page warns: under the held
  snapshot the metapage identity and the `VERBOSE` `num_pages` both **passed** on a
  `VACUUM` that removed not one entry, and only the `dead but not yet removable` count
  and the horizon read caught it. Four new invariants, filed before any fixture
  existed, cover the rule: **27 of 27** clean `VACUUM`s outside the two declared
  exceptions, **33 of 33** maintenance logs neither skipped nor cut short with all four
  settable timeouts forced to `0` as an autovacuum worker forces them to itself, **0
  overlaps** between 96 census lock intervals and 33 maintenance intervals, and **62 of
  66** horizon readings entirely clean with **0** replication slots and **0** prepared
  transactions throughout; five exceptions (X1-X5) are declared rather than satisfied.
  The scores are stable across the change: **30 of 31** decisions right, 0 false
  positives, 1 false negative on `VACUUM (INDEX_CLEANUP OFF)`, 14 flagged each repaying
  37.6-85.7 %, and `est_reclaim_pct` **failing again** as an upper bound (19 held, 12
  violated, up to 11.94 points) so it stays demoted to a level, within 1 point of the
  oracle on 21 of 29. **29 of 31 `(B, C, R)` triples are byte-identical to the
  2026-09-15 run** on a separate cluster from the same pin; the exceptions are `n10`,
  rebuilt on three hot keys at 1,200,000 rows after a 300,000-row version fell under the
  method's own 1 MB floor, and `g09`, whose churned file has now read three different
  values. Two earlier passes of the script were abandoned and contribute no number, and
  the `declare` stage's own guard refused twice, which is what kept the declaration
  ordering honest. The filed script grew from 2,364 to **2,640 lines** and was verified
  byte-identical to the file that ran; the three published statements re-extracted from
  the page at 81, 23 and 195 lines, **3 of 3 identical**. Open questions went from 17 to
  **20**, the new ones being that the horizon proof is a pair of reads rather than an
  interlock, that scoring a fixture which declares an exception is a judgement this page
  made rather than derived, and that forcing the timeouts to `0` removes a hazard but
  leaves the cut-short maintenance state unmeasured. `scripts/wiki_lint` reports 0
  errors and 0 warnings; 250 citations over 110 distinct ranges in 55 files all resolve
  and are in bounds; the script's `clean` stage stopped the server and deleted the
  sandbox; **neither concept page was edited** and **agent verification stays `not
  yet`**.

- 2026-09-15: Added one shared rule, **`The maintenance must not be defeated`**, to all three
  v17 bloat-protocol concept pages - [Mandatory Non-B-Tree, Non-GIN Bloat Tests
  (unverified)](v17/common-concepts/mandatory-non-btree-non-gin-bloat-tests.md),
  [Mandatory B-Tree Bloat Tests (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md)
  and [Mandatory GIN Bloat Tests (unverified)](v17/common-concepts/mandatory-gin-bloat-tests.md) -
  at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, as three sequential tasks with
  three log entries. The review question was whether any of them mandated that a test must not
  create abnormal engine conditions that prevent autovacuum, `VACUUM`, `ANALYZE` or auto-analyze.
  **None did.** All three enforced *issuing* the maintenance - `VACUUM ANALYZE` after every churn,
  no exemption from `autovacuum = off` or `autovacuum_enabled = false`, no unmaintained churn -
  and none enforced its *effect*; worse, two of them **require** a held-snapshot fixture and a
  `VACUUM` whose index cleanup did not run, and two own a `SHARE ROW EXCLUSIVE` measurement lock
  that excludes `VACUUM` and `ANALYZE` by design. The new rule forbids five states from the first
  churn statement to the end of the census: an open transaction or held snapshot anywhere in the
  cluster other than a lazy `VACUUM`, a prepared transaction, a replication slot holding an
  `xmin`, a lock conflicting with `ShareUpdateExclusiveLock` across the maintenance statement, and
  a `statement_timeout`, `transaction_timeout` or `lock_timeout` short enough to fire inside it.
  The evidence is the same on all three pages: `vacuum_get_cutoffs` takes `OldestXmin` from
  `GetOldestNonRemovableTransactionId`; `ComputeXidHorizons` folds in every backend's `xmin` and
  any slot's, skipping only `PROC_IN_VACUUM`/`PROC_IN_LOGICAL_DECODING`; a prepared transaction's
  dummy `PGPROC` keeps its xid running; under a pinned horizon rows stay
  `HEAPTUPLE_RECENTLY_DEAD` and `lazy_scan_heap` never enters `lazy_vacuum`; a non-wraparound
  worker gets `VACOPT_SKIP_LOCKED` and logs `lock not available`; a backend queued behind one
  sends `SIGINT`; and the launcher and worker force all four settable timeouts to `0` "to avoid
  letting these settings prevent regular maintenance from being executed". Each page keeps its own
  consequence: **B-tree** loses page recycling too, because `_bt_pendingfsm_finalize` stops at the
  first page `GlobalVisCheckRemovableFullXid` refuses, so `pgstatindex` keeps reporting
  `deleted_pages`; **GIN** is the sharpest, because `ginbulkdelete` never runs while
  `ginvacuumcleanup`'s `stats == NULL` branch still flushes the pending list and rewrites the
  metapage, so **every settle-step proof passes with no entry removed**; and on the **non-B-tree**
  set a pinned horizon degenerates into exactly the cleanup-only call that page's per-AM proof
  table already describes. Each page gained a new `## Why It Exists` property, a per-fixture proof
  obligation, five to six `## Evidence Map` rows, a source-area row, a callers-and-callees row, a
  `## Context Reviewed` bullet, an extra VACUUM boundary under `## Interactions with Other
  Concepts`, one new open question (the effectiveness proof is one-sided: a nonzero `dead but not
  yet removable` count proves a pinned horizon, a zero count proves little, and
  `pg_stat_activity`/`pg_replication_slots` are reads rather than interlocks), and 19 to 24 new
  `## Source References` entries including three files no page had cited before - `procarray.c`,
  `twophase.c` and `proc.c`. No consumer page was edited, so the five pages that score against
  these protocols now face a rule they have never been checked against.
  `scripts/wiki_lint` reports 0 errors and 0 warnings; the pages are source-only, so no server was
  started and there is nothing to tear down; **agent verification stays `not yet` on all three**.

- 2026-09-15: Re-ran [Detecting Inflated Non-B-Tree Indexes From Catalogs and a
  COMMENT-Stored Baseline in PostgreSQL 17
  (unverified)](v17/questions/indexing/non-btree-index-inflation-comment-baseline.md)
  **end to end under both** [Mandatory Non-B-Tree, Non-GIN Bloat Tests
  (unverified)](v17/common-concepts/mandatory-non-btree-non-gin-bloat-tests.md) **and**
  [Mandatory GIN Bloat Tests
  (unverified)](v17/common-concepts/mandatory-gin-bloat-tests.md), at unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c`, closing the conformance gap the non-B-tree
  concept page had recorded the same day. It is the **third** consumer page brought onto
  a protocol and the **first under two at once**: its 21 hash, GiST, SP-GiST and BRIN
  fixtures run under the non-B-tree page and its 10 GIN fixtures under the GIN page.
  Every number now comes from **one published 2,364-line `## Measurement Script`** that
  builds 17.11 out of tree (`make check` **All 225** plus **All 8 / 1 / 1** on
  `pageinspect`, `pgstattuple` and `pg_freespacemap`), files the declared kind of every
  published column **27 minutes before the first baseline payload** and refuses to
  re-file once a fixture exists, and drives **31 scored fixtures** through build ->
  baseline -> churn (writes, maintenance step, census) -> a `SHARE ROW EXCLUSIVE` decide
  pass over every baselined index at once -> a measured `REINDEX INDEX` oracle, plus a
  34-table analyze census, nine invariants over 96 locked censuses, seven mechanism
  probes and 13 unscored edge cases. **The decision was right 30 of 31** (0 false
  positives, 1 false negative, 14 flagged and each repaying 37.6-85.7 %), and **the
  page's one declared bound failed**: `est_reclaim_pct`, filed as an upper bound, held on
  19 and was violated on 12 by up to 11.94 points, so it is **demoted to a level** even
  though it still lands within 1 point of the oracle on 22 of 29. Four results are about
  the gates: `VACUUM (INDEX_CLEANUP OFF)` produced the only false negative at 36.94 %
  reclaimable; **both auto-analyze stand-ins make the method refuse**, at 11.11 % and
  11.50 %, because a table maintained by auto-analyze alone never advances
  `vacuum_count`; all four no-churn fixtures are refused by the `ANALYZE` gate; and the
  **BRIN arm is still unvalidated**, all four BRIN fixtures reclaiming 0 bytes and all
  four silenced by the 1 MB floor while the maintenance step **grew** three of them. New
  coverage and findings: the maintenance pair on every fixture (7 of 31 moved, GIN by up
  to 39 %), the BRIN summarization stand-in with three desummarized ranges leaving
  exactly three orphaned line pointers, a hash rebuild sized from the **heap's** estimate
  (forging `reltuples` to 100 cost 4,775,936 bytes), a budget-dependent GIN rebuild
  (46,784,512 / 48,021,504 / 49,143,808 bytes at 4MB / 64MB / 256MB), the discovery that
  `brin_page_items` emits a row for an **unused** line pointer, and `brinvacuumcleanup`'s
  `VERBOSE` `num_pages` shown to predate its own summarization. The
  desummarize-plus-summarize refutation reproduced byte for byte on a fresh fixture
  (114,688 -> 196,608, `REINDEX` back to 114,688). **The 13-cell matrix, the
  pre-`VACUUM` evaluation, the six-run reproducibility claim and all 19 old probes were
  removed with the claims they backed**, and one known limitation is retired because an
  index with no baseline now produces no row at all. 17 open questions.
  `scripts/wiki_lint` reports 0 errors and 0 warnings; the script's `clean` stage stopped
  the server and deleted the sandbox; **agent verification stays `not yet`**.

- 2026-09-15: Filed [Mandatory Non-B-Tree, Non-GIN Bloat Tests
  (unverified)](v17/common-concepts/mandatory-non-btree-non-gin-bloat-tests.md), the
  wiki's **third** common concept page, at unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c`. It is the shared measurement protocol
  for every v17 index whose access method is neither B-tree nor GIN: **hash, GiST,
  SP-GiST and BRIN are scored**, and a four-part admission rule covers a non-core AM,
  with `contrib/bloom` as the worked example. Like the GIN page it is protocol-scoped
  and defines **no fixture corpus**. At the asker's direction it **keeps every
  autovacuum, VACUUM, ANALYZE and auto-analyze assumption** of
  [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md): `VACUUM ANALYZE`
  on every table the churn touched before the decide phase, no exemption from
  `autovacuum = off` or from a per-table `autovacuum_enabled = false`, no unmaintained
  churn, the launcher's three verdicts recorded with their five `PGC_SIGHUP` GUCs and
  six `ShareUpdateExclusiveLock` reloptions but applied on the analyze side only, and a
  census that recomputes `relation_needs_vacanalyze`'s strictly-greater test per table
  from the effective reloption-or-GUC values, with the negative-`reltuples` clamp, the
  `autovacuum_enabled` short circuit, two publication points and a
  `stats_fetch_consistency` read rule. **The port is not a copy**, for two reasons this
  AM set supplies. On BRIN the mandatory maintenance **grows** the index -
  `brinbulkdelete` removes nothing and `brinvacuumcleanup` summarizes every
  unsummarized range - so a BRIN fixture is measured on both sides of the maintenance
  step, and because the `autosummarize` work item `brininsert` queues is fulfilled only
  by an autovacuum worker, such a fixture runs a `brin_summarize_new_values()` or
  targeted `brin_summarize_range()` stand-in with three differences named; the
  measurement lock does exclude that stand-in, unlike GIN's index-only flush. The
  **auto-analyze stand-in, by contrast, is a plain `ANALYZE`**, because all four AMs
  no-op in ANALYZE-only mode - GiST, SP-GiST and BRIN test `analyze_only`, hash returns
  NULL stats - which is the other half of the `analyze_rel` comment that names GIN as
  the only core exception. Also filed: a per-AM proof obligation that the index work
  ran (including a hash cleanup that returns NULL and therefore prints no `VACUUM
  VERBOSE` line and writes no index statistics), one oracle with its per-AM inputs (a
  hash rebuild sized from the **heap's** estimate, a GiST sorted build that ignores
  fillfactor, SP-GiST's fillfactor target, BRIN's `pages_per_range`), an instrument
  matrix in which `pgstattuple` refuses SP-GiST and BRIN, `pageinspect` ships **no
  SP-GiST decoder**, and `amcheck` 1.4 verifies none of the four, six cross-checks, and
  the reading rules. **198 distinct citations, every one resolving and in bounds** in
  `raw/postgres-17/`; 13 open questions, led by the absent corpus, the four AMs'
  incomparability, BRIN's summarization-versus-bloat ambiguity, SP-GiST's unverifiable
  page classes and hash's sparse splitpoint file. The existing consumer page,
  [Detecting Inflated Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in
  PostgreSQL 17
  (unverified)](v17/questions/indexing/non-btree-index-inflation-comment-baseline.md),
  was **re-read and not edited**: it already runs `VACUUM (ANALYZE)` after each churn,
  but it also files a pre-`VACUUM` evaluation, runs no census, takes no measurement
  lock, has no BRIN stand-in and declares no bounds, so it does not conform and needs
  its own task.
  `scripts/wiki_lint` reports 0 errors and 0 warnings; no server was started, so there
  is nothing to tear down; **agent verification is `not yet`**.

- 2026-09-15: Re-ran [A COMMENT-Stored Baseline and Normalized Index Growth for
  Finding GIN Indexes That Need REINDEX CONCURRENTLY in PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-reindex-normalized-growth-comment-baseline.md)
  **end to end under** [Mandatory GIN Bloat Tests
  (unverified)](v17/common-concepts/mandatory-gin-bloat-tests.md), at unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c`, the second consumer page brought onto
  the protocol. Every number now comes from **one published 1,596-line
  `## Measurement Script`** that builds 17.11 out of tree, files the declared kind of
  every published column **three seconds before the first fixture's baseline payload**,
  and runs **24 scored fixtures** plus one refusal fixture through build → baseline →
  churn (writes, settle, maintenance) → a `SHARE ROW EXCLUSIVE` decide pass → a measured
  `REINDEX INDEX` oracle, with a 28-table analyze census in between. `make check`
  **All 225** plus **All 8 / 1 / 1 / 30 / 4** on `pageinspect`, `pgstattuple`,
  `pg_freespacemap`, `btree_gin` and `pg_trgm`. The decision was right **19 of 24**
  (1 false positive, 0 false negatives, 4 refusals, one of them hiding a real 73.95 %
  candidate by design), and **the page's one declared bound failed**: `est_reclaimable`,
  filed as an upper bound, held on 14 of 21 and was violated on 7 by −0.01 to −10.43
  points, so it is **demoted to a level**. Five findings replace the retired programme:
  a rebuild made `p02` **21.01 % larger** than its churned file; the fresh-build curve
  grew **2.67x** across the posting-tree conversion and then **1.38x**, not the
  quadruple-then-flat the page used to claim; the pending-list high-water mark is
  enforced *during* the inserts at **514 pending pages**, where
  `nPendingPages * GIN_PAGE_FREESIZE` passes 4 MB, measured as **515 deleted and 515
  FSM-free pages** on `fastupdate = on` against **0 and 0** on its twin; a 64MB build is
  **20.3 %** larger than a 256MB one with the metapage identity now **exact on 9 probe
  builds and 25 baselines**, settling the old off-by-one open question; and the
  `n_mod_since_analyze` race reproduced on **4 of 4** attempts, with a capture inside the
  loading transaction recording `bti = 0`. New coverage: the maintenance pair (996 → 2,381
  metapage pages with no byte moved), two auto-analyze stand-ins that pin the evaluable
  window to **1,001 rows at any table size**, a held snapshot whose three `VACUUM VERBOSE`
  lines read 0 deleted / 60 deleted and 0 reusable / 60 reusable, a
  `VACUUM (INDEX_CLEANUP OFF)` that printed no index line, six opclass and shape fixtures,
  and a census that declined a table sitting **exactly** on its threshold. **Six fixtures
  and four sections were removed** with the claims they backed, because their recipes
  measured unmaintained churn or could not be re-run, and two ladder rungs are now shown
  unreachable under the protocol. `scripts/wiki_lint` reports 0 errors and 0 warnings; the
  script's `clean` stage stopped the server and deleted the sandbox; **agent verification
  was reset to `not yet`**.

- 2026-09-15: Re-ran [Measuring Wasted and Reclaimable Bytes in a GIN Index With
  Contrib Extensions on PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md) **end to
  end under** [Mandatory GIN Bloat Tests
  (unverified)](v17/common-concepts/mandatory-gin-bloat-tests.md), at unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c`, closing the conformance gap the
  concept-page task had recorded. Every number on the page now comes from **one
  published `## Measurement Script`** that builds 17.11 out of tree, files the
  declared kind of every published column **before the first fixture exists**, runs
  build → baseline → churn (writes, settle, maintenance, census) → a decide pass
  under one `SHARE ROW EXCLUSIVE` transaction → a measured `REINDEX INDEX` oracle,
  and deletes itself. `make check` **All 225** plus **All 8 / 1 / 1 / 30 / 4** on
  `pageinspect`, `pgstattuple`, `pg_freespacemap`, `btree_gin` and `pg_trgm`.
  Result over **19 scored fixtures**: the declared **upper bound** held **19 of
  19**; the declared **lower bound** failed **2 of 19** and is therefore **demoted
  to a level**, the two failures being a flushed pending list (64.64 % dead against
  58.05 % returned) and the new auto-analyze stand-in (52.69 % against 45.16 %),
  both indexes packed denser than their own rebuild by pending-list merges. 19 of
  19 size brackets held, the FSM count stayed within the census on 25 of 25
  indexes, and the metapage identity `n_data_pages = live data + (deleted −
  FSM-free)` was **exact on 25 of 25**. The three coverage fixtures the concept page
  newly requires were built and measured: the **maintenance pair**, where a census
  taken before the settle step reads the as-built 14.08 against the settled 54.55
  and the `ANALYZE` half moves no page; the **auto-analyze stand-in**, which flushes
  49 pending pages into 49 dead ones and keeps stale metapage counts by
  construction; and the **simulated census** over 102 tables, which analyzed 10,
  declined a table sitting exactly on its threshold, and reproduces the publication
  hazard on purpose. **Six fixture families and four sections were removed** because
  nothing on the page could re-run them, and the 12.2 leg is kept only as statement
  portability, outside a v17 protocol. `scripts/wiki_lint` reports 0 errors and 0
  warnings; the script's `clean` stage stopped the server and deleted the sandbox;
  **agent verification stays `not yet`**.

- 2026-09-15: Ported every autovacuum, VACUUM, ANALYZE and auto-analyze rule of
  [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md) into
  [Mandatory GIN Bloat Tests
  (unverified)](v17/common-concepts/mandatory-gin-bloat-tests.md) at unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c`, **as binding protocol** at the
  asker's direction. The GIN page now fixes seven things rather than six: the churn
  phase ends in the order writes, settle step, **maintenance step**, **census**, under
  a three-part maintenance assumption (`VACUUM ANALYZE` on every table the churn
  touched before the decide phase; no exemption from `autovacuum = off` or from a
  per-table `autovacuum_enabled = false`; no fixture may leave churn unmaintained),
  beside the launcher's three verdicts recorded with their five `PGC_SIGHUP` GUCs,
  six `ShareUpdateExclusiveLock` reloptions and `pg_stat_all_tables` counters but
  **deliberately not applied on the vacuum side**, and a simulated auto-analyze
  census that recomputes `relation_needs_vacanalyze`'s strictly-greater test per
  table from the effective reloption-or-GUC values, with the negative-`reltuples`
  clamp, the `autovacuum_enabled` short circuit, two publication points and a
  `stats_fetch_consistency` read rule. **The port is not a copy**, and the reason is
  a v17 finding the B-tree page has no counterpart for: `analyze_rel` enters
  ANALYZE-only index cleanup only when the command is not a `VACUUM ANALYZE`, and
  its comment names GIN as the **only core index AM** that does not no-op in that
  mode, so an autovacuum worker's bare `ANALYZE` flushes the pending list while any
  other backend's returns at once. A fixture modelling the auto-analyze-only state
  therefore runs `ANALYZE` **plus** `gin_clean_pending_list()`, with three
  differences from the worker's path named and cited - `full_clean` true versus
  false, neutralised only by the protocol's own no-concurrency rule; an index
  `RowExclusiveLock` with ownership, recovery and invalid-index refusals versus the
  worker's table lock; and neither path reaching `ginUpdateStats`, so such a fixture
  carries **stale metapage counts by construction**, cannot claim the settle step
  and drops to three cross-checks. Also new on the page: the `ANALYZE` half cannot
  un-settle a settled index but does rewrite the measured index's `relpages` and
  `reltuples`, and no shipped test asserts a launcher verdict, `n_mod_since_analyze`
  or the worker-only flush. **586 citations, 144 distinct ranges**, every one
  resolving and in bounds inside `raw/postgres-17/` and every one listed under
  `## Source References`; open questions went from 6 to 12, the six new ones being
  the unsimulated vacuum side, the two stand-in differences that stand, the
  cross-check an analyze-only fixture loses, the unprovable second publication
  point, the `VACUUM`-written index count the mandatory `ANALYZE` now always
  overwrites, and the fact that no previously filed run was produced under either
  new rule. The consumer question page was **re-read and not edited**: its procedure
  has no maintenance step, it runs no census and it has no auto-analyze-stand-in
  fixture, so it no longer conforms and needs its own task. `scripts/wiki_lint`
  reports 0 errors and 0 warnings; no server was started, so there is nothing to
  tear down; **agent verification stays `not yet`**.

- 2026-09-15: Filed [Mandatory GIN Bloat Tests
  (unverified)](v17/common-concepts/mandatory-gin-bloat-tests.md), the wiki's
  **second** common concept page, at unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c`, and moved the protocol out of
  [Measuring Wasted and Reclaimable Bytes in a GIN Index With Contrib Extensions on
  PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md), which now
  links it from its procedure, its measurement-lock section, its four cross-checks
  and its reading rules. At the asker's direction the page is **protocol-scoped, not
  corpus-scoped**: it fixes the five phases per fixture, the settle step and its
  proof obligations, the `SHARE ROW EXCLUSIVE` measurement lock, the measured
  `REINDEX INDEX` oracle bracketed by `pg_relation_size(index, 'main')`, the rule
  that every published column is declared a lower bound, an upper bound or a level
  before the run, the four mandatory cross-checks, the concurrency rules and the
  reading rules - and defines **no fixture corpus**, which stays page-local, with no
  runnable SQL on the concept page. Seven v17 behaviors are cited as the reason each
  rule exists, among them that the entry tree never deletes a tuple, that
  `GinPageIsRecyclable` needs the horizon to move while `ginvacuumcleanup` re-reads
  rather than truncates the file, that entry-page and data-leaf free space are
  different quantities, that the metapage counts have one writer and an
  `analyze_only` call is a no-op outside an autovacuum worker, and that
  `get_raw_page_internal` releases its `AccessShareLock` per call. **356 citations,
  90 distinct ranges over 45 files**, every range resolving and in bounds inside
  `raw/postgres-17/`. Two defects came out of
  the extraction: the superseded protocol paragraph cited
  `indexcmds.c#L678-L679` - `DefineIndex`'s own `ShareLock`, not the REINDEX table
  lock - which the concept page replaces with `RangeVarCallbackForReindexIndex`, and
  the "free index page reads `MaxFSMRequestSize`" claim is now derived through
  `fsm_space_cat_to_avail`'s category floor rather than asserted beside the
  `BLCKSZ - 1` the FSM is told. The consumer page keeps every number, every fenced
  block and both verification fields untouched, and files a new open question 21
  recording that it has **not** been re-scored under the concept page's phase
  boundaries or its declared-kind columns. `scripts/wiki_lint` reports 0 errors and
  0 warnings; no server was started, so there is nothing to tear down; **agent
  verification stays `not yet`** on both pages.

- 2026-09-15: Reviewed and **re-measured on the current pin** [Checking Whether
  an Index Needs a Rebuild to Enable Deduplication After pg_upgrade From
  PostgreSQL 12 to 17
  (unverified)](v17/questions/indexing/btree-deduplication-after-pg-upgrade.md),
  whose numbers were 17.10 measurements taken against the superseded pin
  `54eeefaedbee0385529f3edf321bb99e49232aaa`. All ~50 source citations were
  re-read in `raw/postgres-17/` at `786db8dcf168bd9df8f55047337525ac19118b1c`,
  and the whole measurement is now **one published `## Measurement Script`**
  that builds 12.2 and 17.11 out of tree from their pins, runs one
  `pg_upgrade --copy`, measures 14 stages and deletes itself: `make check`
  **All 225** plus `pageinspect` **All 8** on 17.11 and **All 192** on 12.2,
  `Linux x86_64`, `max_data_alignment` 8, `block_size` 8192. Results:
  **26 carried-over index files, 26 of 26 digests identical** with OID and
  relfilenode preserved, **all 26 reading the flag false**, the 22 in `public`
  at `pd_lower = 64` and version 4 where a fresh index reads 72/true; the
  filed check printed **189 rows**, flagging **20 of the 26** and refusing 6;
  the probe agreed with `bt_metap()` on version, flag and delpages in
  **189 of 189** rows and **23 of 23** after the rebuilds; the gate matched the
  metapage on **17 of 17** shapes, including nondeterministic and deterministic
  ICU collations, and the engine's `DEBUG1` verdict on the 16 that produce one;
  **17 concurrent rebuilds** reclaimed **67.4 % to 69.1 %** on eight
  duplicate-heavy indexes and exactly **0.00 %** on the six refused plus the
  unique, the `uuid` and the empty one; the carried-over index equalled a fresh
  `deduplicate_items = off` twin **to the byte** (22,519,808), the split on an
  updated table read **48.5 % bloat over 69.1 % deduplication**, the churn
  comparison **3.1x**, and the curve **0.0 / 9.8 / 48.1 / 65.4 / 69.5 / 67.4 %**
  at 1 / 2 / 5 / 20 / 100 / 1000 rows per key. **Five corrections**: the
  `btm_oldest_btpo_xact` repurposing is `e5d8a999030`, not `9f3665fbfc3`, which
  deprecated the neighbouring tuple count instead; the relfilenode-snapshot
  fallback must join on schema and name, because `REINDEX ... CONCURRENTLY`
  moves the name to a new `pg_class` OID and the OID join **silently dropped 17
  of the 20 rebuilds**; the statistics claim is now `index_update_stats`'s
  `!IsBinaryUpgrade` skip, with 26 of 26 at `relpages = 0` but the carried-over
  `pg_largeobject` index at `reltuples = -1`; the "relfilenodes continued from
  the old cluster's NextOID" claim is **withdrawn**, since `NextOID` read 16449
  against the old cluster's 24576 and a post-upgrade object got 16503; and one
  mislabeled citation, two narrow `pg_amproc` ranges and a docs-versus-source
  discrepancy in `pgupgrade.sgml` were fixed or filed. The page now links the
  [Mandatory B-Tree Bloat Tests](v17/common-concepts/mandatory-btree-bloat-tests.md)
  concept page and states that it was **not** scored against that suite; the
  concept page was read and not edited. `scripts/wiki_lint` reports 0 errors and
  0 warnings, the script's `clean` stage stopped both servers and deleted the
  sandbox, and **agent verification stays `not yet`**.

- 2026-09-14: Re-ported [A COMMENT-Stored Baseline B-Tree Index-Maintenance
  Heuristic for PostgreSQL 12 Through 17
  (unverified)](v17/questions/indexing/btree-comment-baseline-maintenance-heuristic.md#what-the-2026-09-14-re-port-changed-and-why)
  to [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md) as that page
  stands after the 2026-09-12 retirements, at unchanged pins
  `786db8dcf168bd9df8f55047337525ac19118b1c` and
  `45b88269a353ad93744772791feb6d01bc7e1e42`, and **re-ran both legs end to end
  on Linux x86_64**, `make check` included: 17.11 passed 225 of 225 plus 8, 1
  and 3 for `pageinspect`, `pgstattuple` and `amcheck`, and 12.2 passed 192 of
  192 plus 5, 1 and 2. **Fourteen numbered fixtures left the 17 leg and ten the
  12 leg** - tests 11, 38, 65, 67, 69, 106, 117 and 121 and legs 113a and 113c,
  each deleted with its recipe - so the scored population is **126 fixtures on
  17.11 and 112 on 12.2**, reading **`PASS` on every one**, with 0 false
  positives of either severity, 0 gate disagreements, 95 and 81 rebuilds at a
  mean 86.2 % and 87.1 % reclaim, and stored index counts equal to the
  catalog's on all of them. **Neither filed text changed**: both SQL blocks hash
  to their 2026-09-11 values, so **the clean sheet is the suite narrowing, not
  the heuristic improving** - the four false negatives of the previous run,
  `p113a`, `p113c`, `p65` and `p67`, are precisely the retired
  dead-but-unvacuumed fixtures, and the page files that as its first open
  question instead of claiming credit. At the asker's direction the pass also
  **removed every page-local acceptance fixture** - the whole `edge` stage, its
  four SQL files and its database - and **deleted the claims they backed**: the
  fifteen comment shapes, the candidate-filter refusals, the ten gate
  boundaries, the two forged `reltuples = -1` states, the nine-point threshold
  curve, comment survival across both `REINDEX` forms, the privilege matrix, the
  `COMMENT` lock probe, `dry_run`, idempotence and `pg_dump`; each loss is named
  under Open Questions. Also at the asker's direction the concept page's
  **maintenance assumption was not applied**, so ten recipes still reach the
  decide phase unvacuumed and that departure is stated on the page. Two findings
  came out of the run itself: **fixture 120's precondition was unmet on both
  legs**, because rule 3's census re-analyzes its table at the default
  statistics target and repairs the sampling miss the fixture is built on, and
  the harness's `check_server_errors` was **repaired** after being found unable
  to match the default `%m [%p] ` log prefix at all - its earlier "0 unexpected
  errors" was vacuous, and it now reports 4 logged and 4 deliberate on 17.11 and
  8 and 8 on 12.2. `scripts/wiki_lint` reports 0 errors and 0 warnings, both
  servers were stopped by the scripts' own `clean` stages with teardown
  confirmed and the sandbox deleted, and **agent verification stays `not yet`**.
  The concept page was read and **not edited**.

- 2026-09-14: Removed **both report-side cutoffs** from the statement on
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#what-the-filter-removal-measured) -
  the `actual_bytes > 1024 * 1024` predicate and the `LIMIT 20` - at unchanged
  pins `786db8dcf168bd9df8f55047337525ac19118b1c` and
  `45b88269a353ad93744772791feb6d01bc7e1e42`, and **re-ran both legs end to end
  from their pins on Linux x86_64**, `make check` included: 17.11 passed 225 of
  225 plus 8, 1 and 3 for `pageinspect`, `pgstattuple` and `amcheck`, and 12.2
  passed 192 of 192 plus 5, 1 and 2. `NOT suppress_row` is now the statement's
  only report filter, so on the settled fixture database it prints **68 rows
  where the superseded text prints 20**, 45 of them 1 MB or smaller, and **19
  rows on 12.2** with 6 that small. The score improves by five fixtures:
  **96 `PASS`, 4 `CRITICAL FALSE POSITIVE`, 0 `FALSE POSITIVE` and 26
  `FALSE NEGATIVE`** over 126 fixtures on 17.11 against 91/4/0/31 before, and an
  unchanged **11 `PASS` with 2 `FALSE NEGATIVE`** on 12.2, where **no fixture is
  under 1 MB**. Only **10 of the 31 under-1 MB fixtures became visible** - the
  other 21 were already withheld by an exclusion term - five of them now rebuild
  and repay 83.3 % to 87.9 %, and **two are the page's first threshold losses**:
  `p31` and `f91` read about `-237 %` where a rebuild gave back 79.2 % and
  89.2 %, so the earlier "not one false negative is a threshold loss" headline
  was an artefact of the filter that hid them, and both are filed as the
  clearest candidate for the next revision. The four critical false positives
  are unchanged and all over 1 MB, `expected_stage` still agrees on all 101
  numbered rows, cost did not move (64.5 to 75.2 ms), and family 1 still passes
  25 of 25. Both scripts were edited in place - new `BASE1`/`BASEPRE`
  baselines, a `harness_view` that handles both statement tails, `over_1mb`
  demoted to an observation, and six read-only summaries added - and the probe
  generator kept its own 1 MB filter at the asker's direction, which is filed as
  an open question. `scripts/wiki_lint` reports 0 errors and 0 warnings, both
  servers were stopped by their own `stop` stages with teardown confirmed and
  the sandbox deleted, and **agent verification stays `not yet`**. The concept
  page was read and **not edited**.

- 2026-09-14: Re-ported [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method
  on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#what-the-2026-09-14-re-port-measured)
  to [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md) as that page
  stands after the 2026-09-12 retirements and the 2026-09-13 maintenance
  assumption, at unchanged pins `786db8dcf168bd9df8f55047337525ac19118b1c` and
  `45b88269a353ad93744772791feb6d01bc7e1e42`, and **re-ran both legs end to end
  on Linux x86_64**, `make check` included: 17.11 passed 225 of 225 plus 8, 1
  and 3 for `pageinspect`, `pgstattuple` and `amcheck`, and 12.2 passed 192 of
  192 plus 5, 1 and 2. **Eleven numbered fixtures left the 17 leg** - test 11's
  three `deduplicate_items = off` gate legs, 38, 65, 67, 69, 106, 117, 121's
  three recipes and legs 113a and 113c - **and three left the 12 leg**, and ten
  recipes that keep churn of their own now end on `VACUUM` then `ANALYZE`: 64,
  66, 92, 93, 94, 95, 98, 115, 118 and 119. The scored population is **126
  fixtures on 17.11 and 13 on 12.2**, reading **91 `PASS`, 4 `CRITICAL FALSE
  POSITIVE`, 0 `FALSE POSITIVE`, 31 `FALSE NEGATIVE`** and **11 `PASS` with 2
  `FALSE NEGATIVE`**, with `expected_stage` agreeing on all 101 numbered rows,
  no threshold loss among the misses, 0 build-contract failures and 0 unexpected
  server errors on either leg. Rule 3's census shows the assumption working:
  **2 of 86 tables analyzed and 84 at zero modified rows**. At the asker's
  direction the pass also **removed every page-local fixture** - the geometry
  cells, the insertion-pattern calibration and the whole acceptance stage, with
  the `geo`, `cal` and `acc` databases, `sql` blocks 3 and 4 and two hash
  baselines - and **deleted the claims they backed** rather than keeping them as
  history, which cost the page its measured fresh-build, geometry, calibration,
  compression, posting-tail, publication-barrier and non-owner role coverage;
  each loss is filed under Open Questions. `scripts/wiki_lint` reports 0 errors
  and 0 warnings, both servers were stopped by the scripts' own `clean` stages
  with teardown confirmed and the sandbox deleted, and **agent verification
  stays `not yet`**. The concept page was read and **not edited**.

- 2026-09-13: Re-ported [B-Tree Bloat and Wasted Space From pgstatindex Alone,
  on PostgreSQL 12 and 17
  (unverified)](v17/questions/indexing/btree-bloat-with-pgstatindex.md#what-the-maintenance-assumption-changed)
  to [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md) as it
  stands after the retirement of tests 11, 11b and 38 and the addition of the
  maintenance assumption, at unchanged pins
  `786db8dcf168bd9df8f55047337525ac19118b1c` and
  `45b88269a353ad93744772791feb6d01bc7e1e42`, and **re-ran both legs end to end
  on Darwin arm64**, `make check` included: 17.11 passed 225 of 225 plus
  `pgstattuple` 1 of 1, 12.2 passed 192 of 192 plus 1 of 1. Nine churned
  recipes now end on `VACUUM` then `ANALYZE`, and five retired indexes left the
  port. **`PASS` on 125 of 125 and 117 of 117**, with no false positive or false
  negative of either severity; worst under-estimate `-4.1` where it was `-9.8`,
  because the maintenance step removed the dead index entries behind the old
  `b93`/`b95` under-read; rule 3's census analyzed 2 of 88 tables on both legs.
  The same pass fixed source-only defects a review listed the same day: a
  release-tag claim the tagless checkout cannot support, three PostgreSQL 12
  claims stated from v17 evidence, uncited `NaN`, `USAGE`, `relation_open`,
  `written=` and `MATERIALIZED` claims, a Contents block that listed
  fourth-level headings, and a Source References list out of step with the
  body. The scripts gained per-call session timeouts, more statement tags,
  failure marking in the timing loop, and prerequisites for a host without
  `pkg-config`. Both servers were stopped by the scripts' own `clean` stages
  with teardown confirmed and the sandbox deleted. **Agent verification stays
  `not yet`**. The concept page was read and **not edited**.

- 2026-09-12: Retired tests 11, 11b and 38 from [Mandatory B-Tree Bloat Tests (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md). Explicitly enabling or disabling deduplication is outside the mandatory suite. The remaining 113 numbered tests keep their numbers; consumer scripts and historical measurements are unchanged.

- 2026-09-12: Removed the **"skip anything smaller" size prefilter** from the
  statement on [B-Tree Bloat and Wasted Space From pgstatindex Alone, on
  PostgreSQL 12 and 17
  (unverified)](v17/questions/indexing/btree-bloat-with-pgstatindex.md), at
  unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, and **re-ran both
  legs end to end from their pins**, `make check` included: 17.11 passed 225 of
  225 plus `pgstattuple` 1 of 1, 12.2 passed 192 of 192 plus 1 of 1. The
  `min_index_bytes` parameter and the `pg_relation_size` predicate went
  together, so **`pgstatindex` is now the only function the statement measures
  with**, and it prints every candidate: **367 rows on 17.11 and 347 on 12.2**
  against 115 and 123 before, the catalog's and TOAST's own indexes included.
  The suite is now passed outright — **`PASS` on 131 of 131 and 116 of 116,
  with 0 `CRITICAL FALSE POSITIVE`, 0 `FALSE POSITIVE` and 0 `FALSE
  NEGATIVE`** — because the 25 and 5 false negatives were rows the prefilter
  withheld (31 and 7 fixtures sit under 1 MB); `taken_stage` equals
  `taken_nofilter` on every fixture and `lost_by` is empty on both legs. The
  clean sheet is **not** the reading improving, and the page still files the
  retired unvacuumed fixtures as an open question. What the removal cost is
  measured too: **2 to 8 % of wall time** for 256 and 228 more indexes, the
  same `read` counts with about 3,000 and 1,000 more buffer hits, a plan two
  `CTE Scan` nodes shorter because `params` is now singly referenced and
  inlined, small-index artefacts that now reach the reader unmarked
  (`c_one_idx` at 44.6 % wasted, `c_zero_idx` at 0.0 % against a measured
  50.0 %), and **the loss of the concurrent-drop shield**: a `DROP INDEX` that
  commits during the report now aborts it, reproduced in both windows on both
  legs where three earlier sweeps had never landed in the second one. A new
  `crossleg` stage puts the cross-major comparison in the script — 290 keys
  printed by both legs, 191 rows identical field for field, and of the 42
  differing fixture keys, three are the harness's own tables and **all 39
  others have fewer leaf pages on 17.11**. `sql` blocks 1, 2 and 4 changed and
  both scripts' hash constants moved with them; accuracy against the oracle is
  unchanged (95 and 97 within one point, worst over-estimate `+10.0`, worst
  under-estimate `−9.8`). Both servers were stopped by the scripts' own stages
  with teardown confirmed and the sandbox deleted, `scripts/wiki_lint` reports
  0 errors and 0 warnings, and **agent verification stays `not yet`**: three
  claims on the page remain source readings the current fixtures do not
  exercise, and one is a cross-version attribution this evidence base cannot
  settle. The concept page was read and **not edited**.

- 2026-09-12: Re-synced [B-Tree Bloat and Wasted Space From pgstatindex Alone,
  on PostgreSQL 12 and 17
  (unverified)](v17/questions/indexing/btree-bloat-with-pgstatindex.md#what-the-re-sync-to-the-narrowed-suite-changed)
  to [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md) as that page
  stands after its narrowing to **115 numbered tests**, at unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c`, and **re-ran both legs end to end
  from their pins**, `make check` included: 17.11 passed 225 of 225 plus
  `pgstattuple` 1 of 1, 12.2 passed 192 of 192 plus 1 of 1. **The eight retired
  fixtures left the port** - numbers 65, 67, 69, 106, 117 and 121 and legs 113a
  and 113c, ten indexes in all - so the scored population is **131 fixtures on
  17.11 and 116 on 12.2**, with 0 and 15 skips: 14 feature gates, plus **test
  120's precondition, met on 17.11 and unmet on 12.2** where `p120` read
  `reltuples = 10002` and the fixture was recorded and scored from nothing. The
  scoring is **0 `CRITICAL FALSE POSITIVE` and 0 `FALSE POSITIVE`** again, 106
  and 111 `PASS`, and **every one of the 25 and 5 false negatives is the
  statement's own 1 MB report filter**, so the filter-free score is `PASS` on
  131 of 131 and 116 of 116. **That headline is the narrowing, not the
  reading**, and it is filed as an open question rather than a result: the four
  fixtures that used to defeat the method with the filter off were the retired
  `p65`, `p67`, `p113a` and `p113c`, so a method that misreads a not-yet-
  vacuumed index now passes, and the `VACUUM`-written row count has no fixture
  either. Also measured: the worst under-estimate improves from `−100.1` to
  `−9.8` on `b93`/`b95` on both legs, rule 3's census falls from 17 of 99 tables
  to **8 of 89** because nine of the ten retired tables were tables it had been
  analyzing, `expected_stage` agrees on 131 of 131 and 116 of 116, 0
  build-contract failures, 0 failed post-churn shape assertions, and the
  `compare` stage re-derives both `Follow-up` equivalence tables with **0
  differing rows in both directions** on 371 and 351 indexes. **The re-sync also
  found one drift beyond the retired fixtures**: `sql` block 5's comment still
  claimed rule 2's drain costs every leaf an entry, corrected to volume against
  distribution, and block 6 gained a family 6 check that prints each fixture's
  counted population beside its `pg_class.reltuples`, so an unknown `-1` cannot
  be read as a measured zero - no fixture reached `-1` in this run. Blocks 4, 5
  and 6 changed and both scripts' hash constants moved with them; the filed
  statement, the harness and family 1 are unchanged. Both servers were stopped
  by the scripts' own stages with teardown confirmed and the sandbox deleted,
  `scripts/wiki_lint` reports 0 errors and 0 warnings, and **agent verification
  stays `not yet`**: three claims on the page are now source readings the
  current fixtures do not exercise and one is a cross-version attribution this
  evidence base cannot settle. The concept page was read and **not edited**.
  Note on dates: this run is the later of the two most recent, even though the
  review below is filed under 2026-09-13 - that label is a day ahead of the
  repository's clock, and its commit is dated 2026-09-12.

- 2026-09-12: Narrowed [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md) at unchanged
  pin `786db8dcf168bd9df8f55047337525ac19118b1c`, source-only and with no server
  started: **the eight fixtures that deliberately withheld maintenance are
  removed**, at the asker's direction and after the scope was confirmed against
  two wider readings. Four of them skipped the `VACUUM` after entries left the
  index (65, 67, 113a, 113c); four ran the `VACUUM` and skipped the following
  `ANALYZE` (69, 106, 117, 121). The numbers are **retired, not reused**, so the
  suite is **115 numbered tests** where it was 121: family 2 now reads 18 to 77
  less 65, 67 and 69, family 5 reads 92 to 112 less 106, and family 6 reads 113
  to 120 less 117, keeping only `p113b` of test 113. **Two claims flipped from
  covered to absent, and both are filed as Open Questions**: no fixture builds a
  dead-but-not-vacuumed index any more, so a method that misreads one now passes
  the suite; and with the `VACUUM`-then-stop recipes gone, nothing pins the count
  `update_relstats_all_indexes` writes, which corrects the `Why It Exists` claim
  that all four `reltuples` writers had a family 6 fixture - three do. A new
  named limit records the retired numbers and the boundary the removal drew: the
  **skipped maintenance command**, not the misleading statistic, so fixtures
  whose point is a missing or stale statistics row (64, 83, 85, 97, 98, 108, 110
  to 112, 118) stay. The `TRUNCATE`-then-reload citation left with fixture 121's
  `i_trunc` leg and was dropped from `## Source References`.
  `scripts/wiki_lint` reports 0 errors and 0 warnings, nothing was started so
  nothing needed stopping, and **agent verification stays `not yet`**. The three
  consumer question pages were re-read and **not edited**, per the concept-page
  read-only rule: all three port and score the removed fixtures, and
  [btree-comment-baseline-maintenance-heuristic](v17/questions/indexing/btree-comment-baseline-maintenance-heuristic.md)
  also states that all 121 numbered tests are ported, so each needs its own task.

- 2026-09-13: Reviewed [B-Tree Bloat and Wasted Space From pgstatindex Alone,
  on PostgreSQL 12 and 17
  (unverified)](v17/questions/indexing/btree-bloat-with-pgstatindex.md#what-the-2026-09-13-review-repaired)
  claim by claim against the pin `786db8dcf168bd9df8f55047337525ac19118b1c` and
  against [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md) as that page
  stood after its 2026-09-12 revision, then **rebuilt both servers and re-ran
  both legs end to end**, four times in all while the repairs landed. 17.11
  passed `make check` 225 of 225 plus `pgstattuple` 1 of 1; 12.2 passed 192 of
  192 plus 1 of 1. **Every filed source citation resolves and supports its
  label**, and every measured claim reproduced except the ones listed below.
  **Six defects in the suite port, all confirmed and fixed in the page's own
  `sql` blocks**: rule 3's census read `current_setting('autovacuum_analyze_
  threshold')` for every table where `relation_needs_vacanalyze` reads the
  table's own reloption whenever it is non-negative, so fixtures **94 and 95
  both decided the wrong way** - corrected, `b94t` is analyzed at a threshold of
  100 and `b95t` left alone at 610,000 against the cluster's 41,050; the churn
  had **one publication point where rule 3 needs two**, so on 12.2 the drain's
  deletes reached `mod_since_analyze` after its own `ANALYZE` had zeroed it and
  the census analyzed 31 tables in one run and 51 in the 2026-09-11 run against
  17.11's 17 - `wiki_flush()` now forces the flush where SQL can and waits out
  the publish interval where it cannot, and **both legs censused 17 of 99**;
  family 1 lacked the **11b off-to-on `deduplicate_items` control** the concept
  page added on 2026-09-12, now built and scored (**141 fixtures on 17.11**,
  127 on 12.2 with 14 skips) and passing at a `−6.3`-point under-estimate
  because rule 2's drain loosens it first; **test 120's probabilistic
  precondition was assumed**, and is now asserted after the census - met on
  both legs in the filed run and **unmet on 17.11 an hour earlier**, where
  `p120` read `reltuples = 10031` and the fixture was recorded as an unmet
  precondition and scored from nothing; rule 2's drain was described as losing
  entries from every leaf when **its guarantee is volume, not distribution**,
  now asserted per fixture as one of six post-churn shapes with **0 assertions
  failed**; and the **2 % index-vacuum bypass was named as the condition when it
  is one of four**. **Three claims were narrowed under measurement**: the 14
  cross-major differences are not all deduplication, because `p68` carries a
  counted 50,000 distinct keys over 50,000 predicate rows and still differs
  (the hinted bottom-up deletion pass is the v17 mechanism, and the release that
  introduced it is not citable here); the `i_ff10` sample row under `How to read
  the output` came from the retired 1,000,000-row population (41 MB and 5,264
  leaves, not 206 MB and 26,316); and the `written=832`/`written=874` ring
  counters do not appear in these plans at all. **The page's largest standing
  gap is closed**: a new `compare` stage recovers both superseded statement
  texts from their own commits, hash-checks them, and re-derives the two
  `Follow-up` output-equivalence tables on the current population - **0
  differing rows in both directions on both legs**, 385 and 365 indexes, with
  the alert-era output equal to its successor byte for byte once field 14 is
  cut. Scoring after the repairs: **0 `CRITICAL FALSE POSITIVE` and 0 `FALSE
  POSITIVE`**, 112 and 118 `PASS`, 29 and 9 `FALSE NEGATIVE` of which only four
  are the reading's, `expected_stage` agreeing on 141 of 141 and 127 of 127, and
  0 build-contract failures. Both servers were stopped by the scripts' own
  stages with no `postmaster.pid`, no matching process and an empty socket
  directory confirmed, and the sandbox deleted. `scripts/wiki_lint` reports 0
  errors and 0 warnings. **Agent verification stays `not yet`**: two claims on
  the page are source readings no fixture exercises (the bypass conditions and
  the unlogged-on-a-standby filter) and one is a cross-version attribution this
  page's evidence base cannot settle. The concept page was **read and not
  edited**, per the read-only rule; the one change it needs - exempting test 11b
  from the drain, or giving it an undrained twin - is filed as an open question
  on the question page.

- 2026-09-12: Revised [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md) against
  **eight reported defects, every one confirmed in the pin**
  `786db8dcf168bd9df8f55047337525ac19118b1c`, source-only and with no server
  started. **Rule 3 stopped equating the auto-analyze threshold with the cluster
  GUCs**: it now defines the effective per-table values -
  `relopts->analyze_threshold` and `relopts->analyze_scale_factor` whenever they
  are `>= 0`, the GUC only otherwise, read out of the `AutoVacOpts` member of
  `StdRdOptions` by `extract_autovac_opts` - plus the negative-`reltuples`
  clamp, the strictly-greater comparison and the `autovacuum_enabled` short
  circuit, in a six-row table. That is exactly what **fixtures 94 and 95
  override** at 100/0 and 200000/1. Rule 3 also gained a **two-point
  statistics-publication requirement**, because sequential phases do not put
  churn into `n_mod_since_analyze`: pending counts reach the shared entry only
  through a `pgstat_report_stat` flush, unforced at most once per 1000 ms
  `PGSTAT_MIN_INTERVAL`, while `pgstat_report_analyze` zeroes the counter and
  says in its own comment that it forgets changes committed during the
  `ANALYZE`; `pg_stat_force_next_flush()`, `stats_fetch_consistency` (default
  `cache`, `PGC_USERSET`) and `pg_stat_clear_snapshot()` are named as the
  mechanisms, with `stats.sql` cited as the engine's own use of the sequence.
  **The oracle section now records that a rebuilt or freshly built empty index
  keeps `reltuples = -1`, not `0`** - `RelationSetNewRelfilenumber` writes the
  sentinel and `index_update_stats` preserves it when the build count is zero,
  which also suppresses the `relpages` update - so family 6 must distinguish an
  empty population from an unknown count on 113a-c, 115, 116, 118 and 121's
  `nzb_k`. **Rule 2's drain lost its every-leaf guarantee**: a sorted build makes
  leaf order key order, so the spread follows each fixture's key-to-heap
  correlation, and the rule now states volume against distribution in a table
  and requires a per-fixture assertion where the distribution is the point.
  **Test 120 must assert its intended zero estimate after the census**, since
  `acquire_sample_rows` seeds its block sampler from the global PRNG; an
  unmet precondition is recorded instead of credited coverage. **Family 1 gained
  test 11b**, the off-to-on `deduplicate_items` transition control the suite
  never had - built off, switched on with `ALTER INDEX`, no further inserts -
  which is a different condition from test 11 because the insert gate and the
  build gate read the option at different times; this is the `i_dedup_off` gap
  the 2026-09-11 `pgstatindex` run measured at **69.1 % reclaimable against a
  reported −0.3 %**. Two engine claims were narrowed: the `DEBUG1` deduplication
  verdict is **not** a complete oracle (the `INCLUDE` refusal returns before the
  log line, and only `_bt_leafbuild` passes `debugmessage = true` while
  `btbuildempty` passes false - the only two callers in the tree), and the 2 %
  index-vacuum bypass is **one of four conditions**, beside
  `consider_bypass_optimization`, `rel_pages > 0` and a 32 MB dead-item cap,
  with index cleanup still running when it applies. Finally, the
  **resolving-only citations were re-anchored**: the REINDEX range moved from
  `index.c#L3583-L3600`, which is signature and locals, to `#L3781-L3789`, the
  actual suppress / new-relfilenode / `index_build` calls, joined by
  `index_build`'s two `index_update_stats` calls and `ReindexIndex`'s dispatch;
  `btbulkdelete` and `btvacuumscan` likewise moved to bodies that contain the
  work. Three new `###` subsections supply the context AGENTS.md requires:
  eight caller-to-callee boundaries, the generated files fixtures depend on
  (`Gen_fmgrtab.pl`'s `fmgr_builtins` table behind tests 14 and 16,
  `genbki.pl`'s catalog headers), and a nine-row shipped-test table whose last
  row is an **explicit absence** - `pg_regress` adds only
  `log_autovacuum_min_duration = 0`, and no shipped test asserts a launcher
  analyze decision, a bypass decision, or the value of `n_mod_since_analyze`.
  The page is source-only, so no measurement was run and none was added; five
  new Open Questions name what the fixes could not close. `scripts/wiki_lint`
  reports 0 errors and 0 warnings. **Agent verification stays `not yet`**, and
  the three consumer pages were re-read but **not edited**, per the concept-page
  read-only rule: all three censuses on
  [btree-bloat-with-pgstatindex](v17/questions/indexing/btree-bloat-with-pgstatindex.md),
  [btree-index-bloat-core-sql-only](v17/questions/indexing/btree-index-bloat-core-sql-only.md)
  and
  [btree-comment-baseline-maintenance-heuristic](v17/questions/indexing/btree-comment-baseline-maintenance-heuristic.md)
  read `current_setting('autovacuum_analyze_threshold')` for every table and so
  now contradict the corrected rule 3 on fixtures 94 and 95; each needs its own
  task.

- 2026-09-11: Replaced the fixture suite of [B-Tree Bloat and Wasted Space From
  pgstatindex Alone, on PostgreSQL 12 and 17
  (unverified)](v17/questions/indexing/btree-bloat-with-pgstatindex.md#the-mandatory-suite-scored-on-both-majors)
  with the shared [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md) and **ran
  both legs end to end** at unchanged pins
  `786db8dcf168bd9df8f55047337525ac19118b1c` and
  `45b88269a353ad93744772791feb6d01bc7e1e42`. The 32 fixtures the page used to
  build are retired as the scored population and their accuracy tables are
  gone; the suite's harness, fixture text and churn phase are filed as `sql`
  blocks 2 to 6 so **both legs read the same suite out of the page**, and schema
  `bl` keeps only the guard and model shapes the suite does not cover. 17.11
  built out of tree passed `make check` **225 of 225** plus `pgstattuple` 1 of 1;
  12.2, now built `--with-icu` because five fixtures need ICU collations, passed
  **192 of 192** plus 1 of 1. **140 fixtures scored on 17.11 and 127 on 12.2**,
  with 13 skips recorded from the server's own messages (four need the
  `deduplicate_items` reloption, nine need B-tree support function 4), 0
  build-contract failures, and 0 unexpected server errors on either leg.
  **The finding is that a physical reading makes no false positive at all**: 0
  `CRITICAL FALSE POSITIVE` and 0 `FALSE POSITIVE` on both legs, family 3's
  eight constructions included — `f84`'s forged index count and `f85`'s stale
  table statistics cost a catalog-only estimator two critical false positives on
  the same fixtures, and this statement reads neither column. 111 and 118 `PASS`;
  of the 29 and 9 false negatives **only four are the reading's**, the same four
  on both majors (`p65`, `p67`, `p113a`, `p113c`: entries that left the index
  with no `VACUUM`, reported at `0.0` and `−0.1` against a measured 89.1 % and
  100.0 %), and the other 25 and 5 are rows the statement's own 1 MB filter never
  prints, 23 of the 25 within 3.4 points of the truth. Newly measured: 100 of 140
  and 103 of 127 estimates within 1.0 point of the oracle and 133 and 120 within
  5.0, worst over-estimate `+10.0` and `+6.3`; `expected_stage`, recomputed in
  the harness from its own `pgstatindex` call, agreeing with the statement on
  **140 of 140 and 127 of 127**; the filed text agreeing with the harness view on
  every row both print; rule 3's census analyzing 17 of 99 tables on 17.11 and 51
  of 99 on 12.2, a publication-timing difference that moves nothing because this
  method reads no row count; 96 of the 110 report rows identical across the two
  majors with all 14 differences carrying duplicate keys; `index_size` equal to
  `pg_relation_size` for 382 of 382 and 363 of 363 candidates; and a cost of
  ~1.4 GB read at 227 ms and 242 ms over 385 and 366 B-tree indexes. A new
  `guard` stage gives the 18 and 17 `bl` fixtures their own oracle, which is how
  `i_dedup_off` is now measured at **69.1 % reclaimable against a reported
  `−0.3 %`** — the page's largest miss, and **a gap in the concept page's family
  1**, which builds `deduplicate_items = off` indexes but never switches the
  option back on; that is reported rather than fixed, because a concept page
  changes only on its own task. Both servers were stopped by the scripts' own
  `stop` stages with no `postmaster.pid`, no matching process and an empty socket
  directory confirmed, and the sandbox was deleted. Agent verification stays
  `not yet`: the two `Follow-up` sections' output-equivalence tables were
  measured on the retired population and are not reproduced by the filed
  scripts.

- 2026-09-11: Re-scored [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method
  on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#the-mandatory-suite-re-scored-under-the-shared-protocol)
  against the shared [Mandatory B-Tree Bloat Tests
  (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md) at unchanged
  pins `786db8dcf168bd9df8f55047337525ac19118b1c` and
  `45b88269a353ad93744772791feb6d01bc7e1e42`, and **stopped defining the suite on
  the question page**: `Mandatory test review` now leads with the concept-page
  link, drops the group inventory it used to carry, restates the page's
  obligations as the concept page's six families, and names the three deviations
  that remain this page's own. Both legs were built out of tree and run end to
  end under the edited script text: 17.11 `make check` 225 of 225 plus 8, 1 and 3;
  12.2 192 of 192 plus 5, 1 and 2; **0 unexpected server errors on either leg**.
  **140 fixtures scored on 17.11** - the 112 numbered ones plus the 28
  deduplication-gate ones, which now run the same five phases - giving 101 `PASS`,
  4 `CRITICAL FALSE POSITIVE`, 0 `FALSE POSITIVE` and 35 `FALSE NEGATIVE`, and
  **19 on 12.2**, where the exact filed text still executes unmodified, giving 17
  `PASS` and 2 `FALSE NEGATIVE`. The finding is that **not one false negative is a
  threshold loss**: 23 were withheld by an exclusion term, 8 fell under the 1 MB
  report filter and 4 carried a caveat the reading rule refuses to promote, on
  files a rebuild emptied by a mean 83.5 %, 86.3 % and 100.0 %, while
  `expected_stage` - the decision recomputed from the harness's own internals -
  agreed with the statement on all 140. The four critical false positives are the
  four rows a reader would have acted on: `f84` at 94.2 %, `f85` at 70.9 %,
  `i103` at 84.1 % and `x109` at 62.5 %, each against a measured 0.0 %. Scoring
  the decision instead of the number is what exposes them, and the page's older
  bands are printed beside the shared ones to show it: 91 `PASS`, 12 critical
  false positives and 6 false negatives on the same rows, 8 of the 12 on rows the
  report never shows, so the page's earlier "eight false negatives" was a scoring
  artifact rather than a property of the method. Newly measured: a baseline phase
  for every fixture, taken by a `ddl_command_end` event trigger at each index
  build, with **0 build-contract failures on either leg**; rule 2's uniform drain
  over 37 `suite` tables and both `gate` tables; rule 3's census, which censused
  97 tables and analyzed 17 with its own boundary visible at 5.0 % left alone
  against 18.0 % analyzed (22 and 8 on 12.2); the forged count of fixture 84
  surviving that census at 5,000 against a real 100,000; 45 of 112 and 28 of 28
  rebuild decisions returning a mean 81.0 % and 88.4 %; and a cost of 66.5 to
  74.1 ms against the superseded text's 50.6 to 55.0 ms on 329 indexes over
  68,614 blocks. **Four script defects the run found were repaired in the filed
  text before the numbers were taken**: a gate stage that could not run twice
  because `DROP OPERATOR CLASS` leaves the implicit operator family behind,
  a `gate_res` query that read the harness's own primary keys and hit
  `bt_page_items` on an empty index, a drain whose `ANALYZE` reset
  `mod_since_analyze` before its own `DELETE` counts published (46 tables
  analyzed instead of 17), and a 12.2 drain that left `n_live_tup` at 0 beside a
  catalog count of 50,172, which only the census's `ANALYZE` repairs and which
  had cost three false negatives. 39 failures remain open and unfixed, agent
  verification stays `not yet`. Both servers were stopped by their own `stop`
  stages with no `postmaster.pid`, no matching process and an empty socket
  directory confirmed, and the sandbox was deleted.

- 2026-09-11: Filed the wiki's **first common concept page**, [Mandatory B-Tree
  Bloat Tests (unverified)](v17/common-concepts/mandatory-btree-bloat-tests.md),
  at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, and moved the
  shared suite definition out of [A COMMENT-Stored Baseline B-Tree
  Index-Maintenance Heuristic for PostgreSQL 12 Through 17
  (unverified)](v17/questions/indexing/btree-comment-baseline-maintenance-heuristic.md#the-ported-mandatory-suite)
  into it. The concept page defines the suite once: 121 numbered tests in six
  families, the five phases every fixture runs (build, baseline, churn, decide,
  and a measured `REINDEX INDEX` as the only oracle), the three porting rules -
  split each recipe at the index build, drain nine heap blocks in ten for shape
  fixtures with 70-71, 78-85, 96-97, 101-105, 108-112, 116 and 120 exempt, and
  simulate the auto-analyze with the engine's own
  `mod_since_analyze > autovacuum_analyze_threshold +
  autovacuum_analyze_scale_factor * reltuples` test - the four verdict bands that
  keep a critical false positive separate from an ordinary one, and the two
  mandatory scoring columns. Each family is catalogued fixture by fixture against
  the v17 behavior it targets, with **167 citations, 63 distinct ranges over 33
  files**: the
  equal-image gate (`_bt_allequalimage`'s `INCLUDE` refusal before any lookup,
  per-key support function 4, `btequalimage` and `btvarstrequalimage`'s collation
  test, the `deduplicate_items` reloption and the `!btspool->isunique` build
  gate, and `prosrc`-based internal-function resolution behind the alias and
  impostor tests); partial indexes, whose own population `ANALYZE` estimates as
  `ceil(tupleFract * totalrows)` rather than reading the table's `reltuples`; the
  eight false-positive constructions that must not be rebuilt and the six
  false-negative ones that must be; the threshold, `INCLUDE`-width and
  expression-statistics controls; and the drained-queue and zero-count shapes
  that exercise all four writers of `reltuples`, down to the `-1` a new
  relfilenode leaves. **The page is source-only**, per the concept-page rule: no
  measured number appears on it, the heuristic page keeps its results, its two
  leg scripts and its own deviations, and six limits are named - chief among them
  that a file full of dead-but-unvacuumed entries reads dense to any density
  method, which no fixture in the suite currently closes. All four fenced blocks
  of the heuristic page still hash to their recorded baselines
  (`93b64e2d…`, `7427d62d…`, `c2f99506…`, `7318192e…`), so no SQL or script text
  moved. No server was built or started for this change.

- 2026-09-11: Revised [A COMMENT-Stored Baseline B-Tree Index-Maintenance
  Heuristic for PostgreSQL 12 Through 17
  (unverified)](v17/questions/indexing/btree-comment-baseline-maintenance-heuristic.md#verdict)
  for a follow-up that asked for two changes, and **re-ran both legs end to end**
  at unchanged pins `786db8dcf168bd9df8f55047337525ac19118b1c` and
  `45b88269a353ad93744772791feb6d01bc7e1e42`. The payload is now an 86-byte v2
  shape carrying the **index's own `pg_class.reltuples`** beside the file size and
  the table's count, and the same 20 % up-or-down test runs on all three; a v1
  payload reads `invalid` and re-initializes, measured on both the
  wrong-version and the missing-key shape. The ported mandatory suite now
  **simulates the auto-analyze** a server with autovacuum on would have run, and
  not by hand: the new step applies the engine's own
  `n_mod_since_analyze > autovacuum_analyze_threshold +
  autovacuum_analyze_scale_factor * reltuples` test, read back as 50 and 0.1 on
  both servers, which analyzed **77 of 99 fixture tables on 17.11 and 57 of 97 on
  12.2**, with the rule's boundary visible in its own output at **9.8 % left alone
  and 11.1 % analyzed** on both. The two changes together turn **21 false
  negatives into 4**: 136 of 140 `PASS` on 17.11 and 118 of 122 on 12.2, 0 false
  positives, 0 gate disagreements, 140 of 140 and 122 of 122 stored index counts
  equal to the catalog's, 103 and 85 rebuilds at a mean 86.3 % and 87.0 %
  reclaim, and 0 unexpected server errors on either leg (`make check` 225 and
  192, all contrib suites passing). The third gate **opened 26 fixtures the
  two-gate form skipped and lost none**, 21 of the 26 genuinely bloated at a mean
  76.3 % reclaim; the size test alone still catches `p76`, whose file doubled on
  indexed-key updates while its entry count moved 0.3 %, and no fixture is caught
  by the table count alone. **The four that remain are threshold losses, not gate
  losses** — `p113a`, `p113c`, `p65`, `p67` all had their gate opened and then
  read 0.0-0.1 % wasted, because their dead index entries were never vacuumed and
  `pgstatindex` reports a dense file. Also newly measured: who writes an index's
  `reltuples` and when it is left stale (exact from a build, sampled through
  `tupleFract` from `ANALYZE`, exact from `VACUUM` unless `estimated_count` is set
  or index vacuuming is bypassed under 2 % of heap pages), ten gate boundaries at
  six decimals, 15 comment shapes, and a settled cost of 4,074 buffer hits with
  **zero data-page reads** against 75,847 buffers fully gated. Twelve open
  questions remain, the first being the unvacuumed-entry blind spot; agent
  verification stays `not yet`. Both servers were stopped by the scripts' own
  `stop` stage and the 12 GB sandbox deleted, with no `postmaster.pid`, no
  matching process and an empty socket directory confirmed for each.

- 2026-09-11: Filed [A COMMENT-Stored Baseline B-Tree Index-Maintenance
  Heuristic for PostgreSQL 12 Through 17
  (unverified)](v17/questions/indexing/btree-comment-baseline-maintenance-heuristic.md#verdict)
  at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, measured on two
  isolated servers built out of tree from the v17 and v12 pins (17.11: `make
  check` 225 of 225 plus 1, 8 and 3 for `pgstattuple`, `pageinspect` and
  `amcheck`; 12.2: 192 of 192 plus 1, 5 and 2), with **0 unexpected server
  errors on either leg**. Two filed texts, both executing unmodified on 12.2
  and 17.11 and sharing a 100-line byte-identical gate pipeline: a read-only
  plan statement and a top-level `DO` block that commits once per index. The
  only persistent state is a 72-byte `@btmaint:` payload appended to the
  index's own comment. The sibling estimator page's entire mandatory suite was
  **ported fixture by fixture** - tests 1-17, 18-91 and controls 92-121 - split
  into an as-built baseline phase and a churn phase (74 shape fixtures that had
  no churn of their own get a uniform 90 % heap-block drain; the 25 fixtures
  whose point is that a fresh index must not be touched stay untouched), and
  scored against a measured `REINDEX INDEX`: **140 fixtures on 17.11 and 122 on
  12.2, 119 and 101 `PASS`, 0 false positives of either severity, 140 of 140
  and 122 of 122 gate decisions equal to the same arithmetic recomputed
  independently, 8 of 8 false-positive constructions left alone with a measured
  0.0 % reclaim, and 84 rebuilds at a mean 87.1 % reclaim**. The one structural
  finding is that the specified gate cannot see a partial index draining: all
  **21 false negatives on each server** are partial indexes, in three families
  (subset drained to zero with `tuple_ratio` 1.0000 and `idx_tuple_ratio`
  0.0000; the table moving 15-19 % while the index lost 75-95 %, which includes
  the sibling page's own `b92`-`b95` calibration controls at exactly 18 %; and
  three where no writer had updated any count), and an index-entry gate would
  catch 18 of the 21 on both servers. Also measured: both gate boundaries to six
  decimals (1.200000 fires, 1.199999 skips), a nine-point decision curve
  identical on both servers that reads `0.888 x fraction deleted` and puts the
  40 % threshold at 45.0 % of entries deleted, `wasted_pct` under-estimating the
  rebuild by a mean 8.4 points over 90 measured fixtures with 88 within 15,
  comment survival across `REINDEX INDEX` (OID unchanged) and `REINDEX INDEX
  CONCURRENTLY` (17438 -> 17440, comment md5 unchanged), `reltuples` refreshed
  by the rebuild itself (1000 after `CREATE INDEX`, 2000 after `REINDEX`),
  `ShareUpdateExclusiveLock` for the comment write, the v17 privilege split in
  which a `MAINTAIN` grantee may rebuild but is still refused the comment, 13
  comment-parsing shapes including seven malformed payloads, three consecutive
  runs of which the second and third write nothing, a dry run that changes no
  `pg_description` md5, `pg_dump` carrying all 13 payloads, and a cost profile
  of 21.3-32.6 ms with **zero data-page reads** settled against 108.4-128.3 ms
  and 452 MB read fully gated. **Two defects the suite found were repaired in
  the filed texts before the numbers were taken**: a `LATERAL ... WHERE stage =
  'measure'` that still read every candidate index end to end (57,964 buffers in
  a settled database, now 0), and a malformed marker kept as if it were a human
  note (95 and 97 bytes where a clean initialize writes 72). Nine open questions
  remain, the first being the unmeasured index-entry gate variant; agent
  verification stays `not yet`. Both servers were stopped by the scripts' own
  `stop` stage and the 12 GB sandbox deleted, with no `postmaster.pid`, no
  matching process and an empty socket directory confirmed for each.

- 2026-09-10: Reviewed [Physical Index Statistics, Tuple Counts, and Bytes per
  Tuple in PostgreSQL 12
  (unverified)](v12/questions/indexing/physical-index-statistics-tuple-counts-and-bytes.md#what-an-isolated-122-server-measured)
  end to end at unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`:
  every one of its 354 source citations (228 distinct ranges over 91 files)
  re-read against the pinned checkout, all in bounds and all
  `raw/postgres-12/`, and **no source claim needed correction**. The page now
  carries the mandatory `## Measurement Script` section it lacked, with one
  Bash-and-SQL script, an eight-item usage table, a sixteen-row stage table
  naming every dependency, the apply scope of all eight cluster settings, and a
  last-run record; the published script is byte-identical to the file that
  produced the numbers, and re-extracting it from the page reproduces the
  SHA-256 of both fenced SQL blocks it executes. An isolated 12.2 build (192 of
  192 engine tests, `pageinspect` 5 of 5) measured: a per-writer `reltuples`
  matrix over all seven access methods, in which **one BRIN index reads 14,
  100000 and 13** from build, `ANALYZE` and `VACUUM` and keeps 13 through
  `VACUUM ANALYZE`, hash reads 80000 before accepting the 100000-row estimate,
  and GIN reads 300000 extracted keys; an empty-heap BRIN at 1 then 0 with its
  one physical summary item intact; `btm_last_cleanup_num_heap_tuples` at -1
  then 74961 against the same index's own 75000; `hashm_ntuples` 60000 against
  `reltuples` 75000; a GIN pending list counting 50 heap tuples for 150 keys,
  and a `VACUUM` that wrote no index `reltuples` at all because its heap scan
  skipped pages; **both GiST `pgstattuple` defects quantified** — 0 items for a
  five-row single-page index, and a 42-item overcount that is exactly twice the
  21 pages marked `F_LEAF|F_DELETED`, with no truncation and no FSM entry; the
  full dispatch and privilege matrix with exact refusals, including Bloom as
  `unknown index`; item payloads of 16, 24 and 16 bytes including MAXALIGN
  padding against 54 excluded high keys; `main_bytes / reltuples` swinging
  90.28 to 22.57 on a byte-identical file; and FSM read-backs of 8,160 for a
  reclaimed index page and 7,936 for BRIN. Six open questions were added,
  including that the GiST deleted-page count is not run-stable (15 and 21 across
  runs, the doubling relationship holding each time) and that every number comes
  from one platform at `block_size = 8192`. The server was stopped by the
  published script's own `stop` stage with `pg_ctl -m fast -w stop` and the
  sandbox deleted, with no `postmaster.pid`, no matching process and a free
  port confirmed afterwards.

- 2026-09-10: Reviewed [B-Tree Bloat and Wasted Space From pgstatindex Alone,
  on PostgreSQL 12 and 17
  (unverified)](v17/questions/indexing/btree-bloat-with-pgstatindex.md#re-measured-from-a-published-script)
  end to end at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`: every
  citation re-read against the pinned checkout, both servers rebuilt from the
  two pins in an empty sandbox, and the whole measurement re-run. **The page
  now carries the mandatory `## Measurement Script` section it lacked**, with
  two Bash-and-SQL leg scripts, published fixture DDL, an eight-item usage
  table, a per-stage table, the apply scope of all nine cluster settings, and a
  last-run record; the earlier harness was never published and its sandbox had
  been deleted, so the suite is a reconstruction. It lands close: 17.11 passed
  225 of 225 core tests and 12.2 192 of 192, the filed text still **executes
  unmodified on 12.2** (28 rows against 29 on 17.11, 14 columns), and the
  invalid-index row comes back `4|2|6758400|290|4|820|0|0|90.05|0` digit for
  digit, alongside identical implied leaf capacity (8151.6 and 8152.1), ten
  identical refusal messages, three identical privilege outcomes, the
  22,487,040-byte 1,918-dead-page fixture, the 44.6 % / 7,309-byte worst
  residual, and eighteen accuracy rows to the tenth of a point, including the
  `+1.8` over-estimate on the same 456 kB TOAST primary key and `−2.8` on
  `i_ff10_del90`. **Three claims were corrected in place**: `BTPageOpaqueData`
  has five fields, not four; the invalid-index refusal separates these two
  *minors* rather than the two majors, because `13503eb5905` says in this
  checkout's own history that it was back-patched to all supported versions;
  and a committed concurrent `DROP INDEX` usually costs one row rather than the
  report, because the size prefilter's `pg_relation_size` opens with
  `try_relation_open` and returns NULL, measured at 24 rows against 25 with no
  error, while the abort path did not reproduce in a ten-delay sweep on either
  server. Six open questions were added, the largest being that most figures on
  the page predate the script now filed for them; agent verification stays
  `not yet`. Both servers were stopped with `pg_ctl -m fast -w stop` by the
  scripts' own `clean` stages and the sandbox deleted, with no `postmaster.pid`,
  no process and free ports confirmed afterwards.

- 2026-09-10: Re-ran both suite scripts of [Testing the PostgreSQL 12 Core-SQL
  B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#what-the-2026-09-10-full-re-run-measured-on-darwin-arm64)
  end to end, twice, from an empty sandbox on a second platform, Darwin arm64
  (macOS 26.6.2, Apple clang 21.0.0, ICU 78.3 through `ICU_CFLAGS` and
  `ICU_LIBS`), at unchanged pins `786db8dcf168bd9df8f55047337525ac19118b1c`
  and `45b88269a353ad93744772791feb6d01bc7e1e42`. `make check` passed 225 of
  225 on 17.11 and 192 of 192 on 12.2 with every contrib suite, all five text
  hashes matched, and every verdict count of the 2026-09-09 Linux run
  reproduced: geometry 78 of 78, fresh builds `0 bytes` on 10 of 10, the gate
  at 0 over-credits and worst 28.8 %, calibration digit for digit, the
  numbered suite at 53 withheld with 0 unexplained and 0 contract failures,
  and the 12 leg at 13 PASS / 5 / 1 with `transform_edits=0`; the one moved
  verdict is the known fixture 120 flip. Three script defects were repaired
  first: both `stop` stages used `pg_ctl -m immediate`, which skips the
  shutdown checkpoint and forces recovery on restart, and now use `-m fast -w`
  and confirm no `postmaster.pid`, no process and an empty socket directory
  before `clean` deletes anything; the 12 leg's database-existence check
  connected to a database that did not exist yet; and the 17 leg's `extstat`
  ran before `suite`, so a fresh run measured an empty database. Runtimes on
  this host: 2 min 26 s and 1 min 52 s for the full legs and 65 s for the 17
  leg's scoring stages from a built tree, which records the 12 leg's full-run
  figure at last. Two script-scope open questions closed and one opened: the
  `EXCEPT` attribution returns 31 rows per direction (21 moved numbers, 10
  caveat-only) against the filed 26, and the Linux output that would reconcile
  it was deleted with its sandbox. Both servers were stopped by the repaired
  stages and the 8.4 GB sandbox deleted; agent verification stays `not yet`,
  and the tenth prompt was corrected and restated with the asker's agreement.

- 2026-09-10: Fixed the failed cross-version execution test on [Testing the
  PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#the-portable-extended-statistics-filter)
  at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, and measured the
  fix on both servers the 2026-09-09 run left in place. The `extstat` CTE's
  `AND se.inherited = false` named a `pg_stats_ext` column the pinned 12.2
  server does not have, and a column reference is resolved at parse time, so no
  runtime version guard can save it; it now reads
  `AND coalesce((row_to_json(se) ->> 'inherited')::boolean, false) = false`,
  which parses whether or not the column exists and, where it does not, admits
  the single `ANALYZE` pass such a server records. **The exact filed text is now
  accepted unmodified on 12.2**, with the 12 leg's transformer reporting
  `transform_edits=0`, and on 17.11 the edit is inert: `EXCEPT` in both
  directions over every projected column returns 0 rows in all six fixture
  databases, 186 rows of which 7 are fed by the changed CTE. The previous text,
  rebuilt from the filed one by undoing exactly this edit, reproduces its filed
  SHA-256 `8acd531b…` and is still refused on 12.2 at `LINE 116`, which makes
  the one-line diff auditable. A new `extstat` stage in each script closes the
  widening open question with measurements rather than dropping it: on three
  inheritance parents and one control the filed and previous texts agree
  everywhere, while the old delete-the-line transformer reads 2.3, 60.1 and
  `-33.7` against measured reclaims of 0.0, 59.7 and 0.0 — always
  under-reporting bloat, by 1.5 points where a posting list's TID payload
  dominates and by 34.5 where the widened estimate stops crediting
  deduplication at all. Cost is inside the noise (95.3 ms against 91.6 ms over
  six interleaved pairs, overlapping ranges), the 12 leg's re-scored 19
  fixtures return the same verdict counts, `BASE1` is re-baselined to
  `646df923…`, and the 12 leg's from-a-built-tree runtime is now recorded.
  Three open questions were narrowed and one was closed; agent verification
  stays `not yet`, and the ninth prompt was corrected and restated with the
  asker's agreement.

- 2026-09-09: Reviewed the measurement-script section of [Testing the
  PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#measurement-script-section-review)
  at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, read-only with no
  server started. The page now has the top-level `## Measurement Script` section
  the rule requires, between `## Answer` and `## Context Reviewed` and listed in
  `## Contents`, holding the eight-item usage information, the protocol, both
  scripts, the reading guide, the last-run record and the review itself; no
  subsection heading changed, so every existing link still resolves.
  **Thirteen defects were repaired in place**, the material ones being the
  `awk`/`shasum` extraction recipe the Bash-and-SQL-only rule forbids, the
  `cost` stage missing from the 17 script's own stage list, a
  documented-but-unread `KEEP` variable, `listen_addresses`, `port` and
  `logging_collector` written with no apply scope named, `psql` helpers and the
  `cost` stage running without `ON_ERROR_STOP` (so a failed statement in a `-f`
  script left the status 0), an unguarded `rm -rf "$SANDBOX"`, missing page and
  checkout preconditions, fixture blocks never marked disposable, and the
  undocumented positional dependency of `md_block sql N` on this page's
  fenced-block order. The audit re-derived all five SHA-256 baselines from the
  page in pure Bash, parsed both scripts before and after, re-read the section's
  37 citations, and tested the new containment guard against nine paths. Four
  script-scope open questions were filed: the repaired scripts have not been
  re-run, fixture DDL is marked disposable rather than tagged, the 12 leg's
  cluster settings have no citable apply scope on a v17 page, and the 12 leg's
  runtime was never recorded. No measured number changed and agent verification
  stays `not yet`; the eighth prompt was corrected and restated with the
  asker's agreement.

- 2026-09-09: Added [Reading the results of a
  run](v17/questions/indexing/btree-index-bloat-core-sql-only.md#reading-the-results-of-a-run)
  to the same page at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`,
  at the asker's request and at reader's-guide depth: a map of the output files and the
  result tables each stage leaves behind, one scored row column by
  column with `actual` named as the truth column, the five verdicts and their
  exact thresholds, the three-way reading of verdict plus `reported` plus
  `alertable` that the page scores itself on, a clean-run checklist, the three
  outcomes that look like failures and are not, and a symptom-to-file triage
  list that separates a harness fault from an estimator defect. No measurement,
  no SQL and no pin change; the seventh prompt was corrected and restated with
  the asker's agreement.

- 2026-09-09: Filed two reusable suite scripts, and ran both, on [Testing the
  PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#the-two-suite-scripts-and-the-rules-they-follow)
  at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`. The asker chose a
  corrected restatement of the prompt, both legs built and run, every test
  family the page names, and the scripts kept in the page. `btree_bloat_suite_v17.sh`
  and `btree_bloat_suite_v12.sh` are Bash and SQL only, extract the statement
  texts from the page in pure Bash, and were run end to end: 17.11 passed All
  225 core tests plus 8, 1 and 3 for `pageinspect`, `pgstattuple` and `amcheck`,
  and 12.2 passed All 192 plus 5, 1 and 2. **The partial-index half of the
  mandatory suite is scored against the current statement for the first time** —
  112 fixtures, 59 reported, 53 withheld with every withheld row naming its
  term, 0 contract failures, and three reported critical false positives that
  survive the page's own reading rule. **The cross-version open question is
  answered and the answer is no**: the exact text is refused on the pinned 12
  server at `pg_stats_ext.inherited`, one edit makes it run, and 19 fixtures
  then score there with every gate verdict `ineligible`. Two open questions were
  added (a fixture whose verdict flips with the ANALYZE sample, and the probe
  generator's own 1 MB filter) and three were updated. Agent verification stays
  `not yet`.

- 2026-09-09: Re-verified [Indexes Only on the Parent Versus Only on the Child
  Tables of a Declaratively Partitioned Table in PostgreSQL 12
  (unverified)](v12/questions/indexing/partitioned-index-parent-vs-child.md)
  claim by claim at unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`,
  source-only. All 440 citations (201 distinct ranges, 35 files) resolve in
  bounds inside `raw/postgres-12/` and every checked range supports its claim;
  no defect was found and no page content changed. Structure (22 Contents
  entries, anchors, front matter, title hint, 13 wiki links) re-checked and
  `wiki_lint` clean. Set `verified_by_agent: claude-fable-5-medium
  2026-09-09T16:28:07Z`; the four Open Questions remain runtime-measurement
  items outside a source-only pass, and `verified: false` is untouched.

- 2026-09-09: Corrected [Indexes Only on the Parent Versus Only on the Child
  Tables of a Declaratively Partitioned Table in PostgreSQL 12
  (unverified)](v12/questions/indexing/partitioned-index-parent-vs-child.md)
  at unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`. This source-only
  follow-up supersedes the original summary's blanket ON CONFLICT, definition
  uniformity, DROP INDEX, and root-executor claims. Added the untargeted
  `DO NOTHING` exception, precise attachment-matching limits, owning-constraint
  drop rules, detached/default-partition locks, INSERT versus UPDATE and
  planning-time index opens, and invalid-leaf adoption during table attachment
  without parent invalidation. Added the utility caller's hierarchy pre-locking,
  key structures, catalog/parser generation and extension boundaries. Qualified
  restore-cost and relhasindex claims and recorded the documentation's omitted
  empty-parent ONLY exception. No server run or pin change; original Question,
  SQL, `verified: false` and `verified_by_agent: not yet` are unchanged.

- 2026-09-09: Filed [Indexes Only on the Parent Versus Only on the Child
  Tables of a Declaratively Partitioned Table in PostgreSQL 12
  (unverified)](v12/questions/indexing/partitioned-index-parent-vs-child.md) at
  unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42` (12.2), source-only at
  the asker's request. Prompt hygiene first: the asker chose "correct and
  restate", then scoped the page to the `CREATE INDEX ON parent` cascade versus
  per-partition `CREATE INDEX`, with no server measurements. The finding is that
  the comparison is not symmetric - `DefineIndex` skips the build for a
  partitioned table and recurses, so both designs end with one real index per
  partition, and `plancat.c` ignores `RELKIND_PARTITIONED_INDEX` outright, making
  plan shape, pruning and write-path maintenance identical. The differences are
  DDL, locking and operations, and both directions are enumerated from source:
  the cascade's `ShareLock` on every partition held to commit in a single
  transaction, the outright `CONCURRENTLY` refusal, the unimplemented `REINDEX`
  for both the partitioned index and the partitioned table, the
  `DEPENDENCY_PARTITION_PRI` row plus the absence of any
  `ALTER INDEX ... DETACH PARTITION` in the v12 grammar, the
  `AccessExclusiveLock` index build a mismatched `ATTACH PARTITION` performs, and
  the three parent-only capabilities (`UNIQUE`/`PRIMARY KEY` containing all
  partition key columns, FK target via `transformFkeyCheckAttrs`, and
  `ON CONFLICT` via `infer_arbiter_indexes` plus `get_partition_ancestors`). Also
  documents the `ON ONLY` hybrid and its two traps, the `ExecOpenIndices`
  per-statement cost the parent adds on the root, the `pg_dump` `ON ONLY` plus
  `dumpIndexAttach` restore shape, and the observability split (`pg_indexes`
  includes the parent, `pg_stat_all_indexes` excludes it, `pg_partition_tree` and
  `\dPi+` aggregate it). 230 citations over 22 files, all resolving inside
  `raw/postgres-12/`. Four open questions remain, so agent verification stays
  `not yet`.

- 2026-09-09: Re-verified [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat
  Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#re-verified-on-a-rebuilt-server)
  claim by claim at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, on
  an independently built 17.11 server (`--with-icu --enable-debug`; `make check`
  225/225 and the `pageinspect`, `pgstattuple` and `amcheck` checks passing).
  All 476 citations were re-read against the checkout (68 files, 164 distinct
  ranges, every one resolving and supporting its label) and **every measured
  figure reproduced**: 78/78 geometry cells, `0 bytes` on 10 of 10 fresh builds
  against the published statement's 6, all three deterministic defects, the
  equal-image matrix against `bt_metap`, 132 TIDs at an item length of 808
  bytes, posting mean absolute error 16.06 % to 5.77 %, the seven-pattern
  calibration digit for digit, 367 against 10,003 compression blocks, and both
  validation probes. The pass also **scored the deduplication gate against the
  current statement for the first time** — 27 fixtures, zero over-credits,
  `equalimage` matching the metapage on all 20 `recognized`/`ineligible` rows,
  `i_multi_bad` at exactly 28.8 %, `i_ei_true` at `-226.4 %`, the three `text`
  fixtures fixed from `+7.8 %` to `-0.2 %`, and two under-credits where the pass
  criteria allowed one — and **measured the nondeterministic-collation branch**
  that every earlier `--without-icu` build could not reach. Six reporting
  defects were corrected in place: the published `relpages` comparison
  (26/52/15, not 53/71/5), the non-owner row count (8 of 10, not 9), the
  posting table's inverted sign convention, the statistics-barrier artifact's
  unstated 1000 ms flush-interval precondition, a 32-byte datum described as a
  32-byte tuple, and the platform question, settled as `Linux x86_64` at
  `max_data_alignment` 8 and `database_block_size` 8192. One open question was
  added — a duplicate-heavy multicolumn index with correlated keys and no
  `ndistinct` statistics object reads `-320.0 %` to `-562.1 %`, which
  `CREATE STATISTICS` takes to `0.0 %` — and the platform question was
  replaced by an unpublished-fixture-recipe question. Tests 18-91 and fixtures
  92-121 remain unscored, so agent verification stays `not yet`. The sandbox was
  deleted after filing.

- 2026-09-09: Reviewed the mandatory tests of [Testing the PostgreSQL 12
  Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#mandatory-test-review)
  at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, without building a
  server. The page's numbered suite — tests 1-17 (deduplication gate), 18-91
  (partial indexes), fixtures 92-112 and the change-E fixtures 113-121 — was last
  scored on 2026-08-24 against the superseded six-change text (`bffd166e…`) and
  has never been run against the revised `_r2` statement; the 2026-09-08 numbers
  rest on that day's fixtures alone. The review derives each group's expected
  verdict from the two texts (gate credit unchanged, tests 13-16 relabelled
  `unknown` with a caveat, the partial split expected to hold, `i103` and `x109`
  expected to remain critical false positives, fixture 118 now caveated and
  probe-catchable, `i_multi_bad`'s 28.8 % expected to survive as integer
  `stawidth` truncation), lists eleven gaps (the suite, `EXCEPT` attribution,
  ICU, the 12.2 leg where the text reads `pg_stats_ext.inherited`, role
  coverage, fixture-contract fixes, the scoring column, block size and parallel,
  concurrent and partitioned builds, harness typing, a platform record, cost)
  and files a ten-step protocol with pass criteria. Five open questions were
  added, including a conflict between the page's stated x86-64 Linux platform
  and this repository's Darwin arm64 host. The four SQL blocks re-hashed to
  their baselines and the superseded block was recovered from revision
  `f2d73b4`. Agent verification stays `not yet`.

- 2026-09-08: Implemented open questions 17 through 19 on [Measuring Wasted and
  Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md#the-derived-arithmetic-statements)
  at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, measured on an
  isolated 17.11 server built out of tree from the checkout. **17**: every literal
  size is now derived from `pg_control_init()` or measured by a layout probe that
  reads `SizeOfPageHeaderData` 24, `sizeof(ItemIdData)` 4 and the 8-byte GIN
  special area off an empty GIN index's root, reaching the FSM's 8160 from that
  pair; the derived census matches the guarded one in 240 of 240 cells on two
  databases at the same 7,890 buffers, and the derived probe adds
  `malformed_pages` and `undecoded_pages`. **18**: a `SHARE ROW EXCLUSIVE`
  measurement protocol replaces detection with enforcement — eight concurrent
  commands blocked, readers unaffected, 40 censuses that read nine different
  dead-page counts across one VACUUM became 20 identical ones — with its one hole,
  an owner's `gin_clean_pending_list()`, measured at `bloat_pct` 8.66 -> 82.74
  inside a locked transaction. **19**: the wraparound failsafe (reached with
  `autovacuum_freeze_max_age` at its 100000 minimum, a restart, plus 120,000
  burned xids), four `-m immediate` crashes giving 0, 0, 2 and 6 byte-for-byte-zero
  pages at the file tail, and three corruption shapes including one the buffer
  manager refuses before any SQL guard runs. The core programme reproduced a fifth
  time and the churn sweep digit for digit; the published extended fixture SQL does
  not reproduce the first corpus's extended scoring table, filed as new open
  question 20. Agent verification stays `not yet`; the sandbox was deleted after
  filing.

- 2026-09-08: Implemented all ten repair plans on [Testing the PostgreSQL 12
  Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#what-the-ten-plans-changed)
  at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, and measured the
  result on an isolated 17.11 server built out of tree from the checkout.
  `make check` passed 225 of 225 tests; the `pageinspect` and `pgstattuple`
  contrib checks passed. The revised statement reports exactly `0 bytes` on 10
  of 10 freshly built indexes with keys from 8 to 2000 bytes (the superseded one
  was wrong on 4, worst `-33.9 %`), its geometry closed forms reproduce
  `relpages` in 78 of 78 (key width, fillfactor) cells, and its point estimate
  equals the `REINDEX INDEX` outcome in 6 of 7 insertion-pattern fixtures. All
  three deterministic defects reproduced and are fixed, and three more surfaced
  under measurement: the missing hard-fit reservation, the internal-level
  minus-infinity item plus never-closed rightmost page, and a three-byte-too-wide
  expression width. Added a three-state `equalimage` column scored against
  `bt_metap`, two-size posting-tail pricing (mean absolute error 15.92 % to
  5.73 %), `numeric` output, `reltuples_writer`, seven caveat strings and a
  companion probe generator. Four measured residuals stay open. The sandbox was
  deleted after filing.

- 2026-09-07: Sixth pass on [Measuring Wasted and Reclaimable Bytes in a GIN Index
  With Contrib Extensions on PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md#the-guarded-census-statement)
  at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`: every citation
  re-read against the checkout (479 after the pass, 218 distinct ranges over 64
  files, all supporting their claims); 17.11 rebuilt out of tree; the published
  fixtures reproduced byte for byte a fourth time; the revised plan's query guards
  implemented as a guarded census statement that agrees with the published one in
  all 208 shared cells and reads the same 7,892 buffers; and the plan's acceptance
  cases run: five hand-corrupted index files (one of which aborts the published
  statement outright), a restricted role, an invalid index, both temporary-index
  cases, a held `REPEATABLE READ` snapshot, two bypassed index cleanups, a
  concurrent VACUUM, a concurrent `REINDEX CONCURRENTLY`, an insert stream, the
  seven rebuilds and a three-budget rebuild of `f1`. Open questions 17 through 19
  rewritten; 1, 3 and 6 narrowed. The 27-fixture corpus was not re-run; agent
  verification stays `not yet`; the sandbox was deleted after filing.

- 2026-09-07: Reviewed all ten repair plans under Open Questions on
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#plan-review)
  against unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`. All ten are
  kept. Three findings are deterministic defects in the current statement:
  missing `inherited = false` filters double-count inputs for inheritance parents,
  the expression-statistics visibility test uses the table's privileges while
  `pg_stats` filters by the index's owner-only ACL, and unguarded `bigint` casts
  can abort the report. Also filed: an ordered publication barrier from the
  backend's idle flush, VACUUM as a second writer of index `reltuples`, an
  `EXISTS` and `GROUP BY` probe design, confirmation of the posting-tail formula,
  a leaf-capacity identity for uniform tuples up to 896 bytes, the complete
  built-in equal-image inventory with the pattern-opclass collation refusal,
  `pg_size_pretty(numeric)`, out-of-tree build and hash re-baseline requirements,
  and per-insertion-pattern threshold calibration, with a revised implementation
  order. Executable SQL, source pin and verification fields are unchanged; no
  server was built or started.

- 2026-09-07: Focused [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md) on its current
  recommended statement. Removed superseded SQL, alternate-method comparisons,
  historical follow-up narratives and references unrelated to the retained model.
  Consolidated current limitations and proposals under Open Questions, rebuilt
  Contents and the source inventory, and repaired links to removed sections.
  Executable SQL and verification fields are unchanged; SQL comments now describe
  the retained stages without relying on removed change-history sections. No
  source repin or server execution was performed.

- 2026-09-06: Pruned the Open Questions list on
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#open-questions)
  against the latest recommended SQL: 35 obsolete or unrelated entries removed,
  56 retained. Current width, population, packing, suppression, reporting and
  validation gaps remain; questions solely about other versions were outside
  the v12/v17 cleanup scope. No SQL, source pin or verification field changed.

- 2026-09-06: Reviewed open question 2 on
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md#partial-index-widths-and-zero-counts)
  at unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`.
  Proposed a per-attribute width-provenance guard and independent count
  validation. Corrected the attribution of both historical failures to the
  deduplication gate: the floor and change B do not depend on it. Filed an
  integration sketch, diagnostic policy, costs and acceptance tests; preserved
  every existing SQL block. No server was started or historical measurement
  rerun, and cross-version validation remains open. Verification fields remain
  `verified: false` and `verified_by_agent: not yet`.

- 2026-09-05: Reviewed the original six-step plan on
  [Measuring Wasted and Reclaimable Bytes in a GIN Index With Contrib Extensions
  on PostgreSQL 17 (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md#plan-review)
  against unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`.
  Filed seven source-backed findings and a revised implementation and validation
  plan. Corrected unconditional rebuild-bound wording, the reversed whole-page
  inequality, and the interpretation of recycling and consistency checks.
  Recorded unsupported-format and classification guards as unimplemented work;
  preserved the published SQL and earlier measurements. This was a source-only
  plan review, so `verified_by_agent` is `not yet` and human verification is unchanged.

- 2026-09-03: **new question page, source and history only**, [How Bottom-Up Index Deletion and B-Tree
  Deduplication Work in PostgreSQL 17
  (unverified)](v17/questions/indexing/bottom-up-deletion-and-btree-deduplication.md), pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). Prompt hygiene was applied first and the asker chose
  "correct and restate", then chose **source-and-history scope** (no server built, no measurements), a single
  new page under `indexing`, and **comprehensive** coverage of the adjacent mechanisms.
  **Answer: both are leaf-page-local, last-second attempts to avoid a leaf page split**, run from
  `_bt_delete_or_dedup_one_page` in a fixed order that is *simple deletion, then bottom-up deletion, then
  deduplication* — the README calls dedup "our last line of defense" and bottom-up "our second last".
  Selection is decided by four booleans; the two non-obvious ones are the `checkingunique && !uniquedup`
  early return (the documented unique-index heuristic that skips straight to a split) and the
  `uniquedup = true` that a *failed* simple-deletion pass sets, which is how bottom-up can fire on a
  non-unique index with no executor hint. The `indexUnchanged` hint is per index, key-columns-only, cached
  in `IndexInfo`, deliberately blind to `INCLUDE` columns and index predicates, and only considered for a
  `TU_All` (non-HOT) update. The table-AM contract asks for `Max(BLCKSZ/16, newitemsz)` (512 bytes at the
  default `BLCKSZ`) and reports success at `Max(BLCKSZ/24, newitemsz)` (341 bytes) — a *higher* bar than
  "the new item fits" — while `neverdedup` returns true on zero duplicate intervals purely to stop a
  pointless dedup pass; the return value "is always just advisory information". heapam is in control of
  cost: promising-TID counts are rounded to powers of two with a floor of 4, all but the best
  `BOTTOMUP_MAX_NBLOCKS` = 6 blocks are discarded up front, `BOTTOMUP_TOLERANCE_NBLOCKS` = 3 defines
  favorable contiguity, and three give-up rules plus a target-halving decay bound the work.
  **Two asymmetries are the page's main findings.** First, deduplication requires `allequalimage` but
  bottom-up deletion "deliberately omit[s] an index-is-allequalimage test", so on a `numeric` or
  nondeterministic-collation index bottom-up deletion still runs and dedup never does. Second,
  `CREATE INDEX` gates build-time dedup on `!btspool->isunique`, so a unique index is *never* deduplicated
  at build time even though it can be at insert time. Also filed: bottom-up deletion is **B-tree only**
  (GiST and hash use the `index_compute_xid_horizon_for_tuples` shim, which hardcodes `bottomup = false`);
  both need only an exclusive buffer lock, not `VACUUM`'s cleanup lock; and `Btree/DELETE` **cannot**
  distinguish the two deletion strategies, because `_bt_delitems_delete` is shared. Six worked examples,
  including byte arithmetic that reproduces the documentation's own 616-byte 100-TID posting list
  (`16 + 100 * 6`) and derives a 222-TID ceiling for an `int4` key at `maxpostingsize` 1352.
  **Observability and test gaps**: no counter, wait event, progress view or `EXPLAIN` field exists for
  either mechanism, and no test in the tree names bottom-up deletion — an exhaustive search of `src/test`
  and every contrib test directory for `bottom-up`/`bottomup` returns nothing; the closest coverage is
  `btree_index.sql`'s 1,350-iteration unique-index `DELETE`/`INSERT` loop, which asserts nothing about it.
  History is dated by presence test of the defining symbol at each release tag, not `git tag --contains`:
  14 commits from `0d861bbb702` (dedup, v13) and `d168b666823` (bottom-up, v14) through `3b42bdb4716`
  (v17), and **v17 changed nothing behavioral** — `nbtdedup.c` differs from `REL_16_0` only in its
  copyright line, the heapam index-deletion region is identical to `REL_17_0`, all four tuning constants
  are textually unchanged since `REL_14_0`, and the v17 read-stream work left this path on plain
  `PrefetchBuffer`/`ReadBuffer`. Six open questions, the first being that nothing on the page is measured.
  406 citations across 44 files verified to resolve, sit in range and cite only `raw/postgres-17/`; 189
  identifier labels name a symbol inside their own hunk and all 35 `## Contents` anchors resolve in
  document order. `verified_by_agent: not yet`; `verified:` untouched.

- 2026-09-02: **existing question page deepened in place**, [How the REPACK Command Works in PostgreSQL
  19, and Its 58 Feature-Scope Commits (unverified)](v19/questions/storage-and-vacuum/repack-command.md),
  unchanged pin `135b867a530cac2e3796d87c852b53bef40f0077` (`REL_19_BETA3-130-g135b867a530`). Prompt
  hygiene was applied first and the asker chose "correct and restate" (`does repack has` ->
  `does REPACK have`, `throtle` -> `throttle`, `i/o` -> `I/O`), then chose to **deepen the existing
  `## I/O Impact and Throttling` section** rather than file a duplicate page, at **source-and-history
  scope** — no v19 server was built and the section carries no measurements.
  **Answer: `REPACK` cannot be throttled.** `ExecRepack()` takes exactly three options (`VERBOSE`,
  `ANALYZE`, `CONCURRENTLY`), none about I/O; `vacuum_delay_point()` appears in `vacuumlazy.c`,
  `analyze.c` and the index AMs but nowhere in `repack.c`, `heapam_relation_copy_for_cluster()` or
  `rewriteheap.c`, whose only interruption point is `CHECK_FOR_INTERRUPTS()`; and no background process
  ever issues one, since `cluster_rel()`'s only callers are `ExecRepack()` and `VACUUM (FULL)` and
  autovacuum never sets `VACOPT_FULL`. **The section's previous claim was corrected**: it implied the
  blocking rewrite writes through shared buffers with a BULKWRITE ring. It does not — `begin_heap_rewrite`
  opens an `smgr_bulk_start_rel()` stream, so the blocking path **bypasses the buffer manager** and calls
  `smgrextend()` directly, WAL-logging in batches of up to `XLR_MAX_BLOCK_ID` = 32 pages and writing no
  WAL at all under `wal_level = minimal` (`RelationNeedsWAL()` is false for a same-transaction relation);
  `BAS_BULKWRITE` covers only the `CONCURRENTLY` copy, and btree index builds use the same bulk-write
  interface. **New findings**: the blocking copy dirties the old heap by taking an exclusive buffer lock
  per tuple so `HeapTupleSatisfiesVacuum()` hint bits stick ("rewriting most of the old table during
  VACUUM FULL doesn't exactly help", says the source); the concurrent copy dirties it instead through
  `heap_page_prune_opt()`, which the blocking `SnapshotAny` scan never reaches because page-at-a-time mode
  is off; TOAST is rewritten in **both** modes with chunk inserts that carry no bulk-insert state; the
  index-scan copy path uses a bare `ReadBuffer()` with no strategy, read stream or I/O combining; the v19
  BULKREAD ring is no longer a flat 256 kB but grows by `io_combine_limit * effective_io_concurrency`
  blocks; the sequential read stream takes its look-ahead from `effective_io_concurrency`, **not**
  `maintenance_io_concurrency`; and `pg_stat_io` cannot see the blocking rewrite's writes at all, because
  `IOOP_WRITE`/`IOOP_EXTEND` are counted only in `bufmgr.c`/`localbuf.c`.
  **Doc-versus-source discrepancy filed under Open Questions**: `ref/repack.sgml` still advises
  `enable_sort = off` to avoid the sort file, but `plan_cluster_use_sort()` compares only `total_cost`
  while `cost_sort()` records a disabled `enable_sort` in `disabled_nodes` and adds no cost (Robert Haas's
  `e22253467942`, an ancestor of the pin); the paragraph predates REPACK, sitting in `cluster.sgml` at
  `ac58465e061^`, and only `enable_indexscan = off` still works, via an explicit short-circuit.
  The section now has four subsections, a 13-row settings table stating restart/reload/session scope for
  every GUC, and a named list of non-controls. 377 citations across 27 new and existing files verified to
  resolve, sit in range and cite only `raw/postgres-19/`; all 31 `## Contents` anchors resolve in document
  order. `verified_by_agent: not yet`; `verified:` untouched.

- 2026-09-02: **new question page, built and measured**, [Improvements Since PostgreSQL 12 in Storage
  Performance, Query Planning, Index Bloat, and Vacuum, as of PostgreSQL 17
  (unverified)](v17/questions/storage-and-vacuum/improvements-since-v12.md), pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). Prompt hygiene was applied first and the asker chose
  "correct and restate" (six corrections), then chose **build-and-measure scope**, a **single combined page**
  under `storage-and-vacuum`, and **comprehensive** per-area coverage. Two isolated servers were built out of
  tree from this repo's own pins - 17.11 from `raw/postgres-17` and 12.2 from `raw/postgres-12`
  (`REL_12_2`) - with identical non-default settings, `autovacuum = off`, and per-table
  `autovacuum_enabled = false`, so 16 measurement runs differ only because the engine differs.
  **Release dating does not use `git tag --contains`**, because it is wrong for any reverted-then-reintroduced
  feature: it would have placed `MAINTAIN` in v16 (commit `60684dd834a` is an ancestor of `REL_16_0`, but
  `151c22deee6` reverted it and `ecb0fd33720` re-landed it for **v17**) and `recovery_prefetch` in v14
  (`1d257577e08` reverted, re-landed as `5dc0418fab2` for **v15**). Every date instead comes from a presence
  test of the defining symbol at each release tag; the eager/lazy freezing strategies of `4d417992613` are
  excluded because `6c6b4972664` reverted them the same day and no release shipped them. The method also
  showed that v13's dedup entry point was `_bt_dedup_one_page` (not today's `_bt_dedup_pass`) and that Memoize
  shipped in v14 already renamed, the master rename `83f4fcc6550` having been back-patched.
  **Index bloat**: deduplication (v13) 22,519,808 -> 6,979,584 bytes (-69.0%) on 100 distinct keys and
  66,486,272 -> 4,030,464 (-93.9%) on a single-value text index, while two all-distinct indexes are
  **byte-identical** across the gap (22,487,040 and 11,255,808, same 2,733 leaf pages, same 90.06% density);
  bottom-up deletion (v14) was isolated from dedup with `deduplicate_items = off` - legitimate because
  `_bt_delete_or_dedup_one_page` "deliberately omit[s] an index-is-allequalimage test" - giving **-64.3%
  alone** where the key never changes and **byte-identical to 12.2** (58,449,920) where the keys do change,
  the 61.6% saving there being entirely dedup working on incidental duplicates.
  **Vacuum**: the v17 TidStore cuts index passes **18 -> 2** over 3,000,000 dead tuples at
  `maintenance_work_mem = 1MB` (12.2 capping at 174,517 TIDs per pass over an identical 28,038-page heap), and
  the byte-based budget in `dead_items_alloc` explains the progress view swapping `max_dead_tuples`/
  `num_dead_tuples` for `max_dead_tuple_bytes`/`dead_tuple_bytes`/`num_dead_item_ids` plus `indexes_total`/
  `indexes_processed`; the v14 bypass (2% of `rel_pages` **and** under 32 MB of TidStore) turns two full index
  scans into `index scan bypassed` at 22 buffer hits and 391 bytes of WAL.
  **Query planning**: Memoize 572,305 -> 586 buffer hits (977x), incremental sort 7,447 -> 11 buffers and
  31.867 -> 0.601 ms, v17 GROUP BY reordering deleting a 1,000,000-row sort, and the v17 SAOP rework
  1,504 -> **5** buffers on 500 clustered keys.
  **Storage**: the v17 read stream cuts a cold 53,192-block seq scan 53,210 -> 3,346 read syscalls, and the
  `io_combine_limit` sweep (1.000/3.994/15.897/31.568 blocks per call at 8/32/128/256 kB) reproduces 12.2's
  53,210 calls **exactly** at 8 kB, isolating block combining as the whole of the gain.
  **Three results contradict the obvious expectation**: v13 disk-based hash aggregation is *slower* than
  17.11's own sort path (840.533 ms/61,208 kB versus 786.466 ms/23,504 kB, against 12.2's 992.216 ms/27,416
  kB), so the real gain on that query is v15/v16 sort work; the SAOP rework is worth nothing when array
  elements do not share leaf pages (1,501 versus 1,504); and v16 page-level freezing freezes **nothing** after
  a bulk load at default settings on *either* major - the source's `hint_bit_fpi` gate predicts why, and
  turning on the `postmaster`-context `wal_log_hints` flips 17.11 to all 3,704 pages and 300,000 tuples frozen
  for 31,380,997 bytes of WAL while 12.2 still freezes none. Seven open questions, including unmeasured LZ4/
  Zstandard ratios (this host has no `lz4.h`/`zstd.h`, so both builds are pglz-only and the build gate is
  measured instead) and the fact that `read_bytes` was 0 on every run, so no physical device I/O was measured.
  109 citations across 27 files verified to resolve, sit in range and cite only `raw/postgres-17/`; 87
  identifier labels name a symbol inside their hunk and all 16 `## Contents` anchors resolve in document order.
  `verified_by_agent: not yet`; `verified:` untouched.

- 2026-09-01: **new question page, source and history only**, [How VACUUM and Autovacuum Truncation Works in
  PostgreSQL 17, Whether It Covers TOAST, and What Changed Since PostgreSQL 12
  (unverified)](v17/questions/storage-and-vacuum/vacuum-truncation-and-toast.md), pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). Prompt hygiene was applied first and the asker chose
  "correct and restate", then chose **source-and-history scope**, so no server was built and the page carries no
  measurements. **Answer**: relation truncation is the last step of a lazy `VACUUM`, the only part of it that takes
  `AccessExclusiveLock`, and it removes a **suffix** only; autovacuum runs the identical code. `nonempty_pages` is
  set during the heap scan from `hastup`, and pruning deliberately does **not** set `hastup` for `LP_DEAD` items, on
  the assumption they become `LP_UNUSED` in the second pass - which is exactly why the value is provisional and the
  backwards `count_nondeletable_pages` re-scan is *necessary rather than optional*, and why it stops at any
  `ItemIdIsUsed` line pointer. The thresholds are OR-ed (`>= 1000` trailing pages **or** `>= rel_pages / 16`), so the
  fraction rule governs below 16,000 blocks and the flat 1000-page rule above it; neither is tunable. The lock is
  taken with `ConditionalLockRelation` for ~100 retries of 50 ms, the scan self-suspends within 20 ms of a detected
  waiter and commits a partial truncation, and no `vacuum_delay_point` runs while the lock is held.
  **TOAST: yes**, and the interesting part is whose setting decides - since **17.6** (`2e0b5d252b1`, Michael
  Paquier/Nathan Bossart, "Avoid scribbling of VACUUM options", backpatched through 13) `vacuum_rel` copies
  `VacuumParams` before resolving the reloption, so the TOAST table reads its own `toast.vacuum_truncate` instead of
  inheriting the parent's resolved value, and a second relation in `VACUUM a, b` no longer inherits the first's; the
  same commit added the six `vacuum-truncate-*`/`vacuum-index-cleanup-*` injection points whose test emits four
  notices in enabled/disabled/disabled/enabled order. A main-table `vacuum_truncate` never propagates to TOAST (the
  only TOAST fallback is for `AutoVacOpts`), and autovacuum never recurses into TOAST at all - it schedules TOAST
  tables in a second `pg_class` pass. **Since v12**: 16 changes attributed to commits and first-containing release
  tags, the behavioral ones being the `old_snapshot_threshold` veto disappearing with "snapshot too old" (v17
  `f691f5b80a8` - v12 refuses to truncate at all when that feature is on), the wraparound-failsafe veto (v14
  `1e55e7d1755` + `60f1f09ff44`, global flag v16 `71a825194fd`), the `pg_usleep` -> `WaitLatch` change that produced
  the `VacuumTruncate` wait event (v15 `70685385d70`), `PROCESS_TOAST` (v14) / `PROCESS_MAIN` (v16), `toast_parent`
  privilege checks (v17 `ecb0fd33720`), and the 17.6 scribbling fix; `RelationTruncate` separately gained batched
  fork truncation (v13 `6d05086c0a7`), `RelationPreTruncate` (v13 `c6b92041d38`) and a checkpoint interlock (v15
  `412ad7a5563`, extended 17.3 `d4ffbf47b2d`/`66aaabe7a18`). Unchanged: both size constants, all three timing
  constants, the conditional-lock strategy, the relation-grew bailout and the `ItemIdIsUsed` test. Six open
  questions, including an unreachable `vacuum-truncate-auto` injection point and the untested consequence that a
  1 TB heap with 999 trailing empty pages is never truncated. 177 citations across 20 files verified to resolve,
  sit in range and cite only `raw/postgres-17/`; 21 `## Contents` anchors resolve in document order.
  `verified_by_agent: not yet`; `verified:` untouched.

- 2026-09-01: **claim-by-claim review** of [How pg_plan_advice Works in PostgreSQL 19, and All Its
  Commits (unverified)](v19/questions/query-planning/pg-plan-advice.md) at the unchanged pin
  `135b867a530cac2e3796d87c852b53bef40f0077`, source-only at the asker's chosen scope (no v19 server
  built). Every citation was re-resolved (237 before the edits, **278 after, across 48 files**, all in
  range and all `raw/postgres-19/`), all 56 `## Contents` anchors re-checked, and **all 56 listed
  commits re-verified** for hash, subject, author, author date and ancestry; `git log --
  contrib/pg_plan_advice/` returns exactly the 28 module commits the page lists, and the support list
  is complete for `pgplanadvice.sgml`, `src/test/modules/test_plan_advice` and the `headerscheck`
  exclusion. **Six corrections, made in place.** (1) `PGS_CONSIDER_PARTITIONWISE` is never cleared by
  the module — all eight mask writes are `&= ~` and none of their masks holds that bit, which the page
  had described as "preserved unless explicitly removed"; partitionwise advice instead clears
  `PGS_JOIN_ANY` to induce a partitionwise join or `PGS_APPEND | PGS_MERGE_APPEND` to prevent one.
  (2) `joinrel_setup_hook` reads only the trove's Gather/partitionwise `REL` slice, not join-method
  advice. (3) The prepared-statement mechanism was wrong: `PREPARE` does not plan at all
  (`PrepareQuery` stops at `CompleteCachedPlan`), so the planner runs inside the first
  `EXPLAIN (PLAN_ADVICE) EXECUTE` and still generates nothing, because the plan cache plans with no
  `ExplainState` (`ExplainExecuteQuery` -> `GetCachedPlan` -> `BuildCachedPlan` -> `pg_plan_queries`,
  which hardcodes `NULL`) — exactly the limitation core's `c83ac02e` message records. (4) The
  star-schema regression example was quoted three lines deep when the block is four; `NO_GATHER(f d1
  d2)` restored. (5) The `3ab3f33281f` entry conflated the renamed *generated* `SEQ_SCAN`/`NO_GATHER`
  targets with the *supplied* `DO_NOT_SCAN(alt_t2@exists_to_any_1)` in `sql/alternatives.sql`, while
  the generated `DO_NOT_SCAN(alt_t2@exists_1)` never changed. (6) `ea203d371de` is Richard Guo's
  commit, not Robert Haas's. The module's own TAP test `t/001_foreign_scan.pl` — most of
  `89f5f860cc5` by line count — was missing from both the commit entry and the testing section, which
  is now three layers; smaller fixes cover the README-versus-`5883ff30` attribution of the sort-order
  gap, chronological ordering of two core commits, and the `4321dcad`, `4f888d0f` and Álvaro Herrera
  details. `verified_by_agent` moved to `claude-opus-5-max 2026-09-01T14:07:51Z`; `verified:`
  untouched.

- 2026-09-01: **repin v19**, `67342a148632801d44c2fb9a7bf4231b6827c5d2` -> `135b867a530cac2e3796d87c852b53bef40f0077`
  (`REL_19_BETA3-26-g67342a14863` -> `REL_19_BETA3-130-g135b867a530`), at the asker's request to move v19 to the
  latest `REL_19_STABLE` commit. The branch is **still stamped `19beta3`** in `configure.ac` and `meson.build`;
  upstream has no `REL_19_RC1` or `REL_19_0` tag, so the branch tip is the only "latest" available and no release
  stamp moved in the range. **All 104 commits were reviewed**: 6 change a filed claim, 7 more touch a cited file
  without changing one, 91 are unrelated. **REPACK feature-scope commits 55 -> 58** — `9bb8e16bd53` gives
  `repack_is_permitted_for_relation()` an `already_locked` argument so only the two unlocked discovery loops treat a
  concurrently dropped relation as a skip while locked callers assert; `f23de46e15b` replaces `vacuum_relation` with
  `qualified_name opt_name_list` in the `RepackStmt` production, so the previously accepted but never honored
  `REPACK ONLY t` and `REPACK t *` are now syntax errors (`VACUUM (FULL) ONLY t` is unaffected); and `dc8628e55d4`
  aligns `ddl.sgml`, `maintenance.sgml`, `monitoring.sgml` and `mvcc.sgml` with REPACK's existence, documenting
  `pg_stat_progress_repack` as covering all three rewrite commands and naming REPACK in the `ACCESS EXCLUSIVE` list
  with its CONCURRENTLY exception. **`pg_plan_advice` module commits 27 -> 28** — `400c810ddbd` tightens the
  `FOREIGN_JOIN` sublist test from `== 1` to `< 2`, so `FOREIGN_JOIN(())` is rejected. **Two autovacuum fixes**, both
  post-beta3: `4af0528a0e4` calls `parallel_vacuum_propagate_shared_delay_params()` after
  `AutoVacuumUpdateCostLimit()` so a rebalanced cost limit reaches the parallel workers instead of waiting for a
  `SIGHUP` (previously they could spend up to twice the configured budget), with a third TAP case and the new
  `autovacuum-worker-cost-balanced` injection point; and `7ddb9c41a13` gives `pg_stat_get_autovacuum_scores()` the
  TOAST-to-main reloption fallback `do_autovacuum()` already had, via a pre-pass over `pg_class`, so the view matches
  the documented promise that it computes scores the way a worker does. The on-access VM-setting algorithm, the
  scoring math, the parallel-worker cap, `repack_worker.c`, `pgrepack.c`, `ref/repack.sgml`, the logical-decoding
  files, and every other cited behavior file are byte-identical across the range. 102 citation fragments were
  re-anchored and 3 `repack.c#repack_is_permitted_for_relation` anchors repointed by hand (the old range overran the
  function); the `gram.y` anchors moved 52 lines because of the `ALTER TABLE ... MERGE/SPLIT PARTITION(S)` revert
  `3e8bcc8644f`, which also moved `parsenodes.h#RawStmt`. All 739 v19 citations resolve, sit in range and cite only
  `raw/postgres-19/`. `verified_by_agent` stays `not yet` on all four v19 pages, because a repin is not a
  claim-by-claim re-verification; `verified:` untouched.

- 2026-08-31: **fourth follow-up, one added column**, on [Measuring Wasted and Reclaimable Bytes in a GIN
  Index With Contrib Extensions on PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md), unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). The asker asked for a bloat percentage column in the
  census statement, built from what the statement already computes, and chose `waste + slack` over the two
  narrower definitions. `bloat_pct` is now a **four-line hunk** in the `SELECT` list -
  `((deleted_pages + new_pages) * block_size + entry_slack + data_slack) / main_fork_bytes`, gated on
  `gin_version = 2` like the slack columns - and nothing else in the statement moved: the filed text and the
  amended text returned **identical values in all 175 pre-existing cells** over seven indexes, and
  `EXPLAIN (ANALYZE, BUFFERS)` read `shared hit=7568` either way, so the column costs no page read.
  **Measured on two servers built from this repo's own pins**, 17.11 in `.wiki-runtime/tmp/ginpct17/` and
  12.2 in `.wiki-runtime/tmp/ginpct12/`, both deleted after filing: the seven published fixtures were rebuilt
  from the page's own SQL, censused, and then rebuilt index by index with `REINDEX INDEX`. The column
  reproduces the page's `waste+slack %` scoring column exactly (64.12 / 75.30 / 48.05 / 49.80 / 95.22 / 51.34
  / 54.15), it is **identical on both majors** - 178 of 182 cells match, the four that differ being `f7`'s
  already-documented 128-and-10-byte slack gap - and both majors' rebuilds landed on the same seven byte
  counts, so the scoring is the same on each. **The column also forced two of the page's own rules to be
  rewritten rather than quietly contradicted**: "never publish their sum as bloat" and the entry-slack
  paragraph now describe what the number is worth, because it over-read every rebuild here by **+5.01 to
  +49.80 points** - `f3_fresh_gin`, never churned, reads **48.05** while `REINDEX` returns nothing, and
  `f4_empty_gin`, an index over an empty table, reads **49.80** over a single entry page holding 8,160 free
  bytes, a floor that comes from `entrySplitPage` halving what it splits. A new eighth fixture measures the
  pending-list hole: censused with a live 246-page pending list an index read `bloat_pct` **8.66** beside
  `pending_pct` **81.73** while `REINDEX` reclaimed **67.77%** (2,465,792 -> 794,624 bytes, byte-identical on
  12.2), and the same index read **44.96** straight after its rebuild. Rounding is documented too: the column
  rounds the summed bytes, so `f2_pending_gin` prints 64.64 + 10.65 = 75.29 against a `bloat_pct` of 75.30.
  The published statement was extracted from the page's own Markdown and re-run on both servers to produce
  the numbers filed. Open questions went 15 -> 16: the column has no actionable threshold, because its floor
  is a fresh build's fill (50.16% to 72.11% across opclasses, and itself a function of
  `maintenance_work_mem`). 307 citations across 48 files verified to resolve, sit in range and cite only
  `raw/postgres-17/`; 41 `## Contents` anchors resolve and match document order, and one stale label was
  corrected on the way through - `gindatapage.c#dataPlaceToPageLeaf` names no function in this checkout, and
  the hunk it cites sits inside `dataBeginPlaceToPageLeaf`. `verified_by_agent` set to
  `claude-opus-5-max 2026-08-31T18:49:20Z`; `verified: false` untouched.

- 2026-08-31: **new question page, source plus measurements**, [How Reliable the Catalog-Statistics Table and TOAST
  Bloat Query Is in PostgreSQL 12
  (unverified)](v12/questions/storage-and-vacuum/catalog-statistics-bloat-query-reliability.md), pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (12.2, tag `REL_12_2`). The asker supplied the widely circulated
  `pg_stats`/`pg_class` bloat-estimate statement and asked how reliable it is. **Verdict: a usable screen and a bad
  measurement.** Scored on an isolated 12.2 server over 26 fixture relations with three independent readings each -
  the statement, exact `pgstattuple`, and a real `VACUUM FULL` as arbiter. Over 21 scored rows: mean absolute error
  **9.47 points**, 13 within 1 point, min **−50.00**, max **+33.00**; the asker's chosen ground truth, `pgstattuple`'s
  `dead + free`, scored **10.79** against the same rewrites with a **−86.41** miss. As a triage screen it scored
  **9 TP / 2 FP / 5 FN / 9 TN**. Every large error is traced to a line of the statement: **−50.00** on a table deleted
  but not re-analyzed, **−25.05** because `nullhdr2 = MAX(null_frac) * MAXALIGN(24 + n/8)` charges a second aligned
  header (68.02 modelled bytes/tuple against a real `t_len` of 40, where the engine charges 8), **−11.98** because
  `ceil(toast.reltuples / 4)` is byte-exact for 6,400-byte payloads (8,192,000 predicted, 8,192,000 delivered) but
  over-predicts 1.5x when a 2,100-byte payload puts 6 chunks on a page, **−9.00** on an inheritance parent where
  `analyze_rel`'s second pass yields 4 `pg_stats` rows for 2 attributes and doubles `datawidth`, **+21.00** from
  per-column alignment padding (60.00 modelled against 72.00 real), **+33.00** from dividing by `bs - 20` with no
  per-page floor (2.982 implied tuples where 2 fit), and **+31.00** from having no `fillfactor` term. Five relation
  classes never get a number - matviews (absent from `information_schema.columns`), partitioned parents (absent from
  `pg_stat_user_tables`, which is `relkind IN ('r','t','m')`), `STATISTICS 0` tables, never-analyzed tables, and empty
  tables - and **no `can_estimate = false` row can pass the published `WHERE` clause**, so a 31.88 MB table with 74.99%
  reclaimable is built through six CTEs and discarded. The `no_stats` CTE's stated purpose does not fire on this major:
  a `json` column does get a `pg_statistic` row via `compute_trivial_stats`, measured with `avg_width = 54`. One shape
  where the query beats the exact function: a dropped 500-byte column reads **92** against a **92.42%** rewrite while
  `pgstattuple` reads **6.01**. A never-vacuumed TOAST relation with `relpages = 0` makes a 31 MB table report
  `table_mb = 0.203`. Also measured: three incompatible size bases in one report (a 442,368-byte gap on one fixture),
  the `bloat_data` duplicate-column `ambiguous` error, one `AccessExclusiveLock` on any `pg_table_size`-branch table
  killing the whole statement at `lock_timeout` while the same lock on an estimated-branch table does not, a role with
  `SELECT` on 1 of 26 tables getting a clean-looking one-row report, and 36 ms at 27 tables against 224 ms at 427,
  dominated by `information_schema.columns` rather than `pg_table_size`. Prompt hygiene applied first: four corrections
  offered and accepted, recorded in the page. The scoring variant was derived mechanically from the verbatim statement
  with a byte-identical 4,962-byte CTE prefix, and both published snippets were extracted from the page's own Markdown
  and re-run. 138 citations verified to resolve, sit in range, cite only `raw/postgres-12/`, and contain their labelled
  symbols; 25 `## Contents` anchors resolve and match document order; 8 open questions. `verified_by_agent` set to
  `claude-opus-5-max 2026-08-31T16:02:19Z`; `verified: false` untouched.

- 2026-08-31: **removed a v12 question page**, Proposing and Testing a fillfactor-Corrected
  pgstattuple_approx Metric for Table Heap Bloat in PostgreSQL 12 (unverified), at the user's
  request, together with its `wiki/index.md` and `wiki/v12/index.md` entries, the inbound
  `## Navigation` links on the two surviving v12 `storage-and-vacuum` pages, and the clause that
  described it in the v12 coverage cell above. The one prose reference to it - the heap-and-TOAST
  page's note that bloated heap rows read 1.8 to 4.0 points low - now cites `pgstatapprox.c:97` and
  `bufpage.h#SizeOfPageHeaderData` directly and points at that page's own exact-versus-approximate
  section, so no surviving claim rests on the deleted page. v12 `pgstattuple_approx` coverage now
  runs through [Measuring Heap and TOAST Bloat With pgstattuple_approx in PostgreSQL 12
  (unverified)](v12/questions/storage-and-vacuum/pgstattuple-approx-heap-and-toast-bloat.md), which
  keeps the `fillfactor` reserve derivation, the reserve-subtraction-versus-ratio comparison, and the
  approximate-versus-exact cost split. **No longer filed anywhere in the wiki**: the three-step
  screen/measure/confirm procedure, the seven-point fillfactor sweep (uncorrected 0.44 to 91.02 on
  unbloated tables against corrected 0.02 to 1.79, except 10.16 at `fillfactor = 10`), the
  closed-form residual model matching all seven within 0.05 points, the reloption-lowered-after-load
  case where `VACUUM FULL` grows a table 44.93% and only the unclamped metric reports it (−42.23),
  the 30.08-point unusable-page-tail false positive, the 84.22-point dropped-column blind spot, the
  6.9 ms / 42-read against 484.8 ms / 137,932-read cost comparison on a 1.08 GB table, and the
  catalog-only-estimator scoring. The pin `45b88269a353ad93744772791feb6d01bc7e1e42` and every
  surviving page's citations and verification fields are unchanged.

- 2026-08-31: **new question page, source plus measurements**, [Measuring Heap and TOAST Bloat With
  pgstattuple_approx in PostgreSQL 12
  (unverified)](v12/questions/storage-and-vacuum/pgstattuple-approx-heap-and-toast-bloat.md), pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (12.2, tag `REL_12_2`). The asker asked for one runnable
  statement measuring heap and TOAST bloat with `pgstattuple_approx`, and **v12 does not allow the
  TOAST half**: `pgstattuple_approx` accepts only `RELKIND_RELATION` and `RELKIND_MATVIEW`, so a
  TOAST relation returns `ERROR: "pg_toast_16405" is not a table or materialized view`. The filed
  statement measures the main heap with `pgstattuple_approx`, the TOAST heap with the exact
  `pgstattuple` (which does accept `RELKIND_TOASTVALUE`), labels each row with the function that
  produced it, and hard-codes the TOAST fillfactor at 100 on source grounds - `heap_reloptions()`
  overwrites the parsed value with 100 for `RELKIND_TOASTVALUE`, `toast.fillfactor` is refused as an
  unrecognized parameter, and `toast_save_datum()` reaches `heap_insert()` with a zero `saveFreeSpace`.
  **Tested against `VACUUM FULL` on an isolated 12.2 server over ten fixtures.** The requested
  reserve-subtraction formula is algebraically identical to the rewrite-matching ratio form at
  `fillfactor = 100` (12 of 12 such rows agreed to the digit) and lands −4.02 to +8.98 points from the
  truth there, but **understates by 15.54 points** on a bloated `fillfactor = 70` table (34.46 against
  50.00, ratio form 49.22) because it charges the reserve against the pre-rewrite size. **TOAST free
  space is mostly chunk geometry**: a never-deleted TOAST relation read **19.58% free** while
  `VACUUM FULL` reclaimed **0.00%**, reconciled to the byte from `TOAST_MAX_CHUNK_SIZE` = 1,996
  (measured chunks 1,996/1,996/1,996/412; 6,544 occupied and 1,604 free bytes per page), and a payload
  that is an exact multiple of the chunk size read **0.24%**. Also measured: `f_toastonly` at 200 kB
  heap / 31 MB TOAST with 75.00% of the TOAST reclaimable; the cost split (45 buffer accesses and zero
  heap reads for the all-visible heap branch against 10,006 for a 5,000-page TOAST scan - exactly two
  per page, since the free-space loop re-reads each block - and 51x time / 690x physical reads between
  the two functions on one 27 MB heap); `scanned_percent` truncating to 0 with 1 page of 5,000 scanned;
  10,000 dead TOAST chunks present before any VACUUM because `heap_delete()` calls `toast_delete()` in
  the same transaction; `pg_stat_scan_tables` sufficing for both rows while `SELECT` on the table stays
  denied; and the VACUUM warning in one table - a trailing delete let plain `VACUUM` truncate a TOAST
  relation 16,384,000 -> 8,192,000 bytes, an interior delete of the same row count changed nothing
  until `VACUUM FULL`. Safety behaviour is source-backed and tested: `pgstattuple(0)` raises
  `could not open relation with OID 0`, so the `reltoastrelid <> 0` filter sits below the lateral call;
  `nullif`/`coalesce` make a zero-length relation report `0.00`; and unsupported targets return zero
  rows rather than aborting. The published SQL was extracted mechanically from the page's own Markdown
  and re-run to produce the published output. 136 citations verified to resolve, sit in range, cite
  only `raw/postgres-12/` and contain their labelled symbols; 27 `## Contents` anchors resolve and
  match document order; 8 open questions. `verified_by_agent` set to
  `claude-opus-5-max 2026-08-31T14:13:19Z`; `verified: false` untouched. Sandbox retained at
  `.wiki-runtime/tmp/pta12/`.

- 2026-08-31: **new question page, source plus measurements**, [How Much I/O a VACUUM FULL Performs on
  a Multi-GB, Near-Empty Heap in PostgreSQL 17
  (unverified)](v17/questions/storage-and-vacuum/vacuum-full-io-on-near-empty-heap.md), pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). This is the PostgreSQL 17 counterpart of the
  filed v12 page of the same basename, asked and answered independently on v17 evidence; 17.11 was
  built out of tree from `raw/postgres-17/` and the asker's test was run.
  **The hypothesis holds exactly, and the v17 answer is not the v12 answer.** On four byte-identical
  fixtures - 200,000,000 rows in **884,956 blocks / 7,249,559,552 bytes** at 226 tuples per page,
  99.9% deleted with the physically last rows kept so `VACUUM` could not truncate, then `VACUUM` and
  `VACUUM FREEZE` leaving **all 884,956 pages all-visible and all-frozen** - `VACUUM FULL` read
  **884,956 blocks with 0 buffer hits** and the block layer delivered **7,249,559,552 bytes, the file
  size to the byte**, in 3.02 s. A plain `VACUUM` on the identical heap read **0 blocks** in 3.17 ms,
  skipping 884,955 of 884,956 pages. `pg_stat_io` agreed with `pg_statio_all_tables` to the block in
  the `bulkread` context.
  **The v17-specific result is the syscall count.** Those 884,956 blocks arrived in **55,361 read
  system calls**, 15.985 blocks each, because `b7b0f3f2724` (`REL_17_0`) routed sequential scans
  through the read stream and `210622c60e1` added `io_combine_limit`, defaulting to 128 kB. A
  six-point sweep on a 44,248-block fixture moved the call count **28,179 -> 14,122 -> 7,088 -> 3,586
  -> 1,823 -> 976** across `8kB` -> `256kB` while `heap_blks_read + heap_blks_hit` stayed at
  **exactly 44,248 in all six runs**. The syscall count is tunable; the block count is not.
  **Also measured**: the new heap at **885 blocks / 7,249,920 bytes** (999.95:1); **28 `XLOG/FPI`
  records** carrying 885 full-page images, since `log_newpages` batches 32 per record; WAL collapsing
  **7,353,992 -> 110,008 bytes** at `wal_level = minimal` with all 884,956 reads and 55,361 calls
  unchanged; a warm-cache run identical on every read counter with **`read_bytes = 0`** and 1.20 s
  against 2.99 s; the **zero-row** heap (`vacuum_truncate = off`) reading all 6.75 GB to produce a
  **0-byte** new heap in **three** write calls; an indexed run decomposing to **885,841 = 884,956 +
  885** with `idx_blks_read` +1 and a 4,513,792-byte index rebuilt to the same size; and the old
  relfilenode left at 0 bytes with `.1`-`.6`, `_vm` and `_fsm` already unlinked.
  **Three findings that differ from the older major**, each traced to a commit in this checkout's own
  history: emptied pages keep **zero** line pointers at `pd_lower = 24` (so `pgstattuple` reports
  **99.56%** free) because `PageRepairFragmentation` truncates the array and `nindexes == 0` sends
  `HEAP_PAGE_PRUNE_MARK_UNUSED_NOW` into pruning; `heap_blks_scanned` still reports **0 of 884,956
  for 427 of 434 samples** during the scan but now **ends at exactly 884,956** (`3df51ca8b39`,
  back-patched to `REL_12_6`, so this is a 12.0-12.5 distinction rather than a 12-vs-17 one); and the
  rewrite's writes go through v17's bulk-write facility (`8af25652489`), which hides the new heap's
  extends from `pg_stat_io` and hands the fsync to the checkpointer instead of calling
  `smgrimmedsync`.
  **One documentation conflict and one counter conflict are filed as open questions**:
  `maintenance.sgml` still says a rewrite needs "extra disk space approximately equal to the size of
  the table", which is off by a factor of **0.0001** here (7,249,920 against 7,249,559,552); and
  `pg_stat_io.reads` is documented as a count of read operations but is incremented by the block
  count, reading 884,956 where the backend made 55,361 calls. 343 citations, all verified to resolve,
  sit in range, cite only `raw/postgres-17/` and carry labels consistent with their own line ranges
  (one real error caught: a `PageGetHeapFreeSpace` label pointing at `bufpage.h`'s `PageHeaderData`
  struct); 41 `## Contents` anchors all resolve and match document order; 8 open questions.
  `verified_by_agent` set to `claude-opus-5-max 2026-08-31T13:20:20Z`; `verified: false` untouched. The sandbox was
  deleted afterwards at the asker's instruction, so the fixture SQL is published in the page.

- 2026-08-28: **measured follow-up** on [How Much I/O a VACUUM FULL Performs on a Multi-GB,
  Near-Empty Heap in PostgreSQL 12
  (unverified)](v12/questions/storage-and-vacuum/vacuum-full-io-on-near-empty-heap.md), same pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (12.2, tag `REL_12_2`). The page had been
  **source-only by the asker's original scoping**; the asker then asked for the test to be run, so
  12.2 was built out of tree from `raw/postgres-12/` and the answer now carries measurements.
  **The hypothesis holds exactly.** On the asker's fixture - 200,000,000 rows loaded into
  **884,956 blocks / 7,249,559,552 bytes** at 226 tuples per page, 99.9% deleted with the
  physically last rows kept so `VACUUM` could not truncate, then `VACUUM` and `VACUUM FREEZE`
  leaving **all 884,956 pages all-visible and all-frozen** at unchanged size - `VACUUM FULL` read
  **884,956 blocks with 0 buffer hits** and the block layer delivered **7,249,559,552 bytes, the
  file size to the byte**, in 2.15 s. A plain `VACUUM` on the identical heap read **0 blocks** in
  17 ms, skipping 884,955 frozen pages: the same visibility map that let `VACUUM` read nothing let
  the rewrite read 6.75 GB. **Seven `VACUUM FULL` runs**; the four comparable ones agree
  byte-for-byte on `heap_blks_read` 884,956, `rchar` 7,250,034,354, `syscr` 885,019 and WAL 84,720,
  and `syscr` decomposes as 884,956 heap-block reads of exactly 8192 bytes plus 63 other calls
  carrying the residual 474,802 bytes. A **warm page cache** changed only `read_bytes` (0
  against 7,249,559,552) and the clock (1.25 s against 2.15 s), not one of the 884,956 reads.
  **The extreme case** - the same 6.75 GB heap with `vacuum_truncate = off` and **zero rows** -
  still read all 884,956 blocks and produced a **0-byte** new heap.
  **Also measured**: `pg_waldump` counted **885 `XLOG/FPI` records for the 885 new pages** and
  nothing for the 884,956 read (7,377,944 bytes at `replica` against 84,720 at `minimal`);
  `heap_blks_scanned` reported **0 of 884,956 for 49 of 51 samples** and for **all 94 samples** on
  the rowless heap; the index rebuild read only the new 885-block heap (789 misses + 96 hits) with
  `idx_blks_read` 0; `VACUUM FULL` ran 2.05 s against a cost-delayed
  `VACUUM (DISABLE_PAGE_SKIPPING)` at **57.27 s** over identical bytes; the old relfilenode sat at
  **0 bytes with segments `.1`-`.6` already unlinked** and vanished at `CHECKPOINT`; and every
  emptied page kept **226 of 226 line pointers** (`pd_lower` 928), which is why `pgstattuple`
  reported **88.53%** free rather than ~100%.
  **Two claims corrected.** `heap_blks_scanned` does **not** necessarily end below
  `heap_blks_total` - it ends at the last returned tuple's block plus one, measured at exactly
  884,956 on the fixture whose last block holds live rows and at **0** on the rowless one - and
  the doc's "extra disk space approximately equal to the size of the table" is off by a factor of
  **0.0001** here (7,249,920 bytes against 7,249,559,552). Open questions were rewritten: the
  three that the run settled are gone, and TOAST, unfrozen hint bits, single row width/scale, fast
  local storage, and the deleted sandbox are now named as the remaining gaps. Citations 307 -> 362,
  all re-checked; open questions 6 -> 8. `verified_by_agent` set to
  `claude-opus-5-max 2026-08-28T12:11:54Z`; `verified: false` untouched. The sandbox was deleted
  afterwards at the asker's instruction, so the fixture SQL is published in the page.

- 2026-08-27: **review and first filing** of [How Much I/O a VACUUM FULL Performs on a Multi-GB,
  Near-Empty Heap in PostgreSQL 12
  (unverified)](v12/questions/storage-and-vacuum/vacuum-full-io-on-near-empty-heap.md), pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (12.2, tag `REL_12_2`), corrections made **in place**.
  The page had been drafted but never linked or logged, so `scripts/wiki_lint` was reporting it as
  an orphan; the review completes the bookkeeping and the page is now linked from
  `wiki/index.md` and `wiki/v12/index.md`.
  **Source-only by the asker's scoping, and the review kept that scope**: no 12.2 server was
  built, so every claim rests on `raw/postgres-12/` alone. **All 246 pre-existing citations
  resolved, sat in range, cited only `raw/postgres-12/` and carried labels consistent with their
  own line ranges**; the 25 `## Contents` anchors all resolved and matched document order.
  **Three substantive corrections.** (1) The observability section claimed
  `pg_stat_progress_cluster.heap_blks_scanned` "advances once per block with no skipping" and was
  "the honest number". It is written **once per returned tuple**, inside the copy loop, as
  `heapScan->rs_cblock + 1`, and **nothing squares it up at end of scan** - so on precisely the
  shape this page is about (a multi-GB heap whose pages hold no `LP_NORMAL` line pointers) the
  counter stands still across whole runs of blocks and ends below `heap_blks_total`. The section
  now leads with `pg_statio_all_tables.heap_blks_read` instead. (2) "An empty page yields
  `PageGetMaxOffsetNumber(dp) == 0`" is only true of a page that never held a line pointer: v12's
  `PageRepairFragmentation` carries the comment "It doesn't remove unused line pointers! Please
  don't change this.", so a page emptied by `DELETE` plus `VACUUM` keeps its array at its
  historical high-water mark and `heapgettup` walks it, rejecting each entry on `ItemIdIsNormal`.
  (3) Both published monitoring statements used `SET LOCAL` with no enclosing `BEGIN`, which at
  top level only raises `WARNING: SET LOCAL can only be used in transaction blocks` and leaves the
  query untimed; they are now wrapped in `BEGIN` / `COMMIT`.
  **One arithmetic error**: the worked example's `t_len = 500` row read `MAXALIGN(t_len) + 4` as
  504 instead of **508**; the derived columns do not move, because `floor(8168 / 508)` and
  `floor(8168 / 504)` are both 16. **Two citation ranges were too narrow for their claims** and
  were widened: `md.c#mdunlinkfork` 284-322 -> **284-359**, since the deferred
  `register_unlink_segment` is line 323 and the immediate later-segment unlink loop is 326-359;
  and `bufpage.c#PageGetHeapFreeSpace` 664-695 -> **664-714**, since both `space = 0` returns sit
  at 701 and 710. **Three precision fixes**: writes are `ceil(live bytes / usable page bytes)`
  pages *including* the final partial one rather than plus it, `VacuumCostBalance` accrues only
  while `VacuumCostActive` (so not at the v12 default `vacuum_cost_delay = 0`), and the
  `BAS_BULKREAD` ring does not strictly protect the cache because `StrategyRejectBuffer` empties a
  slot and sends the next allocation to the clock sweep.
  **Six previously uncited claims now carry evidence**: the `XLogIsNeeded()` /
  `RelationNeedsWAL` definitions, the absent free-space-map path in `rewriteheap.c`, the
  index-driven `toast_fetch_datum` chunk scan, the B-tree build's `maintenance_work_mem` sort
  budget, the missing-VM-fork reason the next plain `VACUUM` cannot skip, and
  `XLogHintBitIsNeeded()` behind open question 3. The visibility-map and prefetch absence claims
  now also name `heapam_handler.c`, the file that actually holds the scan-and-copy loop. Citations
  246 -> 307; open questions stay at 6, with open question 1 naming two newly identified
  unmeasured quantities. `verified_by_agent` set to `claude-opus-5-max 2026-08-27T21:44:14Z`;
  `verified: false` untouched.

- 2026-08-27: **review** of [A COMMENT-Stored Baseline and Normalized Index Growth for Finding
  GIN Indexes That Need REINDEX CONCURRENTLY in PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-reindex-normalized-growth-comment-baseline.md), same
  pin `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11), with corrections made **in place**.
  The page's sandbox had been deleted the same day it was filed, so 17.11 was **rebuilt a second
  time** out of tree from `raw/postgres-17/` with the same `configure` line and cluster settings.
  **All 137 citations resolve, sit in range, cite only `raw/postgres-17/` and carry labels
  consistent with their own line ranges**; the 30 `## Contents` anchors all resolve, cover every
  heading and match document order. The extractor still finds **exactly three** `wiki_gin`
  blocks at **41 / 18 / 76 lines**, byte-identical to the ones executed, and **all three run
  verbatim**.
  **The fixture SQL was never published, so no absolute byte size could be reproduced** - a
  re-derived 600,000-row table built a 14,737,408-byte index against the filed 16,474,112, and
  everything downstream moved with it. **Every fixture-independent claim reproduced**: the
  9-field capture with `bac` 0 / `bti` 600000 / `btu` 0 / `btd` 0 and the two-line human comment
  preserved byte for byte, the nine-field read round-trip, `churn_ratio` **2.0000**,
  `heap_tuple_ratio` **1.0000**, the `candidate: disproportionate growth` verdict, `btu`
  **1200000** after re-capture, the `insufficient churn: not evaluated` re-evaluation, and
  exactly one payload after re-capture. The prediction identity held at **60.90 predicted
  against 60.88 measured** - 0.02 rather than 0.00 because the rebuild returned one page larger
  than the baseline, the same one-page effect the filed run recorded on c10. Reproduced
  **exactly**: the `reltuples` swing **1000000 / 200000 / 100000 / 500000**, and the entire
  `fastupdate` pairing - **310** pending pages, **515** FSM free pages, **4,218,880 bytes** of
  growth on `fastupdate = on` and **not one byte** on `fastupdate = off` - because those three
  figures are set by `gin_pending_list_limit`, which is exactly the page's claim about them.
  Six edge cases returned byte-identical output including both refusal strings, the single
  `ShareUpdateExclusiveLock` on the index and none on the table, and `REINDEX CONCURRENTLY`
  moving the comment to a new index OID with a stale `bfn`. No `RelationTruncate` call exists
  anywhere under `src/backend/access/gin/`, while `spgvacuum.c:896` has one.
  **Three findings.** The comment-size arithmetic was wrong and self-contradictory: with the
  9-byte tag, a newline and a 56-byte human note, a 133-byte payload makes a **142**-byte
  comment bare and **199** with the note, not the filed 143 and 192 - and 192 contradicted the
  page's own E1 row of 196. `VACUUM` is only a **conditional** writer of an index's
  `reltuples`: `vac_cleanup_one_index` merely produces the count, the `pg_class` write lives in
  `update_relstats_all_indexes`, and it is skipped whenever `estimated_count` is set, which
  happens whenever the heap scan skipped a page - measured as a second plain `VACUUM` leaving
  **500000** where `VACUUM (DISABLE_PAGE_SKIPPING)` wrote **100000**, a fifth value the index
  can hold and a further argument for the brief's table-`reltuples` denominator. And one
  `maintenance_work_mem` row is internally inconsistent by exactly one page (13,350 total
  against 3,350 + 10,000 + 1) against the invariant
  `total = entry + data + pending + 1`, which held with residual 0 on six fresh builds measured
  now in both the all-inline and posting-tree regimes and at both 64MB and 256MB, and which
  every other table on the page satisfies; filed as open question 14 because the original
  fixture no longer exists to settle which figure is off. Open questions 13 -> 14.
  `verified_by_agent` refreshed to `claude-opus-5-max 2026-08-27T15:31:08Z`. The review sandbox
  `.wiki-runtime/tmp/ginrev/` was deleted afterwards, so `.wiki-runtime` is back to the venv
  alone and a third rebuild would be needed to re-measure.

- 2026-08-27: **new v17 question** - [A COMMENT-Stored Baseline and Normalized Index Growth for
  Finding GIN Indexes That Need REINDEX CONCURRENTLY in PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-reindex-normalized-growth-comment-baseline.md), same pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). A designed and measured GIN-only
  `REINDEX` shortlist whose whole persistent state is a **133-byte `@ginbase:` payload** in the
  index's own `COMMENT ON INDEX` - nine flat fields, no table, no extension - scored on a
  **12-cell matrix run three times** with `REINDEX INDEX` as ground truth on a 17.11 server built
  from this pin. **Right on 10 of 12 cells**; `1 - 1/normalized_index_growth` predicted the
  reclaimed fraction to within **0.05 points on 5 of the 9 evaluable cells** (83.82/83.82,
  54.63/54.63, 57.18/57.14, 11.91/11.95, 0.00/0.00) and runs 2 and 3 were byte-identical. The
  three published statements were then **extracted from the page and re-run verbatim** in a fourth
  database on a differently named index: the full capture -> churn -> evaluate -> rebuild ->
  re-capture lifecycle worked and the prediction landed at **55.66% against a measured 55.66%**.
  **Four brief premises are corrected on evidence.** The `index size remains >= 75-80% of
  baseline` clause is **vacuous** - no file under `src/backend/access/gin/` calls
  `RelationTruncate`, so `index_size_ratio >= 1` always holds on an un-rebuilt index and the
  shrinkage rule collapses into `normalized >= 2.0`, a strict subset of the growth rule. "Both
  grew 50%, so do nothing" is false: +50% rows grew the index **+120%** (20,594,688 ->
  45,391,872) for `normalized` 1.4694, and `REINDEX` reclaimed **39.51%**. A fresh GIN build is a
  **step function** of row count - 7,495,680 / 13,729,792 / 20,594,688 / 82,329,600 / 82,329,600 /
  246,169,600 bytes at 250k / 500k / 1M / 2M / 4M / 8M rows over one 10,000-key universe,
  quadrupling at the posting-tree conversion (`n_data_pages` 0 -> 10,000) and then flat - which is
  why the same-keys doubling over-predicted 67.65 against 35.33 while the new-keys doubling, whose
  lists stayed inline, hit 11.91 against 11.95. And the blind spot is sized by
  `gin_pending_list_limit`: 150,000 rows added 515 pages (4,218,880 bytes) to a `fastupdate = on`
  index and **nothing at all** to an otherwise identical `fastupdate = off` one, the flushed pages
  went to the FSM and stayed in the file, and `REINDEX` returned both to 16,474,112 - leaving a
  growth sweep reading `normalized` 1.1419 / 1.0049 / 0.8374 against 20.39 / 20.39 / 0.48%
  reclaimable. Two further cautions are measured: the baseline is a function of
  `maintenance_work_mem` (109,371,392 bytes at 64MB against 82,329,600 at 256MB and 1GB, because
  `ginBuildCallback` flushes at that budget), and an `n_mod_since_analyze` staleness veto had to be
  **withdrawn** - `pgstat_report_analyze` zeroes the counter but pending backend counts are applied
  additively afterwards under a 1000 ms `PGSTAT_MIN_INTERVAL` rate limit, so it read 600000 while
  the same `VACUUM (ANALYZE)` had set `reltuples` correctly to 400000; reproduced independently at 1
  of 4 back-to-back `DELETE` + `VACUUM (ANALYZE)` pairs with `n_live_tup` clamped to 0. The
  `analyze_count` veto that replaced it is what caught the one cell whose ratios were silently
  meaningless (60% deleted, no `ANALYZE`, `normalized` 1.0000 over a real 46.66% reclaim). All
  **119 citations resolve, are in range and version-correct**, and checking them found and fixed a
  real error: the entry increment is in `ginHeapTupleBulkInsert`, called once per indexed column by
  `ginBuildCallback`, not in `ginBuildCallback` itself. Thirteen open questions, including that
  partial and multi-column GIN indexes were never tested - where the table `reltuples` the
  heuristic divides by is not the indexed population. `.wiki-runtime` was emptied to the venv alone
  (111M -> 13M) before the work, and the sandbox `.wiki-runtime/tmp/ginorm/` that replaced it was
  **deleted the same day** after filing (8.8 GiB), so no compiled 17.11 install and no harness
  remain: reproduction means rebuilding 17.11 out of tree from `raw/postgres-17/` and re-deriving
  the fixtures from the page's own methodology section, since only the three published statements
  were carried into the page.

- 2026-08-27: **review** of [Reading an Index's Entry Count From the Catalogs, for Every
  Index Type, in PostgreSQL 17
  (unverified)](v17/questions/indexing/index-entry-count-from-catalogs.md), same pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11), with corrections made **in place**.
  The page's own sandbox had lost its data directory, so 17.11 was re-`initdb`'d from the
  surviving exact-pin install and the fixtures were rebuilt in two fresh databases.
  **All 125 distinct citations resolve and carry the claimed text**; three citation
  *labels* disagreed with their own line ranges and were fixed (`pg_class.h:62-70` ->
  `62-69`, `nbtsort.c:585-600` -> `576-600`, twice). The published statement is
  **byte-identical to the tested one** (68 lines, compared line by line).
  **Every measured figure reproduced byte for byte** except the three that cannot:
  14 of 14 exact twice, 15 of 16 at 180,000 rows with the same `-104` partial-BRIN miss,
  580766 / 597901 / 1178667 / 30000 / 150000 / 116 / 12 / 2000 / 150379, the
  522874 / 538110 / 1060984 GIN truths, the 100 / 98 / 198 metapage counts, the
  115-against-116 VACUUM reading on a 3702-block heap with range 115 starting at block
  3680, all seven forgery verdicts, the 999 / 1000 partition leaves, and 20,000,001
  entries reading back as 20000000. The three that moved are now labelled as such: the
  **parallel BRIN count** (a second five-point sweep read 116/221/328/305/326 against
  116/222/325/328/311, and three four-worker builds 326/330/325 against 317/319/328, so
  the figure is bracketed at 305-330 with the on-disk truth 116 in all ten sweep builds),
  the two **sample-derived partial-index `ANALYZE` readings** (140142 / 18444 against the
  filed 139494 / 17736), and wall-clock timestamps, which the page now states as an
  ordering. **Four findings were added**: an empty table's BRIN index reads `1`, because
  the serial build's final `form_and_insert_tuple` has no empty-range guard; every access
  method allocates at least one page at build time (1 btree/GiST/bloom, 2 GIN, 3
  SP-GiST/BRIN, 4 hash), which makes the statement's `zero: no storage yet` branch
  unreachable for a valid non-partitioned index; a non-partial BRIN undercount of **1
  against 8** summaries on an all-dead 256-block heap; and a `ct.relpages = 0` guard that
  silently disables the BRIN bound, measured on a `CREATE TABLE AS` plus `DELETE` table
  holding 256 real blocks. A new verdict census shows eight of nine branches firing and
  only two proving an overwrite - the BRIN bound (3 of 3 after `ANALYZE`) and the GIN
  bound, which needs `indnatts >= 2`. GUC apply scopes were added for every setting the
  page sets. Open questions 8 -> 9. `verified_by_agent` refreshed to
  `claude-opus-5-max 2026-08-27T13:07:45Z`; the recreated data directory was deleted after
  the review, so the exact-pin install remains but the cluster must be re-`initdb`'d again.

- 2026-08-26: **two-major follow-up** on [Measuring Wasted and Reclaimable Bytes in a
  GIN Index With Contrib Extensions on PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md), same pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11), answering "make sure that statement
  runs on v12, and run all tests on v12 and v17" against **two** servers built out of tree
  from this repo's own pins: **12.2** (`server_version_num` 120002) and **17.11**.
  **All four published statements now run on both, after three edits.** `get_raw_page`
  takes `int4` on 12.2 (`f18aa1b2039` widened it to `int8` in `REL_14_0`), so the block
  number needs `::int`; the census needs a `pagesize = 0` page class ahead of the flags
  tests; and the entry-tuple probe needs the same guard on its `'{}'` filter. The FSM
  cross-check and the size bracket run unchanged and derive **8160** on both.
  **The non-cosmetic edit is decisive.** On 12.2 `gin_page_opaque_info` returns a row with
  `flags = {}` for an all-zero page where 17.11 returns a NULL row - the fix
  (`cd4868a5700`, `Backpatch-through: 10`) reached the 12 branch as `5378d55cb2f`, first
  tagged **`REL_12_11`**, after this repo's 12.2 pin. Measured by appending two zeroed
  blocks to an index file: the filed text reports **56 entry pages, 0 new pages and 0 waste
  bytes** on 12.2 against 54 / 2 / 16,384 on 17.11, with the self-check passing, and the
  probe's downlink count reads **41 against 53** (each zero page contributes -6). A
  `dd`-zeroed metapage **aborts the whole multi-index census** on 12.2 where 17.11 returns
  NULLs. The crash route did not reproduce: `-m immediate` mid-insert produced **no** zeroed
  pages on either server.
  **26 of 27 scored fixtures came out byte-identical across the majors**, including all seven
  published ones reproducing every filed figure (17,571,840 / 6,209,536 / 10,117,120 /
  16,384 / 7,356,416 / 7,356,416 / 11,927,552 bytes and 42.42 / 58.05 / 0.00 / 0.00 / 89.09 /
  46.33 / 13.26% reclaimed), with identical tallies: lower bound 24 of 27, upper 25 of 27,
  upper-plus-pending 26 of 27. Identical too: the `f2` lifecycle, the three-VACUUM horizon
  sequence with every page's `prune_xid` equal to the holder's `backend_xmin`, the five flush
  rounds and their FSM readings, the `pg_stat_scan_tables` privilege matrix, both timeout
  cancellations (2007 ms and 1505 / 1504 ms), the standby refusals, and rebuild equivalence
  (`REINDEX` and `REINDEX CONCURRENTLY` both 7,356,416 -> 3,948,544, and both 2,605,056 under
  a 100,000-row insert stream).
  **Two headline claims corrected.** `waste + slack` is **not** an upper bound when the
  dead-key population is large - an 800,000-row `jsonb_path_ops` index with 819,770 dead
  entry tuples read 43.43% against 50.00% reclaimed on 17.11 and 39.03 against 49.99 on
  12.2 - nor when a pending list is live (13.73% against 40.00%, repaired by adding
  `pending_pct`). And a census **does** evict a hot working set once the target exceeds the
  cache: at 8,192 buffers a 9,616-block census took a 1,862-page set from `usagecount` 3 to
  80 resident pages on 17.11 and to 0 on 12.2, while a 16k-block seq scan left it intact.
  **A fresh GIN build's size is a function of `maintenance_work_mem`**: the same index
  rebuilt to 34,611,200 bytes at 64MB and 50,814,976 at 96MB and above - 47% apart, biggest
  budget giving the biggest index - with payload constant near 25.6 MB and all the movement
  in `entry_slack`, because `ginBuildCallback` spends a budget measured by
  `GetMemoryChunkSpace`; 17.11 fits about 7% more per flush than 12.2, which is the only
  reason the 27th fixture differs. **Open question 7 closed**: the round-five entry-tree
  explosion is slack exhaustion, entry slack falling by an almost constant 395 kB a round
  (2,126,732 -> 538,900) with the tree pinned at 572 pages before 255 splits arrive at once.
  Also: 12.2's `pgstatginindex` **answers** for an invalid index where 17.11 refuses
  (`13503eb5905`, `REL_17_0`); 12.2 prints the VACUUM cross-check as one deleted-pages number
  in a `DETAIL` block; and the race-detector ranking depends on the writer, not the version
  (metapage check 23 of 25 under four `fastupdate` writers, size bracket 4 of 25). Open
  questions 10 -> 15. `verified_by_agent` refreshed to
  `claude-opus-5-max 2026-08-26T16:30:12Z`; both sandboxes deleted at the user's instruction.

- 2026-08-26: **open-questions pass** on [Measuring Wasted and Reclaimable Bytes in a
  GIN Index With Contrib Extensions on PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md), same pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11), on the then-retained
  `.wiki-runtime/tmp/ginw2/` sandbox, **deleted the same day** at the user's instruction,
  so re-verification now means rebuilding 17.11 from `raw/postgres-17/` and re-running the
  page's published fixture SQL. Open questions went **11 -> 10: two closed, six
  narrowed, one new**, over fourteen new fixtures. **Reproducibility is now settled.**
  The page's published fixture SQL, re-run unmodified in two freshly created databases,
  returned **every** filed number byte for byte - all seven sizes, every page-class
  count, `entry_slack` and `data_slack` to the byte, the `f2` lifecycle
  (2,195,456 -> 6,209,536 -> 6,209,536 with `pgstatginindex` reading `2 | 490 | 50000`),
  the three-VACUUM `f5` sequence with its B-tree sibling line, and all seven `REINDEX`
  results (42.42 / 58.05 / 0.00 / 0.00 / 89.09 / 46.33 / 13.26%). Only `prune_xid`
  moved, reading 953 against the earlier 791 and 870, exactly as the page predicted.
  **The payload-and-fill model's failure boundary is a straight line.** A five-point
  sweep holding churn volume constant while varying the share of the key population
  replaced gives +0.09 / +12.62 / +25.16 / +37.69 / +50.19% at 0 / 25 / 50 / 75 / 100%,
  increments of +12.53, +12.54, +12.53 and +12.50. **The detection gap closed with a new
  probe**: on GIN entry-leaf pages `(pd_lower - 24) / 4` counts entry tuples, and that
  equals the index's key population exactly - 50,028 against 50,028 distinct lexemes, 32
  against 32 tags, and 53 against 50 tags plus GIN's three null categories. It separates
  the two churn shapes at **50,028 dead entry tuples against 1**. Correcting the model
  still fails, because dead tuples are smaller than live ones (16 bytes against 32), so
  subtracting at the average over-corrects by -7.5% to -36.8%; the two estimates only
  bracket the truth. **A second lower-bound violation was constructed and found**:
  `fh2_gin`, grown entirely through the pending list, reads 21.66% dead pages against
  19.25% reclaimed. The bound turns out to be an identity - `waste <= reclaimed` exactly
  when the aged in-use core is at least as big as its own rebuild - and the density form
  of that test predicted the direction on 3 of 3 new fixtures, including a six-block near
  miss. **Flush growth has a mechanism.** Over five identical insert-and-flush rounds the
  pending list was built from the FSM's free stock every time (0 free -> the file grew by
  exactly the 736 pending pages; 736 free -> zero growth, four rounds running), and every
  round then reached its flush with 0 free pages, because `RecordPageWithFreeSpace`
  updates only the bottom FSM level while `fsm_search` starts at the root and
  `ginInsertCleanup` vacuums the FSM only at the end - so a flush can never reuse the
  pages it frees. What the merge itself wants is still unpredictable, and not from total
  slack: +194 blocks at 2.33 MB of slack against +0 at 3.20 MB. **A concurrent VACUUM
  defeats every cross-check the page recommends**: 14 censuses of an unchanging
  2,594-block file reported 0 to 2,294 dead pages against a truth of 2,368 - 91% of the
  file - with the self-check, the metapage check and the new size bracket all passing
  every time. Under four writers, though, the size bracket caught the race **13 of 14**
  where the metapage check caught **0 of 14**, so the page's race advice was corrected.
  **`REINDEX CONCURRENTLY` closed**: under the same 100,000-row insert stream both forms
  returned 3,276,800 -> **2,662,400** bytes (1901 ms against 2013 ms), and 1,548,288 with
  no load. **Four more opclasses** (`jsonb_ops`, `text[]` `array_ops`, weighted
  `tsvector`, plus `jsonb_path_ops` at 50k and 800k rows) take the tally to **26 fixtures:
  26 of 26 upper bound, 24 of 26 lower**, and the 16x scale check moved the model error by
  0.42 points, retiring scale as a suspect. **The eviction conclusion is corrected**: at
  16,384 buffers a 26,195-block census left a hot 3,704-page working set *fully resident*
  while destroying a once-read set of the same size, because the clock sweep spends usage
  count, not pages - the hot set went from `usagecount` 5 to 1, and a second census then
  took it. The FSM cross-check no longer hardcodes 8160 either; it derives
  `MaxFSMRequestSize` from `pg_control_init()`, which returned 8160 and matched the
  largest `avail` over 3,478 free GIN pages. `verified_by_agent` refreshed to
  `claude-opus-5-max 2026-08-26T15:02:41Z`; the sandbox is retained.

- 2026-08-26: **follow-up measurements** on [Measuring Wasted and Reclaimable Bytes in a
  GIN Index With Contrib Extensions on PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md), same pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11), closing **eight of the page's
  thirteen open questions** on the sandbox the review had rebuilt. Nine new published
  fixtures (`f8`-`f16`) plus `pg_trgm`, `btree_gin` and `pg_buffercache` from the same
  tree. **A held `REPEATABLE READ` snapshot pins recyclability indefinitely**: 768 deleted
  pages stayed `0 reusable` across two extra VACUUMs and six xids, then became reusable on
  the very next VACUUM after the snapshot was terminated **with no new xids**, with
  `prune_xid = 870` equal to the holder's `backend_xmin` — so the shared horizon, not xid
  consumption, is the gate. **The census's self-check cannot detect a concurrent writer**:
  over 25 censuses of a 1,000,000-row index under an insert-and-flush loop,
  `census_total_pages = blocks` held 25 of 25 while `pending_pages` disagreed with
  `meta_pending_pages` in 19 of 25 and the block count went stale by up to 664 blocks.
  **Autoanalyze alone flushed a 491-page pending list in under 10 s** (`autovacuum` is
  `PGC_SIGHUP`, so a reload sufficed), growing the file 836 -> 958 blocks and moving the
  waste reading to 51.25% with no user action. **`REINDEX CONCURRENTLY` returned the
  identical byte count** as plain `REINDEX` on the same recipe (3,948,544), in 379 ms
  against 151 ms. **Five more opclasses and shapes** (`jsonb_path_ops`, `gin_trgm_ops`,
  `btree_gin`, multicolumn, partial) took the bound totals to **12 of 12 upper, 11 of 12
  lower**, with `btree_gin` missing the lower bound by only 0.13 points, and fresh-build
  fill ranging 51.30-72.11% across opclasses. The payload-and-fill model's failure mode
  **reproduced independently** at +18.12% on the multicolumn fixture whose churn replaced
  both key columns, against +0.00% to +1.49% on the four that did not. **Real all-zero
  pages were produced**, 4 and 7 of them, by killing the server mid-insert with
  `-m immediate`. And **eviction was measured**: at 8,192 buffers a 6,665-block census
  left all 6,665 pages resident where a 4,092-block seq scan left 98 (the `BAS_BULKREAD`
  ring), then lost 2,942 of them to the next four censuses. Open questions went 13 -> 11.
  `verified_by_agent` refreshed to `claude-opus-5-max 2026-08-26T14:01:59Z`.

- 2026-08-26: **reviewed** [Measuring Wasted and Reclaimable Bytes in a GIN Index With
  Contrib Extensions on PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md) on unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11), with corrections made in place. The
  page's sandbox had been deleted and its fixtures were never published, so 17.11 was
  rebuilt from `raw/postgres-17/` by a VPATH build (leaving the evidence tree untouched),
  the fixtures were reconstructed and are **now printed in the page as SQL**, and every
  measurement was re-run. **All 119 source citations re-read: zero broken**, plus the three
  absence claims (no `RelationTruncate`/`smgrtruncate` under `src/backend/access/gin/`,
  `pages_deleted` incremented in exactly two places, amcheck shipping only the two B-tree
  checks and `verify_heapam`). **Three fixtures reproduced the filed figures byte for
  byte** — the empty index (16,384 / 2 blocks / 8,160 slack), the mass-deleted posting-tree
  index (7,356,416 bytes, 1 / 96 / 32 / 768 pages, 85.52% waste, 9.70% slack, `REINDEX` to
  802,816) and its half-emptied twin (51.34% slack, `REINDEX` to 3,948,544) — as did the
  whole three-VACUUM horizon sequence and the B-tree sibling line beside it, which
  identifies the reconstruction as faithful and the first run's "32 hot keys" as 32 keys per
  row. **Both headline conclusions survive**: over seven fixtures `waste + slack` bounded
  the reclaimed bytes from above 7 of 7, and `waste` alone was not a lower bound in 1 of 7
  (64.64% dead against 58.05% reclaimed, a 268-block core rebuilding to 318). **One filed
  claim did not reproduce**: the pending-list flush left the file size unchanged at
  6,209,536 bytes rather than growing it by one block, so the page now gives the mechanism
  and files the unpredictability as an open question. **A new failure mode was found** in
  the payload-and-fill model, +19.94% on a churn that replaces the key population against
  +0.07% on one that does not, because GIN's entry tree never deletes a tuple and the census
  counts dead entry tuples as payload; a seventh fixture was added to isolate it. Three
  previously source-only claims are now measured: dead-page reuse (491 dead pages absorbed a
  50k-row pending list for +26 blocks), `ginvacuumcleanup` counting not-yet-recyclable
  deleted pages as data pages (`meta_data_pages 77` against 63 live data pages), and the
  recovery refusals on a real physical standby, where `gin_clean_pending_list` and `VACUUM`
  are both refused while the census functions answer. Two source-side notes were added:
  `freespace.c`'s own comment illustrates `MaxFSMRequestSize` as 8164, a value the macro
  cannot produce, and the `pd_lower` claim now cites `GinDataPageSetDataSize` itself. Every
  refusal, privilege and timeout row reproduced (2001.272 ms and 1500.477 ms against the
  filed 2000.846 / 1500.252), `census_total_pages = blocks` held on all 8 indexes, and two
  consecutive runs were byte-identical. Open questions went from 11 to 13. The page remains
  human-unverified, but `verified_by_agent` is now set
  (`claude-opus-5-max 2026-08-26T13:30:26Z`), since every claim it makes is either re-read
  in the pinned source or measured on the rebuilt server. New sandbox
  `.wiki-runtime/tmp/ginw2/` was retained at the time, but **no longer exists** — it was
  deleted on 2026-08-26 at the user's instruction.

- 2026-08-25: filed [Measuring Wasted and Reclaimable Bytes in a GIN Index With Contrib
  Extensions on PostgreSQL 17
  (unverified)](v17/questions/indexing/gin-index-wasted-space-contrib.md) on unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11): a `pageinspect` page census, because
  no single contrib function can measure GIN waste — `pgstattuple` refuses GIN outright and
  `pgstatginindex` reads only three metapage fields, returning `0 / 0` for an index whose
  file was 65% dead pages. **Two premises of the request are corrected on evidence.** A free
  index page reads **8160** from `pg_freespace`, never 8191: `RecordFreeIndexPage` does
  record `BLCKSZ - 1`, but the FSM keeps one byte per page and category 255 converts back to
  `MaxFSMRequestSize` = `MaxHeapTupleSize`; the measured maximum `avail` over every GIN index
  was 8160. And GIN's `pages_deleted` is a per-run counter, not a census — one VACUUM
  reported `0 currently deleted, 768 reusable` for the GIN index beside `520 currently
  deleted` for the B-tree on the same table. **Scored against `REINDEX INDEX` on an isolated
  17.11 server over six ~200k-row fixtures**, `whole_page_waste + slack` bounded the
  reclaimed bytes from above in 6 of 6 cases, but `whole_page_waste` alone is **not** a lower
  bound: one index held **65.49% dead pages while `REINDEX` returned 50.07%**, because
  `entrySplitPage` halves entry pages, so a fresh build is only ~60% full and that index's
  517-block in-use core rebuilt to 748 blocks — 44.7% larger. **Entry-page slack is growth
  room, not waste**: the untouched control reads 38.88% slack and reclaims 0 bytes, and
  50,000 rows' worth of pending entries were absorbed into existing pages for +1 block (and,
  on a freshly rebuilt index, for zero growth). Posting-tree slack does track the truth
  (51.34% measured against 46.33% reclaimed). The four-state pending-list lifecycle is filed
  byte-exactly: 4,227,072 -> 12,263,424 (981 pending pages) -> 12,271,616 after
  `gin_clean_pending_list()`, which **grew the file by one block** and converted 65.5% of it
  into dead pages, -> 6,127,616 after `REINDEX`, with `pgstatginindex` reading `0 / 0` in
  three of the four states. Posting-tree deletions are the opposite of pending flushes:
  because `GinPageIsRecyclable` consults the most conservative shared horizon, 768 deleted
  pages stayed **0 reusable across two VACUUMs** on an idle cluster and only became reusable
  after three transaction ids were consumed, while the census saw them the whole time. Also
  documented and measured: the superuser-only raw-page functions against the
  `pg_stat_scan_tables` grant, `gin_clean_pending_list`'s ownership check, invalid /
  partitioned / other-session-temp behaviour including `pg_freespace` answering where the
  other two refuse, the absence of any GIN verifier in v17 contrib amcheck, one buffer read
  per block with **no** `BAS_BULKREAD` ring, and cancellations at 2000.846 ms
  (`lock_timeout`) and 1500.252 ms (`statement_timeout`). Eleven open questions, chief among
  them that no fixture produced an all-zero page, that `ginVersion <> 2` is untestable on
  v17, and that the payload-and-fill model that predicted every rebuild size within 3.07%
  takes its fill fraction from the rebuild it predicts. At filing the page was
  human-unverified and agent-unverified. Its sandbox `.wiki-runtime/tmp/ginw/` **no longer exists** — it was gone
  by the time the 2026-08-26 review looked, which is why that review rebuilt the server and
  republished the fixtures; the 8.3 GB `.wiki-runtime/tmp/idxm/` sandbox behind the
  non-B-tree inflation page was deleted first at the user's instruction, and that page's two
  "artifacts under" pointers were corrected to say so.

- 2026-08-25: **re-ran every test** on [Detecting Inflated Non-B-Tree Indexes From
  Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17
  (unverified)](v17/questions/indexing/non-btree-index-inflation-comment-baseline.md),
  on unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11), which closes the
  gap the review earlier the same day left open. The 13-cell matrix ran three more times
  (runs 5, 6 and 7, about ten minutes each) plus the six original probes, the 13 review
  probes and one new probe, all scored by the statement the page publishes rather than
  the harness's copy. **The heuristic came out unchanged and the physical measurements
  are exactly reproducible**: all 13 `(B, post-churn, C, R)` quadruples in runs 5-7 are
  byte-identical to filed run 4 and therefore to runs 2 and 3 — six runs, two days, one
  server restart — as are all 13 `reclaimed_bytes`, `reclaimed_pct` and
  **recommendations**, which is also the direct proof that the new access-method guard is
  inert on matrix data. The `ANALYZE` gate held in all 78 pre-`VACUUM` evaluations, with
  `c05_gin_pending`'s pre-`VACUUM` 1.372 identical every time. **Nine of the 13
  `size_inflation` figures are bit-identical across all six runs**; the four that drift
  are exactly the cells whose population term is an `ANALYZE` sample, by at most 2.6%
  (`c08_spgist_prefix` 7.228-7.419), so the two figures corrected earlier that day are
  now given as ranges instead: `pf_shift` read 8.976-9.152 against a true 9.00x, and
  `c10`'s churn ratio 5.31-5.48. Every probe reproduced, **including one that reproduced
  its own bug**: the `reltuples` probe again failed with `VACUUM cannot run inside a
  transaction block`, which is direct proof the filed third column never came from it,
  while the corrected form returned 43 / 200000 / 22 for BRIN and 180000 for the other
  four — the filed table exactly, 43 included. P4's GIN pending list was byte-identical
  (491 pages / 16,654,336 -> 0 / 21,905,408), P3's reset block identical, P2's filenode
  progression identical in shape, and P1's comment came to 340/243 where the filed
  capture is 309/212 — a difference of exactly 31 bytes both times, the length of the
  `dbr` key, which closes that figure arithmetically. Two corrections: the invalid-index
  arm was demonstrated on a *B-tree*, which the guard now pre-empts, so it was re-tested
  on an invalid **hash** index left by a divide-by-zero `CREATE INDEX CONCURRENTLY` and
  does report `skip: index not valid`; and a parallel BRIN build's `reltuples` is not
  reproducible at all — eight observations of the default build span 43 to 46 and the
  four-worker build gave 102 then 90, while the serial build wrote 23 both days. Open
  questions were rewritten to 15, dropping the now-answered "matrix not re-run" and
  adding one-cluster scope, guard precedence, parallel-build non-determinism and the one
  aside (a single hot key at 1 row per 90 seconds) that was not reproduced. The page
  remains human-unverified and agent-unverified.

- 2026-08-25: **reviewed** [Detecting Inflated Non-B-Tree Indexes From Catalogs and a
  COMMENT-Stored Baseline in PostgreSQL 17
  (unverified)](v17/questions/indexing/non-btree-index-inflation-comment-baseline.md)
  on unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). The page's
  measurement sandbox survived an unrelated cleanup, so the review re-read the 57 source
  ranges the page cited beforehand, re-derived every filed number from the harness's own CSVs, and
  restarted the same 17.11 cluster with all 13 fixtures intact rather than rebuilding.
  **Six corrections.** Three figures were run-3 values sitting in a run-4 table
  (`pf_shift` 9.024 -> 9.124, 0.180 -> 0.178, churn ratio 5.468 -> 5.418); no verdict
  moves. **Two "measured" claims had no recorded evidence and both re-measure
  correctly**: the `reltuples` progression, whose probe had run `DELETE ...; VACUUM ...`
  in one `psql -c` and so aborted with `VACUUM cannot run inside a transaction block`
  and rolled the `DELETE` back (re-run: 180000 for hash/GIN/GiST/SP-GiST and 22 for
  BRIN, exactly as filed), and the statistics-reset output block, whose recorded probe
  predated the final statement (re-run with the filed text: reproduces character for
  character). **The BRIN parallel over-count mechanism was wrong**: the merge does not
  "increment per merged range" — each participant counts its own *partial* summaries,
  the leader adopts the sum, and the union that follows inserts with `brin_doinsert`
  without recounting, so the number is (participant, range) pairs; the same 23-range
  index now reads **23 serial, 44-45 default, 102 with four workers**, which also
  explains the filed 348 on a 70-range index as five participants times seventy.
  **`brin_summarize_range()` had never actually been run** — the filed table measured
  `brin_summarize_new_values()` — and 318 explicit `brin_desummarize_range()` plus 318
  `brin_summarize_range()` calls reproduce it identically: 114688 -> 114688 -> 196608,
  with `REINDEX` returning 114688. **Two captures are byte-identical only inside one
  clock second** (`ts` moves), and the filed 309/212-byte comment grows to **340/243**
  once `dbr` is present. **One statement change**: a 3x-bloated B-tree scored `none`,
  because the threshold table has no `btree` row and every NULL comparison fell to
  `ELSE`, so a `WHEN t.amname IS NULL THEN 'unsupported access method'` arm was added
  and proven inert — over all 19 baselined indexes the filed and amended texts differ
  on **exactly 2 rows, both B-tree**, with all 13 cells byte-identical, and the page's
  published block re-run verbatim matches the tested text on all 19. Everything else
  held: runs 2, 3 and 4 do carry identical (B, post-churn, C, R) quadruples on all 13
  cells, run 1 differs on exactly the two cells named defective, all 13 published cell
  scripts match the scripts that ran, and every kB in the results table is the recorded
  byte count over 1024. Open questions grew from 11 to 14. The page remains
  human-unverified and agent-unverified.

- 2026-08-24: filed [Detecting Inflated Non-B-Tree Indexes From Catalogs and a
  COMMENT-Stored Baseline in PostgreSQL 17
  (unverified)](v17/questions/indexing/non-btree-index-inflation-comment-baseline.md)
  on unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11): a
  `REINDEX`-candidate heuristic for HASH, GIN, GiST, SP-GiST and BRIN whose only
  persistent store is an `@idxmaint:` JSON payload in the index's own comment. It
  predicts the size of a *fresh rebuild for the current logical population* instead of
  comparing current size to baseline size, with a per-AM population unit: indexed
  tuples for hash/GiST/SP-GiST, tuples x `avg_width` for GIN, and
  `ceil(table relpages / pages_per_range)` for BRIN. **Validated on an isolated 17.11
  server over a 13-cell matrix with `REINDEX INDEX` as ground truth**: the 7 flagged
  candidates reclaimed 37.7-85.7%, the four controls were correctly left alone, and
  `1 - 1/size_inflation` predicted the actual reclaimed fraction **to 0.0 points on 7
  of 13 cells and within 2.5 points on 12 of 13**. The whole matrix ran three times
  and produced **identical (B, post-churn, C, R) quadruples on all 13 cells**; only
  the inflation figures drift, by 1-2%, because the population term comes from an
  `ANALYZE` sample. Three catalog facts drive the design: an index's `reltuples` means
  the AM's own entry count after `CREATE INDEX`, the *table's* row estimate after
  `ANALYZE` (`tupleFract` is initialised to 1.0 and `compute_index_stats` skips plain
  indexes) and the AM's `num_index_tuples` after `VACUUM` - measured as 300000 /
  200000 / 180000 for GIN and 43 / 200000 / 22 for BRIN, so the baseline is only valid
  if captured after `ANALYZE`; **no per-table statistics reset timestamp exists in
  v17**, so a reset is detectable only as a stored counter going backwards; and a
  parallel BRIN build writes `reltuples = 348` where the true range count is 70.
  **Two measured results contradict the brief.** `brin_desummarize_range()` followed
  by `brin_summarize_range()` freed nothing and then grew a churned `minmax_multi`
  index by 71%, 114,688 to 196,608 bytes, where `REINDEX` returned it to 114,688; and
  flushing a GIN pending list **grew** the index from 16,654,336 to 21,905,408 bytes,
  so a pre-`VACUUM` GIN reading understates rather than overstates the eventual size.
  Comment preservation is proven end to end: a two-line human comment containing `@`
  and `}` survived capture, re-capture, `REINDEX` and `REINDEX CONCURRENTLY`, the
  latter changing the index OID (16649 -> 16651) while `index_concurrently_swap` moved
  the `pg_description` row with it. Eleven open questions are filed, chief among them
  that **the BRIN arm is unvalidated against any true positive** (both BRIN cells
  reclaimed 0 bytes) and that the multiplicative model has no intercept, which is why
  `c10_brin_minmax` reads 0.209 where the truth is about 1.0. The page is
  human-unverified and agent-unverified.

- 2026-08-24: **removed the `reltuples = 0` guard** from the recommended statement in
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md), on unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11), at the asker's request. `live_rows` is a
  two-arm `CASE` again and every `reltuples` of 0 is priced as an empty index on 12 through 17,
  so **change E is now unconditional**; the `unmeasured: reltuples 0, table has live rows`
  status arm became unreachable and was deleted with it, proven by a third statement text that
  keeps the arm and returns **0 rows from `EXCEPT` in both directions over 52 columns** on both
  servers. Both legs were rebuilt and the whole suite re-scored, and they move in opposite
  directions. On **17.11 the change buys nothing and costs one critical false positive**: 3 of
  118 rows move, two are withheld by change B either way, and fixture 118 — a queue that refilled
  after being measured empty — reports **99.3% waste on a live 1.1 MB index** with `status = ok`
  and an empty `caveats`, which is the exact reading that got the auto-analyze trigger rejected as
  change E's test one follow-up earlier. On **12.2 it is a real trade**: 7 of 103 rows move, the
  drained-queue family reports on that major for the first time (100.0 / 100.0 / 99.6 against
  measured 100.0 / 100.0 / 99.6) and the verdicts go 54 PASS / 5 UNMEASURED / 5 critical to
  **57 / 0 / 7**. A new non-partial fixture prices the majors' difference from source: an index
  rebuilt while its table was empty and then reloaded reads `unmeasured: reltuples unknown` on
  17.11, where `RelationSetNewRelfilenumber` writes the `-1` sentinel, and **100.0% waste on a
  dense 21 MB index** on 12.2, where it writes 0. Timing is unchanged on both (43.4-51.3 against
  43.5-53.1 ms on 17.11). Both servers are the ones the previous follow-up kept, restarted with a
  fresh database each, and the rebuild's fidelity is filed: 119 of 119 identical pre-rebuild block
  counts against the earlier run, 118 of 119 after it, and a fixture defect found in passing
  (`p75` deletes 100% of its subset where its comment says 90%). Eight open questions record the
  gaps, including that no observation exists of how often a stale zero occurs outside a fixture.
  The page remains human-unverified and agent-unverified.

- 2026-08-24: added **mandatory test 113 and change E** to [Testing the PostgreSQL 12
  Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md), on unchanged
  pin `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). The new mandatory test is a
  drained job queue — 1,000,000 rows inserted as `state = 'pending'`, a partial index
  `WHERE state = 'pending'`, then every row updated to `'done'` — and **the recommended
  statement failed it in all three states** on an index a `REINDEX` takes from 2745 blocks
  to 1. The arithmetic was never wrong: `expected_blocks` was already 1, and a guard
  written for the majors where `reltuples = 0` was ambiguous replaced the answer with
  `unmeasured: reltuples 0, table has live rows`. **Change E** is two lines that let the
  guard stand down when the zero is provably current — server 14 or later, and
  `n_mod_since_analyze = 0` — and the `VACUUM + ANALYZE` and `ANALYZE`-only states now read
  **100.0% against a measured 100.0%**. It is the first lettered change on the page that
  widens the output rather than narrowing it, so both directions were priced on servers.
  The threshold is deliberately **not** change B's auto-analyze trigger: with the trigger
  substituted, a queue that refills after being measured empty reports **99.3% waste on a
  1.1 MB index that is entirely live**, `status = ok` and no caveat. Change E's own cost is
  one critical false positive, when an `ANALYZE` sample misses the whole predicate subset —
  87.5% on a live 8-block index, reproduced in **8 of 10** consecutive `ANALYZE`s at
  `default_statistics_target = 1`. The drained-but-unanalysed state stays withheld by change
  B, because no catalog fact distinguishes it from a healthy index and a `VACUUM` alone does
  not lift it; one `ANALYZE` does. Regression evidence is an `EXCEPT` in both directions over
  a rebuilt 119-index suite — the page's own runnable deduplication-gate harness verbatim,
  a shape rebuild of partial requirements 18-91, and the 92-112 controls — which moves
  **exactly 4 rows, all inside that one branch**, with verdicts going 50 PASS / 2 critical
  false positives to 52 / 3. Timing is unchanged (58.0-68.4 ms filed against 57.4-65.1 ms
  amended over six interleaved pairs). Both legs ran on **newly initialised** 17.11 and 12.2
  clusters built for this run, because the earlier sandbox was deleted on 2026-08-24; on
  12.2 the version gate holds even though the counter reads 0 there, so both texts return
  the identical `unmeasured` row and `EXCEPT` returns 0 rows either way. Five open questions
  record the gaps, including that the 18-112 fixtures are shape rebuilds rather than the
  filed scripts, that the false positive's size bound is derived rather than measured, and
  that majors 13 through 16 were not run. The page remains human-unverified and
  agent-unverified.

- 2026-08-23: removed the v17 question page Calibrating a COMMENT-Stored
  Bytes-per-Table-Tuple REINDEX Threshold for Every Non-B-Tree Index in
  PostgreSQL 17 (unverified) at the user's request. Removed its entries from the
  root index and v17 landing page, and removed the matching 132-cell
  re-measurement clause from the v17 coverage cell. No surviving v17 content page
  linked to it. Historical links in this page and `wiki/log.md` now name the page
  as plain text so they do not point to a deleted file. The PostgreSQL 12 page of
  the same basename remains in coverage. The v17 pin and every surviving page's
  source citations and verification fields are unchanged.

- 2026-08-20: **rebased every wasted-space calculation on the index fillfactor** in
  [B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17
  (unverified)](v17/questions/indexing/btree-bloat-with-pgstatindex.md), on unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). The leaf term is now measured
  against the same build-code target density the rebuild estimate uses —
  `(leaf_capacity - BLCKSZ * (100 - fillfactor) / 100) / leaf_capacity`, 89.95% at
  8192/90, not the literal 90.00% — clamped at zero, with empty and deleted pages still
  counted in full; the pair is renamed `wasted_vs_fillfactor` / `wasted_ff_pct` so no
  archived output is silently reinterpreted. **A fresh index now reports 0.0 at any
  fillfactor**, where the filed text read 89.6% on a `fillfactor = 10` index and 9.8% on a
  healthy default one. Four edits, 122 lines to 126, still 14 output columns, `notes`
  untouched. **Both retained clusters reproduced their filed output byte for byte before
  anything was compared** — no fixture rebuild was needed this time — and then showed that
  only those two fields moved: the 12 untouched presentation fields identical (2,109 and
  2,180 bytes), 28 internal columns either way with `wasted_space` swapped one-for-one for
  `wasted_vs_fillfactor`, **0 rows from `EXCEPT` in both directions over the 27 shared
  columns across 214 and 220 indexes**, 24 of 27 rows still byte-identical across the two
  servers, and 0 negative and 0 increased values anywhere. Cost is unchanged: identical
  plan shape and **identical total buffers, 108,021 on 17.11 and 108,327 on 12.2**. Ground
  truth is a rebuild: after `REINDEX INDEX` the column is exactly 0 for 81 of 97 and 76 of
  96 scored indexes, ≤ 0.1% for 87 and 85, and **≤ 0.4% for every index the report actually
  prints**; the worst residual anywhere is 44.6% on a one-row index that cannot fill a page,
  which the 1 MB prefilter excludes and which the old baseline read even worse (49.6%). For
  in-page waste the new column is `(leaf_capacity - target_free) / block_size` of
  `est_reclaimable` — **0.8951 predicted at 8192/90, 0.8868-0.8921 measured**, against
  `1.0001` where the waste is whole dead pages. Four fixtures bloated at fillfactors
  100/50/10 were added because every previous fixture carrying real waste had the default
  90; they confirm the ratio to four decimals on both servers and expose the consequence of
  the change: **`i_ff10_del90` is 89.9% reclaimable and reports 8.3% wasted**, because at
  fillfactor 10 nine tenths of the file is free space by instruction. Those fixtures also
  found the reclaim estimate's first vacuumed miss over one point (`87.1` against `89.9`),
  attributed to per-page high-key overhead that `avg_leaf_density` counts as payload. Five
  open questions were added or rewritten. The page remains human-unverified and
  agent-unverified.

- 2026-08-20: **removed the threshold and the verdict column** from the statement in
  [B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17
  (unverified)](v17/questions/indexing/btree-bloat-with-pgstatindex.md), on unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). The `20::numeric AS alert_pct`
  parameter, its `p.alert_pct` pass-through and the `CASE ... THEN 'rebuild candidate'
  ELSE 'ok' END AS status` column are gone, so the report **measures and estimates
  without judging**: 122 lines instead of 125, 14 output columns instead of 15, `notes`
  untouched. **Both retained clusters were restarted and their fixtures rebuilt first**,
  because the accuracy pass ends by rebuilding every index it scores and that state no
  longer reproduces the report; after the rebuild the filed text returned the archived
  17.11 table character for character and the 12.2 one as the same 27 rows with two tied
  rows swapped, which is how the missing `ORDER BY` tie-break surfaced. Identity is
  measured two ways on both servers: the amended output equals the filed output with
  field 14 cut, byte for byte (2,448 and 2,531 bytes), and one view per text over the
  internal `final` stage exposes **29 columns against 28 with `alert_pct` the only loss**
  and **0 rows from `EXCEPT` in both directions over the 28 shared columns, across 214
  and 220 indexes**. Cost is unchanged (4 `CTE Scan` nodes either way; 136.3 against
  135.7 ms on 17.11 and 134.7 against 127.9 ms on 12.2). The 15 rows per server that the
  old column called `rebuild candidate` are the first 15 rows of the amended output on
  this suite, but the sort is on reclaimable bytes while the label was on percent, so
  that is a coincidence rather than a rule. Three open questions were added or rewritten,
  including that no replacement alerting rule was measured. The page remains
  human-unverified and agent-unverified.

- 2026-08-20: filed [B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12
  and 17 (unverified)](v17/questions/indexing/btree-bloat-with-pgstatindex.md) against
  unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). **One statement, one
  measurement function.** `pgstatindex` supplies every number; `pg_class`, `pg_index`,
  `pg_am`, `pg_namespace` and a `pg_relation_size` cost prefilter only choose and label
  indexes. It reports **two different percentages on purpose**: `wasted_pct`, free bytes in
  live leaf pages plus every empty and deleted page measured against perfect packing, and
  `est_reclaimable_pct`, the same file measured against a rebuild at its own fillfactor.
  The rebuild target is taken from the build code rather than from the reloption — a sorted
  build closes a leaf when free space falls below `BLCKSZ * (100 - fillfactor) / 100`, so at
  8192/90 the reachable density is 89.95%, not 90% — which makes the estimate conservative
  by construction. The two readings disagree loudly and correctly: a fresh `fillfactor = 10`
  index reads **89.6% wasted and −0.5% reclaimable**, while an index whose leaves are a
  textbook 89.94% dense is **69.9% reclaimable** because 1,918 of its pages are empty or
  deleted. **Every candidate filter is there because `pgstatindex` raises on that shape and
  one raised call aborts the whole report**: the five non-B-tree access methods and
  partitioned indexes (`relation "..." is not a btree index`), another session's temp index
  (a 4.4 MB one moved the candidate count 27 -> 28 on 17.11), a stale OID (`could not open
  relation with OID ...`), and **the majors' single behavioural difference — an invalid
  index, which 17.11 refuses with `index "..." is not valid` (commit `13503eb5905`, earliest
  containing tag `REL_17_0` in this checkout) while 12.2 returns a row for it**. **Scored
  against `REINDEX INDEX` on newly initialised isolated 12.2 and 17.11 servers** over one
  shared 24-shape fixture script plus one 17-only deduplication fixture: **91 of 94 and 89
  of 93 scored indexes within 1.0 point**, 92 and 90 within 2.0, the identical `+1.7` worst
  over-estimate on both (a 456 kB TOAST primary key; every other row over-estimates by at
  most `+0.1`), and **24 of the report's rows byte-identical across the two servers** — the
  three that differ are the two duplicate-key indexes (21 MB against 6800 kB, 20 MB against
  6368 kB: deduplication changes the input, not the arithmetic) and a non-deterministic
  churn fixture. Three under-estimates are documented rather than hidden: entries deleted
  but not vacuumed (`−0.1%` reported against 89.9% actual, on both servers), an index with
  `deduplicate_items = off` whose rebuild would deduplicate (`−0.3%` against 69.1%, v13+
  only), and 400-byte keys (`69.9%` against 75.0%, because wide tuples close a page fuller
  than the model's bound). Also measured on both: `index_size` equal to `pg_relation_size`
  for **218 of 218 and 212 of 212** candidates; `NaN` density on an index with no leaf pages,
  and `NaN > 20` true for both `float8` and `numeric`, with all 62 and 59 `NaN` rows scoring
  exactly 0.0 through the statement's guard; leaf capacity implied at **8151.6 and 8152.1**
  from two known-content pages against the hard-coded `8192 - 24 - 16`; a `pg_stat_scan_tables`
  member reading every row while `pgstatindex('bl.i_del90')` by name fails for the same role
  with `permission denied for schema bl`, which is why the statement passes an OID; ~830 MB
  of index pages read per run through a 256 kB `BAS_BULKREAD` ring (106,351 and 105,413
  buffers at the function scan, 124.2 ms and 132.6 ms execution); a `lock_timeout`
  cancellation at 2000.9 ms behind an uncommitted `DROP INDEX`; and a concurrent drop three
  seconds into a run killing the whole statement. Eight open questions record the gaps,
  including no standby run, one block size, and no roll-up for partitioned tables. The page
  is human-unverified and agent-unverified.

- 2026-08-20: **rebuilt the recommended B-tree wasted-space statement for readability and
  maintainability** in [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on
  PostgreSQL 17 (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md),
  on unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11), and **reran all 91
  mandatory tests plus fixtures 92-112 on newly initialised 17.11 and 12.2 clusters**. The
  rebuild is a **pure refactor and moves nothing the statement returns**: still sixteen
  CTEs, but `sized`/`fit`/`posting` collapse into one `page` CTE of three commented
  laterals while a new `env` and a new `gate` take the server constants and the whole
  deduplication decision out of `idx` (77 lines to 62); three statistics-state facts are
  named once in `modelled` so the caveat list and the `WHERE` clause stop spelling the same
  conditions twice; and a 35-line header maps each named change 1-6 and A-D to its stage.
  Every arithmetic expression is byte-identical and moved rather than rewritten, because
  the model mixes `numeric` and `float8`. **Identity is measured four ways on both
  servers**: `EXCEPT` in each direction between views generated from the two Markdown
  blocks returns **0 rows over 95 indexes on 17.11 and 92 on 12.2**, both exact texts give
  byte-identical `psql` output, and **0 of 129 and 0 of 106 scored fixtures disagree** on
  status, either percentage, caveats or the suppression flag. The reran suite scores
  identically under both texts: 30 deduplication-gate fixtures reproducing 421/460/1376/1931
  blocks, 0 gate over-credits and the single `i_ei_true` under-credit at `−226.4%`; 74
  partial-index tests at **66 PASS / 0 critical false positives / 0 false positives / 8
  false negatives**, with **74 of 74 live-block counts matching for the fourth consecutive
  run** and six floors moved by `ANALYZE` sampling but none across a verdict boundary; test
  16's `ei_null`/`ei_boom`/`i_squat` cases and the four DDL refusals verbatim; and the
  zero-fixture audit query at 6 rows in the fixture database against 0 in a stock one. The
  cost is stated rather than hidden — one extra `CTE Scan on idx` (5 nodes to 6), `+1.3 ms`
  of planning and `+0.8 ms` of execution at 123 indexes, `+3.2%` of execution at 600. And
  running the whole partial suite on a 12 server for the first time found the exclusions'
  portability limit: `dedup_applies` is false for all 106 indexes on 12.2, so change A's
  duplicates disjunct (25 of the 36 withheld rows on 17.11) cannot fire and **tests 30 and
  64 return as unsuppressed critical false positives at 87.6% and 93.5%** with `status = ok`
  and an empty caveat string, while the missing `pg_stat_force_next_flush()` leaves 17
  fixtures scored with `last_analyze` unset and fires change B nineteen times. Three
  fixtures are unconstructible on 12.2 (test 38's `deduplicate_items`, tests 51-52's ICU).
  Five open questions record the gaps, including no run at a block size other than 8192, no
  14.23 run of the rebuilt text, and the two new 12.2 false positives. The page remains
  human-unverified and agent-unverified.

- 2026-08-20: **applied change D** to the recommended B-tree wasted-space statement in
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md), on unchanged
  pin `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). It is the **first exclusion
  term that reaches non-partial indexes**, so the flag is renamed `suppress_partial` ->
  `suppress_row`: with one new input column (`has_expressions`, i.e. `pg_index.indexprs
  IS NOT NULL`) and one disjunct, **a non-partial expression index with no statistics
  row of its own returns no row**. The source says why the shape cannot be priced —
  `ANALYZE` writes an index its own `pg_statistic` rows only for expression attributes
  (`analyze.c:450-478`, `:588-602`), and `index_drop` uses the same `indexprs` test when
  deciding whether an index has statistics to remove (`index.c:2341-2363`) — so the
  expression falls to the statement's 32-byte default width. Control `np97` read **64.9%
  waste on 5201 blocks a `REINDEX` reproduces exactly**: a 44-byte modelled tuple against
  a measured 120-byte item, on leaves `pgstatindex` puts at 91.31% density with zero
  fragmentation. **Two critical false positives go and no partial-index verdict moves**
  (66 PASS / 0 / 0 / 8 under both texts over tests 18-91, the disjunct carrying `NOT
  is_partial`); exactly four rows differ between the texts, all non-partial: `np97` 64.9%
  and a mixed `(k, upper(s))` key 60.5% withheld as false positives, a −614.9%
  over-prediction withheld at no cost, and one true detection lost. **Unlike change C the
  silence lifts** — one `ANALYZE` takes `np97` to a reported `−16.6%` — and an
  identical-DDL pair prices the whole trade: the same index that a `REINDEX` shrinks 5201
  blocks to 523 reads 96.4% with no statistics row and 89.2% with one, against a measured
  89.9%. Two wider forms were generated from the page's own Markdown and scored beside the
  filed one: dropping `has_expressions` also catches a plain index whose column carries
  `SET STATISTICS 0` (the one alertable hole change D leaves, 64.9% on a healthy index),
  and dropping `last_analyze IS NOT NULL` also catches a never-analysed table the alerting
  rule already covers; neither was applied. An unprivileged role reading through a
  `security_invoker` copy is untouched, because `any_stats_hidden` blocks the term.
  Report-level effect over 95 indexes and 73,867 blocks: 53 rows to 49, 35 to 31
  over the 1 MB filter, 6 readings above the 50% line to 3, 0 of 11 non-partial indexes
  withheld to 4; cost is inside the noise over eight interleaved pairs (40.1-48.2 ms as
  filed against 38.7-47.6 ms amended). Measured by restarting the change-C run's isolated
  17.11 cluster with a fresh scratch database — **74 of 74 live-block counts and all 74
  pre-change reported/withheld verdicts reproduce for the third consecutive run** — plus
  seven new non-partial fixtures numbered 106-112, four estimator texts generated
  mechanically from the page's Markdown, and `REINDEX INDEX` as ground truth; change D is
  the second term also run on the isolated 12.2 server, where the same expression fixture
  builds the same 5201 blocks and moves from a reported 64.9% to withheld. Four open
  questions record the gaps, including the discarded true detection, the `SET STATISTICS
  0` residual, the fixture-inflated above-50 count, and changes A and B still being
  17.11-only. The page remains human-unverified and agent-unverified.

- 2026-08-20: **applied change C** to the recommended B-tree wasted-space statement in
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md) and
  re-scored all 74 partial-index tests against the amended text, on unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). The change is one more
  disjunct in `suppress_partial` — `bool_or(attnum > indnkeyatts AND attlen < 0)`
  in the `statvis` CTE — so **a partial index with a variable-width `INCLUDE`
  column returns no row**, and the suite reaches **0 critical false positives**
  (from 1). Exactly one of the 74 tests changes state, test 47; the four true
  detections still report at 74.7 / 74.3 / 89.1 / 94.2 against measured 74.9 /
  74.3 / 89.1 / 94.2, and the 8 false negatives are unchanged. The defect cannot
  be repaired in core SQL: a non-key column can never be an expression and
  `ANALYZE` writes index statistics only for expression attributes, so the width
  can only come from whole-table `avg_width` — 13 bytes against a stored 207 on
  test 47, a 36-byte modelled tuple against a measured 217.7, on a 787-block index
  `pgstatindex` reads at 89.71% leaf density and one `ANALYZE` moves only from
  84.0% to 83.6%. The term is scoped to `attlen < 0`, so an `INCLUDE (int)` index
  keeps its correct 0.0%; both wider forms were built from the page's own Markdown
  and priced rather than adopted — any `INCLUDE` column costs one more correct row,
  any variable-width column costs three more and is the only form that catches a
  wide **key** column, which still reads 84.1% on a fresh 792-block index with an
  empty `caveats` string. The price is measured and stated: a genuinely
  89.9%-reclaimable partial index with a `text` payload, estimated at 89.5%, is now
  withheld too, and the term emits **no caveat**, so this is the one silence a
  reader cannot see or lift. Whole-database effect over 88 indexes: 52 rows to 47,
  4 readings above the 50% line to 2, 36 partial indexes withheld to 41, 0 of 5
  non-partial indexes touched (including one with a variable-width `INCLUDE` column
  reading a correct −4.0%); cost is inside the noise over eight interleaved pairs
  (38.5-41.3 ms as filed against 39.0-42.3 ms amended). Measured by restarting the
  previous follow-up's isolated 17.11 cluster with a fresh scratch database and
  re-running its unchanged fixture scripts — **74 of 74 live-block counts and all
  74 pre-change reported/withheld verdicts reproduce exactly** — plus six new
  `INCLUDE` fixtures numbered 100-105, four estimator texts generated mechanically
  from the page's Markdown, and `REINDEX INDEX` as ground truth. Change C is also
  the only exclusion term run on an older server: a new isolated 12.2 build reports
  84.1% on the same 787-block fixture under the pre-change text and withholds it
  under the amended one. Six open questions record the gaps, including the discarded
  true detection, the wide-key family the term does not close, the caveat-free
  silence, and that changes A and B are still 17.11-only. The page remains
  human-unverified and agent-unverified.

- 2026-08-19: **applied changes A and B** to the recommended B-tree wasted-space
  statement in [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL
  17 (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md) and
  re-scored all 74 partial-index tests against the amended text, on unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). The two changes are now a
  `suppress_partial` flag in the `modelled` CTE and one `AND NOT suppress_partial`
  conjunct in the `WHERE`, so a partial index missing an index-column statistics
  row, one crediting duplicates from table statistics, or one whose table has
  changed past its **auto-analyze trigger** returns no row at all. **The twelve
  critical false positives become one.** Change A withholds 8 (tests 30, 32, 49, 50,
  78, 79, 83, 85), change B withholds 3 more (64, 69, 84) plus the one plain false
  positive (66), and only test 47 — a wide `INCLUDE` column reading 84.0% on a
  787-block index a `REINDEX` reproduces block for block, with an empty `caveats`
  string — survives, exactly as the tenth follow-up predicted from the recorded
  caveat strings. No true detection is lost: tests 68, 74, 75 and 77 still report
  75.0 / 74.3 / 89.1 / 94.2 against measured 74.9 / 74.3 / 89.1 / 94.2, and the 8
  false negatives are unchanged. Change B's threshold is the trigger
  `relation_needs_vacanalyze` uses — `autovacuum_analyze_threshold +
  autovacuum_analyze_scale_factor * reltuples`, per-table reloption overrides
  included and a negative `reltuples` clamped to zero, measured at 100,050 / 50,050
  / 10,050 / 100 / 1,000,000 / 60 / 50 across seven fixtures — and not the
  `n_mod_since_analyze > 0` first sketched: `> 0` scores these 74 tests identically
  but withheld two genuinely 89.1%-reclaimable indexes on purpose-built calibration
  fixtures, and a GUC-only threshold got both reloption fixtures backwards. The
  exclusion carries `is_partial`, so 0 of 4 non-partial controls are touched, at the
  stated price of a non-partial expression index with no statistics row reading 64.9%
  unsuppressed on a freshly built 5201-block index. Whole-database effect on the
  final state: 82 rows returned to 46, 8 readings above the 50% alert line to 2, and
  9 of the pre-change top-20 triage rows withheld, 6 of them above 50%; cost is
  inside the noise (33.4 / 38.0 / 32.8 ms as filed against 37.5 / 33.6 / 35.2 ms
  amended, interleaved over 86 indexes), and no percentage moves because
  `expected_blocks` and `floor_blocks` are untouched. One new hazard is measured:
  without `pg_stat_force_next_flush()` before an `ANALYZE`, a same-session bulk load
  leaves `n_mod_since_analyze` at the full 200,000 rows and `n_live_tup` at 400,000
  for a 200,000-row table, which fires the new caveat spuriously in the safe
  direction. Measured on one isolated 17.11 server built out of tree from the pin
  `--with-icu --enable-debug`, `autovacuum`/`fsync` off, with three estimator texts
  generated mechanically from the page's own Markdown (the amended text, the
  pre-change text from `git show HEAD:`, and a `> 0` copy) and `REINDEX INDEX` as
  ground truth; the 74 fixtures are a **reconstruction** from the tenth follow-up's
  published shapes, since the original harness was deleted with its sandbox — 61 of
  the 74 reproduce their filed live-block count exactly and 13 differ, three of those
  because the reconstruction got the fixture shape wrong, none changing a verdict
  class. Five open questions record the gaps, including that the reconstruction is
  not the same population, that the `is_partial` scoping is a judgement rather than a
  measurement, that the borrowed trigger is not calibrated against a subset, and that
  the two new terms were never run on 12.2 or 14.23. The page remains
  human-unverified and agent-unverified.

- 2026-08-19: folded **74 partial-index mandatory tests** into the mandatory-tests
  section of [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md), taking
  that suite to 91 tests in one numbering, against unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). **The recommended statement
  fails the primary requirement.** Scored on `wasted_space_pct_floor`, as the
  requirement specifies: 52 PASS, **12 critical false positives**, 1 false positive,
  8 false negatives, 1 cell the pass/fail rule leaves undefined. The twelve report
  84.0% to 99.6% waste on freshly built or freshly grown partial indexes that a
  `REINDEX` reproduces block for block, and the page's filed alerting rule suppresses
  none of them; the eight false negatives are indexes a `REINDEX` shrinks by 73-94%
  reading under 20%. One structural fact explains 20 of the 22: `ANALYZE` builds
  per-column statistics for an index only when the index has expressions, so a
  partial index on a plain column carries a row count and nothing else and is priced
  from whole-table `avg_width`, `null_frac` and `n_distinct` — measured as 0
  `pg_stats` rows for six plain-column partial indexes against 3 for the expression
  ones. Materialising each predicate subset as its own table and pointing the same
  statement at it modelled all seven within 4.1 points and matched the partial twin's
  rebuilt size exactly in all seven, which locates the defect entirely in the
  statistics input rather than the arithmetic. The floor column is proved immune by
  construction to the duplication family (`n_distinct`, MCV and extended-statistics
  mismatches reach 70.6% on the point estimate and 0.0% on the floor) and fully
  exposed to width, NULL-fraction and row-count mismatch. One `ANALYZE` repairs 7 of
  the 12 (93.5% to 0.3%, 99.6% to 0.0%, 86.7% to 1.1%) and nothing in core SQL
  repairs the other 5, because no catalog holds a plain-column partial index's
  subset width or NULL fraction. Two measured alert-routing changes would take the 12
  to 1 at zero cost in true detections — suppress on two caveats the statement
  already emits, and add a partial-index staleness caveat keyed on
  `n_mod_since_analyze`, which separated 0 from 300,000 and 399,000 across a healthy
  index, two stale ones and a genuinely 89%-reclaimable one — and until they are
  applied the recommended-statement section excludes partial indexes from any alert.
  Three incidental findings were filed: a B-tree index datum over 510 bytes is
  pglz-compressed in place (142 blocks for 20,000 compressible 1001-byte keys against
  1560 for 20,000 incompressible 481-byte ones), a same-session `DELETE; VACUUM`
  leaves `n_dead_tup` non-zero because VACUUM and ANALYZE write the counters
  absolutely while pending per-backend deltas add on top, and an append-only partial
  index measured 880 blocks live against 881 rebuilt. Measured on one isolated 17.11
  server built from the pin `--with-icu --enable-debug`, 74 partial indexes over 60
  tables, with `REINDEX INDEX` as ground truth and the statement extracted
  mechanically from the page's own Markdown; the server was shut down cleanly
  afterwards and its sandbox retained under `.wiki-runtime/tmp/partial17/`. Nine
  open questions record what was not done, including that no 12.2 or 14.23 run backs
  the partial-index numbers and that neither proposed change was applied and
  re-scored end to end. The page remains human-unverified and agent-unverified.

- 2026-08-18: folded change 6 into the recommended B-tree wasted-space statement on
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md) and
  **re-measured every server-measured table on that page**, against unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). The section is retitled "with
  all six changes", change 6 keeps its rationale but loses its duplicate SQL block,
  and the recommendation is now one block of SQL with no assembly step. Nothing on
  the page is a 17.10 observation any more. Four servers: one isolated 17.11 install
  configured `--with-icu --enable-debug` carrying four scratch databases (the 15 v12
  fixtures plus the 54-cell matrix and Methods A/A-prime/B/C/D; the twelve-issue-review
  family with its unprivileged `probe` role; the 28 mandatory-test fixtures with their
  eight custom operator classes; a fresh database for the runnable harness), a second
  17.11 cluster plus isolated 14.23 and 12.2 servers for the 12-through-17 family.
  Every scored statement text, including the pre-change-6 form used for the "before"
  column of every comparison, was generated mechanically from the page's own Markdown,
  so the scored text is the filed text plus documented edits. Reproduced exactly: all
  15 `pgstatindex` fixture rows, Method C's rebuild sizes, Method B's 36-of-36 census
  and its 18 never-vacuumed `Heap Fetches` catches, the 313.58%-against-96.15% density
  blow-up, the gate scoreboard (5 over-credits before change 6, 0 after, 1 deliberate
  under-credit; 8 for the earlier v17 sweep), the audit query's 6 / 0 / 0 rows, the
  harness's 23 indexes with 11 "can" and 11 "cannot" `DEBUG1` verdicts, and every 12.2
  blocker (`invalid function number 4`, `unrecognized parameter "deduplicate_items"`,
  `ICU is not supported in this build`). Moved only where `ANALYZE` sampled
  differently: Method A exact on 11 of 15 fixtures rather than 9 (the partial fixture
  landed on 50,034 estimated rows), the 54-cell matrix at 33 exact rather than 30, the
  duplication sweep's 10-rows-per-key row flipping to a negative `n_distinct` and
  losing its credit, and `i_q1000` modelling 899 blocks rather than 901 on 8 stored
  most-common values instead of 11. One earlier claim is corrected: change 6 does not
  under-credit an opclass whose support function is a `LANGUAGE internal` alias of
  `btequalimage` — `prosrc` is what the whitelist matches, so both texts report 69.3%
  on a true 69.4% — and the cost is confined to non-internal support functions,
  re-measured with a SQL one. Newly measured, because this 17.11 build has ICU:
  the nondeterministic-collation conjunct (a healthy 3611-block index reads 0.1%
  against the earlier sweep's 87.6%), change 1's residual over-prediction on a
  two-column and a partial fixture (−24.8% and −33.1%), a never-rebuilt 1.5M-row
  random-insertion twin at 25.9% beside its rebuilt sibling's 11.5%, and interleaved
  timings that price the five earlier changes at roughly 30% while change 6 stays
  inside the noise. Twenty-two open questions were rewritten and three retired as
  resolved. All servers were stopped afterwards. The page remains human-unverified and
  agent-unverified.

- 2026-08-18: added a maintained "current recommended statement" section to
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md), at
  the user's request and against unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c`, together with the standing
  requirement that drives it. The recommendation is the corrected statement with
  all five changes, with change 6's `all_equalimage` subquery substituted for the
  existence test. It is assembled in two stated steps rather than copied, so no
  second SQL text can drift, and the 17.11 and 12.2 runs behind the seventeen
  mandatory-test verdicts were generated exactly that way — the assembled text is
  one the page has run, not one it only describes. The section ranks all six
  variants on the three criteria the prompt named. Accuracy: **0 over-credits**
  over 28 zero-waste fixtures against 5 for the same statement as filed and 8 for
  the earlier v17 sweep, 0 fixtures above 30% on either percentage column against
  3 and 4, plus the five changes' own gains (`i_q1000` +5.5% to −0.6%,
  `i_ext`/`i_sup` −206.4% to +0.1%, and a genuinely 49.8%-reclaimable correlated
  index from an unalertable −38.3% to +49.9%). Fixes: six numbered changes on top
  of the portable statement's gate conjuncts and both reporting corrections,
  ending in the catalog form of what `_bt_allequalimage` actually does — look the
  support function up and **call** it — with `prosrc` rather than `proname` as the
  identity, which is what `fmgr` resolves for a `LANGUAGE internal` function.
  Compatibility: 12 through 17 unchanged, measured on 12.2 and 17.11 for this
  exact text and on 14.23 and 17.10 for the pre-change-6 text, with 13, 15 and 16
  never run and `pg_language.lanname` / `pg_proc.prosrc` confirmed present on
  12.2. Four residual errors are stated with their direction, all safe for a
  floor-based alert except the last: change 1's −99.4% band just above a multiple
  of the 132-TID cap, change 2's −88.6% on independent columns, change 6's single
  custom-opclass under-credit (a real 69.4% rebuild win reported as 0.1%), and the
  27.1% a randomly inserted, never-deleted index reads on both columns while the
  model is exact to the block. The section also records what the recommendation
  does not replace — Method C as the only exact arbiter, Method B's leaf census,
  Method A-prime's sampled width — and the rule for displacing it: name the trade
  instead of switching silently, since an over-prediction and an over-credit are
  not interchangeable. Source-only, with no server run; two new open questions
  record that the ranking covers only this page's own statements and fixtures, and
  that the assembled text has two servers and one 28-fixture set behind it while
  every per-fixture number it inherits was measured without change 6.
  `raw/postgres-17/` is unchanged, and the page stays human-unverified and
  agent-unverified.

- 2026-08-18: filed a seventeen-test mandatory deduplication-gate suite as a
  seventh follow-up on [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on
  PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md),
  against unchanged pin `786db8dcf168bd9df8f55047337525ac19118b1c`, and scored
  both deduplication-aware statements on the page against every test. The
  corrected 12-through-17 statement fails 3 of 17 and the earlier v17 sweep fails
  6; every failure is the same defect, a gate that asks whether an equal-image
  support function exists in `pg_amproc` while `_bt_allequalimage` looks it up and
  then **calls** it. Measured on a **17.11 ICU** build of the pin
  (`--with-icu --enable-debug`, `block_size` 8192, `autovacuum`/`fsync` off) in a
  scratch database with 28 fixtures that have nothing to reclaim, plus the
  isolated 12.2 server for version compatibility. Eight custom operator classes
  supply what no built-in type can — `amvalidate` returns true for SQL and
  PL/pgSQL support functions, since `btvalidate` and `assignProcTypes` check only
  arity, boolean return and non-cross-typedness — and a NULL-returning function
  aborts `CREATE INDEX` with `function 16575 returned NULL` while a raising one
  propagates its exception. As filed the gate over-credits 5 fixtures: a healthy
  1376-block index whose support function returns false reads **69.3%**, and two
  mixed TRUE/FALSE two-column indexes read **78.1%** once a `CREATE STATISTICS
  (ndistinct)` object gives change 2 something to compress; the floor column stays
  at 0.1-0.2% throughout, so the floor-based alert rule was immune and the point
  estimate was not. Change 6 requires the registered proc to be `LANGUAGE
  internal` with `prosrc` in (`btequalimage`, `btvarstrequalimage`): 0
  over-credits, one deliberate under-credit (a custom opclass that really does
  deduplicate, 421 blocks, reads −226.4%), 12.2 / 12.5 / 16.6 ms against the filed
  12.8 / 12.1 / 14.0 ms over 34,164 blocks, and no reading moves on a stock
  database, whose 29 B-tree support-function-4 rows are 26 `btequalimage` plus 3
  `btvarstrequalimage`, all `LANGUAGE internal` in `pg_catalog`. `prosrc` beats
  `proname` on measured fixtures: a `LANGUAGE internal` alias in `public` and a
  renamed-away built-in break the name test as under-credits while a same-named
  SQL impostor at a fresh OID breaks it as an over-credit, which `fmgr`'s built-in
  fast path and its `LANGUAGE internal` `prosrc` lookup explain exactly. Rewriting
  a support function to return false leaves the metapage true, makes
  `bt_index_check` raise `metapage incorrectly indicates that deduplication is
  safe`, and a `REINDEX` then takes the index from 421 to 1376 blocks — which the
  corrected reading predicted to within 0.4 points, closing the earlier
  metapage-versus-catalog question with a measurement. The reverse mutation is
  filed as the honest cost: adding a working `FUNCTION 4` to an opclass that had
  none makes a rebuild reclaim a true 69.4% that change 6 reports as 0.1%. On 12.2
  seven of the seventeen tests are unconstructible (`invalid function number 4`,
  `unrecognized parameter "deduplicate_items"`, `ICU is not supported in this
  build`) and all four statement variants agree with the engine on all 10
  buildable fixtures, with `i_multi_bad` reading 28.8% on both majors — an
  `avg_width` truncation to 4 on a 5-byte `numeric`, not a gate error. Ships a
  zero-fixture audit query (6 rows in the fixture database, 0 on a stock 17.11 and
  0 on 12.2) and a fixture harness that was re-run verbatim from the page text: 23
  indexes, 11 engine "can", 11 "cannot", and no verdict at all for the `INCLUDE`
  index. 13 new open questions record what was not measured, including that the
  earlier tables were not re-scored with change 6 and that the whitelist is a
  fixed two-name list. `raw/postgres-17/` is unchanged, and the page stays
  human-unverified and agent-unverified.

- 2026-08-18: worked a twelve-issue external review of the portable
  12-through-17 statement on [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat
  Method on PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md) as a
  sixth follow-up, measured on a new isolated **17.11** server built out of tree
  from the current pin `786db8dcf168bd9df8f55047337525ac19118b1c` — the first
  numbers on that page taken on the pinned commit rather than the previous 17.10
  one — plus an isolated 12.2 server for portability. The ledger is four issues
  already fixed (the negative `n_distinct` branch, the nondeterministic-collation
  and `indnatts = indnkeyatts` conjuncts, and the two reporting defects), one
  mischaracterized, five applied and two rejected. The mischaracterization is the
  page's own attribution of `i_q1000`'s 49-block gap to page packing: 48 blocks
  are a posting-tuple count error — the model divided a class's rows by its TID
  count, letting one tuple span two key groups, while `_bt_load` flushes the
  pending posting list at every key change — and 1 block is internal-fanout
  error, because pivots above a deduplicated leaf level carry a heap TID and
  measure 212 per page against the modelled 284; leaf packing was already right,
  confirmed by a leaf holding nine 808-byte posting tuples plus a 24-byte
  truncated high key. Applied, with directions stated: the prescribed key-group
  round-up removes every phantom-bloat reading above 264 rows per key (`i_q1000`
  +5.5% to −0.6%, `i_r500` and `i_r1000` +5.5% to −0.2%/−0.3%, `i_r265` +10.8% to
  −33.5%) and is **not** a strict improvement, because it prices each group's
  last, partial posting tuple at full size and so over-predicts to −99.4% at 133
  rows per key and −88.7% at 143, while `i_cd` does not move at all (its 38 blocks
  are an off-by-one leaf capacity: 12 modelled posting tuples where the build fits
  11 data items plus the high key); `pg_stats_ext.n_distinct` replaces the
  per-column product when an `ndistinct` object covers the whole key, which is the
  only change that recovers a missed alert — a correlated `(a, b)` index with 49.8%
  genuinely reclaimable read `−38.3%` with a `−53.3%` floor and now reads `+49.9%`,
  one block from its rebuild — with measured superset-covering, wrong-column-set
  fallback, reversed-column and expression-key behavior, and `pg_stats_ext`'s
  owner-membership condition (8 rows to the owner, 0 to an unprivileged role);
  a `statistics not visible to this role` caveat separates a withheld `pg_stats`
  row from an absent one and joins the alert-suppression set, because the 32-byte
  default `avg_width` makes a healthy 100-byte-key index read 62.5% on **both**
  columns to a role without `SELECT` (0.0% as owner), the same on 12.2; a
  randomly inserted, never-deleted index reports 27.1% on both columns at 65.68%
  leaf density and 49.87% fragmentation with zero deleted pages, its model
  exactly equal to the 2745-block rebuild, which is the one valid issue the
  floor-plus-status-plus-caveats rule cannot defend against; and the baseline is
  stated from `_bt_findsplitloc` — fillfactor only on rightmost splits, 50:50
  elsewhere — with a measured drift table in which the 1020 blocks a rebuild
  reclaimed came 10.9% back after 500,000 further random inserts and a fresh
  rebuild landed on the model's 4116 blocks exactly. Rejected: `least(reltuples,
  n_live_tup)` stays, since `reltuples` alone reports the 19%-drained `i_stale` as
  0.0% and loses 521 blocks on both columns, and `n_live_tup` is DML-maintained
  without `ANALYZE`; `bt_metap().allequalimage` stays out, since the build
  recomputes the flag from the catalog, a pg_upgrade'd v12 index reports false
  until a `REINDEX`, the function is superuser-only, and a `deduplicate_items =
  off` index reports true while holding no posting lists — the metapage answers
  "may this index deduplicate as it stands", not "would a fresh build
  deduplicate". The statement runs unchanged on 12.2, every added construct
  exists in 12 (`pg_stats_ext.n_distinct` renders `{"1, 2": 1000}` there too), and
  `inherited`/`exprs` are deliberately not referenced because 12 lacks them. 15
  new open questions record what was not measured, including the unapplied exact
  leaf-capacity and two-size-posting-tuple refinements, the untested RLS half of
  the new caveat, the un-recomputed 30%-threshold alert table, and that the rest
  of the page remains a 17.10 observation. `raw/postgres-17/` is unchanged, and
  the page stays human-unverified and agent-unverified.

- 2026-08-18: renamed the reporting identifiers of the core-SQL B-tree bloat
  statements on [Measuring B-Tree Index Bloat With Core SQL Only in PostgreSQL 12
  (unverified)](v12/questions/indexing/btree-index-bloat-core-sql-only.md) off the
  word "bloat", at the user's request and against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (12.2), matching the same correction
  made to the v17 page a day earlier. `wasted` is now `wasted_space`, `bloat_pct`
  is `wasted_space_pct`, the Method A tag is `wiki_btree_wasted_space_sweep`, and
  the Method C probe index is `wiki_wasted_space_probe` in all five places it
  appears; the two accuracy-table headers became `model wasted_space %` and
  `true wasted_space %`, while the page title, the conceptual use of "bloat" and
  the fixture-recipe `bloat type` column stay as filed. Source-only: nothing was
  executed, so "no number moves" is an argument about which expressions changed.
  The v12 evidence differs from v17's in three ways worth recording. There is no
  glossary in this checkout, so the normative definition comes from
  `ref/reindex.sgml` — a bloated index "contains many empty or nearly-empty pages"
  — reinforced by `maintenance.sgml`'s partly-emptied-page mechanism, both per-page
  state that a file-size-minus-model statement cannot see, while `ref/copy.sgml`
  supplies "wasted space" for what a maintenance command recovers; all 24
  doc-tree matches for the string are prose, `system_views.sql`, `pg_proc.dat` and
  every contrib SQL script have none, and `pgstattuple` says
  `free_space`/`free_percent`. The query ID is computed in contrib
  `pg_stat_statements` rather than core, and its `JumbleExpr` `T_TargetEntry` case
  hashes `resno` and `ressortgroupref` only, so `resname` cannot move it, and the
  lexer's `xc` state discards the tag before parsing. And the probe rename is not a
  label change at all: because v12 keys a utility statement by
  `pgss_hash_string` over its text, the renamed `CREATE`/`DROP INDEX CONCURRENTLY`
  get new `pg_stat_statements` entries, while inside the two `SELECT`s the same
  name is a constant that `RecordConstLocation` and `generate_normalized_query`
  reduce to `$n`. Five new open questions record what was not run, including that
  the byte column stays clamped at zero beside a signed percentage — `idx_dup` at
  −6.4% and `idx_var` at −4.6% are the two cells affected — and that v12's
  `half_rounded` rounds toward positive infinity rather than symmetrically. No
  server was started, `raw/postgres-12/` is unchanged, and the page remains
  human-unverified and agent-unverified.

- 2026-08-18: renamed the reporting columns of both bloat statements on
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on
  PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md) off the
  word "bloat", at the user's request and against unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). `wasted` is now
  `wasted_space`, `bloat_pct` is `wasted_space_pct`, `bloat_pct_floor` is
  `wasted_space_pct_floor`, and the two statement tags are
  `wiki_btree_wasted_space_sweep_v17` and `wiki_btree_wasted_space_sweep_12_17`;
  the page's prose follows the new names, with two artifacts left verbatim (the
  psql capture taken before the rename and the as-filed expression quotes in the
  reporting-defect table). Source-only: nothing was executed, so the claim that
  only `AS` labels moved rests on the two `SELECT` lists plus the pinned tree.
  `AS` assigns an output column label and nothing else, both `ORDER BY` keys are
  expressions rather than labels (a label is usable there only as a bare sort
  key), and the rename cannot move `queryid`, because `JumbleQuery` hashes the
  post-parse-analysis `Query` tree and `TargetEntry.resname` is declared
  `pg_node_attr(query_jumble_ignore)`, for which `gen_node_support.pl` emits no
  code into the generated `queryjumblefuncs.funcs.c`. The 22-byte names sit far
  below the `NAMEDATALEN` truncation point, where the lexer's
  `downcase_truncate_identifier` would raise a `NOTICE`. The rename is more than
  cosmetic: the glossary defines bloat as space in data pages holding no current
  row versions - per-page state that these statements, which subtract a modelled
  rebuild size from the file size, cannot see - while "wasted space" is the docs'
  own phrase for space a maintenance command recovers, and no core view,
  `pg_proc.dat` entry or contrib SQL script names a column `bloat`
  (`pgstattuple` calls the quantity `free_space`/`free_percent`; the only
  non-prose occurrence in the tree is an unrelated static in the imported IANA
  timezone compiler). Consumer impact is filed too: an old name now raises
  `ERRCODE_UNDEFINED_COLUMN`, `pg_size_pretty` returns `text` so ranking belongs
  on the byte expression through a suggested `wasted_space_bytes`, and an existing
  `pg_stat_statements` entry keeps showing the old tag because the query text is
  written only when the hash entry is created. Five new open questions record
  that no server ran the renamed statements. No server was started,
  `raw/postgres-17/` is unchanged, and the page remains human-unverified and
  agent-unverified.

- 2026-08-18: extended [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on
  PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md) with a
  source-only follow-up that confirms and corrects two reporting defects both of
  its bloat statements shipped with, against unchanged pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` (17.11). Neither defect touches
  `expected_blocks`, `floor_blocks`, `live_rows`, the deduplication gate, `status`
  or `caveats`, so no percentage on the page moves; the two statement blocks now
  carry the corrected columns and the measurements are labelled as taken with the
  defective ones. First, `fsm_bytes > 0 AS has_freed_pages` reports history, not
  state: an index's FSM stores only free-or-used (`RecordFreeIndexPage` writes
  `BLCKSZ - 1`, `RecordUsedIndexPage` writes 0), the first recorded page extends
  the fork to a fixed three blocks / 24576 bytes at `block_size` 8192
  (`SlotsPerFSMPage` 4069, `FSM_TREE_DEPTH` 3), `_bt_allocbuf`'s
  `GetFreeIndexPage` marks pages used without shortening the file, no nbtree path
  reaches `FreeSpaceMapPrepareTruncateRel` (its live callers are heap truncation
  and `RelationTruncateIndexes`; the SP-GiST call is `#ifdef NOT_USED`), and only a
  storage replacement through `RelationSetNewRelfilenumber` — `REINDEX`,
  transactional `TRUNCATE` — resets it, so the column reads false exactly when the
  index is fresh. In the other direction `btvacuumpage` records a deleted page only
  once `BTPageIsRecyclable` holds, `_bt_pendingfsm_finalize` stops at the first
  still-visible `safexid`, half-dead pages are never recorded, and partly-emptied
  leaves — the documented bloat mechanism — never enter the map at all, so a
  deleted-page-heavy index can read false. Renamed `fsm_written_since_build`, with
  the current empty/deleted/reusable counts sourced from `VACUUM VERBOSE`'s
  `pages: N in total, N newly deleted, N currently deleted, N reusable` line
  (`IndexBulkDeleteResult`, where nbtree treats `pages_free` as whole-index state)
  in core, or from contrib: `pgstatindex.deleted_pages` plus `empty_pages` (which
  is in fact the half-dead class), `pg_freespace` with the `avail > 0` idiom its own
  regression test uses on a B-tree index, and `pageinspect`'s per-page `type`. A
  `pg_read_binary_file` decode of the `_fsm` fork is noted as possible in core SQL
  and not attempted. Second, `wasted` was clamped at zero while `bloat_pct` was
  not, so `i_var` on 17.10 printed `0 bytes` beside -4.4% while the signed value is
  -1,163,264 bytes, and the earlier dedup-aware sweep printed `0 bytes` beside
  -92.5% while hiding 10,805,248 bytes; a negative percentage is shown to mean only
  that a rebuild is not predicted to shrink the index — usually model
  over-prediction, but the page's own `idx_dup` really did grow from 396 to 426
  blocks on rebuild — so both columns and the `ORDER BY` key now use one signed
  convention, which `pg_size_pretty` supports symmetrically and the `dbsize`
  regression test asserts. Seven new open questions record that nothing was
  re-measured: no server ran the corrected statement, the rendered strings
  `-1136 kB` / `-10 MB` / `-7824 kB` are derived by hand, and no fixture's FSM state
  was ever recorded, so neither direction of the boolean's failure was observed. No
  server was started, `raw/postgres-17/` is unchanged, and the page remains
  human-unverified and agent-unverified.

- 2026-08-17: removed the v17 question page Detecting Bloat in All Index Types by
  Storing an Index/Heap Size Ratio in COMMENT in PostgreSQL 17 (unverified) at the
  user's request, together with its root-index and v17-landing-page entries, the
  two inbound `## Navigation` links on
  Calibrating a COMMENT-Stored Bytes-per-Table-Tuple REINDEX Threshold for Every Non-B-Tree Index in PostgreSQL 17 (unverified)
  and
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md),
  and the index/heap-ratio clause of the v17 coverage cell above that described
  it: the screening-signal-only verdict, the 49-cell drift-versus-"index larger
  than the heap" scores, the `hashbuild`/`estimate_rel_size` bucket-sizing and
  same-VACUUM-recycling findings, the day-zero sweep, the GIN
  baseline-1.004900 fixture, and the comment durability matrix. No surviving v17
  page referred to the page in prose. The two historical coverage notes below
  that referenced it now name it as plain text. The v12 page of the same name was
  removed on 2026-08-13, so no supported version carries this index/heap-ratio
  proposal any more; COMMENT-stored index-bloat screening in v17 now runs through
  the bytes-per-table-tuple page named above, and core-SQL B-tree bloat
  measurement through the B-tree page named above. The pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` and every surviving page's citations
  and verification fields are unchanged.

- 2026-08-17: repinned the four non-legacy versions to their upstream branch tips
  and reviewed every commit in each range: v14 14.23 `5c00f4e2e3b` -> 14.24
  `a92fbdfb830` (133 commits), v17 17.10 `54eeefaedbe` -> 17.11 `786db8dcf16`
  (193), v18 18.3-line `6cb307251c5` -> 18.6 `baa7b142aac` (294, crossing the 18.4
  and 18.6 releases; 18.5 was stamped but never released), and v19 19beta2
  `99e47536bbf` -> 19beta3 `67342a14863` (152). v12 stays pinned to 12.2
  `45b88269a35` because its pages carry measurements taken on a 12.2 build.
  The v19 checkout had drifted 52 commits *behind* its declared pin, and that pin
  was not even present in the local clone, so every v19 citation line number
  resolved against the wrong tree; `scripts/wiki_lint` now checks the pinned commit
  against the checkout's HEAD so this cannot recur silently. 1,981 citation line
  fragments were re-anchored with the new `scripts/repin_citations`, 493 stale
  labels synced, 38 anchors repointed by hand, and 11 pre-existing citations that
  ran past end-of-file were fixed (including seven on v12 pages). Five claims that
  the ranges falsified were corrected: the v14 and v18 same-role RLS plan-cache
  staleness finding (closed by CVE-2026-14666), the v17 exclusion-index non-reuse
  claim (`1d6c654c818`), the v17 RANGE DEFAULT-partition pruning bug
  (`31f2acde53d`), the v17 "no related commits since 17.10" statement, and the v19
  pgrepack direct-use rejection site (`5d47df21e89`). The v18 bidirectional page's
  open question about unquoted publisher-side identifiers is answered by
  CVE-2026-6638. Measurements taken on the previous pins are kept and labelled as
  such rather than re-run, with a per-page source check of whether the underlying
  code moved; every affected page keeps `verified: false` and
  `verified_by_agent: not yet`.

- 2026-08-17: removed the v12 question page Can COMMENT-Stored Table DML
  Counters Trigger GIN REINDEX at 40% in PostgreSQL 12? (unverified) at the
  user's request, together with its root-index and v12-landing-page entries and
  the one inbound `## Navigation` link on
  [Calibrating a COMMENT-Stored Bytes-per-Table-Tuple REINDEX Threshold for Every Non-B-Tree Index in PostgreSQL 12 (unverified)](v12/questions/indexing/comment-stored-bytes-per-table-tuple-non-btree.md).
  No surviving v12 page referred to it in prose, and the v12 coverage cell above
  never described it, so no coverage clause was dropped. The four historical
  coverage notes below that referenced the page now name it as plain text.
  COMMENT-stored index-bloat screening in v12 now runs through the
  bytes-per-table-tuple page named above, and core-SQL B-tree bloat measurement
  through
  [Measuring B-Tree Index Bloat With Core SQL Only in PostgreSQL 12 (unverified)](v12/questions/indexing/btree-index-bloat-core-sql-only.md);
  no v12 page proposes a table-DML-counter GIN rebuild trigger any more. The pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` and every surviving page's
  citations and verification fields are unchanged.

- 2026-08-13: removed the v12 question page Detecting Bloat in All Index Types
  by Storing an Index/Heap Size Ratio in COMMENT in PostgreSQL 12 (unverified)
  at the user's request, together with its root-index and v12-landing-page
  entries, the two inbound `## Navigation` links on
  [Calibrating a COMMENT-Stored Bytes-per-Table-Tuple REINDEX Threshold for Every Non-B-Tree Index in PostgreSQL 12 (unverified)](v12/questions/indexing/comment-stored-bytes-per-table-tuple-non-btree.md)
  and Can COMMENT-Stored Table DML Counters Trigger GIN REINDEX at 40% in
  PostgreSQL 12? (unverified),
  and the index/heap-ratio clause of the v12 coverage cell above that described
  it, including its drift-versus-"index larger than the heap" and
  `REINDEX INDEX CONCURRENTLY` follow-ups. The six historical coverage notes
  below that referenced the page now name it as plain text. COMMENT-stored
  index-bloat screening in v12 now runs through the bytes-per-table-tuple and
  GIN DML-counter pages named above, and core-SQL B-tree bloat measurement
  through
  [Measuring B-Tree Index Bloat With Core SQL Only in PostgreSQL 12 (unverified)](v12/questions/indexing/btree-index-bloat-core-sql-only.md).
  The separate v17 page Detecting Bloat in All Index Types by Storing an
  Index/Heap Size Ratio in COMMENT in PostgreSQL 17 (unverified) and its inbound
  links were untouched then, so v17 still carried this proposal on that date; it
  was removed on 2026-08-17, as the note above records. The
  pin `45b88269a353ad93744772791feb6d01bc7e1e42` and every surviving page's
  citations and verification fields are unchanged.

- 2026-08-13: filed [Changes to Declarative Partition Bound Syntax and
  pg_class.relpartbound Since Partitioning Was Introduced, as of PostgreSQL 18
  (unverified)](v18/questions/server-administration/declarative-partition-bound-syntax-and-relpartbound.md)
  against unchanged pin `6cb307251c5c6261286c1566496920976640108e` (18.3).
  Verdict: yes to both, but every substantive change landed early. The bound
  grammar changed three times and has been frozen since v12 — `d363d42bb9a`
  replaced `UNBOUNDED` with `MINVALUE`/`MAXVALUE` before 10.0 shipped,
  `6f6b99d1335` and `1aba8e651ac` added `DEFAULT` and hash
  `WITH (MODULUS m, REMAINDER r)` in v11 (with `9361f6f54e3` adding the
  sentinel-ordering rule), and `7c079d7417a` collapsed the literal enumeration
  into a general `partition_bound_expr` in v12. The complete `git log -L` over
  the `PartitionBoundSpec:` production for `REL_10_0..6cb30725` returns only six
  commits, the later ones being a typo fix, two indentation runs, and the v18
  commit `2d8bff603c9`, which adds `parser_errposition(@3)` to the two
  hash-bound errors and is v18's sole grammar change. The `pg_class.relpartbound`
  column definition never changed, while the stored `pg_node_tree` changed twice:
  v11 added `is_default`/`modulus`/`remainder`, and v17's `d20d8fbd3e4` made
  `nodeToString()` write `-1` for every `:location`. The v16 switch to generated
  node support (`964d01ae90c`) left the output byte-compatible, and `outDatum`
  and `_outConst` are byte-identical to `REL_10_0`. The deparsed
  `pg_get_expr(relpartbound, oid)` text never changed, and no typed bound
  accessor was ever added, so the three SQL forms remain the opaque node tree,
  the deparsed `FOR VALUES ...` string, and the derived
  `pg_get_partition_constraintdef()` boolean; exposure changes since v10 are
  additions only, the newest being v14's ` DETACH PENDING` psql annotation.
  Also documented: `MODULUS`/`REMAINDER` are `NonReservedWord` `DefElem`s rather
  than keywords, `MINVALUE`/`MAXVALUE` reach the transform as `ColumnRef`s,
  MERGE/SPLIT PARTITION were reverted by `3890d90c150` before 18.0, the
  write-once/clear-once `relpartbound` lifecycle including the two-transaction
  concurrent detach, and the three engine read paths in `partdesc.c`,
  `partcache.c` and `partbounds.c` with the v18 hardening `c899c6839f5`.
  Measured on an isolated 18.3 build: the literal stored node text for hash,
  list, range and default bounds with `:location -1` at every level in 14/14
  bounds; `FOR VALUES IN ((2+1), 5, NULL)` stored as `Const` 3 and deparsed as
  `FOR VALUES IN (3, 5, NULL)`; `WITH (REMAINDER 0, MODULUS 4)` accepted and
  canonicalized to `WITH (modulus 4, remainder 0)`; quoted `"minvalue"` accepted
  as the sentinel while `"MINVALUE"` is rejected; `FROM (-5)` deparsing as
  `FROM ('-5')`; `pretty = true` identical to the plain call on 14/14 bounds; a
  detach-then-reattach and a `pg_dump -s` round trip reproducing the bound
  exactly; `DETACH` clearing `relpartbound` and `relispartition`; and a no-TOAST
  size cliff where an 8,000-character hex bound stores in 7,627 bytes (25,720
  characters of node text) while 8,400 characters fails with
  `row is too big: size 8216, maximum size 8160`. Four open questions were
  filed, including the platform-specific size cliff, whether `d20d8fbd3e4`
  considered its `pg_node_tree` catalog side effects, the undocumented and
  untested quoted-sentinel asymmetry, and the unmeasured foreign-table partition
  case. Three test gaps were recorded: no test anywhere in the tree asserts the
  stored node text, the size cliff, or the quoted-sentinel behavior. The
  isolated server was stopped and its data directory removed. The page is
  human-unverified and agent-unverified.

- 2026-08-12: filed [Extracting Declarative Range Partition Bounds With SQL and
  No Regex in PostgreSQL 12
  (unverified)](v12/questions/server-administration/extract-range-partition-bounds-without-regex.md)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42` (12.2).
  Verdict: v12 has no catalog column, view, or function that returns a range
  bound as a typed value, so extraction must decompose the
  `pg_get_expr(relpartbound, oid)` text — the same string `psql \d` prints and
  `pg_dump` pastes into `ATTACH PARTITION` — and no regex is needed because the
  deparser's grammar is fixed: `FOR VALUES FROM (` … `) TO (`, elements joined by
  `, `, bare `MINVALUE`/`MAXVALUE`, `DEFAULT` for a default partition, and
  literals with no `::type` and no `COLLATE` because `get_range_partbound_string`
  calls `get_const_expr` with `showtype = -1`. The filed recipe splits the text on
  the quote character with `string_to_array`, masks each literal's contents to an
  equal-length run so quote parity is decidable (the two quotes of an escaped
  quote are adjacent, so every spurious "outside" segment is empty), then finds
  the separators with `strpos`/`substr`; it uses `substr` rather than `substring`
  because only `substring(text, text)` resolves to the regex `textregexsubstr`.
  Measured on an isolated 12.2 server over 18 range parents, 45 partitions and 95
  creation-time control elements: a from-scratch reconstruction of the deparse
  rules matched `pg_get_expr` on 41/41 partitions, the recipe scored 95/95, and the
  obvious `split_part` + `btrim` version scored 81/94 elements and got 9/41
  partitions wrong on values containing `) TO (`, `, `, or an escaped quote.
  `pg_get_expr(relpartbound, 0)` and the `pretty = true` form were byte-identical
  to the canonical call on 45/45; no bound text contained `::`; two contained a
  newline inside a literal. Also measured: `DateStyle`, `TimeZone`,
  `IntervalStyle`, `extra_float_digits`, `bytea_output` and
  `standard_conforming_strings` all change the text (all `PGC_USERSET`), with
  `standard_conforming_strings = off` doubling backslashes and dropping the score
  to 91/95 until an `E''`-string `replace` restored 95/95 under both settings —
  while the plain `replace(x, '\\', '\')` spelling does not even parse under that
  setting; 14 catalog `AccessShareLock`s and zero partition locks at 1048
  partitions, 39.9-44.9 ms for the masked recipe versus 8.3-9.2 ms for the plain
  split; an unprivileged role read all 2109 rows including bounds for a schema it
  cannot use; `DETACH` erases `relpartbound`; a concurrently dropped partition
  makes `pg_get_expr(…, oid)` return NULL while `pg_get_expr(…, 0)` still
  deparses; the value round trip through the key type was exact in 78/81, the
  exceptions being `boolean`'s `true`/`false` keywords; and a 9600-character bound
  fails at DDL time with `row is too big: size 9304, maximum size 8160` because
  `pg_class` has no TOAST table. Seven open questions were filed, including the
  complete upstream absence of any test that deparses a quoted RANGE bound
  containing a comma, quote, or backslash, the untested foreign-table partition
  case, and expression-key type derivation. The test database and server were
  removed. The page is human-unverified and agent-unverified.

- 2026-08-12: filed [Calibrating a COMMENT-Stored Bytes-per-Table-Tuple REINDEX
  Threshold for Every Non-B-Tree Index in PostgreSQL 12
  (unverified)](v12/questions/indexing/comment-stored-bytes-per-table-tuple-non-btree.md)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42` (12.2).
  Verdict: the scheme calibrates for exactly one of the five non-btree access
  methods. Measured on an isolated 12.2 server over 132 cells (22 insert/update/
  delete workloads x 6 index shapes) with `REINDEX INDEX` as ground truth and
  "worth rebuilding" defined as reclaiming >= 20% of current bytes: GiST
  separates perfectly at any threshold in 20-30% (14 TP / 0 FP / 0 FN / 8 TN)
  and a fresh zero-bloat GiST build drifts only -0.29% to +3.84% across
  25k-1.6M rows; hash (window 8.78-11.11%) and SP-GiST (28.24-32.17%) also score
  100% but only at a fixed row count, because a *freshly built* hash index reads
  -20.31% to +49.42% across the power-of-two bucket staircase (28.071 to 52.634
  bytes/row over 60k-250k rows) and SP-GiST up to +33.08%; GIN needs 50%
  (`fastupdate = off`, still 2 FP) or 75% (on, 18/0/0/4); BRIN has no working
  threshold at all, `REINDEX` reclaiming exactly 0.00% in 22/22 cells while the
  reading ranged -87.50% to +9900.00%. One all-method threshold of 30% scores
  90.2% over 132 cells and 93.6% over the 110 non-BRIN cells. Rank correlation
  with reclaimable bytes: GiST 0.992, hash 0.987, GIN-on 0.974, SP-GiST 0.958,
  GIN-off 0.936, BRIN undefined. Also measured: every access method reads exactly
  `1/(1-f)-1` after a delete of fraction f (11.11/33.33/100/300/900/9900%), so
  deletes carry no index information; `VACUUM` never shrank any index (byte-
  identical sizes in every delete cell); the GIN pending list reads +261.73% and
  `gin_clean_pending_list()` moves it to a *worse* +388.78% (23,232,512 ->
  31,391,744 bytes) while delivering the entire query win (3,779 -> 1,336 blocks,
  11.259 -> 1.393 ms) that the later rebuild did not, and `fastupdate` alone
  changes bytes-per-tuple 2.8x; three hash builds over identical 200k rows give
  34.5293 / 38.0928 / 37.1917 bytes/row because `hashbuild` sizes buckets from
  `estimate_rel_size`; a grown hash index carried 87 unwritten zero pages
  (`pg_relation_size` 5,341,184 vs 4,628,480 bytes allocated per `stat`) and
  `pgstattuple()` refused it; hash's del10 "reclaim" is re-bucketing (768 -> 640
  buckets); BRIN's `pages_per_range` spreads the baseline 6.3x (3/4/19 pages at
  128/8/1) and BRIN churn cost 130 -> 487 query blocks at +0.00% reading; stale
  `reltuples` flips one GiST index between +84.71% and -7.64%; a partial index
  that really grew 80.4% read -5.02% against 44.59% reclaimable; and rebuild cost
  ran GiST 650.8 ms, SP-GiST 292.9, GIN 156.7, hash 120.3, BRIN 19.4. `COMMENT ON
  INDEX` mechanics were verified on the pin (literal-only grammar so a computed
  baseline needs dynamic SQL, `ShareUpdateExclusiveLock` on the index, owner-only
  writes, world-readable, `IS NULL`/`IS ''` both delete the row, preserved by
  plain REINDEX and moved to the new OID by REINDEX CONCURRENTLY, copied onto an
  empty clone by `LIKE INCLUDING ALL`). Eleven open questions were filed,
  including single-platform constants, the fixed 1,000-key GIN fixture, warm
  single-client query measurement, and GiST's non-deterministic builds. The test
  server was stopped and its data directory removed. The page is human-unverified
  and agent-unverified.

- 2026-08-12: removed the v12 question page Calibrating a COMMENT-Stored
  Bytes-per-Index-Row REINDEX Threshold in PostgreSQL 12 (unverified) at the
  user's request, together with its root-index and v12-landing-page entries and
  the closing `indexing` clause of the v12 coverage cell above that described
  it. No surviving page linked or cited it, so no `## Navigation` list changed.
  The three historical coverage notes below that referenced the page now name it
  as plain text. COMMENT-stored index-bloat screening in v12 now runs through
  Detecting Bloat in All Index Types by Storing an Index/Heap Size Ratio in
  COMMENT in PostgreSQL 12 (unverified)
  and Can COMMENT-Stored Table DML Counters Trigger GIN REINDEX at 40% in
  PostgreSQL 12? (unverified),
  and core-SQL B-tree bloat measurement through
  [Measuring B-Tree Index Bloat With Core SQL Only in PostgreSQL 12 (unverified)](v12/questions/indexing/btree-index-bloat-core-sql-only.md).
  The pin `45b88269a353ad93744772791feb6d01bc7e1e42` and every surviving page's
  citations and verification fields are unchanged.

- 2026-08-12: filed [Checking Whether an Index Needs a Rebuild to Enable
  Deduplication After pg_upgrade From PostgreSQL 12 to 17
  (unverified)](v17/questions/indexing/btree-deduplication-after-pg-upgrade.md)
  against unchanged pin `54eeefaedbee0385529f3edf321bb99e49232aaa` (17.10).
  Verdict: after a binary upgrade, every B-tree index carried over from the v12
  cluster is unable to deduplicate, and only a rebuild changes it. Deduplication
  safety is recorded once at build time in the metapage's `btm_allequalimage`;
  `_bt_upgrademetapage` refuses to set it ("Only a REINDEX can set this field"),
  `_bt_metaversion` and `bt_metap` both rely on it reading zero for indexes
  upgraded from 12, and no commit under `src/bin/pg_upgrade` has ever touched
  `allequalimage`. `btm_version` is 4 before and after, so version is not the
  discriminator. The filed core-SQL check reads byte 64 of block 0 with
  `pg_read_binary_file` + `get_byte` (offsets confirmed by compiling `offsetof`
  against the pin's own installed headers: contents at 24, `btm_version` at 28,
  `btm_allequalimage` at 64, v17 metapage `pd_lower` 72) and pairs it with a
  catalog mirror of `_bt_allequalimage`. Measured on three isolated 12.2 -> 17.10
  `pg_upgrade --copy` runs plus one ICU-enabled 17.10 cluster: 21/21 carried-over
  indexes read `pd_lower = 64`, version 4 and the flag false while every 17-built
  index read 72/true; the probe agreed with `pageinspect`'s `bt_metap()` in 75/75
  comparisons; all 21 index files were MD5-identical between the old and new data
  directories; the gate matched the engine's own `DEBUG1` verdict on 19 index
  shapes, the silent case being the `INCLUDE` index whose early `return false`
  skips the `elog`. `REINDEX INDEX CONCURRENTLY` reclaimed 69.1%, 69.0%, 69.0%,
  68.7%, 68.5%, 67.4% and 67.4% on the seven duplicate-heavy indexes, 0.0% on the
  unique and the empty one, and left the five not-equal-image indexes identical to
  the byte; a fresh `deduplicate_items = off` twin measured 22,519,808 bytes,
  exactly the carried-over index's size, against 6,963,200 with deduplication on.
  The savings curve over rows per key was 0.0% / 10.0% / 48.1% / 65.4% / 69.5% /
  67.4% at 1 / 2 / 5 / 20 / 100 / 1000. Also measured: the `deduplicate_items`
  trap (flag true, full 22,519,808 bytes, engine still logging "can safely use
  deduplication"), a carried-over index growing to 3.1x a fresh twin over the same
  200,000 duplicate inserts, `VACUUM FULL`/`CLUSTER` setting the flag while plain
  `VACUUM` does not, `GRANT EXECUTE ON FUNCTION pg_read_binary_file(...)` being
  required and `pg_read_server_files` being neither sufficient nor necessary,
  `relpages`/`reltuples` left at 0 for all 21 indexes until the first `ANALYZE`,
  and `pg_largeobject_loid_pn_index` as the single `pg_catalog` B-tree index the
  upgrade carries over. Nine open questions were filed, including the single-platform
  byte offsets and the unobserved standby/replay case. Two open questions on the v17
  core-SQL bloat page were updated to point at these measurements. All four test
  servers were stopped and their data directories removed, leaving only the scripts
  and captured output under `.wiki-runtime/tmp/dedup-upgrade/`. The page is
  human-unverified and agent-unverified.

- 2026-08-12: extended [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on
  PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md) with a
  proposed single B-tree bloat statement for servers 12 through 17, against
  unchanged pin `54eeefaedbee0385529f3edf321bb99e49232aaa` (17.10). The statement
  runs unchanged on every major in that range and credits deduplication only
  where the catalog proves the engine would: non-unique, `deduplicate_items` on,
  `indnatts = indnkeyatts`, a `pg_amproc` equal-image row at `amprocnum = 4` for
  every key opclass, and no key collation with `collisdeterministic = false`. Its
  posting-list arithmetic is derived from `_bt_load`'s
  `MAXALIGN_DOWN(BLCKSZ * 10 / 100) - sizeof(ItemIdData)` cap (812 bytes),
  `_bt_dedup_save_htid`/`_bt_form_posting`'s `MAXALIGN(base + n * 6)` tuple size,
  and `_bt_buildadd`'s `pgspc + last_truncextra < btps_full` rule, which together
  put 9 posting tuples of 808 bytes on a leaf and model 843 leaves against an
  849-block rebuild for 1,000,000 rows under one key. Key groups come from a
  mixture — the NULL run (NULLs deduplicate because `_bt_keep_natts_fast` treats
  two of them as equal), each `most_common_freqs` entry, then the remaining
  distinct values — and a negative `n_distinct` is credited only for whole-table
  indexes because the fraction is over the table's rows, not a partial
  predicate's subset. Measured on isolated 12.2, 14.23 and 17.10 servers built
  from their own pins (17.10 configured `--with-icu`) with identical fixture DDL
  and `CREATE INDEX CONCURRENTLY` ground truth: 68/68/72 indexes swept over
  133,677/94,910/103,056 blocks in 17.7 to 32.9 ms warm, 0/34/36 credited,
  `expected_blocks` identical to the v12 page's Method A in all 34 scored cells
  on 12.2, and within 5% of a rebuild on 25 of 33 cells on 14.23 and 25 of 35 on
  17.10 against Method A's 14 and 15. `i_dupdel` (10 keys, 90% of 1,000,000 rows
  deleted and vacuumed) reads 89.8% on 14.23 and 17.10 against a true 89.8%, and
  90.0% on 12.2 against a true 89.9%. The statement emits a second
  `bloat_pct_floor` column (one tuple per row) plus a `caveats` column, and
  alerting on the floor scores 4 true positives, 0 false positives and 1 false
  negative on every server, against 2 to 3 false positives for the point estimate
  alone: a healthy 28 MB nondeterministic-collation ICU index reads 88.2% without
  the new conjunct and 0.1% with it, a hot-value skew index whose `n_distinct`
  came back 81,281 against a true 750,001 reads 53.4% point / −20.9% floor and
  0.1% after `SET (n_distinct = -0.75)`, and a table doubled since its last
  `ANALYZE` reads 49.9% with the caveat `row-count sources disagree`. Ten new open
  questions were filed, including that majors 13, 15 and 16 were never run and
  the 5.5% to 8.2% posting-list packing loss that is measured but not modelled.
  All three servers were stopped and their data directories removed. The page
  remains human-unverified and agent-unverified.

- 2026-08-12: extended [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on
  PostgreSQL 17
  (unverified)](v17/questions/indexing/btree-index-bloat-core-sql-only.md) with
  three follow-up sections answering whether that page's deduplication-aware
  sweep works for indexes on a v12 server as well as a v17 one, against unchanged
  pin `54eeefaedbee0385529f3edf321bb99e49232aaa` (17.10). Verdict: yes on both,
  because each v17-specific term is gated on a catalog fact a 12 server cannot
  produce - a `pg_amproc` equal-image row at `amprocnum = 4` (`_bt_allequalimage`
  is the engine's own test, and support numbers are bounded by the access method's
  `amsupport`), the `deduplicate_items` reloption, and the `-1` `reltuples`
  sentinel; the three constructs first ship in `REL_13_0`, `REL_13_0` and
  `REL_14_0` per this checkout's own history (`612a1ab7672`, `0d861bbb702`,
  `3d351d916b2`), none of them an ancestor of `REL_12_2`. Measured by running the
  identical statement on isolated 12.2 and 17.10 servers over the same DDL and
  data: 0 of 32 indexes credited on 12.2 with `expected_blocks` identical to the
  v12 page's Method A in every cell and no miss worse than 4 blocks, against 15 of
  34 credited on 17.10; a 10-distinct-key index with 90% of rows deleted and
  vacuumed reads 90.0% on 12.2 (rebuild 278 blocks) and 90.1% on 17.10 (rebuild
  87) against true bloat of 89.9% and 89.8%, where the uncorrected model would
  have said 67.5% on 17.10. 12.2 refuses the gate even deliberately
  (`ERROR: invalid function number 4, must be between 1 and 3`,
  `ERROR: unrecognized parameter "deduplicate_items"`). Two new findings: an
  `INCLUDE` index with a low-cardinality included column read 78.1% bloat on a
  0%-reclaimable 3853-block index on 17.10 because `_bt_allequalimage` refuses
  INCLUDE indexes outright while the sweep probes only key columns - adding
  `indnatts = indnkeyatts` to the gate makes that cell exact and moves no other
  cell - and on 12.2 the `-1` guard is dead code, so a stale-zero `reltuples`
  after `TRUNCATE` and reload reports 99.9% bloat on a healthy 825-block index
  where 17.10 reports `unmeasured`; a zero-plus-size rule for 12 and 13 servers
  was verified as filed. Both servers were stopped, the test databases dropped,
  and the 17.10 data directory removed. The page remains human-unverified and
  agent-unverified.

- 2026-08-11: rebuilt the v12 COMMENT-stored index-bloat page around the index's
  own row count and renamed it to Calibrating a COMMENT-Stored
  Bytes-per-Index-Row REINDEX Threshold in PostgreSQL 12 (unverified),
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). The approved follow-up prompt is "replace live rows by the
  index `pg_class.reltuples`", so the metric is now
  `pg_relation_size(index) / index reltuples` everywhere and every measurement
  was re-run on a fresh isolated 12.2 server. New source model: three writers
  set an index's `reltuples` and they disagree about units - the AM's build
  result through `index_update_stats()`, `ANALYZE`'s
  `ceil(tupleFract * totalrows)`, and `lazy_cleanup_index()`'s
  `num_index_tuples` gated on `estimated_count`; `ginbuild()` counts extracted
  entries while `ginvacuumcleanup()` substitutes the heap count under an
  explicit XXX, `brinbuild()` counts range summary tuples and
  `brinvacuumcleanup()` recounts them with `include_partial = false`, and
  `btvacuumcleanup()`/`hashvacuumcleanup()` can return NULL so no update
  happens at all. Measured over a new 96-cell matrix (12 workloads x 8 indexes,
  seven capture phases each): the swap is a no-op on ordinary indexes (drift
  identical to four decimals in all 84 non-BRIN cells; index and table
  `reltuples` equal in all 192 plain-`ANALYZE` observations), fixes partial
  indexes (10 of 10 defined cells against the table denominator's 8 of 13 over
  13 partial cells), and disqualifies GIN and BRIN. `drift >= 1.30` scores
  42/1/4/49 (94.8%) over 96 cells and 42/0/4/38 (95.2%) excluding BRIN; the four
  misses are all in-domain churn, where the fork stops growing while a rebuild
  reclaims 26.28% to 56.15%. Named measurements: a 20-keys-per-row GIN index
  recorded 4,200,000 rows for a 400,000-row table, making a post-rebuild
  baseline read drift 10.50 with no bloat; one 24,576-byte BRIN index reported
  0.0123 and 279.2727 bytes per index row at different times; a
  `VACUUM (VERBOSE, ANALYZE)` printed no index line while a partial index's own
  population grew 50%, leaving a sampled 150,710 in place, and the
  `vacuum_cleanup_index_scale_factor = 0` reloption restored an exact 310,000;
  `reltuples::numeric` rounded 20,000,020 to 20,000,000 through
  `float4_numeric()`'s six significant digits; a GIN pending list moved the
  ratio down 32% and then up 74% while its probe ran 674x slower (4.043 ms and
  497 blocks against 0.006 ms and 6); deleted-page bloat gave 28.50% reclaim
  with no query change but 413.33 of planner cost, against low-density bloat at
  49.64% reclaim, half the scan blocks and no wall-clock gain; and a partial
  index's predicate column turned 1,800,000 HOT updates into 0 and quadrupled a
  sibling index while both partial indexes read drift 1.0000. New `wiki_bpr_v3`
  capture and detection SQL with an access-method allowlist, a stored-shape
  check and an empty-index rule was executed on the pin, along with a five-step
  runbook using `REINDEX INDEX CONCURRENTLY`. The isolated server was stopped
  and its data directory, build tree, and fixtures removed. The page is
  human-unverified and agent-unverified.

- 2026-08-11: extended the page then titled Calibrating a COMMENT-Stored
  Bytes-per-Live-Row REINDEX Threshold in PostgreSQL 12, since renamed to
  Calibrating a COMMENT-Stored Bytes-per-Index-Row REINDEX Threshold in
  PostgreSQL 12 (unverified),
  with a comprehensive B-tree partial-index section, against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (PostgreSQL 12.2). The filed
  follow-up prompt asks for that section and for the earlier "the denominator is
  wrong by construction" material to be folded into it. Verdict: keep the +30%
  B-tree trigger but divide by the *index's* own `pg_class.reltuples`. On 13
  partial-index cells measured on a fresh isolated 12.2 server (1,000,000-row
  tables, a 10% `st = 'open'` predicate and a 10% `done_at IS NULL` predicate,
  `REINDEX` size delta as ground truth) the table denominator scored 8 of 13
  while the index denominator scored 11 of 11 cells where it is defined, with a
  clean band from 1.0243 benign to 1.3795 harmful; the two undefined cells are
  the two indexes whose own `reltuples` is 0, which a separate empty-index rule
  catches. The swap is free for non-partial indexes because
  `compute_index_stats()` leaves their `tupleFract` at 1.0, verified as an exact
  match to the table count in all 16 `ANALYZE` runs. Table-denominator failures
  measured: 5.2346 with 0% reclaimable on growth inside the predicate, 2.0000
  with 0% reclaimable on deletion outside it, 1.0000 with 99.64% reclaimable on
  a drained queue index, and 1.0526 with 49.64% reclaimable on scattered
  deletion. New source findings: a partial index's predicate columns enter the
  HOT-blocking bitmap, so two identical tables running identical updates
  recorded 0 versus 1,800,000 HOT updates and a 49.96%-reclaimable sibling
  index while both partial indexes reported drift 1.0000; `_bt_vacuum_needs_cleanup()`
  gates the cleanup scan on *heap* growth, so a `VACUUM` skipped an index whose
  own population had grown 50% because the heap grew 5%; `VACUUM (ANALYZE)`
  writes the exact index count that plain `ANALYZE` samples (102,634 and 99,900
  against exactly 100,000); and `get_relation_info()` estimates a partial
  index's row count instead of pinning it. Two bloat shapes were separated with
  `pgstatindex`: deleted-page bloat (66.59% reclaim, 546 deleted pages, density
  89.18, 1.1% fewer scan blocks, but a 2200.13 planner-cost drop equal to 550
  unread pages x `random_page_cost` 4.0) and low-density bloat (49.64% reclaim,
  density 45.06 to 89.83, 49.6% fewer scan blocks). The plain-`ANALYZE` noise
  floor runs from -3.87%/+2.97% at a 10% predicate to `reltuples = 0` on four of
  six runs at 0.001%. New `wiki_bpr_v2` capture and detection SQL, executed on
  the pin along with a five-step runbook using `REINDEX INDEX CONCURRENTLY`, is
  filed. The isolated server was stopped and its data directory, build tree, and
  fixtures removed. The page remains human-unverified and agent-unverified.

- 2026-08-11: filed the page then titled Calibrating a COMMENT-Stored
  Bytes-per-Live-Row REINDEX Threshold in PostgreSQL 12, since renamed to
  Calibrating a COMMENT-Stored Bytes-per-Index-Row REINDEX Threshold in
  PostgreSQL 12 (unverified),
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). The page stores `pg_relation_size(index)` divided by the
  table's `pg_class.reltuples` in the index `COMMENT` and calibrates the drift
  trigger against `REINDEX` ground truth on an isolated server built from the
  pin, over 88 cells (11 workloads x 8 indexes, one index per access method
  including a second GIN index with `fastupdate = off`) plus twelve targeted
  fixtures. Calibrated triggers are +30% for B-tree, GiST, and hash, +40% for
  GIN after the pending list is flushed, and +60% for contrib `bloom`; SP-GiST
  is not separable because its benign 10x-growth drift of 2.2041 exceeds its
  harmful minimum of 2.0000, and BRIN must not use the signal at all. A single
  +30% to +40% rule scored 43 true positives, 5 false positives, 0 false
  negatives, and 40 true negatives, and was exact on the 66 cells that exclude
  BRIN and SP-GiST. Source findings: no v12 index access method truncates its
  own main fork (SP-GiST's truncation is inside `#ifdef NOT_USED`), so VACUUM
  only records reusable pages through `RecordFreeIndexPage()` and index bytes
  are a high-water mark; hash allocates a whole splitpoint batch and counts the
  resulting file hole; `gistchoose()` breaks ties with `random()`. Measured
  failure modes: drift is exactly 2.0000 for all eight indexes in every delete
  workload while reclaim spans 0.00% to 54.19%; a GIN pending list reads 4.1231
  and `gin_clean_pending_list()` raises it to 4.6182 while removing a 12.0x
  query slowdown; 20-keys-per-row GIN rows read 6.3176 and a rebuild grows the
  index 16.85%; an unsummarized BRIN range set reads 0.1000 while a probe costs
  49,961 blocks against 1,411; a partial index reads 0.3640 with 65.66%
  reclaimable; `reltuples` and `n_live_tup` differ 2x after an unvacuumed delete
  and `pg_stat_reset()` zeroes the latter; 400,000 HOT updates moved no index
  byte; and a 49.96% B-tree space reclaim bought 50% fewer index-only-scan
  blocks but 6% to 10% less time and nothing on a point lookup. Capture and
  detection SQL plus a five-step runbook were executed on the pin; the isolated
  server was stopped and its data directory, build tree, and fixtures removed.
  The page is human-unverified and agent-unverified.

- 2026-08-11: removed the v12 question page Detecting Index Bloat with
  COMMENT-Stored Bytes per Tuple in PostgreSQL 12 (unverified) at the user's
  request, together with its root-index and v12-landing-page entries and the
  three inbound `## Navigation` links on
  Can COMMENT-Stored Table DML Counters Trigger GIN REINDEX at 40% in
  PostgreSQL 12? (unverified),
  [Physical Index Statistics, Tuple Counts, and Bytes per Tuple in PostgreSQL 12 (unverified)](v12/questions/indexing/physical-index-statistics-tuple-counts-and-bytes.md),
  and Proposing and Testing a fillfactor-Corrected pgstattuple_approx Metric
  for Table Heap Bloat in PostgreSQL 12 (unverified).
  The v12 coverage cell above never described the page, so it is unchanged.
  COMMENT-stored index-bloat screening in v12 now runs through Detecting Bloat
  in All Index Types by Storing an Index/Heap Size Ratio in COMMENT in
  PostgreSQL 12 (unverified)
  and the GIN DML-counter page named above. The pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` and every surviving page's
  citations and verification fields are unchanged.

- 2026-08-11: reframed Proposing and Testing a fillfactor-Corrected
  pgstattuple_approx Metric for Table Heap Bloat in PostgreSQL 12 (unverified)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). The filed `## Question` now asks for the metric corrected
  for the table's `fillfactor`, and the page is rebuilt around that correction.
  New source derivation: the `RELOPT_KIND_HEAP` reloption with its 10-to-100
  bounds and `ShareUpdateExclusiveLock`, `RelationGetTargetPageFreeSpace()` =
  `BLCKSZ * (100 - fillfactor) / 100` with its integer truncation, the four
  heap callers of that reserve, `make_new_heap()` reloption inheritance, and
  the documented refusals on partitioned and TOAST tables. New measurements on
  a fresh isolated 12.2 server: a seven-point fillfactor sweep where the
  uncorrected signal reads 0.44 to 91.02 on unbloated tables while the
  corrected one reads 0.02 to 1.79 except 10.16 at `fillfactor = 10`; a
  closed-form residual model from the page-close condition that matches all
  seven within 0.05 points; three bloated fillfactor fixtures at −1.51, −0.78,
  and −1.42 corrected against +14.45 and +34.58 raw; `VACUUM FULL` and
  `CLUSTER` agreeing at 1,250 blocks and 40 rows per page while
  `ALTER COLUMN TYPE` gives 1,316 at a wider row; a reloption lowered after
  load that makes a rewrite grow the table 44.93%, reported as −42.23 only
  when the metric is not clamped at zero; the reloption bound, partitioned,
  TOAST, materialized-view, and lock-level boundary results; and three
  `ANALYZE` runs moving `approx_tuple_count` by −379, +697, and −279 rows,
  which replaces the earlier 18-row live-count claim. The nine-fixture
  accuracy matrix, the emptied-page reconciliation, and the step 1 to 3 worked
  example were re-run and reproduced their filed values, with `d_bloat`'s
  ground truth now recorded as 59.99 and its error as −1.86. The step 2 query
  drops its `greatest(..., 0)` clamp and step 1 gains a `fillfactor` column.
  The page is human-unverified and agent-unverified.

- 2026-08-11: filed Proposing and Testing pgstattuple_approx for Table Heap
  Bloat in PostgreSQL 12 (unverified)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2), the first page in the v12 `storage-and-vacuum` category.
  The page proposes a three-step procedure — catalog screen, then
  `pgstattuple_approx` with a `fillfactor` correction, then confirmation before
  a rewrite — and tests it on an isolated server built from the pinned
  checkout with `autovacuum = off`, using `VACUUM FULL` size reduction as
  ground truth. `pgstattuple_approx` cost 6.9 ms and 42 physical reads against
  `pgstattuple`'s 484.8 ms and 137,932 reads on a 1.08 GB all-visible table,
  and 216.7 ms against 470.8 ms with no visibility map at all. Over nine
  fixtures the corrected estimate ran −3.11 to +1.79 points against ground
  truth on the eight ordinary row shapes; the raw `free + dead` signal instead
  produced a 31.25-point `fillfactor` false positive. Two false negatives are
  quantified: dropped-column bytes (85.40% reclaimable, reported 1.18%) and
  v12's retained line-pointer arrays (2 to 7 points). `pageinspect` and
  `pg_freespacemap` reconciled `approx_tuple_len` to `sum(8192 - fsm)` byte for
  byte and showed emptied pages keeping 58 line pointers and charging 288
  phantom bytes each. A catalog-only estimator was exact on all nine
  well-behaved fixtures and wrong by 21.32, 79.99, and −5698.78 points on
  alignment-padding, stale-statistics, and never-analyzed tables. Also filed:
  the exact `reltuples` dependency of `approx_tuple_count` (a forged
  `reltuples = 7` is returned verbatim when every page is skipped), integer
  truncation in `scanned_percent`, a 15.69-point phantom dead-tuple reading
  during an uncommitted bulk insert, dead-but-not-reclaimable rows under an old
  snapshot, the relation-kind matrix including the refused TOAST relation, and
  the `pg_stat_scan_tables` privilege boundary. Test objects were dropped and
  the isolated server was stopped. The page is human-unverified and
  agent-unverified.

- 2026-08-11: reviewed [Physical Index Statistics, Tuple Counts, and Bytes per
  Tuple in PostgreSQL 12
  (unverified)](v12/questions/indexing/physical-index-statistics-tuple-counts-and-bytes.md)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). Every claim and all 354 source citations were rechecked.
  Corrections: `pgstattuple.tuple_len` includes each item's `MAXALIGN` padding
  because B-tree and hash pass an already-rounded `IndexTupleSize()`, and the
  three `bigint` averages now cast to `numeric`; a bare `block_size` identifier
  became `current_setting('block_size')::bigint`;
  `btm_last_cleanup_num_heap_tuples` is written by `btbulkdelete()` as well as
  cleanup; the `ANALYZE` skip guard is `!inh && !(options & VACOPT_VACUUM)`;
  `PageIndexTupleDeleteNoCompact()` returns the tuple bytes to free space and
  retains only the line pointer; `get_raw_page()` requires superuser and
  rejects partitioned indexes; `brinbulkdelete()` still returns a zeroed
  result struct; `pg_am` has four columns; and the `pgstattuple` regression
  file does call generic `pgstattuple()` on a partitioned-index root as an
  expected failure. Two new Open Questions: the BRIN `revmapNumPages =
  lastRevmapPage - 1` off-by-one quantified against `brincostestimate()`, and
  `bufpage.h`'s "unused in index pages" comment versus GIN's `pd_prune_xid`
  reuse. Roughly 40 citations were repointed or rebounded, including the BRIN
  revmap reader, the GiST VACUUM leaf count, `pg_relpages_v1_5`, and the
  `pgstattuple` regression file's true 119-line extent. The page remains
  human-unverified and agent-unverified: this review re-read source only and
  did not re-execute the page's SQL on a live 12.2 server.

- 2026-08-11: filed [Physical Index Statistics, Tuple Counts, and Bytes per
  Tuple in PostgreSQL 12
  (unverified)](v12/questions/indexing/physical-index-statistics-tuple-counts-and-bytes.md)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). The page inventories shared catalog and relation-size
  values and every core index access method's persistent physical metadata,
  with contrib Bloom as the packaged-extension boundary. It distinguishes
  build-, `ANALYZE`-, and `VACUUM`-written `reltuples` meanings from physical
  page-item counts, gives guarded formulas for allocated bytes per catalog
  unit or scanned data item, and documents why GIN keys/postings and BRIN
  summaries cannot be treated as one tuple per heap row. The page remains
  human-unverified and agent-unverified.

- 2026-08-11: filed Can COMMENT-Stored Table DML Counters Trigger GIN
  REINDEX at 40% in PostgreSQL 12? (unverified)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). The source audit rejects an automatic 40% GIN rebuild
  trigger because the proposed counters are table-wide attempted actions, HOT
  updates require no index entries, partial predicates can skip writes, deletes
  reach GIN only through VACUUM, and GIN operator classes choose an arbitrary
  row-to-key cardinality. Exact-pin tests produced a 40% HOT-update false
  positive with 0.00% rebuild savings and a 1% high-cardinality-delete false
  negative with 99.13% savings. Tested capture and detection SQL stores a
  HOT-adjusted inspection baseline plus table-OID, fixed-row, and
  statistics-reset guards in a reserved index comment, and labels 40% as
  `inspect GIN; do not auto-reindex`. The page remains human-unverified and
  agent-unverified pending local workload calibration, a partial-index design,
  and resolution of a v12 GIN-pending-cleanup documentation discrepancy.

- 2026-08-07: filed Detecting Index Bloat with COMMENT-Stored Bytes per Tuple
  in PostgreSQL 12 (unverified)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). The proposal stores actual main-fork bytes per estimated
  indexed heap row in a versioned index comment, treats `1.0` as the normalized
  baseline, and reports `1.4` as an investigation threshold rather than an
  automatic rebuild verdict. Source review established that plain table
  `ANALYZE` must run after creation and before each comparison because GIN's
  immediate build count is extracted entries while BRIN's is range summaries;
  plain `ANALYZE` rewrites both to an estimated indexed-row denominator. Tested
  capture, detection, and guarded post-rebuild recapture SQL preserves human
  comments and filters non-physical or unsuitable index states. An isolated
  exact-pin run covered B-tree, hash, GiST, SP-GiST, GIN, BRIN, and contrib
  Bloom. BRIN and GIN false-positive fixtures reached drift `5.0` and `137.2`
  while `REINDEX` reclaimed `0.0%`, disproving a universal all-AM threshold.
  The page remains human-unverified and agent-unverified pending production
  calibration and third-party-AM review.

- 2026-08-06: filed Detecting Bloat in All Index Types by Storing an
  Index/Heap Size Ratio in COMMENT in PostgreSQL 17 (unverified)
  against unchanged pin `54eeefaedbee0385529f3edf321bb99e49232aaa`
  (PostgreSQL 17.10), copying the v12 question of the same name and reviewing it
  for v17. Prompt hygiene applied first; the user chose silently corrected
  wording, the copy request itself as the filed `## Question`, a full
  re-measurement on v17, and a since-v12 history section. No v12 number was
  carried over: an isolated 17.10 server (previous pin) built from the pinned checkout with
  `autovacuum = off` reproduced every fixture. A 49-cell matrix of seven
  workloads times seven access methods with `REINDEX TABLE` ground truth scored
  `drift >= 1.40` at 13 true and 3 false positives against `index > heap` at 6
  and 2; the 19 cells in the drift 0.90-1.10 band span -8.4% to 80.0%
  reclaimable. Two findings are new relative to the v12 page and are traced to
  source. First, `hashbuild` sizes the initial bucket array from
  `estimate_rel_size`, so identical 200,000-row data produced 923 blocks on a
  narrow heap, 5,122 on a wide never-analyzed one, and 822 when `ANALYZE` ran
  first — a 6.2x inflated day-zero baseline, which added an `ANALYZE`-first rule
  to Capture discipline. Second, v14's same-VACUUM B-tree page recycling
  (`9dd963ae253`) is present but did not fire on an idle server: the
  delete-and-reload cycle still left B-tree +99.27%, GiST +89.47% and GIN
  +82.72% after one VACUUM, while repeating it against a concurrent
  `txid_current()` consumer populated the FSM and ended at 745 blocks instead of
  1,098, matching the condition stated in `_bt_pendingfsm_finalize`. SP-GiST is
  newly disqualified in these fixtures (fresh ratio drifts 2.2787 over 16x
  growth at 0.0% reclaimable). The since-v12 section attributes nine changes to
  their first release tags, including the 17.1 fix `fee8cb94734`, which stops
  parent index comments propagating onto partition children; the measured v17
  outcome is that an `ALTER COLUMN TYPE` on a partitioned table now leaves child
  baselines empty rather than silently overwriting them with the parent's, so
  the audit query detects the loss. Also filed: a day-zero sweep whose implied
  `index > heap` thresholds span 0.94 to 4444.67, the GIN baseline-1.004900
  fixture, RIC-versus-plain-`REINDEX` byte equality on all seven access methods,
  the four RIC refusal cases, an interrupted-RIC `_ccnew` with no baseline, a
  nine-operation comment durability matrix, lock/ownership/read-visibility
  probes, 300-index survey timings against the `relpages` variant, and three
  verified read-only queries. Test objects were dropped and the isolated server
  was stopped. The page is filed with human `verified: false`, the visible
  `(unverified)` title, and `verified_by_agent: not yet`.
- 2026-08-06: added a decision-rule comparison section to Detecting Bloat in
  All Index Types by Storing an Index/Heap Size Ratio in COMMENT in
  PostgreSQL 12 (unverified)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). Prompt hygiene applied first; the user chose corrected
  wording with no prompt note, the absolute reading `current ratio > 1.0` on
  main forks, full exact-pin measurements, and all seven access methods.
  A fresh isolated 12.2 server with `autovacuum = off` ran a 49-cell matrix of
  seven workloads times seven access methods with `REINDEX TABLE` ground truth:
  `drift >= 1.40` scored 13 true and 1 false positive, `index > heap` scored 6
  and 2. The section proves `index_bytes > heap_bytes` is the drift rule
  `drift > 1 / baseline_ratio`, whose per-index threshold measured 0.94 to 1282
  on one table, a 1367x spread set by heap row width. A day-zero sweep held
  every index's block count constant across heaps of 2,858, 3,847 and 13,334
  blocks while the GIN ratio fell 1.435 -> 1.066 -> 0.308; a fresh-B-tree sweep
  from 0 to 1,000,000 rows fell 2.000 -> 0.266. The question's own premise was
  reproduced on a GIN index with baseline 1.004900, which the absolute rule
  condemns at 0.0% reclaimable the moment it is built and at every later step,
  while drift stayed quiet until a rebuild was worth 38.9%. At the 1.40
  crossing a rebuild reclaimed 25.2-38.9%, GiST stalled at 1.399 with 35.4%
  reclaimable, and the 22 cells near drift 1.00 span -8.5% to 80.0%. Threshold
  sweeps from 1.10 to 1.50 score identically. Added a verified read-only
  two-rule comparison query, five Evidence Map rows on tuple layout, fill
  factors, the empty-index metapage and `reindex_index` locks, and six new
  Open Questions. A further section answers the maintenance process rebuilding
  with `REINDEX INDEX CONCURRENTLY`: on a second isolated server, two
  byte-identical churned 200,000-row tables produced identical rebuilt files
  under RIC and plain `REINDEX INDEX` on all seven access methods, so no score
  moves, and all seven stored baselines survived the swap while every index OID
  changed. The costs that remain are peak storage of old plus new until
  phase 6, a `ShareUpdateExclusiveLock` that conflicts with lazy VACUUM's own,
  four `WaitForLockersMultiple` points, and the transaction-block ban. Four
  measured loop-breakers: a direct RIC on an exclusion-constraint index errors,
  `REINDEX TABLE CONCURRENTLY` skips it with only a `WARNING` so its drift
  climbs forever, a temporary relation silently falls back to the
  non-concurrent path, and a `statement_timeout`-interrupted RIC left a
  baseline-less `_ccnew` that the page's audit query flags. Added six more
  Evidence Map rows, two Context Reviewed bullets, five Open Questions, and
  twelve Source References. Test objects were dropped and both isolated
  servers were stopped. Human `verified: false`, the visible `(unverified)`
  title, and
  `verified_by_agent: not yet` are unchanged because this was a scoped
  follow-up rather than a full page re-audit.
- 2026-08-06: reviewed Detecting Bloat in All Index Types by Storing an
  Index/Heap Size Ratio in COMMENT in PostgreSQL 12 (unverified)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`.
  Reclassified the ratio as an allocation-growth screen; separated index growth,
  rebuild-reclaimable fraction, and excess over rebuilt size; corrected ordinary
  VACUUM, BRIN revmap, SP-GiST redirect-XID, GIN pending-list, HOT, lock,
  `relpages`, dump/restore, and `CREATE TABLE ... LIKE INCLUDING ALL` claims;
  and added the catalog/generated-header boundary. Replaced the unsafe audit cast
  and zero-heap filter with exact-pin-tested queries. Reran the 200k-row cycle at
  one, two, and three post-delete VACUUM passes: GIN is 4,101 -> 7,482 blocks
  (+82.44%) with 4,100 entry pages, and SP-GiST is +0.83% in every arm. Updated
  both indexes and the v12 coverage row. Human `verified: false`, the visible
  `(unverified)` title, and `verified_by_agent: not yet` remain unchanged because
  the non-cycle historical measurement tables were not all reproduced.
- 2026-08-06: added a delete-and-reload cycle test section to Detecting Bloat
  in All Index Types by Storing an Index/Heap Size Ratio in COMMENT in
  PostgreSQL 12 (unverified)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). Prompt hygiene applied first; the user chose silently
  corrected wording, all seven access methods, fresh ascending reload keys, and
  results plus a runnable script. A second isolated `autovacuum = off` 12.2
  server carried one 200k-row table with all seven indexes through capture,
  `VACUUM`, full delete, `VACUUM`, and a 200k-row reload. The heap returned to
  exactly 3,847 blocks, so ratio drift equalled raw index growth digit for digit
  on all seven access methods and equalled `REINDEX` ground truth on six; hash's
  0.86% gap resolved to 7 overflow pages at an identical `maxbucket = 767`. One
  post-delete `VACUUM` left B-tree +99.27%, GiST +89.47% and GIN +82.72%;
  two- and three-`VACUUM` arms plus an independent replicate split the access
  methods along the `RecentGlobalXmin` recyclability gate, and `gin_metapage_info`
  showed 600,000 entries still on 4,101 entry pages after three passes. The
  published script was re-run standalone on a fresh database and reproduced every
  filed number. Test objects were dropped and the isolated server was stopped.
  `verified_by_agent` stays `not yet` because this was a scoped addition rather
  than a full page re-audit; human `verified: false` and the visible
  `(unverified)` title are unchanged.
- 2026-08-06: filed Detecting Bloat in All Index Types by Storing an
  Index/Heap Size Ratio in COMMENT in PostgreSQL 12 (unverified)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). Prompt hygiene applied first; the user chose corrected
  wording, a bare-ratio comment payload, source plus exact-pin tests, and
  read-only filed SQL. An isolated 12.2 server built from the pinned checkout
  measured seven access methods (btree, hash, gist, spgist, gin, brin, contrib
  bloom) across a three-scale fresh-ratio invariance sweep, a seven-point
  hash/B-tree sawtooth sweep, and six workload fixtures with `REINDEX` and
  `VACUUM FULL` ground truth, plus a nine-operation COMMENT durability matrix,
  lock/ownership/read-visibility probes, and 300-index survey timings. Test
  objects were dropped and the isolated server was stopped. The page is filed
  with human `verified: false`, the visible `(unverified)` title, and
  `verified_by_agent: not yet`.
- 2026-08-06: removed the v17 question page How a GIN Index Becomes Bloated in
  PostgreSQL 17, and How to Measure It (unverified) at the user's request,
  together with its root-index, v17-landing-page, and coverage-cell entries and
  both inbound references on [Planner Penalties for Bloated Indexes in
  PostgreSQL 17 (unverified)](v17/questions/query-planning/bloated-indexes-query-planner.md):
  the `## Related Pages` entry, and one prose cross-reference that now points at
  that page's own follow-up section on when a GIN index is discarded and a
  B-tree used instead. With the v12 page of the same name removed earlier the
  same day, no version carries a dedicated GIN-bloat page; v17 GIN behavior at
  the planner level remains on that planner page, and the GIN contrib surface
  remains in [PostgreSQL 17 Contrib Extensions
  (unverified)](v17/questions/server-administration/contrib-extensions.md). The
  pin `54eeefaedbee0385529f3edf321bb99e49232aaa` and every surviving page's
  citations and verification fields are unchanged.
- 2026-08-06: removed every remaining `pgstatindex` sampling question page at
  the user's request: Proposing a Sampling pgstatindex Variant for PostgreSQL 17
  (unverified), Proposing a Sampling pgstatindex Variant for PostgreSQL 18
  (unverified), and Why pgstatindex Cannot Use pgstattuple_approx-Style
  Approximation in PostgreSQL 18 (unverified). Removed their root-index and
  version-landing-page entries, the one inbound `## Navigation` link on
  How a GIN Index Becomes Bloated in PostgreSQL 17, and How to Measure It
  (unverified), and the one inbound
  `## Related Pages` link on [Planner Penalties for Bloated Indexes in
  PostgreSQL 17 (unverified)](v17/questions/query-planning/bloated-indexes-query-planner.md).
  Also stripped the sampling clauses from the v17 and v18 coverage cells above,
  so no version now advertises a sampling `pgstatindex` page. With the v12 pages
  removed earlier the same day, the wiki carries no sampling `pgstatindex`
  coverage at all. v18 keeps [Computing and Storing avg_leaf_density During
  (Auto)VACUUM of a B-Tree Index
  (unverified)](v18/questions/indexing/avg-leaf-density-during-vacuum.md), and
  v12 keeps [How pgstatindex Calculates B-Tree Index Statistics in PostgreSQL 12
  (unverified)](v12/questions/indexing/how-pgstatindex-calculates-information.md).
  The pins `54eeefaedbee0385529f3edf321bb99e49232aaa` and
  `6cb307251c5c6261286c1566496920976640108e` and every surviving page's
  citations and verification fields are unchanged.
- 2026-08-06: removed the v12 question page Proposing a Sampling pgstatindex
  Variant for PostgreSQL 12 (unverified) at the user's request, together with
  its root-index, v12-landing-page, and coverage-summary entries and the one
  inbound `## Navigation` link on
  [How pgstatindex Calculates B-Tree Index Statistics in PostgreSQL 12 (unverified)](v12/questions/indexing/how-pgstatindex-calculates-information.md).
  v12 now carries no sampling `pgstatindex` proposal. The exact full-scan
  function stays on that page, and contrib-free bloat estimation stays in
  [Measuring B-Tree Index Bloat With Core SQL Only in PostgreSQL 12 (unverified)](v12/questions/indexing/btree-index-bloat-core-sql-only.md).
  The v17 and v18 sampling `pgstatindex` pages are unaffected. The pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` and every surviving page's
  citations and verification fields are unchanged.
- 2026-08-06: removed the v12 question page Proposing a Sampling pgstatginindex
  Variant for PostgreSQL 12 (unverified) at the user's request, together with
  its root-index, v12-landing-page, and coverage-summary entries. No surviving
  page linked to it, so no navigation section changed. v12 now has no GIN
  page-accounting page; GIN behavior at the planner level remains in
  [Planner Penalties for Bloated Indexes in PostgreSQL 12 (unverified)](v12/questions/query-planning/bloated-indexes-query-planner.md).
  The B-tree page
  Proposing a Sampling pgstatindex Variant for PostgreSQL 12 (unverified)
  and the v17/v18 sampling `pgstatindex` pages are unaffected. The pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` and every surviving page's
  citations and verification fields are unchanged.
- 2026-08-06: removed the v12 question page How a GIN Index Becomes Bloated in
  PostgreSQL 12, and How to Measure It (unverified) at the user's request,
  together with its root-index, v12-landing-page, coverage-summary, and
  cross-page navigation entries. v12 GIN coverage now runs through
  Proposing a Sampling pgstatginindex Variant for PostgreSQL 12 (unverified),
  with GIN-versus-B-tree planner behavior in
  [Planner Penalties for Bloated Indexes in PostgreSQL 12 (unverified)](v12/questions/query-planning/bloated-indexes-query-planner.md).
  The v17 page How a GIN Index Becomes Bloated in PostgreSQL 17, and How to
  Measure It (unverified) is unaffected. The pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` and every surviving page's
  citations and verification fields are unchanged.
- 2026-08-06: filed every question page under a category directory. All 54
  question pages moved from `wiki/vNN/questions/<page>.md` to
  `wiki/vNN/questions/<category>/<page>.md`, across six closed,
  version-identical categories: `query-planning`, `indexing`,
  `storage-and-vacuum`, `replication-and-wal`, `observability`, and
  `server-administration`. The same question basename takes the same category
  in every version, so cross-version coverage comparison is a directory diff.
  Page-relative links on this page were rewritten to match. Coverage, pins,
  citation targets, and verification fields are unchanged; see
  `MANDATORY Question Categories` in `AGENTS.md`.
- 2026-08-06: removed the v12 question page A Heuristic to Detect B-Tree Index
  Bloat in PostgreSQL 12 (unverified) at the user's request, together with its
  root-index, v12-landing-page, and cross-page navigation entries. v12 B-tree
  bloat coverage now runs through [Measuring B-Tree Index Bloat With Core SQL
  Only in PostgreSQL 12
  (unverified)](v12/questions/indexing/btree-index-bloat-core-sql-only.md), [How
  pgstatindex Calculates B-Tree Index Statistics in PostgreSQL 12
  (unverified)](v12/questions/indexing/how-pgstatindex-calculates-information.md), and
  [Planner Penalties for Bloated Indexes in PostgreSQL 12
  (unverified)](v12/questions/query-planning/bloated-indexes-query-planner.md). The pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` and every surviving page's
  citations and verification fields are unchanged.
- 2026-08-06: answered a filed follow-up on [Measuring B-Tree Index Bloat With
  Core SQL Only in PostgreSQL 12
  (unverified)](v12/questions/indexing/btree-index-bloat-core-sql-only.md) against
  unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42` (PostgreSQL 12.2).
  Prompt hygiene applied first; the user chose corrected wording, the same page,
  bloat-relevant `pgstatindex` columns only, and a wide matrix with repeats.
  Built a second isolated 12.2 server carrying 9 bloat types (fresh, scattered
  delete, range delete, random-order insert, all-duplicate, vacuumed churn,
  unvacuumed churn, `LP_DEAD`, stale-catalog) at 200k/500k/1000k rows, each
  table carrying a non-partial and a partial index over the same key, for 54
  indexes; delete patterns use moduli 7 and 11 against a `id % 5 = 0` predicate
  so the partial index loses the same proportion of entries. Against a real
  `CREATE INDEX CONCURRENTLY` rebuild the filed catalog model was exact in 39 of
  54 cells, within 5 blocks in 47, within 0.8 percentage points in 48, and
  wrong only on 6 cells. The index-only-scan census reproduced
  `pgstatindex.leaf_pages` exactly in all 36 cells that passed the
  `Heap Fetches: 0` precondition (partial and non-partial alike),
  `avg_leaf_density` to within 0.04-0.15 points, and `blocks - leaf_est` matched
  `internal + deleted + half-dead + metapage` exactly in all 36, recovering 2330
  deleted pages within one page. Scored head to head as rebuild-size predictors,
  `ceil(leaf_pages * avg_leaf_density / fillfactor) + internal_pages + 1` lost to
  the core-SQL model in 16 of 18 type/kind cells, reaching 994.4% error on the
  `LP_DEAD` fixture where `pgstatindex` reports a healthy-looking 90.06 density
  on a 2745-block index that rebuilds to 251 blocks, because `PageGetFreeSpace`
  counts dead and `LP_DEAD` entries as used. Isolated the one large model
  failure to partial indexes on tables deleted without VACUUM or ANALYZE (510
  blocks, 92.6 points, reporting 0.0% to −2.0% bloat against a true 89.3-90.6%),
  because `pg_stat_all_tables.n_live_tup` counts the whole table and cannot
  substitute for a partial index's `reltuples`; a plain `ANALYZE` cut that error
  to at most one block, the residual being ANALYZE's sampled
  `tupleFract * totalrows` (18,337 against a true 18,181). All 97 citations were
  machine-audited with 0 broken ranges. Test objects were dropped, the isolated
  server was stopped, and human `verified: false`, the visible `(unverified)`
  title, and `verified_by_agent: not yet` are unchanged because this was a
  scoped follow-up.
- 2026-08-06: filed [Measuring B-Tree Index Bloat With Core SQL Only in
  PostgreSQL 12
  (unverified)](v12/questions/indexing/btree-index-bloat-core-sql-only.md) against
  unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42` (PostgreSQL 12.2).
  Prompt hygiene applied first; the user chose corrected wording, a new question
  page, source plus exact-pin tests, and permission to include write/DDL rebuild
  probes. Established from source that core v12 exposes no SQL-callable page or
  FSM reader at all and that `pgstattuple`, `pageinspect`, `pg_freespacemap`,
  and `amcheck` all default to `superuser = true` because their control files
  omit the field, then derived a closed form for the size a rebuild would
  produce: `_bt_pagestate` sets the leaf threshold to
  `BLCKSZ * (100 - fillfactor) / 100`, `_bt_blnewpage` pre-reserves the high-key
  line pointer, and `_bt_buildadd` closes a page when `PageGetFreeSpace()` falls
  below the threshold, giving
  `tuples_per_leaf = floor((BLCKSZ - 48 - floor(BLCKSZ * (100 - ff) / 100)) / (MAXALIGN(hoff + data) + 4))`.
  One isolated 12.2 server with 15 fixtures priced four core-only methods
  against an actual `CREATE INDEX CONCURRENTLY` rebuild: the 26.7 ms catalog
  sweep matched the rebuilt block count exactly on 10 of 14 indexes, within 2
  blocks on 3 more, and by −4.6% on a 2-to-81-character text key, which a
  `pg_column_size` measurement (57.000 bytes over a full scan, 56.893 from a 1%
  `BERNOULLI` sample, against the catalog-derived 60) corrected to +0.32%. The
  `EXPLAIN (ANALYZE, BUFFERS)` index-only-scan census reproduced
  `pgstatindex.leaf_pages` exactly on all 12 fixtures with `Heap Fetches: 0`
  (2736 − 3 = 2733 on the control) and rebuilt `avg_leaf_density` to within 0.03
  to 0.14 points on 11 of them, with no contrib installed. Recorded six measured
  failure modes: stale `pg_class.reltuples` reporting 0.0% on an index whose
  rebuild goes 2745 → 276 blocks until `pg_stat_all_tables.n_live_tup` is
  substituted; an all-duplicate index that a rebuild *grows* from 1291 to 1376
  blocks because splits used `BTREE_SINGLEVAL_FILLFACTOR` 96 while a sorted
  build packs to 90, correctly predicted as −6.4%; a random-insert index
  permanently at 27.0%; a range-deleted index whose `avg_leaf_density` reads a
  healthy 89.83 while 2330 of 2745 blocks are deleted pages; a variable-width
  key mispriced by one MAXALIGN of an average; and an unvacuumed index whose
  300,000 heap fetches inflated the census from 3279 to 8452 leaf pages. Also
  documented `VACUUM VERBOSE`'s exact per-index page census, the no-op-VACUUM
  gap from `_bt_vacuum_needs_cleanup`, and `pg_relation_size(idx,'fsm') > 0` as
  a free deleted-page flag that was non-zero for exactly the one fixture with
  deleted pages. All 95 citations were machine-audited against the pinned source
  with 0 broken ranges, and all five filed SQL blocks ran verbatim on the pinned
  build. New test objects were dropped, the isolated server was stopped, and
  human `verified: false`, the visible `(unverified)` title, and
  `verified_by_agent: not yet` are unchanged pending a claim-by-claim review.
- 2026-08-04: answered a filed follow-up on Proposing a Sampling
  pgstatginindex Variant for PostgreSQL 12 (unverified) against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). Prompt hygiene applied first; the user chose corrected
  wording, source plus exact-pin tests, and concrete new wasted-space output
  fields rather than a diagnostic-only answer. Established the central
  distinction from source: the function can measure free space but not wasted
  space, because GIN has no `fillfactor` (`ginoptions` parses only `fastupdate`
  and `gin_pending_list_limit`) and `entrySplitPage` equalizes entry pages by
  data size with no sorted-insert case, so ~50% free is the structural steady
  state. Four healthy, never-deleted fixtures measured 49.54-49.66% free, and
  a sibling index built over identical rows was byte-identical to the original
  (412 blocks, 50.46% density, same 1,688,200 used bytes), so a rebuild would
  return zero bytes against a reported 49.66% free. Proposed two exact fields
  (`pending_space`, `total_space`) and four estimates (`approx_free_space`,
  `approx_free_percent`, `approx_recyclable_pages`, `approx_recyclable_space`)
  on the `pgstathashindex` model of counting whole unused pages as free and
  excluding bookkeeping pages from the denominator, reading the delete XID out
  of `pd_prune_xid` to split recyclable from stuck pages. The census's
  recyclability verdict matched VACUUM's own `pages_free` and `pg_freespace`
  exactly on all seven fixtures (465, 168 and 40 blocks at avail 8160, zero
  elsewhere), and the two deletion paths were distinguishable on disk
  (`prune_xid = 0` for 393 drained pending pages against 522 and 518 for
  posting pages deleted by `ginDeletePage`). Recorded the hard limits with
  measurements: deleting 360,000 of 400,000 rows without VACUUM moved not one
  output field while `pgstattuple` reported 75.13% dead heap tuples; entry
  tuples for keys that lost every TID survive VACUUM, 4,000 retained where a
  fresh build has 2,000, with the fork never shrinking; and a 246-page pending
  list at 99.6% density was 30.98% of one index yet left `free_percent`
  indistinguishable from a healthy index's. 1,800 further seeded runs plus
  nine full-sample checks established full-sample equivalence on every new
  field, `free_percent` within 0.25 points of truth from 137 of 13,672 pages,
  a worst case of 9.72 points on a 308-page index, and a 60% alarm threshold
  classifying bloated versus healthy correctly in 800 of 800 runs inside a
  measured 51.22-to-62.02 gap, with an empty index as the one false positive.
  Four sibling-index rebuilds priced the fields honestly: of the bytes raw free
  space reported, only 97.7%, 91.4%, 70.0% and 0.0% materialized as recovered
  bytes, while a baseline-corrected form predicted 96.2-98.5% of them. All 292
  citations on the page were machine-audited against the pinned source with 0
  errors across 55 files, and the filed census prototype ran verbatim and
  reproduced the recorded numbers. New test objects were dropped, the isolated
  server was stopped, and human `verified: false`, the visible `(unverified)`
  title, and `verified_by_agent: not yet` are unchanged because this was a
  scoped follow-up. `scripts/wiki_lint` reports 0 errors and 0 warnings.
- 2026-08-04: filed Proposing a Sampling pgstatginindex Variant for PostgreSQL
  12 (unverified) against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2), scoped to GIN only and derived from the existing v12 B-tree
  sampling proposal. Prompt hygiene applied first; the user chose corrected
  wording, a GIN-native page-class contract, exact-pin tests in addition to
  source, and a GIN-specific sample policy rather than the B-tree page's
  100 MiB / 10% floor. Established that v12 offers no physical GIN page
  accounting at all (`pgstattuple()` rejects GIN, `pgstatindex` and
  `pgstathashindex` reject it by access method, `pgstatginindex` reads only
  block 0, and every `pageinspect` GIN function takes one caller-supplied raw
  page), then documented the full flag taxonomy with the ordering trap that
  `GinPageSetDeleted` ORs `GIN_DELETED` onto a posting page's existing
  `GIN_DATA`/`GIN_LEAF` bits while `shiftList` overwrites a drained pending
  page's flags to exactly `GIN_DELETED`; the three per-class capacity
  denominators (8160 entry/list, 8152 data); the data-page `pd_lower`/`maxoff`
  traps; and that GIN never truncates the main fork. Designed three
  GIN-specific rules — an exact pending stratum from the real-time metapage
  counters, a post-stratified expansion over the exactly-known non-pending
  stratum, and a metapage-derived sample floor with an explicit cap — and
  recorded that nothing in v12 samples an index, the only `BlockSampler` caller
  being the table-AM-bound `acquire_sample_rows`. Exact-pin measurements on one
  isolated 12.2 server used seven fixtures (a 106.82 MiB entry-only control, a
  68.57 MiB mixed index carrying all six classes at once, a 246-page pending
  list, a 41.1%-deleted posting-tree index, a small healthy index, a partial
  index, and an empty index) and 6,100 seeded runs: full-sample equivalence held
  on all seven; post-stratification cut the `entry_leaf_pages` standard
  deviation from 46.6 to 6.8 at a 31% pending share and removed a low bias
  (544.0 versus 537.1 against a truth of 544), and from 227.8 to 149.0 at 4.5%;
  entry-leaf density at 1% coverage reproduced 50.44% with 0.00 maximum error
  over 100 seeds; and a one-page class returned `NaN` in 88 of 100 runs.
  Recorded an objective negative result: the page's own first proposal, a flat
  50-page absolute floor, lost to the B-tree size-based rule — an 88-page sample
  missed a 12-page posting-tree-internal class in 87 of 100 runs against 32 for
  the 878-page B-tree rule — so the floor was replaced by the metapage-derived
  one, which reached 18.52% of the index against a requested 1% and still missed
  the class 6 times in 100. Quantified four distinct metapage misreports
  (deleted-but-unrecyclable pages hidden inside `nDataPages`, recyclable ones
  vanishing from every class so 41.1% of one index's blocks became invisible,
  pending pages counted nowhere, and `nTotalPages` reading 548 against 794 live
  blocks), plus a VACUUM that flushed a 393-page pending list and *grew* the
  index from 8,777 to 9,325 blocks with 465 deleted pages left behind. Verified
  the exact pending-list walk and every prototype error path, including that a
  B-tree index is rejected only accidentally by `gin_metapage_info`'s
  `flags == GIN_META` check. All 219 citations were machine-audited against the
  pinned source with 0 errors across 48 files; human `verified: false`, the
  visible `(unverified)` title, and `verified_by_agent: not yet` are unchanged
  pending a claim-by-claim review. `scripts/wiki_lint` reports 0 errors and 0
  warnings.
- 2026-08-04: answered a filed follow-up on [Planner Penalties for Bloated
  Indexes in PostgreSQL 17
  (unverified)](v17/questions/query-planning/bloated-indexes-query-planner.md) against
  unchanged pin `54eeefaedbee0385529f3edf321bb99e49232aaa` (PostgreSQL 17.10).
  Prompt hygiene applied first; the user chose corrected wording, source plus
  exact-pin tests, and a `## Follow-Up` section on the existing v17 page rather
  than a new page. Established from source that v17 discards a GIN index at
  three separate gates, only the last of which is cost: clause matching
  (`op_in_opfamily()` in `match_opclause_to_indexcol()`, with
  `get_index_clause_from_support()` as the only escape hatch, and the four core
  `pg_amop.dat` GIN families carrying no `<`/`<=`/`>=`/`>`); plan shape from
  GIN's AM flags (`amgettuple = NULL`, `amcanorder`/`amcanorderbyop` false,
  `amcanreturn = NULL`, `amsearchnulls`/`amsearcharray`/`amcanparallel` false),
  which removes plain index scans, `ORDER BY` pathkeys, index-only scans,
  `IS NULL`, native `IN (...)`, and parallel index scans; and cost, where
  `gincostestimate()` charges both `random_page_cost` and
  `DEFAULT_PAGE_CPU_MULTIPLIER * cpu_operator_cost` for every pending, entry and
  data page with no tree-height charge, after which `add_path()` fuzzy dominance
  and `choose_bitmap_and()` drop the loser. Also documented the 4X
  stale-metapage-statistics fallback and the trap that
  `gin_clean_pending_list()` leaves `nTotalPages` stale, the keyless
  full-index path a partial GIN index can still yield through `amoptionalkey`
  and the `indexQuals == NIL` branch, the four `CREATE INDEX`/`CLUSTER`
  rejections, and where GIN still wins. Recorded one v17-specific correction
  found by checking rather than carrying over the v12 answer: a bare boolean
  `Var` *does* match a `btree_gin` bool opclass, because `IsBooleanOpfamily()`
  falls back to `op_in_opfamily(BooleanEqualOperator, ...)` for non-built-in
  opfamilies and `match_boolean_index_clause()` rewrites the clause. Exact-pin
  measurements on one isolated 17.10 server (previous pin) priced the same `n = 42` predicate
  at `12.97` through a `btree_gin` GIN index and `4.52` through a B-tree on a
  single table with literally identical statistics (the other index dropped
  inside a rolled-back transaction), with both closed forms reproduced in SQL to
  the cent (`12.9725` and `4.5225`), even though the GIN index was 279 blocks
  against the B-tree's 280; reproduced B-tree wins on `BETWEEN`
  (`67.15` vs `44.31`), `n < 20` (`28.63` vs `8.89`) and `IN (1,2,3)`
  (`30.10` vs `13.57`); proved the three no-path cases with `disable_cost`-priced
  sequential scans; showed a 982-page `fastupdate` pending list moving GIN's
  index cost from `13.80` to `4187.83` so the planner dropped it from the
  `BitmapAnd` and demoted `tsv @@ …` to a `Filter`, with
  `gin_clean_pending_list()` returning exactly `982`; recovered the charged page
  count exactly in five separate states through a two-`random_page_cost` probe
  (`3.00`, `3.00`, `985.00` = 982 pending + 2 entry + 1 data page under the
  invented-statistics branch, `4.00`, and `1001.00` on a 10-block keyless
  partial index); reproduced all four AM rejection messages and the live
  `amutils` property matrix; and measured a multicolumn `gin (tsv, cat)` index
  beating the `BitmapAnd` at `21.55` versus `183.18`, confirming the
  `btree_gin` documentation's own claim. Two filed diagnostic SQL blocks ran
  verbatim against objects literally named `my_table`, `my_col` and
  `my_gin_index`, reporting `pending_pct_of_index = 72.57` and `303.00` charged
  pages of which 246 were pending. Recorded the explicit absence of any
  upstream GIN-versus-B-tree plan comparison and of any `gincostestimate()`
  test coverage, plus five new `## Open Questions` including a `BitmapAnd`
  outcome that was not stable across two runs. All 142 citations on the page
  were machine-audited against the pinned source; human `verified: false`, the
  visible `(unverified)` title, and `verified_by_agent: not yet` are unchanged
  because this was a scoped follow-up, not a fresh full-page claim audit.
  `scripts/wiki_lint` reports 0 errors and 0 warnings.
- 2026-08-04: filed [Planner Penalties for Bloated Indexes in PostgreSQL 17
  (unverified)](v17/questions/query-planning/bloated-indexes-query-planner.md) against
  unchanged pin `54eeefaedbee0385529f3edf321bb99e49232aaa` (PostgreSQL 17.10).
  Prompt hygiene applied first; the user chose corrected wording, exact-pin
  empirical tests in addition to source, and a new standalone v17 page
  cross-linked to the existing v12 page. Established from source that v17 has
  exactly four bloat-sensitive planner inputs, all filled by
  `get_relation_info()`: `IndexOptInfo.pages` (a live
  `RelationGetNumberOfBlocks()` answer for a non-partial index,
  `estimate_rel_size()`'s `pg_class` density for a partial one),
  `IndexOptInfo.tree_height` from `_bt_getrootheight()`'s `btm_fastlevel`, the
  `index_pages` argument threaded into `index_pages_fetched()` and
  `compute_parallel_worker()`, and the v17-only descent clamp
  `num_sa_scans = Min(num_sa_scans, ceil(index->pages * 0.3333333))`. Recorded
  that `pg_class` carries no density or fragmentation column, that
  `pgstatindex`'s `avg_leaf_density` and `leaf_fragmentation` are computed from
  live leaf pages only and are read by nothing on the cost path, and that only
  B-tree, hash, GiST and SP-GiST route through `genericcostestimate()`.
  Catalogued eight bloat shapes with a per-query-shape sensitivity matrix.
  Built the since-v12 section from the checkout's own history: `git log -L`
  bounded by `REL_12_0..HEAD` plus full-function diffs showed
  `index_pages_fetched()` and `cost_index()` are byte-identical and that only
  five commits touched `btcostestimate` (three cosmetic), and
  `git tag --contains` attributed v13 `0d861bbb702`, v14 `d168b666823` /
  `9dd963ae253` / `5100010ee4d` / `1e55e7d1755` / `3499df0dee8` /
  `3d351d916b2`, v16 `eb5c4e953bb` / `cd9479af2af` / `3c569049b7b`, and v17
  `5bf748b86bc` / `9391f71523b` to their first release tags, with the in-tree
  docs and nbtree README supplying their own "prior to PostgreSQL 14" and
  "PostgreSQL 14 added" boundaries. Exact-pin measurements on one isolated
  17.10 server reproduced a closed-form cost prediction from
  `(pages, tuples, fastlevel)` to the cent (`123144.43` exact), an identical
  `4.44` point lookup across a 2,745-block/90.06% index and its
  26,411-block/9.62% twin, a `1428.00` cost gap equal to exactly
  `357 * random_page_cost` between 49.73% and 0% `leaf_fragmentation` with zero
  residual, two 2,745-block indexes over the same 100,000 rows both priced at
  `12730.42` while `avg_leaf_density` read 9.27% versus a healthy-looking
  89.18% (the latter hiding 2,465 deleted pages), a forged
  `pg_class.relpages = 1` that left a non-partial index's cost unchanged at
  `25528.42` while forging a partial index's `reltuples` moved it from
  `24140.12` to `23140.29`, a `cpu_operator_cost = 1` run isolating the height
  charge to exactly `50.00`, a `Seq Scan` plan flip at 25% selectivity, an
  index dropped from a `BitmapAnd` with its qual demoted to a `Filter`, 4
  versus 6 parallel workers, a SAOP descent plateau at exactly 3 versus 19,
  852 versus 2,749 blocks with `deduplicate_items = off` (cost gaps `68.00`
  and `7516.00` matching page arithmetic exactly), and 583 versus 1,174 blocks
  of version-churn growth without and with a held `REPEATABLE READ` snapshot.
  Recorded the explicit test absence (`src/test` has no reference to
  `tree_height`, `btcostestimate`, or `genericcostestimate`; the only in-tree
  `pgstatindex` test runs on an empty index and expects `NaN`). Human
  `verified: false`, the visible `(unverified)` title, and
  `verified_by_agent: not yet` are unchanged pending a claim-by-claim review.
  `scripts/wiki_lint` reports 0 errors and 0 warnings.
- 2026-08-04: answered a filed follow-up on [Planner Penalties for Bloated
  Indexes in PostgreSQL 12
  (unverified)](v12/questions/query-planning/bloated-indexes-query-planner.md) against
  unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42` (PostgreSQL 12.2).
  Prompt hygiene applied first; the user chose corrected wording ("When might a
  GIN index be discarded by the query planner and a B-tree used instead?"),
  source-plus-exact-pin-tests scope, and normalization of the page's
  `## Answer Up Front` heading to `## Answer` plus a new `## Contents` table of
  contents. Established from source that v12 discards a GIN index at three
  separate gates, only the last of which is cost: clause matching
  (`op_in_opfamily()` in `match_opclause_to_indexcol()`, with
  `get_index_clause_from_support()` as the only escape hatch, and the core
  `pg_amop.dat` GIN families carrying no `<`/`<=`/`>=`/`>`); plan shape from
  GIN's AM flags (`amgettuple = NULL`, `amcanorder`/`amcanorderbyop` false,
  `amcanreturn = NULL`, `amsearchnulls`/`amsearcharray`/`amcanparallel` false),
  which removes plain index scans, `ORDER BY` pathkeys, index-only scans,
  `IS NULL`, native `IN (...)`, and parallel index scans; and cost, where
  `gincostestimate()` charges `random_page_cost` for every pending, entry, and
  data page with no descent shortcut, then `add_path()` fuzzy dominance and
  `choose_bitmap_and()` drop the loser. Also documented the 4X
  stale-metapage-statistics fallback, the keyless full-index path a partial GIN
  index can still yield through `amoptionalkey` and
  `GIN_SEARCH_MODE_EVERYTHING`, the four `CREATE INDEX` AM rejections, and where
  GIN still wins. Exact-pin measurements on an isolated 12.2 server priced the
  same `n = 42` predicate at `12.22` through a `btree_gin` GIN index and `4.65`
  through a B-tree on one table with identical statistics, even though the GIN
  index was 279 pages against the B-tree's 826; reproduced B-tree wins on
  `BETWEEN` (`50.68` vs `15.10`), `n < 20` (`28.69` vs `13.11`), `IN (1,2,3)`
  (`28.67` vs `13.94`), `ORDER BY … LIMIT 10` (`8045.40` vs `1.09`),
  index-only scan (`123.74` vs `4.95`), and `IS NULL` (`5343.10` vs `8.43`);
  proved the three no-path cases with `disable_cost`-priced sequential scans at
  `10000000000.00`; showed a 1177-page `fastupdate` pending list moving GIN's
  index cost from `12.45` to `4720.55` so the planner dropped it from the
  `BitmapAnd` and demoted `tsv @@ …` to a `Filter`; and verified the page charge
  exactly, with `pgstatginindex` reporting 393 pending pages,
  `(1588.55 - 397.55) / 3 = 397` pages charged at two `random_page_cost`
  settings, and `gin_clean_pending_list()` returning `393`. A separate 50-page
  run of the three filed SQL blocks, executed verbatim against objects literally
  named `my_table` and `my_gin_index`, reported
  `pending_startup_cost = 200` and a GIN cost drop from `217.51` to `17.51`.
  Recorded the explicit absence of any upstream GIN-versus-B-tree plan
  comparison and of any `gincostestimate()` test coverage. Reset
  `verified_by_agent` to `not yet` because this was a scoped follow-up rather
  than a fresh full-page claim audit; human `verified: false` and the visible
  `(unverified)` title are unchanged. `scripts/wiki_lint` reports 0 errors and
  0 warnings.
- 2026-08-03: filed How a GIN Index Becomes Bloated in PostgreSQL 17, and How
  to Measure It (unverified) against
  unchanged pin `54eeefaedbee0385529f3edf321bb99e49232aaa` (PostgreSQL 17.10).
  Prompt hygiene applied first; the user approved corrected wording, asked for
  contrib and core-SQL-only measurement paths split cleanly, a full exact-pin
  empirical run, and a "what changed since PostgreSQL 12" section. Established
  seven bloat mechanisms from source and, contrary to the usual assumption,
  measured that a rebuild is not always smaller: because `entrySplitPage`
  equalizes by data size with no rightmost or build case and a build drains its
  accumulator in ascending key order, a fresh build settles at 50.31%-52.72%
  entry-leaf fill, so `REINDEX` grew a scattered-retail index (57.79% fill) from
  7,692,288 to 8,765,440 bytes while an ascending-retail index was byte-identical
  to its rebuild. Also measured a 16,801,792-byte entry tree surviving deletion
  of all 300,000 rows and two VACUUMs before `REINDEX` cut it to 16,384 bytes;
  posting leaves at 7.50% fill after 95% of rows were deleted; 76 deleted posting
  pages entering the FSM only after the visibility horizon advanced; FSM `avail`
  of exactly 8160 rather than the `BLCKSZ - 1` implied by the `indexfsm.c`
  comment; a 1471-page pending list moving a forced `Bitmap Index Scan` from
  17.63 to 6260.82 and buffers from 4 to 1473; and the three different meanings
  of `pg_class.reltuples` (300,000 extracted keys after `CREATE INDEX`, 100,000
  heap rows after `ANALYZE`, 90,000 after VACUUM, against a true entry count of
  2,988). Introduced a two-`random_page_cost` `EXPLAIN` probe that recovered
  pending-page counts exactly (591.00 and 101.00 against 589 and 99 pending pages
  plus two fixed pages) and a `CREATE INDEX CONCURRENTLY` rebuild probe whose
  `fresh_bytes` matched the later `REINDEX` size byte-for-byte. Attributed every
  since-v12 change to the checkout's own Stamp-bracketed history, including the
  v16 `DEFAULT_PAGE_CPU_MULTIPLIER` charges that changed the probe's scale factor
  and the v14 index-vacuum bypass and failsafe that can skip GIN entirely. All
  nine filed SQL blocks ran verbatim on an isolated exact-pin server, against
  objects literally named `my_table` / `my_col` / `my_gin_index`. Human
  `verified: false` and the visible `(unverified)` title are unchanged, and
  `verified_by_agent` stays `not yet` pending a separate claim-by-claim review.
  `scripts/wiki_lint` reports 0 errors and 0 warnings.
- 2026-08-03: answered a filed core-SQL-only follow-up on How a GIN Index
  Becomes Bloated in PostgreSQL 12, and How to Measure It (unverified) against
  unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (PostgreSQL 12.2). The user chose
  corrected prompt wording, core-only scope, and a ranked presentation of all
  three candidate methods. Established from source that core SQL cannot inspect
  a GIN index at all: `pg_proc.dat` holds no page, page-header, metapage, or
  FSM-contents function, `GinStatsData` is reachable only from C, and no
  `pg_statistic` slot carries a distinct-element count, so
  `pg_stats.elem_count_histogram` yields postings per row for array columns only
  and nothing for `tsvector` or `jsonb`. Ranked three methods by measured
  accuracy on five deterministic fixtures across three churn rounds: a
  `CREATE INDEX CONCURRENTLY` rebuild probe whose `fresh_bytes` matched the
  later `REINDEX` size byte-for-byte in all five cases; a read-only recorded
  bytes-per-row baseline that stayed within 2.75 percentage points of probe
  truth over eight comparisons and returned exactly 0.00% on the untouched
  control; and a `TABLESAMPLE` extrapolation rejected with numbers, at +17% to
  +455% fresh-size error and −384% reported bloat on a 0%-bloated index, traced
  to GIN size being strongly sublinear in row count. Documented the three
  different meanings `pg_class.reltuples` carries for a GIN index (799,493
  extracted keys after `REINDEX` versus 266,667 heap rows after
  `VACUUM (ANALYZE)` on the same index), which fork each core size function
  counts (a measured 24 kB FSM fork made `pg_table_size` exceed
  `pg_relation_size` by 0.2%), and two core-only pending-list probes: the
  `Bitmap Index Scan` total cost divided by `random_page_cost` (887.5 and
  1,471.7 against 883 and 1,469 real pending pages) and `gin_clean_pending_list`
  returning 883. All eight filed SQL blocks ran verbatim on an isolated
  exact-pin server. Added seven follow-up entries under `## Open Questions`,
  including that no core-only method exists for a first measurement with no
  prior rebuild. Reset `verified_by_agent` to `not yet` because this was a
  scoped follow-up rather than a fresh full-page claim audit; human
  `verified: false` and the visible `(unverified)` title are unchanged.
  `scripts/wiki_lint` reports 0 errors and 0 warnings.
- 2026-08-03: completed a full corrective review of How a GIN Index Becomes
  Bloated in PostgreSQL 12, and How to Measure It (unverified) against
  unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (PostgreSQL 12.2). Corrected four
  material overstatements: build and retail posting-page split policies are
  segment-based heuristics rather than exact fill percentages; an autovacuum
  partial clean can still empty the pre-existing list when there is no concurrent
  append; ordinary VACUUM does not truncate the GIN fork, but `VACUUM FULL`,
  `CLUSTER`, and `TRUNCATE` can rebuild or reset index storage; and a raw deleted
  page count mixes XID-delayed posting-tree pages with former pending-list pages
  that `shiftList` can record in the FSM immediately. Added the separate retained
  entry-page pattern caused when growing in-line posting tuples split entry pages
  before becoming small posting-tree pointers, qualified VACUUM's segment
  recompression and index-cleanup caller gates, and corrected the measurement and
  generated-header boundaries. All five production SQL recipes ran verbatim on an
  isolated exact-pin server. Deterministic fixtures reproduced pending-list growth
  and cleanup, a 16,801,792-byte entry tree surviving deletion of all 300,000 rows,
  an 8.2% retail entry-tree gap with identical posting-page counts after rebuild,
  sparse posting trees falling from 1,654,784 to 98,304 bytes only after rebuild,
  XID-delayed FSM publication for 12 deleted posting pages, and the planner cost
  shift from 5903.25 to 27.25 when a 1471-page pending list was cleaned. Recorded
  `verified_by_agent: GPT-5-6-Sol-Max-Thinking 2026-08-03T18:24:11Z`; human
  `verified: false` and the visible `(unverified)` title remain unchanged.
  `scripts/wiki_lint` reports 0 errors and 0 warnings.
- 2026-07-29: completed a full corrective review of [Comprehensive
  plan_cache_mode Analysis in PostgreSQL 12
  (unverified)](v12/questions/query-planning/plan-cache-mode.md) against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (PostgreSQL 12.2). The page was a
  thin 82-line draft whose 16 distinct citations were all single-line `#L`
  links carrying `file.c#Symbol` labels, with no `## Contents`, no
  `## Evidence Map`, no `## Navigation`, a slug title, and `## Open Questions`
  reading "Pending deep inquiry"; it is now a 125-citation walkthrough. Renamed
  the file from `plan_cache_mode_analysis.md` to `plan-cache-mode.md` to match
  the directory convention, and reworded the filed `## Question` from an
  imperative into a question on explicit user approval. Corrections to the old
  draft: the "decision hierarchy" omitted that `force_generic_plan` and
  `force_custom_plan` are checked *after* the one-shot, no-parameter, and
  transaction-statement rules and therefore cannot override them; the planning
  charge was described without noting it applies to custom plans only; and the
  claimed `GetCachedPlan` "correction" line pointed at `L1200` without the
  surrounding build-and-reprice logic. Added the material the draft lacked:
  `cursor_options` rule 6 and its SPI-only door, `generic_cost = -1` first-pass
  bias, the `INT_MAX` counter guard, `PARAM_FLAG_CONST` folding with the
  `var_eq_const`/`var_eq_non_const` split, retention of the cost history across
  invalidation and `DISCARD PLANS`, the per-execution `AcquireExecutorLocks`
  footprint, PL/pgSQL static/dynamic/simple-expression boundaries, named versus
  unnamed protocol statements, v12 observability limits, error paths,
  build/extension boundaries, test gaps, and five ancestor commits. Exact-pin
  measurements on an isolated 12.2 server with `contrib/auto_explain` installed
  reproduced the switch at execution 6 (charged custom 25.02 versus
  `generic_cost` 18.77), proved the rejected generic plan is cached by recovering
  a stale `Seq Scan` plan under `enable_seqscan = off` where a fresh generic plan
  costs 28.29, showed `force_custom_plan` unable to replan a parameterless
  statement, showed PL/pgSQL static SQL switching at call 6 while dynamic
  `EXECUTE ... USING` ignored `force_generic_plan`, contrasted
  `pgbench -M prepared` (5 custom then generic) with `-M extended` (always
  custom), measured 2 versus 5 relation locks on a four-partition table, and
  measured 0.65 ms versus 0.006 ms of planning per execution on a six-way join.
  Both fenced SQL blocks ran verbatim at the pin with `ON_ERROR_STOP=1`. The
  server was stopped and its disposable fixtures were left under
  `.wiki-runtime/`. Agent verification was recorded as
  `claude-opus-5-max 2026-07-29T21:23:49Z`; human verification remains false.
- 2026-07-29: completed a full corrective review of [Impact of B-Tree Leaf
  Density (60% vs 90%) on Index Scan Queries in PostgreSQL 12
  (unverified)](v12/questions/indexing/leaf-density-60-vs-90-query-impact.md) against
  unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42` (PostgreSQL 12.2).
  Re-resolved all 67 original citation ranges and re-cut, split, or replaced
  most of them; the page now carries 92 distinct ranges. Typical fixes were
  ranges that began mid-comment or ended mid-statement (`nbtree.h#fillfactor`,
  `plancat.c#get_relation_info`, `costsize.c#index_pages_fetched`,
  `nbtsplitloc.c` split selection, `selfuncs.c#genericcostestimate`), a
  `_bt_readpage` range that ran past the function into `_bt_saveitem`, a
  `_bt_readnextpage` backward range that started mid-comment, an
  `estimate_rel_size` range that spilled out of the index case, and
  multi-symbol "X and Y" labels replaced with one symbol per citation.
  Corrected the `EXPLAIN BUFFERS` claim (temp buffers have only read and
  written counters) and the planner-input claim (`index->pages` is the live
  `RelationGetNumberOfBlocks` count, not `pg_class.relpages`; the catalog
  density path applies to partial indexes). Restructured to the mandatory
  shape: added `## Contents`, folded `## Answer Up Front` and its sections into
  one `## Answer`, and renamed `## Related Pages` to `## Navigation`. Added
  source-backed material the page lacked: how splits rather than deletes reach
  60% density, `LP_DEAD` occupancy and in-page compaction, half-dead versus
  deleted page accounting, the absence of index-page prefetch in v12, the
  scan-path data structures, five `PGC_USERSET` settings with apply scope, and
  the contrib plus generated-`BTREE_AM_OID` build boundaries. Exact-pin
  measurements on an isolated 12.2 server reproduced the central claim: over
  1,000,000 `bigint` keys, 90.06 versus 59.90 `avg_leaf_density` gave 2733
  versus 4116 leaf pages and 2738 versus 4121 warm index-only scan buffers
  (50.5% more), with the entire 5552.01 serial-plan cost gap equal to 1388
  extra blocks at `random_page_cost = 4`; a 10,000-key range measured 32 versus
  45 index-only buffers and 31 versus 44 `Bitmap Index Scan` buffers at
  identical heap blocks; the equality probe was identical (cost 0.42..4.44, 4
  buffers) at unchanged `tree_level`; a 100,000-row wide-key fixture showed
  90-to-60 raising `tree_level` from 2 to 3, the probe cost to 0.54..4.56, and
  the probe to 5 buffers; and 1,000,000 random keys inserted retail settled at
  65.58% density with 49.71% `leaf_fragmentation` and no deletions. The filed
  `## Question` was reworded from an imperative with a question mark to a
  question on explicit user approval. The server was stopped and its
  disposable fixtures were left under `.wiki-runtime/`. Agent verification was
  recorded as `claude-opus-5-max 2026-07-29T20:41:00Z`; human verification
  remains false.
- 2026-07-29: completed a full corrective review of [B-Tree Leaf Density vs
  Fragmentation Impact on Index Scan I/O in PostgreSQL 12
  (unverified)](v12/questions/indexing/leaf-density-vs-fragmentation-index-scan-io.md)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). Re-resolved all 52 citation ranges and re-cut or split 40
  of them, mostly ranges that started or ended mid-statement or mid-comment,
  including a `cost.h` range
  that ran into an unrelated enum, an `indexam.sgml` range attached to the
  "must be written in C" paragraph instead of the page-cost paragraph, a
  `_bt_walk_left` range that covered less than half the function, and
  `nbtree.c#btvacuumpage-recycle` / `nbtpage.c#_bt_getbuf-free-page` ranges
  that missed the `RecordFreeIndexPage` and `GetFreeIndexPage` code they were
  cited for. Corrected the `EXPLAIN BUFFERS` claim (temp buffers have only
  read and written counters) and one rounding cell (1.72 to 1.73). Added the
  mandatory `## Contents` block, folded the answer under a single `## Answer`
  section, and added source-backed material the page lacked: v12 issues no
  index-page prefetch, `LP_DEAD` entries still count as dense until an insert
  or VACUUM removes them, half-dead pages stay in the leaf chain while being
  excluded from both `pgstatindex` columns, deleted pages are unlinked yet
  still priced through `index->pages`, both columns can be `NaN`, and the
  three relevant GUCs are `PGC_USERSET`. Exact-pin measurements on an isolated
  12.2 server reproduced the central claim: 90.06 versus 59.90 `avg_leaf_density`
  raised warm index-only scan buffers from 2738 to 4121 (50.5 %, against a
  predicted 1.5035x), while removing 49.95 % `leaf_fragmentation` at matched
  density moved them only from 3697 to 3680; `pageinspect` confirmed 1845 of
  3694 backward right links, a 1848-block mean jump, and zero links to the next
  physical block; and a 90 %-deleted index reported `avg_leaf_density = 90.00`
  over the same 547 leaf pages until VACUUM dropped it to 9.26. The filed
  survey query was executed at the pin and then hardened into a
  `WITH ... AS MATERIALIZED` candidate list so an inlined plan cannot call
  `pgstatindex` on a hash or GiST index; it returned only the ordinary B-trees
  in a database that also held hash, GiST, GIN, BRIN, and partitioned-parent
  indexes. The server was stopped and
  its disposable fixtures were left under `.wiki-runtime/`. Agent verification
  was recorded as `claude-opus-5-max 2026-07-29T19:54:40Z`; human verification
  remains false.
- 2026-07-29: completed a full corrective review of [PostgreSQL 12 Database
  Health Checklist (unverified)](v12/questions/server-administration/database-health-checklist.md)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). Re-resolved and label-checked every citation, now 345.
  Fixed a `checkpointer.c#ForwardFsyncRequest` label naming a symbol that does
  not exist in v12 (`ForwardSyncRequest`, whose range also ran past the
  function), an `analyze.c#do_analyze_rel` label whose range sits in
  `analyze_rel` and stopped before the partition recursion, two
  `relation_needs_vacanalyze` ranges that covered only part of the function's
  header comment, a threshold-decision range that omitted the
  statistics-unavailable branch, a `monitoring.sgml#pg_stat_all_tables` range
  cited under the `pg_stat_progress_vacuum` paragraph, a progress-vacuum doc
  range that stopped inside the `phase` row before the columns the query
  selects, swapped `auth.c` labels (`ClientAuthentication` pointing into
  `auth_failed`, `password-failures` pointing at the `no pg_hba.conf entry`
  block), a `high-availability.sgml#hot_standby_feedback` citation whose lines
  discuss `pg_last_wal_replay_lsn` instead, a `PGC_SU_BACKEND` range that cut
  off before the code that ignores a reload in existing backends, a
  `LogCheckpointEnd` range that cut off before the write/sync duration fields,
  an `initdb.c` citation that only set the `system_views.sql` path, and a
  `wait_for_stats` range that started before the function and dropped its
  terminator. Added the missing evidence for nine replication GUC apply
  scopes, `data_checksums`, `initdb --data-checksums`, `log_lock_waits`,
  `log_temp_files`, the `pg_monitor` role grants, the `varsup.c` XID
  wraparound messages, the `LogCheckpointStart`/`LogCheckpointEnd` message
  sites, the `exec_simple_query` duration-log site, and
  `pgstat_recv_recoveryconflict`, which also documents that a dropped-database
  conflict is deliberately not counted. Corrected "role ownership" to the
  actual `has_privs_of_role` membership test and the
  `pg_stat_statements` redaction from "null" to a nulled `queryid` plus an
  `<insufficient privilege>` text placeholder. An isolated exact-pin primary
  and streaming standby ran all eleven fenced SQL blocks without error and
  reproduced the `pg_monitor` progress gate (`pid` and `datname` only), a
  recovery conflict counted as `confl_snapshot` with its client cancellation,
  a PID-zero prepared-transaction blocker with its retained relation and
  transaction locks, lock-wait and deadlock logging with the `deadlocks`
  counter, temp-file logging with `temp_files`/`temp_bytes`, the v12
  autovacuum summary's absent WAL field, and the `pg_settings` superuser-only
  filter. Both servers were stopped and their fixtures left under
  `.wiki-runtime/`. Agent verification was recorded as
  `claude-opus-5-max 2026-07-29T16:53:15Z`; human verification remains false.
- 2026-07-29: completed a full corrective review of [How wal_sender_timeout Is
  Used and What It Impacts in PostgreSQL 12
  (unverified)](v12/questions/replication-and-wal/wal-sender-timeout.md) against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (PostgreSQL 12.2). Re-resolved and
  label-checked all 364 citations. Fixed a wrong `logicalfuncs.c`
  `CreateDecodingContext` label (that symbol lives in `logical.c`) and its
  too-narrow ranges, two `LogicalRepSyncTableStart` ranges that started
  mid-function, a `process_syncing_tables` label that pointed at the
  `process_syncing_tables_for_apply` comment, a `StartLogStreamer` range that
  started inside `LogStreamerMain`, a `pg_replication_slot_advance` label on the
  physical helper, two single-line label forms on multi-line ranges, and a
  `high-availability.sgml` citation attached to a `requested WAL segment ...
  has already been removed` error text that appears only in `walsender.c`.
  Added the `pg_stat_replication` superuser/`pg_read_all_stats` detail gate, the
  `immediately_reserve` default that leaves a new physical slot unreserved, and
  the `work_mem` identity of the closest protocol test. One isolated server
  built from the exact pin reproduced the reload-driven persistent-slot timeout
  in the same logged millisecond as the reload, the client seeing only
  `server closed the connection unexpectedly`, the temporary-slot drop, a
  20-second per-connection value outranking a 1-second configuration-file
  value, and the statistics privilege split; the created role and slot were
  dropped and the server was stopped. Agent verification was recorded as
  `claude-opus-5-max 2026-07-29T15:30:31Z`; human verification remains false.
- 2026-07-29: completed a full corrective review of A Heuristic to Detect
  B-Tree Index Bloat in PostgreSQL 12 (unverified) against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (PostgreSQL 12.2). Repaired four
  malformed `## Evidence Map` rows, a `nbtsplitloc.c`-labelled citation that
  pointed at `reloptions.c`, a `pg_stat_user_indexes` column claim cited to the
  schema filter instead of the `pg_stat_all_indexes` definition, and an
  `idx_scan` column that never reached the query output. Corrected the
  1.4-to-1.5 overload claim, removed the unsupported `pg_options_to_table`
  access requirement, and narrowed the planner-overestimate claim to
  `empty_pages`/`deleted_pages`. Added the `pg_stat_scan_tables` privilege
  requirement, exact GUC apply scopes, lock-conflict and `BAS_BULKREAD`
  boundaries, the `relkind` filter that excludes `pgstatindex`-rejecting
  partitioned parents, the contrib/`genbki.pl` build boundary, the regression
  coverage gap, and a mandatory `leaf_pages = 0` guard for the `NaN` case that
  otherwise reports `is_bloated = t`. Documented two systematic false positives
  with exact-pin measurements: random-key indexes settle at
  `avg_leaf_density = 64.91` with no deletions, recover to `90.05` under a
  `REINDEX` whose reclaimed bytes matched the prediction within 1.1 %, and drift
  back to `67.65`; and `deleted_pages` enter the free space map only at a second
  VACUUM, after which 430 of 685 were reused with no file growth. Every fenced
  statement, plus fixture, privilege, and `NaN` tests, ran against an isolated
  server built from the exact pin; the server was stopped afterwards. Agent
  verification was recorded as `claude-opus-5-max 2026-07-29T14:57:04Z`; human
  verification remains false.
- 2026-07-27: repinned v19 `REL_19_STABLE` from
  `3aa54433b0cdce48facb610a5b720208cc760654` to
  `99e47536bbf1a165f5dc8d504f928821ebc8df6a` (52 new commits; a clean
  forward move). Reviewed every commit and changed path. Updated the three
  related questions: `dfde93581dc` raises the direct `pg_plan_advice` history
  to 26 commits and fixes underscore-separated occurrence numbers;
  `69fe2514fdd`, `10389a7e15e`, and `99e47536bbf` raise the REPACK feature
  history to 50 commits and cover partitioned discovery, LSN debug formatting,
  and race-safe on-demand logical-decoding activation; and
  `3180ce3d7a8` restores the unconditional wrong-buffer error in
  `visibilitymap_clear()`. Updated the mandatory navigation guide, refreshed
  shifted source anchors, and left all `verified_by_agent` fields at `not yet`
  because this was a changed-range repin rather than a full-page re-audit.
- 2026-07-22: source-reviewed the scalar-function subquery follow-up in
  [Row-Level Security (RLS) in PostgreSQL 14: Implementation, Scalability and
  Performance, and Settings
  (unverified)](v14/questions/server-administration/row-level-security-rls.md) against unchanged pin
  `5c00f4e2e3bcee6931ae93429d53f7c2a4f46156`. Clarified that each surviving
  uncorrelated scalar sublink is lazy zero-or-once per occurrence and execution
  of its containing outer plan, not a query-wide function cache. Added RLS
  rewrite-copy, prepared-execution, residual-filter, runtime-key/rescan,
  lossy-recheck, equality-selectivity, partial-index, volatility,
  immutable-folding, expression-placement, privilege/leakproof, and external
  helper boundaries. Exact-pin direct-query and RLS-policy tests reproduced
  call-count, prepared-execution, volatile-semantic, and skewed-estimate
  differences. This scoped follow-up review leaves `verified_by_agent: not yet`;
  human `verified` remains `false`.
- 2026-07-22: source-reviewed the scalar-function subquery follow-up in
  [Row-Level Security (RLS) in PostgreSQL 18: Implementation, Performance,
  Settings, and Fixes Since PostgreSQL 14
  (unverified)](v18/questions/server-administration/row-level-security-rls.md) against unchanged pin
  `6cb307251c5c6261286c1566496920976640108e`. Clarified that a surviving
  uncorrelated scalar sublink is a lazy zero-or-one InitPlan per occurrence and
  execution of its containing outer plan, not a query-wide function cache.
  Added rewrite-copy,
  correlation, prepared-execution, residual-filter,
  index-runtime-key/lossy-recheck/rescan,
  equality-selectivity, partial-index, parallel-safety, function-volatility,
  immutable-folding, and external-auth-helper boundaries. Exact-pin focused
  tests reproduced the call-count, prepared-plan, semantic, and estimate
  distinctions. This was a scoped follow-up review, so `verified_by_agent`
  remains `not yet` and human `verified` remains `false`.
- 2026-07-22: re-audited [Row-Level Security (RLS) in PostgreSQL 18:
  Implementation, Performance, Settings, and Fixes Since PostgreSQL 14
  (unverified)](v18/questions/server-administration/row-level-security-rls.md) against unchanged pin
  `6cb307251c5c6261286c1566496920976640108e`. Replaced the v15 development
  stamp with the PostgreSQL 14.0 release as the history boundary. Removed
  `bd3611db5a`, whose v14 backpatch shipped in 14.0; added the omitted
  `f062cddafe`, `5ba4cc3090`, `cffca3665d`, and `0dca5d68d7`; and corrected
  the summaries and evidence for the retained rows. The resulting broad
  taxonomy contains 21 changes. Also corrected the current-v18
  logical-replication role boundary: DML and table sync honor `run_as_owner`
  before ACL/RLS checks, while replicated `TRUNCATE` checks as subscription
  owner before its trigger-only owner switches. This was a scoped history
  review, so `verified_by_agent` remains `not yet` and human `verified`
  remains `false`.
- 2026-07-22: added the five PostgreSQL 14 RLS performance follow-up questions
  to the PostgreSQL 18 page using user-approved PostgreSQL 18-adapted wording.
  The existing source-reviewed answer sections already covered plan caching,
  MultiXact, aggregation, query-versus-policy predicates, and scalar-subquery
  InitPlans; no behavioral claims, citations, source pin, or verification fields
  changed.
- 2026-07-22: completed a full corrective review of [Row-Level Security (RLS)
  in PostgreSQL 18: Implementation, Performance, Settings, and Fixes Since
  PostgreSQL 12 (unverified)](v18/questions/server-administration/row-level-security-rls.md) against
  unchanged pin `6cb307251c5c6261286c1566496920976640108e`. Removed five
  carry-over follow-up prompts that were not established as verbatim v18 user
  questions while retaining their source-backed topics inside the answer.
  Corrected command-specific policy layering, recursion and RI boundaries,
  WCO order, error-detail conditions, planner selectivity/cost and cache-layer
  distinctions, membership-edge `inherit_option` semantics, MultiXact
  citations, and
  scalar-InitPlan versus index-runtime-key behavior. Exact-pin prepared-plan
  tests reproduced stale same-role results after membership-edge
  `inherit_option` changes,
  `BYPASSRLS`, superuser, and current-database-owner changes until
  `DISCARD PLANS`; the full 231-test core regression suite passed. Corrected
  the scoped history from 25 to 24 entries by removing a test-only commit and
  removed the cross-branch minor-release matrix because its required refs and
  tag set are absent from the current pinned checkout.
- 2026-07-21: completed a full corrective review of [PostgreSQL 12 Database
  Health Checklist (unverified)](v12/questions/server-administration/database-health-checklist.md)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`
  (PostgreSQL 12.2). Reworked monitoring access and statistics-snapshot
  semantics, client capacity and blocker/prepared-lock SQL, independent
  vacuum/analyze and XID/MultiXact checks, checkpoint/background-writer
  interpretation, archive/replication/slot metrics, full-capture
  `pg_stat_statements` deltas, checksum and base-backup accounting, relation
  diagnostics, and the operational log matrix. Added exact GUC apply scopes,
  generated/build boundaries, direct tests and test gaps, an evidence map, and
  explicit open questions. An out-of-tree build of the exact pin, with its
  matching `pg_stat_statements` and `pgstattuple` modules, executed every final
  fenced SQL statement successfully against an isolated server; diagnostic
  relation placeholders were mapped to local heap and B-tree fixtures. The
  server was stopped after testing. Independent final audits found no remaining
  page defect. Agent verification was recorded as
  `GPT-5 2026-07-21T13:34:54Z`; human verification remains false.
- 2026-07-20: completed a new full claim-to-source review of [Row-Level Security
  (RLS) in PostgreSQL 14: Implementation, Scalability and Performance, and
  Settings (unverified)](v14/questions/server-administration/row-level-security-rls.md) and all five
  follow-ups against unchanged pin
  `5c00f4e2e3bcee6931ae93429d53f7c2a4f46156` (PostgreSQL 14.23). Corrected the
  relcache policy-order description, `ON CONFLICT DO UPDATE` SELECT-policy
  layering, base-restriction versus residual-scan behavior, default-deny DML,
  partial-index implication, plan-time pruning citations, direct-versus-
  subquery aggregate legality, scalar-InitPlan per-occurrence/cardinality and
  lossy-recheck boundaries, table/role permissions, and initial-sync versus
  ongoing/apply logical-replication behavior. Added policy selectivity/cost and
  parallel-hazard effects, exact lock conflicts, CTAS source rewrite, and the
  hook/RI error-detail boundaries. Expanded the plan-cache flaw from same-role
  membership changes to `INHERIT`, `BYPASSRLS`, `SUPERUSER`, intermediate-role,
  and `pg_database_owner` inputs. An exact-pin isolated run reproduced stale
  prepared results for membership, `INHERIT`, `BYPASSRLS`, and database-owner
  changes in both directions; `DISCARD PLANS` restored the new state each time,
  including the security-sensitive `NOBYPASSRLS` case. The server was stopped.
  Agent verification was recorded as `GPT-5 2026-07-20T18:13:13Z`; human
  verification remains false.
- 2026-07-17: completed a full claim-to-source review of [Can ALTER TABLE ...
  ATTACH PARTITION Drop Indexes in PostgreSQL 17
  (unverified)](v17/questions/indexing/attach-partition-index-drops.md) against unchanged
  pin `54eeefaedbee0385529f3edf321bb99e49232aaa` (PostgreSQL 17.10). Scoped the
  answer precisely: core table ATTACH is match-or-create and never drops an
  existing index, while user event triggers or a `ProcessUtility_hook` can issue
  independent DDL before or after the built-in path. Added parser/utility
  dispatch, parent/child lock serialization with DROP, transactional rollback,
  catalog/dependency state, the physical and recursive creation paths,
  generated parser/catalog headers, object-access and custom-AM boundaries,
  shipped-contrib behavior, and explicit test gaps. Corrected the old claim
  that partial and expression indexes are inherently incompatible: mapped
  matching definitions are reusable. Added exclusion-index non-matching and
  separated the direct invalid-index skip from recursive `DefineIndex`, which
  can absorb an invalid leaf. Expanded the since-v12 history with parser,
  event-trigger metadata, recursive matching/validity, exclusion-constraint,
  search-path, and v17-stable propagation fixes. Exact-pin smoke tests confirmed
  matching partial/expression reuse, exclusion non-reuse, rollback, custom
  start/end-trigger drops, and an open multilevel validity edge: an invalid new
  intermediate child can sit below a still-valid pre-existing top index. The
  exact-pin core regression suite passed. Set `verified_by_agent` to
  `GPT-5-6-Sol-Max-Thinking 2026-07-17T19:53:21Z`; human `verified` remains
  `false`.
- 2026-07-17: completed a full claim-to-source review of Proposing a Sampling
  pgstatindex Variant for PostgreSQL 17
  (unverified) against
  unchanged pin `54eeefaedbee0385529f3edf321bb99e49232aaa` (PostgreSQL 17.10),
  and carried over both user-approved corrected follow-ups from the
  corresponding v12 question. Reworked the design around v17's
  `pg_prng_state`/`uint32` `BlockSampler`, v17's invalid-index rejection,
  continuous relation and per-page lock boundaries, stronger sampled-page
  validation, and Make plus Meson extension wiring. Added a strict 10%
  effective-fraction floor below 100 MiB, direct sample-count outputs, and a
  one-read `pageinspect` 1.12 prototype using 64-bit block arguments and the
  `d`/`D` deleted-page mapping. Exact-pin execution over six sub-50-MiB
  bloat/partial/small/empty fixtures plus a 107.13 MiB control confirmed every
  target and strict threshold edge and matched all shared standard-
  `pgstatindex` fields at 100%. One hundred seeds at requested 1% and 5%
  quantified the floor results; the 3.88 MiB partial index moved from 5/25 to
  50 pages, with leaf MAPE changing 0.80% -> 0.81% and 0.95% -> 0.81%, while
  the 0.66 MiB control lost its two leaf-free 1% draws. The `pgstattuple`
  regression target and all eight `pageinspect` targets passed. Set
  `verified_by_agent` to
  `GPT-5-6-Sol-Max-Thinking 2026-07-17T19:25:39Z`; human `verified` remains
  `false`.
- 2026-07-17: extended Proposing a Sampling pgstatindex Variant for PostgreSQL
  12 (unverified) with a
  second user-approved corrected follow-up: apply a 10% effective sample floor
  when captured main-fork size is strictly below 100 MiB, rerun the comparison,
  and explain the small-partial-index effect. Updated the C-policy formula,
  `pageinspect` prototype, pros/cons, boundary tests, and open questions. Reused
  the six original fixtures and added a 107.13 MiB healthy control. Exact-pin
  execution confirmed the strict target policy, synthetic byte edges immediately
  below/at/above 100 MiB, and full-sample equivalence across all seven indexes.
  One hundred identical seeds at requested 1% and 5% showed the 3.88 MiB partial
  index moving from 5/25 pages to 50 pages for either request, with leaf-count
  MAPE changing from 1.18%/1.08% to 0.86%; density mean error stayed 0.02 points.
  `verified_by_agent` remains `not yet` because this was another scoped follow-up.
- 2026-07-17: extended Proposing a Sampling pgstatindex Variant for PostgreSQL
  12 (unverified) with the
  user-approved corrected follow-up requesting comparative tests, against the
  unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`. Added an executed,
  reproducible `pageinspect`-prototype comparison over six indexes, all below
  50 MB: uniformly sparse, contiguous-range-deleted, split/churn, sparse
  partial, small healthy, and empty. A 100% sample matched every shared
  standard-`pgstatindex` field in all six cases. One hundred deterministic
  `setseed()` draws at 1% and 5% quantify leaf/deleted count MAPE, density and
  fragmentation error, and leaf-free draws; the results expose particularly
  high variance for deleted-page counts, fragmentation, and a one-page sample
  of the 0.66 MiB index. Reset `verified_by_agent` to `not yet` because this was
  a scoped follow-up rather than a new full-page audit.
- 2026-07-17: completed a full claim-to-source review of Proposing a Sampling
  pgstatindex Variant for PostgreSQL 12
  (unverified) against
  unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42` (`REL_12_2`).
  Replaced the misleading exact-versus-estimated split with separately timed
  direct observations versus estimates and added direct sample counts. Reworked
  the C proposal around v12's native Algorithm-S `BlockSampler`, including its
  without-replacement ascending output, `int` sample-size ceiling, potentially
  O(number-of-blocks) skip loop, and cancellation boundary. Added the complete
  relation/page-lock, concurrent DML/VACUUM, one-time length, bulk-read ring,
  metapage and sampled-page validation, privilege, extension-upgrade,
  fmgr/generated-header, and test envelopes. Revised the `pageinspect` SQL to
  remove the hidden sub-100-MiB 10% floor, evaluate relation size once, read each
  sampled ordinary page once, expose sample sizes, and document its lock,
  malformed-page, signed-`int4`, helper-lifecycle, and invalid-input limits.
  Exact-pin execution confirmed full-sample equivalence on a populated B-tree
  and the metapage-only edge; the one `pgstattuple` and all five `pageinspect`
  regression targets passed. Set `verified_by_agent` to
  `GPT-5-6-Sol-Max-Thinking 2026-07-17T18:12:12Z`; human `verified` remains
  `false`.
- 2026-07-17: extended [How `wal_sender_timeout` Is Used and What It Impacts in
  PostgreSQL 12 (unverified)](v12/questions/replication-and-wal/wal-sender-timeout.md) with the
  user-approved corrected follow-up, “How does `wal_sender_timeout` affect
  `pg_replication_slots`, and how is WAL retained during error or failure
  scenarios?”, against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42`. Added exact shared-view row and
  column transitions; persistent, temporary, and unreserved-slot boundaries;
  timeout, EOF/protocol/error, orderly `CopyDone`, and crash/restart outcomes;
  `restart_lsn` versus logical confirmation and row horizons; checkpointed
  state and conservative crash rollback; and the checkpoint/restartpoint,
  `wal_keep_segments`, and archive limits on eventual WAL removal. An isolated
  exact-pin libpq smoke test observed a temporary physical slot as active with
  reserved WAL, then absent after its silent stream reached a per-connection
  20-second sender timeout. Reset `verified_by_agent` to `not yet` because this
  was a scoped follow-up rather than a new full-page audit.
- 2026-07-17: completed a full claim-to-source review of [How
  `wal_sender_timeout` Is Used and What It Impacts in PostgreSQL 12
  (unverified)](v12/questions/replication-and-wal/wal-sender-timeout.md) against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42` (`REL_12_2`). Corrected the
  blanket half-time description by adding the earlier non-requesting logical
  WAL-wait heartbeat and shutdown-request branches. Added exact activation and
  exclusion boundaries (`START_REPLICATION` only; not the main base backup,
  logical slot snapshot build, initial table copy, or SQL decoding functions),
  process-local versus exposed reply timestamps, server-stall accounting,
  physical client tools, table-sync catch-up, and receiver/retry controls.
  Expanded operational effects to live reload, `max_wal_senders`, reconnects,
  monitoring limits, synchronous waiters that timeout does not release,
  persistent-versus-temporary slot cleanup, inactive-slot WAL retention, build
  and extension boundaries, and direct-test absence. An isolated exact-pin
  smoke test confirmed active-sender reload, timeout logging, sender-row
  removal, and persistent-slot retention. Set `verified_by_agent` to
  `GPT-5-6-Sol-Max-Thinking 2026-07-17T16:13:56Z`; human `verified` remains
  `false`.
- 2026-07-17: completed a full claim-to-source review of [Query Planner
  Statistics Sources in PostgreSQL 12
  (unverified)](v12/questions/query-planning/query-planner-statistics-sources.md) against
  unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`. Confirmed that
  `pg_stat_all_tables` is cumulative monitoring rather than direct planner
  input, while its underlying modification counter affects planning indirectly
  by triggering auto-analyze. Added the reverse edge where a planner B-tree
  endpoint probe increments an exposed index-scan counter without reading that
  counter as input. Corrected ordinary versus partial index sizing
  and separated CHECK, NOT NULL, and partition-constraint origins. Added the
  complete caller/data-structure path; inherited and expression-index
  statistics, including partial-index correlation costing; built/unbuilt and
  partial-ANALYZE extended-data behavior; defaults, stale/security/error paths
  and the v12 MCV error-label defect; operator/function/type/index/FK metadata;
  table/index AM, FDW, hook, shipped-contrib, generated-header, syscache, and
  relcache boundaries; and direct tests plus explicit negative-test absence.
  The exact-pin core regression suite passed. Set `verified_by_agent` to
  `GPT-5-6-Sol-Max-Thinking 2026-07-17T15:45:58Z`; human `verified` remains
  `false`.
- 2026-07-17: completed a full claim-to-source review of Finding and Prioritizing Bloated B-Tree Indexes for REINDEX in PostgreSQL 12 (unverified) against unchanged
  pin `45b88269a353ad93744772791feb6d01bc7e1e42`. Replaced the former
  whole-index, hard-coded-90 density formula with a configured-fillfactor page
  estimator that separates live-leaf shortfall, half-dead pages, and deleted
  pages. Corrected the false claim that expression indexes lack
  `pg_statistic` rows, downgraded `pgstatindex` from an exact snapshot to a full
  non-snapshot physical observation, and added its buffer-ring, integrity, and
  I/O-counter-pollution boundaries. Reworked priority around paired-window scan
  rates and independent pre/post-REINDEX windows; narrowed concurrent counter
  continuity to the published collector entry copied at swap; and corrected
  split occupancy, invalid-index routing, `_ccnew`/`_ccold` failures, and
  production SQL. Exact-pin checks covered default and nondefault fillfactors,
  expression statistics, sparse post-VACUUM shape, diagnostic counter effects,
  and concurrent REINDEX. Set `verified_by_agent` to
  `GPT-5-6-Sol-Max-Thinking 2026-07-17T15:18:58Z`; human `verified` remains
  `false`.
- 2026-07-17: extended [How CREATE INDEX CONCURRENTLY Is Implemented in
  PostgreSQL 12 (unverified)](v12/questions/indexing/create-index-concurrently.md) with
  the user-approved corrected follow-up, “What GUCs have a performance impact
  on it?”, against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42`. Added a source-backed matrix for
  AM-dependent build and validation memory, B-tree-only worker request and pool
  limits, GiST/GIN boundaries, v12 bulk-read rings and synchronized scans,
  index and temporary storage, backend writeback, B-tree immediate sync,
  WAL/checkpoint/four-transaction commit costs, three timeout-sensitive waits,
  exact restart/reload/session scopes, absent later-version controls, and
  commonly confused non-controls. `verified_by_agent` remains `not yet`
  because this was a scoped expansion, not a full-page re-audit.
- 2026-07-17: extended [How REINDEX INDEX CONCURRENTLY Is Implemented in
  PostgreSQL 12 (unverified)](v12/questions/indexing/reindex-index-concurrently.md) with
  the user-approved corrected follow-up, “What GUCs have a performance impact
  on it?”, against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42`. Added a source-backed matrix for
  AM-dependent build and validation memory, B-tree-only worker request and pool
  limits, GiST/GIN boundaries, v12 bulk-read rings and synchronized scans,
  temporary storage and the fixed preserve-old-index output tablespace,
  B-tree's immediate data sync, WAL/checkpoint costs, xidless commit semantics,
  nine internal commits for one index, five timeout-sensitive waits, exact
  restart/reload/session scopes, absent later-version controls, and commonly
  confused non-controls. `verified_by_agent` remains `not yet` because this was
  a scoped expansion, not a full-page re-audit.
- 2026-07-17: extended [How REINDEX INDEX CONCURRENTLY Is Implemented in
  PostgreSQL 17 (unverified)](v17/questions/indexing/reindex-index-concurrently.md) with
  the user-approved corrected follow-up, “What GUCs have a performance impact
  on it?”, against unchanged pin
  `54eeefaedbee0385529f3edf321bb99e49232aaa`. Added a source-backed matrix for
  AM-dependent build and validation memory, B-tree/BRIN worker request and pool
  limits, GiST/GIN boundaries, v17 sequential read streams, synchronized scans,
  temporary storage and RIC's preserve-old-or-explicit output tablespace rule,
  permanent-build WAL/checkpoint costs, nine internal commits for one index,
  five timeout-sensitive waits, exact restart/reload/session scopes, and
  commonly confused non-controls. Retained the source-visible
  `READ_STREAM_MAINTENANCE` comment versus `READ_STREAM_SEQUENTIAL`
  implementation mismatch under `## Open Questions`. Reset
  `verified_by_agent` to `not yet` because this was a scoped expansion, not a
  full-page re-audit.
- 2026-07-17: repinned v19 `REL_19_STABLE` from
  `8055e3375aa1c2237181e06be26b05b964d18ed5` to
  `3aa54433b0cdce48facb610a5b720208cc760654` (31 new commits; a clean
  forward move). The branch is now stamped `19beta2`. Reviewed every commit,
  changed path, and v19 source citation. Added REPACK documentation commit
  `8a84ddd8c63`, which puts `REPACK` in the generic `MAINTAIN` and predefined
  `pg_maintain` descriptions; the REPACK feature history is now 47 commits.
  Expanded the visibility-map coverage for `56bf5fa5d67` /
  `b01c31eef9c` / `9171f77db23`: heap operations now register modified VM
  pages in WAL, redo preserves the clears, and a new TAP test checks combined
  incremental-backup restore. The on-access VM-setting algorithm, parallel
  autovacuum, and scoring are unchanged. No `pg_plan_advice` module, doc, test,
  or direct core-infrastructure commit landed. Updated all four v19 page pins
  and refreshed 12 content-identical shifted source ranges; all remaining
  existing ranges stayed at the same lines. `verified_by_agent` remains
  `not yet` because this was a changed-range repin, not a full-page re-audit.
- 2026-07-16: extended [How CREATE INDEX CONCURRENTLY Is Implemented in
  PostgreSQL 17 (unverified)](v17/questions/indexing/create-index-concurrently.md) with
  the user-approved corrected follow-up, “What GUCs have a performance impact
  on it?”, against unchanged pin
  `54eeefaedbee0385529f3edf321bb99e49232aaa`. Added a source-backed matrix for
  direct build and validation memory, parallel request and worker-pool limits,
  GiST and GIN boundaries, v17 sequential read-stream I/O, synchronized scans,
  index and temporary storage, WAL compression/checkpoints/four-transaction
  commit costs, waits and timeout semantics, apply scopes, and commonly
  confused settings that do not control CIC. The source-visible mismatch
  between the `READ_STREAM_MAINTENANCE` comment and the heap AM's actual
  `READ_STREAM_SEQUENTIAL` flag is retained under `## Open Questions`.
  `verified_by_agent` remains `not yet` because this was a scoped expansion,
  not a full-page re-audit.
- 2026-07-13: completed a full claim-to-source review of [How MultiXact Works
  in PostgreSQL 14, and How Foreign Keys and Other Operations Degrade
  Performance When the Local Cache Spills to Secondary Storage
  (unverified)](v14/questions/storage-and-vacuum/multixact-foreign-keys-cache-spill.md) against
  unchanged pin `5c00f4e2e3bcee6931ae93429d53f7c2a4f46156`. Corrected the
  premise: the 256-entry backend-local transaction cache evicts with `pfree`
  and never spills an entry; only a subsequent shared-SLRU miss requests a
  filesystem read, which may still hit the OS page cache. Separated one
  backend's cache pressure from cluster-wide MXID/member allocation and added
  exact cache-count, obsolete-read, committed-updater, immutable expansion,
  conflict/wait, WAL/recovery/2PC, horizon/truncation, table-AM, and extension
  boundaries. Corrected the user-visible wait names to the generated forms
  without `Lock`, added the separate MXID-counter hard stop, and narrowed
  freezing to all actual replacement outcomes including a singleton surviving
  locker. Added FK null/partition/restrict edges, update-chain and internal
  tuple-lock callers, `vacuum_multixact_failsafe_age`, exact GUC/reloption
  scopes, build/generated artifacts, attribution limits, and direct tests.
  The exact-pin full isolation suite and all filed diagnostic SQL passed; the
  temporary server was stopped. Set `verified_by_agent` to
  `GPT-5-6-Sol-Max-Thinking 2026-07-13T20:08:07Z`; human `verified` remains
  `false`.
- 2026-07-13: completed a full claim-to-source review of [Performance
  Implications of Functions and Procedures in a WHERE Clause in PostgreSQL 14,
  and How to Minimize the Overhead
  (unverified)](v14/questions/query-planning/functions-procedures-in-where-clause.md) against
  unchanged pin `5c00f4e2e3bcee6931ae93429d53f7c2a4f46156`. Corrected the
  `CALL` boundary: it has no optimizer plan, but evaluates argument expressions
  separately before direct fmgr invocation, and those standalone expressions
  do not enter JIT. Added direct `WHERE` rejection of SRFs/aggregates/window
  functions and removed `ROWS` as a scalar-WHERE lever. Reworked call
  multiplicity around residual scan tuples, join pairs, strict-null skips,
  pseudoconstant rescans, runtime keys, and SQL/JIT inlining. Corrected the
  plain-index claim, resolved expression-index and extended-expression
  statistics, and separated leakproof security promotion from the strict
  `< 10 * cpu_operator_cost` runtime-order cutoff. Added JIT,
  `track_functions`, exact GUC scopes, generated `pg_proc_d.h`, fmgr/contrib
  `sepgsql`, extension-bitcode, and direct-test/absence boundaries. Exact-pin
  spot checks reproduced one-time gating, row-dependent versus strict-null and
  scalar-InitPlan call counts, and expression-index search; the full core
  regression check passed. Set `verified_by_agent` to
  `GPT-5-6-Sol-Max-Thinking 2026-07-13T19:41:59Z`; human `verified` remains
  `false`; `wiki_lint`: 0 errors, 0 warnings.
- 2026-07-13: completed a full claim-to-source review of [Row-Level Security
  (RLS) in PostgreSQL 18: Implementation, Performance, Settings, and Fixes
  Since PostgreSQL 12
  (unverified)](v18/questions/server-administration/row-level-security-rls.md) against unchanged pin
  `6cb307251c5c6261286c1566496920976640108e`. Corrected MERGE INSERT to use
  ordinary `WCO_RLS_INSERT_CHECK` and logical replication to check its selected
  action role (table owner by default, subscription owner with
  `run_as_owner = true`). Added generated `pg_policy_d.h`/relcache/contrib
  boundaries, index/pruning/parallel and policy-cache performance details,
  complete direct settings/tool surfaces, and the source-visible distinction
  between per-tuple filters and optimizable quals. Reproduced both membership
  revoke and grant under an unchanged effective role: cached RLS results stayed
  stale until session-local `DISCARD PLANS`. Expanded the explicitly scoped fix
  history from 20 to 25 by adding seven omitted fixes and removing two
  independent additions; verified all hashes, subjects, ancestry, five
  post-fork v18/master pairs, and first-release tags/dates. The exact-pin build
  and core regression check passed; set `verified_by_agent` to
  `GPT-5-6-Sol-Max-Thinking 2026-07-13T18:58:20Z`; human `verified` remains
  `false`; `wiki_lint`: 0 errors, 0 warnings.
- 2026-07-13: repinned v19 `REL_19_STABLE` from
  `01c544e1afb99bc2a76803870010b7cd2907f3b5` to
  `8055e3375aa1c2237181e06be26b05b964d18ed5` (12 new commits; still stamped
  `19beta1`). Reviewed every commit, changed path, and v19 source citation.
  Added REPACK commit `133eba078f7`, which removes ineffective discovery-time
  table locks and hardens the locked per-table open/recheck path; the REPACK
  feature history is now 46 commits. Added the post-beta1 on-access VM fix
  `e9eaeb04248`, which records a newly all-visible page's free space so a later
  VM-based VACUUM skip does not leave stale FSM state. No `pg_plan_advice`
  module, doc, test, or core-planner commit landed in the range. Updated all
  four v19 page pins, refreshed shifted `repack.c`, `pruneheap.c`, and
  `rewriteHandler.c` anchors, and corrected two pre-existing end-line anchors.
  `verified_by_agent` remains `not yet` because this was a changed-range repin,
  not a full claim-by-claim re-verification.
- 2026-07-13: extended [How CREATE INDEX CONCURRENTLY Is Implemented in
  PostgreSQL 17 (unverified)](v17/questions/indexing/create-index-concurrently.md) with
  the user-approved corrected `maintenance_work_mem` follow-up against unchanged
  pin `54eeefaedbee0385529f3edf321bb99e49232aaa`. The source-backed section
  separates transaction 2's AM-specific first build from transaction 3's serial
  encoded-TID validation sort; traces B-tree and BRIN planned-versus-launched
  parallel participants, 32 MB automatic worker shares, and mandatory worker
  tapes; maps first-build and plateau behavior for every core AM and contrib
  Bloom; and covers GIN pending-list cleanup, GUC scope, observability, extension
  and build boundaries, and direct test gaps. There is no universal byte cutoff;
  the practical plateau is workload-specific. Reset `verified_by_agent` to
  `not yet` because this was a scoped expansion, not a full-page re-audit;
  `wiki_lint`: 0 errors, 0 warnings.
- 2026-07-13: source-reviewed the `maintenance_work_mem` follow-up in [How
  CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 12
  (unverified)](v12/questions/indexing/create-index-concurrently.md) against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42`. Corrected the parallel B-tree
  accounting to distinguish planned from launched workers and to count the
  leader's worker-role output run; qualified the setting as the intended
  primary-sort budget rather than an exact total-command cap; made GIN cleanup
  conditional on a nonempty pending list; documented BRIN's empty validation
  enumeration, GiST's own temporary-file path, and the GIN soft threshold; and
  narrowed temp statistics to file-volume evidence plus the regression-test
  absence claim to direct CIC coverage. The scoped review retains
  `verified_by_agent: not yet` because the full page was not re-verified;
  `wiki_lint`: 0 errors, 0 warnings.
- 2026-07-13: re-audited the `maintenance_work_mem` follow-up in [How CREATE
  INDEX CONCURRENTLY Is Implemented in PostgreSQL 12
  (unverified)](v12/questions/indexing/create-index-concurrently.md) against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42`. Preserved the no-universal-cutoff
  conclusion, but replaced the misleading “two allocations” framing with an
  AM-dependent first-build phase plus the common serial validation-TID sort.
  Clarified the MVCC-to-B-tree alive-tuple boundary, generalized the 32 MB
  parallel participant thresholds, added the session/transaction scope and
  runtime-availability boundary for `max_parallel_maintenance_workers`, and
  distinguished true hash CIC (`NBuffers`) from its temporary non-concurrent
  fallback (`NLocBuffer`). Also sharpened the GiST `auto` switch and GIN forced
  cleanup boundaries, refreshed all three summaries, and retained
  `verified_by_agent: not yet` because this remained a scoped section review;
  `wiki_lint`: 0 errors, 0 warnings.
- 2026-07-13: completed a scoped claim-to-source verification of the
  `maintenance_work_mem` follow-up section in [How CREATE INDEX CONCURRENTLY Is
  Implemented in PostgreSQL 12
  (unverified)](v12/questions/indexing/create-index-concurrently.md) against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42`. Re-checked that section's claims
  against `raw/postgres-12/`: the B-tree serial/parallel budgets and the 32 MB
  per-participant worker cap (0/1/2 workers at below-64/64/96 MB), the full-budget
  serial encoded-TID validation sort, the hash `sort_threshold` selection, the
  per-AM first-build matrix, and the `trace_sort`/`log_temp_files`/progress
  observability plus test-coverage citations all resolve to the cited lines.
  Fixed two precision defects: the misleading `index_concurrently_build`
  "returns before setting indisready" wording (it runs `index_build`, then sets
  `INDEX_CREATE_SET_READY`, then returns) and the `autovacuum_work_mem = -1`
  fallback citation (added the `config.sgml` `autovacuum_work_mem` definition).
  The global and v12 landing-page summaries remain accurate. `verified_by_agent`
  stays `not yet` because this re-audited only one section, not the whole page;
  `wiki_lint`: 0 errors, 0 warnings.
- 2026-07-10: extended [How CREATE INDEX CONCURRENTLY Is Implemented in
  PostgreSQL 12 (unverified)](v12/questions/indexing/create-index-concurrently.md) with
  the user-approved corrected follow-up on `maintenance_work_mem`. The new
  source-backed section separates the transaction-2 AM build from the
  transaction-3 validation TID sort, explains B-tree's serial and parallel
  budgets (including automatic 32 MB participant thresholds and one required
  tape run per worker), and maps first-build behavior for B-tree, hash, GiST,
  GIN, SP-GiST, BRIN, and contrib Bloom. It explains why no universal byte
  cutoff exists, defines the per-AM plateau conditions, distinguishes fixed CIC
  scan/wait/write costs from memory-sensitive work, and covers `trace_sort`,
  `log_temp_files`, progress phases, and aggregate temp counters. The only
  direct v12 regression case forces non-concurrent hash sorting; CIC has no
  memory/plateau test. Same-checkout history for parallel B-tree build, encoded
  validation TIDs, and hash pre-sorting was ancestry-checked. Refreshed
  `wiki/index.md`, `wiki/v12/index.md`, and this coverage row;
  `verified_by_agent` is `not yet` because this was a scoped expansion rather
  than a full-page claim re-audit.
- 2026-07-10: completed a full claim-to-source review of [How `pgstatindex`
  Calculates B-Tree Index Statistics in PostgreSQL 12
  (unverified)](v12/questions/indexing/how-pgstatindex-calculates-information.md) against
  unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`. Preserved the
  core formulas but made their exact boundaries explicit: `index_size` is the
  one-time captured main-fork block count times `BLCKSZ`; density is a ratio of
  summed physical leaf occupancy using `PageGetFreeSpace` and includes retained
  `LP_DEAD` storage; fragmentation is the percentage of live leaves whose
  right-link points to a lower physical block; both percentages are formatted
  to two decimals. Confirmed and expanded the page's existing `empty_pages`
  half-dead-state explanation, and distinguished true-root metadata from the
  fast root. Added fresh-install 1.4-to-1.5 update wiring, function privileges,
  invalid-index acceptance, generated `pg_am_d.h`/`BTREE_AM_OID` implications,
  deleted-page recyclability, one-time length/extension behavior, per-page and
  relation locks, the unlocked/unvalidated metapage read, missing ordinary-page
  B-tree sanity checks, and explicit regression absences. An exact-pin build
  passed the module's one declared `installcheck`; a populated spot check before
  and after `VACUUM` matched the physical-occupancy interpretation. Refreshed
  `wiki/index.md` and `wiki/v12/index.md`; set `verified_by_agent:
  GPT-5-6-Sol-Max-Thinking 2026-07-10T16:00:43Z` after the final claim pass.
  Human `verified` remains `false`.
- 2026-07-10: completed a full claim-to-source review of the [PostgreSQL 12
  Codebase Navigation Guide (unverified)](v12/codebase-navigation-guide.md)
  against unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`.
  Corrected the RIR expansion (`Retrieve-Instead-Retrieve`, not
  "retrieve-instead-rewrite"), added the omitted `PGC_SU_BACKEND` GUC context,
  completed the executor lifecycle through `ExecutorEnd`, and repaired ranges
  that stopped before Parse-source storage, best-path selection, aggregate plan
  dispatch, and complete AM callback definitions. Expanded backend/standalone
  callers, simple-query snapshots, Parse/Bind/Execute/Sync boundaries, portal
  strategies and failure cleanup, outer protocol/transaction error recovery,
  utility caller/event-trigger routing, plan-cache and portal structs, custom AM
  registration/relcache/wrapper/test boundaries, and generated catalog/parser/
  fmgr/LWLock build and reverse-include implications. Refreshed `wiki/index.md`
  and `wiki/v12/index.md`; set `verified_by_agent:
  GPT-5-6-Sol-Max-Thinking 2026-07-10T15:06:04Z` after the final claim pass.
  Human `verified` remains `false`.
- 2026-07-10: completed a full claim-to-source review of [How CREATE INDEX
  CONCURRENTLY Is Implemented in PostgreSQL 12
  (unverified)](v12/questions/indexing/create-index-concurrently.md) against unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42`. Corrected three material scope
  errors: the four explicit core synchronization barriers are not every backend
  wait (DDL event triggers, predicates/expressions, AM callbacks, B-tree unique
  validation, and parallel-worker coordination can also wait); an error in a
  `ddl_command_end` trigger after non-transactional `SET_VALID` can report CIC
  failure while leaving a valid index; and crash recovery cannot itself lose
  completed in-tree build data while retaining `SET_VALID`, but that does not
  rule out the separate prepared-transaction valid-but-incomplete defect or
  prove third-party AM durability. This qualification supersedes the shorthand
  "never a valid-but-incomplete index" in the historical 2026-06-19 coverage
  note below. Added parser/utility/generated-catalog coverage, temp and
  `IF NOT EXISTS` ordering, the core/index-AM boundary, contrib Bloom, direct
  REINDEX citations, test-presence/absence detail, and scoped source history.
  Exact-pin temporary builds reproduced both the prepared-write missing-entry
  defect and the late event-trigger valid-index outcome. Refreshed
  `wiki/index.md` and `wiki/v12/index.md`; set
  `verified_by_agent: GPT-5-6-Sol-Max-Thinking 2026-07-10T14:38:16Z` after the
  final claim pass. Human `verified` remains `false`.
- 2026-07-10: completed a full claim-to-source review of [Row-Level Security
  (RLS) in PostgreSQL 14: Implementation, Scalability and Performance, and
  Settings (unverified)](v14/questions/server-administration/row-level-security-rls.md) against the
  unchanged `REL_14_STABLE` pin `5c00f4e2e3b`. Corrected the blanket per-row
  wording (execution frequency depends on filter, InitPlan, SQL-function
  inlining, and index-runtime-key shape), restrictive-policy sorting phase
  (rewrite, not relcache build), mixed-policy security-level order, and
  partition fan-out wording. Expanded the MultiXact answer from the FK-only
  path to both source-supported paths: policy-authored `FOR SHARE` lookup
  locking and the RLS-induced initial-FK-validation fallback. Added generated
  catalog/header implications, view-owner identity, whole-table/RI/publisher
  replication boundaries, policy-DDL `AccessExclusiveLock`, inspection and
  pg_dump/pg_restore surfaces, GUC scope boundaries, and explicit core/hook
  test coverage. Documented and reproduced the unchanged-effective-user
  role-membership invalidation blind spot in cached policy selection, plus the
  `DISCARD PLANS` mitigation; the in-tree prepared-plan test does not cover
  membership changes. Refreshed `wiki/index.md`, `wiki/v14/index.md`, and the v14
  coverage cell here.
- 2026-07-09: repinned v19 to the new `REL_19_STABLE` branch. Upstream `master`
  had advanced to `20devel` (branch commit `a281a3e6dbb` "Stamp HEAD as 20devel."),
  and the `REL_19_STABLE` branch was created, so the former "post-`REL_19_BETA1`
  `master`" pin was no longer the v19 line. Repinned `raw/postgres-19/` from
  `cdae794af31b3e9cfc323fc654292d86fa746f77` to the `REL_19_STABLE` tip
  `01c544e1afb99bc2a76803870010b7cd2907f3b5` (2026-07-09, still stamped `19beta1`;
  a clean forward move — the old pin is an ancestor, 105 new v19 commits).
  Switched the Branch column from `` `master` (post-19beta1) `` to `REL_19_STABLE`.
  Reviewed the `cdae794a..01c544e1` changed range against the three v19 question
  pages and the codebase navigation guide, refreshed all shifted source line
  anchors (verified via a difflib old->new line map plus content-equality checks),
  and added the new feature-scope commits: REPACK grew 42 -> 45
  (`fb284f2f9bd` stored generated columns, `5e450df50dc` change-replay range-table
  init, tree-wide `da8889ccd7e` `PG_MODULE_MAGIC_EXT`), and `pg_plan_advice` module
  commits grew 22 -> 25 (`89f5f860cc5` FOREIGN_JOIN single-relation fix,
  `ea203d371de` pgindent follow-up, `da8889ccd7e`). Also updated the autovacuum
  page's release-note "typo" caveat because commit `1a7fa06dbcd` fixed the
  `autovacuum_vacuum_insert_score_weight` prefix typo in `release-19.sgml` within
  the range. Refreshed `wiki/index.md`, `wiki/v19/index.md`, the v19 row here, and
  each page's `pinned_commit`. `verified_by_agent` is `not yet` on all v19 pages
  (reset from the prior agent-timestamp on the `pg_plan_advice` page): a repin and
  changed-range review, not a claim-by-claim re-verification.
- 2026-07-09: extended [Table Partitioning Optimizations and Configuration During
  Query Planning and Execution in PostgreSQL 17
  (unverified)](v17/questions/query-planning/partitioning-planning-execution-optimizations.md)
  with a new `## Locking reduction and random-I/O sensitivity per optimization`
  section for the follow-up ("Add an extra analysis on how each optimization will
  reduce locking, and how each will have big gains if random I/O has higher
  latency"; supplied grammatically clean and recorded verbatim under
  `## Question`). Same unchanged pin `54eeefaedbee0385529f3edf321bb99e49232aaa`,
  drafted from a claim-to-source map built directly from `raw/postgres-17/`.
  Locking: expansion/locking runs before costing (`planmain.c` `query_planner`:
  `add_other_rels_to_query` before `make_one_rel`); plan-time pruning is the only
  optimization that reduces read locks because `expand_partitioned_rtentry` prunes
  to `live_parts` before `try_table_open` locks the survivors, whereas inheritance
  locks every member up front via `find_all_inheritors` and constraint exclusion
  (`set_append_rel_size` -> `relation_excluded_by_constraints` ->
  `set_dummy_rel_pathlist`) runs only afterward; run-time pruning keeps all locks
  because `AcquireExecutorLocks` locks every `RTE_RELATION` in the finished plan's
  rtable; write-path routing (`ExecInitPartitionInfo`) takes `RowExclusiveLock`
  lazily per touched leaf, and cross-partition `UPDATE` writes two. Random I/O:
  `random_page_cost` = 4.0 vs `seq_page_cost` = 1.0 (`cost.h`/`costsize.c`), the
  docs advise raising for magnetic/less-cached storage, index-scan heap fetches
  are charged at `random_page_cost` (`cost_index`) and seq scans at
  `seq_page_cost` (`cost_seqscan`), so the scan-eliminating optimizations win most
  on high-latency random storage. Key v17-vs-v12 difference: v17 hash aggregation
  spills to disk (`nodeAgg.c` spill mode; limit `work_mem × hash_mem_multiplier`
  via `get_hash_memory_limit`) and `cost_agg` prices spill writes at
  `random_page_cost`, so partitionwise aggregate gains under slow random I/O by
  avoiding the spill; partitionwise-join batch spills stay `seq_page_cost`
  (`initial_cost_hashjoin`). Updated `## Contents`, `## Question` (follow-up),
  Evidence Map, Context Reviewed, Open Questions, and Source References; refreshed
  `wiki/index.md`, `wiki/v17/index.md`, and the v17 coverage cell.
  `verified_by_agent` stays `not yet`: scoped follow-up, not a full
  claim-by-claim re-verification.
- 2026-07-09: filed [Table Partitioning Optimizations and Configuration During
  Query Planning and Execution in PostgreSQL 17
  (unverified)](v17/questions/query-planning/partitioning-planning-execution-optimizations.md)
  against pin `54eeefaedbee0385529f3edf321bb99e49232aaa`. Applied prompt hygiene:
  the asker approved a grammar-corrected restatement (recorded under
  `## Question`). Drafted from a claim-to-source map built directly from
  `raw/postgres-17/`: the inheritance-vs-declarative split; plan-time constraint
  exclusion (`relation_excluded_by_constraints`); declarative plan-time pruning
  (`expand_partitioned_rtentry` prunes via `prune_append_rel_partitions` before
  locking only `live_parts` with `try_table_open`) and run-time pruning on
  `Append`/`MergeAppend` (`make_partition_pruneinfo`, `ExecInitPartitionPruning`
  / unified `ExecFindMatchingSubPlans`); per-HASH/LIST/RANGE bound matching
  (`perform_pruning_base_step` + `get_matching_*_bounds`); partitionwise join
  with merged non-identical bounds (`build_joinrel_partition_info` /
  `have_partkey_equi_join` / `compute_partition_bounds` -> `partition_bounds_merge`);
  partitionwise aggregate FULL/PARTIAL (`create_ordinary_grouping_paths` /
  `group_by_has_partkey`); executor tuple routing (`ExecFindPartition` /
  `get_partition_for_tuple` with last-found cache), cross-partition UPDATE row
  movement (`ExecCrossPartitionUpdate`), and per-partition COPY batching
  (`CIM_MULTI_CONDITIONAL`); and the four `PGC_USERSET` GUCs with defaults. Added
  an "optimizations since v12" section attributing (via the checkout's own
  `Stamp HEAD as NNdevel` brackets) v13 advanced partitionwise join
  (`c8434d64ce0`), v14 run-time pruning for `UPDATE`/`DELETE`/`ModifyTable`
  (`86dc90056df`; v12 doc caveat removed by `1692d0c3a3f`) and
  `DETACH PARTITION CONCURRENTLY` (`71f4c8c6f74`), v15 `live_parts` bitmap
  (`475dbd0b718`) / run-time-prune refactor (`297daa9d435`) / `MERGE`
  (`7103ebb7aae`), v16 cached tuple routing (`3592e0ff98b`), and v17
  `boolcol IS [NOT] UNKNOWN` pruning (`07c36c1333e`) + concurrent-detach
  robustness (`11f1218ce81`). Updated `wiki/index.md`, `wiki/v17/index.md`, and
  the v17 coverage cell. `verified_by_agent` stays `not yet`: fresh draft, not a
  claim-by-claim re-verification.
- 2026-07-09: extended [Table Partitioning Optimizations and Configuration During
  Query Planning and Execution in PostgreSQL 12
  (unverified)](v12/questions/query-planning/partitioning-planning-execution-optimizations.md)
  with a new `## Locking reduction and random-I/O sensitivity per optimization`
  section for the approved, grammar-corrected follow-up ("how each optimization
  will reduce locking, and how each will have big gains if random I/O has higher
  latency"; original wording recorded under `## Question`). Same unchanged pin
  `45b88269a353ad93744772791feb6d01bc7e1e42`, drafted from a claim-to-source map
  built directly from `raw/postgres-12/`. Locking: expansion/locking runs before
  costing (`planmain.c` `add_other_rels_to_query` -> `make_one_rel`); plan-time
  pruning is the only optimization that reduces read locks because
  `expand_partitioned_rtentry` calls `prune_append_rel_partitions` before
  `table_open(childOID, lockmode)` on the surviving `live_parts`, whereas
  inheritance locks every member up front via `find_all_inheritors` and
  constraint exclusion (`relation_excluded_by_constraints` in
  `set_append_rel_size`) runs only afterward; run-time pruning keeps all locks
  because `AcquireExecutorLocks` locks every `RTE_RELATION` in the finished plan's
  rtable; write-path routing (`ExecInitPartitionInfo`) takes `RowExclusiveLock`
  lazily per touched partition, and cross-partition `UPDATE` locks two. Random
  I/O: `random_page_cost` = 4.0 vs `seq_page_cost` = 1.0 (`cost.h`/`costsize.c`),
  the docs note the 4.0 default assumes ~90% cache and should be raised for slow
  random storage, index-scan heap fetches are charged at `random_page_cost`
  (`cost_index`) and seq scans at `seq_page_cost` (`cost_seqscan`), so the
  scan-eliminating optimizations (pruning, constraint exclusion) win most on
  high-latency random storage; partitionwise join/aggregate are CPU/memory/
  locality wins, not random-I/O ones (v12 costs hash-join `BufFile` spill as
  sequential in `initial_cost_hashjoin`, and hash aggregation `build_hash_table`
  is in-memory). Updated `## Contents`, `## Question` (follow-up), Evidence Map,
  Context Reviewed, Open Questions, and Source References; refreshed
  `wiki/index.md`, `wiki/v12/index.md`, and the v12 coverage cell.
  `verified_by_agent` stays `not yet`: scoped follow-up, not a full
  claim-by-claim re-verification.
- 2026-07-09: filed [Table Partitioning Optimizations and Configuration During
  Query Planning and Execution in PostgreSQL 12
  (unverified)](v12/questions/query-planning/partitioning-planning-execution-optimizations.md)
  against the unchanged pin `45b88269a353ad93744772791feb6d01bc7e1e42`. Applied
  prompt hygiene: the asker approved a grammar-corrected restatement (recorded
  under `## Question`). Drafted from a claim-to-source map built directly from
  `raw/postgres-12/`: partition pruning (plan-time `prune_append_rel_partitions`
  invoked from `expand_partitioned_rtentry` before child expansion, so pruned
  partitions never become child rels; run-time initial + per-scan pruning via
  `ExecFindInitialMatchingSubPlans`/`ExecFindMatchingSubPlans` on
  `Append`/`MergeAppend`, gated by `enable_partition_pruning` in
  `prune_append_rel_partitions` and `createplan.c`) with per-strategy HASH/LIST/
  RANGE differences in `get_matching_hash_bounds`/`get_matching_list_bounds`/
  `get_matching_range_bounds` and `get_partition_for_tuple`; constraint exclusion
  (`relation_excluded_by_constraints` switch on `constraint_exclusion` modes,
  plan-time only, mainly legacy inheritance); partitionwise join
  (`build_joinrel_partition_info` gate + `have_partkey_equi_join` +
  `partition_bounds_equal`) and partitionwise aggregate (`create_grouping_paths`
  patype, `group_by_has_partkey` FULL-vs-PARTIAL); executor tuple routing,
  cross-partition UPDATE row movement (DELETE+INSERT), and per-partition COPY
  multi-insert; the four session-scoped GUCs with defaults; and the v12
  limitation that execution-time pruning covers only `Append`/`MergeAppend`, not
  `ModifyTable`. Updated `wiki/index.md`, `wiki/v12/index.md`, and the v12
  coverage cell. `verified_by_agent` stays `not yet`: fresh draft, not a
  claim-by-claim re-verification.
- 2026-07-07: review-fixed the same v14 RLS sub-SELECT follow-up to remove an
  uncited external-helper assumption. The PostgreSQL 14 source still proves the
  uncorrelated scalar sub-SELECT -> InitPlan -> `PARAM_EXEC` once-per-execution
  behavior, including inside RLS policy expressions, but the exact definitions
  and volatility declarations of external helpers such as `auth.uid()` and
  `auth.jwt()` are now listed as an Open Question to verify in the installed
  schema. Tightened the answer lead to note the main performance win is when the
  unwrapped call would otherwise be a per-row filter; index-qualifiable
  comparisons may already evaluate a `STABLE` function once per scan as a
  runtime key. `verified_by_agent` stays `not yet`: scoped review-fix, not a
  full claim-by-claim re-verification.
- 2026-07-07: review-fixed the `### Wrapping a function in a subquery to
  evaluate it once` section of [Row-Level Security (RLS) in PostgreSQL 14
  (unverified)](v14/questions/server-administration/row-level-security-rls.md) against the unchanged
  pin `5c00f4e2e3b`. Re-verified every source citation in the section (the
  `subselect.c` uncorrelated-`EXPR_SUBLINK`-to-InitPlan / `PARAM_EXEC` path and
  correlated-`SubPlan` contrast, `ExecEvalParamExec`/`ExecSetParamPlan`
  once-only param caching, `ExecScan`/`EEOP_FUNCEXPR` per-tuple evaluation, the
  `clauses.c` `STABLE`-not-folded rule, `ExecReScanIndexScan` runtime keys,
  `policy.c` `hassublinks`, `rewriteHandler.c` policy-sublink handling, and
  `pg_proc.dat` `current_setting` `provolatile => 's'`); all line ranges are
  accurate. Fixed one citation-completeness gap: the claim that `WITH CHECK`
  options also flow through `preprocess_expression`/`SS_process_sublinks` cited
  only the `securityQuals` loop, so added the `WITH CHECK` preprocessing loop
  citation (`planner.c` L818-L828) in the body, Evidence Map, and Context
  Reviewed. `verified_by_agent` stays `not yet`: scoped review-fix, not a full
  claim-by-claim re-verification.
- 2026-07-07: review-fixed [Performance Implications of Functions and
  Procedures in a WHERE Clause in PostgreSQL 14, and How to Minimize the
  Overhead (unverified)](v14/questions/query-planning/functions-procedures-in-where-clause.md)
  against the unchanged pin `5c00f4e2e3b`. Corrected the overbroad claim that a
  WHERE-clause function is always a per-row cost: row-dependent or volatile
  quals still run through the `ExecScan`/`ExecQual`/`EEOP_FUNCEXPR` per-row path,
  but a no-`Var`, non-volatile qual is marked pseudoconstant, costed as startup
  work, and executed once as a gating `Result` / `One-Time Filter`. Tightened
  the `STABLE` caveat, the scalar sub-SELECT mitigation caveat, the `COST`
  default wording (`CREATE FUNCTION` defaults to 1 for C/internal and 100
  otherwise), and the expression-index/generated-column immutability citations.
  Updated `wiki/index.md`, `wiki/v14/index.md`, and the v14 coverage cell.
  `verified_by_agent` stays `not yet`: scoped review-fix, not a full
  claim-by-claim re-verification.
- 2026-07-07: filed [Performance Implications of Functions and Procedures in a
  WHERE Clause in PostgreSQL 14, and How to Minimize the Overhead
  (unverified)](v14/questions/query-planning/functions-procedures-in-where-clause.md) against
  the unchanged pin `5c00f4e2e3b`. Applied prompt hygiene: the asker approved a
  grammar-corrected restatement (recorded under `## Question`) and chose to
  cover procedures explicitly. Drafted from a claim-to-source map built directly
  from `raw/postgres-14/`: procedures (`prokind='p'`) are rejected in every
  expression context by `ParseFuncOrColumn` and run only via the `CALL` utility
  statement (`gram.y`/`transformCallStmt`/`ExecuteCallStmt`, with a
  `create_procedure.out` test); row-dependent or volatile WHERE-clause functions
  are per-row costs (`ExecScan` qual loop -> `ExecQual` -> `EEOP_FUNCEXPR` fmgr
  dispatch), while no-`Var`, non-volatile quals can run once as pseudoconstant
  gating `Result` filters; volatility effects (`VOLATILE` per row where needed,
  `STABLE` single-evaluation as an index-scan comparison value via
  `ExecReScanIndexScan`/`ExecIndexEvalRuntimeKeys` or as a no-`Var` one-time qual,
  `IMMUTABLE` constant-folded by `eval_const_expressions`/`evaluate_function`);
  the cost model (`add_function_cost` = `procost * cpu_operator_cost`, omitted
  `CREATE FUNCTION COST` default 1 for C/internal functions and 100 otherwise)
  and fixed default selectivity (`function_selectivity` 0.3333333, `boolvarsel`
  0.5); expression-index matching (`match_index_to_operand`) and the
  non-volatile-operand runtime-key rule (`match_opclause_to_indexcol`);
  leakproof/security-level qual ordering (`order_qual_clauses`,
  `RestrictInfo.security_level`, `qual_is_pushdown_safe`); parallel-safety
  (`PROPARALLEL_*`, `planner.c` parallel-mode gate, `parallel.sgml`); and the
  mitigations (volatility labeling, expression indexes/generated columns,
  uncorrelated scalar sub-SELECT -> once-per-execution InitPlan via
  `build_subplan`/`ExecEvalParamExec`, SQL-function inlining `inline_function`,
  `COST`/`ROWS`, planner `SUPPORT` functions `supportnodes.h`, `LEAKPROOF`/
  `PARALLEL SAFE`). Updated `wiki/index.md`, `wiki/v14/index.md`, and the v14
  coverage cell. `verified_by_agent` stays `not yet`: fresh draft, not a
  claim-by-claim re-verification.
- 2026-07-07: extended [Row-Level Security (RLS) in PostgreSQL 14
  (unverified)](v14/questions/server-administration/row-level-security-rls.md) with a `### Wrapping a
  function in a subquery to evaluate it once` section for the approved,
  grammar-corrected follow-up on whether wrapping a JWT helper like `auth.uid()`
  in `(SELECT auth.uid())` caches the call. Documented from `raw/postgres-14/`:
  an uncorrelated scalar sub-SELECT becomes an InitPlan whose `PARAM_EXEC` result
  is evaluated once per execution and reused (`build_subplan` EXPR_SUBLINK path,
  `ExecSetParamPlan`/`ExecEvalParamExec`); the sublink is expanded even inside a
  policy because security quals and `WITH CHECK` options run through
  `SS_process_sublinks`; a bare `STABLE` function is not constant-folded and is
  re-invoked per row as a scan filter (`ExecScan`/`EEOP_FUNCEXPR`); the
  index-runtime-key nuance (a `STABLE` function on an index-qualifiable
  comparison is already evaluated once per scan); and the correlated-sub-SELECT
  and once-per-execution caveats. Noted that `auth.uid()`/`auth.jwt()` are
  external functions absent from the pin, and originally compared the common
  claim-reader pattern with core `current_setting`; a later same-day review note
  above narrows that to a verification caveat. Updated `wiki/index.md`,
  `wiki/v14/index.md`, and the v14 coverage cell; `verified_by_agent` stays `not
  yet` because this was a scoped follow-up, not a full claim-by-claim
  re-verification.
- 2026-07-07: review-fixed [Row-Level Security (RLS) in PostgreSQL 14
  (unverified)](v14/questions/server-administration/row-level-security-rls.md) for the approved,
  grammar-corrected aggregation follow-up. Added an `### RLS and aggregation`
  section explaining that aggregate nodes consume the RLS-filtered input
  subplan, so mitigation focuses on cheaper/indexable policy predicates,
  leakproof/indexable filters, partition pruning and session-scoped
  `enable_partitionwise_aggregate`, stable role/`row_security` plan-cache
  environments, or deliberately trusted/pre-aggregated reporting paths. Also
  documented that `row_security = off` errors for subject users rather than
  bypassing RLS, and that aggregate calls are rejected inside policy
  expressions. Updated `wiki/index.md` and `wiki/v14/index.md`;
  `verified_by_agent` stays `not yet` because this was a scoped follow-up, not
  a full claim-by-claim re-verification.
- 2026-07-07: review-fixed [Row-Level Security (RLS) in PostgreSQL 14
  (unverified)](v14/questions/server-administration/row-level-security-rls.md) against the unchanged
  pin `5c00f4e2e3b`. Corrected the RLS plan-cache section to avoid treating SQL
  `DECLARE CURSOR` / `WITH HOLD` cursors as a saved-plan-cache reuse surface
  (ordinary cursor planning stores copied plan trees in a portal; held cursors
  survive by materializing rows), added `plan_cache_mode` as an RLS-relevant
  `PGC_USERSET` setting controlling generic-vs-custom prepared-statement
  planning, fixed the distinct `SET ROLE` vs `SET SESSION AUTHORIZATION` call
  paths, and cited pg_dump's default `row_security = off` behavior. Updated
  `wiki/index.md` and `wiki/v14/index.md`; `verified_by_agent` stays `not yet`
  because this was a scoped review-fix, not a full claim-by-claim
  re-verification.
- 2026-07-06: filed the PostgreSQL 14 MultiXact question page, [How MultiXact
  Works in PostgreSQL 14, and How Foreign Keys and Other Operations Degrade
  Performance When the Local Cache Spills to Secondary Storage
  (unverified)](v14/questions/storage-and-vacuum/multixact-foreign-keys-cache-spill.md), against the
  unchanged pin `5c00f4e2e3b`. Applied prompt hygiene: the asker approved a
  lightly grammar-corrected restatement, recorded under `## Question`. Drafted
  from a claim-to-source map built directly from `raw/postgres-14/`: the MultiXact
  manager (`multixact.c`) — two SLRUs, `MultiXactStateData`, the create/read
  paths, and the 256-entry per-transaction local cache with LRU tail eviction;
  the SLRU layer (`slru.c`) — exclusive-locked reads, buffer-miss physical
  `pg_pread`/`SLRURead`, victim selection and I/O waits; the row-lock producers
  (`heapam.c` `compute_new_xmax_infomask`/`heap_lock_tuple`, `heapam_handler.c`,
  `ri_triggers.c` `FOR KEY SHARE`); member-space guards and
  `MultiXactMemberFreezeThreshold`; the vacuum GUC contexts (`guc.c`);
  observability (`pg_stat_slru`, wait-event names, `mxid_age`,
  `pg_get_multixact_members`); the `fk-contention` isolation test; and the
  "Multixacts and Wraparound" docs. Updated `wiki/index.md`, `wiki/v14/index.md`,
  and the v14 coverage cell above. `verified_by_agent` stays `not yet`: fresh
  draft, not a claim-by-claim re-verification.
- 2026-06-30: filed the first PostgreSQL 14 question page, [Row-Level Security
  (RLS) in PostgreSQL 14 (unverified)](v14/questions/server-administration/row-level-security-rls.md),
  against the unchanged pin `5c00f4e2e3b`. Drafted from a claim-to-source map
  built directly from the `raw/postgres-14/` checkout: the rewrite path
  (`get_row_security_policies`, `fireRIRrules`), the bypass decision
  (`check_enable_rls`, `has_bypassrls_privilege`, `InNoForceRLSOperation`),
  `pg_policy`/`pg_class`/`pg_authid` catalogs, the relcache build
  (`RelationBuildRowSecurity`), the planner `security_level`/`order_qual_clauses`
  leakproof mechanism and inheritance handling, executor `ExecWithCheckOptions`,
  plan-cache `dependsOnRLS` re-planning, the COPY/CTAS/RI/error-leak boundaries,
  and all settings (`row_security` GUC, the `ALTER TABLE` table flags, the
  `BYPASSRLS` role attribute, `CREATE`/`ALTER POLICY` options, and the two
  extension hooks). Confirmed v14 has no `prepsecurity.c` (RLS quals flow through
  the `qual_security_level` machinery). Updated `wiki/index.md`,
  `wiki/v14/index.md`, and the v14 coverage cell above. `verified_by_agent`
  stays `not yet`: this is a fresh draft, not a claim-by-claim re-verification.
- 2026-06-30: added PostgreSQL 14 as a supported (`active`) version. Created the
  `raw/postgres-14/` source checkout and pinned it to the `REL_14_STABLE` tip
  `5c00f4e2e3bcee6931ae93429d53f7c2a4f46156` (`REL_14_23-3-g5c00f4e2e3b`, three
  commits past the 14.23 release stamp; source version 14.23), mirroring how
  v17/v18 pin to their `_STABLE` tips. The checkout was built offline by local
  clone from the existing `raw/postgres-12/` repo (which already carried the
  `REL_14_STABLE` objects and all REL_14 tags), then its `origin` was set to
  `https://github.com/postgres/postgres.git`; working tree is clean at the pin.
  Filed the mandatory [PostgreSQL 14 Codebase Navigation Guide
  (unverified)](v14/codebase-navigation-guide.md) and the
  [v14/index](v14/index.md) landing page, with every guide citation verified
  against the v14 checkout (line numbers differ from v17, and v14's subsystem
  layout genuinely differs — no backend `archive`/`backup` dirs, no storage
  `aio` dir, a single `pg_analyze_and_rewrite`, and catalog headers generated by
  the backend catalog makefile rather than `src/include/catalog/`).
  `verified_by_agent` stays `not yet`: this was a version-add scaffold, not a
  claim-by-claim re-verification.
- 2026-06-29: reviewed [PostgreSQL 18 Row-Level Security
  (unverified)](v18/questions/server-administration/row-level-security-rls.md) against the unchanged
  pin `6cb307251c`. Re-verified that all 120 unique source citations bracket
  their named symbols, spot-checked the most claim-sensitive source
  (`row_security` GUC, `check_enable_rls()`, the RLS `COPY`/pg_dump paths, the
  CVE-2025-8713 evidence), and independently rebuilt the fixes and
  minor-release-first-appearance provenance from local history — all 20 fix
  hashes, the five CVEs, the four not-back-patched fixes, every back-patch
  reach, and every per-branch first-release tag still hold. Two value
  corrections: the `bd3611db5a` row's 13.5/12.9 minor date `2021-11-11` ->
  `2021-11-08` (the `REL_12_9`/`REL_13_5` stamp date, matching the page's stated
  method), and the `CREATE POLICY`-statement count `97` -> `100` in the
  performance section. `verified_by_agent` stays `not yet`: scoped review-fix,
  not a full claim-by-claim re-verification.
- 2026-06-29: moved the `raw/postgres-19/` source checkout to the declared pin
  `cdae794af31b3e9cfc323fc654292d86fa746f77`. The 2026-06-26 repin updated every
  `wiki/v19/**` page's `pinned_commit:` and line anchors to `cdae794a` but left
  the standalone source checkout at the prior pin `9a60f295` (which does not
  contain `cdae794a`), so page citations could not be verified against the
  evidence base. Fetched upstream `master`+tags and checked out `cdae794a`
  (26 commits ahead of `9a60f295`; tip "Take into account default_tablespace
  during MERGE/SPLIT PARTITION(S)"). Then reviewed the commit sections of all
  three v19 question pages against the pin and verified every listed commit for
  hash, subject, author, and ancestry: `pg_plan_advice` (50 commits: 20 core, 22
  module, 8 support; exact 22-commit module completeness), `REPACK` (42
  feature-scope commits; completeness re-checked by file-path and subject grep),
  and autovacuum/VACUUM (24 commits plus `f83d709760d`/`4abf411e232`/
  `a7f59b252a8`; post-beta1 and repin-range claims confirmed). One correction:
  `pg_plan_advice` `47c110f7` had used its commit date `2026-03-26`; switched to
  the author date `2026-03-20` to match the author-date convention the other two
  pages use, with a "Dates are author dates." note added and the `b3a95566`
  repin-range wording tightened. `verified_by_agent` remains `not yet` on all
  v19 pages: this was a commit-section review, not a full claim-by-claim
  re-verification.
- 2026-06-26: repinned PostgreSQL 19 from `9a60f295` to
  `cdae794af31b3e9cfc323fc654292d86fa746f77` after fetching upstream `master`
  and tags (26 new commits; new tip `cdae794a`, 2026-06-26, "Take into account
  default_tablespace during MERGE/SPLIT PARTITION(S)"). Reviewed all v19
  question pages and the codebase navigation guide against the changed-file
  range. No `pg_plan_advice`, REPACK-specific, or
  autovacuum/scoring/parallel-vacuum/visibility feature files changed in
  `9a60f295..cdae794a`; relevant commit references were added as review notes:
  `b3a95566` only touched the out-of-scope `pg_stash_advice` module,
  `4abf411e232` changed `pg_stat_io` autovacuum-launcher accounting outside the
  filed autovacuum feature scope, and `a7f59b252a8` shifted
  `guc_parameters.dat` line anchors. Refreshed GUC citations on the REPACK and
  autovacuum pages and `execnodes.h` line anchors in the codebase guide.
  `verified_by_agent` remains `not yet` on v19 pages because this was a repin
  and changed-file review, not a full claim-by-claim re-verification.
- 2026-06-22: repinned PostgreSQL 19 from `ff8bec8c` to
  `9a60f295bcb186a729d04e76377b7f122b2a1dd9` after fetching upstream `master`
  (16 new commits; new tip `9a60f295`, 2026-06-22, "Strip removed-relation
  references from PlaceHolderVars at join removal"). Reviewed all v19 question
  pages and the codebase navigation guide against the changed-file range. Only
  one changed file is cited by any v19 page — `autovacuum.c` on the autovacuum
  scoring page — and only the autovacuum MXID-score division-by-zero fix
  `1f2297b5487` (post-`REL_19_BETA1`, touching `autovacuum.c` and
  `maintenance.sgml`) is relevant to filed coverage. Updated [PostgreSQL 19
  Autovacuum and VACUUM (unverified)](v19/questions/storage-and-vacuum/autovacuum-parallel-scoring-visibility.md):
  documented the `Max(1, multixact_freeze_max_age)` divisor guard and the
  member-space scaling, added `1f2297b5487` to the scoring commit history,
  corrected the now-stale "no autovacuum feature files changed since beta1"
  note, and shifted the four post-line-3048 `autovacuum.c` citations
  (`L3064-L3078`->`L3067-L3081`, `L3195-L3238`->`L3198-L3243`,
  `L3239-L3240`->`L3244-L3245`, `L3287-L3315`->`L3292-L3320`). Verified no
  `pg_plan_advice`, `REPACK`, or visibility-map/pruning feature files changed in
  the range, so those pages took only the pin bump. `verified_by_agent` remains
  `not yet` on all v19 pages: this was a repin and changed-file review, not a
  full claim-by-claim re-verification.
- 2026-06-19: resolved the remaining PostgreSQL 18 Row-Level Security open
  question — minor-release first-appearance labels. Against the unchanged pin
  `6cb307251c` (a `REL_18_STABLE` commit; that branch forked from master at
  `9c5b9a280c` on 2025-06-29), traced each of the 20 `### Fixes Since PostgreSQL
  12` fixes by finding every same-subject commit across all refs
  (`git log --all --fixed-strings --grep`) and mapping each distinct per-branch
  cherry-pick to its earliest containing release tag
  (`git tag --contains | grep '^REL_NN_M$' | sort -V | head -1`), with tag stamp
  dates from `git log -1 --format=%cs`. Added a `### Minor-Release First
  Appearance` section and table giving each fix's master development-cycle major
  plus its first minor release on every tracked v12+ branch, the back-patch
  reach, and coordinated release dates. Key findings: 16 of 20 fixes were
  back-patched (so they first shipped in coordinated back-branch minors that
  precede the master `.0`), 4 were not back-patched (`a2ab9c06ea`->15.0,
  `6572bd55b0`->17.0, `0dca5d68d7`->18.0, `cd3c45125d`->18.0), and two listed
  hashes (`64f77c6a65` CVE-2025-8713, `749f4ce4d9` doc fix) are REL_18_STABLE
  back-patch commits — not master commits — whose master commits
  (`22424953cde`, `7dc4fa91413`) are on the unreleased v19 line; corrected the
  Fixes-table intro accordingly. Removed the resolved open-question bullet and
  updated Contents, Context Reviewed, Evidence Map, and the index/landing
  summaries. `verified_by_agent` stays `not yet`: this was a targeted
  open-question investigation, not a full-page re-verification.
- 2026-06-19: re-investigated and resolved the commit-provenance open question on
  the PostgreSQL 18 Row-Level Security page now that `raw/postgres-18/` is
  unshallowed (the follow-up the unshallow note below flagged). Against the
  unchanged pin `6cb307251c` (`REL_18_3-113-g6cb307251c5`), verified with `git`
  that all 20 commits in the page's `### Fixes Since PostgreSQL 12` table exist,
  that their subjects match the summaries, and that each is an ancestor of the
  pin and a descendant of the v13 development stamp `615cebc94b5` (2019-07-01);
  confirmed the five RLS CVEs (CVE-2023-2455, -2023-39418, -2024-4317,
  -2024-10976, -2025-8713); and corrected the `d907bd0543` row, which had
  described "altering BYPASSRLS-bearing roles" but actually fixed an over-broad
  superuser requirement on *any* property change of a BYPASSRLS role. A
  completeness scan of `615cebc94b5..6cb307251c` (core RLS files plus an
  RLS/policy/WCO/CVE keyword search) found no significant standalone RLS fix
  missing; the extra commits are companion/follow-up fixes to already-listed
  areas, docs/wording/cosmetic changes, or the v15 security-invoker-views
  feature already covered. Relabeled the table's `Unverified fix description`
  column to `Fix description`, rewrote the table intro and the Open Questions /
  Context Reviewed / Evidence Map provenance items, and refreshed the
  shallow-caveat wording in the v18 row above and the `index.md` / `v18/index.md`
  summaries. Minor-release first-appearance labels remain open (most fixes were
  back-patched to all supported branches, so the first shipping minor release
  needs per-branch cherry-pick tracing). `verified_by_agent` stays `not yet`:
  this was a targeted open-question investigation, not a full-page
  re-verification.
- 2026-06-19: unshallowed the `raw/postgres-18/` source checkout at the user's
  request (`git fetch --unshallow --tags origin`), converting it from a depth-1,
  single-commit clone (1 commit, 0 tags) to full history. The pin is unchanged:
  HEAD stays at `6cb307251c5c6261286c1566496920976640108e`, which `git describe`
  now resolves as `REL_18_3-113-g6cb307251c5` on `origin/REL_18_STABLE`; the
  working tree is clean and the checkout now holds 62,317 commits and 685 tags
  (parity with the v17/v12 checkouts). No `pinned_commit:` value changed on any
  of the 15 `wiki/v18/**` pages and no source-citation line numbers shift, so
  this is not a repin. This lifts the shallow-checkout limitation previously
  cited as the reason v18 commit provenance was left open (the RLS page Open
  Questions and the v18 row/summaries below): local `git log`/tags can now verify
  it. That provenance has not been re-investigated yet, so those "shallow" notes
  remain to be refreshed when it is. `raw/postgres-12/`, `raw/postgres-17/`, and
  `raw/postgres-19/` were left untouched.
- 2026-06-19: investigated the first `## Open Questions` item on the PostgreSQL
  18 Row-Level Security page against pinned commit
  `6cb307251c5c6261286c1566496920976640108e` — whether the checkout has a
  benchmark that quantifies RLS overhead by policy/role/partition count or
  predicate shape. Confirmed it does not: the tree's benchmark/perf tooling
  (`pgbench`, `contrib/intarray/bench`, the ecpg and JSON-parser perf tests) has
  no RLS scenario, the RLS regression and hook tests use only
  `EXPLAIN (COSTS OFF)` plan-shape checks (no timing primitives), and the docs
  give only qualitative guidance. Expanded `### Scalability and Performance
  Issues`, added Context Reviewed and Evidence Map entries, and removed the
  resolved open-question bullet. `verified_by_agent` stays `not yet` because
  this was a targeted open-question investigation, not a full-page
  re-verification.
- 2026-06-19: reviewed the `### Can walsenders or replication-slot xmin holders
  appear in the Wait 3 set?` section of the PostgreSQL 12 `CREATE INDEX
  CONCURRENTLY` page against pinned commit
  `45b88269a353ad93744772791feb6d01bc7e1e42`. Re-verified the three independent
  reasons walsenders/slots stay out of `WaitForOlderSnapshots`: (1) slot xmin is
  a global `procArray->replication_slot_xmin`/`replication_slot_catalog_xmin`
  that `GetCurrentVirtualXIDs` never reads (only `GetOldestXmin` and
  `GetSnapshotData`'s `RecentGlobalXmin` do); (2) a physical walsender connects
  to no database and `GetCurrentVirtualXIDs` lacks `GetOldestXmin`'s "always
  include WalSender" clause; (3) the valid-VXID gate plus the `lxid`/`xmin` clear
  in `ProcArrayEndTransaction`. Confirmed the only in-set walsender is a logical
  one mid-`REPEATABLE READ` snapshot export (`SnapBuildInitialSnapshot`), an
  ordinary in-database holder. Verified xmin-setter exhaustiveness by grepping
  all `(MyPgXact|pgxact)->xmin =` sites. Conclusion holds. Fixed one precision
  error shared by the body and an Evidence Map row: `xmin` is not "set in
  `StartTransaction`" (only `lxid` is; `xmin` is set at snapshot time), so
  reworded to state that an ordinary backend only advertises xmin from within a
  transaction and `lxid`/`xmin` are cleared together at transaction end.
  `verified_by_agent` stays `not yet` because this was a scoped section review,
  not a full-page re-verification.
- 2026-06-19: reviewed the `### Is skipping prepared transactions in the writer
  waits safe?` section of the PostgreSQL 12 `CREATE INDEX CONCURRENTLY` page
  against pinned commit `45b88269a353ad93744772791feb6d01bc7e1e42`. Re-verified
  every claim and citation: the `lmgr.c` "prepared xacts certainly aren't going
  to do anything anymore" comment; the `validate_index` "terminate"/"inserted by
  their originating transaction" invariant; the Wait 1 HOT-safety comment;
  `MarkAsPreparingGuts` setting the dummy proc's `xid` to the real XID but
  `xmin`/`backendId` invalid; the `GetLockConflicts` invalid-VXID drops and the
  `VirtualTransactionIdIsValid` `backendId` check; the Wait 3 `xmin`/VXID filter;
  the `SnapshotAny` `INSERT_IN_PROGRESS` branch vs. the MVCC `else` branch;
  `FinishPreparedTransaction` doing no index work; the not-ready-index insert
  skip; and the non-concurrent `ShareLock`-vs-`RowExclusiveLock` contrast. Also
  confirmed the negative claims (no "prepared" mention in `create_index.sgml`, no
  prepared/two-phase handling in `indexcmds.c`). The "Not on its own [safe]"
  conclusion holds. Fixed one precision error: the writer-wait bullet implied the
  prepared xact's invalid VXID is dropped in "both the fast-path and
  primary-table scans," but its `RowExclusiveLock` is transferred to the primary
  lock table at prepare, so it is encountered and dropped only in the
  primary-table scan; reworded to say both `GetLockConflicts` scan phases drop
  invalid VXIDs in general while the prepared xact hits only the primary-table
  one. `verified_by_agent` stays `not yet` because this was a scoped section
  review, not a full-page re-verification.
- 2026-06-19: reviewed the `## Open Questions` section of the PostgreSQL 12
  `CREATE INDEX CONCURRENTLY` page against pinned commit
  `45b88269a353ad93744772791feb6d01bc7e1e42`. Re-verified every crash /
  immediate-shutdown citation behind the "None for source behavior" conclusion
  (xidless `heap_inplace_update` flag flips, the async-commit branch,
  `heap_xlog_inplace` physical redo, `XLogFlush`-through-position monotonicity,
  and the `DB_SHUTDOWNED` recovery trigger) — the conclusion holds. Closed one
  precision gap: the "recovered valid index is always complete" argument cited
  build durability only for B-tree (`smgrimmedsync`); verified the other five
  core AMs (hash/GiST/SP-GiST/GIN/BRIN) make build pages durable before
  SET_VALID through shared-buffer WAL (`log_newpage_range` / buffered build
  path), and that unlogged tables reset heap and indexes together on crash.
  Rewrote the completeness paragraph to be AM-general, split the Evidence Map
  completeness row and added an unlogged-reset row, added Source References and
  a Context Reviewed entry, and tightened the `## Open Questions` text while
  keeping the "None" marker. `verified_by_agent` stays `not yet` because this
  was a scoped review, not a full-page re-verification.
- 2026-06-19: expanded PostgreSQL 12 `CREATE INDEX CONCURRENTLY` coverage
  against pinned commit `45b88269a353ad93744772791feb6d01bc7e1e42` to resolve
  the crash / immediate-shutdown recovery open question. Source-level
  conclusion: a crash or `immediate` shutdown leaves the same four states as an
  ERROR/cancel and never a valid-but-incomplete index. The state-flag flips run
  in XID-less transactions and are written by `heap_inplace_update`
  (`XLOG_HEAP_INPLACE`, page LSN set, no `XLogFlush`), so `RecordTransactionCommit`
  commits them asynchronously (`XLogSetAsyncXactLSN`, not `XLogFlush`) regardless
  of `synchronous_commit`; a flip therefore becomes durable only when the WAL
  writer, a checkpoint, or a later synchronous commit flushes WAL past its LSN.
  On recovery `heap_xlog_inplace` redoes the flip physically and unconditionally,
  so a flip can survive a phase that wrote no commit record, or be lost although
  `CommitTransactionCommand` returned — but never inconsistently: `XLogFlush`
  flushes WAL sequentially, so durable SET_VALID implies durable SET_READY (state
  monotone, never `(indisready=f, indisvalid=t)`), and a recovered valid index is
  always complete because the B-tree build `smgrimmedsync`s its file before the
  build transaction may commit and the validate scan's WAL precedes SET_VALID
  under the `FlushBuffer` WAL-before-data rule. Rewrote the
  `#### Server crash or immediate shutdown` subsection, added a recovered-state
  table, six Evidence Map rows, a Context Reviewed entry, eight Source References,
  and replaced the resolved `## Open Questions` bullet with the "none" marker.
  `verified_by_agent` stays `not yet` because this was a targeted expansion, not
  a full-page re-verification.
- 2026-06-19: expanded PostgreSQL 12 `CREATE INDEX CONCURRENTLY` coverage
  against pinned commit `45b88269a353ad93744772791feb6d01bc7e1e42` to resolve
  the walsender / replication-slot Wait 3 open question. Source-level
  conclusion: walsenders and replication-slot xmin holders do **not** appear in
  CIC's `WaitForOlderSnapshots` (Wait 3) set through replication's
  xmin-holdback machinery. A slot's reserved xmin/catalog_xmin lives in the
  global `procArray->replication_slot_xmin`/`replication_slot_catalog_xmin`
  (set by `ProcArraySetReplicationSlotXmin`), which `GetCurrentVirtualXIDs`
  never reads — only `GetOldestXmin` and `GetSnapshotData`'s
  `RecentGlobalXmin` do. A physical walsender that advertises its own
  `MyPgXact->xmin` via `hot_standby_feedback` (no slot) is filtered out by
  database — `InitPostgres` returns early for `am_walsender && !am_db_walsender`
  leaving `databaseId = InvalidOid`, and `GetCurrentVirtualXIDs`'s same-db test
  lacks `GetOldestXmin`'s `|| proc->databaseId == 0 /* always include
  WalSender */` clause — and by the valid-VXID gate. `lxid` and `xmin` are set
  in `StartTransaction` and cleared together in `ProcArrayEndTransaction`, so a
  non-transaction backend has neither. The only walsender that can be in the
  set is a logical walsender running `SnapBuildInitialSnapshot` inside a
  `REPEATABLE READ` transaction (slot creation/export), which is an ordinary
  in-database snapshot holder the page already covers. Added a new
  `### Can walsenders or replication-slot xmin holders appear in the Wait 3
  set?` section, Contents entry, a cross-referenced Point 4 bullet, six
  Evidence Map rows, a Context Reviewed entry, twelve Source References, and
  removed the resolved `## Open Questions` bullet. `verified_by_agent` stays
  `not yet` because this was a targeted expansion, not a full-page
  re-verification.
- 2026-06-18: expanded PostgreSQL 12 `CREATE INDEX CONCURRENTLY` coverage
  against pinned commit `45b88269a353ad93744772791feb6d01bc7e1e42` to resolve
  the prepared-transaction writer-wait open question. Source-level assessment:
  skipping prepared transactions in the two `WaitForLockers(ShareLock)` writer
  waits is not sufficient for index correctness. The `validate_index` /
  `DefineIndex` invariant requires that index-modifying transactions either
  terminate before the scans or insert their own tuples; a prepared transaction
  does neither. Its dummy proc carries the real (in-progress) `xid` but an
  invalid `xmin`/VXID, so the MVCC build and validate scans never see its
  writes, all three waits skip it, and `COMMIT PREPARED` does no index
  maintenance — a write committed after the build is left unindexed. Added a new
  `### Is skipping prepared transactions in the writer waits safe?` section,
  Contents entry, Evidence Map rows, Context Reviewed and Source References
  entries, and removed the resolved `## Open Questions` bullet.
  `verified_by_agent` stays `not yet` because this was a targeted expansion, not
  a full-page re-verification.
- 2026-06-18: expanded PostgreSQL 12 `CREATE INDEX CONCURRENTLY` coverage
  against pinned commit `45b88269a353ad93744772791feb6d01bc7e1e42` to resolve
  the first-build-scan tuple-visibility open question. The page now traces, line
  by line into the heap table AM, that a concurrent first scan
  (`index_concurrently_build` -> `index_build` -> `ambuild` ->
  `table_index_build_scan` -> `heapam_index_build_range_scan`) leaves
  `OldestXmin` invalid because of `!ii_Concurrent`, scans with a fresh MVCC
  snapshot, relies on `heapgetpage` -> `HeapTupleSatisfiesMVCC` for visibility,
  and therefore never indexes `RECENTLY_DEAD` tuples nor sets
  `ii_BrokenHotChain` (unlike the non-concurrent `SnapshotAny` build).
  `verified_by_agent` stays `not yet` because this was a targeted expansion, not
  a full-page re-verification.
- 2026-06-18: expanded PostgreSQL 12 `CREATE INDEX CONCURRENTLY` coverage
  against pinned commit `45b88269a353ad93744772791feb6d01bc7e1e42` to resolve
  the inter-builder open question. The page now distinguishes same-table CIC
  serialization by self-conflicting `ShareUpdateExclusiveLock`, different-table
  CIC/RIC interaction through the database-wide `WaitForOlderSnapshots` /
  `GetCurrentVirtualXIDs` old-snapshot wait, and the final no-`xmin` boundary
  that prevents mutual CIC snapshot-wait deadlocks. `verified_by_agent` was
  reset to `not yet` because this was a targeted update, not a full-page
  re-verification.
- 2026-06-18: filed PostgreSQL 12 `wal_sender_timeout` coverage against
  pinned commit `45b88269a353ad93744772791feb6d01bc7e1e42`. The page covers
  GUC scope/default/disable behavior, sender reply tracking, half-time
  keepalives and full-time disconnect, physical and logical streaming paths,
  publisher-side impact on logical subscriptions and `pg_recvlogical`, the
  subscriber-side `wal_receiver_*` distinction, monitoring and synchronous
  replication effects, replication-slot WAL retention, and the direct test
  coverage gap.
- 2026-06-18: filed PostgreSQL 18 `CREATE INDEX CONCURRENTLY` coverage
  against pinned commit `6cb307251c5c6261286c1566496920976640108e`. The
  page covers utility dispatch, restrictions, four internal transactions, two
  heap scans, three waits, table/session `ShareUpdateExclusiveLock`,
  `indislive`/`indisready`/`indisvalid` progression, invalid-index failure
  outcomes, regression/isolation coverage, and v18 changes from v17: `pg_index`
  TOAST snapshot handling, parallel GIN build, virtual-generated-column
  rejection, and temporal `WITHOUT OVERLAPS` shared plumbing.
- 2026-06-18: reviewed PostgreSQL 17 `CREATE INDEX CONCURRENTLY` coverage
  against pinned commit `54eeefaedbee0385529f3edf321bb99e49232aaa`. Fixed the
  v12-era `index_set_state_flags` wording: v17 uses transactional
  `CatalogTupleUpdate` for CIC state-flag flips, not non-transactional
  `heap_inplace_update`; added the required Contents block and direct
  `WaitForLockersMultiple` evidence; advanced agent verification.
- 2026-06-18: repinned PostgreSQL 19 from `e18b0cb7` to `ff8bec8c`
  after fetching 59 new upstream `master` commits. Re-reviewed all v19
  question pages against the changed-file range. `pg_plan_advice` module/doc/test
  citations and the autovacuum/parallel-vacuum/pruning feature files did not
  change in this range. The REPACK page gained the explicit `e2a8cabc`
  concurrent-repack correctness commit, now tracking 42 feature-scope commits,
  and its `repack.c` / `parsenodes.h` citation ranges were refreshed.
- 2026-06-17: expanded PostgreSQL 17 partial-index pros/cons coverage with a
  `What changed from PostgreSQL 12` section. It records the unchanged core
  storage/build/planner/ANALYZE shape and the v17-side deltas: the post-v12
  documentation warning against using many partial indexes as partitioning, the
  PG14 concurrent-index `PROC_IN_SAFE_IC` safe-wait optimization and its
  exclusion for expression/partial indexes, PG15 MERGE target-relation rechecks,
  PG14 expression statistics as an expression-index alternative, PG15 `NULLS NOT
  DISTINCT`, PG16 partial-unique-proof restriction, and the pinned v17 stable
  partial-hash-index planning fix.
- 2026-06-17: filed PostgreSQL 17 partial-index pros/cons coverage. The page
  connects partial-index storage, ordinary expression-index behavior,
  expression-key storage, predicate validation, build/DML predicate filtering,
  planner predicate implication, expression-key matching, operational
  restrictions, `ANALYZE` row-count and expression-statistics behavior,
  planner costing, and regression plans to pinned v17 source.
- 2026-06-17: filed PostgreSQL 12 partial-index pros/cons coverage. The page
  connects partial-index storage, ordinary expression-index behavior,
  expression-key storage, predicate validation, build/DML predicate filtering,
  planner predicate implication, expression-key matching, operational
  restrictions, `ANALYZE` row-count and
  expression-statistics behavior, planner costing, and regression plans to
  pinned v12 source.
- 2026-06-17: filed PostgreSQL 12 NULL-handling-by-index-type coverage for
  B-tree, hash, GiST, SP-GiST, GIN, BRIN, and contrib Bloom. The page uses
  pinned v12 source to connect executor `isnull[]` handling, `amsearchnulls`,
  access-method insertion/search behavior, and regression-test coverage.
- 2026-06-14: tightened the PostgreSQL 12 codebase navigation guide after
  review. Added the extended-query protocol Parse/Bind/Execute path through
  `exec_parse_message()`, `exec_bind_message()`, and `exec_execute_message()`;
  added the core `src/backend/commands/extension.c` boundary for contrib
  extension control files, `CREATE EXTENSION`, and extension script execution;
  and cited the direct `standard_ProcessUtility()` `EXPLAIN`/`SET` dispatch.
- 2026-06-14: made the codebase navigation guide a mandatory root-level
  question-style `type: codebase-navigation-guide` page for every supported
  version. Converted the v12 guide to `wiki/v12/codebase-navigation-guide.md`
  and added matching guides for v17, v18, and v19. Each guide has `## Question`
  and inline `## Answer` sections and maps that version's pinned source layout,
  normal SQL statement path, utility-command dispatch, generated/catalog
  artifacts, key structs, contrib boundaries, tests, and docs.
- 2026-06-12: v17 `REINDEX INDEX CONCURRENTLY` gained a "Can a failure leave an
  invalid index with the original index name?" section, the v17 companion to the
  v12 RIC section. For a healthy index a RIC failure never leaves `index_name`
  invalid: the phase-4 swap renames the rebuilt copy to `index_name` and flips
  validity (`new.indisvalid = true`, `old.indisvalid = false`) atomically in one
  transaction via the transactional `CatalogTupleUpdate`, so the invalid leftover
  is always the differently-named `_ccnew` (pre-swap) or `_ccold` (post-swap) and
  a bloated-but-valid index never degrades to no usable index; the only
  `index_name`-invalid outcome is an index that was already invalid before RIC ran
  (the `concur_reindex_ind5` regression repair case). Noted the v17-specific point
  that all `index_set_state_flags` writes are transactional in v17 (unlike v12's
  in-place `heap_inplace_update`).
- 2026-06-12: filed v17 `REINDEX INDEX CONCURRENTLY` implementation page, the v17
  companion to the v12 RIC page and the v17 CIC page. Covers
  `ReindexRelationConcurrently`'s six phases / five waits, the
  `ShareUpdateExclusiveLock` footprint, the atomic phase-4 swap (new-valid /
  old-invalid flipped together with the transactional `CatalogTupleUpdate`), the
  restriction set, the per-phase failure outcomes, and a since-v12 change section
  (partitioned REINDEX support, `TABLESPACE`, transactional `index_set_state_flags`,
  `PROC_IN_SAFE_IC` for RIC, the progress `WAIT_5` fix, the v15 stats rework, and
  the v17 `MAINTAIN` privilege). Noted a sibling discrepancy: the v17 CIC page
  still calls `index_set_state_flags` non-transactional, which is v12 behavior; v17
  uses `CatalogTupleUpdate` (recorded under the RIC page's Open Questions).
- 2026-06-12: v12 `REINDEX INDEX CONCURRENTLY` gained a "Can a failure leave an
  invalid index with the original index name?" section. For a healthy index a RIC
  failure never leaves `index_name` invalid: the phase-4 swap renames the rebuilt
  copy to `index_name` and flips validity atomically in one transaction, so the
  invalid leftover is always the differently-named `_ccnew` (pre-swap) or `_ccold`
  (post-swap) and a bloated-but-valid index never degrades to no usable index; the
  only `index_name`-invalid outcome is an index that was already invalid before
  RIC ran (the regression repair case).
- 2026-06-12: v12 `REINDEX INDEX CONCURRENTLY` review tightened the `ShareLock`
  wait conflict-set wording, split partitioned-table skip from partitioned-index
  direct-target error, and added the dedicated `reindex-concurrently` isolation
  spec to the coverage summary for that question.

## Archived Versions

| Version | Removed On | Reason |
|---|---|---|

No PostgreSQL versions have been archived yet.

## Status Meanings

- `primary` - exactly one supported version; default target for new ingests and answers.
- `active` - kept close to the primary through active-version verification.
- `legacy` - preserved for reference, but not checked by default.
- `archived` - removed from active maintenance and kept under `wiki/_archive/`.

## Source Pin Rules

- Pins must be exact commit hashes, not floating branch names.
- Source checkouts must live under `raw/postgres-NN/`.
- Version landing pages must live under `wiki/vNN/index.md`.
- Generated runtime artifacts must live under `.wiki-runtime/`: caches under `.wiki-runtime/cache/` and logs under `.wiki-runtime/logs/`.

## Current Primary

- PostgreSQL 18
- Source path: `raw/postgres-18/`
- Branch: `REL_18_STABLE`
- Pinned commit: `6cb307251c5c6261286c1566496920976640108e`
