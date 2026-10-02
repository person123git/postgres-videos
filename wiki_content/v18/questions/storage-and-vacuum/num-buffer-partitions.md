---
type: question
version: 18
pinned_commit: baa7b142aace6821ce085906f314a75bcc4d95c8
verified: false
verified_by_agent: not yet
---

# Usage of NUM_BUFFER_PARTITIONS in PostgreSQL 18 (unverified)

## Question

Follow AGENTS.md.
In PostgreSQL 18, give a comprehensive explanation of the usage of `NUM_BUFFER_PARTITIONS`.

## Short Answer

In PostgreSQL 18, the source symbol is `NUM_BUFFER_PARTITIONS`, a compile-time constant set to `128`; it is the number of partitions of the shared buffer mapping hash table, not a SQL GUC and not the number of shared buffers [lwlock.h#NUM_BUFFER_PARTITIONS](../../../../raw/postgres-18/src/include/storage/lwlock.h#L86-L106). PostgreSQL uses it to split the mapping from `BufferTag` page identities to shared buffer IDs across 128 `BufferMapping` LWLocks so common buffer lookups do not all serialize on one lock [buf_internals.h#BufTableHashPartition](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L186-L209) [README#Buffer-Manager-Internal-Locking](../../../../raw/postgres-18/src/backend/storage/buffer/README#L109-L128).

The key rule is: compute a `BufferTag` hash with `BufTableHashCode()`, map that hash to a partition with `hashcode % NUM_BUFFER_PARTITIONS`, then use the matching `BufferMapping` LWLock while reading or changing the shared buffer lookup table [buf_table.c#BufTableHashCode](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L68-L81) [buf_internals.h#BufMappingPartitionLock](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L186-L209). Lookups take a shared partition lock; inserts and deletes take an exclusive partition lock [buf_table.c#BufTableLookup](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L83-L105) [buf_table.c#BufTableInsert](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L107-L139) [buf_table.c#BufTableDelete](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L141-L161).

## What It Partitions

`NUM_BUFFER_PARTITIONS` partitions only the shared buffer lookup table, whose entries map a `BufferTag` to a buffer ID [buf_table.c#BufferLookupEnt](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L26-L33). A `BufferTag` names one relation block by tablespace OID, database OID, relfilenumber, fork, and block number, and `BufferDesc` stores the current tag for each shared buffer descriptor [buf_internals.h#BufferTag](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L94-L113) [buf_internals.h#BufferDesc](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L258-L271).

The constant does not partition relation data pages themselves. It partitions the hash table used to find which shared buffer currently contains a page [buf_table.c#SharedBufHash](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L26-L33) [README#BufMappingLock](../../../../raw/postgres-18/src/backend/storage/buffer/README#L109-L128). Local buffers use a backend-local hash table created without `HASH_PARTITION`, so `NUM_BUFFER_PARTITIONS` is not part of local buffer lookup [localbuf.c#LocalBufferLookupEnt](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L33-L44) [localbuf.c#InitLocalBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L780-L787).

Two 18.4/18.6 changes are worth recording because they alter the buffer-manager entry-point inventory this page walks, without touching the partition count:

- Rejecting access to another session's temporary relation moved into the buffer manager itself (`1b0dd08157b`, `3aaefe8924f`). `RELATION_IS_OTHER_TEMP`'s header comment now names `ReadBuffer_common()`, `StartReadBuffersImpl()`, `read_stream_begin_impl()`, `PrefetchBuffer()` and `ExtendBufferedRelCommon()` as the entry points that already enforce it, and requires any new buffer-access entry point to do the same; command-level code keeps the macro only for command-specific error messages [rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-18/src/include/utils/rel.h#L664-L676).
- `GetLocalPinLimit()` now returns `num_temp_buffers / 4`, leaving headroom for concurrent pin holders such as multiple scans in one query. This bounds how many local buffers a read stream may pin and prevents `no empty local buffer available` errors under a large `effective_io_concurrency`; it applies to the local buffer pool, which is outside the partitioned shared mapping table (`ed8050370b7`) [localbuf.c#GetLocalPinLimit](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L305-L328) [release-18.sgml#local-buffer-pin-limit](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L1996-L2014).

## Initialization

`lwlock.h` defines `NUM_BUFFER_PARTITIONS` near the `MainLWLockArray` offset calculations because the number of buffer-mapping locks changes where the later lock-manager and predicate-lock-manager lock arrays begin [lwlock.h#fixed-lwlock-offsets](../../../../raw/postgres-18/src/include/storage/lwlock.h#L86-L110). During LWLock initialization, PostgreSQL initializes exactly `NUM_BUFFER_PARTITIONS` locks starting at `BUFFER_MAPPING_LWLOCK_OFFSET`, and each one belongs to the `LWTRANCHE_BUFFER_MAPPING` tranche [lwlock.c#InitializeLWLocks](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L498-L522) [lwlock.c#BuiltinTrancheNames](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L140-L155).

The shared buffer lookup table is initialized as a partitioned shared-memory dynahash table: `InitBufTable()` sets `info.num_partitions = NUM_BUFFER_PARTITIONS` and calls `ShmemInitHash()` with `HASH_PARTITION` [buf_table.c#InitBufTable](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L46-L66). Dynahash requires partitioned hash tables to live in shared memory, asserts that their partition count is a power of two, stores the count in the hash header, and prevents bucket splitting on the fly so bucket subsets can be locked independently [dynahash.c#partitioned-hash-comment](../../../../raw/postgres-18/src/backend/utils/hash/dynahash.c#L6-L23) [dynahash.c#HASH_PARTITION-init](../../../../raw/postgres-18/src/backend/utils/hash/dynahash.c#L526-L539).

The buffer strategy code sizes and initializes that lookup table with `NBuffers + NUM_BUFFER_PARTITIONS` entries, and its source comment says this extra headroom accounts for concurrent allocation work across partitions [freelist.c#StrategyShmemSize](../../../../raw/postgres-18/src/backend/storage/buffer/freelist.c#L448-L463) [freelist.c#StrategyInitialize](../../../../raw/postgres-18/src/backend/storage/buffer/freelist.c#L478-L489).

## How A Partition Is Chosen

`BufTableHashCode()` computes the hash value for a `BufferTag` by calling `get_hash_value()` on the shared buffer hash table [buf_table.c#BufTableHashCode](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L68-L81). `BufTableHashPartition()` returns `hashcode % NUM_BUFFER_PARTITIONS`, and `BufMappingPartitionLock()` uses that partition number to address one lock inside `MainLWLockArray` [buf_internals.h#BufTableHashPartition](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L186-L209).

The buffer README describes the same design at a higher level: since PostgreSQL 8.2, the old notional `BufMappingLock` is split into `NUM_BUFFER_PARTITIONS` locks, each guarding part of the buffer tag space, with the partition determined from low-order bits of the tag hash value [README#partitioned-BufMappingLock](../../../../raw/postgres-18/src/backend/storage/buffer/README#L122-L128). The header also records the invariant that `NUM_BUFFER_PARTITIONS` must be a power of two [buf_internals.h#BufTableHashPartition](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L186-L190).

## Normal Read And Prefetch Paths

`PrefetchSharedBuffer()` creates a `BufferTag`, computes its hash, obtains the matching partition lock in shared mode, and probes `BufTableLookup()`; if the tag is absent, it may issue storage-manager prefetch, and if the tag is present, it returns a recent buffer number that the caller must recheck because this function does not pin it [bufmgr.c#PrefetchSharedBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L557-L620).

`BufferAlloc()` is the central shared-buffer allocation path for ordinary reads. It computes the requested block's `BufferTag` hash, takes the matching partition lock in shared mode, looks for an existing entry, pins the found buffer before releasing the partition lock, and returns that buffer as found when the contents are valid [bufmgr.c#BufferAlloc-hit](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2008-L2066). If the tag is missing, `BufferAlloc()` releases the shared lock, gets a victim buffer, reacquires the same partition lock in exclusive mode, and inserts the new mapping with `BufTableInsert()` [bufmgr.c#BufferAlloc-miss-insert](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2068-L2089).

If another backend inserted the same tag first, `BufTableInsert()` returns the existing buffer ID rather than creating a duplicate, and `BufferAlloc()` gives back its victim buffer, pins the existing buffer while still holding the mapping lock, then releases the lock and returns the existing buffer [buf_table.c#BufTableInsert](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L107-L139) [bufmgr.c#BufferAlloc-insert-race](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2082-L2134). If the insert succeeds, `BufferAlloc()` stores the new tag in the victim buffer descriptor, sets `BM_TAG_VALID`, and releases the partition lock [bufmgr.c#BufferAlloc-new-tag](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2145-L2167).

## Relation Extension Path

Shared relation extension uses the same mapping partitions. `ExtendBufferedRelShared()` first obtains victim buffers, then for each new block builds a `BufferTag`, computes the hash, takes the matching partition lock in exclusive mode, and calls `BufTableInsert()` before relation extension makes the new blocks visible to other backends [bufmgr.c#ExtendBufferedRelShared-victims](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2623-L2662) [bufmgr.c#ExtendBufferedRelShared-insert](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2730-L2756).

If extension finds an existing buffer for a block beyond EOF, it pins the existing buffer before releasing the partition lock and handles the special cases described in the source comments instead of overwriting live data [bufmgr.c#ExtendBufferedRelShared-existing](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2757-L2818). If no existing buffer is found, the extension path assigns the tag, sets `BM_TAG_VALID`, releases the partition lock, and starts buffer I/O for the newly assigned buffer [bufmgr.c#ExtendBufferedRelShared-new](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2820-L2842).

## Invalidation And Reuse Paths

When PostgreSQL reuses a valid shared buffer as a victim, `InvalidateVictimBuffer()` hashes the buffer's old tag, takes that old tag's partition lock in exclusive mode, locks the buffer header, clears the tag and state flags, deletes the old entry from the lookup table, and releases the partition lock [bufmgr.c#InvalidateVictimBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2285-L2350). `GetVictimBuffer()` calls that helper when the chosen buffer still has a valid mapping entry [bufmgr.c#GetVictimBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2353-L2505).

Relation-drop and truncation cleanup also use these partitions. `InvalidateBuffer()` saves the old tag, computes the old hash and partition lock, takes the partition lock in exclusive mode, rechecks that the tag did not change, clears the buffer tag and flags, deletes the hash entry if `BM_TAG_VALID` was set, and returns the buffer to the free list [bufmgr.c#InvalidateBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2169-L2274). `FindAndDropRelationBuffers()` can avoid a full shared-buffer scan for small exact ranges by computing each block's tag hash, probing the proper partition under shared lock, and invalidating the found buffer after rechecking the descriptor [bufmgr.c#FindAndDropRelationBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L4840-L4897).

## Locking Contract

The lookup-table functions deliberately do no locking themselves because callers often need to adjust the buffer header while still holding the mapping lock [buf_table.c#locking-contract](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L1-L10). The contract is shared lock for lookup, exclusive lock for insert, and exclusive lock for delete [buf_table.c#BufTableLookup](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L83-L105) [buf_table.c#BufTableInsert](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L107-L139) [buf_table.c#BufTableDelete](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L141-L161).

The buffer README adds two correctness rules: a backend that finds a buffer by tag must pin it before releasing the mapping lock, and any buffer page-assignment change must hold the mapping lock across both buffer-header changes and hash-table changes [README#BufMappingLock](../../../../raw/postgres-18/src/backend/storage/buffer/README#L109-L120). If code ever needs to hold more than one buffer-mapping partition at once, the README requires locking partitions in partition-number order to avoid deadlock [README#partitioned-BufMappingLock](../../../../raw/postgres-18/src/backend/storage/buffer/README#L122-L128).

`BM_TAG_VALID` is the buffer-state bit that means a buffer has an associated buffer-hashtable entry, and buffer-header changes to the tag require the buffer header lock [buf_internals.h#buffer-flags](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L62-L78) [buf_internals.h#BufferDesc-locking](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L211-L229). `BufTableDelete()` raises `ERROR` if a requested mapping-table entry is missing, because that indicates a corrupted shared buffer hash table [buf_table.c#BufTableDelete](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L141-L161).

## Performance And Observability

The design reduces contention by allowing unrelated buffer tags that hash to different partitions to use different `BufferMapping` LWLocks [README#partitioned-BufMappingLock](../../../../raw/postgres-18/src/backend/storage/buffer/README#L122-L128). Tags that hash to the same partition still serialize on that partition's LWLock when they need incompatible lock modes [buf_internals.h#BufMappingPartitionLock](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L186-L209) [buf_table.c#locking-contract](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L1-L10).

Wait reporting uses the LWLock tranche ID, and the buffer-mapping locks are initialized in the `LWTRANCHE_BUFFER_MAPPING` tranche [lwlock.c#LWLockReportWaitStart](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L732-L740) [lwlock.c#InitializeLWLocks](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L514-L522). The wait-event name table describes `BufferMapping` as waiting to associate a data block with a buffer in the buffer pool [wait_event_names.txt#BufferMapping](../../../../raw/postgres-18/src/backend/utils/activity/wait_event_names.txt#L372-L379).

Changing the partition count is a source-code change, not a runtime setting: `NUM_BUFFER_PARTITIONS` is a preprocessor macro, it participates in fixed LWLock array offsets, and `LWLockShmemSize()` allocates shared memory from `NUM_FIXED_LWLOCKS`, which includes the buffer-mapping partition count through those offsets [lwlock.h#fixed-lwlock-offsets](../../../../raw/postgres-18/src/include/storage/lwlock.h#L86-L110) [lwlock.c#LWLockShmemSize](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L428-L455). Another dynamic shared hash implementation separately defines `DSHASH_NUM_PARTITIONS` as `1 << 7` and comments that this matches `NUM_BUFFER_PARTITIONS` for now, but that is a separate constant rather than a direct use of the buffer-manager macro [dshash.c#DSHASH_NUM_PARTITIONS](../../../../raw/postgres-18/src/backend/lib/dshash.c#L53-L60).

## Tests And Documentation

The same-checkout buffer-manager README is the direct design documentation for `NUM_BUFFER_PARTITIONS`, including its purpose, low-order-hash partition choice, and multi-partition lock-order rule [README#partitioned-BufMappingLock](../../../../raw/postgres-18/src/backend/storage/buffer/README#L122-L128). I found no direct PostgreSQL 18 regression or TAP test that names `NUM_BUFFER_PARTITIONS`, `BufMappingPartitionLock`, `Shared Buffer Lookup Table`, or `BufferMapping`; the behavior is covered by the buffer manager source paths above rather than by a narrow symbol-named test.

## Source Commit History

Every commit reachable from the pinned `raw/postgres-18/` checkout (HEAD `baa7b142aac`, `REL_18_6-10-gbaa7b142aac`) whose diff touches `NUM_BUFFER_PARTITIONS`, oldest first. These are PostgreSQL source-tree commits in the same checkout's git history; reproduce any of them with `git show <hash>` (or `git log -G 'NUM_BUFFER_PARTITIONS'`) inside `raw/postgres-18/`. The macro was born at `16` and is `128` in v18.

The table is unchanged by the 2026-08-17 repin: `git log -S NUM_BUFFER_PARTITIONS` over the 294-commit range `6cb307251c5c6261286c1566496920976640108e..baa7b142aace6821ce085906f314a75bcc4d95c8` (the 18.4 and 18.6 minor releases) returns no commit, so no commit in that range touches the macro.

| Commit | Date | Author (committer) | Subject |
|---|---|---|---|
| `10b9ca3d` | 2006-07-23 | Tom Lane | Split the buffer mapping table into multiple separately lockable partitions |
| `b25dc481` | 2006-07-23 | Tom Lane | Fix oversight in sizing of shared buffer lookup hashtable |
| `f99a569a` | 2006-10-04 | Bruce Momjian | pgindent run for 8.2 |
| `2a275e6d` | 2007-07-16 | Tom Lane | Fix pg_buffercache to release buffer partition locks in reverse order |
| `ea9df812` | 2014-01-27 | Robert Haas | Relax the requirement that all lwlocks be stored in a single array |
| `3acc10c9` | 2014-10-02 | Robert Haas | Increase the number of buffer mapping partitions to 128 |
| `c319991b` | 2016-02-11 | Robert Haas | Use separate lwlock tranches for buffer, lock, and predicate lock managers |
| `6e654546` | 2016-09-29 | Heikki Linnakangas | Don't bother to lock bufmgr partitions in pg_buffercache |
| `3761fe3c` | 2016-12-16 | Robert Haas | Simplify LWLock tranche machinery by removing array_base/array_stride |
| `8c0d7baf` | 2017-08-22 | Andres Freund (patch: Thomas Munro) | Hash tables backed by DSA shared memory |
| `d03d7549` | 2020-11-24 | Michael Paquier (patch: Japin Li) | Use macros instead of hardcoded offsets for LWLock initialization |
| `3ac88fdd` | 2022-07-27 | Robert Haas (patch: Dilip Kumar) | Convert macros to static inline functions (buf_internals.h) |

### `10b9ca3d` — Split the buffer mapping table into partitions (2006-07-23, Tom Lane)

**What it did:** Created `NUM_BUFFER_PARTITIONS` with the initial value `16` and split the single system-wide `BufMappingLock` into that many separately lockable partitions, choosing a partition from the buffer tag's hash. This is the origin of everything the rest of this page describes; the buffer README still narrates this design (see [README#partitioned-BufMappingLock](../../../../raw/postgres-18/src/backend/storage/buffer/README#L122-L128)).

> Split the buffer mapping table into multiple separately lockable
> partitions, as per discussion.  Passes functionality checks, but
> I don't have any performance data yet.

### `b25dc481` — Size the lookup table with partition headroom (2006-07-23, Tom Lane)

**What it did:** Fixed the shared buffer lookup hashtable to be sized for `NBuffers + NUM_BUFFER_PARTITIONS` entries, because `BufferAlloc()` inserts a new mapping before deleting the old one and so transiently needs up to one extra entry per partition. This is the origin of the sizing the page documents at [freelist.c#StrategyInitialize](../../../../raw/postgres-18/src/backend/storage/buffer/freelist.c#L478-L489).

> Fix oversight in sizing of shared buffer lookup hashtable.  Because
> BufferAlloc tries to insert a new mapping entry before deleting the old one
> for a buffer, we have a transient need for more than NBuffers entries ---
> one more in 8.1, and as many as NUM_BUFFER_PARTITIONS more in CVS HEAD.
> In theory this could lead to an "out of shared memory" failure if shmem
> had already been completely claimed by the time the extra entries were
> needed.

### `f99a569a` — pgindent run for 8.2 (2006-10-04, Bruce Momjian)

**What it did:** Cosmetic only. The tree-wide reindent reflowed lines that mention the macro; no behavior or value changed. Included here for completeness because it appears in the macro's diff history.

> pgindent run for 8.2.

### `2a275e6d` — Release partition locks in reverse order in pg_buffercache (2007-07-16, Tom Lane)

**What it did:** Made `pg_buffercache` release the `NUM_BUFFER_PARTITIONS` partition locks in reverse acquisition order and documented why, anticipating a larger partition count. It is the early expression of the deadlock-avoidance lock-ordering rule the page covers under [Locking Contract](#locking-contract).

> Fix pg_buffercache to release buffer partition locks in reverse order,
> and add a note about why.  This is not tremendously important right now,
> probably, but it will get more urgent if NUM_BUFFER_PARTITIONS is increased
> as much as proposed.

### `ea9df812` — Stop assuming all lwlocks live in one array (2014-01-27, Robert Haas)

**What it did:** Changed `BufMappingPartitionLock()` from `FirstBufMappingLock + partition` (an id into one array) to `&MainLWLockArray[BUFFER_MAPPING_LWLOCK_OFFSET + partition].lock`, and added `BufMappingPartitionLockByIndex()`. This is the direct ancestor of the accessors the page cites at [buf_internals.h#BufTableHashPartition](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L186-L209).

> Relax the requirement that all lwlocks be stored in a single array.
>
> This makes it possible to store lwlocks as part of some other data
> structure in the main shared memory segment, or in a dynamic shared
> memory segment.  There is still a main LWLock array and this patch does
> not move anything out of it, but it provides necessary infrastructure
> for doing that in the future.
>
> This change is likely to increase the size of LWLockPadded on some
> platforms, especially 32-bit platforms where it was previously only
> 16 bytes.
>
> Patch by me.  Review by Andres Freund and KaiGai Kohei.

### `3acc10c9` — Increase partitions from 16 to 128 (2014-10-02, Robert Haas)

**What it did:** Changed `#define NUM_BUFFER_PARTITIONS` from `16` to `128`, the value v18 still uses ([lwlock.h#NUM_BUFFER_PARTITIONS](../../../../raw/postgres-18/src/include/storage/lwlock.h#L92-L93)). The message records that scalability testing favored 128 over 64 and smaller values.

> Increase the number of buffer mapping partitions to 128.
>
> Testing by Amit Kapila, Andres Freund, and myself, with and without
> other patches that also aim to improve scalability, seems to indicate
> that this change is a significant win over the current value and over
> smaller values such as 64.  It's not clear how high we can push this
> value before it starts to have negative side-effects elsewhere, but
> going this far looks OK.

### `c319991b` — Give buffer-mapping locks their own tranche (2016-02-11, Robert Haas)

**What it did:** Put the `NUM_BUFFER_PARTITIONS` buffer-mapping locks into a dedicated `LWTRANCHE_BUFFER_MAPPING` tranche. This is the origin of the tranche behind the `BufferMapping` wait event the page documents at [wait_event_names.txt#BufferMapping](../../../../raw/postgres-18/src/backend/utils/activity/wait_event_names.txt#L372-L379).

> Use separate lwlock tranches for buffer, lock, and predicate lock managers.
>
> This finishes the work - spread across many commits over the last
> several months - of putting each type of lock other than the named
> individual locks into a separate tranche.
>
> Amit Kapila

### `6e654546` — Stop locking the partitions in pg_buffercache (2016-09-29, Heikki Linnakangas)

**What it did:** Removed the loop that acquired and released all `NUM_BUFFER_PARTITIONS` partition locks while scanning `pg_buffercache`, accepting a non-atomic snapshot in exchange for not disrupting production traffic. It effectively retired the lock-ordering concern that `2a275e6d` had addressed for that view.

> Don't bother to lock bufmgr partitions in pg_buffercache.
>
> That makes the view a lot less disruptive to use on a production system.
> Without the locks, you don't get a consistent snapshot across all buffers,
> but that's OK. It wasn't a very useful guarantee in practice.
>
> Ivan Kartyshov, reviewed by Tomas Vondra and Robert Haas.

### `3761fe3c` — Simplify the tranche machinery (2016-12-16, Robert Haas)

**What it did:** Removed `array_base`/`array_stride` and re-registered the buffer-mapping tranche by the name `"buffer_mapping"`. The user-visible effect is that LWLock waits, including buffer-mapping waits, all report as `LWLock` rather than the older `LWLockTranche`/`LWLockNamed` split — context for how the `BufferMapping` wait event surfaces today.

> Simplify LWLock tranche machinery by removing array_base/array_stride.
>
> array_base and array_stride were added so that we could identify the
> offset of an LWLock within a tranche, but this facility is only very
> marginally used apart from the main tranche.  So, give every lock in
> the main tranche its own tranche ID and get rid of array_base,
> array_stride, and all that's attached. [...]
>
> The main user-visible impact of this change is that pg_stat_activity
> will now report all waits for LWLocks as "LWLock" rather than
> reporting some as "LWLockTranche" and others as "LWLockNamed".

### `8c0d7baf` — DSA-backed hash tables borrow the partition count (2017-08-22, Andres Freund; patch by Thomas Munro)

**What it did:** Added `dshash`, whose `DSHASH_NUM_PARTITIONS` is defined as `1 << 7` (128) with a comment that it is "set to match `NUM_BUFFER_PARTITIONS` for now." This is the origin of the separate constant the page notes at [dshash.c#DSHASH_NUM_PARTITIONS](../../../../raw/postgres-18/src/backend/lib/dshash.c#L53-L60); it is a deliberate parallel value, not a use of the buffer-manager macro.

> Hash tables backed by DSA shared memory.
>
> Add general purpose chaining hash tables for DSA memory.  Unlike
> DynaHash in shared memory mode, these hash tables can grow as
> required, and cope with being mapped into different addresses in
> different backends. [...]
>
> Author: Thomas Munro
> Reviewed-By: John Gorman, Andres Freund, Dilip Kumar, Robert Haas

### `d03d7549` — Use offset macros for LWLock initialization (2020-11-24, Michael Paquier; patch by Japin Li)

**What it did:** Replaced hardcoded `NUM_INDIVIDUAL_LWLOCKS + NUM_BUFFER_PARTITIONS` offset arithmetic in LWLock setup with the existing `BUFFER_MAPPING_LWLOCK_OFFSET`-style macros. This is the form the page cites at [lwlock.c#InitializeLWLocks](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L498-L522) and the offset macros at [lwlock.h#fixed-lwlock-offsets](../../../../raw/postgres-18/src/include/storage/lwlock.h#L103-L110).

> Use macros instead of hardcoded offsets for LWLock initialization
>
> This makes the code slightly easier to follow, as the initialization
> relies on an offset that overlapped with an equivalent set of macros
> defined, which are used in other places already.
>
> Author: Japin Li

### `3ac88fdd` — Convert the partition macros to static inline functions (2022-07-27, Robert Haas; patch by Dilip Kumar)

**What it did:** Converted `BufTableHashPartition`, `BufMappingPartitionLock`, and `BufMappingPartitionLockByIndex` from preprocessor macros to `static inline` functions in `buf_internals.h`. This is the exact form the page cites today at [buf_internals.h#BufTableHashPartition](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L186-L209).

> Convert macros to static inline functions (buf_internals.h)
>
> Dilip Kumar, reviewed by Vignesh C, Ashutosh Sharma, and me.

## Context Reviewed

- [lwlock.h#NUM_BUFFER_PARTITIONS](../../../../raw/postgres-18/src/include/storage/lwlock.h#L86-L110)
- [buf_internals.h#BufferTag](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L94-L113)
- [buf_internals.h#BufTableHashPartition](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L186-L209)
- [buf_internals.h#BufferDesc](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L258-L271)
- [buf_table.c#InitBufTable](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L46-L66)
- [buf_table.c#BufTableHashCode](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L68-L81)
- [buf_table.c#BufTableLookup](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L83-L105)
- [buf_table.c#BufTableInsert](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L107-L139)
- [buf_table.c#BufTableDelete](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L141-L161)
- [freelist.c#StrategyShmemSize](../../../../raw/postgres-18/src/backend/storage/buffer/freelist.c#L448-L463)
- [freelist.c#StrategyInitialize](../../../../raw/postgres-18/src/backend/storage/buffer/freelist.c#L478-L489)
- [bufmgr.c#PrefetchSharedBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L557-L620)
- [bufmgr.c#BufferAlloc](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2008-L2166)
- [bufmgr.c#InvalidateBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2169-L2274)
- [bufmgr.c#InvalidateVictimBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2285-L2350)
- [bufmgr.c#GetVictimBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2353-L2505)
- [bufmgr.c#ExtendBufferedRelShared](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2623-L2842)
- [bufmgr.c#FindAndDropRelationBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L4840-L4897)
- [localbuf.c#InitLocalBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L780-L787)
- [dynahash.c#partitioned-hash-comment](../../../../raw/postgres-18/src/backend/utils/hash/dynahash.c#L6-L23)
- [dynahash.c#HASH_PARTITION-init](../../../../raw/postgres-18/src/backend/utils/hash/dynahash.c#L526-L539)
- [lwlock.c#InitializeLWLocks](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L498-L522)
- [lwlock.c#LWLockShmemSize](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L428-L455)
- [wait_event_names.txt#BufferMapping](../../../../raw/postgres-18/src/backend/utils/activity/wait_event_names.txt#L372-L379)
- [README#Buffer-Manager-Internal-Locking](../../../../raw/postgres-18/src/backend/storage/buffer/README#L100-L146)

## Evidence Map

| Claim | Source |
|---|---|
| `NUM_BUFFER_PARTITIONS` is `128` and contributes to fixed LWLock offsets | [lwlock.h#NUM_BUFFER_PARTITIONS](../../../../raw/postgres-18/src/include/storage/lwlock.h#L86-L110) |
| The shared buffer mapping table is partitioned to reduce contention | [buf_internals.h#BufTableHashPartition](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L186-L209) [README#partitioned-BufMappingLock](../../../../raw/postgres-18/src/backend/storage/buffer/README#L122-L128) |
| Partition selection is based on the `BufferTag` hash | [buf_table.c#BufTableHashCode](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L68-L81) [buf_internals.h#BufTableHashPartition](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L186-L209) |
| `InitBufTable()` creates the shared lookup table with `HASH_PARTITION` and `NUM_BUFFER_PARTITIONS` | [buf_table.c#InitBufTable](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L46-L66) |
| The lookup table is sized as `NBuffers + NUM_BUFFER_PARTITIONS` | [freelist.c#StrategyShmemSize](../../../../raw/postgres-18/src/backend/storage/buffer/freelist.c#L448-L463) [freelist.c#StrategyInitialize](../../../../raw/postgres-18/src/backend/storage/buffer/freelist.c#L478-L489) |
| Lookup requires at least shared partition lock; insert and delete require exclusive partition lock | [buf_table.c#BufTableLookup](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L83-L105) [buf_table.c#BufTableInsert](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L107-L139) [buf_table.c#BufTableDelete](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L141-L161) |
| Read miss allocation uses shared lookup, victim selection, exclusive insert, and duplicate-insert handling | [bufmgr.c#BufferAlloc-hit](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2008-L2066) [bufmgr.c#BufferAlloc-miss-insert](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2068-L2089) [bufmgr.c#BufferAlloc-insert-race](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2082-L2134) |
| Reuse and relation-drop paths delete old mappings under the old tag's partition lock | [bufmgr.c#InvalidateVictimBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2285-L2350) [bufmgr.c#InvalidateBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2169-L2274) |
| Relation extension inserts new block mappings under the matching partition lock | [bufmgr.c#ExtendBufferedRelShared-insert](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2730-L2756) |
| Waits on these locks report as the `BufferMapping` LWLock wait event | [lwlock.c#InitializeLWLocks](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L514-L522) [lwlock.c#LWLockReportWaitStart](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L732-L740) [wait_event_names.txt#BufferMapping](../../../../raw/postgres-18/src/backend/utils/activity/wait_event_names.txt#L372-L379) |
| The macro was introduced at `16` (2006) and raised to `128` (2014); accessors and offsets were later refactored | pinned `raw/postgres-18/` git history commits `10b9ca3d`, `3acc10c9`, `ea9df812`, `d03d7549`, `3ac88fdd` (see [Source Commit History](#source-commit-history)) |

## Source References

- [lwlock.h#NUM_BUFFER_PARTITIONS](../../../../raw/postgres-18/src/include/storage/lwlock.h#L86-L110) - defines `NUM_BUFFER_PARTITIONS`, fixed LWLock offsets, and `NUM_FIXED_LWLOCKS`.
- [buf_internals.h#BufferTag](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L94-L113) - defines the page identity key used by the shared buffer lookup table.
- [buf_internals.h#BufTableHashPartition](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L186-L209) - maps hash values to buffer mapping partitions and `MainLWLockArray` locks.
- [buf_internals.h#BufferDesc](../../../../raw/postgres-18/src/include/storage/buf_internals.h#L258-L271) - defines the shared buffer descriptor fields tied to lookup-table entries.
- [buf_table.c#locking-contract](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L1-L10) - states that callers must perform mapping-lock synchronization.
- [buf_table.c#InitBufTable](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L46-L66) - creates the partitioned shared buffer lookup table.
- [buf_table.c#BufTableHashCode](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L68-L81), [buf_table.c#BufTableLookup](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L83-L105), [buf_table.c#BufTableInsert](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L107-L139), and [buf_table.c#BufTableDelete](../../../../raw/postgres-18/src/backend/storage/buffer/buf_table.c#L141-L161) - implement hash computation, lookup, insert, and delete.
- [freelist.c#StrategyShmemSize](../../../../raw/postgres-18/src/backend/storage/buffer/freelist.c#L448-L463) and [freelist.c#StrategyInitialize](../../../../raw/postgres-18/src/backend/storage/buffer/freelist.c#L478-L489) - size and initialize the lookup table as `NBuffers + NUM_BUFFER_PARTITIONS`.
- [bufmgr.c#PrefetchSharedBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L557-L620) - shows shared-lock lookup for prefetch.
- [bufmgr.c#BufferAlloc](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2008-L2166) - shows normal shared lookup, exclusive insert, race handling, and tag assignment.
- [bufmgr.c#InvalidateBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2169-L2274), [bufmgr.c#InvalidateVictimBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2285-L2350), and [bufmgr.c#GetVictimBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2353-L2505) - remove old mappings during relation cleanup and buffer reuse.
- [bufmgr.c#ExtendBufferedRelShared](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2623-L2842) - inserts mapping entries for newly extended shared relation blocks.
- [bufmgr.c#FindAndDropRelationBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L4840-L4897) - uses partitioned lookup for small relation-drop/truncation ranges.
- [localbuf.c#InitLocalBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L780-L787) - creates the local buffer lookup hash without `HASH_PARTITION`.
- [localbuf.c#GetLocalPinLimit](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L305-L328) - the 18.6 `num_temp_buffers / 4` local pin limit.
- [rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-18/src/include/utils/rel.h#L664-L676) - names the buffer-manager entry points that reject other sessions' temp relations.
- [release-18.sgml#local-buffer-pin-limit](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L1996-L2014) - 18.6 release note for the local buffer pin limit.
- [dynahash.c#partitioned-hash-comment](../../../../raw/postgres-18/src/backend/utils/hash/dynahash.c#L6-L23), [dynahash.c#HASH_PARTITION-init](../../../../raw/postgres-18/src/backend/utils/hash/dynahash.c#L526-L539), and [dynahash.c#partitioned-bucket-init](../../../../raw/postgres-18/src/backend/utils/hash/dynahash.c#L700-L718) - explain and initialize partitioned dynahash behavior.
- [lwlock.c#LWLockShmemSize](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L428-L455), [lwlock.c#InitializeLWLocks](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L498-L522), and [lwlock.c#LWLockReportWaitStart](../../../../raw/postgres-18/src/backend/storage/lmgr/lwlock.c#L732-L740) - allocate, initialize, and report waits for LWLocks.
- [wait_event_names.txt#BufferMapping](../../../../raw/postgres-18/src/backend/utils/activity/wait_event_names.txt#L372-L379) - defines the user-visible `BufferMapping` LWLock wait event text.
- [dshash.c#DSHASH_NUM_PARTITIONS](../../../../raw/postgres-18/src/backend/lib/dshash.c#L53-L60) - records the separate dynamic shared hash constant that intentionally matches the buffer partition count.
- [README#Buffer-Manager-Internal-Locking](../../../../raw/postgres-18/src/backend/storage/buffer/README#L100-L146) - same-checkout design notes for buffer mapping locks, partitioning, and lock ordering.

## Open Questions

- There is no direct symbol-named regression or TAP test in the pinned PostgreSQL 18 checkout for `NUM_BUFFER_PARTITIONS`, `BufMappingPartitionLock`, `Shared Buffer Lookup Table`, or `BufferMapping`. The explanation above therefore relies on the implementation source and the same-checkout buffer-manager README.

## Related Pages

- [PostgreSQL 18](../../index.md)
- [versions](../../../versions.md)
