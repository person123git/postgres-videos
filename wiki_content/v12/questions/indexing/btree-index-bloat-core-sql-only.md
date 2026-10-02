---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# Measuring B-Tree Index Bloat With Core SQL Only in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [The proposal in one paragraph](#the-proposal-in-one-paragraph)
  - [What core SQL can and cannot see](#what-core-sql-can-and-cannot-see)
  - [What bloat is in a v12 B-tree](#what-bloat-is-in-a-v12-b-tree)
  - [The page-fill model, derived from source](#the-page-fill-model-derived-from-source)
  - [Method A: catalog-only bloat sweep](#method-a-catalog-only-bloat-sweep)
  - [Method A-prime: fix the key width with pg_column_size](#method-a-prime-fix-the-key-width-with-pg_column_size)
  - [Method B: index-only-scan page census](#method-b-index-only-scan-page-census)
  - [Method C: CREATE INDEX CONCURRENTLY rebuild probe](#method-c-create-index-concurrently-rebuild-probe)
  - [Method D: VACUUM VERBOSE page classes](#method-d-vacuum-verbose-page-classes)
  - [Two free triage signals](#two-free-triage-signals)
  - [Which method to use](#which-method-to-use)
  - [Exact-pin measurements](#exact-pin-measurements)
  - [Measured failure modes](#measured-failure-modes)
  - [Settings and apply scopes](#settings-and-apply-scopes)
  - [What no core-SQL method can measure](#what-no-core-sql-method-can-measure)
  - [Follow-up: the comparison fixture matrix](#follow-up-the-comparison-fixture-matrix)
  - [Follow-up: which pgstatindex columns core SQL reproduces](#follow-up-which-pgstatindex-columns-core-sql-reproduces)
  - [Follow-up: error by bloat type, partial and non-partial](#follow-up-error-by-bloat-type-partial-and-non-partial)
  - [Follow-up: an avg_leaf_density predictor head to head](#follow-up-an-avg_leaf_density-predictor-head-to-head)
  - [Follow-up: the partial-index failure and its fix](#follow-up-the-partial-index-failure-and-its-fix)
  - [Follow-up: the output columns say wasted_space, not bloat](#follow-up-the-output-columns-say-wasted_space-not-bloat)
  - [What the rename cannot change](#what-the-rename-cannot-change)
  - [What a consumer must change](#what-a-consumer-must-change)
  - [Follow-up: source support for the v12 and v17 open-question review](#follow-up-source-support-for-the-v12-and-v17-open-question-review)
  - [The v12 build and statistics boundaries](#the-v12-build-and-statistics-boundaries)
  - [The v12 publication protocol](#the-v12-publication-protocol)
  - [V12 catalog, build and output compatibility](#v12-catalog-build-and-output-compatibility)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Propose a SQL-only method, using no contrib extensions, to measure B-tree index bloat in PostgreSQL 12.

Follow-up:

Add sections comparing the SQL bloat results to pgstatindex results, and measure what the error is with different types of index bloat and with partial and non-partial indexes.

Follow-up:

Add a correction. In the SQL, do not use bloat as the output; use wasted_space.

> Prompt note: filed as an approved grammar-corrected restatement of "add
> correction: on the sql don't use bloat as the output but use wasted_space", per
> the repository's prompt-hygiene rule. The asker scoped "the output" to the
> statements' own identifiers and confirmed that both Method A reporting columns
> are renamed (`wasted` -> `wasted_space`, `bloat_pct` -> `wasted_space_pct`),
> that the Method A statement tag and the Method C probe index name are renamed
> too, and that this page's prose and its two accuracy-table percentage headers
> follow the new names. The page title and the conceptual use of "bloat" stay as
> filed.

Follow-up (2026-09-07):

analyze and propose a solution for open questions, ignore open questions not about version 12 and version 17.

> Scope: continue the review of the PostgreSQL 17 question, retaining
> the request as written and covering only PostgreSQL 12 and 17.

## Answer

### The proposal in one paragraph

Compute the size the index *would* have if it were rebuilt right now, and subtract it from the size it has. Core SQL gives you the current size exactly, from the filesystem, through [dbsize.c#calculate_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L266-L308). It does not give you the rebuilt size. Catalog data supports an approximation of v12's deterministic build, whose exact result also depends on the actual tuple widths and page separators ([indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L121-L133), [nbtutils.c#_bt_truncate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L2116-L2164)): `nbtsort.c` checks hard fit and a soft free-space threshold of `BLCKSZ * (100 - fillfactor) / 100`, applying that soft threshold only after the minimum item count ([nbtsort.c#_bt_pagestate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L724-L729), [nbtsort.c#_bt_buildadd](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L856-L899)). On an exact-pin 12.2 server, that computed size matched an actual `CREATE INDEX CONCURRENTLY` rebuild **to the block on 10 of 14 fixtures** and to within 2 blocks on 3 more. Three progressively more expensive core-only methods refine or verify it: a `pg_column_size` key-width measurement, an index-only-scan buffer census that reproduces `pgstatindex`'s `avg_leaf_density` to within 0.14 points with no contrib installed, and a sibling-index rebuild that is exact by construction.

### What core SQL can and cannot see

Core v12 has **no** SQL-callable function that reads an index page, the free space map, or per-page fill. `pgstatindex`, `pgstattuple`, `get_raw_page`, `bt_metap`, `bt_page_stats`, `pg_freespace`, and `bt_index_check` all live under `contrib/`, and `pg_proc.dat` contains no equivalent. Installing them is not merely a `CREATE EXTENSION` away either: none of the four relevant control files sets `superuser = false`, and the parser defaults that field to `true` ([extension.c#read_extension_control_file](../../../../raw/postgres-12/src/backend/commands/extension.c#L605-L625)), so a non-superuser gets `permission denied to create extension` ([extension.c#execute_extension_script](../../../../raw/postgres-12/src/backend/commands/extension.c#L798-L817)). `pageinspect` additionally hard-checks `superuser()` in C at every entry point ([rawpage.c#get_raw_page](../../../../raw/postgres-12/contrib/pageinspect/rawpage.c#L103-L106), [pageinspect.sgml](../../../../raw/postgres-12/doc/src/sgml/pageinspect.sgml#L10-L14)).

What core does expose:

| Surface | What it gives | Live or estimated |
|---|---|---|
| `pg_relation_size(idx)` | main-fork bytes, summed by `stat(2)` over segment files ([dbsize.c#calculate_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L266-L308)) | live, exact |
| `pg_relation_size(idx, 'fsm')` | FSM fork bytes; fork names are `main`/`fsm`/`vm`/`init` ([relpath.c#forkNames](../../../../raw/postgres-12/src/common/relpath.c#L26-L38)) | live, exact |
| `pg_class.relpages` / `reltuples` | block and tuple counts as of the last VACUUM/ANALYZE/build ([pg_class.h#relpages](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L59-L63)) | stale by design |
| `pg_class.reloptions` | the index's `fillfactor`, via `pg_options_to_table` ([pg_proc.dat#pg_options_to_table](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L3603-L3608)) | exact |
| `pg_stats.avg_width` / `null_frac` | sampled stored key width and null fraction ([system_views.sql#pg_stats](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L194-L197)) | estimated |
| `pg_stat_all_tables.n_live_tup` / `n_dead_tup` | collector row counts ([system_views.sql#pg_stat_all_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L566-L572)) | estimated |
| `pg_column_size(col)` | the stored size of an individual datum ([varlena.c#pg_column_size](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L5044-L5090)) | exact per row |
| `EXPLAIN (ANALYZE, BUFFERS)` | blocks touched per plan node ([explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2907)) | live, exact |
| `VACUUM VERBOSE` | index page count, deleted pages, reusable pages ([vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1817-L1827)) | live, exact |

`pg_stat_all_indexes` has no size, page-count or tuple-count column at all — only `idx_scan`, `idx_tup_read`, `idx_tup_fetch` ([system_views.sql#pg_stat_all_indexes](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L658-L672)). And `TABLESAMPLE` cannot sample an index: the parser rejects anything that is not a table, matview, or partitioned table ([parse_clause.c#transformRangeTableSample](../../../../raw/postgres-12/src/backend/parser/parse_clause.c#L1162-L1169)).

### What bloat is in a v12 B-tree

Two distinct things, and core SQL sees them differently.

1. **Underfilled live leaf pages.** The documentation states the mechanism directly: "if all but a few index keys on a page have been deleted, the page remains allocated" ([maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L866-L874)).
2. **Deleted pages still inside the file.** VACUUM unlinks an entirely-empty page and records it in the FSM ([nbtree.c#btvacuumpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1166-L1188)), but the nbtree README is explicit that this "doesn't actually change its state on disk" — the page is handed back out at the next split ([README#page-deletion](../../../../raw/postgres-12/src/backend/access/nbtree/README#L327-L334)). `src/backend/access/nbtree/` contains no call to `RelationTruncate` or `smgrtruncate` and never sets `pages_removed` ([genam.h#IndexBulkDeleteResult](../../../../raw/postgres-12/src/include/access/genam.h#L62-L81)), so the file never shrinks without a rebuild.

Both show up as "the file is bigger than the data needs", which is exactly what the model below measures. A leaf-density metric alone sees only the first; the `idx_range` fixture below has a perfectly healthy 89.83% leaf density while 2330 of its 2745 blocks are deleted pages.

### The page-fill model, derived from source

A B-tree page reserves a 24-byte header and 16 bytes of special space, leaving 8152 usable bytes for line pointers plus tuple bodies. That is nbtree's own arithmetic ([nbtsplitloc.c#leftspace](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L155-L158)), built from [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L213-L216) and [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L55-L68).

One index entry occupies `MAXALIGN(hoff + data) + 4`:

- `hoff` is 8, or 16 when that tuple has any NULL ([itup.h#IndexInfoFindDataOffset](../../../../raw/postgres-12/src/include/access/itup.h#L76-L90));
- `data` is `heap_compute_data_size()`, which skips NULL columns entirely and charges no alignment padding to a short varlena ([heaptuple.c#heap_compute_data_size](../../../../raw/postgres-12/src/backend/access/common/heaptuple.c#L127-L164));
- the whole thing is MAXALIGN'd once more in [indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L121-L135);
- the trailing 4 is `sizeof(ItemIdData)`, the line pointer ([itemid.h#ItemIdData](../../../../raw/postgres-12/src/include/storage/itemid.h#L25-L30)).

A sorted build reserves one line pointer for the future high key up front ([nbtsort.c#_bt_blnewpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L621-L646)), then adds entries while `PageGetFreeSpace()` — which already subtracts one line pointer ([bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L580-L597)) — stays at or above `btps_full`. With `k` entries present, free space is therefore `BLCKSZ - 24 - 16 - 4 - 4 - k*slot`, i.e. `8144 - k*slot` at the default block size. Since `btps_full = BLCKSZ * (100 - fillfactor) / 100`, the number of data entries a finished leaf page keeps is:

```text
tuples_per_leaf = floor( (BLCKSZ - 48 - floor(BLCKSZ * (100 - fillfactor) / 100)) / slot )
```

For a `bigint` key at fillfactor 90 that is `floor((8192 - 48 - 819) / 20) = 366`. Internal levels use the fixed `BTREE_NONLEAF_FILLFACTOR` of 70 ([nbtree.h#BTREE_DEFAULT_FILLFACTOR](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171), [nbtsort.c#_bt_pagestate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L724-L729)), and block 0 is always the metapage ([nbtree.h#BTREE_METAPAGE](../../../../raw/postgres-12/src/include/access/nbtree.h#L131-L135)). Expected size is then `1 + ceil(rows / tuples_per_leaf)` plus the internal levels stacked at fanout `floor((BLCKSZ - 48 - floor(BLCKSZ * 30 / 100)) / slot)`.

Measured against the pinned build: predicted 2733 leaf + 11 internal + 1 meta = 2745 blocks for 1,000,000 `bigint` rows; the real index is 2745 blocks with 2733 leaf and 11 internal pages.

### Method A: catalog-only bloat sweep

One statement, no index I/O, no table access. It ran in 26.7 ms over the whole 14-index test database.

```sql
SET statement_timeout = '30s';
SET lock_timeout = '2s';

WITH RECURSIVE
idx AS (
    SELECT /* wiki_btree_wasted_space_sweep */
           c.oid AS idxoid, n.nspname AS schemaname, t.relname AS tablename,
           c.relname AS indexname, t.oid AS tbloid, x.indkey,
           coalesce((SELECT option_value::int FROM pg_options_to_table(c.reloptions)
                      WHERE option_name = 'fillfactor'), 90) AS fillfactor,
           CASE WHEN x.indpred IS NOT NULL THEN c.reltuples::numeric
                ELSE least(c.reltuples::numeric,
                           coalesce(nullif(s.n_live_tup, 0), c.reltuples)::numeric)
           END                                          AS live_rows,
           c.reltuples::numeric                         AS idx_reltuples,
           coalesce(s.n_dead_tup, 0)                    AS tbl_n_dead_tup,
           greatest(s.last_vacuum, s.last_autovacuum)   AS last_vacuum,
           greatest(s.last_analyze, s.last_autoanalyze) AS last_analyze,
           pg_relation_size(c.oid)                      AS actual_bytes,
           pg_relation_size(c.oid, 'fsm')               AS fsm_bytes,
           current_setting('block_size')::int           AS bs
      FROM pg_class c
      JOIN pg_index x     ON x.indexrelid = c.oid
      JOIN pg_class t     ON t.oid = x.indrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_am am       ON am.oid = c.relam
      LEFT JOIN pg_stat_all_tables s ON s.relid = t.oid
     WHERE am.amname = 'btree' AND c.relkind = 'i' AND x.indisvalid
       AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
),
cols AS (
    SELECT i.idxoid, a.attlen, a.attalign,
           CASE WHEN a.attlen > 0 THEN a.attlen::numeric
                ELSE coalesce(se.avg_width, st.avg_width, 32)::numeric END AS width,
           coalesce(se.null_frac, st.null_frac, 0)::numeric                AS null_frac
      FROM idx i
      JOIN pg_attribute a ON a.attrelid = i.idxoid AND a.attnum > 0 AND NOT a.attisdropped
      LEFT JOIN pg_stats se ON se.schemaname = i.schemaname
                           AND se.tablename = i.indexname AND se.attname = a.attname
      LEFT JOIN pg_attribute ta ON ta.attrelid = i.tbloid
                               AND ta.attnum = i.indkey[a.attnum - 1]
      LEFT JOIN pg_stats st ON st.schemaname = i.schemaname
                           AND st.tablename = i.tablename AND st.attname = ta.attname
),
tuple AS (
    SELECT i.*,
           (SELECT sum((1 - c.null_frac) *
                       CASE WHEN c.attlen < 0 AND c.width <= 127 THEN c.width
                            ELSE ceil(c.width / al.a) * al.a END)
              FROM cols c
              CROSS JOIN LATERAL (SELECT CASE c.attalign WHEN 'c' THEN 1 WHEN 's' THEN 2
                                              WHEN 'i' THEN 4 ELSE 8 END AS a) al
             WHERE c.idxoid = i.idxoid)                                    AS data_size,
           (SELECT 1 - coalesce(exp(sum(ln(greatest(1 - c.null_frac, 1e-9)))), 1)
              FROM cols c WHERE c.idxoid = i.idxoid)                       AS p_null
      FROM idx i
),
sized AS (
    SELECT t.*, ceil((8 + 8 * t.p_null + t.data_size) / 8) * 8 + 4         AS slot
      FROM tuple t
),
fit AS (
    SELECT s.*,
           greatest(floor((s.bs - 48 - floor(s.bs * (100 - s.fillfactor) / 100)) / s.slot), 1)
               AS leaf_cap,
           greatest(floor((s.bs - 48 - floor(s.bs * 30 / 100)) / s.slot), 2)
               AS int_cap
      FROM sized s
),
levels AS (
    SELECT idxoid, ceil(greatest(live_rows, 0) / leaf_cap) AS pages, int_cap FROM fit
    UNION ALL
    SELECT l.idxoid, ceil(l.pages / l.int_cap), l.int_cap FROM levels l WHERE l.pages > 1
),
modelled AS (
    SELECT f.*, (SELECT sum(pages) FROM levels l WHERE l.idxoid = f.idxoid) + 1
                    AS expected_blocks
      FROM fit f
)
SELECT schemaname, tablename, indexname,
       pg_size_pretty(actual_bytes) AS index_size,
       pg_size_pretty(greatest(actual_bytes - expected_blocks * bs, 0)::bigint) AS wasted_space,
       round((100 * (1 - (expected_blocks * bs) / greatest(actual_bytes, 1)))::numeric, 1)
           AS wasted_space_pct,
       fsm_bytes > 0                                  AS has_freed_pages,
       tbl_n_dead_tup                                 AS dead_tuples,
       (last_vacuum IS NULL AND last_analyze IS NULL) AS never_analyzed,
       idx_reltuples::bigint                          AS idx_reltuples,
       live_rows::bigint                              AS modelled_rows
  FROM modelled
 WHERE actual_bytes > 1024 * 1024
 ORDER BY greatest(actual_bytes - expected_blocks * bs, 0) DESC;
```

Two `AS` labels and the statement tag were corrected after this page was first filed, and none of the three changes a value: `wasted` became `wasted_space`, `bloat_pct` became `wasted_space_pct`, and `/* wiki_btree_bloat_sweep */` became `/* wiki_btree_wasted_space_sweep */`. See [Follow-up: the output columns say wasted_space, not bloat](#follow-up-the-output-columns-say-wasted_space-not-bloat).

Design notes that matter:

- **`live_rows` prefers the collector over `pg_class`.** ANALYZE derives an index's `reltuples` from the heap sample (`ceil(tupleFract * totalrows)`, [analyze.c#do_analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629)); VACUUM overwrites it with the true count ([vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1803-L1815)). Neither runs after a bare `DELETE`, so `reltuples` alone reports 0.0% bloat on an index that is 90% reclaimable; see the measured failure below. `pg_stat_all_tables.n_live_tup` tracks the delete immediately, so `least()` of the two recovers the right answer. Partial indexes keep `reltuples`, because `n_live_tup` counts the whole table.
- **`x.indisvalid` filter.** An invalid leftover from a failed concurrent build is not a rebuild candidate; it is a cleanup candidate.
- **`fillfactor` is read per index**, so a `fillfactor=50` index is not reported as 44% bloated.

### Method A-prime: fix the key width with pg_column_size

`pg_stats.avg_width` is a sample mean of the *stored* width ([pg_statistic.h#stawidth](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L39-L49), [analyze.c#compute_scalar_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L2223-L2231)). Because Method A MAXALIGNs that single average, a key whose per-row width straddles alignment boundaries is mispriced. `pg_column_size` fixes it by aligning each row separately:

```sql
SET statement_timeout = '60s';

SELECT /* wiki_btree_measure_slot */
       count(*)                                                 AS rows_measured,
       avg(ceil((8 + pg_column_size(k)) / 8.0) * 8 + 4)         AS avg_slot_bytes
  FROM t_var TABLESAMPLE BERNOULLI (1) REPEATABLE (42);
```

On the variable-width fixture this returned 56.893 bytes from a 1% sample and 57.000 from a full scan, against Method A's catalog-derived 60. Feeding either value back into the same closed form moved the estimate from −4.64% to +0.32% error. Add one `pg_column_size` term per key column, in `indkey` order, for a multi-column index; NULLs are handled by `hoff`, not by the column term.

### Method B: index-only-scan page census

This measures the live leaf chain directly, with no contrib and no writes, by counting the blocks a full index-only scan touches. Two probes in the same session:

```sql
SET statement_timeout = '5min';
SET enable_seqscan = off;
SET enable_bitmapscan = off;
SET max_parallel_workers_per_gather = 0;

-- (1) full walk of the leaf chain; run twice, use the second reading
EXPLAIN (ANALYZE, BUFFERS, TIMING off, COSTS off) SELECT /* wiki_btree_census_full */ count(*) FROM t_seq;
EXPLAIN (ANALYZE, BUFFERS, TIMING off, COSTS off) SELECT /* wiki_btree_census_full */ count(*) FROM t_seq;
-- (2) descent-only calibration: a key that matches nothing; same session, run twice
EXPLAIN (ANALYZE, BUFFERS, TIMING off, COSTS off) SELECT /* wiki_btree_census_descent */ id FROM t_seq WHERE id = -1;
EXPLAIN (ANALYZE, BUFFERS, TIMING off, COSTS off) SELECT /* wiki_btree_census_descent */ id FROM t_seq WHERE id = -1;
```

Both probes must run in the same session and the second reading of each must be used: on `idx_seq` the calibration query read 6 blocks in a cold backend and 3 once the metapage was cached in `rd_amcache` ([nbtpage.c#_bt_getrootheight](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L585-L615)).

`live_leaf_pages = full_scan_blocks - descent_blocks`. The full scan reads the metapage, one page per internal level, and every live leaf exactly once, because `_bt_readnextpage` follows one right link per `_bt_getbuf` call ([nbtsearch.c#_bt_readnextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1737-L1786)); the calibration probe reads one page per internal level plus one leaf, so the difference is the leaf count. Deleted and half-dead pages are skipped by `P_IGNORE` and are correctly absent from the total. On 12 fixtures with `Heap Fetches: 0`, this reproduced `pgstatindex`'s `leaf_pages` **exactly, every time**, and `total_blocks - leaf_est` matched `internal + deleted + half-dead + metapage` exactly as well.

Two preconditions, both enforced by reading the plan:

- **`Heap Fetches` must be 0.** An index-only scan falls back to the heap for any TID whose page is not all-visible ([nodeIndexonlyscan.c#IndexOnlyNext](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L161-L170)), and `BUFFERS` has no per-relation breakdown ([instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33)), so heap blocks silently inflate the count. The measured damage: `idx_churn` reported 8452 leaf pages against a true 3279.
- **The calibration key must match (nearly) nothing.** A probe key with 5000 duplicates read 45 blocks instead of 3 and cost 41 pages of accuracy.

Reconstructed density, which is the core-SQL equivalent of `pgstatindex.avg_leaf_density`:

```text
avg_leaf_density ≈ (rows / live_leaf_pages + 1) * slot_bytes / (BLCKSZ - 40) * 100
```

The `+1` accounts for the high key that every non-rightmost leaf carries ([nbtree.h#P_HIKEY](../../../../raw/postgres-12/src/include/access/nbtree.h#L198-L219)), and `BLCKSZ - 40` is the same denominator `pgstatindex` uses ([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L288-L308)). Measured error was −0.03 to −0.14 points on 11 of 12 fixtures.

### Method C: CREATE INDEX CONCURRENTLY rebuild probe

Exact by construction: build a sibling with the same definition, read its size, drop it.

```sql
-- Generate the DDL. pg_get_indexdef emits reloptions but omits CONCURRENTLY and the
-- tablespace, so both must be added.
SELECT /* wiki_btree_probe_ddl */
       regexp_replace(pg_get_indexdef(c.oid),
                      '^CREATE (UNIQUE )?INDEX ' || quote_ident(c.relname) || ' ON ',
                      'CREATE \1INDEX CONCURRENTLY wiki_wasted_space_probe ON ')
       || coalesce(' TABLESPACE ' || quote_ident(ts.spcname), '') AS ddl
  FROM pg_class c
  LEFT JOIN pg_tablespace ts ON ts.oid = nullif(c.reltablespace, 0)
 WHERE c.oid = 'public.idx_seq'::regclass;
```

Then, as three separate top-level statements:

```sql
SET maintenance_work_mem = '256MB';
SET lock_timeout = '5s';
CREATE INDEX CONCURRENTLY wiki_wasted_space_probe ON public.t_seq USING btree (id);
SELECT /* wiki_btree_probe_result */
       pg_size_pretty(pg_relation_size('public.idx_seq'))              AS live,
       pg_size_pretty(pg_relation_size('wiki_wasted_space_probe'))     AS fresh,
       pg_size_pretty(pg_relation_size('public.idx_seq')
                      - pg_relation_size('wiki_wasted_space_probe'))   AS reclaimable;
DROP INDEX CONCURRENTLY wiki_wasted_space_probe;
```

Constraints and costs, all from source:

- **Three separate statements.** `CREATE INDEX CONCURRENTLY` is rejected inside a transaction block, a subtransaction, or a function ([utility.c#ProcessUtilitySlow](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1301-L1310), [xact.c#PreventInTransactionBlock](../../../../raw/postgres-12/src/backend/access/transam/xact.c#L3329-L3359)). `DROP INDEX CONCURRENTLY` has the same restriction plus no-CASCADE and one-object rules ([tablecmds.c#RemoveRelations](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L1235-L1253)).
- **Lock level is `ShareUpdateExclusiveLock`** on the table, so DML keeps running ([indexcmds.c#DefineIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L548-L564)).
- **Not usable on a partitioned table** ([indexcmds.c#DefineIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L604-L622)), and silently downgraded to a non-concurrent build on temp tables ([indexcmds.c#DefineIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L489-L499)).
- **Failure leaves an invalid index** that still costs write overhead, because `indisvalid` is set non-transactionally as the last step ([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3314-L3330), [create_index.sgml#CONCURRENTLY](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L574-L596)). Always follow up with a check for a leftover `wiki_wasted_space_probe`.
- **It costs a full build**: two table scans ([create_index.sgml#CONCURRENTLY](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L545-L558)), a full-page WAL image per index page whenever `wal_level >= replica` ([nbtsort.c#_bt_blwritepage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L576-L580)), an `smgrimmedsync` of the whole fork ([nbtsort.c#_bt_load](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1288-L1307)), and double disk footprint while it runs. On the 39 MB fixture the probe took 258 ms against 26.7 ms for the whole Method A sweep.
- **The baseline is a fillfactor build, not a maximally packed index** ([nbtsort.c](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L17-L24)). That is the right baseline for "what would `REINDEX` give back", which is the question a DBA is actually asking.

### Method D: VACUUM VERBOSE page classes

`VACUUM VERBOSE` prints an exact per-index page census with no contrib at all:

```text
INFO:  index "idx_range" now contains 150000 row versions in 2745 pages
DETAIL:  50000 index row versions were removed.
2329 index pages have been deleted, 2192 are currently reusable.
```

The message text and every field come from [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1817-L1827), fed by `btvacuumscan`'s `num_pages` / `pages_free` ([nbtree.c#btvacuumscan](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1090-L1098)) and `btvacuumpage`'s `pages_deleted` ([nbtree.c#btvacuumpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1166-L1188)). The split between "deleted" and "currently reusable" is the recycle horizon in [nbtpage.c#_bt_page_recyclable](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L931-L963).

Caveat, observed on the pin: a VACUUM that finds nothing to do prints **no** index line, because `btvacuumcleanup` skips the scan entirely ([nbtree.c#btvacuumcleanup](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L913-L919)). Method D therefore reports only when VACUUM had work to do.

### Two free triage signals

- **`pg_relation_size(idx, 'fsm') > 0`** means VACUUM has recorded at least one recyclable page for that index, since the FSM fork is created by the first `RecordFreeIndexPage` ([nbtree.c#btvacuumpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1166-L1188), [indexfsm.c#RecordFreeIndexPage](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L48-L55)). Across the 14 fixtures this was non-zero for exactly the one index that had deleted pages (24576 bytes for `idx_range`, 0 for the other 13). It is a binary flag, not a quantity: its size does not scale with the number of free pages.
- **`pg_stat_all_indexes.idx_scan`** ranks candidates: an index nobody scans should be dropped, not rebuilt ([system_views.sql#pg_stat_all_indexes](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L658-L672)).

### Which method to use

| Method | Reads | Writes | Cost on a 39 MB index | Accuracy vs an actual rebuild |
|---|---|---|---|---|
| A: catalog sweep | catalogs only | none | 26.7 ms for 14 indexes | exact on 10/14, ±2 blocks on 3, −4.6% on 1 |
| A′: `pg_column_size` | one table scan or sample | none | 1% sample | fixes the one A failure to +0.32% |
| B: IOS census | the whole index | none | 65 ms | leaf-page count exact on 12/12 |
| C: CIC rebuild | table + writes a new index | yes | 258 ms + 39 MB | exact by definition |
| D: VACUUM VERBOSE | the whole index | yes | a VACUUM | exact, but only when VACUUM works |

Run A continuously; confirm the top offenders with B or C before spending a `REINDEX`.

### Exact-pin measurements

All numbers come from one isolated PostgreSQL 12.2 server built from the pinned checkout, `block_size` 8192, `autovacuum = off`. `pgstattuple` was installed **only to provide ground truth**; nothing in Methods A–D uses it.

Fixtures, with `pgstatindex` ground truth:

| index | how it was made | blocks | leaf | internal | deleted | density |
|---|---|---|---|---|---|---|
| `idx_seq` | 1,000,000 sequential `bigint`, built after load | 2745 | 2733 | 11 | 0 | 90.06 |
| `idx_uuid` | 400,000 `uuid` | 1543 | 1533 | 9 | 0 | 90.01 |
| `idx_text` | 500,000 `md5()` `text` | 3607 | 3572 | 34 | 0 | 89.98 |
| `idx_multi` | 500,000 `(int, text)` | 3606 | 3572 | 33 | 0 | 89.96 |
| `idx_var` | 400,000 `text`, 2-81 chars | 3169 | 3126 | 42 | 0 | 90.43 |
| `idx_ff50` | 1,000,000 sequential, `fillfactor=50` | 4971 | 4951 | 19 | 0 | 49.85 |
| `idx_null` | 1,000,000 `bigint`, 25% NULL | 2746 | 2733 | 12 | 0 | 90.09 |
| `idx_part` | partial index over 50,000 of 1,000,000 rows | 139 | 137 | 1 | 0 | 89.83 |
| `idx_dup` | 500,000 identical keys inserted into an existing index | 1291 | 1283 | 7 | 0 | 96.00 |
| `idx_rand` | 1,000,000 random keys inserted into an existing index | 3758 | 3745 | 12 | 0 | 65.81 |
| `idx_del` | 1,000,000 then 90% scattered `DELETE`, VACUUM | 2745 | 2733 | 11 | 0 | 9.27 |
| `idx_range` | 1,000,000 then a contiguous 85% `DELETE`, VACUUM | 2745 | 411 | 3 | 2330 | 89.83 |
| `idx_churn` | 300,000 rows updated twice, never vacuumed | 3293 | 3279 | 13 | 0 | 67.63 |
| `idx_stale` | 1,000,000 then 90% `DELETE`, no VACUUM, no ANALYZE | 2745 | 2733 | 11 | 0 | 90.06 |
| `idx_empty` | empty table | 1 | 0 | 0 | 0 | `NaN` |

`idx_empty` is a metapage-only index; the Method A sweep's `actual_bytes > 1024 * 1024` filter excludes it, and it is left out of the accuracy tables below. Its modelled size is 1 block, which is correct.

Method A against the Method C rebuild, in blocks:

| index | live | rebuilt (exact) | Method A model | model − rebuilt | model wasted_space % | true wasted_space % |
|---|---|---|---|---|---|---|
| `idx_seq` | 2745 | 2745 | 2745 | 0 | 0.0 | 0.0 |
| `idx_uuid` | 1543 | 1543 | 1543 | 0 | 0.0 | 0.0 |
| `idx_text` | 3607 | 3607 | 3607 | 0 | 0.0 | 0.0 |
| `idx_ff50` | 4971 | 4971 | 4971 | 0 | 0.0 | 0.0 |
| `idx_part` | 139 | 139 | 139 | 0 | 0.0 | 0.0 |
| `idx_multi` | 3606 | 3606 | 3607 | +1 | 0.0 | 0.0 |
| `idx_null` | 2746 | 2746 | 2745 | −1 | 0.0 | 0.0 |
| `idx_rand` | 3758 | 2745 | 2745 | 0 | 27.0 | 27.0 |
| `idx_churn` | 3293 | 825 | 825 | 0 | 74.9 | 74.9 |
| `idx_range` | 2745 | 414 | 414 | 0 | 84.9 | 84.9 |
| `idx_del` | 2745 | 276 | 276 | 0 | 89.9 | 89.9 |
| `idx_stale` | 2745 | 276 | 276 | 0 | 89.9 | 89.9 |
| `idx_dup` | 1291 | 1376 | 1374 | −2 | −6.4 | −6.6 |
| `idx_var` | 3169 | 3169 | 3316 | +147 | −4.6 | 0.0 |

Method B against `pgstatindex`:

| index | full-scan blocks | descent blocks | leaf estimate | true leaf | error | density estimate | `pgstatindex` |
|---|---|---|---|---|---|---|---|
| `idx_seq` | 2736 | 3 | 2733 | 2733 | 0 | 90.01 | 90.06 |
| `idx_del` | 2736 | 3 | 2733 | 2733 | 0 | 9.22 | 9.27 |
| `idx_range` | 414 | 3 | 411 | 411 | 0 | 89.78 | 89.83 |
| `idx_rand` | 3748 | 3 | 3745 | 3745 | 0 | 65.76 | 65.81 |
| `idx_text` | 3575 | 3 | 3572 | 3572 | 0 | 89.93 | 89.98 |
| `idx_multi` | 3575 | 3 | 3572 | 3572 | 0 | 89.93 | 89.96 |
| `idx_uuid` | 1536 | 3 | 1533 | 1533 | 0 | 89.96 | 90.01 |
| `idx_dup` | 1286 | 3 | 1283 | 1283 | 0 | 95.86 | 96.00 |
| `idx_ff50` | 4954 | 3 | 4951 | 4951 | 0 | 49.80 | 49.85 |
| `idx_null` | 2736 | 3 | 2733 | 2733 | 0 | 90.01 | 90.09 |
| `idx_part` | 139 | 2 | 137 | 137 | 0 | 89.78 | 89.83 |
| `idx_var` | 3129 | 3 | 3126 | 3126 | 0 | 94.92 | 90.43 |

### Measured failure modes

- **Stale relstats hide real bloat.** After deleting 900,000 of 1,000,000 rows with no VACUUM and no ANALYZE, `pg_class.reltuples` still read `1e+06` for both table and index, and a `reltuples`-only model reported **0.0% bloat** against a true reclaimable 2745 → 276 blocks. `pg_stat_all_tables` knew: `n_live_tup = 100000`, `n_dead_tup = 900000`. Using `least(reltuples, n_live_tup)` produced exactly 276 blocks, matching the rebuild.
- **A rebuild can make an index bigger.** `idx_dup` (500,000 identical keys) sits at 96.00% density because an all-duplicate split uses `BTREE_SINGLEVAL_FILLFACTOR` ([nbtsplitloc.c#_bt_findsplitloc](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L412-L422)), while a fresh sorted build packs to fillfactor 90. Rebuilding grew it from 1291 to 1376 blocks. Method A predicted this correctly as −6.4%: **a negative `wasted_space_pct` is a real reading and means "do not rebuild".**
- **Random-insert indexes report ~27% bloat forever.** `idx_rand` reached 65.81% density with zero deletions, because non-rightmost leaf splits aim for an even 50/50 division rather than fillfactor ([nbtsplitloc.c#_bt_findsplitloc](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L275-L331)). The 27.0% is genuinely reclaimable — the rebuild returned 3758 → 2745 blocks — but the index will drift straight back. This is a workload property, not a maintenance failure.
- **Highly variable key widths mislead Method A by ~5%.** `idx_var` was reported at −4.6% against a true 0.0%, because a single MAXALIGN of the average width is not the average of per-row MAXALIGNs. Method A′ reduced this to +0.32%.
- **Leaf density alone misses deleted pages entirely.** `idx_range` shows a healthy 89.83% `avg_leaf_density` while 2330 of 2745 blocks are deleted; Method A reported 84.9% bloat and the rebuild confirmed 414 blocks.
- **An index-only scan with heap fetches destroys Method B.** `idx_churn` (never vacuumed, 300,000 heap fetches) yielded 8452 estimated leaf pages against a true 3279.

### Settings and apply scopes

| Setting | Context in v12 | Apply scope |
|---|---|---|
| `statement_timeout` | `PGC_USERSET` ([guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2386)) | session/transaction |
| `lock_timeout` | `PGC_USERSET` ([guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2393)) | session/transaction |
| `maintenance_work_mem` | `PGC_USERSET` ([guc.c#maintenance_work_mem](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2243-L2252)) | session/transaction |
| `enable_seqscan`, `enable_bitmapscan`, `max_parallel_workers_per_gather` | `PGC_USERSET` | session/transaction |
| `block_size` | `PGC_INTERNAL` preset ([guc.c#block_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2879-L2884)) | read-only; always read it with `current_setting('block_size')` rather than hard-coding 8192 |
| `wal_level` | `PGC_POSTMASTER` ([guc.c#wal_level](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4409-L4417)) | restart; only relevant because it decides whether Method C WAL-logs every built page |

No method here requires changing a setting that needs a reload or a restart.

### What no core-SQL method can measure

- **`leaf_fragmentation`.** It counts leaves whose right link points to a lower block number ([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L288-L308)), which requires reading page headers in physical order. Nothing in core exposes that.
- **`LP_DEAD` space inside live leaves.** Entries killed by index scans still occupy their slots until the next split or VACUUM; Method B counts only returned rows, so it reports *live* density, which is why its numbers sit slightly below `pgstatindex`'s physical density.
- **The split between half-dead and deleted pages.** Methods A and B lump both into "not in the live leaf chain"; only `VACUUM VERBOSE` separates deleted from currently-reusable.
- **Per-page detail of any kind.** There is no core page reader, so no core method can say *which* pages are empty.

### Follow-up: the comparison fixture matrix

The tables above use one fixture per shape. To answer "what is the error, per bloat type, for partial and non-partial indexes", a second exact-pin run built a full matrix: **9 bloat types × 3 scales × {non-partial, partial} = 54 indexes over 27 tables**, on a freshly built 12.2 server from the same pin.

Each table carries two indexes over the same key, so both see the identical churn:

```sql
CREATE TABLE m_<type>_<scale> (id bigint, flag boolean, pad text);
CREATE INDEX m_<type>_<scale>_full ON m_<type>_<scale> (id);
CREATE INDEX m_<type>_<scale>_part ON m_<type>_<scale> (id) WHERE flag;
```

`flag` is `id % 5 = 0`, so the partial index holds 20% of the rows. Every delete pattern uses modulus 7 or 11, which are coprime with 5, so the partial index loses the same *proportion* of its entries as the non-partial one rather than all or none of them. Scales are 200,000 / 500,000 / 1,000,000 rows, which is the repeat dimension: each reported error is the worst of three independent sizes.

| type | recipe | resulting shape |
|---|---|---|
| `fresh` | build after load, VACUUM | control, no bloat |
| `scatter` | delete 6 of every 7 rows, VACUUM | underfilled leaves, no page emptied |
| `range` | delete the first 85% of the key range, VACUUM twice | mostly deleted pages, healthy density |
| `random` | insert into an already-existing index in random key order | 50/50 split fill |
| `dup` | insert N identical keys into an existing index | 96% single-value fill |
| `churn_vac` | two full-table `UPDATE`s, then VACUUM | 4x size, low density |
| `churn_unvac` | two full-table `UPDATE`s, no VACUUM | dead entries still indexed |
| `lpdead` | delete 10 of every 11 rows, no VACUUM, then index scans that set `LP_DEAD` | killed-but-present entries |
| `stale` | delete 10 of every 11 rows, no VACUUM, no ANALYZE | stale catalogs |

Ground truth per index is the Method C rebuild (exact reclaimable size) plus `pgstatindex` (exact page classes). Method A was executed by running the filed sweep query's own CTE chain, with only the `actual_bytes > 1024 * 1024` triage filter removed so that sub-megabyte partial indexes are included.

### Follow-up: which pgstatindex columns core SQL reproduces

Restricting to the columns that bear on bloat:

| `pgstatindex` column | core-SQL equivalent | measured agreement |
|---|---|---|
| `index_size` | `pg_relation_size(idx)` | identical on all 54 indexes |
| `leaf_pages` | Method B: `full_scan_blocks - descent_blocks` | **exact on all 36 eligible cells**; unavailable on the 18 cells with heap fetches |
| `avg_leaf_density` | `(rows / leaf_est + 1) * slot / (BLCKSZ - 40)` | −0.04 to −0.05 points on 30 cells, −0.14 to −0.15 on the 6 `dup` cells |
| `deleted_pages` | `blocks - leaf_est - (modelled internal + 1)` | within 1 page on all 6 `range` cells (2330 against 2330 at the top scale); a +1 to +28 residual elsewhere, equal to the internal-page modelling error |
| `empty_pages` (half-dead) | none | not separable from deleted pages |
| `internal_pages`, `tree_level`, `root_block_no` | none | no core equivalent |
| `leaf_fragmentation` | none | needs physical page order; no core equivalent |

The non-leaf total is recovered exactly: `blocks - leaf_est` equalled `internal_pages + deleted_pages + empty_pages + 1` in **all 36 eligible cells**, including the `range` cells carrying 2330 deleted pages.

### Follow-up: error by bloat type, partial and non-partial

Method A's modelled block count against the Method C rebuild, worst of the three scales:

| bloat type | non-partial: worst Δblocks / Δpoints | exact cells | partial: worst Δblocks / Δpoints | exact cells |
|---|---|---|---|---|
| `fresh` | 0 / 0.0 | 3/3 | 0 / 0.0 | 3/3 |
| `scatter` | 0 / 0.0 | 3/3 | 0 / 0.0 | 3/3 |
| `range` | 0 / 0.0 | 3/3 | 0 / 0.0 | 3/3 |
| `random` | 0 / 0.0 | 3/3 | 0 / 0.0 | 3/3 |
| `dup` | 4 / 0.2 | 0/3 | 2 / 0.8 | 1/3 |
| `churn_vac` | 5 / 0.0 | 2/3 | 0 / 0.0 | 3/3 |
| `churn_unvac` | 2 / 0.0 | 2/3 | 16 / 0.7 | 1/3 |
| `lpdead` | 0 / 0.0 | 3/3 | **510 / 92.6** | 0/3 |
| `stale` | 0 / 0.0 | 3/3 | **510 / 92.6** | 0/3 |

Across all 54 cells the model was exact on 39, within 5 blocks on 47, within 16 blocks on 48, and wrong by two orders of magnitude on the remaining 6 — all of which are partial indexes on the two fixtures that were never vacuumed *and* never analysed after the delete.

Method B against `pgstatindex`, same matrix:

| bloat type | eligible cells | `leaf_pages` error | density error (points) |
|---|---|---|---|
| `fresh`, `scatter`, `range`, `random`, `churn_vac` | 30 of 30 | 0 in every cell | −0.04 to −0.05 |
| `dup` | 6 of 6 | 0 in every cell | −0.14 to −0.15 |
| `churn_unvac`, `lpdead`, `stale` | 0 of 18 | precondition failed | precondition failed |

Partial-ness does not affect Method B at all: the partial cells were exact wherever the non-partial ones were. The `dup` cells carry the larger density error because a pivot tuple over an all-duplicate key must absorb a heap TID ([nbtutils.c#_bt_truncate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L2082-L2093)), so the single high key the formula adds is 24 bytes rather than the 20-byte `slot` it assumes.

The 18 ineligible cells are exactly the three fixtures whose tables were never vacuumed, so the visibility map is unset and the index-only scan reaches the heap. The census overstated leaf pages by 2 to 10 times there (21,239 against 10,929 at worst) and the `Heap Fetches` check caught every one.

### Follow-up: an avg_leaf_density predictor head to head

The obvious way to use `pgstatindex` for this job is to compare leaf density with the configured fillfactor. As a size predictor that is:

```text
pgstatindex_expected_blocks = ceil(leaf_pages * avg_leaf_density / fillfactor) + internal_pages + 1
```

Scored against the same rebuilds, worst error per bloat type as a percentage of the rebuilt size:

| bloat type | kind | `avg_leaf_density` predictor | core-SQL model |
|---|---|---|---|
| `fresh` | non-partial / partial | 0.1% / 0.0% | 0.0% / 0.0% |
| `scatter` | non-partial / partial | 4.5% / 3.7% | 0.0% / 0.0% |
| `range` | non-partial / partial | 2.4% / 2.4% | 0.0% / 0.0% |
| `random` | non-partial / partial | 0.4% / 0.4% | 0.0% / 0.0% |
| `dup` | non-partial / partial | 0.2% / 0.7% | 0.2% / 0.7% |
| `churn_vac` | non-partial / partial | 2.2% / 2.7% | 0.2% / 0.0% |
| `churn_unvac` | non-partial / partial | 200.7% / 200.0% | 0.1% / 2.9% |
| `lpdead` | non-partial / partial | 994.4% / 959.6% | 0.0% / 980.8% |
| `stale` | non-partial / partial | 994.4% / 959.6% | 0.0% / 980.8% |

The core-SQL model wins or ties in 16 of the 18 cells, and the two it loses are the partial-index `lpdead`/`stale` cells where both predictors are useless.

The reason is structural, not incidental: `pgstatindex` measures *physical* occupancy, and an entry belonging to a dead heap row occupies its slot exactly like a live one. `pgstatindex_impl` derives density from `PageGetFreeSpace()` ([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L288-L308)), which counts `LP_DEAD` items and not-yet-vacuumed entries as used. So on the `lpdead` fixture at the top scale `pgstatindex` reports `avg_leaf_density = 90.06` on a 2745-block index — indistinguishable from the healthy control — while a rebuild returns 251 blocks, reclaiming 90.9% of the file. A DBA reading only `avg_leaf_density` would rank that index as the healthiest in the database.

This is a like-for-like comparison of the two as *rebuild-size predictors*, not a claim that `pgstatindex` is inaccurate. It reports physical occupancy correctly; physical occupancy just is not reclaimable space. The fix for a `pgstatindex` user is the same live row count the core-SQL model already uses, which is why having the extension installed does not, by itself, improve the estimate.

What `pgstatindex` still gives that no core method matches: the exact deleted-versus-half-dead split, `leaf_fragmentation`, `tree_level`, and a leaf count that needs no visibility-map cooperation and no live row count at all.

### Follow-up: the partial-index failure and its fix

The single large error mode in the whole matrix has one cause. Method A's `live_rows` falls back to `pg_class.reltuples` for a partial index, because `pg_stat_all_tables.n_live_tup` counts the whole table and not the predicate subset:

```sql
CASE WHEN x.indpred IS NOT NULL THEN c.reltuples::numeric
     ELSE least(c.reltuples::numeric,
                coalesce(nullif(s.n_live_tup, 0), c.reltuples)::numeric)
END AS live_rows
```

`reltuples` for an index is refreshed only by VACUUM, which writes the true count ([vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1803-L1815)), or by a standalone ANALYZE, which writes `ceil(tupleFract * totalrows)` from the heap sample ([analyze.c#do_analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629)). A bare `DELETE` triggers neither, so on the `stale` and `lpdead` fixtures the partial index still claimed its pre-delete row count and the model reported 0.0% to −2.0% bloat against a true 89.3% to 90.6%. The non-partial index on the very same table was exact, because the collector's `n_live_tup` had already tracked the delete.

The failure announces itself in the sweep's own output — `dead_tuples` read 909,091 and `modelled_rows` equalled the pre-delete `idx_reltuples` — and one plain `ANALYZE` repairs it. Re-running Method A on all six failing cells after `ANALYZE`:

| cell | live blocks | rebuilt | model before ANALYZE | model after | Δ after |
|---|---|---|---|---|---|
| `stale` partial 200k | 112 | 12 | 112 | 12 | 0 |
| `stale` partial 500k | 276 | 27 | 275 | 28 | +1 |
| `stale` partial 1000k | 551 | 52 | 562 | 53 | +1 |
| `lpdead` partial 200k | 112 | 12 | 110 | 12 | 0 |
| `lpdead` partial 500k | 276 | 27 | 275 | 27 | 0 |
| `lpdead` partial 1000k | 551 | 52 | 562 | 53 | +1 |

The worst error drops from 510 blocks to 1. The residual ±1 block is ANALYZE's sampling: it recorded 18,337 index rows against a true 18,181 for the largest partial index, because `tupleFract * totalrows` is an estimate rather than a count.

Practical rule: **treat a partial index whose table shows dead tuples or no recent analyze as unmeasured, not as unbloated.** Run `ANALYZE` first, or fall back to the Method C rebuild probe, which needs no statistics at all.

### Follow-up: the output columns say wasted_space, not bloat

Done. On the reporting side it costs nothing: the Method A sweep now labels its two reporting columns `wasted_space` and `wasted_space_pct`, and carries the tag `/* wiki_btree_wasted_space_sweep */`. Every value expression is untouched — `live_rows`, `slot`, `leaf_cap`, `int_cap`, `expected_blocks`, the triage filter and the `ORDER BY` key — so **no number in any table on this page moves**. The Method C probe index is renamed too, and that one is not a label change; see [What a consumer must change](#what-a-consumer-must-change).

| As filed | Now | The value behind it |
|---|---|---|
| `wasted` | `wasted_space` | `pg_size_pretty(greatest(actual_bytes - expected_blocks * bs, 0)::bigint)`, still clamped at zero |
| `bloat_pct` | `wasted_space_pct` | `round((100 * (1 - (expected_blocks * bs) / greatest(actual_bytes, 1)))::numeric, 1)`, unclamped and therefore signed |
| `/* wiki_btree_bloat_sweep */` | `/* wiki_btree_wasted_space_sweep */` | the Method A statement tag |
| `wiki_bloat_probe` | `wiki_wasted_space_probe` | the Method C probe index, in the generated DDL, the `CREATE`, both `pg_relation_size` arguments and the `DROP` |
| — | `wasted_space_bytes` | the label to give the raw `greatest(actual_bytes - expected_blocks * bs, 0)::bigint` if a consumer parses the output instead of reading it |

Two table headers follow the columns: `model bloat %` and `true bloat %` in [Exact-pin measurements](#exact-pin-measurements) are now `model wasted_space %` and `true wasted_space %`. The `bloat type` column of the matrix tables is deliberately left alone — it names the mechanism that emptied the pages in a fixture, not a column this SQL emits — and so is the page title.

The rename is not merely cosmetic, because "bloat" in this checkout means per-page state, which no method on this page can see. v12 puts its definition in the `REINDEX` reference page: an index "has become 'bloated', that is it contains many empty or nearly-empty pages" ([ref/reindex.sgml#bloated](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57)), and the routine-reindexing section states the mechanism in the same per-page terms — "if all but a few index keys on a page have been deleted, the page remains allocated" ([maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L866-L874)). Method A never reads a page. It subtracts a modelled fresh-build size from `pg_relation_size`, which is why [What no core-SQL method can measure](#what-no-core-sql-method-can-measure) lists `LP_DEAD` space inside live leaves, the deleted-versus-half-dead split, `leaf_fragmentation` and per-page detail as invisible, and why the percentage can be negative at all. "Wasted space" is this documentation's own phrase for space a maintenance command is expected to recover ([ref/copy.sgml#recover-the-wasted-space](../../../../raw/postgres-12/doc/src/sgml/ref/copy.sgml#L532-L541)), which is what the two columns estimate.

Unlike later majors there is no glossary here to appeal to: `doc/src/sgml/` in this checkout has no `glossary.sgml`, so all 24 case-insensitive matches for `bloat` under it are prose — the two paragraphs above, the non-B-tree warning ([maintenance.sgml#non-btree-bloat](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L876-L880)), and settings, replication and release-note advice. What ships as SQL is consistent all the same: `system_views.sql`, `pg_proc.dat` and every contrib SQL script contain zero occurrences of the string, while `pgstattuple` names this class of quantity `free_space`/`free_percent` and `approx_free_space`/`approx_free_percent` ([pgstattuple--1.4.sql#free_space](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L11-L16), [pgstattuple--1.4.sql#approx_free_space](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L88-L94)). The only two contrib occurrences are C comments, one of them the header of the estimator itself ([pgstatapprox.c#header](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L1-L12)).

### What the rename cannot change

- **Any value.** `AS` assigns a name to a select-list entry "for subsequent processing, such as for use in an `ORDER BY` clause or for display by the client application"; the expression itself is untouched ([queries.sgml#Column-Labels](../../../../raw/postgres-12/doc/src/sgml/queries.sgml#L1473-L1496)).
- **Row order.** The sweep sorts on an expression, `ORDER BY greatest(actual_bytes - expected_blocks * bs, 0) DESC`. A label may be a sort key, but only standing alone — the documentation marks `ORDER BY sum + c` as wrong for exactly that reason ([queries.sgml#sort-by-output-column](../../../../raw/postgres-12/doc/src/sgml/queries.sgml#L1742-L1761)) — so no label change reaches this `ORDER BY`.
- **The sweep's `pg_stat_statements` identity.** In v12 the query ID is computed by the contrib module itself, at post-parse-analysis time, over the finished `Query` tree ([pg_stat_statements.c#pgss_post_parse_analyze](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L801-L826)), and the walker's stated rule of thumb is to ignore "anything not semantically significant (such as alias names)" ([pg_stat_statements.c#JumbleQuery](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L2402-L2435)). Its `T_TargetEntry` case appends `resno` and `ressortgroupref` and recurses into the expression; `resname`, which is where an `AS` label lands, is never touched ([pg_stat_statements.c#T_TargetEntry](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L2837-L2845)). The tag cannot reach the tree at all: the lexer switches to an exclusive state at `/*` and returns no token for the comment body ([scan.l#xcstart](../../../../raw/postgres-12/src/backend/parser/scan.l#L344-L346), [scan.l#extended-comments](../../../../raw/postgres-12/src/backend/parser/scan.l#L427-L465)).
- **Identifier limits.** The longest new name is `wiki_wasted_space_probe` at 23 bytes and the longest new label `wasted_space_pct` at 16, against `NAMEDATALEN 64`, which limits names to 63 bytes ([pg_config_manual.h#NAMEDATALEN](../../../../raw/postgres-12/src/include/pg_config_manual.h#L22-L29)). Truncation, and the `NOTICE: identifier "..." will be truncated to "..."` that comes with it, only starts there ([scansup.c#downcase_truncate_identifier](../../../../raw/postgres-12/src/backend/parser/scansup.c#L117-L134), [scansup.c#truncate_identifier](../../../../raw/postgres-12/src/backend/parser/scansup.c#L177-L209)).

### What a consumer must change

1. **Anything that selects the old labels.** Wrapping the sweep in a view or subquery and reading `bloat_pct` now fails with `ERRCODE_UNDEFINED_COLUMN` and `column "bloat_pct" does not exist`, possibly carrying a fuzzy-matched "Perhaps you meant to reference the column ..." hint ([parse_relation.c#errorMissingColumn](../../../../raw/postgres-12/src/backend/parser/parse_relation.c#L3308-L3359)). Output labels have no alias-compatibility mechanism, so there is nothing to deprecate gradually.
2. **Anything that sorts on the byte column.** `pg_size_pretty` returns `text` in both its `int8` and `numeric` forms ([pg_proc.dat#pg_size_pretty](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L6896-L6903)), so `ORDER BY wasted_space DESC` in a wrapper is a collated string comparison through `bttextcmp` and `varstr_cmp` ([varlena.c#bttextcmp](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L1924-L1937), [varlena.c#varstr_cmp](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L1468-L1490)) and puts `9 bytes` above `10 MB`. That was already true of `wasted`; it is why the statement's own `ORDER BY` sorts the byte expression, and why a parsing consumer should take `wasted_space_bytes` instead.
3. **Log and `pg_stat_statements` text matching.** The tag survives into both. `log_statement` and `log_min_duration_statement` print the string as received ([postgres.c#log_statement](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1039-L1047), [postgres.c#duration-statement](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1280-L1298)), and `pgss_store` trims only leading and trailing whitespace from the statement's slice of the source text ([pg_stat_statements.c#pgss_store](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1139-L1146)). So a grep for `wiki_btree_bloat_sweep` stops matching new traffic but not old rows: because the query ID does not move and the text is written only when the hash entry is created ([pg_stat_statements.c#entry-creation](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1169-L1231)), an existing entry keeps showing the old tag until it is evicted or `pg_stat_statements_reset()` runs.
4. **The probe rename, which is an object name and not a label.** `wiki_wasted_space_probe` has to move in five places at once — the generated DDL's replacement string, the `CREATE INDEX CONCURRENTLY`, both `pg_relation_size` arguments and the `DROP INDEX CONCURRENTLY` — plus the leftover check. Renaming some sites and not others produces the failure Method C already warns about: an invalid leftover index that still costs write overhead, because `indisvalid` is set non-transactionally as the last step ([index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3314-L3330)), and a cleanup check looking for the wrong name. It also does something the label rename cannot: it moves the two utility statements' `pg_stat_statements` identity. `pgss_ProcessUtility` passes a query ID of 0 to signal a utility statement ([pg_stat_statements.c#pgss_ProcessUtility](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1054-L1062)), and `pgss_store` then keys it by a hash of the statement text ([pg_stat_statements.c#utility-hash](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1148-L1162)), so the renamed `CREATE INDEX CONCURRENTLY` and `DROP INDEX CONCURRENTLY` land on new entries. Inside the two `SELECT`s the name only ever appears in a string constant — twice as a `pg_relation_size` argument, where parse analysis coerces the unknown literal to `regclass` but keeps the literal's own location "to simplify life for pg_stat_statements" ([parse_coerce.c#coerce_type](../../../../raw/postgres-12/src/backend/parser/parse_coerce.c#L286-L291)), and once inside the DDL generator's replacement text — and a constant is recorded for normalization rather than jumbled ([pg_stat_statements.c#T_Const](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L2534-L2543)), then replaced by a `$n` parameter symbol in the stored text ([pg_stat_statements.c#generate_normalized_query](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L3058-L3087)), so it changes neither their query ID nor what `pg_stat_statements` displays for them.

### Follow-up: source support for the v12 and v17 open-question review

**Use a separate v12 statistics-publication protocol and retain independent
width, NULL and count validation.** This section supplies the missing
version-local source evidence for the
[proposal review on the PostgreSQL 17 question](../../../v17/questions/indexing/btree-index-bloat-core-sql-only.md#open-questions).
It reviews the portable estimator's v12 boundary, not a new implementation of
this page's Method A. Both maintained statements remain unchanged. No server
was started and no historical fixture was rerun for this follow-up.

### The v12 build and statistics boundaries

The B-tree handler declares `BTNProcs` support procedures, and that constant
is 3: comparison, sort support and in-range support. `btoptions` delegates to
the B-tree kind of `default_reloptions`; its registered options are fillfactor
and `vacuum_cleanup_index_scale_factor`. The sorted build passes each input
tuple directly to `_bt_buildadd`, including duplicate keys; this path has no
posting-list aggregation. A portable estimator must not require a fourth
B-tree support procedure or a deduplication reloption to validate v12 inputs.
[nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L104-L114),
[nbtree.h#BTNProcs](../../../../raw/postgres-12/src/include/access/nbtree.h#L379-L395),
[nbtutils.c#btoptions](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L2027-L2031),
[reloptions.c#btree-fillfactor](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L177-L185),
[reloptions.c#vacuum_cleanup_index_scale_factor](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L423-L430),
[nbtsort.c#_bt_load](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1246-L1284).

ANALYZE collects index-column statistics for expression positions whose
`ii_IndexAttrNumbers` entry is zero. For a partial index it evaluates the
predicate, counts matching sampled rows and calls `FormIndexDatum` for
expression values. Plain keys and INCLUDE columns do not acquire independent
predicate-subset column statistics through that expression path. A zero
statistics target skips an attribute. This supports the proposed
attribute-level input diagnostics for plain, expression and mixed indexes;
deduplication eligibility cannot repair a missing or wrong-population width.
[analyze.c#do_analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L438-L466),
[analyze.c#compute_index_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L771-L789),
[analyze.c#subset-expression-statistics](../../../../raw/postgres-12/src/backend/commands/analyze.c#L821-L843),
[analyze.c#examine_attribute](../../../../raw/postgres-12/src/backend/commands/analyze.c#L887-L893).

There are distinct count writers. CREATE INDEX/REINDEX passes the build's
`index_tuples` to `index_update_stats`, which writes a nonnegative count into
`pg_class.reltuples`. Standalone ANALYZE instead writes
`ceil(tupleFract * totalrows)` for each index; its VACUUM-ANALYZE path avoids
overwriting VACUUM's count. `RelationSetNewRelfilenode` initializes the new
relation's count to zero. Thus zero is not a durable certificate of current
emptiness, and a partial-index sample can report zero when it contains no
matching rows. The proposed full subset check must record its own observation
instead of treating either the catalog value or a counter as proof.
[index.c#index_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2989),
[index.c#index_update_stats](../../../../raw/postgres-12/src/backend/catalog/index.c#L2761-L2779),
[analyze.c#index-relstats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629),
[analyze.c#tupleFract](../../../../raw/postgres-12/src/backend/commands/analyze.c#L771-L777),
[analyze.c#subset-estimate](../../../../raw/postgres-12/src/backend/commands/analyze.c#L821-L827),
[relcache.c#RelationSetNewRelfilenode](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L3527-L3541).

The proposed width probe also remains approximate. Index tuple formation
fetches external values, tries inline compression above `TOAST_INDEX_TARGET`
for suitable storage types, derives the NULL-dependent header and calls
`heap_compute_data_size` before aligning the result. `pg_column_size` returns
the size of its input datum, not an index tuple assembled through that path.
Do not convert a sampled heap/composite width into a claim of exact index
bytes.
[indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L66-L133),
[varlena.c#pg_column_size](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L5044-L5089).

The builder tests both hard fit and the fillfactor threshold with a minimum
item count, moves the last tuple into the next page and creates the old page's
high key. `_bt_truncate` can discard suffix attributes or need a heap TID when
equal keys do not separate the pages. Those transitions make a leaf/internal
inventory the appropriate proposed way to isolate the historical 1–6-block
duplicate-key residual. They do not prove that any particular residual came
from one level of the tree. Catalog means omit the actual ordered tuple
lengths and separators needed for exact simulation.
[nbtsort.c#_bt_buildadd](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L856-L935),
[nbtsort.c#high-key-truncation](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L947-L990),
[nbtutils.c#_bt_truncate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L2116-L2201).

### The v12 publication protocol

**Propose ending the fixture writer session before maintenance, followed by
bounded observer polling that checks the intended counters.** The normal
`pgstat_report_stat` path is rate-limited. Backend shutdown explicitly calls
it with `force = true`, sending pending counts to the collector. However,
`pgstat_send` retries interrupted sends and otherwise ignores send failures;
writer exit alone is not proof that the collector received the counts.
[pgstat.c#pgstat_report_stat](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L803-L921),
[pgstat.c#pgstat_beshutdown_hook](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L3073-L3094),
[pgstat.c#pgstat_send](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L4341-L4360).

Clear the observer's statistics snapshot between polling attempts or use new
transactions. The backend caches the statistics-file snapshot until it is
cleared; clearing discards the local view, not pending writer messages.
The shipped `stats.sql` test uses a bounded polling loop, checks independent
counter advances and snapshot time, and reconnects its writer before waiting.
Adapt that pattern to known fixture DML counts, then run ANALYZE/VACUUM and
wait for the maintenance result before scoring. Make timeout a failed harness
precondition rather than an estimator result.
[pgstat.c#backend_read_statsfile](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L5636-L5651),
[pgstat.c#pgstat_clear_snapshot](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L5785-L5806),
[stats.sql#wait_for_stats](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L27-L78),
[stats.sql#writer-reconnect](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L146-L155).

The collector has the same *kind of ordering concern*, established here from
v12's own implementation: `pgstat_recv_tabstat` adds DML deltas, resetting
live/dead counts first when a truncate flag is present;
`pgstat_recv_analyze` assigns live/dead counts absolutely and can zero
`changes_since_analyze`, explicitly forgetting changes committed during
ANALYZE. A database statistics reset can also discard the table entries.
These paths explain why a zero counter cannot certify a fresh subset count.
They do not establish the exact message ordering of the old fixture run.
[pgstat.c#pgstat_recv_tabstat](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L5966-L5994),
[pgstat.c#pgstat_recv_analyze](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6240-L6272),
[pgstat.c#pgstat_recv_resetcounter](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6093-L6121).

**Acceptance:** trace the sender and collector receive sites for load,
truncate/reload and DELETE followed by maintenance. Compare deliberately
delayed publication with the barriered protocol. Store command boundaries,
pending counts, received messages, snapshots and fixture invariants. Existing
TRUNCATE/subtransaction tests provide adjacent engine coverage; the new
estimator artifacts still need their own reproducible fixtures.
[stats.sql#truncate-statistics](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L80-L136).

### V12 catalog, build and output compatibility

`pg_stats` exposes `inherited`; choose non-inherited rows when estimating one
physical index. Its column-privilege and RLS filters can hide statistics, so
absence does not distinguish “not collected” from “not visible.” This pin's
`pg_stats_ext` exposes ndistinct, dependencies and MCV data but no `inherited`
or expression-list field. The proposed adapter must use this view's actual
shape and privilege conditions instead of selecting fields from another
version's definition. Extended statistics are built only for the individual
relation in this pin, guarded by `!inh` in ANALYZE.
[analyze.c#BuildRelationExtStatistics](../../../../raw/postgres-12/src/backend/commands/analyze.c#L576-L584),
[system_views.sql#pg_stats](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L189-L197),
[system_views.sql#pg_stats-visibility](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L247-L254),
[system_views.sql#pg_stats_ext](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L256-L291).

ICU is a configure-time option backed by `USE_ICU` and an ICU dependency check.
An unavailable ICU test build is a build-coverage gap, not evidence that this
version lacks that provider. Build block size is configurable, and `MAXALIGN`
uses the configured `MAXIMUM_ALIGNOF`. Proposed 4/8/16-kB and ICU fixtures must
record their build settings and mark unavailable dependencies as skipped.
Catalog `_d.h` files and `schemapg.h` are generated by the backend catalog
Makefile from the pinned definitions; no new generated field or server patch
is needed for the estimator proposals.
[configure.in#ICU](../../../../raw/postgres-12/configure.in#L730-L738),
[configure.in#blocksize](../../../../raw/postgres-12/configure.in#L250-L265),
[c.h#MAXALIGN](../../../../raw/postgres-12/src/include/c.h#L673-L697),
[Makefile#GENERATED_HEADERS](../../../../raw/postgres-12/src/backend/catalog/Makefile#L51),
[Makefile#genbki](../../../../raw/postgres-12/src/backend/catalog/Makefile#L79-L100).

For proposed signed-byte reporting, keep raw bytes as the machine interface.
Here `pg_size_pretty(bigint)` scales with shifts and its `half_rounded` macro
rounds toward positive infinity. Verify negative boundary strings on this
pin itself rather than importing expected text from another version. This
review changes neither Method A's current projection nor its existing
clamping behavior.
[dbsize.c#half_rounded](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L34-L35),
[dbsize.c#pg_size_pretty](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L534-L571).

Use initial session `statement_timeout = '30s'` and `lock_timeout = '2s'` for
the proposed catalog/probe work. Both contexts are `PGC_USERSET`, so they apply
at session/transaction scope without restart or reload. A probe that exceeds
its budget returns an incomplete measurement; larger probes need a separately
chosen budget.
[guc.c#statement_timeout-and-lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2397).

The v12 source gap in the cross-version Open Questions is addressed by this
section. New fixture execution, instrumented collector attribution,
input/probe integration, page-model accuracy and cost measurement remain open.


## Context Reviewed

- Remaining-open-question review, 2026-09-07: reviewed the portable estimator's v12 B-tree support/build boundary, count and statistics writers, collector sender/receiver protocol, view visibility, generated catalogs, build options and signed formatting. The cited source supports the analysis and proposed acceptance tests. No new server execution or full-page re-verification was performed; existing SQL and human verification fields are unchanged.

- nbtree build and split: `nbtsort.c` (`_bt_pagestate`, `_bt_blnewpage`, `_bt_buildadd`, `_bt_load`), `nbtsplitloc.c` (`_bt_findsplitloc`, `_bt_deltasortsplits`, `_bt_afternewitemoff`), `nbtinsert.c`, `nbtree.h` fillfactor and page-flag constants, `README`.
- Page and tuple layout: `bufpage.h`, `bufpage.c` (`PageInit`, `PageGetFreeSpace`, `PageAddItemExtended`), `itemid.h`, `itup.h`, `indextuple.c` (`index_form_tuple`, `index_truncate_tuple`), `heaptuple.c` (`heap_compute_data_size`), `c.h` MAXALIGN.
- VACUUM and page recycling: `nbtree.c` (`btbulkdelete`, `btvacuumcleanup`, `btvacuumscan`, `btvacuumpage`), `nbtpage.c` (`_bt_pagedel`, `_bt_page_recyclable`, `_bt_getbuf`), `indexfsm.c`, `genam.h` (`IndexBulkDeleteResult`), `vacuumlazy.c` (`lazy_vacuum_index`, `lazy_cleanup_index`), `vacuum.c` (`vac_update_relstats`).
- Core SQL surfaces: `pg_proc.dat`, `dbsize.c`, `relpath.c`/`relpath.h`, `varlena.c` (`pg_column_size`), `tuptoaster.c` (`toast_datum_size`), `system_views.sql`, `pg_class.h`, `pg_statistic.h`, `analyze.c`, `index.c` (`index_update_stats`), `pgstatfuncs.c`, `pgstat.c`, `parse_clause.c` (TABLESAMPLE), `guc.c`.
- Executor and EXPLAIN: `nodeIndexonlyscan.c`, `nbtsearch.c` (`_bt_steppage`, `_bt_readnextpage`, `_bt_endpoint`), `instrument.h`/`instrument.c`, `explain.c`, `explain.sgml`.
- Rebuild path: `indexcmds.c` (`DefineIndex`), `index.c` (`index_set_state_flags`), `tablecmds.c` (`RemoveRelations`, `RenameRelation`), `utility.c`, `xact.c`, `ruleutils.c` (`pg_get_indexdef`), `create_index.sgml`, `reindex.sgml`, `maintenance.sgml`.
- Contrib boundary: `pgstattuple.control`, `pgstattuple--1.4--1.5.sql`, `pgstatindex.c`, `pageinspect.control`, `rawpage.c`, `btreefuncs.c`, `pg_freespacemap.control`, `amcheck.control`, `extension.c`, `pgstattuple.sgml`, `pageinspect.sgml`, `contrib.sgml`.
- Exact-pin execution: one isolated 12.2 server built from the pinned checkout under `.wiki-runtime/`, 15 fixtures, Methods A–D executed against each, with `pgstattuple`/`pageinspect` installed solely as ground truth. Test objects were dropped and the server was stopped afterwards.
- Column-rename follow-up, source coverage (no server run; this follow-up is source-only): output labelling and sorting in `queries.sgml` (the Column Labels section and the `ORDER BY`-by-output-column rule); query identity and query text in contrib `pg_stat_statements.c` (`pgss_post_parse_analyze`, `JumbleQuery`'s rule of thumb, the `T_TargetEntry` and `T_Const` cases of `JumbleExpr`, `RecordConstLocation`, `pgss_store`'s whitespace trim, utility-statement string hash, entry lookup and creation, `generate_normalized_query`, `qtext_store`, `pgss_ProcessUtility`, the `pg_stat_statements.track_utility` GUC) and `postgres.c` (`exec_simple_query`'s `log_statement` and duration logging, `check_log_statement`); lexer comment handling in `scan.l` (`xcstart`/`xcstop`/`xcinside`, the `{whitespace}` rule and the `<xc>` block); identifier limits in `pg_config_manual.h` (`NAMEDATALEN`) and `scansup.c` (`downcase_truncate_identifier`, `downcase_identifier`, `truncate_identifier`); error and type surfaces in `parse_relation.c` (`errorMissingColumn`), `parse_coerce.c` (`coerce_type`'s unknown-literal branch and its location rule), `pg_proc.dat` (both `pg_size_pretty` entries), `varlena.c` (`bttextcmp`, `text_cmp`, `varstr_cmp`) and `dbsize.c` (`half_rounded`, `pg_size_pretty`, `pg_size_pretty_numeric`); vocabulary in `ref/reindex.sgml`, `maintenance.sgml`, `ref/copy.sgml`, `pgstattuple--1.4.sql` and `pgstatapprox.c`, plus whole-tree string searches for `bloat` across `doc/src/sgml/`, `src/`, `system_views.sql`, `pg_proc.dat` and every contrib SQL script, and a check that this checkout has no `doc/src/sgml/glossary.sgml`.
- Follow-up exact-pin execution: a second isolated 12.2 server from the same pin, carrying a 9-bloat-type × 3-scale × partial/non-partial matrix (54 indexes over 27 tables). Per index it collected `pgstatindex` ground truth, the filed Method A model run from the page's own CTE chain, the Method B census with its `Heap Fetches` precondition, and a Method C rebuild, then re-ran Method A on the six failing partial cells after a plain `ANALYZE`. Test objects were dropped and the server was stopped afterwards.

## Evidence Map

| Claim | Evidence |
|---|---|
| Core has no page/FSM reader; the tools are contrib and superuser-gated | [extension.c#read_extension_control_file](../../../../raw/postgres-12/src/backend/commands/extension.c#L605-L625), [extension.c#execute_extension_script](../../../../raw/postgres-12/src/backend/commands/extension.c#L798-L817), [pageinspect.sgml](../../../../raw/postgres-12/doc/src/sgml/pageinspect.sgml#L10-L14), [pgstattuple--1.4--1.5.sql](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92) |
| `pg_relation_size` is a live filesystem measurement of one fork | [dbsize.c#calculate_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L266-L308), [dbsize.c#pg_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L310-L336), [relpath.c#forkNames](../../../../raw/postgres-12/src/common/relpath.c#L26-L38) |
| 8152 usable bytes per B-tree page | [nbtsplitloc.c#leftspace](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L155-L158), [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L213-L216), [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L55-L68) |
| Entry cost is `MAXALIGN(hoff + data) + 4`; NULLs add 8 to `hoff` and drop their data | [itup.h#IndexInfoFindDataOffset](../../../../raw/postgres-12/src/include/access/itup.h#L76-L90), [indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L121-L135), [heaptuple.c#heap_compute_data_size](../../../../raw/postgres-12/src/backend/access/common/heaptuple.c#L127-L164), [itemid.h#ItemIdData](../../../../raw/postgres-12/src/include/storage/itemid.h#L25-L30) |
| Build fills a leaf until free space drops below `BLCKSZ*(100-ff)/100`; one line pointer is pre-reserved | [nbtsort.c#_bt_pagestate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L724-L729), [nbtsort.c#_bt_blnewpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L621-L646), [nbtsort.c#_bt_buildadd](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L856-L899), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L580-L597), [rel.h#RelationGetTargetPageFreeSpace](../../../../raw/postgres-12/src/include/utils/rel.h#L304-L309) |
| Internal levels use fillfactor 70; all-duplicate leaf splits use 96 | [nbtree.h#BTREE_DEFAULT_FILLFACTOR](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171), [nbtsplitloc.c#_bt_findsplitloc](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L412-L422) |
| Non-rightmost leaf splits target 50/50, so random inserts settle well below fillfactor | [nbtsplitloc.c#_bt_findsplitloc](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L275-L331) |
| Deleted pages stay in the file and are only recorded in the FSM | [README#page-deletion](../../../../raw/postgres-12/src/backend/access/nbtree/README#L327-L334), [nbtree.c#btvacuumpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1166-L1188), [indexfsm.c#RecordFreeIndexPage](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L48-L55) |
| Partly-emptied pages remain allocated, which is the documented bloat mechanism | [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L866-L874) |
| Index `reltuples` comes from the heap sample under ANALYZE and the true count under VACUUM | [analyze.c#do_analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629), [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1803-L1815), [vacuum.c#vac_update_relstats](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1181-L1196) |
| `relpages`/`reltuples` are documented planner estimates | [pg_class.h#relpages](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L59-L63), [catalogs.sgml#pg_class](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L1759-L1782) |
| `n_live_tup`/`n_dead_tup` come from the collector | [system_views.sql#pg_stat_all_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L566-L572), [pgstatfuncs.c#pg_stat_get_live_tuples](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L151-L180) |
| `avg_width` is a sampled, post-TOAST stored width | [pg_statistic.h#stawidth](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L39-L49), [analyze.c#compute_scalar_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L2223-L2231) |
| `pg_column_size` returns the stored datum size | [varlena.c#pg_column_size](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L5044-L5090), [tuptoaster.c#toast_datum_size](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L406-L458) |
| A forward index scan reads one buffer per right link | [nbtsearch.c#_bt_readnextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1737-L1786) |
| `BUFFERS` is a single per-node counter with no per-relation split, inclusive of children | [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19-L33), [instrument.c#InstrStopNode](../../../../raw/postgres-12/src/backend/executor/instrument.c#L74-L106), [explain.sgml#BUFFERS](../../../../raw/postgres-12/doc/src/sgml/ref/explain.sgml#L167-L193) |
| Index-only scans fall back to the heap when the VM bit is unset, and report `Heap Fetches` | [nodeIndexonlyscan.c#IndexOnlyNext](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L161-L170), [explain.c#ExplainNode](../../../../raw/postgres-12/src/backend/commands/explain.c#L1594-L1609) |
| `pgstatindex`'s density denominator and fragmentation definition | [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L288-L308), [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L356) |
| `VACUUM VERBOSE` index message and its fields | [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1817-L1827), [nbtree.c#btvacuumscan](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1090-L1098) |
| A no-op VACUUM prints no index line | [nbtree.c#btvacuumcleanup](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L913-L919) |
| CIC restrictions, lock level, invalid-index leftover, and build cost | [indexcmds.c#DefineIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L548-L564), [indexcmds.c#DefineIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L604-L622), [utility.c#ProcessUtilitySlow](../../../../raw/postgres-12/src/backend/tcop/utility.c#L1301-L1310), [index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3314-L3330), [create_index.sgml#CONCURRENTLY](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L574-L596), [nbtsort.c#_bt_blwritepage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L576-L580) |
| `pg_get_indexdef` emits reloptions but not the tablespace or `CONCURRENTLY` | [ruleutils.c#pg_get_indexdef](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L1088-L1115), [ruleutils.c#pg_get_indexdef_worker](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L1410-L1439) |
| `TABLESAMPLE` cannot be applied to an index | [parse_clause.c#transformRangeTableSample](../../../../raw/postgres-12/src/backend/parser/parse_clause.c#L1162-L1169) |
| `AS` names a select-list entry for display and later reference; a label is a sort key only standing alone | [queries.sgml#Column-Labels](../../../../raw/postgres-12/doc/src/sgml/queries.sgml#L1473-L1496), [queries.sgml#sort-by-output-column](../../../../raw/postgres-12/doc/src/sgml/queries.sgml#L1742-L1761) |
| v12 defines a bloated index as one holding many empty or nearly-empty pages, and "wasted space" as what a maintenance command recovers | [ref/reindex.sgml#bloated](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57), [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L866-L874), [ref/copy.sgml#recover-the-wasted-space](../../../../raw/postgres-12/doc/src/sgml/ref/copy.sgml#L532-L541) |
| Contrib names this quantity free space, not bloat, in its SQL interface | [pgstattuple--1.4.sql#free_space](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L11-L16), [pgstattuple--1.4.sql#approx_free_space](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L88-L94), [pgstatapprox.c#header](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L1-L12) |
| A label rename cannot move the sweep's query ID: v12 jumbles the `Query` tree in contrib and ignores `resname` | [pg_stat_statements.c#pgss_post_parse_analyze](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L801-L826), [pg_stat_statements.c#JumbleQuery](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L2402-L2412), [pg_stat_statements.c#T_TargetEntry](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L2837-L2845) |
| A `/* ... */` tag produces no token, so it cannot reach the parse tree | [scan.l#xcstart](../../../../raw/postgres-12/src/backend/parser/scan.l#L344-L346), [scan.l#extended-comments](../../../../raw/postgres-12/src/backend/parser/scan.l#L427-L465) |
| The new names sit far below the truncation point | [pg_config_manual.h#NAMEDATALEN](../../../../raw/postgres-12/src/include/pg_config_manual.h#L22-L29), [scansup.c#downcase_truncate_identifier](../../../../raw/postgres-12/src/backend/parser/scansup.c#L117-L134), [scansup.c#truncate_identifier](../../../../raw/postgres-12/src/backend/parser/scansup.c#L177-L209) |
| Reading an old label raises `ERRCODE_UNDEFINED_COLUMN`, possibly with a fuzzy-match hint | [parse_relation.c#errorMissingColumn](../../../../raw/postgres-12/src/backend/parser/parse_relation.c#L3308-L3359) |
| `pg_size_pretty` returns `text`, so ordering by the byte label is a collated string comparison | [pg_proc.dat#pg_size_pretty](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L6896-L6903), [varlena.c#bttextcmp](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L1924-L1937), [varlena.c#varstr_cmp](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L1468-L1490) |
| The tag reaches the log and `pg_stat_statements`, whose text is written only at entry creation | [postgres.c#log_statement](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1039-L1047), [postgres.c#duration-statement](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1280-L1298), [pg_stat_statements.c#pgss_store](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1139-L1146), [pg_stat_statements.c#entry-creation](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1169-L1231) |
| A utility statement is keyed by a hash of its text, so the probe rename creates new entries, while a constant in a `SELECT` is normalized away | [pg_stat_statements.c#pgss_ProcessUtility](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1054-L1062), [pg_stat_statements.c#utility-hash](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1148-L1162), [pg_stat_statements.c#T_Const](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L2534-L2543), [pg_stat_statements.c#generate_normalized_query](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L3058-L3087), [parse_coerce.c#coerce_type](../../../../raw/postgres-12/src/backend/parser/parse_coerce.c#L286-L291) |

| V12 expression-statistics selection, disabled collection and visibility filters | [analyze.c:438](../../../../raw/postgres-12/src/backend/commands/analyze.c#L438-L466), [analyze.c:887](../../../../raw/postgres-12/src/backend/commands/analyze.c#L887-L893), [system_views.sql:247](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L247-L291) |
| V12 sampled subset counts, reset-to-zero catalog state and build count writes | [analyze.c:771](../../../../raw/postgres-12/src/backend/commands/analyze.c#L771-L789), [analyze.c:607](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629), [relcache.c:3527](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L3527-L3535), [index.c:2761](../../../../raw/postgres-12/src/backend/catalog/index.c#L2761-L2779) |
| V12 rate-limited reports, forced exit reporting, additive/absolute receivers and polling tests | [pgstat.c:803](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L803-L921), [pgstat.c:3083](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L3083-L3094), [pgstat.c:5978](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L5978-L5986), [pgstat.c:6240](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6240-L6272), [stats.sql:27](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L27-L78), [stats.sql:146](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L146-L155) |
| V12 hard/soft page limits, high-key truncation and configurable block size | [nbtsort.c:856](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L856-L976), [nbtutils.c:2116](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L2116-L2201), [configure.in:250](../../../../raw/postgres-12/configure.in#L250-L265) |
| V12 local/inherited column-statistics flag and the extended-statistics view shape | [system_views.sql:189](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L189-L197), [system_views.sql:256](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L256-L291) |
| V12 B-tree support procedures, reloptions and ICU build option | [nbtree.h:379](../../../../raw/postgres-12/src/include/access/nbtree.h#L379-L395), [nbtutils.c:2027](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L2027-L2031), [reloptions.c:179](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L179-L185), [reloptions.c:423](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L423-L430), [configure.in:730](../../../../raw/postgres-12/configure.in#L730-L738) |
| V12 signed-size formatting and rounding | [dbsize.c:34](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L34-L35), [dbsize.c:534](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L534-L571) |
| V12 statistics polling/TRUNCATE tests and generated catalog headers | [stats.sql:27](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L27-L78), [stats.sql:80](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L80-L136), [Makefile:79](../../../../raw/postgres-12/src/backend/catalog/Makefile#L79-L100) |

## Open Questions

The [v12/v17 source follow-up](#follow-up-source-support-for-the-v12-and-v17-open-question-review) supplies source support for the portable estimator. Its new publication/probe protocols and accuracy/cost tests remain proposals; this scoped addition does not resolve the independent Method A–D measurement questions below.

- **Why a cold-session descent probe reads more blocks than a warm one.** On `idx_seq` the calibration query read 6 blocks in a fresh backend and 3 in the same session after one prior execution, while `idx_part` read 2 in both. `_bt_getroot` caches metapage contents in `rd_amcache`, which explains at most one block. The remaining difference was not traced to a specific call site, so Method B is specified as "run both probes twice in one session and use the second reading".
- **The `+1` in the density formula assumes every counted leaf carries a high key.** The rightmost leaf does not ([nbtree.h#P_HIKEY](../../../../raw/postgres-12/src/include/access/nbtree.h#L198-L219)). The error is one entry in the whole index and is inside the measured −0.03 to −0.14 point spread, but it was not isolated separately.
- **Internal-page counts are modelled with untruncated pivot tuples.** `_bt_truncate` can shrink a pivot when the leading key columns already distinguish the boundary ([nbtutils.c#_bt_truncate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L2082-L2093)), so Method A over- or under-counts internal pages by a few. Observed effect: +1 block on `idx_multi`, −1 on `idx_null`, −2 on `idx_dup`, and roughly −10 on the corrected `idx_var` estimate.
- **`pg_column_size` and out-of-line TOAST.** It reports the external compressed payload size for an on-disk-external datum ([tuptoaster.c#toast_datum_size](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L406-L458)) whereas `index_form_tuple` fetches and inlines that value ([indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L66-L110)). Keys wide enough to be externalised would exceed `BTMaxItemSize` anyway, but no fixture exercised the boundary.
- **No direct upstream test covers these estimates.** The pinned tree has no regression test that compares a modelled index size against a built one, and `pgstatindex` itself has limited coverage; the accuracy claims here rest entirely on the exact-pin fixtures described above.
- **Block sizes other than 8192 were not exercised.** The formulas read `current_setting('block_size')`, but every measurement used the default 8192, and `MAXALIGN` was assumed to be 8.
- **Half-dead pages were never produced.** No fixture in either run reached a non-zero `empty_pages`, because a half-dead page requires page deletion to be interrupted between `_bt_mark_page_halfdead` and `_bt_unlink_halfdead_page` ([nbtpage.c#_bt_pagedel](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1462-L1490)). The claim that Methods A and B lump half-dead pages in with deleted ones follows from the code path, not from measurement.
- **The `avg_leaf_density` predictor formula is this page's construction.** `ceil(leaf_pages * avg_leaf_density / fillfactor) + internal_pages + 1` is the natural reading of the density-versus-fillfactor heuristic as a size predictor, but upstream defines no such formula, so the head-to-head scores it against a plausible interpretation rather than a specified one.
- **The matrix varies scale, not seed.** The three repeats per cell are 200,000 / 500,000 / 1,000,000 rows with deterministic delete patterns; only the `random` fixture draws random values, and it used a single fixed `setseed(0.42)`. Error spread across different random draws at one scale was not measured.
- **The post-`ANALYZE` residual was not chased further.** Three of the six repaired cells still differ by one block, tracked to `tupleFract * totalrows` recording 18,337 index rows against a true 18,181; whether a higher `default_statistics_target` removes it was not tested.
- **Nothing was executed for the column rename.** No server ran the renamed statements. That only two `AS` labels, one comment and one index name moved is read off the two statements plus the pinned source, and "no number on this page moves" is an argument about which expressions changed, not a re-measurement. The renamed Method C sequence in particular was never run end to end, so the five renamed sites were not checked against a live `CREATE`/`DROP INDEX CONCURRENTLY`.
- **The byte column is still clamped while the percentage is not.** `wasted_space` keeps `greatest(actual_bytes - expected_blocks * bs, 0)`, so a row can print `0 bytes` beside a negative `wasted_space_pct` — `idx_dup` at −6.4% and `idx_var` at −4.6% are the two cells on this page where that happens. Unclamping was outside this correction's scope and was not measured, and v12's `pg_size_pretty` would not render a negative symmetrically in any case: its `half_rounded` macro is documented as "Divide by two and round towards positive infinity" ([dbsize.c#half_rounded](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L34-L35)), and this checkout carries no `dbsize` regression test to pin that behavior.
- **The `pg_stat_statements` consequences were derived, not observed.** No server was used to confirm that an existing entry keeps the old tag until eviction or reset, that the renamed utility statements land on new entries, or that the probe name is displayed as `$n` in the normalized `SELECT` text.
- **The vocabulary survey is a string search, not a semantic one.** The zero-occurrence claims for `system_views.sql`, `pg_proc.dat` and the contrib SQL scripts, the 24 doc-tree matches, and the absent `glossary.sgml` come from case-insensitive searches of this checkout; a column named for bloat in some other form of words would not have been caught.

## Source References

- [nbtsort.c#_bt_pagestate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L709-L734)
- [nbtsort.c#_bt_buildadd](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L836-L940)
- [nbtsplitloc.c#_bt_findsplitloc](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsplitloc.c#L126-L430)
- [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L55-L68)
- [nbtree.h#BTREE_DEFAULT_FILLFACTOR](../../../../raw/postgres-12/src/include/access/nbtree.h#L158-L171)
- [nbtree.c#btvacuumscan](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L956-L1099)
- [nbtree.c#btvacuumpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L1166-L1188)
- [nbtpage.c#_bt_page_recyclable](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L931-L963)
- [README#page-deletion](../../../../raw/postgres-12/src/backend/access/nbtree/README#L316-L334)
- [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597)
- [itup.h#IndexInfoFindDataOffset](../../../../raw/postgres-12/src/include/access/itup.h#L76-L90)
- [indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L39-L189)
- [heaptuple.c#heap_compute_data_size](../../../../raw/postgres-12/src/backend/access/common/heaptuple.c#L114-L167)
- [dbsize.c#pg_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L310-L336)
- [varlena.c#pg_column_size](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L5044-L5090)
- [system_views.sql#pg_stat_all_indexes](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L658-L672)
- [analyze.c#do_analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L607-L629)
- [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1771-L1830)
- [nbtsearch.c#_bt_readnextpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L1726-L1800)
- [nodeIndexonlyscan.c#IndexOnlyNext](../../../../raw/postgres-12/src/backend/executor/nodeIndexonlyscan.c#L118-L184)
- [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2863-L2907)
- [indexcmds.c#DefineIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L489-L622)
- [index.c#index_set_state_flags](../../../../raw/postgres-12/src/backend/catalog/index.c#L3314-L3403)
- [ruleutils.c#pg_get_indexdef](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L1088-L1115)
- [extension.c#execute_extension_script](../../../../raw/postgres-12/src/backend/commands/extension.c#L798-L817)
- [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365)
- [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L852-L897)
- [create_index.sgml#CONCURRENTLY](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L530-L633)
- [explain.sgml#BUFFERS](../../../../raw/postgres-12/doc/src/sgml/ref/explain.sgml#L167-L193)
- [queries.sgml#Column-Labels](../../../../raw/postgres-12/doc/src/sgml/queries.sgml#L1473-L1515)
- [queries.sgml#sort-by-output-column](../../../../raw/postgres-12/doc/src/sgml/queries.sgml#L1742-L1761)
- [ref/reindex.sgml#bloated](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L47-L57)
- [ref/copy.sgml#recover-the-wasted-space](../../../../raw/postgres-12/doc/src/sgml/ref/copy.sgml#L532-L541)
- [pgstattuple--1.4.sql#free_space](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L11-L16)
- [pgstatapprox.c#header](../../../../raw/postgres-12/contrib/pgstattuple/pgstatapprox.c#L1-L12)
- [pg_stat_statements.c#JumbleQuery](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L2402-L2435)
- [pg_stat_statements.c#pgss_store](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1139-L1231)
- [pg_stat_statements.c#pgss_ProcessUtility](../../../../raw/postgres-12/contrib/pg_stat_statements/pg_stat_statements.c#L1054-L1062)
- [scan.l#extended-comments](../../../../raw/postgres-12/src/backend/parser/scan.l#L427-L465)
- [scansup.c#truncate_identifier](../../../../raw/postgres-12/src/backend/parser/scansup.c#L177-L209)
- [pg_config_manual.h#NAMEDATALEN](../../../../raw/postgres-12/src/include/pg_config_manual.h#L22-L29)
- [parse_relation.c#errorMissingColumn](../../../../raw/postgres-12/src/backend/parser/parse_relation.c#L3308-L3379)
- [pg_proc.dat#pg_size_pretty](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L6896-L6903)
- [varlena.c#bttextcmp](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L1924-L1937)
- [postgres.c#log_statement](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1039-L1047)

- [nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L104-L114)
- [nbtree.h#BTNProcs](../../../../raw/postgres-12/src/include/access/nbtree.h#L379-L395)
- [nbtutils.c#btoptions](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L2027-L2031)
- [reloptions.c#btree-fillfactor](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L177-L185)
- [reloptions.c#vacuum_cleanup_index_scale_factor](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L423-L430)
- [nbtsort.c#_bt_load](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L1246-L1284)
- [analyze.c#do_analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L438-L466)
- [analyze.c#compute_index_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L771-L789)
- [analyze.c#subset-expression-statistics](../../../../raw/postgres-12/src/backend/commands/analyze.c#L821-L843)
- [analyze.c#examine_attribute](../../../../raw/postgres-12/src/backend/commands/analyze.c#L887-L893)
- [index.c#index_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2989)
- [index.c#index_update_stats](../../../../raw/postgres-12/src/backend/catalog/index.c#L2761-L2779)
- [analyze.c#tupleFract](../../../../raw/postgres-12/src/backend/commands/analyze.c#L771-L777)
- [analyze.c#subset-estimate](../../../../raw/postgres-12/src/backend/commands/analyze.c#L821-L827)
- [relcache.c#RelationSetNewRelfilenode](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L3527-L3541)
- [indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L66-L133)
- [varlena.c#pg_column_size](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L5044-L5089)
- [nbtsort.c#_bt_buildadd](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L856-L935)
- [nbtsort.c#high-key-truncation](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L947-L990)
- [nbtutils.c#_bt_truncate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L2116-L2201)
- [pgstat.c#pgstat_report_stat](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L803-L921)
- [pgstat.c#pgstat_beshutdown_hook](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L3073-L3094)
- [pgstat.c#pgstat_send](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L4341-L4360)
- [pgstat.c#backend_read_statsfile](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L5636-L5651)
- [pgstat.c#pgstat_clear_snapshot](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L5785-L5806)
- [stats.sql#wait_for_stats](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L27-L78)
- [stats.sql#writer-reconnect](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L146-L155)
- [pgstat.c#pgstat_recv_tabstat](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L5966-L5994)
- [pgstat.c#pgstat_recv_analyze](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6240-L6272)
- [pgstat.c#pgstat_recv_resetcounter](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L6093-L6121)
- [stats.sql#truncate-statistics](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L80-L136)
- [analyze.c#BuildRelationExtStatistics](../../../../raw/postgres-12/src/backend/commands/analyze.c#L576-L584)
- [system_views.sql#pg_stats](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L189-L197)
- [system_views.sql#pg_stats-visibility](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L247-L254)
- [system_views.sql#pg_stats_ext](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L256-L291)
- [configure.in#ICU](../../../../raw/postgres-12/configure.in#L730-L738)
- [configure.in#blocksize](../../../../raw/postgres-12/configure.in#L250-L265)
- [c.h#MAXALIGN](../../../../raw/postgres-12/src/include/c.h#L673-L697)
- [Makefile#GENERATED_HEADERS](../../../../raw/postgres-12/src/backend/catalog/Makefile#L51)
- [Makefile#genbki](../../../../raw/postgres-12/src/backend/catalog/Makefile#L79-L100)
- [dbsize.c#half_rounded](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L34-L35)
- [dbsize.c#pg_size_pretty](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L534-L571)
- [guc.c#statement_timeout-and-lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2397)
- [indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L121-L133)
- [nbtutils.c#_bt_truncate](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L2116-L2164)
- [system_views.sql:247](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L247-L291)
- [relcache.c:3527](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L3527-L3535)
- [pgstat.c:3083](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L3083-L3094)
- [pgstat.c:5978](../../../../raw/postgres-12/src/backend/postmaster/pgstat.c#L5978-L5986)
- [nbtsort.c:856](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsort.c#L856-L976)
- [reloptions.c:179](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L179-L185)

## Navigation

- [v12/index](../../index.md)
- [PostgreSQL 12 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [How pgstatindex Calculates B-Tree Index Statistics in PostgreSQL 12 (unverified)](how-pgstatindex-calculates-information.md)
- [B-Tree Leaf Density vs Fragmentation Impact on Index Scan I/O in PostgreSQL 12 (unverified)](leaf-density-vs-fragmentation-index-scan-io.md)
- [Planner Penalties for Bloated Indexes in PostgreSQL 12 (unverified)](../query-planning/bloated-indexes-query-planner.md)
- [How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 12 (unverified)](create-index-concurrently.md)
- [versions](../../../versions.md)
