---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: claude-opus-5-max 2026-08-31T14:13:19Z
---

# Measuring Heap and TOAST Bloat With pgstattuple_approx in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Verdict](#verdict)
  - [The statement](#the-statement)
  - [Output columns](#output-columns)
  - [Why the TOAST row cannot come from pgstattuple_approx](#why-the-toast-row-cannot-come-from-pgstattuple_approx)
  - [Where fillfactor and its reserve come from](#where-fillfactor-and-its-reserve-come-from)
  - [Why the TOAST heap gets no fillfactor adjustment](#why-the-toast-heap-gets-no-fillfactor-adjustment)
  - [Which numbers are exact and which are approximate](#which-numbers-are-exact-and-which-are-approximate)
  - [Tables with no TOAST relation, and zero-length relations](#tables-with-no-toast-relation-and-zero-length-relations)
  - [Test setup](#test-setup)
  - [Measured output](#measured-output)
  - [Scored against VACUUM FULL](#scored-against-vacuum-full)
  - [The one formula error worth knowing](#the-one-formula-error-worth-knowing)
  - [TOAST free space is mostly chunk geometry](#toast-free-space-is-mostly-chunk-geometry)
  - [Cost of the two passes](#cost-of-the-two-passes)
  - [Interpretation guide](#interpretation-guide)
  - [What ordinary VACUUM does and does not shrink](#what-ordinary-vacuum-does-and-does-not-shrink)
  - [Privileges](#privileges)
  - [Settings and apply scope](#settings-and-apply-scope)
  - [Query-construction hazards on this pin](#query-construction-hazards-on-this-pin)
  - [Test coverage in the pinned tree](#test-coverage-in-the-pinned-tree)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Create and test a PostgreSQL SQL query to measure heap and TOAST-table bloat using `pgstattuple_approx`. Include:

- Main heap and associated TOAST heap as separate measurements.
- Physical size, live tuples, dead tuples, free space, and scanned percentage.
- The main table's effective `fillfactor`, defaulting to 100.
- Expected reserved free space as `100 - fillfactor`.
- Estimated bloat as dead-tuple space plus free space exceeding the fillfactor reserve.
- No main-table fillfactor adjustment for the TOAST heap.
- Human-readable byte sizes and percentages.
- Safe handling of tables without TOAST relations and zero-length relations.
- Clear explanations that dead-tuple statistics are exact, while live-tuple and free-space statistics are approximate.
- Guidance for interpreting high dead space, high reusable free space, intentional fillfactor headroom, and TOAST bloat.
- A warning that ordinary `VACUUM` reuses space but generally does not shrink the physical relation.
- Support for a configurable schema and table name.
- Valid PostgreSQL SQL that can be run directly after installing the `pgstattuple` extension.

## Answer

### Verdict

The statement below satisfies every item, with one substitution that PostgreSQL 12 forces: **the TOAST row cannot be measured by `pgstattuple_approx`.** That function rejects any relation that is not `RELKIND_RELATION` or `RELKIND_MATVIEW`, and a TOAST relation is `RELKIND_TOASTVALUE` ([pgstatapprox.c#relkind-check](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L280-L290)). Measured on the pinned build:

```text
=> select * from pgstattuple_approx((select reltoastrelid from pg_class where oid='bl.f_both'::regclass));
ERROR:  "pg_toast_16405" is not a table or materialized view
```

The exact function does accept `RELKIND_TOASTVALUE` ([pgstattuple.c#pgstat_relation](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L240-L261)), so the statement measures the main heap with `pgstattuple_approx` and the TOAST heap with `pgstattuple`, and labels each row with the function that produced it. Both functions ship in the same extension, so the "runnable after `CREATE EXTENSION pgstattuple`" requirement still holds ([pgstattuple--1.4.sql#pgstattuple_approx](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L83-L95), [pgstattuple--1.4.sql#pgstattuple-regclass](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L49-L60)).

Four results from testing it against `VACUUM FULL` on an isolated 12.2 server built from this pin, over ten fixtures:

1. **The requested bloat formula is exact-form at `fillfactor = 100` and conservative below it.** Across the seven main-heap rows at `fillfactor = 100`, "dead space plus free space above the reserve" landed within −4.02 to +8.98 points of what `VACUUM FULL` actually reclaimed. On the one bloated `fillfactor = 70` table it read **34.46% against a truth of 50.00%**, a 15.54-point understatement, because the reserve is charged against the *current* size rather than the post-rewrite size. See [The one formula error worth knowing](#the-one-formula-error-worth-knowing).
2. **TOAST free space is mostly geometry, not bloat.** A never-deleted TOAST relation reported **19.58% free** and `VACUUM FULL` reclaimed **0.00%**. The whole 19.58% is the tail page of each value's last chunk. Changing the payload from 6,400 to 3,992 bytes - an exact multiple of `TOAST_MAX_CHUNK_SIZE` - moved the same reading to **0.24%**. See [TOAST free space is mostly chunk geometry](#toast-free-space-is-mostly-chunk-geometry).
3. **The TOAST pass is the expensive half.** On a 296 kB heap with a 39 MB TOAST relation the whole statement ran in 21.1 ms, of which the heap branch cost 45 buffer accesses and the TOAST branch cost 10,006 - exactly two per TOAST page, because `pgstat_heap()` touches every page twice ([pgstattuple.c#free-space-loop](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L365-L383)).
4. **A table can be entirely healthy in its heap and 75% reclaimable in its TOAST relation.** The `f_toastonly` fixture rewrote every payload three times: the heap stayed at 200 kB while the TOAST relation grew to 31 MB, of which `VACUUM FULL` reclaimed 75.00%. Measuring only the main fork would have missed 24 MB.

The `fillfactor` reserve for the TOAST row is not a modelling choice; it is what the server does. `heap_reloptions()` overwrites `fillfactor` with 100 for every `RELKIND_TOASTVALUE` relation ([reloptions.c#heap_reloptions](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L1476-L1493)), and the reloption cannot be set on a TOAST table at all ([create_table.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L1319-L1339)).

### The statement

Set the two timeouts first; both are `PGC_USERSET`, so `SET` applies to the session or transaction with no reload or restart ([guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2386), [guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2397)). The TOAST pass is a full scan, so 5 minutes is a starting point for a table under a few GB, not a universal value.

```sql
SET statement_timeout = '5min';
SET lock_timeout = '5s';

\set target_schema 'public'
\set target_table  'orders'

WITH target AS MATERIALIZED (
    SELECT c.oid           AS heap_oid,
           c.reltoastrelid AS toast_oid,
           coalesce((SELECT o.option_value::int
                       FROM pg_options_to_table(c.reloptions) o
                      WHERE o.option_name = 'fillfactor'), 100) AS fillfactor
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = :'target_schema'
       AND c.relname = :'target_table'
       AND c.relkind IN ('r', 'm')
       AND c.relam = (SELECT oid FROM pg_am WHERE amname = 'heap')
),
toast_target AS MATERIALIZED (
    SELECT toast_oid
      FROM target
     WHERE toast_oid <> 0
),
measured AS (
    SELECT 1                    AS part_order,
           'main heap'::text    AS part,
           t.heap_oid           AS relid,
           t.fillfactor         AS fillfactor,
           s.table_len          AS physical_bytes,
           s.approx_tuple_count AS live_tuples,
           s.approx_tuple_len   AS live_bytes,
           s.dead_tuple_count   AS dead_tuples,
           s.dead_tuple_len     AS dead_bytes,
           s.approx_free_space  AS free_bytes,
           s.scanned_percent    AS scanned_pct,
           'pgstattuple_approx (live/free approximate)'::text AS measured_by
      FROM target t
      CROSS JOIN LATERAL pgstattuple_approx(t.heap_oid) s
    UNION ALL
    SELECT 2, 'toast heap', tt.toast_oid, 100,
           s.table_len, s.tuple_count, s.tuple_len,
           s.dead_tuple_count, s.dead_tuple_len, s.free_space,
           100::float8, 'pgstattuple (exact, full scan)'
      FROM toast_target tt
      CROSS JOIN LATERAL pgstattuple(tt.toast_oid) s
),
computed AS (
    SELECT m.*,
           (m.physical_bytes / current_setting('block_size')::bigint)
             * (current_setting('block_size')::bigint * (100 - m.fillfactor) / 100)
             AS reserved_bytes
      FROM measured m
)
SELECT /* wiki_heap_toast_bloat */
       c.part,
       c.relid::regclass                       AS relation,
       pg_size_pretty(c.physical_bytes)        AS physical_size,
       c.live_tuples,
       pg_size_pretty(c.live_bytes)            AS live_size,
       c.dead_tuples,
       pg_size_pretty(c.dead_bytes)            AS dead_size,
       coalesce(round(100.0 * c.dead_bytes / nullif(c.physical_bytes, 0), 2), 0.00) AS dead_pct,
       pg_size_pretty(c.free_bytes)            AS free_size,
       coalesce(round(100.0 * c.free_bytes / nullif(c.physical_bytes, 0), 2), 0.00) AS free_pct,
       c.fillfactor,
       100 - c.fillfactor                      AS reserved_pct,
       pg_size_pretty(c.reserved_bytes)        AS reserved_size,
       pg_size_pretty(c.dead_bytes + greatest(c.free_bytes - c.reserved_bytes, 0)) AS est_bloat_size,
       coalesce(round(100.0 * (c.dead_bytes + greatest(c.free_bytes - c.reserved_bytes, 0))
                            / nullif(c.physical_bytes, 0), 2), 0.00) AS est_bloat_pct,
       c.scanned_pct::int                      AS scanned_pct,
       c.measured_by
  FROM computed c
 ORDER BY c.part_order;

RESET statement_timeout;
RESET lock_timeout;
```

Seventeen columns is wide for a terminal; run it under `\x on`. The two `\set` lines are the configurable target. Outside `psql`, drop them and bind `$1`/`$2` in place of `:'target_schema'` and `:'target_table'`; nothing else in the statement is client-specific.

### Output columns

| Column | Source | Exactness |
|---|---|---|
| `part` | literal, `main heap` or `toast heap` | - |
| `relation` | `relid::regclass`; the TOAST row prints `pg_toast.pg_toast_NNNNN` | exact |
| `physical_size` | `table_len`, which is `nblocks * BLCKSZ` in both functions ([pgstatapprox.c:185](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L185), [pgstattuple.c:401](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L401)) | exact |
| `live_tuples`, `live_size` | heap row: `approx_tuple_count`/`approx_tuple_len`; TOAST row: `tuple_count`/`tuple_len` | heap row approximate, TOAST row exact |
| `dead_tuples`, `dead_size`, `dead_pct` | `dead_tuple_count`/`dead_tuple_len` from either function | exact in both |
| `free_size`, `free_pct` | heap row: `approx_free_space`; TOAST row: `free_space` | heap row approximate, TOAST row exact |
| `fillfactor` | `pg_class.reloptions` via `pg_options_to_table()`, defaulting to 100; forced to 100 on the TOAST row | exact |
| `reserved_pct` | `100 - fillfactor` | exact |
| `reserved_size` | `pages * (BLCKSZ * (100 - fillfactor) / 100)`, the same integer arithmetic as `RelationGetTargetPageFreeSpace()` | exact |
| `est_bloat_size`, `est_bloat_pct` | `dead_bytes + greatest(free_bytes - reserved_bytes, 0)` | derived; see [Scored against VACUUM FULL](#scored-against-vacuum-full) |
| `scanned_pct` | heap row: `scanned_percent`; TOAST row: 100 by construction | heap row is integer-truncated |
| `measured_by` | literal, names the function and its exactness | - |

Two labelling notes that matter when reading the TOAST row. Its `live_tuples` counts **TOAST chunks**, not table rows: a value is split into chunks of at most `TOAST_MAX_CHUNK_SIZE` bytes, one chunk per row of the TOAST relation ([tuptoaster.h#TOAST_MAX_CHUNK_SIZE](../../../../raw/postgres-12/src/include/access/tuptoaster.h#L77-L96), [storage.sgml#toast-ondisk](../../../../raw/postgres-12/doc/src/sgml/storage.sgml#L413-L424)). And `physical_size` on both rows is the main fork of that one relation, so neither row includes the TOAST relation's own B-tree index; that index is a third relation and needs `pgstatindex` or `pgstattuple`.

`pg_size_pretty` prints exact bytes below 10,240 and half-rounds to `kB`, `MB`, `GB` or `TB` above it ([dbsize.c#pg_size_pretty](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L533-L572), [pg_proc.dat#pg_size_pretty](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L6896-L6903)), so `39 MB` in the output below is 40,960,000 bytes. A monitoring job should keep the raw `bigint` expressions and let the dashboard format them; the pretty form is for a human at a prompt.

### Why the TOAST row cannot come from pgstattuple_approx

`pgstattuple_approx_internal()` opens the relation, rejects other sessions' temporary tables, then applies two gates ([pgstatapprox.c#pgstattuple_approx_internal](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L251-L296)):

| Gate | Condition | Error |
|---|---|---|
| relkind | not `RELKIND_RELATION` and not `RELKIND_MATVIEW` ([pgstatapprox.c#relkind-check](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L280-L290)) | `"%s" is not a table or materialized view` |
| relam | `relam != HEAP_TABLE_AM_OID` ([pgstatapprox.c#relam-check](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L292-L294)) | `only heap AM is supported` |

The stated reason for the relkind gate is the estimator's dependence on the visibility map and free space map, not anything about TOAST: "We support only ordinary relations and materialised views, because we depend on the visibility map and free space map for our estimates about unscanned pages" ([pgstatapprox.c#relkind-check](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L280-L290)). A TOAST relation has both maps and is an ordinary heap in every other respect - `relam` is the heap AM, and `VACUUM` processes it through the same `vacuum_rel()` ([vacuum.c#toast_relid](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1796-L1800), [vacuum.c#vacuum-toast](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1855-L1857)) - so the refusal is a gap in the gate rather than a physical limitation. Measured on `f_both` after its `VACUUM`, `pg_relation_size(oid, 'vm')` and `pg_relation_size(oid, 'fsm')` returned 8,192 and 24,576 bytes for the table and 8,192 and 32,768 for its TOAST relation: both forks exist on both relations. It is recorded as [Open Questions](#open-questions) item 1.

`pgstat_relation()` in the exact function lists `RELKIND_TOASTVALUE` among the four kinds that route to `pgstat_heap()` ([pgstattuple.c#pgstat_relation](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L240-L261)), which is why the substitution works. Measured on the pin, the TOAST relation of a 5,000-row fixture returned a full row from `pgstattuple` in the same session where `pgstattuple_approx` had just refused it.

### Where fillfactor and its reserve come from

`fillfactor` is a table storage parameter, not a GUC. The heap entry is registered for `RELOPT_KIND_HEAP` with default `HEAP_DEFAULT_FILLFACTOR` = 100, minimum `HEAP_MIN_FILLFACTOR` = 10, maximum 100, and `ShareUpdateExclusiveLock` "since it applies only to later inserts" ([reloptions.c#fillfactor-heap](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L167-L176), [rel.h#HEAP_DEFAULT_FILLFACTOR](../../../../raw/postgres-12/src/include/utils/rel.h#L278-L279)). It is stored in `pg_class.reloptions` ([pg_class.h:134](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L134)) and absent when never set, which is exactly the `coalesce(..., 100)` in the statement; `RelationGetFillFactor()` applies the same default in C when `rd_options` is null ([rel.h#RelationGetFillFactor](../../../../raw/postgres-12/src/include/utils/rel.h#L289-L295)).

The percentage becomes bytes in one macro:

```c
#define RelationGetTargetPageFreeSpace(relation, defaultff) \
	(BLCKSZ * (100 - RelationGetFillFactor(relation, defaultff)) / 100)
```

([rel.h#RelationGetTargetPageFreeSpace](../../../../raw/postgres-12/src/include/utils/rel.h#L304-L309)). The statement reproduces that expression with `bigint` arithmetic, including the integer truncation: at `fillfactor = 70` and `BLCKSZ = 8192` the reserve is 2,457 bytes per page, not 2,457.6. `block_size` is a `PGC_INTERNAL` preset that reports the compile-time `BLCKSZ` ([guc.c#block_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2879-L2888)), so reading it through `current_setting()` keeps the statement correct on a non-default build.

The reserve is real, not advisory: `RelationGetBufferForTuple()` computes `saveFreeSpace` from that macro and accepts a candidate page only when `len + saveFreeSpace <= PageGetHeapFreeSpace(page)` ([hio.c#saveFreeSpace](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L348-L350), [hio.c#accept-page](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L500-L508)). Documentation states the same contract from the user's side: 10 to 100, default 100, remaining space "reserved for updating rows on that page" ([create_table.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L1319-L1339)). Measured on the pin, `fillfactor = 9` and `fillfactor = 101` are both refused by the generic bounds check with `DETAIL: Valid values are between "10" and "100".` ([reloptions.c#int-bounds](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L1214-L1221)).

### Why the TOAST heap gets no fillfactor adjustment

Three independent pieces of source say the TOAST relation's fillfactor is 100 and cannot be anything else:

1. `heap_reloptions()` parses TOAST reloptions under `RELOPT_KIND_TOAST` and then **overwrites** the parsed value: `rdopts->fillfactor = 100;`, commented "adjust default-only parameters for TOAST relations" ([reloptions.c#heap_reloptions](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L1476-L1493)).
2. The `fillfactor` entry in `intRelOpts` is registered only for `RELOPT_KIND_HEAP` among table kinds, so a `toast.fillfactor` setting never reaches the parser as a known name and dies in the generic unrecognized-parameter path ([reloptions.c#fillfactor-heap](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L167-L176), [reloptions.c#unrecognized-parameter](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L1146-L1155)).
3. The documentation says it outright: "This parameter cannot be set for TOAST tables" ([create_table.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L1319-L1339)).

Measured on the pin:

| statement | result |
|---|---|
| `ALTER TABLE bl.f_ff70 SET (toast.fillfactor = 70)` | `ERROR: unrecognized parameter "fillfactor"` |
| `pg_class.reloptions` of `bl.f_ff70` after `WITH (fillfactor = 70)` | `{fillfactor=70}` |
| `pg_class.reloptions` of its TOAST relation | `NULL` |

So the main table's reloption is not inherited by the TOAST relation, and the TOAST insert path acts on a fillfactor of 100. That path is `toast_save_datum()`, which splits the datum with `chunk_size = Min(TOAST_MAX_CHUNK_SIZE, data_todo)` and inserts each chunk with plain `heap_insert()` ([tuptoaster.c#chunk-loop](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L1636-L1658)), which reaches the same `RelationGetTargetPageFreeSpace(relation, HEAP_DEFAULT_FILLFACTOR)` and therefore reserves zero bytes. Hard-coding 100 on the TOAST row is not an approximation; it is the value the server used when the chunks were written.

### Which numbers are exact and which are approximate

`pgstattuple_approx` walks every block of the main fork once and takes one of two paths per block ([pgstatapprox.c#statapprox_heap](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L64-L214)):

| Path | Condition | live length | free space | dead counters |
|---|---|---|---|---|
| skip | the visibility-map bit is set ([pgstatapprox.c#vm-skip](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L90-L100)) | `BLCKSZ - GetRecordedFreeSpace()` | the free space map value | untouched |
| scan | otherwise ([pgstatapprox.c#scan-path](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L102-L125)) | sum of `t_len` over live tuples | `PageGetHeapFreeSpace(page)` | exact, from the page |

Consequences, each of which the statement's `measured_by` column is meant to remind the reader of:

- **Dead statistics are exact for the pages that were scanned, and zero by construction for the pages that were skipped.** A page holding a dead tuple cannot be all-visible: `heap_delete()` clears the page's visibility-map bit ([heapam.c#heap_delete-clears-vm](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L2704-L2710)), and `lazy_scan_heap()` refuses to set the bit again while any `LP_DEAD` item remains ([vacuumlazy.c#LP_DEAD-clears-all-visible](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1019-L1030)). Classification uses `HeapTupleSatisfiesVacuum()` against `GetOldestXmin()`, counting `HEAPTUPLE_DEAD`, `HEAPTUPLE_RECENTLY_DEAD` and `HEAPTUPLE_INSERT_IN_PROGRESS` as dead ([pgstatapprox.c#tuple-classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L157-L179)).
- **Live length is inflated on skipped pages.** For a skipped page the function charges everything the free space map does not call free, which includes the page header (`SizeOfPageHeaderData`, 24 bytes on this build), 4 bytes per line pointer whether used or not, and per-tuple alignment padding ([pgstatapprox.c:97](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L97), [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L216)). Do not compare `live_size` across the two rows of this statement: the heap row is page occupancy, the TOAST row is a true sum of `t_len`.
- **Live count is extrapolated, not counted**, by the same routine VACUUM uses for `pg_class.reltuples`; when no page is scanned it returns the stored `reltuples` verbatim ([pgstatapprox.c#reltuples-call](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L187-L196), [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1071-L1112)).
- **Free space on skipped pages is a free-space-map category lower bound**, and the category step is `BLCKSZ / 256` = 32 bytes ([freespace.c#GetRecordedFreeSpace](../../../../raw/postgres-12/src/backend/storage/freespace/freespace.c#L229-L247), [freespace.c#FSM_CAT_STEP](../../../../raw/postgres-12/src/backend/storage/freespace/freespace.c#L63-L65)). The documentation notes the same rounding ([pgstattuple.sgml#fsm-caveat](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L608-L613)).
- **`scanned_percent` truncates.** It is computed as an integer division into a `uint64` field ([pgstatapprox.c#percentages](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L198-L207)). Measured: with 1 page of 5,000 not all-visible, the column reported `0` where the true value is 0.02. A `scanned_pct` of 0 therefore means "at most 1% of the pages", not "no page".

The TOAST row is exact in every column, at the cost of reading every page: `pgstat_heap()` scans with `SnapshotAny` and classifies each tuple with a dirty snapshot ([pgstattuple.c#pgstat_heap](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L318-L363), [pgstattuple.sgml#dirty-snapshot](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L139-L142)), and adds up `PageGetHeapFreeSpace()` for every block including those the scan found empty ([pgstattuple.c#free-space-loop](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L365-L396)). The documented contract for the two functions matches this reading exactly ([pgstattuple.sgml#approx-contract](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L515-L539)).

One difference the two rows inherit from their functions: an in-flight bulk load into the main table shows up as dead space on the heap row, because `pgstattuple_approx` follows VACUUM and calls `HEAPTUPLE_INSERT_IN_PROGRESS` dead, while the dirty snapshot behind the TOAST row treats another transaction's uncommitted insert as live. The two rows are not measured on the same definition of "dead".

### Tables with no TOAST relation, and zero-length relations

**No TOAST relation.** `pg_class.reltoastrelid` is 0 when a table has no TOAST-able column ([pg_class.h:69](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L69), [storage.sgml#reltoastrelid](../../../../raw/postgres-12/doc/src/sgml/storage.sgml#L405-L411)). Passing 0 to either function is not a silent no-op - it aborts the statement:

```text
=> select * from pgstattuple(0);
ERROR:  could not open relation with OID 0
```

That error comes from `relation_open()`, below both functions ([relation.c#relation_open](../../../../raw/postgres-12/src/backend/access/common/relation.c#L47-L62)). The statement keeps `WHERE toast_oid <> 0` in the `toast_target` CTE, one query level below the lateral call, so the function is never reached for such a table. Measured on `bl.f_notoast` (three fixed-width columns, `reltoastrelid = 0`): one row, the main heap, no error.

**Zero-length relations.** `table_len = 0` is reachable three ways: a table created and never inserted into, a truncated table, and - very commonly - the TOAST relation of a table whose varlena values all stayed inline. Four fixtures here have a 0-byte TOAST relation for that last reason. Source handles it: the approximate function guards its percentage block with `if (nblocks != 0)` ([pgstatapprox.c#percentages](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L198-L207)), the exact function guards its own with `if (stat->table_len == 0)` ([pgstattuple.c#zero-length-guard](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L115-L126)), and `vac_estimate_reltuples()` returns the scanned count when `scanned_pages >= total_pages`, which `0 >= 0` satisfies ([vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1071-L1112)). The statement adds `nullif(physical_bytes, 0)` so its own divisions cannot raise `division_by_zero`, then `coalesce(..., 0.00)` so a 0-byte relation reports `0.00`, not NULL. Measured on `bl.f_empty`: both rows all zeros, no error, no NULL.

**Unsupported targets return no rows rather than an error.** The `relkind IN ('r','m')` and `relam = heap` filters in `target` mean a view, a partitioned parent, a missing name, or an index yields an empty result instead of aborting. Measured: a view and a partitioned parent both have `relam = 0` in v12 and are excluded by either filter; a leaf partition has `relkind = 'r'` and `relam = 2` and is measured normally. Without the filters the same targets produce `ERROR: "v_x" is not a table or materialized view`.

### Test setup

- 12.2 built out of tree from `raw/postgres-12/` at the pinned commit `45b88269a353ad93744772791feb6d01bc7e1e42` (tag `REL_12_2`) via `git archive`, configured `--without-readline --without-zlib --without-icu --enable-debug`, `contrib/pgstattuple` installed. `raw/` was not touched: `git status --porcelain` was empty before and after.
- `postgres (PostgreSQL) 12.2`, `block_size` 8192, `pgstattuple` extension version 1.5 ([pgstattuple.control:3](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.control#L1-L5)).
- One cluster, `shared_buffers = 256MB`, `maintenance_work_mem = 256MB`, `autovacuum = off`, `fsync = off`, `track_io_timing = on`. Autovacuum off so that every VACUUM in the results is one the test issued.
- Ten fixtures in schema `bl`. Payloads are built by a deterministic immutable function, `string_agg(md5(seed || i), '')` over `generate_series`. Concatenated md5 hex has too few repeated substrings for pglz to reach the default strategy's required 25% compression rate, so the toaster stores the values out of line uncompressed ([pg_lzcompress.c#strategy_default_data](../../../../raw/postgres-12/src/common/pg_lzcompress.c#L223-L236), [pg_lzcompress.c#need_rate](../../../../raw/postgres-12/src/common/pg_lzcompress.c#L563-L580)); the measured chunk lengths below confirm it:

```sql
create function mkpayload(seed int, nchunks int) returns text language sql immutable as
$$ select string_agg(md5(seed::text || i::text), '') from generate_series(1, nchunks) i $$;
```

| fixture | shape | bloating step |
|---|---|---|
| `f_both` | 5,000 rows, 6,400-byte payload | `delete where id % 2 = 0`, then `VACUUM` |
| `f_dead` | same | `delete where id % 2 = 0`, no VACUUM |
| `f_toastonly` | 1,000 rows, 6,400-byte payload | payload rewritten three times, then `VACUUM` |
| `f_fresh` | 1,000 rows, 6,400-byte payload | none |
| `f_exact` | 2,000 rows, 3,992-byte payload | none |
| `f_notoast` | 100,000 rows, `int` + two `bigint` | `delete where id % 2 = 0`, then `VACUUM` |
| `f_ff70` | 200,000 rows, `fillfactor = 70` | none |
| `f_ff70b` | 200,000 rows, `fillfactor = 70` | `delete where id % 2 = 0`, then `VACUUM` |
| `f_ff100` | 200,000 rows, `fillfactor = 100` set explicitly | `VACUUM` |
| `f_empty` | created, never inserted | none |

Deletes take every second `id` on purpose, so live rows remain on the last page and plain `VACUUM` cannot truncate; that isolates interior free space, which is what the metric is about. Every fixture was built at least twice from these scripts, and every byte count reported below was identical across builds; the SQL in [The statement](#the-statement) was extracted mechanically from this page's own Markdown and re-run to produce the output in [Measured output](#measured-output).

### Measured output

`f_both` and `f_dead` hold byte-identical data and differ only in whether `VACUUM` ran. The same free space appears as `dead` in one and as `free` in the other, and the requested bloat estimate is the same 59.52% on both TOAST rows:

```text
    part    |        relation         | physical_size | live_tuples | live_size | dead_tuples | dead_size | dead_pct | free_size  | free_pct | fillfactor | reserved_pct | reserved_size | est_bloat_size | est_bloat_pct | scanned_pct
------------+-------------------------+---------------+-------------+-----------+-------------+-----------+----------+------------+----------+------------+--------------+---------------+----------------+---------------+-------------
 main heap  | bl.f_both               | 296 kB        |        2500 | 157 kB    |           0 | 0 bytes   |     0.00 | 139 kB     |    46.82 |        100 |            0 | 0 bytes       | 139 kB         |         46.82 |           0
 toast heap | pg_toast.pg_toast_61755 | 39 MB         |       10000 | 16 MB     |           0 | 0 bytes   |     0.00 | 23 MB      |    59.52 |        100 |            0 | 0 bytes       | 23 MB          |         59.52 |         100
 main heap  | bl.f_dead               | 296 kB        |        2500 | 131 kB    |        2500 | 131 kB    |    44.36 | 2068 bytes |     0.68 |        100 |            0 | 0 bytes       | 133 kB         |         45.04 |         100
 toast heap | pg_toast.pg_toast_66763 | 39 MB         |       10000 | 16 MB     |       10000 | 16 MB     |    39.94 | 7832 kB    |    19.58 |        100 |            0 | 0 bytes       | 23 MB          |         59.52 |         100
```

The `f_dead` TOAST row is the interesting one: **10,000 dead chunks appear before any VACUUM runs**, because `heap_delete()` deletes the row's out-of-line data in the same transaction through `toast_delete()` ([heapam.c#toast_delete-call](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L2799-L2812), [tuptoaster.c#toast_delete](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L462-L468)), which issues `simple_heap_delete()` per chunk ([tuptoaster.c#toast_delete_datum](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L1719-L1773)). So `dead_size` on the TOAST row tracks the parent table's DELETEs and updates of TOAST-ed columns directly.

`f_both`'s heap row shows `scanned_pct` 0 with 37 pages, all all-visible after the VACUUM; `f_dead`'s shows 100, because deleting rows cleared every visibility-map bit. Same table, same size, two different measurement paths - which is why `dead_pct` is trustworthy on both but `live_size` differs by 26 kB between them.

The raw numbers behind all ten fixtures, in bytes:

| fixture | part | `table_len` | `dead_len` | `free_len` | ff | `reserved` | `est_bloat_pct` |
|---|---|---|---|---|---|---|---|
| `f_both` | main heap | 303,104 | 0 | 141,920 | 100 | 0 | 46.82 |
| `f_both` | toast heap | 40,960,000 | 0 | 24,380,000 | 100 | 0 | 59.52 |
| `f_dead` | main heap | 303,104 | 134,448 | 2,068 | 100 | 0 | 45.04 |
| `f_dead` | toast heap | 40,960,000 | 16,360,000 | 8,020,000 | 100 | 0 | 59.52 |
| `f_toastonly` | main heap | 204,800 | 0 | 139,776 | 100 | 0 | 68.25 |
| `f_toastonly` | toast heap | 32,768,000 | 0 | 26,048,000 | 100 | 0 | 79.49 |
| `f_fresh` | main heap | 57,344 | 0 | 5,148 | 100 | 0 | 8.98 |
| `f_fresh` | toast heap | 8,192,000 | 0 | 1,604,000 | 100 | 0 | 19.58 |
| `f_exact` | main heap | 106,496 | 0 | 2,132 | 100 | 0 | 2.00 |
| `f_exact` | toast heap | 8,192,000 | 0 | 20,000 | 100 | 0 | 0.24 |
| `f_notoast` | main heap | 5,218,304 | 0 | 2,395,360 | 100 | 0 | 45.90 |
| `f_ff70` | main heap | 40,960,000 | 0 | 12,820,000 | 70 | 12,285,000 | 1.31 |
| `f_ff70b` | main heap | 40,960,000 | 0 | 26,400,000 | 70 | 12,285,000 | 34.46 |
| `f_ff100` | main heap | 28,254,208 | 0 | 116,256 | 100 | 0 | 0.41 |
| `f_empty` | both rows | 0 | 0 | 0 | 100 | 0 | 0.00 |

`f_ff70`'s reserve is the arithmetic worth checking by hand: 5,000 pages times `8192 * 30 / 100` = 5,000 times 2,457 = 12,285,000 bytes, which is 29.99% of the relation rather than 30%, entirely because of the integer division in `RelationGetTargetPageFreeSpace()`.

### Scored against VACUUM FULL

`VACUUM FULL` was then run on all ten fixtures and the physical sizes re-read. `truth_pct` is `100 * (pre - post) / pre` for that one relation; the TOAST rows use the parent's new `reltoastrelid`, since the rewrite creates a new TOAST relation.

| fixture | part | `est_bloat_pct` | `truth_pct` | error |
|---|---|---|---|---|
| `f_both` | main heap | 46.82 | 48.65 | −1.83 |
| `f_both` | toast heap | 59.52 | 50.00 | +9.52 |
| `f_dead` | main heap | 45.04 | 48.65 | −3.61 |
| `f_dead` | toast heap | 59.52 | 50.00 | +9.52 |
| `f_toastonly` | main heap | 68.25 | 72.00 | −3.75 |
| `f_toastonly` | toast heap | 79.49 | 75.00 | +4.49 |
| `f_fresh` | main heap | 8.98 | 0.00 | +8.98 |
| `f_fresh` | toast heap | 19.58 | 0.00 | **+19.58** |
| `f_exact` | main heap | 2.00 | 0.00 | +2.00 |
| `f_exact` | toast heap | 0.24 | 0.00 | +0.24 |
| `f_notoast` | main heap | 45.90 | 49.92 | −4.02 |
| `f_ff70` | main heap | 1.31 | 0.00 | +1.31 |
| `f_ff70b` | main heap | 34.46 | 50.00 | **−15.54** |
| `f_ff100` | main heap | 0.41 | 0.00 | +0.41 |
| `f_empty` | both rows | 0.00 | 0.00 | 0.00 |

Read this table as three separate error sources, not one accuracy number:

1. **Heap rows with real bloat come in 1.8 to 4.0 points low.** The missing bytes are page headers and retained line pointers that the estimate counts as occupied but a rewrite discards ([pgstatapprox.c:97](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L97), [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L216)); see [Which numbers are exact and which are approximate](#which-numbers-are-exact-and-which-are-approximate).
2. **Small relations come in high, because of the partially-filled last page.** `f_fresh` has zero bloat and reads 8.98%: its heap is 7 pages, and almost all of the 5,148 free bytes are in page 7. Do not run a threshold against a relation of a few dozen pages; the last page alone is worth `100/nblocks` percent.
3. **TOAST rows come in 0.2 to 9.5 points high**, for a reason that is specific to TOAST and is the subject of the next section but one.

### The one formula error worth knowing

`f_ff70b` is the only fixture where the requested formula is badly wrong, and the reason is arithmetic rather than measurement. The formula subtracts a reserve computed on the **current** size:

```text
asked  = dead + max(free - table_len * (100 - ff)/100, 0)
```

A rewrite, however, reserves `100 - ff` of the **post-rewrite** size, because `raw_heap_insert()` reads the reserve from the new heap as it fills it. Charging the reserve against 5,000 bloated pages instead of the 2,500 pages that survive over-charges it by a factor of two. The ratio form charges it correctly:

```text
ratio  = table_len - (table_len - free - dead) * 100 / ff
```

Both forms were computed on all 14 measured rows that have a non-zero physical size. They are **algebraically identical at `fillfactor = 100`** - at `ff = 100` the reserve is zero and the ratio collapses to `free + dead` - and the two columns agreed to the digit on all 12 of those rows at `fillfactor = 100`. The only rows where they differ:

| fixture | ff | `truth_pct` | asked | error | ratio | error |
|---|---|---|---|---|---|---|
| `f_ff70` | 70 | 0.00 | 1.31 | +1.31 | 1.86 | +1.86 |
| `f_ff70b` | 70 | 50.00 | 34.46 | **−15.54** | 49.22 | **−0.78** |

So: keep the requested column, because at `fillfactor = 100` it is exactly the same number and it is easier to explain to whoever reads the report. On a table with a non-default `fillfactor` and real bloat, treat it as a floor and compute the ratio form before sizing a maintenance window. Neither form is clamped-optimistic in the other direction: both stay positive here, and both would report a negative value on a table whose `fillfactor` was lowered after loading, which is a real outcome - a rewrite makes such a table *bigger*.

### TOAST free space is mostly chunk geometry

The largest single error in the score table is `f_fresh`'s TOAST row: **19.58% free on a relation that has never had a row deleted**, and `VACUUM FULL` reclaimed exactly 0 bytes. That number is fully predictable from source constants.

`TOAST_MAX_CHUNK_SIZE` is derived so that `EXTERN_TUPLES_PER_PAGE` = 4 maximum-size chunk rows fit on one page ([tuptoaster.h#TOAST_MAX_CHUNK_SIZE](../../../../raw/postgres-12/src/include/access/tuptoaster.h#L77-L96)), which at `BLCKSZ = 8192` works out to 1,996 data bytes per chunk. Measured directly from the two TOAST relations:

| fixture | payload | chunk lengths, by `chunk_seq` |
|---|---|---|
| `f_fresh` | 6,400 bytes | 1,996 / 1,996 / 1,996 / 412 |
| `f_exact` | 3,992 bytes | 1,996 / 1,996 |

A full chunk row is `MAXALIGN(SizeofHeapTupleHeader)` 24 ([htup_details.h:184](../../../../raw/postgres-12/src/include/access/htup_details.h#L184)) + `chunk_id` 4 + `chunk_seq` 4 + varlena header 4 + 1,996 = 2,032 bytes; the 412-byte tail chunk is 448. Per page, with 4 line pointers:

| fixture | occupied | `pd_lower` | `PageGetHeapFreeSpace` | measured free per page |
|---|---|---|---|---|
| `f_fresh` | 3 x 2,032 + 448 = 6,544 | 40 | 8,192 − 6,584 − 4 = **1,604** | 1,604,000 / 1,000 pages = **1,604** |
| `f_exact` | 4 x 2,032 = 8,128 | 40 | 8,192 − 8,168 − 4 = **20** | 20,000 / 1,000 pages = **20** |

The extra 4 bytes are the space `PageGetFreeSpace()` withholds for one more line pointer ([bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L580-L597), [bufpage.c#PageGetHeapFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L664-L715)). `f_fresh`'s live length reconciles to the byte as well: 3,000 full chunks x 2,032 + 1,000 tail chunks x 448 = 6,544,000, which is exactly what `pgstattuple` reported.

Why the tail is not reused: each value's chunks are inserted in sequence, so after a value's last chunk the insertion page holds 1,604 free bytes, and the next value's first chunk needs 2,032. It does not fit, the free space map has no page with 2,032 free either, and the relation is extended. Only a value whose own tail chunk is small enough could ever land there. The result is one page per 6,400-byte value, permanently 19.58% free.

Two rules follow, and they are the difference between a useful TOAST alert and a noisy one:

- **Baseline the TOAST relation against its own geometry, not against zero.** The intrinsic free fraction is roughly `(2032 - (value_size mod 1996 + 36)) / 8192` per value-boundary page. Between the two fixtures here it ranges from 0.24% to 19.58% with no bloat at all.
- **`dead_size` on the TOAST row has no such confound.** It is exact, it is written by the parent's own DELETEs and column updates, and on `f_dead` it read 39.94% against a 50.00% rewrite truth - the closest single signal in the whole test.

### Cost of the two passes

`EXPLAIN (ANALYZE, BUFFERS)` on the statement's own CTE structure, `f_both`, after a server restart:

| branch | relation | pages | buffers | I/O time |
|---|---|---|---|---|
| `pgstattuple_approx` on the main heap | 296 kB, all 37 pages all-visible | 37 | 40 hit + 5 read | 0.029 ms |
| `pgstattuple` on the TOAST relation | 39 MB | 5,000 | 5,006 hit + 5,000 read | 17.984 ms |

Total execution 21.1 ms, planning 1.5 ms. Two readings:

- **The heap branch reads no heap pages at all** when every page is all-visible. Its 45 buffer accesses are the visibility-map page plus one free-space-map lookup per block, which is what the skip path does ([pgstatapprox.c#vm-skip](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L90-L100)).
- **The TOAST branch touches every page exactly twice**, 5,000 physical reads plus 5,006 hits on a 5,000-page relation. That is by design: the free-space loop re-reads each block that the sequential scan just brought in, so the second touch is a buffer hit rather than a second physical read ([pgstattuple.c#free-space-loop](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L365-L383)).

Head-to-head on one relation, the 27 MB / 3,449-page all-visible `f_ff100` heap:

| function | buffers | execution |
|---|---|---|
| `pgstattuple_approx` | 3,452 hit + 5 read | 0.404 ms |
| `pgstattuple` | 3,449 hit + 3,449 read | 20.706 ms |
| `pgstattuple_approx`, repeat | 3,450 hit + 0 read | 0.225 ms |

51x the time and 690x the physical reads for the same relation. That is the whole argument for the hybrid: use the approximate function wherever it is allowed, and pay the exact function's price only where v12 leaves no choice. Both functions use a `BAS_BULKREAD` strategy ring, so neither evicts the buffer cache ([pgstatapprox.c:75](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L75)), and neither sleeps - there is no cost-delay control for either, since neither is VACUUM.

Both functions hold `AccessShareLock` for their whole run and keep an ordinary snapshot, so a long TOAST pass holds back the xmin horizon exactly as any long query does. On a multi-hundred-GB TOAST relation, that is the reason to screen candidates on `pg_relation_size(reltoastrelid)` before running the statement, not after.

### Interpretation guide

Read the two rows independently; they fail in different directions.

| Reading | What it means | What to do |
|---|---|---|
| High `dead_pct`, low `free_pct` | dead row versions that no `VACUUM` has processed yet, or that a still-open snapshot pins | run `VACUUM`; if `dead_pct` does not fall, look for a long-running transaction or an old replication slot before considering a rewrite |
| Low `dead_pct`, high `free_pct`, `reserved_pct` = 0 | reusable space a past `VACUUM` freed; new rows will consume it | do nothing if the table's row count is stable or growing - the space is a working set, not waste. Rewrite only if the table has permanently shrunk |
| `free_pct` at or just above `reserved_pct` on a `fillfactor < 100` table | the headroom the reloption asked for | nothing. `est_bloat_pct` has already subtracted it; `f_ff70` reads 31.30% free and 1.31% bloat |
| `est_bloat_pct` high on a `fillfactor < 100` table | real bloat, but understated | compute the ratio form from [The one formula error worth knowing](#the-one-formula-error-worth-knowing) before sizing the window |
| TOAST `est_bloat_pct` high, heap fine | out-of-line values deleted or rewritten; the heap only ever held 18-byte pointers ([storage.sgml#toast-pointer](../../../../raw/postgres-12/doc/src/sgml/storage.sgml#L424-L431)) | this is the case that motivates the second row. `f_toastonly`: 200 kB heap, 31 MB TOAST relation, 75.00% of it reclaimable |
| TOAST `free_pct` between 0 and ~20 with `dead_pct` 0 | almost certainly chunk-tail geometry, not bloat | baseline it; see [TOAST free space is mostly chunk geometry](#toast-free-space-is-mostly-chunk-geometry) |
| `scanned_pct` 0 with a large `physical_size` | nearly every page was skipped, so `live_*` is an extrapolation from `pg_class.reltuples` | trust `dead_*` and `free_*`, distrust `live_tuples`; compare `relallvisible` against `relpages` for a finer skip ratio |
| `scanned_pct` 100 on a table you expected to be quiet | the visibility map is empty, e.g. after a `VACUUM (INDEX_CLEANUP FALSE)` or a bulk change | the numbers are better than usual here; the reading is exact page-by-page |
| Both rows small and `est_bloat_pct` high | last-page effect on a tiny relation | ignore relations below a few hundred pages |
| Zero rows returned | the target is not an ordinary table or matview on the heap AM, or does not exist | check `relkind`; partitioned parents must be measured per leaf partition |

A partitioned table needs one run per leaf partition: storage parameters are not supported on a partitioned parent, and the parent has no storage of its own.

### What ordinary VACUUM does and does not shrink

Plain `VACUUM` marks dead space reusable and returns it to the operating system only in one narrow case: "it will not return the space to the operating system, except in the special case where one or more pages at the end of a table become entirely free and an exclusive table lock can be easily obtained" ([maintenance.sgml#vacuum-space](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L167-L178)). In code, the attempt is gated on the trailing free pages clearing `REL_TRUNCATE_MINIMUM` = 1000 or one sixteenth of the relation ([vacuumlazy.c#REL_TRUNCATE](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L64-L72), [vacuumlazy.c#should_attempt_truncation](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1851-L1866)), and the truncation itself takes `AccessExclusiveLock` ([vacuumlazy.c#lazy_truncate_heap](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1870-L1875)).

Measured on one fixture, 2,000 rows with 6,400-byte payloads, in three steps:

| step | heap | TOAST relation |
|---|---|---|
| after load | 106,496 | 16,384,000 |
| delete the *trailing* half by `id`, then `VACUUM` | 57,344 | 8,192,000 |
| delete every second *remaining* row, then `VACUUM` | 57,344 | 8,192,000 |
| `VACUUM FULL` | 32,768 | 4,096,000 |

The middle two rows are the warning in one table. Both deletes removed the same number of rows. The one that emptied pages at the *end* of both relations let `VACUUM` truncate them - including the TOAST relation, which `VACUUM` processes through the same code path as the parent ([vacuum.c#vacuum-toast](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1855-L1857)). The one that freed *interior* space changed nothing physical: the TOAST relation stayed at 8,192,000 bytes and reported 59.52% free with 0% dead. `VACUUM FULL` then halved both relations.

So a high `free_pct` with `dead_pct` 0 does not mean `VACUUM` failed. It usually means `VACUUM` succeeded and the space is now inside the relation, waiting for new rows. Only a rewrite - `VACUUM FULL` or `CLUSTER`, both `AccessExclusiveLock`, both needing room for a second copy - gives the bytes back to the filesystem.

### Privileges

Version 1.5 of the extension revokes `EXECUTE` from `PUBLIC` on both functions and grants it to the `pg_stat_scan_tables` role ([pgstattuple--1.4--1.5.sql#pgstattuple-grants](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L74-L75), [pgstattuple--1.4--1.5.sql#approx-grants](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L118-L119), [pg_authid.dat#pg_stat_scan_tables](../../../../raw/postgres-12/src/include/catalog/pg_authid.dat#L39)), which is the documented policy ([pgstattuple.sgml#privileges](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L15-L24)). The pre-1.5 C entry points keep a `superuser()` check for installations whose SQL was not updated ([pgstatapprox.c#superuser-gate](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L216-L234)).

Measured `proacl` on this fresh install was `{postgres=X/postgres,pg_stat_scan_tables=X/postgres}` for `pgstattuple(text)`, `pgstattuple(regclass)` and `pgstattuple_approx(regclass)`. A plain login role and then the same role after `GRANT pg_stat_scan_tables`:

| role state | the statement | `SELECT count(*)` on the table |
|---|---|---|
| plain login role, `USAGE` on the schema | `ERROR: permission denied for function pgstattuple_approx` | `ERROR: permission denied for table f_both` |
| after `GRANT pg_stat_scan_tables` | both rows returned, including the TOAST relation | `ERROR: permission denied for table f_both` |

Neither function checks table-level privileges, and the TOAST row needs no privilege on the `pg_toast` schema, because the function receives an OID and opens the relation itself. Grant that membership knowingly: it exposes sizes, row counts and dead-row counts for every table in the database, though not row contents.

### Settings and apply scope

| Setting | Role here | Context | Apply scope |
|---|---|---|---|
| `statement_timeout` | bounds the TOAST full scan | `PGC_USERSET` ([guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2386)) | session or transaction; no reload, no restart |
| `lock_timeout` | bounds waiting for `AccessShareLock` behind DDL | `PGC_USERSET` ([guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2397)) | session or transaction; no reload, no restart |
| `block_size` | read by the statement to size the reserve | `PGC_INTERNAL`, preset ([guc.c#block_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2879-L2888)) | read-only; fixed at compile time |
| `fillfactor` | the reserve itself | table storage parameter, not a GUC ([reloptions.c#fillfactor-heap](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L167-L176)) | per table, under `ShareUpdateExclusiveLock`; affects later inserts and the next rewrite |
| `autovacuum` and its thresholds | decide how much of the heap is skippable, and therefore how approximate the heap row is | not exercised here; off in the test cluster | see the VACUUM pages |

No cost-delay setting applies. Neither function is VACUUM and neither sleeps, so `vacuum_cost_delay` and `vacuum_cost_limit` have no effect on this statement.

### Query-construction hazards on this pin

Four things about the statement's shape are deliberate, and each was tested.

1. **The `<> 0` filter sits below the lateral call.** `pgstattuple(0)` raises `could not open relation with OID 0` ([relation.c#relation_open](../../../../raw/postgres-12/src/backend/access/common/relation.c#L47-L62)), which would abort the whole statement for every table with no TOAST relation. Measured, the naive shape - `FROM (SELECT ...) t CROSS JOIN LATERAL pgstattuple(t.toast_oid) s WHERE t.toast_oid <> 0` - also returns 0 rows without error on 12.2, because `t.toast_oid <> 0` is a restriction on the outer relation and the planner attaches it to that scan, leaving the nested loop with no outer row. The guarded form does not depend on that reasoning, which is why it is the published one.
2. **`AS MATERIALIZED` pins evaluation.** v12 is the release that added the CTE materialization keywords ([gram.y#opt_materialized](../../../../raw/postgres-12/src/backend/parser/gram.y#L11425-L11429), [select.sgml#MATERIALIZED](../../../../raw/postgres-12/doc/src/sgml/ref/select.sgml#L304-L325)). `target` is referenced twice, so it would not be inlined anyway; the keyword makes the intent explicit and keeps the catalog lookup from being duplicated. On a pre-12 server the keyword is a syntax error - remove it and the statement still behaves, since a multiply-referenced CTE was always materialized before v12.
3. **The reserve uses integer arithmetic on purpose.** `(bytes / block_size) * (block_size * (100 - ff) / 100)` reproduces `RelationGetTargetPageFreeSpace()` including its truncation. Writing it with `numeric` would report a reserve 0.01% larger than the one the server enforces.
4. **`greatest(..., 0)` clamps only the free-space term, not the whole estimate.** Dead space is always counted. Clamping the free term keeps a `fillfactor = 10` table with a nearly empty page tail from reporting negative bloat purely because its declared reserve exceeds its measured free space.

### Test coverage in the pinned tree

The extension's regression test creates one table, one B-tree, one GIN and one hash index, then asserts the error text for unsupported relation kinds ([pgstattuple.sql#unsupported-relations](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L66-L96)). `pgstattuple_approx` appears there four times: refused on a partitioned table, a view and a foreign table, and accepted on a leaf partition ([pgstattuple.out#approx-errors](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L158-L212)).

Two gaps that matter for this statement:

- **No test calls either function on a TOAST relation.** The `RELKIND_TOASTVALUE` branch of `pgstat_relation()` and the corresponding refusal in `pgstattuple_approx` are both untested in the pinned tree.
- **No test measures a non-empty relation.** The file says so itself: "It's difficult to come up with platform-independent test cases for the pgstattuple functions, but the results for empty tables and indexes should be that" ([pgstattuple.sql#file-header](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L10)). Every number in this page therefore rests on this build's measurements plus source reading, not on upstream expected output.

## Context Reviewed

- `contrib/pgstattuple/`: `pgstatapprox.c`, `pgstattuple.c`, `pgstattuple--1.4.sql`, `pgstattuple--1.4--1.5.sql`, `pgstattuple.control`, `sql/pgstattuple.sql`, `expected/pgstattuple.out`.
- Reloptions and fillfactor: `reloptions.c` (`intRelOpts`, `default_reloptions`, `heap_reloptions`, the unrecognized-parameter and bounds error paths), `rel.h` (`StdRdOptions`, `RelationGetFillFactor`, `RelationGetTargetPageFreeSpace`).
- Heap and TOAST write paths: `hio.c` (`RelationGetBufferForTuple`), `heapam.c` (`heap_delete` calling `toast_delete`), `tuptoaster.c` (`toast_save_datum`, `toast_delete`, `toast_delete_datum`), `tuptoaster.h` (`TOAST_TUPLE_THRESHOLD`, `TOAST_MAX_CHUNK_SIZE`).
- Page and map accounting: `bufpage.c` (`PageGetFreeSpace`, `PageGetHeapFreeSpace`), `freespace.c` (`GetRecordedFreeSpace`, `FSM_CAT_STEP`).
- VACUUM: `vacuum.c` (`vac_estimate_reltuples`, the TOAST recursion in `vacuum_rel`), `vacuumlazy.c` (`REL_TRUNCATE_MINIMUM`, `should_attempt_truncation`, `lazy_truncate_heap`).
- Catalogs and SQL surface: `pg_class.h`, `pg_authid.dat`, `pg_proc.dat` (`pg_options_to_table`, `pg_size_pretty`), `gram.y` (`opt_materialized`), `relation.c` (`relation_open`).
- GUCs: `guc.c` (`statement_timeout`, `lock_timeout`, `block_size`).
- Documentation: `pgstattuple.sgml`, `maintenance.sgml`, `storage.sgml`, `ref/create_table.sgml`, `ref/select.sgml`.
- Measurements: one isolated 12.2 server built from the pin, ten fixtures, `VACUUM FULL` as ground truth, `EXPLAIN (ANALYZE, BUFFERS)` for cost, one non-superuser role for the privilege path.

## Evidence Map

| Claim | Evidence |
|---|---|
| `pgstattuple_approx` refuses a TOAST relation | [pgstatapprox.c#relkind-check](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L280-L290); measured `ERROR: "pg_toast_16405" is not a table or materialized view` |
| `pgstattuple` accepts a TOAST relation | [pgstattuple.c#pgstat_relation](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L240-L261); measured full row on the same relation |
| Dead statistics exact, live and free approximate on the heap row | [pgstatapprox.c#statapprox_heap](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L64-L214), [pgstattuple.sgml#approx-contract](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L515-L539) |
| The reserve is `BLCKSZ * (100 - fillfactor) / 100` per page, truncating | [rel.h#RelationGetTargetPageFreeSpace](../../../../raw/postgres-12/src/include/utils/rel.h#L304-L309); measured 12,285,000 bytes over 5,000 pages at `fillfactor = 70` |
| TOAST relations always have fillfactor 100 | [reloptions.c#heap_reloptions](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L1476-L1493), [create_table.sgml#fillfactor](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L1319-L1339); measured `ERROR: unrecognized parameter "fillfactor"` and `NULL` toast reloptions |
| Passing OID 0 aborts the statement | [relation.c#relation_open](../../../../raw/postgres-12/src/backend/access/common/relation.c#L47-L62); measured `ERROR: could not open relation with OID 0` |
| Zero-length relations are safe in both functions | [pgstatapprox.c#percentages](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L198-L207), [pgstattuple.c#zero-length-guard](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L115-L126), [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1071-L1112); measured all-zero rows on `f_empty` |
| `scanned_percent` truncates | [pgstatapprox.c#percentages](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L198-L207); measured 0 for 1 scanned page of 5,000 |
| TOAST chunk size 1,996 and the resulting per-page tail | [tuptoaster.h#TOAST_MAX_CHUNK_SIZE](../../../../raw/postgres-12/src/include/access/tuptoaster.h#L77-L96), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L580-L597); measured chunk lengths 1,996/1,996/1,996/412 and 1,604 free bytes per page |
| Dead TOAST chunks appear at DELETE time | [heapam.c#toast_delete-call](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L2799-L2812), [tuptoaster.c#toast_delete_datum](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L1719-L1773); measured 10,000 dead chunks on the unvacuumed `f_dead` |
| The exact function touches every page twice | [pgstattuple.c#free-space-loop](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L365-L383); measured 5,000 reads + 5,006 hits on 5,000 pages |
| Plain VACUUM truncates only trailing empty pages | [maintenance.sgml#vacuum-space](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L167-L178), [vacuumlazy.c#should_attempt_truncation](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1851-L1866); measured 16,384,000 -> 8,192,000 on a trailing delete and no change on an interior delete |
| Privileges come from `pg_stat_scan_tables` only | [pgstattuple--1.4--1.5.sql#approx-grants](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L118-L119); measured before and after the grant |
| No upstream test covers a TOAST relation or a non-empty relation | [pgstattuple.sql#file-header](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L10), [pgstattuple.out#approx-errors](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L158-L212) |

## Open Questions

1. **Why does `pgstattuple_approx` exclude `RELKIND_TOASTVALUE`?** The stated reason is dependence on the visibility and free space maps, which TOAST relations have. No commit or comment in the pinned tree explains the exclusion, and the source history behind `pgstatapprox.c` was not reviewed for this page.
2. **The chunk-tail baseline formula is fitted to two payload sizes.** `(2032 - (value_size mod 1996 + 36)) / 8192` reproduces 19.58% and 0.24% here, but it was not tested across a sweep of value sizes, compressed values, or values that straddle several pages, and it ignores the pages where two different values' chunks share a page.
3. **The ratio form was not tested below `fillfactor = 70`.** Its −0.78-point error on `f_ff70b` is one data point at one fillfactor on one row shape.
4. **`live_tuples` on the heap row was not stress-tested here.** It re-reports `pg_class.reltuples` when every page is skipped, which makes it an `ANALYZE` sample estimate rather than a count; the statement exposes it because the question asked for it, but no fixture here forged `reltuples` to quantify the exposure.
5. **Dead is not the same as removable.** No fixture held an old snapshot open, so nothing here quantifies how much of a reported `dead_size` an actual `VACUUM` could reclaim under concurrency.
6. **The TOAST relation's index is not measured.** A TOAST relation always carries a unique B-tree on `(chunk_id, chunk_seq)`, which bloats on the same DML and is invisible to this statement.
7. **All measurements come from one 12.2 build with `fsync = off` and `autovacuum = off`, on one filesystem.** Byte counts are geometry and should reproduce anywhere with `BLCKSZ = 8192`; the timings should not be read as production numbers.
8. **The test sandbox under `.wiki-runtime/tmp/pta12/` is retained as of this filing.** If it is deleted, the fixture SQL published in [Test setup](#test-setup) is enough to rebuild it, but the exact OIDs in the sample output will differ.

## Source References

- [pgstatapprox.c](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L1-L315) - the approximate estimator, its relkind and relam gates, and its percentage arithmetic.
- [pgstattuple.c](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L1-L590) - the exact function, its accepted relation kinds including `RELKIND_TOASTVALUE`, and its two-touch page loop.
- [pgstattuple--1.4.sql](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L49-L95) - the SQL signatures and output column names of both functions.
- [pgstattuple--1.4--1.5.sql](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L61-L119) - the 1.5 `REVOKE`/`GRANT` policy.
- [pgstattuple.sgml](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L1-L629) - the documented privilege model, column tables, and the exact-versus-approximate contract.
- [reloptions.c](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L167-L1504) - the heap `fillfactor` entry, the generic error paths, and the forced 100 for TOAST relations.
- [rel.h](../../../../raw/postgres-12/src/include/utils/rel.h#L264-L309) - `StdRdOptions`, the fillfactor default and minimum, and the reserve macros.
- [tuptoaster.h](../../../../raw/postgres-12/src/include/access/tuptoaster.h#L28-L96) - the toasting thresholds and `TOAST_MAX_CHUNK_SIZE`.
- [tuptoaster.c](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L1459-L1773) - chunk splitting through `heap_insert`, and chunk deletion.
- [bufpage.c](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L580-L715) - the two free-space functions and the withheld line pointer.
- [freespace.c](../../../../raw/postgres-12/src/backend/storage/freespace/freespace.c#L63-L247) - free-space-map categories and the 32-byte step.
- [vacuum.c](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1071-L1857) - `vac_estimate_reltuples` and the TOAST recursion.
- [vacuumlazy.c](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L64-L1875) - the truncation thresholds and the truncation attempt.
- [maintenance.sgml](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L167-L178) - what plain `VACUUM` returns to the operating system.
- [storage.sgml](../../../../raw/postgres-12/doc/src/sgml/storage.sgml#L402-L431) - `reltoastrelid`, chunking, and the 18-byte pointer datum.
- [ref/create_table.sgml](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L1319-L1339) - the `fillfactor` storage parameter and its TOAST exclusion.
- [guc.c](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2888) - `statement_timeout`, `lock_timeout`, `block_size`.
- [sql/pgstattuple.sql](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L119) and [expected/pgstattuple.out](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L1-L248) - the upstream test and its explicit limits.

## Navigation

- [v12/index](../../index.md)
- [PostgreSQL 12 Codebase Navigation Guide](../../codebase-navigation-guide.md)
- [How Much I/O a VACUUM FULL Performs on a Multi-GB, Near-Empty Heap in PostgreSQL 12](vacuum-full-io-on-near-empty-heap.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
