---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# Planner Penalties for Bloated Indexes in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
- [Planner Mechanisms](#planner-mechanisms)
  - [1. Physical page count enters index cost](#1-physical-page-count-enters-index-cost)
  - [2. B-tree height has an explicit bloat charge](#2-b-tree-height-has-an-explicit-bloat-charge)
  - [3. Index size participates in cache modeling](#3-index-size-participates-in-cache-modeling)
- [What The Planner Does Not See](#what-the-planner-does-not-see)
- [Examples Of Bloated Indexes](#examples-of-bloated-indexes)
  - [Low-density live leaf pages](#low-density-live-leaf-pages)
  - [Empty or deleted pages](#empty-or-deleted-pages)
  - [Taller B-trees](#taller-b-trees)
  - [Physically fragmented leaf chains](#physically-fragmented-leaf-chains)
- [How Density And Fragmentation Affect Different Queries](#how-density-and-fragmentation-affect-different-queries)
- [Practical Interpretation](#practical-interpretation)
- [Proposed Reindex Candidate Heuristic](#proposed-reindex-candidate-heuristic)
  - [Ordinary Non-Partial Indexes](#ordinary-non-partial-indexes)
  - [Partial Indexes](#partial-indexes)
- [Tests And Coverage](#tests-and-coverage)
- [Follow-Up: When A GIN Index Is Discarded And A B-Tree Is Used Instead](#follow-up-when-a-gin-index-is-discarded-and-a-b-tree-is-used-instead)
  - [Short answer](#short-answer)
  - [Gate 1: the clause never matches the GIN index](#gate-1-the-clause-never-matches-the-gin-index)
  - [Gate 2: the required plan shape rules GIN out](#gate-2-the-required-plan-shape-rules-gin-out)
  - [Gate 3: cost, and why GIN loses on the very same column](#gate-3-cost-and-why-gin-loses-on-the-very-same-column)
  - [A bloated GIN index loses to a B-tree](#a-bloated-gin-index-loses-to-a-b-tree)
  - [Stale GIN metapage statistics](#stale-gin-metapage-statistics)
  - [The keyless GIN path on a partial index](#the-keyless-gin-path-on-a-partial-index)
  - [Jobs no GIN index can be created for](#jobs-no-gin-index-can-be-created-for)
  - [Where GIN still wins](#where-gin-still-wins)
  - [Exact-pin measurements](#exact-pin-measurements)
  - [Settings that move the boundary](#settings-that-move-the-boundary)
  - [Key data structures](#key-data-structures)
  - [Caller and callee boundary](#caller-and-callee-boundary)
  - [Build, generated-header, and extension boundary](#build-generated-header-and-extension-boundary)
  - [Tests and explicit test absence](#tests-and-explicit-test-absence)
- [Open Questions](#open-questions)
- [Related Pages](#related-pages)
- [Evidence Map](#evidence-map)
- [Context Reviewed](#context-reviewed)
- [Source References](#source-references)

## Question

In PostgreSQL 12, are there mechanisms to penalize bloated indexes in the query planner? If there are, give a comprehensive explanation with examples of types of bloated indexes and how leaf fragmentation or density affects them.

Follow-up:

When might a GIN index be discarded by the query planner and a B-tree used instead?

## Answer

Yes, but the mechanism is indirect. PostgreSQL 12 does not store or cost a planner field named `bloat`, `avg_leaf_density`, or `leaf_fragmentation`. It penalizes a bloated B-tree when the bloat appears as more physical index pages, a higher B-tree level, or a larger cache footprint. `get_relation_info()` fills `IndexOptInfo.pages` from the current index block count for ordinary non-partial indexes and records B-tree height with `_bt_getrootheight()`; `btcostestimate()` and `genericcostestimate()` then turn those values into index scan cost ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L417), [selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815), [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116)). The block-count read itself is not a B-tree page scan: `RelationGetNumberOfBlocks()` asks the storage manager for the main-fork relation length, and the magnetic-disk storage manager computes that from segment file sizes through `FileSize()` / `lseek(SEEK_END)` ([bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-12/src/include/storage/bufmgr.h#L188-L199), [bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2791-L2811), [md.c#mdnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L698-L755), [fd.c#FileSize](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L2039-L2053)).

These effects are not all unique to B-trees. The physical-page-count penalty flows through the shared `genericcostestimate()` helper, so it also covers hash, GiST, and SP-GiST indexes; GIN and BRIN use separate cost models. The height penalty measured from the index itself is B-tree-only: GiST and SP-GiST charge the same descent formula but estimate the height from the physical page count, and hash charges no descent cost. Every `pgstatindex` metric in this page is B-tree-only ([selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815), [selfuncs.c#gistcostestimate-descent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6283-L6317), [selfuncs.c#hashcostestimate-no-descent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6237-L6260), [selfuncs.c#gincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6672), [selfuncs.c#brincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6985)).

The important distinction is this:

| Condition | Planner-visible in v12? | Effect |
|---|---:|---|
| More physical index blocks for the same useful keys | Yes | Raises estimated index page work through `index->pages / index->tuples` for ordinary non-partial indexes. |
| Higher B-tree height | Yes | Raises the explicit B-tree descent CPU charge. |
| Low `avg_leaf_density` reported by `pgstatindex` | Not directly | Matters only insofar as it produces more physical pages or height. |
| High `leaf_fragmentation` reported by `pgstatindex` | No | Can slow broad scans on cold storage, but the planner does not read this metric. |
| Empty, deleted, or nearly empty B-tree pages | Partly | Empty/deleted pages still contribute to relation size; nearly empty live pages raise pages per tuple. |

The PostgreSQL 12 manual describes B-tree bloat operationally as indexes with many empty or nearly empty pages and recommends `REINDEX` to reduce that space consumption. It separately says freshly constructed B-tree indexes are slightly faster because logically adjacent pages are usually physically adjacent, which is the runtime issue that `leaf_fragmentation` tries to expose ([ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L49-L55), [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L861-L889)).

## Planner Mechanisms

The planner reaches every index cost estimate through the index access method's `amcostestimate` support function. `get_relation_info()` copies `amcostestimate` from the AM handler into the `IndexOptInfo`, and `cost_index()` casts and calls it for each candidate index scan. PostgreSQL 12's B-tree handler points `amcostestimate` at `btcostestimate`, which is where the height-based charge in section 2 lives ([nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L134), [plancat.c#amcostestimate](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L276-L277), [costsize.c#cost_index-amcostestimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L544-L548)).

The physical-page-count penalty generalizes across the non-GIN, non-BRIN index types. `btcostestimate()`, `hashcostestimate()`, `gistcostestimate()`, and `spgcostestimate()` all delegate to the shared `genericcostestimate()` helper, so the `index->pages / index->tuples` page-count effect in section 1 applies to B-tree, hash, GiST, and SP-GiST indexes alike. `gincostestimate()` and `brincostestimate()` compute cost with their own models and never call `genericcostestimate()`, so this page's page-count formula does not describe GIN or BRIN bloat ([selfuncs.c#btcostestimate-genericcost](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6084), [selfuncs.c#hashcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6226-L6235), [selfuncs.c#gistcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6270-L6281), [selfuncs.c#spgcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6327-L6338), [selfuncs.c#gincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6672), [selfuncs.c#brincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6985)).

The height charge in section 2 uses a height measured from the index only for B-trees. `get_relation_info()` records a real `tree_height` from `_bt_getrootheight()` for B-tree indexes and sets `tree_height = -1` for every other access method ([selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L417)). `gistcostestimate()` and `spgcostestimate()` fill in that `-1` themselves: each assumes a fanout of 100, estimates the height as `log100(index->pages)`, and adds the same `(index->tree_height + 1) * 50.0 * cpu_operator_cost` charge, which its comment calls "calculated the same as for btrees". Their descent charge therefore tracks the physical page count rather than a height read from the index ([selfuncs.c#gistcostestimate-descent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6283-L6317), [selfuncs.c#spgcostestimate-descent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6340-L6374)). `hashcostestimate()` adds no descent charge at all; its comment says hash search goes directly to the target bucket ([selfuncs.c#hashcostestimate-no-descent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6237-L6260)). Every `pgstatindex` metric discussed below is B-tree-only, since `pgstatindex()` reads B-tree page structures.

### 1. Physical page count enters index cost

For a normal non-partial index, PostgreSQL 12 sets `info->pages = RelationGetNumberOfBlocks(indexRelation)` and `info->tuples = rel->tuples`. For a partial index, it calls `estimate_rel_size()`, whose index case still reports current blocks as `*pages` and estimates tuples from catalog tuple density after discounting the metapage ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L407), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L1026)).

That difference matters. In an ordinary non-partial index, extra blocks with the same parent-table tuple estimate directly increase `index->pages / index->tuples`. In a partial index, the current page count still enters costing, but the tuple estimate can scale from the index's recorded tuple density and current block count, so the page-count penalty is less direct ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L394-L407), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L990-L1027)).

#### How `RelationGetNumberOfBlocks(indexRelation)` gets the number

`RelationGetNumberOfBlocks(reln)` is only a macro wrapper around `RelationGetNumberOfBlocksInFork(reln, MAIN_FORKNUM)`, and `MAIN_FORKNUM` is the main relation fork. For indexes, `RelationGetNumberOfBlocksInFork()` opens storage-manager state if needed and returns `smgrnblocks(relation->rd_smgr, forkNum)` ([bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-12/src/include/storage/bufmgr.h#L188-L199), [relpath.h#ForkNumber](../../../../raw/postgres-12/src/include/common/relpath.h#L40-L46), [bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2791-L2811)).

That storage-manager open is lightweight. `RelationOpenSmgr` attaches an `SMgrRelation` only when `rd_smgr` is null, and `smgropen()` looks up or creates the `SMgrRelation` object without opening the underlying relation file. The real file-length work begins when `smgrnblocks()` dispatches through the storage-manager table; PostgreSQL 12's built-in table maps `smgr_nblocks` to `mdnblocks()` for the magnetic-disk storage manager ([rel.h#RelationOpenSmgr](../../../../raw/postgres-12/src/include/utils/rel.h#L472-L479), [smgr.c#smgropen](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L139-L178), [smgr.c#smgrsw](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L40-L83), [smgr.c#smgrnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L630-L640)).

`mdnblocks()` opens the first segment with `mdopen()` if that segment is not already open. `mdopen()` itself opens only the first segment and is a no-op when that segment is already open. `mdnblocks()` then starts from the last open segment, calls `_mdnblocks()` for that segment, and returns `segno * RELSEG_SIZE + nblocks` as soon as it finds a segment smaller than `RELSEG_SIZE`. If a segment is exactly `RELSEG_SIZE`, `mdnblocks()` tries to open the next segment; a missing next segment means the relation length is exactly the number of full segments already found ([md.c#mdopen](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L428-L465), [md.c#mdnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L698-L755)).

`_mdnblocks()` does not read relation blocks. It calls `FileSize(seg->mdfd_vfd)`, checks for an error, and divides the byte length by `BLCKSZ`, ignoring any partial trailing block. `FileSize()` opens the virtual file descriptor if needed and returns `lseek(VfdCache[file].fd, 0, SEEK_END)`. `_mdfd_openseg()` opens later segment files when `mdnblocks()` has to discover more full segments, and assertion-enabled builds can add extra `_mdnblocks()` checks there; those checks are still file-size probes, not page reads ([md.c#_mdnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L1229-L1242), [fd.c#FileSize](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L2039-L2053), [md.c#_mdfd_openseg](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L1056-L1089)).

So the PostgreSQL relation-page I/O for `info->pages = RelationGetNumberOfBlocks(indexRelation)` is zero: this path invokes the `smgr_nblocks` callback, not the `smgr_read` callback, and it does not bring B-tree pages into shared buffers. At the operating-system level, the common already-open single-segment case is a file-size seek on one segment descriptor plus function-call, switch, arithmetic, and virtual-file-descriptor overhead. If the backend has not opened the relation file yet, add an `SMgrRelation` hash lookup or creation and a `PathNameOpenFile()` for the first segment. If the index spans multiple relation segment files, a first discovery pass can open and size each full segment until it reaches the final partial segment or a missing next segment. Relation segment files are capped by `RELSEG_SIZE * BLCKSZ`, and the source comment says the default segment limit is 1GB, so the loop scales with segment files, not with B-tree pages or tuples ([smgr.c#smgrsw](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L40-L83), [md.c#mdopen](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L428-L465), [md.c#mdnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L698-L755), [pg_config.h.in#RELSEG_SIZE](../../../../raw/postgres-12/src/include/pg_config.h.in#L853-L864)).

The CPU cost is therefore `O(1)` for a normal index whose last open segment is the only segment that needs checking, and `O(number_of_segment_files_probed)` for a large multi-segment relation or first-time segment discovery. It is not `O(index_pages)` and not `O(index_tuples)`. Wall time can still include filesystem metadata latency: a cold directory entry, inode, or file descriptor open can make the kernel perform metadata I/O, but PostgreSQL is not transferring index page contents for this planner field ([md.c#mdnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L698-L755), [fd.c#FileSize](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L2039-L2053)).

`genericcostestimate()` estimates the number of index pages touched as a pro-rata fraction of total index pages:

```c
if (index->pages > 1 && index->tuples > 1)
    numIndexPages = ceil(numIndexTuples * index->pages / index->tuples);
else
    numIndexPages = 1.0;
```

It then charges random page cost per touched page for a single scan, or applies `index_pages_fetched()` to model cache effects for repeated scans such as nested-loop inner index scans and scalar-array scans ([selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815), [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L787-L878)).

This means an ordinary non-partial B-tree with twice as many physical pages for the same estimated useful tuples will usually look more expensive for range scans, bitmap index scans, and broad index-only scans. The effect is weaker for a highly selective point lookup because `ceil()` often keeps the estimated leaf pages at one, and a tiny index of one page or one tuple is floored to a single page by the `index->pages > 1 && index->tuples > 1` guard ([selfuncs.c#genericcostestimate-guard](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5777-L5780)).

### 2. B-tree height has an explicit bloat charge

After `genericcostestimate()`, `btcostestimate()` adds a B-tree descent CPU charge. It first charges about `log2(index->tuples) * cpu_operator_cost` for comparisons ([selfuncs.c#btcostestimate-descent-comparisons](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6097-L6102)), then adds:

```c
descentCost = (index->tree_height + 1) * 50.0 * cpu_operator_cost;
```

The comment says this prevents bloated indexes from appearing to have the same search cost as unbloated ones when only a single leaf page is expected. `get_relation_info()` records `tree_height` from `_bt_getrootheight()` while it has the B-tree open ([selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L417)).

The planner height is the fast-root height. `_bt_getrootheight()` returns the cached metapage's `btm_fastlevel`, and its comment says this represents the levels a search descends through. `pgstatindex()` reports `btm_level` as `tree_level`, so after B-tree page deletion creates a fast root, `pgstatindex.tree_level` and planner `tree_height` need not be the same number ([nbtpage.c#_bt_getrootheight](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L575-L626), [nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L90-L110), [pgstatindex.c#metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L239-L249)).

This is the most explicit planner-side bloat penalty in the v12 B-tree code. It is still not a density or fragmentation penalty; it only changes when the B-tree level changes.

### 3. Index size participates in cache modeling

`index_pages_fetched()` estimates cache effects with the Mackert-Lohman formula. It adds the caller's `index_pages` to `root->total_table_pages` when prorating `effective_cache_size`, so a larger index increases the estimated cache competition term used in both index page costing and heap page costing around index scans ([costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L787-L878), [costsize.c#cost_index](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L470-L665)).

The page-cost constants are global or tablespace-level estimates. `seq_page_cost` defaults to 1.0, and `random_page_cost` defaults to 4.0; lowering `random_page_cost` makes index scans look cheaper, raising it makes them look more expensive, but this is not a per-index bloat signal ([config.sgml#seq-random-page-cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4696-L4765)). `seq_page_cost`, `random_page_cost`, and `effective_cache_size` are all `PGC_USERSET` (`user`-context) GUCs, so a session can change them with `SET` for the current session or transaction; none needs a server restart or a config reload ([guc.c#seq-random-page-cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3207-L3227), [guc.c#effective-cache-size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3108-L3113)).

## What The Planner Does Not See

`pgstatindex()` is a diagnostic function in `contrib/pgstattuple`, not an input to planner path creation. It scans B-tree blocks, counts leaf/internal/empty/deleted pages, sums leaf free space, and counts backward right-link transitions. The result tuple includes `avg_leaf_density` and `leaf_fragmentation`, but those values are not read by `get_relation_info()`, `genericcostestimate()`, or `btcostestimate()` ([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L216-L365), [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L417), [selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815)).

`avg_leaf_density` is computed as `100 - free_space / max_avail * 100` across live leaf pages. The free-space input is `PageGetFreeSpace(page)`, and `pgstatindex()` ignores deleted and half-dead pages for that density denominator ([pgstatindex.c#leaf-density](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L288-L356)).

`leaf_fragmentation` is computed as `fragments / leaf_pages * 100`, where a fragment is counted when a live leaf page's `btpo_next` is not `P_NONE` and points to a lower physical block number. `BTPageOpaqueData` stores both sibling links, so this metric is about physical order of the logical leaf chain, not free space or tuple density ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L300-L307), [pgstatindex.c#result-formulas](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L356), [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L30-L68)).

## Examples Of Bloated Indexes

### Low-density live leaf pages

A B-tree can have many live leaf pages that are only partly full. The docs describe the common shape: completely empty B-tree pages can be reclaimed for reuse, but a page with only a few remaining keys can stay allocated, so patterns that delete most but not all keys from many key ranges produce poor space use ([maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L861-L874)).

For a fixed live tuple count and tuple width, leaf-page count scales approximately as:

```text
leaf_page_multiplier = baseline_density / observed_density
```

So a 60% dense index needs about `90 / 60 = 1.5x` as many leaf pages as a 90% dense index for the same live entries. The planner does not know the 60% number, but it can see the larger `index->pages`; broad scans then get a larger `numIndexPages` estimate ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L407), [selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815)).

At execution, B-tree scans position once and then walk leaf pages. `btgettuple()` calls `_bt_first()` for the first tuple and `_bt_next()` after that; `_bt_next()` calls `_bt_steppage()` when the current leaf page is exhausted; forward `_bt_readnextpage()` follows the saved right link and reads the next block with `_bt_getbuf()` ([nbtree.c#btgettuple](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L213-L284), [nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1334-L1381), [nbtsearch.c#_bt_steppage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1619-L1724), [nbtsearch.c#forward-readnextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1727-L1800), [nbtpage.c#_bt_getbuf](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L748-L820)).

### Empty or deleted pages

`pgstatindex()` reports `deleted_pages` for pages marked deleted and `empty_pages` for the remaining `P_IGNORE` case, which is the half-dead state in this code path. The diagnostic's `index_size` includes leaf, internal, empty, deleted, and metapage blocks, so this kind of bloat appears as physical relation size even though those pages do not hold useful live keys ([pgstatindex.c#page-classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L264-L344), [nbtree.h#P_IGNORE](../../../../raw/postgres-12/src/include/access/nbtree.h#L186-L195)).

The planner's physical page count does not subtract those diagnostic categories. For ordinary non-partial indexes, it reads the index relation's current block count; for partial indexes, the index branch of `estimate_rel_size()` reports current blocks as pages ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L407), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L972)).

This can make a bloated index look more expensive even when many extra pages are not useful scan pages. The model is deliberately coarse: `genericcostestimate()` treats touched index pages as a pro-rata fraction of total pages and says this simplistic method effectively counts leaf pages while ignoring metapage and upper-level overhead ([selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815)).

This page-count inflation is not always permanent. A deleted B-tree page that has aged past its recyclable horizon can be handed back out by a later page split, because `_bt_getbuf(rel, P_NEW)` asks `GetFreeIndexPage()` for a free page before extending the relation. So under ongoing insert load some deleted pages are reused rather than left as permanent dead weight in `index->pages` — the same FSM reuse described in the fragmented leaf-chains example below ([nbtpage.c#_bt_getbuf-new-page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L748-L820)).

### Taller B-trees

If extra pages are enough to add another planner-visible B-tree search level, point lookups and narrow scans get a direct cost increase from the `tree_height + 1` descent charge. The B-tree metapage stores both `btm_level` and `btm_fastlevel`; `pgstatindex()` reports `btm_level` as `tree_level`, while planner costing uses `_bt_getrootheight()` and therefore `btm_fastlevel` ([nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L90-L110), [pgstatindex.c#metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L239-L249), [nbtpage.c#_bt_getrootheight](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L575-L626), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L417), [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116)).

This is why a unique equality probe is not completely blind to severe bloat: even when the estimated leaf pages remain one, a taller tree raises startup and total cost.

### Physically fragmented leaf chains

Leaf fragmentation is different from density. A fragmented index can have the same number of live leaf pages and the same average density as an unfragmented index, but its logical next leaf pages can be physically out of order. `pgstatindex()` counts a fragment when `btpo_next` points backward to a lower block number ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L300-L307)).

The planner does not cost that. The executor can still feel it. Forward scans follow `btpo_next` through `_bt_readnextpage()` and read the named block with `_bt_getbuf()`. If those blocks are not physically adjacent, cold scans can lose sequential locality. The v12 manual states the same operational point: a freshly constructed B-tree is slightly faster because logically adjacent pages are usually physically adjacent ([nbtsearch.c#forward-readnextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1727-L1800), [nbtpage.c#_bt_getbuf](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L748-L820), [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L881-L889)).

Page splits and page reuse explain how this can happen. `_bt_split()` allocates a new right page with `_bt_getbuf(rel, P_NEW, BT_WRITE)`, then updates sibling links. `_bt_getbuf(P_NEW)` first asks the free space map for a reusable index page before extending the relation, so a new logical neighbor may be placed at an older physical block ([nbtinsert.c#split-new-right-page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L1408-L1437), [nbtpage.c#_bt_getbuf-new-page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L748-L820)).

## How Density And Fragmentation Affect Different Queries

| Query shape | Density effect | Fragmentation effect |
|---|---|---|
| Unique point lookup | Usually small unless height rises; estimated leaf pages often remain one. | Usually small because the scan does not walk many leaf links. |
| Selective range scan | More leaf pages for the same key range raises planner cost and executor page steps. | Can add cold-storage latency if the range spans many physically disordered leaves. |
| Wide range scan or ordered index scan | Often large; page count can scale near linearly with density loss. | Can be large on seek-sensitive storage; invisible to planner. |
| Bitmap index scan | B-tree side still uses `_bt_first()` and `_bt_next()` while filling the TID bitmap. | Same index-side locality issue; heap access after bitmap creation is a separate cost. |
| Index-only scan | Same index leaf walk; heap fetches may be avoided by visibility map state. | Same leaf-chain locality issue for the index pages that are read. |

`btgetbitmap()` confirms the bitmap case: it fetches the first matching B-tree tuple and continues scanning by calling `_bt_next()` while adding TIDs to the bitmap ([nbtree.c#btgetbitmap](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L287-L335)). Index-only scans still get TIDs through the index access method; they avoid heap access only when the visibility map says the heap page is all-visible ([indexam.c#index_getnext_tid](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L502-L545), [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L121-L170)).

## Practical Interpretation

Use `pgstatindex()` as a diagnosis, not as a direct explanation of planner choices. Low density and many empty/deleted pages are important because they usually increase the physical page count that the planner can see. Fragmentation is important because it can hurt wall-clock scan time, especially on cold or seek-sensitive storage, but it does not change v12 planner cost by itself ([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L216-L365), [selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815), [config.sgml#seq-random-page-cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4696-L4765)).

`REINDEX` is the source-backed repair for physical B-tree bloat. The v12 docs say it rebuilds the index from table data, reduces bloat by writing a new version without dead pages, and can apply changed storage parameters such as fillfactor ([ref/reindex.sgml#reindex-use-cases](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L32-L72)). B-tree fillfactor defaults to 90, can be set from 10 to 100, and is useful differently for static versus heavily updated tables ([create_index.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L369-L390), [nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L159-L171)).

## Proposed Reindex Candidate Heuristic

Treat `avg_leaf_density` and `leaf_fragmentation` as triage signals, not as automatic `REINDEX` triggers. PostgreSQL 12 exposes both fields through `pgstatindex(regclass)` (the installed default extension version 1.5 re-creates the function with the same output columns), and `pgstatindex_impl()` computes them by scanning B-tree pages; the planner still does not read either value, and the v12 manuals describe REINDEX-worthy B-tree bloat and physical-adjacency benefits without defining percentage cutoffs ([pgstattuple--1.4.sql#pgstatindex-regclass](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L62-L73), [pgstattuple--1.4--1.5.sql#pgstatindex-regclass-15](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92), [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L216-L365), [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L861-L895), [ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L49-L55)).

Use a size and workload gate before acting on either metric. The signal matters most when the index is large, growing faster than the live key set, or used by range scans, ordered index scans, bitmap index scans, or index-only scans that walk many leaf pages. Those are the cases where PostgreSQL's page-count costing and executor leaf-page traversal make extra leaf pages or poor physical order visible in cost or wall-clock time ([selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815), [nbtsearch.c#forward-readnextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1727-L1800), [nbtree.c#btgetbitmap](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L287-L335), [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L121-L170)).

### Ordinary Non-Partial Indexes

For an ordinary non-partial B-tree, low density is the cleaner REINDEX signal. `get_relation_info()` sets `info->pages` to the current index block count and `info->tuples` to the parent table's tuple estimate, so extra pages for the same useful key population feed directly into the `index->pages / index->tuples` term used by `genericcostestimate()` ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L407), [selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815)).

| Signal | Proposed candidate band | Interpretation for ordinary indexes |
|---|---|---|
| Low `avg_leaf_density` alone | Watch below about 70%; strong candidate below about 50-60% when the index is large or scan-heavy. | A default-built B-tree targets 90% leaf fillfactor, so 70% density implies roughly `90 / 70 = 1.29x` as many leaf pages as a 90% baseline, and 60% implies `1.5x`. This is a practical threshold, not a PostgreSQL-defined rule ([create_index.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L369-L390), [pgstatindex.c#leaf-density](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L288-L356)). |
| High `leaf_fragmentation` alone | Watch around 30%; strong candidate above about 50% only when broad leaf-chain scans are latency-sensitive. | The metric counts backward physical jumps in the logical leaf chain, so it points at lost locality rather than wasted space. A rebuilt B-tree can help because freshly built B-trees usually place logically adjacent pages physically adjacent, but the metric does not encode jump distance or cache residency ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L300-L307), [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L881-L889)). |
| Low density and high fragmentation together | Strong candidate even if neither metric is individually extreme, especially for repeated range or ordered scans. | Low density increases the page population the planner can see through `index->pages`; fragmentation can add storage-locality cost that the planner does not see. This combination is where `REINDEX` can plausibly improve both estimated cost and runtime locality ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L417), [selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815), [pgstatindex.c#result-formulas](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L356)). |

### Partial Indexes

For a partial B-tree, use the same `pgstatindex()` metrics, but be more conservative before calling it a planner-cost problem. `get_relation_info()` does not set `info->tuples` to the parent table estimate for partial indexes. It calls `estimate_rel_size()`, which still reports the current index block count as `pages` but estimates tuples from the partial index's own catalog tuple density after discounting the metapage; `get_relation_info()` then clamps that tuple estimate to the parent table size ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L407), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L1026)).

That means a low `avg_leaf_density` partial index is still a REINDEX candidate when it is large or scan-heavy, but the planner penalty is less direct than for an ordinary index. The strongest partial-index candidates are those where low density or many empty/deleted pages coincide with a large current `index_size`, a stable or shrinking predicate-matching row set, and observed plans or `EXPLAIN (ANALYZE, BUFFERS)` output showing expensive scans. High `leaf_fragmentation` remains a runtime-locality signal rather than a planner input, so it matters most for partial indexes that support broad ordered or range scans over the predicate slice ([pgstatindex.c#result-formulas](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L356), [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L861-L889), [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867-L2978)).

Keep small indexes and point-lookup-only indexes low in the queue unless height, relation size, or observed latency changed. `REINDEX` rewrites the index and normally takes an `ACCESS EXCLUSIVE` lock; `REINDEX CONCURRENTLY` reduces the lock level but is still maintenance work, so the better candidate is an index whose diagnostic signal lines up with size, workload shape, and observed query cost or buffer behavior ([maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L890-L895), [ref/reindex.sgml#reindex-use-cases](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L32-L72), [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867-L2978)).

## Tests And Coverage

The `pgstattuple` regression test checks `pgstatindex()` entry points and empty-index output, but it does not create populated B-trees with non-`NaN` density or nonzero fragmentation assertions ([pgstattuple.sql#pgstatindex-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L18-L113), [pgstattuple.out#empty-index-output](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L47-L85)).

The core `btree_index` regression test is present in the v12 regression schedule. Its test body creates a deliberately tall B-tree with `fillfactor = 10` and covers B-tree page deletion plus FSM page recycling after `VACUUM`, but it does not compare planner choices for the same logical index at different `avg_leaf_density` or `leaf_fragmentation` levels ([serial_schedule#btree_index](../../../../raw/postgres-12/src/test/regress/serial_schedule#L100), [parallel_schedule#btree_index](../../../../raw/postgres-12/src/test/regress/parallel_schedule#L71), [btree_index.sql#tall-fillfactor](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L110-L123), [btree_index.sql#page-recycling](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L147-L162)).

## Follow-Up: When A GIN Index Is Discarded And A B-Tree Is Used Instead

### Short answer

PostgreSQL 12 discards a GIN index at three separate gates, and only the third one is about cost. A GIN index that clears gates 1 and 2 still loses to a B-tree on the same column for ordinary comparison predicates, because `gincostestimate()` charges `random_page_cost` for every entry page, data page, and pending-list page it expects to touch, while `genericcostestimate()` charges the B-tree a pro-rata page share plus cheap CPU descent.

| Gate | Where | What makes GIN lose | Recovery |
|---|---|---|---|
| 1. Clause matching | `match_clause_to_indexcol()` | The query operator is not in the GIN index's operator family, and no planner support function rewrites it, so no `IndexClause` and therefore no GIN path is ever created ([indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2380-L2447), [indxpath.c#match_opclause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2546-L2663)). | Use a matching operator, or add the operators through `contrib/btree_gin`. |
| 2. Plan shape | `build_index_paths()` / `get_index_paths()` | GIN has no `amgettuple`, no ordering, and no `amcanreturn`, so it cannot produce a plain `Index Scan`, cannot satisfy `ORDER BY` pathkeys, cannot feed an `Index Only Scan`, cannot serve `IS NULL`, and handles `= ANY (array)` only through the bitmap path ([ginutil.c#ginhandler](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L36-L81), [indxpath.c#get_index_paths-submit](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L789-L800), [indxpath.c#build_index_paths-pathkeys](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L985-L1028)). | None. These are AM properties, not costs. |
| 3. Cost | `gincostestimate()` vs `btcostestimate()`, then `add_path()` / `choose_bitmap_and()` | GIN's page charges are all at `random_page_cost` and include the whole pending list; the B-tree's are a pro-rata share of `index->pages` plus a small descent charge ([selfuncs.c#gincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6672-L6979), [selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815), [pathnode.c#add_path](../../../../raw/postgres-12/src/backend/optimizer/util/pathnode.c#L422-L464)). | Clean the pending list, `VACUUM`, or drop `fastupdate`. |

At the pin, the same `n = 42` predicate on the same 300,000-row table with the same statistics cost `12.22` through a `btree_gin` GIN index and `4.65` through a B-tree index, and the planner chose the B-tree.

### Gate 1: the clause never matches the GIN index

`create_index_paths()` walks `rel->indexlist` and calls `match_restriction_clauses_to_index()` for each index before any cost model runs ([indxpath.c#create_index_paths](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L232-L308)). For an `OpExpr`, `match_opclause_to_indexcol()` accepts the clause only when the index column's collation matches and `op_in_opfamily(expr_op, opfamily)` is true; otherwise it falls through to `get_index_clause_from_support()`, the planner-support-function escape hatch ([indxpath.c#match_opclause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2546-L2663), [indxpath.c#get_index_clause_from_support](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2717-L2774)).

The core GIN operator families do not contain the B-tree comparison operators. Their `pg_amop` memberships are bootstrap catalog data, and none of them lists `<`, `<=`, `>=`, or `>`:

| GIN opfamily | Operators declared | Evidence |
|---|---|---|
| `gin/array_ops` | `&&`, `@>`, `<@`, `=` (whole-array equality, GIN strategy 4) | [pg_amop.dat#gin-array_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1211-L1223) |
| `gin/tsvector_ops` | `@@`, `@@@` | [pg_amop.dat#gin-tsvector_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1269-L1275) |
| `gin/jsonb_ops` | `@>`, `?`, `?|`, `?&`, `@?`, `@@` | [pg_amop.dat#gin-jsonb_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1458-L1476) |
| `gin/jsonb_path_ops` | `@>`, `@?`, `@@` | [pg_amop.dat#gin-jsonb_path_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1478-L1487) |

So `WHERE jb = '{"k": 42}'::jsonb` cannot use a `jsonb_ops` GIN index at all: `jsonb`'s `=` lives in the B-tree and hash families, not the GIN one ([pg_amop.dat#btree-hash-jsonb_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1436-L1456)). The manual states the rule directly: "each column must be used with operators appropriate to the index type; clauses that involve other operators will not be considered" ([indices.sgml#other-operators](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L454-L457)). `contrib/pg_trgm` says the same about its own class: "These indexes do not support equality nor simple comparison operators, so you may need a regular B-tree index too" ([pgtrgm.sgml#index-support](../../../../raw/postgres-12/doc/src/sgml/pgtrgm.sgml#L363-L372)).

`contrib/btree_gin` closes gate 1 deliberately. Each of its operator classes declares exactly strategies 1 through 5 — `<`, `<=`, `=`, `>=`, `>` — with the type's B-tree comparison proc as GIN support function 1 ([btree_gin--1.0.sql#int4_ops](../../../../raw/postgres-12/contrib/btree_gin/btree_gin--1.0.sql#L56-L69)). Its own documentation, however, states the conclusion this follow-up asks about: "In general, these operator classes will not outperform the equivalent standard B-tree index methods, and they lack one major feature of the standard B-tree code: the ability to enforce uniqueness" ([btree-gin.sgml#caveats](../../../../raw/postgres-12/doc/src/sgml/btree-gin.sgml#L24-L33)).

One non-cost rejection is worth naming because it is easy to misattribute. For a boolean column, `WHERE i = true` is simplified to a bare boolean `Var`, so no `OpExpr` survives to match the opclass, and the upstream expected output shows a `Seq Scan` with `Filter: i` even though the test sets `enable_seqscan=off` ([bool.out#gin-seqscan](../../../../raw/postgres-12/contrib/btree_gin/expected/bool.out#L88-L96), [bool.sql#enable_seqscan-off](../../../../raw/postgres-12/contrib/btree_gin/sql/bool.sql#L1-L9)). That is clause simplification, not `gincostestimate()`.

### Gate 2: the required plan shape rules GIN out

`get_relation_info()` copies a fixed set of AM capability flags into each `IndexOptInfo`, deriving `amhasgettuple` and `amhasgetbitmap` from whether the AM supplies those callbacks ([plancat.c#get_relation_info-am-flags](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L266-L279)). GIN and B-tree differ on almost every one:

| `IndexAmRoutine` field | GIN | B-tree | Planner consequence |
|---|---|---|---|
| `amgettuple` | `NULL` | `btgettuple` | `get_index_paths()` submits a plain `IndexPath` to `add_path()` only when `index->amhasgettuple`; a GIN path can only be collected into `*bitindexpaths` ([indxpath.c#get_index_paths-submit](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L789-L800)). |
| `amcanorder` / `amcanorderbyop` | `false` / `false` | `true` / `false` | `get_relation_info()` fills `sortopfamily` only for `BTREE_AM_OID` or another `amcanorder` AM, so `index_is_ordered` is false for GIN and `useful_pathkeys` stays `NIL` ([plancat.c#get_relation_info-sortopfamily](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L281-L320), [indxpath.c#build_index_paths-pathkeys](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L985-L1020)). |
| `amcanreturn` | `NULL` | `btcanreturn` | `index_can_return()` returns false when `amcanreturn` is `NULL`, so every `canreturn[i]` is false and `check_index_only()` fails ([indexam.c#index_can_return](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L714-L731), [indxpath.c#check_index_only](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1895-L1907)). |
| `amsearchnulls` | `false` | `true` | `match_clause_to_indexcol()` only accepts a `NullTest` when `index->amsearchnulls`, so `IS NULL` never reaches GIN ([indxpath.c#match_clause_to_indexcol-nulltest](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2429-L2444)). |
| `amsearcharray` | `false` | `true` | A `ScalarArrayOpExpr` is skipped for plain paths and re-offered only for bitmap paths, and `counts.arrayScans` multiplies the GIN estimate ([indxpath.c#build_index_paths-saop](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L932-L956), [indxpath.c#get_index_paths-nonnative-saop](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L802-L816)). |
| `amcanparallel` | `false` | `true` | No partial GIN index path; `build_index_paths()` gates parallel paths on `index->amcanparallel` ([ginutil.c#ginhandler](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L41-L56), [indxpath.c#build_index_paths-parallel](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1053-L1072)). |

Both handlers set these in one place: [ginutil.c#ginhandler](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L36-L81) and [nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L106-L151).

Three consequences follow, and none of them can be reversed by tuning:

- **No plain index scan.** The AM developer documentation explains why: `amgetbitmap` returns tuples in a bitmap that "doesn't have any specific ordering", "ordering operators will never be supplied for such a scan", and "there is no provision for index-only scans with `amgetbitmap`, since there is no way to return the contents of index tuples" ([indexam.sgml#amgetbitmap](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L862-L881)). Two upstream test comments say the same operationally: "GIN currently supports only bitmap scans, not plain indexscans" and "GIN only supports bitmapscan, so no need to test plain indexscan" ([create_index.sql#gin-bitmap-only](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L271-L279), [tsearch.sql#gin-bitmap-only](../../../../raw/postgres-12/src/test/regress/sql/tsearch.sql#L94-L101)).
- **No sorted output.** "Of the index types currently supported by PostgreSQL, only B-tree can produce sorted output" ([indices.sgml#ordering](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L479-L487)). Even a bitmap plan built from a B-tree loses order, because the bitmap is laid out in physical order ([indices.sgml#bitmap-scans](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L592-L605)).
- **No index-only scan.** "As a counterexample, GIN indexes cannot support index-only scans because each index entry typically holds only part of the original data value" ([indices.sgml#index-only-scans](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L1044-L1056)), matching the `amcanreturn` contract ([indexam.sgml#amcanreturn](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L373-L386)).

The upstream `amutils` regression test asserts exactly this property matrix for `gin` versus `btree`: `orderable`, `returnable`, `search_array`, and `search_nulls` are all `f` for GIN while `bitmap_scan` is `t` and `index_scan` is `f`, and `can_order`, `can_unique`, `can_include` are all `f` ([amutils.out#column-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L96-L108), [amutils.out#index-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L122-L129), [amutils.out#am-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L150-L158)).

### Gate 3: cost, and why GIN loses on the very same column

`cost_index()` calls the AM's `amcostestimate` through the `IndexOptInfo` function pointer, so GIN and B-tree paths for the same clause are priced by different code ([costsize.c#cost_index-amcostestimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L537-L548)). `gincostestimate()` builds its estimate as follows:

1. Read the metapage counters with `ginGetStats()`. Only `nPendingPages` is current; the rest are as of the last `VACUUM` ([selfuncs.c#gincostestimate-stats](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6700-L6772), [ginutil.c#ginGetStats](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L631-L657)).
2. Seed the startup page count with the **entire pending list**: `entryPagesFetched = numPendingPages` ([selfuncs.c#gincostestimate-pending](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6864-L6873)).
3. Add `ceil(counts.searchEntries * rint(pow(numEntryPages, 0.15)))` entry pages, plus a proportional share of entry and data pages for partial-match keys ([selfuncs.c#gincostestimate-entrypages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6875-L6901)).
4. Charge all of that at `random_page_cost` as **startup** cost, "because logically-close pages could be far apart on disk" ([selfuncs.c#gincostestimate-startup](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6922-L6926)).
5. Add scan-time data pages, taking the larger of the per-entry estimate and a selectivity-derived floor of `ceil(indexSelectivity * numTuples / (BLCKSZ / 3))`, again at `random_page_cost` ([selfuncs.c#gincostestimate-datapages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6928-L6966)).
6. Add qual evaluation costs, with no descent charge and no ordering support ([selfuncs.c#gincostestimate-qualcost](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6968-L6979)).

`btcostestimate()` instead delegates to `genericcostestimate()`, which estimates `numIndexPages = ceil(numIndexTuples * index->pages / index->tuples)`, then adds a `log2(index->tuples)` comparison charge and the `(tree_height + 1) * 50.0 * cpu_operator_cost` descent charge described in section 2 above ([selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815), [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6097-L6116)).

That asymmetry is the whole story for a selective equality lookup, and it survives GIN being the physically smaller index. At the pin, `t_both` carried both a `btree_gin` GIN index of 279 pages and a B-tree index of 826 pages on the same `int` column, with `pgstatindex` reporting `tree_level = 2` for the B-tree. For `n = 42` (30 matching rows out of 300,000):

- GIN charged 3 pages at `random_page_cost`: total `12.22` at `random_page_cost = 4`, falling to `3.22` at `random_page_cost = 1`, so `(12.22 - 3.22) / 3 = 3.00` pages.
- The B-tree charged 1 page plus CPU: `ceil(30 * 826 / 300000) = 1` page at `4.0`, plus `log2(300000) * 0.0025 ≈ 0.046`, plus `(2 + 1) * 50 * 0.0025 = 0.375`, plus `30 * (0.005 + 0.0025) = 0.225`, totalling `4.65` — exactly what `EXPLAIN` printed.

The losing path is then dropped by ordinary path pruning. `add_path()` compares candidates with `compare_path_costs_fuzzily()` at `STD_FUZZ_FACTOR = 1.01` and refuses or removes a dominated path ([pathnode.c#add_path](../../../../raw/postgres-12/src/backend/optimizer/util/pathnode.c#L422-L464), [pathnode.c#STD_FUZZ_FACTOR](../../../../raw/postgres-12/src/backend/optimizer/util/pathnode.c#L48-L52), [pathnode.c#add_path-costs-better](../../../../raw/postgres-12/src/backend/optimizer/util/pathnode.c#L556-L579)). Because a GIN path is only ever a bitmap input, the decisive filter is usually `choose_bitmap_and()`: it first keeps only the cheapest path in each group of paths using identical clause sets, sorts the survivors by index access cost, and then adds a further index to the AND group only when `bitmap_and_cost_est()` reports a lower total ([indxpath.c#choose_bitmap_and](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1368-L1385), [indxpath.c#choose_bitmap_and-accept-reject](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1515-L1577)). A GIN index whose own scan cost exceeds the saving it produces is therefore dropped from the bitmap tree entirely, and its predicate reappears as a `Filter` above the surviving B-tree bitmap scan.

### A bloated GIN index loses to a B-tree

This is the case that connects the follow-up back to this page's subject. GIN bloat in the `fastupdate` pending list is charged to the planner in full and immediately, because `nPendingPages` is the one metapage counter `gincostestimate()` treats as current ([selfuncs.c#gincostestimate-stats](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6700-L6730), [selfuncs.c#gincostestimate-pending](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6864-L6873)). The manual states the runtime consequence: "searches must scan the list of pending entries in addition to searching the regular index, and so a large list of pending entries will slow searches significantly" ([gin.sgml#fast-update](../../../../raw/postgres-12/doc/src/sgml/gin.sgml#L491-L499)).

Measured at the pin on a 200,000-row table with a `tsvector` GIN index (`fastupdate = on`) and a B-tree index on an `int` category column, querying `tsv @@ to_tsquery('simple','zebracorn') AND cat = 7`:

| Pending pages (`pgstatginindex`) | GIN index-scan cost | Plan chosen | Plan total cost |
|---:|---:|---|---:|
| 0 | `12.45` | `BitmapAnd` of GIN and B-tree | `56.64` |
| 1177 | `4720.55` | B-tree bitmap scan only; `tsv @@ …` demoted to `Filter` | `4712.42` |
| 0 after `gin_clean_pending_list()` | `16.55` | `BitmapAnd` of GIN and B-tree | `82.10` |

The arithmetic is exactly the pending-page charge. In a second, tighter run, `pgstatginindex` reported 393 pending pages and the GIN index-scan cost was `1588.55` at `random_page_cost = 4` and `397.55` at `random_page_cost = 1`; `(1588.55 - 397.55) / 3 = 397` pages charged, that is 393 pending pages plus 4 entry and data pages. `gin_clean_pending_list()` then returned `393`, matching `pgstatginindex` exactly, and the GIN cost fell back to `16.55` — a 96-fold swing driven purely by pending-list pages ([pgstatindex.c#pgstatginindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L480-L497), [pgstatindex.c#pgstatginindex_internal](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L509-L575), [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L1027-L1074)).

Note the direction of the sign: unlike the B-tree page-count penalty in section 1, this is not a mild pro-rata increase. Every pending page is added to **startup** cost for every scan, so it also disqualifies the GIN path from cheap-startup plans such as `LIMIT`.

### Stale GIN metapage statistics

`gincostestimate()` trusts the last-`VACUUM` counters only when the index has not grown too much. It requires `nTotalPages <= numPages`, `nTotalPages > numPages / 4`, `nEntryPages > 0`, and `nEntries > 0`; otherwise it invents statistics from the live block count — 90% entry pages, the rest data pages, and 100 entries per entry page — after clamping the page count to at least 10 ([selfuncs.c#gincostestimate-scale-or-invent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6732-L6772)). The source comment names the 4X cutoff and calls the 100-entries figure "rather bogus".

Two details matter operationally. First, `numPages` comes from `index->pages`, which `get_relation_info()` reads live with `RelationGetNumberOfBlocks()`, so index growth reaches the cost model before `ANALYZE` runs, while `index->tuples` stays at the stale `pg_class.reltuples` ([plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L407)). Second, `numPendingPages` is discarded when it is not smaller than `numPages`, which is a sanity guard, not a cost reduction ([selfuncs.c#gincostestimate-pending-guard](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6722-L6730)).

Measured at the pin with `fastupdate = off`, so growth landed in real entry and data pages: an `int[]` GIN index of 27 pages cost `13.55` for `arr @> ARRAY[5]`; after growing to 4127 pages (153-fold, far past the 4X cutoff) with only `ANALYZE` run, the invented statistics produced `17.58`; after `VACUUM ANALYZE` refreshed the metapage counters, the same query cost `17.89`. In this fixture the fallback under-estimated by 1.7%, so the 4X branch is a source of imprecision rather than a reliable penalty.

### The keyless GIN path on a partial index

GIN sets `amoptionalkey = true`, so a GIN path can be built with no index clause at all when the index's partial predicate is proven, which is the one case where `build_index_paths()` reaches its path-generation gate through `useful_predicate` ([ginutil.c#ginhandler](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L41-L56), [indxpath.c#build_index_paths-amoptionalkey](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L964-L974), [indxpath.c#build_index_paths-path-gate](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1030-L1038)). `gincostestimate()` prices that as a full index scan, setting `exactEntries = searchEntries = numEntries` when `indexQuals == NIL` ([selfuncs.c#gincostestimate-fullscan](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6855-L6862)).

Such a path is executable in v12: `ginNewScanKey()` generates a `GIN_SEARCH_MODE_EVERYTHING` scan key when there are no regular keys, and errors only for a pre-9.1 index whose `ginVersion < 1` ([ginscan.c#ginNewScanKey-everything](../../../../raw/postgres-12/src/backend/access/gin/ginscan.c#L376-L387), [ginscan.c#ginNewScanKey-old-version](../../../../raw/postgres-12/src/backend/access/gin/ginscan.c#L389-L405), [gin.h#GIN_SEARCH_MODE](../../../../raw/postgres-12/src/include/access/gin.h#L32-L36)). Fresh indexes are written at `GIN_CURRENT_VERSION` 2, so that error path is unreachable without an upgraded pre-9.1 index ([ginblock.h:102](../../../../raw/postgres-12/src/include/access/ginblock.h#L102)).

At the pin, a two-page partial GIN index `ON t_part USING gin (arr) WHERE flag` with 186 distinct keys produced exactly this plan for `SELECT id FROM t_part WHERE flag`: a `Bitmap Index Scan` with no `Index Cond`, costing `748.33` at `random_page_cost = 4` and `187.33` at `random_page_cost = 1`, i.e. `(748.33 - 187.33) / 3 = 187` pages charged — one entry-page probe per index entry plus one data page. It still beat the `1834.00` sequential scan and returned the correct 100 rows, so a keyless GIN path is not automatically discarded. The docs warn about the general shape: a full-index scan "is much slower than the other two choices, since it requires scanning essentially the entire index" ([gin.sgml#extractQuery-searchmode](../../../../raw/postgres-12/doc/src/sgml/gin.sgml#L215-L222)).

### Jobs no GIN index can be created for

For some requirements the planner never gets a choice, because `DefineIndex()` rejects the GIN index at DDL time. All four errors reproduced verbatim at the pin:

| Statement | v12 error | Source |
|---|---|---|
| `CREATE UNIQUE INDEX … USING gin (b)` | `access method "gin" does not support unique indexes` | [indexcmds.c#amcanunique](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L751-L755) |
| `CREATE INDEX … USING gin (b) INCLUDE (c)` | `access method "gin" does not support included columns` | [indexcmds.c#amcaninclude](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L756-L760) |
| `ALTER TABLE … ADD EXCLUDE USING gin (b WITH &&)` | `access method "gin" does not support exclusion constraints` | [indexcmds.c#amgettuple-exclusion](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L766-L770) |
| `CREATE INDEX … USING gin (b DESC)` | `access method "gin" does not support ASC/DESC options` | [indexcmds.c#amcanorder-ordering](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1818-L1832) |

`ADD PRIMARY KEY` therefore always builds a B-tree; at the pin the resulting `t_err_pkey` had `amname = btree`, `indisunique = t`, `indisprimary = t`. The manual states the same restrictions: "Currently, only B-tree indexes can be declared unique", "For index methods that support ordered scans (currently, only B-tree)", and, for exclusion constraints, "The access method must support `amgettuple` … at present this means GIN cannot be used" ([indices.sgml#unique-indexes](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L643-L653), [create_index.sgml#ordered-scans](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L692-L705), [create_table.sgml#exclude-amgettuple](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L988-L996)).

### Where GIN still wins

The mirror image is just as important: for the operators GIN's opfamily does carry, the B-tree is not a candidate at all, so nothing about the cost comparison above applies. At the pin, `WHERE jb @> '{"k": 42}'::jsonb` used the `jsonb_ops` GIN index at index cost `22.25`, while the table carrying only a B-tree index on `jb` fell back to a parallel sequential scan costing `5685.50`. And the pending-list case above shows GIN reducing a `4696.42` B-tree-only plan to `56.64` when its pending list is clean.

The `btree_gin` documentation names the one case where GIN can beat two separate indexes on mixed predicates: "for queries that test both a GIN-indexable column and a B-tree-indexable column, it might be more efficient to create a multicolumn GIN index that uses one of these operator classes than to create two separate indexes that would have to be combined via bitmap ANDing" ([btree-gin.sgml#caveats](../../../../raw/postgres-12/doc/src/sgml/btree-gin.sgml#L24-L33)). That claim is about avoiding the `BitmapAnd`, not about beating a B-tree on a single column, and this page did not test it.

### Exact-pin measurements

All numbers below come from an isolated PostgreSQL 12.2 server built from this page's pinned checkout, at default cost GUCs (`random_page_cost = 4`, `seq_page_cost = 1`, `cpu_tuple_cost = 0.01`, `cpu_index_tuple_cost = 0.005`, `cpu_operator_cost = 0.0025`, `effective_cache_size = 4GB`, `block_size = 8192`). Cost figures are `EXPLAIN` index-side costs and plan totals.

The seven `n` rows ran against one table, `t_both` (300,000 rows, 3093 heap pages, `n = id % 10000` with six NULLs), carrying both a `btree_gin` GIN index and a B-tree index on `n`; each alternative was isolated by dropping the other index inside a rolled-back transaction, so both were priced from identical statistics. The two `jb` rows compare two sibling tables with byte-identical content, one holding only a `jsonb_ops` GIN index and the other only a B-tree index on `jb`; both were separately analyzed and produced the same 30-row estimate.

| Query | GIN-only plan | B-tree-only plan | Chosen when both indexes exist |
|---|---|---|---|
| `n = 42` | `Bitmap Index Scan` `12.22`, total `123.74` | `Bitmap Index Scan` `4.65`, total `116.17` | B-tree |
| `n BETWEEN 100 AND 120` | `50.68`, total `1674.12` | `15.10`, total `1638.55` | B-tree |
| `n < 20` | `28.69`, total `1578.44` | `13.11`, total `1562.86` | B-tree |
| `n IN (1,2,3)` | `28.67`, total `340.64` | `13.94`, total `325.91` | B-tree |
| `ORDER BY n LIMIT 10` | no index path: `Sort` over `Parallel Seq Scan`, total `8045.40` | `Index Scan`, total `1.09` | B-tree, 7381x cheaper |
| `SELECT n WHERE n = 42` | `Bitmap Heap Scan`, total `123.74` | `Index Only Scan`, total `4.95` | B-tree, 25x cheaper |
| `n IS NULL` | no index path: `Parallel Seq Scan`, total `5343.10` | `Index Scan`, total `8.43` | B-tree, 634x cheaper |
| `jb = '{"k": 42}'::jsonb` | no index path: `Parallel Seq Scan`, total `5658.50` | `Bitmap Index Scan` `4.65`, total `116.17` | not co-located; only the B-tree had a path |
| `jb @> '{"k": 42}'::jsonb` | `Bitmap Index Scan` `22.25`, total `911.80` | no index path: `Parallel Seq Scan`, total `5685.50` | not co-located; only GIN had a path |

The four "no index path" rows are gate-1 and gate-2 rejections rather than cost losses. Re-running the three GIN ones with `enable_seqscan = off` produced sequential scans priced at `10000000000.00`, that is `disable_cost` added to the only surviving path, which proves no GIN path existed to compare against ([costsize.c:120](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L120), [costsize.c:231](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L231)).

On the `n` column the GIN index was the *smaller* of the two — 279 pages against the B-tree's 826, because a `btree_gin` index stores one entry per distinct value and only 10,000 distinct values existed. Smaller and still more expensive is the point: the loss comes from GIN's page charges all being `random_page_cost`, not from GIN being bloated.

Reproducing this requires `contrib/btree_gin`, since `int4` has no core GIN operator class. The fixtures used `CREATE EXTENSION btree_gin`, `pg_trgm`, and `pgstattuple`, all built from the pinned tree.

```sql
-- Which index would serve this predicate, and at what cost?
-- Session-scoped guards; both are PGC_USERSET.
SET /* wiki_gin_vs_btree_guards */ statement_timeout = '60s';
SET /* wiki_gin_vs_btree_guards */ lock_timeout = '5s';

-- 1. Do the candidate GIN and B-tree indexes exist, and what does the AM allow?
SELECT /* wiki_gin_vs_btree_candidates */
       c.relname            AS index_name,
       am.amname,
       c.relpages,
       pg_relation_size(c.oid) AS bytes,
       pg_index_has_property(i.indexrelid, 'index_scan')        AS index_scan,
       pg_index_has_property(i.indexrelid, 'bitmap_scan')       AS bitmap_scan,
       pg_index_column_has_property(i.indexrelid, 1, 'orderable')    AS orderable,
       pg_index_column_has_property(i.indexrelid, 1, 'returnable')   AS returnable,
       pg_index_column_has_property(i.indexrelid, 1, 'search_array') AS search_array,
       pg_index_column_has_property(i.indexrelid, 1, 'search_nulls') AS search_nulls
FROM pg_index i
JOIN pg_class c  ON c.oid = i.indexrelid
JOIN pg_am    am ON am.oid = c.relam
WHERE i.indrelid = 'my_table'::regclass
ORDER BY am.amname, c.relname;

-- 2. Is the operator even in the index's operator family?
--    An operator absent here can never produce an index path for that clause.
--    DISTINCT collapses the one pg_amop row per left/right type pair.
SELECT DISTINCT /* wiki_gin_vs_btree_opfamily */
       c.relname AS index_name,
       am.amname,
       op.oprname,
       ao.amopstrategy
FROM pg_index i
JOIN pg_class c   ON c.oid = i.indexrelid
JOIN pg_am    am  ON am.oid = c.relam
JOIN pg_opclass oc ON oc.oid = i.indclass[0]
JOIN pg_amop  ao  ON ao.amopfamily = oc.opcfamily
JOIN pg_operator op ON op.oid = ao.amopopr
WHERE i.indrelid = 'my_table'::regclass
ORDER BY am.amname, c.relname, ao.amopstrategy;

-- 3. How much of the GIN cost is pending-list backlog?
--    Requires CREATE EXTENSION pgstattuple.
SELECT /* wiki_gin_pending_backlog */
       version, pending_pages, pending_tuples,
       pending_pages * current_setting('random_page_cost')::float8
         AS pending_startup_cost
FROM pgstatginindex('my_gin_index');
```

`pg_index_has_property`, `pg_index_column_has_property`, and `pg_indexam_has_property` are core functions, so query 1 needs no extension ([amutils.c#property-functions](../../../../raw/postgres-12/src/backend/utils/adt/amutils.c#L411-L447)). All three blocks above ran verbatim at the pin against a fixture literally named `my_table` with indexes `my_gin_index` (GIN on an `int[]` column, `fastupdate = on`) and `my_btree_index`:

- Query 1 returned `index_scan = f`, `bitmap_scan = t`, `orderable = f`, `returnable = f`, `search_array = f`, `search_nulls = f` for the GIN index and `t` for all six on the B-tree, matching `amutils.out` ([amutils.out#column-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L96-L108), [amutils.out#index-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L122-L129)).
- Query 2 returned exactly `&&`, `@>`, `<@`, `=` at strategies 1 to 4 for the GIN index and `<`, `<=`, `=`, `>=`, `>` at strategies 1 to 5 for the B-tree, reproducing the `pg_amop.dat` memberships from a live catalog ([pg_amop.dat#gin-array_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1211-L1223)).
- Query 3 reported `pending_pages = 50`, `pending_tuples = 20000`, and `pending_startup_cost = 200`. The GIN index-scan cost was `217.51` at that moment and `17.51` immediately after `gin_clean_pending_list()` returned `50` — a `200.00` reduction, exactly the predicted charge.

The same relationship held at larger scale in the pending-list fixture: 393 pending pages times `4.0` is `1572.00`, and the observed GIN cost moved from `16.55` to `1588.55`.

### Settings that move the boundary

| Setting | v12 default | Effect on the GIN-versus-B-tree decision | Apply scope |
|---|---|---|---|
| `random_page_cost` | `4` | Scales every GIN page charge, including pending pages, and the B-tree's smaller page share; lowering it shrinks GIN's disadvantage proportionally | `PGC_USERSET` (`user`): session or transaction, no reload or restart ([guc.c#random_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3207-L3227), [config.sgml#random-page-cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4713-L4770)) |
| `effective_cache_size` | `4GB` | Feeds `index_pages_fetched()`, which GIN uses only for repeated scans (`loop_count > 1` or `arrayScans > 1`) | `PGC_USERSET`: session or transaction ([guc.c#effective_cache_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3117), [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L787-L878)) |
| `enable_bitmapscan` | `on` | Turning it off adds `disable_cost` to every bitmap heap scan, which is the only plan shape GIN can appear in | `PGC_USERSET`: session or transaction ([guc.c#enable-flags](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L883-L922), [costsize.c#cost_bitmap_heap_scan](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L939-L1034)) |
| `enable_indexscan` | `on` | Turning it off penalizes plain `Index Scan` paths, which only the B-tree has; it does not disable the bitmap path | `PGC_USERSET`: session or transaction ([guc.c#enable-flags](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L883-L922), [costsize.c#cost_index-enable-indexscan](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L533-L535)) |
| `enable_indexonlyscan` | `on` | Turning it off makes `check_index_only()` return false, removing the B-tree's index-only advantage | `PGC_USERSET`: session or transaction ([guc.c#enable-flags](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L883-L922), [indxpath.c#check_index_only](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1895-L1907)) |
| `gin_pending_list_limit` | `4MB` | Caps how large the pending list grows before a foreground cleanup, so it bounds the worst-case GIN startup charge; overridable per index as a storage parameter | `PGC_USERSET`: session or transaction ([guc.c#gin_pending_list_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3175-L3184), [config.sgml#gin-pending-list-limit](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7972-L7993), [create_index.sgml#gin-storage-parameters](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L438-L487)) |
| `fastupdate` (index storage parameter) | `on` | Turning it off stops new pending pages; it does not flush existing ones, so pair it with `VACUUM` or `gin_clean_pending_list()` | `ALTER INDEX … SET (fastupdate = off)`: DDL, no restart or reload ([create_index.sgml#fastupdate](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L443-L469), [ginutil.c#ginoptions](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L603-L629)) |
| `gin_fuzzy_search_limit` | `0` | Not a planner input. It caps GIN results at execution time in `ginget.c`, so it changes runtime output, not path choice | `PGC_USERSET`: session or transaction ([guc.c#gin_fuzzy_search_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3096-L3105), [ginget.c#GinFuzzySearchLimit](../../../../raw/postgres-12/src/backend/access/gin/ginget.c#L593-L618)) |

None of these eight needs a restart or a configuration reload; all seven GUCs are `PGC_USERSET` and `fastupdate` is index DDL.

### Key data structures

- `IndexOptInfo` carries everything the planner knows about a candidate index: `pages`, `tuples`, `tree_height`, `opfamily`, `sortopfamily`, `canreturn`, `indpred`, `predOK`, the copied AM capability flags, and the `amcostestimate` function pointer ([pathnodes.h#IndexOptInfo](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L781-L835)).
- `GinQualCounts` holds the per-clause tallies `gincostestimate()` builds: `haveFullScan`, `partialEntries`, `exactEntries`, `searchEntries`, and `arrayScans` ([selfuncs.c#GinQualCounts](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6388-L6395)).
- `GinStatsData` is the metapage snapshot: `nPendingPages`, `nTotalPages`, `nEntryPages`, `nDataPages`, `nEntries`, and `ginVersion` ([gin.h#GinStatsData](../../../../raw/postgres-12/src/include/access/gin.h#L41-L49), [ginutil.c#ginGetStats](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L631-L657)).
- `IndexClause` is the per-clause match record produced at gate 1, including its `lossy` flag and `indexcol` ([pathnodes.h#IndexClause](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L1216-L1224)).

### Caller and callee boundary

The decision path for a base relation runs:

```text
set_plain_rel_pathlist / set_rel_pathlist
  -> create_index_paths(root, rel)                      indxpath.c:232
     -> match_restriction_clauses_to_index              gate 1
        -> match_clause_to_indexcol                     indxpath.c:2380
           -> match_opclause_to_indexcol                indxpath.c:2546  (op_in_opfamily)
              -> get_index_clause_from_support          indxpath.c:2712  (support-function rewrite)
     -> get_index_paths(root, rel, index, ..., &bitindexpaths)
        -> build_index_paths                            gate 2 (scantype, pathkeys, index-only)
           -> create_index_path -> cost_index            costsize.c:476
              -> index->amcostestimate                  gincostestimate / btcostestimate
        -> add_path (plain paths only, amhasgettuple)   pathnode.c:423
     -> choose_bitmap_and(root, rel, bitindexpaths)     gate 3 for bitmap inputs
     -> create_bitmap_heap_path -> cost_bitmap_heap_scan costsize.c:940
     -> add_path
```

Each step is cited above; the two entry points are [indxpath.c#create_index_paths](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L232-L346) and [costsize.c#cost_index](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L476-L548). `cost_bitmap_tree_node()` adds `0.1 * cpu_operator_cost` per retrieved tuple so a bitmap scan never looks identical to a single-tuple index scan, and `cost_bitmap_heap_scan()` interpolates between `random_page_cost` and `seq_page_cost` by `sqrt(pages_fetched / T)` and charges the full restriction qual per fetched tuple because it assumes the bitmap may be lossy ([costsize.c#cost_bitmap_tree_node](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L1040-L1055), [costsize.c#cost_bitmap_heap_scan](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L983-L1012)).

Two upstream boundaries in `get_relation_info()` precede all of this: an index that is not `indisvalid`, or a partitioned index, is dropped from `rel->indexlist` before any matching or costing happens, so an invalid GIN index left behind by a failed build is invisible to the planner ([plancat.c#get_relation_info-skip](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L198-L234)).

### Build, generated-header, and extension boundary

- The GIN and B-tree handlers are reached through `pg_am`, whose bootstrap data is compiled into generated catalog headers; `get_relation_info()`'s ordering special case tests `info->relam == BTREE_AM_OID`, a symbol from the generated `pg_am_d.h` ([plancat.c#get_relation_info-sortopfamily](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L281-L320), [pg_am.dat#gin-btree](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L29)).
- GIN operator-class memberships for core types are bootstrap `.dat` data, not SQL, so adding or removing a GIN operator changes generated catalog headers and requires a rebuild plus `initdb` ([pg_amop.dat#gin-jsonb_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1458-L1476), [pg_opclass.dat#gin](../../../../raw/postgres-12/src/include/catalog/pg_opclass.dat#L243-L247)).
- `contrib/btree_gin` is in the unconditional `SUBDIRS` list, so `make -C contrib` builds it, but it still has to be installed and enabled with `CREATE EXTENSION btree_gin` before `int4` gets a GIN operator class ([contrib/Makefile:13](../../../../raw/postgres-12/contrib/Makefile#L13), [btree_gin.control](../../../../raw/postgres-12/contrib/btree_gin/btree_gin.control#L1-L5)).
- `btree_gin`'s range support is a partial-match scan, not a B-tree descent: `gin_btree_extract_query()` sets `partialmatch` for `<`, `<=`, `>=`, and `>`, and for `<`/`<=` starts at `leftmostvalue()` and walks forward ([btree_gin.c#gin_btree_extract_query](../../../../raw/postgres-12/contrib/btree_gin/btree_gin.c#L47-L101)). `gincostestimate()` prices each partial-match key as 100 entries and charges a proportional share of every entry and data page as startup cost, which is why the measured `BETWEEN` gap (`50.68` versus `15.10`) is wider than the equality gap ([selfuncs.c#gincost_pattern-partial](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6472-L6496), [selfuncs.c#gincostestimate-entrypages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6884-L6901)).
- `btree_gin` supplies GIN support functions 1 through 5 only, with no `triconsistent` (support function 6), so its opclasses cannot use GIN fast scan ([btree_gin--1.0.sql#int4_ops](../../../../raw/postgres-12/contrib/btree_gin/btree_gin--1.0.sql#L56-L69), [gin.h#GINNProcs](../../../../raw/postgres-12/src/include/access/gin.h#L22-L28)).
- `pgstatginindex()` lives in `contrib/pgstattuple`, so the pending-page measurement above needs that extension; `gin_clean_pending_list()` is core ([pgstatindex.c#pgstatginindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L480-L497), [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L1027-L1074)).

### Tests and explicit test absence

No PostgreSQL 12 regression test, core or contrib, compares a GIN plan with a B-tree plan for the same query. What exists:

| Coverage | Status | Evidence |
|---|---|---|
| GIN AM storage, pending list, VACUUM | Present, but with no `EXPLAIN`, no `enable_*scan`, and no `SELECT … WHERE` at all | [gin.sql#whole-test](../../../../raw/postgres-12/src/test/regress/sql/gin.sql#L1-L36), [serial_schedule:107](../../../../raw/postgres-12/src/test/regress/serial_schedule#L107), [parallel_schedule:76](../../../../raw/postgres-12/src/test/regress/parallel_schedule#L76) |
| GIN's planner-relevant AM properties | Present, asserted declaratively rather than through plans | [amutils.out#column-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L96-L108), [amutils.out#index-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L122-L129), [serial_schedule:139](../../../../raw/postgres-12/src/test/regress/serial_schedule#L139) |
| GIN plan shape is always a bitmap scan | Present, but the GUCs are set to force it, removing planner choice | [create_index.sql#gin-forced-bitmap](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L271-L279), [create_index.out#gin-bitmap-plan](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L680-L690) |
| A GIN index being rejected in favour of a `Seq Scan` | Present exactly once, and caused by boolean clause simplification, not by cost | [bool.out#gin-seqscan](../../../../raw/postgres-12/contrib/btree_gin/expected/bool.out#L88-L96) |
| `btree_gin` correctness for all five strategies | Present, on 3-to-7-row tables with `enable_seqscan=off` and no B-tree index anywhere | [int4.sql#five-strategies](../../../../raw/postgres-12/contrib/btree_gin/sql/int4.sql#L1-L15) |
| GIN page-level predicate locking | Present, forces GIN use rather than testing planner choice | [predicate-gin.spec#setup](../../../../raw/postgres-12/src/test/isolation/specs/predicate-gin.spec#L1-L20) |
| `gincostestimate()` behaviour or any GIN cost number | **Absent.** Every GIN `EXPLAIN` in the tree uses `COSTS OFF`, and no test references `gincostestimate` | [selfuncs.c#gincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6672-L6979) |
| GIN with `ORDER BY` served from the index, `IS NULL`, or an index-only scan | **Absent.** GIN `ORDER BY` queries always show a separate `Sort`; the KNN `ORDER BY` cases are EXPLAINed for GiST only | [create_index.out#gin-bitmap-plan](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L680-L690) |
| The `ginNewScanKey()` "old GIN indexes" error | **Absent, and unreachable in-tree** because fresh indexes are `GIN_CURRENT_VERSION` 2 | [ginscan.c#ginNewScanKey-old-version](../../../../raw/postgres-12/src/backend/access/gin/ginscan.c#L389-L405), [ginblock.h:102](../../../../raw/postgres-12/src/include/access/ginblock.h#L102) |

## Open Questions

- PostgreSQL 12 does not define a universal `avg_leaf_density` or `leaf_fragmentation` threshold for `REINDEX`; the proposed candidate bands above are operational triage values, while the docs describe conditions and tradeoffs rather than a percentage cutoff ([maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L861-L895), [ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L49-L55)).
- `leaf_fragmentation` does not encode jump distance, run length, operating-system read-ahead behavior, or cache residency, so it cannot by itself predict elapsed time ([pgstatindex.c#fragmentation-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L300-L307), [config.sgml#random-page-cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4713-L4765)).
- `EXPLAIN (ANALYZE, BUFFERS)` can show node-level shared/local/temp buffer hits and reads, but the v12 output path does not split those counters into index versus heap pages or sequential versus nonsequential reads ([explain.c#plan-buffer-usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L1864-L1866), [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867-L2978)).
- The GIN-versus-B-tree cost comparisons in the follow-up are single-fixture measurements at default cost GUCs on one 300,000-row table with 10,000 distinct values, six NULLs, and a 20-byte payload. The ordering of `12.22` versus `4.65` follows from the cost formulas, but the *size* of the gap depends on selectivity, distinct-value count, index page counts, and `random_page_cost`; this page did not sweep those dimensions ([selfuncs.c#gincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6672-L6979), [selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815)).
- The 4X stale-statistics fallback under-estimated by only 1.7% in the measured fixture (`17.58` invented versus `17.89` after `VACUUM`). The source comment calls the invented 100-entries-per-page figure "rather bogus", so the error is workload-dependent and this page has no bound for it ([selfuncs.c#gincostestimate-scale-or-invent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6732-L6772)).
- The `btree_gin` documentation claims a multicolumn GIN index can beat two separate indexes combined via bitmap ANDing for mixed GIN-plus-B-tree predicates. That claim is not tested here ([btree-gin.sgml#caveats](../../../../raw/postgres-12/doc/src/sgml/btree-gin.sgml#L24-L33)).
- `gincostestimate()` has no regression coverage in v12, and every GIN `EXPLAIN` in the tree uses `COSTS OFF`, so upstream asserts none of the cost behaviour described in the follow-up ([selfuncs.c#gincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6672-L6979), [gin.sql#whole-test](../../../../raw/postgres-12/src/test/regress/sql/gin.sql#L1-L36)).
- `gincostestimate()` sets `*indexCorrelation = 0.0` unconditionally, so a GIN path never receives the index-order correlation credit that `cost_index()` gives a well-correlated B-tree. This page did not measure how much of the observed gap that accounts for on wide range scans ([selfuncs.c#gincostestimate-correlation](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6794-L6797), [costsize.c#cost_index](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L476-L548)).

## Related Pages

- [v12/index](../../index.md)
- [Impact of B-Tree Leaf Density (60% vs 90%) on Index Scan Queries in PostgreSQL 12 (unverified)](../indexing/leaf-density-60-vs-90-query-impact.md)
- [B-Tree Leaf Density vs Fragmentation Impact on Index Scan I/O in PostgreSQL 12 (unverified)](../indexing/leaf-density-vs-fragmentation-index-scan-io.md)
- [How pgstatindex Calculates B-Tree Index Statistics in PostgreSQL 12 (unverified)](../indexing/how-pgstatindex-calculates-information.md)
- [How NULL Values Are Handled in PostgreSQL 12 Indexes (unverified)](../indexing/null-values-in-indexes.md)
- [Query Planner Statistics Sources in PostgreSQL 12 (unverified)](query-planner-statistics-sources.md)
- [EXPLAIN ANALYZE BUFFERS Output in PostgreSQL 12 (unverified)](../observability/explain-analyze-buffers-output.md)
- [versions](../../../versions.md)

## Evidence Map

| Claim | Evidence |
|---|---|
| Planner B-tree bloat penalties are page-count and height based, not direct `pgstatindex` metrics | [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L417), [selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5765-L5815), [selfuncs.c#btcostestimate-bloat-charge](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6104-L6116) |
| The planner calls each index's `amcostestimate`; the page-count penalty is shared by B-tree, hash, GiST, and SP-GiST via `genericcostestimate()`; GIN and BRIN use separate cost models; the measured tree-height charge is B-tree-only, GiST and SP-GiST reuse the descent formula with a height estimated as `log100(index->pages)`, and hash adds no descent charge | [nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L134), [plancat.c#amcostestimate](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L276-L277), [costsize.c#cost_index-amcostestimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L544-L548), [selfuncs.c#btcostestimate-genericcost](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6084), [selfuncs.c#gincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6672), [selfuncs.c#brincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6985), [plancat.c#get_relation_info-tree-height](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L409-L417), [selfuncs.c#gistcostestimate-descent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6283-L6317), [selfuncs.c#spgcostestimate-descent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6340-L6374), [selfuncs.c#hashcostestimate-no-descent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6237-L6260) |
| B-tree page count is read from the current index relation for ordinary indexes and from `estimate_rel_size()` for partial indexes | [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L407), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L1026) |
| Planner B-tree height uses `_bt_getrootheight()` / `btm_fastlevel`; `pgstatindex.tree_level` reports `btm_level` | [nbtpage.c#_bt_getrootheight](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L575-L626), [nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L90-L110), [pgstatindex.c#metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L239-L249) |
| `RelationGetNumberOfBlocks()` obtains the main-fork length through storage-manager segment size checks, not a B-tree page scan | [bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-12/src/include/storage/bufmgr.h#L188-L199), [bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2791-L2811), [smgr.c#smgrnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L630-L640), [md.c#mdnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L698-L755), [md.c#_mdnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L1229-L1242), [fd.c#FileSize](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L2039-L2053) |
| `pgstatindex()` computes density, fragmentation, and page category diagnostics outside planner costing | [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L216-L365) |
| A reindex-candidate heuristic can use `avg_leaf_density` and `leaf_fragmentation`, but PostgreSQL 12 defines no source-level cutoff; ordinary and partial indexes also differ in how `get_relation_info()` estimates tuples for page-count costing | [pgstattuple--1.4.sql#pgstatindex-regclass](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L62-L73), [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L216-L365), [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L861-L895), [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L407), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L1026) |
| B-tree range scans walk sibling-linked leaf pages through `_bt_next()`, `_bt_steppage()`, `_bt_readnextpage()`, and `_bt_getbuf()` | [nbtree.c#btgettuple](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L213-L284), [nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1334-L1381), [nbtsearch.c#_bt_steppage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1619-L1724), [nbtsearch.c#forward-readnextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1727-L1800), [nbtpage.c#_bt_getbuf](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L748-L820) |
| B-tree bloat and physical adjacency are documented maintenance concerns | [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L861-L889), [ref/reindex.sgml#bloat](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L49-L55) |
| Fillfactor shapes initial B-tree density and split behavior | [create_index.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L369-L390), [nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L159-L171) |
| Existing tests do not compare planner decisions by density or fragmentation level | [pgstattuple.sql#pgstatindex-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L18-L113), [serial_schedule#btree_index](../../../../raw/postgres-12/src/test/regress/serial_schedule#L100), [parallel_schedule#btree_index](../../../../raw/postgres-12/src/test/regress/parallel_schedule#L71), [btree_index.sql#tall-fillfactor](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L110-L123), [btree_index.sql#page-recycling](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L147-L162) |
| A GIN index is dropped at gate 1 when the query operator is not in its operator family, unless a planner support function rewrites the clause | [indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2380-L2447), [indxpath.c#match_opclause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2546-L2663), [indxpath.c#get_index_clause_from_support](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2717-L2774), [indices.sgml#other-operators](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L454-L457) |
| Core GIN operator families carry no B-tree comparison operators; `contrib/btree_gin` adds strategies 1-5 for scalar types | [pg_amop.dat#gin-array_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1211-L1223), [pg_amop.dat#gin-tsvector_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1269-L1275), [pg_amop.dat#gin-jsonb_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1458-L1476), [pg_amop.dat#btree-hash-jsonb_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1436-L1456), [btree_gin--1.0.sql#int4_ops](../../../../raw/postgres-12/contrib/btree_gin/btree_gin--1.0.sql#L56-L69) |
| GIN's AM flags make a plain index scan, ordered output, index-only scan, `IS NULL`, native SAOP, and parallel index scan impossible, not merely expensive | [ginutil.c#ginhandler](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L36-L81), [nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L106-L151), [plancat.c#get_relation_info-am-flags](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L266-L279), [indxpath.c#get_index_paths-submit](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L789-L800), [indxpath.c#build_index_paths-pathkeys](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L985-L1028), [indxpath.c#check_index_only](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1895-L1907), [indexam.c#index_can_return](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L714-L731), [amutils.out#column-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L96-L108), [amutils.out#index-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L122-L129) |
| Documentation states the same three plan-shape limits: only B-tree produces sorted output, GIN cannot do index-only scans, and `amgetbitmap` supports neither ordering nor index data retrieval | [indices.sgml#ordering](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L479-L487), [indices.sgml#index-only-scans](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L1044-L1056), [indexam.sgml#amgetbitmap](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L862-L881), [indexam.sgml#amcanreturn](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L373-L386) |
| `gincostestimate()` charges `random_page_cost` for pending pages, entry pages, and data pages, and adds no descent charge | [selfuncs.c#gincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6672-L6979), [selfuncs.c#gincostestimate-pending](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6864-L6873), [selfuncs.c#gincostestimate-startup](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6922-L6926), [selfuncs.c#gincostestimate-qualcost](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6968-L6979) |
| A pending list of 393 pages added exactly `393 * random_page_cost` to GIN index cost, confirmed against `pgstatginindex` and `gin_clean_pending_list()` | [selfuncs.c#gincostestimate-pending](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6864-L6873), [pgstatindex.c#pgstatginindex_internal](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L509-L575), [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L1027-L1074), [gin.sgml#fast-update](../../../../raw/postgres-12/doc/src/sgml/gin.sgml#L491-L499) |
| The losing GIN bitmap input is dropped by `choose_bitmap_and()` / `add_path()` fuzzy dominance, and its predicate reappears as a `Filter` | [indxpath.c#choose_bitmap_and](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1368-L1385), [indxpath.c#choose_bitmap_and-accept-reject](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1515-L1577), [pathnode.c#add_path](../../../../raw/postgres-12/src/backend/optimizer/util/pathnode.c#L422-L464), [pathnode.c#STD_FUZZ_FACTOR](../../../../raw/postgres-12/src/backend/optimizer/util/pathnode.c#L48-L52) |
| Stale metapage counters are scaled only within 4X growth; beyond that `gincostestimate()` invents 90% entry pages and 100 entries per entry page | [selfuncs.c#gincostestimate-scale-or-invent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6732-L6772), [ginutil.c#ginGetStats](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L631-L657) |
| A partial GIN index can yield a keyless full-index bitmap path that is priced as `numEntries` entry probes and is executable at `GIN_CURRENT_VERSION` 2 | [indxpath.c#build_index_paths-amoptionalkey](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L964-L974), [selfuncs.c#gincostestimate-fullscan](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6855-L6862), [ginscan.c#ginNewScanKey-everything](../../../../raw/postgres-12/src/backend/access/gin/ginscan.c#L376-L387), [ginblock.h:102](../../../../raw/postgres-12/src/include/access/ginblock.h#L102) |
| `CREATE INDEX` rejects a GIN index for `UNIQUE`, `INCLUDE`, `ASC`/`DESC`, and exclusion constraints before the planner is involved | [indexcmds.c#amcanunique](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L751-L755), [indexcmds.c#amcaninclude](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L756-L760), [indexcmds.c#amgettuple-exclusion](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L766-L770), [indexcmds.c#amcanorder-ordering](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1818-L1832), [indices.sgml#unique-indexes](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L643-L653), [create_table.sgml#exclude-amgettuple](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L988-L996) |
| `btree_gin` range predicates use GIN partial match, priced at 100 entries per key plus a proportional page share as startup cost | [btree_gin.c#gin_btree_extract_query](../../../../raw/postgres-12/contrib/btree_gin/btree_gin.c#L47-L101), [selfuncs.c#gincost_pattern-partial](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6472-L6496), [selfuncs.c#gincostestimate-entrypages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6884-L6901) |
| No v12 test compares a GIN plan with a B-tree plan; the single GIN-rejected-for-seq-scan assertion is caused by boolean clause simplification | [gin.sql#whole-test](../../../../raw/postgres-12/src/test/regress/sql/gin.sql#L1-L36), [create_index.sql#gin-forced-bitmap](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L271-L279), [bool.out#gin-seqscan](../../../../raw/postgres-12/contrib/btree_gin/expected/bool.out#L88-L96), [int4.sql#five-strategies](../../../../raw/postgres-12/contrib/btree_gin/sql/int4.sql#L1-L15) |
| Every setting that moves the GIN-versus-B-tree boundary is `PGC_USERSET`, so none needs a restart or reload | [guc.c#enable-flags](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L883-L922), [guc.c#random_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3207-L3227), [guc.c#effective_cache_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3117), [guc.c#gin_pending_list_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3175-L3184), [guc.c#gin_fuzzy_search_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3096-L3105) |

## Context Reviewed

- Required wiki navigation: [versions](../../../versions.md), [wiki index](../../../index.md), [v12/index](../../index.md), and recent [log](../../../log.md).
- PostgreSQL 12 planner, costing, and block-count sources: `plancat.c`, `selfuncs.c`, `costsize.c`, `bufmgr.h`, `bufmgr.c`, `rel.h`, `relpath.h`, `smgr.c`, `md.c`, `fd.c`, `pg_config.h.in`, and `config.sgml`.
- Index access method cost-estimate dispatch and per-AM cost functions: the `amcostestimate` wiring in `plancat.c` and `costsize.c`, the B-tree handler in `nbtree.c`, and `btcostestimate`, `hashcostestimate`, `gistcostestimate`, `spgcostestimate`, `gincostestimate`, and `brincostestimate` in `selfuncs.c` to confirm which cost functions delegate to `genericcostestimate()` and how each handles the descent charge (B-tree measured fast-root height, GiST/SP-GiST synthetic `log100(pages)` height, hash none).
- PostgreSQL 12 B-tree sources: `nbtree.c`, `nbtsearch.c`, `nbtpage.c`, `nbtinsert.c`, and `nbtree.h`.
- PostgreSQL 12 diagnostics, docs, and tests: `pgstatindex.c`, `pgstattuple--1.4.sql`, `pgstattuple.sql`, `pgstattuple.out`, `maintenance.sgml`, `ref/reindex.sgml`, `ref/create_index.sgml`, `serial_schedule`, and `parallel_schedule`.
- For the GIN follow-up: the whole path-generation front end in `indxpath.c` (`create_index_paths`, `get_index_paths`, `build_index_paths`, `check_index_only`, `match_clause_to_indexcol`, `match_opclause_to_indexcol`, `get_index_clause_from_support`, `build_paths_for_OR`, `choose_bitmap_and`), path pruning in `pathnode.c` (`add_path`, `compare_path_costs_fuzzily`, `STD_FUZZ_FACTOR`), and the cost entry points in `costsize.c` (`cost_index`, `cost_bitmap_heap_scan`, `cost_bitmap_tree_node`, `cost_seqscan`, `index_pages_fetched`, `disable_cost`).
- GIN internals and their planner interface: `ginutil.c` (`ginhandler`, `ginGetStats`, `ginoptions`), `ginscan.c` (`ginNewScanKey`, the `GIN_SEARCH_MODE_EVERYTHING` path and the old-version error), `ginfast.c` (`gin_clean_pending_list`), `ginget.c` (`GinFuzzySearchLimit`), `ginblock.h` (`GIN_CURRENT_VERSION`), and `gin.h` (`GinStatsData`, `GINNProcs`, the `GIN_SEARCH_MODE_*` constants).
- Cost models compared side by side: `gincostestimate`, `gincost_pattern`, `gincost_opexpr`, `gincost_scalararrayopexpr`, and `GinQualCounts` against `btcostestimate` and `genericcostestimate` in `selfuncs.c`.
- Catalog and DDL boundaries: the GIN operator-family memberships in `pg_amop.dat`, GIN opclasses in `pg_opclass.dat`, AM rows in `pg_am.dat`, and the AM-capability rejections in `indexcmds.c`.
- Extension boundary: `contrib/btree_gin` (`btree_gin.c`, `btree_gin--1.0.sql`, `btree_gin.control`, `Makefile`, `sql/int4.sql`, `sql/bool.sql`, `expected/bool.out`), `contrib/Makefile`, and `contrib/pgstattuple/pgstatindex.c` for `pgstatginindex`.
- Documentation reviewed for the follow-up: `indices.sgml` (index types, ordering, bitmap combination, index-only scans, unique indexes, examining index usage), `indexam.sgml` (`amcanreturn`, `amgetbitmap`), `gin.sgml` (fast update, extractQuery search modes, tips), `btree-gin.sgml`, `pgtrgm.sgml`, `ref/create_index.sgml`, `ref/create_table.sgml`, and `config.sgml` for the eight settings listed above.
- Test surfaces reviewed for the follow-up: `src/test/regress/sql/gin.sql`, `expected/amutils.out`, `sql/create_index.sql` with `expected/create_index.out`, `sql/tsearch.sql`, `src/test/isolation/specs/predicate-gin.spec`, the `gin` and `amutils` entries in both regression schedules, and all 29 `contrib/btree_gin` per-type tests.
- Exact-pin execution environment: PostgreSQL 12.2 built from `raw/postgres-12/` into `.wiki-runtime/pg12-install`, an isolated cluster under `.wiki-runtime/ginbt-data` with a Unix-socket-only listener, and `btree_gin`, `pg_trgm`, and `pgstattuple` installed from the same build.

## Source References

- [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L417)
- [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L1026)
- [plancat.c#amcostestimate](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L276-L277)
- [bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-12/src/include/storage/bufmgr.h#L188-L199)
- [bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2791-L2811)
- [relpath.h#ForkNumber](../../../../raw/postgres-12/src/include/common/relpath.h#L40-L46)
- [rel.h#RelationOpenSmgr](../../../../raw/postgres-12/src/include/utils/rel.h#L472-L479)
- [smgr.c#smgropen](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L139-L178)
- [smgr.c#smgrsw](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L40-L83)
- [smgr.c#smgrnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L630-L640)
- [md.c#mdopen](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L428-L465)
- [md.c#mdnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L698-L755)
- [md.c#_mdfd_openseg](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L1056-L1089)
- [md.c#_mdnblocks](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L1229-L1242)
- [fd.c#FileSize](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L2039-L2053)
- [pg_config.h.in#RELSEG_SIZE](../../../../raw/postgres-12/src/include/pg_config.h.in#L853-L864)
- [selfuncs.c#genericcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5680-L5815)
- [selfuncs.c#btcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5920-L6116)
- [selfuncs.c#hashcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6226-L6235)
- [selfuncs.c#hashcostestimate-no-descent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6237-L6260)
- [selfuncs.c#gistcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6270-L6281)
- [selfuncs.c#gistcostestimate-descent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6283-L6317)
- [selfuncs.c#spgcostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6327-L6338)
- [selfuncs.c#spgcostestimate-descent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6340-L6374)
- [selfuncs.c#gincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6672)
- [selfuncs.c#brincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6985)
- [costsize.c#cost_index](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L470-L665)
- [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L787-L878)
- [pgstattuple--1.4.sql#pgstatindex-regclass](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L62-L73)
- [pgstattuple--1.4--1.5.sql#pgstatindex-regclass-15](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)
- [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L216-L365)
- [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L30-L68)
- [nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L90-L110)
- [nbtree.h#P_IGNORE](../../../../raw/postgres-12/src/include/access/nbtree.h#L186-L195)
- [nbtree.h#fillfactor](../../../../raw/postgres-12/src/include/access/nbtree.h#L159-L171)
- [nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L134)
- [nbtree.c#btgettuple](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L213-L284)
- [nbtree.c#btgetbitmap](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L287-L335)
- [nbtpage.c#_bt_getrootheight](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L575-L626)
- [nbtsearch.c#_bt_next](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1334-L1381)
- [nbtsearch.c#_bt_steppage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1619-L1724)
- [nbtsearch.c#_bt_readnextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1727-L1800)
- [nbtpage.c#_bt_getbuf](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L748-L820)
- [nbtinsert.c#split-new-right-page](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L1408-L1437)
- [indexam.c#index_getnext_tid](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L502-L545)
- [nodeIndexonlyscan.c#visibility-map-check](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L121-L170)
- [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L861-L895)
- [ref/reindex.sgml#reindex-use-cases](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L32-L72)
- [create_index.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L369-L390)
- [config.sgml#seq-random-page-cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4696-L4765)
- [guc.c#seq-random-page-cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3207-L3227)
- [guc.c#effective-cache-size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3108-L3113)
- [pgstattuple.sql#pgstatindex-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L18-L113)
- [pgstattuple.out#empty-index-output](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L47-L85)
- [serial_schedule#btree_index](../../../../raw/postgres-12/src/test/regress/serial_schedule#L100)
- [parallel_schedule#btree_index](../../../../raw/postgres-12/src/test/regress/parallel_schedule#L71)
- [btree_index.sql#tall-fillfactor](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L110-L123)
- [btree_index.sql#page-recycling](../../../../raw/postgres-12/src/test/regress/sql/btree_index.sql#L147-L162)

Added for the GIN follow-up:

- [plancat.c#get_relation_info-skip](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L198-L234)
- [plancat.c#get_relation_info-am-flags](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L266-L279)
- [plancat.c#get_relation_info-sortopfamily](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L281-L320)
- [pathnodes.h#IndexOptInfo](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L781-L835)
- [pathnodes.h#IndexClause](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L1216-L1224)
- [indxpath.c#create_index_paths](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L232-L346)
- [indxpath.c#get_index_paths-submit](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L789-L800)
- [indxpath.c#get_index_paths-nonnative-saop](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L802-L816)
- [indxpath.c#build_index_paths-saop](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L932-L956)
- [indxpath.c#build_index_paths-amoptionalkey](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L964-L974)
- [indxpath.c#build_index_paths-pathkeys](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L985-L1028)
- [indxpath.c#build_index_paths-path-gate](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1030-L1038)
- [indxpath.c#build_index_paths-parallel](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1053-L1072)
- [indxpath.c#choose_bitmap_and](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1368-L1385)
- [indxpath.c#choose_bitmap_and-accept-reject](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1515-L1577)
- [indxpath.c#check_index_only](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L1895-L1907)
- [indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2380-L2447)
- [indxpath.c#match_opclause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2546-L2663)
- [indxpath.c#get_index_clause_from_support](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2717-L2774)
- [pathnode.c#STD_FUZZ_FACTOR](../../../../raw/postgres-12/src/backend/optimizer/util/pathnode.c#L48-L52)
- [pathnode.c#add_path](../../../../raw/postgres-12/src/backend/optimizer/util/pathnode.c#L422-L464)
- [pathnode.c#add_path-costs-better](../../../../raw/postgres-12/src/backend/optimizer/util/pathnode.c#L556-L579)
- [costsize.c:120](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L120)
- [costsize.c:231](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L231)
- [costsize.c#cost_index-enable-indexscan](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L533-L535)
- [costsize.c#cost_index-amcostestimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L537-L548)
- [costsize.c#cost_bitmap_heap_scan](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L939-L1034)
- [costsize.c#cost_bitmap_tree_node](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L1040-L1055)
- [selfuncs.c#GinQualCounts](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6388-L6395)
- [selfuncs.c#gincost_pattern-partial](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6472-L6496)
- [selfuncs.c#gincostestimate](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6672-L6979)
- [selfuncs.c#gincostestimate-pending-guard](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6722-L6730)
- [selfuncs.c#gincostestimate-scale-or-invent](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6732-L6772)
- [selfuncs.c#gincostestimate-correlation](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6794-L6797)
- [selfuncs.c#gincostestimate-fullscan](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6855-L6862)
- [selfuncs.c#gincostestimate-pending](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6864-L6873)
- [selfuncs.c#gincostestimate-entrypages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6875-L6901)
- [selfuncs.c#gincostestimate-startup](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6922-L6926)
- [selfuncs.c#gincostestimate-datapages](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6928-L6966)
- [selfuncs.c#gincostestimate-qualcost](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6968-L6979)
- [ginutil.c#ginhandler](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L36-L81)
- [ginutil.c#ginoptions](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L603-L629)
- [ginutil.c#ginGetStats](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L631-L657)
- [ginscan.c#ginNewScanKey-everything](../../../../raw/postgres-12/src/backend/access/gin/ginscan.c#L376-L387)
- [ginscan.c#ginNewScanKey-old-version](../../../../raw/postgres-12/src/backend/access/gin/ginscan.c#L389-L405)
- [ginget.c#GinFuzzySearchLimit](../../../../raw/postgres-12/src/backend/access/gin/ginget.c#L593-L618)
- [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L1027-L1074)
- [ginblock.h:102](../../../../raw/postgres-12/src/include/access/ginblock.h#L102)
- [gin.h#GINNProcs](../../../../raw/postgres-12/src/include/access/gin.h#L22-L28)
- [gin.h#GIN_SEARCH_MODE](../../../../raw/postgres-12/src/include/access/gin.h#L32-L36)
- [gin.h#GinStatsData](../../../../raw/postgres-12/src/include/access/gin.h#L41-L49)
- [nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L106-L151)
- [indexam.c#index_can_return](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L714-L731)
- [indexcmds.c#amcanunique](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L751-L755)
- [indexcmds.c#amcaninclude](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L756-L760)
- [indexcmds.c#amgettuple-exclusion](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L766-L770)
- [indexcmds.c#amcanorder-ordering](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L1818-L1832)
- [amutils.c#property-functions](../../../../raw/postgres-12/src/backend/utils/adt/amutils.c#L411-L447)
- [pg_am.dat#gin-btree](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L29)
- [pg_amop.dat#gin-array_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1211-L1223)
- [pg_amop.dat#gin-tsvector_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1269-L1275)
- [pg_amop.dat#btree-hash-jsonb_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1436-L1456)
- [pg_amop.dat#gin-jsonb_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1458-L1476)
- [pg_amop.dat#gin-jsonb_path_ops](../../../../raw/postgres-12/src/include/catalog/pg_amop.dat#L1478-L1487)
- [pg_opclass.dat#gin](../../../../raw/postgres-12/src/include/catalog/pg_opclass.dat#L243-L247)
- [contrib/Makefile:13](../../../../raw/postgres-12/contrib/Makefile#L13)
- [btree_gin.control](../../../../raw/postgres-12/contrib/btree_gin/btree_gin.control#L1-L5)
- [btree_gin.c#gin_btree_extract_query](../../../../raw/postgres-12/contrib/btree_gin/btree_gin.c#L47-L101)
- [btree_gin--1.0.sql#int4_ops](../../../../raw/postgres-12/contrib/btree_gin/btree_gin--1.0.sql#L56-L69)
- [int4.sql#five-strategies](../../../../raw/postgres-12/contrib/btree_gin/sql/int4.sql#L1-L15)
- [bool.sql#enable_seqscan-off](../../../../raw/postgres-12/contrib/btree_gin/sql/bool.sql#L1-L9)
- [bool.out#gin-seqscan](../../../../raw/postgres-12/contrib/btree_gin/expected/bool.out#L88-L96)
- [pgstatindex.c#pgstatginindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L480-L497)
- [pgstatindex.c#pgstatginindex_internal](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L509-L575)
- [gin.sql#whole-test](../../../../raw/postgres-12/src/test/regress/sql/gin.sql#L1-L36)
- [create_index.sql#gin-forced-bitmap](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L271-L279)
- [create_index.out#gin-bitmap-plan](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L680-L690)
- [tsearch.sql#gin-bitmap-only](../../../../raw/postgres-12/src/test/regress/sql/tsearch.sql#L94-L101)
- [amutils.out#column-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L96-L108)
- [amutils.out#index-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L122-L129)
- [amutils.out#am-properties](../../../../raw/postgres-12/src/test/regress/expected/amutils.out#L150-L158)
- [predicate-gin.spec#setup](../../../../raw/postgres-12/src/test/isolation/specs/predicate-gin.spec#L1-L20)
- [serial_schedule:107](../../../../raw/postgres-12/src/test/regress/serial_schedule#L107)
- [serial_schedule:139](../../../../raw/postgres-12/src/test/regress/serial_schedule#L139)
- [parallel_schedule:76](../../../../raw/postgres-12/src/test/regress/parallel_schedule#L76)
- [guc.c#enable-flags](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L883-L922)
- [guc.c#gin_fuzzy_search_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3096-L3105)
- [guc.c#effective_cache_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3117)
- [guc.c#gin_pending_list_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3175-L3184)
- [guc.c#random_page_cost](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3207-L3227)
- [indices.sgml#index-types](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L126-L153)
- [indices.sgml#other-operators](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L454-L457)
- [indices.sgml#ordering](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L479-L487)
- [indices.sgml#bitmap-scans](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L592-L605)
- [indices.sgml#unique-indexes](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L643-L653)
- [indices.sgml#index-only-scans](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L1044-L1056)
- [indices.sgml#examining-index-usage](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L1497-L1512)
- [indexam.sgml#amcanreturn](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L373-L386)
- [indexam.sgml#amgetbitmap](../../../../raw/postgres-12/doc/src/sgml/indexam.sgml#L862-L881)
- [gin.sgml#extractQuery-searchmode](../../../../raw/postgres-12/doc/src/sgml/gin.sgml#L215-L222)
- [gin.sgml#fast-update](../../../../raw/postgres-12/doc/src/sgml/gin.sgml#L491-L499)
- [gin.sgml#gin-pending-list-limit](../../../../raw/postgres-12/doc/src/sgml/gin.sgml#L565-L588)
- [btree-gin.sgml#caveats](../../../../raw/postgres-12/doc/src/sgml/btree-gin.sgml#L24-L33)
- [pgtrgm.sgml#index-support](../../../../raw/postgres-12/doc/src/sgml/pgtrgm.sgml#L363-L372)
- [create_index.sgml#gin-storage-parameters](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L438-L487)
- [create_index.sgml#fastupdate](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L443-L469)
- [create_index.sgml#ordered-scans](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L692-L705)
- [create_table.sgml#exclude-amgettuple](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L988-L996)
- [config.sgml#random-page-cost-detail](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4713-L4770)
- [config.sgml#gin-pending-list-limit](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7972-L7993)
