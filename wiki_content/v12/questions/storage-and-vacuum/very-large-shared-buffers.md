---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# Pros and Cons of a Very Large shared_buffers Such as 256 GB on a 1 TB RAM System in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [What 256 GB of shared_buffers actually allocates](#what-256-gb-of-shared_buffers-actually-allocates)
  - [Pros](#pros)
  - [Cons](#cons)
  - [Hard limits above 256 GB](#hard-limits-above-256-gb)
  - [Thresholds that move when NBuffers is huge](#thresholds-that-move-when-nbuffers-is-huge)
  - [What a big pool does not buy](#what-a-big-pool-does-not-buy)
  - [Structures, build inputs and extension boundaries](#structures-build-inputs-and-extension-boundaries)
  - [Settings that move with it, and their apply scope](#settings-that-move-with-it-and-their-apply-scope)
  - [What to look at before and after the change](#what-to-look-at-before-and-after-the-change)
  - [Decision guide](#decision-guide)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 12, what are the pros and cons of having a very large `shared_buffers`, like 256 GB or more, on a system with more than 1 TB of RAM?

Prompt note, per `MANDATORY Prompt Hygiene`: the original request read `follow agents.md, in postgresql 12, question : what are the pros and cons of having a very large shared buffers like 256GB or more on a system with more than 1TB of RAM.` The defects were `agents.md` for AGENTS.md, lowercase `postgresql`, a space before the colon, `a very large shared buffers` for the GUC `shared_buffers`, `256GB`/`1TB` missing the space before the unit, a lowercase sentence start, and a terminating period on a question. The asker chose **correct and restate**, chose **source-only evidence with no measured numbers**, and chose **v12-only framing** with no reference to controls that exist in other major versions. All three choices are recorded here.

Review prompt, 2026-09-16, corrected form: `Follow AGENTS.md. In PostgreSQL 12, review the question page "Pros and Cons of a Very Large shared_buffers Such as 256 GB on a 1 TB RAM System in PostgreSQL 12".` The request as written read `follow agents.md, in postgresql 12, review question: # Pros and Cons of a Very Large shared_buffers Such as 256 GB on a 1 TB RAM System in PostgreSQL 12 (unverified)`; the defects were `agents.md` for AGENTS.md, lowercase `postgresql`, the lowercase sentence opening `follow`, a stray Markdown heading marker `#` inside the sentence, the page-state hint `(unverified)` carried into the prompt text, and no terminal period. The asker chose **correct and restate**, a **full claim-by-claim re-verification** of every citation range, **no measurements** so the page stays source-only, and **report before editing**. That review found no incorrect claim and no citation defect; it found omissions, which this revision fixes.

## Answer

### Short answer

**256 GB is within PostgreSQL 12's configuration range, but source alone cannot establish that it is the best size for a 1 TB machine.** The same-checkout documentation suggests 25% of memory as a starting point for a dedicated database server and cautions that more than 40% is unlikely to outperform a smaller allocation. These are general recommendations, not a benchmark of a 1 TB host. A valid setting can still fail at startup if the shared-memory allocation fails. [guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2163) [config.sgml#shared_buffers](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1488-L1531) [sysv_shmem.c#CreateAnonymousSegment](../../../../raw/postgres-12/src/backend/port/sysv_shmem.c#L528-L590)

PostgreSQL's memory units are binary: `shared_buffers = '256GB'` means 256 GiB. With the default 8192-byte `BLCKSZ`, that is **33,554,432 buffers**. It is 25% of 1 TiB, not 25% of a decimal terabyte. These are arithmetic conversions, not measurements. [guc.c#memory_unit_conversion_table](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L788-L818) [configure.in#blocksize](../../../../raw/postgres-12/configure.in#L247-L277)

The potential benefit is retaining useful pages and avoiding repeated reads or dirty evictions. The costs include reserved memory, larger full-pool scans, and a higher threshold for using the bulk-read ring. Two specifics are worth carrying into the decision: the pool's own bookkeeping adds roughly **6.13 GiB** of shared memory on top of the 256 GiB of pages, and 33,554,432 buffers sits one MiB on the wrong side of a mapping-hash power-of-two boundary that costs about **257 MiB** of that. Source establishes these mechanisms; it does not establish their net effect or a proportional increase in elapsed time. [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L743-L796) [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1065-L1165) [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1828-L1871) [heapam.c#initscan](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L265)

### What 256 GB of shared_buffers actually allocates

`shared_buffers` is a `PGC_POSTMASTER` setting: changing it requires a **restart**. Its range is 16 through `INT_MAX / 2` blocks. The C default is 1024 blocks; `initdb` instead tries candidate sizes starting at 128 MiB, scales its 8192-byte trial units to the configured `BLCKSZ`, and tests them with a bootstrap backend. It may select a smaller value. [guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2163) [initdb.c#test_config_settings](../../../../raw/postgres-12/src/bin/initdb/initdb.c#L947-L967) [initdb.c#test_config_settings](../../../../raw/postgres-12/src/bin/initdb/initdb.c#L1018-L1050)

The setting covers page storage. `BufferShmemSize()` also includes three arrays—buffer descriptors, I/O locks and checkpoint sort slots—plus the mapping hash and strategy control structure. The freelist uses `BufferDesc.freeNext`; it is not another per-buffer array. The checkpointer separately reserves `NBuffers` request slots. Other subsystems and extensions add to the main shared-memory request. [buf_init.c#BufferShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L160-L193) [buf_internals.h#BufferDesc](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L135-L190) [freelist.c#StrategyShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L453-L465) [checkpointer.c#CheckpointerShmemSize](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L889-L902) [ipci.c#CreateSharedMemoryAndSemaphores](../../../../raw/postgres-12/src/backend/storage/ipc/ipci.c#L94-L166)

The following sizes are **conditional layout arithmetic**, not values measured from a build. They assume 8192-byte blocks, 8-byte pointers, 4-byte `int`, OID, block-number and enum fields, the ordinary alignment implied by those types, `sizeof(BufferDesc) <= 64`, and `sizeof(LWLock) <= 32`. A debug build or different ABI can invalidate the assumptions. The definitions, including the conditional lock padding, are the evidence for the calculation. [buf_internals.h#BufferDescPadded](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L192-L218) [lwlock.h#LWLock](../../../../raw/postgres-12/src/include/storage/lwlock.h#L32-L41) [lwlock.h#LWLOCK_MINIMAL_SIZE](../../../../raw/postgres-12/src/include/storage/lwlock.h#L61-L88) [buf_internals.h#BufferTag](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L91-L96)

| Allocation | Assumed bytes per slot | Derived total at 256 GiB | Source |
|---|---|---|---|
| Page | 8192 | 256 GiB | [buf_init.c#InitBufferPool](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L81-L83) |
| `BufferDescPadded` | 64 | 2 GiB | [buf_internals.h#BufferDescPadded](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L192-L218) |
| `LWLockMinimallyPadded` | 32 | 1 GiB | [lwlock.h#LWLOCK_MINIMAL_SIZE](../../../../raw/postgres-12/src/include/storage/lwlock.h#L61-L88) |
| `CkptSortItem` | 20 | 640 MiB | [buf_internals.h#CkptSortItem](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L283-L298) |
| `CheckpointerRequest` | 24 | 768 MiB | [sync.h#FileTag](../../../../raw/postgres-12/src/include/storage/sync.h#L45-L51) [checkpointer.c#CheckpointerRequest](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L109-L113) |
| Mapping hash | `BufferLookupEnt` is 24; `hash_estimate_size()` turns that into buckets, a segment directory and element groups | **≈1.75 GiB**, derived below | [buf_table.c#BufTableShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/buf_table.c#L28-L45) [freelist.c#StrategyShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L453-L465) [lwlock.h#NUM_BUFFER_PARTITIONS](../../../../raw/postgres-12/src/include/storage/lwlock.h#L107-L126) [dynahash.c#hash_estimate_size](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L731-L767) |

The four listed non-page arrays add **4.375 GiB**. The mapping hash adds about **1.75 GiB** more, so the shared memory this pool needs beyond its own pages is roughly **6.13 GiB**, before padding and every other shared-memory consumer. Both totals follow from the preceding conditional sizes and the allocation formulas; neither is the size of the complete server mapping. [buf_init.c#BufferShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L160-L193) [checkpointer.c#CheckpointerShmemSize](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L889-L902) [ipci.c#CreateSharedMemoryAndSemaphores](../../../../raw/postgres-12/src/backend/storage/ipc/ipci.c#L94-L166)

The mapping hash can be derived rather than left open, because `hash_estimate_size()` is arithmetic. `StrategyShmemSize()` requests `NBuffers + NUM_BUFFER_PARTITIONS` entries, which is 33,554,560 here. `next_pow2_long()` calls `my_log2()`, a ceiling, so the bucket count is the first power of two at or above that: **2^26**. The estimate is then a 262,144-slot segment directory at 8 bytes per slot, 262,144 segments of `MAXALIGN(256 * 8)` = 2,048 bytes, and elements in groups of `choose_nelem_alloc(24)` = 51 at `MAXALIGN(16) + MAXALIGN(24)` = 40 bytes each. That is 2 MiB plus 512 MiB plus 1,280 MiB. [freelist.c#StrategyShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L453-L465) [dynahash.c#hash_estimate_size](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L731-L767) [dynahash.c#my_log2](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L1716-L1730) [dynahash.c#choose_nelem_alloc](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L603-L628) [dynahash.c#DEF_SEGSIZE](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L110-L113) [hsearch.h#HASHELEMENT](../../../../raw/postgres-12/src/include/utils/hsearch.h#L46-L55) [dynahash.c#HASHBUCKET](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L118-L122)

**256 GiB lands on the wrong side of a power-of-two boundary.** 33,554,432 buffers is exactly 2^25, and the `+ NUM_BUFFER_PARTITIONS` term pushes the requested entry count 128 past it, so the bucket count doubles to 2^26 and the segment array doubles from 256 MiB to 512 MiB. Requesting 33,554,304 blocks instead — 2^25 − 128, one MiB less cache — leaves the request at exactly 2^25 entries, halves the directory and the segment array, and saves about **257 MiB** of shared memory. Note that `hash_estimate_size()` documents an assumption of default hash parameters while `InitBufTable()` passes `HASH_PARTITION`, so these are the formula's own numbers, not a reading from a built server. [freelist.c#StrategyShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L453-L465) [buf_table.c#InitBufTable](../../../../raw/postgres-12/src/backend/storage/buffer/buf_table.c#L52-L68) [dynahash.c#hash_estimate_size](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L731-L767) [dynahash.c#init_htab](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L670-L704)

On non-Windows builds without `EXEC_BACKEND`, the default main shared-memory implementation is `mmap`; other builds have different defaults. That path obtains one successful anonymous mapping, potentially after a failed huge-page attempt when `huge_pages = try`. Failure is fatal; the hint naming `shared_buffers` specifically accompanies `ENOMEM`. Initialization loops over the descriptors before the new pool can be used. [pg_shmem.h#DEFAULT_SHARED_MEMORY_TYPE](../../../../raw/postgres-12/src/include/storage/pg_shmem.h#L72-L78) [sysv_shmem.c#CreateAnonymousSegment](../../../../raw/postgres-12/src/backend/port/sysv_shmem.c#L528-L590) [sysv_shmem.c#PGSharedMemoryCreate](../../../../raw/postgres-12/src/backend/port/sysv_shmem.c#L624-L657) [buf_init.c#InitBufferPool](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L111-L144)

### Pros

**Useful cache hits avoid a data-file read.** For an ordinary existing-page read, `BufferAlloc()` looks up a tag, takes a shared mapping lock and pins the buffer. A valid hit returns before `smgrread()`. A found but invalid buffer can require I/O coordination, and lock acquisition can wait, so “no syscall” is too strong. On a miss, the storage path reaches `FileRead()` and `pg_pread()`. A larger pool can turn misses into hits when the workload reuses pages that the smaller pool evicted. [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L994-L1057) [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L743-L796) [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L889-L924) [md.c#mdread](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L590-L600) [fd.c#FileRead](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1875-L1885)

**Fewer dirty evictions can reduce work in user backends.** A backend may flush a dirty victim before reusing it. For permanent pages, `FlushBuffer()` calls `XLogFlush()` to ensure WAL is durable through the page's LSN. That call can return immediately when the required WAL is already flushed. Keeping useful pages longer can reduce this work; fitting a working set does not guarantee zero backend writes. [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1065-L1165) [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2671-L2788) [xlog.c#XLogFlush](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2797-L2818)

**Repeated modifications can share a later write.** Several changes to a page while it remains dirty can be included in one later flush. This is an opportunity for write coalescing, not an exactly-once-per-checkpoint guarantee. Backend eviction and background cleaning can write pages between checkpoints. Checkpoint selection marks eligible dirty buffers, then rechecks their checkpoint flags before writing; another writer can clear a flag, and later modifications can dirty the page again. [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1803-L1857) [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1976-L1997) [bufmgr.c#SyncOneBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2354-L2411) [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2774-L2788)

**Frequently reused pages have eviction protection.** On a backend's first private pin, a normal access can increment the shared usage count up to five; a strategy access only raises zero to one. Repeated pins already held by that backend do not increment it again. The replacement sweep decrements a nonzero count before reuse. These rules apply at smaller pool sizes too. [bufmgr.c#PinBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1578-L1638) [buf_internals.h#BM_MAX_USAGE_COUNT](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L69-L77) [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L315-L357)

**A larger request queue can absorb more pending sync requests.** The checkpointer's capacity equals `NBuffers`, but requests can contain duplicates and there is no guarantee it will never fill. A full queue triggers compaction that scans its requests while holding the communication lock exclusively; if forwarding still fails, or the checkpointer is unavailable, the data-file path can synchronize the file in the backend. The headroom is not free: the queue's own drain and compaction allocate in proportion to its length, as the next section describes. [checkpointer.c#CheckpointerShmemInit](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L914-L931) [checkpointer.c#ForwardSyncRequest](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1086-L1160) [checkpointer.c#CompactCheckpointerRequestQueue](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1178-L1272) [md.c#register_dirty_segment](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L893-L912)

### Cons

**Memory competes with other consumers and may duplicate the OS cache.** Data files use buffered reads and writes, so PostgreSQL and the operating system can retain copies of the same page. This does not mean every hot page necessarily consumes memory twice. Leave room for other allocations and the OS cache; the documentation's memory-pressure guidance includes reducing `shared_buffers` or `work_mem`. `shared_buffers` needs a restart; `work_mem` is session/transaction scoped. [md.c#mdopen](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L450) [md.c#mdread](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L590-L600) [md.c#mdwrite](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L660-L670) [fd.c#FileRead](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1875-L1885) [fd.c#FileWrite](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1958-L1968) [runtime.sgml#linux-memory-overcommit](../../../../raw/postgres-12/doc/src/sgml/runtime.sgml#L1448-L1476) [guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2163) [guc.c#work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2230-L2241)

**A buffer checkpoint scans the full pool, then sorts only its dirty candidates.** Each invocation of `BufferSync()` examines `NBuffers` headers, even if it ultimately finds no pages to write. It normally selects dirty permanent buffers; shutdown, end-of-recovery or `CHECKPOINT_FLUSH_ALL` can widen selection. It sorts `num_to_scan`, not all `NBuffers`, and skips the sort when that count is zero. At this pool size the full scan examines 33,554,432 headers by construction; its elapsed time is unmeasured. [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1774-L1871)

Checkpoint write pacing occurs later; it does not spread out that initial scan. Immediate checkpoints and shutdown can bypass delays. More buffers permit a larger dirty set but do not require one. The documentation says larger pools usually need a corresponding `max_wal_size` increase to spread writes over time; treat that as a workload-dependent tuning consideration, with **reload** scope. [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2018-L2035) [bufmgr.c#CheckPointBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2580-L2590) [checkpointer.c#CheckpointWriteDelay](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L648-L715) [config.sgml#shared_buffers](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1510-L1528) [guc.c#max_wal_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2554-L2564)

**Exactly five maintenance paths scan all shared-buffer descriptors, and the tree names the cost itself.** Relation and database invalidation or flush routines search the whole pool. The header comments above two of them read **`XXX currently it sequentially searches the buffer pool, should be changed to more clever ways of searching`**, each followed by a rationale that these paths are not performance-critical and should not slow the hot paths down — a judgement made for pools far smaller than this one. All five use an unlocked tag precheck before locking a candidate, unlike the checkpoint scan, which takes the header spinlock on every buffer. Temporary-relation branches use local buffers. The list is closed: the only other `NBuffers` loops in `bufmgr.c` are two debugging printers compiled out under `#ifdef NOT_USED`. [bufmgr.c#DropRelFileNodeBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2919-L2923) [bufmgr.c#DropRelFileNodeBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2925-L2971) [bufmgr.c#DropRelFileNodesAllBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2982-L3072) [bufmgr.c#DropDatabaseBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3085-L3113) [bufmgr.c#PrintBufferDescs](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3122-L3169) [bufmgr.c#FlushRelationBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3183-L3188) [bufmgr.c#FlushRelationBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3190-L3271) [bufmgr.c#FlushDatabaseBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3288-L3325)

| Caller or operation | Relevant path and qualification | Source |
|---|---|---|
| Relation deletion | Pending transactional deletes are batched through `smgrdounlinkall()` and `DropRelFileNodesAllBuffers()`, so several partitions dropped in one transaction need not cause one scan per partition. The batch is one pass, not a free one: at or below `DROP_RELS_BSEARCH_THRESHOLD` (20) relations the per-buffer test is a linear walk of the relfilenode list, so dropping 20 relations costs up to **671,088,640** `RelFileNodeEquals()` comparisons in that single pass; above 20 it sorts once and binary-searches | [storage.c#smgrDoPendingDeletes](../../../../raw/postgres-12/src/backend/catalog/storage.c#L399-L460) [smgr.c#smgrdounlinkall](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L433-L463) [bufmgr.c:69](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L69) [bufmgr.c#DropRelFileNodesAllBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3017-L3058) |
| Relation truncation, including VACUUM truncation | `RelationTruncate()` reaches `smgrtruncate()`, and each fork truncated is its own `DropRelFileNodeBuffers()` pass: `FreeSpaceMapTruncateRel()` and `visibilitymap_truncate()` call `smgrtruncate()` on their own forks before the main fork, so a heap with both forks present costs **three** full-pool passes | [storage.c#RelationTruncate](../../../../raw/postgres-12/src/backend/catalog/storage.c#L230-L295) [smgr.c#smgrtruncate](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L646-L669) [freespace.c#FreeSpaceMapTruncateRel](../../../../raw/postgres-12/src/backend/storage/freespace/freespace.c#L321-L322) [visibilitymap.c#visibilitymap_truncate](../../../../raw/postgres-12/src/backend/access/heap/visibilitymap.c#L534-L535) [vacuumlazy.c#lazy_truncate_heap](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1950-L1974) |
| Truncation WAL replay | `smgr_redo()` reaches truncation paths | [storage.c#smgr_redo](../../../../raw/postgres-12/src/backend/catalog/storage.c#L575-L629) |
| Tablespace file copy | Heap copy uses the table AM's `FlushRelationBuffers()` call; index copy has a separate call | [heapam_handler.c#heapam_relation_copy_data](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L636-L660) [tablecmds.c#index_copy_data](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L12764-L12791) |
| `heap_sync()` | Flushes heap and possible TOAST buffers for permanent relations | [heapam.c#heap_sync](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L8923-L8960) |
| `CREATE DATABASE` on the primary | Requests an immediate forced checkpoint with `CHECKPOINT_FLUSH_ALL` before copying | [dbcommands.c#createdb](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L574-L585) |
| `CREATE DATABASE` replay | Calls `FlushDatabaseBuffers()` on the source database | [dbcommands.c#dbase_redo](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L2130-L2141) |
| `DROP DATABASE` | Invalidates database buffers, including during replay | [dbcommands.c#dropdb](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L937-L942) [dbcommands.c#dbase_redo](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L2143-L2173) |
| `ALTER DATABASE ... SET TABLESPACE` | Forces a checkpoint, then drops cached database buffers before moving files; this is the caller at line 1228 | [dbcommands.c#movedb](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L1200-L1228) |

**Draining or compacting the sync-request queue allocates in proportion to `NBuffers`.** Both operations run with `CheckpointerCommLock` held exclusively. `AbsorbSyncRequests()` copies the queue with an ordinary `palloc()` before clearing it, so a full queue at this pool size is a **768 MiB** allocation in the checkpointer — 33,554,432 requests at the 24 bytes assumed above. `CompactCheckpointerRequestQueue()` is worse: it takes `palloc0(sizeof(bool) * num_requests)`, **32 MiB** here, and builds a local hash table sized by the queue, which under the same assumptions is a 1 MiB directory plus 256 MiB of bucket segments up front and roughly 1.5 GiB of 48-byte elements. Neither cost appears at a small pool, because neither queue can be long. These are conditional arithmetic on the struct definitions and the allocation formulas, and they assume a queue that has actually filled; source does not establish how often it does. [checkpointer.c#AbsorbSyncRequests](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1285-L1333) [checkpointer.c#CompactCheckpointerRequestQueue](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1196-L1208) [checkpointer.c#CheckpointerShmemInit](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L914-L931) [dynahash.c#init_htab](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L670-L704) [dynahash.c#choose_nelem_alloc](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L603-L628)

**Replacement work is workload-dependent.** `StrategyGetBuffer()` tries a strategy ring before the freelist and clock sweep. The sweep uses a shared atomic clock hand, tests pins and usage counts, and can examine many buffers. The header's “five plus one cycles” discussion describes aging usage counts in the simplified case; it is not a wall-clock bound or a concurrency-safe upper bound on one allocation. Other backends can change usage counts, and `BufferAlloc()` can reject a candidate and retry. The pinned-buffer error occurs after `NBuffers` pinned observations without a usage-count decrement resetting the counter; it is not a simultaneous snapshot of all pins. [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L200-L217) [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L268-L357) [freelist.c#ClockSweepTick](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L112-L168) [buf_internals.h#BM_MAX_USAGE_COUNT](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L69-L77) [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1065-L1165)

**Background cleaning has both fixed and pool-dependent controls.** The default write cap is 100 pages per round and the normal delay is 200 ms; the cap does not grow automatically with `NBuffers`. The scan estimate does depend on allocation history and buffer density, and its minimum term is `NBuffers / (120000 / bgwriter_delay)`. That term is 55,924 buffers at this size and default delay after the floating-point calculation is cast to an integer. It is not a promise to write that many pages or finish a pool pass in 120 seconds: the writer skips pinned/recently used buffers, can hit its write cap, and can hibernate. Source does not establish that the defaults are inadequate for every 256 GiB pool. [guc.c#bgwriter_lru_maxpages](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2738-L2746) [guc.c#bgwriter_delay](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2727-L2736) [bufmgr.c#BgBufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2040-L2336) [bufmgr.c#SyncOneBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2354-L2411) [bgwriter.c#BackgroundWriterMain](../../../../raw/postgres-12/src/backend/postmaster/bgwriter.c#L327-L373)

**Startup and cache warming have distinct costs.** A newly initialized pool has invalid descriptors; its initialization loop grows with `NBuffers`. This is not a mandatory read of 256 GiB of data at startup. Subsequent requests fill the pages they need, and a miss can be served from the OS cache. `pg_prewarm` can explicitly load pages; autoprewarm saves identifiers used to reload them, not page contents. This does not establish that promotion of an already-running standby starts with an empty pool. [buf_init.c#InitBufferPool](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L111-L144) [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L743-L796) [md.c#mdread](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L590-L600) [pg_prewarm.c#pg_prewarm](../../../../raw/postgres-12/contrib/pg_prewarm/pg_prewarm.c#L185-L199) [autoprewarm.c#autoprewarm](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L1-L24) [autoprewarm.c#apw_dump_now](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L644-L650)

**Contrib inspection and warming add allocation limits.** `pg_buffercache` allocates `NBuffers * sizeof(BufferCachePagesRec)` with `MemoryContextAllocHuge()` and visits every buffer before returning its rows. Under a 32-byte record layout, the temporary array alone is 1 GiB at this pool size; a SQL `LIMIT` does not avoid that initial collection. It obtains per-buffer consistency, not a single consistent snapshot across the whole pool. [pg_buffercache_pages.c#BufferCachePagesRec](../../../../raw/postgres-12/contrib/pg_buffercache/pg_buffercache_pages.c#L26-L44) [pg_buffercache_pages.c#pg_buffercache_pages](../../../../raw/postgres-12/contrib/pg_buffercache/pg_buffercache_pages.c#L126-L176)

Autoprewarm instead uses ordinary `palloc(NBuffers * sizeof(BlockInfoRecord))` before filtering valid buffers. Under the 20-byte record layout assumed above, that is **640 MiB** at 256 GiB — and the cost recurs. `pg_prewarm.autoprewarm_interval` defaults to 300 seconds, so with the module preloaded the worker repeats that allocation and a 33,554,432-header lock walk **every five minutes** until the interval is set to 0 or the worker stops. That interval is `PGC_SIGHUP`, so changing it needs a **reload**; `pg_prewarm.autoprewarm`, which decides whether the worker starts at all, is `PGC_POSTMASTER` and needs a **restart**. Past a certain pool size the allocation stops succeeding altogether; see the next section. These are conditional source calculations, not reproduced runtime results. [autoprewarm.c#BlockInfoRecord](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L58-L65) [autoprewarm.c#apw_dump_now](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L559-L620) [autoprewarm.c#_PG_init](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L114-L141) [autoprewarm.c#autoprewarm_main](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L207-L246) [memutils.h#MaxAllocSize](../../../../raw/postgres-12/src/include/utils/memutils.h#L24-L46) [mcxt.c#palloc](../../../../raw/postgres-12/src/backend/utils/mmgr/mcxt.c#L924-L938)

**A bigger pool does not add mapping-lock partitions or solve every contention problem.** There are 128 mapping partitions. Replacement can lock two different partitions, or just one when old and new tags share a partition. The clock hand uses an atomic operation; the strategy spinlock is used for such tasks as wrap accounting and freelist access, not for every clock tick. A larger pool could reduce replacement-related lock traffic by avoiding misses, so unchanged partition count alone does not prove unchanged contention. [lwlock.h#NUM_BUFFER_PARTITIONS](../../../../raw/postgres-12/src/include/storage/lwlock.h#L107-L126) [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1169-L1212) [freelist.c#ClockSweepTick](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L112-L168) [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L268-L313)

**Huge pages and memory placement need platform-specific validation.** The anonymous allocation path can request explicit huge pages, with fallback controlled by `huge_pages`; changing that GUC requires restart. The pinned documentation describes supported platforms and distinguishes explicit huge pages from transparent huge pages. The cited allocation path does not set a NUMA node policy; topology, launch policy and actual placement are outside this source-only assessment. A 1 TB capacity alone does not establish a multi-socket topology. [sysv_shmem.c#CreateAnonymousSegment](../../../../raw/postgres-12/src/backend/port/sysv_shmem.c#L528-L590) [config.sgml#huge_pages](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1533-L1590) [guc.c#huge_pages](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4470-L4478)

### Hard limits above 256 GB

The question asks about 256 GB **or more**, so it is worth naming where "more" stops being a tuning choice. Three walls are visible in source. All three are arithmetic on the same ABI assumptions stated above, with 8 KiB blocks.

| Wall | Where it is | Reached at |
|---|---|---|
| The setting itself | `shared_buffers` accepts at most `INT_MAX / 2` blocks, because the code "sometimes multiplies the number of shared buffers by two without checking for overflow" | 1,073,741,823 blocks, which is **8 TiB minus one block** |
| Autoprewarm's dump | `palloc(20 * NBuffers)` must satisfy `MaxAllocSize`, 1 GiB minus one byte | from 53,687,092 blocks, about **409.6 GiB** — the dump then errors even when almost no buffer holds a useful page |
| Draining a full sync-request queue | `palloc(24 * num_requests)`, where `max_requests` is `NBuffers` | from 44,739,243 blocks, about **341.3 GiB**, and only when the queue has actually filled |

The first is a refusal at startup and is unambiguous. The other two are `elog(ERROR)` from `palloc()` in one process — the autoprewarm worker and the checkpointer — not a refusal to start and not data loss, and the second of them needs a full queue before it can fire. Neither has a test in this checkout. [guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2163) [memutils.h#MaxAllocSize](../../../../raw/postgres-12/src/include/utils/memutils.h#L24-L46) [mcxt.c#palloc](../../../../raw/postgres-12/src/backend/utils/mmgr/mcxt.c#L924-L938) [autoprewarm.c#BlockInfoRecord](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L58-L65) [autoprewarm.c#apw_dump_now](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L559-L620) [checkpointer.c#AbsorbSyncRequests](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1285-L1333) [checkpointer.c#CheckpointerShmemInit](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L914-L931)

### Thresholds that move when NBuffers is huge

For eligible non-local heap scans, `initscan()` enables the bulk-read ring only when table size is **strictly greater than `NBuffers / 4`**, and only when the caller permits the strategy. Synchronized scanning additionally requires its flag and GUC. At 256 GiB, the boundary is 64 GiB: a table exactly at the boundary does not qualify. Below it, normal replacement can retain useful pages or allow one-pass scans to displace other pages; residency is not guaranteed. [heapam.c#initscan](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L300)

Synchronized scanning coordinates starting positions; disabling that coordination does not prevent shared-buffer hits. Parallel scans also have their own shared scan state, so the synchronized-scan size test should not be described as disabling parallel worker coordination. [syncscan.c#synchronized-scans](../../../../raw/postgres-12/src/backend/access/heap/syncscan.c#L6-L32) [tableam.c#table_block_parallelscan_initialize](../../../../raw/postgres-12/src/backend/access/table/tableam.c#L370-L385) [tableam.c#table_block_parallelscan_startblock_init](../../../../raw/postgres-12/src/backend/access/table/tableam.c#L403-L430) [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L994-L1057)

| Mechanism | Formula or ceiling | Meaning at this size | Source |
|---|---|---|---|
| Bulk-read and synchronized-scan eligibility | table blocks `> NBuffers / 4`, with caller flags and relevant GUC | boundary 64 GiB, strictly exceeded | [heapam.c#initscan](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L300) |
| Strategy-ring clamp | `Min(NBuffers / 8, requested_ring_size)` | 256 KiB read/vacuum rings and 16 MiB write ring already reach full size at pools of 2 MiB and 128 MiB respectively; this is not a special 256 GiB benefit | [freelist.c#GetAccessStrategy](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L541-L588) |
| Hash-index build sort threshold for non-temp relations | `Min((maintenance_work_mem * 1024L) / BLCKSZ, NBuffers)` | the smaller term controls; sorting is selected when the initial bucket count reaches the threshold; temp relations use `NLocBuffer` | [hash.c#hashbuild](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L138-L158) |
| Transaction-status cache | `Min(128, Max(4, NBuffers / 512))` | capped at 128 buffers from a 512 MiB pool with 8 KiB blocks | [clog.c#CLOGShmemBuffers](../../../../raw/postgres-12/src/backend/access/transam/clog.c#L675-L679) |
| Commit-timestamp cache | `Min(16, Max(4, NBuffers / 1024))` | capped at 16 buffers from a 128 MiB pool with 8 KiB blocks | [commit_ts.c#CommitTsShmemBuffers](../../../../raw/postgres-12/src/backend/access/transam/commit_ts.c#L469-L473) |
| Automatic WAL buffers | starts at `NBuffers / 32`, capped by one WAL segment expressed in WAL blocks, with a floor of 8 | `NBuffers / 32` is 1,048,576 WAL blocks here, so the cap decides: with the default 16 MB segment and 8 KiB `XLOG_BLCKSZ` that is **2,048 blocks, or 16 MiB** — the same value any pool of 512 MiB or more receives | [xlog.c#XLOGChooseNumBuffers](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L4850-L4873) [pg_config_manual.h#DEFAULT_XLOG_SEG_SIZE](../../../../raw/postgres-12/src/include/pg_config_manual.h#L16-L20) [configure.in#wal_blocksize](../../../../raw/postgres-12/configure.in#L312-L330) |

### What a big pool does not buy

- **Shared storage for temporary tables:** their pages use session-local buffers and `temp_buffers`. [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L732-L742) [config.sgml#temp_buffers](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1592-L1612)
- **A proportionately larger VACUUM ring:** manual vacuum and autovacuum obtain `BAS_VACUUM`, whose maximum size is fixed. VACUUM can still benefit from pages already in shared buffers: cache lookup precedes replacement-strategy selection. [vacuum.c#vacuum](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L292-L299) [autovacuum.c#do_autovacuum](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2288) [freelist.c#GetAccessStrategy](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L541-L588) [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L994-L1057)
- **An automatically larger planner cache assumption:** `index_pages_fetched()` uses `effective_cache_size`; increasing `shared_buffers` does not itself change that GUC. This does not guarantee identical plans if other planner inputs change. `effective_cache_size` is session/transaction scoped. [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L825-L877) [guc.c#effective_cache_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3117)

### Structures, build inputs and extension boundaries

`BufferTag` identifies a relation, fork and block. A `BufferDesc` combines that tag with shared state carrying reference count, usage count and flags, plus a content lock and freelist link. Header-state protection, content protection, mapping lookup and I/O coordination are distinct boundaries. A strategy ring holds references to shared buffers; it is not a separate page cache. `FileTag` identifies the files handled by the checkpointer's request queue. [buf_internals.h#BufferTag](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L91-L96) [buf_internals.h#buffer-state](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L30-L77) [buf_internals.h#BufferDesc](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L135-L190) [freelist.c#BufferAccessStrategyData](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L67-L97) [sync.h#FileTag](../../../../raw/postgres-12/src/include/storage/sync.h#L45-L51) [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L994-L1057)

`configure` generates `pg_config.h`, including the configured block size and pointer-size macro used by padding definitions; `c.h` includes that header. The buffer-manager objects build together, while named lightweight-lock definitions are generated from `lwlocknames.txt`. Therefore the raw struct declarations do not establish a universal compiled layout. [configure.in#blocksize](../../../../raw/postgres-12/configure.in#L247-L277) [configure.in#AC_CONFIG_HEADERS](../../../../raw/postgres-12/configure.in#L2473-L2477) [pg_config.h.in#BLCKSZ](../../../../raw/postgres-12/src/include/pg_config.h.in#L39-L43) [pg_config.h.in#SIZEOF_VOID_P](../../../../raw/postgres-12/src/include/pg_config.h.in#L879) [c.h#configuration-headers](../../../../raw/postgres-12/src/include/c.h#L54-L55) [Makefile#OBJS](../../../../raw/postgres-12/src/backend/storage/buffer/Makefile#L15) [Makefile#lwlocknames](../../../../raw/postgres-12/src/backend/storage/lmgr/Makefile#L29-L33)

The extension surface is not limited to contrib modules that read the pool. `smgrdounlinkfork()` is declared in `smgr.h` and calls `DropRelFileNodeBuffers()`, so it is a full-pool pass an extension can trigger; no in-core caller invokes it in this checkout, only the batched `smgrdounlinkall()` path does. [smgr.c#smgrdounlinkfork](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L500-L523) [smgr.h:93](../../../../raw/postgres-12/src/include/storage/smgr.h#L93) [bufmgr.c#DropRelFileNodeBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2925-L2971)

The SQL below uses installed system views and catalog-declared functions. `pg_proc.dat` is a catalog-generation input and `system_views.sql` is installed by the catalog build. Generic `SET` grammar reaches `ExecSetVariableStmt()` through utility dispatch. The contrib modules inspected above directly use buffer internals, so their allocation costs must be assessed separately from the core pool. [Makefile#catalog-generation](../../../../raw/postgres-12/src/backend/catalog/Makefile#L60-L89) [Makefile#install-data](../../../../raw/postgres-12/src/backend/catalog/Makefile#L106-L109) [gram.y#VariableSetStmt](../../../../raw/postgres-12/src/backend/parser/gram.y#L1402-L1421) [utility.c#VariableSetStmt](../../../../raw/postgres-12/src/backend/tcop/utility.c#L684-L685) [autoprewarm.c#apw_dump_now](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L559-L620) [pg_buffercache_pages.c#pg_buffercache_pages](../../../../raw/postgres-12/contrib/pg_buffercache/pg_buffercache_pages.c#L126-L176)

### Settings that move with it, and their apply scope

Apply scope follows the GUC context: `postmaster` needs a restart, `sighup` needs a reload, `user`/`PGC_USERSET` applies per session or transaction; `superuser`/`PGC_SUSET` has that scope but requires superuser privilege. The source contexts are cited per row; `SET LOCAL` is handled by `ExecSetVariableStmt()` ([guc.c#ExecSetVariableStmt](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L8100-L8124)).

| Setting | Context | Apply scope | Why it matters here | Source |
|---|---|---|---|---|
| `shared_buffers` | `PGC_POSTMASTER` | restart | the setting itself | [guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2163) |
| `huge_pages` | `PGC_POSTMASTER` | restart | page-table overhead for a 256 GB mapping | [guc.c#huge_pages](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4470-L4478) |
| `shared_memory_type` | `PGC_POSTMASTER` | restart | selects the main shared-memory implementation supported by the build | [guc.c#shared_memory_type](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4429-L4437) |
| `wal_buffers` | `PGC_POSTMASTER` | restart | automatic sizing is capped; the cap alone is not evidence that more is needed | [guc.c#wal_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2602-L2611) |
| `max_wal_size` | `PGC_SIGHUP` | reload | the documentation ties it to a larger `shared_buffers` | [guc.c#max_wal_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2554-L2564) |
| `checkpoint_timeout` | `PGC_SIGHUP` | reload | maximum interval between automatic checkpoints | [guc.c#checkpoint_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2566-L2575) |
| `checkpoint_completion_target` | `PGC_SIGHUP` | reload | spreads the write phase | [guc.c#checkpoint_completion_target](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3413-L3421) |
| `checkpoint_flush_after` | `PGC_SIGHUP` | reload | batches writeback requests during the checkpoint | [guc.c#checkpoint_flush_after](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2591-L2600) |
| `bgwriter_lru_maxpages` | `PGC_SIGHUP` | reload | caps pages written per round, default 100 | [guc.c#bgwriter_lru_maxpages](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2738-L2746) |
| `bgwriter_lru_multiplier` | `PGC_SIGHUP` | reload | scales the lookahead estimate | [guc.c#bgwriter_lru_multiplier](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3351-L3359) |
| `bgwriter_delay` | `PGC_SIGHUP` | reload | sets the normal delay and affects the scan floor; hibernation can extend the delay | [guc.c#bgwriter_delay](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2727-L2736) |
| `bgwriter_flush_after` | `PGC_SIGHUP` | reload | writeback batching for background writes | [guc.c#bgwriter_flush_after](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2748-L2757) |
| `log_checkpoints` | `PGC_SIGHUP` | reload | records individual checkpoint timings | [guc.c#log_checkpoints](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1217-L1225) |
| `backend_flush_after` | `PGC_USERSET` | session or transaction | writeback batching for backend-issued writes | [guc.c#backend_flush_after](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2777-L2786) |
| `effective_cache_size` | `PGC_USERSET` | session or transaction | the planner's cache assumption, independent of `NBuffers` | [guc.c#effective_cache_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3117) |
| `synchronize_seqscans` | `PGC_USERSET` | session or transaction | scan eligibility also requires table blocks strictly above `NBuffers / 4` | [guc.c#synchronize_seqscans](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1732-L1740) |
| `temp_buffers` | `PGC_USERSET` | session, before first temp-table use | temp tables never use the shared pool | [guc.c#temp_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2165-L2174) |
| `work_mem` | `PGC_USERSET` | session or transaction | competes for the RAM the pool did not take | [guc.c#work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2230-L2241) |
| `maintenance_work_mem` | `PGC_USERSET` | session or transaction | competes for memory and supplies one term of the hash-build sort threshold | [guc.c#maintenance_work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2243-L2252) |
| `track_io_timing` | `PGC_SUSET` | superuser session or transaction | enables I/O timing in the processes doing the work; default off | [guc.c#track_io_timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1401-L1409) |
| `pg_prewarm.autoprewarm` | `PGC_POSTMASTER` | restart | decides whether the dump/reload worker starts at all; default on, but only defined when the module is preloaded | [autoprewarm.c#_PG_init](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L114-L141) |
| `pg_prewarm.autoprewarm_interval` | `PGC_SIGHUP` | reload | how often the worker repeats its `NBuffers`-sized allocation and full-pool walk; default 300 s, and 0 disables time-based dumping | [autoprewarm.c#_PG_init](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L114-L141) [autoprewarm.c#autoprewarm_main](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L207-L246) |

### What to look at before and after the change

Compare counter deltas over equivalent workloads, not lifetime totals or hit ratio alone. `pg_stat_bgwriter` exposes writer and checkpoint counters; `pg_stat_database` exposes block counts and timing. Record `stats_reset`, allow for collection lag, and avoid a long-lived transaction that reuses a statistics snapshot. Individual checkpoint log lines add write/sync/total durations. Read their buffer percentage with care: it is `ckpt_bufs_written * 100 / NBuffers`, so at 33,554,432 buffers a checkpoint that wrote 100,000 pages prints about 0.3 %, and the field stops being a useful glance at exactly this pool size. [system_views.sql#pg_stat_bgwriter](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L935-L947) [system_views.sql#pg_stat_database](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L856-L882) [monitoring.sgml#statistics-collection](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L229-L260) [xlog.c#LogCheckpointEnd](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L8435-L8442) [xlog.c:8442](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L8442)

`buffers_backend` is broader than dirty-victim writes: relation extension also registers dirty segments. **`buffers_backend_fsync` counts backend data-file sync fallback, not WAL flushes.** `buffers_alloc` is narrower than it looks: `StrategyGetBuffer()` returns early when a strategy ring supplies the buffer, and increments the allocation counter only on the freelist-and-sweep path, stating that buffers recycled by a strategy object are intentionally not counted. Ring-served reads are therefore invisible in that column, which matters here because the `NBuffers / 4` threshold decides how much traffic uses a ring at all. No one of these counters isolates the benefit of a larger cache. [md.c#mdextend](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L373-L422) [md.c#register_dirty_segment](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L893-L912) [checkpointer.c#ForwardSyncRequest](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1107-L1160) [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L200-L217) [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L245-L250) [heapam.c#initscan](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L300)

The database block counts include counted accesses to local temporary-table buffers as well as shared buffers. `blks_read` does not establish physical device I/O: a data-file read may be served by the OS cache. I/O timing is off by default and must be enabled in the workload processes to make the timing columns useful; enabling it only in a monitoring session does not instrument other sessions. The reported times are milliseconds. [bufmgr.c#ReadBufferExtended](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L640-L669) [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L732-L796) [pgstat.h#pgstat_count_buffer_read](../../../../raw/postgres-12/src/include/pgstat.h#L1384-L1397) [pgstat.c#pgstat_initstats](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L1751-L1784) [pgstat.c#pgstat_recv_tabstat](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6001-L6005) [fd.c#FileRead](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1875-L1885) [guc.c#track_io_timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1401-L1409) [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2764-L2769) [pgstatfuncs.c#pg_stat_get_db_blk_read_time](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L1569-L1597)

The following SQL was checked against the pinned source, not executed in this review. Both timeout settings below are session-scoped (`PGC_USERSET`); `SET LOCAL` would restrict them to a transaction. [guc.c#statement_timeout-and-lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2397) [guc.c#ExecSetVariableStmt](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L8100-L8124)

```sql
SET /* wiki_v12_monitor_statement_timeout */ statement_timeout = '30s';
SET /* wiki_v12_monitor_lock_timeout */ lock_timeout = '5s';
```

Writer and checkpoint counters, including the reset boundary: [system_views.sql#pg_stat_bgwriter](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L935-L947)

```sql
SELECT /* wiki_v12_shared_buffers_writers */
       buffers_checkpoint,
       buffers_clean,
       maxwritten_clean,
       buffers_backend,
       buffers_backend_fsync,
       buffers_alloc,
       checkpoints_timed,
       checkpoints_req,
       checkpoint_write_time,
       checkpoint_sync_time,
       stats_reset
FROM pg_stat_bgwriter;
```

Database buffer hit percentage, including local-buffer activity and possible OS-cache hits on reads. The numeric cast and two-argument `round` are catalog-declared: [pg_proc.dat#numeric](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L4292-L4294) [pg_proc.dat#round](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L4130-L4132) [system_views.sql#pg_stat_database](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L856-L882) [bufmgr.c#ReadBufferExtended](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L640-L669) [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L732-L796)

```sql
SELECT /* wiki_v12_shared_buffer_hit_ratio */
       datname,
       blks_hit,
       blks_read,
       round(100.0 * blks_hit / nullif(blks_hit::numeric + blks_read, 0), 2) AS hit_pct,
       blk_read_time,
       blk_write_time,
       stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY blks_hit::numeric + blks_read DESC;
```

Configured pool size and arithmetic thresholds; a heap scan must **exceed** the reported bulk-read boundary and satisfy the eligibility flags: [heapam.c#initscan](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L300) [freelist.c#GetAccessStrategy](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L541-L588) [clog.c#CLOGShmemBuffers](../../../../raw/postgres-12/src/backend/access/transam/clog.c#L675-L679) [commit_ts.c#CommitTsShmemBuffers](../../../../raw/postgres-12/src/backend/access/transam/commit_ts.c#L469-L473)

```sql
SELECT /* wiki_v12_nbuffers_derived_thresholds */
       sb.setting::bigint AS shared_buffer_blocks,
       pg_size_pretty(sb.setting::bigint * bs.setting::bigint) AS shared_buffers_total,
       pg_size_pretty((sb.setting::bigint / 4) * bs.setting::bigint) AS bulkread_strategy_threshold,
       pg_size_pretty((sb.setting::bigint / 8) * bs.setting::bigint) AS ring_clamp,
       least(128, greatest(4, sb.setting::bigint / 512)) AS clog_slru_buffers,
       least(16, greatest(4, sb.setting::bigint / 1024)) AS commit_ts_slru_buffers
FROM pg_settings sb, pg_settings bs
WHERE sb.name = 'shared_buffers'
  AND bs.name = 'block_size';
```

`pg_settings` wraps `pg_show_all_settings()`. `shared_buffers` is reported in blocks, `block_size` reports `BLCKSZ` in bytes and has internal, non-settable context, and `pg_size_pretty(bigint)` is catalog-declared. [system_views.sql#pg_settings](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L512-L513) [pg_proc.dat#pg_show_all_settings](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L5770-L5775) [guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2163) [guc.c#block_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2879-L2888) [pg_proc.dat#pg_size_pretty](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L6897-L6899)

For actual mapping size, the pinned documentation gives an OS-level procedure using the postmaster PID. Use `pg_buffercache` with awareness of its up-front allocation and scan cost. [runtime.sgml#linux-huge-pages](../../../../raw/postgres-12/doc/src/sgml/runtime.sgml#L1542-L1566) [pg_buffercache_pages.c#pg_buffercache_pages](../../../../raw/postgres-12/contrib/pg_buffercache/pg_buffercache_pages.c#L126-L176)

### Decision guide

Treat 256 GiB as a candidate to compare with a smaller pool. The strongest reason to keep it is a measured reduction in repeated reads or foreground dirty-victim work that improves the workload's throughput or latency. Source identifies those opportunities, but no such comparison was run for this page. [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L743-L796) [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1065-L1165)

Include memory headroom, checkpoint duration, maintenance-operation latency and restart preparation in that comparison. Repeated independent relation invalidations and the initial checkpoint scan warrant particular attention because their searches cover the pool; transactional delete batching can reduce the number of searches. [runtime.sgml#linux-memory-overcommit](../../../../raw/postgres-12/doc/src/sgml/runtime.sgml#L1448-L1476) [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1828-L1871) [bufmgr.c#DropRelFileNodesAllBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2982-L3072) [storage.c#smgrDoPendingDeletes](../../../../raw/postgres-12/src/backend/catalog/storage.c#L399-L460) [buf_init.c#InitBufferPool](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L111-L144)

A staged comparison is a recommendation, not a source-proven optimum. Schedule a **restart** for each `shared_buffers` change. Enable `log_checkpoints` with a **reload** if individual checkpoint records are needed, remembering that its percentage field is `NBuffers`-relative. Change other controls only when the observed workload supports it; neither explicit huge pages nor departing from every background-writer default is a prerequisite established by this source review. If 256 GiB survives the comparison, consider writing it as `shared_buffers = 33554304` rather than `256GB`: that gives up one MiB of cache and takes the mapping hash off the wrong side of its power-of-two boundary. [freelist.c#StrategyShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L453-L465) [dynahash.c#hash_estimate_size](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L731-L767) [xlog.c:8442](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L8442) [guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2163) [guc.c#log_checkpoints](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1217-L1225) [xlog.c#LogCheckpointEnd](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L8435-L8442) [sysv_shmem.c#CreateAnonymousSegment](../../../../raw/postgres-12/src/backend/port/sysv_shmem.c#L528-L590) [bufmgr.c#BgBufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2040-L2336)

## Context Reviewed

- Target: PostgreSQL 12.2, pin `45b88269a353ad93744772791feb6d01bc7e1e42`; all behavioral evidence comes from that checkout.
- Concepts: shared-buffer mapping, pinning, replacement, strategy rings, dirty-page writes, checkpoints, file sync requests and cache statistics. No PostgreSQL 12 common-concept pages are available for these concepts; none were created or modified.
- Core normal/error paths: buffer lookup and invalid-buffer coordination; dirty-victim retries; usage-count aging and pinned-buffer error; checkpoint candidate selection, concurrent writes and pacing; queue-full compaction, queue drain and backend file-sync fallback.
- Caller boundaries: storage-manager unlink/truncate including the per-fork FSM and visibility-map truncations, batched pending deletes and their below-threshold linear rnode walk, VACUUM truncation, heap/index tablespace copies, database creation/drop/move and WAL replay, plus the extension-only `smgrdounlinkfork()` route.
- Struct/build boundaries: buffer descriptors and tags, strategy rings, request records, the dynamic-hash sizing formulas behind the buffer mapping table, generated configuration/lock headers, catalog generation and generic SET dispatch.
- Contrib: `pg_buffercache`, `pg_prewarm`, autoprewarm including its two custom GUCs and dump period, and ordinary versus huge memory allocation.
- Monitoring: catalog/view definitions, counter producers and what each one excludes, collector aggregation, timing GUC, the `NBuffers`-relative checkpoint log percentage, and statistics snapshot documentation.
- Full-pool-loop census: every `NBuffers` loop in `bufmgr.c` was enumerated. Five are compiled maintenance searches plus the checkpoint scan; the remaining two are `PrintBufferDescs()` and `PrintPinnedBufs()` under `#ifdef NOT_USED`, so the list of full-pool searchers on the page is closed rather than illustrative. [bufmgr.c#PrintBufferDescs](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3122-L3169)
- Tests: inspected `src/test` and `contrib` references to `shared_buffers`; no large-pool case was found in that search, and neither `MaxAllocSize` wall above 256 GiB is exercised. The cited recovery test uses 128 kB; the TAP harness uses 1 MB in its `allows_streaming` branch. [016_min_consistency.pl#shared_buffers](../../../../raw/postgres-12/src/test/recovery/t/016_min_consistency.pl#L46-L54) [PostgresNode.pm#allows_streaming](../../../../raw/postgres-12/src/test/perl/PostgresNode.pm#L462-L479)
- Review scope: source-only. No server, benchmark or measurement script was run; numeric examples are explicitly conditional source arithmetic.
- Re-verification, 2026-09-16: every citation range on the page was re-read against the pin and every claim re-checked. All 163 distinct ranges resolve, are in bounds, and match their labels; no claim was found incorrect. The additions in this revision are the omissions that pass found.

## Evidence Map

| Claim group | Primary evidence |
|---|---|
| Configuration, startup failure and extra allocation | [guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2163) [buf_init.c#BufferShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L160-L193) [sysv_shmem.c#CreateAnonymousSegment](../../../../raw/postgres-12/src/backend/port/sysv_shmem.c#L528-L590) |
| Mapping-hash size and its power-of-two boundary | [freelist.c#StrategyShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L453-L465) [dynahash.c#hash_estimate_size](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L731-L767) [dynahash.c#my_log2](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L1716-L1730) [dynahash.c#choose_nelem_alloc](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L603-L628) [buf_table.c#InitBufTable](../../../../raw/postgres-12/src/backend/storage/buffer/buf_table.c#L52-L68) |
| Sync-queue drain and compaction allocations | [checkpointer.c#AbsorbSyncRequests](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1285-L1333) [checkpointer.c#CompactCheckpointerRequestQueue](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1196-L1208) [dynahash.c#init_htab](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L670-L704) |
| Hard limits above 256 GB | [guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2163) [memutils.h#MaxAllocSize](../../../../raw/postgres-12/src/include/utils/memutils.h#L24-L46) [mcxt.c#palloc](../../../../raw/postgres-12/src/backend/utils/mmgr/mcxt.c#L924-L938) [autoprewarm.c#apw_dump_now](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L559-L620) |
| Per-fork truncation passes and drop batching | [freespace.c#FreeSpaceMapTruncateRel](../../../../raw/postgres-12/src/backend/storage/freespace/freespace.c#L321-L322) [visibilitymap.c#visibilitymap_truncate](../../../../raw/postgres-12/src/backend/access/heap/visibilitymap.c#L534-L535) [bufmgr.c:69](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L69) [bufmgr.c#DropRelFileNodesAllBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3017-L3058) |
| Autoprewarm dump period and its GUC scopes | [autoprewarm.c#_PG_init](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L114-L141) [autoprewarm.c#autoprewarm_main](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L207-L246) |
| Cache hits, eviction and durability boundary | [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L994-L1165) [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2671-L2788) [xlog.c#XLogFlush](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2797-L2818) |
| Full checkpoint scan versus candidate-only sort | [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1774-L1871) [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1976-L2035) |
| DDL scans and transactional batching | [bufmgr.c#DropRelFileNodesAllBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2982-L3072) [storage.c#smgrDoPendingDeletes](../../../../raw/postgres-12/src/backend/catalog/storage.c#L399-L460) [dbcommands.c#createdb](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L574-L585) [dbcommands.c#movedb](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L1200-L1228) |
| Replacement and background-writer limits | [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L200-L357) [bufmgr.c#BgBufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2040-L2336) |
| Ring and scan eligibility thresholds | [freelist.c#GetAccessStrategy](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L541-L588) [heapam.c#initscan](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L300) |
| Contrib allocation limits | [pg_buffercache_pages.c#pg_buffercache_pages](../../../../raw/postgres-12/contrib/pg_buffercache/pg_buffercache_pages.c#L126-L176) [autoprewarm.c#apw_dump_now](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L559-L620) [memutils.h#MaxAllocSize](../../../../raw/postgres-12/src/include/utils/memutils.h#L24-L46) |
| Backend sync counter semantics | [checkpointer.c#ForwardSyncRequest](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1107-L1160) [md.c#register_dirty_segment](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L893-L912) |
| Database counters and timing | [bufmgr.c#ReadBufferExtended](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L640-L669) [pgstat.c#pgstat_recv_tabstat](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6001-L6005) [pgstatfuncs.c#pg_stat_get_db_blk_read_time](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L1569-L1597) |
| Generated build/catalog inputs | [configure.in#AC_CONFIG_HEADERS](../../../../raw/postgres-12/configure.in#L2473-L2477) [Makefile#lwlocknames](../../../../raw/postgres-12/src/backend/storage/lmgr/Makefile#L29-L33) [Makefile#catalog-generation](../../../../raw/postgres-12/src/backend/catalog/Makefile#L60-L89) |

## Open Questions

- No workload or host measurements establish the best pool size, scan latency, write savings, memory headroom, huge-page availability or NUMA placement. The 25% recommendation is not a 1 TB benchmark.
- The byte totals depend on the stated ABI and build assumptions. The mapping-hash figure is now derived rather than left open, but `hash_estimate_size()` documents an assumption of default hash parameters while `InitBufTable()` passes `HASH_PARTITION`, so the real shared allocation can differ from the estimate that sized it. The complete main-segment size is still not calculated. No contrib array example and neither `MaxAllocSize` wall was reproduced on a built server. [dynahash.c#hash_estimate_size](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L731-L767) [buf_table.c#InitBufTable](../../../../raw/postgres-12/src/backend/storage/buffer/buf_table.c#L52-L68)
- The sync-queue costs assume a queue that has actually filled. Source supplies the capacity, the compaction trigger and the allocation formulas, but nothing here establishes how often a 33,554,432-entry queue fills, or whether a checkpointer ever reaches the 768 MiB copy in practice. The comment above the array size says the choice of `NBuffers` is arbitrary and "may prove too large or small". [checkpointer.c#CheckpointerShmemSize](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L889-L902) [checkpointer.c#AbsorbSyncRequests](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1285-L1333)
- The 671,088,640 figure for a 20-relation drop is an upper bound on comparisons in one pass, not a timing. The threshold's own comment calls its value "rather a guess than an exactly determined value, as it depends on many factors (CPU and RAM speeds, amount of shared buffers etc.)", so this page cannot say whether 20 is the wrong cut-off at this pool size. [bufmgr.c#DropRelFileNodesAllBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3017-L3058)
- Whether giving up one MiB of cache to stay below the mapping hash's power-of-two boundary is worth about 257 MiB of shared memory is a workload judgement. The arithmetic is the whole of that claim; no run compared the two settings.
- No large-pool regression case was found in the inspected test search. Small configured pools in the recovery test and conditional TAP setup do not validate behavior or performance at this scale. [016_min_consistency.pl#shared_buffers](../../../../raw/postgres-12/src/test/recovery/t/016_min_consistency.pl#L46-L54) [PostgresNode.pm#allows_streaming](../../../../raw/postgres-12/src/test/perl/PostgresNode.pm#L462-L479)
- No frequency or latency bound for clock-sweep retries is established here. Concurrent pins, usage changes and candidate rejection prevent treating the header's simplified cycle discussion as a universal allocation bound. [buf_internals.h#BM_MAX_USAGE_COUNT](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L69-L77) [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L315-L357) [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1065-L1165)
- Shared-buffer mapping, clock-sweep replacement and buffer-access strategies lack version-local common-concept pages. They would be useful separate tasks; this question review does not create them.
- `verified: false` remains human-controlled. `verified_by_agent: not yet` is retained while the stated build and workload validation gaps remain.

## Source References

- [guc.c#shared_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2150-L2163)
- [config.sgml#shared_buffers](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1488-L1531)
- [sysv_shmem.c#CreateAnonymousSegment](../../../../raw/postgres-12/src/backend/port/sysv_shmem.c#L528-L590)
- [guc.c#memory_unit_conversion_table](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L788-L818)
- [configure.in#blocksize](../../../../raw/postgres-12/configure.in#L247-L277)
- [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L743-L796)
- [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1065-L1165)
- [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1828-L1871)
- [heapam.c#initscan](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L265)
- [initdb.c#test_config_settings](../../../../raw/postgres-12/src/bin/initdb/initdb.c#L947-L967)
- [initdb.c#test_config_settings](../../../../raw/postgres-12/src/bin/initdb/initdb.c#L1018-L1050)
- [buf_init.c#BufferShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L160-L193)
- [buf_internals.h#BufferDesc](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L135-L190)
- [freelist.c#StrategyShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L453-L465)
- [checkpointer.c#CheckpointerShmemSize](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L889-L902)
- [ipci.c#CreateSharedMemoryAndSemaphores](../../../../raw/postgres-12/src/backend/storage/ipc/ipci.c#L94-L166)
- [buf_internals.h#BufferDescPadded](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L192-L218)
- [lwlock.h#LWLock](../../../../raw/postgres-12/src/include/storage/lwlock.h#L32-L41)
- [lwlock.h#LWLOCK_MINIMAL_SIZE](../../../../raw/postgres-12/src/include/storage/lwlock.h#L61-L88)
- [buf_internals.h#BufferTag](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L91-L96)
- [buf_init.c#InitBufferPool](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L81-L83)
- [buf_internals.h#CkptSortItem](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L283-L298)
- [sync.h#FileTag](../../../../raw/postgres-12/src/include/storage/sync.h#L45-L51)
- [checkpointer.c#CheckpointerRequest](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L109-L113)
- [buf_table.c#BufTableShmemSize](../../../../raw/postgres-12/src/backend/storage/buffer/buf_table.c#L28-L45)
- [lwlock.h#NUM_BUFFER_PARTITIONS](../../../../raw/postgres-12/src/include/storage/lwlock.h#L107-L126)
- [dynahash.c#hash_estimate_size](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L731-L767)
- [dynahash.c#my_log2](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L1716-L1730)
- [dynahash.c#choose_nelem_alloc](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L603-L628)
- [dynahash.c#DEF_SEGSIZE](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L110-L113)
- [hsearch.h#HASHELEMENT](../../../../raw/postgres-12/src/include/utils/hsearch.h#L46-L55)
- [dynahash.c#HASHBUCKET](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L118-L122)
- [buf_table.c#InitBufTable](../../../../raw/postgres-12/src/backend/storage/buffer/buf_table.c#L52-L68)
- [dynahash.c#init_htab](../../../../raw/postgres-12/src/backend/utils/hash/dynahash.c#L670-L704)
- [pg_shmem.h#DEFAULT_SHARED_MEMORY_TYPE](../../../../raw/postgres-12/src/include/storage/pg_shmem.h#L72-L78)
- [sysv_shmem.c#PGSharedMemoryCreate](../../../../raw/postgres-12/src/backend/port/sysv_shmem.c#L624-L657)
- [buf_init.c#InitBufferPool](../../../../raw/postgres-12/src/backend/storage/buffer/buf_init.c#L111-L144)
- [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L994-L1057)
- [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L889-L924)
- [md.c#mdread](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L590-L600)
- [fd.c#FileRead](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1875-L1885)
- [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2671-L2788)
- [xlog.c#XLogFlush](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L2797-L2818)
- [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1803-L1857)
- [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1976-L1997)
- [bufmgr.c#SyncOneBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2354-L2411)
- [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2774-L2788)
- [bufmgr.c#PinBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1578-L1638)
- [buf_internals.h#BM_MAX_USAGE_COUNT](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L69-L77)
- [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L315-L357)
- [checkpointer.c#CheckpointerShmemInit](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L914-L931)
- [checkpointer.c#ForwardSyncRequest](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1086-L1160)
- [checkpointer.c#CompactCheckpointerRequestQueue](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1178-L1272)
- [md.c#register_dirty_segment](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L893-L912)
- [md.c#mdopen](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L450)
- [md.c#mdwrite](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L660-L670)
- [fd.c#FileWrite](../../../../raw/postgres-12/src/backend/storage/file/fd.c#L1958-L1968)
- [runtime.sgml#linux-memory-overcommit](../../../../raw/postgres-12/doc/src/sgml/runtime.sgml#L1448-L1476)
- [guc.c#work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2230-L2241)
- [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1774-L1871)
- [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2018-L2035)
- [bufmgr.c#CheckPointBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2580-L2590)
- [checkpointer.c#CheckpointWriteDelay](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L648-L715)
- [config.sgml#shared_buffers](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1510-L1528)
- [guc.c#max_wal_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2554-L2564)
- [bufmgr.c#DropRelFileNodeBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2919-L2923)
- [bufmgr.c#DropRelFileNodeBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2925-L2971)
- [bufmgr.c#DropRelFileNodesAllBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2982-L3072)
- [bufmgr.c#DropDatabaseBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3085-L3113)
- [bufmgr.c#PrintBufferDescs](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3122-L3169)
- [bufmgr.c#FlushRelationBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3183-L3188)
- [bufmgr.c#FlushRelationBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3190-L3271)
- [bufmgr.c#FlushDatabaseBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3288-L3325)
- [storage.c#smgrDoPendingDeletes](../../../../raw/postgres-12/src/backend/catalog/storage.c#L399-L460)
- [smgr.c#smgrdounlinkall](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L433-L463)
- [bufmgr.c:69](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L69)
- [bufmgr.c#DropRelFileNodesAllBuffers](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3017-L3058)
- [storage.c#RelationTruncate](../../../../raw/postgres-12/src/backend/catalog/storage.c#L230-L295)
- [smgr.c#smgrtruncate](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L646-L669)
- [freespace.c#FreeSpaceMapTruncateRel](../../../../raw/postgres-12/src/backend/storage/freespace/freespace.c#L321-L322)
- [visibilitymap.c#visibilitymap_truncate](../../../../raw/postgres-12/src/backend/access/heap/visibilitymap.c#L534-L535)
- [vacuumlazy.c#lazy_truncate_heap](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1950-L1974)
- [storage.c#smgr_redo](../../../../raw/postgres-12/src/backend/catalog/storage.c#L575-L629)
- [heapam_handler.c#heapam_relation_copy_data](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L636-L660)
- [tablecmds.c#index_copy_data](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L12764-L12791)
- [heapam.c#heap_sync](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L8923-L8960)
- [dbcommands.c#createdb](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L574-L585)
- [dbcommands.c#dbase_redo](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L2130-L2141)
- [dbcommands.c#dropdb](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L937-L942)
- [dbcommands.c#dbase_redo](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L2143-L2173)
- [dbcommands.c#movedb](../../../../raw/postgres-12/src/backend/commands/dbcommands.c#L1200-L1228)
- [checkpointer.c#AbsorbSyncRequests](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1285-L1333)
- [checkpointer.c#CompactCheckpointerRequestQueue](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1196-L1208)
- [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L200-L217)
- [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L268-L357)
- [freelist.c#ClockSweepTick](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L112-L168)
- [guc.c#bgwriter_lru_maxpages](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2738-L2746)
- [guc.c#bgwriter_delay](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2727-L2736)
- [bufmgr.c#BgBufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2040-L2336)
- [bgwriter.c#BackgroundWriterMain](../../../../raw/postgres-12/src/backend/postmaster/bgwriter.c#L327-L373)
- [pg_prewarm.c#pg_prewarm](../../../../raw/postgres-12/contrib/pg_prewarm/pg_prewarm.c#L185-L199)
- [autoprewarm.c#autoprewarm](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L1-L24)
- [autoprewarm.c#apw_dump_now](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L644-L650)
- [pg_buffercache_pages.c#BufferCachePagesRec](../../../../raw/postgres-12/contrib/pg_buffercache/pg_buffercache_pages.c#L26-L44)
- [pg_buffercache_pages.c#pg_buffercache_pages](../../../../raw/postgres-12/contrib/pg_buffercache/pg_buffercache_pages.c#L126-L176)
- [autoprewarm.c#BlockInfoRecord](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L58-L65)
- [autoprewarm.c#apw_dump_now](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L559-L620)
- [autoprewarm.c#_PG_init](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L114-L141)
- [autoprewarm.c#autoprewarm_main](../../../../raw/postgres-12/contrib/pg_prewarm/autoprewarm.c#L207-L246)
- [memutils.h#MaxAllocSize](../../../../raw/postgres-12/src/include/utils/memutils.h#L24-L46)
- [mcxt.c#palloc](../../../../raw/postgres-12/src/backend/utils/mmgr/mcxt.c#L924-L938)
- [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1169-L1212)
- [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L268-L313)
- [config.sgml#huge_pages](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1533-L1590)
- [guc.c#huge_pages](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4470-L4478)
- [heapam.c#initscan](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L233-L300)
- [syncscan.c#synchronized-scans](../../../../raw/postgres-12/src/backend/access/heap/syncscan.c#L6-L32)
- [tableam.c#table_block_parallelscan_initialize](../../../../raw/postgres-12/src/backend/access/table/tableam.c#L370-L385)
- [tableam.c#table_block_parallelscan_startblock_init](../../../../raw/postgres-12/src/backend/access/table/tableam.c#L403-L430)
- [freelist.c#GetAccessStrategy](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L541-L588)
- [hash.c#hashbuild](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L138-L158)
- [clog.c#CLOGShmemBuffers](../../../../raw/postgres-12/src/backend/access/transam/clog.c#L675-L679)
- [commit_ts.c#CommitTsShmemBuffers](../../../../raw/postgres-12/src/backend/access/transam/commit_ts.c#L469-L473)
- [xlog.c#XLOGChooseNumBuffers](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L4850-L4873)
- [pg_config_manual.h#DEFAULT_XLOG_SEG_SIZE](../../../../raw/postgres-12/src/include/pg_config_manual.h#L16-L20)
- [configure.in#wal_blocksize](../../../../raw/postgres-12/configure.in#L312-L330)
- [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L732-L742)
- [config.sgml#temp_buffers](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1592-L1612)
- [vacuum.c#vacuum](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L292-L299)
- [autovacuum.c#do_autovacuum](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2288)
- [costsize.c#index_pages_fetched](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L825-L877)
- [guc.c#effective_cache_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3107-L3117)
- [buf_internals.h#buffer-state](../../../../raw/postgres-12/src/include/storage/buf_internals.h#L30-L77)
- [freelist.c#BufferAccessStrategyData](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L67-L97)
- [configure.in#AC_CONFIG_HEADERS](../../../../raw/postgres-12/configure.in#L2473-L2477)
- [pg_config.h.in#BLCKSZ](../../../../raw/postgres-12/src/include/pg_config.h.in#L39-L43)
- [pg_config.h.in#SIZEOF_VOID_P](../../../../raw/postgres-12/src/include/pg_config.h.in#L879)
- [c.h#configuration-headers](../../../../raw/postgres-12/src/include/c.h#L54-L55)
- [Makefile#OBJS](../../../../raw/postgres-12/src/backend/storage/buffer/Makefile#L15)
- [Makefile#lwlocknames](../../../../raw/postgres-12/src/backend/storage/lmgr/Makefile#L29-L33)
- [smgr.c#smgrdounlinkfork](../../../../raw/postgres-12/src/backend/storage/smgr/smgr.c#L500-L523)
- [smgr.h:93](../../../../raw/postgres-12/src/include/storage/smgr.h#L93)
- [Makefile#catalog-generation](../../../../raw/postgres-12/src/backend/catalog/Makefile#L60-L89)
- [Makefile#install-data](../../../../raw/postgres-12/src/backend/catalog/Makefile#L106-L109)
- [gram.y#VariableSetStmt](../../../../raw/postgres-12/src/backend/parser/gram.y#L1402-L1421)
- [utility.c#VariableSetStmt](../../../../raw/postgres-12/src/backend/tcop/utility.c#L684-L685)
- [guc.c#ExecSetVariableStmt](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L8100-L8124)
- [guc.c#shared_memory_type](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4429-L4437)
- [guc.c#wal_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2602-L2611)
- [guc.c#checkpoint_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2566-L2575)
- [guc.c#checkpoint_completion_target](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3413-L3421)
- [guc.c#checkpoint_flush_after](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2591-L2600)
- [guc.c#bgwriter_lru_multiplier](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3351-L3359)
- [guc.c#bgwriter_flush_after](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2748-L2757)
- [guc.c#log_checkpoints](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1217-L1225)
- [guc.c#backend_flush_after](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2777-L2786)
- [guc.c#synchronize_seqscans](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1732-L1740)
- [guc.c#temp_buffers](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2165-L2174)
- [guc.c#maintenance_work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2243-L2252)
- [guc.c#track_io_timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1401-L1409)
- [system_views.sql#pg_stat_bgwriter](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L935-L947)
- [system_views.sql#pg_stat_database](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L856-L882)
- [monitoring.sgml#statistics-collection](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L229-L260)
- [xlog.c#LogCheckpointEnd](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L8435-L8442)
- [xlog.c:8442](../../../../raw/postgres-12/src/backend/access/transam/xlog.c#L8442)
- [md.c#mdextend](../../../../raw/postgres-12/src/backend/storage/smgr/md.c#L373-L422)
- [checkpointer.c#ForwardSyncRequest](../../../../raw/postgres-12/src/backend/postmaster/checkpointer.c#L1107-L1160)
- [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L245-L250)
- [bufmgr.c#ReadBufferExtended](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L640-L669)
- [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L732-L796)
- [pgstat.h#pgstat_count_buffer_read](../../../../raw/postgres-12/src/include/pgstat.h#L1384-L1397)
- [pgstat.c#pgstat_initstats](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L1751-L1784)
- [pgstat.c#pgstat_recv_tabstat](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6001-L6005)
- [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2764-L2769)
- [pgstatfuncs.c#pg_stat_get_db_blk_read_time](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L1569-L1597)
- [guc.c#statement_timeout-and-lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2397)
- [pg_proc.dat#numeric](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L4292-L4294)
- [pg_proc.dat#round](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L4130-L4132)
- [system_views.sql#pg_settings](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L512-L513)
- [pg_proc.dat#pg_show_all_settings](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L5770-L5775)
- [guc.c#block_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2879-L2888)
- [pg_proc.dat#pg_size_pretty](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L6897-L6899)
- [runtime.sgml#linux-huge-pages](../../../../raw/postgres-12/doc/src/sgml/runtime.sgml#L1542-L1566)
- [016_min_consistency.pl#shared_buffers](../../../../raw/postgres-12/src/test/recovery/t/016_min_consistency.pl#L46-L54)
- [PostgresNode.pm#allows_streaming](../../../../raw/postgres-12/src/test/perl/PostgresNode.pm#L462-L479)
- [bufmgr.c#BufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L994-L1165)
- [bufmgr.c#BufferSync](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1976-L2035)
- [freelist.c#StrategyGetBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/freelist.c#L200-L357)

## Navigation

- [v12/index](../../index.md)
- [PostgreSQL 12 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
