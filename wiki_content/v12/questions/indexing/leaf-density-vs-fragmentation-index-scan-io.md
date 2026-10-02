---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# B-Tree Leaf Density vs Fragmentation Impact on Index Scan I/O in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [What PostgreSQL 12 measures](#what-postgresql-12-measures)
  - [Where index scan reads come from](#where-index-scan-reads-come-from)
  - [Density impact estimates](#density-impact-estimates)
  - [Fragmentation impact estimates](#fragmentation-impact-estimates)
  - [Combined estimate matrix](#combined-estimate-matrix)
  - [Exact-pin measurements](#exact-pin-measurements)
  - [Reproduction](#reproduction)
  - [How fragmentation arises](#how-fragmentation-arises)
  - [What both metrics hide](#what-both-metrics-hide)
  - [Which one matters more](#which-one-matters-more)
  - [Settings and apply scope](#settings-and-apply-scope)
  - [Operational reading](#operational-reading)
  - [Tests and coverage](#tests-and-coverage)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 12, what has more impact on index scan I/O: B-tree leaf density or fragmentation? Provide a comprehensive comparison, analyze different levels of density and fragmentation, and estimate the impact on index scan I/O.

## Answer

Leaf density has the larger effect on the index scan I/O that PostgreSQL 12 can see, count, and price. Density changes how many leaf pages a scan visits and how many blocks the planner charges for ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800)). Fragmentation reorders those same reads without changing their count: v12 never reads `leaf_fragmentation` in costing, and `EXPLAIN (ANALYZE, BUFFERS)` has no counter for physical-order disorder ([selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835), [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33), [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2985)). Fragmentation's cost therefore lands entirely on the storage path. Whether it dominates elapsed time there is a modelling question, not a measured one on this page. v12 documents random access to mechanical storage as normally much more expensive than four times sequential access, and every measurement below was taken on a warm cache, so they bound the buffer-count effect and say nothing about device latency ([config.sgml#random_page_cost-mechanical](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4737-L4744)).

Measured on an isolated server built from this page's pinned commit, over the same 1,000,000 `bigint` keys (details in [Exact-pin measurements](#exact-pin-measurements)):

| Index state | `leaf_pages` | `avg_leaf_density` | `leaf_fragmentation` | Warm plan buffers | of which index blocks |
|---|---:|---:|---:|---:|---:|
| Built with `fillfactor = 90` | 2733 | 90.06 | 0 | 2736 | 2735 |
| Built with `fillfactor = 60` | 4116 | 59.90 | 0 | 4119 | 4118 |
| Random-order retail inserts | 3684 | 66.89 | 49.84 | 3687 | 3686 |
| Same index rebuilt at `fillfactor = 67` | 3677 | 67.02 | 0 | 3680 | 3679 |

Dropping density from 90 to 60 raised buffer accesses by 50.5 %. Removing 49.84 % fragmentation at unchanged density moved them by 0.19 %, entirely explained by the 7-page size difference.

The buffer column is a plan total, not an index-side total. Every row above carries exactly one heap-relation block, the visibility-map page the index-only scan consults, which is what the last column removes ([nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170)).

For a fixed live tuple count and fixed average index tuple size, the leaf-page multiplier from density is approximately:

```text
leaf_page_multiplier = baseline_density / observed_density
```

So, compared with a 90 % dense B-tree, a 60 % dense B-tree needs about `90 / 60 = 1.5x` as many leaf pages for the same live index tuples. That extra page count feeds planner costing through `IndexOptInfo.pages` and `genericcostestimate`, and it feeds executor work because `_bt_next` steps through leaf pages with `_bt_steppage` and `_bt_readnextpage` after `_bt_first` positions the scan ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780), [nbtsearch.c#_bt_first-position](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1244-L1321), [nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800)).

`leaf_fragmentation` is different. In `pgstatindex`, it is the percentage of live leaf pages whose logical right link points to a lower physical block number. It measures physical-order reversals in the leaf chain, not free space, tuple count, jump distance, run length, or read latency ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307), [pgstatindex.c#leaf_fragmentation](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L352-L356), [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L55-L68)). A fragmented index can visit exactly the same number of leaf pages as an unfragmented index with the same density; the difference is that logical neighbors are less likely to be physical neighbors. The PostgreSQL 12 manual makes the same point: updated B-tree indexes can be slower than freshly built ones because logically adjacent pages are usually physically adjacent in a newly built index ([maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L882-L888)).

Practical ranking:

| Workload shape | More important factor | Why |
|---|---|---|
| Point lookup on a unique or highly selective key | Usually neither, unless density bloat raises tree height | The scan positions to one leaf page; `btcostestimate` adds a height-based descent charge so bloated indexes do not look free for one-leaf probes ([nbtsearch.c#_bt_first-position](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1244-L1321), [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116)). |
| Warm-cache range scan | Usually density | The same logical range touches more leaf buffers when density is lower, and the docs say fully cached data has no penalty for touching pages out of sequence ([nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800), [config.sgml#random_page_cost-cached](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4757-L4768)). |
| Cold large range scan on SSD or storage with low random-read penalty | Usually density, sometimes tied | Density changes page count; fragmentation changes order, and the docs model low-random-cost storage with a reduced `random_page_cost` ([config.sgml#random_page_cost-ssd](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4746-L4755)). |
| Cold large range scan on mechanical or seek-sensitive storage | Fragmentation can dominate latency | The same leaf count becomes many nonsequential fetches, and v12 documents random access to mechanical storage as normally much more expensive than four times sequential access ([config.sgml#random_page_cost-mechanical](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4737-L4744)). |
| Full index scan or index-only `COUNT(*)` style scan | Density sets the page count; fragmentation sets the locality | `_bt_endpoint` starts from an end when there is no usable boundary key, and `_bt_next` then walks the leaf chain page by page ([nbtsearch.c#endpoint-start](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L980-L998), [nbtsearch.c#_bt_endpoint](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L2136-L2229), [nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381)). |

The ranking above rests on the same executor path and the same two planner constants. v12 defines `seq_page_cost` as the cost of a disk page fetch that is part of a series of sequential fetches, default 1.0, and `random_page_cost` as the cost of a non-sequentially-fetched disk page, default 4.0 ([config.sgml#seq_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4696-L4711), [config.sgml#random_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4713-L4770), [cost.h#default-costs](../../../../raw/postgres-12/src/include/optimizer/cost.h#L21-L30)).

### What PostgreSQL 12 measures

`pgstatindex` computes `avg_leaf_density` by summing `PageGetFreeSpace(page)` and the per-page available capacity over live leaf pages, then returning `100 - free_space / max_avail * 100`. `PageGetFreeSpace` subtracts one line-pointer slot when possible, so the value is not the raw `pd_upper - pd_lower` gap ([pgstatindex.c#leaf-page-accounting](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L300), [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L351), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597)).

`pgstatindex` computes `leaf_fragmentation` as `fragments / leaf_pages * 100`, where `fragments` increments only when a live leaf page's `btpo_next` is not `P_NONE` and points to an earlier physical block. This is a one-bit-per-leaf-page physical-order test, not a cost model, and the v12 documentation defines the column only as "Leaf page fragmentation" ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307), [pgstatindex.c#leaf_fragmentation](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L352-L356), [pgstattuple.sgml#leaf_fragmentation-column](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L257-L261)).

Both numbers come from a full physical read of the index: `pgstatindex` walks every block from 1 to `RelationGetNumberOfBlocks`, share-locking each page, using a `BAS_BULKREAD` strategy ([pgstatindex.c:222](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L222), [pgstatindex.c#full-block-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315)).

The default B-tree leaf fillfactor is 90 %, while pages above the leaf level use a fixed 70 % fillfactor. The v12 header says the leaf fillfactor is applied during index build and when splitting a rightmost page; non-rightmost splits try to divide the data equally, and a page filled entirely with one duplicate value splits at an effective 96 % fillfactor ([nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171)). The split-point chooser adds one v12 case the header does not name: a non-rightmost leaf split whose new item sits at the rightmost point of a localized grouping can also apply the leaf fillfactor instead of splitting 50:50 ([nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L275-L331)). A second override runs after that first choice. `_bt_findsplitloc` calls `_bt_strategy` to classify the page, and `SPLIT_SINGLE_VALUE` then re-sorts the split points at `BTREE_SINGLEVAL_FILLFACTOR`, which is where the header's 96 % figure is actually applied, while `SPLIT_MANY_DUPLICATES` widens the split interval and leaves the multiplier alone ([nbtsplitloc.c#split-strategy-overrides](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L403-L422)).

### Where index scan reads come from

For a plain B-tree scan, `_bt_first` preprocesses the scan keys, descends with `_bt_search`, positions on the target leaf page with `_bt_binsrch`, and loads matching items from that page with `_bt_readpage`. Later calls to `_bt_next` return saved items from the current page until the page is exhausted, then call `_bt_steppage` ([nbtsearch.c#_bt_first](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L746-L1331), [nbtsearch.c#_bt_first-position](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1244-L1321), [nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381)).

For forward scans, `_bt_steppage` uses the previously saved `nextPage` right link, and `_bt_readnextpage` reads each candidate leaf page with `_bt_getbuf`, skips it and follows its own `btpo_next` if the page is deleted or half-dead, and otherwise hands it to `_bt_readpage`, which stores matching TIDs in the backend-local scan position array ([nbtsearch.c#_bt_steppage-nextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1661-L1690), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800), [nbtsearch.c#_bt_readpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1383-L1616)). One leaf page per right-link step is therefore one buffer access, whatever the physical block numbers are.

For backward scans, `_bt_readnextpage` uses `_bt_walk_left`, which is more complex because it must handle a left sibling that splits while the scan is in flight and a current page that gets deleted after the scan leaves it ([nbtsearch.c#_bt_readnextpage-backward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1801-L1903), [nbtsearch.c#_bt_walk_left](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1930-L2053)).

No PostgreSQL 12 scan path prefetches an index page. All four backend `PrefetchBuffer` call sites name `MAIN_FORKNUM` of a heap relation: two in the bitmap heap scan's prefetch iterator, one in lazy vacuum's truncation scan, and one in the heap TID horizon helper. The documentation likewise states that `effective_io_concurrency` currently affects only bitmap heap scans ([bufmgr.c#PrefetchBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L521-L530), [nodeBitmapHeapscan.c#prefetch](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L501-L509), [nodeBitmapHeapscan.c#prefetch-second](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L550-L560), [vacuumlazy.c:2078](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L2078), [heapam.c:6956](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L6956), [config.sgml#effective_io_concurrency](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2166-L2181)). One contrib module is the exception. `pg_prewarm` loops over a caller-chosen block range and prefetches whatever fork it was handed, so it can prefetch an index fork on demand ([pg_prewarm.c#prefetch-loop](../../../../raw/postgres-12/contrib/pg_prewarm/pg_prewarm.c#L159-L164)). Inside the server, nothing overlaps a backward leaf-chain jump with the next read, so the whole fragmentation penalty is left to kernel read-ahead and the device.

`EXPLAIN (ANALYZE, BUFFERS)` prints node-level shared and local hit, read, dirtied, and written counters plus temp read and written counters from `Instrumentation.bufusage`. It does not split a node's buffers into index pages versus heap pages, and it does not label sequential versus nonsequential reads ([explain.c#plan-buffer-usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L1864-L1866), [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2985), [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33)).

### Density impact estimates

These estimates assume the same live index tuple count, the same average tuple width, the same visibility state, and a scan wide enough that leaf-page walking dominates the one-time descent. They estimate leaf pages visited, not heap fetches.

| Average leaf density | Leaf pages versus 90 % baseline | Extra leaf page visits | PostgreSQL-visible I/O effect |
|---:|---:|---:|---|
| 95 % | 0.95x | About 5 % fewer | Possible after compact data or duplicate-heavy effective fill behavior; fewer leaf buffers than 90 % for the same live tuple volume. |
| 90 % | 1.00x | Baseline | Default fresh-build leaf target. |
| 80 % | 1.13x | 12.5 % more | Small but visible for wide scans. |
| 70 % | 1.29x | 28.6 % more | Often enough to change large range-scan buffer counts. |
| 60 % | 1.50x | 50.0 % more | Strong direct impact on range scans and full index scans. |
| 50 % | 1.80x | 80.0 % more | Bloat-sized effect; more planner cost and more executor leaf-page steps. |
| 40 % | 2.25x | 125.0 % more | More than doubles leaf-page work for the same logical key volume. |
| 30 % | 3.00x | 200.0 % more | Severe density loss; index-side page count can dominate. |

The planner path matches this page-count model. For ordinary non-partial indexes, `get_relation_info` sets `IndexOptInfo.pages` from `RelationGetNumberOfBlocks(indexRelation)` and locks `IndexOptInfo.tuples` to the parent table estimate; for partial indexes it calls `estimate_rel_size`, whose index case reports current blocks as pages. `genericcostestimate` then computes `numIndexPages = ceil(numIndexTuples * index->pages / index->tuples)` when both counts are greater than one, and charges the index tablespace's random page cost per page, adjusted by the Mackert-Lohman cache model for repeated scans ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L971), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780), [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835), [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L786-L878)).

Two caveats on that mapping. `index->pages` is the whole main fork, so it also counts the metapage, internal pages, half-dead pages, and deleted pages; the density-to-page-count translation is exact only when the change is confined to live leaf pages ([pgstatindex.c#index_size](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L336-L341), [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407)). And for a one-leaf point probe, density usually does not change the number of leaf pages visited at all. PostgreSQL 12 still adds an explicit B-tree descent charge of `(tree_height + 1) * 50.0 * cpu_operator_cost`, whose comment says the charge exists so that bloated indexes do not appear to have the same search cost as unbloated ones when only a single leaf page is expected ([selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L418)).

### Fragmentation impact estimates

These estimates assume the same density and the same logical key range. Under those assumptions, fragmentation adds no leaf pages. It changes the physical order of the block numbers read while following the logical leaf chain.

Let:

```text
L = leaf pages visited by the logical scan
N = share of right-link transitions that do not go to the next physical block
S = cost of a sequential page fetch
R = cost of a nonsequential page fetch
```

The input is `N`, not `leaf_fragmentation`, and the difference is the single most important caveat on this page. `pgstatindex` counts a leaf page as fragmented only when its right link points *backward*, at a lower block number ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307), [pgstatindex.c#leaf_fragmentation](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L352-L356)). A right link that jumps a thousand blocks *forward* costs a seek and is counted as perfectly ordered. So `leaf_fragmentation / 100` is a lower bound on `N`, and the measured gap is large: in the fixture under [Exact-pin measurements](#exact-pin-measurements) the metric read 49.84 while `N` was 1.00, because not one of the 3683 forward links pointed at the next physical block. Use `leaf_fragmentation` to detect disorder, and the `pageinspect` census under [Reproduction](#reproduction) to size it.

A simple storage-order model is:

```text
order_cost_multiplier = 1 + N * (R / S - 1)
```

This is not PostgreSQL 12 planner output. It is a sensitivity model built on v12's documented distinction between sequential and nonsequential page fetches, with defaults 1.0 and 4.0 ([config.sgml#seq_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4696-L4711), [config.sgml#random_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4713-L4770), [cost.h#default-costs](../../../../raw/postgres-12/src/include/optimizer/cost.h#L21-L30)). It also assumes each non-adjacent transition costs a full nonsequential fetch, which overstates short jumps that kernel read-ahead may still cover.

Using the default `R / S = 4` as a nonsequential-sensitive model:

| `N`, non-adjacent transition share | Non-adjacent transitions in a representative `L`-page scan | Order-cost multiplier at `R / S = 4` | Smallest `leaf_fragmentation` that can accompany it | PostgreSQL buffer counter expectation |
|---:|---:|---:|---:|---|
| 0 % | `0` | 1.00x | 0 | Same leaf-page count as density predicts; best physical locality. |
| 10 % | `0.10 * (L - 1)` | 1.30x | 0 | Same distinct leaf pages, some order breaks. |
| 25 % | `0.25 * (L - 1)` | 1.75x | 0 | Same distinct leaf pages; cold-storage latency can become visible. |
| 50 % | `0.50 * (L - 1)` | 2.50x | 0 | Same distinct leaf pages; order cost can exceed a 60-versus-90 density penalty in cold-storage latency. |
| 75 % | `0.75 * (L - 1)` | 3.25x | 0 | Same distinct leaf pages; physical-order cost can dominate elapsed time. |
| 100 % | `1.00 * (L - 1)` | 4.00x | 0 | Worst-case sensitivity endpoint. The measured fixture sits on this row at `leaf_fragmentation` 49.84. |

The fourth column is 0 on every row because a chain of forward-only jumps can be arbitrarily disordered while `leaf_fragmentation` reads zero. That is why the metric cannot be used as `N` directly.

When pages are already cached, the docs say setting `random_page_cost` equal to `seq_page_cost` makes sense because there is then no penalty for touching pages out of sequence. Under `R / S = 1` the order-cost multiplier is 1.00x at every level of disorder, so density dominates the PostgreSQL-visible buffer work ([config.sgml#random_page_cost-cached](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4757-L4768)).

For SSD-like storage, the docs say storage with a low random read cost relative to sequential may be better modeled with a lower `random_page_cost`. At `R / S = 1.2` the same model gives `1 + N * 0.2`, so even fully non-adjacent traversal is only a 1.20x order penalty, which is smaller than the 1.50x density penalty from 60 % versus 90 % leaf density ([config.sgml#random_page_cost-ssd](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4746-L4755)).

### Combined estimate matrix

The combined model for a large cold forward range scan is:

```text
combined_multiplier = (0.90 / density) * (1 + N * (R / S - 1))
```

Here `density` and `N` are fractions, such as `0.60` and `0.50`. The first term estimates extra leaf pages. The second term estimates the physical-order penalty. PostgreSQL 12 models the first term directly through physical index pages and does not model the second term at all ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780), [pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307)).

At `R / S = 4`:

| Density | `N` = 0 % | `N` = 25 % | `N` = 50 % | `N` = 75 % | `N` = 100 % |
|---:|---:|---:|---:|---:|---:|
| 90 % | 1.00x | 1.75x | 2.50x | 3.25x | 4.00x |
| 80 % | 1.13x | 1.97x | 2.81x | 3.66x | 4.50x |
| 70 % | 1.29x | 2.25x | 3.21x | 4.18x | 5.14x |
| 60 % | 1.50x | 2.63x | 3.75x | 4.88x | 6.00x |
| 50 % | 1.80x | 3.15x | 4.50x | 5.85x | 7.20x |
| 40 % | 2.25x | 3.94x | 5.63x | 7.31x | 9.00x |

At `R / S = 1.2`, which represents a much lower random-read penalty:

| Density | `N` = 0 % | `N` = 25 % | `N` = 50 % | `N` = 75 % | `N` = 100 % |
|---:|---:|---:|---:|---:|---:|
| 90 % | 1.00x | 1.05x | 1.10x | 1.15x | 1.20x |
| 80 % | 1.13x | 1.18x | 1.24x | 1.29x | 1.35x |
| 70 % | 1.29x | 1.35x | 1.41x | 1.48x | 1.54x |
| 60 % | 1.50x | 1.58x | 1.65x | 1.73x | 1.80x |
| 50 % | 1.80x | 1.89x | 1.98x | 2.07x | 2.16x |
| 40 % | 2.25x | 2.36x | 2.48x | 2.59x | 2.70x |

The measured fixture is one cell of the first table. At 66.89 density and `N` = 1.00 it predicts `(0.90 / 0.6689) * 4.00 = 5.38x` against a fresh 90 percent index, of which PostgreSQL's own counters showed only the `1.35x` page-count term; the rest is a storage-path prediction this page did not measure.

These tables estimate index-side leaf-page I/O pressure only. They do not estimate heap reads, visibility-map effects in index-only scans, CPU spent evaluating scan keys, kernel read-ahead behavior, controller caches, concurrent buffer churn, or tuple visibility checks outside the B-tree access method.

### Exact-pin measurements

All numbers below come from one isolated PostgreSQL 12.2 server built out of tree from this page's `pinned_commit`, with `shared_buffers = 512MB`, `autovacuum = off`, `synchronous_commit = on`, and `pgstattuple` plus `pageinspect` installed. The density and fragmentation fixtures each index 1,000,000 distinct `bigint` keys; the dead-space fixture uses 200,000. Buffer counts come from the second, warm `EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)` execution, so they count buffer accesses rather than device reads. [Reproduction](#reproduction) publishes every statement.

Two methodological points govern the whole section. First, an `EXPLAIN` buffer line is a plan total and cannot be split by relation, so each table below also reports the split obtained by resetting the cumulative counters around one warm execution and reading `pg_statio_user_indexes` against `pg_statio_user_tables` ([explain.c#plan-buffer-usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L1864-L1866), [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33)). Second, every fixture was gated on `pg_class.relallvisible = relpages` before measurement, because an index-only scan over a heap that is not fully all-visible silently becomes an index scan plus heap fetches; see [Reproduction](#reproduction) for why that gate is not optional.

Density only, two build fillfactors, both freshly built and therefore physically ordered:

| Measurement | `fillfactor = 90` | `fillfactor = 60` | Ratio |
|---|---:|---:|---:|
| `avg_leaf_density` | 90.06 | 59.90 | 0.665 |
| `leaf_fragmentation` | 0 | 0 | |
| `leaf_pages` | 2733 | 4116 | 1.506 |
| `internal_pages` | 11 | 16 | |
| `tree_level` | 2 | 2 | |
| `pg_class.relpages` | 2745 | 4133 | 1.506 |
| Warm plan buffers, serial | 2736 | 4119 | 1.505 |
| of which index blocks | 2735 | 4118 | 1.506 |
| of which visibility-map blocks | 1 | 1 | 1.000 |
| `Index Only Scan` node cost, serial | 25980.42 | 31532.42 | 1.214 |
| Warm plan buffers, default parallel plan | 2738 | 4121 | 1.505 |
| `Finalize Aggregate` total, default parallel plan | 22188.97 | 27740.97 | 1.250 |

Four things follow.

- The predicted multiplier `90.06 / 59.90 = 1.5035` matched the measured leaf-page ratio `4116 / 2733 = 1.5060` and the measured index-block ratio `4118 / 2735 = 1.5056`.
- The whole cost difference is index pages. The two indexes differ by 1388 physical blocks, 4133 against 2745, and the scan-node gap `31532.42 - 25980.42` is exactly `1388 * 4.0 = 5552.00` at the default `random_page_cost` ([selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835)). Tree height did not change, so the descent charge was identical.
- The 2735 index blocks are the root, one internal page, and 2733 leaves. The metapage is served from the relcache on a warm scan, because `_bt_getroot` caches the metapage contents in `rd_amcache` and re-reads only the root block ([nbtpage.c#_bt_getroot-cache](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L267-L307)).
- Plan shape moves the buffer count, and it moves the heap side, not the index side. The same scan under the default `max_parallel_workers_per_gather = 2` reads 2738 and 4121, two more each, while the index blocks stay at 2735 and 4118. The extra two are visibility-map blocks: `ioss_VMBuffer` lives in the per-process scan state and is initialised to `InvalidBuffer` in each worker, so the leader and its two workers each pin the page separately and the heap side reads 3 instead of 1 ([execnodes.h#IndexOnlyScanState](../../../../raw/postgres-12/src/include/nodes/execnodes.h#L1470-L1479), [nodeIndexonlyscan.c#ExecIndexOnlyScanInitializeWorker](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L678-L684)).

Backward scans read the same pages as forward scans. A full index-only scan in descending order measured 2736 warm buffers at 90 percent and 4119 at 60 percent, matching the forward figures exactly, on an index no other session was modifying ([nbtsearch.c#_bt_walk_left](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1930-L2053)).

Fragmentation only, produced by retail insertion in random key order under `setseed(0.5)` and then removed by a rebuild at a fillfactor chosen to reproduce the same density:

| Index state | `leaf_pages` | `avg_leaf_density` | `leaf_fragmentation` | `relpages` | Warm plan buffers | of which index blocks |
|---|---:|---:|---:|---:|---:|---:|
| Random-order retail inserts | 3684 | 66.89 | 49.84 | 3699 | 3687 | 3686 |
| Rebuilt at `fillfactor = 67` | 3677 | 67.02 | 0 | 3692 | 3680 | 3679 |

The `pageinspect` census of the same two indexes, over every live leaf page:

| Index state | Forward right links | Pointing backward | Pointing to `blkno + 1` | Not pointing to `blkno + 1` | Mean absolute jump |
|---|---:|---:|---:|---:|---:|
| Random-order retail inserts | 3683 | 1836 | 0 | 3683 | 1838.7 blocks |
| Rebuilt at `fillfactor = 67` | 3676 | 0 | 3663 | 13 | 1.0 blocks |

Three things follow.

- `pgstatindex`'s `leaf_fragmentation` reproduced exactly as the share of live leaf pages whose `btpo_next` points backward: `1836 / 3684 = 49.84 %` ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307)).
- Removing that fragmentation left buffer accesses essentially unchanged, 3687 to 3680. That 0.19 % move is exactly the 7-leaf-page size difference, which is what the source predicts: the executor pays one buffer access per right-link step regardless of block order ([nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800)).
- `leaf_fragmentation` understates the disorder badly, and the census puts a number on the gap. The metric read 49.84 %, but **not one** of the 3683 forward links pointed at the next physical block, so 100 % of the transitions were non-adjacent, and the average jump spanned 1839 blocks. The rebuilt index is the mirror image: 3663 of 3676 links go to the very next block and the mean jump is one. Its 13 non-adjacent links are the points where the physically interleaved internal pages sit between two leaves.

The fragmented row is seed-dependent. Repeating the same insert under four seeds gave:

| `setseed` | `leaf_pages` | `avg_leaf_density` | `leaf_fragmentation` |
|---:|---:|---:|---:|
| 0.1 | 3762 | 65.51 | 49.76 |
| 0.25 | 3740 | 65.89 | 49.89 |
| 0.5 | 3684 | 66.89 | 49.84 |
| 0.9 | 3744 | 65.82 | 49.84 |

Density lands between 65.51 and 66.89 and `leaf_fragmentation` between 49.76 and 49.89, so the fragmentation figure is stable near half the leaf pages while the page count is not. The `setseed(0.5)` row reproduced twice, byte for byte, on two separately built tables.

Dead space, showing that `avg_leaf_density` reports physical occupancy rather than live-entry density. A 200,000-row table lost 90 percent of its rows, with no vacuum in between:

| State | Live rows | `leaf_pages` | `avg_leaf_density` | Plan buffers | Index blocks | Heap blocks | `Heap Fetches` |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 200000 | 547 | 90.00 | 550 | 549 | 1 | 0 |
| After deleting 90 %, first scan | 20000 | 547 | 90.00 | 1435 | 549 | 886 | 200000 |
| After deleting 90 %, steady state | 20000 | 547 | 90.00 | 1435 | 549 | 886 | 20000 |
| After `VACUUM` | 20000 | 547 | 9.26 | 550 | 549 | 1 | 0 |

The index looked perfectly dense at 90.00 while nine out of ten of its entries were dead, and the leaf-page count never dropped: after `VACUUM` removed the dead entries the same 547 leaf pages held 20,000 entries at 9.26 % density. That is the v12 documented failure mode, in which pages that keep a few keys stay allocated and only completely empty pages are reclaimed ([maintenance.sgml#routine-reindex-partly-empty](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L866-L874)).

The two middle rows need reading carefully, because the obvious explanation is wrong.

- The extra 885 buffers are heap **pages**, not heap **fetches**. The heap side went from 1 block to 886, which is the relation's 885 data pages plus the same visibility-map page. The 20,000 heap fetches collapse onto those 885 pages because `heapam_index_fetch_tuple` calls `ReleaseAndReadBuffer`, which returns the buffer it already holds when the next TID is on the same block, so a run of TIDs on one page costs one buffer access ([heapam_handler.c#heapam_index_fetch_tuple](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L117-L144), [bufmgr.c#ReleaseAndReadBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1510-L1553)).
- The heap is visited at all because `heap_delete` clears the page's visibility-map bit, so `VM_ALL_VISIBLE` fails and the index-only scan falls back to a heap fetch ([heapam.c#heap_delete-vm-clear](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L2704-L2710), [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170)).
- `Heap Fetches` falls from 200,000 to 20,000 between the first scan and the second, while the buffer count does not move. The first scan dirtied 546 leaf pages: it marked the 180,000 dead entries `LP_DEAD` through `_bt_killitems`, and later scans skip them without a heap fetch. The remaining 20,000 fetches are the live rows, and they still span every heap page ([nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1785-L1799)).

### Reproduction

These are the statements that produce every figure in the previous section. Most of them create and drop tables and are meant for a disposable server built from the pin, not for a database anyone cares about. The two read-backs at the end are the only ones worth pointing at a real index, and both read every block of the index they are given, so they are diagnostics rather than monitoring queries ([pgstatindex.c#full-block-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315)).

Server settings: `shared_buffers = 512MB`, `autovacuum = off`, `synchronous_commit = on`, `max_parallel_workers_per_gather = 2`, everything else default.

`synchronous_commit = on` is load-bearing, not incidental. With it off, the first `VACUUM` after a bulk insert cannot set the tuples' `xmin`-committed hint bits, because a hint bit may only be set once the commit record is flushed. Pages therefore stay out of the visibility map, `pg_class.relallvisible` stays 0, and every "index-only" scan below silently becomes an index scan plus a heap fetch per tuple. Measured on this server, that turned the 90 percent full scan from 2736 buffers and `Heap Fetches: 0` into 7161 buffers and `Heap Fetches: 1000000`. Gate every fixture on the catalog before measuring:

```sql
SELECT relname, relpages, relallvisible FROM pg_class WHERE relname = 'ld_a90';
```

Fixture A, density only:

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

Plan shapes. `enable_seqscan = off` throughout; `max_parallel_workers_per_gather = 0` for the serial rows and the default 2 for the parallel rows. Buffer counts come from the second, warm execution.

```sql
SET enable_seqscan = off;
SET max_parallel_workers_per_gather = 0;
-- run twice and read the second
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) SELECT count(*) FROM ld_a90;
-- backward full scan
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) SELECT id FROM ld_a90 ORDER BY id DESC OFFSET 999999;
RESET max_parallel_workers_per_gather;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) SELECT count(*) FROM ld_a90;
```

Splitting one warm scan into index blocks and visibility-map blocks. The warm-up, the reset and the measured run must share one session, or the measured session re-reads the metapage and the index count comes out one too high. The reset needs a quiet moment on either side, because the collector receives a statement's counters after the statement ends:

```sql
SELECT count(*) FROM ld_a90;          -- warm the cache
SELECT pg_sleep(1);
SELECT pg_stat_reset();
SELECT pg_sleep(1);
SELECT count(*) FROM ld_a90;
SELECT pg_sleep(2);
SELECT idx_blks_read, idx_blks_hit FROM pg_statio_user_indexes WHERE relname = 'ld_a90';
SELECT heap_blks_read, heap_blks_hit FROM pg_statio_user_tables WHERE relname = 'ld_a90';
```

Fixture C, fragmentation only. The index exists before the rows arrive, and `setseed` makes the insert order reproducible. The rebuild is a separate index at the fillfactor that reproduces the measured density:

```sql
SET max_parallel_workers_per_gather = 0;
CREATE TABLE ld_cf (id bigint);
CREATE INDEX ld_cf_idx ON ld_cf (id);
SELECT setseed(0.5);
INSERT INTO ld_cf SELECT g FROM generate_series(1,1000000) g ORDER BY random();
VACUUM (ANALYZE) ld_cf;

CREATE TABLE ld_c (id bigint);
CREATE INDEX ld_c_idx ON ld_c (id);
SELECT setseed(0.5);
INSERT INTO ld_c SELECT g FROM generate_series(1,1000000) g ORDER BY random();
VACUUM (ANALYZE) ld_c;
DROP INDEX ld_c_idx;
CREATE INDEX ld_c_idx ON ld_c (id) WITH (fillfactor = 67);
```

Fixture H, dead space. The baseline row is the same table before the delete:

```sql
CREATE TABLE ld_h3 (id bigint);
INSERT INTO ld_h3 SELECT g FROM generate_series(1,200000) g;
CREATE INDEX ld_h3_idx ON ld_h3 (id);
VACUUM (ANALYZE) ld_h3;
-- measure the baseline here, then
DELETE FROM ld_h3 WHERE id % 10 <> 0;
-- measure the first scan and the steady state here, then
VACUUM ld_h3;
```

The `pageinspect` census, the first statement worth running against a real index. It reads every block, so treat it as a diagnostic. Both timeouts are `PGC_USERSET`, so they apply at session or transaction scope with no reload and no restart ([guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2386), [guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2396)). `bt_page_stats` reports `btpo_next` as `0` for the rightmost page, matching `P_NONE`, and the `type = 'l'` filter keeps the census on live leaf pages ([nbtree.h:181](../../../../raw/postgres-12/src/include/access/nbtree.h#L181)):

```sql
SET /* wiki_leaf_density_vs_fragmentation */ statement_timeout = '10min';
SET /* wiki_leaf_density_vs_fragmentation */ lock_timeout = '5s';

WITH b AS MATERIALIZED (
  SELECT s.blkno, s.type, s.btpo_next
  FROM generate_series(1, (pg_relation_size('ld_cf_idx')/current_setting('block_size')::int)::int - 1) AS g(blkno),
       LATERAL bt_page_stats('ld_cf_idx', g.blkno) AS s
)
SELECT /* wiki_leaf_density_vs_fragmentation */
       count(*) AS leaf_pages,
       count(*) FILTER (WHERE btpo_next <> 0) AS forward_links,
       count(*) FILTER (WHERE btpo_next <> 0 AND btpo_next < blkno) AS backward_links,
       count(*) FILTER (WHERE btpo_next = blkno + 1) AS adjacent_links,
       count(*) FILTER (WHERE btpo_next <> 0 AND btpo_next <> blkno + 1) AS nonadjacent_links,
       round(avg(abs(btpo_next - blkno)) FILTER (WHERE btpo_next <> 0), 1) AS mean_jump
FROM b WHERE type = 'l';
```

The survey-query fixture, used to check that the statement under [Operational reading](#operational-reading) returns only ordinary B-trees:

```sql
CREATE SCHEMA surv;
CREATE TABLE surv.mixed (a int, b int[], r int4range, t text);
INSERT INTO surv.mixed SELECT g, ARRAY[g, g+1], int4range(g, g+10), 'x'||g FROM generate_series(1,2000) g;
CREATE INDEX mixed_btree_a ON surv.mixed (a);
CREATE INDEX mixed_hash ON surv.mixed USING hash (a);
CREATE INDEX mixed_gin ON surv.mixed USING gin (b);
CREATE INDEX mixed_gist ON surv.mixed USING gist (r);
CREATE INDEX mixed_brin ON surv.mixed USING brin (a);
CREATE TABLE surv.part (a int) PARTITION BY RANGE (a);
CREATE TABLE surv.part1 PARTITION OF surv.part FOR VALUES FROM (1) TO (100);
CREATE INDEX part_idx ON surv.part (a);
CREATE TEMP TABLE surv_temp (a int PRIMARY KEY);
```

### How fragmentation arises

During retail insertion, `_bt_insertonpg` splits a page when `PageGetFreeSpace(page) < itemsz`. `_bt_split` acquires the new right page with `_bt_getbuf(rel, P_NEW, BT_WRITE)`, sets the left page's `btpo_next` to the new block, and copies the old right link into the new page's `btpo_next` while pointing its `btpo_prev` back at the original page ([nbtinsert.c#_bt_insertonpg-split-test](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L963-L1002), [nbtinsert.c#_bt_split-new-right-page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L1403-L1439)).

When `_bt_getbuf` is asked for `P_NEW`, it first asks `GetFreeIndexPage` for a free page, conditionally locks the candidate, and reinitializes and returns it if `_bt_page_recyclable` agrees; only when the free space map has nothing usable does it extend the relation with `ReadBuffer(rel, P_NEW)` ([nbtpage.c#_bt_getbuf-fsm-reuse](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L801-L832), [nbtpage.c#_bt_getbuf-extend](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L844-L875)). Both outcomes break physical order in different ways: reuse can place a new logical neighbor at an older, lower block, and extension places it at the very end of the relation, far from the page it logically follows. The measured random-insert index above shows the extension case: every one of its 3683 forward right links jumped, on average by 1839 blocks, and none landed on the next physical page.

VACUUM supplies the reuse path by calling `RecordFreeIndexPage` for each B-tree page that `_bt_page_recyclable` accepts. Those pages only become findable once `btvacuumscan` has finished the index and called `IndexFreeSpaceMapVacuum`, which it skips entirely when it recycled nothing ([nbtree.c#btvacuumpage-recycle](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1166-L1173), [nbtree.c#btvacuumscan-fsm-vacuum](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1087-L1091), [indexfsm.c#GetFreeIndexPage](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L32-L46)).

An insert can also recover density in place instead of splitting: when the target page is full and carries the `BTP_HAS_GARBAGE` hint, `_bt_findinsertloc` calls `_bt_vacuum_one_page`, which erases the page's `LP_DEAD` items through `_bt_delitems_delete` ([nbtinsert.c#_bt_findinsertloc-lp-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L752-L761), [nbtinsert.c#_bt_vacuum_one_page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L2243-L2288)).

The manual's operational summary matches those mechanics: completely empty B-tree pages are reclaimed for re-use, partly empty pages remain allocated and waste space, and a freshly constructed B-tree index is slightly faster to access because logically adjacent pages are usually also physically adjacent ([maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L852-L888), [ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57)).

### What both metrics hide

Four blind spots matter when either metric is used to reason about scan I/O.

- Dead entries count as dense. `_bt_killitems` only marks a matched index tuple `LP_DEAD` in place, so its storage keeps counting toward `avg_leaf_density` until an insert on the same page or a VACUUM removes it ([nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1785-L1799), [nbtinsert.c#_bt_vacuum_one_page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L2243-L2288)). The dead-space measurement above shows the consequence: 90.00 % density over 90 % dead entries.
- Half-dead pages are invisible to both metrics but still cost reads. `pgstatindex` classifies a page by `P_ISDELETED` first and then by `P_IGNORE`, so a half-dead page lands in `empty_pages` and is excluded from `leaf_pages`, hence from both `avg_leaf_density` and `leaf_fragmentation` ([pgstatindex.c#page-classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310), [nbtree.h#page-flag-macros](../../../../raw/postgres-12/src/include/access/nbtree.h#L189-L194)). The first stage of page deletion marks the leaf half-dead but leaves it linked to its siblings, so a scan still reads it and steps right ([nbtpage.c#_bt_mark_page_halfdead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1645-L1652), [README#page-deletion](../../../../raw/postgres-12/src/backend/access/nbtree/README#L214-L226), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800)).
- Deleted pages are the opposite case. The second deletion stage rewrites the siblings' side links and marks the page `BTP_DELETED`, so scans no longer traverse it, yet it still occupies a block in the main fork and therefore still inflates the `index->pages` the planner prices ([nbtpage.c#_bt_unlink_halfdead_page-sidelinks](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1967-L1982), [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407)).
- Both columns can be `NaN`. `avg_leaf_density` is `NaN` when no live leaf page contributed available space, and `leaf_fragmentation` is `NaN` when `leaf_pages` is zero, which is what the regression test observes for an empty index ([pgstatindex.c#avg_leaf_density](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L351), [pgstatindex.c#leaf_fragmentation](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L352-L356), [pgstattuple.out#empty-index-NaN](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L44-L52)).

### Which one matters more

Density matters more when the question is "how many index leaf buffers will PostgreSQL touch?". For wide scans the executor walks more leaf pages when density is lower, and the planner estimates more index pages when the physical index is larger ([nbtsearch.c#_bt_steppage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1618-L1724), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780)). The exact-pin measurement puts a number on it: 50.5 % more buffer accesses at 59.90 % density than at 90.06 %.

Fragmentation matters more when the question is "how expensive is each of those reads on this storage path?". The executor still follows the logical leaf chain, but `leaf_fragmentation` says some right-link steps go backward in physical block order. PostgreSQL 12 documents nonsequential fetches as more expensive than sequential ones, especially for mechanical storage, while also documenting that fully cached data has no out-of-sequence penalty ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800), [config.sgml#random_page_cost-mechanical](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4737-L4744), [config.sgml#random_page_cost-cached](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4757-L4768)).

Point lookups usually hide both effects. A unique equality lookup pays one descent and one leaf-page visit; density affects it mainly if bloat increases tree height, and fragmentation has little opportunity to matter because the scan is not walking many leaf links ([nbtsearch.c#_bt_first-position](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1244-L1321), [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116)).

Full index scans expose both. When `_bt_first` finds no usable boundary keys, `_bt_endpoint` starts from the first or last leaf page and later `_bt_next` calls continue through the leaf chain. Density controls how many pages are in that chain for the same live tuple volume; fragmentation controls how physically ordered the chain is ([nbtsearch.c#endpoint-start](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L980-L998), [nbtsearch.c#_bt_endpoint](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L2136-L2229), [pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307)).

Bitmap index scans use the B-tree access method's `btgetbitmap`, which loops with `_bt_first` and `_bt_next` while adding TIDs to the bitmap, so the index side behaves the same way. The heap access pattern after bitmap creation is a separate executor concern, and it is the only part of the plan that v12 prefetches ([nbtree.c#btgetbitmap](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L286-L342), [nodeBitmapHeapscan.c#prefetch](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L501-L509)).

Index-only scans still walk the same index pages through `index_getnext_tid`; they avoid heap fetches only when the visibility map says the heap page is all-visible. Density and fragmentation therefore affect index-side I/O even when heap I/O is avoided ([indexam.c#index_getnext_tid](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L501-L545), [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170)).

### Settings and apply scope

Three settings appear in this analysis. Two of them, `seq_page_cost` and `random_page_cost`, are real levers; `effective_io_concurrency` is listed because it looks like one and is not. None needs a restart or a reload. All three are `PGC_USERSET`, so a session or transaction can change them with `SET` or `SET LOCAL`:

| Setting | v12 context | Apply scope | Relevance here |
|---|---|---|---|
| `seq_page_cost` | `PGC_USERSET` | Session or transaction | Sets the `S` in the order-cost model; also settable per tablespace ([guc.c#seq_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3206-L3216), [config.sgml#seq_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4696-L4711)). |
| `random_page_cost` | `PGC_USERSET` | Session or transaction | Sets the `R`; the planner reads the index tablespace's value through `get_tablespace_page_costs` ([guc.c#random_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3217-L3227), [config.sgml#random_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4713-L4770), [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835)). |
| `effective_io_concurrency` | `PGC_USERSET` | Session or transaction | Does not help a fragmented leaf chain; documented as affecting bitmap heap scans only ([guc.c#effective_io_concurrency](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2759-L2775), [config.sgml#effective_io_concurrency](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2166-L2181)). |

Neither page cost changes physical layout; they only change which plan the planner picks. The layout levers are `REINDEX` and the index `fillfactor` reloption. `REINDEX` acts at build time. The leaf fillfactor acts at build time and again at every rightmost split, and at a non-rightmost split that lands after a newly inserted item, so it keeps steering density long after the build ([nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171), [nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L275-L331), [ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57)).

### Operational reading

For index scan I/O visible in PostgreSQL counters, compare `leaf_pages`, `index_size`, and `avg_leaf_density` first. A fall from 90 % to 60 % density implies roughly 50 % more leaf-page visits for broad scans, which the exact-pin test reproduced as 50.5 % more buffer accesses ([pgstatindex.c#index_size](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L336-L341), [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L351), [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2985)).

For elapsed latency on cold scans, inspect `leaf_fragmentation` next, then stop trusting it as a magnitude. A 49.84 % fragmented index read 0.19 % more buffers, as measured above, but it can turn many logical next-page steps into nonsequential block accesses, and the same index was fully non-adjacent while the metric read half that. Treat a nonzero value as a signal to run the `pageinspect` census under [Reproduction](#reproduction), which reports the share that actually matters. Severity then still depends on cache residency, storage random-read cost, and kernel read-ahead ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307), [config.sgml#random_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4713-L4770)).

This survey reads both columns for every ordinary B-tree index. `pgstatindex` reads every block of each index, so it is a diagnostic, not a monitoring query; the `relkind = 'i'` filter keeps partitioned parents out because `IS_INDEX` tests for `RELKIND_INDEX` only, so a `relkind = 'I'` parent fails with `relation "..." is not a btree index`, and the `relpersistence` filter drops every temporary index. That is broader than the server's own rule, which rejects only *other* sessions' temporary relations because `pgstatindex` has no visibility into their local buffers. Executing it needs membership in `pg_stat_scan_tables`, a direct grant, or superuser, because the 1.5 script revokes `EXECUTE` from `PUBLIC` and grants it to that role. Both timeouts below are `PGC_USERSET`, so they apply at session or transaction scope with no reload or restart ([pgstatindex.c#full-block-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315), [pgstatindex.c#relkind-am-macros](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L70-L71), [pgstatindex.c#relation-checks](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L224-L238), [pgstattuple--1.4--1.5.sql#pgstatindex-grants](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92), [guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2386), [guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2396)):

```sql
SET /* wiki_leaf_density_vs_fragmentation */ statement_timeout = '10min';
SET /* wiki_leaf_density_vs_fragmentation */ lock_timeout = '5s';

WITH candidate AS MATERIALIZED (
    SELECT c.oid AS indexrelid,
           n.nspname AS schema_name,
           c.relname AS index_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_am am ON am.oid = c.relam
    WHERE c.relkind = 'i'
      AND am.amname = 'btree'
      AND c.relpersistence <> 't'
      AND n.nspname NOT IN ('pg_catalog', 'pg_toast', 'information_schema')
)
SELECT /* wiki_leaf_density_vs_fragmentation */
       k.schema_name,
       k.index_name,
       s.index_size / current_setting('block_size')::int AS blocks,
       s.leaf_pages,
       s.empty_pages,
       s.deleted_pages,
       s.avg_leaf_density,
       s.leaf_fragmentation
  FROM candidate k
  CROSS JOIN LATERAL pgstatindex(k.indexrelid::regclass) AS s
 WHERE s.leaf_pages > 0
 ORDER BY s.leaf_fragmentation DESC, s.avg_leaf_density;
```

The `AS MATERIALIZED` is defensive, not stylistic, and it guards exactly one of the three filters. v12 folds a single-reference, side-effect-free `WITH` query into the parent query by default ([queries.sgml#with-materialization](../../../../raw/postgres-12/doc/src/sgml/queries.sgml#L2221-L2236)). The `relkind` and `relpersistence` tests survive that inlining whatever the join order, because both are single-relation restrictions on `pg_class` and are applied at that scan. The access-method test is not, because it comes from the `pg_am` join, and an inlined form leaves the planner free to place that join above the lateral `pgstatindex` call. A plan that did so would reach a hash or GiST index first and fail with `relation "..." is not a btree index`. Materializing the candidate list removes that freedom ([pgstatindex.c#relation-checks](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L224-L238)). Re-run on a database also holding hash, GiST, GIN, and BRIN indexes, a partitioned parent index and this session's own temporary index, the query returned only ordinary B-trees and skipped all six. The `AS NOT MATERIALIZED` variant returned exactly the same rows, and its plan shows why that is luck rather than a guarantee: the `pg_class` scan carries `Filter: ((relpersistence <> 't'::"char") AND (relkind = 'i'::"char"))`, so those two filters are unconditional, while the access-method test remains a separate hash join that the planner merely happened to place below the function scan. The temporary index is the sharpest case. `pgstatindex` accepts this session's own temporary index and reported 3 leaf pages at 81.99 density for one, so the `relpersistence` filter is the survey's choice, not a server restriction.

For maintenance decisions, PostgreSQL 12 source and documentation define no universal threshold such as "reindex at 60 % density" or "reindex at 40 % fragmentation". The documentation recommends `REINDEX` for B-tree indexes with many empty or nearly-empty pages and notes that a rebuild can improve access speed by restoring physical adjacency ([maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L852-L888), [ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57)).

### Tests and coverage

The v12 `pgstattuple` regression test checks `pgstatindex` output for an empty B-tree and the error paths for unsupported relation kinds and access methods. It never populates a B-tree, so it never asserts a non-`NaN` density or a nonzero fragmentation ([pgstattuple.sql#pgstatindex-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L9-L113), [pgstattuple.out#empty-index-NaN](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L44-L52), [pgstattuple.out#partition-index-NaN](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L228-L236)).

The core `btree_index` regression test creates a deliberately tall B-tree with `fillfactor = 10` and later exercises multilevel page deletion and FSM page recycling, but it does not compare planner or executor I/O at different `avg_leaf_density` and `leaf_fragmentation` levels ([btree_index.sql#tall-fillfactor](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L110-L123), [btree_index.sql#page-recycling](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L144-L162)).

No test in the pinned checkout links either column to scan I/O. The measurements in this page were run against a disposable server built from the pin, not from an in-tree test.

## Context Reviewed

- Required wiki navigation: [versions](../../../versions.md), [wiki index](../../../index.md), [v12/index](../../index.md), and recent [log](../../../log.md).
- PostgreSQL 12 diagnostic sources: `contrib/pgstattuple/pgstatindex.c`, `contrib/pgstattuple/pgstattuple--1.4--1.5.sql`, `doc/src/sgml/pgstattuple.sgml`, `src/backend/storage/page/bufpage.c`, and `src/include/access/nbtree.h`.
- PostgreSQL 12 B-tree scan and maintenance sources: `nbtsearch.c`, `nbtinsert.c`, `nbtsplitloc.c`, `nbtpage.c`, `nbtutils.c`, `nbtree.c`, and `src/backend/access/nbtree/README`.
- PostgreSQL 12 planner and costing sources: `plancat.c`, `selfuncs.c`, `costsize.c`, `cost.h`, `guc.c`, `config.sgml`, and `indexam.sgml`.
- PostgreSQL 12 measurement and executor sources: `explain.c`, `instrument.h`, `indexam.c`, `nodeIndexonlyscan.c`, `nodeBitmapHeapscan.c`, `heapam_handler.c`, `heapam.c`, `vacuumlazy.c`, and `bufmgr.c`. Every `PrefetchBuffer` call site in `src/backend/` and `contrib/` was enumerated for the prefetch claim.
- PostgreSQL 12 free-space and diagnostic-extension sources: `src/backend/storage/freespace/indexfsm.c`, `contrib/pg_prewarm/pg_prewarm.c`, and `contrib/pageinspect/btreefuncs.c` with `contrib/pageinspect/pageinspect--1.5.sql`.
- Same-checkout docs and tests: `maintenance.sgml`, `ref/reindex.sgml`, `contrib/pgstattuple/sql/pgstattuple.sql`, `contrib/pgstattuple/expected/pgstattuple.out`, and `src/test/regress/sql/btree_index.sql`.
- Exact-pin execution: on 2026-09-07 every measurement on this page was re-run on one isolated PostgreSQL 12.2 server built out of tree from `45b88269a353ad93744772791feb6d01bc7e1e42`, with `pgstattuple` and `pageinspect` installed, covering the density, fragmentation, census, dead-space and survey-query fixtures. `raw/postgres-12/` was never written to. The server was stopped and its build, install and data trees removed afterwards, so nothing under `.wiki-runtime/` reproduces these numbers; every fixture is published on this page under [Reproduction](#reproduction) instead.

## Evidence Map

| Claim | Evidence |
|---|---|
| `avg_leaf_density` is computed from live-leaf free space over per-page available capacity | [pgstatindex.c#leaf-page-accounting](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L300), [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L351), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597) |
| `leaf_fragmentation` counts live leaf pages whose right link points backward in physical block order, and the docs define it no further | [pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307), [pgstatindex.c#leaf_fragmentation](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L352-L356), [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L55-L68), [pgstattuple.sgml#leaf_fragmentation-column](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L257-L261) |
| Reading either column costs a full physical index read under `BAS_BULKREAD`, is restricted to `relkind = 'i'` B-tree indexes, rejects other sessions' temporary relations, and is gated on `pg_stat_scan_tables` | [pgstatindex.c:222](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L222), [pgstatindex.c#full-block-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315), [pgstatindex.c#relkind-am-macros](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L70-L71), [pgstatindex.c#relation-checks](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L224-L238), [pgstattuple--1.4--1.5.sql#pgstatindex-grants](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92) |
| Default leaf fillfactor is 90 %, non-leaf 70 %, duplicates 96 %, and v12 can also apply the leaf fillfactor to a non-rightmost split after a new item | [nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171), [nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L275-L331) |
| Planner B-tree I/O costing uses physical index pages, tuple estimates, and page costs, never `leaf_fragmentation` | [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L971), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780), [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835), [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L786-L878) |
| A one-leaf probe still pays a tree-height descent charge so bloat is not free | [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L418) |
| B-tree scans position once, then walk the leaf chain one buffer per right-link step | [nbtsearch.c#_bt_first-position](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1244-L1321), [nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381), [nbtsearch.c#_bt_steppage-nextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1661-L1690), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1747-L1800) |
| Backward scans take the more complex `_bt_walk_left` path | [nbtsearch.c#_bt_readnextpage-backward](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1801-L1903), [nbtsearch.c#_bt_walk_left](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1930-L2053) |
| No v12 scan path prefetches an index page: all four backend `PrefetchBuffer` call sites name a heap relation's main fork, `effective_io_concurrency` is documented as bitmap-heap-only, and only the `pg_prewarm` contrib module can prefetch an index fork on demand | [bufmgr.c#PrefetchBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L521-L530), [nodeBitmapHeapscan.c#prefetch](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L501-L509), [nodeBitmapHeapscan.c#prefetch-second](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L550-L560), [vacuumlazy.c:2078](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L2078), [heapam.c:6956](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L6956), [pg_prewarm.c#prefetch-loop](../../../../raw/postgres-12/contrib/pg_prewarm/pg_prewarm.c#L159-L164), [config.sgml#effective_io_concurrency](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2166-L2181) |
| The 96 % duplicate fillfactor is applied by the `SPLIT_SINGLE_VALUE` strategy, not by the first-pass fillfactor choice | [nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171), [nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L275-L331), [nbtsplitloc.c#split-strategy-overrides](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L403-L422) |
| Pages VACUUM recycles become findable only after `btvacuumscan` calls `IndexFreeSpaceMapVacuum`, which it skips when nothing was recycled | [nbtree.c#btvacuumpage-recycle](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1166-L1173), [nbtree.c#btvacuumscan-fsm-vacuum](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1087-L1091), [indexfsm.c#GetFreeIndexPage](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L32-L46) |
| Measured: a warm full index-only scan of the 90 percent index is 2735 index blocks plus one visibility-map block, and the metapage is served from the relcache | [nbtpage.c#_bt_getroot-cache](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L267-L307), [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170), fixture A under [Exact-pin measurements](#exact-pin-measurements) |
| Measured: `leaf_fragmentation` is a lower bound on physical disorder, reading 49.84 on an index whose forward links were 100 % non-adjacent | [pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307), the census under [Reproduction](#reproduction) |
| Measured: a dead-entry heap fetch costs one buffer access per distinct heap block, not one per fetch, because `ReleaseAndReadBuffer` keeps the pinned buffer when the next TID is on the same page | [heapam_handler.c#heapam_index_fetch_tuple](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L117-L144), [bufmgr.c#ReleaseAndReadBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1510-L1553), [heapam.c#heap_delete-vm-clear](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L2704-L2710) |
| `EXPLAIN BUFFERS` reports node-level buffer counters, not relation-kind or physical-order counters | [explain.c#plan-buffer-usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L1864-L1866), [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2985), [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33) |
| Page splits allocate through `_bt_getbuf(P_NEW)`, which reuses an FSM page or extends the relation, and VACUUM feeds the FSM | [nbtinsert.c#_bt_insertonpg-split-test](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L963-L1002), [nbtinsert.c#_bt_split-new-right-page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L1403-L1439), [nbtpage.c#_bt_getbuf-fsm-reuse](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L801-L832), [nbtpage.c#_bt_getbuf-extend](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L844-L875), [nbtree.c#btvacuumpage-recycle](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1166-L1173) |
| `LP_DEAD` index tuples keep occupying leaf space until an insert on the page or a VACUUM removes them | [nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1785-L1799), [nbtinsert.c#_bt_findinsertloc-lp-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L752-L761), [nbtinsert.c#_bt_vacuum_one_page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L2243-L2288) |
| Half-dead pages stay linked to their siblings and are excluded from both metrics; deleted pages are unlinked but still occupy blocks | [pgstatindex.c#page-classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310), [nbtree.h#page-flag-macros](../../../../raw/postgres-12/src/include/access/nbtree.h#L189-L194), [nbtpage.c#_bt_mark_page_halfdead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1645-L1652), [nbtpage.c#_bt_unlink_halfdead_page-sidelinks](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1967-L1982), [README#page-deletion](../../../../raw/postgres-12/src/backend/access/nbtree/README#L214-L226) |
| Only completely empty B-tree pages are reclaimed; pages that keep a few keys stay allocated | [maintenance.sgml#routine-reindex-partly-empty](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L866-L874), [ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57) |
| Fresh B-tree indexes are usually better physically ordered than indexes updated many times | [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L882-L888) |
| v12 cost constants distinguish sequential from nonsequential page fetches, and both are session-scoped `PGC_USERSET` values | [config.sgml#seq_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4696-L4711), [config.sgml#random_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4713-L4770), [cost.h#default-costs](../../../../raw/postgres-12/src/include/optimizer/cost.h#L21-L30), [guc.c#seq_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3206-L3216), [guc.c#random_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3217-L3227), [indexam.sgml#index-cost-parameters](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L1281-L1290) |
| Existing tests do not compare density and fragmentation I/O levels | [pgstattuple.sql#pgstatindex-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L9-L113), [btree_index.sql#tall-fillfactor](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L110-L123), [btree_index.sql#page-recycling](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L144-L162) |

## Open Questions

- `leaf_fragmentation` does not encode jump distance, run length, or forward jumps, and the census puts a number on the gap: a 49.84 % fragmented index had zero right links to the next physical block and a mean jump of 1839 blocks, so two indexes with equal `leaf_fragmentation` can present very different request patterns to storage. The census closes the measurement gap for one index at a time, but v12 still ships no column that reports it ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L302-L307)).
- The order-cost and combined tables remain sensitivity models. The measurements in this page were taken on a warm cache, so they confirm the buffer-count claims but not any elapsed-time claim about cold, seek-sensitive storage; PostgreSQL 12 exposes no counter that would isolate that effect ([explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2985), [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33)).
- `EXPLAIN (ANALYZE, BUFFERS)` cannot separate index-relation buffers from heap-relation buffers inside a node, and an index-only scan never fully removes the heap: it pins the visibility map, so every plan total on this page includes exactly one heap-relation block. The per-relation cumulative counters do separate the two when one statement is isolated, which is how the index-side columns above were obtained, but that is a second measurement rather than something `EXPLAIN` reports ([explain.c#plan-buffer-usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L1864-L1866), [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170)).
- The breakeven point where fragmentation dominates density depends on cache residency, storage hardware, kernel and device read-ahead, tablespace cost settings, and concurrent buffer churn. PostgreSQL 12 derives no such point from `pgstatindex` output ([config.sgml#planner-cost-constants](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4669-L4770), [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835)).
- The half-dead page case is source-backed but not measured here, because producing a durable half-dead leaf page requires an interrupted or crashed VACUUM ([README#page-deletion](../../../../raw/postgres-12/src/backend/access/nbtree/README#L214-L226), [nbtpage.c#_bt_mark_page_halfdead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1645-L1652)).
- The fragmentation fixture is seed-dependent and the page count is the loose part. Across four seeds `leaf_pages` ranged from 3684 to 3762 and `avg_leaf_density` from 65.51 to 66.89, while `leaf_fragmentation` stayed inside 49.76 to 49.89. A rebuild that matches density therefore has to be re-derived per run, and the filed `fillfactor = 67` matches the `setseed(0.5)` row only.
- Two figures previously filed on this page and shared with the leaf-density question page were wrong for a traceable reason, and one of them is now explained in full. The page filed 2738 and 4121 warm buffers and called them index-only scan buffers. Re-running the fixture shows that the serial plan reads 2736 and 4119 while the default parallel plan reads exactly 2738 and 4121, so the filed numbers were parallel-plan totals under a serial label. The per-relation split locates the difference on the heap side: index blocks are 2735 and 4118 in both plans, and the parallel runs read three visibility-map blocks instead of one, one per participating process. The filed costs of 22647.09 and 28199.09 are narrowed but not pinned: both sit exactly 458.12 above the fully all-visible parallel totals of 22188.97 and 27740.97, and forging `pg_class.relallvisible = 3970` on both 4425-page heaps reproduces them to within 0.88, the same residual in both, which is what a heap that was not fully all-visible when the original numbers were taken would produce. No integer `relallvisible` closes the last 0.88, and the original fixture SQL was deleted before this review, so the residual is not attributable. See also [Open Questions](leaf-density-60-vs-90-query-impact.md#open-questions) on the leaf-density question page.

## Source References

- [pgstatindex.c#relkind-am-macros](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L70-L71)
- [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365)
- [pgstattuple--1.4--1.5.sql#pgstatindex-grants](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)
- [pgstattuple.sgml#pgstatindex-columns](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L189-L266)
- [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597)
- [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L55-L68)
- [nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171)
- [nbtree.h:181](../../../../raw/postgres-12/src/include/access/nbtree.h#L181)
- [nbtree.h#page-flag-macros](../../../../raw/postgres-12/src/include/access/nbtree.h#L189-L194)
- [nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L275-L331)
- [nbtsplitloc.c#split-strategy-overrides](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L403-L422)
- [nbtsearch.c#_bt_first](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L746-L1331)
- [nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1333-L1381)
- [nbtsearch.c#_bt_readpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1383-L1616)
- [nbtsearch.c#_bt_steppage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1618-L1724)
- [nbtsearch.c#_bt_readnextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1726-L1906)
- [nbtsearch.c#_bt_walk_left](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1930-L2053)
- [nbtsearch.c#_bt_endpoint](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L2136-L2229)
- [nbtinsert.c#_bt_findinsertloc-lp-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L752-L761)
- [nbtinsert.c#_bt_insertonpg](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L931-L1002)
- [nbtinsert.c#_bt_split-new-right-page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L1403-L1439)
- [nbtinsert.c#_bt_vacuum_one_page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L2243-L2288)
- [nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1785-L1799)
- [nbtpage.c#_bt_getbuf](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L747-L879)
- [nbtpage.c#_bt_getroot-cache](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L267-L307)
- [nbtpage.c#_bt_mark_page_halfdead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1645-L1652)
- [nbtpage.c#_bt_unlink_halfdead_page-sidelinks](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1967-L1982)
- [README#page-deletion](../../../../raw/postgres-12/src/backend/access/nbtree/README#L214-L226)
- [nbtree.c#btvacuumpage-recycle](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1166-L1173)
- [nbtree.c#btvacuumscan-fsm-vacuum](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1087-L1091)
- [indexfsm.c#GetFreeIndexPage](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L32-L46)
- [nbtree.c#btgetbitmap](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L286-L342)
- [indexam.c#index_getnext_tid](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L501-L545)
- [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L170)
- [execnodes.h#IndexOnlyScanState](../../../../raw/postgres-12/src/include/nodes/execnodes.h#L1470-L1479)
- [nodeIndexonlyscan.c#ExecIndexOnlyScanInitializeWorker](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L678-L684)
- [nodeBitmapHeapscan.c#prefetch](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L501-L509)
- [nodeBitmapHeapscan.c#prefetch-second](../../../../raw/postgres-12/src/backend/executor/nodeBitmapHeapscan.c#L550-L560)
- [bufmgr.c#PrefetchBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L521-L530)
- [bufmgr.c#ReleaseAndReadBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1510-L1553)
- [pg_prewarm.c#prefetch-loop](../../../../raw/postgres-12/contrib/pg_prewarm/pg_prewarm.c#L159-L164)
- [vacuumlazy.c:2078](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L2078)
- [heapam.c:6956](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L6956)
- [heapam.c#heap_delete-vm-clear](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L2704-L2710)
- [heapam_handler.c#heapam_index_fetch_tuple](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L117-L144)
- [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L418)
- [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L971)
- [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5780)
- [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5782-L5835)
- [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116)
- [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L786-L878)
- [cost.h#default-costs](../../../../raw/postgres-12/src/include/optimizer/cost.h#L21-L30)
- [guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2386)
- [guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2396)
- [guc.c#effective_io_concurrency](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2759-L2775)
- [guc.c#seq_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3206-L3216)
- [guc.c#random_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3217-L3227)
- [explain.c#plan-buffer-usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L1864-L1866)
- [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2985)
- [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33)
- [config.sgml#planner-cost-constants](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4669-L4770)
- [config.sgml#effective_io_concurrency](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L2166-L2181)
- [indexam.sgml#index-cost-parameters](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L1281-L1290)
- [queries.sgml#with-materialization](../../../../raw/postgres-12/doc/src/sgml/queries.sgml#L2221-L2236)
- [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L852-L888)
- [ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57)
- [pgstattuple.sql#pgstatindex-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L9-L113)
- [pgstattuple.out#empty-index-NaN](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L44-L52)
- [pgstattuple.out#partition-index-NaN](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L228-L236)
- [btree_index.sql#tall-fillfactor](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L110-L123)
- [btree_index.sql#page-recycling](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L144-L162)

## Navigation

- [v12/index](../../index.md)
- [Impact of B-Tree Leaf Density (60% vs 90%) on Index Scan Queries in PostgreSQL 12 (unverified)](leaf-density-60-vs-90-query-impact.md)
- [How pgstatindex Calculates B-Tree Index Statistics in PostgreSQL 12 (unverified)](how-pgstatindex-calculates-information.md)
- [Planner Penalties for Bloated Indexes in PostgreSQL 12 (unverified)](../query-planning/bloated-indexes-query-planner.md)
- [EXPLAIN ANALYZE BUFFERS Output in PostgreSQL 12 (unverified)](../observability/explain-analyze-buffers-output.md)
- [versions](../../../versions.md)
