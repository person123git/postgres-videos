---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# Pros and Cons of a Very Large shared_buffers Such as 256 GB on a 1 TB RAM System in PostgreSQL 17, and What Changed Since PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [What 256 GiB of shared_buffers actually allocates](#what-256-gib-of-shared_buffers-actually-allocates)
  - [How the 256 GiB figures were computed under a 4 GiB test cap](#how-the-256-gib-figures-were-computed-under-a-4-gib-test-cap)
  - [Pros](#pros)
  - [Cons](#cons)
  - [The edges: the floor, the ceiling, and a pool larger than the machine](#the-edges-the-floor-the-ceiling-and-a-pool-larger-than-the-machine)
  - [Thresholds that move when NBuffers is huge](#thresholds-that-move-when-nbuffers-is-huge)
  - [What a big pool does not buy](#what-a-big-pool-does-not-buy)
  - [What changed since PostgreSQL 12](#what-changed-since-postgresql-12)
  - [What did not change since PostgreSQL 12](#what-did-not-change-since-postgresql-12)
  - [Settings that move with it, and their apply scope](#settings-that-move-with-it-and-their-apply-scope)
  - [What to look at before and after the change](#what-to-look-at-before-and-after-the-change)
  - [Decision guide](#decision-guide)
  - [How this was measured, and what the measurements cannot say](#how-this-was-measured-and-what-the-measurements-cannot-say)
- [Measurement Script](#measurement-script)
  - [Usage](#usage)
  - [The script](#the-script)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 17, what are the pros and cons of having a very large `shared_buffers`, like 256 GB or more, on a system with more than 1 TB of RAM? What has changed since PostgreSQL 12?

Prompt note, per `MANDATORY Prompt Hygiene`: the request read `follow agents.md, In PostgreSQL 17, what are the pros and cons of having a very large \`shared_buffers\`, like 256 GB or more, on a system with more than 1 TB of RAM?, what have changed since version 12.` The defects were `agents.md` for AGENTS.md, the lowercase sentence opening `follow`, a comma splice joining the instruction to the question with `In` capitalised mid-sentence, `?,` splicing two questions together, `what have changed` for `what has changed`, a terminating period on a question, and `version 12` for `PostgreSQL 12`. The asker chose **correct and restate**, chose to **build 17.11 and measure** rather than a source-only answer, chose to evidence the since-v12 part from **`raw/postgres-17/` citations plus that checkout's own commit history** rather than citing the v12 checkout, and scoped the delta to **large-pool mechanisms only**. All four choices are recorded here.

Revision note, 2026-09-17: a review of the first filing listed 16 defects in it - nine wrong or overstated source claims, four defects in the published script, and three omissions from the since-v12 history. All 16 are corrected here, and the script was edited in place and re-run end to end. The same review **capped every `shared_buffers` value this page's script may name at 4 GiB**, in a running server and in a non-allocating `postgres -C` probe alike. That cap is why no number on this page is measured above **524,288 buffers**, why the pool ladder is 1, 2, 3 and 4 GiB, and why every 256 GiB figure below is arithmetic on formulas validated under the cap rather than an answer from the binary. Each such figure says so where it appears.

The PostgreSQL 12 answer to the same question is a separate page: [Pros and Cons of a Very Large shared_buffers Such as 256 GB on a 1 TB RAM System in PostgreSQL 12 (unverified)](../../../v12/questions/storage-and-vacuum/very-large-shared-buffers.md). This page does not cite it as evidence.

## Answer

### Short answer

**256 GiB is a legal setting that v17 will allocate, and the engine has more pool-size-dependent machinery than v12 did - but three things it must do per operation still walk every buffer, and source alone cannot say whether the trade is a win for a given workload.**

- `shared_buffers` is `PGC_POSTMASTER`, so any change needs a **restart**. The range is 16 blocks through `INT_MAX / 2` blocks, because the code "sometimes multiplies the number of shared buffers by two without checking for overflow" ([guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2257-L2270)). The engine prints both ends when you miss them: asking for 15 blocks gets `FATAL: 15 8kB is outside the valid range for parameter "shared_buffers" (16 8kB .. 1073741823 8kB)`.
- The shipped documentation still recommends 25 % of memory as a starting point and cautions that more than 40 % is unlikely to beat a smaller setting, and it warns that a larger pool usually needs a matching `max_wal_size` increase ([config.sgml#shared_buffers](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L1650-L1692)). 256 GiB is 25 % of 1 TiB.
- At the default 8 kB block size, `shared_buffers = '256GB'` is **33,554,432 buffers**. The whole shared-memory segment for that pool works out to **280,492,630,016 bytes**, which `shared_memory_size` would report as **267,499 MB**: 262,144 MiB of pages plus **5,355 MiB** of bookkeeping. That figure is arithmetic, not a measurement - the pinned formulas, fitted to four segments measured exactly at 1 to 4 GiB and then evaluated at 33,554,432 buffers. See [How the 256 GiB figures were computed under a 4 GiB test cap](#how-the-256-gib-figures-were-computed-under-a-4-gib-test-cap).
- The measured costs that scale with the pool are a whole **`CHECKPOINT`, whose first act is to lock and inspect every buffer header** (11.0 ns per buffer on the test host), **server start** (71 ns per buffer), and every **`DROP`** (6.6 ns per buffer) and **`TRUNCATE`** (9.6 ns per buffer). On a primary the drop and truncate passes are not optimised away: the targeted-lookup shortcut added in v14 is reachable only in recovery, and even there only under conditions a big relation fails.
- The single most surprising number is unchanged from v12: a sequential scan asks for the bulk-read ring and synchronised scanning only when the relation exceeds **`NBuffers / 4`** ([heapam.c#initscan](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L408-L527)). At 256 GiB that line sits at **64 GiB**, so every smaller scan is free to evict the pool.

### What 256 GiB of shared_buffers actually allocates

Four arrays and one hash table are sized directly from `NBuffers` ([buf_init.c#InitBufferPool](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L67-L151), [buf_init.c#BufferShmemSize](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L159-L186), [freelist.c#StrategyShmemSize](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L452-L464)), the checkpointer's sync-request queue is sized from it ([checkpointer.c#CheckpointerShmemSize](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L882-L897)), and so are three SLRU caches, up to a cap they reach at exactly 4 GiB ([slru.c#SimpleLruAutotuneBuffers](../../../../raw/postgres-17/src/backend/access/transam/slru.c#L232-L237)).

The per-buffer column is measured on a running server from `pg_shmem_allocations.allocated_size`, at a 4 GiB pool (524,288 buffers). The 256 GiB column is **arithmetic**: the same formulas evaluated at 33,554,432 buffers, using a model checked against four measured segments in the next subsection.

| Shared memory region | Bytes per buffer, measured at 524,288 buffers | Arithmetic at 33,554,432 buffers | Source |
|---|---|---|---|
| `Buffer Blocks` | 8192.008 | 262,144 MiB + 4 kB alignment | [buf_init.c:82-86](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L82-L86) |
| `Buffer Descriptors` | 64.000 | 2048 MiB | [buf_init.c:76-79](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L76-L79) |
| `Checkpointer Data` (sync-request slots) | 32.000, until the queue caps | 305 MiB at the 10,000,000-slot cap | [checkpointer.c:886-895](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L886-L895) |
| `Checkpoint BufferIds` (sort array) | 20.000 | 640 MiB | [buf_init.c:101-103](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L101-L103) |
| `Buffer IO Condition Variables` | 16.000 | 512 MiB | [buf_init.c:88-92](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L88-L92) |
| `Shared Buffer Lookup Table` | 0.064 in the named row; its buckets, directory and elements are allocated outside it | 1794 MiB in total | [freelist.c:478-488](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L478-L488), [buf_table.c#BufTableShmemSize](../../../../raw/postgres-17/src/backend/storage/buffer/buf_table.c#L40-L44), [dynahash.c#hash_estimate_size](../../../../raw/postgres-17/src/backend/utils/hash/dynahash.c#L783-L819) |
| `transaction`, `commit_timestamp`, `subtransaction` | 32.315 + 16.315 + 16.315, still growing at 4 GiB | 8 MiB each, at the 1024-block cap | [slru.c#SimpleLruShmemSize](../../../../raw/postgres-17/src/backend/access/transam/slru.c#L198-L222), [clog.c#CLOGShmemBuffers](../../../../raw/postgres-17/src/backend/access/transam/clog.c#L767-L775) |
| whole segment | 8490.938 | 8359.332 | `sum(allocated_size)`, which covers the whole segment ([shmem.c:510-534](../../../../raw/postgres-17/src/backend/storage/ipc/shmem.c#L510-L534)) |

The per-buffer total falls as the pool grows because two of its terms stop growing: measured over the whole segment it is **8628.750** bytes per buffer at 1 GiB, **8536.875** at 2 GiB, **8500.896** at 3 GiB and **8490.938** at 4 GiB. Differencing `-C shared_memory_size` answers over block pairs shows the same thing as a marginal cost:

| Block-count pair | Marginal bytes per buffer | What is happening |
|---|---|---|
| 150,000 -> 250,000 | **8430** | inside one bucket regime; three SLRUs still growing |
| 400,000 -> 500,000 | **8441** | same regime, same terms |
| 262,100 -> 524,160 | **8426** | the widest span the 4 GiB cap allows, so the least affected by the MiB rounding |
| 200,000 -> 300,000 | **8451** | the mapping table's bucket array doubles inside this range |

That marginal figure is **not** the one a 256 GiB pool pays, and the difference is the point. It decomposes exactly:

| Term | Bytes per buffer | Why |
|---|---|---|
| the four `NBuffers` arrays | 8192 + 64 + 16 + 20 = **8292** | one page, one `BufferDescPadded`, one condition variable, one `CkptSortItem` ([buf_init.c#BufferShmemSize](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L159-L186)) |
| one sync-request slot | **32** | while `NBuffers < 10,000,000` ([checkpointer.c#CheckpointerShmemSize](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L882-L897)) |
| one mapping-table element | **40** | `MAXALIGN(sizeof(HASHELEMENT)) + MAXALIGN(24)` ([dynahash.c:810-816](../../../../raw/postgres-17/src/backend/utils/hash/dynahash.c#L810-L816)) |
| three auto-sizing SLRUs | 32.31 + 16.31 + 16.31 = **64.94** | while `NBuffers / 512 < 1024`; measured as the per-block cost of each cache divided by 512 |
| total inside the cap | **8428.9** | against 8426 to 8451 measured |

The SLRU term is the one the cap hides. `transaction` costs 16,545 bytes per block against 8,353 for the other two, because CLOG alone carries a `group_lsn` array of `CLOG_LSNS_PER_PAGE` LSNs per slot ([slru.c:218-221](../../../../raw/postgres-17/src/backend/access/transam/slru.c#L218-L221), [clog.c#CLOGShmemSize](../../../../raw/postgres-17/src/backend/access/transam/clog.c#L777-L784)), and all three stop growing at 1024 blocks - that is, at `NBuffers = 524,288`, the cap itself ([slru.c#SimpleLruAutotuneBuffers](../../../../raw/postgres-17/src/backend/access/transam/slru.c#L232-L237)). So above 4 GiB the marginal cost drops to **8364** bytes per buffer, and above 10,000,000 blocks (76.3 GiB) the sync-request slot stops too, leaving **8332** ([checkpointer.c:133-134](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L133-L134)). Neither of those two figures is measurable under the cap; both are arithmetic on the terms above.

**256 GiB lands one step past a power-of-two boundary in the mapping table, and that step is 257 MiB.** The table is sized `NBuffers + NUM_BUFFER_PARTITIONS` ([freelist.c:478-488](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L478-L488), [lwlock.h:87-93](../../../../raw/postgres-17/src/include/storage/lwlock.h#L87-L93)), so 128 is added to a 2^25 pool, and `hash_estimate_size()` rounds the bucket count up to a power of two, sizes the segment array from it, and doubles the directory with it ([dynahash.c#hash_estimate_size](../../../../raw/postgres-17/src/backend/utils/hash/dynahash.c#L783-L819)). The cap forbids probing the 2^25 boundary, so the step was measured at 2^18 instead, where the same arithmetic predicts 2,105,344 bytes:

| `shared_buffers` in blocks | `shared_memory_size` | Delta | Note |
|---|---|---|---|
| 261,888 | 2130 MB | - | |
| 262,016 (2^18 - 128) | 2131 MB | +1 MB | last size with 2^18 buckets |
| 262,017 | 2133 MB | **+2 MB** | first size needing 2^19 buckets |
| 262,144 (2 GiB exactly) | 2135 MB | +2 MB | |
| 262,145 | 2135 MB | 0 | |

At the 2^25 boundary the same formula gives 1,611,663,272 bytes of lookup table just below it and 1,881,147,304 bytes just above: a **269,484,032-byte, 257 MiB** step, which is 256 MiB of bucket segments plus 1 MiB of directory. So `shared_buffers = '255GB'` (33,423,360 blocks) is arithmetically cheaper than `'256GB'` by that step. Whether 257 MiB matters on a 1 TiB host is a judgement, not a source claim.

Huge pages: at this host's 2 MiB `Hugepagesize` a 256 GiB pool needs **133,750** pages, or **262** with `huge_page_size = '1GB'`, by the same arithmetic through `hp_required = size_b / hp_size + 1` ([ipci.c#InitializeShmemGUCs](../../../../raw/postgres-17/src/backend/storage/ipc/ipci.c#L369-L398), [guc_tables.c#huge_page_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3598-L3607)). Both settings are `PGC_POSTMASTER`: **restart**.

### How the 256 GiB figures were computed under a 4 GiB test cap

Every 256 GiB number above comes from one arithmetic model, and the model is checked before it is used. `postgres -C shared_memory_size` would answer directly - it runs the sizing code and exits at [postmaster.c:964-971](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L964-L971), before `CreateSharedMemoryAndSemaphores()` at [postmaster.c:980](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L980) - but naming a 256 GiB value even there is outside this page's cap, so it was not asked.

The model implements the pool-scaling terms of `CalculateShmemSize()` and nothing else: [buf_init.c#BufferShmemSize](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L159-L186), [freelist.c#StrategyShmemSize](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L452-L464), [buf_table.c#BufTableShmemSize](../../../../raw/postgres-17/src/backend/storage/buffer/buf_table.c#L40-L44), [dynahash.c#hash_estimate_size](../../../../raw/postgres-17/src/backend/utils/hash/dynahash.c#L783-L819), [checkpointer.c#CheckpointerShmemSize](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L882-L897), and the final 8 kB round-up at [ipci.c:162-163](../../../../raw/postgres-17/src/backend/storage/ipc/ipci.c#L162-L163). Everything that does not scale with `NBuffers` is fitted as one constant. So that nothing unmodelled moves during the fit, the measurement pass pins the three auto-sizing SLRUs to 1024 blocks - the value their own formula caps at, and therefore the value a 256 GiB pool would choose - and pins `wal_buffers` to the 16 MiB that `XLOGChooseNumBuffers()` caps at from a 1 GiB pool upward ([xlog.c#XLOGChooseNumBuffers](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L4575-L4585)).

The measured side is exact: `sum(allocated_size)` over `pg_shmem_allocations` is the whole segment in bytes, because the view emits every named allocation, one `<anonymous>` row for allocations outside the shmem index, and one NULL-name row for the unused tail ([shmem.c:510-534](../../../../raw/postgres-17/src/backend/storage/ipc/shmem.c#L510-L534)).

| Buffers | Measured segment, bytes | Model, bytes | Residual |
|---|---|---|---|
| 131,072 (1 GiB) | 1,156,521,984 | 1,156,521,984 | fitted here; constant term 58,116,200 bytes |
| 262,144 (2 GiB) | 2,254,913,536 | 2,254,905,344 | **+8192** |
| 393,216 (3 GiB) | 3,351,199,744 | 3,351,191,552 | **+8192** |
| 524,288 (4 GiB) | 4,451,696,640 | 4,451,688,448 | **+8192** |

The residual is one 8 kB page, identically, at all three checks - exactly the granularity of the round-up the sizing code finishes with. Evaluated at 33,554,432 buffers the model gives **280,492,621,824** bytes, and with that same one-page residual **280,492,630,016** bytes, which `shared_memory_size` would round up and print as **267,499 MB**. The corresponding huge-page counts are 133,750 and 262.

Two independent facts support the extrapolation. The per-buffer constants the model uses were each measured in the table above, and the marginal cost the model predicts for a pool above the SLRU cap, 8364 bytes per buffer, decomposes exactly into source constants: `8192 + 64 + 16 + 20` for the four arrays, `32` for one sync-request slot, and `40` for one mapping-table element, which is `MAXALIGN(sizeof(HASHELEMENT)) + MAXALIGN(sizeof(BufferLookupEnt))` with the 24-byte entry of [buf_table.c:26-31](../../../../raw/postgres-17/src/backend/storage/buffer/buf_table.c#L26-L31). What no arithmetic can supply is what the operating system does with a 261 GiB mapping; see `## Open Questions`.

### Pros

**A hit costs a partition lock and a pin, never an `smgr` call.** `ReadBuffer_common()` reaches `PinBufferForBlock()` and returns when the page is already valid; only a miss reaches `WaitReadBuffers()` -> `smgrreadv()` ([bufmgr.c#ReadBuffer_common](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1196-L1264), [bufmgr.c#WaitReadBuffers](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1411-L1588)). More resident pages means more of this path, though source cannot say how many more for a given workload.

**A dirty victim is written by whichever backend needs the buffer, and that write forces WAL first.** `GetVictimBuffer()` writes the page it wants to reuse **only if that page is dirty** - the `FlushBuffer()` call sits inside `if (buf_state & BM_DIRTY)` - and `FlushBuffer()` calls `XLogFlush()` up to the page LSN before `smgrwrite()` ([bufmgr.c#GetVictimBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1954-L2105), [bufmgr.c:1995-2053](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1995-L2053), [bufmgr.c:3927](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3927), [bufmgr.c:3948](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3948)). A pool that holds the working set makes that foreground write rarer.

**The v16 counters for this count replacement, not writing.** `pg_stat_io`'s `evictions` and `reuses` are incremented for **every** victim that was `BM_VALID`, dirty or clean, and whether or not anything reached storage: the `IOOP_EVICT`/`IOOP_REUSE` counting is outside the dirty branch, and `reuses` specifically means the buffer came from the caller's own strategy ring ([bufmgr.c:2061-2081](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2061-L2081), [system_views.sql#pg_stat_io](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1153-L1173)). Measured: one bulk-read scan of a 37,384-block table through a 256 kB ring reported **37,352 `reuses` and 0 `evictions`**, with `writes` untouched, because the ring's own pages were clean and were simply replaced. Ring reuse at that rate is the strategy working as designed, not a signal that the pool is too small. The foreground *write* is `pg_stat_io.writes` on the client-backend row.

**A checkpoint writes only what was dirty when it started.** `BufferSync()` marks the dirty set with `BM_CHECKPOINT_NEEDED` in one pass and writes that set, so a page dirtied repeatedly between checkpoints is not written once per dirtying ([bufmgr.c#BufferSync](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2931-L3193)). A larger pool can absorb more re-dirtying before a write is forced, at the cost of a larger dirty set to write when the checkpoint comes.

**Hot pages survive the sweep.** `usage_count` rises to `BM_MAX_USAGE_COUNT` (5) and the clock sweep must decrement it to zero before the buffer can be taken ([buf_internals.h:71-79](../../../../raw/postgres-17/src/include/storage/buf_internals.h#L71-L79), [freelist.c#StrategyGetBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L196-L357)).

**The strategy rings scale with the pool instead of shrinking it.** `GetAccessStrategyWithSize()` caps every ring at `NBuffers / 8`, which is 32 GiB at 256 GiB, and treats 0 as "no strategy at all" - so a `VACUUM` there can be given a ring as large as the setting's own maximum, 16 GiB, and get all of it, or be told `0` and use the pool like any other reader ([freelist.c#GetAccessStrategyWithSize](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L583-L614), [miscadmin.h:274-278](../../../../raw/postgres-17/src/include/miscadmin.h#L274-L278)). Note which limit binds where: below a 128 GiB pool the `NBuffers / 8` cap is the smaller of the two, and at or above it the setting's 16 GiB maximum is. Measured at a 1 GiB pool, where that cap is 16,384 blocks, against a fixture rebuilt identically for each run and counted on the main fork only:

| `BUFFER_USAGE_LIMIT` | Main-fork blocks of the table left in the pool | Table size, main fork |
|---|---|---|
| `'128kB'` | 16 - exactly the ring | 41,122 |
| `'2MB'` (the default) | 256 - exactly the ring | 41,122 |
| `'256MB'` | 16,384 - exactly the `NBuffers / 8` cap, not the 32,768 blocks asked for | 41,122 |
| `'0'` (unlimited) | 41,122 - the whole table | 41,122 |

Each run also left 13 free-space-map and 2 visibility-map blocks resident, which is why the count needs a fork filter: without one, the ring sizes read 15 blocks high.

**Per-backend pin budgets grow with the pool.** Batched pin limits are `NBuffers / (MaxBackends + NUM_AUXILIARY_PROCS)`, which read streams and relation extension both consult; at a small pool this is the binding limit, at 256 GiB it is not ([bufmgr.c#LimitAdditionalPins](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2120-L2144), [read_stream.c:452-478](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L452-L478)).

**Three SLRU caches grow with the pool, up to a cap.** `transaction_buffers`, `commit_timestamp_buffers` and `subtransaction_buffers` default to `NBuffers / 512` rounded down to a 16-slot bank and capped at 1024 blocks ([slru.c#SimpleLruAutotuneBuffers](../../../../raw/postgres-17/src/backend/access/transam/slru.c#L232-L237), [clog.c#CLOGShmemBuffers](../../../../raw/postgres-17/src/backend/access/transam/clog.c#L767-L775)). Measured across the ladder: 256 blocks at 1 GB, 512 at 2 GB, 768 at 3 GB and 1024 - the cap - at 4 GB. So 4 GiB is where this benefit ends: at 256 GiB each of the three is still 8 MiB, no larger unless set explicitly.

**The sync-request queue grows with the pool, up to a cap - but the queue-full path never goes away.** It is `Min(NBuffers, 10000000)` slots, so a 256 GiB pool gets the maximum ([checkpointer.c:133-134](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L133-L134), [checkpointer.c#CheckpointerShmemSize](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L882-L897)). `ForwardSyncRequest()` still returns false - leaving the caller to fsync for itself - in two cases, and only one of them is about size: when the queue is full *and* compaction finds no duplicate to drop, and whenever `checkpointer_pid` is 0, which no pool size affects ([checkpointer.c#ForwardSyncRequest](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L1098-L1141)). A bigger queue makes the first rarer; it does not remove the fallback, and the comment above the function says a backend fsync is "theoretically possible" for exactly that reason.

### Cons

**Every checkpoint locks and inspects all 33.5 million buffer headers before writing anything.** `BufferSync()`'s first loop takes the header spinlock on each buffer, then it sorts only the dirty set ([bufmgr.c#BufferSync](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2931-L3193)). What the table below times is a **whole `CHECKPOINT`**, not that scan alone: the WAL flush, `CheckPointGuts()` and the fsync phase are inside the interval too. What makes the scan the moving part is that there was almost nothing else to do - the pool was clean before each sequence, and the six checkpoints together wrote at most a handful of pages:

| Pool | Buffers | Dirty buffers before the sequence | Buffers the 6 checkpoints wrote | Median `CHECKPOINT` |
|---|---|---|---|---|
| 1 GB | 131,072 | 3 | 6 | 6.09 ms |
| 2 GB | 262,144 | 0 | 1 | 8.74 ms |
| 3 GB | 393,216 | 0 | 1 | 9.03 ms |
| 4 GB | 524,288 | 0 | 0 | 10.42 ms |

Keeping it that clean took a fix to the measurement itself: the first filing's timer inserted its result row between checkpoints, which dirtied a page and emitted WAL each time and inflated the 1 GiB median from 6.09 ms to 9.5 ms. The timer now accumulates in a local array and writes every row after the last checkpoint.

The slope across the ladder is **11.0 ns per buffer**, which extrapolates to about **0.37 s per checkpoint at 33,554,432 buffers**. The extrapolation is arithmetic on this host's slope over a 4x range, not a measurement of a 256 GiB pool.

**`DROP` and `TRUNCATE` scan the whole pool on a primary - once per statement, not once per fork.** `DropRelationBuffers()` and `DropRelationsAllBuffers()` will use targeted `BufMapping` lookups when every fork's size is cached and the total work is below `BUF_DROP_FULL_SCAN_THRESHOLD` (`NBuffers / 32`), but `smgrnblocks_cached()` returns `InvalidBlockNumber` unless `InRecovery`, so on a primary the shortcut is unreachable ([bufmgr.c:84-89](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L84-L89), [bufmgr.c#DropRelationBuffers](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4110-L4223), [bufmgr.c#FindAndDropRelationBuffers](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4405-L4452), [smgr.c#smgrnblocks_cached](../../../../raw/postgres-17/src/backend/storage/smgr/smgr.c#L678-L690)). Measured on a primary, medians over 30 runs of a one-block table, with the commit inside the timed interval because the pass happens in `smgrDoPendingDeletes()` at commit ([storage.c#smgrDoPendingDeletes](../../../../raw/postgres-17/src/backend/catalog/storage.c#L657-L719)), and with `synchronous_commit = off` so the commit's WAL flush wait is not inside it:

| Pool | Buffers | `DROP TABLE`, own transaction | `TRUNCATE`, main fork only | `TRUNCATE`, main + fsm + vm |
|---|---|---|---|---|
| 1 GB | 131,072 | 1.13 ms | 1.61 ms | 2.15 ms |
| 2 GB | 262,144 | 1.97 ms | 2.66 ms | 3.26 ms |
| 3 GB | 393,216 | 2.91 ms | 4.06 ms | 4.77 ms |
| 4 GB | 524,288 | 3.71 ms | 5.38 ms | 6.21 ms |

That is **6.6 ns per buffer per `DROP`** and **9.6 ns** per `TRUNCATE`, or about **0.22 s** and **0.32 s** respectively at 33,554,432 buffers by the same arithmetic. Three details matter operationally.

First, batching helps: dropping 30 one-block tables in one transaction cost **9.73 ms** at 524,288 buffers against 30 x 3.71 ms = 111 ms one at a time, an 11x saving, because `smgrdounlinkall()` hands the whole pending set to one `DropRelationsAllBuffers()` call ([smgr.c#smgrdounlinkall](../../../../raw/postgres-17/src/backend/storage/smgr/smgr.c#L462-L522)).

Second, **the fork count does not multiply the cost**. The three-fork table carried 222 main, 3 free-space-map and 1 visibility-map blocks, and its `TRUNCATE` cost 1.15x the one-fork table's at the same pool size, not 3x. That is what the code says too: `DropRelationBuffers()` takes a fork array and has exactly one `for (i = 0; i < NBuffers; i++)` loop, with the fork comparison inside it, and `RelationTruncate()` gathers every fork into one array and makes a single `smgrtruncate2()` call, which makes a single `DropRelationBuffers()` call ([bufmgr.c:4184-4222](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4184-L4222), [storage.c#RelationTruncate](../../../../raw/postgres-17/src/backend/catalog/storage.c#L288-L439), [smgr.c#smgrtruncate2](../../../../raw/postgres-17/src/backend/storage/smgr/smgr.c#L712-L736)). **The first filing said the opposite** - that `VACUUM`'s truncation runs a pass per fork - which was PostgreSQL 12 behaviour; commit `6d05086c0a79`, first released in 13.0, is what collapsed the three passes into one, and it is in the since-v12 table below.

Third, `TRUNCATE` measured consistently more per buffer than `DROP` even though both read as one pass in source; that gap is filed under `## Open Questions` rather than explained here.

**Six maintenance routines still walk every buffer, and the tree says so itself.** `FlushRelationBuffers()` carries the comment **`XXX currently it sequentially searches the buffer pool, should be changed to more clever ways of searching`**, with the rationale that these paths are not performance-critical - a judgement made for pools far smaller than this one ([bufmgr.c:4553-4568](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4553-L4568)).

| Routine | Reached by | Source |
|---|---|---|
| `DropRelationBuffers` | `smgrtruncate2()`, so `VACUUM` truncation and its replay - one call, every fork | [bufmgr.c#DropRelationBuffers](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4110-L4223), [smgr.c#smgrtruncate2](../../../../raw/postgres-17/src/backend/storage/smgr/smgr.c#L712-L736) |
| `DropRelationsAllBuffers` | pending deletes at commit: `DROP`, `TRUNCATE`, `REINDEX`, rewriting DDL | [bufmgr.c#DropRelationsAllBuffers](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4233-L4393) |
| `DropDatabaseBuffers` | `DROP DATABASE`, `ALTER DATABASE ... SET TABLESPACE`, replay of a drop, and the **failure** path of a `STRATEGY wal_log` `CREATE DATABASE` - not its success path | [bufmgr.c#DropDatabaseBuffers](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4465-L4493), [dbcommands.c#createdb_failure_callback](../../../../raw/postgres-17/src/backend/commands/dbcommands.c#L1593-L1616), [dbcommands.c#dropdb](../../../../raw/postgres-17/src/backend/commands/dbcommands.c#L1634-L1856), [dbcommands.c#movedb](../../../../raw/postgres-17/src/backend/commands/dbcommands.c#L1964-L2282) |
| `FlushRelationBuffers` | heap and index copies for `ALTER TABLE`/`ALTER INDEX ... SET TABLESPACE`, and an unlogged sequence's init fork | [bufmgr.c#FlushRelationBuffers](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4572-L4658), [heapam_handler.c:637-645](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L637-L645), [tablecmds.c:15586-15595](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L15586-L15595), [sequence.c:344-352](../../../../raw/postgres-17/src/backend/commands/sequence.c#L344-L352) |
| `FlushRelationsAllBuffers` | `smgrdosyncall()`, the `wal_level = minimal` sync path | [bufmgr.c#FlushRelationsAllBuffers](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4670-L4757) |
| `FlushDatabaseBuffers` | `CREATE DATABASE` replay of the file-copy strategy | [bufmgr.c#FlushDatabaseBuffers](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4925-L4960), [dbcommands.c#dbase_redo](../../../../raw/postgres-17/src/backend/commands/dbcommands.c#L3270-L3432) |

**Server start pays for initialising every header, serially.** `InitBufferPool()` clears the tag, initialises the atomic state, the content `LWLock` and the condition variable for each buffer in one loop ([buf_init.c#InitBufferPool](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L67-L151)). The postmaster logs `starting PostgreSQL` only *after* `CreateSharedMemoryAndSemaphores()` ([postmaster.c:980](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L980), [postmaster.c:1083-1084](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L1083-L1084)), so the interval that contains this work is the one before that line:

| Pool | Buffers | Shell clock to `starting PostgreSQL`, min of 10 | Median | `starting` to `ready`, min of 10 |
|---|---|---|---|---|
| 1 GB | 131,072 | 25 ms | 33.5 ms | 10 ms |
| 2 GB | 262,144 | 32 ms | 43.0 ms | 10 ms |
| 3 GB | 393,216 | 44 ms | 50.5 ms | 25 ms |
| 4 GB | 524,288 | 53 ms | 67.0 ms | 8 ms |

That is **71 ns per buffer** on the minima, about **2.4 s at 33,554,432 buffers** by extrapolation, and it is paid on every restart - including the restart that `shared_buffers` itself requires. The last column has no trend, so this is pool initialisation and mapping, not startup-process work. The interval also contains fork, exec and configuration load, which is why the minimum of ten restarts is the figure quoted and the median is printed beside it: at these pool sizes the per-restart noise is the same order as the pool's own share, and a single trial per size cannot see the slope at all.

**The pool is not a substitute for the operating system cache, and by default the data is in both.** Relation data is read with ordinary buffered `preadv()` unless `debug_io_direct` is set, which is `PGC_POSTMASTER` and which the shipped documentation restricts outright: "Currently this feature reduces performance, and is intended for developer testing only" ([guc_tables.c#debug_io_direct](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4699-L4708), [config.sgml#debug_io_direct](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L11595-L11624)). Turning it on removes the second copy, and with it the second cache. Measured as a controlled pair - the same 37,384-block table, the same default 128 kB `io_combine_limit`, the same 1 GiB pool, an empty pool on both legs, and only `debug_io_direct` different - `pg_stat_io` recorded **31.2 ms** of `bulkread` `read_time` buffered against **511.7 ms** with `debug_io_direct = data`, a 16x difference on identical block counts. Read that as how much the page cache was worth for a re-read on this host, not as a reason to set the option: the documentation's restriction stands, and this page makes no operational recommendation from it.

**`pg_buffercache`'s row-per-buffer reader costs one `BufferCachePagesRec` per buffer, collected before the first row is returned.** Measured at 524,288 buffers, median of three: **103.1 ms** for `SELECT count(*) FROM pg_buffercache`, against **1.8 ms** for `pg_buffercache_summary()` and **1.5 ms** for `pg_buffercache_usage_counts()` - a 56x gap ([pg_buffercache_pages.c#pg_buffercache_pages](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache_pages.c#L69-L246), [pg_buffercache_pages.c#pg_buffercache_summary](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache_pages.c#L249-L313)). Scaled to 33,554,432 buffers that is a multi-second query, and - as arithmetic on the record layout for a 64-bit build, where the struct's ten fields pack into 32 bytes - a 1 GiB temporary array. A monitoring job that selects from `pg_buffercache` every minute is therefore a different proposition at 256 GiB than at 4 GiB.

**Autoprewarm's dump repeats an `NBuffers`-sized allocation on a timer, and needed a fix to survive a large pool at all.** `apw_dump_now()` allocates `sizeof(BlockInfoRecord) * NBuffers` and walks every header; `pg_prewarm.autoprewarm_interval` defaults to 300 s and is `PGC_SIGHUP`, so with the module preloaded this repeats every five minutes until it is set to 0 ([autoprewarm.c#apw_dump_now](../../../../raw/postgres-17/contrib/pg_prewarm/autoprewarm.c#L569-L713), [autoprewarm.c:104-120](../../../../raw/postgres-17/contrib/pg_prewarm/autoprewarm.c#L104-L120)). The allocation passes `MCXT_ALLOC_HUGE`, with the comment "With sufficiently large shared_buffers, allocation will exceed 1GB, so allow for a huge allocation to prevent outright failure" ([autoprewarm.c:600-608](../../../../raw/postgres-17/contrib/pg_prewarm/autoprewarm.c#L600-L608)). That flag is new in this line: commit `e4b8f925a929`, first released in **17.6**, added it. `BlockInfoRecord` is 20 bytes on this build, so the 1 GiB `palloc` limit is reached at about 53.7 million buffers - a 410 GiB pool - and before 17.6 a pool that large made every autoprewarm dump fail.

**Replacement work is unbounded in wall-clock terms.** The clock sweep's stated bound is `BM_MAX_USAGE_COUNT + 1` complete cycles, and the `trycounter` resets on every usage-count decrement, so one allocation can examine far more than `NBuffers` headers under concurrency ([freelist.c#StrategyGetBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L196-L357), [freelist.c#ClockSweepTick](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L108-L164)). One sweep pass over 33.5 M buffers is 33.5 M atomic increments and header locks.

**Background cleaning has one knob that scales with the pool and one that does not.** `bgwriter_lru_maxpages` defaults to 100 and `bgwriter_delay` to 200 ms, neither derived from `NBuffers` ([guc_tables.c#bgwriter_lru_maxpages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3088-L3096), [guc_tables.c#bgwriter_delay](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3077-L3086)). What does scale is the round's floor target: `BgBufferSync()` computes `min_scan_buffers = NBuffers / (scan_whole_pool_milliseconds / bgwriter_delay)` with that constant fixed at 120000.0, which is **55,924 buffers** at 256 GiB and the default delay, and raises the round's target to `min_scan_buffers + reusable_buffers_est` when the allocation estimate is smaller ([bufmgr.c:3228-3230](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3228-L3230), [bufmgr.c:3394-3413](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3394-L3413)).

Those two numbers are not the same quantity, so a five-figure target beside a 100-page cap does not by itself prove the writer falls behind. The scan stops when `reusable_buffers` reaches the target, and a buffer counts toward `reusable_buffers` in two ways: because the round wrote it, or because `SyncOneBuffer()` found it already reusable - pin count and usage count both zero - and returned without writing anything. Only the first consumes the 100-page allowance ([bufmgr.c:3427-3450](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3427-L3450), [bufmgr.c#SyncOneBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3490-L3544)). Over a pool whose replacement candidates are mostly clean, the writer can therefore reach a 55,924-buffer target having written nothing, and `maxwritten_clean` stays at zero.

What a large pool does change is the ceiling on dirty work one round may clear, because that ceiling is absolute: 100 pages per 200 ms is 500 pages a second whatever `NBuffers` is. When the buffers ahead of the sweep really are dirty, the cleaning that matters is done by backends in `GetVictimBuffer()` and by the checkpointer, and `pg_stat_bgwriter.maxwritten_clean` against `pg_stat_io`'s client-backend `writes` is how to tell which case a given server is in.

**Fixed partitioning does not widen with the pool.** The mapping table has `NUM_BUFFER_PARTITIONS` = 128 partition locks regardless of size, and the strategy control block is guarded by a single `buffer_strategy_lock` spinlock ([lwlock.h:87-93](../../../../raw/postgres-17/src/include/storage/lwlock.h#L87-L93), [freelist.c:30-62](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L30-L62)).

**Memory committed here is memory `work_mem`, `maintenance_work_mem` and the page cache cannot use**, and the pool is not sized against them by any code in the tree. The planner never reads `NBuffers`; it reads `effective_cache_size`, which is a separate `PGC_USERSET` estimate of Postgres plus OS cache ([costsize.c:22-26](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L22-L26), [guc_tables.c#effective_cache_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3508-L3518)).

**There is no NUMA awareness anywhere in the tree.** A grep for `NUMA`, `libnuma` or `numa_available` across `src/`, `contrib/` and `configure.ac` in this checkout returns nothing, so a 256 GiB segment's placement across sockets is entirely the kernel's business.

**Nothing in the shipped tests exercises a large pool.** The only `shared_buffers` settings in the test tree are `128kB` in [016_min_consistency.pl:55](../../../../raw/postgres-17/src/test/recovery/t/016_min_consistency.pl#L55), `1MB` in [032_relfilenode_reuse.pl:21](../../../../raw/postgres-17/src/test/recovery/t/032_relfilenode_reuse.pl#L21) and `256kB` in [004_io_direct.pl:47](../../../../raw/postgres-17/src/test/modules/test_misc/t/004_io_direct.pl#L47). `contrib/pg_buffercache`'s own test only checks that its views agree with the setting ([pg_buffercache.sql](../../../../raw/postgres-17/contrib/pg_buffercache/sql/pg_buffercache.sql#L1-L12)).

### The edges: the floor, the ceiling, and a pool larger than the machine

The 4 GiB cap decides what this section can measure. The floor end of the range is inside it, so it is measured; the ceiling end is not, so it is a source claim and an error message, not a probe.

| Probe | Result | Measured? |
|---|---|---|
| `shared_buffers = 15` | `FATAL: 15 8kB is outside the valid range for parameter "shared_buffers" (16 8kB .. 1073741823 8kB)` | yes |
| `shared_buffers = 16`, started for real | `pg_ctl start` exits 0; the server reports `shared_buffers` = `128kB`, `shared_memory_size` = `8MB`, and answers `SELECT count(*) FROM pg_class` with 415 | yes |
| `shared_buffers = 524288` (4 GiB, the cap) | accepted; `shared_memory_size` = 4246 MB | yes |
| `shared_buffers = 1073741823` (the ceiling, just under 8 TiB) and one block past it | the ceiling is `INT_MAX / 2` blocks, and the engine names it in the range error above | no - source and the error text only |
| `shared_buffers = '1GB'`, `huge_pages = on`, no huge pages configured | exit status 1, `FATAL: could not map anonymous shared memory: Cannot allocate memory`, with the hint naming the request as 1,132,462,080 bytes and huge pages as a cause | yes |

That hinted request is 1080 MiB where `shared_memory_size` for the same pool is 1079 MB, because a huge-page attempt rounds the allocation up to a multiple of `Hugepagesize` before calling `mmap()` ([sysv_shmem.c:609-628](../../../../raw/postgres-17/src/backend/port/sysv_shmem.c#L609-L628)). At 256 GiB that rounding is at most 2 MiB on a 267,499 MB request.

The floor probe is the one the first filing got wrong. It asked `postgres -C shared_memory_size` and reported "starts" - but `-C` prints its answer and exits at [postmaster.c:964-971](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L964-L971), *before* `CreateSharedMemoryAndSemaphores()` at [postmaster.c:980](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L980), so it cannot tell you whether a setting starts a server. The floor now starts one and runs a query in it.

The range comes from the GUC definition ([guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2257-L2270)). The mapping failure comes from `CreateAnonymousSegment()`, which retries without `MAP_HUGETLB` only when `huge_pages` is not `on`, and otherwise reports the error with that hint ([sysv_shmem.c#CreateAnonymousSegment](../../../../raw/postgres-17/src/backend/port/sysv_shmem.c#L599-L668)). Two consequences follow from that code rather than from a measurement, because the cap forbids asking for a pool bigger than the machine: a request the kernel will not map is a failure to start rather than a degraded start, and `huge_pages = on` turns a missing huge-page reservation into the same failure - which is why v15's `shared_memory_size_in_huge_pages` exists ([guc_tables.c#shared_memory_size_in_huge_pages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2294-L2303)). What a mistyped `2560GB` does on a particular 1 TiB host is not settled here: whether `mmap` refuses depends on that host's memory, swap and `vm.overcommit_memory`, and the only over-size failure this page measured is the huge-page one above, on a 31 GiB host.

### Thresholds that move when NBuffers is huge

| Derived value | Formula | At 33,554,432 buffers | Source |
|---|---|---|---|
| Bulk-read ring and synchronised scanning kick in | relation > `NBuffers / 4` | 8,388,608 blocks = **64 GiB** | [heapam.c#initscan](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L408-L527), [tableam.c#table_block_parallelscan_initialize](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L389-L404) |
| Any strategy ring's cap | `NBuffers / 8`, but a `VACUUM` ring cannot be *asked* for more than `MAX_BAS_VAC_RING_SIZE_KB` = 16 GiB | 4,194,304 buffers = **32 GiB**, so the 16 GiB setting maximum binds first | [freelist.c#GetAccessStrategyWithSize](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L583-L614), [miscadmin.h:274-278](../../../../raw/postgres-17/src/include/miscadmin.h#L274-L278) |
| Targeted drop instead of a full scan (recovery only, and only if every fork's size is cached) | total blocks to invalidate < `NBuffers / 32` | 1,048,576 blocks = 8 GiB | [bufmgr.c:84-89](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L84-L89), [bufmgr.c:4156-4182](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4156-L4182) |
| Batched pin budget per backend | `NBuffers / (MaxBackends + NUM_AUXILIARY_PROCS)` | 260,111 at `max_connections = 100` and default worker and sender counts, where `MaxBackends` is 123 and `NUM_AUXILIARY_PROCS` 6 | [bufmgr.c#LimitAdditionalPins](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2120-L2144), [postinit.c:579-584](../../../../raw/postgres-17/src/backend/utils/init/postinit.c#L579-L584), [proc.h:431-443](../../../../raw/postgres-17/src/include/storage/proc.h#L431-L443) |
| `wal_buffers` when `-1` | `NBuffers / 32`, capped at one WAL segment | 16 MiB | [xlog.c#XLOGChooseNumBuffers](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L4575-L4585) |
| `transaction_buffers`, `commit_timestamp_buffers`, `subtransaction_buffers` when `0` | `NBuffers / 512`, bank-aligned, capped at 1024 blocks | 8 MiB each | [slru.c#SimpleLruAutotuneBuffers](../../../../raw/postgres-17/src/backend/access/transam/slru.c#L232-L237) |
| Background writer's per-round floor target | `NBuffers / (120000 / bgwriter_delay)` | 55,924 buffers, against a 100-page write cap | [bufmgr.c#BgBufferSync](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3207-L3488) |
| Checkpointer sync-request slots | `Min(NBuffers, 10000000)` | 10,000,000 | [checkpointer.c:133-134](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L133-L134) |

The `NBuffers / 4` line is the one to internalise. Measured at a 1 GiB pool, where the line is 32,768 blocks, counting main-fork blocks only:

| Fixture | Main-fork blocks | Context used | Blocks of it left in the pool after one seq scan | Pool blocks in use afterwards |
|---|---|---|---|---|
| `below` | 18,692 (under the line) | `normal`, 18,767 reads, 473 hits, **0** evictions | **18,692** - all of it | 18,854 of 131,072 |
| `above` | 37,384 (over the line) | `bulkread`, 37,384 reads, **37,352** reuses, 0 evictions | **32** - exactly the 256 kB ring | 194 of 131,072 |

Note what the `below` row does *not* show: 0 evictions. One scan of a relation under the line fills the pool with that relation, but it only evicts what it needs room for, and here there was room. A single plain scan of a sub-`NBuffers / 4` relation cannot by itself introduce more distinct pages than the relation has, so on a 256 GiB pool the exposure is a 64 GiB relation's worth of pages competing with the working set - not an emptied pool.

### What a big pool does not buy

- **Temporary tables.** They live in per-backend local buffers sized by `temp_buffers`, a `PGC_USERSET` setting with a 1024-block default and its own pin limit ([guc_tables.c#temp_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2382-L2391), [localbuf.c#LimitAdditionalLocalPins](../../../../raw/postgres-17/src/backend/storage/buffer/localbuf.c#L290-L306)).
- **`VACUUM`'s default footprint.** Its ring is 2 MB unless raised ([guc_tables.c#vacuum_buffer_usage_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2272-L2281)).
- **Planner cost estimates.** The planner reads `effective_cache_size`, never `NBuffers` ([costsize.c:22-26](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L22-L26)).
- **Read combining you can see.** `pg_stat_io.reads` counts *blocks*: `WaitReadBuffers()` passes `io_buffers_len` to `pgstat_count_io_op_time()`, and `op_bytes` is hard-coded to `BLCKSZ` ([bufmgr.c:1519-1521](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1519-L1521), [pgstatfuncs.c:1425-1431](../../../../raw/postgres-17/src/backend/utils/adt/pgstatfuncs.c#L1425-L1431)). Measured, the same scan reported **37,495 reads and 380 hits at every one** of `io_combine_limit` = 8 kB, 32 kB, 128 kB and 256 kB, on all three trials of each. The setting does move the clock: median `read_time` was 39.0 ms at 8 kB against 30.1, 27.9 and 34.4 ms at 32 kB, 128 kB and 256 kB, and median scan time 152.4 ms against 123.5, 120.3 and 128.8 ms. So combining is real and invisible to the counters at once.
- **A warm pool after a restart.** `pg_prewarm` loads pages on demand and autoprewarm stores block identifiers, not contents ([pg_prewarm.c#pg_prewarm](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c#L76-L291), [autoprewarm.c#autoprewarm_database_main](../../../../raw/postgres-17/contrib/pg_prewarm/autoprewarm.c#L437-L561)).

### What changed since PostgreSQL 12

Scoped to mechanisms that change the pros and cons at 256 GiB. Each row is attributed to the commit in this checkout's own history and to the first release tag that contains it.

| First in | Change | Why it matters at 256 GiB | Commit |
|---|---|---|---|
| 13 | `pg_shmem_allocations` view | the pool's own bookkeeping became inspectable, which is how the per-buffer table above was measured | `ed10f32e37e` |
| 13 | `DropRelationBuffers()` takes a fork array, so a truncation scans the pool **once** instead of once per fork | this is the single biggest large-pool change in the range: in v12 a `VACUUM` truncation that touched main, fsm and vm walked 33.5 M headers three times, and the commit message names `shared_buffers` being large as the motivation | `6d05086c0a79` |
| 13 | `FlushRelationsAllBuffers()` added | a sixth full-pool scan exists that v12 did not have | `cb2fd7eac28` |
| 14 | `BUF_DROP_FULL_SCAN_THRESHOLD` plus `smgrnblocks_cached()` | drop and truncate can use targeted lookups, but only with **every** fork's size cached **and** fewer blocks to invalidate than `NBuffers / 32`, and `smgrnblocks_cached()` answers only `InRecovery` - so a standby's replay of a *small* drop skips the scan, a standby's replay of a big one does not, and a primary never does | `d6ad34f3410`, `bea449c635c` |
| 14 | per-buffer I/O locks replaced by condition variables | per-buffer overhead for that array is the measured 16 bytes, not an `LWLock` | `d87251048a0` |
| 14 | `huge_page_size` GUC | 1 GiB pages become selectable, taking the 256 GiB mapping from 133,750 page reservations to 262 | `d2bddc2500f` |
| 14 | `checkpoint_completion_target` default 0.5 -> 0.9 | the larger dirty set a big pool permits is spread over more of the interval by default | `bbcc4eb2e08` |
| 15 | `shared_memory_size` and `shared_memory_size_in_huge_pages` | the sizing of an unallocatable pool can be read before committing to it, with `postgres -C`, which is the right operational move before a restart at 256 GiB even though this page's 4 GiB cap kept it from asking | `bd1788051b0`, `43c1c4f65ea` |
| 15 | built-in `shared_buffers` default 8 MB -> 128 MB | the baseline this decision is compared against moved | `f7bda63a487` |
| 15 | `CREATE DATABASE ... STRATEGY wal_log`, and the default | the default path copies block by block through the pool instead of forcing the file-copy strategy's checkpoints | `9c08aea6a30` |
| 15 | cumulative statistics moved into shared memory | prerequisite for the per-context I/O view below | `5891c7a8ed8` |
| 16 | `pg_stat_io` | evictions, reuses, hits and per-context reads became countable, so "is the pool too small" stops being a guess | `a9c70b46dbe` |
| 16 | `vacuum_buffer_usage_limit` and `GetAccessStrategyWithSize()` | `VACUUM`'s ring is configurable and capped at `NBuffers / 8`, so a big pool can be spent on maintenance deliberately; the default was raised to 2 MB in 17 | `1cbbee03385`, `98f320eb2ef` |
| 16 | `pg_buffercache_summary()` and `pg_buffercache_usage_counts()` | a pool census without the `NBuffers`-sized allocation: measured 1.8 ms against 103.1 ms at 524,288 buffers | `2589434ae0f`, `f3fa31327ec` |
| 16 | `PG_IO_ALIGN_SIZE` | `Buffer Blocks` carries 4 kB of alignment padding, and direct I/O becomes possible | `faeedbcefd4` |
| 16 | `debug_io_direct` | double buffering becomes visible as a choice, though the documentation keeps it to developer testing; measured at 511.7 ms against 31.2 ms of `read_time` on the same scan | `319bae9a8da` |
| 16 | `LimitAdditionalPins()` | per-backend batch pin budget derived from `NBuffers`, so a large pool raises the ceiling on batched work | `31966b151e6` |
| 17 | read streams, vectored reads, `io_combine_limit`, and strategy pin limits | misses are issued as combined reads with adaptive look-ahead, and ring users cannot pin their way out of the ring | `b5a9b18cd0b`, `210622c60e1`, `b7b0f3f2724`, `041b96802ef`, `3bd8439ed62` |
| 17 | SLRU auto-sizing GUCs and bank-partitioned SLRU locks | `transaction_buffers` and two others now scale with `shared_buffers` to a 1024-block cap and can be raised to 1 GiB | `53c2a97a926` |
| 17 | `pg_stat_checkpointer`, and `buffers_backend`/`buffers_backend_fsync` removed from `pg_stat_bgwriter` | monitoring built on v12's `pg_stat_bgwriter` columns breaks; the replacement is `pg_stat_io` | `96f052613f3`, `74604a37f2f` |
| 17 | `pg_buffercache_evict()` | a pool can be perturbed deliberately under test | `13453eedd3f` |
| 17 | `huge_pages_status` | whether the running server actually got huge pages is now readable | `a14354cac0e` |
| 17.6 | `MAX_CHECKPOINT_REQUESTS` caps the sync-request queue at 10,000,000 slots | above a 76.3 GiB pool the queue stops growing, which takes 32 bytes per buffer off the marginal cost of every further buffer | `13559de9538`, `60589003480` |
| 17.6 | autoprewarm's dump array may exceed 1 GiB (`MCXT_ALLOC_HUGE`) | before this, a preloaded `pg_prewarm` could not dump a pool over about 53.7 million buffers at all: the `palloc` exceeded `MaxAllocSize` and the dump failed outright. A 256 GiB pool is under that line, a 512 GiB pool is not | `e4b8f925a929` |

### What did not change since PostgreSQL 12

Verified against this checkout's history over the range `REL_12_2..786db8dcf16`; every claim below is cited to the v17 source, and the v12 side is a history statement, not a citation.

- The GUC itself: `PGC_POSTMASTER`, floor 16, ceiling `INT_MAX / 2`, and the same overflow comment ([guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2257-L2270)).
- The `NBuffers / 4` bulk-read and synchronised-scan threshold ([heapam.c#initscan](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L408-L527)).
- The 256 kB bulk-read ring and the 128 kB sync-scan report interval ([freelist.c#GetAccessStrategy](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L541-L574), [syncscan.c:73-83](../../../../raw/postgres-17/src/backend/access/common/syncscan.c#L73-L83)).
- `BM_MAX_USAGE_COUNT` = 5 and the shape of the clock sweep ([buf_internals.h:71-79](../../../../raw/postgres-17/src/include/storage/buf_internals.h#L71-L79), [freelist.c#StrategyGetBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L196-L357)).
- `NUM_BUFFER_PARTITIONS` = 128 and the single `buffer_strategy_lock` ([lwlock.h:87-93](../../../../raw/postgres-17/src/include/storage/lwlock.h#L87-L93), [freelist.c:30-62](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L30-L62)).
- `BufferSync()`'s full-header scan per checkpoint ([bufmgr.c#BufferSync](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2931-L3193)).
- `bgwriter_delay` 200 ms and `bgwriter_lru_maxpages` 100, neither derived from `NBuffers` ([guc_tables.c#bgwriter_delay](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3077-L3086), [guc_tables.c#bgwriter_lru_maxpages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3088-L3096)).
- The documentation's 25 % starting point and 40 % caution ([config.sgml#shared_buffers](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L1650-L1692)).
- No NUMA awareness, and no test that exercises a large pool.

### Settings that move with it, and their apply scope

| Setting | v17 default | Context | Apply scope | Relevance at 256 GiB |
|---|---|---|---|---|
| `shared_buffers` | 16384 blocks (128 MB) | `PGC_POSTMASTER` | **restart** | the decision itself |
| `huge_pages` | `try` | `PGC_POSTMASTER` | **restart** | `on` turns a missing reservation into a failure to start |
| `huge_page_size` | 0 (platform default) | `PGC_POSTMASTER` | **restart** | 1 GiB pages cut the reservation count from 133,750 to 262 |
| `huge_pages_status` | n/a, read-only | `PGC_INTERNAL` | read-only | whether the running server got them |
| `shared_memory_size`, `shared_memory_size_in_huge_pages` | n/a, read-only | `PGC_INTERNAL` | read-only, and readable via `postgres -C` before starting | plan the allocation |
| `max_wal_size` | 1024 MB | `PGC_SIGHUP` | **reload** | the docs tie a larger pool to raising this |
| `checkpoint_timeout`, `checkpoint_completion_target` | 300 s, 0.9 | `PGC_SIGHUP` | **reload** | spread the larger dirty set |
| `checkpoint_flush_after` | 32 blocks where the platform supports it, else 0 ([pg_config_manual.h:170-180](../../../../raw/postgres-17/src/include/pg_config_manual.h#L170-L180)) | `PGC_SIGHUP` | **reload** | writeback pacing during the checkpoint |
| `bgwriter_delay`, `bgwriter_lru_maxpages`, `bgwriter_lru_multiplier` | 200 ms, 100, 2.0 | `PGC_SIGHUP` | **reload** | the only way to make background cleaning scale with the pool |
| `backend_flush_after` | 0 (off) | `PGC_USERSET` | session/transaction | pacing for the writes backends do themselves ([guc_tables.c#backend_flush_after](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3152-L3161)) |
| `vacuum_buffer_usage_limit` | 2048 kB | `PGC_USERSET` | session/transaction, or per command via `BUFFER_USAGE_LIMIT` | spend pool on maintenance; 0 or 128 kB to 16 GiB, then capped at `NBuffers / 8` |
| `io_combine_limit` | 16 blocks (128 kB) | `PGC_USERSET` | session/transaction | size of a combined read on a miss |
| `effective_io_concurrency`, `maintenance_io_concurrency` | 1 and 10 where the build supports prefetching, 0 and 0 otherwise | `PGC_USERSET` | session/transaction | look-ahead depth of the read streams ([bufmgr.h:157-166](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L157-L166)) |
| `effective_cache_size` | 524288 blocks (4 GB) | `PGC_USERSET` | session/transaction | the planner's cache estimate; it never reads `NBuffers` |
| `temp_buffers` | 1024 blocks | `PGC_USERSET` | session, before first temp use | temp tables do not use the pool |
| `transaction_buffers`, `commit_timestamp_buffers`, `subtransaction_buffers` | 0 = auto | `PGC_POSTMASTER` | **restart** | auto-size to `NBuffers / 512`, capped at 1024 blocks |
| `multixact_offset_buffers`, `multixact_member_buffers`, `notify_buffers`, `serializable_buffers` | 16, 32, 16, 32 | `PGC_POSTMASTER` | **restart** | fixed; a big pool does not raise them |
| `debug_io_direct` | empty | `PGC_POSTMASTER` | **restart** | removes the OS cache from the data path; a developer option |
| `track_io_timing` | off | `PGC_SUSET` | reload, or session for a superuser | needed for `read_time`/`write_time` in `pg_stat_io` |
| `pg_prewarm.autoprewarm` | on | `PGC_POSTMASTER` | **restart** | whether the `NBuffers`-sized dump worker runs at all |
| `pg_prewarm.autoprewarm_interval` | 300 s | `PGC_SIGHUP` | **reload** | how often it repeats |

Contexts are read from the pinned GUC table: [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2257-L2270), [guc_tables.c#vacuum_buffer_usage_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2272-L2281), [guc_tables.c#shared_memory_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2283-L2292), [guc_tables.c#commit_timestamp_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2305-L2314), [guc_tables.c#subtransaction_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2360-L2369), [guc_tables.c#transaction_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2371-L2380), [guc_tables.c#max_wal_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2842-L2852), [guc_tables.c#checkpoint_flush_after](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2880-L2889), [guc_tables.c#io_combine_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3138-L3150), [guc_tables.c#backend_flush_after](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3152-L3161), [guc_tables.c#checkpoint_completion_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3916-L3924), [guc_tables.c#huge_pages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L5057-L5065), [guc_tables.c#huge_pages_status](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L5067-L5076).

### What to look at before and after the change

Verified against the pinned catalogs. Each statement sets session-scoped timeouts first; both are `PGC_USERSET`.

```sql
SET /* wiki_shbuf_session */ statement_timeout = '30s';
SET /* wiki_shbuf_session */ lock_timeout = '5s';

-- 1. What the current pool costs, and what the proposed one would.
SELECT /* wiki_shbuf_sizing */ name, setting, unit
FROM pg_settings
WHERE name IN ('shared_buffers', 'shared_memory_size',
               'shared_memory_size_in_huge_pages', 'huge_pages',
               'huge_pages_status', 'huge_page_size');

-- 2. Where the pool's shared memory actually goes.
SELECT /* wiki_shbuf_shmem */ coalesce(name, '<anonymous>') AS name,
       pg_size_pretty(size) AS size
FROM pg_shmem_allocations
ORDER BY size DESC
LIMIT 15;

-- 3. Is the pool too small?  Read these columns together, and read them for
--    what they count.  A high hits/(hits+reads) ratio in the 'normal'
--    context is the pool doing its job.  'evictions' and 'reuses' count
--    claiming a valid victim buffer, clean or dirty, so neither is a write
--    count: 'reuses' in a 'bulkread' or 'vacuum' context is a strategy ring
--    recycling its own pages and is expected, whatever the pool size.  The
--    foreground write a too-small pool forces is 'writes' on the
--    client-backend row, which is what v12's pg_stat_bgwriter.buffers_backend
--    used to report before v17 removed it.
SELECT /* wiki_shbuf_io */ backend_type, object, context,
       reads, hits, evictions, reuses, writes, fsyncs
FROM pg_stat_io
WHERE reads > 0 OR writes > 0 OR evictions > 0
ORDER BY backend_type, context;

-- 4. A pool census that does not allocate one record per buffer.
SELECT /* wiki_shbuf_census */ * FROM pg_buffercache_summary();
SELECT /* wiki_shbuf_usage */ * FROM pg_buffercache_usage_counts();

-- 5. Checkpoint pressure.  num_requested counts every checkpoint that
--    arrived as a request rather than on checkpoint_timeout, which includes
--    max_wal_size pressure but also every manual CHECKPOINT, every
--    CREATE/DROP DATABASE and a shutdown - so a high count is a reason to
--    look for the cause, not proof of WAL pressure.  buffers_written counts
--    the buffers the checkpointer actually wrote, not the dirty set
--    BufferSync() marked at the start: pages already written by a backend or
--    the background writer in between are not counted here.
SELECT /* wiki_shbuf_ckpt */ num_timed, num_requested, buffers_written,
       write_time, sync_time, stats_reset
FROM pg_stat_checkpointer;
```

Before starting a server with the new value, size it without allocating it:

```bash
postgres -D "$PGDATA" -c shared_buffers=256GB -C shared_memory_size
postgres -D "$PGDATA" -c shared_buffers=256GB -C shared_memory_size_in_huge_pages
```

Sources for the two counter comments above. `evictions` and `reuses` are counted for every `BM_VALID` victim, outside the dirty branch that writes ([bufmgr.c:2061-2081](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2061-L2081)). `num_requested` is incremented once per checkpoint whose flags carried `CHECKPOINT_REQUESTED` ([checkpointer.c:424-431](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L424-L431), [checkpointer.c#RequestCheckpoint](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L946-L1010)), and the requesters include a manual `CHECKPOINT` ([utility.c:942-954](../../../../raw/postgres-17/src/backend/tcop/utility.c#L942-L954)), `max_wal_size` pressure through `CHECKPOINT_CAUSE_XLOG` ([xlog.c:2502-2508](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L2502-L2508)), `CREATE DATABASE`, `DROP DATABASE` and `ALTER DATABASE ... SET TABLESPACE` ([dbcommands.c:566-568](../../../../raw/postgres-17/src/backend/commands/dbcommands.c#L566-L568), [dbcommands.c:1830-1834](../../../../raw/postgres-17/src/backend/commands/dbcommands.c#L1830-L1834), [dbcommands.c:2083-2085](../../../../raw/postgres-17/src/backend/commands/dbcommands.c#L2083-L2085)), `DROP TABLESPACE` ([tablespace.c:497-503](../../../../raw/postgres-17/src/backend/commands/tablespace.c#L497-L503)), and shutdown ([checkpointer.c:595-602](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L595-L602)). `buffers_written` is incremented only when `SyncOneBuffer()` reports it wrote the buffer ([bufmgr.c:3139-3147](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3139-L3147)).

Privileges: `pg_shmem_allocations` is revoked from `PUBLIC` and granted to `pg_read_all_stats` ([system_views.sql:652-658](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L652-L658)); the `pg_buffercache` view and `pg_buffercache_pages()` are granted to `pg_monitor` ([pg_buffercache--1.2--1.3.sql:1-7](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache--1.2--1.3.sql#L1-L7)), as are `pg_buffercache_summary()` and `pg_buffercache_usage_counts()` ([pg_buffercache--1.3--1.4.sql:24-28](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache--1.3--1.4.sql#L24-L28)); and `pg_buffercache_evict()` checks `superuser()` in C, with no grant of its own ([pg_buffercache_pages.c#pg_buffercache_evict](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache_pages.c#L362-L375), [pg_buffercache--1.4--1.5.sql:1-6](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache--1.4--1.5.sql#L1-L6)).

### Decision guide

Reasoning only from the mechanisms filed above.

1. **If the hot working set fits in 256 GiB and the rest of the database is much larger**, the pool is doing what it is for: hits avoid `smgr` entirely, and hot pages hold `usage_count` against the sweep. The costs you accept are the per-checkpoint header scan, the `DROP`/`TRUNCATE` scans, and a ~2.4 s restart.
2. **If the whole database fits in 256 GiB**, the second copy in the OS cache is buying less than it would otherwise - but that is not a reason to reach for `debug_io_direct`. The shipped documentation says the feature "reduces performance" and "is intended for developer testing only" ([config.sgml#debug_io_direct](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L11621-L11624)), and the measured 511.7 ms against 31.2 ms above is this host's page cache being removed, not a benefit being found. This page makes no recommendation to set it.
3. **If the workload drops or truncates relations frequently** - partition rotation, `REINDEX`, temp-to-permanent churn, an ETL that recreates tables - price it: about 0.22 s per `DROP` and 0.32 s per `TRUNCATE` at this size, and batching many drops into one transaction measured 11x cheaper than one transaction each. The fork count does not multiply it.
4. **If sequential scans of tables under 64 GiB matter**, remember the `NBuffers / 4` line: below it a scan uses the default strategy, so its pages compete with the working set on equal terms instead of cycling through a 256 kB ring, and synchronised scanning is off so two concurrent scans do not share a scan position. They do still share the *pages*: an ordinary `BufferAlloc()` lookup finds a block another backend already loaded, whatever `synchronize_seqscans` says ([bufmgr.c#BufferAlloc](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1609-L1664)). And one such scan cannot evict more than its own size: it introduces at most the relation's own distinct pages.
5. **If a monitoring job selects from `pg_buffercache`**, move it to `pg_buffercache_summary()` before the pool grows.
6. **If autoprewarm is preloaded**, decide the interval deliberately; the dump repeats an `NBuffers`-sized allocation and a full header walk, and on anything before 17.6 that allocation fails outright above about 53.7 million buffers.
7. **Before the restart**, price the pool with `postgres -C shared_memory_size` and reserve huge pages against `shared_memory_size_in_huge_pages`, not against `shared_buffers`. Remember two things about that: `-C` exits before shared memory is created, so it proves the sizing arithmetic and nothing about whether the server will start; and `huge_pages = on` turns a missing reservation into a failure to start rather than a fallback.
8. **What source cannot tell you**: whether 256 GiB beats 128 GiB for your queries. Nothing in the tree models that, and the documentation's own guidance stops at 25 % with a caution at 40 %.

### How this was measured, and what the measurements cannot say

- Every number above comes from [the script filed below](#measurement-script), run in one invocation on 2026-09-17 against server version **17.11**, built from pin `786db8dcf168bd9df8f55047337525ac19118b1c` (`REL_17_11-7-g786db8dcf16`).
- Platform: Linux 6.18.33.2-microsoft-standard-WSL2, x86_64, `MemTotal` 32,583,848 kB, `Hugepagesize` 2048 kB, `HugePages_Total` 0, `vm.overcommit_memory` 0. Build: `block_size` 8192, `wal_block_size` 8192, `segment_size` 131072 blocks, `MAXIMUM_ALIGNOF` 8, `data_checksums` off, `max_connections` 100.
- The build passed its own suites in the same run: core regression **All 225 tests passed**, `contrib/pg_buffercache` **All 1 tests passed**, both checked on exit status as well as on the result line. The measurement cluster's log contains **0** `ERROR` or `FATAL` lines; the deliberate failure probes run against a separate data directory.
- **The script may not name a `shared_buffers` value above 4 GiB** - 524,288 blocks - anywhere, in a running server or in a `postgres -C` probe. One guard function converts every value to blocks and refuses anything larger, and it runs over `BASE_SB` and `POOLS` before the first stage starts. The pool ladder is therefore 1, 2, 3 and 4 GiB, and the largest pool any timing on this page used is 524,288 buffers.
- **No 256 GiB figure on this page is a measurement.** Each is either the validated arithmetic model of [the subsection above](#how-the-256-gib-figures-were-computed-under-a-4-gib-test-cap) or a labelled linear extrapolation of a slope measured between 131,072 and 524,288 buffers - a 64x extrapolation from a 4x range.
- Timings are taken inside the server with `clock_timestamp()` around each statement, accumulated in a local array, and written to the results table only after the last timed statement, so the timer never dirties a page between two measured statements. The `DROP`/`TRUNCATE` numbers include the commit, because that is where the buffer-pool pass happens, and run with `synchronous_commit = off` so the WAL flush wait is not inside the interval.
- The cluster ran with one connection at a time and no concurrent load, so every figure is a single-backend, uncontended figure. Contention on the 128 mapping partitions and on `buffer_strategy_lock` is exactly what this setup cannot measure.
- Both clusters were stopped and the sandbox deleted before this page was filed. The `stop` stage asserts it: no `postmaster.pid` in either data directory, no `postgres` process referring to the sandbox, and no Unix socket left for port 55418 or 55419. An `EXIT` trap runs the same shutdown if any stage dies.

## Measurement Script

### Usage

| Item | Detail |
|---|---|
| Purpose | produces every measured number on this page: the `-C` sizing sweep up to the 4 GiB cap, the mapping-table bucket step, the exact `pg_shmem_allocations` segment totals and per-buffer costs, SLRU auto-sizing, the fitted shared-memory model and the 256 GiB arithmetic it yields, server start per pool size, `CHECKPOINT` duration with its dirty and written counts, `DROP`/`TRUNCATE` full-pool passes with the fork census, the `NBuffers / 4` threshold, the `VACUUM` ring, `io_combine_limit`, the three `pg_buffercache` readers, and the range, startup and mapping error paths |
| Invocation | `bash shbuf.sh` from the repository root, with the script saved anywhere; it resolves everything from `WIKI_ROOT`, which defaults to `$PWD` |
| Stages | `build check sizing cluster shmem model startup ckpt drop strategy vacring iocombine bcache errors summary stop` in that default order, plus `clean` on request. Select stages as arguments: `bash shbuf.sh sizing shmem`. Each stage is idempotent: `build` skips when the binary exists, `cluster` skips `initdb` when the data directory exists, and the timing stages delete their own previous rows before re-measuring. Any stage that fails ends the run with a non-zero exit status |
| Environment | `WIKI_ROOT` (`$PWD`), `SRC` (`$WIKI_ROOT/raw/postgres-17`), `SANDBOX` (`$WIKI_ROOT/.wiki-runtime/tmp/shbuf`), `PORT` (`55418`, and `PORT + 1` for the probe cluster), `JOBS` (`12`), `MAX_SB_BLOCKS` (`524288`, the 4 GiB cap), `BASE_SB` (`1GB`), `POOLS` (`1GB 2GB 3GB 4GB`), `ROWS_BELOW` (`2000000`), `ROWS_ABOVE` (`4000000`), `TRIALS` (`3`), `STARTUP_TRIALS` (`10`), `DROPS` (`30`) |
| Prerequisites | a C toolchain, `make`, `flex`, `bison`, `perl`, readline and zlib headers, and ICU discoverable through `pkg-config` because the tree is configured `--with-icu`; `initdb` runs with `--locale=C --encoding=UTF8`; about 6 GiB of free RAM for the 4 GiB pool stages and about 8 GiB of disk for the build, install and data directories |
| Output | one file per stage under `$SANDBOX/out/`, and `$SANDBOX/out/summary.txt`, which concatenates all of them plus the test-suite result lines and an `ERROR`/`FATAL` audit of the cluster log. Read `summary.txt` first |
| Runtime | about 12 minutes for a full run on 22 cores, of which roughly 1 minute is the build and 4 minutes `make check`; a re-run from a built tree with `sizing cluster shmem model startup ckpt drop strategy vacring iocombine bcache errors summary` is about 7 minutes |
| Cleanup | `bash shbuf.sh clean` stops both clusters and deletes `$SANDBOX`. The `stop` stage, which runs by default, stops both and asserts that no `postmaster.pid` is left in either data directory, no `postgres` process refers to the sandbox, and no Unix socket file is left for `$PORT` or `$PORT + 1`. An `EXIT` trap stops both clusters however the run ends, including through `die` |

Isolation: the pinned checkout is read only, the build is out of tree, each of the two clusters has its own data directory and port inside one sandbox socket directory, and every fixture table is disposable. GUC apply scopes are named in the script's own header, every `psql` call runs `-X -v ON_ERROR_STOP=1` with session-scoped `statement_timeout` and `lock_timeout`, and `guard_sb()` enforces the 4 GiB cap on every server start and every `postgres -C` probe.

Last run: 2026-09-17, server 17.11 from pin `786db8dcf168bd9df8f55047337525ac19118b1c`, Linux 6.18.33.2-microsoft-standard-WSL2 x86_64, `block_size` 8192, `MAXIMUM_ALIGNOF` 8, `data_checksums` off, `max_connections` 100, `Hugepagesize` 2048 kB with `HugePages_Total` 0. The 1,111-line block below is the file that ran.

### The script

```bash
#!/usr/bin/env bash
# Measurements for the wiki page
#   wiki/v17/questions/storage-and-vacuum/very-large-shared-buffers.md
#
# What this measures, and why it is safe to run
# ---------------------------------------------
# Every number that page reports about a running v17 server comes from this
# script.  It builds the pinned PostgreSQL 17 checkout out of tree and then
# measures the pool-size-dependent code paths at pool sizes this host may
# run: exact shared-memory totals from pg_shmem_allocations, SLRU
# auto-sizing, server start time, checkpoint duration over a clean pool,
# DROP/TRUNCATE full-pool passes, the NBuffers/4 bulk-read threshold, the
# VACUUM ring, io_combine_limit, the three pg_buffercache readers, and the
# startup and mapping error paths.
#
# A 4 GiB cap on every shared_buffers this script may name
# --------------------------------------------------------
# MAX_SB_BLOCKS (524,288 blocks = 4 GiB at BLCKSZ 8192) caps every
# shared_buffers value this script uses, and guard_sb() enforces it on the
# way into a running server *and* on the way into a non-allocating
# "postgres -C" probe.  No stage may name a larger value.  The consequence
# is deliberate: a 256 GiB pool is never sized by the binary here, so this
# script cannot report a measured figure for one.  Instead the model stage
# fits the pinned shared-memory formulas to the exact byte totals measured
# at 1-4 GiB, checks the fit at every measured size, and then evaluates the
# same formulas at 33,554,432 buffers.  Those 256 GiB figures are arithmetic
# on validated formulas, and the page labels them as such.
#
# Timings are taken inside the server with clock_timestamp() around each
# statement and accumulated in a local array, so the timer's own INSERT
# never lands between two timed statements.  Server start time is read from
# the server's own log timestamps, which carry milliseconds.
#
# The pinned checkout under raw/postgres-17 is read only.  Everything this
# script writes lives under $SANDBOX, the clean stage deletes it, and an
# EXIT trap stops both clusters however the run ends.  The two clusters it
# starts have their own data directories, their own socket directory and
# non-default ports; neither is a cluster anyone else named.  Every fixture
# is disposable: the script creates and drops its own tables in its own
# database.
#
# Usage, from the repository root:
#   bash .wiki-runtime/tmp/shbuf.sh                 # every stage, in order
#   bash .wiki-runtime/tmp/shbuf.sh sizing shmem    # selected stages
#   bash .wiki-runtime/tmp/shbuf.sh clean           # stop, delete the sandbox
#
# Stages, in default order:
#   build check sizing cluster shmem model startup ckpt drop strategy
#   vacring iocombine bcache errors summary stop
# and, on request only: clean
#
# Any stage that fails ends the run with a non-zero exit status.
#
# Environment: WIKI_ROOT SRC SANDBOX PORT JOBS MAX_SB_BLOCKS BASE_SB POOLS
#              ROWS_BELOW ROWS_ABOVE TRIALS STARTUP_TRIALS DROPS
#
# GUC apply scopes, read from the pinned v17 GUC table:
#   shared_buffers, huge_pages, huge_page_size, debug_io_direct, wal_buffers,
#   transaction_buffers, commit_timestamp_buffers, subtransaction_buffers
#       -> PGC_POSTMASTER, restart.  This script restarts for every value.
#   bgwriter_delay, bgwriter_lru_maxpages -> PGC_SIGHUP, reload.  Read only.
#   track_io_timing -> PGC_SUSET (guc_tables.c:1421): reload, or session
#       scope for a superuser.  This script passes it at server start.
#   vacuum_buffer_usage_limit, io_combine_limit, backend_flush_after,
#   max_parallel_workers_per_gather, synchronous_commit, statement_timeout,
#   lock_timeout -> PGC_USERSET, session/transaction scope.
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
SRC="${SRC:-$WIKI_ROOT/raw/postgres-17}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/shbuf}"
PORT="${PORT:-55418}"
JOBS="${JOBS:-12}"
MAX_SB_BLOCKS="${MAX_SB_BLOCKS:-524288}"
BASE_SB="${BASE_SB:-1GB}"
POOLS="${POOLS:-1GB 2GB 3GB 4GB}"
ROWS_BELOW="${ROWS_BELOW:-2000000}"
ROWS_ABOVE="${ROWS_ABOVE:-4000000}"
TRIALS="${TRIALS:-3}"
STARTUP_TRIALS="${STARTUP_TRIALS:-10}"
DROPS="${DROPS:-30}"

BUILD="$SANDBOX/build17"; INST="$SANDBOX/install17"; DATA="$SANDBOX/data17"
EDATA="$SANDBOX/dataerr"; OUT="$SANDBOX/out"; SOCK="$SANDBOX/sock17"
BIN="$INST/bin"; DB=shbuf; EPORT=$(( PORT + 1 ))
export PGPORT="$PORT" PGHOST="$SOCK" PGDATABASE="$DB" PGUSER=postgres

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# The 4 GiB cap.  sb_blocks() converts a shared_buffers spelling to blocks;
# guard_sb() refuses anything above MAX_SB_BLOCKS.  Every server start and
# every "postgres -C" probe below goes through one of these.
sb_blocks() {
  local v="$1" n u
  n=${v%%[!0-9]*}; u=${v#"$n"}
  [ -n "$n" ] || { printf 'x'; return 0; }
  case "$u" in
    '')     printf '%s' "$n" ;;
    B)      printf '%s' "$(( n / 8192 ))" ;;
    kB|KB)  printf '%s' "$(( n / 8 ))" ;;
    MB)     printf '%s' "$(( n * 128 ))" ;;
    GB)     printf '%s' "$(( n * 131072 ))" ;;
    TB)     printf '%s' "$(( n * 134217728 ))" ;;
    *)      printf 'x' ;;
  esac
}

guard_sb() {
  local v="$1" b
  b=$(sb_blocks "$v")
  case "$b" in ''|*[!0-9]*) die "cannot parse shared_buffers value '$v'" ;; esac
  [ "$b" -le "$MAX_SB_BLOCKS" ] \
    || die "shared_buffers=$v is $b blocks, above this script's $MAX_SB_BLOCKS-block (4 GiB) cap"
  printf '%s' "$b"
}

# -X ignores ~/.psqlrc so a stray file cannot change a result; ON_ERROR_STOP
# means no failed statement passes silently.  statement_timeout and
# lock_timeout are PGC_USERSET, so passing them through libpq applies them at
# session scope, with no reload and no restart.
SESSION_OPTS="-c statement_timeout=10min -c lock_timeout=60s"
pg()  { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -v ON_ERROR_STOP=1 "$@"; }
pgq() { pg -At "$@"; }

running() { "$BIN/pg_ctl" -D "$DATA" status >/dev/null 2>&1; }
probe_running() { "$BIN/pg_ctl" -D "$EDATA" status >/dev/null 2>&1; }
stop_server() { running && "$BIN/pg_ctl" -D "$DATA" -m fast -w stop >/dev/null 2>&1; return 0; }
stop_probe()  { probe_running && "$BIN/pg_ctl" -D "$EDATA" -m fast -w stop >/dev/null 2>&1; return 0; }

# Teardown is guaranteed, not left to the happy path: die(), an unhandled
# failure and a signal all run this.  It stops both clusters and never
# deletes anything, so a failed run keeps its results for inspection.
CLEANED=0
on_exit() {
  local st=$?
  if [ "$CLEANED" = 0 ] && [ -x "$BIN/pg_ctl" ]; then
    stop_server; stop_probe
  fi
  exit "$st"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Restart the measurement cluster with one shared_buffers value plus any extra
# "name=value" options.  shared_buffers is PGC_POSTMASTER, so every size
# change below is a restart, not a reload.
start_with() {
  local sb="$1"; shift
  local log="${SERVER_LOG:-$OUT/server.log}"
  guard_sb "$sb" >/dev/null
  local o="-p $PORT -k $SOCK -c shared_buffers=$sb -c listen_addresses='' -c logging_collector=off"
  for extra in "$@"; do o="$o -c $extra"; done
  stop_server
  "$BIN/pg_ctl" -D "$DATA" -l "$log" -w -o "$o" start >/dev/null 2>&1 \
    || die "server did not start with shared_buffers=$sb (see $log)"
}

nbuffers() { pgq -c "SELECT /* wiki_shbuf_nbuffers */ setting::bigint FROM pg_settings WHERE name = 'shared_buffers';"; }

# "postgres -C <runtime-computed GUC>" reaches the shared-memory sizing code
# and exits at postmaster.c:964-971, before CreateSharedMemoryAndSemaphores()
# at postmaster.c:980.  It therefore prices a pool without mapping one - but
# it proves nothing about whether that pool would start, which is why the
# errors stage starts a real server at the floor instead of asking -C.
size_c() {   # size_c <shared_buffers> <guc> [extra -c options...]
  local sb="$1" guc="$2"; shift 2
  guard_sb "$sb" >/dev/null
  "$BIN/postgres" -D "$EDATA" -c shared_buffers="$sb" "$@" -C "$guc" 2>/dev/null | tail -1
}

# --------------------------------------------------------------------------
# Server-side stopwatches.  Both accumulate elapsed microseconds in a local
# array and write every row *after* the loop, so the timer's own INSERT can
# never dirty a page or emit WAL between two timed statements.  That matters
# most for the ckpt stage, where a row inserted between checkpoints would
# give the next checkpoint real work to do.
install_timer() {
  pg -q <<'SQL' || die "could not install the timer"
CREATE /* wiki_shbuf_fixture */ TABLE IF NOT EXISTS meas
  (stage text, pool bigint, label text, i int, us bigint);
CREATE OR REPLACE /* wiki_shbuf_fixture */ FUNCTION timeit
  (p_stage text, p_label text, p_stmt text, p_n int, p_fmt boolean DEFAULT false)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  i  int;
  t0 timestamptz;
  t1 timestamptz;
  s  text;
  nb bigint := (SELECT setting::bigint FROM pg_settings WHERE name = 'shared_buffers');
  us bigint[] := '{}';
BEGIN
  FOR i IN 1..p_n LOOP
    s := CASE WHEN p_fmt THEN format(p_stmt, i) ELSE p_stmt END;
    t0 := clock_timestamp();
    EXECUTE s;
    t1 := clock_timestamp();
    us := us || (extract(epoch FROM (t1 - t0)) * 1000000)::bigint;
  END LOOP;
  INSERT INTO meas
    SELECT p_stage, nb, p_label, g, us[g] FROM generate_subscripts(us, 1) g;
END
$fn$;
-- timeit() cannot time DROP or TRUNCATE: the buffer-pool work for a dropped
-- or replaced relfilenode is queued as a pending delete and performed by
-- smgrDoPendingDeletes() at commit, which is after timeit()'s stopwatch
-- stops.  timeit_tx() is a procedure, so it can COMMIT inside the loop and
-- put the commit inside the measured interval.  Its rows are also written
-- only after the loop; a plpgsql procedure's local variables survive the
-- COMMITs in between.
CREATE OR REPLACE /* wiki_shbuf_fixture */ PROCEDURE timeit_tx
  (p_stage text, p_label text, p_stmt text, p_n int, p_fmt boolean DEFAULT false)
LANGUAGE plpgsql AS $pr$
DECLARE
  i  int;
  t0 timestamptz;
  t1 timestamptz;
  s  text;
  nb bigint := (SELECT setting::bigint FROM pg_settings WHERE name = 'shared_buffers');
  us bigint[] := '{}';
BEGIN
  FOR i IN 1..p_n LOOP
    s := CASE WHEN p_fmt THEN format(p_stmt, i) ELSE p_stmt END;
    t0 := clock_timestamp();
    EXECUTE s;
    COMMIT;
    t1 := clock_timestamp();
    us := us || (extract(epoch FROM (t1 - t0)) * 1000000)::bigint;
  END LOOP;
  INSERT INTO meas
    SELECT p_stage, nb, p_label, g, us[g] FROM generate_subscripts(us, 1) g;
  COMMIT;
END
$pr$;
SQL
}

report_meas() {   # report_meas <stage> <outfile>
  pg -c "SELECT /* wiki_shbuf_report */ pool AS pool_buffers, label,
                count(*) AS n, min(us) AS min_us,
                round(avg(us))::bigint AS avg_us,
                (percentile_cont(0.5) WITHIN GROUP (ORDER BY us))::bigint AS median_us,
                max(us) AS max_us
         FROM meas WHERE stage = '$1'
         GROUP BY pool, label ORDER BY label, pool;" >> "$2" 2>&1 \
    || die "could not report stage $1"
}

# below/above are the two seq-scan fixtures: one smaller and one larger than
# NBuffers/4 at BASE_SB.  Disposable, like every table here.
ensure_fixtures() {
  local n
  n=$(pgq -c "SELECT /* wiki_shbuf_fixture */ count(*) FROM pg_class WHERE relname IN ('below','above');") \
    || die "could not inspect the fixtures"
  [ "$n" = 2 ] && return 0
  # Each VACUUM gets its own -c: several statements inside one -c travel as a
  # single query, which puts them in an implicit transaction block, and VACUUM
  # cannot run there.
  pg -q -c "DROP /* wiki_shbuf_fixture */ TABLE IF EXISTS below, above;" \
        -c "CREATE /* wiki_shbuf_fixture */ TABLE below (id int, pad text);
            INSERT /* wiki_shbuf_fixture */ INTO below
              SELECT g, repeat('x', 40) FROM generate_series(1, $ROWS_BELOW) g;
            CREATE /* wiki_shbuf_fixture */ TABLE above (id int, pad text);
            INSERT /* wiki_shbuf_fixture */ INTO above
              SELECT g, repeat('x', 40) FROM generate_series(1, $ROWS_ABOVE) g;" \
        -c "VACUUM /* wiki_shbuf_fixture */ (ANALYZE) below, above;" >/dev/null \
    || die "could not build the below/above fixtures"
}

# --------------------------------------------------------------------------
stage_build() {
  say "build: configure the pinned checkout out of tree, install it and two contrib modules"
  mkdir -p "$BUILD" "$OUT" "$SOCK" || die "could not create the sandbox"
  if [ -x "$BIN/postgres" ]; then note "already built, skipping"; return 0; fi
  [ -x "$SRC/configure" ] || die "no pinned checkout at $SRC"
  ( cd "$BUILD" && "$SRC/configure" --prefix="$INST" --enable-debug \
      --with-icu --with-readline --with-zlib > configure.log 2>&1 ) \
    || { cp "$BUILD/configure.log" "$OUT/" 2>/dev/null; die "configure failed, see $OUT/configure.log"; }
  ( cd "$BUILD" && make -s -j "$JOBS" > make.log 2>&1 \
      && make -s install > install.log 2>&1 \
      && make -s -C contrib/pg_buffercache install >> install.log 2>&1 \
      && make -s -C contrib/pg_prewarm install >> install.log 2>&1 ) \
    || { cp "$BUILD"/{make,install}.log "$OUT/" 2>/dev/null; die "make failed, see $OUT/make.log"; }
  cp "$BUILD"/{configure,make,install}.log "$OUT/" 2>/dev/null
  "$BIN/postgres" --version > "$OUT/version.txt" 2>&1 || die "the built binary does not run"
  note "$(cat "$OUT/version.txt")"
}

# A suite that fails must fail the run: both the exit status of make and the
# suite's own result line are checked.
stage_check() {
  say "check: the build's own test suites"
  : > "$OUT/check_summary.txt"
  local rc line
  ( cd "$BUILD" && make -s check > "$OUT/check.log" 2>&1 ); rc=$?
  line=$(grep -E 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests failed' "$OUT/check.log" | tail -1)
  printf 'core regression: exit %s, %s\n' "$rc" "${line:-no result line}" >> "$OUT/check_summary.txt"
  [ "$rc" -eq 0 ] || die "core regression suite failed (exit $rc), see $OUT/check.log"
  case "$line" in *'tests passed'*) ;; *) die "core regression printed no pass line" ;; esac
  ( cd "$BUILD" && make -s -C contrib/pg_buffercache check > "$OUT/check_bcache.log" 2>&1 ); rc=$?
  line=$(grep -E 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests failed' "$OUT/check_bcache.log" | tail -1)
  printf 'pg_buffercache:  exit %s, %s\n' "$rc" "${line:-no result line}" >> "$OUT/check_summary.txt"
  [ "$rc" -eq 0 ] || die "pg_buffercache suite failed (exit $rc), see $OUT/check_bcache.log"
  case "$line" in *'tests passed'*) ;; *) die "pg_buffercache printed no pass line" ;; esac
  cat "$OUT/check_summary.txt" >&2
}

# --------------------------------------------------------------------------
# No server runs in this stage.  Every value named here is inside the 4 GiB
# cap, so the sweep stops at 4 GiB and the bucket-boundary probe uses the
# 2^18-block boundary rather than the 2^25-block one a 256 GiB pool sits on.
stage_sizing() {
  say "sizing: shared_memory_size for every pool up to the 4 GiB cap, with nothing allocated"
  mkdir -p "$OUT" || die "could not create $OUT"
  [ -f "$EDATA/PG_VERSION" ] || "$BIN/initdb" -D "$EDATA" -U postgres --locale=C --encoding=UTF8 \
    > "$OUT/initdb_err.log" 2>&1 || die "initdb for the probe directory failed"
  local sb nb smb hp
  : > "$OUT/sizing.txt"
  printf 'cap: %s blocks (%s MiB)\n\n' "$MAX_SB_BLOCKS" "$(( MAX_SB_BLOCKS / 128 ))" >> "$OUT/sizing.txt"
  printf '%-10s %12s %12s %14s %16s\n' setting blocks shmem_mb huge_2mb page_bytes >> "$OUT/sizing.txt"
  for sb in 128MB 256MB 512MB 1GB 2GB 3GB 4GB; do
    nb=$(size_c "$sb" shared_buffers)
    smb=$(size_c "$sb" shared_memory_size)
    hp=$(size_c "$sb" shared_memory_size_in_huge_pages)
    [ -n "$nb" ] && [ -n "$smb" ] || die "postgres -C produced no answer at $sb"
    printf '%-10s %12s %12s %14s %16s\n' "$sb" "$nb" "$smb" "$hp" "$(( nb * 8192 ))" >> "$OUT/sizing.txt"
  done

  # Marginal shared memory per buffer, from block-count pairs.  The pair form
  # cancels every fixed cost.  shared_memory_size is rounded up to whole MiB
  # (ipci.c:377-383), so a pair needs a wide span to be precise: 262,060
  # blocks keeps the rounding under 4.1 bytes per buffer.  The exact,
  # unrounded version of this measurement is in the shmem stage, which reads
  # whole bytes out of pg_shmem_allocations.
  local pair lo hi lomb himb
  printf '\nmarginal MiB-rounded bytes of shared memory per buffer, from block pairs\n' >> "$OUT/sizing.txt"
  printf '%-22s %10s %10s %16s %s\n' pair lo_mb hi_mb bytes_per_buffer note >> "$OUT/sizing.txt"
  for pair in 150000:250000:'inside the 2^18-bucket regime' \
              200000:300000:'crosses 2^18 buckets' \
              262100:524160:'inside the 2^19-bucket regime, widest span under the cap' \
              400000:500000:'inside the 2^19-bucket regime'; do
    lo=${pair%%:*}; hi=$(printf '%s' "$pair" | cut -d: -f2)
    lomb=$(size_c "$lo" shared_memory_size)
    himb=$(size_c "$hi" shared_memory_size)
    [ -n "$lomb" ] && [ -n "$himb" ] || die "postgres -C produced no answer for pair $lo:$hi"
    printf '%-22s %10s %10s %16s %s\n' "$lo->$hi" "$lomb" "$himb" \
      "$(( ( (himb - lomb) * 1048576 ) / (hi - lo) ))" "${pair##*:}" >> "$OUT/sizing.txt"
  done

  # The mapping table is sized NBuffers + NUM_BUFFER_PARTITIONS
  # (freelist.c:458) and hash_estimate_size() rounds that up to a power of
  # two bucket count (dynahash.c:795), so one buffer past a power of two
  # doubles the bucket segments and can double the directory.  A 256 GiB pool
  # is 2^25 blocks and lands one NUM_BUFFER_PARTITIONS step past the
  # boundary; this probe shows the same step at 2^18, which is inside the cap.
  local b prev=0
  printf '\nthe buffer mapping table step around 2^18 blocks\n' >> "$OUT/sizing.txt"
  printf '%-14s %12s %12s %s\n' blocks shmem_mb delta_mb note >> "$OUT/sizing.txt"
  for b in 261888 262016 262017 262144 262145; do
    lomb=$(size_c "$b" shared_memory_size)
    [ -n "$lomb" ] || die "postgres -C produced no answer at $b blocks"
    printf '%-14s %12s %12s %s\n' "$b" "$lomb" "$(( prev == 0 ? 0 : lomb - prev ))" \
      "$( [ "$b" = 262016 ] && printf '2^18 - 128, last size with 2^18 buckets'; \
          [ "$b" = 262017 ] && printf 'first size needing 2^19 buckets'; \
          [ "$b" = 262144 ] && printf '2 GiB exactly'; )" >> "$OUT/sizing.txt"
    prev=$lomb
  done
  cat "$OUT/sizing.txt" >&2
}

# --------------------------------------------------------------------------
stage_cluster() {
  say "cluster: initdb, start at shared_buffers=$BASE_SB, install contrib and the timer"
  mkdir -p "$OUT" "$SOCK" || die "could not create $OUT"
  [ -f "$DATA/PG_VERSION" ] || "$BIN/initdb" -D "$DATA" -U postgres --locale=C --encoding=UTF8 \
    > "$OUT/initdb.log" 2>&1 || die "initdb failed, see $OUT/initdb.log"
  start_with "$BASE_SB"
  local have
  have=$(PGDATABASE=postgres pgq -c "SELECT /* wiki_shbuf_fixture */ count(*) FROM pg_database WHERE datname = '$DB';") \
    || die "could not read pg_database"
  if [ "$have" = 0 ]; then
    PGDATABASE=postgres pg -q -c "CREATE /* wiki_shbuf_fixture */ DATABASE $DB;" || die "CREATE DATABASE failed"
  fi
  pg -q -c "CREATE /* wiki_shbuf_fixture */ EXTENSION IF NOT EXISTS pg_buffercache;
            CREATE /* wiki_shbuf_fixture */ EXTENSION IF NOT EXISTS pg_prewarm;" || die "extensions failed"
  install_timer
  ensure_fixtures
  {
    pgq -c "SELECT /* wiki_shbuf_facts */ version();"
    pgq -c "SELECT /* wiki_shbuf_facts */ name || ' = ' || setting || coalesce(' ' || unit, '')
            FROM pg_settings WHERE name IN
              ('block_size','wal_block_size','segment_size','data_checksums','shared_buffers','huge_pages',
               'huge_pages_status','huge_page_size','io_combine_limit','vacuum_buffer_usage_limit',
               'bgwriter_delay','bgwriter_lru_maxpages','bgwriter_lru_multiplier','checkpoint_timeout',
               'checkpoint_completion_target','max_wal_size','max_connections','effective_cache_size',
               'wal_level','track_io_timing','debug_io_direct','shared_memory_size',
               'shared_memory_size_in_huge_pages','temp_buffers','wal_buffers','backend_flush_after')
            ORDER BY name;"
    printf 'uname                  %s\n' "$(uname -srm)"
    printf 'MemTotal               %s\n' "$(grep -F MemTotal /proc/meminfo)"
    printf 'Hugepagesize           %s\n' "$(grep -F Hugepagesize /proc/meminfo)"
    printf 'HugePages_Total        %s\n' "$(grep -F HugePages_Total /proc/meminfo)"
    printf 'overcommit_memory      %s\n' "$(cat /proc/sys/vm/overcommit_memory)"
    printf 'pinned commit          %s\n' "$(cd "$SRC" && git log -1 --format=%H)"
    printf 'pinned describe        %s\n' "$(cd "$SRC" && git describe --tags)"
    printf 'MAX_DATA_ALIGNMENT     %s\n' "$(grep -F 'define MAXIMUM_ALIGNOF' "$BUILD/src/include/pg_config.h" 2>/dev/null)"
    printf 'shared_buffers cap     %s blocks\n' "$MAX_SB_BLOCKS"
  } > "$OUT/facts.txt" 2>&1
  cat "$OUT/facts.txt" >&2
}

# --------------------------------------------------------------------------
# Every pool-size-dependent shared structure, read from the server itself.
# pg_shmem_allocations reports whole bytes, and its rows cover the entire
# segment: named allocations, one "<anonymous>" row for allocations outside
# the shmem index, and one NULL-name row for the still-unused tail
# (shmem.c:510-534).  The sum of allocated_size is therefore the exact
# segment size, which the model stage needs unrounded.
stage_shmem() {
  say "shmem: pg_shmem_allocations and SLRU auto-sizing, per pool size"
  local sb nb tot
  : > "$OUT/shmem.txt"; : > "$OUT/shmem_totals.txt"
  for sb in $POOLS; do
    start_with "$sb"; nb=$(nbuffers) || die "could not read shared_buffers"
    { printf '\n--- shared_buffers = %s (%s buffers)\n' "$sb" "$nb"
      pg -c "SELECT /* wiki_shbuf_shmem */ name, size, allocated_size,
                    round(allocated_size::numeric / $nb, 3) AS bytes_per_buffer
             FROM pg_shmem_allocations
             WHERE name IN ('Buffer Blocks','Buffer Descriptors','Buffer IO Condition Variables',
                            'Checkpoint BufferIds','Shared Buffer Lookup Table','Buffer Strategy Status',
                            'Checkpointer Data','transaction','commit_timestamp','subtransaction')
             ORDER BY allocated_size DESC;"
      pg -c "SELECT /* wiki_shbuf_shmem_total */ CASE WHEN name IS NULL THEN '<unused tail>' ELSE name END AS name,
                    allocated_size,
                    round(allocated_size::numeric / $nb, 3) AS bytes_per_buffer
             FROM pg_shmem_allocations WHERE name IS NULL OR name = '<anonymous>'
             UNION ALL
             SELECT 'whole segment', sum(allocated_size), round(sum(allocated_size)::numeric / $nb, 3)
             FROM pg_shmem_allocations;"
      pg -c "SELECT /* wiki_shbuf_slru */ name, setting AS blocks, setting::bigint * 8192 AS bytes
             FROM pg_settings
             WHERE name IN ('transaction_buffers','commit_timestamp_buffers','subtransaction_buffers',
                            'multixact_offset_buffers','multixact_member_buffers','notify_buffers',
                            'serializable_buffers','wal_buffers')
             ORDER BY name;"
    } >> "$OUT/shmem.txt" 2>&1 || die "could not read pg_shmem_allocations at $sb"
    tot=$(pgq -c "SELECT /* wiki_shbuf_segment */ sum(allocated_size) FROM pg_shmem_allocations;") \
      || die "could not total pg_shmem_allocations at $sb"
    printf '%s %s %s\n' "$nb" "$tot" "$(size_c "$sb" shared_memory_size)" >> "$OUT/shmem_totals.txt"
  done
  cat "$OUT/shmem.txt" >&2
  note "exact segment totals in $OUT/shmem_totals.txt"
}

# --------------------------------------------------------------------------
# The model stage is the page's substitute for a 256 GiB measurement, which
# the 4 GiB cap forbids.  It implements the pinned formulas
#   BufferShmemSize()       buf_init.c:159-186
#   StrategyShmemSize()     freelist.c:452-464
#   BufTableShmemSize()     buf_table.c:40-44
#   hash_estimate_size()    dynahash.c:783-819
#   CheckpointerShmemSize() checkpointer.c:882-897
#   the 8 kB round-up       ipci.c:162-164
# and fits the one term it cannot compute - everything in the segment that
# does not scale with NBuffers - to the exact byte total measured at the
# smallest pool, then checks the fitted model against every other measured
# pool.  sum(allocated_size) over pg_shmem_allocations is that exact total:
# the view's rows cover the whole segment (shmem.c:510-534) and the sum is
# PGShmemHeader.totalsize, which is CalculateShmemSize()'s answer in bytes,
# not the MiB-rounded shared_memory_size.
#
# CLOG, commit_timestamp and subtransaction also scale with NBuffers, through
# SimpleLruAutotuneBuffers() (slru.c:232-237), and this model does not
# implement SimpleLruShmemSize().  So the measurement pass pins those three
# to 1024 blocks - the value the same formula caps at, and therefore the value
# a 256 GiB pool would auto-size to - and pins wal_buffers to the 16 MiB that
# XLOGChooseNumBuffers() caps at from a 1 GiB pool upward.  With those held,
# the only NBuffers-dependent terms left are the ones modelled here, and the
# fitted fixed term is the same one a 256 GiB server would carry.
next_pow2() { local n=$1 p=1; while [ "$p" -lt "$n" ]; do p=$(( p * 2 )); done; printf '%s' "$p"; }

buftable_bytes() {   # dynahash.c:783-819 with entrysize 24 (BufferLookupEnt)
  local n=$1 nb ns nd segs dir elems eac nea
  nb=$(next_pow2 "$n")
  ns=$(next_pow2 "$(( (nb - 1) / 256 + 1 ))")
  nd=256; while [ "$nd" -lt "$ns" ]; do nd=$(( nd * 2 )); done
  segs=$(( ns * 2048 ))          # nSegments * MAXALIGN(DEF_SEGSIZE * sizeof(HASHBUCKET))
  dir=$(( nd * 8 ))              # nDirEntries * sizeof(HASHSEGMENT)
  eac=51                         # choose_nelem_alloc(24): elementSize 40, allocSize 2048
  nea=$(( (n - 1) / eac + 1 ))
  elems=$(( nea * eac * 40 ))    # nElementAllocs * elementAllocCnt * elementSize
  printf '%s' "$(( segs + dir + elems ))"
}

pool_bytes() {   # every term in the segment that scales with NBuffers
  local nb=$1 q
  q=$(( nb < 10000000 ? nb : 10000000 ))
  printf '%s' "$(( nb * 8192 + nb * 64 + nb * 16 + nb * 20 \
                   + q * 32 + $(buftable_bytes $(( nb + 128 ))) ))"
}

round8k() { printf '%s' "$(( $1 + 8192 - $1 % 8192 ))"; }   # ipci.c:162-164

SLRU_PINS="transaction_buffers=1024 commit_timestamp_buffers=1024 subtransaction_buffers=1024 wal_buffers=16MB"

stage_model() {
  say "model: fit the pinned shared-memory formulas to measured segments, then evaluate 256 GiB"
  local sb nb tot fixed=0 first=1 pred err
  : > "$OUT/model_totals.txt"
  for sb in $POOLS; do
    # shellcheck disable=SC2086
    start_with "$sb" $SLRU_PINS
    nb=$(nbuffers) || die "could not read shared_buffers"
    tot=$(pgq -c "SELECT /* wiki_shbuf_segment */ sum(allocated_size) FROM pg_shmem_allocations;") \
      || die "could not total pg_shmem_allocations at $sb"
    [ -n "$tot" ] || die "empty segment total at $sb"
    printf '%s %s %s\n' "$nb" "$tot" "$sb" >> "$OUT/model_totals.txt"
  done

  : > "$OUT/model.txt"
  printf 'the three SLRU sizes and wal_buffers are pinned for this pass: %s\n\n' "$SLRU_PINS" >> "$OUT/model.txt"
  printf '%-12s %16s %16s %10s %s\n' buffers measured_bytes modelled_bytes error_b note >> "$OUT/model.txt"
  local nchecks=0 resid="" resid_same=1
  while read -r nb tot sb; do
    [ -n "$nb" ] || continue
    if [ "$first" = 1 ]; then
      # Fit so that round8k(pool + fixed) reproduces this measurement.
      fixed=$(( tot - $(pool_bytes "$nb") - 8192 )); first=0
      printf '%-12s %16s %16s %10s %s\n' "$nb" "$tot" "$(round8k $(( $(pool_bytes "$nb") + fixed )))" \
        "$(( tot - $(round8k $(( $(pool_bytes "$nb") + fixed )) ) ))" \
        "$sb, fit: everything not scaling with NBuffers = $fixed bytes" >> "$OUT/model.txt"
      continue
    fi
    pred=$(round8k $(( $(pool_bytes "$nb") + fixed )))
    err=$(( tot - pred ))
    nchecks=$(( nchecks + 1 ))
    if [ -z "$resid" ]; then resid=$err; elif [ "$resid" != "$err" ]; then resid_same=0; fi
    printf '%-12s %16s %16s %10s %s\n' "$nb" "$tot" "$pred" "$err" "$sb, check" >> "$OUT/model.txt"
  done < "$OUT/model_totals.txt"
  if [ "$resid_same" = 1 ] && [ "$nchecks" -gt 1 ]; then
    printf '\nthe residual is the same %s bytes at all %s checks, so the model is exact up to\n' \
      "$resid" "$nchecks" >> "$OUT/model.txt"
    printf 'one constant offset; the 256 GiB rows below are reported both ways.\n' >> "$OUT/model.txt"
  else
    resid=0
    printf '\nthe residual is not constant across the checks, so no offset is applied below.\n' >> "$OUT/model.txt"
  fi

  # 33,554,432 buffers is 256 GiB at the default 8 kB block size.  Nothing
  # below is measured: it is the fitted model evaluated outside the cap.
  local big=33554432 bt bp total adj hp2 hp1
  bt=$(buftable_bytes $(( big + 128 )))
  bp=$(pool_bytes "$big")
  total=$(round8k $(( bp + fixed )))
  adj=$(( total + resid ))
  hp2=$(( adj / 2097152 + 1 ))     # ipci.c:393, add_size(size_b / hp_size, 1)
  hp1=$(( adj / 1073741824 + 1 ))
  {
    printf '\narithmetic for 33,554,432 buffers (256 GiB), from the fitted model - not measured\n'
    printf 'Buffer Blocks            %16s bytes  %8s MiB\n' "$(( big * 8192 ))" "$(( big * 8192 / 1048576 ))"
    printf 'Buffer Descriptors       %16s bytes  %8s MiB\n' "$(( big * 64 ))" "$(( big * 64 / 1048576 ))"
    printf 'Buffer IO Cond Variables %16s bytes  %8s MiB\n' "$(( big * 16 ))" "$(( big * 16 / 1048576 ))"
    printf 'Checkpoint BufferIds     %16s bytes  %8s MiB\n' "$(( big * 20 ))" "$(( big * 20 / 1048576 ))"
    printf 'Checkpointer requests    %16s bytes  %8s MiB  (capped at 10,000,000 slots)\n' \
      "$(( 10000000 * 32 ))" "$(( 10000000 * 32 / 1048576 ))"
    printf 'Shared Buffer Lookup Tbl %16s bytes  %8s MiB\n' "$bt" "$(( bt / 1048576 ))"
    printf 'everything else (fitted) %16s bytes  %8s MiB\n' "$fixed" "$(( fixed / 1048576 ))"
    printf 'whole segment            %16s bytes  %8s MiB\n' "$total" "$(( total / 1048576 ))"
    printf 'plus the %s-byte residual  %16s bytes  %8s MiB\n' "$resid" "$adj" "$(( adj / 1048576 ))"
    printf 'shared_memory_size would report, rounding up to whole MiB: %s MB\n' \
      "$(( (adj + 1048575) / 1048576 ))"
    printf 'huge pages at 2 MiB      %16s\n' "$hp2"
    printf 'huge pages at 1 GiB      %16s\n' "$hp1"
    printf '\nthe mapping-table step a 2^25-block pool sits just past, computed the same way\n'
    printf '33,554,304 blocks (2^25 - 128) lookup table %16s bytes\n' "$(buftable_bytes 33554432)"
    printf '33,554,305 blocks                           %16s bytes\n' "$(buftable_bytes 33554433)"
    printf 'step                                        %16s bytes  %8s MiB\n' \
      "$(( $(buftable_bytes 33554433) - $(buftable_bytes 33554432) ))" \
      "$(( ( $(buftable_bytes 33554433) - $(buftable_bytes 33554432) ) / 1048576 ))"
    printf '\nthe same step at the 2^18 boundary the sizing stage measured\n'
    printf '262,016 blocks lookup table                 %16s bytes\n' "$(buftable_bytes 262144)"
    printf '262,017 blocks lookup table                 %16s bytes\n' "$(buftable_bytes 262145)"
    printf 'step                                        %16s bytes\n' \
      "$(( $(buftable_bytes 262145) - $(buftable_bytes 262144) ))"
  } >> "$OUT/model.txt"
  cat "$OUT/model.txt" >&2
}

# --------------------------------------------------------------------------
# InitBufferPool() initializes every buffer header serially at startup, inside
# CreateSharedMemoryAndSemaphores().  The postmaster logs "starting
# PostgreSQL" *after* that call, so the interval that contains the pool's
# initialization is the one from the shell's pre-start clock reading to that
# first log line; it also contains exec, configuration load and the whole
# shared-memory mapping.  The second interval, from that line to "ready to
# accept connections", is startup-process work and contains no pool
# initialization at all.  Both are reported.
#
# The interval also contains fork, exec and configuration load, which on this
# host cost tens of milliseconds and vary from restart to restart.  At the
# pool sizes the 4 GiB cap allows, the pool's own share of it is the same
# order as that noise, so this stage takes STARTUP_TRIALS restarts per pool
# size and files every one of them: the minimum is the cleanest estimator of
# a deterministic cost under additive noise, and the spread has to be on the
# page beside it or the slope cannot be judged.
stage_startup() {
  say "startup: shared-memory creation and post-creation startup, per pool size"
  local sb nb i d t tz t0 first ready pre post
  start_with "$BASE_SB"; install_timer
  pg -q -c "DELETE /* wiki_shbuf_reset */ FROM meas WHERE stage IN ('startup','startup_ready');" >/dev/null \
    || die "could not clear previous startup rows"
  : > "$OUT/startup.txt"
  printf '%-10s %12s %16s %16s %8s\n' \
    shared_buffers blocks min_to_starting_ms min_starting_ready_ms trials >> "$OUT/startup.txt"
  for sb in $POOLS; do
    pre=999999; post=999999
    for i in $(seq 1 "$STARTUP_TRIALS"); do
      stop_server
      SERVER_LOG="$OUT/start_$sb.log"; : > "$SERVER_LOG"
      t0=$(date +%s%3N)
      start_with "$sb"
      read -r d t tz _ < <(grep -F 'starting PostgreSQL' "$SERVER_LOG" | head -1)
      first=$(date -d "$d $t $tz" +%s%3N 2>/dev/null)
      read -r d t tz _ < <(grep -F 'ready to accept connections' "$SERVER_LOG" | head -1)
      ready=$(date -d "$d $t $tz" +%s%3N 2>/dev/null)
      [ -n "$first" ] && [ -n "$ready" ] || die "could not read the start timestamps at $sb"
      [ $(( first - t0 )) -lt "$pre" ] && pre=$(( first - t0 ))
      [ $(( ready - first )) -lt "$post" ] && post=$(( ready - first ))
      nb=$(nbuffers) || die "could not read shared_buffers"
      # Recorded in microseconds, like every other row in meas.  Writing the
      # row here cannot perturb the next trial: the next measured interval
      # begins after a clean stop, whose shutdown checkpoint is outside it.
      pg -q -c "INSERT /* wiki_shbuf_startup */ INTO meas VALUES
                  ('startup', $nb, 'shell clock to starting PostgreSQL', $i, $(( (first - t0) * 1000 ))),
                  ('startup_ready', $nb, 'starting PostgreSQL to ready', $i, $(( (ready - first) * 1000 )));" \
        >/dev/null || die "could not record the startup intervals at $sb"
    done
    unset SERVER_LOG
    printf '%-10s %12s %16s %16s %8s\n' "$sb" "$nb" "$pre" "$post" "$STARTUP_TRIALS" >> "$OUT/startup.txt"
  done
  printf '\n' >> "$OUT/startup.txt"
  report_meas startup "$OUT/startup.txt"
  report_meas startup_ready "$OUT/startup.txt"
  cat "$OUT/startup.txt" >&2
}

# --------------------------------------------------------------------------
# BufferSync() locks and examines every buffer header before writing
# anything, so repeated checkpoints over an idle, clean pool put that scan in
# the foreground.  What is timed is still a whole CHECKPOINT: WAL flush,
# CheckPointGuts() and the fsync phase are inside the interval too.  To bound
# the write part of it, this stage records pg_stat_checkpointer.buffers_written
# and pg_buffercache_summary().buffers_dirty on both sides of the sequence, so
# the page can say how many pages the six checkpoints actually wrote instead
# of assuming none.
stage_ckpt() {
  say "ckpt: CHECKPOINT over an idle, clean pool, per pool size"
  local sb nb before after dirty
  : > "$OUT/ckpt.txt"
  printf '%-10s %12s %14s %16s %16s\n' \
    pool blocks dirty_before written_by_6 requested_by_6 >> "$OUT/ckpt.txt"
  for sb in $POOLS; do
    start_with "$sb"; install_timer; nb=$(nbuffers) || die "could not read shared_buffers"
    pg -q -c "DELETE /* wiki_shbuf_reset */ FROM meas WHERE stage = 'ckpt' AND pool =
                (SELECT setting::bigint FROM pg_settings WHERE name = 'shared_buffers');" >/dev/null \
      || die "could not clear previous ckpt rows at $sb"
    # Two warm-up checkpoints, then the counters are read: the first absorbs
    # whatever the restart and the DELETE dirtied.
    pg -q -c "CHECKPOINT /* wiki_shbuf_ckpt_warm */;" -c "CHECKPOINT /* wiki_shbuf_ckpt_warm */;" >/dev/null \
      || die "warm-up checkpoint failed at $sb"
    pg -q -c "SELECT /* wiki_shbuf_stat_reset */ pg_stat_reset_shared('checkpointer');" >/dev/null \
      || die "could not reset the checkpointer statistics at $sb"
    dirty=$(pgq -c "SELECT /* wiki_shbuf_dirty */ buffers_dirty FROM pg_buffercache_summary();") \
      || die "could not read pg_buffercache_summary() at $sb"
    before=$(pgq -F' ' -c "SELECT /* wiki_shbuf_ckpt_stat */ buffers_written, num_requested FROM pg_stat_checkpointer;") \
      || die "could not read pg_stat_checkpointer at $sb"
    pg -q -c "SELECT /* wiki_shbuf_ckpt */ timeit('ckpt', 'CHECKPOINT', 'CHECKPOINT', 6);" >/dev/null \
      || die "checkpoint timing failed at $sb"
    after=$(pgq -F' ' -c "SELECT /* wiki_shbuf_ckpt_stat */ buffers_written, num_requested FROM pg_stat_checkpointer;") \
      || die "could not re-read pg_stat_checkpointer at $sb"
    printf '%-10s %12s %14s %16s %16s\n' "$sb" "$nb" "$dirty" \
      "$(( ${after%% *} - ${before%% *} ))" "$(( ${after##* } - ${before##* } ))" >> "$OUT/ckpt.txt"
  done
  printf '\n' >> "$OUT/ckpt.txt"
  report_meas ckpt "$OUT/ckpt.txt"
  cat "$OUT/ckpt.txt" >&2
}

# --------------------------------------------------------------------------
# DROP and TRUNCATE reach DropRelationsAllBuffers() and DropRelationBuffers().
# Outside recovery smgrnblocks_cached() returns InvalidBlockNumber
# (smgr.c:678-690), so the BUF_DROP_FULL_SCAN_THRESHOLD shortcut cannot be
# taken and each call scans the whole pool once.  One call covers every fork:
# DropRelationBuffers() takes a fork array and has a single NBuffers loop
# (bufmgr.c:4184-4222), and RelationTruncate() hands it all three forks in one
# smgrtruncate2() call (storage.c:421).
#
# The pool pass happens at commit, so the commit has to be inside the measured
# interval - and on this host a commit's WAL flush wait is milliseconds and
# varies more than the pass itself costs at 1-4 GiB.  The timing sessions
# therefore run with synchronous_commit = off (PGC_USERSET, session scope), so
# what is timed is the statement plus the pool pass, not the WAL fsync.  These
# are not production DROP latencies; they are the pool-pass cost.
stage_drop() {
  say "drop: DROP and TRUNCATE of tiny relations, per pool size"
  local sb i
  local async="SET /* wiki_shbuf_async */ synchronous_commit = off;"
  : > "$OUT/drop.txt"
  printf 'timed with synchronous_commit = off, so the WAL flush wait is outside the interval\n' >> "$OUT/drop.txt"
  for sb in $POOLS; do
    start_with "$sb"; install_timer
    pg -q -c "DELETE /* wiki_shbuf_reset */ FROM meas WHERE stage = 'drop' AND pool =
                (SELECT setting::bigint FROM pg_settings WHERE name = 'shared_buffers');" >/dev/null \
      || die "could not clear previous drop rows at $sb"

    # $DROPS disposable one-block tables, dropped one transaction at a time,
    # and then $DROPS more dropped in a single transaction.  The serial form
    # runs one full-pool pass per drop; the batched form runs one pass for the
    # whole set, because smgrdounlinkall() hands every pending delete to
    # DropRelationsAllBuffers() together.
    for i in $(seq 1 "$DROPS"); do
      pg -q -c "CREATE /* wiki_shbuf_fixture */ TABLE d$i (id int);
                INSERT /* wiki_shbuf_fixture */ INTO d$i VALUES (1);" >/dev/null \
        || die "could not create fixture d$i at $sb"
    done
    pg -q -c "$async" \
          -c "CALL /* wiki_shbuf_drop */ timeit_tx('drop', 'DROP TABLE, 1 block, own transaction',
                'DROP TABLE d%s', $DROPS, true);" >/dev/null || die "drop timing failed at $sb"
    local list=""
    for i in $(seq 1 "$DROPS"); do
      pg -q -c "CREATE /* wiki_shbuf_fixture */ TABLE b$i (id int);
                INSERT /* wiki_shbuf_fixture */ INTO b$i VALUES (1);" >/dev/null \
        || die "could not create fixture b$i at $sb"
      list="$list${list:+, }b$i"
    done
    pg -q -c "$async" \
          -c "CALL /* wiki_shbuf_drop_batch */ timeit_tx('drop', 'DROP TABLE, $DROPS tables, one transaction',
                'DROP TABLE $list', 1);" >/dev/null || die "batched drop timing failed at $sb"

    # TRUNCATE of a one-block table that has neither a visibility map nor a
    # free space map, then of one that has both.  RelationTruncate() passes
    # every fork to one DropRelationBuffers() call, so the fork count is a
    # test of that: if the pool were scanned per fork the second row would be
    # about three times the first.
    pg -q -c "DROP /* wiki_shbuf_fixture */ TABLE IF EXISTS t1, t3;" >/dev/null \
      || die "could not drop the truncate fixtures at $sb"
    pg -q -c "CREATE /* wiki_shbuf_fixture */ TABLE t1 (id int);
              CREATE /* wiki_shbuf_fixture */ TABLE t3 (id int);" >/dev/null \
      || die "could not create the truncate fixtures at $sb"
    # Read the fork sizes on the shape the timed TRUNCATE will see, which
    # means before it runs: a TRUNCATE leaves every fork at zero blocks, so
    # reading them afterwards says nothing about what was dropped.
    pg -q -c "INSERT /* wiki_shbuf_fixture */ INTO t3 SELECT g FROM generate_series(1, 50000) g;" \
          -c "VACUUM /* wiki_shbuf_fixture */ t3;" >/dev/null \
      || die "could not fill t3 for the fork probe at $sb"
    { printf '\n--- forks present on t3 at %s, before TRUNCATE\n' "$sb"
      pg -c "SELECT /* wiki_shbuf_forks */ 't3' AS rel,
                    pg_relation_size('t3'::regclass, 'main') / 8192 AS main_blocks,
                    pg_relation_size('t3'::regclass, 'fsm') / 8192 AS fsm_blocks,
                    pg_relation_size('t3'::regclass, 'vm') / 8192 AS vm_blocks;"
    } >> "$OUT/drop.txt" 2>&1 || die "could not read the fork sizes at $sb"
    pg -q -c "TRUNCATE /* wiki_shbuf_fixture */ t3;" >/dev/null \
      || die "could not reset t3 after the fork probe at $sb"
    for i in $(seq 1 "$DROPS"); do
      pg -q -c "INSERT /* wiki_shbuf_fixture */ INTO t1 VALUES (1);" -c "$async" \
            -c "CALL /* wiki_shbuf_trunc */ timeit_tx('drop', 'TRUNCATE, main fork only', 'TRUNCATE t1', 1);" >/dev/null \
        || die "truncate timing failed at $sb"
      pg -q -c "INSERT /* wiki_shbuf_fixture */ INTO t3 SELECT g FROM generate_series(1, 50000) g;" \
            -c "VACUUM /* wiki_shbuf_fixture */ t3;" -c "$async" \
            -c "CALL /* wiki_shbuf_trunc3 */ timeit_tx('drop', 'TRUNCATE, main + vm + fsm', 'TRUNCATE t3', 1);" >/dev/null \
        || die "three-fork truncate timing failed at $sb"
    done
    pg -q -c "DROP /* wiki_shbuf_fixture */ TABLE t1, t3;" >/dev/null \
      || die "could not drop the truncate fixtures at $sb"
  done
  printf '\n' >> "$OUT/drop.txt"
  report_meas drop "$OUT/drop.txt"
  cat "$OUT/drop.txt" >&2
}

# --------------------------------------------------------------------------
# initscan() asks for BAS_BULKREAD and synchronized scanning only when the
# relation is larger than NBuffers/4.  Below that line a seq scan uses the
# default strategy and one table can fill the pool.  Buffers are counted per
# fork, because a relation's fsm and vm pages are in the pool too and would
# otherwise inflate the main-fork answer.
stage_strategy() {
  say "strategy: the NBuffers/4 bulk-read threshold, read from pg_buffercache"
  start_with "$BASE_SB"; install_timer; ensure_fixtures
  local nb thr t
  nb=$(nbuffers) || die "could not read shared_buffers"; thr=$(( nb / 4 ))
  : > "$OUT/strategy.txt"
  printf 'pool_blocks %s   NBuffers/4 %s blocks (%s MiB)\n' "$nb" "$thr" "$(( thr * 8192 / 1048576 ))" >> "$OUT/strategy.txt"
  pg -c "SELECT /* wiki_shbuf_relsize */ relname,
                pg_relation_size(oid, 'main') / 8192 AS main_blocks,
                pg_relation_size(oid, 'fsm') / 8192 AS fsm_blocks,
                pg_relation_size(oid, 'vm') / 8192 AS vm_blocks,
                (pg_relation_size(oid, 'main') / 8192) > $thr AS above_threshold
         FROM pg_class WHERE relname IN ('below','above') ORDER BY relname;" >> "$OUT/strategy.txt" 2>&1 \
    || die "could not read the fixture sizes"
  for t in below above; do
    start_with "$BASE_SB"                       # a restart empties the pool
    pg -q -c "SELECT /* wiki_shbuf_reset_io */ pg_stat_reset_shared('io');" >/dev/null \
      || die "could not reset pg_stat_io"
    # max_parallel_workers_per_gather is PGC_USERSET.  Zero keeps the whole
    # scan in one backend, so pg_stat_io's client-backend rows account for all
    # of it instead of leaving part under 'parallel worker'.
    pg -q -c "SET /* wiki_shbuf_noparallel */ max_parallel_workers_per_gather = 0;
              SELECT /* wiki_shbuf_seqscan */ count(*) FROM $t;" >/dev/null \
      || die "could not scan $t"
    { printf '\n--- after one seq scan of %s\n' "$t"
      pg -c "SELECT /* wiki_shbuf_cached */ '$t' AS rel, relforknumber,
                    count(*) AS blocks_of_rel
             FROM pg_buffercache
             WHERE relfilenode = pg_relation_filenode('$t'::regclass)
             GROUP BY relforknumber ORDER BY relforknumber;"
      pg -c "SELECT /* wiki_shbuf_cached_total */
                    count(*) FILTER (WHERE relfilenode IS NOT NULL) AS blocks_used,
                    count(*) AS pool_blocks
             FROM pg_buffercache;"
      pg -c "SELECT /* wiki_shbuf_io_ctx */ context, reads, hits, evictions, reuses
             FROM pg_stat_io
             WHERE backend_type = 'client backend' AND object = 'relation' AND (reads > 0 OR hits > 0)
             ORDER BY context;"
    } >> "$OUT/strategy.txt" 2>&1 || die "could not read the pool census after scanning $t"
  done
  cat "$OUT/strategy.txt" >&2
}

# --------------------------------------------------------------------------
# vacuum_buffer_usage_limit is PGC_USERSET and BUFFER_USAGE_LIMIT overrides it
# per command; 0 means "use as much of the pool as you like", and whatever the
# setting says the ring is capped at NBuffers/8.
#
# The fixture is rebuilt from scratch for every limit, so each VACUUM sees the
# same relation rather than one that has grown by the previous iteration's
# UPDATE, and its size is read in the same iteration that scores it.  Buffers
# are counted per fork.
stage_vacring() {
  say "vacring: VACUUM's buffer ring, from 128 kB to unlimited"
  local lim blocks main fsm vm used
  : > "$OUT/vacring.txt"
  printf 'the ring cap is NBuffers/8 = %s blocks at %s\n' "$(( $(sb_blocks "$BASE_SB") / 8 ))" "$BASE_SB" >> "$OUT/vacring.txt"
  printf '%-14s %12s %12s %10s %10s %12s\n' \
    buffer_usage_limit main_blocks main_cached fsm_cached vm_cached pool_used >> "$OUT/vacring.txt"
  for lim in '128kB' '2MB' '256MB' '0'; do
    start_with "$BASE_SB"
    # Its own fixture, rebuilt identically for every limit, so the stage
    # neither depends on nor disturbs the below/above pair, and no iteration
    # inherits the previous one's bloat.
    pg -q -c "DROP /* wiki_shbuf_fixture */ TABLE IF EXISTS vacrel;" >/dev/null \
      || die "could not drop vacrel"
    pg -q -c "CREATE /* wiki_shbuf_fixture */ TABLE vacrel (id int, pad text);
              INSERT /* wiki_shbuf_fixture */ INTO vacrel
                SELECT g, repeat('x', 40) FROM generate_series(1, $ROWS_ABOVE) g;" >/dev/null \
      || die "could not build vacrel"
    pg -q -c "VACUUM /* wiki_shbuf_fixture */ (ANALYZE) vacrel;" >/dev/null \
      || die "could not settle vacrel"
    pg -q -c "UPDATE /* wiki_shbuf_fixture */ vacrel SET pad = pad WHERE id % 10 = 0;" >/dev/null \
      || die "could not churn vacrel"
    blocks=$(pgq -c "SELECT /* wiki_shbuf_relsize */ pg_relation_size('vacrel'::regclass, 'main') / 8192;") \
      || die "could not size vacrel"
    start_with "$BASE_SB"                       # a restart empties the pool again
    pg -q -c "VACUUM /* wiki_shbuf_vacring */ (BUFFER_USAGE_LIMIT '$lim') vacrel;" >/dev/null \
      || die "VACUUM (BUFFER_USAGE_LIMIT '$lim') failed"
    main=$(pgq -c "SELECT /* wiki_shbuf_cached */ count(*) FROM pg_buffercache
                   WHERE relfilenode = pg_relation_filenode('vacrel'::regclass) AND relforknumber = 0;")
    fsm=$(pgq -c "SELECT /* wiki_shbuf_cached */ count(*) FROM pg_buffercache
                  WHERE relfilenode = pg_relation_filenode('vacrel'::regclass) AND relforknumber = 1;")
    vm=$(pgq -c "SELECT /* wiki_shbuf_cached */ count(*) FROM pg_buffercache
                 WHERE relfilenode = pg_relation_filenode('vacrel'::regclass) AND relforknumber = 2;")
    used=$(pgq -c "SELECT /* wiki_shbuf_cached */ count(*) FROM pg_buffercache WHERE relfilenode IS NOT NULL;")
    [ -n "$main" ] && [ -n "$fsm" ] && [ -n "$vm" ] && [ -n "$used" ] \
      || die "could not census the pool after VACUUM at limit $lim"
    printf '%-14s %12s %12s %10s %10s %12s\n' "$lim" "$blocks" "$main" "$fsm" "$vm" "$used" >> "$OUT/vacring.txt"
  done
  cat "$OUT/vacring.txt" >&2
}

# --------------------------------------------------------------------------
# io_combine_limit is PGC_USERSET and caps how many blocks one read-stream
# read may cover.  pg_stat_io's reads column counts *blocks*, not read calls:
# WaitReadBuffers() passes io_buffers_len, the number of blocks the vectored
# read covered, to pgstat_count_io_op_time().  So the same scan reports the
# same read count at every setting, and the only visible effect is elapsed
# time.  Both are reported, because the unchanged count is itself the finding.
# Each setting is scanned TRIALS times so the times can be compared against
# their own spread instead of taken as single samples.
stage_iocombine() {
  say "iocombine: io_combine_limit against scan time and pg_stat_io counts"
  local lim row blocks i
  start_with "$BASE_SB" 'track_io_timing=on'; install_timer
  pg -q -c "DROP /* wiki_shbuf_fixture */ TABLE IF EXISTS combine;" >/dev/null || die "could not drop combine"
  pg -q -c "CREATE /* wiki_shbuf_fixture */ TABLE combine (id int, pad text);
            INSERT /* wiki_shbuf_fixture */ INTO combine
              SELECT g, repeat('x', 40) FROM generate_series(1, $ROWS_ABOVE) g;" >/dev/null \
    || die "could not build combine"
  pg -q -c "VACUUM /* wiki_shbuf_fixture */ (ANALYZE) combine;" >/dev/null || die "could not settle combine"
  blocks=$(pgq -c "SELECT /* wiki_shbuf_relsize */ pg_relation_size('combine'::regclass, 'main') / 8192;") \
    || die "could not size combine"
  pg -q -c "DELETE /* wiki_shbuf_reset */ FROM meas WHERE stage = 'iocombine';" >/dev/null \
    || die "could not clear previous iocombine rows"
  : > "$OUT/iocombine.txt"
  printf 'combine is %s main-fork blocks; NBuffers/4 is %s blocks, so the scan is a bulk read\n' \
    "$blocks" "$(( $(nbuffers) / 4 ))" >> "$OUT/iocombine.txt"
  printf '%-18s %12s %12s %14s\n' io_combine_limit reads hits read_time_ms >> "$OUT/iocombine.txt"
  for lim in '8kB' '32kB' '128kB' '256kB'; do
    for i in $(seq 1 "$TRIALS"); do
      start_with "$BASE_SB" 'track_io_timing=on'   # empty pool, warm OS cache
      pg -q -c "SELECT /* wiki_shbuf_reset_io */ pg_stat_reset_shared('io');" >/dev/null \
        || die "could not reset pg_stat_io"
      pg -q -c "SET /* wiki_shbuf_iocombine */ io_combine_limit = '$lim';
                SET /* wiki_shbuf_noparallel */ max_parallel_workers_per_gather = 0;
                SELECT /* wiki_shbuf_seqscan */ timeit('iocombine', 'seq scan at io_combine_limit $lim',
                  'SELECT count(*) FROM combine', 1);" >/dev/null \
        || die "scan with io_combine_limit $lim failed"
      row=$(pgq -F' ' -c "SELECT /* wiki_shbuf_io_reads */ coalesce(sum(reads), 0), coalesce(sum(hits), 0),
                                 round(coalesce(sum(read_time), 0)::numeric, 1)
                          FROM pg_stat_io WHERE object = 'relation';") \
        || die "could not read pg_stat_io at $lim"
      printf '%-18s %12s %12s %14s\n' "$lim" $row >> "$OUT/iocombine.txt"
    done
  done
  printf '\n' >> "$OUT/iocombine.txt"
  report_meas iocombine "$OUT/iocombine.txt"
  cat "$OUT/iocombine.txt" >&2
}

# --------------------------------------------------------------------------
# pg_buffercache's row-per-buffer reader collects NBuffers records before it
# returns a row; the two summary readers added in 16 walk the same headers
# without allocating.  Measured at the largest pool the cap allows.
stage_bcache() {
  say "bcache: the three pg_buffercache readers at the 4 GiB cap"
  start_with 4GB; install_timer
  : > "$OUT/bcache.txt"
  printf 'pool_blocks %s\n' "$(nbuffers)" >> "$OUT/bcache.txt"
  pg -q -c "DELETE /* wiki_shbuf_reset */ FROM meas WHERE stage = 'bcache';" >/dev/null \
    || die "could not clear previous bcache rows"
  pg -q -c "SELECT /* wiki_shbuf_bcache */ timeit('bcache', 'pg_buffercache rows',
              'SELECT count(*) FROM pg_buffercache', 3);
            SELECT /* wiki_shbuf_bcache */ timeit('bcache', 'pg_buffercache_summary()',
              'SELECT * FROM pg_buffercache_summary()', 3);
            SELECT /* wiki_shbuf_bcache */ timeit('bcache', 'pg_buffercache_usage_counts()',
              'SELECT * FROM pg_buffercache_usage_counts()', 3);" >/dev/null || die "bcache timing failed"
  report_meas bcache "$OUT/bcache.txt"
  { printf '\n'; pg -c "SELECT /* wiki_shbuf_bcache */ * FROM pg_buffercache_summary();"; } >> "$OUT/bcache.txt" 2>&1 \
    || die "could not read pg_buffercache_summary()"
  cat "$OUT/bcache.txt" >&2
}

# --------------------------------------------------------------------------
# The edges.  Under the 4 GiB cap this stage can no longer ask for a pool
# larger than the machine, so what it measures is: the range check below the
# floor, that the floor itself really starts and answers a query (which
# "postgres -C" cannot tell you, because it exits at postmaster.c:964-971
# before CreateSharedMemoryAndSemaphores()), the mapping failure that
# huge_pages = on turns into a refusal to start, and a controlled buffered
# versus direct-I/O pair on one fixture at one io_combine_limit.
#
# The probes use their own data directory, so the measurement cluster is
# never touched, and every probe's exit status is recorded.
stage_errors() {
  say "errors: the range floor, a real start at the floor, huge pages, direct I/O"
  mkdir -p "$OUT" || die "could not create $OUT"
  [ -f "$EDATA/PG_VERSION" ] || "$BIN/initdb" -D "$EDATA" -U postgres --locale=C --encoding=UTF8 \
    > "$OUT/initdb_err.log" 2>&1 || die "initdb for the probe directory failed"
  : > "$OUT/errors.txt"
  local probe_n rc

  probe() {   # probe <label> <postgres options...>
    printf '\n--- %s\n' "$1" >> "$OUT/errors.txt"; shift
    timeout 60 "$BIN/postgres" -D "$EDATA" -c "port=$EPORT" \
      -c "unix_socket_directories=$SOCK" -c 'listen_addresses=' "$@" > "$OUT/probe.tmp" 2>&1
    printf 'exit status %s\n' "$?" >> "$OUT/errors.txt"
    head -4 "$OUT/probe.tmp" >> "$OUT/errors.txt"
  }

  # The GUC range is 16 .. INT_MAX/2 blocks (guc_tables.c:2257-2270).  Only
  # the floor end of it is inside this script's cap, so only the floor end is
  # probed; the ceiling is a source claim on this page, not a measurement.
  for probe_n in 15:'one block below the floor' 16:'the floor itself' \
                 $MAX_SB_BLOCKS:'the cap this script enforces'; do
    printf '\n--- shared_buffers = %s blocks, %s\n' "${probe_n%%:*}" "${probe_n##*:}" >> "$OUT/errors.txt"
    "$BIN/postgres" -D "$EDATA" -c shared_buffers="${probe_n%%:*}" -C shared_memory_size 2>&1 \
      | tail -1 >> "$OUT/errors.txt"
  done

  # Does the floor actually start?  -C cannot say, so start it and ask it.
  printf '\n--- a real server at shared_buffers = 16 blocks (128 kB)\n' >> "$OUT/errors.txt"
  stop_probe
  "$BIN/pg_ctl" -D "$EDATA" -l "$OUT/floor.log" -w \
    -o "-p $EPORT -k $SOCK -c shared_buffers=16 -c listen_addresses='' -c logging_collector=off" \
    start >/dev/null 2>&1; rc=$?
  printf 'pg_ctl start exit status %s\n' "$rc" >> "$OUT/errors.txt"
  if [ "$rc" -eq 0 ]; then
    PGDATABASE=postgres PGPORT="$EPORT" pg -c \
      "SELECT /* wiki_shbuf_floor */ current_setting('shared_buffers') AS shared_buffers,
              current_setting('shared_memory_size') AS shared_memory_size_mb,
              count(*) AS answered FROM pg_class;" >> "$OUT/errors.txt" 2>&1 \
      || die "the floor server started but would not answer a query"
    stop_probe
    printf 'stopped, postmaster.pid present: %s\n' \
      "$( [ -f "$EDATA/postmaster.pid" ] && printf yes || printf no )" >> "$OUT/errors.txt"
  else
    tail -4 "$OUT/floor.log" >> "$OUT/errors.txt"
    die "the floor server did not start; see $OUT/floor.log"
  fi

  # huge_pages = on with no huge pages reserved is the mapping failure this
  # host can still produce under the cap: CreateAnonymousSegment() retries
  # without MAP_HUGETLB only when huge_pages is not 'on' (sysv_shmem.c:599-668).
  # This probe is expected to fail, which is why it can run in the foreground.
  guard_sb 1GB >/dev/null
  probe "shared_buffers = 1GB, huge_pages = on, no huge pages configured" \
    -c shared_buffers=1GB -c huge_pages=on

  # Buffered against direct I/O, as a controlled pair: the same fixture, the
  # same io_combine_limit, the same pool size, an empty pool on both legs,
  # and only debug_io_direct different.  debug_io_direct is PGC_POSTMASTER and
  # the shipped documentation calls it developer-testing-only
  # (config.sgml:11621-11624), so this is a measurement of what the operating
  # system cache was worth here, not a recommendation.
  local leg
  for leg in buffered direct; do
    if [ "$leg" = buffered ]; then
      start_with 1GB 'track_io_timing=on'
    else
      start_with 1GB 'track_io_timing=on' 'debug_io_direct=data'
    fi
    pg -q -c "SELECT /* wiki_shbuf_reset_io */ pg_stat_reset_shared('io');" >/dev/null \
      || die "could not reset pg_stat_io on the $leg leg"
    { printf '\n--- %s leg: one seq scan of above\n' "$leg"
      pg -c "SELECT /* wiki_shbuf_directio */ current_setting('debug_io_direct') AS debug_io_direct,
                    current_setting('io_combine_limit') AS io_combine_limit,
                    current_setting('huge_pages_status') AS huge_pages_status;"
      pg -c "SET /* wiki_shbuf_noparallel */ max_parallel_workers_per_gather = 0;
             SELECT /* wiki_shbuf_seqscan */ count(*) FROM above;"
      pg -c "SELECT /* wiki_shbuf_io_ctx */ context, reads, hits, round(read_time::numeric, 1) AS read_time_ms
             FROM pg_stat_io
             WHERE backend_type = 'client backend' AND object = 'relation' AND reads > 0;"
    } >> "$OUT/errors.txt" 2>&1 || die "the $leg direct-I/O leg failed"
  done
  start_with "$BASE_SB"
  cat "$OUT/errors.txt" >&2
}

# --------------------------------------------------------------------------
stage_summary() {
  say "summary: every result file in one place"
  local f n
  { printf '===== facts\n'; cat "$OUT/facts.txt" 2>/dev/null
    for f in sizing shmem model startup ckpt drop strategy vacring iocombine bcache errors; do
      printf '\n===== %s\n' "$f"; cat "$OUT/$f.txt" 2>/dev/null
    done
    printf '\n===== test suites\n'; cat "$OUT/check_summary.txt" 2>/dev/null
    printf '\n===== ERROR/FATAL audit of the measurement cluster log\n'
    n=$(grep -cE 'ERROR|FATAL' "$OUT/server.log" 2>/dev/null)
    printf 'matching lines: %s\n' "${n:-0}"
    grep -E 'ERROR|FATAL' "$OUT/server.log" 2>/dev/null | tail -10
  } > "$OUT/summary.txt" 2>&1
  cat "$OUT/summary.txt" >&2
  note "results in $OUT/summary.txt"
}

# Teardown asserts the state it left behind.  Both clusters listen on a Unix
# socket only (listen_addresses=''), so what has to be gone is the socket
# file, not a TCP listener.
stage_stop() {
  say "stop: shut both clusters down, and prove they are down"
  stop_server; stop_probe
  if [ -f "$DATA/postmaster.pid" ]; then die "postmaster.pid is still present in $DATA"; fi
  if [ -f "$EDATA/postmaster.pid" ]; then die "postmaster.pid is still present in $EDATA"; fi
  if pgrep -a postgres 2>/dev/null | grep -qF "$SANDBOX"; then
    pgrep -a postgres | grep -F "$SANDBOX" >&2
    die "a postgres process still refers to $SANDBOX"
  fi
  local s
  for s in "$SOCK/.s.PGSQL.$PORT" "$SOCK/.s.PGSQL.$EPORT"; do
    if [ -e "$s" ]; then die "socket $s still exists"; fi
  done
  note "no postmaster.pid in either data directory, no matching postgres process"
  note "no socket file for port $PORT or $EPORT in $SOCK"
  return 0
}

stage_clean() {
  say "clean: stop both clusters and delete the sandbox"
  stage_stop || die "refusing to delete a sandbox that is not fully stopped"
  CLEANED=1
  rm -rf "$SANDBOX" || die "could not delete $SANDBOX"
  note "deleted $SANDBOX"
  return 0
}

# Validate every configured pool size in the main shell, before any stage
# runs, so a value over the cap fails the run rather than an inner subshell.
guard_sb "$BASE_SB" >/dev/null
for s in $POOLS; do guard_sb "$s" >/dev/null; done

ALL="build check sizing cluster shmem model startup ckpt drop strategy vacring iocombine bcache errors summary stop"
for s in ${@:-$ALL}; do
  case "$s" in
    build|check|sizing|cluster|shmem|model|startup|ckpt|drop|strategy|vacring|iocombine|bcache|errors|summary|stop|clean)
      "stage_$s" || die "stage $s failed" ;;
    *) die "unknown stage: $s" ;;
  esac
done
```

## Context Reviewed

- Buffer manager: [bufmgr.c](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c), [freelist.c](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c), [buf_init.c](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c), [buf_table.c](../../../../raw/postgres-17/src/backend/storage/buffer/buf_table.c), [localbuf.c](../../../../raw/postgres-17/src/backend/storage/buffer/localbuf.c), [buf_internals.h](../../../../raw/postgres-17/src/include/storage/buf_internals.h), [bufmgr.h](../../../../raw/postgres-17/src/include/storage/bufmgr.h).
- Read streams and I/O: [read_stream.c](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c), [smgr.c](../../../../raw/postgres-17/src/backend/storage/smgr/smgr.c), [md.c](../../../../raw/postgres-17/src/backend/storage/smgr/md.c).
- Shared memory and startup: [ipci.c](../../../../raw/postgres-17/src/backend/storage/ipc/ipci.c), [shmem.c](../../../../raw/postgres-17/src/backend/storage/ipc/shmem.c), [dynahash.c](../../../../raw/postgres-17/src/backend/utils/hash/dynahash.c), [sysv_shmem.c](../../../../raw/postgres-17/src/backend/port/sysv_shmem.c), [postmaster.c](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c).
- Writers and checkpoints: [checkpointer.c](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c), [bgwriter.c](../../../../raw/postgres-17/src/backend/postmaster/bgwriter.c), [xlog.c](../../../../raw/postgres-17/src/backend/access/transam/xlog.c), and every `RequestCheckpoint()` caller: [utility.c](../../../../raw/postgres-17/src/backend/tcop/utility.c), [tablespace.c](../../../../raw/postgres-17/src/backend/commands/tablespace.c), [xlogrecovery.c](../../../../raw/postgres-17/src/backend/access/transam/xlogrecovery.c).
- The `TRUNCATE` path, for whether it runs one pool pass or two: [tablecmds.c#ExecuteTruncateGuts](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L1924-L2195), [relcache.c#RelationSetNewRelfilenumber](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3787-L3970), [heap.c#heap_truncate_one_rel](../../../../raw/postgres-17/src/backend/catalog/heap.c#L3144-L3172).
- SLRU sizing: [slru.c](../../../../raw/postgres-17/src/backend/access/transam/slru.c), [slru.h](../../../../raw/postgres-17/src/include/access/slru.h), [clog.c](../../../../raw/postgres-17/src/backend/access/transam/clog.c), [commit_ts.c](../../../../raw/postgres-17/src/backend/access/transam/commit_ts.c), [subtrans.c](../../../../raw/postgres-17/src/backend/access/transam/subtrans.c).
- Callers of the full-pool routines: [storage.c](../../../../raw/postgres-17/src/backend/catalog/storage.c), [dbcommands.c](../../../../raw/postgres-17/src/backend/commands/dbcommands.c), [tablecmds.c](../../../../raw/postgres-17/src/backend/commands/tablecmds.c), [heapam_handler.c](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c).
- Scan strategy: [heapam.c](../../../../raw/postgres-17/src/backend/access/heap/heapam.c), [tableam.c](../../../../raw/postgres-17/src/backend/access/table/tableam.c), [syncscan.c](../../../../raw/postgres-17/src/backend/access/common/syncscan.c).
- GUCs, views and docs: [guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c), [system_views.sql](../../../../raw/postgres-17/src/backend/catalog/system_views.sql), [pgstatfuncs.c](../../../../raw/postgres-17/src/backend/utils/adt/pgstatfuncs.c), [config.sgml](../../../../raw/postgres-17/doc/src/sgml/config.sgml).
- Contrib: [pg_buffercache_pages.c](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache_pages.c), [pg_prewarm.c](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c), [autoprewarm.c](../../../../raw/postgres-17/contrib/pg_prewarm/autoprewarm.c).
- Tests that mention the setting at all: [016_min_consistency.pl](../../../../raw/postgres-17/src/test/recovery/t/016_min_consistency.pl), [032_relfilenode_reuse.pl](../../../../raw/postgres-17/src/test/recovery/t/032_relfilenode_reuse.pl), [004_io_direct.pl](../../../../raw/postgres-17/src/test/modules/test_misc/t/004_io_direct.pl), [pg_buffercache.sql](../../../../raw/postgres-17/contrib/pg_buffercache/sql/pg_buffercache.sql).
- Source history in the same checkout, for the since-v12 section: `git log`, `git tag --contains` and `git diff REL_12_2..786db8dcf16` over the files above.

## Evidence Map

| Claim | Evidence |
|---|---|
| `shared_buffers` is restart-only, floor 16, ceiling `INT_MAX / 2` | [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2257-L2270); the floor is probed both ways in the `errors` stage, and the range error text names the ceiling. The ceiling itself is not probed: it is above the 4 GiB cap |
| The floor really starts a server, not just prices one | `errors` stage: `pg_ctl start` at 16 blocks exits 0 and the server answers a query. `-C` cannot show this, because it exits at [postmaster.c:964-971](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L964-L971) before [postmaster.c:980](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L980) |
| 256 GiB is 33,554,432 buffers and 267,499 MB of shared memory | **arithmetic, not measured**: the `model` stage's fit of [ipci.c#CalculateShmemSize](../../../../raw/postgres-17/src/backend/storage/ipc/ipci.c#L90-L166), [buf_init.c#BufferShmemSize](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L159-L186), [freelist.c#StrategyShmemSize](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L452-L464), [dynahash.c#hash_estimate_size](../../../../raw/postgres-17/src/backend/utils/hash/dynahash.c#L783-L819), [checkpointer.c#CheckpointerShmemSize](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L882-L897) and [ipci.c:162-163](../../../../raw/postgres-17/src/backend/storage/ipc/ipci.c#L162-L163), checked against four exactly measured segments |
| The measured segment total is exact, not MiB-rounded | `sum(allocated_size)` covers the whole segment ([shmem.c:510-534](../../../../raw/postgres-17/src/backend/storage/ipc/shmem.c#L510-L534)); `shared_memory_size` rounds up to MiB at [ipci.c:377-383](../../../../raw/postgres-17/src/backend/storage/ipc/ipci.c#L377-L383) |
| Per-buffer overhead 8192 + 64 + 16 + 20 + 32 + 40, plus ~65 for three SLRUs below 4 GiB | `shmem` stage per-region rows against [buf_init.c#BufferShmemSize](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L159-L186), [checkpointer.c#CheckpointerShmemSize](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L882-L897), [dynahash.c:810-816](../../../../raw/postgres-17/src/backend/utils/hash/dynahash.c#L810-L816), [slru.c#SimpleLruShmemSize](../../../../raw/postgres-17/src/backend/access/transam/slru.c#L198-L222); marginal 8426-8451 from the `sizing` pairs |
| A 257 MiB mapping-table step sits at 2^25 blocks | measured at the 2^18 boundary (+2 MB) in the `sizing` stage; computed at 2^25 from [dynahash.c#hash_estimate_size](../../../../raw/postgres-17/src/backend/utils/hash/dynahash.c#L783-L819) plus [freelist.c:478-488](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L478-L488) and [lwlock.h:87-93](../../../../raw/postgres-17/src/include/storage/lwlock.h#L87-L93) |
| Request queue caps at 10,000,000 slots | [checkpointer.c:133-134](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L133-L134), [checkpointer.c#CheckpointerShmemSize](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L882-L897); the cap is above the 4 GiB test cap, so its effect on marginal cost is arithmetic |
| The queue-full fallback survives any pool size | [checkpointer.c#ForwardSyncRequest](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L1098-L1141) |
| A checkpoint scans every header; 11.0 ns per buffer measured | [bufmgr.c#BufferSync](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2931-L3193); `ckpt` stage, with `buffers_dirty` 0 and 0-6 buffers written across each six-checkpoint sequence |
| `buffers_written` counts performed writes, not the marked dirty set | [bufmgr.c:3139-3147](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3139-L3147) |
| `num_requested` includes manual and DDL checkpoints | [checkpointer.c:424-431](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c#L424-L431), [utility.c:942-954](../../../../raw/postgres-17/src/backend/tcop/utility.c#L942-L954), [dbcommands.c:1830-1834](../../../../raw/postgres-17/src/backend/commands/dbcommands.c#L1830-L1834); `ckpt` stage read 6 requested for 6 manual checkpoints at every pool size |
| `DROP`/`TRUNCATE` scan the pool on a primary; 6.6 and 9.6 ns per buffer measured | [bufmgr.c#DropRelationBuffers](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4110-L4223), [smgr.c#smgrnblocks_cached](../../../../raw/postgres-17/src/backend/storage/smgr/smgr.c#L678-L690), [storage.c#smgrDoPendingDeletes](../../../../raw/postgres-17/src/backend/catalog/storage.c#L657-L719); `drop` stage |
| One pass covers every fork | [bufmgr.c:4184-4222](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4184-L4222), [smgr.c#smgrtruncate2](../../../../raw/postgres-17/src/backend/storage/smgr/smgr.c#L712-L736), [storage.c#RelationTruncate](../../../../raw/postgres-17/src/backend/catalog/storage.c#L288-L439); `drop` stage, 1.15x not 3x for a 222/3/1-block three-fork table |
| The recovery shortcut needs cached sizes *and* a small block count | [bufmgr.c:4156-4182](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4156-L4182), [bufmgr.c:84-89](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L84-L89) |
| Batching drops into one transaction costs one pass | [smgr.c#smgrdounlinkall](../../../../raw/postgres-17/src/backend/storage/smgr/smgr.c#L462-L522); `drop` stage batched row, 11x |
| Server start is 71 ns per buffer before the first log line | [buf_init.c#InitBufferPool](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c#L67-L151), [postmaster.c:1083-1084](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L1083-L1084); `startup` stage, minima over 10 restarts per pool size |
| Bulk-read strategy and sync scan only above `NBuffers / 4` | [heapam.c#initscan](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L408-L527), [tableam.c#table_block_parallelscan_initialize](../../../../raw/postgres-17/src/backend/access/table/tableam.c#L389-L404); `strategy` stage, 18,692 vs 32 resident main-fork blocks |
| A cached page is shared whatever `synchronize_seqscans` says | [bufmgr.c#BufferAlloc](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1609-L1664) |
| `evictions`/`reuses` count replacement, not writes | [bufmgr.c:1995-2053](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1995-L2053) against [bufmgr.c:2061-2081](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2061-L2081); `strategy` stage, 37,352 reuses with 0 evictions and no writes |
| The background writer's target counts clean reusable buffers | [bufmgr.c:3394-3413](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3394-L3413), [bufmgr.c:3427-3450](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3427-L3450), [bufmgr.c#SyncOneBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L3490-L3544) |
| Ring cap is `NBuffers / 8`; default `VACUUM` ring 2 MB | [freelist.c#GetAccessStrategyWithSize](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L584-L614), [guc_tables.c#vacuum_buffer_usage_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2272-L2281); `vacring` stage, exactly 16,384 main-fork blocks at the cap |
| `pg_stat_io.reads` counts blocks, so combining is invisible to the counter | [bufmgr.c:1519-1521](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L1519-L1521), [pgstatfuncs.c:1425-1431](../../../../raw/postgres-17/src/backend/utils/adt/pgstatfuncs.c#L1425-L1431); `iocombine` stage, 37,495 reads on all 12 trials while `read_time` moved |
| `pg_buffercache` row reader is 56x the summary readers | [pg_buffercache_pages.c#pg_buffercache_pages](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache_pages.c#L69-L246); `bcache` stage at 524,288 buffers |
| Direct I/O removes the OS cache from the data path, and is developer-only | [guc_tables.c#debug_io_direct](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4699-L4708), [config.sgml:11621-11624](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L11621-L11624); `errors` stage controlled pair, 511.7 ms vs 31.2 ms `read_time` |
| SLRU auto-sizing to a 1024-block cap reached at 4 GiB | [slru.c#SimpleLruAutotuneBuffers](../../../../raw/postgres-17/src/backend/access/transam/slru.c#L232-L237), [clog.c#CLOGShmemBuffers](../../../../raw/postgres-17/src/backend/access/transam/clog.c#L767-L775); `shmem` stage, 256 -> 512 -> 768 -> 1024 blocks |
| Autoprewarm needed `MCXT_ALLOC_HUGE` for large pools | [autoprewarm.c:600-608](../../../../raw/postgres-17/contrib/pg_prewarm/autoprewarm.c#L600-L608); commit `e4b8f925a929`, first tag `REL_17_6` |
| Since-v12 attributions | `git log -S<symbol>`, `git show` and `git tag --contains` in `raw/postgres-17`, commit ids in the delta table |
| No NUMA support | grep for `NUMA`, `libnuma`, `numa_available` over `src/`, `contrib/`, `configure.ac` returns nothing |

## Open Questions

1. **Whether 256 GiB is the right size for a given 1 TiB host is not answerable from this evidence.** Source fixes the mechanisms and this run fixes their slopes on one machine; neither models a workload. The documentation's 25 % / 40 % guidance is guidance, not a measurement ([config.sgml#shared_buffers](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L1650-L1692)).
2. **Nothing on this page was measured above 524,288 buffers, and the 4 GiB cap is the reason.** Both kinds of 256 GiB figure inherit a gap from it. The shared-memory total is a model that reproduces four measured segments to within one constant 8 kB page, but it is still evaluated 64x outside the range it was fitted in, and a real `postgres -C shared_memory_size` at `'256GB'` would settle it in one command. The timings - about 0.37 s per checkpoint, 0.22 s per `DROP`, 0.32 s per `TRUNCATE`, 2.4 s of restart - are linear extrapolations of slopes measured over a 4x range, and whether those slopes stay linear across a 64x larger array, with TLB pressure and NUMA placement in play, is untested here. An uncapped run would replace both.
3. **The two marginal-cost figures above the cap are arithmetic.** 8364 bytes per buffer above 4 GiB and 8332 above 10,000,000 blocks follow from the terms measured below the cap, but neither boundary can be crossed under it, so neither number was observed. The SLRU cap at exactly `NBuffers = 524,288` means the measured marginal cost, 8426-8451, is the *only* regime this page could sample.
4. **Every timing is single-backend and uncontended.** The 128 mapping partitions, `buffer_strategy_lock`, and the clock sweep's behaviour under many concurrent allocators are exactly what a large pool is supposed to stress, and this run does not stress them.
5. **`TRUNCATE` measured 45 % more per buffer than `DROP`, and source does not explain the gap.** Both should be one `DropRelationsAllBuffers()` pass at commit: for a regular table `TRUNCATE` goes through `RelationSetNewRelfilenumber()`, whose non-upgrade path only calls `RelationDropStorage()` to queue a pending delete ([relcache.c:3869-3873](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3869-L3873)), and the per-fork `RelationTruncate()` path belongs to `VACUUM` truncation, not to `TRUNCATE` ([tablecmds.c:2140-2185](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L2140-L2185)). Yet the measured slopes are 6.6 against 9.6 ns per buffer, consistently across four pool sizes. Either `TRUNCATE` carries pool-proportional work this reading has not found, or the fixture difference - a fresh relfilenode and a `pg_class` update each iteration - costs something that happens to scale. Not resolved.
6. **`VACUUM`'s own truncation was not measured.** The one-pass-per-statement claim is measured for `TRUNCATE` and read from source for `VACUUM` truncation, whose `RelationTruncate()` -> `smgrtruncate2()` -> one `DropRelationBuffers()` call is the same code but a different caller ([storage.c#RelationTruncate](../../../../raw/postgres-17/src/backend/catalog/storage.c#L288-L439), [vacuumlazy.c:2640-2652](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2640-L2652)). A `VACUUM`-truncation leg with a relation that actually shrinks would close it.
7. **The `drop` stage measures a primary only.** The v14 targeted-lookup path needs `InRecovery` ([smgr.c#smgrnblocks_cached](../../../../raw/postgres-17/src/backend/storage/smgr/smgr.c#L678-L690)) and, on top of that, every fork's size cached and fewer than `NBuffers / 32` blocks to invalidate ([bufmgr.c:4156-4182](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L4156-L4182)). So "a standby's replay avoids the full scan" holds only for small relations, is source-verified and unmeasured, and needs a standby leg.
8. **Huge pages were never actually used.** `HugePages_Total` was 0 on the test host, so the 133,750 and 262 page counts are arithmetic on `hp_required = size_b / hp_size + 1` and `huge_pages = on` was only measured failing. What a 256 GiB segment costs in TLB misses with and without 1 GiB pages is exactly the question this setup cannot ask.
9. **`io_combine_limit` moves the clock but not the counter, and the ranking of the three larger settings is not resolved.** Median `read_time` was 39.0 ms at 8 kB against 30.1, 27.9 and 34.4 ms at 32 kB, 128 kB and 256 kB over three trials each, with the file in the host page cache: the 8 kB penalty is clear, the ordering among the rest is inside the spread. A cold-storage test with more trials is needed, and v17's counters cannot help because `reads` is a block count.
10. **The direct-I/O pair is one host, one fixture, one re-read.** 511.7 ms against 31.2 ms is what removing this host's page cache cost for a warm re-read of 37,384 blocks. It says nothing about a cold read, about a workload whose pages are not in the page cache anyway, or about the write path - and the documentation restricts the option to developer testing regardless ([config.sgml:11621-11624](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L11621-L11624)).
11. **No shipped test covers a large pool**, so there is no upstream regression coverage behind any of the pool-size-dependent paths above; the largest setting anywhere in the tree is 1 MB.

## Source References

- [src/backend/storage/buffer/bufmgr.c](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c) - `BUF_DROP_FULL_SCAN_THRESHOLD` (84-89), `ReadBuffer_common` (1196-1264), `WaitReadBuffers` (1411-1588) including the block-count I/O statistics at 1519-1521, `BufferAlloc` (1609-1664) with the mapping-table lookup that finds another backend's page at 1634-1654, `GetVictimBuffer` (1954-2105) with the dirty-only write branch at 1995-2053 and eviction/reuse counting at 2061-2081, `LimitAdditionalPins` (2120-2144), `BufferSync` (2931-3193) including the `buffers_written` increment at 3139-3147, `BgBufferSync` (3207-3488) with `scan_whole_pool_milliseconds` at 3228-3230, the floor target at 3394-3413 and the LRU scan at 3427-3450, `SyncOneBuffer` (3490-3544), `FlushBuffer` (3863-3991) with `XLogFlush` at 3927 and `smgrwrite` at 3948, `DropRelationBuffers` (4110-4223) with the recovery-shortcut conditions at 4156-4182 and the single `NBuffers` loop at 4184-4222, `DropRelationsAllBuffers` (4233-4393), `FindAndDropRelationBuffers` (4405-4452), `DropDatabaseBuffers` (4465-4493), `FlushRelationBuffers` (4553-4658), `FlushRelationsAllBuffers` (4670-4757), `FlushDatabaseBuffers` (4925-4960), `EvictUnpinnedBuffer` (6160-6204).
- [src/backend/storage/buffer/freelist.c](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c) - `BufferStrategyControl` (30-62), `ClockSweepTick` (108-164), `StrategyGetBuffer` (196-357), `StrategyShmemSize` (452-464), `StrategyInitialize` (474-526) with the `NBuffers + NUM_BUFFER_PARTITIONS` sizing at 478-488, `GetAccessStrategy` (541-574), `GetAccessStrategyWithSize` (584-614), `GetAccessStrategyPinLimit` (647-672), `StrategyRejectBuffer` (798-816).
- [src/backend/storage/buffer/buf_init.c](../../../../raw/postgres-17/src/backend/storage/buffer/buf_init.c) - `InitBufferPool` (67-151), `BufferShmemSize` (159-186).
- [src/backend/storage/buffer/buf_table.c](../../../../raw/postgres-17/src/backend/storage/buffer/buf_table.c) - `BufferLookupEnt` (26-31), `BufTableShmemSize` (40-44), `InitBufTable` (51-66).
- [src/backend/utils/hash/dynahash.c](../../../../raw/postgres-17/src/backend/utils/hash/dynahash.c) - `DEF_SEGSIZE` and `DEF_DIRSIZE` (123-125), `choose_nelem_alloc` (656-679), `hash_estimate_size` (783-819) with the element-group term at 810-816, `hash_select_dirsize` (830-847).
- [src/backend/storage/ipc/shmem.c](../../../../raw/postgres-17/src/backend/storage/ipc/shmem.c) - `ShmemAllocRaw` cacheline alignment (186-204), `ShmemInitStruct` allocation accounting (387-476), `pg_get_shmem_allocations` including the `<anonymous>` and unused-tail rows (491-539).
- [src/backend/storage/buffer/localbuf.c](../../../../raw/postgres-17/src/backend/storage/buffer/localbuf.c) - `LimitAdditionalLocalPins` (290-306).
- [src/include/storage/buf_internals.h](../../../../raw/postgres-17/src/include/storage/buf_internals.h) - `BM_MAX_USAGE_COUNT` (71-79), `BufferDesc` (246-258).
- [src/include/storage/bufmgr.h](../../../../raw/postgres-17/src/include/storage/bufmgr.h) - `NBuffers` declaration (149), prefetch-dependent I/O concurrency defaults (157-166).
- [src/include/storage/lwlock.h](../../../../raw/postgres-17/src/include/storage/lwlock.h) - `NUM_BUFFER_PARTITIONS` (87-93).
- [src/include/storage/proc.h](../../../../raw/postgres-17/src/include/storage/proc.h) - `NUM_SPECIAL_WORKER_PROCS` and `NUM_AUXILIARY_PROCS` (431-443).
- [src/include/pg_config_manual.h](../../../../raw/postgres-17/src/include/pg_config_manual.h) - `DEFAULT_CHECKPOINT_FLUSH_AFTER` (170-180).
- [src/include/miscadmin.h](../../../../raw/postgres-17/src/include/miscadmin.h) - `MIN_BAS_VAC_RING_SIZE_KB` and `MAX_BAS_VAC_RING_SIZE_KB` (274-278).
- [src/backend/commands/vacuum.c](../../../../raw/postgres-17/src/backend/commands/vacuum.c) - `check_vacuum_buffer_usage_limit` (126-140), the `BUFFER_USAGE_LIMIT` option range check (196-214).
- [src/backend/utils/init/postinit.c](../../../../raw/postgres-17/src/backend/utils/init/postinit.c) - the `MaxBackends` formula (579-584).
- [src/backend/storage/aio/read_stream.c](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c) - look-ahead design (1-45), pin limits in `read_stream_begin_relation` (452-478).
- [src/backend/storage/ipc/ipci.c](../../../../raw/postgres-17/src/backend/storage/ipc/ipci.c) - `CalculateShmemSize` (90-166), `InitializeShmemGUCs` (369-398).
- [src/backend/port/sysv_shmem.c](../../../../raw/postgres-17/src/backend/port/sysv_shmem.c) - `GetHugePageSize` (479-572), `CreateAnonymousSegment` (599-668).
- [src/backend/postmaster/postmaster.c](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c) - `InitializeShmemGUCs()` then the runtime-computed `-C` exit (935-971), `CreateSharedMemoryAndSemaphores` (980), `starting %s` (1083-1084).
- [src/backend/postmaster/checkpointer.c](../../../../raw/postgres-17/src/backend/postmaster/checkpointer.c) - `MAX_CHECKPOINT_REQUESTS` (133-134), the timed/requested counters (415-431), the shutdown request (595-602), `CheckpointerShmemSize` (882-897), `RequestCheckpoint` (946-1010), `ForwardSyncRequest` (1098-1141) with the checkpointer-absent and queue-full fallback at 1117-1123, `CompactCheckpointerRequestQueue` (1160-1258), `AbsorbSyncRequests` (1270-1311).
- [src/backend/access/transam/slru.c](../../../../raw/postgres-17/src/backend/access/transam/slru.c) - `SimpleLruShmemSize` (198-222) including the CLOG-only `group_lsn` term at 218-221, `SimpleLruAutotuneBuffers` (232-237).
- [src/include/access/slru.h](../../../../raw/postgres-17/src/include/access/slru.h) - `SLRU_MAX_ALLOWED_BUFFERS` (24).
- [src/backend/access/transam/clog.c](../../../../raw/postgres-17/src/backend/access/transam/clog.c) - `CLOGShmemBuffers` (767-775), `CLOGShmemSize` (777-784).
- [src/backend/access/transam/commit_ts.c](../../../../raw/postgres-17/src/backend/access/transam/commit_ts.c) - `CommitTsShmemBuffers` (506-513).
- [src/backend/access/transam/subtrans.c](../../../../raw/postgres-17/src/backend/access/transam/subtrans.c) - `SUBTRANSShmemBuffers` (201-208).
- [src/backend/access/transam/xlog.c](../../../../raw/postgres-17/src/backend/access/transam/xlog.c) - `XLOGChooseNumBuffers` (4575-4585).
- [src/backend/access/heap/heapam.c](../../../../raw/postgres-17/src/backend/access/heap/heapam.c) - `initscan` (408-527), sequential-scan read stream (1252-1258).
- [src/backend/access/table/tableam.c](../../../../raw/postgres-17/src/backend/access/table/tableam.c) - `table_block_parallelscan_initialize` (389-404).
- [src/backend/access/heap/syncscan.c](../../../../raw/postgres-17/src/backend/access/common/syncscan.c) - `SYNC_SCAN_REPORT_INTERVAL` (73-83).
- [src/backend/catalog/storage.c](../../../../raw/postgres-17/src/backend/catalog/storage.c) - `RelationTruncate` (288-439) with the one-array, one-call `smgrtruncate2()` at 421, `smgrDoPendingDeletes` (657-719), `smgr_redo` (965-1079).
- [src/backend/storage/smgr/smgr.c](../../../../raw/postgres-17/src/backend/storage/smgr/smgr.c) - `smgrdounlinkall` (462-522), `smgrnblocks_cached` (678-690), `smgrtruncate` (692-710), `smgrtruncate2` (712-736) with the single `DropRelationBuffers()` call at 736.
- [src/backend/commands/dbcommands.c](../../../../raw/postgres-17/src/backend/commands/dbcommands.c) - `createdb` (670-1532) with its pre-copy checkpoint at 566-568, `createdb_failure_callback` (1593-1616) and its `DropDatabaseBuffers()` at 1610, `dropdb` (1634-1856) with its checkpoint at 1833-1835 and pool pass at 1820, `movedb` (1964-2282), `dbase_redo` (3270-3432) with `FlushDatabaseBuffers()` at 3334 and `DropDatabaseBuffers()` at 3395.
- [src/backend/tcop/utility.c](../../../../raw/postgres-17/src/backend/tcop/utility.c) - `T_CheckPointStmt` privilege check and `RequestCheckpoint()` (942-954).
- [src/backend/commands/tablespace.c](../../../../raw/postgres-17/src/backend/commands/tablespace.c) - the `DROP TABLESPACE` checkpoint (497-503).
- [src/backend/utils/cache/relcache.c](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c) - `RelationSetNewRelfilenumber` (3787-3970), whose non-upgrade path only queues a pending delete (3869-3873).
- [src/backend/optimizer/path/costsize.c](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c) - `effective_cache_size` rationale (22-26).
- [src/backend/utils/misc/guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c) - `shared_buffers` (2257-2270), `vacuum_buffer_usage_limit` (2272-2281), `shared_memory_size` (2283-2292), `shared_memory_size_in_huge_pages` (2294-2303), `commit_timestamp_buffers` (2305-2314), `subtransaction_buffers` (2360-2369), `transaction_buffers` (2371-2380), `temp_buffers` (2382-2391), `max_wal_size` (2842-2852), `checkpoint_flush_after` (2880-2889), `bgwriter_delay` (3077-3086), `bgwriter_lru_maxpages` (3088-3096), `io_combine_limit` (3138-3150), `backend_flush_after` (3152-3161), `effective_cache_size` (3508-3518), `huge_page_size` (3598-3607), `checkpoint_completion_target` (3916-3924), `debug_io_direct` (4699-4708), `huge_pages` (5057-5065), `huge_pages_status` (5067-5076).
- [src/backend/utils/init/globals.c](../../../../raw/postgres-17/src/backend/utils/init/globals.c) - `NBuffers` default (139).
- [src/backend/catalog/system_views.sql](../../../../raw/postgres-17/src/backend/catalog/system_views.sql) - `pg_shmem_allocations` and its grants (652-658), `pg_stat_bgwriter` (1134-1139), `pg_stat_checkpointer` (1141-1151), `pg_stat_io` (1153-1173).
- [src/backend/access/heap/heapam_handler.c](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c) - heap copy for `SET TABLESPACE` (637-645).
- [src/backend/commands/tablecmds.c](../../../../raw/postgres-17/src/backend/commands/tablecmds.c) - index copy for `SET TABLESPACE` (15586-15595).
- [src/backend/commands/sequence.c](../../../../raw/postgres-17/src/backend/commands/sequence.c) - an unlogged sequence's init fork (344-352).
- [src/backend/utils/adt/pgstatfuncs.c](../../../../raw/postgres-17/src/backend/utils/adt/pgstatfuncs.c) - `op_bytes` hard-coded to `BLCKSZ` (1425-1431).
- [doc/src/sgml/config.sgml](../../../../raw/postgres-17/doc/src/sgml/config.sgml) - `shared_buffers` (1650-1692), `vacuum_buffer_usage_limit` (1974-2002), `transaction_buffers` (2143-2160), `io_combine_limit` (2778-2800), `huge_pages_status` (11204-11215), `shared_memory_size` (11365-11378), `shared_memory_size_in_huge_pages` (11379-11395), `debug_io_direct` (11595-11626) including the developer-testing-only restriction at 11621-11624.
- [contrib/pg_buffercache/pg_buffercache_pages.c](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache_pages.c) - `pg_buffercache_pages` (69-246), `pg_buffercache_summary` (249-313), `pg_buffercache_usage_counts` (316-356), `pg_buffercache_evict` (362-375).
- [contrib/pg_buffercache/pg_buffercache.control](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache.control#L1-L5) - default version 1.5.
- [contrib/pg_buffercache/pg_buffercache--1.2--1.3.sql](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache--1.2--1.3.sql#L1-L7), [pg_buffercache--1.3--1.4.sql](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache--1.3--1.4.sql#L24-L28), [pg_buffercache--1.4--1.5.sql](../../../../raw/postgres-17/contrib/pg_buffercache/pg_buffercache--1.4--1.5.sql#L1-L6) - the `pg_monitor` grants, and the ungranted `pg_buffercache_evict()`.
- [contrib/pg_prewarm/pg_prewarm.c](../../../../raw/postgres-17/contrib/pg_prewarm/pg_prewarm.c) - `pg_prewarm` (76-291).
- [contrib/pg_prewarm/autoprewarm.c](../../../../raw/postgres-17/contrib/pg_prewarm/autoprewarm.c) - `BlockInfoRecord` (60-68), GUC definitions (104-120), `autoprewarm_database_main` (437-561), `apw_dump_now` (569-713) with the 17.6 `MCXT_ALLOC_HUGE` allocation at 600-608.
- [src/test/recovery/t/016_min_consistency.pl](../../../../raw/postgres-17/src/test/recovery/t/016_min_consistency.pl#L49-L56), [src/test/recovery/t/032_relfilenode_reuse.pl](../../../../raw/postgres-17/src/test/recovery/t/032_relfilenode_reuse.pl#L18-L24), [src/test/modules/test_misc/t/004_io_direct.pl](../../../../raw/postgres-17/src/test/modules/test_misc/t/004_io_direct.pl#L44-L50), [contrib/pg_buffercache/sql/pg_buffercache.sql](../../../../raw/postgres-17/contrib/pg_buffercache/sql/pg_buffercache.sql#L1-L12) - the only `shared_buffers` settings and pool assertions in the test tree.

## Navigation

- [v17/index](../../index.md)
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
- Same question for PostgreSQL 12: [Pros and Cons of a Very Large shared_buffers Such as 256 GB on a 1 TB RAM System in PostgreSQL 12 (unverified)](../../../v12/questions/storage-and-vacuum/very-large-shared-buffers.md)
