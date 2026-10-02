---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# Impact of B-Tree Leaf Density (60% vs 90%) on Index Scan Queries in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [What avg_leaf_density measures](#what-avg_leaf_density-measures)
  - [How an index ends up at 60 percent](#how-an-index-ends-up-at-60-percent)
  - [Exact-pin measurements](#exact-pin-measurements)
  - [Reproduction](#reproduction)
  - [Planner cost impact](#planner-cost-impact)
  - [Executor scan path impact](#executor-scan-path-impact)
  - [Buffer manager and caching effects](#buffer-manager-and-caching-effects)
  - [Point lookups versus range scans](#point-lookups-versus-range-scans)
  - [What density does not tell you](#what-density-does-not-tell-you)
  - [Data structures on the scan path](#data-structures-on-the-scan-path)
  - [Settings and apply scope](#settings-and-apply-scope)
  - [Build, catalog, and extension boundaries](#build-catalog-and-extension-boundaries)
  - [Tests and coverage](#tests-and-coverage)
  - [Operational reading](#operational-reading)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 12, what is the impact on queries that scan indexes with a leaf density of 60% vs 90%?

## Answer

At the same live index tuple count and the same average tuple width, a B-tree at 60% average leaf density holds its entries in roughly `90 / 60 = 1.5x` as many leaf pages as the same index at 90%. That page-count ratio is the primary channel, and it lands in two places PostgreSQL 12 can measure:

- The planner prices an index scan from the index's physical page count. `get_relation_info` sets `IndexOptInfo.pages` from `RelationGetNumberOfBlocks` for an ordinary index, and `genericcostestimate` computes `numIndexPages = ceil(numIndexTuples * index->pages / index->tuples)` and charges the index tablespace's random page cost per page ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780), [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835)).
- The executor walks the leaf chain one buffer per right-link step. After `_bt_first` positions the scan, `_bt_next` calls `_bt_steppage`, which calls `_bt_readnextpage`, which reads each leaf page with `_bt_getbuf` ([nbtsearch.c#_bt_first-position](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1244-L1331), [nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381), [nbtsearch.c#_bt_steppage-nextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1661-L1690), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800)).

Measured on an isolated server built from this page's pinned commit, over the same 1,000,000 `bigint` keys (details in [Exact-pin measurements](#exact-pin-measurements)):

| Index | `avg_leaf_density` | `leaf_pages` | Warm buffers, whole plan | `Index Only Scan` node cost |
|---|---:|---:|---:|---:|
| `fillfactor = 90` | 90.06 | 2733 | 2736 | 25980.42 |
| `fillfactor = 60` | 59.90 | 4116 | 4119 | 31532.42 |

The scan-node cost difference, 5552.00, is exactly the 1388 extra index blocks times the default `random_page_cost` of 4.0. Warm buffer accesses rose 50.5%. A secondary channel exists: if the extra pages push the root one level higher, the descent charge rises too, which the wide-key fixture below reproduces.

Both cost figures name the `Index Only Scan` node, not the whole plan. The `count(*)` query used to drive the scan wraps that node in an `Aggregate` that adds one `cpu_operator_cost` per input row, so the plan totals are 28480.42 and 34032.43 ([costsize.c#cost_agg-plain](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L2193-L2201)).

The impact is not uniform across query shapes:

| Query shape | 60% versus 90% impact | Why |
|---|---|---|
| Equality probe on a unique or highly selective key | Usually none, unless the extra pages add a tree level | The scan reads one leaf page either way; the only density-sensitive term is the descent charge `(tree_height + 1) * 50 * cpu_operator_cost` ([selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L418)). Measured: identical cost and 4 buffers at both densities on the narrow-key fixture; one extra buffer and a 0.42-to-0.54 startup cost on a wide-key fixture whose `tree_level` went from 2 to 3. |
| Range scan, `ORDER BY` scan, or multi-column prefix scan | Index-side page reads scale with the leaf-page ratio | `_bt_next` steps page by page once the current page is exhausted ([nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381)). Measured on a 10,000-key range: 31 versus 45 index-only buffers, and 31 versus 45 again when both indexes sit on one table so the row estimate cannot differ. |
| Bitmap index scan | Same index-side effect; heap side unchanged | `btgetbitmap` loops on the same `_bt_first` / `_bt_next` pair ([nbtree.c#btgetbitmap](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L286-L342)). Measured: 30 versus 44 buffers on the `Bitmap Index Scan` node, with one block on the `Bitmap Heap Scan` above it in both plans. |
| Full index scan or index-only `count(*)` | Largest effect; scales with total leaf pages | With no usable boundary key, `_bt_first` starts from an endpoint through `_bt_endpoint` and then walks the whole chain ([nbtsearch.c#endpoint-start](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L980-L998), [nbtsearch.c#_bt_endpoint](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L2136-L2229)). Measured: 2736 versus 4119 buffers. |

Two limits on the "1.5x" rule of thumb. First, the planner prices the whole main fork, so the metapage, internal pages, half-dead pages, and deleted pages are charged too; the density-to-page-count translation is exact only when the change is confined to live leaf pages ([pgstatindex.c#index_size](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L336-L341), [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407)). Second, `avg_leaf_density` reports physical occupancy, not live-entry occupancy: index entries whose heap tuples are dead still count as full until an insert on the page or a VACUUM removes them ([nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1785-L1799), [nbtinsert.c#_bt_vacuum_one_page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L2243-L2288)).

### What avg_leaf_density measures

PostgreSQL 12 stores no runtime leaf-density value. `avg_leaf_density` is computed on demand by `pgstatindex`, from the `pgstattuple` contrib module, as

```text
100 - sum(PageGetFreeSpace(leaf)) / sum(pd_special - SizeOfPageHeaderData) * 100
```

over the live leaf pages, where the denominator is the `max_avail` term `BLCKSZ - (BLCKSZ - pd_special + SizeOfPageHeaderData)` ([pgstatindex.c#leaf-page-accounting](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L300), [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L351)). The free-space term is `PageGetFreeSpace`, not `PageGetExactFreeSpace`, so it reserves one line pointer before reporting ([bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597), [bufpage.c#PageGetExactFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L626-L647)). The v12 documentation defines the column only as "Average density of leaf pages" ([pgstattuple.sgml#avg_leaf_density-column](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L251-L255)).

Three properties of the measurement matter when reasoning about scan I/O:

- Only live leaf pages contribute. `pgstatindex` classifies each page by `P_ISDELETED` first, then `P_IGNORE`, so deleted pages land in `deleted_pages` and half-dead pages land in `empty_pages`; neither reaches the density average ([pgstatindex.c#page-classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310), [nbtree.h#page-flag-macros](../../../../raw/postgres-12/src/include/access/nbtree.h#L187-L196)).
- Reading the value costs a full physical read of the index: every block from 1 to `RelationGetNumberOfBlocks` is read and share-locked under a `BAS_BULKREAD` strategy ([pgstatindex.c:222](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L222), [pgstatindex.c#full-block-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315)).
- `avg_leaf_density` is `NaN` when no live leaf page contributed available space, which is what an empty index reports ([pgstatindex.c#avg_leaf_density](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L351), [pgstattuple.out#empty-index-NaN](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L44-L52)).

### How an index ends up at 60 percent

90% is the fresh-build target and 60% is a plausible steady state, not a corruption symptom.

`BTREE_DEFAULT_FILLFACTOR` is 90 and `BTREE_NONLEAF_FILLFACTOR` is 70. The header states that the leaf fillfactor applies during index build and when splitting a rightmost page, that non-rightmost splits try to divide the data equally, and that a page filled entirely with one duplicate value splits at an effective 96% ([nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171)). The build path sets its per-level "full" threshold from `RelationGetTargetPageFreeSpace(index, BTREE_DEFAULT_FILLFACTOR)` for leaves and from `BTREE_NONLEAF_FILLFACTOR` above them ([nbtsort.c#_bt_pagestate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L709-L734)). The documentation says the same thing from the user side: leaf pages are filled to the fillfactor during initial build and when extending the index at the right ([create_index.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L369-L392)).

The split-point chooser is what pulls the average down. `_bt_findsplitloc` reads the relation's fillfactor once, then selects a multiplier: non-leaf pages use 70% only when rightmost, a rightmost leaf always uses the leaf fillfactor, a "split after new item" case at the rightmost point of a localized grouping may also use the leaf fillfactor, and any other leaf split starts at 50:50 ([nbtsplitloc.c:170](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L170), [nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L275-L331), [nbtsplitloc.c#_bt_findsplitloc-header](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L97-L105)).

That 50:50 default is not the final word. `_bt_findsplitloc` then calls `_bt_strategy` to classify the page, and two outcomes revise the choice: `SPLIT_MANY_DUPLICATES` widens the split interval while leaving the multiplier alone, and `SPLIT_SINGLE_VALUE` re-sorts the split points at `BTREE_SINGLEVAL_FILLFACTOR`, so a leaf holding one repeated value splits at 96 percent instead of in half ([nbtsplitloc.c#split-strategy-overrides](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L403-L422), [nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171)). Fixture D below measures that path at 95.98 density, against 90.05 for the same insertion pattern with distinct keys.

Deletes do not shrink leaf pages on their own. An index scan marks entries it knows are dead `LP_DEAD` in place ([nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1785-L1799)). Those bytes are recovered on the same page later, either by an insert that finds the page full and the `BTP_HAS_GARBAGE` hint set, which calls `_bt_vacuum_one_page` and compacts the page through `_bt_delitems_delete`, or by VACUUM, which issues one `_bt_delitems_vacuum` per page ([nbtinsert.c#_bt_findinsertloc-lp-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L752-L761), [nbtinsert.c#_bt_vacuum_one_page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L2243-L2288), [nbtpage.c#_bt_delitems_delete](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1058-L1079), [nbtree.c#btvacuumpage-delitems](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1273-L1294)). A page is removed from the tree only when it becomes completely empty, and only later becomes reusable through the free space map ([nbtree.c#btvacuumpage-pagedel](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1338-L1347), [nbtree.c#btvacuumpage-recycle](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1166-L1173)). The manual states the operational consequence: completely empty B-tree pages are reclaimed for re-use, but a page that keeps a few keys stays allocated ([maintenance.sgml#routine-reindex-partly-empty](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L866-L874)).

So a 90% index reaches 60% by splitting, not by leaking. A measured example is in the next section: 1,000,000 random keys inserted one at a time into an already-indexed table settled at 65.58% with no deletions at all.

### Exact-pin measurements

All numbers below were re-measured on 2026-09-07 on one isolated PostgreSQL 12.2 server built from this page's `pinned_commit`, with `shared_buffers = 512MB`, `autovacuum = off`, and `pgstattuple` installed. The [Reproduction](#reproduction) section publishes the statements that produce them. Buffer counts come from the second, warm `EXPLAIN (ANALYZE, BUFFERS)` execution, so they count buffer accesses, not device reads. Costs are default planner constants: `seq_page_cost = 1`, `random_page_cost = 4`, `cpu_operator_cost = 0.0025`, `effective_cache_size = 4GB`.

Session settings used to pin the plan shape: `enable_seqscan = off` throughout; `max_parallel_workers_per_gather = 0` for the rows labelled serial; `enable_indexonlyscan = off` plus `enable_indexscan = off` for the bitmap row; and `enable_bitmapscan = off` for the wide-key probes. Both tables in fixture A were `VACUUM (ANALYZE)`-ed after the build.

Fixture A, narrow keys: 1,000,000 sequential `bigint` values, the same data in two tables, indexes built by `CREATE INDEX` at `fillfactor = 90` and `fillfactor = 60`.

| Measurement | `fillfactor = 90` | `fillfactor = 60` | Ratio |
|---|---:|---:|---:|
| `avg_leaf_density` | 90.06 | 59.90 | 0.665 |
| `leaf_pages` | 2733 | 4116 | 1.506 |
| `internal_pages` | 11 | 16 | |
| `tree_level` | 2 | 2 | |
| `pg_class.relpages` | 2745 | 4133 | 1.506 |
| Full scan, warm buffers on the whole plan | 2736 | 4119 | 1.505 |
| of which index blocks | 2735 | 4118 | 1.506 |
| of which visibility-map blocks | 1 | 1 | 1.000 |
| Full scan, `Index Only Scan` node cost | 25980.42 | 31532.42 | 1.214 |
| Full scan, `Aggregate` plan total | 28480.42 | 34032.43 | 1.195 |
| Full scan, `Parallel Index Only Scan` node cost | 20147.09 | 25699.09 | 1.276 |
| Full scan, `Finalize Aggregate` plan total | 22188.97 | 27740.97 | 1.250 |
| 10,000-key range, index-only warm buffers | 31 | 45 | 1.452 |
| 10,000-key range, `Index Only Scan` node cost | 299.79 | 377.63 | 1.260 |
| 10,000-key range, estimated rows | 9568 | 10260 | 1.072 |
| 10,000-key range, `Bitmap Index Scan` node buffers | 30 | 44 | 1.467 |
| Equality probe cost | 0.42..4.44 | 0.42..4.44 | 1.000 |
| Equality probe warm buffers | 4 | 4 | 1.000 |

Four things follow.

- The predicted multiplier `90.06 / 59.90 = 1.5035` matched the measured leaf-page ratio `4116 / 2733 = 1.5060` and the index-block ratio `4118 / 2735 = 1.5056`.
- The entire full-scan cost difference is index pages. The two indexes differ by 1388 physical blocks, 2745 versus 4133, matching their `pg_class.relpages`, and the scan-node gap `31532.42 - 25980.42` is exactly `1388 * 4.0 = 5552.00`. The parallel scan node reproduces the same 5552.00. Node cost grew 21.4 percent because the per-tuple CPU terms are unchanged; the index page term is what scales ([selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835)).
- The warm buffer count is not purely index-side. Resetting the cumulative counters around one warm execution splits the 2736 into 2735 index blocks and one heap-relation block, which is the visibility-map page the index-only scan consults ([nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170)). The 2735 index blocks are the root, one internal page, and 2733 leaves; the metapage is served from the relcache on a warm scan.
- The 10,000-key range row mixes two effects, because the two tables were sampled by separate `ANALYZE` runs and produced different row estimates. The same-table comparison below removes that.

Fixture B, wide keys: 100,000 values of 110-byte `text`, with only one index present at a time so the planner had no alternative to price.

| Measurement | `fillfactor = 90` | `fillfactor = 60` |
|---|---:|---:|
| `avg_leaf_density` | 91.31 | 60.87 |
| `leaf_pages` | 1695 | 2565 |
| `internal_pages` | 38 | 59 |
| `tree_level` | 2 | 3 |
| Index blocks | 1734 | 2625 |
| Equality probe cost | 0.42..4.44 | 0.54..4.56 |
| Equality probe warm buffers | 4 | 5 |
| Full scan, `Index Only Scan` node cost | 8436.42 | 12000.54 |
| Full scan, `Aggregate` plan total | 8686.42 | 12250.54 |

This fixture is the point-lookup exception. The 1.5x page growth pushed the root one level up, so `_bt_getrootheight` returned 3 instead of 2, the descent charge rose by `50 * cpu_operator_cost = 0.125` (visible as startup cost 0.42 to 0.54), and the probe read one more index page ([plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L418), [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116)). The full-scan difference is again pages: `12000.54 - 8436.42 = 3564.12`, and `(2625 - 1734) * 4.0 = 3564.00`, with the remaining 0.12 the extra descent level. Every figure in this fixture reproduced exactly on re-measurement.

Fixture C, how the density gets there: 1,000,000 random `bigint` keys inserted one row at a time into a table that already had the index, with no updates and no deletes.

| Measurement | Value |
|---|---:|
| `avg_leaf_density` | 66.25 |
| `leaf_pages` | 3720 |
| `internal_pages` | 12 |
| `leaf_fragmentation` | 49.89 |
| `tree_level` | 2 |

Against fixture A's freshly built 90 percent index over the same key count, that is 1.361x the leaf pages, matching `90.06 / 66.25 = 1.359`. No page was ever deleted; the 50:50 non-rightmost split rule alone produced a two-thirds-dense index ([nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L275-L331)). This is the one fixture on the page whose exact values are not reproducible: the insertion order is a fresh random permutation on every run, so density lands near two thirds rather than on a fixed figure. An earlier run of the same fixture read 65.58 density over 3758 leaf pages.

Fixture D, the single-value split: 300,000 rows carrying one repeated `bigint` key, inserted into a table that already had the index, against a control of 300,000 distinct ascending keys inserted the same way.

| Measurement | One repeated key | Distinct ascending keys |
|---|---:|---:|
| `avg_leaf_density` | 95.98 | 90.05 |
| `leaf_pages` | 770 | 820 |
| `internal_pages` | 5 | 4 |
| `tree_level` | 2 | 2 |

The duplicate fixture lands on `BTREE_SINGLEVAL_FILLFACTOR`, not on the 50:50 rule, and the distinct control lands on the leaf fillfactor because every split is rightmost. This is the measured basis for the split-strategy correction above ([nbtsplitloc.c#split-strategy-overrides](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L403-L422)).

Fixture E, density against selectivity: the same table and the same `ANALYZE` statistics, with one index dropped and rebuilt at the other fillfactor so the planner sees one candidate at a time and an identical row estimate.

| Measurement | `fillfactor = 90` | `fillfactor = 60` |
|---|---:|---:|
| Estimated rows | 9568 | 9568 |
| `Index Only Scan` node cost | 299.79 | 351.79 |
| Warm buffers | 31 | 45 |

Holding the estimate fixed, density alone moved warm buffers from 31 to 45 and the node cost by exactly `52.00`, which is the 13 extra pages the pro-rata term prices at `random_page_cost` ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780)). Compare the two-table row in fixture A, where the estimates were 9568 and 10260 and the cost ratio therefore carried a selectivity component as well.

Fixture F, where a density change moves `tree_level`: 100,000 rows of `text` at a range of key widths, built at each fillfactor.

| Key width, bytes | `tree_level` at 90 | `tree_level` at 60 |
|---:|---:|---:|
| 8 to 100 | 2 | 2 |
| 104 | 2 | 3 |
| 110 | 2 | 3 |
| 112 | 2 | 3 |
| 120 to 220 | 3 | 3 |

At this row count the 90-to-60 change adds a level only inside a narrow band, measured here between 104 and 112 bytes. Below it both trees are two levels deep and the probe cost is identical; above it both are already three levels deep and the probe cost is identical again. Fixture B sits inside the band at 110 bytes, which is why it shows the effect.

Backward scans read the same pages as forward scans. A full index-only scan of fixture A in descending order measured 2736 warm buffers at 90 percent and 4119 at 60 percent, matching the forward figures exactly, on an index no other session was modifying ([nbtsearch.c#_bt_walk_left](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1930-L2053)).

When the index no longer fits in shared buffers, the extra pages become buffer-pool misses on every repetition. Restarting the same server with `shared_buffers = 1MB` and repeating the full scan three times gave a steady 2735 misses at 90 percent against 4118 at 60 percent, a ratio of 1.506, with one hit each time for the visibility-map page. These are shared-buffer misses, not device reads: the operating system page cache still held the files.

Fixture G, what refreshes an index's own `pg_class` row: a 200,000-row table and index, grown to 600,000 rows, with no VACUUM at any point.

| Point in time | Index `relpages` | Index `reltuples` | Real index blocks |
|---|---:|---:|---:|
| Just after `CREATE INDEX` | 551 | 200000 | 551 |
| After inserting 400,000 more rows | 551 | 200000 | 1648 |
| After a plain `ANALYZE` | 1648 | 600000 | 1648 |

A plain `ANALYZE` refreshed both columns, and the index build had set them in the first place. VACUUM is not the only writer; see [What density does not tell you](#what-density-does-not-tell-you).

### Reproduction

These are the statements that produce every figure in the previous section. They are fixture statements for a disposable server built from the pin: they create and drop tables, and they are not meant for a database anyone cares about. Only the read-back at the end is worth pointing at a real index, and `pgstatindex` reads every block of the index it is given, so it is a diagnostic rather than a monitoring query ([pgstatindex.c#full-block-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315)). Both timeouts are `PGC_USERSET`, so they apply at session or transaction scope with no reload and no restart ([guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2386), [guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2396)).

Server settings: `shared_buffers = 512MB`, `autovacuum = off`, `max_parallel_workers_per_gather = 2`, everything else default.

Fixture A, narrow keys:

```sql
CREATE TABLE ld_a90 (id bigint);
INSERT INTO ld_a90 SELECT g FROM generate_series(1,1000000) g;
CREATE TABLE ld_a60 (id bigint);
INSERT INTO ld_a60 SELECT g FROM generate_series(1,1000000) g;
CREATE INDEX ld_a90_idx ON ld_a90 (id) WITH (fillfactor = 90);
CREATE INDEX ld_a60_idx ON ld_a60 (id) WITH (fillfactor = 60);
VACUUM (ANALYZE) ld_a90;
VACUUM (ANALYZE) ld_a60;
```

Plan shapes. `enable_seqscan = off` throughout; `max_parallel_workers_per_gather = 0` for the serial rows and the default 2 for the parallel rows; `enable_indexonlyscan = off` plus `enable_indexscan = off` for the bitmap row; `enable_bitmapscan = off` for the wide-key probes. Buffer counts come from the second, warm execution.

```sql
SET enable_seqscan = off;
SET max_parallel_workers_per_gather = 0;
-- full scan, run twice and read the second
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) SELECT count(*) FROM ld_a90;
-- 10,000-key range
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
  SELECT count(*) FROM ld_a90 WHERE id >= 500000 AND id < 510000;
-- equality probe
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) SELECT id FROM ld_a90 WHERE id = 500000;
-- backward full scan
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
  SELECT id FROM ld_a90 ORDER BY id DESC OFFSET 999999;
```

Splitting one warm scan into index blocks and visibility-map blocks. The reset needs a quiet moment on either side, because the collector receives a statement's counters after the statement ends:

```sql
SELECT count(*) FROM ld_a90;          -- warm the cache
SELECT pg_sleep(2);
SELECT pg_stat_reset();
SELECT pg_sleep(2);
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) SELECT count(*) FROM ld_a90;
SELECT pg_sleep(2);
SELECT idx_blks_read, idx_blks_hit FROM pg_statio_user_indexes
  WHERE indexrelname = 'ld_a90_idx';
SELECT heap_blks_read, heap_blks_hit FROM pg_statio_user_tables
  WHERE relname = 'ld_a90';
```

Fixture B, wide keys, one index present at a time:

```sql
CREATE TABLE ld_b (t text);
ALTER TABLE ld_b ALTER COLUMN t SET STORAGE PLAIN;
INSERT INTO ld_b SELECT lpad(g::text, 110, '0') FROM generate_series(1,100000) g;
VACUUM (ANALYZE) ld_b;
CREATE INDEX ld_b_idx ON ld_b (t) WITH (fillfactor = 90);   -- then 60
```

Fixture C, random-order inserts into an existing index, and fixture D, the single-value split:

```sql
CREATE TABLE ld_c (id bigint);
CREATE INDEX ld_c_idx ON ld_c (id);
INSERT INTO ld_c SELECT g FROM generate_series(1,1000000) g ORDER BY random();

CREATE TABLE ld_d (id bigint);
CREATE INDEX ld_d_idx ON ld_d (id);
INSERT INTO ld_d SELECT 42 FROM generate_series(1,300000) g;
```

Fixture E holds the row estimate fixed by keeping one table and swapping the index, with no `ANALYZE` in between:

```sql
DROP INDEX ld_a90_idx;
CREATE INDEX ld_a90_idx60 ON ld_a90 (id) WITH (fillfactor = 60);
```

Fixture G, which writer refreshes the index's catalog row:

```sql
CREATE TABLE ld_e (id bigint, flag boolean);
INSERT INTO ld_e SELECT g, (g % 2 = 0) FROM generate_series(1,200000) g;
CREATE INDEX ld_e_idx ON ld_e (id);
SELECT relpages, reltuples FROM pg_class WHERE relname = 'ld_e_idx';
INSERT INTO ld_e SELECT g, true FROM generate_series(200001,600000) g;
SELECT relpages, reltuples FROM pg_class WHERE relname = 'ld_e_idx';
ANALYZE ld_e;
SELECT relpages, reltuples FROM pg_class WHERE relname = 'ld_e_idx';
```

The density read-back, the one statement worth running against a real index:

```sql
SET /* wiki_leaf_density_60_vs_90 */ statement_timeout = '10min';
SET /* wiki_leaf_density_60_vs_90 */ lock_timeout = '5s';

SELECT /* wiki_leaf_density_60_vs_90 */
       s.tree_level,
       s.index_size,
       s.internal_pages,
       s.leaf_pages,
       s.empty_pages,
       s.deleted_pages,
       s.avg_leaf_density,
       s.leaf_fragmentation
FROM   pgstatindex('ld_a90_idx') s;
```

### Planner cost impact

B-tree paths are costed by `btcostestimate`, which delegates the page and cache arithmetic to `genericcostestimate`; `cost_index` calls the access method through `amcostestimate` and folds the result into the path's startup and run cost ([nbtree.c#bthandler-callbacks](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L128-L148), [costsize.c#cost_index-amcostestimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L537-L560)).

The sizing input is `IndexOptInfo.pages`:

- For an ordinary non-partial index, `get_relation_info` sets `info->pages = RelationGetNumberOfBlocks(indexRelation)` and locks `info->tuples` to the parent table's estimate ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407)).
- For a partial index it calls `estimate_rel_size`, whose index case still reports current blocks as `*pages` but derives the tuple count from the previous `pg_class` density after discounting the metapage ([plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L971), [plancat.c#estimate_rel_size-index-tuples](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L984-L1026)).

`genericcostestimate` then scales pages pro rata and prices them:

```c
if (index->pages > 1 && index->tuples > 1)
    numIndexPages = ceil(numIndexTuples * index->pages / index->tuples);
```

Its own comment notes that this counts only leaf pages in effect and ignores metapage and upper-level overhead, and that repeated scans are adjusted by the Mackert-Lohman model in `index_pages_fetched`, whose cache term explicitly adds the index's pages to the pages competing for `effective_cache_size` ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780), [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835), [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L786-L878)).

For a fixed number of qualifying index tuples, a 1.5x increase in `index->pages` is a 1.5x increase in `numIndexPages` before cache adjustment, which is what the measured 5552.01 cost difference confirms. On top of that, `btcostestimate` adds `(index->tree_height + 1) * 50.0 * cpu_operator_cost` per scan and once per scalar-array-operation scan, with a comment saying the charge exists so that bloated indexes do not appear to have the same search cost as unbloated ones when only one leaf page is expected ([selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116)).

Nothing in the planner reads `avg_leaf_density`, and no GUC or reloption tells the planner to cost an index as if its density were different. The consequence is a plan-choice effect, not just a cost effect: once the larger index's page charge exceeds the alternatives, the planner can switch to a sequential scan, a bitmap plan, or another index.

### Executor scan path impact

All B-tree scans enter through the access-method callbacks: `btgettuple` for plain and index-only scans, `btgetbitmap` for bitmap index scans ([nbtree.c#bthandler-callbacks](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L128-L148)).

1. `btgettuple` calls `_bt_first` for the first item and `_bt_next` afterwards, and remembers TIDs the caller reported as dead in `so->killedItems` ([nbtree.c#btgettuple](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L212-L284)).
2. `_bt_first` builds an insertion-type scan key, descends with `_bt_search`, and loads the matching items from the target leaf page with `_bt_readpage` ([nbtsearch.c#_bt_first-position](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1244-L1331), [nbtsearch.c#_bt_search](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L91-L323)).
3. `_bt_next` returns saved items from the current page until it runs out, then calls `_bt_steppage`, which for a forward scan uses the right link saved during `_bt_readpage` and calls `_bt_readnextpage` ([nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381), [nbtsearch.c#_bt_steppage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1618-L1724), [nbtsearch.c#_bt_steppage-nextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1661-L1690)).
4. Forward `_bt_readnextpage` reads the candidate page with `_bt_getbuf`, skips it and follows its own `btpo_next` if `P_IGNORE` says it is deleted or half-dead, and otherwise hands it to `_bt_readpage` starting at `P_FIRSTDATAKEY` ([nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800), [nbtpage.c#_bt_getbuf](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L747-L759), [nbtree.h#P_FIRSTDATAKEY](../../../../raw/postgres-12/src/include/access/nbtree.h#L217-L219)).
5. Backward scans take the more complex `_bt_walk_left` path, because the page to the left may split while the scan is in flight and the page just left may be deleted ([nbtsearch.c#_bt_readnextpage-backward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1801-L1903), [nbtsearch.c#_bt_walk_left](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1930-L2053)). On an index no other session is modifying, the page count is the same in both directions, which fixture A confirms at 2736 and 4119 warm buffers either way. Under concurrent splits and deletions `_bt_walk_left` can revisit pages, so the counts are equal only in the quiescent case.

Each additional leaf page therefore costs one `_bt_getbuf` buffer lookup, pin, and `BT_READ` content lock; one `_bt_readpage` pass that checks items with `_bt_checkkeys` and copies the matches into the scan's local item array via `_bt_saveitem`; and one later unlock or unpin through `_bt_drop_lock_and_maybe_pin` or `_bt_relbuf` ([nbtsearch.c#_bt_readpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1383-L1597), [nbtsearch.c#_bt_readpage-forward-loop](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1466-L1531), [nbtsearch.c#_bt_saveitem](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1599-L1616), [nbtpage.c#_bt_relbuf](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L913-L917), [bufmgr.c#LockBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3585-L3607)).

The per-page work is not purely proportional in one respect: only the first page is binary-searched, and `_bt_readpage` can clear `moreRight` early after testing the page's high key, so a lower-density index does not always pay 1.5x the key comparisons even though it pays 1.5x the page reads ([nbtsearch.c#_bt_readpage-high-key](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1503-L1525)).

Two consumers sit above this loop and both inherit the effect. `index_getnext_tid` calls `amgettuple` per TID and is the path used by index and index-only scans; an index-only scan still walks the same index pages and only avoids the heap fetch when the visibility map reports the heap page all-visible ([indexam.c#index_getnext_tid](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L501-L545), [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170)). `btgetbitmap` fills a TID bitmap with the same loop, which is why the measured `Bitmap Index Scan` buffers tracked the leaf-page ratio while heap blocks did not move ([nbtree.c#btgetbitmap](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L286-L342)).

### Buffer manager and caching effects

- Each index page access goes through the shared buffer mapping hash. Even a hit takes the buffer partition lock, calls `BufTableLookup`, pins the buffer, and releases the lock; v12 partitions that table 128 ways ([bufmgr.c#BufferAlloc-hit](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1011-L1035), [buf_internals.h#BufMappingPartitionLock](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L121-L131), [lwlock.h#NUM_BUFFER_PARTITIONS](../../../../raw/postgres-12/src/include/storage/lwlock.h#L106-L113)).
- The extra pages enlarge the working set. The planner models that explicitly: `index_pages_fetched` pro-rates `effective_cache_size` over `root->total_table_pages` plus the index's own pages ([costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L786-L878)).
- PostgreSQL 12 issues no prefetch for index pages on any scan path. All four backend `PrefetchBuffer` call sites name `MAIN_FORKNUM` of a heap relation: two in the bitmap heap scan, one in the VACUUM truncation scan, and one on the xid-horizon path ([bufmgr.c#PrefetchBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L521-L530), [nodeBitmapHeapscan.c#prefetch](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L501-L509), [nodeBitmapHeapscan.c#prefetch-second](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L550-L560), [vacuumlazy.c#prefetch](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L2070-L2081), [heapam.c#prefetch-xid-horizon](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L6948-L6958)). The documentation states that `effective_io_concurrency` affects only bitmap heap scans ([config.sgml#effective_io_concurrency](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2166-L2181)). The one way to prefetch index blocks in this checkout is the `pg_prewarm` contrib module, which takes any relation and any fork and so accepts an index, but it is a manual warm-up, not something a scan does for itself ([pg_prewarm.c#prefetch-loop](../../../../raw/postgres-12/contrib/pg_prewarm/pg_prewarm.c#L159-L164)). The extra leaf reads of a 60 percent index are therefore serialized against the device with no overlap from inside the server.
- Physical adjacency is a separate axis from density. The manual notes that a freshly constructed B-tree is slightly faster to access than one updated many times because logically adjacent pages are usually physically adjacent in a new index ([maintenance.sgml#routine-reindex-adjacency](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L882-L888)). Fixture C shows the two axes moving together in practice: 65.58% density with 49.71% `leaf_fragmentation` ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307)).

### Point lookups versus range scans

- Equality probe on a unique or high-cardinality leading column: one leaf page either way, so the visible difference is only the descent charge, and that moves only if `tree_height` moves. Fixture A measured identical cost and 4 buffers at both densities; fixture B, where `tree_level` went 2 to 3, measured 5 buffers and +0.12 startup cost ([nbtsearch.c#_bt_first-position](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1244-L1331), [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116)).
- Range scan, index `ORDER BY`, or prefix scan on a multi-column index: the leaf pages visited grow with the pages holding qualifying keys, because `_bt_next` steps page by page ([nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800)).
- Full index scan, including an index-only `count(*)`: `_bt_first` finds no usable boundary key, `_bt_endpoint` starts at one end, and the scan then covers the entire chain, so index-side work tracks the total leaf-page count ([nbtsearch.c#endpoint-start](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L980-L998), [nbtsearch.c#_bt_endpoint](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L2136-L2229)).
- Nested-loop inner scans amplify the difference but not linearly, because `genericcostestimate` runs repeated scans through the Mackert-Lohman cache model instead of multiplying pages by loop count ([selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835), [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L786-L878)).

### What density does not tell you

- Dead entries count as dense. `_bt_killitems` only sets `LP_DEAD` in place, so those bytes keep counting toward `avg_leaf_density` until an insert on that page or a VACUUM removes them; an index can read 90.00 while most of its entries are dead ([nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1785-L1799), [nbtinsert.c#_bt_vacuum_one_page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L2243-L2288)).
- Half-dead pages are excluded from the average yet still read. `pgstatindex` counts them as `empty_pages`, but the first stage of page deletion leaves the leaf linked to its siblings, so a forward scan still reads it before stepping right ([pgstatindex.c#page-classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800)).
- Deleted pages are the opposite case: scans no longer traverse them, but they still occupy blocks in the main fork and so still inflate the `index->pages` the planner prices ([pgstatindex.c#page-classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310), [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407)).
- Density says nothing about physical order. `leaf_fragmentation` is the separate column for that, and it counts only live leaf pages whose right link points to a lower block number ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307)).
- Neither planner input comes from the index's own statistics. For an ordinary index, `index->pages` is the live block count from `RelationGetNumberOfBlocks`, not the catalog `pg_class.relpages`, and `index->tuples` is the parent table's estimate, so the pro-rata ratio reads nothing that `pgstatindex` reports and nothing that only an index `ANALYZE` would refresh ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407)). A partial index is the exception, because `estimate_rel_size` derives its tuple count from the index's own catalog density ([plancat.c#estimate_rel_size-index-tuples](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L984-L1026)). Three things write an index's own `pg_class` row: the index build sets both columns through `index_update_stats`, a plain `ANALYZE` rewrites them from the current block count unless it is running as part of `VACUUM ANALYZE`, and VACUUM writes them when the access method reports an exact count ([index.c#index_update_stats-callers](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2986), [analyze.c#index-relstats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629), [nbtree.c#btvacuumcleanup](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L891-L942), [vacuumlazy.c#lazy_cleanup_index-relstats](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1803-L1815)). Fixture G measures the `ANALYZE` path: an index left at a stale 551 `relpages` while the file grew to 1648 blocks was corrected to 1648 by a plain `ANALYZE` with no VACUUM.
- `EXPLAIN (ANALYZE, BUFFERS)` cannot attribute buffers to the index. `show_buffer_usage` prints hit, read, dirtied, and written counters for shared and local buffers, read and written for temp buffers, plus optional I/O timing, all from one per-node `BufferUsage` struct; it never splits index pages from heap pages ([explain.c#plan-buffer-usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L1864-L1866), [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2985), [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33)). That is why the measurements above use index-only scans and the `Bitmap Index Scan` node. Neither is purely index-side, though. An index-only scan consults the visibility map for every TID and pins that buffer, so one block of its count belongs to the heap relation, and it falls back to a heap fetch for any page the map does not report all-visible; the fixtures here reported `Heap Fetches: 0` only because `VACUUM` had left the heap fully all-visible ([nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170)).

### Data structures on the scan path

| Structure | Role in this question |
|---|---|
| `BTPageOpaqueData` | Holds `btpo_prev` and `btpo_next`, the sibling links the scan follows and the input to both `pgstatindex` leaf columns ([nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L55-L68)). |
| `BTMetaPageData` | Supplies the root block and level that `pgstatindex` reports as `tree_level` and that `_bt_getrootheight` feeds to the planner's descent charge ([nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L97-L113), [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365)). |
| `BTScanPosData` and `BTScanPosItem` | The per-page result buffer: one page's matching TIDs are copied here, so more leaf pages means more fill-and-drain cycles of this array ([nbtree.h#BTScanPosItem](../../../../raw/postgres-12/src/include/access/nbtree.h#L541-L546), [nbtree.h#BTScanPosData](../../../../raw/postgres-12/src/include/access/nbtree.h#L548-L583)). |
| `BTScanOpaqueData` | Per-scan state, including `currPos`, `markPos`, and the `killedItems` array that carries `LP_DEAD` candidates ([nbtree.h#BTScanOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L629-L669)). |
| `IndexOptInfo` fields `pages`, `tuples`, `tree_height` | The three planner inputs density can move ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L418)). |
| `BufferUsage` | The only per-node I/O record `EXPLAIN` can print, with no index-versus-heap split ([instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33)). |

### Settings and apply scope

No setting changes an existing index's density; the layout levers are `REINDEX` and the index `fillfactor` reloption, both applied at build time ([create_index.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L369-L392), [ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57)). The settings that change how the extra pages are priced or read are all `PGC_USERSET`, so a session or transaction can set them with `SET` or `SET LOCAL`, with no reload and no restart.

| Setting | v12 context | Apply scope | Relevance to 60% versus 90% |
|---|---|---|---|
| `random_page_cost` | `PGC_USERSET` | Session or transaction | Multiplies the extra index pages; read for the index's tablespace ([guc.c#random_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3217-L3227), [config.sgml#random_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4713-L4770)). |
| `seq_page_cost` | `PGC_USERSET` | Session or transaction | Sets the alternative a bloated index competes with; also settable per tablespace ([guc.c#seq_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3207-L3216), [config.sgml#seq_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4696-L4711)). |
| `effective_cache_size` | `PGC_USERSET` | Session or transaction | Feeds the Mackert-Lohman adjustment that discounts repeated scans of the larger index ([guc.c#effective_cache_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3117), [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L786-L878)). |
| `cpu_operator_cost` | `PGC_USERSET` | Session or transaction | Scales the B-tree descent charge, the only term that reacts to a density-driven height change ([guc.c#cpu_operator_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3250-L3260), [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116)). |
| `effective_io_concurrency` | `PGC_USERSET` | Session or transaction | Does not help; documented as affecting bitmap heap scans only, and v12 prefetches no index page ([guc.c#effective_io_concurrency](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2759-L2775), [config.sgml#effective_io_concurrency](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2166-L2181), [bufmgr.c#PrefetchBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L521-L530)). |

### Build, catalog, and extension boundaries

- Measuring density needs a contrib extension. `pgstatindex` lives in `contrib/pgstattuple`, is built as the `pgstattuple` module from `pgstatindex.o`, and must be installed with `CREATE EXTENSION` before any of this is observable ([contrib/pgstattuple/Makefile](../../../../raw/postgres-12/contrib/pgstattuple/Makefile#L1-L13)).
- Execution is privilege-gated. The 1.5 SQL script revokes `pgstatindex(regclass)` from `PUBLIC` and grants it to `pg_stat_scan_tables`, so a caller needs that role or superuser ([pgstattuple--1.4--1.5.sql#pgstatindex-grants](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)).
- `pgstatindex` also rejects inputs before reading anything: a non-index or non-B-tree relation raises `relation "%s" is not a btree index`, and another session's temporary relation raises `cannot access temporary tables of other sessions` ([pgstatindex.c#relation-checks](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L224-L238)).
- The costing path depends on a generated catalog header. `get_relation_info` fetches tree height only when `info->relam == BTREE_AM_OID`, and that symbol is declared as an `oid_symbol` in `pg_am.dat`, materialized into `pg_am_d.h` by the backend catalog `GENERATED_HEADERS` rule; the pinned checkout contains the data file, not the header ([plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L418), [pg_am.dat#BTREE_AM_OID](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L20), [catalog/Makefile:51](../../../../raw/postgres-12/src/backend/catalog/Makefile#L51)).

### Tests and coverage

No test in the pinned checkout ties `avg_leaf_density` to scan I/O or plan cost.

- The `pgstattuple` regression test calls `pgstatindex` on an empty primary-key B-tree through the `text`, `name`, and `regclass` entry points and checks the error paths for unsupported relation kinds and access methods. It never populates a B-tree, so it never asserts a non-`NaN` density ([pgstattuple.sql#pgstatindex-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L9-L113), [pgstattuple.out#empty-index-NaN](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L44-L52)).
- The core `btree_index` test builds a deliberately tall tree with `fillfactor = 10` and later exercises page deletion and FSM recycling, but it compares no costs or buffer counts across densities ([btree_index.sql#tall-fillfactor](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L110-L123), [btree_index.sql#page-recycling](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L144-L162)).

The measurements in this page were therefore run against a disposable server built from the pin, not from an in-tree test.

### Operational reading

- Compare `leaf_pages` and `index_size` first, not the density percentage alone. Density is the ratio; the page count is what the planner charges and the executor reads ([pgstatindex.c#index_size](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L336-L341), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780)).
- Expect the effect to show up in wide scans, not in primary-key lookups. That asymmetry is structural: one is a page walk, the other is one descent plus one page ([nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381), [nbtsearch.c#_bt_first-position](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1244-L1331)).
- Check `tree_level` before and after any rebuild. It is the only density-driven input that changes single-probe cost, and fixture B shows a 90-to-60 change can move it ([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365), [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116)).
- Do not read 60% as a defect threshold. PostgreSQL 12 defines no density cutoff for `REINDEX`; the documentation recommends rebuilding indexes with many empty or nearly-empty pages, and notes the physical-adjacency benefit, without naming a percentage ([ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57), [maintenance.sgml#routine-reindex-partly-empty](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L866-L874), [maintenance.sgml#routine-reindex-adjacency](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L882-L888)).
- A rebuild at a lower `fillfactor` is a deliberate trade: fewer future splits against more pages read by every scan from the first day ([create_index.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L369-L392)).

## Context Reviewed

- Required wiki navigation: [versions](../../../versions.md), [wiki index](../../../index.md), [v12/index](../../index.md), and recent [log](../../../log.md).
- PostgreSQL 12 B-tree scan sources: `nbtree.c`, `nbtsearch.c`, `nbtpage.c`, `nbtinsert.c`, `nbtutils.c`, `nbtsplitloc.c`, `nbtsort.c`, and `src/include/access/nbtree.h`.
- PostgreSQL 12 planner and costing sources: `plancat.c`, `selfuncs.c`, `costsize.c`, and `guc.c`.
- PostgreSQL 12 statistics writers: `src/backend/commands/analyze.c` and `src/backend/catalog/index.c`.
- PostgreSQL 12 executor, measurement, and storage sources: `indexam.c`, `nodeIndexonlyscan.c`, `nodeBitmapHeapscan.c`, `explain.c`, `instrument.h`, `bufmgr.c`, `buf_internals.h`, `lwlock.h`, `heapam.c`, and `vacuumlazy.c`. Every `PrefetchBuffer` call site in `src/backend/` and `contrib/` was enumerated for the prefetch claim.
- Diagnostic and build surfaces: `contrib/pgstattuple/pgstatindex.c`, `contrib/pgstattuple/Makefile`, `contrib/pgstattuple/pgstattuple--1.4--1.5.sql`, `contrib/pg_prewarm/pg_prewarm.c`, `src/include/catalog/pg_am.dat`, and `src/backend/catalog/Makefile`.
- Same-checkout docs and tests: `config.sgml`, `maintenance.sgml`, `ref/create_index.sgml`, `ref/reindex.sgml`, `pgstattuple.sgml`, `contrib/pgstattuple/sql/pgstattuple.sql`, `contrib/pgstattuple/expected/pgstattuple.out`, and `src/test/regress/sql/btree_index.sql`.
- Exact-pin execution: one isolated PostgreSQL 12.2 server built from `45b88269a353ad93744772791feb6d01bc7e1e42` with `pgstattuple` and `pageinspect` installed, used for all seven fixtures. The 2026-09-07 re-measurement rebuilt that server from the pin because the original sandbox had been deleted on the same day; its statements are published under [Reproduction](#reproduction) rather than left in a scratch directory. The rebuilt server was stopped and its data directory removed after the run, so nothing under `.wiki-runtime/` is needed to reproduce these numbers.

## Evidence Map

| Claim | Evidence |
|---|---|
| `avg_leaf_density` is computed from live-leaf free space over per-page available capacity, using `PageGetFreeSpace` | [pgstatindex.c#leaf-page-accounting](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L300), [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L351), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597), [pgstattuple.sgml#avg_leaf_density-column](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L251-L255) |
| Reading it costs a full physical index read under `BAS_BULKREAD`, is privilege-gated, and rejects non-B-tree and other sessions' temporary relations | [pgstatindex.c:222](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L222), [pgstatindex.c#full-block-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315), [pgstatindex.c#relation-checks](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L224-L238), [pgstattuple--1.4--1.5.sql#pgstatindex-grants](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92) |
| Default leaf fillfactor is 90, non-leaf 70, duplicates 96; build and rightmost splits apply it, other leaf splits start at 50:50 except the split-after-new-item case, and the single-value strategy then overrides the multiplier to 96 | [nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171), [nbtsort.c#_bt_pagestate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L709-L734), [nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L275-L331), [nbtsplitloc.c#split-strategy-overrides](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L403-L422), [create_index.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L369-L392) |
| Measured: 300,000 rows of one repeated key reach 95.98 density where the same insert pattern with distinct keys reaches 90.05 | Fixture D under [Exact-pin measurements](#exact-pin-measurements), reproduced by [Reproduction](#reproduction) |
| Measured: the published cost figures name plan nodes, and the `count(*)` wrapper adds one `cpu_operator_cost` per row on top of the scan node | [costsize.c#cost_agg-plain](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L2193-L2201), fixture A under [Exact-pin measurements](#exact-pin-measurements) |
| Measured: one warm full index-only scan of the 90 percent index is 2735 index blocks plus one visibility-map block | [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170), fixture A under [Exact-pin measurements](#exact-pin-measurements) |
| Measured: with the row estimate held fixed on one table, density alone moved warm buffers from 31 to 45 and node cost by exactly 52.00 | Fixture E under [Exact-pin measurements](#exact-pin-measurements) |
| Measured: at 100,000 rows the 90-to-60 change adds a tree level only for key widths in a band around 104 to 112 bytes | Fixture F under [Exact-pin measurements](#exact-pin-measurements) |
| `LP_DEAD` entries keep counting as dense until an insert on the page or a VACUUM compacts it; only completely empty pages leave the tree | [nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1785-L1799), [nbtinsert.c#_bt_findinsertloc-lp-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L752-L761), [nbtpage.c#_bt_delitems_delete](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1058-L1079), [nbtree.c#btvacuumpage-pagedel](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1338-L1347), [maintenance.sgml#routine-reindex-partly-empty](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L866-L874) |
| Planner sizing comes from physical index pages for ordinary indexes and from `estimate_rel_size` for partial indexes | [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L971), [plancat.c#estimate_rel_size-index-tuples](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L984-L1026) |
| `numIndexPages` scales pro rata with `index->pages / index->tuples`, is charged at the index tablespace's random page cost, and is cache-adjusted for repeated scans | [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780), [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835), [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L786-L878), [costsize.c#cost_index-amcostestimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L537-L560) |
| A one-leaf probe still pays `(tree_height + 1) * 50 * cpu_operator_cost`, and the height comes from `_bt_getrootheight` | [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L418) |
| B-tree scans position once and then walk the leaf chain one buffer per right-link step, in both scan directions | [nbtree.c#btgettuple](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L212-L284), [nbtsearch.c#_bt_first-position](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1244-L1331), [nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381), [nbtsearch.c#_bt_steppage-nextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1661-L1690), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800), [nbtsearch.c#_bt_readnextpage-backward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1801-L1903), [nbtsearch.c#_bt_walk_left](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1930-L2053) |
| Per-page executor work is a `_bt_getbuf` read plus a `_bt_readpage` pass that saves matches, with an early stop from the high key | [nbtpage.c#_bt_getbuf](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L747-L759), [nbtsearch.c#_bt_readpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1383-L1597), [nbtsearch.c#_bt_readpage-forward-loop](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1466-L1531), [nbtsearch.c#_bt_readpage-high-key](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1503-L1525), [nbtsearch.c#_bt_saveitem](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1599-L1616) |
| Bitmap index scans and index-only scans inherit the same index-side page walk | [nbtree.c#btgetbitmap](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L286-L342), [indexam.c#index_getnext_tid](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L501-L545), [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170) |
| Every buffer access takes a 128-way partitioned mapping lock, and the planner counts index pages in the cache competition term | [bufmgr.c#BufferAlloc-hit](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1011-L1035), [buf_internals.h#BufMappingPartitionLock](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L121-L131), [lwlock.h#NUM_BUFFER_PARTITIONS](../../../../raw/postgres-12/src/include/storage/lwlock.h#L106-L113), [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L786-L878) |
| No v12 scan path prefetches an index page: all four backend `PrefetchBuffer` call sites name a heap relation's main fork, `effective_io_concurrency` is documented as bitmap-heap-only, and only the `pg_prewarm` contrib module can prefetch an index fork on demand | [bufmgr.c#PrefetchBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L521-L530), [nodeBitmapHeapscan.c#prefetch](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L501-L509), [nodeBitmapHeapscan.c#prefetch-second](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L550-L560), [vacuumlazy.c#prefetch](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L2070-L2081), [heapam.c#prefetch-xid-horizon](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L6948-L6958), [pg_prewarm.c#prefetch-loop](../../../../raw/postgres-12/contrib/pg_prewarm/pg_prewarm.c#L159-L164), [config.sgml#effective_io_concurrency](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2166-L2181) |
| `EXPLAIN BUFFERS` reports per-node shared and local hit/read/dirtied/written and temp read/written only, with no index-versus-heap split | [explain.c#plan-buffer-usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L1864-L1866), [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2985), [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33) |
| An index's own `pg_class` page and tuple counts are written by the index build, by a plain `ANALYZE`, and by VACUUM for exact counts; fixture G measures the `ANALYZE` path correcting 551 to 1648 `relpages` with no VACUUM | [index.c#index_update_stats-callers](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2986), [analyze.c#index-relstats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629), [nbtree.c#btvacuumcleanup](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L891-L942), [vacuumlazy.c#lazy_cleanup_index-relstats](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1803-L1815) |
| All five relevant settings are `PGC_USERSET`, so session or transaction scope with no reload or restart | [guc.c#random_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3217-L3227), [guc.c#seq_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3207-L3216), [guc.c#effective_cache_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3117), [guc.c#cpu_operator_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3250-L3260), [guc.c#effective_io_concurrency](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2759-L2775) |
| The density diagnostic is a contrib module, and the costing path's `BTREE_AM_OID` comes from a generated catalog header | [contrib/pgstattuple/Makefile](../../../../raw/postgres-12/contrib/pgstattuple/Makefile#L1-L13), [pg_am.dat#BTREE_AM_OID](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L20), [catalog/Makefile:51](../../../../raw/postgres-12/src/backend/catalog/Makefile#L51) |
| No pinned test compares scan I/O or cost across leaf densities | [pgstattuple.sql#pgstatindex-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L9-L113), [pgstattuple.out#empty-index-NaN](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L44-L52), [btree_index.sql#tall-fillfactor](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L110-L123), [btree_index.sql#page-recycling](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L144-L162) |
| No universal density threshold for `REINDEX` exists in v12 source or docs | [ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57), [maintenance.sgml#routine-reindex-partly-empty](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L866-L874) |

## Open Questions

- Device I/O is still not isolated. `EXPLAIN` reports buffer accesses, and its per-node `BufferUsage` never splits index pages from heap pages ([explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2985), [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33)). Two things narrow the gap without closing it. The cumulative per-relation counters do separate index from heap when one statement is isolated, which is how the 2735-plus-1 split above was obtained, and a 1MB buffer pool converts the extra pages into a steady 2735 against 4118 misses per repetition. Both are shared-buffer misses; the operating system page cache still served the files, so no elapsed-time claim about storage follows.
- The breakeven point where a low-density index loses to a sequential scan depends on `random_page_cost`, `cpu_tuple_cost`, correlation, and cache residency. The v12 planner derives nothing from `pgstatindex` output, so no threshold is source-backed ([selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835), [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L786-L878)).
- The half-dead page case is source-backed but not measured here, because producing a durable half-dead leaf page requires an interrupted or crashed VACUUM ([pgstatindex.c#page-classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800)).
- Fixture F pins the tree-level band only at one row count. At 100,000 rows the 90-to-60 change adds a level for key widths between roughly 104 and 112 bytes and nowhere else in the 8-to-220-byte sweep, but the band moves with row count, and v12 exposes no planner input that would predict it ([plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L418)).
- An earlier revision of this page published warm buffer counts of 2738 and 4121 for the full scan and parallel plan totals of 22647.09 and 28199.09. The 2026-09-07 re-measurement reproduced every other figure in fixtures A and B exactly but read 2736 and 4119 buffers, and 22188.97 and 27740.97 for the parallel plans. A later run on a server rebuilt from the same pin settled the buffer half: the serial plan reads 2736 and 4119 while the default parallel plan reads exactly 2738 and 4121, so the earlier figures were parallel-plan totals carrying a serial label; the index blocks are 2735 and 4118 under both plans, and the two extra buffers are visibility-map blocks pinned once per participating process. The cost half is narrowed but not pinned. Both earlier totals sit exactly 458.12 above the fully all-visible values, and forging `pg_class.relallvisible = 3970` on both 4425-page heaps reproduces them to within 0.88, the same residual in both, which is what a heap that was not fully all-visible at the time would produce; no integer `relallvisible` closes that last 0.88. See [Open Questions](leaf-density-vs-fragmentation-index-scan-io.md#open-questions) on the density-versus-fragmentation page, where that run is recorded.

## Source References

- [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365)
- [pgstatindex.c#relation-checks](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L224-L238)
- [pgstatindex.c#full-block-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315)
- [pgstatindex.c#page-classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310)
- [pgstatindex.c#leaf-page-accounting](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L300)
- [pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307)
- [pgstatindex.c#index_size](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L336-L341)
- [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L351)
- [contrib/pgstattuple/Makefile](../../../../raw/postgres-12/contrib/pgstattuple/Makefile#L1-L13)
- [pgstattuple--1.4--1.5.sql#pgstatindex-grants](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)
- [pg_prewarm.c#prefetch-loop](../../../../raw/postgres-12/contrib/pg_prewarm/pg_prewarm.c#L159-L164)
- [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597)
- [bufpage.c#PageGetExactFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L626-L647)
- [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L55-L68)
- [nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L97-L113)
- [nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171)
- [nbtree.h#page-flag-macros](../../../../raw/postgres-12/src/include/access/nbtree.h#L187-L196)
- [nbtree.h#P_FIRSTDATAKEY](../../../../raw/postgres-12/src/include/access/nbtree.h#L217-L219)
- [nbtree.h#BTScanPosItem](../../../../raw/postgres-12/src/include/access/nbtree.h#L541-L546)
- [nbtree.h#BTScanPosData](../../../../raw/postgres-12/src/include/access/nbtree.h#L548-L583)
- [nbtree.h#BTScanOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L629-L669)
- [nbtsort.c#_bt_pagestate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L709-L734)
- [nbtsplitloc.c#_bt_findsplitloc-header](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L97-L105)
- [nbtsplitloc.c:170](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L170)
- [nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L275-L331)
- [nbtsplitloc.c#split-strategy-overrides](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L403-L422)
- [nbtinsert.c#_bt_findinsertloc-lp-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L752-L761)
- [nbtinsert.c#_bt_vacuum_one_page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L2243-L2288)
- [nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1785-L1799)
- [nbtpage.c#_bt_getbuf](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L747-L759)
- [nbtpage.c#_bt_relbuf](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L913-L917)
- [nbtpage.c#_bt_delitems_delete](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1058-L1079)
- [nbtree.c#bthandler-callbacks](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L128-L148)
- [nbtree.c#btgettuple](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L212-L284)
- [nbtree.c#btgetbitmap](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L286-L342)
- [nbtree.c#btvacuumcleanup](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L891-L942)
- [nbtree.c#btvacuumpage-recycle](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1166-L1173)
- [nbtree.c#btvacuumpage-delitems](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1273-L1294)
- [nbtree.c#btvacuumpage-pagedel](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1338-L1347)
- [nbtsearch.c#_bt_search](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L91-L323)
- [nbtsearch.c#endpoint-start](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L980-L998)
- [nbtsearch.c#_bt_first-position](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1244-L1331)
- [nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381)
- [nbtsearch.c#_bt_readpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1383-L1597)
- [nbtsearch.c#_bt_readpage-forward-loop](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1466-L1531)
- [nbtsearch.c#_bt_readpage-high-key](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1503-L1525)
- [nbtsearch.c#_bt_saveitem](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1599-L1616)
- [nbtsearch.c#_bt_steppage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1618-L1724)
- [nbtsearch.c#_bt_steppage-nextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1661-L1690)
- [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800)
- [nbtsearch.c#_bt_readnextpage-backward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1801-L1903)
- [nbtsearch.c#_bt_walk_left](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1930-L2053)
- [nbtsearch.c#_bt_endpoint](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L2136-L2229)
- [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407)
- [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L418)
- [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L971)
- [plancat.c#estimate_rel_size-index-tuples](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L984-L1026)
- [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780)
- [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835)
- [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116)
- [costsize.c#cost_index-amcostestimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L537-L560)
- [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L786-L878)
- [costsize.c#cost_agg-plain](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L2193-L2201)
- [indexam.c#index_getnext_tid](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L501-L545)
- [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170)
- [nodeBitmapHeapscan.c#prefetch](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L501-L509)
- [nodeBitmapHeapscan.c#prefetch-second](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L550-L560)
- [explain.c#plan-buffer-usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L1864-L1866)
- [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2985)
- [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33)
- [bufmgr.c#PrefetchBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L521-L530)
- [bufmgr.c#BufferAlloc-hit](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1011-L1035)
- [bufmgr.c#LockBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3585-L3607)
- [buf_internals.h#BufMappingPartitionLock](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L121-L131)
- [lwlock.h#NUM_BUFFER_PARTITIONS](../../../../raw/postgres-12/src/include/storage/lwlock.h#L106-L113)
- [vacuumlazy.c#lazy_cleanup_index-relstats](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1803-L1815)
- [vacuumlazy.c#prefetch](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L2070-L2081)
- [heapam.c#prefetch-xid-horizon](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L6948-L6958)
- [analyze.c#index-relstats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629)
- [index.c#index_update_stats-callers](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2986)
- [guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2386)
- [guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2396)
- [guc.c#effective_io_concurrency](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2759-L2775)
- [guc.c#effective_cache_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3117)
- [guc.c#seq_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3207-L3216)
- [guc.c#random_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3217-L3227)
- [guc.c#cpu_operator_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3250-L3260)
- [pg_am.dat#BTREE_AM_OID](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L20)
- [catalog/Makefile:51](../../../../raw/postgres-12/src/backend/catalog/Makefile#L51)
- [config.sgml#effective_io_concurrency](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2166-L2181)
- [config.sgml#seq_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4696-L4711)
- [config.sgml#random_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4713-L4770)
- [maintenance.sgml#routine-reindex-partly-empty](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L866-L874)
- [maintenance.sgml#routine-reindex-adjacency](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L882-L888)
- [create_index.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L369-L392)
- [ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57)
- [pgstattuple.sgml#avg_leaf_density-column](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L251-L255)
- [pgstattuple.sql#pgstatindex-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L9-L113)
- [pgstattuple.out#empty-index-NaN](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L44-L52)
- [btree_index.sql#tall-fillfactor](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L110-L123)
- [btree_index.sql#page-recycling](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L144-L162)

## Navigation

- [v12/index](../../index.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
- [How pgstatindex Calculates B-Tree Index Statistics in PostgreSQL 12 (unverified)](how-pgstatindex-calculates-information.md)
- [B-Tree Leaf Density vs Fragmentation Impact on Index Scan I/O in PostgreSQL 12 (unverified)](leaf-density-vs-fragmentation-index-scan-io.md)
- [How Bloated Indexes Affect the Query Planner in PostgreSQL 12 (unverified)](../query-planning/bloated-indexes-query-planner.md)
- [EXPLAIN ANALYZE BUFFERS Output in PostgreSQL 12 (unverified)](../observability/explain-analyze-buffers-output.md)
