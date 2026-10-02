---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# Calibrating a COMMENT-Stored Bytes-per-Table-Tuple REINDEX Threshold for Every Non-B-Tree Index in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Verdict](#verdict)
  - [Calibrated thresholds per access method](#calibrated-thresholds-per-access-method)
  - [Why the metric behaves the way it does in v12](#why-the-metric-behaves-the-way-it-does-in-v12)
  - [Recording the baseline with COMMENT ON INDEX](#recording-the-baseline-with-comment-on-index)
  - [The maintenance-time check](#the-maintenance-time-check)
  - [Index-specific factors](#index-specific-factors)
  - [Space reclaimed is not query performance](#space-reclaimed-is-not-query-performance)
  - [Failure modes that no threshold can fix](#failure-modes-that-no-threshold-can-fix)
  - [Operational recipe](#operational-recipe)
  - [Settings and their apply scope](#settings-and-their-apply-scope)
- [Test Summary](#test-summary)
  - [Environment and protocol](#environment-and-protocol)
  - [Fixture and index shapes](#fixture-and-index-shapes)
  - [Workloads](#workloads)
  - [Result matrix](#result-matrix)
  - [Threshold scoring](#threshold-scoring)
  - [Scale sweep](#scale-sweep)
  - [Access-method probes](#access-method-probes)
  - [COMMENT mechanics checked on the pin](#comment-mechanics-checked-on-the-pin)
  - [Reproducibility and cleanup](#reproducibility-and-cleanup)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Record a stable post-build baseline for every index except btree in its PostgreSQL index comment using `COMMENT ON INDEX`. Calculate the baseline as **index size in bytes divided by the table's pg_class.reltuples**, producing bytes per tuple. During maintenance, recalculate the ratio and compare it with the stored baseline; an increase indicates that the index is consuming more space per live tuple. For each index type and workload, determine the percentage increase that serves as the best proxy for triggering a reindex while minimizing unnecessary rebuilds and missed harmful bloat. Calibrate this threshold using realistic insert, update, and delete workloads, then rebuild each index and measure the actual space reclaimed and query-performance improvement. Include index-specific factors, such as the GIN pending list, when evaluating the accuracy of the proxy. Document a summary of the tests and how they were tested.

(The prompt as typed contained "postgreql 12", "bytes per tuples", a comma splice before "For each index type", "documment", and "how it was tested"; the user approved correcting all of them before this page was written.)

## Answer

### Verdict

The scheme works, but only for two of the five non-B-tree access methods, and only under a stated precondition. Measured on an isolated PostgreSQL 12.2 server built from this pin, over 132 measured cells (22 workloads x 6 index shapes) with `REINDEX` as ground truth:

- **GiST is the one access method where a stored baseline plus a fixed percentage calibrates cleanly.** A threshold anywhere in **20-30%** separated every "worth rebuilding" cell from every "not worth it" cell (14 true positives, 0 false positives, 0 false negatives), and a *fresh, zero-bloat* GiST index's ratio moved only ±3.84% across a 64x row-count range, so growth alone does not trip it.
- **hash and SP-GiST are usable only if the row count is roughly stable.** Their best thresholds (hash 9-11%, SP-GiST 29-32%) score 100% on a fixed-size table, but a freshly built, zero-bloat hash index reads anywhere from -20.31% to +49.42% purely from the bucket-allocation staircase, and a fresh SP-GiST index up to +33.08%. Both windows are narrower than their own no-bloat noise.
- **GIN needs a much higher threshold (50-75%) and still misclassifies**, because insert growth genuinely lowers GIN packing density and because the pending list moves the numerator for reasons a rebuild is the wrong answer to.
- **BRIN must never be rebuilt on this signal.** `REINDEX` reclaimed exactly 0.00% in all 22 BRIN cells, while the ratio moved between -87.50% and +9900.00%. Every firing is a false positive.

The reason the proxy works at all is a v12 property: plain `VACUUM` never returns index main-fork blocks to the operating system for any of these access methods, so the numerator only ever rises until a rebuild. `RelationTruncate` has exactly seven call sites in this tree, and the only index-side one is inside `TRUNCATE`'s immediate rebuild path [heap.c#RelationTruncateIndexes](../../../../raw/postgres-12/src/backend/catalog/heap.c#L3163-L3207); SP-GiST's index truncation is present but disabled under `#ifdef NOT_USED` with the comment "Note that btree doesn't do this either" [spgvacuum.c#spgvacuumscan](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L863-L886). Every access method instead recycles freed pages through the FSM fork [indexfsm.c#RecordFreeIndexPage](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L48-L55), which `pg_relation_size`'s default `'main'` fork does not count [pg_proc.dat#pg_relation_size](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L6883-L6887).

The reason it fails is the denominator. `pg_class.reltuples` is a `float4` estimate of live rows, and in this version there is no `-1` sentinel: the comment is exactly "# of tuples (not always up-to-date)" [pg_class.h:62-63](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L62-L63). It is refreshed by block-sampled `ANALYZE` [analyze.c#acquire_sample_rows](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1111-L1122), by old-density extrapolation in `VACUUM` [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1058-L1113), and — critically for a "post-build baseline" — by every index build, which rewrites the *heap's* `relpages` and `reltuples` as a side effect [index.c#index_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2986).

### Calibrated thresholds per access method

"Worth rebuilding" below means a `REINDEX` that reclaims at least 20% of the index's current bytes. `Window` is the measured gap between the highest reading among not-worth-it cells and the lowest reading among worth-it cells; any threshold inside the window scores perfectly on this data set. `Growth noise` is the spread of a *freshly built* index's ratio across 25,000 to 1,600,000 rows, which is the amount of drift a stored baseline accumulates with no bloat at all.

| Index type | Recommended threshold | Perfect window | TP / FP / FN / TN | Growth noise (fresh build) | Verdict |
|---|---|---|---|---|---|
| GiST | **25%** | 13.97% -> 33.33% | 14 / 0 / 0 / 8 | -0.29% to +3.84% | calibrates; noise is far below the threshold |
| SP-GiST | **30%** | 28.24% -> 32.17% | 15 / 0 / 0 / 7 | -4.80% to +33.08% | only with a stable row count; re-baseline on growth |
| hash | **10%** | 8.78% -> 11.11% | 16 / 0 / 0 / 6 | -20.31% to +49.42% | only with a stable row count; staircase swamps the window |
| GIN, `fastupdate = off` | **50%** | none at 20% (best 40-62%) | 16 / 2 / 0 / 4 | +13.78% to +80.48% | screening only |
| GIN, `fastupdate = on` | **75%** | 55.84% -> 100.00% | 18 / 0 / 0 / 4 | +13.78% to +80.48% | screening only; flush the pending list first |
| BRIN | **never fire** | none at any value | 0 / 4 / 0 / 18 | +700.00% to -87.50% | do not use; `REINDEX` reclaimed 0.00% in 22/22 cells |

The two right-hand columns come from different sweeps and use different reference points: the confusion counts are the 22 workload cells at a fixed 200,000 rows, the hash growth-noise range is the 60,000-row-referenced splitpoint sweep, and the other growth-noise ranges are the 200,000-row-referenced scale sweep. Both sweeps are reported in full under [Test Summary](#test-summary).

A single threshold for all five is worse than per-method values but not useless: 30% scored 90.2% accuracy over all 132 cells (78 TP, 12 FP, 1 FN, 41 TN), and 93.6% over the 110 non-BRIN cells (78 TP, 6 FP, 1 FN, 25 TN). Ten of the twelve false positives at 30% are BRIN.

Rank correlation between the reading and the reclaimable fraction is high for everything except BRIN: GiST 0.992, hash 0.987, GIN `fastupdate = on` 0.974, SP-GiST 0.958, GIN `fastupdate = off` 0.936, BRIN undefined (its reclaimable fraction has zero variance).

### Why the metric behaves the way it does in v12

The ratio mixes two independent quantities, and one of them is far noisier than the thing being measured.

**Numerator — monotone, but quantized per access method.** `pg_relation_size(index)` sums the segment files of one fork [dbsize.c#calculate_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L273-L308), and the one-argument form hardcodes `'main'` [pg_proc.dat#pg_relation_size](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L6883-L6887). Freed pages leave the main fork's high-water mark untouched:

- hash frees an overflow page by clearing a bitmap bit, never by truncating [hashovfl.c#_hash_freeovflpage](../../../../raw/postgres-12/src/backend/access/hash/hashovfl.c#L593-L641), and its README states it outright: "There is currently no provision to shrink a hash index, other than by rebuilding it with REINDEX" [hash/README:31-34](../../../../raw/postgres-12/src/backend/access/hash/README#L31-L34). `hashvacuumcleanup` only reports `RelationGetNumberOfBlocks` [hash.c#hashvacuumcleanup](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L641-L656).
- GiST does delete empty leaf pages in this version and records recyclable ones in the FSM [gistvacuum.c#gistvacuumpage](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c#L306-L317), gated on the page's deletion XID preceding `RecentGlobalXmin` [gistutil.c#gistPageRecyclable](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L883-L906), and reuses them through `gistNewBuffer` [gistutil.c#gistNewBuffer](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L813-L822) — inside the same file.
- GIN puts recyclable pages in the FSM and refreshes the metapage statistics [ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L755-L784).
- SP-GiST converts expired redirect tuples to placeholders and only removes placeholders at the end of a page [spgvacuum.c#vacuumRedirectAndPlaceholder](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L519-L530).
- BRIN's `ambulkdelete` is a no-op by design [brin.c#brinbulkdelete](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L766-L784), and `brinvacuumcleanup` only refreshes the FSM and adds summaries [brin.c#brin_vacuum_scan](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L1490-L1500).

**Denominator — an estimate with three distinct failure states.** Stale (nothing ran `ANALYZE`), extrapolated (a partial `VACUUM` reused the previous density for unscanned pages, [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1096-L1112)), or zero. Zero is ambiguous in v12 and means both "unknown tuple density" and "genuinely empty", as `heap_vacuum_rel` says in so many words [vacuumlazy.c#heap_vacuum_rel](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L320-L330).

Because the numerator cannot fall and the denominator can, a pure delete workload produces a reading that is a closed-form function of the delete fraction and carries **no information about the index at all**. Measured: every access method read exactly +11.11%, +33.33%, +100.00%, +300.00%, +900.00% and +9900.00% after deleting 10%, 25%, 50%, 75%, 90% and 99% of rows — that is `1/(1-f) - 1` to the cent — while the reclaimable fraction at +900.00% ranged from 84.58% (hash) to 89.36% (GiST) to 0.00% (BRIN).

### Recording the baseline with COMMENT ON INDEX

`COMMENT ON INDEX` accepts a string literal or `NULL` and nothing else — the grammar production is `Sconst | NULL_P` [gram.y#comment_text](../../../../raw/postgres-12/src/backend/parser/gram.y#L6589-L6592). Confirmed on the pin: `COMMENT ON INDEX i IS (SELECT '1.0')` and `COMMENT ON INDEX i IS 12.5` both fail with `syntax error`. A computed baseline therefore has to go through dynamic SQL. Other mechanics verified on the pin:

| Behavior | Evidence |
|---|---|
| Takes `ShareUpdateExclusiveLock` on the index, held to commit (measured: one `relation` lock on the index, none on the table) | [comment.c#CommentObject](../../../../raw/postgres-12/src/backend/commands/comment.c#L66-L73) |
| Requires ownership of the index (measured: `ERROR: must be owner of index t_cm_gin`) | [objectaddress.c#check_object_ownership](../../../../raw/postgres-12/src/backend/catalog/objectaddress.c#L2275-L2289) |
| One row per index in `pg_description`, `classoid = pg_class`, `objsubid = 0` (measured) | [comment.c#CreateComments](../../../../raw/postgres-12/src/backend/commands/comment.c#L142-L225) |
| `IS NULL` and `IS ''` both delete the row (measured: 0 rows after each) | [comment.c:154-156](../../../../raw/postgres-12/src/backend/commands/comment.c#L154-L156) |
| Canonical read is `obj_description(idx, 'pg_class')` | [pg_proc.dat#obj_description](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L2311-L2314) |
| Plain `REINDEX INDEX` keeps it: the OID does not change (measured: 18061 before and after) | [index.c#reindex_index](../../../../raw/postgres-12/src/backend/catalog/index.c#L3436-L3544) |
| `REINDEX INDEX CONCURRENTLY` keeps it by moving the row: OID changed 18061 -> 18063, still exactly one `pg_description` row (measured) | [index.c#index_concurrently_swap](../../../../raw/postgres-12/src/backend/catalog/index.c#L1612-L1656) |
| `DROP INDEX` deletes it | [dependency.c#deleteOneObject](../../../../raw/postgres-12/src/backend/catalog/dependency.c#L1313-L1320) |
| Any user can read it, so put no secrets in it | [ref/comment.sgml#Notes](../../../../raw/postgres-12/doc/src/sgml/ref/comment.sgml#L274-L286) |
| `CREATE TABLE ... (LIKE t INCLUDING ALL)` copies the numeric baseline onto the new, empty index (measured: clone carried `ratio=42.270720 size=2113536` while the clone index was 81,920 bytes with `reltuples = 0`) | [parse_utilcmd.c#transformTableLikeClause](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L1206-L1216) |

Upstream tests cover comment survival across `REINDEX TABLE` and `REINDEX TABLE CONCURRENTLY` [create_index.sql:845-854](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L845-L854), but nothing in the tree ties a comment to an index's size or bloat.

A tagged prefix keeps human text intact and is idempotent. Verified on the pin, including a re-stamp that neither duplicated the tag nor lost the sentence after it:

```sql
CREATE OR REPLACE FUNCTION wiki_bpt_stamp(idx regclass) RETURNS numeric
LANGUAGE plpgsql AS $$
DECLARE sz bigint; rt real; relid oid; r numeric; human text; tag text;
BEGIN
    SELECT /* wiki_bpt_stamp */ pg_relation_size(i.indexrelid), c.reltuples, c.oid
      INTO sz, rt, relid
      FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid
     WHERE i.indexrelid = idx;
    IF rt <= 0 THEN
        RAISE EXCEPTION 'reltuples is % for the table behind %; ANALYZE it first', rt, idx;
    END IF;
    r := sz::numeric / rt::numeric;
    human := btrim(regexp_replace(coalesce(obj_description(idx, 'pg_class'), ''),
                                  '\[wiki_bpt v1[^]]*\]', '', 'g'));
    tag := format('[wiki_bpt v1 ratio=%s size=%s reltuples=%s relid=%s at=%s]',
                  round(r, 6), sz, rt, relid, date_trunc('second', now()));
    EXECUTE format('COMMENT ON INDEX %s IS %L', idx::text, btrim(tag || ' ' || human));
    RETURN r;
END $$;
```

The `rt <= 0` guard matters: on a never-analyzed table the division is by zero, and v12 has no way to tell that apart from an empty table. Measured: an empty table with a hash index reported `relpages = 10`, `reltuples = 0` and 81,920 index bytes; after inserting 100,000 rows without `ANALYZE`, `reltuples` was still 0.

Recording `relid` in the tag is what lets a later check notice that the comment was copied to a different table by `INCLUDING ALL`.

### The maintenance-time check

Run this *after* `VACUUM (ANALYZE)`, never before. It refuses to score an index whose baseline was captured for a different relation, and it applies the per-method threshold from the table above.

```sql
SET statement_timeout = '60s';   -- session scope; use SET LOCAL inside a transaction block
SET lock_timeout = '5s';

SELECT /* wiki_bpt_check */
       c.relname                                        AS index_name,
       am.amname,
       pg_size_pretty(pg_relation_size(c.oid))          AS index_size,
       t.reltuples::numeric                             AS table_reltuples,
       round(b.baseline, 4)                             AS baseline_bytes_per_tuple,
       round(pg_relation_size(c.oid)::numeric
             / nullif(t.reltuples::numeric, 0), 4)      AS now_bytes_per_tuple,
       round(100 * (pg_relation_size(c.oid)::numeric
                    / nullif(t.reltuples::numeric, 0) / b.baseline - 1), 2) AS pct_increase,
       CASE am.amname WHEN 'gist' THEN 25 WHEN 'spgist' THEN 30 WHEN 'hash' THEN 10
                      WHEN 'gin' THEN 50 ELSE NULL END  AS threshold_pct,
       CASE
         WHEN am.amname = 'brin' THEN 'ignore: BRIN size does not track bloat'
         WHEN b.relid <> t.oid   THEN 'ignore: baseline was captured on another table'
         WHEN t.reltuples <= 0   THEN 'ignore: ANALYZE the table first'
         WHEN i.indpred IS NOT NULL THEN 'ignore: partial index, wrong denominator'
         WHEN 100 * (pg_relation_size(c.oid)::numeric
                     / nullif(t.reltuples::numeric, 0) / b.baseline - 1)
              >= CASE am.amname WHEN 'gist' THEN 25 WHEN 'spgist' THEN 30
                                WHEN 'hash' THEN 10 WHEN 'gin' THEN 50 END
           THEN 'candidate'
         ELSE 'ok'
       END                                              AS verdict
FROM pg_index i
JOIN pg_class c  ON c.oid = i.indexrelid
JOIN pg_class t  ON t.oid = i.indrelid
JOIN pg_am   am  ON am.oid = c.relam
CROSS JOIN LATERAL (
    SELECT (regexp_match(obj_description(c.oid, 'pg_class'),
                         '\[wiki_bpt v1 ratio=([0-9.]+)'))[1]::numeric AS baseline,
           (regexp_match(obj_description(c.oid, 'pg_class'),
                         'relid=([0-9]+)'))[1]::oid                    AS relid
) b
WHERE am.amname <> 'btree'
  AND b.baseline IS NOT NULL
  AND c.relpersistence = 'p'
ORDER BY 7 DESC NULLS LAST;
```

`indpred` is the partial-index guard; the measured reason for it is below. `pg_relation_size` needs no privileges in this version (there is no ACL check for it in `dbsize.c`, unlike `pg_database_size`), and comments are world readable, so the check runs as any login role; only stamping needs index ownership.

### Index-specific factors

**GIN pending list — the factor that breaks the proxy most convincingly.** With `fastupdate = on` (the v12 default, [gin_private.h:31](../../../../raw/postgres-12/src/include/access/gin_private.h#L31)), new entries land in a pending list until `nPendingPages * GIN_PAGE_FREESIZE` exceeds the effective limit [ginfast.c#ginHeapTupleFastInsert](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L438-L461). Measured on a 200,000-row baseline followed by 200,000 more rows with `gin_pending_list_limit = 256MB`:

| Stage | Index bytes | Reading vs baseline | Pending pages | Query blocks | Query ms |
|---|---|---|---|---|---|
| Pending list full | 23,232,512 | **+261.73%** | 2,444 | 3,779 | 11.259 |
| After `gin_clean_pending_list()` (returned 2,444 pages) | **31,391,744** | **+388.78%** | 0 | 1,336 | 1.393 |
| After `VACUUM (ANALYZE)` | 31,391,744 | +388.78% | 0 | — | — |
| After `REINDEX` | 8,224,768 | +28.06% | 0 | 1,336 | 0.912 |

Three separate problems in one table. The proxy fires at +261.73%; the correct, cheap fix is a pending-list flush, not a rebuild; and after that flush the reading gets **worse**, because the flush moves entries into the entry and data trees while the 2,444 emptied pending pages only go back to the FSM inside the same file [ginfast.c#shiftList](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L664-L665). The flush alone delivered the entire block-count improvement (3,779 -> 1,336, 2.8x) and 8.1x of the latency; the subsequent rebuild reclaimed 73.8% of the bytes and changed the block count not at all. A `fastupdate = off` control over the same inserts finished at 11,370,496 bytes (+77.04%) and rebuilt to 8,224,768 — the same rebuilt size, from a file 2.8x smaller. So on GIN, `fastupdate` alone moves bytes-per-tuple by a factor of nearly three with no difference in indexed content.

GIN size also is not per row: one heap row yields one entry per array element [ginarrayproc.c#ginarrayextract](../../../../raw/postgres-12/src/backend/access/gin/ginarrayproc.c#L50-L58), and the entry tree is keyed by value, so the numerator scales with distinct keys and posting-list compressibility rather than with the denominator.

**hash — three independent distortions.**

1. *The post-build baseline is not a property of the data.* `hashbuild` sizes the initial bucket count from `estimate_rel_size` of the heap, not from the rows it actually scans [hash.c#hashbuild](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L126-L130), and that estimator invents "10 pages of average-width rows" when `relpages = 0` [heapam_handler.c#heapam_estimate_rel_size](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2116-L2119). Measured on three tables with identical 200,000 rows: never analyzed before the build gave 930 pages / 896 buckets / **38.0928** bytes per row; analyzed first gave 843 / 768 / **34.5293**; built at one row then filled gave 908 / 652 / **37.1917**. That is a 10.3% spread in the "stable" baseline, which is comparable to the entire recommended threshold of 10%.
2. *Bucket allocation is a power-of-two staircase.* Buckets come in splitpoint groups [hashpage.c#_hash_init_metabuffer](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L508-L522), and a split extends the logical EOF across the whole group [hashpage.c#_hash_expandtable](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L781-L805). Measured fresh builds: 35.226 bytes/row at 60,000 rows, 30.193 at 70,000, **52.634** at 80,000, then falling monotonically to 28.071 at 150,000 before rising again to 34.529 at 200,000 — a 1.87x range with zero bloat anywhere.
3. *`pg_relation_size` counts pages the server never wrote.* `_hash_alloc_buckets` extends the fork by writing only the last block of the range and relying on the filesystem hole [hashpage.c#_hash_alloc_buckets](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L969-L979). Measured after growing 60,000 -> 130,000 rows: 652 pages of which **87 read back as all zeroes**; `pg_relation_size` said 5,341,184 bytes while `stat` reported 9,040 512-byte blocks = 4,628,480 allocated, i.e. exactly 87 x 8192 bytes of hole. `pgstattuple()` refuses such an index outright (`index "t_grow_hash" contains unexpected zero page at block 3096`), which it did in 4 of my 22 hash cells.

A fourth nuance: for hash, part of what `REINDEX` "reclaims" is re-bucketing, not dead space. After deleting 10% of rows and vacuuming, the index stayed at 6,905,856 bytes and 768 buckets; the rebuild produced 5,341,184 bytes and **640** buckets because `hashbuild` re-read the now-smaller `reltuples`. That is 22.66% reclaimed with no dead space involved.

**GiST — the well-behaved case, with one asterisk.** Build-time fillfactor sets page density [gistbuild.c#gistbuild](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c#L150-L153), but runtime inserts pass `freespace = 0` [gist.c#gistinsert](../../../../raw/postgres-12/src/backend/access/gist/gist.c#L176) and splits ignore fillfactor entirely — `gistfitpage` still carries a `/* TODO: Consider fillfactor */` [gistutil.c#gistfitpage](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L78-L89). That is exactly why insert-only growth did **not** inflate GiST's ratio in my runs (-6.83% to -7.37% at 2x to 8x) while churn did (+13.97% to +354.99%). The asterisk: GiST builds are not byte-deterministic. Re-running two identical cells reproduced 10 of 12 numbers exactly and differed only for GiST (84.62% vs 84.22%, 45.86% vs 45.72% reclaimed).

**SP-GiST — placeholders and an XID gate.** A deleted or moved leaf tuple leaves a redirect or placeholder occupying `SGDTSIZE` so later offsets do not shift, and a redirect becomes a placeholder only once its XID precedes `RecentGlobalXmin` [spgvacuum.c#vacuumRedirectAndPlaceholder](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L519-L530); only trailing placeholders are removed. Measured: after rewriting the indexed column on all 200,000 rows and before any `VACUUM`, the index read +160.86% with 67.97% of page bytes in use. Because the gate depends on the oldest snapshot in the cluster, the same maintenance window can score differently depending on unrelated long-running transactions.

**BRIN — the numerator has almost nothing to do with rows.** Total size is driven by heap block count divided by `pages_per_range` [brin.sgml#brin-intro](../../../../raw/postgres-12/doc/src/sgml/brin.sgml#L52-L60), with the revmap growing one page per `REVMAP_PAGE_MAXITEMS` ranges [brin_page.h#REVMAP_PAGE_MAXITEMS](../../../../raw/postgres-12/src/include/access/brin_page.h#L88-L94). Measured on one 200,000-row table: `pages_per_range = 128` gave 3 pages and 0.12288 bytes/row, `8` gave 4 pages and 0.16384, `1` gave 19 pages and 0.77824 — a 6.3x baseline spread from a reloption. Under churn the index stayed at exactly 24,576 bytes (reading +0.00%) while the same query went from 130 to 487 blocks, and the rebuild brought it only to 386 blocks with 0.00% bytes reclaimed. BRIN degrades in summary *precision*, which this metric cannot see, and the fix for that is `brin_desummarize_range` plus a summarization pass, not `REINDEX`.

### Space reclaimed is not query performance

The two payoffs the question asks about are only loosely related, and for two access methods they are unrelated.

Restricting to cells where a 30% threshold would fire, and comparing shared-buffer blocks touched by the representative single-index query before and after the rebuild:

| Index type | Cells fired | Cells with any block reduction | Mean block ratio | Max block ratio |
|---|---|---|---|---|
| GIN (either setting) | 19 | 9 | 12.62x | 221.67x |
| SP-GiST | 14 | 13 | 2.51x | 8.91x |
| GiST | 13 | 12 | 2.05x | 9.74x |
| hash | 14 | **0** | 1.00x | 1.00x |
| BRIN | 6 | **0** | 1.00x | 1.00x |

Hash equality lookups touched 1 to 3 blocks regardless of how bloated the index was, so a hash rebuild bought space and nothing else in every cell I measured. And the biggest query wins were not produced by the rebuild at all but by the `VACUUM` that should precede it:

| Index type | Workload | Reclaimed by rebuild | Query blocks before | after |
|---|---|---|---|---|
| GIN | 90% deleted, vacuumed | 82.40% | 3 | 3 |
| GIN | 90% deleted, **not** vacuumed | 89.80% | 665 | 3 |
| GiST | 90% deleted, vacuumed | 89.36% | 13 | 4 |
| GiST | 90% deleted, **not** vacuumed | 90.06% | 516 | 53 |
| SP-GiST | 90% deleted, vacuumed | 89.30% | 37 | 11 |
| SP-GiST | 90% deleted, **not** vacuumed | 89.23% | 757 | 85 |

Rebuild cost on the 200,000-row fixture, for weighing "unnecessary rebuilds": GiST 650.8 ms, SP-GiST 292.9 ms, GIN 156.7 ms, hash 120.3 ms, BRIN 19.4 ms.

### Failure modes that no threshold can fix

- **Stale `reltuples` inverts the answer.** The same GiST index at the same instant read **+84.71%** with `reltuples` left at 200,000 after the table doubled, and **-7.64%** one `ANALYZE` later with `reltuples = 400,000`. The index bytes were identical (25,829,376) in both readings.
- **Partial indexes get the wrong denominator, and it hides real bloat.** After `ANALYZE`, a partial index's own `reltuples` is the predicate subset, `ceil(tupleFract * totalrows)` [analyze.c#do_analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L612-L622), while the question's denominator is the whole table. Measured on a GiST index with `WHERE n < 10000` (20,000 of 200,000 rows): the baseline read 7.1270 against the table and 71.2704 against the index. After adding 200,000 rows whose qualifying members were then deleted and vacuumed, the index grew 1,425,408 -> 2,572,288 bytes (+80.4%) with the qualifying row count unchanged at 20,000 — and the metric read **-5.02%**, i.e. "improved". The rebuild reclaimed **44.59%**. This probe sits outside the 132-cell matrix, so it is not counted in the scoring above; inside the matrix the single false negative at a 30% threshold is hash `del10` (+11.11% read against 22.66% reclaimable). The partial-index miss is systematic rather than marginal, which is why the check excludes `indpred IS NOT NULL` outright.
- **A rebuild does not re-stamp the baseline.** Nothing in `reindex_index` or `index_concurrently_swap` rewrites a comment's contents, so after a rebuild the stored number still describes the pre-rebuild index. Re-stamping is a separate step the operator must perform.
- **A fresh rebuild does not return to the baseline.** The GIN case above rebuilt to +28.06% versus its own stored baseline, because a fresh build at 400,000 rows simply has a different bytes-per-tuple than a fresh build at 200,000.
- **`INCLUDING ALL` clones a wrong baseline** onto an empty index, as measured above. The `relid=` guard in the check catches it.
- **`pg_relation_size` on a partitioned index returns 0** in this version (no relkind check in `dbsize.c`), and a partitioned parent's `reltuples` is never written, since the non-inherited `ANALYZE` pass is skipped for `RELKIND_PARTITIONED_TABLE`. Apply the scheme per partition.

### Operational recipe

1. Stamp the baseline immediately after each build or rebuild, on a table that has just been analyzed. For hash, analyze *before* the build too, or the bucket count is sized from a guess.
2. At maintenance time, run `VACUUM (ANALYZE)` first, then read the ratio. Skipping `ANALYZE` produces readings that are wrong by tens of points; skipping `VACUUM` inflates both the reading and the apparent rebuild benefit.
3. For GIN, run `SELECT gin_clean_pending_list('idx')` (or rely on the `VACUUM`, which flushes the list) and only then compare. A firing that survives a flush is the only GIN firing worth acting on.
4. Apply the per-method threshold from the table above; treat BRIN as out of scope for this signal.
5. Before rebuilding, confirm the row count is comparable to the baseline's `reltuples=` field. If the table has grown by more than roughly 25%, re-stamp instead of rebuilding: for hash, SP-GiST and GIN the growth term alone can exceed the threshold.
6. Rebuild with `REINDEX INDEX CONCURRENTLY` if availability matters; it preserves the comment, as measured.
7. Re-stamp after the rebuild, and record the achieved reclaim so the threshold can be revisited with local data.

### Settings and their apply scope

Determined from the same-version GUC and reloption definitions:

| Setting | Kind | Default | Scope needed to change it |
|---|---|---|---|
| `gin_pending_list_limit` | GUC, `PGC_USERSET`, kB [guc.c#gin_pending_list_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3175-L3184) | 4096 kB | session/transaction (`SET`); also settable per index |
| `fastupdate` | GIN reloption [reloptions.c:127](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L127) | `true` | `ALTER INDEX`, takes `AccessExclusiveLock`; does not flush the existing list |
| `gin_pending_list_limit` | GIN reloption [reloptions.c:324](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L324) | -1 (use the GUC) | `ALTER INDEX`, `AccessExclusiveLock` |
| `pages_per_range` | BRIN reloption [reloptions.c:316](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L316) | 128 [brin.h:39](../../../../raw/postgres-12/src/include/access/brin.h#L39) | `ALTER INDEX`, `AccessExclusiveLock`; only a rebuild re-lays the index out |
| `autosummarize` | BRIN reloption [reloptions.c:100](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L100) | `false` | `ALTER INDEX`, `AccessExclusiveLock` |
| `fillfactor` | hash 75, GiST 90, SP-GiST 80 [hash.h:279](../../../../raw/postgres-12/src/include/access/hash.h#L279), [gist_private.h:465](../../../../raw/postgres-12/src/include/access/gist_private.h#L465), [spgist.h:25](../../../../raw/postgres-12/src/include/access/spgist.h#L25) | — | `ALTER INDEX`, `ShareUpdateExclusiveLock`; hash writes it into the metapage at build time only |
| `statement_timeout`, `lock_timeout` | GUC, `PGC_USERSET` | 0 | session/transaction |

No `postmaster`-context (restart) or `sighup`-context (reload) setting is required by anything on this page.

## Test Summary

### Environment and protocol

- Server built from this checkout only: `configure --prefix=.wiki-runtime/pg12/install --without-readline --without-zlib --enable-debug`; `postgres (PostgreSQL) 12.2`. contrib `pageinspect`, `pgstattuple` and `pg_freespacemap` installed from the same tree.
- Isolated throwaway cluster on port 55442 with a private socket directory under `.wiki-runtime/tmp/bpt/`. `shared_buffers = 512MB`, `maintenance_work_mem = 256MB`, `work_mem = 64MB`, `max_wal_size = 4GB`, `fsync = off`, `synchronous_commit = off`, **`autovacuum = off`**, `track_io_timing = on`, 8192-byte blocks.
- Autovacuum was disabled so that each cell's `VACUUM`/`ANALYZE` boundary is exactly where the script puts it. In production, autovacuum is what keeps the denominator fresh; the "stale `reltuples`" probe measures what happens when it does not.
- Per-cell protocol: build the table, load rows, `VACUUM (ANALYZE)`, create the six indexes, stamp each baseline via `COMMENT ON INDEX`, run the workload, reach the maintenance point (`VACUUM (ANALYZE)` unless the cell name says otherwise), read the ratio and the access-method internals, measure the query, `REINDEX INDEX`, measure size and query again, record one row per index.
- Ground truth for space is `pg_relation_size` before and after `REINDEX INDEX` on the same index. Ground truth for query work is the root-node shared blocks (hit + read) from `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` with `enable_seqscan = off`, median execution time over 7 runs, warm cache.
- Page density for every access method came from `page_header(get_raw_page(...))` over all pages, treating `pd_lower = 0` as an unwritten page, because `pgstattuple()` opens only btree, hash and GiST indexes in this version [pgstattuple.c#pgstattuple_internal](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L262-L286) and refuses hash indexes containing a splitpoint hole.

### Fixture and index shapes

One table per cell, every column a pure function of `id` so a rerun reproduces the same bytes: `n = (id*7919) % 100000` (hash key), `b = id` (BRIN key, perfectly correlated), `p = point((id*7919)%100000/1e5, (id*104729)%100000/1e5)` (GiST key), `tags`/`tags2 = ARRAY[(id*3)%1000, (id*7)%1000, (id*11)%1000, (id*13)%1000, (id*17)%1000]` (GIN keys, 5 entries per row over a 1,000-value vocabulary), `s = md5(id::text)` (SP-GiST radix key), `pad = repeat('x',40)` (never indexed). Baseline scale 200,000 rows, heap 5,406 pages.

Six indexes per table, covering all five core non-btree access methods plus the GIN pending-list variable: `hash (n)`, `gist (p)`, `gin (tags) WITH (fastupdate = off)`, `gin (tags2) WITH (fastupdate = on)`, `spgist (s)`, `brin (b)`. The two GIN indexes are on separate columns so each query can only choose one of them. Fresh sizes at 200,000 rows: hash 843 pages, GiST 1,713, GIN 392, SP-GiST 1,551, BRIN 3.

Representative queries, one per index: `n = 7919` (hash, index scan), `p <@ box '((0.40,0.40),(0.45,0.45))'` (GiST), `tags @> ARRAY[42]` and `tags2 @> ARRAY[42]` (GIN), `s >= 'ab' AND s < 'ac'` (SP-GiST), `b BETWEEN 100000 AND 100500` (BRIN).

### Workloads

22 labels, 132 cells. All maintenance points ran `VACUUM (ANALYZE)` except `del90_novac` (`ANALYZE` only) and the mid-workload vacuums noted below.

| Label | What it does after the baseline |
|---|---|
| `steady` | nothing; the control |
| `del10` ... `del99` | delete 10 / 25 / 50 / 75 / 90 / 99% of rows, spread evenly over all heap pages |
| `del90_novac` | delete 90%, then `ANALYZE` without `VACUUM` |
| `churn25` / `churn50` / `churn100` | `UPDATE ... SET n = n + 1` on 25 / 50 / 100% of rows (non-HOT: an indexed column changes, so all six indexes get new entries) |
| `churn200` / `churn400` | 2 / 4 full passes of the same update |
| `hot` | `fillfactor = 70` table, two full passes updating only `pad`; measured 241,920 of 400,000 updates were HOT (60.5%), so this is a partial-HOT workload, not a pure one |
| `grow2x` / `grow4x` / `grow8x` | insert to 2x / 4x / 8x the baseline row count, no updates or deletes |
| `turnover` | delete half the rows, `VACUUM`, re-insert the same number |
| `mixed` | three rounds of +40,000 inserts, 20% indexed-column updates, 10% deletes, with a `VACUUM` between rounds |
| `grow2x+churn50` | insert to 2x, then update the indexed column on half the rows |

### Result matrix

Each cell is `pct_increase / reclaimed_pct`. `pct_increase` is the reading the proxy produces at the maintenance point; `reclaimed_pct` is what `REINDEX INDEX` actually recovered.

| Workload | hash | GiST | GIN fu=off | GIN fu=on | SP-GiST | BRIN |
|---|---|---|---|---|---|---|
| `steady` | 0.00 / 0.00 | 0.00 / 0.17 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| `del10` | 11.11 / 22.66 | 11.11 / 7.72 | 11.11 / 8.42 | 11.11 / 8.42 | 11.11 / 10.12 | 11.11 / 0.00 |
| `del25` | 33.33 / 39.03 | 33.33 / 23.12 | 33.33 / 17.35 | 33.33 / 17.35 | 33.33 / 26.11 | 33.33 / 0.00 |
| `del50` | 100.00 / 39.03 | 100.00 / 48.57 | 100.00 / 39.03 | 100.00 / 39.03 | 100.00 / 51.84 | 100.00 / 0.00 |
| `del75` | 300.00 / 69.40 | 300.00 / 74.11 | 300.00 / 62.24 | 300.00 / 62.24 | 300.00 / 75.56 | 300.00 / 0.00 |
| `del90` | 900.00 / 84.58 | 900.00 / 89.36 | 900.00 / 82.40 | 900.00 / 82.40 | 900.00 / 89.30 | 900.00 / 0.00 |
| `del90_novac` | 900.00 / 84.58 | 900.00 / 90.06 | 900.00 / 89.80 | 900.00 / 89.80 | 900.00 / 89.23 | 900.00 / 0.00 |
| `del99` | 9900.00 / 98.81 | 9900.00 / 98.83 | 9900.00 / 97.70 | 9900.00 / 97.70 | 9900.00 / 98.52 | 9900.00 / 0.00 |
| `churn25` | 35.47 / 25.22 | 13.97 / 8.50 | 62.24 / 41.04 | 192.60 / 67.31 | 32.17 / 23.95 | 0.00 / 0.00 |
| `churn50` | 50.89 / 32.47 | 40.89 / 28.32 | 126.53 / 58.67 | 255.87 / 73.69 | 53.58 / 34.63 | 0.00 / 0.00 |
| `churn100` | 112.81 / 53.01 | 84.62 / 45.86 | 254.08 / 71.76 | 384.44 / 79.36 | 152.29 / 60.36 | 0.00 / 0.00 |
| `churn200` | 197.15 / 66.35 | 185.54 / 65.08 | 254.59 / 71.80 | 385.97 / 79.42 | 240.94 / 70.67 | 0.00 / 0.00 |
| `churn400` | 421.35 / 80.82 | 354.99 / 78.09 | 761.22 / 88.45 | 888.52 / 89.94 | 381.56 / 79.23 | 0.00 / 0.00 |
| `hot` | 81.38 / 44.87 | 67.99 / 37.16 | 246.11 / 55.39 | 379.02 / 67.77 | 105.35 / 50.96 | 0.00 / 0.00 |
| `grow2x` | 6.41 / 4.24 | -7.37 / -9.67 | 77.04 / 27.67 | 142.22 / 47.13 | 28.24 / -0.38 | -50.00 / 0.00 |
| `grow4x` | 8.30 / 5.34 | -7.11 / -11.41 | 111.10 / 14.50 | 133.23 / 22.61 | -3.35 / 0.28 | -75.00 / 0.00 |
| `grow8x` | 8.78 / 5.36 | -6.83 / -7.83 | 39.41 / 9.38 | 55.84 / 18.93 | -4.11 / 0.72 | -87.50 / 0.00 |
| `turnover` | 0.00 / 0.12 | 0.00 / -3.86 | 125.51 / 29.64 | 245.66 / 54.10 | 3.61 / 2.92 | 0.00 / 0.00 |
| `mixed` | 53.51 / 25.93 | 33.84 / 21.43 | 198.12 / 52.16 | 308.89 / 65.12 | 56.71 / 29.99 | -15.25 / 0.00 |
| `grow2x+churn50` | 48.70 / 30.08 | 42.02 / 27.06 | 169.13 / 52.56 | 198.60 / 57.24 | 72.86 / 25.66 | -50.00 / 0.00 |

Notes on reading it: negative `reclaimed_pct` means the rebuild produced a *larger* index (GiST at `grow2x`/`grow4x`/`grow8x`, and GiST `turnover` at -3.86%). `steady` proves the metric is quiet when nothing happens. `del*` readings are identical across access methods by construction, since only the denominator moved. `VACUUM` never shrank any index: `base_size` and `now_size` were byte-identical in every `del50`, `del90` and `del99` cell, for all six index shapes.

### Threshold scoring

Positive class: `REINDEX` reclaims at least 20% of current bytes. Grid searched at 1-point resolution from 0 to 300.

| Index type | Best threshold range | TP | FP | FN | TN | Accuracy |
|---|---|---|---|---|---|---|
| hash | 9 - 11 | 16 | 0 | 0 | 6 | 100.0% |
| GiST | 14 - 33 | 14 | 0 | 0 | 8 | 100.0% |
| SP-GiST | 29 - 32 | 15 | 0 | 0 | 7 | 100.0% |
| GIN `fastupdate = on` | 56 - 100 | 18 | 0 | 0 | 4 | 100.0% |
| GIN `fastupdate = off` | 40 - 62 | 16 | 2 | 0 | 4 | 90.9% |
| BRIN | 101 - 300 | 0 | 4 | 0 | 18 | 81.8% |

The two GIN `fastupdate = off` false positives are `grow4x` (+111.10% reading, 14.50% reclaimable) and `grow8x`/`del25`-class cells; the four BRIN false positives at its "best" threshold are simply the delete cells whose readings exceed any finite bound. Raising the positive class to 50% reclaimable makes GIN separable (126.53% -> boundary) but leaves BRIN unsalvageable at every setting.

A single all-method threshold, over all 132 cells: 20% -> 89.4% accuracy (13 FP, 1 FN); **30% -> 90.2%** (12 FP, 1 FN); 50% -> 86.4% (8 FP, 10 FN); 100% -> 79.5% (7 FP, 20 FN). Excluding BRIN: 30% -> 93.6% (6 FP, 1 FN).

### Scale sweep

Fresh builds at seven scales, identical fixture, `ANALYZE` before each build, no bloat present anywhere. Bytes per table tuple:

| Rows | Heap pages | hash | GiST | GIN | SP-GiST | BRIN |
|---|---|---|---|---|---|---|
| 25,000 | 676 | 42.598 | 71.434 | 23.265 | 84.541 | 0.983 |
| 50,000 | 1,352 | 42.271 | 69.960 | 20.808 | 62.259 | 0.492 |
| 100,000 | 2,703 | 42.107 | 70.779 | 18.268 | 60.703 | 0.246 |
| 200,000 | 5,406 | 34.529 | 70.164 | 16.056 | 63.529 | 0.123 |
| 400,000 | 10,811 | 35.185 | 71.107 | 20.562 | 81.777 | 0.061 |
| 800,000 | 21,622 | 35.400 | 72.858 | 28.979 | 61.225 | 0.031 |
| 1,600,000 | 43,244 | 35.548 | 70.682 | 20.285 | 60.477 | 0.015 |

Drift of each fresh build against the 200,000-row fresh build, in percent — this is the false-positive floor a stored baseline inherits from growth alone:

| Rows | hash | GiST | GIN | SP-GiST | BRIN |
|---|---|---|---|---|---|
| 25,000 | +23.37 | +1.81 | +44.90 | +33.08 | +700.00 |
| 50,000 | +22.42 | -0.29 | +29.59 | -2.00 | +300.00 |
| 100,000 | +21.95 | +0.88 | +13.78 | -4.45 | +100.00 |
| 400,000 | +1.90 | +1.34 | +28.06 | +28.72 | -50.00 |
| 800,000 | +2.52 | +3.84 | +80.48 | -3.63 | -75.00 |
| 1,600,000 | +2.95 | +0.74 | +26.34 | -4.80 | -87.50 |

Index page counts over the same scales show why: GiST is close to linear (218 / 427 / 864 / 1,713 / 3,472 / 7,115 / 13,805), hash is a staircase (130 / 258 / 514 / 843 / 1,718 / 3,457 / 6,943), SP-GiST is non-monotone in density (258 / 380 / 741 / 1,551 / 3,993 / 5,979 / 11,812), GIN is sub- then super-linear (71 / 127 / 223 / 392 / 1,004 / 2,830 / 3,962), and BRIN is constant at 3 pages. The GIN 400,000 and 800,000 points were re-measured on independent fixtures and reproduced exactly (1,004 pages / 20.5619 and 2,830 pages / 28.9792, with `n_entry_pages` 7 and `n_data_pages` 996 and 2,822 respectively, `n_entries` 1,000 in both). Note that this fixture holds distinct-key count fixed at 1,000 while rows grow, which is the regime where GIN size is dominated by posting-tree data pages.

### Access-method probes

Beyond the matrix, each measurement below was run as its own fixture:

- **GIN pending list**: four-stage table in [Index-specific factors](#index-specific-factors), plus the `fastupdate = off` control.
- **hash baseline instability**: three build paths, same 200,000 rows, 34.5293 / 38.0928 / 37.1917 bytes per row.
- **hash splitpoint staircase**: 11 fresh builds from 60,000 to 250,000 rows, bytes per row 28.071 to 52.634.
- **hash sparse hole**: 87 unwritten pages, `pg_relation_size` 5,341,184 vs 4,628,480 bytes allocated per `stat`.
- **hash re-bucketing**: 768 buckets before, 640 after the rebuild, 22.66% "reclaimed" from a 10% delete.
- **stale and zero `reltuples`**: +84.71% vs -7.64% for the same index; `NULL` ratio on a never-analyzed 100,000-row table.
- **partial index**: +80.4% real growth reported as -5.02%, 44.59% actually reclaimable.
- **SP-GiST pre-vacuum churn**: +160.86% with 67.97% page-byte occupancy.
- **BRIN reloption and precision**: 3 / 4 / 19 pages at `pages_per_range` 128 / 8 / 1; 130 -> 487 -> 386 query blocks across churn and rebuild at 0.00% bytes changed.
- **rebuild cost**: GiST 650.8 ms, SP-GiST 292.9 ms, GIN 156.7 / 155.7 ms, hash 120.3 ms, BRIN 19.4 ms at 200,000 rows.

### COMMENT mechanics checked on the pin

Every row of the table in [Recording the baseline with COMMENT ON INDEX](#recording-the-baseline-with-comment-on-index) was executed: the two syntax errors for a non-literal comment, tag-plus-human-text round-tripping and idempotent re-stamping, the `pg_description` row shape (`classoid = pg_class`, `objsubid = 0`), OID stability across plain `REINDEX` (18061 -> 18061) and OID change with comment survival across `REINDEX INDEX CONCURRENTLY` (18061 -> 18063, one row), deletion by `IS NULL` and by `IS ''`, the single `ShareUpdateExclusiveLock` on the index, a non-owner login role reading the baseline but failing to write it (`must be owner of index`), and `LIKE ... INCLUDING ALL` copying the numeric baseline onto an 81,920-byte empty clone.

### Reproducibility and cleanup

Two cells (`churn100`, `del50`) were re-run end to end after the first pass: 10 of 12 index-level results were identical to the digit, including byte-identical index sizes; only GiST differed (84.62% vs 84.22% reading, 45.86% vs 45.72% and 48.57% vs 48.83% reclaimed), consistent with an order-dependent `picksplit` and a size-dependent buffering-build decision. The duplicated pairs in the matrix (`churn`/`churn200` and `grow`/`grow4x`, run hours apart) likewise agreed exactly for five of six index shapes.

The test server was stopped and its data directory removed after the run; the SQL harness and captured output remain under `.wiki-runtime/tmp/bpt/`. `raw/postgres-12/` was never modified.

## Context Reviewed

- Comment storage and lifecycle: `comment.c`, `gram.y` (`CommentStmt`, `comment_text`), `objectaddress.c` (address resolution, ownership), `dependency.c` (deletion), `index.c` (`index_concurrently_swap`, `reindex_index`), `parse_utilcmd.c` (`LIKE`), `pg_description.h`, `indexing.h`, `pg_proc.dat` (`obj_description`), `ref/comment.sgml`, `create_index.sql` / `create_index.out`, `create_table_like.sql`.
- Size and statistics: `dbsize.c`, `pg_proc.dat` (`pg_relation_size`), `pg_class.h`, `vacuum.c` (`vac_update_relstats`, `vac_estimate_reltuples`), `vacuumlazy.c` (`heap_vacuum_rel`, `lazy_cleanup_index`, `lazy_truncate_heap`), `analyze.c` (`analyze_rel`, `do_analyze_rel`, `compute_index_stats`, `acquire_sample_rows`), `index.c` (`index_update_stats`, `index_build`), `heapam_handler.c` (`heapam_estimate_rel_size`, `heapam_index_build_range_scan`), `plancat.c` (`get_relation_info`, `estimate_rel_size`), `autovacuum.c` (`relation_needs_vacanalyze`), `storage.c` (`RelationTruncate` call sites), `catalogs.sgml`, `perform.sgml`, `func.sgml`.
- Access methods: `hash.c`, `hashpage.c`, `hashovfl.c`, `hashinsert.c`, `hashutil.c`, `hash.h`, `hash/README`; `gist.c`, `gistbuild.c`, `gistvacuum.c`, `gistutil.c`, `gist_private.h`, `gist/README`; `ginfast.c`, `ginvacuum.c`, `ginutil.c`, `gininsert.c`, `gindatapage.c`, `ginpostinglist.c`, `ginarrayproc.c`, `ginblock.h`, `gin_private.h`, `gin/README`, `gin.sgml`; `spgvacuum.c`, `spgutils.c`, `spgdoinsert.c`, `spgist_private.h`, `spgist.h`, `spgist/README`; `brin.c`, `brin_pageops.c`, `brin_revmap.c`, `brin_tuple.c`, `brin_page.h`, `brin.h`, `brin.sgml`.
- Shared infrastructure: `indexfsm.c`, `freespace.c`, `reloptions.c`, `guc.c`, `postgresql.conf.sample`, `genam.h` (`IndexVacuumInfo`, `IndexBulkDeleteResult`), `maintenance.sgml`, `ref/reindex.sgml`, `ref/create_index.sgml`.
- Tooling boundaries: `contrib/pgstattuple` (`pgstattuple.c`, `pgstatindex.c`, its SQL scripts and expected output), `contrib/pageinspect` (`ginfuncs.c`, `hashfuncs.c`, `brinfuncs.c` and its extension scripts), `contrib/pg_freespacemap`, `contrib/amcheck` (btree-only).
- Test surfaces: `src/test/regress/sql/{create_index,gin,gist,brin,spgist,hash_index,vacuum,dbsize,create_table_like}.sql`, `src/test/isolation/specs/vacuum-reltuples.spec`.

## Evidence Map

| Claim | Evidence |
|---|---|
| `COMMENT ON INDEX` accepts only a literal or `NULL` | [gram.y#comment_text](../../../../raw/postgres-12/src/backend/parser/gram.y#L6589-L6592) + measured syntax errors |
| It locks the index with `ShareUpdateExclusiveLock` | [comment.c#CommentObject](../../../../raw/postgres-12/src/backend/commands/comment.c#L66-L73) + measured `pg_locks` row |
| Empty string is folded to `NULL`, which deletes the row | [comment.c:154-156](../../../../raw/postgres-12/src/backend/commands/comment.c#L154-L156), [comment.c#CreateComments](../../../../raw/postgres-12/src/backend/commands/comment.c#L196-L206) |
| Index ownership is required to write a comment | [objectaddress.c#check_object_ownership](../../../../raw/postgres-12/src/backend/catalog/objectaddress.c#L2275-L2289) + measured error |
| `REINDEX ... CONCURRENTLY` moves the comment to the new OID | [index.c#index_concurrently_swap](../../../../raw/postgres-12/src/backend/catalog/index.c#L1612-L1656), [create_index.sql:845-854](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L845-L854) + measured OID change |
| `DROP INDEX` removes the comment | [dependency.c#deleteOneObject](../../../../raw/postgres-12/src/backend/catalog/dependency.c#L1313-L1320) |
| `LIKE ... INCLUDING ALL` copies index comments | [parse_utilcmd.c#transformTableLikeClause](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L1206-L1216) + measured clone |
| Comments are readable by any user | [ref/comment.sgml#Notes](../../../../raw/postgres-12/doc/src/sgml/ref/comment.sgml#L274-L286) + measured non-owner read |
| `pg_relation_size(idx)` measures the main fork only | [pg_proc.dat#pg_relation_size](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L6883-L6887), [dbsize.c#calculate_relation_size](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c#L273-L308) |
| `reltuples` is a `float4` estimate with no `-1` sentinel in v12 | [pg_class.h:59-66](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L59-L66), [vacuumlazy.c#heap_vacuum_rel](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L320-L330) |
| `VACUUM` extrapolates `reltuples` from the previous density | [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1058-L1113) |
| `ANALYZE` extrapolates from a block sample | [analyze.c#acquire_sample_rows](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1111-L1122) |
| An index build rewrites the heap's `relpages`/`reltuples` | [index.c#index_build](../../../../raw/postgres-12/src/backend/catalog/index.c#L2977-L2986), [index.c#index_update_stats](../../../../raw/postgres-12/src/backend/catalog/index.c#L2761-L2786) |
| Index `reltuples` refresh depends on the AM reporting an exact count | [vacuumlazy.c#lazy_cleanup_index](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L1803-L1812) |
| A partial index's own `reltuples` is the predicate subset | [analyze.c#do_analyze_rel](../../../../raw/postgres-12/src/backend/commands/analyze.c#L612-L622), [analyze.c#compute_index_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L817-L823) |
| The planner uses the table's tuple count for non-partial indexes | [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L387-L399) |
| No index AM truncates its main fork during VACUUM | [spgvacuum.c#spgvacuumscan](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L863-L886), [hash/README:31-34](../../../../raw/postgres-12/src/backend/access/hash/README#L31-L34), [hash.c#hashvacuumcleanup](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L641-L656) + measured byte-identical sizes |
| Freed index pages go to the FSM fork, which is not measured | [indexfsm.c#RecordFreeIndexPage](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c#L48-L55), [gistvacuum.c#gistvacuumpage](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c#L306-L317), [ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c#L755-L784) |
| GIN pending list flush threshold and the `gin_clean_pending_list` fix | [ginfast.c#ginHeapTupleFastInsert](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L438-L461), [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c#L1031-L1074) + measured four-stage table |
| `fastupdate` defaults to on | [gin_private.h:31](../../../../raw/postgres-12/src/include/access/gin_private.h#L31), [reloptions.c:127](../../../../raw/postgres-12/src/backend/access/common/reloptions.c#L127) |
| One GIN entry per array element | [ginarrayproc.c#ginarrayextract](../../../../raw/postgres-12/src/backend/access/gin/ginarrayproc.c#L50-L58) |
| Hash bucket count comes from a heap estimate, not the scan | [hash.c#hashbuild](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L126-L130), [heapam_handler.c#heapam_estimate_rel_size](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2116-L2119) + three measured builds |
| Hash grows in power-of-two splitpoint groups, extending the EOF over a hole | [hashpage.c#_hash_init_metabuffer](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L508-L522), [hashpage.c#_hash_alloc_buckets](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c#L969-L979) + measured 87 zero pages |
| GiST split ignores fillfactor, so inserts do not thin pages | [gistutil.c#gistfitpage](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L78-L89), [gist.c#gistinsert](../../../../raw/postgres-12/src/backend/access/gist/gist.c#L172-L180) |
| GiST deletes empty leaf pages under an XID gate | [gistutil.c#gistPageRecyclable](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L883-L906) |
| SP-GiST redirects become placeholders only past `RecentGlobalXmin` | [spgvacuum.c#vacuumRedirectAndPlaceholder](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c#L519-L530) |
| BRIN `ambulkdelete` is a no-op; cleanup only touches the FSM | [brin.c#brinbulkdelete](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L766-L784), [brin.c#brin_vacuum_scan](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L1490-L1500) |
| BRIN entry count is heap pages divided by `pages_per_range` | [brin.sgml#brin-intro](../../../../raw/postgres-12/doc/src/sgml/brin.sgml#L52-L60), [brin_page.h#REVMAP_PAGE_MAXITEMS](../../../../raw/postgres-12/src/include/access/brin_page.h#L88-L94) |
| `pgstattuple` cannot open GIN, SP-GiST or BRIN indexes | [pgstattuple.c#pgstattuple_internal](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c#L262-L286) |
| Upstream advises monitoring physical size for non-B-tree indexes | [maintenance.sgml#routine-reindex](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml#L874-L880) |
| `REINDEX` is the documented remedy for a bloated index | [ref/reindex.sgml](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml#L45-L58) |
| `gin_pending_list_limit` is `PGC_USERSET`, default 4096 kB | [guc.c#gin_pending_list_limit](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3175-L3184) |

## Open Questions

- All thresholds come from one fixture family on one platform (x86-64 Linux under WSL2, 8192-byte blocks, gcc 13.3). Key widths, key cardinality, opclass choice and `BLCKSZ` all move the constants; the windows for hash and SP-GiST are narrow enough that another fixture could invert them.
- The GIN measurements hold distinct-key count fixed at 1,000 while row count grows. A fixture whose distinct keys grow with rows would put GIN in a different size regime, and the +80.48% fresh-build drift at 800,000 rows may not generalize.
- The "worth rebuilding" boundary of 20% reclaimable is a judgement, not a measurement. Thresholds at 30% and 50% were scored, but no cost model ties reclaimed bytes and query blocks to an operational value.
- Query work was measured warm, single-client, with `enable_seqscan = off`, on one representative query shape per access method. Cold-cache behavior, concurrency, and plan-shape changes caused by bloat were not measured, and hash's flat result may be an artifact of a single-row equality probe.
- Timings were taken on WSL2 with `fsync = off` and `synchronous_commit = off`. Only the block counts and byte sizes should be treated as portable; the millisecond figures are indicative.
- Autovacuum was off. In production, autovacuum both refreshes the denominator and flushes the GIN pending list during its analyze pass, so the observed GIN readings are an upper bound on what a production maintenance window would see.
- SP-GiST's redirect-to-placeholder gate depends on the oldest snapshot in the cluster; no cell was run with a competing long-lived snapshot, so the worst-case SP-GiST reading under a held snapshot is unmeasured.
- The BRIN conclusion is derived from one correlated `int4` minmax column at three `pages_per_range` values. Inclusion opclasses, uncorrelated columns and much larger tables were not measured, though the size model in `brin.sgml` predicts the same insensitivity.
- GiST results are not bit-reproducible (measured spread ~0.4 points across identical runs), so its window edges carry that uncertainty.
- No upstream test asserts index size, page counts or bloat for any of these five access methods, and none ties a comment to size, so there is no in-tree regression coverage that would catch a future change invalidating this calibration.
- Cross-version behavior is out of scope here: v13 added B-tree deduplication and later versions changed `reltuples` to use a `-1` sentinel, so these constants must not be reused for another major version.

## Source References

- [comment.c](../../../../raw/postgres-12/src/backend/commands/comment.c)
- [gram.y](../../../../raw/postgres-12/src/backend/parser/gram.y)
- [objectaddress.c](../../../../raw/postgres-12/src/backend/catalog/objectaddress.c)
- [dependency.c](../../../../raw/postgres-12/src/backend/catalog/dependency.c)
- [index.c](../../../../raw/postgres-12/src/backend/catalog/index.c)
- [heap.c](../../../../raw/postgres-12/src/backend/catalog/heap.c)
- [parse_utilcmd.c](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c)
- [pg_proc.dat](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat)
- [pg_class.h](../../../../raw/postgres-12/src/include/catalog/pg_class.h)
- [dbsize.c](../../../../raw/postgres-12/src/backend/utils/adt/dbsize.c)
- [vacuum.c](../../../../raw/postgres-12/src/backend/commands/vacuum.c)
- [vacuumlazy.c](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c)
- [analyze.c](../../../../raw/postgres-12/src/backend/commands/analyze.c)
- [heapam_handler.c](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c)
- [plancat.c](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c)
- [indexfsm.c](../../../../raw/postgres-12/src/backend/storage/freespace/indexfsm.c)
- [reloptions.c](../../../../raw/postgres-12/src/backend/access/common/reloptions.c)
- [guc.c](../../../../raw/postgres-12/src/backend/utils/misc/guc.c)
- [hash.c](../../../../raw/postgres-12/src/backend/access/hash/hash.c)
- [hashpage.c](../../../../raw/postgres-12/src/backend/access/hash/hashpage.c)
- [hashovfl.c](../../../../raw/postgres-12/src/backend/access/hash/hashovfl.c)
- [hash.h](../../../../raw/postgres-12/src/include/access/hash.h)
- [hash/README](../../../../raw/postgres-12/src/backend/access/hash/README)
- [gist.c](../../../../raw/postgres-12/src/backend/access/gist/gist.c)
- [gistbuild.c](../../../../raw/postgres-12/src/backend/access/gist/gistbuild.c)
- [gistvacuum.c](../../../../raw/postgres-12/src/backend/access/gist/gistvacuum.c)
- [gistutil.c](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c)
- [gist_private.h](../../../../raw/postgres-12/src/include/access/gist_private.h)
- [ginfast.c](../../../../raw/postgres-12/src/backend/access/gin/ginfast.c)
- [ginvacuum.c](../../../../raw/postgres-12/src/backend/access/gin/ginvacuum.c)
- [ginutil.c](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c)
- [ginarrayproc.c](../../../../raw/postgres-12/src/backend/access/gin/ginarrayproc.c)
- [ginblock.h](../../../../raw/postgres-12/src/include/access/ginblock.h)
- [gin_private.h](../../../../raw/postgres-12/src/include/access/gin_private.h)
- [spgvacuum.c](../../../../raw/postgres-12/src/backend/access/spgist/spgvacuum.c)
- [spgutils.c](../../../../raw/postgres-12/src/backend/access/spgist/spgutils.c)
- [spgist.h](../../../../raw/postgres-12/src/include/access/spgist.h)
- [brin.c](../../../../raw/postgres-12/src/backend/access/brin/brin.c)
- [brin_page.h](../../../../raw/postgres-12/src/include/access/brin_page.h)
- [brin.h](../../../../raw/postgres-12/src/include/access/brin.h)
- [pgstattuple.c](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.c)
- [create_index.sql](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql)
- [maintenance.sgml](../../../../raw/postgres-12/doc/src/sgml/maintenance.sgml)
- [ref/comment.sgml](../../../../raw/postgres-12/doc/src/sgml/ref/comment.sgml)
- [ref/reindex.sgml](../../../../raw/postgres-12/doc/src/sgml/ref/reindex.sgml)
- [brin.sgml](../../../../raw/postgres-12/doc/src/sgml/brin.sgml)

## Navigation

- [v12 index](../../index.md)
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
- [Measuring B-Tree Index Bloat With Core SQL Only in PostgreSQL 12 (unverified)](btree-index-bloat-core-sql-only.md)
- [Physical Index Statistics, Tuple Counts, and Bytes per Tuple in PostgreSQL 12 (unverified)](physical-index-statistics-tuple-counts-and-bytes.md)
- [How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 12 (unverified)](reindex-index-concurrently.md)
- [PostgreSQL 12 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
