---
type: question
version: 18
pinned_commit: baa7b142aace6821ce085906f314a75bcc4d95c8
verified: false
verified_by_agent: not yet
---

# Computing and Storing avg_leaf_density During (Auto)VACUUM of a B-Tree Index (unverified)

**Answer up front.** When PostgreSQL 18 B-tree VACUUM actually enters
`btvacuumscan`, it already reads every index block except the metapage and takes
a cleanup lock on each live leaf page, so the `pgstatindex`-style numerator and
denominator can be accumulated with no extra page reads
([nbtree.c#btvacuumscan](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1186),
[nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361)).
The durable storage target with the least new I/O is still the B-tree metapage,
but only when `_bt_set_cleanup_info` is already going to dirty and WAL-log it;
if its early-return guard would otherwise fire, persisting a fresh density adds
one metapage write and one small WAL record
([nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232)).
For PostgreSQL 18 specifically, reusing or renaming the deprecated metapage
`float8` slot `btm_last_cleanup_num_heap_tuples` is less invasive than adding a
new `float4`, but WAL redo and `pageinspect` must be updated because v18 still
resets and exposes that field
([nbtree.h#BTMetaPageData](../../../../raw/postgres-18/src/include/access/nbtree.h#L104),
[btreefuncs.c#bt_metap](../../../../raw/postgres-18/contrib/pageinspect/btreefuncs.c#L838)).
A queryable copy can also go into the cumulative statistics system as a shared
stats update, with persistence only through the normal clean-shutdown stats file
path
([pgstat_relation.c#pgstat_report_vacuum](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_relation.c#L210),
[pgstat.c](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c)).
Two caveats matter: VACUUM can skip the B-tree scan entirely, and exact
"after VACUUM" parity with `pgstatindex` needs explicit accounting for empty
leaf pages that `_bt_pagedel` successfully deletes or fails to delete.

## Question

> In PostgreSQL 18, create a detailed analysis of how to modify vacuum and
> autovacuum to calculate `avg_leaf_density` for an index like `pgstatindex` and
> store it in a statistics table. After each successful vacuum or autovacuum of
> an index, the information should be available. This solution should minimize
> extra I/O as much as possible, so the calculation should try to use all current
> data available during vacuum to calculate `avg_leaf_density`.

## What avg_leaf_density Is

`pgstatindex` defines it as the percentage of *usable* leaf-page space that is
actually occupied, averaged over all leaf pages:

- For each leaf page it adds `max_avail = BLCKSZ - (BLCKSZ - pd_special + SizeOfPageHeaderData)`
  and `free_space = PageGetExactFreeSpace(page)`
  ([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-18/contrib/pgstattuple/pgstatindex.c#L213)).
- The reported figure is `100.0 - free_space / max_avail * 100.0`, or `NaN` when
  there are no leaf pages
  ([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-18/contrib/pgstattuple/pgstatindex.c#L213)).

The `max_avail` expression algebraically reduces to
`pd_special - SizeOfPageHeaderData`. `SizeOfPageHeaderData` is
`offsetof(PageHeaderData, pd_linp)`
([bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-18/src/include/storage/bufpage.h#L218)),
and B-tree pages are initialized with `sizeof(BTPageOpaqueData)` as special
space, which `PageInit` aligns before setting `pd_special`
([nbtpage.c#_bt_pageinit](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L1129),
[bufpage.c#PageInit](../../../../raw/postgres-18/src/backend/storage/page/bufpage.c#L42)).
For a B-tree leaf page, that means
`pd_special = BLCKSZ - MAXALIGN(sizeof(BTPageOpaqueData))`, so `max_avail` is
the **same constant** for every leaf page in a given build:

```
C = BLCKSZ - SizeOfPageHeaderData - MAXALIGN(sizeof(BTPageOpaqueData))
```

`free_space` is exactly `pd_upper - pd_lower`
([bufpage.c#PageGetExactFreeSpace](../../../../raw/postgres-18/src/backend/storage/page/bufpage.c#L957)).

Therefore the whole statistic needs only two scalars per index:

```
nleaf            = number of live leaf pages visited
sum_free_space   = Σ (pd_upper - pd_lower) over those leaf pages
avg_leaf_density = 100.0 * (1.0 - sum_free_space / (nleaf * C))   -- NaN if nleaf == 0
```

Accumulating `max_avail` per page (instead of `nleaf * C`) keeps byte-for-byte
parity with `pgstatindex` and is robust if the constant ever varies; the cost
is identical.

## Why VACUUM Is the Zero-Extra-I/O Place

`pgstatindex` exists only because, outside VACUUM, there is no other moment when
every leaf page is already in hand. A B-tree VACUUM scan removes that objection
when it runs:

- `btbulkdelete` calls `btvacuumscan`; `btvacuumcleanup` calls it only when no
  `btbulkdelete` scan ran and `_bt_vacuum_needs_cleanup` says cleanup is needed
  ([nbtree.c#btbulkdelete](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1068),
  [nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098)).
- `btvacuumscan` walks **all** blocks except the metapage in physical order via
  a maintenance read stream and calls `btvacuumpage` on each
  ([nbtree.c#btvacuumscan](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1186)).
- `btvacuumpage` takes a cleanup lock on every live leaf page "whether or not it
  actually contains any deletable tuples" and then has the page pointer in hand
  ([nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361)).

So the bytes `pgstatindex` would read are already pinned and locked during
`btvacuumscan`. Computing the two sums there adds a subtraction and two adds per
leaf page and no I/O at all.

## The Computation: Where to Hook In

### 1. Carry accumulators in `BTVacState`

`BTVacState` is the per-scan private state already threaded through
`btvacuumscan` -> `btvacuumpage`
([nbtree.h#BTVacState](../../../../raw/postgres-18/src/include/access/nbtree.h#L331)).
Add three fields:

```c
/* avg_leaf_density accumulators (whole-index, reset per btvacuumscan) */
uint64   nleaf;            /* live leaf pages visited */
uint64   sum_free_space;   /* Σ PageGetExactFreeSpace over those leaves */
uint64   sum_max_avail;    /* Σ per-leaf usable space (== nleaf * C) */
```

Zero them next to the existing `stats->num_pages = 0; ...` resets at the top of
`btvacuumscan`, so a multi-pass VACUUM that calls `btvacuumscan` more than once
does not double-count
([nbtree.c#btvacuumscan](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1186)).

### 2. Accumulate in the `P_ISLEAF` branch after compaction

`btvacuumpage` classifies the page. Recyclable, already-deleted, half-dead, and
internal pages are handled in earlier branches; the `else if (P_ISLEAF(opaque))`
branch is reached for live leaf pages that `pgstatindex` would count at that
moment
([nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361)).
Inside that branch, `_bt_delitems_vacuum` may delete/compact items and `maxoff`
is recomputed afterward
([nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361)).
Place the basic accumulation **after** the `if (ndeletable > 0 || nupdatable > 0)`
apply block, so the measured free space reflects item deletion and posting-list
compaction done by this VACUUM:

```c
/* after _bt_delitems_vacuum has run and maxoff was recomputed */
Size max_avail = ((PageHeader) page)->pd_special - SizeOfPageHeaderData;

vstate->nleaf++;
vstate->sum_free_space += PageGetExactFreeSpace(page);
vstate->sum_max_avail  += max_avail;
```

That placement is exact for pages that remain live leaves. Empty pages need extra
care. `btvacuumpage` sets `attempt_pagedel` for an empty leaf page, but
`_bt_pagedel` can return without deleting it when the page is the root, the
rightmost page, no longer empty, or part of an incomplete split; `_bt_pagedel`
also releases the caller's buffer before returning
([nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361),
[nbtpage.c#_bt_pagedel](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L1802)).
Therefore the simple `if (!attempt_pagedel) count it` sketch is not exact:
it misses empty pages that survive deletion. Counting before `_bt_pagedel` is
also not exact for an "after VACUUM" statistic, because `pgstatindex` does not
count pages once they are half-dead or deleted
([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-18/contrib/pgstattuple/pgstatindex.c#L213)).

For exact post-VACUUM parity, add a small deletion-accounting hook rather than
only a leaf-branch counter:

1. Count live leaves after compaction.
2. Track which counted leaf blocks contributed to the sums.
3. When `_bt_pagedel`/`_bt_unlink_halfdead_page` actually marks a counted leaf
   page deleted, subtract that page's saved contribution before finalizing the
   density
   ([nbtpage.c#_bt_unlink_halfdead_page](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L2314)).
4. If an empty current leaf enters `_bt_pagedel` but survives, keep the
   contribution; if `_bt_pagedel` released the lock and another backend inserted
   into the page, treat the value as an estimate unless the implementation
   rechecks that rare case.

This branch also runs in the cleanup-only path (`callback == NULL`), so the
statistic is still produced when `btvacuumcleanup` triggers a scan
([nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098)).

### 3. Derive the final figure at the end of `btvacuumscan`

After the page loop, where `stats->num_pages` is finalized
([nbtree.c#btvacuumscan](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1186)),
compute:

```c
bool avg_leaf_density_valid = (vstate.sum_max_avail > 0);
double avg_leaf_density =
    avg_leaf_density_valid
      ? 100.0 * (1.0 - (double) vstate.sum_free_space
                            / (double) vstate.sum_max_avail)
      : 0.0;
```

Store it as `float8` plus a validity bit, or store `-1.0` internally and expose
SQL `NULL` or `NaN` through the accessor. A bare `-1.0` column is awkward in the
cumulative statistics system because relation stats reset by zeroing the shared
entry, and `0.0` is a valid leaf-density value
([pgstat_shmem.c#shared_stat_reset_contents](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L1109)).

## Where to Store It (the "stat table")

Two complementary targets, chosen for minimal extra I/O.

### Option A (recommended durable store): the B-tree metapage

`btvacuumcleanup` calls `_bt_set_cleanup_info` after a successful
`btvacuumscan`, and `_bt_set_cleanup_info` reads the metapage before deciding
whether it can return without a write
([nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098),
[nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232)).
If `btm_last_cleanup_num_delpages` changes or the metapage needs upgrade, the
function already takes a write lock, marks the metapage dirty, and emits an
`xl_btree_metadata` record; if the value is unchanged, it releases the buffer
and returns
([nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232)).
So density storage has zero extra page reads, but it only has zero extra writes
when that metapage update was already needed.

For PostgreSQL 18, the least invasive metapage layout is to reuse or rename the
existing deprecated `float8 btm_last_cleanup_num_heap_tuples` slot:

1. Rename or reinterpret `btm_last_cleanup_num_heap_tuples` as
   `btm_last_avg_leaf_density`, keeping it `float8` to match `pgstatindex`'s
   `FLOAT8` output
   ([nbtree.h#BTMetaPageData](../../../../raw/postgres-18/src/include/access/nbtree.h#L104),
   [pgstattuple--1.4.sql](../../../../raw/postgres-18/contrib/pgstattuple/pgstattuple--1.4.sql)).
2. Pass density and validity into `_bt_set_cleanup_info`; widen the early-return
   guard to compare both `num_delpages` and the stored density so a completed
   scan can refresh the value
   ([nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232)).
3. Add the density to `xl_btree_metadata` and restore it in `_bt_restore_meta`,
   because v18 redo currently reconstructs `btm_last_cleanup_num_heap_tuples`
   as `-1.0`
   ([nbtxlog.h#xl_btree_metadata](../../../../raw/postgres-18/src/include/access/nbtxlog.h#L49),
   [nbtxlog.c#_bt_restore_meta](../../../../raw/postgres-18/src/backend/access/nbtree/nbtxlog.c#L82)).
4. Update `pageinspect` if the metapage field is exposed there, because
   `bt_metap` still returns `btm_last_cleanup_num_heap_tuples`
   ([btreefuncs.c#bt_metap](../../../../raw/postgres-18/contrib/pageinspect/btreefuncs.c#L838)).

Adding a brand-new field to `BTMetaPageData` is possible, but it is more
invasive: it changes the metapage layout, requires a B-tree metapage-version
story, and still needs WAL redo changes. Reusing the deprecated `float8` slot
keeps the on-page `BTMetaPageData` size stable while preserving crash recovery
through the widened `xl_btree_metadata` record.

Incremental I/O cost: **zero extra page reads**. Extra write cost is **zero only
when `_bt_set_cleanup_info` would already dirty the metapage**. If the scan
finishes and `num_delpages` is unchanged, refreshing a durable density converts
the existing early return into one metapage write plus one small WAL record
([nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232)).

To expose it, add or update a `pageinspect`/contrib accessor that reads the
metapage field, or surface the last value through Option B.

### Option B (queryable, no VACUUM-time disk I/O): cumulative statistics

The "stat table" users normally query is the cumulative statistics system. Index
entries already live there under `PGSTAT_KIND_RELATION`, keyed by the index
relid, and `pg_stat_all_indexes` reads those index-relid entries through
`pg_stat_get_*` accessors
([system_views.sql#pg_stat_all_indexes](../../../../raw/postgres-18/src/backend/catalog/system_views.sql#L803),
[pgstatfuncs.c#pg_stat_get_numscans](../../../../raw/postgres-18/src/backend/utils/adt/pgstatfuncs.c#L82)).
Plan:

1. Add `float8 avg_leaf_density` plus a `density_stats_valid` flag to
   `PgStat_StatTabEntry`
   ([pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-18/src/include/pgstat.h#L422)).
   It is meaningful only for B-tree index entries; reset code zeros relation
   stats, so the accessor should return `NULL` unless the validity flag is set
   ([pgstat_shmem.c#shared_stat_reset_contents](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L1109)).
2. Return the value out of the AM. `IndexBulkDeleteResult` is the AM-to-VACUUM
   contract
   ([genam.h#IndexBulkDeleteResult](../../../../raw/postgres-18/src/include/access/genam.h#L98));
   add `float8 avg_leaf_density` plus a validity flag to it and set it from the
   `btvacuumscan`
   computation. Both `btbulkdelete` and `btvacuumcleanup` already return this
   struct
   ([nbtree.c#btbulkdelete](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1068),
   [nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098)).
3. Report it from VACUUM. The struct surfaces in
   `lazy_vacuum_one_index`/`lazy_cleanup_one_index`
   ([vacuumlazy.c#lazy_cleanup_one_index](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L3061))
   and is retained in `vacrel->indstats`. Add a per-index reporter modeled on
   `pgstat_report_vacuum`, which takes a locked shared entry, writes fields, and
   unlocks: an in-memory shared-hashtable update, **not** a disk write
   ([pgstat_relation.c#pgstat_report_vacuum](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_relation.c#L210)).
   Relation stats are written to the permanent stats file only through the
   normal stats-file path, which loads stats at startup, discards them after a
   crash, and writes them before clean shutdown for stats kinds that opt in
   ([pgstat.c](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c),
   [pgstat.c#PGSTAT_KIND_RELATION](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L303)).
4. Expose it as a new column in the `pg_stat_all_indexes` view and a
   `pg_stat_get_*` accessor; that means touching the view SQL, the C accessor
   in `pgstatfuncs.c`, and the `pg_proc.dat` entry for the new function
   ([system_views.sql#pg_stat_all_indexes](../../../../raw/postgres-18/src/backend/catalog/system_views.sql#L803),
   [pgstatfuncs.c](../../../../raw/postgres-18/src/backend/utils/adt/pgstatfuncs.c),
   [pg_proc.dat](../../../../raw/postgres-18/src/include/catalog/pg_proc.dat)).

Autovacuum needs no separate change: autovacuum workers run the same
`vacuum()` -> `vacuum_rel()` -> `table_relation_vacuum()` path as manual lazy
VACUUM, and the heap lazy VACUUM path reaches
`index_bulk_delete`/`index_vacuum_cleanup` through `vac_bulkdel_one_index` and
`vac_cleanup_one_index`
([autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L3173),
[vacuum.c#vacuum_rel](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L2018),
[vacuum.c#vac_bulkdel_one_index](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L2651),
[indexam.c#index_bulk_delete](../../../../raw/postgres-18/src/backend/access/index/indexam.c#L795)).
If the reporter also records whether the scan came from manual VACUUM or
autovacuum, call it from the leader-side lazy VACUUM path after serial or
parallel index work has populated `vacrel->indstats`; that preserves the
existing `AmAutoVacuumWorkerProcess()` distinction used by
`pgstat_report_vacuum`
([vacuumlazy.c#lazy_vacuum_one_index](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L3095),
[vacuumlazy.c#lazy_cleanup_one_index](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L3061),
[vacuumlazy.c#dead_items_cleanup](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L3606),
[pgstat_relation.c#pgstat_report_vacuum](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_relation.c#L210)).

### Recommendation

Do **both**: metapage as the durable source of truth and cumulative stats as the
cheap queryable surface. The metapage survives crash/restart through WAL when the
density is included in `xl_btree_metadata`; cumulative stats are convenient but
are discarded after crash and only written to the permanent stats file on clean
shutdown
([nbtxlog.c#_bt_restore_meta](../../../../raw/postgres-18/src/backend/access/nbtree/nbtxlog.c#L82),
[pgstat.c](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c)).
If only one is wanted, the metapage gives the strongest durability, at the cost
of a metapage write whenever a completed scan refreshes density but
`_bt_set_cleanup_info` would otherwise have returned early.

| Aspect | Metapage (A) | Cumulative stats (B) |
|---|---|---|
| Extra read I/O during VACUUM | none | none |
| Extra write I/O during VACUUM | none only when cleanup already dirties metapage; otherwise one metapage WAL write | none for the stat update itself (shared memory) |
| Durable across crash/restart | yes (WAL-logged) | best-effort (stats file; reset on crash) |
| Directly queryable | needs accessor function | yes, via `pg_stat_all_indexes` |
| Replicated to standbys | yes | no |

## Pros and Cons

This question proposes a code modification, so the points below weigh that
proposed design rather than existing behavior. Each con is a summary; the
detailed, fully cited version follows in the Cons Evidence section below.

### Pros

- **Effectively zero extra read I/O.** When the B-tree scan runs, every leaf
  page is already pinned and cleanup-locked in `btvacuumpage`, so the numerator
  and denominator are accumulated from bytes already in hand
  ([nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361),
  [nbtree.c#btvacuumscan](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1186)).
- **Negligible CPU cost.** The per-leaf work is one subtraction and two adds, and
  the whole statistic collapses to two scalars per index (`nleaf`,
  `sum_free_space`), because `max_avail` is a per-build constant
  ([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-18/contrib/pgstattuple/pgstatindex.c#L213),
  [bufpage.c#PageGetExactFreeSpace](../../../../raw/postgres-18/src/backend/storage/page/bufpage.c#L957)).
- **Post-compaction accuracy.** Accumulating after `_bt_delitems_vacuum` reflects
  the item deletion and posting-list compaction this VACUUM performed, not the
  pre-VACUUM state
  ([nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361)).
- **No autovacuum-specific code.** Autovacuum workers run the same
  `vacuum_rel` -> lazy VACUUM -> `index_bulk_delete`/`index_vacuum_cleanup`
  path, and the cleanup-only (`callback == NULL`) scan is covered too
  ([autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L3173),
  [nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098)).
- **Choice of durability vs. queryability.** The metapage gives a crash-durable,
  WAL-replicated value; cumulative stats give a cheap `pg_stat_all_indexes`
  surface with no VACUUM-time disk write. The two can be combined
  ([nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232),
  [pgstat_relation.c#pgstat_report_vacuum](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_relation.c#L210)).
- **Optional byte-for-byte parity.** Summing real per-leaf `max_avail` instead of
  `nleaf * C` matches `pgstatindex` exactly at no extra cost
  ([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-18/contrib/pgstattuple/pgstatindex.c#L213)).

### Cons

- **Cannot refresh after *every* successful VACUUM.** `INDEX_CLEANUP off`, the
  wraparound failsafe, and `btvacuumcleanup`'s early return all skip the index
  scan by design, leaving no leaf pages in hand
  ([vacuumlazy.c#heap_vacuum_rel](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L615),
  [vacuumlazy.c#lazy_check_wraparound_failsafe](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L2964),
  [nbtpage.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L179)).
- **Durable metapage storage is not write-free.** A changed density can turn
  `_bt_set_cleanup_info`'s early return into one metapage write plus one
  `XLOG_BTREE_META_CLEANUP` record
  ([nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232)).
- **On-disk and extension-visible change.** Reusing the deprecated
  `btm_last_cleanup_num_heap_tuples` slot still requires `xl_btree_metadata`,
  `_bt_restore_meta`, and `pageinspect` updates; a brand-new field needs a
  metapage version and pg_upgrade story
  ([nbtxlog.c#_bt_restore_meta](../../../../raw/postgres-18/src/backend/access/nbtree/nbtxlog.c#L82),
  [btreefuncs.c#bt_metap](../../../../raw/postgres-18/contrib/pageinspect/btreefuncs.c#L838)).
- **Cumulative stats are not durable.** They reset on crash and persist only on
  clean shutdown, and the new field needs an explicit validity bit to tell "no
  value" from a real `0.0`
  ([pgstat.c](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c),
  [pgstat_shmem.c#shared_stat_reset_contents](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L1109)).
- **Exact parity needs deletion-aware accounting.** Empty leaves entering
  `_bt_pagedel` may survive or be deleted (with right siblings deleted in
  passing), so a single `P_ISLEAF` counter is not exact across
  `btvacuumpage`/`_bt_pagedel`/`_bt_unlink_halfdead_page`
  ([nbtpage.c#_bt_pagedel](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L1802),
  [nbtpage.c#_bt_unlink_halfdead_page](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L2314)).
- **Estimate under concurrency.** Concurrent page splits can make `btvacuumscan`
  visit a moved page twice, the same double-counting class already acknowledged
  for `num_index_tuples`
  ([nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098)).
- **Extra integration surface for parallel VACUUM.** A density field added to
  `IndexBulkDeleteResult` must stay correct in the DSM copy path, not just the
  serial lazy VACUUM path
  ([vacuumparallel.c#parallel_vacuum_end](../../../../raw/postgres-18/src/backend/commands/vacuumparallel.c#L436)).
- **Wasted bytes in shared stats.** A B-tree-only field in the shared
  `PgStat_StatTabEntry` costs bytes for every table and non-B-tree index entry
  ([pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-18/src/include/pgstat.h#L422)).

## Cons Evidence

The strongest con is that "after every successful VACUUM/autovacuum" conflicts
with PostgreSQL 18 paths that intentionally avoid index scans. Manual
`INDEX_CLEANUP off` disables both index vacuuming and index cleanup, the
wraparound failsafe disables further index vacuuming and cleanup, and B-tree
cleanup can return `NULL` without `btvacuumscan` when no bulk-delete scan ran
and `_bt_vacuum_needs_cleanup` says cleanup is unnecessary
([vacuumlazy.c#heap_vacuum_rel](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L615),
[vacuumlazy.c#lazy_check_wraparound_failsafe](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L2964),
[nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098),
[nbtpage.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L179)).
Refreshing density in those cases would require a physical B-tree scan that
PostgreSQL 18 currently avoids, so the feature cannot both refresh after every
successful VACUUM and preserve the existing no-scan behavior.

Durable metapage storage is not write-free. `_bt_set_cleanup_info` takes the
metapage read lock, returns early when the metapage version is new enough and
`btm_last_cleanup_num_delpages` is unchanged, and otherwise upgrades to a write
lock, marks the metapage dirty, and emits `XLOG_BTREE_META_CLEANUP` when the
relation needs WAL
([nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232)).
Storing density durably means a changed density can turn that early return into
one metapage write plus one WAL record even when the existing cleanup field did
not change
([nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232),
[nbtxlog.h#xl_btree_metadata](../../../../raw/postgres-18/src/include/access/nbtxlog.h#L49)).

Reusing the deprecated metapage `float8` slot reduces layout churn, but it is
still an on-disk and extension-visible behavior change. PostgreSQL 18 still has
`btm_last_cleanup_num_heap_tuples` in `BTMetaPageData`, `_bt_set_cleanup_info`
sets it to `-1.0`, WAL redo reconstructs it as `-1.0`, and `pageinspect`
exposes it from `bt_metap`
([nbtree.h#BTMetaPageData](../../../../raw/postgres-18/src/include/access/nbtree.h#L104),
[nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232),
[nbtxlog.c#_bt_restore_meta](../../../../raw/postgres-18/src/backend/access/nbtree/nbtxlog.c#L82),
[btreefuncs.c#bt_metap](../../../../raw/postgres-18/contrib/pageinspect/btreefuncs.c#L838)).
Preserving a density value through crash recovery therefore requires changing
the metadata WAL record and redo path, and exposing or hiding the changed field
requires `pageinspect` API decisions
([nbtxlog.h#xl_btree_metadata](../../../../raw/postgres-18/src/include/access/nbtxlog.h#L49),
[nbtxlog.c#_bt_restore_meta](../../../../raw/postgres-18/src/backend/access/nbtree/nbtxlog.c#L82),
[btreefuncs.c#bt_metap](../../../../raw/postgres-18/contrib/pageinspect/btreefuncs.c#L838)).

The cumulative statistics path is queryable, but it is not a durable source of
truth. PostgreSQL 18 loads cumulative stats from the filesystem at startup
unless startup follows a crash, discards all stats after crash, and writes stats
before clean shutdown only for stats kinds that allow it
([pgstat.c](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c)).
Relation stats reset by zeroing the `PgStat_StatTabEntry`, so a B-tree density
field in that struct needs an explicit validity bit or it cannot distinguish
"no value" from real `0.0` density
([pgstat_shmem.c#shared_stat_reset_contents](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L1109),
[pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-18/src/include/pgstat.h#L422)).

Exact `pgstatindex` parity is harder than a per-live-leaf counter. `pgstatindex`
counts live leaf pages, counts half-dead pages separately as empty pages, and
counts fully deleted pages separately
([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-18/contrib/pgstattuple/pgstatindex.c#L213)).
During B-tree VACUUM, an empty leaf enters `_bt_pagedel`, but `_bt_pagedel` can
return without deleting the page when the page is rightmost, root, no longer
empty after relocking, or part of an incomplete split; it also can delete a
right sibling in passing after deleting the original leaf page
([nbtpage.c#_bt_pagedel](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L1802),
[nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361)).
An exact post-VACUUM density therefore needs deletion-aware accounting across
`btvacuumpage`, `_bt_pagedel`, and `_bt_unlink_halfdead_page`, not just a single
counter in the `P_ISLEAF` branch
([nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361),
[nbtpage.c#_bt_pagedel](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L1802),
[nbtpage.c#_bt_unlink_halfdead_page](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L2314)).

The value may need to be documented as an estimate under concurrent structural
changes. `btvacuumscan` repeatedly rechecks relation length so it can visit leaf
pages added after the scan starts, `btvacuumpage` backtracks for pages moved by
splits, and `btvacuumcleanup` already treats tuple counts as suspect because
concurrent page splits can double-count index tuples
([nbtree.c#btvacuumscan](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1186),
[nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361),
[nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098)).

Parallel VACUUM adds another integration surface. Manual parallel VACUUM stores
each index's `IndexBulkDeleteResult` in dynamic shared memory, copies it with
`sizeof(IndexBulkDeleteResult)`, and runs index bulk-delete/cleanup in leader or
worker processes; PostgreSQL 18 does not use parallel VACUUM workers for
autovacuum
([vacuumparallel.c#parallel_vacuum_end](../../../../raw/postgres-18/src/backend/commands/vacuumparallel.c#L436),
[vacuumparallel.c#parallel_vacuum_process_one_index](../../../../raw/postgres-18/src/backend/commands/vacuumparallel.c#L865),
[vacuumparallel.c#parallel_vacuum_main](../../../../raw/postgres-18/src/backend/commands/vacuumparallel.c#L989)).
Any density result added to the AM result contract must stay correct in that DSM
copy path, not just in the serial lazy VACUUM path
([genam.h#IndexBulkDeleteResult](../../../../raw/postgres-18/src/include/access/genam.h#L98),
[vacuumparallel.c#parallel_vacuum_end](../../../../raw/postgres-18/src/backend/commands/vacuumparallel.c#L436)).

## When the Value Will *Not* Refresh (coverage caveats)

The figure describes the **last index scan**, not the live index. VACUUM can
correctly skip the B-tree scan:

- `btvacuumcleanup` returns `NULL` without scanning when there was no
  `btbulkdelete` and `_bt_vacuum_needs_cleanup` is false (the common
  no-dead-tuples, few-deleted-pages case)
  ([nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098),
  [nbtpage.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L179)).
- VACUUM skips index vacuuming entirely under `INDEX_CLEANUP off` or when the
  wraparound failsafe is active
  ([vacuumlazy.c#heap_vacuum_rel](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L615),
  [vacuumlazy.c#lazy_check_wraparound_failsafe](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L2964)).

In all of these, `stats` is `NULL` or unscanned, so **leave the stored density
unchanged** and keep its previous timestamp/value. Do not write a zero or a
stale recomputation. Document that the field reflects the most recent scan. For
the stats surface, a new per-index reporter can reuse the existing
`last_vacuum_time`/`last_autovacuum_time` fields in `PgStat_StatTabEntry`, but
v18's `pg_stat_all_indexes` does not expose those timestamps today
([pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-18/src/include/pgstat.h#L422),
[system_views.sql#pg_stat_all_indexes](../../../../raw/postgres-18/src/backend/catalog/system_views.sql#L803)).

## Accuracy Notes

- The leaf-branch counter is post-compaction within this VACUUM, so it reflects
  item deletion on pages that remain leaves. It reflects the index exactly as
  VACUUM leaves it only if the implementation also subtracts counted leaves that
  `_bt_pagedel` later marks half-dead/deleted, and keeps or rechecks empty
  leaves that `_bt_pagedel` fails to delete
  ([nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361),
  [nbtpage.c#_bt_pagedel](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L1802)).
- Concurrent page splits can make `btvacuumscan` visit a moved page twice; this
  is the same known double-counting class already acknowledged for
  `num_index_tuples`
  ([nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098)).
  The density error from this is bounded and no worse than the existing tuple
  estimate, so treating it as an estimate (like `estimated_count`) is
  consistent.
- The backtrack path in `btvacuumpage` re-reads a sibling block but the
  `btpo_cycleid`/`P_ISDELETED` early-return guard prevents reprocessing a page
  already handled, so accumulation stays once-per-live-leaf
  ([nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361)).
- Parallel VACUUM copies `IndexBulkDeleteResult` through dynamic shared memory
  with `sizeof(IndexBulkDeleteResult)`, so a new result field must be included
  in the parallel copy/reporting path, not only the serial
  `lazy_vacuum_one_index` path
  ([vacuumparallel.c](../../../../raw/postgres-18/src/backend/commands/vacuumparallel.c)).

## Minimal Change List

1. `BTVacState`: add `nleaf`, `sum_free_space`, `sum_max_avail`
   ([nbtree.h#BTVacState](../../../../raw/postgres-18/src/include/access/nbtree.h#L331)).
2. `btvacuumscan`: zero them with the other resets; derive `avg_leaf_density`
   after the page loop
   ([nbtree.c#btvacuumscan](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1186)).
3. `btvacuumpage`: accumulate in the `P_ISLEAF` branch after compaction, and
   add page-deletion accounting if the stored value must match `pgstatindex`
   after VACUUM rather than "post-compaction leaves seen during the scan"
   ([nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361),
   [nbtpage.c#_bt_pagedel](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L1802)).
4. `IndexBulkDeleteResult`: add `avg_leaf_density` plus a validity flag
   ([genam.h#IndexBulkDeleteResult](../../../../raw/postgres-18/src/include/access/genam.h#L98)).
5. Metapage path: preferably reuse/rename deprecated
   `btm_last_cleanup_num_heap_tuples`; update `_bt_set_cleanup_info`,
   `xl_btree_metadata`, `_bt_restore_meta`, and `pageinspect`
   ([nbtree.h#BTMetaPageData](../../../../raw/postgres-18/src/include/access/nbtree.h#L104),
   [nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232),
   [nbtxlog.h#xl_btree_metadata](../../../../raw/postgres-18/src/include/access/nbtxlog.h#L49),
   [nbtxlog.c#_bt_restore_meta](../../../../raw/postgres-18/src/backend/access/nbtree/nbtxlog.c#L82),
   [btreefuncs.c#bt_metap](../../../../raw/postgres-18/contrib/pageinspect/btreefuncs.c#L838)).
6. Stats path: extend `PgStat_StatTabEntry`, add a reporter beside
   `pgstat_report_vacuum`, report after serial/parallel index work has
   populated `vacrel->indstats`, add a C accessor, catalog entry, and view
   column
   ([pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-18/src/include/pgstat.h#L422),
   [pgstat_relation.c#pgstat_report_vacuum](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_relation.c#L210),
   [vacuumlazy.c#lazy_cleanup_one_index](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L3061),
   [pgstatfuncs.c](../../../../raw/postgres-18/src/backend/utils/adt/pgstatfuncs.c),
   [pg_proc.dat](../../../../raw/postgres-18/src/include/catalog/pg_proc.dat)).
7. No autovacuum-specific change: the autovacuum worker uses the same path and
   is already distinguished by `AmAutoVacuumWorkerProcess()`
   ([autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L3173),
   [pgstat_relation.c#pgstat_report_vacuum](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_relation.c#L210)).

## Context Reviewed

- B-tree VACUUM driver and per-page handler: `btbulkdelete`,
  `btvacuumcleanup`, `btvacuumscan`, `btvacuumpage`
  ([nbtree.c#btvacuumscan](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1186)).
- Metapage maintenance and WAL: `_bt_set_cleanup_info`,
  `_bt_vacuum_needs_cleanup`, `_bt_restore_meta`, `BTMetaPageData`,
  `xl_btree_metadata`.
- VACUUM/index boundary: `lazy_vacuum_one_index`, `lazy_cleanup_one_index`,
  `vac_bulkdel_one_index`, `vac_cleanup_one_index`, `IndexVacuumInfo`,
  `IndexBulkDeleteResult`, and parallel vacuum result copying.
- Statistics surface: `pgstat_report_vacuum`, `PgStat_StatTabEntry`,
  `PGSTAT_KIND_RELATION`, `pgstatfuncs.c`, `pg_proc.dat`, and
  `pg_stat*_all_indexes` view definitions.
- Autovacuum entry: `autovacuum_do_vac_analyze` and the shared
  `vacuum_rel`/lazy VACUUM path.
- Reference semantics: `pgstatindex_impl`, `PageGetExactFreeSpace`,
  `SizeOfPageHeaderData`.

## Evidence Map

| Claim | Source |
|---|---|
| `avg_leaf_density = 100 - free/max_avail*100`, NaN if no leaves | [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-18/contrib/pgstattuple/pgstatindex.c#L213) |
| Free space is `pd_upper - pd_lower` | [bufpage.c#PageGetExactFreeSpace](../../../../raw/postgres-18/src/backend/storage/page/bufpage.c#L957) |
| `btvacuumscan` visits every leaf under cleanup lock when the B-tree scan runs | [nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361), [nbtree.c#btvacuumscan](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1186) |
| `_bt_set_cleanup_info` may early-return without dirtying the metapage | [nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232) |
| Empty page deletion can succeed or return without deleting | [nbtpage.c#_bt_pagedel](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L1802) |
| Index scan can be skipped entirely | [nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098), [nbtpage.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L179) |
| Stats write is shared-memory, autovacuum-aware, and persisted only through the stats-file path | [pgstat_relation.c#pgstat_report_vacuum](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_relation.c#L210), [pgstat.c](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c) |
| AM result contract struct | [genam.h#IndexBulkDeleteResult](../../../../raw/postgres-18/src/include/access/genam.h#L98) |

## Source References

- [nbtree.c#btvacuumscan](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1186) - whole-index VACUUM scan; reset point for accumulators and derivation site.
- [nbtree.c#btvacuumpage](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1361) - per-page handler; `P_ISLEAF` branch is the accumulation point and the `attempt_pagedel` decision point.
- [nbtree.c#btvacuumcleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L1098) - cleanup entry; skip-scan decision and metapage maintenance call.
- [nbtpage.c#_bt_pagedel](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L1802), [nbtpage.c#_bt_unlink_halfdead_page](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L2314) - page-deletion path that exact post-VACUUM density must account for.
- [nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L232) - conditional metapage write and early-return guard.
- [nbtpage.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-18/src/backend/access/nbtree/nbtpage.c#L179) - when the index scan is skipped entirely.
- [nbtxlog.c#_bt_restore_meta](../../../../raw/postgres-18/src/backend/access/nbtree/nbtxlog.c#L82) - metapage WAL redo to extend.
- [nbtree.h#BTVacState](../../../../raw/postgres-18/src/include/access/nbtree.h#L331), [nbtree.h#BTMetaPageData](../../../../raw/postgres-18/src/include/access/nbtree.h#L104) - structs to extend.
- [nbtxlog.h#xl_btree_metadata](../../../../raw/postgres-18/src/include/access/nbtxlog.h#L49) - WAL record struct to extend.
- [genam.h#IndexBulkDeleteResult](../../../../raw/postgres-18/src/include/access/genam.h#L98) - AM-to-VACUUM result contract.
- [vacuumlazy.c#lazy_cleanup_one_index](../../../../raw/postgres-18/src/backend/access/heap/vacuumlazy.c#L3061) - VACUUM/index boundary and stats reporting site.
- [vacuum.c#vac_bulkdel_one_index](../../../../raw/postgres-18/src/backend/commands/vacuum.c#L2651), [indexam.c#index_bulk_delete](../../../../raw/postgres-18/src/backend/access/index/indexam.c#L795) - generic VACUUM-to-index-AM bridge.
- [vacuumparallel.c](../../../../raw/postgres-18/src/backend/commands/vacuumparallel.c) - parallel VACUUM copies `IndexBulkDeleteResult`.
- [autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L3173) - autovacuum enters the shared `vacuum()` path.
- [pgstat_relation.c#pgstat_report_vacuum](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_relation.c#L210) - model for the cumulative-stats reporter.
- [pgstat.c](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c), [pgstat_shmem.c#shared_stat_reset_contents](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L1109) - stats persistence and reset behavior.
- [pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-18/src/include/pgstat.h#L422) - cumulative stats entry to extend.
- [pgstatfuncs.c](../../../../raw/postgres-18/src/backend/utils/adt/pgstatfuncs.c), [pg_proc.dat](../../../../raw/postgres-18/src/include/catalog/pg_proc.dat), [system_views.sql#pg_stat_all_indexes](../../../../raw/postgres-18/src/backend/catalog/system_views.sql#L803) - accessor and view surface for `pg_stat_all_indexes`.
- [btreefuncs.c#bt_metap](../../../../raw/postgres-18/contrib/pageinspect/btreefuncs.c#L838) - existing metapage field exposure.
- [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-18/contrib/pgstattuple/pgstatindex.c#L213) - reference `avg_leaf_density` semantics.
- [bufpage.c#PageGetExactFreeSpace](../../../../raw/postgres-18/src/backend/storage/page/bufpage.c#L957) - free-space primitive used in the formula.

## Open Questions

- This page proposes a code modification, not a description of existing
  behavior. The accumulation/storage logic is designed from verified source but
  has not been compiled or runtime-verified; treat code snippets as design
  intent, not patches.
- Exact post-VACUUM parity needs a concrete design for subtracting counted leaf
  pages that `_bt_pagedel` deletes, including empty right siblings deleted in
  passing. The low-overhead design sketched here needs implementation review.
- Adding B-tree-only fields to the shared `PgStat_StatTabEntry` wastes bytes for
  table entries and non-B-tree indexes. A separate `PGSTAT_KIND_*` for index
  physical stats, or a `pgstat` variable-numbered stats entry, may be cleaner
  but was not traced here.
- Reusing `btm_last_cleanup_num_heap_tuples` avoids growing `BTMetaPageData`,
  but it changes the meaning of a field exposed by `pageinspect`. Adding a new
  metapage field instead would require a metapage version and pg_upgrade story.
- Extending `xl_btree_metadata` implies WAL compatibility/release-process work;
  the exact `XLOG_PAGE_MAGIC` and upgrade requirements were not assessed here.
- Whether to expose no-leaf/no-scan as SQL `NULL` vs `'NaN'::float8` to match
  `pgstatindex` output exactly is a UI decision left open.
