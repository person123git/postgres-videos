---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: claude-opus-5-max 2026-08-31T16:02:19Z
---

# How Reliable the Catalog-Statistics Table and TOAST Bloat Query Is in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
  - [Prompt hygiene](#prompt-hygiene)
  - [The statement under review](#the-statement-under-review)
- [Answer](#answer)
  - [Verdict](#verdict)
  - [What the statement actually computes](#what-the-statement-actually-computes)
  - [How it was measured](#how-it-was-measured)
  - [The score](#the-score)
  - [Where it is exact](#where-it-is-exact)
  - [Five tables it never mentions](#five-tables-it-never-mentions)
  - [Four ways it reads low](#four-ways-it-reads-low)
  - [Three ways it reads high](#three-ways-it-reads-high)
  - [The per-tuple model, in bytes](#the-per-tuple-model-in-bytes)
  - [The TOAST half](#the-toast-half)
  - [What table_mb is and is not](#what-table_mb-is-and-is-not)
  - [The published WHERE clause](#the-published-where-clause)
  - [Locks, privileges, and cost](#locks-privileges-and-cost)
  - [Two defects that are not about accuracy](#two-defects-that-are-not-about-accuracy)
  - [When to trust it](#when-to-trust-it)
  - [How to reproduce](#how-to-reproduce)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 12, review and run measurements on how reliable this SQL is to measure table and TOAST bloat:

```sql
WITH constants AS (
    -- define some constants for sizes of things
    -- for reference down the query and easy maintenance
    SELECT current_setting('block_size')::numeric AS bs, 23 AS hdr, 8 AS ma
),
no_stats AS (
    -- screen out table who have attributes
    -- which dont have stats, such as JSON
    SELECT table_schema, table_name,
        n_live_tup::numeric as est_rows,
        pg_table_size(relid)::numeric as table_size
    FROM information_schema.columns
        JOIN pg_stat_user_tables as psut
           ON table_schema = psut.schemaname
           AND table_name = psut.relname
        LEFT OUTER JOIN pg_stats
        ON table_schema = pg_stats.schemaname
            AND table_name = pg_stats.tablename
            AND column_name = attname
    WHERE attname IS NULL
        AND table_schema NOT IN ('pg_catalog', 'information_schema')
    GROUP BY table_schema, table_name, relid, n_live_tup
),
null_headers AS (
    -- calculate null header sizes
    -- omitting tables which dont have complete stats
    -- and attributes which aren't visible
    SELECT
        hdr+1+(sum(case when null_frac <> 0 THEN 1 else 0 END)/8) as nullhdr,
        SUM((1-null_frac)*avg_width) as datawidth,
        MAX(null_frac) as maxfracsum,
        schemaname,
        tablename,
        hdr, ma, bs
    FROM pg_stats CROSS JOIN constants
        LEFT OUTER JOIN no_stats
            ON schemaname = no_stats.table_schema
            AND tablename = no_stats.table_name
    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        AND no_stats.table_name IS NULL
        AND EXISTS ( SELECT 1
            FROM information_schema.columns
                WHERE schemaname = columns.table_schema
                    AND tablename = columns.table_name )
    GROUP BY schemaname, tablename, hdr, ma, bs
),
data_headers AS (
    -- estimate header and row size
    SELECT
        ma, bs, hdr, schemaname, tablename,
        (datawidth+(hdr+ma-(case when hdr%ma=0 THEN ma ELSE hdr%ma END)))::numeric AS datahdr,
        (maxfracsum*(nullhdr+ma-(case when nullhdr%ma=0 THEN ma ELSE nullhdr%ma END))) AS nullhdr2
    FROM null_headers
),
table_estimates AS (
    -- make estimates of how large the table should be
    -- based on row and page size
    SELECT schemaname, tablename, bs,
        reltuples::numeric as est_rows, relpages * bs as table_bytes,
    CEIL((reltuples*
            (datahdr + nullhdr2 + 4 + ma -
                (CASE WHEN datahdr%ma=0
                    THEN ma ELSE datahdr%ma END)
                )/(bs-20))) * bs AS expected_bytes,
        reltoastrelid
    FROM data_headers
        JOIN pg_class ON tablename = relname
        JOIN pg_namespace ON relnamespace = pg_namespace.oid
            AND schemaname = nspname
    WHERE pg_class.relkind = 'r'
),
estimates_with_toast AS (
    -- add in estimated TOAST table sizes
    -- estimate based on 4 toast tuples per page because we dont have
    -- anything better.  also append the no_data tables
    SELECT schemaname, tablename,
        TRUE as can_estimate,
        est_rows,
        table_bytes + ( coalesce(toast.relpages, 0) * bs ) as table_bytes,
        expected_bytes + ( ceil( coalesce(toast.reltuples, 0) / 4 ) * bs ) as expected_bytes
    FROM table_estimates LEFT OUTER JOIN pg_class as toast
        ON table_estimates.reltoastrelid = toast.oid
            AND toast.relkind = 't'
),
table_estimates_plus AS (
-- add some extra metadata to the table data
-- and calculations to be reused
-- including whether we cant estimate it
-- or whether we think it might be compressed
    SELECT current_database() as databasename,
            schemaname, tablename, can_estimate,
            est_rows,
            CASE WHEN table_bytes > 0
                THEN table_bytes::NUMERIC
                ELSE NULL::NUMERIC END
                AS table_bytes,
            CASE WHEN expected_bytes > 0
                THEN expected_bytes::NUMERIC
                ELSE NULL::NUMERIC END
                    AS expected_bytes,
            CASE WHEN expected_bytes > 0 AND table_bytes > 0
                AND expected_bytes <= table_bytes
                THEN (table_bytes - expected_bytes)::NUMERIC
                ELSE 0::NUMERIC END AS bloat_bytes
    FROM estimates_with_toast
    UNION ALL
    SELECT current_database() as databasename,
        table_schema, table_name, FALSE,
        est_rows, table_size,
        NULL::NUMERIC, NULL::NUMERIC
    FROM no_stats
),
bloat_data AS (
    -- do final math calculations and formatting
    select current_database() as databasename,
        schemaname, tablename, can_estimate,
        table_bytes, round(table_bytes/(1024^2)::NUMERIC,3) as table_mb,
        expected_bytes, round(expected_bytes/(1024^2)::NUMERIC,3) as expected_mb,
        round(bloat_bytes*100/table_bytes) as pct_bloat,
        round(bloat_bytes/(1024::NUMERIC^2),2) as mb_bloat,
        table_bytes, expected_bytes, est_rows
    FROM table_estimates_plus
)
-- filter output for bloated tables
SELECT databasename, schemaname, tablename,
    can_estimate,
    est_rows,
    pct_bloat, mb_bloat,
    table_mb
FROM bloat_data
-- this where clause defines which tables actually appear
-- in the bloat chart
-- example below filters for tables which are either 50%
-- bloated and more than 20mb in size, or more than 25%
-- bloated and more than 4GB in size
WHERE ( pct_bloat >= 10 AND mb_bloat >= 10 )
    OR ( mb_bloat >= 100 )
ORDER BY pct_bloat DESC;
```

### Prompt hygiene

The prompt was corrected before filing, at the asker's request. Four changes, and nothing else:

| As written | As restated | Why |
|---|---|---|
| `in postgresql 12` | `In PostgreSQL 12` | sentence-initial capital; product name spelling |
| `how reliable is this sql` | `how reliable this SQL is` | an embedded question does not invert subject and verb |
| `sql`, `toast` | `SQL`, `TOAST` | initialisms |
| `bloat :` | `bloat:` | stray space before the colon |

The SQL body is reproduced byte for byte, comments and typos included, because it is the object under review.

### The statement under review

Everything below refers to the statement above, unmodified. A second copy with the final `WHERE` clause removed was derived mechanically from the same file so that every fixture could be scored, and the 4,962-byte CTE chain shared by the two copies was checked to be byte-identical (SHA-256 `e523590dec04e760f2c2e8bcc890a5d8330cde5e0c98e7c4a8927e60e6aa17d6`). Every number in this page therefore comes out of the asker's own arithmetic.

## Answer

### Verdict

**It is a usable screen and a bad measurement.** On 21 scored fixtures its bloat percentage lands within 1 point of what a real `VACUUM FULL` reclaimed on 13 of them, and its mean absolute error is 9.47 points — slightly better than the exact `pgstattuple`'s own `dead + free` reading against the same rewrites (10.79 points). But its errors are not noise: they are systematic, they run in both directions, and the worst of them are silent.

The four things to know before using it on PostgreSQL 12:

1. **It can report `0` when half the table is reclaimable.** A table deleted but not yet vacuumed or re-analyzed read `pct_bloat = 0` against a rewrite that returned 50.00%. The estimate is only as fresh as `pg_class.relpages` and `pg_class.reltuples`, which are updated by `VACUUM`, `ANALYZE`, and a few DDL commands, not by DML ([catalogs.sgml#relpages](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L1759-L1781)).
2. **It silently drops whole classes of relation.** Materialized views, partitioned parents, any table with one `STATISTICS 0` column, and any never-analyzed table produce either no row at all or a row with `pct_bloat = NULL` that the published `WHERE` clause then discards. Three fixtures holding 25.34 MB, 25.38 MB, and 31.88 MB, with 50.00% to 74.99% reclaimable, never produced a number at all.
3. **It invents bloat on healthy tables.** Column alignment padding it cannot see, page-packing remainders it does not model, and `fillfactor` it ignores produced `+21`, `+33`, and `+31` points of bloat on three fixtures a rewrite could not shrink at all.
4. **One locked table kills the whole report.** The `no_stats` branch calls `pg_table_size()`, which opens each relation with `AccessShareLock` ([dbsize.c#pg_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L450-L467)). With an `AccessExclusiveLock` held on one 25.38 MB fixture, the statement died at `lock_timeout` instead of returning the 11 rows it returns unlocked.

As a triage screen against "a rewrite would return at least 10 MB and at least 25%", it scored **9 true positives, 2 false positives, 5 false negatives, 9 true negatives** over 25 fixtures.

### What the statement actually computes

It is a two-branch report, and the branches do not measure the same thing.

**Branch 1, `can_estimate = true`** — a catalog-only model. For each `relkind = 'r'` relation with complete column statistics:

```text
actual   = relpages * bs + toast.relpages * bs
modelled = ceil(reltuples * T / (bs - 20)) * bs + ceil(toast.reltuples / 4) * bs
bloat    = greatest(actual - modelled, 0)
T        = MAXALIGN(MAXALIGN(23) + sum((1 - null_frac) * avg_width))
           + max(null_frac) * MAXALIGN(24 + count(null_frac <> 0) / 8)
           + 4
```

The `23` is `SizeofHeapTupleHeader`, which the pinned header labels in a comment as 23 bytes ([htup_details.h#HeapTupleHeaderData](../../../../raw/postgres-12/src/include/access/htup_details.h#L152-L184)); the trailing `4` is `sizeof(ItemIdData)`, the line pointer ([itemid.h#ItemIdData](../../../../raw/postgres-12/src/include/storage/itemid.h#L25-L30)); `ma = 8` is the `MAXIMUM_ALIGNOF` this build was configured with, applied through [c.h#MAXALIGN](../../../../raw/postgres-12/src/include/c.h#L679-L689) — the value is substituted by `configure` and so is not a constant in the pinned tree ([pg_config.h.in:797](../../../../raw/postgres-12/src/include/pg_config.h.in#L797)), but the measured tuple geometry on this server is consistent with 8, since a `(bigint, int)` row has `t_len = 36 = MAXALIGN(23) + 12`; and `bs` comes from the `PGC_INTERNAL` preset `block_size`, which is fixed at `BLCKSZ` and cannot be set ([guc.c#block_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2879-L2888)).

The engine's real per-tuple cost is `MAXALIGN(t_len) + 4`, where `t_len = MAXALIGN(23 + BITMAPLEN(natts) if any NULL) + heap_compute_data_size(...)` ([heaptuple.c#heap_form_tuple](../../../../raw/postgres-12/src/backend/access/common/heaptuple.c#L1020-L1095)), and `heap_compute_data_size` advances the offset with `att_align_datum` for every attribute, so inter-column padding is part of the tuple ([heaptuple.c#heap_compute_data_size](../../../../raw/postgres-12/src/backend/access/common/heaptuple.c#L114-L167)).

**Branch 2, `can_estimate = false`** — a physical size with no estimate at all. `pg_table_size(relid)` sums every fork of the heap *plus* the TOAST heap *plus* the TOAST index ([dbsize.c#calculate_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L380-L408), [dbsize.c#calculate_toast_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L338-L378)), and `est_rows` comes from the statistics collector's `n_live_tup` rather than `reltuples` ([monitoring.sgml#n_live_tup](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2773-L2776)). `pct_bloat` and `mb_bloat` are `NULL` on this branch by construction.

### How it was measured

An isolated 12.2 server was built out of tree from `raw/postgres-12/` at the pin (`REL_12_2`), with `contrib/pgstattuple` installed, `autovacuum = off`, `fsync = off`, `shared_buffers = 256MB`, and `default_statistics_target = 100`. Twenty-six relations in one schema, each isolating one suspected defect, were loaded deterministically, analyzed, mutated, and re-analyzed — except two deliberately left stale. Twenty-five of them are heaps or materialized views and so can be measured by `pgstattuple`; the twenty-sixth is a partitioned parent.

Three independent readings were then taken for every fixture:

| Reading | Source | What it means |
|---|---|---|
| `estimator_pct` | the asker's statement | the catalog model's answer |
| `pgstattuple_pct` | `100 * (dead_tuple_len + free_space) / table_len`, main heap plus TOAST heap | the asker's chosen ground truth, exact per-page |
| `rewrite_pct` | bytes before minus bytes after a real `VACUUM FULL` | what a rebuild actually returns |

`pgstattuple` was chosen as ground truth by the asker. It reads `t_len` per visible and non-visible tuple and `PageGetHeapFreeSpace()` per block, and sets `table_len` from the block count ([pgstattuple.c#pgstat_heap](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L315-L404)), so `table_len` is always larger than its three components; the extension's own documentation says the difference is page overhead, line pointers, and alignment padding ([pgstattuple.sgml#note](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L123-L131)). Because that footnote is exactly where the two estimates disagree, the `VACUUM FULL` reading was added as an arbiter and is reported beside both. It is the third column that decides the disputed rows, and it changes the ranking: against the rewrite, `pgstattuple` is off by up to 86.41 points.

`pgstattuple` accepts `RELKIND_TOASTVALUE`, so the TOAST heap could be measured directly ([pgstattuple.c#pgstat_relation](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L239-L305)). It refuses a partitioned table — `ERROR: "t17_part" (partitioned table) is not supported` was reproduced — so the partitioned parent is reported by presence, not by percentage.

### The score

Twenty-five fixtures. `rewrite_pct` is the arbiter; `est − rewrite` is the estimator's error in percentage points. Rows are sorted by that error.

| Fixture | Shape | rewrite % | pgstattuple % | estimator % | est − rewrite |
|---|---|---|---|---|---|
| `t06_del50_stale` | 50% deleted, no `VACUUM`, no re-`ANALYZE` | 50.00 | 40.96 | **0** | **−50.00** |
| `t03_wide_plain` | 2,700-byte rows, 2 per page, never modified | 0.00 | 32.76 | **33** | **+33.00** |
| `t04_ff70_clean` | `fillfactor = 70`, freshly loaded | 0.00 | 30.38 | **31** | **+31.00** |
| `t08_nullable_bloat` | 12 columns, `null_frac = 1.0`, 50% deleted + `VACUUM` | 54.05 | 49.86 | **29** | **−25.05** |
| `t02_clean_padded` | `smallint`/`bigint` alternation, never modified | 0.00 | 0.41 | **21** | **+21.00** |
| `t18_ff70_bloat` | `fillfactor = 70` and 50% deleted + `VACUUM` | 50.00 | 61.87 | 65 | +15.00 |
| `t22_toast_2chunk` | 2,100 external bytes/row, 75% deleted + `VACUUM` | 74.98 | 79.25 | 63 | −11.98 |
| `t15_inh_parent` | inheritance parent, 50% deleted + `VACUUM` | 50.00 | 45.47 | 41 | −9.00 |
| `t11_json` | `json` column, never modified | 0.00 | 0.86 | 1 | +1.00 |
| `t19_mixed` | six mixed types, TOAST emptied, 40% deleted | 74.99 | 74.19 | 74 | −0.99 |
| `t15_inh_child` | inheritance child, untouched | 49.54 | 41.42 | 50 | +0.46 |
| `t14_dropped_col` | 500-byte column dropped after load | 92.42 | **6.01** | 92 | **−0.42** |
| `t10_toast_bloat` | 6,400 external bytes/row, 75% deleted + `VACUUM` | 74.99 | 79.43 | 75 | +0.01 |
| `t01_clean_narrow` | `bigint, int`, never modified | 0.00 | 0.32 | 0 | 0.00 |
| `t05_del50_vac` | 50% deleted + `VACUUM` | 50.00 | 45.47 | 50 | 0.00 |
| `t07_upd_dead` | every row updated once, non-HOT, not vacuumed | 50.00 | 40.96 | 50 | 0.00 |
| `t09_toast_clean` | 31 MB TOAST, never vacuumed, nothing deleted | 0.00 | 19.47 | 0 | 0.00 |
| `t16_mv_src` | 50% deleted + `VACUUM` | 50.00 | 45.47 | 50 | 0.00 |
| `t17_part_p1` | range partition, 50% deleted + `VACUUM` | 50.00 | 45.47 | 50 | 0.00 |
| `t17_part_p2` | range partition, 50% deleted + `VACUUM` | 50.00 | 45.47 | 50 | 0.00 |
| `t20_grown` | grew 6x since the last `ANALYZE` | 0.00 | 0.32 | 0 | 0.00 |
| `t12_stats0` | one `STATISTICS 0` column, 50% deleted + `VACUUM` | 50.00 | 45.47 | *no value* | *not reported* |
| `t16_mv` | materialized view, 50% of rows deleted + `VACUUM` | 50.00 | 45.47 | *no row* | *not reported* |
| `t21_toast_stats0` | `STATISTICS 0` plus 75% TOAST deleted | 74.99 | 79.43 | *no value* | *not reported* |
| `t13_empty` | zero rows | — | — | *no value* | *not reported* |

Summary over the 21 rows where both the estimator and the rewrite produced a number:

| Metric | Estimator vs rewrite | `pgstattuple` vs rewrite |
|---|---|---|
| rows scored | 21 | 24 |
| minimum error | −50.00 | −86.41 |
| maximum error | +33.00 | +32.76 |
| mean absolute error | **9.47** | **10.79** |
| within 1 point | 13 | — |
| within 5 points | 13 | 16 |
| worse than 20 points | 5 | 3 |

As a screen, using the published `WHERE` clause as the decision and "a rewrite returns ≥ 10 MB and ≥ 25%" as the truth:

| | worth rebuilding | not worth it |
|---|---|---|
| **flagged** | 9 (`t05`, `t07`, `t10`, `t14`, `t15_inh_parent`, `t16_mv_src`, `t18`, `t19`, `t22`) | 2 (`t03_wide_plain`, `t04_ff70_clean`) |
| **not flagged** | 5 (`t06`, `t08`, `t12`, `t16_mv`, `t21`) | 9 |

### Where it is exact

Thirteen of the 21 scored rows came within 1 point of the rewrite. Seven of those are the easy shape — fixed-width columns, no nulls, `fillfactor = 100`, statistics refreshed after the change, and a per-tuple size that divides a page nearly evenly — and on that shape the model is not approximately right, it is arithmetically right. For `t05_del50_vac` it produced 44.02 bytes per tuple against a real on-page cost of `MAXALIGN(36) + 4 = 44`, and `pct_bloat = 50` against `rewrite_pct = 50.00`.

Two rows deserve separate mention because the estimator beat the ground truth:

- **`t14_dropped_col`, +85.99 points better than `pgstattuple`.** A 500-byte column was dropped after loading. `pgstattuple` still counts each surviving tuple at its full 540 bytes and reported 6.01% — but `VACUUM FULL` reclaimed **92.42%** (35,110,912 → 2,662,400 bytes), because the rewrite reconstructs every tuple from Datums and nulls out dropped attributes ([heapam_handler.c#reform_and_rewrite_tuple](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2508-L2548)). The estimator reads `pg_stats` for the *live* columns only, so it modelled 44.12 bytes per tuple and reported **92**. Off by 0.42 points where the exact function was off by 86.41.
- **`t10_toast_bloat`, +0.01 points.** The `/4` TOAST rule predicted `ceil(4000 / 4) * 8192 = 8,192,000` bytes for the rewritten TOAST heap, and the rewrite produced exactly 8,192,000 bytes. See [The TOAST half](#the-toast-half).

### Five tables it never mentions

| Fixture | Size | Reclaimable by rewrite | Why it disappears |
|---|---|---|---|
| `t16_mv` (materialized view) | 25.34 MB | 50.00% | no row anywhere |
| `t12_stats0` | 25.38 MB | 50.00% | `can_estimate = false`, `pct_bloat` `NULL` |
| `t21_toast_stats0` | 31.88 MB | 74.99% | `can_estimate = false`, `pct_bloat` `NULL` |
| `t13_empty` | 0 bytes | n/a | `can_estimate = false` |
| `t17_part` (partitioned parent) | 25.34 MB across 2 partitions | 50.00% per partition | no row for the parent |

The mechanisms are all in the pinned catalogs:

- **Materialized views are excluded twice.** `information_schema.columns` restricts itself to `relkind IN ('r','v','f','p')` ([information_schema.sql#columns](../../../../raw/postgres-12/src/backend/catalog/information_schema.sql#L778-L797)), so the `EXISTS` gate in `null_headers` rejects a matview, and `table_estimates` then filters `relkind = 'r'` anyway. Measured: 2 rows in `pg_stats`, 1 row in `pg_stat_all_tables`, **0** rows in `information_schema.columns`, 0 rows in the report.
- **Partitioned parents are excluded twice too.** `pg_stat_all_tables` restricts itself to `relkind IN ('r','t','m')` ([system_views.sql#pg_stat_all_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L552-L581)), so `'p'` cannot reach `no_stats`, and `relkind = 'r'` drops it from the estimated branch. Its partitions are reported individually, which is arguably the right unit — but nothing in the output tells you an aggregate is missing.
- **One `STATISTICS 0` column routes an entire table to the null branch.** `examine_attribute` returns `NULL` when `attstattarget == 0`, so no `pg_statistic` row is written ([analyze.c#examine_attribute](../../../../raw/postgres-12/src/backend/commands/analyze.c#L878-L893)). The `no_stats` CTE then matches on `attname IS NULL` for that one column and the table loses its estimate entirely.
- **An empty table has no column statistics at all.** `do_analyze_rel` computes and stores per-column statistics only inside `if (numrows > 0)` ([analyze.c:512](../../../../raw/postgres-12/src/backend/commands/analyze.c#L512)); the `vac_update_relstats` call that refreshes `relpages`/`reltuples` sits outside that block ([analyze.c#vac_update_relstats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L587-L605)). Measured: both columns of `t13_empty` have `attstattarget = -1` and no `pg_stats` row.

The `no_stats` CTE's stated purpose does not fire on this major. Its comment says it screens out "attributes which dont have stats, such as JSON", but a `json` column **does** get a `pg_statistic` row in 12.2: `json` has no default `=` operator and no opclass (measured: 0 equality operators, 0 opclasses, against 1 for `jsonb`), so `std_typanalyze` falls through to `compute_trivial_stats` ([analyze.c#std_typanalyze](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1649-L1718)), which still records `stanullfrac` and `stawidth` ([analyze.c#compute_trivial_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1721-L1800)). Measured on `t11_json`: `null_frac = 0`, `avg_width = 54`, `n_distinct = 0`, and `most_common_vals`, `histogram_bounds`, `correlation` all `NULL`. `can_estimate` was `true` and the estimate was accurate (+1.00 point). The branch that exists to catch JSON catches empty tables and `STATISTICS 0` columns instead.

### Four ways it reads low

**1. Stale `pg_class` — up to −50.00 points, and the failure is invisible.** `t06_del50_stale` and `t05_del50_vac` were built and deleted identically; the only difference is that `t05` was then vacuumed and re-analyzed and `t06` was neither. `t05` read 50 against a 50.00% rewrite. `t06` read **0** against the same 50.00% rewrite, because `reltuples` was still 600,000 and `relpages` still 3,243, so `modelled ≈ actual`. Both `relpages` and `reltuples` are documented as planner estimates refreshed by `VACUUM`, `ANALYZE`, and some DDL ([catalogs.sgml#relpages](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L1759-L1781)); `vac_update_relstats` is their shared writer ([vacuum.c#vac_update_relstats](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1116-L1170)). `TRUNCATE` and rewriting DDL zero them through `RelationSetNewRelfilenode` ([relcache.c#RelationSetNewRelfilenode](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L3419-L3542)). Nothing in the output distinguishes "no bloat" from "no recent statistics": both print `pct_bloat = 0`.

**2. The `nullhdr2` term over-charges nulls — −25.05 points.** `t08_nullable_bloat` has 12 columns; after the delete, every surviving row has `NULL` in 11 of them, so `null_frac = 1.0` and `datawidth` collapses to `8.00`. The model then computes

```text
nullhdr  = 23 + 1 + (11 / 8) = 25          -- integer division, so 1
nullhdr2 = max(null_frac) * MAXALIGN(25) = 1.0 * 32 = 32
T        = MAXALIGN(8 + 24) + 32 + 4 = 68
```

against a real tuple of `t_len = 40` costing `MAXALIGN(40) + 4 = 44` on the page. Measured per-tuple: **68.02 modelled, 40.00 real `t_len`**. The engine's actual null-bitmap charge is the difference between `MAXALIGN(23 + BITMAPLEN(12))` and `MAXALIGN(23)`, that is 32 − 24 = **8 bytes**, and only for rows that have a null at all ([heaptuple.c#heap_form_tuple](../../../../raw/postgres-12/src/backend/access/common/heaptuple.c#L1020-L1095)). The model charges a whole second aligned header, 24 bytes too many, which inflates `modelled` by 55% and drags a 54.05% truth down to a reported 29 — below the report's own 10 MB threshold, so the row vanished from the filtered output as well.

Note also that `maxfracsum` is `MAX(null_frac)`, not a sum: a single mostly-null column sets the multiplier for the entire table.

**3. Inherited statistics are double-counted — −9.00 points.** `t15_inh_parent` matches `t05_del50_vac` in content and in size (both 26,574,848 bytes) and differs only in having a child table. `analyze_rel` runs `do_analyze_rel` once for the relation and again for the inheritance tree when `relhassubclass` is set ([analyze.c#analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L118-L270)), and `pg_stats` exposes `stainherit` as a column without filtering on it ([system_views.sql#pg_stats](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L189-L252)). So `null_headers` sums `(1 - null_frac) * avg_width` over both copies. Measured: **4 `pg_stats` rows for 2 live attributes** (2 inherited, 2 own) and `datawidth = 24.00` where the identical child read `12.00`. Modelled per-tuple went 44.02 → **52.00**, and `pct_bloat` went 50 → **41** on the same 50.00% truth. A parent with more columns loses proportionally more.

**4. The `/4` TOAST rule assumes a chunk geometry that is not universal — −11.98 points.** See [The TOAST half](#the-toast-half).

### Three ways it reads high

**1. Column alignment padding — +21.00 points on a table with nothing wrong with it.** `t02_clean_padded` alternates `smallint` and `bigint`. `avg_width` is per column, so `datawidth = 2+8+2+8+2+8 = 30.00`, and the model produces `MAXALIGN(30 + 24) + 4 = 60` bytes per tuple. The real tuple pads each `bigint` to an 8-byte boundary, giving 48 data bytes, `t_len = 72`, and `MAXALIGN(72) + 4 = 76` on the page. Measured: **60.00 modelled against 72.00 real `t_len`**. The full chain checks out: `ceil(400000 * 60 / 8172) = 2937` pages = 24,059,904 bytes = 22.945 MB modelled against 29.211 MB actual, `mb_bloat = 6.27`, `pct_bloat = 21`. `VACUUM FULL` reclaimed **0.00%** and `pgstattuple` agreed at 0.41%. This one is a pure artefact of the model, and only the report's 10 MB floor kept it out of the filtered output.

**2. Page-packing remainders — +33.00 points.** `t03_wide_plain` stores 2,700-byte payloads with `STORAGE PLAIN`, so each tuple costs 2,740 bytes on the page and exactly **2** fit in the 8,168 usable bytes. The model divides total tuple bytes by `bs - 20 = 8172` with no flooring, implying **2.982** tuples per page, and reports 33% bloat. `VACUUM FULL` reclaimed **0.00%**: a rewrite lays the rows out identically. Two separate errors are hiding here — the missing floor, and the fact that `bs - 20` overstates the usable space, since the page header is 24 bytes ([bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L212-L216)) and `PageGetHeapFreeSpace` further deducts a line pointer and returns 0 once `MaxHeapTuplesPerPage` line pointers exist ([bufpage.c#PageGetHeapFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L649-L715), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597)). Note that `pgstattuple` calls this 33% "free" too — it is genuinely free space, it is just not reclaimable. Re-measured after the rewrite, `pgstattuple` reported **10,736,000 free bytes of 32,768,000, i.e. 32.76% again**, unchanged to two decimals. This is the row where the asker's chosen ground truth and the estimator are both 33 points from what a rebuild delivers.

**3. `fillfactor` is ignored — +31.00 points clean, +15.00 points bloated.** `t04_ff70_clean` was loaded at `fillfactor = 70` and never modified. Every insert reserves `BLCKSZ * (100 - fillfactor) / 100` bytes ([rel.h#RelationGetTargetPageFreeSpace](../../../../raw/postgres-12/src/include/utils/rel.h#L289-L309)), enforced in `RelationGetBufferForTuple` ([hio.c#RelationGetBufferForTuple](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L320-L350)) and in the batch insert path ([heapam.c#heap_multi_insert](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L2105-L2200)). The model has no `fillfactor` term, so it expects 100% packing and calls the entire 30% reserve bloat. A rewrite reclaims none of it, because `raw_heap_insert` reserves the same space in the new heap ([rewriteheap.c#raw_heap_insert](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L628-L700)). Re-measured after the rewrite, `t04_ff70_clean` reported **11,578,928 free bytes of 38,109,184, i.e. 30.38% again**. On `t18_ff70_bloat`, which has both a 70 fillfactor and 50% deleted rows, the two effects compose: 65 reported against 50.00 reclaimed.

### The per-tuple model, in bytes

The model's per-tuple size `T` is recoverable from the published `expected_mb`, which makes the errors above directly attributable. Measured on the same run:

| Fixture | modelled bytes/tuple | real `t_len` | error |
|---|---|---|---|
| `t01_clean_narrow` | 44.01 | 36.00 (`+4` lp, `MAXALIGN` → 44) | exact |
| `t02_clean_padded` | 60.00 | 72.00 (→ 76) | **−16 (padding)** |
| `t03_wide_plain` | 2740.69 | 2732.00 (→ 2740) | exact per tuple; the loss is page flooring |
| `t08_nullable_bloat` | 68.02 | 40.00 (→ 44) | **+24 (null header)** |
| `t11_json` | 92.02 | 82.63 (→ ~88) | +4 |
| `t14_dropped_col` | 44.12 | 540.00 (→ 544) | −500, and correct, because a rewrite drops the column |
| `t15_inh_parent` | 52.00 | 36.00 (→ 44) | **+8 (inherited stats counted twice)** |
| `t19_mixed` | 121.99 | 105.75 (→ ~112) | +10 |

`avg_width` is the in-heap width, not the logical width: `compute_scalar_stats` adds `VARSIZE_ANY(...)` of the stored datum and its comment states "if the value is toasted, we use the toasted width" ([analyze.c#compute_scalar_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L2162-L2246)). That is the right choice for this model — an external value occupies 18 bytes in the heap — and it means `datawidth` does not double-count TOAST.

### The TOAST half

The `/4` rule is better than its own comment claims, and its failure mode is precise. Four chunk tuples per page is not a guess: `TOAST_MAX_CHUNK_SIZE` is derived so that `EXTERN_TUPLES_PER_PAGE = 4` maximum-size chunks fit on a page ([tuptoaster.h#TOAST_MAX_CHUNK_SIZE](../../../../raw/postgres-12/src/include/access/tuptoaster.h#L77-L96)), which on this build is 1,996 data bytes per chunk. But `toast_save_datum` splits a value into `ceil(size / 1996)` chunks, and only the last one is short ([tuptoaster.c#TOAST_MAX_CHUNK_SIZE](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L1636-L1693)), so the ratio of chunks to pages depends on the payload size:

| Fixture | payload | chunks/row | chunk lengths | TOAST before | rewrite → | `/4` predicts | error |
|---|---|---|---|---|---|---|---|
| `t10_toast_bloat` | 6,400 B | 4 | 1996 ×3 + 412 | 32,768,000 | **8,192,000** | 8,192,000 | **exact** |
| `t21_toast_stats0` | 6,400 B | 4 | 1996 ×3 + 412 | 32,768,000 | **8,192,000** | 8,192,000 | exact (but the row is not reported) |
| `t19_mixed` | 6,400 B | 4 | 1996 ×3 + 412 | 49,152,000 | **8,192** | 8,192 | **exact** |
| `t22_toast_2chunk` | 2,100 B | 2 | 1996 + 104 | 32,768,000 | **8,192,000** | 12,288,000 | **+4,096,000 (1.5x)** |

With 6,400-byte payloads, three full chunks plus one 412-byte tail happen to be exactly four tuples per page, and the rule is exact to the byte. With 2,100-byte payloads the tail chunk is only 104 bytes, six chunks share a page, and the rule over-predicts the rewritten size by half — which is the whole −11.98-point error on `t22_toast_2chunk`. Chunk lengths were read directly: `t09_toast_clean` holds **12,000 chunks of 1,996 bytes and 4,000 of 412**, for 4,000 rows. Its TOAST heap reads 6,416,000 free bytes of 32,768,000 — **19.58%** — and re-measuring after `VACUUM FULL` returned the same 6,416,000, so that reading is chunk geometry, not recoverable space.

The bigger TOAST problem is not the divisor. **`table_bytes` omits the TOAST heap entirely until something vacuums it.** `t09_toast_clean` is a 31 MB table:

```text
toast relpages   = 0            toast actual bytes = 32,768,000
toast reltuples  = 0            reported table_mb  = 0.203
```

`ANALYZE` never touches the TOAST relation's `pg_class` row — `do_analyze_rel` calls `vac_update_relstats` for `onerel` and its indexes only ([analyze.c#vac_update_relstats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L587-L629)) — and `vacuum_rel` recurses into the TOAST relation with a comment that says so explicitly: "analyze" will not get done on the toast table ([vacuum.c#vacuum_rel](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1843-L1866)). Autovacuum reaches TOAST relations in a second pass that ignores analyze and only vacuums them when `n_dead_tuples` exceeds the threshold or wraparound forces it ([autovacuum.c#RELKIND_TOASTVALUE](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2138-L2192), [autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2958-L3081)). An insert-only table produces no dead TOAST chunks, so on a real cluster its TOAST `relpages` can stay 0 indefinitely. For such a table this report understates the size by the whole TOAST heap — here by a factor of 155 — and, because `expected_bytes` omits the same relation, it reports `pct_bloat = 0`, which happens to be right (the rewrite reclaimed 0.00%) for entirely the wrong reason.

One more measured detail: `t19_mixed`'s TOAST heap held **4 live chunks in 6,000 pages** and plain `VACUUM` could not truncate it, because the single surviving toasted row (`id = 300000`, excluded from the delete by `id < 300000`) sits in the last pages. `VACUUM FULL` then took it to one page. The estimator got this right — `ceil(4 / 4) * 8192 = 8192` — and reported 74 against a 74.99% rewrite.

### What table_mb is and is not

`table_mb` is not the table's size, and it is not consistent between the two branches. Measured for every fixture, `est_table_bytes − pg_table_size()` was negative in all 24 cases:

| Fixture | main fork | main + TOAST heap | `pg_table_size()` | reported `table_mb` |
|---|---|---|---|---|
| `t01_clean_narrow` | 26,574,848 | 26,574,848 | 26,599,424 | 25.344 |
| `t09_toast_clean` | 212,992 | 32,980,992 | 33,406,976 | **0.203** |
| `t20_grown` | 26,574,848 | 26,574,848 | 26,599,424 | **4.227** |
| `t10_toast_bloat` | 212,992 | 32,980,992 | 33,423,360 | 31.453 |
| `t12_stats0` (null branch) | 26,574,848 | 26,574,848 | 26,607,616 | **25.375** |
| `t21_toast_stats0` (null branch) | 212,992 | 32,980,992 | 33,423,360 | **31.875** |

Three separate discrepancies:

1. **Forks are missing on the estimated branch.** `relpages` counts the main fork only, so the FSM and VM are excluded (24,576 to 40,960 bytes per fixture here), and the TOAST index is excluded as well (442,368 bytes on `t10_toast_bloat`).
2. **The two branches use different bases.** `t12_stats0` reports **25.375 MB** where the same table on the estimated branch would report 25.344, and `t21_toast_stats0` reports **31.875** against 31.453, because `pg_table_size()` includes FSM, VM, and the TOAST index. Two rows of the same report are not comparable.
3. **`relpages` staleness propagates into the size.** `t20_grown` grew 6x since its last `ANALYZE` and reports **4.227 MB** for a 25.34 MB table. The `mb_bloat` figure that the `WHERE` clause thresholds against is derived from this same stale number.

### The published WHERE clause

Three problems, all measured.

**The comment does not match the code.** The comment says the example "filters for tables which are either 50% bloated and more than 20mb in size, or more than 25% bloated and more than 4GB in size". The code is `(pct_bloat >= 10 AND mb_bloat >= 10) OR (mb_bloat >= 100)`.

**No `can_estimate = false` row can ever pass it.** On that branch `expected_bytes` is `NULL`, so `bloat_bytes` is `0`, `pct_bloat` and `mb_bloat` are `NULL`, and every comparison is `NULL`. Measured: all four such rows evaluated the filter to `NULL`, not `true`. The `UNION ALL` that appends them, and the comment "also append the no_data tables", buy nothing in the default configuration — a 31.88 MB table with 74.99% reclaimable was assembled, carried through six CTEs, and then dropped.

**Over-estimates cannot be seen and under-estimates cannot be measured.** `bloat_bytes` is clamped to `0` unless `expected_bytes <= table_bytes`, so the report can never show a negative reading. On `t02_clean_padded` and `t04_ff70_clean` — where the model over-shoots the physical size for structural reasons — the clamp is what turns a diagnosable modelling error into a plausible-looking bloat number.

### Locks, privileges, and cost

**Locks: one table can kill the report.** `pg_table_size()` opens the relation with `AccessShareLock` and closes it immediately ([dbsize.c#pg_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L450-L467)), so the locks do not accumulate — a sweep of 24 relations left 0 relation locks held. But the acquisition still blocks. Measured with `lock_timeout = 4s`:

| Lock held by another session | Report outcome |
|---|---|
| `AccessExclusiveLock` on `f.t12_stats0` (null branch) | waits for `AccessShareLock` on `f.t12_stats0`, then `ERROR: canceling statement due to lock timeout` |
| `AccessExclusiveLock` on `f.t13_empty` (null branch, 0 bytes) | same error |
| `AccessExclusiveLock` on `f.t05_del50_vac` (estimated branch) | **no wait**, 11 rows returned |
| no lock | 11 rows returned |

So the exposure is exactly the set of tables that reach `pg_table_size` — and that set includes every empty and never-analyzed table in the database. An `ALTER TABLE`, `TRUNCATE`, `REINDEX`, or `VACUUM FULL` on one of them loses the whole report. `pg_table_size` is at least crash-safe against concurrent drops: it uses `try_relation_open` and returns `NULL` rather than erroring if the relation is gone ([dbsize.c#pg_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L450-L467)).

Recommended session-scoped guards for a production run, both `PGC_USERSET` so they need neither restart nor reload:

```sql
SET /* wiki_bloat_query_guards */ lock_timeout = '2s';
SET /* wiki_bloat_query_guards */ statement_timeout = '60s';
```

**Privileges: a restricted role gets a near-empty report and no warning.** Both source views gate on privileges — `pg_stats` on `has_column_privilege(...)` ([system_views.sql#pg_stats](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L189-L252)) and `information_schema.columns` on `pg_has_role(c.relowner, 'USAGE') OR has_column_privilege(...)` ([information_schema.sql#columns](../../../../raw/postgres-12/src/backend/catalog/information_schema.sql#L778-L797)). Measured: a role with `USAGE` on the schema and `SELECT` on exactly one of 26 tables ran the statement successfully and got **one row**. It saw 2 `pg_stats` rows and 1 table in `information_schema.columns`. A monitoring role provisioned per-table will report a clean database.

**Cost: dominated by `information_schema.columns`, not by `pg_table_size`.** Measured wall-clock over three runs each:

| Database shape | tables reaching `pg_table_size` | run time |
|---|---|---|
| 27 user tables | 6 | 36.4 / 31.6 / 37.4 ms |
| 427 user tables, none analyzed | 406 | 184.8 / 164.0 / 149.7 ms |
| 427 user tables, all analyzed | 3 | 215.7 / 224.4 / 224.6 ms |
| back to 27 user tables | 3 | 32.4 / 33.9 / 32.1 ms |

Analyzing everything made the statement **slower** — from 149.7-184.8 ms to 215.7-224.6 ms — even though it cut the `pg_table_size` calls from 406 to 3: more `pg_stats` rows means more groups in `null_headers`, each of which re-evaluates the `EXISTS` against `information_schema.columns`. On an earlier run of the same database, before the harness created its own scratch tables (26 user tables, 98 `information_schema.columns` rows, 68 `pg_stats` rows), `EXPLAIN (ANALYZE, BUFFERS)` produced a **319-line plan** with 9.0 ms of planning and 28.0 ms of execution.

### Two defects that are not about accuracy

**`bloat_data` has duplicate output columns.** It selects `table_bytes` and `expected_bytes` twice each. The asker's final `SELECT` does not reference either, so the statement runs — but any attempt to project them fails:

```text
ERROR:  column reference "table_bytes" is ambiguous
```

This is ordinary CTE behaviour (`WITH x AS (SELECT 1 AS a, 2 AS a) SELECT a FROM x` fails the same way), and it blocks the obvious extension of the report. The statement as written does wrap: `CREATE TABLE ... AS <statement>` succeeded and produced 11 rows, because the *outer* column list is unique.

**`MAX(null_frac) AS maxfracsum`** is named for a sum and is a maximum. The name is the only documentation of that term's intent, and it is wrong.

### When to trust it

Given the measurements, the query is worth running when all of these hold, and worth distrusting otherwise:

| Condition | Why |
|---|---|
| statistics are fresh (`ANALYZE` after the last bulk change) | otherwise the reading is bounded below by staleness: −50.00 points measured |
| `fillfactor = 100` | otherwise the reserve is reported as bloat: +31.00 points measured |
| fixed-width columns are ordered without padding gaps | otherwise padding is reported as bloat: +21.00 points measured |
| tuples are small relative to a page | otherwise the packing remainder is reported as bloat: +33.00 points measured |
| few nullable columns, or `null_frac` well below 1 | otherwise the null header over-charge hides bloat: −25.05 points measured |
| no inheritance children | otherwise `datawidth` doubles: −9.00 points measured |
| TOAST values are large multiples of 1,996 bytes, and the TOAST relation has been vacuumed at least once | otherwise the `/4` rule or a zero `toast.relpages` distorts both sides |
| you accept that matviews, partitioned parents, `STATISTICS 0` tables, and never-analyzed tables are absent | the report cannot see them |

For the shapes it handles, `pct_bloat` is trustworthy to a few points. For everything else, `pgstattuple` on a candidate list is the follow-up, and only `VACUUM FULL` or `pgstattuple` plus knowledge of `fillfactor` and dropped columns answers "how much would a rebuild return".

### How to reproduce

The fixture matrix, in outline. Each table isolates one row of the score table above.

```sql
-- alignment padding: modelled 60 bytes/tuple, real 76 on the page
CREATE TABLE f.t02_clean_padded(
    a smallint NOT NULL, b bigint NOT NULL, c smallint NOT NULL,
    d bigint NOT NULL, e smallint NOT NULL, h bigint NOT NULL);
INSERT INTO f.t02_clean_padded
SELECT g % 100, g, g % 100, g, g % 100, g FROM generate_series(1, 400000) g;

-- page flooring: 2 tuples fit, the model implies 2.982
CREATE TABLE f.t03_wide_plain(id int NOT NULL, payload text NOT NULL);
ALTER TABLE f.t03_wide_plain ALTER COLUMN payload SET STORAGE PLAIN;
INSERT INTO f.t03_wide_plain
SELECT g, substr(repeat(md5(g::text), 100), 1, 2700) FROM generate_series(1, 8000) g;

-- TOAST geometry that is not 4 chunks per page: 1996 + 104
CREATE TABLE f.t22_toast_2chunk(id int NOT NULL, payload text NOT NULL);
ALTER TABLE f.t22_toast_2chunk ALTER COLUMN payload SET STORAGE EXTERNAL;
INSERT INTO f.t22_toast_2chunk
SELECT g, substr((SELECT string_agg(md5((g * 1000 + s)::text), '')
                  FROM generate_series(1, 100) s), 1, 2100)
FROM generate_series(1, 12000) g;
```

Ground truth for one relation and its TOAST heap, with the `reltoastrelid <> 0` filter below the lateral call so `pgstattuple(0)` is never reached (it raises `could not open relation with OID 0`):

```sql
SELECT /* wiki_bloat_ground_truth */
       n.nspname, c.relname,
       m.table_len, m.dead_tuple_len, m.free_space,
       coalesce(t.table_len, 0)      AS toast_len,
       coalesce(t.dead_tuple_len, 0) AS toast_dead_len,
       coalesce(t.free_space, 0)     AS toast_free
FROM pg_class c
     JOIN pg_namespace n ON n.oid = c.relnamespace
     CROSS JOIN LATERAL pgstattuple(c.oid) m
     LEFT JOIN LATERAL (
         SELECT ps.*
         FROM (SELECT c.reltoastrelid AS toid
               WHERE c.reltoastrelid <> 0
               OFFSET 0) s
              CROSS JOIN LATERAL pgstattuple(s.toid) ps
     ) t ON true
WHERE n.nspname = 'f' AND c.relkind IN ('r', 'm')
ORDER BY c.relname;
```

The `OFFSET 0` is load-bearing: without it the planner flattens the subquery, the `<> 0` qual is evaluated after the function scan, and the statement fails with `could not open relation with OID 0` — reproduced while building this page.

Both snippets above were extracted mechanically from this page's own Markdown and re-run against the same 12.2 server, so what is published is what executed. `lock_timeout` and `statement_timeout` are both `PGC_USERSET` ([guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2376-L2400)), so they take effect for the session or transaction and need neither a restart nor a reload. Verify production-bound copies against your own cluster before use.

## Context Reviewed

- **Tuple and page geometry**: `htup_details.h` (`HeapTupleHeaderData`, `SizeofHeapTupleHeader`, `MaxHeapTuplesPerPage`, `BITMAPLEN`), `bufpage.h`/`bufpage.c` (`SizeOfPageHeaderData`, `PageGetFreeSpace`, `PageGetHeapFreeSpace`), `itemid.h` (`ItemIdData`), `c.h` (`MAXALIGN`), `heaptuple.c` (`heap_form_tuple`, `heap_compute_data_size`).
- **Insert and rewrite paths**: `hio.c` (`RelationGetBufferForTuple`), `heapam.c` (`heap_multi_insert`), `rewriteheap.c` (`raw_heap_insert`), `heapam_handler.c` (`reform_and_rewrite_tuple`), `rel.h` (`HEAP_DEFAULT_FILLFACTOR`, `RelationGetTargetPageFreeSpace`).
- **Statistics production**: `analyze.c` (`analyze_rel`, `do_analyze_rel`, `examine_attribute`, `std_typanalyze`, `compute_trivial_stats`, `compute_scalar_stats`), `vacuum.c` (`vac_update_relstats`, `vacuum_rel`, `vac_estimate_reltuples`), `autovacuum.c` (`do_autovacuum`, `relation_needs_vacanalyze`), `relcache.c` (`RelationSetNewRelfilenode`).
- **Catalog surfaces the query reads**: `system_views.sql` (`pg_stats`, `pg_stat_all_tables`, `pg_stat_user_tables`), `information_schema.sql` (`columns`), `dbsize.c` (`pg_table_size`, `calculate_table_size`, `calculate_toast_table_size`), `guc.c` (`block_size`).
- **TOAST**: `tuptoaster.h` (`MaximumBytesPerTuple`, `TOAST_TUPLE_THRESHOLD`, `EXTERN_TUPLES_PER_PAGE`, `TOAST_MAX_CHUNK_SIZE`), `tuptoaster.c` (`toast_save_datum`).
- **Measurement tooling**: `contrib/pgstattuple/pgstattuple.c` (`pgstat_relation`, `pgstat_heap`, `build_pgstattuple_type`).
- **Documentation in the same checkout**: `catalogs.sgml` (`pg_class.relpages`, `pg_class.reltuples`), `monitoring.sgml` (`n_live_tup`), `pgstattuple.sgml` (column definitions and the `table_len` note).
- **Exact-pin server**: 12.2 built out of tree from `raw/postgres-12/`, 26 fixture relations, three readings per fixture (estimator, `pgstattuple`, `VACUUM FULL`), plus probes for pg_statistic row counts, TOAST chunk geometry, report presence, filter reachability, locks, privileges, and cost.

## Evidence Map

| Claim | Evidence |
|---|---|
| `hdr = 23` matches `SizeofHeapTupleHeader` | [htup_details.h#HeapTupleHeaderData](../../../../raw/postgres-12/src/include/access/htup_details.h#L152-L184) |
| line pointer is 4 bytes | [itemid.h#ItemIdData](../../../../raw/postgres-12/src/include/storage/itemid.h#L25-L30) |
| `bs - 20` overstates usable page space; the header is 24 bytes | [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L212-L216) |
| a page also reserves a line pointer, and caps at `MaxHeapTuplesPerPage` | [bufpage.c#PageGetHeapFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L649-L715), [htup_details.h#MaxHeapTuplesPerPage](../../../../raw/postgres-12/src/include/access/htup_details.h#L563-L576) |
| real tuple size includes the null bitmap inside `MAXALIGN` and per-column padding | [heaptuple.c#heap_form_tuple](../../../../raw/postgres-12/src/backend/access/common/heaptuple.c#L1020-L1095), [heaptuple.c#heap_compute_data_size](../../../../raw/postgres-12/src/backend/access/common/heaptuple.c#L114-L167) |
| `fillfactor` reserves space on insert and on rewrite | [rel.h#RelationGetTargetPageFreeSpace](../../../../raw/postgres-12/src/include/utils/rel.h#L289-L309), [hio.c#RelationGetBufferForTuple](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L320-L350), [heapam.c#heap_multi_insert](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L2105-L2200), [rewriteheap.c#raw_heap_insert](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L628-L700) |
| `relpages`/`reltuples` are estimates refreshed by VACUUM/ANALYZE/DDL | [catalogs.sgml#relpages](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L1759-L1781), [vacuum.c#vac_update_relstats](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1116-L1170), [relcache.c#RelationSetNewRelfilenode](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L3419-L3542) |
| inheritance parents get a second `pg_statistic` row per column | [analyze.c#analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L118-L270), [system_views.sql#pg_stats](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L189-L252) |
| `STATISTICS 0` suppresses the `pg_statistic` row | [analyze.c#examine_attribute](../../../../raw/postgres-12/src/backend/commands/analyze.c#L878-L893) |
| an empty table gets no column statistics but does get fresh `relpages` | [analyze.c:512](../../../../raw/postgres-12/src/backend/commands/analyze.c#L512), [analyze.c#vac_update_relstats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L587-L605) |
| `json` still gets `null_frac` and `avg_width` | [analyze.c#std_typanalyze](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1649-L1718), [analyze.c#compute_trivial_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1721-L1800) |
| `avg_width` is the in-heap width, so TOAST pointers are 18 bytes | [analyze.c#compute_scalar_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L2162-L2246) |
| matviews are absent from `information_schema.columns` | [information_schema.sql#columns](../../../../raw/postgres-12/src/backend/catalog/information_schema.sql#L778-L797) |
| partitioned tables are absent from `pg_stat_user_tables` | [system_views.sql#pg_stat_all_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L552-L581), [system_views.sql#pg_stat_user_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L613-L616) |
| the null branch measures a different footprint | [dbsize.c#pg_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L450-L467), [dbsize.c#calculate_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L380-L408), [dbsize.c#calculate_toast_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L338-L378) |
| `est_rows` on the null branch is a collector estimate | [monitoring.sgml#n_live_tup](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2773-L2776) |
| four maximum-size TOAST chunks per page is the design target; tails are short | [tuptoaster.h#TOAST_MAX_CHUNK_SIZE](../../../../raw/postgres-12/src/include/access/tuptoaster.h#L77-L96), [tuptoaster.h#MaximumBytesPerTuple](../../../../raw/postgres-12/src/include/access/tuptoaster.h#L27-L57), [tuptoaster.c#TOAST_MAX_CHUNK_SIZE](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L1636-L1693) |
| ANALYZE never refreshes TOAST `relpages`; autovacuum only vacuums it on dead tuples or wraparound | [vacuum.c#vacuum_rel](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1843-L1866), [analyze.c#vac_update_relstats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L587-L629), [autovacuum.c#RELKIND_TOASTVALUE](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2138-L2192), [autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2958-L3081) |
| a rewrite drops dropped-column bytes, which `pgstattuple` cannot see | [heapam_handler.c#reform_and_rewrite_tuple](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2508-L2548) |
| `pgstattuple` measures `t_len` and `PageGetHeapFreeSpace`, and accepts TOAST relations | [pgstattuple.c#pgstat_heap](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L315-L404), [pgstattuple.c#pgstat_relation](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L239-L305), [pgstattuple.c#build_pgstattuple_type](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L90-L145) |
| `table_len` exceeds its components by page overhead, line pointers, and padding | [pgstattuple.sgml#note](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L123-L131) |
| `block_size` is a fixed preset | [guc.c#block_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2879-L2888) |
| `statement_timeout` and `lock_timeout` are session-scoped | [guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2376-L2400) |

Measured claims (exact-pin 12.2 server, 26 fixture relations): the score and screening tables, the per-tuple table, the TOAST geometry table, the size-accounting table, the lock, privilege and cost tables, the `pg_statistic` row counts, the chunk-length census, and the reproduced error strings.

## Open Questions

1. **Why `no_stats` exists at all.** Its comment cites JSON, which is measurably not a case on this major. Whether the pattern predates `compute_trivial_stats` in some older release is a question about versions outside this pin and was not investigated here.
2. **The `nullhdr`/`nullhdr2` intent.** The measured behaviour (a whole extra aligned header, scaled by `MAX(null_frac)`) is 24 bytes per row above the engine's real bitmap cost on a 12-column table. Whether the term was meant to model something else — a dropped-column allowance, perhaps — cannot be determined from the statement.
3. **`t19_mixed` was not the mixed TOAST case intended.** Its delete predicate `id % 5 < 2` happens to cover every `id % 50 = 0` row, so all toasted rows were deleted. The measurement stands, but a partial-TOAST-delete case at that width was not exercised; `t10` and `t22` cover partial deletes at 4-chunk and 2-chunk geometry.
4. **Byte-level free-space reconciliation for `t22_toast_2chunk` was not completed.** Live length reconciles exactly (`3000 * (2032 + 140) = 6,516,000`), but the 26,032,000-byte free-space reading was not decomposed page by page, because the surviving chunks are scattered rather than clustered. No claim in this page depends on that decomposition.
5. **`autovacuum = off` in the sandbox.** The never-vacuumed TOAST finding is therefore a source-plus-fixture argument, not an observation of a default cluster over time. The source path is verified; how long a real insert-only TOAST relation keeps `relpages = 0` in practice depends on `autovacuum_freeze_max_age` and was not timed.
6. **Cost was measured to 427 tables only.** The observed non-monotonic behaviour (analyzing everything made it slower) is reported as measured; the shape of the curve beyond a few hundred tables was not established, and no extrapolation is offered.
7. **`vac_estimate_reltuples` blending was not exercised deliberately.** Every fixture here was either fully scanned by `VACUUM`/`ANALYZE` or deliberately left stale, so the partial-scan blend at [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1072-L1113) is a plausible additional source of `reltuples` error that this run does not quantify.
8. **The harness's own scratch tables appear in the report.** `public.truth` and `public.rewrite` were created in a non-system schema, so the statement measured them too. They were excluded from every scoring query by schema name, but they are the reason one `can_estimate = false` row in the filter-reachability probe is not a fixture.

## Source References

- [htup_details.h#HeapTupleHeaderData](../../../../raw/postgres-12/src/include/access/htup_details.h#L152-L184) — the header struct, its 23-byte comment, and `SizeofHeapTupleHeader`.
- [htup_details.h#MaxHeapTuplesPerPage](../../../../raw/postgres-12/src/include/access/htup_details.h#L563-L576) — line-pointer ceiling per heap page.
- [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L212-L216) — 24-byte page header.
- [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597) — free space minus one line pointer.
- [bufpage.c#PageGetHeapFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L649-L715) — the heap variant, with the `MaxHeapTuplesPerPage` cutoff.
- [itemid.h#ItemIdData](../../../../raw/postgres-12/src/include/storage/itemid.h#L25-L30) — the 4-byte line pointer.
- [c.h#MAXALIGN](../../../../raw/postgres-12/src/include/c.h#L679-L689) — the alignment macro the query re-implements in SQL.
- [pg_config.h.in:797](../../../../raw/postgres-12/src/include/pg_config.h.in#L797) — `MAXIMUM_ALIGNOF` is substituted by `configure`, so the query's hard-coded `8` is a build assumption.
- [heaptuple.c#heap_compute_data_size](../../../../raw/postgres-12/src/backend/access/common/heaptuple.c#L114-L167) — per-attribute alignment inside the tuple.
- [heaptuple.c#heap_form_tuple](../../../../raw/postgres-12/src/backend/access/common/heaptuple.c#L1020-L1095) — header, `BITMAPLEN`, `MAXALIGN`, data length.
- [rel.h#RelationGetTargetPageFreeSpace](../../../../raw/postgres-12/src/include/utils/rel.h#L289-L309) — the `fillfactor` reserve, with `HEAP_DEFAULT_FILLFACTOR`.
- [hio.c#RelationGetBufferForTuple](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L320-L350) — `saveFreeSpace` on the insert path.
- [heapam.c#heap_multi_insert](../../../../raw/postgres-12/src/backend/access/heap/heapam.c#L2105-L2200) — the same reserve in the batch path.
- [rewriteheap.c#raw_heap_insert](../../../../raw/postgres-12/src/backend/access/heap/rewriteheap.c#L628-L700) — the reserve applied by a rewrite, which is why `VACUUM FULL` does not reclaim it.
- [heapam_handler.c#reform_and_rewrite_tuple](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2508-L2548) — dropped columns nulled during a rewrite.
- [analyze.c#analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L118-L270) — the non-inherited and inherited passes.
- [analyze.c:512](../../../../raw/postgres-12/src/backend/commands/analyze.c#L512) — statistics computed only when `numrows > 0`.
- [analyze.c#vac_update_relstats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L587-L629) — `vac_update_relstats` for the relation and its indexes, never its TOAST relation.
- [analyze.c#examine_attribute](../../../../raw/postgres-12/src/backend/commands/analyze.c#L878-L893) — `attstattarget == 0` skip.
- [analyze.c#std_typanalyze](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1649-L1718) — algorithm selection by available operators.
- [analyze.c#compute_trivial_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1721-L1800) — `stanullfrac` and `stawidth` without MCVs.
- [analyze.c#compute_scalar_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L2162-L2246) — the toasted-width comment and `VARSIZE_ANY` accumulation.
- [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1072-L1113) — the density blend for partial scans.
- [vacuum.c#vac_update_relstats](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1116-L1170) — the shared writer of `relpages`/`reltuples`.
- [vacuum.c#vacuum_rel](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1843-L1866) — TOAST vacuumed, TOAST never analyzed.
- [autovacuum.c#RELKIND_TOASTVALUE](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2138-L2192) — the TOAST second pass that ignores analyze.
- [autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2958-L3081) — `n_dead_tuples` threshold and the wraparound force.
- [relcache.c#RelationSetNewRelfilenode](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L3419-L3542) — `relpages`/`reltuples` zeroed by a relfilenode swap.
- [system_views.sql#pg_stats](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L189-L252) — `stainherit` exposed but not filtered; the column-privilege gate.
- [system_views.sql#pg_stat_all_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L552-L581) — `relkind IN ('r','t','m')`.
- [system_views.sql#pg_stat_user_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L613-L616) — the schema filter the query relies on.
- [information_schema.sql#columns](../../../../raw/postgres-12/src/backend/catalog/information_schema.sql#L778-L797) — `relkind IN ('r','v','f','p')` and the privilege gate.
- [dbsize.c#calculate_toast_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L338-L378) — TOAST heap plus TOAST indexes.
- [dbsize.c#calculate_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L380-L408) — every fork, plus TOAST.
- [dbsize.c#pg_table_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L450-L467) — `try_relation_open(AccessShareLock)`, `NULL` on a dropped relation.
- [guc.c#block_size](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2879-L2888) — `PGC_INTERNAL` preset.
- [guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2376-L2400) — `statement_timeout` and `lock_timeout`, both `PGC_USERSET`.
- [tuptoaster.h#MaximumBytesPerTuple](../../../../raw/postgres-12/src/include/access/tuptoaster.h#L27-L57) — the per-page tuple-size derivation and `TOAST_TUPLE_THRESHOLD`.
- [tuptoaster.h#TOAST_MAX_CHUNK_SIZE](../../../../raw/postgres-12/src/include/access/tuptoaster.h#L77-L96) — `EXTERN_TUPLES_PER_PAGE = 4` and the 1,996-byte chunk.
- [tuptoaster.c#TOAST_MAX_CHUNK_SIZE](../../../../raw/postgres-12/src/backend/access/heap/tuptoaster.c#L1636-L1693) — `chunk_size = Min(TOAST_MAX_CHUNK_SIZE, data_todo)`, so only the tail is short.
- [pgstattuple.c#build_pgstattuple_type](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L90-L145) — the percentage arithmetic used as ground truth.
- [pgstattuple.c#pgstat_relation](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L239-L305) — accepted and rejected relkinds.
- [pgstattuple.c#pgstat_heap](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L315-L404) — `t_len` accumulation, `PageGetHeapFreeSpace` per block, `table_len` from the block count.
- [catalogs.sgml#relpages](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L1759-L1781) — both columns documented as planner estimates.
- [monitoring.sgml#n_live_tup](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2773-L2776) — "Estimated number of live rows".
- [pgstattuple.sgml#note](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L123-L131) — why `table_len` exceeds the sum of its parts.

## Navigation

- [v12/index](../../index.md) — PostgreSQL 12 landing page.
- [PostgreSQL 12 Codebase Navigation Guide](../../codebase-navigation-guide.md) — source-tree map for this pin.
- [Measuring Heap and TOAST Bloat With pgstattuple_approx in PostgreSQL 12](pgstattuple-approx-heap-and-toast-bloat.md) — the sampling alternative, with the same `fillfactor` and TOAST-chunk problems measured on the same major.
- [How Much I/O a VACUUM FULL Performs on a Multi-GB, Near-Empty Heap in PostgreSQL 12](vacuum-full-io-on-near-empty-heap.md) — the cost of the rewrite this page uses as its arbiter.
- [Measuring B-Tree Index Bloat With Core SQL Only in PostgreSQL 12](../indexing/btree-index-bloat-core-sql-only.md) — the index-side counterpart to a catalog-only estimator.
- [PostgreSQL 12 Database Health Checklist](../server-administration/database-health-checklist.md) — where a bloat screen fits among the other signals.
- [versions](../../../versions.md) — source pin manifest.
- [index](../../../index.md) — global wiki catalog.
