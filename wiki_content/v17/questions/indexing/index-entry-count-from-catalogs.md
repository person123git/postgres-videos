---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: claude-opus-5-max 2026-08-27T13:07:45Z
---

# Reading an Index's Entry Count From the Catalogs, for Every Index Type, in PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
  - [Prompt corrections](#prompt-corrections)
  - [Scoping answers](#scoping-answers)
  - [Review prompt, 2026-08-27](#review-prompt-2026-08-27)
- [Answer](#answer)
  - [The one catalog column](#the-one-catalog-column)
  - [The statement](#the-statement)
  - [What one entry means per access method](#what-one-entry-means-per-access-method)
  - [Measured accuracy on a fresh build](#measured-accuracy-on-a-fresh-build)
  - [The three writers and which one wins](#the-three-writers-and-which-one-wins)
  - [The lifecycle stage by stage](#the-lifecycle-stage-by-stage)
  - [Which access methods repair a forged count](#which-access-methods-repair-a-forged-count)
  - [BRIN returns four different numbers for one index](#brin-returns-four-different-numbers-for-one-index)
  - [B-tree counts TIDs rather than index tuples](#b-tree-counts-tids-rather-than-index-tuples)
  - [GIN counts entries per row per column](#gin-counts-entries-per-row-per-column)
  - [Hash omits every NULL row](#hash-omits-every-null-row)
  - [The three sentinel values and the float4 ceiling](#the-three-sentinel-values-and-the-float4-ceiling)
  - [Why timestamp ordering cannot decide provenance](#why-timestamp-ordering-cannot-decide-provenance)
  - [What the statement cannot decide](#what-the-statement-cannot-decide)
  - [Which verdicts the statement actually returns](#which-verdicts-the-statement-actually-returns)
  - [What the 2026-08-27 review re-measured](#what-the-2026-08-27-review-re-measured)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Filed after prompt-hygiene correction, at the asker's request.

Follow `AGENTS.md`, in PostgreSQL 17. Question: how, for all index types, can a SQL
query read from the catalog the number of heap tuples that are indexed by one index?

### Prompt corrections

The original prompt read: `follow agents.md , in postgresql 17 , question: how for all
indexes types a sql query the catalog the number of tuples from the heap are indexed by
the one index?` The asker chose "correct and restate". The corrections were:
`agents.md` -> `AGENTS.md`; `postgresql` -> `PostgreSQL`; `sql` -> `SQL`; the space
before each comma removed; `all indexes types` -> `all index types`; the missing verb
supplied as `how ... can a SQL query read from the catalog`; `the number of tuples from
the heap are indexed by the one index` -> `the number of heap tuples that are indexed by
one index`.

### Scoping answers

Three scoping answers were taken before drafting:

1. **Unit.** Report the number of index entries the access method stores, not the
   heap-row count, and explain where the two diverge. This page therefore answers the
   corrected prompt by first showing that "heap tuples indexed by one index" is not a
   quantity the catalogs hold for every access method, and then reporting what they do
   hold.
2. **Depth.** Build an isolated 17.11 server from this repo's pin and measure, rather
   than answer from source alone.
3. **Allowed sources.** The statement may use the system catalogs plus the `pg_stat_*`
   views. `pageinspect` and plain SQL are used only as independent ground truth for
   scoring, never inside the answer statement.

### Review prompt, 2026-08-27

Filed after prompt-hygiene correction, at the asker's request.

Follow `AGENTS.md`, in PostgreSQL 17. Review question: Reading an Index's Entry Count
From the Catalogs, for Every Index Type, in PostgreSQL 17 (unverified).

The original prompt read: `follow agents.md , in postgresql 17 , review question: Reading
an Index's Entry Count From the Catalogs, for Every Index Type, in PostgreSQL 17
(unverified)`. The asker chose "correct and restate". The corrections were:
`agents.md` -> `AGENTS.md`; `postgresql` -> `PostgreSQL`; the space before each comma
removed.

Three scoping answers were taken before reviewing: audit the citations **and** re-measure
on a server; make corrections **in place** rather than as an appended review log; and
recreate the test cluster under `.wiki-runtime/`, then delete it when the review is filed.
Its outcome is [What the 2026-08-27 review re-measured](#what-the-2026-08-27-review-re-measured).

## Answer

**There is exactly one catalog column, and it is not a heap-tuple count for every access
method.** The number lives in `pg_class.reltuples` on the *index's own* `pg_class` row
(`relkind = 'i'`), and what one unit of it means is decided by the index access method:
B-tree stores heap TIDs, GIN stores extracted entries summed over rows *and* indexed
columns, BRIN stores summarized page ranges, and hash silently omits every row whose key
is NULL. Measured on a fresh serial rebuild, that column is byte-exact against
independent ground truth for all seven access methods — 14 of 14 indexes, twice, in two
separate databases. But it is overwritten by the next `ANALYZE` with the table's estimated
live row count, so on any real installation the value you read is usually not an entry
count at all.

### The one catalog column

`pg_class.reltuples` is a `float4` documented only as "Number of live rows in the table"
([pg_class.h:62-66](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L66),
[catalogs.sgml#reltuples](../../../../raw/postgres-17/doc/src/sgml/catalogs.sgml#L2034-L2048)).
The documentation never says what it means for an index; the only hint that it applies to
indexes at all is the `pg_class` preamble's "This includes indexes" and "Not all of
`pg_class`'s columns are meaningful for all relation kinds"
([catalogs.sgml#pg_class](../../../../raw/postgres-17/doc/src/sgml/catalogs.sgml#L1889-L1901)).

No other catalog column can hold this count. `pg_class.relpages` and `relallvisible` are
page counts ([pg_class.h:62-69](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L69));
`pg_index` carries only `indnatts` and `indnkeyatts`, which are column counts
([pg_index.h#Form_pg_index](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L29-L63));
`pg_am` has no numeric column at all
([pg_am.h#Form_pg_am](../../../../raw/postgres-17/src/include/catalog/pg_am.h#L29-L41));
and while `ANALYZE` does write `pg_statistic` rows keyed on an index OID for expression
indexes ([analyze.c#update_attstats-index](../../../../raw/postgres-17/src/backend/commands/analyze.c#L596-L602)),
`stadistinct` is a per-column distinct-value estimate that can even be a negative
multiplier, not a count of stored entries
([pg_statistic.h#stadistinct](../../../../raw/postgres-17/src/include/catalog/pg_statistic.h#L52-L69)).

Nor do the statistics views help. `pg_stat_all_indexes` exposes `idx_scan`,
`last_idx_scan`, `idx_tup_read` and `idx_tup_fetch`
([system_views.sql#pg_stat_all_indexes](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L790-L805)),
and `idx_tup_read` is documented as "Number of index entries returned by scans on this
index" ([monitoring.sgml#pg_stat_all_indexes](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L4027-L4034))
— a cumulative scan counter, not a population. `system_views.sql` never selects
`reltuples` in any view, so the query must read `pg_class` directly.

### The statement

Verified against the pinned checkout and run on an exact-pin 17.11 server. It reads
`pg_class`, `pg_am`, `pg_index`, `pg_namespace` and `pg_stat_all_tables` only.

```sql
SET statement_timeout = '30s';
SET lock_timeout = '2s';

SELECT /* wiki_index_entry_count */
       n.nspname                                          AS schema_name,
       ct.relname                                         AS table_name,
       ci.relname                                         AS index_name,
       am.amname                                          AS am,
       ci.relpages                                        AS index_pages,
       CASE WHEN ci.relkind = 'I' OR ci.reltuples < 0 OR NOT x.indisvalid
            THEN NULL ELSE ci.reltuples::bigint END       AS entry_count,
       CASE am.amname
         WHEN 'btree'  THEN 'heap TIDs, posting lists expanded; NULL keys included'
         WHEN 'hash'   THEN 'index tuples; a row whose key is NULL is not indexed'
         WHEN 'gist'   THEN 'leaf index tuples, one per indexed row'
         WHEN 'spgist' THEN 'leaf index tuples, one per indexed row'
         WHEN 'gin'    THEN 'extracted entries, summed over rows AND indexed columns'
         WHEN 'brin'   THEN 'summarized page ranges, NOT rows'
         WHEN 'bloom'  THEN 'signature rows, one per indexed row'
         ELSE 'defined by this AM''s ambuild / amvacuumcleanup'
       END                                                AS entry_unit,
       CASE
         WHEN ci.relkind = 'I'
           THEN 'n/a: partitioned index, never built, has no storage'
         WHEN NOT x.indisvalid
           THEN 'n/a: invalid index, never counted'
         WHEN ci.reltuples < 0
           THEN 'unknown: -1, storage was reset and nothing has counted it since'
         WHEN ci.reltuples = 0 AND ci.relpages = 0
           THEN 'zero: no storage yet'
         WHEN am.amname = 'brin' AND ct.relpages > 0
              AND ci.reltuples > ceil(ct.relpages::numeric / brin.ppr)
           THEN 'impossible: over ceil(table relpages / pages_per_range) = '
                || ceil(ct.relpages::numeric / brin.ppr)::bigint
         WHEN am.amname = 'gin' AND ct.reltuples >= 0
              AND ci.reltuples < ct.reltuples * x.indnatts
           THEN 'impossible: under rows x indnatts; GIN emits >= 1 entry per row per column'
         WHEN am.amname IN ('gin', 'brin', 'hash')
              AND x.indpred IS NULL
              AND ct.reltuples >= 0 AND ci.reltuples = ct.reltuples
           THEN 'suspect: equals the table row estimate, so probably overwritten'
         WHEN ci.reltuples > 16777216
           THEN 'plausible but rounded: over 2^24, float4 cannot hold it exactly'
         ELSE 'plausible'
       END                                                AS verdict,
       CASE WHEN am.amname = 'brin' AND ct.relpages > 0
            THEN ceil(ct.relpages::numeric / brin.ppr)::bigint END
                                                          AS brin_max_ranges,
       x.indnatts,
       x.indpred IS NOT NULL                              AS is_partial,
       ct.reltuples::bigint                               AS table_reltuples,
       s.analyze_count + s.autoanalyze_count              AS analyzes,
       s.vacuum_count + s.autovacuum_count                AS vacuums
FROM pg_class ci
     JOIN pg_am am        ON am.oid = ci.relam
     JOIN pg_index x      ON x.indexrelid = ci.oid
     JOIN pg_class ct     ON ct.oid = x.indrelid
     JOIN pg_namespace n  ON n.oid = ci.relnamespace
     LEFT JOIN pg_stat_all_tables s ON s.relid = ct.oid
     CROSS JOIN LATERAL (
       SELECT coalesce((SELECT o.option_value::int
                          FROM pg_options_to_table(ci.reloptions) o
                         WHERE o.option_name = 'pages_per_range'), 128) AS ppr
     ) brin
WHERE ci.relkind IN ('i', 'I')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname !~ '^pg_toast'
ORDER BY n.nspname, ct.relname, ci.relname;
```

Both timeouts are `PGC_USERSET`
([guc_tables.c:2611-2620](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620),
[guc_tables.c:2622-2631](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)),
so the two `SET`s apply to the session or transaction that runs them and need neither a
reload nor a restart. The statement is read-only and needs no other setting changed.

The `verdict` column carries only claims that are decidable from catalogs. Two of them
are hard bounds rather than heuristics:

- **BRIN.** The number of summarized page ranges cannot exceed
  `ceil(table relpages / pages_per_range)`, because `brinsummarize` walks the revmap one
  `pagesPerRange` step at a time over the table's block count
  ([brin.c#brinsummarize](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1878-L1957)).
  `pages_per_range` defaults to 128
  ([brin.h#BRIN_DEFAULT_PAGES_PER_RANGE](../../../../raw/postgres-17/src/include/access/brin.h#L39-L45)).
- **GIN.** The build-time entry count cannot be below `rows * indnatts`, because
  `ginBuildCallback` loops over every column of the index tuple descriptor
  ([gininsert.c#ginBuildCallback](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L276-L314))
  and `ginExtractEntries` always yields at least one entry per value — a
  `GIN_CAT_NULL_ITEM` placeholder for NULL and a `GIN_CAT_EMPTY_ITEM` placeholder when the
  opclass extracts nothing
  ([ginutil.c#ginExtractEntries](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L491-L525)).

`brin.ppr` is derived from `pg_class.reloptions`, so the bound is computed from catalogs
alone. `brinsummarize` itself uses the live `RelationGetNumberOfBlocks(heapRel)`
([brin.c:1892](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1892)), which
is why a stale `pg_class.relpages` on the table can move the bound; substituting
`pg_relation_size(ct.oid) / current_setting('block_size')::int` makes it exact at the cost
of leaving the catalog-only constraint.

### What one entry means per access method

Every access method returns its own count in `IndexBuildResult.index_tuples`, documented
in the header as "# of tuples inserted into index"
([genam.h#IndexBuildResult](../../../../raw/postgres-17/src/include/access/genam.h#L27-L34)),
and `index_build` writes exactly that into the index's `pg_class` row while writing
`heap_tuples` into the table's
([index.c#index_build-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3127-L3135)).
The SGML documentation never defines what that field counts — `ambuild` is described only
as returning "a palloc'd struct containing statistics about the new index"
([indexam.sgml#ambuild](../../../../raw/postgres-17/doc/src/sgml/indexam.sgml#L276-L296))
— so the unit is only knowable from each AM's build callback:

| AM | One unit is | Increment site |
|---|---|---|
| `btree` | one heap TID per scanned row, NULL keys included, counted before deduplication | [nbtsort.c#_bt_build_callback](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L576-L600) |
| `hash` | one index tuple per row **whose key is not NULL** | [hash.c#hashbuildCallback](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L209-L242) |
| `gist` | one leaf tuple per row | [gistbuild.c#gistSortedBuildCallback](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L384-L394), [gistbuild.c#gistBuildCallback](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L819-L841) |
| `spgist` | one leaf tuple per row | [spginsert.c#spgistBuildCallback](../../../../raw/postgres-17/src/backend/access/spgist/spginsert.c#L56-L67) |
| `gin` | extracted entries, summed over rows **and** indexed columns | [gininsert.c#ginHeapTupleBulkInsert](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L252-L274) |
| `brin` | one summarized page range, **empty ranges excluded** | [brin.c#form_and_insert_tuple](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1975-L1989), [brin.c#brinbuild-result](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1247-L1258) |
| `bloom` (contrib) | one signature row per row | [blinsert.c#blbuild-result](../../../../raw/postgres-17/contrib/bloom/blinsert.c#L148-L157) |

Hash's omission is the `_hash_convert_tuple` early return: `hashbuildCallback` returns
before incrementing when the conversion fails, and the conversion fails exactly when the
key is NULL, "because the only supported search operator is `=`, and we assume it is
strict"
([hashutil.c#_hash_convert_tuple](../../../../raw/postgres-17/src/backend/access/hash/hashutil.c#L303-L335)).

### Measured accuracy on a fresh build

Measured on an isolated server built out of tree from `raw/postgres-17/`
(`PostgreSQL 17.11`, `server_version_num` 170011), on a 200,000-row table carrying one
index per access method plus the shape variants that make the units diverge. Ground truth
is independent of `pg_class`: `pageinspect` for B-tree, hash, GiST and BRIN, and plain SQL
over the indexed values for GIN. All indexes were rebuilt with
`max_parallel_maintenance_workers = 0`, which is `PGC_USERSET`
([guc_tables.c:3409-3417](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417))
and so needs only a session-scoped `SET`; `autovacuum = off` is `PGC_SIGHUP`
([guc_tables.c:1449-1457](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457))
and was set in `postgresql.conf` before the server started, so a reload would also serve.

| Index | AM | `pg_class.reltuples` | Independent truth | Delta |
|---|---|---|---|---|
| `i_bt_id` | btree | 200000 | 200000 TIDs | 0 |
| `i_bt_v` (25% NULL) | btree | 200000 | 200000 TIDs (150379 on-disk tuples) | 0 |
| `i_bt_dup` (200 dups/key) | btree | 200000 | 200000 TIDs (**2000** on-disk tuples) | 0 |
| `i_bt_part` (partial) | btree | 150000 | 150000 TIDs | 0 |
| `i_hash_v` (25% NULL) | hash | 150000 | 150000 (metapage and page sum agree) | 0 |
| `i_gin_arr` | gin | 580766 | 580766 entries | 0 |
| `i_gin_tsv` | gin | 597901 | 597901 entries | 0 |
| `i_gin_multi` (2 columns) | gin | 1178667 | 1178667 entries | 0 |
| `i_gin_null` (NULL arrays) | gin | 30000 | 30000 entries | 0 |
| `i_gin_empty` (`'{}'` arrays) | gin | 30000 | 30000 entries | 0 |
| `i_gist_pt` | gist | 200000 | 200000 leaf items | 0 |
| `i_spg_txt` | spgist | 200000 | 200000 rows | 0 |
| `i_brin_id` (`pages_per_range=32`) | brin | 116 | 116 summarized ranges | 0 |
| `i_bloom_b` | bloom | 200000 | 200000 rows | 0 |

**14 of 14 exact.** The whole fixture set was then dropped and rebuilt from scratch in a
second database; every figure above reproduced byte for byte, including 580766, 597901,
1178667 and 116. `1178667 = 580766 + 597901` exactly, which is the two-column GIN sum.

A second scoring pass on the same fixtures after a 10% delete and a rebuild at 180,000
rows scored **15 of 16 exact**. The single miss is a partial BRIN index, covered below.

The 2026-08-27 review re-ran both passes on a cluster created from scratch, in two fresh
databases, and every cell of this table came back byte for byte: **14 of 14 exact, twice**,
and **15 of 16** at 180,000 rows with the same partial-BRIN miss, reading `12` against
`116` for a delta of `-104` and an error of `-89.655%`. At 180,000 rows the three GIN
indexes rebuilt to 522874, 538110 and 1060984 entries, again matched exactly by the
plain-SQL truth.

### The three writers and which one wins

Three code paths write an index's `pg_class.reltuples`, and they disagree about what it
means.

1. **`CREATE INDEX` / `REINDEX`** writes the AM's own `index_tuples`
   ([index.c:3133-3135](../../../../raw/postgres-17/src/backend/catalog/index.c#L3133-L3135)),
   through `index_update_stats`, which also refreshes `relpages` and sends a relcache
   invalidation
   ([index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2788-L2842)).
2. **`VACUUM`** writes the AM's `num_index_tuples` from `amvacuumcleanup`, but only when
   the AM returned a struct *and* did not mark the count estimated
   ([vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099)).
   `estimated_count` is set for the whole cleanup pass from
   `vacrel->scanned_pages < vacrel->rel_pages`
   ([vacuumlazy.c:2352-2356](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2352-L2356)),
   so a VACUUM that skipped even one all-visible page suppresses the write for any AM that
   copies the flag.
3. **`ANALYZE`** writes `ceil(tupleFract * totalrows)` for **every** index of the table,
   unconditionally
   ([analyze.c#index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663)).
   `tupleFract` is 1.0 for a non-partial index
   ([analyze.c:449](../../../../raw/postgres-17/src/backend/commands/analyze.c#L449)) and a
   sampled fraction for a partial one
   ([analyze.c#tupleFract-partial](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953)).

`ANALYZE` wins, because it is the only one of the three that never consults the access
method. Its own comment states the assumption it makes — "We assume that VACUUM hasn't set
`pg_class.reltuples` already, even during a `VACUUM ANALYZE`" — and lists the two
exceptions
([analyze.c:612-621](../../../../raw/postgres-17/src/backend/commands/analyze.c#L612-L621)).
Both writers go through `vac_update_relstats`, which stores the value verbatim with no
clamping
([vacuum.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1409-L1461)).

### The lifecycle stage by stage

Measured on the 200,000-row fixture, reading every index's `reltuples` after each event.
`autovacuum` was off, so every transition is the named command. The table had just been
built, so the "VACUUM, nothing dead" pass scanned every page and `estimated_count` was
false for it; the forged-value probe below runs the same command against an all-visible
table, where it is true, and gets a different answer for GIN.

| Index | AM | build | VACUUM, nothing dead | after DELETE 10% | VACUUM, bulkdelete | ANALYZE | VACUUM INDEX_CLEANUP OFF |
|---|---|---|---|---|---|---|---|
| `i_bt_id` | btree | 200000 | 200000 | 200000 | 180000 | 180000 | 180000 |
| `i_bt_dup` | btree | 200000 | 200000 | 200000 | 180000 | 180000 | 180000 |
| `i_bt_v` | btree | 200000 | 200000 | 200000 | 180000 | 180000 | 180000 |
| `i_bt_part` | btree | 150000 | 150000 | 150000 | 140000 | **139494** (sampled) | 139494 |
| `i_hash_v` | hash | 150000 | 150000 | 150000 | 140000 | **180000** | 180000 |
| `i_gin_arr` | gin | **580766** | **200000** | 200000 | 180000 | 180000 | 180000 |
| `i_gin_tsv` | gin | **597901** | **200000** | 200000 | 180000 | 180000 | 180000 |
| `i_gin_multi` | gin | **1178667** | **200000** | 200000 | 180000 | 180000 | 180000 |
| `i_gist_pt` | gist | 200000 | 200000 | 200000 | 180000 | 180000 | 180000 |
| `i_spg_txt` | spgist | 200000 | 200000 | 200000 | 180000 | 180000 | 180000 |
| `i_bloom_b` | bloom | 200000 | 200000 | 200000 | 180000 | 180000 | 180000 |
| `i_brin_id` | brin | 116 | 116 | 116 | 116 | **180000** | 180000 |
| `i_brin_par` (parallel build) | brin | **319** (varies) | **116** | 116 | 116 | **180000** | 180000 |
| `i_brin_part` (partial) | brin | **12** | **116** | 116 | 116 | **17736** (sampled) | 17736 |

Two cells are not reproducible constants, and both are marked above. The parallel BRIN
build count varies with parallel block allocation, so `319` is one build's reading; the
review measured `326` for the same index. The two `ANALYZE` readings for *partial* indexes
come from `tupleFract = numindexrows / numrows` over a random sample
([analyze.c#tupleFract-partial](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953)),
so they move every run: the review read `140142` and `18444` here, and `140478` and `17958`
on a later pass over the same fixtures. **Every other cell in this table reproduced byte
for byte** on the review's fresh cluster, including all three GIN build counts, the
116/12 BRIN builds, and every 180000.

Four readings matter:

- **A single VACUUM destroys every GIN entry count.** `ginvacuumcleanup` overwrites the
  count with the heap tuple count, under an `XXX` comment admitting it is "bogus if the
  index is partial, but it's real hard to tell how many distinct heap entries are
  referenced by a GIN index"
  ([ginvacuum.c#ginvacuumcleanup-count](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L731-L739)).
  580766 becomes 200000 on the first VACUUM.
- **`ANALYZE` flattens all seven access methods to the table's row estimate.** BRIN goes
  from 116 page ranges to 180000, a factor of about 1550. Hash goes from a correct 140000 to
  180000, silently re-adding the 40,000 NULL rows it never indexed.
- **`DELETE` alone changes nothing**, in either direction.
- **`VACUUM (INDEX_CLEANUP OFF)` changes nothing.** `update_relstats_all_indexes` asserts
  `vacrel->do_index_cleanup` and is only reached when index cleanup runs
  ([vacuumlazy.c:3079](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3079)),
  which is the same effect the `analyze.c` comment names for
  `VACUUM (ANALYZE, INDEX_CLEANUP OFF)`.

### Which access methods repair a forged count

To decide per AM whether a plain VACUUM refreshes the count, every index's `reltuples` was
forged to 777777 and a plain `VACUUM` with nothing to delete was run. This isolates the
`amvacuumcleanup` contract, which permits returning NULL "if the index was not changed at
all during the `VACUUM` operation"
([indexam.sgml#amvacuumcleanup](../../../../raw/postgres-17/doc/src/sgml/indexam.sgml#L418-L445)).

| AM | Forgery survived? | Why |
|---|---|---|
| btree | **yes** | `btvacuumcleanup` returns NULL unless `_bt_vacuum_needs_cleanup` fires ([nbtree.c:870-874](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L870-L874)), which in 17.11 needs a pre-`BTREE_NOVAC_VERSION` metapage or `btm_last_cleanup_num_delpages` above 5% of the index ([nbtpage.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L178-L222)) |
| hash | **yes** | "If hashbulkdelete wasn't called, return NULL signifying no change" ([hash.c#hashvacuumcleanup](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L647-L663)) |
| gin | **yes** | it copies `estimated_count` from the input ([ginvacuum.c:739](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L739)), which was true here, so `update_relstats_all_indexes` skipped it |
| gist | no, repaired | full scan when `stats == NULL` ([gistvacuum.c#gistvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L74-L105)), `estimated_count = false` ([gistvacuum.c:150-152](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L150-L152)) |
| spgist | no, repaired | full scan when `stats == NULL` ([spgvacuum.c#spgvacuumcleanup](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L946-L985)), `estimated_count = false` ([spgvacuum.c:820-822](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L820-L822)) |
| brin | no, repaired to a **different** value | re-derives the range count ([brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332)) |
| bloom | no, repaired | per-page `BloomPageGetMaxOffset` sum, `estimated_count` never assigned anywhere in `contrib/bloom` ([blvacuum.c#blvacuumcleanup](../../../../raw/postgres-17/contrib/bloom/blvacuum.c#L168-L217)) |

GIN's survival is entirely a visibility-map effect, which was then confirmed directly:
after re-forging the same three GIN indexes and running
`VACUUM (DISABLE_PAGE_SKIPPING) t`, so that `scanned_pages = rel_pages` and
`estimated_count` became false, all three were **repaired to 180000** — the heap row count,
not their true 522874, 538110 and 1060984 entries — while the forged B-tree and hash values
stayed at 777777.

So on one table, one `VACUUM` can leave a B-tree's count stale, overwrite a GIN's count with
the wrong quantity, and recompute a BRIN's count, all in the same command. There is no
per-table provenance; provenance is per index.

The review re-ran both probes and got the same seven verdicts, the same three
`VACUUM (DISABLE_PAGE_SKIPPING)` repairs to 180000, the same three GIN truths of 522874,
538110 and 1060984, and the same three BRIN repairs to 115.

### BRIN returns four different numbers for one index

For one physical BRIN index over one table, four code paths produce four different
`reltuples`, and only one of them equals the number of range summaries on disk.

| How the value was written | Reading | Ranges on disk |
|---|---|---|
| serial `CREATE INDEX` | **116** | 116 |
| parallel `CREATE INDEX` | **319** (nondeterministic; 305-330 across the review's builds) | 116 |
| serial build, partial index (`WHERE id < 20000`) | **12** | 116, of which 104 are empty-range summaries |
| `VACUUM` after the table was truncated to 3702 blocks | **115** | 116 |
| `ANALYZE` | **180000** | 116 |

Each has a distinct cause:

- **Parallel builds count pre-merge partial summaries.** Each worker's
  `form_and_spill_tuple` increments its own `bs_numtuples` per range slice it writes to the
  shared tuplesort
  ([brin.c#form_and_spill_tuple](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1996-L2015)),
  the workers sum into `brinshared->indtuples`
  ([brin.c:2837-2841](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2837-L2841)),
  and the leader *copies* that total into its own state
  ([brin.c#_brin_parallel_heapscan](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2569-L2596)).
  The leader then inserts the merged ranges with `brin_doinsert` directly and never
  increments the counter
  ([brin.c#_brin_parallel_merge-insert](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2688-L2740)),
  so the reported figure is the number of worker slices, not the number of ranges. The
  feature is new in this major version — `b4375717147`, first tagged `REL_17_BETA1` — and
  its commit message names the merge that makes the count wrong: the leader "merges
  duplicates (which may happen if the parallel scan does not align with BRIN
  pages_per_range)". Because parallel block allocation is nondeterministic, **the same
  finished index gets a different count on every rebuild**. Two independent runs, each
  sweeping `max_parallel_maintenance_workers` 0, 1, 2, 4 and 8 on the same 3712-block
  table, returned **116, 222, 325, 328, 311** and **116, 221, 328, 305, 326**; three
  four-worker builds of one index returned **317, 319, 328** in the first run and **326,
  330, 325** in the second. The on-disk range count was checked for all ten sweep builds
  and read 116 every time, so the serial build is the only one of the five that reports the
  truth.
- **Empty ranges are backfilled without being counted.** `brin_fill_empty_ranges` inserts
  empty-range summaries with `brin_doinsert` and never touches `bs_numtuples`
  ([brin.c#brin_fill_empty_ranges](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2979-L3004)),
  and in a parallel build `form_and_spill_tuple` also returns early for an empty range
  ([brin.c:2002-2004](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2002-L2004)).
  A partial BRIN index whose predicate excludes most of the table therefore reports 12
  against 116 summaries on disk. This is the one miss in the 16-index scoring pass, and it
  is an **under**count, so the `brin_max_ranges` bound in the statement cannot detect it.
  The serial path's own final flush is the exception: `form_and_insert_tuple` has no
  empty-range guard
  ([brin.c#form_and_insert_tuple](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1975-L1989)),
  so it counts the last range even when it is empty — which is why a BRIN index on an
  **empty** table reads `reltuples = 1`, measured, against one empty-range summary on disk
  and a zero-block heap.
- **`VACUUM` excludes a trailing partial range.** `brinvacuumcleanup` calls
  `brinsummarize` with `include_partial = false`
  ([brin.c:1326-1327](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1326-L1327)),
  and that flag makes the loop `break` before the final short range
  ([brin.c:1923-1925](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1923-L1925)).
  With the table at 3702 blocks and `pages_per_range = 32`, range 115 starts at block 3680
  and is partial, so VACUUM reported 115 while 116 summaries existed. Note also that both
  out-parameters are the *same* variable, so the figure is new-plus-existing summaries
  ([brin.c:1326-1327](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1326-L1327),
  [brin.c:1946-1954](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1946-L1954)).
  This is also why a VACUUM *repairs* the parallel-build overcount, as the lifecycle table
  shows at 319 -> 116.

### B-tree counts TIDs rather than index tuples

`_bt_build_callback` increments once per scanned row, before the leaf pages are written and
therefore before deduplication packs equal keys into posting lists
([nbtsort.c:576-600](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L576-L600)).
Measured on a 200,000-row index with 1,000 distinct keys, `reltuples` read **200000** while
only **2000** index tuples existed on the leaf pages — a factor of 100. The 25%-NULL index
read 200000 against 150379 on-disk tuples.

The VACUUM path is explicit that TIDs are the intended unit and that the cleanup-only path
cannot deliver them: `btvacuumpage` adds `nhtidslive` when a bulkdelete callback is present
but only `maxoff - minoff + 1` otherwise
([nbtree.c#btvacuumpage-counts](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1345-L1365)),
and `btvacuumcleanup` therefore marks the cleanup-only result estimated, noting that
"`num_index_tuples` is supposed to represent the number of TIDs in the index" and that the
naive count "can underestimate the number of tuples in the index significantly"
([nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L876-L893)).
Marking it estimated is exactly what makes `update_relstats_all_indexes` skip the write, so
the underestimate never reaches `pg_class`.

B-tree, GiST and SP-GiST additionally clamp the VACUUM count down to the heap tuple count
when it is known accurately
([nbtree.c:917-921](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L917-L921),
[gistvacuum.c:98-102](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L98-L102),
[spgvacuum.c:978-982](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L978-L982)).
Hash, GIN, BRIN and bloom do not clamp.

### GIN counts entries per row per column

`ginBuildCallback` calls `ginHeapTupleBulkInsert` once per column of the index's own tuple
descriptor
([gininsert.c:286-288](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L286-L288)),
and each call adds that column's `nentries`
([gininsert.c:271](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L271)).
The descriptor is the index relation's
([ginutil.c#initGinState](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L96-L113)),
so the multiplier is `pg_index.indnatts`. Measured: the two-column
`(arr, tsv)` index read 1178667, exactly `580766 + 597901`, the sum of its two
single-column twins.

Within one value, entries are sorted and de-duplicated, "avoid[ing] generating redundant
index entries"
([ginutil.c#ginExtractEntries](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L476-L557)),
and both a NULL value and a value from which the opclass extracts nothing yield exactly one
placeholder entry
([ginutil.c#placeholders](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L491-L525)).
Both placeholder cases were measured: 30,000-row tables of NULL arrays and of `'{}'` arrays
each read exactly 30000.

GIN also keeps an accurate count of its distinct entry keys, but only in its own metapage.
`ginvacuumcleanup` sums `PageGetMaxOffsetNumber` over the entry-leaf pages into
`idxStat.nEntries` and hands it to `ginUpdateStats`
([ginvacuum.c#nEntries](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L776-L789)).
That is a third, distinct quantity, and it never reaches `pg_class`. Measured after a
VACUUM, with `pageinspect` reading the metapage:

| Index | `pg_class.reltuples` | metapage `n_entries` | true extracted entries |
|---|---|---|---|
| `i_gin_arr` | 200000 | **100** | 580766 |
| `i_gin_tsv` | 200000 | **98** | 597901 |
| `i_gin_multi` | 200000 | **198** | 1178667 |

100 is the number of distinct array elements, 98 the number of distinct lexemes, and
`198 = 100 + 98`. So a GIN index has three defensible entry counts that differ by four
orders of magnitude, and the catalogs expose the least useful of them.

### Hash omits every NULL row

On a column with 25% NULLs, a B-tree read 200000 and a hash index on the same column read
150000 — measured, and matching `_hash_convert_tuple`'s NULL rejection
([hashutil.c:324-329](../../../../raw/postgres-17/src/backend/access/hash/hashutil.c#L324-L329)).
Hash also maintains its own count in the metapage `hashm_ntuples`
([hash.c#hashbulkdelete-meta](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L586-L606)),
which agreed with both the summed page items and `pg_class.reltuples` at 150000, but that
field is not reachable from the catalogs.

After the 10% delete and a VACUUM that ran bulkdelete, the hash index read 140000, which is
exactly the surviving non-NULL population: 150000 built, minus the 10,000 deleted rows that
were not NULL. `ANALYZE` then raised it to 180000.

### The three sentinel values and the float4 ceiling

- **`0` means "never built", not "-1".** `RelationBuildLocalRelation` allocates `rd_rel`
  with `palloc0` and never sets `reltuples`
  ([relcache.c#RelationBuildLocalRelation](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3656-L3665)),
  and `index_create` inserts that row directly
  ([index.c#InsertPgClassTuple-index](../../../../raw/postgres-17/src/backend/catalog/index.c#L1018-L1027))
  without the `reltuples = -1` step that tables get in `AddNewRelationTuple`
  ([heap.c:1006-1009](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1006-L1009)).
  Measured `0` on three shapes: an index built on an empty table, a partitioned index, and
  the invalid index left behind by a failed `CREATE INDEX CONCURRENTLY`. For an index, `0`
  is therefore ambiguous between "empty" and "never counted"; pairing it with
  `relpages = 0` separates most cases.
- **An index on an empty table reads 0 while its table reads -1.** Measured. The special
  hack in `index_update_stats` that preserves `-1` fires only when the relation's existing
  `reltuples` is already negative
  ([index.c:2825-2836](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2836)),
  which is true of the table and false of the brand-new index.
- **`-1` means the storage was reset.** `RelationSetNewRelfilenumber` writes
  `relpages = 0, reltuples = -1, relallvisible = 0`
  ([relcache.c#RelationSetNewRelfilenumber-stats](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3943-L3954)).
  Measured: a B-tree read 1000 after a rebuild with 1000 rows, then `-1` after
  `TRUNCATE` plus `REINDEX`.
- **A partitioned index can never hold a count.** `relkind = 'I'` is asserted against in
  `index_update_stats`
  ([index.c:2900-2901](../../../../raw/postgres-17/src/backend/catalog/index.c#L2900-L2901)),
  a partitioned index is never built
  ([index.c:775-778](../../../../raw/postgres-17/src/backend/catalog/index.c#L775-L778)), and
  `ANALYZE` refuses to open a partitioned table's indexes at all
  ([analyze.c:419-427](../../../../raw/postgres-17/src/backend/commands/analyze.c#L419-L427)).
  Measured 0 on the parent while both leaf indexes read 999 and 1000.
- **`float4` loses the low bits above 2^24.** `reltuples` is `float4`
  ([pg_class.h:65-66](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L65-L66)),
  whose 24-bit significand is exact for integers only to 16,777,216. A GIN index measured
  with exactly **20,000,001** extracted entries reported `2e+07`, reading **20000000** as a
  `bigint` — off by one. At 20,000,000 entries the value was exact, because that integer
  happens to be representable.

### Why timestamp ordering cannot decide provenance

A tempting design is to order `pg_stat_all_tables.last_vacuum` against `last_analyze` and
label the value accordingly. That is unsound, and was measured to be wrong twice on the
same fixture:

1. After an `ANALYZE`, a `VACUUM (INDEX_CLEANUP OFF)` moved `last_vacuum` ahead of
   `last_analyze` while BRIN's `reltuples` stayed at the `ANALYZE`-written 180000.
   `update_relstats_all_indexes` is only reached when index cleanup runs at all — it asserts
   `vacrel->do_index_cleanup`
   ([vacuumlazy.c:3079](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3079)).
2. A subsequent plain `VACUUM` with nothing dead left the B-tree and hash indexes at the
   `ANALYZE` value of 180000 while moving BRIN to 115. `last_vacuum` was newer than
   `last_analyze` for all three.

Both readings reproduced in the review, which reports the comparison as a boolean rather
than as clock times, because the times themselves are properties of one sandbox: `VACUUM
(INDEX_CLEANUP OFF)` returned `vacuum_looks_newer = true` with BRIN unchanged at 180000, and
the following plain `VACUUM` returned `true` again with B-tree and hash at 180000 and BRIN at
115.

`pg_stat_all_tables` timestamps are per table
([system_views.sql#pg_stat_all_tables](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L670-L703)),
and `pg_stat_all_indexes` has no timestamp for vacuum or analyze at all. The statement
therefore reports `analyzes` and `vacuums` as context only and never derives a verdict from
them.

### What the statement cannot decide

- **A single-column GIN index whose entry count legitimately equals the row count.**
  `i_gin_null` and `i_gin_empty` hold correct build-time counts of 30000, equal to their row
  counts, and the statement flags both `suspect`. This false positive is unavoidable from
  catalogs, because an opclass that extracts exactly one entry per value produces precisely
  the reading that an overwrite produces.
- **Any BRIN undercount.** The bound is one-sided, so a reading below the true number of
  summaries is invisible. The partial index above is one shape (12 against 116); a
  *non-partial* one is a heap whose rows were all deleted without a VACUUM, measured at
  **1 against 8 summaries on disk** over a 256-block heap with `pages_per_range = 32`.
- **A BRIN index whose table has a zero `relpages`.** The bound is guarded by
  `ct.relpages > 0`, and that guard fires more often than it looks: the same
  `CREATE TABLE AS` plus `DELETE` fixture left `pg_class.relpages = 0` on a table holding
  256 real blocks, so `brin_max_ranges` came back NULL and no BRIN verdict was possible.
  Substituting `pg_relation_size(ct.oid) / current_setting('block_size')::int` for
  `ct.relpages` closes this, at the cost of reading the file rather than the catalog.
- **A parallel BRIN build whose overcount happens to stay under the bound**, which is
  possible for a table with many empty ranges.
- **Whether a B-tree or hash count is merely stale.** Both AMs return NULL from
  `amvacuumcleanup` in the common case, so their value can be arbitrarily old with nothing
  in the catalogs to say so.
- **An index created after the last `ANALYZE`**, which still holds its build count. There is
  no index creation timestamp in the catalogs.

To read a true entry count for an arbitrary index, the only reliable procedure is to rebuild
it serially and read `pg_class.reltuples` before anything analyzes the table — which is what
the 14-of-14 measurement did.

### Which verdicts the statement actually returns

Run over 20 indexes in one database and 16 in another, the statement returned eight of its
nine verdicts. Two of them *prove* an overwrite; the rest only suspect one or describe the
row.

| Verdict | Fires on, measured | Strength |
|---|---|---|
| `impossible: over ceil(table relpages / pages_per_range) = 116` | all three BRIN indexes once `ANALYZE` had written 180000, 180000 and 17790 over their 116, 116 and 12 | proof |
| `impossible: under rows x indnatts` | `i_gin_multi`, reading 180000 where two indexed columns force at least 360000 | proof |
| `suspect: equals the table row estimate` | single-column GIN (`i_gin_arr`, `i_gin_tsv`) and `i_hash_v` after `ANALYZE`, plus the two legitimate 30000 readings on `tnull` | heuristic, 2 known false positives |
| `plausible` | every correct reading, including `i_hash_v` at 150000 against a 200,000-row table, where the NULL rows keep the two numbers apart and the equality test correctly stays quiet | no claim |
| `plausible but rounded: over 2^24` | `i_big_gin` at 20000000 | no claim |
| `n/a: partitioned index, never built, has no storage` | `i_p_bt`, `relkind = 'I'` | structural |
| `n/a: invalid index, never counted` | the index left by a failed `CREATE UNIQUE INDEX CONCURRENTLY`, `reltuples = 0`, `relpages = 0` | structural |
| `unknown: -1, storage was reset` | `i_e_bt` after `TRUNCATE` plus `REINDEX` | structural |
| `zero: no storage yet` | never reached; see below | — |

Two consequences are worth stating plainly:

- **The GIN lower bound only works from two columns up.** A single-column GIN index's floor
  is one entry per row, which is exactly the value an overwrite writes, so the bound can
  never fire and `suspect` is the strongest available verdict. From `indnatts = 2` the floor
  doubles and any overwrite is provably wrong.
- **The `zero: no storage yet` branch is unreachable for a valid, non-partitioned index.**
  Every access method allocates at least one page during `ambuild`, measured on an empty
  table as `relpages` of 1 for btree, GiST and bloom, 2 for GIN, 3 for SP-GiST and BRIN, and
  4 for hash. The two shapes that really do read `relpages = 0` — a partitioned index and
  an index left invalid by a failed concurrent build — are both caught by earlier branches.
  So an index on an empty table reports `plausible` with `entry_count = 0`, which is its
  true count; BRIN is the exception at 1, for the reason given above.

### What the 2026-08-27 review re-measured

The review rebuilt the environment (the earlier sandbox's data directory was gone, the
17.11 install was not), re-created the fixtures in two fresh databases, re-ran every probe,
and re-read every citation. Outcome:

- **All 125 distinct source citations the page carried at review time resolve** to a
  non-blank, in-bounds line range in `raw/postgres-17/` at pin
  `786db8dcf168bd9df8f55047337525ac19118b1c`, and each cited range contains the code,
  comment or documentation text the claim attributes to it. Three citation *labels*
  disagreed with their own line ranges and were corrected (`pg_class.h:62-70` -> `62-69`,
  `nbtsort.c:585-600` -> `576-600`, twice). The review then added four `guc_tables.c`
  citations for apply scopes, so the page now carries 129, all resolving.
- **The published statement is byte-identical to the statement that was tested**: 68 lines,
  compared line by line against the harness file.
- **Every measured number reproduced byte for byte** except the three that cannot: the
  parallel BRIN count, the two `ANALYZE` readings on partial indexes, and wall-clock
  timestamps. That includes 14 of 14 exact twice, 15 of 16 at 180,000 rows with the same
  `-104` partial-BRIN miss, 580766 / 597901 / 1178667 / 30000 / 150000 / 116 / 12 / 2000 /
  150379, the 522874 / 538110 / 1060984 GIN truths, the 100 / 98 / 198 metapage counts, the
  115-against-116 VACUUM reading on a 3702-block heap with range 115 starting at block 3680,
  the seven forgery verdicts, the 999 / 1000 partition leaves, and the `20,000,001` entries
  that read back as 20000000.
- **Four things were added because the review measured them**: the BRIN serial build's
  unguarded final flush (an empty table reads 1), the per-AM `relpages` floor that makes
  `zero: no storage yet` unreachable, the non-partial BRIN undercount of 1 against 8, and
  the `ct.relpages = 0` guard that silently disables the BRIN bound.
- The parallel BRIN over-count was traced to its commit, `b4375717147`, first tagged
  `REL_17_BETA1`, and `bs_numtuples` is touched by no other commit reachable from this pin
  except the original BRIN commit `7516f525941`.

## Context Reviewed

- `pg_class` and `pg_index` catalog definitions, and the `pg_am`, `pg_statistic`,
  `pg_statistic_ext` and `pg_statistic_ext_data` headers, to establish that
  `pg_class.reltuples` is the only column that can hold this count.
- `system_views.sql` definitions of `pg_stat_all_tables`, `pg_stat_all_indexes`,
  `pg_statio_all_indexes`, `pg_indexes` and `pg_stats`.
- `genam.h` `IndexBuildResult` and `IndexBulkDeleteResult`, and `amapi.h`
  `ambuild_function`.
- Build callbacks and `ambuild` result assembly for btree, hash, GiST, SP-GiST, GIN, BRIN
  and contrib bloom.
- `ambulkdelete` and `amvacuumcleanup` for the same seven access methods, including the
  `estimated_count` and clamping behavior of each.
- `index.c` `index_build`, `index_update_stats`, `index_create`'s `InsertPgClassTuple` call,
  and the partitioned-index assertions.
- `vacuumlazy.c` `lazy_cleanup_all_indexes`, `lazy_vacuum_one_index`,
  `lazy_cleanup_one_index` and `update_relstats_all_indexes`.
- `analyze.c` `do_analyze_rel` index handling, `compute_index_stats` `tupleFract`, and
  `vacuum.c` `vac_update_relstats` and `vac_estimate_reltuples`.
- `relcache.c` `RelationBuildLocalRelation` and `RelationSetNewRelfilenumber`, and
  `heap.c` `InsertPgClassTuple` and `AddNewRelationTuple`.
- `catalogs.sgml`, `indexam.sgml` and `monitoring.sgml` for the documented contracts.
- An isolated 17.11 server built out of tree from `raw/postgres-17/` with
  `autovacuum = off`, carrying 22 indexes over seven access methods, scored against
  `pageinspect` and plain-SQL ground truth in two independent databases.
- `guc_tables.c` entries for `statement_timeout`, `lock_timeout`,
  `max_parallel_maintenance_workers` and `autovacuum`, for the apply scope of every setting
  this page sets.
- The pinned checkout's own history for `bs_numtuples` and the parallel BRIN build
  (`b4375717147`, `7516f525941`), and `contrib/pageinspect`'s file list, which has no
  SP-GiST module.
- 2026-08-27 review on a cluster created from scratch with the surviving 17.11 install: the
  fixtures, truth views, stage, forgery, timestamp and edge probes re-run in two fresh
  databases; four new probes (per-AM `relpages` on an empty table, BRIN on an empty table,
  BRIN over an all-dead 256-block heap, and the statement run against an `ANALYZE`-written
  state); a citation resolver over all 125 distinct citations; and a line-by-line comparison
  of the published statement against the tested one.

## Evidence Map

| Claim | Evidence |
|---|---|
| `pg_class.reltuples` is `float4` and the only catalog column holding an index entry count | [pg_class.h:62-66](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L66), [pg_index.h#Form_pg_index](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L29-L63), [pg_am.h#Form_pg_am](../../../../raw/postgres-17/src/include/catalog/pg_am.h#L29-L41), [pg_statistic.h#stadistinct](../../../../raw/postgres-17/src/include/catalog/pg_statistic.h#L52-L69) |
| The docs define `reltuples` only for tables | [catalogs.sgml#reltuples](../../../../raw/postgres-17/doc/src/sgml/catalogs.sgml#L2034-L2048), [catalogs.sgml#pg_class](../../../../raw/postgres-17/doc/src/sgml/catalogs.sgml#L1889-L1901) |
| `pg_stat_all_indexes` has no stored-entry count | [system_views.sql#pg_stat_all_indexes](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L790-L805), [monitoring.sgml#idx_tup_read](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L4027-L4034) |
| `index_tuples` is the AM's own count and lands on the index's row | [genam.h#IndexBuildResult](../../../../raw/postgres-17/src/include/access/genam.h#L27-L34), [index.c:3127-3135](../../../../raw/postgres-17/src/backend/catalog/index.c#L3127-L3135) |
| B-tree counts one TID per scanned row, pre-deduplication | [nbtsort.c:576-600](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L576-L600) |
| B-tree's VACUUM unit is TIDs, and the cleanup-only count is deliberately an estimate | [nbtree.c#btvacuumpage-counts](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1345-L1365), [nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L876-L893) |
| Hash omits NULL-keyed rows | [hash.c#hashbuildCallback](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L209-L242), [hashutil.c#_hash_convert_tuple](../../../../raw/postgres-17/src/backend/access/hash/hashutil.c#L303-L335) |
| GIN sums extracted entries over rows and columns, with one placeholder for NULL or empty | [gininsert.c#ginHeapTupleBulkInsert](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L252-L274), [gininsert.c:286-288](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L286-L288), [ginutil.c#ginExtractEntries](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L476-L557) |
| GIN's VACUUM cleanup substitutes the heap tuple count | [ginvacuum.c#ginvacuumcleanup-count](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L731-L739) |
| GiST, SP-GiST and bloom count one leaf/signature entry per row | [gistbuild.c#gistBuildCallback](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L819-L841), [spginsert.c#spgistBuildCallback](../../../../raw/postgres-17/src/backend/access/spgist/spginsert.c#L56-L67), [blinsert.c#blbuild-result](../../../../raw/postgres-17/contrib/bloom/blinsert.c#L148-L157) |
| BRIN counts page ranges, excluding empty ones, and parallel builds count worker slices | [brin.c#form_and_insert_tuple](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1975-L1989), [brin.c#form_and_spill_tuple](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1996-L2015), [brin.c#_brin_parallel_heapscan](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2569-L2596), [brin.c#brin_fill_empty_ranges](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2979-L3004) |
| BRIN's VACUUM count skips a trailing partial range | [brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332), [brin.c:1923-1925](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1923-L1925) |
| The BRIN range bound and its `pages_per_range` default | [brin.c#brinsummarize](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1878-L1957), [brin.h#BRIN_DEFAULT_PAGES_PER_RANGE](../../../../raw/postgres-17/src/include/access/brin.h#L39-L45) |
| VACUUM writes the index row only for a non-NULL, non-estimated result | [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099), [vacuumlazy.c:2352-2356](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2352-L2356), [genam.h#IndexBulkDeleteResult](../../../../raw/postgres-17/src/include/access/genam.h#L56-L84) |
| `amvacuumcleanup` may return NULL | [indexam.sgml#amvacuumcleanup](../../../../raw/postgres-17/doc/src/sgml/indexam.sgml#L418-L445), [hash.c#hashvacuumcleanup](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L647-L663), [nbtpage.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L178-L222) |
| ANALYZE overwrites every index unconditionally with `ceil(tupleFract * totalrows)` | [analyze.c#index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663), [analyze.c:449](../../../../raw/postgres-17/src/backend/commands/analyze.c#L449), [analyze.c#tupleFract-partial](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953), [analyze.c:612-621](../../../../raw/postgres-17/src/backend/commands/analyze.c#L612-L621) |
| Both writers store the value verbatim | [vacuum.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1409-L1461), [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2788-L2842) |
| A new index reads 0, a reset one reads -1, a partitioned one can never be counted | [relcache.c#RelationBuildLocalRelation](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3656-L3665), [index.c#InsertPgClassTuple-index](../../../../raw/postgres-17/src/backend/catalog/index.c#L1018-L1027), [heap.c:1006-1009](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1006-L1009), [relcache.c#RelationSetNewRelfilenumber-stats](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3943-L3954), [index.c:2900-2901](../../../../raw/postgres-17/src/backend/catalog/index.c#L2900-L2901), [analyze.c:419-427](../../../../raw/postgres-17/src/backend/commands/analyze.c#L419-L427) |
| Timestamp ordering cannot decide provenance | [vacuumlazy.c:3079](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3079), [system_views.sql#pg_stat_all_tables](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L670-L703) |
| The statement's two timeouts are session/transaction scope | [guc_tables.c:2611-2620](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c:2622-2631](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631) |
| The measurement's settings: `max_parallel_maintenance_workers` is session scope, `autovacuum` needs a reload | [guc_tables.c:3409-3417](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417), [guc_tables.c:1449-1457](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457) |
| A serial BRIN build counts its final range even when empty, so an empty table reads 1 | [brin.c#form_and_insert_tuple](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1975-L1989), [brin.c#brinbuild](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1091-L1261) |
| ANALYZE's partial-index value is a sample fraction, so it is not reproducible | [analyze.c#tupleFract-partial](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953) |

## Open Questions

1. **`indexam.sgml` contradicts the 17.11 code about `VACUUM VERBOSE`.** The documentation
   states that `amvacuumcleanup` statistics "will be reported by `VACUUM` if `VERBOSE` is
   given"
   ([indexam.sgml#amvacuumcleanup](../../../../raw/postgres-17/doc/src/sgml/indexam.sgml#L418-L445)),
   but the `ereport` that prints `num_index_tuples` sits in `vac_cleanup_one_index` at
   `ivinfo->message_level`
   ([vacuum.c#vac_cleanup_one_index](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2564-L2583)),
   and every call site that reaches it passes `DEBUG2`
   ([vacuumlazy.c:2477-2485](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2477-L2485)).
   What `VACUUM VERBOSE` actually prints per index is a page-only line
   ([vacuumlazy.c:718-732](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L732)).
   Per `AGENTS.md`, source wins; this page therefore does not claim `VERBOSE` shows the
   count. Whether the SGML wording is stale or intends "reported" loosely is unresolved,
   and the `DEBUG2` route was not measured on the server.
2. **Whether upstream considers the parallel BRIN overcount a bug is still unresolved**,
   though the 2026-08-27 review narrowed the history question: the count is written by
   `b4375717147` (parallel BRIN builds, first tagged `REL_17_BETA1`), `bs_numtuples` is
   touched by no other commit reachable from this pin except the original BRIN commit
   `7516f525941`, and the feature commit's own message describes the leader merge that
   makes the number wrong. Nothing outside this checkout may be cited here, so whether a
   later branch changed it cannot be answered from this page's evidence base.
3. **Only one `pages_per_range` value (32) and one table size were measured for BRIN.**
   Whether the parallel overcount ratio scales with `pages_per_range`, table size, or chunk
   allocation was not tested. Two independent sweeps now bracket the four-worker figure at
   305-330 on one 3712-block table, which measures run-to-run spread, not scaling.
4. **GIN opclasses beyond `array_ops` and `tsvector_ops` were not scored.** `jsonb_ops`,
   `jsonb_path_ops`, `trgm_ops` and the `btree_gin` opclasses may make the
   `rows * indnatts` lower bound tight or loose in ways not measured here.
5. **No SP-GiST ground truth is independent of the row count.** `pageinspect` ships no
   SP-GiST functions in this checkout, so the SP-GiST rows in the accuracy table compare
   `reltuples` against the table's row count, which is what the AM counts by construction —
   a weaker check than the other six access methods received.
6. **The `equals_table_rows` false-positive rate is unquantified.** It was observed on 2 of
   22 indexes in this fixture set; that number is a property of the fixtures, not an
   estimate for real schemas.
7. **Concurrency was not tested.** Every measurement ran with a single client and
   `autovacuum = off`. How the verdicts behave against a concurrent autovacuum or
   autoanalyze, which can move both the table's and the index's `reltuples` mid-statement,
   was not measured.
8. **Only `contrib/bloom` was tested as a non-core access method.** Other out-of-core AMs
   fall into the statement's `ELSE` branch with no unit label, and nothing here constrains
   what they count. This also limits the `zero: no storage yet` finding: the `relpages >= 1`
   floor was measured for the seven access methods in this fixture set, and an out-of-core
   AM whose `ambuild` allocates no page would reach that branch.
9. **The two `impossible` verdicts were exercised on one fixture set only.** Both fired
   correctly there — BRIN 3 of 3 and multi-column GIN 1 of 1 against an `ANALYZE`-written
   state — but no false positive was constructed for either, and the BRIN bound has one
   known blind spot beyond the undercounts above: a table whose `pg_class.relpages` is
   stale *high* would raise the bound and hide an overcount.

## Source References

- [genam.h#IndexBuildResult](../../../../raw/postgres-17/src/include/access/genam.h#L27-L34)
- [genam.h#IndexBulkDeleteResult](../../../../raw/postgres-17/src/include/access/genam.h#L56-L84)
- [amapi.h#ambuild_function](../../../../raw/postgres-17/src/include/access/amapi.h#L102-L105)
- [pg_class.h#Form_pg_class](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L32-L120)
- [pg_index.h#Form_pg_index](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L29-L63)
- [pg_am.h#Form_pg_am](../../../../raw/postgres-17/src/include/catalog/pg_am.h#L29-L41)
- [pg_statistic.h#stadistinct](../../../../raw/postgres-17/src/include/catalog/pg_statistic.h#L52-L69)
- [brin.h#BRIN_DEFAULT_PAGES_PER_RANGE](../../../../raw/postgres-17/src/include/access/brin.h#L39-L45)
- [index.c#index_create-pg_class](../../../../raw/postgres-17/src/backend/catalog/index.c#L1018-L1027)
- [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2788-L2956)
- [index.c#index_build-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3127-L3135)
- [nbtsort.c#btbuild-result](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L328-L338)
- [nbtsort.c#_bt_build_callback](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L576-L600)
- [nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L845-L924)
- [nbtree.c#btvacuumpage-counts](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1345-L1365)
- [nbtpage.c#_bt_vacuum_needs_cleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L178-L222)
- [hash.c#hashbuild](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L111-L195)
- [hash.c#hashbuildCallback](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L206-L242)
- [hash.c#hashbulkdelete-meta](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L586-L640)
- [hash.c#hashvacuumcleanup](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L642-L663)
- [hashutil.c#_hash_convert_tuple](../../../../raw/postgres-17/src/backend/access/hash/hashutil.c#L303-L335)
- [gistbuild.c#gistbuild-result](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L344-L355)
- [gistbuild.c#gistBuildCallback](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L819-L841)
- [gistvacuum.c#gistvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L71-L105)
- [spginsert.c#spgistBuildCallback](../../../../raw/postgres-17/src/backend/access/spgist/spginsert.c#L40-L67)
- [spginsert.c#spgbuild-result](../../../../raw/postgres-17/src/backend/access/spgist/spginsert.c#L136-L148)
- [spgvacuum.c#spgvacuumcleanup](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L941-L985)
- [gininsert.c#ginHeapTupleBulkInsert](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L246-L274)
- [gininsert.c#ginBuildCallback](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L276-L314)
- [gininsert.c#ginbuild-result](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L419-L428)
- [ginutil.c#initGinState](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L91-L113)
- [ginutil.c#ginExtractEntries](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L476-L557)
- [ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L694-L803)
- [brin.c#brinbuild](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1091-L1261)
- [brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1303-L1332)
- [brin.c#brinsummarize](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1866-L1960)
- [brin.c#form_and_insert_tuple](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1971-L2015)
- [brin.c#_brin_parallel_heapscan](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2559-L2596)
- [brin.c#_brin_parallel_merge](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2609-L2750)
- [brin.c#brin_fill_empty_ranges](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2966-L3004)
- [blinsert.c#blbuild-result](../../../../raw/postgres-17/contrib/bloom/blinsert.c#L140-L158)
- [blvacuum.c#blvacuumcleanup](../../../../raw/postgres-17/contrib/bloom/blvacuum.c#L168-L217)
- [vacuumlazy.c#verbose-index-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L732)
- [vacuumlazy.c#lazy_cleanup_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2349-L2405)
- [vacuumlazy.c#lazy_vacuum_one_index](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2407-L2458)
- [vacuumlazy.c#lazy_cleanup_one_index](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2460-L2507)
- [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099)
- [analyze.c#do_analyze_rel-indexes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L410-L480)
- [analyze.c#relstats-update](../../../../raw/postgres-17/src/backend/commands/analyze.c#L612-L677)
- [analyze.c#compute_index_stats-tupleFract](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L975)
- [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1300-L1366)
- [vacuum.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1369-L1461)
- [vacuum.c#vac_cleanup_one_index](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2559-L2583)
- [relcache.c#RelationBuildLocalRelation](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3656-L3665)
- [relcache.c#RelationSetNewRelfilenumber-stats](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3943-L3954)
- [heap.c#InsertPgClassTuple](../../../../raw/postgres-17/src/backend/catalog/heap.c#L899-L939)
- [heap.c#AddNewRelationTuple](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1000-L1016)
- [system_views.sql#pg_stat_all_tables](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L670-L703)
- [system_views.sql#pg_stat_all_indexes](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L790-L805)
- [catalogs.sgml#pg_class-preamble](../../../../raw/postgres-17/doc/src/sgml/catalogs.sgml#L1889-L1901)
- [catalogs.sgml#relpages-reltuples](../../../../raw/postgres-17/doc/src/sgml/catalogs.sgml#L2021-L2048)
- [indexam.sgml#ambuild](../../../../raw/postgres-17/doc/src/sgml/indexam.sgml#L276-L296)
- [indexam.sgml#ambulkdelete](../../../../raw/postgres-17/doc/src/sgml/indexam.sgml#L387-L416)
- [indexam.sgml#amvacuumcleanup](../../../../raw/postgres-17/doc/src/sgml/indexam.sgml#L418-L445)
- [monitoring.sgml#pg_stat_all_indexes](../../../../raw/postgres-17/doc/src/sgml/monitoring.sgml#L3931-L4047)
- [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620)
- [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)
- [guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417)
- [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457)

## Navigation

- [v17 index](../../index.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
- [v17 codebase navigation guide](../../codebase-navigation-guide.md)
- [v17: Detecting Inflated Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline](non-btree-index-inflation-comment-baseline.md)
- [v17: B-Tree Bloat and Wasted Space From pgstatindex Alone](btree-bloat-with-pgstatindex.md)
- [v17: How CREATE INDEX CONCURRENTLY Is Implemented](create-index-concurrently.md)
