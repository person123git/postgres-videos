---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: Claude-Opus-5-Max 2026-09-10T19:35:00Z
---

# Physical Index Statistics, Tuple Counts, and Bytes per Tuple in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [What PostgreSQL stores and what it does not](#what-postgresql-stores-and-what-it-does-not)
  - [Why `pg_class.reltuples` changes meaning](#why-pg_classreltuples-changes-meaning)
  - [Shared page and tuple overhead](#shared-page-and-tuple-overhead)
  - [Per-access-method inventory](#per-access-method-inventory)
  - [Calculations that are valid](#calculations-that-are-valid)
  - [Catalog inventory SQL](#catalog-inventory-sql)
  - [B-tree and hash physical data-item SQL](#b-tree-and-hash-physical-data-item-sql)
  - [Consistency, cost, and privilege limits](#consistency-cost-and-privilege-limits)
  - [Planner, caller-callee, and generated-build boundaries](#planner-caller-callee-and-generated-build-boundaries)
  - [Tests and explicit test gaps](#tests-and-explicit-test-gaps)
  - [What an isolated 12.2 server measured](#what-an-isolated-122-server-measured)
- [Measurement Script](#measurement-script)
  - [Usage](#usage)
  - [Stages](#stages)
  - [The script](#the-script)
  - [Last run](#last-run)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

For all PostgreSQL 12 index access methods, analyze all physical statistics stored for each index, including statistics in `pg_class`. Explain whether and how these statistics can be used to calculate or estimate the number of index tuples and the on-disk bytes represented by each tuple.

Prompt note: the original request had spelling and grammatical errors. The user approved this corrected wording before drafting.

## Answer

No PostgreSQL 12 catalog column gives an exact, access-method-independent count of physical index tuples or an exact number of on-disk bytes per tuple. `pg_class.relpages` and `reltuples` are explicitly allowed to be stale, and `reltuples` can change units after `CREATE INDEX`, standalone `ANALYZE`, and `VACUUM`. `pg_relation_size()` gives the current logical file length, but dividing it by `reltuples` gives only **allocated bytes per current catalog-count unit**. It is not a tuple-width calculation.[pg_class.h#physical-relstats](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L49-L66) [index.c#index-build-statistics](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2989) [analyze.c#index-relstats-update](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629) [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1771-L1815) [dbsize.c#calculate_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L266-L308)

PostgreSQL 12 bootstraps six core index access methods: B-tree, hash, GiST, GIN, SP-GiST, and BRIN. Bloom is a shipped `contrib` extension that registers a seventh index access method. A partitioned-index root has `relkind = 'I'` and no storage; its physical child indexes have `relkind = 'i'` and must be measured separately.[pg_am.dat#core-index-access-methods](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L35) [bloom--1.0.sql#CREATE-ACCESS-METHOD](../../../../raw/postgres-12/contrib/bloom/bloom--1.0.sql#L1-L25) [pg_class.h#relation-kinds-and-storage](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L152-L192)

### Short answer

| Access method | Heap-to-index relationship | Persistent whole-index counter | Best meaningful physical denominator | Can stored aggregates recover heap rows? |
| --- | --- | --- | --- | --- |
| B-tree | Normally one leaf data item per indexed heap tuple version; internal pivots and leaf high keys are additional physical items.[nbtsort.c#_bt_build_callback](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L593-L619) [nbtree.h#high-key](../../../../raw/postgres-12/src/include/access/nbtree.h#L198-L219) | None. `btm_last_cleanup_num_heap_tuples` is the parent-heap count recorded by the last VACUUM pass over the index, bulk delete or cleanup, not the current leaf-item count.[nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L97-L110) [nbtree.c#btbulkdelete-meta-update](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L877-L883) [nbtree.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L783-L845) | Stable full scan of leaf data items, excluding high keys. | No exact current row count; dead entries, HOT chains, partial predicates, and concurrent change break equality with visible rows.[README.HOT#HOT-index-entries](../../../../raw/postgres-12/src/backend/access/heap/README.HOT#L34-L55) |
| Hash | One stored item per qualifying non-NULL heap tuple version; NULL keys are omitted.[hashutil.c#_hash_convert_tuple](../../../../raw/postgres-12/src/backend/access/hash/hashutil.c#L312-L343) | `hashm_ntuples`, maintained as the logical hash item count; split copies and not-yet-cleaned physical items can make a page census differ.[hash.h#HashMetaPageData](../../../../raw/postgres-12/src/include/access/hash.h#L242-L263) [hash.c#hashbulkdelete](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L444-L633) | Stable bucket/overflow-page item scan. | Only with external knowledge of the partial predicate, NULL rule, dead entries, and concurrency. |
| GiST | One leaf tuple is built per qualifying heap tuple version; routing tuples occupy internal pages.[gistbuild.c#gistBuildCallback](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L457-L495) | None. GiST has no metapage at all: block zero is the root, and the page opaque data holds no counter.[gist_private.h#GIST_ROOT_BLKNO](../../../../raw/postgres-12/src/include/access/gist_private.h#L262-L263) [gist.h#GISTPageOpaqueData](../../../../raw/postgres-12/src/include/access/gist.h#L41-L82) | A correct AM-aware scan of nondeleted leaf pages. | Not from stored aggregates. PostgreSQL 12's generic `pgstattuple()` GiST path has source-visible gaps described below. |
| GIN | One heap TID can produce many extracted-key associations and can occur in pending tuples, embedded posting lists, or posting trees.[ginutil.c#ginExtractEntries](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L477-L599) [ginblock.h#posting-layout](../../../../raw/postgres-12/src/include/access/ginblock.h#L183-L191) [ginblock.h#posting-lists-and-trees](../../../../raw/postgres-12/src/include/access/ginblock.h#L218-L344) | Pending-list counts plus build/last-maintenance page and key counts; no total posting-association count.[ginblock.h#GinMetaPageData](../../../../raw/postgres-12/src/include/access/ginblock.h#L54-L100) [gininsert.c#gin-build-metapage-statistics](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L395-L406) [ginutil.c#ginUpdateStats](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L659-L716) | The denominator must be named: entry keys, pending tuples, posting TIDs, or distinct referenced heap TIDs. | No. Aggregate counters are insufficient, and `reltuples` itself changes unit.[ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L686-L731) |
| SP-GiST | One live leaf tuple carries one heap TID; inner, node, redirect, dead, and placeholder tuples are separate physical objects.[spgist_private.h#tuple-states](../../../../raw/postgres-12/src/include/access/spgist_private.h#L232-L244) [spgist_private.h#inner-and-node-tuples](../../../../raw/postgres-12/src/include/access/spgist_private.h#L245-L305) [spgist_private.h#leaf-tuples](../../../../raw/postgres-12/src/include/access/spgist_private.h#L307-L372) | No live/dead aggregate. The metapage contains only possibly stale last-used-page/free-space hints.[spgist_private.h#page-and-metapage-data](../../../../raw/postgres-12/src/include/access/spgist_private.h#L36-L101) | Stable count of `SPGIST_LIVE` leaf tuples. | Not from stored aggregates. |
| BRIN | One logical summary tuple represents a heap page range, not a heap row.[brin_tuple.h#BRIN-tuple-purpose](../../../../raw/postgres-12/src/include/access/brin_tuple.h#L18-L30) | `pagesPerRange` and `lastRevmapPage`; valid reverse-map TIDs identify referenced summaries or placeholders, not necessarily completed summaries.[brin_page.h#metapage-and-revmap](../../../../raw/postgres-12/src/include/access/brin_page.h#L63-L94) [brin_revmap.c#leftover-placeholder](../../../../raw/postgres-12/src/backend/access/brin/brin_revmap.c#L397-L405) | Dereferenced valid reverse-map entries after excluding placeholder tuples for completed summaries; used regular-page line pointers for all physical summary and placeholder items. | No. A range can contain zero through many heap tuple versions. |
| Contrib Bloom | One fixed-size signature tuple per qualifying heap tuple version.[blinsert.c#bloomBuildCallback](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L72-L117) | No tuple aggregate; the metapage stores signature options and a not-full-page reuse cache.[bloom.h#BloomMetaPageData](../../../../raw/postgres-12/contrib/bloom/bloom.h#L99-L165) | Sum `maxoff`, the per-page tuple count, across nondeleted data pages.[bloom.h#BloomPageOpaqueData](../../../../raw/postgres-12/contrib/bloom/bloom.h#L31-L46) | Only with external predicate/dead-entry knowledge. |

### What PostgreSQL stores and what it does not

| Location | Stored fields | Meaning for physical accounting |
| --- | --- | --- |
| `pg_class` | `relam`, `relfilenode`, `reltablespace`, `relpages`, `reltuples`, `relallvisible`, persistence, relation kind, attribute count, and AM-specific `reloptions`.[pg_class.h#FormData_pg_class](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L29-L84) [pg_class.h#reloptions](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L128-L139) | `relpages` is the last stored main-fork block count. `reltuples` is a `float4` estimate whose unit depends on its last writer. Index writers set `relallvisible` to zero because index relations do not use heap visibility-map accounting.[index.c#index_update_stats](../../../../raw/postgres-12/src/backend/catalog/index.c#L2655-L2712) [index.c#index-relallvisible](../../../../raw/postgres-12/src/backend/catalog/index.c#L2761-L2785) |
| `pg_index` | Parent table, key and included-column counts, uniqueness and state flags, column map, collations, opclasses, per-column AM options, expression tree, and partial predicate.[pg_index.h#FormData_pg_index](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L29-L59) | These fields explain which heap rows and attributes could be represented. They contain no page count, tuple count, free-space count, or byte count. |
| `pg_statistic` / `pg_stats` | Table-column distributions and statistics for expression-index attributes; `stawidth` is the average width in bytes of non-null entries *as actually stored, post-TOAST*, so a moved-out-of-line value counts only its pointer.[analyze.c#index-expression-statistics](../../../../raw/postgres-12/src/backend/commands/analyze.c#L413-L467) [pg_statistic.h#stawidth](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L39-L49) | These are planner value-distribution statistics. Expression `stawidth` uses the expression result type and is not the serialized index item, opclass storage value, or page footprint.[analyze.c#index-expression-result-type](../../../../raw/postgres-12/src/backend/commands/analyze.c#L869-L925) |
| `pg_stat_all_indexes` / `pg_statio_all_indexes` | `idx_scan`, `idx_tup_read`, `idx_tup_fetch`, blocks read, and blocks hit.[system_views.sql#index-statistics-views](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L658-L708) | These are cumulative workload and I/O counters, not current population or allocation. Bitmap scans, dead entries, and index-only scans also make read/fetch units differ.[monitoring.sgml#index-statistics](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2847-L2940) |
| AM metapage/page opaque data | Access-method-specific structural fields and, for some AMs, persistent counters. | These fields are detailed below. PostgreSQL 12 has no generic callback that returns a physical item count, occupied bytes, or bloat.[amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L163-L233) |
| `IndexBuildResult` / `IndexBulkDeleteResult` | Build counts; VACUUM page, tuple, removed, deleted, free, and estimated/exact fields.[genam.h#index-maintenance-statistics](../../../../raw/postgres-12/src/include/access/genam.h#L27-L81) | These structures are transient. Their values can update `pg_class` or appear in `VACUUM` reporting, but PostgreSQL does not retain every field as a per-index catalog row.[vacuumlazy.c#index-cleanup-report](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1803-L1827) |

`pg_class.reloptions` contains physical policy rather than measured occupancy. The complete shipped set relevant here is: B-tree `fillfactor` and `vacuum_cleanup_index_scale_factor`; hash `fillfactor`; GiST `fillfactor` and `buffering`; SP-GiST `fillfactor`; GIN `fastupdate` and `gin_pending_list_limit`; BRIN `pages_per_range` and `autosummarize`; and Bloom signature `length` plus per-column `colN` bit counts. These settings can change tuple width, packing, pending storage, summary granularity, cleanup, or build strategy, but none is a current byte or tuple census.[reloptions.c#index-fillfactors](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L177-L216) [reloptions.c#B-tree-and-GiST-options](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L423-L449) [ginutil.c#ginoptions](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L602-L629) [spgutils.c#spgoptions](../../../../raw/postgres-12/src/backend/access/spgist/spgutils.c#L583-L590) [brin.c#brinoptions](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L817-L845) [blutils.c#Bloom-reloptions](../../../../raw/postgres-12/contrib/bloom/blutils.c#L55-L79)

`pg_relation_size(index, 'main')` is current in a different sense: PostgreSQL opens the relation, calls `stat()` on each segment file, and sums `st_size`. This is logical relation-file length. It is not occupied tuple payload and not filesystem block allocation after sparse files, compression, or storage-layer effects.[dbsize.c#calculate_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L266-L308)

The named relation forks are `main`, `fsm`, `vm`, and `init`; those exact strings are what `pg_relation_size()` accepts, through `forkname_to_number()`. `pg_table_size(index_oid)` behaves sensibly on an index and sums all its forks; `pg_indexes_size(index_oid)` instead means indexes attached to that relation and therefore returns zero for an index.[relpath.h#ForkNumber](../../../../raw/postgres-12/src/include/common/relpath.h#L32-L55) [relpath.c#forkNames](../../../../raw/postgres-12/src/common/relpath.c#L26-L64) [dbsize.c#calculate_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L380-L408) [dbsize.c#calculate_indexes_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L410-L448)

The free space map (FSM) is another persistent physical hint, not a catalog aggregate. B-tree, GiST, GIN, SP-GiST, and Bloom use the generic index-FSM API to find wholly reusable pages. Its implementation writes `BLCKSZ - 1` for free and `0` for used, so the fork records page availability rather than byte-granular free space.[indexfsm.c#index-FSM-implementation](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L32-L73) [nbtpage.c#B-tree-FSM-allocation](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L790-L815) [gistutil.c#GiST-FSM-allocation](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L805-L830) [ginutil.c#GIN-FSM-allocation](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L286-L305) [spgutils.c#SP-GiST-FSM-allocation](../../../../raw/postgres-12/src/backend/access/spgist/spgutils.c#L205-L230) [blutils.c#Bloom-FSM-allocation](../../../../raw/postgres-12/contrib/bloom/blutils.c#L340-L360)

Hash instead keeps overflow-page availability in metapage-referenced bitmap pages. BRIN uses the general FSM, recording actual regular-page free space after quantizing it into an eight-bit category; reads return the category's lower-bound byte estimate. The shipped `pg_freespacemap` extension exposes the recorded estimate through `pg_freespace(regclass, bigint)`. The byte length of any FSM fork says how large the map is; it does not equal the free bytes in the main fork.[hash.h#overflow-bitmaps](../../../../raw/postgres-12/src/include/access/hash.h#L201-L228) [hash.h#bitmap-pages](../../../../raw/postgres-12/src/include/access/hash.h#L287-L307) [brin_pageops.c#brin_getinsertbuffer](../../../../raw/postgres-12/src/backend/access/brin/brin_pageops.c#L660-L706) [brin_pageops.c#BRIN-FSM-recording](../../../../raw/postgres-12/src/backend/access/brin/brin_pageops.c#L854-L899) [freespace.c#RecordPageWithFreeSpace](../../../../raw/postgres-12/src/backend/storage/freespace/freespace.c#L173-L191) [freespace.c#FSM-quantization](../../../../raw/postgres-12/src/backend/storage/freespace/freespace.c#L379-L416) [pg_freespacemap--1.1.sql#pg_freespace](../../../../raw/postgres-12/contrib/pg_freespacemap/pg_freespacemap--1.1.sql#L7-L10) [pg_freespacemap.c#pg_freespace](../../../../raw/postgres-12/contrib/pg_freespacemap/pg_freespacemap.c#L17-L42)

For B-tree, GiST, GIN, SP-GiST, and Bloom, counting nonzero `pg_freespace` results counts pages recorded as wholly reusable, subject to FSM staleness. For BRIN, summing the returned values gives the sum of recorded, quantized lower-bound free-space estimates. Neither calculation counts tuples, and neither subtracts bytes from the relation's allocated file length.[indexfsm.c#index-FSM-implementation](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L32-L73) [freespace.c#FSM-quantization](../../../../raw/postgres-12/src/backend/storage/freespace/freespace.c#L379-L416)

### Why `pg_class.reltuples` changes meaning

The common build layer calls the selected AM's `ambuild` callback and copies `IndexBuildResult.index_tuples` into the index's `pg_class.reltuples`. The AM therefore chooses the build-time unit.[genam.h#IndexBuildResult](../../../../raw/postgres-12/src/include/access/genam.h#L27-L34) [index.c#index_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L2808-L2815) [index.c#ambuild-call](../../../../raw/postgres-12/src/backend/catalog/index.c#L2899-L2904) [index.c#index-build-statistics](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2989)

A standalone table `ANALYZE` later overwrites every ordinary index's `reltuples` with `ceil(tupleFract * totalrows)`. `tupleFract` starts at `1.0` and, for a partial index, is the sampled fraction of heap rows that passes the predicate. This normalizes the catalog value to estimated live heap rows satisfying the partial predicate, or to the whole-table estimate for a nonpartial index—even when an AM such as hash omits NULL keys. The guard is `if (!inh && !(params->options & VACOPT_VACUUM))`, so the overwrite is skipped both when the `ANALYZE` runs as part of a `VACUUM`—the VACUUM phase is expected to have supplied the index count—and on the inheritance-tree pass.[analyze.c#index-initialization](../../../../raw/postgres-12/src/backend/commands/analyze.c#L413-L467) [analyze.c#partial-index-sample](../../../../raw/postgres-12/src/backend/commands/analyze.c#L714-L822) [analyze.c#index-relstats-update](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629) [hashutil.c#hash-NULL-omission](../../../../raw/postgres-12/src/backend/access/hash/hashutil.c#L312-L343)

VACUUM passes an estimated or exact surviving-heap count to the AM. It writes the AM's returned `num_index_tuples` into `pg_class` only when `estimated_count` is false; otherwise an older value can remain.[genam.h#IndexVacuumInfo](../../../../raw/postgres-12/src/include/access/genam.h#L36-L53) [genam.h#IndexBulkDeleteResult](../../../../raw/postgres-12/src/include/access/genam.h#L55-L81) [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1058-L1113) [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1771-L1815)

| Last writer | Value put in index `reltuples` |
| --- | --- |
| New physical relation before build | Zero.[heap.c#new-relation-relstats](../../../../raw/postgres-12/src/backend/catalog/heap.c#L954-L998) |
| `CREATE INDEX` / `REINDEX` | B-tree, GiST, SP-GiST, and Bloom count one successful leaf insertion per qualifying build callback; hash omits NULL keys; GIN counts extracted key associations; BRIN counts inserted range summaries.[nbtsort.c#_bt_build_callback](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L593-L619) [gistbuild.c#gistBuildCallback](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L457-L495) [spginsert.c#spgist-build-count](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L41-L69) [blinsert.c#bloom-build-count](../../../../raw/postgres-12/contrib/bloom/blinsert.c#L72-L117) [hash.c#hash-build-callback](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L200-L236) [gininsert.c#gin-build-count](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L245-L288) [brin.c#brin-build-count](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L658-L743) |
| Standalone table `ANALYZE` | Estimated live heap rows satisfying the index predicate; all nonpartial indexes get the table estimate, even hash indexes that omit NULLs.[analyze.c#index-relstats-update](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629) |
| Sufficiently complete `VACUUM` | AM cleanup result. GIN substitutes the heap tuple count and calls it bogus for partial GIN. BRIN counts newly summarized ranges plus existing valid reverse-map entries for full ranges, can therefore include a crash-leftover placeholder, and skips the last partial range. Other AMs return AM-specific surviving data/leaf-item counts subject to their concurrency rules.[ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L686-L731) [brin.c#brinvacuumcleanup](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L786-L815) [brin.c#brinsummarize-counting](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L1299-L1401) [brin_revmap.c#leftover-placeholder](../../../../raw/postgres-12/src/backend/access/brin/brin_revmap.c#L397-L405) |

Therefore the expression `main_bytes / reltuples` can change sharply even when the index file does not. If the last operation is unknown, the denominator's unit is unknown. A plain table `ANALYZE` can deliberately normalize it to the catalog row-estimate unit—predicate-scaled for a partial index and the whole table for a nonpartial index—but that is not necessarily a count of rows actually represented by the AM and does not make the ratio a physical tuple size.[analyze.c#index-relstats-update](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629) [hashutil.c#hash-NULL-omission](../../../../raw/postgres-12/src/backend/access/hash/hashutil.c#L312-L343)

### Shared page and tuple overhead

Most built-in index pages use a generic page header, a line-pointer array, free space, tuple/item bytes, and AM-specific special space. `PageHeaderData` stores the page LSN, checksum, flags, free-space boundaries, page-size/version, and `pd_prune_xid`. The header comment states flatly that `pd_prune_xid` "is currently unused in index pages," but GIN in fact reuses that field as a deleted-page reclamation XID; see `## Open Questions`.[bufpage.h#page-layout](../../../../raw/postgres-12/src/include/storage/bufpage.h#L22-L75) [bufpage.h#pd_prune_xid](../../../../raw/postgres-12/src/include/storage/bufpage.h#L134-L135) [bufpage.h#PageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L105-L164) [ginblock.h#deleted-page-xid](../../../../raw/postgres-12/src/include/access/ginblock.h#L131-L138)

An ordinary `IndexTuple` stores a heap TID and a `t_info` word containing NULL, variable-width, AM-reserved, and serialized-size bits. `IndexTupleSize()` therefore gives one tuple object's serialized length, not its whole-file share. That length is itself already `MAXALIGN`ed: `index_form_tuple()` rounds the size up before storing it in `t_info`.[itup.h#IndexTupleData](../../../../raw/postgres-12/src/include/access/itup.h#L23-L90) [indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L126-L188)

For a slotted page, inserting an item consumes `MAXALIGN(item_length)` bytes in the tuple area and, when a new slot is needed, one `ItemIdData` line pointer. `PageAddItemExtended()` stores the caller's unrounded `size` in the line pointer, but B-tree and hash pass an already-`MAXALIGN`ed `IndexTupleSize()`, so for those AMs `lp_len` equals the aligned footprint and includes the tuple's own trailing padding. Page headers, special space, internal tuples, metapages, fragmentation, free space, and deleted/reusable pages remain shared overhead.[bufpage.c#PageAddItemExtended-space](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L290-L341) [itemid.h#ItemIdData](../../../../raw/postgres-12/src/include/storage/itemid.h#L20-L41) [nbtinsert.c#_bt_insertonpg-itemsz](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L963-L965) [hashinsert.c#_hash_doinsert-itemsz](../../../../raw/postgres-12/src/backend/access/hash/hashinsert.c#L57-L60)

This formula is not universal. Bloom stores a packed fixed-size tuple array without line pointers: `BloomPageAddItem()` writes each tuple at a computed offset and advances `pd_lower` directly, never allocating an `ItemIdData`. GIN posting-tree leaf pages likewise hold posting-list segments rather than ordinary index tuples—compressed in the current GIN version 2 format, but still an uncompressed `ItemPointer` array on pre-9.4 pages carried forward by `pg_upgrade`.[bloom.h#Bloom-page-layout](../../../../raw/postgres-12/contrib/bloom/bloom.h#L58-L74) [blutils.c#BloomPageAddItem](../../../../raw/postgres-12/contrib/bloom/blutils.c#L307-L339) [ginblock.h#posting-tree-data-pages](../../../../raw/postgres-12/src/include/access/ginblock.h#L265-L326)

### Per-access-method inventory

#### B-tree

The B-tree metapage stores `btm_magic`, format version, root block/level, fast-root block/level, the oldest deletion XID, and the parent heap tuple count seen by the last cleanup. Each ordinary page stores left/right sibling links, level or deletion XID, flags, and the last-split VACUUM cycle ID. Flags identify leaf, root, deleted, metapage, half-dead, split-end, garbage, and incomplete-split states.[nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L55-L78) [nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L90-L110)

None of those fields is a current global entry count. `btm_last_cleanup_num_heap_tuples` is initialized to `-1`, rewritten with `IndexVacuumInfo.num_heap_tuples` by both `btbulkdelete()` and `btvacuumcleanup()`, and consulted with the oldest deletion XID only to decide whether another cleanup is useful.[nbtpage.c#metapage-initialization](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L47-L77) [nbtpage.c#_bt_update_meta_cleanup_info](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L150-L226) [nbtree.c#btbulkdelete-meta-update](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L877-L883) [nbtree.c#btvacuumcleanup-meta-update](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L924-L926) [nbtree.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L783-L845)

`pgstatindex()` exposes index size, tree version/level/root, internal/leaf/empty/deleted page counts, average leaf density, and leaf fragmentation. It does not expose a tuple count. The same extension's `pg_relpages()` returns the current main-fork block count through `RelationGetNumberOfBlocks()`; that is a dynamic size observation, not the stored `pg_class.relpages` value. `pageinspect` exposes metapage and per-page fields and individual item lengths; page-level item totals require care because a non-rightmost B-tree page has a high key that is not a heap-row leaf entry.[pgstattuple--1.4--1.5.sql#pgstatindex-result](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L34) [pgstatindex.c#pgstatindex-full-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L216-L365) [pgstatindex.c#pg_relpages_v1_5](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L406-L428) [nbtree.h#high-key](../../../../raw/postgres-12/src/include/access/nbtree.h#L198-L219) [pageinspect--1.5.sql#btree-functions](../../../../raw/postgres-12/contrib/pageinspect/pageinspect--1.5.sql#L146-L189) [pageinspect--1.6--1.7.sql#bt_metap](../../../../raw/postgres-12/contrib/pageinspect/pageinspect--1.6--1.7.sql#L7-L26)

For physical leaf accounting, `pgstattuple()` starts after the metapage—the dispatcher passes `BTREE_METAPAGE + 1` as the first block—visits only nonignored leaf pages, starts at `P_FIRSTDATAKEY()` to exclude high keys, and sums each line pointer's item length. Its “live” count means “not marked `LP_DEAD`,” not MVCC-visible heap rows.[pgstattuple.c#btree-dispatch-start-block](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L265-L267) [pgstattuple.c#pgstat_btree_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L406-L448) [pgstattuple.c#pgstat_index_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L564-L590)

#### Hash

Each hash page stores previous/next links, bucket number, type/state flags, and a page identifier. The metapage stores magic/version, `hashm_ntuples`, fill factor, page and bitmap sizes, bitmap shift, maximum bucket, high/low masks, overflow split point, first free overflow bit, bitmap count, hash procedure OID, cumulative overflow-page counts, and bitmap page block numbers.[hash.h#HashPageOpaqueData](../../../../raw/postgres-12/src/include/access/hash.h#L45-L99) [hash.h#HashMetaPageData](../../../../raw/postgres-12/src/include/access/hash.h#L193-L263)

`hashm_ntuples` is the closest core persistent global count. Normal insertion increments it only after the index tuple is added to a page, and `hashinsert()` returns without inserting anything when `_hash_convert_tuple()` rejects a NULL key; VACUUM can replace the counter with a full bucket scan or dead-reckon after concurrent inserts/splits.[hashinsert.c#hashm_ntuples-increment](../../../../raw/postgres-12/src/backend/access/hash/hashinsert.c#L190-L235) [hash.c#hashinsert-null-rejection](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L244-L269) [hash.c#hashbulkdelete](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L444-L633) Physical bucket line items can temporarily exceed it because a bucket split copies items before split cleanup removes the old copies.[hashpage.c#bucket-split-copy](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L1107-L1287)

`pageinspect.hash_metapage_info()` exposes every metapage field, while its other hash functions expose page type, live/dead items, free bytes, links, bucket, flags, bitmap state, and individual items. `pgstathashindex()` performs a whole-index page scan and returns the metapage hash version, bucket/overflow/bitmap/unused page counts, non-`LP_DEAD` items, `LP_DEAD` items, and free percentage.[pageinspect--1.5--1.6.sql#hash-functions](../../../../raw/postgres-12/contrib/pageinspect/pageinspect--1.5--1.6.sql#L6-L77) [pgstattuple--1.4--1.5.sql#pgstathashindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L123-L133) [pgstatindex.c#pgstathashindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L575-L727)

Generic `pgstattuple()` also supports hash. It scans bucket and overflow pages and sums line-item counts and lengths, so it measures physical stored items, including split copies that still exist, rather than relying on `hashm_ntuples`.[pgstattuple.c#pgstat_hash_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L450-L490) [pgstattuple.c#pgstat_index_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L564-L590)

#### GiST

GiST has no metapage or global persistent count. Its root is block zero. Each page's opaque trailer stores a node-sequence number, right link, flags, and page identifier; flags identify leaf, deleted, tuples-deleted, follow-right, and garbage states.[gist_private.h#GIST_ROOT_BLKNO](../../../../raw/postgres-12/src/include/access/gist_private.h#L263) [gist.h#GISTPageOpaqueData](../../../../raw/postgres-12/src/include/access/gist.h#L41-L82)

Build creates one leaf `IndexTuple` per qualifying heap callback and counts it once. VACUUM adds each leaf page's surviving item count, but concurrent page splits can double-count; cleanup caps the total to the heap count only when VACUUM knows that count exactly, that is when `estimated_count` is false.[gistbuild.c#gistBuildCallback](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L457-L495) [gistvacuum.c#gistvacuumpage-leaf-count](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c#L318-L412) [gistvacuum.c#gistvacuumcleanup](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c#L100-L145)

PostgreSQL 12's `pgstattuple()` dispatch claims GiST support, but the pinned implementation starts at `GIST_ROOT_BLKNO + 1`. It therefore returns zero leaf items for a one-page GiST whose root is itself a leaf. It also tests `F_LEAF` without excluding `F_DELETED`, while page deletion preserves existing flags and repurposes `pd_lower` for deletion metadata rather than line pointers. This page does not treat that GiST result as an exact physical census.[pgstattuple.c#GiST-dispatch](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L283) [pgstattuple.c#pgstat_gist_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L492-L518) [gist.h#deleted-page-layout](../../../../raw/postgres-12/src/include/access/gist.h#L160-L183)

PostgreSQL 12 `pageinspect` has no GiST-specific decoder. A reliable GiST count therefore requires a corrected extension or another AM-aware page walker that includes a leaf root, excludes deleted pages, and distinguishes leaf from routing tuples.[pageinspect/Makefile#modules-and-tests](../../../../raw/postgres-12/contrib/pageinspect/Makefile#L3-L15)

#### GIN

Each GIN page stores a right link, a context-dependent `maxoff`, and flags for data, leaf, deleted, metapage, pending-list, full-row, incomplete-split, and compressed pages. On a nonleaf posting-data page `maxoff` counts `PostingItem` objects; on a pending-list page it counts heap-tuple insertion groups, not necessarily the temporary index tuples on that page.[ginblock.h#GinPageOpaqueData](../../../../raw/postgres-12/src/include/access/ginblock.h#L29-L48) [ginfast.c#pending-list-page-accounting](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L52-L208)

The metapage stores pending-list head/tail, free bytes in the tail, pending page count, pending heap-tuple count, total/entry/data page counts, entry-key count, and format version. Pending-list counters are actively maintained, while the main page/key fields are planner statistics refreshed by VACUUM.[ginblock.h#GinMetaPageData](../../../../raw/postgres-12/src/include/access/ginblock.h#L54-L100) [ginfast.c#pending-list-maintenance](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L544-L625) [ginutil.c#ginGetStats](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L631-L657) [ginutil.c#ginUpdateStats](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L659-L716)

`nPendingHeapTuples` is not a pending physical `IndexTuple` count: `ginHeapTupleFastCollect()` forms one temporary tuple per extracted entry, while the counter advances once per heap tuple. `nEntries` counts entry-tree key tuples, not posting TIDs; until VACUUM physically recounts entry leaf items, repeated build accumulator flushes can also make the build-time value differ from a global distinct-key count, because each flush calls `ginEntryInsert()` again for keys it has already counted.[ginfast.c#ginHeapTupleFastCollect](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L464-L542) [ginfast.c#nPendingHeapTuples-increment](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L368-L373) [gininsert.c#gin-build-entry-accounting](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L172-L205) [gininsert.c#ginBuildCallback-accumulator-flush](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L275-L314) [ginvacuum.c#GIN-entry-page-census](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L746-L781)

After build, `reltuples` is the sum of extracted-key associations across indexed columns. After a sufficiently complete VACUUM, GIN instead reports the heap tuple count and explicitly notes that this is bogus for a partial GIN index because distinct referenced heap tuples are hard to determine.[gininsert.c#gin-build-count](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L245-L288) [gininsert.c#ginbuild-result](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L316-L427) [ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L686-L731)

`pgstatginindex()` exposes only version, pending pages, and pending heap tuples. `pageinspect` exposes the full metapage, page opaque fields, and compressed posting-tree leaf segments, but it does not provide one whole-index traversal that decodes pending tuples, entry tuples with embedded postings, and every posting tree. A total association count requires such a traversal; a distinct referenced-TID count additionally requires deduplication.[pgstattuple--1.4--1.5.sql#pgstatginindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L47-L57) [pgstatindex.c#pgstatginindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L479-L573) [pageinspect--1.5.sql#GIN-functions](../../../../raw/postgres-12/contrib/pageinspect/pageinspect--1.5.sql#L240-L279) [ginfuncs.c#gin_leafpage_items](../../../../raw/postgres-12/contrib/pageinspect/ginfuncs.c#L156-L265)

#### SP-GiST

SP-GiST reserves block 0 for its metapage, block 1 for the normal root, and block 2 for the NULL root. Page opaque data stores flags plus redirection and placeholder counts and deliberately stores no live/dead count.[spgist_private.h#fixed-pages](../../../../raw/postgres-12/src/include/access/spgist_private.h#L25-L34) [spgist_private.h#SpGistPageOpaqueData](../../../../raw/postgres-12/src/include/access/spgist_private.h#L36-L71)

The metapage contains a magic value and eight last-used-page entries. Each entry has a block number and a free-space estimate that may be obsolete; writes are opportunistic placement hints, and callers recheck the real page before use.[spgist_private.h#SpGistMetaPageData](../../../../raw/postgres-12/src/include/access/spgist_private.h#L73-L101) [spgutils.c#metapage-cache-update](../../../../raw/postgres-12/src/backend/access/spgist/spgutils.c#L268-L312) [spgutils.c#cached-page-recheck](../../../../raw/postgres-12/src/backend/access/spgist/spgutils.c#L385-L490)

Inner tuples store state, `allTheSame`, node count, prefix size, total size, and an optional prefix plus embedded node tuples. A live leaf stores state, tuple size, same-parent link, heap TID, and opclass-defined datum. Redirect/dead/placeholder tuples have their own state and size, and redirects carry an index pointer and transaction ID.[spgist_private.h#inner-and-node-tuples](../../../../raw/postgres-12/src/include/access/spgist_private.h#L245-L305) [spgist_private.h#leaf-and-dead-tuples](../../../../raw/postgres-12/src/include/access/spgist_private.h#L307-L372)

Build counts one successful leaf insertion per indexed heap tuple. VACUUM counts `SPGIST_LIVE` leaf tuples—in `vacuumLeafPage()` for ordinary leaf pages and in `vacuumLeafRoot()` for a leaf root—but concurrent tuple movement can double-count; it clamps only when a known whole-heap count is lower. Empty pages remain reusable inside the main fork because SP-GiST cleanup does not truncate the index.[spginsert.c#spgist-build-count](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L41-L69) [spgvacuum.c#vacuumLeafPage](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L105-L168) [spgvacuum.c#vacuumLeafRoot](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L401-L480) [spgvacuum.c#scan-and-no-truncation](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L786-L890) [spgvacuum.c#concurrent-count-cap](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L926-L969)

Neither `pageinspect` nor generic `pgstattuple()` supplies an SP-GiST decoder in PostgreSQL 12. A physical census needs custom code that counts live leaves separately from routing, redirect, dead, and placeholder objects.[pageinspect/Makefile#modules-and-tests](../../../../raw/postgres-12/contrib/pageinspect/Makefile#L3-L15) [pgstattuple.c#unsupported-index-AMs](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L312)

#### BRIN

BRIN page special space records page type and an evacuation flag. The three page types are metapage, reverse map, and regular summary storage. The metapage contains magic, version, `pagesPerRange`, and `lastRevmapPage`; reverse-map pages are arrays of summary-tuple TIDs.[brin_page.h#page-types](../../../../raw/postgres-12/src/include/access/brin_page.h#L23-L60) [brin_page.h#metapage-and-revmap](../../../../raw/postgres-12/src/include/access/brin_page.h#L63-L94)

For each heap page range, a valid reverse-map TID points to a current summary or placeholder tuple; an invalid TID means unsummarized. A placeholder normally exists during summarization and can survive a crash. A BRIN tuple stores the range's starting heap block, null/placeholder/data-offset bits, optional per-column null flags, and an opclass-defined number and type of summary values.[brin_revmap.c#brinGetTupleForHeapBlock](../../../../raw/postgres-12/src/backend/access/brin/brin_revmap.c#L179-L311) [brin_tuple.h#BrinTuple](../../../../raw/postgres-12/src/include/access/brin_tuple.h#L49-L89) [brin.c#summarization-placeholder](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L1164-L1200) [brin_revmap.c#leftover-placeholder](../../../../raw/postgres-12/src/backend/access/brin/brin_revmap.c#L397-L405) [brin_internal.h#stored-summary-values](../../../../raw/postgres-12/src/include/access/brin_internal.h#L19-L60)

Build stores one summary per encountered range, including skipped empty ranges and the final accumulated range, and returns the summary count as `index_tuples`. BRIN bulk delete performs no index work at all—there are no per-heap-tuple index entries to remove—and only allocates and returns a zeroed result struct. VACUUM calls summarization with `include_partial = false`; it adds newly summarized ranges and every existing non-NULL reverse-map entry for full ranges without testing the tuple's placeholder bit. Its `reltuples` can therefore count a crash-leftover placeholder while omitting a physically present final partial-range summary.[brin.c#range-build](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L591-L656) [brin.c#brin-build-result](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L658-L743) [brin.c#brinbulkdelete](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L766-L784) [brin.c#brinvacuumcleanup](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L786-L815) [brin.c#brinsummarize-counting](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L1299-L1401) [brin_revmap.c#leftover-placeholder](../../../../raw/postgres-12/src/backend/access/brin/brin_revmap.c#L397-L405)

The final call to `form_and_insert_tuple()` is unconditional, and that call both stores a summary and increments the build counter. A normal build on an empty heap therefore stores one all-empty summary and reports build-time `reltuples = 1`; a later VACUUM can report zero summarized full ranges—its range loop is bounded by the heap's current block count—while that physical item remains.[brin.c#brin-build-final-tuple](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L713-L740) [brin.c#form_and_insert_tuple](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L1403-L1421) [brin.c#brinsummarize-range-loop](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L1325-L1344) [brin.c#brinvacuumcleanup](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L786-L815)

At a stable instant, count dereferenced valid reverse-map TIDs whose tuple is not marked as a placeholder to obtain completed current summaries. Count used regular-page line pointers for every physically present summary or placeholder item. Tuple movement and desummarization atomically update or invalidate the reverse map while marking the old item unused; `PageIndexTupleDeleteNoCompact()` retains the unused line-pointer slot unless it was the last one, but it moves the tuple bytes back into free space and never leaves an extra used summary. Stable count differences therefore indicate placeholders, corruption, or a scan that observed concurrent change, while allocated-byte calculations must still include unused slots and free space. `brin_page_items()` emits one row per indexed attribute, so a multicolumn summary must be counted once by page/item offset, not once per returned row.[brin_tuple.h#BrinTupleIsPlaceholder](../../../../raw/postgres-12/src/include/access/brin_tuple.h#L49-L89) [brin_pageops.c#summary-tuple-move](../../../../raw/postgres-12/src/backend/access/brin/brin_pageops.c#L242-L268) [brin_revmap.c#desummarize](../../../../raw/postgres-12/src/backend/access/brin/brin_revmap.c#L407-L433) [bufpage.c#PageIndexTupleDeleteNoCompact](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L947-L1025) [brinfuncs.c#brin_page_items](../../../../raw/postgres-12/contrib/pageinspect/brinfuncs.c#L206-L317)

`pageinspect` exposes page type, all metapage fields, reverse-map TIDs, and regular-page summary contents. Generic `pgstattuple()` rejects BRIN.[pageinspect--1.5.sql#BRIN-functions](../../../../raw/postgres-12/contrib/pageinspect/pageinspect--1.5.sql#L191-L229) [pgstattuple.c#unsupported-index-AMs](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L312)

#### Contrib Bloom and third-party access methods

Bloom page opaque data stores tuple count `maxoff`, flags, and page ID. Its metapage stores magic, active bounds into the not-full-page array, frozen signature options, and that page-reuse array. It stores no whole-index tuple count.[bloom.h#page-opaque](../../../../raw/postgres-12/contrib/bloom/bloom.h#L31-L79) [bloom.h#metapage-and-tuple](../../../../raw/postgres-12/contrib/bloom/bloom.h#L99-L165)

Each Bloom data tuple contains a heap TID followed by a fixed-size signature. For one particular Bloom index, the exact tuple size is `initBloomState()`'s `sizeOfBloomTuple = BLOOMTUPLEHDRSZ + sizeof(BloomSignatureWord) * bloomLength`, where `BloomSignatureWord` is `uint16` and `bloptions()` has already converted the requested signature `length` from bits to words. Pages store these tuples contiguously without line pointers. A stable full scan can sum `maxoff` on initialized, nondeleted data pages, which is also what VACUUM cleanup does.[blutils.c#initBloomState](../../../../raw/postgres-12/contrib/bloom/blutils.c#L152-L202) [bloom.h#BloomSignatureWord](../../../../raw/postgres-12/contrib/bloom/bloom.h#L80-L83) [blutils.c#Bloom-options](../../../../raw/postgres-12/contrib/bloom/blutils.c#L472-L491) [blutils.c#BloomPageAddItem](../../../../raw/postgres-12/contrib/bloom/blutils.c#L307-L339) [blvacuum.c#Bloom-page-census](../../../../raw/postgres-12/contrib/bloom/blvacuum.c#L163-L216)

Extensions can register arbitrary access-method handlers in `pg_am`. `pg_am` itself stores only the row OID, name, handler OID, and AM type, while `IndexAmRoutine` has build, insert, vacuum, cost, option, property, and scan callbacks but no generic physical-statistics callback. Every third-party AM therefore needs its own disk-format, build-count, vacuum-count, and inspection review.[pg_am.h#FormData_pg_am](../../../../raw/postgres-12/src/include/catalog/pg_am.h#L29-L41) [amcmds.c#CreateAccessMethod](../../../../raw/postgres-12/src/backend/commands/amcmds.c#L37-L113) [amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L163-L233)

### Calculations that are valid

Use names that expose the numerator and denominator:

| Quantity | Formula | Interpretation |
| --- | --- | --- |
| Catalog-estimated main-fork bytes | `relpages * current_setting('block_size')::bigint` | Bytes implied by the last stored block count. It can be stale.[pg_class.h#relpages](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L59-L66) [guc.c#block_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2879-L2888) |
| Current main-fork logical bytes | `pg_relation_size(index_oid, 'main')` | Sum of current segment-file `st_size`; includes every main-fork page, not only tuple payload.[dbsize.c#calculate_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L266-L308) |
| Current main-fork pages | `pg_relation_size(index_oid, 'main') / current_setting('block_size')::bigint` | Current logical main-fork length in PostgreSQL blocks. `block_size` is a preset GUC and is reachable from SQL only through `current_setting()`.[dbsize.c#calculate_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L266-L308) [guc.c#block_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2879-L2888) |
| Current all-fork logical bytes | `pg_table_size(index_oid)` | Main plus FSM, VM, and init forks for that index.[dbsize.c#calculate_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L380-L408) |
| Allocated main bytes per catalog unit | `pg_relation_size(index_oid, 'main') / NULLIF(reltuples, 0)` | A trend ratio only. The denominator can mean build items, estimated rows, or an AM cleanup unit. Never label it tuple width.[index.c#index-build-statistics](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2989) [analyze.c#index-relstats-update](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629) [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1771-L1815) |
| B-tree/hash average non-`LP_DEAD` data-item payload | `tuple_len::numeric / NULLIF(tuple_count, 0)` | Average stored item length from B-tree leaf items or hash bucket/overflow items. It sums `lp_len`, which both AMs set from an already-`MAXALIGN`ed `IndexTupleSize()`, so it *includes* each item's own alignment padding. It excludes the four-byte line pointer, page header, special space, routing/meta pages, and free space. Cast to `numeric`: every `pgstattuple` count and length column is `bigint`, so an uncast division truncates.[pgstattuple.c#B-tree-page-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L406-L448) [pgstattuple.c#hash-page-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L450-L490) [pgstattuple.c#pgstat_index_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L564-L590) [indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L126-L188) [pgstattuple--1.4--1.5.sql#pgstattuple-regclass-result](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L61-L72) |
| B-tree/hash average payload over all stored data items | `(tuple_len + dead_tuple_len)::numeric / NULLIF(tuple_count + dead_tuple_count, 0)` | Includes `LP_DEAD` item bodies but still excludes shared overhead.[pgstattuple.c#pgstat_index_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L564-L590) [bufpage.h#page-layout](../../../../raw/postgres-12/src/include/storage/bufpage.h#L22-L75) |
| B-tree/hash allocated main bytes per stored data item | `table_len::numeric / NULLIF(tuple_count + dead_tuple_count, 0)` | Whole-main-fork allocation per scanned B-tree leaf or hash bucket/overflow item, including metadata, routing pages, free space, and reusable/deleted pages. It is an average share, not the item's own size.[pgstattuple.c#pgstat_index](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L520-L562) |
| BRIN allocated main bytes per completed current summary | `main_bytes / NULLIF(nonplaceholder_valid_revmap_TIDs, 0)` | Average allocation per completed summarized range. Each valid TID must be dereferenced and placeholders excluded; the result does not measure heap rows or tuple payload.[brin_revmap.c#brinGetTupleForHeapBlock](../../../../raw/postgres-12/src/backend/access/brin/brin_revmap.c#L179-L311) [brin_tuple.h#BrinTupleIsPlaceholder](../../../../raw/postgres-12/src/include/access/brin_tuple.h#L49-L89) [brin_tuple.h#BRIN-tuple-purpose](../../../../raw/postgres-12/src/include/access/brin_tuple.h#L18-L30) |
| SP-GiST allocated main bytes per represented heap TID | `main_bytes / NULLIF(live_leaf_count, 0)` | Requires a custom stable page scan. It includes three fixed pages, routing/dead objects, and reusable space.[spgist_private.h#fixed-pages](../../../../raw/postgres-12/src/include/access/spgist_private.h#L25-L34) [spgist_private.h#leaf-tuples](../../../../raw/postgres-12/src/include/access/spgist_private.h#L307-L372) [spgvacuum.c#vacuumLeafPage](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L105-L168) |
| Bloom tuple payload | `BLOOMTUPLEHDRSZ + sizeof(BloomSignatureWord) * bloomLength` | Exact for each tuple in one Bloom index; whole-file allocation per tuple still requires the data-page `maxoff` census.[bloom.h#BloomTuple](../../../../raw/postgres-12/contrib/bloom/bloom.h#L137-L165) [blutils.c#initBloomState](../../../../raw/postgres-12/contrib/bloom/blutils.c#L199-L202) |

For GIN, no single denominator is honest. Report separate figures such as bytes per entry key, bytes per posting association, bytes per pending heap tuple, or bytes per distinct referenced heap TID, and state exactly how each count was obtained. The metapage can supply `nEntries` and `nPendingHeapTuples`, subject to the build/VACUUM and unit caveats above; its aggregates cannot produce a total posting-association count or a distinct referenced-TID count.[ginblock.h#GinMetaPageData](../../../../raw/postgres-12/src/include/access/ginblock.h#L54-L100) [ginblock.h#posting-lists-and-trees](../../../../raw/postgres-12/src/include/access/ginblock.h#L218-L344)

For logical **visible rows**, obtain a separate heap-side count under a declared snapshot and apply the partial predicate and AM-specific omission rules. That result measures bytes allocated per visible qualifying row, not physical index tuples: an index can retain entries for dead heap versions, and a HOT chain can let one index entry lead to several heap versions.[heapam_handler.c#index-build-visibility](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L1387-L1428) [README.HOT#HOT-index-entries](../../../../raw/postgres-12/src/backend/access/heap/README.HOT#L34-L55)

### Catalog inventory SQL

This read-only inventory returns catalog estimates, actual logical fork lengths, definition/state fields that affect interpretation, and a deliberately cautious allocation ratio. It includes metadata-only partitioned roots but does not call size functions for them.

`statement_timeout` and `lock_timeout` are `PGC_USERSET` settings in PostgreSQL 12. They need neither restart nor reload and can be set for a session or transaction. The snippet uses `SET LOCAL`, so both changes last only for this transaction.[guc.c#statement-and-lock-timeouts](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2397)

```sql
BEGIN /* wiki_index_physical_inventory */;

SET /* wiki_index_physical_inventory_statement_timeout */ LOCAL
    statement_timeout = '30s';
SET /* wiki_index_physical_inventory_lock_timeout */ LOCAL
    lock_timeout = '1s';

SELECT /* wiki_index_physical_inventory */
       n.nspname AS index_schema,
       c.relname AS index_name,
       tn.nspname AS table_schema,
       t.relname AS table_name,
       am.amname,
       c.relkind,
       c.relpersistence,
       c.relfilenode,
       c.reltablespace,
       c.reloptions,
       i.indnatts,
       i.indnkeyatts,
       i.indisvalid,
       i.indisready,
       i.indislive,
       i.indpred IS NOT NULL AS is_partial,
       i.indexprs IS NOT NULL AS has_expressions,
       c.relpages,
       c.reltuples,
       c.relallvisible,
       current_setting('block_size')::bigint AS block_size_bytes,
       CASE WHEN c.relkind = 'i'
            THEN c.relpages::bigint
                 * current_setting('block_size')::bigint
       END AS catalog_main_bytes_estimate,
       CASE WHEN c.relkind = 'i'
            THEN pg_relation_size(c.oid, 'main')
       END AS current_main_bytes,
       CASE WHEN c.relkind = 'i'
            THEN pg_relation_size(c.oid, 'fsm')
       END AS current_fsm_bytes,
       CASE WHEN c.relkind = 'i'
            THEN pg_relation_size(c.oid, 'vm')
       END AS current_vm_bytes,
       CASE WHEN c.relkind = 'i'
            THEN pg_relation_size(c.oid, 'init')
       END AS current_init_bytes,
       CASE WHEN c.relkind = 'i'
            THEN pg_table_size(c.oid)
       END AS current_all_forks_bytes,
       CASE WHEN c.relkind = 'i' AND c.reltuples > 0
            THEN pg_relation_size(c.oid, 'main')::numeric
                 / c.reltuples::numeric
       END AS allocated_main_bytes_per_catalog_count,
       pg_get_expr(i.indpred, i.indrelid) AS partial_predicate
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_am AS am ON am.oid = c.relam
JOIN pg_index AS i ON i.indexrelid = c.oid
JOIN pg_class AS t ON t.oid = i.indrelid
JOIN pg_namespace AS tn ON tn.oid = t.relnamespace
WHERE c.relkind IN ('i', 'I')
ORDER BY n.nspname, c.relname;

COMMIT /* wiki_index_physical_inventory */;
```

The `relpages * block_size` column and current size columns answer different questions. The former preserves the last catalog sample; the latter reads file lengths now. The ratio intentionally keeps the name `catalog_count` because the query cannot discover which operation last established its unit.[pg_class.h#physical-relstats](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L59-L66) [dbsize.c#pg_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L310-L336)

Cost note: `pg_relation_size()` and `pg_table_size()` are both volatile, so every one of the five size calls runs per row, each opening the relation under `AccessShareLock` and `stat()`ing its segment files; `pg_table_size()` re-stats the same four forks the individual calls already measured. On an installation with many indexes, add a schema or index filter to the `WHERE` clause, or drop the `pg_table_size()` column and add the four fork columns instead.[pg_proc.dat#pg_relation_size](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L6888-L6891) [pg_proc.dat#pg_table_size](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L6908-L6911) [dbsize.c#calculate_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L380-L408)

### B-tree and hash physical data-item SQL

With `pgstattuple` 1.5 installed and the caller granted its `regclass` function, this query is suitable only for a B-tree or hash index. Replace `public.index_name`; do not use this calculation for GiST in PostgreSQL 12 because of the pinned-source defects above.[pgstattuple--1.4--1.5.sql#pgstattuple-regclass](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L61-L75) [pgstattuple.c#index-AM-dispatch](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L312)

```sql
BEGIN /* wiki_index_data_item_accounting */;

SET /* wiki_index_data_item_accounting_statement_timeout */ LOCAL
    statement_timeout = '5min';
SET /* wiki_index_data_item_accounting_lock_timeout */ LOCAL
    lock_timeout = '1s';

SELECT /* wiki_index_data_item_accounting */
       s.table_len AS main_fork_bytes,
       s.tuple_count AS non_lp_dead_data_items,
       s.dead_tuple_count AS lp_dead_data_items,
       s.tuple_len AS non_lp_dead_payload_bytes,
       s.dead_tuple_len AS lp_dead_payload_bytes,
       CASE WHEN s.tuple_count > 0
            THEN s.tuple_len::numeric / s.tuple_count
       END AS avg_non_lp_dead_item_payload_bytes,
       CASE WHEN s.tuple_count + s.dead_tuple_count > 0
            THEN (s.tuple_len + s.dead_tuple_len)::numeric
                 / (s.tuple_count + s.dead_tuple_count)
       END AS avg_all_item_payload_bytes,
       CASE WHEN s.tuple_count + s.dead_tuple_count > 0
            THEN s.table_len::numeric
                 / (s.tuple_count + s.dead_tuple_count)
       END AS allocated_main_bytes_per_stored_data_item
FROM pgstattuple('public.index_name'::regclass) AS s;

COMMIT /* wiki_index_data_item_accounting */;
```

The extension's output calls the first category “live tuples,” but the implementation tests only `ItemIdIsDead()`. Interpret it as non-`LP_DEAD` physical items, not as a visibility-qualified row count.[pgstattuple--1.4--1.5.sql#pgstattuple-regclass-result](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L61-L72) [pgstattuple.c#pgstat_index_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L564-L590)

### Consistency, cost, and privilege limits

`pg_relation_size()` acquires `AccessShareLock`, which does not block ordinary DML. Its file-length numerator and the lazily maintained catalog denominator are not one atomic census.[dbsize.c#pg_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L310-L336) [mvcc.sgml#table-lock-conflicts](../../../../raw/postgres-12/doc/src/sgml/mvcc.sgml#L849-L907)

For an index, `pgstattuple()` scans the AM-selected page range to the repeatedly checked current end of the main fork: B-tree and hash start after their metapages, while the flawed GiST path starts after its root. Only `table_len` reports the final whole-fork block length. The function takes page locks while inspecting each selected page, and it momentarily takes the relation-extension lock in `ExclusiveLock` mode every time it re-reads the fork length, but no index-wide snapshot prevents inserts, splits, cleanup, or extension during the scan. Treat a result collected under concurrent maintenance or DML as a moving physical observation.[pgstattuple.c#index-AM-dispatch](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L283) [pgstattuple.c#pgstat_index](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L520-L562)

`pageinspect.get_raw_page()` copies one separately locked page at a time. A multi-page query built from it is not a whole-index consistent snapshot unless the caller separately excludes changes. It reads raw storage and requires superuser: any other role gets `ERRCODE_INSUFFICIENT_PRIVILEGE`. It also rejects a partitioned index outright, so `relkind = 'I'` rows cannot be inspected this way.[rawpage.c#get_raw_page_internal](../../../../raw/postgres-12/contrib/pageinspect/rawpage.c#L94-L171)

Version 1.5 of `pgstattuple` revokes public execution and grants its inspection functions to `pg_stat_scan_tables`; these functions can still generate substantial sequential I/O. Use a maintenance window for a stable census and bound production runs with transaction-local timeouts.[pgstattuple--1.4--1.5.sql#privileges](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L19-L45) [pgstattuple--1.4--1.5.sql#regclass-privileges](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L61-L100)

### Planner, caller-callee, and generated-build boundaries

The normal write path computes index attributes in `ExecInsertIndexTuples()` and calls the selected AM's insert callback through `index_insert()`. Build and maintenance use the same boundary: common code calls `ambuild`, `ambulkdelete`, and `amvacuumcleanup`; the AM returns transient statistics; common catalog code decides whether to persist them.[execIndexing.c#ExecInsertIndexTuples](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L355-L405) [index.c#FormIndexDatum](../../../../raw/postgres-12/src/backend/catalog/index.c#L2578-L2652) [amapi.h#IndexAmRoutine-callbacks](../../../../raw/postgres-12/src/include/access/amapi.h#L209-L233) [index.c#ambuild-call](../../../../raw/postgres-12/src/backend/catalog/index.c#L2899-L2904) [vacuumlazy.c#lazy_vacuum_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1735-L1769) [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1771-L1815)

The planner does not treat an ordinary index's own `reltuples` as a physical entry count. For a nonpartial index it takes current blocks and sets index tuples equal to the parent table estimate. For a partial index it calls `estimate_rel_size()`, which scales the index's old tuple/page density to current pages and clamps the result to the parent estimate; when the recorded page count is zero it instead invents a density from attribute widths and relies on that same clamp. That source path calls its one-metapage subtraction "a kluge because it assumes more than it ought to about index structure," currently "OK for btree, hash, and GIN indexes but suspect for GiST indexes."[plancat.c#get_relation_info-index-size](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L407) [plancat.c#estimate_rel_size-metapage-kluge](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L984-L998) [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L955-L1027)

`pg_class.h`, `pg_index.h`, and `pg_am.h` are catalog inputs. The build generates `_d.h` definitions and bootstrap catalog artifacts from those inputs and `.dat` rows; generated headers add no hidden per-index physical-statistics catalog.[pg_class.h#catalog-input](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L12-L29) [pg_index.h#catalog-input](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L12-L29) [catalog/Makefile#generated-catalog-inputs](../../../../raw/postgres-12/src/backend/catalog/Makefile#L28-L69) [catalog/Makefile#catalog-generation](../../../../raw/postgres-12/src/backend/catalog/Makefile#L71-L101)

### Tests and explicit test gaps

PostgreSQL 12 regression tests exercise GIN pending-list cleanup, SP-GiST VACUUM paths, and BRIN summarize/desummarize behavior. `pageinspect` has direct B-tree, hash, GIN, and BRIN tests. The `pgstattuple` regression file calls generic `pgstattuple()` on the heap and separately exercises `pgstatindex()`, `pgstatginindex()`, and `pgstathashindex()`. Its only index argument to generic `pgstattuple()` is the partitioned-index root `test_partitioned_index`, an expected-failure case; the file never calls generic `pgstattuple()` on a B-tree, hash, or GiST index that has storage, and it creates no GiST index at all.[gin.sql#pending-list-tests](../../../../raw/postgres-12/src/test/regress/sql/gin.sql#L7-L36) [spgist.sql#vacuum-tests](../../../../raw/postgres-12/src/test/regress/sql/spgist.sql#L7-L31) [brin.sql#summarize-tests](../../../../raw/postgres-12/src/test/regress/sql/brin.sql#L406-L449) [pageinspect/Makefile#regression-tests](../../../../raw/postgres-12/contrib/pageinspect/Makefile#L3-L15) [pgstattuple.sql#extension-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L119) [pgstattuple.sql#partitioned-index-failure](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L66-L70) [pgstattuple.out#partitioned-index-error](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L156-L160)

No cross-AM `pg_class.reltuples` lifecycle assertion, catalog-derived bytes-per-item formula, SP-GiST/Bloom `pageinspect` decoder, or direct one-page/deleted-page GiST `pgstattuple()` case was found in the reviewed test and contrib inspection scope. The `contrib/bloom` regression file exercises scans, `VACUUM`, `amvalidate`, and reloptions, but never inspects a page. The one `reltuples` isolation spec in the checkout is heap-only.[pageinspect/Makefile#regression-tests](../../../../raw/postgres-12/contrib/pageinspect/Makefile#L3-L15) [pgstattuple.sql#extension-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L119) [bloom.sql#bloom-regression-scope](../../../../raw/postgres-12/contrib/bloom/sql/bloom.sql#L1-L95) [vacuum-reltuples.spec#heap-only-reltuples](../../../../raw/postgres-12/src/test/isolation/specs/vacuum-reltuples.spec#L1-L48)

### What an isolated 12.2 server measured

A 12.2 server built from this pin ran the script in [Measurement Script](#measurement-script) on 2026-09-10. Every number below is what that build did; the reason for each is still the same-version source citation beside it.

The fixture is one index per access method on `fx_units`, built at 100,000 rows and then reduced by `DELETE ... WHERE id % 4 = 0`, leaving 75,000 live rows, 60,000 non-NULL hash keys, 5,000 rows satisfying the partial predicate `id % 10 = 0`, and a 1,703-page heap.

#### Catalog counters

`pg_class.reltuples`, in the order the writers ran:

| Index | AM | Build | `ANALYZE` | `VACUUM` | `VACUUM` after delete | `ANALYZE` after delete | `VACUUM ANALYZE` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ix_bt` | btree | 100000 | 100000 | 100000 | 75000 | 75000 | 75000 |
| `ix_hash` | hash | **80000** | **100000** | 100000 | **60000** | 75000 | 75000 |
| `ix_gist` | gist | 100000 | 100000 | 100000 | 75000 | 75000 | 75000 |
| `ix_gin` | gin | **300000** | **100000** | 100000 | 75000 | 75000 | 75000 |
| `ix_spg` | spgist | 100000 | 100000 | 100000 | 75000 | 75000 | 75000 |
| `ix_brin` | brin | **14** | **100000** | **13** | **13** | **75000** | **13** |
| `ix_bloom` | bloom | 100000 | 100000 | 100000 | 75000 | 75000 | 75000 |
| `ix_part` (partial) | btree | 10000 | 10237 | 10000 | 5000 | 4873 | 4873 |

Readings:

- Three writers, three units, one BRIN index: 14 summaries from the build, the 100,000-row table estimate from `ANALYZE`, and 13 full-range summaries from `VACUUM`. The heap is 1,703 pages at `pages_per_range = 128`, so `ceil(1703 / 128) = 14` ranges exist and block 2 holds 14 summary items; the build's unconditional final `form_and_insert_tuple()` supplies the fourteenth, and `include_partial = false` is why `VACUUM` reports 13.[brin.c#brin-build-final-tuple](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L713-L740) [brin.c#brinsummarize-counting](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L1299-L1401)
- `VACUUM ANALYZE` leaves 13, not 75,000: the `ANALYZE` half skips index relstats when it runs inside a `VACUUM`.[analyze.c#index-relstats-update](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629)
- Hash counts 80,000 at build (the non-NULL keys) and then accepts 100,000 from a nonpartial-index `ANALYZE`, which is the whole-table estimate.[hashutil.c#hash-NULL-omission](../../../../raw/postgres-12/src/backend/access/hash/hashutil.c#L312-L343) [analyze.c#index-relstats-update](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629)
- GIN counts 300,000 at build. That is the extracted-key sum: three distinct array elements per row over 100,000 rows. `VACUUM` then substitutes the heap count.[gininsert.c#gin-build-count](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L245-L288) [ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L686-L731)
- The partial index is exact after a build (10000) and an estimate after `ANALYZE` (10237, then 4873 against 5,000 actual rows), because `ANALYZE` scales the sampled predicate-passing fraction.[analyze.c#partial-index-sample](../../../../raw/postgres-12/src/backend/commands/analyze.c#L714-L822)
- `relallvisible` is 0 on all 17 fixture indexes.[index.c#index-relallvisible](../../../../raw/postgres-12/src/backend/catalog/index.c#L2761-L2785)
- BRIN on a heap with no rows: `relpages = 3` (metapage, revmap page, one regular page), `reltuples = 1` after the build, `reltuples = 0` after `VACUUM`, and the one non-placeholder summary item is still on block 2 afterwards.[brin.c#brin-build-final-tuple](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L713-L740) [brin.c#brinsummarize-range-loop](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L1325-L1344)

#### Metapage counters

- B-tree: `btm_last_cleanup_num_heap_tuples` reads `-1` on a freshly built index and `74961` after one `VACUUM` of its table — the heap estimate that `VACUUM` passed in, not the index's own `reltuples` of `75000`, and not the 75,000 live rows.[nbtpage.c#metapage-initialization](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L47-L77) [nbtpage.c#_bt_update_meta_cleanup_info](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L150-L226)
- Hash: `hashm_ntuples = 60000` after `VACUUM`, matching `pgstathashindex()`'s 60,000 live items, while the same index's `pg_class.reltuples` says 75,000. The metapage counter and the catalog estimate are different quantities at the same instant.[hash.c#hashbulkdelete](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L444-L633) [pgstatindex.c#pgstathashindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L575-L727)
- GIN pending list, `fastupdate = on`, after 50 inserts of three array elements each: `n_pending_tuples = 50`, and the single pending page's `maxoff` is also 50 with flags `{list,list_fullrow}` — heap-tuple groups, not the 150 temporary index tuples those rows produced. After the next `VACUUM` cleans the list, pending drops to 0 and `nEntries` moves from 150 to 300, the physically recounted entry-leaf items.[ginfast.c#ginHeapTupleFastCollect](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L464-L542) [ginfast.c#nPendingHeapTuples-increment](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L368-L373) [ginvacuum.c#GIN-entry-page-census](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L746-L781)
- That same `VACUUM` left the GIN index's `reltuples` at its build value of 225,000, because the heap scan skipped all-visible pages, so `estimated_count` was true and nothing was written.[vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1771-L1815)
- BRIN metapage: `pagesperrange = 128`, `lastrevmappage = 1`; the one revmap page holds 1,360 slots of which 14 are valid TIDs and 1,346 are `(0,0)`. `brinGetStats()` would derive `revmapNumPages = 0` from that metapage; see `## Open Questions`.[brin_page.h#metapage-and-revmap](../../../../raw/postgres-12/src/include/access/brin_page.h#L63-L94) [brin.c#brinGetStats](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L1089-L1108)
- `brin_page_items()` on the two-column BRIN returns 14 rows for 7 physical items, exactly two per item.[brinfuncs.c#brin_page_items](../../../../raw/postgres-12/contrib/pageinspect/brinfuncs.c#L206-L317)
- Bloom: `{length=80,col1=4,col2=4}` is 5 signature words, so `BLOOMTUPLEHDRSZ + 2 * 5 = 16` bytes per tuple and `(8192 - 24 - 8) / 16 = 510` tuples per page. For 100,000 rows that predicts `ceil(100000 / 510) + 1 = 198` pages, and `relpages` is 198.[blutils.c#initBloomState](../../../../raw/postgres-12/contrib/bloom/blutils.c#L199-L202) [blutils.c#Bloom-options](../../../../raw/postgres-12/contrib/bloom/blutils.c#L472-L491) [bloom.h#BloomTuple](../../../../raw/postgres-12/contrib/bloom/bloom.h#L137-L165)

#### The GiST gaps, quantified

- A GiST index whose block zero is both root and leaf: 1 page, 5 indexed rows, and `pgstattuple()` returns `table_len = 8192` with `tuple_count = 0`, `tuple_len = 0` and `free_space = 0`. The dispatcher starts the scan at `GIST_ROOT_BLKNO + 1`, so it never looks at the only page there is.[pgstattuple.c#GiST-dispatch](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L283)
- A 2,242-page GiST index reduced from 200,000 rows to 10,000 by `DELETE` and two `VACUUM`s: `pgstattuple()` reports `tuple_count = 10042`, an overcount of 42. A page census read out of the raw page trailer explains it exactly — 2,181 live leaf pages carrying 10,000 line pointers, 40 internal pages (not counted), and 21 pages that are marked both `F_LEAF` and `F_DELETED`. `GistPageSetDeleted()` sets `pd_lower` to `MAXALIGN(24) + 8 = 32` on a deleted page, so `PageGetMaxOffsetNumber()` reads two line pointers there, and `2 * 21 = 42`.[pgstattuple.c#pgstat_gist_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L492-L518) [gist.h#deleted-page-layout](../../../../raw/postgres-12/src/include/access/gist.h#L160-L183) [gist.h#GISTPageOpaqueData](../../../../raw/postgres-12/src/include/access/gist.h#L41-L82)
- Those 21 deleted pages neither shrank the file (`relpages` stayed 2,242 and the main fork stayed 18,366,464 bytes) nor appeared in the free space map: the FSM fork is 0 bytes and all 2,242 pages report `pg_freespace = 0`. `gistvacuumscan()` records a deleted page only once `gistPageRecyclable()` is true, and vacuums the index FSM only when it found at least one such page.[gistvacuum.c#empty-page-unlink-count](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c#L465-L584) [gistvacuum.c#GistPageSetDeleted](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c#L651-L683)

#### Which inspection path accepts what

| Call | Outcome on 12.2 |
| --- | --- |
| `pgstattuple('ix_bt')`, `('ix_hash')`, `('ix_gist')` | accepted: 75050, 60050 and 75050 items |
| `pgstattuple('ix_part')`, `pgstattuple(<leaf index of a partitioned table>)` | accepted: 5005 and 999 items |
| `pgstattuple('ix_gin')` / `('ix_spg')` / `('ix_brin')` | `ERROR: "..." (gin index / spgist index / brin index) is not supported` |
| `pgstattuple('ix_bloom')` | `ERROR: "ix_bloom" (unknown index) is not supported` |
| `pgstattuple('ix_parted')` | `ERROR: "ix_parted" (partitioned index) is not supported` |
| `pgstatindex('ix_hash')` | `ERROR: relation "ix_hash" is not a btree index` |
| `pgstathashindex('ix_bt')` | `ERROR: relation "ix_bt" is not a hash index` |
| `pgstatginindex('ix_bt')` | `ERROR: relation "ix_bt" is not a GIN index` |
| `pg_relpages('ix_spg')` | accepted: 607 |
| `pg_relpages('ix_parted')` | `ERROR: "ix_parted" is not a table, index, materialized view, sequence, or TOAST table` |
| `get_raw_page('ix_parted', 0)` | `ERROR: cannot get raw page from partitioned index "ix_parted"` |

Bloom lands in the `default:` arm because its AM OID is not one of the six bootstrapped ones, and the installed `pageinspect` 1.7 exposes decoders for B-tree, hash, GIN, BRIN, heap and generic pages only — no GiST, SP-GiST or Bloom function exists to call.[pgstattuple.c#index-AM-dispatch](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L312) [pg_am.dat#core-index-access-methods](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L35) [pageinspect/Makefile#modules-and-tests](../../../../raw/postgres-12/contrib/pageinspect/Makefile#L3-L15)

Privileges, from a plain login-less role with `SELECT` on the table: `pgstattuple`, `pgstatindex` and `pg_freespace` all fail with `permission denied for function`, `get_raw_page` fails with `must be superuser to use raw page functions`, and `pg_relation_size` succeeds. After `GRANT pg_stat_scan_tables`, `pgstattuple` and `pgstatindex` succeed while `get_raw_page` still refuses. All nine installed `pgstattuple` functions carry `{owner=X/owner,pg_stat_scan_tables=X/owner}`.[pgstattuple--1.4--1.5.sql#regclass-privileges](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L61-L100) [rawpage.c#get_raw_page_internal](../../../../raw/postgres-12/contrib/pageinspect/rawpage.c#L94-L171)

#### Item bytes, padding and high keys

| Index | Key | Items | `tuple_len` | Bytes per item | `MAXALIGN(8 + stored datum)` |
| --- | --- | --- | --- | --- | --- |
| `ix_pad5` | `text` `'abcde'` | 20000 | 320000 | 16.0 | `MAXALIGN(8 + 1 + 5) = 16` |
| `ix_pad9` | `text` `'abcdefghi'` | 20000 | 480000 | 24.0 | `MAXALIGN(8 + 1 + 9) = 24` |
| `ix_padint` | `int4` | 20000 | 320000 | 16.0 | `MAXALIGN(8 + 4) = 16` |

`pgstattuple`'s payload therefore includes each item's own alignment padding, and `bt_page_items()` agrees item by item: leaf page 2 of `ix_pad5` holds 366 items of 16 bytes plus one 24-byte item, and of `ix_padint` 367 items of 16 bytes. `pg_column_size('abcde'::text)` is 9, which is *not* the width to use — the index tuple stores the short 1-byte varlena header.[indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L126-L188) [pgstattuple.c#pgstat_index_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L564-L590)

High keys are the reason the two item counts differ: over `ix_pad5`'s 55 leaf pages `bt_page_stats()` sums 20,054 live items while `pgstattuple()` reports 20,000, and the 54-item gap is exactly the 54 non-rightmost leaf pages. One leaf page shows the shared overhead directly: 367 items, `avg_item_size = 16`, 1,468 bytes of line pointers, and 800 bytes still free.[nbtree.h#high-key](../../../../raw/postgres-12/src/include/access/nbtree.h#L198-L219) [pgstattuple.c#pgstat_btree_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L406-L448) [itemid.h#ItemIdData](../../../../raw/postgres-12/src/include/storage/itemid.h#L20-L41)

#### Sizes, forks and the free space map

- A B-tree index has only a main fork here: `main = 2260992`, `fsm = 0`, `vm = 0`, `init = 0`, `pg_table_size = 2260992`, `pg_total_relation_size = 2260992`, and `pg_indexes_size = 0`. A fifth fork name fails with `ERROR: invalid fork name` plus a hint naming exactly `main`, `fsm`, `vm` and `init`.[dbsize.c#calculate_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L380-L408) [dbsize.c#calculate_indexes_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L410-L448) [relpath.c#forkNames](../../../../raw/postgres-12/src/common/relpath.c#L26-L64)
- The stale-catalog gap, on one index whose file never stops growing: after the build, `relpages = 139` and the file is 1,138,688 bytes; after 150,000 more rows with no `ANALYZE`, `relpages` is still 139 and `reltuples` still 50,000 while the file is 4,513,792 bytes and `pg_relpages()` already reports 551. `main_bytes / reltuples` reads **90.28** at that moment and **22.57** immediately after `ANALYZE`, with the file byte-identical between the two readings.[pg_class.h#physical-relstats](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L59-L66) [pgstatindex.c#pg_relpages_v1_5](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L406-L428) [analyze.c#index-relstats-update](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629)
- The same ratio across access methods at one instant: bloom 21.61, brin 1890.46, btree 30.15, partial btree 50.43, gin 12.23, gist 129.02, hash 56.14, spgist 66.26 bytes per catalog count. The denominators are not the same kind of thing.[index.c#index-build-statistics](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2989)
- Index FSM entries are whole-page availability, quantized: a B-tree with 816 `VACUUM`-reclaimed pages out of 825 reports `pg_freespace = 8160` on every one of them and 0 on the rest, because `RecordFreeIndexPage()` writes `BLCKSZ - 1` and the FSM stores category 255, whose lower bound is 8,160 bytes. The two-column BRIN instead reports 7,936 on its one regular page — actual free space, quantized the same way.[indexfsm.c#index-FSM-implementation](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L32-L73) [freespace.c#FSM-quantization](../../../../raw/postgres-12/src/backend/storage/freespace/freespace.c#L379-L416)
- FSM forks exist for the B-tree, GIN, SP-GiST and BRIN fixtures (24,576 bytes each) and are absent for hash, Bloom and the GiST index. Hash's own availability map is the metapage's `mapp[]`, which here names one bitmap page at block 513.[hash.h#overflow-bitmaps](../../../../raw/postgres-12/src/include/access/hash.h#L201-L228) [hash.h#bitmap-pages](../../../../raw/postgres-12/src/include/access/hash.h#L287-L307)

#### Both filed SQL snippets, as filed

The catalog-inventory block runs unmodified and returns 180 rows over its 29 columns, with the partitioned-index root `ix_parted` present as `relkind = 'I'`, `relfilenode = 0` and NULL in every size column. The B-tree/hash block fails unmodified with `ERROR: relation "public.index_name" does not exist`, which is the placeholder the surrounding text tells the reader to replace, and succeeds against each B-tree and hash fixture once only that name is substituted.[pgstattuple--1.4--1.5.sql#pgstattuple-regclass](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L61-L75) [pg_class.h#relation-kinds-and-storage](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L152-L192)

## Measurement Script

Every number in [What an isolated 12.2 server measured](#what-an-isolated-122-server-measured) comes from the one script below. Re-run it rather than writing a second one; edit it in place when a fixture, statement or threshold changes, and re-run it before filing new numbers.

### Usage

| Item | Detail |
| --- | --- |
| Purpose | measures the catalog and metapage counters, `pgstattuple`/`pageinspect`/`pg_freespacemap` dispatch and privileges, item widths, fork sizes and FSM contents that this page reports, and executes both of the page's own fenced SQL blocks against the pinned build |
| Invocation | `bash physidx_stats_v12.sh [stage ...]`, run from the repository root (it reads `wiki/…/physical-index-statistics-tuple-counts-and-bytes.md` and `raw/postgres-12/` relative to `$PWD`) |
| Stages | `build check cluster fixtures inventory dataitem reltuples ampages gistgap dispatch padding sizes fsm privs report`, in that default order; `stop` and `clean` tear the sandbox down and are not in the default order |
| Environment | `WIKI_ROOT` (`$PWD`), `PAGE` (this page's path under `$WIKI_ROOT`), `SRC12` (`$WIKI_ROOT/raw/postgres-12`), `SANDBOX` (`$WIKI_ROOT/.wiki-runtime/tmp/physidx-measure`), `PORT12` (`55432`), `JOBS` (`8`), `EXTRA_CFLAGS` (`-O2 -g`), `KEEP` (`0`; `1` makes `clean` a no-op) |
| Prerequisites | a C toolchain and GNU make; readline and zlib development headers, because `build` configures `--with-readline --with-zlib --enable-debug`; the pinned checkout at `SRC12`; `initdb --locale=C --encoding=UTF8`, which the fixtures assume; the `pgstattuple`, `pageinspect`, `pg_freespacemap` and `bloom` contrib modules, which `build` installs |
| Output | one file per stage under `$SANDBOX/out/`; read `platform.txt` first, then `reltuples.txt`. `inventory.txt` and `dataitem.txt` also record the SHA-256 of the page block they executed |
| Runtime | wall clock on the review host with `JOBS=8`: roughly 4 to 5 minutes for `build` plus `cluster` from an empty sandbox, 1 to 2 minutes for every measuring stage together from an existing tree, and about 2 minutes for `check`. A full default order from nothing is therefore about 6 minutes |
| Cleanup | `bash physidx_stats_v12.sh stop clean` stops the server with `pg_ctl -m fast -w stop`, refuses to continue if `postmaster.pid` survives or a matching process is still running, and then deletes `$SANDBOX` |

### Stages

| Stage | What it does | Needs |
| --- | --- | --- |
| `build` | configures 12.2 out of tree under `$SANDBOX/build`, installs into `$SANDBOX/install`, then builds and installs the four contrib modules; skips everything when the binary already exists, and copies `configure.log`, `make.log` and `install.log` into `out/` on the failure path too | nothing |
| `check` | runs `make check` for the engine and for each of the four contrib modules, writes a one-line verdict per suite into `out/checks.txt`, and copies the logs and any `regression.diffs` | `build` |
| `cluster` | `initdb --locale=C --encoding=UTF8`, writes the cluster settings below, starts on `PORT12`, creates the `physidx` database and the four extensions, and records the platform facts into `out/platform.txt` | `build` |
| `fixtures` | creates the disposable fixture tables and one index per access method, plus the empty-heap BRIN, the single-page GiST, the page-deleting GiST, the three fixed-width B-trees, the partitioned pair, the two-column BRIN and the snapshot table | `cluster` |
| `inventory` | extracts the page's first fenced `sql` block and runs it unmodified | `fixtures` |
| `dataitem` | extracts the second fenced `sql` block, runs it unmodified, then re-runs it per index with only `public.index_name` substituted | `fixtures` |
| `reltuples` | rebuilds, analyzes, vacuums, deletes a quarter of the rows and repeats, snapshotting `pg_class` after each writer; also measures the empty-heap BRIN and the GIN and BRIN arithmetic | `fixtures` |
| `ampages` | reads the B-tree, hash, GIN and BRIN metapages, the GIN pending list before and after cleanup, the reverse map, `brin_page_items()` per attribute, and the Bloom width arithmetic | `reltuples` |
| `gistgap` | measures the single-page GiST, then deletes 95 % of the other GiST fixture's rows, vacuums twice, and censuses the pages by reading `F_LEAF`/`F_DELETED` out of the raw page trailer | `fixtures` |
| `dispatch` | calls every inspection function on every access method and records the exact refusals | `fixtures` |
| `padding` | compares `pgstattuple` payloads, `bt_page_items()` item lengths, the predicted `MAXALIGN` widths, and the high-key gap | `fixtures` |
| `sizes` | reads all four forks and the size functions, then builds a deliberately stale index to contrast catalog estimate, `pg_relpages()` and file length | `fixtures` |
| `fsm` | builds a B-tree whose pages `VACUUM` reclaims and reads `pg_freespace` for it, for BRIN, and for every fixture's FSM fork; also reads the hash metapage's bitmap-page list | `fixtures` |
| `privs` | creates a plain role, records what it may and may not call before and after `GRANT pg_stat_scan_tables`, prints the installed ACLs, and drops the role | `fixtures` |
| `report` | lists the result files in reading order | any |
| `stop` | stops the cluster and verifies the teardown | none |
| `clean` | deletes `$SANDBOX`, refusing any path outside `.wiki-runtime/tmp/` | `stop` |

Every fixture statement is disposable: the script creates and drops databases, roles, tables and indexes, and must not be pointed at a database anyone cares about. The measuring stages mutate their fixtures, so re-run `fixtures` before re-running one of them alone.

Cluster settings and their apply scope, all written into `postgresql.conf` before the first start: `listen_addresses`, `unix_socket_directories`, `port` and `shared_buffers` are `PGC_POSTMASTER` (restart); `autovacuum` and `fsync` are `PGC_SIGHUP` (reload); `maintenance_work_mem` and `max_parallel_maintenance_workers` are `PGC_USERSET` (session or transaction). `autovacuum` is off so that no background worker rewrites a `reltuples` value a stage has just measured. The script's own statements are guarded by `statement_timeout = 10min` and `lock_timeout = 5s`, both `PGC_USERSET` in this version, passed through `PGOPTIONS` because a multi-statement `psql -c` would wrap `VACUUM` in a transaction block.[guc.c#statement-and-lock-timeouts](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2397)

### The script

```bash
#!/usr/bin/env bash
#
# physidx_stats_v12.sh - the measurement script for the wiki page
# wiki/v12/questions/indexing/physical-index-statistics-tuple-counts-and-bytes.md
#
# It builds the pinned PostgreSQL 12 checkout out of tree, starts an isolated
# cluster, creates one disposable fixture per index access method, and then
# measures the quantities the page claims: which catalog and metapage counters
# exist, what unit each writer leaves in pg_class.reltuples, which contrib
# inspection paths accept an index at all, and what a byte-per-tuple division
# actually divides.
#
# Every fixture object is disposable.  The script creates and drops databases,
# roles, tables and indexes; do not point it at a database anyone cares about.
#
# Usage, from the repository root:
#   bash physidx_stats_v12.sh                 # all stages, default order
#   bash physidx_stats_v12.sh reltuples       # one stage
#   bash physidx_stats_v12.sh stop clean      # tear the sandbox down
#
# Stages: build check cluster fixtures inventory dataitem reltuples ampages
#         gistgap dispatch padding sizes fsm privs report stop clean
#
# The measuring stages mutate their fixtures (they delete rows and vacuum), so
# re-run "fixtures" before re-running one of them on its own if you want the
# numbers this page reports.
#
# Environment: WIKI_ROOT PAGE SRC12 SANDBOX PORT12 JOBS EXTRA_CFLAGS KEEP
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v12/questions/indexing/physical-index-statistics-tuple-counts-and-bytes.md}"
SRC12="${SRC12:-$WIKI_ROOT/raw/postgres-12}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/physidx-measure}"
PORT12="${PORT12:-55432}"
JOBS="${JOBS:-8}"
EXTRA_CFLAGS="${EXTRA_CFLAGS:--O2 -g}"
KEEP="${KEEP:-0}"

BUILD="$SANDBOX/build"; INST="$SANDBOX/install"; DATA="$SANDBOX/data"
OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql"; SOCK="$SANDBOX/sock"; BIN="$INST/bin"
DB=physidx
export PGPORT="$PORT12" PGHOST="$SOCK" PGDATABASE=postgres

# statement_timeout and lock_timeout are PGC_USERSET in PostgreSQL 12: they
# need neither a restart nor a reload and apply to the session.  They travel
# through PGOPTIONS rather than a SET prefix because a multi-statement
# psql -c runs in one implicit transaction, and VACUUM cannot run there.
export PGOPTIONS="-c statement_timeout=10min -c lock_timeout=5s"

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# -X ignores ~/.psqlrc so a stray startup file cannot change a result;
# ON_ERROR_STOP is on every helper, because without it a failed statement
# inside a -f script still leaves the exit status 0.
q()  { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "$1" > /dev/null || die "failed: $1"; }
s()  { "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
t()  { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" -c "$1"; }
fl() { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" -f "$1"; }
# Deliberate-failure helper: records the server's own message instead of dying.
xf() { "$BIN/psql" -X -q -d "$DB" -c "$1" 2>&1 | head -3; }

# The fence is assembled at run time from printf '\140', so this script holds no
# literal Markdown fence and can therefore be published inside one.  md_block
# depends on the order of fenced sql blocks in the page: block 1 is the catalog
# inventory, block 2 the B-tree/hash data-item query.  Adding an earlier sql
# block to the page renumbers them.
md_block() {
  local lang=$1 want=$2 file=$3 n=0 inb=0 line tick fence
  tick=$(printf '\140'); fence="$tick$tick$tick"
  while IFS= read -r line; do
    if [ "$inb" = 1 ]; then
      if [ "$line" = "$fence" ]; then inb=0; [ "$n" = "$want" ] && return 0; continue; fi
      [ "$n" = "$want" ] && printf '%s\n' "$line"
    elif [ "$line" = "$fence$lang" ]; then
      n=$((n + 1)); inb=1
    fi
  done < "$file"
}

# --------------------------------------------------------------- build -------
keep_build_logs() {
  local l
  for l in configure make install; do
    [ -f "$BUILD/$l.log" ] && cp "$BUILD/$l.log" "$OUT/$l.log"
  done
  return 0
}
stage_build() {
  say "build 12.2 out of tree from $SRC12"
  mkdir -p "$BUILD" "$OUT" "$SQLD"
  [ -x "$BIN/postgres" ] && { note "already built, skipping"; return 0; }
  [ -x "$SRC12/configure" ] || die "no pinned checkout at $SRC12; set SRC12 or run from the repository root"
  ( cd "$BUILD" && "$SRC12/configure" --prefix="$INST" --enable-debug \
      --with-readline --with-zlib CFLAGS="$EXTRA_CFLAGS" > configure.log 2>&1 ) \
    || { keep_build_logs; die "configure failed, see $OUT/configure.log"; }
  ( cd "$BUILD" && make -j"$JOBS" > make.log 2>&1 && make install > install.log 2>&1 ) \
    || { keep_build_logs; grep -m3 'error:' "$BUILD/make.log" >&2
         die "make failed, see $OUT/make.log"; }
  local m
  for m in pgstattuple pageinspect pg_freespacemap bloom; do
    ( cd "$BUILD" && make -C "contrib/$m" -j"$JOBS" >> install.log 2>&1 \
        && make -C "contrib/$m" install >> install.log 2>&1 ) \
      || { keep_build_logs; die "contrib/$m failed, see $OUT/install.log"; }
  done
  keep_build_logs
  note "$("$BIN/postgres" --version)"
}

stage_check() {
  say "regression suites, 12.2"
  : > "$OUT/checks.txt"
  ( cd "$BUILD" && make check > check_core.log 2>&1 )
  printf 'core=%s %s\n' "$?" \
    "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_core.log" | tail -1)" \
    >> "$OUT/checks.txt"
  local m
  for m in pgstattuple pageinspect pg_freespacemap bloom; do
    ( cd "$BUILD" && make -C "contrib/$m" check > "check_$m.log" 2>&1 )
    printf '%s=%s %s\n' "$m" "$?" \
      "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_$m.log" | tail -1)" \
      >> "$OUT/checks.txt"
  done
  for m in core pgstattuple pageinspect pg_freespacemap bloom; do
    cp "$BUILD/check_$m.log" "$OUT/check_$m.log" 2>/dev/null
  done
  local d
  for d in "$BUILD/src/test/regress" "$BUILD"/contrib/*; do
    [ -f "$d/regression.diffs" ] && cp "$d/regression.diffs" "$OUT/diffs_$(basename "$d").txt"
  done
  cat "$OUT/checks.txt" >&2
}

# ------------------------------------------------------------- cluster -------
# Cluster settings and their apply scope in PostgreSQL 12:
#   listen_addresses, unix_socket_directories, port, shared_buffers  PGC_POSTMASTER (restart)
#   autovacuum, fsync                                                PGC_SIGHUP (reload)
#   maintenance_work_mem, max_parallel_maintenance_workers           PGC_USERSET (session)
# autovacuum is off so that no background worker rewrites a reltuples value a
# stage just measured; fsync is off because this cluster is disposable.
stage_cluster() {
  say "isolated 12.2 cluster on port $PORT12"
  mkdir -p "$OUT" "$SQLD"
  if "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then note "already running"
  else
    if [ ! -d "$DATA" ]; then
      mkdir -p "$SOCK"
      "$BIN/initdb" -D "$DATA" --locale=C --encoding=UTF8 > "$OUT/initdb.log" 2>&1 \
        || die "initdb failed"
      cat >> "$DATA/postgresql.conf" <<CONF
listen_addresses = ''
unix_socket_directories = '$SOCK'
port = $PORT12
autovacuum = off
fsync = off
shared_buffers = '256MB'
maintenance_work_mem = '256MB'
max_parallel_maintenance_workers = 0
CONF
    fi
    "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w start > /dev/null || die "start failed"
  fi
  "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d postgres \
      -c "SELECT /* wiki_physidx_database_exists */ 1
            FROM pg_database WHERE datname = '$DB'" | grep -q 1 \
    || "$BIN/createdb" -T template0 -E UTF8 --locale=C "$DB"
  local e
  for e in pgstattuple pageinspect pg_freespacemap bloom; do
    q "CREATE /* wiki_physidx_extension */ EXTENSION IF NOT EXISTS $e"
  done
  {
    printf 'date: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'uname: %s\n' "$(uname -sm)"
    printf 'server: %s\n' "$(s 'SELECT /* wiki_physidx_version */ version()')"
    printf 'pin: %s\n' "$(cd "$SRC12" && git rev-parse HEAD 2>/dev/null)"
    printf 'block_size: %s\n' "$(s "SELECT /* wiki_physidx_block_size */ current_setting('block_size')")"
    printf 'max_data_alignment: %s\n' \
      "$("$BIN/pg_controldata" -D "$DATA" | grep -i 'Maximum data alignment' | tr -s ' ' | cut -d' ' -f4)"
    printf 'extensions: %s\n' "$(s "SELECT /* wiki_physidx_extlist */ string_agg(extname || ' ' || extversion, ', ' ORDER BY extname) FROM pg_extension")"
  } > "$OUT/platform.txt"
  cat "$OUT/platform.txt" >&2
}

# ------------------------------------------------------------ fixtures -------
# All fixture objects below are disposable.
stage_fixtures() {
  say "disposable fixtures, one index per access method"
  cat > "$SQLD/fixtures.sql" <<'SQL'
BEGIN /* wiki_physidx_fixtures */;

DROP TABLE IF EXISTS fx_units CASCADE;
CREATE TABLE fx_units (
    id  int,
    k   int,
    txt text,
    arr text[],
    pt  point,
    bx  box
);
INSERT INTO fx_units
SELECT g,
       CASE WHEN g % 5 = 0 THEN NULL ELSE g END,
       'k' || g,
       ARRAY['a' || (g % 100), 'b' || (g % 50), 'c' || (g % 25)],
       point(g % 1000, g / 1000),
       box(point(g % 1000, g / 1000), point((g % 1000) + 1, (g / 1000) + 1))
FROM generate_series(1, 100000) AS g;

CREATE INDEX ix_bt    ON fx_units USING btree (id);
CREATE INDEX ix_hash  ON fx_units USING hash (k);
CREATE INDEX ix_gist  ON fx_units USING gist (bx);
CREATE INDEX ix_gin   ON fx_units USING gin (arr);
CREATE INDEX ix_spg   ON fx_units USING spgist (pt);
CREATE INDEX ix_brin  ON fx_units USING brin (id);
CREATE INDEX ix_bloom ON fx_units USING bloom (id, k) WITH (length = 80, col1 = 4, col2 = 4);
CREATE INDEX ix_part  ON fx_units USING btree (id) WHERE id % 10 = 0;

-- BRIN on a heap that has no rows at all.
DROP TABLE IF EXISTS fx_empty CASCADE;
CREATE TABLE fx_empty (id int);
CREATE INDEX ix_empty_brin ON fx_empty USING brin (id);

-- A GiST index small enough that block zero is both root and leaf.
DROP TABLE IF EXISTS fx_tiny CASCADE;
CREATE TABLE fx_tiny (bx box);
INSERT INTO fx_tiny
SELECT box(point(g, g), point(g + 1, g + 1)) FROM generate_series(1, 5) AS g;
CREATE INDEX ix_tiny_gist ON fx_tiny USING gist (bx);

-- A GiST index whose pages VACUUM can delete after a bulk DELETE.
DROP TABLE IF EXISTS fx_gistdel CASCADE;
CREATE TABLE fx_gistdel (pt point);
INSERT INTO fx_gistdel
SELECT point(g % 2000, g / 2000) FROM generate_series(1, 200000) AS g;
CREATE INDEX ix_gistdel ON fx_gistdel USING gist (pt);

-- Fixed-width keys for the alignment-padding measurement.
DROP TABLE IF EXISTS fx_pad5 CASCADE;
CREATE TABLE fx_pad5 (s text);
INSERT INTO fx_pad5 SELECT 'abcde' FROM generate_series(1, 20000);
CREATE INDEX ix_pad5 ON fx_pad5 USING btree (s);

DROP TABLE IF EXISTS fx_pad9 CASCADE;
CREATE TABLE fx_pad9 (s text);
INSERT INTO fx_pad9 SELECT 'abcdefghi' FROM generate_series(1, 20000);
CREATE INDEX ix_pad9 ON fx_pad9 USING btree (s);

DROP TABLE IF EXISTS fx_padint CASCADE;
CREATE TABLE fx_padint (i int);
INSERT INTO fx_padint SELECT g FROM generate_series(1, 20000) AS g;
CREATE INDEX ix_padint ON fx_padint USING btree (i);

-- A partitioned index root (relkind 'I') and its storage-carrying leaf.
DROP TABLE IF EXISTS fx_parted CASCADE;
CREATE TABLE fx_parted (id int, v text) PARTITION BY RANGE (id);
CREATE TABLE fx_parted_p1 PARTITION OF fx_parted FOR VALUES FROM (1) TO (1000);
INSERT INTO fx_parted SELECT g, 'v' || g FROM generate_series(1, 999) AS g;
CREATE INDEX ix_parted ON fx_parted USING btree (id);

-- A two-column BRIN, for the one-row-per-attribute reading of brin_page_items.
DROP TABLE IF EXISTS fx_brin2 CASCADE;
CREATE TABLE fx_brin2 (a int, b int);
INSERT INTO fx_brin2 SELECT g, g * 2 FROM generate_series(1, 50000) AS g;
CREATE INDEX ix_brin2 ON fx_brin2 USING brin (a, b) WITH (pages_per_range = 32);

DROP TABLE IF EXISTS mx_reltuples;
CREATE TABLE mx_reltuples
    (stage text, ix text, am text, relpages int, reltuples real,
     relallvisible int, main_bytes bigint);

COMMIT /* wiki_physidx_fixtures */;
SQL
  fl "$SQLD/fixtures.sql" > "$OUT/fixtures.log" 2>&1 || { tail -5 "$OUT/fixtures.log" >&2; die "fixtures failed"; }
  note "$(s "SELECT /* wiki_physidx_fixture_count */ count(*) || ' indexes' FROM pg_class WHERE relkind IN ('i','I') AND relnamespace = 'public'::regnamespace")"
}

# ----------------------------------------------------------- inventory -------
# Runs the page's first fenced sql block exactly as filed.
stage_inventory() {
  say "the page's catalog inventory SQL, exactly as filed"
  [ -f "$PAGE" ] || die "no page at $PAGE; set PAGE or run from the repository root"
  md_block sql 1 "$PAGE" > "$SQLD/inventory.sql"
  [ -s "$SQLD/inventory.sql" ] || die "could not extract sql block 1 from $PAGE"
  printf 'sha256 of filed block 1: %s\n' "$(sha256sum < "$SQLD/inventory.sql" | cut -d' ' -f1)" \
    > "$OUT/inventory.txt"
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" -f "$SQLD/inventory.sql" \
    >> "$OUT/inventory.txt" 2>&1
  printf 'exit=%s\n' "$?" >> "$OUT/inventory.txt"
  sed -n '1,4p' "$OUT/inventory.txt" >&2
  note "full result in $OUT/inventory.txt"
}

# ------------------------------------------------------------ dataitem -------
# Runs the page's second fenced sql block, first unmodified (its placeholder
# index name is expected to fail), then once per B-tree/hash fixture with only
# that placeholder replaced.
stage_dataitem() {
  say "the page's B-tree/hash data-item SQL"
  md_block sql 2 "$PAGE" > "$SQLD/dataitem.sql"
  [ -s "$SQLD/dataitem.sql" ] || die "could not extract sql block 2 from $PAGE"
  { printf 'sha256 of filed block 2: %s\n' "$(sha256sum < "$SQLD/dataitem.sql" | cut -d' ' -f1)"
    printf '\n-- unmodified, with the filed placeholder name --\n'
    "$BIN/psql" -X -q -P pager=off -d "$DB" -f "$SQLD/dataitem.sql" 2>&1
  } > "$OUT/dataitem.txt"
  local ix text
  text=$(cat "$SQLD/dataitem.sql")
  for ix in ix_bt ix_hash ix_pad5 ix_pad9 ix_padint ix_part; do
    printf '\n-- %s --\n' "$ix" >> "$OUT/dataitem.txt"
    printf '%s\n' "${text//public.index_name/public.$ix}" \
      | "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" >> "$OUT/dataitem.txt" 2>&1
  done
  cat "$OUT/dataitem.txt" >&2
}

# ----------------------------------------------------------- reltuples -------
# What each writer leaves in an index's pg_class.reltuples.
snapshot() {
  q "INSERT /* wiki_physidx_snapshot */ INTO mx_reltuples
     SELECT '$1', c.relname, am.amname, c.relpages, c.reltuples, c.relallvisible,
            pg_relation_size(c.oid, 'main')
       FROM pg_class c JOIN pg_am am ON am.oid = c.relam
      WHERE c.relkind = 'i' AND c.relnamespace = 'public'::regnamespace"
}
stage_reltuples() {
  say "pg_class.reltuples per writer, per access method"
  q "TRUNCATE /* wiki_physidx_snapshot_reset */ mx_reltuples"
  # A fresh rebuild, so that the 'build' row is the build writer's own value.
  q "REINDEX /* wiki_physidx_rebuild */ TABLE fx_units"
  snapshot build
  q "ANALYZE /* wiki_physidx_analyze */ fx_units"
  snapshot analyze
  q "VACUUM /* wiki_physidx_vacuum */ fx_units"
  snapshot vacuum
  q "DELETE /* wiki_physidx_delete */ FROM fx_units WHERE id % 4 = 0"
  q "VACUUM /* wiki_physidx_vacuum2 */ fx_units"
  snapshot vacuum_after_delete
  q "ANALYZE /* wiki_physidx_analyze2 */ fx_units"
  snapshot analyze_after_delete
  q "VACUUM /* wiki_physidx_vacuum_analyze */ ANALYZE fx_units"
  snapshot vacuum_analyze

  { printf '\n-- heap facts, after the delete --\n'
    t "SELECT /* wiki_physidx_heap_facts */ c.relname, c.relpages, c.reltuples,
              pg_relation_size(c.oid) AS heap_bytes,
              (SELECT count(*) FROM fx_units) AS live_rows,
              (SELECT count(*) FROM fx_units WHERE k IS NOT NULL) AS non_null_k,
              (SELECT count(*) FROM fx_units WHERE id % 10 = 0) AS partial_rows
         FROM pg_class c WHERE c.relname = 'fx_units'"
    printf '\n-- index reltuples by writer (100000 rows built, 25000 then deleted) --\n'
    t "SELECT /* wiki_physidx_reltuples_matrix */ ix, am,
              max(reltuples) FILTER (WHERE stage = 'build') AS after_build,
              max(reltuples) FILTER (WHERE stage = 'analyze') AS after_analyze,
              max(reltuples) FILTER (WHERE stage = 'vacuum') AS after_vacuum,
              max(reltuples) FILTER (WHERE stage = 'vacuum_after_delete') AS after_vac_del,
              max(reltuples) FILTER (WHERE stage = 'analyze_after_delete') AS after_ana_del,
              max(reltuples) FILTER (WHERE stage = 'vacuum_analyze') AS after_vac_ana
         FROM mx_reltuples WHERE ix LIKE 'ix\_%' GROUP BY ix, am ORDER BY am, ix"
    printf '\n-- relpages, relallvisible and current main bytes at the last snapshot --\n'
    t "SELECT /* wiki_physidx_pages_matrix */ ix, am, relpages, relallvisible, main_bytes,
              main_bytes / current_setting('block_size')::bigint AS current_pages
         FROM mx_reltuples WHERE stage = 'vacuum_analyze' AND ix LIKE 'ix\_%'
         ORDER BY am, ix"
    printf '\n-- BRIN on an empty heap: after build --\n'
    t "SELECT /* wiki_physidx_brin_empty_build */ relname, relpages, reltuples
         FROM pg_class WHERE relname IN ('fx_empty','ix_empty_brin') ORDER BY relname"
    printf 'pages and page types actually present:\n'
    t "SELECT /* wiki_physidx_brin_empty_items */ blknum,
              brin_page_type(get_raw_page('ix_empty_brin', blknum)) AS page_type
         FROM generate_series(0, (pg_relation_size('ix_empty_brin')
                                  / current_setting('block_size')::bigint - 1)::int) AS blknum"
    t "SELECT /* wiki_physidx_brin_empty_summary */ count(*) AS summary_rows,
              count(DISTINCT itemoffset) AS summary_items,
              bool_or(placeholder) AS any_placeholder
         FROM brin_page_items(get_raw_page('ix_empty_brin', 2), 'ix_empty_brin')"
    printf 'after VACUUM of the empty heap:\n'
    q "VACUUM /* wiki_physidx_brin_empty_vacuum */ fx_empty"
    t "SELECT /* wiki_physidx_brin_empty_after */ relname, relpages, reltuples
         FROM pg_class WHERE relname IN ('fx_empty','ix_empty_brin') ORDER BY relname"
    t "SELECT /* wiki_physidx_brin_empty_items2 */ count(DISTINCT itemoffset) AS summary_items_still_present
         FROM brin_page_items(get_raw_page('ix_empty_brin', 2), 'ix_empty_brin')"
    printf '\n-- GIN extracted-key arithmetic, on the current heap --\n'
    t "SELECT /* wiki_physidx_gin_keys */
              (SELECT count(*) FROM fx_units) AS heap_rows,
              (SELECT sum(cardinality(arr)) FROM fx_units) AS array_elements,
              (SELECT count(DISTINCT e) FROM fx_units, unnest(arr) AS e) AS distinct_keys,
              (SELECT reltuples FROM pg_class WHERE relname = 'ix_gin') AS gin_reltuples"
    printf '\n-- BRIN range arithmetic --\n'
    t "SELECT /* wiki_physidx_brin_ranges */
              (SELECT relpages FROM pg_class WHERE relname = 'fx_units') AS heap_pages,
              (brin_metapage_info(get_raw_page('ix_brin',0))).pagesperrange AS pages_per_range,
              ceil((SELECT relpages FROM pg_class WHERE relname = 'fx_units')::numeric
                   / (brin_metapage_info(get_raw_page('ix_brin',0))).pagesperrange) AS full_and_partial_ranges,
              (SELECT count(DISTINCT itemoffset)
                 FROM brin_page_items(get_raw_page('ix_brin', 2), 'ix_brin')) AS summary_items_on_page2"
  } > "$OUT/reltuples.txt" 2>&1
  cat "$OUT/reltuples.txt" >&2
}

# ------------------------------------------------------------- ampages -------
# Persistent metapage counters, read through pageinspect and pgstattuple.
stage_ampages() {
  say "metapage and whole-index counters per access method"
  q "DROP /* wiki_physidx_btfresh */ INDEX IF EXISTS ix_bt_fresh"
  q "CREATE /* wiki_physidx_btfresh */ INDEX ix_bt_fresh ON fx_units USING btree (id)"
  { printf '\n-- B-tree metapage, freshly built index, before any VACUUM of it --\n'
    t "SELECT /* wiki_physidx_btmeta_fresh */ * FROM bt_metap('ix_bt_fresh')"
    printf 'the same index after one VACUUM of its table:\n'
    q "VACUUM /* wiki_physidx_btfresh_vacuum */ fx_units"
    t "SELECT /* wiki_physidx_btmeta_fresh2 */ * FROM bt_metap('ix_bt_fresh')"
    t "SELECT /* wiki_physidx_btmeta_heap */ (SELECT count(*) FROM fx_units) AS live_heap_rows,
              (SELECT reltuples FROM pg_class WHERE relname = 'fx_units') AS heap_reltuples,
              (SELECT reltuples FROM pg_class WHERE relname = 'ix_bt_fresh') AS index_reltuples"
    printf '\n-- pgstatindex, and pg_relpages versus stored relpages --\n'
    t "SELECT /* wiki_physidx_pgstatindex */ * FROM pgstatindex('ix_bt')"
    t "SELECT /* wiki_physidx_relpages */ pg_relpages('ix_bt') AS pg_relpages,
              (SELECT relpages FROM pg_class WHERE relname = 'ix_bt') AS stored_relpages,
              pg_relation_size('ix_bt','main') / current_setting('block_size')::bigint AS size_pages"
    printf '\n-- hash metapage and item census --\n'
    t "SELECT /* wiki_physidx_hashmeta */ magic, version, ntuples, ffactor, bsize,
              maxbucket, ovflpoint, nmaps, procid
         FROM hash_metapage_info(get_raw_page('ix_hash', 0))"
    t "SELECT /* wiki_physidx_hashstat */ * FROM pgstathashindex('ix_hash')"
    t "SELECT /* wiki_physidx_hash_nulls */
              (SELECT count(*) FROM fx_units) AS heap_rows,
              (SELECT count(*) FROM fx_units WHERE k IS NOT NULL) AS non_null_keys,
              (SELECT reltuples FROM pg_class WHERE relname = 'ix_hash') AS hash_reltuples"
    printf '\n-- GIN metapage --\n'
    t "SELECT /* wiki_physidx_ginmeta */ n_total_pages, n_entry_pages, n_data_pages,
              n_entries, n_pending_pages, n_pending_tuples, version
         FROM gin_metapage_info(get_raw_page('ix_gin', 0))"
    t "SELECT /* wiki_physidx_ginstat */ * FROM pgstatginindex('ix_gin')"
    printf 'a GIN index with fastupdate on, after 50 three-key inserts:\n'
    q "DROP /* wiki_physidx_ginfast */ INDEX IF EXISTS ix_gin_fast"
    q "CREATE /* wiki_physidx_ginfast */ INDEX ix_gin_fast ON fx_units USING gin (arr) WITH (fastupdate = on)"
    q "INSERT /* wiki_physidx_ginfast_rows */ INTO fx_units (id, k, arr)
         SELECT 900000 + g, g, ARRAY['p' || g, 'q' || g, 'r' || g]
           FROM generate_series(1, 50) AS g"
    t "SELECT /* wiki_physidx_ginfast_meta */ n_pending_pages, n_pending_tuples,
              n_entries, n_total_pages
         FROM gin_metapage_info(get_raw_page('ix_gin_fast', 0))"
    printf 'the pending pages themselves (maxoff is heap-tuple groups, not index tuples):\n'
    t "SELECT /* wiki_physidx_ginfast_pages */ blk,
              (gin_page_opaque_info(get_raw_page('ix_gin_fast', blk))).maxoff AS maxoff,
              (gin_page_opaque_info(get_raw_page('ix_gin_fast', blk))).flags AS flags
         FROM (SELECT ((gin_metapage_info(get_raw_page('ix_gin_fast',0))).pending_head)::int AS blk) h"
    printf 'keys inserted by those 50 rows: 150 (three distinct array elements each)\n'
    printf 'after the pending list is cleaned up by VACUUM:\n'
    q "VACUUM /* wiki_physidx_ginfast_vacuum */ fx_units"
    t "SELECT /* wiki_physidx_ginfast_meta2 */ n_pending_pages, n_pending_tuples,
              n_entries, n_total_pages,
              (SELECT reltuples FROM pg_class WHERE relname = 'ix_gin_fast') AS reltuples
         FROM gin_metapage_info(get_raw_page('ix_gin_fast', 0))"
    printf '\n-- BRIN metapage and reverse map --\n'
    t "SELECT /* wiki_physidx_brinmeta */ * FROM brin_metapage_info(get_raw_page('ix_brin', 0))"
    t "SELECT /* wiki_physidx_brin_revmap */ count(*) AS revmap_slots,
              count(*) FILTER (WHERE pages::text <> '(0,0)') AS valid_tids,
              count(*) FILTER (WHERE pages::text = '(0,0)') AS invalid_tids
         FROM brin_revmap_data(get_raw_page('ix_brin', 1))"
    printf 'brin_page_items rows per physical item, two-column BRIN:\n'
    t "SELECT /* wiki_physidx_brin_items_per_attr */ count(*) AS rows_returned,
              count(DISTINCT itemoffset) AS distinct_items,
              count(*) / count(DISTINCT itemoffset) AS rows_per_item
         FROM brin_page_items(get_raw_page('ix_brin2', 2), 'ix_brin2')"
    printf '\n-- SP-GiST has no aggregate to read, and no decoder --\n'
    t "SELECT /* wiki_physidx_spg */ relname, relpages, reltuples,
              pg_relation_size(oid,'main') / current_setting('block_size')::bigint AS pages
         FROM pg_class WHERE relname = 'ix_spg'"
    printf '\n-- Bloom: fixed tuple width, checked against the file length --\n'
    t "SELECT /* wiki_physidx_bloom */ relname, reloptions, relpages, reltuples,
              pg_relation_size(oid,'main') / current_setting('block_size')::bigint AS pages
         FROM pg_class WHERE relname = 'ix_bloom'"
    t "SELECT /* wiki_physidx_bloom_arith */ 80 AS length_bits, 80/16 AS signature_words,
              6 + 2 * (80/16) AS predicted_tuple_bytes,
              (8192 - 24 - 8) / (6 + 2 * (80/16)) AS predicted_tuples_per_page,
              ceil(100000::numeric / ((8192 - 24 - 8) / (6 + 2 * (80/16)))) + 1
                AS predicted_pages_for_100000_rows"
  } > "$OUT/ampages.txt" 2>&1
  cat "$OUT/ampages.txt" >&2
}

# ------------------------------------------------------------- gistgap -------
# The page's GiST claims about the pinned pgstattuple implementation.
stage_gistgap() {
  say "GiST: single-page index and deleted pages under pgstattuple"
  { printf '\n-- a GiST index whose block zero is root and leaf --\n'
    t "SELECT /* wiki_physidx_gist_tiny_size */ relname, relpages, reltuples,
              pg_relation_size(oid,'main') / current_setting('block_size')::bigint AS pages
         FROM pg_class WHERE relname = 'ix_tiny_gist'"
    t "SELECT /* wiki_physidx_gist_tiny_stat */ table_len, tuple_count, tuple_len,
              tuple_percent, dead_tuple_count, free_space, free_percent
         FROM pgstattuple('ix_tiny_gist')"
    printf 'rows actually indexed: %s\n' "$(s 'SELECT /* wiki_physidx_gist_tiny_rows */ count(*) FROM fx_tiny')"
    printf '\n-- a multi-page GiST index --\n'
    t "SELECT /* wiki_physidx_gist_stat */ table_len, tuple_count, tuple_len, tuple_percent,
              dead_tuple_count, free_space, free_percent
         FROM pgstattuple('ix_gistdel')"
    printf 'rows indexed: %s\n' "$(s 'SELECT /* wiki_physidx_gist_rows */ count(*) FROM fx_gistdel')"
    printf '\n-- after deleting 95%% of the rows and vacuuming twice --\n'
    q "DELETE /* wiki_physidx_gist_delete */ FROM fx_gistdel WHERE (pt[0])::int % 20 <> 0"
    q "VACUUM /* wiki_physidx_gist_vacuum */ fx_gistdel"
    q "VACUUM /* wiki_physidx_gist_vacuum2 */ fx_gistdel"
    t "SELECT /* wiki_physidx_gist_stat2 */ table_len, tuple_count, tuple_len, tuple_percent,
              dead_tuple_count, free_space, free_percent
         FROM pgstattuple('ix_gistdel')"
    printf 'rows left: %s\n' "$(s 'SELECT /* wiki_physidx_gist_rows2 */ count(*) FROM fx_gistdel')"
    t "SELECT /* wiki_physidx_gist_after */ relname, relpages, reltuples,
              pg_relation_size(oid,'main') AS main_bytes,
              pg_relation_size(oid,'fsm') AS fsm_bytes
         FROM pg_class WHERE relname = 'ix_gistdel'"
    printf 'free pages the GiST index recorded in the FSM:\n'
    t "SELECT /* wiki_physidx_gist_fsm */ avail, count(*)
         FROM pg_freespace('ix_gistdel') GROUP BY avail ORDER BY avail DESC LIMIT 5"
    printf 'page census read straight out of the GiST page opaque trailer.  There is\n'
    printf 'no GiST decoder in this pageinspect, so the two flag bytes are read from\n'
    printf 'the raw page: GISTPageOpaqueData is 16 bytes at pd_special, flags sit at\n'
    printf 'pd_special + 12, F_LEAF = 1 and F_DELETED = 2.  A deleted page keeps its\n'
    printf 'F_LEAF bit and has pd_lower = MAXALIGN(24) + 8 = 32, which\n'
    printf 'PageGetMaxOffsetNumber reads as 2 line pointers:\n'
    t "WITH pages AS (
         SELECT /* wiki_physidx_gist_page_census */ blk,
                h.lower AS pd_lower, h.special AS pd_special,
                get_byte(p.raw, h.special + 12)
                  + 256 * get_byte(p.raw, h.special + 13) AS flags
           FROM generate_series(0, (pg_relation_size('ix_gistdel')
                                    / current_setting('block_size')::bigint - 1)::int) AS blk,
                LATERAL get_raw_page('ix_gistdel', blk) AS p(raw),
                LATERAL page_header(p.raw) AS h
       )
       SELECT (flags & 1) <> 0 AS is_leaf, (flags & 2) <> 0 AS is_deleted,
              count(*) AS pages, min(pd_lower) AS min_pd_lower, max(pd_lower) AS max_pd_lower,
              sum((pd_lower - 24) / 4) AS line_pointers_pagegetmaxoffset_would_report
         FROM pages GROUP BY 1, 2 ORDER BY 1, 2"
    t "SELECT /* wiki_physidx_gist_phantom */
              (SELECT tuple_count FROM pgstattuple('ix_gistdel')) AS pgstattuple_items,
              (SELECT count(*) FROM fx_gistdel) AS live_rows,
              (SELECT tuple_count FROM pgstattuple('ix_gistdel'))
                - (SELECT count(*) FROM fx_gistdel) AS difference"
  } > "$OUT/gistgap.txt" 2>&1
  cat "$OUT/gistgap.txt" >&2
}

# ------------------------------------------------------------ dispatch -------
# Which inspection path accepts which access method, and the exact refusals.
stage_dispatch() {
  say "contrib inspection dispatch and refusals"
  { local ix
    printf '\n-- pgstattuple() per index --\n'
    for ix in ix_bt ix_hash ix_gist ix_gin ix_spg ix_brin ix_bloom ix_part \
              ix_parted fx_parted_p1_id_idx; do
      printf '%-22s %s\n' "$ix" \
        "$(xf "SELECT /* wiki_physidx_dispatch */ tuple_count FROM pgstattuple('$ix')" | tr '\n' ' ')"
    done
    printf '\n-- the typed functions on the wrong access method --\n'
    printf 'pgstatindex(ix_hash):     %s\n' "$(xf "SELECT /* wiki_physidx_wrongam1 */ version FROM pgstatindex('ix_hash')" | tr '\n' ' ')"
    printf 'pgstathashindex(ix_bt):   %s\n' "$(xf "SELECT /* wiki_physidx_wrongam2 */ version FROM pgstathashindex('ix_bt')" | tr '\n' ' ')"
    printf 'pgstatginindex(ix_bt):    %s\n' "$(xf "SELECT /* wiki_physidx_wrongam3 */ version FROM pgstatginindex('ix_bt')" | tr '\n' ' ')"
    printf 'pg_relpages(ix_spg):      %s\n' "$(xf "SELECT /* wiki_physidx_relpages_spg */ pg_relpages('ix_spg')" | tr '\n' ' ')"
    printf 'pg_relpages(ix_parted):   %s\n' "$(xf "SELECT /* wiki_physidx_relpages_part */ pg_relpages('ix_parted')" | tr '\n' ' ')"
    printf '\n-- get_raw_page() on a partitioned index root --\n'
    printf '%s\n' "$(xf "SELECT /* wiki_physidx_rawpart */ length(get_raw_page('ix_parted', 0))" | tr '\n' ' ')"
    printf '\n-- which pageinspect decoders exist at all --\n'
    printf 'installed functions: %s\n' \
      "$(s "SELECT /* wiki_physidx_pageinspect_list */ string_agg(p.proname, ' ' ORDER BY p.proname)
              FROM pg_depend d JOIN pg_proc p ON p.oid = d.objid
              JOIN pg_extension e ON e.oid = d.refobjid WHERE e.extname = 'pageinspect'")"
    printf '\n-- relkind and storage of the partitioned pair --\n'
    t "SELECT /* wiki_physidx_partkinds */ relname, relkind, relfilenode, relpages, reltuples,
              pg_relation_size(oid) AS bytes
         FROM pg_class
        WHERE relname IN ('fx_parted','fx_parted_p1','ix_parted','fx_parted_p1_id_idx')
        ORDER BY relname"
  } > "$OUT/dispatch.txt" 2>&1
  cat "$OUT/dispatch.txt" >&2
}

# -------------------------------------------------------------- padding ------
# Does pgstattuple's tuple_len include each item's MAXALIGN padding?
stage_padding() {
  say "item payload versus MAXALIGN padding and the line pointer"
  { printf '\n-- three B-tree indexes with known key widths --\n'
    t "SELECT /* wiki_physidx_pad */ v.ix,
              (pgstattuple(v.ix)).tuple_count AS items,
              (pgstattuple(v.ix)).tuple_len AS payload_bytes,
              ((pgstattuple(v.ix)).tuple_len::numeric
                 / (pgstattuple(v.ix)).tuple_count) AS avg_item_bytes,
              (pgstattuple(v.ix)).table_len AS main_bytes
         FROM (VALUES ('ix_pad5'),('ix_pad9'),('ix_padint')) AS v(ix)"
    printf '\n-- the same items as pageinspect sees them, one leaf page each --\n'
    t "SELECT /* wiki_physidx_pad_items */ 'ix_pad5' AS ix, itemlen, count(*)
         FROM bt_page_items('ix_pad5', 2) GROUP BY itemlen ORDER BY itemlen"
    t "SELECT /* wiki_physidx_pad_items9 */ 'ix_pad9' AS ix, itemlen, count(*)
         FROM bt_page_items('ix_pad9', 2) GROUP BY itemlen ORDER BY itemlen"
    t "SELECT /* wiki_physidx_pad_itemsint */ 'ix_padint' AS ix, itemlen, count(*)
         FROM bt_page_items('ix_padint', 2) GROUP BY itemlen ORDER BY itemlen"
    printf '\n-- predicted item size: MAXALIGN(8-byte header + stored datum) --\n'
    printf 'a text of 5 or 9 bytes gets a 1-byte varlena header inside the index\n'
    printf 'tuple, so the stored datum is 1 + octet_length, not pg_column_size:\n'
    t "SELECT /* wiki_physidx_pad_widths */
              octet_length('abcde') AS text5_octets,
              octet_length('abcdefghi') AS text9_octets,
              pg_column_size('abcde'::text) AS text5_pg_column_size,
              8 AS index_tuple_header,
              8 * ceil((8 + 1 + octet_length('abcde'))::numeric / 8) AS predicted_text5,
              8 * ceil((8 + 1 + octet_length('abcdefghi'))::numeric / 8) AS predicted_text9,
              8 * ceil((8 + 4)::numeric / 8) AS predicted_int4"
    printf '\n-- high keys: pgstattuple skips them, bt_page_items does not --\n'
    t "SELECT /* wiki_physidx_high_keys */
              count(*) FILTER (WHERE p.type = 'l') AS leaf_pages,
              sum(p.live_items) FILTER (WHERE p.type = 'l') AS leaf_items_incl_high_keys,
              (SELECT tuple_count FROM pgstattuple('ix_pad5')) AS pgstattuple_items,
              sum(p.live_items) FILTER (WHERE p.type = 'l')
                - (SELECT tuple_count FROM pgstattuple('ix_pad5')) AS difference,
              (SELECT count(*) FROM fx_pad5) AS heap_rows
         FROM generate_series(1, (pg_relpages('ix_pad5') - 1)::int) AS blk,
              LATERAL bt_page_stats('ix_pad5', blk) AS p"
    printf '\n-- one leaf page: items, payload, line pointers, free space --\n'
    t "SELECT /* wiki_physidx_pad_page */ 'ix_pad5' AS ix, p.live_items, p.dead_items,
              p.avg_item_size, p.page_size, p.free_size,
              4 * p.live_items AS line_pointer_bytes
         FROM bt_page_stats('ix_pad5', 2) AS p"
    printf '\n-- LP_DEAD items still count as stored bytes --\n'
    t "SELECT /* wiki_physidx_dead */ table_len, tuple_count, tuple_len,
              dead_tuple_count, dead_tuple_len, free_space
         FROM pgstattuple('ix_bt')"
  } > "$OUT/padding.txt" 2>&1
  cat "$OUT/padding.txt" >&2
}

# ---------------------------------------------------------------- sizes ------
# Fork names, size functions and the catalog-versus-file distinction.
stage_sizes() {
  say "size functions, forks and the stale-catalog gap"
  { printf '\n-- every accepted fork name, one B-tree index --\n'
    t "SELECT /* wiki_physidx_forks */
              pg_relation_size('ix_bt','main') AS main,
              pg_relation_size('ix_bt','fsm')  AS fsm,
              pg_relation_size('ix_bt','vm')   AS vm,
              pg_relation_size('ix_bt','init') AS init,
              pg_table_size('ix_bt')           AS table_size,
              pg_indexes_size('ix_bt')         AS indexes_size,
              pg_total_relation_size('ix_bt')  AS total"
    printf 'a rejected fork name: %s\n' "$(xf "SELECT /* wiki_physidx_badfork */ pg_relation_size('ix_bt','junk')" | tr '\n' ' ')"
    printf '\n-- catalog estimate versus current file length after unindexed growth --\n'
    q "DROP /* wiki_physidx_stale */ TABLE IF EXISTS fx_stale CASCADE"
    q "CREATE /* wiki_physidx_stale */ TABLE fx_stale (id int)"
    q "INSERT /* wiki_physidx_stale */ INTO fx_stale SELECT g FROM generate_series(1, 50000) g"
    q "CREATE /* wiki_physidx_stale */ INDEX ix_stale ON fx_stale (id)"
    t "SELECT /* wiki_physidx_stale_before */ 'after build' AS moment, relpages, reltuples,
              pg_relation_size(oid,'main') AS main_bytes,
              relpages::bigint * current_setting('block_size')::bigint AS catalog_bytes
         FROM pg_class WHERE relname = 'ix_stale'"
    q "INSERT /* wiki_physidx_stale_grow */ INTO fx_stale
         SELECT g FROM generate_series(50001, 200000) g"
    t "SELECT /* wiki_physidx_stale_after */ 'after 150k more rows, no ANALYZE' AS moment,
              relpages, reltuples,
              pg_relpages('ix_stale') AS pg_relpages,
              pg_relation_size(oid,'main') AS main_bytes,
              relpages::bigint * current_setting('block_size')::bigint AS catalog_bytes,
              CASE WHEN reltuples > 0
                   THEN round((pg_relation_size(oid,'main') / reltuples)::numeric, 2)
              END AS bytes_per_catalog_count
         FROM pg_class WHERE relname = 'ix_stale'"
    q "ANALYZE /* wiki_physidx_stale_analyze */ fx_stale"
    t "SELECT /* wiki_physidx_stale_analyzed */ 'after ANALYZE' AS moment, relpages, reltuples,
              pg_relation_size(oid,'main') AS main_bytes,
              CASE WHEN reltuples > 0
                   THEN round((pg_relation_size(oid,'main') / reltuples)::numeric, 2)
              END AS bytes_per_catalog_count
         FROM pg_class WHERE relname = 'ix_stale'"
    printf '\n-- the same ratio across access methods, one moment --\n'
    t "SELECT /* wiki_physidx_ratio */ c.relname, am.amname, c.reltuples,
              pg_relation_size(c.oid,'main') AS main_bytes,
              CASE WHEN c.reltuples > 0
                   THEN round((pg_relation_size(c.oid,'main') / c.reltuples)::numeric, 2)
              END AS main_bytes_per_catalog_count
         FROM pg_class c JOIN pg_am am ON am.oid = c.relam
        WHERE c.relname IN ('ix_bt','ix_hash','ix_gist','ix_gin','ix_spg','ix_brin',
                            'ix_bloom','ix_part')
        ORDER BY am.amname, c.relname"
  } > "$OUT/sizes.txt" 2>&1
  cat "$OUT/sizes.txt" >&2
}

# ------------------------------------------------------------------ fsm ------
stage_fsm() {
  say "what the index free space map records"
  q "DROP /* wiki_physidx_fsm */ TABLE IF EXISTS fx_fsm CASCADE"
  q "CREATE /* wiki_physidx_fsm */ TABLE fx_fsm (id int)"
  q "INSERT /* wiki_physidx_fsm */ INTO fx_fsm SELECT g FROM generate_series(1, 300000) g"
  q "CREATE /* wiki_physidx_fsm */ INDEX ix_fsm ON fx_fsm (id)"
  q "DELETE /* wiki_physidx_fsm */ FROM fx_fsm WHERE id > 1000"
  q "VACUUM /* wiki_physidx_fsm_vacuum */ fx_fsm"
  q "VACUUM /* wiki_physidx_fsm_vacuum2 */ fx_fsm"
  { printf '\n-- a B-tree whose pages VACUUM reclaimed --\n'
    t "SELECT /* wiki_physidx_fsm_btree */
              pg_relation_size('ix_fsm','main') / current_setting('block_size')::bigint AS main_pages,
              pg_relation_size('ix_fsm','fsm') AS fsm_bytes,
              (SELECT count(*) FROM pg_freespace('ix_fsm')) AS mapped_pages,
              (SELECT count(*) FROM pg_freespace('ix_fsm') WHERE avail > 0) AS pages_with_avail,
              (SELECT max(avail) FROM pg_freespace('ix_fsm')) AS max_avail"
    t "SELECT /* wiki_physidx_fsm_values */ avail, count(*)
         FROM pg_freespace('ix_fsm') GROUP BY avail ORDER BY avail DESC LIMIT 5"
    t "SELECT /* wiki_physidx_fsm_btree_pages */ leaf_pages, internal_pages,
              empty_pages, deleted_pages, index_size, avg_leaf_density
         FROM pgstatindex('ix_fsm')"
    printf '\n-- BRIN records quantized regular-page free space instead --\n'
    t "SELECT /* wiki_physidx_fsm_brin */ avail, count(*)
         FROM pg_freespace('ix_brin2') GROUP BY avail ORDER BY avail DESC"
    printf '\n-- hash keeps overflow-page availability in its own bitmap pages --\n'
    t "SELECT /* wiki_physidx_fsm_hash */ bucket_pages, overflow_pages, bitmap_pages,
              unused_pages
         FROM pgstathashindex('ix_hash')"
    t "SELECT /* wiki_physidx_fsm_hash_bitmap */ nmaps, mapp[1:nmaps] AS bitmap_page_blocks
         FROM hash_metapage_info(get_raw_page('ix_hash', 0))"
    printf '\n-- the byte length of the FSM fork is the map, not the free bytes --\n'
    t "SELECT /* wiki_physidx_fsm_forks */ c.relname, am.amname,
              pg_relation_size(c.oid,'main') AS main_bytes,
              pg_relation_size(c.oid,'fsm') AS fsm_bytes
         FROM pg_class c JOIN pg_am am ON am.oid = c.relam
        WHERE c.relname IN ('ix_fsm','ix_brin2','ix_hash','ix_spg','ix_gin','ix_bloom','ix_gistdel')
        ORDER BY c.relname"
  } > "$OUT/fsm.txt" 2>&1
  cat "$OUT/fsm.txt" >&2
}

# ---------------------------------------------------------------- privs ------
stage_privs() {
  say "privileges on the inspection functions"
  q "DROP /* wiki_physidx_role */ ROLE IF EXISTS physidx_plain"
  q "CREATE /* wiki_physidx_role */ ROLE physidx_plain"
  q "GRANT /* wiki_physidx_role */ SELECT ON fx_units TO physidx_plain"
  { printf '\n-- as a plain role --\n'
    printf 'pgstattuple:      %s\n' "$(xf "SET ROLE physidx_plain; SELECT /* wiki_physidx_priv1 */ tuple_count FROM pgstattuple('ix_bt')" | tr '\n' ' ')"
    printf 'pgstatindex:      %s\n' "$(xf "SET ROLE physidx_plain; SELECT /* wiki_physidx_priv2 */ version FROM pgstatindex('ix_bt')" | tr '\n' ' ')"
    printf 'get_raw_page:     %s\n' "$(xf "SET ROLE physidx_plain; SELECT /* wiki_physidx_priv3 */ length(get_raw_page('ix_bt',0))" | tr '\n' ' ')"
    printf 'pg_freespace:     %s\n' "$(xf "SET ROLE physidx_plain; SELECT /* wiki_physidx_priv4 */ count(*) FROM pg_freespace('ix_bt')" | tr '\n' ' ')"
    printf 'pg_relation_size: %s\n' "$(xf "SET ROLE physidx_plain; SELECT /* wiki_physidx_priv5 */ pg_relation_size('ix_bt')" | tr '\n' ' ')"
    q "GRANT /* wiki_physidx_role_grant */ pg_stat_scan_tables TO physidx_plain"
    printf '\n-- after GRANT pg_stat_scan_tables --\n'
    printf 'pgstattuple:      %s\n' "$(xf "SET ROLE physidx_plain; SELECT /* wiki_physidx_priv6 */ tuple_count FROM pgstattuple('ix_bt')" | tr '\n' ' ')"
    printf 'pgstatindex:      %s\n' "$(xf "SET ROLE physidx_plain; SELECT /* wiki_physidx_priv7 */ version FROM pgstatindex('ix_bt')" | tr '\n' ' ')"
    printf 'get_raw_page:     %s\n' "$(xf "SET ROLE physidx_plain; SELECT /* wiki_physidx_priv8 */ length(get_raw_page('ix_bt',0))" | tr '\n' ' ')"
    printf '\n-- declared privileges as installed --\n'
    t "SELECT /* wiki_physidx_acl */ p.proname, pg_get_function_identity_arguments(p.oid) AS args,
              p.proacl::text
         FROM pg_proc p JOIN pg_depend d ON d.objid = p.oid
         JOIN pg_extension e ON e.oid = d.refobjid
        WHERE e.extname = 'pgstattuple' ORDER BY p.proname, args"
  } > "$OUT/privs.txt" 2>&1
  q "REVOKE /* wiki_physidx_role_revoke */ pg_stat_scan_tables FROM physidx_plain"
  q "DROP /* wiki_physidx_role_drop */ OWNED BY physidx_plain"
  q "DROP /* wiki_physidx_role_drop */ ROLE physidx_plain"
  cat "$OUT/privs.txt" >&2
}

# --------------------------------------------------------------- report ------
stage_report() {
  say "results"
  local f
  for f in platform.txt checks.txt inventory.txt dataitem.txt reltuples.txt \
           ampages.txt gistgap.txt dispatch.txt padding.txt sizes.txt fsm.txt privs.txt; do
    [ -f "$OUT/$f" ] && printf '%s\n' "$OUT/$f"
  done
  note "read $OUT/platform.txt first, then $OUT/reltuples.txt"
}

# ----------------------------------------------------------- stop, clean -----
stage_stop() {
  say "stop the cluster"
  if "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -m fast -w stop || die "pg_ctl stop failed"
  else note "not running"; fi
  [ -f "$DATA/postmaster.pid" ] && die "postmaster.pid still present in $DATA"
  pgrep -f "postgres -D $DATA" > /dev/null && die "a postgres process still matches $DATA"
  note "stopped; no postmaster.pid, no matching process"
}

stage_clean() {
  say "delete the sandbox"
  [ "$KEEP" = 1 ] && { note "KEEP=1, leaving $SANDBOX in place"; return 0; }
  case "$SANDBOX" in
    */.wiki-runtime/tmp/*) : ;;
    *) die "refusing to delete $SANDBOX: not under .wiki-runtime/tmp/" ;;
  esac
  [ -f "$DATA/postmaster.pid" ] && die "run the stop stage first"
  rm -rf "$SANDBOX"
  [ -d "$SANDBOX" ] && die "sandbox still present"
  note "deleted $SANDBOX"
}

STAGES_DEFAULT="build cluster fixtures inventory dataitem reltuples ampages gistgap dispatch padding sizes fsm privs report"
for stage in ${*:-$STAGES_DEFAULT}; do
  case "$stage" in
    build|check|cluster|fixtures|inventory|dataitem|reltuples|ampages|gistgap|dispatch|padding|sizes|fsm|privs|report|stop|clean)
      "stage_$stage" ;;
    *) die "unknown stage: $stage" ;;
  esac
done
```

### Last run

| Fact | Value |
| --- | --- |
| Date | 2026-09-10 |
| Stages run | `fixtures inventory dataitem reltuples ampages gistgap dispatch padding sizes fsm privs report`, then `check`, then `stop clean` |
| Server | `PostgreSQL 12.2 on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit` |
| Pin | `45b88269a353ad93744772791feb6d01bc7e1e42`, built out of tree from `raw/postgres-12/` |
| Platform | Linux x86_64, `block_size = 8192`, `max_data_alignment = 8` |
| Extensions | `bloom 1.0`, `pageinspect 1.7`, `pg_freespacemap 1.2`, `pgstattuple 1.5` |
| Suites | `make check`: engine 192 of 192 passed; `pageinspect` 5 of 5; `pgstattuple` 1 of 1; `bloom` 1 of 1; `pg_freespacemap` ships no test suite |
| Page blocks executed | fenced `sql` block 1 at SHA-256 `08367525ecb547a9ca56ec246930732e0e07599d7046b5af666a4db5feb955ed`, block 2 at `7352c45b6ea190e10e3af2cd4c05a196f994a46cadd942cec0f0ba2befcee3c0`; the `bash` block above is byte-identical to the file that was run, and re-extracting it from this page reproduces both hashes |
| Teardown | server stopped with `pg_ctl -m fast -w stop`; no `postmaster.pid`, no matching process, sandbox deleted |

## Context Reviewed

- Pinned PostgreSQL 12.2 checkout at commit `45b88269a353ad93744772791feb6d01bc7e1e42`.
- Shared catalog definitions and writers: `pg_class`, `pg_index`, `pg_statistic`, index build, standalone `ANALYZE`, `VACUUM`, planner size estimation, relation-size functions, generic page/tuple layout, cumulative statistics views, and the index AM API.
- B-tree, hash, GiST, GIN, SP-GiST, BRIN, and contrib Bloom metapages, page opaque structures, tuple formats, insert/build paths, VACUUM paths, cost/planner readers, error paths, contrib inspection code, and reloptions.
- Reverse users of the shared build/VACUUM statistics structures and generated catalog headers.
- Core regression, contrib regression, the heap-only `reltuples` isolation spec, and the direct inspection tests listed above.
- Process note, not source evidence: an isolated 12.2 server built from the exact pin ran the script in [Measurement Script](#measurement-script) on 2026-09-10, with the `pgstattuple`, `pageinspect`, `pg_freespacemap` and `bloom` modules installed, and executed both of this page's fenced SQL blocks. An earlier run, before that script existed, could execute only the catalog-inventory block because its installation had no `pgstattuple` shared module; the B-tree/hash block is now executed rather than inferred.[pgstattuple--1.4--1.5.sql#pgstattuple-regclass-result](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L61-L72) [pgstattuple.c#index-AM-dispatch](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L312)
- Re-review on 2026-08-11 against the same pin rechecked every claim and citation on this page; the corrections it produced are recorded in `wiki/log.md`.
- Re-review on 2026-09-10 against the same pin re-read all 354 source citations on this page (228 distinct line ranges over 91 files), all of which resolve in bounds and cite only `raw/postgres-12/`, and added the measured section and the measurement script. No source claim needed correction; the stale process note above was rewritten and six open questions were added or sharpened.

## Evidence Map

| Claim | Primary evidence |
| --- | --- |
| `pg_class` physical relstats are stale estimates and index `relallvisible` is zero | [pg_class.h#physical-relstats](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L49-L66), [index.c#index-relallvisible](../../../../raw/postgres-12/src/backend/catalog/index.c#L2761-L2785) |
| Build, `ANALYZE`, and `VACUUM` can write different `reltuples` units | [index.c#index-build-statistics](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2989), [analyze.c#index-relstats-update](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629), [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1771-L1815) |
| Current PostgreSQL size is segment `st_size`, not tuple payload or filesystem allocation | [dbsize.c#calculate_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L266-L308) |
| B-tree has structural/last-cleanup metadata but no current global tuple count | [nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L90-L110), [nbtree.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L783-L845) |
| Hash persists `hashm_ntuples`, but physical split copies and cleanup make page counts a different quantity | [hash.h#HashMetaPageData](../../../../raw/postgres-12/src/include/access/hash.h#L242-L263), [hashpage.c#bucket-split-copy](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L1107-L1287) |
| GiST has no aggregate and the PostgreSQL 12 `pgstattuple` path is not a safe exact census | [gist.h#GISTPageOpaqueData](../../../../raw/postgres-12/src/include/access/gist.h#L41-L82), [pgstattuple.c#GiST-dispatch](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L283), [gist.h#deleted-page-layout](../../../../raw/postgres-12/src/include/access/gist.h#L160-L183) |
| GIN metapage counters have several units and cannot recover total postings or rows | [ginblock.h#GinMetaPageData](../../../../raw/postgres-12/src/include/access/ginblock.h#L54-L100), [ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L686-L731) |
| SP-GiST stores placement hints and per-page redirect/placeholder counts, not live-leaf totals | [spgist_private.h#page-and-metapage-data](../../../../raw/postgres-12/src/include/access/spgist_private.h#L36-L101) |
| BRIN counts summaries/ranges, not rows; valid revmap TIDs identify referenced summaries or placeholders | [brin_page.h#metapage-and-revmap](../../../../raw/postgres-12/src/include/access/brin_page.h#L63-L94), [brin_revmap.c#brinGetTupleForHeapBlock](../../../../raw/postgres-12/src/backend/access/brin/brin_revmap.c#L179-L311), [brin_revmap.c#leftover-placeholder](../../../../raw/postgres-12/src/backend/access/brin/brin_revmap.c#L397-L405) |
| Bloom has fixed tuple payloads but no aggregate tuple counter | [bloom.h#metapage-and-tuple](../../../../raw/postgres-12/contrib/bloom/bloom.h#L99-L165), [blvacuum.c#Bloom-page-census](../../../../raw/postgres-12/contrib/bloom/blvacuum.c#L163-L216) |
| No generic AM physical-statistics callback exists | [amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L163-L233) |
| `VACUUM ANALYZE` leaves the VACUUM leg's index count, not the ANALYZE estimate (measured: 13, not 75,000, on a BRIN index) | [analyze.c#index-relstats-update](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629) |
| A VACUUM whose heap scan skipped pages writes no index `reltuples` at all (measured: a GIN index kept its 225,000 build value) | [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1771-L1815), [genam.h#IndexBulkDeleteResult](../../../../raw/postgres-12/src/include/access/genam.h#L55-L81) |
| `pgstattuple`'s B-tree/hash item payload includes each item's MAXALIGN padding and excludes high keys (measured: 16.0 bytes for a five-byte text key; 20,000 items against 20,054 leaf line pointers) | [indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L126-L188), [pgstattuple.c#pgstat_btree_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L406-L448), [nbtree.h#high-key](../../../../raw/postgres-12/src/include/access/nbtree.h#L198-L219) |
| A deleted GiST page keeps `F_LEAF` and reports two phantom line pointers to `pgstattuple` (measured: 21 deleted pages, 42 extra items) | [gist.h#deleted-page-layout](../../../../raw/postgres-12/src/include/access/gist.h#L160-L183), [pgstattuple.c#pgstat_gist_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L492-L518) |
| A recorded free index page reads back as the FSM category's lower bound, not `BLCKSZ - 1` (measured: 8,160) | [indexfsm.c#index-FSM-implementation](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L32-L73), [freespace.c#FSM-quantization](../../../../raw/postgres-12/src/backend/storage/freespace/freespace.c#L379-L416) |

## Open Questions

- BRIN reverse-map pages occupy blocks `1 .. lastRevmapPage`: `revmap_get_blkno()` adds one to skip the metapage, and extension sets `lastRevmapPage` to the new highest map block. An index with N revmap pages therefore has `lastRevmapPage = N`, but `brinGetStats()` derives `revmapNumPages = lastRevmapPage - 1`, one page short. Its consumer treats the value as a true page count—`brincostestimate()` charges `seq_page_cost * revmapNumPages` as startup cost, prices `numPages - revmapNumPages` at random cost, and its hypothetical-index branch instead computes a rounded-up `(indexRanges / REVMAP_PAGE_MAXITEMS) + 1`. A one-revmap-page index is thus costed as if the revmap were free. This page therefore uses the raw last block and reverse-map contents for physical accounting rather than the derived planner count.[brin_revmap.c#revmap-block-mapping](../../../../raw/postgres-12/src/backend/access/brin/brin_revmap.c#L445-L463) [brin_revmap.c#revmap-extension](../../../../raw/postgres-12/src/backend/access/brin/brin_revmap.c#L616-L638) [brin.c#brinGetStats](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L1089-L1108) [selfuncs.c#brincostestimate-hypothetical-revmap](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L7032-L7043) [selfuncs.c#brincostestimate-revmap-cost](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L7173-L7187)
- `bufpage.h` states that `pd_prune_xid` "is currently unused in index pages," but GIN reads and writes that same field as a deleted-page reclamation XID through `GinPageGetDeleteXid()` and `GinPageSetDeleteXid()`. GIN is the only index AM in the checkout that does so. This page follows the implementation: on a deleted GIN page the field is in use.[bufpage.h#pd_prune_xid](../../../../raw/postgres-12/src/include/storage/bufpage.h#L134-L135) [ginblock.h#deleted-page-xid](../../../../raw/postgres-12/src/include/access/ginblock.h#L131-L138)
- The pinned `pgstattuple()` GiST implementation skips block-zero leaf roots and does not exclude deleted pages, and its regression file has no direct GiST case. Both effects are now measured on this pin — 0 items reported for a five-row single-page index, and a 42-item overcount from 21 deleted pages — but whether an operational installation carries a downstream correction cannot be established from this checkout; verify that code before using GiST output.[pgstattuple.c#GiST-dispatch](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L283) [pgstattuple.c#pgstat_gist_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L492-L518) [pgstattuple.sql#extension-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L119)
- How many GiST pages a given `DELETE` plus `VACUUM` sequence actually deletes is not stable across runs of the script's own `gistgap` stage: repeated runs of the identical fixture produced 15 and 21 deleted pages, hence 30- and 42-item overcounts. The *relationship* held every time — the overcount was exactly twice the number of pages marked both `F_LEAF` and `F_DELETED` — because whether an empty leaf page is unlinked at all depends on the downlink recheck and on how many empty pages the second pass still has left to process. Treat the filed 21/42 as one observation of a variable quantity, not a constant.[gistvacuum.c#empty-page-unlink-count](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c#L465-L584) [gistvacuum.c#gistvacuumpage-leaf-count](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c#L318-L412)
- The GiST fixture ended two `VACUUM`s with 21 deleted pages and an *absent* FSM fork, so "counting nonzero `pg_freespace` results counts pages recorded as wholly reusable" understates the lag for GiST specifically: `gistvacuumscan()` records a deleted page only once `gistPageRecyclable()` accepts its delete XID, and it vacuums the index FSM only when that pass found at least one such page. The number of `VACUUM`s and the transaction activity needed to make those pages appear in the map was not established.[gistvacuum.c#gistvacuumcleanup](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c#L100-L145) [indexfsm.c#index-FSM-implementation](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L32-L73)
- `IndexBulkDeleteResult.pages_removed` is documented as physical file shrink, but GiST increments it when leaf pages are unlinked and marked deleted without truncating the main fork. For this GiST path, treat the returned value as removed from the tree, not proven bytes released to the filesystem.[genam.h#IndexBulkDeleteResult](../../../../raw/postgres-12/src/include/access/genam.h#L55-L81) [gistvacuum.c#empty-page-unlink-count](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c#L465-L584) [gistvacuum.c#GistPageSetDeleted](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c#L651-L683)
- The index-FSM introductory comment says `BLCKSZ - 1` means used and zero means unused, but `RecordFreeIndexPage()` and `RecordUsedIndexPage()` implement the reverse. This page follows the executable implementation: free is `BLCKSZ - 1`, used is zero.[indexfsm.c#index-FSM-comment](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L14-L20) [indexfsm.c#index-FSM-implementation](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L48-L65)
- `pgstattuple` documentation describes visibility-tested live/dead tuples, but its index path classifies only `LP_DEAD` versus not `LP_DEAD`. This page follows the index implementation.[pgstattuple.sgml#live-dead-description](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L70-L142) [pgstattuple.c#pgstat_index_page](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L564-L590)
- No regression assertion for a cross-AM `reltuples` lifecycle or bytes-per-entry formula was found in the reviewed test scope. The formulas here should be regression-tested against each production AM/opclass and concurrency pattern before they drive automation.[pgstattuple.sql#extension-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L119) [pageinspect/Makefile#regression-tests](../../../../raw/postgres-12/contrib/pageinspect/Makefile#L3-L15)
- Third-party AMs are intentionally unresolved by core source. Their handler and on-disk format can define different counters and even a different page layout.[amcmds.c#CreateAccessMethod](../../../../raw/postgres-12/src/backend/commands/amcmds.c#L37-L113) [storage.sgml#index-page-format-boundary](../../../../raw/postgres-12/doc/src/sgml/storage.sgml#L697-L711)
- Every filed number comes from one host and one block size: Linux x86_64, `block_size = 8192`, `max_data_alignment = 8`, one 12.2 build. The item widths, page capacities and Bloom page arithmetic are all functions of those two platform values, and none of them has been re-measured on a second platform or a non-default `BLCKSZ`.[bufpage.h#page-layout](../../../../raw/postgres-12/src/include/storage/bufpage.h#L22-L75) [guc.c#block_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2879-L2888)
- The `ANALYZE` figures for the partial index are sample-driven and therefore move between runs: successive runs of the same fixture recorded 10237 and 9867 against 10,000 actual matching rows, and 4873 and 4915 against 5,000 after the delete. The filed values are one draw, and the script sets no `default_statistics_target` to pin the sample size.[analyze.c#partial-index-sample](../../../../raw/postgres-12/src/backend/commands/analyze.c#L714-L822)
- The measured section covers what the shipped inspection paths expose. The AM-aware traversals this page says a correct census would need — a GiST walker that includes a leaf root and excludes deleted pages, an SP-GiST live-leaf counter, and a GIN traversal that decodes pending tuples, embedded posting lists and posting trees — were not written, so the "best meaningful physical denominator" column remains unmeasured for GiST, SP-GiST and GIN.[pgstattuple.c#unsupported-index-AMs](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L312) [pageinspect/Makefile#modules-and-tests](../../../../raw/postgres-12/contrib/pageinspect/Makefile#L3-L15)

## Source References

- Shared catalogs and accounting: [pg_class.h#FormData_pg_class](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L29-L84), [pg_index.h#FormData_pg_index](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L29-L59), [genam.h#index-maintenance-statistics](../../../../raw/postgres-12/src/include/access/genam.h#L27-L81), [index.c#index-build-statistics](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2989), [analyze.c#index-relstats-update](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629), [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1771-L1815), [dbsize.c#calculate_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L266-L308).
- Generic storage and extension API: [bufpage.h#page-layout](../../../../raw/postgres-12/src/include/storage/bufpage.h#L22-L75), [itup.h#IndexTupleData](../../../../raw/postgres-12/src/include/access/itup.h#L23-L90), [amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L163-L233).
- Core AM layouts: [nbtree.h#B-tree-page-and-meta-data](../../../../raw/postgres-12/src/include/access/nbtree.h#L55-L110), [hash.h#HashMetaPageData](../../../../raw/postgres-12/src/include/access/hash.h#L242-L263), [gist.h#GISTPageOpaqueData](../../../../raw/postgres-12/src/include/access/gist.h#L41-L82), [ginblock.h#GIN-page-and-meta-data](../../../../raw/postgres-12/src/include/access/ginblock.h#L29-L100), [spgist_private.h#SP-GiST-page-and-meta-data](../../../../raw/postgres-12/src/include/access/spgist_private.h#L25-L101), [brin_page.h#BRIN-page-and-meta-data](../../../../raw/postgres-12/src/include/access/brin_page.h#L23-L94).
- Contrib layout and inspection: [bloom.h#Bloom-layout](../../../../raw/postgres-12/contrib/bloom/bloom.h#L31-L165), [pgstattuple.c#index-AM-dispatch](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L255-L312), [pgstatindex.c#inspection-structures](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L70-L128), [pageinspect/Makefile#modules-and-tests](../../../../raw/postgres-12/contrib/pageinspect/Makefile#L3-L15).

## Navigation

- [PostgreSQL 12 index](../../index.md)
- [PostgreSQL 12 codebase navigation guide](../../codebase-navigation-guide.md)
- [Wiki index](../../../index.md)
- [Versions](../../../versions.md)
