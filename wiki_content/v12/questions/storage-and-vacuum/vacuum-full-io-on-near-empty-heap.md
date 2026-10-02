---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: claude-opus-5-max 2026-08-28T12:11:54Z
---

# How Much I/O a VACUUM FULL Performs on a Multi-GB, Near-Empty Heap in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [Where VACUUM FULL goes in v12](#where-vacuum-full-goes-in-v12)
  - [Read side: the whole heap, every block, no skip path](#read-side-the-whole-heap-every-block-no-skip-path)
  - [Heap size means the physical file, not pg_class.relpages](#heap-size-means-the-physical-file-not-pg_classrelpages)
  - [Write side: the new heap is sized by live rows](#write-side-the-new-heap-is-sized-by-live-rows)
  - [Page arithmetic for the new heap](#page-arithmetic-for-the-new-heap)
  - [WAL volume](#wal-volume)
  - [The fsync](#the-fsync)
  - [The old file is unlinked, not rewritten](#the-old-file-is-unlinked-not-rewritten)
  - [Index rebuild](#index-rebuild)
  - [TOAST](#toast)
  - [Worked example for the shape in the question](#worked-example-for-the-shape-in-the-question)
  - [Where the reads land in the buffer pool](#where-the-reads-land-in-the-buffer-pool)
  - [Second-order writes to the old heap: hint bits](#second-order-writes-to-the-old-heap-hint-bits)
  - [No cost-based throttling applies to the rewrite](#no-cost-based-throttling-applies-to-the-rewrite)
  - [What VACUUM FULL never does here](#what-vacuum-full-never-does-here)
  - [How to observe the read volume on a v12 server](#how-to-observe-the-read-volume-on-a-v12-server)
  - [What the command leaves behind](#what-the-command-leaves-behind)
  - [Test coverage in the pinned tree](#test-coverage-in-the-pinned-tree)
- [Follow-Up: Measured On A 12.2 Server](#follow-up-measured-on-a-122-server)
  - [What was built and run](#what-was-built-and-run)
  - [The fixture: 884,956 blocks holding 200,000 rows](#the-fixture-884956-blocks-holding-200000-rows)
  - [Result: VACUUM FULL read every block](#result-vacuum-full-read-every-block)
  - [Control: the same heap, a plain VACUUM, zero blocks](#control-the-same-heap-a-plain-vacuum-zero-blocks)
  - [The extreme case: a 6.75 GB heap with no rows at all](#the-extreme-case-a-675-gb-heap-with-no-rows-at-all)
  - [Writes, WAL, and the fsync](#writes-wal-and-the-fsync)
  - [What the progress view showed](#what-the-progress-view-showed)
  - [The index rebuild reads the new heap](#the-index-rebuild-reads-the-new-heap)
  - [No cost-based delay reaches the rewrite](#no-cost-based-delay-reaches-the-rewrite)
  - [What happened to the old file](#what-happened-to-the-old-file)
  - [Retained line pointers, measured](#retained-line-pointers-measured)
  - [What the measurements corrected](#what-the-measurements-corrected)
  - [How to reproduce](#how-to-reproduce)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 12, if a table heap is multiple GBs in size, however it has only a few thousand rows, so the table heap is essentially empty or filled with empty pages, how much I/O will a VACUUM FULL perform in relation to heap size?

Prompt hygiene note: the prompt as typed read "in postgresql 12, question: if a table heap is in multiple GBs however is has how few thousand rows so the table heap essentially empty or filled with empty pages ,  how much i/o a vacuum full will perform in relation to heap size?". Per `MANDATORY Prompt Hygiene` the asker was offered the choice and selected "correct and restate", so the restated text above fixes: `postgresql` -> `PostgreSQL`, `i/o` -> `I/O`, `vacuum full` -> `VACUUM FULL`, the garbled `is has how few thousand rows` -> `it has only a few thousand rows`, the missing verb in `the table heap essentially empty`, the space before the comma, and the doubled space. The asker also scoped this to source-only evidence (no measured run) and to `VACUUM FULL` alone (no comparison with plain `VACUUM`, `CLUSTER`, or `pg_repack`).

Follow-up:

Run tests on a PostgreSQL 12 database to measure I/O. The test is a table with initially 200 million rows, with 99.9% of the rows deleted but the last ones kept so that VACUUM does not truncate the heap. After VACUUM and VACUUM FREEZE, measure the heap size, then perform a VACUUM FULL and measure how much of the heap is read. The hypothesis is that the whole heap is read, even the empty or frozen pages.

Prompt hygiene note for the follow-up: the prompt as typed read "follow agents.md, in postgresql 12, for question: How Much I/O a VACUUM FULL Performs on a Multi-GB, Near-Empty Heap in PostgreSQL 12 (unverified) , run tests on a v12 db to measure i/o , the test is a table with initial 200mil rows, have 99.9% rows deleted but the last ones should stay to vacuum doesn't truncate the heap. after vacuum and vacuum freeze  mesure the heap size, and perform a vacuum full and measure how much of the heap is read the hypotesis is that all the heap is read even the empty or frozen pages." The asker was offered the choice and selected "correct and restate", so the restated text above fixes: `mesure` -> `measure`, `hypotesis` -> `hypothesis`, `postgresql` -> `PostgreSQL`, `i/o` -> `I/O`, `db` -> `database`, `200mil` -> `200 million`, `vacuum`/`vacuum freeze`/`vacuum full` -> `VACUUM`/`VACUUM FREEZE`/`VACUUM FULL`, the missing `so` in `to vacuum doesn't truncate the heap`, the space before the comma, and the doubled space. The `follow agents.md` and page-title clauses are routing instructions rather than part of the question, so they are not restated. Two scoping answers were taken up front: a narrow `bigint` row shape, chosen because it reproduces the `t_len = 32` row of the [worked example](#worked-example-for-the-shape-in-the-question); and deletion of the sandbox afterwards, with the fixture SQL published under [How to reproduce](#how-to-reproduce).

## Answer

### Short answer

Reads scale with the **full physical size of the heap**. Writes scale with the **live data only**. Emptiness buys you nothing on the read side.

| Component | Volume, relative to old heap size `S` | Why |
|---|---|---|
| Old heap reads | `≈ S` (every block, once, sequentially) | plain seq scan over `rs_nblocks` with no visibility-map skip |
| New heap writes | `≈ live bytes` (a few pages here), not `S` | one `smgrextend` per filled page |
| WAL | `0` at `wal_level = minimal`; `≈ new heap size` if `XLogIsNeeded()` | one full-page `log_newpage` per new page |
| fsync | one `smgrimmedsync` per new relation: the (tiny) heap, plus its TOAST heap if it has one | `heap_sync` at end of rewrite |
| Old heap deletion | metadata only (first segment `ftruncate`d to 0 with its unlink deferred past the next checkpoint, later 1 GB segments unlinked at once) | `mdunlinkfork` |
| Index rebuilds | reads the **new** small heap, writes small indexes | `reindex_relation` after the swap |
| TOAST | proportional to **live** toasted bytes, via index lookups | external values fetched back and re-saved |

So on a 4 GB heap holding a few thousand rows, expect roughly **4 GB of sequential reads** and, depending on row width, **184 kB to 2.5 MB of writes** — a read:write ratio of about **1,700:1 to 22,800:1** over the stored tuple widths in the [worked example](#worked-example-for-the-shape-in-the-question). The command's duration is set by how fast the storage can stream the old file, not by how much data survives.

This was measured on a 12.2 server built from the pin. A 7,249,559,552-byte heap holding 200,000 live rows in its last 886 pages, with all 884,956 pages marked all-visible and all-frozen, was read in full: `heap_blks_read` moved by exactly **884,956** and the block layer delivered exactly **7,249,559,552 bytes**, while the new heap came to 885 blocks. The same heap under a plain `VACUUM` read **0 blocks**. See [Follow-Up: Measured On A 12.2 Server](#follow-up-measured-on-a-122-server).

The one thing that *is* proportional to emptiness is the per-tuple CPU work, and even that is bounded by *line pointers* rather than by surviving rows. v12's `PageRepairFragmentation` never removes unused line pointers — "It doesn't remove unused line pointers! Please don't change this." [bufpage.c#PageRepairFragmentation](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L471-L482) — so a page emptied by `DELETE` plus `VACUUM` keeps its line pointer array and `PageGetMaxOffsetNumber` stays at that page's historical high-water mark. `heapgettup` then walks the array and skips every entry that fails `ItemIdIsNormal`, with no visibility test, no tuple reform and no rewrite call [heapam.c#heapgettup](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L651-L700). Only a page that never held a line pointer gives `PageGetMaxOffsetNumber(dp) == 0`, and only such a page costs nothing beyond its read.

### Where VACUUM FULL goes in v12

`VACUUM FULL` is not a separate code path in v12; it is `CLUSTER` without a cluster index. `vacuum_rel` takes `AccessExclusiveLock` for the `FULL` case and hands off to `cluster_rel` with `InvalidOid` as the index: [vacuum.c#vacuum_rel](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1680-L1681), [vacuum.c:1816-1828](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1816-L1828). `cluster.c`'s header comment states the contract: "If indexOid is InvalidOid, the table will be rewritten in physical order instead of index order. This is the new implementation of VACUUM FULL" [cluster.c#cluster_rel](../../../../raw/postgres-12/src/backend/commands/cluster.c#L261-L266).

`cluster_rel` tags progress reporting as `PROGRESS_CLUSTER_COMMAND_VACUUM_FULL` precisely because `indexOid` is invalid [cluster.c:276-281](../../../../raw/postgres-12/src/backend/commands/cluster.c#L276-L281), then calls `rebuild_relation` [cluster.c:428-429](../../../../raw/postgres-12/src/backend/commands/cluster.c#L428-L429), which does three things in order: create a transient heap, copy the data, swap and reindex [cluster.c#rebuild_relation](../../../../raw/postgres-12/src/backend/commands/cluster.c#L610-L626).

### Read side: the whole heap, every block, no skip path

Because `OIDOldIndex` is `InvalidOid`, `copy_table_data` leaves `OldIndex = NULL` and sets `use_sort = false` [cluster.c:797-800](../../../../raw/postgres-12/src/backend/commands/cluster.c#L797-L800), [cluster.c:891-894](../../../../raw/postgres-12/src/backend/commands/cluster.c#L891-L894). That selects the sequential-scan branch of the heap AM's copy callback, which opens a plain `table_beginscan` with `SnapshotAny` and **no scan keys**, and publishes the relation's total block count as `heap_blks_total`:

[heapam_handler.c#heapam_relation_copy_for_cluster](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L769-L782)

There is no visibility-map consultation anywhere in this path: `grep` for `visibilitymap` returns zero matches in all three files that make up the rewrite — [cluster.c](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1-L76), [heapam_handler.c](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L20-L50) (which holds the scan-and-copy loop), and [rewriteheap.c](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L1-L120). That is a correctness requirement, not an oversight: the rewrite must copy every live *and* recently-dead tuple, and an all-visible page still contains tuples that must move to the new relfilenode. Contrast plain `VACUUM`, whose `heap_blks_scanned` documentation explicitly says "the visibility map is used to optimize scans, some blocks will be skipped without inspection" [monitoring.sgml#heap_blks_scanned](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3803-L3813); the `pg_stat_progress_cluster` counterpart carries no such sentence [monitoring.sgml#pg_stat_progress_cluster](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L4026-L4032).

The scan visits every block exactly once. `initscan` fixes `rs_nblocks = RelationGetNumberOfBlocks()` [heapam.c#initscan](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L225-L231), and `heapgettup` walks forward with wraparound, terminating only when it returns to `rs_startblock` [heapam.c#heapgettup](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L728-L764). Each block costs exactly one `ReadBufferExtended` [heapam.c#heapgetpage](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L380-L383). An empty page is not special-cased: it is read, then `linesleft` is set from `PageGetMaxOffsetNumber` and the loop moves on [heapam.c:766-784](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L766-L784). A page with no line pointers at all gives `linesleft = 0` and is abandoned immediately; a page whose tuples were deleted and vacuumed still carries its line pointer array, so the loop walks it and rejects each entry on `ItemIdIsNormal` [heapam.c:651-700](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L651-L700). Either way the block is read once, and nothing about the page's emptiness removes that read.

There is also no prefetching to soften it. `PrefetchBuffer` appears nowhere in [cluster.c](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1-L76), [heapam_handler.c](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L20-L50) or [rewriteheap.c](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L1-L120), and the one call site in `heapam.c` sits in `heap_compute_xid_horizon_for_tuples`, an index-vacuum helper outside this path [heapam.c:6952-6958](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L6952-L6958). So v12 issues one 8 kB `ReadBufferExtended` at a time and relies on OS readahead for sequential throughput.

One subtlety worth knowing when watching progress: `SnapshotAny` is not an MVCC snapshot, so page-at-a-time mode is switched off [heapam.c:1160-1164](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L1160-L1164) and `heapgetpage` returns right after the read [heapam.c:385-386](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L385-L386) — which also means `heap_page_prune_opt` is *not* called on the old heap during the rewrite. Synchronized scanning can still start the scan mid-relation when the relation exceeds `NBuffers / 4` [heapam.c:245-296](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L245-L296), and because `heap_blks_scanned` is reported as `heapScan->rs_cblock + 1` [heapam_handler.c:815-821](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L815-L821), the progress counter can start high and wrap to 1. That counter is also updated per returned tuple rather than per block, which matters a great deal on this shape; see [How to observe the read volume on a v12 server](#how-to-observe-the-read-volume-on-a-v12-server). The block *count* read is unchanged.

### Heap size means the physical file, not pg_class.relpages

The read volume is set by `RelationGetNumberOfBlocks`, which for a table goes through `table_relation_size` and rounds up to whole blocks [bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2799-L2826), [bufmgr.h:198-199](../../../../raw/postgres-12/src/include/storage/bufmgr.h#L198-L199). That is a live `smgr` answer about the file on disk, not the possibly stale `pg_class.relpages` estimate. A heap whose `relpages` says 100 but whose file is 4 GB will be read as 4 GB.

### Write side: the new heap is sized by live rows

Every surviving tuple is reformed and handed to the rewrite module [heapam_handler.c#reform_and_rewrite_tuple](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2523-L2548), which fills one private page buffer and flushes it with `smgrextend` when the next tuple no longer fits:

[rewriteheap.c#raw_heap_insert](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L688-L728)

Three consequences for I/O accounting:

1. **The new heap bypasses shared buffers entirely.** `state->rs_buffer` is a `palloc(BLCKSZ)` scratch page [rewriteheap.c:270-273](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L270-L273) and each finished page goes straight to storage via `smgrextend(..., true)` — the `true` being `skipFsync`, because the rewrite fsyncs once at the end instead [rewriteheap.c:705-716](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L705-L716).
2. **Writes are strictly `ceil(live bytes / usable page bytes)` pages**, the last of which is the possibly-partial page that `end_heap_rewrite` flushes after the scan ends [rewriteheap.c:330-345](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L330-L345). Dead tuples never reach `raw_heap_insert`: `HEAPTUPLE_DEAD` short-circuits to `rewrite_heap_dead_tuple` and `continue` [heapam_handler.c:879-890](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L879-L890).
3. **The free space map is never consulted or written for the main fork**, because the rewrite does not go through `RelationGetBufferForTuple` at all: neither that function nor any free-space-map call appears in [rewriteheap.c](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L1-L120), whose only FSM reference is the `HEAP_INSERT_SKIP_FSM` flag it passes for TOAST inserts [rewriteheap.c:653-658](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L653-L658).

Tuples are also frozen on the way through, which costs no extra I/O beyond the page write [rewriteheap.c#rewrite_heap_tuple](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L405-L413); the cutoffs are computed aggressively because the table is being rewritten anyway [cluster.c:860-867](../../../../raw/postgres-12/src/backend/commands/cluster.c#L860-L867). This is why the docs call `FREEZE` redundant under `FULL` [vacuum.sgml#FREEZE](../../../../raw/postgres-12/doc/src/sgml/ref/vacuum.sgml#L113-L126).

### Page arithmetic for the new heap

The packing rule is exactly the `raw_heap_insert` test `len + saveFreeSpace > pageFreeSpace`, with:

- `len = MAXALIGN(heaptup->t_len)` [rewriteheap.c:673](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L673)
- `saveFreeSpace = BLCKSZ * (100 - fillfactor) / 100`, defaulting to fillfactor 100 and therefore 0 [rewriteheap.c:684-686](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L684-L686), [rel.h#RelationGetTargetPageFreeSpace](../../../../raw/postgres-12/src/include/utils/rel.h#L304-L309), [rel.h:278-279](../../../../raw/postgres-12/src/include/utils/rel.h#L278-L279)
- `pageFreeSpace = PageGetHeapFreeSpace(page)`, which is `pd_upper - pd_lower` minus one `ItemIdData` for the new line pointer, and zero once `MaxHeapTuplesPerPage` line pointers exist with none free [bufpage.c#PageGetHeapFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L664-L714), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L580-L597)

The new heap's fillfactor is inherited, because `make_new_heap` copies the old heap's reloptions [cluster.c:664-673](../../../../raw/postgres-12/src/backend/commands/cluster.c#L664-L673), [cluster.c:694-714](../../../../raw/postgres-12/src/backend/commands/cluster.c#L694-L714). With the constants `SizeOfPageHeaderData = 24` (from `PageHeaderData`: 8 + 2 + 2 + 2 + 2 + 2 + 2 + 4 before `pd_linp`) [bufpage.h#PageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L151-L164), [bufpage.h:216](../../../../raw/postgres-12/src/include/storage/bufpage.h#L216) and `sizeof(ItemIdData) = 4` [itemid.h#ItemIdData](../../../../raw/postgres-12/src/include/storage/itemid.h#L25-L30), the derived capacity of a default-fillfactor page is

```text
tuples_per_page = floor((BLCKSZ - SizeOfPageHeaderData) / (MAXALIGN(t_len) + 4))
                = floor(8168 / (MAXALIGN(t_len) + 4))
```

capped by `MaxHeapTuplesPerPage = floor(8168 / (MAXALIGN(SizeofHeapTupleHeader) + 4)) = 291` [htup_details.h#MaxHeapTuplesPerPage](../../../../raw/postgres-12/src/include/access/htup_details.h#L564-L576), [htup_details.h:184](../../../../raw/postgres-12/src/include/access/htup_details.h#L184). This arithmetic is derived from the cited rules, not measured on a server.

### WAL volume

The rewrite is WAL-logged only when WAL is genuinely needed for it:

```c
use_wal = XLogIsNeeded() && RelationNeedsWAL(NewHeap);
```

[heapam_handler.c:719-723](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L719-L723)

`XLogIsNeeded()` is the `wal_level >= WAL_LEVEL_REPLICA` test [xlog.h:177-181](../../../../raw/postgres-12/src/include/access/xlog.h#L177-L181), [xlog.h#WalLevel](../../../../raw/postgres-12/src/include/access/xlog.h#L159-L165), and `RelationNeedsWAL` is true only for permanent relations [rel.h#RelationNeedsWAL](../../../../raw/postgres-12/src/include/utils/rel.h#L515-L520). So at `wal_level = minimal`, the new heap generates **no WAL for its data at all** — the transient relfilenode is created and dropped inside the one transaction, so crash recovery only has to not find it. When WAL is needed, each new page is logged as one full-page image via `log_newpage` [rewriteheap.c:697-703](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L697-L703) plus the last page [rewriteheap.c:331-338](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L331-L338).

The critical point for this question: **WAL is proportional to the new heap, not the old one.** A 4 GB heap with a few thousand rows produces kilobytes of WAL for the heap, not gigabytes. The remaining WAL comes from catalog updates (`pg_class` rows for both relations, the relfilenode swap, `RelationClearMissing`) and from the index rebuilds.

TOAST inserts made during the rewrite follow the same decision, via `HEAP_INSERT_SKIP_WAL` when `rs_use_wal` is false [rewriteheap.c:653-668](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L653-L668).

### The fsync

Regardless of the WAL decision, the rewrite ends with an unconditional flush-and-fsync of the new relation for any WAL-logged table [rewriteheap.c:347-359](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L347-L359). `heap_sync` flushes buffers and calls `smgrimmedsync` for the main fork and, if present, the TOAST heap; the FSM is deliberately not synced [heapam.c#heap_sync](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L8937-L8961). On the shape in the question that is an fsync over a handful of pages.

### The old file is unlinked, not rewritten

`finish_heap_swap` exchanges relfilenodes rather than copying anything back [cluster.c#swap_relation_files](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1035-L1062), then drops the transient relation — which by then owns the *old*, multi-GB relfilenode — with `performDeletion` [cluster.c:1449-1458](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1449-L1458). Deletion is scheduled for commit, not executed inline [storage.c#RelationDropStorage](../../../../raw/postgres-12/src/backend/catalog/storage.c#L144-L160), which is why the code comment notes there is "no chance to reclaim disk space before commit" [cluster.c:1378-1392](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1378-L1392).

Two I/O facts follow:

- Any dirty old-heap buffers still resident are **discarded, not written**: `smgrdounlinkall` states that "bufmgr will just drop them without bothering to write the contents" [smgr.c#smgrdounlinkall](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L459-L463).
- The main fork's first segment is `ftruncate`d to zero and its real unlink deferred to after the next checkpoint, to protect the relfilenode number from reuse; additional 1 GB segments are unlinked on the spot in the `for (segno = 1;; segno++)` loop that runs until `ENOENT` [md.c#mdunlinkfork](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L284-L359), with the rationale spelled out for exactly this "CLUSTER and CREATE INDEX" fsync-not-WAL case [md.c:225-254](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L225-L254). Freeing multiple GB is therefore filesystem metadata work, not data movement.

### Index rebuild

After the swap, every index is rebuilt from scratch [cluster.c:1393-1410](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1393-L1410). `reindex_index` assigns a new relfilenode and calls `index_build` [index.c#reindex_index](../../../../raw/postgres-12/src/backend/catalog/index.c#L3526-L3530), and each AM's build does a full `table_index_build_scan` — for example B-tree [nbtsort.c:487-491](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L487-L491), hash [hash.c:165-168](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L165-L168), GiST [gistbuild.c:193-198](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L193-L198), GIN [gininsert.c:378-384](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L378-L384), SP-GiST [spginsert.c:126-128](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L126-L128), BRIN [brin.c:719-724](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L719-L724).

That scan is over the **new** heap, which is already tiny, so index-rebuild I/O is proportional to the surviving rows and not to the old heap. The comment in `finish_heap_swap` gives the design reason: rebuilding beats incremental index maintenance because the rewrite is effectively a bulk load [cluster.c:1378-1392](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1378-L1392). Note that this is where `maintenance_work_mem` matters for a `VACUUM FULL` — a B-tree build sizes its sort area from it [nbtsort.c:442-445](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L442-L445) — while the heap phase itself never sorts, because `use_sort` is false and the tuplesort is never created [heapam_handler.c:738-744](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L738-L744).

### TOAST

`vacuum_rel` deliberately does **not** recurse into the TOAST relation for a `FULL` vacuum: "In VACUUM FULL, though, the toast table is automatically rebuilt by cluster_rel so we shouldn't recurse to it" [vacuum.c:1792-1800](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1792-L1800). `make_new_heap` creates a fresh TOAST relation for the transient heap [cluster.c:725-751](../../../../raw/postgres-12/src/backend/commands/cluster.c#L725-L751), and because both heaps have one, the swap is done by content with `rd_toastoid` set so pointers and value OIDs are preserved [cluster.c:826-856](../../../../raw/postgres-12/src/backend/commands/cluster.c#L826-L856).

The data still moves. Any tuple carrying an external pointer goes through the toaster [rewriteheap.c:640-669](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L640-L669), and `toast_insert_or_update` fetches each external value back — "any external value we find still in the tuple must be someone else's that we cannot reuse ... Fetch it back" [tuptoaster.c:680-699](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L680-L699) — via `heap_tuple_fetch_attr` -> `toast_fetch_datum` [tuptoaster.c#heap_tuple_fetch_attr](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L100-L111), then re-saves it with `toast_save_datum` [tuptoaster.c:863-870](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L863-L870).

So TOAST I/O is:

- **Reads**: index-driven chunk fetches for live toasted values only. `toast_fetch_datum` opens the TOAST index and reads the chunks through `systable_beginscan_ordered` on `(valueid, chunkidx)` [tuptoaster.c#toast_fetch_datum](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L1904-L1935), so a bloated TOAST relation is never sequentially scanned and its dead chunks cost nothing. Those reads are random-ish rather than sequential.
- **Writes**: the live chunks re-inserted into the new TOAST relation, with `HEAP_INSERT_SKIP_FSM` so the FSM is not read or written [rewriteheap.c:653-658](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L653-L658), [hio.c:325](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L325), [hio.c:520-527](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L520-L527).

A near-empty main heap with a near-empty-but-huge TOAST relation therefore shrinks both, and still only reads the main heap in full.

### Worked example for the shape in the question

Derived from the cited packing rule, for a 4 GB heap (`524,288` blocks) holding 5,000 live rows and no TOAST, default fillfactor:

| Stored tuple length `t_len` | `MAXALIGN(t_len) + 4` | tuples/page | new heap pages | new heap bytes | read:write |
|---|---|---|---|---|---|
| 32 | 36 | 226 | 23 | 188,416 | ~22,800 : 1 |
| 48 | 52 | 157 | 32 | 262,144 | ~16,400 : 1 |
| 100 | 108 | 75 | 67 | 548,864 | ~7,800 : 1 |
| 500 | 508 | 16 | 313 | 2,564,096 | ~1,675 : 1 |

Reads stay at 4,294,967,296 bytes in every row of that table. Only the right-hand columns move. The table is arithmetic over cited definitions, not a measurement; see [Open Questions](#open-questions).

### Where the reads land in the buffer pool

Because the relation is multiple GB and therefore certainly larger than `NBuffers / 4`, `initscan` attaches a `BAS_BULKREAD` strategy [heapam.c:245-258](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L245-L258) — `table_beginscan` passes `SO_ALLOW_STRAT` [tableam.h#table_beginscan](../../../../raw/postgres-12/src/include/access/tableam.h#L736-L744). That ring is `256 * 1024 / BLCKSZ` = 32 buffers, further capped at `NBuffers / 8` [freelist.c#GetAccessStrategy](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L541-L588).

Practical effect: streaming 4 GB through the pool recycles the same 32 buffers, so a `VACUUM FULL` on a bloated table largely leaves the rest of the cache alone. The reads still hit the storage device once per block. The ring is not airtight, though: a ring buffer that is dirty and whose write would need a WAL flush is dropped out of the ring by `StrategyRejectBuffer`, which sets that slot to `InvalidBuffer` so the next allocation comes from the normal clock sweep and evicts a non-ring buffer [freelist.c#StrategyRejectBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L685-L704), [bufmgr.c:1122-1139](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1122-L1139). On this shape that is bounded by the hint-bit dirtying described below.

### Second-order writes to the old heap: hint bits

There is one way the old, doomed heap can generate writes. Every surviving-candidate tuple is visibility-tested with `HeapTupleSatisfiesVacuum` [heapam_handler.c:823-828](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L823-L828), and that function sets commit/abort hint bits, each of which calls `MarkBufferDirtyHint` [heapam_visibility.c#HeapTupleSatisfiesVacuum](../../../../raw/postgres-12/src/backend/access/heap/heapam_visibility.c#L1188-L1213), [heapam_visibility.c:1244-1253](../../../../raw/postgres-12/src/backend/access/heap/heapam_visibility.c#L1244-L1253), [heapam_visibility.c#SetHintBits](../../../../raw/postgres-12/src/backend/access/heap/heapam_visibility.c#L112-L131). A dirtied ring buffer is normally written when its slot is reused; only a buffer whose write would require a WAL flush is rejected and replaced [freelist.c#StrategyRejectBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L685-L696).

For the shape in the question this term is small and bounded by the number of *`LP_NORMAL` tuples* present, not by heap size: a page whose line pointers are all unused or dead never reaches `HeapTupleSatisfiesVacuum` at all, and a heap that reached this state through `DELETE` plus routine `VACUUM` generally has its remaining hint bits already set. Any such page still dirty at commit time is discarded rather than written [smgr.c#smgrdounlinkall](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L459-L463).

### No cost-based throttling applies to the rewrite

`vacuum_delay_point` is the only place a vacuum sleeps [vacuum.c#vacuum_delay_point](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1945-L1971), and it is **not called** anywhere in `cluster.c`, `rewriteheap.c`, or `heapam_handler.c` — the pinned tree's callers are `vacuumlazy.c`, `analyze.c`, the statistics type-analyze functions, and the index AMs' bulkdelete/cleanup routines. Buffer accesses accrue `VacuumCostBalance` only while `VacuumCostActive` is set, which requires `vacuum_cost_delay > 0` [bufmgr.c:767-772](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L767-L772), [bufmgr.c:959-961](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L959-L961), [vacuum.c:375-385](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L375-L385) — so at the v12 default of `0` the counters `VacuumPageHit`/`VacuumPageMiss` advance but the balance stays at zero. Either way, with no delay point in the path nothing sleeps.

So the gigabytes are read as fast as the device allows. Relevant settings and apply scopes:

| Setting | v12 default | Context | Apply scope | Effect on VACUUM FULL |
|---|---|---|---|---|
| `vacuum_cost_delay` | `0` | `PGC_USERSET` | session/transaction | none during the rewrite; if set above `0` the balance accrues there and can be paid off later by a `VACUUM (FULL, ANALYZE)`'s analyze phase, which does call `vacuum_delay_point` [analyze.c:1046](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1046) and is never reset in between [vacuum.c:375-385](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L375-L385) |
| `vacuum_cost_limit` | `200` | `PGC_USERSET` | session/transaction | same |
| `vacuum_cost_page_hit` / `_miss` / `_dirty` | `1` / `10` / `20` | `PGC_USERSET` | session/transaction | same |

Sources: [guc.c:3372-3381](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3372-L3381), [guc.c:2311-2319](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2311-L2319), [guc.c:2281-2309](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2281-L2309), plus `VacuumCostActive = (VacuumCostDelay > 0)` [vacuum.c:375-385](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L375-L385). `PGC_USERSET` maps to session/transaction scope: no restart and no reload is needed to change any of them.

### What VACUUM FULL never does here

- It does not truncate the old file in place. `TRUNCATE` and `INDEX_CLEANUP` are explicitly ignored under `FULL` [vacuum.sgml#INDEX_CLEANUP](../../../../raw/postgres-12/doc/src/sgml/ref/vacuum.sgml#L193-L203), [vacuum.sgml#TRUNCATE](../../../../raw/postgres-12/doc/src/sgml/ref/vacuum.sgml#L209-L224), and `RelationTruncate` appears nowhere in [rewriteheap.c](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L1-L120).
- It cannot be combined with `DISABLE_PAGE_SKIPPING`, which errors out [vacuum.c:262-268](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L262-L268) — consistent with there being no page skipping to disable.
- It does not read the old heap twice. One scan, one pass.

### How to observe the read volume on a v12 server

Use `pg_statio_all_tables.heap_blks_read`, not the progress view. `heap_blks_total` is honest — it is `rs_nblocks` published once at scan start [heapam_handler.c:779-781](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L779-L781), [monitoring.sgml:4018-4024](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L4018-L4024) — but `heap_blks_scanned` is **not a per-block counter**, and on a near-empty heap it badly under-reports the reads:

- The only write to it is inside the per-tuple loop, immediately after `table_scan_getnextslot` returns a tuple, and its value is that tuple's block number plus one [heapam_handler.c:810-821](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L810-L821).
- Blocks that return no tuple therefore produce no update at all. Under `SnapshotAny` a block returns a tuple only if it holds at least one `LP_NORMAL` line pointer [heapam.c:651-700](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L651-L700), so a page whose line pointers are all `LP_UNUSED` or `LP_DEAD` — the normal state after `DELETE` plus `VACUUM` — is invisible to the counter.
- Nothing sets the counter to `heap_blks_total` when the scan finishes; the loop simply ends and `end_heap_rewrite` runs [heapam_handler.c:923-974](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L923-L974).

So on a 4 GB heap holding a few thousand rows the counter sits unchanged across every run of tupleless blocks while those gigabytes stream past. Its final value is one past the block of the last tuple the scan returned, not the number of blocks read — which lands on `heap_blks_total` exactly when the relation's last block holds a live row, and stays at `0` when the relation holds no live row at all. Both end states were measured; see [What the progress view showed](#what-the-progress-view-showed) and [The extreme case: a 6.75 GB heap with no rows at all](#the-extreme-case-a-675-gb-heap-with-no-rows-at-all). The v12 documentation says only that the counter "advances when the phase is `seq scanning heap`" [monitoring.sgml:4026-4032](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L4026-L4032); it does not promise one increment per block, and the plain-`VACUUM` column's "skipped blocks are included in this total, so that this number will eventually become equal to `heap_blks_total`" sentence has no counterpart here [monitoring.sgml#heap_blks_scanned](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3803-L3813).

The progress view is still worth watching for `phase`, `heap_tuples_written` and `index_rebuild_count`. Note that in the `VACUUM FULL` path `heap_tuples_scanned` and `heap_tuples_written` are set from the same `*num_tuples` counter in one `pgstat_progress_update_multi_param` call, so they are always equal and neither counts dead tuples [heapam_handler.c:892-922](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L892-L922). All columns used below exist in v12's `pg_stat_progress_cluster` [system_views.sql#pg_stat_progress_cluster](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L967-L992).

```sql
BEGIN;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '2s';

SELECT /* wiki_vacuum_full_read_progress */
       p.pid,
       c.relname,
       p.command,
       p.phase,
       p.heap_blks_total,
       p.heap_blks_scanned,
       p.heap_tuples_scanned,
       p.heap_tuples_written,
       p.index_rebuild_count
  FROM pg_stat_progress_cluster p
  JOIN pg_class c ON c.oid = p.relid;
COMMIT;
```

The read count itself comes from `pg_statio_all_tables.heap_blks_read` / `heap_blks_hit`, taken before and after the command. Those are fed by the `pgstat_count_buffer_read` / `pgstat_count_buffer_hit` calls inside `ReadBufferExtended`, so every block the rewrite reads is counted exactly once [bufmgr.c:660-669](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L660-L669), [system_views.sql#pg_statio_all_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L623-L646):

```sql
BEGIN;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '2s';

SELECT /* wiki_vacuum_full_io_counters */
       relid,
       schemaname,
       relname,
       heap_blks_read,
       heap_blks_hit,
       toast_blks_read,
       toast_blks_hit,
       idx_blks_read,
       idx_blks_hit
  FROM pg_statio_all_tables
 WHERE schemaname = 'public'
   AND relname = 'your_table';
COMMIT;
```

Both statements were checked against the pinned checkout's view definitions and column names; neither was executed, since this answer is source-only by request. The `BEGIN` / `COMMIT` wrapper is required for the timeouts to apply: at top level outside a transaction block, `SET LOCAL` calls `WarnNoTransactionBlock` [guc.c:8115-8123](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L8115-L8123), which raises `WARNING: SET LOCAL can only be used in transaction blocks` and leaves the following statement untimed [xact.c#CheckTransactionBlock](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L3404-L3430).

### What the command leaves behind

`swap_relation_files` swaps `relpages`, `reltuples`, and `relallvisible` between the two `pg_class` rows [cluster.c:1131-1148](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1131-L1148), and `copy_table_data` had already written the new heap's real page and tuple counts — `relpages` and `reltuples` only, never `relallvisible` [cluster.c:950-972](../../../../raw/postgres-12/src/backend/commands/cluster.c#L950-L972). Since the rewrite never touches the visibility map, the new heap has no VM fork and `relallvisible` lands at 0. The first plain `VACUUM` afterwards therefore reads the whole (now tiny) heap: with no VM fork, `visibilitymap_get_status` returns 0 for every block [visibilitymap.c#visibilitymap_get_status](../../../../raw/postgres-12/src/backend/access/heap/visibilitymap.c#L329-L356), [visibilitymap.c#vm_readbuf](../../../../raw/postgres-12/src/backend/access/heap/visibilitymap.c#L553-L587), so `lazy_scan_heap` finds nothing skippable [vacuumlazy.c:609-636](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L609-L636). `VACUUM (FULL, VERBOSE)` reports the old block count in its own message, using `RelationGetNumberOfBlocks(OldHeap)` [cluster.c:934-943](../../../../raw/postgres-12/src/backend/commands/cluster.c#L934-L943).

### Test coverage in the pinned tree

`VACUUM FULL` is exercised for correctness in [vacuum.sql:22](../../../../raw/postgres-12/src/test/regress/sql/vacuum.sql#L22), [vacuum.sql:70-74](../../../../raw/postgres-12/src/test/regress/sql/vacuum.sql#L70-L74), [vacuum.sql:144-145](../../../../raw/postgres-12/src/test/regress/sql/vacuum.sql#L144-L145), and for invalid-index behavior in [create_index.sql:495-499](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L495-L499). There is **no test of I/O volume, block counts, or progress-view output**: `pg_stat_progress_cluster` appears in the test tree only as a view-definition dump [rules.out:1849](../../../../raw/postgres-12/src/test/regress/expected/rules.out#L1849). The read-everything property is therefore guaranteed by the code path, not by a regression test.

## Follow-Up: Measured On A 12.2 Server

**The hypothesis is confirmed, exactly.** On a 884,956-block heap whose pages were all empty and all frozen, `VACUUM FULL` read **884,956 blocks** — every one — and the operating system delivered **7,249,559,552 bytes** to the backend, which is the heap file's size to the byte. A plain `VACUUM` on the identical heap read **0 blocks**. Being empty and being frozen each cost the rewrite nothing.

| Command, same 7,249,559,552-byte heap | Blocks read | Device bytes read | Duration |
|---|---|---|---|
| `VACUUM FULL` (cold page cache) | 884,956 | 7,249,559,552 | 2.15 s |
| `VACUUM FULL` (warm page cache) | 884,956 | 0 | 1.25 s |
| `VACUUM` | 0 | 0 | 0.017 s |
| `VACUUM (DISABLE_PAGE_SKIPPING)` | 884,956 | 7,249,559,552 | 57.27 s (cost-delayed) |

### What was built and run

12.2 was built out of tree from the pinned checkout, so `raw/postgres-12/` was never written to:

- Source: `git archive` of `raw/postgres-12` at `45b88269a353ad93744772791feb6d01bc7e1e42`, tag `REL_12_2`, `git status --porcelain` empty before and after.
- Build: `./configure --without-readline --without-zlib CFLAGS="-O2"`, then `make`, `make install`, `make -C contrib install`. `SELECT version()` reported `PostgreSQL 12.2 on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit`.
- Cluster: `shared_buffers = 128MB`, `maintenance_work_mem = 1GB`, `wal_level = minimal` (one run at `replica`), `max_wal_size = 4GB`, `autovacuum = off`, `track_io_timing = on`, `fsync` left at its default `on`, `vacuum_cost_delay` left at its v12 default `0`, `block_size` 8192.
- Extensions used for inspection only: `pageinspect`, `pg_visibility`, `pgstattuple`, `pg_freespacemap`.
- Three independent measurement channels per command: `pg_statio_all_tables` and `pg_stat_database` before/after; `/proc/<backend pid>/io` sampled every 100 ms; and `pg_stat_progress_cluster` sampled every 20 ms over one long-lived connection. Both counter families are fed from `ReadBufferExtended`, which calls `pgstat_count_buffer_read` before dispatching on the fork number [bufmgr.c:660-669](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L660-L669) — so a relation's visibility-map and free-space-map reads land in the same `heap_blks_read` column as its main fork, which is why one early run read 28 blocks more than the heap has: 229,376 bytes of visibility map is exactly 28 blocks, and the snapshot query itself was reading it.
- The page cache was controlled with `posix_fadvise(POSIX_FADV_DONTNEED)` over the relation's seven segment files (no privileges required), so "cold" means the block layer really had to deliver the bytes and `read_bytes` counts them.
- `VACUUM FULL` was run **seven times**. The four comparable runs at `wal_level = minimal` agree to the byte on `heap_blks_read` (884,956), `rchar` (7,250,034,354), `syscr` (885,019) and WAL (84,720). Only `read_bytes` differs among them, and only because one of the four was run against a warm page cache on purpose.

### The fixture: 884,956 blocks holding 200,000 rows

```sql
CREATE TABLE bloat (id bigint NOT NULL);
INSERT INTO bloat SELECT g FROM generate_series(1, 200000000) g;
DELETE FROM bloat WHERE id <= 199800000;   -- 99.9%, keeping the physically last rows
VACUUM (VERBOSE) bloat;
VACUUM (FREEZE, VERBOSE) bloat;
```

| Stage | Heap bytes | Heap blocks | Live rows | Note |
|---|---|---|---|---|
| After load | 7,249,559,552 | 884,956 | 200,000,000 | 226 tuples/page, 124.5 s |
| After `DELETE` of 199,800,000 rows | 7,249,559,552 | 884,956 | 200,000 | 97.6 s, read all 884,956 blocks |
| After `VACUUM` | 7,249,559,552 | 884,956 | 200,000 | 27.0 s, **no truncation** |
| After `VACUUM FREEZE` | 7,249,559,552 | 884,956 | 200,000 | 0.05 s, all 884,956 pages all-frozen |

The load reproduces the [worked example](#worked-example-for-the-shape-in-the-question) exactly. `pageinspect` reports `lp_len = 32` for all 170 tuples on the last page with `t_hoff = 24`, so `MAXALIGN(t_len) + 4 = 36` and the predicted `floor(8168 / 36) = 226` tuples per page is what the loader produced: 200,000,000 rows in 884,956 blocks is 225.99994 tuples per block.

Keeping the tail rows worked as intended. `VACUUM` reported `"bloat": removed 199800000 row versions in 884071 pages` and left the relation at its full 884,956 blocks, because `should_attempt_truncation` measures `rel_pages - nonempty_pages` and the last page is not empty [vacuumlazy.c#should_attempt_truncation](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1851-L1866), [vacuumlazy.c:313-314](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L313-L314).

`VACUUM FREEZE` then took **50 ms** and reported `found 0 removable, 200000 nonremovable row versions in 886 out of 884956 pages` with `Skipped 0 pages due to buffer pins, 884070 frozen pages`. An aggressive vacuum may still skip all-frozen pages [vacuumlazy.c#lazy_scan_heap](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L575-L578), [vacuumlazy.c:616-622](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L616-L622), and the earlier plain `VACUUM` had already frozen the 884,070 emptied pages. It read 821 blocks. Afterwards `pg_visibility_map_summary` reported `all_visible = all_frozen = 884956`: every page in the relation was marked frozen before the rewrite ran.

One side effect worth naming, because it makes `reltuples` untrustworthy on this shape: `VACUUM FREEZE` scanned 886 pages and wrote `pg_class.reltuples = 399800` for a table holding 200,000 rows, because a partial scan extrapolates the old density over the unscanned pages instead of using the count it saw [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1058-L1086).

### Result: VACUUM FULL read every block

```text
INFO:  vacuuming "public.bloat"
INFO:  "bloat": found 0 removable, 200000 nonremovable row versions in 884956 pages
DETAIL:  0 dead row versions cannot be removed yet.
CPU: user: 0.41 s, system: 1.54 s, elapsed: 2.12 s.
```

| Channel | Cold page cache | Warm page cache |
|---|---|---|
| `pg_statio_all_tables.heap_blks_read` | **884,956** | **884,956** |
| `pg_statio_all_tables.heap_blks_hit` | 0 | 0 |
| `/proc/<pid>/io` `rchar` | 7,250,034,354 | 7,250,034,354 |
| `/proc/<pid>/io` `syscr` | 885,019 | 885,019 |
| `/proc/<pid>/io` `read_bytes` | **7,249,559,552** | **0** |
| `pg_stat_database.blk_read_time` | 1,169.40 ms | 105.20 ms |
| Duration | 2.15 s | 1.25 s |

Three things follow from that pair of columns.

1. **The read count is the whole relation, not the live data.** 884,956 blocks read against 200,000 live rows occupying 886 blocks. The 884,070 leading blocks contained no live tuple, were marked all-visible and all-frozen, and were read anyway — there is no visibility-map consultation in the rewrite path, as [Read side: the whole heap, every block, no skip path](#read-side-the-whole-heap-every-block-no-skip-path) sets out.
2. **The syscall counts decompose to one 8 kB read per block.** Subtracting the heap leaves `885,019 - 884,956 = 63` read calls and `7,250,034,354 - 7,249,559,552 = 474,802` bytes, which is the backend's own catalog and configuration reading; the remaining 884,956 calls carry exactly 8192 bytes each. The rewrite issues them one at a time, as [heapgetpage](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L380-L383) implies, and `read_bytes` reaching precisely the file size confirms nothing was coalesced away below it.
3. **The OS page cache changes only where the bytes come from.** Warm, the device delivered nothing and the command still made all 885,019 read calls and still counted 884,956 buffer misses, because `shared_buffers` is 128 MB and the `BAS_BULKREAD` ring recycles 32 buffers. The 1.7x wall-clock difference is the entire benefit; the read volume is identical.

### Control: the same heap, a plain VACUUM, zero blocks

Immediately before the rewrite, on the identical relation:

```text
INFO:  "bloat": found 0 removable, 170 nonremovable row versions in 1 out of 884956 pages
Skipped 0 pages due to buffer pins, 884955 frozen pages.
```

`heap_blks_read` moved by **0** and the command took **17 ms**. Plain `VACUUM` skipped 884,955 of 884,956 pages on the visibility map and touched only the last page, which it is forced to look at when truncation is possible [vacuumlazy.c:655-657](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L655-L657). This is the cleanest available demonstration that the visibility map was fully populated and would have permitted skipping: the same map that let `VACUUM` read nothing let `VACUUM FULL` read 6.75 GB.

### The extreme case: a 6.75 GB heap with no rows at all

The `vacuum_truncate` reloption makes the pure case reachable: it is read by `vacuum_rel` into `params->truncate` [vacuum.c:1782-1790](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1782-L1790), which `should_attempt_truncation` checks first [vacuumlazy.c:1852-1857](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1852-L1857), and it takes only `ShareUpdateExclusiveLock` [reloptions.c#vacuum_truncate](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L152-L160).

```sql
ALTER TABLE bloat SET (vacuum_truncate = off);
DELETE FROM bloat;
VACUUM bloat;   -- 884,956 blocks retained, 0 live rows, all_visible = all_frozen = 884956
```

`VACUUM FULL` on that heap:

| Measurement | Value |
|---|---|
| VERBOSE | `found 0 removable, 0 nonremovable row versions in 884956 pages` |
| `heap_blks_read` + `heap_blks_hit` | 884,038 + 918 = **884,956** |
| `read_bytes` | **7,249,559,552** |
| New heap size | **0 bytes, 0 blocks** |
| `pg_stat_progress_cluster.heap_blks_scanned`, all 94 samples | **0** of 884,956 |
| Duration | 1.97 s |

6.75 GB was read from disk to produce a zero-byte file. `end_heap_rewrite` writes a final page only `if (state->rs_buffer_valid)`, and with no tuple ever inserted that flag is never set [rewriteheap.c#end_heap_rewrite](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L330-L345), so the write side collapsed to nothing while the read side did not move at all.

### Writes, WAL, and the fsync

| Quantity | `wal_level = minimal` | `wal_level = replica` |
|---|---|---|
| Old heap read | 7,249,559,552 bytes | 7,249,559,552 bytes |
| New heap written | 7,249,920 bytes (885 blocks) | 7,249,920 bytes (885 blocks) |
| Backend `write_bytes` | 7,323,648 | 14,598,144 |
| WAL generated | **84,720 bytes** | **7,377,944 bytes** |
| Read : new-heap-write | **999.95 : 1** | **999.95 : 1** |

`ceil(200000 / 226) = 885`, which is what the rewrite produced, so the packing rule in [Page arithmetic for the new heap](#page-arithmetic-for-the-new-heap) is confirmed on a real relation.

`pg_waldump --stats=record` over the exact LSN range of the `replica` run decomposes its 7,377,944 bytes:

| Record type | Count | Combined bytes | Share |
|---|---|---|---|
| `XLOG/FPI` | **885** | 7,264,605 | 98.84% |
| `Btree/INSERT_LEAF` | 32 | 58,986 | 0.80% |
| `Heap/INSERT` | 13 | 23,209 | 0.32% |
| `Transaction/COMMIT` | 1 | 949 | 0.01% |
| everything else (`Heap/DELETE`, `Heap/UPDATE`, `Heap/HOT_UPDATE`, `Btree/INSERT_UPPER`, `Btree/SPLIT_R`, `Storage/CREATE`, `Standby/LOCK`, `Standby/RUNNING_XACTS`, `XLOG/NEXTOID`) | 23 | 2,195 | 0.03% |
| **Total** | **954** | **7,349,944** | 100% |

**885 full-page images for 885 new pages**, one each, exactly as `raw_heap_insert` and `end_heap_rewrite` log them [rewriteheap.c:697-703](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L697-L703), [rewriteheap.c:331-338](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L331-L338). Not one WAL record describes the 884,956 blocks that were read, and the remaining 69 records are catalog churn plus the `Storage/CREATE` of the new relfilenode. At `minimal` the same command logged 84,720 bytes, 87 times less, because `use_wal` is false [heapam_handler.c:719-723](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L719-L723).

### What the progress view showed

`pg_stat_progress_cluster` was sampled every 20 ms through the rewrite. On the main fixture:

| Samples | `phase` | `heap_blks_total` | `heap_blks_scanned` | `heap_tuples_scanned` |
|---|---|---|---|---|
| 49 | `seq scanning heap` | 884,956 | **0** | 0 |
| 1 | `seq scanning heap` | 884,956 | 884,441 | 83,620 |
| 1 | `seq scanning heap` | 884,956 | 884,956 | 200,000 |

For 49 of 51 samples — roughly the first 96% of the command — the counter reported that **zero** blocks had been scanned out of 884,956, while the backend was demonstrably reading gigabytes. It then jumped to the full count inside the last ~40 ms, when the scan finally reached block 884,070 and started returning tuples. That is the behavior [How to observe the read volume on a v12 server](#how-to-observe-the-read-volume-on-a-v12-server) predicts from the update site, which sits inside the per-tuple branch and writes `heapScan->rs_cblock + 1` [heapam_handler.c:810-821](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L810-L821). Plain `VACUUM` has no such defect: its counterpart is updated once per block, before the page is even examined [vacuumlazy.c:659](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L659).

`pg_statio_all_tables.heap_blks_read` was correct in every run, which is why the answer above recommends it.

### The index rebuild reads the new heap

With one `bigint` B-tree present, `CREATE INDEX` on the bloated heap read 884,984 blocks — the whole 884,956-block heap plus the 28-block visibility map, which `index_update_stats` reads through `visibilitymap_count` to refresh `relallvisible` [index.c#index_update_stats](../../../../raw/postgres-12/src/backend/catalog/index.c#L2761-L2770) — and produced a 4,513,792-byte index.

The `VACUUM FULL` that followed read **885,745** heap blocks with 96 hits. That decomposes exactly:

```text
884,956  old heap, the sequential scan
    885  new heap, read back by the B-tree build (789 misses + 96 hits)
------
885,745  heap_blks_read delta, plus 96 hits
```

`idx_blks_read` stayed at **0**: the old index was never read, only dropped and rebuilt, and the rebuilt index came out at the same 4,513,792 bytes. The progress view showed the `rebuilding index` phase after `seq scanning heap`. So the index-rebuild term is proportional to the surviving rows, as [Index rebuild](#index-rebuild) argues from `reindex_relation` running after the swap.

### No cost-based delay reaches the rewrite

Both commands below ran on the same fixture with `vacuum_cost_delay = 1ms` and `vacuum_cost_limit = 200` set in the session, and both read the same 7,249,559,552 bytes from the device:

| Command | Duration | `heap_blks_read` | Decomposition |
|---|---|---|---|
| `VACUUM (FULL) bloat` | **2.05 s** | 884,956 | the heap, and nothing else |
| `VACUUM (DISABLE_PAGE_SKIPPING) bloat` | **57.27 s** | 885,204 | 884,956 heap + 28 visibility map + 220 free space map |

A 27.9x difference on identical heap I/O. `DISABLE_PAGE_SKIPPING` forces the same total read by bypassing the visibility-map lookup outright [vacuumlazy.c:609-611](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L609-L611), [vacuumlazy.c:665](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L665), and then pays the cost delay at every `vacuum_delay_point`. The rewrite has no such call site, so its 2.05 s is indistinguishable from the 2.15 s it takes with the delay at its default `0`. Cost-based throttling is not a lever on `VACUUM FULL`.

### What happened to the old file

The 7,249,559,552-byte relation occupied seven segment files: six of 1,073,741,824 bytes and one of 807,108,608. Listing the directory immediately after the command committed, before any checkpoint:

```text
-rw------- 1 ... 0        16438      <- old relfilenode, truncated to zero
-rw------- 1 ... 7249920  16441      <- new relfilenode
(16438.1 through 16438.6 are already gone)
```

After an explicit `CHECKPOINT`, `16438` disappeared too. That is precisely the two-part behavior of `mdunlinkfork`: the first segment is truncated and its unlink deferred past the next checkpoint to protect the relfilenode number, while the higher-numbered segments are unlinked on the spot [md.c#mdunlinkfork](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L284-L359). Reclaiming 6.75 GB cost no data movement.

The forks went with it: `vm_fork_bytes` 229,376 -> 0 and `fsm_fork_bytes` 1,802,240 -> 0, and `relallvisible` 884,956 -> 0. The next plain `VACUUM` therefore reported `found 0 removable, 200000 nonremovable row versions in 885 out of 885 pages` with `Skipped 0 pages due to buffer pins, 0 frozen pages` — it could not skip a single page, and it rebuilt an 8,192-byte visibility map. That confirms [What the command leaves behind](#what-the-command-leaves-behind).

### Retained line pointers, measured

Before this run, the page listed "how many line pointers per page survive `DELETE` plus `VACUUM` in practice" as an open question. The answer on this fixture is **all of them**:

| Probe | Result |
|---|---|
| `page_header` of block 100 | `lower = 928`, `upper = 8192` |
| `heap_page_items` of block 100 | 226 line pointers, 226 `LP_UNUSED`, 0 `LP_NORMAL`, 0 bytes of tuple data |
| 101-page sample across blocks 0 to 884,069 | min = max = **226** line pointers, 0 live tuples |
| Last block 884,955 | 170 line pointers, all `LP_NORMAL`, all with `t_infomask & 0x0300` set (frozen) |

`lower = 928` is `24 + 226 * 4`: the page header plus a full-width line pointer array with nothing behind it. This is `PageRepairFragmentation` keeping its promise not to remove unused line pointers [bufpage.c#PageRepairFragmentation](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L471-L482), and it means the rewrite's scan walked 226 `ItemIdIsNormal` tests per page across 884,070 pages — about 200 million rejected line pointers — on top of the reads.

It also has a visible consequence for bloat measurement. `pgstattuple` on the pre-rewrite heap returned `tuple_percent` 0.09 and `free_percent` **88.53**, not ~99.9: the retained arrays occupy 928 of every 8192 bytes, or 11.33%, and no free-space accounting counts them as free.

### What the measurements corrected

- **`heap_blks_scanned` does not necessarily end below `heap_blks_total`.** The answer above said it does. Measured, the final value is the last returned tuple's block number plus one, so it ended at exactly 884,956 of 884,956 on the fixture whose last block holds live rows, and at **0** of 884,956 on the zero-row fixture. The under-reporting is real and severe, but it is a during-the-scan property, not an end-state one. The sentence has been corrected in place.
- **The doc's "extra disk space approximately equal to the size of the table" is quantifiably wrong here**, as the open question on that conflict predicted from source. The transient heap was 7,249,920 bytes against an old relation of 7,249,559,552: **0.0001** of the table, not ~1.0.
- **The hint-bit write term was nil on this shape**, where the page had left it unquantified. On a fully frozen heap the backend's `write_bytes` was 7,323,648, against a new heap of 7,249,920 — leaving 73,728 bytes for everything else, so no meaningful old-heap dirtying occurred. This bounds the term for a frozen heap only; a heap carrying unset hint bits was not tested.
- **The multi-segment path is no longer only read, it is exercised.** The relation really did occupy seven segment files, and the truncate-plus-deferred-unlink split was observed directly.
- **The `t_len = 32` row of the worked example is confirmed**, and the read:write ratio it predicts for that row (~22,800:1 at 5,000 rows) is consistent with the 999.95:1 measured here at 200,000 rows, since the write side scales with the live row count and the read side does not.

### How to reproduce

The sandbox was deleted after the run, so the fixture is published in full. It needs a throwaway 12.2 cluster built from `raw/postgres-12/`; do not run it against anything you care about, since it writes ~7 GB and holds `AccessExclusiveLock`.

```sql
-- Fixture. Approximately 7 GB of heap plus WAL; takes a few minutes.
CREATE TABLE bloat (id bigint NOT NULL);
INSERT INTO bloat SELECT g FROM generate_series(1, 200000000) g;
DELETE FROM bloat WHERE id <= 199800000;
VACUUM (VERBOSE) bloat;
VACUUM (FREEZE, VERBOSE) bloat;

SELECT /* wiki_vf_fixture_state */
       pg_relation_size('bloat')        AS heap_bytes,
       pg_relation_size('bloat') / 8192 AS heap_blocks,
       (SELECT count(*) FROM bloat)     AS live_rows,
       (SELECT all_visible FROM pg_visibility_map_summary('bloat')) AS all_visible,
       (SELECT all_frozen  FROM pg_visibility_map_summary('bloat')) AS all_frozen;
```

Take `heap_blks_read` before and after the rewrite with the statement already published under [How to observe the read volume on a v12 server](#how-to-observe-the-read-volume-on-a-v12-server), and read the backend's own byte counters from `/proc`:

```sql
BEGIN;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '2s';

SELECT /* wiki_vf_backend_pid */ pid, application_name, state, query
  FROM pg_stat_activity
 WHERE query LIKE '%VACUUM%' AND pid <> pg_backend_pid();
COMMIT;
```

```bash
# Cold-cache reads: evict the relation, then watch the backend's counters.
#   base/<db>/<relfilenode> comes from SELECT pg_relation_filepath('bloat');
python3 - "$PGDATA/base/16384/16438" <<'PY'
import os, sys
base = sys.argv[1]
for p in [base] + [f"{base}.{i}" for i in range(1, 64)]:
    if os.path.exists(p):
        fd = os.open(p, os.O_RDONLY)
        os.fsync(fd); os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED); os.close(fd)
PY
grep -E 'rchar|syscr|read_bytes' /proc/<backend pid>/io   # before and after
```

The `VACUUM (FULL, VERBOSE)` line count is the fourth channel and needs no tooling: it prints the old relation's block count directly, from `RelationGetNumberOfBlocks(OldHeap)` [cluster.c:934-943](../../../../raw/postgres-12/src/backend/commands/cluster.c#L934-L943).

## Context Reviewed

- Dispatch and locking: [vacuum.c](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1620-L1700), including the `FULL` lock mode, the TOAST-recursion suppression, and the `DISABLE_PAGE_SKIPPING` rejection.
- Rewrite driver: all of [cluster.c](../../../../raw/postgres-12/src/backend/commands/cluster.c#L255-L434) `cluster_rel`, `rebuild_relation`, `make_new_heap`, `copy_table_data`, `swap_relation_files`, `finish_heap_swap`.
- Heap AM copy callback and its registration: [heapam_handler.c](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L690-L979), [heapam_handler.c:2640](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2640).
- Rewrite module: [rewriteheap.c](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L240-L757) `begin_heap_rewrite`, `end_heap_rewrite`, `rewrite_heap_tuple`, `raw_heap_insert`.
- Sequential-scan mechanics: [heapam.c](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L205-L320) `initscan`, [heapam.c:355-386](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L355-L386) `heapgetpage`, all of [heapam.c:486-785](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L486-L785) `heapgettup` including the `ItemIdIsNormal` skip and the per-page `linesleft` reset.
- Buffer strategy and stats: [freelist.c](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L537-L704), [bufmgr.c:640-970](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L640-L970), [bufmgr.c:1090-1160](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1090-L1160) the ring-reject path, [bufmgr.c:2790-2837](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2790-L2837).
- Storage teardown: [storage.c](../../../../raw/postgres-12/src/backend/catalog/storage.c#L143-L170), [smgr.c](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L419-L473), [md.c](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L220-L362).
- Page and tuple limits, and line pointer retention: [bufpage.c](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L439-L720) including `PageRepairFragmentation`, [bufpage.h](../../../../raw/postgres-12/src/include/storage/bufpage.h#L110-L220), [htup_details.h](../../../../raw/postgres-12/src/include/access/htup_details.h#L550-L580), [itemid.h](../../../../raw/postgres-12/src/include/storage/itemid.h#L17-L33), [rel.h](../../../../raw/postgres-12/src/include/utils/rel.h#L270-L312).
- Visibility map after the swap: [visibilitymap.c](../../../../raw/postgres-12/src/backend/access/heap/visibilitymap.c#L309-L367), [visibilitymap.c:547-587](../../../../raw/postgres-12/src/backend/access/heap/visibilitymap.c#L547-L587), [vacuumlazy.c:560-736](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L560-L736).
- WAL-level and persistence predicates: [xlog.h](../../../../raw/postgres-12/src/include/access/xlog.h#L159-L199), [rel.h:515-520](../../../../raw/postgres-12/src/include/utils/rel.h#L515-L520).
- `SET LOCAL` scope for the observability statements: [guc.c:8110-8125](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L8110-L8125), [xact.c:3367-3430](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L3367-L3430).
- TOAST: [tuptoaster.c](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L640-L880), [tuptoaster.c:1890-1990](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L1890-L1990) `toast_fetch_datum`, [hio.c](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L286-L330).
- Index rebuild entry points: [index.c](../../../../raw/postgres-12/src/backend/catalog/index.c#L3433-L3540), plus each AM's `table_index_build_scan` call.
- GUCs: [guc.c](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2280-L2320), [guc.c:3372-3392](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3372-L3392).
- Docs: [vacuum.sgml](../../../../raw/postgres-12/doc/src/sgml/ref/vacuum.sgml#L60-L230), [maintenance.sgml](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L120-L240), [monitoring.sgml](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3780-L4090).
- Catalog views: [system_views.sql](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L590-L995).
- Tests: [vacuum.sql](../../../../raw/postgres-12/src/test/regress/sql/vacuum.sql#L18-L150), [create_index.sql](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L490-L505), [rules.out](../../../../raw/postgres-12/src/test/regress/expected/rules.out#L1845-L1855).

Added for the measured follow-up:

- Truncation control: [vacuumlazy.c#should_attempt_truncation](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1832-L1875) and its two call sites [vacuumlazy.c:313-314](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L313-L314), [vacuumlazy.c:655-657](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L655-L657); the `vacuum_truncate` reloption definition [reloptions.c](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L84-L160) and its resolution into `VacuumParams` [vacuum.c:1770-1790](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1770-L1790).
- Page-skipping in plain `VACUUM`, for the control runs: the aggressive/all-frozen rule [vacuumlazy.c:566-596](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L566-L596), the two skip loops [vacuumlazy.c:609-622](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L609-L622), [vacuumlazy.c:661-678](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L661-L678), the `DISABLE_PAGE_SKIPPING` -> `aggressive` promotion [vacuumlazy.c:245-256](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L245-L256), and the per-block progress update [vacuumlazy.c:659](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L659).
- `reltuples` after a partial scan: [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1058-L1110).
- Where `CREATE INDEX` reads the visibility map: [index.c#index_update_stats](../../../../raw/postgres-12/src/backend/catalog/index.c#L2656-L2680), [index.c:2761-2770](../../../../raw/postgres-12/src/backend/catalog/index.c#L2761-L2770).
- Why a tupleless rewrite writes no page at all: [rewriteheap.c#end_heap_rewrite](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L330-L345).

## Evidence Map

| Claim | Evidence |
|---|---|
| `VACUUM FULL` is `CLUSTER` with no index | [vacuum.c:1816-1828](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1816-L1828), [cluster.c:261-266](../../../../raw/postgres-12/src/backend/commands/cluster.c#L261-L266) |
| It takes `AccessExclusiveLock` | [vacuum.c:1680-1681](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1680-L1681) |
| No sort, so no temp-file I/O in the heap phase | [cluster.c:891-894](../../../../raw/postgres-12/src/backend/commands/cluster.c#L891-L894), [heapam_handler.c:738-744](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L738-L744) |
| Plain seq scan with `SnapshotAny`, no scan keys | [heapam_handler.c:769-782](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L769-L782) |
| `heap_blks_total` is the whole relation | [heapam_handler.c:779-781](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L779-L781), [monitoring.sgml:4018-4024](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L4018-L4024) |
| No visibility-map skipping in the rewrite | zero `visibilitymap` matches in [cluster.c](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1-L76), [heapam_handler.c](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L20-L50) and [rewriteheap.c](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L1-L120); contrast [monitoring.sgml:3803-3813](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3803-L3813) |
| Every block is read exactly once | [heapam.c:225-231](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L225-L231), [heapam.c:728-764](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L728-L764), [heapam.c:380-383](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L380-L383) |
| Vacuumed-empty pages keep their line pointers, so the scan walks the array and skips on `ItemIdIsNormal` | [bufpage.c:471-482](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L471-L482), [heapam.c:651-700](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L651-L700), [heapam.c:766-784](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L766-L784) |
| Page-mode off under `SnapshotAny`, so no opportunistic pruning | [heapam.c:1160-1164](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L1160-L1164), [heapam.c:385-386](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L385-L386) |
| Read volume is the physical file size | [bufmgr.c:2799-2826](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2799-L2826), [bufmgr.h:198-199](../../../../raw/postgres-12/src/include/storage/bufmgr.h#L198-L199) |
| New pages written by `smgrextend`, outside shared buffers | [rewriteheap.c:270-273](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L270-L273), [rewriteheap.c:705-716](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L705-L716) |
| Dead tuples are never written | [heapam_handler.c:879-890](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L879-L890) |
| Packing rule and fillfactor inheritance | [rewriteheap.c:673](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L673), [rewriteheap.c:684-693](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L684-L693), [rel.h:304-309](../../../../raw/postgres-12/src/include/utils/rel.h#L304-L309), [cluster.c:664-673](../../../../raw/postgres-12/src/backend/commands/cluster.c#L664-L673) |
| Page free-space accounting | [bufpage.c:580-597](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L580-L597), [bufpage.c:664-714](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L664-L714), [bufpage.h:151-164](../../../../raw/postgres-12/src/include/storage/bufpage.h#L151-L164), [itemid.h:25-30](../../../../raw/postgres-12/src/include/storage/itemid.h#L25-L30) |
| `MaxHeapTuplesPerPage` cap | [htup_details.h:564-576](../../../../raw/postgres-12/src/include/access/htup_details.h#L564-L576) |
| WAL only when `XLogIsNeeded()`, one FPI per new page | [heapam_handler.c:719-723](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L719-L723), [rewriteheap.c:697-703](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L697-L703), [xlog.h:177-181](../../../../raw/postgres-12/src/include/access/xlog.h#L177-L181), [rel.h:515-520](../../../../raw/postgres-12/src/include/utils/rel.h#L515-L520) |
| Unconditional fsync of the new heap and its TOAST | [rewriteheap.c:347-359](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L347-L359), [heapam.c:8937-8961](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L8937-L8961) |
| Relfilenodes are swapped, not copied | [cluster.c:1035-1062](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1035-L1062) |
| Old file deleted at commit; dirty buffers dropped unwritten | [cluster.c:1449-1458](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1449-L1458), [storage.c:144-160](../../../../raw/postgres-12/src/backend/catalog/storage.c#L144-L160), [smgr.c:459-463](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L459-L463) |
| First segment truncated with its unlink deferred to the next checkpoint; later segments unlinked at once | [md.c:284-359](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L284-L359), [md.c:225-254](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L225-L254) |
| Indexes rebuilt from the new heap | [cluster.c:1393-1410](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1393-L1410), [index.c:3526-3530](../../../../raw/postgres-12/src/backend/catalog/index.c#L3526-L3530), [nbtsort.c:487-491](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L487-L491) |
| TOAST not recursed into; rebuilt via the main rewrite | [vacuum.c:1792-1800](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1792-L1800), [cluster.c:725-751](../../../../raw/postgres-12/src/backend/commands/cluster.c#L725-L751), [cluster.c:826-856](../../../../raw/postgres-12/src/backend/commands/cluster.c#L826-L856) |
| External values fetched back and re-saved | [rewriteheap.c:640-669](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L640-L669), [tuptoaster.c:680-699](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L680-L699), [tuptoaster.c:100-111](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L100-L111) |
| TOAST inserts skip the FSM | [rewriteheap.c:653-658](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L653-L658), [hio.c:325](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L325), [hio.c:520-527](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L520-L527) |
| 32-buffer `BAS_BULKREAD` ring | [heapam.c:245-258](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L245-L258), [tableam.h:736-744](../../../../raw/postgres-12/src/include/access/tableam.h#L736-L744), [freelist.c:541-588](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L541-L588) |
| Hint bits can dirty old-heap pages | [heapam_handler.c:823-828](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L823-L828), [heapam_visibility.c:112-131](../../../../raw/postgres-12/src/backend/access/heap/heapam_visibility.c#L112-L131), [heapam_visibility.c:1188-1213](../../../../raw/postgres-12/src/backend/access/heap/heapam_visibility.c#L1188-L1213), [freelist.c:685-696](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L685-L696) |
| No `vacuum_delay_point` in the rewrite path | [vacuum.c:1945-1971](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1945-L1971) plus zero matches in `cluster.c`/`rewriteheap.c`/`heapam_handler.c` |
| Cost GUC defaults and `PGC_USERSET` scope | [guc.c:3372-3381](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3372-L3381), [guc.c:2281-2319](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2281-L2319), [vacuum.c:375-385](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L375-L385) |
| `TRUNCATE`/`INDEX_CLEANUP` ignored, `DISABLE_PAGE_SKIPPING` rejected | [vacuum.sgml:193-224](../../../../raw/postgres-12/doc/src/sgml/ref/vacuum.sgml#L193-L224), [vacuum.c:262-268](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L262-L268) |
| Progress and statistics observability | [system_views.sql:967-992](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L967-L992), [system_views.sql:623-646](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L623-L646), [bufmgr.c:660-669](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L660-L669) |
| `heap_blks_scanned` is updated per returned tuple, not per block, and is never squared up at end of scan | [heapam_handler.c:810-821](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L810-L821), [heapam_handler.c:923-974](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L923-L974), [monitoring.sgml:4026-4032](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L4026-L4032) |
| `heap_tuples_scanned` equals `heap_tuples_written` in this path | [heapam_handler.c:892-922](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L892-L922) |
| `SET LOCAL` needs an enclosing transaction block | [guc.c:8115-8123](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L8115-L8123), [xact.c:3404-3430](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L3404-L3430) |
| `relallvisible` swapped in, VM never built, so the next plain `VACUUM` cannot skip | [cluster.c:1131-1148](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1131-L1148), [cluster.c:950-972](../../../../raw/postgres-12/src/backend/commands/cluster.c#L950-L972), [visibilitymap.c:329-356](../../../../raw/postgres-12/src/backend/access/heap/visibilitymap.c#L329-L356), [vacuumlazy.c:609-636](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L609-L636) |
| Correctness-only test coverage | [vacuum.sql:70-74](../../../../raw/postgres-12/src/test/regress/sql/vacuum.sql#L70-L74), [create_index.sql:495-499](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L495-L499), [rules.out:1849](../../../../raw/postgres-12/src/test/regress/expected/rules.out#L1849) |

Measured on the 12.2 server built from this pin (see [Follow-Up: Measured On A 12.2 Server](#follow-up-measured-on-a-122-server)); the source column gives the mechanism the measurement exercises:

| Measured claim | Number | Mechanism |
|---|---|---|
| Every block of the old heap is read | `heap_blks_read` 884,956 of 884,956; `read_bytes` 7,249,559,552 | [heapam.c:225-231](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L225-L231), [heapam.c:380-383](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L380-L383) |
| All-frozen pages are read anyway | all 884,956 pages all-frozen beforehand; plain `VACUUM` read 0 | no `visibilitymap` reference in [heapam_handler.c](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L20-L50), against [vacuumlazy.c:566-596](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L566-L596) |
| One 8 kB read call per block | `syscr` 885,019 = 884,956 heap blocks + 63 other calls; `rchar` 7,250,034,354 = 7,249,559,552 + 474,802 | [heapam.c:380-383](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L380-L383) |
| Writes track live rows | new heap 885 blocks = `ceil(200000 / 226)` | [rewriteheap.c:684-693](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L684-L693) |
| A tupleless rewrite writes nothing | new heap 0 bytes from an 884,956-block old heap | [rewriteheap.c:330-345](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L330-L345) |
| WAL is one FPI per new page | 885 `XLOG/FPI` records for 885 new pages | [rewriteheap.c:697-703](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L697-L703), [rewriteheap.c:331-338](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L331-L338) |
| `wal_level = minimal` suppresses it | 84,720 bytes against 7,377,944 | [heapam_handler.c:719-723](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L719-L723) |
| `heap_blks_scanned` under-reports | 0 of 884,956 for 49 of 51 samples; 0 for all 94 samples on a rowless heap | [heapam_handler.c:810-821](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L810-L821) |
| Index rebuild reads only the new heap | 885 blocks, `idx_blks_read` 0 | [cluster.c:1393-1410](../../../../raw/postgres-12/src/backend/commands/cluster.c#L1393-L1410) |
| No cost-based delay | 2.05 s against 57.27 s for the same bytes under the same GUCs | [vacuum.c:1945-1971](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1945-L1971) |
| First segment truncated, later ones unlinked, first removed at checkpoint | `16438` at 0 bytes with `.1`-`.6` gone, then absent after `CHECKPOINT` | [md.c:284-359](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L284-L359) |
| Line pointers survive `DELETE` plus `VACUUM` | 226 of 226 `LP_UNUSED`, `pd_lower` 928 | [bufpage.c:471-482](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L471-L482) |
| No VM fork after the rewrite | `relallvisible` 884,956 -> 0, vm fork 229,376 -> 0, next `VACUUM` skipped 0 pages | [cluster.c:950-972](../../../../raw/postgres-12/src/backend/commands/cluster.c#L950-L972) |

## Open Questions

1. **TOAST was not measured.** The fixture is a single `bigint` column, so no TOAST relation existed and the [TOAST](#toast) section remains source-only. The costly case it describes — a near-empty main heap beside a huge TOAST relation whose live chunks must be fetched back through the TOAST index and re-saved — was never built, so the random-read term there carries no number.
2. **The hint-bit write term is bounded only for a frozen heap.** The fixture was fully frozen before the rewrite, so `HeapTupleSatisfiesVacuum` had no hint bits left to set and the backend's `write_bytes` (7,323,648) is accounted for by the new heap (7,249,920) alone. On a heap carrying unset hint bits the term is still unquantified, and whether a dirtied ring buffer is written or rejected still depends on `XLogNeedsFlush(lsn)` and therefore on whether `data_checksums` or `wal_log_hints` made the hint-bit update WAL-logged — the `XLogHintBitIsNeeded()` test [xlog.h:183-192](../../../../raw/postgres-12/src/include/access/xlog.h#L183-L192), consumed by `MarkBufferDirtyHint` [bufmgr.c#MarkBufferDirtyHint](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3465-L3500). Neither `data_checksums` nor `wal_log_hints` was enabled in the measured cluster.
3. **One row width, one fixture scale.** Every measurement uses `t_len = 32` at 884,956 blocks. The other three rows of the [worked example](#worked-example-for-the-shape-in-the-question) were not built, and no second heap size was run, so linearity of reads in file size is inferred from the code path rather than from two points on a curve.
4. **The storage was fast and local.** Reads streamed at roughly 3.4 GB/s, so a 6.75 GB heap took 2.15 s cold. Nothing here tells you the wall-clock cost on slower or networked storage; only the byte counts transfer.
5. **Concurrent-activity effects on the swap were not examined.** `DropRelFileNodesAllBuffers` scans the buffer pool, so the teardown cost scales with `shared_buffers`; that path was cited for its no-write property, not analyzed for cost, and the measured cluster ran a small 128 MB pool with no other session active.
6. **Partitioned tables were not considered.** `VACUUM FULL` on a partitioned parent expands to its leaves, and the per-leaf accounting above should apply once each, but the expansion path in `vacuum.c` was not traced and no partitioned fixture was built.
7. **The documentation conflict is now measured, but not resolved upstream.** [maintenance.sgml:233-237](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L233-L237) says these rewriting commands "temporarily use extra disk space approximately equal to the size of the table", and [vacuum.sgml:100-108](../../../../raw/postgres-12/doc/src/sgml/ref/vacuum.sgml#L100-L108) says `FULL` "requires extra disk space, since it writes a new copy of the table". Measured, the transient heap was 7,249,920 bytes against an old relation of 7,249,559,552 — a factor of 0.0001, not ~1.0 — and 0 bytes on the rowless fixture. Source and measurement agree with each other and disagree with the prose; no same-version doc text states the near-empty case.
8. **The sandbox is gone.** The build, cluster and harness were deleted after the run at the asker's instruction, so reproducing any number means rebuilding 12.2 out of tree from `raw/postgres-12/` and re-running [How to reproduce](#how-to-reproduce). The fixture SQL is published in full; the sampling harness (the `/proc` poller and the `\watch` progress sampler) is described but not published verbatim.

## Source References

- [vacuum.c](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1620-L1860)
- [cluster.c](../../../../raw/postgres-12/src/backend/commands/cluster.c#L255-L1520)
- [heapam_handler.c](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L690-L979)
- [rewriteheap.c](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L240-L757)
- [heapam.c](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L205-L785)
- [heapam_visibility.c](../../../../raw/postgres-12/src/backend/access/heap/heapam_visibility.c#L80-L145)
- [visibilitymap.c](../../../../raw/postgres-12/src/backend/access/heap/visibilitymap.c#L309-L367)
- [vacuumlazy.c](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L560-L736)
- [tuptoaster.c](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L640-L880)
- [hio.c](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L286-L330)
- [nbtsort.c](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L380-L500)
- [bufmgr.c](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L640-L970)
- [freelist.c](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L537-L704)
- [bufpage.c](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L439-L720)
- [smgr.c](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L419-L473)
- [md.c](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L220-L362)
- [storage.c](../../../../raw/postgres-12/src/backend/catalog/storage.c#L143-L170)
- [index.c](../../../../raw/postgres-12/src/backend/catalog/index.c#L3433-L3540)
- [index.c#index_update_stats](../../../../raw/postgres-12/src/backend/catalog/index.c#L2656-L2790)
- [reloptions.c](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L84-L160)
- [xact.c](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L3367-L3430)
- [system_views.sql](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L590-L995)
- [guc.c](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2280-L2320)
- [xlog.h](../../../../raw/postgres-12/src/include/access/xlog.h#L159-L199)
- [bufpage.h](../../../../raw/postgres-12/src/include/storage/bufpage.h#L110-L220)
- [htup_details.h](../../../../raw/postgres-12/src/include/access/htup_details.h#L550-L580)
- [itemid.h](../../../../raw/postgres-12/src/include/storage/itemid.h#L17-L33)
- [rel.h](../../../../raw/postgres-12/src/include/utils/rel.h#L270-L312)
- [bufmgr.h](../../../../raw/postgres-12/src/include/storage/bufmgr.h#L176-L210)
- [tableam.h](../../../../raw/postgres-12/src/include/access/tableam.h#L723-L751)
- [ref/vacuum.sgml](../../../../raw/postgres-12/doc/src/sgml/ref/vacuum.sgml#L60-L230)
- [maintenance.sgml](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L120-L240)
- [monitoring.sgml](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L3780-L4090)
- [vacuum.sql](../../../../raw/postgres-12/src/test/regress/sql/vacuum.sql#L18-L150)
- [create_index.sql](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L490-L505)
- [rules.out](../../../../raw/postgres-12/src/test/regress/expected/rules.out#L1845-L1855)

## Navigation

- [v12/index](../../index.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
- [PostgreSQL 12 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [PostgreSQL 12 Database Health Checklist (unverified)](../server-administration/database-health-checklist.md)
