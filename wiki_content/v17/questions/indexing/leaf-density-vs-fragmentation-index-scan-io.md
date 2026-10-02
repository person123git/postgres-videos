---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# B-Tree Leaf Density vs Fragmentation Impact on Index Scan I/O in PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
  - [Filing note](#filing-note)
- [Answer](#answer)
  - [What PostgreSQL 17 measures](#what-postgresql-17-measures)
  - [Where index scan reads come from](#where-index-scan-reads-come-from)
  - [Density impact estimates](#density-impact-estimates)
  - [Fragmentation impact estimates](#fragmentation-impact-estimates)
  - [Combined estimate matrix](#combined-estimate-matrix)
  - [Exact-pin measurements](#exact-pin-measurements)
  - [How fragmentation arises](#how-fragmentation-arises)
  - [What both metrics hide](#what-both-metrics-hide)
  - [Which one matters more](#which-one-matters-more)
  - [Settings and apply scope](#settings-and-apply-scope)
  - [Operational reading](#operational-reading)
  - [Tests and coverage](#tests-and-coverage)
- [Measurement Script](#measurement-script)
  - [Usage](#usage)
  - [Last run](#last-run)
  - [The script](#the-script)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 17, what has more impact on index scan I/O: B-tree leaf density or fragmentation? Provide a comprehensive comparison, analyze different levels of density and fragmentation, and estimate the impact on index scan I/O.

### Filing note

The asker's instruction, corrected silently at their choice: *Follow AGENTS.md. Target version: PostgreSQL 17.* It named thirteen items the answer must cover: a measured verdict table; what PostgreSQL 17 measures; where index scan reads come from; density estimates; fragmentation estimates; the combined matrix; exact-pin measurements; how fragmentation arises; what both metrics hide; which factor matters more per workload; settings with their apply scope from the PostgreSQL 17 GUC tables; an operational survey query; and tests. Each item has its own section under [Answer](#answer).

## Answer

Leaf density has the larger effect on the index scan I/O that PostgreSQL 17 can see, count and price. Density decides how many [leaf pages](../../../glossary.md#leaf-page) a scan visits and how many index pages the [planner](../../../glossary.md#planner) charges for ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L463-L501), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6737), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2191-L2243)). Fragmentation changes only the physical order of the same page visits. The planner never reads it: `genericcostestimate` charges `random_page_cost` for every index page it expects to touch, in whatever order ([selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6787)). The executor never compensates for it: no [B-tree](../../../glossary.md#b-tree) read path in 17 [prefetches](../../../glossary.md#prefetch) or [stream-reads](../../../glossary.md#read-stream) an index page, so every leaf is one synchronous single-block read through `_bt_getbuf` ([nbtpage.c#_bt_getbuf](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L844-L857), [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1248-L1263)). Disorder therefore costs nothing that PostgreSQL counts; its whole cost falls on the kernel and the storage device, where this page gives a model and no measurement.

Measured on an isolated server built from this page's pinned commit, over the same 1,000,000 `bigint` keys (details under [Exact-pin measurements](#exact-pin-measurements)):

| Index state | `leaf_pages` | `avg_leaf_density` | `leaf_fragmentation` | Warm plan buffers | of which index blocks |
|---|---:|---:|---:|---:|---:|
| Built with `fillfactor = 90` | 2,733 | 90.06 | 0 | 2,736 | 2,735 |
| Built with `fillfactor = 60` | 4,116 | 59.9 | 0 | 4,119 | 4,118 |
| Random-order retail inserts, `setseed(0.5)` | 3,701 | 66.58 | 49.45 | 3,704 | 3,703 |
| The same index rebuilt at `fillfactor = 67` | 3,677 | 67.02 | 0 | 3,680 | 3,679 |

- Dropping density from 90.06 to 59.9 raised buffer accesses by 50.5 %, from 2,736 to 4,119.
- Removing 49.45 % fragmentation at about the same density moved them by 0.65 %, from 3,704 to 3,680. That is exactly the 24 leaf pages the rebuild did not need.
- The buffer column is a plan total. Every row includes one heap-relation block, the [visibility-map](../../../glossary.md#visibility-map) page the [index-only scan](../../../glossary.md#index-only-scan) consults, and the last column removes it through the per-relation [cumulative statistics](../../../glossary.md#cumulative-statistics) counters ([nodeIndexonlyscan.c#IndexOnlyNext-visibility-check](../../../../raw/postgres-17/src/backend/executor/nodeIndexonlyscan.c#L161-L170), [visibilitymap.c#vm_readbuf](../../../../raw/postgres-17/src/backend/access/heap/visibilitymap.c#L616-L625)).
- `leaf_fragmentation` also understates physical disorder. On the random-order index it read 49.45 while 100 % of the forward [right links](../../../glossary.md#sibling-link) skipped the next block, by 1,845 blocks on average. On an index filled in descending key order it read 99.96 while 4,876 of 4,901 right links stepped back exactly one block.

The practical ranking follows from that. Density decides the page count for every workload that walks leaf pages. Fragmentation decides the elapsed time only when the pages are not cached and the storage charges much more for non-sequential reads than for sequential ones. The PostgreSQL 17 documentation says that random access to durable storage "is normally much more expensive than four times sequential access", but that fully cached data has "no penalty for touching pages out of sequence" ([config.sgml#random_page_cost-durable-storage](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5875-L5882), [config.sgml#random_page_cost-cached](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5896-L5907)). [Which one matters more](#which-one-matters-more) gives the ranking per workload.

### What PostgreSQL 17 measures

Both numbers come from [pgstatindex](../../../glossary.md#pgstatindex) in the [pgstattuple](../../../glossary.md#pgstattuple) [contrib](../../../glossary.md#contrib) module, and all of the arithmetic sits in `pgstatindex_impl()` ([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L215-L381)).

- **The scan.** It reads the [metapage](../../../glossary.md#metapage), block 0, first, then every block from 1 to `RelationGetNumberOfBlocks() - 1`, share-locking each page in turn. Both reads use a `BAS_BULKREAD` access strategy, the [ring buffer](../../../glossary.md#ring-buffer) for bulk reads ([pgstatindex.c:222](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L222), [pgstatindex.c#metapage-read](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L252-L265), [pgstatindex.c#full-block-scan](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L278-L331)). The cost of the report is therefore a full physical read of the index, and the documentation warns that the result is accumulated page by page rather than taken as a snapshot ([pgstattuple.sgml#pgstatindex-not-a-snapshot](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L275-L279)).
- **The page classes.** A page flagged deleted counts as `deleted_pages`. A half-dead page counts as `empty_pages`, because `P_IGNORE` covers both flags and the deleted test runs first. A live leaf counts as `leaf_pages`. Anything else counts as `internal_pages`, the root included ([pgstatindex.c#page-classification](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L326), [nbtree.h#page-flag-macros](../../../../raw/postgres-17/src/include/access/nbtree.h#L218-L228)). `index_size` is the number of counted pages plus one for the metapage, times the block size ([pgstatindex.c#index_size](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L357)).
- **`avg_leaf_density`.** For each live leaf page it adds `PageGetFreeSpace(page)` to `free_space` and the page's usable space, `pd_special - SizeOfPageHeaderData`, to `max_avail`. The result is `100 - free_space / max_avail * 100`, printed with two decimals, or `NaN` when no live leaf page contributed ([pgstatindex.c#leaf-page-accounting](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L308-L316), [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L367)). `PageGetFreeSpace` returns `pd_upper - pd_lower`, minus the four bytes of one new line pointer, and zero when the gap is smaller than a line pointer, so a full page reads slightly denser than its raw gap ([bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L898-L923)).
- **`leaf_fragmentation`.** It counts a live leaf page as a fragment when its right link `btpo_next` is not `P_NONE` and names a lower block number, and reports `fragments / leaf_pages * 100`, or `NaN` with no leaf pages ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323), [pgstatindex.c#leaf_fragmentation](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L368-L372), [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-17/src/include/access/nbtree.h#L62-L69), [nbtree.h:212](../../../../raw/postgres-17/src/include/access/nbtree.h#L212)). It is one bit per leaf page. It does not record jump distance, forward jumps, or the order a backward scan sees. The documentation defines the two columns only as "Average density of leaf pages" and "Leaf page fragmentation" ([pgstattuple.sgml#pgstatindex-density-fragmentation](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L251-L261)).
- **What it refuses.** It rejects any relation that is not a plain index (`relkind = 'i'`) of the B-tree access method, other sessions' temporary relations, and in 17 any index whose `indisvalid` is false ([pgstatindex.c#relkind-am-macros](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L70-L71), [pgstatindex.c#relation-checks](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L250)). The `indisvalid` check came from commit `13503eb590`, "Diagnose !indisvalid in more SQL functions", which is in this checkout's history before `Stamp 17.0.`

The fillfactors that set a fresh index's density are constants in `nbtree.h`: leaf pages default to 90 %, pages above the leaf level use a fixed 70 %, a page full of one duplicate value splits at an effective 96 %, and the leaf reloption accepts 10 to 100. The header comment says the leaf fillfactor applies at build time and on rightmost splits, and that other splits divide the data equally ([nbtree.h#fillfactor](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202), [nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1145)). The code follows it in two places:

- **Build.** `_bt_pagestate()` gives each level its own "full" threshold, `BLCKSZ * (100 - 70) / 100` above the leaves and `BTGetTargetPageFreeSpace()` on the leaves. `_bt_buildadd()` starts a new page once the free space would fall below that threshold ([nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L645-L671), [nbtsort.c#page-full-test](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L844-L855)). Eight builds of the same keys landed at 94.98, 90.06, 80.03, 69.95, 59.9, 49.85, 39.79 and 29.73 for fillfactors 95 to 30 ([Exact-pin measurements](#exact-pin-measurements)).
- **Splits.** `_bt_findsplitloc()` reads the leaf fillfactor from the index's options. It uses 70 % on a rightmost internal page and the leaf fillfactor on a rightmost leaf page. On any other leaf page it uses the leaf fillfactor only when `_bt_afternewitemoff()` detects an insert at the right end of a localized ascending group, and otherwise splits 50:50 ([nbtsplitloc.c:172](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L172), [nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L335)). Then `_bt_strategy()` classifies the page. `SPLIT_SINGLE_VALUE`, chosen when the page holds only one value and is the rightmost page for it, re-sorts the split points at `BTREE_SINGLEVAL_FILLFACTOR`. That is the function that applies the 96 % in 17. `SPLIT_MANY_DUPLICATES` only widens the split interval ([nbtsplitloc.c:364](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L364), [nbtsplitloc.c#split-strategy-overrides](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L397-L416), [nbtsplitloc.c#single-value-choice](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L1011-L1040)). [Deduplication](../../../glossary.md#deduplication) anticipates the same target: its single-value strategy lowers the maximum posting-list size in `_bt_singleval_fillfactor()` so the page is about 96 % full when it finally splits, and the code notes that its calculation "needs to match nbtsplitloc.c" ([nbtdedup.c#singleval-strategy-choice](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L104-L109), [nbtdedup.c#_bt_do_singleval](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L755-L802), [nbtdedup.c#_bt_singleval_fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L821-L842)).

The user documentation states the consequence for layout: leaf pages are filled to the fillfactor "during initial index builds, and also when extending the index at the right", and pages that later fill up "will be split, leading to fragmentation of the on-disk index structure" ([create_index.sgml#index-reloption-fillfactor](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L404-L411)).

### Where index scan reads come from

**The planner** prices index I/O from the whole [main fork](../../../glossary.md#fork) and never from its order.

- `get_relation_info()` fills [IndexOptInfo](../../../glossary.md#indexoptinfo). For an index without a predicate, `pages` is `RelationGetNumberOfBlocks()`, the live file size rather than `pg_class.relpages`, and `tuples` is the parent table's estimate. A partial index goes through `estimate_rel_size()`, whose index branch also starts from the live block count. For a B-tree, `tree_height` comes from `_bt_getrootheight()` ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L463-L501), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160)). That returns `btm_fastlevel` from the metapage copy cached in the [relcache](../../../glossary.md#relcache), and never refreshes a cached copy ([nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717)).
- `genericcostestimate()` estimates the pages a scan touches as `ceil(numIndexTuples * pages / tuples)` when both counts exceed one, and as one page otherwise. A single scan pays `spc_random_page_cost` for each of them. A repeated scan runs the total through the Mackert-Lohman cache model in `index_pages_fetched()`, which uses [effective_cache_size](../../../glossary.md#effective_cache_size). The CPU term is `numIndexTuples * (cpu_index_tuple_cost + qual_op_cost)` ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6737), [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6787), [selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810), [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L897-L951)). The page cost is the index [tablespace](../../../glossary.md#tablespace)'s `random_page_cost` when one is set, else the setting ([spccache.c#get_tablespace_page_costs](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L173-L205)).
- `btcostestimate()` adds a descent charge of `ceil(log2(tuples)) * cpu_operator_cost` plus `(tree_height + 1) * 50 * cpu_operator_cost`. The comment explains the second term: without it, "bloated indexes would appear to have the same search cost as unbloated ones" when one leaf page is expected ([selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145), [selfuncs.c#btcostestimate-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7106)).
- `cost_index()` adds the access method's whole index cost to the path. For an index-only scan it scales the heap page estimate by `1 - allvisfrac`, and `allvisfrac` is `relallvisible` over the heap's current pages ([costsize.c#cost_index-index-charge](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L617-L633), [costsize.c#cost_index-heap-pages](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L714-L747), [tableam.c#allvisfrac](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L749-L760)). For a [parallel](../../../glossary.md#parallel-query) path it divides only the per-tuple CPU run cost by the parallel divisor. The divisor is the worker count plus a leader share of `1 - 0.3 * workers`, added only when `parallel_leader_participation` is on and the share is positive ([costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L806-L815), [costsize.c#get_parallel_divisor](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L6375-L6405)). The index's page charge is therefore never divided. The worker count comes from the index pages the scan expects to touch ([costsize.c#cost_index-workers](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L779), [allpaths.c#compute_parallel_worker](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4203-L4279)).

For a full serial index-only `count(*)` over an all-visible heap, those rules reduce to a closed form: `pages * 4.0 + tuples * 0.005 + ceil(log2(tuples)) * 0.0025 + (tree_height + 1) * 0.125 + tuples * 0.01`, with the last term divided by 2.4 in a two-worker plan ([cost.h#default-costs](../../../../raw/postgres-17/src/include/optimizer/cost.h#L21-L30)). The measured node costs match it on all four indexes of the verdict table, serial and parallel. For the fillfactor-90 build it gives 25,980.425 against the 25,980.42 that `EXPLAIN` printed.

**The executor** reads one leaf page per step of the leaf chain.

- `_bt_first()` preprocesses the scan keys. Without a usable boundary key it calls `_bt_endpoint()`, which descends from the root along the first or last downlink to the leftmost or rightmost leaf. Otherwise it descends with `_bt_search()`, positions with `_bt_binsrch()` and loads the first page with `_bt_readpage()` ([nbtsearch.c#_bt_first-endpoint](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1149-L1167), [nbtsearch.c#_bt_get_endpoint](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2491-L2561), [nbtsearch.c#_bt_endpoint](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2572-L2664), [nbtsearch.c#_bt_first-descend-and-read](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1387-L1469)). The root comes from the cached metapage copy, so a warm session reads the root block but not the metapage ([nbtpage.c#_bt_getroot-cached-metapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L356-L400)).
- `_bt_readpage()` records the page's block and its right link as `currPage` and `nextPage`, skips items marked `LP_DEAD` when the scan ignores killed tuples, and checks the high key so that it can stop without visiting the next page ([nbtsearch.c#_bt_readpage-currpage-nextpage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1612-L1631), [nbtsearch.c#_bt_readpage-skip-killed-forward](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1717-L1725), [nbtsearch.c#_bt_readpage-high-key](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1788-L1811)).
- `_bt_next()` returns saved items until the page runs out, then calls `_bt_steppage()`. That applies any pending `LP_DEAD` marks through `_bt_killitems()` and chooses the next block: the saved `nextPage` going forward, or the current page going backward ([nbtsearch.c#_bt_next](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1495-L1529), [nbtsearch.c#_bt_steppage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2040-L2168)).
- `_bt_readnextpage()` going forward reads that block with `_bt_getbuf()`, skips a deleted or half-dead page by following its own right link, and otherwise hands the page to `_bt_readpage()` ([nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2191-L2243)). Going backward, it must first lock the current page again, or read it again if its [pin](../../../glossary.md#buffer-pin) was dropped, and only then can `_bt_walk_left()` read the left sibling and check that the sibling's right link still points back ([nbtsearch.c#_bt_readnextpage-backward](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2244-L2335), [nbtsearch.c#_bt_walk_left](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2377-L2481)).
- Whether the pin survives depends on the scan type. `_bt_drop_lock_and_maybe_pin()` drops it for an MVCC [index scan](../../../glossary.md#index-scan) on a WAL-logged index, but never for an index-only scan, which "can never drop" its pin ([nbtsearch.c#_bt_drop_lock_and_maybe_pin](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L51-L72), [README#concurrent-tid-recycling](../../../../raw/postgres-17/src/backend/access/nbtree/README#L443-L470)). The source comment concedes the cost of re-pinning a page on the way left ([nbtsearch.c#_bt_readnextpage-backward-comment](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2256-L2268)). Measured on the fillfactor-90 index, a backward plain index scan read 5,468 index buffers against 2,735 forward, while index-only scans read 2,735 in both directions.
- A [bitmap](../../../glossary.md#bitmap-scan) index scan runs the same forward walk: `btgetbitmap()` loops over `_bt_first()` and `_bt_next()` and adds each TID to the bitmap ([nbtree.c#btgetbitmap](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L262-L306)). A parallel scan shares one leaf chain: each participant takes the next page from shared state in `_bt_parallel_seize()` and publishes the following one in `_bt_parallel_release()` ([nbtree.c#_bt_parallel_seize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L582-L612), [nbtree.c#_bt_parallel_release](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L701-L726)).
- An index-only scan tests `VM_ALL_VISIBLE` for every TID with a visibility-map buffer it keeps pinned, and counts every failed test as a heap fetch, which is what `EXPLAIN` prints as `Heap Fetches` ([nodeIndexonlyscan.c#IndexOnlyNext-visibility-check](../../../../raw/postgres-17/src/backend/executor/nodeIndexonlyscan.c#L161-L170), [visibilitymap.c#visibilitymap_get_status-reuse](../../../../raw/postgres-17/src/backend/access/heap/visibilitymap.c#L366-L395), [explain.c#heap-fetches](../../../../raw/postgres-17/src/backend/commands/explain.c#L1993-L1994)). The buffer lives in each process's own scan state and starts empty in every process, so a parallel plan pins the map page once per participant ([execnodes.h#IndexOnlyScanState](../../../../raw/postgres-17/src/include/nodes/execnodes.h#L1699-L1718), [nodeIndexonlyscan.c:104](../../../../raw/postgres-17/src/backend/executor/nodeIndexonlyscan.c#L104), [nodeIndexonlyscan.c:750](../../../../raw/postgres-17/src/backend/executor/nodeIndexonlyscan.c#L750)).

**Prefetch and read streams.** No path that reads B-tree pages during a scan prefetches or stream-reads them in 17. `_bt_getbuf()` calls `ReadBuffer()`, and `ReadBuffer_common()` starts a single-block read without the advice flag, so no `smgrprefetch()` call is issued ([nbtpage.c#_bt_getbuf](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L844-L857), [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1248-L1263), [bufmgr.c#StartReadBuffersImpl-advice](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1326-L1343)). A search of `src/` and `contrib/` finds every caller:

| Call site | Who calls it | Fork | Can it touch an index page? |
|---|---|---|---|
| `PrefetchBuffer` in `BitmapPrefetch()`, twice ([nodeBitmapHeapscan.c:500](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L500), [nodeBitmapHeapscan.c:551](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L551)) | bitmap heap scan, serial and parallel | heap `MAIN_FORKNUM` | no: heap pages after the bitmap is built |
| `PrefetchBuffer` in `index_delete_prefetch_buffer()` ([heapam.c:8416](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8416)) | `heap_index_delete_tuples()`, called by B-tree simple and bottom-up deletion | heap `MAIN_FORKNUM` | no: the heap blocks behind the index entries |
| `PrefetchBuffer` in `count_nondeletable_pages()` ([vacuumlazy.c:2758](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2758)) | VACUUM's heap truncation | heap `MAIN_FORKNUM` | no |
| `PrefetchSharedBuffer` in `XLogPrefetcherNextBlock()` ([xlogprefetcher.c:769](../../../../raw/postgres-17/src/backend/access/transam/xlogprefetcher.c#L769)) | WAL replay, under `recovery_prefetch` | whatever fork each WAL block reference names | yes, but only while replaying WAL |
| `PrefetchBuffer` in `pg_prewarm()` `prefetch` mode ([pg_prewarm.c:227](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L227)) | contrib `pg_prewarm`, on request | the caller's fork of the caller's relation ([pg_prewarm.c:127](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L127), [pg_prewarm.c:146](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L146)) | yes, on request only |
| `read_stream_begin_relation` in `heap_beginscan()` ([heapam.c:1252](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1252)) | sequential and TID-range scans | heap `MAIN_FORKNUM` ([heapam.c#heap_beginscan-read-stream](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1242-L1259)) | no |
| `read_stream_begin_relation` in `acquire_sample_rows()` ([analyze.c:1199](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1199)) | ANALYZE's block sample | heap `MAIN_FORKNUM` ([analyze.c#acquire_sample_rows-read-stream](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1199-L1205)) | no |
| `read_stream_begin_relation` in `pg_prewarm()` `buffer` mode ([pg_prewarm.c:263](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L263)) | contrib `pg_prewarm`, on request | the caller's fork ([pg_prewarm.c#buffer-mode](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L250-L282)) | yes, on request only |

The remaining calls are the machinery beneath them: `PrefetchBuffer()` dispatching to the local or shared implementation, and read streams issuing their advice from `StartReadBuffersImpl()` ([bufmgr.c#PrefetchBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L644-L666), [bufmgr.c#PrefetchSharedBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L551-L558), [localbuf.c:96](../../../../raw/postgres-17/src/backend/storage/buffer/localbuf.c#L96)). Only recovery and a manual `pg_prewarm` call can therefore bring index blocks in ahead of need, and neither happens during a scan. Nothing inside the server overlaps a leaf-chain jump with the next read, so the whole cost of disorder is left to the kernel and the device. On the host that produced this page's numbers, macOS has no `posix_fadvise`, so `USE_PREFETCH` is not defined and both I/O-concurrency settings are 0 and cannot be raised ([pg_config_manual.h#USE_PREFETCH](../../../../raw/postgres-17/src/include/pg_config_manual.h#L150-L163), [bufmgr.h#io-concurrency-defaults](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L157-L164), [variable.c#check_io_concurrency](../../../../raw/postgres-17/src/backend/commands/variable.c#L1222-L1246)). That changes no measured number here, because B-tree scans do not prefetch on any platform.

**What the counters can see.** [EXPLAIN BUFFERS](../../../glossary.md#explain-buffers) prints a node's shared hits, reads, dirtied and written blocks from its `BufferUsage`, with no split by relation, by fork, or by sequential against non-sequential access ([instrument.h#BufferUsage](../../../../raw/postgres-17/src/include/executor/instrument.h#L24-L42), [explain.c#show_buffer_usage](../../../../raw/postgres-17/src/backend/commands/explain.c#L3742-L3817)). The per-relation counters do split by relation. `PinBufferForBlock()` counts every pin as a block fetched, and every hit also as a block hit, against the relation it was read for. A visibility-map read is made through the heap relation, so it lands on the heap's counters. The statistics views report reads as fetched minus hit ([bufmgr.c#PinBufferForBlock-counting](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1161-L1171), [pgstat.h#buffer-counting-macros](../../../../raw/postgres-17/src/include/pgstat.h#L635-L644), [system_views.sql#pg_statio_all_tables](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L746-L778), [system_views.sql#pg_statio_all_indexes](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L817-L831)). A buffer counts as dirtied only when it goes from clean to dirty ([bufmgr.c#MarkBufferDirty-accounting](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2587-L2596), [bufmgr.c#MarkBufferDirtyHint-accounting](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L5147-L5150)). None of these counters records physical order.

### Density impact estimates

These estimates hold the live index tuple count, the tuple width and the visibility state constant, and assume a scan wide enough that walking leaf pages dominates the one-time descent. For that case the leaf-page multiplier from density is:

```text
leaf_page_multiplier = baseline_density / observed_density
```

The model column uses a 90 % baseline. The measured columns come from eight fresh builds of the same 1,000,000 keys, one per fillfactor, each measured with a warm serial index-only `count(*)`, relative to the fillfactor-90 build ([Exact-pin measurements](#exact-pin-measurements)):

| Fillfactor | Model multiplier `90 / d` | Extra leaf visits (model) | Measured density | Predicted `90.06 / density` | Measured leaf multiplier | Measured index blocks read | PostgreSQL-visible effect |
|---:|---:|---:|---:|---:|---:|---:|---|
| 95 | 0.95x | -5.3 % | 94.98 | 0.9482 | 0.9480 | 2,593 | fewer leaf pages than the default build |
| 90 | 1.00x | baseline | 90.06 | 1.0000 | 1.0000 | 2,735 | the default fresh build |
| 80 | 1.13x | 12.5 % | 80.03 | 1.1253 | 1.1259 | 3,079 | small but visible on wide scans |
| 70 | 1.29x | 28.6 % | 69.95 | 1.2875 | 1.2887 | 3,524 | enough to move range-scan buffer counts |
| 60 | 1.50x | 50.0 % | 59.9 | 1.5035 | 1.5060 | 4,118 | half again as many leaf visits |
| 50 | 1.80x | 80.0 % | 49.85 | 1.8066 | 1.8116 | 4,953 | bloat-sized; the plan cost rises with it |
| 40 | 2.25x | 125.0 % | 39.79 | 2.2634 | 2.2730 | 6,214 | more than doubles leaf work |
| 30 | 3.00x | 200.0 % | 29.73 | 3.0293 | 3.0494 | 8,336 | index-side pages dominate a wide scan |

The model holds to within 0.7 % at every level. The small excess at low density comes from each leaf's fixed overhead: every leaf page carries a high key and a page header whatever it holds, and more pages mean more of them. The planner follows the same page count. Every full-scan node cost in the ladder differs from the fillfactor-90 cost by the difference in `pg_class.relpages` times `random_page_cost`, as the closed form above predicts: 30 % costs 48,464.43 against 25,980.42, a gap of 22,484.01, and the files differ by 5,621 blocks.

Six caveats on the mapping from density to I/O:

- **Whole-fork pages.** `IndexOptInfo.pages` counts every block of the main fork ([plancat.c#index-pages-from-file-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L477)). A full scan reads only the leaves plus one root-to-leaf path. The fillfactor-90 file has 2,745 blocks and the scan read 2,735 of them.
- **The metapage.** A warm session serves it from the relcache, so the scan does not read it ([nbtpage.c#_bt_getroot-cached-metapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L356-L400)). The planner still prices it, as one of the whole-fork pages.
- **Internal pages.** They fill to a fixed 70 % whatever the leaf fillfactor. As leaf density fell from 90.06 to 29.73 the internal pages grew from 11 to 31, but the tree stayed at level 2, so every descent still read two pages above the leaf.
- **Half-dead pages.** `pgstatindex` counts them in `empty_pages`, not in `leaf_pages`, so they enter neither metric. They stay linked into the leaf chain, and a scan reads them and steps past them ([pgstatindex.c#page-classification](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L326), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2191-L2243)). This page did not produce one; see [Open Questions](#open-questions).
- **Deleted pages.** They are unlinked, so a scan never reads them, but they keep their blocks, so the planner keeps pricing them. Measured below, a 551-block index with 271 deleted pages was scanned by reading 278 blocks and was still priced at 551 pages ([nbtpage.c#_bt_unlink_halfdead_page-sibling-links](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2597-L2612)).
- **Point lookups.** A one-leaf probe reads the same number of pages at any density. Density reaches it only through the tree height, which the descent charge prices at `50 * cpu_operator_cost` a level ([selfuncs.c#btcostestimate-height-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)). Every point lookup measured here, at any density and any order, read three index blocks and one visibility-map block.

### Fragmentation impact estimates

These estimates hold density and the logical key range constant. Under those assumptions fragmentation adds no page. It changes the physical order of the blocks a scan reads while it follows the leaf chain.

```text
L = leaf pages visited by the scan
N = share of right-link steps that do not go to the next physical block
S = cost of a sequential page fetch
R = cost of a non-sequential page fetch
```

The input is `N`, not `leaf_fragmentation`, and the difference between them is the most important caveat on this page. `leaf_fragmentation` counts a leaf only when its right link points backward, at a lower block ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323)). A right link that jumps a thousand blocks forward costs a seek and counts as ordered. Every backward link is non-adjacent, so `leaf_fragmentation / 100` is at most `N`, apart from the one-page difference between the two denominators. The measured gap is large:

- the random-order index read 49.45 while `N` was 100 %, because not one of its 3,700 forward links pointed at the next block;
- the fresh builds read 0 while `N` was 0.36 % to 0.37 %, because the build interleaves internal pages with the leaves ([nbtsort.c#page-number-allocation](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L650-L654));
- the descending-order index read 99.96 with `N` at 100 %, yet 4,876 of its right links pointed exactly one block back.

`N` measures only forward scans. A backward scan follows left links, and the descending-order index shows the asymmetry: 4,876 of its left links point at the next block up, so its backward scan reads the file in ascending order. Use `leaf_fragmentation` to detect disorder, and the `pageinspect` census in the script, which reports `N`, jump distance and both directions, to size it.

A storage-order sensitivity model is:

```text
order_cost_multiplier = 1 + N * (R / S - 1)
```

This is not PostgreSQL 17 planner output. It borrows the distinction the cost constants draw between a page fetched in a sequential series, `seq_page_cost`, default 1.0, and a non-sequentially fetched page, `random_page_cost`, default 4.0 ([config.sgml#seq_page_cost](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5841-L5847), [config.sgml#random_page_cost](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5858-L5864), [cost.h#default-costs](../../../../raw/postgres-17/src/include/optimizer/cost.h#L21-L30)). The planner itself charges `random_page_cost` for every index page, ordered or not ([selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6787)). The model also treats every non-adjacent step as a full non-sequential fetch, which overstates short jumps that the kernel's read-ahead may still cover.

| `N` | Non-adjacent steps in an `L`-page scan | Multiplier at `R / S = 1` | at `R / S = 1.2` | at `R / S = 4` | Smallest `leaf_fragmentation` that can accompany it | Largest | PostgreSQL buffer counters |
|---:|---:|---:|---:|---:|---:|---:|---|
| 0 % | 0 | 1.00x | 1.00x | 1.00x | 0 | 0 | the page count density predicts, in file order |
| 10 % | `0.10 * (L - 1)` | 1.00x | 1.02x | 1.30x | 0 | about 10 | same pages, some order breaks |
| 25 % | `0.25 * (L - 1)` | 1.00x | 1.05x | 1.75x | 0 | about 25 | same pages |
| 50 % | `0.50 * (L - 1)` | 1.00x | 1.10x | 2.50x | 0 | about 50 | same pages |
| 75 % | `0.75 * (L - 1)` | 1.00x | 1.15x | 3.25x | 0 | about 75 | same pages |
| 100 % | `1.00 * (L - 1)` | 1.00x | 1.20x | 4.00x | 0 | about 100 | same pages; the random-order and descending-order fixtures sit here, at 49.45 and 99.96 |

The smallest possible `leaf_fragmentation` is 0 on every row, because a chain of forward-only jumps can be arbitrarily disordered, and the fresh builds show the effect on a small scale. The largest is about `N`, reached when every non-adjacent step points backward.

**The cached reading.** The PostgreSQL 17 documentation says that setting `random_page_cost` equal to `seq_page_cost` "makes sense if the database is entirely cached in RAM, since in that case there is no penalty for touching pages out of sequence" ([config.sgml#random_page_cost-cached](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5896-L5907)). At `R / S = 1` the order multiplier is 1.00 at every `N`, so density alone decides PostgreSQL-visible work. The warm-cache measurements on this page are that case: removing 100 % non-adjacency changed buffer accesses only by the page-count difference.

**The SSD reading.** The documentation at this pin gives no SSD value. The example "solid-state drives, might also be better modeled with a lower value for random_page_cost, e.g., 1.1" was removed from the 17 branch by commit `3f0b994cf3`, "doc: rewrite random_page_cost description", dated 2025-10-30, which this checkout's history first reaches at `Stamp 17.7.` The 17.11 text says instead that storage with a higher random read cost, "like magnetic disks", might use a higher value, and that data likely to be completely cached, or high network latency, might justify a lower one ([config.sgml#random_page_cost-guidance](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5884-L5894)). The `R / S = 1.2` column is kept as the asker's low-penalty sensitivity value, not as a documented figure. At that ratio even complete non-adjacency is a 1.20x order penalty, smaller than the 1.50x density penalty of 60 % against 90 %.

### Combined estimate matrix

For a large, cold, forward range scan the two effects multiply:

```text
combined_multiplier = (0.90 / density) * (1 + N * (R / S - 1))
```

Here `density` and `N` are fractions, such as 0.60 and 0.50. The first factor estimates the extra leaf pages, which PostgreSQL 17 counts and prices through the physical page count. The second estimates the order penalty, which PostgreSQL 17 neither counts nor prices ([plancat.c#index-pages-from-file-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L477), [selfuncs.c#numIndexPages-prorata](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732)).

At `R / S = 4`:

| Density | `N` = 0 % | 25 % | 50 % | 75 % | 100 % |
|---:|---:|---:|---:|---:|---:|
| 90 % | 1.00x | 1.75x | 2.50x | 3.25x | 4.00x |
| 80 % | 1.13x | 1.97x | 2.81x | 3.66x | 4.50x |
| 70 % | 1.29x | 2.25x | 3.21x | 4.18x | 5.14x |
| 60 % | 1.50x | 2.63x | 3.75x | 4.88x | 6.00x |
| 50 % | 1.80x | 3.15x | 4.50x | 5.85x | 7.20x |
| 40 % | 2.25x | 3.94x | 5.63x | 7.31x | 9.00x |

At `R / S = 1.2`:

| Density | `N` = 0 % | 25 % | 50 % | 75 % | 100 % |
|---:|---:|---:|---:|---:|---:|
| 90 % | 1.00x | 1.05x | 1.10x | 1.15x | 1.20x |
| 80 % | 1.13x | 1.18x | 1.24x | 1.29x | 1.35x |
| 70 % | 1.29x | 1.35x | 1.41x | 1.48x | 1.54x |
| 60 % | 1.50x | 1.58x | 1.65x | 1.73x | 1.80x |
| 50 % | 1.80x | 1.89x | 1.98x | 2.07x | 2.16x |
| 40 % | 2.25x | 2.36x | 2.48x | 2.59x | 2.70x |

The measured random-order index sits at a density of 0.6658 and `N` of 1.00. Against a fresh fillfactor-90 build the model predicts 5.41x at `R / S = 4`, 1.62x at 1.2, and 1.35x at 1.0. PostgreSQL's own counters showed only the 1.35x page term: 3,704 warm buffers against 2,736. The rest is a storage-path prediction that this page did not measure. Across the matrix, density moves the result by up to 2.25x at 40 %, while order moves it by up to 4x at `R / S = 4` and by 1.2x at 1.2. For cold device time, the answer therefore turns on the storage's `R / S` more than on either metric.

These tables estimate index-side leaf I/O only. They leave out heap reads, visibility-map effects, the CPU cost of evaluating scan keys, kernel read-ahead, controller caches, concurrent buffer eviction, and the pin behaviour that makes backward plain index scans read each leaf twice.

### Exact-pin measurements

Every number in this section comes from one run of the script under [Measurement Script](#measurement-script). The run used an isolated PostgreSQL 17.11 server built out of tree from this page's `pinned_commit`, with `shared_buffers = 512MB`, `autovacuum = off`, `synchronous_commit = on` and every other setting at its default, and with `pgstattuple`, `pageinspect`, `pg_visibility` and `pg_freespacemap` installed. The 1,000,000-row fixtures index the keys 1 to 1,000,000 as `bigint`; the dead-space and recycling fixtures use 200,000.

Three rules govern every measurement.

- **Warm, and one execution for both views.** Each measured query runs once to warm the cache and the session's metapage copy. The session then flushes its pending statistics, resets the table's and the index's counters, runs the query once more under `EXPLAIN (ANALYZE, BUFFERS)`, flushes again, and reads the two relations' counters ([pgstatfuncs.c#pg_stat_force_next_flush](../../../../raw/postgres-17/src/backend/utils/adt/pgstatfuncs.c#L1688-L1695), [pgstatfuncs.c#pg_stat_reset_single_table_counters](../../../../raw/postgres-17/src/backend/utils/adt/pgstatfuncs.c#L1761-L1770), [pgstat.c#pgstat_report_stat-force](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L583-L600)). `EXPLAIN` and the counters therefore describe the same execution. Every measured execution read 0 blocks from outside shared buffers, and the script fails if one does, so buffer counts here are accesses, not device reads.
- **A visibility gate.** An index-only scan over a heap page that is not all-visible becomes an index scan plus a heap fetch. Before each scan the script requires `pg_class.relpages`, `pg_class.relallvisible`, the file's block count, and the all-visible count from `pg_visibility_map_summary()` to agree. The dead-space and `synchronous_commit` fixtures are the deliberate exceptions, because their visibility is what they measure.
- **Plan shape asserted.** Each measurement names the node, index, direction and worker count it expects, and the script fails on any other plan.

The dead-space fixture measures states in which churn has not yet been vacuumed. The wiki's [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md) protocol forbids such states for fixtures that score a bloat estimator; this page scores no estimator, and the fixture exists to show what the metrics report before maintenance.

#### The density pair

| Measurement | `fillfactor = 90` | `fillfactor = 60` | Ratio or gap |
|---|---:|---:|---:|
| `avg_leaf_density` | 90.06 | 59.9 | 0.665 |
| `leaf_fragmentation` | 0 | 0 | |
| `leaf_pages` | 2,733 | 4,116 | 1.506 |
| `internal_pages` | 11 | 16 | |
| `tree_level` | 2 | 2 | |
| `pg_class.relpages` | 2,745 | 4,133 | 1.506 |
| Warm plan buffers, serial | 2,736 | 4,119 | 1.505 |
| of which index blocks | 2,735 | 4,118 | 1.506 |
| of which visibility-map blocks | 1 | 1 | |
| `Index Only Scan` node cost, serial | 25,980.42 | 31,532.42 | +5,552.00 |
| `Aggregate` total, serial | 28,480.43 | 34,032.44 | +5,552.01 |
| Warm plan buffers, default parallel plan, 2 workers launched | 2,738 | 4,121 | 1.505 |
| of which index blocks | 2,735 | 4,118 | |
| of which visibility-map blocks | 3 | 3 | |
| `Parallel Index Only Scan` node cost | 20,147.09 | 25,699.09 | +5,552.00 |
| `Finalize Aggregate` total | 22,188.98 | 27,740.98 | +5,552.00 |

- The predicted multiplier, 90.06 / 59.9 = 1.5035, matched the measured leaf-page ratio, 1.5060, and the index-block ratio, 1.5057.
- **The whole cost gap is index pages.** The two files differ by 1,388 blocks, and 1,388 times the default `random_page_cost` of 4.0 is 5,552.00. That is the gap between the serial nodes, between the parallel nodes, and between both plan totals, the serial total's 5,552.01 being a rounding of two printed values. In `random_page_cost` units the gap is exactly the difference in `relpages`. The tree height was equal, so the descent charge was identical.
- **Why the gap survives parallelism unchanged.** For the same index, the serial node costs 25,980.42 and the parallel node 20,147.09. The difference, 5,833.33, is 1,000,000 times `cpu_tuple_cost` times `1 - 1 / 2.4`: only the per-tuple CPU run cost is divided among the participants, while the index's page and per-entry costs are charged in full ([costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L806-L815)).
- The 2,735 index blocks are the root, one internal page, and 2,733 leaves. The parallel plan read the same 2,735 index blocks, and two more visibility-map blocks, one per extra participant.

#### Scan shape and direction

The density pair's heap was loaded in key order, so a plain index scan reads each heap page once. `heapam_index_fetch_tuple()` keeps the pinned heap buffer while the next TID is on the same page, and `ReleaseAndReadBuffer()` then returns it without a new access ([heapam_handler.c#heapam_index_fetch_tuple](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L125-L140), [bufmgr.c#ReleaseAndReadBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2612-L2645)).

| Scan, warm | ff 90: plan buffers | index blocks | heap blocks | ff 60: plan buffers | index blocks | heap blocks |
|---|---:|---:|---:|---:|---:|---:|
| Index-only, forward, `ORDER BY id OFFSET 999999` | 2,736 | 2,735 | 1 | 4,119 | 4,118 | 1 |
| Index-only, backward, `ORDER BY id DESC OFFSET 999999` | 2,736 | 2,735 | 1 | 4,119 | 4,118 | 1 |
| Plain index scan, forward | 7,160 | 2,735 | 4,425 | 8,543 | 4,118 | 4,425 |
| Plain index scan, backward | 9,893 | 5,468 | 4,425 | 12,659 | 8,234 | 4,425 |
| Point lookup, `id = 500000` | 4 | 3 | 1 | 4 | 3 | 1 |
| Range, 100,000 keys, `id BETWEEN 450001 AND 550000` | 277 | 276 | 1 | 416 | 415 | 1 |
| Bitmap index scan, `id IS NOT NULL` (index side) | | 2,735 | | | 4,118 | |

- **Backward plain index scans read every leaf twice**: 5,468 is exactly `2 * 2,733 + 2`, and 8,234 is `2 * 4,116 + 2`. The plain scan drops each leaf's pin after reading it, so stepping left must read the current page again to find its left link, and then read the left sibling ([nbtsearch.c#_bt_readnextpage-backward-repin](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2269-L2286)). The index-only scan keeps its pin and reads each leaf once in both directions. The planner costed both directions the same, 30,408.42 at fillfactor 90 and 35,960.43 at 60, so it does not see this.
- Density scales every walking shape by the same 1.5x, and leaves the point lookup untouched.
- The bitmap index scan's own node reported exactly the index-only scan's index blocks, as the shared forward walk implies.

#### The fragmentation pair

The random-order fixture creates its index before loading, then inserts the keys 1 to 1,000,000 in a `setseed(0.5)` random order, so every key is a retail insert. The rebuild sets the index's fillfactor to the rounded density the inserts left, 67, and runs `REINDEX INDEX` on the same index.

| Measurement | Random-order inserts | Rebuilt at `fillfactor = 67` |
|---|---:|---:|
| `leaf_pages` | 3,701 | 3,677 |
| `avg_leaf_density` | 66.58 | 67.02 |
| `leaf_fragmentation` | 49.45 | 0 |
| `internal_pages`, `tree_level` | 14, 2 | 14, 2 |
| `pg_class.relpages` | 3,716 | 3,692 |
| Warm index-only `count(*)`: plan buffers, index blocks | 3,704, 3,703 | 3,680, 3,679 |
| `Index Only Scan` node cost | 29,864.42 | 29,768.42 |
| Default parallel plan: plan buffers, index blocks | 3,706, 3,703 | 3,682, 3,679 |
| Backward index-only scan: plan buffers | 3,704 | 3,680 |
| Point lookup: plan buffers | 4 | 4 |
| Range of 100,000 keys: index blocks | 397 | 371 |
| Bitmap index scan: index blocks | 3,703 | 3,679 |

- Removing the fragmentation removed 24 buffer accesses out of 3,704. The rebuilt index has exactly 24 fewer leaf pages, and the plan-cost gap, 96.00, is 24 blocks of `relpages` times 4.0. The executor paid one buffer access per right-link step in both indexes, whatever the block numbers were.
- `leaf_fragmentation` reproduced as the share of leaves with a backward right link: 1,830 / 3,701 = 49.45 %.

The `pageinspect` sibling-link census over every live leaf page, from `bt_multi_page_stats()` ([btreefuncs.c#bt_multi_page_stats](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L336-L460), [btreefuncs.c#page-type](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L125-L170)):

| Index | Forward right links | Backward | To `blkno + 1` | Not to `blkno + 1` | `N` | Mean absolute jump | Max jump |
|---|---:|---:|---:|---:|---:|---:|---:|
| Random-order inserts | 3,700 | 1,830 | 0 | 3,700 | 100.00 % | 1,845.4 | 3,663 |
| Rebuilt at `fillfactor = 67` | 3,676 | 0 | 3,663 | 13 | 0.35 % | 1.0 | 3 |
| Built at `fillfactor = 90` | 2,732 | 0 | 2,722 | 10 | 0.37 % | 1.0 | 3 |
| Built at `fillfactor = 60` | 4,115 | 0 | 4,100 | 15 | 0.36 % | 1.0 | 3 |
| Descending-order inserts | 4,901 | 4,900 | 0 | 4,901 | 100.00 % | 2.0 | 4,926 |

- The rebuilt index is the mirror image of the fragmented one: 3,663 of 3,676 links go to the next block. Its 13 other links step over the interleaved internal pages.
- `N` is 100 % on both, but the mean jump separates the random-order index, 1,845 blocks, from the descending one. The descending index's 2.0 comes from 4,876 one-block steps backward, 24 longer backward steps, and one forward jump of 4,926 blocks, the leftmost leaf's link.

**Density is not uniform inside a fragmented index.** The same range scan over each tenth of the key space read between 335 and 409 index blocks on the random-order index, and between 370 and 374 on the rebuilt one:

| Keys | 1-100k | 100k-200k | 200k-300k | 300k-400k | 400k-500k | 500k-600k | 600k-700k | 700k-800k | 800k-900k | 900k-1M |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Random-order: index blocks | 409 | 404 | 337 | 349 | 384 | 399 | 386 | 390 | 343 | 335 |
| Rebuilt: index blocks | 373 | 371 | 370 | 371 | 371 | 370 | 371 | 371 | 370 | 374 |

A range scan pays the local density of its range, and the index-wide 66.58 hides a spread of about plus or minus 10 %. That is why the 450,001-550,000 range above cost 397 blocks against 371, a 7 % gap from an index only 0.65 % larger. Non-rightmost leaf splits divide a page 50:50 ([nbtsplitloc.c#other-leaf-pages-split-50-50](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L329-L335)), so each leaf's fill cycles between about half and full, and the pages covering different key ranges sit at different points of that cycle. This page measured the spread per tenth, not per page.

#### Descending order and the seed sweep

Inserting the same keys in descending order sends every insert to the leftmost leaf. That page is never rightmost, so each split divides it 50:50, the upper half moves to a block newly added at the end of the file, and the left half keeps receiving the next smaller keys.

| Measurement | Descending-order inserts |
|---|---:|
| `leaf_pages`, `avg_leaf_density` | 4,902, 50.34 |
| `leaf_fragmentation` | 99.96 |
| Right links to `blkno - 1`, of 4,901 | 4,876 |
| Left links to `blkno + 1`, of 4,901 | 4,876 |
| Warm index-only scan, forward and backward: plan buffers | 4,905 and 4,905 |

The metric reads nearly total fragmentation, the leaves sit in almost exact reverse key order in the file, and PostgreSQL counts the same 4,905 buffers in either direction. A forward scan presents the file to the kernel in descending order and a backward scan in ascending order. PostgreSQL cannot tell those apart.

The random-order recipe under four seeds:

| `setseed` | `leaf_pages` | `avg_leaf_density` | `leaf_fragmentation` | `N` | Mean absolute jump |
|---:|---:|---:|---:|---:|---:|
| 0.1 | 3,670 | 67.14 | 49.75 | 100.00 % | 1,835.1 |
| 0.25 | 3,742 | 65.86 | 49.39 | 100.00 % | 1,866.1 |
| 0.5 | 3,701 | 66.58 | 49.45 | 100.00 % | 1,845.4 |
| 0.9 | 3,851 | 64 | 49.78 | 100.00 % | 1,923.4 |

`leaf_fragmentation` stayed between 49.39 and 49.78 and `N` at 100 % under every seed, while the page count moved by 4.9 %, from 3,670 to 3,851. The fragmentation figure is stable; the page count, which decides I/O, is the seed-dependent part. The seed-0.5 row reproduced the fragmentation pair's index exactly, on a separately built table.

#### Dead space

A 200,000-row table lost 90 % of its rows to one `DELETE`, and was measured before the delete, on the first scan after it, in the steady state, and after `VACUUM`:

| State | Rows the scan returned | `leaf_pages` | `avg_leaf_density` | `LP_DEAD` items | Plan buffers | Index blocks | Heap blocks | `Heap Fetches` | Buffers dirtied |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Before the delete | 200,000 | 547 | 90 | 0 | 550 | 549 | 1 | 0 | 0 |
| After deleting 180,000 rows, before any scan | | 547 | 90 | 0 | | | | | |
| First scan | 20,000 | 547 | 90 | 180,000 after it | 1,435 | 549 | 886 | 200,000 | 547 |
| Steady state | 20,000 | 547 | 90 | 180,000 | 1,435 | 549 | 886 | 20,000 | 0 |
| After `VACUUM` | 20,000 | 547 | 9.26 | 0 | 550 | 549 | 1 | 0 | 0 |

- **The index looked fully dense with 90 % of its entries dead,** before and after the first scan had marked all 180,000 of them `LP_DEAD` on all 547 leaves. `_bt_killitems()` marks the line pointer in place and sets a page flag; it frees no space, so `PageGetFreeSpace()` and the density do not move ([nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4312-L4342)).
- After `VACUUM` the same 547 leaves held 20,000 entries at 9.26 %. No leaf became empty, so none was deleted. The documentation describes this pattern: pages that keep a few keys remain allocated, and "periodic reindexing is recommended" ([maintenance.sgml#routine-reindex-partly-empty](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1032-L1040)).
- **The extra 885 buffers are heap pages, not heap fetches.** The heap side went from 1 block to 886, the table's 885 pages plus the same visibility-map page. The heap is visited at all because `heap_delete()` clears each page's visibility-map bits ([heapam.c#heap_delete-clear-vm](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L3121-L3146)). The catalog did not notice: `pg_class.relallvisible` still read 885 while the live map read 0, because only `VACUUM`, `ANALYZE` and index builds rewrite that column ([vacuum.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1444-L1461), [index.c#index_update_stats-relallvisible](../../../../raw/postgres-17/src/backend/catalog/index.c#L2851-L2857)). The gate checks both for that reason.
- **`Heap Fetches` fell from 200,000 to 20,000 while buffers stayed at 1,435.** On the first scan each dead tuple sent `all_dead` back through `index_fetch_heap()`, `btgettuple()` remembered the item, and `_bt_steppage()` marked the page's items `LP_DEAD` before leaving it; later scans skip them ([indexam.c#index_fetch_heap-kill](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L644-L652), [nbtree.c#btgettuple-killed-items](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L226-L245), [nbtsearch.c#_bt_steppage-killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2049-L2051)). The 547 buffers the first scan dirtied are the 547 leaves that gained `LP_DEAD` marks; the heap pages had been dirtied by the `DELETE` already, and a buffer counts as dirtied only on its first change.
- The planner's cost for the scan did not move with the delete, 5,204.42, and fell to 2,504.41 only when `VACUUM` rewrote the tuple count. The page count it prices, 551, never changed.

#### Deleted and recycled pages

A second 200,000-row table lost the contiguous keys 50,001 to 150,000, so whole leaves emptied:

| State | `leaf_pages` | `deleted_pages` | `avg_leaf_density` | `relpages` | Free pages in the FSM | Index blocks a warm scan read | Scan node cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| Built | 547 | 0 | 90 | 551 | | | |
| After the delete and `VACUUM` | 276 | 271 | 89.18 | 551 | 0 | 278 | 3,704.42 |
| After one transaction ID and a second `VACUUM` | 276 | 271 | 89.18 | 551 | 271 | | |
| After a random-order refill of the same keys and `VACUUM` | 640 | 0 | 76.96 | 644 | 0 | 642 | 5,576.42 |

- **Deleted pages cost the planner and not the executor.** After the first `VACUUM` the scan read 278 blocks of a 551-block file, but the node cost still included 551 pages at 4.0 each. The density of the surviving leaves, 89.18, says nothing about the 271 empty blocks.
- **They became reusable only later.** The first `VACUUM` deleted them but put none in the [free space map](../../../glossary.md#free-space-map), because a deleted page may be recycled only once its stored transaction ID is behind the removal horizon ([nbtree.h#BTPageIsRecyclable](../../../../raw/postgres-17/src/include/access/nbtree.h#L279-L318), [nbtpage.c#_bt_pendingfsm_finalize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2995-L3055)). After one transaction took an ID, the second `VACUUM` recorded all 271.
- **Reuse scattered the leaf chain.** The refill's splits took all 271 recycled blocks and then extended the file by 93. The census went from 0 backward links to 180, `leaf_fragmentation` 28.12, with `N` at 57.59 % and a mean jump of 143.8 blocks. Nothing ties a recycled block to the key that needs it: `_bt_allocbuf()` takes no key, and takes whatever block `GetFreeIndexPage()` returns ([nbtpage.c:869](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L869), [nbtpage.c#_bt_allocbuf-fsm-reuse](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L877-L969), [indexfsm.c#GetFreeIndexPage](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L32-L46)).

#### Does `synchronous_commit = off` still block the visibility map in 17?

Yes, for as long as the commit record that the hint check consults is unflushed.

- `SetHintBits()` refuses to set a committed hint while `XLogNeedsFlush(commitLSN)` is true for the inserting transaction, unless the page's own LSN is already past it ([heapam_visibility.c#SetHintBits](../../../../raw/postgres-17/src/backend/access/heap/heapam_visibility.c#L82-L132)).
- VACUUM counts a live tuple toward an all-visible page only if its xmin-committed [hint bit](../../../glossary.md#hint-bits) is set, with a comment naming asynchronous commit as the reason ([pruneheap.c#heap_prune_record_unchanged_lp_normal-all-visible](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1363-L1387), [vacuumlazy.c#heap_page_is_all_visible-hint](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3011-L3021)).
- An [asynchronous commit](../../../glossary.md#asynchronous-commit) skips the flush, reports its LSN to the [WAL writer](../../../glossary.md#wal-writer), and stores that LSN in the commit log ([xact.c#RecordTransactionCommit-async](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L1487-L1521), [xlog.c#XLogSetAsyncXactLSN](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L2607-L2657)). The commit log keeps one LSN per group of 32 transaction IDs, raised by any later asynchronous commit in the group, so the lookup "might return the LSN of a later transaction that falls into the same group" ([clog.c#lsn-groups](../../../../raw/postgres-17/src/backend/access/transam/clog.c#L91-L96), [clog.c#group-lsn-update](../../../../raw/postgres-17/src/backend/access/transam/clog.c#L702-L716), [clog.c#TransactionIdGetStatus](../../../../raw/postgres-17/src/backend/access/transam/clog.c#L719-L758), [transam.c#TransactionIdGetCommitLSN](../../../../raw/postgres-17/src/backend/access/transam/transam.c#L376-L405)).

Measured, with the load committed at `synchronous_commit = off` in its session:

| Trial | `synchronous_commit` | Was the relevant commit record flushed when `VACUUM` started? | Heap pages | All-visible after `VACUUM`: `relallvisible`, live map | Warm index-only `count(*)` |
|---|---|---|---:|---:|---|
| P1: 1,000,000 rows loaded in transaction 1034, `CREATE INDEX` in transaction 1035, then `VACUUM (ANALYZE)` at once | off | The load's, yes: it ended by 0/561F9148 and the flush stood at 0/57000000. The index build's, no: it ended by 0/5755A120, and the flush was still at 0/5755A000 after `VACUUM` | 4,425 | 0, 0 | 7,161 buffers, 2,735 of them index and 4,426 heap; 1,000,000 heap fetches |
| P1 after `CHECKPOINT` and a second `VACUUM` | off | yes | 4,425 | 4,425, 4,425 | 2,736 buffers; 0 heap fetches |
| P2-1 to P2-5: 5,000 rows, then `VACUUM` at once | off | no, in 5 of 5 | 23 | 0, 0 in 5 of 5 | |
| P2 with `pg_sleep(1)` before `VACUUM` | off | yes | 23 | 23, 23 | |
| P2 with a synchronous commit | on | yes | 23 | 23, 23 | |

P1 shows the group effect. The load's own commit record was already on disk, but transactions 1034 and 1035 fall in the same group of 32, so the commit log answered the load's hint check with the index build's later LSN, which was not. P2 shows the plain case five times out of five: `VACUUM` ran before the load's own commit record was flushed. A one-second wait, five times `wal_writer_delay`, or a synchronous commit removed the effect.

The WAL writer flushes at least once every `wal_writer_delay`, 200 ms by default, or sooner once `wal_writer_flush_after` worth of WAL is waiting, and the source guarantees that an asynchronous commit reaches disk within at most three `wal_writer_delay` cycles ([xlog.c#XLogBackgroundFlush-async-bound](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L2949-L2958), [xlog.c#XLogBackgroundFlush-flush-rules](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L3033-L3059), [wal.sgml#async-commit-risk-window](../../../../raw/postgres-17/doc/src/sgml/wal.sgml#L438-L444), [guc_tables.c#wal_writer_delay](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2902-L2911), [guc_tables.c#wal_writer_flush_after](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2913-L2922)). A `VACUUM` that runs inside that window after a bulk load leaves the new pages out of the visibility map, and an index-only scan over them fetches every row from the heap. That is why every other fixture on this page runs with `synchronous_commit = on` and passes the visibility gate first.

### How fragmentation arises

A leaf becomes a fragment when a split gives it a right sibling at a lower block number, and splits happen only when in-place recovery fails.

1. **The split test.** `_bt_insertonpg()` splits the page when `PageGetFreeSpace(page) < itemsz` ([nbtinsert.c#_bt_insertonpg-split-test](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1203-L1221)).
2. **In-place recovery comes first.** When the target leaf cannot take the new tuple, `_bt_findinsertloc()` calls `_bt_delete_or_dedup_one_page()` ([nbtinsert.c#_bt_findinsertloc-delete-or-dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L899-L906)), which tries up to three things in order. It stops after the first when its caller asked for simple deletion only, or when a unique-index insert found no duplicate on the page ([nbtinsert.c#simpleonly-return](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2734-L2752)):
   - [simple index deletion](../../../glossary.md#simple-index-deletion) of every `LP_DEAD` item, now found by scanning the line pointers rather than by trusting the page's `BTP_HAS_GARBAGE` hint ([nbtinsert.c#_bt_delete_or_dedup_one_page-comment](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2655-L2681), [nbtinsert.c#simple-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2702-L2733));
   - [bottom-up index deletion](../../../glossary.md#bottom-up-index-deletion), when the executor says the key did not change or a unique index found duplicates ([nbtinsert.c#bottom-up-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2776));
   - deduplication, when it is enabled and the index is `allequalimage` ([nbtinsert.c#deduplication](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2778-L2781)).

   Both deletion passes check the heap through `heap_index_delete_tuples()`. On a platform with prefetch support it prefetches the heap blocks up to the `maintenance_io_concurrency` distance, capped for bottom-up deletion at its count of contiguous "favorable" heap blocks at the head of its processing order, which is at least one ([heapam.c#heap_index_delete_tuples-prefetch-distance](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8540-L8570), [heapam.c#bottomup_nblocksfavorable](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8881-L8890)). All three exist in this checkout; each one that frees enough space avoids a split and therefore a new sibling link.
3. **The split writes the links.** `_bt_split()` keeps the left half in the original block, takes the right page from `_bt_allocbuf()`, points the left page's `btpo_next` at it, and gives it the left page as `btpo_prev` and the old right link as `btpo_next` ([nbtinsert.c#_bt_split-allocate-right-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1707-L1724), [nbtinsert.c#_bt_split-sibling-links](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1726-L1746)). In 17 there is no `_bt_getbuf(P_NEW)`: `_bt_getbuf()` asserts a valid block number and only reads existing pages, and allocation is `_bt_allocbuf()`'s job ([nbtpage.c#_bt_getbuf](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L844-L857)).
4. **Where the new block comes from.** `_bt_allocbuf()` first asks the free space map through `GetFreeIndexPage()`, takes only a conditional lock on the candidate, and reuses it if it is new or `BTPageIsRecyclable()` agrees, logging a reuse record for hot standby. Only when the map has nothing usable does it extend the relation by one page with `ExtendBufferedRel()` ([nbtpage.c#_bt_allocbuf-fsm-reuse](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L877-L969), [nbtpage.c#_bt_allocbuf-extend](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L971-L987), [indexfsm.c#GetFreeIndexPage](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L32-L46)). Extension puts the new right page at the end of the file: its left sibling's link jumps forward, and its own right link points back to the old right sibling, which is what `leaf_fragmentation` counts. Only a split of the rightmost page leaves the new page with no right link. Reuse puts it at an old block, in either direction. The measurements show both: random-order inserts on a growing file produced 1,830 backward links in 3,700, and the refill that reused 271 recycled blocks took the census from 0 to 180 backward links.
5. **Where free pages come from.** A page is deleted only once it is completely empty, first by marking it half-dead and removing its downlink, then by unlinking it from its siblings and marking it deleted with a safe-to-recycle transaction ID ([README#page-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/README#L232-L259), [README#page-deletion-second-stage](../../../../raw/postgres-17/src/backend/access/nbtree/README#L279-L282), [nbtpage.c#_bt_mark_page_halfdead-flag](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2225-L2232), [nbtpage.c#_bt_unlink_halfdead_page-unlink-and-delete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2597-L2648), [nbtree.h#BTPageSetDeleted](../../../../raw/postgres-17/src/include/access/nbtree.h#L238-L257)). `btvacuumpage()` records an already recyclable deleted page with `RecordFreeIndexPage()`, `_bt_pendingfsm_finalize()` records the pages this `VACUUM` deleted if their transaction ID is already safe, and `btvacuumscan()` calls `IndexFreeSpaceMapVacuum()` only when it recorded at least one ([nbtree.c#btvacuumpage-recycle](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1165-L1171), [nbtpage.c#_bt_pendingfsm_finalize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2995-L3055), [nbtree.c#btvacuumscan-fsm-vacuum](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1048-L1059), [indexfsm.c#RecordFreeIndexPage-and-IndexFreeSpaceMapVacuum](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L48-L74)).

The manual summarizes the result: a freshly built B-tree "is slightly faster to access than one that has been updated many times because logically adjacent pages are usually also physically adjacent in a newly built index" ([maintenance.sgml#routine-reindex-adjacency](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1048-L1054)).

### What both metrics hide

- **Dead entries count as dense.** `LP_DEAD` marks free no space until an insert on the page or `VACUUM` removes the items ([nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4312-L4342), [nbtinsert.c#simple-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2702-L2733)). Measured: 90 % density over 180,000 dead entries out of 200,000.
- **Local density.** The average hides a spread of about plus or minus 10 % across key ranges on a randomly filled index, and a range scan pays its range's local density.
- **Half-dead pages.** They land in `empty_pages`, out of both metrics, yet stay in the leaf chain, where a scan reads and skips them ([pgstatindex.c#page-classification](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L326), [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2191-L2243), [nbtsearch.c#_bt_walk_left-half-dead-note](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2364-L2376)).
- **Deleted pages.** They sit in `deleted_pages`, are skipped by scans, and are still priced by the planner, measured at 271 deleted pages in a 551-page file.
- **`NaN`.** `avg_leaf_density` is `NaN` when no live leaf page contributed space, and `leaf_fragmentation` when `leaf_pages` is 0 ([pgstatindex.c#avg_leaf_density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L367), [pgstatindex.c#leaf_fragmentation](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L368-L372)). The `pgstattuple` [regression test](../../../glossary.md#regression-test) shows both as `NaN` for an empty index and for an empty index on a partition ([pgstattuple.out#empty-index-NaN](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L44-L52), [pgstattuple.out#partition-index-NaN](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L260-L268)).
- **Direction and distance.** `leaf_fragmentation` sees only backward right links, and records neither how far a link jumps nor what a backward scan sees. The descending-order index read 99.96 although every step but one moved a single block.
- **Time.** The report is accumulated page by page while the index may change ([pgstattuple.sgml#pgstatindex-not-a-snapshot](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L275-L279)).

### Which one matters more

Density matters more whenever the question is how many index buffers PostgreSQL will touch. Fragmentation matters more only when each of those touches is an uncached read on storage that charges much more for non-sequential access.

| Workload | Matters more | Why |
|---|---|---|
| Point lookup on a unique or highly selective key | Usually neither | The scan reads one root-to-leaf path. Every point lookup measured here read 3 index blocks and 1 visibility-map block, at 90 %, 60 %, fragmented or rebuilt. Density reaches it only through tree height, which the descent charge prices ([nbtsearch.c#_bt_first-descend-and-read](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1387-L1469), [selfuncs.c#btcostestimate-height-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)). |
| Warm range scan | Density, and specifically the range's local density | 100,000 keys cost 276 index blocks at 90 % and 415 at 60 %. The same keys cost 397 on the random-order index and 371 rebuilt, and the gap is local density: order costs nothing on cached pages ([config.sgml#random_page_cost-cached](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5896-L5907)). |
| Cold range scan on storage with a low random-read penalty | Usually density | The order model at `R / S = 1.2` caps at 1.20x, below the 1.50x of 60 % against 90 %. The 17.11 docs no longer give an SSD figure, and this page did not measure one. |
| Cold range scan on magnetic or otherwise seek-sensitive storage | Fragmentation can dominate elapsed time | The model at `R / S = 4` reaches 4.00x at full non-adjacency, against 1.50x for 60 % density, and the docs say random access to durable storage is "normally much more expensive than four times sequential access" ([config.sgml#random_page_cost-durable-storage](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5875-L5882)). PostgreSQL issues one synchronous read per leaf with no prefetch, so nothing in the server hides a seek. |
| Full index scan or index-only `count(*)` | Density sets the count; order sets locality | 2,735 index blocks at 90 %, 4,118 at 60 %, 3,703 fragmented, 3,679 rebuilt. Direction matters for plain index scans only: backward, they read every leaf twice. |
| Bitmap index scan | Density on the index side | `btgetbitmap()` runs the same forward leaf walk, and measured the same index blocks as the index-only scan ([nbtree.c#btgetbitmap](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L262-L306)). The heap side after the bitmap is a separate concern and the only one that prefetches, which this host could not do ([nodeBitmapHeapscan.c:551](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L551)). |
| Parallel index scan | Density | The participants share one leaf chain and read the same index blocks as a serial scan, 2,735 and 4,118, plus one visibility-map block each. |

### Settings and apply scope

No setting changes an index's physical layout. The planner and I/O settings below change what the planner assumes or what the executor overlaps; each context is read from the pinned `guc_tables.c` and mapped as `postmaster` to restart, `sighup` to reload, and `user` or `superuser` to session or transaction scope, per the [GUC context](../../../glossary.md#guc-context) rules.

| Setting | Context | Apply scope | Relevance to index scan I/O |
|---|---|---|---|
| `seq_page_cost` | `user` ([guc_tables.c#seq_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3675-L3685)) | session or transaction | the `S` of the order model; the planner never charges it for B-tree pages; a tablespace can override it ([spccache.c#get_tablespace_page_costs](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L173-L205)) |
| `random_page_cost` | `user` ([guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696)) | session or transaction | the `R`; charged for every index page a scan is expected to touch |
| `effective_cache_size` | `user` ([guc_tables.c#effective_cache_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3518)) | session or transaction | caps repeated-scan page counts through `index_pages_fetched()` |
| `effective_io_concurrency` | `user` ([guc_tables.c#effective_io_concurrency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3109-L3121)) | session or transaction | bitmap heap scan prefetch depth, and the I/O depth of non-maintenance read streams; no B-tree index read uses it ([nodeBitmapHeapscan.c#prefetch_maximum](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L760-L764), [read_stream.c#max_ios](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L420-L442)) |
| `maintenance_io_concurrency` | `user` ([guc_tables.c#maintenance_io_concurrency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3123-L3136)) | session or transaction | heap prefetch while B-tree simple and bottom-up deletion check the heap, maintenance read streams, and recovery prefetch ([heapam.c#heap_index_delete_tuples-prefetch-distance](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8540-L8570), [read_stream.c#max_ios](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L420-L442), [xlogprefetcher.c#max_inflight](../../../../raw/postgres-17/src/backend/access/transam/xlogprefetcher.c#L1000-L1004)) |
| `io_combine_limit` | `user` ([guc_tables.c#io_combine_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3138-L3150)) | session or transaction | read streams only, so no B-tree scan ([read_stream.c:536](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L536)) |
| `recovery_prefetch` | `sighup` ([guc_tables.c#recovery_prefetch](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L5078-L5086)) | reload | the one core path that can prefetch index blocks, and only during WAL replay |
| `track_io_timing` | `superuser` ([guc_tables.c#track_io_timing](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1420-L1428)) | session or transaction | times each read and write; `EXPLAIN (BUFFERS)` prints the times as `I/O Timings`, and the cumulative statistics accumulate them; like the buffer counts, they record no order ([pgstat_io.c#pgstat_count_io_op_time](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_io.c#L121-L151), [explain.c#show_buffer_usage-io-timings](../../../../raw/postgres-17/src/backend/commands/explain.c#L3819-L3860)) |
| `min_parallel_index_scan_size`, `max_parallel_workers_per_gather` | `user` ([guc_tables.c#min_parallel_index_scan_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3531-L3540), [guc_tables.c#max_parallel_workers_per_gather](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3419-L3428)) | session or transaction | worker count for a parallel index scan, from the index pages it expects to touch ([allpaths.c#compute_parallel_worker](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4203-L4279)) |
| `vacuum_buffer_usage_limit` | `user` ([guc_tables.c#vacuum_buffer_usage_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2272-L2281)) | session or transaction | the ring `VACUUM` reads index pages through; not a scan setting ([vacuum.c#vacuum-buffer-strategy](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L436-L445), [vacuumlazy.c:2434](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2434), [nbtree.c#btvacuumpage-strategy-read](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1098-L1105)) |
| `shared_buffers` | `postmaster` ([guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270)) | restart | decides whether a scan's pages stay warm, which is when order stops mattering |
| `synchronous_commit` | `user` ([guc_tables.c#synchronous_commit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4925-L4933)) | session or transaction | `off` can keep freshly loaded pages out of the visibility map, turning index-only scans into heap fetches |
| `wal_writer_delay`, `wal_writer_flush_after` | `sighup` ([guc_tables.c#wal_writer_delay](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2902-L2911), [guc_tables.c#wal_writer_flush_after](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2913-L2922)) | reload | bound how long an asynchronous commit stays unflushed |
| `debug_io_direct` | `postmaster` ([guc_tables.c#debug_io_direct](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4699-L4708)) | restart | bypasses the kernel cache for data files; the docs say it "reduces performance, and is intended for developer testing only" ([config.sgml#debug_io_direct](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L11602-L11624)) |

The layout levers are [REINDEX](../../../glossary.md#reindex) and the `fillfactor` [storage parameter](../../../glossary.md#storage-parameter).

- **`REINDEX`, and `REINDEX CONCURRENTLY`, which exists in 17.** A rebuild writes the leaves in key order at the index's fillfactor, allocating block numbers in the order it fills pages ([nbtsort.c#page-number-allocation](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L650-L654), [nbtsort.c#page-full-test](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L844-L855)). Plain `REINDEX` "requires an `ACCESS EXCLUSIVE` lock by default", and the [CONCURRENTLY](../../../glossary.md#concurrently) option needs only `SHARE UPDATE EXCLUSIVE` ([maintenance.sgml#routine-reindex-locks](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1056-L1062), [ref/reindex.sgml#concurrently](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml#L166-L182)). Measured, the rebuild took `N` from 100 % to 0.35 % and `leaf_fragmentation` from 49.45 to 0, and cut warm buffer accesses by 0.65 %, all of it from 24 fewer pages.
- **`fillfactor`.** It governs the build and the rightmost and split-after-new-item splits, and is read from the index's options at split time ([create_index.sgml#index-reloption-fillfactor](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L404-L411), [nbtsplitloc.c:172](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L172)). `ALTER INDEX ... SET (fillfactor = n)` does not modify the index contents at once; the documentation points to `REINDEX` for the full effect ([ref/alter_index.sgml#set-storage-parameter](../../../../raw/postgres-17/doc/src/sgml/ref/alter_index.sgml#L122-L133)). A lower value costs leaf-page I/O in exchange for fewer early splits: the documentation calls 50 to 90 a range that can "smooth out" the rate of page splits after a bulk load ([create_index.sgml#index-reloption-fillfactor-inserts](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L413-L426)).

### Operational reading

Read density first: `leaf_pages`, `index_size` and `avg_leaf_density` predict PostgreSQL-visible index I/O, and the fillfactor ladder shows how closely. A fall from 90 % to 60 % means about 50 % more leaf visits on any walking scan.

Read `leaf_fragmentation` second, as a detector rather than a magnitude. A nonzero value says that some leaves link backward; it does not say how many steps are non-sequential, how far they jump, or in which direction a scan meets them. Run the census in the script for that. Whether the disorder costs anything then depends on cache residency and the storage's non-sequential penalty, neither of which PostgreSQL reports.

This survey reads both columns for every ordinary B-tree index. It reads every block of each index it reports, so treat it as a diagnostic, not a monitoring query ([pgstatindex.c#full-block-scan](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L278-L331)). Both timeouts are `user` context, so the `SET` statements apply at session scope with no reload or restart ([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)). `lock_timeout` bounds the wait for each index's `AccessShareLock`. That lock conflicts only with `ACCESS EXCLUSIVE`, the mode a plain `REINDEX` takes, but it waits behind a queued `ACCESS EXCLUSIVE` request as well as a granted one ([pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L203-L213), [lock.c#LockConflicts-AccessShareLock](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L67-L68), [lock.c#LockAcquireExtended-wait-queue](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L1031-L1040)).

```sql
SET /* wiki_leaf_density_vs_fragmentation */ statement_timeout = '10min';
SET /* wiki_leaf_density_vs_fragmentation */ lock_timeout = '5s';

WITH /* wiki_leaf_density_vs_fragmentation */ candidate AS MATERIALIZED (
    SELECT c.oid AS indexrelid,
           n.nspname AS schema_name,
           c.relname AS index_name
      FROM pg_class c
      JOIN pg_index i ON i.indexrelid = c.oid
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_am am ON am.oid = c.relam
     WHERE c.relkind = 'i'
       AND am.amname = 'btree'
       AND c.relpersistence <> 't'
       AND i.indisvalid
       AND n.nspname NOT IN ('pg_catalog', 'information_schema')
       AND n.nspname !~ '^pg_toast'
)
SELECT k.schema_name,
       k.index_name,
       s.index_size / current_setting('block_size')::int AS blocks,
       s.tree_level,
       s.leaf_pages,
       s.empty_pages,
       s.deleted_pages,
       s.avg_leaf_density,
       s.leaf_fragmentation
  FROM candidate k
 CROSS JOIN LATERAL pgstatindex(k.indexrelid::regclass) AS s
 WHERE s.leaf_pages > 0
 ORDER BY s.leaf_fragmentation DESC, s.avg_leaf_density, k.schema_name, k.index_name;
```

Each filter mirrors a rule `pgstatindex` enforces, or chooses to be broader. Every refusal below was measured on a database that holds each kind of index:

- **`c.relkind = 'i'`** matches `IS_INDEX()`, which accepts only plain indexes. A partitioned parent, `relkind = 'I'`, fails with `relation "part_idx" is not a btree index` ([pgstatindex.c#relkind-am-macros](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L70-L71)).
- **`am.amname = 'btree'`** matches `IS_BTREE()`. A hash index fails with the same message.
- **`i.indisvalid`** matches 17's validity check. The [invalid index](../../../glossary.md#invalid-index) a failed `CREATE UNIQUE INDEX CONCURRENTLY` left behind fails with `index "mixed_invalid" is not valid`, and without this filter the whole survey stopped on it ([pgstatindex.c#relation-checks](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L250)).
- **`c.relpersistence <> 't'`** is broader than the server's rule. `RELATION_IS_OTHER_TEMP()` rejects only other sessions' temporary relations ([rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/src/include/utils/rel.h#L667-L669)). The session's own temporary index worked and reported 3 leaf pages at 81.99, while another session's failed with `cannot access temporary tables of other sessions`. Without this filter the survey stopped on the other session's index.
- **The schema filter** is a choice: `pgstatindex` accepts catalog and TOAST indexes, and this survey leaves them out.
- **`s.leaf_pages > 0`** drops empty indexes, whose two columns are `NaN`.

The `AS MATERIALIZED` is defensive, and it guards the filters that come from joins. The PostgreSQL 17 documentation says a side-effect-free `WITH` query referenced once is folded into the parent query by default, and that `MATERIALIZED` forces separate evaluation ([queries.sgml#with-materialization](../../../../raw/postgres-17/doc/src/sgml/queries.sgml#L2520-L2535)). In both measured plans the `relkind` and `relpersistence` tests are filters on the `pg_class` scan itself, while the access method, `indisvalid` and schema tests come from joins. With `MATERIALIZED`, every row reaches `pgstatindex` through the finished candidate list. With `NOT MATERIALIZED` the planner happened to put the function scan above every join, so the survey returned the same rows, but nothing in that plan obliges it to.

Privileges. Version 1.5 of `pgstattuple`, the default in 17, revokes `EXECUTE` on `pgstatindex(regclass)` from `PUBLIC` and grants it to `pg_stat_scan_tables`; the function then opens the index with no check of its own ([pgstattuple--1.4--1.5.sql#pgstatindex-grants](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92), [pgstattuple.control:3](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.control#L3), [pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L203-L213), [pgstattuple.sgml#privileges](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L15-L24)). Measured with a role that has no `SELECT` on any fixture table: with no grant the survey failed with `permission denied for function pgstatindex`; as a member of `pg_stat_scan_tables` it returned all 8 rows a superuser saw; with a direct `GRANT EXECUTE ON FUNCTION pgstatindex(regclass)` it returned the same 8. Either grant exposes page-level statistics for every index, including those on tables the role cannot read.

For maintenance decisions, PostgreSQL 17 source and documentation define no threshold such as "reindex at 60 % density" or "at 40 % fragmentation". The documentation recommends periodic reindexing for B-tree indexes whose pages keep only a few keys, and notes that a rebuild can speed access by restoring physical adjacency ([maintenance.sgml#routine-reindex-partly-empty](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1032-L1040), [maintenance.sgml#routine-reindex-adjacency](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1048-L1054)). This survey is a report, not a rebuild rule, and it has not been scored against the wiki's [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md).

### Tests and coverage

- The `pgstattuple` regression test calls `pgstatindex` only on empty indexes, where both columns are `NaN`, and on the error paths for other relation kinds and access methods. Its own comment says platform-independent cases are hard to write, so it tests empty relations. It never populates a B-tree, and it has no case for the 17 "is not valid" error ([pgstattuple.sql#empty-relations](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L1-L37), [pgstattuple.sql#partition-index](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L110-L120), [pgstattuple.out#empty-index-NaN](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L44-L52)).
- The [pageinspect](../../../glossary.md#pageinspect) test reads `bt_page_stats()` on a one-row index and `bt_multi_page_stats()` on a 1,000-row index. It shows sibling links but relates them to nothing ([btree.sql#bt_multi_page_stats](../../../../raw/postgres-17/contrib/pageinspect/sql/btree.sql#L1-L23)).
- The core `btree_index` test builds a deliberately tall tree at `fillfactor = 10` and exercises multilevel page deletion and free-space-map page recycling, but compares no scan I/O ([btree_index.sql#tall-tree](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L240-L250), [btree_index.sql#page-deletion-and-recycling](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L252-L270)).
- No test in the pinned checkout relates density or fragmentation to scan I/O. The measurements on this page come from a disposable server built from the pin, on which the core suite and the four contrib suites the script uses passed.

## Measurement Script

### Usage

| Item | Detail |
|---|---|
| Purpose | produces every measured number on this page: the verdict table, the density pair with its serial and parallel plans, costs and per-relation split, the fillfactor ladder, the scan shapes and directions, the fragmentation pair with its census and per-tenth ranges, the descending-order fixture, the seed sweep, the dead-space and recycling fixtures, the `synchronous_commit` probe, the survey's measured behaviour, and the evaluated model tables |
| Invocation | `bash .wiki-runtime/tmp/ldfrag.sh` from the repository root, with the script saved at that path. Any path works: every path derives from `WIKI_ROOT`, which defaults to `$PWD` |
| Stages | `build check cluster density ladder scans frag desc seeds dead recycle async survey model summary stop` in that default order, plus `clean` on request; select stages as arguments, for example `bash .wiki-runtime/tmp/ldfrag.sh frag model summary`. `build` checks that the checkout is at the pin with no tracked file changed, configures out of tree, installs core plus `pgstattuple`, `pageinspect`, `pg_visibility` and `pg_freespacemap`, and records the pin beside the binaries; it skips the build when binaries from the pin exist. `check` runs `make check` and the four contrib suites. `cluster` runs `initdb` once, writes `ldfrag.conf`, starts the server, creates the `ldfrag` database, and installs the extensions and the recording harness in schema `ldh`; re-running it clears every recorded result. `density`, `ladder`, `scans`, `frag`, `desc`, `seeds`, `dead`, `recycle`, `async` and `survey` build and measure their fixtures. `model` evaluates the page's formulas from the recorded facts. `summary` writes the result file. `stop` stops the server and asserts the teardown; `clean` also deletes the sandbox. Each fixture stage drops and rebuilds its own tables and replaces its own results, so any stage can be re-run alone after `cluster`; `scans` needs `density`, and `model` needs `density`, `ladder` and `frag` |
| Failure handling | Every stage name is checked before any stage runs. Every `psql` call that fails ends the run with a non-zero status, and every measurement fails the run if the plan is not the intended node, index, direction and worker count, or if it read a block from outside shared buffers. `expect_error()` runs the survey stage's deliberately failing statements and fails the run if one succeeds. An `EXIT` trap stops the server, and the survey's background session, on every path out, and only in a sandbox the run claimed as its own |
| Environment | `WIKI_ROOT` (`$PWD`), `SRC` (`$WIKI_ROOT/raw/postgres-17`), `SANDBOX` (`$WIKI_ROOT/.wiki-runtime/tmp/ldfrag`, which must resolve to a directory directly inside `.wiki-runtime/tmp`), `PORT` (`55471`), `JOBS` (`8`), `ASYNC_TRIALS` (`5`). The pin, the row counts, the seeds and the fillfactor ladder are constants in the script. A `PGOPTIONS` in the caller's environment reaches no measurement session |
| Prerequisites | `bash`, `git`, a C toolchain, `make`, `flex`, `bison` and `perl` for the build, and zlib headers. The tree is configured `--without-icu --without-readline`, so neither library is needed. `initdb` runs with `--locale=C --encoding=UTF8`. About 2 GiB of disk for the build, install and data directories. No extension outside the four contrib modules above |
| Output | `$SANDBOX/out/summary.txt`: the suite results, one table per page table, every recorded value in recording order, the model values, one line per plan node, the survey outputs and plans, and the count of server-log `ERROR` lines. Read it first. The per-stage `psql` output, the generated SQL under `out/sql/`, `server.log`, the survey's output files and the build and test logs sit beside it |
| Runtime | 3 to 4 minutes for a full run from an empty sandbox on 10 cores, of which about 2 minutes is the build and the five suites; 1 to 2 minutes to re-run every fixture stage on a built tree |
| Cleanup | `bash .wiki-runtime/tmp/ldfrag.sh clean` stops the server, asserts that `pg_ctl` finds no server and that no `postmaster.pid`, no process naming the data directory and no socket for `$PORT` is left, and deletes `$SANDBOX`. It refuses a directory without the script's `.ldfrag-sandbox` mark. The default run ends with `stop`, which makes the same assertions and keeps the sandbox |

Isolation and safety. The pinned checkout is read only and checked against the pin before it is built; the build is out of tree; the cluster has its own data directory, socket directory and port. Every fixture statement is disposable: the script creates and drops its own tables, indexes and one role, `ld_reader`, in its own database, and none of those statements is meant for a database anyone cares about. The filed survey is the one statement written for real databases. Every statement the script sends carries a `/* wiki_ldfrag_... */` tag after its leading verb, statements inside the recording helpers included; the survey carries the page's `/* wiki_leaf_density_vs_fragmentation */` tag. Every `psql` call runs `-X` with `ON_ERROR_STOP` and with session-scoped `statement_timeout = 30min` and `lock_timeout = 60s`; the survey sets its own 10 minutes and 5 seconds. GUC contexts are named in the script header: `port`, `listen_addresses`, `unix_socket_directories` and `shared_buffers` are `postmaster`, written once and applied by the start; `autovacuum` is `sighup`; every other setting the script changes is `user` and applies at session scope.

### Last run

| Item | Value |
|---|---|
| Date | 2026-09-23, one full run from an empty sandbox, 21:51:48Z to 21:55:13Z |
| Server | `PostgreSQL 17.11 on aarch64-apple-darwin27.0.0, compiled by Apple clang version 21.0.0 (clang-2100.3.34.2), 64-bit`, built from pin `786db8dcf168bd9df8f55047337525ac19118b1c` and configured `--without-icu --without-readline`. The script recorded the same commit for the pin, the install and the checkout |
| Platform | Darwin 27.0.0 arm64, 10 cores, bash 5.3.15, `block_size` 8192, maximum data alignment 8, `initdb --locale=C --encoding=UTF8`, data checksums off, `wal_level = replica`. `effective_io_concurrency` and `maintenance_io_concurrency` are 0 because the platform has no `posix_fadvise` |
| Settings | `shared_buffers = 512MB`, `autovacuum = off`, `synchronous_commit = on`; every other setting at its default, including `max_parallel_workers_per_gather = 2`, `max_parallel_maintenance_workers = 2`, `random_page_cost = 4`, `seq_page_cost = 1`, `wal_writer_delay = 200ms` and `wal_writer_flush_after = 128` blocks |
| Test suites | `make check` All 225 tests passed; `pgstattuple` All 1, `pageinspect` All 8, `pg_visibility` All 1, `pg_freespacemap` All 1 |
| Runtime | 3 minutes 25 seconds from an empty sandbox |
| Reproduction | Three earlier full runs the same day, with earlier versions of the script, gave the same fixture values wherever they recorded them; one of them stopped at the `model` stage on a type error in the script's own arithmetic, since fixed. What moved between runs was what depends on timing or sampling: the `synchronous_commit` probe's LSNs and the moment its WAL writer ran, the survey's temporary-schema name, and range-scan plan costs, which follow `ANALYZE`'s sample. The last edit before this run changed only the rounding of the model's cost check |
| Server log | 8 `ERROR` lines, each a failure the survey stage asked for |
| Teardown | the run ended with the `stop` stage, which asserted that `pg_ctl` found no server and that no `postmaster.pid`, no process naming the data directory and no socket for port 55471 was left; the `clean` stage then deleted the sandbox |

The published script is the file that ran, byte for byte: 1,588 lines, md5 `6e3de97c4a2451add9e2081891479c8b`.

### The script

```bash
#!/usr/bin/env bash
# Measurements for the wiki page
#   wiki/v17/questions/indexing/leaf-density-vs-fragmentation-index-scan-io.md
#
# What this measures, and why it is safe to run
# ---------------------------------------------
# Every number that page reports about a running PostgreSQL 17 server comes
# from this script.  It builds the pinned checkout out of tree, starts one
# isolated cluster, and builds B-tree indexes over the same 1,000,000 bigint
# keys in different physical shapes: fresh builds at eight fillfactors, retail
# inserts in random key order under four seeds, the random-order index
# rebuilt at the fillfactor that matches its density, and retail inserts in
# descending key order.  For each shape it
# records what pgstatindex, pageinspect, the planner, EXPLAIN (ANALYZE,
# BUFFERS) and the per-relation cumulative counters report.  It also builds a
# 200,000-row dead-space fixture, a 200,000-row fixture whose emptied leaf
# pages are deleted, recycled through the free space map and reused, probes
# whether synchronous_commit = off keeps VACUUM from setting visibility-map
# bits, runs the page's survey statement against a database that holds every
# kind of index the statement must skip, and evaluates the page's arithmetic
# models.  Buffer counts are warm-cache buffer accesses, not device reads.
# Nothing is timed.
#
# The pinned checkout under raw/postgres-17 is read only.  The build and check
# stages refuse to run unless it is at $PIN with no tracked file changed, the
# build records $PIN beside the binaries, and every later stage refuses an
# install built from anything else.  Everything this script writes lives under
# $SANDBOX, which must resolve to a directory directly inside this
# repository's .wiki-runtime/tmp.  The script marks the sandbox when it
# creates it, and stop and clean touch nothing that does not carry the mark.
# The cluster has its own data directory, its own socket directory and a
# non-default port; it is never a cluster anyone else named.
#
# Every fixture is disposable: the script creates and drops its own tables,
# indexes and one role (ld_reader) in its own database, ldfrag.  None of the
# fixture statements is meant for a database anyone cares about.  The one
# statement written for real databases is the survey in $OUT/survey.sql,
# which the page files verbatim.
#
# Usage, from the repository root:
#   bash .wiki-runtime/tmp/ldfrag.sh                   # every stage, in order
#   bash .wiki-runtime/tmp/ldfrag.sh frag model        # selected stages
#   bash .wiki-runtime/tmp/ldfrag.sh clean             # stop, delete sandbox
#
# Stages, in default order:
#   build check cluster density ladder scans frag desc seeds dead recycle
#   async survey model summary stop
# and, on request only: clean
#
# Results.  Every measured value goes to the table ldh.fact through ldh.put(),
# every captured plan to ldh.plan, and every model value to ldh.model.  The
# summary stage writes all three, the platform facts, the test results and the
# survey outputs to $SANDBOX/out/summary.txt.
#
# Failure and teardown.  Every psql call that fails ends the run with a
# non-zero status, and stage exit status is checked on top of that.  Every
# stage name is checked before any stage runs.  The two deliberate exceptions
# are expect_error() and the background session that owns a temporary index,
# both in the survey stage: the first runs statements that must fail and
# records their messages, and fails the run if one succeeds.  An EXIT trap
# stops the server and the background session on every path out of the
# script, successful or not, so no postmaster is left behind; the sandbox is
# kept until the clean stage runs.  Every SQL stage starts the server if it is
# not up, so a selected re-run works after a finished run.
#
# Environment: WIKI_ROOT SRC SANDBOX PORT JOBS ASYNC_TRIALS
#
# GUC apply scopes, from the pinned v17 guc_tables.c:
#   port, listen_addresses, unix_socket_directories, shared_buffers
#       -> PGC_POSTMASTER, restart.  Written once to ldfrag.conf by cluster.
#   autovacuum -> PGC_SIGHUP, reload.  Written once to ldfrag.conf.
#   synchronous_commit -> PGC_USERSET.  Written to ldfrag.conf as on (its
#       default) and set to off at session scope in the async stage only.
#   enable_seqscan, enable_bitmapscan, enable_indexscan, enable_indexonlyscan,
#   max_parallel_workers_per_gather, stats_fetch_consistency,
#   statement_timeout, lock_timeout, application_name
#       -> PGC_USERSET, session scope, no reload and no restart.
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
SRC="${SRC:-$WIKI_ROOT/raw/postgres-17}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/ldfrag}"
PORT="${PORT:-55471}"
JOBS="${JOBS:-8}"
ASYNC_TRIALS="${ASYNC_TRIALS:-5}"

# The commit the page pins.
PIN=786db8dcf168bd9df8f55047337525ac19118b1c
MARKER=.ldfrag-sandbox
PINFILE=.ldfrag-pin
SANDBOX_OK=0
HOLDER_PID=""
CURRENT_STAGE=""

# Fixture sizes and ladders.  They are constants, not environment variables,
# because every number on the page depends on them.
ROWS=1000000
DEAD_ROWS=200000
SEEDS="0.1 0.25 0.5 0.9"
LADDER="95 90 80 70 60 50 40 30"

KNOWN_STAGES="build check cluster density ladder scans frag desc seeds dead recycle async survey model summary stop clean"
DEFAULT_STAGES="build check cluster density ladder scans frag desc seeds dead recycle async survey model summary stop"

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# resolve_sandbox: turn $SANDBOX into its real path, and refuse one that is not
# a directory directly inside this repository's .wiki-runtime/tmp once .. and
# symbolic links are resolved.
resolve_sandbox() {
  local tmp parent base real
  mkdir -p "$WIKI_ROOT/.wiki-runtime/tmp" || die "cannot create $WIKI_ROOT/.wiki-runtime/tmp"
  tmp=$(cd "$WIKI_ROOT/.wiki-runtime/tmp" && pwd -P) || die "cannot resolve .wiki-runtime/tmp"
  base=$(basename "$SANDBOX")
  case "$base" in ''|.|..|/) die "refusing sandbox $SANDBOX: it names no directory of its own" ;; esac
  if [ -e "$SANDBOX" ] || [ -L "$SANDBOX" ]; then
    real=$(cd "$SANDBOX" 2>/dev/null && pwd -P) || die "refusing sandbox $SANDBOX: it is not a directory"
  else
    parent=$(cd "$(dirname "$SANDBOX")" 2>/dev/null && pwd -P) \
      || die "refusing sandbox $SANDBOX: its parent directory does not exist"
    real="$parent/$base"
  fi
  [ "$(dirname "$real")" = "$tmp" ] || die "refusing sandbox $SANDBOX: $real is not directly inside $tmp"
  SANDBOX="$real"
}
resolve_sandbox

BUILD="$SANDBOX/build"; INST="$SANDBOX/install"; DATA="$SANDBOX/data"
SOCK="$SANDBOX/sock"; OUT="$SANDBOX/out"; BIN="$INST/bin"; DB=ldfrag
export PGPORT="$PORT" PGHOST="$SOCK" PGDATABASE="$DB" PGUSER=postgres

check_pin() {
  local head dirty
  head=$(git -C "$SRC" rev-parse HEAD 2>/dev/null) || die "$SRC is not a git checkout"
  [ "$head" = "$PIN" ] || die "$SRC is at $head, not at the pinned $PIN"
  dirty=$(git -C "$SRC" status --porcelain --untracked-files=no 2>/dev/null) \
    || die "git status failed in $SRC"
  [ -z "$dirty" ] || die "$SRC has changed tracked files, so a build would not be the pin"
}

check_install_pin() {
  local built
  built=$(cat "$INST/$PINFILE" 2>/dev/null) || die "$INST has no build record: run the build stage"
  [ "$built" = "$PIN" ] || die "$INST was built from $built, not the pinned $PIN: run clean, then build"
}

# claim_sandbox: create $SANDBOX, or accept one this script created, and mark
# it.  An existing non-empty directory without the mark is refused.
claim_sandbox() {
  if [ -e "$SANDBOX" ] && [ ! -f "$SANDBOX/$MARKER" ] \
     && [ -n "$(ls -A "$SANDBOX" 2>/dev/null)" ]; then
    die "refusing sandbox $SANDBOX: it exists, is not empty, and this script did not create it"
  fi
  mkdir -p "$SANDBOX" && : > "$SANDBOX/$MARKER" || die "cannot create $SANDBOX"
  mkdir -p "$OUT/sql" || die "cannot create $OUT"
  SANDBOX_OK=1
}

# own_sandbox: the check stop and clean make before they touch anything.
own_sandbox() {
  [ -d "$SANDBOX" ] || { note "no sandbox at $SANDBOX"; return 1; }
  [ -f "$SANDBOX/$MARKER" ] || die "refusing: $SANDBOX carries no $MARKER, so this script did not create it"
  SANDBOX_OK=1
}

# Every psql call runs -X, so a ~/.psqlrc cannot change a result, with
# ON_ERROR_STOP, so no failed statement passes silently, and with the two
# timeouts at session scope.  The options are passed per call and never
# exported, so a PGOPTIONS in the caller's environment reaches no session.
SESSION_OPTS="-c statement_timeout=30min -c lock_timeout=60s"

# pgf FILE LOG [EXTRA_PGOPTIONS [psql args...]]: run one SQL file, append its
# output to LOG, and end the run if psql fails.
pgf() {
  local f="$1" log="$2" extra="${3:-}"
  if [ $# -ge 3 ]; then shift 3; else shift $#; fi
  PGOPTIONS="$SESSION_OPTS $extra" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -f "$f" "$@" >> "$log" 2>&1 \
    || die "psql failed in stage ${CURRENT_STAGE:-<none>} on $f; see $log"
}

# sqlrun STAGE NAME [EXTRA_PGOPTIONS]: write stdin to $OUT/sql/STAGE.NAME.sql
# and run it with pgf.
sqlrun() {
  local f="$OUT/sql/$1.$2.sql"
  cat > "$f" || die "cannot write $f"
  pgf "$f" "$OUT/$1.out" "${3:-}"
}

# pgq SQL: one value, for use inside $(...).  A failure only ends the
# subshell, so every caller follows it with its own || die.
pgq() { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -At -v ON_ERROR_STOP=1 -c "$1"; }

# putv STAGE FIXTURE METRIC VALUE: record an arbitrary string, passed through
# a psql variable so no quoting in VALUE can break the statement.
putv() {
  printf "SELECT /* wiki_ldfrag_%s */ ldh.put(:'st', :'fx', :'me', :'va');\n" "$1" \
    | PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 \
        -v st="$1" -v fx="$2" -v me="$3" -v va="$4" -f - > /dev/null \
    || die "could not record $1/$2/$3"
}

running() { [ -x "$BIN/pg_ctl" ] && [ -f "$DATA/PG_VERSION" ] && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; }

start_server() {
  running && return 0
  "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w -t 120 start > "$OUT/pg_ctl.out" 2>&1 \
    || die "the server did not start; see $OUT/server.log"
}

# stop_holder: end the survey stage's background session.  Its backend sits in
# pg_sleep and would not notice a killed client, so it is terminated from the
# server side first, then the client is reaped.
stop_holder() {
  if [ -n "$HOLDER_PID" ]; then
    if running; then
      pgq "SELECT /* wiki_ldfrag_survey */ count(pg_terminate_backend(pid)) FROM pg_stat_activity WHERE application_name = 'ldfrag_temp_owner'" \
        > /dev/null 2>&1
    fi
    kill "$HOLDER_PID" 2> /dev/null
    wait "$HOLDER_PID" 2> /dev/null
    HOLDER_PID=""
  fi
}

stop_server() {
  stop_holder
  if running; then
    "$BIN/pg_ctl" -D "$DATA" -m fast -w -t 120 stop > /dev/null 2>&1 || die "pg_ctl stop failed"
  fi
  return 0
}

# assert_stopped: pg_ctl finds no server, no postmaster.pid is left, no
# process names the data directory, and no socket file is left for $PORT.
assert_stopped() {
  if [ -x "$BIN/pg_ctl" ] && [ -f "$DATA/PG_VERSION" ] && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    die "a server is still running on $DATA"
  fi
  [ ! -f "$DATA/postmaster.pid" ] || die "$DATA/postmaster.pid is still there"
  if pgrep -f "$DATA" > /dev/null 2>&1; then die "a process still names $DATA"; fi
  [ ! -S "$SOCK/.s.PGSQL.$PORT" ] || die "socket $SOCK/.s.PGSQL.$PORT is still there"
  note "stopped: no server, no postmaster.pid, no process on $DATA, no socket for port $PORT"
}

# The EXIT trap stops the background session and the server on every path out
# of the script, but only in a sandbox this run claimed or verified.
on_exit() {
  local st=$?
  trap - EXIT INT TERM
  stop_holder
  if [ "$SANDBOX_OK" = 1 ] && running; then
    "$BIN/pg_ctl" -D "$DATA" -m fast -w -t 120 stop > /dev/null 2>&1 \
      || printf '!! could not stop the server on %s\n' "$DATA" >&2
    printf '   exit status %s; the server on %s was stopped\n' "$st" "$DATA" >&2
  fi
  exit "$st"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# need_server: every SQL stage runs through this.  It needs a built install,
# a cluster, and the recording harness the cluster stage installs.
need_server() {
  own_sandbox || die "no sandbox: run build, check and cluster first"
  check_install_pin
  [ -f "$DATA/PG_VERSION" ] || die "no cluster at $DATA: run the cluster stage"
  start_server
  local ok
  ok=$(pgq "SELECT /* wiki_ldfrag_need */ to_regnamespace('ldh') IS NOT NULL") || die "cannot query the server"
  [ "$ok" = t ] || die "the recording harness is missing: run the cluster stage"
}

clear_stage() {
  sqlrun "$1" clear <<SQL
DELETE /* wiki_ldfrag_$1 */ FROM ldh.fact WHERE stage = '$1';
DELETE /* wiki_ldfrag_$1 */ FROM ldh.plan WHERE stage = '$1';
SQL
}

# Session settings for the scan shapes.  Every one is PGC_USERSET and is set
# at session scope in the measuring session only.
set_ios_serial() {
  printf 'SET /* wiki_ldfrag_%s */ enable_seqscan = off;\n' "$1"
  printf 'SET /* wiki_ldfrag_%s */ enable_bitmapscan = off;\n' "$1"
  printf 'SET /* wiki_ldfrag_%s */ max_parallel_workers_per_gather = 0;\n' "$1"
}
set_ios_parallel() {
  # max_parallel_workers_per_gather stays at its default, 2.
  printf 'SET /* wiki_ldfrag_%s */ enable_seqscan = off;\n' "$1"
  printf 'SET /* wiki_ldfrag_%s */ enable_bitmapscan = off;\n' "$1"
}
set_plain_serial() {
  set_ios_serial "$1"
  printf 'SET /* wiki_ldfrag_%s */ enable_indexonlyscan = off;\n' "$1"
}
set_bitmap_serial() {
  printf 'SET /* wiki_ldfrag_%s */ enable_seqscan = off;\n' "$1"
  printf 'SET /* wiki_ldfrag_%s */ enable_indexscan = off;\n' "$1"
  printf 'SET /* wiki_ldfrag_%s */ enable_indexonlyscan = off;\n' "$1"
  printf 'SET /* wiki_ldfrag_%s */ max_parallel_workers_per_gather = 0;\n' "$1"
}

# measure STAGE FIXTURE LABEL TABLE INDEX MODE SETTINGS QUERY NODE DIRECTION WORKERS
#
# One measuring session.  MODE warm runs QUERY once first, so the measured
# execution finds every page in shared buffers and the index metapage in the
# session's relcache.  MODE first only plans QUERY first (EXPLAIN without
# ANALYZE), which loads the metapage into the relcache through the planner's
# tree-height lookup but reads no leaf, so the measured execution is the
# first one.  Then the session flushes its pending statistics, resets the
# table's and the index's cumulative counters, runs QUERY once under EXPLAIN
# (ANALYZE, BUFFERS) inside ldh.capture(), flushes again, and reads the two
# relations' counters in ldh.split().  EXPLAIN and the counters therefore
# describe the same execution.  ldh.expect() then fails the run unless the
# plan used NODE on INDEX in DIRECTION with WORKERS launched workers.
measure() {
  local stage="$1" fixture="$2" label="$3" tbl="$4" idx="$5" mode="$6"
  local settings="$7" q="$8" node="$9" dir="${10}" workers="${11}"
  local f="$OUT/sql/$stage.$fixture.$label.sql"
  {
    printf 'SET /* wiki_ldfrag_%s */ stats_fetch_consistency = none;\n' "$stage"
    printf '%s\n' "$settings"
    case "$mode" in
      warm)  printf '%s;\n' "$q" ;;
      first) printf 'EXPLAIN /* wiki_ldfrag_%s */ (COSTS OFF) %s;\n' "$stage" "$q" ;;
      *) die "measure: unknown mode $mode" ;;
    esac
    printf 'SELECT /* wiki_ldfrag_%s */ pg_stat_force_next_flush();\n' "$stage"
    printf "SELECT /* wiki_ldfrag_%s */ pg_stat_reset_single_table_counters('%s'::regclass), pg_stat_reset_single_table_counters('%s'::regclass);\n" \
      "$stage" "$tbl" "$idx"
    printf "SELECT /* wiki_ldfrag_%s */ ldh.capture('%s', '%s', '%s', \$ldq\$%s\$ldq\$);\n" \
      "$stage" "$stage" "$fixture" "$label" "$q"
    printf 'SELECT /* wiki_ldfrag_%s */ pg_stat_force_next_flush();\n' "$stage"
    printf "SELECT /* wiki_ldfrag_%s */ ldh.split('%s', '%s', '%s', '%s'::regclass, '%s'::regclass);\n" \
      "$stage" "$stage" "$fixture" "$label" "$tbl" "$idx"
    printf "SELECT /* wiki_ldfrag_%s */ ldh.expect('%s', '%s', '%s', '%s', '%s', '%s', %s);\n" \
      "$stage" "$stage" "$fixture" "$label" "$node" "$idx" "$dir" "$workers"
  } > "$f" || die "cannot write $f"
  pgf "$f" "$OUT/$stage.out"
}

# The seven scan shapes measured on each index of the density pair and of the
# fragmentation pair.  Q_* are the statements; every one is a disposable
# fixture query.
scan_suite() {
  local stage="$1" fixture="$2" tbl="$3" idx="$4" plain="$5"
  local t="/* wiki_ldfrag_$stage */"
  measure "$stage" "$fixture" ios_fwd "$tbl" "$idx" warm "$(set_ios_serial "$stage")" \
    "SELECT $t id FROM $tbl ORDER BY id OFFSET $((ROWS - 1))" "Index Only Scan" Forward 0
  measure "$stage" "$fixture" ios_bwd "$tbl" "$idx" warm "$(set_ios_serial "$stage")" \
    "SELECT $t id FROM $tbl ORDER BY id DESC OFFSET $((ROWS - 1))" "Index Only Scan" Backward 0
  if [ "$plain" = yes ]; then
    measure "$stage" "$fixture" is_fwd "$tbl" "$idx" warm "$(set_plain_serial "$stage")" \
      "SELECT $t id FROM $tbl ORDER BY id OFFSET $((ROWS - 1))" "Index Scan" Forward 0
    measure "$stage" "$fixture" is_bwd "$tbl" "$idx" warm "$(set_plain_serial "$stage")" \
      "SELECT $t id FROM $tbl ORDER BY id DESC OFFSET $((ROWS - 1))" "Index Scan" Backward 0
  fi
  measure "$stage" "$fixture" point "$tbl" "$idx" warm "$(set_ios_serial "$stage")" \
    "SELECT $t id FROM $tbl WHERE id = 500000" "Index Only Scan" Forward 0
  measure "$stage" "$fixture" range "$tbl" "$idx" warm "$(set_ios_serial "$stage")" \
    "SELECT $t count(*) FROM $tbl WHERE id BETWEEN 450001 AND 550000" "Index Only Scan" Forward 0
  measure "$stage" "$fixture" bitmap "$tbl" "$idx" warm "$(set_bitmap_serial "$stage")" \
    "SELECT $t count(*) FROM $tbl WHERE id IS NOT NULL" "Bitmap Index Scan" none 0
}

# decile_suite: the same range scan over each tenth of the key space, so the
# page can show how evenly the leaves hold the keys.
decile_suite() {
  local stage="$1" fixture="$2" tbl="$3" idx="$4"
  local t="/* wiki_ldfrag_$stage */" d lo hi
  for d in 0 1 2 3 4 5 6 7 8 9; do
    lo=$((d * ROWS / 10 + 1)); hi=$(((d + 1) * ROWS / 10))
    measure "$stage" "$fixture" "decile$d" "$tbl" "$idx" warm "$(set_ios_serial "$stage")" \
      "SELECT $t count(*) FROM $tbl WHERE id BETWEEN $lo AND $hi" "Index Only Scan" Forward 0
  done
}

full_suite() {
  local stage="$1" fixture="$2" tbl="$3" idx="$4"
  local t="/* wiki_ldfrag_$stage */"
  measure "$stage" "$fixture" ios_serial "$tbl" "$idx" warm "$(set_ios_serial "$stage")" \
    "SELECT $t count(*) FROM $tbl" "Index Only Scan" Forward 0
  measure "$stage" "$fixture" ios_parallel "$tbl" "$idx" warm "$(set_ios_parallel "$stage")" \
    "SELECT $t count(*) FROM $tbl" "Index Only Scan" Forward 2
}

# ---------------------------------------------------------------------------
# build: configure out of tree, build, install core plus pgstattuple,
# pageinspect, pg_visibility and pg_freespacemap.  Skipped when binaries built from the pin
# are already installed.
stage_build() {
  check_pin
  claim_sandbox
  if [ -x "$BIN/postgres" ] && [ "$(cat "$INST/$PINFILE" 2>/dev/null)" = "$PIN" ]; then
    note "binaries built from $PIN are installed; skipping the build"
    return 0
  fi
  mkdir -p "$BUILD" || die "cannot create $BUILD"
  ( cd "$BUILD" && "$SRC/configure" --prefix="$INST" --without-icu --without-readline ) \
    > "$OUT/configure.log" 2>&1 || die "configure failed; see $OUT/configure.log"
  make -C "$BUILD" -j"$JOBS" > "$OUT/make.log" 2>&1 || die "make failed; see $OUT/make.log"
  make -C "$BUILD" install > "$OUT/install.log" 2>&1 || die "make install failed; see $OUT/install.log"
  local m
  for m in pgstattuple pageinspect pg_visibility pg_freespacemap; do
    make -C "$BUILD/contrib/$m" -j"$JOBS" install >> "$OUT/install.log" 2>&1 \
      || die "building contrib/$m failed; see $OUT/install.log"
  done
  printf '%s\n' "$PIN" > "$INST/$PINFILE" || die "cannot record the pin beside the binaries"
}

# check: the core regression suite and the four contrib suites this page
# depends on, each against its own temporary installation.
stage_check() {
  check_pin
  own_sandbox || die "no sandbox: run build first"
  check_install_pin
  make -C "$BUILD" check > "$OUT/check-core.log" 2>&1 || die "make check failed; see $OUT/check-core.log"
  local m
  for m in pgstattuple pageinspect pg_visibility pg_freespacemap; do
    make -C "$BUILD/contrib/$m" check > "$OUT/check-$m.log" 2>&1 \
      || die "make check failed in contrib/$m; see $OUT/check-$m.log"
  done
}

# cluster: initdb once, write ldfrag.conf, start the server, create the
# database, and install the four extensions and the recording harness.
# Re-running it recreates the harness schema, which clears every recorded
# result.
stage_cluster() {
  own_sandbox || die "no sandbox: run build first"
  check_install_pin
  mkdir -p "$SOCK" "$OUT/sql" && chmod 700 "$SOCK" || die "cannot create $SOCK"
  if [ ! -f "$DATA/PG_VERSION" ]; then
    "$BIN/initdb" -D "$DATA" -U postgres --auth=trust --locale=C --encoding=UTF8 \
      > "$OUT/initdb.log" 2>&1 || die "initdb failed; see $OUT/initdb.log"
    printf "include_if_exists = 'ldfrag.conf'\n" >> "$DATA/postgresql.conf" \
      || die "cannot edit postgresql.conf"
  fi
  cat > "$DATA/ldfrag.conf" <<CONF || die "cannot write ldfrag.conf"
# Written by ldfrag.sh.  Contexts from the pinned guc_tables.c.
port = $PORT                              # PGC_POSTMASTER: restart
listen_addresses = ''                     # PGC_POSTMASTER: restart
unix_socket_directories = '$SOCK'         # PGC_POSTMASTER: restart
shared_buffers = 512MB                    # PGC_POSTMASTER: restart
autovacuum = off                          # PGC_SIGHUP: reload
synchronous_commit = on                   # PGC_USERSET: session; on is the default
CONF
  start_server
  local have
  have=$(PGDATABASE=postgres pgq "SELECT /* wiki_ldfrag_cluster */ count(*) FROM pg_database WHERE datname = '$DB'") \
    || die "cannot query the server"
  if [ "$have" = 0 ]; then
    PGDATABASE=postgres pgq "CREATE /* wiki_ldfrag_cluster */ DATABASE $DB" > /dev/null || die "cannot create $DB"
  fi
  sqlrun cluster harness <<'SQL'
CREATE /* wiki_ldfrag_cluster */ EXTENSION IF NOT EXISTS pgstattuple;
CREATE /* wiki_ldfrag_cluster */ EXTENSION IF NOT EXISTS pageinspect;
CREATE /* wiki_ldfrag_cluster */ EXTENSION IF NOT EXISTS pg_visibility;
CREATE /* wiki_ldfrag_cluster */ EXTENSION IF NOT EXISTS pg_freespacemap;
DROP /* wiki_ldfrag_cluster */ SCHEMA IF EXISTS ldh CASCADE;
CREATE /* wiki_ldfrag_cluster */ SCHEMA ldh;

-- No primary key and no index on any harness table: the survey reports every
-- ordinary B-tree index in the database, and a harness index would enter it.
CREATE /* wiki_ldfrag_cluster */ TABLE ldh.fact (
    stage       text NOT NULL,
    fixture     text NOT NULL,
    metric      text NOT NULL,
    value       text,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE /* wiki_ldfrag_cluster */ TABLE ldh.plan (
    stage       text NOT NULL,
    fixture     text NOT NULL,
    label       text NOT NULL,
    query       text NOT NULL,
    plan        jsonb NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE /* wiki_ldfrag_cluster */ TABLE ldh.model (
    kind    text NOT NULL,
    row_key text NOT NULL,
    col_key text NOT NULL,
    value   numeric);

CREATE /* wiki_ldfrag_cluster */ FUNCTION ldh.put(p_stage text, p_fixture text, p_metric text, p_value text)
RETURNS void LANGUAGE sql AS $f$
    DELETE /* wiki_ldfrag_put */ FROM ldh.fact
     WHERE stage = p_stage AND fixture = p_fixture AND metric = p_metric;
    INSERT /* wiki_ldfrag_put */ INTO ldh.fact (stage, fixture, metric, value)
    VALUES (p_stage, p_fixture, p_metric, p_value);
$f$;

CREATE /* wiki_ldfrag_cluster */ FUNCTION ldh.get(p_stage text, p_fixture text, p_metric text)
RETURNS text LANGUAGE sql STABLE AS $f$
    SELECT /* wiki_ldfrag_get */ value FROM ldh.fact
     WHERE stage = p_stage AND fixture = p_fixture AND metric = p_metric;
$f$;

-- vis: record the heap's catalog view of visibility (relpages,
-- relallvisible) beside the live map (pg_visibility_map_summary) and the
-- file size.
CREATE /* wiki_ldfrag_cluster */ FUNCTION ldh.vis(p_stage text, p_fixture text, p_tbl regclass)
RETURNS boolean LANGUAGE plpgsql AS $f$
DECLARE
    v_relpages int;
    v_allvis   int;
    v_vm       bigint;
    v_blocks   bigint;
BEGIN
    SELECT /* wiki_ldfrag_vis */ c.relpages, c.relallvisible INTO v_relpages, v_allvis
      FROM pg_class c WHERE c.oid = p_tbl;
    SELECT /* wiki_ldfrag_vis */ s.all_visible INTO v_vm FROM pg_visibility_map_summary(p_tbl) AS s;
    v_blocks := pg_relation_size(p_tbl) / current_setting('block_size')::int;
    PERFORM /* wiki_ldfrag_vis */ ldh.put(p_stage, p_fixture, 'heap_blocks', v_blocks::text);
    PERFORM /* wiki_ldfrag_vis */ ldh.put(p_stage, p_fixture, 'heap_relpages', v_relpages::text);
    PERFORM /* wiki_ldfrag_vis */ ldh.put(p_stage, p_fixture, 'heap_relallvisible', v_allvis::text);
    PERFORM /* wiki_ldfrag_vis */ ldh.put(p_stage, p_fixture, 'vm_all_visible', v_vm::text);
    RETURN v_relpages = v_blocks AND v_allvis = v_blocks AND v_vm = v_blocks;
END
$f$;

-- gate: the visibility gate every scanned fixture passes before it is
-- measured.  An index-only scan over a heap page that is not all-visible
-- turns into a heap fetch, so a fixture that fails the gate is not measured.
CREATE /* wiki_ldfrag_cluster */ FUNCTION ldh.gate(p_stage text, p_fixture text, p_tbl regclass)
RETURNS void LANGUAGE plpgsql AS $f$
BEGIN
    IF NOT ldh.vis(p_stage, p_fixture, p_tbl) THEN
        RAISE EXCEPTION 'visibility gate failed for % (%/%): relpages %, relallvisible %, all-visible in the map %, blocks %',
            p_tbl, p_stage, p_fixture,
            ldh.get(p_stage, p_fixture, 'heap_relpages'),
            ldh.get(p_stage, p_fixture, 'heap_relallvisible'),
            ldh.get(p_stage, p_fixture, 'vm_all_visible'),
            ldh.get(p_stage, p_fixture, 'heap_blocks');
    END IF;
    PERFORM /* wiki_ldfrag_gate */ ldh.put(p_stage, p_fixture, 'gate', 'passed');
END
$f$;

-- pgsi: every pgstatindex column, the metapage levels, and the index's own
-- catalog row.
CREATE /* wiki_ldfrag_cluster */ FUNCTION ldh.pgsi(p_stage text, p_fixture text, p_idx regclass)
RETURNS void LANGUAGE plpgsql AS $f$
DECLARE
    s  record;
    m  record;
    c  record;
    bs int := current_setting('block_size')::int;
BEGIN
    SELECT /* wiki_ldfrag_pgsi */ * INTO s FROM pgstatindex(p_idx);
    SELECT /* wiki_ldfrag_pgsi */ * INTO m FROM bt_metap(p_idx::text);
    SELECT /* wiki_ldfrag_pgsi */ k.relpages, k.reltuples,
           coalesce((SELECT substr(o, 12) FROM unnest(k.reloptions) AS o WHERE o LIKE 'fillfactor=%'), 'unset') AS ff
      INTO c FROM pg_class k WHERE k.oid = p_idx;
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'version', s.version::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'tree_level', s.tree_level::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'index_size_blocks', (s.index_size / bs)::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'root_block_no', s.root_block_no::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'internal_pages', s.internal_pages::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'leaf_pages', s.leaf_pages::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'empty_pages', s.empty_pages::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'deleted_pages', s.deleted_pages::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'avg_leaf_density', s.avg_leaf_density::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'leaf_fragmentation', s.leaf_fragmentation::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'index_blocks', (pg_relation_size(p_idx) / bs)::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'index_relpages', c.relpages::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'index_reltuples', c.reltuples::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'index_fillfactor', c.ff);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'metap_level', m.level::text);
    PERFORM /* wiki_ldfrag_pgsi */ ldh.put(p_stage, p_fixture, 'metap_fastlevel', m.fastlevel::text);
END
$f$;

-- census: every page's sibling link, from pageinspect.  Only live leaf pages
-- (type 'l') enter the link counts, which is the set pgstatindex's
-- leaf_pages counts.  N is the share of right links that do not point at the
-- next physical block; backward_links is what leaf_fragmentation counts.
CREATE /* wiki_ldfrag_cluster */ FUNCTION ldh.census(p_stage text, p_fixture text, p_idx regclass)
RETURNS void LANGUAGE plpgsql AS $f$
DECLARE
    r record;
BEGIN
    WITH /* wiki_ldfrag_census */ b AS MATERIALIZED (
        SELECT s.blkno, s.type, s.btpo_next, s.btpo_prev, s.live_items, s.dead_items
          FROM bt_multi_page_stats(p_idx::text, 1, -1) AS s)
    SELECT count(*) FILTER (WHERE type = 'l') AS leaf_pages,
           count(*) FILTER (WHERE type IN ('i', 'r')) AS internal_pages,
           count(*) FILTER (WHERE type IN ('d', 'D')) AS deleted_pages,
           count(*) FILTER (WHERE type = 'e') AS half_dead_pages,
           count(*) FILTER (WHERE type = 'l' AND btpo_next <> 0) AS forward_links,
           count(*) FILTER (WHERE type = 'l' AND btpo_next <> 0 AND btpo_next < blkno) AS backward_links,
           count(*) FILTER (WHERE type = 'l' AND btpo_next = blkno + 1) AS adjacent_links,
           count(*) FILTER (WHERE type = 'l' AND btpo_next <> 0 AND btpo_next <> blkno + 1) AS nonadjacent_links,
           count(*) FILTER (WHERE type = 'l' AND btpo_next > blkno + 1) AS forward_jumps,
           round(avg(abs(btpo_next - blkno)) FILTER (WHERE type = 'l' AND btpo_next <> 0), 1) AS mean_abs_jump,
           max(abs(btpo_next - blkno)) FILTER (WHERE type = 'l' AND btpo_next <> 0) AS max_abs_jump,
           sum(dead_items) FILTER (WHERE type = 'l') AS leaf_dead_items,
           count(*) FILTER (WHERE type = 'l' AND dead_items > 0) AS leaf_pages_with_dead_items,
           count(*) FILTER (WHERE type = 'l' AND btpo_next = blkno - 1) AS right_to_prev_block,
           count(*) FILTER (WHERE type = 'l' AND btpo_prev <> 0) AS left_links,
           count(*) FILTER (WHERE type = 'l' AND btpo_prev = blkno + 1) AS left_to_next_block,
           count(*) FILTER (WHERE type = 'l' AND btpo_prev = blkno - 1) AS left_to_prev_block,
           round(avg(abs(btpo_prev - blkno)) FILTER (WHERE type = 'l' AND btpo_prev <> 0), 1) AS mean_abs_left_jump
      INTO r FROM b;
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_leaf_pages', r.leaf_pages::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_internal_pages', r.internal_pages::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_deleted_pages', r.deleted_pages::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_half_dead_pages', r.half_dead_pages::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_forward_links', r.forward_links::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_backward_links', r.backward_links::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_adjacent_links', r.adjacent_links::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_nonadjacent_links', r.nonadjacent_links::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_forward_jumps', r.forward_jumps::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_mean_abs_jump', r.mean_abs_jump::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_max_abs_jump', r.max_abs_jump::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_leaf_dead_items', r.leaf_dead_items::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_leaf_pages_with_dead_items', r.leaf_pages_with_dead_items::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_N_pct',
        CASE WHEN r.forward_links > 0
             THEN round(100.0 * r.nonadjacent_links / r.forward_links, 2)::text END);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_backward_pct_of_leaf_pages',
        CASE WHEN r.leaf_pages > 0
             THEN round(100.0 * r.backward_links / r.leaf_pages, 2)::text END);
    -- Signed one-block steps, in both directions: a forward scan follows
    -- right links and a backward scan follows left links.
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_right_to_prev_block', r.right_to_prev_block::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_left_links', r.left_links::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_left_to_next_block', r.left_to_next_block::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_left_to_prev_block', r.left_to_prev_block::text);
    PERFORM /* wiki_ldfrag_census */ ldh.put(p_stage, p_fixture, 'census_mean_abs_left_jump', r.mean_abs_left_jump::text);
END
$f$;

-- xplain: one execution under EXPLAIN (ANALYZE, BUFFERS), as JSON.
CREATE /* wiki_ldfrag_cluster */ FUNCTION ldh.xplain(q text)
RETURNS jsonb LANGUAGE plpgsql AS $f$
DECLARE
    j json;
BEGIN
    EXECUTE 'EXPLAIN /* wiki_ldfrag_explain */ (ANALYZE, BUFFERS, TIMING OFF, SUMMARY OFF, FORMAT JSON) ' || q INTO j;
    RETURN j::jsonb;
END
$f$;

-- capture: run q once under EXPLAIN and record the plan's totals, the index
-- scan node's own numbers, and the Gather node's worker counts.
CREATE /* wiki_ldfrag_cluster */ FUNCTION ldh.capture(p_stage text, p_fixture text, p_label text, q text)
RETURNS void LANGUAGE plpgsql AS $f$
DECLARE
    j   jsonb;
    top jsonb;
    pln jsonb;
    sc  jsonb;
    g   jsonb;
    p   text := p_label || '.';
BEGIN
    j := ldh.xplain(q);
    DELETE /* wiki_ldfrag_capture */ FROM ldh.plan
     WHERE stage = p_stage AND fixture = p_fixture AND label = p_label;
    INSERT /* wiki_ldfrag_capture */ INTO ldh.plan (stage, fixture, label, query, plan)
    VALUES (p_stage, p_fixture, p_label, q, j);
    top := j -> 0 -> 'Plan';
    pln := j -> 0 -> 'Planning';
    sc  := jsonb_path_query_first(j, 'strict $.** ? (@."Node Type" like_regex "Index")');
    g   := jsonb_path_query_first(j, 'strict $.** ? (@."Node Type" == "Gather")');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'top_node', top ->> 'Node Type');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'top_total_cost', top ->> 'Total Cost');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'plan_buffers_hit', top ->> 'Shared Hit Blocks');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'plan_buffers_read', top ->> 'Shared Read Blocks');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'plan_buffers_dirtied', top ->> 'Shared Dirtied Blocks');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'plan_rows', top ->> 'Actual Rows');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'planning_buffers_hit', coalesce(pln ->> 'Shared Hit Blocks', '0'));
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'scan_node', sc ->> 'Node Type');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'scan_index', sc ->> 'Index Name');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'scan_direction', coalesce(sc ->> 'Scan Direction', 'none'));
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'scan_parallel_aware', sc ->> 'Parallel Aware');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'scan_startup_cost', sc ->> 'Startup Cost');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'scan_total_cost', sc ->> 'Total Cost');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'scan_buffers_hit', sc ->> 'Shared Hit Blocks');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'scan_buffers_read', sc ->> 'Shared Read Blocks');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'scan_buffers_dirtied', sc ->> 'Shared Dirtied Blocks');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'heap_fetches', sc ->> 'Heap Fetches');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'scan_rows_per_loop', sc ->> 'Actual Rows');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'scan_loops', sc ->> 'Actual Loops');
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'workers_planned', coalesce(g ->> 'Workers Planned', '0'));
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'workers_launched', coalesce(g ->> 'Workers Launched', '0'));
    PERFORM /* wiki_ldfrag_capture */ ldh.put(p_stage, p_fixture, p || 'gather_total_cost', g ->> 'Total Cost');
END
$f$;

-- split: the same execution's buffer accesses per relation, from the
-- cumulative counters.  Parallel workers flush their counters when they exit,
-- which can be after the leader has returned, so the function waits until
-- the two relations' counters stop moving.  Visibility-map pages are read
-- through the heap relation, so they count on the heap side.
CREATE /* wiki_ldfrag_cluster */ FUNCTION ldh.split(p_stage text, p_fixture text, p_label text, p_tbl regclass, p_idx regclass)
RETURNS void LANGUAGE plpgsql AS $f$
DECLARE
    v_prev   bigint := -1;
    v_cur    bigint;
    v_stable int := 0;
    v_polls  int := 0;
    p        text := p_label || '.';
BEGIN
    IF current_setting('stats_fetch_consistency') <> 'none' THEN
        RAISE EXCEPTION 'split() needs stats_fetch_consistency = none';
    END IF;
    LOOP
        v_cur := pg_stat_get_blocks_fetched(p_idx) + pg_stat_get_blocks_fetched(p_tbl);
        IF v_cur = v_prev THEN v_stable := v_stable + 1; ELSE v_stable := 0; END IF;
        EXIT WHEN v_stable >= 3 OR v_polls >= 100;
        v_prev := v_cur;
        v_polls := v_polls + 1;
        PERFORM /* wiki_ldfrag_split */ pg_sleep(0.1);
    END LOOP;
    IF v_stable < 3 THEN
        RAISE EXCEPTION 'the cumulative counters of % and % did not settle', p_tbl, p_idx;
    END IF;
    PERFORM /* wiki_ldfrag_split */ ldh.put(p_stage, p_fixture, p || 'idx_blks_hit', pg_stat_get_blocks_hit(p_idx)::text);
    PERFORM /* wiki_ldfrag_split */ ldh.put(p_stage, p_fixture, p || 'idx_blks_read',
        (pg_stat_get_blocks_fetched(p_idx) - pg_stat_get_blocks_hit(p_idx))::text);
    PERFORM /* wiki_ldfrag_split */ ldh.put(p_stage, p_fixture, p || 'heap_blks_hit', pg_stat_get_blocks_hit(p_tbl)::text);
    PERFORM /* wiki_ldfrag_split */ ldh.put(p_stage, p_fixture, p || 'heap_blks_read',
        (pg_stat_get_blocks_fetched(p_tbl) - pg_stat_get_blocks_hit(p_tbl))::text);
END
$f$;

-- expect: fail the run unless the recorded plan has the intended shape.
CREATE /* wiki_ldfrag_cluster */ FUNCTION ldh.expect(p_stage text, p_fixture text, p_label text,
                                   p_node text, p_index text, p_dir text, p_workers int)
RETURNS void LANGUAGE plpgsql AS $f$
DECLARE
    p text := p_label || '.';
BEGIN
    IF ldh.get(p_stage, p_fixture, p || 'scan_node') IS DISTINCT FROM p_node
       OR ldh.get(p_stage, p_fixture, p || 'scan_index') IS DISTINCT FROM p_index
       OR ldh.get(p_stage, p_fixture, p || 'scan_direction') IS DISTINCT FROM p_dir
       OR ldh.get(p_stage, p_fixture, p || 'workers_launched')::int <> p_workers
       OR ldh.get(p_stage, p_fixture, p || 'plan_buffers_read')::bigint <> 0 THEN
        RAISE EXCEPTION 'plan for %/%/% is not the intended shape: % on % %, % workers, % buffers read (wanted % on % %, % workers, 0 read)',
            p_stage, p_fixture, p_label,
            ldh.get(p_stage, p_fixture, p || 'scan_node'), ldh.get(p_stage, p_fixture, p || 'scan_index'),
            ldh.get(p_stage, p_fixture, p || 'scan_direction'), ldh.get(p_stage, p_fixture, p || 'workers_launched'),
            ldh.get(p_stage, p_fixture, p || 'plan_buffers_read'),
            p_node, p_index, p_dir, p_workers;
    END IF;
END
$f$;
SQL
}

# ---------------------------------------------------------------------------
# density: the density pair.  Same 1,000,000 keys, loaded in key order, index
# built after the load at fillfactor 90 and at fillfactor 60.
stage_density() {
  need_server
  clear_stage density
  sqlrun density fixtures <<SQL
-- Disposable fixture: creates and drops its own tables.
DROP /* wiki_ldfrag_density */ TABLE IF EXISTS ld_a90, ld_a60;
CREATE /* wiki_ldfrag_density */ TABLE ld_a90 (id bigint);
INSERT /* wiki_ldfrag_density */ INTO ld_a90 SELECT g FROM generate_series(1, $ROWS) AS g;
CREATE /* wiki_ldfrag_density */ INDEX ld_a90_idx ON ld_a90 (id) WITH (fillfactor = 90);
VACUUM /* wiki_ldfrag_density */ (ANALYZE) ld_a90;
CREATE /* wiki_ldfrag_density */ TABLE ld_a60 (id bigint);
INSERT /* wiki_ldfrag_density */ INTO ld_a60 SELECT g FROM generate_series(1, $ROWS) AS g;
CREATE /* wiki_ldfrag_density */ INDEX ld_a60_idx ON ld_a60 (id) WITH (fillfactor = 60);
VACUUM /* wiki_ldfrag_density */ (ANALYZE) ld_a60;
SELECT /* wiki_ldfrag_density */ ldh.gate('density', 'A90', 'ld_a90'), ldh.gate('density', 'A60', 'ld_a60');
SELECT /* wiki_ldfrag_density */ ldh.pgsi('density', 'A90', 'ld_a90_idx'), ldh.pgsi('density', 'A60', 'ld_a60_idx');
SELECT /* wiki_ldfrag_density */ ldh.census('density', 'A90', 'ld_a90_idx'), ldh.census('density', 'A60', 'ld_a60_idx');
SQL
  full_suite density A90 ld_a90 ld_a90_idx
  full_suite density A60 ld_a60 ld_a60_idx
}

# ladder: one heap, one index at a time, rebuilt at each fillfactor.
stage_ladder() {
  need_server
  clear_stage ladder
  sqlrun ladder heap <<SQL
-- Disposable fixture: creates and drops its own table.
DROP /* wiki_ldfrag_ladder */ TABLE IF EXISTS ld_ff;
CREATE /* wiki_ldfrag_ladder */ TABLE ld_ff (id bigint);
INSERT /* wiki_ldfrag_ladder */ INTO ld_ff SELECT g FROM generate_series(1, $ROWS) AS g;
VACUUM /* wiki_ldfrag_ladder */ (ANALYZE) ld_ff;
SQL
  local ff
  for ff in $LADDER; do
    sqlrun ladder "ff$ff" <<SQL
DROP /* wiki_ldfrag_ladder */ INDEX IF EXISTS ld_ff_idx;
CREATE /* wiki_ldfrag_ladder */ INDEX ld_ff_idx ON ld_ff (id) WITH (fillfactor = $ff);
SELECT /* wiki_ldfrag_ladder */ ldh.gate('ladder', 'ff$ff', 'ld_ff');
SELECT /* wiki_ldfrag_ladder */ ldh.pgsi('ladder', 'ff$ff', 'ld_ff_idx');
SQL
    measure ladder "ff$ff" ios_serial ld_ff ld_ff_idx warm "$(set_ios_serial ladder)" \
      "SELECT /* wiki_ldfrag_ladder */ count(*) FROM ld_ff" "Index Only Scan" Forward 0
  done
  sqlrun ladder drop <<'SQL'
DROP /* wiki_ldfrag_ladder */ TABLE IF EXISTS ld_ff;
SQL
}

# scans: forward and backward, index-only and plain, point, range and bitmap
# on the density pair.
stage_scans() {
  need_server
  clear_stage scans
  sqlrun scans gate <<'SQL'
SELECT /* wiki_ldfrag_scans */ ldh.gate('scans', 'A90', 'ld_a90'), ldh.gate('scans', 'A60', 'ld_a60');
SQL
  scan_suite scans A90 ld_a90 ld_a90_idx yes
  scan_suite scans A60 ld_a60 ld_a60_idx yes
}

# frag: the fragmentation pair.  The index exists before the rows arrive, and
# the rows arrive in a seeded random key order, so every key is a retail
# insert.  Then the same index is rebuilt at the fillfactor that matches the
# density the inserts left, and everything is measured again.
stage_frag() {
  need_server
  clear_stage frag
  sqlrun frag fixture <<SQL
-- Disposable fixture: creates and drops its own table.
DROP /* wiki_ldfrag_frag */ TABLE IF EXISTS ld_c;
CREATE /* wiki_ldfrag_frag */ TABLE ld_c (id bigint);
CREATE /* wiki_ldfrag_frag */ INDEX ld_c_idx ON ld_c (id);
SELECT /* wiki_ldfrag_frag */ setseed(0.5);
INSERT /* wiki_ldfrag_frag */ INTO ld_c SELECT g FROM generate_series(1, $ROWS) AS g ORDER BY random();
VACUUM /* wiki_ldfrag_frag */ (ANALYZE) ld_c;
SELECT /* wiki_ldfrag_frag */ ldh.gate('frag', 'C-fragmented', 'ld_c');
SELECT /* wiki_ldfrag_frag */ ldh.pgsi('frag', 'C-fragmented', 'ld_c_idx');
SELECT /* wiki_ldfrag_frag */ ldh.census('frag', 'C-fragmented', 'ld_c_idx');
SQL
  full_suite frag C-fragmented ld_c ld_c_idx
  scan_suite frag C-fragmented ld_c ld_c_idx no
  decile_suite frag C-fragmented ld_c ld_c_idx
  sqlrun frag rebuild <<'SQL'
DO /* wiki_ldfrag_frag */ $d$
DECLARE
    ff int;
BEGIN
    SELECT /* wiki_ldfrag_frag */ round(s.avg_leaf_density)::int INTO ff FROM pgstatindex('ld_c_idx') AS s;
    PERFORM /* wiki_ldfrag_frag */ ldh.put('frag', 'C-rebuilt', 'rebuild_fillfactor', ff::text);
    EXECUTE format('ALTER /* wiki_ldfrag_frag */ INDEX ld_c_idx SET (fillfactor = %s)', ff);
END
$d$;
REINDEX /* wiki_ldfrag_frag */ INDEX ld_c_idx;
SELECT /* wiki_ldfrag_frag */ ldh.gate('frag', 'C-rebuilt', 'ld_c');
SELECT /* wiki_ldfrag_frag */ ldh.pgsi('frag', 'C-rebuilt', 'ld_c_idx');
SELECT /* wiki_ldfrag_frag */ ldh.census('frag', 'C-rebuilt', 'ld_c_idx');
SQL
  full_suite frag C-rebuilt ld_c ld_c_idx
  scan_suite frag C-rebuilt ld_c ld_c_idx no
  decile_suite frag C-rebuilt ld_c ld_c_idx
}

# desc: the same keys inserted retail in descending order.  Every insert lands
# on the leftmost leaf, so every split is a leftmost split, and the pages the
# splits add are appended at the end of the file.
stage_desc() {
  need_server
  clear_stage desc
  local t="/* wiki_ldfrag_desc */"
  sqlrun desc fixture <<SQL
-- Disposable fixture: creates and drops its own table.
DROP /* wiki_ldfrag_desc */ TABLE IF EXISTS ld_d;
CREATE /* wiki_ldfrag_desc */ TABLE ld_d (id bigint);
CREATE /* wiki_ldfrag_desc */ INDEX ld_d_idx ON ld_d (id);
INSERT /* wiki_ldfrag_desc */ INTO ld_d SELECT g FROM generate_series(1, $ROWS) AS g ORDER BY g DESC;
VACUUM /* wiki_ldfrag_desc */ (ANALYZE) ld_d;
SELECT /* wiki_ldfrag_desc */ ldh.gate('desc', 'D-descending', 'ld_d');
SELECT /* wiki_ldfrag_desc */ ldh.pgsi('desc', 'D-descending', 'ld_d_idx');
SELECT /* wiki_ldfrag_desc */ ldh.census('desc', 'D-descending', 'ld_d_idx');
SQL
  measure desc D-descending ios_fwd ld_d ld_d_idx warm "$(set_ios_serial desc)" \
    "SELECT $t id FROM ld_d ORDER BY id OFFSET $((ROWS - 1))" "Index Only Scan" Forward 0
  measure desc D-descending ios_bwd ld_d ld_d_idx warm "$(set_ios_serial desc)" \
    "SELECT $t id FROM ld_d ORDER BY id DESC OFFSET $((ROWS - 1))" "Index Only Scan" Backward 0
  sqlrun desc drop <<'SQL'
DROP /* wiki_ldfrag_desc */ TABLE IF EXISTS ld_d;
SQL
}

# seeds: the fragmentation recipe under four seeds.  Seed 0.5 must reproduce
# the frag stage's fragmented index exactly.
stage_seeds() {
  need_server
  clear_stage seeds
  local s
  for s in $SEEDS; do
    sqlrun seeds "seed$s" <<SQL
-- Disposable fixture: creates and drops its own table.
DROP /* wiki_ldfrag_seeds */ TABLE IF EXISTS ld_seed;
CREATE /* wiki_ldfrag_seeds */ TABLE ld_seed (id bigint);
CREATE /* wiki_ldfrag_seeds */ INDEX ld_seed_idx ON ld_seed (id);
SELECT /* wiki_ldfrag_seeds */ setseed($s);
INSERT /* wiki_ldfrag_seeds */ INTO ld_seed SELECT g FROM generate_series(1, $ROWS) AS g ORDER BY random();
VACUUM /* wiki_ldfrag_seeds */ (ANALYZE) ld_seed;
SELECT /* wiki_ldfrag_seeds */ ldh.gate('seeds', 'seed$s', 'ld_seed');
SELECT /* wiki_ldfrag_seeds */ ldh.pgsi('seeds', 'seed$s', 'ld_seed_idx');
SELECT /* wiki_ldfrag_seeds */ ldh.census('seeds', 'seed$s', 'ld_seed_idx');
SQL
  done
  sqlrun seeds drop <<'SQL'
DROP /* wiki_ldfrag_seeds */ TABLE IF EXISTS ld_seed;
SQL
}

# dead: 200,000 rows, 90 % deleted, measured before the delete, on the first
# scan after it, in the steady state, and after VACUUM.  The unmaintained
# middle states are the point of this fixture.
stage_dead() {
  need_server
  clear_stage dead
  local t="/* wiki_ldfrag_dead */"
  sqlrun dead fixture <<SQL
-- Disposable fixture: creates and drops its own table.
DROP /* wiki_ldfrag_dead */ TABLE IF EXISTS ld_h;
CREATE /* wiki_ldfrag_dead */ TABLE ld_h (id bigint);
INSERT /* wiki_ldfrag_dead */ INTO ld_h SELECT g FROM generate_series(1, $DEAD_ROWS) AS g;
CREATE /* wiki_ldfrag_dead */ INDEX ld_h_idx ON ld_h (id);
VACUUM /* wiki_ldfrag_dead */ (ANALYZE) ld_h;
SELECT /* wiki_ldfrag_dead */ ldh.gate('dead', 'H-baseline', 'ld_h');
SELECT /* wiki_ldfrag_dead */ ldh.pgsi('dead', 'H-baseline', 'ld_h_idx');
SELECT /* wiki_ldfrag_dead */ ldh.census('dead', 'H-baseline', 'ld_h_idx');
SQL
  measure dead H-baseline ios ld_h ld_h_idx warm "$(set_ios_serial dead)" \
    "SELECT $t count(*) FROM ld_h" "Index Only Scan" Forward 0
  sqlrun dead delete <<'SQL'
DELETE /* wiki_ldfrag_dead */ FROM ld_h WHERE id % 10 <> 0;
SELECT /* wiki_ldfrag_dead */ ldh.put('dead', 'H-after-delete', 'deleted_rows', :'ROW_COUNT');
SELECT /* wiki_ldfrag_dead */ ldh.vis('dead', 'H-after-delete', 'ld_h');
SELECT /* wiki_ldfrag_dead */ ldh.pgsi('dead', 'H-after-delete', 'ld_h_idx');
SELECT /* wiki_ldfrag_dead */ ldh.census('dead', 'H-after-delete', 'ld_h_idx');
SQL
  measure dead H-first ios ld_h ld_h_idx first "$(set_ios_serial dead)" \
    "SELECT $t count(*) FROM ld_h" "Index Only Scan" Forward 0
  sqlrun dead after-first <<'SQL'
SELECT /* wiki_ldfrag_dead */ ldh.vis('dead', 'H-after-first-scan', 'ld_h');
SELECT /* wiki_ldfrag_dead */ ldh.pgsi('dead', 'H-after-first-scan', 'ld_h_idx');
SELECT /* wiki_ldfrag_dead */ ldh.census('dead', 'H-after-first-scan', 'ld_h_idx');
SQL
  measure dead H-steady ios ld_h ld_h_idx warm "$(set_ios_serial dead)" \
    "SELECT $t count(*) FROM ld_h" "Index Only Scan" Forward 0
  sqlrun dead vacuum <<'SQL'
VACUUM /* wiki_ldfrag_dead */ ld_h;
SELECT /* wiki_ldfrag_dead */ ldh.gate('dead', 'H-after-vacuum', 'ld_h');
SELECT /* wiki_ldfrag_dead */ ldh.pgsi('dead', 'H-after-vacuum', 'ld_h_idx');
SELECT /* wiki_ldfrag_dead */ ldh.census('dead', 'H-after-vacuum', 'ld_h_idx');
SQL
  measure dead H-after-vacuum ios ld_h ld_h_idx warm "$(set_ios_serial dead)" \
    "SELECT $t count(*) FROM ld_h" "Index Only Scan" Forward 0
}

# recycle: whole leaf pages emptied by a delete and deleted by VACUUM, then
# placed in the free space map by a second VACUUM once a transaction ID has
# been consumed, then reused by the page splits of a seeded random-order
# refill of the same keys.  Measured at each step: the page classes, the
# sibling-link census, the free-space-map entries and, where the heap is
# all-visible, a warm index-only scan.
stage_recycle() {
  need_server
  clear_stage recycle
  local t="/* wiki_ldfrag_recycle */"
  sqlrun recycle build <<SQL
-- Disposable fixture: creates and drops its own table.
DROP /* wiki_ldfrag_recycle */ TABLE IF EXISTS ld_r;
CREATE /* wiki_ldfrag_recycle */ TABLE ld_r (id bigint);
INSERT /* wiki_ldfrag_recycle */ INTO ld_r SELECT g FROM generate_series(1, $DEAD_ROWS) AS g;
CREATE /* wiki_ldfrag_recycle */ INDEX ld_r_idx ON ld_r (id);
VACUUM /* wiki_ldfrag_recycle */ (ANALYZE) ld_r;
SELECT /* wiki_ldfrag_recycle */ ldh.gate('recycle', 'R-built', 'ld_r');
SELECT /* wiki_ldfrag_recycle */ ldh.pgsi('recycle', 'R-built', 'ld_r_idx');
SELECT /* wiki_ldfrag_recycle */ ldh.census('recycle', 'R-built', 'ld_r_idx');
DELETE /* wiki_ldfrag_recycle */ FROM ld_r WHERE id BETWEEN 50001 AND 150000;
SELECT /* wiki_ldfrag_recycle */ ldh.put('recycle', 'R-deleted', 'deleted_rows', :'ROW_COUNT');
VACUUM /* wiki_ldfrag_recycle */ (ANALYZE) ld_r;
SELECT /* wiki_ldfrag_recycle */ ldh.gate('recycle', 'R-deleted', 'ld_r');
SELECT /* wiki_ldfrag_recycle */ ldh.pgsi('recycle', 'R-deleted', 'ld_r_idx');
SELECT /* wiki_ldfrag_recycle */ ldh.census('recycle', 'R-deleted', 'ld_r_idx');
SELECT /* wiki_ldfrag_recycle */ ldh.put('recycle', 'R-deleted', 'fsm_free_pages', count(*)::text)
  FROM pg_freespace('ld_r_idx') WHERE avail > 0;
SQL
  measure recycle R-deleted ios ld_r ld_r_idx warm "$(set_ios_serial recycle)" \
    "SELECT $t count(*) FROM ld_r" "Index Only Scan" Forward 0
  sqlrun recycle refill <<'SQL'
-- The deleted pages carry the next transaction ID of the moment they were
-- deleted.  Taking one transaction ID moves the removal horizon past it, so
-- the next VACUUM's cleanup scan can hand the pages to the free space map.
SELECT /* wiki_ldfrag_recycle */ pg_current_xact_id();
VACUUM /* wiki_ldfrag_recycle */ ld_r;
SELECT /* wiki_ldfrag_recycle */ ldh.pgsi('recycle', 'R-recyclable', 'ld_r_idx');
SELECT /* wiki_ldfrag_recycle */ ldh.put('recycle', 'R-recyclable', 'fsm_free_pages', count(*)::text)
  FROM pg_freespace('ld_r_idx') WHERE avail > 0;
SELECT /* wiki_ldfrag_recycle */ setseed(0.5);
INSERT /* wiki_ldfrag_recycle */ INTO ld_r SELECT g FROM generate_series(50001, 150000) AS g ORDER BY random();
VACUUM /* wiki_ldfrag_recycle */ (ANALYZE) ld_r;
SELECT /* wiki_ldfrag_recycle */ ldh.gate('recycle', 'R-refilled', 'ld_r');
SELECT /* wiki_ldfrag_recycle */ ldh.pgsi('recycle', 'R-refilled', 'ld_r_idx');
SELECT /* wiki_ldfrag_recycle */ ldh.census('recycle', 'R-refilled', 'ld_r_idx');
SELECT /* wiki_ldfrag_recycle */ ldh.put('recycle', 'R-refilled', 'fsm_free_pages', count(*)::text)
  FROM pg_freespace('ld_r_idx') WHERE avail > 0;
SQL
  measure recycle R-refilled ios ld_r ld_r_idx warm "$(set_ios_serial recycle)" \
    "SELECT $t count(*) FROM ld_r" "Index Only Scan" Forward 0
}

# async: does synchronous_commit = off still keep VACUUM from setting
# visibility-map bits?  P1 repeats the density fixture's recipe with the load
# committed asynchronously; P2 commits a small load asynchronously and runs
# VACUUM at once, ASYNC_TRIALS times, then once after a one-second wait and
# once with a synchronous commit.  The flush LSN is read just before and just
# after each VACUUM, so each result can be attributed.  These fixtures are
# not gated: their visibility is what is being measured.
stage_async() {
  need_server
  clear_stage async
  local t="/* wiki_ldfrag_async */"
  # P1 runs the load and the index build each in an explicit transaction so
  # their transaction IDs can be recorded: the commit log keeps one LSN per
  # group of 32 transaction IDs, so the index build's later asynchronous
  # commit can hold back the load's hint bits even after the load's own
  # commit record is flushed.
  sqlrun async p1 "-c synchronous_commit=off" <<'SQL'
-- Disposable fixture: creates and drops its own table.
DROP /* wiki_ldfrag_async */ TABLE IF EXISTS ld_async;
CREATE /* wiki_ldfrag_async */ TABLE ld_async (id bigint);
BEGIN /* wiki_ldfrag_async */;
INSERT /* wiki_ldfrag_async */ INTO ld_async SELECT g FROM generate_series(1, 1000000) AS g;
SELECT /* wiki_ldfrag_async */ pg_current_xact_id() AS insert_xid \gset
COMMIT /* wiki_ldfrag_async */;
SELECT /* wiki_ldfrag_async */ pg_current_wal_insert_lsn() AS commit_upper, pg_current_wal_flush_lsn() AS flush_after_commit \gset
BEGIN /* wiki_ldfrag_async */;
CREATE /* wiki_ldfrag_async */ INDEX ld_async_idx ON ld_async (id);
SELECT /* wiki_ldfrag_async */ pg_current_xact_id() AS index_xid \gset
COMMIT /* wiki_ldfrag_async */;
SELECT /* wiki_ldfrag_async */ pg_current_wal_insert_lsn() AS index_commit_upper, pg_current_wal_flush_lsn() AS flush_before_vacuum \gset
VACUUM /* wiki_ldfrag_async */ (ANALYZE) ld_async;
SELECT /* wiki_ldfrag_async */ pg_current_wal_flush_lsn() AS flush_after_vacuum \gset
SELECT /* wiki_ldfrag_async */ ldh.put('async', 'P1', 'synchronous_commit', current_setting('synchronous_commit')),
       ldh.put('async', 'P1', 'insert_xid', :'insert_xid'),
       ldh.put('async', 'P1', 'index_xid', :'index_xid'),
       ldh.put('async', 'P1', 'insert_xid_lsn_group', (:'insert_xid'::xid8::text::bigint / 32)::text),
       ldh.put('async', 'P1', 'index_xid_lsn_group', (:'index_xid'::xid8::text::bigint / 32)::text),
       ldh.put('async', 'P1', 'commit_lsn_upper_bound', :'commit_upper'),
       ldh.put('async', 'P1', 'flush_lsn_after_commit', :'flush_after_commit'),
       ldh.put('async', 'P1', 'index_commit_lsn_upper_bound', :'index_commit_upper'),
       ldh.put('async', 'P1', 'flush_lsn_before_vacuum', :'flush_before_vacuum'),
       ldh.put('async', 'P1', 'flush_lsn_after_vacuum', :'flush_after_vacuum'),
       ldh.put('async', 'P1', 'commit_flushed_before_vacuum', (:'flush_before_vacuum'::pg_lsn >= :'commit_upper'::pg_lsn)::text),
       ldh.put('async', 'P1', 'index_commit_flushed_before_vacuum', (:'flush_before_vacuum'::pg_lsn >= :'index_commit_upper'::pg_lsn)::text);
SELECT /* wiki_ldfrag_async */ ldh.vis('async', 'P1', 'ld_async');
SQL
  measure async P1 ios_serial ld_async ld_async_idx warm "$(set_ios_serial async)" \
    "SELECT $t count(*) FROM ld_async" "Index Only Scan" Forward 0
  sqlrun async p1-after <<'SQL'
CHECKPOINT /* wiki_ldfrag_async */;
VACUUM /* wiki_ldfrag_async */ ld_async;
SELECT /* wiki_ldfrag_async */ ldh.gate('async', 'P1-after-checkpoint', 'ld_async');
SQL
  measure async P1-after-checkpoint ios_serial ld_async ld_async_idx warm "$(set_ios_serial async)" \
    "SELECT $t count(*) FROM ld_async" "Index Only Scan" Forward 0
  local i name opts wait
  for i in $(seq 1 "$ASYNC_TRIALS") delayed control; do
    case "$i" in
      delayed) name=P2-delayed; opts="-c synchronous_commit=off"; wait="SELECT $t pg_sleep(1);" ;;
      control) name=P2-control; opts="-c synchronous_commit=on";  wait="" ;;
      *)       name="P2-$i";    opts="-c synchronous_commit=off"; wait="" ;;
    esac
    sqlrun async "$name" "$opts" <<SQL
DROP /* wiki_ldfrag_async */ TABLE IF EXISTS ld_race;
CREATE /* wiki_ldfrag_async */ TABLE ld_race (id bigint);
INSERT /* wiki_ldfrag_async */ INTO ld_race SELECT g FROM generate_series(1, 5000) AS g;
SELECT /* wiki_ldfrag_async */ pg_current_wal_insert_lsn() AS commit_upper \gset
$wait
SELECT /* wiki_ldfrag_async */ pg_current_wal_flush_lsn() AS flush_before_vacuum \gset
VACUUM /* wiki_ldfrag_async */ ld_race;
SELECT /* wiki_ldfrag_async */ pg_current_wal_flush_lsn() AS flush_after_vacuum \gset
SELECT /* wiki_ldfrag_async */ ldh.put('async', '$name', 'synchronous_commit', current_setting('synchronous_commit')),
       ldh.put('async', '$name', 'commit_lsn_upper_bound', :'commit_upper'),
       ldh.put('async', '$name', 'flush_lsn_before_vacuum', :'flush_before_vacuum'),
       ldh.put('async', '$name', 'flush_lsn_after_vacuum', :'flush_after_vacuum'),
       ldh.put('async', '$name', 'commit_flushed_before_vacuum', (:'flush_before_vacuum'::pg_lsn >= :'commit_upper'::pg_lsn)::text);
SELECT /* wiki_ldfrag_async */ ldh.vis('async', '$name', 'ld_race');
SQL
  done
  sqlrun async drop <<'SQL'
DROP /* wiki_ldfrag_async */ TABLE IF EXISTS ld_async, ld_race;
SQL
}

# expect_error STAGE FIXTURE FILE [psql args...]: run FILE, which must fail,
# and record the first ERROR line.  A FILE that succeeds ends the run.
expect_error() {
  local stage="$1" fixture="$2" f="$3"; shift 3
  local err="$f.err" line msg=""
  PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -f "$f" "$@" > "$f.out" 2> "$err"
  local st=$?
  [ "$st" -ne 0 ] || die "$f was expected to fail and succeeded"
  while IFS= read -r line; do
    case "$line" in *ERROR:*) msg="${line#*ERROR:  }"; break ;; esac
  done < "$err"
  [ -n "$msg" ] || die "$f failed without an ERROR line; see $err"
  putv "$stage" "$fixture" error "$msg"
}

# survey: the page's survey statement, run against every kind of index it must
# skip, as a superuser and as an unprivileged role under three grants.
stage_survey() {
  need_server
  clear_stage survey
  local t="/* wiki_ldfrag_survey */"
  # The filed statement.  The page carries exactly this text.
  cat > "$OUT/survey.sql" <<'SQL' || die "cannot write $OUT/survey.sql"
SET /* wiki_leaf_density_vs_fragmentation */ statement_timeout = '10min';
SET /* wiki_leaf_density_vs_fragmentation */ lock_timeout = '5s';

WITH /* wiki_leaf_density_vs_fragmentation */ candidate AS MATERIALIZED (
    SELECT c.oid AS indexrelid,
           n.nspname AS schema_name,
           c.relname AS index_name
      FROM pg_class c
      JOIN pg_index i ON i.indexrelid = c.oid
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_am am ON am.oid = c.relam
     WHERE c.relkind = 'i'
       AND am.amname = 'btree'
       AND c.relpersistence <> 't'
       AND i.indisvalid
       AND n.nspname NOT IN ('pg_catalog', 'information_schema')
       AND n.nspname !~ '^pg_toast'
)
SELECT k.schema_name,
       k.index_name,
       s.index_size / current_setting('block_size')::int AS blocks,
       s.tree_level,
       s.leaf_pages,
       s.empty_pages,
       s.deleted_pages,
       s.avg_leaf_density,
       s.leaf_fragmentation
  FROM candidate k
 CROSS JOIN LATERAL pgstatindex(k.indexrelid::regclass) AS s
 WHERE s.leaf_pages > 0
 ORDER BY s.leaf_fragmentation DESC, s.avg_leaf_density, k.schema_name, k.index_name;
SQL
  local survey v_novalid v_notemp v_notmat
  local pat_valid=$'       AND i.indisvalid\n'
  local pat_temp=$'       AND c.relpersistence <> \'t\'\n'
  local pat_mat='AS MATERIALIZED'
  survey=$(cat "$OUT/survey.sql") || die "cannot read $OUT/survey.sql"
  # Each pattern is a quoted expansion, so it is matched literally.
  v_novalid="${survey/"$pat_valid"/}"
  v_notemp="${survey/"$pat_temp"/}"
  v_notmat="${survey/"$pat_mat"/AS NOT MATERIALIZED}"
  [ "$v_novalid" != "$survey" ] && [ "$v_notemp" != "$survey" ] && [ "$v_notmat" != "$survey" ] \
    || die "could not derive the survey variants"
  printf '%s\n' "$v_novalid" > "$OUT/survey_no_indisvalid.sql"
  printf '%s\n' "$v_notemp" > "$OUT/survey_no_relpersistence.sql"
  printf '%s\n' "$v_notmat" > "$OUT/survey_not_materialized.sql"

  sqlrun survey fixture <<'SQL'
-- Disposable fixture: creates and drops its own schema, tables and role.
DROP /* wiki_ldfrag_survey */ SCHEMA IF EXISTS surv CASCADE;
DROP /* wiki_ldfrag_survey */ ROLE IF EXISTS ld_reader;
CREATE /* wiki_ldfrag_survey */ ROLE ld_reader LOGIN;
CREATE /* wiki_ldfrag_survey */ SCHEMA surv;
CREATE /* wiki_ldfrag_survey */ TABLE surv.mixed (a int, b int[], r int4range, t text);
INSERT /* wiki_ldfrag_survey */ INTO surv.mixed
    SELECT g, ARRAY[g, g + 1], int4range(g, g + 10), 'x' || g FROM generate_series(1, 2000) AS g;
CREATE /* wiki_ldfrag_survey */ INDEX mixed_btree_a ON surv.mixed (a);
CREATE /* wiki_ldfrag_survey */ INDEX mixed_hash ON surv.mixed USING hash (a);
CREATE /* wiki_ldfrag_survey */ INDEX mixed_gin ON surv.mixed USING gin (b);
CREATE /* wiki_ldfrag_survey */ INDEX mixed_gist ON surv.mixed USING gist (r);
CREATE /* wiki_ldfrag_survey */ INDEX mixed_brin ON surv.mixed USING brin (a);
CREATE /* wiki_ldfrag_survey */ INDEX mixed_empty ON surv.mixed (a) WHERE a < 0;
CREATE /* wiki_ldfrag_survey */ TABLE surv.part (a int) PARTITION BY RANGE (a);
CREATE /* wiki_ldfrag_survey */ TABLE surv.part1 PARTITION OF surv.part FOR VALUES FROM (1) TO (100);
INSERT /* wiki_ldfrag_survey */ INTO surv.part SELECT g FROM generate_series(1, 99) AS g;
CREATE /* wiki_ldfrag_survey */ INDEX part_idx ON surv.part (a);
CREATE /* wiki_ldfrag_survey */ UNLOGGED TABLE surv.unlogged (a int PRIMARY KEY);
INSERT /* wiki_ldfrag_survey */ INTO surv.unlogged SELECT g FROM generate_series(1, 1000) AS g;
VACUUM /* wiki_ldfrag_survey */ (ANALYZE) surv.mixed, surv.part1, surv.unlogged;
SQL
  # A unique index built concurrently over duplicate keys fails and leaves an
  # invalid index behind.
  printf 'CREATE /* wiki_ldfrag_survey */ UNIQUE INDEX CONCURRENTLY mixed_invalid ON surv.mixed ((a %% 10));\n' \
    > "$OUT/sql/survey.invalid.sql" || die "cannot write the invalid-index fixture"
  expect_error survey invalid-index-build "$OUT/sql/survey.invalid.sql"
  sqlrun survey catalog <<'SQL'
SELECT /* wiki_ldfrag_survey */ ldh.put('survey', 'fixture', 'relkind_' || c.relname, c.relkind::text || '/' || c.relpersistence::text || '/' || am.amname || '/valid=' || coalesce(i.indisvalid::text, 'n/a'))
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  LEFT JOIN pg_index i ON i.indexrelid = c.oid
  LEFT JOIN pg_am am ON am.oid = c.relam
 WHERE n.nspname = 'surv' AND c.relkind IN ('i', 'I');
SQL
  # Another session owns a temporary B-tree index for the rest of the stage.
  PGOPTIONS="$SESSION_OPTS -c application_name=ldfrag_temp_owner" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 \
    -c "CREATE /* wiki_ldfrag_survey */ TEMP TABLE ld_other_temp (a int PRIMARY KEY)" \
    -c "INSERT /* wiki_ldfrag_survey */ INTO ld_other_temp SELECT g FROM generate_series(1, 1000) AS g" \
    -c "SELECT /* wiki_ldfrag_survey */ pg_sleep(600)" > "$OUT/temp_owner.log" 2>&1 &
  HOLDER_PID=$!
  local n=0 found=""
  while [ "$n" -lt 100 ]; do
    found=$(pgq "SELECT /* wiki_ldfrag_survey */ n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relname = 'ld_other_temp_pkey' AND n.nspname LIKE 'pg_temp%'") \
      || die "cannot look for the other session's temporary index"
    [ -n "$found" ] && break
    kill -0 "$HOLDER_PID" 2> /dev/null || die "the temporary-index session exited early; see $OUT/temp_owner.log"
    sleep 0.2; n=$((n + 1))
  done
  [ -n "$found" ] || die "the other session's temporary index never appeared"
  putv survey fixture other_session_temp_index "$found"

  # 1. The filed statement, as a superuser, from a session that owns its own
  #    temporary B-tree index.
  {
    printf 'CREATE /* wiki_ldfrag_survey */ TEMP TABLE ld_own_temp (a int PRIMARY KEY);\n'
    printf 'INSERT /* wiki_ldfrag_survey */ INTO ld_own_temp SELECT g FROM generate_series(1, 1000) AS g;\n'
    printf "SELECT /* wiki_ldfrag_survey */ ldh.put('survey', 'own-temp', 'avg_leaf_density', s.avg_leaf_density::text), ldh.put('survey', 'own-temp', 'leaf_pages', s.leaf_pages::text) FROM pgstatindex('ld_own_temp_pkey') AS s;\n"
    printf '\\o %s\n' "$OUT/survey_superuser.txt"
    printf '\\i %s\n' "$OUT/survey.sql"
    printf '\\o\n'
    printf "SELECT /* wiki_ldfrag_survey */ ldh.put('survey', 'superuser', 'rows', :'ROW_COUNT');\n"
  } > "$OUT/sql/survey.superuser.sql" || die "cannot write the superuser run"
  pgf "$OUT/sql/survey.superuser.sql" "$OUT/survey.out"

  # 2. The same statement without indisvalid, without the relpersistence
  #    filter, and with NOT MATERIALIZED.
  expect_error survey no-indisvalid "$OUT/survey_no_indisvalid.sql"
  expect_error survey no-relpersistence "$OUT/survey_no_relpersistence.sql"
  {
    printf '\\o %s\n' "$OUT/survey_not_materialized.txt"
    printf '\\i %s\n' "$OUT/survey_not_materialized.sql"
    printf '\\o\n'
    printf "SELECT /* wiki_ldfrag_survey */ ldh.put('survey', 'not-materialized', 'rows', :'ROW_COUNT');\n"
  } > "$OUT/sql/survey.notmat.sql" || die "cannot write the NOT MATERIALIZED run"
  if PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -f "$OUT/sql/survey.notmat.sql" \
       > "$OUT/sql/survey.notmat.sql.out" 2> "$OUT/sql/survey.notmat.sql.err"; then
    putv survey not-materialized outcome succeeded
  else
    putv survey not-materialized outcome failed
    expect_error survey not-materialized "$OUT/survey_not_materialized.sql"
  fi
  # The two plans, so the page can show where each filter is applied.  The
  # query text starts after the first blank line, below the two SETs.
  local plan text
  for plan in survey survey_not_materialized; do
    text=$(cat "$OUT/$plan.sql") || die "cannot read $OUT/$plan.sql"
    {
      printf "SET /* wiki_ldfrag_survey */ statement_timeout = '10min';\n"
      printf 'EXPLAIN /* wiki_ldfrag_survey */ (COSTS OFF) %s\n' "${text#*$'\n'$'\n'}"
    } > "$OUT/sql/survey.explain.$plan.sql" || die "cannot write the EXPLAIN of $plan"
    pgf "$OUT/sql/survey.explain.$plan.sql" "$OUT/survey_plan_$plan.txt"
  done

  # 3. The other session's temporary index, the partitioned parent and the
  #    hash index, each handed to pgstatindex directly.
  printf "SELECT /* wiki_ldfrag_survey */ * FROM pgstatindex('%s');\n" "$found" > "$OUT/sql/survey.othertemp.sql"
  expect_error survey direct-other-session-temp "$OUT/sql/survey.othertemp.sql"
  printf "SELECT /* wiki_ldfrag_survey */ * FROM pgstatindex('surv.part_idx');\n" > "$OUT/sql/survey.parted.sql"
  expect_error survey direct-partitioned-index "$OUT/sql/survey.parted.sql"
  printf "SELECT /* wiki_ldfrag_survey */ * FROM pgstatindex('surv.mixed_hash');\n" > "$OUT/sql/survey.hash.sql"
  expect_error survey direct-hash-index "$OUT/sql/survey.hash.sql"
  printf "SELECT /* wiki_ldfrag_survey */ * FROM pgstatindex('surv.mixed_invalid');\n" > "$OUT/sql/survey.invalid-direct.sql"
  expect_error survey direct-invalid-index "$OUT/sql/survey.invalid-direct.sql"

  # 4. Privileges.  ld_reader has no SELECT on any fixture table.
  sqlrun survey privs <<'SQL'
SELECT /* wiki_ldfrag_survey */ ldh.put('survey', 'ld_reader', 'select_on_ld_a90', has_table_privilege('ld_reader', 'ld_a90', 'SELECT')::text),
       ldh.put('survey', 'ld_reader', 'execute_pgstatindex_before', has_function_privilege('ld_reader', 'pgstatindex(regclass)', 'EXECUTE')::text),
       ldh.put('survey', 'ld_reader', 'public_execute', (SELECT coalesce(bool_or(a.grantee = 0), false)::text
           FROM pg_proc p, aclexplode(p.proacl) AS a WHERE p.oid = 'pgstatindex(regclass)'::regprocedure));
SQL
  expect_error survey reader-no-grant "$OUT/survey.sql" -U ld_reader
  local how rows l
  for how in role direct; do
    if [ "$how" = role ]; then
      pgq "GRANT /* wiki_ldfrag_survey */ pg_stat_scan_tables TO ld_reader" > /dev/null || die "grant failed"
    else
      pgq "GRANT /* wiki_ldfrag_survey */ EXECUTE ON FUNCTION pgstatindex(regclass) TO ld_reader" > /dev/null || die "grant failed"
    fi
    # ld_reader cannot write to the harness, so its rows are counted here.
    PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -At -v ON_ERROR_STOP=1 -U ld_reader -f "$OUT/survey.sql" \
      > "$OUT/survey_reader_$how.txt" 2> "$OUT/survey_reader_$how.err" \
      || die "the survey failed for ld_reader with the $how grant; see $OUT/survey_reader_$how.err"
    rows=0
    while IFS= read -r l; do [ -n "$l" ] && rows=$((rows + 1)); done < "$OUT/survey_reader_$how.txt"
    putv survey "reader-$how" rows "$rows"
    if [ "$how" = role ]; then
      pgq "REVOKE /* wiki_ldfrag_survey */ pg_stat_scan_tables FROM ld_reader" > /dev/null || die "revoke failed"
    else
      pgq "REVOKE /* wiki_ldfrag_survey */ EXECUTE ON FUNCTION pgstatindex(regclass) FROM ld_reader" > /dev/null || die "revoke failed"
    fi
  done
  stop_holder
}

# model: the page's arithmetic, evaluated here so the tables cannot drift from
# the formulas, and the measured fixtures placed in them.
stage_model() {
  need_server
  sqlrun model tables <<'SQL'
DELETE /* wiki_ldfrag_model */ FROM ldh.model;
-- Leaf pages against a 90 % baseline, for the same live index tuples.
INSERT /* wiki_ldfrag_model */ INTO ldh.model
SELECT 'density', d::text, 'multiplier', round(90.0 / d, 2) FROM unnest(ARRAY[95, 90, 80, 70, 60, 50, 40, 30]) AS d
UNION ALL
SELECT 'density', d::text, 'extra_pct', round((90.0 / d - 1) * 100, 1) FROM unnest(ARRAY[95, 90, 80, 70, 60, 50, 40, 30]) AS d;
-- Order-cost multiplier 1 + N * (R/S - 1).
INSERT /* wiki_ldfrag_model */ INTO ldh.model
SELECT 'order', n::text, 'rs=' || rs::text, round(1 + n / 100.0 * (rs - 1), 2)
  FROM unnest(ARRAY[0, 10, 25, 50, 75, 100]) AS n, unnest(ARRAY[1.0, 1.2, 4.0]) AS rs;
-- Combined (0.90 / density) * (1 + N * (R/S - 1)).
INSERT /* wiki_ldfrag_model */ INTO ldh.model
SELECT 'combined rs=' || rs::text, d::text, n::text, round((0.90 / (d / 100.0)) * (1 + n / 100.0 * (rs - 1)), 2)
  FROM unnest(ARRAY[90, 80, 70, 60, 50, 40]) AS d, unnest(ARRAY[0, 25, 50, 75, 100]) AS n, unnest(ARRAY[4.0, 1.2]) AS rs;
-- The ladder: predicted leaf-page multiplier from density against the
-- measured one, both relative to the fillfactor-90 build.
INSERT /* wiki_ldfrag_model */ INTO ldh.model
SELECT 'ladder', f.fixture, 'predicted_multiplier',
       round(ldh.get('ladder', 'ff90', 'avg_leaf_density')::numeric / f.value::numeric, 4)
  FROM ldh.fact f WHERE f.stage = 'ladder' AND f.metric = 'avg_leaf_density'
UNION ALL
SELECT 'ladder', f.fixture, 'measured_leaf_multiplier',
       round(f.value::numeric / ldh.get('ladder', 'ff90', 'leaf_pages')::numeric, 4)
  FROM ldh.fact f WHERE f.stage = 'ladder' AND f.metric = 'leaf_pages'
UNION ALL
SELECT 'ladder', f.fixture, 'measured_index_block_multiplier',
       round(f.value::numeric / ldh.get('ladder', 'ff90', 'ios_serial.idx_blks_hit')::numeric, 4)
  FROM ldh.fact f WHERE f.stage = 'ladder' AND f.metric = 'ios_serial.idx_blks_hit';
-- The closed form for a serial and a two-worker parallel index-only
-- count(*) over every key, against the Index Only Scan node cost EXPLAIN
-- recorded: index pages * random_page_cost + tuples * cpu_index_tuple_cost
-- + ceil(log2(tuples)) * cpu_operator_cost
-- + (tree height + 1) * 50 * cpu_operator_cost, plus tuples * cpu_tuple_cost
-- divided by the parallel divisor (1 serial; 2 + (1 - 0.3 * 2) = 2.4 with two
-- workers).  Heap I/O is zero because every heap page is all-visible.
INSERT /* wiki_ldfrag_model */ INTO ldh.model
SELECT 'costcheck', x.stage || '/' || x.fixture, w.shape,
       round(p.relpages * current_setting('random_page_cost')::numeric
             + 1000000 * current_setting('cpu_index_tuple_cost')::numeric
             + ceil(ln(1000000::numeric) / ln(2::numeric)) * current_setting('cpu_operator_cost')::numeric
             + (p.fastlevel + 1) * 50 * current_setting('cpu_operator_cost')::numeric
             + 1000000 * current_setting('cpu_tuple_cost')::numeric / w.divisor, 3)
  FROM (VALUES ('density', 'A90'), ('density', 'A60'), ('frag', 'C-fragmented'), ('frag', 'C-rebuilt')) AS x(stage, fixture)
 CROSS JOIN LATERAL (SELECT ldh.get(x.stage, x.fixture, 'index_relpages')::numeric AS relpages,
                            ldh.get(x.stage, x.fixture, 'metap_fastlevel')::numeric AS fastlevel) AS p
 CROSS JOIN (VALUES ('predicted_serial', 1.0), ('predicted_parallel', 2.4)) AS w(shape, divisor)
UNION ALL
SELECT 'costcheck', x.stage || '/' || x.fixture, 'recorded_' || w.shape,
       ldh.get(x.stage, x.fixture, w.shape || '.scan_total_cost')::numeric
  FROM (VALUES ('density', 'A90'), ('density', 'A60'), ('frag', 'C-fragmented'), ('frag', 'C-rebuilt')) AS x(stage, fixture)
 CROSS JOIN (VALUES ('ios_serial'), ('ios_parallel')) AS w(shape);
-- The measured fragmented index, placed in the combined model.
INSERT /* wiki_ldfrag_model */ INTO ldh.model
SELECT 'placement', 'C-fragmented', 'rs=' || rs::text,
       round((0.90 / (ldh.get('frag', 'C-fragmented', 'avg_leaf_density')::numeric / 100))
             * (1 + ldh.get('frag', 'C-fragmented', 'census_N_pct')::numeric / 100 * (rs - 1)), 2)
  FROM unnest(ARRAY[1.0, 1.2, 4.0]) AS rs
UNION ALL
SELECT 'placement', 'C-fragmented', 'page_term_only',
       round(0.90 / (ldh.get('frag', 'C-fragmented', 'avg_leaf_density')::numeric / 100), 2);
SQL
}

# summary: platform facts, every recorded value, every model value, the plans
# and the survey outputs, in one file.
stage_summary() {
  need_server
  clear_stage platform
  local line align
  line=$("$BIN/pg_controldata" -D "$DATA" 2>/dev/null | grep 'Maximum data alignment') \
    || die "pg_controldata failed"
  align="${line##*:}"; align="${align// /}"
  putv platform host uname "$(uname -srm)"
  putv platform host bash "$BASH_VERSION"
  putv platform host max_data_alignment "$align"
  putv platform host pin "$PIN"
  putv platform host install_pin "$(cat "$INST/$PINFILE")"
  putv platform host checkout_head "$(git -C "$SRC" rev-parse HEAD)"
  sqlrun summary platform <<'SQL'
SELECT /* wiki_ldfrag_summary */ ldh.put('platform', 'server', 'version', version());
SELECT /* wiki_ldfrag_summary */ ldh.put('platform', 'server', s.name, s.setting || coalesce(' ' || s.unit, '') || ' [' || s.context || ']')
  FROM pg_settings AS s
 WHERE s.name IN ('block_size', 'shared_buffers', 'autovacuum', 'synchronous_commit',
                  'max_parallel_workers_per_gather', 'max_parallel_workers', 'max_worker_processes',
                  'max_parallel_maintenance_workers', 'parallel_leader_participation',
                  'effective_io_concurrency', 'maintenance_io_concurrency', 'io_combine_limit',
                  'seq_page_cost', 'random_page_cost', 'cpu_tuple_cost', 'cpu_index_tuple_cost',
                  'cpu_operator_cost', 'effective_cache_size', 'data_checksums', 'wal_level',
                  'wal_writer_delay', 'wal_writer_flush_after', 'jit', 'default_statistics_target',
                  'maintenance_work_mem', 'work_mem', 'track_io_timing', 'stats_fetch_consistency');
SQL
  local s f
  f="$OUT/summary.txt"
  {
    printf 'ldfrag.sh summary, written %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf '\n== test suites\n'
    for s in check-core check-pgstattuple check-pageinspect check-pg_visibility check-pg_freespacemap; do
      if [ -f "$OUT/$s.log" ]; then
        printf '%s: ' "$s"; grep -E 'tests passed|tests failed|failed \(' "$OUT/$s.log" | tail -1
      else
        printf '%s: not run\n' "$s"
      fi
    done
  } > "$f" || die "cannot write $f"
  PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -v ON_ERROR_STOP=1 >> "$f" 2>&1 <<'SQL' || die "summary queries failed"
\pset footer off
CREATE /* wiki_ldfrag_summary */ TEMP VIEW v AS
SELECT stage, fixture, metric, value FROM ldh.fact;
\echo
\echo == table: the four summary shapes (serial warm index-only count(*))
SELECT /* wiki_ldfrag_summary */ f.stage, f.fixture,
       max(value) FILTER (WHERE metric = 'leaf_pages') AS leaf_pages,
       max(value) FILTER (WHERE metric = 'avg_leaf_density') AS avg_leaf_density,
       max(value) FILTER (WHERE metric = 'leaf_fragmentation') AS leaf_fragmentation,
       max(value) FILTER (WHERE metric = 'index_relpages') AS index_relpages,
       max(value) FILTER (WHERE metric = 'ios_serial.plan_buffers_hit') AS plan_buffers,
       max(value) FILTER (WHERE metric = 'ios_serial.idx_blks_hit') AS index_blocks,
       max(value) FILTER (WHERE metric = 'ios_serial.heap_blks_hit') AS heap_blocks,
       max(value) FILTER (WHERE metric = 'ios_serial.scan_total_cost') AS ios_node_cost
  FROM v f WHERE (f.stage, f.fixture) IN (('density', 'A90'), ('density', 'A60'), ('frag', 'C-fragmented'), ('frag', 'C-rebuilt'))
 GROUP BY f.stage, f.fixture ORDER BY f.stage, f.fixture DESC;
\echo
\echo == table: density pair, serial and parallel
SELECT /* wiki_ldfrag_summary */ fixture,
       max(value) FILTER (WHERE metric = 'internal_pages') AS internal_pages,
       max(value) FILTER (WHERE metric = 'tree_level') AS tree_level,
       max(value) FILTER (WHERE metric = 'ios_serial.top_total_cost') AS serial_total,
       max(value) FILTER (WHERE metric = 'ios_parallel.plan_buffers_hit') AS par_buffers,
       max(value) FILTER (WHERE metric = 'ios_parallel.idx_blks_hit') AS par_index_blocks,
       max(value) FILTER (WHERE metric = 'ios_parallel.heap_blks_hit') AS par_heap_blocks,
       max(value) FILTER (WHERE metric = 'ios_parallel.scan_total_cost') AS par_node_cost,
       max(value) FILTER (WHERE metric = 'ios_parallel.top_total_cost') AS par_total,
       max(value) FILTER (WHERE metric = 'ios_parallel.workers_launched') AS workers
  FROM v WHERE stage = 'density' GROUP BY fixture ORDER BY fixture DESC;
\echo
\echo == table: fillfactor ladder
SELECT /* wiki_ldfrag_summary */ fixture,
       max(value) FILTER (WHERE metric = 'leaf_pages') AS leaf_pages,
       max(value) FILTER (WHERE metric = 'avg_leaf_density') AS density,
       max(value) FILTER (WHERE metric = 'internal_pages') AS internal,
       max(value) FILTER (WHERE metric = 'tree_level') AS level,
       max(value) FILTER (WHERE metric = 'index_relpages') AS relpages,
       max(value) FILTER (WHERE metric = 'ios_serial.plan_buffers_hit') AS plan_buffers,
       max(value) FILTER (WHERE metric = 'ios_serial.idx_blks_hit') AS index_blocks,
       max(value) FILTER (WHERE metric = 'ios_serial.scan_total_cost') AS node_cost
  FROM v WHERE stage = 'ladder' GROUP BY fixture ORDER BY substr(fixture, 3)::int DESC;
\echo
\echo == table: scan shapes (plan buffers / index blocks / heap blocks / node cost)
SELECT /* wiki_ldfrag_summary */ stage, fixture, split_part(metric, '.', 1) AS shape,
       max(value) FILTER (WHERE metric LIKE '%.plan_buffers_hit') AS plan_buffers,
       max(value) FILTER (WHERE metric LIKE '%.scan_buffers_hit') AS scan_node_buffers,
       max(value) FILTER (WHERE metric LIKE '%.idx_blks_hit') AS index_blocks,
       max(value) FILTER (WHERE metric LIKE '%.heap_blks_hit') AS heap_blocks,
       max(value) FILTER (WHERE metric LIKE '%.scan_total_cost') AS node_cost,
       max(value) FILTER (WHERE metric LIKE '%.scan_rows_per_loop') AS rows_per_loop
  FROM v WHERE stage IN ('scans', 'frag', 'desc') AND metric LIKE '%.%'
 GROUP BY stage, fixture, split_part(metric, '.', 1) ORDER BY stage, fixture, shape;
\echo
\echo == table: sibling-link census
SELECT /* wiki_ldfrag_summary */ stage, fixture,
       max(value) FILTER (WHERE metric = 'census_leaf_pages') AS leaf,
       max(value) FILTER (WHERE metric = 'census_forward_links') AS fwd_links,
       max(value) FILTER (WHERE metric = 'census_backward_links') AS backward,
       max(value) FILTER (WHERE metric = 'census_adjacent_links') AS to_next,
       max(value) FILTER (WHERE metric = 'census_nonadjacent_links') AS not_next,
       max(value) FILTER (WHERE metric = 'census_forward_jumps') AS fwd_jumps,
       max(value) FILTER (WHERE metric = 'census_N_pct') AS n_pct,
       max(value) FILTER (WHERE metric = 'census_mean_abs_jump') AS mean_jump,
       max(value) FILTER (WHERE metric = 'census_max_abs_jump') AS max_jump,
       max(value) FILTER (WHERE metric = 'leaf_fragmentation') AS leaf_frag,
       max(value) FILTER (WHERE metric = 'census_internal_pages') AS internal,
       max(value) FILTER (WHERE metric = 'census_deleted_pages') AS deleted,
       max(value) FILTER (WHERE metric = 'census_leaf_dead_items') AS dead_items,
       max(value) FILTER (WHERE metric = 'census_right_to_prev_block') AS right_minus1,
       max(value) FILTER (WHERE metric = 'census_left_to_next_block') AS left_plus1,
       max(value) FILTER (WHERE metric = 'census_left_to_prev_block') AS left_minus1,
       max(value) FILTER (WHERE metric = 'census_mean_abs_left_jump') AS mean_left_jump
  FROM v WHERE metric LIKE 'census_%' OR metric = 'leaf_fragmentation'
 GROUP BY stage, fixture HAVING max(value) FILTER (WHERE metric = 'census_leaf_pages') IS NOT NULL
 ORDER BY stage, fixture;
\echo
\echo == table: dead space and recycling
SELECT /* wiki_ldfrag_summary */ stage, fixture,
       max(value) FILTER (WHERE metric = 'deleted_rows') AS deleted_rows,
       max(value) FILTER (WHERE metric = 'leaf_pages') AS leaf,
       max(value) FILTER (WHERE metric = 'deleted_pages') AS deleted_pages,
       max(value) FILTER (WHERE metric = 'avg_leaf_density') AS density,
       max(value) FILTER (WHERE metric = 'index_relpages') AS relpages,
       max(value) FILTER (WHERE metric = 'fsm_free_pages') AS fsm_free,
       max(value) FILTER (WHERE metric = 'heap_relallvisible') AS relallvisible,
       max(value) FILTER (WHERE metric = 'vm_all_visible') AS vm_all_visible,
       max(value) FILTER (WHERE metric = 'ios.plan_buffers_hit') AS plan_buffers,
       max(value) FILTER (WHERE metric = 'ios.plan_buffers_dirtied') AS dirtied,
       max(value) FILTER (WHERE metric = 'ios.idx_blks_hit') AS index_blocks,
       max(value) FILTER (WHERE metric = 'ios.heap_blks_hit') AS heap_blocks,
       max(value) FILTER (WHERE metric = 'ios.heap_fetches') AS heap_fetches,
       max(value) FILTER (WHERE metric = 'ios.scan_rows_per_loop') AS rows,
       max(value) FILTER (WHERE metric = 'ios.scan_total_cost') AS node_cost
  FROM v WHERE stage IN ('dead', 'recycle')
 GROUP BY stage, fixture ORDER BY stage, min(fixture);
\echo
\echo == table: synchronous_commit probe
SELECT /* wiki_ldfrag_summary */ fixture,
       max(value) FILTER (WHERE metric = 'synchronous_commit') AS sync_commit,
       max(value) FILTER (WHERE metric = 'commit_lsn_upper_bound') AS commit_upper,
       max(value) FILTER (WHERE metric = 'flush_lsn_before_vacuum') AS flush_before,
       max(value) FILTER (WHERE metric = 'flush_lsn_after_vacuum') AS flush_after,
       max(value) FILTER (WHERE metric = 'commit_flushed_before_vacuum') AS flushed,
       max(value) FILTER (WHERE metric = 'insert_xid') AS insert_xid,
       max(value) FILTER (WHERE metric = 'index_xid') AS index_xid,
       max(value) FILTER (WHERE metric = 'index_commit_lsn_upper_bound') AS index_commit_upper,
       max(value) FILTER (WHERE metric = 'index_commit_flushed_before_vacuum') AS index_flushed,
       max(value) FILTER (WHERE metric = 'heap_blocks') AS heap_blocks,
       max(value) FILTER (WHERE metric = 'heap_relallvisible') AS relallvisible,
       max(value) FILTER (WHERE metric = 'vm_all_visible') AS vm_all_visible,
       max(value) FILTER (WHERE metric = 'ios_serial.plan_buffers_hit') AS plan_buffers,
       max(value) FILTER (WHERE metric = 'ios_serial.heap_fetches') AS heap_fetches
  FROM v WHERE stage = 'async' GROUP BY fixture ORDER BY min(fixture);
\echo
\echo == recorded values (stage, fixture, metric, value), in recording order
SELECT /* wiki_ldfrag_summary */ stage, fixture, metric, value
  FROM ldh.fact ORDER BY recorded_at, stage, fixture, metric;
\echo
\echo == model values
SELECT /* wiki_ldfrag_summary */ kind, row_key, col_key, value
  FROM ldh.model ORDER BY kind, row_key, col_key;
\echo
\echo == plans (text rendering of the recorded JSON: node, index, direction, costs, buffers)
SELECT /* wiki_ldfrag_summary */ p.stage, p.fixture, p.label,
       n ->> 'Node Type' AS node, n ->> 'Index Name' AS index, n ->> 'Scan Direction' AS dir,
       n ->> 'Startup Cost' AS startup, n ->> 'Total Cost' AS total,
       n ->> 'Shared Hit Blocks' AS hit, n ->> 'Shared Read Blocks' AS read,
       n ->> 'Shared Dirtied Blocks' AS dirtied, n ->> 'Heap Fetches' AS heap_fetches,
       n ->> 'Workers Launched' AS workers, n ->> 'Actual Rows' AS rows_per_loop, n ->> 'Actual Loops' AS loops
  FROM ldh.plan p, jsonb_path_query(p.plan, 'strict $.** ? (exists (@."Node Type"))') AS n
 ORDER BY p.recorded_at, p.stage, p.fixture, p.label;
SQL
  {
    for s in survey_superuser survey_not_materialized survey_reader_role survey_reader_direct \
             survey_plan_survey survey_plan_survey_not_materialized; do
      printf '\n== %s\n' "$s"
      if [ -f "$OUT/$s.txt" ]; then cat "$OUT/$s.txt"; else printf 'not produced\n'; fi
    done
    printf '\n== server log ERROR lines\n'
    grep -c 'ERROR:' "$OUT/server.log" || true
  } >> "$f" || die "cannot write $f"
  note "wrote $f"
}

stage_stop() {
  own_sandbox || return 0
  stop_server
  assert_stopped
}

stage_clean() {
  own_sandbox || return 0
  stop_server
  assert_stopped
  rm -rf "$SANDBOX" || die "could not delete $SANDBOX"
  SANDBOX_OK=0
  note "deleted $SANDBOX"
}

run_stage() {
  CURRENT_STAGE="$1"
  say "stage $1"
  "stage_$1" || die "stage $1 failed"
}

main() {
  local stages s k ok
  if [ $# -eq 0 ]; then stages="$DEFAULT_STAGES"; else stages="$*"; fi
  for s in $stages; do
    ok=0
    for k in $KNOWN_STAGES; do [ "$s" = "$k" ] && ok=1; done
    [ "$ok" = 1 ] || die "unknown stage '$s'; known stages: $KNOWN_STAGES"
  done
  for s in $stages; do run_stage "$s"; done
}

main "$@"
```

## Context Reviewed

- Required wiki navigation: [versions](../../../versions.md), [wiki index](../../../index.md), [v17/index](../../index.md), the recent [log](../../../log.md), and the [Wiki Glossary (unverified)](../../../glossary.md) entries for the terms this page uses.
- Common concept pages for v17: [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md), read for its fixture rules, which this page's dead-space fixture deliberately does not follow because it scores no bloat estimator. The GIN and non-B-tree test pages cover other access methods. No concept page covers leaf density, sibling links or the visibility map, so those are explained inline.
- The PostgreSQL 12 page for the same question was read for its structure only; no claim here rests on it.
- `pgstattuple` and `pageinspect`: `contrib/pgstattuple/pgstatindex.c`, `pgstattuple--1.4--1.5.sql`, `pgstattuple.control`, `sql/pgstattuple.sql`, `expected/pgstattuple.out`, `doc/src/sgml/pgstattuple.sgml`, `contrib/pageinspect/btreefuncs.c`, `pageinspect--1.11--1.12.sql`, `sql/btree.sql`.
- B-tree access method: `nbtree.h`, `nbtsearch.c`, `nbtinsert.c`, `nbtsplitloc.c`, `nbtdedup.c`, `nbtsort.c`, `nbtpage.c`, `nbtutils.c`, `nbtree.c`, `src/backend/access/nbtree/README`.
- Planner: `plancat.c`, `selfuncs.c`, `costsize.c`, `allpaths.c`, `tableam.c`, `spccache.c`, `cost.h`.
- Executor, buffers and statistics: `nodeIndexonlyscan.c`, `execnodes.h`, `indexam.c`, `heapam_handler.c`, `explain.c`, `instrument.h`, `bufmgr.c`, `bufmgr.h`, `localbuf.c`, `read_stream.c`, `visibilitymap.c`, `pgstat.h`, `pgstat.c`, `pgstatfuncs.c`, `system_views.sql`.
- Every `PrefetchBuffer`, `PrefetchSharedBuffer`, `PrefetchLocalBuffer`, `smgrprefetch` and `read_stream_begin_relation` call in `src/` and `contrib/`: `nodeBitmapHeapscan.c`, `heapam.c`, `vacuumlazy.c`, `xlogprefetcher.c`, `analyze.c`, `pg_prewarm.c`, plus `pg_config_manual.h` and `variable.c` for `USE_PREFETCH`.
- Visibility and commit: `heapam_visibility.c`, `pruneheap.c`, `heapam.c`, `xact.c`, `xlog.c`, `clog.c`, `transam.c`, `vacuum.c`, `index.c`, `rel.h`, `indexfsm.c`.
- Settings and docs: `guc_tables.c`, `config.sgml`, `maintenance.sgml`, `ref/create_index.sgml`, `ref/reindex.sgml`, `queries.sgml`; tests `src/test/regress/sql/btree_index.sql`.
- History in this checkout: commit `3f0b994cf3` for the `random_page_cost` documentation rewrite, and commit `13503eb590` for the `indisvalid` check, each placed against the `Stamp 17.N.` commits by ancestry, because this clone has no release tags.
- Exact-pin execution: one full run of the published script from an empty sandbox, described under [Last run](#last-run).

## Evidence Map

| Claim | Evidence |
|---|---|
| `avg_leaf_density` is 100 minus summed `PageGetFreeSpace` over summed usable space of live leaves, `NaN` with none | [pgstatindex.c#leaf-page-accounting](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L308-L316), [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L367), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L898-L923) |
| `leaf_fragmentation` counts only backward right links of live leaves | [pgstatindex.c#fragmentation-count](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323), [pgstatindex.c#leaf_fragmentation](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L368-L372) |
| `pgstatindex` reads every block under `BAS_BULKREAD` and rejects non-B-tree, other-session temporary and invalid indexes | [pgstatindex.c:222](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L222), [pgstatindex.c#full-block-scan](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L278-L331), [pgstatindex.c#relation-checks](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L250) |
| Fillfactors 90, 70 and 96, the build threshold, and the split rules including `SPLIT_SINGLE_VALUE` | [nbtree.h#fillfactor](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202), [nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L645-L671), [nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L335), [nbtsplitloc.c#split-strategy-overrides](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L397-L416), [nbtdedup.c#_bt_singleval_fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L821-L842) |
| The planner prices the whole main fork at `random_page_cost` per page, never order | [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L463-L501), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6737), [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6787) |
| The descent charge and the undivided index charge in parallel plans | [selfuncs.c#btcostestimate-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7106), [costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L806-L815), [costsize.c#get_parallel_divisor](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L6375-L6405) |
| Scans walk one leaf per step; backward plain scans re-read the current leaf; index-only scans keep the pin | [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2191-L2243), [nbtsearch.c#_bt_readnextpage-backward](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2244-L2335), [nbtsearch.c#_bt_drop_lock_and_maybe_pin](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L51-L72), [README#concurrent-tid-recycling](../../../../raw/postgres-17/src/backend/access/nbtree/README#L443-L470) |
| No B-tree scan path prefetches or stream-reads; the full list of prefetch and read-stream sites | [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1248-L1263), [nodeBitmapHeapscan.c:500](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L500), [nodeBitmapHeapscan.c:551](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L551), [heapam.c:8416](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8416), [vacuumlazy.c:2758](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2758), [xlogprefetcher.c:769](../../../../raw/postgres-17/src/backend/access/transam/xlogprefetcher.c#L769), [pg_prewarm.c:227](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L227), [heapam.c:1252](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1252), [analyze.c:1199](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1199), [pg_prewarm.c:263](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L263) |
| `EXPLAIN` buffers have no relation split; the per-relation counters do, with visibility-map reads on the heap | [instrument.h#BufferUsage](../../../../raw/postgres-17/src/include/executor/instrument.h#L24-L42), [bufmgr.c#PinBufferForBlock-counting](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1161-L1171), [visibilitymap.c#vm_readbuf](../../../../raw/postgres-17/src/backend/access/heap/visibilitymap.c#L616-L625) |
| Splits allocate through `_bt_allocbuf`, which reuses free-space-map pages or extends by one page | [nbtinsert.c#_bt_split-allocate-right-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1707-L1724), [nbtinsert.c#_bt_split-sibling-links](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1726-L1746), [nbtpage.c#_bt_allocbuf-fsm-reuse](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L877-L969), [nbtpage.c#_bt_allocbuf-extend](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L971-L987) |
| In-place recovery before a split: simple deletion, bottom-up deletion, deduplication | [nbtinsert.c#_bt_findinsertloc-delete-or-dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L899-L906), [nbtinsert.c#simple-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2702-L2733), [nbtinsert.c#bottom-up-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2776), [nbtinsert.c#deduplication](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2778-L2781) |
| `VACUUM` feeds the free space map only for pages already safe to recycle | [nbtree.c#btvacuumpage-recycle](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1165-L1171), [nbtpage.c#_bt_pendingfsm_finalize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2995-L3055), [nbtree.h#BTPageIsRecyclable](../../../../raw/postgres-17/src/include/access/nbtree.h#L279-L318), [nbtree.c#btvacuumscan-fsm-vacuum](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1048-L1059) |
| `LP_DEAD` marks free no space; the heap delete clears visibility bits that the catalog does not track until `VACUUM` | [nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4312-L4342), [heapam.c#heap_delete-clear-vm](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L3121-L3146), [vacuum.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1444-L1461) |
| Asynchronous commit keeps hint bits, and so visibility-map bits, off until the group's commit LSN is flushed | [heapam_visibility.c#SetHintBits](../../../../raw/postgres-17/src/backend/access/heap/heapam_visibility.c#L82-L132), [pruneheap.c#heap_prune_record_unchanged_lp_normal-all-visible](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1363-L1387), [clog.c#group-lsn-update](../../../../raw/postgres-17/src/backend/access/transam/clog.c#L702-L716), [xact.c#RecordTransactionCommit-async](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L1487-L1521) |
| The 17.11 docs: durable-storage and cached readings, no SSD value | [config.sgml#random_page_cost-durable-storage](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5875-L5882), [config.sgml#random_page_cost-guidance](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5884-L5894), [config.sgml#random_page_cost-cached](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5896-L5907), commit `3f0b994cf3` |
| Survey filters mirror `pgstatindex`'s rules; the privilege model | [pgstatindex.c#relkind-am-macros](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L70-L71), [rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/src/include/utils/rel.h#L667-L669), [pgstattuple--1.4--1.5.sql#pgstatindex-grants](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92), [queries.sgml#with-materialization](../../../../raw/postgres-17/doc/src/sgml/queries.sgml#L2520-L2535) |
| Tests cover empty-index `NaN` and error paths, not I/O | [pgstattuple.sql#empty-relations](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L1-L37), [pgstattuple.out#empty-index-NaN](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L44-L52), [btree.sql#bt_multi_page_stats](../../../../raw/postgres-17/contrib/pageinspect/sql/btree.sql#L1-L23), [btree_index.sql#page-deletion-and-recycling](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L252-L270) |
| Measured: density moves buffer counts and cost by the page count; order moves neither | [Exact-pin measurements](#exact-pin-measurements), from the published script |

## Open Questions

- **Cold storage was not measured.** Every buffer count here is a warm-cache access. The order-cost and combined tables are sensitivity models, and no elapsed-time claim about cold, seek-sensitive storage is measured. The host that ran the script is macOS, whose kernel cache cannot be dropped without root, which this wiki's isolation rules forbid, and `debug_io_direct` is documented as a developer option that reduces performance ([config.sgml#debug_io_direct](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L11602-L11624)).
- **Neither metric describes what the kernel sees.** The census shows a descending-order index whose forward scan reads the file one block at a time in descending order, and a fresh build whose backward scan does the same. Whether a kernel's read-ahead treats descending order like ascending order is outside PostgreSQL's source, so the model counts only steps to `blkno + 1` as sequential.
- **Local density.** The per-tenth spread on the random-order index, 335 to 409 index blocks against 370 to 374 rebuilt, is measured. The explanation from the 50:50 split rule is a reading of `nbtsplitloc.c`; this page did not measure fill per page.
- **The documentation contradicts the source on `effective_io_concurrency`.** `config.sgml` says it "only affects bitmap heap scans", but in 17 `read_stream_begin_relation()` also takes its I/O depth from it for every stream not flagged `READ_STREAM_MAINTENANCE`, including sequential scans and `pg_prewarm` ([config.sgml#effective_io_concurrency](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L2718-L2726), [read_stream.c#max_ios](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L420-L442)). Source wins on this page.
- **A stale comment.** `_bt_split()` still says the right page "was initialized by `_bt_getbuf`" one line after calling `_bt_allocbuf()` ([nbtinsert.c#_bt_split-stale-comment](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1720-L1723)).
- **No SSD figure at this pin.** The `R / S = 1.2` rows rest on the asker's choice of sensitivity value, not on the 17.11 documentation, which dropped its SSD example in 17.7.
- **The `synchronous_commit` probe is a race.** P1's outcome depends on when the WAL writer ran. The attribution to the shared commit-log LSN rests on the recorded transaction IDs, which fall in one group of 32, and on the recorded LSN bounds; the group LSN itself is not visible from SQL.
- **Half-dead pages were not produced.** A durable half-dead leaf needs an interrupted page deletion, so its effect is source-backed only ([README#page-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/README#L232-L259)).
- **The survey drops the session's own temporary indexes.** `pgstatindex` accepts them, as measured; no narrower filter that keeps them was tested.
- **The seed sweep has four seeds.** Its spread, 3,670 to 3,851 leaf pages, describes those seeds only, not a distribution.
- **The bitmap heap side was not investigated.** The bitmap scans read all 4,425 heap pages although the heap was all-visible; the index side, which this page uses, is unaffected.

## Source References

- [btreefuncs.c#page-type](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L125-L170)
- [btreefuncs.c#bt_multi_page_stats](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L336-L460)
- [btree.sql#bt_multi_page_stats](../../../../raw/postgres-17/contrib/pageinspect/sql/btree.sql#L1-L23)
- [pg_prewarm.c:127](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L127)
- [pg_prewarm.c:146](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L146)
- [pg_prewarm.c:227](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L227)
- [pg_prewarm.c#buffer-mode](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L250-L282)
- [pg_prewarm.c:263](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L263)
- [pgstattuple.out#empty-index-NaN](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L44-L52)
- [pgstattuple.out#partition-index-NaN](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L260-L268)
- [pgstatindex.c#relkind-am-macros](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L70-L71)
- [pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L203-L213)
- [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L215-L381)
- [pgstatindex.c:222](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L222)
- [pgstatindex.c#relation-checks](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L250)
- [pgstatindex.c#metapage-read](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L252-L265)
- [pgstatindex.c#full-block-scan](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L278-L331)
- [pgstatindex.c#page-classification](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L326)
- [pgstatindex.c#leaf-page-accounting](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L308-L316)
- [pgstatindex.c#fragmentation-count](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323)
- [pgstatindex.c#index_size](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L357)
- [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L367)
- [pgstatindex.c#leaf_fragmentation](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L368-L372)
- [pgstattuple--1.4--1.5.sql#pgstatindex-grants](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)
- [pgstattuple.control:3](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.control#L3)
- [pgstattuple.sql#empty-relations](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L1-L37)
- [pgstattuple.sql#partition-index](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L110-L120)
- [config.sgml#effective_io_concurrency](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L2718-L2726)
- [config.sgml#seq_page_cost](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5841-L5847)
- [config.sgml#random_page_cost](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5858-L5864)
- [config.sgml#random_page_cost-durable-storage](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5875-L5882)
- [config.sgml#random_page_cost-guidance](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5884-L5894)
- [config.sgml#random_page_cost-cached](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5896-L5907)
- [config.sgml#debug_io_direct](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L11602-L11624)
- [maintenance.sgml#routine-reindex-partly-empty](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1032-L1040)
- [maintenance.sgml#routine-reindex-adjacency](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1048-L1054)
- [maintenance.sgml#routine-reindex-locks](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1056-L1062)
- [pgstattuple.sgml#privileges](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L15-L24)
- [pgstattuple.sgml#pgstatindex-density-fragmentation](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L251-L261)
- [pgstattuple.sgml#pgstatindex-not-a-snapshot](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L275-L279)
- [queries.sgml#with-materialization](../../../../raw/postgres-17/doc/src/sgml/queries.sgml#L2520-L2535)
- [ref/alter_index.sgml#set-storage-parameter](../../../../raw/postgres-17/doc/src/sgml/ref/alter_index.sgml#L122-L133)
- [create_index.sgml#index-reloption-fillfactor](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L404-L411)
- [create_index.sgml#index-reloption-fillfactor-inserts](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L413-L426)
- [ref/reindex.sgml#concurrently](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml#L166-L182)
- [wal.sgml#async-commit-risk-window](../../../../raw/postgres-17/doc/src/sgml/wal.sgml#L438-L444)
- [heapam.c#heap_beginscan-read-stream](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1242-L1259)
- [heapam.c:1252](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1252)
- [heapam.c#heap_delete-clear-vm](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L3121-L3146)
- [heapam.c:8416](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8416)
- [heapam.c#heap_index_delete_tuples-prefetch-distance](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8540-L8570)
- [heapam.c#bottomup_nblocksfavorable](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8881-L8890)
- [heapam_handler.c#heapam_index_fetch_tuple](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L125-L140)
- [heapam_visibility.c#SetHintBits](../../../../raw/postgres-17/src/backend/access/heap/heapam_visibility.c#L82-L132)
- [pruneheap.c#heap_prune_record_unchanged_lp_normal-all-visible](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1363-L1387)
- [vacuumlazy.c:2434](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2434)
- [vacuumlazy.c:2758](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2758)
- [vacuumlazy.c#heap_page_is_all_visible-hint](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3011-L3021)
- [visibilitymap.c#visibilitymap_get_status-reuse](../../../../raw/postgres-17/src/backend/access/heap/visibilitymap.c#L366-L395)
- [visibilitymap.c#vm_readbuf](../../../../raw/postgres-17/src/backend/access/heap/visibilitymap.c#L616-L625)
- [indexam.c#index_fetch_heap-kill](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L644-L652)
- [README#page-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/README#L232-L259)
- [README#page-deletion-second-stage](../../../../raw/postgres-17/src/backend/access/nbtree/README#L279-L282)
- [README#concurrent-tid-recycling](../../../../raw/postgres-17/src/backend/access/nbtree/README#L443-L470)
- [nbtdedup.c#singleval-strategy-choice](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L104-L109)
- [nbtdedup.c#_bt_do_singleval](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L755-L802)
- [nbtdedup.c#_bt_singleval_fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L821-L842)
- [nbtinsert.c#_bt_findinsertloc-delete-or-dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L899-L906)
- [nbtinsert.c#_bt_insertonpg-split-test](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1203-L1221)
- [nbtinsert.c#_bt_split-allocate-right-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1707-L1724)
- [nbtinsert.c#_bt_split-stale-comment](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1720-L1723)
- [nbtinsert.c#_bt_split-sibling-links](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1726-L1746)
- [nbtinsert.c#_bt_delete_or_dedup_one_page-comment](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2655-L2681)
- [nbtinsert.c#simple-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2702-L2733)
- [nbtinsert.c#simpleonly-return](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2734-L2752)
- [nbtinsert.c#bottom-up-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2776)
- [nbtinsert.c#deduplication](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2778-L2781)
- [nbtpage.c#_bt_getroot-cached-metapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L356-L400)
- [nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717)
- [nbtpage.c#_bt_getbuf](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L844-L857)
- [nbtpage.c:869](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L869)
- [nbtpage.c#_bt_allocbuf-fsm-reuse](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L877-L969)
- [nbtpage.c#_bt_allocbuf-extend](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L971-L987)
- [nbtpage.c#_bt_mark_page_halfdead-flag](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2225-L2232)
- [nbtpage.c#_bt_unlink_halfdead_page-sibling-links](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2597-L2612)
- [nbtpage.c#_bt_unlink_halfdead_page-unlink-and-delete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2597-L2648)
- [nbtpage.c#_bt_pendingfsm_finalize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2995-L3055)
- [nbtree.c#btgettuple-killed-items](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L226-L245)
- [nbtree.c#btgetbitmap](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L262-L306)
- [nbtree.c#_bt_parallel_seize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L582-L612)
- [nbtree.c#_bt_parallel_release](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L701-L726)
- [nbtree.c#btvacuumscan-fsm-vacuum](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1048-L1059)
- [nbtree.c#btvacuumpage-strategy-read](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1098-L1105)
- [nbtree.c#btvacuumpage-recycle](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1165-L1171)
- [nbtsearch.c#_bt_drop_lock_and_maybe_pin](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L51-L72)
- [nbtsearch.c#_bt_first-endpoint](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1149-L1167)
- [nbtsearch.c#_bt_first-descend-and-read](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1387-L1469)
- [nbtsearch.c#_bt_next](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1495-L1529)
- [nbtsearch.c#_bt_readpage-currpage-nextpage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1612-L1631)
- [nbtsearch.c#_bt_readpage-skip-killed-forward](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1717-L1725)
- [nbtsearch.c#_bt_readpage-high-key](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1788-L1811)
- [nbtsearch.c#_bt_steppage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2040-L2168)
- [nbtsearch.c#_bt_steppage-killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2049-L2051)
- [nbtsearch.c#_bt_readnextpage-forward](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2191-L2243)
- [nbtsearch.c#_bt_readnextpage-backward](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2244-L2335)
- [nbtsearch.c#_bt_readnextpage-backward-comment](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2256-L2268)
- [nbtsearch.c#_bt_readnextpage-backward-repin](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2269-L2286)
- [nbtsearch.c#_bt_walk_left-half-dead-note](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2364-L2376)
- [nbtsearch.c#_bt_walk_left](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2377-L2481)
- [nbtsearch.c#_bt_get_endpoint](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2491-L2561)
- [nbtsearch.c#_bt_endpoint](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2572-L2664)
- [nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L645-L671)
- [nbtsort.c#page-number-allocation](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L650-L654)
- [nbtsort.c#page-full-test](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L844-L855)
- [nbtsplitloc.c:172](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L172)
- [nbtsplitloc.c#fillfactor-selection](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L335)
- [nbtsplitloc.c#other-leaf-pages-split-50-50](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L329-L335)
- [nbtsplitloc.c:364](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L364)
- [nbtsplitloc.c#split-strategy-overrides](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L397-L416)
- [nbtsplitloc.c#single-value-choice](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L1011-L1040)
- [nbtutils.c#_bt_killitems-mark-dead](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4312-L4342)
- [tableam.c#allvisfrac](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L749-L760)
- [clog.c#lsn-groups](../../../../raw/postgres-17/src/backend/access/transam/clog.c#L91-L96)
- [clog.c#group-lsn-update](../../../../raw/postgres-17/src/backend/access/transam/clog.c#L702-L716)
- [clog.c#TransactionIdGetStatus](../../../../raw/postgres-17/src/backend/access/transam/clog.c#L719-L758)
- [transam.c#TransactionIdGetCommitLSN](../../../../raw/postgres-17/src/backend/access/transam/transam.c#L376-L405)
- [xact.c#RecordTransactionCommit-async](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L1487-L1521)
- [xlog.c#XLogSetAsyncXactLSN](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L2607-L2657)
- [xlog.c#XLogBackgroundFlush-async-bound](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L2949-L2958)
- [xlog.c#XLogBackgroundFlush-flush-rules](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L3033-L3059)
- [xlogprefetcher.c:769](../../../../raw/postgres-17/src/backend/access/transam/xlogprefetcher.c#L769)
- [xlogprefetcher.c#max_inflight](../../../../raw/postgres-17/src/backend/access/transam/xlogprefetcher.c#L1000-L1004)
- [index.c#index_update_stats-relallvisible](../../../../raw/postgres-17/src/backend/catalog/index.c#L2851-L2857)
- [system_views.sql#pg_statio_all_tables](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L746-L778)
- [system_views.sql#pg_statio_all_indexes](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L817-L831)
- [analyze.c:1199](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1199)
- [analyze.c#acquire_sample_rows-read-stream](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1199-L1205)
- [explain.c#heap-fetches](../../../../raw/postgres-17/src/backend/commands/explain.c#L1993-L1994)
- [explain.c#show_buffer_usage](../../../../raw/postgres-17/src/backend/commands/explain.c#L3742-L3817)
- [explain.c#show_buffer_usage-io-timings](../../../../raw/postgres-17/src/backend/commands/explain.c#L3819-L3860)
- [vacuum.c#vacuum-buffer-strategy](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L436-L445)
- [vacuum.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1444-L1461)
- [variable.c#check_io_concurrency](../../../../raw/postgres-17/src/backend/commands/variable.c#L1222-L1246)
- [nodeBitmapHeapscan.c:500](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L500)
- [nodeBitmapHeapscan.c:551](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L551)
- [nodeBitmapHeapscan.c#prefetch_maximum](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L760-L764)
- [nodeIndexonlyscan.c:104](../../../../raw/postgres-17/src/backend/executor/nodeIndexonlyscan.c#L104)
- [nodeIndexonlyscan.c#IndexOnlyNext-visibility-check](../../../../raw/postgres-17/src/backend/executor/nodeIndexonlyscan.c#L161-L170)
- [nodeIndexonlyscan.c:750](../../../../raw/postgres-17/src/backend/executor/nodeIndexonlyscan.c#L750)
- [allpaths.c#compute_parallel_worker](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4203-L4279)
- [costsize.c#cost_index-index-charge](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L617-L633)
- [costsize.c#cost_index-heap-pages](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L714-L747)
- [costsize.c#cost_index-workers](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L779)
- [costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L806-L815)
- [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L897-L951)
- [costsize.c#get_parallel_divisor](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L6375-L6405)
- [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L463-L501)
- [plancat.c#index-pages-from-file-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L477)
- [plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160)
- [read_stream.c#max_ios](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L420-L442)
- [read_stream.c:536](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L536)
- [bufmgr.c#PrefetchSharedBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L551-L558)
- [bufmgr.c#PrefetchBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L644-L666)
- [bufmgr.c#PinBufferForBlock-counting](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1161-L1171)
- [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1248-L1263)
- [bufmgr.c#StartReadBuffersImpl-advice](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1326-L1343)
- [bufmgr.c#MarkBufferDirty-accounting](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2587-L2596)
- [bufmgr.c#ReleaseAndReadBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2612-L2645)
- [bufmgr.c#MarkBufferDirtyHint-accounting](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L5147-L5150)
- [localbuf.c:96](../../../../raw/postgres-17/src/backend/storage/buffer/localbuf.c#L96)
- [indexfsm.c#GetFreeIndexPage](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L32-L46)
- [indexfsm.c#RecordFreeIndexPage-and-IndexFreeSpaceMapVacuum](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L48-L74)
- [lock.c#LockConflicts-AccessShareLock](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L67-L68)
- [lock.c#LockAcquireExtended-wait-queue](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L1031-L1040)
- [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L898-L923)
- [pgstat.c#pgstat_report_stat-force](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L583-L600)
- [pgstat_io.c#pgstat_count_io_op_time](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_io.c#L121-L151)
- [pgstatfuncs.c#pg_stat_force_next_flush](../../../../raw/postgres-17/src/backend/utils/adt/pgstatfuncs.c#L1688-L1695)
- [pgstatfuncs.c#pg_stat_reset_single_table_counters](../../../../raw/postgres-17/src/backend/utils/adt/pgstatfuncs.c#L1761-L1770)
- [selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145)
- [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6737)
- [selfuncs.c#numIndexPages-prorata](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732)
- [selfuncs.c#genericcostestimate-page-costs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6787)
- [selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810)
- [selfuncs.c#btcostestimate-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7106)
- [selfuncs.c#btcostestimate-height-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)
- [spccache.c#get_tablespace_page_costs](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L173-L205)
- [guc_tables.c#track_io_timing](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1420-L1428)
- [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270)
- [guc_tables.c#vacuum_buffer_usage_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2272-L2281)
- [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620)
- [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)
- [guc_tables.c#wal_writer_delay](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2902-L2911)
- [guc_tables.c#wal_writer_flush_after](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2913-L2922)
- [guc_tables.c#effective_io_concurrency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3109-L3121)
- [guc_tables.c#maintenance_io_concurrency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3123-L3136)
- [guc_tables.c#io_combine_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3138-L3150)
- [guc_tables.c#max_parallel_workers_per_gather](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3419-L3428)
- [guc_tables.c#effective_cache_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3518)
- [guc_tables.c#min_parallel_index_scan_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3531-L3540)
- [guc_tables.c#seq_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3675-L3685)
- [guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696)
- [guc_tables.c#debug_io_direct](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4699-L4708)
- [guc_tables.c#synchronous_commit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4925-L4933)
- [guc_tables.c#recovery_prefetch](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L5078-L5086)
- [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-17/src/include/access/nbtree.h#L62-L69)
- [nbtree.h#fillfactor](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202)
- [nbtree.h:212](../../../../raw/postgres-17/src/include/access/nbtree.h#L212)
- [nbtree.h#page-flag-macros](../../../../raw/postgres-17/src/include/access/nbtree.h#L218-L228)
- [nbtree.h#BTPageSetDeleted](../../../../raw/postgres-17/src/include/access/nbtree.h#L238-L257)
- [nbtree.h#BTPageIsRecyclable](../../../../raw/postgres-17/src/include/access/nbtree.h#L279-L318)
- [nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1145)
- [instrument.h#BufferUsage](../../../../raw/postgres-17/src/include/executor/instrument.h#L24-L42)
- [execnodes.h#IndexOnlyScanState](../../../../raw/postgres-17/src/include/nodes/execnodes.h#L1699-L1718)
- [cost.h#default-costs](../../../../raw/postgres-17/src/include/optimizer/cost.h#L21-L30)
- [pg_config_manual.h#USE_PREFETCH](../../../../raw/postgres-17/src/include/pg_config_manual.h#L150-L163)
- [pgstat.h#buffer-counting-macros](../../../../raw/postgres-17/src/include/pgstat.h#L635-L644)
- [bufmgr.h#io-concurrency-defaults](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L157-L164)
- [rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/src/include/utils/rel.h#L667-L669)
- [btree_index.sql#tall-tree](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L240-L250)
- [btree_index.sql#page-deletion-and-recycling](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L252-L270)

## Navigation

- [v17/index](../../index.md)
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
- [Wiki Glossary (unverified)](../../../glossary.md)
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
- [Planner Penalties for Bloated Indexes in PostgreSQL 17 (unverified)](../query-planning/bloated-indexes-query-planner.md)
- [B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17 (unverified)](btree-bloat-with-pgstatindex.md)
- [How Bottom-Up Index Deletion and B-Tree Deduplication Work in PostgreSQL 17 (unverified)](bottom-up-deletion-and-btree-deduplication.md)
- [How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 17 (unverified)](reindex-index-concurrently.md)
- [B-Tree Leaf Density vs Fragmentation Impact on Index Scan I/O in PostgreSQL 12 (unverified)](../../../v12/questions/indexing/leaf-density-vs-fragmentation-index-scan-io.md), the same question for PostgreSQL 12
