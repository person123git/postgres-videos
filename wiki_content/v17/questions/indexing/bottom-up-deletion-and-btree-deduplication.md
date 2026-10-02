---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# How Bottom-Up Index Deletion and B-Tree Deduplication Work in PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [One entry point, three strategies, one order](#one-entry-point-three-strategies-one-order)
  - [What makes each strategy eligible](#what-makes-each-strategy-eligible)
  - [Where the indexUnchanged hint comes from](#where-the-indexunchanged-hint-comes-from)
  - [Step 1: simple deletion](#step-1-simple-deletion)
  - [Step 2: bottom-up index deletion](#step-2-bottom-up-index-deletion)
  - [How heapam spends its budget](#how-heapam-spends-its-budget)
  - [Step 3: deduplication](#step-3-deduplication)
  - [The posting list tuple format](#the-posting-list-tuple-format)
  - [Single value strategy](#single-value-strategy)
  - [Posting list splits](#posting-list-splits)
  - [Deduplication during CREATE INDEX and REINDEX](#deduplication-during-create-index-and-reindex)
  - [Why deduplication needs allequalimage and bottom-up deletion does not](#why-deduplication-needs-allequalimage-and-bottom-up-deletion-does-not)
  - [Worked example 1: which strategy fires, for six workloads](#worked-example-1-which-strategy-fires-for-six-workloads)
  - [Worked example 2: the size of one posting list](#worked-example-2-the-size-of-one-posting-list)
  - [Worked example 3: reading posting lists with pageinspect](#worked-example-3-reading-posting-lists-with-pageinspect)
  - [Worked example 4: what the WAL shows](#worked-example-4-what-the-wal-shows)
  - [Worked example 5: turning deduplication off](#worked-example-5-turning-deduplication-off)
  - [Worked example 6: the regression tests that stage both mechanisms](#worked-example-6-the-regression-tests-that-stage-both-mechanisms)
  - [Key data structures](#key-data-structures)
  - [Locking](#locking)
  - [WAL and replay](#wal-and-replay)
  - [Error and corruption paths](#error-and-corruption-paths)
  - [How VACUUM differs](#how-vacuum-differs)
  - [Settings, reloptions, and catalog dependencies](#settings-reloptions-and-catalog-dependencies)
  - [Observability, and what you cannot see](#observability-and-what-you-cannot-see)
  - [Tests](#tests)
  - [Source history](#source-history)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Follow AGENTS.md. In PostgreSQL 17, explain how bottom-up index deletion and B-tree deduplication work. Provide examples.

> Prompt note: filed as an approved grammar-corrected restatement of "follow
> agents.md, in postgresql 17, question: explain how Bottom-up index deletion works
> and B-tree deduplication works, provide examples", per the repository's
> prompt-hygiene rule. The asker chose the corrected wording, chose
> **source-and-history scope** (no server was built, so this page carries no
> measurements), chose a single new page under `indexing`, and asked for
> comprehensive coverage of the adjacent mechanisms.

## Answer

### Short answer

Both are **leaf-page-local, last-second attempts to avoid a B-tree leaf page
split**, run from the same function on the insert path when the target page
cannot fit the incoming tuple. They differ in what they do with the page:

| | Bottom-up index deletion | Deduplication |
|---|---|---|
| Goal | Delete index tuples that are garbage | Re-encode surviving duplicates more compactly |
| Removes entries? | Yes, physically | No — same logical contents |
| Needs the table? | Yes, asks the table AM which TIDs are dead | No, works on the index page alone |
| Needs `allequalimage`? | No | Yes |
| Turned off by | Nothing | `deduplicate_items = off` |
| First shipped in | PostgreSQL 14 | PostgreSQL 13 |

The order is fixed and both are preceded by a third strategy: `_bt_findinsertloc`
calls `_bt_delete_or_dedup_one_page` when `PageGetFreeSpace(page) <
insertstate->itemsz` ([nbtinsert.c:899-907](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L899-L907)),
and that function runs **simple deletion first, then bottom-up deletion, then
deduplication**, stopping as soon as enough space exists
([nbtinsert.c#_bt_delete_or_dedup_one_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2654-L2782)).
If all three fail, the page splits.

Deduplication is the *last* line of defense, not the first: the nbtree README
calls it "our last line of defense against splitting a leaf page (bottom-up index
deletion may be attempted first, as our second last line of defense)"
([README:914-920](../../../../raw/postgres-17/src/backend/access/nbtree/README#L914-L920)).

Nothing in either mechanism changed in PostgreSQL 17. `nbtdedup.c` is
byte-identical to `REL_16_0` apart from its copyright line, and the heapam side is
identical to `REL_17_0`.

### One entry point, three strategies, one order

```text
btinsert
└── _bt_doinsert                                   nbtinsert.c
    ├── _bt_search_insert                          (exclusive lock on leaf page)
    ├── _bt_check_unique                           (sets LP_DEAD bits in passing)
    └── _bt_findinsertloc
        │   if PageGetFreeSpace(page) < itemsz:
        └── _bt_delete_or_dedup_one_page
            ├── 1. scan line pointer array for LP_DEAD items
            │   └── _bt_simpledel_pass ──► _bt_delitems_delete_check
            │                                └── table_index_delete_tuples
            │                                    └── heap_index_delete_tuples
            │       return if PageGetFreeSpace(page) >= itemsz
            ├── 2. _bt_bottomupdel_pass ──► _bt_delitems_delete_check
            │                                   └── (same tableam call, bottomup = true)
            │       return if it reports success
            └── 3. _bt_dedup_pass                  (no tableam call at all)
```

`_bt_delete_or_dedup_one_page` always begins by scanning the whole line pointer
array for `ItemIdIsDead` items, regardless of the `BTP_HAS_GARBAGE` page flag,
which it explicitly no longer consults
([nbtinsert.c:2669-2681](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2669-L2681)).
There are three call sites, and two of them ask for simple deletion only, via the
`simpleonly` argument: the `!heapkeyspace` (pg_upgrade'd version 2/3 index) loop
([nbtinsert.c:938-952](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L938-L952))
and the case where the new tuple's insert position overlaps an LP_DEAD-marked
posting list, where deleting early avoids clearing that bit during a posting list
split ([nbtinsert.c:990-1009](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L990-L1009)).

### What makes each strategy eligible

Four booleans decide everything. `checkingunique` is `checkUnique != UNIQUE_CHECK_NO`
([nbtinsert.c:101-138](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L101-L138)),
`indexUnchanged` is the executor hint, and `uniquedup` is derived
([nbtinsert.c:840-897](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L840-L897)):

- `uniquedup` starts as `indexUnchanged`.
- It becomes true if `_bt_check_unique` left `insertstate->low < insertstate->stricthigh`,
  meaning it encountered a duplicate.
- It becomes true if the unique check had to step right to a sibling page.
- It becomes true inside `_bt_delete_or_dedup_one_page` when simple deletion ran
  but did not free enough space — "Might as well assume duplicates"
  ([nbtinsert.c:2721-2733](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2721-L2733)).

Then:

| Strategy | Condition |
|---|---|
| Simple deletion | At least one `ItemIdIsDead` line pointer on the page |
| Early return | `simpleonly`, or `checkingunique && !uniquedup` |
| Bottom-up deletion | `indexUnchanged \|\| uniquedup` |
| Deduplication | `BTGetDeduplicateItems(rel) && itup_key->allequalimage` |

The `checkingunique && !uniquedup` early return is the documented "special
heuristic ... to determine whether a deduplication pass in a unique index should
take place", which lets an insert "skip straight to splitting a leaf page"
([btree.sgml:822-833](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L822-L833)).
It is also why a unique index never applies single value strategy: dedup is only
reached there with `uniquedup` true, which is passed down as `bottomupdedup = true`
([nbtinsert.c:2778-2781](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2778-L2781)).

### Where the indexUnchanged hint comes from

`indexUnchanged` is set per index, by the executor, only for an `UPDATE` whose
`table_tuple_update()` returned `TU_All` — that is, an update that could not use
HOT ([execIndexing.c#ExecInsertIndexTuples](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L260-L306)).
For each index it then calls `index_unchanged_by_update`, which caches its answer
in `IndexInfo` and returns true only when **no** key column of that index overlaps
`ExecGetUpdatedCols`/`ExecGetExtraUpdatedCols`, and no indexed expression contains
a `Var` in those sets ([execIndexing.c#index_unchanged_by_update](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L955-L1069)).
Three details matter:

- `INCLUDE` (non-key) column changes do not disqualify the hint — non-key values
  are "opaque payload state to the index AM"
  ([execIndexing.c:979-991](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L979-L991)).
- Index *predicates* are deliberately ignored, so a partial index still gets the
  hint ([execIndexing.c:1060-1068](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L1060-L1068)).
- Row-level `BEFORE` triggers do not change the answer, because they do not
  affect the `updatedCols` bitmaps
  ([execIndexing.c:986-989](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L986-L989)).

The hint reaches nbtree through `index_insert`
([indexam.c:213-235](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L213-L235))
and `btinsert` ([nbtree.c:180-198](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L180-L198)).
Every other core AM accepts the argument and ignores it. Logical replication's
apply worker takes care to build a proper `EState` so "the executor can correctly
pass down indexUnchanged hint"
([worker.c:2592-2601](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L2592-L2601)).

### Step 1: simple deletion

Simple deletion physically removes index tuples whose `LP_DEAD` bit is already
set, plus any "extra" tuples the table AM finds delete-safe for free.

`LP_DEAD` bits are hints set by two paths: `_bt_killitems`, after an index scan
told nbtree which returned TIDs were dead
([nbtutils.c#_bt_killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4139-L4348)),
and `_bt_check_unique`, which marks a conflicting entry killed when its whole HOT
chain is dead ([nbtinsert.c:676-696](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L676-L696)).
A posting list tuple can only be marked dead when **every** TID in it is dead
([nbtutils.c:4245-4310](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4245-L4310)),
which the README notes is not much of a problem in practice because LP_DEAD bits
are only a starting point
([README:546-555](../../../../raw/postgres-17/src/backend/access/nbtree/README#L546-L555)).

`_bt_simpledel_pass` then does something more ambitious than deleting just those
items ([nbtinsert.c#_bt_simpledel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2784-L2916)):

1. `_bt_deadblocks` builds a sorted, unique array of the table block numbers
   reached from LP_DEAD-marked tuples, **plus the incoming tuple's own block** —
   the one block simple deletion visits with no known-dead item on it, on the
   theory that recent garbage is concentrated there
   ([nbtinsert.c#_bt_deadblocks](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2918-L3005)).
2. Every TID on the page whose block is in that array is added to `deltids`, with
   `knowndeletable` set from `ItemIdIsDead`. Posting lists contribute each TID
   separately.
3. `_bt_delitems_delete_check` calls the table AM, then deletes what came back.

So the number of extra tuples deleted "might greatly exceed the number of LP_DEAD-marked
index tuples", because the table AM was going to read those blocks anyway
([nbtinsert.c:2799-2809](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2799-L2809)).
If this alone frees `insertstate->itemsz`, the function returns and neither of the
other two strategies runs.

### Step 2: bottom-up index deletion

Bottom-up deletion targets **version churn**: duplicates created by `UPDATE`s that
did not logically change this index's key columns. It never merges tuples; it only
deletes them ([nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L280-L421)).

It reuses the deduplication machinery to find duplicate groups. Walking the page
from `P_FIRSTDATAKEY`, it calls `_bt_dedup_start_pending` on the first item and
then, for each subsequent item, tests `_bt_keep_natts_fast(rel, state->base, itup) > nkeyatts`
and `_bt_dedup_save_htid(state, itup)`. Because `maxpostingsize` is set to `BLCKSZ`
— "We're not really deduplicating" — `_bt_dedup_save_htid` never refuses on size
grounds, so the intervals it forms are pure equality groups
([nbtdedup.c:323-336](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L323-L336)).

Each finished interval is handed to `_bt_bottomupdel_finish_pending`, which moves
its TIDs into the table AM's `deltids` array and decides which are **promising**
([nbtdedup.c#_bt_bottomupdel_finish_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L611-L753)):

- Plain non-pivot tuple: `promising = dupinterval`, i.e. true when the interval
  held more than one item. `freespace` is the real `ItemIdGetLength(itemid) + sizeof(ItemIdData)`.
- Posting list tuple: at most **one** TID in the whole posting list can be
  promising, on the "conservative assumption that there can only be at most one
  affected logical row per posting list tuple". Which one depends on where the
  list's blocks cluster: `firstpromising = (minblocklist == midblocklist)`, else
  `lastpromising = (midblocklist == maxblocklist)`, comparing the first, middle
  (`nitem / 2`) and last TIDs' block numbers. Every posting TID reports
  `freespace = sizeof(ItemPointerData)`, "at worst".

Two numbers are then sent to the table AM
([nbtdedup.c:337-359](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L337-L359)):

- `delstate.bottomup = true`, and every entry has `knowndeletable = false` — the
  interface forbids a bottom-up caller from claiming otherwise, "because
  everything is highly speculative"
  ([tableam.h:172-199](../../../../raw/postgres-17/src/include/access/tableam.h#L172-L199)).
- `delstate.bottomupfreespace = Max(BLCKSZ / 16, newitemsz)`, where `newitemsz`
  already includes the new line pointer. At the default `BLCKSZ` of 8192 that
  floor is **512 bytes**.

After `_bt_delitems_delete_check` returns, the pass reports success in one of two
ways ([nbtdedup.c:394-421](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L394-L421)):

- `neverdedup`: if `state->nintervals == 0` — no duplicate group at all — it
  returns true regardless of what was freed, purely to stop the caller wasting a
  deduplication pass.
- Otherwise it returns `PageGetExactFreeSpace(page) >= Max(BLCKSZ / 24, newitemsz)`,
  a **341-byte** floor at the default `BLCKSZ`. Note this is a *higher* bar than
  "the new item fits": the point is to not come straight back here on the next
  insert. The comment is explicit that the return value "is always just advisory
  information" and that it sometimes returns true having failed to free enough,
  which makes the caller skip dedup and split immediately.

### How heapam spends its budget

`heap_index_delete_tuples` is the only implementation of the
`index_delete_tuples` table AM callback
([heapam_handler.c:2626](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L2626),
[tableam.h#table_index_delete_tuples](../../../../raw/postgres-17/src/include/access/tableam.h#L1345-L1365)),
and it is in control of cost ([heapam.c#heap_index_delete_tuples](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8487-L8804)):

1. `index_delete_sort` puts `deltids` in TID order with a specialized insertion
   sort ([heapam.c#index_delete_sort](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8836-L8878)).
2. For bottom-up callers only, `bottomup_sort_and_shrink` groups TIDs by table
   block into `IndexDeleteCounts`, rounds each group's `npromisingtids` up to the
   next power of two — **with a floor of 4**, because "npromisingtids is far too
   noisy to trust when choosing between a pair of block groups that both have very
   low values" — sorts groups by descending promising count, then descending
   power-of-two-bucketed TID count, then ascending first-TID offset, and finally
   **discards everything outside the best `BOTTOMUP_MAX_NBLOCKS` = 6 blocks**
   ([heapam.c#bottomup_sort_and_shrink](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L9040-L9172),
   [heapam.c#bottomup_sort_and_shrink_cmp](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8982-L9038),
   [heapam.c#BOTTOMUP_MAX_NBLOCKS](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L205-L216)).
3. `bottomup_nblocksfavorable` counts how many of those blocks, starting from the
   first, are within `BOTTOMUP_TOLERANCE_NBLOCKS` = 3 blocks of the previous one.
   The first block is always favorable
   ([heapam.c#bottomup_nblocksfavorable](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8881-L8980)).
4. Prefetch distance is `maintenance_io_concurrency` (via the tablespace option,
   or the GUC directly for a catalog relation, to avoid syscache deadlock risk),
   capped at `nblocksfavorable` for bottom-up callers
   ([heapam.c:8540-8570](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8540-L8570),
   [heapam.c#index_delete_prefetch_buffer](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8384-L8428)).
5. Per TID, `heap_hot_search_buffer` with an `InitNonVacuumableSnapshot` decides
   deletability: if any tuple in the HOT chain is non-vacuumable the entry is
   skipped, otherwise `knowndeletable = true` and `istatus->freespace` is added to
   `actualfreespace` ([heapam.c:8689-8712](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8689-L8712)).
6. Three give-up rules run when the next TID is on a new block
   ([heapam.c:8586-8654](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8586-L8654)):
   - stop if the space target was already met on the previous block
     (`bottomup_final_block`);
   - stop if the last block freed nothing at all
     (`nblocksaccessed >= 1 && actualfreespace == lastfreespace`) — "the main way
     in which we keep the cost of bottom-up deletion under control";
   - otherwise, halve `curtargetfreespace` — but only once the favorable-block
     credit is exhausted, so contiguous blocks buy patience.
7. `snapshotConflictHorizon` is advanced from the heap tuple headers with
   `HeapTupleHeaderAdvanceConflictHorizon`, and an `LP_DEAD` line pointer
   terminates the walk because the earlier prune record already accounted for it
   ([heapam.c:8714-8790](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8714-L8790)).
8. `delstate->ndeltids` is shrunk to the last index actually processed. For a
   bottom-up caller this can legitimately be **zero**
   ([heapam.c:8794-8803](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8794-L8803)).

Back in nbtree, `_bt_delitems_delete_check` sorts `deltids` back into
leaf-page order on the `id` field, returns immediately if `ndeltids == 0`, and
otherwise classifies each index tuple into *delete the whole tuple* or *rewrite
the posting list without these TIDs*, the latter through `BTVacuumPosting` and
`_bt_update_posting`
([nbtpage.c#_bt_delitems_delete_check](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1474-L1679),
[nbtpage.c#_bt_delitems_cmp](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1459-L1472),
[nbtdedup.c#_bt_update_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L913-L994)).
That granular TID removal is exactly why the README rejects compressing posting
lists: it "would be a big problem for workloads that depend heavily on bottom-up
index deletion" ([README:931-942](../../../../raw/postgres-17/src/backend/access/nbtree/README#L931-L942)).

Only nbtree calls `table_index_delete_tuples` directly. GiST's `gistprunepage`
and hash's `_hash_vacuum_one_page` go through the generic shim
`index_compute_xid_horizon_for_tuples`, which hardcodes `bottomup = false` and
`knowndeletable = true` and exists only to obtain a conflict horizon
([genam.c#index_compute_xid_horizon_for_tuples](../../../../raw/postgres-17/src/backend/access/index/genam.c#L276-L345),
[gist.c:1695-1705](../../../../raw/postgres-17/src/backend/access/gist/gist.c#L1695-L1705),
[hashinsert.c:391-401](../../../../raw/postgres-17/src/backend/access/hash/hashinsert.c#L391-L401)).
**Bottom-up deletion is a B-tree-only feature.**

### Step 3: deduplication

Deduplication rewrites the page so that each run of equal tuples becomes one
posting list tuple: the key once, then a sorted array of table TIDs
([btree.sgml:747-759](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L747-L759)).
`_bt_dedup_pass` builds the result on a temporary page and swaps it in
([nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L33-L278)):

1. Initialize `BTDedupStateData` with `maxpostingsize = Min(BTMaxItemSize(page) / 2, INDEX_SIZE_MASK)`.
   The comment explains the choice: one third of a page would be legal, but one
   sixth "ought to leave us with a good split point when pages full of duplicates
   can be split several times"
   ([nbtdedup.c:75-99](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L75-L99)).
2. Decide `singlevalstrat` via `_bt_do_singleval`, but only when `!bottomupdedup`.
3. `PageGetTempPageCopySpecial`, copy the original LSN, copy the high key if the
   page is not rightmost.
4. Walk from `P_FIRSTDATAKEY` to `PageGetMaxOffsetNumber`. The first item starts a
   pending posting list. Each later item is merged if
   `_bt_keep_natts_fast(...) > nkeyatts` **and** `_bt_dedup_save_htid` accepts it;
   otherwise the pending list is finished with `_bt_dedup_finish_pending` and the
   item starts a new one. `Assert(!ItemIdIsDead(itemid))` encodes the contract that
   the caller already removed LP_DEAD items.
5. If `state->nintervals == 0`, nothing was merged: free the temp page and return
   without dirtying anything. Notably, the code does **not** check whether the
   savings are sufficient, because there is "some small value in nbtsplitloc.c
   always operating against a page that is fully deduplicated"
   ([nbtdedup.c:207-224](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L207-L224)).
6. Otherwise, clear `BTP_HAS_GARBAGE` "just to keep things tidy", enter a critical
   section, `PageRestoreTempPage`, `MarkBufferDirty`, and emit one
   `XLOG_BTREE_DEDUP` record.

The three helpers are shared with the bottom-up pass, index builds, and REDO:

- `_bt_dedup_start_pending` copies the base tuple's TID or existing posting list
  into `state->htids`, and sets `basetupsize` to `BTreeTupleGetPostingOffset(base)`
  for an existing posting list so the old array is not double-counted
  ([nbtdedup.c#_bt_dedup_start_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L423-L475)).
- `_bt_dedup_save_htid` refuses when
  `MAXALIGN(basetupsize + (nhtids + nhtids_new) * sizeof(ItemPointerData)) > maxpostingsize`,
  and in that case bumps `nmaxitems` **only if the list already holds more than 50
  TIDs** — a deliberately arbitrary limit that keeps the single-value counter from
  being confused by merely-large tuples
  ([nbtdedup.c#_bt_dedup_save_htid](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L477-L544)).
- `_bt_dedup_finish_pending` writes the base tuple unchanged when `nitems == 1`
  (space saving zero, no interval recorded), else forms the posting list, records
  the interval, and returns `phystupsize - (tuplesz + sizeof(ItemIdData))`
  ([nbtdedup.c#_bt_dedup_finish_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L546-L609)).

### The posting list tuple format

A posting list tuple is a non-pivot tuple that repurposes `t_tid`
([nbtree.h:432-466](../../../../raw/postgres-17/src/include/access/nbtree.h#L432-L466)):

```text
plain non-pivot:    t_tid (table TID) | t_info | key values
posting list:       t_tid (offset+n)  | t_info | key values | ItemPointerData[n]
```

`INDEX_ALT_TID_MASK` is set in `t_info` and `BT_IS_POSTING` (`0x2000`) in the
offset half of `t_tid`; the low 12 bits of that offset hold the TID count, and the
block half holds the byte offset at which the array starts
([nbtree.h#BTreeTupleSetPosting](../../../../raw/postgres-17/src/include/access/nbtree.h#L503-L515),
[nbtree.h#BTreeTupleIsPosting](../../../../raw/postgres-17/src/include/access/nbtree.h#L491-L501)).
`_bt_form_posting` always starts the array at a `MAXALIGN`'d offset, and a
one-TID "posting list" is impossible by construction — it degrades to a plain
tuple, which is what guarantees deduplication always shrinks the `MAXALIGN`'d
total ([nbtdedup.c#_bt_form_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L844-L911)).
Under assertions, `_bt_posting_valid` checks `n >= 2` and strictly ascending,
valid TIDs ([nbtdedup.c#_bt_posting_valid](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L1072-L1104)).

Because the count field is 12 bits and posting lists are capped at a sixth of a
page, `MaxTIDsPerBTreePage` — `(BLCKSZ - SizeOfPageHeaderData - sizeof(BTPageOpaqueData)) / sizeof(ItemPointerData)`
— sizes the per-page scratch arrays
([nbtree.h#MaxTIDsPerBTreePage](../../../../raw/postgres-17/src/include/access/nbtree.h#L174-L187)).

### Single value strategy

When a page holds nothing but copies of one value, merging everything would leave
`nbtsplitloc.c` no useful split point. `_bt_do_singleval` detects the case by
comparing the incoming tuple against **both** the first data item and the last
item on the page ([nbtdedup.c#_bt_do_singleval](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L755-L802)).
If both match, the pass changes behavior at two thresholds
([nbtdedup.c:174-201](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L174-L201)):

- at `nmaxitems == 5`, call `_bt_singleval_fillfactor`, which reduces
  `maxpostingsize` by `leftfree * ((100 - BTREE_SINGLEVAL_FILLFACTOR) / 100.0)`,
  i.e. 4% of the page's usable space, so the sixth list comes out smaller
  ([nbtdedup.c#_bt_singleval_fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L804-L842),
  [nbtree.h#BTREE_SINGLEVAL_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202));
- at `nmaxitems == 6`, set `state->deduplicate = false` and stop merging, leaving
  the tail of the page as plain tuples for the anticipated split to move to the
  new right sibling.

The upshot is that such a page ends up 96% full after it splits, "just like it
would if deduplication were disabled", and that several passes over the same page
are expected, the last of which frees nothing
([nbtdedup.c:755-779](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L755-L779)).

Single value strategy is skipped for bottom-up callers on purpose. Commit
`dd94c2852e6` explains why: applying it after a failed bottom-up pass "wastes
cycles because later bottom-up deletion passes will overinterpret older duplicate
tuples that deduplication actually just skipped over 'by design'", and it "makes
bottom-up deletion much less effective for low cardinality indexes that happen to
cross a meaningless 'index has single key value per leaf page' threshold".

### Posting list splits

If the incoming tuple's table TID falls *inside* an existing posting list's TID
range, the insert cannot simply be added — that would break the invariant that
posting list TIDs are sorted and the key space includes the heap TID. Instead
`_bt_binsrch_insert` reports `insertstate->postingoff > 0` and `_bt_insertonpg`
performs a **posting list split** in the same atomic action as the insert
([nbtinsert.c:1155-1201](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1155-L1201),
[README:990-1018](../../../../raw/postgres-17/src/backend/access/nbtree/README#L990-L1018)).

`_bt_swap_posting` shifts TIDs right from `postingoff` to make a hole, drops the
list's old maximum TID into the *new item*, and puts the new item's original TID
into the hole. The rewritten posting list is exactly the same size as before,
which is the whole point: page space accounting never has to know
([nbtdedup.c#_bt_swap_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L996-L1070)).
The in-place overwrite happens inside the insert's critical section
(`memcpy(oposting, nposting, ...)`) and is logged as `XLOG_BTREE_INSERT_POST`
([nbtinsert.c:1274-1290](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1274-L1290),
[nbtinsert.c:1325-1345](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1325-L1345));
REDO reconstructs it by calling the same `_bt_swap_posting`
([nbtxlog.c:200-225](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L200-L225)).

`_bt_findinsertloc` guards one edge: `postingoff == -1` means the overlapping
posting list is LP_DEAD-marked, so it runs simple deletion first and redoes the
binary search, asserting `postingoff == 0` afterwards
([nbtinsert.c:990-1009](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L990-L1009)).

### Deduplication during CREATE INDEX and REINDEX

Index builds deduplicate eagerly rather than lazily, packing each group of
duplicates before the leaf page is written
([btree.sgml:785-798](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L785-L798)).
`_bt_load` computes its gate as

```c
deduplicate = wstate->inskey->allequalimage && !btspool->isunique &&
    BTGetDeduplicateItems(wstate->index);
```

([nbtsort.c:1144-1152](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1144-L1152)),
so — unlike the insert path — **a unique index is never deduplicated at build
time**, and neither is the `merge` path that exists when a second spool holds dead
tuples. `allequalimage` is computed once by `_bt_allequalimage(wstate->index, true)`,
whose `debugmessage` argument emits the `DEBUG1` line `index "%s" can safely use deduplication`
([nbtsort.c:557-566](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L557-L566),
[nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183)).

The build loop uses the same `_bt_dedup_start_pending`/`_bt_dedup_save_htid`
helpers but its own finisher, `_bt_sort_dedup_finish_pending`, which adds the
tuple through `_bt_buildadd` and passes the posting list's byte overhead as
`truncextra` ([nbtsort.c:1264-1355](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1264-L1355),
[nbtsort.c#_bt_sort_dedup_finish_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1021-L1057)).
The size cap is different too: `maxpostingsize = MAXALIGN_DOWN(BLCKSZ * 10 / 100) - sizeof(ItemIdData)`,
chosen to reproduce a fillfactor of 90 "when there happen to be a great many
duplicates" — with the acknowledged side effect that higher leaf fillfactor
settings become ineffective for such indexes
([nbtsort.c:1287-1308](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1287-L1308)).

### Why deduplication needs allequalimage and bottom-up deletion does not

Deduplication throws away all but one physical copy of the key, so two datums that
compare equal must be *interchangeable*. That property is what `_bt_allequalimage`
establishes, per key column, from opclass support function 4
(`BTEQUALIMAGE_PROC`), and it is recorded once in the metapage field
`btm_allequalimage` at build time
([nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183),
[nbtree.h#BTEQUALIMAGE_PROC](../../../../raw/postgres-17/src/include/access/nbtree.h#L686-L712)).
`btequalimage` returns true unconditionally; `btvarstrequalimage` returns false for
a nondeterministic collation
([datum.c#btequalimage](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L415-L438),
[varlena.c#btvarstrequalimage](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L2595-L2613)).
`INCLUDE` indexes are rejected outright by the attribute-count test at the top of
`_bt_allequalimage`. The documented unsafe cases are nondeterministic-collation
`text`/`varchar`/`char`, `numeric` (display scale), `jsonb` (uses `numeric`
internally), `float4`/`float8` (`-0` versus `0`), container types, and `INCLUDE`
([btree.sgml:834-909](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L834-L909)).

Bottom-up deletion uses the *same* equality routine, `_bt_keep_natts_fast`, but
only to guess where version churn is. Since it merges nothing, the source says so
outright: "We deliberately omit an index-is-allequalimage test here"
([nbtinsert.c:2757-2776](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2776)).
`_bt_keep_natts_fast` compares with `datum_image_eq`, and its own comment records
the asymmetry: attributes it calls equal are definitely equal to `_bt_keep_natts`
too, and it is *guaranteed* to agree only in an all-equal-image index
([nbtutils.c#_bt_keep_natts_fast](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4852-L4905)).
So on a `numeric` or nondeterministic-collation index, bottom-up deletion still
works and deduplication never runs.

### Worked example 1: which strategy fires, for six workloads

Derived from the conditions in
[nbtinsert.c#_bt_delete_or_dedup_one_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2654-L2782)
and [nbtinsert.c:840-897](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L840-L897).
Each row assumes the target leaf page is already too full for the new tuple.

| Workload | LP_DEAD items? | `indexUnchanged` | `uniquedup` | What runs |
|---|---|---|---|---|
| `INSERT` of new values, non-unique index | no | false | false | nothing but the split |
| `INSERT` of new values, unique index (`checkingunique`, no dup seen) | no | false | false | early return, then split |
| `UPDATE` not touching this index's keys, no scans have run | no | **true** | true | bottom-up, then dedup |
| Same, but index scans set LP_DEAD bits first | yes | true | true | simple deletion; if it frees enough, nothing else |
| Repeated `DELETE` + `INSERT` of the same key, unique index | maybe | false | **true** (dup seen by `_bt_check_unique`) | bottom-up, then dedup |
| Bulk load of many duplicates, non-unique index | no | false | false | **dedup only** |

The last two rows are the two documented triggers: the README says bottom-up
deletion "is triggered within unique indexes in cases with continual INSERT and
DELETE related churn, since that is easy to detect without any external hint"
([README:557-569](../../../../raw/postgres-17/src/backend/access/nbtree/README#L557-L569)).
Row 6 is why an append-only duplicate-heavy index shrinks from deduplication while
getting nothing from bottom-up deletion.

### Worked example 2: the size of one posting list

Arithmetic from the cited definitions, on a build with `BLCKSZ` 8192 (the
`configure` default, [configure.ac:263-265](../../../../raw/postgres-17/configure.ac#L263-L265))
and `MAXALIGN` of 8. A single-column `int4` index, no nulls:

| Quantity | Derivation | Value |
|---|---|---|
| `sizeof(IndexTupleData)` | `ItemPointerData` (6, packed) + `unsigned short` (2) | 8 |
| Plain non-pivot tuple | `MAXALIGN(8 + 4)` in `index_form_tuple` | 16 |
| Line pointer | `sizeof(ItemIdData)` | 4 |
| Cost of one entry, not deduplicated | 16 + 4 | **20** |
| `SizeOfPageHeaderData` | `offsetof(PageHeaderData, pd_linp)` | 24 |
| `MAXALIGN(sizeof(BTPageOpaqueData))` | 4+4+4+2+2 = 16 | 16 |
| `BTMaxItemSize(page)` | `MAXALIGN_DOWN((8192 − MAXALIGN(24+12) − 16)/3) − MAXALIGN(6)` | 2704 |
| `maxpostingsize` | `Min(2704/2, 0x1FFF)` | 1352 |
| Largest posting list | `MAXALIGN(16 + n*6) ≤ 1352` | n = 222, 1352 bytes |
| Cost of one entry inside it | (1352 + 4) / 222 | **≈ 6.1** |

Sources: [itup.h#IndexTupleData](../../../../raw/postgres-17/src/include/access/itup.h#L35-L71),
[indextuple.c:150-167](../../../../raw/postgres-17/src/backend/access/common/indextuple.c#L150-L167),
[bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L211-L214),
[nbtree.h#BTPageOpaqueData](../../../../raw/postgres-17/src/include/access/nbtree.h#L62-L71),
[nbtree.h#BTMaxItemSize](../../../../raw/postgres-17/src/include/access/nbtree.h#L154-L168),
[nbtdedup.c:84-99](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L84-L99),
[nbtdedup.c:503-531](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L503-L531).

The same arithmetic reproduces a number printed in the documentation. The
`pageinspect` example page stores posting lists of "100 6 byte TIDs" for an
`int4`-like key and reports `itemlen` 616, which is exactly `16 + 100 * 6`
([pageinspect.sgml:406-439](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L406-L439)).

### Worked example 3: reading posting lists with pageinspect

`bt_page_items` decodes posting lists into a `tids` array, so a leaf page's
representation is directly inspectable. The documented example is a leaf page on
which every table-pointing tuple is a posting list
([pageinspect.sgml:406-439](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L406-L439)):

```text
test=# SELECT itemoffset, ctid, itemlen, nulls, vars, data, dead, htid, tids[0:2] AS some_tids
        FROM bt_page_items('tenk2_hundred', 5);
 itemoffset |   ctid    | itemlen | nulls | vars |          data           | dead |  htid  |      some_tids
------------+-----------+---------+-------+------+-------------------------+------+--------+---------------------
          1 | (16,1)    |      16 | f     | f    | 30 00 00 00 00 00 00 00 |      |        |
          2 | (16,8292) |     616 | f     | f    | 24 00 00 00 00 00 00 00 | f    | (1,6)  | {"(1,6)","(10,22)"}
```

Three things to read off it: `itemoffset` 1 is the high key; `ctid` on a posting
list tuple is *not* a table pointer but the encoded `(posting offset, count | BT_IS_POSTING)`
pair, which is why every posting row shows the same `(16,8292)`; and `htid` is the
decoded first table TID, populated "regardless of the underlying tuple
representation". `dead` is the `LP_DEAD` bit that feeds simple deletion. The array
is produced by `bt_page_items` from `BTreeTupleGetPosting`
([btreefuncs.c:590-606](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L590-L606)).

Whether deduplication is even possible for the index is a separate metapage
question: `bt_metap` exposes `allequalimage`
([btreefuncs.c#bt_metap](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L840-L922),
[pageinspect.sgml:305-315](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L305-L315)).

`amcheck` validates the same structure independently: `bt_index_check` raises
`posting list contains misplaced TID in index "%s"` if a posting list is not in
ascending TID order, and expands posting lists into plain tuples via
`bt_posting_plain_tuple` for its heapallindexed and rootdescend checks
([verify_nbtree.c:1520-1552](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L1520-L1552),
[verify_nbtree.c:3070-3082](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L3070-L3082)).

### Worked example 4: what the WAL shows

Both mechanisms are visible in `pg_waldump`, and they are distinguishable from
`VACUUM`'s work ([nbtdesc.c:51-83](../../../../raw/postgres-17/src/backend/access/rmgrdesc/nbtdesc.c#L51-L83),
[nbtdesc.c:163-193](../../../../raw/postgres-17/src/backend/access/rmgrdesc/nbtdesc.c#L163-L193)):

| Record | `rmgr` description format | Emitted by |
|---|---|---|
| `Btree/DEDUP` | `nintervals: %u` | a deduplication pass |
| `Btree/DELETE` | `snapshotConflictHorizon: %u, ndeleted: %u, nupdated: %u, isCatalogRel: %c` plus `deleted:`/`updated:` arrays | simple **and** bottom-up deletion |
| `Btree/VACUUM` | `ndeleted: %u, nupdated: %u` plus the same arrays | `VACUUM` only |
| `Btree/INSERT_POST` | (insert record) | an insert that split a posting list |

Two consequences follow from the table. First, a `DEDUP` record carries only an
interval count, because the intervals array is registered as buffer data that
`XLogInsert` can omit entirely when it stores a full-page image
([nbtdedup.c:245-268](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L245-L268)).
Second, **`Btree/DELETE` cannot tell you which of the two deletion strategies ran**:
`_bt_delitems_delete` is shared, and the README confirms "the same WAL records are
used for each operation"
([nbtpage.c#_bt_delitems_delete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1264-L1382),
[README:571-580](../../../../raw/postgres-17/src/backend/access/nbtree/README#L571-L580)).
`nupdated > 0` does tell you that some posting list had a subset of its TIDs
removed, and `delvacuum_desc` prints those per-list TID positions as
`{ off: %u, nptids: %u, ptids: [...] }`
([nbtdesc.c#delvacuum_desc](../../../../raw/postgres-17/src/backend/access/rmgrdesc/nbtdesc.c#L195-L254),
[nbtxlog.h#xl_btree_update](../../../../raw/postgres-17/src/include/access/nbtxlog.h#L258-L271)).

### Worked example 5: turning deduplication off

The reloption is documented with this example
([create_index.sgml:911-915](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L911-L915)):

```sql
CREATE INDEX title_idx ON films (title) WITH (deduplicate_items = off);
```

Behavior worth knowing before using it:

- The default is `on`, and the reloption is B-tree-only
  ([create_index.sgml#deduplicate_items](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L448-L476),
  [reloptions.c:159-168](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L168)).
- `BTGetDeduplicateItems` defaults to `true` when the index has no `rd_options` at
  all ([nbtree.h#BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1129-L1151)).
- Setting it off via `ALTER INDEX` "prevents future insertions from triggering
  deduplication, but does not in itself make existing posting list tuples use the
  standard tuple representation". The reloption's lock level is
  `ShareUpdateExclusiveLock`, with the comment "since it applies only to later
  inserts".
- It does **not** disable bottom-up deletion, which has no off switch.
- The documentation's own advice is that disabling "isn't usually helpful", the
  penalty being "small, fixed" for write-heavy indexes with no duplicates and zero
  for read-only workloads ([btree.sgml:799-833](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L799-L833)).

### Worked example 6: the regression tests that stage both mechanisms

`src/test/regress/sql/btree_index.sql` contains the only in-tree SQL written
specifically for these paths
([btree_index.sql:205-231](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L205-L231)):

```sql
-- get test coverage for "single value" deduplication strategy:
insert into btree_bpchar select 'foo' from generate_series(1,1500);

CREATE TABLE dedup_unique_test_table (a int) WITH (autovacuum_enabled=false);
CREATE UNIQUE INDEX dedup_unique ON dedup_unique_test_table (a) WITH (deduplicate_items=on);
CREATE UNIQUE INDEX plain_unique ON dedup_unique_test_table (a) WITH (deduplicate_items=off);
DO $$
BEGIN
    FOR r IN 1..1350 LOOP
        DELETE FROM dedup_unique_test_table;
        INSERT INTO dedup_unique_test_table SELECT 1;
    END LOOP;
END$$;

-- Exercise the LP_DEAD-bit-set tuple deletion code with a posting list tuple.
-- The implementation prefers deleting existing items to merging any duplicate
-- tuples into a posting list, so we need an explicit test to make sure we get
-- coverage (note that this test also assumes BLCKSZ is 8192 or less):
DROP INDEX plain_unique;
DELETE FROM dedup_unique_test_table WHERE a = 1;
INSERT INTO dedup_unique_test_table SELECT i FROM generate_series(0,450) i;
```

Reading it against the code above: the 1,500-row `'foo'` insert is what drives
`_bt_do_singleval` to true; the `dedup_unique`/`plain_unique` pair contrasts
insert-time deduplication with a unique index that has it disabled; the 1,350-iteration
`DELETE`/`INSERT` loop is exactly the "continual INSERT and DELETE related churn"
that the README names as the non-hint trigger for bottom-up deletion in a unique
index; and the final block's comment states the priority order — deletion before
merging — as a testing problem. `autovacuum_enabled=false` keeps `VACUUM` from
doing the cleanup instead. The expected output records no plan or size output for
any of this ([btree_index.out:412-437](../../../../raw/postgres-17/src/test/regress/expected/btree_index.out#L412-L437)),
so the test only proves the code paths do not crash or corrupt.

### Key data structures

| Structure | Where | Role |
|---|---|---|
| `BTDedupStateData` | [nbtree.h:837-893](../../../../raw/postgres-17/src/include/access/nbtree.h#L837-L893) | whole-pass state: `deduplicate`, `nmaxitems`, `maxpostingsize`, the pending list (`base`, `baseoff`, `basetupsize`, `htids`, `nhtids`, `nitems`, `phystupsize`) and the `intervals` array |
| `BTDedupInterval` | [nbtree.h:837-845](../../../../raw/postgres-17/src/include/access/nbtree.h#L837-L845) | `(baseoff, nitems)` pair; the WAL payload of a dedup record |
| `BTVacuumPostingData` | [nbtree.h:895-914](../../../../raw/postgres-17/src/include/access/nbtree.h#L895-L914) | a posting list to rewrite: original `itup`, `updatedoffset`, and the `deletetids` positions |
| `TM_IndexDelete` | [tableam.h:217-221](../../../../raw/postgres-17/src/include/access/tableam.h#L217-L221) | 8 bytes: table TID plus an `id` back-reference, kept small so sorting is fast |
| `TM_IndexStatus` | [tableam.h:223-231](../../../../raw/postgres-17/src/include/access/tableam.h#L223-L231) | `idxoffnum`, `knowndeletable`, `promising`, `freespace` |
| `TM_IndexDeleteOp` | [tableam.h:233-262](../../../../raw/postgres-17/src/include/access/tableam.h#L233-L262) | the operation: `irel`, `iblknum`, `bottomup`, `bottomupfreespace`, and the two mutable arrays |
| `IndexDeleteCounts` | [heapam.c:205-216](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L205-L216) | heapam's per-block group: `npromisingtids`, `ntids`, `ifirsttid` |
| `IndexDeletePrefetchState` | [heapam.c:191-201](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L191-L201) | prefetch cursor over `deltids` |

The two-array split in `TM_IndexDeleteOp` is a deliberate performance choice, and
the `id` field is the contract that lets nbtree restore leaf-page order after the
table AM has reordered and shrunk the array
([tableam.h:162-216](../../../../raw/postgres-17/src/include/access/tableam.h#L162-L216)).

### Locking

Both mechanisms run while the backend holds an **exclusive buffer lock** on the
one leaf page. `_bt_doinsert` documents that `insertstate.buf` comes back "locked
in exclusive mode", and `_bt_search_insert` gets there either through the
rightmost-page fastpath's `_bt_conditionallockbuf` or through
`_bt_search(..., BT_WRITE, ...)`
([nbtinsert.c:160-167](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L160-L167),
[nbtinsert.c#_bt_search_insert](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L316-L381)).
Neither needs a cleanup lock, unlike `VACUUM`: "Opportunistic index tuple deletion
performs almost the same page-level modifications while only holding an exclusive
lock. This is safe because there is no question of TID recycling taking place
later on — only VACUUM can make TIDs recyclable"
([README:189-193](../../../../raw/postgres-17/src/backend/access/nbtree/README#L189-L193)).

Inside `heap_index_delete_tuples` the backend additionally takes a **share** lock
on each visited heap buffer, one at a time, releasing the previous one before
reading the next ([heapam.c:8656-8679](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8656-L8679)).
That is the reason the prefetch-distance code checks `IsCatalogRelation` first:
the caller already holds a buffer lock in the index, so syscache lookups must be
avoided to remove deadlock risk
([heapam.c:8547-8558](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8547-L8558)).
No heavyweight lock is taken by either mechanism, and neither writes to the table.

### WAL and replay

- Deduplication emits one `XLOG_BTREE_DEDUP` record per pass, carrying
  `nintervals` and the intervals array as registered buffer data
  ([nbtdedup.c:240-270](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L240-L270),
  [nbtxlog.h#xl_btree_dedup](../../../../raw/postgres-17/src/include/access/nbtxlog.h#L163-L177)).
  `btree_xlog_dedup` replays it by re-running the merge from the intervals, using
  a deliberately larger `maxpostingsize` than the primary
  ("Conservatively use larger maxpostingsize than primary") and asserting that the
  intervals it reconstructs `memcmp`-match the logged ones
  ([nbtxlog.c#btree_xlog_dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L463-L554)).
- Both deletion strategies emit `XLOG_BTREE_DELETE` with a
  `snapshotConflictHorizon` and `isCatalogRel`, used to generate recovery
  conflicts on a standby. The horizon is zeroed when `!XLogStandbyInfoActive()`
  ([nbtpage.c:1516-1531](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1516-L1531),
  [nbtxlog.h#xl_btree_delete](../../../../raw/postgres-17/src/include/access/nbtxlog.h#L197-L256)).
  This is the one structural difference from `xl_btree_vacuum`, which has no
  horizon field at all; the other is that only `_bt_delitems_vacuum` clears the
  page's vacuum cycle ID
  ([nbtpage.c:1264-1282](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1264-L1282)).
- A posting list split rides along in the insert's own record as
  `XLOG_BTREE_INSERT_POST`, or in the page split record's `postingoff` field —
  the README's justification is that a single atomic action both avoids
  concurrency problems and "minimizes the volume of extra WAL required for a
  posting list split, since we don't have to explicitly WAL-log the original
  posting list tuple" ([README:990-1007](../../../../raw/postgres-17/src/backend/access/nbtree/README#L990-L1007)).
- Nothing here is unlogged-index-specific: `RelationNeedsWAL(rel)` gates both
  record types.

### Error and corruption paths

| Condition | Behavior |
|---|---|
| Posting list split at offset 0 or ≥ `nhtids` | `ERROR "posting list tuple with %d items cannot be split at offset %d"` — a sanity check for corruption "known to happen in the field from time to time" ([nbtdedup.c:1033-1045](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L1033-L1045)) |
| Overlapping "posting list" is actually a plain tuple, or is LP_DEAD | `ERRCODE_INDEX_CORRUPTED`, `"table tid from new index tuple (%u,%u) overlaps with invalid duplicate tuple at offset %u of block %u"` ([nbtinsert.c:1173-1192](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1173-L1192)) |
| Index TID points past the heap page's line pointer array, at an unused item, or at a heap-only tuple | three `ERRCODE_INDEX_CORRUPTED` reports from `index_delete_check_htid`, checked on every deletion pass ([heapam.c#index_delete_check_htid](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8430-L8485)) |
| Rebuilt page will not accept a tuple | `ERROR "deduplication failed to add tuple to page"` / `"deduplication failed to add highkey"` ([nbtdedup.c:566-595](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L566-L595)) |
| Same, during REDO | additionally `ERROR "deduplication failed to add heap tid to pending posting list"` ([nbtxlog.c:519-533](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L519-L533)) |
| Overwriting a shortened posting list fails | `PANIC "failed to update partially dead item in block %u of index \"%s\""` ([nbtpage.c:1309-1321](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1309-L1321)) |

`index_delete_check_htid` is the hardening added in PostgreSQL 15 by
`e7428a99a13`; the same commit relaxed the `offnum > maxoff` case from an error to
a loop break, since "an offset past the end of page's line pointer array is
possible when the array was truncated"
([heapam.c:8726-8740](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8726-L8740)).

The one-third-of-a-page limit never bites deduplication, because `maxpostingsize`
is at most half of `BTMaxItemSize(page)` and `_bt_dedup_finish_pending` asserts
`tuplesz <= BTMaxItemSize(newpage)`; `_bt_check_third_page` is reached only from
`_bt_findinsertloc` for the incoming tuple
([nbtinsert.c:829-832](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L829-L832),
[nbtutils.c#_bt_check_third_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5080-L5127)).

### How VACUUM differs

`VACUUM` reaches the same page-modification code through a different door, and the
distinction is the documented one: bottom-up deletion is *qualitative* and
page-local, autovacuum is *quantitative* and table-wide
([btree.sgml:656-678](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L656-L678)).

| | Bottom-up / simple deletion | `VACUUM` (`btvacuumscan`) |
|---|---|---|
| Trigger | an insert that would split a page | table-level thresholds |
| Scope | one leaf page | every leaf page, in a linear scan |
| Lock | exclusive buffer lock | full cleanup lock on every leaf page |
| Decides deadness by | `heap_hot_search_buffer` with a non-vacuumable snapshot | the `IndexBulkDeleteCallback` over collected dead TIDs |
| Posting lists | `_bt_delitems_delete_check` → `_bt_update_posting` | `btreevacuumposting` → `_bt_delitems_vacuum` |
| WAL | `XLOG_BTREE_DELETE` | `XLOG_BTREE_VACUUM` |
| Can free pages / truncate | no | yes (page deletion, FSM) |

`btvacuumpage` handles posting lists with the identical `BTVacuumPosting`
mechanism, batching one `_bt_delitems_vacuum` call per page "so as to minimize WAL
traffic" ([nbtree.c:1240-1320](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1240-L1320)).

The documentation is explicit that bottom-up deletion does not replace `VACUUM`:
it "does not provide any strong guarantees about how old the oldest garbage index
tuple may be", and an exhaustive clean sweep is still eventually required because
only that makes table TID recycling safe
([btree.sgml:704-733](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L704-L733)).
Conversely, "it's quite possible that the on-disk size of certain indexes will
never increase by even one single page/block despite *constant* version churn".

### Settings, reloptions, and catalog dependencies

| Knob | Kind | Apply scope | Effect here |
|---|---|---|---|
| `deduplicate_items` | B-tree index reloption, default `on` | `ALTER INDEX` takes `ShareUpdateExclusiveLock`; affects later inserts only, no rebuild | gates the deduplication pass and build-time deduplication |
| `maintenance_io_concurrency` | GUC, `PGC_USERSET`, default 10 with `USE_PREFETCH` | session/transaction scope (`SET` is enough; no reload or restart) | prefetch distance in `heap_index_delete_tuples`, capped at `nblocksfavorable` for bottom-up |
| `maintenance_io_concurrency` tablespace option | tablespace option | `ALTER TABLESPACE`; read per call | overrides the GUC for the index's tablespace |
| `fillfactor` | B-tree index reloption, default 90 | affects splits and builds | not consulted by either pass; build-time dedup caps posting lists at 10% of `BLCKSZ` instead |

Sources: [reloptions.c:159-168](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L168),
[nbtree.h#BTOptions](../../../../raw/postgres-17/src/include/access/nbtree.h#L1129-L1151),
[guc_tables.c#maintenance_io_concurrency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3123-L3136),
[bufmgr.h#DEFAULT_MAINTENANCE_IO_CONCURRENCY](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L157-L166),
[spccache.c#get_tablespace_maintenance_io_concurrency](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L222-L237),
[nbtsort.c:1287-1308](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1287-L1308).

There is **no** GUC for either mechanism: no way to disable bottom-up deletion, no
way to force a deduplication pass, no cost-delay hook, and no per-table control.

Two build-time / catalog dependencies are worth naming because they are what make
deduplication possible at all:

- Support function 4 rows in `pg_amproc.dat`, plus the `pg_proc.dat` entries they
  name. The collation-sensitive character opclasses register the conditional
  function: `text_ops` for both `text` and `name`
  ([pg_amproc.dat:201-212](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L201-L212))
  and `bpchar_ops` for `bpchar`
  ([pg_amproc.dat:28-35](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L28-L35)),
  while `text_pattern_ops` and `bpchar_pattern_ops` register the unconditional
  `btequalimage`
  ([pg_amproc.dat:240-249](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L240-L249)).
  The documented-unsafe families register **no** support function 4 at all —
  `numeric_ops`, `float_ops`, `jsonb_ops`, `array_ops`, `record_ops` and
  `range_ops` each have zero `amprocnum => '4'` rows — which
  `_bt_allequalimage`'s `!OidIsValid(equalimageproc)` branch treats as unsafe
  ([nbtutils.c:5149-5170](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5149-L5170)).
  These are generated-catalog data, so adding an equal-image function to an
  opclass is a `genbki.pl` change plus a catalog version bump
  ([pg_proc.dat#btvarstrequalimage](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L1055-L1057),
  [nbtree.h#BTNProcs](../../../../raw/postgres-17/src/include/access/nbtree.h#L686-L712)).
- The metapage field `btm_allequalimage`, written once at build time and read back
  through the insertion scan key. A `pg_upgrade`d index from before PostgreSQL 13
  has it zero, which is a separate topic covered by
  [Checking Whether an Index Needs a Rebuild to Enable Deduplication After pg_upgrade From PostgreSQL 12 to 17 (unverified)](btree-deduplication-after-pg-upgrade.md).

### Observability, and what you cannot see

What exists:

- `pg_waldump` output — `Btree/DEDUP` and `Btree/DELETE` records, per the table
  above.
- `pageinspect`'s `bt_page_items` (`tids`, `dead`, `itemlen`) and `bt_metap`
  (`allequalimage`).
- `CREATE INDEX`'s `DEBUG1` verdict, `index "%s" can safely use deduplication`
  ([nbtutils.c:5172-5180](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5172-L5180)).
- Index size, indirectly, via `pg_relation_size` and `pgstatindex`.

What does not exist in PostgreSQL 17:

- No counter anywhere for deduplication passes, bottom-up passes, index tuples
  deleted opportunistically, or page splits avoided. `pg_stat_all_indexes` exposes
  only `idx_scan`, `idx_tup_read` and `idx_tup_fetch`.
- No wait event, progress view, or `EXPLAIN` field for any of it.
- No way to distinguish simple from bottom-up deletion after the fact, because
  they share `XLOG_BTREE_DELETE`.
- `pgstatindex`'s `avg_leaf_density` counts posting lists as ordinary tuples, so a
  deduplicated index's density figure is not comparable with a non-deduplicated
  one; see [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)](btree-index-bloat-core-sql-only.md).

### Tests

| Test | What it covers |
|---|---|
| [btree_index.sql:205-231](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L205-L231) | single value strategy, unique-index deduplication on/off, LP_DEAD deletion of a posting list tuple |
| [btree_index.sql:186-190](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L186-L190) | `deduplicate_items=on` on a `bpchar_ops` index |
| [check_btree.sql:14-18](../../../../raw/postgres-17/contrib/amcheck/sql/check_btree.sql#L14-L18) | `amcheck` over an index built `WITH (deduplicate_items = ON)` |
| [004_verify_nbtree_unique.pl:115-133](../../../../raw/postgres-17/contrib/amcheck/t/004_verify_nbtree_unique.pl#L115-L133) | unique-violation detection with deduplication both off and on |
| [005_opclass_damage.pl:45-52](../../../../raw/postgres-17/src/bin/pg_amcheck/t/005_opclass_damage.pl#L45-L52) | `deduplicate_items = off` used to isolate a broken-opclass case |
| [btree.out:1-16](../../../../raw/postgres-17/contrib/pageinspect/expected/btree.out#L1-L16) | `bt_metap` output including `allequalimage` |

The gap: **no test in this checkout names bottom-up index deletion**, and there is
no injection point, `DEBUG` message, or assertion output that would let a test
observe a bottom-up pass. Searching the whole `src/test` tree and every contrib
test directory for `bottom-up`/`bottomup` returns nothing. The closest coverage is
the `dedup_unique_test_table` `DELETE`/`INSERT` loop, which creates precisely the
unique-index churn the README names as bottom-up deletion's non-hint trigger — but
the test asserts nothing about it.

### Source history

Dates below come from presence tests of the defining symbol at each release tag in
this checkout, not from `git tag --contains`. Both features are Peter Geoghegan's.

| Commit | Date | First release | Change |
|---|---|---|---|
| `0d861bbb702` | 2020-02-26 | 13 | `Add deduplication to nbtree.` Creates `nbtdedup.c`, the posting list format, `XLOG_BTREE_DEDUP`, `btm_allequalimage`, support function 4, and the `deduplicate_items` reloption |
| `84ec9b231a8` | 2020-03-01 | 13 | `Remove dead code from _bt_update_posting().` |
| `77b88bd5dc9` | 2020-03-02 | 13 | `Add assertions to _bt_update_posting().` |
| `a7b9d24e4e0` | 2020-03-28 | 13 | `Make deduplication use number of key attributes.` |
| `be14f884d57` | 2020-06-19 | 14 | `Fix deduplication "single value" strategy bug.` |
| `cf2acaf4dcb` | 2020-11-17 | 14 | `Deprecate nbtree's BTP_HAS_GARBAGE flag.` Makes deleting LP_DEAD items the caller's job |
| `d168b666823` | 2021-01-13 | 14 | `Enhance nbtree index tuple deletion.` Adds bottom-up deletion, `_bt_simpledel_pass`, and the `TM_IndexDeleteOp` interface |
| `8f72bbac3e4` | 2021-05-14 | 14 | `Harden nbtree deduplication posting split code.` |
| `dd94c2852e6` | 2021-09-21 | 15 | `Fix "single value strategy" index deletion issue.` Stops a bottom-up caller from applying single value strategy |
| `a5213adf3d3` | 2021-10-27 | 15 | `Further harden nbtree posting split code.` |
| `e7428a99a13` | 2021-11-04 | 15 | `Add hardening to catch invalid TIDs in indexes.` Adds `index_delete_check_htid` |
| `f68faf4c753` | 2022-08-05 | 16 | `Fix comments about deduplication updating page.` |
| `06e0652750e` | 2023-04-18 | 16 | `Remove useless argument from nbtree dedup function.` Drops `_bt_dedup_pass`'s now-unused `heapRel` |
| `3b42bdb4716` | 2024-02-16 | 17 | `Use new overflow-safe integer comparison functions.` Rewrites `_bt_blk_cmp` and `_bt_delitems_cmp` as `pg_cmp_u32`/`pg_cmp_s16` |

The v13 presence test: `src/backend/access/nbtree/nbtdedup.c` does not exist at
`REL_12_0`, contains `_bt_dedup_start_pending` from `REL_13_0` onward, and gains
`_bt_bottomupdel_pass` at `REL_14_0`.

What PostgreSQL 17 changed: **nothing behavioral.** `nbtdedup.c` differs from
`REL_16_0` by one line, its copyright year. The heapam region containing
`index_delete_prefetch_buffer`, `index_delete_check_htid`,
`heap_index_delete_tuples`, `bottomup_nblocksfavorable`,
`bottomup_sort_and_shrink_cmp` and `bottomup_sort_and_shrink` is identical to
`REL_17_0` and differs from `REL_16_0` only in a comment that renames
`XLOG_HEAP2_PRUNE` to `XLOG_HEAP2_PRUNE_VACUUM_SCAN`. `BOTTOMUP_MAX_NBLOCKS` = 6,
`BOTTOMUP_TOLERANCE_NBLOCKS` = 3, the `npromisingtids <= 4` floor and the
`curtargetfreespace /= 2` decay are textually unchanged at every tag from
`REL_14_0` to the pin. In particular, v17's read-stream work did **not** convert
this path: `index_delete_prefetch_buffer` still issues one `PrefetchBuffer` per
new block, and `heap_index_delete_tuples` still calls `ReadBuffer` directly.

## Context Reviewed

- Insert path and both strategies: `src/backend/access/nbtree/nbtinsert.c`
  (`_bt_doinsert`, `_bt_check_unique`, `_bt_findinsertloc`, `_bt_insertonpg`,
  `_bt_delete_or_dedup_one_page`, `_bt_simpledel_pass`, `_bt_deadblocks`,
  `_bt_blk_cmp`), `nbtdedup.c` in full, `nbtpage.c`
  (`_bt_delitems_delete_check`, `_bt_delitems_delete`, `_bt_delitems_cmp`,
  `_bt_delitems_update`), `nbtutils.c` (`_bt_killitems`, `_bt_keep_natts_fast`,
  `_bt_allequalimage`, `_bt_check_third_page`), `nbtsort.c` (`_bt_load`,
  `_bt_sort_dedup_finish_pending`), `nbtree.c` (`btinsert`, `btvacuumpage`),
  `nbtxlog.c` (`btree_xlog_dedup`, `btree_xlog_insert`, `btree_xlog_delete`),
  `src/include/access/nbtree.h`, `src/include/access/nbtxlog.h`.
- Table AM side: `src/include/access/tableam.h`,
  `src/backend/access/heap/heapam.c` (`heap_index_delete_tuples`,
  `index_delete_sort`, `index_delete_prefetch_buffer`, `index_delete_check_htid`,
  `bottomup_sort_and_shrink`, `bottomup_nblocksfavorable`),
  `src/backend/access/heap/heapam_handler.c`,
  `src/backend/access/index/genam.c`, and the two other AM callers
  `src/backend/access/gist/gist.c`, `src/backend/access/hash/hashinsert.c`.
- Executor hint: `src/backend/executor/execIndexing.c`,
  `src/backend/access/index/indexam.c`,
  `src/backend/replication/logical/worker.c`.
- Equal-image support: `src/backend/utils/adt/datum.c`,
  `src/backend/utils/adt/varlena.c`, `src/include/catalog/pg_amproc.dat`,
  `src/include/catalog/pg_proc.dat`.
- Tuple and page layout arithmetic: `src/include/access/itup.h`,
  `src/backend/access/common/indextuple.c`, `src/include/storage/bufpage.h`,
  `src/include/storage/itemptr.h`, `src/include/storage/itemid.h`,
  `configure.ac` (`--with-blocksize` default).
- Settings: `src/backend/access/common/reloptions.c`,
  `src/backend/utils/misc/guc_tables.c`, `src/include/storage/bufmgr.h`,
  `src/backend/utils/cache/spccache.c`.
- WAL description: `src/backend/access/rmgrdesc/nbtdesc.c`.
- Design documentation: `src/backend/access/nbtree/README` (Simple deletion,
  Bottom-Up deletion, Notes about deduplication, Deduplication in unique indexes,
  Posting list splits, VACUUM cleanup-lock sections).
- User documentation: `doc/src/sgml/btree.sgml`,
  `doc/src/sgml/ref/create_index.sgml`, `doc/src/sgml/pageinspect.sgml`,
  `doc/src/sgml/indexam.sgml`.
- Tests and tooling: `src/test/regress/sql/btree_index.sql` and its expected
  output, `contrib/amcheck/sql/check_btree.sql`,
  `contrib/amcheck/t/004_verify_nbtree_unique.pl`,
  `src/bin/pg_amcheck/t/005_opclass_damage.pl`,
  `contrib/pageinspect/btreefuncs.c`, `contrib/pageinspect/expected/btree.out`,
  `contrib/amcheck/verify_nbtree.c`. Exhaustive search of `src/test` and every
  contrib test directory for `bottom-up`/`bottomup` (no matches).
- Source history in this checkout: `git log` over
  `src/backend/access/nbtree/nbtdedup.c` and `nbtinsert.c` since `0d861bbb702`
  and `d168b666823`; `git merge-base --is-ancestor` against `REL_13_0` through
  `REL_17_0` for each commit listed; `git grep` presence tests of
  `_bt_dedup_start_pending` and `_bt_bottomupdel_pass` at `REL_12_0` through
  `REL_17_0`; `git diff` of `nbtdedup.c` and of the extracted heapam
  index-deletion region across `REL_14_0`, `REL_16_0`, `REL_17_0` and the pin.
- Pinned checkout `raw/postgres-17/` at commit
  `786db8dcf168bd9df8f55047337525ac19118b1c` (PostgreSQL 17.11,
  `REL_17_11-7-g786db8dcf16`), verified clean with an empty
  `git status --porcelain`.
- **No server was built and nothing on this page was measured**, per the asker's
  choice of source-and-history scope. Every number is either a constant from the
  cited source, arithmetic over cited constants (labelled as such), or output
  quoted from the checkout's own documentation.

## Evidence Map

| Claim | Source |
|---|---|
| Both run from one function, in a fixed order, only when the page is too full | [nbtinsert.c#_bt_delete_or_dedup_one_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2654-L2782), [nbtinsert.c:899-907](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L899-L907) |
| Deduplication is the last line of defense, bottom-up the second last | [README:914-920](../../../../raw/postgres-17/src/backend/access/nbtree/README#L914-L920) |
| `BTP_HAS_GARBAGE` is no longer a gate; the whole line pointer array is scanned | [nbtinsert.c:2669-2719](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2669-L2719) |
| Two call sites ask for simple deletion only | [nbtinsert.c:938-952](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L938-L952), [nbtinsert.c:990-1009](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L990-L1009) |
| `uniquedup` is set four ways, including after failed simple deletion | [nbtinsert.c:840-897](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L840-L897), [nbtinsert.c:2721-2733](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2721-L2733) |
| `checkingunique && !uniquedup` returns early; that is the documented unique-index heuristic | [nbtinsert.c:2735-2752](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2735-L2752), [btree.sgml:822-833](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L822-L833) |
| Bottom-up trigger is `indexUnchanged \|\| uniquedup`; dedup needs the reloption and `allequalimage` | [nbtinsert.c:2757-2781](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2781) |
| `indexUnchanged` is per index, key-columns-only, cached, ignores predicates | [execIndexing.c#index_unchanged_by_update](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L955-L1069) |
| The hint is only considered for a non-HOT `UPDATE` (`TU_All`) | [execIndexing.c#ExecInsertIndexTuples](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L260-L306), [execIndexing.c:425-445](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L425-L445) |
| Hint plumbing reaches `btinsert`; other AMs ignore it | [indexam.c:213-235](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L213-L235), [nbtree.c:180-198](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L180-L198) |
| Logical replication apply builds state so the hint can be passed | [worker.c:2592-2601](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L2592-L2601) |
| LP_DEAD bits come from index scans and from unique checks | [nbtutils.c#_bt_killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4139-L4348), [nbtinsert.c:676-696](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L676-L696) |
| A posting list is LP_DEAD only when every TID is dead | [nbtutils.c:4245-4310](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4245-L4310), [README:546-555](../../../../raw/postgres-17/src/backend/access/nbtree/README#L546-L555) |
| Simple deletion adds the new item's block and every same-block TID | [nbtinsert.c#_bt_simpledel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2784-L2916), [nbtinsert.c#_bt_deadblocks](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2918-L3005) |
| Bottom-up sets `maxpostingsize = BLCKSZ` so intervals are pure equality groups | [nbtdedup.c:323-336](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L323-L336) |
| Promising rules: plain tuples by interval, posting lists at most one TID by block clustering | [nbtdedup.c#_bt_bottomupdel_finish_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L611-L753) |
| `bottomupfreespace = Max(BLCKSZ/16, newitemsz)`; success bar is `Max(BLCKSZ/24, newitemsz)`; `nintervals == 0` returns true | [nbtdedup.c:337-359](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L337-L359), [nbtdedup.c:394-421](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L394-L421) |
| A bottom-up caller may not claim `knowndeletable`, and may get zero back | [tableam.h:172-216](../../../../raw/postgres-17/src/include/access/tableam.h#L172-L216), [heapam.c:8794-8803](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8794-L8803) |
| heapam sorts, buckets by power of two with a floor of 4, and keeps 6 blocks | [heapam.c#bottomup_sort_and_shrink](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L9040-L9172), [heapam.c#bottomup_sort_and_shrink_cmp](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8982-L9038) |
| `BOTTOMUP_MAX_NBLOCKS` 6, `BOTTOMUP_TOLERANCE_NBLOCKS` 3, favorable-block rule | [heapam.c#BOTTOMUP_MAX_NBLOCKS](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L205-L216), [heapam.c#bottomup_nblocksfavorable](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8881-L8980) |
| Three give-up rules and the halving decay | [heapam.c:8586-8654](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8586-L8654) |
| Deletability comes from `heap_hot_search_buffer` under a non-vacuumable snapshot | [heapam.c:8689-8712](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8689-L8712) |
| Prefetch distance and the catalog-relation special case | [heapam.c:8540-8570](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8540-L8570), [heapam.c#index_delete_prefetch_buffer](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8384-L8428) |
| nbtree restores leaf-page order and does granular TID removal | [nbtpage.c#_bt_delitems_delete_check](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1474-L1679), [nbtdedup.c#_bt_update_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L913-L994) |
| Bottom-up deletion is B-tree only; GiST and hash use the generic shim | [genam.c#index_compute_xid_horizon_for_tuples](../../../../raw/postgres-17/src/backend/access/index/genam.c#L276-L345), [gist.c:1695-1705](../../../../raw/postgres-17/src/backend/access/gist/gist.c#L1695-L1705), [hashinsert.c:391-401](../../../../raw/postgres-17/src/backend/access/hash/hashinsert.c#L391-L401), [heapam_handler.c:2626](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L2626) |
| Dedup pass steps, temp page, and the "no savings test" decision | [nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L33-L278) |
| `maxpostingsize` is a sixth of a page by choice, not a limit | [nbtdedup.c:75-99](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L75-L99) |
| The 50-TID rule inside `_bt_dedup_save_htid` | [nbtdedup.c#_bt_dedup_save_htid](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L477-L544) |
| Posting list tuple format and its flag bits | [nbtree.h:432-466](../../../../raw/postgres-17/src/include/access/nbtree.h#L432-L466), [nbtree.h#BTreeTupleSetPosting](../../../../raw/postgres-17/src/include/access/nbtree.h#L491-L515) |
| One-TID posting lists are impossible, guaranteeing dedup shrinks the tuple | [nbtdedup.c#_bt_form_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L844-L911) |
| Single value strategy thresholds, 96% fillfactor, and the multi-pass expectation | [nbtdedup.c:174-201](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L174-L201), [nbtdedup.c#_bt_do_singleval](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L755-L802), [nbtdedup.c#_bt_singleval_fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L804-L842), [nbtree.h#BTREE_SINGLEVAL_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202) |
| Posting list splits keep the list the same size and ride the insert's atomic action | [nbtdedup.c#_bt_swap_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L996-L1070), [nbtinsert.c:1155-1201](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1155-L1201), [README:990-1018](../../../../raw/postgres-17/src/backend/access/nbtree/README#L990-L1018) |
| REDO reuses `_bt_swap_posting` | [nbtxlog.c:200-225](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L200-L225) |
| Build-time dedup skips unique indexes and uses a 10%-of-page cap | [nbtsort.c:1144-1152](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1144-L1152), [nbtsort.c:1287-1308](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1287-L1308), [btree.sgml:785-798](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L785-L798) |
| Build-time `allequalimage` and the `DEBUG1` verdict | [nbtsort.c:557-566](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L557-L566), [nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183) |
| `btequalimage` always true; `btvarstrequalimage` false for nondeterministic collations | [datum.c#btequalimage](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L415-L438), [varlena.c#btvarstrequalimage](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L2595-L2613) |
| Documented unsafe types and the `INCLUDE` restriction | [btree.sgml:834-909](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L834-L909) |
| Bottom-up deliberately omits the `allequalimage` test | [nbtinsert.c:2757-2776](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2776) |
| `_bt_keep_natts_fast` uses `datum_image_eq` and is only guaranteed exact when all-equal-image | [nbtutils.c#_bt_keep_natts_fast](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4852-L4905) |
| Tuple-size arithmetic inputs | [itup.h#IndexTupleData](../../../../raw/postgres-17/src/include/access/itup.h#L35-L71), [indextuple.c:150-167](../../../../raw/postgres-17/src/backend/access/common/indextuple.c#L150-L167), [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L211-L214), [nbtree.h#BTMaxItemSize](../../../../raw/postgres-17/src/include/access/nbtree.h#L154-L168), [configure.ac:263-265](../../../../raw/postgres-17/configure.ac#L263-L265) |
| The documentation's 616-byte, 100-TID posting list | [pageinspect.sgml:406-439](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L406-L439) |
| `bt_page_items` decodes posting lists into `tids`; `bt_metap` exposes `allequalimage` | [btreefuncs.c:590-606](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L590-L606), [btreefuncs.c#bt_metap](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L840-L922) |
| `amcheck` validates posting list ordering and expands lists for its other checks | [verify_nbtree.c:1520-1552](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L1520-L1552), [verify_nbtree.c:3070-3082](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L3070-L3082) |
| WAL record descriptions, and that DEDUP carries only `nintervals` | [nbtdesc.c:51-83](../../../../raw/postgres-17/src/backend/access/rmgrdesc/nbtdesc.c#L51-L83), [nbtdesc.c#delvacuum_desc](../../../../raw/postgres-17/src/backend/access/rmgrdesc/nbtdesc.c#L195-L254), [nbtdedup.c:245-268](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L245-L268) |
| Simple and bottom-up deletion share `XLOG_BTREE_DELETE` | [nbtpage.c#_bt_delitems_delete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1264-L1382), [README:571-580](../../../../raw/postgres-17/src/backend/access/nbtree/README#L571-L580) |
| Replay of a dedup record re-runs the merge with a larger cap and asserts equality | [nbtxlog.c#btree_xlog_dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L463-L554) |
| `snapshotConflictHorizon` is zeroed without standby info; `xl_btree_vacuum` has no such field | [nbtpage.c:1516-1531](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1516-L1531), [nbtxlog.h#xl_btree_delete](../../../../raw/postgres-17/src/include/access/nbtxlog.h#L197-L256) |
| Exclusive buffer lock is enough; only VACUUM needs a cleanup lock | [README:189-193](../../../../raw/postgres-17/src/backend/access/nbtree/README#L189-L193), [README:166-202](../../../../raw/postgres-17/src/backend/access/nbtree/README#L166-L202), [nbtinsert.c#_bt_search_insert](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L316-L381) |
| Heap buffers are share-locked one at a time | [heapam.c:8656-8679](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8656-L8679) |
| Error and PANIC paths | [nbtdedup.c:1033-1045](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L1033-L1045), [nbtinsert.c:1173-1192](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1173-L1192), [heapam.c#index_delete_check_htid](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8430-L8485), [nbtdedup.c:566-595](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L566-L595), [nbtxlog.c:519-533](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L519-L533), [nbtpage.c:1309-1321](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1309-L1321) |
| VACUUM's posting list handling and one-record-per-page batching | [nbtree.c:1240-1320](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1240-L1320) |
| Bottom-up is qualitative, autovacuum quantitative; VACUUM is still required | [btree.sgml:656-678](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L656-L678), [btree.sgml:704-733](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L704-L733) |
| `deduplicate_items` default, lock level, no retroactive effect | [reloptions.c:159-168](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L168), [nbtree.h#BTOptions](../../../../raw/postgres-17/src/include/access/nbtree.h#L1129-L1151), [create_index.sgml#deduplicate_items](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L448-L476) |
| The documented `deduplicate_items = off` example | [create_index.sgml:911-915](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L911-L915) |
| `maintenance_io_concurrency` is `PGC_USERSET` with default 10, overridable per tablespace | [guc_tables.c#maintenance_io_concurrency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3123-L3136), [bufmgr.h#DEFAULT_MAINTENANCE_IO_CONCURRENCY](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L157-L166), [spccache.c#get_tablespace_maintenance_io_concurrency](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L222-L237) |
| Support function 4 is generated-catalog data; which opclass registers which function | [pg_amproc.dat:28-35](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L28-L35), [pg_amproc.dat:201-212](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L201-L212), [pg_amproc.dat:240-249](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L240-L249), [pg_proc.dat#btvarstrequalimage](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L1055-L1057), [nbtree.h#BTNProcs](../../../../raw/postgres-17/src/include/access/nbtree.h#L686-L712) |
| Test coverage, and the regression test's own comment on priority order | [btree_index.sql:205-231](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L205-L231), [btree_index.out:412-437](../../../../raw/postgres-17/src/test/regress/expected/btree_index.out#L412-L437) |
| Data-structure definitions | [nbtree.h:837-914](../../../../raw/postgres-17/src/include/access/nbtree.h#L837-L914), [tableam.h:217-262](../../../../raw/postgres-17/src/include/access/tableam.h#L217-L262), [heapam.c:191-216](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L191-L216) |
| `MaxTIDsPerBTreePage` sizes the scratch arrays | [nbtree.h#MaxTIDsPerBTreePage](../../../../raw/postgres-17/src/include/access/nbtree.h#L174-L187) |
| Posting list compression was rejected partly because of bottom-up deletion | [README:931-942](../../../../raw/postgres-17/src/backend/access/nbtree/README#L931-L942) |
| Deduplication in unique indexes buys time for deletion | [README:950-988](../../../../raw/postgres-17/src/backend/access/nbtree/README#L950-L988), [btree.sgml:810-821](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L810-L821) |
| Continual INSERT/DELETE churn triggers bottom-up in unique indexes without a hint | [README:557-569](../../../../raw/postgres-17/src/backend/access/nbtree/README#L557-L569) |
| Simple deletion was the only category before PostgreSQL 14 | [btree.sgml:679-703](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L679-L703) |
| Index AM documentation mentions the hint's purpose | [indexam.sgml:336-346](../../../../raw/postgres-17/doc/src/sgml/indexam.sgml#L336-L346) |

## Open Questions

- **Which strategy actually fires, and how much it saves, is unmeasured here.**
  The asker chose source-and-history scope, so no 17.11 server was built. The
  companion page
  [Improvements Since PostgreSQL 12 in Storage Performance, Query Planning, Index
  Bloat, and Vacuum, as of PostgreSQL 17 (unverified)](../storage-and-vacuum/improvements-since-v12.md)
  carries measurements for both features taken on isolated 17.11 and 12.2 servers;
  those numbers are not reproduced or re-derived on this page.
- **The byte arithmetic in worked example 2 is derived, not observed.** It assumes
  `BLCKSZ` 8192 and `MAXIMUM_ALIGNOF` 8, and it assumes `heap_compute_data_size`
  contributes exactly 4 bytes for a single non-null `int4`. The 616-byte
  documentation figure agrees with the model, but the 222-TID maximum and the
  ≈6.1-bytes-per-entry figure were not checked against a real page.
- **Whether `btree_index.sql`'s unique-index churn loop really reaches
  `_bt_bottomupdel_pass` is inferred, not proven.** The trigger conditions and the
  README's description of unique-index churn both point that way, but nothing in
  the checkout instruments it, so the inference could not be confirmed without
  building a server.
- **`_bt_do_singleval`'s comment describes a penultimate/final pass sequence that
  is not directly asserted anywhere.** The claim that the final single-value pass
  frees nothing comes from the function's own comment
  ([nbtdedup.c:755-779](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L755-L779)),
  not from an assertion or a test.
- **Deduplication's effect on `pgstatindex`-style density metrics is asserted from
  the other filed page, not re-derived here.** The exact size of that distortion
  belongs to
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)](btree-index-bloat-core-sql-only.md).
- **Whether the absence of a read stream on the index-deletion prefetch path is a
  deliberate v17 decision or simply unconverted work is not answerable from the
  source.** The observation is that `index_delete_prefetch_buffer` still uses
  `PrefetchBuffer` and `heap_index_delete_tuples` still uses `ReadBuffer`; the
  reason is not recorded in the code.

## Source References

- [nbtinsert.c#_bt_doinsert](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L79-L138)
- [nbtinsert.c#_bt_search_insert](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L316-L381)
- [nbtinsert.c#_bt_check_unique](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L406-L696)
- [nbtinsert.c#_bt_findinsertloc](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L788-L1012)
- [nbtinsert.c#_bt_insertonpg](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1105-L1201)
- [nbtinsert.c#_bt_delete_or_dedup_one_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2654-L2782)
- [nbtinsert.c#_bt_simpledel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2784-L2916)
- [nbtinsert.c#_bt_deadblocks](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2918-L3005)
- [nbtinsert.c#_bt_blk_cmp](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L3007-L3017)
- [nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L33-L278)
- [nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L280-L421)
- [nbtdedup.c#_bt_dedup_start_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L423-L475)
- [nbtdedup.c#_bt_dedup_save_htid](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L477-L544)
- [nbtdedup.c#_bt_dedup_finish_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L546-L609)
- [nbtdedup.c#_bt_bottomupdel_finish_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L611-L753)
- [nbtdedup.c#_bt_do_singleval](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L755-L802)
- [nbtdedup.c#_bt_singleval_fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L804-L842)
- [nbtdedup.c#_bt_form_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L844-L911)
- [nbtdedup.c#_bt_update_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L913-L994)
- [nbtdedup.c#_bt_swap_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L996-L1070)
- [nbtdedup.c#_bt_posting_valid](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L1072-L1104)
- [nbtpage.c#_bt_delitems_delete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1264-L1382)
- [nbtpage.c#_bt_delitems_cmp](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1459-L1472)
- [nbtpage.c#_bt_delitems_delete_check](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1474-L1679)
- [nbtutils.c#_bt_killitems](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4139-L4348)
- [nbtutils.c#_bt_keep_natts_fast](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4852-L4905)
- [nbtutils.c#_bt_check_third_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5080-L5127)
- [nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183)
- [nbtsort.c#_bt_leafbuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L536-L566)
- [nbtsort.c#_bt_sort_dedup_finish_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1021-L1057)
- [nbtsort.c#_bt_load](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1130-L1355)
- [nbtree.c#btinsert](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L180-L198)
- [nbtree.c#btvacuumpage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1073-L1320)
- [nbtxlog.c#btree_xlog_insert](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L160-L225)
- [nbtxlog.c#btree_xlog_dedup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L463-L554)
- [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-17/src/include/access/nbtree.h#L62-L71)
- [nbtree.h#BTMaxItemSize](../../../../raw/postgres-17/src/include/access/nbtree.h#L154-L168)
- [nbtree.h#MaxTIDsPerBTreePage](../../../../raw/postgres-17/src/include/access/nbtree.h#L174-L187)
- [nbtree.h#BTREE_SINGLEVAL_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202)
- [nbtree.h#BTreeTupleIsPosting](../../../../raw/postgres-17/src/include/access/nbtree.h#L432-L515)
- [nbtree.h#BTNProcs](../../../../raw/postgres-17/src/include/access/nbtree.h#L686-L712)
- [nbtree.h#BTDedupStateData](../../../../raw/postgres-17/src/include/access/nbtree.h#L837-L914)
- [nbtree.h#BTOptions](../../../../raw/postgres-17/src/include/access/nbtree.h#L1129-L1151)
- [nbtxlog.h#xl_btree_dedup](../../../../raw/postgres-17/src/include/access/nbtxlog.h#L163-L177)
- [nbtxlog.h#xl_btree_delete](../../../../raw/postgres-17/src/include/access/nbtxlog.h#L197-L256)
- [nbtxlog.h#xl_btree_update](../../../../raw/postgres-17/src/include/access/nbtxlog.h#L258-L271)
- [README:166-202](../../../../raw/postgres-17/src/backend/access/nbtree/README#L166-L202)
- [README#Simple deletion](../../../../raw/postgres-17/src/backend/access/nbtree/README#L511-L555)
- [README#Bottom-Up deletion](../../../../raw/postgres-17/src/backend/access/nbtree/README#L557-L619)
- [README#Notes about deduplication](../../../../raw/postgres-17/src/backend/access/nbtree/README#L904-L948)
- [README#Deduplication in unique indexes](../../../../raw/postgres-17/src/backend/access/nbtree/README#L950-L988)
- [README#Posting list splits](../../../../raw/postgres-17/src/backend/access/nbtree/README#L990-L1018)
- [heapam.c#IndexDeletePrefetchState](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L191-L216)
- [heapam.c#index_delete_prefetch_buffer](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8384-L8428)
- [heapam.c#index_delete_check_htid](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8430-L8485)
- [heapam.c#heap_index_delete_tuples](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8487-L8804)
- [heapam.c#index_delete_sort](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8836-L8878)
- [heapam.c#bottomup_nblocksfavorable](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8881-L8980)
- [heapam.c#bottomup_sort_and_shrink_cmp](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L8982-L9038)
- [heapam.c#bottomup_sort_and_shrink](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L9040-L9172)
- [heapam_handler.c#index_delete_tuples](../../../../raw/postgres-17/src/backend/access/heap/heapam_handler.c#L2620-L2630)
- [tableam.h#TM_IndexDelete](../../../../raw/postgres-17/src/include/access/tableam.h#L162-L231)
- [tableam.h#TM_IndexDeleteOp](../../../../raw/postgres-17/src/include/access/tableam.h#L233-L262)
- [tableam.h#table_index_delete_tuples](../../../../raw/postgres-17/src/include/access/tableam.h#L1345-L1365)
- [genam.c#index_compute_xid_horizon_for_tuples](../../../../raw/postgres-17/src/backend/access/index/genam.c#L276-L345)
- [gist.c#gistprunepage](../../../../raw/postgres-17/src/backend/access/gist/gist.c#L1671-L1705)
- [hashinsert.c#_hash_vacuum_one_page](../../../../raw/postgres-17/src/backend/access/hash/hashinsert.c#L370-L401)
- [indexam.c#index_insert](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L213-L235)
- [execIndexing.c#ExecInsertIndexTuples](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L260-L306)
- [execIndexing.c:425-445](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L425-L445)
- [execIndexing.c#index_unchanged_by_update](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L955-L1069)
- [worker.c:2592-2601](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L2592-L2601)
- [nbtdesc.c#btree_desc](../../../../raw/postgres-17/src/backend/access/rmgrdesc/nbtdesc.c#L24-L83)
- [nbtdesc.c#btree_identify](../../../../raw/postgres-17/src/backend/access/rmgrdesc/nbtdesc.c#L139-L193)
- [nbtdesc.c#delvacuum_desc](../../../../raw/postgres-17/src/backend/access/rmgrdesc/nbtdesc.c#L195-L254)
- [itup.h#IndexTupleData](../../../../raw/postgres-17/src/include/access/itup.h#L35-L71)
- [indextuple.c:150-167](../../../../raw/postgres-17/src/backend/access/common/indextuple.c#L150-L167)
- [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L211-L214)
- [datum.c#btequalimage](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L415-L438)
- [varlena.c#btvarstrequalimage](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L2595-L2613)
- [pg_amproc.dat:28-35](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L28-L35)
- [pg_amproc.dat:201-212](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L201-L212)
- [pg_amproc.dat:240-249](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L240-L249)
- [pg_proc.dat#btvarstrequalimage](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L1055-L1057)
- [reloptions.c:159-168](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L168)
- [guc_tables.c#maintenance_io_concurrency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3123-L3136)
- [bufmgr.h#DEFAULT_MAINTENANCE_IO_CONCURRENCY](../../../../raw/postgres-17/src/include/storage/bufmgr.h#L157-L166)
- [spccache.c#get_tablespace_maintenance_io_concurrency](../../../../raw/postgres-17/src/backend/utils/cache/spccache.c#L222-L237)
- [configure.ac:263-265](../../../../raw/postgres-17/configure.ac#L263-L265)
- [btree.sgml#btree-deletion](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L632-L734)
- [btree.sgml#btree-deduplication](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L736-L911)
- [create_index.sgml#deduplicate_items](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L448-L476)
- [create_index.sgml:911-915](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L911-L915)
- [indexam.sgml:336-346](../../../../raw/postgres-17/doc/src/sgml/indexam.sgml#L336-L346)
- [pageinspect.sgml#bt_page_items](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L400-L480)
- [pageinspect.sgml:305-315](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L305-L315)
- [btree_index.sql:186-190](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L186-L190)
- [btree_index.sql:205-231](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L205-L231)
- [btree_index.out:412-437](../../../../raw/postgres-17/src/test/regress/expected/btree_index.out#L412-L437)
- [check_btree.sql:14-18](../../../../raw/postgres-17/contrib/amcheck/sql/check_btree.sql#L14-L18)
- [004_verify_nbtree_unique.pl:115-133](../../../../raw/postgres-17/contrib/amcheck/t/004_verify_nbtree_unique.pl#L115-L133)
- [005_opclass_damage.pl:45-52](../../../../raw/postgres-17/src/bin/pg_amcheck/t/005_opclass_damage.pl#L45-L52)
- [btreefuncs.c#bt_page_print_tuples](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L482-L606)
- [btreefuncs.c#bt_metap](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L840-L922)
- [btree.out:1-16](../../../../raw/postgres-17/contrib/pageinspect/expected/btree.out#L1-L16)
- [verify_nbtree.c#bt_target_page_check](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L1365-L1552)
- [verify_nbtree.c#bt_posting_plain_tuple](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L3070-L3082)

## Navigation

- [v17/index](../../index.md)
- [Checking Whether an Index Needs a Rebuild to Enable Deduplication After pg_upgrade From PostgreSQL 12 to 17 (unverified)](btree-deduplication-after-pg-upgrade.md)
- [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)](btree-index-bloat-core-sql-only.md)
- [B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17 (unverified)](btree-bloat-with-pgstatindex.md)
- [Improvements Since PostgreSQL 12 in Storage Performance, Query Planning, Index Bloat, and Vacuum, as of PostgreSQL 17 (unverified)](../storage-and-vacuum/improvements-since-v12.md)
- [Planner Penalties for Bloated Indexes in PostgreSQL 17 (unverified)](../query-planning/bloated-indexes-query-planner.md)
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [versions](../../../versions.md)
- [Wiki Index](../../../index.md)
