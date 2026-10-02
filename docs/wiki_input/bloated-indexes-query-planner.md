---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# Planner Penalties for Bloated Indexes in PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Mental Model](#mental-model)
  - [Logic Map](#logic-map)
  - [Step-By-Step Mechanism](#step-by-step-mechanism)
  - [Branches And Exceptional Cases](#branches-and-exceptional-cases)
  - [Lifecycle Of The Planner Inputs](#lifecycle-of-the-planner-inputs)
  - [Key Interactions](#key-interactions)
  - [Formulas](#formulas)
  - [What The Planner Does Not See](#what-the-planner-does-not-see)
  - [Types Of Bloated Indexes](#types-of-bloated-indexes)
  - [How Density And Fragmentation Affect Different Queries](#how-density-and-fragmentation-affect-different-queries)
  - [Exact-Pin Measurements](#exact-pin-measurements)
  - [Causal Summary](#causal-summary)
  - [What Changed Since PostgreSQL 12](#what-changed-since-postgresql-12)
  - [Settings That Move The Boundary](#settings-that-move-the-boundary)
  - [Practical Interpretation](#practical-interpretation)
  - [Key Data Structures](#key-data-structures)
  - [Caller And Callee Boundary](#caller-and-callee-boundary)
  - [Build, Generated-Header, And Extension Boundary](#build-generated-header-and-extension-boundary)
  - [Tests And Explicit Test Absence](#tests-and-explicit-test-absence)
  - [Follow-Up: When A GIN Index Is Discarded And A B-Tree Is Used Instead](#follow-up-when-a-gin-index-is-discarded-and-a-b-tree-is-used-instead)
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

In PostgreSQL 17, are there mechanisms to penalize bloated indexes in the query planner? If there are, give a comprehensive explanation with examples of types of bloated indexes and how leaf fragmentation or density affects them, and what changed since PostgreSQL 12.

Follow-up:

When might a GIN index be discarded by the query planner and a B-tree used instead?

## Answer

Yes, but only indirectly. PostgreSQL 17's [planner](../../../glossary.md#planner) has no notion of [bloat](../../../glossary.md#bloat). It prices an [index scan](../../../glossary.md#index-scan) from the index's physical size and, for a [B-tree](../../../glossary.md#b-tree), from the tree's height. So bloat raises a plan's [cost](../../../glossary.md#cost) mainly when it adds pages that the scan is expected to read, or adds a level to the tree. Dead entries at the ends of a B-tree can also hold a stale row estimate ([Step 6](#step-6-probe-the-ends-of-a-b-tree-while-estimating-rows)).

That has a surprising consequence. A scan that reads a large part of an index pays for bloat in full, page for page. A one-row lookup on the same bloated index costs exactly what it costs on a freshly built one, as long as the index has no more pages than the table has rows and keeps its height. And the density and fragmentation figures that [`pgstatindex`](../../../glossary.md#pgstatindex) reports never reach the planner at all.

The reason is that, for a non-partial B-tree, the cost code sees only three numbers about the index. It reads the index file's current [block](../../../glossary.md#block) count, assumes the index holds one entry per estimated table row, and reads a B-tree's height from its [metapage](../../../glossary.md#metapage). Neither the [`pg_class`](../../../glossary.md#pg_class) [catalog](../../../glossary.md#catalog) nor the planner's [`IndexOptInfo`](../../../glossary.md#indexoptinfo) structure has a bloat, density or fragmentation field ([pg_class.h#relpages](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L69), [pathnodes.h#IndexOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1120-L1128)).

Measured on an isolated server built from this pin, the consequences are sharply uneven:

| Situation | Planner's charge, measured | Why |
|---|---|---|
| Whole-index scan of a dense index and its bloated twin, 2,745 against 26,411 blocks | `28480.42` against `123144.43` ([measured](#whole-index-scan-cost-is-a-closed-form-in-pages-tuples-and-tree-height)) | [Step 2](#step-2-charge-the-pages-a-scan-touches) |
| One-row lookup on the same two indexes | `4.44` on both ([measured](#the-point-lookup-is-nearly-blind-to-bloat)) | [Step 2](#step-2-charge-the-pages-a-scan-touches) |
| One-row lookup on a 2,745-block index over 1,000 rows | `12.29`, against `4.29` after a rebuild ([measured](#a-mostly-empty-index-the-fast-root-drops-and-pages-outnumber-rows)) | [Branches](#branches-and-exceptional-cases) |
| The dense and bloated lookups repeated 50,000 times in a [nested loop](../../../glossary.md#nested-loop-join) | `0.66` against `2.50` per loop ([measured](#index-pages-in-the-cache-model)) | [Step 4](#step-4-apply-the-cache-model-and-pick-workers) |
| A [partial index](../../../glossary.md#partial-index) that grew from 57 to 331 blocks since its statistics were written | 113 pages until [`ANALYZE`](../../../glossary.md#statistics), then 331 ([measured](#a-partial-index-hides-its-growth-until-its-statistics-are-rewritten)) | [Key Interactions](#key-interactions) |
| Dead entries at the upper end of a B-tree | no cost term; a stale 10-row estimate held for four plans ([measured](#dead-entries-at-the-end-of-a-b-tree-the-endpoint-probe)) | [Step 6](#step-6-probe-the-ends-of-a-b-tree-while-estimating-rows) |
| 49.87% against 0% `leaf_fragmentation` | a gap of exactly `(1148 - 744) * random_page_cost` = `1616.00` ([measured](#leaf-fragmentation-contributes-exactly-zero)) | [Mental Model](#mental-model) |
| 9.27% against 89.18% `avg_leaf_density` on two 2,745-block indexes | the same `12730.42` ([measured](#two-indexes-with-the-same-cost-and-opposite-avg_leaf_density)) | [What The Planner Does Not See](#what-the-planner-does-not-see) |

Since PostgreSQL 12 the cost formulas barely moved. v17 added one new input, a cap on estimated [ScalarArrayOp](../../../glossary.md#scalararrayopexpr) descents (`5bf748b86bc`). Work on nbtree in v13 and v14 reduces how much bloat builds up (`0d861bbb702`, `d168b666823`). And a 100-heap-page limit on the planning-time endpoint probe arrived in 16 and was [back-patched](../../../glossary.md#back-patch) (`9c6ad5eaa9`). [What Changed Since PostgreSQL 12](#what-changed-since-postgresql-12) sets out each change against the pinned history.

### Mental Model

Eight values decide what the planner charges for an index. The table says what each one means, where it comes from, whether it is live or stored, and which later step uses it. *Live* means read from the index or table file while the query is planned. *Stored* means written into a catalog by an earlier command, so it describes the relation as it was then.

| Value | Meaning | Source | Live or stored | Later use |
|---|---|---|---|---|
| `index->pages` (`IndexOptInfo.pages`) | every block of the index's main [fork](../../../glossary.md#fork) | `RelationGetNumberOfBlocks()`, called by `get_relation_info()` ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486), [bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L280-L281)) | live | the page share ([step 2](#step-2-charge-the-pages-a-scan-touches)), the cache model ([step 4](#step-4-apply-the-cache-model-and-pick-workers)), the descent cap ([step 5](#step-5-clamp-scalararrayop-descents-new-in-v17)) |
| `index->tuples` | the entries the planner assumes the index holds | non-partial: the table's row estimate; partial: a recorded density times the live blocks, capped at the table's estimate ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160)) | derived from live sizes and stored ratios | the page share ([step 2](#step-2-charge-the-pages-a-scan-touches)), the comparison charge ([step 3](#step-3-charge-the-b-tree-height)) |
| table row estimate (`rel->tuples`) | the rows the table is estimated to hold | the recorded `reltuples / relpages` times the live heap blocks, or a width-based density when the table has no statistics yet ([tableam.c#table_block_relation_estimate_size-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L711-L747)) | derived from a live size and a stored ratio | `index->tuples` for a non-partial index; the rows a scan reads |
| `pg_class.relpages`, `reltuples` | the counts the last [`VACUUM`](../../../glossary.md#vacuum), `ANALYZE` or index build recorded ([reltuples and relpages](../../../glossary.md#reltuples-and-relpages)) | the relation's catalog row ([pg_class.h#relpages](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L69)) | stored | the table's density; a partial index's density ([Lifecycle](#lifecycle-of-the-planner-inputs)) |
| `numIndexTuples` | the entries one descent of this scan reads | the [selectivity](../../../glossary.md#selectivity) of the boundary conditions times the table's row estimate ([selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019)) | computed from stored statistics | the page share and the per-entry CPU charge ([step 2](#step-2-charge-the-pages-a-scan-touches)) |
| `numIndexPages` | the index pages one descent touches | a pro-rata share of `index->pages` ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)) | computed | the page charge ([step 2](#step-2-charge-the-pages-a-scan-touches)); the worker count ([step 4](#step-4-apply-the-cache-model-and-pick-workers)) |
| `tree_height` | a B-tree's [fast-root](../../../glossary.md#fast-root) level | `_bt_getrootheight()`, from the metapage or a per-backend cached copy of it ([plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500), [nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717)) | live, unless the cached copy is stale | the descent charge ([step 3](#step-3-charge-the-b-tree-height)) |
| a column's lowest and highest values | the ends of the [histogram](../../../glossary.md#most-common-values-and-histogram) | `pg_statistic` from the last `ANALYZE`, replaced by a read of the index's end when that read succeeds ([selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136)) | stored, or live after a successful probe | the selectivity, so `numIndexTuples` ([step 6](#step-6-probe-the-ends-of-a-b-tree-while-estimating-rows)) |

Four pairs of similar names come from different places, and mixing them up is the usual way to misread a plan:

- **`index->pages` against `pg_class.relpages`.** The planner charges the live block count, so bloat counts at the next plan with no `ANALYZE` ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)). Forging `relpages = 1` changes no cost ([measured](#the-planner-reads-the-live-block-count-not-pg_classrelpages)). Only a partial index reads `relpages`, and only to compute its density.
- **`index->tuples` against the index's real entry count.** For a non-partial index, `tuples` is the table's row estimate ([plancat.c:476](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L476)). So removing index entries never lowers it, and a falling table estimate raises `pages / tuples` while the index keeps its pages.
- **`index->pages` against `numIndexPages`.** The first is the whole index; the second is this scan's share. The cache model uses the first, and parallel-worker selection the second ([costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L772), [selfuncs.c#btcostestimate-outputs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7206-L7210)).
- **`tree_height` against `pgstatindex`'s `tree_level`.** The planner charges the fast-root level, `btm_fastlevel`; `pgstatindex` reports the true root level, `btm_level` ([nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717), [pgstatindex.c#pgstatindex_impl-metapage](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L252-L265)). Page deletion can lower only the first.

`avg_leaf_density` and `leaf_fragmentation` are not in the table because nothing on the cost path reads them. `pgstatindex` computes them on demand, from live [leaf pages](../../../glossary.md#leaf-page) only ([pgstatindex.c#pgstatindex_impl-pages](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L331), [pgstatindex.c#pgstatindex_impl-density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L372)).

### Logic Map

The flowchart follows one index path from the index's files to the plan choice. Each box names the decision, the values it reads, and what it hands to the next box. The bracketed letters key the citations listed under it.

```text
Plan a scan of index I on table T
|
+-- [A] Read I's size (get_relation_info)
|     I partitioned? -- yes --> pages = 0, tuples = 0, no height; stop
|     I partial?     -- no  --> pages = live blocks of I
|     |                         tuples = T's row estimate
|     |              -- yes --> pages = live blocks of I
|     |                         tuples = recorded density x live blocks
|     |                                  (width-based density if relpages <= 1 or reltuples < 0),
|     |                                  capped at T's row estimate
|     I a B-tree?    -- yes --> tree_height = btm_fastlevel (metapage or cached copy)
|                    -- no  --> tree_height = -1
|
+-- [B] Estimate the rows the conditions match
|     range condition reaching the first or last histogram bound,
|     and a plain B-tree leads with that column?
|           -- yes --> probe that end of the index: live value, or give up
|                      after 100 heap pages and keep the stored bound
|     numIndexTuples = selectivity x T's row estimate    (1 for a unique equality lookup)
|
+-- [C] Price the index work (btcostestimate, genericcostestimate)
|     v17 B-tree: descents s = min(array descents, ceil(pages x 0.3333333)), at least 1
|     pages > 1 and tuples > 1?
|           -- no  --> numIndexPages = 1
|           -- yes --> numIndexPages = ceil(numIndexTuples x pages / tuples)
|     scan repeated (loops x s > 1)?
|           -- no  --> I/O = numIndexPages x random_page_cost
|           -- yes --> I/O = Mackert-Lohman(numIndexPages x loops x s, universe = pages)
|                            x random_page_cost / loops
|     + per-entry CPU; B-tree: + s x (log2 comparisons + (tree_height + 1) x 50 x cpu_operator_cost)
|
+-- [D] Finish the index path (cost_index)
|     heap fetches through the cache model, index pages in the total (not a single correlated scan)
|     parallel: workers from numIndexPages, unless a parallel_workers reloption is set
|
+-- [E] Compare paths (add_path, choose_bitmap_and)
      the cheaper path survives: a bloated index can lose to a sequential scan,
      drop out of a BitmapAnd, or get more parallel workers
```

- [A] [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160), [plancat.c#estimate_rel_size-density](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1116-L1146), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500), [plancat.c#get_relation_info-partitioned](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L502-L508)
- [B] [selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136), [selfuncs.c#get_actual_variable_range-index-choice](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6179-L6239), [selfuncs.c#get_actual_variable_endpoint-limit](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6436-L6457), [selfuncs.c#btcostestimate-unique-equality](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6991-L7002), [selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019)
- [C] [selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732), [selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779), [selfuncs.c#genericcostestimate-single-scan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6780-L6787), [selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810), [selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091), [selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)
- [D] [costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747), [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951), [costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L772), [allpaths.c#compute_parallel_worker](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4202-L4279)
- [E] [pathnode.c#add_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L419-L622), [indxpath.c#choose_bitmap_and](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1287-L1489)

### Step-By-Step Mechanism

Each step reads its inputs, makes its decisions, computes a value and hands it to the next step. The step numbers follow the [Logic Map](#logic-map); step 6 belongs to box B, because it runs while rows are estimated.

#### Step 1: Read the index size

**Input:** the index's file and its `pg_class` row, and the table's row estimate. **Decisions:** is the index partitioned, partial, a B-tree? **Output:** `pages`, `tuples` and `tree_height` in `IndexOptInfo`.

`get_relation_info()` opens every index of a table while it builds the planner's picture of that table. It copies the [access method](../../../glossary.md#access-method)'s cost function, `amcostestimate`, into `IndexOptInfo` ([plancat.c#amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L331-L332)). Then it fills the size fields ([plancat.c#get_relation_info-index-block](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L463-L508)):

```c
if (info->indpred == NIL)
{
    info->pages = RelationGetNumberOfBlocks(indexRelation);
    info->tuples = rel->tuples;
}
```

([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486))

For a non-partial index, `pages` is the block count the [storage manager](../../../glossary.md#storage-manager) reports now ([bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4002-L4020)). So pages added by bloat count at the very next plan. Fixture Q's plain index was charged all 825 of its live blocks while `pg_class` still recorded 551.

`tuples` for the same index is the table's row estimate, not the index's entry count. Removing index entries therefore never lowers it. The table's estimate is itself the recorded `reltuples / relpages` density, or a width-based one when the table has no statistics yet, times the live [heap](../../../glossary.md#heap) size ([tableam.c#table_block_relation_estimate_size-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L711-L747)).

A partial index takes both values from `estimate_rel_size()` instead. `pages` is still the live block count. `tuples` is the density its `pg_class` row records, `reltuples` over `relpages`, times the live block count, each count less the metapage when the row records any pages ([plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160)). `get_relation_info()` then caps `tuples` at the table's row estimate ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)). That recorded density is why a partial index hides its own growth; see [Key Interactions](#key-interactions).

For a B-tree, `tree_height` is the fast-root level that `_bt_getrootheight()` reads while the index is open. Every other access method gets `-1` ([plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500)). A [partitioned index](../../../glossary.md#partitioned-index) has no storage, so it gets `pages = 0`, `tuples = 0` and a height of `-1` ([plancat.c#get_relation_info-partitioned](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L502-L508)).

**Consequence:** every later step works from these three numbers, and none of them measures how full the pages are.

#### Step 2: Charge the pages a scan touches

**Input:** `numIndexTuples`, `pages`, `tuples`. **Decisions:** the two guards on the pro-rata share. **Output:** `numIndexPages` and the page and entry charges.

`btcostestimate()` first decides how many entries one descent reads. It multiplies the selectivity of the conditions that bound the scan by the table's row estimate ([selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019)). A unique index searched by equality on every key column skips that and reads one entry ([selfuncs.c#btcostestimate-unique-equality](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6991-L7002)).

`genericcostestimate()` then turns entries into pages. It takes the same fraction of the index's pages as of its entries, rounded up:

```c
if (index->pages > 1 && index->tuples > 1)
    numIndexPages = ceil(numIndexTuples * index->pages / index->tuples);
else
    numIndexPages = 1.0;
```

([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732))

Its comment says this counts only leaf pages and ignores the metapage and upper levels. Because the share is proportional to `pages`, every extra block of bloat raises it for any scan that reads a meaningful fraction of the index.

A single scan pays `random_page_cost` for each of those pages ([selfuncs.c#genericcostestimate-single-scan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6780-L6787)). Each entry read also costs `cpu_index_tuple_cost` plus one `cpu_operator_cost` per index condition ([selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810)). The page cost comes from the index's [tablespace](../../../glossary.md#tablespace) when that tablespace sets its own ([selfuncs.c#genericcostestimate-tablespace](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6734-L6737)).

Two guards change the result, and both show up in real workloads. The `ceil()` keeps a small lookup at one page while `numIndexTuples * pages <= tuples`. The `pages > 1 && tuples > 1` test returns a flat one page whenever either count is one or less. [Branches And Exceptional Cases](#branches-and-exceptional-cases) lists what each guard does to a bloated index.

**Consequence:** a broad scan pays for bloat in proportion to page count, and a one-row lookup pays nothing for it while the index has no more pages than the table has rows.

#### Step 3: Charge the B-tree height

**Input:** `tree_height`, `tuples` and the descent count. **Decision:** the comparison charge applies only when `tuples > 1`; the level charge always applies. **Output:** two CPU charges per descent.

After `genericcostestimate()` returns, `btcostestimate()` adds a comparison charge, `ceil(log2(tuples))` times `cpu_operator_cost`, for the key comparisons of one descent ([selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091)). It then adds a page charge for every level the descent passes through:

```c
descentCost = (index->tree_height + 1) * DEFAULT_PAGE_CPU_MULTIPLIER * cpu_operator_cost;
```

([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106))

The in-tree comment names bloat as a reason for this second charge: "if we had no such charge at all, bloated indexes would appear to have the same search cost as unbloated ones, at least in cases where only a single leaf page is expected to be visited." `DEFAULT_PAGE_CPU_MULTIPLIER` is `50.0` ([selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145)), and `cpu_operator_cost` defaults to `0.0025` ([cost.h:28](../../../../raw/postgres-17/src/include/optimizer/cost.h#L28)). So each extra level costs `0.125`.

The charge follows levels, not density: it changes only when the tree gains or loses a level. Fixture H's one-level and two-level indexes price the same lookup at `8.31` and `8.43` ([measured](#the-tree-height-charge-isolated-to-the-cent)).

The level is the fast root, not the true root. `_bt_getrootheight()` returns `btm_fastlevel` ([nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717)). [Page deletion](../../../glossary.md#b-tree-page-deletion) can lower that level in place ([nbtpage.c#_bt_unlink_halfdead_page-fastroot](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2565-L2659)), while the true root level never decreases ([README#page-deletion-and-tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L362-L381)). `pgstatindex` reports the true level as `tree_level` ([pgstatindex.c#pgstatindex_impl-metapage](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L252-L265), [pgstatindex.c:351](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L351), [pgstattuple--1.4--1.5.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L24), [pgstattuple.control:3](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.control#L3)). Fixture F measures the two apart: `tree_level` 2 against `fastlevel` 1.

The height can also be out of date. `_bt_getrootheight()` answers from a per-backend cached copy of the metapage whenever one exists, and its comment says "slightly-stale data is fine" ([nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717)). [Lifecycle Of The Planner Inputs](#lifecycle-of-the-planner-inputs) lists the events that refresh that copy and the ones that leave it stale.

**Consequence:** height is the only bloat signal in a lone one-page lookup's cost, apart from a row estimate the endpoint probe of step 6 can leave stale, and it is worth `0.125` per level at default settings.

#### Step 4: Apply the cache model and pick workers

**Input:** `numIndexPages`, the number of times the scan repeats, `pages`. **Decisions:** is the scan repeated; is the path parallel? **Output:** a per-loop page charge and a worker count.

A scan repeats when it is the inner side of a nested loop, or once per array element of a `ScalarArrayOpExpr` such as `id = ANY (...)`. Then `genericcostestimate()` multiplies `numIndexPages` by the number of scans. It passes the product to `index_pages_fetched()`, which applies the [Mackert-Lohman](../../../glossary.md#mackert-lohman-formula) cache model with the whole index as the set of pages ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779), [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)). The result is divided by the loop count, so each loop pays a share.

Because the whole index is the set of pages, a repeated one-page lookup can be priced by bloat even though a lone one is not. How much depends on the loop count. Few loops over a large index pay about one page each, whatever its size. Once the loops together touch twice the index's pages, an index within its cache share is charged the whole index, spread across the loops. [Formulas](#formulas) gives the exact cases.

The model shares out [`effective_cache_size`](../../../glossary.md#effective_cache_size) across the query's tables plus the index being costed ([costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951), [allpaths.c#total_table_pages](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L183-L216)). So a bloated index claims a larger share of the notional cache for itself. `cost_index()` also passes `index->pages` when it prices heap fetches through the same model: a single scan's uncorrelated estimate and both repeated-scan estimates use it, and only a single scan's perfectly correlated estimate skips it ([costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747)). `compute_bitmap_pages()` does the same for repeated [bitmap scans](../../../glossary.md#bitmap-scan) ([costsize.c#compute_bitmap_pages-repeated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L6463-L6476)). In each case a bloated index leaves a smaller share of the cache for the heap.

[Parallel](../../../glossary.md#parallel-query) worker selection reads a different number. `cost_index()` hands `compute_parallel_worker()` the access method's page output, which `btcostestimate()` sets to `numIndexPages` ([costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L772), [selfuncs.c#btcostestimate-outputs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7206-L7210)). The worker count then grows by one each time that estimate triples ([allpaths.c#compute_parallel_worker-index-ramp](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4253-L4272)). So bloat raises the worker count through the pages this scan touches, which grow with its selectivity, rather than through the whole index. [Branches](#branches-and-exceptional-cases) lists the settings that bypass this.

**Consequence:** repetition turns the whole index back into a cost input, and bloat can change a plan's shape, not only its price ([measured](#bloat-changes-parallel-worker-counts): 4 workers against 6 for a whole-index scan).

#### Step 5: Clamp ScalarArrayOp descents (new in v17)

**Input:** the array lengths in the boundary conditions, and `pages`. **Decision:** is the estimated descent count above a third of the pages? **Output:** `num_sa_scans`, the descent count every B-tree charge is multiplied by.

The cost model assumes that a condition such as `id = ANY (ARRAY[...])` makes a B-tree descend once per array element, up to a limit. v17's `btcostestimate()` caps the estimated number of descents at a third of the index's pages:

```c
num_sa_scans = Min(num_sa_scans, ceil(index->pages * 0.3333333));
num_sa_scans = Max(num_sa_scans, 1);
```

([selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042))

The clamp came with `5bf748b86bc`, v17's native ScalarArrayOp B-tree scans; [v17: index pages now cap ScalarArrayOp descents](#v17-index-pages-now-cap-scalararrayop-descents) gives its history. `num_sa_scans` multiplies both descent charges of step 3. It also reaches `genericcostestimate()` through `GenericCosts`, where it multiplies the page count before the cache model ([selfuncs.c#btcostestimate-genericcost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7067-L7073), [selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779)).

The per-entry charge is treated differently: it is divided and multiplied by the same count, so it mostly cancels. [Key Interactions](#key-interactions) shows the two ways it does not.

**Consequence:** a bloated index has a higher cap, so on the same `= ANY` query it keeps more estimated descents than its dense twin. Against v12, which had no clamp, that is a discount for the dense index rather than a penalty for the bloated one ([measured](#the-v17-scalararrayop-descent-clamp): fixture I's 8-block index stops at its cap of 3 descents, while its 55-block twin, capped at 19, keeps adding descents through the ten-element array).

#### Step 6: Probe the ends of a B-tree while estimating rows

**Input:** a range condition, the column's histogram, the first suitable B-tree. **Decisions:** does the search reach an end bound; does the probe find a live row within its limit? **Output:** a row estimate, which sets `numIndexTuples` in step 2.

This step prices nothing, and no cost term charges it. It is a read that row estimation makes while planning. Dead entries at an end of a B-tree make that read longer, and they can leave a stale row estimate in place.

**When it runs.** The range-comparison estimators pass a comparison against a constant to `scalarineqsel()` ([selfuncs.c#scalarineqsel_wrapper](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1397-L1503)), which calls `ineq_histogram_selectivity()` ([selfuncs.c:690](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L690)). When that function's binary search is about to compare against the first or last histogram bound, it asks for the column's current minimum or maximum instead. The source says this "ameliorates misestimates when the min or max is moving as a result of changes since the last ANALYZE" ([selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136)).

Two other estimators reach the same code. Prefix estimation for a pattern such as `LIKE 'foo%'` calls `ineq_histogram_selectivity()` ([like_support.c#prefix_selectivity](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1213-L1270)). Merge-join costing calls `mergejoinscansel()` ([costsize.c:3577](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L3577), [costsize.c:4016](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L4016)), which reads each side's extremes from statistics without a probe and then calls `scalarineqsel()` four times against them ([selfuncs.c#mergejoinscansel-ranges](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L3141-L3156), [selfuncs.c#get_variable_range-not-used](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5993-L6003), [selfuncs.c#mergejoinscansel-scalarineqsel](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L3164-L3203)). When the two columns span similar ranges, those constants land in the end bins, so the probe can run there too.

**Which index it reads.** `get_actual_variable_range()` takes the first index on the table that is a B-tree, is not partial, is not [hypothetical](../../../glossary.md#hypothetical-index), and whose first column matches the compared expression, [collation](../../../glossary.md#collation) and sort operator. It gives up at once on a partitioned table's parent ([selfuncs.c#get_actual_variable_range-index-choice](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6179-L6239), [selfuncs.c#get_actual_variable_range](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6157-L6331)).

**What it reads.** `get_actual_variable_endpoint()` walks the index from that end, using the [index-only scan](../../../glossary.md#index-only-scan) machinery under a [non-vacuumable snapshot](../../../glossary.md#snapshotnonvacuumable) ([selfuncs.c#get_actual_variable_endpoint-snapshot](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6376-L6386), [selfuncs.c#get_actual_variable_endpoint-scan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6415-L6458)). An entry whose heap page is [all-visible](../../../glossary.md#visibility-map) is accepted without a heap visit. Any other entry costs a heap visit. Rows that no [snapshot](../../../glossary.md#snapshot) can still see are skipped; recently dead and uncommitted rows are accepted.

**The limit.** Each skipped entry on a heap page different from the previous one counts one visited page. Once the count passes `VISITED_PAGES_LIMIT`, 100, the probe gives up ([selfuncs.c#get_actual_variable_endpoint-limit](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6436-L6457)), and the estimate keeps "whatever extremal value is recorded in pg_statistic" ([selfuncs.c#get_actual_variable_endpoint-give-up](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6409-L6413)).

**Self-healing.** When an entry's whole [HOT](../../../glossary.md#hot) chain is dead, `index_fetch_heap()` asks for the entry to be killed ([indexam.c#index_fetch_heap-kill](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L644-L652)). The B-tree records that request on its next call and marks the recorded entries dead before it leaves the page or ends the scan ([nbtree.c#btgettuple-kill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L226-L245), [nbtsearch.c#_bt_steppage-killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2049-L2051), [nbtree.c#btendscan-killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L424-L426)). The entry at which the probe gives up is the exception: the loop stops before the B-tree is called again, so that request is never recorded. The next probe skips the killed entries without a heap visit ([selfuncs.c#get_actual_variable_endpoint-killed](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6388-L6397)), so successive plans each get up to 100 heap pages further.

**On a standby.** A transaction started during recovery neither sets nor honors killed entries ([genam.c#RelationGetIndexScan-recovery](../../../../raw/postgres-17/src/backend/access/index/genam.c#L107-L119), [nbtsearch.c:1721](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1721), [nbtsearch.c:1850](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1850)). So on a [hot standby](../../../glossary.md#hot-standby) each probe walks the same dead entries again.

**History.** The 100-page limit is commit `9c6ad5eaa9` (2022-11-22), first in PostgreSQL 16; its message asks for a back-patch to all supported branches. See [v16, back-patched: the endpoint probe gives up after 100 heap pages](#v16-back-patched-the-endpoint-probe-gives-up-after-100-heap-pages).

**Consequence:** dead entries at an end of a B-tree cost planning time and can hold a stale row estimate. Fixture E kept a 10-row estimate for four plans while each marked 100 heap pages' worth of entries dead, and the fifth plan estimated 1 row ([measured](#dead-entries-at-the-end-of-a-b-tree-the-endpoint-probe)).

#### Which access methods share these mechanisms

Four core access methods route through `genericcostestimate()`: B-tree, [hash](../../../glossary.md#hash-index), [GiST](../../../glossary.md#gist) and [SP-GiST](../../../glossary.md#sp-gist) ([selfuncs.c:7073](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7073), [selfuncs.c:7221](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7221), [selfuncs.c:7265](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7265), [selfuncs.c:7320](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7320)). So does [contrib](../../../glossary.md#contrib) `bloom`, the only other caller in the tree.

Bloom is the most exposed of the five. `blcostestimate()` sets the entries read to all of `index->tuples`, because "We have to visit all index tuples anyway" ([blcost.c#blcostestimate](../../../../raw/postgres-17/contrib/bloom/blcost.c#L22-L42)). So `numIndexPages` is the whole index, and a single bloom scan is charged for every page ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)). A repeated bloom scan goes through the same cache model as the others ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779)).

The height charge is B-tree-only in the sense that only B-trees supply a measured height. GiST and SP-GiST fill in their own by assuming a fanout of 100 and taking `log100(index->pages)`, then apply the same formula "calculated the same as for btrees" ([selfuncs.c#gistcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7256-L7308), [selfuncs.c#spgcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7311-L7363)). Their descent charge therefore tracks page count. `hashcostestimate()` adds no descent charge ([selfuncs.c#hashcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7213-L7253)).

| Input | B-tree | Hash | GiST, SP-GiST | contrib `bloom` |
|---|---|---|---|---|
| `pages` in the page share | yes ([selfuncs.c:7073](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7073)) | yes ([selfuncs.c:7221](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7221)) | yes ([selfuncs.c:7265](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7265), [selfuncs.c:7320](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7320)) | yes, the whole index on every scan ([blcost.c#blcostestimate](../../../../raw/postgres-17/contrib/bloom/blcost.c#L22-L42)) |
| `tree_height` | measured fast root ([plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500)) | none ([selfuncs.c#hashcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7213-L7253)) | derived from `pages` ([selfuncs.c#gistcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7256-L7308), [selfuncs.c#spgcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7311-L7363)) | none ([blcost.c#blcostestimate](../../../../raw/postgres-17/contrib/bloom/blcost.c#L22-L42)) |
| Cache model on repeated scans | yes ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779)) | yes ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779)) | yes ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779)) | yes ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779)) |
| Worker count from `numIndexPages` | yes ([costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L772)) | no ([hash.c:75](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L75)) | no ([gist.c:77](../../../../raw/postgres-17/src/backend/access/gist/gist.c#L77), [spgutils.c:62](../../../../raw/postgres-17/src/backend/access/spgist/spgutils.c#L62)) | no ([blutils.c:124](../../../../raw/postgres-17/contrib/bloom/blutils.c#L124)) |
| Descent clamp | yes ([selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042)) | no | no | no |
| Endpoint probe | yes, plain B-trees only ([selfuncs.c#get_actual_variable_range-index-choice](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6179-L6239)) | no | no | no |

The worker row is B-tree's alone because every other access method here sets `amcanparallel = false` (the cited lines), so it never gets a [partial index path](../../../glossary.md#partial-path).

[GIN](../../../glossary.md#gin) and [BRIN](../../../glossary.md#brin) have their own models and never call `genericcostestimate()`; both source comments say their search behavior is "completely different from other index types" ([selfuncs.c#gincostestimate-header](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7662-L7671), [selfuncs.c#brincostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8052-L8061)). Both read `index->pages` ([selfuncs.c:7674](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7674), [selfuncs.c:8063](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8063)), and both reopen the index to read metapage counters that `IndexOptInfo` does not carry:

- `gincostestimate()` reads the live [pending-list](../../../glossary.md#pending-list) page count and the entry-page, data-page and entry counts that the last build or `VACUUM` wrote ([selfuncs.c#gincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7697-L7711), [gininsert.c:406](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L406), [ginvacuum.c:789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L789)). It scales those counts to `index->pages`, or invents them from it when they cannot be trusted ([selfuncs.c#gincostestimate-scale-or-invent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7767)). The [follow-up](#follow-up-when-a-gin-index-is-discarded-and-a-b-tree-is-used-instead) covers GIN.
- `brincostestimate()` reads only `pagesPerRange` and a range-map page count, which are structural values rather than bloat counters ([brin.c#brinGetStats](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1638-L1654), [selfuncs.c#brincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8086-L8101)). It charges every index page on every scan ([selfuncs.c#brincostestimate-page-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8244-L8258)), so BRIN bloat reaches the cost only through `index->pages`; see [Non-B-tree bloat](#non-b-tree-bloat).

Every `pgstatindex` metric on this page is B-tree-only. The function reads B-tree page structures and rejects any other relation with `is not a btree index` ([pgstatindex.c#pgstatindex_impl-btree-check](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L228)). Its [regression test](../../../glossary.md#regression-test) asserts that rejection for a GIN and a hash index ([sql/pgstattuple.sql#wrong-index-type](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L55-L63), [expected/pgstattuple.out#wrong-index-type](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L145-L150)).

### Branches And Exceptional Cases

Each row names a condition that changes what the steps above do, and what that does to a bloated index.

**The page share (step 2) and the cache model (step 4)**

| Condition / state | Behavior | Consequence |
|---|---|---|
| `index->pages <= 1` or `index->tuples <= 1` | `numIndexPages` is a flat 1 ([selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732)) | a table estimated at one row prices a scan of an index of any size at one page ([measured](#the-pages-outnumber-rows-guard-at-its-limit) on 551 blocks) |
| `numIndexTuples * pages <= tuples` | `ceil()` rounds the share up to 1 page (same lines) | a one-row lookup is blind to bloat while the index has no more pages than the table has rows |
| `numIndexTuples * pages > tuples` | the share is `ceil(numIndexTuples * pages / tuples)` pages (same lines) | a drained queue table's one-row lookup is charged several pages: `12.29` against `4.29` rebuilt |
| unique index, equality on every key column, no array or `IS NULL` condition | `numIndexTuples = 1` ([selfuncs.c#btcostestimate-unique-equality](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6991-L7002)) | the two rows above with one entry |
| scan repeated, loops touch well under the index's pages in total | the cache model counts nearly every fetch as new ([costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)) | about one page per loop, whatever the index's size |
| scan repeated, index within its cache share, loops touch at least twice its pages | fetches capped at the whole index (same lines) | the whole index, spread across the loops: linear in pages |
| index larger than its share of `effective_cache_size` | fetches can exceed the index size (same lines) | repeated reads priced beyond the whole index ([measured](#index-pages-in-the-cache-model) at 64MB) |
| index in a tablespace that sets its own `random_page_cost` | that value replaces the setting ([selfuncs.c#genericcostestimate-tablespace](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6734-L6737), [spccache.c#get_tablespace_page_costs](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L181-L196)) | every charged page is weighted by the tablespace's value |

**The size inputs (step 1) and parallel workers (step 4)**

| Condition / state | Behavior | Consequence |
|---|---|---|
| partial index whose row records `reltuples >= 0` and `relpages > 1` | `tuples` = recorded density times live blocks, capped at the table's estimate ([plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160)) | growth since the row was written is charged only in step with the table's growth ([Key Interactions](#key-interactions)) |
| partial index whose row records `relpages <= 1` or `reltuples < 0` | density invented from column widths ([plancat.c#estimate_rel_size-density](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1116-L1146)) | the charge rests on the invented density until the row is rewritten ([Lifecycle](#lifecycle-of-the-planner-inputs)) |
| partitioned index | `pages = 0`, `tuples = 0`, no height ([plancat.c#get_relation_info-partitioned](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L502-L508)) | the parent index contributes no size input |
| access method other than B-tree | `tree_height = -1` ([plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500)) | see [Which access methods share these mechanisms](#which-access-methods-share-these-mechanisms) |
| table has a `parallel_workers` [storage parameter](../../../glossary.md#storage-parameter) | that number is used, with no page counts at all ([allpaths.c#compute_parallel_worker-reloption](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4208-L4213), [reloptions.c#parallel_workers](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L374-L382)) | bloat moves no worker count |
| plain base relation, touched-page estimate below `min_parallel_index_scan_size` | no parallel path ([allpaths.c#compute_parallel_worker-threshold](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4216-L4227)) | bloat can lift a scan over the threshold |
| [inheritance](../../../glossary.md#inheritance) child or partition | exempt from that minimum-size rejection (same lines) | a small child can still get workers from the tripling ramp |

**The endpoint probe (step 6)**

| Condition / state | Behavior | Consequence |
|---|---|---|
| the histogram search never reaches an end bound | no probe ([selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136)) | the stored histogram decides |
| only partial, hypothetical or non-B-tree indexes lead with the column | no probe ([selfuncs.c#get_actual_variable_range-index-choice](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6179-L6239)) | the stored bound is used |
| a live row within 100 visited heap pages | the live value replaces the bound ([selfuncs.c#get_actual_variable_endpoint-limit](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6436-L6457)) | a corrected estimate |
| more than 100 heap pages of [dead rows](../../../glossary.md#dead-tuple) | the probe gives up ([selfuncs.c#get_actual_variable_endpoint-give-up](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6409-L6413)) | a stale estimate, and planning time spent |
| a snapshot old enough to see the deleted rows | they count as recently dead and are accepted ([selfuncs.c#get_actual_variable_endpoint-snapshot](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6376-L6386)) | the deleted extreme is returned at once, and nothing is killed |
| hot standby | killed entries are neither set nor honored ([genam.c#RelationGetIndexScan-recovery](../../../../raw/postgres-17/src/backend/access/index/genam.c#L107-L119)) | every plan walks the same dead entries |

### Lifecycle Of The Planner Inputs

Three pieces of state change over an index's life: its `pg_class` row, a [backend](../../../glossary.md#backend)'s cached copy of its metapage, and the killed marks on its entries. Each table lists the events that change one of them and when later plans see the change.

**The index's `pg_class` row.** Only a partial index's charge reads this row, through its recorded density ([plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160)); a write to the row also sends the [relcache](../../../glossary.md#relcache) [invalidation](../../../glossary.md#invalidation-message) that refreshes the cached height below.

| Event | State before | State after | Effect on later calculation |
|---|---|---|---|
| `CREATE INDEX` | no row | the row starts at `relpages = 0`, `reltuples = 0` ([index.c#index_create-pg_class](../../../../raw/postgres-17/src/backend/catalog/index.c#L1008-L1024), [relcache.c#RelationBuildLocalRelation-rd_rel](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3656-L3659)); the build then writes its own counts ([index.c#index_update_stats-write](../../../../raw/postgres-17/src/backend/catalog/index.c#L2835-L2923)) | a partial index's density is the build's |
| empty B-tree build | as above | `relpages = 1`, the metapage alone ([nbtsort.c#_bt_load-first-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1287-L1290), [nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1063-L1128)) | `relpages <= 1`: a partial index takes the width-based density |
| [`REINDEX`](../../../glossary.md#reindex) or `TRUNCATE` | any counts | reset to `relpages = 0`, `reltuples = -1` ([relcache.c#RelationSetNewRelfilenumber-reset](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3948-L3954)); a rebuild with entries writes its counts, one with none leaves the reset ([index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842)) | after an empty rebuild, the width-based density until the row is rewritten |
| build during binary upgrade ([`pg_upgrade`](../../../glossary.md#pg_upgrade)) | no row | counts never written, so `relpages = 0` (same lines) | the width-based density until `ANALYZE` |
| inserts, updates, page splits | recorded counts | unchanged; only the file grows | non-partial: charged at once through live `pages`; partial: charged only in step with the table's growth |
| `VACUUM` with index cleanup, when the access method measured its counts exactly | old counts | rewritten through `vac_update_relstats()` ([vacuumlazy.c#heap_vacuum_rel-index-stats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L512-L513), [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099)), unless nothing changed ([vacuum.c#vac_update_relstats-dirty](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1446-L1461)) | a partial index's charge catches up |
| `VACUUM` whose index counts are estimated or absent, or with index cleanup off | old counts | not written (same `update_relstats_all_indexes` lines); a B-tree `VACUUM` that never ran `btbulkdelete()` returns no counts or estimated ones ([nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L851-L893)) | the lag continues |
| `ANALYZE` | old counts | every index's row rewritten with its live block count ([analyze.c#do_analyze_rel-index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663)) | fixture Q: 113 charged pages became 331 |

**A backend's cached copy of the metapage.** `_bt_getrootheight()` prices from this copy when it exists ([nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717)).

| Event | State before | State after | Effect on later calculation |
|---|---|---|---|
| first plan, scan or insert in a backend | no copy | the metapage is cached in `rd_amcache` (same lines, [nbtpage.c#_bt_getroot-cache](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L523-L528), [nbtpage.c#_bt_metaversion-cache](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L773-L775)) | later plans in that backend reuse it |
| a relcache invalidation of the index | cached | freed ([relcache.c#RelationCacheInvalidateEntry](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2975-L2985), [relcache.c#RelationFlushRelation](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2916-L2924), [relcache.c#RelationClearRelation](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2600-L2603)) | the next plan reads a fresh metapage |
| `VACUUM` or `ANALYZE` changes the index's `pg_class` counts | cached | an in-place update registers an invalidation and sends it when the write completes ([heapam.c:6668](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6668), [inval.c#CacheInvalidateHeapTupleCommon-pg_class](../../../../raw/postgres-17/src/backend/utils/cache/inval.c#L1383-L1392), [heapam.c#heap_inplace_update_and_unlock-send](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6888-L6892)); planning locks the index and absorbs it ([plancat.c:253](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L253), [lmgr.c#LockRelationOid-accept](../../../../raw/postgres-17/src/backend/storage/lmgr/lmgr.c#L134-L138)) | fresh at the next plan, as the nbtree README expects ([README#metapage-cache](../../../../raw/postgres-17/src/backend/access/nbtree/README#L776-L790)) |
| `vac_update_relstats()` finds the counts unchanged | cached | nothing written, and the registered invalidation discarded ([vacuum.c#vac_update_relstats-dirty](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1446-L1461), [vacuum.c#vac_update_relstats-inplace](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1545-L1548), [heapam.c#heap_inplace_unlock](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6914-L6920)) | the copy stays |
| a scan finds the cached fast root deleted, half-dead, at another level or not alone | cached | discarded and re-read ([nbtpage.c#_bt_getroot-stale-cache](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L380-L403), [nbtree.h:225](../../../../raw/postgres-17/src/include/access/nbtree.h#L225)) | refreshed in that backend only |
| `_bt_gettrueroot()` runs | cached | flushed unconditionally ([nbtpage.c#_bt_gettrueroot-flush](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L592-L600)) | refreshed in that backend |
| a [root split](../../../glossary.md#page-split) | cached | the metapage alone is rewritten, with no catalog change ([nbtinsert.c#_bt_newlevel-metapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2515-L2519)) | other backends keep the old height |
| a split of the only page on a level below the true root | cached | the fast root moves up in the metapage alone ([nbtinsert.c#_bt_insertonpg-fastroot](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1250-L1295)) | stale until another event refreshes it |

**Killed marks on index entries, as the endpoint probe uses them.**

| Event | State before | State after | Effect on later calculation |
|---|---|---|---|
| `DELETE` of the rows at an end of the key range, no `VACUUM` | live entries | entries pointing at dead heap rows | the next range estimate there probes them ([selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136)) |
| a probe passes dead entries within its 100-page limit | unmarked | marked killed, except the entry at which it gives up ([indexam.c#index_fetch_heap-kill](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L644-L652), [nbtree.c#btgettuple-kill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L226-L245)) | the next probe skips them without heap visits |
| a probe reaches a live entry | the stored bound in use | the live value used ([selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136)) | fixture E's estimate fell from 10 rows to 1 |

### Key Interactions

The surprising results come from components that read different values for the same index.

**A partial index cancels its own growth.** `estimate_rel_size()` makes a partial index's `tuples` grow with its live pages, at the recorded density ([plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160)). `btcostestimate()` sizes the scan from the table's row estimate instead ([selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019)). In `ceil(numIndexTuples * pages / tuples)`, the live page count therefore appears once on top and once, through `tuples`, underneath. The index's own growth cancels, and only the table's growth moves the charge. The cancellation ends when `tuples` reaches the table's estimate and the cap binds, or when the row is rewritten ([Lifecycle](#lifecycle-of-the-planner-inputs)).

**ScalarArrayOp descents divide and multiply the entry count.** `btcostestimate()` divides the entry count by the clamped `num_sa_scans` and rounds it ([selfuncs.c:7064](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7064)); `genericcostestimate()` multiplies it back ([selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810)). The two cancel except in two ways. `rint()` rounding moves the product: fixture I's 8-block index, clamped to 3 descents, is charged `rint(10 / 3) * 3 = 9` entries for a ten-element array and `rint(4 / 3) * 3 = 3` for a four-element one. And a floor of one entry per descent ([selfuncs.c#genericcostestimate-tuple-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6707-L6715)) makes the term `num_sa_scans * (cpu_index_tuple_cost + qual_op_cost)` whenever descents outnumber estimated rows. There a bloated index's higher clamp raises it too.

**The cache model and the page share read different sizes.** The page share of step 2 can stay at one page per loop, while `index_pages_fetched()` uses the whole `index->pages` as its set of pages ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779)). A lone lookup is priced from the first and a repeated one from the second. That is why the nested loop sees bloat that the single lookup does not.

**The endpoint probe reaches the cost through the row estimate.** The probe changes the selectivity, the selectivity sets `numIndexTuples` ([selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019)), and `numIndexTuples` scales both the page share and the per-entry charge ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732), [selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810)). The dead entries' own pages are charged only as ordinary blocks of `index->pages`.

**`pgstatindex` and the planner count different pages.** `avg_leaf_density` averages over live leaf pages only. Deleted and half-dead pages are counted apart ([pgstatindex.c#pgstatindex_impl-pages](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L331)), yet they remain blocks of the file that step 1 counts. So a high density can sit on an index ten times larger than it needs to be ([measured](#two-indexes-with-the-same-cost-and-opposite-avg_leaf_density), fixture M).

### Formulas

**Terms.** `pages` is `index->pages` and `tuples` is `index->tuples`, both from step 1. `k` is `numIndexTuples`, the entries one descent reads. `L` is the loop count of a nested-loop inner scan, and `s` is the ScalarArrayOp descent count after the v17 clamp (1 without an array). `h` is `tree_height`. `rpc` is `random_page_cost`, or the index tablespace's value; `cot` is `cpu_operator_cost`; `cit` is `cpu_index_tuple_cost`; `q` is the number of index conditions. `T`, `N` and `b` are defined with the Mackert-Lohman formula below.

**Pages one descent touches** ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)):

```text
numIndexPages = ceil(k * pages / tuples)    when pages > 1 and tuples > 1
numIndexPages = 1                           otherwise
```

In plain words: a scan reads the same fraction of the index's pages as of its entries, and never less than one page.

**Page I/O, per loop** ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779), [selfuncs.c#genericcostestimate-single-scan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6780-L6787)):

```text
I/O = numIndexPages * rpc                                  when L * s = 1
I/O = PF(N = numIndexPages * L * s, T = pages) * rpc / L   when L * s > 1
```

**Mackert-Lohman `PF`** ([costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)). `N` is the page fetches the scans would make with no cache. `T` is the index's pages. `b` is the index's share of `effective_cache_size`: `ceil(effective_cache_size * T / (table pages in the query + T))`.

```text
PF = min(ceil(2TN / (2T + N)), T)              when T <= b
PF = ceil(2TN / (2T + N))                      when T > b and N <= 2Tb / (2T - b)
PF = ceil(b + (N - 2Tb / (2T - b)) * (T - b) / T)   when T > b and N > 2Tb / (2T - b)
```

In plain words: while `N` is small next to `T`, `2TN / (2T + N)` is close to `N`, so nearly every fetch is charged. The expression reaches `T` exactly when `N = 2T`, because `2TN / (2T + N) = T` solves to `N = 2T`. So an index within its cache share is never charged more than its whole size. An index larger than its share can be charged more than that.

**Per-entry CPU** ([selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810)): `k * s * (cit + q * cot)`, plus the one-time cost of evaluating non-constant comparison values.

**B-tree descents** ([selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091), [selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)):

```text
per descent  = ceil(log2(tuples)) * cot  +  (h + 1) * 50 * cot
startup     += per descent
total       += s * per descent
```

The first term is omitted when `tuples <= 1`. In plain words: one level is worth `50 * cot`, and every descent pays for all levels plus the leaf.

**The v17 descent clamp** ([selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042)): `s = max(1, min(estimated descents, ceil(pages * 0.3333333)))`. In plain words: a B-tree is never charged for more descents than a third of its pages.

`cost_index()` adds the heap side and `cpu_tuple_cost` for each row it expects to return ([costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747), [costsize.c#cost_index-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L795-L800)). On an all-visible table an index-only scan fetches no heap pages, so the measured totals in [Exact-Pin Measurements](#exact-pin-measurements) add only the row term. Each of those subsections works its costs through these formulas, step by step.

### What The Planner Does Not See

The planner sees bloat only as pages and levels. This table takes the bloat signals an operator might look at and says whether any planner input carries them.

| Bloat signal | Seen by the v17 planner? | Why |
|---|---|---|
| More blocks for the same useful keys | Yes | They raise `index->pages`, and with it the pro-rata page share `numIndexPages` ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)); see [Step 2](#step-2-charge-the-pages-a-scan-touches) |
| An extra B-tree level | Yes | Each fast-root level adds `50 * cpu_operator_cost` to every descent ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)); see [Step 3](#step-3-charge-the-b-tree-height) |
| Deleted, half-dead or empty pages | Yes, as ordinary pages | They are blocks of the main fork, and the block count covers that fork whole ([bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L280-L281)); the note below the table says what a scan does with them |
| Low `avg_leaf_density` from `pgstatindex` | Only through extra pages or levels | `IndexOptInfo` has no density field ([pathnodes.h#IndexOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1120-L1128)), so low density costs something only when it leaves more blocks or levels behind |
| High `leaf_fragmentation` from `pgstatindex` | No | No planner input carries it ([pathnodes.h#IndexOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1120-L1128)); its measured contribution is exactly zero ([Leaf fragmentation contributes exactly zero](#leaf-fragmentation-contributes-exactly-zero)) |
| Free space recorded in the index [FSM](../../../glossary.md#free-space-map) | No | No file under `src/backend/optimizer/`, and neither `selfuncs.c` nor contrib `bloom`'s `blcost.c`, calls into the FSM, a grep recorded in the [Evidence Map](#evidence-map); a free page is still a block of the main fork ([bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L280-L281)) |
| Index entries that VACUUM removed | No, for a non-partial index | Its `tuples` is the table's row estimate, not its entry count ([plancat.c:476](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L476)) |
| Growth of a partial index since its `pg_class` row was written | Only in step with the table's growth | Its `tuples` grows with its live blocks at the recorded density, so its own growth nearly cancels in the page share ([plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160), [selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019)); see [Step 1](#step-1-read-the-index-size) |
| Where inside the index the useful entries sit | No | The page share is a flat fraction of the whole index ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)) |
| Dead entries at either end of a B-tree | Not as a cost; they can hold a row estimate at a stale value | A range comparison that reaches a histogram end reads them while planning, and gives up after more than 100 heap-page visits that found no usable row ([selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136), [selfuncs.c#get_actual_variable_endpoint-limit](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6436-L6457)); see [Step 6](#step-6-probe-the-ends-of-a-b-tree-while-estimating-rows) |

The planner charges deleted, half-dead and empty pages alike, but a scan treats them differently:

- A deleted page has been unlinked from its siblings, so no scan that starts after the unlink reaches it ([nbtpage.c#_bt_unlink_halfdead_page-siblings](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2597-L2612)).
- A half-dead page is still in the sibling chain, so a scan that steps right reads it and skips it ([README#half-dead](../../../../raw/postgres-17/src/backend/access/nbtree/README#L247-L259), [nbtsearch.c#_bt_readnextpage-step-right](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2207-L2219)).
- An empty page that is not being deleted is read like any other. The rightmost page of a level is one such page, because it is never deleted ([README#page-deletion-and-tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L362-L381)).

The estimate's own guards can still collapse the charge for all of them to one page, which [The pages-outnumber-rows guard at its limit](#the-pages-outnumber-rows-guard-at-its-limit) measures.

The two `pgstatindex` metrics people reach for are computed from live leaf pages only. Deleted and half-dead pages are counted separately and left out of the density and fragmentation arithmetic, although they *are* included in the reported `index_size`:

```c
if (P_ISDELETED(opaque))
    indexStat.deleted_pages++;
else if (P_IGNORE(opaque))
    indexStat.empty_pages++;   /* this is the "half dead" state */
else if (P_ISLEAF(opaque))
{
    ...
    if (opaque->btpo_next != P_NONE && opaque->btpo_next < blkno)
        indexStat.fragments++;
}
```

([pgstatindex.c#pgstatindex_impl-pages](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L331), [pgstatindex.c#pgstatindex_impl-density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L372))

So `avg_leaf_density` answers "how full are the leaf pages that still hold data", and `leaf_fragmentation` answers "how often does the right-sibling link point backwards". The B-tree cost model asks two different questions about the index's physical state: how many blocks to charge ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)), and how many levels lie below the fast root ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)). Neither metric answers either question. [Two indexes with the same cost and opposite avg_leaf_density](#two-indexes-with-the-same-cost-and-opposite-avg_leaf_density) shows an index reading 89.18% density while it is about ten times larger than it needs to be.

### Types Of Bloated Indexes

This page calls an index bloated when it holds more pages than its useful entries need, because those extra pages are what the planner charges for. The manual's glossary defines bloat more narrowly, as space in data pages that holds no current row versions, "such as unused (free) space or outdated row versions" ([glossary.sgml#Bloat](../../../../raw/postgres-17/doc/src/sgml/glossary.sgml#L242-L250)).

Two shapes below fit only the broader sense, because their extra pages hold current entries, not dead ones. An index with [deduplication](../../../glossary.md#deduplication) turned off stores each duplicate as its own leaf tuple instead of merging the group into one [posting list](../../../glossary.md#posting-list) ([btree.sgml#deduplication](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L736-L800)). A GIN pending list is deferred insert work: GIN adds new entries to an unsorted list and moves them into the main structure later, in bulk ([gin.sgml#fast-update](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L503-L529)). The wiki's GIN measurement protocol therefore does not score pending pages as waste ([Mandatory GIN Bloat Tests (unverified)](../../common-concepts/mandatory-gin-bloat-tests.md)). Yet `gincostestimate()` charges a single scan for every pending page at `random_page_cost` ([selfuncs.c#gincostestimate-pending](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7882-L7886), [selfuncs.c#gincostestimate-random-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7976-L7980)).

The eight shapes differ along the same four dimensions:

| Shape | How it arises | What `pgstatindex` shows | What the planner charges | What removes it |
|---|---|---|---|---|
| [Low-density live leaf pages](#low-density-live-leaf-pages) | Scattered deletions leave leaf pages allocated but nearly empty ([maintenance.sgml#routine-reindex](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1032-L1040)) | Low `avg_leaf_density`: 9.27% in fixture B ([pgstatindex.c#pgstatindex_impl-density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L372)) | Every block ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)) | A rebuild ([ref/reindex.sgml#bloated](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml#L54-L64)) |
| [Deleted and half-dead pages](#deleted-and-half-dead-pages) | VACUUM deletes empty leaf pages, which stay in the file ([nbtpage.c#_bt_unlink_halfdead_page-deleted](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2628-L2659)) | Counted apart and left out of the density: 89.18% in fixture M ([pgstatindex.c#pgstatindex_impl-pages](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L331)) | Every block, deleted ones included ([bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L280-L281)) | A rebuild; [recycling](../../../glossary.md#index-page-recycling) reuses the blocks but never returns them ([nbtpage.c#_bt_allocbuf-fsm](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L901-L905)) |
| [Extra tree levels](#extra-tree-levels) | A root split adds a level ([nbtinsert.c#_bt_newlevel-metapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2515-L2519)), and sparse pages need more of them for the same keys | `tree_level`, the true root's level ([pgstatindex.c#pgstatindex_impl-metapage](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L252-L265)) | `50 * cpu_operator_cost` per fast-root level per descent ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)) | A rebuild; page deletion can lower the fast root ([nbtpage.c#_bt_unlink_halfdead_page-fastroot](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2565-L2659)) |
| [Physically fragmented leaf chains](#physically-fragmented-leaf-chains) | A split can append its new right half at the end of the file ([nbtpage.c#_bt_allocbuf](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L868-L988)) | `leaf_fragmentation`, which counts backward links only ([pgstatindex.c#pgstatindex_impl-fragments](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323)) | Nothing ([pathnodes.h#IndexOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1120-L1128)) | A rebuild restores physical order ([maintenance.sgml#fresh-index](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1048-L1054)) |
| [Version-churn duplicates](#version-churn-duplicates-from-non-hot-updates) | A non-HOT `UPDATE` adds an entry to every index that accepts the new row ([btree.sgml#version-churn](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L638-L655), [execIndexing.c#ExecInsertIndexTuples-predicate](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L368-L387)) | More leaf pages, not necessarily lower density: 98.01% in fixture P's unblocked run | Every block ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)) | Bottom-up deletion limits it while no old snapshot still needs the rows ([README#deduplication-and-bottom-up-note](../../../../raw/postgres-17/src/backend/access/nbtree/README#L980-L988)) |
| [Deduplication disabled](#duplicate-heavy-indexes-with-deduplication-disabled) | Each duplicate is stored as its own tuple ([btree.sgml#deduplication](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L736-L800)) | Normal density on more pages: 2,749 blocks at 90.16% against 852 in fixture N | Every block ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)) | `deduplicate_items` on, for an [`allequalimage`](../../../glossary.md#allequalimage) index, at the next pre-split pass or rebuild ([nbtinsert.c#_bt_delete_or_dedup_one_page-dedup-gate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2778-L2781), [nbtsort.c#_bt_load-deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1151-L1152)) |
| [Bloat VACUUM skipped](#bloat-that-vacuum-deliberately-skipped) | The 2% bypass, the [wraparound failsafe](../../../glossary.md#vacuum-failsafe) or `INDEX_CLEANUP OFF` skip [index vacuuming](../../../glossary.md#index-vacuuming) ([vacuumlazy.c#lazy_vacuum-bypass-branch](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949), [vacuumlazy.c#lazy_check_wraparound_failsafe-clears](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326), [vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402)) | The skipped entries still occupy leaf space, and the density counts that space as used ([pgstatindex.c#pgstatindex_impl-pages](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L331)) | Every block ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)) | A later VACUUM that runs index vacuuming ([vacuumlazy.c#lazy_vacuum-index-vacuuming](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1950-L1956)) |
| [Non-B-tree bloat](#non-b-tree-bloat) | Growth of hash, GiST, SP-GiST, BRIN and GIN indexes, which the manual calls not well researched ([maintenance.sgml#routine-reindex-non-btree](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1042-L1046)) | Nothing: `pgstatindex` rejects them ([pgstatindex.c#pgstatindex_impl-btree-check](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L228)) | Pages, through each access method's own `amcostestimate` ([costsize.c#cost_index-amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L610-L621)); see [Which access methods share these mechanisms](#which-access-methods-share-these-mechanisms) | A rebuild ([ref/reindex.sgml#bloated](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml#L54-L64)) |

#### Low-density live leaf pages

This is the classic case the manual describes: scattered deletions leave every leaf page allocated but nearly empty ([maintenance.sgml#routine-reindex](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1032-L1040)). Fixture B deleted 90% of 1,000,000 rows with `id % 10 <> 0` and was vacuumed twice. Its index kept **2,745 blocks, 2,733 of them live leaf pages and none deleted, at 9.27% `avg_leaf_density`**.

It is the one shape on which `avg_leaf_density` and the planner agree, because low density here means a high `pages / tuples` ratio ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)).

How full a page is left depends on how it was last filled. A build and each kind of page split aim at a different target, set by the index's [fillfactor](../../../glossary.md#fillfactor) or by fixed constants ([nbtree.h#fillfactor-comment](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L197)):

| Event | The (left) page is filled to | Source |
|---|---|---|
| Index build | leaf pages: the index fillfactor, 90 by default; pages above the leaf level: 70 | [nbtsort.c#_bt_pagestate-leaf-fill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L661-L665), [nbtree.h#BTREE_DEFAULT_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L200-L202) |
| Rightmost leaf split | the index fillfactor | [nbtsplitloc.c#_bt_findsplitloc-fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L334) |
| Leaf split recognized as a localized ascending insertion ("split after new item") | the index fillfactor, or exactly after the new item | [nbtsplitloc.c#_bt_findsplitloc-fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L334) |
| Rightmost internal split | `BTREE_NONLEAF_FILLFACTOR`, 70 | [nbtsplitloc.c#_bt_findsplitloc-fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L334), [nbtree.h#BTREE_DEFAULT_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L200-L202) |
| Any other leaf or internal split | about half: the lowest-penalty split point among those close to an even balance of free space | [nbtsplitloc.c#_bt_deltasortsplits](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L561-L588), [nbtsplitloc.c#_bt_defaultinterval](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L852-L920), [nbtsplitloc.c#_bt_bestsplitloc](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L770-L812) |
| Leaf page with many duplicates, not all one value | either side of the group of duplicates around the balance point, which can leave the halves far from equal | [nbtsplitloc.c#_bt_findsplitloc-many-duplicates](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L374-L405), [nbtsplitloc.c#_bt_strategy-many-duplicates](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L985-L1009) |
| Leaf page entirely of one value, the last page holding it | `BTREE_SINGLEVAL_FILLFACTOR`, 96 | [nbtsplitloc.c#_bt_findsplitloc-single-value](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L389-L416), [nbtsplitloc.c#_bt_strategy-single-value](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L1011-L1041) |

The "about half" row is near-equal, not exact. On a leaf page the split penalty favors a point that lets [suffix truncation](../../../glossary.md#suffix-truncation) drop more attributes from the new high key; on an internal page it favors the smallest new [pivot](../../../glossary.md#pivot-tuple) ([nbtsplitloc.c#_bt_split_penalty](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L1119-L1153)).

A split target is not a ceiling. Between splits, inserts keep filling a page until the next item no longer fits ([nbtinsert.c#_bt_insertonpg-split-check](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1203-L1210)). Fixture P's 1,000-value `tag` index shows the effect: churned without a held snapshot, it reads 98.01% after five update rounds, above the 91.47% its build left under the default fillfactor of 90. Which mechanisms filled its pages is not traced; see [Open Questions](#open-questions).

The per-index `fillfactor` reloption takes [`ShareUpdateExclusiveLock`](../../../glossary.md#shareupdateexclusivelock), because it affects only later inserts ([reloptions.c#intRelOpts-fillfactor-btree](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L185-L194)). [Settings That Move The Boundary](#settings-that-move-the-boundary) says which later splits it reaches.

#### Deleted and half-dead pages

When a leaf page becomes completely empty, VACUUM can delete it. The page stays in the relation as a tombstone. Its own sibling links stay intact ([nbtpage.c#_bt_unlink_halfdead_page-side-links](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2597-L2600)), and it is labelled with a `safexid` ([nbtpage.c#_bt_unlink_halfdead_page-deleted](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2628-L2659)). It becomes recyclable only once no scan can still hold a reference to it ([README#placing-deleted-pages-in-the-fsm](../../../../raw/postgres-17/src/backend/access/nbtree/README#L383-L441)).

Recycling reuses a block but never returns it to the operating system. VACUUM records a recyclable page in the FSM with `RecordFreeIndexPage()` ([nbtree.c:1168](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1168), [nbtpage.c:3050](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L3050)), and `_bt_allocbuf()` asks `GetFreeIndexPage()` for such a page before it extends the file ([nbtpage.c#_bt_allocbuf-fsm](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L901-L905)). Nothing under `src/backend/access/nbtree/` calls `RelationTruncate()` or `smgrtruncate()`, a grep. So the blocks stay inside `RelationGetNumberOfBlocks()` and stay charged, recycled or not ([bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L280-L281)).

Fixture M deleted a *contiguous* 90% (`id > 100000`), which let VACUUM empty whole pages. The index kept **2,745 blocks: 276 live leaf pages, 2,465 deleted pages**, 3 internal pages and the metapage, at an `avg_leaf_density` of **89.18%**. A second and a third VACUUM did not shrink the file; `REINDEX` cut it to 276 blocks.

This is the shape on which `avg_leaf_density` misleads about size. The planner does see the size, and it overcharges fixture M's scans. By the source, a whole-index scan walks only the 276 live leaves, because VACUUM unlinked each deleted page from its level's sibling chain ([nbtpage.c#_bt_unlink_halfdead_page-siblings](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2597-L2612)). The planner still prices that scan at `12730.42`, the same as fixture B, whose scan walks 2,733 live leaves.

#### Extra tree levels

A taller tree means more pages per descent, so the level charge of [Step 3](#step-3-charge-the-b-tree-height) fires. Fixture H built 50,000 rows into a 139-block index at `fastlevel = 1`, and the same 50,000 rows at `fillfactor = 10` into a 1,323-block index at `fastlevel = 2`. The point lookup rose from `8.31` to `8.43`. The gap before rounding is exactly the `0.125` level charge, which [The tree-height charge, isolated to the cent](#the-tree-height-charge-isolated-to-the-cent) reads as `50.00` at `cpu_operator_cost = 1`.

The README's rule that the height of the tree cannot decrease is about the true root, `btm_level` ([README#page-deletion-and-tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L362-L381)). The planner charges the fast root's level instead, and page deletion does lower that one ([nbtpage.c#_bt_unlink_halfdead_page-fastroot](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2565-L2659)). In fixture F, deleting all but the top 1,000 of 1,000,000 keys and vacuuming twice, with no rebuild, left `tree_level` at 2 and moved `fastlevel` from 2 to 1. That removed one level charge from every scan of the index.

#### Physically fragmented leaf chains

`leaf_fragmentation` counts the leaf pages whose right sibling lives at a lower block number ([pgstatindex.c#pgstatindex_impl-fragments](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323)). It rises when pages split in the middle of the key space.

The cause is where a split's new right half goes. `_bt_allocbuf()` supplies it ([nbtinsert.c:1720](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1720)): a recycled page from the FSM if one is there, and otherwise a new block at the end of the file ([nbtpage.c#_bt_allocbuf](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L868-L988)). An appended right half then links right to an older page at a lower block number, which counts as a fragment.

Only VACUUM records recyclable pages in the FSM ([nbtree.c:1168](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1168), [nbtpage.c:3050](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L3050)). So an index filled by random-order inserts with no page deletion behind it, like fixture G's, appends every split. After deletions, a split's new page can land at a low block number instead, and its links point whichever way the recycled block happens to lie.

The metric under-reports, because only *backward* links count ([pgstatindex.c#pgstatindex_impl-fragments](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323)). A right-sibling link that jumps a thousand blocks forward is no more physically adjacent than one that points backwards, yet it scores nothing. The manual ties physical adjacency to real runtime cost ([maintenance.sgml#fresh-index](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1048-L1054)). The planner never reads the metric, so its measured contribution to cost is exactly `0.00` ([Leaf fragmentation contributes exactly zero](#leaf-fragmentation-contributes-exactly-zero)).

#### Version-churn duplicates from non-HOT UPDATEs

Every index is [*HOT-blocking*](../../../glossary.md#hot-blocking-column) except a [summarizing index](../../../glossary.md#summarizing-index) such as BRIN, whose columns the relcache collects in a separate set ([relcache.c#RelationGetIndexAttrBitmap-summarizing](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L5390-L5398)). An `UPDATE` that modifies a column of a HOT-blocking index cannot be HOT ([heapam.c#heap_update-hot-decision](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4140-L4166)). It then writes a new entry into every index that accepts the new row, including indexes whose own columns did not change ([btree.sgml#version-churn](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L638-L655), [execIndexing.c#ExecInsertIndexTuples-loop](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L343-L387)). Those entries are logically unchanged duplicates.

The manual states this more strongly than the code. It says that changing one indexed column "always" requires a new index tuple in "each and every" index ([btree.sgml#version-churn](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L638-L655)). The source makes the two exceptions below. This page follows the source, and the discrepancy is recorded under [Open Questions](#open-questions).

- **Only summarizing-index columns changed, and the new version fits on the old page.** `heap_update()` considers HOT only when the new version stays on the same page (`newbuf == buffer`); otherwise it just marks the old page as full ([heapam.c#heap_update-hot-decision](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4140-L4166)). Inside that branch, an update that touches no HOT-blocking column is HOT. If it touched summarized columns, it reports `TU_Summarizing`, "Only summarized columns were updated, TID is unchanged" ([heapam.c#heap_update-update-indexes](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4415-L4429), [tableam.h#TU_UpdateIndexes](../../../../raw/postgres-17/src/include/access/tableam.h#L113-L127)).
- **The summarizing case then skips every other index.** `ExecUpdateEpilogue()` passes `TU_Summarizing` on as `onlySummarizing` ([nodeModifyTable.c#ExecUpdateEpilogue-onlySummarizing](../../../../raw/postgres-17/src/backend/executor/nodeModifyTable.c#L2162-L2166)), and `ExecInsertIndexTuples()` then skips every non-summarizing index ([execIndexing.c#ExecInsertIndexTuples-onlySummarizing](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L361-L366)). So a BRIN-indexed column can churn without adding one B-tree entry, but only while the updated rows keep fitting on their own pages. Once one does not, `heap_update()` reports `TU_All` ([heapam.c:4429](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4429)), and every index that accepts the new row gets an entry. Changing only summarizing columns is necessary for the exception, not sufficient.
- **A partial index whose predicate the new row fails.** `ExecInsertIndexTuples()` evaluates each partial index's predicate against the new tuple and skips the insert when it is not satisfied ([execIndexing.c#ExecInsertIndexTuples-predicate](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L368-L387)). Every other index that accepts the row, unrelated non-partial B-trees included, still gets an entry ([execIndexing.c#ExecInsertIndexTuples-loop](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L343-L387)).

nbtree fights the duplicates it does get with [bottom-up index deletion](../../../glossary.md#bottom-up-index-deletion), a pass triggered when a version-churn page split is anticipated ([btree.sgml#bottom-up-deletion](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L656-L678), [nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L280-L320), [nbtinsert.c#_bt_delete_or_dedup_one_page-dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2782)). [v14: bottom-up index deletion](#v14-bottom-up-index-deletion) names the commit that added it.

Fixture P ran five whole-table non-HOT `UPDATE` rounds over 200,000 rows. They grew an unrelated index on a 1,000-value column from 169 to **543 blocks**. The identical workload with a long-lived [`REPEATABLE READ`](../../../glossary.md#isolation-level) snapshot open in another session grew it to **1,173 blocks** instead. The README names such a snapshot as what keeps deletion from freeing tuples ([README#deduplication-and-bottom-up-note](../../../../raw/postgres-17/src/backend/access/nbtree/README#L980-L988)).

The benefit depends on the shape of the index. Over a 100-value column the same workload grew the index from 180 to **1,020 blocks in both runs**, so there the unheld [horizon](../../../glossary.md#xmin-horizon) bought nothing. [Version churn with and without a held snapshot](#version-churn-with-and-without-a-held-snapshot) has the full measurements.

#### Duplicate-heavy indexes with deduplication disabled

Deduplication merges duplicate leaf tuples into posting lists in two places. A build merges each group of duplicates before it adds the group to the leaf page it is filling ([btree.sgml#btree-deduplication-build](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L786-L797)). An insert runs a deduplication pass lazily, at the point a page would otherwise split ([btree.sgml#deduplication](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L736-L800), [README#notes-about-deduplication](../../../../raw/postgres-17/src/backend/access/nbtree/README#L904-L948), [nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L33-L58)). Deduplication is on by default, and the `deduplicate_items` reloption turns it off per index ([reloptions.c#deduplicate_items](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L167)).

The reloption is not the only gate. Both paths also require the index to be `allequalimage`. `CREATE INDEX` or `REINDEX` decides that once, from each key column's [operator class](../../../glossary.md#operator-class) and collation, and stores it in the metapage ([nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183), [nbtsort.c#_bt_leafbuild-allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L560-L564)). The build checks it beside the reloption, and also skips deduplication for a unique index ([nbtsort.c#_bt_load-deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1151-L1152)). The insert-time pass checks it beside the reloption ([nbtinsert.c#_bt_delete_or_dedup_one_page-dedup-gate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2778-L2781)).

The manual lists what never qualifies: `text`, `varchar` and `char` under a [nondeterministic collation](../../../glossary.md#nondeterministic-collation), `numeric`, `jsonb`, `float4` and `float8`, container types such as composites, arrays and ranges, and every index with `INCLUDE` columns, that is every [covering index](../../../glossary.md#covering-index) ([btree.sgml#deduplication-restrictions](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L834-L908)). A duplicate-heavy index of one of those kinds keeps every duplicate as its own tuple, whatever `deduplicate_items` says.

Fixture N measures the build path. 1,000,000 rows over 100 distinct keys built **852 blocks** with `deduplicate_items = on` and **2,749 blocks** with it off. That is a 3.2x difference in the planner's `pages` input for identical logical content. Both indexes were created after the rows were loaded, so the difference is the build's.

#### Bloat that VACUUM deliberately skipped

Index vacuuming is the step of VACUUM that deletes dead index entries. Three conditions skip it; [v14: VACUUM can skip index vacuuming on its own](#v14-vacuum-can-skip-index-vacuuming-on-its-own) gives the commits that added the first two:

| Condition | When it applies | What it switches off | Does `amvacuumcleanup` still run? |
|---|---|---|---|
| The 2% bypass | `INDEX_CLEANUP` is left at `AUTO`; fewer than `BYPASS_THRESHOLD_PAGES` (2% of `rel_pages`) hold [`LP_DEAD`](../../../glossary.md#line-pointer) items; the [TID](../../../glossary.md#tid) store is under 32MB; and no earlier round of index vacuuming ran in the same VACUUM ([vacuumlazy.c#BYPASS_THRESHOLD_PAGES](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L85-L89), [vacuumlazy.c#lazy_vacuum-bypass](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1880-L1949), [vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402), [vacuumlazy.c#lazy_scan_heap-bypass-off](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L894-L896)) | `do_index_vacuuming` only ([vacuumlazy.c#lazy_vacuum-bypass-branch](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949)) | Yes |
| The wraparound failsafe | the table's `relfrozenxid` is older than `vacuum_failsafe_age`, or its `relminmxid` older than `vacuum_multixact_failsafe_age`, each raised to at least 1.05 times the matching autovacuum freeze maximum ([vacuum.c#vacuum_xid_failsafe_check](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1252-L1297), [vacuumlazy.c#lazy_check_wraparound_failsafe](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2287-L2347)) | `do_index_vacuuming` and `do_index_cleanup` ([vacuumlazy.c#lazy_check_wraparound_failsafe-clears](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326)) | No |
| `INDEX_CLEANUP OFF` | the `VACUUM` option, or the `vacuum_index_cleanup = off` reloption when the command does not set one ([vacuum.c#vacuum_rel-index-cleanup-reloption](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2156-L2178)) | both, before the scan starts ([vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402)) | No |

The 2% bypass is not a skip of all index maintenance, and reading it that way overstates how much bloat it can hide. The branch that takes it says so in as many words, "bypass index vacuuming, but do index cleanup" ([vacuumlazy.c#lazy_vacuum-bypass-branch](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949)). So `amvacuumcleanup` still runs, and what that buys depends on the access method:

| AM | Under the 2% bypass |
|---|---|
| B-tree | No entry is deleted. `btvacuumcleanup()` is still called, with `stats == NULL`, and asks `_bt_vacuum_needs_cleanup()`; when that says yes, a full `btvacuumscan()` can place previously deleted pages in the FSM ([nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L851-L893)) |
| GIN | `ginvacuumcleanup()` flushes the pending list whenever `ginbulkdelete()` was not called, which covers the bypass ([ginvacuum.c#ginvacuumcleanup-pending](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L719-L729)). When `ginbulkdelete()` does run, it flushes the list itself on its first call ([ginvacuum.c#ginbulkdelete-pending](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L591-L602)) |

The GIN flush also runs in every VACUUM that collected no dead items. Index vacuuming, and with it every `ambulkdelete` call, runs only when dead items exist, while cleanup runs whenever `do_index_cleanup` is set ([vacuumlazy.c#lazy_vacuum-call](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1066)).

The failsafe is the stronger escape hatch, because clearing `do_index_cleanup` too stops `amvacuumcleanup`, and with it the GIN pending-list flush. `INDEX_CLEANUP OFF` has the same effect by request, and the manual warns that the reloption "may also lead to severely bloated indexes if table modifications are frequent" ([ref/create_table.sgml#reloption-vacuum-index-cleanup](../../../../raw/postgres-17/doc/src/sgml/ref/create_table.sgml#L1558-L1575)).

#### Non-B-tree bloat

The manual states plainly that "the potential for bloat in non-B-tree indexes has not been well researched", and it recommends monitoring their physical size ([maintenance.sgml#routine-reindex-non-btree](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1042-L1046)). The wiki's protocol for measuring waste in hash, GiST, SP-GiST and BRIN indexes is [Mandatory Non-B-Tree, Non-GIN Bloat Tests (unverified)](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md). This section says only what the planner charges for such an index; none of it is scored against that protocol.

Hash, GiST and SP-GiST get the page charge through `genericcostestimate()`; see [Which access methods share these mechanisms](#which-access-methods-share-these-mechanisms). GIN and BRIN price pages through their own models.

BRIN charges every index page on every scan. `brincostestimate()` charges `revmapNumPages` pages, which stand for the range map ([revmap](../../../glossary.md#brin-summarization)), as startup cost at the tablespace's sequential page cost, `spc_seq_page_cost * revmapNumPages * loop_count`. It charges the remaining `index->pages - revmapNumPages` pages at `spc_random_page_cost * (numPages - revmapNumPages) * loop_count`, with `numPages = index->pages` ([selfuncs.c:8063](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8063), [selfuncs.c#brincostestimate-page-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8244-L8258)). There is no cache model: both terms are multiplied by `loop_count` instead of going through `index_pages_fetched()`.

`revmapNumPages` comes from the metapage through `brinGetStats()`, which returns it and `pagesPerRange` and nothing else ([brin.c#brinGetStats](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1638-L1654), [brin.h#BrinStatsData](../../../../raw/postgres-17/src/include/access/brin.h#L32-L36)). It is `lastRevmapPage - 1` ([brin.c:1651](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1651)). The revmap occupies blocks 1 through `lastRevmapPage`, because the first revmap page is the block after the metapage and each extension takes the next block ([brin_pageops.c#brin_metapage_init-lastRevmapPage](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L498-L503), [brin_revmap.c#revmap_physical_extend](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L551-L608)). So one revmap page is charged at the random rate, with the metapage and the regular pages.

Both values are structural, not bloat counters. BRIN bloat therefore reaches the cost only through `index->pages`, and a bloated BRIN index is charged in proportion to its size on every query.

GIN is different: it prices pages from metapage counters and its pending list, as [Which access methods share these mechanisms](#which-access-methods-share-these-mechanisms) sets out. Its pending list is charged like bloat although it is deferred insert work; [Follow-Up: When A GIN Index Is Discarded And A B-Tree Is Used Instead](#follow-up-when-a-gin-index-is-discarded-and-a-b-tree-is-used-instead) covers the consequences.

### How Density And Fragmentation Affect Different Queries

Each query shape reads the planner's inputs differently, so the same bloat moves their costs by different amounts. The fragmentation column holds the same answer in every row, for the reason in note (a) under the table.

| Query shape | Sensitivity to extra pages | Sensitivity to extra levels | Sensitivity to fragmentation |
|---|---|---|---|
| Equality lookup returning `k` rows | None while `k * pages <= tuples`, because `ceil()` keeps the share at one page; past that, `ceil(k * pages / tuples)` pages ([selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732)) | Full: below that threshold the height charge is the only bloat signal ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)) | None (a) |
| Range scan or broad index-only scan | Linear in `pages / tuples` ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)) | One charge per level ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)) | None (a) |
| Bitmap index scan feeding a [`BitmapAnd`](../../../glossary.md#bitmapand) | Linear, and a bloated index can be dropped from the `BitmapAnd` ([indxpath.c#choose_bitmap_and](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1287-L1489)) | One charge per level ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)) | None (a) |
| Nested-loop inner index scan | From none to linear. A few loops over a large index cost about one page each; once loops times touched pages reach twice the index's pages, an index within its cache share is charged whole, spread over the loops ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779), [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)). Fixture A: `0.66` against `2.50` per loop; see [Index pages in the cache model](#index-pages-in-the-cache-model) | Charged once per loop ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)) | None (a) |
| `= ANY (array)` on a B-tree | Linear, and the v17 descent clamp gives a bloated index a higher cap on estimated descents than its dense twin ([selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042)) | Charged once per estimated descent ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)) | None (a) |
| Parallel index or index-only scan | The size threshold and the worker count both follow the pages the scan is expected to touch ([costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L772), [allpaths.c#compute_parallel_worker](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4202-L4279)), unless the table sets the `parallel_workers` reloption, which replaces the page-based count ([allpaths.c#compute_parallel_worker-reloption](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4208-L4213)) | One charge per level ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)) | None (a) |
| Any scan of a partial B-tree | The pages it had when its `pg_class` row was last written, in full; pages gained since, only in step with the table's growth until that row is rewritten ([plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160), [selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019)). Fixture Q: 113 pages charged at 331 live blocks, 331 after `ANALYZE` | One charge per level ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)) | None (a) |
| GIN | Its own model: the whole pending list on a single scan, plus entry and data pages taken from metapage counters scaled to `index->pages` ([selfuncs.c#gincostestimate-pending](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7882-L7886), [selfuncs.c#gincostestimate-scale-or-invent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7767)); see [the follow-up](#follow-up-when-a-gin-index-is-discarded-and-a-b-tree-is-used-instead) | Derived from pages, as for GiST: `rint(pow(numEntryPages, 0.15))` entry pages per search entry ([selfuncs.c:7895](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7895)) | None (a) |
| BRIN | Every index page on every scan, times `loop_count` ([selfuncs.c#brincostestimate-page-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8244-L8258)) | None: a non-B-tree gets no measured height ([plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500)), and the BRIN charge counts pages only ([selfuncs.c#brincostestimate-page-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8244-L8258)) | None (a) |

(a) No planner input carries fragmentation. `IndexOptInfo`'s size fields are `pages`, `tuples` and `tree_height` only ([pathnodes.h#IndexOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1120-L1128)), and `leaf_fragmentation` exists only in `pgstatindex`'s output ([pgstatindex.c#pgstatindex_impl-density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L372)). Fixture G measures the result, exactly `0.00` ([Leaf fragmentation contributes exactly zero](#leaf-fragmentation-contributes-exactly-zero)).

The overall pattern follows from the page share. Bloat mostly raises the price of plans that already read much of the index, and barely registers on a selective lookup. So a badly bloated index can keep serving primary-key lookups at an almost unchanged plan and price, while reporting queries over the same table get dearer.

Two exceptions end that blindness, and both run through the page count. An index with more pages than its table has rows charges a one-row lookup several pages, measured at `12.29` against `4.29` for the same 1,000 rows after a rebuild. A lookup that repeats, as the inner side of a nested loop, is priced through the cache model, measured at `0.66` against `2.50` per loop. [A mostly-empty index: the fast root drops and pages outnumber rows](#a-mostly-empty-index-the-fast-root-drops-and-pages-outnumber-rows) and [Index pages in the cache model](#index-pages-in-the-cache-model) reproduce both calculations.

Dead entries at either end of a plain B-tree reach planning by another route, the row estimate. A range comparison near the end of the histogram makes the planner read them, and after more than 100 heap-page visits that return no usable row it falls back to the stale histogram bound. Fixture E's Index Only Scan cost `4.59` at the stale 10-row estimate and `4.44` once a probe reached the live maximum; see [Step 6](#step-6-probe-the-ends-of-a-b-tree-while-estimating-rows).

### Exact-Pin Measurements

This section reports what one isolated server, built from the pinned checkout, charged for pairs of indexes that hold the same logical content in different physical shapes. The measurements test the mechanism described in [Step-By-Step Mechanism](#step-by-step-mechanism): each subsection names the step it exercises and shows the arithmetic that reproduces the printed cost.

#### Fixtures and method

All numbers below come from one isolated server built from the pinned checkout by the script filed under [Measurement Script](#measurement-script), last run on 2026-09-25 (`PostgreSQL 17.11 on aarch64-apple-darwin27.0.0`, pin `786db8dcf168bd9df8f55047337525ac19118b1c`, [`block_size`](../../../glossary.md#blcksz) 8192, maximum data [alignment](../../../glossary.md#alignment) 8).

The server ran with [`autovacuum`](../../../glossary.md#autovacuum) off and [`shared_buffers`](../../../glossary.md#shared_buffers) at 256MB. Both are set once, on the postmaster command line: `autovacuum` is `PGC_SIGHUP` and `shared_buffers` is `PGC_POSTMASTER` ([guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457), [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270)). The planner cost settings stay at their defaults: `seq_page_cost = 1`, `random_page_cost = 4`, `cpu_tuple_cost = 0.01`, `cpu_index_tuple_cost = 0.005`, `cpu_operator_cost = 0.0025` ([cost.h#DEFAULT_SEQ_PAGE_COST](../../../../raw/postgres-17/src/include/optimizer/cost.h#L24-L28)) and `effective_cache_size = 4GB`, which is 524,288 pages at 8kB ([cost.h:34](../../../../raw/postgres-17/src/include/optimizer/cost.h#L34)).

Two contrib modules read the indexes directly. [`pgstattuple`](../../../glossary.md#pgstattuple) supplied `pgstatindex`. [`pageinspect`](../../../glossary.md#pageinspect) supplied `bt_metap()`, which shows the planner's fast-root level directly, and `bt_multi_page_stats()`, whose `dead_items` counts the line pointers on each page that are marked dead ([btreefuncs.c#GetBTPageStatistics-items](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L172-L187)). `pg_class.relallvisible` against `relpages` confirmed each table's visibility-map state.

Provenance: the page's first filing measured on the previous pin, `54eeefaedbee` (17.10), with scripts that were never published, and this page quotes no number from those runs. Between that pin and this one, `git log 54eeefaedbee..786db8dcf168` over `src/backend/optimizer/`, `selfuncs.c`, the nbtree, index, GIN and BRIN directories and `analyze.c` lists nine commits. None of them touches a cost-estimation function or an index-size input; the one `selfuncs.c` change adds a datatype check to `scalarineqsel()`'s `ctid` special case ([selfuncs.c#scalarineqsel-ctid-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L599-L601)).

Method notes that matter for reading the numbers:

- **One candidate index per query.** Most comparisons use two separate tables with identical contents, so every query has exactly one candidate index and no tie-breaking between indexes is involved.
- **Before-and-after fixtures.** Fixtures B and M each keep 100,000 of the same 1,000,000 rows: B keeps every tenth row, M the first tenth. Fixtures B, M, F, F-one, L3, P, Q, D and T also compare one index with itself before and after a change, and fixture E follows one index through six consecutive plans.
- **Two indexes on one table.** Where one table carries two indexes that are priced separately (fixtures N, Q and S), each is priced with the other dropped inside a rolled-back [subtransaction](../../../glossary.md#subtransaction). Both are therefore priced on literally the same statistics. Fixture L3 keeps both of its indexes, and fixture D keeps both except in its B-tree-only plan, because how the planner combines them is what they measure.
- **No heap term, mostly.** Most comparisons use an index-only scan on tables vacuum-frozen to 100% all-visible, so `cost_index()` charges no heap I/O ([costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747)). Each total still carries `rows * cpu_tuple_cost`, because `cost_index()` charges `cpu_tuple_cost` for every row it expects to fetch, index-only or not ([costsize.c#cost_index-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L795-L800)). That term is equal on both sides of every comparison whose row estimates match. Fixture F-one's estimates differ, 200,000 rows before against 1 after, so its section separates that term.
- **Deliberate exceptions to the heap rule:**
  - Fixtures H and N select a non-indexed column, and fixture I is analyzed but never vacuumed. Each pays the same heap fetches on both sides of its comparison.
  - Fixtures P and Q price the `Bitmap Index Scan` node, whose cost is the index access method's own total with no heap term ([costsize.c#cost_index-save-indextotalcost](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L623-L629), [createplan.c#create_bitmap_subplan-indexpath](../../../../raw/postgres-17/src/backend/optimizer/plan/createplan.c#L3480-L3485)). So it does not matter that their churn left the tables not all-visible.
  - Fixture E reads row estimates and dead-entry counts. Its two `Index Only Scan` costs carry no heap term only because `pg_class` still counted every heap page all-visible after the delete; see [Dead entries at the end of a B-tree: the endpoint probe](#dead-entries-at-the-end-of-a-b-tree-the-endpoint-probe).
  - The plan-choice tests select a non-indexed column too, because a heap fetch is what makes the [sequential scan](../../../glossary.md#sequential-scan) competitive.
- **Plan-shape switches.** `enable_seqscan` and `enable_bitmapscan` are turned off where an index or index-only scan has to be priced. Fixture P's bitmap scans turn off `enable_seqscan` and `enable_indexscan` instead, and fixture Q's also turn off `enable_indexonlyscan`. The nested-loop test turns off `enable_hashjoin` and `enable_mergejoin` and sets `max_parallel_workers_per_gather = 0`. The plan-choice tests, fixture L3 and fixture E run at the defaults.
- **Apply scope of every setting a fixture changes.** All of them are [`PGC_USERSET`](../../../glossary.md#guc-context): the six `enable_*` switches ([guc_tables.c#enable_seqscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L783-L792), [guc_tables.c#enable_indexscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L793-L802), [guc_tables.c#enable_indexonlyscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L803-L812), [guc_tables.c#enable_bitmapscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L813-L822), [guc_tables.c#enable_mergejoin](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L893-L902), [guc_tables.c#enable_hashjoin](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L903-L912)), `cpu_operator_cost` ([guc_tables.c#cpu_operator_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3719-L3729)), `random_page_cost` ([guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696)), `effective_cache_size` ([guc_tables.c#effective_cache_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3518)) and the five parallel settings ([guc_tables.c#max_parallel_workers_per_gather](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3419-L3428), [guc_tables.c#max_parallel_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3430-L3439), [guc_tables.c#min_parallel_table_scan_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3520-L3529), [guc_tables.c#parallel_tuple_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3730-L3740), [guc_tables.c#parallel_setup_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3741-L3751)). The script's `xp()` helper applies each with `set_config(..., true)`, so the setting lasts only for the one transaction that plans the statement.
- **Statistics are exact, so the numbers are reproducible.** Every session runs with `default_statistics_target = 10000` (`PGC_USERSET`, session scope, [guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2070-L2079)). `ANALYZE` samples 300 rows per unit of that target ([analyze.c#std_typanalyze-minrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1876-L1894)). At 3,000,000 rows that is more than any fixture holds, so `ANALYZE` reads every row and the statistics carry no sampling noise. The setting itself does not enter the cost model. Every run of the filed script on this pin has reproduced every recorded value; the latest runs are described under [Last run](#last-run).
- **Exact statistics are not exact row estimates.** Exhaustive sampling makes the statistics, and therefore every cost, the same on every run. It does not make a row estimate equal the true row count, for the two reasons below.
  - The selectivity model adds its own assumption. `clauselist_selectivity_ext()` multiplies the selectivities of clauses it cannot combine into a two-sided range ([clausesel.c#clauselist_selectivity_ext-multiply](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L253-L263)). A one-sided range such as `id <= 20000`, with no partner bound on its column, is multiplied in the same way ([clausesel.c#clauselist_selectivity_ext-one-sided](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L329-L333)). Multiplying assumes the clauses are independent.
  - Four measurements put two clauses on two columns: fixture L3's `a = 5 AND c = 7`, fixture D's `tsv @@ … AND cat = 7`, fixture P-gin's `id <= 5000 AND n = 42`, and fixture Q's `id <= 20000 AND v > 0`, where `v > 0` holds for every row.
  - The first two record each estimate beside its true count, in [Bloat changes plans](#bloat-changes-plans) and [A GIN index with a large pending list loses to a B-tree](#a-gin-index-with-a-large-pending-list-loses-to-a-b-tree). Both are built with independent columns, so neither violates the assumption. No fixture on this page bounds the error the assumption can cause.
  - Statistics describe the table as it was at the last `ANALYZE`. Fixtures Q and E change their tables after it on purpose, so their estimates depart from the counts their construction fixes: Q estimates 40,000 rows for 20,000 live ones, and E estimates 10 for none.
- **Plans are recorded, not scraped.** The script records each plan as `EXPLAIN (FORMAT JSON)` and keeps every node's type, index, costs, rows, width, workers, and index, recheck and filter conditions. The three `text` excerpts below set those recorded values in [`EXPLAIN`](../../../glossary.md#explain)'s text layout; the relation names come from each fixture's query.

| Fixture | Contents | Dense index | Bloated twin |
|---|---|---|---|
| A | 1,000,000 rows, `int` key | `a_dense_idx`, 2,745 blocks, 90.06% density, `fastlevel` 2 | `a_sparse_idx`, `fillfactor = 10`, 26,411 blocks, 9.62% density, `fastlevel` 2 |
| B | 1,000,000 rows, then `DELETE` of 90% by `id % 10 <> 0` | after `REINDEX`: 276 blocks, 89.83%, `fastlevel` 1 | before: 2,745 blocks, 9.27%, `fastlevel` 2 |
| F | 1,000,000 rows, then `DELETE` of all but the top 1,000 keys, two VACUUMs | after `REINDEX`: 5 blocks, `fastlevel` 1 | 2,745 blocks: 4 live leaves, 2 internal pages, 2,738 deleted pages and the metapage; `tree_level` 2, **`fastlevel` 1** |
| F-one | 200,000 rows, then `DELETE` of all but one row, two VACUUMs | before: 551 blocks, 547 live leaves, 90.00% density, `fastlevel` 2 | after: the same 551 blocks, now 1 live leaf, 2 internal pages, **547 deleted pages** and the metapage; 0.29% density, `tree_level` 2, **`fastlevel` 0**, `reltuples` 1 |
| G | 300,000 rows | `g_seq_idx`, `fillfactor = 100`, 744 blocks, 99.89% density, 0% fragmentation | `g_frag_idx` filled by `setseed(0.42)` random-order inserts, 1,148 blocks, 64.69% density, **49.87% fragmentation** |
| H | 50,000 rows | `h_l1_idx`, 139 blocks, `fastlevel` 1 | `h_l2_idx`, `fillfactor = 10`, 1,323 blocks, `fastlevel` 2 |
| I | 2,000 rows, analyzed but not vacuumed | `i_small_idx`, 8 blocks | `i_big_idx`, `fillfactor = 10`, 55 blocks |
| M | 1,000,000 rows, then `DELETE` of a contiguous 90% | after `REINDEX`: 276 blocks | 2,745 blocks: 276 live leaves, 3 internal pages, **2,465 deleted pages** and the metapage; 89.18% density |
| N | 1,000,000 rows over 100 distinct keys | `deduplicate_items = on`, 852 blocks | `deduplicate_items = off`, 2,749 blocks |
| P | 200,000 rows, `tag = id % 1000`, five whole-table non-HOT `UPDATE` rounds | no blocking snapshot: 169 -> 543 blocks | `REPEATABLE READ` snapshot held: 169 -> 1,173 blocks |
| P-100 | the same with `tag = id % 100` | no blocking snapshot: 180 -> 1,020 blocks | snapshot held: 180 -> 1,020 blocks |
| L3 | 500,000 rows, `a = g % 2000` plus an independent seeded `c` over 0..19; `l3_a` is 449 blocks at 85.47% throughout | `l3_c` at the default fillfactor: 427 blocks, 89.81% density | `l3_c` rebuilt at `fillfactor = 10`: 3,801 blocks, 10.37% density |
| Q | 200,000 rows, `v = id`, heap `fillfactor = 100`; ten `UPDATE ... SET v = v + 1` rounds over the rows with `id <= 20000`, in one transaction, with no `VACUUM` or `ANALYZE` until the last step | built: partial `q_part` (`WHERE id <= 20000`) 57 blocks, plain `q_full` 551 blocks | churned: `q_part` 331 blocks at 77.56% density, `q_full` 825 blocks at 85.14%; `pg_class` still records 57 and 551 |
| E | 200,000 rows, primary key `e_t_pkey`; then `DELETE` of `id > 100000`, with no `VACUUM` or `ANALYZE` until a final plain `VACUUM` | before the delete: 885 heap blocks, `id` histogram ending at 200000 | after it: 100,000 dead rows at the index's upper end, the same histogram |

Fixture G's random insert order and fixture L3's `c` column come from a seeded random generator (`setseed(0.42)`), so their block counts and row counts are the same on every run.

#### Whole-index scan cost is a closed form in pages, tuples and tree height

For one kind of scan, the B-tree cost model reduces to three inputs. The scan must read the whole index once, be an index-only scan on a table that is 100% all-visible, and carry one index qual that compares the column with a constant. Fixture A's `WHERE id > 0` is such a scan: its selectivity is exactly 1, so both row estimates are 1,000,000.

The inputs, and what the planner's intermediate values reduce to for this kind of scan:

| Symbol | Meaning | Source at the pin |
|---|---|---|
| `P` | the index's live block count, `index->pages` | `RelationGetNumberOfBlocks()` in `get_relation_info()` ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)) |
| `R` | the table's row estimate: `reltuples` scaled from `relpages` to the live heap size; for a non-partial index it is also `index->tuples` | [tableam.c#table_block_relation_estimate_size-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L711-L747), [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486) |
| `H` | the fast-root level, which `bt_metap()` reports as `fastlevel` and the planner uses as `tree_height` | [nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717) |
| `numIndexTuples` | entries the scan reads: selectivity times `R`, so `R` here | [selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019) |
| `numIndexPages` | pages the scan touches: `ceil(numIndexTuples * P / R)`, so `P` here | [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732) |
| `rows` | rows the scan returns, `R` here; `cost_index()` charges `cpu_tuple_cost` for each | [costsize.c#cost_index-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L795-L800) |
| `qual_op_cost` | one `cpu_operator_cost` per index qual, so 0.0025 here; the other operand charge, `qual_arg_cost`, is zero for a constant | [selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810) |

With those inputs the total is a sum of five terms:

```text
total = P * random_page_cost                         page charge
      + R * (cpu_index_tuple_cost + qual_op_cost)    per-entry CPU
      + ceil(log2(R)) * cpu_operator_cost            descent comparisons
      + (H + 1) * 50 * cpu_operator_cost             level charge
      + R * cpu_tuple_cost                           per-row CPU
```

Only the page charge and the level charge can carry bloat, because the other three depend on the table's row estimate alone. [Step 2](#step-2-charge-the-pages-a-scan-touches) and [Step 3](#step-3-charge-the-b-tree-height) explain where those two come from. The heap adds nothing here, because the table is all-visible ([costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747)).

| Index | Blocks | Density | `fastlevel` | Observed total cost | Predicted from `(P, R, H)` |
|---|---:|---:|---:|---:|---:|
| `a_dense_idx` | 2,745 | 90.06% | 2 | `28480.42` | `28480.42` |
| `a_sparse_idx` | 26,411 | 9.62% | 2 | `123144.43` | `123144.43` |

The prediction, term by term, with `R` = 1,000,000 and `H` = 2 for both indexes:

| Term | `a_dense_idx` | `a_sparse_idx` |
|---|---:|---:|
| Page charge, `P * 4.0` | 2,745 × 4.0 = 10,980.00 | 26,411 × 4.0 = 105,644.00 |
| Per-entry CPU, `R * (0.005 + 0.0025)` | 7,500.00 | 7,500.00 |
| Descent comparisons, `ceil(log2(1000000))` = 20, × 0.0025 | 0.05 | 0.05 |
| Level charge, `(2 + 1) * 50 * 0.0025` | 0.375 | 0.375 |
| Per-row CPU, `R * 0.01` | 10,000.00 | 10,000.00 |
| Total | 28,480.425, printed `28480.42` | 123,144.425, printed `123144.43` |

The script's `predict()` evaluates the same expression in `float8`, in the planner's order of operations, from `P`, `R` and `H` only. It equals the `EXPLAIN` total on 7 of 7 whole-index scans: both fixture-A indexes, fixtures B and M before the rebuild, fixture B after it, and both fixture-G indexes. Both fixture-A totals are exactly `x.425` in decimal. The planner's doubles print one as `.42` and the other as `.43`, and the `float8` recomputation lands on the same side both times.

The 9.62x larger index costs 4.32x more in total. Without the `1000000 * 0.01 = 10000.00` of `cpu_tuple_cost` that both totals carry, it costs 6.12x more on the index alone: `113144.43` against `18480.42`.

A 10% range scan falls outside the closed form, because it reads a pro-rata share of the index and its two bounds are two index quals. Fixture A's `id BETWEEN 1 AND 100000` (100,000 rows estimated by both) costs `3100.43` dense against `12568.42` bloated. The page charges are `ceil(100000 * 2745 / 1000000) = 275` against `ceil(100000 * 26411 / 1000000) = 2642` pages at 4.0 ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)). Each total adds 100,000 × (0.005 + 2 × 0.0025) of per-entry CPU, 0.425 of descent charges and 100,000 × 0.01 of per-row CPU.

#### The point lookup is nearly blind to bloat

Fixture A, `WHERE id = 42`, both tables 100% all-visible:

```text
Index Only Scan using a_dense_idx on a_dense  (cost=0.42..4.44 rows=1 width=4)
  Index Cond: (id = 42)
Index Only Scan using a_sparse_idx on a_sparse  (cost=0.42..4.44 rows=1 width=4)
  Index Cond: (id = 42)
```

The two costs are identical to the cent, across a 9.62x size difference and an 80-point density difference. `ceil(1 * pages / tuples)` is `1` for both indexes ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)), and both trees have `fastlevel = 2`. [Step 2](#step-2-charge-the-pages-a-scan-touches) explains why the page charge stays at one page.

Fixture B shows the same thing where the bloat is real rather than built with a fillfactor. Before `REINDEX` its index is 2,745 blocks at 9.27% density; after, it is 276 blocks at 89.83%. The whole-index scan drops from `12730.42` to `2854.29`, 4.46x. The point lookup drops only from `4.44` to `4.31`, and that entire `0.125` difference is the level the rebuild removed.

#### The tree-height charge, isolated to the cent

Fixture H holds the row count constant at 50,000. The `fillfactor = 10` twin has 9.5x the blocks and one more level. A one-row lookup is charged one page either way, so only the level reaches its cost. The last column sets `cpu_operator_cost = 1` for the one statement (`PGC_USERSET`, [guc_tables.c#cpu_operator_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3719-L3729)), which makes each CPU term readable:

| Index | Blocks | `fastlevel` | `WHERE id = 25000` | Same with `cpu_operator_cost = 1` |
|---|---:|---:|---|---|
| `h_l1_idx` | 139 | 1 | `cost=0.29..8.31` | `cost=116.00..125.02` |
| `h_l2_idx` | 1,323 | 2 | `cost=0.41..8.43` | `cost=166.00..175.01` |

At `cpu_operator_cost = 1` the startup costs are `116.00` and `166.00`, and both decompose exactly:

- 16 comparison charges, because `ceil(log2(50000)) = 16` ([selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091));
- plus the level charge `(fastlevel + 1) * 50` ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)): `16 + 2 * 50 = 116` and `16 + 3 * 50 = 166`.

The gap is `50.00`, exactly `DEFAULT_PAGE_CPU_MULTIPLIER` ([selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145)). At default settings the same gap is `50 * 0.0025 = 0.125`, so a 9.5x larger index raises a point-lookup cost by about 1.5%. Fixture H selects a non-indexed column, so all four costs include one heap page at `4.0`.

#### A mostly-empty index: the fast root drops and pages outnumber rows

Fixture F builds the same 2,745-block index as fixture A, deletes every row except the top 1,000 keys (`id > 999000`), and vacuums twice. The index is not rebuilt until the last row of the table below.

| State | Blocks | Live leaf pages | Deleted pages | `tree_level` | `fastlevel` | `WHERE id = 999950` | Whole-index scan |
|---|---:|---:|---:|---:|---:|---|---:|
| built, 1,000,000 rows | 2,745 | 2,733 | 0 | 2 | 2 | `cost=0.42..4.44` | |
| after the delete and two VACUUMs, 1,000 rows | 2,745 | 4 | 2,738 | 2 | **1** | `cost=0.28..12.29` | `10997.77` |
| after `REINDEX` | 5 | 3 | 0 | 1 | 1 | `cost=0.28..4.29` | |

Two things happen here that no fixture before it reaches.

**The planner's height fell without a rebuild.** Page deletion left the true root where it was, at block 290 and level 2. It moved the fast root to block 2570 at level 1, which is the adjustment the README describes for deleting the next-to-last page on a level ([README#page-deletion-and-tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L362-L381), [nbtpage.c#_bt_unlink_halfdead_page-fastroot](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2565-L2659)). `pgstatindex` still reports `tree_level` 2, while the startup cost charges one level fewer: `0.28` is `ceil(log2(1000)) * 0.0025 + (1 + 1) * 0.125`, that is `0.025 + 0.25 = 0.275`.

**The point lookup stopped being cheap.** With 1,000 rows and 2,745 pages, `numIndexPages = ceil(1 * 2745 / 1000) = 3` ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)), so the one-row lookup is charged three random pages:

| Term | Calculation | Value |
|---|---|---:|
| Page charge | 3 pages × `random_page_cost` 4.0 | 12.00 |
| Per-entry CPU | 1 entry × (`cpu_index_tuple_cost` 0.005 + one qual's `cpu_operator_cost` 0.0025) | 0.0075 |
| Descent comparisons | `ceil(log2(1000))` = 10 × 0.0025 | 0.025 |
| Level charge | (`fastlevel` 1 + 1) × 50 × 0.0025 | 0.25 |
| Per-row CPU | 1 row × `cpu_tuple_cost` 0.01 | 0.01 |
| Total | | 12.2925, printed `12.29` |

The rebuilt index is charged one page, so the same lookup costs `4.29`. A whole-index scan of the 1,000 rows costs `10997.77`, of which `10980.00` is the 2,745 pages at 4.0.

This is the shape a drained queue table leaves behind. It is the one case on this page where bloat reaches the *page* charge of a lone single-row lookup. Elsewhere bloat reaches such a lookup only through the `0.125` level charge, as fixtures B and H show.

A lookup that returns `k` rows is charged `ceil(k * pages / tuples)` pages, so it feels bloat sooner: fixture P's `tag = 7` bitmap scans, 200 rows each, cost `5.92` against `9.92` for one page against two. Repetition is the other way bloat reaches a lookup, measured in [Index pages in the cache model](#index-pages-in-the-cache-model). Draining the table one step further removes the page charge again; that is the next section.

#### The pages-outnumber-rows guard at its limit

Draining the table one step further inverts the penalty. `genericcostestimate()` computes the pro-rata share only when `index->pages > 1` **and** `index->tuples > 1`; when either test fails it charges a flat `numIndexPages = 1.0` ([selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732)). For a non-partial index `tuples` is the table's row estimate ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)). So the second test fails on a table the planner believes holds one row, whatever the index's size.

Fixture F-one is a 200,000-row table whose index is then stripped of all but one entry. Nothing is rebuilt.

| State | Blocks | Live leaf pages | Deleted pages | `tree_level` | `fastlevel` | `pg_class` `relpages` / `reltuples` | `WHERE id > 0` | `WHERE id = 200000` |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| built, 200,000 rows | 551 | 547 | 0 | 2 | 2 | 885 / 200000 | `5704.42` | |
| after deleting 199,999 rows and two VACUUMs | 551 | 1 | **547** | 2 | **0** | 885 / **1** | **`4.14`** | **`4.14`** |

The index still occupies all 551 blocks, and `pgstatindex` reports 0.29% `avg_leaf_density` and 547 deleted pages. The planner charges it for **one** page. The whole-index scan and the single-row lookup cost the identical `4.14`, because with one tuple there is nothing left for either estimate to differ about. Term by term:

- **Page charge:** from `551 * 4.0 = 2204.00` to `1 * 4.0 = 4.00`. That fall is the guard alone, since `index->pages` did not change.
- **Per-entry CPU:** from `200000 * (0.005 + 0.0025) = 1500.00` to `0.0075`; and per-row `cpu_tuple_cost` from `2000.00` to `0.01`. That fall is the row count, not the guard.
- **Descent comparisons:** the `ceil(log2(tuples))` charge disappeared, because that term is guarded on `index->tuples > 1` too ([selfuncs.c#btcostestimate-log2-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7086-L7091)).
- **Level charge:** from `(2 + 1) * 0.125 = 0.375` to `(0 + 1) * 0.125 = 0.125`. Page deletion pulled the fast root down to a leaf, `fastlevel` 0 against an unchanged `tree_level` 2 — fixture F's fast-root effect, taken to the bottom of the tree.

Adding those back gives `4.00 + 0.0075 + 0.125 + 0.01 = 4.1425`, printed `4.14`, with a startup cost of `0.125` printed `0.12`.

So the two guards in [Step 2](#step-2-charge-the-pages-a-scan-touches) bracket the page charge from both ends:

| Table row estimate against index pages | Page charge of a one-row lookup | Measured on |
|---|---|---|
| at least as many rows as index pages | one page, so the page charge is blind to bloat; only the level charge sees an extra level | fixtures A, B and H |
| more than one row, fewer rows than pages | `ceil(pages / rows)` pages | fixture F |
| one row or fewer | one page again, whatever the index's size | fixture F-one |

As a result, the cheapest whole-index scan on this page belongs to its emptiest index. A monitoring rule that reads plan cost as a bloat signal reads this index as healthy.

#### Leaf fragmentation contributes exactly zero

Fixture G, both tables frozen to 100% all-visible so the index-only scan pays no heap cost:

| Index | Blocks | Density | Fragmentation | `fastlevel` | Observed | Predicted |
|---|---:|---:|---:|---:|---:|---:|
| `g_seq_idx` | 744 | 99.89% | **0.00%** | 2 | `8226.42` | `8226.42` |
| `g_frag_idx` | 1,148 | 64.69% | **49.87%** | 2 | `9842.42` | `9842.42` |

The observed gap is `9842.42 - 8226.42 = 1616.00`. The page-count gap is `1148 - 744 = 404`, and `404 * random_page_cost = 404 * 4.0 = 1616.00`. So the residual attributable to a 49.87-point fragmentation difference is `0.00`. The closed-form prediction, which has no fragmentation term, reproduces both costs.

#### Two indexes with the same cost and opposite avg_leaf_density

Fixtures B and M both end at 2,745 blocks over 100,000 surviving rows. Both price a whole-index scan at exactly `12730.42`, dropping to `2854.29` after `REINDEX`. Their `pgstatindex` output could hardly be more different:

| Fixture | Deletion pattern | Blocks | Live leaf pages | Deleted pages | `avg_leaf_density` | Whole-index cost |
|---|---|---:|---:|---:|---:|---:|
| B | scattered (`id % 10 <> 0`) | 2,745 | 2,733 | 0 | **9.27%** | `12730.42` |
| M | contiguous (`id > 100000`) | 2,745 | 276 | **2,465** | **89.18%** | `12730.42` |

A monitoring rule that flags low `avg_leaf_density` catches fixture B and misses fixture M completely. Yet the planner is charged the same 2,745 pages for both, and a rebuild recovers 10x in both. For planner cost, what counts is blocks against the rows the planner expects, and on that reading the two indexes are identical.

That reading prices plans; it does not predict what a rebuild returns. `REINDEX` builds a new file for the same index relation ([index.c#reindex_index-rebuild](../../../../raw/postgres-17/src/backend/catalog/index.c#L3784-L3789)), and the build reapplies the index's storage parameters. It sets each leaf page's free-space target from the `fillfactor` reloption ([nbtsort.c#_bt_pagestate-leaf-fill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L661-L665)), and it deduplicates only when `deduplicate_items` is on ([nbtsort.c#_bt_load-deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1151-L1152), [nbtree.h#BTGetFillFactor-BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1150)).

So two indexes on this page that look bloated by blocks per row would come back at about their current size. One is fixture N's `deduplicate_items = off` index, 2,749 blocks against 852 for the same rows, both at about 90% density. The other is fixture A's `fillfactor = 10` twin, 26,411 blocks against 2,745. That is a reading of the build code; this page rebuilds neither index. Fixture L3 shows the fillfactor half directly: its `REINDEX` at `fillfactor = 10` turned `l3_c`'s 427 blocks into 3,801.

A partial index's population is not its table's row count either: fixture Q's `q_part` holds 20,000 of 200,000 rows by its predicate. This page's size-against-rows reading is a statement about planner cost. It has not been scored against [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md), which governs claims about whether an index should be rebuilt.

#### The planner reads the live block count, not pg_class.relpages

A 200,000-row table with a `fillfactor = 10` index occupying 5,285 blocks priced its whole-index scan at `24640.42`. The script then forges the catalog row on the scratch server. This is a disposable-fixture step and must never be run against a database anyone cares about:

```text
UPDATE /* wiki_bloatplan_fixture_catalog_forgery */ pg_class SET relpages = 1 WHERE relname = 'b_stale_idx';
-- pg_class: relpages = 1, reltuples = 200000; live size 5285 blocks
Index Only Scan using b_stale_idx on b_stale  (cost=0.42..24640.42 rows=200000 width=4)
  Index Cond: (id > 0)
```

The cost did not move. That confirms `get_relation_info()` used `RelationGetNumberOfBlocks()` for this non-partial index, not the stored `relpages` ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)); see [Step 1](#step-1-read-the-index-size).

A **partial** index behaves differently, because `estimate_rel_size()` derives its tuple count from the density recorded in `pg_class` ([plancat.c#estimate_rel_size-density](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1116-L1146)). Forging `reltuples` from 200,000 to 20 on an otherwise identical partial index (`WHERE id > 0`) moved the cost from `24140.42` to `23140.49`, and the startup cost from `0.42` to `0.39`. With 20 claimed tuples, `genericcostestimate()` caps the entries read at the index's `tuples` ([selfuncs.c#genericcostestimate-tuple-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6707-L6715)). So the scan is charged `20 * cpu_index_tuple_cost` instead of `200000 *`, and `ceil(log2(20)) = 5` comparisons instead of 18 ([selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091)). The page charge stays at all 5,285 pages.

[A partial index hides its growth until its statistics are rewritten](#a-partial-index-hides-its-growth-until-its-statistics-are-rewritten) shows the same path reached by real growth, with no forgery.

The partial index starts `500.00` below the plain one for a reason that has nothing to do with size. Its predicate implies the query's only clause, so `check_index_predicates()` drops that clause from the list the index is matched against ([indxpath.c#check_index_predicates-indrestrictinfo](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L3318-L3378), [indxpath.c#match_restriction_clauses_to_index](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1968-L1974)). The scan therefore carries no index qual, and its 200,000 tuples pay no `qual_op_cost`: `200000 * 0.0025 = 500.00`.

The script vacuums every fixture table when it builds it, except fixture I's, which are analyzed but never vacuumed on purpose. Stage `fstale` prices both of its tables straight after that vacuum, so both are all-visible (`relallvisible` 885 of 885), and neither index-only scan pays a heap fetch ([costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747)).

#### A partial index hides its growth until its statistics are rewritten

A partial index is charged for its growth only as fast as the table's row estimate grows. That lasts until `ANALYZE`, or a `VACUUM` that counts the index's entries exactly, rewrites the index's `pg_class` row; then the whole growth arrives at once. A plain index is charged its live size at once.

Fixture Q measures both on one table. After the churn, the partial index had grown from 57 to 331 blocks and was charged 113 pages. The plain index had grown from 551 to 825 blocks and was charged all 825. After `ANALYZE` the partial index was charged all 331.

Fixture Q is the table `q_t (id int, v int, pad text)` with heap `fillfactor = 100` and 200,000 rows with `v = id`. It has a partial index `q_part ON q_t (v) WHERE id <= 20000` and a plain index `q_full ON q_t (v)`, and it is built with `VACUUM (FREEZE, ANALYZE)`.

The churn is ten `UPDATE q_t SET v = v + 1 WHERE id <= 20000` rounds inside one [PL/pgSQL](../../../glossary.md#plpgsql) `DO` block. Each round changes an indexed column, so no round can be HOT ([heapam.c#heap_update-hot-decision](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4140-L4166)), and each adds an entry to both indexes. The rounds share one transaction, so no replaced version is dead to anyone before the commit ([heapam_visibility.c#HeapTupleSatisfiesVacuumHorizon-same-xact](../../../../raw/postgres-17/src/backend/access/heap/heapam_visibility.c#L1253-L1266), [heapam_visibility.c#HeapTupleSatisfiesVacuumHorizon-xmax-in-progress](../../../../raw/postgres-17/src/backend/access/heap/heapam_visibility.c#L1383-L1386)). The heap doubled exactly, from 1,471 to 2,942 blocks. Nothing writes `pg_class` until the final `ANALYZE q_t`.

Each state prices two forced bitmap scans: `SELECT v FROM q_t WHERE id <= 20000 AND v > 0` on the partial index, and `SELECT v FROM q_t WHERE v > 0` on the plain one. Each runs with the other index hidden in a rolled-back subtransaction.

The charged pages are the `Bitmap Index Scan` node's cost difference between `random_page_cost` 4 and 1, divided by 3. That works because on a single scan `genericcostestimate()` charges `numIndexPages * spc_random_page_cost`, and no other term of the node's cost depends on that setting ([selfuncs.c#genericcostestimate-single-scan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6780-L6787)). The script sets `random_page_cost = 1` for the one statement (`PGC_USERSET`, [guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696)).

| State | `q_t` `relpages` / `reltuples` / live blocks | `q_part` `relpages` / `reltuples` / live blocks | `q_full` `relpages` / `reltuples` / live blocks |
|---|---|---|---|
| built, after `VACUUM (FREEZE, ANALYZE)` | 1,471 / 200,000 / 1,471 | 57 / 20,000 / 57 | 551 / 200,000 / 551 |
| churned, `pg_class` untouched | 1,471 / 200,000 / **2,942** | 57 / 20,000 / **331** | 551 / 200,000 / **825** |
| after `ANALYZE q_t` | 2,942 / 200,000 / 2,942 | 331 / 20,000 / 331 | 825 / 200,000 / 825 |

| State | Partial query: rows, `Bitmap Index Scan` at `random_page_cost` 4 / 1, pages charged | Plain query: rows, `Bitmap Index Scan` at 4 / 1, pages charged |
|---|---|---|
| built | 20,000, `378.29` / `207.29`, **57** | 200,000, `3704.42` / `2051.42`, **551** |
| churned | 40,000, `752.29` / `413.29`, **113** | 400,000, `6300.42` / `3825.42`, **825** |
| after `ANALYZE` | 20,000, `1474.29` / `481.29`, **331** | 200,000, `4800.42` / `2325.42`, **825** |

After the churn, [`pg_relation_size()`](../../../glossary.md#relation-size-functions) puts `q_part` at 331 blocks and `q_full` at 825. `pgstatindex` reports 329 leaves at 77.56% density and 49.85% fragmentation for `q_part`, and 820 leaves at 85.14% and 20% for `q_full`. `bt_metap()` gives their fast-root levels as 1 and 2.

The churned partial charge, step by step from the pinned code:

1. **Table row estimate.** The planner scales `reltuples` by the live heap size ([plancat.c#get_relation_info-table-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L196-L202), [tableam.c#table_block_relation_estimate_size-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L711-L747)): `rint(200000 / 1471 * 2942) = 400000`. The dead versions fill heap pages that the recorded density reads as live rows, which is why both row estimates doubled.
2. **Partial index `tuples`.** `pages` is the live block count, 331. `estimate_rel_size()` scales the recorded density by the live blocks, both counts less the metapage ([plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160)): `rint(20000 / (57 - 1) * (331 - 1)) = 117857`. That is below the table's `400000`, so `get_relation_info()` does not clamp it ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)).
3. **Entries read.** `btcostestimate()` takes the selectivity of the index predicate ANDed with the index qual, times the **table's** rows ([selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019)). That is `0.1 * 400000 = 40000`, because `id <= 20000` is 10% of the rows and `v > 0` holds for all of them.
4. **Pages charged.** `genericcostestimate()` charges `ceil(40000 * 331 / 117857) = 113` pages ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)).
5. **Node total.** Page charge `113 * 4.0 = 452`, per-entry CPU `40000 * (0.005 + 0.0025) = 300`, descent comparisons `ceil(log2(117857)) * 0.0025 = 17 * 0.0025 = 0.0425`, and level charge `(fastlevel 1 + 1) * 0.125 = 0.25`: `752.2925`, printed `752.29`.

The plain index needs no scaling, because its `tuples` is the table's `400000`. It is charged `ceil(400000 * 825 / 400000) = 825` pages, its whole live size. `ANALYZE` rewrites every index's `relpages` and `reltuples` ([analyze.c#do_analyze_rel-index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663)). Afterwards the partial charge is `ceil(20000 * 331 / 20000) = 331` pages. The plain index keeps its 825 pages, and its total falls by `1500.00` as printed: `200000 * (0.005 + 0.0025)` for the halved row estimate, plus one fewer `log2` comparison at `0.0025` that the rounding hides.

The partial index's growth cancels out because its live block count appears in both `pages` and `tuples`. `numIndexPages` therefore comes to about `selectivity * table rows / recorded density`, which does not depend on the index's live size. The charge rose from 57 to 113 because the table's row estimate doubled with its heap, not because the index grew 5.8x. [Key Interactions](#key-interactions) sets this cancellation beside the others.

Two conditions bound the lag:

- **The clamp.** It holds while the scaled `tuples` stays below the table's row estimate. Past that, `get_relation_info()` clamps `tuples` to the table's rows, and the charge becomes `selectivity * pages`, like a plain index's ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)).
- **A rewrite of the index's `pg_class` row.** `ANALYZE` ends the lag, as measured here. So does a `VACUUM` whose counts for the index are exact ([vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099)). A build or rebuild writes the index's own counts through `index_update_stats()` ([index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135), [index.c#index_update_stats-write](../../../../raw/postgres-17/src/backend/catalog/index.c#L2835-L2923)). There are two exceptions. A rebuild that finds no entries while the row holds `reltuples = -1` leaves it at `-1`, and a build during binary upgrade writes nothing ([index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842)).

Fixture Q runs neither a `VACUUM` nor a rebuild. This is the partial-index path of [Step 1](#step-1-read-the-index-size), reached by real growth; [Lifecycle Of The Planner Inputs](#lifecycle-of-the-planner-inputs) lists every event that rewrites the row.

#### Bloat changes plans

Fixture A with all `enable_*` settings at their defaults, selecting a non-indexed column so that a heap fetch is required:

| Selectivity | Dense index | Bloated twin |
|---|---|---|
| 25% (`id BETWEEN 1 AND 250000`) | `Index Scan using a_dense_idx` at `9590.42` | `Seq Scan` at `22353.00`; the index path is rejected |
| 12% (`id BETWEEN 1 AND 120000`) | `Index Scan` at `4606.43` | `Index Scan` at `15966.42` |

The sequential scan is the same `22353.00` on both tables: 7,353 heap pages, plus 1,000,000 rows at `cpu_tuple_cost` and two operator evaluations each ([costsize.c#cost_seqscan](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L315-L322)). With exact statistics the row estimates are 250,000 and 120,000 rows.

Bloat also removes an index from a `BitmapAnd`. Fixture L3 is a 500,000-row table with `a = g % 2000` and an independent `c` drawn by the seeded random generator over 0..19, so `a = 5 AND c = 7` selects real rows. With both indexes healthy — `l3_a` at 449 blocks and 85.47% density, `l3_c` at 427 and 89.81% — the two-clause predicate produced a `BitmapAnd` over both, under a `Bitmap Heap Scan` whose plan total is `328.51`.

The `BitmapAnd` node itself costs `282.26`. That is the `c` bitmap's `275.70`, the `a` bitmap's `6.30`, and `0.26` for combining them. The combining charge is `100 * cpu_operator_cost = 0.25` for the second input ([costsize.c#cost_bitmap_and_node-combine](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1184-L1186)). Each input also adds `0.1 * cpu_operator_cost` per row of its index path ([costsize.c:1127](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1127)), and an unparameterized index path carries the relation's 12 estimated rows ([costsize.c#cost_index-rows](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L589-L604)): `2 * 0.1 * 0.0025 * 12 = 0.006`.

Bloating only the `c` index to 3,801 blocks at 10.37% density, by rebuilding it at `fillfactor = 10`, made the planner drop it and demote `c = 7` to a `Filter`:

```text
Bitmap Heap Scan on l3  (cost=6.30..806.01 rows=12 width=25)
  Recheck Cond: (a = 5)
  Filter: (c = 7)
  ->  Bitmap Index Scan on l3_a  (cost=0.00..6.30 rows=250 width=0)
        Index Cond: (a = 5)
```

Fixture L3 also tests the method note's claim that exhaustive statistics make every cost reproducible without making every estimate true; fixture D in the GIN follow-up is the other such fixture. Both columns are analyzed exhaustively, and the conjunction is still estimated by multiplying two per-clause selectivities, which assumes independence ([clausesel.c#clauselist_selectivity_ext-multiply](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L253-L263)). Each estimate beside the true count:

| Predicate | Estimated rows | Actual rows |
|---|---:|---:|
| `a = 5` | 250 | 250 |
| `c = 7` | 24,971 | 24,971 |
| `a = 5 AND c = 7` | 12 | 12 |

All three match, but not for the same reason. The two single-column estimates are exact because `default_statistics_target = 10000` buys each column a most-common-values (MCV) list long enough to hold all of its values at their true frequencies. When every sampled value repeats, `ANALYZE` takes the sample's distinct count as the column's, and when every value fits the target it keeps them all ([analyze.c#compute_scalar_stats-stadistinct](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2550-L2560), [analyze.c#compute_scalar_stats-complete-mcv](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2614-L2636)).

The conjunction matches by luck of the seed. Independence makes the product right only on average: the estimate is `500000 * (250 / 500000) * (24971 / 500000) = 12.49`, printed 12. The true count of `c = 7` among the 250 rows with `a = 5` is itself a random draw, with a standard deviation of about 3.4. That it came out at exactly 12 is a property of `setseed(0.42)`, not of the model. Fixture D is built so that its conjunction is exact by construction; see [A GIN index with a large pending list loses to a B-tree](#a-gin-index-with-a-large-pending-list-loses-to-a-b-tree).

Either way, agreement is not proof. The multiplication is an assumption, and no fixture on this page violates it, so nothing here bounds the error it can cause. That limit is filed under [Open Questions](#open-questions).

#### Bloat changes parallel worker counts

Fixture A's parallel index-only scans differ only in the index. The script plans them with `max_parallel_workers_per_gather = 8`, `max_parallel_workers = 8`, `enable_seqscan = off` and `enable_bitmapscan = off`, each set for the one statement (all `PGC_USERSET`; see [Fixtures and method](#fixtures-and-method)). It also sets `min_parallel_table_scan_size = 0`, which an index-only scan never consults, because `cost_index()` passes it no heap-page estimate ([costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L772)).

| Index | Blocks | Workers, whole index | Workers, 50% of the keys | Workers, 20% of the keys |
|---|---:|---:|---:|---:|
| `a_dense_idx` | 2,745 | 4 | 3 | 2 |
| `a_sparse_idx` | 26,411 | 6 | 5 | 5 |

Every count follows `compute_parallel_worker()`'s powers-of-three ramp ([allpaths.c#compute_parallel_worker](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4202-L4279)). The ramp starts from `min_parallel_index_scan_size`, 512kB by default, which is 64 blocks ([guc_tables.c#min_parallel_index_scan_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3531-L3540)). It gives one worker from 64 pages, two from 192, three from 576, four from 1,728, five from 5,184 and six from 15,552. The ramp is applied to the pages the scan is expected to touch; see [Step 4](#step-4-apply-the-cache-model-and-pick-workers).

The whole-index scans touch every page, so they read as if the index size set the count. The partial scans show that it does not. The bloated index plans 5 workers for a 20% scan, because 20% of 26,411 pages is still 5,283 pages, where the dense index's 549 pages earn 2. If `index->pages` chose the count, every cell in the bloated row would read 6.

The two partial-scan columns were planned twice: once at the default `parallel_setup_cost` and `parallel_tuple_cost`, and once with both set to `0` for the statement (both `PGC_USERSET`, [guc_tables.c#parallel_tuple_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3730-L3740), [guc_tables.c#parallel_setup_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3741-L3751)). The planner chose the same parallel plan with the same worker counts both times, as it did for the whole-index column. Each plan is a partial `Aggregate` under `Gather`, so each worker returns one row and the tuple-transfer charge is negligible. Bloat bought two or three extra workers for no extra useful data.

#### Index pages in the cache model

Fixture A again, this time as the inner side of a 50,000-iteration nested loop. `a_outer` holds 50,000 keys spread evenly over the 1,000,000. Hash and merge joins are disabled and `max_parallel_workers_per_gather = 0`, each for the one statement. The index-only scan is now repeated, so `genericcostestimate()` prices its pages through `index_pages_fetched()`, the Mackert-Lohman cache model ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779), [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)).

| Inner index | Blocks | Inner scan, per loop | Nested Loop total | Inner scan at `effective_cache_size = 64MB` | Nested Loop total at 64MB |
|---|---:|---|---:|---|---:|
| `a_dense_idx` | 2,745 | `cost=0.42..0.66` | `34327.00` | `cost=0.42..1.38` | `70323.00` |
| `a_sparse_idx` | 26,411 | `cost=0.42..2.50` | `126095.00` | `cost=0.42..3.55` | `178623.00` |

The `count(*)` `Aggregate` above each join adds the same `125.01` in every cell, so the query totals are `34452.01`, `126220.01`, `70448.01` and `178748.01`.

Each loop touches one index page, so without a cache model every loop would pay `4.0`. The model instead counts the distinct pages that 50,000 one-page fetches reach, over a universe of the whole index (the formula's terms are defined in [Formulas](#formulas)):

| Step | `a_dense_idx` | `a_sparse_idx` |
|---|---|---|
| Fetches ignoring cache, `numIndexPages * loops` | 1 × 50,000 = 50,000 | 1 × 50,000 = 50,000 |
| Twice the index, `2 * P` | 5,490, so the fetches reach it | 52,822, so the fetches fall just short |
| Pages the model counts | capped at the whole index: 2,745 | `ceil(2 * 26411 * 50000 / (2 * 26411 + 50000))` = 25,687 |
| Page charge per loop, `pages * 4.0 / 50000` | 0.22 | 2.05 (2.11 if capped) |
| Descent, per-entry and per-row CPU per loop | 0.4425 | 0.4425 |
| Inner scan total per loop | 0.66 | 2.50 |

Both indexes fit their prorated share of the 4GB `effective_cache_size`, which is what allows the cap ([costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)). The share is `ceil(effective_cache_size * T / (table pages + T))`, and the join's two tables hold 7,353 and 222 heap pages, 7,575 in all, as the run records. At 524,288 pages that gives the dense index `ceil(524288 * 2745 / (7575 + 2745)) = 139455` pages and the bloated twin `ceil(524288 * 26411 / (7575 + 26411)) = 407432`, both far above `T`. Every table is all-visible, so the heap contributes nothing and the whole difference is the index.

Fifty thousand one-page loops reach both indexes' sizes, so the model prices about the whole index spread over the loops. Here the sensitivity to bloat is close to linear. With few loops over a large index the formula counts about one page per loop, and bloat barely registers; [Step 4](#step-4-apply-the-cache-model-and-pick-workers) sets out both regimes.

Shrinking `effective_cache_size` to 64MB for the statement (`PGC_USERSET`, [guc_tables.c#effective_cache_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3518)) makes the prorated cache share smaller than either index, `ceil(8192 * 2745 / 10320) = 2179` pages against 2,745 and `ceil(8192 * 26411 / 33986) = 6367` against 26,411, so the formula's `T > b` cases apply and both costs rise. So a bloated index is charged more for *repeated* lookups even though each touches a single page. That is the part of the penalty a lone point lookup never shows.

#### The v17 ScalarArrayOp descent clamp

Fixture I runs `= ANY` lookups with `cpu_operator_cost = 1` for the statement (`PGC_USERSET`, [guc_tables.c#cpu_operator_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3719-L3729)), so that each estimated descent is directly readable. Each additional descent adds about 116 cost units:

- 111 of descent CPU: `ceil(log2(2000)) = 11` comparisons plus `(1 + 1) * 50` for two pages ([selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091), [selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106));
- one more index page at `4.0`;
- about `1.0` of per-tuple CPU.

The tables are analyzed but never vacuumed, so the index-only scan is charged heap access as a plain index scan would be. That is one random heap page (`4.0`) at every array length, because the heap is in key order, plus `cpu_tuple_cost` per row, identically for both indexes ([costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747), [costsize.c#cost_index-correlation-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L781-L800)). The clamp is `ceil(pages * 0.3333333)` ([selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042)): `3` for the 8-block index and `19` for the 55-block index. [Step 5](#step-5-clamp-scalararrayop-descents-new-in-v17) explains the clamp.

| Array length | `i_small_idx` (8 blocks, clamp 3) | `i_big_idx` (55 blocks, clamp 19) |
|---:|---:|---:|
| 1 | `120.02` | `120.02` |
| 2 | `236.03` | `236.03` |
| 3 | `352.04` | `352.04` |
| 4 | `352.05` | `468.06` |
| 6 | `355.09` | `700.09` |
| 10 | `358.14` | `1164.15` |

The dense index plateaus at exactly three descents and stops charging for longer arrays; the bloated index keeps paying. At ten elements the bloated index is charged `1164.15` against `358.14` for the identical query and identical row estimates, purely because its page count raised the cap. The residual growth on the plateaued rows is the per-tuple term, not descents.

#### Version churn with and without a held snapshot

Fixture P is a 200,000-row table `(id, payload, tag)` with indexes on `payload` and `tag`. `UPDATE ... SET payload = payload + 1` changes an indexed column, so it is non-HOT and writes a logically unchanged duplicate into the `tag` index on every round. Each of the five rounds is its own transaction, and no VACUUM runs. Fixture P sets `tag = id % 1000`; fixture P-100 sets `tag = id % 100` and changes nothing else.

| Fixture | Run | `tag` index blocks after 5 rounds | Density | Fragmentation | `fastlevel` | Bitmap index scan cost, `tag = 7` |
|---|---|---:|---:|---:|---:|---:|
| P, 1,000 tag values | no blocking snapshot | 543 (from 169) | 98.01% | 64.31% | 1 -> 2 | `5.92` |
| P, 1,000 tag values | `REPEATABLE READ` snapshot held elsewhere | 1,173 (from 169) | 82.52% | 42.88% | 1 -> 2 | `9.92` |
| P-100, 100 tag values | no blocking snapshot | 1,020 (from 180) | 91.16% | 18.48% | 1 -> 2 | `59.42` |
| P-100, 100 tag values | `REPEATABLE READ` snapshot held elsewhere | 1,020 (from 180) | 91.11% | 18.48% | 1 -> 2 | `59.42` |

Six row versions were created per logical row over five rounds. In fixture P the blocked run grew 6.9x, close to storing every version, and the unblocked run grew 3.2x.

The difference matches what bottom-up index deletion can and cannot do. The README names an old snapshot holding up cleanup as exactly the condition that defeats it ([README#deduplication-and-bottom-up-note](../../../../raw/postgres-17/src/backend/access/nbtree/README#L980-L988)). No stage isolates that mechanism, so the attribution rests on the source. The `4.00` gap between the two bitmap index scan costs is one page: `ceil(200 * 1173 / 200000) = 2` against `ceil(200 * 543 / 200000) = 1` ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)).

The unblocked run's density reads 98.01%, above the 91.47% its build left at the default leaf fillfactor of 90 ([nbtree.h:200](../../../../raw/postgres-17/src/include/access/nbtree.h#L200)). Fillfactor sets how full a build, a rightmost leaf split or a split-after-new-item split leaves a page; any other leaf split divides the page about evenly ([nbtsort.c#_bt_pagestate-leaf-fill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L661-L665), [nbtsplitloc.c#_bt_findsplitloc-fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L334)). Later inserts can fill any page further (see [Low-density live leaf pages](#low-density-live-leaf-pages)). Which of deduplication, bottom-up deletion and the single-value split strategy did the packing here was not traced; it is filed under [Open Questions](#open-questions).

Fixture P-100 is the control that keeps this result from being over-read. With 2,000 rows per tag value instead of 200, the same five rounds grew the index 5.7x to the same 1,020 blocks whether or not a snapshot was held. There the free horizon bought nothing. Why was not traced; it is filed under [Open Questions](#open-questions).

#### Dead entries at the end of a B-tree: the endpoint probe

Dead entries at the end of a B-tree cost planning work and can hold a row estimate at a stale value. They add no page charge of their own: in fixture E the index-only scan's cost moves only with the row estimate, `4.59` at `rows=10` against `4.44` at `rows=1`. The read that meets them is the planning-time endpoint probe of [Step 6](#step-6-probe-the-ends-of-a-b-tree-while-estimating-rows).

Fixture E measures the probe. In each of four consecutive plans it passed exactly 100 heap pages of dead rows, gave up on the 101st, and left a stale 10-row estimate. Each probe also marked the entries it passed as dead, so the fifth plan reached a live row and the estimate fell to 1.

Fixture E is `e_t (id int, v int)`: 200,000 rows, primary key `e_t_pkey`, then `VACUUM (FREEZE, ANALYZE)`, which leaves 885 heap blocks and an `id` histogram of 10,001 bounds ending at 200000. `DELETE FROM e_t WHERE id > 100000` follows, with no `VACUUM` and no `ANALYZE` before the six plans; a plain `VACUUM` runs after them. Each plan is an `EXPLAIN` of `SELECT count(*) FROM e_t WHERE id > 199990` at default settings, followed by `sum(dead_items)` over `bt_multi_page_stats('e_t_pkey', 1, -1)`:

| Moment | Index Only Scan estimate | Plan total | Index entries marked dead |
|---|---:|---:|---:|
| before the delete | `rows=10` | `4.63` | not read |
| after the delete, before any plan | | | 0 |
| plan 1 | `rows=10` | `4.63` | 22,590 |
| plan 2 | `rows=10` | `4.63` | 45,190 |
| plan 3 | `rows=10` | `4.63` | 67,790 |
| plan 4 | `rows=10` | `4.63` | 90,390 |
| plan 5 | `rows=1` | `4.45` | 100,000 |
| plan 6 | `rows=1` | `4.45` | 100,000 |
| after a plain `VACUUM` | `rows=1` | `4.45` | 0 |

The plan total is the `count(*)` `Aggregate`; the `Index Only Scan` under it costs `0.42..4.59` at `rows=10` and `0.42..4.44` at `rows=1`. Nothing here is timed. Every plan is `EXPLAIN` alone, and `bt_multi_page_stats()` only reads pages, so the planner's probe is the only thing that can have marked the entries dead.

The steps that produce these counts, from the pinned source:

1. **The probe runs.** `id > 199990` falls in the histogram's last bin, so `ineq_histogram_selectivity()`'s binary search reaches the last bound. Before comparing with it, the function asks `get_actual_variable_range()` for the column's current maximum ([selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136)). `e_t_pkey` qualifies, because it is a plain B-tree, neither partial nor hypothetical, whose first column is `id` ([selfuncs.c#get_actual_variable_range-index-choice](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6179-L6239)).
2. **The probe counts heap pages.** `get_actual_variable_endpoint()` reads the index from that end as an index-only scan. An entry whose heap page is not all-visible costs a heap fetch. When the fetch finds no acceptable row, the probe counts that heap page if it differs from the last one it counted, and moves on. The fetch runs before the count, so the probe stops on the fetch that takes the count past `VISITED_PAGES_LIMIT` (100): the 101st page it reads ([selfuncs.c#get_actual_variable_endpoint-scan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6415-L6458)). The caller then keeps the bound stored in `pg_statistic` ([selfuncs.c#get_actual_variable_endpoint-comment](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6371-L6414)).
3. **The probe marks what it passed.** `index_fetch_heap()` sets `kill_prior_tuple` when the whole chain is dead ([indexam.c#index_fetch_heap-kill](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L644-L652)). `btgettuple()` records the item on its next call ([nbtree.c#btgettuple-kill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L226-L245)), and the recorded items are marked dead when the scan leaves the leaf page or ends ([nbtsearch.c#_bt_steppage-killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2049-L2051), [nbtree.c#btendscan-killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L424-L426)).

The counts follow from that loop:

- **Plan 1.** 885 heap blocks hold 200,000 rows at 226 to a full block, so the last block holds `200000 - 884 * 226 = 216`. Plan 1 marked the dead entries of that block and of 99 full ones, `216 + 99 * 226 = 22590`: exactly 100 heap pages. The fetch on the 101st page trips the limit, and its entry is never recorded, because no further `btgettuple()` call follows.
- **Plans 2 to 4.** Each passed 100 more full blocks, `100 * 226 = 22600` entries each.
- **Plan 5.** It found `100000 - 90390 = 9610` dead entries left: 118 on block 442, which holds `id` 99,893 to 100,118, and `42 * 226 = 9492` on blocks 443 to 484. That is 43 heap pages, under the limit, and the next entry, `id` 100,000 on block 442, is live.
- **The estimates.** While plans 1 to 4 gave up, the stale bound 200000 kept `id > 199990` at half of the last 20-row bin. In `200000 * (1 - 9999.5 / 10000) = 10` rows, `9999.5 / 10000` is the fraction of the histogram below 199990: 9,999 whole bins plus half of the last one. Plan 5's new maximum, 100000, put 199990 above every bound, so the selectivity became 0 and the estimate fell to the one-row floor ([selfuncs.c#ineq_histogram_selectivity-above-last-bound](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1162-L1168), [selfuncs.c#ineq_histogram_selectivity-flip-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1319-L1344), [costsize.c#clamp_row_est](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L202-L218)).
- **After `VACUUM`.** The plain `VACUUM` removed every dead entry. The histogram still ends at 200000, but the probe now reads 100000 at once, so the estimate stays at 1.

No cost term saw the dead entries. The two `Index Only Scan` totals, `4.59` and `4.44`, differ only by nine estimated rows at `0.005 + 0.0025 + 0.01 = 0.0175` each: `cpu_index_tuple_cost`, one qual's `cpu_operator_cost` and `cpu_tuple_cost`. That is `0.1575` before rounding. The page, descent and level terms are the same in both, because one page covers either estimate ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732), [selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810), [costsize.c#cost_index-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L795-L800)).

Neither total has a heap term either, although the delete cleared the visibility-map bits of every page it touched ([heapam.c#heap_delete-clear-vm](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L3120-L3146)), and step 2 relies on those cleared bits. The planner does not read the map for this. It takes the table's all-visible fraction from `pg_class.relallvisible` ([plancat.c#get_relation_info-table-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L196-L202), [tableam.c#table_block_relation_estimate_size-allvisfrac](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L749-L760)), which `VACUUM` and `ANALYZE` refresh from the map ([vacuumlazy.c#heap_vacuum_rel-relstats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L556-L575), [analyze.c#do_analyze_rel-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L623-L645)). The stage runs neither between the delete and plan 6.

The totals show that the fraction was still 1. Below 1, the `rows=10` plans would fetch at least one heap page, `ceil(ceil(10 / 200000 * 885) * (1 - fraction)) = 1`, and add at least one `random_page_cost` of 4.00 ([costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747), [costsize.c#cost_index-correlation-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L781-L800)). The index terms and `cpu_tuple_cost` already account for the whole total:

| Term | Calculation | Value |
|---|---|---:|
| Startup: descent comparisons and level charge | `ceil(log2(200000)) * 0.0025 + (2 + 1) * 0.125` | 0.42 |
| Page charge | 1 index page × 4.0 | 4.00 |
| Per-entry CPU | 10 × (0.005 + 0.0025) | 0.075 |
| Per-row CPU | 10 × 0.01 | 0.10 |
| Total | | 4.595, printed `4.59` |

What the dead entries cost is planning work, which no plan cost prices. One probe reads up to 101 heap pages: 100 that yield nothing, and the 101st, whose fetch trips the limit ([selfuncs.c#get_actual_variable_endpoint-scan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6415-L6458)).

The limit binds each probe, not each plan. `ineq_histogram_selectivity()` calls `get_actual_variable_range()` whenever a clause's binary search reaches the first or last bound, and for both ends when the histogram has only two bounds ([selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136)). That function makes a separate `get_actual_variable_endpoint()` call for the minimum and for the maximum ([selfuncs.c#get_actual_variable_range-endpoint-calls](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6282-L6314)), and each call starts its own page count at zero ([selfuncs.c:6365](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6365)).

So a plan pays up to 101 heap pages for every probe it makes, and a plan whose range clauses reach several histogram ends makes several probes. Fixture E's single clause made one probe per plan, which is what its 22,590 and 22,600 counts show. Later plans pay again, each starting past the entries earlier probes marked dead. That goes on until a probe reaches a live entry within its limit or a `VACUUM` removes the dead entries, as plans 1 to 5 and the final `VACUUM` show.

Fixture E ran with no other session, so every deleted row was dead to all transactions. Under a snapshot old enough to still see the deleted rows, `SnapshotNonVacuumable` accepts them as recently dead ([selfuncs.c#get_actual_variable_endpoint-comment](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6371-L6414)). The probe would then stop at the first one and return the deleted maximum without marking anything; fixture E does not measure that case. The 100-page limit has its own history; see [v16, back-patched: the endpoint probe gives up after 100 heap pages](#v16-back-patched-the-endpoint-probe-gives-up-after-100-heap-pages).

#### Deduplication

Fixture N, 1,000,000 rows over 100 distinct keys, two indexes on the same column:

| Index | Blocks | Density | `WHERE k = 5` | `WHERE k > 0` |
|---|---:|---:|---:|---:|
| `deduplicate_items = on` | 852 | 89.70% | `24021.01` | `50111.17` |
| `deduplicate_items = off` | 2,749 | 90.16% | `24097.01` | `57623.17` |

Each index is priced with the other one dropped inside a rolled-back subtransaction. These are plain index scans on `SELECT *`, so every cost also contains the same heap fetches in both rows. Only the gaps belong to the index, and both gaps are pure page arithmetic:

| Predicate | Rows estimated | Touched pages, on | Touched pages, off | Gap at `random_page_cost` 4.0 | Observed gap |
|---|---:|---:|---:|---:|---:|
| `k > 0` | 990,000 | `ceil(990000 * 852 / 1000000)` = 844 | `ceil(990000 * 2749 / 1000000)` = 2,722 | (2,722 - 844) × 4.0 = 7,512.00 | `57623.17 - 50111.17` = 7,512.00 |
| `k = 5` | 10,000 | `ceil(10000 * 852 / 1000000)` = 9 | `ceil(10000 * 2749 / 1000000)` = 28 | (28 - 9) × 4.0 = 76.00 | `24097.01 - 24021.01` = 76.00 |

The touched-page counts are the pro-rata share of [Step 2](#step-2-charge-the-pages-a-scan-touches) ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)). `avg_leaf_density` reads about 90% for both indexes, because it measures the leaf pages' free space against the space available ([pgstatindex.c#pgstatindex_impl-density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L372)). It cannot see that one index stores 3.2x more pages for the same information: deduplication changes how many entries a full page holds, not how full it is.

### Causal Summary

1. **Initial state.** A bloated index has more blocks than its live entries need, and possibly an extra level. Nothing in `pg_class` or `IndexOptInfo` records how full those blocks are ([pathnodes.h#IndexOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1120-L1128)).
2. **Input.** While planning, the planner reads the index's live block count, takes the table's row estimate as the index's entry count, and reads a B-tree's fast-root level, possibly from a cached copy ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500)).
3. **Transformation.** The cost code charges a scan the same fraction of the index's pages as of its entries, at `random_page_cost` each, plus `50 * cpu_operator_cost` per level on every descent ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732), [selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)).
4. **Interaction.** `ceil()` and the one-page guard hide bloat from a single small lookup. The cache model brings the whole index back for repeated scans, and the v17 descent cap grows with pages. A partial index's recorded density cancels its own growth, and the endpoint probe moves row estimates rather than costs ([selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732), [selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779), [selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160), [selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136); [Key Interactions](#key-interactions)).
5. **Observed result.** Broad scans cost more in proportion to their extra pages. One-row lookups stay flat until pages outnumber rows or the lookup repeats. Plans change shape: a sequential scan wins, an index drops out of a `BitmapAnd`, or a parallel scan gets more workers ([Bloat changes plans](#bloat-changes-plans), [Bloat changes parallel worker counts](#bloat-changes-parallel-worker-counts)).
6. **Refresh.** A non-partial index's new pages count at the next plan. A partial index's density and a backend's cached height wait for a `VACUUM`, `ANALYZE` or rebuild to rewrite the index's `pg_class` row, or for another invalidation ([Lifecycle Of The Planner Inputs](#lifecycle-of-the-planner-inputs)). Only a rebuild shrinks the file; `VACUUM`'s page recycling lets later splits reuse deleted pages but never returns them ([Deleted and half-dead pages](#deleted-and-half-dead-pages)).

### What Changed Since PostgreSQL 12

Since PostgreSQL 12 the cost formulas themselves barely moved. What changed is mostly how much bloat exists to be priced. On top of that, v17 added one new page-count input for `= ANY` searches, and v16 bounded a planning-time probe of an index's ends.

Each subsection below names the commit behind a change and what it does to the planner's index-size inputs. The [Since-v12 summary table](#since-v12-summary-table) lists them together.

#### How this section dates a change

Every attribution here comes from the pinned v17 checkout's own history. The checkout has no tags; it is a single-branch clone of `REL_17_STABLE` with its full history.

Each development cycle opens with a `Stamp HEAD as NNdevel.` commit:

| Stamp | Commit | Date |
|---|---|---|
| 13devel | `615cebc94b` | 2019-07-01 |
| 14devel | `d10b19e224` | 2020-06-07 |
| 15devel | `596b5af1d3` | 2021-06-28 |
| 16devel | `d31d30973a` | 2022-06-30 |
| 17devel | `5bcc7e6dc8` | 2023-06-29 |

A main-line commit that descends from one stamp but not from the next first shipped in that version. For example, a commit that descends from `d10b19e224` but not from `596b5af1d3` first shipped in PostgreSQL 14. Within 17.x, a commit belongs to the first `Stamp 17.N.` commit that contains it.

The v12 baseline is the branch point. The 13devel stamp's parent is `9e1c9f9594`, "pgindent run prior to branching v12." (2019-07-01), and the stamp itself changes only version strings, release notes and release tooling. So "unchanged since v12" below means that `git log -L`, run over `615cebc94b..HEAD` with the function's line range at the pin, lists no commit, or only commits whose changes cancel, and that the function's text at `615cebc94b` equals its text at the pin. "Before commit X" describes the lines that X's own diff removes.

Two limits follow from dating commits this way:

- **Back-patches.** The history dates the main-line commit only. A commit whose message says it was back-patched may also be in an older branch's minor releases, and this checkout cannot show which release first carried it. Three of the commits this section names say they were back-patched without naming a release: `9c6ad5eaa9` ("Back-patch to all supported branches"), `d3751adcf1` ("Back-patch to v11") and `9f3665fbfc` ("Backpatch: 13-"). Only the first two can reach 12.x releases. [Open Questions](#open-questions) records what that leaves unknown for PostgreSQL 12.
- **Branch point, not release.** `REL_12_STABLE` kept receiving fixes after it branched, and such a fix usually landed on the main line too, after `615cebc94b`. So a `615cebc94b..HEAD` range can list a change that 12.x releases also carry. `d3751adcf1` (2019-07-12), in the endpoint probe's history below, says it was back-patched to v11, so it may be one.

#### The cost code that did not change at all

This is the history of the four functions that turn index size into cost, since the v12 branch point:

| Function | Commits in `615cebc94b..HEAD` | Net change |
|---|---|---|
| `index_pages_fetched()` ([costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)) | none | none: its text at `615cebc94b` equals the pin's |
| `cost_index()` ([costsize.c#cost_index](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L549-L821)) | `8ce3aa9b59` "Rename files and headers related to index AM" and its revert, `7854e07f25` | none: its text at `615cebc94b` equals the pin's |
| `genericcostestimate()` ([selfuncs.c#genericcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6626-L6828)) | `9391f71523` and `5bf748b86b`, both first in 17 | one hunk: the caller now supplies `num_sa_scans` ([selfuncs.c#genericcostestimate-num_sa_scans](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6657-L6679)), and `estimate_array_length()` takes `root` and returns a `double` |
| `btcostestimate()` ([selfuncs.c#btcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6870-L7211)) | `9fd45870c1` (16), `eb5c4e953b` (16), `9391f71523` (17), `5bf748b86b` (17), `950d4a2cb1` (17) | two functional commits, `9391f71523` and `5bf748b86b`; the other three replace a `MemSet` call, extract the `50.0` multiplier into a macro, and fix a typo |

So the parts of `genericcostestimate()` that price bloat are the same as at the v12 branch point: the `numIndexPages` prorating, the `index->pages > 1 && index->tuples > 1` guard, the Mackert-Lohman call for repeated scans, and the single-scan charge ([selfuncs.c#genericcostestimate-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6786)). A reader who knows the v12 model already knows most of the v17 one.

#### v16: the 50x page charge became a macro

`eb5c4e953b` "Extract the multiplier for CPU process cost of index page into a macro" (2023-01-08, first in 16) changed only the spelling. Its diff replaces the literal `50.0` in `(index->tree_height + 1) * 50.0 * cpu_operator_cost` with `DEFAULT_PAGE_CPU_MULTIPLIER` in `btcostestimate()`, `gistcostestimate()` and `spgcostestimate()`, and defines the macro as `50.0` ([selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145)). The three charges at the pin read the macro ([selfuncs.c:7104](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7104), [selfuncs.c:7299](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7299), [selfuncs.c:7354](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7354)). The value, and therefore the behavior, is unchanged.

The companion commit `cd9479af2a` "Improve GIN cost estimation" (2023-01-08, also first in 16) applied the same multiplier inside `gincostestimate()`. There it is a CPU charge for each entry page and data page the scan expects to touch ([selfuncs.c#gincostestimate-page-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7937-L7955), [selfuncs.c:8015](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8015)). That changes how GIN bloat is priced, but it does not touch the B-tree path.

#### v13: GIN's whole-index estimate narrowed

`4b754d6c16e` "Avoid full scan of GIN indexes when possible" (2020-01-18, first in 13) is the other commit that changed `gincostestimate()` since the v12 branch point. It also changed GIN's executor, in `ginget.c`, `ginscan.c` and `gin_private.h`.

Before it, a single `haveFullScan` flag covered the whole query. Any match-all key set it, and the cost estimate then priced the scan as if every entry in the index had been listed in the query: the commit's diff removes the test `if (counts.haveFullScan || indexQuals == NIL)`.

Since the commit the flags are per column. A match-all key sets `attHasFullScan` and a default or include-empty key sets `attHasNormalScan` ([selfuncs.c#gincost_pattern-searchmode](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7454-L7489)). The whole-index branch fires only when some column has a full-scan key and no normal key ([selfuncs.c#gincostestimate-fullscan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7852-L7877)). So a query that pairs a match-all key with an ordinary key on the same column is no longer charged for every entry of a possibly bloated GIN index. No fixture here measures this change.

#### v17: index pages now cap ScalarArrayOp descents

`5bf748b86b` "Enhance nbtree ScalarArrayOp execution." (2024-04-06, first in 17) is the only commit since the v12 branch point that added a cost input through which a bloated B-tree is charged more than its dense twin. It introduced the clamp `num_sa_scans = Min(num_sa_scans, ceil(index->pages * 0.3333333))` ([selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042)); `git log -S'ceil(index->pages * 0.3333333)'` finds no other commit that adds or removes that expression. [Step 5: Clamp ScalarArrayOp descents (new in v17)](#step-5-clamp-scalararrayop-descents-new-in-v17) explains how the clamp prices bloat.

The same commit made `GenericCosts.num_sa_scans` an input as well as an output ([selfuncs.h#GenericCosts](../../../../raw/postgres-17/src/include/utils/selfuncs.h#L108-L138)). At the v12 branch point the field was already declared, as an output that `genericcostestimate()` computed. `btcostestimate()` now hands its own estimate over ([selfuncs.c#btcostestimate-genericcost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7067-L7073)), and `genericcostestimate()` counts the arrays itself only when it is given less than one ([selfuncs.c#genericcostestimate-num_sa_scans](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6657-L6679)). The commit also reworded the descent comments from "per SA scan" to "per estimated SA index descent" ([selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091), [selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)). The field's own comment now reads "# indexscans from ScalarArrayOpExprs"; `66bde49d96` (2019-08-13, first in 13) changed it from "# indexscans from ScalarArrayOps".

Before `5bf748b86b` there was no clamp. At the v12 branch point, `genericcostestimate()` set `num_sa_scans` to the product of the lengths of every `ScalarArrayOpExpr` among the index quals, and `btcostestimate()` charged both of its descent costs `costs.num_sa_scans` times (`git show 615cebc94b:src/backend/utils/adt/selfuncs.c`). So in v17 `index->pages` sets a ceiling on descent charges where the formula had no page-count input at that point. Fixture I measures the consequence: its dense and bloated twins diverge by 3.25x on a ten-element `= ANY`.

How v17's descent count compares with the branch point's depends on the array and on where the `= ANY` sits:

| Case | At the v12 branch point | In v17 | Bloat effect |
|---|---|---|---|
| A constant list in a boundary qual | the list's length; a `Const` array or an `ARRAY[...]` list has the same length in both ([selfuncs.c#estimate_array_length](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L2131-L2207)) | the same length, clamped to `ceil(index pages / 3)` ([selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042)) | a discount, never a surcharge: a bloated index keeps more of the old count than its dense twin. Fixture I measures this case |
| An `= ANY` outside the boundary quals | one descent per element, because the product covered every index qual | no extra descent: `btcostestimate()` counts only the boundary quals, which stop at the first index column without an `=` qual ([selfuncs.c#btcostestimate-bound-saop](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6904-L6989)) | none, whatever the index size; not measured here |
| A non-constant array, such as a parameterized `t.id = ANY(o.ids)` ([indxpath.c#match_saopclause_to_indexcol](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2651-L2669)) | a flat 10 (`estimate_array_length()` at `615cebc94b`) | the average distinct-element count in the array's statistics, or 10 without them ([selfuncs.c#estimate_array_length](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L2131-L2207)), then the clamp | with 40 elements in the statistics, an index of more than 30 pages is charged more descents than before, and a bloated index more than its dense twin while the twin's cap is below 40; not measured here |

The third row comes from `9391f71523` "Teach estimate_array_length() to use statistics where available." (2024-01-04, also first in 17). It changed how the *unclamped* array length is estimated, which feeds the same variable.

#### v16: partitioned indexes are zeroed out

`3c569049b7b` "Allow left join removals and unique joins on partitioned tables" (2023-01-09, first in 16) stopped skipping partitioned indexes in `get_relation_info()`, so that their uniqueness can prove joins. Its diff removes a skip whose comment read "Ignore partitioned indexes, since they are not usable for queries". It adds the `RELKIND_PARTITIONED_INDEX` guard ([plancat.c:471](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471)) that lists them with `pages = 0`, `tuples = 0.0` and `tree_height = -1` ([plancat.c#get_relation_info-partitioned](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L502-L508)).

So neither the branch point nor v17 gives a partitioned parent index a size, and bloat pricing is unchanged. The guard is the only change to what `get_relation_info()`'s index-size block computes since the branch point. The block's other three commits are a comment typo fix (`eef231e816`) and a `_bt_getrootheight()` argument that `61b313e47e` added and `d088ba5a5a` removed again.

#### v14: reltuples turns negative for never-analyzed relations

`3d351d916b2` "Redefine pg_class.reltuples to be -1 before the first VACUUM or ANALYZE." (2020-08-30, first in 14) made `-1` mean "unknown" ([pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L65-L66)). Its diff changes four things this page reads:

1. A rebuild's reset now writes `reltuples = -1` instead of `0` ([relcache.c#RelationSetNewRelfilenumber-reset](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3948-L3954)).
2. `index_update_stats()` keeps an existing `-1` when a build finds no entries. Because it already skipped writing a negative count at the v12 branch point, such a build now writes nothing ([index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842)).
3. `estimate_rel_size()`'s index branch trusts the recorded density only while `reltuples >= 0`; before, `relpages > 0` alone was enough ([plancat.c#estimate_rel_size-density](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1116-L1146)).
4. The table-side "never vacuumed" test changed too; see [v14 and v17: the table row estimate that non-partial indexes inherit](#v14-and-v17-the-table-row-estimate-that-non-partial-indexes-inherit).

For an index, "never analyzed" is not the condition that matters, and a new index does not start at `-1`. `index_create()` inserts the zero-filled row that `RelationBuildLocalRelation()` built, so a new index starts at `relpages = 0` and `reltuples = 0` ([index.c#index_create-pg_class](../../../../raw/postgres-17/src/backend/catalog/index.c#L1008-L1024), [relcache.c#RelationBuildLocalRelation-rd_rel](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3656-L3659)). Only a relation that `AddNewRelationTuple()` creates, such as a new table, starts at `-1`; an index's row does not ([heap.c#AddNewRelationTuple-empty](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1006-L1009)).

What each way of building an index leaves in its `pg_class` row at the pin:

| How the index is built | Row before the build | What the build writes | Row afterwards |
|---|---|---|---|
| `CREATE INDEX` | a new row, `relpages = 0`, `reltuples = 0` ([index.c#index_create-pg_class](../../../../raw/postgres-17/src/backend/catalog/index.c#L1008-L1024)) | its block and entry counts, also with no entries ([index.c#index_build-index-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3133-L3135)) | the counts; an empty B-tree is the metapage alone, `1` and `0` ([nbtsort.c#_bt_load-first-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1287-L1290)) |
| [`REINDEX CONCURRENTLY`](../../../glossary.md#concurrently) | a new index through `index_create()`, `0` and `0` ([index.c:1459](../../../../raw/postgres-17/src/backend/catalog/index.c#L1459)) | the counts | the counts |
| `REINDEX`, and every command that gives the table new storage, such as a [table rewrite](../../../glossary.md#table-rewrite) | reset to `0` and `-1` ([relcache.c#RelationSetNewRelfilenumber-reset](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3948-L3954), [index.c#reindex_index-rebuild](../../../../raw/postgres-17/src/backend/catalog/index.c#L3784-L3789)) | the counts, or nothing when the build found no entries ([index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842)) | the counts, or `0` and `-1` |
| `TRUNCATE` of a table created or given new storage in the current subtransaction | not reset: the table is emptied in place ([tablecmds.c#ExecuteTruncateGuts-in-place](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L2133-L2145), [heap.c#RelationTruncateIndexes](../../../../raw/postgres-17/src/backend/catalog/heap.c#L3083-L3087)) | as for `REINDEX` | can keep an earlier `-1`, never sets one |
| a build during binary upgrade, as `pg_upgrade` runs it | a new row, `0` and `0` | nothing, since `71b66171d0` (below) | `0` and `0` until `ANALYZE`, or a `VACUUM` whose index pass reports an exact count, writes the row ([analyze.c#do_analyze_rel-index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663), [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099)) |

The commands in the third row are `TRUNCATE`, which gives the table new, empty storage ([tablecmds.c#ExecuteTruncateGuts-rewrite](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L2167-L2189)), and [`VACUUM FULL`](../../../glossary.md#vacuum-full), [`CLUSTER`](../../../glossary.md#cluster), a table-rewriting `ALTER TABLE` and a non-concurrent `REFRESH MATERIALIZED VIEW`, which all end in `finish_heap_swap()` ([vacuum.c:2260](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2260), [cluster.c:670](../../../../raw/postgres-17/src/backend/commands/cluster.c#L670), [tablecmds.c:5873](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L5873), [matview.c:890](../../../../raw/postgres-17/src/backend/commands/matview.c#L890)). Each calls `reindex_relation()` ([cluster.c:1508](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1508)), which rebuilds every index with `reindex_index()` ([index.c:4048](../../../../raw/postgres-17/src/backend/catalog/index.c#L4048)).

`71b66171d0` "CREATE INDEX: do not update stats during binary upgrade." (2024-04-03, first in 17) added the last row's skip, because during binary upgrade "the indexes are created before the data is moved into place" ([index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842)). A cleanup-only B-tree pass reports an estimate, so it does not write the row either ([nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L851-L893)).

So an index holds `-1` only after a rebuild through `reindex_index()` produced no entries. The test is on the index's own entry count ([index.c#index_build-index-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3133-L3135)). A B-tree build counts each row the heap scan hands it ([nbtsort.c:599](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L599), [nbtsort.c:338](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L338)). The scan hands over no row that is dead to every transaction and no row that fails a partial index's predicate ([heapam_handler.c#heapam_index_build_range_scan-dead](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1419-L1423), [heapam_handler.c#index-build-predicate](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1636-L1644)). So a rebuild produces no entries when the table is empty, holds only such dead rows, or has no row that satisfies a partial index's predicate.

The index then keeps `-1` while later inserts fill it, until `ANALYZE` or a `VACUUM` with an exact count writes the row. Its catalog `relpages` stays `0` all that time, so the new `reltuples >= 0` half of the density test changes nothing for it. A non-partial index never reads its own `reltuples` anyway, because its tuple count is the table's estimate ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)).

Before `3d351d916b2` there was no `-1` state for an index: the reset wrote `reltuples = 0` (the commit's `relcache.c` hunk), and there was no hack to keep, so every build wrote its counts.

One consequence shows on a partial B-tree. Take one whose rebuild produced no entries, so that the build wrote the metapage alone, and which later inserts filled. Both versions take `estimate_rel_size()`'s width-based fallback for it, but they differ by one page. Before the commit, the row held `relpages = 1`, and the metapage discount left no page of density data. In v17 the row holds `relpages = 0`, which skips the discount. So v17 estimates one page's worth of fallback density more, before `get_relation_info()` clamps the result to the table's rows ([plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160)).

#### v14 and v17: the table row estimate that non-partial indexes inherit

A non-partial index takes its `tuples` from the table's row estimate ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)). `table_block_relation_estimate_size()` computes that estimate ([tableam.c#table_block_relation_estimate_size-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L711-L747)). So a change there moves every such index's `pages / tuples` ratio. Three commits since the v12 branch point changed it:

| Commit | First release | What its diff changes | Effect on an index's `tuples` |
|---|---|---|---|
| `3d351d916b2` | 14 | the "never vacuumed" test, which counts a table without inheritance children as at least 10 pages, from `relpages == 0` to `reltuples < 0` ([tableam.c#table_block_relation_estimate_size-never-vacuumed](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L690-L699)) | A table that `VACUUM` emptied and truncated to zero blocks records `relpages = 0` and `reltuples = 0` ([vacuumlazy.c#heap_vacuum_rel-relstats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L556-L575)). It is now estimated at zero rows ([tableam.c#table_block_relation_estimate_size-empty](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L703-L709)), so each scan of its non-partial indexes is charged one page ([selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732)). Before, it counted as never vacuumed and got at least 10 pages of rows |
| `29cf61ade3` | 17.0 | the width-based density for a table without statistics is scaled by the table's fillfactor ([tableam.c#table_block_relation_estimate_size-fillfactor](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L733-L743)) | A low-fillfactor table without statistics is estimated at fewer rows (the message says the old estimate could be up to 10x too high at the minimum fillfactor of 10), which raises its indexes' `pages / tuples` |
| `587b6aa3f3` | 17.5 ("Backpatch-through: 17") | that density is clamped to at least one row per page ([tableam.c#table_block_relation_estimate_size-min-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L744-L745)) | In 17.0 to 17.4, rows wider than the fillfactor space gave a density of 0, which the message says left the relation estimated at a single row; its indexes' `tuples` copied the table's zero and fell under the one-page guard |

This page measures none of the three.

#### v16, back-patched: the endpoint probe gives up after 100 heap pages

`9c6ad5eaa9` "YA attempt at taming worst-case behavior of get_actual_variable_range." (2022-11-22, first in 16) changed how dead index entries at the end of a B-tree reach the planner. It changes a row estimate, not a cost formula. [Step 6: Probe the ends of a B-tree while estimating rows](#step-6-probe-the-ends-of-a-b-tree-while-estimating-rows) explains the probe itself.

Before the commit, `get_actual_variable_endpoint()` had no page limit, so it walked the whole run of dead entries. That cost planning time, but dead entries sent the estimate back to the histogram bound only when no live entry remained at all. The commit's diff adds a counter. Each time a rejected entry points at a different heap page from the one before, the probe counts a page, and it gives up once the count passes 100 ([selfuncs.c#VISITED_PAGES_LIMIT](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6447-L6455)). The caller then keeps whatever bound `pg_statistic` recorded ([selfuncs.c#get_actual_variable_endpoint-give-up](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6409-L6413)).

So since the limit, a delete at one end of the index that leaves dead entries spanning more than 100 heap pages sends the next plans back to the stale bound, and their row estimates can change. On a primary this lasts until killed entries let a plan reach an accepted row, `VACUUM` removes the entries, or `ANALYZE` rebuilds the histogram from live rows ([selfuncs.c#get_actual_variable_endpoint-killed](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6388-L6397), [indexam.c#index_fetch_heap-kill](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L644-L652)). On a hot standby only a replayed removal or a replayed `ANALYZE` ends it, because a transaction that started during recovery neither marks entries killed nor skips marked ones ([genam.c#RelationGetIndexScan-recovery](../../../../raw/postgres-17/src/backend/access/index/genam.c#L107-L119), [nbtxlog.c#btree_xlog_vacuum](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L598-L634)).

Fixture E, run on a single primary server, measures the primary case: four plans at `rows=10`, each marking another 100 heap pages' worth of entries dead (22,590 after the first plan, 90,390 after the fourth), then a fifth plan at `rows=1`. See [Dead entries at the end of a B-tree: the endpoint probe](#dead-entries-at-the-end-of-a-b-tree-the-endpoint-probe).

The commit message says "Back-patch to all supported branches". Which older branches and minor releases that covers cannot be read from this checkout, so [Open Questions](#open-questions) records the gap for PostgreSQL 12. Two earlier commits changed the same function since the v12 branch point. `d3751adcf1` (2019-07-12, first in 13) taught it to cope with broken HOT chains and says it was back-patched to v11. `dc7420c2c9` (2020-08-12, first in 14) replaced the horizon of the probe's snapshot: its diff changes `InitNonVacuumableSnapshot(SnapshotNonVacuumable, RecentGlobalXmin)` to take `GlobalVisTestFor(heapRel)` ([selfuncs.c#get_actual_variable_endpoint-horizon](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6415-L6416)).

#### v13: deduplication

`0d861bbb702` "Add deduplication to nbtree." (2020-02-26, first in 13) introduced posting-list tuples. Its diff adds three pieces:

- the new `nbtdedup.c`, whose lazy pass runs before a leaf page would split ([nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L33-L58));
- deduplication during index builds in `nbtsort.c` ([nbtsort.c#_bt_load-deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1151-L1152));
- the `deduplicate_items` storage parameter in `reloptions.c` ([reloptions.c#deduplicate_items](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L167)).

It changes no cost formula. It changes how many pages a duplicate-heavy index needs, and therefore what the unchanged formula is fed. Fixture N measures 852 blocks against 2,749 for the same data with the feature disabled.

An index built on PostgreSQL 12 and carried into v17 by `pg_upgrade` does not deduplicate until it is rebuilt. Deduplication needs the metapage's `btm_allequalimage` flag, only `CREATE INDEX` or `REINDEX` sets it, and "pg_upgrade hasn't been taught to set the metapage field" ([nbtree.h#btm_allequalimage-upgrade](../../../../raw/postgres-17/src/include/access/nbtree.h#L135-L141), [btree.sgml#deduplication-safety](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L834-L838)). An `INCLUDE` index, or one with an operator class that lacks a `BTEQUALIMAGE_PROC` returning true, never deduplicates ([nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183)).

Bottom-up index deletion, below, has no such gate: `_bt_delete_or_dedup_one_page()` runs it before the `allequalimage` test that guards deduplication ([nbtinsert.c#_bt_delete_or_dedup_one_page-dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2782)). So an upgraded v12 index gets bottom-up deletion at once, but deduplication only after a `REINDEX`.

#### v14: bottom-up index deletion

`d168b666823` "Enhance nbtree index tuple deletion." (2021-01-13, first in 14) added `_bt_bottomupdel_pass()` ([nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L280-L320)). The v17 documentation states the boundary directly: "Prior to PostgreSQL 14, the only category of B-Tree deletion was simple deletion" ([btree.sgml#simple-vs-bottom-up](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L679-L703)). The README says bottom-up index deletion "was added to PostgreSQL 14" ([README#deduplication-and-bottom-up-note](../../../../raw/postgres-17/src/backend/access/nbtree/README#L980-L988)).

The documentation also says such an index's on-disk size may "never increase by even one single page/block despite constant version churn" ([btree.sgml#bottom-up-effectiveness](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L704-L720)). Fixture P measures less than that under a deliberately harsh churn: five whole-table rounds with no `VACUUM` grew the index 3.2x, against 6.9x when an old snapshot blocked deletion. Fixture P-100 measures no difference at all on a column with ten times fewer distinct values. [Open Questions](#open-questions) keeps the documentation's stronger claim open.

#### v16: updates of only summarizing-index columns can stay HOT

`19d8e2308b` "Ignore BRIN indexes when checking for HOT updates" (2023-03-20, first in 16) removed one source of version-churn B-tree entries. Its message says it re-applies `5753d4ee32`, which `e3fcca0d0d` reverted. Both of those fall in the 15 development cycle, before the 16devel stamp, so they net to nothing.

Before `19d8e2308b`, `heap_update()` tested the modified columns against `INDEX_ATTR_BITMAP_ALL`, the columns of every index on the table, BRIN included. The table AM then set a single boolean that told the executor to insert into every index or into none (the commit's `heapam.c` and `heapam_handler.c` hunks). So an `UPDATE` that changed only a BRIN-indexed column was never HOT, and it wrote a new entry into every B-tree on the table.

In v17 the relcache keeps separate column sets for hot-blocking and for summarizing indexes, chosen by the access method's `amsummarizing` flag ([relcache.c#RelationGetIndexAttrBitmap-summarizing](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L5390-L5398)), which BRIN sets ([brin.c:269](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L269)). `heap_update()` tests HOT against the hot-blocking set only ([heapam.c#heap_update-attr-bitmaps](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L3434-L3437), [heapam.c#heap_update-hot-decision](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4140-L4166)). It reports `TU_Summarizing` when the update touched only summarizing columns ([heapam.c#heap_update-update-indexes](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4415-L4429), [tableam.h#TU_UpdateIndexes](../../../../raw/postgres-17/src/include/access/tableam.h#L113-L127)), and `ExecInsertIndexTuples()` then skips every non-summarizing index ([execIndexing.c#ExecInsertIndexTuples-onlySummarizing](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L361-L366)).

The saving holds only while the new version fits on the old page; [Version-churn duplicates from non-HOT UPDATEs](#version-churn-duplicates-from-non-hot-updates) describes that limit. No fixture here measures it.

#### v14: faster recycling of deleted pages

`9dd963ae253` "Recycle nbtree pages deleted during same VACUUM." (2021-03-21, first in 14) shortened the time deleted pages stay dead weight. The README says that before v14 VACUUM placed only *previously* deleted pages in the free space map, and "PostgreSQL 14 added the ability for VACUUM to consider if it's possible to recycle newly deleted pages at the end of the full index scan where the page deletion took place" ([README#postgresql-14-fsm-change](../../../../raw/postgres-17/src/backend/access/nbtree/README#L403-L424)).

Recycling still only records a deleted page in the free space map for reuse ([README#placing-deleted-pages-in-the-fsm](../../../../raw/postgres-17/src/backend/access/nbtree/README#L383-L441)). No file under `src/backend/access/nbtree/` calls `RelationTruncate()` or `smgrtruncate()` (a `grep` at the pin finds none), so the file never shrinks. The planner reads the live block count ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)) and keeps paying for those pages until a rebuild. Fixture M measures 2,465 deleted pages still inside a 2,745-block index after three VACUUMs.

Two earlier commits in the 14 cycle changed the same recycling path. `e5d8a99903` "Use full 64-bit XIDs in deleted nbtree pages." (2021-02-24) stores a 64-bit `safexid` in each deleted page ([nbtree.h#BTDeletedPageData](../../../../raw/postgres-17/src/include/access/nbtree.h#L230-L236)). Its message says that otherwise "we risk "leaking" deleted pages by making them non-recyclable indefinitely".

The same diff replaces the metapage's oldest-[XID](../../../glossary.md#transaction-id) field, `btm_oldest_btpo_xact`, with `btm_last_cleanup_num_delpages` ([nbtree.h#BTMetaPageData](../../../../raw/postgres-17/src/include/access/nbtree.h#L103-L119)). `_bt_vacuum_needs_cleanup()` uses that count to decide whether a cleanup-only VACUUM must scan the index. It asks for a scan when the count exceeds 5% of the index's blocks, or when the metapage is too old to hold the count ([nbtpage.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L172-L223)).

`9f3665fbfc` "Don't consider newly inserted tuples in nbtree VACUUM." (2021-03-10) removed the `vacuum_cleanup_index_scale_factor` setting, so inserted tuples no longer trigger that scan. Its message says "Backpatch: 13-", and `effdd3f3b6`'s message says that 13 only disabled the setting. `effdd3f3b6` "Add back vacuum_cleanup_index_scale_factor parameter." (2021-03-11, also first in 14) restored the B-tree storage parameter, though not the [GUC](../../../glossary.md#guc), to avoid dump and reload hazards. The parameter is marked "Deprecated B-Tree parameter." and no code reads its value: a grep of the checkout's `.c` and `.h` files finds it only declared and parsed ([reloptions.c#vacuum_cleanup_index_scale_factor](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L462-L470), [nbtree.h:1134](../../../../raw/postgres-17/src/include/access/nbtree.h#L1134), [nbtutils.c#btoptions-parse-table](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4566-L4567)).

`9f3665fbfc` also marks the tuple count of a cleanup-only B-tree scan as an estimate ([nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L851-L893)), and VACUUM writes an index's `relpages` and `reltuples` only from an exact count ([vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099)). So a VACUUM that only cleans up a B-tree no longer refreshes its `pg_class` row. Before the commit it did: `btvacuumscan()` reset `estimated_count` to false (the diff removes that line), and at the v12 branch point `lazy_cleanup_index()` called `vac_update_relstats()` for the index whenever the count was not an estimate (`git show 615cebc94b:src/backend/access/heap/vacuumlazy.c`).

The planner's size estimate reads that row only for a partial index, whose tuple count comes from its recorded density ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)). [A partial index hides its growth until its statistics are rewritten](#a-partial-index-hides-its-growth-until-its-statistics-are-rewritten) measures what a stale row costs. Neither commit changes a cost formula.

#### v14: VACUUM can skip index vacuuming on its own

Two commits in the 14 cycle made VACUUM skip index vacuuming by itself: `5100010ee4d` "Teach VACUUM to bypass unnecessary index vacuuming." (2021-04-07), the 2% `BYPASS_THRESHOLD_PAGES` rule, and `1e55e7d1755` "Add wraparound failsafe to VACUUM." (2021-04-07).

At the v12 branch point, VACUUM skipped index vacuuming only on request. `VACUUM (INDEX_CLEANUP false)` or the boolean `vacuum_index_cleanup` storage parameter cleared `useindex`, which skipped index vacuuming and index cleanup together (`git show 615cebc94b:src/backend/access/heap/vacuumlazy.c`: `useindex = (nindexes > 0 && params->index_cleanup == VACOPT_TERNARY_ENABLED)`).

A third commit, `3499df0dee8` "Support disabling index bypassing by VACUUM." (2021-06-18, first in 14), turned that boolean storage parameter into a three-valued one with `auto`, which is now the default. A VACUUM that names no `INDEX_CLEANUP` takes the parameter's value ([reloptions.c#vacuum_index_cleanup](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L510-L520), [vacuum.c#index_cleanup-default](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2155-L2179)). [`INDEX_CLEANUP ON`](../../../glossary.md#index_cleanup), or `vacuum_index_cleanup = on`, now forces index vacuuming by switching the 2% bypass off, though it cannot switch off the failsafe ([vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402)).

The 2% bypass clears only `do_index_vacuuming`, so it never skips index cleanup ([vacuumlazy.c#lazy_vacuum-bypass-branch](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949)). The failsafe clears `do_index_cleanup` as well ([vacuumlazy.c#lazy_check_wraparound_failsafe-clears](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326)).

#### Since-v12 summary table

| Change | First release | Effect on planner-visible bloat | Current code |
|---|---|---|---|
| `0d861bbb702` deduplication | 13 | Fewer pages for duplicate-heavy indexes built or rebuilt on v13 or later; an index `pg_upgrade` carried over from v12 needs a `REINDEX` first; measured 3.2x | [nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L33-L58), [nbtree.h#btm_allequalimage-upgrade](../../../../raw/postgres-17/src/include/access/nbtree.h#L135-L141) |
| `4b754d6c16e` per-column GIN full-scan test | 13 | Fewer GIN scans charged for every entry of a possibly bloated index: only a column with a match-all key and no normal key triggers the whole-index estimate | [selfuncs.c#gincostestimate-fullscan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7852-L7877) |
| `3d351d916b2` `reltuples = -1` | 14 | An index holds `-1` only after an empty rebuild through `reindex_index()`, with `relpages = 0`, so the density test never changes branch for it. A table that `VACUUM` emptied and truncated is now estimated at zero rows, so each scan of its non-partial indexes is charged one page | [index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842), [tableam.c#table_block_relation_estimate_size-never-vacuumed](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L690-L699) |
| `d168b666823` bottom-up index deletion | 14 | Fewer pages under non-HOT `UPDATE` churn; measured 543 against 1,173 blocks with deletion blocked (2.2x) on a 1,000-value column, and no difference on a 100-value one | [nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L280-L320) |
| `e5d8a99903` 64-bit XIDs in deleted pages | 14 | Deleted pages can no longer become unrecyclable; the file still does not shrink | [nbtree.h#BTDeletedPageData](../../../../raw/postgres-17/src/include/access/nbtree.h#L230-L236) |
| `9f3665fbfc` inserts no longer trigger cleanup | 14; its message says "Backpatch: 13-" | Cleanup-only index scans are no longer driven by inserted tuples, and a cleanup-only B-tree VACUUM no longer rewrites the index's `relpages` and `reltuples`, which only a partial index's estimate reads | [nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L851-L893) |
| `9dd963ae253` recycle newly deleted pages | 14 | Deleted pages are reusable sooner; the file still does not shrink | [README#postgresql-14-fsm-change](../../../../raw/postgres-17/src/backend/access/nbtree/README#L403-L424) |
| `5100010ee4d` 2% index-vacuum bypass | 14 | A new automatic way for dead index entries to stay, while index cleanup still runs | [vacuumlazy.c#lazy_vacuum-bypass-branch](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949) |
| `1e55e7d1755` wraparound failsafe | 14 | Skips index vacuuming and index cleanup under wraparound pressure | [vacuumlazy.c#lazy_check_wraparound_failsafe-clears](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326) |
| `3499df0dee8` `INDEX_CLEANUP` auto | 14 | Lets an operator force index vacuuming: it switches off the 2% bypass, not the failsafe | [vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402) |
| `eb5c4e953b` `DEFAULT_PAGE_CPU_MULTIPLIER` | 16 | Cosmetic; the value stays 50.0 | [selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145) |
| `cd9479af2a` GIN page CPU charges | 16 | Changes GIN bloat pricing, not B-tree pricing | [selfuncs.c#gincostestimate-page-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7937-L7955) |
| `3c569049b7b` partitioned-index zeroing | 16 | Lists partitioned indexes with zero size; the branch point skipped them, so pricing is unchanged | [plancat.c#get_relation_info-partitioned](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L502-L508) |
| `9c6ad5eaa9` endpoint-probe page limit | 16; its message says "Back-patch to all supported branches" | Not a cost input: dead entries at the end of a B-tree can hold a range estimate on the stale histogram bound for several plans; measured `rows=10` for four plans, then `rows=1` | [selfuncs.c#VISITED_PAGES_LIMIT](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6447-L6455) |
| `19d8e2308b` summarizing-only updates stay HOT | 16 | An update of only BRIN-indexed columns adds no B-tree entry while the new version fits on its page; before, it added one to every index | [heapam.c#heap_update-update-indexes](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4415-L4429), [execIndexing.c#ExecInsertIndexTuples-onlySummarizing](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L361-L366) |
| `5bf748b86b` SAOP descent clamp | 17 | A **new** `index->pages` input for `= ANY`. For a constant list in a boundary qual it is a cap that discounts small or dense indexes relative to the branch point; an `= ANY` outside the boundary quals gets one descent instead of one per element | [selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042) |
| `9391f71523` `estimate_array_length()` statistics | 17 | Sizes a non-constant array from its element statistics instead of a fixed 10, which can raise or lower the descent count before the clamp | [selfuncs.c#estimate_array_length](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L2131-L2207) |
| `29cf61ade3` fillfactor in the table estimate | 17 | A low-fillfactor table without statistics is estimated at fewer rows, which raises its indexes' `pages / tuples` | [tableam.c#table_block_relation_estimate_size-fillfactor](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L733-L743) |
| `71b66171d0` no index statistics during binary upgrade | 17 | An index `pg_upgrade` creates keeps `relpages = 0` and `reltuples = 0` until `ANALYZE`, or a `VACUUM` whose index pass reports an exact count, writes its row; only a partial index's estimate reads them | [index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842) |
| `587b6aa3f3` at least one row per page | 17.5 | Ends the zero-row table estimate for rows wider than the fillfactor space | [tableam.c#table_block_relation_estimate_size-min-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L744-L745) |
| `index_pages_fetched()`, `cost_index()` | unchanged | Their text at `615cebc94b` equals the pin's | [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951), [costsize.c#cost_index](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L549-L821) |
| `numIndexPages` prorating, height charge | unchanged | The same formulas, and the same 50.0 multiplier under a new name | [selfuncs.c#genericcostestimate-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6786), [selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106) |

### Settings That Move The Boundary

Every setting below is `PGC_USERSET`, so each takes effect at session or transaction scope with `SET`, with no reload and no restart. None of them is a bloat control. They change how heavily the existing page count is weighted.

| Setting | v17 default | Role in bloat pricing | Apply scope |
|---|---|---|---|
| `random_page_cost` | 4.0, `DEFAULT_RANDOM_PAGE_COST` ([cost.h:25](../../../../raw/postgres-17/src/include/optimizer/cost.h#L25)) | Multiplies each index page the estimate counts as fetched: the pro-rata `numIndexPages` on a single scan, or the Mackert-Lohman result on a repeated one ([selfuncs.c#genericcostestimate-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6786)); see note 1 | session or transaction ([guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696)) |
| `cpu_operator_cost` | 0.0025, `DEFAULT_CPU_OPERATOR_COST` ([cost.h:28](../../../../raw/postgres-17/src/include/optimizer/cost.h#L28)) | Scales the B-tree comparison charge and the per-level height charge `(tree_height + 1) * 50 * cpu_operator_cost`, the charge the source names as its guard against bloat ([selfuncs.c#btcostestimate-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7106)) | session or transaction ([guc_tables.c#cpu_operator_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3719-L3729)) |
| `effective_cache_size` | 524288 pages, 4GB at 8kB blocks, `DEFAULT_EFFECTIVE_CACHE_SIZE` ([cost.h:34](../../../../raw/postgres-17/src/include/optimizer/cost.h#L34)) | Sets the cache that the Mackert-Lohman model shares out between the query's tables and the index being priced ([costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)); see note 2 | session or transaction ([guc_tables.c#effective_cache_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3518)) |
| `min_parallel_index_scan_size` | `(512 * 1024) / BLCKSZ`, 64 blocks or 512kB at 8kB blocks ([guc_tables.c#min_parallel_index_scan_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3531-L3540)) | The smallest touched-page estimate at which an index path can go parallel, and the base of the worker ramp; both read the scan's `numIndexPages`, not `index->pages` ([costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L772)); see note 3 | session or transaction ([guc_tables.c#min_parallel_index_scan_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3531-L3540)) |

Notes:

1. B-tree upper levels are charged CPU only ([selfuncs.c#btcostestimate-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7106)), and BRIN charges its range-map pages at `seq_page_cost` ([selfuncs.c#brincostestimate-page-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8244-L8258)). A tablespace's own `random_page_cost`, set with `ALTER TABLESPACE … SET`, replaces the setting for every index stored there. That override is not a GUC change: `genericcostestimate()` looks the page cost up by the index's tablespace ([selfuncs.c#genericcostestimate-tablespace](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6734-L6737), [spccache.c#get_tablespace_page_costs](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L181-L196)).
2. `index_pages_fetched()` gives the relation being priced `effective_cache_size * T / (total_table_pages + index_pages)`. So a larger index takes a larger share for its own repeated scans and leaves a smaller share for the heap ([costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)). [Step 4: Apply the cache model and pick workers](#step-4-apply-the-cache-model-and-pick-workers) walks through the model.
3. The index threshold is necessary, not sufficient. A plain index scan must also have a heap-page estimate of at least `min_parallel_table_scan_size`, and it gets the smaller of the heap and index worker counts; only an index-only scan skips the heap test ([costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L772)). A table's `parallel_workers` storage parameter bypasses all of it ([allpaths.c#compute_parallel_worker-reloption](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4208-L4213), [allpaths.c#compute_parallel_worker-threshold](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4216-L4227), [allpaths.c#compute_parallel_worker-index-ramp](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4253-L4272)).

Two per-index storage parameters change the physical layout rather than its price. Both take `ShareUpdateExclusiveLock` with the in-tree reason "since it applies only to later inserts" ([reloptions.c#intRelOpts-fillfactor-btree](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L185-L194), [reloptions.c#deduplicate_items](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L167)). Neither is inert on the pages that already exist, so "no effect until a rebuild" is too strong. Both are read at the moment a leaf page is about to split:

| Storage parameter | Read when | Effect on pages that already exist | What a rebuild does |
|---|---|---|---|
| `fillfactor` | by `_bt_findsplitloc()` on every split ([nbtsplitloc.c#leaffillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L170-L176)) | sets the target of the next rightmost or split-after-new-item leaf split, also on a page built under the old value; every other leaf split starts from 50:50 ([nbtsplitloc.c#_bt_findsplitloc-fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L334)) | fills every leaf page to it ([nbtsort.c#_bt_pagestate-leaf-fill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L661-L665)) |
| `deduplicate_items` | by `_bt_delete_or_dedup_one_page()` before a leaf page splits ([nbtinsert.c#_bt_delete_or_dedup_one_page-dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2782)) | compacts an existing leaf in place when an insert reaches it, if the index is `allequalimage` and no earlier exit fired | deduplicates only when it is on, the index is `allequalimage`, and the index is not unique ([nbtsort.c#_bt_load-deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1151-L1152)) |

Pages crowded with duplicates can override the fillfactor target. `_bt_strategy()` can take over any leaf split other than an exact split after the new item, when the default split interval has no split point that avoids adding a heap TID to the new high key ([nbtsplitloc.c:317](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L317), [nbtsplitloc.c:364](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L364), [nbtsplitloc.c#split-strategies](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L364-L416), [nbtsplitloc.c#_bt_strategy](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L985-L1041)). A page that is not entirely one value then splits beside its group of duplicates (`SPLIT_MANY_DUPLICATES`).

A page entirely of one value that is the last page holding it, meaning the rightmost leaf or a page whose high key differs from the new item, splits at `BTREE_SINGLEVAL_FILLFACTOR`, 96%, whatever the index fillfactor ([nbtree.h:202](../../../../raw/postgres-17/src/include/access/nbtree.h#L202)). A page entirely of one value that is not the last page of that value keeps the default split.

The deduplication pass runs only after three earlier exits have not fired ([nbtinsert.c#early-returns](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2721-L2776)):

1. [Simple deletion](../../../glossary.md#simple-index-deletion) of `LP_DEAD` entries frees room for the new item.
2. The caller asked for simple deletion only, or is a unique-index insert that found no duplicate.
3. A bottom-up deletion pass frees enough space.

Only the first and third exits avoid the split. The second returns before the deduplication pass without making room for the new item, so its page can still split undeduplicated.

`allequalimage` is fixed into the metapage when the index is built, and the storage parameter does not change it ([nbtsort.c#_bt_leafbuild-allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L560-L564)). It is false for any index with `INCLUDE` columns, and otherwise depends on each key column's operator class and collation ([nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183)). The v17 source also relies on it being zero on an index `pg_upgrade` carried over from PostgreSQL 12 ([nbtpage.c#_bt_metaversion-comment](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L720-L737)).

What a rebuild adds is reach and immediacy. `REINDEX` applies the new layout to every page at once, instead of page by page as traffic happens to touch them, which is one of the scenarios its reference page documents ([ref/reindex.sgml#storage-parameter](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml#L66-L71)). A rebuild applies the index's storage parameters as they stand, not a healthy default. That is why the `l3_c` bloating step in [Bloat changes plans](#bloat-changes-plans) uses `ALTER INDEX … SET (fillfactor = 10)` followed by `REINDEX`. Fixture N instead builds its two variants directly, one of them with `CREATE INDEX … WITH (deduplicate_items = off)`.

### Practical Interpretation

- **Read the planner's bloat cost from blocks, not from `avg_leaf_density`.** The planner is charged for blocks ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)), and fixture M shows a 10x-oversized index reporting 89.18% density. [What The Planner Does Not See](#what-the-planner-does-not-see) lists what the planner ignores.
- **Do not read blocks per row as a rebuild verdict.** A rebuild reapplies the index's storage parameters: it fills leaves only to the fillfactor and skips deduplication while `deduplicate_items` is off ([nbtsort.c#_bt_pagestate-leaf-fill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L661-L665), [nbtsort.c#_bt_load-deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1151-L1152)). So fixture N's `n_off` (2,749 blocks against 852) and fixture A's `a_sparse_idx` (26,411 against 2,745) would come back at about the same size. That is a source reading; this page's script rebuilds neither index.
- **A partial index's population is not the table's row count.** `ANALYZE` counts only the sampled rows that pass the predicate ([analyze.c#partial-index-population](../../../../raw/postgres-17/src/backend/commands/analyze.c#L902-L908), [analyze.c#tupleFract](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953)). This page's advice is about planner pricing. It has not been scored against [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md), the wiki's acceptance suite for rebuild decisions.
- **Do not expect a bloated index to be abandoned by short transactional lookups (OLTP, online transaction processing).** While the index has no more pages than the table has rows, a single point lookup that touches one leaf page is charged only the height difference ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)). That is `0.125` per level at default settings, about 1.5% of fixture H's heap-fetching lookup and 2.8% of fixture A's index-only one.
- **The height charge still sees a level.** Fixture B's lookup drops from `4.44` to `4.31` when a rebuild removes one, and fixture H's two lookups cost `8.31` and `8.43`. Only the page charge is blind; see [Step 3: Charge the B-tree height](#step-3-charge-the-b-tree-height).
- **Two independent things end that blindness.** The first is an index with more pages than its table has rows, which a drained queue table leaves behind: fixture F's one-row lookup costs `12.29`, against `4.29` after a rebuild ([selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732)). The second is repetition as a nested-loop inner scan, priced through the cache model with the whole index as the page universe ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779)): fixture A costs `2.50` against `0.66` per loop. [A mostly-empty index: the fast root drops and pages outnumber rows](#a-mostly-empty-index-the-fast-root-drops-and-pages-outnumber-rows) and [Index pages in the cache model](#index-pages-in-the-cache-model) work both through.
- **The join case is the one people miss.** The lookup it repeats looks free when priced alone. Bloat moves its repeated price from almost nothing, for a few loops over a large index, to linearly in the index's pages once loops times touched pages reach twice the index size, for an index that fits its share of `effective_cache_size` ([costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)). A rebuild changes what such lookups cost in both shapes.
- **Do not read a cheap plan on a nearly empty table as evidence that its index is healthy.** `ceil(pages / tuples)` runs only while `index->pages > 1` and `index->tuples > 1`; otherwise every scan is charged one page, whatever the index's size ([selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732)). A non-partial index inherits the table's row estimate ([plancat.c:476](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L476)), which is zero for a table that `VACUUM` emptied and truncated ([v14 and v17: the table row estimate that non-partial indexes inherit](#v14-and-v17-the-table-row-estimate-that-non-partial-indexes-inherit)). [The pages-outnumber-rows guard at its limit](#the-pages-outnumber-rows-guard-at-its-limit) measures a one-row table on 551 blocks.
- **Do not read the planner's height from `pgstatindex`.** `pgstatindex`'s `tree_level` is the true root level ([pgstatindex.c#pgstatindex_impl-metapage](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L252-L265)). The planner charges the fast-root level, which VACUUM's page deletion can lower without a rebuild ([nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717)). `bt_metap()` shows both, but only as they are on disk now; see the next point.
- **A backend may price an index from an older metapage.** It keeps its cached copy until a relcache invalidation reaches it or one of its scans trips `_bt_getroot()`'s stale-fast-root check ([relcache.c#RelationCacheInvalidateEntry](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2975-L2985), [relcache.c#RelationFlushRelation](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2916-L2924), [relcache.c#RelationClearRelation](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2600-L2603), [nbtpage.c#_bt_getroot-stale-cache](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L380-L403)). The `pg_class` write that VACUUM or ANALYZE makes for the index sends that invalidation only when a count changed. `vac_update_relstats()` finishes the in-place update, which sends it, when something changed, and cancels the update otherwise ([vacuum.c#vac_update_relstats-dirty](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1446-L1461), [vacuum.c#vac_update_relstats-inplace](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1545-L1548), [heapam.c:6668](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6668), [heapam.c#heap_inplace_update_and_unlock-send](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6888-L6892), [heapam.c#heap_inplace_unlock](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6914-L6920)).
- **A root split sends no invalidation.** It writes index pages only: a new root page carrying the new level, and the metapage's root and fast-root fields ([nbtinsert.c#_bt_newlevel-root-level](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2507-L2513), [nbtinsert.c#_bt_newlevel-metapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2515-L2519)). So until the next such `pg_class` write, a backend that has only planned against the index can price it at a different height from one that has scanned it. [Lifecycle Of The Planner Inputs](#lifecycle-of-the-planner-inputs) lists every event that refreshes or keeps the cached height.
- **Expect plan changes on the analytical side.** Fixture A flipped to a sequential scan at 25% selectivity, and fixture L3's bloated index was dropped from a `BitmapAnd` entirely, because the planner keeps the cheapest path ([pathnode.c#add_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L419-L622), [indxpath.c#choose_bitmap_and](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1287-L1489)). See [Bloat changes plans](#bloat-changes-plans).
- **Treat `leaf_fragmentation` as a partial runtime signal only.** The manual ties physical adjacency to I/O ([maintenance.sgml#fresh-index](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1048-L1054)). The metric counts only backward sibling links ([pgstatindex.c#pgstatindex_impl-fragments](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323)), and the cost model reads neither.
- **On v17, expect `= ANY (...)` over a constant list to get cheaper on a rebuilt B-tree, not dearer on a bloated one.** The descent clamp can only lower a constant list's count, and a bloated index's higher cap keeps more of it ([selfuncs.c#estimate_array_length](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L2131-L2207), [selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042)). Only arrays in the boundary quals add descents ([selfuncs.c#btcostestimate-boundary-saop](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6950-L6961)).
- **A non-constant array can push past the old default.** It is counted as the average number of distinct elements its `STATISTIC_KIND_DECHIST` statistics record, and only one without such statistics gets the flat 10 ([selfuncs.c#estimate_array_length-statistics](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L2162-L2206)). That average can exceed 10, and a bloated index's higher cap lets it keep the larger count. [v17: index pages now cap ScalarArrayOp descents](#v17-index-pages-now-cap-scalararrayop-descents) sets each rule against the v12 branch point.
- **A bloated partial index is priced from its recorded density, not its live size.** Pages it gained since its `pg_class` row was last written reach the charge only in step with the table's growth ([plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160), [selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019)). They arrive all at once when `ANALYZE`, an exact-count `VACUUM`, or a build that finds entries rewrites the row ([analyze.c#do_analyze_rel-index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663), [vacuumlazy.c#heap_vacuum_rel-index-stats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L512-L513), [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099), [index.c#index_build-index-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3133-L3135)). An empty rebuild and a build during binary upgrade write nothing ([index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842)). Fixture Q: 113 pages charged at 331 live blocks, then 331 after `ANALYZE`. See [Step 1: Read the index size](#step-1-read-the-index-size).
- **A range predicate near either end of a B-tree can make planning read dead entries.** This moves a row estimate and costs planning time; it is not a cost term ([selfuncs.c#get_actual_variable_endpoint-limit](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6436-L6457), [selfuncs.c#get_actual_variable_endpoint-give-up](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6409-L6413)). In fixture E four plans kept a stale 10-row estimate for `id > 199990`, each marking 100 heap pages' worth of entries dead, until the fifth reached a live entry and estimated 1 row. See [Step 6: Probe the ends of a B-tree while estimating rows](#step-6-probe-the-ends-of-a-b-tree-while-estimating-rows) and [Dead entries at the end of a B-tree: the endpoint probe](#dead-entries-at-the-end-of-a-b-tree-the-endpoint-probe).

### Key Data Structures

| Structure | Field | Role |
|---|---|---|
| `IndexOptInfo` | `pages`, `tuples`, `tree_height` | The size inputs `get_relation_info()` fills for every access method ([pathnodes.h#IndexOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1120-L1128)). `genericcostestimate()` reads `pages` and `tuples`, plus the table's `rel->tuples` and the index's tablespace ([selfuncs.c:6695](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6695), [selfuncs.c#genericcostestimate-tablespace](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6734-L6737)). `btcostestimate()` reads `tree_height`; `gistcostestimate()` and `spgcostestimate()` fill it themselves |
| [`RelOptInfo`](../../../glossary.md#reloptinfo) | `pages`, `tuples`, `allvisfrac` | Parent-table estimates ([pathnodes.h#RelOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L941-L944)), filled by `estimate_rel_size()` ([plancat.c:201](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L201)). `tuples` is copied into a non-partial index's `tuples` ([plancat.c:476](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L476)) and caps a partial index's ([plancat.c:484](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L484)) |
| `PlannerInfo` | `total_table_pages` | The table-only page total used to prorate `effective_cache_size` ([pathnodes.h#total_table_pages](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L483-L484)) |
| `GenericCosts` | `numIndexPages`, `numIndexTuples`, `num_sa_scans` | The shared cost scratchpad ([selfuncs.h#GenericCosts](../../../../raw/postgres-17/src/include/utils/selfuncs.h#L108-L138)). `numIndexPages` is what every caller returns as `*indexPages`; `num_sa_scans` became an input as well in v17 (`5bf748b86b`; see [v17: index pages now cap ScalarArrayOp descents](#v17-index-pages-now-cap-scalararrayop-descents)) |
| `BTMetaPageData` | `btm_level`, `btm_fastlevel` | The true root level versus the fast-root level the planner uses ([nbtree.h#BTMetaPageData](../../../../raw/postgres-17/src/include/access/nbtree.h#L103-L119)) |
| `AttStatsSlot` | `values`, `nvalues` | The histogram bounds `ineq_histogram_selectivity()` searches ([lsyscache.h#AttStatsSlot](../../../../raw/postgres-17/src/include/utils/lsyscache.h#L46-L62)). It overwrites the first or last bound in its copy with the value the endpoint probe reads, and keeps `pg_statistic`'s bound when the probe fails ([selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136)) |
| `LVRelState` | `consider_bypass_optimization`, `do_index_vacuuming`, `do_index_cleanup` | `consider_bypass_optimization` gates the 2% bypass ([vacuumlazy.c:1900](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1900)). The other two are separate switches: the bypass clears only `do_index_vacuuming`, so `amvacuumcleanup` still runs, and the wraparound failsafe clears both ([vacuumlazy.c#LVRelState](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L148-L156), [vacuumlazy.c#lazy_vacuum-bypass-branch](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949), [vacuumlazy.c#lazy_check_wraparound_failsafe-clears](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326)) |
| `pg_class` | `relpages`, `reltuples`, `relallvisible` | The only physical-size catalog columns; no density or fragmentation column exists ([pg_class.h#relpages](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L69)) |

The three `IndexOptInfo` size fields are not the complete input set for every access method. `gincostestimate()` and `brincostestimate()` also reopen the index and read their own metapage counters ([selfuncs.c#gincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7697-L7711), [selfuncs.c#brincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8086-L8101)).

### Caller And Callee Boundary

This is the call tree from the planner's entry point to the functions that read an index's size and price it. [Logic Map](#logic-map) shows the decisions taken along it; this section shows who calls whom, and where plugins can step in.

```text
query_planner                                        planmain.c
  ├─ add_base_rels_to_query -> build_simple_rel      initsplan.c, relnode.c
  │    └─ get_relation_info                          plancat.c
  │         ├─ RelationGetNumberOfBlocks             -> smgrnblocks (non-partial index)
  │         ├─ estimate_rel_size                     -> pg_class density (partial index)
  │         ├─ _bt_getrootheight                     -> btm_fastlevel (B-tree only)
  │         └─ get_relation_info_hook                a plugin may rewrite pages, tuples, tree_height
  └─ make_one_rel                                    allpaths.c
       ├─ set_base_rel_sizes -> set_rel_size -> set_plain_rel_size
       │    └─ set_baserel_size_estimates -> clauselist_selectivity    (row estimate; endpoint probe below)
       ├─ root->total_table_pages is summed
       └─ set_base_rel_pathlists -> set_rel_pathlist
            ├─ set_plain_rel_pathlist -> create_index_paths              indxpath.c
            │    ├─ get_index_paths -> build_index_paths -> create_index_path -> cost_index
            │    │    ├─ amcostestimate  ==  btcostestimate / hash / gist / spgist / gin / brin
            │    │    │    ├─ clauselist_selectivity  (btcostestimate: boundary quals)
            │    │    │    ├─ genericcostestimate    (bt, hash, gist, spgist, contrib bloom)
            │    │    │    │    ├─ clauselist_selectivity  (all index quals)
            │    │    │    │    └─ index_pages_fetched     (repeated scans, T = index->pages)
            │    │    │    └─ index_pages_fetched    (gincostestimate: entry and data pages scaled from index->pages)
            │    │    ├─ index_pages_fetched         (heap fetches, 3 call sites, index->pages)
            │    │    └─ compute_parallel_worker     allpaths.c (numIndexPages, not index->pages)
            │    ├─ add_path -> compare_path_costs_fuzzily         pathnode.c
            │    └─ choose_bitmap_and                              indxpath.c
            │         └─ bitmap_scan_cost_est -> cost_bitmap_heap_scan -> compute_bitmap_pages
            │              └─ index_pages_fetched    (repeated bitmap scans, get_indexpath_pages)
            └─ set_rel_pathlist_hook                 a plugin may delete or modify costed paths

clauselist_selectivity -> clauselist_selectivity_ext -> clause_selectivity_ext   clausesel.c
  └─ restriction_selectivity -> the operator's oprrest, e.g. scalargtsel        plancat.c
       └─ scalarineqsel_wrapper -> scalarineqsel -> ineq_histogram_selectivity  selfuncs.c
            └─ get_actual_variable_range         first or last histogram bound; plain B-tree only
                 └─ get_actual_variable_endpoint index-only walk, SnapshotNonVacuumable, 100 heap pages
```

Call sites, in tree order: [planmain.c:170](../../../../raw/postgres-17/src/backend/optimizer/plan/planmain.c#L170), [initsplan.c:165](../../../../raw/postgres-17/src/backend/optimizer/plan/initsplan.c#L165), [relnode.c:340](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c#L340), [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500), [plancat.c#get_relation_info_hook](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L570-L576), [planmain.c:280](../../../../raw/postgres-17/src/backend/optimizer/plan/planmain.c#L280), [allpaths.c#total_table_pages](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L183-L216), [allpaths.c:322](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L322), [allpaths.c:411](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L411), [allpaths.c:581](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L581), [costsize.c:5264](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L5264), [allpaths.c:221](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L221), [allpaths.c:351](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L351), [allpaths.c:499](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L499), [allpaths.c:783](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L783), [indxpath.c:279](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L279), [indxpath.c:722](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L722), [indxpath.c:963](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L963), [pathnode.c:1024](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L1024), [costsize.c#cost_index-amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L610-L621), [selfuncs.c:7015](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7015), [selfuncs.c:7073](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7073), [selfuncs.c:6682](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6682), [selfuncs.c:6767](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6767), [selfuncs.c#gincostestimate-cache-effects](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7957-L7974), [costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747), [costsize.c:765](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L765), [indxpath.c#choose_bitmap_and-call](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L340-L343), [pathnode.c:452](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L452), [indxpath.c#bitmap_scan_cost_est](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1526-L1553), [costsize.c:1044](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1044), [costsize.c#compute_bitmap_pages-repeated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L6463-L6476), [allpaths.c#set_rel_pathlist_hook](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L532-L539).

Endpoint-probe chain: [clausesel.c#clauselist_selectivity](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L100-L108), [clausesel.c:136](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L136), [clausesel.c:183](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L183), [clausesel.c:848](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L848), [plancat.c#restriction_selectivity](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1951-L1979), [pg_operator.dat#int4gt](../../../../raw/postgres-17/src/include/catalog/pg_operator.dat#L453-L456), [selfuncs.c#scalargtsel](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1490-L1494), [selfuncs.c:1461](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1461), [selfuncs.c:690](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L690), [selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136), [selfuncs.c#get_actual_variable_range](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6157-L6331), [selfuncs.c#get_actual_variable_endpoint](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6349-L6501). The same probe is reached from `prefix_selectivity()` for `LIKE` prefixes ([like_support.c:1245](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1245), [like_support.c:1266](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1266)) and from `mergejoinscansel()` through `scalarineqsel()` ([selfuncs.c#mergejoinscansel-scalarineqsel](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L3164-L3203)). `get_variable_range()`'s own call to it is compiled out with `#ifdef NOT_USED` ([selfuncs.c#get_variable_range-not-used](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5993-L6003)).

Definitions: [costsize.c#cost_index](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L549-L821), [selfuncs.c#genericcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6626-L6828), [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951), [allpaths.c#compute_parallel_worker](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4202-L4279), [indxpath.c#choose_bitmap_and](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1287-L1489), [pathnode.c#compare_path_costs_fuzzily](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L163-L212).

`CLUSTER` reuses the same costing outside query planning. For a B-tree clustering index, `CLUSTER` asks `plan_cluster_use_sort()` whether to scan the index or to sort a sequential scan ([cluster.c#plan_cluster_use_sort-call](../../../../raw/postgres-17/src/backend/commands/cluster.c#L948-L951)). That function builds a minimal planner state, costs a whole-index `create_index_path()`, and picks the sort when it is cheaper ([planner.c#plan_cluster_use_sort](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6761-L6874), [planner.c#plan_cluster_use_sort-compare](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6861-L6873)).

A whole-index scan is charged every page. With no quals, `btcostestimate()` estimates the table's full row count ([selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019)). `CLUSTER` accepts only a non-partial index ([cluster.c#check_index_is_clusterable-partial](../../../../raw/postgres-17/src/backend/commands/cluster.c#L525-L534)), so `genericcostestimate()` turns that count into all of `index->pages`, each at the random-page cost, unless the table's row estimate is one or less ([selfuncs.c#genericcostestimate-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6786)).

So a bloated clustering index raises the index side of that comparison and pushes `CLUSTER` toward the sort. It does not decide the choice alone, because the index side also carries heap fetches priced by [correlation](../../../glossary.md#correlation) ([costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747)). Two conditions force the sort regardless of bloat: `enable_indexscan = off`, and an index missing from the planner's index list, for example one not yet past its `indcheckxmin` horizon ([planner.c#plan_cluster_use_sort-short-circuits](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6788-L6841)).

On the write side, nbtree decides how many pages exist, but it leans on two services outside it. It asks the index free space map for a recyclable page before extending the file ([nbtpage.c:903](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L903), [nbtpage.c:978](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L978)). It asks the table access method which entries simple and bottom-up deletion may remove ([nbtpage.c:1526](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1526)).

Inside nbtree, [nbtsplitloc.c#_bt_findsplitloc-fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L334) chooses where a page splits, and [nbtinsert.c#_bt_delete_or_dedup_one_page-dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2782) tries bottom-up deletion and then deduplication before splitting. [nbtpage.c#_bt_unlink_halfdead_page-deleted](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2628-L2659) marks pages deleted and can lower the fast-root level.

### Build, Generated-Header, And Extension Boundary

- **Two generated catalog headers.** `get_relation_info()` tests `RELKIND_PARTITIONED_INDEX` and `BTREE_AM_OID` ([plancat.c:471](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471), [plancat.c:488](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488)), and the endpoint probe tests the same `BTREE_AM_OID` to pick its index ([selfuncs.c:6197](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6197)). Both symbols reach that code only through headers the build generates.
  - The `RELKIND_*` letters sit in `pg_class.h`'s `EXPOSE_TO_CLIENT_CODE` block ([pg_class.h#RELKIND_INDEX-and-RELKIND_PARTITIONED_INDEX](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L162-L173)). `Catalog.pm` collects that block ([Catalog.pm#client_code](../../../../raw/postgres-17/src/backend/catalog/Catalog.pm#L61-L66), [Catalog.pm#client_code-push](../../../../raw/postgres-17/src/backend/catalog/Catalog.pm#L197-L205)), and `genbki.pl` copies it into the generated `pg_class_d.h` ([genbki.pl#client_code](../../../../raw/postgres-17/src/backend/catalog/genbki.pl#L563-L567)).
  - `BTREE_AM_OID` is an `oid_symbol` in `pg_am.dat` ([pg_am.dat:18](../../../../raw/postgres-17/src/include/catalog/pg_am.dat#L18)), which `genbki.pl` turns into a `#define` in `pg_am_d.h` ([genbki.pl#oid_symbol](../../../../raw/postgres-17/src/backend/catalog/genbki.pl#L675-L687)).
  - Renumbering either changes catalog contents. The catalog version guards such a change: `initdb` stores it in `pg_control`, and a backend built with another value refuses to run on that database, so the change needs a rebuild and a new `initdb` ([catversion.h#header-comment](../../../../raw/postgres-17/src/include/catalog/catversion.h#L6-L14)).
  - The three cost files use no generated parser header: a `grep` for `parser/gram` in `costsize.c`, `selfuncs.c` and `plancat.c` finds no include.
- **`relpages`, `reltuples` and `relallvisible` are declared by hand.** They come from the hand-written catalog header `src/include/catalog/pg_class.h`, which documents `-1` as "unknown" ([pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L65-L66)). Its `BKI_DEFAULT(-1)` on `reltuples` applies only to the rows describing bootstrap catalogs, as the header's own note says ([pg_class.h#CATALOG](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L21-L32)). A table created later gets its `-1` from `AddNewRelationTuple()` ([heap.c#AddNewRelationTuple-empty](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1006-L1009)), while a new index's row starts at `relpages = 0` and `reltuples = 0` ([index.c#index_create-pg_class](../../../../raw/postgres-17/src/backend/catalog/index.c#L1008-L1024), [relcache.c#RelationBuildLocalRelation-rd_rel](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3656-L3659)).
- **The struct the planner reads is cpp output.** `FormData_pg_class`, which `estimate_rel_size()` reads, is not generated by `genbki.pl`. It is the `CATALOG()` macro in the same hand-written header, expanded by cpp through `#define CATALOG(name,oid,oidmacro) typedef struct CppConcat(FormData_,name)` ([genbki.h:23](../../../../raw/postgres-17/src/include/catalog/genbki.h#L23)). The header's own comment says so: "cpp turns this into typedef struct FormData_pg_class" ([pg_class.h#CATALOG](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L21-L32)).
- **What `genbki.pl` does with the header.** It reads the header through `Catalog.pm` ([pg_class.h#NOTES](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L11-L16)) and emits the derived `pg_class_d.h` and the bootstrap [`.bki`](../../../glossary.md#bki) file `postgres.bki` ([genbki.pl:437](../../../../raw/postgres-17/src/backend/catalog/genbki.pl#L437), [genbki.pl:456](../../../../raw/postgres-17/src/backend/catalog/genbki.pl#L456)). `initdb` runs that file in bootstrap mode to create `template1` ([initdb.c#bootstrap_template1](../../../../raw/postgres-17/src/bin/initdb/initdb.c#L1523-L1539), [initdb.c:2770](../../../../raw/postgres-17/src/bin/initdb/initdb.c#L2770)). So changing one of these columns' declarations is an `initdb`-visible catalog change, not only a recompile.
- **Two limits are compile-time constants.** `DEFAULT_PAGE_CPU_MULTIPLIER` is a private `#define` inside `selfuncs.c` ([selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145)), not an exported symbol and not a GUC. What it multiplies is not fixed: an extension can change `cpu_operator_cost`, and it can rewrite `tree_height` through `get_relation_info_hook`, below. `VISITED_PAGES_LIMIT`, the endpoint probe's 100-page limit, is likewise a local `#define` inside `get_actual_variable_endpoint()` ([selfuncs.c:6447](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6447)), with no GUC to change it.
- **A custom index access method prices bloat through its own estimator.** `pathnodes.h` deliberately types `IndexOptInfo.amcostestimate` weakly to avoid including `amapi.h`, so `cost_index()` casts it before calling ([costsize.c#cost_index-amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L610-L621)). A custom access method therefore takes part in bloat pricing mainly through its own `amcostestimate`, and gets `tree_height = -1` unless it is a B-tree ([plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500)). `cost_index()` still feeds its `index->pages` into the heap-side cache model, as for every access method ([costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747)).
- **Four [hooks](../../../glossary.md#hook) sit on or beside this path:**
  - `get_relation_info_hook` runs at the end of `get_relation_info()`, after every `IndexOptInfo` is filled, so that a plugin can "editorialize on the info we obtained from the catalogs. Actions might include altering the assumed relation size, removing an index, or adding a hypothetical index to the indexlist" ([plancat.c#get_relation_info_hook](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L570-L576), [plancat.h#get_relation_info_hook_type](../../../../raw/postgres-17/src/include/optimizer/plancat.h#L20-L25)). A plugin there can substitute `pages`, `tuples`, `tree_height` or the `amcostestimate` pointer itself before any path is costed.
  - The cost code expects hypothetical indexes: `gincostestimate()` skips the metapage read for an index marked `hypothetical` ([selfuncs.c#gincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7697-L7711)), and the endpoint probe skips such an index rather than reading it ([selfuncs.c#get_actual_variable_range-skips](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6196-L6212)).
  - `get_relation_stats_hook` and `get_index_stats_hook` supply statistics wherever the planner looks them up. `examine_variable()` and `examine_simple_variable()` consult them for every selectivity estimate, which sets `numIndexTuples` and through it `numIndexPages` ([selfuncs.c#examine_variable-get_index_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5203-L5204), [selfuncs.c#examine_simple_variable-get_relation_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5375-L5376)). `btcostestimate()` consults them for correlation ([selfuncs.c#btcostestimate-stats-hooks](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7116-L7171)), and so does `brincostestimate()` ([selfuncs.c#brincostestimate-get_relation_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8135-L8136), [selfuncs.c#brincostestimate-get_index_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8166-L8167)). They cannot substitute a page count or a tree height, but they can move the page charge through selectivity.
  - `set_rel_pathlist_hook` runs after the core code has built and costed a relation's paths, and a plugin there "could also delete or modify paths added by the core code" ([allpaths.c#set_rel_pathlist_hook](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L532-L539)).
- **Every density and fragmentation metric on this page comes from contrib, not core:** `pgstatindex` in `pgstattuple` and `bt_metap()` in `pageinspect`. The page reads physical size through core's `pg_relation_size()`, which reports disk space usage ([pg_proc.dat#pg_relation_size](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7487-L7495)).
- **One 17.x change touched `pgstattuple`.** `036decbba2a` "pgstattuple: Improve reports generated for indexes (hash, gist, btree)" is first contained in the `Stamp 17.7.` commit, and its message says "Backpatch-through: 13". It added a `BTPageOpaqueData` size check to `pgstattuple`'s B-tree page handling ([pgstattuple.c#pgstat_btree_page-checks](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L419-L425)). Its rule that an all-zero page counts as free space was new for GiST and hash and, in the message's words, "already applied to btree". The pin contains it. It touches only `pgstattuple.c`, so it changes `pgstattuple()` output, not `pgstatindex()` density or fragmentation.

### Tests And Explicit Test Absence

- **No test asserts the bloat charge.** Every B-tree plan in the regression suites runs the height charge, but no test pins an index cost:
  - no file under `src/test` names `tree_height`, `btcostestimate` or `genericcostestimate`;
  - across all 794 expected `.out` files in the checkout, the only plan lines that print numeric costs are two lines of a partitioned `UPDATE` at `cost=0.00..0.00` ([expected/inherit.out#parted_tab-update](../../../../raw/postgres-17/src/test/regress/expected/inherit.out#L697-L698)), found by searching for `(cost=` followed by a number.
- **No test asserts the endpoint probe or its limit.** Nothing under `src/test`, `contrib` or `doc` names `get_actual_variable_range`, `get_actual_variable_endpoint`, `VISITED_PAGES_LIMIT` or `SnapshotNonVacuumable`. None of the three commits that bounded how long the probe runs added a test: `fccebe421d` and `3ca930fc39` changed the snapshot it reads under, `9c6ad5eaa9` added the 100-page limit, and each touched only source and header files.
- **Which plans reach the probe.** A plan reaches it only when a range estimate searches a histogram to its first or last bound, or the histogram has only two bounds ([selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136)). The range estimate can come from an inequality against a constant, a `LIKE` prefix ([like_support.c:1245](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1245), [like_support.c:1266](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1266)) or merge-join costing ([selfuncs.c#mergejoinscansel-scalarineqsel](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L3164-L3203)). The compared column must also lead a B-tree that is not partial or hypothetical and matches the comparison's collation and the histogram's sort operator ([selfuncs.c#get_actual_variable_range-index-choice](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6179-L6239)).
- **What no test asserts about the probe.** No test checks the value the probe returns, its fallback after 100 heap pages, or the entries it marks dead; this page's fixture E measures them.
- **Every successful in-tree `pgstatindex` call runs against an empty index**, so none asserts anything about density or fragmentation. The test creates `test (a int primary key, b int[])` with no rows and expects `avg_leaf_density` and `leaf_fragmentation` to be `NaN` through four spellings of the call ([sql/pgstattuple.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L18-L37), [expected/pgstattuple.out#NaN](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L44-L82)). A fifth call, on the empty index of an empty partition, expects `(4,0,8192,0,0,0,0,0,NaN,NaN)` ([expected/pgstattuple.out#partition-index](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L264-L268)).
- **The other `pgstatindex` calls are error paths.** GIN, hash, a partitioned table, a view, a foreign table, a partition and a sequence are each rejected as `not a btree index` ([expected/pgstattuple.out:146](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L146), [expected/pgstattuple.out:150](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L150), [expected/pgstattuple.out:171](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L171), [expected/pgstattuple.out:190](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L190), [expected/pgstattuple.out:209](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L209), [expected/pgstattuple.out:255](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L255), [expected/pgstattuple.out:292](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L292)). The `NaN` comes from the `max_avail > 0` and `leaf_pages > 0` guards ([pgstatindex.c#pgstatindex_impl-density-guards](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L372)).
- **The nbtree features that limit bloat are tested for correctness, not size.** Deduplication and deletion are covered through `src/test/regress/sql/btree_index.sql` and [`contrib/amcheck`](../../../glossary.md#amcheck), neither of which asserts page counts. `btree_index.sql` does build a fast root by deleting most of an 80,000-row index and vacuuming, then splits it, but as a correctness and WAL-coverage test ([btree_index.sql#multilevel-page-deletion](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L252-L270)).
- **So every measurement on this page comes from this page's own script** on an isolated exact-pin server, not from an in-tree test.

### Follow-Up: When A GIN Index Is Discarded And A B-Tree Is Used Instead

#### Short answer

PostgreSQL 17 drops a GIN index from a plan at one of four checkpoints, and only the last one is about cost:

1. **Usable?** The index must be valid, visible to the planning transaction and, if it is a partial index, implied by the query ([plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281), [indxpath.c#create_index_paths-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L260-L266)).
2. **Operator?** The clause's operator must belong to the index's operator family ([indxpath.c#match_opclause_to_indexcol-op_in_opfamily](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2433-L2459)).
3. **Plan shape?** The plan must not need a plain index scan, sorted output, an index-only scan or an `IS NULL` search, because GIN supports none of them ([ginutil.c#ginhandler](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L36-L89)).
4. **Cost?** The GIN path, or the plan built on it, must be estimated cheaper than the alternatives ([indxpath.c#choose_bitmap_and](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1287-L1489), [pathnode.c#add_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L419-L622)).

On an ordinary comparison against a column that a B-tree also indexes, the fourth checkpoint usually favors the B-tree, even when the GIN index is smaller. The reason is how each is priced. `gincostestimate()` charges a random page read for every page it expects to touch, every page of its pending list included ([selfuncs.c#gincostestimate-pending](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7882-L7886), [selfuncs.c#gincostestimate-random-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7976-L7980)). A B-tree is charged only a pro-rata share of its pages ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)). On one table with identical statistics, `n = 42` cost `12.97` through a 279-block GIN index and `4.52` through a 280-block B-tree; see [Same table, same statistics, both indexes](#same-table-same-statistics-both-indexes).

#### Decision tree

The four checkpoints run in this order while the planner builds paths for one table. Each branch says what the next stage receives.

```text
A clause on a column that GIN index G and a B-tree both cover
│
├─ Gate 0  Is G usable in this transaction?                                [G0]
│   ├─ indisvalid is false ─────────────────────────> G skipped, no IndexOptInfo
│   ├─ indcheckxmin set, and the pg_index row's
│   │  xmin not older than TransactionXmin ─────────> G skipped, plan marked transient
│   └─ partial, and the query does not imply
│      its predicate ───────────────────────────────> no path over G
│                                                     (an OR arm may still use G)
├─ Gate 1  Is the clause's operator in G's operator family?                [G1]
│   ├─ yes, or a support function rewrites it ──────> an IndexClause on G
│   └─ no ──────────────────────────────────────────> no Index Cond on G; a partial G
│                                                     whose predicate is proven still
│                                                     gets a clauseless path
├─ Gate 2  Does the plan need a shape GIN lacks?                           [G2]
│   ├─ plain Index Scan (amgettuple is NULL) ───────> G offers bitmap paths only
│   ├─ ORDER BY from the index (amcanorder) ────────> no pathkeys from G
│   ├─ Index Only Scan (amcanreturn is NULL) ───────> no index-only path on G
│   ├─ IS NULL (amsearchnulls) ─────────────────────> the clause never matches G
│   └─ parallel index path (amcanparallel) ─────────> none; a Parallel Bitmap Heap
│                                                     Scan above G is still possible
└─ Gate 3  Is G's path cheaper?                                            [G3]
    ├─ G and the B-tree serve the same clauses ─────> choose_bitmap_and keeps the lower
    │                                                 index cost + 0.1 x cpu_operator_cost
    │                                                 x rows; a tie keeps the first
    ├─ they serve different clauses ────────────────> G joins an AND group only if the
    │                                                 whole bitmap heap scan gets cheaper
    └─ add_path then compares the surviving bitmap heap path with every other path
```

Key to the diagram:

- [G0] [plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281), [indxpath.c#create_index_paths-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L260-L266)
- [G1] [indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2203-L2269), [indxpath.c#match_opclause_to_indexcol-op_in_opfamily](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2433-L2459), [indxpath.c#get_index_clause_from_support](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2557-L2615), [indxpath.c#build_index_paths-generate](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L954-L962)
- [G2] [ginutil.c#ginhandler](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L36-L89), [plancat.c#get_relation_info-am-flags](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L317-L335), [indxpath.c#get_index_paths-submit](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L740-L751), [indxpath.c#build_index_paths-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L975-L1002), [allpaths.c#create_partial_bitmap_paths](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4162-L4185)
- [G3] [indxpath.c#choose_bitmap_and-cheapest-of-group](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1353-L1399), [costsize.c#cost_bitmap_tree_node-indexpath](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1114-L1128), [indxpath.c#choose_bitmap_and-accept-reject](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1418-L1489), [pathnode.c#add_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L419-L622)

The same four gates, with where each runs and what reverses it:

| Gate | Where it runs | What makes GIN lose | Recovery |
|---|---|---|---|
| 0. Usability, not GIN-specific | `get_relation_info()`, `create_index_paths()` ([plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281), [indxpath.c#create_index_paths-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L260-L266)) | The index is [invalid](../../../glossary.md#invalid-index), not yet usable under [`indcheckxmin`](../../../glossary.md#indcheckxmin), or partial with a predicate the query does not imply | Rebuild an invalid index; wait for older transactions to end; write a `WHERE` clause that implies the predicate. See [Gate 0](#gate-0-the-index-is-not-usable-for-this-query) |
| 1. Clause matching | `match_clause_to_indexcol()` ([indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2203-L2269)) | The operator is not in the GIN operator family, and no [planner support function](../../../glossary.md#planner-support-function) rewrites it ([indxpath.c#match_opclause_to_indexcol-op_in_opfamily](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2433-L2459)). This rejects the clause, not necessarily the index | Use a matching operator, or add the comparison operators with [`contrib/btree_gin`](../../../glossary.md#btree_gin-and-btree_gist) ([btree_gin--1.0.sql#int4_ops](../../../../raw/postgres-17/contrib/btree_gin/btree_gin--1.0.sql#L56-L69)) |
| 2. Plan shape | `build_index_paths()`, `get_index_paths()` ([indxpath.c#get_index_paths](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L709-L767)) | The plan needs a plain, ordered, index-only, `IS NULL` or parallel index scan, and GIN supports none of them ([ginutil.c#ginhandler](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L36-L89)) | None: these are access-method properties, not costs. See [Gate 2](#gate-2-the-required-plan-shape-rules-gin-out) |
| 3. Cost | `gincostestimate()` against `btcostestimate()`, then `choose_bitmap_and()` and `add_path()` ([costsize.c#cost_index-amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L610-L621), [indxpath.c#choose_bitmap_and](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1287-L1489)) | The GIN path, or the plan that uses it, is estimated dearer. Every pending page is charged in full on a single scan ([selfuncs.c#gincostestimate-pending](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7882-L7886)) | Drain the pending list and refresh the metapage counters. See [Gate 3](#gate-3-cost-and-why-gin-loses-on-the-same-column) and [Lifecycle of the pending list and metapage counters](#lifecycle-of-the-pending-list-and-metapage-counters) |

#### Gate 0: the index is not usable for this query

Three checks run before any clause is matched. None of them is GIN-specific, and each can drop a GIN index while an older B-tree on the same table stays usable.

**Invalid index.** `get_relation_info()` leaves out every index whose `pg_index.indisvalid` is false, so the planner never builds an `IndexOptInfo` for it ([plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281)). A failed `CREATE INDEX CONCURRENTLY` leaves such an index behind. The manual recommends dropping and rebuilding it, or running `REINDEX INDEX CONCURRENTLY` ([ref/create_index.sgml#invalid-index](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L645-L667)).

**Index not yet usable by this transaction.** `get_relation_info()` also skips an index whose `indcheckxmin` flag is set while the `xmin` of its [`pg_index`](../../../glossary.md#pg_index) row does not precede the transaction's [`TransactionXmin`](../../../glossary.md#transactionxmin). It then marks the plan [transient](../../../glossary.md#transient-plan) ([plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281)). A cached transient plan records the `TransactionXmin` it was built under, and a later use under a different one plans again ([plancache.c#BuildCachedPlan-transient](../../../../raw/postgres-17/src/backend/utils/cache/plancache.c#L1022-L1033), [plancache.c#CheckCachedPlan-transient](../../../../raw/postgres-17/src/backend/utils/cache/plancache.c#L866-L873)).

The `xmin` of that `pg_index` row is the index's usability horizon. For a new index it is the transaction ID of the `CREATE INDEX` transaction, and the creating transaction cannot use a flagged index while it holds old snapshots ([README.HOT#indcheckxmin](../../../../raw/postgres-17/src/backend/access/heap/README.HOT#L341-L353)). Only some builds set the flag, depending on whether they met broken HOT chains:

| Build | `indcheckxmin` afterwards | Evidence |
|---|---|---|
| `CREATE INDEX`, not concurrent, that met broken HOT chains | set | [index.c#index_build-indcheckxmin](../../../../raw/postgres-17/src/backend/catalog/index.c#L3099-L3101) |
| `CREATE INDEX CONCURRENTLY` | never set by the build | [index.c#index_build-indcheckxmin](../../../../raw/postgres-17/src/backend/catalog/index.c#L3099-L3101) |
| `REINDEX` that met no broken HOT chains | cleared | [index.c#reindex_index-indcheckxmin](../../../../raw/postgres-17/src/backend/catalog/index.c#L3800-L3850) |
| `REINDEX` of a valid index that met broken HOT chains | left as it was | [index.c#reindex_index-indcheckxmin](../../../../raw/postgres-17/src/backend/catalog/index.c#L3800-L3850) |
| `REINDEX` of an invalid, not-ready or dead index that met broken HOT chains | set | [index.c#reindex_index-indcheckxmin](../../../../raw/postgres-17/src/backend/catalog/index.c#L3800-L3850) |

**Partial index whose predicate is not proven.** `check_index_predicates()` sets `predOK` only when the relation's restriction clauses imply the index predicate, together with join clauses that can move to the relation and [equivalence](../../../glossary.md#equivalence-class)-derived join clauses ([indxpath.c#check_index_predicates-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L3272-L3350)). `create_index_paths()` skips a partial index without `predOK` before it matches any clause. Its comment leaves such an index to `generate_bitmap_or_paths()`, which may still use it for one arm of an `OR` ([indxpath.c#create_index_paths-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L260-L266)).

#### Gate 1: the clause never matches the GIN index

`create_index_paths()` matches each index's restriction clauses before any cost model runs ([indxpath.c#create_index_paths](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L234-L413)). For an operator clause, `match_opclause_to_indexcol()` accepts the clause only when the index column's collation matches and `op_in_opfamily()` finds the operator in the column's operator family. Otherwise it falls through to `get_index_clause_from_support()`, which lets a planner support function supply a rewritten clause ([indxpath.c#match_opclause_to_indexcol-op_in_opfamily](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2433-L2459), [indxpath.c#get_index_clause_from_support](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2557-L2615)).

The core GIN operator families are bootstrap catalog data, and none of them lists `<`, `<=`, `>=` or `>`:

| GIN opfamily | Operators declared | Evidence |
|---|---|---|
| `gin/array_ops` | `&&`, `@>`, `<@`, `=` (whole-array equality, GIN strategy 4) | [pg_amop.dat#gin-array_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1232-L1244) |
| `gin/tsvector_ops` | `@@`, `@@@` | [pg_amop.dat#gin-tsvector_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1290-L1296) |
| `gin/jsonb_ops` | `@>`, `?`, `?|`, `?&`, `@?`, `@@` | [pg_amop.dat#gin-jsonb_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1593-L1611) |
| `gin/jsonb_path_ops` | `@>`, `@?`, `@@` | [pg_amop.dat#gin-jsonb_path_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1613-L1622) |

So `WHERE jb = '{"k": 42}'::jsonb` cannot use a `jsonb_ops` GIN index at all, because `jsonb`'s `=` is only in the B-tree and hash families ([pg_amop.dat#btree-hash-jsonb_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1571-L1591)). The manual states the general rule: "each column must be used with operators appropriate to the index type; clauses that involve other operators will not be considered" ([indices.sgml#other-operators](../../../../raw/postgres-17/doc/src/sgml/indices.sgml#L505-L508)). `contrib/pg_trgm` says the same about its own classes: "Inequality operators are not supported. Note that those indexes may not be as efficient as regular B-tree indexes for equality operator." ([pgtrgm.sgml#index-support](../../../../raw/postgres-17/doc/src/sgml/pgtrgm.sgml#L413-L425)).

`contrib/btree_gin` closes gate 1 on purpose. Each of its operator classes declares exactly strategies 1 through 5, that is `<`, `<=`, `=`, `>=` and `>`. For `int4`, its GIN support function 1 is the type's B-tree comparison function ([btree_gin--1.0.sql#int4_ops](../../../../raw/postgres-17/contrib/btree_gin/btree_gin--1.0.sql#L56-L69)). Its documentation draws the conclusion this follow-up asks about: "In general, these operator classes will not outperform the equivalent standard B-tree index methods, and they lack one major feature of the standard B-tree code: the ability to enforce uniqueness." ([btree-gin.sgml#caveats](../../../../raw/postgres-17/doc/src/sgml/btree-gin.sgml#L24-L33)).

**A rejected clause is not a rejected index.** Gate 1 decides whether one clause can become an `Index Cond`. It does not decide whether any path over the index exists. `build_index_paths()` builds a path when any of four things holds: there is an index clause, the index's order is useful, an index-only scan is possible, or the index has a useful predicate ([indxpath.c#build_index_paths-generate](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L954-L962)).

The only clause-related hard stop is on the first column of an access method with `amoptionalkey = false`, and GIN sets `amoptionalkey = true` ([indxpath.c#build_index_paths-amoptionalkey](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L887-L897), [ginutil.c:49](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L49)). Two other stops do not depend on clause matching. `build_index_paths()` returns no path when the access method lacks the requested scan type, which [Gate 2](#gate-2-the-required-plan-shape-rules-gin-out) covers ([indxpath.c#build_index_paths-scantype](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L826-L842)). An unproven partial predicate stops the index earlier, at [Gate 0](#gate-0-the-index-is-not-usable-for-this-query).

So a partial GIN index whose predicate the query implies still gets a clauseless path, even when no query operator is in any of its operator families. `gincostestimate()` prices that path as a whole-index scan, and [The keyless full-index path on a partial GIN index](#the-keyless-full-index-path-on-a-partial-gin-index) measures it. Read gate 1 as "this clause will not be an `Index Cond`". The index itself disappears only when no other reason to build a path survives.

One case looks like a gate-1 rejection but is not: a boolean column. Constant folding turns `WHERE i = true` into a bare boolean `Var`, so no `OpExpr` survives ([clauses.c#simplify_boolean_equality](../../../../raw/postgres-17/src/backend/optimizer/util/clauses.c#L3990-L4045)). v17 still matches it. `IsBooleanOpfamily()` accepts any operator family that contains `BooleanEqualOperator`, and checks a family that is not built in through a [catcache](../../../glossary.md#syscache) lookup ([indxpath.c#IsBooleanOpfamily](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2271-L2286), [pg_opfamily.h#IsBuiltinBooleanOpfamily](../../../../raw/postgres-17/src/include/catalog/pg_opfamily.h#L59-L65)). `match_boolean_index_clause()` then rewrites the bare `Var` back into `indexkey = true` ([indxpath.c#match_boolean_index_clause](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2288-L2384)).

The upstream expected output shows the resulting `Index Cond: (i = true)` on a `btree_gin` bool index ([bool.out#gin-bool-equality](../../../../raw/postgres-17/contrib/btree_gin/expected/bool.out#L89-L98)). The [Boolean column](#boolean-column) measurement reproduces it for `i`, `i = true` and `i IS TRUE` alike.

#### Gate 2: the required plan shape rules GIN out

`get_relation_info()` copies a fixed set of access-method capability flags into each `IndexOptInfo`. It derives `amhasgettuple` from whether the access method supplies `amgettuple`, and `amhasgetbitmap` from `amgetbitmap` together with the table access method's `scan_bitmap_next_block` ([plancat.c#get_relation_info-am-flags](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L317-L335)). GIN and B-tree differ on almost every flag:

| `IndexAmRoutine` field | GIN | B-tree | Planner consequence |
|---|---|---|---|
| `amgettuple` | `NULL` ([ginutil.c:79](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L79)) | `btgettuple` ([nbtree.c:143](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L143)) | `get_index_paths()` hands a path to `add_path()` only when `index->amhasgettuple`, so a GIN path can only become a bitmap input ([indxpath.c#get_index_paths-submit](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L740-L751)). `build_index_paths()` would also refuse `ST_INDEXSCAN`, though no caller in the pinned tree asks for it ([indxpath.c#build_index_paths-scantype](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L826-L842)) |
| `amcanorder` / `amcanorderbyop` | `false` / `false` ([ginutil.c#ginhandler-amcanorder](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L44-L45)) | `true` / `false` ([nbtree.c#bthandler-amcanorder](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L108-L109)) | `get_relation_info()` fills `sortopfamily` only for a B-tree or another `amcanorder` access method ([plancat.c#get_relation_info-sortopfamily](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L340-L422)). So `index_is_ordered` is false for GIN, and `useful_pathkeys` stays `NIL`: GIN offers the planner no [pathkeys](../../../glossary.md#pathkey), the sort orders a path can deliver ([indxpath.c#build_index_paths-pathkeys](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L905-L944)) |
| `amcanreturn` | `NULL` ([ginutil.c:70](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L70)) | `btcanreturn` ([nbtree.c:134](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L134)) | `index_can_return()` returns false ([indexam.c#index_can_return](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L780-L797)), so every `canreturn[i]` is false ([plancat.c#get_relation_info-canreturn](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L296-L301)). `check_index_only()` then fails for any query that needs a column, and passes trivially for one that needs none, such as a bare `count(*)` ([indxpath.c#check_index_only](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1730-L1800)) |
| `amsearchnulls` | `false` ([ginutil.c:51](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L51)) | `true` ([nbtree.c:115](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L115)) | `match_clause_to_indexcol()` accepts a `NullTest` only when `index->amsearchnulls`, so `IS NULL` never reaches GIN ([indxpath.c#match_clause_to_indexcol-nulltest](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2251-L2266)) |
| `amsearcharray` | `false` ([ginutil.c:50](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L50)) | `true` ([nbtree.c:114](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L114)) | A `ScalarArrayOpExpr` is left out of plain paths and offered again only as a bitmap path ([indxpath.c#build_index_paths-saop](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L862-L885), [indxpath.c#get_index_paths-nonnative-saop](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L753-L766)). `counts.arrayScans` then multiplies the GIN estimate ([selfuncs.c#gincost_scalararrayopexpr](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7550-L7660)) |
| `amcanparallel` | `false` ([ginutil.c:55](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L55)) | `true` ([nbtree.c:119](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L119)) | No partial path over a GIN index: `build_index_paths()` builds parallel index paths only when `index->amcanparallel` ([indxpath.c#build_index_paths-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L975-L1002)). A parallel bitmap heap scan above GIN is still possible, as the next paragraphs show |

**GIN is not shut out of parallel plans.** What `amcanparallel = false` removes is a partial *index* path. `create_index_paths()` hands whatever `choose_bitmap_and()` produced to `create_partial_bitmap_paths()` ([indxpath.c:347](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L347)). That function sizes workers from the heap pages alone, passing `index_pages = -1` to `compute_parallel_worker()`, and adds a `Parallel Bitmap Heap Scan` over the unchanged bitmap ([allpaths.c#create_partial_bitmap_paths](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4162-L4185)).

The bitmap is built once and shared. Whichever participating process reaches it first builds it, and the executor calls that process the leader for the parallel bitmap scan ([nodeBitmapHeapscan.c#BitmapShouldInitializeSharedState](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L774-L806), [nodeBitmapHeapscan.c#BitmapHeapNext-shared-bitmap](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L130-L141)).

Every participating process then attaches to one shared iterator, and `tbm_shared_iterate()` hands out the next heap page under a lock on each call. The heap fetches are therefore divided among the processes ([nodeBitmapHeapscan.c#shared-iterator](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L143-L170), [nodeBitmapHeapscan.c:241](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L241), [tidbitmap.c#tbm_shared_iterate](../../../../raw/postgres-17/src/backend/nodes/tidbitmap.c#L1044-L1136)). So a GIN index cannot drive parallel query, and it does not prevent it either.

Three consequences follow, and no setting reverses them:

- **No plain index scan.** The access-method documentation explains why: `amgetbitmap` returns a bitmap that "doesn't have any specific ordering", "Ordering operators will never be supplied for such a scan", and "there is no provision for index-only scans with `amgetbitmap`, since there is no way to return the contents of index tuples" ([indexam.sgml#amgetbitmap](../../../../raw/postgres-17/doc/src/sgml/indexam.sgml#L991-L1010)). Two upstream test comments say the same: "GIN currently supports only bitmap scans, not plain indexscans" and "GIN only supports bitmapscan, so no need to test plain indexscan" ([create_index.sql#gin-bitmap-only](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L264-L268), [tsearch.sql#gin-bitmap-only](../../../../raw/postgres-17/src/test/regress/sql/tsearch.sql#L225-L230)).
- **No sorted output.** "Of the index types currently supported by PostgreSQL, only B-tree can produce sorted output — the other index types return matching rows in an unspecified, implementation-dependent order." ([indices.sgml#ordering](../../../../raw/postgres-17/doc/src/sgml/indices.sgml#L530-L538)). Even a bitmap scan built from a B-tree loses the order, because the bitmap is laid out in physical order ([indices.sgml#bitmap-scans](../../../../raw/postgres-17/doc/src/sgml/indices.sgml#L643-L656)).
- **No index-only scan.** "As a counterexample, GIN indexes cannot support index-only scans because each index entry typically holds only part of the original data value" ([indices.sgml#index-only-scans](../../../../raw/postgres-17/doc/src/sgml/indices.sgml#L1125-L1136)), which matches the `amcanreturn` contract.

The upstream `amutils` regression test asserts this property matrix for `gin` against `btree`. For GIN, `orderable`, `returnable`, `search_array` and `search_nulls` are all `f`, `bitmap_scan` is `t` and `index_scan` is `f`. `can_order`, `can_unique`, `can_exclude` and `can_include` are all `f` ([amutils.out#column-properties](../../../../raw/postgres-17/src/test/regress/expected/amutils.out#L96-L108), [amutils.out#index-properties](../../../../raw/postgres-17/src/test/regress/expected/amutils.out#L122-L129), [amutils.out#am-properties](../../../../raw/postgres-17/src/test/regress/expected/amutils.out#L152-L157)).

#### Gate 3: cost, and why GIN loses on the same column

`cost_index()` calls each index's `amcostestimate` through the `IndexOptInfo`, so GIN and B-tree paths for the same clause are priced by different code ([costsize.c#cost_index-amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L610-L621)). The GIN recipe below uses these terms:

| Term | Meaning | Source |
|---|---|---|
| `numPages` | the GIN index's live block count, `index->pages` | [selfuncs.c:7674](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7674) |
| `numTuples` | `index->tuples`, which for a non-partial index is the table's row estimate | [selfuncs.c:7675](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7675) |
| `numPendingPages` | pending-list pages, read live from the metapage | [selfuncs.c#gincostestimate-trust](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7727) |
| `numEntryPages`, `numDataPages`, `numEntries` | entry-tree pages, posting-tree pages and distinct keys, from the counters the last build or `VACUUM` wrote, scaled or invented as [Stale GIN metapage statistics](#stale-gin-metapage-statistics) describes | [selfuncs.c#gincostestimate-scale-or-invent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7767) |
| `searchEntries`, `exactEntries`, `partialEntries`, `arrayScans` | per-query counts derived from the index quals: keys searched, exact keys, partial-match keys and array scans | [selfuncs.c#GinQualCounts](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7370-L7378) |
| `outer_scans` | the loop count of a nested-loop inner scan, 1 otherwise | [selfuncs.c:7880](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7880) |
| `indexSelectivity` | the fraction of the table's rows the quals, and a partial index's predicate, select | [selfuncs.c#gincostestimate-selectivity](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7778-L7784) |

`gincostestimate()` builds its estimate in eight steps:

1. Read the metapage counters with `ginGetStats()`. Only `nPendingPages` is current; the rest date from the last build or `VACUUM` ([selfuncs.c#gincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7697-L7711), [selfuncs.c#gincostestimate-trust](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7727), [ginutil.c#ginGetStats](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L616-L642)). Scale or invent the others as [Stale GIN metapage statistics](#stale-gin-metapage-statistics) describes.
2. Seed the startup page count with the whole pending list: `entryPagesFetched = numPendingPages` ([selfuncs.c#gincostestimate-pending](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7882-L7886)).
3. Add `ceil(searchEntries * rint(pow(numEntryPages, 0.15)))` entry pages, plus a proportional share of entry and data pages for partial-match keys ([selfuncs.c#gincostestimate-entrypages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7888-L7914)).
4. Charge `ceil(log2(numEntries))` comparisons at `cpu_operator_cost` per search entry for the entry-tree descent ([selfuncs.c#gincostestimate-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7919-L7935)).
5. Charge `DEFAULT_PAGE_CPU_MULTIPLIER * cpu_operator_cost`, that is `50 * cpu_operator_cost`, for every entry page and every partial-match data page ([selfuncs.c#gincostestimate-page-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7937-L7955), [selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145)). Step 4 and the entry-page part of step 5 add to both the startup and the total estimate, and step 8 adds the startup estimate to the total again, so at `arrayScans = 1` each is counted twice in the total. The partial-match data-page charge goes to the startup estimate only, plus `arrayScans - 1` copies in the total, so it counts once per array scan.
6. Charge the pages from steps 2 and 3 at `random_page_cost`, as startup cost, "because logically-close pages could be far apart on disk". When `outer_scans > 1` or `arrayScans > 1`, first multiply both page counts by `outer_scans * arrayScans`, cap each with `index_pages_fetched()` over `numEntryPages` or `numDataPages`, and divide by `outer_scans` ([selfuncs.c#gincostestimate-cache-effects](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7957-L7974), [selfuncs.c#gincostestimate-random-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7976-L7980)).
7. Count the scan-time data pages as the exact-match entries' share of the data pages, `ceil(numDataPages * exactEntries / numEntries)`, raised to a selectivity floor of `ceil(indexSelectivity * (numTuples / (BLCKSZ / 3)))` ([selfuncs.c#gincostestimate-datapages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7982-L8006)). Add one more `50 * cpu_operator_cost` per search entry to the startup cost, and one per scan-time data page to the total ([selfuncs.c#gincostestimate-search-entry-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8008-L8015)). On a repeated scan these data pages also go through `index_pages_fetched()` over `numDataPages` before they are charged ([selfuncs.c#gincostestimate-datapages-cache](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8017-L8025)).
8. Add the startup estimate, and the scan-time data pages at `random_page_cost`, to the total ([selfuncs.c#gincostestimate-total](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8027-L8029)). Then add `qual_op_cost` once per search entry and array scan, and `cpu_index_tuple_cost` per estimated matching tuple ([selfuncs.c#gincostestimate-qualcost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8031-L8048)). There is no tree-height charge and no ordering support ([selfuncs.c#gincostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7662-L8050)).

`btcostestimate()` instead calls `genericcostestimate()`, which prorates `numIndexPages = ceil(numIndexTuples * index->pages / index->tuples)` ([selfuncs.c#btcostestimate-genericcost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7067-L7073), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)). `btcostestimate()` then adds a `ceil(log2(index->tuples))` comparison charge and the `(tree_height + 1) * 50 * cpu_operator_cost` height charge ([selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091), [selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)); see [Step 3: Charge the B-tree height](#step-3-charge-the-b-tree-height).

That difference decides a selective lookup. On the lookup worked through below, GIN pays `random_page_cost` for two entry pages and one data page, plus page CPU charges that count twice. The B-tree pays for one pro-rata page and a small height charge. So the GIN estimate comes out higher on every comparison predicate measured below, even though the GIN index is physically smaller. Nothing in the source makes that a guarantee, and [Where GIN still wins](#where-gin-still-wins) measures a case where the GIN path is the cheaper one.

**Worked example: `n = 42` on fixture S.** The inputs are values the script records. The GIN index has 279 blocks, `numEntryPages` 278, `numEntries` 10,000 and `nDataPages` 0, and nothing pending. The B-tree has 280 blocks and `fastlevel` 1. The table holds 300,000 rows, and 30 of them match, so `indexSelectivity` is 0.0001. Computed by hand from the pinned code, both estimates match `EXPLAIN` to the cent:

| GIN term | Calculation | Cost |
|---|---|---:|
| entry pages (step 3) | `ceil(1 * rint(278^0.15)) = ceil(1 * 2) = 2` | |
| data pages (step 7) | per-entry estimate `ceil(0 * 1 / 10000) = 0`; floor `ceil(0.0001 * (300000 / 2730)) = 1` | |
| page I/O (steps 6 and 8) | `(2 + 1) * 4.0` | `12.00` |
| descent and entry-page CPU, each counted twice (steps 4, 5 and 8) | `(ceil(log2(10000)) * 0.0025 + 2 * 50 * 0.0025) * 2 = (0.035 + 0.25) * 2` | `0.57` |
| search-entry and data-page CPU (step 7) | `50 * 0.0025 + 1 * 50 * 0.0025` | `0.25` |
| qual and tuple CPU (step 8) | `1 * 0.0025 + 30 * 0.005` | `0.1525` |
| **total** | | **`12.9725`**, printed `12.97` |

| B-tree term | Calculation | Cost |
|---|---|---:|
| page I/O | `ceil(30 * 280 / 300000) = 1` page, `* 4.0` | `4.00` |
| descent comparisons | `ceil(log2(300000)) * 0.0025 = 19 * 0.0025` | `0.0475` |
| height charge | `(1 + 1) * 50 * 0.0025` | `0.25` |
| tuple CPU | `30 * (0.005 + 0.0025)` | `0.225` |
| **total** | | **`4.5225`**, printed `4.52` |

The `2730` is `BLCKSZ / 3` in integer arithmetic at the 8 kB block size the run recorded ([selfuncs.c#gincostestimate-datapages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7982-L8006)).

**How gate 3 drops the GIN index.** Computing the two estimates does not yet drop anything. A GIN path is only ever a bitmap input, so `choose_bitmap_and()` usually decides, and what it compares depends on which clauses each index serves:

| Clauses served | What `choose_bitmap_and()` compares | Consequence |
|---|---|---|
| The same clause set, as for one predicate on one column | Each path's `cost_bitmap_tree_node()` figure: the index's own `amcostestimate` total, which `cost_index()` saves in the path ([costsize.c:628](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L628)), plus `0.1 * cpu_operator_cost` per row ([indxpath.c#choose_bitmap_and-cheapest-of-group](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1353-L1399), [costsize.c#cost_bitmap_tree_node-indexpath](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1114-L1128)). The row count is the relation's output estimate, `baserel->rows`, the same for every unparameterized path on the table ([costsize.c#cost_index-rows](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L589-L604)) | The lower index estimate wins, and a tie keeps the path met first. Winning does not win the plan, because the B-tree's plain index paths still compete in `add_path()` ([indxpath.c#get_index_paths-submit](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L740-L751)) |
| Different clauses | Whole bitmap-heap-scan estimates, with and without the GIN index in the AND group ([indxpath.c#choose_bitmap_and-accept-reject](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1418-L1489), [indxpath.c#bitmap_scan_cost_est](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1526-L1553), [indxpath.c#bitmap_and_cost_est](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1560-L1571)) | GIN joins the group only if the whole scan gets cheaper, so its own estimate alone does not decide. Fixture D keeps a GIN index estimated at `3141.12` in a `BitmapAnd` for that reason |

The row count in the first comparison is not the `rows` figure `EXPLAIN` prints on a `Bitmap Index Scan` node. That figure is `clamp_row_est(indexselectivity * tuples)`, the index's own selectivity times the table's estimated rows ([createplan.c#create_bitmap_subplan-indexpath](../../../../raw/postgres-17/src/backend/optimizer/plan/createplan.c#L3480-L3485)).

The surviving bitmap heap path then competes with every other path for the relation. `add_path()` compares candidates with `compare_path_costs_fuzzily()` at `STD_FUZZ_FACTOR = 1.01`, and refuses or removes a dominated path ([pathnode.c#add_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L419-L622), [pathnode.c#STD_FUZZ_FACTOR](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L42-L47)). A GIN index that `choose_bitmap_and()` leaves out is gone from the plan, and its clause reappears as a `Filter` above the surviving B-tree bitmap scan.

#### A GIN index with a large pending list loses to a B-tree

This case connects the follow-up back to this page's subject. A large `fastupdate` pending list is charged to the planner in full and at once, because `nPendingPages` is the one metapage counter `gincostestimate()` treats as current ([selfuncs.c#gincostestimate-trust](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7727), [ginutil.c#ginGetStats](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L616-L642)).

The pending list is insert work that GIN has postponed, not wasted space ([gin.sgml#fast-update-flush](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L508-L515)). It counts as bloat here only in this page's broad sense of extra pages the planner is charged for; see [Types Of Bloated Indexes](#types-of-bloated-indexes). The manual states its runtime cost: "searches must scan the list of pending entries in addition to searching the regular index, and so a large list of pending entries will slow searches significantly" ([gin.sgml#fast-update-searches](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L521-L529)).

Measured at the pin on fixture D: a `docs` table with a `tsvector` GIN index (`fastupdate = on`) and a B-tree index on an `int` category column, queried with `tsv @@ to_tsquery('simple','zebracorn') AND cat = 7`. The table starts at 200,000 vacuumed rows and takes two further 100,000-row inserts. The inserting sessions raise `gin_pending_list_limit`, a `PGC_USERSET` setting ([guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585)), so no insert asks for a cleanup.

The two clauses must be able to hold together, or every cost below prices a plan for a predicate that matches nothing. `cat` is `i % 20`, and the rare lexeme lands on every 4,999th row. Because 4,999 is prime, it shares no factor with 20, so the lexeme rows walk through all twenty values of `i % 20` in turn. At 400,000 rows that makes 80 lexeme rows, 20,000 rows with `cat = 7`, and 4 rows with both.

The planner's estimates match those counts, which is agreement rather than proof. In the final, vacuumed 400,000-row state (the last row of the table below) it estimates 80, 19,999 and 4; in the first, 200,000-row state it estimated 40, 10,000 and 2. It estimates the conjunction by multiplying the two per-clause selectivities, which assumes independence, and this fixture is built to satisfy that assumption; [Bloat changes plans](#bloat-changes-plans) gives the same caveat.

The `cat = 7` estimate is one row short because the plain `VACUUM` extrapolated `reltuples` from the pages it scanned and left it at 399,985, which a selectivity of `0.05` turns into 19,999 ([vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1299-L1366)). Building the multicolumn index in [Where GIN still wins](#where-gin-still-wins) rewrote `reltuples` to exactly 400,000. `ginbuild()` returns the heap tuple count of its build scan, and `index_build()` writes that count into the table's `pg_class` row ([gininsert.c#ginbuild-scan](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L382-L384), [gininsert.c:424](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L424), [index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135), [index.c#index_update_stats-write](../../../../raw/postgres-17/src/backend/catalog/index.c#L2835-L2923)). The same clause is then estimated at 20,000.

| State | Pending pages (`pgstatginindex`) | GIN blocks | GIN scan cost for `tsv @@ …` alone | Two-clause plan using the GIN index | Same query with the GIN index hidden | Plan chosen |
|---|---:|---:|---:|---:|---:|---|
| vacuumed, 200,000 rows | 0 | 302 | `13.01` | `132.40` | `2323.30` | `BitmapAnd` of GIN and B-tree |
| first insert, 300,000 rows | 736 | 1,038 | `3141.12` | `3321.93` | `3486.80` | `BitmapAnd` still, at 25 times the vacuumed price |
| second insert, 400,000 rows | 1,471 | 1,773 | `6264.98` | not chosen | `4646.42` | B-tree bitmap scan only; `tsv @@ …` demoted to `Filter` |
| after `gin_clean_pending_list()` | 0 | 2,073 | `17.49` | `255.85` | `4646.42` | `BitmapAnd` of GIN and B-tree |
| after `VACUUM` | 0 | 2,073 | `17.46` | `255.81` | `4646.40` | `BitmapAnd` of GIN and B-tree |

The GIN index leaves the `BitmapAnd` once its scan costs more than it saves. `choose_bitmap_and()` keeps it for as long as the two-index plan is cheaper than the B-tree-only plan ([indxpath.c#choose_bitmap_and-accept-reject](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1418-L1489)). On this fixture that comparison flips between 736 and 1,471 pending pages. At 736 pages, `3321.93` against `3486.80` keeps the GIN index, so the planner goes on using it at 25 times the vacuumed plan's cost. At 1,471 pages, a GIN scan of `6264.98` alone exceeds the whole B-tree-only plan of `4646.42`, so the GIN index is dropped.

The boundary therefore depends on what the alternative costs, not only on the pending list. Here the B-tree-only plan is expensive because `cat = 7` alone selects one row in twenty. The GIN-scan column is a separate `EXPLAIN` of the GIN clause on its own. The hidden-index column drops the GIN index inside a rolled-back subtransaction.

`gin_clean_pending_list()` returned exactly `1471`, matching `pgstatginindex` ([ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1027-L1091), [pgstatindex.c#pgstatginindex_internal](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L506-L577)).

**Every pending page is charged in full on a single scan.** Unlike the B-tree page charge in [Step 2: Charge the pages a scan touches](#step-2-charge-the-pages-a-scan-touches), this is not a pro-rata share. Each pending page costs `random_page_cost` plus the `50 * cpu_operator_cost` page charge counted twice, `4.25` per page at default settings ([selfuncs.c#gincostestimate-random-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7976-L7980), [selfuncs.c#gincostestimate-page-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7937-L7955), [selfuncs.c#gincostestimate-total](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8027-L8029)).

`gincostestimate()` books `4.125` of that `4.25` as startup cost, everything except one `50 * cpu_operator_cost` term. The split never reaches a plan, though. A GIN path is only ever a bitmap input, and `cost_bitmap_heap_scan()` takes the index's total cost as its own startup cost whatever the split was ([costsize.c#cost_bitmap_heap_scan-startup](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1044-L1048)).

**A repeated scan amortizes only half of that charge.** The pending pages are seeded into `entryPagesFetched` ([selfuncs.c:7886](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7886)). When the scan repeats, as a nested-loop inner scan with `loop_count > 1` or an array qual with `arrayScans > 1`, `gincostestimate()` runs `entryPagesFetched`, pending pages included, and both data-page counts through `index_pages_fetched()` and divides by `outer_scans` ([selfuncs.c#gincostestimate-cache-effects](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7957-L7974), [selfuncs.c#gincostestimate-datapages-cache](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8017-L8025)). The page universe there is `numEntryPages` or `numDataPages`, which does not include the pending pages. So a repeated scan can be charged fewer entry-side pages than the pending list alone holds:

| Half of the charge | Repeated scans |
|---|---|
| The `random_page_cost` I/O charge | **Amortized.** It is applied after the cache adjustment, so the Mackert-Lohman cap covers the pending pages too ([selfuncs.c:7980](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7980)) |
| The `50 * cpu_operator_cost` per-page charge | **Not amortized.** It is computed from the pre-adjustment page count, and the source says why in as many words: "This is not amortized over a loop" ([selfuncs.c#gincostestimate-page-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7937-L7955)) |

One GIN measurement on this page does take the repeated-scan branch. `loop_count` is 1 for every GIN query here, so `outer_scans` is 1 throughout. But fixture S's `n IN (1,2,3)` is a `ScalarArrayOpExpr` over three satisfiable constants, and `gincost_scalararrayopexpr()` multiplies `arrayScans` by their number ([selfuncs.c#gincost_scalararrayopexpr-arrayScans](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7648-L7658)). That row is therefore priced at `arrayScans = 3` and takes the cache adjustment, while its per-page CPU charge, multiplied by `arrayScans` before the adjustment, is not amortized ([selfuncs.c#gincostestimate-cache-effects](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7957-L7974)).

The branch does not depend on `amsearcharray`. `gincostestimate()` hands any `ScalarArrayOpExpr` among a path's index clauses to `gincost_scalararrayopexpr()` ([selfuncs.c#gincostestimate-saop-clause](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7823-L7833)). What `amsearcharray = false` decides is how the array clause reaches the estimate: the first `build_index_paths()` call leaves it out, and it comes back only through the `ST_BITMAPSCAN` retry ([indxpath.c#build_index_paths-saop](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L862-L885), [indxpath.c#get_index_paths-nonnative-saop](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L753-L766)); see [Gate 2](#gate-2-the-required-plan-shape-rules-gin-out). Every other GIN row on this page prices a single scan with `arrayScans = 1`, where the adjustment does not fire.

#### Stale GIN metapage statistics

`gincostestimate()` trusts the counters of the last build or `VACUUM` only while the index has not grown too much, and even then it scales them. Its conditions decide among three behaviors:

| Condition | Behavior | Consequence |
|---|---|---|
| `nPendingPages < numPages` | `numPendingPages` is the live pending count ([selfuncs.c#gincostestimate-pending-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7724-L7727)) | every pending page is charged, as the previous section shows |
| `nPendingPages >= numPages` | `numPendingPages = 0` ([selfuncs.c#gincostestimate-pending-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7724-L7727)) | a sanity guard against an impossible count, not a cost reduction |
| `numPages > 0`, `nTotalPages <= numPages`, `nTotalPages > numPages / 4`, `nEntryPages > 0` and `nEntries > 0` | **scaled:** `nEntryPages`, `nDataPages` and `nEntries` are each multiplied by `numPages / nTotalPages` and rounded up. Entry pages are then clamped to the non-pending pages, and data pages to what remains ([selfuncs.c#gincostestimate-stats-branch](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7729-L7747)) | the estimate follows growth since the last build or `VACUUM`, up to 4X. The measurement tables call a scale of 1.0 "trusted" |
| any of those fails: the index grew 4X or more, shrank, has zero counters, or is hypothetical, whose counters read as zero ([selfuncs.c#gincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7697-L7711)) | **invented:** `numPages` is raised to at least 10. Entry pages are `floor(0.9 * (numPages - numPendingPages))`, data pages the rest, and entries 100 per entry page ([selfuncs.c#gincostestimate-invented](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7748-L7767)) | the estimate follows the live block count alone. The source comment names the 4X cutoff and calls the 100-entries figure "rather bogus" |

A scaled example is fixture D at 736 pending pages. Its index has 1,038 live blocks and a recorded total of 302, so `302 <= 1038` and `302 > 1038 / 4`. Its entry pages scale to `ceil(273 * 1038 / 302) = 939` and are clamped to the `1038 - 736 = 302` non-pending pages. Its data pages scale to `ceil(28 * 1038 / 302) = 97` and are clamped to the `0` pages left.

`numPages` is `index->pages`, which `get_relation_info()` reads live with `RelationGetNumberOfBlocks()` ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)). So index growth reaches the cost model before any `ANALYZE`, and it can move an index from the scaled branch to the invented one without any counter being written.

Measured on fixture T: a 2,000-row table's GIN index (`fastupdate = off`, 100 distinct keys) sat at 2 blocks with metapage counters `(nTotalPages, nEntryPages, nDataPages, nEntries) = (2, 1, 0, 100)` and priced `n = 42` at `8.64`.

Adding 398,000 rows over 200,000 distinct keys, with an `ANALYZE` but no `VACUUM`, grew it to 1,369 live blocks while the metapage still recorded 2. Because `2 <= 1369 / 4`, the estimate moved to the invented branch (1,232 entry pages, 137 data pages, 123,200 entries), and the cost rose to `17.19`. A later `VACUUM` rewrote the metapage to `(1369, 1368, 0, 200000)`, and the cost moved by one cent, to `17.20`.

#### Lifecycle of the pending list and metapage counters

Two kinds of state go stale in different ways. The pending list grows with every fast-update insert, and the planner reads its size live. The other counters change only when a build or a `VACUUM` rewrites them. These events change each:

| Event | State before | State after | Effect on later estimates |
|---|---|---|---|
| Insert into an index with `fastupdate = on`, the default | a pending list of some size | the new entries are appended to the pending list ([gininsert.c#gininsert-fastupdate](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L510-L530)) | each new pending page adds `4.25` to a single scan at default settings |
| An insert pushes the list past `gin_pending_list_limit` | a list over the limit | the inserting backend asks for a cleanup that is not forced. It returns at once if another process holds the metapage lock, and otherwise stops at the tail it saw when it started ([ginfast.c#needCleanup](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L448-L471), [ginfast.c#ginInsertCleanup-conditional-lock](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L818-L828), [ginfast.c#ginInsertCleanup-stop-at-tail](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L881-L888)) | the list usually shrinks; the other counters are not rewritten |
| Insert with `fastupdate = off` | an existing pending list | new entries go straight into the entry and posting trees, and the old list stays ([gininsert.c#gininsert-fastupdate](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L510-L530), [ref/create_index.sgml#fastupdate-note](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L524-L532)) | the old pending pages are still charged until something drains them |
| `gin_clean_pending_list()` | a pending list | the whole list moves into the tree, and the fork can grow. Only a build and `VACUUM`'s cleanup rewrite the other counters, so they stay as they were ([ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1027-L1091), [gininsert.c:406](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L406), [ginvacuum.c:789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L789)) | the pending charge drops to 0, but the growth can push the index onto the invented branch |
| `VACUUM` with index cleanup on, including one that skips index vacuuming because it found no dead items or took the 2% bypass | a pending list and old counters | `ginbulkdelete()` flushes the list on its first call, or `ginvacuumcleanup()` flushes it when no bulk delete ran. Then `ginUpdateStats()` rewrites the counters ([ginvacuum.c#ginbulkdelete-pending](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L591-L602), [ginvacuum.c#ginvacuumcleanup-pending](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L719-L729), [ginvacuum.c:789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L789), [vacuumlazy.c#lazy_vacuum-call](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1066)) | no pending charge, and a scale of 1.0 |
| `VACUUM` with index cleanup off: `INDEX_CLEANUP OFF`, `vacuum_index_cleanup = off`, or the wraparound failsafe | a pending list and old counters | no `amvacuumcleanup` call, so no flush and no new counters ([vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402), [vacuumlazy.c#lazy_check_wraparound_failsafe-clears](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326)) | no change |
| `ANALYZE` run by an autovacuum worker | a pending list and old counters | after sampling, `ginvacuumcleanup()` flushes the list up to the tail it saw (`full_clean = false`) and returns before `ginUpdateStats()` ([analyze.c:527](../../../../raw/postgres-17/src/backend/commands/analyze.c#L527), [analyze.c#do_analyze_rel-index-cleanup](../../../../raw/postgres-17/src/backend/commands/analyze.c#L694-L721), [ginvacuum.c#ginvacuumcleanup-analyze-only](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L717), [ginfast.c:847](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L847)) | the pending charge drops; the counters stay stale |
| A manual `ANALYZE` | a pending list and old counters | nothing: an `ANALYZE`-only cleanup call outside autovacuum returns at once ([ginvacuum.c#ginvacuumcleanup-analyze-only](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L717)) | no change |
| `CREATE INDEX` or `REINDEX` | any | a fresh build with no pending list, whose counters `ginUpdateStats()` writes with the new block count ([gininsert.c#ginbuild-stats](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L405-L406)) | no pending charge, and a scale of 1.0 |

Fixture D shows the `gin_clean_pending_list()` row. The freshly vacuumed index read `(302, 273, 28, 1779)` at 302 live blocks. After the drain it had 2,073 live blocks while the metapage still recorded 302, so `302 <= 2073 / 4` kept the estimate on invented counters until the next `VACUUM` wrote `(2073, 547, 54, 1779)`. No fixture on this page exercises the autovacuum `ANALYZE` row, because the script runs with `autovacuum = off`.

#### The keyless full-index path on a partial GIN index

GIN sets `amoptionalkey = true` ([ginutil.c:49](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L49)), so `build_index_paths()` does not stop when no clause matches the first index column ([indxpath.c#build_index_paths-amoptionalkey](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L887-L897)). A partial index whose predicate is proven still yields a path through `useful_predicate` ([indxpath.c#build_index_paths-generate](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L954-L962)).

`gincostestimate()` prices that clauseless path as a whole-index scan. When `fullIndexScan` is set or `indexQuals == NIL`, it sets `searchEntries = numEntries`, "as if every key in the index had been listed in the query" ([selfuncs.c#gincostestimate-fullscan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7852-L7877)). The same branch fires when an attribute has a full scan but no normal scan, which is how `GIN_SEARCH_MODE_ALL` reaches the estimate ([gin.h#GIN_SEARCH_MODE_DEFAULT-to-EVERYTHING](../../../../raw/postgres-17/src/include/access/gin.h#L34-L37), [selfuncs.c#gincost_pattern-searchmode](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7454-L7489)).

Measured: a **10-block** partial GIN index with 1,000 entries priced `WHERE id <= 5000`, its own predicate with no GIN-indexable clause, at `4430.38`. The two-`random_page_cost` probe recovered exactly `1001.00` charged pages, 100 times the index's physical size: `ceil(1000 * rint(pow(9, 0.15))) = 1000` entry pages plus one data page. Adding `AND n = 42` dropped the same index's cost to `8.55`.

#### Jobs no GIN index can be created for

Before any planner gate, four things cannot be built on GIN in v17, each rejected because the access method lacks the capability. `amcanunique`, `amcaninclude` and `amclusterable` are false, and an exclusion constraint needs `amgettuple`, which GIN does not supply ([indexcmds.c#DefineIndex-am-checks](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L860-L879), [cluster.c#check_index_is_clusterable-amclusterable](../../../../raw/postgres-17/src/backend/commands/cluster.c#L517-L522)). The script's `grej` stage reproduces all four messages verbatim at the pin:

| Attempt | v17 error |
|---|---|
| `CREATE UNIQUE INDEX … USING gin` | `access method "gin" does not support unique indexes` |
| `CREATE INDEX … USING gin (…) INCLUDE (…)` | `access method "gin" does not support included columns` |
| `EXCLUDE USING gin (… WITH =)` | `access method "gin" does not support exclusion constraints` |
| `CLUSTER … USING <gin index>` | `cannot cluster on index "…" because access method does not support clustering` |

#### Where GIN still wins

- **Operators only GIN has.** Gate 1 runs in both directions: `@@`, `@>`, `?`, `&&` and the `jsonpath` operators are in GIN operator families and not in B-tree ones ([pg_amop.dat#gin-array_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1232-L1244), [pg_amop.dat#gin-tsvector_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1290-L1296), [pg_amop.dat#gin-jsonb_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1593-L1611)). For those predicates there is no B-tree candidate to lose to.
- **One multicolumn GIN instead of a `BitmapAnd`.** The `btree_gin` documentation says that "for queries that test both a GIN-indexable column and a B-tree-indexable column, it might be more efficient to create a multicolumn GIN index that uses one of these operator classes than to create two separate indexes that would have to be combined via bitmap ANDing" ([btree-gin.sgml#caveats](../../../../raw/postgres-17/doc/src/sgml/btree-gin.sgml#L24-L33)). Measured on fixture D after its `VACUUM`, a `gin (tsv, cat)` index priced the two-column predicate at `21.51` and won the plan at `37.20`, against `240.13` for the `BitmapAnd` of the separate indexes at a plan cost of `255.82`.
- **Why that `BitmapAnd` cost one cent more than in the fixture D table.** The table shows `255.81` for the same plan because building the multicolumn index rewrote the table's `reltuples` from `VACUUM`'s 399,985 to 400,000 ([index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135), [index.c#index_update_stats-write](../../../../raw/postgres-17/src/backend/catalog/index.c#L2835-L2923)).
- **Write amortization.** The pending list exists to make GIN insertion cheap, at the documented cost of slower searches ([gin.sgml#fast-update](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L503-L529)).

#### GIN exact-pin measurements

All numbers in this follow-up come from the same run of the same script as the rest of the page: `PostgreSQL 17.11` built from the pin, `autovacuum = off`, `shared_buffers = 256MB`, default planner cost settings (`random_page_cost = 4`, `cpu_operator_cost = 0.0025`, `cpu_index_tuple_cost = 0.005`), and exact statistics; see [Fixtures and method](#fixtures-and-method). `btree_gin` supplied the int4 and bool GIN operator classes, `pgstattuple` supplied `pgstatginindex`, and `pageinspect` supplied `gin_metapage_info()` and `bt_metap()`.

| Fixture | Contents | GIN index | B-tree index |
|---|---|---|---|
| S | `t_both`, 300,000 rows, `n = i % 10000` | `t_both_n_gin`, `btree_gin` int4 opclass, **279 blocks**, `nEntryPages` 278, `nEntries` 10,000, `nDataPages` 0 | `t_both_n_bt`, **280 blocks**, `fastlevel` 1, 90.31% `avg_leaf_density` |
| D | `docs`, 200,000 then 300,000 then 400,000 rows; each `tsvector` is `filler`, `w` plus `i % 1000`, `v` plus `i % 777`, and `zebracorn` on every 4,999th row | `docs_tsv_gin` on `tsvector`, `fastupdate = on`, 302 blocks when vacuumed | `docs_cat_bt` on `cat = i % 20`, 171 blocks |
| T | `t_stale`, 2,000 rows with `n = i % 100`, then 398,000 more with `n = i % 200000` | `t_stale_gin`, `fastupdate = off`, vacuumed at 2,000 rows and not again until the last step | none |
| P-gin | `t_part`, 100,000 rows, `n = i % 1000` | `t_part_gin`, partial `WHERE id <= 5000`, 10 blocks, 1,000 entries | none |
| B-gin | `t_bool`, 100,000 boolean rows, 1% true | `t_bool_gin`, `btree_gin` bool opclass | none |

##### Same table, same statistics, both indexes

Each row below is two `EXPLAIN` runs on fixture S, with the *other* index dropped inside a rolled-back subtransaction, so `pg_statistic`, `reltuples` and every selectivity estimate are identical. `enable_seqscan` was off, so that a missing index path shows as a `disable_cost`-priced sequential scan. The B-tree runs of the first four rows also had `enable_indexscan` off, so those four rows compare the two `Bitmap Index Scan` nodes. Both settings are `PGC_USERSET`, and the script sets them for one statement ([guc_tables.c#enable_seqscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L783-L792), [guc_tables.c#enable_indexscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L793-L802)). The last three rows give each plan's top node.

| Predicate | GIN | B-tree | Row estimate (both) |
|---|---:|---:|---:|
| `n = 42` | `12.97` | `4.52` | 30 |
| `n BETWEEN 100 AND 200` | `66.30` | `42.60` | 3,030 |
| `n < 20` | `28.57` | `8.80` | 600 |
| `n IN (1,2,3)` | `30.10` | `13.57` | 90 |
| `ORDER BY n LIMIT 10` | no index path: `Sort` over `Seq Scan`, `Limit` at `10000010810.92` | `Limit` at `0.66` | 10 |
| `SELECT n WHERE n = 42` | no index-only scan: `Bitmap Heap Scan` at `119.83` | `Index Only Scan` at `4.82` | 30 |
| `n IS NULL` | no index path: `Seq Scan` at `10000004328.00` | `Index Scan` at `8.31` | 1 |

The last three rows are gate-2 outcomes rather than cost losses, and they are not the same outcome. Two of them, `ORDER BY n LIMIT 10` and `n IS NULL`, have **no GIN path at all**, so the planner falls back to the disabled sequential scan.

`enable_seqscan = off` adds `disable_cost = 1.0e10` ([costsize.c:130](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L130)) to that scan's startup cost and then prices it normally ([costsize.c#cost_seqscan-disable](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L304-L305)). So each figure is `1.0e10` plus the plan's normal cost: the `Seq Scan` at `10000004328.00` is `1.0e10 + 4328.00`, and the `Limit` at `10000010810.92` is `1.0e10 + 10810.92`, the sort over that scan plus its first 10 rows.

The third, `SELECT n WHERE n = 42`, still **uses the GIN index**. It loses only the index-*only* scan and falls back to a `Bitmap Heap Scan` at `119.83`, against the B-tree's `Index Only Scan` at `4.82`. Two `NULL` callbacks cause that, and neither removes the bitmap path. GIN's `NULL` `amcanreturn` ([ginutil.c:70](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L70)) fails `check_index_only()`. Its `NULL` `amgettuple` ([ginutil.c:79](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L79)) leaves `amhasgettuple` false ([plancat.c#get_relation_info-am-flags](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L317-L335)), so `get_index_paths()` keeps every plain or index-only `IndexPath` out of `add_path()` and passes it on only as a bitmap candidate ([indxpath.c#get_index_paths-submit](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L740-L751)).

GIN therefore cannot get an index-only scan even for a query that needs no columns, and only two of the seven rows carry a `disable_cost` figure. With every `enable_*` setting at its default, the planner chose the B-tree for `n = 42`, `n BETWEEN 100 AND 200` and `n < 20` alike.

##### The page charge, isolated

Running the same query at `random_page_cost = 4` and at `random_page_cost = 1` isolates the page count, because every other GIN charge is a CPU charge that does not scale with it. `random_page_cost` is `PGC_USERSET`, and the script sets it for one statement ([guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696)). The last column names the branch of [Stale GIN metapage statistics](#stale-gin-metapage-statistics) that priced each row:

| Case | Cost at `rpc = 4` | Cost at `rpc = 1` | Difference / 3 | Reconciliation |
|---|---:|---:|---:|---|
| Fixture S, `n = 42` | `12.97` | `3.97` | `3.00` | trusted stats, scale `279 / 279 = 1.0` ([selfuncs.c#gincostestimate-stats-branch](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7729-L7747)): `rint(278^0.15) = 2` entry pages + 1 data page from the selectivity floor, since the metapage records 0 data pages |
| Fixture D, vacuumed, `nTotalPages` 302 = 302 live blocks | `13.01` | `4.01` | `3.00` | trusted stats, scale `302 / 302 = 1.0` ([selfuncs.c#gincostestimate-stats-branch](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7729-L7747)): `rint(273^0.15) = 2` entry pages + 1 data page |
| Fixture D, 736 pending pages, 1,038 live blocks | `3141.12` | `924.12` | `739.00` | scaled stats, `302 > 1038 / 4`, scale `1038 / 302 = 3.44` ([selfuncs.c#gincostestimate-stats-branch](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7729-L7747)): entry pages clamp from 939 to 302, so `rint(302^0.15) = 2`, and data pages clamp to 0, so the 1 data page is the selectivity floor: 736 pending + 2 entry + 1 data page |
| Fixture D, 1,471 pending pages, 1,773 live blocks | `6264.98` | `1842.98` | `1474.00` | invented stats, `302 <= 1773 / 4` ([selfuncs.c#gincostestimate-invented](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7748-L7767)): `floor((1773 - 1471) * 0.9) = 271` entry pages, `rint(271^0.15) = 2`: 1,471 pending + 2 entry + 1 data page |
| Fixture D, drained, 2,073 live blocks, metapage still 302 | `17.49` | `5.49` | `4.00` | invented stats, `302 <= 2073 / 4` ([selfuncs.c#gincostestimate-invented](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7748-L7767)): `floor(2073 * 0.9) = 1865` entry pages, `rint(1865^0.15) = 3`: 3 entry pages + 1 data page |
| Fixture T, stale metapage, 1,369 live blocks | `17.19` | `5.19` | `4.00` | invented stats, `2 <= 1369 / 4` ([selfuncs.c#gincostestimate-invented](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7748-L7767)): `floor(1369 * 0.9) = 1232` entry pages, `rint(1232^0.15) = 3`: 3 entry pages + 1 data page |
| Fixture T after `VACUUM`, metapage `(1369, 1368, 0, 200000)` | `17.20` | `5.20` | `4.00` | trusted stats, scale `1369 / 1369 = 1.0` ([selfuncs.c#gincostestimate-stats-branch](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7729-L7747)): `rint(1368^0.15) = 3` entry pages + 1 data page from the selectivity floor |
| Fixture P-gin, keyless partial index, 10 live blocks | `4430.38` | `1427.38` | `1001.00` | trusted stats, scale `10 / 10 = 1.0`; no index qual, so a full-index scan with `searchEntries = numEntries = 1000` ([selfuncs.c#gincostestimate-fullscan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7852-L7877)), each `rint(9^0.15) = 1` entry page: 1,000 entry pages + 1 data page from the selectivity floor |

The difference is divided by three because each charged page costs `3.0` more at `rpc = 4` than at `rpc = 1`. Every row is also charged at least one data page. The data-page floor is `ceil(indexSelectivity * (numTuples / (BLCKSZ / 3)))`, so a scan whose per-entry data-page count is 0 still pays for one data page whenever its selectivity and `index->tuples` are both above zero ([selfuncs.c#gincostestimate-datapages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7982-L8006), [selfuncs.c:7675](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7675)).

The two pending-list rows are the sharpest result. 736 and 1,471 pages that hold no tree structure at all are charged page for page, `739.00` and `1474.00`, on a scan that is charged 4 pages once the list is gone. They also land on different branches. At 1,038 live blocks the recorded counters are still within the 4X window, so they are scaled; at 1,773 blocks they are not, and the estimate is invented from the block count. The plan consequences are in [A GIN index with a large pending list loses to a B-tree](#a-gin-index-with-a-large-pending-list-loses-to-a-b-tree).

##### Boolean column

Fixture B-gin priced `WHERE i`, `WHERE i = true` and `WHERE i IS TRUE` identically at `38.26` for the GIN index scan, each with `Index Cond: (i = true)`. So a bare boolean `Var` is not a gate-1 rejection in v17. `i IS TRUE` also left `Filter: (i IS TRUE)` on the heap node while still using the index.

##### Live property matrix

Queried on fixture S, `pg_index_has_property` and `pg_index_column_has_property` returned exactly the values the `amutils` expected output asserts. `index_scan`, `clusterable` and `backward_scan` are false for GIN and true for B-tree, and `bitmap_scan` is true for both. `orderable`, `returnable`, `search_array` and `search_nulls` are false for GIN and true for B-tree ([amutils.out#column-properties](../../../../raw/postgres-17/src/test/regress/expected/amutils.out#L96-L108), [amutils.out#index-properties](../../../../raw/postgres-17/src/test/regress/expected/amutils.out#L122-L129)).

##### A diagnostic pair for a live server

The script's `diag` stage reads both blocks below out of this page and runs them verbatim at the pin, against objects literally named `my_table`, `my_col` and `my_gin_index`; [Last run](#last-run) records the runs that executed them.

The first block reports how much of one named GIN index is pending list. The planner charges a single scan one page read for every pending page ([selfuncs.c#gincostestimate-pending](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7882-L7886)), although those pages hold deferred insert work rather than wasted space ([gin.sgml#fast-update](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L503-L529)). Drop the `c.relname` condition to list every valid, non-partitioned GIN index in the database other than another session's temporary ones.

The inner filters keep `pgstatginindex()` away from three kinds of GIN index that it rejects with an `ERROR`, which would abort the whole query:

- A partitioned index carries the GIN access method in `relam` like any other index, but its `relkind` is `'I'`, and `pgstatginindex()` accepts only `relkind` `'i'` ([index.c:1015](../../../../raw/postgres-17/src/backend/catalog/index.c#L1015), [pg_class.h#RELKIND_INDEX-and-RELKIND_PARTITIONED_INDEX](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L162-L173), [pgstatindex.c#IS_INDEX](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L70-L72)).
- An invalid index, such as a failed `CREATE INDEX CONCURRENTLY` leaves behind ([ref/create_index.sgml#concurrently-invalid](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L646-L651)).
- Another session's temporary index, whose `relpersistence` is `'t'` ([pg_class.h:177](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L177), [pgstatindex.c#pgstatginindex_internal-checks](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L520-L543), [rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/src/include/utils/rel.h#L667-L669)).

The `OFFSET 0` fence makes sure those filters run before the call. A subquery with `OFFSET` is never pulled up into the outer query, so it is planned and filtered on its own before its rows reach the `LATERAL` call ([prepjointree.c#is_simple_subquery](../../../../raw/postgres-17/src/backend/optimizer/prep/prepjointree.c#L1689-L1701)).

```sql
SET /* wiki_gin_pending_list_share */ statement_timeout = '30s';
SET /* wiki_gin_pending_list_share */ lock_timeout = '5s';

SELECT /* wiki_gin_pending_list_share */
       gi.relname                                       AS gin_index,
       pg_relation_size(gi.oid) / current_setting('block_size')::int AS live_blocks,
       g.pending_pages,
       g.pending_tuples,
       round(100.0 * g.pending_pages
             / greatest(pg_relation_size(gi.oid)
                        / current_setting('block_size')::int, 1), 2)
                                                        AS pending_pct_of_index
  FROM (SELECT c.oid, c.relname
          FROM pg_class c
          JOIN pg_index i ON i.indexrelid = c.oid
          JOIN pg_am    a ON a.oid = c.relam
         WHERE a.amname = 'gin'
           AND c.relkind = 'i'
           AND i.indisvalid
           AND (c.relpersistence <> 't'
                OR c.relnamespace = pg_my_temp_schema())
           AND c.relname = 'my_gin_index'
        OFFSET 0) AS gi  -- fence: filter before pgstatginindex() runs
  CROSS JOIN LATERAL pgstatginindex(gi.oid) AS g
 ORDER BY g.pending_pages DESC;

RESET /* wiki_gin_pending_list_share */ statement_timeout;
RESET /* wiki_gin_pending_list_share */ lock_timeout;
```

It reported `live_blocks = 340`, `pending_pages = 246`, `pending_tuples = 50000` and `pending_pct_of_index = 72.35`, against a `my_table` of 100,000 vacuumed rows with 50,000 more waiting in the pending list. `pgstatginindex` comes from `pgstattuple`. Since extension version 1.5 the SQL function binds to a C entry point with no superuser check of its own, and relies on `EXECUTE`, which the upgrade script revokes from `PUBLIC` and grants to `pg_stat_scan_tables` ([pgstattuple--1.4--1.5.sql#pgstatginindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L49-L57), [pgstatindex.c#pgstatginindex_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L497-L504)). It takes an [`AccessShareLock`](../../../glossary.md#lock-mode) on the index and reads only the metapage ([pgstatindex.c#pgstatginindex_internal](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L506-L577)).

The second block recovers the number of pages the planner is charging, without any contrib module:

```sql
SET /* wiki_gin_page_charge_probe */ statement_timeout = '30s';
SET /* wiki_gin_page_charge_probe */ lock_timeout = '5s';
SET /* wiki_gin_page_charge_probe */ enable_seqscan = off;

-- Run this first.  get_tablespace_page_costs() returns the tablespace's own
-- random_page_cost whenever that reloption is set, and ignores the session
-- GUC entirely.  If spc_random_page_cost below is not NULL, the two EXPLAIN
-- runs price the index's pages identically and the subtraction reports zero
-- charged pages no matter how many the planner is really charging for.
SELECT /* wiki_gin_page_charge_tablespace_check */
       c.relname                                       AS gin_index,
       t.spcname                                       AS tablespace,
       (SELECT o.option_value
          FROM pg_options_to_table(t.spcoptions) AS o
         WHERE o.option_name = 'random_page_cost')     AS spc_random_page_cost
  FROM pg_class c
  JOIN pg_tablespace t
    ON t.oid = CASE WHEN c.reltablespace <> 0 THEN c.reltablespace
                    ELSE (SELECT d.dattablespace FROM pg_database d
                           WHERE d.datname = current_database()) END
 WHERE c.relname = 'my_gin_index';

SET /* wiki_gin_page_charge_probe */ random_page_cost = 4;
EXPLAIN /* wiki_gin_page_charge_probe_high */ (COSTS ON)
SELECT count(*) FROM my_table
 WHERE my_col @@ to_tsquery('simple', 'filler');

SET /* wiki_gin_page_charge_probe */ random_page_cost = 1;
EXPLAIN /* wiki_gin_page_charge_probe_low */ (COSTS ON)
SELECT count(*) FROM my_table
 WHERE my_col @@ to_tsquery('simple', 'filler');

RESET /* wiki_gin_page_charge_probe */ random_page_cost;
RESET /* wiki_gin_page_charge_probe */ enable_seqscan;
RESET /* wiki_gin_page_charge_probe */ statement_timeout;
RESET /* wiki_gin_page_charge_probe */ lock_timeout;
```

The `Bitmap Index Scan` costs were `2030.46` and `1121.46`, so `(2030.46 - 1121.46) / 3 = 303.00` pages, of which 246 were pending list. Divide by three because the two runs differ by exactly `3.0` per charged page.

Both blocks change settings for their own session only, and reset them. [`statement_timeout`](../../../glossary.md#statement_timeout-and-lock_timeout), `lock_timeout`, `enable_seqscan` and `random_page_cost` are all `PGC_USERSET`, so none needs a reload or a restart ([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631), [guc_tables.c#enable_seqscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L783-L792), [guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696)). On the measurement server the check returns `pg_default` and a NULL `spc_random_page_cost`, so the session setting is what `gincostestimate()` sees.

Two conditions have to hold before the subtraction means anything, and neither is visible in the arithmetic:

- **The index's tablespace must not override `random_page_cost`.** `gincostestimate()` prices its pages with `get_tablespace_page_costs(index->reltablespace, ...)`, which returns the tablespace's `random_page_cost` option whenever it is set to a non-negative value, and falls back to the setting only when it is not ([spccache.c#get_tablespace_page_costs](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L181-L196), [selfuncs.c#gincostestimate-tablespace-costs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7786-L7789)). An index on such a tablespace prices identically at `random_page_cost = 4` and `= 1`, so the probe reports `0.00` charged pages for an index that may be charging thousands. The query above tells the two cases apart; it reads the catalog only and takes no lock on the index.
- **Both plans must name the same index.** Changing `random_page_cost` changes relative costs, so the cheaper setting can select a different index, a different bitmap combination or a different node shape ([indxpath.c#choose_bitmap_and-accept-reject](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1418-L1489), [pathnode.c#add_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L419-L622)). The difference would then subtract two unrelated plans. Check that the `Bitmap Index Scan` line in both outputs names the index you are probing before dividing by three.

#### GIN settings that move the boundary

| Setting | v17 default | Role in the GIN-versus-B-tree decision | Apply scope |
|---|---|---|---|
| `random_page_cost` | 4.0 ([cost.h:25](../../../../raw/postgres-17/src/include/optimizer/cost.h#L25)) | Multiplies every pending, entry and data page GIN expects to touch, unless the index's tablespace sets its own `random_page_cost` ([selfuncs.c#gincostestimate-tablespace-costs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7786-L7789), [selfuncs.c#gincostestimate-random-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7976-L7980), [selfuncs.c#gincostestimate-total](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8027-L8029), [spccache.c#get_tablespace_page_costs](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L181-L196)) | session/transaction (`PGC_USERSET`, [guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696)) |
| `cpu_operator_cost` | 0.0025 ([cost.h:28](../../../../raw/postgres-17/src/include/optimizer/cost.h#L28)) | Scales GIN's entry-tree descent and its `50 *` per-page CPU charges ([selfuncs.c#gincostestimate-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7919-L7935), [selfuncs.c#gincostestimate-page-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7937-L7955), [selfuncs.c#gincostestimate-search-entry-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8008-L8015), [selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145)), and the B-tree's height charge ([selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)) | session/transaction (`PGC_USERSET`, [guc_tables.c#cpu_operator_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3719-L3729)) |
| `gin_pending_list_limit` | 4MB (`4096` kB, [guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585)) | The size at which an insert *asks* for a cleanup. Not a ceiling: see below ([ginfast.c#needCleanup](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L448-L471)) | session/transaction (`PGC_USERSET`, [guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585)) |
| `enable_bitmapscan` | on ([guc_tables.c#enable_bitmapscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L813-L822)) | Turning it off does not remove GIN's plan shape; it adds `disable_cost` to it. See below ([costsize.c#cost_bitmap_heap_scan-disable](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1041-L1042)) | session/transaction (`PGC_USERSET`, [guc_tables.c#enable_bitmapscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L813-L822)) |

Two of those four need the fine print spelled out, because the obvious reading of each is wrong.

**`gin_pending_list_limit` triggers a cleanup; it does not cap the list.** `ginHeapTupleFastInsert()` writes the new entries first, and only then compares the resulting size with the limit and sets `needCleanup`. So the list is already over the limit when the test fires ([ginfast.c#needCleanup](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L448-L471)). The cleanup that follows is deliberately not forced: called from a regular insert, `ginInsertCleanup()` takes the metapage lock only conditionally, and if another process holds it, returns at once "in hope that concurrent process will clean up pending list" ([ginfast.c#ginInsertCleanup-conditional-lock](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L818-L828)).

The GIN chapter frames the limit the same way, as a condition under which entries are moved, and notes that "the overhead work can be done by a background process" ([gin.sgml#fast-update](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L503-L529)). The setting's reference entry, its `guc_tables.c` description and the per-index option's description in `reloptions.c` all describe it as the maximum size of the pending list ([config.sgml#guc-gin-pending-list-limit](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L9870-L9890), [guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585), [reloptions.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L339-L347)). The source does not enforce a maximum; that discrepancy is filed under [Open Questions](#open-questions).

So the setting bounds the typical pending-list charge, not its maximum, and fixture D reaches 1,471 pending pages by raising the limit so that no insert ever asks for a cleanup.

**`enable_bitmapscan = off` does not remove the path.** It is a cost penalty, not a veto. `cost_bitmap_heap_scan()` adds `disable_cost` to the startup cost and then prices the path normally ([costsize.c#cost_bitmap_heap_scan-disable](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1041-L1042)). A GIN plan therefore still wins when every alternative is also disabled or more expensive, which is how the `disable_cost`-priced sequential scans in the fixture S table were produced with `enable_seqscan = off`. What turning it off reliably does is make any other viable plan win.

Two per-index storage parameters change the physical shape rather than its price, and changing either takes [`AccessExclusiveLock`](../../../glossary.md#accessexclusivelock): `fastupdate` (default on) and a per-index `gin_pending_list_limit` override ([reloptions.c#fastupdate](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L123-L130), [reloptions.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L339-L347)). `gin_clean_pending_list()` drains the list on demand and takes `RowExclusiveLock` on the index ([ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1027-L1091)).

#### GIN key data structures

| Structure | Field | Role |
|---|---|---|
| `GinQualCounts` | `partialEntries`, `exactEntries`, `searchEntries`, `arrayScans`, `attHasFullScan`, `attHasNormalScan` | The whole per-qual working set `gincostestimate()` derives from the index quals ([selfuncs.c#GinQualCounts](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7370-L7378)) |
| `GinStatsData` | `nPendingPages`, `nTotalPages`, `nEntryPages`, `nDataPages`, `nEntries` | The metapage counters ([gin.h#GinStatsData](../../../../raw/postgres-17/src/include/access/gin.h#L40-L50)); only `nPendingPages` and `ginVersion` are current ([ginutil.c#ginGetStats](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L616-L642)) |
| `GinMetaPageData` | same counters, on disk | Where those numbers live, and why `VACUUM` is what refreshes them ([ginblock.h#GinMetaPageData](../../../../raw/postgres-17/src/include/access/ginblock.h#L55-L101)) |
| `FormData_pg_index` | `indisvalid`, `indcheckxmin` | Gate-0 inputs, read before any `IndexOptInfo` exists ([pg_index.h#indisvalid](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L42-L43)). `get_relation_info()` skips an invalid index, and skips an `indcheckxmin` index whose `pg_index` row is not yet older than `TransactionXmin`, marking the plan transient ([plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281)) |
| `IndexOptInfo` | `indpred`, `predOK` | The gate-0 partial-index test ([pathnodes.h:1168](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1168), [pathnodes.h:1181](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1181)). `check_index_predicates()` sets `predOK` when the query's restrictions imply the predicate ([indxpath.c#check_index_predicates-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L3272-L3350)), and `create_index_paths()` skips a partial index without it ([indxpath.c#create_index_paths-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L260-L266)) |
| `IndexOptInfo` | `amhasgettuple`, `amhasgetbitmap`, `amcanparallel`, `amsearcharray`, `amsearchnulls`, `amoptionalkey`, `sortopfamily`, `canreturn[]` | The gate-2 inputs, all filled once in `get_relation_info()`: the flags ([plancat.c#get_relation_info-am-flags](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L317-L335)), `canreturn[]` ([plancat.c#get_relation_info-canreturn](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L296-L301)) and `sortopfamily` ([plancat.c#get_relation_info-sortopfamily](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L340-L422)) |

#### GIN caller and callee boundary

```text
build_simple_rel                                relnode.c
  └─ get_relation_info                          plancat.c
       ├─ skips an index that is not indisvalid                      GATE 0
       ├─ skips an indcheckxmin index not yet usable (plan transient) GATE 0
       └─ fills IndexOptInfo: AM flags, canreturn[] via index_can_return, sortopfamily

set_plain_rel_pathlist                          allpaths.c
  └─ create_index_paths                         indxpath.c
       ├─ skips a partial index that is not predOK                   GATE 0
       ├─ match_restriction_clauses_to_index
       │    └─ match_clauses_to_index -> match_clause_to_index
       │         └─ match_clause_to_indexcol
       │              ├─ match_boolean_index_clause  (IsBooleanOpfamily opfamilies)
       │              ├─ match_opclause_to_indexcol  -> op_in_opfamily   GATE 1
       │              │    └─ get_index_clause_from_support
       │              ├─ match_saopclause_to_indexcol
       │              └─ NullTest branch             needs amsearchnulls GATE 2
       ├─ get_index_paths
       │    ├─ build_index_paths(ST_ANYSCAN)    amoptionalkey / pathkeys
       │    │    ├─ check_index_only            reads canreturn[]    GATE 2
       │    │    └─ create_index_path -> cost_index
       │    │         └─ amcostestimate == gincostestimate   GATE 3 input
       │    │              ├─ ginGetStats       -> GIN metapage
       │    │              ├─ gincost_opexpr / gincost_scalararrayopexpr
       │    │              │    └─ gincost_pattern   -> extractQuery support proc
       │    │              └─ index_pages_fetched    (nestloop / array scans)
       │    ├─ add_path                         amhasgettuple only   GATE 2
       │    └─ build_index_paths(ST_BITMAPSCAN)  non-native SAOP retry
       ├─ choose_bitmap_and                     GATE 3
       │    ├─ cost_bitmap_tree_node            same clause set: keeps the cheaper index (GIN vs B-tree)
       │    ├─ bitmap_scan_cost_est -> cost_bitmap_heap_scan   prices each AND-group leader
       │    └─ bitmap_and_cost_est -> bitmap_scan_cost_est     adds an index only if the whole scan gets cheaper
       ├─ create_bitmap_heap_path -> cost_bitmap_heap_scan     enable_bitmapscan adds disable_cost
       └─ add_path                              whole paths compete  GATE 3
```

`GATE 3` marks where cost decides. `gincostestimate()` only supplies the index estimate. For one clause matched by both a GIN and a B-tree index, as on fixture S, `choose_bitmap_and()` keeps whichever index path `cost_bitmap_tree_node()` prices lower: its index estimate plus a small per-row bitmap charge ([indxpath.c#choose_bitmap_and-cheapest-of-group](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1353-L1399), [costsize.c#cost_bitmap_tree_node](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1114-L1144)). For different clauses it adds an index to an AND group only when the whole bitmap-heap-scan estimate drops ([indxpath.c#choose_bitmap_and-accept-reject](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1418-L1489)). The resulting bitmap heap path then competes with every other path for the relation in `add_path()` ([indxpath.c:343](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L343), [pathnode.c#add_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L419-L622)).

Symbols: [relnode.c:340](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c#L340), [plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281), [plancat.c#get_relation_info-canreturn](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L296-L301), [allpaths.c:783](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L783), [indxpath.c#create_index_paths](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L234-L413), [indxpath.c#create_index_paths-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L260-L266), [indxpath.c#match_restriction_clauses_to_index](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1968-L1974), [indxpath.c#match_clauses_to_index](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2051-L2064), [indxpath.c#match_clause_to_index](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2084-L2136), [indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2203-L2269), [indxpath.c#get_index_paths](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L709-L767), [indxpath.c#get_index_paths-submit](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L740-L751), [indxpath.c#build_index_paths](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L804-L1057), [indxpath.c#check_index_only](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1730-L1800), [pathnode.c:1024](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L1024), [costsize.c#cost_index-amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L610-L621), [selfuncs.c#gincostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7662-L8050), [selfuncs.c#gincost_pattern](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7380-L7492), [indxpath.c#choose_bitmap_and](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1287-L1489), [indxpath.c#bitmap_scan_cost_est](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1526-L1553), [indxpath.c#bitmap_and_cost_est](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1560-L1571), [indxpath.c:341](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L341), [pathnode.c#create_bitmap_heap_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L1042-L1068), [costsize.c#cost_bitmap_heap_scan-disable](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1041-L1042), [ginutil.c#ginhandler](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L36-L89).

#### GIN tests and explicit test absence

- **No test asserts a GIN or B-tree index cost, so none compares the two.** No expected output under `src/test` or `contrib` prints a numeric cost for any index or bitmap node. A search of every `*.out` file there for `(cost=` followed by a digit finds only the two `cost=0.00..0.00` lines of a partitioned `UPDATE` plan in `inherit.out` ([expected/inherit.out#parted_tab-update](../../../../raw/postgres-17/src/test/regress/expected/inherit.out#L697-L698)). Neither `src/test` nor `contrib` mentions `gincostestimate`, though every GIN plan in the suites runs it.
- **The one same-column pair in the suites never coexists.** `jsonb.sql` builds a GIN index `jidx` on `testjsonb.j`, drops it, and only then builds a B-tree of the same name on the same column, so no test plan can choose between them ([jsonb.sql:852](../../../../raw/postgres-17/src/test/regress/sql/jsonb.sql#L852), [jsonb.sql:929](../../../../raw/postgres-17/src/test/regress/sql/jsonb.sql#L929), [jsonb.sql:932](../../../../raw/postgres-17/src/test/regress/sql/jsonb.sql#L932)).
- The `btree_gin` suite asserts plan *shape* only, never cost. Every `EXPLAIN` in it uses `COSTS OFF`, and every test file except the install script sets `enable_seqscan = off` ([bool.sql#enable_seqscan-off](../../../../raw/postgres-17/contrib/btree_gin/sql/bool.sql#L1-L9), [bool.out#gin-bool-equality](../../../../raw/postgres-17/contrib/btree_gin/expected/bool.out#L89-L98)).
- Gate 0's `indcheckxmin` skip has no regression test. No file under `src/test` mentions `indcheckxmin`, and its only `contrib` mention is in `amcheck`'s `verify_nbtree.c`, which is not a test.
- What *is* covered is the gate-2 property matrix, by `amutils`: its column-level half (`orderable`, `returnable`, `search_array`, `search_nulls`) and its index-level half (`clusterable`, `index_scan`, `bitmap_scan`, `backward_scan`) ([amutils.out#column-properties](../../../../raw/postgres-17/src/test/regress/expected/amutils.out#L96-L108), [amutils.out#index-properties](../../../../raw/postgres-17/src/test/regress/expected/amutils.out#L122-L129)). The bitmap-only restriction is covered by comments and expected plans in `create_index` and `tsearch` ([create_index.sql#gin-bitmap-only](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L264-L268), [tsearch.sql#gin-bitmap-only](../../../../raw/postgres-17/src/test/regress/sql/tsearch.sql#L225-L230)).
- Every measurement in this follow-up comes from this page's own script on an isolated exact-pin server, not from an in-tree test.

#### GIN causal summary

1. **Initial state.** A table has a GIN index and a B-tree on the same column. The GIN metapage holds counters from the last build or `VACUUM`, plus a live pending-list size that inserts have grown since ([selfuncs.c#gincostestimate-trust](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7727), [gininsert.c#gininsert-fastupdate](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L510-L530)).
2. **Input.** A query clause on that column reaches the planner.
3. **Gates 0 to 2.** The planner drops the GIN index if it is unusable in this transaction, rejects the clause if its operator is outside the GIN operator family, and never gives GIN a plain, ordered, index-only or `IS NULL` scan. Whatever survives is a bitmap input ([plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281), [indxpath.c#match_opclause_to_indexcol-op_in_opfamily](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2433-L2459), [indxpath.c#get_index_paths-submit](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L740-L751)).
4. **Pricing.** `gincostestimate()` charges every pending page and a power-law number of entry pages at `random_page_cost`, plus page CPU charges. `btcostestimate()` charges a pro-rata share of the B-tree's pages plus a small height charge ([selfuncs.c#gincostestimate-pending](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7882-L7886), [selfuncs.c#gincostestimate-entrypages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7888-L7914), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)).
5. **Interaction.** `choose_bitmap_and()` keeps the cheaper index for the same clause, or adds GIN to an AND group only when the whole scan gets cheaper; `add_path()` then compares whole plans ([indxpath.c#choose_bitmap_and](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1287-L1489), [pathnode.c#add_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L419-L622)).
6. **Observed result.** On a comparison predicate the B-tree wins, `4.52` against `12.97`. A pending list of 1,471 pages pushes a GIN index out of a `BitmapAnd` it joins at 736 pages, because its scan alone, `6264.98`, exceeds the B-tree-only plan, `4646.42`.
7. **Refresh.** `VACUUM`, an autovacuum `ANALYZE` or `gin_clean_pending_list()` drains the pending list, which removes the pending charge at the next plan. Only a build or a `VACUUM` rewrites the other counters ([ginvacuum.c#ginvacuumcleanup-analyze-only](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L717), [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1027-L1091), [gininsert.c:406](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L406), [ginvacuum.c:789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L789)).

## Measurement Script

### Usage

| Item | Detail |
|---|---|
| Purpose | produces every measured number on this page, in the main answer and in the GIN follow-up: block counts, `pgstatindex` density and fragmentation, `bt_metap()` fast-root levels, GIN metapage counters and pending pages, every `EXPLAIN` cost, row estimate, plan width and worker count, the closed-form predictions, fixture Q's charged index pages and catalog rows, fixture E's dead-entry counts, the catalog, metapage-root, estimate-against-truth and AM-property values the page quotes, the four GIN rejection messages, and the verbatim run of the two filed diagnostic blocks |
| Invocation | `bash .wiki-runtime/tmp/bloatplan.sh` from the repository root, after extracting the script to that path with the two commands under this table. The script resolves everything from `WIKI_ROOT`, which defaults to `$PWD` and must be this repository: it checks for `AGENTS.md`, `wiki` and `raw` there before it creates anything |
| Stages | `build check cluster fa fb ff fg fh fi fn fstale fl3 fp fq fe gs gd gt gp gb grej diag predict summary stop` in that default order, plus `clean` on request. Select stages as arguments: `bash .wiki-runtime/tmp/bloatplan.sh fa predict`. `build` checks that the checkout is at the pin with no tracked file changed, configures out of tree, installs core plus `pgstattuple`, `pageinspect` and `btree_gin`, and records the pin beside the binaries last. It skips the build when that record exists and names the pin; an install with no record, left by an interrupted build, is removed and built again. `check` repeats the pin checks and runs `make check` and the three contrib suites, with their temporary servers' sockets in `$SANDBOX/rs`. `cluster` runs `initdb` once, starts the server, and installs the recording helpers `xp()`, `nodes()`, `idxcost()`, `ixstat()`, `ginstat()`, `predict()` and `fact()`. `fa` `fb` `ff` `fg` `fh` `fi` `fn` `fstale` `fl3` `fp` `fq` `fe` build the B-tree fixtures A, B with M, F with F-one, G, H, I, N, the forged catalog rows, the `BitmapAnd` pair L3, P with P-100, the partial-index pair Q, and the endpoint-probe table E. `gs` `gd` `gt` `gp` `gb` build the GIN fixtures S, D, T, P-gin and B-gin. `grej` sends the four statements that must fail. `diag` reads the two `sql` blocks out of this page and runs them verbatim. `predict` compares the closed form with `EXPLAIN`. `summary` writes the result file. `stop` stops the server and asserts the teardown. Every fixture stage drops and rebuilds its own tables and replaces its own result rows, so any stage can be re-run alone; `grej` needs `gs` and refuses to run without it, and `predict` needs `fa`, `fb` and `fg` for its seven rows. Every SQL stage starts the server itself if it is not up, so a selected re-run works after a default run has already stopped the cluster; `cluster` starts it by definition, and `build`, `check`, `stop` and `clean` never start one |
| Failure handling | Every stage name is checked before any stage runs, so a misspelt stage stops the run before anything is built or started. Every `psql` call that fails ends the run with a non-zero status: `pg()`, `pgq()` and `pgopt()` end in a `die`, and each `psql` call made inside `$(...)`, where `die` can only end the subshell, is followed by its own `\|\| die`. Stage exit status is checked on top of that, so a failed `configure`, `make`, `make check` or `psql` cannot be reported as a pass. `grej`'s four statements are meant to fail, so it first checks that fixture S's GIN index exists, then runs each statement alone through `pgerr()`, with `ON_ERROR_STOP` like every other call. Each must end `psql` with status 3, `psql`'s status for a failed statement read from a script or standard input under `ON_ERROR_STOP` ([mainloop.c#MainLoop-exit-status](../../../../raw/postgres-17/src/bin/psql/mainloop.c#L587-L594), [settings.h:172](../../../../raw/postgres-17/src/bin/psql/settings.h#L172)), and with its own rejection text, so a failure for any other reason, such as a missing table, stops the run. The one deliberate exception is the background snapshot holder, which the script ends itself with `pg_terminate_backend()`; its exit status is discarded, and the script checks instead that the holder took a snapshot and that exactly one live holder was ended after the churn. An `EXIT` trap stops the server and the snapshot-holding session on every path out, including a `die` in the middle of a fixture and an interrupt, and then checks that no `postmaster.pid` and no process naming the data directory is left, failing the run if either is. It leaves the sandbox for inspection, and it touches a server only in a sandbox the run claimed as its own |
| Environment | `WIKI_ROOT` (`$PWD`), `SRC` (`$WIKI_ROOT/raw/postgres-17`), `SANDBOX` (`$WIKI_ROOT/.wiki-runtime/tmp/bloatplan`, and it must resolve to a directory directly inside `.wiki-runtime/tmp`), `PAGE` (this page under `$WIKI_ROOT`), `PORT` (`55437`), `JOBS` (`8`), `STATS_TARGET` (`10000`). The pin is a constant in the script, not a variable. The script sets two variables itself rather than reading them: `TMPDIR`, pointed at `$SANDBOX/tmp` for every stage that writes, so that `bash`'s here-document files and the build's temporary files stay in the sandbox, and `PG_REGRESS_SOCK_DIR`, pointed at `$SANDBOX/rs` for the regression suites, so that `pg_regress` does not create a socket directory under `/tmp` ([pg_regress.c#make_temp_sockdir](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L499-L525), [pg_regress.c#PG_REGRESS_SOCK_DIR](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L842-L849)). A `PGOPTIONS` in the caller's environment reaches no measurement session, because every session gets its options passed explicitly. The script also clears a caller's `PGSERVICE`, `PGSERVICEFILE` and `PGHOSTADDR`: libpq fills options from a service entry before it reads the environment ([fe-connect.c#conninfo_add_defaults](../../../../raw/postgres-17/src/interfaces/libpq/fe-connect.c#L6201-L6245)), so a service would override the exported `PGHOST`, `PGPORT`, `PGDATABASE` and `PGUSER`, and a host address would send sessions over TCP instead of to the sandbox socket ([fe-connect.c#pqConnectOptions2-host-type](../../../../raw/postgres-17/src/interfaces/libpq/fe-connect.c#L1189-L1204), [fe-connect.c#PQconnectPoll-host-address](../../../../raw/postgres-17/src/interfaces/libpq/fe-connect.c#L2754-L2764)) |
| Prerequisites | `bash` 3.2 or later (both macOS `/bin/bash` 3.2.57 and bash 5.3.15 ran the final text; see [Last run](#last-run)), `git`, a C toolchain, GNU `make` 3.81 or newer installed as `make` on `PATH` ([installation.sgml:40](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L40)), `flex`, `bison`, `perl` for the build, zlib headers, and `pgrep`, without which `stop` and `clean` refuse to report a clean teardown. The tree is configured `--without-icu --without-readline`, so neither library is needed. `initdb` runs with `--locale=C --encoding=UTF8`. `$SANDBOX` must contain no single quote, because the socket directory is passed to the server inside single quotes, and `$SANDBOX/sock/.s.PGSQL.$PORT`, like `$SANDBOX/rs/.s.PGSQL.` plus the regression suites' port, must be shorter than the platform's Unix-socket path buffer, which the server checks against `UNIXSOCK_PATH_BUFLEN` ([pqcomm.h:60](../../../../raw/postgres-17/src/include/libpq/pqcomm.h#L60), [pqcomm.c:453](../../../../raw/postgres-17/src/backend/libpq/pqcomm.c#L453)). About 3 GiB of disk for the build, install and data directories |
| Output | `$SANDBOX/out/summary.txt`: the B-tree index table, the GIN table, the prediction table, each fixture table's size and visibility state, the `fx` table of every other value the page quotes, one line per recorded plan with every node's index, costs, rows, width, workers, index condition, recheck condition and filter, then the platform facts, the four error messages and the two diagnostic outputs. Read it first. `server.log`, the build and test logs, the snapshot holders' logs, and the extracted `diag1.sql` and `diag2.sql` sit beside it |
| Runtime | about 2 minutes for a single full run on an idle 10-core machine, most of it the build and the four test suites; two runs side by side took 3 minutes 39 seconds each (see [Last run](#last-run)); a re-run of every fixture stage while the build is still present takes under a minute |
| Cleanup | `bash .wiki-runtime/tmp/bloatplan.sh clean` stops the server and deletes `$SANDBOX`, and refuses a directory that does not carry the script's `.bloatplan-sandbox` mark; then `rm -f .wiki-runtime/tmp/bloatplan.sh` deletes the extracted script. The `stop` stage, which runs by default, stops the server and asserts that `pg_ctl` finds no server and that no `postmaster.pid`, no process whose command line names the data directory (`pgrep -f -- "$DATA"`) and no socket on `$PORT` is left; it refuses to assert anything on a host without `pgrep`. Neither is the only safety net: the `EXIT` trap stops the server on any exit path and then checks for a leftover `postmaster.pid` or process, failing the run loudly if it finds one |

Extract the script from this page, from the repository root:

```sh
fence=$(printf '\140\140\140')
sed -n "/^${fence}bash\$/,/^${fence}\$/p" wiki/v17/questions/query-planning/bloated-indexes-query-planner.md | sed '1d;$d' > .wiki-runtime/tmp/bloatplan.sh
```

The first `sed` prints the page's only `bash` block with its two fence lines, and the second drops those lines. The fence is assembled with `printf` so that this block does not contain one.

Isolation: the pinned checkout is read only and checked against the pin before it is built, with `git --no-optional-locks status` so that the check never rewrites the checkout's index file, the build is out of tree, the cluster has its own data directory, socket directory and port `55437`, the libpq variables that could redirect a session elsewhere are cleared, and every fixture table is disposable. Stage `fstale` forges two `pg_class` rows on purpose, tagged `wiki_bloatplan_fixture_catalog_forgery`; they belong to a throwaway fixture and must never be pointed at a database anyone cares about. GUC apply scopes are named in the script's own header, from the pinned definitions: `shared_buffers`, `port`, `listen_addresses` and `unix_socket_directories` are `PGC_POSTMASTER`, so they need a restart and are set once on the postmaster command line ([guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270), [guc_tables.c#port](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2393-L2401), [guc_tables.c#listen_addresses](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4436-L4445), [guc_tables.c#unix_socket_directories](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4425-L4434)); `autovacuum` is `PGC_SIGHUP`, a reload setting, also set once there ([guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457)); every other setting the script touches is `PGC_USERSET`, session or transaction scope: `default_statistics_target`, the six `enable_*` switches, `effective_cache_size`, `random_page_cost`, `cpu_operator_cost`, the five parallel settings, `gin_pending_list_limit`, `statement_timeout`, `lock_timeout` and `application_name` ([guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2070-L2079), [guc_tables.c#enable_seqscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L783-L792), [guc_tables.c#enable_indexscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L793-L802), [guc_tables.c#enable_indexonlyscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L803-L812), [guc_tables.c#enable_bitmapscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L813-L822), [guc_tables.c#enable_mergejoin](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L893-L902), [guc_tables.c#enable_hashjoin](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L903-L912), [guc_tables.c#effective_cache_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3518), [guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696), [guc_tables.c#cpu_operator_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3719-L3729), [guc_tables.c#max_parallel_workers_per_gather](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3419-L3428), [guc_tables.c#max_parallel_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3430-L3439), [guc_tables.c#min_parallel_table_scan_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3520-L3529), [guc_tables.c#parallel_tuple_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3730-L3740), [guc_tables.c#parallel_setup_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3741-L3751), [guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585), [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631), [guc_tables.c#application_name](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4644-L4653)). Every `psql` call runs `-X` with session-scoped `statement_timeout` and `lock_timeout` and with `ON_ERROR_STOP`, including `grej`'s, whose four statements are meant to fail and each run alone. Every stage that writes points `TMPDIR` into the sandbox, and the regression suites keep their sockets in `$SANDBOX/rs`, so nothing is written outside `$SANDBOX` apart from the extracted script itself. The snapshot holder runs with the same options in the background; its 20-minute `statement_timeout` outlasts its 900-second sleep, and the script ends it after the churn and checks that exactly one live holder was ended. Every statement the script writes carries a `/* wiki_bloatplan_... */` tag after its leading verb, statements inside the recording helpers included; the two filed diagnostic blocks carry their own `/* wiki_gin_... */` tags.

### Last run

| Item | Value |
|---|---|
| Date | 2026-09-25, two full runs of the script text filed below, each from an empty sandbox of its own, started together after the page, the script and the two diagnostic blocks were final: one under Homebrew bash 5.3.15 (22:48:21Z to 22:52:00Z, port 55437) and one under macOS `/bin/bash` 3.2.57 (22:48:21Z to 22:52:00Z, `SANDBOX=.wiki-runtime/tmp/bloatplan32`, `PORT=55438`). An earlier text, which differed only in running `git status` without `--no-optional-locks`, had run as a pair twice that day from empty sandboxes (21:55:27Z to 21:59:19Z and 22:32:02Z to 22:35:51Z), with the same results |
| Server | `PostgreSQL 17.11 on aarch64-apple-darwin27.0.0, compiled by Apple clang version 21.0.0 (clang-2100.3.34.2), 64-bit`, built from pin `786db8dcf168bd9df8f55047337525ac19118b1c`, configured `--without-icu --without-readline`. The script's pin checks passed, and its platform record names the same commit for the pin, the install and the checkout |
| Platform | Darwin arm64, bash 5.3.15 and bash 3.2.57, `block_size` 8192, maximum data alignment 8, `initdb --locale=C --encoding=UTF8` |
| Test suites | in both runs, `make check` All 225 tests passed; `pgstattuple` All 1, `pageinspect` All 8, `btree_gin` All 30 |
| Agreement | the two runs wrote the same `summary.txt` apart from its run timestamps and the bash version line: 37 B-tree index rows, 11 GIN rows, 7 of 7 closed-form predictions equal to `EXPLAIN`, 29 fixture-table rows, 50 recorded facts, 146 plans, the four rejection messages and both diagnostic outputs. Every measured number on this page appears in that summary or is arithmetic on its values. `$SANDBOX/tmp` and `$SANDBOX/rs` were empty after both runs |
| Runtime | 3 minutes 39 seconds for each of the two runs side by side on 10 cores, most of it the two builds and test suites competing for the cores; the fixture stages took about 50 seconds |
| Failure handling, checked | Checked on this text before the final runs: `cluster bogus` was refused before anything was created; `WIKI_ROOT` set to the repository's `wiki` directory was refused before any directory was created; a run forced to fail inside stage `fa` (`STATS_TARGET=bogus`) stopped the server through the exit trap, left no `postmaster.pid`, no process naming the data directory and no socket, and exited 1. Earlier checks of the sandbox rules still apply to this text: a `SANDBOX` outside `.wiki-runtime/tmp`, one that leaves it through `..` or a symbolic link, and an existing non-empty unmarked directory are refused; `stop` and `clean` refuse any unmarked directory; `grej` without fixture S stops with status 1; `stop` without `pgrep` on `PATH` stops with status 1 |
| Teardown | after each run the `stop` stage asserted that `pg_ctl` found no server and that no `postmaster.pid`, no process naming the data directory and no socket on the run's port was left; the `clean` stage then stopped the server and deleted each sandbox, and the extracted script was deleted |

The published text was extracted from this page with the commands under [Usage](#usage) and compared byte for byte with the script text that ran; its md5 is `e6dae2e4df17eb0fbe013f11ebebfded`.

### The script

```bash
#!/usr/bin/env bash
# Measurements for the wiki page
#   wiki/v17/questions/query-planning/bloated-indexes-query-planner.md
#
# What this measures, and why it is safe to run
# ---------------------------------------------
# Every number that page reports about a running v17 server comes from this
# script.  It builds the pinned PostgreSQL 17 checkout out of tree, starts one
# isolated cluster, builds pairs of indexes that hold the same logical content
# in different physical shapes, and records what the planner charges for them:
# index block counts, pgstatindex density and fragmentation, the B-tree
# fast-root level, GIN metapage counters, and EXPLAIN costs.  Nothing is timed.
#
# The pinned checkout under raw/postgres-17 is read only, and the build and
# check stages refuse to run unless it is at $PIN with no tracked file changed;
# build records $PIN beside the binaries, and cluster, which every stage that
# has to start the server runs first, refuses an install built from anything
# else.  Everything this script writes lives under $SANDBOX, which must resolve
# to a directory directly inside this repository's .wiki-runtime/tmp.  Every
# stage that writes points TMPDIR at $SANDBOX/tmp, so bash's here-document
# files and the build's temporary files land there too, and check points the
# regression suites' socket directory at $SANDBOX/rs instead of a directory
# under /tmp.  The script marks the sandbox when it creates
# it, and stop and clean touch nothing that does not carry that mark.  The
# cluster has its own data directory, its own socket directory and a
# non-default port; it is never a cluster anyone else named.  Every fixture is
# disposable: the script creates and drops its own tables in its own database.
# Two statements forge pg_class rows on purpose (stage fstale); they are part
# of a disposable fixture and must never be pointed at a database anyone
# cares about.
#
# Usage, from the repository root:
#   bash .wiki-runtime/tmp/bloatplan.sh                # every stage, in order
#   bash .wiki-runtime/tmp/bloatplan.sh fa predict     # selected stages
#   bash .wiki-runtime/tmp/bloatplan.sh clean          # stop, delete the sandbox
#
# Stages, in default order:
#   build check cluster fa fb ff fg fh fi fn fstale fl3 fp fq fe
#   gs gd gt gp gb grej diag predict summary stop
# and, on request only: clean
#
# Results.  Index rows, GIN rows, predictions and plans go to the tables ix,
# gx, pr and r; every other value the page reports (catalog probes, metapage
# roots, estimate-against-truth counts, AM properties, the pending-list drain,
# the snapshot holder, the page charges of fixture Q, the dead entries of
# fixture E) goes to the table fx through fact().  The summary stage writes all
# five, with the platform facts, to $SANDBOX/out/summary.txt.
#
# Failure and teardown.  Every psql call that fails ends the run with a
# non-zero status.  pg(), pgq() and pgopt() call die themselves.  A psql call
# inside $(...) runs in a subshell, where die can only end the subshell, so
# every such call is followed by its own || die.  Two pipelines carry psql
# output, and pipefail hands psql's status to each: the platform record in
# cluster, which is checked the same way, and pgerr() in grej, whose
# statements are meant to fail, so grej first checks that fixture S exists and
# then requires psql's failed-statement status and the expected error text for
# each of its four statements.  Stage exit status is checked on top of
# that, and every stage name is checked before any stage runs, so a failed
# configure, make, make check or psql, or a misspelt stage, can never be
# reported as a pass.  An EXIT trap stops the server and the snapshot-holding
# session on every path out of the script, including a failure in the middle
# of a fixture and an interrupt, so no postmaster is left behind; the sandbox
# is kept for inspection unless the clean stage ran.  Every SQL stage starts
# the server if it is not up, so a selected re-run works after a default run
# has stopped the cluster; cluster starts it itself, and build, check, stop
# and clean never start one.
#
# Environment: WIKI_ROOT SRC SANDBOX PAGE PORT JOBS STATS_TARGET.  WIKI_ROOT
# must be this repository: the script checks for its AGENTS.md, wiki and raw
# before it creates anything.  The script sets TMPDIR and, for the regression
# suites, PG_REGRESS_SOCK_DIR itself.  It
# also clears three libpq variables a caller may have set, PGSERVICE,
# PGSERVICEFILE and PGHOSTADDR, because a service entry's values win over the
# exported PGHOST, PGPORT, PGDATABASE and PGUSER, and a host address sends a
# session over TCP instead of to the sandbox socket.  PGOPTIONS is never
# exported; every session gets its options passed explicitly.
#
# GUC apply scopes, from the pinned v17 guc_tables.c:
#   shared_buffers, port, listen_addresses, unix_socket_directories
#       -> PGC_POSTMASTER, restart.  Set once on the postmaster command line.
#   autovacuum -> PGC_SIGHUP, reload.  Set once on the postmaster command line.
#   default_statistics_target, enable_seqscan, enable_bitmapscan,
#   enable_indexscan, enable_indexonlyscan, enable_hashjoin, enable_mergejoin,
#   effective_cache_size,
#   random_page_cost, cpu_operator_cost,
#   max_parallel_workers_per_gather, max_parallel_workers,
#   min_parallel_table_scan_size, parallel_setup_cost, parallel_tuple_cost,
#   gin_pending_list_limit, statement_timeout, lock_timeout, application_name
#       -> PGC_USERSET, session or transaction scope, no reload and no restart.
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
SRC="${SRC:-$WIKI_ROOT/raw/postgres-17}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/bloatplan}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v17/questions/query-planning/bloated-indexes-query-planner.md}"
PORT="${PORT:-55437}"
JOBS="${JOBS:-8}"
# ANALYZE samples 300 * default_statistics_target rows.  At 10000 that is
# 3,000,000 rows, more than any fixture holds, so every ANALYZE reads every row
# and the statistics, and with them every row estimate and cost, are the same
# on every run.  The setting does not enter the cost model.
STATS_TARGET="${STATS_TARGET:-10000}"

# The commit the page pins.  build and check refuse a checkout at any other
# commit, and every later stage refuses binaries built from any other.
PIN=786db8dcf168bd9df8f55047337525ac19118b1c
# MARKER is the file claim_sandbox() writes into a sandbox this script created;
# PINFILE is the file build writes beside the binaries it installed.
MARKER=.bloatplan-sandbox
PINFILE=.bloatplan-pin
SANDBOX_OK=0

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# check_root: WIKI_ROOT must be this wiki repository, so that the sandbox, the
# checkout and the page all resolve inside it.  It runs before anything is
# created, so a run from the wrong directory creates nothing there.
check_root() {
  [ -f "$WIKI_ROOT/AGENTS.md" ] && [ -d "$WIKI_ROOT/wiki" ] && [ -d "$WIKI_ROOT/raw" ] \
    || die "WIKI_ROOT=$WIKI_ROOT is not the wiki repository: run from its root or set WIKI_ROOT"
}

# resolve_sandbox: turn $SANDBOX into its real path, and refuse one that is not
# a directory directly inside this repository's .wiki-runtime/tmp once .. and
# symbolic links are resolved.  It runs before any stage, and every path below
# is derived from its result, so pg_ctl, pgrep and rm all see the resolved path.
resolve_sandbox() {
  local tmp parent base real
  mkdir -p "$WIKI_ROOT/.wiki-runtime/tmp" || die "cannot create $WIKI_ROOT/.wiki-runtime/tmp"
  tmp=$(cd "$WIKI_ROOT/.wiki-runtime/tmp" && pwd -P) || die "cannot resolve $WIKI_ROOT/.wiki-runtime/tmp"
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

# setup_paths: runs once, after every stage name has been checked, so a
# misspelt stage or a wrong WIKI_ROOT creates nothing.  Every path the stages
# use is derived from the resolved sandbox.
setup_paths() {
  check_root
  resolve_sandbox
  BUILD="$SANDBOX/build"; INST="$SANDBOX/install"; DATA="$SANDBOX/data"
  SOCK="$SANDBOX/sock"; OUT="$SANDBOX/out"; BIN="$INST/bin"; DB=bloatplan
  # libpq applies a service entry before it reads PGHOST, PGPORT, PGDATABASE and
  # PGUSER, and a PGHOSTADDR sends the session over TCP to that address.  Either
  # one inherited from the caller could point every fixture statement, the
  # catalog forgery included, at a server nobody named, so both are cleared.
  unset PGSERVICE PGSERVICEFILE PGHOSTADDR
  export PGPORT="$PORT" PGHOST="$SOCK" PGDATABASE="$DB" PGUSER=postgres
}

# use_sandbox_tmp: point TMPDIR into the sandbox, so that bash's here-document
# files, the compiler's temporary files and anything else that honours TMPDIR
# stay under $SANDBOX.
use_sandbox_tmp() {
  mkdir -p "$SANDBOX/tmp" || die "cannot create $SANDBOX/tmp"
  export TMPDIR="$SANDBOX/tmp"
}

# check_pin: the build and the regression suites must come from exactly the
# commit the page records, with no tracked file changed.  Untracked files, such
# as a Finder .DS_Store, are not part of the build and are not checked.
check_pin() {
  local head dirty
  head=$(git -C "$SRC" rev-parse HEAD 2>/dev/null) || die "$SRC is not a git checkout"
  [ "$head" = "$PIN" ] || die "$SRC is at $head, not at the pinned $PIN"
  # --no-optional-locks keeps git status from refreshing the checkout's index
  # file, so the pinned checkout is never written to.
  dirty=$(git -C "$SRC" --no-optional-locks status --porcelain --untracked-files=no 2>/dev/null) \
    || die "git status failed in $SRC"
  [ -z "$dirty" ] || die "$SRC has changed tracked files, so a build would not be the pin"
}

# check_install_pin: the binaries under $INST were built from $PIN.
check_install_pin() {
  local built
  built=$(cat "$INST/$PINFILE" 2>/dev/null) || die "$INST has no build record: run the build stage"
  [ "$built" = "$PIN" ] || die "$INST was built from $built, not the pinned $PIN: run clean, then build"
}

# claim_sandbox: create $SANDBOX, or accept one this script created before, and
# mark it as this script's.  An existing directory that is not empty and
# carries no mark is refused.
claim_sandbox() {
  if [ -e "$SANDBOX" ] && [ ! -f "$SANDBOX/$MARKER" ] \
     && [ -n "$(ls -A "$SANDBOX" 2>/dev/null)" ]; then
    die "refusing sandbox $SANDBOX: it exists, is not empty, and this script did not create it"
  fi
  mkdir -p "$SANDBOX" && : > "$SANDBOX/$MARKER" || die "cannot create $SANDBOX"
  SANDBOX_OK=1
}

# own_sandbox: the check stop and clean make before they touch anything.  It
# returns 1 when there is no sandbox at all, and refuses one without the mark.
own_sandbox() {
  [ -d "$SANDBOX" ] || { note "no sandbox at $SANDBOX"; return 1; }
  [ -f "$SANDBOX/$MARKER" ] || die "refusing: $SANDBOX carries no $MARKER, so this script did not create it"
  SANDBOX_OK=1
}

# -X ignores ~/.psqlrc so a stray file cannot change a result; ON_ERROR_STOP
# means no failed statement passes silently.  The three settings are
# PGC_USERSET, so passing them through libpq applies them at session scope.
#
# pg() and pgq() abort the whole run when psql fails, rather than returning a
# status to a caller that may not look at it.  Without that, only the LAST
# command of a stage function set the stage's exit status, so a failed fixture
# build or a failed UPDATE round in the middle of a stage was invisible: the
# stage returned 0, run_stage saw 0, and the run reported a pass over numbers
# that were never produced.  Every psql call in this script is essential in
# exactly that sense.  Three calls do not go through these helpers: pgerr(),
# for the grej stage, which expects each of its statements to fail and checks
# the status and error text itself; the snapshot holder in hold_snapshot(),
# which runs in the background; and the two diagnostic blocks in stage_diag.
# All three carry the same -X, ON_ERROR_STOP and SESSION_OPTS.  The options
# are passed per call and never exported, so a
# PGOPTIONS in the caller's environment reaches no measurement session.
SESSION_OPTS="-c statement_timeout=20min -c lock_timeout=60s -c default_statistics_target=$STATS_TARGET"
CURRENT_STAGE=""
pg()    { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -v ON_ERROR_STOP=1 "$@" \
            || die "psql failed in stage ${CURRENT_STAGE:-<none>}: psql $*"; }
pgq()   { pg -At "$@"; }
# A psql invocation that has to override PGOPTIONS goes through this, so it
# aborts the run the same way pg() does.
pgopt() { local o="$1"; shift; PGOPTIONS="$SESSION_OPTS $o" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 "$@" \
            || die "psql failed in stage ${CURRENT_STAGE:-<none>} with PGOPTIONS $o: psql $*"; }
# pgerr runs one statement that must fail, for the grej stage.  psql runs with
# -X and ON_ERROR_STOP like every other call, reads the statement from stdin,
# and must exit with status 3, which psql returns when a script statement fails
# under ON_ERROR_STOP; its ERROR line must contain the expected text.  Any
# other status, including 0 for a statement that unexpectedly succeeds, or any
# other error text ends the run.
pgerr() {
  local sql="$1" want="$2" out st
  out=$(printf '%s\n' "$sql" | PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 2>&1)
  st=$?
  [ "$st" = 3 ] || die "expected psql status 3 from a statement that must fail, got $st: $sql: $out"
  printf '%s\n' "$out" | grep -E 'ERROR' >> "$OUT/grej.txt"
  case "$out" in
    *"ERROR:  $want"*) ;;
    *) die "expected the error \"$want\" from: $sql; got: $out" ;;
  esac
}

running() { [ -x "$BIN/pg_ctl" ] && "$BIN/pg_ctl" -D "$DATA" status >/dev/null 2>&1; }
stop_server() { running && "$BIN/pg_ctl" -D "$DATA" -m fast -w stop >/dev/null 2>&1; return 0; }

# Teardown on every path out of the script, not only on the stop stage: a die
# in the middle of a fixture, a failed psql, or an interrupt all land here, so
# no measurement postmaster and no snapshot holder survives the run.  The
# sandbox is left alone; only the clean stage deletes it.  The trap stops a
# server only in a sandbox this run claimed or verified as its own
# (SANDBOX_OK=1), so an exit caused by a refused sandbox stops nothing.
HOLDER_PID=""
on_exit() {
  local st=$?
  trap - EXIT INT TERM
  if [ "$SANDBOX_OK" = 1 ] && [ "$st" -ne 0 ] && running; then
    printf '!! exit status %s with the server still up; stopping it\n' "$st" >&2
  fi
  # Stopping the server first drops the holder session's connection, so its
  # pg_sleep ends and the background subshell exits on its own; the kill is only
  # there for the case where the shutdown could not reach it.
  [ "$SANDBOX_OK" = 1 ] && stop_server
  [ -n "$HOLDER_PID" ] && kill "$HOLDER_PID" 2>/dev/null
  wait 2>/dev/null
  # The stop above is checked, not assumed, on every path out: a postmaster.pid
  # or a process naming the data directory that survives it turns the run into
  # a failure and names the command that stops it.
  if [ "$SANDBOX_OK" = 1 ]; then
    if [ -f "$DATA/postmaster.pid" ] \
       || { command -v pgrep >/dev/null 2>&1 && pgrep -f -- "$DATA" >/dev/null 2>&1; }; then
      printf '!! teardown incomplete: a postmaster.pid or a process from %s is left; stop it with %s -D %s -m fast stop\n' \
        "$DATA" "$BIN/pg_ctl" "$DATA" >&2
      [ "$st" -ne 0 ] || st=1
    fi
  fi
  if [ "$st" -ne 0 ]; then
    if [ "$SANDBOX_OK" = 1 ] && [ -d "$SANDBOX" ]; then
      printf '!! failed with status %s; %s was kept\n' "$st" "$SANDBOX" >&2
    else
      printf '!! failed with status %s\n' "$st" >&2
    fi
  fi
  exit "$st"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Any stage that talks SQL needs a server.  stage_cluster is idempotent, so
# calling it again after a default run's stop stage just restarts the same data
# directory with the same recorded rows still in it.
need_server() {
  running && return 0
  [ -x "$BIN/pg_ctl" ] || die "no built server at $BIN: run the build stage first"
  stage_cluster || die "could not start the measurement server"
}

stage_build() {
  say "build: configure the pinned checkout out of tree, install core and three contrib modules"
  check_pin
  mkdir -p "$BUILD" "$OUT" "$SOCK" || die "cannot create the build directories under $SANDBOX"
  # The build record is written last, so it, not a postgres binary, is what
  # marks a finished build.  A build interrupted after the core install but
  # before the contrib installs or the record leaves binaries behind with no
  # record; that install is incomplete, so it is removed and built again.
  if [ -f "$INST/$PINFILE" ]; then
    check_install_pin
    [ -x "$BIN/postgres" ] || die "$INST has a build record but no postgres binary: run clean, then build"
    note "already built from $PIN: $("$BIN/postgres" --version)"; return 0
  fi
  if [ -e "$INST" ]; then
    note "removing the incomplete install at $INST, which has no build record"
    rm -rf "$INST" || die "cannot remove the incomplete install at $INST"
  fi
  [ -x "$SRC/configure" ] || die "no pinned checkout at $SRC"
  ( cd "$BUILD" && "$SRC/configure" --prefix="$INST" --without-icu --without-readline \
      > "$OUT/configure.log" 2>&1 ) || die "configure failed, see $OUT/configure.log"
  ( cd "$BUILD" && make -s -j "$JOBS" > "$OUT/make.log" 2>&1 \
      && make -s install > "$OUT/install.log" 2>&1 \
      && for m in pgstattuple pageinspect btree_gin; do
           make -s -C contrib/$m install >> "$OUT/install.log" 2>&1 || exit 1
         done ) || die "make failed, see $OUT/make.log"
  printf '%s\n' "$PIN" > "$INST/$PINFILE" || die "cannot record the build's pin in $INST"
  note "$("$BIN/postgres" --version), built from $PIN"
}

stage_check() {
  say "check: core regression suite, then the three contrib suites, on the built tree"
  check_pin
  check_install_pin
  # A failing suite is a failed stage.  Without the || die the subshell's status
  # is discarded and a run with four broken suites reports a pass.
  # pg_regress would otherwise put each temporary server's socket and lock
  # file in a new directory under $TMPDIR or /tmp, outside the sandbox;
  # PG_REGRESS_SOCK_DIR keeps them in $SANDBOX/rs, a path short enough for
  # the Unix-socket limit.
  local m rs="$SANDBOX/rs"
  mkdir -p "$rs" || die "cannot create $rs"
  ( cd "$BUILD" && PG_REGRESS_SOCK_DIR="$rs" make -s check > "$OUT/check.log" 2>&1 ) \
    || die "make check failed, see $OUT/check.log"
  note "core: $(grep -E 'tests passed|tests failed|failed' "$OUT/check.log" | tail -n 1)"
  for m in pgstattuple pageinspect btree_gin; do
    ( cd "$BUILD" && PG_REGRESS_SOCK_DIR="$rs" make -s -C contrib/$m check > "$OUT/check_$m.log" 2>&1 ) \
      || die "contrib/$m check failed, see $OUT/check_$m.log"
    note "$m: $(grep -E 'tests passed|tests failed|failed' "$OUT/check_$m.log" | tail -n 1)"
  done
}

stage_cluster() {
  say "cluster: initdb, start with autovacuum off, install contrib and the recording helpers"
  check_install_pin
  mkdir -p "$OUT" "$SOCK" || die "cannot create $OUT and $SOCK"
  [ -f "$DATA/PG_VERSION" ] || "$BIN/initdb" -D "$DATA" -U postgres --locale=C --encoding=UTF8 \
    > "$OUT/initdb.log" 2>&1 || die "initdb failed, see $OUT/initdb.log"
  running || "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w \
    -o "-p $PORT -k '$SOCK' -c listen_addresses='' -c autovacuum=off -c shared_buffers=256MB" start \
    >/dev/null 2>&1 || die "server did not start, see $OUT/server.log"
  local have
  have=$(PGDATABASE=postgres pgq -c "SELECT /* wiki_bloatplan_dbcheck */ count(*) FROM pg_database WHERE datname = '$DB'") \
    || die "could not read pg_database"
  [ "$have" = "1" ] || PGDATABASE=postgres pg -q -c "CREATE /* wiki_bloatplan_fixture */ DATABASE $DB"
  pg -q <<'SQL' || die "could not install the helpers"
CREATE /* wiki_bloatplan_fixture */ EXTENSION IF NOT EXISTS pgstattuple;
CREATE /* wiki_bloatplan_fixture */ EXTENSION IF NOT EXISTS pageinspect;
CREATE /* wiki_bloatplan_fixture */ EXTENSION IF NOT EXISTS btree_gin;
CREATE /* wiki_bloatplan_fixture */ TABLE IF NOT EXISTS r
  (seq serial, label text, top_node text, startup numeric, total numeric, plan_rows numeric, plan jsonb);
CREATE /* wiki_bloatplan_fixture */ TABLE IF NOT EXISTS ix
  (seq serial, label text, idx text, blocks bigint, tree_level int, fastlevel int, leaf_pages bigint,
   internal_pages bigint, empty_pages bigint, deleted_pages bigint, density float8, frag float8);
CREATE /* wiki_bloatplan_fixture */ TABLE IF NOT EXISTS gx
  (seq serial, label text, idx text, blocks bigint, pending_pages bigint, n_total bigint,
   n_entry bigint, n_data bigint, n_entries bigint);
CREATE /* wiki_bloatplan_fixture */ TABLE IF NOT EXISTS pr
  (seq serial, label text, pages float8, tuples float8, fastlevel float8, predicted text, observed text);
CREATE /* wiki_bloatplan_fixture */ TABLE IF NOT EXISTS fx
  (seq serial, label text, value text);

-- fact(): keep one value the page reports that is not an index row, a GIN
-- row, a prediction or a plan.  A later call under the same label replaces
-- the earlier one, so a re-run of a stage replaces its own facts.
CREATE OR REPLACE /* wiki_bloatplan_fixture */ FUNCTION fact(p_label text, p_value text)
RETURNS text LANGUAGE plpgsql AS $fn$
BEGIN
  DELETE /* wiki_bloatplan_record */ FROM fx WHERE label = p_label;
  INSERT /* wiki_bloatplan_record */ INTO fx(label, value) VALUES (p_label, p_value);
  RETURN p_label || ': ' || p_value;
END $fn$;

-- xp(): EXPLAIN one statement and keep the plan.  p_hide names an index that
-- is dropped inside a subtransaction which is always rolled back, so two
-- indexes on one table can each be priced alone on literally identical
-- statistics.  p_set entries are 'name=value' pairs of PGC_USERSET settings,
-- applied transaction-locally, so they end with the calling statement.
CREATE OR REPLACE /* wiki_bloatplan_fixture */ FUNCTION xp
  (p_label text, p_q text, p_hide text DEFAULT NULL, VARIADIC p_set text[] DEFAULT '{}'::text[])
RETURNS text LANGUAGE plpgsql AS $fn$
DECLARE j json; s text;
BEGIN
  FOREACH s IN ARRAY p_set LOOP
    PERFORM /* wiki_bloatplan_explain_setting */ set_config(split_part(s, '=', 1), split_part(s, '=', 2), true);
  END LOOP;
  IF p_hide IS NULL THEN
    EXECUTE 'EXPLAIN /* wiki_bloatplan_explain */ (FORMAT JSON) ' || p_q INTO j;
  ELSE
    BEGIN
      EXECUTE 'DROP /* wiki_bloatplan_fixture_rolled_back */ INDEX ' || p_hide;
      EXECUTE 'EXPLAIN /* wiki_bloatplan_explain */ (FORMAT JSON) ' || p_q INTO j;
      RAISE EXCEPTION 'undo' USING ERRCODE = 'P0099';
    EXCEPTION WHEN SQLSTATE 'P0099' THEN NULL;
    END;
  END IF;
  DELETE /* wiki_bloatplan_record */ FROM r WHERE label = p_label;
  INSERT /* wiki_bloatplan_record */ INTO r(label, top_node, startup, total, plan_rows, plan)
  VALUES (p_label, j->0->'Plan'->>'Node Type', (j->0->'Plan'->>'Startup Cost')::numeric,
          (j->0->'Plan'->>'Total Cost')::numeric, (j->0->'Plan'->>'Plan Rows')::numeric, j::jsonb);
  RETURN format('%s | %s', p_label, nodes(p_label));
END $fn$;

-- nodes(): one line per recorded plan, every node with its index, costs, rows,
-- width, workers, index condition, recheck condition and filter.
CREATE OR REPLACE /* wiki_bloatplan_fixture */ FUNCTION nodes(p_label text)
RETURNS text LANGUAGE sql AS $fn$
  SELECT /* wiki_bloatplan_record */ string_agg(
           (n->>'Node Type')
           || coalesce(' ' || (n->>'Index Name'), '')
           || ' ' || (n->>'Startup Cost') || '..' || (n->>'Total Cost')
           || ' rows=' || (n->>'Plan Rows')
           || ' width=' || (n->>'Plan Width')
           || coalesce(' workers=' || (n->>'Workers Planned'), '')
           || coalesce(' cond=' || (n->>'Index Cond'), '')
           || coalesce(' recheck=' || (n->>'Recheck Cond'), '')
           || coalesce(' filter=' || (n->>'Filter'), ''), ' ; ')
    FROM r, LATERAL jsonb_path_query(plan, 'strict $.** ? (exists(@."Node Type"))') AS n
   WHERE label = p_label
$fn$;

-- idxcost(): the total cost of the one Bitmap Index Scan node in a recorded
-- plan.  That node carries the index's own amcostestimate total and nothing
-- from the heap, so two plans at random_page_cost 4 and 1 differ there by
-- exactly 3.0 per index page the planner charged.
CREATE OR REPLACE /* wiki_bloatplan_fixture */ FUNCTION idxcost(p_label text)
RETURNS numeric LANGUAGE sql AS $fn$
  SELECT /* wiki_bloatplan_record */ (jsonb_path_query_first(plan,
           'strict $.** ? (@."Node Type" == "Bitmap Index Scan")') ->> 'Total Cost')::numeric
    FROM r WHERE label = p_label
$fn$;

-- ixstat(): block count, pgstatindex figures and the fast-root level of one B-tree.
CREATE OR REPLACE /* wiki_bloatplan_fixture */ FUNCTION ixstat(p_label text, p_idx regclass)
RETURNS text LANGUAGE plpgsql AS $fn$
DECLARE s record; m record; b bigint;
BEGIN
  SELECT /* wiki_bloatplan_record */ * INTO s FROM pgstatindex(p_idx);
  SELECT /* wiki_bloatplan_record */ * INTO m FROM bt_metap(p_idx::text);
  b := pg_relation_size(p_idx) / current_setting('block_size')::int;
  DELETE /* wiki_bloatplan_record */ FROM ix WHERE label = p_label;
  INSERT /* wiki_bloatplan_record */ INTO ix(label, idx, blocks, tree_level, fastlevel, leaf_pages, internal_pages, empty_pages,
                 deleted_pages, density, frag)
  VALUES (p_label, p_idx::text, b, s.tree_level, m.fastlevel, s.leaf_pages, s.internal_pages,
          s.empty_pages, s.deleted_pages, s.avg_leaf_density, s.leaf_fragmentation);
  RETURN format('%s | %s blocks=%s tree_level=%s fastlevel=%s leaf=%s internal=%s deleted=%s density=%s frag=%s',
                p_label, p_idx, b, s.tree_level, m.fastlevel, s.leaf_pages, s.internal_pages,
                s.deleted_pages, s.avg_leaf_density, s.leaf_fragmentation);
END $fn$;

-- ginstat(): block count, pending pages and the metapage counters of one GIN index.
CREATE OR REPLACE /* wiki_bloatplan_fixture */ FUNCTION ginstat(p_label text, p_idx regclass)
RETURNS text LANGUAGE plpgsql AS $fn$
DECLARE m record; g record; b bigint;
BEGIN
  SELECT /* wiki_bloatplan_record */ * INTO m FROM gin_metapage_info(get_raw_page(p_idx::text, 0));
  SELECT /* wiki_bloatplan_record */ * INTO g FROM pgstatginindex(p_idx);
  b := pg_relation_size(p_idx) / current_setting('block_size')::int;
  DELETE /* wiki_bloatplan_record */ FROM gx WHERE label = p_label;
  INSERT /* wiki_bloatplan_record */ INTO gx(label, idx, blocks, pending_pages, n_total, n_entry, n_data, n_entries)
  VALUES (p_label, p_idx::text, b, g.pending_pages, m.n_total_pages, m.n_entry_pages, m.n_data_pages, m.n_entries);
  RETURN format('%s | %s blocks=%s pending=%s meta(total,entry,data,entries)=(%s,%s,%s,%s)',
                p_label, p_idx, b, g.pending_pages, m.n_total_pages, m.n_entry_pages, m.n_data_pages, m.n_entries);
END $fn$;

-- predict(): the whole-index-scan cost of one B-tree, recomputed in float8 in
-- the planner's own order of operations from three inputs only: the index's
-- live block count, the planner's row estimate for the table, and the
-- fast-root level.  It is compared with the EXPLAIN total recorded under
-- p_label.  The index-only scan pays no heap cost because every fixture it is
-- used on is 100% all-visible.  The row estimate is the one
-- table_block_relation_estimate_size() makes: reltuples scaled from relpages
-- to the live heap block count, rounded with rint(), which is what SQL
-- round() does to a float8.  On every fixture predict() is used on, the table
-- was vacuumed just before, so the scaling changes nothing.
CREATE OR REPLACE /* wiki_bloatplan_fixture */ FUNCTION predict(p_label text, p_idx regclass, p_tbl regclass)
RETURNS text LANGUAGE plpgsql AS $fn$
DECLARE
  pages float8 := pg_relation_size(p_idx) / current_setting('block_size')::int;
  relp float8 := (SELECT /* wiki_bloatplan_record */ relpages FROM pg_class WHERE oid = p_tbl);
  relt float8 := (SELECT /* wiki_bloatplan_record */ reltuples FROM pg_class WHERE oid = p_tbl);
  curp float8 := pg_relation_size(p_tbl) / current_setting('block_size')::int;
  tuples float8;
  fl float8 := (SELECT /* wiki_bloatplan_record */ fastlevel FROM bt_metap(p_idx::text));
  rpc float8 := current_setting('random_page_cost')::float8;
  citc float8 := current_setting('cpu_index_tuple_cost')::float8;
  coc float8 := current_setting('cpu_operator_cost')::float8;
  ctc float8 := current_setting('cpu_tuple_cost')::float8;
  generic float8; d1 float8; d2 float8; startup float8; idx_total float8; total float8; obs text;
BEGIN
  tuples := CASE WHEN relp > 0 AND relt >= 0 THEN round(relt / relp * curp) ELSE relt END;
  generic := (pages * rpc) + tuples * (citc + coc * 1);   -- genericcostestimate, one index qual
  d1 := ceil(ln(tuples) / ln(2.0::float8)) * coc;         -- btcostestimate, log2(N) comparisons
  d2 := (fl + 1) * 50.0 * coc;                            -- btcostestimate, per-page descent charge
  startup := d1 + d2;
  idx_total := generic + d1 + d2;
  total := startup + ((idx_total - startup) + ctc * tuples);   -- cost_index
  SELECT /* wiki_bloatplan_record */ to_char(r.total, 'FM999999990.00') INTO obs FROM r WHERE label = p_label;
  DELETE /* wiki_bloatplan_record */ FROM pr WHERE label = p_label;
  INSERT /* wiki_bloatplan_record */ INTO pr(label, pages, tuples, fastlevel, predicted, observed)
  VALUES (p_label, pages, tuples, fl, to_char(total, 'FM999999990.00'), obs);
  RETURN format('%s | pages=%s tuples=%s fastlevel=%s predicted=%s observed=%s',
                p_label, pages, tuples, fl, to_char(total, 'FM999999990.00'), obs);
END $fn$;
SQL
  local head built
  head=$(git -C "$SRC" rev-parse HEAD 2>/dev/null) || die "cannot read HEAD from $SRC"
  built=$(cat "$INST/$PINFILE") || die "cannot read the build record in $INST"
  {
    date -u '+run started %Y-%m-%dT%H:%M:%SZ'
    uname -sm
    echo "bash $BASH_VERSION"
    pgq -c "SELECT /* wiki_bloatplan_version */ version()"
    echo "pin $PIN; install built from $built; checkout HEAD $head"
    "$BIN/pg_controldata" "$DATA" | grep -E 'Database block size|Maximum data alignment' \
      || die "pg_controldata did not report the block size and the maximum alignment"
    pgq -c "SELECT /* wiki_bloatplan_settings */ name || ' = ' || setting FROM pg_settings WHERE name IN ('autovacuum','shared_buffers','random_page_cost','seq_page_cost','cpu_tuple_cost','cpu_index_tuple_cost','cpu_operator_cost','effective_cache_size','min_parallel_index_scan_size','default_statistics_target','gin_pending_list_limit') ORDER BY 1"
  } | tee "$OUT/platform.txt" || die "could not record the platform facts"
}

# Settings that force an index or index-only scan so that one named index is
# priced, not chosen.  Both are PGC_USERSET and last for one statement.
IOS="'enable_seqscan=off','enable_bitmapscan=off'"
PAR="'max_parallel_workers_per_gather=8','max_parallel_workers=8','min_parallel_table_scan_size=0','enable_seqscan=off','enable_bitmapscan=off'"
PAR0="$PAR,'parallel_setup_cost=0','parallel_tuple_cost=0'"
# A nested loop with the fixture index on the inner side, so that the scan is
# repeated and index_pages_fetched() prices the index pages through the cache model.
NL="'enable_hashjoin=off','enable_mergejoin=off','max_parallel_workers_per_gather=0'"
# A bitmap scan, so that the Bitmap Index Scan node carries the index's own
# cost with no heap component (fixture Q).  All three are PGC_USERSET.
BMP="'enable_seqscan=off','enable_indexscan=off','enable_indexonlyscan=off'"

stage_fa() {
  say "fa: fixture A, 1,000,000 rows, a default index against a fillfactor = 10 twin"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS a_dense, a_sparse, a_outer;
CREATE /* wiki_bloatplan_fixture */ TABLE a_outer  (id int NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO a_outer SELECT g * 20 FROM generate_series(1, 50000) g;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) a_outer;
CREATE /* wiki_bloatplan_fixture */ TABLE a_dense  (id int NOT NULL, pad text NOT NULL);
CREATE /* wiki_bloatplan_fixture */ TABLE a_sparse (id int NOT NULL, pad text NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO a_dense  SELECT g, repeat('x', 24) FROM generate_series(1, 1000000) g;
INSERT /* wiki_bloatplan_fixture */ INTO a_sparse SELECT g, repeat('x', 24) FROM generate_series(1, 1000000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX a_dense_idx  ON a_dense  (id);
CREATE /* wiki_bloatplan_fixture */ INDEX a_sparse_idx ON a_sparse (id) WITH (fillfactor = 10);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) a_dense;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) a_sparse;
SQL
  pgq <<SQL
SELECT /* wiki_bloatplan_heap */ 'heap ' || relname || ' pages=' || relpages || ' allvisible=' || relallvisible FROM pg_class WHERE relname IN ('a_dense','a_sparse') ORDER BY 1;
SELECT /* wiki_bloatplan_record */ ixstat('A dense', 'a_dense_idx');
SELECT /* wiki_bloatplan_record */ ixstat('A sparse', 'a_sparse_idx');
SELECT /* wiki_bloatplan_record */ xp('A dense full',   'SELECT id FROM a_dense  WHERE id > 0', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('A sparse full',  'SELECT id FROM a_sparse WHERE id > 0', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('A dense point',  'SELECT id FROM a_dense  WHERE id = 42', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('A sparse point', 'SELECT id FROM a_sparse WHERE id = 42', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('A dense 10pct',  'SELECT id FROM a_dense  WHERE id BETWEEN 1 AND 100000', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('A sparse 10pct', 'SELECT id FROM a_sparse WHERE id BETWEEN 1 AND 100000', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('A dense flip25',  'SELECT pad FROM a_dense  WHERE id BETWEEN 1 AND 250000');
SELECT /* wiki_bloatplan_record */ xp('A sparse flip25', 'SELECT pad FROM a_sparse WHERE id BETWEEN 1 AND 250000');
SELECT /* wiki_bloatplan_record */ xp('A dense flip12',  'SELECT pad FROM a_dense  WHERE id BETWEEN 1 AND 120000');
SELECT /* wiki_bloatplan_record */ xp('A sparse flip12', 'SELECT pad FROM a_sparse WHERE id BETWEEN 1 AND 120000');
SELECT /* wiki_bloatplan_record */ xp('A dense parallel',  'SELECT count(id) FROM a_dense  WHERE id > 0', NULL, $PAR);
SELECT /* wiki_bloatplan_record */ xp('A sparse parallel', 'SELECT count(id) FROM a_sparse WHERE id > 0', NULL, $PAR);
SELECT /* wiki_bloatplan_record */ xp('A dense parallel 50pct',  'SELECT count(id) FROM a_dense  WHERE id BETWEEN 1 AND 500000', NULL, $PAR);
SELECT /* wiki_bloatplan_record */ xp('A dense parallel 20pct',  'SELECT count(id) FROM a_dense  WHERE id BETWEEN 1 AND 200000', NULL, $PAR);
SELECT /* wiki_bloatplan_record */ xp('A sparse parallel 50pct', 'SELECT count(id) FROM a_sparse WHERE id BETWEEN 1 AND 500000', NULL, $PAR);
SELECT /* wiki_bloatplan_record */ xp('A sparse parallel 20pct', 'SELECT count(id) FROM a_sparse WHERE id BETWEEN 1 AND 200000', NULL, $PAR);
SELECT /* wiki_bloatplan_record */ xp('A dense par0 100pct',  'SELECT count(id) FROM a_dense  WHERE id > 0', NULL, $PAR0);
SELECT /* wiki_bloatplan_record */ xp('A dense par0 50pct',   'SELECT count(id) FROM a_dense  WHERE id BETWEEN 1 AND 500000', NULL, $PAR0);
SELECT /* wiki_bloatplan_record */ xp('A dense par0 20pct',   'SELECT count(id) FROM a_dense  WHERE id BETWEEN 1 AND 200000', NULL, $PAR0);
SELECT /* wiki_bloatplan_record */ xp('A sparse par0 100pct', 'SELECT count(id) FROM a_sparse WHERE id > 0', NULL, $PAR0);
SELECT /* wiki_bloatplan_record */ xp('A sparse par0 50pct',  'SELECT count(id) FROM a_sparse WHERE id BETWEEN 1 AND 500000', NULL, $PAR0);
SELECT /* wiki_bloatplan_record */ xp('A sparse par0 20pct',  'SELECT count(id) FROM a_sparse WHERE id BETWEEN 1 AND 200000', NULL, $PAR0);
SELECT /* wiki_bloatplan_record */ xp('A dense nestloop',        'SELECT count(*) FROM a_outer o JOIN a_dense  d ON d.id = o.id', NULL, $NL);
SELECT /* wiki_bloatplan_record */ xp('A sparse nestloop',       'SELECT count(*) FROM a_outer o JOIN a_sparse d ON d.id = o.id', NULL, $NL);
SELECT /* wiki_bloatplan_record */ xp('A dense nestloop ecs64',  'SELECT count(*) FROM a_outer o JOIN a_dense  d ON d.id = o.id', NULL, $NL, 'effective_cache_size=64MB');
SELECT /* wiki_bloatplan_record */ xp('A sparse nestloop ecs64', 'SELECT count(*) FROM a_outer o JOIN a_sparse d ON d.id = o.id', NULL, $NL, 'effective_cache_size=64MB');
SQL
}

stage_fb() {
  say "fb: fixtures B (scattered 90% delete) and M (contiguous 90% delete)"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS b_scat, m_cont;
CREATE /* wiki_bloatplan_fixture */ TABLE b_scat (id int NOT NULL, pad text NOT NULL);
CREATE /* wiki_bloatplan_fixture */ TABLE m_cont (id int NOT NULL, pad text NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO b_scat SELECT g, repeat('x', 24) FROM generate_series(1, 1000000) g;
INSERT /* wiki_bloatplan_fixture */ INTO m_cont SELECT g, repeat('x', 24) FROM generate_series(1, 1000000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX b_scat_idx ON b_scat (id);
CREATE /* wiki_bloatplan_fixture */ INDEX m_cont_idx ON m_cont (id);
DELETE /* wiki_bloatplan_fixture */ FROM b_scat WHERE id % 10 <> 0;
DELETE /* wiki_bloatplan_fixture */ FROM m_cont WHERE id > 100000;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) b_scat;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) b_scat;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) m_cont;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) m_cont;
SQL
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ixstat('B before', 'b_scat_idx');
SELECT /* wiki_bloatplan_record */ ixstat('M before', 'm_cont_idx');
SELECT /* wiki_bloatplan_record */ xp('B before full',  'SELECT id FROM b_scat WHERE id > 0', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('M before full',  'SELECT id FROM m_cont WHERE id > 0', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('B before point', 'SELECT id FROM b_scat WHERE id = 50000', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('M before point', 'SELECT id FROM m_cont WHERE id = 50000', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ predict('B before full', 'b_scat_idx', 'b_scat');
SELECT /* wiki_bloatplan_record */ predict('M before full', 'm_cont_idx', 'm_cont');
SQL
  pg -q -c "VACUUM /* wiki_bloatplan_fixture */ m_cont"
  pgq -c "SELECT /* wiki_bloatplan_record */ ixstat('M third vacuum', 'm_cont_idx')"
  pg -q -c "REINDEX /* wiki_bloatplan_fixture */ INDEX b_scat_idx" -c "REINDEX /* wiki_bloatplan_fixture */ INDEX m_cont_idx"
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ixstat('B after', 'b_scat_idx');
SELECT /* wiki_bloatplan_record */ ixstat('M after', 'm_cont_idx');
SELECT /* wiki_bloatplan_record */ xp('B after full',  'SELECT id FROM b_scat WHERE id > 0', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('M after full',  'SELECT id FROM m_cont WHERE id > 0', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('B after point', 'SELECT id FROM b_scat WHERE id = 50000', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ predict('B after full', 'b_scat_idx', 'b_scat');
SQL
}

stage_ff() {
  say "ff: fixture F, the fast root moves down without a rebuild, and pages outnumber rows"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS f_root;
CREATE /* wiki_bloatplan_fixture */ TABLE f_root (id int NOT NULL, pad text NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO f_root SELECT g, repeat('x', 24) FROM generate_series(1, 1000000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX f_root_idx ON f_root (id);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) f_root;
SQL
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ixstat('F built', 'f_root_idx');
SELECT /* wiki_bloatplan_record */ xp('F built point', 'SELECT id FROM f_root WHERE id = 999950', NULL, $IOS);
SQL
  pg -q <<'SQL'
DELETE /* wiki_bloatplan_fixture */ FROM f_root WHERE id <= 999000;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) f_root;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) f_root;
SQL
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ixstat('F deleted', 'f_root_idx');
SELECT /* wiki_bloatplan_record */ fact('F deleted metapage', 'root=' || root || ' level=' || level || ' fastroot=' || fastroot || ' fastlevel=' || fastlevel) FROM bt_metap('f_root_idx');
SELECT /* wiki_bloatplan_record */ xp('F deleted point', 'SELECT id FROM f_root WHERE id = 999950', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('F deleted full',  'SELECT id FROM f_root WHERE id > 0', NULL, $IOS);
SQL
  pg -q -c "REINDEX /* wiki_bloatplan_fixture */ INDEX f_root_idx"
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ixstat('F rebuilt', 'f_root_idx');
SELECT /* wiki_bloatplan_record */ xp('F rebuilt point', 'SELECT id FROM f_root WHERE id = 999950', NULL, $IOS);
SQL
  # The other end of the same guard.  genericcostestimate() prorates pages only
  # when index->pages > 1 AND index->tuples > 1; otherwise the estimate is a
  # flat one page.  For a non-partial index tuples is the TABLE's row estimate,
  # so a table down to one surviving row prices a scan of an index of any size
  # at a single page.  f_one keeps its 200,000-row index and loses all but one
  # row.
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS f_one;
CREATE /* wiki_bloatplan_fixture */ TABLE f_one (id int NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO f_one SELECT g FROM generate_series(1, 200000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX f_one_idx ON f_one (id);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) f_one;
SQL
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ixstat('F one before', 'f_one_idx');
SELECT /* wiki_bloatplan_record */ fact('F one catalog before', 'relpages=' || relpages || ' reltuples=' || reltuples) FROM pg_class WHERE relname = 'f_one';
SELECT /* wiki_bloatplan_record */ xp('F one before full', 'SELECT id FROM f_one WHERE id > 0', NULL, $IOS);
SQL
  pg -q <<'SQL'
DELETE /* wiki_bloatplan_fixture */ FROM f_one WHERE id < 200000;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) f_one;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) f_one;
SQL
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ixstat('F one after', 'f_one_idx');
SELECT /* wiki_bloatplan_record */ fact('F one catalog after', 'relpages=' || relpages || ' reltuples=' || reltuples) FROM pg_class WHERE relname = 'f_one';
SELECT /* wiki_bloatplan_record */ xp('F one after full',  'SELECT id FROM f_one WHERE id > 0', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('F one after point', 'SELECT id FROM f_one WHERE id = 200000', NULL, $IOS);
SQL
}

stage_fg() {
  say "fg: fixture G, a fillfactor = 100 build against seeded random-order inserts"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS g_seq, g_frag;
CREATE /* wiki_bloatplan_fixture */ TABLE g_seq  (id int NOT NULL);
CREATE /* wiki_bloatplan_fixture */ TABLE g_frag (id int NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO g_seq SELECT g FROM generate_series(1, 300000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX g_seq_idx  ON g_seq  (id) WITH (fillfactor = 100);
CREATE /* wiki_bloatplan_fixture */ INDEX g_frag_idx ON g_frag (id);
SELECT /* wiki_bloatplan_fixture */ setseed(0.42);
INSERT /* wiki_bloatplan_fixture */ INTO g_frag SELECT g FROM generate_series(1, 300000) g ORDER BY random();
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) g_seq;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) g_frag;
SQL
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ixstat('G seq', 'g_seq_idx');
SELECT /* wiki_bloatplan_record */ ixstat('G frag', 'g_frag_idx');
SELECT /* wiki_bloatplan_record */ xp('G seq full',  'SELECT id FROM g_seq  WHERE id > 0', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('G frag full', 'SELECT id FROM g_frag WHERE id > 0', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ predict('G seq full',  'g_seq_idx',  'g_seq');
SELECT /* wiki_bloatplan_record */ predict('G frag full', 'g_frag_idx', 'g_frag');
SQL
}

stage_fh() {
  say "fh: fixture H, 50,000 rows, a one-level tree against a two-level tree"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS h_l1, h_l2;
CREATE /* wiki_bloatplan_fixture */ TABLE h_l1 (id int NOT NULL, pad text NOT NULL);
CREATE /* wiki_bloatplan_fixture */ TABLE h_l2 (id int NOT NULL, pad text NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO h_l1 SELECT g, repeat('x', 24) FROM generate_series(1, 50000) g;
INSERT /* wiki_bloatplan_fixture */ INTO h_l2 SELECT g, repeat('x', 24) FROM generate_series(1, 50000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX h_l1_idx ON h_l1 (id);
CREATE /* wiki_bloatplan_fixture */ INDEX h_l2_idx ON h_l2 (id) WITH (fillfactor = 10);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) h_l1;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) h_l2;
SQL
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ixstat('H l1', 'h_l1_idx');
SELECT /* wiki_bloatplan_record */ ixstat('H l2', 'h_l2_idx');
SELECT /* wiki_bloatplan_record */ xp('H l1 point', 'SELECT * FROM h_l1 WHERE id = 25000', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('H l2 point', 'SELECT * FROM h_l2 WHERE id = 25000', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('H l1 point opcost1', 'SELECT * FROM h_l1 WHERE id = 25000', NULL, 'cpu_operator_cost=1', $IOS);
SELECT /* wiki_bloatplan_record */ xp('H l2 point opcost1', 'SELECT * FROM h_l2 WHERE id = 25000', NULL, 'cpu_operator_cost=1', $IOS);
SQL
}

stage_fi() {
  say "fi: fixture I, 2,000 rows, the v17 ScalarArrayOp descent clamp"
  # The two tables are analyzed but never vacuumed, so relallvisible is 0 and
  # the index-only scan is charged heap access exactly as a plain index scan
  # would be.  With the heap in key order that is one random heap page (4.0)
  # at every array length, plus cpu_tuple_cost for each row, the same for both
  # indexes.
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS i_small, i_big;
CREATE /* wiki_bloatplan_fixture */ TABLE i_small (id int NOT NULL);
CREATE /* wiki_bloatplan_fixture */ TABLE i_big   (id int NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO i_small SELECT g FROM generate_series(1, 2000) g;
INSERT /* wiki_bloatplan_fixture */ INTO i_big   SELECT g FROM generate_series(1, 2000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX i_small_idx ON i_small (id);
CREATE /* wiki_bloatplan_fixture */ INDEX i_big_idx   ON i_big   (id) WITH (fillfactor = 10);
ANALYZE /* wiki_bloatplan_fixture */ i_small;
ANALYZE /* wiki_bloatplan_fixture */ i_big;
SQL
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ ixstat('I small', 'i_small_idx');
SELECT /* wiki_bloatplan_record */ ixstat('I big', 'i_big_idx');
SELECT /* wiki_bloatplan_heap */ 'heap ' || relname || ' pages=' || relpages || ' allvisible=' || relallvisible FROM pg_class WHERE relname IN ('i_small','i_big') ORDER BY 1;
SQL
  local n arr
  for n in 1 2 3 4 6 10; do
    arr=$(pgq -c "SELECT /* wiki_bloatplan_array */ '{' || string_agg((g * 150)::text, ',') || '}' FROM generate_series(1, $n) g") \
      || die "could not build the $n-element array"
    pgq <<SQL
SELECT /* wiki_bloatplan_record */ xp('I small saop $n', \$q\$SELECT * FROM i_small WHERE id = ANY ('$arr'::int[])\$q\$, NULL, 'cpu_operator_cost=1', $IOS);
SELECT /* wiki_bloatplan_record */ xp('I big saop $n',   \$q\$SELECT * FROM i_big   WHERE id = ANY ('$arr'::int[])\$q\$, NULL, 'cpu_operator_cost=1', $IOS);
SQL
  done
}

stage_fn() {
  say "fn: fixture N, 1,000,000 rows over 100 keys, deduplicate_items on against off"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS n_t;
CREATE /* wiki_bloatplan_fixture */ TABLE n_t (k int NOT NULL, pad text NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO n_t SELECT g % 100, repeat('x', 24) FROM generate_series(1, 1000000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX n_on  ON n_t (k);
CREATE /* wiki_bloatplan_fixture */ INDEX n_off ON n_t (k) WITH (deduplicate_items = off);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) n_t;
SQL
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ixstat('N on', 'n_on');
SELECT /* wiki_bloatplan_record */ ixstat('N off', 'n_off');
SELECT /* wiki_bloatplan_record */ xp('N on k=5',  'SELECT * FROM n_t WHERE k = 5', 'n_off', $IOS);
SELECT /* wiki_bloatplan_record */ xp('N off k=5', 'SELECT * FROM n_t WHERE k = 5', 'n_on',  $IOS);
SELECT /* wiki_bloatplan_record */ xp('N on k>0',  'SELECT * FROM n_t WHERE k > 0', 'n_off', $IOS);
SELECT /* wiki_bloatplan_record */ xp('N off k>0', 'SELECT * FROM n_t WHERE k > 0', 'n_on',  $IOS);
SQL
}

stage_fstale() {
  say "fstale: a forged pg_class.relpages on a plain index, a forged reltuples on a partial one"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS b_stale, b_part;
CREATE /* wiki_bloatplan_fixture */ TABLE b_stale (id int NOT NULL);
CREATE /* wiki_bloatplan_fixture */ TABLE b_part  (id int NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO b_stale SELECT g FROM generate_series(1, 200000) g;
INSERT /* wiki_bloatplan_fixture */ INTO b_part  SELECT g FROM generate_series(1, 200000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX b_stale_idx ON b_stale (id) WITH (fillfactor = 10);
CREATE /* wiki_bloatplan_fixture */ INDEX b_part_idx  ON b_part  (id) WITH (fillfactor = 10) WHERE id > 0;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) b_stale;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) b_part;
SQL
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ixstat('stale plain', 'b_stale_idx');
SELECT /* wiki_bloatplan_record */ ixstat('stale partial', 'b_part_idx');
SELECT /* wiki_bloatplan_record */ xp('stale plain honest',   'SELECT id FROM b_stale WHERE id > 0', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('stale partial honest', 'SELECT id FROM b_part  WHERE id > 0', NULL, $IOS);
SQL
  # Disposable-fixture catalog forgery.  Never run this against a real database.
  pg -q -c "UPDATE /* wiki_bloatplan_fixture_catalog_forgery */ pg_class SET relpages = 1 WHERE relname = 'b_stale_idx'" \
        -c "UPDATE /* wiki_bloatplan_fixture_catalog_forgery */ pg_class SET reltuples = 20 WHERE relname = 'b_part_idx'"
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ fact('forged catalog ' || relname, 'relpages=' || relpages || ' reltuples=' || reltuples || ' live blocks=' || pg_relation_size(oid) / current_setting('block_size')::int) FROM pg_class WHERE relname IN ('b_stale_idx','b_part_idx') ORDER BY relname;
SELECT /* wiki_bloatplan_record */ xp('stale plain forged',   'SELECT id FROM b_stale WHERE id > 0', NULL, $IOS);
SELECT /* wiki_bloatplan_record */ xp('stale partial forged', 'SELECT id FROM b_part  WHERE id > 0', NULL, $IOS);
SQL
}

stage_fl3() {
  say "fl3: a bloated index dropped from a BitmapAnd, over two independent columns"
  # c is drawn from a seeded PRNG instead of being derived from g, so a and c
  # are independent of each other and a = 5 AND c = 7 is a combination that
  # exists.  setseed makes the draw reproducible, as it does for fixture G.
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS l3;
CREATE /* wiki_bloatplan_fixture */ TABLE l3 (a int NOT NULL, c int NOT NULL, pad text NOT NULL);
SELECT /* wiki_bloatplan_fixture */ setseed(0.42);
INSERT /* wiki_bloatplan_fixture */ INTO l3
  SELECT g % 2000, floor(random() * 20)::int, repeat('x', 24) FROM generate_series(1, 500000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX l3_a ON l3 (a);
CREATE /* wiki_bloatplan_fixture */ INDEX l3_c ON l3 (c);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) l3;
SQL
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ ixstat('l3 a', 'l3_a');
SELECT /* wiki_bloatplan_record */ ixstat('l3 c healthy', 'l3_c');
SELECT /* wiki_bloatplan_record */ xp('l3 healthy', 'SELECT pad FROM l3 WHERE a = 5 AND c = 7');
SELECT /* wiki_bloatplan_record */ xp('l3 a only',  'SELECT pad FROM l3 WHERE a = 5');
SELECT /* wiki_bloatplan_record */ xp('l3 c only',  'SELECT pad FROM l3 WHERE c = 7');
SQL
  pg -q -c "ALTER /* wiki_bloatplan_fixture */ INDEX l3_c SET (fillfactor = 10)" -c "REINDEX /* wiki_bloatplan_fixture */ INDEX l3_c"
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ ixstat('l3 c bloated', 'l3_c');
SELECT /* wiki_bloatplan_record */ xp('l3 bloated', 'SELECT pad FROM l3 WHERE a = 5 AND c = 7');
-- Exact statistics are not exact estimates.  Both columns are analyzed
-- exhaustively here, and the conjunction is still estimated by multiplying two
-- per-clause selectivities, so record each estimate beside the true count and
-- let the page report the gap rather than assert there is none.  c is a
-- random draw, so even with independent columns the true count of the
-- conjunction is itself random; only its expectation equals the product.
SELECT /* wiki_bloatplan_record */ fact('l3 actual rows', 'a=5 AND c=7 = ' || count(*) FILTER (WHERE a = 5 AND c = 7)
       || ', a=5 = ' || count(*) FILTER (WHERE a = 5)
       || ', c=7 = ' || count(*) FILTER (WHERE c = 7)
       || ', total = ' || count(*)) FROM l3;
SELECT /* wiki_bloatplan_record */ fact('l3 estimated rows', string_agg(label || ' = ' || plan_rows, ', ' ORDER BY seq))
  FROM r WHERE label IN ('l3 healthy', 'l3 a only', 'l3 c only', 'l3 bloated');
SQL
}

churn() {  # churn <table>: five whole-table non-HOT UPDATE rounds, one transaction each
  local t="$1" i
  for i in 1 2 3 4 5; do
    pg -q -c "UPDATE /* wiki_bloatplan_fixture_churn */ $t SET payload = payload + 1"
  done
}

hold_snapshot() {  # hold_snapshot <table>: REPEATABLE READ snapshot in a second session
  local t="$1" tries=0 n
  # The holder runs in the background with the same -X, ON_ERROR_STOP and
  # SESSION_OPTS as every other session.  Its 20-minute statement_timeout
  # outlasts the 900-second sleep, and release_snapshot() ends it long before.
  ( PGAPPNAME=bloatplan_holder PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 \
      -c "BEGIN /* wiki_bloatplan_fixture_holder */ ISOLATION LEVEL REPEATABLE READ" \
      -c "SELECT /* wiki_bloatplan_fixture_holder */ count(*) FROM $t" \
      -c "SELECT /* wiki_bloatplan_fixture_holder */ pg_sleep(900)" > "$OUT/holder_$t.log" 2>&1 ) &
  HOLDER_PID=$!
  while :; do
    n=$(pgq -c "SELECT /* wiki_bloatplan_holder_probe */ count(*) FROM pg_stat_activity WHERE application_name = 'bloatplan_holder' AND backend_xmin IS NOT NULL") \
      || die "the holder probe failed"
    [ "$n" = "1" ] && break
    tries=$((tries + 1)); [ "$tries" -gt 60 ] && die "the holder session never took its snapshot"
    sleep 1
  done
  # The xmin itself is a transaction id that moves with every run, so the
  # fact records only that the holder has one, which keeps summary.txt
  # identical between runs.
  pgq -c "SELECT /* wiki_bloatplan_record */ fact('holder $t', 'snapshot held, backend_xmin ' || CASE WHEN backend_xmin IS NULL THEN 'not set' ELSE 'set' END) FROM pg_stat_activity WHERE application_name = 'bloatplan_holder'"
}

release_snapshot() {  # release_snapshot <table>: end the holder, which must still be alive
  local t="$1" ended n
  # A holder that died during the churn would have released its snapshot
  # early, so exactly one live session must be ended here.  The 10-second
  # timeout makes pg_terminate_backend() wait until the backend has exited.
  ended=$(pgq -c "SELECT /* wiki_bloatplan_holder_release */ count(*) FILTER (WHERE pg_terminate_backend(pid, 10000)) FROM pg_stat_activity WHERE application_name = 'bloatplan_holder'") \
    || die "the holder release failed"
  [ "$ended" = "1" ] || die "expected to end exactly one live holder session after the churn, ended $ended"
  pgq -c "SELECT /* wiki_bloatplan_record */ fact('holder $t ended', 'sessions ended after the churn=$ended')"
  wait 2>/dev/null
  HOLDER_PID=""
  n=$(pgq -c "SELECT /* wiki_bloatplan_holder_probe */ count(*) FROM pg_stat_activity WHERE application_name = 'bloatplan_holder'") \
    || die "the holder probe failed"
  [ "$n" = "0" ] || die "the holder session is still connected"
}

stage_fp() {
  say "fp: fixture P, version churn at 1,000 and at 100 tag values, with and without a held snapshot"
  local mod t
  for mod in 1000 100; do
    for t in p${mod}_free p${mod}_held; do
      pg -q <<SQL
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS $t;
CREATE /* wiki_bloatplan_fixture */ TABLE $t (id int NOT NULL, payload int NOT NULL, tag int NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO $t SELECT g, g, g % $mod FROM generate_series(1, 200000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX ${t}_payload ON $t (payload);
CREATE /* wiki_bloatplan_fixture */ INDEX ${t}_tag     ON $t (tag);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) $t;
SQL
    done
    pgq -c "SELECT /* wiki_bloatplan_record */ ixstat('P$mod free start', 'p${mod}_free_tag')" \
        -c "SELECT /* wiki_bloatplan_record */ ixstat('P$mod held start', 'p${mod}_held_tag')"
    churn p${mod}_free
    pgq -c "SELECT /* wiki_bloatplan_record */ ixstat('P$mod free end', 'p${mod}_free_tag')"
    hold_snapshot p${mod}_held
    churn p${mod}_held
    pgq -c "SELECT /* wiki_bloatplan_record */ ixstat('P$mod held end', 'p${mod}_held_tag')"
    release_snapshot p${mod}_held
    pg -q -c "ANALYZE /* wiki_bloatplan_fixture */ p${mod}_free" -c "ANALYZE /* wiki_bloatplan_fixture */ p${mod}_held"
    pgq <<SQL
SELECT /* wiki_bloatplan_record */ xp('P$mod free bitmap', 'SELECT * FROM p${mod}_free WHERE tag = 7', NULL, 'enable_seqscan=off','enable_indexscan=off');
SELECT /* wiki_bloatplan_record */ xp('P$mod held bitmap', 'SELECT * FROM p${mod}_held WHERE tag = 7', NULL, 'enable_seqscan=off','enable_indexscan=off');
SQL
  done
}

q_state() {  # q_state <state>: catalog rows, live sizes and the charged index pages of fixture Q
  local s="$1"
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ fact('Q $s ' || c.relname, 'relpages=' || c.relpages || ' reltuples=' || c.reltuples || ' live blocks=' || pg_relation_size(c.oid) / current_setting('block_size')::int) FROM pg_class c WHERE c.relname IN ('q_t','q_part','q_full') ORDER BY c.relname;
SELECT /* wiki_bloatplan_record */ xp('Q $s partial rpc4', 'SELECT v FROM q_t WHERE id <= 20000 AND v > 0', 'q_full', $BMP);
SELECT /* wiki_bloatplan_record */ xp('Q $s partial rpc1', 'SELECT v FROM q_t WHERE id <= 20000 AND v > 0', 'q_full', $BMP, 'random_page_cost=1');
SELECT /* wiki_bloatplan_record */ xp('Q $s plain rpc4',   'SELECT v FROM q_t WHERE v > 0', 'q_part', $BMP);
SELECT /* wiki_bloatplan_record */ xp('Q $s plain rpc1',   'SELECT v FROM q_t WHERE v > 0', 'q_part', $BMP, 'random_page_cost=1');
SELECT /* wiki_bloatplan_record */ fact('Q $s charged index pages',
       'partial=' || round((idxcost('Q $s partial rpc4') - idxcost('Q $s partial rpc1')) / 3, 2)
       || ' plain=' || round((idxcost('Q $s plain rpc4') - idxcost('Q $s plain rpc1')) / 3, 2));
SQL
}

stage_fq() {
  say "fq: fixture Q, a partial index that grows after its pg_class row was last written"
  # q_part covers the first 20,000 of 200,000 rows; q_full covers them all.
  # Ten UPDATE rounds over the partial index's rows, in one transaction so
  # that no pruning and no bottom-up deletion can reclaim a version while the
  # rounds run, add ten entries per row to both indexes and double the heap.
  # Nothing writes pg_class until the ANALYZE at the end.
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS q_t;
CREATE /* wiki_bloatplan_fixture */ TABLE q_t (id int NOT NULL, v int NOT NULL, pad text NOT NULL) WITH (fillfactor = 100);
INSERT /* wiki_bloatplan_fixture */ INTO q_t SELECT g, g, repeat('x', 20) FROM generate_series(1, 200000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX q_part ON q_t (v) WHERE id <= 20000;
CREATE /* wiki_bloatplan_fixture */ INDEX q_full ON q_t (v);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) q_t;
SQL
  q_state built
  pg -q <<'SQL'
DO /* wiki_bloatplan_fixture_churn */ $churn$
BEGIN
  FOR i IN 1..10 LOOP
    UPDATE /* wiki_bloatplan_fixture_churn */ q_t SET v = v + 1 WHERE id <= 20000;
  END LOOP;
END $churn$;
SQL
  pgq -c "SELECT /* wiki_bloatplan_record */ ixstat('Q part churned', 'q_part')" \
      -c "SELECT /* wiki_bloatplan_record */ ixstat('Q full churned', 'q_full')"
  q_state churned
  pg -q -c "ANALYZE /* wiki_bloatplan_fixture */ q_t"
  q_state analyzed
}

stage_fe() {
  say "fe: fixture E, dead entries at the end of a B-tree and the planner's endpoint probe"
  # The histogram is built while id runs to 200,000; the upper half is then
  # deleted and nothing vacuums or analyzes the table.  A predicate that lands
  # in the last histogram bucket makes the planner probe the index for the
  # true maximum.  Each probe reads dead entries until it has visited 100 heap
  # pages without a visible row, and the entries it read are marked dead in
  # the index, so each plan gets further than the one before.
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS e_t;
CREATE /* wiki_bloatplan_fixture */ TABLE e_t (id int NOT NULL, v int NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO e_t SELECT g, g FROM generate_series(1, 200000) g;
ALTER /* wiki_bloatplan_fixture */ TABLE e_t ADD CONSTRAINT e_t_pkey PRIMARY KEY (id);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) e_t;
SQL
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ fact('E histogram', 'bounds=' || array_length(histogram_bounds::text::int[], 1)
       || ' last bound=' || (histogram_bounds::text::int[])[array_length(histogram_bounds::text::int[], 1)]
       || ' heap blocks=' || pg_relation_size('e_t') / current_setting('block_size')::int)
  FROM pg_stats WHERE schemaname = 'public' AND tablename = 'e_t' AND attname = 'id';
SELECT /* wiki_bloatplan_record */ xp('E before delete', 'SELECT count(*) FROM e_t WHERE id > 199990');
SQL
  pg -q -c "DELETE /* wiki_bloatplan_fixture */ FROM e_t WHERE id > 100000"
  pgq -c "SELECT /* wiki_bloatplan_record */ fact('E after delete', 'index entries marked dead=' || sum(dead_items)) FROM bt_multi_page_stats('e_t_pkey', 1, -1)"
  local k
  for k in 1 2 3 4 5 6; do
    pgq <<SQL
SELECT /* wiki_bloatplan_record */ xp('E plan $k', 'SELECT count(*) FROM e_t WHERE id > 199990');
SELECT /* wiki_bloatplan_record */ fact('E plan $k', 'index entries marked dead=' || sum(dead_items)) FROM bt_multi_page_stats('e_t_pkey', 1, -1);
SQL
  done
  pg -q -c "VACUUM /* wiki_bloatplan_fixture */ e_t"
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ fact('E after vacuum', 'index entries marked dead=' || sum(dead_items)) FROM bt_multi_page_stats('e_t_pkey', 1, -1);
SELECT /* wiki_bloatplan_record */ xp('E after vacuum', 'SELECT count(*) FROM e_t WHERE id > 199990');
SQL
}

# ---- GIN follow-up ----------------------------------------------------------

stage_gs() {
  say "gs: fixture S, one table, a btree_gin GIN index and a B-tree on the same column"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS t_both;
CREATE /* wiki_bloatplan_fixture */ TABLE t_both (id int NOT NULL, n int);
INSERT /* wiki_bloatplan_fixture */ INTO t_both SELECT i, i % 10000 FROM generate_series(1, 300000) i;
CREATE /* wiki_bloatplan_fixture */ INDEX t_both_n_gin ON t_both USING gin (n);
CREATE /* wiki_bloatplan_fixture */ INDEX t_both_n_bt  ON t_both (n);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) t_both;
SQL
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ ginstat('S gin', 't_both_n_gin');
SELECT /* wiki_bloatplan_record */ ixstat('S btree', 't_both_n_bt');
SELECT /* wiki_bloatplan_record */ xp('S gin n=42',      'SELECT * FROM t_both WHERE n = 42', 't_both_n_bt',  'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('S bt n=42',       'SELECT * FROM t_both WHERE n = 42', 't_both_n_gin', 'enable_seqscan=off', 'enable_indexscan=off');
SELECT /* wiki_bloatplan_record */ xp('S gin between',   'SELECT * FROM t_both WHERE n BETWEEN 100 AND 200', 't_both_n_bt',  'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('S bt between',    'SELECT * FROM t_both WHERE n BETWEEN 100 AND 200', 't_both_n_gin', 'enable_seqscan=off', 'enable_indexscan=off');
SELECT /* wiki_bloatplan_record */ xp('S gin n<20',      'SELECT * FROM t_both WHERE n < 20', 't_both_n_bt',  'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('S bt n<20',       'SELECT * FROM t_both WHERE n < 20', 't_both_n_gin', 'enable_seqscan=off', 'enable_indexscan=off');
SELECT /* wiki_bloatplan_record */ xp('S gin in123',     'SELECT * FROM t_both WHERE n IN (1,2,3)', 't_both_n_bt',  'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('S bt in123',      'SELECT * FROM t_both WHERE n IN (1,2,3)', 't_both_n_gin', 'enable_seqscan=off', 'enable_indexscan=off');
SELECT /* wiki_bloatplan_record */ xp('S gin orderby',   'SELECT * FROM t_both ORDER BY n LIMIT 10', 't_both_n_bt',  'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('S bt orderby',    'SELECT * FROM t_both ORDER BY n LIMIT 10', 't_both_n_gin', 'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('S gin ios',       'SELECT n FROM t_both WHERE n = 42', 't_both_n_bt',  'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('S bt ios',        'SELECT n FROM t_both WHERE n = 42', 't_both_n_gin', 'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('S gin isnull',    'SELECT * FROM t_both WHERE n IS NULL', 't_both_n_bt',  'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('S bt isnull',     'SELECT * FROM t_both WHERE n IS NULL', 't_both_n_gin', 'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('S gin n=42 rpc1', 'SELECT * FROM t_both WHERE n = 42', 't_both_n_bt',  'enable_seqscan=off', 'random_page_cost=1');
SELECT /* wiki_bloatplan_record */ xp('S default n=42',    'SELECT * FROM t_both WHERE n = 42');
SELECT /* wiki_bloatplan_record */ xp('S default between', 'SELECT * FROM t_both WHERE n BETWEEN 100 AND 200');
SELECT /* wiki_bloatplan_record */ xp('S default n<20',    'SELECT * FROM t_both WHERE n < 20');
SELECT /* wiki_bloatplan_record */ fact('S property ' || p, 'gin=' || pg_index_has_property('t_both_n_gin'::regclass, p) || ' btree=' || pg_index_has_property('t_both_n_bt'::regclass, p))
  FROM unnest(ARRAY['clusterable','index_scan','bitmap_scan','backward_scan']) p;
SELECT /* wiki_bloatplan_record */ fact('S column property ' || p, 'gin=' || pg_index_column_has_property('t_both_n_gin'::regclass, 1, p) || ' btree=' || pg_index_column_has_property('t_both_n_bt'::regclass, 1, p))
  FROM unnest(ARRAY['orderable','returnable','search_array','search_nulls']) p;
SQL
}

# docs_rows <from> <to>: the INSERT that fills fixture D.
#
# The rare lexeme is placed on every 4,999th row, not every 5,000th.  With a
# period of 5,000 the fixture was degenerate: 20 divides 5,000, so every row
# carrying the lexeme also had cat = 0, and the two-clause predicate
# "zebracorn AND cat = 7" could not match a single row however the planner
# priced it.  4,999 is prime, so it is coprime with the 20 category values and
# the two populations are independent: the lexeme rows walk all 20 residues of
# i % 20 in turn, so exactly one in twenty of them carries each category.
# cat stays i % 20, which keeps it exactly uniform and keeps the count of
# lexeme rows the same (80 in 400,000 either way).
docs_rows() {  # docs_rows <from> <to>
  printf "INSERT /* wiki_bloatplan_fixture */ INTO docs SELECT i, i %% 20, to_tsvector('simple', 'filler w' || (i %% 1000) || ' v' || (i %% 777) || CASE WHEN i %% 4999 = 0 THEN ' zebracorn' ELSE '' END) FROM generate_series(%s, %s) i" "$1" "$2"
}

docs_state() {  # docs_state <label>: what the planner does with the two-clause query in this state
  local l="$1"
  local q="SELECT * FROM docs WHERE tsv @@ to_tsquery('simple','zebracorn') AND cat = 7"
  local qg="SELECT * FROM docs WHERE tsv @@ to_tsquery('simple','zebracorn')"
  pgq <<SQL
SELECT /* wiki_bloatplan_record */ ginstat('D $l', 'docs_tsv_gin');
SELECT /* wiki_bloatplan_record */ fact('D $l heap', 'relpages=' || relpages || ' reltuples=' || reltuples || ' live blocks=' || pg_relation_size(oid) / current_setting('block_size')::int) FROM pg_class WHERE relname = 'docs';
SELECT /* wiki_bloatplan_record */ xp('D $l chosen',     \$q\$$q\$q\$);
SELECT /* wiki_bloatplan_record */ xp('D $l btree only', \$q\$$q\$q\$, 'docs_tsv_gin');
SELECT /* wiki_bloatplan_record */ xp('D $l gin alone',      \$q\$$qg\$q\$, NULL, 'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('D $l gin alone rpc1', \$q\$$qg\$q\$, NULL, 'enable_seqscan=off', 'random_page_cost=1');
SQL
}

stage_gd() {
  say "gd: fixture D, a tsvector GIN index with a fastupdate pending list, then a multicolumn GIN"
  pg -q <<SQL
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS docs;
CREATE /* wiki_bloatplan_fixture */ TABLE docs (id int NOT NULL, cat int NOT NULL, tsv tsvector NOT NULL);
$(docs_rows 1 200000);
CREATE /* wiki_bloatplan_fixture */ INDEX docs_tsv_gin ON docs USING gin (tsv) WITH (fastupdate = on);
CREATE /* wiki_bloatplan_fixture */ INDEX docs_cat_bt  ON docs (cat);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) docs;
SQL
  pgq -c "SELECT /* wiki_bloatplan_record */ ixstat('D cat btree', 'docs_cat_bt')"
  docs_state "vacuumed"
  # gin_pending_list_limit is PGC_USERSET; raised for these two sessions only so
  # that the inserts do not drain the pending list themselves.
  pgopt "-c gin_pending_list_limit=1GB" \
    -c "$(docs_rows 200001 300000)" -c "ANALYZE /* wiki_bloatplan_fixture */ docs"
  docs_state "pending one"
  pgopt "-c gin_pending_list_limit=1GB" \
    -c "$(docs_rows 300001 400000)" -c "ANALYZE /* wiki_bloatplan_fixture */ docs"
  docs_state "pending two"
  pgq -c "SELECT /* wiki_bloatplan_record */ fact('D gin_clean_pending_list returned', gin_clean_pending_list('docs_tsv_gin')::text)"
  docs_state "drained"
  pg -q -c "VACUUM /* wiki_bloatplan_fixture */ docs"
  docs_state "revacuumed"
  # The cat = 7 clause on its own, in the same state, so that all three
  # estimates the page sets beside true counts come from one statistics state.
  pgq -c "SELECT /* wiki_bloatplan_record */ xp('D revacuumed cat alone', 'SELECT * FROM docs WHERE cat = 7')"
  pg -q -c "CREATE /* wiki_bloatplan_fixture */ INDEX docs_multi_gin ON docs USING gin (tsv, cat)"
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ ginstat('D multi', 'docs_multi_gin');
SELECT /* wiki_bloatplan_record */ fact('D multi heap', 'relpages=' || relpages || ' reltuples=' || reltuples || ' live blocks=' || pg_relation_size(oid) / current_setting('block_size')::int) FROM pg_class WHERE relname = 'docs';
SELECT /* wiki_bloatplan_record */ xp('D multi chosen', $q$SELECT * FROM docs WHERE tsv @@ to_tsquery('simple','zebracorn') AND cat = 7$q$);
SELECT /* wiki_bloatplan_record */ xp('D multi hidden', $q$SELECT * FROM docs WHERE tsv @@ to_tsquery('simple','zebracorn') AND cat = 7$q$, 'docs_multi_gin');
-- The two clauses must be able to hold together, or every cost above prices a
-- plan for a predicate that matches nothing.  Record the true counts beside
-- the estimates, as fixture L3 does, so the page reports the gap instead of
-- assuming there is none.
SELECT /* wiki_bloatplan_record */ fact('D actual rows', 'zebracorn AND cat=7 = '
       || count(*) FILTER (WHERE tsv @@ to_tsquery('simple','zebracorn') AND cat = 7)
       || ', zebracorn = ' || count(*) FILTER (WHERE tsv @@ to_tsquery('simple','zebracorn'))
       || ', cat=7 = ' || count(*) FILTER (WHERE cat = 7)
       || ', total = ' || count(*)) FROM docs;
SELECT /* wiki_bloatplan_record */ fact('D estimated rows', string_agg(label || ' = ' || plan_rows, ', ' ORDER BY seq))
  FROM r WHERE label IN ('D revacuumed chosen', 'D revacuumed gin alone', 'D revacuumed cat alone', 'D multi chosen');
SQL
}

stage_gt() {
  say "gt: fixture T, a stale GIN metapage and the 4X fallback"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS t_stale;
CREATE /* wiki_bloatplan_fixture */ TABLE t_stale (id int NOT NULL, n int NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO t_stale SELECT i, i % 100 FROM generate_series(1, 2000) i;
CREATE /* wiki_bloatplan_fixture */ INDEX t_stale_gin ON t_stale USING gin (n) WITH (fastupdate = off);
VACUUM /* wiki_bloatplan_fixture */ (ANALYZE) t_stale;
SQL
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ ginstat('T small', 't_stale_gin');
SELECT /* wiki_bloatplan_record */ xp('T small n=42', 'SELECT * FROM t_stale WHERE n = 42', NULL, 'enable_seqscan=off');
SQL
  pg -q -c "INSERT /* wiki_bloatplan_fixture */ INTO t_stale SELECT i, i % 200000 FROM generate_series(2001, 400000) i" \
        -c "ANALYZE /* wiki_bloatplan_fixture */ t_stale"
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ ginstat('T grown', 't_stale_gin');
SELECT /* wiki_bloatplan_record */ xp('T grown n=42',      'SELECT * FROM t_stale WHERE n = 42', NULL, 'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('T grown n=42 rpc1', 'SELECT * FROM t_stale WHERE n = 42', NULL, 'enable_seqscan=off', 'random_page_cost=1');
SQL
  pg -q -c "VACUUM /* wiki_bloatplan_fixture */ t_stale"
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ ginstat('T vacuumed', 't_stale_gin');
SELECT /* wiki_bloatplan_record */ xp('T vacuumed n=42',      'SELECT * FROM t_stale WHERE n = 42', NULL, 'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('T vacuumed n=42 rpc1', 'SELECT * FROM t_stale WHERE n = 42', NULL, 'enable_seqscan=off', 'random_page_cost=1');
SQL
}

stage_gp() {
  say "gp: fixture P-gin, the keyless path on a partial GIN index"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS t_part;
CREATE /* wiki_bloatplan_fixture */ TABLE t_part (id int NOT NULL, n int NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO t_part SELECT i, i % 1000 FROM generate_series(1, 100000) i;
CREATE /* wiki_bloatplan_fixture */ INDEX t_part_gin ON t_part USING gin (n) WHERE id <= 5000;
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) t_part;
SQL
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ ginstat('Pg partial', 't_part_gin');
SELECT /* wiki_bloatplan_record */ xp('Pg keyless',      'SELECT * FROM t_part WHERE id <= 5000', NULL, 'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('Pg keyless rpc1', 'SELECT * FROM t_part WHERE id <= 5000', NULL, 'enable_seqscan=off', 'random_page_cost=1');
SELECT /* wiki_bloatplan_record */ xp('Pg keyed',        'SELECT * FROM t_part WHERE id <= 5000 AND n = 42', NULL, 'enable_seqscan=off');
SQL
}

stage_gb() {
  say "gb: fixture B-gin, a boolean column under a btree_gin bool opclass"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS t_bool;
CREATE /* wiki_bloatplan_fixture */ TABLE t_bool (id int NOT NULL, i boolean);
INSERT /* wiki_bloatplan_fixture */ INTO t_bool SELECT g, g % 100 = 0 FROM generate_series(1, 100000) g;
CREATE /* wiki_bloatplan_fixture */ INDEX t_bool_gin ON t_bool USING gin (i);
VACUUM /* wiki_bloatplan_fixture */ (FREEZE, ANALYZE) t_bool;
SQL
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ xp('Bg bare',   'SELECT * FROM t_bool WHERE i',         NULL, 'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('Bg eqtrue', 'SELECT * FROM t_bool WHERE i = true',  NULL, 'enable_seqscan=off');
SELECT /* wiki_bloatplan_record */ xp('Bg istrue', 'SELECT * FROM t_bool WHERE i IS TRUE', NULL, 'enable_seqscan=off');
SQL
}

stage_grej() {
  say "grej: the four things no GIN index can be created for (four errors are the expected result)"
  # The four statements need fixture S.  Without it they would fail for the
  # wrong reason, "relation does not exist", so the index is checked first,
  # and each statement must then fail with its own rejection text.
  local have
  have=$(pgq -c "SELECT /* wiki_bloatplan_grej_precheck */ to_regclass('t_both_n_gin') IS NOT NULL") \
    || die "could not check for fixture S"
  [ "$have" = "t" ] || die "grej needs fixture S: run the gs stage first"
  : > "$OUT/grej.txt" || die "cannot write $OUT/grej.txt"
  pgerr "CREATE /* wiki_bloatplan_expected_error */ UNIQUE INDEX rej_u ON t_both USING gin (n);" \
    'access method "gin" does not support unique indexes'
  pgerr "CREATE /* wiki_bloatplan_expected_error */ INDEX rej_i ON t_both USING gin (n) INCLUDE (id);" \
    'access method "gin" does not support included columns'
  pgerr "ALTER /* wiki_bloatplan_expected_error */ TABLE t_both ADD CONSTRAINT rej_x EXCLUDE USING gin (n WITH =);" \
    'access method "gin" does not support exclusion constraints'
  pgerr "CLUSTER /* wiki_bloatplan_expected_error */ t_both USING t_both_n_gin;" \
    'cannot cluster on index "t_both_n_gin" because access method does not support clustering'
  cat "$OUT/grej.txt"
}

stage_diag() {
  say "diag: run the page's two filed diagnostic blocks verbatim against my_table / my_col / my_gin_index"
  # The page's two sql blocks are read out of the page itself, so what runs is
  # what is filed.  The fence is assembled here because this script is
  # published inside a fenced block.
  local fence n=0 inblock=0 line
  fence=$(printf '\140\140\140')
  [ -f "$PAGE" ] || die "no page at $PAGE"
  while IFS= read -r line; do
    if [ "$inblock" = 0 ] && [ "$line" = "${fence}sql" ]; then
      n=$((n + 1)); inblock=1; : > "$OUT/diag$n.sql"; continue
    fi
    if [ "$inblock" = 1 ] && [ "$line" = "$fence" ]; then inblock=0; continue; fi
    [ "$inblock" = 1 ] && printf '%s\n' "$line" >> "$OUT/diag$n.sql"
  done < "$PAGE"
  [ "$n" = "2" ] || die "expected exactly two sql blocks on the page, found $n"
  pg -q <<'SQL'
DROP /* wiki_bloatplan_fixture */ TABLE IF EXISTS my_table;
CREATE /* wiki_bloatplan_fixture */ TABLE my_table (id int NOT NULL, my_col tsvector NOT NULL);
INSERT /* wiki_bloatplan_fixture */ INTO my_table SELECT i, to_tsvector('simple', 'filler w' || (i % 1000)) FROM generate_series(1, 100000) i;
CREATE /* wiki_bloatplan_fixture */ INDEX my_gin_index ON my_table USING gin (my_col) WITH (fastupdate = on);
VACUUM /* wiki_bloatplan_fixture */ (ANALYZE) my_table;
SQL
  pgopt "-c gin_pending_list_limit=1GB" \
    -c "INSERT /* wiki_bloatplan_fixture */ INTO my_table SELECT i, to_tsvector('simple', 'filler w' || (i % 1000)) FROM generate_series(100001, 150000) i"
  # The blocks SET their own timeouts; SESSION_OPTS is passed as well so that a
  # PGOPTIONS in the caller's environment cannot reach these two sessions.
  PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -v ON_ERROR_STOP=1 -f "$OUT/diag1.sql" > "$OUT/diag1.out" 2>&1 \
    || die "diagnostic block 1 failed, see $OUT/diag1.out"
  PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -v ON_ERROR_STOP=1 -f "$OUT/diag2.sql" > "$OUT/diag2.out" 2>&1 \
    || die "diagnostic block 2 failed, see $OUT/diag2.out"
  grep -E 'my_gin_index' "$OUT/diag1.out" "$OUT/diag2.out"
}

stage_predict() {
  say "predict: the closed form in (pages, tuples, fastlevel) against EXPLAIN, fixture A"
  pgq <<'SQL'
SELECT /* wiki_bloatplan_record */ predict('A dense full',  'a_dense_idx',  'a_dense');
SELECT /* wiki_bloatplan_record */ predict('A sparse full', 'a_sparse_idx', 'a_sparse');
SELECT /* wiki_bloatplan_record */ fact('closed form against EXPLAIN', 'matches on ' || count(*) FILTER (WHERE predicted = observed) || ' of ' || count(*)) FROM pr;
SQL
}

stage_summary() {
  say "summary: written to $OUT/summary.txt"
  # Only standard output goes to the file: a psql error or an abort message
  # lands on the terminal, where it is seen, not inside the results.
  pg <<'SQL' > "$OUT/summary.txt"
\pset pager off
SELECT /* wiki_bloatplan_summary */ label, idx, blocks, tree_level, fastlevel, leaf_pages AS leaf, internal_pages AS internal,
       deleted_pages AS deleted, density, frag FROM ix ORDER BY seq;
SELECT /* wiki_bloatplan_summary */ label, idx, blocks, pending_pages AS pending, n_total, n_entry, n_data, n_entries FROM gx ORDER BY seq;
SELECT /* wiki_bloatplan_summary */ label, pages, tuples, fastlevel, predicted, observed, predicted = observed AS match FROM pr ORDER BY seq;
SELECT /* wiki_bloatplan_summary */ c.relname AS fixture_table, c.relpages, c.relallvisible, c.reltuples
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname NOT IN ('r','ix','gx','pr','fx') ORDER BY 1;
SELECT /* wiki_bloatplan_summary */ label, value FROM fx ORDER BY seq;
\pset format unaligned
SELECT /* wiki_bloatplan_summary */ label, nodes(label) AS plan FROM r ORDER BY seq;
SQL
  cat "$OUT/platform.txt" >> "$OUT/summary.txt"
  [ -f "$OUT/grej.txt" ] && cat "$OUT/grej.txt" >> "$OUT/summary.txt"
  [ -f "$OUT/diag1.out" ] && cat "$OUT/diag1.out" "$OUT/diag2.out" >> "$OUT/summary.txt"
  date -u '+run finished %Y-%m-%dT%H:%M:%SZ' >> "$OUT/summary.txt"
  note "$(grep -c . "$OUT/summary.txt") lines"
}

# The teardown is asserted, not assumed: pg_ctl finds no server, there is no
# postmaster.pid, no process whose command line names this data directory,
# and no socket is left on the port.  $DATA is the resolved path pg_ctl was
# given, so it is the text the postmaster's own command line carries; the
# pattern is the bare path, as AGENTS.md prescribes, so it also catches a
# process that names the directory without a preceding -D.
assert_down() {
  # Without pgrep the process check below would fail with status 127 and
  # pass silently, so its absence is an error, not a pass.
  command -v pgrep >/dev/null 2>&1 || die "pgrep is needed to assert that no postgres process is left"
  "$BIN/pg_ctl" -D "$DATA" status >/dev/null 2>&1 && die "pg_ctl still reports a server running from $DATA"
  [ -f "$DATA/postmaster.pid" ] && die "postmaster.pid is still present in $DATA"
  pgrep -f -- "$DATA" >/dev/null 2>&1 && die "a process naming $DATA is still running"
  [ -e "$SOCK/.s.PGSQL.$PORT" ] && die "the socket $SOCK/.s.PGSQL.$PORT is still present"
  return 0
}

stage_stop() {
  say "stop: shut the measurement cluster down"
  own_sandbox || return 0
  stop_server
  assert_down
  note "stopped: no postmaster.pid, no process from $DATA, no socket on port $PORT; $SANDBOX is kept until the clean stage"
}

stage_clean() {
  say "clean: stop the server and delete the sandbox"
  own_sandbox || return 0
  stop_server
  assert_down
  rm -rf "$SANDBOX" || die "could not delete $SANDBOX"
  SANDBOX_OK=0
  note "removed $SANDBOX"
}

# The dispatcher checks every stage name before any stage runs, claims the
# sandbox for the stages that write into it, starts a server for the stages
# that need one, and turns a failed stage into a failed run.  Without the
# || die a stage that returns non-zero without calling die is skipped over and
# the script still exits 0.  CURRENT_STAGE only names the stage in the abort
# message; the abort itself comes from pg(), pgopt() or an explicit die inside
# the stage, because a stage function's own exit status is the status of its
# LAST command and cannot speak for the calls before it.
SQL_STAGES="fa fb ff fg fh fi fn fstale fl3 fp fq fe gs gd gt gp gb grej diag predict summary"
known_stage() {
  case " build check cluster stop clean $SQL_STAGES " in *" $1 "*) return 0 ;; esac
  return 1
}
run_stage() {
  local st="$1"
  CURRENT_STAGE="$st"
  case "$st" in
    stop|clean) ;;
    build|check|cluster) claim_sandbox; use_sandbox_tmp ;;
    *) claim_sandbox; use_sandbox_tmp; need_server ;;
  esac
  "stage_$st" || die "stage $st failed"
  CURRENT_STAGE=""
}

DEFAULT="build check cluster $SQL_STAGES stop"
[ $# -eq 0 ] && set -- $DEFAULT
for st in "$@"; do known_stage "$st" || die "unknown stage: $st; nothing was run"; done
setup_paths
for st in "$@"; do run_stage "$st"; done
```

## Context Reviewed

Planner and cost path: `src/backend/optimizer/util/plancat.c` (`get_relation_info`, `estimate_rel_size`), `src/backend/optimizer/path/costsize.c` (`cost_index`, `index_pages_fetched`, `cost_bitmap_heap_scan`, `compute_bitmap_pages`, `get_indexpath_pages`), `src/backend/optimizer/path/allpaths.c` (`total_table_pages`, `compute_parallel_worker`), `src/backend/optimizer/path/indxpath.c` (`choose_bitmap_and`, `bitmap_scan_cost_est`), `src/backend/optimizer/util/pathnode.c` (`compare_path_costs_fuzzily`), `src/backend/utils/adt/selfuncs.c` (`genericcostestimate`, `btcostestimate`, `hashcostestimate`, `gistcostestimate`, `spgcostestimate`, `gincostestimate`, `brincostestimate`, `add_predicate_to_index_quals`).

nbtree: `nbtpage.c` (`_bt_getrootheight`, fast-root update, page deletion), `nbtsplitloc.c` (`_bt_findsplitloc` fillfactor policy and single-value strategy), `nbtdedup.c` (`_bt_dedup_pass`, `_bt_bottomupdel_pass`), `nbtinsert.c` (pre-split deletion and deduplication), `nbtsort.c`, `src/include/access/nbtree.h`, and the nbtree `README` sections on page deletion, tree height, FSM placement, simple deletion, bottom-up deletion, split policy, and deduplication.

VACUUM: `src/backend/access/heap/vacuumlazy.c` (`BYPASS_THRESHOLD_PAGES`, `lazy_vacuum`, `lazy_check_wraparound_failsafe`, `LVRelState`).

Headers and catalogs: `src/include/nodes/pathnodes.h` (`IndexOptInfo`, `RelOptInfo`, `PlannerInfo`), `src/include/catalog/pg_class.h`, `src/backend/access/common/reloptions.c` (including the table `parallel_workers` option), `src/backend/utils/cache/spccache.c` (`get_tablespace_page_costs`), `src/backend/utils/misc/guc_tables.c`.

Contrib: `contrib/pgstattuple/pgstatindex.c` plus its `sql/` and `expected/` regression files, `contrib/pageinspect` `bt_metap()` definitions.

Documentation: `ref/reindex.sgml`, `maintenance.sgml` (routine reindexing), `glossary.sgml` (Bloat), `btree.sgml` (version churn, bottom-up deletion, deduplication), `ref/create_table.sgml` (`vacuum_index_cleanup`), `ref/create_index.sgml`, `indices.sgml`, `pgstattuple.sgml`.

History: every cross-version statement rests on this checkout's own history. The v12 baseline is the branch point `9e1c9f9594`, the parent of the 13devel stamp `615cebc94b`. An "unchanged since v12" claim is `git log -L` with the function's line range over `615cebc94b..HEAD`, plus identical text at `615cebc94b`. A "before commit X" claim is read from X's own diff. A first release is the first `Stamp HEAD as NNdevel.` or `Stamp 17.N.` commit that has the change as an ancestor (`git merge-base --is-ancestor`), because the checkout carries no tags. Traced this way: `genericcostestimate()`, `btcostestimate()`, `gincostestimate()`, `index_pages_fetched()`, `cost_index()`, `get_actual_variable_endpoint()`, the `get_relation_info()` index-size block, `estimate_rel_size()` and `table_block_relation_estimate_size()`; `git log -S` for the ScalarArrayOp clamp and for `stats->estimated_count = true`; and the messages of every attributed commit. The checkout cannot show what 12.x minor releases contain; see [Open Questions](#open-questions). `raw/postgres-12` was read only as a cross-check and is not cited. `git log 54eeefaedbee..786db8dcf168` lists the commits between the previous pin and this one.

Empirical: one isolated PostgreSQL 17.11 server built from the pin by the script under [Measurement Script](#measurement-script), whose B-tree stages cover density, real deletion bloat, a mostly-empty index whose fast root moved, the same draining taken to one surviving row so that the flat one-page estimate fires, height, seeded fragmentation, catalog forgery, plan flips, `BitmapAnd` pruning, parallel worker counts at three selectivities under both default and zeroed parallel costs, a repeated inner scan under two cache settings, the v17 SAOP clamp, version churn at two key cardinalities with and without a held snapshot, deduplication, a closed-form prediction checked against `EXPLAIN`, a partial and a plain index on one table priced before their growth reached `pg_class` and again after `ANALYZE` (fixture Q), and the planning-time endpoint probe of a primary key whose upper half was deleted, followed through six plans and a plain `VACUUM` with the dead-entry count read after each (fixture E).

Pin: `raw/postgres-17/` at commit `786db8dcf168bd9df8f55047337525ac19118b1c` (PostgreSQL 17.11, seven commits past `Stamp 17.11.` `083ac03341`); repinned from `54eeefaedbee0385529f3edf321bb99e49232aaa` (17.10) on 2026-08-17. Every measured number on the page was taken on this pin by the script filed under [Measurement Script](#measurement-script); [Last run](#last-run) records the latest runs.

Follow-up (GIN versus B-tree) additions. Path generation and gating: `src/backend/optimizer/path/indxpath.c` (`create_index_paths`, `match_restriction_clauses_to_index`, `match_clause_to_indexcol`, `match_opclause_to_indexcol`, `match_saopclause_to_indexcol`, `match_boolean_index_clause`, `IsBooleanOpfamily`, `get_index_clause_from_support`, `get_index_paths`, `build_index_paths`, `check_index_only`, `choose_bitmap_and`, `bitmap_and_cost_est`), `src/backend/optimizer/util/plancat.c` (the AM capability-flag copy and the `sortopfamily` branches), `src/backend/optimizer/util/pathnode.c` (`add_path`, `STD_FUZZ_FACTOR`), `src/backend/access/index/indexam.c` (`index_can_return`), `src/backend/optimizer/path/costsize.c` (`disable_cost`).

GIN internals: `src/backend/utils/adt/selfuncs.c` (`gincostestimate`, `gincost_pattern`, `gincost_opexpr`, `gincost_scalararrayopexpr`, `GinQualCounts`), `src/backend/access/gin/ginutil.c` (`ginhandler`, `ginGetStats`, `ginUpdateStats`), `src/backend/access/gin/ginfast.c` (`gin_clean_pending_list`), `src/include/access/gin.h` (`GinStatsData`, `GIN_SEARCH_MODE_*`), `src/include/access/ginblock.h` (`GinMetaPageData`).

Catalogs, errors and settings: `src/include/catalog/pg_amop.dat` (the four core GIN opfamilies plus the B-tree and hash `jsonb` families), `src/include/catalog/pg_opfamily.h` (`IsBuiltinBooleanOpfamily`), `src/backend/commands/indexcmds.c` (unique/`INCLUDE`/multicolumn/exclusion AM checks), `src/backend/commands/cluster.c` (`amclusterable`), `src/backend/access/common/reloptions.c` (`fastupdate`, per-index `gin_pending_list_limit`), `src/backend/utils/misc/guc_tables.c` (`gin_pending_list_limit`).

Contrib, tests and docs: `contrib/btree_gin` (`btree_gin--1.0.sql` operator classes, `sql/bool.sql`, `expected/bool.out`), `contrib/pgstattuple/pgstatindex.c` (`pgstatginindex`), `src/test/regress/expected/amutils.out`, `src/test/regress/sql/create_index.sql`, `src/test/regress/sql/tsearch.sql`, `doc/src/sgml/indices.sgml`, `doc/src/sgml/indexam.sgml`, `doc/src/sgml/gin.sgml`, `doc/src/sgml/btree-gin.sgml`, `doc/src/sgml/pgtrgm.sgml`.

Follow-up history: `git log -L` with `gincostestimate()`'s line range over `615cebc94b..HEAD` returns exactly two commits, `cd9479af2a` and `4b754d6c16e`, first in 16 and 13 by ancestry against the `Stamp HEAD as NNdevel.` commits. The follow-up describes only v17 behavior. The main answer's [v13: GIN's whole-index estimate narrowed](#v13-gins-whole-index-estimate-narrowed) reads the earlier behavior from `4b754d6c16e`'s own diff.

Follow-up empirical: the GIN stages of the same script on the same server, with `btree_gin`, `pgstattuple` and `pageinspect` installed, covering same-column GIN-versus-B-tree costing on identical statistics (the closed-form reconciliation of both cost models in [Gate 3](#gate-3-cost-and-why-gin-loses-on-the-same-column) was done by hand from the counters the script records; the script's own `predict()` checks only the seven B-tree whole-index scans), the three plan-shape cases of the fixture-S table, `fastupdate` pending-list bloat at two sizes with the B-tree-only alternative priced beside it, the drain and the following `VACUUM`, the 4X stale-metapage fallback, the keyless partial-index path, the boolean-column case, the live AM property matrix, the four `CREATE INDEX`/`CLUSTER` rejections, a multicolumn-GIN comparison, and verbatim execution of the two filed diagnostic blocks as read out of this page. The `clean` stage stopped the server and deleted the sandbox.

Also read while checking and revising the page, beyond the files above: for the endpoint probe, `selfuncs.c`'s `scalarineqsel()` wrappers, `ineq_histogram_selectivity()`, `mergejoinscansel()`, `get_variable_range()`, `get_actual_variable_range()` and `get_actual_variable_endpoint()`, `like_support.c`, `plancat.c`'s `restriction_selectivity()`, `pg_operator.dat`, `lsyscache.h`, `costsize.c`'s `clamp_row_est()`, `nbtree.c`'s `btgettuple()` and `btendscan()`, `nbtsearch.c`, `indexam.c`, `genam.c`, `nbtxlog.c` and `contrib/pageinspect/btreefuncs.c`; for the index-size inputs and their lifecycle, `bufmgr.c`, `bufmgr.h`, `tableam.c`, `heapam_visibility.c`, `analyze.c`, `heapam.c`'s `heap_update()`, `heap_delete()` and in-place update, `inval.c`, `relcache.c`, `lmgr.c`, `vacuum.c`, `index.c`, `tablecmds.c`, `heap.c`, `matview.c`, `heapam_handler.c`, `nbtsort.c`, `nbtinsert.c`, `nbtpage.c`, `nbtsplitloc.c`, `nbtutils.c`, `nbtdedup.c`, `nodeModifyTable.c`, `execIndexing.c` and `tableam.h`; for the cost path, `clausesel.c`, `selfuncs.h`, `plancat.h`, `spccache.c`, `cost.h`, `planmain.c`, `initsplan.c`, `relnode.c`, `pathnode.c`, `createplan.c`, `planner.c` and contrib `bloom`'s `blcost.c` and `blutils.c`; for BRIN and GIN, `brin.c`, `brin_revmap.c`, `brin_pageops.c`, `brin.h`, `gininsert.c`, `ginvacuum.c`, `ginfast.c` and `tidbitmap.c`; for gate 0, `pg_index.h`, `plancache.c`, `README.HOT` and `prepjointree.c`; for the generated-header and test claims, `genbki.h`, `genbki.pl`, `Catalog.pm`, `catversion.h`, `initdb.c`, `pg_am.dat`, `pg_proc.dat`, `btree_index.sql`, `jsonb.sql`, `inherit.out` and `pgstattuple--1.4--1.5.sql`; and for the script, libpq's `fe-connect.c`, `pqcomm.c`, `pqcomm.h`, psql's `mainloop.c` and `settings.h`, `pg_regress.c`, `src/Makefile.global.in` and `installation.sgml`. The page's review history is recorded in the [log](../../../log.md).

## Evidence Map

| Claim | Evidence |
|---|---|
| `pg_class` carries only three size statistics, `relpages`, `reltuples` and `relallvisible`, and `IndexOptInfo` only three index-size fields, `pages`, `tuples` and `tree_height`; neither has a bloat, density or fragmentation field | [pg_class.h#relpages](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L69), [pathnodes.h#IndexOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1120-L1128) |
| `pages` comes from the live block count for non-partial indexes | [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486); `RelationGetNumberOfBlocks()` counts the main fork only ([bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4002-L4020), [bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L280-L281)); measured: forged `relpages = 1` left cost at `24640.42`, and fixture Q's plain `q_full` was charged all 825 of its live blocks while `pg_class` still recorded 551 |
| `tuples` is the parent table's estimate for non-partial indexes, so removing index entries never lowers it, and `pages / tuples` also rises when the table's estimate falls while the index keeps its pages | [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486), [plancat.c:476](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L476); measured on fixture F: the index kept 2,745 blocks while the table's estimate fell from 1,000,000 to 1,000 rows, and its one-row lookup rose from `4.44` to `12.29` |
| A partial index's `tuples` is its recorded `pg_class` density times its live blocks less the metapage, clamped to the table's rows; a forged `reltuples` caps the entries read but leaves every page charged | [plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160), [plancat.c#estimate_rel_size-density](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1116-L1146), [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486), [selfuncs.c#genericcostestimate-tuple-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6707-L6715), [selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091); measured: forged `reltuples = 20` moved the cost `24140.42` -> `23140.49` and the startup `0.42` -> `0.39`, with all 5,285 pages still charged |
| A partial index uses its recorded density only while `reltuples >= 0` and `relpages > 1`; otherwise it invents a density from the column widths | [plancat.c#estimate_rel_size-density](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1116-L1146); not measured |
| A new index's row starts at `relpages = 0` and `reltuples = 0`, and a build writes its own counts, an empty B-tree build recording `relpages = 1`; a `REINDEX` or `TRUNCATE` first resets the row to `0` and `-1`, a rebuild with no entries leaves those, and a build during binary upgrade writes nothing | [index.c#index_create-pg_class](../../../../raw/postgres-17/src/backend/catalog/index.c#L1008-L1024), [relcache.c#RelationBuildLocalRelation-rd_rel](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3656-L3659), [index.c#index_update_stats-write](../../../../raw/postgres-17/src/backend/catalog/index.c#L2835-L2923), [nbtsort.c#_bt_load-first-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1287-L1290), [nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1063-L1128), [relcache.c#RelationSetNewRelfilenumber-reset](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3948-L3954), [index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842); not measured |
| A partial index is charged about its estimated matching rows divided by its last recorded density, so pages it gains reach the charge only in proportion to the table's estimated growth, until `ANALYZE`, a `VACUUM` that counts its entries exactly, or a rebuild rewrites its `pg_class` row, or until the clamp binds | [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160), [selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019), [selfuncs.c:6695](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6695), [selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732), [tableam.c#table_block_relation_estimate_size-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L711-L747), [analyze.c#do_analyze_rel-index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663), [vacuumlazy.c#heap_vacuum_rel-index-stats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L512-L513), [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099), [index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135), [index.c#index_update_stats-write](../../../../raw/postgres-17/src/backend/catalog/index.c#L2835-L2923), [index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842), a rebuild that finds no entries while the row holds `reltuples = -1` and a build during binary upgrade being the two exceptions; measured on fixture Q: `q_part` grew from 57 to 331 blocks and was charged 57, then 113, then 331 after `ANALYZE`, while `q_full` grew from 551 to 825 blocks and was charged all 825 before `ANALYZE`. After the churn `pgstatindex` read `q_part` at 77.56% density and 49.85% fragmentation and `q_full` at 85.14% and 20% ([pgstatindex.c#pgstatindex_impl-density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L372)), and `bt_metap()` read their `fastlevel` as 1 and 2 ([btreefuncs.c:908](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L908)). The exact-count `VACUUM`, the rebuild and the clamp are not measured |
| Fixture Q's churned partial charge: the table estimate is `rint(200000 / 1471 * 2942) = 400000`, the partial `tuples` `rint(20000 / (57 - 1) * (331 - 1)) = 117857`, the entries read `0.1 * 400000 = 40000`, and the charge `ceil(40000 * 331 / 117857) = 113` pages, in a node total of `752.29`; after `ANALYZE` it is `ceil(20000 * 331 / 20000) = 331`. The plain index keeps its 825 pages after `ANALYZE`, and its total falls by `1500.00`: `200000 * (0.005 + 0.0025)` for the halved row estimate, plus one fewer descent comparison, `ceil(log2(400000)) = 19` against `ceil(log2(200000)) = 18`, at `0.0025`, which the rounding hides | [plancat.c#get_relation_info-table-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L196-L202), [tableam.c#table_block_relation_estimate_size-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L711-L747), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160), [selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732), [analyze.c#do_analyze_rel-index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663), [analyze.c#do_analyze_rel-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L623-L645), [selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810), [selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091); measured: `752.29` / `413.29` at `random_page_cost` 4 / 1, so 113 pages, and `1474.29` / `481.29` after `ANALYZE`, so 331, with the `pg_class` rows before and after; the plain index's `Bitmap Index Scan` total `6300.42` before `ANALYZE` and `4800.42` after |
| Fixture Q's ten `UPDATE` rounds are non-HOT, so each adds an entry to both indexes, the partial one included because every updated row still satisfies `id <= 20000`; and they share one transaction, so no replaced version is dead to anyone before the commit | [heapam.c#heap_update-hot-decision](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4140-L4166), [heapam.c:4429](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4429), [nodeModifyTable.c#ExecUpdateEpilogue-onlySummarizing](../../../../raw/postgres-17/src/backend/executor/nodeModifyTable.c#L2162-L2166), [execIndexing.c#ExecInsertIndexTuples-loop](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L343-L387), [heapam_visibility.c#HeapTupleSatisfiesVacuumHorizon-same-xact](../../../../raw/postgres-17/src/backend/access/heap/heapam_visibility.c#L1253-L1266), [heapam_visibility.c#HeapTupleSatisfiesVacuumHorizon-xmax-in-progress](../../../../raw/postgres-17/src/backend/access/heap/heapam_visibility.c#L1383-L1386); measured: the heap doubled exactly, 1,471 -> 2,942 blocks |
| The charged index pages are the `Bitmap Index Scan` node's cost difference between `random_page_cost` 4 and 1, divided by 3, and that node's cost is the access method's own total with no heap term | [selfuncs.c#genericcostestimate-single-scan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6780-L6787), [costsize.c#cost_index-save-indextotalcost](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L623-L629), [createplan.c#create_bitmap_subplan-indexpath](../../../../raw/postgres-17/src/backend/optimizer/plan/createplan.c#L3480-L3485) |
| For a partial index the `ceil(log2(tuples))` comparison charge also grows with the live block count | [selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160); it enters fixture Q's `752.29` as `ceil(log2(117857)) * 0.0025` |
| Page count enters cost pro-rata | [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732); measured `28480.42` vs `123144.43` |
| Height charge prices descent CPU, and bloat is one of its two stated reasons | [selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106) |
| Height charge is `50 * cpu_operator_cost` per level | [selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145), `0.125` at the default `cpu_operator_cost` of `0.0025` ([cost.h:28](../../../../raw/postgres-17/src/include/optimizer/cost.h#L28)); measured startup gap exactly `50.00` at `cpu_operator_cost = 1`. The height charge still sees bloat on a lone lookup: fixture B's falls from `4.44` to `4.31` when a rebuild removes a level, and fixture H's two lookups cost `8.31` and `8.43` |
| Planner height is the fast-root level, while `pgstatindex` reports the true root level `btm_level` as `tree_level` | [nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717), [README#page-deletion-and-tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L362-L381), [pgstatindex.c#pgstatindex_impl-metapage](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L252-L265), [pgstatindex.c:351](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L351), [pgstattuple--1.4--1.5.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L24), [pgstattuple.control:3](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.control#L3); measured on fixture F: `tree_level` 2 against `fastlevel` 1 |
| Index pages enter cache modeling: `index_pages_fetched()` prorates `effective_cache_size` over the query's table pages plus the index, `total_table_pages` counts table pages only, and every B-tree-family call site passes `index->pages` (GIN passes its entry- or data-page count); `cost_index()` passes it on each of its three `index_pages_fetched()` calls, two for repeated scans and one for the normal case, and computes the normal case's perfectly-correlated estimate without the cache model | [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951), [allpaths.c#total_table_pages](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L183-L216), [pathnodes.h#total_table_pages](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L483-L484), [costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747), [costsize.c#cost_index-repeated-uncorrelated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L680-L683), [costsize.c#cost_index-repeated-correlated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L702-L707), [costsize.c#cost_index-normal-uncorrelated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L720-L723), [costsize.c#cost_index-normal-correlated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L733-L746), [selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779), [costsize.c#compute_bitmap_pages-repeated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L6463-L6476), [selfuncs.c#gincostestimate-cache-effects](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7957-L7974); measured `0.66` against `2.50` per loop for a repeated inner index-only scan, and both higher at `effective_cache_size = 64MB` |
| The scan's touched-pages estimate, not the index size, chooses parallel workers | [costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L772), [selfuncs.c#btcostestimate-outputs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7206-L7210), [allpaths.c#compute_parallel_worker](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4202-L4279); measured 6 / 5 / 5 workers at 100% / 50% / 20% of the 26,411-block index against 4 / 3 / 2 on its 2,745-block twin |
| The page-based worker calculation is conditional | a table `parallel_workers` reloption is used instead and skips it entirely, capped only by the caller's maximum, `max_parallel_workers_per_gather` for `cost_index()` ([allpaths.c#compute_parallel_worker-reloption](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4208-L4213), [allpaths.c:4276](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4276), [plancat.c:205](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L205), [reloptions.c#parallel_workers](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L374-L382)); the `min_parallel_index_scan_size` rejection is guarded on `RELOPT_BASEREL`, exempting inheritance children ([allpaths.c#compute_parallel_worker-threshold](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4216-L4227)). Neither case is measured here |
| `min_parallel_index_scan_size` is necessary but not sufficient: a plain index scan also needs a heap-page estimate of at least `min_parallel_table_scan_size` and takes the smaller of the two worker counts, while an index-only scan passes no heap estimate | [costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L772), [allpaths.c#compute_parallel_worker-threshold](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4216-L4227), [allpaths.c#compute_parallel_worker-index-ramp](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4253-L4272); fixture A's parallel scans are index-only, so only the index test is measured |
| A flat one-page estimate is a ceiling as well as a floor: `tuples <= 1` collapses an index of any size to one page | [selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732), [selfuncs.c#btcostestimate-log2-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7086-L7091); measured on fixture F-one: 551 blocks and one live leaf priced at `4.14`, the page term `1 * 4.0` |
| A repeated lookup is priced with the whole index as the page universe, even though a single one is not: few loops over a large index are charged about one page each whatever its size; once loops times touched pages reach the index size the charge approaches the whole index spread over the loops, it is capped at the whole index from twice the index size while the index fits its cache share, and it passes the cap only when the query's tables plus the index exceed `effective_cache_size` | [selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779), [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951); measured on fixture A over 50,000 loops: `0.66` against `2.50` per loop on indexes that both price a lone lookup at `4.44`. The page charges are `2745 * 4.0 / 50000 = 0.22`, at the cap, and `25687 * 4.0 / 50000 = 2.05`, just short of it, 9.36x the charge for 9.62x the pages; at `effective_cache_size = 64MB`, the case past the cap, `1.38` against `3.55`. The few-loops regime is not measured |
| v17 clamps SAOP descents to `ceil(pages/3)` | [selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042); measured plateau at 3 descents on the 8-block index; the 55-block index's cap of 19 is computed and not reached at 10 elements |
| The SAOP per-tuple CPU charge is divided by the descent count and multiplied back, so `rint()` rounding moves it, and a floor of one tuple per descent makes it `num_sa_scans * (cpu_index_tuple_cost + qual_op_cost)` when descents outnumber rows | [selfuncs.c:7064](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7064), [selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810), [selfuncs.c#genericcostestimate-tuple-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6707-L6715); measured on fixture I's 8-block index, clamped to 3 descents: `rint(10 / 3) * 3 = 9` tuples at ten elements and `rint(4 / 3) * 3 = 3` at four, the same 3 tuples as at three elements, so `352.04` at three elements and `352.05` at four differ by one heap row's `cpu_tuple_cost` |
| The endpoint probe is not a cost input: when `ineq_histogram_selectivity()`'s binary search reaches the first or last histogram bound, or the histogram has two bounds, it replaces that bound in its copy with the live minimum or maximum, and keeps `pg_statistic`'s bound when the probe fails | [selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136), [lsyscache.h#AttStatsSlot](../../../../raw/postgres-17/src/include/utils/lsyscache.h#L46-L62), [selfuncs.c#get_actual_variable_endpoint-give-up](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6409-L6413) |
| The probe is reached from `scalarltsel()`, `scalarlesel()`, `scalargtsel()` and `scalargesel()` for a comparison against a constant, from `LIKE` fixed-prefix estimation, and from merge-join costing, which compares each side's column with the other side's `pg_statistic` extremes; `get_variable_range()`'s own call to the probe is compiled out | [selfuncs.c#scalarineqsel_wrapper](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1397-L1503), [selfuncs.c:690](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L690), [like_support.c#prefix_selectivity](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1213-L1270), [like_support.c:1245](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1245), [like_support.c:1266](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1266), [costsize.c:3577](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L3577), [costsize.c:4016](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L4016), [selfuncs.c#mergejoinscansel-ranges](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L3141-L3156), [selfuncs.c#get_variable_range](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5969-L6098), [selfuncs.c#get_variable_range-not-used](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5993-L6003), [selfuncs.c#mergejoinscansel-scalarineqsel](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L3164-L3203); the chain from `clauselist_selectivity()`: [clausesel.c#clauselist_selectivity](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L100-L108), [clausesel.c:136](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L136), [clausesel.c:183](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L183), [clausesel.c:848](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L848), [plancat.c#restriction_selectivity](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1951-L1979), [pg_operator.dat#int4gt](../../../../raw/postgres-17/src/include/catalog/pg_operator.dat#L453-L456), [selfuncs.c#scalargtsel](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1490-L1494), [selfuncs.c:1461](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1461). Fixture E exercises only the `scalargtsel()` path |
| The probe reads only the first index that is a B-tree, not partial, not hypothetical, and whose first column matches the compared expression, collation and sort operator, and it gives up at once on a partitioned parent; no other access method and no partial index is probed | [selfuncs.c#get_actual_variable_range-index-choice](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6179-L6239), [selfuncs.c#get_actual_variable_range](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6157-L6331), [selfuncs.c#get_actual_variable_range-skips](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6196-L6212), [selfuncs.c:6197](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6197) |
| The probe walks the index as an index-only scan under `SnapshotNonVacuumable`: an entry on an all-visible heap page is accepted without a heap visit, rows dead to every snapshot are skipped, and recently dead or uncommitted rows are accepted | [selfuncs.c#get_actual_variable_endpoint-snapshot](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6376-L6386), [selfuncs.c#get_actual_variable_endpoint-horizon](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6415-L6416), [selfuncs.c#get_actual_variable_endpoint-scan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6415-L6458), [selfuncs.c#get_actual_variable_endpoint-comment](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6371-L6414); fixture E covers only rows dead to every snapshot |
| Each probe counts a heap page when a rejected entry points to a different page than the last one counted, and gives up on the fetch that takes the count past `VISITED_PAGES_LIMIT` (100), a local `#define` with no GUC; each call starts at zero and the minimum and maximum are separate calls, so the limit binds each probe, not each plan, and one probe reads up to 101 heap pages | [selfuncs.c#get_actual_variable_endpoint-limit](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6436-L6457), [selfuncs.c#VISITED_PAGES_LIMIT](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6447-L6455), [selfuncs.c:6447](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6447), [selfuncs.c:6365](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6365), [selfuncs.c#get_actual_variable_range-endpoint-calls](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6282-L6314), [selfuncs.c#get_actual_variable_endpoint](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6349-L6501); measured on fixture E: 885 heap blocks of 226 rows, the last holding 216, and plan 1 marked `216 + 99 * 226 = 22590` entries, exactly 100 heap pages, and plans 2 to 4 marked `22600` each |
| Every entry the probe passes over because its whole HOT chain is dead is marked killed, so the next probe passes it without a heap visit; the entry whose fetch trips the 100-page limit is not, because no further `btgettuple()` call records it | [indexam.c#index_fetch_heap-kill](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L644-L652), [nbtree.c#btgettuple-kill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L226-L245), [nbtsearch.c#_bt_steppage-killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2049-L2051), [nbtree.c#btendscan-killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L424-L426), [selfuncs.c#get_actual_variable_endpoint-killed](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6388-L6397); `bt_multi_page_stats()`'s `dead_items` counts the line pointers marked dead ([btreefuncs.c#GetBTPageStatistics-items](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L172-L187)); measured on fixture E: 0 entries marked dead after the delete, then 22,590, 45,190, 67,790, 90,390 and 100,000 after plans 1 to 5, and 0 after a plain `VACUUM` |
| In a transaction started during recovery the probe neither marks rejected entries killed nor skips marked ones, so on a hot standby a dead run over more than 100 heap pages keeps the stale bound until the standby replays the entries' removal | [genam.c#RelationGetIndexScan-recovery](../../../../raw/postgres-17/src/backend/access/index/genam.c#L107-L119), [nbtsearch.c:1721](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1721), [nbtsearch.c:1850](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1850), [indexam.c#index_fetch_heap-kill](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L644-L652), [nbtxlog.c#btree_xlog_vacuum](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L598-L634); not measured: the script builds no standby |
| A probe that gives up leaves a stale row estimate; one that reaches a live entry moves the bound and corrects it | [selfuncs.c#ineq_histogram_selectivity-above-last-bound](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1162-L1168), [selfuncs.c#ineq_histogram_selectivity-flip-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1319-L1344), [costsize.c#clamp_row_est](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L202-L218); measured on fixture E: `id > 199990` stayed at `rows=10` for plans 1 to 4, `200000 * (1 - 9999.5 / 10000) = 10` from the stale bound 200000; plan 5 found 9,610 dead entries on 43 heap pages, reached `id` 100,000 and fell to `rows=1`, and the estimate stayed at 1 after `VACUUM` |
| Dead entries at the end of a B-tree add no page or level to the cost; they reach it only through the row estimate | [selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732), [selfuncs.c:6810](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6810), [selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810), [costsize.c#cost_index-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L795-L800), [cost.h#DEFAULT_SEQ_PAGE_COST](../../../../raw/postgres-17/src/include/optimizer/cost.h#L24-L28); measured on fixture E: the Index Only Scan at `0.42..4.59` for `rows=10` and `0.42..4.44` for `rows=1`, which rebuild as `4.0 + 0.42 + 10 * (0.005 + 0.0025) + 10 * 0.01 = 4.595` and `4.4375` |
| Fixture E's Index Only Scan totals carry no heap term although the delete cleared the visibility-map bits of its pages, because the planner reads the all-visible fraction from `pg_class.relallvisible`, which `VACUUM` and `ANALYZE` refresh from the map, as does an index build on the table; the stage runs neither, and builds no index, between the delete and plan 6, and the server runs with `autovacuum=off` | [heapam.c#heap_delete-clear-vm](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L3120-L3146), [plancat.c#get_relation_info-table-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L196-L202), [tableam.c#table_block_relation_estimate_size-allvisfrac](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L749-L760), [vacuumlazy.c#heap_vacuum_rel-relstats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L556-L575), [analyze.c#do_analyze_rel-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L623-L645), [index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135), [index.c#index_update_stats-relallvisible](../../../../raw/postgres-17/src/backend/catalog/index.c#L2851-L2928), [costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747), [costsize.c#cost_index-correlation-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L781-L800); measured `4.59` at `rows=10`, which leaves no room for the `4.00` one heap page would add |
| Four core AMs and contrib `bloom` use `genericcostestimate`; GIN and BRIN do not | [selfuncs.c:7073](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7073), [selfuncs.c:7221](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7221), [selfuncs.c:7265](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7265), [selfuncs.c:7320](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7320), [blcost.c#blcostestimate](../../../../raw/postgres-17/contrib/bloom/blcost.c#L22-L42); [selfuncs.c#gincostestimate-header](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7662-L7671), [selfuncs.c#brincostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8052-L8061) |
| A single contrib `bloom` scan is charged every index page; a repeated one over an index within its cache share is capped at the index's page count and spread over the loops | [blcost.c#blcostestimate](../../../../raw/postgres-17/contrib/bloom/blcost.c#L22-L42), [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732), [selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779), [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951); not measured |
| GiST/SP-GiST estimate height from page count | [selfuncs.c#gistcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7256-L7308), [selfuncs.c#spgcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7311-L7363) |
| Hash charges no descent cost | [selfuncs.c#hashcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7213-L7253) |
| `avg_leaf_density`/`leaf_fragmentation` ignore deleted pages | [pgstatindex.c#pgstatindex_impl-pages](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L331), [pgstatindex.c#pgstatindex_impl-density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L372); measured 89.18% on a 2,465-deleted-page index |
| Fragmentation contributes zero cost | no cost input carries it: `IndexOptInfo` has no fragmentation field ([pathnodes.h#IndexOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1120-L1128)) and the page charge is a flat pro-rata share of `pages` ([selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)); measured gap `1616.00` = `404 * 4.0` with 49.87% vs 0% fragmentation |
| Deleted pages stay in the fork | [nbtpage.c#_bt_unlink_halfdead_page-deleted](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2628-L2659), [README#placing-deleted-pages-in-the-fsm](../../../../raw/postgres-17/src/backend/access/nbtree/README#L383-L441); recycling goes through the FSM only ([nbtree.c:1168](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1168), [nbtpage.c:3050](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L3050), [nbtpage.c#_bt_allocbuf-fsm](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L901-L905)); measured 2,745 blocks after three VACUUMs; no `RelationTruncate()` or `smgrtruncate()` call exists under `src/backend/access/nbtree/` |
| VACUUM unlinks a deleted page from its siblings, so no later scan reaches it; a half-dead page stays in the chain and is read and skipped; the rightmost page of a level is never deleted | [nbtpage.c#_bt_unlink_halfdead_page-siblings](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2597-L2612), [README#half-dead](../../../../raw/postgres-17/src/backend/access/nbtree/README#L247-L259), [nbtsearch.c#_bt_readnextpage-step-right](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2207-L2219), [README#page-deletion-and-tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L362-L381); measured: fixture M's whole-index scan, which by that source walks only its 276 live leaves, is priced at `12730.42` like fixture B's over 2,733 live leaves. What either scan reads is not measured |
| A split takes its new right half from `_bt_allocbuf()`, which asks the FSM before extending the file, and only VACUUM records recyclable pages there, so an index with no deletions behind it appends every split | [nbtinsert.c:1720](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1720), [nbtpage.c#_bt_allocbuf](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L868-L988), [nbtpage.c:903](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L903), [nbtpage.c:978](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L978), [nbtree.c:1168](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1168), [nbtpage.c:3050](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L3050); nbtree asks the table AM which entries simple and bottom-up deletion may remove ([nbtpage.c:1526](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1526)); measured: fixture G's random-order index reads 49.87% `leaf_fragmentation` |
| Build and split policy set how full a page is left, not a density ceiling: a rightmost leaf split uses the leaf fillfactor, as does a leaf split that the "split after new item" optimization recognizes, unless it splits exactly after the new item; a rightmost internal split uses `BTREE_NONLEAF_FILLFACTOR` (70); every other split aims for an even balance and takes the lowest-penalty point near it; a page of many duplicates may split beside its group, and the last page of a single value splits at 96% | [nbtree.h#fillfactor-comment](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L197), [nbtsplitloc.c#_bt_findsplitloc-fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L334), [nbtsplitloc.c#_bt_deltasortsplits](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L561-L588), [nbtsplitloc.c#_bt_defaultinterval](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L852-L920), [nbtsplitloc.c#_bt_bestsplitloc](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L770-L812), [nbtsplitloc.c#_bt_split_penalty](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L1119-L1153), [nbtsplitloc.c#_bt_findsplitloc-many-duplicates](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L374-L405), [nbtsplitloc.c#_bt_strategy-many-duplicates](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L985-L1009), [nbtsplitloc.c#_bt_findsplitloc-single-value](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L389-L416), [nbtsplitloc.c#_bt_strategy-single-value](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L1011-L1041), [nbtree.h#BTREE_DEFAULT_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L200-L202); measured: fixture P's `tag` index read 91.47% after its build at the default fillfactor of 90 ([nbtree.h:200](../../../../raw/postgres-17/src/include/access/nbtree.h#L200)) and 98.01% after the unblocked churn |
| `_bt_strategy()` overrides a leaf split whose default interval cannot avoid a heap TID in the new high key: `SPLIT_MANY_DUPLICATES` for a page not entirely one value, and `SPLIT_SINGLE_VALUE` at 96% for the last page holding one value, whatever the fillfactor | [nbtsplitloc.c#split-strategies](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L364-L416), [nbtsplitloc.c#_bt_strategy](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L985-L1041), [nbtree.h:202](../../../../raw/postgres-17/src/include/access/nbtree.h#L202) |
| `fillfactor` and `deduplicate_items` take `ShareUpdateExclusiveLock` because they apply only to later inserts; GIN's `fastupdate` and per-index `gin_pending_list_limit` take `AccessExclusiveLock`, and `gin_clean_pending_list()` takes `RowExclusiveLock` | [reloptions.c#intRelOpts-fillfactor-btree](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L185-L194), [reloptions.c#deduplicate_items](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L167), [reloptions.c#fastupdate](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L123-L130), [reloptions.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L339-L347), [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1027-L1091) |
| Bloat can drop an index from a `BitmapAnd` | [indxpath.c#choose_bitmap_and](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1287-L1489); measured `c = 7` demoted to `Filter` |
| VACUUM can skip index vacuuming | [vacuumlazy.c#BYPASS_THRESHOLD_PAGES](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L85-L89), [vacuumlazy.c#lazy_vacuum-bypass](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1880-L1949), considered only under `INDEX_CLEANUP` `AUTO` and before any round of index vacuuming ([vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402), [vacuumlazy.c#lazy_scan_heap-bypass-off](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L894-L896), [vacuumlazy.c:1900](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1900)), [vacuumlazy.c#lazy_check_wraparound_failsafe](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2287-L2347) |
| `index_pages_fetched()` and `cost_index()` are unchanged since the v12 branch point, and `genericcostestimate()` changed in two commits | [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951), [costsize.c#cost_index](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L549-L821), [selfuncs.c#genericcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6626-L6828); `git log -L` with each function's line range over `615cebc94b..HEAD` lists no commit on `index_pages_fetched()`, only `8ce3aa9b59` and its revert `7854e07f25` on `cost_index()`, and only `9391f71523` and `5bf748b86b` on `genericcostestimate()`; the text at `615cebc94b` equals the pin's for the first two; `615cebc94b`'s parent is `9e1c9f9594`, "pgindent run prior to branching v12." |
| The SAOP clamp is new in v17 | [selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042); `git log -S'ceil(index->pages * 0.3333333)'` finds only `5bf748b86b`, which descends from `5bcc7e6dc8` (17devel); at `615cebc94b`, `btcostestimate()` has no clamp and charges its descents `costs.num_sa_scans` times |
| Against the v12 branch point, the clamp can only lower the descent count of a constant list in a boundary qual; an `= ANY` outside the boundary quals now adds no descents, where it added one per element then; a non-constant array is sized from its element statistics and can exceed the flat 10 used then | [selfuncs.c#estimate_array_length](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L2131-L2207), [selfuncs.c#estimate_array_length-statistics](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L2162-L2206), [selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042), [selfuncs.c#btcostestimate-bound-saop](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6904-L6989), [selfuncs.c#btcostestimate-boundary-saop](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6950-L6961), [selfuncs.c#btcostestimate-genericcost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7067-L7073), [selfuncs.c#genericcostestimate-num_sa_scans](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6657-L6679), [selfuncs.h#GenericCosts](../../../../raw/postgres-17/src/include/utils/selfuncs.h#L108-L138), [indxpath.c#match_saopclause_to_indexcol](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2651-L2669); at `615cebc94b`, `genericcostestimate()` multiplies the length of every `ScalarArrayOpExpr` among the index quals and `estimate_array_length()` returns 10 for a non-constant array; `9391f71523` descends from `5bcc7e6dc8`. Only the first case is measured (fixture I) |
| The 50.0 multiplier became a macro in v16 with no change in value | [selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145), [selfuncs.c:7104](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7104), [selfuncs.c:7299](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7299), [selfuncs.c:7354](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7354); `eb5c4e953b`'s diff replaces three literal `50.0` multipliers with `DEFAULT_PAGE_CPU_MULTIPLIER`; it descends from `d31d30973a` and not from `5bcc7e6dc8` |
| Deduplication is v13 | [nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L33-L58), [nbtsort.c#_bt_load-deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1151-L1152), [reloptions.c#deduplicate_items](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L167); `0d861bbb702`'s diff adds `nbtdedup.c`, build-time deduplication in `nbtsort.c` and the `deduplicate_items` reloption; it descends from `615cebc94b` and not from `d10b19e224`; measured 852 vs 2,749 blocks. An index `pg_upgrade` carried from v12 does not deduplicate until it is rebuilt, because only `CREATE INDEX` or `REINDEX` sets `btm_allequalimage` ([nbtree.h#btm_allequalimage-upgrade](../../../../raw/postgres-17/src/include/access/nbtree.h#L135-L141), [btree.sgml#deduplication-safety](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L834-L838), [nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183)), while bottom-up deletion runs before that test ([nbtinsert.c#_bt_delete_or_dedup_one_page-dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2782)); not measured |
| Deduplication at build and at insert also needs `allequalimage`, decided at `CREATE INDEX` or `REINDEX` from each key's operator class and collation; the build also skips unique indexes; the types the manual lists and every `INCLUDE` index never deduplicate | [btree.sgml#btree-deduplication-build](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L786-L797), [btree.sgml#deduplication](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L736-L800), [README#notes-about-deduplication](../../../../raw/postgres-17/src/backend/access/nbtree/README#L904-L948), [nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L33-L58), [nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183), [nbtsort.c#_bt_leafbuild-allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L560-L564), [nbtsort.c#_bt_load-deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1151-L1152), [nbtinsert.c#_bt_delete_or_dedup_one_page-dedup-gate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2778-L2781), [btree.sgml#deduplication-restrictions](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L834-L908); measured on fixture N: 852 against 2,749 blocks, both built after the load |
| The pre-split deduplication pass runs only after three exits have not fired, and the second exit returns without making room, so its page can split undeduplicated; the source relies on `allequalimage` being zero on an index `pg_upgrade` carried from 12 | [nbtinsert.c#early-returns](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2721-L2776), [nbtinsert.c#_bt_delete_or_dedup_one_page-dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2782), [nbtpage.c#_bt_metaversion-comment](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L720-L737) |
| Bottom-up deletion is v14 | `d168b666823`, first major version 14 by branch-point ancestry; [nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L280-L320), [btree.sgml#simple-vs-bottom-up](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L679-L703), [README#bottom-up-added-in-14](../../../../raw/postgres-17/src/backend/access/nbtree/README#L980-L981), [README#deduplication-and-bottom-up-note](../../../../raw/postgres-17/src/backend/access/nbtree/README#L980-L988); measured 543 vs 1,173 blocks on a 1,000-value column, and 1,020 vs 1,020 on a 100-value one |
| Newly deleted pages recyclable in the same VACUUM is v14 | `9dd963ae253`, first major version 14 by branch-point ancestry; [README#postgresql-14-fsm-change](../../../../raw/postgres-17/src/backend/access/nbtree/README#L403-L424) |
| `e5d8a99903` (first in 14) stores a 64-bit `safexid` in deleted pages and replaced `btm_oldest_btpo_xact` with `btm_last_cleanup_num_delpages`, which `_bt_vacuum_needs_cleanup()` compares with 5% of the index | [nbtree.h#BTDeletedPageData](../../../../raw/postgres-17/src/include/access/nbtree.h#L230-L236), [nbtree.h#BTMetaPageData](../../../../raw/postgres-17/src/include/access/nbtree.h#L103-L119), [nbtpage.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L172-L223); its diff replaces `btm_oldest_btpo_xact` with `btm_last_cleanup_num_delpages`; `d10b19e224` is an ancestor of `e5d8a99903` and `596b5af1d3` is not. Not measured |
| `9f3665fbfc` (first in 14) marks a cleanup-only B-tree VACUUM's count as estimated, so VACUUM no longer rewrites that index's `relpages` and `reltuples`, which it did at the v12 branch point; its message says `Backpatch: 13-`; `effdd3f3b6` restored `vacuum_cleanup_index_scale_factor` only as a deprecated storage parameter that no code reads | [nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L851-L893), [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099), [reloptions.c#vacuum_cleanup_index_scale_factor](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L462-L470), [nbtree.h:1134](../../../../raw/postgres-17/src/include/access/nbtree.h#L1134); `git log -S 'stats->estimated_count = true'` attributes that line to `9f3665fbfc`; `9f3665fbfc`'s diff adds `stats->estimated_count = true` to the cleanup-only path and removes `btvacuumscan()`'s `stats->estimated_count = false`; at `615cebc94b`, `lazy_cleanup_index()` calls `vac_update_relstats()` for the index when the count is not an estimate; `d10b19e224` is an ancestor of both commits and `596b5af1d3` of neither; both commit messages. Not measured |
| At the v12 branch point VACUUM skipped index vacuuming only on request, and skipped index cleanup with it; v14 added the automatic 2% bypass and the wraparound failsafe, and `3499df0dee8` made the setting tri-valued with `auto` as the default | [reloptions.c#vacuum_index_cleanup](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L510-L520), [vacuum.c#index_cleanup-default](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2155-L2179), [vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402), [vacuumlazy.c#lazy_vacuum-bypass-branch](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949), [vacuumlazy.c#lazy_check_wraparound_failsafe-clears](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326); at `615cebc94b`, `vacuumlazy.c` sets `useindex = (nindexes > 0 && params->index_cleanup == VACOPT_TERNARY_ENABLED)`; `3499df0dee8`'s diff turns the boolean `vacuum_index_cleanup` reloption into an enum; `5100010ee4d`, `1e55e7d1755` and `3499df0dee8` first in 14 by branch-point ancestry |
| `reltuples = -1` is v14, and an index holds it only after a rebuild through `reindex_index()` produced no entries; its catalog `relpages` is `0` then, so the new `reltuples >= 0` test never changes an index's branch | `3d351d916b2`, first major version 14 by branch-point ancestry, whose `index.c` diff adds the keep-`-1` hack; [plancat.c#estimate_rel_size-density](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1116-L1146), [pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L65-L66), [relcache.c#RelationSetNewRelfilenumber-reset](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3948-L3954), [index.c#reindex_index-rebuild](../../../../raw/postgres-17/src/backend/catalog/index.c#L3784-L3789), [index.c#index_build-index-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3133-L3135), [index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842); not measured |
| Plain `REINDEX`, `TRUNCATE`, `VACUUM FULL`, `CLUSTER`, a table-rewriting `ALTER TABLE` and a non-concurrent `REFRESH MATERIALIZED VIEW` rebuild each index through `reindex_index()`; `TRUNCATE`'s in-place path for a table new in the subtransaction can keep a `-1` but never sets one; `REINDEX CONCURRENTLY` builds through `index_create()` and starts at `0` and `0` | [tablecmds.c#ExecuteTruncateGuts-rewrite](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L2167-L2189), [vacuum.c:2260](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2260), [cluster.c:670](../../../../raw/postgres-17/src/backend/commands/cluster.c#L670), [tablecmds.c:5873](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L5873), [matview.c:890](../../../../raw/postgres-17/src/backend/commands/matview.c#L890), [cluster.c:1508](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1508), [index.c:4048](../../../../raw/postgres-17/src/backend/catalog/index.c#L4048), [tablecmds.c#ExecuteTruncateGuts-in-place](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L2133-L2145), [heap.c#RelationTruncateIndexes](../../../../raw/postgres-17/src/backend/catalog/heap.c#L3083-L3087), [index.c:1459](../../../../raw/postgres-17/src/backend/catalog/index.c#L1459), [index.c#index_create-pg_class](../../../../raw/postgres-17/src/backend/catalog/index.c#L1008-L1024); not measured |
| A B-tree build counts only the rows the heap scan hands it, and the scan skips rows dead to every transaction and rows that fail a partial index's predicate, so a rebuild can produce no entries on a table that is not empty | [nbtsort.c:599](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L599), [nbtsort.c:338](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L338), [heapam_handler.c#heapam_index_build_range_scan-dead](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1419-L1423), [heapam_handler.c#index-build-predicate](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1636-L1644); not measured |
| `71b66171d0` (first in 17.0) skips index statistics during binary upgrade, so an index that `pg_upgrade` creates keeps `relpages = 0` and `reltuples = 0` until `ANALYZE`, or a `VACUUM` whose index pass reports an exact count, writes its row; a cleanup-only B-tree pass writes nothing | [index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842), [analyze.c#do_analyze_rel-index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663), [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099), [nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L851-L893); `5bcc7e6dc8` is an ancestor of `71b66171d0`, which the `Stamp 17.0.` commit `d7ec59a63d` contains; not measured |
| For a partial B-tree whose rebuild produced no entries and which inserts then filled, both the v12 branch point and v17 take the width-based fallback, and v17, holding `relpages = 0`, skips the metapage discount and estimates one page's worth more | [plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160), [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486), [nbtsort.c#_bt_load-first-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1287-L1290); `3d351d916b2`'s diff: before it the reset wrote `reltuples = 0` (`relcache.c`); it adds the keep-`-1` rule (`index.c`) and the `reltuples >= 0` density test (`plancat.c`); the `if (relpages > 0)` metapage discount is unchanged; not measured |
| `3c569049b7b` (first in 16) lists partitioned indexes with `pages = 0`, `tuples = 0` and `tree_height = -1`, where the v12 branch point skipped them, so neither version sizes them | [plancat.c:471](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471), [plancat.c#get_relation_info-partitioned](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L502-L508); its diff removes the skip commented "Ignore partitioned indexes, since they are not usable for queries" and adds the guard; `d31d30973a` is an ancestor of `3c569049b7b` and `5bcc7e6dc8` is not |
| The endpoint probe's 100-heap-page limit is `9c6ad5eaa9` (2022-11-22), first in 16, whose message says "Back-patch to all supported branches"; before it the probe had no page limit and used `RecentGlobalXmin` as its horizon, which `dc7420c2c9` (first in 14) replaced with `GlobalVisTestFor()` | [selfuncs.c#VISITED_PAGES_LIMIT](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6447-L6455), [selfuncs.c#get_actual_variable_endpoint-give-up](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6409-L6413), [selfuncs.c#get_actual_variable_endpoint-horizon](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6415-L6416); `9c6ad5eaa9`'s diff adds `VISITED_PAGES_LIMIT` and the page counter; `dc7420c2c9`'s diff changes the `InitNonVacuumableSnapshot()` horizon from `RecentGlobalXmin`; `d31d30973a` is an ancestor of `9c6ad5eaa9` and `5bcc7e6dc8` is not; `git log -L` with `get_actual_variable_endpoint()`'s line range over `615cebc94b..HEAD` lists `9c6ad5eaa9`, `dc7420c2c9` and `d3751adcf1`; which 12.x releases carry the limit is under Open Questions; the v17 side is measured by fixture E |
| `19d8e2308b` (2023-03-20, first in 16) lets an `UPDATE` of only summarizing-index columns stay HOT and skip every non-summarizing index; the v12 branch point tested HOT against every indexed column, BRIN included, and told the executor to insert into all indexes or none | [relcache.c#RelationGetIndexAttrBitmap-summarizing](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L5390-L5398), [brin.c:269](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L269), [heapam.c#heap_update-attr-bitmaps](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L3434-L3437), [heapam.c#heap_update-hot-decision](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4140-L4166), [heapam.c#heap_update-update-indexes](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4415-L4429), [tableam.h#TU_UpdateIndexes](../../../../raw/postgres-17/src/include/access/tableam.h#L113-L127), [execIndexing.c#ExecInsertIndexTuples-onlySummarizing](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L361-L366); `d31d30973a` is an ancestor of `19d8e2308b` and `5bcc7e6dc8` is not; its message says it re-applies `5753d4ee32`, which `e3fcca0d0d` reverted, both descendants of the 15devel stamp `596b5af1d3` and not of the 16devel one; its diff replaces `INDEX_ATTR_BITMAP_ALL` in `heap_update()` with the hot-blocking and summarized bitmaps, and the boolean `update_indexes` with `TU_UpdateIndexes`; not measured |
| `4b754d6c16e` (2020-01-18, first in 13) made GIN's whole-index estimate fire only for a column with a full-scan key and no normal key; before it, any `GIN_SEARCH_MODE_ALL` key fired it | [selfuncs.c#gincost_pattern-searchmode](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7454-L7489), [selfuncs.c#gincostestimate-fullscan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7852-L7877); its diff removes `if (counts.haveFullScan \|\| indexQuals == NIL)`; `615cebc94b` is an ancestor of `4b754d6c16e` and `d10b19e224` is not; not measured |
| No test asserts the bloat charge | no `src/test` match for `tree_height`, `btcostestimate`, `genericcostestimate`; `btree_index.sql` builds and splits a fast root as a correctness test only ([btree_index.sql#multilevel-page-deletion](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L252-L270)); across the checkout's 794 expected `.out` files the only plan lines with numeric costs are [expected/inherit.out#parted_tab-update](../../../../raw/postgres-17/src/test/regress/expected/inherit.out#L697-L698) |
| No in-tree test asserts the endpoint probe or its limit | no file under `src/test`, `contrib` or `doc` names `get_actual_variable_range`, `get_actual_variable_endpoint`, `VISITED_PAGES_LIMIT` or `SnapshotNonVacuumable`; `git show --stat` lists only `selfuncs.c` for `fccebe421` and `9c6ad5eaa9`, and only source and header files for `3ca930fc3`; the conditions for reaching the probe are in [selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136) and [selfuncs.c#get_actual_variable_range-index-choice](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6179-L6239) |
| No test covers gate 0's `indcheckxmin` skip | no file under `src/test` mentions `indcheckxmin`, and its only `contrib` mention is `contrib/amcheck/verify_nbtree.c` |
| The `pgstatindex` test uses an empty index | [sql/pgstattuple.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L18-L37), [expected/pgstattuple.out#NaN](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L44-L82), [expected/pgstattuple.out#partition-index](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L264-L268), [pgstatindex.c#pgstatindex_impl-density-guards](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L372) |
| All four cost GUCs are `PGC_USERSET`, with defaults of 4.0, 0.0025, 524288 pages and 64 blocks | [guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696), [guc_tables.c#cpu_operator_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3719-L3729), [guc_tables.c#effective_cache_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3518), [guc_tables.c#min_parallel_index_scan_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3531-L3540), [cost.h:25](../../../../raw/postgres-17/src/include/optimizer/cost.h#L25), [cost.h:28](../../../../raw/postgres-17/src/include/optimizer/cost.h#L28), [cost.h:34](../../../../raw/postgres-17/src/include/optimizer/cost.h#L34) |
| `random_page_cost` multiplies only the index pages the estimate counts as fetched; B-tree upper levels are charged CPU only, BRIN's range-map pages `seq_page_cost`, and a tablespace setting replaces the GUC | [selfuncs.c#genericcostestimate-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6786), [selfuncs.c#btcostestimate-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7106), [selfuncs.c#brincostestimate-page-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8244-L8258), [spccache.c#get_tablespace_page_costs](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L181-L196), [selfuncs.c#genericcostestimate-tablespace](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6734-L6737) |
| Every setting the script sets has the context its header names: `shared_buffers`, `port`, `listen_addresses` and `unix_socket_directories` are `PGC_POSTMASTER`, `autovacuum` is `PGC_SIGHUP`, and the rest are `PGC_USERSET` | [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270), [guc_tables.c#port](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2393-L2401), [guc_tables.c#listen_addresses](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4436-L4445), [guc_tables.c#unix_socket_directories](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4425-L4434), [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457), [guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2070-L2079), [guc_tables.c#enable_seqscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L783-L792), [guc_tables.c#enable_indexscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L793-L802), [guc_tables.c#enable_indexonlyscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L803-L812), [guc_tables.c#enable_bitmapscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L813-L822), [guc_tables.c#enable_mergejoin](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L893-L902), [guc_tables.c#enable_hashjoin](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L903-L912), [guc_tables.c#effective_cache_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3518), [guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696), [guc_tables.c#cpu_operator_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3719-L3729), [guc_tables.c#max_parallel_workers_per_gather](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3419-L3428), [guc_tables.c#max_parallel_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3430-L3439), [guc_tables.c#min_parallel_table_scan_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3520-L3529), [guc_tables.c#parallel_tuple_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3730-L3740), [guc_tables.c#parallel_setup_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3741-L3751), [guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585), [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631), [guc_tables.c#application_name](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4644-L4653) |
| `ceil()` charges a lookup of `k` estimated rows one page while `k * pages <= tuples`, so a one-row lookup is charged `ceil(pages / tuples)` pages once pages outnumber rows | [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732), [selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732); measured on fixture F: `12.29` on 2,745 blocks over 1,000 rows, `4.29` after `REINDEX`; fixture P's 200-row bitmap scans are charged one page at 543 blocks and two at 1,173, `5.92` against `9.92` |
| Page deletion can lower the planner's height without a rebuild | [nbtpage.c#_bt_unlink_halfdead_page-fastroot](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2565-L2659), [README#page-deletion-and-tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L362-L381); measured `tree_level` 2 against `fastlevel` 1, startup `0.42` -> `0.28` |
| The whole-index closed form holds for a single whole-index, all-visible index-only scan with one constant index qual, and it has no standalone `qual_op_cost` term | [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486), [tableam.c#table_block_relation_estimate_size-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L711-L747), [nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717), [selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810), [costsize.c#cost_index-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L795-L800); `predict()` equals `EXPLAIN` on 7 of 7 whole-index scans |
| A plugin can rewrite `pages`, `tuples` and `tree_height` before costing | [plancat.c#get_relation_info_hook](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L570-L576), [plancat.h#get_relation_info_hook_type](../../../../raw/postgres-17/src/include/optimizer/plancat.h#L20-L25); `gincostestimate()` skips the metapage read for a hypothetical index ([selfuncs.c#gincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7697-L7711)), and the endpoint probe skips a hypothetical index ([selfuncs.c#get_actual_variable_range-skips](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6196-L6212)); not exercised |
| The statistics hooks move the page charge through selectivity, and `set_rel_pathlist_hook` can delete or modify costed paths | [selfuncs.c#examine_variable-get_index_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5203-L5204), [selfuncs.c#examine_simple_variable-get_relation_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5375-L5376), [selfuncs.c#btcostestimate-stats-hooks](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7116-L7171), [selfuncs.c#brincostestimate-get_relation_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8135-L8136), [selfuncs.c#brincostestimate-get_index_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8166-L8167), [allpaths.c#set_rel_pathlist_hook](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L532-L539); not exercised |
| `cost_index()` calls the index AM's `amcostestimate` through the pointer `get_relation_info()` copied into `IndexOptInfo`, and a custom AM gets `tree_height = -1` | [costsize.c#cost_index-amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L610-L621), [plancat.c#amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L331-L332), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500); not exercised |
| A predicate-implied clause is dropped from a partial index's quals | [indxpath.c#check_index_predicates-indrestrictinfo](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L3318-L3378), [indxpath.c#match_restriction_clauses_to_index](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1968-L1974); measured `500.00` = `200000 * cpu_operator_cost` between the plain and the partial twin |
| `ANALYZE` reads every fixture row at `default_statistics_target = 10000` | [analyze.c#std_typanalyze-minrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1876-L1894); every run of the filed script agrees on every recorded value; see [Last run](#last-run) |
| GIN's startup/total split never reaches a plan | [costsize.c#cost_bitmap_heap_scan-startup](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1044-L1048), [ginutil.c:79](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L79) |
| `pgstatindex` rejects every non-B-tree relation | [pgstatindex.c#pgstatindex_impl-btree-check](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L228), [sql/pgstattuple.sql#wrong-index-type](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L55-L63) |
| Nothing on the cost path reads the FSM | no file under `src/backend/optimizer/`, and neither `selfuncs.c` nor contrib `bloom`'s `blcost.c`, includes `freespace.h` or calls an FSM function: `/usr/bin/grep -rn -i -E 'freespace\|GetFreeIndexPage\|RecordFree\|GetRecordedFreeSpace\|fsm'` over those paths on the pin returns nothing; the planner's block count is the main fork's alone ([bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L280-L281)) |
| A GIN *clause* is discarded at clause matching when the operator is not in its opfamily; the *index* is not necessarily discarded with it | [indxpath.c#match_opclause_to_indexcol-op_in_opfamily](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2433-L2459); core GIN families carry no `<`/`<=`/`>=`/`>` ([pg_amop.dat#gin-array_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1232-L1244), [pg_amop.dat#gin-tsvector_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1290-L1296), [pg_amop.dat#gin-jsonb_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1593-L1611), [pg_amop.dat#gin-jsonb_path_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1613-L1622)); but `build_index_paths()` still generates a path on `useful_predicate` alone ([indxpath.c#build_index_paths-generate](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L954-L962)), and GIN's `amoptionalkey = true` removes the only hard stop ([indxpath.c#build_index_paths-amoptionalkey](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L887-L897), [ginutil.c:49](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L49)); measured on the keyless partial GIN path |
| One GIN measurement here is priced with the array cache adjustment, not without it | `n IN (1,2,3)` sets `counts.arrayScans = 3` ([selfuncs.c#gincost_scalararrayopexpr-arrayScans](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7648-L7658)), which satisfies the `outer_scans > 1 \|\| counts.arrayScans > 1` test ([selfuncs.c#gincostestimate-cache-effects](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7957-L7974)); the recorded plan carries `Index Cond: (n = ANY ('{1,2,3}'::integer[]))` on the GIN index |
| The GIN array cache branch does not depend on `amsearcharray`, which only routes the array clause through the `ST_BITMAPSCAN` retry | [selfuncs.c#gincostestimate-saop-clause](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7823-L7833), [selfuncs.c#gincost_scalararrayopexpr-arrayScans](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7648-L7658), [indxpath.c#build_index_paths-saop](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L862-L885), [indxpath.c#get_index_paths-nonnative-saop](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L753-L766) |
| The two-`random_page_cost` page-charge probe is invalid on an index whose tablespace overrides `random_page_cost` | [spccache.c#get_tablespace_page_costs](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L181-L196) returns the reloption and ignores the GUC; [selfuncs.c#gincostestimate-tablespace-costs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7786-L7789) is what GIN calls; the filed block now checks for the override first and reported `pg_default` with no override on the measurement server |
| `btree_gin` adds strategies 1-5 but is documented not to outperform B-tree | [btree_gin--1.0.sql#int4_ops](../../../../raw/postgres-17/contrib/btree_gin/btree_gin--1.0.sql#L56-L69), [btree-gin.sgml#caveats](../../../../raw/postgres-17/doc/src/sgml/btree-gin.sgml#L24-L33) |
| A bare boolean `Var` still matches a GIN bool opclass in v17 | [indxpath.c#IsBooleanOpfamily](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2271-L2286), [indxpath.c#match_boolean_index_clause](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2288-L2384), [bool.out#gin-bool-equality](../../../../raw/postgres-17/contrib/btree_gin/expected/bool.out#L89-L98); measured `38.26` for `i`, `i = true` and `i IS TRUE` |
| GIN yields no plain index scan, no pathkeys, no index-only scan, no `IS NULL`, no native array scan, and no partial index path of its own | [ginutil.c#ginhandler](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L36-L89), with `NULL` `amcanreturn` and `amgettuple` ([ginutil.c:70](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L70), [ginutil.c:79](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L79)) copied by [plancat.c#get_relation_info-am-flags](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L317-L335), against B-tree's handler ([nbtree.c:143](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L143), [nbtree.c#bthandler-amcanorder](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L108-L109), [nbtree.c:134](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L134), [nbtree.c:115](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L115), [nbtree.c:114](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L114), [nbtree.c:119](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L119)), [indxpath.c#get_index_paths-submit](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L740-L751), [indxpath.c#build_index_paths-pathkeys](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L905-L944), [indxpath.c#check_index_only](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1730-L1800), [indxpath.c#match_clause_to_indexcol-nulltest](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2251-L2266), [amutils.out#index-properties](../../../../raw/postgres-17/src/test/regress/expected/amutils.out#L122-L129); measured: `ORDER BY` and `IS NULL` as `disable_cost` sequential scans, and the index-only case as a `Bitmap Heap Scan` at `119.83` |
| GIN charges every pending, entry and data page at `random_page_cost` plus `50 * cpu_operator_cost` | [selfuncs.c#gincostestimate-page-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7937-L7955), [selfuncs.c#gincostestimate-random-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7976-L7980), [selfuncs.c#gincostestimate-search-entry-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8008-L8015), [selfuncs.c#gincostestimate-total](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8027-L8029); measured `12.97` GIN vs `4.52` B-tree on identical statistics, both reconciled by hand to the cent from the recorded counters |
| On a single scan every pending page is charged in full, `4.25` per page of total cost at default settings, `4.125` of it as startup cost | [selfuncs.c#gincostestimate-pending](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7882-L7886), [selfuncs.c#gincostestimate-random-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7976-L7980), [selfuncs.c#gincostestimate-page-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7937-L7955), [selfuncs.c#gincostestimate-total](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8027-L8029); measured 736 pending pages moving the GIN scan from `13.01` to `3141.12` inside a `BitmapAnd` the planner kept, charged `739.00` pages (736 pending, 2 entry and 1 data page), and 1,471 pages moving it to `6264.98` and out of the `BitmapAnd` |
| `gin_clean_pending_list()` drains the list but leaves `nTotalPages` stale | [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1027-L1091), [selfuncs.c#gincostestimate-scale-or-invent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7767); only [gininsert.c:406](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L406) and [ginvacuum.c:789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L789) call `ginUpdateStats()`; measured 2,073 live blocks against a metapage still reading 302 |
| An `ANALYZE` run by an autovacuum worker flushes the GIN pending list in its final index-cleanup step, only as far as the tail page recorded when the flush begins, and leaves the metapage counters stale; a manual `ANALYZE` leaves the list alone | [ginvacuum.c#ginvacuumcleanup-analyze-only](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L717), [analyze.c#do_analyze_rel-index-cleanup](../../../../raw/postgres-17/src/backend/commands/analyze.c#L694-L721), [analyze.c:527](../../../../raw/postgres-17/src/backend/commands/analyze.c#L527), [ginfast.c:847](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L847), [ginfast.c#ginInsertCleanup-stop-at-tail](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L881-L888), [gin.sgml#fast-update-flush](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L508-L515), [ginvacuum.c:789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L789); not measured |
| `gincostestimate()` scales the last-`VACUUM` counters by `numPages / nTotalPages`, rounding up, and clamps them to the non-pending pages while the index has a page, the total, entry-page and entry counts are nonzero (the data-page count may be zero), and `nTotalPages` is at most the index and more than a quarter of it; otherwise it invents them from the live block count, at least 10 pages, 90% of them entry pages holding 100 entries each | [selfuncs.c#gincostestimate-stats-branch](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7729-L7747), [selfuncs.c#gincostestimate-invented](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7748-L7767), [selfuncs.c#gincostestimate-scale-or-invent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7767), [selfuncs.c#gincostestimate-trust](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7727); measured on fixture T: 1,369 live blocks against a metapage reading 2, charged 4 pages; on fixture D at 736 pending pages: entry pages `ceil(273 * 1038 / 302) = 939` clamped to 302 and data pages `97` clamped to 0 |
| `gincostestimate()` uses the pending-page count only while it is below `index->pages`, and its data-page floor needs a nonzero selectivity and a nonzero `index->tuples` | [selfuncs.c#gincostestimate-pending-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7724-L7727), [selfuncs.c#gincostestimate-datapages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7982-L8006), [selfuncs.c:7675](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7675); measured: one floor data page on every trusted-statistics row of the page-charge table |
| A keyless partial GIN path is priced as a whole-index scan | [selfuncs.c#gincostestimate-fullscan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7852-L7877), [indxpath.c#build_index_paths-amoptionalkey](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L887-L897); measured `1001.00` charged pages on a 10-block index |
| GIN rejects unique, `INCLUDE`, exclusion and `CLUSTER` | [indexcmds.c#DefineIndex-am-checks](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L860-L879), [cluster.c#check_index_is_clusterable-amclusterable](../../../../raw/postgres-17/src/backend/commands/cluster.c#L517-L522); all four messages reproduced |
| A multicolumn GIN can beat a `BitmapAnd` of GIN + B-tree | [btree-gin.sgml#caveats](../../../../raw/postgres-17/doc/src/sgml/btree-gin.sgml#L24-L33); measured `21.51` versus `240.13` |
| No test asserts a GIN or B-tree index cost, and no test plan can choose between a GIN and a B-tree on one column | no expected output under `src/test` or `contrib` prints a numeric cost for an index or bitmap node: the only plan-node costs are [expected/inherit.out#parted_tab-update](../../../../raw/postgres-17/src/test/regress/expected/inherit.out#L697-L698); no match for `gincostestimate` in either tree; `jsonb.sql` drops the GIN `jidx` before creating the B-tree `jidx` ([jsonb.sql:852](../../../../raw/postgres-17/src/test/regress/sql/jsonb.sql#L852), [jsonb.sql:929](../../../../raw/postgres-17/src/test/regress/sql/jsonb.sql#L929), [jsonb.sql:932](../../../../raw/postgres-17/src/test/regress/sql/jsonb.sql#L932)); every `btree_gin` `EXPLAIN` uses `COSTS OFF` ([bool.sql#explain-costs-off](../../../../raw/postgres-17/contrib/btree_gin/sql/bool.sql#L23-L26)) |
| The planner's tree height can be a stale per-backend cached copy of the metapage, until an invalidation or a failed cache check discards it | [nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717) caches `BTMetaPageData` in `rel->rd_amcache`, never caches an index with no root, and its comment declines to refresh the cache; scans and inserts fill the same cache ([nbtpage.c#_bt_getroot-cache](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L523-L528), [nbtpage.c#_bt_metaversion-cache](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L773-L775)). Three events discard it: relcache invalidation ([relcache.c#RelationCacheInvalidateEntry](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2975-L2985), [relcache.c#RelationFlushRelation](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2916-L2924), [relcache.c#RelationClearRelation](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2600-L2603)), `_bt_getroot()` rejecting a cached fast root that is deleted or half-dead ([nbtree.h:225](../../../../raw/postgres-17/src/include/access/nbtree.h#L225)), at another level, or not alone on its level ([nbtpage.c#_bt_getroot-stale-cache](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L380-L403)), and the unconditional flush in [nbtpage.c#_bt_gettrueroot-flush](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L592-L600). No fixture reads a stale height: every measurement is planned in a session opened after the last change to its index |
| The `pg_class` writes that VACUUM and `ANALYZE` make for an index reach a planning backend as a relcache invalidation; a root split, a split that moves the fast root up, an unchanged row, and a VACUUM that writes no index row send none | VACUUM writes an index's row only from exact counts with index cleanup on ([vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099), [vacuumlazy.c#heap_vacuum_rel-index-stats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L512-L513)), and `ANALYZE` writes every index's row ([analyze.c#do_analyze_rel-index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663)). Both are in-place updates ([vacuum.c#vac_update_relstats-inplace](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1545-L1548)) that register an invalidation for the index's own entry ([heapam.c:6668](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6668), [inval.c#CacheInvalidateHeapTupleCommon-pg_class](../../../../raw/postgres-17/src/backend/utils/cache/inval.c#L1383-L1392), [inval.c:1447](../../../../raw/postgres-17/src/backend/utils/cache/inval.c#L1447)), send it after the write ([heapam.c#heap_inplace_update_and_unlock-send](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6888-L6892)) and discard it when the row is unchanged ([vacuum.c#vac_update_relstats-dirty](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1446-L1461), [heapam.c#heap_inplace_unlock](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6914-L6920)); the planner's index lock absorbs it ([plancat.c:253](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L253), [lmgr.c#LockRelationOid-accept](../../../../raw/postgres-17/src/backend/storage/lmgr/lmgr.c#L134-L138)), as [README#metapage-cache](../../../../raw/postgres-17/src/backend/access/nbtree/README#L776-L790) expects. A root split writes only index pages ([nbtinsert.c#_bt_newlevel-root-level](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2507-L2513), [nbtinsert.c#_bt_newlevel-metapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2515-L2519)), and splitting the only page of a level below the true root rewrites the fast root in the metapage alone ([nbtinsert.c#_bt_insertonpg-fastroot](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1250-L1295), [README#page-deletion-and-tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L362-L381)). A B-tree VACUUM that never called `btbulkdelete()`, because it collected no dead items or bypassed index vacuuming, gets no statistics or estimated ones and writes no row ([nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L851-L893), [vacuumlazy.c#lazy_scan_heap-lazy_vacuum-call](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1051-L1052), [vacuumlazy.c#lazy_vacuum-bypass-branch](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949)). Read from source; not measured |
| `leaf_fragmentation` counts backward sibling links only, not physical adjacency | [pgstatindex.c#pgstatindex_impl-fragments](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323) |
| An `UPDATE` of only summarizing-index columns adds no entry to a B-tree, but only while the new version fits on the old page | the whole HOT decision is inside `if (newbuf == buffer)` and the `else` branch only hints the page full ([heapam.c#heap_update-hot-decision](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4140-L4166)); a non-HOT update reports `TU_All` ([heapam.c:4429](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4429)); otherwise [heapam.c#heap_update-update-indexes](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4415-L4429), [tableam.h#TU_UpdateIndexes](../../../../raw/postgres-17/src/include/access/tableam.h#L113-L127), [nodeModifyTable.c#ExecUpdateEpilogue-onlySummarizing](../../../../raw/postgres-17/src/backend/executor/nodeModifyTable.c#L2162-L2166), [execIndexing.c#ExecInsertIndexTuples-onlySummarizing](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L361-L366) |
| A non-HOT update skips every partial index whose predicate the new row fails, and still inserts into every other index that accepts the row | [execIndexing.c#ExecInsertIndexTuples-predicate](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L368-L387), [execIndexing.c#ExecInsertIndexTuples-loop](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L343-L387), [heapam.c:4429](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4429) |
| The 2% bypass skips index vacuuming but still runs index cleanup | [vacuumlazy.c#lazy_vacuum-bypass-branch](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949) clears only `do_index_vacuuming`; [nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L851-L893) can still scan and recycle; [ginvacuum.c#ginvacuumcleanup-pending](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L719-L729) flushes the pending list whenever `ginbulkdelete()` was not called, which also covers every VACUUM that collected no dead items ([vacuumlazy.c#lazy_vacuum-call](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1066)), and `ginbulkdelete()` flushes it on its first call ([ginvacuum.c#ginbulkdelete-pending](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L591-L602)) |
| The wraparound failsafe clears `do_index_cleanup` too, so it does stop cleanup | [vacuumlazy.c#lazy_check_wraparound_failsafe-clears](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326) |
| `fillfactor` reaches existing pages at their next rightmost or split-after-new-item leaf split, and `deduplicate_items` at their next pre-split deduplication pass, without a rebuild | [nbtsplitloc.c#leaffillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L170-L176), [nbtinsert.c#_bt_delete_or_dedup_one_page-dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2782), [nbtsort.c#_bt_leafbuild-allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L560-L564) |
| `IndexOptInfo` is not the whole size input for every AM: GIN and BRIN reopen the index for metapage values, and only GIN's track bloat; BRIN's are `pagesPerRange` and the revmap page count, which grows with the heap's ranges | [selfuncs.c:7674](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7674), [selfuncs.c:8063](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8063), [selfuncs.c#gincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7697-L7711), [selfuncs.c#gincostestimate-scale-or-invent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7767), [selfuncs.c#brincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8086-L8101), [brin.c#brinGetStats](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1638-L1654), [brin.h#BrinStatsData](../../../../raw/postgres-17/src/include/access/brin.h#L32-L36), [brin_revmap.c#HEAPBLK_TO_REVMAP_BLK](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L35-L43), [brin_revmap.c#revmap_extend_and_get_blkno](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L494-L514) |
| `FormData_pg_class` is cpp output of the `CATALOG()` macro, not a `genbki.pl` product | [genbki.h:23](../../../../raw/postgres-17/src/include/catalog/genbki.h#L23), [pg_class.h#CATALOG](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L21-L32), [pg_class.h#NOTES](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L11-L16) |
| The cost path and the endpoint probe compile against generated catalog headers: the `RELKIND_*` letters from `pg_class.h`'s client-code block, which `genbki.pl` copies into `pg_class_d.h`, and `BTREE_AM_OID`, an `oid_symbol` in `pg_am.dat` | [plancat.c:471](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471), [plancat.c:488](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488), [selfuncs.c:6197](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6197), [pg_class.h#RELKIND_INDEX-and-RELKIND_PARTITIONED_INDEX](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L162-L173), [Catalog.pm#client_code](../../../../raw/postgres-17/src/backend/catalog/Catalog.pm#L61-L66), [Catalog.pm#client_code-push](../../../../raw/postgres-17/src/backend/catalog/Catalog.pm#L197-L205), [genbki.pl#client_code](../../../../raw/postgres-17/src/backend/catalog/genbki.pl#L563-L567), [pg_am.dat:18](../../../../raw/postgres-17/src/include/catalog/pg_am.dat#L18), [genbki.pl#oid_symbol](../../../../raw/postgres-17/src/backend/catalog/genbki.pl#L675-L687) |
| `036decbba2a`, first contained in the `Stamp 17.7.` commit, added a `BTPageOpaqueData` size check to `pgstattuple`'s B-tree page handling; it changes `pgstattuple()` output, not `pgstatindex()` | [pgstattuple.c#pgstat_btree_page-checks](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L419-L425) |
| A serial GIN bitmap index scan can feed a `Parallel Bitmap Heap Scan` | [indxpath.c:347](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L347), [allpaths.c#create_partial_bitmap_paths](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4162-L4185); the bitmap is built once and shared, and each participant takes the next heap page from one shared iterator ([nodeBitmapHeapscan.c#BitmapShouldInitializeSharedState](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L774-L806), [nodeBitmapHeapscan.c#BitmapHeapNext-shared-bitmap](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L130-L141), [nodeBitmapHeapscan.c#shared-iterator](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L143-L170), [nodeBitmapHeapscan.c:241](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L241), [tidbitmap.c#tbm_shared_iterate](../../../../raw/postgres-17/src/backend/nodes/tidbitmap.c#L1044-L1136)); not measured |
| On a repeated GIN scan the pending-page I/O charge is amortized and the per-page CPU charge is not | [selfuncs.c#gincostestimate-cache-effects](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7957-L7974), [selfuncs.c:7980](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7980), [selfuncs.c#gincostestimate-page-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7937-L7955) |
| `gin_pending_list_limit` triggers a non-forced cleanup after the insert, and is not a ceiling | [ginfast.c#needCleanup](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L448-L471), [ginfast.c#ginInsertCleanup-conditional-lock](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L818-L828), [gin.sgml#fast-update](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L503-L529); the reference entry and GUC description call it a "maximum size" ([config.sgml#guc-gin-pending-list-limit](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L9870-L9890), [guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585)), filed under Open Questions |
| `fastupdate = off` does not flush the entries already in the pending list | [ref/create_index.sgml#fastupdate-note](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L524-L532) |
| `enable_bitmapscan = off` adds `disable_cost` and does not remove the bitmap path | [costsize.c#cost_bitmap_heap_scan-disable](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1041-L1042) |
| Gate 3 is a comparison of computed costs, not a rule that GIN loses | [indxpath.c#choose_bitmap_and-cheapest-of-group](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1353-L1399), [pathnode.c#add_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L419-L622); measured: a multicolumn GIN at `21.51` beating a `BitmapAnd` at `240.13` |
| For two indexes on the identical clause set, `choose_bitmap_and()` keeps the lower `amcostestimate` total plus `0.1 * cpu_operator_cost` per row, and the row term is the same for both (`baserel->rows`), not the `rows` figure `EXPLAIN` prints; on a tie the path met first stays, and the B-tree's plain paths still compete in `add_path()` | [indxpath.c#choose_bitmap_and-cheapest-of-group](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1353-L1399), [costsize.c:628](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L628), [costsize.c#cost_bitmap_tree_node-indexpath](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1114-L1128), [costsize.c#cost_index-rows](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L589-L604), [createplan.c#create_bitmap_subplan-indexpath](../../../../raw/postgres-17/src/backend/optimizer/plan/createplan.c#L3480-L3485), [indxpath.c#get_index_paths-submit](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L740-L751); measured on fixture S: the planner chose the B-tree for `n = 42`, `n BETWEEN 100 AND 200` and `n < 20` |
| For indexes on different clauses, an index joins an AND group only when the whole bitmap-heap-scan estimate drops, and `add_path()` then compares whole paths | [indxpath.c#choose_bitmap_and-accept-reject](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1418-L1489), [indxpath.c#bitmap_scan_cost_est](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1526-L1553), [indxpath.c#bitmap_and_cost_est](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1560-L1571), [pathnode.c#add_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L419-L622); measured on fixture D at 736 pending pages: the GIN estimate `3141.12` against the B-tree's `168.80`, kept because the `BitmapAnd` plan, `3321.93`, is below the B-tree-only plan, `3486.80` |
| Gate 0: `get_relation_info()` builds no `IndexOptInfo` for an index that is not `indisvalid`, and skips an `indcheckxmin` index whose `pg_index` row does not precede `TransactionXmin`, marking the plan transient; a cached transient plan is planned again when `TransactionXmin` changes | [pg_index.h#indisvalid](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L42-L43), [plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281), [plancache.c#BuildCachedPlan-transient](../../../../raw/postgres-17/src/backend/utils/cache/plancache.c#L1022-L1033), [plancache.c#CheckCachedPlan-transient](../../../../raw/postgres-17/src/backend/utils/cache/plancache.c#L866-L873), [README.HOT#indcheckxmin](../../../../raw/postgres-17/src/backend/access/heap/README.HOT#L341-L353); a failed `CREATE INDEX CONCURRENTLY` leaves an invalid index ([ref/create_index.sgml#invalid-index](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L645-L667), [ref/create_index.sgml#concurrently-invalid](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L646-L651)); not measured |
| `index_build()` sets `indcheckxmin` only for a non-concurrent `CREATE INDEX` that met broken HOT chains; `reindex_index()` clears it after a rebuild that met none, and otherwise keeps it on a valid index and sets it on an invalid, not-ready or dead one | [index.c#index_build-indcheckxmin](../../../../raw/postgres-17/src/backend/catalog/index.c#L3099-L3101), [index.c#reindex_index-indcheckxmin](../../../../raw/postgres-17/src/backend/catalog/index.c#L3800-L3850); not measured |
| A partial index whose predicate the query's restrictions do not imply is skipped before clause matching and left to `generate_bitmap_or_paths()`; with `build_index_paths()`'s missing-scan-type return, these are the hard stops that do not depend on clause matching | [indxpath.c#check_index_predicates-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L3272-L3350), [indxpath.c#create_index_paths-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L260-L266), [pathnodes.h:1168](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1168), [pathnodes.h:1181](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1181), [indxpath.c#build_index_paths-scantype](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L826-L842); not measured |
| Exhaustive sampling removes sampling noise; the independence assumption survives it, and so do changes made after `ANALYZE` | [clausesel.c#clauselist_selectivity_ext-multiply](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L253-L263), [clausesel.c#clauselist_selectivity_ext-one-sided](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L329-L333); a column whose every sampled value repeats and fits the target gets a complete MCV list ([analyze.c#compute_scalar_stats-stadistinct](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2550-L2560), [analyze.c#compute_scalar_stats-complete-mcv](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2614-L2636)); measured on fixture L3, 250, 24,971 and 12 estimated against 250, 24,971 and 12 actual, where the conjunction's match is the seed's (independence predicts 12.49 on average), and on fixture D, 80, 19,999 and 4 estimated against 80, 20,000 and 4 actual, where the conjunction is exact by construction. Fixtures Q and E change their tables after `ANALYZE` on purpose: Q estimates 40,000 rows for 20,000 live ones, and E 10 for none. No fixture here violates the independence assumption |
| An `INDEX_CLEANUP ON` VACUUM forces index vacuuming, not cleanup | [vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402), [vacuumlazy.c#lazy_vacuum-bypass-branch](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949) |
| BRIN charges every index page on every scan: the range-map pages at `seq_page_cost` as startup cost, the rest at `random_page_cost`, both multiplied by `loop_count` with no cache model, so BRIN bloat reaches the cost only through `index->pages` | [selfuncs.c:8063](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8063), [selfuncs.c#brincostestimate-page-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8244-L8258), [brin.c#brinGetStats](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1638-L1654); not measured |
| Bloat flips a plan to a sequential scan | measured on fixture A: `Index Scan` at `9590.42` on the dense index against `Seq Scan` at `22353.00` on the bloated twin, for the same 25% range; `22353.00` is 7,353 heap pages at `seq_page_cost` plus 1,000,000 rows at `cpu_tuple_cost` and two operator evaluations each ([costsize.c#cost_seqscan](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L315-L322)) |
| An index-only scan of an all-visible table pays no heap I/O but still `cpu_tuple_cost` per expected row | [costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747), [costsize.c#cost_index-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L795-L800); measured: fixture A's whole-index totals each carry `10000.00`, so the 9.62x larger index costs 6.12x more on the index alone (`113144.43` against `18480.42`) and 4.32x in total |
| Fixture I pays one random heap page per scan at every array length because its heap is in key order | [costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747), [costsize.c#cost_index-correlation-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L781-L800) |
| Blocks per row price plans but do not predict what `REINDEX` returns: the rebuild reapplies the index's `fillfactor` and `deduplicate_items`, and a partial index's population is the sampled rows that pass its predicate | [index.c#reindex_index-rebuild](../../../../raw/postgres-17/src/backend/catalog/index.c#L3784-L3789), [nbtsort.c:665](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L665), [nbtsort.c#_bt_pagestate-leaf-fill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L661-L665), [nbtsort.c#_bt_load-deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1151-L1152), [nbtree.h#BTGetFillFactor-BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1150), [analyze.c#partial-index-population](../../../../raw/postgres-17/src/backend/commands/analyze.c#L902-L908), [analyze.c#tupleFract](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953); measured on fixture L3: `REINDEX` at `fillfactor = 10` turned 427 blocks into 3,801. That `n_off` and `a_sparse_idx` would rebuild at about their current size is a source reading; neither is rebuilt, and the reading is not scored against [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md) |
| This page's *bloat* is broader than the manual's: an index with deduplication off and a GIN pending list fit only the broad sense; the pending list is deferred insert work, yet a single GIN scan is charged for every pending page | [glossary.sgml#Bloat](../../../../raw/postgres-17/doc/src/sgml/glossary.sgml#L242-L250), [btree.sgml#deduplication](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L736-L800), [gin.sgml#fast-update](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L503-L529), [gin.sgml#fast-update-flush](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L508-L515), [selfuncs.c#gincostestimate-pending](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7882-L7886), [selfuncs.c#gincostestimate-random-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7976-L7980); the pending list is not scored as waste under [Mandatory GIN Bloat Tests (unverified)](../../common-concepts/mandatory-gin-bloat-tests.md) |
| `CLUSTER` on a B-tree prices a whole-index scan, charged every index page unless the table's estimate is one row or less, against a sorted sequential scan, so bloat pushes it toward the sort without deciding it; `enable_indexscan = off` or an index missing from the planner's list forces the sort | [cluster.c#plan_cluster_use_sort-call](../../../../raw/postgres-17/src/backend/commands/cluster.c#L948-L951), [planner.c#plan_cluster_use_sort](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6761-L6874), [planner.c#plan_cluster_use_sort-compare](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6861-L6873), [planner.c#plan_cluster_use_sort-short-circuits](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6788-L6841), [selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019), [cluster.c#check_index_is_clusterable-partial](../../../../raw/postgres-17/src/backend/commands/cluster.c#L525-L534), [selfuncs.c#genericcostestimate-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6786), [costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747); not measured |
| `RelOptInfo.tuples`, filled by `estimate_rel_size()`, is copied into a non-partial index and caps a partial one; `consider_bypass_optimization` gates the 2% bypass; `AttStatsSlot` carries the histogram bounds the probe overwrites | [pathnodes.h#RelOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L941-L944), [plancat.c:201](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L201), [plancat.c:476](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L476), [plancat.c:484](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L484), [vacuumlazy.c:1900](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1900), [vacuumlazy.c#LVRelState](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L148-L156), [lsyscache.h#AttStatsSlot](../../../../raw/postgres-17/src/include/utils/lsyscache.h#L46-L62) |
| The caller and callee path from `query_planner()` through `get_relation_info()`, `create_index_paths()`, `cost_index()` and the AM's `amcostestimate`, and from `clauselist_selectivity()` to the endpoint probe | [planmain.c:170](../../../../raw/postgres-17/src/backend/optimizer/plan/planmain.c#L170), [initsplan.c:165](../../../../raw/postgres-17/src/backend/optimizer/plan/initsplan.c#L165), [relnode.c:340](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c#L340), [planmain.c:280](../../../../raw/postgres-17/src/backend/optimizer/plan/planmain.c#L280), [allpaths.c:783](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L783), [indxpath.c:279](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L279), [pathnode.c:1024](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L1024), [costsize.c#cost_index-amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L610-L621), [indxpath.c#choose_bitmap_and-call](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L340-L343), [clausesel.c#clauselist_selectivity](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L100-L108), [plancat.c#restriction_selectivity](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1951-L1979), [selfuncs.c#get_actual_variable_range](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6157-L6331), [selfuncs.c#get_actual_variable_endpoint](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6349-L6501) |
| Between the two pins, nine commits touch the cost path, and none changes a cost function or the planner's index-size inputs | `git log 54eeefaedbee..786db8dcf168` over `src/backend/optimizer/`, `selfuncs.c`, the nbtree, index, GIN and BRIN directories and `analyze.c`; the one `selfuncs.c` change is a `ctid` datatype check in `scalarineqsel()` ([selfuncs.c#scalarineqsel-ctid-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L599-L601)), and the nbtree change an empty-index recheck in `_bt_endpoint()` ([nbtsearch.c#_bt_endpoint-empty-index](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2590-L2606)) |
| The two filed diagnostic blocks run as printed | executed verbatim by the script's `diag` stage: `340` live blocks, `246` pending pages, `72.35` %; `2030.46` and `1121.46`, so `303.00` charged pages; `pg_default` with no `random_page_cost` override |
| `pgstatginindex()` raises an `ERROR` on a partitioned GIN index, an invalid one and another session's temporary one, so the first diagnostic block filters them out in an `OFFSET 0` subquery, which is never pulled up | [index.c:1015](../../../../raw/postgres-17/src/backend/catalog/index.c#L1015), [pg_class.h#RELKIND_INDEX-and-RELKIND_PARTITIONED_INDEX](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L162-L173), [pgstatindex.c#IS_INDEX](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L70-L72), [pgstatindex.c#pgstatginindex_internal-checks](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L520-L543), [rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/src/include/utils/rel.h#L667-L669), [pg_class.h:177](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L177), [ref/create_index.sgml#concurrently-invalid](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L646-L651), [prepjointree.c#is_simple_subquery](../../../../raw/postgres-17/src/backend/optimizer/prep/prepjointree.c#L1689-L1701); the filters ran against one valid, permanent, non-partitioned index only |
| `pgstatginindex()` needs `EXECUTE`, which the 1.5 upgrade grants to `pg_stat_scan_tables`, takes `AccessShareLock` and reads only the metapage | [pgstattuple--1.4--1.5.sql#pgstatginindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L49-L57), [pgstatindex.c#pgstatginindex_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L497-L504), [pgstatindex.c#pgstatginindex_internal](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L506-L577) |
| Each `disable_cost` figure in fixture S's table is `1.0e10` plus the plan's normal cost | [costsize.c:130](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L130), [costsize.c#cost_seqscan-disable](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L304-L305); measured `10000004328.00` = `1.0e10 + 4328.00` and `10000010810.92` = `1.0e10 + 10810.92` |
| The `cat = 7` estimate depends on how `reltuples` was last written | [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1299-L1366); measured: 19,999 after a plain `VACUUM` left `reltuples` at 399,985, and 20,000 after `CREATE INDEX` rewrote it to 400,000, because the GIN build returns its heap scan's tuple count and `index_build()` writes it into the table's row ([gininsert.c#ginbuild-scan](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L382-L384), [gininsert.c:424](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L424), [index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135), [index.c#index_update_stats-write](../../../../raw/postgres-17/src/backend/catalog/index.c#L2835-L2923)) |
| The script clears `PGSERVICE` and `PGSERVICEFILE` because libpq fills options from a service entry before it reads the environment, and `PGHOSTADDR` because libpq gives a non-empty host address precedence over `host`, a socket directory included, and resolves it as a numeric network address, so the session goes over TCP rather than to the sandbox socket; the build needs GNU `make` 3.81 or newer, and the server refuses a socket path longer than its buffer | [fe-connect.c#conninfo_add_defaults](../../../../raw/postgres-17/src/interfaces/libpq/fe-connect.c#L6201-L6245), [fe-connect.c#hostaddr-option](../../../../raw/postgres-17/src/interfaces/libpq/fe-connect.c#L223-L225), [fe-connect.c#pqConnectOptions2-host-type](../../../../raw/postgres-17/src/interfaces/libpq/fe-connect.c#L1189-L1204), [fe-connect.c#PQconnectPoll-host-address](../../../../raw/postgres-17/src/interfaces/libpq/fe-connect.c#L2754-L2764), [installation.sgml:40](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L40), [pqcomm.h:60](../../../../raw/postgres-17/src/include/libpq/pqcomm.h#L60), [pqcomm.c:453](../../../../raw/postgres-17/src/backend/libpq/pqcomm.c#L453) |
| A unique index searched by equality on every key column, with no array or `IS NULL` condition, reads one entry | [selfuncs.c#btcostestimate-unique-equality](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6991-L7002) |
| The Mackert-Lohman estimate is capped at the index size exactly when the loops' fetches reach twice the index's pages, for an index within its cache share; fixture A's shares are 139,455 and 407,432 pages at 4GB and 2,179 and 6,367 at 64MB | [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951), [allpaths.c#total_table_pages](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L183-L216); the join's two tables hold 7,353 and 222 heap pages in the run summary |
| `BitmapAnd` `282.26` = `275.70` + `6.30` + `100 * cpu_operator_cost` + `2 * 0.1 * 0.0025 * 12` | [costsize.c#cost_bitmap_and_node-combine](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1184-L1186), [costsize.c:1127](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1127), [costsize.c#cost_index-rows](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L589-L604); measured on fixture L3 |
| `brinGetStats()` returns `revmapNumPages = lastRevmapPage - 1`, while the range map occupies blocks 1 to `lastRevmapPage`, so one range-map page is charged at the random rate | [brin.c:1651](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1651), [brin_pageops.c#brin_metapage_init-lastRevmapPage](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L498-L503), [brin_revmap.c#revmap_physical_extend](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L551-L608), [selfuncs.c#brincostestimate-page-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8244-L8258); not measured |
| Every index except a summarizing one is HOT-blocking | [relcache.c#RelationGetIndexAttrBitmap-summarizing](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L5390-L5398), [heapam.c#heap_update-hot-decision](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4140-L4166) |
| The `vacuum_index_cleanup` reloption sets `index_cleanup` when the `VACUUM` command does not | [vacuum.c#vacuum_rel-index-cleanup-reloption](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2156-L2178), [vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402) |
| The wraparound failsafe fires when `relfrozenxid` or `relminmxid` is older than its failsafe age, each raised to at least 1.05 times the matching freeze maximum, and clears both index switches | [vacuum.c#vacuum_xid_failsafe_check](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1252-L1297), [vacuumlazy.c#lazy_check_wraparound_failsafe-clears](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326) |
| A GIN index's pending list is flushed by VACUUM (bulk delete or cleanup), by an autovacuum `ANALYZE` up to the tail it saw, and by `gin_clean_pending_list()`; only a build and VACUUM's cleanup rewrite the other metapage counters; a manual `ANALYZE` does neither | [ginvacuum.c#ginbulkdelete-pending](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L591-L602), [ginvacuum.c#ginvacuumcleanup-analyze-only](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L717), [ginvacuum.c#ginvacuumcleanup-pending](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L719-L729), [ginvacuum.c:789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L789), [gininsert.c#ginbuild-stats](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L405-L406), [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1027-L1091); measured: fixture D's drain left the metapage at 302 until VACUUM wrote (2073, 547, 54, 1779) |
| Since `3d351d916b2` (14), "never vacuumed" means `reltuples < 0`, so a table that VACUUM emptied and truncated is estimated at zero rows and each scan of its non-partial indexes is charged one page | [tableam.c#table_block_relation_estimate_size-never-vacuumed](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L690-L699), [tableam.c#table_block_relation_estimate_size-empty](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L703-L709), [vacuumlazy.c#heap_vacuum_rel-relstats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L556-L575), [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486), [selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732); the commit's `tableam.c` hunk replaces `relpages == 0` with `reltuples < 0`; not measured |
| `29cf61ade3` (first in 17.0) scales a statistics-free table's width-based density by its fillfactor, and `587b6aa3f3` (first in 17.5) clamps it to at least one row per page | [tableam.c#table_block_relation_estimate_size-fillfactor](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L733-L743), [tableam.c#table_block_relation_estimate_size-min-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L744-L745); both diffs and messages; `Stamp 17.0.` (`d7ec59a63d`) contains `29cf61ade3`, and the first stamp containing `587b6aa3f3` is `Stamp 17.5.` (`5e2f3df49d`); not measured |
| The v12 baseline is the branch point `9e1c9f9594`, the parent of the 13devel stamp `615cebc94b`, which changes only version, release-note and release-tooling files | `git log -1 615cebc94b^`; `git show --name-only 615cebc94b` |
| The script keeps its temporary files and the regression suites' sockets inside the sandbox | [pg_regress.c#make_temp_sockdir](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L499-L525), [pg_regress.c#PG_REGRESS_SOCK_DIR](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L842-L849); both final runs left `$SANDBOX/tmp` and `$SANDBOX/rs` empty |
| Each `grej` statement must end `psql` with status 3, the status for a failed statement read from a script or standard input under `ON_ERROR_STOP` | [mainloop.c#MainLoop-exit-status](../../../../raw/postgres-17/src/bin/psql/mainloop.c#L587-L594), [settings.h:172](../../../../raw/postgres-17/src/bin/psql/settings.h#L172); both final runs recorded the four rejection texts |

## Open Questions

Measurements that are narrower than the claims they support:

- **Version churn.** Fixture P's growth ratios (3.2x unblocked, 6.9x blocked) come from one deliberately harsh workload with autovacuum off, and fixture P-100 shows the result depends on the index's shape: on a 100-value column the same workload grew the index to 1,020 blocks with or without a held snapshot. Why the free horizon bought nothing there was not traced. Both P-100 runs end with identical block counts, which points at the insertion pattern inside long runs of one key rather than at the horizon, but nothing on this page establishes that. No stage isolates bottom-up index deletion as the cause of the 543-versus-1,173 difference either; that attribution rests on the README ([README#deduplication-and-bottom-up-note](../../../../raw/postgres-17/src/backend/access/nbtree/README#L980-L988)). The documentation's stronger claim, that some indexes "never increase by even one single page/block despite constant version churn" ([btree.sgml#bottom-up-effectiveness](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L704-L720)), was not reproduced and would need a gentler, steady-state workload. Nor was the 98.01% density of fixture P's unblocked run traced to a mechanism: deduplication, bottom-up deletion and the single-value split strategy can each leave a leaf page fuller than the 91.47% `pgstatindex` measured after the build, and the script does not separate them.
- **The cache model's heap side.** [Step 4](#step-4-apply-the-cache-model-and-pick-workers) is measured on the index side only. [Index pages in the cache model](#index-pages-in-the-cache-model) prices a repeated inner scan at `0.66` against `2.50` per loop, but every table in that fixture is all-visible, so no heap page is fetched. The other half of the step, a bloated index shrinking the heap's prorated share of `effective_cache_size`, was not isolated; it needs a nested loop whose inner scan fetches heap pages while the tables and the index together exceed the cache setting. The index side is measured in two regimes only, 50,000 loops at the default `effective_cache_size` and at `64MB`. The few-loops regime, where the formula charges about one page per loop whatever the index's size, is read from source only ([costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)).
- **GIN's per-page CPU charge.** Whether this charge, added in v16 by `cd9479af2a` ("Improve GIN cost estimation", 2023-01-08; after the 16devel stamp `d31d30973a` and before the 17devel stamp `5bcc7e6dc8`), ever decides a GIN-versus-B-tree choice by itself, rather than the `random_page_cost` term, was not isolated: no fixture varies `cpu_operator_cost` for a GIN plan. [Gate 3](#gate-3-cost-and-why-gin-loses-on-the-same-column) reconciles the charge to the cent on one fixture only.
- **The `BitmapAnd` boundary.** In fixture D it was located between two pending-list sizes, 736 pages (index kept) and 1,471 pages (index dropped), and not bisected. The comparison that decides it is identified, the two-index plan against the B-tree-only plan, but the crossover size was not measured.
- **GIN's two statistics branches.** Fixture T's `VACUUM` refreshed the GIN metapage from `(2, 1, 0, 100)` to `(1369, 1368, 0, 200000)` and the `n = 42` cost moved by one cent, from `17.19` to `17.20`. The invented and trusted branches produce the same charged page count here, `4.00`, so this fixture does not separate them; a fixture where the two branches diverge visibly was not built.
- **Rounding.** The GIN entry-page estimate `ceil(searchEntries * rint(pow(numEntryPages, 0.15)))` was reconciled arithmetically in every measured case, but `rint()`'s rounding of exact `.5` values to even was not exercised.
- **`btree_gin` range predicates.** Whether `contrib/btree_gin`'s partial-match path (`gincost_pattern()` charging `partialEntries += 100` per key, [selfuncs.c:7467](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7467)) systematically over- or under-charges a range predicate was not investigated; the measurements report only the resulting costs.
- **Parallel plans that ship rows.** The parallel-worker counts were measured on `count()` queries, whose partial aggregate makes each worker return one row, and there the planner chose the same parallel plans at the default parallel costs as with both costs set to `0`. A query that ships its rows through `Gather` pays `parallel_tuple_cost` for each of them, so whether bloat changes the worker count of such a scan depends on the parallel path winning on cost first, which was not measured.
- **Exact statistics are not an exact model.** Every row estimate on this page comes from exhaustive statistics, because the script runs with `default_statistics_target = 10000`, and this page does not bound how far the model can be from the truth. Two fixtures record two-clause estimates beside true counts, L3 and D, and both are built with *independent* columns, the one case where the multiplication in `clauselist_selectivity_ext()` is right, and even then only on average ([clausesel.c#clauselist_selectivity_ext-multiply](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L253-L263), [clausesel.c#clauselist_selectivity_ext-one-sided](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L329-L333)). L3's conjunction matches its true count by luck of the seed, and D's is exact by construction. D's single-clause `cat = 7` estimate, 19,999 against 20,000 true, is off by a row for a different reason, VACUUM's extrapolated `reltuples`. Fixture A's range predicates on its unique key are estimated by histogram interpolation and land on their true counts by construction; the script records no true count beside them. Nothing here exercises a correlated column pair or an extended-statistics object, so the page carries no measured case in which the independence assumption fails. A server at the default target of 100 samples only 30,000 rows ([guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2070-L2079), [analyze.c#std_typanalyze-minrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1876-L1894)), and no sampled run is filed on this page.
- **The partial-index lag.** Fixture Q measures it through one path only, `ANALYZE` rewriting the index's `pg_class` row. Four neighboring claims are read from source: that a `VACUUM` whose counts for the index are exact, or a rebuild, ends the lag the same way ([vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099), [index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135)); that the lag stops once the scaled `tuples` reaches the table's row estimate and `get_relation_info()`'s clamp binds ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)); that a partial index whose row records `relpages <= 1` or `reltuples = -1` takes the width-based density instead ([plancat.c#estimate_rel_size-density](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1116-L1146)); and which commands leave an index's row at `-1`, or at `0` and `0`, as [Lifecycle Of The Planner Inputs](#lifecycle-of-the-planner-inputs) sets out. No fixture builds an index whose rebuild produced no entries, whether from an empty table, from rows dead to every transaction, or from a partial predicate that no row satisfies.
- **The endpoint probe.** Fixture E measures it on one plain primary key, for one `>` clause, with no other session, on a primary server. The rest is read from source: that a snapshot old enough to see the deleted rows makes `SnapshotNonVacuumable` accept them as recently dead, so the probe returns the deleted maximum at once and marks nothing ([selfuncs.c#get_actual_variable_endpoint-comment](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6371-L6414)); that on a hot standby the probe neither marks nor honors killed entries, so every plan walks the same dead entries until the standby replays their removal ([genam.c#RelationGetIndexScan-recovery](../../../../raw/postgres-17/src/backend/access/index/genam.c#L107-L119), [nbtxlog.c#btree_xlog_vacuum](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L598-L634)); that `LIKE` prefix estimation and merge-join costing reach the probe too ([like_support.c#prefix_selectivity](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1213-L1270), [selfuncs.c#mergejoinscansel-scalarineqsel](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L3164-L3203)); and that no partial index and no non-B-tree index is ever probed ([selfuncs.c#get_actual_variable_range-index-choice](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6179-L6239)). The page claims one probe per histogram end that a clause's search reaches, and several probes for several such clauses; whether one clause can be probed more than once in a plan, through a selectivity path that does not reuse the cached restriction selectivity, such as join-clause or index-predicate selectivity, was not traced. Nothing in fixture E is timed, so the planning time a probe costs, up to 101 heap pages, is not measured.
- **GIN gate 0 and the pending-list flush.** The gate-0 checks are read from source only: no fixture builds an invalid index, an `indcheckxmin` index inside its horizon, or a partial GIN index whose predicate the query does not imply ([plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281), [indxpath.c#create_index_paths-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L260-L266)). No fixture exercises the pending-list flush that an autovacuum `ANALYZE` performs, or shows that it leaves the metapage counters stale ([ginvacuum.c#ginvacuumcleanup-analyze-only](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L717)); the script runs with `autovacuum = off`. The first diagnostic block's filters were exercised only against one valid, permanent, non-partitioned GIN index, so the `ERROR`s they avoid on a partitioned, an invalid and another session's temporary GIN index are read from `pgstatginindex()`'s checks ([pgstatindex.c#pgstatginindex_internal-checks](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L520-L543)) and were not reproduced.

Claims read from the pinned source that no fixture on this page exercises:

- **Stale cached height.** That a backend keeps costing from a stale cached metapage until an invalidation reaches it, so that two backends can price one index differently; that a root split, a split that moves the fast root up, or a `VACUUM` that writes no statistics leaves a stale height in place; and that an `ANALYZE`'s write of an index's row clears it ([Lifecycle Of The Planner Inputs](#lifecycle-of-the-planner-inputs)).
- **Which indexes an `UPDATE` writes into.** That an `UPDATE` touching only summarizing-index columns leaves an unrelated B-tree untouched while the new version fits on its page, and that one whose new version does not fit reports `TU_All` and writes into every index that accepts the row; that a partial index whose predicate the new row fails receives no entry ([Version-churn duplicates from non-HOT UPDATEs](#version-churn-duplicates-from-non-hot-updates)). Fixture P changes an indexed column, so it is non-HOT whether or not the new version fits; isolating the fit-decided route needs an update of only summarizing or unindexed columns on full pages.
- **VACUUM's skips.** That VACUUM's 2% bypass still runs `amvacuumcleanup`, so it can flush a GIN pending list or recycle B-tree pages while skipping index vacuuming; and that a B-tree VACUUM that never called `btbulkdelete()` writes no `pg_class` row for the index ([nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L851-L893)).
- **Reloptions on existing pages.** That a changed `fillfactor` reaches already-existing pages at their next rightmost or split-after-new-item split, and a changed `deduplicate_items` at their next pre-split pass; and that a `REINDEX` of fixture N's `deduplicate_items = off` index or of fixture A's `fillfactor = 10` twin would come back at about its current size ([nbtsort.c#_bt_pagestate-leaf-fill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L661-L665), [nbtsort.c#_bt_load-deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1151-L1152)), which the script does not run.
- **Parallel exemptions.** That a table `parallel_workers` reloption makes `compute_parallel_worker()` skip the page-based calculation, capped only by `max_parallel_workers_per_gather`, and that an inheritance child is exempt from the minimum-size rejection. Every fixture here is a plain unpartitioned table with no such reloption.
- **The tablespace override.** That an index on a tablespace carrying a `random_page_cost` option makes the two-`random_page_cost` page-charge probe report zero charged pages. The source path is unambiguous, but no second tablespace was created, and the filed diagnostic block ran only against `pg_default`, where it correctly reported no override.
- **GIN under parallel and repeated scans.** That a serial GIN bitmap index scan can feed a `Parallel Bitmap Heap Scan`; and that a repeated GIN scan amortizes the pending-page I/O charge through `index_pages_fetched()` while leaving the per-page CPU charge unamortized. The second would change how [A GIN index with a large pending list loses to a B-tree](#a-gin-index-with-a-large-pending-list-loses-to-a-b-tree) reads for a nested-loop inner scan. Fixture S's `n IN (1,2,3)` enters the repeated-scan branch at `arrayScans = 3`, so the cache adjustment fires on a measured row, but that index has no pending pages; a fixture with both a pending list and a repeated scan was not built.
- **The extension boundary.** That a custom index access method gets `tree_height = -1` unless `relam == BTREE_AM_OID` ([plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500)), and that a `get_relation_info_hook` plugin can rewrite `pages`, `tuples` or `tree_height` before costing ([plancat.c#get_relation_info_hook](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L570-L576)); no custom access method and no hook plugin was built. The same goes for contrib `bloom`: a single scan is charged for every index page, as `blcostestimate()` says ([blcost.c#blcostestimate](../../../../raw/postgres-17/contrib/bloom/blcost.c#L22-L42)), and a repeated one over an index within its cache share is capped at the index's page count and spread over the loops ([selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779)); no bloom fixture was measured.
- **Other source-only claims.** That BRIN charges every index page on every scan; that the statistics hooks move the page charge through selectivity and that `set_rel_pathlist_hook` can edit costed paths; that the cost path compiles against generated catalog headers; that a query needing no column passes `check_index_only()` trivially; that fixture M's whole-index scan walks only its 276 live leaves because VACUUM unlinked each deleted page from its siblings, since no fixture measures what a scan reads ([nbtpage.c#_bt_unlink_halfdead_page-siblings](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2597-L2612)); and that `CLUSTER` prices a whole-index scan against a sort ([planner.c#plan_cluster_use_sort](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6761-L6874)).
- **Rebuild advice.** The page's size-against-rows reading and its first Practical Interpretation bullet have not been scored against [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md), which governs rebuild decisions.

What the v17 checkout's history can and cannot establish about PostgreSQL 12:

- **How the history is read.** [What Changed Since PostgreSQL 12](#what-changed-since-postgresql-12) is read from the pinned v17 checkout's own history: commit diffs, `git log -L` over `615cebc94b..HEAD`, and ancestry against the `Stamp HEAD as NNdevel.` and `Stamp 17.N.` commits. No fixture and no v12 server backs it. That covers the v16 summarizing-only HOT change, the v13 narrowing of GIN's whole-index estimate, the `pg_upgrade` caveat for deduplication, the two `= ANY` cases fixture I does not build (an array outside the boundary quals, and a non-constant array sized from statistics), the `reltuples` states of new, rebuilt and upgraded indexes, `9f3665fbfc` stopping a cleanup-only B-tree VACUUM from writing `pg_class`, the three table-estimate changes (`3d351d916b2`'s never-vacuumed test, `29cf61ade3` and `587b6aa3f3`), and the one-page difference in the width-based fallback before `3d351d916b2`. Only the endpoint probe's 100-page limit is measured, and only on the v17 side (fixture E).
- **What 12.x releases contain.** The v17 checkout cannot show what PostgreSQL 12 releases contain beyond the branch point `9e1c9f9594`, because it has no `REL_12_STABLE` history and no tags. `9c6ad5eaa9`'s message says "Back-patch to all supported branches", so some 12.x minor release may carry the endpoint probe's 100-page limit, but this checkout cannot show which one, or whether the wiki's v12 pin does. `d3751adcf1` says it was back-patched to v11, so it may already be in 12.0. The page therefore compares v17 with the v12 branch point, not with a 12.x release.
- **An empty rebuild of a partial index.** For a partial index of an access method whose empty build leaves more than one block, rebuilt with no entries, the two versions record different densities. Before `3d351d916b2` the reset wrote `reltuples = 0` and the build then recorded its block count, which is a density of zero. Since that commit the rebuild keeps `-1`, and v17 falls back to column widths ([plancat.c#estimate_rel_size-density](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1116-L1146), [relcache.c#RelationSetNewRelfilenumber-reset](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3948-L3954), [index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842)). A fresh `CREATE INDEX` of such an index with no matching rows records a zero density in v17 too, because the new row starts at `reltuples = 0`, not `-1`, so the keep-`-1` rule does not fire ([relcache.c#RelationBuildLocalRelation-rd_rel](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3656-L3659), [index.c#index_create-pg_class](../../../../raw/postgres-17/src/backend/catalog/index.c#L1008-L1024)). Which core access methods build that way was not worked out.

Places where the documentation and the source disagree; the page follows the source:

- **Which indexes a non-HOT `UPDATE` writes into.** `btree.sgml` says that changing one indexed column "*always* necessitates a new set of index tuples — one for *each and every* index on the table" ([btree.sgml#version-churn](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L638-L655)). The source makes two exceptions. An update that changes only summarizing-index columns and keeps the new version on its page is HOT with `TU_Summarizing`, and `ExecInsertIndexTuples()` then skips every non-summarizing index ([heapam.c#heap_update-hot-decision](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4140-L4166), [heapam.c#heap_update-update-indexes](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4415-L4429), [execIndexing.c#ExecInsertIndexTuples-onlySummarizing](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L361-L366)). A partial index whose predicate the new row fails gets no entry ([execIndexing.c#ExecInsertIndexTuples-predicate](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L368-L387)). No fixture exercises either exception.
- **`gin_pending_list_limit`.** The setting's reference entry, its GUC description and the per-index reloption's description ("Maximum size of the pending list for this GIN index, in kilobytes.", [reloptions.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L339-L347)) all describe it as the maximum size of the pending list, and the reference entry says that a list growing past it "is cleaned up" ([config.sgml#guc-gin-pending-list-limit](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L9870-L9890), [guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585)). The source allows the overshoot the entry describes but does not guarantee the cleanup: `ginHeapTupleFastInsert()` tests the size only after adding entries and then asks for a cleanup that is not forced and is skipped when another process holds the metapage lock ([ginfast.c#needCleanup](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L448-L471), [ginfast.c#ginInsertCleanup-conditional-lock](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L818-L828)). Fixture D grows its pending list by raising the limit rather than by exceeding it, so no measurement here shows the overshoot.
- **When a concurrently built index becomes usable.** The `CREATE INDEX` reference says a concurrently built index "may not be immediately usable for queries" while transactions that predate the build exist ([ref/create_index.sgml#not-immediately-usable](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L640-L642)), but `index_build()` never sets `indcheckxmin` for a concurrent build ([index.c#index_build-indcheckxmin](../../../../raw/postgres-17/src/backend/catalog/index.c#L3099-L3101)), and `get_relation_info()` holds back a valid index only through that flag ([plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281)). Which mechanism the sentence refers to was not traced.
- **Which VACUUMs flush a GIN pending list.** `gin.sgml` says the pending entries are moved "When the table is vacuumed or autoanalyzed" ([gin.sgml#fast-update-flush](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L508-L515)). A `VACUUM` with index cleanup off, whether by `INDEX_CLEANUP OFF`, the `vacuum_index_cleanup` reloption or the wraparound failsafe, calls neither `ginbulkdelete()` nor `ginvacuumcleanup()`, so it leaves the list in place ([vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402), [vacuumlazy.c#lazy_check_wraparound_failsafe-clears](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326), [ginvacuum.c#ginvacuumcleanup-pending](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L719-L729)). The page follows the source; no fixture exercises it.

## Source References

- [pg_class.h#relpages](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L69)
- [pathnodes.h#IndexOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1120-L1128)
- [plancat.c#get_relation_info-index-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471-L486)
- [bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L280-L281)
- [plancat.c#estimate_rel_size-index](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1079-L1160)
- [tableam.c#table_block_relation_estimate_size-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L711-L747)
- [selfuncs.c#btcostestimate-numIndexTuples](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7007-L7019)
- [selfuncs.c#genericcostestimate-numIndexPages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6717-L6732)
- [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488-L500)
- [nbtpage.c#_bt_getrootheight](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L663-L717)
- [selfuncs.c#ineq_histogram_selectivity-endpoints](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1076-L1136)
- [plancat.c:476](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L476)
- [costsize.c#cost_index-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L749-L772)
- [selfuncs.c#btcostestimate-outputs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7206-L7210)
- [pgstatindex.c#pgstatindex_impl-metapage](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L252-L265)
- [pgstatindex.c#pgstatindex_impl-pages](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L331)
- [pgstatindex.c#pgstatindex_impl-density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L372)
- [plancat.c#estimate_rel_size-density](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1116-L1146)
- [plancat.c#get_relation_info-partitioned](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L502-L508)
- [selfuncs.c#get_actual_variable_range-index-choice](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6179-L6239)
- [selfuncs.c#get_actual_variable_endpoint-limit](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6436-L6457)
- [selfuncs.c#btcostestimate-unique-equality](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6991-L7002)
- [selfuncs.c#btcostestimate-saop-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7021-L7042)
- [selfuncs.c#genericcostestimate-mackert-lohman](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6739-L6779)
- [selfuncs.c#genericcostestimate-single-scan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6780-L6787)
- [selfuncs.c#genericcostestimate-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6789-L6810)
- [selfuncs.c#btcostestimate-log2-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7091)
- [selfuncs.c#btcostestimate-page-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7093-L7106)
- [costsize.c#cost_index-heap-fetches](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L670-L747)
- [costsize.c#index_pages_fetched](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L859-L951)
- [allpaths.c#compute_parallel_worker](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4202-L4279)
- [pathnode.c#add_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L419-L622)
- [indxpath.c#choose_bitmap_and](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1287-L1489)
- [plancat.c#amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L331-L332)
- [plancat.c#get_relation_info-index-block](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L463-L508)
- [bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4002-L4020)
- [selfuncs.c#genericcostestimate-tablespace](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6734-L6737)
- [selfuncs.c:145](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L145)
- [cost.h:28](../../../../raw/postgres-17/src/include/optimizer/cost.h#L28)
- [nbtpage.c#_bt_unlink_halfdead_page-fastroot](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2565-L2659)
- [README#page-deletion-and-tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L362-L381)
- [pgstatindex.c:351](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L351)
- [pgstattuple--1.4--1.5.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L24)
- [pgstattuple.control:3](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.control#L3)
- [allpaths.c#total_table_pages](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L183-L216)
- [costsize.c#compute_bitmap_pages-repeated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L6463-L6476)
- [allpaths.c#compute_parallel_worker-index-ramp](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4253-L4272)
- [selfuncs.c#btcostestimate-genericcost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7067-L7073)
- [selfuncs.c#scalarineqsel_wrapper](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1397-L1503)
- [selfuncs.c:690](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L690)
- [like_support.c#prefix_selectivity](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1213-L1270)
- [costsize.c:3577](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L3577)
- [costsize.c:4016](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L4016)
- [selfuncs.c#mergejoinscansel-ranges](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L3141-L3156)
- [selfuncs.c#get_variable_range-not-used](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5993-L6003)
- [selfuncs.c#mergejoinscansel-scalarineqsel](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L3164-L3203)
- [selfuncs.c#get_actual_variable_range](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6157-L6331)
- [selfuncs.c#get_actual_variable_endpoint-snapshot](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6376-L6386)
- [selfuncs.c#get_actual_variable_endpoint-scan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6415-L6458)
- [selfuncs.c#get_actual_variable_endpoint-give-up](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6409-L6413)
- [indexam.c#index_fetch_heap-kill](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L644-L652)
- [nbtree.c#btgettuple-kill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L226-L245)
- [nbtsearch.c#_bt_steppage-killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2049-L2051)
- [nbtree.c#btendscan-killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L424-L426)
- [selfuncs.c#get_actual_variable_endpoint-killed](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6388-L6397)
- [genam.c#RelationGetIndexScan-recovery](../../../../raw/postgres-17/src/backend/access/index/genam.c#L107-L119)
- [nbtsearch.c:1721](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1721)
- [nbtsearch.c:1850](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1850)
- [selfuncs.c:7073](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7073)
- [selfuncs.c:7221](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7221)
- [selfuncs.c:7265](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7265)
- [selfuncs.c:7320](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7320)
- [blcost.c#blcostestimate](../../../../raw/postgres-17/contrib/bloom/blcost.c#L22-L42)
- [selfuncs.c#gistcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7256-L7308)
- [selfuncs.c#spgcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7311-L7363)
- [selfuncs.c#hashcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7213-L7253)
- [hash.c:75](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L75)
- [gist.c:77](../../../../raw/postgres-17/src/backend/access/gist/gist.c#L77)
- [spgutils.c:62](../../../../raw/postgres-17/src/backend/access/spgist/spgutils.c#L62)
- [blutils.c:124](../../../../raw/postgres-17/contrib/bloom/blutils.c#L124)
- [selfuncs.c#gincostestimate-header](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7662-L7671)
- [selfuncs.c#brincostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8052-L8061)
- [selfuncs.c:7674](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7674)
- [selfuncs.c:8063](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8063)
- [selfuncs.c#gincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7697-L7711)
- [gininsert.c:406](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L406)
- [ginvacuum.c:789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L789)
- [selfuncs.c#gincostestimate-scale-or-invent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7767)
- [brin.c#brinGetStats](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1638-L1654)
- [selfuncs.c#brincostestimate-stats](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8086-L8101)
- [selfuncs.c#brincostestimate-page-charge](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8244-L8258)
- [pgstatindex.c#pgstatindex_impl-btree-check](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L228)
- [sql/pgstattuple.sql#wrong-index-type](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L55-L63)
- [expected/pgstattuple.out#wrong-index-type](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L145-L150)
- [selfuncs.c#genericcostestimate-numIndexPages-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6732)
- [spccache.c#get_tablespace_page_costs](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L181-L196)
- [allpaths.c#compute_parallel_worker-reloption](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4208-L4213)
- [reloptions.c#parallel_workers](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L374-L382)
- [allpaths.c#compute_parallel_worker-threshold](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4216-L4227)
- [index.c#index_create-pg_class](../../../../raw/postgres-17/src/backend/catalog/index.c#L1008-L1024)
- [relcache.c#RelationBuildLocalRelation-rd_rel](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3656-L3659)
- [index.c#index_update_stats-write](../../../../raw/postgres-17/src/backend/catalog/index.c#L2835-L2923)
- [nbtsort.c#_bt_load-first-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1287-L1290)
- [nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1063-L1128)
- [relcache.c#RelationSetNewRelfilenumber-reset](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3948-L3954)
- [index.c#index_update_stats-empty](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842)
- [vacuumlazy.c#heap_vacuum_rel-index-stats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L512-L513)
- [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099)
- [vacuum.c#vac_update_relstats-dirty](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1446-L1461)
- [nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L851-L893)
- [analyze.c#do_analyze_rel-index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663)
- [nbtpage.c#_bt_getroot-cache](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L523-L528)
- [nbtpage.c#_bt_metaversion-cache](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L773-L775)
- [relcache.c#RelationCacheInvalidateEntry](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2975-L2985)
- [relcache.c#RelationFlushRelation](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2916-L2924)
- [relcache.c#RelationClearRelation](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L2600-L2603)
- [heapam.c:6668](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6668)
- [inval.c#CacheInvalidateHeapTupleCommon-pg_class](../../../../raw/postgres-17/src/backend/utils/cache/inval.c#L1383-L1392)
- [heapam.c#heap_inplace_update_and_unlock-send](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6888-L6892)
- [plancat.c:253](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L253)
- [lmgr.c#LockRelationOid-accept](../../../../raw/postgres-17/src/backend/storage/lmgr/lmgr.c#L134-L138)
- [README#metapage-cache](../../../../raw/postgres-17/src/backend/access/nbtree/README#L776-L790)
- [vacuum.c#vac_update_relstats-inplace](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1545-L1548)
- [heapam.c#heap_inplace_unlock](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6914-L6920)
- [nbtpage.c#_bt_getroot-stale-cache](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L380-L403)
- [nbtree.h:225](../../../../raw/postgres-17/src/include/access/nbtree.h#L225)
- [nbtpage.c#_bt_gettrueroot-flush](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L592-L600)
- [nbtinsert.c#_bt_newlevel-metapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2515-L2519)
- [nbtinsert.c#_bt_insertonpg-fastroot](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1250-L1295)
- [selfuncs.c:7064](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7064)
- [selfuncs.c#genericcostestimate-tuple-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6707-L6715)
- [costsize.c#cost_index-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L795-L800)
- [nbtpage.c#_bt_unlink_halfdead_page-siblings](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2597-L2612)
- [README#half-dead](../../../../raw/postgres-17/src/backend/access/nbtree/README#L247-L259)
- [nbtsearch.c#_bt_readnextpage-step-right](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2207-L2219)
- [glossary.sgml#Bloat](../../../../raw/postgres-17/doc/src/sgml/glossary.sgml#L242-L250)
- [btree.sgml#deduplication](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L736-L800)
- [gin.sgml#fast-update](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L503-L529)
- [selfuncs.c#gincostestimate-pending](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7882-L7886)
- [selfuncs.c#gincostestimate-random-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7976-L7980)
- [maintenance.sgml#routine-reindex](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1032-L1040)
- [ref/reindex.sgml#bloated](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml#L54-L64)
- [nbtpage.c#_bt_unlink_halfdead_page-deleted](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2628-L2659)
- [nbtpage.c#_bt_allocbuf-fsm](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L901-L905)
- [nbtpage.c#_bt_allocbuf](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L868-L988)
- [pgstatindex.c#pgstatindex_impl-fragments](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323)
- [maintenance.sgml#fresh-index](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1048-L1054)
- [btree.sgml#version-churn](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L638-L655)
- [execIndexing.c#ExecInsertIndexTuples-predicate](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L368-L387)
- [README#deduplication-and-bottom-up-note](../../../../raw/postgres-17/src/backend/access/nbtree/README#L980-L988)
- [nbtinsert.c#_bt_delete_or_dedup_one_page-dedup-gate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2778-L2781)
- [nbtsort.c#_bt_load-deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1151-L1152)
- [vacuumlazy.c#lazy_vacuum-bypass-branch](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949)
- [vacuumlazy.c#lazy_check_wraparound_failsafe-clears](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2326)
- [vacuumlazy.c#heap_vacuum_rel-index-cleanup](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L402)
- [vacuumlazy.c#lazy_vacuum-index-vacuuming](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1950-L1956)
- [maintenance.sgml#routine-reindex-non-btree](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1042-L1046)
- [costsize.c#cost_index-amcostestimate](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L610-L621)
- [nbtree.h#fillfactor-comment](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L197)
- [nbtsort.c#_bt_pagestate-leaf-fill](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L661-L665)
- [nbtree.h#BTREE_DEFAULT_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L200-L202)
- [nbtsplitloc.c#_bt_findsplitloc-fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L334)
- [nbtsplitloc.c#_bt_deltasortsplits](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L561-L588)
- [nbtsplitloc.c#_bt_defaultinterval](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L852-L920)
- [nbtsplitloc.c#_bt_bestsplitloc](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L770-L812)
- [nbtsplitloc.c#_bt_findsplitloc-many-duplicates](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L374-L405)
- [nbtsplitloc.c#_bt_strategy-many-duplicates](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L985-L1009)
- [nbtsplitloc.c#_bt_findsplitloc-single-value](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L389-L416)
- [nbtsplitloc.c#_bt_strategy-single-value](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L1011-L1041)
- [nbtsplitloc.c#_bt_split_penalty](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L1119-L1153)
- [nbtinsert.c#_bt_insertonpg-split-check](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1203-L1210)
- [reloptions.c#intRelOpts-fillfactor-btree](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L185-L194)
- [nbtpage.c#_bt_unlink_halfdead_page-side-links](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2597-L2600)
- [README#placing-deleted-pages-in-the-fsm](../../../../raw/postgres-17/src/backend/access/nbtree/README#L383-L441)
- [nbtree.c:1168](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1168)
- [nbtpage.c:3050](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L3050)
- [nbtinsert.c:1720](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1720)
- [relcache.c#RelationGetIndexAttrBitmap-summarizing](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L5390-L5398)
- [heapam.c#heap_update-hot-decision](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4140-L4166)
- [execIndexing.c#ExecInsertIndexTuples-loop](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L343-L387)
- [heapam.c#heap_update-update-indexes](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4415-L4429)
- [tableam.h#TU_UpdateIndexes](../../../../raw/postgres-17/src/include/access/tableam.h#L113-L127)
- [nodeModifyTable.c#ExecUpdateEpilogue-onlySummarizing](../../../../raw/postgres-17/src/backend/executor/nodeModifyTable.c#L2162-L2166)
- [execIndexing.c#ExecInsertIndexTuples-onlySummarizing](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L361-L366)
- [heapam.c:4429](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L4429)
- [btree.sgml#bottom-up-deletion](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L656-L678)
- [nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L280-L320)
- [nbtinsert.c#_bt_delete_or_dedup_one_page-dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2782)
- [btree.sgml#btree-deduplication-build](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L786-L797)
- [README#notes-about-deduplication](../../../../raw/postgres-17/src/backend/access/nbtree/README#L904-L948)
- [nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L33-L58)
- [reloptions.c#deduplicate_items](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L167)
- [nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183)
- [nbtsort.c#_bt_leafbuild-allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L560-L564)
- [btree.sgml#deduplication-restrictions](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L834-L908)
- [vacuumlazy.c#BYPASS_THRESHOLD_PAGES](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L85-L89)
- [vacuumlazy.c#lazy_vacuum-bypass](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1880-L1949)
- [vacuumlazy.c#lazy_scan_heap-bypass-off](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L894-L896)
- [vacuum.c#vacuum_xid_failsafe_check](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1252-L1297)
- [vacuumlazy.c#lazy_check_wraparound_failsafe](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2287-L2347)
- [vacuum.c#vacuum_rel-index-cleanup-reloption](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2156-L2178)
- [ginvacuum.c#ginvacuumcleanup-pending](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L719-L729)
- [ginvacuum.c#ginbulkdelete-pending](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L591-L602)
- [vacuumlazy.c#lazy_vacuum-call](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1066)
- [ref/create_table.sgml#reloption-vacuum-index-cleanup](../../../../raw/postgres-17/doc/src/sgml/ref/create_table.sgml#L1558-L1575)
- [brin.h#BrinStatsData](../../../../raw/postgres-17/src/include/access/brin.h#L32-L36)
- [brin.c:1651](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1651)
- [brin_pageops.c#brin_metapage_init-lastRevmapPage](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L498-L503)
- [brin_revmap.c#revmap_physical_extend](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L551-L608)
- [selfuncs.c:7895](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7895)
- [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457)
- [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270)
- [cost.h#DEFAULT_SEQ_PAGE_COST](../../../../raw/postgres-17/src/include/optimizer/cost.h#L24-L28)
- [cost.h:34](../../../../raw/postgres-17/src/include/optimizer/cost.h#L34)
- [btreefuncs.c#GetBTPageStatistics-items](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L172-L187)
- [selfuncs.c#scalarineqsel-ctid-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L599-L601)
- [costsize.c#cost_index-save-indextotalcost](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L623-L629)
- [createplan.c#create_bitmap_subplan-indexpath](../../../../raw/postgres-17/src/backend/optimizer/plan/createplan.c#L3480-L3485)
- [guc_tables.c#enable_seqscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L783-L792)
- [guc_tables.c#enable_indexscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L793-L802)
- [guc_tables.c#enable_indexonlyscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L803-L812)
- [guc_tables.c#enable_bitmapscan](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L813-L822)
- [guc_tables.c#enable_mergejoin](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L893-L902)
- [guc_tables.c#enable_hashjoin](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L903-L912)
- [guc_tables.c#cpu_operator_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3719-L3729)
- [guc_tables.c#random_page_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3686-L3696)
- [guc_tables.c#effective_cache_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3518)
- [guc_tables.c#max_parallel_workers_per_gather](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3419-L3428)
- [guc_tables.c#max_parallel_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3430-L3439)
- [guc_tables.c#min_parallel_table_scan_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3520-L3529)
- [guc_tables.c#parallel_tuple_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3730-L3740)
- [guc_tables.c#parallel_setup_cost](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3741-L3751)
- [guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2070-L2079)
- [analyze.c#std_typanalyze-minrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1876-L1894)
- [clausesel.c#clauselist_selectivity_ext-multiply](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L253-L263)
- [clausesel.c#clauselist_selectivity_ext-one-sided](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L329-L333)
- [selfuncs.c#btcostestimate-log2-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7086-L7091)
- [index.c#reindex_index-rebuild](../../../../raw/postgres-17/src/backend/catalog/index.c#L3784-L3789)
- [nbtree.h#BTGetFillFactor-BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1150)
- [indxpath.c#check_index_predicates-indrestrictinfo](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L3318-L3378)
- [indxpath.c#match_restriction_clauses_to_index](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1968-L1974)
- [heapam_visibility.c#HeapTupleSatisfiesVacuumHorizon-same-xact](../../../../raw/postgres-17/src/backend/access/heap/heapam_visibility.c#L1253-L1266)
- [heapam_visibility.c#HeapTupleSatisfiesVacuumHorizon-xmax-in-progress](../../../../raw/postgres-17/src/backend/access/heap/heapam_visibility.c#L1383-L1386)
- [plancat.c#get_relation_info-table-size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L196-L202)
- [index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135)
- [costsize.c#cost_seqscan](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L315-L322)
- [costsize.c#cost_bitmap_and_node-combine](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1184-L1186)
- [costsize.c:1127](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1127)
- [costsize.c#cost_index-rows](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L589-L604)
- [analyze.c#compute_scalar_stats-stadistinct](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2550-L2560)
- [analyze.c#compute_scalar_stats-complete-mcv](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2614-L2636)
- [guc_tables.c#min_parallel_index_scan_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3531-L3540)
- [costsize.c#cost_index-correlation-cpu](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L781-L800)
- [nbtree.h:200](../../../../raw/postgres-17/src/include/access/nbtree.h#L200)
- [selfuncs.c#get_actual_variable_endpoint-comment](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6371-L6414)
- [selfuncs.c#ineq_histogram_selectivity-above-last-bound](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1162-L1168)
- [selfuncs.c#ineq_histogram_selectivity-flip-clamp](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1319-L1344)
- [costsize.c#clamp_row_est](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L202-L218)
- [heapam.c#heap_delete-clear-vm](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L3120-L3146)
- [tableam.c#table_block_relation_estimate_size-allvisfrac](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L749-L760)
- [vacuumlazy.c#heap_vacuum_rel-relstats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L556-L575)
- [analyze.c#do_analyze_rel-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L623-L645)
- [selfuncs.c#get_actual_variable_range-endpoint-calls](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6282-L6314)
- [selfuncs.c:6365](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6365)
- [costsize.c#cost_index](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L549-L821)
- [selfuncs.c#genericcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6626-L6828)
- [selfuncs.c#genericcostestimate-num_sa_scans](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6657-L6679)
- [selfuncs.c#btcostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6870-L7211)
- [selfuncs.c#genericcostestimate-page-cost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6729-L6786)
- [selfuncs.c:7104](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7104)
- [selfuncs.c:7299](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7299)
- [selfuncs.c:7354](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7354)
- [selfuncs.c#gincostestimate-page-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7937-L7955)
- [selfuncs.c:8015](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8015)
- [selfuncs.c#gincost_pattern-searchmode](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7454-L7489)
- [selfuncs.c#gincostestimate-fullscan](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7852-L7877)
- [selfuncs.h#GenericCosts](../../../../raw/postgres-17/src/include/utils/selfuncs.h#L108-L138)
- [selfuncs.c#estimate_array_length](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L2131-L2207)
- [selfuncs.c#btcostestimate-bound-saop](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6904-L6989)
- [indxpath.c#match_saopclause_to_indexcol](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2651-L2669)
- [plancat.c:471](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L471)
- [pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L65-L66)
- [heap.c#AddNewRelationTuple-empty](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1006-L1009)
- [index.c#index_build-index-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3133-L3135)
- [index.c:1459](../../../../raw/postgres-17/src/backend/catalog/index.c#L1459)
- [tablecmds.c#ExecuteTruncateGuts-in-place](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L2133-L2145)
- [heap.c#RelationTruncateIndexes](../../../../raw/postgres-17/src/backend/catalog/heap.c#L3083-L3087)
- [tablecmds.c#ExecuteTruncateGuts-rewrite](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L2167-L2189)
- [vacuum.c:2260](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2260)
- [cluster.c:670](../../../../raw/postgres-17/src/backend/commands/cluster.c#L670)
- [tablecmds.c:5873](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L5873)
- [matview.c:890](../../../../raw/postgres-17/src/backend/commands/matview.c#L890)
- [cluster.c:1508](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1508)
- [index.c:4048](../../../../raw/postgres-17/src/backend/catalog/index.c#L4048)
- [nbtsort.c:599](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L599)
- [nbtsort.c:338](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L338)
- [heapam_handler.c#heapam_index_build_range_scan-dead](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1419-L1423)
- [heapam_handler.c#index-build-predicate](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L1636-L1644)
- [tableam.c#table_block_relation_estimate_size-never-vacuumed](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L690-L699)
- [tableam.c#table_block_relation_estimate_size-empty](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L703-L709)
- [tableam.c#table_block_relation_estimate_size-fillfactor](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L733-L743)
- [tableam.c#table_block_relation_estimate_size-min-density](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L744-L745)
- [selfuncs.c#VISITED_PAGES_LIMIT](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6447-L6455)
- [nbtxlog.c#btree_xlog_vacuum](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L598-L634)
- [selfuncs.c#get_actual_variable_endpoint-horizon](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6415-L6416)
- [nbtree.h#btm_allequalimage-upgrade](../../../../raw/postgres-17/src/include/access/nbtree.h#L135-L141)
- [btree.sgml#deduplication-safety](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L834-L838)
- [btree.sgml#simple-vs-bottom-up](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L679-L703)
- [btree.sgml#bottom-up-effectiveness](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L704-L720)
- [brin.c:269](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L269)
- [heapam.c#heap_update-attr-bitmaps](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L3434-L3437)
- [README#postgresql-14-fsm-change](../../../../raw/postgres-17/src/backend/access/nbtree/README#L403-L424)
- [nbtree.h#BTDeletedPageData](../../../../raw/postgres-17/src/include/access/nbtree.h#L230-L236)
- [nbtree.h#BTMetaPageData](../../../../raw/postgres-17/src/include/access/nbtree.h#L103-L119)
- [nbtpage.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L172-L223)
- [reloptions.c#vacuum_cleanup_index_scale_factor](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L462-L470)
- [nbtree.h:1134](../../../../raw/postgres-17/src/include/access/nbtree.h#L1134)
- [nbtutils.c#btoptions-parse-table](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4566-L4567)
- [reloptions.c#vacuum_index_cleanup](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L510-L520)
- [vacuum.c#index_cleanup-default](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2155-L2179)
- [cost.h:25](../../../../raw/postgres-17/src/include/optimizer/cost.h#L25)
- [selfuncs.c#btcostestimate-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7075-L7106)
- [nbtsplitloc.c#leaffillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L170-L176)
- [nbtsplitloc.c:317](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L317)
- [nbtsplitloc.c:364](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L364)
- [nbtsplitloc.c#split-strategies](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L364-L416)
- [nbtsplitloc.c#_bt_strategy](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L985-L1041)
- [nbtree.h:202](../../../../raw/postgres-17/src/include/access/nbtree.h#L202)
- [nbtinsert.c#early-returns](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2721-L2776)
- [nbtpage.c#_bt_metaversion-comment](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L720-L737)
- [ref/reindex.sgml#storage-parameter](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml#L66-L71)
- [analyze.c#partial-index-population](../../../../raw/postgres-17/src/backend/commands/analyze.c#L902-L908)
- [analyze.c#tupleFract](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953)
- [nbtinsert.c#_bt_newlevel-root-level](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2507-L2513)
- [selfuncs.c#btcostestimate-boundary-saop](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6950-L6961)
- [selfuncs.c#estimate_array_length-statistics](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L2162-L2206)
- [selfuncs.c:6695](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6695)
- [pathnodes.h#RelOptInfo](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L941-L944)
- [plancat.c:201](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L201)
- [plancat.c:484](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L484)
- [pathnodes.h#total_table_pages](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L483-L484)
- [lsyscache.h#AttStatsSlot](../../../../raw/postgres-17/src/include/utils/lsyscache.h#L46-L62)
- [vacuumlazy.c:1900](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1900)
- [vacuumlazy.c#LVRelState](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L148-L156)
- [planmain.c:170](../../../../raw/postgres-17/src/backend/optimizer/plan/planmain.c#L170)
- [initsplan.c:165](../../../../raw/postgres-17/src/backend/optimizer/plan/initsplan.c#L165)
- [relnode.c:340](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c#L340)
- [plancat.c#get_relation_info_hook](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L570-L576)
- [planmain.c:280](../../../../raw/postgres-17/src/backend/optimizer/plan/planmain.c#L280)
- [allpaths.c:322](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L322)
- [allpaths.c:411](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L411)
- [allpaths.c:581](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L581)
- [costsize.c:5264](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L5264)
- [allpaths.c:221](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L221)
- [allpaths.c:351](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L351)
- [allpaths.c:499](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L499)
- [allpaths.c:783](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L783)
- [indxpath.c:279](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L279)
- [indxpath.c:722](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L722)
- [indxpath.c:963](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L963)
- [pathnode.c:1024](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L1024)
- [selfuncs.c:7015](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7015)
- [selfuncs.c:6682](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6682)
- [selfuncs.c:6767](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6767)
- [selfuncs.c#gincostestimate-cache-effects](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7957-L7974)
- [costsize.c:765](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L765)
- [indxpath.c#choose_bitmap_and-call](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L340-L343)
- [pathnode.c:452](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L452)
- [indxpath.c#bitmap_scan_cost_est](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1526-L1553)
- [costsize.c:1044](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1044)
- [allpaths.c#set_rel_pathlist_hook](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L532-L539)
- [clausesel.c#clauselist_selectivity](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L100-L108)
- [clausesel.c:136](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L136)
- [clausesel.c:183](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L183)
- [clausesel.c:848](../../../../raw/postgres-17/src/backend/optimizer/path/clausesel.c#L848)
- [plancat.c#restriction_selectivity](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1951-L1979)
- [pg_operator.dat#int4gt](../../../../raw/postgres-17/src/include/catalog/pg_operator.dat#L453-L456)
- [selfuncs.c#scalargtsel](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1490-L1494)
- [selfuncs.c:1461](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L1461)
- [selfuncs.c#get_actual_variable_endpoint](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6349-L6501)
- [like_support.c:1245](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1245)
- [like_support.c:1266](../../../../raw/postgres-17/src/backend/utils/adt/like_support.c#L1266)
- [pathnode.c#compare_path_costs_fuzzily](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L163-L212)
- [cluster.c#plan_cluster_use_sort-call](../../../../raw/postgres-17/src/backend/commands/cluster.c#L948-L951)
- [planner.c#plan_cluster_use_sort](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6761-L6874)
- [planner.c#plan_cluster_use_sort-compare](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6861-L6873)
- [cluster.c#check_index_is_clusterable-partial](../../../../raw/postgres-17/src/backend/commands/cluster.c#L525-L534)
- [planner.c#plan_cluster_use_sort-short-circuits](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L6788-L6841)
- [nbtpage.c:903](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L903)
- [nbtpage.c:978](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L978)
- [nbtpage.c:1526](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1526)
- [plancat.c:488](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L488)
- [selfuncs.c:6197](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6197)
- [pg_class.h#RELKIND_INDEX-and-RELKIND_PARTITIONED_INDEX](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L162-L173)
- [Catalog.pm#client_code](../../../../raw/postgres-17/src/backend/catalog/Catalog.pm#L61-L66)
- [Catalog.pm#client_code-push](../../../../raw/postgres-17/src/backend/catalog/Catalog.pm#L197-L205)
- [genbki.pl#client_code](../../../../raw/postgres-17/src/backend/catalog/genbki.pl#L563-L567)
- [pg_am.dat:18](../../../../raw/postgres-17/src/include/catalog/pg_am.dat#L18)
- [genbki.pl#oid_symbol](../../../../raw/postgres-17/src/backend/catalog/genbki.pl#L675-L687)
- [catversion.h#header-comment](../../../../raw/postgres-17/src/include/catalog/catversion.h#L6-L14)
- [pg_class.h#CATALOG](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L21-L32)
- [genbki.h:23](../../../../raw/postgres-17/src/include/catalog/genbki.h#L23)
- [pg_class.h#NOTES](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L11-L16)
- [genbki.pl:437](../../../../raw/postgres-17/src/backend/catalog/genbki.pl#L437)
- [genbki.pl:456](../../../../raw/postgres-17/src/backend/catalog/genbki.pl#L456)
- [initdb.c#bootstrap_template1](../../../../raw/postgres-17/src/bin/initdb/initdb.c#L1523-L1539)
- [initdb.c:2770](../../../../raw/postgres-17/src/bin/initdb/initdb.c#L2770)
- [selfuncs.c:6447](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6447)
- [plancat.h#get_relation_info_hook_type](../../../../raw/postgres-17/src/include/optimizer/plancat.h#L20-L25)
- [selfuncs.c#get_actual_variable_range-skips](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6196-L6212)
- [selfuncs.c#examine_variable-get_index_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5203-L5204)
- [selfuncs.c#examine_simple_variable-get_relation_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5375-L5376)
- [selfuncs.c#btcostestimate-stats-hooks](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7116-L7171)
- [selfuncs.c#brincostestimate-get_relation_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8135-L8136)
- [selfuncs.c#brincostestimate-get_index_stats_hook](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8166-L8167)
- [pg_proc.dat#pg_relation_size](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7487-L7495)
- [pgstattuple.c#pgstat_btree_page-checks](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L419-L425)
- [expected/inherit.out#parted_tab-update](../../../../raw/postgres-17/src/test/regress/expected/inherit.out#L697-L698)
- [sql/pgstattuple.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L18-L37)
- [expected/pgstattuple.out#NaN](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L44-L82)
- [expected/pgstattuple.out#partition-index](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L264-L268)
- [expected/pgstattuple.out:146](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L146)
- [expected/pgstattuple.out:150](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L150)
- [expected/pgstattuple.out:171](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L171)
- [expected/pgstattuple.out:190](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L190)
- [expected/pgstattuple.out:209](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L209)
- [expected/pgstattuple.out:255](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L255)
- [expected/pgstattuple.out:292](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L292)
- [pgstatindex.c#pgstatindex_impl-density-guards](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L372)
- [btree_index.sql#multilevel-page-deletion](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L252-L270)
- [plancat.c#get_relation_info-index-skips](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L256-L281)
- [indxpath.c#create_index_paths-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L260-L266)
- [indxpath.c#match_opclause_to_indexcol-op_in_opfamily](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2433-L2459)
- [ginutil.c#ginhandler](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L36-L89)
- [indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2203-L2269)
- [indxpath.c#get_index_clause_from_support](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2557-L2615)
- [indxpath.c#build_index_paths-generate](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L954-L962)
- [plancat.c#get_relation_info-am-flags](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L317-L335)
- [indxpath.c#get_index_paths-submit](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L740-L751)
- [indxpath.c#build_index_paths-parallel](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L975-L1002)
- [allpaths.c#create_partial_bitmap_paths](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4162-L4185)
- [indxpath.c#choose_bitmap_and-cheapest-of-group](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1353-L1399)
- [costsize.c#cost_bitmap_tree_node-indexpath](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1114-L1128)
- [indxpath.c#choose_bitmap_and-accept-reject](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1418-L1489)
- [btree_gin--1.0.sql#int4_ops](../../../../raw/postgres-17/contrib/btree_gin/btree_gin--1.0.sql#L56-L69)
- [indxpath.c#get_index_paths](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L709-L767)
- [ref/create_index.sgml#invalid-index](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L645-L667)
- [plancache.c#BuildCachedPlan-transient](../../../../raw/postgres-17/src/backend/utils/cache/plancache.c#L1022-L1033)
- [plancache.c#CheckCachedPlan-transient](../../../../raw/postgres-17/src/backend/utils/cache/plancache.c#L866-L873)
- [README.HOT#indcheckxmin](../../../../raw/postgres-17/src/backend/access/heap/README.HOT#L341-L353)
- [index.c#index_build-indcheckxmin](../../../../raw/postgres-17/src/backend/catalog/index.c#L3099-L3101)
- [index.c#reindex_index-indcheckxmin](../../../../raw/postgres-17/src/backend/catalog/index.c#L3800-L3850)
- [indxpath.c#check_index_predicates-predOK](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L3272-L3350)
- [indxpath.c#create_index_paths](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L234-L413)
- [pg_amop.dat#gin-array_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1232-L1244)
- [pg_amop.dat#gin-tsvector_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1290-L1296)
- [pg_amop.dat#gin-jsonb_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1593-L1611)
- [pg_amop.dat#gin-jsonb_path_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1613-L1622)
- [pg_amop.dat#btree-hash-jsonb_ops](../../../../raw/postgres-17/src/include/catalog/pg_amop.dat#L1571-L1591)
- [indices.sgml#other-operators](../../../../raw/postgres-17/doc/src/sgml/indices.sgml#L505-L508)
- [pgtrgm.sgml#index-support](../../../../raw/postgres-17/doc/src/sgml/pgtrgm.sgml#L413-L425)
- [btree-gin.sgml#caveats](../../../../raw/postgres-17/doc/src/sgml/btree-gin.sgml#L24-L33)
- [indxpath.c#build_index_paths-amoptionalkey](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L887-L897)
- [ginutil.c:49](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L49)
- [indxpath.c#build_index_paths-scantype](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L826-L842)
- [clauses.c#simplify_boolean_equality](../../../../raw/postgres-17/src/backend/optimizer/util/clauses.c#L3990-L4045)
- [indxpath.c#IsBooleanOpfamily](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2271-L2286)
- [pg_opfamily.h#IsBuiltinBooleanOpfamily](../../../../raw/postgres-17/src/include/catalog/pg_opfamily.h#L59-L65)
- [indxpath.c#match_boolean_index_clause](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2288-L2384)
- [bool.out#gin-bool-equality](../../../../raw/postgres-17/contrib/btree_gin/expected/bool.out#L89-L98)
- [ginutil.c:79](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L79)
- [nbtree.c:143](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L143)
- [ginutil.c#ginhandler-amcanorder](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L44-L45)
- [nbtree.c#bthandler-amcanorder](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L108-L109)
- [plancat.c#get_relation_info-sortopfamily](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L340-L422)
- [indxpath.c#build_index_paths-pathkeys](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L905-L944)
- [ginutil.c:70](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L70)
- [nbtree.c:134](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L134)
- [indexam.c#index_can_return](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L780-L797)
- [plancat.c#get_relation_info-canreturn](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L296-L301)
- [indxpath.c#check_index_only](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1730-L1800)
- [ginutil.c:51](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L51)
- [nbtree.c:115](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L115)
- [indxpath.c#match_clause_to_indexcol-nulltest](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2251-L2266)
- [ginutil.c:50](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L50)
- [nbtree.c:114](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L114)
- [indxpath.c#build_index_paths-saop](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L862-L885)
- [indxpath.c#get_index_paths-nonnative-saop](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L753-L766)
- [selfuncs.c#gincost_scalararrayopexpr](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7550-L7660)
- [ginutil.c:55](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L55)
- [nbtree.c:119](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L119)
- [indxpath.c:347](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L347)
- [nodeBitmapHeapscan.c#BitmapShouldInitializeSharedState](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L774-L806)
- [nodeBitmapHeapscan.c#BitmapHeapNext-shared-bitmap](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L130-L141)
- [nodeBitmapHeapscan.c#shared-iterator](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L143-L170)
- [nodeBitmapHeapscan.c:241](../../../../raw/postgres-17/src/backend/executor/nodeBitmapHeapscan.c#L241)
- [tidbitmap.c#tbm_shared_iterate](../../../../raw/postgres-17/src/backend/nodes/tidbitmap.c#L1044-L1136)
- [indexam.sgml#amgetbitmap](../../../../raw/postgres-17/doc/src/sgml/indexam.sgml#L991-L1010)
- [create_index.sql#gin-bitmap-only](../../../../raw/postgres-17/src/test/regress/sql/create_index.sql#L264-L268)
- [tsearch.sql#gin-bitmap-only](../../../../raw/postgres-17/src/test/regress/sql/tsearch.sql#L225-L230)
- [indices.sgml#ordering](../../../../raw/postgres-17/doc/src/sgml/indices.sgml#L530-L538)
- [indices.sgml#bitmap-scans](../../../../raw/postgres-17/doc/src/sgml/indices.sgml#L643-L656)
- [indices.sgml#index-only-scans](../../../../raw/postgres-17/doc/src/sgml/indices.sgml#L1125-L1136)
- [amutils.out#column-properties](../../../../raw/postgres-17/src/test/regress/expected/amutils.out#L96-L108)
- [amutils.out#index-properties](../../../../raw/postgres-17/src/test/regress/expected/amutils.out#L122-L129)
- [amutils.out#am-properties](../../../../raw/postgres-17/src/test/regress/expected/amutils.out#L152-L157)
- [selfuncs.c:7675](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7675)
- [selfuncs.c#gincostestimate-trust](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7713-L7727)
- [selfuncs.c#GinQualCounts](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7370-L7378)
- [selfuncs.c:7880](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7880)
- [selfuncs.c#gincostestimate-selectivity](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7778-L7784)
- [ginutil.c#ginGetStats](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L616-L642)
- [selfuncs.c#gincostestimate-entrypages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7888-L7914)
- [selfuncs.c#gincostestimate-descent](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7919-L7935)
- [selfuncs.c#gincostestimate-datapages](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7982-L8006)
- [selfuncs.c#gincostestimate-search-entry-cpu](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8008-L8015)
- [selfuncs.c#gincostestimate-datapages-cache](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8017-L8025)
- [selfuncs.c#gincostestimate-total](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8027-L8029)
- [selfuncs.c#gincostestimate-qualcost](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L8031-L8048)
- [selfuncs.c#gincostestimate](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7662-L8050)
- [costsize.c:628](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L628)
- [indxpath.c#bitmap_and_cost_est](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L1560-L1571)
- [pathnode.c#STD_FUZZ_FACTOR](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L42-L47)
- [gin.sgml#fast-update-flush](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L508-L515)
- [gin.sgml#fast-update-searches](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L521-L529)
- [guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585)
- [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1299-L1366)
- [gininsert.c#ginbuild-scan](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L382-L384)
- [gininsert.c:424](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L424)
- [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1027-L1091)
- [pgstatindex.c#pgstatginindex_internal](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L506-L577)
- [costsize.c#cost_bitmap_heap_scan-startup](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1044-L1048)
- [selfuncs.c:7886](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7886)
- [selfuncs.c:7980](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7980)
- [selfuncs.c#gincost_scalararrayopexpr-arrayScans](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7648-L7658)
- [selfuncs.c#gincostestimate-saop-clause](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7823-L7833)
- [selfuncs.c#gincostestimate-pending-guard](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7724-L7727)
- [selfuncs.c#gincostestimate-stats-branch](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7729-L7747)
- [selfuncs.c#gincostestimate-invented](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7748-L7767)
- [gininsert.c#gininsert-fastupdate](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L510-L530)
- [ginfast.c#needCleanup](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L448-L471)
- [ginfast.c#ginInsertCleanup-conditional-lock](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L818-L828)
- [ginfast.c#ginInsertCleanup-stop-at-tail](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L881-L888)
- [ref/create_index.sgml#fastupdate-note](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L524-L532)
- [analyze.c:527](../../../../raw/postgres-17/src/backend/commands/analyze.c#L527)
- [analyze.c#do_analyze_rel-index-cleanup](../../../../raw/postgres-17/src/backend/commands/analyze.c#L694-L721)
- [ginvacuum.c#ginvacuumcleanup-analyze-only](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L717)
- [ginfast.c:847](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L847)
- [gininsert.c#ginbuild-stats](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L405-L406)
- [gin.h#GIN_SEARCH_MODE_DEFAULT-to-EVERYTHING](../../../../raw/postgres-17/src/include/access/gin.h#L34-L37)
- [indexcmds.c#DefineIndex-am-checks](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L860-L879)
- [cluster.c#check_index_is_clusterable-amclusterable](../../../../raw/postgres-17/src/backend/commands/cluster.c#L517-L522)
- [costsize.c:130](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L130)
- [costsize.c#cost_seqscan-disable](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L304-L305)
- [index.c:1015](../../../../raw/postgres-17/src/backend/catalog/index.c#L1015)
- [pgstatindex.c#IS_INDEX](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L70-L72)
- [ref/create_index.sgml#concurrently-invalid](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L646-L651)
- [pg_class.h:177](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L177)
- [pgstatindex.c#pgstatginindex_internal-checks](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L520-L543)
- [rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/src/include/utils/rel.h#L667-L669)
- [prepjointree.c#is_simple_subquery](../../../../raw/postgres-17/src/backend/optimizer/prep/prepjointree.c#L1689-L1701)
- [pgstattuple--1.4--1.5.sql#pgstatginindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L49-L57)
- [pgstatindex.c#pgstatginindex_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L497-L504)
- [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620)
- [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)
- [selfuncs.c#gincostestimate-tablespace-costs](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7786-L7789)
- [costsize.c#cost_bitmap_heap_scan-disable](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1041-L1042)
- [config.sgml#guc-gin-pending-list-limit](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L9870-L9890)
- [reloptions.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L339-L347)
- [reloptions.c#fastupdate](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L123-L130)
- [gin.h#GinStatsData](../../../../raw/postgres-17/src/include/access/gin.h#L40-L50)
- [ginblock.h#GinMetaPageData](../../../../raw/postgres-17/src/include/access/ginblock.h#L55-L101)
- [pg_index.h#indisvalid](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L42-L43)
- [pathnodes.h:1168](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1168)
- [pathnodes.h:1181](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1181)
- [costsize.c#cost_bitmap_tree_node](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1114-L1144)
- [indxpath.c:343](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L343)
- [indxpath.c#match_clauses_to_index](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2051-L2064)
- [indxpath.c#match_clause_to_index](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L2084-L2136)
- [indxpath.c#build_index_paths](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L804-L1057)
- [selfuncs.c#gincost_pattern](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7380-L7492)
- [indxpath.c:341](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L341)
- [pathnode.c#create_bitmap_heap_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L1042-L1068)
- [jsonb.sql:852](../../../../raw/postgres-17/src/test/regress/sql/jsonb.sql#L852)
- [jsonb.sql:929](../../../../raw/postgres-17/src/test/regress/sql/jsonb.sql#L929)
- [jsonb.sql:932](../../../../raw/postgres-17/src/test/regress/sql/jsonb.sql#L932)
- [bool.sql#enable_seqscan-off](../../../../raw/postgres-17/contrib/btree_gin/sql/bool.sql#L1-L9)
- [mainloop.c#MainLoop-exit-status](../../../../raw/postgres-17/src/bin/psql/mainloop.c#L587-L594)
- [settings.h:172](../../../../raw/postgres-17/src/bin/psql/settings.h#L172)
- [pg_regress.c#make_temp_sockdir](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L499-L525)
- [pg_regress.c#PG_REGRESS_SOCK_DIR](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L842-L849)
- [fe-connect.c#conninfo_add_defaults](../../../../raw/postgres-17/src/interfaces/libpq/fe-connect.c#L6201-L6245)
- [fe-connect.c#pqConnectOptions2-host-type](../../../../raw/postgres-17/src/interfaces/libpq/fe-connect.c#L1189-L1204)
- [fe-connect.c#PQconnectPoll-host-address](../../../../raw/postgres-17/src/interfaces/libpq/fe-connect.c#L2754-L2764)
- [installation.sgml:40](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L40)
- [pqcomm.h:60](../../../../raw/postgres-17/src/include/libpq/pqcomm.h#L60)
- [pqcomm.c:453](../../../../raw/postgres-17/src/backend/libpq/pqcomm.c#L453)
- [guc_tables.c#port](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2393-L2401)
- [guc_tables.c#listen_addresses](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4436-L4445)
- [guc_tables.c#unix_socket_directories](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4425-L4434)
- [guc_tables.c#application_name](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4644-L4653)
- [btreefuncs.c:908](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L908)
- [costsize.c#cost_index-repeated-uncorrelated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L680-L683)
- [costsize.c#cost_index-repeated-correlated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L702-L707)
- [costsize.c#cost_index-normal-uncorrelated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L720-L723)
- [costsize.c#cost_index-normal-correlated](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L733-L746)
- [allpaths.c:4276](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L4276)
- [plancat.c:205](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L205)
- [selfuncs.c#get_variable_range](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L5969-L6098)
- [selfuncs.c:6810](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L6810)
- [index.c#index_update_stats-relallvisible](../../../../raw/postgres-17/src/backend/catalog/index.c#L2851-L2928)
- [README#bottom-up-added-in-14](../../../../raw/postgres-17/src/backend/access/nbtree/README#L980-L981)
- [bool.sql#explain-costs-off](../../../../raw/postgres-17/contrib/btree_gin/sql/bool.sql#L23-L26)
- [inval.c:1447](../../../../raw/postgres-17/src/backend/utils/cache/inval.c#L1447)
- [vacuumlazy.c#lazy_scan_heap-lazy_vacuum-call](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1051-L1052)
- [brin_revmap.c#HEAPBLK_TO_REVMAP_BLK](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L35-L43)
- [brin_revmap.c#revmap_extend_and_get_blkno](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L494-L514)
- [nbtsort.c:665](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L665)
- [nbtsearch.c#_bt_endpoint-empty-index](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L2590-L2606)
- [fe-connect.c#hostaddr-option](../../../../raw/postgres-17/src/interfaces/libpq/fe-connect.c#L223-L225)
- [selfuncs.c:7467](../../../../raw/postgres-17/src/backend/utils/adt/selfuncs.c#L7467)
- [ref/create_index.sgml#not-immediately-usable](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L640-L642)

## Navigation

- [v17/index](../../index.md)
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [Wiki Glossary (unverified)](../../../glossary.md)
- [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md) - the protocol for claims about wasted B-tree space and rebuild decisions; this page's rebuild advice is not scored against it.
- [Mandatory GIN Bloat Tests (unverified)](../../common-concepts/mandatory-gin-bloat-tests.md) - the protocol for claims about wasted GIN space, under which a pending list is deferred work rather than waste.
- [Mandatory Non-B-Tree, Non-GIN Bloat Tests (unverified)](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md) - the protocol for claims about wasted space in hash, GiST, SP-GiST and BRIN indexes; this page's pricing of those indexes is not scored against it.
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
- [log](../../../log.md)
- [How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 17 (unverified)](../indexing/reindex-index-concurrently.md) - the online rebuild that resets every input on this page.
- [Pros and Cons of Partial Indexes in PostgreSQL 17 (unverified)](../indexing/partial-indexes-pros-cons.md) - more on the partial-index costing path that behaves differently here.
- [How Bottom-Up Index Deletion and B-Tree Deduplication Work in PostgreSQL 17 (unverified)](../indexing/bottom-up-deletion-and-btree-deduplication.md) - the two mechanisms fixtures N, P and P-100 exercise, including the heap-block budget that decides what a bottom-up pass can free.
- [Planner Penalties for Bloated Indexes in PostgreSQL 12 (unverified)](../../../v12/questions/query-planning/bloated-indexes-query-planner.md) - the same question, and the same GIN-versus-B-tree follow-up, answered against the v12 pin.
