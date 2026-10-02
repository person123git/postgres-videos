---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: claude-opus-5-max 2026-08-31T13:20:20Z
---

# How Much I/O a VACUUM FULL Performs on a Multi-GB, Near-Empty Heap in PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [Where VACUUM FULL goes in v17](#where-vacuum-full-goes-in-v17)
  - [Read side: the whole heap, every block, no skip path](#read-side-the-whole-heap-every-block-no-skip-path)
  - [What v17 changes: the reads are combined, not fewer](#what-v17-changes-the-reads-are-combined-not-fewer)
  - [Heap size means the physical file, not pg_class.relpages](#heap-size-means-the-physical-file-not-pg_classrelpages)
  - [Write side: the new heap is sized by live rows](#write-side-the-new-heap-is-sized-by-live-rows)
  - [Page arithmetic for the new heap](#page-arithmetic-for-the-new-heap)
  - [WAL volume](#wal-volume)
  - [The fsync is handed to the checkpointer](#the-fsync-is-handed-to-the-checkpointer)
  - [The old file is unlinked, not rewritten](#the-old-file-is-unlinked-not-rewritten)
  - [Index rebuild](#index-rebuild)
  - [TOAST](#toast)
  - [Emptied pages in v17: the line pointer array is truncated](#emptied-pages-in-v17-the-line-pointer-array-is-truncated)
  - [Where the reads land in the buffer pool](#where-the-reads-land-in-the-buffer-pool)
  - [No cost-based throttling, and no BUFFER_USAGE_LIMIT either](#no-cost-based-throttling-and-no-buffer_usage_limit-either)
  - [What VACUUM FULL never does here](#what-vacuum-full-never-does-here)
  - [How to observe the read volume on a v17 server](#how-to-observe-the-read-volume-on-a-v17-server)
  - [What the command leaves behind](#what-the-command-leaves-behind)
  - [Test coverage in the pinned tree](#test-coverage-in-the-pinned-tree)
- [Measured On A 17.11 Server](#measured-on-a-1711-server)
  - [What was built and run](#what-was-built-and-run)
  - [The fixture: 884,956 blocks holding 200,000 rows](#the-fixture-884956-blocks-holding-200000-rows)
  - [Result: VACUUM FULL read every block](#result-vacuum-full-read-every-block)
  - [Read combining: 55,361 syscalls for 884,956 blocks](#read-combining-55361-syscalls-for-884956-blocks)
  - [The syscall count is tunable; the block count is not](#the-syscall-count-is-tunable-the-block-count-is-not)
  - [Control: the same heap, a plain VACUUM, zero blocks](#control-the-same-heap-a-plain-vacuum-zero-blocks)
  - [The extreme case: a 6.75 GB heap with no rows at all](#the-extreme-case-a-675-gb-heap-with-no-rows-at-all)
  - [Writes, WAL, and the fsync](#writes-wal-and-the-fsync)
  - [What the progress view showed](#what-the-progress-view-showed)
  - [The index rebuild reads the new heap](#the-index-rebuild-reads-the-new-heap)
  - [What happened to the old file](#what-happened-to-the-old-file)
  - [Truncated line pointers, measured](#truncated-line-pointers-measured)
  - [How to reproduce](#how-to-reproduce)
- [What Changed Since PostgreSQL 12](#what-changed-since-postgresql-12)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 17, if a table heap is multiple GBs in size but it has only a few thousand rows, so the table heap is essentially empty or filled with empty pages, how much I/O will a VACUUM FULL perform in relation to heap size?

Run tests on a PostgreSQL 17 database to measure I/O. The test is a table with initially 200 million rows, with 99.9% of the rows deleted but the last ones kept so that VACUUM does not truncate the heap. After VACUUM and VACUUM FREEZE, measure the heap size, then perform a VACUUM FULL and measure how much of the heap is read. The hypothesis is that the whole heap is read, even the empty or frozen pages.

Prompt hygiene note: the prompt as typed read "follow agents.md, in postgresql 17, question: In PostgreSQL 17, if a table heap is multiple GBs in size, however it has only a few thousand rows, so the table heap is essentially empty or filled with empty pages, how much I/O will a VACUUM FULL perform in relation to heap size?, Run tests on a PostgreSQL 17 database to measure I/O. ...". Per `MANDATORY Prompt Hygiene` the asker was offered the choice and selected "correct and restate", so the restated text above fixes three things: the comma splice `is multiple GBs in size, however it has only a few thousand rows` -> `is multiple GBs in size but it has only a few thousand rows`; the comma after a question mark in `in relation to heap size?, Run tests` -> a sentence break; and `postgresql 17` -> `PostgreSQL 17` in the routing preamble. The `follow agents.md` and `in postgresql 17` clauses are routing instructions rather than part of the question, so they are not restated. Two scoping answers were taken up front: the same narrow `bigint` row shape as the PostgreSQL 12 page, so the two majors are directly comparable; and deletion of the sandbox afterwards, with the fixture SQL published under [How to reproduce](#how-to-reproduce).

## Answer

### Short answer

Reads scale with the **full physical size of the heap**. Writes scale with the **live data only**. Emptiness buys you nothing on the read side, and v17 changes nothing about that.

| Component | Volume, relative to old heap size `S` | Why |
|---|---|---|
| Old heap reads | `≈ S` (every block, once, sequentially) | plain seq scan over `rs_nblocks` with no visibility-map skip |
| New heap writes | `≈ live bytes` (a few pages here), not `S` | one bulk-write page per filled page |
| WAL | no page images at `wal_level = minimal`; `≈ new heap size` otherwise | one full-page image per new page, batched 32 per record |
| fsync | usually none in the backend: the new relation is *registered* for the next checkpoint | `smgr_bulk_finish` calls `smgrregistersync` |
| Old heap deletion | metadata only (first segment truncated with its unlink deferred past the next checkpoint, later 1 GB segments unlinked at once) | `mdunlinkfork` |
| Index rebuilds | reads the **new** small heap, writes small indexes | `finish_heap_swap` reindexes after the swap |
| TOAST | proportional to **live** toasted bytes, via index lookups | external values fetched back and re-saved |

So on a 4 GB heap holding a few thousand rows, expect roughly **4 GB of sequential reads** and, depending on row width, a few hundred kB to a few MB of writes. The command's duration is set by how fast the storage can stream the old file, not by how much data survives.

What v17 changes is the *shape* of those reads, not their volume. The rewrite's sequential scan now goes through the read stream, so the same 4 GB arrives in **~128 kB read calls instead of 8 kB ones** — about 16x fewer system calls for identical bytes. See [What v17 changes: the reads are combined, not fewer](#what-v17-changes-the-reads-are-combined-not-fewer).

This was measured on a 17.11 server built from the pin. A 7,249,559,552-byte heap holding 200,000 live rows in its last 886 pages, with all 884,956 pages marked all-visible and all-frozen, was read in full: `heap_blks_read` moved by exactly **884,956** with **zero** buffer hits, and the block layer delivered exactly **7,249,559,552 bytes** in **55,361** read system calls, while the new heap came to 885 blocks. The same heap under a plain `VACUUM` read **0 blocks**. See [Measured On A 17.11 Server](#measured-on-a-1711-server).

### Where VACUUM FULL goes in v17

`VACUUM FULL` is not a separate code path in v17; it is `CLUSTER` without a cluster index. `vacuum_rel` takes `AccessExclusiveLock` for the `FULL` case [vacuum.c:2054-2055](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2054-L2055) and hands off to `cluster_rel` with `InvalidOid` as the index [vacuum.c:2248-2261](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2248-L2261). `cluster.c`'s header comment states the contract: "If indexOid is InvalidOid, the table will be rewritten in physical order instead of index order. This is the new implementation of VACUUM FULL" [cluster.c#cluster_rel](../../../../raw/postgres-17/src/backend/commands/cluster.c#L306-L311).

`cluster_rel` tags progress reporting as `PROGRESS_CLUSTER_COMMAND_VACUUM_FULL` precisely because `indexOid` is invalid [cluster.c:323-330](../../../../raw/postgres-17/src/backend/commands/cluster.c#L323-L330), opens the relation with `AccessExclusiveLock` [cluster.c:337](../../../../raw/postgres-17/src/backend/commands/cluster.c#L337), and reaches `rebuild_relation`, which does three things in order: create a transient heap, copy the data, swap and reindex [cluster.c#rebuild_relation](../../../../raw/postgres-17/src/backend/commands/cluster.c#L632-L674).

Four option interactions are worth knowing before measuring, because each is an error rather than a silent no-op: `PARALLEL` is rejected [vacuum.c:317-320](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L317-L320), `DISABLE_PAGE_SKIPPING` is rejected [vacuum.c:353-357](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L353-L357), and `PROCESS_TOAST` is *required* [vacuum.c:360-364](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L360-L364). `BUFFER_USAGE_LIMIT` is rejected too unless `ANALYZE` is also given [vacuum.c:322-331](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L322-L331).

### Read side: the whole heap, every block, no skip path

Because `OIDOldIndex` is `InvalidOid`, `copy_table_data` leaves `OldIndex = NULL` and sets `use_sort = false` [cluster.c:844-847](../../../../raw/postgres-17/src/backend/commands/cluster.c#L844-L847), [cluster.c:948-951](../../../../raw/postgres-17/src/backend/commands/cluster.c#L948-L951). That selects the sequential-scan branch of the heap AM's copy callback, which opens a plain `table_beginscan` with `SnapshotAny` and **no scan keys**, and publishes the relation's total block count as `heap_blks_total`:

[heapam_handler.c:760-773](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L760-L773)

`SnapshotAny` is deliberate: the comment says "To ensure we see recently-dead tuples that still need to be copied, we scan with SnapshotAny and use HeapTupleSatisfiesVacuum for the visibility test" [heapam_handler.c:737-741](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L737-L741).

There is no visibility-map consultation anywhere in this path. Searching the whole of each of the three files that make up the rewrite for `visibilitymap`, `VM_ALL_` and `all_visible` returns **zero** matches in [cluster.c](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1-L70) and **zero** in [rewriteheap.c](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L100-L120) — the links point at each file's head — and in `heapam_handler.c` exactly two: the `#include` [heapam_handler.c:30](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L30) and one `VM_ALL_VISIBLE` test [heapam_handler.c:2141](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L2141), which is in the bitmap-scan callback, not in the rewrite. That is a correctness requirement, not an oversight: the rewrite must copy every live *and* recently-dead tuple, and an all-visible page still contains tuples that must move to the new relfilenode. Contrast plain `VACUUM`, whose `heap_blks_scanned` documentation explicitly says "the visibility map is used to optimize scans, some blocks will be skipped without inspection" [monitoring.sgml#heap_blks_scanned](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L6229-L6236); the `pg_stat_progress_cluster` counterpart carries no such sentence [monitoring.sgml:5584-5602](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L5584-L5602).

The scan visits every block exactly once. `initscan` fixes `rs_nblocks = RelationGetNumberOfBlocks()` [heapam.c:425-431](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L425-L431), and the block sequence comes from `heapgettup_advance_block`, which walks forward with wraparound and stops only when it returns to `rs_startblock` [heapam.c#heapgettup_advance_block](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L867-L906). An empty page is not special-cased: it is read, `linesleft` is set from the page's line pointer count, and the loop moves on [heapam.c#heapgettup](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L974-L1035). Each surviving line pointer that is not `LP_NORMAL` is skipped with no visibility test and no rewrite call [heapam.c:995-1001](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L995-L1001). Either way the block is read once, and nothing about the page's emptiness removes that read.

One subtlety worth knowing when watching progress: `SnapshotAny` is not an MVCC snapshot, so page-at-a-time mode is switched off [heapam.c:1182-1186](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1182-L1186), which routes the scan through `heapgettup` rather than `heapgettup_pagemode` [heapam.c:1417-1425](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1417-L1425) — and therefore `heap_page_prune_opt` is *not* called on the old heap during the rewrite, because that call sits inside the pagemode-only `heap_prepare_pagescan` [heapam.c:618-628](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L618-L628). Synchronized scanning can still start the scan mid-relation when the relation exceeds `NBuffers / 4` [heapam.c:445-496](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L445-L496); v17's progress reporting compensates for that wraparound explicitly, unlike the block *count*, which is unaffected either way.

### What v17 changes: the reads are combined, not fewer

v17 routes every sequential scan through the read stream, and the rewrite's scan is an ordinary sequential scan, so it inherits that. `heap_beginscan` creates the stream whenever `SO_TYPE_SEQSCAN` is set [heapam.c:1237-1259](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1237-L1259), and `table_beginscan` — the call the rewrite uses — always sets that flag [tableam.h#table_beginscan](../../../../raw/postgres-17/src/include/access/tableam.h#L913-L921). Each block then arrives through `read_stream_next_buffer` instead of a direct `ReadBuffer` [heapam.c#heap_fetch_next_buffer](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L692-L734), with the block numbers supplied by a callback that is just the old block-advance logic [heapam.c#heap_scan_stream_read_next_serial](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L378-L401).

The consequence for I/O is that adjacent blocks are merged into one system call. The stream's job, in its own words, is "to form reads of up to io_combine_limit, by attempting to merge them with a pending read" [read_stream.c:10-20](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L10-L20). `WaitReadBuffers` then greedily extends each read over consecutive buffers and issues a single `smgrreadv` for the run [bufmgr.c#WaitReadBuffers](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1494-L1521), which `mdreadv` turns into one `preadv` per segment, capped at `PG_IOV_MAX` [md.c#mdreadv](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L821-L929).

The size of those calls is bounded by three numbers, all resolved when the stream is created:

| Bound | Value on a default v17 server | Source |
|---|---|---|
| `io_combine_limit` | 16 blocks (128 kB) | `DEFAULT_IO_COMBINE_LIMIT = Min(PG_IOV_MAX, 128 kB / BLCKSZ)` [bufmgr.h:168-170](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L168-L170) |
| `max_ios`, from `effective_io_concurrency` | 1 | [read_stream.c:419-442](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L419-L442) |
| strategy pin limit, `BAS_BULKREAD` ring | 32 buffers | [freelist.c#GetAccessStrategyPinLimit](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L646-L661), ring size 256 kB [freelist.c:551-573](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L551-L573) |

`max_pinned_buffers` comes out as `Max(max_ios * 4, io_combine_limit)` clamped by the strategy limit — `Max(4, 16) = 16`, under the ring's 32 [read_stream.c:452-472](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L452-L472). Two further details matter for a whole-relation scan: `READ_STREAM_SEQUENTIAL` **disables** `posix_fadvise` advice, on the theory that the kernel's own readahead is better for a scan it can detect [read_stream.c:508-520](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L508-L520); and the look-ahead distance starts at 1 and ramps up, because the rewrite does not pass `READ_STREAM_FULL` [read_stream.c:545-553](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L545-L553). So the first few reads of the scan are short, and the rest plateau at `io_combine_limit`.

Two accounting consequences follow, and both are easy to misread:

1. **Block counters do not change.** `pgstat_count_buffer_read` is called once per block in `PinBufferForBlock`, whatever the eventual read size [bufmgr.c:1162-1171](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1162-L1171), so `pg_statio_all_tables.heap_blks_read` still counts 8 kB blocks.
2. **`pg_stat_io.reads` counts blocks, not read operations, despite the documentation.** `WaitReadBuffers` passes `io_buffers_len` as the count [bufmgr.c:1518-1521](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1518-L1521) and `pgstat_count_io_op_n` adds that count to the counter [pgstat_io.c:82-93](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_io.c#L82-L93), while the docs describe `reads` as the "Number of read operations, each of the size specified in `op_bytes`" with `op_bytes` fixed at the block size [monitoring.sgml:2616-2626](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L2616-L2626), [monitoring.sgml#op_bytes](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L2714-L2729). Source wins: with combining in play, the true number of read calls is smaller than `reads`, and nothing in `pg_stat_io` exposes it. This is filed under [Open Questions](#open-questions).

### Heap size means the physical file, not pg_class.relpages

The read volume is set by `RelationGetNumberOfBlocks`, which for a table goes through `table_relation_size` and rounds up to whole blocks [bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3993-L4020). That is a live `smgr` answer about the file on disk, not the possibly stale `pg_class.relpages` estimate. A heap whose `relpages` says 100 but whose file is 4 GB will be read as 4 GB.

### Write side: the new heap is sized by live rows

Every surviving tuple is reformed and handed to the rewrite module [heapam_handler.c#reform_and_rewrite_tuple](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L919-L937), which fills one page buffer and queues it when the next tuple no longer fits [rewriteheap.c:640-673](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L640-L673).

In v17 the page never enters shared buffers. `rs_buffer` is a `BulkWriteBuffer` obtained from the bulk-write facility [rewriteheap.c:130-140](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L130-L140), the rewrite starts a bulk write on the new relation [rewriteheap.c:250-260](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L250-L260), and each finished page goes to `smgr_bulk_write` [rewriteheap.c:655-663](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L655-L663). `bulk_write.c` states the tradeoff in its header: "We bypass the buffer manager to avoid the locking overhead, and call smgrextend() directly. A downside is that the pages will need to be re-read into shared buffers on first use after the build finishes" [bulk_write.c:1-25](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L1-L25).

Three consequences for I/O accounting:

1. **Writes are queued 32 pages at a time.** `smgr_bulk_write` appends to a pending array and flushes when it reaches `MAX_PENDING_WRITES`, which is `XLR_MAX_BLOCK_ID` [bulk_write.c:48](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L48), [bulk_write.c#smgr_bulk_write](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L323-L335) — and that constant is 32 [xlogrecord.h:241](../../../../raw/postgres-17/src/include/access/xlogrecord.h#L241). Each flush WAL-logs the batch and then calls `smgrextend` once per page [bulk_write.c#smgr_bulk_flush](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L242-L313).
2. **Dead tuples are never written.** A tuple that `HeapTupleSatisfiesVacuum` reports as `HEAPTUPLE_DEAD` is passed to `rewrite_heap_dead_tuple` for bookkeeping and then skipped [heapam_handler.c:894-905](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L894-L905).
3. **`pg_stat_io` does not see these writes at all.** The extends bypass `ExtendBufferedRel`, so no `IOOP_EXTEND` is counted; the only extend accounting in the buffer manager is on the buffered path [bufmgr.c:2440-2452](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2440-L2452).

### Page arithmetic for the new heap

The rewrite packs pages to the new relation's fillfactor, defaulting to `HEAP_DEFAULT_FILLFACTOR` [rewriteheap.c:643-646](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L643-L646), and the transient heap inherits the old relation's reloptions [cluster.c:711-721](../../../../raw/postgres-17/src/backend/commands/cluster.c#L711-L721). So for a table at the default fillfactor of 100, the new heap is `ceil(live bytes / usable page bytes)` pages, where each tuple costs `MAXALIGN(t_len) + sizeof(ItemIdData)` and the usable space per page is `BLCKSZ` minus the page header and the special-space reserve [bufpage.c#PageGetHeapFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L976-L1011). A narrow `bigint` row gives `t_len = 32`, `MAXALIGN(32) + 4 = 36`, and `floor(8168 / 36) = 226` tuples per page.

### WAL volume

WAL is emitted only when the new relation needs it: `smgr_bulk_start_rel` sets `use_wal` from `RelationNeedsWAL(rel)` [bulk_write.c#smgr_bulk_start_rel](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L87-L93), which is false at `wal_level = minimal` for a relation created in this transaction.

When WAL is needed, each flush calls `log_newpages` for the whole batch [bulk_write.c:254-276](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L254-L276), and `log_newpages` writes **one `XLOG_FPI` record per 32 pages**, with every page forced to a full-page image [xloginsert.c#log_newpages](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L1174-L1228). So WAL volume tracks the *new* heap's size, not the old one's, and the record count is that divided by 32.

### The fsync is handed to the checkpointer

v17 does not fsync the new heap inline in the normal case. `smgr_bulk_finish` flushes the remaining pages and then, for a WAL-logged relation, calls `smgrregistersync` so the next checkpoint does the flushing — falling back to an immediate `smgrimmedsync` only if a checkpoint started while the bulk write was in progress [bulk_write.c#smgr_bulk_finish](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L130-L223). The pages themselves were written with `skipFsync = true` [bulk_write.c:304-308](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L304-L308).

### The old file is unlinked, not rewritten

`finish_heap_swap` swaps relfilenodes rather than copying data [cluster.c#finish_heap_swap](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1438-L1520), so reclaiming the space costs no data movement. At commit the old relfilenode's first segment is truncated to zero and its unlink deferred past the next checkpoint (to protect the relfilenode number from reuse), while the higher-numbered 1 GB segments are unlinked immediately [md.c#mdunlinkfork](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L344-L430), [md.c#register_unlink_segment](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L1410-L1450).

### Index rebuild

Indexes are rebuilt after the swap, from the new heap [cluster.c:1505-1512](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1505-L1512), which is also why `cluster.c` says it is "better to create the indexes afterwards than to fill them incrementally while we load the table" [cluster.c:302-305](../../../../raw/postgres-17/src/backend/commands/cluster.c#L302-L305). The index-build reads are therefore proportional to the surviving rows, not to the old heap.

### TOAST

`VACUUM FULL` does not recurse into the TOAST relation; it is rebuilt as a side effect of the main rewrite, which is why `vacuum_rel` suppresses TOAST recursion for the `FULL` case [vacuum.c:2210-2224](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2210-L2224). Out-of-line values are fetched back and re-saved by the rewrite when the reformed tuple is too big or carries pointers from another relation [rewriteheap.c:596-630](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L596-L630). That work is proportional to live toasted bytes and is index-driven, not a second sequential scan.

### Emptied pages in v17: the line pointer array is truncated

This is where v17 differs from older majors in a way that is visible to `pgstattuple` and to the scan's CPU cost. v17's `PageRepairFragmentation` "removes unused line pointers from the end of the line pointer array" [bufpage.c#PageRepairFragmentation](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L683-L699), and VACUUM's second pass calls `PageTruncateLinePointerArray` directly on every page whose dead items it just set to `LP_UNUSED` [vacuumlazy.c:2222-2232](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2222-L2232), [pruneheap.c:1704-1712](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1704-L1712). That routine truncates the array back to its last used entry, "avoid[ing] truncating the line pointer array to 0 items, if necessary by leaving behind a single remaining LP_UNUSED item" [bufpage.c#PageTruncateLinePointerArray](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L815-L835).

So a page emptied by `DELETE` plus `VACUUM` on v17 keeps **one** line pointer, not its historical high-water mark. The rewrite's scan finds `linesleft = 1`, rejects that entry on `ItemIdIsNormal` and moves on [heapam.c:995-1001](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L995-L1001). The per-page CPU work is therefore negligible; the read is not.

### Where the reads land in the buffer pool

The scan takes a `BAS_BULKREAD` strategy when the relation exceeds `NBuffers / 4` [heapam.c:433-465](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L433-L465), a 256 kB / 32-buffer ring [freelist.c:551-573](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L551-L573). So a multi-GB rewrite does not evict the whole buffer pool. The ring is not an absolute guarantee: `StrategyRejectBuffer` drops a buffer out of the ring when it turns out to be dirty, sending the next allocation to the normal clock sweep [freelist.c#StrategyRejectBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L786-L816). The reads are attributed to the `bulkread` I/O context [freelist.c:774-775](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L774-L775), which the docs describe as "Certain large read I/O operations done outside of shared buffers, for example, a sequential scan of a large table" [monitoring.sgml#bulkread](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L2599-L2605).

### No cost-based throttling, and no BUFFER_USAGE_LIMIT either

Neither `cluster.c`, `heapam_handler.c` nor `rewriteheap.c` contains a `vacuum_delay_point` call; the only call sites are in plain vacuum, analyze and the index AMs' vacuum routines [vacuum.c#vacuum_delay_point](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2384-L2418). So `vacuum_cost_delay` and `vacuum_cost_limit` — both `PGC_USERSET`, so session or transaction scope, with `vacuum_cost_delay` defaulting to `0` [guc_tables.c:3865-3873](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3865-L3873), [guc_tables.c:2546-2553](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2546-L2553) — do not throttle a rewrite.

The v17-era knob is no help either: `VACUUM (BUFFER_USAGE_LIMIT ...)` is an error with `FULL` unless `ANALYZE` is also specified [vacuum.c:322-331](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L322-L331), which the reference page states as well [ref/vacuum.sgml#BUFFER_USAGE_LIMIT](../../../../raw/postgres-17/doc/src/sgml/ref/vacuum.sgml#L343-L356). The ring the rewrite's scan uses is the fixed 256 kB `BAS_BULKREAD` one, not the `vacuum_buffer_usage_limit` ring [guc_tables.c:2273-2281](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2273-L2281).

The settings that *do* change the syscall shape of the reads are `io_combine_limit` and `effective_io_concurrency`, both `PGC_USERSET`, so both take effect for the session or transaction that sets them, with no restart or reload [guc_tables.c:3139-3147](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3139-L3147), [guc_tables.c:3110-3121](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3110-L3121). Neither changes the number of bytes read.

### What VACUUM FULL never does here

- It never skips a block because the page is all-visible or all-frozen. There is no visibility-map read in the rewrite path.
- It never prunes the old heap opportunistically: page-at-a-time mode is off under `SnapshotAny` [heapam.c:1182-1186](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1182-L1186).
- It never uses the free space map of the old relation. `INDEX_CLEANUP` and `TRUNCATE` are ignored, per the reference page [ref/vacuum.sgml:220-224](../../../../raw/postgres-17/doc/src/sgml/ref/vacuum.sgml#L220-L224), [ref/vacuum.sgml:266-272](../../../../raw/postgres-17/doc/src/sgml/ref/vacuum.sgml#L266-L272).
- It never sorts, so there is no temp-file I/O in the heap phase: `use_sort` is false without an index [cluster.c:948-951](../../../../raw/postgres-17/src/backend/commands/cluster.c#L948-L951), and `tuplesort` stays `NULL` [heapam_handler.c:729-735](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L729-L735).

### How to observe the read volume on a v17 server

Four channels, in decreasing order of trustworthiness for this shape:

1. **`pg_statio_all_tables.heap_blks_read`** — one increment per block, from `PinBufferForBlock` [bufmgr.c:1162-1171](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1162-L1171). Take a delta across the command.
2. **`pg_stat_io`, `object = 'relation'`, `context = 'bulkread'`** — the same block count, filtered to the strategy the rewrite uses [freelist.c:774-775](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L774-L775). New since the v12 line and useful because it separates the rewrite's reads from ordinary buffered reads.
3. **`VACUUM (FULL, VERBOSE)`** — prints the old relation's block count directly, from `RelationGetNumberOfBlocks(OldHeap)` [cluster.c:992-1002](../../../../raw/postgres-17/src/backend/commands/cluster.c#L992-L1002). No tooling required.
4. **`pg_stat_progress_cluster.heap_blks_scanned`** — do not use this to size the read. It advances only when a tuple is returned and the block number changed [heapam_handler.c:827-835](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L827-L835), so on precisely the shape this page is about — long runs of pages holding no live tuple — it stands still for most of the command. v17 does square it up to `rs_nblocks` when the scan ends [heapam_handler.c:803-816](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L803-L816), so the *final* value is right even though the intermediate ones are not.

The number of read *system calls* is not exposed by any of them; on Linux, `/proc/<backend pid>/io` (`syscr`, `read_bytes`) is the only way to see it.

### What the command leaves behind

The visibility map and free space map of the new relfilenode do not exist: the rewrite writes neither, and `relallvisible` is swapped along with the relfilenode [cluster.c#swap_relation_files](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1061-L1140). So the next plain `VACUUM` after a `VACUUM FULL` cannot skip a single page — it has no map to skip with — and it rebuilds both forks. On the fixture this is visible as `relallvisible` dropping to 0.

### Test coverage in the pinned tree

`VACUUM FULL` has correctness coverage but no I/O-volume coverage. The regression suite runs it over ordinary tables, catalogs and partitioned tables [vacuum.sql:20-22](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L20-L22), [vacuum.sql:99-103](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L99-L103), [vacuum.sql:238-239](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L238-L239), checks that `INDEX_CLEANUP` is ignored with `FULL` [vacuum.sql:161-163](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L161-L163), and checks the `BUFFER_USAGE_LIMIT` rejection [vacuum.sql:329-330](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L329-L330). Nothing in the tree asserts how many blocks a rewrite reads.

## Measured On A 17.11 Server

### What was built and run

17.11 was built out of tree from the pinned checkout: `git archive 786db8dcf168bd9df8f55047337525ac19118b1c` into a scratch directory, `./configure --prefix=... --without-icu --without-readline --without-zlib --enable-debug`, `make`, `make install`, `make -C contrib install`. `postgres --version` reported `postgres (PostgreSQL) 17.11`. Non-default cluster settings were `shared_buffers = 128MB` (the default), `autovacuum = off`, `track_io_timing = on`, `max_wal_size = 4GB`, `checkpoint_timeout = 30min`, `maintenance_work_mem = 256MB`, `logging_collector = on`. `wal_level` was left at its `replica` default except for the one run that tested `minimal`. `io_combine_limit` was `128kB`, `effective_io_concurrency` `1`, `maintenance_io_concurrency` `10` — all defaults, confirmed with `SHOW`.

Four separate 200-million-row fixtures were built, one per destructive run, because a `VACUUM FULL` removes the very bloat being measured. All four came out byte-identical: **7,249,559,552 bytes in 884,956 blocks**, with `all_visible = all_frozen = 884,956`.

### The fixture: 884,956 blocks holding 200,000 rows

```sql
CREATE TABLE bloat (id bigint NOT NULL);
INSERT INTO bloat SELECT g FROM generate_series(1, 200000000) g;
DELETE FROM bloat WHERE id <= 199800000;
VACUUM (VERBOSE) bloat;
VACUUM (FREEZE, VERBOSE) bloat;
```

| Stage | Heap bytes | Heap blocks | Live rows | Note |
|---|---|---|---|---|
| After load | 7,249,559,552 | 884,956 | 200,000,000 | 226 tuples/page, 134.6 s |
| After `DELETE` of 199,800,000 rows | 7,249,559,552 | 884,956 | 200,000 | no truncation |
| After `VACUUM` | 7,249,559,552 | 884,956 | 200,000 | 34.7 s, scanned 884,956 pages (100.00%), **no truncation** |
| After `VACUUM FREEZE` | 7,249,559,552 | 884,956 | 200,000 | 17.6 ms, scanned 886 pages (0.10%), froze 200,000 tuples |

200,000,000 rows in 884,956 blocks is 225.99994 tuples per block, which is the `floor(8168 / 36) = 226` the [page arithmetic](#page-arithmetic-for-the-new-heap) predicts for a `bigint` row.

Keeping the tail rows worked as intended: `VACUUM` left the relation at its full 884,956 blocks, because `should_attempt_truncation` measures `rel_pages - nonempty_pages` and the last page is not empty [vacuumlazy.c#should_attempt_truncation](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2529-L2544).

The `VACUUM FREEZE` then took **17.6 ms** and reported `pages: 0 removed, 884956 remain, 886 scanned (0.10% of total)` with `frozen: 886 pages from table (0.10% of total) had 200000 tuples frozen`. An aggressive vacuum still skips all-frozen pages [vacuumlazy.c#find_next_unskippable_block](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1186-L1255), and the earlier plain `VACUUM` had already left the 884,070 emptied pages all-frozen — they hold no tuple, so there is nothing on them left to freeze. Afterwards `pg_visibility_map_summary` reported `all_visible = all_frozen = 884956`: **every page in the relation was marked frozen before the rewrite ran**.

Unlike older majors, the aggressive vacuum did not corrupt the row estimate: `pg_class` read `relpages = 884956`, `reltuples = 200000` for a table holding exactly 200,000 rows, because `vac_estimate_reltuples` keeps the old value when under 2% of an unchanged-size relation was scanned [vacuum.c:1329-1348](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1329-L1348).

### Result: VACUUM FULL read every block

```text
INFO:  vacuuming "public.bloat"
INFO:  "public.bloat": found 0 removable, 200000 nonremovable row versions in 884956 pages
DETAIL:  0 dead row versions cannot be removed yet.
CPU: user: 0.49 s, system: 2.39 s, elapsed: 2.99 s.
```

Cold run: server restarted (so shared buffers were empty) and the seven heap segments evicted from the OS page cache with `posix_fadvise(POSIX_FADV_DONTNEED)`.

| Channel | Cold page cache | Warm page cache |
|---|---|---|
| `pg_statio_all_tables.heap_blks_read` | **884,956** | **884,956** |
| `pg_statio_all_tables.heap_blks_hit` | **0** | **0** |
| `pg_stat_io` `bulkread` `reads` | **884,956** | 884,956 |
| `/proc/<pid>/io` `rchar` | 7,249,903,616 | 7,249,903,616 |
| `/proc/<pid>/io` `syscr` | **55,361** | **55,361** |
| `/proc/<pid>/io` `read_bytes` | **7,249,559,552** | **0** |
| WAL generated | 7,353,992 | 7,360,208 |
| Duration (psql `Time:`) | 3.02 s | 1.20 s |

Four things follow from that pair of columns.

1. **The read count is the whole relation, not the live data.** 884,956 blocks read against 200,000 live rows occupying 886 blocks, with **not one buffer hit**. The 884,070 leading blocks contained no live tuple, were marked all-visible and all-frozen, and were read anyway — there is no visibility-map consultation in the rewrite path, as [Read side: the whole heap, every block, no skip path](#read-side-the-whole-heap-every-block-no-skip-path) sets out.
2. **`read_bytes` reached the file size exactly.** 884,956 × 8192 = 7,249,559,552, which is the relation's size to the byte and the exact value the block layer reported. Nothing was coalesced away below it, and nothing was skipped.
3. **`pg_stat_io` agreed with `pg_statio_all_tables` to the block**, both reporting 884,956 in the `bulkread` context and zero hits — so the rewrite's reads are cleanly attributable to the `BAS_BULKREAD` strategy.
4. **The OS page cache changes only where the bytes come from.** Warm, the device delivered nothing (`read_bytes = 0`) and the command still made all 55,361 read calls, still moved 7,249,903,616 bytes through `rchar`, and still counted 884,956 buffer misses. The 2.5x wall-clock difference (3.02 s against 1.20 s) is the entire benefit; the read volume is identical.

An earlier cold run that restarted nothing (so shared buffers still held part of the relation) split the same total: **869,079 reads + 15,877 hits = 884,956**, with 15,877 × 8 kB ≈ 124 MB of a 128 MB buffer pool supplying the hits. The relation is read in full either way; only the source of the blocks moves.

### Read combining: 55,361 syscalls for 884,956 blocks

This is the one number that a PostgreSQL 12-era measurement of the same fixture cannot reproduce, and it was identical in all three full-size runs:

| Quantity | Value |
|---|---|
| Blocks read | 884,956 |
| Read system calls (`syscr` delta) | 55,361 |
| Blocks per read call | **15.985** |
| Theoretical minimum at 16 blocks/call over 7 segments | 55,310 |

The 15.985 average is `io_combine_limit = 128kB` = 16 blocks in action: `WaitReadBuffers` extends each read over consecutive buffers and issues one `smgrreadv` for the run [bufmgr.c:1494-1521](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1494-L1521), and `mdreadv` splits only at 1 GB segment boundaries and at `PG_IOV_MAX` [md.c:842-848](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L842-L848). The floor of 55,310 is `6 × (131072 / 16) + ceil(98524 / 16)` for the six full segments plus the 98,524-block tail; the measured 55,361 is 51 calls above it, which is the look-ahead ramp-up from `distance = 1` [read_stream.c:545-553](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L545-L553) plus occasional short reads when the consumer holds one of the 16 pinnable buffers.

The same bytes, the same block count, and about **16x fewer read calls** than one call per block. No counter inside the server reports this: `pg_statio_all_tables.heap_blks_read` and `pg_stat_io.reads` both said 884,956.

### The syscall count is tunable; the block count is not

To show that the combining is really `io_combine_limit` and nothing else, the same fixture shape was rebuilt at 1/20th scale — 10,000,000 rows loaded into **44,248 blocks**, 99.9% deleted with the tail kept, then `VACUUM` and `VACUUM FREEZE`, leaving all 44,248 pages all-frozen — and one `VACUUM FULL` was run per setting, each on a freshly built fixture with the heap evicted from the OS page cache:

| `io_combine_limit` | `heap_blks_read` | `heap_blks_hit` | Sum | `syscr` | Blocks per read call |
|---|---|---|---|---|---|
| `8kB` | 28,126 | 16,122 | **44,248** | 28,179 | 0.998 |
| `16kB` | 28,122 | 16,126 | **44,248** | 14,122 | 1.991 |
| `32kB` | 28,121 | 16,127 | **44,248** | 7,088 | 3.967 |
| `64kB` | 28,121 | 16,127 | **44,248** | 3,586 | 7.842 |
| `128kB` (default) | 28,121 | 16,127 | **44,248** | 1,823 | 15.426 |
| `256kB` (the maximum) | 29,018 | 15,230 | **44,248** | 976 | 29.732 |

Every row reads the whole heap: `heap_blks_read + heap_blks_hit` is **44,248** in all six runs, and the device delivered between 231.3 MB and 232.2 MB every time. Only the call count moves, by a factor of **28.9** from end to end, tracking the setting almost exactly — `0.998, 1.991, 3.967, 7.842, 15.426, 29.732` blocks per call against a nominal `1, 2, 4, 8, 16, 32`. The shortfall at the top end is the ramp-up and the pinnable-buffer ceiling; `256kB` is the maximum because `MAX_IO_COMBINE_LIMIT` is `PG_IOV_MAX`, itself `Min(IOV_MAX, 32)` [bufmgr.h:168-169](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L168-L169), [pg_iovec.h:43](../../../../raw/postgres-17/src/include/port/pg_iovec.h#L43).

`io_combine_limit` is `PGC_USERSET`, so a session can raise it for one command with no restart and no reload [guc_tables.c:3139-3147](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3139-L3147). It buys fewer system calls over the same bytes. It does not make `VACUUM FULL` read less.

On the same small fixture, `CREATE INDEX` on the bloated heap read **28,170 blocks with 16,080 hits — 44,250 in total** against a 44,248-block heap, producing a 245,760-byte index for the 10,000 surviving rows. Building an index on a near-empty heap costs a full scan too; the rewrite is not special in that respect.

### Control: the same heap, a plain VACUUM, zero blocks

Immediately before the rewrite, on the identical relation, with the OS cache evicted:

```text
INFO:  vacuuming "vf1.public.bloat"
INFO:  finished vacuuming "vf1.public.bloat": index scans: 0
pages: 0 removed, 884956 remain, 1 scanned (0.00% of total)
buffer usage: 297 hits, 1 misses, 0 dirtied
```

`heap_blks_read` moved by **0** and the command took **3.17 ms**. Plain `VACUUM` skipped 884,955 of 884,956 pages using the visibility map [vacuumlazy.c#heap_vac_scan_next_block](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1087-L1170) and touched only the last page. This is the cleanest available demonstration that the visibility map was fully populated and would have permitted skipping: **the same map that let `VACUUM` read nothing let `VACUUM FULL` read 6.75 GB.**

### The extreme case: a 6.75 GB heap with no rows at all

The `vacuum_truncate` reloption makes the pure case reachable. It is defined at `ShareUpdateExclusiveLock` [reloptions.c#vacuum_truncate](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L150-L158), resolved into `params->truncate` when the command does not say otherwise [vacuum.c:2190-2202](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2190-L2202), and from there into `vacrel->do_rel_truncate` [vacuumlazy.c:391](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L391), which `should_attempt_truncation` checks first [vacuumlazy.c:2534-2535](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2534-L2535):

```sql
ALTER TABLE bloat SET (vacuum_truncate = off);
DELETE FROM bloat;
VACUUM bloat;   -- 884,956 blocks retained, 0 live rows, all_visible = all_frozen = 884956
```

`VACUUM FULL` on that heap:

| Measurement | Value |
|---|---|
| VERBOSE | `found 0 removable, 0 nonremovable row versions in 884956 pages` |
| `heap_blks_read` / `heap_blks_hit` | **884,956** / 0 |
| `syscr` | 55,361 |
| `read_bytes` | **7,249,559,552** |
| `wchar` / `syscw` | 24,928 / **3** |
| WAL generated | 108,384 bytes |
| New heap size | **0 bytes, 0 blocks** |
| `pg_stat_progress_cluster.heap_blks_scanned`, all 566 samples | **0** of 884,956 |
| Duration (psql `Time:`) | 3.00 s |

**6.75 GB was read from disk to produce a zero-byte file**, with three write system calls in the whole command. `end_heap_rewrite` writes a final page only `if (state->rs_buffer)`, and with no tuple ever inserted that pointer stays `NULL` [rewriteheap.c#end_heap_rewrite](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L296-L327), so the write side collapsed to nothing while the read side did not move at all — byte for byte the same 7,249,559,552 as the 200,000-row run.

### Writes, WAL, and the fsync

| Quantity | `wal_level = replica` | `wal_level = minimal` | Zero-row heap, `replica` |
|---|---|---|---|
| Old heap read | 7,249,559,552 bytes | 7,249,559,552 bytes | 7,249,559,552 bytes |
| `heap_blks_read` | 884,956 | 884,956 | 884,956 |
| `syscr` | 55,361 | 55,361 | 55,361 |
| New heap written | 7,249,920 bytes (885 blocks) | 7,249,920 bytes (885 blocks) | 0 |
| Backend `wchar` / `syscw` | 12,616,037 / 1,032 | 7,283,045 / **889** | 24,928 / **3** |
| WAL generated | **7,353,992 bytes** | **110,008 bytes** | 108,384 bytes |
| Duration (psql `Time:`) | 3.02 s | 2.74 s | 3.00 s |
| Read : new-heap-write | **999.95 : 1** | 999.95 : 1 | unbounded |

`ceil(200000 / 226) = 885`, which is exactly what the rewrite produced, so the packing rule in [Page arithmetic for the new heap](#page-arithmetic-for-the-new-heap) is confirmed on a real relation.

The read side is untouched by `wal_level`: all three runs read 884,956 blocks in 55,361 calls and pulled 7,249,559,552 bytes off the device. The write side moves a lot. At `minimal` the backend's own writes come to 7,283,045 bytes in **889** calls, of which 885 are the 8 kB `smgrextend` calls for the new heap's pages — the remaining 4 calls carry 33,125 bytes. WAL collapses by a factor of 67, because `smgr_bulk_start_rel` sets `use_wal` from `RelationNeedsWAL` and the new relfilenode does not need WAL at `minimal` [bulk_write.c:87-93](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L87-L93). At `replica` the backend writes 12,616,037 bytes in 1,032 calls: the same 885 heap pages plus 147 WAL write calls carrying 5,366,117 bytes, with the rest of the 7.35 MB flushed by the walwriter.

Setting `wal_level` requires a **restart** (`PGC_POSTMASTER`), so this is not a knob to reach for mid-incident.

The predicted `pg_stat_io` blind spot showed up as measured zeros: across the cold and warm runs the client backend's `extends` counter moved by **0** in every context while 885 pages were being added to a new relation, because the bulk-write path calls `smgrextend` directly and never reaches the buffer manager's accounting [bulk_write.c:297-308](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L297-L308), [bufmgr.c:2440-2452](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2440-L2452). If you size a rewrite's write volume from `pg_stat_io`, you will see nothing at all.

`pg_waldump --stats=record` over the exact LSN range of the run decomposes its WAL:

| Record type | Count | Combined bytes | Share |
|---|---|---|---|
| `XLOG/FPI` | **28** | 7,233,753 | 98.66% |
| `Btree/INSERT_LEAF` | 33 | 66,629 | 0.91% |
| `Heap2/MULTI_INSERT` | 5 | 11,734 | 0.16% |
| `Heap/INSERT` | 3 | 10,575 | 0.14% |
| `Heap/UPDATE`, `Heap/DELETE`, `Heap/HOT_UPDATE` | 16 | 8,354 | 0.11% |
| `Transaction/COMMIT`, `Storage/CREATE`, `Standby/LOCK`, `XLOG/NEXTOID` | 5 | 1,121 | 0.02% |
| **Total** | **90** | **7,332,166** | 100% |

**28 records carried the 885 full-page images**, which is `ceil(885 / 32)` — one record per bulk-write batch, exactly as `log_newpages` batches them [xloginsert.c:1188-1210](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L1188-L1210). Not one WAL record describes the 884,956 blocks that were read. The remaining 62 records are catalog churn plus the `Storage/CREATE` of the new relfilenode.

### What the progress view showed

`pg_stat_progress_cluster` was sampled continuously through each rewrite from a second session.

| Run | Samples | `seq scanning heap` | of those, `heap_blks_scanned = 0` | `rebuilding index` |
|---|---|---|---|---|
| No index, 200,000 rows | 434 | 434 | **427** | — |
| One B-tree index | 486 | 471 | 461 | 14, **all reporting `scanned = 884,956` of 884,956** |
| No rows at all | 566 | 566 | **566** | — |

Two facts, and they pull in opposite directions:

- **During the scan the counter is useless on this shape.** For 427 of 434 samples — roughly the first 98% of the command — it reported that **zero** blocks had been scanned out of 884,956, while the backend was demonstrably reading gigabytes. That is what the update site predicts: it fires only after a tuple is returned *and* the block number changed [heapam_handler.c:827-835](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L827-L835), and this heap returns no tuple until block 884,070. Plain `VACUUM` has no such defect: its counterpart is updated once per block before the page is examined [vacuumlazy.c:851-854](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L851-L854).
- **The final value is correct, which is v17-specific.** In the indexed run the `rebuilding index` phase held the command open long enough to sample the post-scan state, and all 14 samples read `heap_blks_scanned = 884,956` of `heap_blks_total = 884,956`, with `heap_tuples_scanned = heap_tuples_written = 200,000`. That is the explicit end-of-scan assignment [heapam_handler.c:803-816](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L803-L816) doing its job on precisely the shape it was written for — "If the last pages of the scan were empty, we would go to the next phase while heap_blks_scanned != heap_blks_total."

`pg_statio_all_tables.heap_blks_read` was correct in every run, which is why the answer above recommends it first.

### The index rebuild reads the new heap

With one `bigint` B-tree index present, built after the fixture was emptied and frozen, the index came to **4,513,792 bytes**. The `VACUUM FULL` that followed read **885,841** heap blocks with **0** hits. That decomposes exactly:

```text
884,956  old heap, the sequential scan
    885  new heap, read back by the B-tree build
-------
885,841  heap_blks_read delta
```

The `/proc` counters decompose the same way: `rchar` moved by 7,257,153,536, which is the scan's 7,249,903,616 plus exactly 7,249,920 — the new heap's 885 blocks — in 59 extra read calls. `idx_blks_read` moved by **1**: the old index was never read, only dropped and rebuilt, and the rebuilt index came out at the same 4,513,792 bytes. The new heap has to be re-read from the file system because the bulk-write path never put it in shared buffers [bulk_write.c:12-17](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L12-L17). So the index-rebuild term is proportional to the surviving rows, as [Index rebuild](#index-rebuild) argues from the reindex happening after the swap.

### What happened to the old file

The 7,249,559,552-byte relation occupied seven segment files: six of 1,073,741,824 bytes and one of 807,108,608, plus a 229,376-byte visibility map and a 1,802,240-byte free space map. Listing the directory immediately after the command committed, before any checkpoint:

```text
-rw------- 1 ... 0        16467      <- old relfilenode, truncated to zero
-rw------- 1 ... 7249920  16470      <- new relfilenode
(16467.1 through 16467.6, 16467_vm and 16467_fsm are already gone)
```

That is precisely the two-part behavior of `mdunlinkfork`: the first segment is truncated and its unlink deferred past the next checkpoint to protect the relfilenode number, while the higher-numbered segments are unlinked on the spot [md.c#mdunlinkfork](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L344-L430). Reclaiming 6.75 GB cost no data movement.

The forks went with it: `vm_bytes` 229,376 -> 0, `fsm_bytes` 1,802,240 -> 0, and `relallvisible` 884,956 -> 0, confirming [What the command leaves behind](#what-the-command-leaves-behind).

### Truncated line pointers, measured

On this fixture, emptied pages kept **no** line pointers at all:

| Probe | Result |
|---|---|
| `page_header` of block 100 | `lower = 24`, `upper = 8192`, `flags = 4` (`PD_ALL_VISIBLE`) |
| `heap_page_items` of block 100 | **0** line pointers, 0 `LP_UNUSED`, 0 `LP_NORMAL`, 0 bytes of tuple data |
| 101-page sample across blocks 0 to 884,069 | min = max = **0** line pointers, 0 live tuples |
| Last block 884,955 | 170 line pointers, all `LP_NORMAL`, all frozen |
| `pg_freespace` | 884,072 pages with free space, 7,214,018,976 bytes available |

`lower = 24` is `SizeOfPageHeaderData` with nothing behind it: the line pointer array is gone entirely, not merely unused. Two v17 mechanisms combine to produce that. `PageRepairFragmentation` removes trailing unused line pointers [bufpage.c:795-806](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L795-L806), and because this fixture had **no indexes when `VACUUM` ran**, `lazy_scan_prune` passed `HEAP_PAGE_PRUNE_MARK_UNUSED_NOW` [vacuumlazy.c:1439-1441](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1439-L1441), so the dead items went straight to `LP_UNUSED` during pruning [pruneheap.c:515-525](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L515-L525) and the whole array was truncated. Had an index been present, VACUUM's second pass would have called `PageTruncateLinePointerArray` instead, which leaves one `LP_UNUSED` item behind [bufpage.c:825-828](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L825-L828).

The visible consequence for bloat measurement is that `pgstattuple` tells the truth here: `tuple_percent` 0.09 and `free_percent` **99.56**, against a `table_len` of 7,249,559,552 and `tuple_len` of 6,400,000.

### How to reproduce

The sandbox was deleted after the run, so the fixture is published in full. It needs a throwaway 17.11 cluster built from `raw/postgres-17/`; do not run it against anything you care about, since it writes about 7 GB plus WAL and holds `AccessExclusiveLock`.

```sql
-- Fixture. Approximately 7 GB of heap plus WAL; takes a few minutes.
CREATE TABLE bloat (id bigint NOT NULL);
INSERT INTO bloat SELECT g FROM generate_series(1, 200000000) g;
DELETE FROM bloat WHERE id <= 199800000;
VACUUM (VERBOSE) bloat;
VACUUM (FREEZE, VERBOSE) bloat;

SELECT /* wiki_vf17_fixture_state */
       pg_relation_size('bloat')        AS heap_bytes,
       pg_relation_size('bloat') / 8192 AS heap_blocks,
       (SELECT count(*) FROM bloat)     AS live_rows,
       (SELECT all_visible FROM pg_visibility_map_summary('bloat')) AS all_visible,
       (SELECT all_frozen  FROM pg_visibility_map_summary('bloat')) AS all_frozen;
```

Take the block counters before and after the rewrite from both channels, in a session that then forces its pending statistics out:

```sql
BEGIN;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '2s';

SELECT /* wiki_vf17_read_counters */
       s.heap_blks_read, s.heap_blks_hit,
       (SELECT reads FROM pg_stat_io
         WHERE backend_type = 'client backend'
           AND object = 'relation' AND context = 'bulkread') AS bulkread_reads
  FROM pg_statio_all_tables s
 WHERE s.relid = 'bloat'::regclass;
COMMIT;
```

`pg_stat_force_next_flush()` in the session that ran the `VACUUM FULL` makes its counters visible immediately rather than after the next flush interval. Read the backend's own byte and syscall counters from `/proc`, which is the only way to see the read *call* count:

```bash
# Cold-cache reads: evict the relation, then compare the backend's counters.
#   base/<db>/<relfilenode> comes from SELECT pg_relation_filepath('bloat');
python3 - "$PGDATA/base/16384/16467" <<'PY'
import os, sys
base = sys.argv[1]
for p in [base] + [f"{base}.{i}" for i in range(1, 64)]:
    if os.path.exists(p):
        fd = os.open(p, os.O_RDONLY)
        os.fsync(fd); os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED); os.close(fd)
PY
grep -E 'rchar|syscr|read_bytes' /proc/<backend pid>/io   # before and after
```

The `VACUUM (FULL, VERBOSE)` line count needs no tooling at all: it prints the old relation's block count directly [cluster.c:992-1002](../../../../raw/postgres-17/src/backend/commands/cluster.c#L992-L1002).

## What Changed Since PostgreSQL 12

The answer to the question itself did not change: no commit has ever taught the `CLUSTER` / `VACUUM FULL` heap scan to consult the visibility map. Searching the checkout's own history for `visibilitymap` in the three files that make up the rewrite finds nothing in `cluster.c` and `rewriteheap.c`, and in `heapam_handler.c` only `04e72ed617b` ("BitmapHeapScan: Push skip_fetch optimization into table AM", earliest containing tag `REL_17_0`), which touches the bitmap-scan callback and not `heapam_relation_copy_for_cluster`. The read side is still "every block, once".

Nine things around it did change. Each row names the commit from the pinned checkout's own history and the earliest release tag that contains it.

| Change | Commit | First shipped | Effect on this shape |
|---|---|---|---|
| Sequential scans read through the read stream | `b7b0f3f2724` | `REL_17_0` | The rewrite's scan inherits read combining, since `table_beginscan` sets `SO_TYPE_SEQSCAN` [tableam.h:913-921](../../../../raw/postgres-17/src/include/access/tableam.h#L913-L921) |
| The read stream API itself | `b5a9b18cd0b` | `REL_17_0` | Look-ahead and merging logic [read_stream.c:10-46](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L10-L46) |
| `io_combine_limit` GUC plus `StartReadBuffers`/`WaitReadBuffers` | `210622c60e1` | `REL_17_0` | Caps a single read at 16 blocks by default [bufmgr.h:168-170](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L168-L170) |
| `smgrreadv`/`smgrwritev` | `4908c587205` | `REL_17_0` | One `preadv` per run of blocks [md.c#mdreadv](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L821-L929) |
| `bulk_write.c`, and `rewriteheap.c` converted to use it | `8af25652489` | `REL_17_0` | New heap pages are queued 32 at a time, WAL-logged per batch, and the trailing `smgrimmedsync` is replaced by `smgrregistersync` [bulk_write.c:130-223](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L130-L223) |
| `heap_sync()` removed | `c6b92041d38` | `REL_13_0` | Removed the rewrite's forced sync of the TOAST heap |
| `heap_blks_scanned` fixed: per block, wraparound-corrected, squared up at end of scan | `3df51ca8b39` (master) | `REL_14_0`, and back-patched as `dcc20946a8f` to `REL_13_2` and `fce17e486f3` to `REL_12_6` | The final progress value is now correct; the mid-scan stall on empty pages remains |
| `pg_stat_io` | `a9c70b46dbe` | `REL_16_0` | A `bulkread`-filtered view of the same block count |
| `BUFFER_USAGE_LIMIT`, `vacuum_buffer_usage_limit`, and the `FULL` rejection | `1cbbee03385` | `REL_16_0` | The one new buffer knob explicitly does not apply to `VACUUM FULL` [vacuum.c:322-331](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L322-L331) |
| `PROCESS_TOAST`, required with `FULL` | `7cb3048f38e` | `REL_14_0` | `VACUUM (FULL, PROCESS_TOAST false)` is an error [vacuum.c:360-364](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L360-L364) |

Two changes matter enough to state separately, because they change numbers a reader might compare against an older measurement:

- **Emptied pages no longer keep their line pointer array.** v17's `PageRepairFragmentation` removes trailing unused line pointers [bufpage.c:683-699](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L683-L699), and `PageTruncateLinePointerArray` does the same in VACUUM's second pass [bufpage.c:815-835](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L815-L835). On a table with no indexes VACUUM goes further: `lazy_scan_prune` passes `HEAP_PAGE_PRUNE_MARK_UNUSED_NOW` when `nindexes == 0` [vacuumlazy.c:1439-1441](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1439-L1441), so dead items become `LP_UNUSED` during pruning [pruneheap.c:1279-1293](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1279-L1293) and the array is truncated away entirely. Measured consequence on this fixture: every emptied page ended with `pd_lower = 24` and **zero** line pointers, `pgstattuple` reported **99.56%** free, and the rewrite's scan had one line pointer per page to reject rather than one per tuple the page once held. On a major that retains the array, the same rows leave a full-width array behind, which both costs scan CPU and is counted as neither tuple nor free space; that comparison is not made here because it would need same-version evidence from that major. See [Truncated line pointers, measured](#truncated-line-pointers-measured).
- **`reltuples` survives the fixture's `VACUUM FREEZE`.** `vac_estimate_reltuples` keeps the existing value when the relation is exactly the same size and less than 2% of its pages were scanned [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1313-L1348), so the aggressive vacuum that scanned 886 of 884,956 pages left `reltuples = 200000` instead of extrapolating the old density over the unscanned pages.

Two traps for anyone extending this comparison: the "eager and lazy freezing strategies" commit `4d417992613` reports `REL_16_0` from `git tag --contains` but was reverted the same day by `6c6b4972664` and never shipped; and `io_max_combine_limit` (`10f66468475`) plus the `vacuum_truncate` GUC (`0164a0f9ee1`) are PostgreSQL 18 changes that are not in this checkout.

## Context Reviewed

- Dispatch, options and locking: [vacuum.c](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L296-L375) option assembly and the four `FULL` interactions, [vacuum.c:1980-2310](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1980-L2310) `vacuum_rel` including the lock mode, the reloption resolution and the TOAST-recursion suppression, [vacuum.c:1301-1366](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1301-L1366) `vac_estimate_reltuples`, [vacuum.c:2380-2420](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2380-L2420) `vacuum_delay_point`.
- Rewrite driver: all of [cluster.c](../../../../raw/postgres-17/src/backend/commands/cluster.c#L300-L440) `cluster_rel`, [cluster.c:632-812](../../../../raw/postgres-17/src/backend/commands/cluster.c#L632-L812) `rebuild_relation` and `make_new_heap`, [cluster.c:814-1060](../../../../raw/postgres-17/src/backend/commands/cluster.c#L814-L1060) `copy_table_data`, [cluster.c:1061-1140](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1061-L1140) `swap_relation_files`, [cluster.c:1438-1520](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1438-L1520) `finish_heap_swap`.
- Heap AM copy callback: [heapam_handler.c](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L690-L994) `heapam_relation_copy_for_cluster` in full, including the progress-reporting sites and the dead-tuple branch.
- Rewrite module: [rewriteheap.c](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L120-L340) state and lifecycle, [rewriteheap.c:590-680](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L590-L680) `raw_heap_insert` and the TOAST call.
- Bulk write facility: all of [bulk_write.c](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L1-L351).
- Sequential-scan mechanics and the read stream: [heapam.c](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L340-L530) callbacks and `initscan`, [heapam.c:590-740](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L590-L740) `heap_prepare_pagescan` and `heap_fetch_next_buffer`, [heapam.c:780-1046](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L780-L1046) block advance and `heapgettup`, [heapam.c:1150-1300](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1150-L1300) `heap_beginscan`/`heap_rescan`; all of [read_stream.c](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L1-L600).
- Vectored I/O and buffer accounting: [bufmgr.c:1140-1540](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1140-L1540) `PinBufferForBlock`, `StartReadBuffersImpl`, `WaitReadBuffers`, [bufmgr.c:2250-2460](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2250-L2460) the buffered extend path, [bufmgr.c:3993-4030](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3993-L4030) `RelationGetNumberOfBlocksInFork`; [md.c:700-1035](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L700-L1035) `mdreadv`/`mdwritev`; [pgstat_io.c](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_io.c#L76-L155) the I/O counters.
- Buffer strategy: [freelist.c:530-680](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L530-L680) ring sizes, buffer count and pin limit, [freelist.c:750-816](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L750-L816) I/O context mapping and `StrategyRejectBuffer`.
- Storage teardown: [md.c:290-430](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L290-L430) `mdunlink`/`mdunlinkfork`/`do_truncate`, [md.c:1405-1455](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L1405-L1455) `register_unlink_segment`.
- Page and line pointer handling: [bufpage.c:680-900](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L680-L900) `PageRepairFragmentation` and `PageTruncateLinePointerArray`, [pruneheap.c:300-540](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L300-L540) `heap_page_prune_and_freeze` option handling, [pruneheap.c:1260-1300](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1260-L1300) and [pruneheap.c:1550-1720](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1550-L1720) the record/execute halves.
- Plain VACUUM, for the control runs: [vacuumlazy.c:380-400](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L380-L400) option resolution, [vacuumlazy.c:820-1030](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L820-L1030) `lazy_scan_heap` with its per-block progress update, [vacuumlazy.c:1070-1260](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1070-L1260) the skip machinery, [vacuumlazy.c:1420-1460](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1420-L1460) the one-pass prune option, [vacuumlazy.c:2200-2250](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2200-L2250) `lazy_vacuum_heap_page`, [vacuumlazy.c:2509-2560](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2509-L2560) `should_attempt_truncation`.
- WAL: [xloginsert.c:1140-1230](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L1140-L1230) `log_newpage`/`log_newpages`, [xlogrecord.h:228-244](../../../../raw/postgres-17/src/include/access/xlogrecord.h#L228-L244) `XLR_MAX_BLOCK_ID`.
- Reloptions: [reloptions.c:80-160](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L80-L160) including the `vacuum_truncate` lock-level rationale.
- GUCs: [guc_tables.c:2262-2281](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2262-L2281) `shared_buffers` and `vacuum_buffer_usage_limit`, [guc_tables.c:2546-2553](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2546-L2553) and [guc_tables.c:3865-3873](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3865-L3873) the vacuum cost settings, [guc_tables.c:3110-3147](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3110-L3147) the three asynchronous-I/O settings, [guc_tables.c:1767-1774](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1767-L1774) `synchronize_seqscans`.
- Interfaces: [tableam.h:900-930](../../../../raw/postgres-17/src/include/access/tableam.h#L900-L930) `table_beginscan` flags, [bufmgr.h:160-175](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L160-L175) the combine-limit constants, [pg_iovec.h:35-50](../../../../raw/postgres-17/src/include/port/pg_iovec.h#L35-L50) `PG_IOV_MAX`, [bufpage.h:110-220](../../../../raw/postgres-17/src/include/storage/bufpage.h#L110-L220) page accessors.
- Docs: [ref/vacuum.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/vacuum.sgml#L70-L360) the `FULL` description and every option that interacts with it, [ref/vacuum.sgml:460-505](../../../../raw/postgres-17/doc/src/sgml/ref/vacuum.sgml#L460-L505) the progress-view note, [maintenance.sgml:120-255](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L120-L255) the space-recovery discussion, [monitoring.sgml:2497-2840](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L2497-L2840) `pg_stat_io`, [monitoring.sgml:5460-5660](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L5460-L5660) `pg_stat_progress_cluster` and its phases, [monitoring.sgml:6200-6250](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L6200-L6250) the VACUUM progress contrast.
- Tests: [vacuum.sql](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L18-L110), [vacuum.sql:155-200](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L155-L200), [vacuum.sql:310-335](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L310-L335).

## Evidence Map

| Claim | Evidence |
|---|---|
| `VACUUM FULL` is `CLUSTER` with no index | [vacuum.c:2248-2261](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2248-L2261), [cluster.c:306-311](../../../../raw/postgres-17/src/backend/commands/cluster.c#L306-L311) |
| It takes `AccessExclusiveLock` | [vacuum.c:2054-2055](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2054-L2055), [cluster.c:337](../../../../raw/postgres-17/src/backend/commands/cluster.c#L337) |
| `PARALLEL`, `DISABLE_PAGE_SKIPPING` and `BUFFER_USAGE_LIMIT` are errors with `FULL`; `PROCESS_TOAST` is required | [vacuum.c:317-364](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L317-L364) |
| No sort, so no temp-file I/O in the heap phase | [cluster.c:948-951](../../../../raw/postgres-17/src/backend/commands/cluster.c#L948-L951), [heapam_handler.c:729-735](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L729-L735) |
| Plain seq scan with `SnapshotAny`, no scan keys | [heapam_handler.c:760-773](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L760-L773), [heapam_handler.c:737-741](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L737-L741) |
| `heap_blks_total` is the whole relation | [heapam_handler.c:770-773](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L770-L773), [monitoring.sgml:5584-5592](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L5584-L5592) |
| No visibility-map skipping in the rewrite | no `visibilitymap` reference in [cluster.c](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1-L70) or [rewriteheap.c](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L100-L120), and only the bitmap-scan callback in [heapam_handler.c](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L2130-L2150); contrast [monitoring.sgml:6229-6236](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L6229-L6236) |
| Every block is visited exactly once | [heapam.c:425-431](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L425-L431), [heapam.c:867-906](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L867-L906), [heapam.c:974-1035](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L974-L1035) |
| Blocks arrive through the read stream, one buffer at a time | [heapam.c:1237-1259](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1237-L1259), [heapam.c:692-734](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L692-L734), [tableam.h:913-921](../../../../raw/postgres-17/src/include/access/tableam.h#L913-L921) |
| Adjacent blocks are merged into one `preadv`, capped at `io_combine_limit` | [read_stream.c:10-20](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L10-L20), [bufmgr.c:1494-1521](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1494-L1521), [md.c:842-848](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L842-L848), [bufmgr.h:168-170](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L168-L170) |
| Look-ahead is bounded by `effective_io_concurrency` and the strategy pin limit; advice is off for sequential streams | [read_stream.c:419-442](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L419-L442), [read_stream.c:452-472](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L452-L472), [read_stream.c:508-520](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L508-L520), [freelist.c:646-661](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L646-L661) |
| Block counters count blocks regardless of read size | [bufmgr.c:1162-1171](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1162-L1171) |
| `pg_stat_io.reads` is incremented by the block count, not by one per read call | [bufmgr.c:1518-1521](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1518-L1521), [pgstat_io.c:82-93](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_io.c#L82-L93), against [monitoring.sgml:2616-2626](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L2616-L2626) |
| Vacuumed-empty pages keep at most one line pointer | [bufpage.c:683-699](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L683-L699), [bufpage.c:795-806](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L795-L806), [bufpage.c:815-835](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L815-L835), [vacuumlazy.c:1439-1441](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1439-L1441), [pruneheap.c:515-525](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L515-L525) |
| Page-mode off under `SnapshotAny`, so no opportunistic pruning | [heapam.c:1182-1186](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1182-L1186), [heapam.c:618-628](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L618-L628), [heapam.c:1417-1425](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1417-L1425) |
| Read volume is the physical file size | [bufmgr.c:3993-4020](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3993-L4020) |
| New pages go through the bulk-write facility, outside shared buffers | [rewriteheap.c:130-140](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L130-L140), [rewriteheap.c:250-260](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L250-L260), [rewriteheap.c:655-663](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L655-L663), [bulk_write.c:1-25](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L1-L25) |
| Writes are queued 32 at a time and extended one page per call | [bulk_write.c:48](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L48), [bulk_write.c:323-335](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L323-L335), [bulk_write.c:278-310](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L278-L310), [xlogrecord.h:241](../../../../raw/postgres-17/src/include/access/xlogrecord.h#L241) |
| The rewrite's extends are invisible to `pg_stat_io` | `smgrextend` called directly at [bulk_write.c:297-308](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L297-L308) against the only extend accounting, at [bufmgr.c:2440-2452](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2440-L2452) |
| Dead tuples are never written | [heapam_handler.c:894-905](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L894-L905) |
| Packing rule and fillfactor inheritance | [rewriteheap.c:643-646](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L643-L646), [cluster.c:711-721](../../../../raw/postgres-17/src/backend/commands/cluster.c#L711-L721), [bufpage.c#PageGetHeapFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L976-L1011) |
| A tupleless rewrite writes no page at all | [rewriteheap.c:296-327](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L296-L327) |
| WAL only when the new relation needs it, one `XLOG_FPI` record per 32 pages | [bulk_write.c:87-93](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L87-L93), [bulk_write.c:254-276](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L254-L276), [xloginsert.c:1174-1228](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L1174-L1228) |
| The fsync is registered for the next checkpoint, not done inline | [bulk_write.c:130-223](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L130-L223) |
| Relfilenodes are swapped, not copied | [cluster.c:1061-1140](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1061-L1140), [cluster.c:1438-1520](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1438-L1520) |
| First segment truncated with its unlink deferred; later segments unlinked at once | [md.c:344-430](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L344-L430), [md.c:1410-1450](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L1410-L1450) |
| Indexes rebuilt from the new heap, after the swap | [cluster.c:1505-1512](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1505-L1512), [cluster.c:302-305](../../../../raw/postgres-17/src/backend/commands/cluster.c#L302-L305) |
| TOAST not recursed into; external values re-saved by the rewrite | [vacuum.c:2210-2224](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2210-L2224), [rewriteheap.c:596-630](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L596-L630) |
| 256 kB / 32-buffer `BAS_BULKREAD` ring, `bulkread` I/O context, ring not absolute | [heapam.c:433-465](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L433-L465), [freelist.c:551-573](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L551-L573), [freelist.c:774-775](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L774-L775), [freelist.c:786-816](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L786-L816) |
| No `vacuum_delay_point` in the rewrite path | [vacuum.c:2380-2420](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2380-L2420) plus zero matches in `cluster.c`, `rewriteheap.c` and `heapam_handler.c` |
| Cost, buffer and I/O settings and their apply scopes | [guc_tables.c:2273-2281](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2273-L2281), [guc_tables.c:2546-2553](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2546-L2553), [guc_tables.c:3110-3147](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3110-L3147), [guc_tables.c:3865-3873](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3865-L3873) |
| `heap_blks_scanned` advances per block only when a tuple is returned, but is squared up at end of scan | [heapam_handler.c:827-835](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L827-L835), [heapam_handler.c:803-816](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L803-L816), against the per-block update in plain VACUUM at [vacuumlazy.c:851-854](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L851-L854) |
| `reltuples` is preserved through a small aggressive scan | [vacuum.c:1329-1348](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1329-L1348) |
| Truncation control, and the `vacuum_truncate` reloption path | [vacuumlazy.c:2529-2544](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2529-L2544), [vacuumlazy.c:391](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L391), [vacuum.c:2190-2202](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2190-L2202), [reloptions.c:150-158](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L150-L158) |
| Plain VACUUM skips all-visible and all-frozen runs | [vacuumlazy.c:1087-1170](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1087-L1170), [vacuumlazy.c:1186-1255](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1186-L1255), [vacuumlazy.c:111](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L111) |
| Correctness-only test coverage | [vacuum.sql:20-22](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L20-L22), [vacuum.sql:161-163](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L161-L163), [vacuum.sql:329-330](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L329-L330) |

Measured on the 17.11 server built from this pin (see [Measured On A 17.11 Server](#measured-on-a-1711-server)); the source column gives the mechanism the measurement exercises:

| Measured claim | Number | Mechanism |
|---|---|---|
| Every block of the old heap is read | `heap_blks_read` 884,956 of 884,956 with 0 hits; `read_bytes` 7,249,559,552 | [heapam.c:425-431](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L425-L431), [heapam.c:867-906](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L867-L906) |
| All-frozen pages are read anyway | all 884,956 pages all-frozen beforehand; plain `VACUUM` read 0 | no `visibilitymap` reference in the rewrite, against [vacuumlazy.c:1087-1170](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1087-L1170) |
| Reads are combined at `io_combine_limit` | 55,361 calls for 884,956 blocks (15.985 blocks/call); 28,179 -> 976 calls across `8kB` -> `256kB` | [bufmgr.c:1494-1521](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1494-L1521), [md.c:842-848](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L842-L848) |
| Combining does not change the block count | `heap_blks_read + heap_blks_hit` = 44,248 at every one of six settings | [bufmgr.c:1162-1171](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1162-L1171) |
| The new heap is sized by live rows | 885 blocks / 7,249,920 bytes for 200,000 rows; 0 bytes for 0 rows | [rewriteheap.c:640-673](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L640-L673), [rewriteheap.c:296-327](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L296-L327) |
| WAL batches 32 pages per record | 28 `XLOG/FPI` records for 885 pages | [xloginsert.c:1188-1210](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L1188-L1210) |
| WAL is skipped at `minimal` | 110,008 bytes against 7,353,992 at `replica`, same 884,956 reads | [bulk_write.c:87-93](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L87-L93) |
| The index rebuild reads only the new heap | 885,841 = 884,956 + 885; `idx_blks_read` +1 | [cluster.c:1505-1512](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1505-L1512), [bulk_write.c:12-17](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L12-L17) |
| The progress view stalls during the scan but ends correct | 427 of 434 samples at 0; 14 of 14 at 884,956 after the scan | [heapam_handler.c:827-835](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L827-L835), [heapam_handler.c:803-816](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L803-L816) |
| Emptied pages keep no line pointers | `pd_lower = 24`, 0 line pointers on 101 sampled pages; `pgstattuple` `free_percent` 99.56 | [bufpage.c:795-806](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L795-L806), [vacuumlazy.c:1439-1441](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1439-L1441) |
| The old file is truncated and its later segments unlinked before any checkpoint | first segment 0 bytes, `.1`-`.6`, `_vm` and `_fsm` gone | [md.c:344-430](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L344-L430) |
| The command leaves no visibility map | `vm_bytes` 229,376 -> 0, `relallvisible` 884,956 -> 0 | [cluster.c:1061-1140](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1061-L1140) |
| `reltuples` is not distorted by the aggressive freeze | 200,000 after a scan of 886 of 884,956 pages | [vacuum.c:1329-1348](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1329-L1348) |

## Open Questions

1. **`pg_stat_io.reads` contradicts its own documentation when reads are combined.** Source increments the counter by the block count [bufmgr.c:1518-1521](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1518-L1521), [pgstat_io.c:82-93](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_io.c#L82-L93); the docs call it a count of read operations of `op_bytes` each [monitoring.sgml:2616-2626](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L2616-L2626). Measured, `reads` was 884,956 while the backend made 55,361 read calls. Source wins, but whether the documentation or the counter is considered the defect in this branch is not settled here.
2. **`maintenance.sgml` overstates the transient space for this shape by four orders of magnitude.** It says a rewrite "temporarily use[s] extra disk space approximately equal to the size of the table" [maintenance.sgml:226-239](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L226-L239). Measured, the transient heap was 7,249,920 bytes against an old relation of 7,249,559,552 — a factor of **0.0001**. The statement is right for a table that is actually full and wrong for the shape this page is about; `ref/vacuum.sgml` states the same idea without quantifying it [ref/vacuum.sgml:99-108](../../../../raw/postgres-17/doc/src/sgml/ref/vacuum.sgml#L99-L108).
3. **TOAST was never exercised.** The fixture is a single `bigint` column, so `rewrite_heap_tuple`'s detoast-and-re-save path [rewriteheap.c:596-630](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L596-L630) never ran. The claim that TOAST work is proportional to live toasted bytes rests on source alone.
4. **Only one row width and one scale were measured.** Everything here is a 32-byte `bigint` tuple at 226 per page in a 6.75 GB heap. The read side cannot depend on width, since it is a block count, but the 999.95:1 read-to-write ratio is a function of the surviving row count and width and should not be quoted for another shape.
5. **The hint-bit write term was nil on this shape and remains unbounded in general.** Every page was frozen before the rewrite, so no old-heap dirtying occurred. A heap carrying unset hint bits was not tested; `heapam_handler.c` still takes a share lock and calls `HeapTupleSatisfiesVacuum` per tuple [heapam_handler.c:838-892](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L838-L892), which can set hint bits and dirty pages in the old relation.
6. **The fsync path was inferred, not observed.** `smgr_bulk_finish` normally calls `smgrregistersync` and falls back to `smgrimmedsync` only if a checkpoint intervened [bulk_write.c:200-222](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L200-L222). No run was instrumented to distinguish the two, and `checkpoint_timeout` was 30 minutes with `max_wal_size` 4 GB, so the fallback may or may not have been taken during the WAL-heavy fixture builds.
7. **Storage was a single local SSD-backed filesystem in WSL2.** The block-layer numbers (`read_bytes`) and the 2.5x warm/cold wall-clock ratio are properties of that setup. The syscall and block counts are not, and reproduced byte-identically across independent runs.
8. **The sandbox was deleted afterwards at the asker's instruction.** The fixture SQL is published under [How to reproduce](#how-to-reproduce), but the harness that took the `/proc` samples and the progress-view samples is gone, so re-running requires rebuilding both from the published methodology.

## Source References

- Command dispatch and options: [vacuum.c](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L296-L375)
- Rewrite driver: [cluster.c](../../../../raw/postgres-17/src/backend/commands/cluster.c#L300-L440)
- Heap AM copy callback: [heapam_handler.c](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L690-L994)
- Rewrite module: [rewriteheap.c](../../../../raw/postgres-17/src/backend/access/heap/rewriteheap.c#L120-L340)
- Bulk write facility: [bulk_write.c](../../../../raw/postgres-17/src/backend/storage/smgr/bulk_write.c#L1-L351)
- Sequential scan and read stream: [heapam.c](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L340-L530), [read_stream.c](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L1-L600)
- Buffer manager and vectored I/O: [bufmgr.c](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1140-L1540), [md.c](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L700-L1035)
- Buffer strategy: [freelist.c](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L530-L680)
- Page and line pointers: [bufpage.c](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L680-L900), [pruneheap.c](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L1550-L1720)
- Plain VACUUM: [vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1070-L1260)
- WAL: [xloginsert.c](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L1140-L1230)
- Settings: [guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3110-L3147)
- Documentation: [ref/vacuum.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/vacuum.sgml#L70-L360), [maintenance.sgml](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L120-L255), [monitoring.sgml](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L2497-L2840)
- Tests: [vacuum.sql](../../../../raw/postgres-17/src/test/regress/sql/vacuum.sql#L18-L110)

## Navigation

- [v17/index](../../index.md) - PostgreSQL 17 landing page.
- [PostgreSQL 17 Codebase Navigation Guide](../../codebase-navigation-guide.md) - Map of the pinned v17 source tree.
- [wiki index](../../../index.md) - Global catalog.
- [versions](../../../versions.md) - Source pin manifest.
