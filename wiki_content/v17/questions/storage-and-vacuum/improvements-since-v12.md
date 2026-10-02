---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# Improvements Since PostgreSQL 12 in Storage Performance, Query Planning, Index Bloat, and Vacuum, as of PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [How each improvement was dated](#how-each-improvement-was-dated)
  - [Storage performance](#storage-performance)
  - [Query planning](#query-planning)
  - [Index bloat](#index-bloat)
  - [Vacuum](#vacuum)
  - [Results that contradict the obvious expectation](#results-that-contradict-the-obvious-expectation)
  - [Settings introduced since v12, with apply scope](#settings-introduced-since-v12-with-apply-scope)
  - [Measurement environment](#measurement-environment)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Follow AGENTS.md. In PostgreSQL 17, question: what are the improvements since PostgreSQL 12 in terms of storage performance, query planning, index bloat, and vacuum?

Prompt hygiene was applied before drafting and the asker chose "correct and restate". The prompt as typed read: `follow agents.md, in postgresql 17, question: what are the improvement since version 12 in terms of storage performance, query planning, index bloat , vacuum.` Six corrections were made: `agents.md` -> `AGENTS.md`, `postgresql` -> `PostgreSQL`, `improvement` -> `improvements`, `version 12` -> `PostgreSQL 12`, the stray space in `index bloat ,` removed, and `and` inserted before the final list item. The asker also chose build-and-measure scope, one combined page, and comprehensive per-area coverage.

## Answer

### Short answer

Every one of the four areas gained something that changes production behavior, and the four largest wins are each attributable to a single release. The numbers below are measured on this repository's own pins: PostgreSQL 17.11 built from `raw/postgres-17` at `786db8dcf16`, against PostgreSQL 12.2 built from `raw/postgres-12` at `45b88269a35`, same host, same fixtures, same non-default settings.

| Area | Biggest single change | First shipped in | Measured on identical fixtures (12.2 -> 17.11) |
|---|---|---|---|
| Index bloat | B-tree deduplication | 13 | Duplicate-heavy index 22,519,808 -> 6,979,584 bytes (**-69.0%**); single-value text index 66,486,272 -> 4,030,464 bytes (**-93.9%**); all-distinct index **byte-identical** |
| Index bloat | Bottom-up index deletion | 14 | Version-churn index 58,449,920 -> 20,856,832 bytes (**-64.3%**) from this mechanism alone, isolated with `deduplicate_items = off`; **-74.6%** with v13 deduplication on top |
| Vacuum | Dead TIDs in a TidStore | 17 | **18 index passes -> 2** over 3,000,000 dead tuples at `maintenance_work_mem = 1MB` |
| Vacuum | Index-vacuum bypass at 2% | 14 | Two indexes fully scanned -> `index scan bypassed`, VACUUM cost **22 buffer hits, 0 misses, 391 bytes of WAL** |
| Query planning | Memoize | 14 | Parameterized nested loop **572,305 -> 586 buffer hits** (977x fewer) |
| Query planning | Incremental sort | 13 | `ORDER BY a, b LIMIT 100` **7,447 -> 11 buffers**, 31.867 ms -> 0.601 ms |
| Query planning | nbtree ScalarArrayOp rework | 17 | 500 clustered `IN` keys **1,504 -> 5 buffer hits** |
| Storage performance | Read stream / vectored I/O | 17 | Cold 53,192-block seq scan **53,210 -> 3,346 read syscalls** (15.9x fewer) |

Two framing points matter as much as the wins:

- **The biggest storage-performance change is a syscall-shape change, not a physical-I/O change.** At `io_combine_limit = 8kB`, 17.11 issues exactly the same 53,210 read calls as 12.2. The improvement is entirely block combining, and it is tunable per session.
- **Three plausible expectations turned out false when measured**, including the assumption that v13's disk-based hash aggregation makes large `GROUP BY` faster. See [Results that contradict the obvious expectation](#results-that-contradict-the-obvious-expectation).

### How each improvement was dated

Release attribution here is not taken from a commit's `git tag --contains`, because that answer is wrong whenever a feature was committed, reverted, and later reintroduced. Two features in scope have exactly that history, and both would have been misdated:

| Feature | Commit | `--contains` says | Actually shipped in | Why |
|---|---|---|---|---|
| `MAINTAIN` privilege / `pg_maintain` | `60684dd834a` (2022-12-13) | `REL_16_0` | **17** | Reverted by `151c22deee6` (2023-07-07), reintroduced by `ecb0fd33720` (2024-03-13) |
| `recovery_prefetch` | `1d257577e08` (2021-04-08) | `REL_14_0` | **15** | Reverted before 14 shipped, re-landed as `5dc0418fab2` (2022-04-07) |

So every date in this page comes from a presence test of the defining symbol at each release tag inside the pinned `raw/postgres-17` checkout, which is immune to that trap. For `MAINTAIN` the test returns zero hits at `REL_16_0` and nine at `REL_17_0`; for `recovery_prefetch`, zero through `REL_14_0` and six at `REL_15_0`. The eager/lazy freezing strategies of `4d417992613` are excluded from this page entirely, because `6c6b4972664` reverted them the same day and no release ever contained them.

Two more attribution subtleties this method exposed:

- **Deduplication is v13, but `_bt_dedup_pass` is not the v13 function.** The v13 entry point was `_bt_dedup_one_page`, present only at `REL_13_0`; the feature commit is `0d861bbb702` ("Add deduplication to nbtree", 2020-02-26) and the reloption `deduplicate_items` is present from `REL_13_0` onward.
- **Memoize shipped in v14 already named Memoize.** The master rename commit `83f4fcc6550` first appears in `REL_15_0`, but `ExecMemoize` is present at `REL_14_0`, because the rename was back-patched onto the 14 branch before release.

### Storage performance

#### Read stream and vectored I/O (v17)

v17 introduces a read-stream abstraction that turns a sequential access pattern into few large reads instead of many 8 kB reads. `heap_beginscan` attaches a stream with `READ_STREAM_SEQUENTIAL` ([heapam.c:1252](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1252)), built by [read_stream.c#read_stream_begin_relation](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L389-L570), and the buffer manager gained a multi-block entry point in [bufmgr.h#StartReadBuffers](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L221-L364). How many blocks may be merged into one call is capped by the new `io_combine_limit` GUC, defined at [guc_tables.c#io_combine_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3138-L3150) as `PGC_USERSET` in blocks.

Measured on one 435,748,864-byte (53,192-block) table, single-process cold scan, counting the backend's own read syscalls from `/proc/<pid>/io`:

| Server | `io_combine_limit` | Read syscalls | Blocks per call |
|---|---|---|---|
| 12.2 | not available | 53,210 | 1.000 |
| 17.11 | `8kB` | 53,210 | 1.000 |
| 17.11 | `32kB` | 13,318 | 3.994 |
| 17.11 | `128kB` (default) | 3,346 | 15.897 |
| 17.11 | `256kB` | 1,685 | 31.568 |

The `8kB` row is the control that makes the claim precise: with combining disabled, 17.11 issues **the same 53,210 calls as 12.2**, to the call. `read_bytes` was 0 on every run because the freshly written file sat in the OS page cache, so this measures syscall count and not physical device traffic.

#### Other storage changes, by release

| Change | First shipped | Commit | Where it lives in v17 |
|---|---|---|---|
| `maintenance_io_concurrency` for maintenance prefetching | 13 | `fc34b0d9de2` | [guc_tables.c#maintenance_io_concurrency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3123-L3136) |
| Skip WAL for new relfilenodes at `wal_level = minimal`, with `wal_skip_threshold` | 13 | `cb2fd7eac28` | GUC present from `REL_13_0` |
| Faster truncation of relation forks | 13 | `6d05086c0a7` | `RelationTruncate` batching |
| WAL usage tracking infrastructure | 13 | `df3b181499b` | feeds `EXPLAIN`, `pg_stat_statements` and the autovacuum log |
| LZ4 TOAST compression, `default_toast_compression` | 14 | `bbe0a81db69` | [guc_tables.c#default_toast_compression](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4809-L4818) |
| `pg_stat_wal` view | 14 | `8d9a935965f` | view present from `REL_14_0` |
| WAL full-page-write compression with LZ4, then Zstandard | 15 | `4035cd5d4ee`, `e9537321a74` | [guc_tables.c#wal_compression_options](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L469-L478) |
| WAL prefetching during recovery | 15 | `5dc0418fab2` | [guc_tables.c#recovery_prefetch](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L5078-L5086) |
| Bulk relation extension | 16 | `31966b151e6` | [bufmgr.c#ExtendBufferedRelBy](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L875-L896), [md.c#mdzeroextend](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L525-L635) |
| `pg_stat_io` | 16 | `a9c70b46dbe` | [system_views.sql#pg_stat_io](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1153) |
| SLRU caches split into banks, with per-subsystem sizing GUCs | 17 | `53c2a97a926` | [slru.c#SLRU_BANK_SIZE](../../../../raw/postgres-17/src/backend/access/transam/slru.c#L143-L144), [guc_tables.c#transaction_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2371-L2380) |
| `pg_stat_checkpointer` | 17 | `96f052613f3` | separate checkpointer stats view |
| Streaming I/O in `ANALYZE` | 17 | `041b96802ef` | read stream in the analyze scan |
| `file_extend_method` | **17.8** | `4dac22aa10d` | added in a minor release, not at 17.0 |

Two of these are build-gated rather than always available, which is measurable: on a server configured without LZ4, `SET default_toast_compression = 'lz4'` fails with `ERROR: invalid value for parameter "default_toast_compression": "lz4"`. That comes from the enum table, where `lz4` exists only under `#ifdef USE_LZ4` ([guc_tables.c#default_toast_compression_options](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L461-L467)); the separate `NO_LZ4_SUPPORT()` error in [toast_compression.c#NO_LZ4_SUPPORT](../../../../raw/postgres-17/src/backend/access/common/toast_compression.c#L28-L32) is raised instead by the four datum-level entry points, `lz4_compress_datum`, `lz4_decompress_datum`, `lz4_decompress_datum_slice` and `toast_get_compression_id`, which is how a build without LZ4 reports an LZ4-compressed datum it cannot read. `wal_compression` gates `lz4` and `zstd` the same way. On 12.2 the GUC does not exist at all: `ERROR: unrecognized configuration parameter "default_toast_compression"`.

### Query planning

#### Incremental sort (v13)

v13 added a sort node that consumes an input already sorted by a prefix of the requested keys and sorts only within each prefix group, created by [pathnode.c#create_incremental_sort_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L2951-L2987) and enabled by [guc_tables.c#enable_incremental_sort](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L843-L852). Feature commit `d2d8a229bc5` ("Implement Incremental Sort", 2020-04-06).

Measured with an index on `(a)` only and a 1,000,000-row table, `SELECT * FROM i_t ORDER BY a, b LIMIT 100`:

| Server | Plan | Rows read | Buffers | Time |
|---|---|---|---|---|
| 12.2 | `Limit -> Gather Merge -> Sort -> Parallel Seq Scan` | 1,000,000 | 7,447 | 31.867 ms |
| 17.11 | `Limit -> Incremental Sort -> Index Scan using i_a` | 1,000 | 11 | 0.601 ms |

17.11 reports `Presorted Key: a` with one full-sort group and one presorted group. It reads a thousandth of the rows because `LIMIT` can stop after the first prefix group.

#### Memoize (v14)

v14 added a caching node for parameterized subplans, built by [pathnode.c#create_memoize_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L1598-L1640), executed by [nodeMemoize.c#ExecMemoize](../../../../raw/postgres-17/src/backend/executor/nodeMemoize.c#L697-L949), gated by [guc_tables.c#enable_memoize](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L873-L882). Feature commit `b6002a796dc` ("Add Result Cache executor node", 2021-04-01).

Measured on a nested loop with 100,000 outer rows drawing on only 50 distinct join keys, hash and merge joins disabled, both sides identical:

| Server | Inner node | Inner loops | Total buffers |
|---|---|---|---|
| 12.2 | `Index Only Scan using p_ab` | 100,000 | 572,305 hit + 139 read |
| 17.11 | `Memoize -> Index Only Scan using p_a` | 50 | 586 hit + 47 read |

17.11 reports `Hits: 99950  Misses: 50  Evictions: 0  Overflows: 0  Memory Usage: 1762kB`. Both produce 99,998,000 rows. That is **977x fewer buffer hits** for the same answer.

#### GROUP BY key reordering (v17)

v17 lets the planner try alternative orderings of grouping keys so an existing index order can be reused, in [pathkeys.c#get_useful_group_keys_orderings](../../../../raw/postgres-17/src/backend/optimizer/path/pathkeys.c#L465-L548), controlled by [guc_tables.c#enable_group_by_reordering](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1000-L1009) (`PGC_USERSET`, default on). Feature commit `0452b461bc4` (2024-01-21).

With an index on `(a, b)` and the query written `GROUP BY b, a`:

| Server | Plan |
|---|---|
| 12.2 | `GroupAggregate` / `Group Key: b, a` / `Sort` / `Seq Scan` |
| 17.11 | `GroupAggregate` / `Group Key: a, b` / `Index Only Scan using p_ab` |

17.11 rewrote the group key order and removed the sort of 1,000,000 rows entirely.

#### nbtree ScalarArrayOp execution (v17)

v17 reworked how a B-tree scan executes `= ANY (array)`, so one scan advances through array elements inside the leaf level instead of re-descending the tree per element; the machinery is [nbtutils.c#_bt_advance_array_keys](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L1789-L2464), which grows from 6 word-matches at `REL_16_0` to 25 at `REL_17_0`. Feature commit `5bf748b86bc` ("Enhance nbtree ScalarArrayOp execution", 2024-04-06).

Two array shapes against the same index on a 1,000,000-row table, index path forced:

| Array shape | 12.2 buffers | 17.11 buffers | 12.2 time | 17.11 time |
|---|---|---|---|---|
| 500 **clustered** keys (`500001..500500`) | 1,504 hit | **5 hit** | 0.296 ms | 0.095 ms |
| 500 keys spread 2,000 apart | 1,504 hit | 1,501 hit + 511 read | 2.836 ms | 3.361 ms |

The pairing is the point: the improvement is specifically the removal of *redundant descents*, so it is worth ~300x when the array elements share leaf pages and **nothing at all** when they do not.

#### Other planning changes, by release

| Change | First shipped | Commit | Where it lives in v17 |
|---|---|---|---|
| Disk-based hash aggregation, `hash_mem_multiplier` | 13 | `1f39bce0215`, `d6c08e29e7b` | [nodeAgg.c#hashagg_spill_tuple](../../../../raw/postgres-17/src/backend/executor/nodeAgg.c#L2925-L2982), [guc_tables.c#hash_mem_multiplier](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3832-L3841) |
| Partitionwise join with non-identical bounds | 13 | `c8434d64ce0` | [partbounds.c#partition_bounds_merge](../../../../raw/postgres-17/src/backend/partitioning/partbounds.c#L1118-L1177) |
| Extended statistics on expressions | 14 | `a4d75c86bf1` | `STATS_EXT_EXPRESSIONS`, view `pg_stats_ext_exprs` |
| Asynchronous append for foreign scans | 14 | `27e1f14563c` | `enable_async_append` |
| Rework of `UPDATE`/`DELETE` planning, enabling run-time pruning for them | 14 | `86dc90056df` | `ModifyTable` path |
| Specialized sort routines by key type | 15 | `6974924347c` | `qsort_tuple_signed` and siblings, present from `REL_15_0` |
| `MERGE` | 15 | `7103ebb7aae` | `ExecMerge`, present from `REL_15_0` |
| Right anti join plan shapes | 16 | `16dc2703c54` | `JOIN_RIGHT_ANTI`, present from `REL_16_0` |
| Presorted input for `ORDER BY`/`DISTINCT` aggregates | 16 | `1349d2790bf` | [guc_tables.c#enable_presorted_aggregate](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L975-L989) |
| Tuplesort API split, enabling further sort work | 16 | present at `REL_16_0` | `TuplesortPublic` |
| Partition pruning on `boolcol IS [NOT] UNKNOWN` | 17 | `07c36c1333e` | pruning step generation |
| `MERGE ... WHEN NOT MATCHED BY SOURCE` | 17 | present at `REL_17_0` | `MERGE_WHEN_NOT_MATCHED_BY_SOURCE` |

The v16 presorted-aggregate change is measurable on the same fixture. `SELECT array_length(array_agg(a ORDER BY a), 1) FROM i_t` over 1,000,000 rows:

| Server | Plan | Temp blocks | Time |
|---|---|---|---|
| 12.2 | `Aggregate -> Seq Scan` | temp read=1471 written=1476 | 144.799 ms |
| 17.11 | `Aggregate -> Index Only Scan using i_a` | none | 96.176 ms |

12.2 sorted a million values inside the aggregate and spilled; 17.11 fed the aggregate in index order and spilled nothing.

### Index bloat

#### B-tree deduplication (v13)

v13 taught B-tree leaf pages to store one index tuple per distinct key with a posting list of heap TIDs, in [nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L58-L278), applied as a last resort before a page split and gated on the reloption plus an equal-image opclass test at [nbtinsert.c#L2778-L2781](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2778-L2781). The reloption is [reloptions.c#deduplicate_items](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L168), read through [nbtree.h#BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1146-L1150), and it takes `ShareUpdateExclusiveLock` because it only affects later inserts. Feature commit `0d861bbb702`.

Three indexes over the same 1,000,000-row table, built the same way on both servers:

| Index | Key population | 12.2 bytes | 17.11 bytes | Change |
|---|---|---|---|---|
| `dedup_dup` | 100 distinct values, 10,000 rows each | 22,519,808 | 6,979,584 | **-69.0%** |
| `dedup_null` | expression key, 25% NULL | 22,519,808 | 6,971,392 | -69.0% |
| `dedup_uniq` | 1,000,000 distinct values | 22,487,040 | **22,487,040** | **0.0%, byte-identical** |
| `byp2_i2` | one distinct text value, 500,000 rows | 66,486,272 | 4,030,464 | **-93.9%** |
| `byp2_i1` | 500,000 distinct integers | 11,255,808 | **11,255,808** | 0.0%, byte-identical |

Both all-distinct indexes are byte-identical across a five-major-version gap, and `dedup_uniq` reports the same 2,733 leaf pages and the same 90.06% `avg_leaf_density` on both. That is the cleanest possible statement of the feature's scope: deduplication is worth up to 94% on duplicate-heavy keys and exactly nothing on unique ones.

#### Bottom-up index deletion (v14)

v14 added a deletion pass triggered by an executor hint that the incoming index tuple is logically unchanged, so version churn is cleaned before a page split rather than after. The pass is [nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L307-L421); the decision order inside [nbtinsert.c#_bt_delete_or_dedup_one_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2654-L2782) is simple deletion, then bottom-up deletion, then deduplication. The hint originates in the executor at [execIndexing.c#index_unchanged_by_update](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L963-L1069) and travels through `index_insert`. Feature commit `d168b666823` ("Enhance nbtree index tuple deletion", 2021-01-13).

Critically, the source states that bottom-up deletion is **not** gated on the deduplication reloption: "We deliberately omit an index-is-allequalimage test here" ([nbtinsert.c#L2769-L2776](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2769-L2776)). That makes the two mechanisms separable by experiment, which is what the third column below does.

Fixture: 200,000 rows, `bud_a` on a column whose value never changes, `bud_b` on a column updated every round, so all 8 update rounds are non-HOT. Autovacuum off cluster-wide; the heap grew to exactly 79,683,584 bytes on both servers, confirming identical churn.

| Index | 12.2 (neither mechanism) | 17.11, `deduplicate_items = off` (bottom-up only) | 17.11, default (both) |
|---|---|---|---|
| key never changes | 58,449,920 | 20,856,832 | **14,868,480** |
| key changes each round | 58,449,920 | **58,449,920** | 22,478,848 |

Reading the decomposition:

- For the index whose key never changes, bottom-up deletion **alone** accounts for -64.3%, and deduplication takes it a further -28.7%, to -74.6% overall.
- For the index whose key genuinely changes, bottom-up deletion contributes **nothing**: with dedup off, 17.11 is **byte-identical to 12.2** at 58,449,920 bytes, because the `indexUnchanged` hint is false for the column that actually changed. The 61.6% that 17.11 does save there is entirely deduplication, working on the incidental duplicates that overlapping version ranges create.
- Leaf-page density tells the same story: 62.47% on both 12.2 indexes, versus 90.65% and 75.26% on 17.11.

#### Other index changes, by release

| Change | First shipped | Commit | Note |
|---|---|---|---|
| Recycle nbtree pages deleted during the same VACUUM | 14 | `9dd963ae253` | [nbtpage.c#_bt_pendingfsm_finalize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2995-L3055) |
| `pg_class.reltuples = -1` before the first VACUUM/ANALYZE | 14 | `3d351d916b2` | changes every size-estimating bloat query |
| BRIN minmax-multi and bloom opclasses | 14 | `ab596105b55`, `77b88cd1bb9` | `minmax_multi` present from `REL_14_0` |
| GiST sortsupport builds | 14 | `9f984ba6d23` | `gistSortedBuild` present from `REL_14_0` |
| `verify_heapam` and the `pg_amcheck` front end | 14 | `866e24d47db`, `9706092839d` | contrib plus `src/bin/pg_amcheck` |
| amcheck can verify unique constraints | 17 | `5ae2087202a` | `checkunique` argument |

### Vacuum

#### Dead TIDs in a TidStore (v17)

Through v16, VACUUM accumulated dead TIDs in a flat array whose capacity was a TID count derived from `maintenance_work_mem`; when it filled, VACUUM stopped scanning, vacuumed every index, and resumed. v17 replaced that array with a TidStore built on a radix tree, added by `30e144287a7` ("Add TIDStore, to store sets of TIDs (ItemPointerData) efficiently", 2024-03-21) on top of the radix-tree template `ee1b30f128d`. The allocation is now expressed **in bytes**: [vacuumlazy.c#dead_items_alloc](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2823-L2882) sets `max_bytes = vac_work_mem * 1024L` and calls [tidstore.c#TidStoreCreateLocal](../../../../raw/postgres-17/src/backend/access/common/tidstore.c#L165-L203).

Because the budget is now bytes rather than TIDs, the progress view changed shape too. Measured column lists:

| Server | Trailing columns of `pg_stat_progress_vacuum` |
|---|---|
| 12.2 | `index_vacuum_count, max_dead_tuples, num_dead_tuples` |
| 17.11 | `index_vacuum_count, max_dead_tuple_bytes, dead_tuple_bytes, num_dead_item_ids, indexes_total, indexes_processed` |

Those map to [progress.h#L20-L30](../../../../raw/postgres-17/src/include/commands/progress.h#L20-L30) and are published by [system_views.sql#pg_stat_progress_vacuum](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1209).

Measured effect, one index, 3,000,000 rows deleted, identical 28,038-page heap on both, `maintenance_work_mem = 1MB`:

| Server | Index passes | Per-pass TID count |
|---|---|---|
| 12.2 | **18** | 17 passes of 174,517, then 32,997 |
| 17.11 | **2** | reported as `index scans: 2` |

Nine times fewer passes over the index at the same memory budget. The v17 figure is 2 rather than 1 because the TidStore is still bounded by the same budget; it is denser, not unbounded.

#### Index-vacuum bypass (v14)

v14 taught VACUUM to skip index vacuuming entirely when almost no heap pages hold dead items. In v17 the test has two conditions, at [vacuumlazy.c#L1931-L1949](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1931-L1949): fewer than 2% of `rel_pages` hold LP_DEAD items, using [vacuumlazy.c#BYPASS_THRESHOLD_PAGES](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L89), **and** the TidStore is using less than 32 MB. Feature commit `5100010ee4d` ("Teach VACUUM to bypass unnecessary index vacuuming", 2021-04-07); `3499df0dee8` then made `INDEX_CLEANUP = on` force the work.

Fixture: 500,000 rows over 8,621 pages, two indexes, 50 rows deleted from the first page only.

| Server | What VACUUM did to the indexes | Reported cost |
|---|---|---|
| 12.2 | scanned both, `50 index row versions were removed` twice | no buffer accounting in v12 VERBOSE |
| 17.11 | neither, `index scan bypassed: 1 pages from table (0.01% of total) have 50 dead item identifiers` | `22 hits, 0 misses, 0 dirtied`; WAL `2 records, 0 full page images, 391 bytes` |

#### Page-level freezing (v16), and the condition that gates it

v16 added page-level freezing (`1de58df4fec`, 2022-12-28) and v17 folded pruning and freezing into one pass, [pruneheap.c#heap_page_prune_and_freeze](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L350-L910), emitting a combined `XLOG_HEAP2_PRUNE_FREEZE` record. The decision is at [pruneheap.c#L673-L722](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L673-L722): freeze if required to advance `relfrozenxid`, **or** opportunistically if the page would become all-frozen *and a full-page image is being written anyway*. That second clause reads `hint_bit_fpi`, set at [pruneheap.c#L554-L558](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L554-L558) when the visibility checks themselves caused an FPI.

That gate is directly testable, and both outcomes were measured on a 300,000-row bulk load followed by a plain `VACUUM` with no `FREEZE` keyword:

| `wal_log_hints` | 12.2 all-frozen pages | 17.11 all-frozen pages |
|---|---|---|
| `off` (default) | 0 of 3,704 | **0 of 3,704** |
| `on` | 0 of 3,704 | **3,704 of 3,704** |

With hint-bit logging off, v17 behaves exactly like v12 here and freezes nothing, because no FPI is being written and the opportunistic branch never fires. With it on, one plain VACUUM froze all 300,000 tuples and took `relfrozenxid` age to 0, reporting `frozen: 3704 pages from table (100.00% of total) had 300000 tuples frozen`. The cost is visible in the same line of output: `WAL usage: 11116 records, 3709 full page images, 31380997 bytes`, about 31 MB of WAL for a 30 MB table. `wal_log_hints` is `postmaster` context, so both clusters were **restarted** to change it; data checksums have the same effect via `XLogHintBitIsNeeded()`.

#### Other vacuum changes, by release

| Change | First shipped | Commit | Where it lives in v17 |
|---|---|---|---|
| Index vacuuming in parallel, `VACUUM (PARALLEL n)` | 13 | `40d964ec997` | [vacuumparallel.c#parallel_vacuum_init](../../../../raw/postgres-17/src/backend/commands/vacuumparallel.c#L242-L422); `VACUUM_OPTION_PARALLEL_BULKDEL` present from `REL_13_0` |
| Autovacuum triggered by inserts | 13 | `b07642dbcd8` | [guc_tables.c#autovacuum_vacuum_insert_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3358-L3366) |
| Autovacuum logs WAL usage | 13 | `b7ce6de93b5` | autovacuum log line |
| `pg_stat_progress_analyze` | 13 | `a166d408eb0` | view present from `REL_13_0` |
| Wraparound failsafe | 14 | `1e55e7d1755` | [vacuumlazy.c#lazy_check_wraparound_failsafe](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2300-L2347), [guc_tables.c#vacuum_failsafe_age](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2706-L2714) |
| `VACUUM (PROCESS_TOAST)` | 14 | `7cb3048f38e` | [vacuum.c:251](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L251) |
| Pruning horizon decoupled from snapshot building | 14 | `dc7420c2c92` | `GlobalVisState`, present from `REL_14_0` |
| Removal of the `tupgone` special case | 14 | `8523492d4e3` | `lazy_scan_prune` structure |
| Per-index statistics in autovacuum logs | 14 | `5aed6a1fc21` | autovacuum log detail |
| Parallel vacuum reorganised behind one API | 15 | `22bd3cbe0c2` | `parallel_vacuum_init` present from `REL_15_0` |
| VACUUM reports scanned pages and new `relfrozenxid` | 15 | `872770fd6cc` | VERBOSE output |
| `reltuples` no longer distorted by partial scans, then by tiny tables | 15, 16 | `74388a1ac36`, `3097bde7dd1` | `vac_estimate_reltuples` |
| `VACUUM (BUFFER_USAGE_LIMIT)` and `vacuum_buffer_usage_limit` | 16 | `1cbbee03385` | [vacuum.c:193](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L193), [guc_tables.c#vacuum_buffer_usage_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2272-L2281) |
| `VACUUM (PROCESS_MAIN)` | 16 | `4211fbd8413` | [vacuum.c:249](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L249) |
| `VACUUM (SKIP_DATABASE_STATS, ONLY_DATABASE_STATS)` | 16 | `a46a7011b27` | [vacuum.c:287](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L287) |
| Failsafe state made globally visible | 16 | `71a825194fd` | `VacuumFailsafeActive`, present from `REL_16_0` |
| Vacuuming an index-less relation optimised | 17 | `c120550edb8` | `lazy_vacuum_heap_rel` path |
| `MAINTAIN` privilege and `pg_maintain` role | 17 | `ecb0fd33720` | measured: `GRANT MAINTAIN` succeeds on 17.11, `ERROR: unrecognized privilege type "maintain"` on 12.2 |
| `old_snapshot_threshold` removed | 17 | `f691f5b80a8` | removes a VACUUM-visible veto |

### Results that contradict the obvious expectation

These are measured outcomes that a reader would probably guess wrong.

**1. v13's disk-based hash aggregation did not make this large `GROUP BY` faster; the sort did.** 2,000,000 groups, no usable index, `work_mem = 1MB`:

| Server and path | Plan | Temp disk | Execution time |
|---|---|---|---|
| 12.2, only option | `GroupAggregate` + `Sort`, `external merge` | 27,416 kB | 992.216 ms |
| 17.11, planner's choice | `HashAggregate`, `Batches: 321` | 61,208 kB | 840.533 ms |
| 17.11, `enable_hashagg = off` | `GroupAggregate` + `Sort`, `external merge` | 23,504 kB | **786.466 ms** |

17.11's own sort path beats the hash path it actually chose, on both time and temp space, and the honest v12-to-v17 improvement on this query is the **sort** getting 20.7% faster and 14.3% smaller on disk, which is v15/v16 tuplesort work. The v13 feature widened the planner's options; it did not make this case faster.

**2. The v17 ScalarArrayOp rework is worth nothing when array elements do not share leaf pages.** 1,504 buffers on 12.2 versus 1,501 on 17.11 for 500 keys spread 2,000 apart, against 1,504 versus 5 for 500 clustered keys.

**3. Page-level freezing does not make a plain VACUUM freeze a freshly loaded table at default settings.** Both majors leave all 3,704 pages unfrozen until `wal_log_hints` (or checksums) is on. A reader who expected v16 to have removed post-load freeze debt would be wrong for a default cluster.

### Settings introduced since v12, with apply scope

Every setting named on this page, with the context read from `pg_settings` on the 17.11 server and the apply scope that follows from it.

| Setting | Context | Apply scope | Default on 17.11 |
|---|---|---|---|
| `transaction_buffers` | `postmaster` | **restart** | 32 (8 kB units) |
| `wal_log_hints` | `postmaster` | **restart** | `off` (set to `on` only for the freezing test) |
| `autovacuum_vacuum_insert_threshold` | `sighup` | **reload** | 1000 |
| `recovery_prefetch` | `sighup` | **reload** | `try` |
| `wal_compression` | `superuser` | session/transaction | `off` |
| `default_toast_compression` | `user` | session/transaction | `pglz` |
| `enable_incremental_sort` | `user` | session/transaction | `on` |
| `enable_memoize` | `user` | session/transaction | `on` |
| `enable_presorted_aggregate` | `user` | session/transaction | `on` |
| `enable_group_by_reordering` | `user` | session/transaction | `on` |
| `hash_mem_multiplier` | `user` | session/transaction | 2 |
| `io_combine_limit` | `user` | session/transaction | 16 blocks (128 kB) |
| `maintenance_io_concurrency` | `user` | session/transaction | 10 |
| `maintenance_work_mem` | `user` | session/transaction | 65536 kB |
| `vacuum_buffer_usage_limit` | `user` | session/transaction | 2048 kB |
| `vacuum_failsafe_age` | `user` | session/transaction | 1600000000 |

### Measurement environment

Both servers were built out of tree from this repository's own pinned checkouts, so `raw/` was never written to, and both were configured identically:

- 17.11 from `raw/postgres-17` at `786db8dcf168bd9df8f55047337525ac19118b1c`; 12.2 from `raw/postgres-12` at `45b88269a353ad93744772791feb6d01bc7e1e42` (tag `REL_12_2`).
- `configure --without-readline --without-zlib --without-icu --enable-debug`, so **neither build has LZ4 or Zstandard**, which is why the TOAST and WAL compression ratios are not measured here.
- Non-default settings, the same on both: `port`, `unix_socket_directories`, `listen_addresses = ''`, `track_io_timing = on`, `log_checkpoints = on`, `log_autovacuum_min_duration = 0`, `autovacuum = off`. `shared_buffers` left at the 128 MB default on both. `wal_log_hints = on` was added to both, with a restart, only for the freezing test.
- Contrib `pgstattuple`, `pageinspect` and `pg_visibility` installed on both.
- Per-table `autovacuum_enabled = false` on every fixture as well, so no background worker could touch a measurement mid-run.
- Read-syscall counts come from `/proc/<backend-pid>/io` (`syscr`), with `max_parallel_workers_per_gather = 0` so a single process performs the whole scan. An earlier run without that setting attributed only 18,602 of 53,192 blocks to the leader, which is how the need for it was found.

## Context Reviewed

- Interface inventories diffed mechanically between the working tree and `REL_12_0` inside `raw/postgres-17`: 76 GUCs added and 12 removed, 5 reloptions added, 15 system views added.
- Commit ranges enumerated for the four subsystems, `REL_12_0..HEAD`: 333 commits touching the vacuum files, 491 the index AMs, 676 the planner, 643 the buffer/storage/WAL files.
- Release attribution for every dated claim by presence test of the defining symbol at `REL_12_0`, `REL_13_0`, `REL_14_0`, `REL_15_0`, `REL_16_0`, `REL_17_0` and the pin.
- v17 implementation source for each claimed mechanism, including the caller/callee boundaries that matter: `heap_beginscan` into `read_stream_begin_relation`, `execIndexing.c` into `index_insert` for the `indexUnchanged` hint, `_bt_delete_or_dedup_one_page` ordering simple/bottom-up/dedup passes, `dead_items_alloc` into `TidStoreCreateLocal`, and `heap_page_prune_and_freeze`'s freeze decision.
- Two isolated servers built from the pins, 16 measurement runs including 2 deliberate controls (`io_combine_limit = 8kB`, `deduplicate_items = off`), 1 negative result, and 8 cross-version boundary checks with exact error text.

## Evidence Map

| Claim | Evidence |
|---|---|
| Deduplication is v13 and saves 69.0%/93.9% on duplicate-heavy indexes, 0.0% on unique ones | `_bt_dedup_pass`, `deduplicate_items` reloption, `BTGetDeduplicateItems`; presence at `REL_13_0`; commit `0d861bbb702`; M1 and M3b index sizes |
| Bottom-up deletion is v14, is independent of the dedup reloption, and does nothing when keys change | `_bt_bottomupdel_pass`, `_bt_delete_or_dedup_one_page` decision order and its "deliberately omit" comment, `index_unchanged_by_update`; commit `d168b666823`; M2 and M2b, where dedup-off/key-changing is byte-identical to 12.2 |
| TidStore is v17 and cuts index passes from 18 to 2 at 1 MB | `TidStoreCreateLocal`, `dead_items_alloc` byte budget, `progress.h` byte-based counters; commits `30e144287a7`, `ee1b30f128d`; M4 pass counts; measured progress-view column lists |
| Index-vacuum bypass is v14, gated on 2% of pages **and** 32 MB of TidStore | `BYPASS_THRESHOLD_PAGES`, the bypass block in `vacuumlazy.c`; commit `5100010ee4d`; M3 VERBOSE output on both servers |
| Read stream is v17 and reduces read syscalls 15.9x at the default | `read_stream_begin_relation`, `heap_beginscan` call site, `StartReadBuffers`, `io_combine_limit` GUC; M9 sweep including the 8 kB control equal to 12.2 |
| Incremental sort is v13; Memoize is v14; group-key reordering is v17 | `create_incremental_sort_path`, `create_memoize_path`/`ExecMemoize`, `get_useful_group_keys_orderings` and their GUCs; commits `d2d8a229bc5`, `b6002a796dc`, `0452b461bc4`; M6-1, M5-5, M5-2 plans |
| nbtree SAOP rework is v17 and helps only clustered arrays | `_bt_advance_array_keys` growth 6 -> 25 word-matches between `REL_16_0` and `REL_17_0`; commit `5bf748b86bc`; M7 versus the M6-3 control |
| Page-level freezing is v16 but gated on an FPI being written anyway | `heap_page_prune_and_freeze` freeze decision, `hint_bit_fpi`; commit `1de58df4fec`; M10 and M10b, which flip the outcome by toggling `wal_log_hints` |
| MAINTAIN shipped in 17, not 16; `recovery_prefetch` in 15, not 14 | Presence tests at each tag; revert/reintroduce commits `60684dd834a`, `151c22deee6`, `ecb0fd33720`, and `1d257577e08`, `5dc0418fab2`; measured `GRANT MAINTAIN` outcomes |
| LZ4 TOAST and WAL compression are build-gated | `default_toast_compression_options` and `wal_compression_options` `#ifdef USE_LZ4`; measured `invalid value for parameter` on a build without LZ4 |
| v17's own sort beats its own hash path on the large `GROUP BY` | M8 three-way comparison, 786.466 ms / 23,504 kB versus 840.533 ms / 61,208 kB versus 12.2's 992.216 ms / 27,416 kB |
| Apply scopes for all named settings | `pg_settings.context` read on the 17.11 server; `PGC_USERSET`/`PGC_POSTMASTER` in the cited GUC table entries |

## Open Questions

- **TOAST LZ4 and WAL LZ4/Zstandard compression ratios are unmeasured.** This host has no `lz4.h` or `zstd.h`, and installing them is out of scope for this environment, so both builds are pglz-only. The v14/v15 changes are documented from source and history, and the build gate is measured, but no compression-ratio or WAL-volume comparison is offered.
- **The pre-v17 dead-TID array capacity is asserted only from measurement.** 12.2 was observed to cap at 174,517 TIDs per pass at `maintenance_work_mem = 1MB`, and `maintenance_work_mem = 8GB` was accepted by both servers, so the old 1 GB allocation ceiling is not demonstrated here. Establishing it would require citing v12 source, which this page may not do.
- **Parallel index vacuum (v13) is confirmed to exist but not benchmarked.** `VACUUM (PARALLEL 4)` succeeds on 17.11 and fails on 12.2 with `ERROR: unrecognized VACUUM option "parallel"`, and the source path is cited, but no wall-clock comparison of parallel versus serial index vacuuming was run.
- **`pg_stat_io`, `pg_stat_wal`, `pg_stat_checkpointer`, SLRU bank sizing and bulk relation extension are dated and cited but not measured.** `pg_stat_io` was only confirmed to exist with 35 rows on 17.11 and to be absent on 12.2.
- **Every measurement is single-run on one host, with the fixture in the OS page cache.** `read_bytes` was 0 on all M9 runs, so no physical device I/O was measured anywhere in this page; timings are indicative, not benchmark-grade, and the M8 time differences in particular are within the range where repeated runs could reorder them.
- **The v13 `enable_hashagg_disk` GUC, added in 13 and removed in 14, is not covered.** It appears in neither the 12.2 nor the 17.11 server, so it could not be measured, and no claim is made about its behavior in 13.
- **Several rows in the per-release tables are dated by symbol presence without a named commit**, specifically the v16 tuplesort API split and the v17 `MERGE ... WHEN NOT MATCHED BY SOURCE` entry. Their release is established, their introducing commit was not isolated.

## Source References

- [read_stream.c#read_stream_begin_relation](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L389-L570)
- [bufmgr.h#StartReadBuffers](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L221-L364)
- [bufmgr.c#ExtendBufferedRelBy](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L875-L896)
- [md.c#mdzeroextend](../../../../raw/postgres-17/src/backend/storage/smgr/md.c#L525-L635)
- [heapam.c:1252](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1252)
- [slru.c#SLRU_BANK_SIZE](../../../../raw/postgres-17/src/backend/access/transam/slru.c#L143-L144)
- [toast_compression.c#NO_LZ4_SUPPORT](../../../../raw/postgres-17/src/backend/access/common/toast_compression.c#L28-L32)
- [guc_tables.c#default_toast_compression_options](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L461-L467)
- [guc_tables.c#wal_compression_options](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L469-L478)
- [guc_tables.c#enable_incremental_sort](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L843-L852)
- [guc_tables.c#enable_memoize](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L873-L882)
- [guc_tables.c#enable_presorted_aggregate](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L975-L989)
- [guc_tables.c#enable_group_by_reordering](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1000-L1009)
- [guc_tables.c#wal_log_hints](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1170-L1178)
- [guc_tables.c#vacuum_buffer_usage_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2272-L2281)
- [guc_tables.c#transaction_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2371-L2380)
- [guc_tables.c#vacuum_failsafe_age](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2706-L2714)
- [guc_tables.c#maintenance_io_concurrency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3123-L3136)
- [guc_tables.c#io_combine_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3138-L3150)
- [guc_tables.c#autovacuum_vacuum_insert_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3358-L3366)
- [guc_tables.c#hash_mem_multiplier](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3832-L3841)
- [guc_tables.c#default_toast_compression](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4809-L4818)
- [guc_tables.c#recovery_prefetch](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L5078-L5086)
- [nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L58-L278)
- [nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L307-L421)
- [nbtinsert.c#_bt_delete_or_dedup_one_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2654-L2782)
- [nbtinsert.c#L2769-L2776](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2769-L2776)
- [nbtinsert.c#L2778-L2781](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2778-L2781)
- [nbtpage.c#_bt_pendingfsm_finalize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L2995-L3055)
- [nbtutils.c#_bt_advance_array_keys](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L1789-L2464)
- [nbtree.h#BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1146-L1150)
- [reloptions.c#deduplicate_items](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L168)
- [execIndexing.c#index_unchanged_by_update](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L963-L1069)
- [vacuumlazy.c#BYPASS_THRESHOLD_PAGES](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L89)
- [vacuumlazy.c#L1931-L1949](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1931-L1949)
- [vacuumlazy.c#lazy_check_wraparound_failsafe](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2300-L2347)
- [vacuumlazy.c#dead_items_alloc](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2823-L2882)
- [tidstore.c#TidStoreCreateLocal](../../../../raw/postgres-17/src/backend/access/common/tidstore.c#L165-L203)
- [pruneheap.c#heap_page_prune_and_freeze](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L350-L910)
- [pruneheap.c#L554-L558](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L554-L558)
- [pruneheap.c#L673-L722](../../../../raw/postgres-17/src/backend/access/heap/pruneheap.c#L673-L722)
- [vacuumparallel.c#parallel_vacuum_init](../../../../raw/postgres-17/src/backend/commands/vacuumparallel.c#L242-L422)
- [vacuum.c:193](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L193)
- [vacuum.c:249](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L249)
- [vacuum.c:251](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L251)
- [vacuum.c:287](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L287)
- [progress.h#L20-L30](../../../../raw/postgres-17/src/include/commands/progress.h#L20-L30)
- [system_views.sql#pg_stat_io](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1153)
- [system_views.sql#pg_stat_progress_vacuum](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1209)
- [pathnode.c#create_memoize_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L1598-L1640)
- [pathnode.c#create_incremental_sort_path](../../../../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L2951-L2987)
- [pathkeys.c#get_useful_group_keys_orderings](../../../../raw/postgres-17/src/backend/optimizer/path/pathkeys.c#L465-L548)
- [nodeMemoize.c#ExecMemoize](../../../../raw/postgres-17/src/backend/executor/nodeMemoize.c#L697-L949)
- [nodeAgg.c#hashagg_spill_tuple](../../../../raw/postgres-17/src/backend/executor/nodeAgg.c#L2925-L2982)
- [partbounds.c#partition_bounds_merge](../../../../raw/postgres-17/src/backend/partitioning/partbounds.c#L1118-L1177)

## Navigation

- [v17/index](../../index.md)
- [PostgreSQL 17 Codebase Navigation Guide](../../codebase-navigation-guide.md)
- [GUC Default-Value Changes Since PostgreSQL 12](../server-administration/guc-default-changes-since-v12.md)
- [How VACUUM and Autovacuum Truncation Works in PostgreSQL 17](vacuum-truncation-and-toast.md)
- [Planner Penalties for Bloated Indexes in PostgreSQL 17](../query-planning/bloated-indexes-query-planner.md)
- [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17](../indexing/btree-index-bloat-core-sql-only.md)
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
