---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [The statement](#the-statement)
  - [How to read the output](#how-to-read-the-output)
  - [Follow-up: no threshold, no verdict column](#follow-up-no-threshold-no-verdict-column)
  - [Follow-up: wasted space measured against the fillfactor](#follow-up-wasted-space-measured-against-the-fillfactor)
  - [What one pgstatindex call actually measures](#what-one-pgstatindex-call-actually-measures)
  - [Why every candidate filter is there](#why-every-candidate-filter-is-there)
  - [The one behavioural difference between 12 and 17](#the-one-behavioural-difference-between-12-and-17)
  - [The model, from avg_leaf_density to a rebuilt size](#the-model-from-avg_leaf_density-to-a-rebuilt-size)
  - [Why the two page-layout constants are safe](#why-the-two-page-layout-constants-are-safe)
  - [wasted_vs_fillfactor is not est_reclaimable](#wasted_vs_fillfactor-is-not-est_reclaimable)
  - [NaN is the trap](#nan-is-the-trap)
  - [Mandatory test review](#mandatory-test-review)
  - [The mandatory suite, scored on both majors](#the-mandatory-suite-scored-on-both-majors)
  - [What it gets wrong, measured](#what-it-gets-wrong-measured)
  - [Deduplication changes the input, not the arithmetic](#deduplication-changes-the-input-not-the-arithmetic)
  - [What it costs to run](#what-it-costs-to-run)
  - [Privileges](#privileges)
  - [Locking, timeouts, and the concurrent-drop race](#locking-timeouts-and-the-concurrent-drop-race)
  - [How this was measured](#how-this-was-measured)
- [Measurement Script](#measurement-script)
  - [How to use the two leg scripts](#how-to-use-the-two-leg-scripts)
  - [The shared suite's harness](#the-shared-suites-harness)
  - [Family 1, the deduplication gate](#family-1-the-deduplication-gate)
  - [Families 2 to 6, tests 18 to 120](#families-2-to-6-tests-18-to-120)
  - [Rule 2, the uniform drain](#rule-2-the-uniform-drain)
  - [Rule 3, the census, and the forgeries](#rule-3-the-census-and-the-forgeries)
  - [The PostgreSQL 17 leg script](#the-postgresql-17-leg-script)
  - [The PostgreSQL 12 leg script](#the-postgresql-12-leg-script)
  - [The last run](#the-last-run)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 17: provide SQL that uses `pgstatindex` only, for B-tree indexes,
to report bloat and wasted space. Make sure that it works on v12 and v17.

Prompt note: the request was filed as `in postgresql 17 , question:  provide sql
that using pgstatindex only for btree indexes to report bloat, wasted space,
make sure that it works on v12 and v17`. It had lowercase `postgresql` and `sql`,
a space before a comma, a double space, `that using` for `that uses`, `btree` for
`B-tree`, and two comma splices; the asker approved the corrected restatement
above. Four scoping answers are recorded with it: `pgstatindex` is the only
measurement function, while `pg_class`, `pg_index`, `pg_am`, `pg_namespace` and
`pg_relation_size` may be read to choose, size and label indexes; the deliverable
is one statement that runs unchanged on both majors; the statement was executed on
isolated 12.2 and 17.11 servers and scored against `REINDEX INDEX`; and it is filed
as a new page rather than a follow-up on
[Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17](btree-index-bloat-core-sql-only.md),
which is deliberately the no-contrib method.

Follow-up: remove `alert_pct`. Report only the index statistics and the estimate
of wasted space.

> Prompt note: filed as an approved corrected restatement of `in postgresql 17 ,
> for question: B-Tree Bloat and Wasted Space From pgstatindex Alone, on
> PostgreSQL 12 and 17 (unverified) , remove the alert_pct , just report on the
> index stats and estimation of wasted space`, per the repository's
> prompt-hygiene rule; the original had `agents.md` for AGENTS.md, lowercase
> `postgresql`, three spaces before commas, and a comma splice. Three scoping
> answers are recorded with it: the `status` column goes with `alert_pct`,
> because the parameter existed only to drive it; the `notes` column stays
> exactly as it was; and both retained servers were restarted, their fixtures
> rebuilt, and the amended text run on each.

Second follow-up: adjust every wasted-space-related calculation to the index
fillfactor.

> Prompt note: filed as an approved corrected restatement of `follow agents.md,
> in postgresql 17 , for question: B-Tree Bloat and Wasted Space From
> pgstatindex Alone, on PostgreSQL 12 and 17 (unverified) , adjust any wasted
> space related calculation to the index fillfactor`, per the repository's
> prompt-hygiene rule; the original had `agents.md` for AGENTS.md, lowercase
> `postgresql`, two spaces before commas, and unhyphenated `wasted space
> related`. Four scoping answers are recorded with it: the baseline is the
> build-code target density the estimate already uses,
> `(leaf_capacity - BLCKSZ * (100 - fillfactor) / 100) / leaf_capacity`, not the
> literal `fillfactor / 100`, so both columns rest on one target; an index denser
> than that target reports zero rather than a negative number; the two output
> columns are renamed `wasted_vs_fillfactor` and `wasted_ff_pct` so the baseline
> is in the name and no old output is silently reinterpreted; and both retained
> servers were restarted and both texts run on each.

Review: following AGENTS.md, review this question page for PostgreSQL 17.

> Prompt note: filed as an approved corrected restatement of `follow agents.md,
> in postgresql 17,  review question: B-Tree Bloat and Wasted Space From
> pgstatindex Alone, on PostgreSQL 12 and 17 (unverified)`, per the
> repository's prompt-hygiene rule; the original had `agents.md` for AGENTS.md,
> lowercase `postgresql`, a double space after the comma, and no finite verb.
> Four scoping answers are recorded with it: re-read every citation against the
> pinned checkout **and** rebuild both servers and re-measure; repair whatever
> the review finds, in place; and add the mandatory `## Measurement Script`
> section with a runnable script, then run it. What that review found was
> re-measured again by the 2026-09-11 revision, under
> [The mandatory suite, scored on both majors](#the-mandatory-suite-scored-on-both-majors);
> the corrections carried in
> [Locking, timeouts, and the concurrent-drop race](#locking-timeouts-and-the-concurrent-drop-race),
> [The one behavioural difference between 12 and 17](#the-one-behavioural-difference-between-12-and-17)
> and [Why the two page-layout constants are safe](#why-the-two-page-layout-constants-are-safe),
> and the new [Measurement Script](#measurement-script) section.

Fourth follow-up: following AGENTS.md, for PostgreSQL 17: on this question
page, replace the mandatory tests with the tests on the common concept page
*Mandatory B-Tree Bloat Tests*, and keep the link to that common concept page.

> Prompt note: filed as an approved corrected restatement of `follow agents.md,
> in postgresql 17, for question:  B-Tree Bloat and Wasted Space From
> pgstatindex Alone, on PostgreSQL 12 and 17 (unverified), replace the mandatory
> test by tests on common-concept: # Mandatory B-Tree Bloat Tests (unverified),
> keep the link with the common concept.`, per the repository's prompt-hygiene
> rule; the original had `agents.md` for AGENTS.md, lowercase `postgresql`, a
> double space after `question:`, a stray `#` before the concept page's title,
> the `(unverified)` hint treated as part of both titles, `the mandatory test`
> for a whole suite of tests, `replace ... by` for `replace ... with`, `on
> common-concept:` for "on the common concept page", and `keep the link with`
> for "keep the link to". Four scoping answers are recorded with it: the shared
> suite **replaces the fixture suite** the two leg scripts used to build, so the
> 32 fixtures of schema `bl` are retired as the scored population and only the
> guard and model shapes the suite does not cover stay; **both legs run end to
> end**, built from their pins and checked before a fixture exists; the numbers
> the old `bl` suite produced are **replaced**, so the shared suite's scoring is
> this page's only acceptance evidence; and the concept page itself was not
> edited, per the read-only rule for common concept documents.

Second review: following AGENTS.md, review this question page for PostgreSQL 17.

> Prompt note: filed as an approved corrected restatement of `follow agents.md,
> in postgresql 17, review  question:  B-Tree Bloat and Wasted Space From
> pgstatindex Alone, on PostgreSQL 12 and 17 (unverified)`, per the repository's
> prompt-hygiene rule; the original had `agents.md` for AGENTS.md, lowercase
> `postgresql`, and two double spaces. Four scoping answers are recorded with
> it: a **full claim-by-claim** review rather than a targeted one; **build both
> servers and re-measure** rather than a source-only pass; **repair in place**;
> and the corrected prompt recorded here. What the review found is under
> [What the 2026-09-12 review repaired](#what-the-2026-09-12-review-repaired):
> six defects in this page's port of the shared suite, three claims narrowed
> because measurement contradicted them, and the two `Follow-up` sections'
> comparison tables re-derived on the current population by a new `compare`
> stage.

Fifth follow-up: following AGENTS.md, for PostgreSQL 17: update this page's
tests from the common concept page *Mandatory B-Tree Bloat Tests*, and re-run
the tests.

> Prompt note: filed as an approved corrected restatement of `follow agents.md,
> in postgresql 17, for question:  B-Tree Bloat and Wasted Space From
> pgstatindex Alone, on PostgreSQL 12 and 17 (unverified) , update test from the
> common-concepts and re-run the tests.`, per the repository's prompt-hygiene
> rule; the original had `agents.md` for AGENTS.md, lowercase `postgresql`, a
> double space after `question:`, a space before the comma, `update test` for a
> whole suite of tests, and `the common-concepts` for "the common concept page".
> Four scoping answers are recorded with it: the update is the **narrowing plus
> a full re-sync**, so the eight fixtures the concept page retired on 2026-09-12
> are removed *and* every remaining fixture, rule and band is re-checked against
> that page line by line; **both legs run end to end**, builds and regression
> suites included; the claims that rested on the retired fixtures are
> **re-derived from the new run**, with the coverage those fixtures carried
> filed as an open question rather than kept as stale numbers; and the concept
> page itself was again not edited, per the read-only rule. What changed is
> under [What the re-sync to the narrowed suite changed](#what-the-re-sync-to-the-narrowed-suite-changed).

Sixth follow-up: following AGENTS.md, for PostgreSQL 17: remove the "skip
anything smaller" size filter from the statement.

> Prompt note: filed as an approved corrected restatement of `follow agents.md,
> in postgresql 17, for question:  B-Tree Bloat and Wasted Space From
> pgstatindex Alone, remove skip anything smaller filter from the statement.`,
> per the repository's prompt-hygiene rule; the original had `agents.md` for
> AGENTS.md, lowercase `postgresql`, a double space after `question:`, the page
> title without its `, on PostgreSQL 12 and 17` suffix, and `remove skip
> anything smaller filter` without its article or its quotation marks. Four
> scoping answers are recorded with it: the **whole predicate goes**, the
> `min_index_bytes` parameter and the `pg_relation_size` call together, so
> `pgstatindex` is now the only function the statement measures with and the
> concurrent-drop shield that call provided goes with it; **both legs run end
> to end** from their pins, so every number the filter touched is re-derived
> rather than adjusted; the sections that existed to explain the filter are
> **rewritten in place**, with no filter-era narrative and no history section
> kept; and the concept page was read and again not edited, per the read-only
> rule.

Third review and its execution: following AGENTS.md, for PostgreSQL 17, review
this question page without fixing anything, and list the fixes and a plan. Then
carry out that plan.

> Prompt note: filed as an approved corrected restatement of two prompts. The
> first was `follow agents.md, in postgresql 17 , review question: # B-Tree
> Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17
> (unverified), do not fix anything just list fixes and plan.`; it had
> `agents.md` for AGENTS.md, lowercase `postgresql`, a space before the comma, a
> stray `#` before the page title, the `(unverified)` hint treated as part of
> the title, and a comma splice before `just`. The second was `execute plan`,
> which lacks its article. Scope was settled by the two prompts themselves: the
> first review changed nothing and listed fixes and a plan in the conversation;
> the second carried out the whole plan. That plan retired tests 11, 11b and 38
> from the port, applied the concept page's maintenance assumption to the nine
> churned recipes that lacked it, repaired the source-only defects the review
> found, re-ran both legs from their pins, re-derived every measured number, and
> left the concept page unedited, per the read-only rule. One reading was the
> executor's rather than the concept page's: 66, 115 and 119 are treated as
> churned because each writes rows after its index build, although the concept
> page names only 64, 92 to 95, 98 and 118. What changed is under
> [What the maintenance assumption changed](#what-the-maintenance-assumption-changed).

Fourth review: following AGENTS.md, in PostgreSQL 17, review the question page
*B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17*.

> Prompt note: filed as an approved corrected restatement of `follow agents.md,
> in postgresql 17, review : btree-bloat-with-pgstatindex.md`, per the
> repository's prompt-hygiene rule; the original had `agents.md` for AGENTS.md,
> lowercase `postgresql`, a space before the colon, a lowercase sentence start,
> and the page named by its filename rather than by its title. Three scoping
> answers are recorded with it: **re-verify every citation against the pin and
> re-run both legs**, rather than a source-only or list-only pass; **repair in
> place**; and the corrected prompt recorded here. The pass found one thing the
> earlier ones could not have: the concept page gained
> `### The maintenance must not be defeated` on 2026-09-15, after this page's
> last run, and this page is the last of its three consumers to be brought onto
> it. What that changed is under
> [The maintenance, proved not defeated](#the-maintenance-proved-not-defeated).


## Answer

### The statement

One statement, eight stages, and `pgstatindex` is the only function it measures
with. It prefilters nothing: every B-tree index the function accepts is read,
including the catalog's own. On the fixture database of the run behind this
revision it returned 350 rows on the 12.2 server and 365 on the 17.11 server,
from the same text, unmodified.

```sql
-- B-tree bloat and wasted space from pgstatindex alone.
-- Runs unchanged on PostgreSQL 12 and 17.
--
--   params    the two page-layout constants
--   cand      every index pgstatindex can be called on without raising
--   measured  one pgstatindex() call per candidate
--   modelled  per-index constants: leaf capacity, fillfactor, target free space
--   sized     bytes holding entries, dead-page bytes, the fillfactor target
--   est       leaf pages a rebuild at this index's fillfactor would need
--   final     the modelled rebuilt size
--
-- wasted_vs_fillfactor measures the file against a rebuild at this index's own
-- fillfactor: free bytes in live leaf pages beyond what such a build leaves,
-- never below zero, plus every empty and deleted page.  est_reclaimable is the
-- same target read as a file size, which is what REINDEX gives back.
-- The statement sets no threshold and reaches no verdict.  It reports the
-- measurements and the estimate, ordered by est_reclaimable, largest first.

SET statement_timeout = '15min';
SET lock_timeout = '5s';

WITH params AS (
    SELECT current_setting('block_size')::bigint AS bs,
           24::bigint      AS page_header,    -- SizeOfPageHeaderData
           16::bigint      AS btree_special   -- MAXALIGN(sizeof(BTPageOpaqueData))
),
cand AS MATERIALIZED (
    SELECT c.oid       AS idx_oid,
           n.nspname   AS schema_name,
           c.relname   AS index_name,
           t.relname   AS table_name,
           (SELECT o.option_value::int
              FROM pg_options_to_table(c.reloptions) o
             WHERE o.option_name = 'fillfactor') AS fillfactor_opt
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_index x     ON x.indexrelid = c.oid
      JOIN pg_class t     ON t.oid = x.indrelid
      JOIN pg_am a        ON a.oid = c.relam
     WHERE a.amname = 'btree'                        -- pgstatindex takes no other AM
       AND c.relkind = 'i'                           -- not 'I', a partitioned index has no storage
       AND x.indisvalid AND x.indisready AND x.indislive
       AND NOT pg_is_other_temp_schema(c.relnamespace)
       AND (c.relpersistence <> 'u' OR NOT pg_is_in_recovery())
),
measured AS (
    SELECT c.*, s.*
      FROM cand c, LATERAL pgstatindex(c.idx_oid::regclass) s
),
modelled AS (
    SELECT m.*,
           p.bs,
           p.bs - p.page_header - p.btree_special AS leaf_capacity,
           COALESCE(m.fillfactor_opt, 90)         AS fillfactor,
           -- what a build leaves free on a leaf page: BLCKSZ * (100 - fillfactor) / 100
           (p.bs * (100 - COALESCE(m.fillfactor_opt, 90))) / 100 AS target_free,
           m.empty_pages + m.deleted_pages        AS dead_pages,
           -- an index with no leaf pages reports NaN; NaN sorts above every
           -- number, so it must never reach a comparison
           CASE WHEN m.leaf_pages > 0 AND m.avg_leaf_density <> 'NaN'::float8
                THEN (m.avg_leaf_density / 100)::numeric
                ELSE 0::numeric END               AS density
      FROM measured m CROSS JOIN params p
),
sized AS (
    SELECT d.*,
           d.leaf_pages * d.leaf_capacity                       AS leaf_bytes,
           round(d.leaf_pages * d.leaf_capacity * d.density)    AS live_leaf_bytes,
           d.dead_pages * d.bs                                  AS dead_bytes,
           (d.leaf_capacity - d.target_free)::numeric / d.leaf_capacity AS target_density
      FROM modelled d
),
est AS (
    SELECT s.*,
           -- free leaf bytes a rebuild at this fillfactor would not leave,
           -- never negative, plus pages that hold nothing at any fillfactor
           GREATEST(round(s.leaf_bytes * s.target_density) - s.live_leaf_bytes, 0)
               + s.dead_bytes AS wasted_vs_fillfactor,
           CASE WHEN s.leaf_pages = 0 THEN 0
                ELSE ceil(s.leaf_pages * s.density / s.target_density) END
               AS est_leaf_pages
      FROM sized s
),
final AS (
    SELECT e.*,
           (1 + e.est_leaf_pages
              + CASE WHEN e.leaf_pages = 0 THEN 0
                     ELSE round(e.internal_pages * e.est_leaf_pages / e.leaf_pages) END
           ) * e.bs AS est_rebuilt_bytes
      FROM est e
)
SELECT /* wiki_btree_bloat_pgstatindex_12_17 */
       f.schema_name,
       f.index_name,
       f.table_name,
       pg_size_pretty(f.index_size) AS index_size,
       f.leaf_pages,
       f.dead_pages,
       CASE WHEN f.leaf_pages > 0 THEN round(f.avg_leaf_density::numeric, 2) END
           AS avg_leaf_density,
       CASE WHEN f.leaf_pages > 0 THEN round(f.leaf_fragmentation::numeric, 2) END
           AS leaf_fragmentation,
       pg_size_pretty(f.wasted_vs_fillfactor::bigint) AS wasted_vs_fillfactor,
       round(100 * f.wasted_vs_fillfactor / f.index_size, 1) AS wasted_ff_pct,
       pg_size_pretty(f.est_rebuilt_bytes::bigint) AS est_rebuilt_size,
       pg_size_pretty((f.index_size - f.est_rebuilt_bytes)::bigint) AS est_reclaimable,
       round(100 * (f.index_size - f.est_rebuilt_bytes) / f.index_size, 1)
           AS est_reclaimable_pct,
       array_to_string(array_remove(ARRAY[
           CASE WHEN f.leaf_pages = 0 THEN 'no leaf pages' END,
           CASE WHEN f.version < 4 THEN 'metapage version ' || f.version END,
           CASE WHEN f.fillfactor <> 90 THEN 'fillfactor ' || f.fillfactor END,
           CASE WHEN f.leaf_pages > 0 AND f.leaf_fragmentation >= 30
                THEN 'fragmented, not wasted space' END,
           CASE WHEN 100 * (f.index_size - f.est_rebuilt_bytes) / f.index_size <= -1
                THEN 'denser than a rebuild would leave it' END,
           CASE WHEN f.dead_pages > 0
                 AND f.dead_bytes >= (f.index_size - f.est_rebuilt_bytes) / 2
                 AND f.index_size > f.est_rebuilt_bytes
                THEN 'reclaim is mostly empty/deleted pages' END
       ], NULL), '; ') AS notes
  FROM final f
 ORDER BY f.index_size - f.est_rebuilt_bytes DESC;
```

It needs `CREATE EXTENSION pgstattuple` in the database being examined. On 17
the default version is 1.5, whose upgrade script defines the `regclass` form
the statement calls
([pgstattuple.control:1-5](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.control#L1-L5),
[pgstattuple--1.4--1.5.sql#pgstatindex-regclass](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)).
That the 12.2 server offers the same form is measured, not cited: its
`cluster` stage installed the extension and recorded version `1.5`, and the
filed text ran there unmodified.

`statement_timeout` and `lock_timeout` are both `PGC_USERSET`
([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620),
[guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)),
so they apply at session/transaction scope and need no reload or restart. The
statement timeout is minutes, not seconds, because this report reads every page
of every index it reports on; see [What it costs to run](#what-it-costs-to-run).

### How to read the output

Read `est_reclaimable_pct` first. It is the modelled answer to "how much smaller
would `REINDEX INDEX` make this file", and against a measured rebuild of every
fixture of the wiki's shared mandatory suite it landed within one point of the
truth on 93 of 126 fixtures on 17.11 and 100 of 117 on 12.2, within five points
on 125 and 116, and never over-estimated by more than ten points
([the scoring](#the-mandatory-suite-scored-on-both-majors)). The
statement itself reaches no verdict. It carries no threshold, labels no row, and
returns the measurements and the estimate ordered by estimated reclaim, largest
first. Why the column that used to carry a verdict is gone, and where the
threshold belongs instead, is
[Follow-up: no threshold, no verdict column](#follow-up-no-threshold-no-verdict-column).

Read the other columns as supporting detail:

| Column | Means | Watch for |
|---|---|---|
| `wasted_vs_fillfactor`, `wasted_ff_pct` | Free bytes inside live leaf pages beyond what a build at this index's fillfactor leaves, never below zero, plus every empty and deleted page | A fresh index reports 0.0 at any fillfactor. It counts payload bytes, so it runs about `(leaf_capacity - target_free) / block_size` of `est_reclaimable_pct` — 0.895 of it at 8192/90 |
| `avg_leaf_density` | Share of leaf-page space holding entries | Low density is the usual bloat signal, but it is blind to whole pages that hold nothing, and a low number is normal at a low fillfactor |
| `dead_pages` | `empty_pages + deleted_pages` | These are 100% waste at any fillfactor and invisible to `avg_leaf_density`. A measured index read 89.94% density and was still 69.9% reclaimable |
| `leaf_fragmentation` | Share of leaves whose right sibling sits at a lower block number | Not wasted space at all. Physical disorder that costs sequential-scan I/O; the note says so |
| `notes` | Why a row looks odd | `no leaf pages`, `fillfactor N`, `fragmented, not wasted space`, `denser than a rebuild would leave it`, `reclaim is mostly empty/deleted pages` |

Two rows from this revision's 17.11 run show why both percentages exist:

```text
 index_name  | index_size | leaf_pages | dead_pages | avg_leaf_density | wasted_ff_pct | est_reclaimable_pct | notes
 i_delhead   | 21 MB      |        821 |       1918 |            89.94 |          69.9 |                69.9 | reclaim is mostly empty/deleted pages
 i_ff10      | 41 MB      |       5264 |          0 |             9.62 |           0.0 |                -0.5 | fillfactor 10
```

`i_delhead` has textbook-perfect leaves and is two thirds reclaimable, and here
the two columns agree to the tenth because every wasted byte is in a whole page
that holds nothing. `i_ff10` looks catastrophic by density and is exactly the
size its owner asked for, so both columns say there is nothing to take back.
Both rows are from the `guard` stage's own population, and both servers print
them identically.

**Read the smallest rows with care.** With no size prefilter the report also
prints indexes of one, two and three pages, where a rebuild cannot pack the
target density however hard it tries: a one-row index reads `44.6` in
`wasted_ff_pct` and `0.0` in `est_reclaimable_pct` on both servers, and the
two-page `c_zero_idx` reads `0.0` in `est_reclaimable_pct` where a rebuild
returns 50.0 %, and `44.7` in `wasted_ff_pct` on the leaf page it has. Those
are rounding artefacts of a file too small to fill a page, not waste and not a
missed rebuild; see [What it gets wrong, measured](#what-it-gets-wrong-measured).

### Follow-up: no threshold, no verdict column

The statement measures and estimates; it no longer judges. Five edits took out
the threshold and the column it drove, and nothing else in the text moved:

| Where | Was | Is |
|---|---|---|
| `params` | `20::numeric AS alert_pct` | gone; at that revision `min_index_bytes` became the last entry, and the sixth follow-up has since removed that too |
| `modelled` | `p.alert_pct,` carried it down the pipeline | gone |
| presentation `SELECT` | `CASE WHEN 100 * (index_size - est_rebuilt_bytes) / index_size >= f.alert_pct THEN 'rebuild candidate' ELSE 'ok' END AS status` | gone |
| header comment | `Alert on est_reclaimable_pct; read wasted_pct for composition only.` | the statement sets no threshold and reaches no verdict, and returns rows ordered by `est_reclaimable`, largest first |
| stage list | `params  tunables and the two page-layout constants` | `params  the size prefilter and the two page-layout constants`, which the sixth follow-up narrowed again to `params  the two page-layout constants` |

The text drops from 125 lines and 6,002 bytes to 122 lines and 5,839 bytes, and
the output from 15 columns to 14. `notes` is untouched.

**Nothing else the statement returns moved**, and every run of the `compare`
stage re-derives that on the population the shared suite builds, the current one
included. The stage recovers the superseded text from its own commit, refuses a
text that does not hash to the recorded one, and puts both through the same
three checks:

| Check | 12.2 | 17.11 |
|---|---|---|
| Rows returned, either text | 123 | 110 |
| Columns returned, superseded against amended | 15 against 14 | 15 against 14 |
| Superseded text, `rebuild candidate` / `ok` | 88 / 35 | 76 / 34 |
| Amended output against the superseded output with column 14 cut | identical, 10,609 bytes | identical, 9,506 bytes |
| Columns exposed by the internal `final` stage, superseded against amended | 29 against 28, and `alert_pct` is the only one missing | 29 against 28, and `alert_pct` is the only one missing |
| `EXCEPT` in both directions over the 28 shared columns | **0 rows**, 354 indexes | **0 rows**, 369 indexes |

Both texts still print the same rows, because both prefiltered at 1 MB; the
size prefilter went two revisions later. The row check compares `psql -A -F '|'`
output with field 14, `status`, removed from the superseded run. The column
check builds one view per text over the internal `final` stage, generated
mechanically from each text with the two `SET` lines dropped and, for a text
that still carries one, its `min_index_bytes` set to 0, so all three texts are
compared over every index in the database. Both views are read inside one
query: materializing them in turn does not work, because each pass creates and
drops a relation and so grows the catalog's own indexes, which are candidates
too — that alone produced 29 differing rows before the stage was fixed.

**Cost was unchanged when the column went**, which is what a removed `CASE` over
an already-computed expression should cost: the same plan shape on both servers
(4 `CTE Scan` nodes, 72 plan lines on 17.11 and 69 on 12.2) and six interleaved
end-to-end runs of the two texts spanning 226.7-278.8 ms against 219.2-254.2 ms
on 17.11 and 219.4-248.4 ms against 213.5-232.7 ms on 12.2. Those are that
revision's numbers on that revision's population; the `cost` stage now times the
filed text against the fillfactor-era one, and what it measures today is under
[What it costs to run](#what-it-costs-to-run).

What a reader loses is the label, not the ranking: the sort is on reclaimable
**bytes** and the old label was on reclaimable **percent**, so a small, badly
bloated index can sort below a large, healthy one.
A caller that wants a threshold applies it to `est_reclaimable_pct` at the call
site, where it can differ per environment and per index size, instead of being
frozen at 20 inside a report whose job is to measure.

### Follow-up: wasted space measured against the fillfactor

Every wasted-space calculation is now rebased on the index's own fillfactor, so
a correctly built index reports no waste whatever its fillfactor is. The filed
column measured the file against perfect packing, which meant a healthy default
index always reported about 10% wasted and a deliberate `fillfactor = 10` index
reported 89.6% — a number that described the DBA's own instruction, not a
problem. Four edits, in one CTE and one `SELECT` list:

| Where | Was | Is |
|---|---|---|
| `est` | `s.leaf_bytes - s.live_leaf_bytes + s.dead_bytes AS wasted_space` | `GREATEST(round(s.leaf_bytes * s.target_density) - s.live_leaf_bytes, 0) + s.dead_bytes AS wasted_vs_fillfactor` |
| presentation `SELECT` | `pg_size_pretty(f.wasted_space::bigint) AS wasted_space` | `pg_size_pretty(f.wasted_vs_fillfactor::bigint) AS wasted_vs_fillfactor` |
| presentation `SELECT` | `round(100 * f.wasted_space / f.index_size, 1) AS wasted_pct` | `round(100 * f.wasted_vs_fillfactor / f.index_size, 1) AS wasted_ff_pct` |
| header comment, stage list | `wasted_space measures the file against perfect packing` | the fillfactor-relative definition, and `sized` now names the target |

The text grows from 122 lines and 5,839 bytes to 126 lines and 6,154 bytes, and
the output keeps its 14 columns. `notes` is untouched, and so is every other
expression in the statement.

Three decisions are worth stating, because each could have gone the other way:

- **The baseline is `target_density`, not `fillfactor / 100`.** It is the same
  `(leaf_capacity - BLCKSZ * (100 - fillfactor) / 100) / leaf_capacity` the
  rebuild estimate already uses — 89.95% at 8192 and fillfactor 90, not 90.00% —
  so the two columns now measure against one target instead of two that differ
  by 0.05 points ([nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L645-L671),
  [nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1145)).
- **The leaf term is clamped at zero.** An index denser than its target is not
  holding negative waste; it is denser than a rebuild would leave it, which the
  `notes` column already says. `GREATEST(..., 0)` applies to the leaf term only,
  so empty and deleted pages still count in full — they hold nothing at any
  fillfactor.
- **The columns are renamed.** `wasted_space` and `wasted_pct` meant something
  else in the two earlier versions of this report, and an archived output should
  not be silently reinterpreted. The baseline is now in the name.

**Measured on both servers, and nothing outside those two fields moved.** The
`compare` stage re-derives this comparison on every run's own population; these
are the current run's figures:

| Check | 12.2 | 17.11 |
|---|---|---|
| Rows returned, superseded text against filed | 123 against 354 | 110 against 369 |
| Output columns, either text | 14 | 14 |
| The 12 untouched fields: rows the superseded text printed that the filed output does not repeat exactly | **0 of 123** | **0 of 110** |
| Rows only the filed text prints, on those 12 fields | 231 | 259 |
| Columns exposed by the internal `final` stage | 28 against 28; `wasted_space` out, `wasted_vs_fillfactor` in | 28 against 28; same one-for-one swap |
| `EXCEPT` in both directions over the 27 shared columns | **0 rows**, 354 indexes | **0 rows**, 369 indexes |
| Rows where the new column exceeds the old one | 0 of 354 | 0 of 369 |
| Rows where the new column is negative | 0 of 354 | 0 of 369 |
| Rows where the leaf term clamps to zero | 25, all of them printed | 29, all of them printed |

The two texts no longer print the same rows, because the filed one prefilters
nothing and the superseded one skipped anything under a megabyte, so the row
check is a set comparison: every row the older text printed appears in the filed
output unchanged on the 12 fields the rebase did not touch, and the rest of the
filed output is the 231 and 259 rows that prefilter used to hide.

**What actually changed, on the 17.11 report.** The leaf term clamps to zero on
29 of the 369 rows, every one of them printed, and every remaining row with
in-page waste fell by roughly a tenth of the file. These rows come from the same
run as everything else on this page, the superseded text's output beside the
filed one:

```text
 index_name  | index_size | avg_leaf_density | old wasted_pct | wasted_ff_pct | est_reclaimable_pct | notes
 p18         | 4408 kB    |             9.88 |           89.0 |          79.1 |                88.7 |
 p75         | 2208 kB    |             9.25 |           89.7 |          79.7 |                89.1 |
 i_delhead   | 21 MB      |            89.94 |           72.9 |          69.9 |                69.9 | reclaim is mostly empty/deleted pages
 i_ff100     | 3976 kB    |            99.82 |            0.2 |           0.2 |                 0.0 | fillfactor 100
 i_fresh     | 4408 kB    |            90.00 |            9.9 |           0.0 |                -0.2 |
 i_ff50      | 7976 kB    |            49.81 |           49.6 |           0.0 |                -0.2 | fillfactor 50
 i_ff10      | 41 MB      |             9.62 |           89.6 |           0.0 |                -0.5 | fillfactor 10
 i_dedup_off | 21 MB      |            90.16 |            9.7 |           0.0 |                -0.3 |
 i_dup_ins   | 6368 kB    |            95.94 |            4.0 |           0.0 |                -6.7 | denser than a rebuild would leave it
```

Both servers produce this pattern; on 12.2 the leaf term clamps on 25 rows out
of 354, the difference being the fixtures 12.2 cannot build.

The `fillfactor = 100` rows are the exception that proves the arithmetic: at
fillfactor 100 the target free space is zero, so
`target_density` is exactly 1 and the new column equals the old one to the byte.
That happened for 133 of 354 indexes on 12.2 and 138 of 369 on 17.11 — the three
`fillfactor = 100` indexes on each leg (`i_ff100`, `i_ff100_del90` and the
suite's `p54`) plus every index with no leaf pages, where both definitions
reduce to the dead-page term.

**A rebuilt index must report zero, and it does.** After `REINDEX INDEX` over
every scored index, the new column was measured again on both servers:

| Post-`REINDEX` residual | 12.2 | 17.11 |
|---|---|---|
| Suite fixtures rebuilt | 117 | 126 |
| Exactly `0` bytes | 43 | 46 |
| At or below 0.1% | 58 | 60 |
| Worst residual, all fixtures | 14.9%, `p25` at two leaf pages | 14.9%, `p25` and `p31` |
| Worst residual, fixtures at or above 1 MB (51 on 12.2, 48 on 17.11) | **0.3%** | **0.3%** |
| Guard fixtures rebuilt | 17 | 18 |
| Worst guard residual | 44.6%, `c_one_idx` | 44.6%, `c_one_idx` |

The 44.6% is the honest limit of the definition and it is the same fixture on
both servers: `c_one_idx`, a one-row index whose single leaf page is 0.29% dense.
A rebuild cannot make one tuple fill 89.95% of a page, so the column claims
7,309 wasted bytes that no operation will ever return. Every index in that state
has three leaf pages or fewer, and **the report now prints all of them**: with
the size prefilter gone nothing keeps a one-page index out of the output, so a
reader sees the over-report with no note attached, which is
[an open question](#open-questions). Two suite fixtures show the same effect at
14.9% on two- and three-page files, while the 51 and 48 fixtures at or above
1 MB show it at 0.3% or less.

**The two columns are related, not redundant.** For waste that sits inside live
leaf pages, the new column is a fixed fraction of the reclaim estimate, because
it counts payload bytes while `est_reclaimable` counts whole file pages including
each one's 24-byte header and 16-byte special area:

```text
wasted_vs_fillfactor / est_reclaimable  ->  (leaf_capacity - target_free) / block_size
                                        =   (8152 - 819) / 8192  =  0.8951   at 8192/90
```

Measured in the current run, at the default fillfactor: `p18` reports 79.1%
wasted against 88.7% reclaimable, a ratio of `0.892`, and `i_int4` 76.2 against
85.7, `0.889`, both against the predicted `0.8951`. Where the waste is whole
dead pages the ratio goes to exactly 1: `i_delhead` reads 69.9 and 69.9, and
`i_ff50_delhead` 89.7 and 89.7. So the ratio reads as a composition signal: near
0.89 the waste is inside pages, at 1.0 it is whole pages, and a rebuild is the
only way to return either.

**At a low fillfactor the two columns diverge, and the new one is the smaller.**
No fixture of the shared suite states a fillfactor other than 90, 100 or 70, so
the `bl` guard set keeps four of its own — a table filled, indexed at a stated
fillfactor, then nine tenths of the rows deleted and the table vacuumed — and the
`guard` stage rebuilds each one for its `actual_pct`. Both servers produced these
four rows identically in the current run:

```text
 index_name     | ff  | leaf | dead | density | target | wasted_ff_pct | est_pct | actual_pct | ratio pred/meas | after
 i_ff100_del90  | 100 |  493 |    0 |   10.25 | 100.00 |          88.6 |    89.5 |       89.5 | 0.9951 / 0.9899 |   1.5
 i_ff50_del90   |  50 |  991 |    0 |    5.25 |  49.75 |          44.0 |    89.3 |       89.8 | 0.4951 / 0.4928 |   0.4
 i_ff10_del90   |  10 | 5264 |    0 |    1.23 |   9.57 |           8.3 |    87.1 |       90.0 | 0.0952 / 0.0953 |   0.0
 i_ff50_delhead |  50 |  100 |  894 |   49.36 |  49.75 |          89.7 |    89.7 |       89.8 | 0.4951 / 1.0000 |   0.4
```

The predicted ratio holds across the whole fillfactor range on both servers, and
the consequence is blunt: **`i_ff10_del90` is 90.0% reclaimable and reports 8.3%
wasted.** That is the definition working, not failing. At fillfactor 10 the index
is *supposed* to be nine tenths free space, so the bytes that a rebuild would not
leave free are a small share of the file even though the rebuild takes it from
43,294,720 bytes to 4,349,952. A reader who wants
"how much disk will `REINDEX` give back" must read `est_reclaimable_pct`, at any
fillfactor; `wasted_ff_pct` answers "how much of this file is space its own
fillfactor does not justify", and the lower the fillfactor the further apart
those two questions are. The old baseline hid the difference by reporting 97.8%
for the same index, which was neither answer. `i_ff50_delhead` shows the other
end: its waste is 894 whole dead pages, the ratio goes to `1.0000`, and the two
columns agree at 89.7%.

The last column is the post-`REINDEX` residual, and `i_ff100_del90`'s 1.5% is
worth naming: rebuilt, it holds 20,000 rows in 52 pages, because the rightmost
page of any build takes whatever is left over. Against a 100% target that partial
page is most of the residual, and on a 416 kB index that is 1.5%. The effect is
per-index, not per-byte, so it shrinks as the index grows.

These four fixtures also carry the guard set's worst under-estimate at a
non-default fillfactor: `i_ff10_del90` at `87.1` against an actual `90.0`,
**`−2.9` points**. Among the guard fixtures only the two blind spots beat it —
`i_dedup_off` at `−69.4` and the two-page `c_zero_idx` at `−50.0` — and among
the suite's fixtures only `p32` at `−4.1` and `f78` at `−3.5` do; in the other
direction the worst over-estimate anywhere on the suite is `+10.0`. The likely
cause is in the same numbers. Every
non-rightmost page holds a high key in item 1
([nbtree.h#P_HIKEY](../../../../raw/postgres-17/src/include/access/nbtree.h#L348-L369)),
which a rebuild into 531 pages writes 531 times and the 5,264-page original
carries 5,264 times, and `avg_leaf_density` counts that per-page overhead as
occupied space because `PageGetFreeSpace` reports only what is unallocated
([pgstatindex.c#leaf-accounting](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L304-L324),
[bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L898-L923)).
At a density of 1.23% that overhead is most of the measured payload, so the model
believes there is more to re-pack than there is. The error is in the safe
direction; the per-page accounting that would confirm the size of each term was
not done, and it is recorded under [Open Questions](#open-questions).

**Cost is unchanged.** Re-measured in the current run: six interleaved
end-to-end runs of the filed text and the fillfactor-era one spanned
221.4-262.5 ms against 223.2-266.6 ms on 17.11 and 228.6-306.6 ms against
211.0-250.1 ms on 12.2 — overlapping ranges, which for one multiplication over
an already-materialized CTE is noise. The two timings are not for one
population: the fillfactor-era text is timed as filed, so it still skips every
index under 1 MB and reads 259 and 231 fewer indexes than the filed text. The two texts' outputs are compared field by field on the
same population, by the `compare` stage, and the comparison returns no
difference outside the two fields the edit moved.

**What this column does not become.** It is still a description of the file, not
a prescription for it. `pgstatindex` cannot see entries that are deleted but not
yet vacuumed: the suite's retired `p65` and `p67` read `0.1` wasted and `0.0`
reclaimable on files a rebuild emptied by 89.1% in the 2026-09-12 review run,
and zero is a flat way to be
wrong — a limit the current suite no longer builds a fixture for
([the blind spot the suite stopped building](#the-blind-spot-the-suite-stopped-building)).
And fillfactor is a build-time and
rightmost-split target, not
a property a growing index holds: a leaf split applies the fillfactor only on the
rightmost page or when `_bt_afternewitemoff` finds the new item at the end of a
localized group of ascending insertions, other leaf splits aim to divide the
free space evenly, and a page full of one value splits at
`BTREE_SINGLEVAL_FILLFACTOR`, 96%
([nbtsplitloc.c#fillfactormult](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L279-L335),
[nbtsplitloc.c#SPLIT_SINGLE_VALUE](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L406-L416),
[nbtree.h#BTREE_SINGLEVAL_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202)).
The column measures the file against what a rebuild would produce, which is the
only fillfactor-relative question `REINDEX` can answer.

### What one pgstatindex call actually measures

`pgstatindex` opens the index with `AccessShareLock`, reads the metapage, then
walks every remaining block under a shared buffer lock with a `BAS_BULKREAD`
strategy, buckets each page into deleted, half-dead (`empty_pages`), leaf, or
internal, and closes the index again
([pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L203-L213),
[pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L215-L333),
[nbtree.h#P_ISLEAF](../../../../raw/postgres-17/src/include/access/nbtree.h#L212-L227)).
Three details drive the model:

- **`index_size` is the whole file**, computed as `(1 + leaf + internal + deleted
  + empty) * BLCKSZ`
  ([pgstatindex.c#index_size](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L349-L357)).
  Measured: it equalled `pg_relation_size()` for **367 of 367** candidate indexes
  on 17.11 and **352 of 352** on 12.2.
- **`avg_leaf_density` covers live leaves only.** It is
  `100 - free_space / max_avail * 100`, where both sums are accumulated only in
  the leaf branch of the loop; deleted and half-dead pages contribute to neither
  ([pgstatindex.c#leaf-accounting](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L304-L324),
  [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L367)).
  That is why the statement adds `dead_pages * bs` separately.
- **`leaf_fragmentation` counts pages, not bytes**: leaves whose `btpo_next` is a
  lower block number, over `leaf_pages`
  ([pgstatindex.c#fragments](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323),
  [pgstatindex.c#leaf_fragmentation](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L368-L372)).

Nothing here reads `pg_class.reltuples`, `pg_statistic` or the cumulative
statistics views, so the report does not care whether the table was ever analyzed.
That is the main thing it buys over a catalog-only estimator, whose accuracy rests
on statistics freshness and on the `reltuples = -1` sentinel; both hazards are
measured in
[Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17](btree-index-bloat-core-sql-only.md).
The shared suite puts a number on it: all eight of its false-positive
constructions pass here, including the two that forge a count and stale a
statistics row, and nothing the statement reports depends on which tables the
maintenance step and rule 3's census analyzed
([the scoring](#the-mandatory-suite-scored-on-both-majors)).

The reason `REINDEX` is the remedy and `VACUUM` is not: the nbtree code contains
no call to `RelationTruncate` or `smgrtruncate` (0 matches under
`src/backend/access/nbtree/`). A vacuum puts deleted pages into the free space map
for reuse instead
([nbtree.c#RecordFreeIndexPage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1165-L1170),
[nbtree.c#_bt_pendingfsm_finalize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1048-L1059)).
Measured on both servers: after deleting 70% of a table and vacuuming, its index
still occupied 22,487,040 bytes with 1,918 dead pages, and `REINDEX` took it to
6,758,400.

### Why every candidate filter is there

Every filter in `cand` exists because `pgstatindex` raises on that shape, and one
raised call aborts the whole statement. Each was reproduced on both servers:

| Filter | What happens without it |
|---|---|
| `a.amname = 'btree'` | `ERROR: relation "s_hash" is not a btree index` — reproduced for hash, GIN, GiST, SP-GiST and BRIN ([pgstatindex.c#IS_BTREE](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L228)) |
| `c.relkind = 'i'` | A partitioned index is `'I'`, so `IS_INDEX` is false and the call fails the same test a non-B-tree index fails: `ERROR: relation "i_part" is not a btree index`, reproduced on both servers. Upstream's expected output covers the neighbours rather than this exact call — `pgstattuple` on a partitioned index, `pgstatindex` on a partitioned table ([pg_class.h#RELKIND_PARTITIONED_INDEX](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L165-L173), [pgstatindex.c:70](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L70), [pgstattuple.out#partitioned](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L155-L171)) |
| `indisvalid AND indisready AND indislive` | On 17.11, `ERROR: index "i_invalid" is not valid`. On 12.2 the same index returns a row. See the next section ([pgstatindex.c#indisvalid](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L240-L250), [pg_index.h#indisvalid](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L42-L45)) |
| `NOT pg_is_other_temp_schema(...)` | `ERROR: cannot access temporary tables of other sessions`. Measured on both servers: a second session holding a 6600 kB temp index raises exactly that when the index is called by OID, while the statement returned all its rows — 369 on 17.11 and 354 on 12.2 — with that session open ([pgstatindex.c#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L230-L238), [rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/src/include/utils/rel.h#L652-L669)) |
| `relpersistence <> 'u' OR NOT pg_is_in_recovery()` | Untested belt and braces, and the one filter no fixture exercises. The planner refuses unlogged relations during recovery ([plancat.c#recovery](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L149-L153)) but a function call never goes through that path, and `pgstatindex_impl` has no such guard, so on a standby it would read whatever is in the file. On a primary, unlogged indexes are read normally; see [Open Questions](#open-questions) |

**There is no size filter, so there is no candidate this statement declines to
measure.** Every B-tree index the function accepts is read, whatever it holds,
including each catalog and TOAST index of the database. Two consequences follow
and both are measured: the report reads every page of every index in the
database, which is [What it costs to run](#what-it-costs-to-run), and nothing in
`cand` opens a relation any more — the whole CTE is a catalog read — which is
what makes a concurrent `DROP INDEX` behave as
[Locking, timeouts, and the concurrent-drop race](#locking-timeouts-and-the-concurrent-drop-race)
describes. A caller who wants a cheaper report adds a predicate of its own;
`pg_relation_size(c.oid) >= <bytes>` is a `stat()`-level answer that also
absorbs a concurrent drop, because it opens with `try_relation_open` and returns
NULL rather than raising
([dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L346-L371)),
and `c.relpages >= <pages>` is cheaper still at the price of trusting a
catalog number no read refreshes.

The index is passed by OID, not by name (`pgstatindex(c.idx_oid::regclass)`). That
is deliberate: see [Privileges](#privileges).

`cand` is `AS MATERIALIZED`, so the candidate list is fixed before the first page
is read
([gram.y#opt_materialized](../../../../raw/postgres-17/src/backend/parser/gram.y#L12910-L12914)).
The 12.2 server accepted the clause in this run, which is the evidence that the
oldest major this statement claims parses it.

### The one behavioural difference between 12 and 17

**An invalid index is the only shape where the two pinned servers disagree**,
and it is the reason the `indisvalid` filter is not optional. Read it as a
difference between 12.2 and 17.11, not necessarily between the majors: the
commit that added the check says it was back-patched. See below.

On the 17.11 server, `pgstatindex` on an index with `indisvalid = false` fails:

```text
ERROR:  index "i_invalid" is not valid
```

On the 12.2 server, the identical call on the identical fixture returns a row:

```text
 version | tree_level | index_size | root_block_no | internal_pages | leaf_pages | empty_pages | deleted_pages | avg_leaf_density | leaf_fragmentation
       4 |          2 |    6758400 |           290 |              4 |        820 |           0 |             0 |            90.05 |                  0
```

The check is `13503eb5905`, "Diagnose !indisvalid in more SQL functions"
(2023-10-30). This checkout carries no release tags, so the history readable here
places the commit on `REL_17_STABLE` and says nothing about which tagged release
first shipped it. The commit states its own reasoning, that a `!indisready` index could
lead to `ERRCODE_DATA_CORRUPTED` and that an `indisready && !indisvalid` index
gives confusing results because its size can be too low for a valid index of the
table
([pgstatindex.c#indisvalid](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L240-L250)).

**The measured difference is between these two minors.** The same commit
message, in this checkout's own history, ends "Back-patch to v11 (all supported
versions)". What that means for any 12.x minor after 12.2 is a claim about
another checkout, which this page may not cite, so it is filed under
[Open Questions](#open-questions) rather than stated here. What is measured is
that the pinned 12.2 returns a row and 17.11 raises the error.

Filtering the index out is right on both servers: on 17.11 it prevents an abort,
and on 12.2 it prevents a half-built index from being reported as a healthy one.
A `CREATE INDEX CONCURRENTLY` that fails part-way leaves exactly such an index
behind, marked invalid
([ref/create_index.sgml#invalid-index](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L646-L661));
see also
[How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 17](create-index-concurrently.md).

Everything else matched. Both servers produced the same message text for
non-B-tree access methods, partitioned indexes, tables, views, sequences,
another session's temp index, and a stale OID
(`ERROR: could not open relation with OID 2147483647`).

### The model, from avg_leaf_density to a rebuilt size

The estimate is a ratio, so most constants cancel:

```text
payload_leaf_pages  = leaf_pages * avg_leaf_density / 100
est_leaf_pages      = ceil(payload_leaf_pages / target_density)
est_internal_pages  = round(internal_pages * est_leaf_pages / leaf_pages)
est_rebuilt_bytes   = (1 + est_leaf_pages + est_internal_pages) * block_size
est_reclaimable     = index_size - est_rebuilt_bytes
```

`target_density` is not the fillfactor. It is what the build code actually leaves
behind. A sorted build closes a leaf page when the remaining free space drops
below `BLCKSZ * (100 - fillfactor) / 100`
([nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L645-L671),
[nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1145),
[nbtsort.c#_bt_buildadd](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L845-L860)),
so the density a rebuild reaches is `(leaf_capacity - target_free) / leaf_capacity`
and not `fillfactor / 100`. At `block_size` 8192 and the default fillfactor of 90
([nbtree.h#BTREE_DEFAULT_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202),
[reloptions.c#btree-fillfactor](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L185-L194))
that is `(8152 - 819) / 8152 = 89.95%`, marginally below the fillfactor, which
makes the estimate conservative by construction.

Measured fresh-build densities, byte-identical on both servers over a 200,000-row
`int` index, against what the formula predicts:

| fillfactor | modelled target density | measured `avg_leaf_density` | reported `est_reclaimable_pct` |
|---|---|---|---|
| 100 | 100.00 | 99.82 | 0.0 |
| 90 | 89.95 | 90.00 | −0.2 |
| 50 | 49.75 | 49.81 | −0.2 |
| 10 | 9.57 | 9.62 | −0.5 |

`est_internal_pages` uses `round`, not `ceil`, because it is a proportional
estimate rather than a capacity bound; internal pages were under 0.5% of every
fixture. Non-leaf pages are built to a fixed 70%
([nbtree.h#BTREE_NONLEAF_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202)),
which the model does not use.

### Why the two page-layout constants are safe

`leaf_capacity` is `block_size - 24 - 16`, which reproduces `pgstatindex`'s own
`max_avail`, computed as `pd_special - SizeOfPageHeaderData`
([pgstatindex.c#max_avail](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L308-L314)).
The 24 is `SizeOfPageHeaderData`
([bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L211-L214));
the 16 is `MAXALIGN(sizeof(BTPageOpaqueData))`, whose five fields are two
`BlockNumber`, one `uint32` and two `uint16` — `btpo_flags`, and
`btpo_cycleid`, which is declared as a `BTCycleId`
([nbtree.h#BTPageOpaqueData](../../../../raw/postgres-17/src/include/access/nbtree.h#L62-L71),
[nbtree.h:29](../../../../raw/postgres-17/src/include/access/nbtree.h#L29)).
The same subtraction appears in core as
`BLCKSZ - SizeOfPageHeaderData - sizeof(BTPageOpaqueData)`
([nbtree.h#MaxTIDsPerBTreePage](../../../../raw/postgres-17/src/include/access/nbtree.h#L185-L187)).

Rather than trust the arithmetic, both servers were asked to imply the constant
from pages with known contents. One `int4` key on a root leaf page leaves
`8160 - 28 - 4 = 8128` free, and an empty leaf page leaves `8176 - 24 - 4 = 8148`;
the 4 is the line pointer that `PageGetFreeSpace` deducts
([bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L898-L923)).
Both servers reported `0.29` and `0.05`, implying `max_avail` of 8151.6 and
8152.1 against the statement's 8152.

The statement reads `block_size` from the server, so a cluster built at another
`BLCKSZ` scales; the 24 and the 16 do not depend on `BLCKSZ`. Nothing was run at a
block size other than 8192.

### wasted_vs_fillfactor is not est_reclaimable

```text
target_density       = (leaf_capacity - block_size * (100 - fillfactor) / 100)
                       / leaf_capacity
wasted_vs_fillfactor = max(leaf_pages * leaf_capacity
                             * (target_density - avg_leaf_density/100), 0)
                     + (empty_pages + deleted_pages) * block_size
```

That is the file measured against the density a rebuild at this index's own
fillfactor reaches, which is the only fillfactor-relative question `REINDEX` can
answer. It counts bytes that hold nothing **and that a rebuild would not leave
empty**, so a correctly packed index reports zero at any fillfactor, and the
`fillfactor = 10` fixture that used to report 89.6% now reports 0.0.

`est_reclaimable` answers a different question with the same target: not "how
many bytes in this file are surplus" but "how large would the file be after a
rebuild". The gap between them is per-page overhead. `wasted_vs_fillfactor`
counts payload bytes inside leaf pages; `est_reclaimable` counts whole 8 kB file
pages, each carrying a 24-byte header and a 16-byte special area that the payload
figure excludes. For in-page waste that makes the first a fixed fraction
`(leaf_capacity - target_free) / block_size` of the second — 0.8951 at 8192 and
fillfactor 90, measured at 0.8868 to 0.8921 — and for whole dead pages the two
coincide, because a dead page wastes all 8,192 of its bytes and gives all 8,192
back. Both are in the output because a reader who wants to know how much of the
file is surplus and a reader who wants to know how much disk a rebuild returns
are asking different things.

An earlier version of this report measured the same free bytes against 100%
packing under the names `wasted_space` and `wasted_pct`. That number was the
literal reading of "wasted space" but it was mostly a restatement of the
fillfactor: a healthy default index reported about 10%. See
[Follow-up: wasted space measured against the fillfactor](#follow-up-wasted-space-measured-against-the-fillfactor).

### NaN is the trap

An index with no leaf pages returns `NaN` for both `avg_leaf_density` and
`leaf_fragmentation`, because the C code guards on `max_avail > 0` and
`leaf_pages > 0`
([pgstatindex.c#NaN](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L372)).
Upstream's own expected output records this for an empty index
([pgstattuple.out#empty-index](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L44-L52)).

In PostgreSQL, `NaN` compares greater than every number, for `float8` and for
`numeric` alike
([float.h#NaN-aware-comparisons](../../../../raw/postgres-17/src/include/utils/float.h#L252-L258),
[float.h#float8_gt](../../../../raw/postgres-17/src/include/utils/float.h#L315-L319),
[numeric.c#cmp_numerics](../../../../raw/postgres-17/src/backend/utils/adt/numeric.c#L2527-L2547)).
Measured on both servers:

```text
 is_nan | nan_over_threshold | numeric_nan_over_threshold
 t      | t                  | t
```

So a naive `WHERE bloat_pct > 20` reports every empty index as maximally bloated.
The statement converts density to `0` behind a `leaf_pages > 0` test before any
arithmetic, prints `NULL` instead of `NaN`, and tags the row `no leaf pages`. In
this revision's run 134 of the 367 candidate indexes on 17.11 and 129 of the 352
on 12.2 had `NaN` density — mostly empty catalog TOAST indexes, plus the suite's
own empty-subset fixtures — and every one of them reported exactly `0.0`
estimated reclaim. **They are printed rows now**, since nothing filters them out
by size, which is why the guard needs to hold: an empty index is one `NaN` away
from topping a report sorted on a percentage.

### Mandatory test review

**The suite is not defined here.** Its six fixture families, its five phases,
its maintenance assumption, its rule that the maintenance must not be defeated,
its three porting rules, its `REINDEX INDEX` oracle and its four verdict bands
are defined once for this version in
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md).
Read that page for what a test *is*; this section says only what is local to
this page: which of that suite's obligations this statement has met, and where
this page's own run departs from the shared definition. The 2026-09-11 revision
replaced the 32-fixture set this page used to build with that suite, the
2026-09-13 re-port took on the maintenance assumption, and this revision takes
on the rule beside it; the port is in line with the concept page as it stands
today, and both legs were re-run against it. The results are under
[The mandatory suite, scored on both majors](#the-mandatory-suite-scored-on-both-majors).

Obligations, in the shared suite's families. The suite is **113 numbered
tests**: 11, 11b and 38 are retired, and so are 65, 67, 69, 106, 117, 121 and
legs 113a and 113c, so this page no longer builds or scores any of them.

| Family | Fixtures here | State for the filed statement |
|---|---|---|
| 1, the deduplication gate | tests 1-17 less the retired 11 and 11b: 25 indexes on two 500,000-row tables, 16 of them constructible on 12.2 | **run and passed**, 25 of 25 on 17.11 and 16 of 16 on 12.2 |
| 2, partial indexes | tests 18-77 less the retired 38, 65, 67 and 69: 60 indexes on both legs | **run and passed**, 60 of 60 on both legs |
| 3, false-positive constructions | tests 78-85, eight fresh indexes, none churned | **run and passed**, 8 of 8 on both legs, `f84`'s forged index count and `f85`'s stale table statistics included |
| 4, false-negative constructions | tests 86-91 | **run and passed**, 6 of 6 on both legs; its six fixtures run from 11 to 87 leaf pages, and every one is printed |
| 5, the change A-D controls | tests 92-112 less the retired 106: 20 fixtures | **run and passed**, 20 of 20 on both legs. 94 and 95 still carry their per-table reloptions, and the census still reads their effective thresholds of 100 and 610,000; under the maintenance assumption both reach it already analyzed, so neither reading decides anything |
| 6, the drained queue and zero counts | tests 113-120 less the retired 117, and 113 keeps only `p113b`: 7 fixtures planned on each leg | **run and passed**, 6 of 6 on 17.11 and 7 of 7 on 12.2. Test 120 is scored only when its post-census precondition holds — **not met on 17.11** in this run, where `p120` read `reltuples = 6643` and the fixture was recorded as an unmet precondition, and met on 12.2, where it read `0` |

Every obligation the concept page states is met by this revision's run:

- **The maintenance assumption.** Every recipe that inserts, deletes or updates
  rows after its index build ends on the maintenance step, with the churn
  published before it: rule 2's drain does it for its 38 tables, and the
  recipes with churn of their own do it inside `sql` block 4. The step is one
  `VACUUM (VERBOSE, ANALYZE)`, and `ANALYZE` is still the last writer of
  `reltuples`, because `vacuum()` vacuums a relation before it analyzes it
  ([vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650)).
  The cluster's `autovacuum = off` is isolation only and exempts no table.
- **The maintenance must not be defeated.** Every one of those statements is
  bracketed, runs in a session whose settable timeouts are 0, and is scored
  only after the run has proved it did its work: see
  [The maintenance, proved not defeated](#the-maintenance-proved-not-defeated).
- **The three rules.** Each fixture has a baseline taken at its index build by a
  `ddl_command_end` trigger; rule 2's drain skips exactly the concept page's
  exempt list; rule 3's census runs after the maintenance step, reads the
  *effective* per-table analyze parameters rather than the cluster GUCs, and
  records a recheck that still disagrees rather than analyzing again.
- **The ordering.** The churn is published before the maintenance `ANALYZE`
  resets the counter and again before the census reads it; the catalog forgery
  is applied after both.
- **The fixture contracts.** Test 120's probabilistic precondition is asserted
  after the census instead of assumed; every fixture predicted reclaimable is
  checked for the post-churn shape that prediction needs; family 6 prints the
  catalog count beside the population each fixture counted, so an unknown
  `reltuples = -1` cannot be read later as a measured zero; `expected_stage` and
  `want_stage` are both present; and the fixtures a server cannot build are
  recorded as skips with the server's own message rather than dropped.

Four deviations remain, and they are this page's, not the suite's:

- **The decision rule is this harness's.** The shared bands score a decision,
  and this statement deliberately reaches none: it reports `est_reclaimable_pct`
  and stops, as
  [Follow-up: no threshold, no verdict column](#follow-up-no-threshold-no-verdict-column)
  explains. The harness turns it into a decision with a 50 % threshold on
  `est_reclaimable_pct` that appears nowhere in the statement.
- **Two decisions are scored, and they coincide.** `taken_stage` is what a
  reader takes from the filed output, so a fixture the statement never prints
  counts as `leave` whatever its arithmetic says; `taken_nofilter` applies the
  same threshold to every index regardless. The two columns are kept side by
  side as the check that the statement hides nothing, and on this run they
  agree on every fixture: **126 of 126 and 117 of 117 printed**, 92 and 83
  rebuild decisions either way, and `lost_by` empty on both legs.
- **`expected_stage` is recomputed from the instrument, not from the gate.**
  The harness calls `pgstatindex` itself on each churned fixture and rebuilds
  the whole estimate from those ten columns, so a statement that disagrees with
  its own input is visible. It never disagreed: 126 of 126 and 117 of 117.
- **The guard fixtures keep their own oracle.** Schema `bl` holds the shapes the
  suite does not cover - the refusals, the invalid index, the four fillfactors,
  the two known-content pages, the duplicate builds and the
  build-with-deduplication-off shape - and the `guard` stage rebuilds each one
  and measures it. No verdict band is applied to them, and the maintenance
  assumption does not govern them, because they are not suite fixtures.

The engine's own suites are not a test of this statement. `make check` runs the
core regression tests against a temporary installation inside the build tree,
and `contrib/pgstattuple`'s tests run from its own directory the same way;
nothing in them reads `est_reclaimable_pct`. What they do provide is the
adjacent coverage of `pgstatindex` itself.
[regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59),
[regress.sgml#contrib-suites](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L171-L195),
[installation.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L515-L522),
[pgstattuple.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L18-L37).

### The mandatory suite, scored on both majors

**Every numbered fixture of the shared suite has been run under its five
phases, its maintenance assumption and the rule that the maintenance must not
be defeated, and scored with its four bands, on both majors, and the statement
passes all of them: `PASS` on 126 of 126 on 17.11 and 117 of 117 on 12.2, with
0 `CRITICAL FALSE POSITIVE`, 0 `FALSE POSITIVE` and 0 `FALSE NEGATIVE` on
either leg** — family 3's eight constructions, where a catalog-only estimator
is misled by design, included. Three things stand behind that clean sheet and
none of them is the reading getting better. Every fixture is printed, so the
scoring loses no right answer to a row the report withheld; every maintenance
statement is proved to have done its work, so no fixture is scored on a file a
defeated `VACUUM` left dense ([the proofs](#the-maintenance-proved-not-defeated));
and the suite no longer builds the fixtures that used to defeat the reading,
which is [an open question](#open-questions), not a result.

| Result | 17.11 | 12.2 |
|---|---|---|
| Fixtures planned, of the 126 this port attempts | 126 | 117 |
| Fixtures scored | 126 | 117 |
| Fixtures not scored, recorded as skips | **0** | 9, every one a fixture that needs B-tree support function 4 |
| Fixtures the report printed | **126 of 126** | **117 of 117** |
| `PASS` | **126** | **117** |
| `CRITICAL FALSE POSITIVE` | 0 | 0 |
| `FALSE POSITIVE` | 0 | 0 |
| `FALSE NEGATIVE` | **0** | **0** |
| Fixtures below 1 MB | 31 | 8 |
| Rebuild decisions taken, and what they returned | 92, mean **87.5 %** (60.0 to 100.0) | 83, mean **88.6 %** (74.3 to 100.0) |
| The same decisions taken from the reading rather than the report | 92 | 83 |
| `expected_stage` agreeing with the statement | **126 of 126** | **117 of 117** |
| Build-contract failures | 0 | 0 |
| Post-churn shape assertions failed | 0 | 0 |
| Maintenance statements proved not defeated | **67 of 67** | **67 of 67** |
| Filed text against the harness view, on every fixture | **0 disagreements** | **0 disagreements** |

Both servers were built out of tree from the pins and checked before a fixture
existed: 17.11 passed `make check` **All 225 tests** plus `contrib/pgstattuple`
All 1; 12.2 passed **All 192** plus All 1. `Linux x86_64`, `block_size` 8192,
`max_data_alignment` 8, `initdb --locale=C --encoding=UTF8`, `autovacuum = off`,
`fsync = off`, `shared_buffers = 512MB`. The filed `sql` block hashes to
`3d4507a54b38…` and **executed unmodified on both**, returning 365 rows on
17.11 and 350 on 12.2, 14 columns each. **0 unexpected server errors on either
leg**: 17 and 16 errors were logged and every one belongs to a stage that asked
for it.

#### What the five phases produced

| Phase | 17.11 | 12.2 |
|---|---|---|
| build | 126 fixtures, 0 skipped | 117 fixtures, **9 skipped at build**, every one a fixture that needs a B-tree support function 4; the server's own message is recorded for each |
| baseline | 126 baselines, one per index, taken at the index build by the event trigger; **0 build-contract failures** | 117 baselines taken, 0 build-contract failures |
| churn | the recipes with churn of their own ran it and their bracketed maintenance statement during the build stage; 36 suite tables and both family 1 tables were drained nine heap blocks in ten and then given the same statement; **67 maintenance statements on each leg, every one proved not defeated**; the census then analyzed 2 of 88 tables | the same, table for table |
| decide | the filed text as filed (**365** rows), then the same text as a view over its internal `final` stage (**367** rows) | as filed (**350**), then **352** |
| oracle | a measured `REINDEX INDEX` on all 126 | on all 117 |

The two-row gap in the `decide` line is the report's own footprint, not a
candidate it hid. The two extra rows are `public.report_filed_pkey` and its
TOAST index, which the `report` stage creates to hold the rows the statement
just printed, so they exist for the second reading and not the first. **No
fixture differed between the two readings on either leg**; one shared row did,
and it is the same footprint: `pg_toast.pg_toast_2618_index`, the TOAST index
of `pg_rewrite`, which the harness view's own creation wrote between the
readings — it read `0.0` for the report and `−50.0` for the view on 17.11.
**This is what including the catalog costs**: the report covers indexes that
the reader's own session writes to, so two readings taken minutes apart are not
obliged to agree on them, and the row counts quoted on this page differ by
stage for the same reason — 365 and 350 printed by `report`, 367 and 352 read
by `decide`, 369 and 354 by `facts`, `cost`, `priv` and `compare`, and 371 and
356 by `race`, each after the harness had created a few more relations.

**The maintenance assumption leaves rule 3's census almost nothing to decide,
and that is the assumption working.** Every table a churn touched reaches the
census freshly analyzed: on both legs the census read 88 tables, analyzed 2,
and the highest share of changed rows it left alone rounds to 0.0 %. The census
analyzed the other two on both legs, and they are the two the
concept page says it should reach: `f85t`, whose build phase ran an `UPDATE` and a `VACUUM`
and no `ANALYZE` after them, at 100,000 changes against a threshold of 50,050, and
`x108t`, the never-analysed table of 108, at 500,000. The two per-table
overrides are still read as such — `b94t` at a threshold of **100** and `b95t`
at **610,000** — and neither table is analyzed, because both carry 0
modifications after their maintenance step. The census still applies the
engine's own test: `relation_needs_vacanalyze` takes the base threshold and the
scale factor from the table's **own reloption** whenever that reloption is
non-negative and from the cluster GUC only otherwise. The one difference between
the legs is the recheck, which finds `f85t` and `x108t` still above their
threshold on 12.2 and neither on 17.11, and records that as a disagreement
rather than analyzing again. Nothing in this page's statement reads a row count,
so none of this can move a single number it reports - which is itself the
cleanest demonstration of what a physical reading buys.
[autovacuum.c#anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3066-L3076),
[autovacuum.c#anl-effective-values](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3011-L3017),
[autovacuum.c#doanalyze](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095),
[rel.h#AutoVacOpts](../../../../raw/postgres-17/src/include/utils/rel.h#L308-L326),
[reloptions.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L243-L251),
[system_views.sql#n_mod_since_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L689),
[pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L583-L600),
[pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L330-L338).

The drain selects survivors by block number out of the tuple's own `ctid`, and
the `VACUUM` that follows is what turns the dead entries into pages a rebuild
can give back. What the drain does **not** guarantee is where the loss lands in
the index: a serial build makes leaf order key order, so whether the survivors
leave every leaf sparse or a contiguous run of pages that hold nothing follows
from each fixture's own key-to-heap correlation. That is why the harness records
the post-churn shape per fixture and asserts it wherever the prediction depends
on it — a fixture predicted reclaimable must show the space physically, as
leaves below the build target or as whole empty and deleted pages. Measured, and
**0 assertions failed on either leg**:

| Post-churn shape | 17.11 | 12.2 |
|---|---|---|
| sparse leaves and dead pages, predicted `rebuild` | 28 | 32 |
| dead pages only, predicted `rebuild` | 1 | 0 |
| sparse leaves only, predicted `rebuild` | 66 | 54 |
| sparse leaves, predicted `leave` | 16 | 16 |
| still dense, predicted `leave` | 14 | 14 |
| no leaf pages, predicted `leave` | 1 | 1 |

[itemptr.h#ItemPointerData](../../../../raw/postgres-17/src/include/storage/itemptr.h#L36-L40),
[nbtsort.c#sorted-build](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L4-L15),
[nbtree.c#btbulkdelete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L820-L843),
[nbtpage.c#_bt_pagedel](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1802-L1815).
Fixture 84's forged index count is applied after the maintenance step and the
census and survives both at `reltuples = 5000` against a real 100,000, which is
the point of ordering the forgeries last.
[analyze.c#totalindexrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L648-L660),
[index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2809-L2842).

Family 6 printed its catalog counts beside the populations its fixtures
counted, and no fixture reached the `-1` state: on both legs `p113b`, `p116`
and `p120` read a measured zero and `p114`, `p115`, `p118` and `p119` a count.
`p118` and `p119` read 48,580 and 49,980 on 17.11 and 50,000 and 48,300 on
12.2 against 50,000 counted rows, because the maintenance statement's `ANALYZE`
half re-estimated both after their arrivals, which is the concept page's own
point that the two fixtures now name one state.

#### What the maintenance assumption changed

History, and the before-and-after columns below are the 2026-09-12 and
2026-09-13 runs, not this one. The concept page added the maintenance
assumption on 2026-09-13. The port was re-read against it recipe by recipe, and
nine churned fixtures did not end on the maintenance step: 64, 66, 92, 93, 94,
95, 98, 115 and 118 stopped after a publish, and 119 after an `ANALYZE` alone.
The concept page names six of them outright — 64, 92 to 95, 98 and 118 — and 66,
115 and 119 follow from rule 1's cut plus the assumption's first part, because
each writes rows after its index build. All nine ended on `VACUUM` then
`ANALYZE` from that revision, and on one bracketed `VACUUM (VERBOSE, ANALYZE)`
from this one. The same pass removed tests 11, 11b and 38, which the concept
page had retired on 2026-09-12 and this port still built. Both legs were then
re-run from their pins.

| Change | Before, 2026-09-12 | After, 2026-09-13 |
|---|---|---|
| Fixtures the port builds | 131 on 17.11, 116 on 12.2 | **126** and **117**; the five retired indexes — `i_dupoff`, `i_text_off`, `i2_off`, `i_dedup_on_after` and `p38` — are gone. 12.2 had skipped all five, so its planned count is unchanged, and it scores one more because test 120's precondition held there this time |
| 12.2 skips at build | 14, five of them for the `deduplicate_items` reloption | **9**, every one for B-tree support function 4; no suite fixture sets the reloption any more |
| Worst under-estimate | `−9.8`, on `b93` and `b95` | **`−4.1`**, on `p32`, the same on both legs |
| `b92` to `b95` | `b93` and `b95` read 79.3 % against a measured 89.1 % | all four read **89.1 %** against a measured 89.1 %. The counted `UPDATE` had left dead index entries in the file, and the maintenance `VACUUM` removes them, so the old under-estimate was withheld maintenance too |
| Rule 3's census | 89 tables, 8 analyzed | **88 tables, 2 analyzed** (`f85t` and `x108t`); 86 read zero modifications on 17.11. The churned tables it used to analyze now reach it analyzed |
| Within 1.0 point of the oracle | 95 of 131 and 97 of 116 | 92 of 125 and 100 of 117, and 93 of 126 and 100 of 117 in the current run |
| `p64`, `p98`, `p115`, `p118` | dense, `leave`, and a stale or empty row count at decide time | still dense and `leave`, 0.0 % actual; their row counts are now re-estimated before decide |

**What the assumption cost this page.** Tests 92 to 95 no longer isolate the
analyze threshold, because all four are analyzed after their changes. 118 and
119 now name one state. And one more shape a density reading used to be scored
against is gone: the under-read on `b93` and `b95` was a withheld `VACUUM`,
which the suite no longer builds. The concept page files the first two as its
own open questions; the third is filed under this page's
[Open Questions](#open-questions).

#### The maintenance, proved not defeated

**The concept page added `### The maintenance must not be defeated` on
2026-09-15, after this page's previous run, and this revision is the first that
runs under it.** The assumption's part 3 forbids skipping the maintenance; this
rule forbids sabotaging it, because a `VACUUM ANALYZE` can be skipped for want
of a lock, cut short by a timeout, or left with a removal horizon that covers
everything it was asked to remove, and still return success. What it leaves
behind is the shape a fixture that never ran one leaves, with no missing
statement in the recipe to show for it.

Five edits brought the port onto the rule, and every one is in the `sql` blocks
this page files:

| Before, the 2026-09-13 run | Now |
|---|---|
| the maintenance step was `VACUUM x;` then `ANALYZE x;`, with `wiki_flush()` around each | one `VACUUM (VERBOSE, ANALYZE) x;` between `maint_begin('x')` and `maint_end('x')`, which flush on both sides. One statement, so one VERBOSE report to read a dead-tuple count out of, and `ANALYZE` is still the last writer of `reltuples` ([vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650)) |
| the fixture, drain and census sessions ran at `statement_timeout = '900s'` and a `lock_timeout` of 2 or 5 seconds | all three settable timeouts that exist on both majors are `0` in every session that issues maintenance, which is what an autovacuum worker does to its own, "to avoid letting these settings prevent regular maintenance from being executed" ([autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470), [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642), [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653)) |
| nothing recorded what a maintenance statement did | three tables do: `maint` per statement, `horizon` per probe, `pageclass` per planned index |
| nothing looked for a holder of the removal horizon | `horizon_probe()` runs before every maintenance statement and on both sides of the census, reading the backends with an `xmin` or an open transaction, the replication slots and the prepared transactions — the three kinds of holder `GetOldestNonRemovableTransactionId` folds in ([vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122), [procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815), [procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902), [twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26), [system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L878-L885), [system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017)) |
| a defeated fixture would have been scored | the `churn` stage checks the four proofs and **dies rather than score**: no end stamp, a missing or non-zero dead count, a horizon probe with a holder, or a skip or cancellation line in the server log each stop the run |

**What the run recorded.** Every maintenance statement of both legs, and the
same four proofs on each:

| Proof | 17.11 | 12.2 |
|---|---|---|
| Maintenance statements, all completed | **67** — 38 from rule 2's drain, 28 from the fixtures' own churn, 1 the `prebuild` of fixture 85 | **67**, the same split |
| `tuples: … are dead but not yet removable`, the statement's own count ([vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L657-L663)) | **0 on every one of the 67** | **0 on every one of the 67** |
| Tuples removed | 22,457,808 | 22,457,692 |
| Dead tuples left behind, re-read after the census | 0 | 0 |
| Horizon probes with a holder | **0 of 73** | **0 of 73** |
| Timeout sets in force | 1: `statement_timeout=0 lock_timeout=0 idle_in_transaction_session_timeout=0 transaction_timeout=0` | 1: the same three zeros and `transaction_timeout=n/a`, because 12.2 has no such setting |
| `skipping vacuum of …`, `skipping analyze of …`, `canceling …` lines in the server log | **0** | **0** |
| Page classes after the maintenance | 126 indexes read, 29 with deleted pages, **10,340 deleted pages**, 0 half-dead | 116 indexes read, 32 with deleted pages, **11,868 deleted pages**, 0 half-dead |

**Nothing was defeated before the rule either, and that is the result.** The
scores this revision files reproduce the 2026-09-13 run's shape fixture for
fixture — `PASS` on every scored fixture on both legs, the same three
`want_stage` misses, the same `−4.1` worst under-estimate on `p32` — so the
rule cost this page no verdict. What it bought is that the clean sheet is now
checked rather than assumed: before this pass nothing in either script would
have noticed a `VACUUM` that ran under a pinned horizon, and the reading it
produced would have been filed as a pass.

**What these proofs do not establish.** Three limits, stated rather than
implied. The horizon probe is a read taken beside the statement, not an
interlock around it: a session that opened a snapshot after the probe and
closed it before the next one would not appear, and the concept page records
the same limitation against its own definition. The `bl` guard fixtures keep
plain `VACUUM`s and are not bracketed, because they are not suite fixtures and
the assumption does not govern them. And `dead tuples left behind` is a
statistics reading taken after the census rather than a second VERBOSE report:
on 12.2 the counters travel to a collector process, so an immediate read can
still show the pre-vacuum count, which is why the run re-reads them once the
churn phase has finished ([pgstat_relation.c#report_vacuum-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L233-L246)).

#### The blind spot the suite stopped building

**Nothing in the suite defeats the reading any more**, and that is a change in
the suite rather than in the statement. It is worth stating plainly, because it
means this page no longer has a measured failure mode of its own.

Until the concept page's 2026-09-12 narrowing, four fixtures failed on both
majors and they were one failure mode: entries that left the index without a
`VACUUM` are still physically present, so every leaf page stays dense while a
rebuild would empty the file. Those four were 65, 67 and legs 113a and 113c, and
all four are retired, because each withheld a maintenance command. What the
2026-09-12 review run measured on them is history now, and the current suite
builds no replacement:

| Retired test | Fixture | What it did | The statement said | `REINDEX` gave back |
|---|---|---|---|---|
| 65 | `p65` | 90 % of the subset deleted, **no `VACUUM`** | `0.0 %`, density 89.83 | **89.1 %** |
| 67 | `p67` | 90 % of the subset moved out of the predicate by `UPDATE`, **no `VACUUM`** | `0.0 %`, density 89.83 | **89.1 %** |
| 113a | `p113a` | the whole queue drained, **nothing run** | `−0.1 %`, density 90.06 | **100.0 %** |
| 113c | `p113c` | the same, `ANALYZE` only | `−0.1 %`, density 90.06 | **100.0 %** |

The limit those numbers illustrated is still real and is still named by the
concept page for any density method: `pgstatindex` counts bytes that hold
entries, not entries that are still live, and a dead entry occupies its leaf
page until `btbulkdelete` runs `btvacuumscan` over the index and removes it. So
"vacuum first, then read" remains the operational order this statement needs.
**But on the current suite that is a source reading, not a measurement**, and a
method that misread an unvacuumed index would now pass; the gap is filed as
[an open question](#open-questions). The one fixture still in the suite that
shows the *mechanism* rather than the failure is `p113b`, the same drained queue
with the `VACUUM` and `ANALYZE` left in: 2,745 blocks of which 2,741 are
`deleted_pages`, density 0.05, the statement reads **99.9 %** and the rebuild
returns **100.0 %** — identically on both majors. The `VACUUM` is the whole
difference between that row and the retired 113a above it.

`VACUUM` can also decline to do that work, and the 2 % of heap pages this page
used to name as the condition is **one of four**. `lazy_vacuum` bypasses index
vacuuming only when `consider_bypass_optimization` is still set, when the
relation has at least one page, when `lpdead_item_pages` is *strictly* below
`rel_pages * BYPASS_THRESHOLD_PAGES`, and when the dead-item store is under
32 MB; when it does apply it turns off index *vacuuming* only, and index
cleanup still runs. No fixture on this page demonstrates a bypass, so that
statement is a source reading rather than a measurement.
[pgstatindex.c#leaf-accounting](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L304-L324),
[nbtree.c#btbulkdelete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L820-L843),
[vacuumlazy.c#BYPASS_THRESHOLD_PAGES](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L85-L89),
[vacuumlazy.c#bypass-conditions](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1899-L1934),
[vacuumlazy.c#bypass-applies](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949).

#### Accuracy against the oracle

`est_reclaimable_pct` against what `REINDEX INDEX` actually returned, over every
scored fixture:

| Measure | 17.11 | 12.2 |
|---|---|---|
| Fixtures scored | 126 | 117 |
| Within 1.0 point | **93** | **100** |
| Within 5.0 points | 125 | 116 |
| Worst over-estimate | **+10.0** | **+6.3** |
| Worst under-estimate | **−4.1** | **−4.1** |
| Filed prediction (`want_stage`) hit | 123 | 114 |

**The worst under-estimate is `p32`**, the extreme width-mismatch subset, which reads
85.5 % against a measured 89.6 % on a 636-block index with 168 dead pages, the
same on both legs; next come `f78` at `−3.5` on both and `p51` at `−3.3` on
17.11. The `−9.8` this table carried until the 2026-09-13 revision was `b93`
and `b95`, and the maintenance step removed it; see
[What the maintenance assumption changed](#what-the-maintenance-assumption-changed).
The worst over-estimate is the direction that matters operationally, because it
promises space a rebuild will not return, and on this suite it is still bounded
by ten points on 17.11 and about six on 12.2. Both bounds are rows a reader
sees: `p25` is a ten-block index on 17.11, read at 70.0 % against 60.0 %, and a
sixteen-block one on 12.2, at 81.3 % against 75.0 %. The three `want_stage`
misses are the same on both legs and all three are `PASS`: `p73` at 49.3 %,
`p76` at 49.5 % and `f88` at 40.5 % (43.6 % on 12.2) were predicted as rebuilds
and fell just under the harness's 50 % threshold, which is where a threshold
sits.

#### What the shared suite says that the retired fixture set could not

Three things this page could not have learned from the 32-fixture set it used
until 2026-09-11:

1. **A physical reading is immune to the catalog traps.** Family 3's eight
   constructions exist to catch a method that believes `pg_class.reltuples` or
   `pg_statistic`, and `f84`'s forged index count and `f85`'s stale table
   statistics are the two the wiki's catalog-only estimator reports as critical
   false positives on the same fixtures
   ([its own run records them](btree-index-bloat-core-sql-only.md#the-mandatory-suite-re-scored-under-the-shared-protocol)).
   All eight pass here, on both majors, because this statement reads neither
   column.
   [pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L64-L66),
   [analyze.c#tupleFract](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953).
2. **The equal-image gate is invisible to it, and the decision is still right
   25 times out of 25.** Family 1 builds 25 indexes whose deduplication
   eligibility varies by opclass, collation and `INCLUDE` column; the statement
   reads none of that and passes all 25, because after the drain every one of
   them is sparse whatever its keys are. Where the gate does show up in a number
   is the undrained guard fixture `i_dedup_off`; see
   [Deduplication changes the input, not the arithmetic](#deduplication-changes-the-input-not-the-arithmetic).
3. **The threshold, not the estimate, is what the borderline fixtures test.**
   The calibration ladder 72-75 deletes a quarter, a half, three quarters and
   nine tenths of a subset; the statement read **24.6, 49.3, 74.3 and 89.1**
   against a measured **25.0, 49.6, 74.3 and 89.1**, identically on both majors,
   and only the half-deleted rung fell on the wrong side of the harness's
   threshold - by 0.7 of a point, with the oracle at 49.6 % agreeing that
   nothing much was there. Beside it, test 76 is the shape a row-count method
   cannot see at all: indexed-key `UPDATE`s took the file from 276 to 551 blocks
   while the subset's population never moved, and the statement read 49.5 %
   against a measured 49.9 %.

#### The two majors, side by side

The two reports cover whole databases, so the comparison is one the `crossleg`
stage makes for both legs at once, on `schema_name` plus `index_name`: 365 rows
on 17.11 against 350 on 12.2, 289 keys printed by both, **181 rows identical
field for field**, 108 shared keys differing, 76 keys only 17.11 prints and 61
only 12.2 does.

| Schema | Printed, 17.11 | Printed, 12.2 | Both | Identical | Differ | Only 17.11 | Only 12.2 |
|---|---|---|---|---|---|---|---|
| `public`, the suite's fixtures | 130 | 121 | 121 | 81 | 40 | 9 | 0 |
| `bl`, the guard fixtures | 18 | 17 | 17 | 15 | 2 | 1 | 0 |
| `pg_catalog` | 124 | 117 | 115 | 51 | 64 | 9 | 2 |
| `pg_toast` | 93 | 95 | 36 | 34 | 2 | 57 | 59 |

**Read the two fixture schemas, and treat the other two as scenery.** A TOAST
index is named for the OID of its table, so a name matching across two
independently created clusters is a coincidence — 36 of about 94 do — and the
catalog differs between the majors by construction, both in which indexes exist
and in how much they hold.

In the two fixture schemas, 138 keys are printed by both legs, 96 rows are
identical field for field, and 42 differ. Two of the 42 are the harness's own
bookkeeping indexes — `plan_pkey` and `snap_pkey` — which hold the same number
of leaf pages but different contents, because the two legs plan and skip
different numbers of fixtures. **The other 40 all point the same way: fewer
leaf pages on 17.11**, and the two mechanisms below are why. `i_dup` reads 843
leaves against 2,733, `i_int4` 417 against 1,367, `p48` 87 against 384.
Nothing in either fixture schema is larger on 17.11. The 10 keys only 17.11
prints are the shapes 12.2 cannot build — the nine that need a B-tree support
function 4, plus the `i_dedup_off` guard fixture — and 12.2 prints no fixture
that 17.11 does not.

**Deduplication is the larger mechanism but not the only one, and `p68` is the
row that proves it.** It carries 50,000 distinct keys over 50,000 predicate
rows — counted again in this run, not assumed — and still reads 1,093 leaves at
11.52 % density on 17.11 against 1,366 at 9.27 % on 12.2. Its churn is five
`UPDATE`s that move rows in and out of the predicate while the key never
changes, and the v17 tree deletes index entries on that path before it
considers a page split: `ExecInsertIndexTuples` passes an `indexUnchanged` hint
for an `UPDATE`, and `_bt_delete_or_dedup_one_page` then runs a bottom-up
deletion pass on that hint alone, "deliberately omit[ting] an
index-is-allequalimage test". So a churned index can differ between the two
servers with no duplicate key anywhere in it. Which release first behaved that
way is not readable from this page's evidence base, and is
[an open question](#open-questions).
[execIndexing.c#indexUnchanged](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L427-L445),
[nbtinsert.c#bottom-up-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2776),
[nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L285-L308).

Both servers also produced the same message for every rejected shape, the same
implied leaf capacity, the same fresh-build densities at four fillfactors, the
same `22,487,040` bytes and 1,918 dead pages on the head-deleted fixture, and
the same three privilege outcomes. The one behavioural difference is still the
invalid index, and it is
[a difference between these two minors](#the-one-behavioural-difference-between-12-and-17).

#### What the 2026-09-12 review repaired

History, kept because the defects it names could recur. The 2026-09-11 run was
scored against the concept page as it stood that day. The concept page was
revised on 2026-09-12, and a review that day re-read this page's port against it
claim by claim. Its log entry and its label on this page used to read
2026-09-13, a day ahead of its commit; both now carry the commit's date. **Six
defects, every one confirmed and fixed in the filed `sql` blocks, then re-run
end to end on both legs:**

| Defect | What it did | What the fix changed |
|---|---|---|
| Rule 3's census read `current_setting()` for every table | decided fixtures 94 and 95 against the cluster threshold of 41,050 instead of their own 100 and 610,000 | both fixtures decided the other way, and the census prints the two per-table overrides it read |
| The churn published its counts once, not twice | on 12.2 the drain's deletes reached `mod_since_analyze` *after* its own `ANALYZE` had zeroed it, so the census analyzed 31 or 51 tables where 17.11 analyzed 17 | `wiki_flush()` forces the publish where SQL can and waits out the publish interval where it cannot, and both legs censused 17 of 99 at that revision |
| Family 1 had no test 11b | the off-to-on `deduplicate_items` transition was measured only by this page's own undrained guard fixture | 11b was built and scored; the concept page later retired it, and the 2026-09-13 re-port removed it again |
| Test 120's precondition was assumed | the fixture was credited whether or not the `ANALYZE` sample missed its 2,000-row subset | asserted after the census, and recorded as an unmet precondition whenever the sample finds the subset |
| Rule 2's drain was described as losing entries from every leaf | the guarantee is volume, not distribution | the harness records the post-churn shape per fixture and asserts it where the prediction depends on it |
| The 2 % index-vacuum bypass was named as *the* condition | it is one of four | stated as one of four, with the strict comparison, the 32 MB cap and the cleanup that still runs |

The same review narrowed three claims because measurement contradicted them —
the cross-major differences are **not** all deduplication, one sample row came
from a retired population, and 12.2's census count is not a fixed property of
the major — and it added the `compare` stage, which re-derives the two
`Follow-up` sections' output-equivalence tables on each run's own population.

#### What the re-sync to the narrowed suite changed

History as well. The concept page narrowed the suite on 2026-09-12, retiring
every fixture that withheld a maintenance command, and this page's port was
re-synced the same day: the eight withheld-maintenance fixtures — ten indexes,
`p65`, `p67`, `p69`, `x106`, `p113a`, `p113c`, `p117`, `nz_k`, `nzb_k` and
`i_trunc` — left the port, their numbers were not reused, and both legs were
re-run. That removed the four `FALSE NEGATIVE`s the reading itself had produced
(`p65`, `p67`, `p113a` and `p113c`), moved the worst under-estimate from
`−100.1` to `−9.8`, and moved the census from 17 of 99 tables analyzed to 8 of
89. It also added family 6's catalog-count check. The numbers it filed are all
superseded by the current run.

### What it gets wrong, measured

Three failure modes, all measured by the two filed scripts, in the order a
reader should worry about them. The fourth — entries deleted but not yet
vacuumed, which cost `−89.1` and `−100.1` points — **is no longer measured by
anything on this page**, because the four fixtures that produced it are retired;
see [The blind spot the suite stopped building](#the-blind-spot-the-suite-stopped-building)
and [Open Questions](#open-questions). The operational advice it produced has
not changed: vacuum first, then read.

1. **Deduplication the current index is not using.** `i_dedup_off`, built with
   `deduplicate_items = off` and then switched on, reports 90.16 % density and
   `−0.3 %` while `REINDEX` takes the file from 22,519,808 to 6,963,200 bytes:
   **69.1 % reclaimed, `−69.4` points**. No `pgstatindex` column distinguishes
   such an index, and it is **this page's largest measured miss**. The shared
   suite no longer covers the condition at all, since its test 11b was retired
   with every other explicit `deduplicate_items` setting, so this guard fixture
   is the only thing on the page that measures it. 12.2 cannot build the shape
   at all.
2. **Indexes too small to fill a page, and the report prints all of them now.**
   `c_zero_idx`, whose single leaf page holds nothing, reports `0.0 %` against a
   measured 50.0 %: the rebuild takes it from two pages to one. In the other
   direction `c_one_idx`, one row on one page, reports `44.6 %` in
   `wasted_ff_pct` that no rebuild returns, and the worst over-estimate on the
   whole suite is `p25` at `+10.0` points on ten blocks. The same rounding leaves
   a 14.9 % residual on a two-leaf-page index immediately after `REINDEX`,
   against 0.3 % or less for every fixture at or above 1 MB. None of this is
   new arithmetic; what changed is that no prefilter keeps those rows out of
   the output, and no `notes` string marks them.
3. **A concurrent `DROP INDEX` can take the whole report with it.** `cand` is a
   pure catalog read, so a drop that commits after the statement's snapshot
   leaves a candidate whose relation `pgstatindex` then cannot open, and the
   report ends in `ERROR: could not open relation with OID …` with no rows at
   all. Measured on both servers, in both windows, in the current run; see
   [Locking, timeouts, and the concurrent-drop race](#locking-timeouts-and-the-concurrent-drop-race).

### Deduplication changes the input, not the arithmetic

Deduplication is the largest source of same-statement, different-numbers between
the two servers. The 12.2 server has no `deduplicate_items` reloption — it
refuses the guard fixture below with `unrecognized parameter
"deduplicate_items"` — and its indexes come out as large as a non-deduplicating
build predicts, which is measured here rather than cited, since this page may not
cite the v12 source. Two fixtures with a key of ten distinct values over a
million rows:

| Fixture | 12.2 size | 17.11 size | 12.2 est / actual | 17.11 est / actual |
|---|---|---|---|---|
| `i_dup`, built by `CREATE INDEX` | 21 MB, 2,733 leaves | 6800 kB, 843 leaves | −0.3 / 0.0 | 0.0 / 0.0 |
| `i_dup_ins`, built empty then filled | 20 MB, 2,570 leaves | 6368 kB, 790 leaves | −6.6 / −6.4 | −6.7 / −6.8 |

The estimate is right on both servers. What changed is the index: on 17.11 the
duplicates are already posting lists, so the payload `pgstatindex` measures is
already the compressed payload, and a rebuild reproduces it. Both rows come from
the `guard` stage, which rebuilds each fixture and measures the file on both
sides of the rebuild.

The failure case is an index whose pages are **not** deduplicated but whose
rebuild would be. `i_dedup_off` builds one deliberately with
`deduplicate_items = off`
([nbtree.h#BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1146-L1151)),
then turns the option back on: the report reads 90.16% density, `0.0` wasted and
`−0.3%` reclaimable, and `REINDEX` takes the file from 22,519,808 to 6,963,200
bytes — **69.1% reclaimed, a `−69.4`-point miss, the largest of any fixture on
this page**. The reloption does not exist on 12.2, so the fixture is
unconstructible there, and the 12 leg records that as a skip with the server's
own message: `unrecognized parameter "deduplicate_items"`.

The shared suite does not cover this condition. It carried it briefly as test
11b, drained, where the statement passed at a `−6.3`-point under-estimate, and
the concept page retired 11b on 2026-09-12 together with every other fixture
that sets `deduplicate_items` explicitly. `i_dedup_off` is therefore the only
measurement of it on this page, and a method that misses it passes the suite;
that is filed under [Open Questions](#open-questions).

A realistic version of this is a cluster upgraded from 12 with `pg_upgrade`. The
v17 code relies on `btm_allequalimage` being zeroed on the version 4 indexes such
an upgrade carries over, so they cannot deduplicate until they are rebuilt
([nbtpage.c#_bt_metaversion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L727-L736),
[nbtree.h#btm_allequalimage](../../../../raw/postgres-17/src/include/access/nbtree.h#L103-L119)).
`pgstatindex` returns `version` but not that flag, and the 12.2 server's own
indexes already report version 4 in this run, so no column the statement reads
distinguishes them. That case, and the core-SQL test for it, is
[Checking Whether an Index Needs a Rebuild to Enable Deduplication After pg_upgrade From PostgreSQL 12 to 17](btree-deduplication-after-pg-upgrade.md).

### What it costs to run

This report reads every page of every index it reports on. That is the price of
not depending on statistics. `EXPLAIN (ANALYZE, BUFFERS)` attributes it precisely,
because the reads go through the buffer manager:

| Server | Indexes in the database | Rows printed | Buffers, whole statement | Execution |
|---|---|---|---|---|
| 12.2 | 355 B-tree over 157,249 blocks | 354 | 31,905 hit + 129,225 read, 161,130 blocks (1.23 GiB) | 250.6 ms |
| 17.11 | 370 B-tree over 151,667 blocks | 369 | 34,387 hit + 122,663 read, 157,050 blocks (1.20 GiB) | 258.0 ms |

**Reading every index costs less than it sounds like it should**, because the
indexes a size prefilter removes are the small ones by definition. What this run
measures directly is the two texts interleaved end to end through psql, warm, six
runs each: the filed text takes 221.4-262.5 ms against the fillfactor-era text's
223.2-266.6 ms on 17.11, and 228.6-306.6 ms against 211.0-250.1 ms on 12.2. The
fillfactor-era text is timed as filed, prefilter included, so it reads 259 and
231 fewer indexes; the overlapping ranges are the whole cost of reading them.

The cost scales with the bytes of index, not the number of indexes: both
databases hold about 1.2 GiB of B-tree and the statement reads all of it, in
about a quarter of a second, on a host where every one of those files had just
been built and read by earlier stages. On cold
storage the same read is a disk-bandwidth problem, and there is no longer a knob
in the statement to make it smaller — a caller who needs one adds a predicate,
as [Why every candidate filter is there](#why-every-candidate-filter-is-there)
describes.

The plan is two nodes shorter than it was, and for a reason worth naming:
`params` is now referenced once, by `modelled`, so the planner inlines it instead
of scanning it twice
([subselect.c#SS_process_ctes](../../../../raw/postgres-17/src/backend/optimizer/plan/subselect.c#L911-L955)).
The plans hold 2 `CTE Scan` nodes on both servers — `cand`, which is
`AS MATERIALIZED`, and `measured` — with 62 plan lines on 17.11 and 57 on 12.2,
as `psql` counts them, and planning at 2.6 and 4.4 ms.

One mitigation is left, and it is the AM's rather than the statement's: the scan
uses a `BAS_BULKREAD` strategy, a 256 kB ring
([pgstatindex.c:222](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L222),
[freelist.c#GetAccessStrategy](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L540-L574)),
so a large report does not evict the buffer pool. `EXPLAIN (BUFFERS)` prints a
`written=` counter only when the statement wrote a shared buffer out
([explain.c#shared_blks_written](../../../../raw/postgres-17/src/backend/commands/explain.c#L3782-L3784)),
and this run's plans show none on either leg.

### Privileges

`pgstattuple` 1.5 revokes `EXECUTE` from `PUBLIC` and grants it to
`pg_stat_scan_tables`
([pgstattuple--1.4--1.5.sql#grants](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92),
[pgstattuple.sgml#access](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L15-L24)).
The `_v1_5` entry points carry no `superuser()` check; only the pre-1.5 symbols do
([pgstatindex.c#pgstatindex_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L162-L180),
[pgstatindex.c#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L144-L160)).

Measured identically on both servers with a login role `mon` whose only privilege
is membership in `pg_stat_scan_tables`:

- `mon` runs the whole statement and gets every row — 369 on 17.11 and 354 on
  12.2, the whole population at that stage — including indexes on tables in a
  schema it has no `USAGE` on (`has_schema_privilege('mon', 'bl', 'USAGE')` is
  false on both).
- `pgstatindex('bl.i_delhead')` by **name** fails for `mon` with
  `ERROR: permission denied for schema bl`, because the text form opens the index
  through `relation_openrv`, and resolving a schema-qualified name checks schema
  `USAGE`
  ([pgstatindex.c#pgstatindex_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L170-L180),
  [namespace.c#RangeVarGetRelidExtended](../../../../raw/postgres-17/src/backend/catalog/namespace.c#L528-L532),
  [namespace.c#LookupExplicitNamespace](../../../../raw/postgres-17/src/backend/catalog/namespace.c#L3388-L3420)).
  This is why the statement passes `c.idx_oid::regclass`: the OID overload never
  resolves a name, and the same index by OID returns its 821 leaf pages to the
  same role.
- A role without the membership gets
  `ERROR: permission denied for function pgstatindex`.

So the grant needed is exactly `GRANT pg_stat_scan_tables TO <role>`, and it
carries page-level visibility into every table in the database. No `SELECT`
privilege on the indexed tables is involved at any point.

### Locking, timeouts, and the concurrent-drop race

`pgstatindex` takes `AccessShareLock` on the index
([pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L204-L213)),
so it waits behind anything holding `AccessExclusiveLock`. With another session
sitting on an uncommitted `DROP INDEX`, `lock_timeout = '2s'` cancelled the call
at 2010.9 ms on 17.11 and 2011.6 ms on 12.2:

```text
ERROR:  canceling statement due to lock timeout
```

**A drop that commits while the statement is running ends the report, wherever
it lands.** That is the price of the size prefilter's removal, and it is now
measured rather than reasoned about. `cand` is a pure catalog read: it scans
`pg_class` under the statement's own MVCC snapshot and opens nothing, so an index
dropped and committed after that snapshot is still a candidate when
`pgstatindexbyid_v1_5` reaches it, and that function uses `relation_open`, which
raises rather than returning NULL
([pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L204-L213),
[relation.c#relation_open](../../../../raw/postgres-17/src/backend/access/common/relation.c#L47-L61)):

```text
ERROR:  could not open relation with OID 18970
```

Both timings were driven against the same `bl.i_race` fixture and both aborted,
identically on the two servers:

| What the second session did | 17.11 | 12.2 |
|---|---|---|
| Took `AccessExclusiveLock` one second before the report started and committed two seconds later | the report blocked on that index, then `could not open relation with OID 18970` after 2006 ms; **0 rows, against 371 with no drop** | the same message, at `OID 19328`, after 2007 ms; **0 rows against 356** |
| Started after the report, swept across ten delays from 5 ms to 2 s | aborted at the **first** delay, 5 ms in: `could not open relation with OID 19882` after 2013 ms | the same at the first delay, `OID 20219` after 2014 ms |

The second row closes a gap this page carried for four revisions. Until the
prefilter went, `cand` sized every candidate with `pg_relation_size`, whose
`try_relation_open` returns NULL for a relation that has gone — the comment
above it says returning NULL "for already-dropped tables" beats throwing "and
abort the whole query"
([dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L346-L371))
— so the candidate disappeared silently and the report came back one row
shorter, while the abort needed the drop to land in the few milliseconds between
that size check and the per-index call. Three sweeps of ten delays never landed
in it. With the call gone the window is the whole report, and the first attempt
at 5 ms found it on both servers, in this run as in the one before it.

So the operational advice is stronger than it was: **one dropped index loses the
whole report**, not one row, and no timing luck is needed. On a database with
heavy DDL, add a predicate that excludes the tables under migration, put back a
`pg_relation_size(c.oid) >= 0` test to buy the old shield, or drive
`pgstatindex` from a loop that catches the error per index and keeps going.

### How this was measured

Every number on this page comes from the two scripts under
[Measurement Script](#measurement-script), run end to end for this revision on
2026-09-16, both legs concurrently on one Linux x86_64 host, one leg per pinned
major:

- **17.11**, `server_version_num` 170011, built out of tree from this page's pin
  `786db8dcf168bd9df8f55047337525ac19118b1c` with
  `--enable-debug --with-icu --with-readline --with-zlib`; `make check` **All 225
  tests passed** and `contrib/pgstattuple` **All 1**, both before a fixture
  existed.
- **12.2**, `server_version_num` 120002, built the same way from the v12 pin
  `45b88269a353ad93744772791feb6d01bc7e1e42`, also `--with-icu` because five
  fixtures of the shared suite need ICU collations, with
  `CFLAGS="-O2 -g -DTRUE=1 -DFALSE=0"` to restore the two macros ICU 68 removed;
  `make check` **All 192 tests passed** and `contrib/pgstattuple` **All 1**.

This host has `pkg-config`, so neither build needed `ICU_CFLAGS` and
`ICU_LIBS`; on a host without it both must be exported, as
[Prerequisites](#prerequisites) describes. Both clusters ran at `block_size`
8192, `max_data_alignment` 8, `initdb --locale=C --encoding=UTF8`,
`autovacuum = off`, `fsync = off`, `shared_buffers = 512MB`, on Unix sockets
inside the sandbox at ports 55417 and 55412. `pgstatindex` is the only
measurement function: no `pageinspect`, no `pgstattuple()`, no `amcheck`.
`REINDEX INDEX` is the only oracle, for the suite's 126 and 117 scored fixtures
and for the 18 and 17 guard fixtures alike.

Both legs read the same six `sql` blocks out of this page and refuse to run when
any of them does not hash to the constant filed in the script, so the text that
was measured is the text that is published. The statement itself is `sql` block
1, `3d4507a54b38…`, **123 lines and 5,976 bytes**, unchanged by this revision
and by the three before it. Blocks 2, 4, 5 and 6 changed, all for the no-defeat
rule: block 2 gained the `maint`, `horizon` and `pageclass` tables and the four
functions that bracket a maintenance statement; block 4 turned its 33
maintenance statements into bracketed `VACUUM (VERBOSE, ANALYZE)` calls and
zeroed its timeouts; block 5 did the same for the drain's 38; and block 6
zeroed its timeouts, probes the horizon on both sides of the census and reads
the page classes. Block 3, family 1, is unchanged. Every hash constant in both
scripts moved with them.

What the 2026-09-11 run replaced is the fixture set: until then this page scored
32 fixtures of its own in schema `bl`, and the shared mandatory suite now
supplies the scored population while `bl` keeps only the guard and model shapes
the suite does not cover. What the 2026-09-12 review added is the `compare`
stage, which re-derives the two `Follow-up` sections' output-equivalence tables
on each run's own population, against both superseded texts recovered from their
own commits and hash-checked. **This revision re-derived every measured number
again**, on a different host from the 2026-09-13 run and under the no-defeat
rule; the only numbers kept from earlier runs are the plan shapes and timings
the two `Follow-up` sections attribute to their own revisions, and the four
readings of retired fixtures under
[The blind spot the suite stopped building](#the-blind-spot-the-suite-stopped-building),
each labelled with the run that took it.

Nothing is retained. The scripts create `.wiki-runtime/tmp/pgsi/`; the 12 leg's
`clean` stage and then the 17 leg's stopped both servers, confirmed the
teardown and deleted the sandbox.

## Measurement Script

Two scripts produce every number this page takes from a running server, one per
version leg: `bloat_pgstatindex_v17.sh` for 17.11 and `bloat_pgstatindex_v12.sh`
for 12.2. Both are filed in full below, in Bash and SQL only, and both ran end
to end on 2026-09-16 on Linux x86_64, every stage in one invocation per leg.

**The fixtures they score are the shared suite's, not this page's own.** The six
families, the five phases, the three porting rules, the `REINDEX INDEX` oracle
and the four verdict bands are defined once for this version in
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md),
and the suite's harness, its fixture text and its churn phase are filed here as
`sql` blocks 2 to 6 so that both legs read the same suite out of this page. What
the run measured is
[The mandatory suite, scored on both majors](#the-mandatory-suite-scored-on-both-majors);
what is local to this page is
[Mandatory test review](#mandatory-test-review).

Schema `bl` holds the guard and model fixtures the suite does not cover and this
page still measures: the shapes `pgstatindex` refuses, an index the catalog says
is not valid, two pages of known contents, fresh builds at four fillfactors, the
four fillfactor-deleted fixtures, the dead-page fixture, the two duplicate
builds and the build-with-deduplication-off shape. Those are not scored
fixtures and no verdict band is applied to them.

### How to use the two leg scripts

| Item | The 17 leg, `bloat_pgstatindex_v17.sh` | The 12 leg, `bloat_pgstatindex_v12.sh` |
|---|---|---|
| Purpose | builds 17.11 from this page's pin, runs its regression suites, builds the shared mandatory suite and the `bl` guard fixtures, executes this page's `sql` block 1 exactly as filed, and scores every suite fixture against a measured `REINDEX INDEX` under the shared four bands | the same on 12.2 from the v12 pin, and it answers the three questions the 17 leg cannot: whether the exact filed text still executes unmodified on the oldest major this page claims, which fixtures of the shared suite a 12.2 server cannot build at all, and — in its `crossleg` stage — how the two majors' reports differ row by row |
| Invocation | `bash bloat_pgstatindex_v17.sh [stage ...]`, run from the repository root | `bash bloat_pgstatindex_v12.sh [stage ...]`, run from the repository root |
| Stages | 19 stages plus `stop` and `clean`; see [the stages](#the-stages-both-legs). With no argument every stage runs, in the table's order | the same 19 with the same meanings, plus `crossleg`, which reads the two legs' reports out of the shared `out/` and compares them |
| Environment | 9 variables, all with defaults; see [what the scripts read](#what-the-scripts-read-from-the-environment) | the same 9 plus `EXTRA_CFLAGS`, two of them named for this leg |
| Prerequisites | a C toolchain, ICU, readline and zlib headers with either `pkg-config` or exported `ICU_CFLAGS` and `ICU_LIBS`, `git`, `sha256sum`, a nanosecond `date`, and the pinned checkout at `raw/postgres-17`; see [Prerequisites](#prerequisites) | the same, and ICU is required here too: five fixtures of the shared suite need ICU collations, so this leg passes `--with-icu` and restores the `TRUE`/`FALSE` macros ICU 68 removed through `CFLAGS` |
| Output | under `$SANDBOX/out`; **read `verdicts17.txt` first**, then `maint_proofs17.txt` for the no-defeat proofs, `skipped17.txt` for what the server could not build, `decide17.txt` for the population, `facts17.txt` and `guard17.txt` for the version-local facts and the guard fixtures, `residual17.txt` for the post-rebuild residual, `census17.txt` for rule 3's decisions, family 6's catalog counts and the page classes, and `compare17.txt` for the filed text against the two texts it superseded. Build and check logs are copied there so they survive `clean` | the same directory, with `12` in every name: `verdicts12.txt`, `maint_proofs12.txt`, `skipped12.txt`, `decide12.txt`, `facts12.txt`, `guard12.txt`, `residual12.txt`, `census12.txt`, `compare12.txt`, plus the one file that belongs to neither leg, `crossleg.txt` |
| Runtime | on the last run, a 22-core Linux x86_64 host with both legs running at once and the trees already built: `check cluster texts` took about **25 seconds** at `JOBS=10`, `fixtures suite churn` about **1 minute 25 seconds**, and `report` through `summary` about **55 seconds**, for **2 minutes 42 seconds** end to end. A first run adds the build, a few minutes more | about **20 seconds** for `check cluster texts`, then about **7 minutes 15 seconds** for `fixtures suite churn`, most of it waiting: `wiki_flush()` cannot force a statistics flush on this major, so it sleeps out the publish interval instead, twice per maintenance statement among other places, and `report` through `crossleg` about **55 seconds**. **8 minutes 27 seconds** end to end |
| Cleanup | `bash bloat_pgstatindex_v17.sh clean` stops the server with `pg_ctl -m fast -w stop`, confirms the teardown — no `postmaster.pid`, no postgres process on the data directory, an empty socket directory — and only then deletes `$SANDBOX`, after checking it is inside `$WIKI_ROOT/.wiki-runtime/tmp/`. `stop` does the first two and keeps everything. **`out/` is inside `$SANDBOX`, so copy it out first** | `clean` stops the 12 server the same way and deletes only this leg's `build12`, `install12`, `data12`, `sock12` and `sql12`, because the 17 leg owns the shared `out/`. Run the 17 leg's `clean` last to remove the sandbox |

Save the two `sh` blocks below under those names and run them from the
repository root: `WIKI_ROOT` defaults to `$PWD`, and everything else — this
page, both pinned checkouts and the sandbox — is resolved beneath it. The five
`sql` blocks stay in this page; the scripts read them out of it and refuse to
run on a text that does not hash to the filed one.

```sh
bash bloat_pgstatindex_v17.sh                     # every stage, in order
bash bloat_pgstatindex_v17.sh score residual      # selected stages
bash bloat_pgstatindex_v12.sh report              # just the 12.2 execution result
bash bloat_pgstatindex_v17.sh clean               # stop and delete the sandbox
```

#### The stages, both legs

Every stage is idempotent and re-runnable on its own once the stages it needs
have run. The default order is the order of this table, and that order matters
in one place: `score` rebuilds every scored index, so `report`, `decide`,
`facts`, `cost` and `priv` have to precede it, and `residual` and `race` follow
it.

| Stage | What it does | Needs first |
|---|---|---|
| `build` | configures the pinned checkout out of tree under `$SANDBOX/build17`, installs into `$SANDBOX/install17`, then builds and installs `contrib/pgstattuple`; skips everything when the binary already exists. Copies `configure.log`, `make.log` and `install.log` into `out/` on the failure path too, because `clean` deletes the build tree | nothing |
| `check` | `make check` plus the `pgstattuple` check, one result line each into `out/checks17.txt`, then copies every `check_*.log` and any `regression.diffs` into `out/` | `build` |
| `cluster` | `initdb --locale=C --encoding=UTF8`, writes the settings below into `postgresql.conf`, starts on `PORT`, creates the database and `CREATE EXTENSION pgstattuple`, writes a run mark into the server log for the error audit, and records `uname -sm`, the version, `block_size`, `max_data_alignment` and the two autovacuum analyze settings into `out/platform17.txt` | `build` |
| `texts` | extracts `sql` blocks 1 to 6 from this page and checks each one's SHA-256 against the constant at the top of the script, generates the harness view from block 1 with one edit, printed — the two `SET` lines dropped — and recovers the two superseded texts from `OLD_REV` and `OLD_REV_ALERT` unedited. Their size prefilters are neutralised only where `compare` turns each text into a view, so that all three are compared over one population; `cost` times the recovered text as filed, prefilter included | `cluster` |
| `fixtures` | drops and rebuilds schema `bl`: fresh builds at four fillfactors, the four fillfactor-deleted fixtures, the dead-page fixture, the two duplicate builds, the deduplication-off shape where the server accepts the reloption, two known-content pages, an empty table's primary key, the shapes `pgstatindex` refuses and an index the catalog says is not valid | `cluster` |
| `suite` | phases 1 and 2 of the shared suite: recreates schema `public` with `initdb`'s `USAGE` grant, installs the harness of `sql` block 2 — the plan, the snapshots, the verdict view and the `maint`, `horizon` and `pageclass` tables the no-defeat rule needs — builds family 1 from block 3 under `client_min_messages = debug1` so `_bt_allequalimage` logs its own verdict, builds families 2 to 6 from block 4, then checks every fixture's build contract while it is still as built. Its stdout and stderr are split, because the fixtures' bracketed `VACUUM (VERBOSE, ANALYZE)` statements report on stderr and the next stage parses them | `texts` |
| `churn` | phase 3, in the suite's order: rule 2's uniform drain from block 5, each table ending on one bracketed `VACUUM (VERBOSE, ANALYZE)`, in its own session; then the VERBOSE output of every maintenance statement this run issued, turned into one recorded row per table; then rule 3's census, the catalog forgeries, the page classes and the churned snapshot from block 6 in another session, because on the 12 leg a backend's pending statistics publish when it exits; then the rule's four proofs, which **die rather than score** a fixture whose maintenance was defeated. The fixtures with churn of their own ran their bracketed maintenance inside block 4, during `suite`. Writes `drain17.txt`, `drain_verbose17.log`, `census17.txt` and `maint_proofs17.txt` | `suite` |
| `report` | phase 4, part one: runs the filed text **as filed**, both `SET` lines included, records whether it executed and how many rows, columns and bytes it returned, and loads the rows it printed back into `report_filed`, which is what `reported` means in the verdict view | `texts`, `suite` |
| `decide` | phase 4, part two: materializes the same text as a table over its internal `final` stage, so every intermediate column is visible, and checks the two readings against each other — they must agree on every row, and the view may hold no row the report did not print | `report` |
| `facts` | the version-local facts: candidate count, `index_size` against `pg_relation_size`, the two `NaN` comparisons, ten refusals, the invalid index, fresh-build density at four fillfactors, the implied `max_avail` from two known-content pages, the post-`VACUUM` size of the head-deleted index, one row per `bl` guard fixture, and another session's temp index | `decide`, `fixtures` |
| `cost` | the database's B-tree population and size, `EXPLAIN (ANALYZE, BUFFERS)` of the filed text with `plan_lines` counting only the plan, then six interleaved end-to-end runs of the filed text and the fillfactor-era text as filed. A run that fails is marked `filed_run_failed` or `prev_run_failed` rather than timed as a success | `texts` |
| `priv` | creates two login roles, grants `pg_stat_scan_tables` to one, and reads an index three ways: the whole statement, by name, and by OID | `texts`, `fixtures` |
| `compare` | the filed text against the two texts it superseded, recovered from their own commits and hash-checked: what each prints, which columns each one's internal `final` stage exposes, `EXCEPT` in both directions over the shared columns, and the two properties the fillfactor rebase claims. Both sides of every comparison are read in one query, so they see one index state | `texts`, `report` |
| `score` | phase 5, the oracle: for every fixture in the plan, reads what the statement said, calls `pgstatindex` itself, runs `REINDEX INDEX`, measures the file again, then writes the verdict tables into `out/verdicts17.txt`, including the post-churn shape assertion. **Destructive**: it rebuilds every scored index | `decide` |
| `guard` | the same oracle over schema `bl`: one `REINDEX INDEX` per guard fixture, the file measured before and after, and the statement re-read for each one's post-rebuild residual, into `out/guard17.txt`. No verdict band is applied, because these are not suite fixtures. **Destructive** | `decide`, `fixtures` |
| `residual` | re-reads the statement over exactly the population `score` rebuilt and writes the post-`REINDEX` residual of `wasted_vs_fillfactor` | `score` |
| `race` | the `lock_timeout` cancellation, then the two concurrent-drop timings on the `bl.i_race` fixture: a drop that commits while `cand` runs, and a sweep of ten delays aimed at the window between `cand` and the per-index call | `texts`, `fixtures` |
| `errors` | the error audit: counts what the server logged after this run's mark and prints the distinct messages, so an error no stage asked for is visible | `cluster` |
| `crossleg` | **12 leg only.** The two reports side by side, as text out of the shared `out/`: how many index names both print, how many of those rows are identical field for field, and which names only one leg has. It needs no server, and it skips itself with a note when the 17 leg has not written its report yet | the 12 leg's `report`, and the 17 leg's |
| `summary` | prints what landed in `out/` and the small result files | nothing |
| `stop` | stops the server with `pg_ctl -m fast -w stop`, so the checkpointer writes a shutdown checkpoint and the next start needs no recovery, then confirms no `postmaster.pid`, no postgres process on the data directory and an empty socket directory. It dies rather than report a stop that did not happen | `cluster` |
| `clean` | `stop`, then deletes the sandbox after checking it is inside `$WIKI_ROOT/.wiki-runtime/tmp/`; because `stop` dies on a failed teardown, `clean` never deletes a live cluster | nothing |

#### What the scripts read from the environment

| Variable | Default | Read by | Meaning |
|---|---|---|---|
| `WIKI_ROOT` | `$PWD` | both | the repository root; everything else is resolved beneath it |
| `PAGE` | `$WIKI_ROOT/wiki/v17/questions/indexing/btree-bloat-with-pgstatindex.md` | both | the page the six `sql` blocks are extracted from |
| `SANDBOX` | `$WIKI_ROOT/.wiki-runtime/tmp/pgsi` | both | build, install, data, socket, SQL and output directories; the only tree either script writes |
| `JOBS` | `4` | both | `make -j` parallelism |
| `ROWS` | `1000000` | both | the `bl` guard-fixture size. The fillfactor fixtures use `ROWS / 5`. The shared suite's own fixture sizes are in its `sql` blocks and are not parameterised |
| `OLD_REV` | `cbbbd16` | both | the revision of this page holding the statement text superseded by the fillfactor rebase |
| `OLD_REV_ALERT` | `0dbabb6` | both | the revision holding the text superseded by the removal of `alert_pct` and `status`; the `compare` stage scores both against the filed text |
| `SRC` / `SRC12` | `$WIKI_ROOT/raw/postgres-17` / `-12` | 17 leg / 12 leg | the pinned checkout, read only |
| `PORT` / `PORT12` | `55417` / `55412` | 17 leg / 12 leg | the cluster's port |
| `EXTRA_CFLAGS` | `-O2 -g -DTRUE=1 -DFALSE=0` | 12 leg | `CFLAGS` for the 12.2 build; ICU 68 dropped the two macros that tree still uses. On a host whose ICU still defines them set it to `-O2 -g`, not to an empty string: `configure` treats an empty `CFLAGS` as set and then builds without optimisation |
| `ICU_CFLAGS`, `ICU_LIBS` | unset | both, through `configure` | not read by the scripts themselves, but inherited by both `configure` runs. `--with-icu` finds ICU through `pkg-config`, so on a host without it both must be exported before the build, as they were for the last run |

Both scripts export `PGPORT`, `PGHOST` and `PGDATABASE` for their own `psql`
calls, so a value in the caller's environment is overridden rather than
honoured. Every helper call also passes
`PGOPTIONS="-c statement_timeout=30min -c lock_timeout=60s"`, per call rather
than exported, because `pg_regress` keeps an inherited `PGOPTIONS` and appends
its own to it
([pg_regress.c#PGOPTIONS](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L785-L798)),
so an exported value would reach `make check`.

The cluster settings each `cluster` stage writes, with the apply scope each one
needs. All of them are written to `postgresql.conf` before the first start, so
every one is in force from the first connection, and none of them is changed
again while the cluster is up:

| Setting | Value | Context | Apply scope |
|---|---|---|---|
| `listen_addresses` | `''` | `PGC_POSTMASTER` | restart ([guc_tables.c#listen_addresses](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4436-L4445)) |
| `port` | `55417` / `55412` | `PGC_POSTMASTER` | restart ([guc_tables.c#port](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2393-L2401)) |
| `unix_socket_directories` | inside the sandbox | `PGC_POSTMASTER` | restart ([guc_tables.c#unix_socket_directories](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4425-L4434)) |
| `shared_buffers` | `512MB` | `PGC_POSTMASTER` | restart ([guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270)) |
| `logging_collector` | `off` | `PGC_POSTMASTER` | restart ([guc_tables.c#logging_collector](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1640-L1648)) |
| `fsync` | `off` | `PGC_SIGHUP` | reload ([guc_tables.c#fsync](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1096-L1107)) |
| `autovacuum` | `off` | `PGC_SIGHUP` | reload ([guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457)) |
| `maintenance_work_mem` | `256MB` | `PGC_USERSET` | session or transaction ([guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2465-L2474)) |
| `max_parallel_maintenance_workers` | `0` | `PGC_USERSET` | session or transaction ([guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417)) |

`autovacuum` is off so that no background worker moves a fixture between the
five phases, not because the fixtures model an unmaintained database. Under the
shared suite's maintenance assumption every churn ends on `VACUUM` and `ANALYZE`
run by the fixture text itself, and rule 3's census recomputes the launcher's
analyze verdict, with the engine's own threshold, for the tables no churn
touched
([autovacuum.c#anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3066-L3076),
[guc_tables.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3367-L3375),
[guc_tables.c#autovacuum_analyze_scale_factor](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3906-L3914)).
`fsync` is off because the cluster is disposable. The fixture and harness blocks
also set `statement_timeout`, `lock_timeout`, `client_min_messages` and
`maintenance_work_mem` per session, all `PGC_USERSET`
([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620),
[guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631),
[guc_tables.c#client_min_messages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4776-L4784),
[guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2465-L2474)).
The `fixtures` stage also writes one database-level custom setting,
`ALTER DATABASE ... SET bl.rows`, so a dollar-quoted fixture body can read the
row count; it applies to new sessions in that database only, stays set until the
database is dropped, and exists only in the disposable cluster.
These contexts are read from the v17 GUC table, which is this page's version;
the 12.2 contexts are not citable here, and that is
[an open question](#open-questions).

#### Prerequisites

- A C toolchain and `make`. Both legs build their own server; no installed
  PostgreSQL is used or needed.
- Development headers for ICU, readline and zlib, for **both** legs. The shared
  suite needs ICU collations in family 1 and in tests 51 and 52, so the 12 leg
  is configured `--with-icu` as well and records a skip for those five fixtures
  if the build refuses them. `configure` looks ICU up through `pkg-config`
  ([configure.ac#ICU](../../../../raw/postgres-17/configure.ac#L842)); on a host
  without it, export `ICU_CFLAGS` and `ICU_LIBS` pointing at the ICU
  installation before running either script.
- The two pinned checkouts, at `raw/postgres-17` and `raw/postgres-12`. Both
  stay read-only: each build is a VPATH build in a directory under
  `.wiki-runtime/tmp/`, which is the form the documentation describes
  ([installation.sgml#VPATH](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L425-L436)).
- `git`, with `OLD_REV` reachable, since `texts` recovers the superseded
  statement with `git show`.
- `sha256sum`, the text tools the stages use — `sort`, `comm`, `uniq`, `cut`,
  `tail`, `grep` and `sed`, the last two only for reading the server log and
  trimming psql's `psql:file:line:` prefix — a `date` whose `+%s%N` prints
  nanoseconds, which the `cost` and `race` timings need, and a Bash new enough
  for arrays, process substitution and `${var:-default}`. GNU `date` is what
  the last run used, and the macOS `date` of an earlier one also qualified; a
  `date` that prints `%N` literally breaks the millisecond arithmetic. Nothing
  else: no Python, no `awk`, no `perl`, no `jq`. Every VERBOSE parse and every
  proof check is Bash case patterns and parameter expansion.
- Free TCP ports 55417 and 55412, or `PORT`/`PORT12` set to free ones. Both
  clusters set `listen_addresses = ''` and listen on a Unix socket inside the
  sandbox, so the port is reserved but never bound on TCP.
- `contrib/pgstattuple`, built and installed from the same tree as the server,
  into the disposable cluster only.
- Disk for two source builds, two clusters and the fixtures: the recorded run
  left a 4,391 MB database on 17.11 and a 4,413 MB database on 12.2 at the point
  the `cost` stage measured them, and `score` briefly doubles the largest index
  it rebuilds.

**Every statement either script sends is disposable.** The fixture stages drop
and rebuild two whole schemas, write `indisvalid = false` and a forged
`reltuples` into the catalog by hand, create and drop two login roles, drop and
recreate an index during the race stage, and rebuild every scored index during
the oracle pass. Never point `SANDBOX`, `PORT`, `PORT12` or `PGHOST` at a
cluster anyone cares about.

### The shared suite's harness

`sql` block 2. Installed once per fixture database by the `suite` stage, and
read by both legs. It carries the five phases' bookkeeping - the plan with its
filed `want_stage` prediction, the build-contract check, the two snapshots, the
baseline event trigger that makes rule 1's cut, the oracle procedure and the
verdict view with the shared four bands - and the bookkeeping the no-defeat
rule asks for: the `maint`, `horizon` and `pageclass` tables, and the
`maint_begin()`, `maint_end()`, `maint_after()` and `horizon_probe()`
functions that bracket every maintenance statement the suite issues.

```sql
-- The shared mandatory suite's harness for this page's statement.  It is
-- installed once in the fixture database of the sandbox cluster and is read by
-- both leg scripts, so the 17 and the 12 run score the same fixtures through
-- the same five phases and the same four verdict bands.  The suite itself -
-- its six families, its phases, its maintenance assumption, its rule that the
-- maintenance must not be defeated, its three porting rules, its REINDEX INDEX
-- oracle and its bands - is defined in the wiki's common concept page
-- "Mandatory B-Tree Bloat Tests" and is not redefined here.
--
-- Beside the plan, the snapshots and the verdict view, this file installs the
-- bookkeeping that rule asks for: the maint, horizon and pageclass tables and
-- the maint_begin(), maint_end() and horizon_probe() functions, which bracket
-- every maintenance statement the suite issues.
--
-- DISPOSABLE.  Every object below is created in a throwaway database of the
-- sandbox cluster and is not meant for a database anyone cares about.
SET /* wiki_pgsi_harness_client_min_messages */ client_min_messages = warning;
SET /* wiki_pgsi_harness_statement_timeout */ statement_timeout = '900s';
SET /* wiki_pgsi_harness_lock_timeout */ lock_timeout = '5s';

DROP EVENT TRIGGER IF EXISTS snap_on_build_trg;
DROP VIEW  IF EXISTS verdicts;
DROP TABLE IF EXISTS snap;
DROP TABLE IF EXISTS res;
DROP TABLE IF EXISTS skipped;
DROP TABLE IF EXISTS plan;
DROP TABLE IF EXISTS decide;
DROP TABLE IF EXISTS report_filed;
DROP TABLE IF EXISTS maint;
DROP TABLE IF EXISTS horizon;
DROP TABLE IF EXISTS pageclass;

-- want_stage is the per-fixture prediction, filed in the fixture text before
-- the run and never rewritten after one.  built_rows is the population
-- measured at the end of the build phase, which is what the build contract is
-- about, because rule 2's drain deliberately changes that population next.
CREATE TABLE plan(num int, leg text DEFAULT '', grp text, req text, idx text,
                  rowsql text, want_rows bigint, built_rows bigint,
                  want_stage text, note text,
                  PRIMARY KEY (num, leg));

-- A fixture the server under test cannot build is recorded here with the
-- server's own message, never silently dropped and never rewritten.
CREATE TABLE skipped(num int, leg text DEFAULT '', idx text, reason text,
                     PRIMARY KEY (num, leg));

-- Phase 2, the baseline: one index's file size and both row counts at one
-- phase.  'built' is written the moment the index is created, 'churned' once
-- the fixture has been disturbed.
CREATE TABLE snap(phase text, idx text, bytes numeric, blocks int,
                  tbl_tuples numeric, idx_tuples numeric,
                  PRIMARY KEY (phase, idx));

-- Phases 4 and 5, one row per fixture: what the statement said about the
-- churned file, what pgstatindex says when the harness calls it itself, and
-- what the rebuild then gave back.
CREATE TABLE res(num int, leg text, req text, idx text,
                 size_before bigint, size_after bigint,
                 blocks_before int, blocks_after int,
                 reported bool, est_pct numeric, rep_est_pct numeric,
                 wasted_ff_pct numeric, notes text,
                 raw_size bigint, raw_internal int, raw_leaf int,
                 raw_empty int, raw_deleted int,
                 raw_density float8, raw_frag float8, fillfactor int,
                 true_rows bigint, want_rows bigint, note text,
                 PRIMARY KEY (num, leg));

-- "Flush" here means publish the calling session's pending table counts now,
-- because the shared suite has two publication points and neither is
-- satisfied by running the phases in order: the churn must reach
-- mod_since_analyze before the maintenance ANALYZE zeroes the counter, or the
-- census reads a freshly analyzed table as still dirty, and it must reach it
-- before the census reads it.
--
-- pg_stat_force_next_flush() does exactly that on the 17 leg.  Where the
-- function does not exist there is no way to force the flush from SQL, so this
-- waits out the publish interval instead: pending counts are published at the
-- end of a transaction that starts at least one publish interval after the
-- last publish, and every caller runs this in autocommit, one statement per
-- transaction.  That is why the 12 leg is the slower of the two.
CREATE OR REPLACE FUNCTION wiki_flush() RETURNS void LANGUAGE plpgsql AS $wf$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
              WHERE n.nspname = 'pg_catalog' AND p.proname = 'pg_stat_force_next_flush')
  THEN EXECUTE 'SELECT pg_stat_force_next_flush()';
  ELSE PERFORM pg_sleep(1.1);
  END IF;
END $wf$;

-- try_ddl returns the server's own message instead of raising, which is what
-- turns a feature the server under test does not have into a recorded skip.
CREATE OR REPLACE FUNCTION try_ddl(cmd text) RETURNS text LANGUAGE plpgsql AS $td$
BEGIN
  EXECUTE cmd;
  RETURN NULL;
EXCEPTION WHEN OTHERS THEN
  RETURN SQLERRM;
END $td$;

CREATE OR REPLACE FUNCTION plan_add(n int, r text, i text, q text DEFAULT NULL,
                                    w bigint DEFAULT NULL, lg text DEFAULT '',
                                    nt text DEFAULT NULL)
RETURNS void LANGUAGE sql AS
$$ INSERT INTO plan(num, leg, req, idx, rowsql, want_rows, note)
   VALUES (n, lg, r, i, q, w, nt) $$;

-- fixture() builds one index and files either a plan row or a skip row, so a
-- gated fixture leaves a record either way.
CREATE OR REPLACE FUNCTION fixture(n int, r text, i text, ddl text,
                                   q text DEFAULT NULL, w bigint DEFAULT NULL,
                                   lg text DEFAULT '') RETURNS text
LANGUAGE plpgsql AS $fx$
DECLARE msg text;
BEGIN
  msg := try_ddl(ddl);
  IF msg IS NULL THEN
    PERFORM plan_add(n, r, i, q, w, lg);
    RETURN 'built ' || i;
  END IF;
  INSERT INTO skipped(num, leg, idx, reason) VALUES (n, lg, i, msg);
  RETURN 'skipped ' || i || ': ' || msg;
END $fx$;

CREATE OR REPLACE FUNCTION skip_add(n int, i text, why text, lg text DEFAULT '')
RETURNS void LANGUAGE sql AS
$$ INSERT INTO skipped(num, leg, idx, reason) VALUES (n, lg, i, why) $$;

CREATE OR REPLACE FUNCTION snap_take(ph text, i text) RETURNS void
LANGUAGE sql AS
$$ INSERT INTO snap(phase, idx, bytes, blocks, tbl_tuples, idx_tuples)
   SELECT ph, ic.relname, pg_relation_size(ic.oid),
          (pg_relation_size(ic.oid) / current_setting('block_size')::int)::int,
          tc.reltuples, ic.reltuples
     FROM pg_class ic
     JOIN pg_index ix ON ix.indexrelid = ic.oid
     JOIN pg_class tc ON tc.oid = ix.indrelid
    WHERE ic.relname = i
   ON CONFLICT (phase, idx) DO UPDATE
      SET bytes = excluded.bytes, blocks = excluded.blocks,
          tbl_tuples = excluded.tbl_tuples, idx_tuples = excluded.idx_tuples $$;

-- ============================ the maintenance must not be defeated ==========
-- The shared suite's rule of that name.  Part 3 of its maintenance assumption
-- forbids skipping the maintenance; this rule forbids sabotaging it, because a
-- statement that ran, returned success and changed nothing leaves the same
-- shape as one that never ran.  Three tables hold the four proofs the rule
-- asks for, per maintenance statement:
--   1. the statement completed, and no skip line in the server log names it
--   2. its own VACUUM (VERBOSE) "dead but not yet removable" count is zero
--   3. no other backend, replication slot or prepared transaction held an
--      xmin when it started
--   4. the page classes it left in the index
-- source records where the statement came from: 'fixture' for a recipe's own
-- churn, 'drain' for rule 2's uniform drain, and 'prebuild' for fixture 85,
-- whose VACUUM precedes its index build and deliberately carries no ANALYZE.
-- None of the three carries a primary key, deliberately: this page's statement
-- reports every B-tree index the function accepts, so each index here would
-- enter the report it is scoring.  maint_begin() therefore deletes before it
-- inserts instead of upserting.
CREATE TABLE maint(tbl text, ord int, source text,
                   started timestamptz, ended timestamptz,
                   removed numeric, remain numeric, dead_not_removable numeric,
                   mods_after numeric, dead_after numeric, timeouts text);

-- The horizon holders, read immediately before every maintenance statement and
-- on both sides of the census.  These are reads beside the statement rather
-- than an interlock around it, which is the limitation the shared definition
-- records against itself.
CREATE TABLE horizon(step text, tbl text, at timestamptz, xmin_holders int,
                     open_xacts int, slots int, slot_xmins int, prepared int,
                     detail text);

-- The page classes of every planned index after the maintenance step.  Deleted
-- and half-dead pages are the visible trace of a horizon that moved; a drained
-- fixture whose index has neither is what a defeated VACUUM leaves behind.
CREATE TABLE pageclass(idx text, leaf_pages numeric,
                       empty_pages numeric, deleted_pages numeric,
                       avg_leaf_density numeric, index_size numeric);

-- Who could be holding a removal horizon back at the moment this is called:
-- any other backend with an open transaction or a published xmin, any
-- replication slot, and any prepared transaction.  VACUUM's OldestXmin folds
-- in exactly those, so a clean reading beside every maintenance statement is
-- the evidence that nothing pinned the horizon while it ran.  The probe's own
-- backend is excluded by pid: it is the session issuing the maintenance, and
-- its INSERT commits before the VACUUM begins.
CREATE OR REPLACE FUNCTION horizon_probe(p_step text, p_tbl text)
RETURNS void LANGUAGE sql AS
$hp$ INSERT INTO horizon(step, tbl, at, xmin_holders, open_xacts, slots,
                         slot_xmins, prepared, detail)
     SELECT p_step, p_tbl, clock_timestamp(),
            (SELECT count(*) FROM pg_stat_activity a
              WHERE a.pid <> pg_backend_pid() AND a.backend_xmin IS NOT NULL),
            (SELECT count(*) FROM pg_stat_activity a
              WHERE a.pid <> pg_backend_pid() AND a.xact_start IS NOT NULL),
            (SELECT count(*) FROM pg_replication_slots),
            (SELECT count(*) FROM pg_replication_slots s
              WHERE s.xmin IS NOT NULL OR s.catalog_xmin IS NOT NULL),
            (SELECT count(*) FROM pg_prepared_xacts),
            (SELECT coalesce(string_agg(a.pid || ':' || coalesce(a.state, '?')
                                        || ':xmin='
                                        || coalesce(a.backend_xmin::text, '-'),
                                        ', ' ORDER BY a.pid), 'none')
               FROM pg_stat_activity a
              WHERE a.pid <> pg_backend_pid()
                AND (a.backend_xmin IS NOT NULL
                     OR a.xact_start IS NOT NULL)) $hp$;

-- One maintenance statement, bracketed.  maint_begin publishes the churn the
-- statement is about to consume, probes the horizon, records the timeout
-- values actually in force rather than the ones the file meant to set, and
-- stamps the start; maint_end stamps the end and reads what the statement left
-- behind.  The VERBOSE counts are filled in afterwards, from the server's own
-- message text, by the leg script's parse_verbose.  transaction_timeout exists
-- on one of the two majors this page runs on, so it is read through the
-- missing_ok form and recorded as n/a where the server has no such setting.
-- A table maintained twice keeps one row: the delete-and-insert here and the
-- greatest() in that UPDATE together mean the row describes the last statement
-- and the worst dead count of all of them.
CREATE OR REPLACE FUNCTION maint_begin(p_tbl text, p_source text DEFAULT 'fixture')
RETURNS void LANGUAGE sql AS
$mb$ SELECT wiki_flush();
     DELETE FROM maint WHERE tbl = p_tbl;
     INSERT INTO maint(tbl, ord, source, started, timeouts)
     SELECT p_tbl, coalesce((SELECT max(ord) FROM maint), 0) + 1, p_source,
            clock_timestamp(),
            'statement_timeout=' || current_setting('statement_timeout') ||
            ' lock_timeout=' || current_setting('lock_timeout') ||
            ' idle_in_transaction_session_timeout='
              || current_setting('idle_in_transaction_session_timeout') ||
            ' transaction_timeout='
              || coalesce(current_setting('transaction_timeout', true), 'n/a');
     SELECT horizon_probe('maint', p_tbl) $mb$;

CREATE OR REPLACE FUNCTION maint_end(p_tbl text) RETURNS void LANGUAGE sql AS
$me$ SELECT pg_stat_clear_snapshot();
     UPDATE maint m
        SET ended = clock_timestamp(),
            mods_after = st.n_mod_since_analyze, dead_after = st.n_dead_tup
       FROM pg_stat_all_tables st
      WHERE st.schemaname = 'public' AND st.relname = m.tbl AND m.tbl = p_tbl;
     SELECT wiki_flush() $me$;

-- What the maintenance left, re-read once the whole churn phase has finished.
-- maint_end() reads the two counters immediately after its own statement, and
-- on a server whose statistics travel to a collector process rather than to
-- shared memory that read can still return the counts from before the VACUUM.
-- This re-read is taken after rule 3's census, when they have settled, and it
-- is the one the run reports.  It moves no proof: proof 2 is the VERBOSE
-- count, which is the statement's own report of what it could not remove.
CREATE OR REPLACE FUNCTION maint_after() RETURNS void LANGUAGE sql AS
$ma$ SELECT pg_stat_clear_snapshot();
     UPDATE maint m
        SET mods_after = st.n_mod_since_analyze, dead_after = st.n_dead_tup
       FROM pg_stat_all_tables st
      WHERE st.schemaname = 'public' AND st.relname = m.tbl $ma$;

-- Rule 1 cuts every recipe at its index build.  The cut is made by an event
-- trigger rather than by moving fixture statements, so a recipe whose churn
-- follows in the same file is cut at exactly the same point as one whose churn
-- is the drain stage.  DO NOTHING keeps the first build's snapshot, so neither
-- a fixture's own REINDEX nor the oracle rebuild can overwrite it.
CREATE OR REPLACE FUNCTION snap_on_build() RETURNS event_trigger
LANGUAGE plpgsql AS $et$
DECLARE c record;
BEGIN
  FOR c IN SELECT objid FROM pg_event_trigger_ddl_commands()
            WHERE command_tag = 'CREATE INDEX' LOOP
    INSERT INTO snap(phase, idx, bytes, blocks, tbl_tuples, idx_tuples)
    SELECT 'built', ic.relname, pg_relation_size(ic.oid),
           (pg_relation_size(ic.oid) / current_setting('block_size')::int)::int,
           tc.reltuples, ic.reltuples
      FROM pg_class ic
      JOIN pg_index ix ON ix.indexrelid = ic.oid
      JOIN pg_class tc ON tc.oid = ix.indrelid
     WHERE ic.oid = c.objid
    ON CONFLICT (phase, idx) DO NOTHING;
  END LOOP;
END $et$;
CREATE EVENT TRIGGER snap_on_build_trg ON ddl_command_end
  WHEN TAG IN ('CREATE INDEX') EXECUTE FUNCTION snap_on_build();

-- The end of the build phase: each fixture's own counting query, evaluated
-- while the fixture is still as built.
CREATE OR REPLACE PROCEDURE assert_built() LANGUAGE plpgsql AS $ab$
DECLARE p record; n bigint;
BEGIN
  FOR p IN SELECT * FROM plan WHERE rowsql IS NOT NULL ORDER BY num, leg LOOP
    EXECUTE p.rowsql INTO n;
    UPDATE plan SET built_rows = n WHERE num = p.num AND leg = p.leg;
  END LOOP;
END $ab$;

-- Phases 4 and 5.  decide holds one pass of this page's statement over the
-- churned database, taken through the harness view, which differs from the
-- filed text in its presentation SELECT only; report_filed holds the rows the
-- filed text itself printed, which is where the notes column comes from.  The
-- raw pgstatindex call below is the harness reading the instrument itself, so
-- the verdict view can recompute the estimate independently of the statement's
-- own CTE chain.  The REINDEX is the only oracle, and it runs after both
-- readings.
CREATE OR REPLACE PROCEDURE score_all() LANGUAGE plpgsql AS $sc$
DECLARE p record; d record; x record; sb bigint; sa bigint; tr bigint; rep record;
BEGIN
  FOR p IN SELECT * FROM plan ORDER BY num, leg LOOP
    tr := NULL;
    IF p.rowsql IS NOT NULL THEN EXECUTE p.rowsql INTO tr; END IF;
    sb := pg_relation_size(p.idx::regclass);
    SELECT * INTO d FROM decide WHERE index_name = p.idx;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'the statement returned no row for %', p.idx;
    END IF;
    SELECT * INTO rep FROM report_filed WHERE index_name = p.idx;
    SELECT * INTO x FROM pgstatindex(p.idx::regclass);
    EXECUTE format('REINDEX INDEX %I', p.idx);
    sa := pg_relation_size(p.idx::regclass);
    INSERT INTO res VALUES (p.num, p.leg, p.req, p.idx, sb, sa,
      (sb / current_setting('block_size')::int)::int,
      (sa / current_setting('block_size')::int)::int,
      rep.index_name IS NOT NULL,
      round(100 * (d.index_size - d.est_rebuilt_bytes) / d.index_size, 1),
      rep.est_pct,
      round(100 * d.wasted_vs_fillfactor / d.index_size, 1),
      rep.notes,
      x.index_size, x.internal_pages, x.leaf_pages, x.empty_pages,
      x.deleted_pages, x.avg_leaf_density, x.leaf_fragmentation,
      d.fillfactor, tr, p.want_rows, p.note);
  END LOOP;
END $sc$;

-- The verdict view.  actual is what the rebuild of the churned file really
-- gave back and is the only oracle; verdict applies the shared suite's four
-- bands to it.  taken_stage is the decision a reader takes from the filed
-- statement's own output: a fixture the statement never prints is a 'leave'
-- whatever its arithmetic says.  taken_nofilter is the same threshold applied
-- to every index whether the report printed it or not, so the two columns
-- coincide exactly when the statement hides nothing, and they are kept side by
-- side as the check on that.  expected_stage recomputes the whole estimate
-- from the harness's own pgstatindex call, so a statement that disagrees with
-- its own instrument is visible.  The 50 % rebuild threshold is this
-- harness's, not the suite's, and not the statement's: the statement carries
-- no threshold at all.
CREATE VIEW verdicts AS
SELECT r.num, r.leg, p.grp, r.idx, r.req,
       s.blocks AS blocks_built, r.blocks_before, r.blocks_after, a.actual,
       r.est_pct, r.wasted_ff_pct, r.raw_density AS density,
       r.raw_empty + r.raw_deleted AS dead_pages, r.raw_leaf AS leaf_pages,
       r.reported, d.taken_stage, d.taken_nofilter, x.expected_stage,
       p.want_stage,
       CASE WHEN d.taken_stage = 'rebuild' AND a.actual < 10  THEN 'CRITICAL FALSE POSITIVE'
            WHEN d.taken_stage = 'rebuild' AND a.actual < 35  THEN 'FALSE POSITIVE'
            WHEN d.taken_stage = 'leave'   AND a.actual >= 50 THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END                                   AS verdict,
       CASE WHEN d.taken_nofilter = 'rebuild' AND a.actual < 10  THEN 'CRITICAL FALSE POSITIVE'
            WHEN d.taken_nofilter = 'rebuild' AND a.actual < 35  THEN 'FALSE POSITIVE'
            WHEN d.taken_nofilter = 'leave'   AND a.actual >= 50 THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END                                   AS verdict_nofilter,
       CASE WHEN d.taken_stage = 'leave' AND a.actual >= 50
            THEN CASE WHEN r.est_pct IS NULL   THEN 'unmeasured'
                      WHEN NOT r.reported      THEN 'not printed'
                      ELSE 'threshold' END END                AS lost_by,
       -- The filed text and the harness view must agree wherever the filed
       -- text prints a row at all; the view differs from it in its
       -- presentation SELECT only.
       (NOT r.reported OR r.est_pct = r.rep_est_pct)           AS view_matches_report,
       (p.want_rows IS NULL OR p.built_rows = p.want_rows)     AS contract_ok,
       -- Rule 2's drain guarantees volume, not distribution: a serial build
       -- makes leaf order key order, so whether the survivors leave every leaf
       -- sparse or a contiguous run of pages that hold nothing follows from
       -- each fixture's key-to-heap correlation.  shape is the post-churn
       -- distribution the fixture reached, and shape_ok is the assertion the
       -- shared suite requires where that distribution is the point: a fixture
       -- predicted reclaimable must show the space physically, either as
       -- leaves below the build target or as whole empty and deleted pages.
       CASE WHEN r.raw_leaf = 0                                THEN 'no leaves'
            WHEN r.raw_empty + r.raw_deleted > 0
             AND g.dens < (g.leaf_cap - g.target_free) / g.leaf_cap THEN 'both'
            WHEN r.raw_empty + r.raw_deleted > 0               THEN 'dead pages'
            WHEN g.dens < (g.leaf_cap - g.target_free) / g.leaf_cap THEN 'sparse leaves'
            ELSE 'dense' END                                   AS shape,
       CASE WHEN p.want_stage <> 'rebuild' THEN NULL
            ELSE r.raw_empty + r.raw_deleted > 0
                 OR (r.raw_leaf > 0
                     AND g.dens < (g.leaf_cap - g.target_free) / g.leaf_cap)
            END                                                AS shape_ok,
       s.tbl_tuples AS tbl_tuples_built, c.tbl_tuples AS tbl_tuples_churned,
       s.idx_tuples AS idx_tuples_built, c.idx_tuples AS idx_tuples_churned,
       p.built_rows, r.true_rows, p.want_rows, r.fillfactor,
       r.raw_frag AS leaf_fragmentation, r.notes, r.note
  FROM res r
  JOIN plan p ON p.num = r.num AND p.leg = r.leg
  LEFT JOIN snap s ON s.phase = 'built'   AND s.idx = r.idx
  LEFT JOIN snap c ON c.phase = 'churned' AND c.idx = r.idx
  CROSS JOIN LATERAL (
        SELECT round(100.0 * (r.size_before - r.size_after)
                     / greatest(r.size_before, 1), 1) AS actual) a
  CROSS JOIN LATERAL (
        SELECT CASE WHEN r.reported AND r.est_pct >= 50
                    THEN 'rebuild' ELSE 'leave' END AS taken_stage,
               CASE WHEN r.est_pct >= 50
                    THEN 'rebuild' ELSE 'leave' END AS taken_nofilter) d
  -- expected_stage: the statement's own model, rebuilt here from the ten
  -- columns pgstatindex returned to the harness.  leaf capacity is
  -- block_size - SizeOfPageHeaderData - MAXALIGN(sizeof(BTPageOpaqueData)),
  -- the target free space is block_size * (100 - fillfactor) / 100, and an
  -- index with no leaf pages reports NaN, which must never reach a comparison.
  CROSS JOIN LATERAL (
        SELECT current_setting('block_size')::numeric AS bs) b
  CROSS JOIN LATERAL (
        SELECT b.bs - 24 - 16                                     AS leaf_cap,
               (b.bs * (100 - r.fillfactor)) / 100                AS target_free,
               CASE WHEN r.raw_leaf > 0 AND r.raw_density <> 'NaN'::float8
                    THEN (r.raw_density / 100)::numeric ELSE 0 END AS dens) g
  CROSS JOIN LATERAL (
        SELECT CASE WHEN r.raw_leaf = 0 THEN 0
                    ELSE ceil(r.raw_leaf * g.dens
                              / ((g.leaf_cap - g.target_free) / g.leaf_cap)) END AS el) e
  CROSS JOIN LATERAL (
        SELECT (1 + e.el + CASE WHEN r.raw_leaf = 0 THEN 0
                                ELSE round(r.raw_internal * e.el / r.raw_leaf) END)
               * b.bs                                              AS eb) f2
  CROSS JOIN LATERAL (
        SELECT round(100 * (r.raw_size - f2.eb) / r.raw_size, 1)    AS exp_pct) h
  CROSS JOIN LATERAL (
        SELECT CASE WHEN h.exp_pct >= 50 THEN 'rebuild' ELSE 'leave' END
                                                                    AS expected_stage) x;
```

### Family 1, the deduplication gate

`sql` block 3. Tests 1 to 17, less the retired test 11 and its 11b transition
control, as 25 fixtures on two 500,000-row tables. Every index is built through
`fixture()`, so a server that has no B-tree support function 4 or no ICU records
a skip with its own message instead of losing the test.

```sql
-- Family 1 of the shared mandatory suite, the deduplication gate: tests 1 to
-- 17, less the retired 11 and 11b, as 25 fixtures on two 500,000-row tables
-- whose key columns each carry 5,000 distinct values.  The family is catalogued
-- fixture by fixture in the common concept page "Mandatory B-Tree Bloat
-- Tests"; this file is the port.  Test 11 (deduplicate_items = off, three
-- indexes) and 11b (the off-to-on switch) are retired: no mandatory fixture
-- sets deduplicate_items at build time or afterward, and neither number is
-- reused.
--
-- Every object is built through fixture(), which files a plan row when the
-- server accepts the build and a skip row carrying the server's own message
-- when it does not.  That is how a 12.2 server without B-tree support
-- function 4 or without ICU records what it could not construct instead of
-- silently dropping it.
--
-- DISPOSABLE.  This file drops and recreates tables, operator families,
-- collations and a public.btequalimage impostor in a throwaway database of the
-- sandbox cluster.  It is not meant for a database anyone cares about.
SET /* wiki_pgsi_gate_client_min_messages */ client_min_messages = warning;
SET /* wiki_pgsi_gate_statement_timeout */ statement_timeout = '900s';
SET /* wiki_pgsi_gate_lock_timeout */ lock_timeout = '5s';
SET /* wiki_pgsi_gate_maintenance_work_mem */ maintenance_work_mem = '256MB';

DROP TABLE IF EXISTS t CASCADE;
DROP TABLE IF EXISTS t2 CASCADE;
-- The family, not the class.  CREATE OPERATOR CLASS with no FAMILY clause
-- creates an operator family of the same name and puts the support-function
-- rows in it; dropping only the class leaves that family and its FUNCTION 4
-- row behind, and the next run then fails on pg_amproc_fam_proc_index.
DROP OPERATOR FAMILY IF EXISTS int4_ei_true  USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS int4_ei_false USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS int4_ei_none  USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS int4_ei_alias USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS int8_ei_true  USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS int8_ei_false USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS text_squat    USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS text_renamed  USING btree CASCADE;
DROP COLLATION IF EXISTS ci;
DROP COLLATION IF EXISTS cdet;

-- The two ICU collations tests 3, 4 and 9 need.  A build configured without
-- ICU refuses both, and the fixtures that need them are skipped below.
SELECT /* wiki_pgsi_gate_collations */ 'cdet: ' ||
       coalesce(try_ddl($c$CREATE COLLATION cdet (provider = icu, locale = 'und')$c$), 'created')
       AS icu_deterministic,
       'ci: ' ||
       coalesce(try_ddl($c$CREATE COLLATION ci (provider = icu, locale = 'und-u-ks-level2', deterministic = false)$c$), 'created')
       AS icu_nondeterministic;

-- The callbacks tests 12 to 16 register as B-tree support function 4.  The two
-- LANGUAGE internal aliases exist only where the engine has the builtins, so
-- both are attempted rather than assumed.
SELECT /* wiki_pgsi_gate_callbacks */
       coalesce(try_ddl($c$CREATE OR REPLACE FUNCTION ei_true(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS 'SELECT true'$c$), 'ok') AS ei_true,
       coalesce(try_ddl($c$CREATE OR REPLACE FUNCTION ei_false(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS 'SELECT false'$c$), 'ok') AS ei_false,
       coalesce(try_ddl($c$CREATE OR REPLACE FUNCTION ei_alias(oid) RETURNS bool LANGUAGE internal IMMUTABLE AS 'btequalimage'$c$), 'ok') AS ei_alias,
       coalesce(try_ddl($c$CREATE OR REPLACE FUNCTION public.btequalimage(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS 'SELECT true'$c$), 'ok') AS impostor,
       coalesce(try_ddl($c$CREATE OR REPLACE FUNCTION ei_renamed(oid) RETURNS bool LANGUAGE internal IMMUTABLE AS 'btvarstrequalimage'$c$), 'ok') AS renamed_builtin;

-- The eight operator classes.  int4_ei_none declares no FUNCTION 4 at all and
-- is therefore constructible on every major; the other seven are not.
SELECT /* wiki_pgsi_gate_opclasses */ name,
       coalesce(try_ddl(ddl), 'created') AS result
  FROM (VALUES
    ('int4_ei_none',  $c$CREATE OPERATOR CLASS int4_ei_none FOR TYPE int4 USING btree AS
       OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
       OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
       FUNCTION 1 btint4cmp(int4,int4)$c$),
    ('int4_ei_true',  $c$CREATE OPERATOR CLASS int4_ei_true FOR TYPE int4 USING btree AS
       OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
       OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
       FUNCTION 1 btint4cmp(int4,int4), FUNCTION 4 ei_true(oid)$c$),
    ('int4_ei_false', $c$CREATE OPERATOR CLASS int4_ei_false FOR TYPE int4 USING btree AS
       OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
       OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
       FUNCTION 1 btint4cmp(int4,int4), FUNCTION 4 ei_false(oid)$c$),
    ('int4_ei_alias', $c$CREATE OPERATOR CLASS int4_ei_alias FOR TYPE int4 USING btree AS
       OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
       OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
       FUNCTION 1 btint4cmp(int4,int4), FUNCTION 4 ei_alias(oid)$c$),
    ('int8_ei_true',  $c$CREATE OPERATOR CLASS int8_ei_true FOR TYPE int8 USING btree AS
       OPERATOR 1 <(int8,int8), OPERATOR 2 <=(int8,int8), OPERATOR 3 =(int8,int8),
       OPERATOR 4 >=(int8,int8), OPERATOR 5 >(int8,int8),
       FUNCTION 1 btint8cmp(int8,int8), FUNCTION 4 ei_true(oid)$c$),
    ('int8_ei_false', $c$CREATE OPERATOR CLASS int8_ei_false FOR TYPE int8 USING btree AS
       OPERATOR 1 <(int8,int8), OPERATOR 2 <=(int8,int8), OPERATOR 3 =(int8,int8),
       OPERATOR 4 >=(int8,int8), OPERATOR 5 >(int8,int8),
       FUNCTION 1 btint8cmp(int8,int8), FUNCTION 4 ei_false(oid)$c$),
    ('text_squat',    $c$CREATE OPERATOR CLASS text_squat FOR TYPE text USING btree AS
       OPERATOR 1 <(text,text), OPERATOR 2 <=(text,text), OPERATOR 3 =(text,text),
       OPERATOR 4 >=(text,text), OPERATOR 5 >(text,text),
       FUNCTION 1 bttextcmp(text,text), FUNCTION 4 public.btequalimage(oid)$c$),
    ('text_renamed',  $c$CREATE OPERATOR CLASS text_renamed FOR TYPE text USING btree AS
       OPERATOR 1 <(text,text), OPERATOR 2 <=(text,text), OPERATOR 3 =(text,text),
       OPERATOR 4 >=(text,text), OPERATOR 5 >(text,text),
       FUNCTION 1 bttextcmp(text,text), FUNCTION 4 ei_renamed(oid)$c$)
  ) o(name, ddl) ORDER BY name;

CREATE TABLE t AS
SELECT i::int4 AS u, (i % 5000)::int4 AS a, (i % 5000)::int8 AS b,
       'key' || lpad((i % 5000)::text, 8, '0') AS s, ((i % 5000)::numeric) AS n,
       (i % 5000)::float4 AS f4, (i % 5000)::float8 AS f8, (i % 7)::int4 AS d
  FROM generate_series(1, 500000) i;
CREATE TABLE t2 AS
SELECT i::int4 AS u, (i % 5000)::int4 AS a, (i % 5000)::int8 AS b,
       'key' || lpad((i % 5000)::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE t, t2; SELECT wiki_flush();

-- The 25 fixtures.  client_min_messages is debug1 here because
-- _bt_allequalimage logs its own verdict at that level, which makes the engine
-- its own oracle for this family; the script keeps the log.
SET client_min_messages = debug1;
SELECT fixture(1,  'int4 key, 100 rows per key',            'i_int4',
               'CREATE INDEX i_int4 ON t (a)',                          'SELECT count(*) FROM t',  500000, 'i_int4');
SELECT fixture(2,  'int8 key, 100 rows per key',            'i_int8',
               'CREATE INDEX i_int8 ON t (b)',                          'SELECT count(*) FROM t',  500000, 'i_int8');
SELECT fixture(3,  'text key, default collation',           'i_text_det',
               'CREATE INDEX i_text_det ON t (s)',                      'SELECT count(*) FROM t',  500000, 'i_text_det');
SELECT fixture(3,  'text key, deterministic ICU collation', 'i_text_icu_det',
               'CREATE INDEX i_text_icu_det ON t (s COLLATE cdet)',     'SELECT count(*) FROM t',  500000, 'i_text_icu_det');
SELECT fixture(4,  'text key, nondeterministic collation',  'i_text_nondet',
               'CREATE INDEX i_text_nondet ON t (s COLLATE ci)',        'SELECT count(*) FROM t',  500000, 'i_text_nondet');
SELECT fixture(5,  'numeric key, no support function 4',    'i_numeric',
               'CREATE INDEX i_numeric ON t (n)',                       'SELECT count(*) FROM t',  500000, 'i_numeric');
SELECT fixture(6,  'float4 key, no support function 4',     'i_float4',
               'CREATE INDEX i_float4 ON t (f4)',                       'SELECT count(*) FROM t',  500000, 'i_float4');
SELECT fixture(6,  'float8 key, no support function 4',     'i_float8',
               'CREATE INDEX i_float8 ON t (f8)',                       'SELECT count(*) FROM t',  500000, 'i_float8');
SELECT fixture(7,  'two equal-image key columns',           'i_multi_ok',
               'CREATE INDEX i_multi_ok ON t (a, b)',                   'SELECT count(*) FROM t',  500000, 'i_multi_ok');
SELECT fixture(7,  'two equal-image key columns, table 2',  'i2_ok',
               'CREATE INDEX i2_ok ON t2 (a, b)',                       'SELECT count(*) FROM t2', 500000, 'i2_ok');
SELECT fixture(8,  'one column not equal-image',            'i_multi_bad',
               'CREATE INDEX i_multi_bad ON t (a, n)',                  'SELECT count(*) FROM t',  500000, 'i_multi_bad');
SELECT fixture(9,  'expression key, numeric result',        'i_expr_num',
               'CREATE INDEX i_expr_num ON t ((a::numeric))',           'SELECT count(*) FROM t',  500000, 'i_expr_num');
SELECT fixture(9,  'expression key, nondeterministic',      'i_expr_lower_ci',
               'CREATE INDEX i_expr_lower_ci ON t ((lower(s)) COLLATE ci)', 'SELECT count(*) FROM t', 500000, 'i_expr_lower_ci');
SELECT fixture(10, 'INCLUDE column refused before lookup',  'i_inc',
               'CREATE INDEX i_inc ON t (a) INCLUDE (d)',               'SELECT count(*) FROM t',  500000, 'i_inc');
-- 11 and 11b were here and are retired.
SELECT fixture(12, 'opclass declaring no FUNCTION 4',       'i_ei_none',
               'CREATE INDEX i_ei_none ON t (a int4_ei_none)',          'SELECT count(*) FROM t',  500000, 'i_ei_none');
SELECT fixture(13, 'custom FUNCTION 4 returning false',     'i_ei_false',
               'CREATE INDEX i_ei_false ON t (a int4_ei_false)',        'SELECT count(*) FROM t',  500000, 'i_ei_false');
SELECT fixture(14, 'custom FUNCTION 4 returning true',      'i_ei_true',
               'CREATE INDEX i_ei_true ON t (a int4_ei_true)',          'SELECT count(*) FROM t',  500000, 'i_ei_true');
SELECT fixture(14, 'internal alias of btequalimage',        'i_ei_alias',
               'CREATE INDEX i_ei_alias ON t (a int4_ei_alias)',        'SELECT count(*) FROM t',  500000, 'i_ei_alias');
SELECT fixture(15, 'true then false callbacks',             'i_mixed_tf',
               'CREATE INDEX i_mixed_tf ON t (a int4_ei_true, b int8_ei_false)', 'SELECT count(*) FROM t', 500000, 'i_mixed_tf');
SELECT fixture(15, 'false then true callbacks',             'i_mixed_ft',
               'CREATE INDEX i_mixed_ft ON t (a int4_ei_false, b int8_ei_true)', 'SELECT count(*) FROM t', 500000, 'i_mixed_ft');
SELECT fixture(15, 'true then false, table 2',              'i2_tf',
               'CREATE INDEX i2_tf ON t2 (a int4_ei_true, b int8_ei_false)', 'SELECT count(*) FROM t2', 500000, 'i2_tf');
SELECT fixture(15, 'false then true, table 2',              'i2_ft',
               'CREATE INDEX i2_ft ON t2 (a int4_ei_false, b int8_ei_true)', 'SELECT count(*) FROM t2', 500000, 'i2_ft');
SELECT fixture(16, 'SQL impostor named btequalimage',       'i_squat',
               'CREATE INDEX i_squat ON t (s text_squat)',              'SELECT count(*) FROM t',  500000, 'i_squat');
SELECT fixture(16, 'renamed internal btvarstrequalimage',   'i_text_det2',
               'CREATE INDEX i_text_det2 ON t (s text_renamed)',        'SELECT count(*) FROM t',  500000, 'i_text_det2');
SELECT fixture(17, 'unique index over equal-image keys',    'i_uniq',
               'CREATE UNIQUE INDEX i_uniq ON t (u)',                   'SELECT count(*) FROM t',  500000, 'i_uniq');
RESET client_min_messages;
SELECT wiki_flush();

-- Test 4's other half, measured rather than derived: text_pattern_ops refuses
-- a nondeterministic collation outright, so the refusal is the fixture.
SELECT /* wiki_pgsi_gate_pattern */
       coalesce(try_ddl('CREATE INDEX i_pattern_nondet ON t (s COLLATE ci text_pattern_ops)'),
                'UNEXPECTED: the build was accepted') AS text_pattern_ops_nondeterministic;

-- Every gate fixture is a shape fixture, so rule 2 drains all of them and
-- every prediction is a rebuild: a 500,000-entry index that keeps one heap
-- block in ten cannot stay dense whatever its keys are.
UPDATE /* wiki_pgsi_gate_families */ plan
   SET grp = 'gate', want_stage = 'rebuild'
 WHERE num <= 17;
SELECT /* wiki_pgsi_gate_counts */
       (SELECT count(*) FROM plan WHERE grp = 'gate')      AS gate_fixtures,
       (SELECT count(*) FROM skipped WHERE num <= 17)      AS gate_skipped,
       (SELECT count(*) FROM snap WHERE phase = 'built')   AS baselines_taken;
SELECT /* wiki_pgsi_gate_skips */ num, idx, reason FROM skipped WHERE num <= 17 ORDER BY num, idx;
```

### Families 2 to 6, tests 18 to 120

`sql` block 4, the build phase of the other five families: 60 partial-index
fixtures, the eight false-positive and six false-negative constructions, the
change A-to-D controls and the drained-queue and zero-count shapes. Rule 1 cuts
each recipe at its index build; the fixtures that carry churn of their own keep
it here, and each of those ends on the maintenance the concept page's
maintenance assumption requires - one `VACUUM (VERBOSE, ANALYZE)` between
`maint_begin()` and `maint_end()`, in a session whose settable timeouts are 0,
as the rule beside it requires. Fixture 85 is the one exception the suite
defines: its bracketed `VACUUM` deliberately carries no `ANALYZE`, because
statistics that predate its widening `UPDATE` are the trap it builds.

The nine fixtures the concept page retired on 2026-09-12 are absent, and their
numbers are not reused: 38, 65, 67, 69, 106, 117 and 121, plus legs 113a and
113c. Test 38 set `deduplicate_items = off`; each of the others withheld a
maintenance command. The block ends at 120.

```sql
-- Families 2 to 6 of the shared mandatory suite, build phase: tests 18-77
-- (partial indexes), 78-85 and 86-91 (the false-positive and false-negative
-- constructions) and controls 92-120, every recipe up to and including the
-- index that is scored.  The families are catalogued fixture by fixture in the
-- common concept page "Mandatory B-Tree Bloat Tests"; this file is the port,
-- and it runs unchanged on both majors this page claims.
--
-- Nine fixtures this port used to build are retired and are therefore absent:
-- numbers 38, 65, 67, 69, 106, 117 and 121, and legs 113a and 113c.  38 set
-- deduplicate_items = off, which no mandatory fixture does any more.  Every
-- other one withheld a maintenance command - four skipped the VACUUM after
-- entries had left the index, four ran the VACUUM and skipped the following
-- ANALYZE - and the concept page does not reuse the numbers.  A run of this
-- port that reports a fixture 38, 65, 67, 69, 106, 117 or 121 is therefore
-- reporting a fixture the suite no longer defines.  64, 66 and 68 keep their
-- numbers, and test 113 keeps its one surviving leg, p113b.
--
-- The maintenance assumption: every table a churn touched gets its maintenance
-- before the decide phase, whatever the launcher's thresholds say, and the
-- cluster's autovacuum = off exempts nothing.  A recipe below that inserts,
-- deletes or updates rows after its index build ends on that step; rule 2's
-- drain ends on it for the shape fixtures that have no churn of their own.
--
-- The maintenance must not be defeated, which is the rule beside it, so the
-- step is one statement rather than two: VACUUM (VERBOSE, ANALYZE), bracketed
-- by maint_begin() and maint_end().  One statement means one VERBOSE report to
-- read the "dead but not yet removable" count out of, and vacuum() vacuums a
-- relation before it analyzes it, so ANALYZE is still the last writer of
-- reltuples.  The brackets publish the churn before the ANALYZE half resets
-- the counter, probe the horizon holders, record the timeouts in force and
-- stamp both ends.  All four settable timeouts are 0 in this session for the
-- same reason an autovacuum worker forces them to 0: a timeout that fires
-- inside the maintenance statement leaves a fixture neither churned nor
-- maintained.  transaction_timeout is not set here, because it does not exist
-- on both majors; on the major that has it the default is already 0, and
-- maint_begin() records whatever was actually in force.
--
-- Rule 1 cuts each recipe at its index build, and the harness event trigger
-- takes the baseline at the cut; rule 2's drain with its maintenance step,
-- rule 3's census and the catalog forgeries are the churn stage.  Fixtures
-- that carry churn of their own keep it here, so the cut for those is the
-- trigger rather than a file boundary.  wiki_flush() precedes every build-phase
-- ANALYZE and is called by both brackets, because pg_stat_force_next_flush()
-- does not exist on every major.  Two fixtures need a feature a server under
-- test may not have and are built through fixture(), which records a skip with
-- the server's own message: p51 and p52 need ICU collations.
--
-- DISPOSABLE.  Everything below creates and drops objects in the public schema
-- of a throwaway database of the sandbox cluster, which the suite stage has
-- just recreated.  It is not meant for a database anyone cares about.
SET /* wiki_pgsi_suite_client_min_messages */ client_min_messages = warning;
SET /* wiki_pgsi_suite_statement_timeout */ statement_timeout = 0;
SET /* wiki_pgsi_suite_lock_timeout */ lock_timeout = 0;
SET /* wiki_pgsi_suite_idle_timeout */ idle_in_transaction_session_timeout = 0;
SET /* wiki_pgsi_suite_maintenance_work_mem */ maintenance_work_mem = '256MB';

-- ============================================================ 18-21 =========
-- Predicate selectivity.  One 1,000,000-row table, distinct bigint keys.
CREATE TABLE pt1 AS
SELECT i::bigint AS k, (i % 100)::int AS sel FROM generate_series(1, 1000000) i;
SELECT wiki_flush(); ANALYZE pt1; SELECT wiki_flush();
CREATE INDEX p18 ON pt1 (k) WHERE sel < 20;
CREATE INDEX p19 ON pt1 (k) WHERE sel < 1;
CREATE INDEX p20 ON pt1 (k) WHERE sel < 10;
CREATE INDEX p21 ON pt1 (k) WHERE sel < 80;
SELECT plan_add(18, 'baseline, subset distribution = table (20%)', 'p18',
                'SELECT count(*) FROM pt1 WHERE sel < 20', 200000);
SELECT plan_add(19, 'very selective, ~1%', 'p19',
                'SELECT count(*) FROM pt1 WHERE sel < 1', 10000);
SELECT plan_add(20, 'moderately selective, ~10%', 'p20',
                'SELECT count(*) FROM pt1 WHERE sel < 10', 100000);
SELECT plan_add(21, 'large subset, ~80%', 'p21',
                'SELECT count(*) FROM pt1 WHERE sel < 80', 800000);

-- ============================================================ 22-33 =========
CREATE TABLE pd22 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd22; SELECT wiki_flush();
CREATE INDEX p22 ON pd22 (k) WHERE hot;
SELECT plan_add(22, 'highly duplicated subset, unique outside', 'p22',
                'SELECT count(*) FROM pd22 WHERE hot', 100000);

CREATE TABLE pd23 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE ((i / 5) % 100)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd23; SELECT wiki_flush();
CREATE INDEX p23 ON pd23 (k) WHERE hot;
SELECT plan_add(23, 'highly unique subset, duplicated outside', 'p23',
                'SELECT count(*) FROM pd23 WHERE hot', 100000);

CREATE TABLE pd24 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50000)::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd24; SELECT wiki_flush();
CREATE INDEX p24 ON pd24 (k) WHERE hot;
SELECT plan_add(24, 'n_distinct radically different in the subset', 'p24',
                'SELECT count(*) FROM pd24 WHERE hot', 100000);

CREATE TABLE pd25 AS SELECT (i % 100 = 0) AS hot,
       CASE WHEN i % 100 = 0 THEN ((i / 100) % 997)::int ELSE (i % 5)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd25; SELECT wiki_flush();
CREATE INDEX p25 ON pd25 (k) WHERE hot;
SELECT plan_add(25, 'MCV distribution differs inside the subset', 'p25',
                'SELECT count(*) FROM pd25 WHERE hot', 5000);

CREATE TABLE pd26 AS SELECT (i % 50 = 0) AS hot,
       CASE WHEN i % 50 = 0 THEN (1000000 + i)::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd26; SELECT wiki_flush();
CREATE INDEX p26 ON pd26 (k) WHERE hot;
SELECT plan_add(26, 'table-wide MCVs absent inside the subset', 'p26',
                'SELECT count(*) FROM pd26 WHERE hot', 10000);

CREATE TABLE pd27 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 AND i % 100 <> 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd27; SELECT wiki_flush();
CREATE INDEX p27 ON pd27 (k) WHERE hot;
SELECT plan_add(27, 'NULL-heavy subset, non-NULL outside', 'p27',
                'SELECT count(*) FROM pd27 WHERE hot', 100000);

CREATE TABLE pd28 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN i::bigint ELSE NULL END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd28; SELECT wiki_flush();
CREATE INDEX p28 ON pd28 (k) WHERE hot;
SELECT plan_add(28, 'NULL-free subset, NULL-heavy table (bigint)', 'p28',
                'SELECT count(*) FROM pd28 WHERE hot', 25000);

CREATE TABLE pd29 AS
SELECT CASE WHEN i % 5 = 0 THEN NULL ELSE lpad(i::text, 20, '0') END AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd29; SELECT wiki_flush();
CREATE INDEX p29 ON pd29 (s) WHERE s IS NULL;
SELECT plan_add(29, 'all-NULL partial index, WHERE s IS NULL', 'p29',
                'SELECT count(*) FROM pd29 WHERE s IS NULL', 100000);

CREATE TABLE pd30 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd30; SELECT wiki_flush();
CREATE INDEX p30 ON pd30 (s) WHERE hot;
SELECT plan_add(30, 'subset values wider than outside (13 against 204 bytes)', 'p30',
                'SELECT count(*) FROM pd30 WHERE hot', 25000);

CREATE TABLE pd31 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN lpad((i % 9)::text, 12, 'n')
            ELSE repeat('W', 190) || lpad(i::text, 10, '0') END AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd31; SELECT wiki_flush();
CREATE INDEX p31 ON pd31 (s) WHERE hot;
SELECT plan_add(31, 'subset values narrower than outside', 'p31',
                'SELECT count(*) FROM pd31 WHERE hot', 25000);

-- 32 is the page's published recipe, verbatim.
CREATE TABLE pw32 AS
SELECT (i % 50 = 0) AS hot,
       CASE WHEN i % 50 = 0 THEN repeat('W', 390) || lpad(i::text, 10, '0')
            ELSE repeat('n', 18) || (i % 9)::text END AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pw32; SELECT wiki_flush();
CREATE INDEX p32 ON pw32 (s) WHERE hot;
SELECT plan_add(32, 'extreme width mismatch (27 against 404 bytes)', 'p32',
                'SELECT count(*) FROM pw32 WHERE hot', 10000);

CREATE TABLE pd33 AS SELECT (i % 5 = 0) AS hot,
       lpad(i::text, 10 + (i % 40), 'x') AS s FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd33; SELECT wiki_flush();
CREATE INDEX p33 ON pd33 (s) WHERE hot;
SELECT plan_add(33, 'variable-width values, same range inside and out', 'p33',
                'SELECT count(*) FROM pd33 WHERE hot', 100000);

-- ============================================================ 34-39 =========
CREATE TABLE pd34 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd34; SELECT wiki_flush();
CREATE INDEX p34 ON pd34 (k) WHERE hot;
SELECT plan_add(34, 'dedup-heavy subset, 1000 rows per key', 'p34',
                'SELECT count(*) FROM pd34 WHERE hot', 100000);

CREATE TABLE pd35 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd35; SELECT wiki_flush();
CREATE INDEX p35 ON pd35 (k) WHERE hot;
SELECT plan_add(35, 'duplicate-heavy table, unique subset', 'p35',
                'SELECT count(*) FROM pd35 WHERE hot', 100000);

CREATE TABLE pd36 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN 42 ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd36; SELECT wiki_flush();
CREATE INDEX p36 ON pd36 (k) WHERE hot;
SELECT plan_add(36, 'one key group, 100,000 TIDs against a 132 cap', 'p36',
                'SELECT count(*) FROM pd36 WHERE hot', 100000);

CREATE TABLE pd37 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd37; SELECT wiki_flush();
CREATE INDEX p37 ON pd37 (k) WHERE hot;
SELECT plan_add(37, 'NULL deduplication, every subset key NULL', 'p37',
                'SELECT count(*) FROM pd37 WHERE hot', 100000);

-- 38 was here and is retired: it built the subset with deduplicate_items = off.

CREATE TABLE pd39 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd39; SELECT wiki_flush();
CREATE UNIQUE INDEX p39 ON pd39 (k) WHERE hot;
SELECT plan_add(39, 'partial UNIQUE index', 'p39',
                'SELECT count(*) FROM pd39 WHERE hot', 100000);

-- ============================================================ 40-47 =========
CREATE TABLE pd40 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 97)::int  END AS b
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd40; SELECT wiki_flush();
CREATE INDEX p40 ON pd40 (a, b) WHERE hot;
SELECT plan_add(40, 'two-column key correlated only in the subset', 'p40',
                'SELECT count(*) FROM pd40 WHERE hot', 100000);

CREATE TABLE pd41 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 97)::int  ELSE (i % 100)::int END AS b
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd41; SELECT wiki_flush();
CREATE INDEX p41 ON pd41 (a, b) WHERE hot;
SELECT plan_add(41, 'two-column key independent only in the subset', 'p41',
                'SELECT count(*) FROM pd41 WHERE hot', 100000);

CREATE TABLE pd42 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50)::int ELSE i::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50)::int ELSE i::int END AS b
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd42; SELECT wiki_flush();
CREATE INDEX p42 ON pd42 (a, b) WHERE hot;
SELECT plan_add(42, 'multi-column duplicate keys in the subset', 'p42',
                'SELECT count(*) FROM pd42 WHERE hot', 100000);

CREATE TABLE pd43 AS SELECT (i % 5 = 0) AS hot, i::int AS a, (i * 2)::int AS b
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd43; SELECT wiki_flush();
CREATE INDEX p43 ON pd43 (a, b) WHERE hot;
SELECT plan_add(43, 'multi-column unique keys in the subset', 'p43',
                'SELECT count(*) FROM pd43 WHERE hot', 100000);

-- 44: the same correlated shape with and without a CREATE STATISTICS object.
--     Two tables, because one ANALYZE would repair both legs at once.
CREATE TABLE pd44a AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd44a; SELECT wiki_flush();
CREATE INDEX p44a ON pd44a (a, b) WHERE hot;
SELECT plan_add(44, 'multicolumn key, no ndistinct object', 'p44a',
                'SELECT count(*) FROM pd44a WHERE hot', 100000);
CREATE TABLE pd44b AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS pd44b_nd (ndistinct) ON a, b FROM pd44b;
SELECT wiki_flush(); ANALYZE pd44b; SELECT wiki_flush();
CREATE INDEX p44b ON pd44b (a, b) WHERE hot;
SELECT plan_add(44, 'multicolumn key, with CREATE STATISTICS (ndistinct)', 'p44b',
                'SELECT count(*) FROM pd44b WHERE hot', 100000, 'ndistinct');

CREATE TABLE pd45 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 97)::int  ELSE (i % 100)::int END AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS pd45_nd (ndistinct) ON a, b FROM pd45;
SELECT wiki_flush(); ANALYZE pd45; SELECT wiki_flush();
CREATE INDEX p45 ON pd45 (a, b) WHERE hot;
SELECT plan_add(45, 'extended statistics wrong for the subset', 'p45',
                'SELECT count(*) FROM pd45 WHERE hot', 100000);

CREATE TABLE pd46 AS SELECT (i % 5 = 0) AS hot, i::int AS k, (i % 7)::int AS pay
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pd46; SELECT wiki_flush();
CREATE INDEX p46 ON pd46 (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(46, 'partial index with INCLUDE columns', 'p46',
                'SELECT count(*) FROM pd46 WHERE hot', 100000);

CREATE TABLE pi47 AS SELECT (i % 20 = 0) AS hot, i::int AS k,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS payload
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pi47; SELECT wiki_flush();
CREATE INDEX p47 ON pi47 (k) INCLUDE (payload) WHERE hot;
SELECT plan_add(47, 'wide INCLUDE values inside the subset', 'p47',
                'SELECT count(*) FROM pi47 WHERE hot', 25000);

-- ============================================================ 48-55 =========
-- Expression legs come in twins: the '' leg has no statistics row for the
-- expression, the 'after analyze' leg has one.
CREATE TABLE pe48 AS SELECT (i % 5 = 0) AS active,
       CASE WHEN i % 5 = 0 THEN 'NAME' || lpad(((i / 5) % 20)::text, 6, '0')
            ELSE 'name' || lpad((i % 100)::text, 6, '0') END AS name
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pe48; SELECT wiki_flush();
CREATE INDEX p48 ON pe48 (lower(name)) WHERE active;
SELECT plan_add(48, 'partial expression index, lower(name) WHERE active', 'p48',
                'SELECT count(*) FROM pe48 WHERE active', 100000);
CREATE TABLE pe48b AS SELECT (i % 5 = 0) AS active,
       CASE WHEN i % 5 = 0 THEN 'NAME' || lpad(((i / 5) % 20)::text, 6, '0')
            ELSE 'name' || lpad((i % 100)::text, 6, '0') END AS name
  FROM generate_series(1, 500000) i;
CREATE INDEX p48b ON pe48b (lower(name)) WHERE active;
SELECT wiki_flush(); ANALYZE pe48b; SELECT wiki_flush();
SELECT plan_add(48, 'the same after one ANALYZE with the index in place', 'p48b',
                'SELECT count(*) FROM pe48b WHERE active', 100000, 'after analyze');

CREATE TABLE pe49 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pe49; SELECT wiki_flush();
CREATE INDEX p49 ON pe49 (upper(s)) WHERE hot;
SELECT plan_add(49, 'expression width mismatch in the subset', 'p49',
                'SELECT count(*) FROM pe49 WHERE hot', 25000);
CREATE TABLE pe49b AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX p49b ON pe49b (upper(s)) WHERE hot;
SELECT wiki_flush(); ANALYZE pe49b; SELECT wiki_flush();
SELECT plan_add(49, 'the same after one ANALYZE with the index in place', 'p49b',
                'SELECT count(*) FROM pe49b WHERE hot', 25000, 'after analyze');

CREATE TABLE pe50 AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pe50; SELECT wiki_flush();
CREATE INDEX p50 ON pe50 (upper(s)) WHERE hot;   -- real width 101, fallback 32
SELECT plan_add(50, 'missing expression statistics, 32-byte fallback', 'p50',
                'SELECT count(*) FROM pe50 WHERE hot', 100000);
CREATE TABLE pe50b AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX p50b ON pe50b (upper(s)) WHERE hot;
SELECT wiki_flush(); ANALYZE pe50b; SELECT wiki_flush();
SELECT plan_add(50, 'the same after one ANALYZE with the index in place', 'p50b',
                'SELECT count(*) FROM pe50b WHERE hot', 100000, 'after analyze');

-- Gated: a server built without ICU has no collation provider for these two,
-- so both collations and both fixtures are attempted and recorded either way.
SELECT 'suite_det: ' ||
       coalesce(try_ddl($c$CREATE COLLATION suite_det (provider = icu, locale = 'und')$c$), 'created'),
       'suite_nondet: ' ||
       coalesce(try_ddl($c$CREATE COLLATION suite_nondet (provider = icu, locale = 'und-u-ks-level2', deterministic = false)$c$), 'created');
CREATE TABLE pc51 AS SELECT (i % 5 = 0) AS hot,
       'key' || lpad(((i / 5) % 100)::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pc51; SELECT wiki_flush();
SELECT fixture(51, 'deterministic ICU collation', 'p51',
               'CREATE INDEX p51 ON pc51 (s COLLATE suite_det) WHERE hot',
               'SELECT count(*) FROM pc51 WHERE hot', 100000);
SELECT fixture(52, 'nondeterministic ICU collation', 'p52',
               'CREATE INDEX p52 ON pc51 (s COLLATE suite_nondet) WHERE hot',
               'SELECT count(*) FROM pc51 WHERE hot', 100000);

CREATE TABLE pf AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pf; SELECT wiki_flush();
CREATE INDEX p53 ON pf (k) WHERE hot;
CREATE INDEX p54 ON pf (k) WITH (fillfactor = 100) WHERE hot;
CREATE INDEX p55 ON pf (k) WITH (fillfactor = 70)  WHERE hot;
SELECT plan_add(53, 'default fillfactor 90', 'p53', 'SELECT count(*) FROM pf WHERE hot', 100000);
SELECT plan_add(54, 'fillfactor = 100',      'p54', 'SELECT count(*) FROM pf WHERE hot', 100000);
SELECT plan_add(55, 'fillfactor = 70',       'p55', 'SELECT count(*) FROM pf WHERE hot', 100000);

-- ============================================================ 56-63 =========
CREATE TABLE ps AS
SELECT (i % 5 = 0) AS flag,
       CASE WHEN i % 5 = 0 THEN 'OPEN' ELSE 'CLOSED' END AS status,
       timestamptz '2020-01-01' + (i * interval '1 minute') AS created,
       CASE WHEN i % 5 = 0 THEN NULL ELSE i::int END AS nk,
       i::int AS k, (i % 1000)::int AS k2
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE ps; SELECT wiki_flush();
CREATE INDEX p56 ON ps (k) WHERE flag;
CREATE INDEX p57 ON ps (k) WHERE status = 'OPEN';
CREATE INDEX p58 ON ps (k) WHERE created >= timestamptz '2020-09-01';
CREATE INDEX p59 ON ps (k) WHERE nk IS NULL;
CREATE INDEX p60 ON ps (k) WHERE nk IS NOT NULL;
CREATE INDEX p61 ON ps (k) WHERE flag AND status = 'OPEN';
CREATE INDEX p62 ON ps (k) WHERE k < 100000;
CREATE INDEX p63 ON ps (k2) WHERE k >= 400000;
SELECT plan_add(56, 'boolean predicate, WHERE flag', 'p56', 'SELECT count(*) FROM ps WHERE flag', 100000);
SELECT plan_add(57, 'equality predicate, status = ''OPEN''', 'p57', 'SELECT count(*) FROM ps WHERE status = ''OPEN''', 100000);
SELECT plan_add(58, 'range predicate, created >= ...', 'p58', 'SELECT count(*) FROM ps WHERE created >= timestamptz ''2020-09-01''', NULL);
SELECT plan_add(59, 'IS NULL predicate on a non-key column', 'p59', 'SELECT count(*) FROM ps WHERE nk IS NULL', 100000);
SELECT plan_add(60, 'IS NOT NULL predicate', 'p60', 'SELECT count(*) FROM ps WHERE nk IS NOT NULL', 400000);
SELECT plan_add(61, 'multi-column predicate', 'p61', 'SELECT count(*) FROM ps WHERE flag AND status = ''OPEN''', 100000);
SELECT plan_add(62, 'predicate correlated with the indexed value', 'p62', 'SELECT count(*) FROM ps WHERE k < 100000', 99999);
SELECT plan_add(63, 'predicate negatively correlated with the value', 'p63', 'SELECT count(*) FROM ps WHERE k >= 400000', 100001);

-- ============================================================ 64-68 =========
-- 65, 67 and 69 were here and are retired: 65 deleted 90 % of the subset and
-- withheld the VACUUM, 67 moved 90 % of it out of the predicate and withheld
-- the VACUUM, and 69 ran the VACUUM and withheld the ANALYZE.  64, 66 and 68
-- are the three that remain, at their original numbers.
-- 64: stale statistics after inserts into the subset.
CREATE TABLE pc64 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pc64; SELECT wiki_flush();
CREATE INDEX p64 ON pc64 (k) WHERE hot;
INSERT INTO pc64 SELECT true, 500000 + i FROM generate_series(1, 200000) i;
SELECT maint_begin('pc64');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) pc64;
SELECT maint_end('pc64');
SELECT plan_add(64, 'stale statistics after inserts into the subset', 'p64',
                'SELECT count(*) FROM pc64 WHERE hot', 300000);

-- 66: rows entering the index (false -> true).
CREATE TABLE pc66 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pc66; SELECT wiki_flush();
CREATE INDEX p66 ON pc66 (k) WHERE hot;
UPDATE pc66 SET hot = true WHERE NOT hot AND k % 5 = 1;
SELECT maint_begin('pc66');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) pc66;
SELECT maint_end('pc66');
SELECT plan_add(66, 'rows entering the index (false -> true)', 'p66',
                'SELECT count(*) FROM pc66 WHERE hot', 200000);

-- 68: heavy predicate churn, then VACUUM + ANALYZE.
CREATE TABLE pc68 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pc68; SELECT wiki_flush();
CREATE INDEX p68 ON pc68 (k) WHERE hot;
UPDATE pc68 SET hot = true  WHERE k % 3 = 0;
UPDATE pc68 SET hot = false WHERE k % 3 = 0;
UPDATE pc68 SET hot = true  WHERE k % 3 = 1;
UPDATE pc68 SET hot = false WHERE k % 3 = 1;
UPDATE pc68 SET hot = (k % 10 = 0);
SELECT maint_begin('pc68');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) pc68;
SELECT maint_end('pc68');
SELECT plan_add(68, 'heavy predicate churn, then VACUUM + ANALYZE', 'p68',
                'SELECT count(*) FROM pc68 WHERE hot', 50000);

-- ============================================================ 70-77 =========
CREATE TABLE pb AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb; SELECT wiki_flush();
CREATE INDEX p70 ON pb (k) WHERE hot;
SELECT plan_add(70, 'freshly created partial index', 'p70',
                'SELECT count(*) FROM pb WHERE hot', 100000);
CREATE INDEX p71 ON pb (k) WHERE hot;
REINDEX INDEX p71;
SELECT plan_add(71, 'freshly REINDEXed partial index', 'p71',
                'SELECT count(*) FROM pb WHERE hot', 100000);

CREATE TABLE pb72 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb72; SELECT wiki_flush();
CREATE INDEX p72 ON pb72 (k) WHERE hot;
DELETE FROM pb72 WHERE hot AND (k / 5) % 4 = 0;
SELECT maint_begin('pb72');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) pb72;
SELECT maint_end('pb72');
SELECT plan_add(72, '25% of the subset deleted', 'p72', 'SELECT count(*) FROM pb72 WHERE hot', 75000);

CREATE TABLE pb73 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb73; SELECT wiki_flush();
CREATE INDEX p73 ON pb73 (k) WHERE hot;
DELETE FROM pb73 WHERE hot AND (k / 5) % 2 = 0;
SELECT maint_begin('pb73');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) pb73;
SELECT maint_end('pb73');
SELECT plan_add(73, '50% of the subset deleted', 'p73', 'SELECT count(*) FROM pb73 WHERE hot', 50000);

CREATE TABLE pb74 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb74; SELECT wiki_flush();
CREATE INDEX p74 ON pb74 (k) WHERE hot;
DELETE FROM pb74 WHERE hot AND (k / 5) % 4 <> 0;
SELECT maint_begin('pb74');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) pb74;
SELECT maint_end('pb74');
SELECT plan_add(74, '75% of the subset deleted', 'p74', 'SELECT count(*) FROM pb74 WHERE hot', 25000);

-- 75 is the corrected recipe: 90% of the subset, not the whole of it.
CREATE TABLE pb75 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb75; SELECT wiki_flush();
CREATE INDEX p75 ON pb75 (k) WHERE hot;
DELETE FROM pb75 WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('pb75');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) pb75;
SELECT maint_end('pb75');
SELECT plan_add(75, '90% of the subset deleted (corrected recipe)', 'p75',
                'SELECT count(*) FROM pb75 WHERE hot', 10000);

CREATE TABLE pb76 AS SELECT (i % 5 = 0) AS hot, i::int AS k, 'x'::text AS pad
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb76; SELECT wiki_flush();
CREATE INDEX p76 ON pb76 (k) WHERE hot;
UPDATE pb76 SET k = k + 1000000 WHERE hot;
SELECT maint_begin('pb76');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) pb76;
SELECT maint_end('pb76');
SELECT plan_add(76, 'bloated through indexed-key UPDATEs', 'p76',
                'SELECT count(*) FROM pb76 WHERE hot', 100000);

CREATE TABLE pb77 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb77; SELECT wiki_flush();
CREATE INDEX p77 ON pb77 (k) WHERE hot;
DELETE FROM pb77 WHERE hot AND k < 475000;          -- contiguous 95%
SELECT maint_begin('pb77');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) pb77;
SELECT maint_end('pb77');
SELECT plan_add(77, 'many empty and deleted B-tree pages', 'p77',
                'SELECT count(*) FROM pb77 WHERE hot', 5001);

-- ============================================================ 78-85 =========
-- Critical-false-positive constructions.  Every index is freshly built.
CREATE TABLE f78t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 290) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f78t; SELECT wiki_flush();
CREATE INDEX f78 ON f78t (s) WHERE hot;
SELECT plan_add(78, 'predicate-conditioned width mismatch', 'f78',
                'SELECT count(*) FROM f78t WHERE hot', 25000);

CREATE TABLE f79t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('t', 300) || lpad(i::text, 4, '0')
            ELSE NULL END AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f79t; SELECT wiki_flush();
CREATE INDEX f79 ON f79t (s) WHERE hot;
SELECT plan_add(79, 'predicate-conditioned NULL mismatch', 'f79',
                'SELECT count(*) FROM f79t WHERE hot', 25000);

CREATE TABLE f80t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f80t; SELECT wiki_flush();
CREATE INDEX f80 ON f80t (k) WHERE hot;
SELECT plan_add(80, 'predicate-conditioned n_distinct mismatch', 'f80',
                'SELECT count(*) FROM f80t WHERE hot', 100000);

CREATE TABLE f81t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 20)::int ELSE 7 END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f81t; SELECT wiki_flush();
CREATE INDEX f81 ON f81t (k) WHERE hot;
SELECT plan_add(81, 'predicate-conditioned MCV mismatch', 'f81',
                'SELECT count(*) FROM f81t WHERE hot', 100000);

CREATE TABLE f82t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 89)::int  END AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS f82_nd (ndistinct) ON a, b FROM f82t;
SELECT wiki_flush(); ANALYZE f82t; SELECT wiki_flush();
CREATE INDEX f82 ON f82t (a, b) WHERE hot;
SELECT plan_add(82, 'predicate-conditioned multi-column correlation', 'f82',
                'SELECT count(*) FROM f82t WHERE hot', 100000);

CREATE TABLE f83t AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f83t; SELECT wiki_flush();
CREATE INDEX f83 ON f83t (md5(s), lower(s)) WHERE hot;    -- no statistics row
SELECT plan_add(83, 'missing index/expression statistics', 'f83',
                'SELECT count(*) FROM f83t WHERE hot', 100000);

CREATE TABLE f84t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f84t; SELECT wiki_flush();
CREATE INDEX f84 ON f84t (k) WHERE hot;
-- The forged count is written by the churn stage, after the rule 3 census: an
-- ANALYZE of f84t rewrites reltuples for the table and for every index on it,
-- so a forgery written here would be silently repaired and the fixture would
-- stop testing anything.
SELECT plan_add(84, 'stale partial-index reltuples', 'f84',
                'SELECT count(*) FROM f84t WHERE hot', 100000);

CREATE TABLE f85t AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f85t; SELECT wiki_flush();
UPDATE f85t SET s = repeat('W', 200) || s WHERE hot;   -- table statistics now stale
SELECT maint_begin('f85t', 'prebuild');
VACUUM /* wiki_pgsi_maint */ (VERBOSE) f85t;   -- no ANALYZE: that is the fixture
SELECT maint_end('f85t');
CREATE INDEX f85 ON f85t (s) WHERE hot;
SELECT plan_add(85, 'stale table statistics', 'f85',
                'SELECT count(*) FROM f85t WHERE hot', 100000);

-- ============================================================ 86-91 =========
-- Critical-false-negative constructions: genuinely bloated, VACUUMed, ANALYZEd.
CREATE TABLE f86t AS SELECT (i % 5 = 0) AS hot, ((i / 5) % 100)::int AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f86t; SELECT wiki_flush();
CREATE INDEX f86 ON f86t (k) WHERE hot;
DELETE FROM f86t WHERE hot AND k >= 25;
SELECT maint_begin('f86t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) f86t;
SELECT maint_end('f86t');
SELECT plan_add(86, 'duplicate concentration inside the subset', 'f86',
                'SELECT count(*) FROM f86t WHERE hot', 25000);

CREATE TABLE f87t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f87t; SELECT wiki_flush();
CREATE INDEX f87 ON f87t (k) WHERE hot;
DELETE FROM f87t WHERE hot AND k IS NOT NULL;
SELECT maint_begin('f87t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) f87t;
SELECT maint_end('f87t');
SELECT plan_add(87, 'NULL concentration inside the subset', 'f87',
                'SELECT count(*) FROM f87t WHERE hot', 25000);

CREATE TABLE f88t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN lpad((i % 9)::text, 9, '0')
            ELSE repeat('W', 390) || lpad(i::text, 10, '0') END AS s
  FROM generate_series(1, 200000) i;
SELECT wiki_flush(); ANALYZE f88t; SELECT wiki_flush();
CREATE INDEX f88 ON f88t (s) WHERE hot;
DELETE FROM f88t WHERE hot AND s > lpad('4', 9, '0');
SELECT maint_begin('f88t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) f88t;
SELECT maint_end('f88t');
SELECT plan_add(88, 'subset narrower than table statistics', 'f88', NULL, NULL);

CREATE TABLE f89t AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f89t; SELECT wiki_flush();
CREATE INDEX f89 ON f89t (a, b) WHERE hot;
DELETE FROM f89t WHERE hot AND a >= 25;
SELECT maint_begin('f89t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) f89t;
SELECT maint_end('f89t');
SELECT plan_add(89, 'conditional multi-column correlation', 'f89',
                'SELECT count(*) FROM f89t WHERE hot', 25000);

CREATE TABLE f90t AS SELECT (i % 5 = 0) AS hot, ((i / 5) % 1000)::int AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f90t; SELECT wiki_flush();
CREATE INDEX f90 ON f90t (k) WHERE hot;
DELETE FROM f90t WHERE hot AND k >= 250;
SELECT maint_begin('f90t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) f90t;
SELECT maint_end('f90t');
SELECT plan_add(90, 'real deduplication stronger than predicted', 'f90',
                'SELECT count(*) FROM f90t WHERE hot', 25000);

CREATE TABLE f91t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN lpad((i % 9)::text, 9, '0')
            ELSE repeat('W', 390) || lpad(i::text, 10, '0') END AS s,
       i::int AS ord
  FROM generate_series(1, 200000) i;
SELECT wiki_flush(); ANALYZE f91t; SELECT wiki_flush();
CREATE INDEX f91 ON f91t (s) WHERE hot;
DELETE FROM f91t WHERE hot AND ord < 190000;         -- contiguous 95%
SELECT maint_begin('f91t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) f91t;
SELECT maint_end('f91t');
SELECT plan_add(91, 'many deleted pages plus an over-predicting model', 'f91',
                'SELECT count(*) FROM f91t WHERE hot', 2001);

-- ============================================================ 92-95 =========
-- Change B threshold calibration: a genuinely reclaimable partial index,
-- disturbed by a known number of row changes, with and without reloptions.
-- Under the maintenance assumption each counted UPDATE is followed by the
-- maintenance VACUUM and ANALYZE, so all four tables reach rule 3's census
-- freshly analyzed and the reloption pair no longer changes its decision.
-- The four keep their numbers and their reclaimable index.
CREATE TABLE b92t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE b92t; SELECT wiki_flush();
CREATE INDEX b92 ON b92t (k) WHERE hot;
DELETE FROM b92t WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('b92t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) b92t;
SELECT maint_end('b92t');
UPDATE b92t SET k = k WHERE k % 500 = 0;              -- 1,000 rows changed
SELECT maint_begin('b92t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) b92t;
SELECT maint_end('b92t');
SELECT plan_add(92, '1,000 rows updated under the GUC threshold', 'b92',
                'SELECT count(*) FROM b92t WHERE hot', 10000);

CREATE TABLE b93t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE b93t; SELECT wiki_flush();
CREATE INDEX b93 ON b93t (k) WHERE hot;
DELETE FROM b93t WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('b93t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) b93t;
SELECT maint_end('b93t');
UPDATE b93t SET k = k WHERE k % 2 = 0;                -- above the trigger
SELECT maint_begin('b93t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) b93t;
SELECT maint_end('b93t');
SELECT plan_add(93, 'rows updated above the GUC threshold', 'b93',
                'SELECT count(*) FROM b93t WHERE hot', 10000);

CREATE TABLE b94t (hot bool, k int)
  WITH (autovacuum_analyze_threshold = 100, autovacuum_analyze_scale_factor = 0);
INSERT INTO b94t SELECT (i % 5 = 0), i FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE b94t; SELECT wiki_flush();
CREATE INDEX b94 ON b94t (k) WHERE hot;
DELETE FROM b94t WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('b94t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) b94t;
SELECT maint_end('b94t');
UPDATE b94t SET k = k WHERE k % 500 = 0;              -- 1,000 > the reloption
SELECT maint_begin('b94t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) b94t;
SELECT maint_end('b94t');
SELECT plan_add(94, '1,000 rows updated, table reloption threshold 100', 'b94',
                'SELECT count(*) FROM b94t WHERE hot', 10000);

CREATE TABLE b95t (hot bool, k int)
  WITH (autovacuum_analyze_threshold = 200000, autovacuum_analyze_scale_factor = 1);
INSERT INTO b95t SELECT (i % 5 = 0), i FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE b95t; SELECT wiki_flush();
CREATE INDEX b95 ON b95t (k) WHERE hot;
DELETE FROM b95t WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('b95t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) b95t;
SELECT maint_end('b95t');
UPDATE b95t SET k = k WHERE k % 2 = 0;                -- below the reloption
SELECT maint_begin('b95t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) b95t;
SELECT maint_end('b95t');
SELECT plan_add(95, 'many rows updated, table reloption threshold 200,000', 'b95',
                'SELECT count(*) FROM b95t WHERE hot', 10000);

-- ============================================================ 96-99 =========
-- Non-partial controls: the partial-only exclusions must not reach them.
CREATE TABLE np AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE np; SELECT wiki_flush();
CREATE INDEX np96 ON np (k);
CREATE INDEX np97 ON np (upper(s));                   -- no statistics row
SELECT plan_add(96, 'plain index, fresh statistics', 'np96', 'SELECT count(*) FROM np', 500000);
SELECT plan_add(97, 'expression index, no statistics row', 'np97', 'SELECT count(*) FROM np', 500000);

CREATE TABLE np98t AS SELECT i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE np98t; SELECT wiki_flush();
CREATE INDEX np98 ON np98t (k);
INSERT INTO np98t SELECT 500000 + i FROM generate_series(1, 300000) i;
SELECT maint_begin('np98t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) np98t;
SELECT maint_end('np98t');
SELECT plan_add(98, 'plain index, stale row counts after 300,000 inserts', 'np98',
                'SELECT count(*) FROM np98t', 800000);

-- 99: the corrected recipe.  An index and a table cannot share a name, so the
-- table is np99t and the index np99.
CREATE TABLE np99t AS SELECT (i % 1000)::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE np99t; SELECT wiki_flush();
CREATE INDEX np99 ON np99t (k);
DELETE FROM np99t WHERE k >= 60;
SELECT maint_begin('np99t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) np99t;
SELECT maint_end('np99t');
SELECT plan_add(99, 'duplicate-heavy index, genuinely reclaimable', 'np99',
                'SELECT count(*) FROM np99t', 30000);

-- =========================================================== 100-105 ========
-- The variable-width INCLUDE family.
CREATE TABLE i100t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE i100t; SELECT wiki_flush();
CREATE INDEX i100 ON i100t (k) INCLUDE (pay) WHERE hot;
DELETE FROM i100t WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('i100t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) i100t;
SELECT maint_end('i100t');
SELECT plan_add(100, 'partial + INCLUDE (text), 90% of the subset deleted', 'i100',
                'SELECT count(*) FROM i100t WHERE hot', 10000);

CREATE TABLE i101t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE i101t; SELECT wiki_flush();
CREATE INDEX i101 ON i101t (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(101, 'partial + INCLUDE (text), same width inside and outside', 'i101',
                'SELECT count(*) FROM i101t WHERE hot', 100000);

CREATE TABLE i102t AS SELECT i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE i102t; SELECT wiki_flush();
CREATE INDEX i102 ON i102t (k) INCLUDE (pay);
SELECT plan_add(102, 'non-partial + wide INCLUDE (text), freshly built', 'i102',
                'SELECT count(*) FROM i102t', 500000);

CREATE TABLE i103t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad(i::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE i103t; SELECT wiki_flush();
CREATE INDEX i103 ON i103t (s) WHERE hot;
SELECT plan_add(103, 'partial + wide key column, unique values, no caveat', 'i103',
                'SELECT count(*) FROM i103t WHERE hot', 25000);

CREATE TABLE i104t AS SELECT (i % 20 = 0) AS hot, i::int AS k,
       CASE WHEN i % 20 = 0 THEN lpad((i % 9)::text, 12, 'n')
            ELSE repeat('W', 190) || lpad(i::text, 10, '0') END AS pay
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE i104t; SELECT wiki_flush();
CREATE INDEX i104 ON i104t (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(104, 'partial + INCLUDE (text) narrower inside the subset', 'i104',
                'SELECT count(*) FROM i104t WHERE hot', 25000);

CREATE TABLE i105t AS SELECT (i % 20 = 0) AS hot, i::int AS k, (i % 7)::int AS n,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS pay
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE i105t; SELECT wiki_flush();
CREATE INDEX i105 ON i105t (k) INCLUDE (n, pay) WHERE hot;
SELECT plan_add(105, 'partial + INCLUDE (int, text), mixed non-key widths', 'i105',
                'SELECT count(*) FROM i105t WHERE hot', 25000);

-- =========================================================== 107-112 ========
-- The expression-statistics family.  106 was its first member and is retired:
-- it deleted 90 % of the table, ran the VACUUM and withheld the ANALYZE, which
-- is the shape the suite no longer builds.  107 is the same recipe with the
-- ANALYZE in place, and it stays.
CREATE TABLE x107t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE x107t; SELECT wiki_flush();
CREATE INDEX x107 ON x107t (upper(s));
DELETE FROM x107t WHERE k % 10 <> 0;
SELECT maint_begin('x107t');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) x107t;
SELECT maint_end('x107t');
SELECT plan_add(107, 'the same, with one ANALYZE after the build', 'x107',
                'SELECT count(*) FROM x107t', 50000);

CREATE TABLE x108t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX x108 ON x108t (upper(s));                -- table never analysed
SELECT wiki_flush();
SELECT plan_add(108, 'expression index on a never-analysed table', 'x108',
                'SELECT count(*) FROM x108t', 500000);

CREATE TABLE x109t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ALTER TABLE x109t ALTER COLUMN s SET STATISTICS 0;
SELECT wiki_flush(); ANALYZE x109t; SELECT wiki_flush();
CREATE INDEX x109 ON x109t (s);
SELECT plan_add(109, 'plain index, key column with SET STATISTICS 0', 'x109',
                'SELECT count(*) FROM x109t', 500000);

CREATE TABLE x110t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE x110t; SELECT wiki_flush();
CREATE INDEX x110 ON x110t (k, upper(s));             -- mixed key, no stats row
SELECT plan_add(110, 'mixed key (k, upper(s)), no statistics row', 'x110',
                'SELECT count(*) FROM x110t', 500000);

CREATE TABLE x111t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE x111t; SELECT wiki_flush();
CREATE INDEX x111 ON x111t (left(s, 3));              -- narrow expression
SELECT plan_add(111, 'narrow expression left(s, 3), no statistics row', 'x111',
                'SELECT count(*) FROM x111t', 500000);

CREATE TABLE x112t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE x112t; SELECT wiki_flush();
CREATE INDEX x112 ON x112t (upper(s)) WHERE hot;      -- partial expression
SELECT plan_add(112, 'partial expression index, no statistics row', 'x112',
                'SELECT count(*) FROM x112t WHERE hot', 100000);

-- =========================================================== 113-120 ========
-- The drained queue.  Test 113 had three legs and keeps one: 113a ran nothing
-- after the drain and 113c ran the ANALYZE only, so both withheld the VACUUM
-- and both are retired.  113b, the leg that runs VACUUM and ANALYZE, is the
-- whole of test 113 now, and it keeps the leg label 'b' so the number-and-leg
-- identity a reader sees is the one the concept page defines.
CREATE TABLE q113b AS SELECT i::int AS id, 'pending'::text AS state
  FROM generate_series(1, 1000000) i;
SELECT wiki_flush(); ANALYZE q113b; SELECT wiki_flush();
CREATE INDEX p113b ON q113b (id) WHERE state = 'pending';
UPDATE q113b SET state = 'done';
SELECT maint_begin('q113b');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) q113b;
SELECT maint_end('q113b');
SELECT plan_add(113, 'drained queue, VACUUM + ANALYZE', 'p113b',
                'SELECT count(*) FROM q113b WHERE state = ''pending''', 0, 'b');

-- 114: a genuine, fully repaired detection on the same queue shape.
CREATE TABLE q114 AS SELECT i::int AS id, 'pending'::text AS state
  FROM generate_series(1, 1000000) i;
SELECT wiki_flush(); ANALYZE q114; SELECT wiki_flush();
CREATE INDEX p114 ON q114 (id) WHERE state = 'pending';
UPDATE q114 SET state = 'done' WHERE id % 100 <> 0;
SELECT maint_begin('q114');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) q114;
SELECT maint_end('q114');
SELECT plan_add(114, 'queue drained to 1%, VACUUM + ANALYZE', 'p114',
                'SELECT count(*) FROM q114 WHERE state = ''pending''', 10000);

-- 115: index built on an analysed empty table, then loaded.
CREATE TABLE q115(id int, state text);
SELECT wiki_flush(); ANALYZE q115; SELECT wiki_flush();
CREATE INDEX p115 ON q115 (id) WHERE state = 'pending';
INSERT INTO q115 SELECT i, 'pending' FROM generate_series(1, 1000000) i;
SELECT maint_begin('q115');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) q115;
SELECT maint_end('q115');
SELECT plan_add(115, 'index built on an analysed empty table, then loaded', 'p115',
                'SELECT count(*) FROM q115 WHERE state = ''pending''', 1000000);

-- 116: a subset that is genuinely empty and was measured empty.
CREATE TABLE q116 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p116 ON q116 (id) WHERE state = 'pending';
SELECT wiki_flush(); ANALYZE q116; SELECT wiki_flush();
SELECT plan_add(116, 'subset empty from the start and measured empty', 'p116',
                'SELECT count(*) FROM q116 WHERE state = ''pending''', 0);

-- 117 was here and is retired: it drained the queue, ran the VACUUM and
-- withheld the ANALYZE.  113b is the drained-queue shape the suite keeps.
-- 118: the subset was empty at the last ANALYZE, then 50,000 rows arrived.
-- The maintenance step after the arrivals re-estimates the index's own count,
-- so 118 no longer reaches the decide phase with the empty-subset estimate;
-- the concept page files that as the price of the assumption.
CREATE TABLE q118 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p118 ON q118 (id) WHERE state = 'pending';
SELECT wiki_flush(); ANALYZE q118; SELECT wiki_flush();
INSERT INTO q118 SELECT 1000000 + i, 'pending' FROM generate_series(1, 50000) i;
SELECT maint_begin('q118');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) q118;
SELECT maint_end('q118');
SELECT plan_add(118, 'subset measured empty, then 50,000 rows arrive', 'p118',
                'SELECT count(*) FROM q118 WHERE state = ''pending''', 50000);

-- 119: fixture 118 after one more ANALYZE.  Under the maintenance assumption
-- the two differ only by a second sample.
CREATE TABLE q119 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p119 ON q119 (id) WHERE state = 'pending';
SELECT wiki_flush(); ANALYZE q119; SELECT wiki_flush();
INSERT INTO q119 SELECT 1000000 + i, 'pending' FROM generate_series(1, 50000) i;
SELECT maint_begin('q119');
VACUUM /* wiki_pgsi_maint */ (VERBOSE, ANALYZE) q119;
SELECT maint_end('q119');
ANALYZE q119; SELECT wiki_flush();                    -- the one more ANALYZE
SELECT plan_add(119, 'fixture 118 after one more ANALYZE', 'p119',
                'SELECT count(*) FROM q119 WHERE state = ''pending''', 50000);

-- 120: the ANALYZE sample missed the subset entirely.
CREATE TABLE q120 AS SELECT i::int AS id,
       CASE WHEN i <= 2000 THEN 'pending' ELSE 'done' END::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p120 ON q120 (id) WHERE state = 'pending';
SET default_statistics_target = 1;
SELECT wiki_flush(); ANALYZE q120; SELECT wiki_flush();
RESET default_statistics_target;
SELECT plan_add(120, 'a 300-row sample missed a 2,000-row subset', 'p120',
                'SELECT count(*) FROM q120 WHERE state = ''pending''', 2000);

-- 121 was here and is retired, all three of its legs: nz_k emptied, vacuumed
-- and reloaded without an ANALYZE, nzb_k did the same with a REINDEX while the
-- table was empty, and i_trunc was a TRUNCATE and reload without an ANALYZE.
-- All three ended on a withheld ANALYZE, so the suite stops at 120 and 121 is
-- not reused.  The stale-count shapes that survive are catalog states rather
-- than withheld commands: 64, 83, 85, 97, 98, 108, 110 to 112 and 118, plus
-- f84's forgery, which the census stage writes after it runs.

-- The shared suite's families, and the per-fixture prediction of what a
-- physical density reading will decide once the churn has run.  Both are filed
-- here, in this text, before the run, and want_stage is never rewritten after
-- one.  The prediction is for taken_nofilter, the decision the method reaches
-- when it is shown every index; the verdict view reports it beside
-- taken_stage, the decision the filed text's own output supports, and the two
-- coincide when the statement hides no candidate from the reader.
UPDATE /* wiki_pgsi_suite_families */ plan SET grp =
       CASE WHEN num BETWEEN 18 AND 77  THEN 'partial'
            WHEN num BETWEEN 78 AND 85  THEN 'falsepos'
            WHEN num BETWEEN 86 AND 91  THEN 'falseneg'
            WHEN num BETWEEN 92 AND 112 THEN 'control'
            ELSE 'zero' END
 WHERE num >= 18;

UPDATE /* wiki_pgsi_suite_predictions */ plan SET want_stage =
       CASE
         -- Family 3, and every other fixture whose point is that a fresh index
         -- must not be touched.  Rule 2 exempts all of them from the drain, so
         -- their leaves are still packed to the build target and pgstatindex
         -- has nothing to report.  A physical reading is expected to pass all
         -- fourteen, including the two - f84's forged index count and f85's
         -- stale table statistics - that only a catalog reader can fall for.
         WHEN num BETWEEN 78 AND 85                      THEN 'leave'
         WHEN num IN (70, 71, 96, 97, 101, 102, 103, 104, 105,
                      108, 109, 110, 111, 112, 116, 120)  THEN 'leave'
         -- Family 4: reclaimable by construction, vacuumed and analyzed, so
         -- the free space is really in the file.
         WHEN num BETWEEN 86 AND 91                      THEN 'rebuild'
         -- There is no prediction for the unvacuumed blind spot any more.  The
         -- four fixtures that carried it - 65, 67 and legs 113a and 113c - were
         -- the one shape a density reading cannot see: entries gone from the
         -- table but still physically present in the index, so every leaf stays
         -- dense while a rebuild would empty the file.  All four are retired,
         -- so nothing in this run predicts or measures that shape.
         -- Inserts, or rows entering the predicate, in key order or
         -- interleaved: the file grew to hold what it holds, and a rebuild
         -- returns a fifth of it at most.  The maintenance VACUUM these
         -- fixtures now get removes no index entry, because no entry left the
         -- index, so the prediction filed before the assumption still stands.
         -- 121's reload legs were predicted here too and are retired with it.
         WHEN num IN (64, 66, 98, 115, 118, 119)         THEN 'leave'
         -- A quarter of the subset deleted leaves the file about 67 % dense
         -- against an 89.95 % target, which is under the harness threshold.
         WHEN num = 72                                   THEN 'leave'
         -- Everything else was drained by rule 2 or by its own recipe and then
         -- vacuumed, so the free space is visible to a density reading.
         ELSE 'rebuild' END
 WHERE num >= 18;

CALL /* wiki_pgsi_suite_assert_built */ assert_built();
SELECT count(*) AS planned_fixtures FROM plan;
SELECT count(*) AS fixtures_skipped FROM skipped;
SELECT count(*) AS baselines_taken FROM snap WHERE phase = 'built';
SELECT count(*) AS build_contract_failures FROM plan
 WHERE want_rows IS NOT NULL AND built_rows <> want_rows;
SELECT num, leg, idx, reason FROM skipped ORDER BY num, leg;
```

### Rule 2, the uniform drain

`sql` block 5, phase 3's first half: delete every heap tuple outside one heap
block in ten, then one bracketed `VACUUM (VERBOSE, ANALYZE)`, over the 36 suite
tables and the two family 1 tables that have no churn of their own. The
fixtures whose point is that a fresh index must not be touched appear nowhere in
the list.

```sql
-- Phase 3 of the shared mandatory suite, in the order that suite prescribes:
-- rule 2's uniform drain over every shape fixture that has no churn of its
-- own, ending on the maintenance step the concept page's maintenance
-- assumption requires; then rule 3's census, which recomputes the launcher's
-- analyze verdict for the tables no churn touched; then the catalog
-- forgeries; then the churned snapshot.  The fixtures whose point is that a
-- fresh index must not be touched are exempt and appear nowhere in the drain
-- list.
--
-- DISPOSABLE.  Every statement below rewrites fixtures, and one of them writes
-- a forged count into pg_class, in a throwaway database of the sandbox
-- cluster.  It is not meant for a database anyone cares about.
-- This session issues maintenance statements, so all four settable timeouts
-- are 0 in it, as an autovacuum worker forces them to be; transaction_timeout
-- is left to its default, because it does not exist on both majors and that
-- default is already 0 where it does.  maint_begin() records what was in
-- force.
SET /* wiki_pgsi_churn_client_min_messages */ client_min_messages = warning;
SET /* wiki_pgsi_churn_statement_timeout */ statement_timeout = 0;
SET /* wiki_pgsi_churn_lock_timeout */ lock_timeout = 0;
SET /* wiki_pgsi_churn_idle_timeout */ idle_in_transaction_session_timeout = 0;

-- Rule 2, the uniform drain: delete every heap tuple outside one heap block in
-- ten, then the maintenance step, one VACUUM (VERBOSE, ANALYZE) bracketed by
-- maint_begin() and maint_end() as the no-defeat rule asks.
-- The block number comes out of the tuple's own
-- ctid, so the survivors are spread across the heap rather than clustered at
-- one end, and the VACUUM's btvacuumscan visits every index block and removes
-- every entry whose TID was drained.  What that guarantees is volume, not
-- distribution: a serial build makes leaf order key order, so whether the
-- survivors leave every leaf sparse or a contiguous run of pages holding
-- nothing follows from each fixture's key-to-heap correlation, which the
-- recipe sets and this rule does not.  The harness records the shape each
-- fixture reached and asserts it where a prediction depends on it.  The
-- statements are generated and executed one at a time because VACUUM cannot
-- run inside a transaction block.  The two gate tables are shape fixtures too,
-- so both are drained here with the rest.
SELECT /* wiki_pgsi_drain_generator */ format(st.tmpl, tb.name)
  FROM (VALUES (1, 'pt1'), (2, 'pd22'), (3, 'pd23'), (4, 'pd24'), (5, 'pd25'),
               (6, 'pd26'), (7, 'pd27'), (8, 'pd28'), (9, 'pd29'), (10, 'pd30'),
               (11, 'pd31'), (12, 'pw32'), (13, 'pd33'), (14, 'pd34'),
               (15, 'pd35'), (16, 'pd36'), (17, 'pd37'),
               (18, 'pd39'), (19, 'pd40'), (20, 'pd41'), (21, 'pd42'),
               (22, 'pd43'), (23, 'pd44a'), (24, 'pd44b'), (25, 'pd45'),
               (26, 'pd46'), (27, 'pi47'), (28, 'pe48'), (29, 'pe48b'),
               (30, 'pe49'), (31, 'pe49b'), (32, 'pe50'), (33, 'pe50b'),
               (34, 'pc51'), (35, 'pf'), (36, 'ps'),
               (37, 't'), (38, 't2')) tb(n, name)
-- Steps 2 and 4 are the brackets, and they carry the publication points the
-- maintenance step inherits from rule 3: maint_begin() puts the DELETE's row
-- counts into mod_since_analyze *before* the ANALYZE half of step 3 zeroes
-- that counter, and maint_end() publishes the state the census is about to
-- read.  Both call wiki_flush(), which forces the publish where SQL can and
-- waits out the publish interval where it cannot, so both orderings hold on
-- every major rather than only on the one whose catalog has the function.
-- They also probe the horizon holders and stamp the statement, which is what
-- lets the run prove the maintenance was not defeated.
 CROSS JOIN (VALUES
        (1, 'DELETE /* wiki_pgsi_drain */ FROM %1$I WHERE ((ctid::text::point)[0])::int %% 10 <> 0'),
        (2, 'SELECT /* wiki_pgsi_drain_begin */ maint_begin(%1$L, ''drain'')'),
        (3, 'VACUUM /* wiki_pgsi_drain_maint */ (VERBOSE, ANALYZE) %1$I'),
        (4, 'SELECT /* wiki_pgsi_drain_end */ maint_end(%1$L)')) st(k, tmpl)
 ORDER BY tb.n, st.k
\gexec

SELECT /* wiki_pgsi_drain_count */ count(*) AS tables_drained
  FROM (VALUES ('pt1'), ('pd22'), ('pd23'), ('pd24'), ('pd25'), ('pd26'),
               ('pd27'), ('pd28'), ('pd29'), ('pd30'), ('pd31'), ('pw32'),
               ('pd33'), ('pd34'), ('pd35'), ('pd36'), ('pd37'),
               ('pd39'), ('pd40'), ('pd41'), ('pd42'), ('pd43'), ('pd44a'),
               ('pd44b'), ('pd45'), ('pd46'), ('pi47'), ('pe48'), ('pe48b'),
               ('pe49'), ('pe49b'), ('pe50'), ('pe50b'), ('pc51'), ('pf'),
               ('ps'), ('t'), ('t2')) d(name);
```

### Rule 3, the census, and the forgeries

`sql` block 6, phase 3's second half, run in a session of its own so the drain's
pending statistics have published: rule 3's census, which recomputes the
launcher's analyze verdict for the tables no churn touched, then fixture 84's
forged index count, then test 120's precondition, then family 6's catalog-count
check — which is what keeps an empty population and an unknown `reltuples = -1`
apart — then the page classes the maintenance left, which is proof 4 of the
no-defeat rule, then the churned snapshot the statement is about to be asked
about.

```sql
-- The rest of phase 3, run in a session of its own so that the drain session's
-- pending statistics have published: rule 3's census, then the catalog
-- forgeries, then the page classes, then the churned snapshot.  Every churned
-- table has already had its maintenance VACUUM (VERBOSE, ANALYZE), in its own
-- recipe or in the drain, so the census finds those tables freshly analyzed;
-- the tables it can still decide are the ones no churn touched.
--
-- DISPOSABLE.  This file analyzes fixtures and writes a forged count into
-- pg_class in a throwaway database of the sandbox cluster.
-- The census runs ANALYZE, so it is a maintenance session too: the same
-- timeouts are 0 in it, and the no-defeat rule's window closes only when the
-- census has finished, which is why the horizon is probed on both sides of it.
SET /* wiki_pgsi_census_client_min_messages */ client_min_messages = warning;
SET /* wiki_pgsi_census_statement_timeout */ statement_timeout = 0;
SET /* wiki_pgsi_census_lock_timeout */ lock_timeout = 0;
SET /* wiki_pgsi_census_idle_timeout */ idle_in_transaction_session_timeout = 0;
SELECT wiki_flush();
SELECT /* wiki_pgsi_census_horizon_before */ horizon_probe('census-before', NULL);

-- Rule 3: the launcher's analyze verdict, recomputed for every suite table
-- after the maintenance step, using the engine's own test rather than a
-- per-fixture annotation -
-- mod_since_analyze > anl_base_thresh + anl_scale_factor * reltuples, with a
-- negative reltuples counted as zero and the comparison strictly greater.
-- The two parameters are NOT the cluster GUCs: relation_needs_vacanalyze
-- takes each from the table's own reloption whenever that reloption holds a
-- non-negative value and falls back to the GUC only otherwise, and
-- autovacuum_enabled = false makes the decision false outright.  Fixtures 94
-- and 95 carry that precedence, at 100/0 and 200000/1; under the maintenance
-- assumption both reach the census already analyzed, so the override no
-- longer changes what the census does to them, but the arithmetic stays the
-- engine's because the defect a current_setting() census would have is in the
-- arithmetic, not in those two fixtures.  autovacuum is off on this cluster,
-- so every ANALYZE below is one this rule asked for.  Only the suite's own schema is censused; the guard
-- fixtures in schema bl are not suite fixtures and are left alone.
DROP TABLE IF EXISTS autoanl;
DROP TABLE IF EXISTS autoanl_after;
CREATE TABLE autoanl AS
SELECT /* wiki_pgsi_autoanalyze_census */
       c.relname                                       AS tbl,
       GREATEST(c.reltuples, 0)::numeric               AS reltuples,
       st.n_mod_since_analyze::numeric                 AS mods,
       o.base_thresh, o.scale_factor, o.av_enabled,
       (o.base_thresh <> current_setting('autovacuum_analyze_threshold')::numeric
        OR o.scale_factor <> current_setting('autovacuum_analyze_scale_factor')::numeric
        OR NOT o.av_enabled)                           AS per_table_override,
       round(o.base_thresh
             + o.scale_factor * GREATEST(c.reltuples, 0)::numeric, 1) AS threshold,
       round(100 * st.n_mod_since_analyze
             / GREATEST(c.reltuples, 1)::numeric, 1)   AS mod_pct,
       (o.av_enabled
        AND st.n_mod_since_analyze
            > o.base_thresh
              + o.scale_factor * GREATEST(c.reltuples, 0)::numeric) AS would_autoanalyze
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
  CROSS JOIN LATERAL (
       SELECT COALESCE((SELECT r.option_value::numeric
                          FROM pg_options_to_table(c.reloptions) r
                         WHERE r.option_name = 'autovacuum_analyze_threshold'),
                       current_setting('autovacuum_analyze_threshold')::numeric)
                                                       AS base_thresh,
              COALESCE((SELECT r.option_value::numeric
                          FROM pg_options_to_table(c.reloptions) r
                         WHERE r.option_name = 'autovacuum_analyze_scale_factor'),
                       current_setting('autovacuum_analyze_scale_factor')::numeric)
                                                       AS scale_factor,
              COALESCE((SELECT r.option_value::bool
                          FROM pg_options_to_table(c.reloptions) r
                         WHERE r.option_name = 'autovacuum_enabled'), true)
                                                       AS av_enabled) o
 WHERE st.schemaname = 'public'
   AND c.relkind = 'r'
   AND c.relname NOT IN ('plan', 'res', 'snap', 'skipped', 'decide',
                         'report_filed', 'autoanl', 'autoanl_after',
                         'maint', 'horizon', 'pageclass');

SELECT /* wiki_pgsi_autoanalyze_generator */
       format('ANALYZE /* wiki_pgsi_autoanalyze */ %I', tbl)
  FROM autoanl WHERE would_autoanalyze ORDER BY tbl
\gexec

-- The read side of rule 3: a view read may be served from a cached snapshot,
-- so the recheck discards it before reading the counter again.  A table the
-- recheck still finds above its own threshold is recorded as a disagreement
-- rather than analyzed a second time.
SELECT /* wiki_pgsi_autoanalyze_clear_snapshot */ pg_stat_clear_snapshot();
CREATE TABLE autoanl_after AS
SELECT /* wiki_pgsi_autoanalyze_recheck */
       c.relname AS tbl, st.n_mod_since_analyze::numeric AS mods,
       GREATEST(c.reltuples, 0)::numeric AS reltuples,
       a.threshold,
       (st.n_mod_since_analyze > a.threshold) AS still_above
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
  JOIN autoanl a ON a.tbl = c.relname
 WHERE st.schemaname = 'public' AND c.relkind = 'r'
   AND a.would_autoanalyze;

SELECT /* wiki_pgsi_autoanalyze_boundary */
       count(*) AS tables_censused,
       count(*) FILTER (WHERE would_autoanalyze) AS analyzed,
       count(*) FILTER (WHERE per_table_override) AS per_table_overrides,
       min(mod_pct) FILTER (WHERE would_autoanalyze) AS lowest_analyzed_pct,
       max(mod_pct) FILTER (WHERE NOT would_autoanalyze) AS highest_left_alone_pct,
       min(threshold) AS min_threshold, max(threshold) AS max_threshold,
       (SELECT count(*) FROM autoanl_after WHERE still_above) AS recheck_disagreements
  FROM autoanl;

-- The tables that carry a per-table reloption, printed with the effective
-- values the rule read for them.
SELECT /* wiki_pgsi_autoanalyze_overrides */ tbl, reltuples, mods,
       base_thresh, scale_factor, threshold, would_autoanalyze
  FROM autoanl WHERE per_table_override ORDER BY tbl;

-- The forgeries, after the census.  Fixture 84's whole point is a partial index
-- whose recorded entry count is wrong, and an ANALYZE of the table rewrites
-- reltuples for the table and for every index on it, so a forgery written
-- during the build would have been silently repaired.
UPDATE /* wiki_pgsi_forge_84 */ pg_class SET reltuples = 5000
 WHERE relname = 'f84';
SELECT /* wiki_pgsi_forge_check */ relname, reltuples AS forged_reltuples
  FROM pg_class WHERE relname = 'f84';

-- Test 120's precondition, asserted after the census rather than assumed.
-- ANALYZE does not sample deterministically: acquire_sample_rows seeds its
-- block sampler from the global PRNG, so a 300-row sample of a million rows
-- usually misses a 2,000-row subset and sometimes finds a row of it.  The
-- fixture's precondition is the resulting state, not the recipe that aims at
-- it: the partial index's own reltuples must read 0, which is what
-- ceil(tupleFract * totalrows) writes when no sampled row passed the
-- predicate.  An unknown count of -1 is not a measured zero either.  When the
-- state did not arrive the fixture records an unmet precondition and is scored
-- from nothing, rather than credited as covered.
SELECT /* wiki_pgsi_120_precondition */ c.relname AS idx,
       c.reltuples AS idx_reltuples, (c.reltuples = 0) AS precondition_met
  FROM pg_class c WHERE c.relname = 'p120';

INSERT /* wiki_pgsi_120_unmet */ INTO skipped(num, leg, idx, reason)
SELECT 120, '', 'p120',
       'unmet precondition: the ANALYZE sample found the subset, p120 reltuples = '
       || c.reltuples
  FROM pg_class c WHERE c.relname = 'p120' AND c.reltuples <> 0
    ON CONFLICT (num, leg) DO NOTHING;

DELETE /* wiki_pgsi_120_unscored */ FROM plan
 WHERE num = 120
   AND EXISTS (SELECT 1 FROM skipped s WHERE s.num = 120 AND s.idx = 'p120');

UPDATE /* wiki_pgsi_120_met */ plan
   SET note = 'precondition asserted after the census: p120 reltuples = 0'
 WHERE num = 120;

-- Family 6 has to keep an empty population and an unknown catalog count
-- apart, because for an index that ended up with no entries they are not the
-- same state and pg_class.reltuples shows only the second: both a fresh build
-- and a rebuild of an empty index leave reltuples = -1 with relpages
-- untouched.  Every fixture in the family therefore asserts its population
-- from its own counting query, which is what built_rows holds; this is the
-- catalog side of the same fixtures, printed so that no -1 in a later reading
-- can be mistaken for a measured zero.
SELECT /* wiki_pgsi_family6_counts */ p.num, p.leg, p.idx,
       p.built_rows AS population_counted, c.reltuples AS idx_reltuples,
       CASE WHEN c.reltuples < 0 THEN 'unknown'
            WHEN c.reltuples = 0 THEN 'measured zero'
            ELSE 'counted' END                          AS catalog_state
  FROM plan p
  JOIN pg_class c ON c.relname = p.idx
  JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
 WHERE p.num BETWEEN 113 AND 120
 ORDER BY p.num, p.leg;

-- Proof 4 of the no-defeat rule: the page classes every planned index carries
-- once the maintenance step has run.  Deleted and half-dead pages are the
-- visible trace of a horizon that moved, and a drained fixture whose index has
-- neither is the shape a defeated VACUUM leaves behind.  pgstatindex reads
-- every page and writes nothing, so the decide phase that follows sees exactly
-- the state the maintenance left.
DELETE FROM pageclass;
INSERT /* wiki_pgsi_pageclass */ INTO pageclass
       (idx, leaf_pages, empty_pages, deleted_pages, avg_leaf_density, index_size)
SELECT p.idx, m.leaf_pages, m.empty_pages, m.deleted_pages,
       CASE WHEN m.avg_leaf_density = 'NaN'::float8 THEN NULL
            ELSE round(m.avg_leaf_density::numeric, 2) END,
       m.index_size
  FROM plan p, LATERAL pgstatindex(p.idx::regclass) m;

SELECT /* wiki_pgsi_pageclass_report */
       count(*) AS indexes_read,
       count(*) FILTER (WHERE deleted_pages > 0) AS with_deleted_pages,
       count(*) FILTER (WHERE empty_pages > 0)   AS with_half_dead_pages,
       coalesce(sum(deleted_pages), 0)           AS deleted_pages_total
  FROM pageclass;

SELECT /* wiki_pgsi_census_horizon_after */ horizon_probe('census-after', NULL);

-- The churned snapshot: the state the statement is about to be asked about.
SELECT /* wiki_pgsi_snap_churned */ count(*) AS churned_snapshots
  FROM (SELECT snap_take('churned', idx) FROM plan ORDER BY num, leg) s;
SELECT /* wiki_pgsi_snap_phases */ phase, count(*) AS snapshots
  FROM snap GROUP BY phase ORDER BY phase;
```

### The PostgreSQL 17 leg script

```sh
#!/usr/bin/env bash
#
# bloat_pgstatindex_v17.sh - the PostgreSQL 17 leg of the measurement behind
# "B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and
# 17".  Bash and SQL only: build the pinned 17 checkout out of tree, run its
# regression suites, start an isolated cluster, build the wiki's shared
# mandatory B-tree bloat suite, run this page's statement exactly as filed,
# and score every fixture against a measured REINDEX INDEX.
#
# The scored fixtures are the shared suite's, not this page's own.  Its six
# families, its five phases (build, baseline, churn, decide, oracle), its
# maintenance assumption, its rule that the maintenance must not be defeated,
# its three porting rules, its REINDEX INDEX oracle and its four verdict bands
# are defined once, in the wiki's common concept page "Mandatory B-Tree Bloat
# Tests"; nothing here redefines them, and every deviation is named on the
# page.  The fixture text, the harness and the churn phase are filed as sql
# blocks 2 to 6 of the same page and are read out of it at run time, so both
# legs run the same suite.
#
# Every maintenance statement the suite issues is one VACUUM (VERBOSE, ANALYZE)
# between maint_begin() and maint_end(), in a session whose settable timeouts
# are 0, and the churn stage checks the rule's four proofs on all of them -
# completion, the VERBOSE dead-but-not-yet-removable count, the horizon holders
# and the page classes - and dies rather than score a defeated fixture.
#
# Schema bl holds what the suite does not cover and this page still measures:
# the shapes pgstatindex refuses, an index the catalog says is not valid, two
# pages of known contents and an empty table's primary key, fresh builds at
# four fillfactors, the four fillfactor-deleted fixtures, the dead-page
# fixture, the two duplicate builds, the build-with-deduplication-off shape,
# and the race stage's own index.  Those are guard and model fixtures, not
# scored fixtures.
#
# The pinned checkout is read only.  Everything this script writes lives under
# $SANDBOX, and `clean` deletes it.
#
# Usage, from the repository root:
#   bash bloat_pgstatindex_v17.sh                 # every stage, in order
#   bash bloat_pgstatindex_v17.sh score residual  # selected stages
#   bash bloat_pgstatindex_v17.sh clean           # stop and delete the sandbox
#
# Stages: build check cluster texts fixtures suite churn report decide facts
#         cost priv compare score guard residual race errors summary stop clean
#
# Environment: WIKI_ROOT PAGE SRC SANDBOX PORT JOBS ROWS OLD_REV OLD_REV_ALERT
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v17/questions/indexing/btree-bloat-with-pgstatindex.md}"
SRC="${SRC:-$WIKI_ROOT/raw/postgres-17}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/pgsi}"
PORT="${PORT:-55417}"
JOBS="${JOBS:-4}"
ROWS="${ROWS:-1000000}"
OLD_REV="${OLD_REV:-cbbbd16}"
OLD_REV_ALERT="${OLD_REV_ALERT:-0dbabb6}"

BUILD="$SANDBOX/build17"; INST="$SANDBOX/install17"; DATA="$SANDBOX/data17"
OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql"; SOCK="$SANDBOX/sock17"; BIN="$INST/bin"
DB=bloat17
export PGPORT="$PORT" PGHOST="$SOCK" PGDATABASE=postgres

# SHA-256 of the sql blocks this page files, in page order.  BASE_SQL is the
# filed statement; BASE_HARNESS, BASE_GATE, BASE_SUITE, BASE_DRAIN and
# BASE_CENSUS are the shared suite's harness, its family 1 fixtures, its
# families 2 to 6, rule 2's drain and rule 3's census.  BASE_PREV is the text
# filed before wasted space was rebased on the fillfactor and BASE_ALERT the
# text filed before alert_pct and the status column were removed; both are
# recovered from git history, for the compare and cost stages.
BASE_SQL=3d4507a54b38ac3edfaffd41f29c91518d6032dd561a025f343bbeb3c0c55b5d
BASE_HARNESS=87f6a505e42ee7432c05a4f514dc43b23f9ddbceabdc782fb710347789d97321
BASE_GATE=d73fb4d599896b5e129f49ee682f57bde8eab06abdcbb085c12f201d08b614a9
BASE_SUITE=713d503da008c19f9f16278070338870389aaf3db3b87198efa1f978f2b4126a
BASE_DRAIN=72711d3ece42ec5423acd2f8e9de15ea40920463785db6aee90e57d33a1d6d83
BASE_CENSUS=9ac052745ce92bdd8b989a8610cfb7b89e5b74b14d911316e92e70ac23993d84
BASE_PREV=f5b995d3c5d51dddd1378e4e1ac31f9ad180cec0cc811a803186b86a1fb721e9
BASE_ALERT=da4f4277b24e654c0241911f3ef977bfa5d109d3986ce30fe07919b3f82c93a0

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# -X ignores ~/.psqlrc; ON_ERROR_STOP is on every helper, because without it a
# failed statement inside a -f script leaves the exit status 0.
# SESSION_OPTS gives every helper session a statement_timeout and a
# lock_timeout.  Both are PGC_USERSET, so the libpq options string applies them
# at session scope, with no reload and no restart, and a block that SETs its
# own values overrides them.  They are passed per call rather than exported,
# because pg_regress keeps an inherited PGOPTIONS and make check must not see
# them.
SESSION_OPTS="-c statement_timeout=30min -c lock_timeout=60s"
q()  { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
s()  { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
t()  { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" -c "$1"; }
fl() { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" -f "$1"; }
# err() runs a statement that is expected to fail and prints the message only.
err() { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -At -q -d "$DB" -c "$1" 2>&1 | grep -E '^(ERROR|FATAL)' | head -1; }

# The fence is assembled at run time so that this script contains no literal
# Markdown fence and can therefore live inside one.
md_block() {
  local lang=$1 want=$2 file=$3 n=0 inb=0 line tick fence
  tick=$(printf '\140'); fence="$tick$tick$tick"
  while IFS= read -r line; do
    if [ "$inb" = 1 ]; then
      if [ "$line" = "$fence" ]; then inb=0; [ "$n" = "$want" ] && return 0; continue; fi
      [ "$n" = "$want" ] && printf '%s\n' "$line"
    elif [ "$line" = "$fence$lang" ]; then
      n=$((n + 1)); inb=1
    fi
  done < "$file"
}

# block <n> <want-hash> <outfile> <label>: extract one sql block of the page
# and refuse to run on a text that is not the filed one.
block() {
  local n=$1 want=$2 file=$3 label=$4 got
  md_block sql "$n" "$PAGE" > "$file"
  [ -s "$file" ] || die "sql block $n of $PAGE is empty"
  got=$(sha256sum < "$file" | cut -d' ' -f1)
  [ "$got" = "$want" ] || die "$label (sql block $n) hashes $got, expected $want"
  note "$label: $(wc -l < "$file") lines, $(wc -c < "$file") bytes, sha256 ${got:0:12}"
}

# parse_verbose <log>: turn the maintenance statements' VACUUM (VERBOSE) output
# into one UPDATE per maintained table, so that proof 2 of the shared suite's
# rule "The maintenance must not be defeated" - each statement's own "dead but
# not yet removable" count - is a recorded number rather than a line in a log.
# A 17.11 server emits one message per relation,
#   INFO:  finished vacuuming "db.schema.tbl": index scans: N
#   tuples: X removed, Y remain, Z are dead but not yet removable
# so the relation name is carried from the header line to the tuples line, and
# the schema-qualified name is cut back to the bare table name.  INFO reaches
# the client whatever client_min_messages says, which is why the fixture
# sessions keep theirs at warning.  A table maintained twice keeps the larger
# of the two dead counts, so neither statement can hide behind the other.
# Bash case patterns and parameter expansion only: no awk, no perl.
parse_verbose() {
  local log=$1 line cur="" rest removed remain dead
  [ -f "$log" ] || return 0
  while IFS= read -r line; do
    case $line in
      *'finished vacuuming "'*)
        rest=${line#*finished vacuuming \"}; rest=${rest%%\"*}; cur=${rest##*.} ;;
      'tuples: '*' are dead but not yet removable'*)
        [ -n "$cur" ] || continue
        rest=${line#tuples: };    removed=${rest%% removed,*}
        rest=${rest#* removed, }; remain=${rest%% remain,*}
        rest=${rest#* remain, };  dead=${rest%% are dead*}
        printf "UPDATE /* wiki_pgsi_maint_verbose */ maint SET removed = %s, remain = %s, dead_not_removable = greatest(coalesce(dead_not_removable, 0), %s) WHERE tbl = '%s';\n" \
               "$removed" "$remain" "$dead" "$cur"
        cur="" ;;
    esac
  done < "$log"
}

# maint_skips: proof 1's other half.  A foreground VACUUM or ANALYZE that could
# not take its ShareUpdateExclusiveLock says so in the log, and a statement cut
# short by a timeout does too; either way the command returned without doing
# the work.  Only the lines after the run mark the cluster stage wrote are
# read, so a re-run does not inherit the lines of the run before it.
maint_skips() {
  local log="$OUT/server17.log" from line
  : > "$OUT/maint_skips17.txt"
  [ -f "$log" ] || return 0
  # The window the rule names: from the first churn statement, which the suite
  # stage marks, until the census has finished.  Reading from the run mark
  # instead would sweep in the race stage's deliberate lock-timeout
  # cancellation whenever the suite and churn stages are re-run on a cluster
  # that already carries one.
  from=$(grep -n 'wiki_pgsi_maint_mark' "$log" | tail -1 | cut -d: -f1)
  [ -n "${from:-}" ] || from=$(grep -n 'wiki_pgsi_run_mark' "$log" | tail -1 | cut -d: -f1)
  [ -n "${from:-}" ] || from=1
  while IFS= read -r line; do
    case $line in
      *'skipping vacuum of '*|*'skipping analyze of '*|\
      *'canceling autovacuum task'*|*'canceling statement due to'*)
        printf '%s\n' "$line" >> "$OUT/maint_skips17.txt" ;;
    esac
  done < <(sed -n "${from},\$p" "$log")
  return 0
}

# The shared suite's rule "The maintenance must not be defeated" says a fixture
# that carried a defeating state into its maintenance statement is repaired and
# re-run rather than scored.  This function is that rule, enforced: it fails the
# run instead of publishing a number taken under a defeated maintenance.
#
# Four proofs, per maintenance statement:
#   1. the statement completed - a recorded end stamp - and no skip or
#      cancellation line names its table;
#   2. its VERBOSE "dead but not yet removable" count exists and is zero;
#   3. every horizon probe found no other backend with an xmin or an open
#      transaction, no replication slot and no prepared transaction;
#   4. the page classes are recorded, which the census file's own read does.
maint_proofs() {
  local n bad skips=0
  q "SELECT /* wiki_pgsi_maint_after */ maint_after()" > /dev/null \
    || die "the post-maintenance counter read failed"
  n=$(s 'SELECT count(*) FROM maint')
  [ "${n:-0}" -gt 0 ] || die "no maintenance statement was recorded at all"
  bad=$(s 'SELECT count(*) FROM maint WHERE ended IS NULL')
  [ "$bad" = 0 ] || { t 'SELECT tbl, source, started FROM maint
                          WHERE ended IS NULL ORDER BY tbl' >&2
                      die "$bad maintenance statements did not complete"; }
  bad=$(s 'SELECT count(*) FROM maint WHERE dead_not_removable IS NULL')
  [ "$bad" = 0 ] || { t 'SELECT tbl, source FROM maint
                          WHERE dead_not_removable IS NULL ORDER BY tbl' >&2
                      die "$bad maintained tables have no VERBOSE count: proof 2 is missing"; }
  bad=$(s 'SELECT count(*) FROM maint WHERE dead_not_removable > 0')
  [ "$bad" = 0 ] || { t 'SELECT tbl, source, removed, remain, dead_not_removable,
                                dead_after
                           FROM maint WHERE dead_not_removable > 0
                          ORDER BY dead_not_removable DESC' >&2
                      die "$bad maintained tables kept dead tuples the horizon still covered: the maintenance was defeated, repair the fixture and re-run"; }
  bad=$(s 'SELECT count(*) FROM horizon
            WHERE xmin_holders > 0 OR open_xacts > 0
               OR slots > 0 OR prepared > 0')
  [ "$bad" = 0 ] || { t 'SELECT step, tbl, xmin_holders, open_xacts, slots,
                                prepared, detail
                           FROM horizon
                          WHERE xmin_holders > 0 OR open_xacts > 0
                             OR slots > 0 OR prepared > 0 ORDER BY at' >&2
                      die "$bad horizon probes found a holder: the maintenance ran with a pinned horizon"; }
  bad=$(s 'SELECT count(*) FROM pageclass')
  [ "${bad:-0}" -gt 0 ] || die "no page classes were recorded: proof 4 is missing"
  maint_skips
  # grep -c on an empty file prints 0 and exits 1, so the count is taken only
  # when there is something to count; an "|| printf 0" fallback here would
  # concatenate the two zeros and fail the check on a clean run.
  [ -s "$OUT/maint_skips17.txt" ] && skips=$(grep -c '' "$OUT/maint_skips17.txt")
  { printf 'maintenance statements  %s, %s completed\n' "$n" \
      "$(s 'SELECT count(*) FROM maint WHERE ended IS NOT NULL')"
    printf 'by source               %s\n' \
      "$(s "SELECT string_agg(source || '=' || n, ' ' ORDER BY source)
              FROM (SELECT source, count(*) AS n FROM maint GROUP BY source) x")"
    printf 'dead but not removable  max %s over %s tables\n' \
      "$(s 'SELECT coalesce(max(dead_not_removable), -1) FROM maint')" "$n"
    printf 'dead tuples left behind max %s\n' \
      "$(s 'SELECT coalesce(max(dead_after), -1) FROM maint')"
    printf 'tuples removed          %s\n' \
      "$(s 'SELECT coalesce(sum(removed), 0) FROM maint')"
    printf 'horizon probes clean    %s of %s\n' \
      "$(s 'SELECT count(*) FROM horizon
             WHERE xmin_holders = 0 AND open_xacts = 0
               AND slots = 0 AND prepared = 0')" \
      "$(s 'SELECT count(*) FROM horizon')"
    printf 'timeout sets in force   %s: %s\n' \
      "$(s 'SELECT count(DISTINCT timeouts) FROM maint')" \
      "$(s 'SELECT DISTINCT timeouts FROM maint')"
    printf 'indexes page-classed    %s, %s with deleted pages, %s deleted pages\n' \
      "$(s 'SELECT count(*) FROM pageclass')" \
      "$(s 'SELECT count(*) FROM pageclass WHERE deleted_pages > 0')" \
      "$(s 'SELECT coalesce(sum(deleted_pages), 0) FROM pageclass')"
    printf 'skip or cancellation lines %s\n' "$skips"; } > "$OUT/maint_proofs17.txt"
  cat "$OUT/maint_proofs17.txt" >&2
  [ "$skips" = 0 ] || { cat "$OUT/maint_skips17.txt" >&2
                        die "$skips skip or cancellation line(s) in the server log: a maintenance statement did not do its work"; }
}

# ---------------------------------------------------------------- build ------
stage_build() {
  say "build 17 out of tree from $SRC"
  [ -x "$BIN/postgres" ] && { note "already built, skipping"; return 0; }
  [ -x "$SRC/configure" ] || die "no pinned checkout at $SRC; set SRC or run from the repository root"
  mkdir -p "$BUILD" "$OUT" "$SQLD"
  ( cd "$BUILD" && "$SRC/configure" --prefix="$INST" --enable-debug \
      --with-icu --with-readline --with-zlib > configure.log 2>&1 ) \
    || { cp "$BUILD/configure.log" "$OUT/configure17.log" 2>/dev/null; die "configure failed, see $OUT/configure17.log"; }
  ( cd "$BUILD" && make -j"$JOBS" > make.log 2>&1 && make install > install.log 2>&1 ) \
    || { cp "$BUILD"/*.log "$OUT/" 2>/dev/null; grep -m3 'error:' "$BUILD/make.log" >&2; die "make failed"; }
  ( cd "$BUILD" && make -C contrib/pgstattuple -j"$JOBS" >> install.log 2>&1 \
      && make -C contrib/pgstattuple install >> install.log 2>&1 ) || die "contrib/pgstattuple failed"
  local l
  for l in configure make install; do cp "$BUILD/$l.log" "$OUT/${l}17.log" 2>/dev/null; done
  note "$("$BIN/postgres" --version)"
}

stage_check() {
  say "regression suites, 17"
  mkdir -p "$OUT"
  : > "$OUT/checks17.txt"
  ( cd "$BUILD" && make check > check_core.log 2>&1 )
  printf 'core=%s %s\n' "$?" \
    "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_core.log" | tail -1)" \
    >> "$OUT/checks17.txt"
  ( cd "$BUILD" && make -C contrib/pgstattuple check > check_pgstattuple.log 2>&1 )
  printf 'pgstattuple=%s %s\n' "$?" \
    "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_pgstattuple.log" | tail -1)" \
    >> "$OUT/checks17.txt"
  local l d
  for l in "$BUILD"/check_*.log; do [ -f "$l" ] && cp "$l" "$OUT/17_$(basename "$l")"; done
  for d in "$BUILD"/src/test/regress/regression.diffs "$BUILD"/contrib/pgstattuple/regression.diffs; do
    [ -f "$d" ] && cp "$d" "$OUT/diffs17_$(basename "$(dirname "$d")").txt"
  done
  cat "$OUT/checks17.txt" >&2
}

# -------------------------------------------------------------- cluster ------
# Cluster settings and their apply scope, all written to postgresql.conf before
# the first start, so every one of them is in force from the first connection:
#   listen_addresses, port, unix_socket_directories, shared_buffers,
#   logging_collector  -> PGC_POSTMASTER, restart
#   fsync, autovacuum                                   -> PGC_SIGHUP, reload
#   maintenance_work_mem, max_parallel_maintenance_workers -> PGC_USERSET,
#                                                          session scope
# autovacuum is off so that no background worker moves a fixture between the
# five phases, not because the fixtures model an unmaintained database: under
# the shared suite's maintenance assumption every churn ends on one bracketed
# VACUUM (VERBOSE, ANALYZE) run by the fixture text itself, and rule 3's census
# recomputes the launcher's analyze verdict for the tables no churn touched.
stage_cluster() {
  say "isolated 17 cluster on port $PORT"
  mkdir -p "$OUT" "$SQLD" "$SOCK"
  if [ ! -f "$DATA/PG_VERSION" ]; then
    "$BIN/initdb" -D "$DATA" --locale=C --encoding=UTF8 > "$OUT/initdb17.log" 2>&1 \
      || die "initdb failed, see $OUT/initdb17.log"
    cat >> "$DATA/postgresql.conf" <<CONF
listen_addresses = ''
port = $PORT
unix_socket_directories = '$SOCK'
shared_buffers = 512MB
maintenance_work_mem = 256MB
max_parallel_maintenance_workers = 0
autovacuum = off
fsync = off
logging_collector = off
CONF
  fi
  if ! "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server17.log" -w start > /dev/null 2>&1 \
      || die "server did not start, see $OUT/server17.log"
  fi
  # The error audit reads only the lines after this mark, so a re-run does not
  # inherit the errors of the run before it.
  printf -- '-- wiki_pgsi_run_mark %s\n' "$(date -u +%FT%TZ)" >> "$OUT/server17.log"
  "$BIN/psql" -X -At -q -d postgres -c "SELECT 1" > /dev/null 2>&1 || die "cannot connect"
  "$BIN/psql" -X -At -q -d postgres -c \
    "SELECT count(*) FROM pg_database WHERE datname = '$DB'" | grep -q '^1$' \
    || "$BIN/createdb" "$DB" || die "createdb failed"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null || die "pgstattuple not installed"
  {
    printf 'uname=%s\n' "$(uname -sm)"
    printf 'server_version_num=%s\n' "$(s 'SHOW server_version_num')"
    printf 'server_version=%s\n' "$(s 'SHOW server_version')"
    printf 'block_size=%s\n' "$(s 'SHOW block_size')"
    printf 'max_data_alignment=%s\n' "$("$BIN/pg_controldata" -D "$DATA" | grep -i 'maximum data alignment' | tr -s ' ' | cut -d' ' -f4)"
    printf 'pgstattuple=%s\n' "$(s "SELECT extversion FROM pg_extension WHERE extname = 'pgstattuple'")"
    printf 'autovacuum_analyze_threshold=%s\n' "$(s 'SHOW autovacuum_analyze_threshold')"
    printf 'autovacuum_analyze_scale_factor=%s\n' "$(s 'SHOW autovacuum_analyze_scale_factor')"
  } > "$OUT/platform17.txt"
  cat "$OUT/platform17.txt" >&2
}

# ---------------------------------------------------------------- texts -----
# Six texts come out of the page and one out of git history:
#   report.sql   the filed statement, byte for byte, hash-checked
#   view.sql     the same text as a view over the internal `final` stage, with
#                one edit, printed: the two SET lines dropped.  The filed text
#                prefilters nothing, so the view's population is the report's
#   harness.sql, gate.sql, suite.sql, drain.sql, census.sql
#                the shared mandatory suite, all hash-checked
#   prev.sql     the text filed before wasted space was rebased on the
#                fillfactor, recovered from OLD_REV for the cost comparison
gen_view() {                       # gen_view <view> < text
  local view=$1 line tail=0
  printf 'DROP VIEW IF EXISTS %s CASCADE;\nCREATE VIEW %s AS\n' "$view" "$view"
  while IFS= read -r line; do
    case $line in
      "SET statement_timeout"*|"SET lock_timeout"*)
        printf '   harness edit: dropped %s\n' "$line" >&2; continue ;;
      *"AS min_index_bytes"*)
        printf '   harness edit: %s -> 0\n' "$(printf '%s' "$line" | tr -s ' ')" >&2
        # The filed text has no size prefilter left to neutralise; the two
        # recovered texts still carry one, and are read at 0 so that all three
        # are compared over one population.  The superseded alert_pct text
        # carries another params entry after this one, so the trailing comma
        # has to survive the edit.
        case $line in
          *"min_index_bytes,"*)
            printf '           0::bigint AS min_index_bytes,  -- harness: score every index\n' ;;
          *)
            printf '           0::bigint AS min_index_bytes  -- harness: score every index\n' ;;
        esac
        continue ;;
      "SELECT /* wiki_btree_bloat_pgstatindex_12_17 */") tail=1; continue ;;
    esac
    [ "$tail" = 1 ] && continue
    printf '%s\n' "$line"
  done
  printf 'SELECT f.* FROM final f;\n'
}

stage_texts() {
  say "extract the statement and the shared suite from $PAGE"
  mkdir -p "$SQLD" "$OUT"
  [ -f "$PAGE" ] || die "no page at $PAGE; set PAGE or run from the repository root"
  block 1 "$BASE_SQL"     "$SQLD/report.sql"  "filed statement"
  block 2 "$BASE_HARNESS" "$SQLD/harness.sql" "suite harness"
  block 3 "$BASE_GATE"    "$SQLD/gate.sql"    "family 1 fixtures"
  block 4 "$BASE_SUITE"   "$SQLD/suite.sql"   "families 2-6 fixtures"
  block 5 "$BASE_DRAIN"   "$SQLD/drain.sql"   "rule 2 drain"
  block 6 "$BASE_CENSUS"  "$SQLD/census.sql"  "rule 3 census and forgeries"
  gen_view bloat_final < "$SQLD/report.sql" > "$SQLD/view.sql"
  # The statement alone, without the two SET lines, for EXPLAIN.
  grep -v '^SET ' "$SQLD/report.sql" > "$SQLD/bare.sql"
  old_text "$OLD_REV"       "$BASE_PREV"  prev
  old_text "$OLD_REV_ALERT" "$BASE_ALERT" alert
}

# old_text <rev> <want-hash> <name>: recover sql block 1 of this page as it
# stood at <rev>, refuse a text that is not the one recorded, and leave it in
# $SQLD/<name>.sql.  The two superseded texts are what the compare stage
# measures the filed text against, on the population this run built.
old_text() {
  local rev=$1 want=$2 name=$3 got
  local rel=wiki/v17/questions/indexing/btree-bloat-with-pgstatindex.md
  if ! git -C "$WIKI_ROOT" cat-file -e "$rev:$rel" 2>/dev/null; then
    note "no revision $rev in this repository; the $name comparison will be skipped"
    return 0
  fi
  git -C "$WIKI_ROOT" show "$rev:$rel" > "$SQLD/page_$name.md"
  md_block sql 1 "$SQLD/page_$name.md" > "$SQLD/$name.sql"
  got=$(sha256sum < "$SQLD/$name.sql" | cut -d' ' -f1)
  [ "$got" = "$want" ] || die "$name text hashes $got, expected $want"
  grep -v '^SET ' "$SQLD/$name.sql" > "$SQLD/${name}_bare.sql"
  note "$name text ($rev): $(wc -l < "$SQLD/$name.sql") lines, $(wc -c < "$SQLD/$name.sql") bytes, sha256 ${got:0:12}"
}

# ------------------------------------------------------------- fixtures -----
# Schema bl: the guard and model fixtures, which the shared suite does not
# cover and this page still measures.  Every statement is DISPOSABLE - it drops
# and rebuilds a whole schema and writes indisvalid = false into pg_index by
# hand - and is not meant for a database anyone cares about.  The two session
# GUCs are PGC_USERSET: session scope, no reload and no restart.
stage_fixtures() {
  say "guard and model fixtures in schema bl (rows=$ROWS)"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null
  cat > "$SQLD/fixtures.sql" <<'SQL'
-- DISPOSABLE guard and model fixtures for the pgstatindex bloat report.
-- Every object lives in schema bl of a throwaway database.
SET statement_timeout = '30min';   -- PGC_USERSET, session scope
SET lock_timeout      = '30s';     -- PGC_USERSET, session scope
SET client_min_messages = warning;

DROP SCHEMA IF EXISTS bl CASCADE;
CREATE SCHEMA bl;

-- 1. fresh builds at four fillfactors: the model's target density, measured.
--    i_race is the race stage's own fixture, dropped and recreated there so no
--    other fixture is disturbed.
CREATE TABLE bl.t_fresh (id int);
INSERT INTO bl.t_fresh SELECT g FROM generate_series(1, :ff_rows) g;
CREATE INDEX i_fresh ON bl.t_fresh (id);
CREATE INDEX i_ff100 ON bl.t_fresh (id) WITH (fillfactor = 100);
CREATE INDEX i_ff50  ON bl.t_fresh (id) WITH (fillfactor = 50);
CREATE INDEX i_ff10  ON bl.t_fresh (id) WITH (fillfactor = 10);
CREATE INDEX i_race  ON bl.t_fresh (id) WITH (fillfactor = 80);

-- 2. the four fillfactor fixtures: built at a stated fillfactor, then nine
--    tenths of the rows deleted and the table vacuumed.
CREATE TABLE bl.t_ffdel (id int);
INSERT INTO bl.t_ffdel SELECT g FROM generate_series(1, :ff_rows) g;
CREATE INDEX i_ff100_del90 ON bl.t_ffdel (id) WITH (fillfactor = 100);
CREATE INDEX i_ff50_del90  ON bl.t_ffdel (id) WITH (fillfactor = 50);
CREATE INDEX i_ff10_del90  ON bl.t_ffdel (id) WITH (fillfactor = 10);
DELETE FROM bl.t_ffdel WHERE id % 10 <> 0;
VACUUM bl.t_ffdel;

CREATE TABLE bl.t_ffhead (id int);
INSERT INTO bl.t_ffhead SELECT g FROM generate_series(1, :ff_rows) g;
CREATE INDEX i_ff50_delhead ON bl.t_ffhead (id) WITH (fillfactor = 50);
DELETE FROM bl.t_ffhead WHERE id <= (:ff_rows * 9) / 10;
VACUUM bl.t_ffhead;

-- 3. the dead-page fixture: a contiguous head deleted, then vacuumed, so whole
--    pages hold nothing while avg_leaf_density stays high.
CREATE TABLE bl.t_delhead (id int);
INSERT INTO bl.t_delhead SELECT g FROM generate_series(1, :rows) g;
CREATE INDEX i_delhead ON bl.t_delhead (id);
DELETE FROM bl.t_delhead WHERE id <= (:rows * 7) / 10;
VACUUM bl.t_delhead;

-- 4. duplicates, built two ways: by CREATE INDEX and by inserts.
CREATE TABLE bl.t_dup (v int);
INSERT INTO bl.t_dup SELECT g % 10 FROM generate_series(1, :rows) g;
CREATE INDEX i_dup ON bl.t_dup (v);

CREATE TABLE bl.t_dup_ins (v int);
CREATE INDEX i_dup_ins ON bl.t_dup_ins (v);
INSERT INTO bl.t_dup_ins SELECT g % 10 FROM generate_series(1, :rows) g;

-- 5. built with deduplication off, then turned back on: the pg_upgrade shape,
--    where a rebuild compresses what the current file cannot.  The reloption
--    does not exist on every major, so the fixture is attempted and its
--    absence recorded.
DO $dd$
DECLARE msg text;
BEGIN
  EXECUTE 'CREATE TABLE bl.t_dedup (v int)';
  EXECUTE 'INSERT INTO bl.t_dedup SELECT g % 10 FROM generate_series(1, ' ||
          current_setting('bl.rows') || ') g';
  BEGIN
    EXECUTE 'CREATE INDEX i_dedup_off ON bl.t_dedup (v) WITH (deduplicate_items = off)';
    EXECUTE 'ALTER INDEX bl.i_dedup_off SET (deduplicate_items = on)';
  EXCEPTION WHEN OTHERS THEN
    msg := SQLERRM;
    RAISE WARNING 'i_dedup_off skipped: %', msg;
  END;
END
$dd$;
SELECT CASE WHEN to_regclass('bl.i_dedup_off') IS NULL
            THEN 'i_dedup_off skipped' ELSE 'i_dedup_off built' END AS dedup_off_fixture;

-- 6. two pages of known contents, for the implied leaf capacity, and an empty
--    table's primary key, for the NaN density.
CREATE TABLE bl.c_one (id int);
INSERT INTO bl.c_one VALUES (1);
CREATE INDEX c_one_idx ON bl.c_one (id);

CREATE TABLE bl.c_zero (id int);
INSERT INTO bl.c_zero VALUES (1);
CREATE INDEX c_zero_idx ON bl.c_zero (id);
DELETE FROM bl.c_zero;
VACUUM bl.c_zero;

CREATE TABLE bl.t_empty (id int PRIMARY KEY);

-- 7. the shapes pgstatindex refuses, one per candidate filter.
CREATE TABLE bl.s_other (id int, v text, g_point point, r int4range);
INSERT INTO bl.s_other SELECT g, md5(g::text), point(g, g), int4range(g, g + 10)
  FROM generate_series(1, 20000) g;
CREATE INDEX s_hash   ON bl.s_other USING hash   (id);
CREATE INDEX s_gin    ON bl.s_other USING gin    (to_tsvector('simple', v));
CREATE INDEX s_gist   ON bl.s_other USING gist   (g_point);
CREATE INDEX s_spgist ON bl.s_other USING spgist (g_point);
CREATE INDEX s_brin   ON bl.s_other USING brin   (id);
CREATE VIEW  bl.s_view AS SELECT 1 AS one;
CREATE SEQUENCE bl.s_seq;

CREATE TABLE bl.t_part (id int) PARTITION BY RANGE (id);
CREATE TABLE bl.t_part_1 PARTITION OF bl.t_part FOR VALUES FROM (1) TO (100001);
CREATE TABLE bl.t_part_2 PARTITION OF bl.t_part FOR VALUES FROM (100001) TO (200001);
INSERT INTO bl.t_part SELECT g FROM generate_series(1, 200000) g;
CREATE INDEX i_part ON bl.t_part (id);

-- 8. an index the catalog says is not valid.  Only a disposable cluster may
--    have its catalog written to by hand like this.
CREATE TABLE bl.t_invalid (id int);
INSERT INTO bl.t_invalid SELECT g FROM generate_series(1, 300000) g;
CREATE INDEX i_invalid ON bl.t_invalid (id);
UPDATE pg_index SET indisvalid = false WHERE indexrelid = 'bl.i_invalid'::regclass;
SQL
  local ffrows=$((ROWS / 5))
  # psql does not substitute :variables inside a dollar-quoted body, so the
  # version-guarded fixture reads its row count from a database-level GUC.
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" \
    -c "ALTER DATABASE $DB SET bl.rows = '$ROWS'" > /dev/null || die "cannot set bl.rows"
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" \
    -v rows="$ROWS" -v ff_rows="$ffrows" \
    -f "$SQLD/fixtures.sql" > "$OUT/fixtures17.log" 2>&1 || {
      tail -5 "$OUT/fixtures17.log" >&2; die "guard fixtures failed"; }
  grep -E 'i_dedup_off (built|skipped)' "$OUT/fixtures17.log" >&2
  note "indexes in bl: $(s "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'bl' AND c.relkind IN ('i','I')")"
}

# ---------------------------------------------------------------- suite -----
# Phases 1 and 2 of the shared mandatory suite: the public schema is recreated,
# the harness installed - its event trigger is what cuts each recipe at its
# index build - then family 1 and families 2 to 6 are built and each fixture's
# build contract checked while it is still as built.
stage_suite() {
  say "the shared mandatory suite, build and baseline phases"
  [ -f "$SQLD/suite.sql" ] || die "run the texts stage first"
  # CREATE SCHEMA public grants nothing to PUBLIC, so initdb's USAGE grant is
  # restored here: without it a non-superuser cannot even see pgstatindex, and
  # the privilege stage would measure the sandbox rather than the function.
  q "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;
     GRANT USAGE ON SCHEMA public TO PUBLIC;" > /dev/null \
    || die "schema reset failed"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null || die "pgstattuple not installed"
  # The no-defeat rule's window opens at the first churn statement, which is in
  # the fixture file below; this mark is where the skip-line check starts
  # reading, so a re-run of this stage does not inherit an earlier run's lines.
  printf -- '-- wiki_pgsi_maint_mark %s\n' "$(date -u +%FT%TZ)" >> "$OUT/server17.log"
  fl "$SQLD/harness.sql" > "$OUT/suite_harness17.log" 2>&1 \
    || { tail -5 "$OUT/suite_harness17.log" >&2; die "harness install failed"; }
  # client_min_messages is debug1 for family 1 only, because
  # _bt_allequalimage logs its own verdict at that level.
  PGOPTIONS="$SESSION_OPTS -c client_min_messages=debug1" \
    "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" -f "$SQLD/gate.sql" \
    > "$OUT/gate17.log" 2>&1 || { tail -20 "$OUT/gate17.log" >&2; die "family 1 failed"; }
  grep -c 'can safely use deduplication' "$OUT/gate17.log" \
    | xargs printf 'DEBUG1 can safely use deduplication: %s\n' >&2
  grep -c 'cannot use deduplication' "$OUT/gate17.log" \
    | xargs printf 'DEBUG1 cannot use deduplication:      %s\n' >&2
  # stdout and stderr are split here, because the maintenance statements'
  # VACUUM (VERBOSE) messages arrive on stderr and the churn stage parses them
  # for proof 2 of the no-defeat rule.
  fl "$SQLD/suite.sql" > "$OUT/suite17.log" 2> "$OUT/suite_verbose17.log" \
    || { tail -20 "$OUT/suite17.log" >&2; tail -20 "$OUT/suite_verbose17.log" >&2
         die "families 2-6 failed"; }
  {
    printf -- '-- family 1 build log, tail\n'; tail -8 "$OUT/gate17.log"
    printf -- '-- families 2-6 build log, tail\n'; tail -12 "$OUT/suite17.log"
  } > "$OUT/suite_build17.txt"
  note "$(s "SELECT count(*) || ' fixtures planned, ' ||
              (SELECT count(*) FROM skipped) || ' skipped, ' ||
              (SELECT count(*) FROM snap WHERE phase = 'built') || ' baselines, ' ||
              (SELECT count(*) FROM plan
                WHERE want_rows IS NOT NULL AND built_rows <> want_rows) ||
              ' build-contract failures' FROM plan")"
  t "SELECT /* wiki_pgsi_suite_skips */ num, leg, idx, reason FROM skipped
      ORDER BY num, leg" > "$OUT/skipped17.txt" 2>&1
  t "SELECT /* wiki_pgsi_suite_families */ grp, count(*) AS fixtures,
            count(*) FILTER (WHERE want_stage = 'rebuild') AS want_rebuild
       FROM plan GROUP BY grp ORDER BY grp" >> "$OUT/skipped17.txt" 2>&1
  cat "$OUT/skipped17.txt" >&2
}

# ---------------------------------------------------------------- churn -----
# Phase 3, in the order the shared suite prescribes.  The drain runs in its own
# session and the census in another, because before PostgreSQL 15 a backend's
# pending statistics publish when it exits, and rule 3 reads them.  Between
# them the maintenance statements' VERBOSE output is turned into recorded
# numbers, and after them the four no-defeat proofs are checked: the stage dies
# rather than score a fixture whose maintenance was defeated.
stage_churn() {
  say "churn: rule 2 drain with its maintenance step, rule 3 census, forgeries last, churned snapshot"
  [ -n "$(s 'SELECT 1 FROM plan LIMIT 1')" ] || die "no plan rows; run the suite stage first"
  fl "$SQLD/drain.sql" > "$OUT/drain17.txt" 2> "$OUT/drain_verbose17.log" \
    || { tail -5 "$OUT/drain17.txt" >&2; tail -5 "$OUT/drain_verbose17.log" >&2
         die "drain failed"; }
  # Proof 2, recorded: every VERBOSE message this run produced, the fixture
  # file's statements and the drain's alike, as one UPDATE per maintained
  # table.  The UPDATEs are keyed by table and take the greatest dead count, so
  # applying them twice changes nothing.
  parse_verbose "$OUT/suite_verbose17.log" > "$SQLD/maint_verbose.sql"
  parse_verbose "$OUT/drain_verbose17.log" >> "$SQLD/maint_verbose.sql"
  [ -s "$SQLD/maint_verbose.sql" ] \
    || die "the VACUUM VERBOSE output produced no tuples line: proof 2 is missing"
  fl "$SQLD/maint_verbose.sql" > /dev/null || die "recording the VERBOSE counts failed"
  sleep 1
  fl "$SQLD/census.sql" > "$OUT/census17.txt" 2>&1 || { tail -5 "$OUT/census17.txt" >&2; die "census failed"; }
  tail -40 "$OUT/census17.txt" >&2
  say "no-defeat proofs: completion, VERBOSE counts, horizon, page classes"
  maint_proofs
  # The skip list is re-dumped here because the census can add to it: test
  # 120's precondition is asserted after the census, and an unmet precondition
  # is a skip rather than a score.
  t "SELECT /* wiki_pgsi_skips_after_census */ num, leg, idx, reason FROM skipped
      ORDER BY num, leg" > "$OUT/skipped17.txt" 2>&1
  t "SELECT /* wiki_pgsi_families_after_census */ grp, count(*) AS fixtures,
            count(*) FILTER (WHERE want_stage = 'rebuild') AS want_rebuild
       FROM plan GROUP BY grp ORDER BY grp" >> "$OUT/skipped17.txt" 2>&1
  note "$(s "SELECT count(*) || ' fixtures scored after the census, ' ||
              (SELECT count(*) FROM skipped) || ' skipped' FROM plan")"
}

# --------------------------------------------------------------- report -----
# Phase 4, the decide phase, part one: the filed text exactly as filed, both
# SET lines included.  Its own output is what the reader sees, so the rows it
# prints are loaded back as report_filed and are what `reported` means.
stage_report() {
  say "run the filed statement"
  [ -f "$SQLD/report.sql" ] || die "run the texts stage first"
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -P footer=off -A -F '|' -d "$DB" \
    -f "$SQLD/report.sql" > "$OUT/report17.txt" 2> "$OUT/report17.err"
  local rc=$?
  if [ "$rc" != 0 ]; then
    printf 'exact_text=refused\n' > "$OUT/exact17.txt"
    head -5 "$OUT/report17.err" >> "$OUT/exact17.txt"
    cat "$OUT/exact17.txt" >&2
    die "the filed text did not run; see $OUT/report17.err"
  fi
  printf 'exact_text=executes\n' > "$OUT/exact17.txt"
  # footer=off leaves one header line and one line per row.
  local rows cols
  rows=$(grep -c '^' "$OUT/report17.txt"); rows=$((rows - 1))
  cols=$(head -1 "$OUT/report17.txt" | tr '|' '\n' | grep -c '^')
  {
    printf 'report_rows=%s\n' "$rows"
    printf 'report_columns=%s\n' "$cols"
    printf 'report_bytes=%s\n' "$(wc -c < "$OUT/report17.txt")"
  } >> "$OUT/exact17.txt"
  cat "$OUT/exact17.txt" >&2
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" \
    -f "$SQLD/report.sql" > "$OUT/report17_pretty.txt" 2>&1
  # Load the printed rows back.  Fields 2, 13 and 14 are index_name,
  # est_reclaimable_pct and notes; no field of this report can contain a pipe.
  q "DROP TABLE IF EXISTS report_filed;
     CREATE /* wiki_pgsi_report_filed */ TABLE report_filed(index_name text PRIMARY KEY, est_pct numeric, notes text);" \
    > /dev/null || die "report_filed failed"
  : > "$SQLD/report_rows.sql"
  local name pct notes
  while IFS='|' read -r _ name _ _ _ _ _ _ _ _ _ _ pct notes; do
    [ -n "${name:-}" ] || continue
    printf "INSERT INTO report_filed VALUES ('%s', %s, '%s');\n" \
      "${name//\'/\'\'}" "${pct:-NULL}" "${notes//\'/\'\'}" >> "$SQLD/report_rows.sql"
  done < <(tail -n +2 "$OUT/report17.txt")
  fl "$SQLD/report_rows.sql" > /dev/null || die "loading report_filed failed"
  note "report_filed rows: $(s 'SELECT count(*) FROM report_filed')"
}

# --------------------------------------------------------------- decide -----
# Phase 4, part two: the same text as a view over its internal `final` stage,
# so every scored fixture gets the statement's own arithmetic with every
# intermediate column visible.  The filed text prefilters nothing, so the
# view's population is the report's and the two must agree row for row.  One
# pass, materialized, because the view reads every page of every index.
stage_decide() {
  say "materialize the statement's reading of every index"
  fl "$SQLD/view.sql" > /dev/null || die "harness view failed"
  q "DROP TABLE IF EXISTS decide;
     CREATE TABLE decide AS SELECT /* wiki_pgsi_decide */ * FROM bloat_final;" \
    > /dev/null || die "decide failed"
  q "CREATE /* wiki_pgsi_decide_idx */ INDEX decide_idx ON decide (index_name);" > /dev/null
  {
    printf 'decide_rows=%s\n' "$(s 'SELECT count(*) FROM decide')"
    printf 'decide_fixtures=%s\n' "$(s 'SELECT count(*) FROM decide d JOIN plan p ON p.idx = d.index_name')"
    printf 'filed_rows=%s\n' "$(s 'SELECT count(*) FROM report_filed')"
    # The view differs from the filed text in its presentation SELECT only, so
    # the two must agree on every row, and the view may hold no row the report
    # did not print.
    printf 'view_disagrees_with_filed=%s\n' \
      "$(s "SELECT count(*) FROM report_filed r JOIN decide d ON d.index_name = r.index_name
             WHERE round(100 * (d.index_size - d.est_rebuilt_bytes) / d.index_size, 1) <> r.est_pct")"
    printf 'view_rows_the_report_did_not_print=%s\n' \
      "$(s "SELECT count(*) FROM decide d WHERE NOT EXISTS
             (SELECT 1 FROM report_filed r WHERE r.index_name = d.index_name)")"
    printf 'fixtures_printed=%s of %s\n' \
      "$(s "SELECT count(*) FROM plan p JOIN report_filed r ON r.index_name = p.idx")" \
      "$(s 'SELECT count(*) FROM plan')"
    printf 'fixtures_under_1mb=%s of %s\n' \
      "$(s "SELECT count(*) FROM plan p JOIN decide d ON d.index_name = p.idx
             WHERE d.index_size < 1024 * 1024")" "$(s 'SELECT count(*) FROM plan')"
  } > "$OUT/decide17.txt"
  cat "$OUT/decide17.txt" >&2
}

# ---------------------------------------------------------------- facts -----
stage_facts() {
  say "version-local facts, refusals and page arithmetic"
  : > "$OUT/facts17.txt"
  local f="$OUT/facts17.txt"
  {
    printf 'server_version_num=%s\n' "$(s 'SHOW server_version_num')"
    printf 'block_size=%s\n' "$(s 'SHOW block_size')"
    printf 'candidates=%s\n' "$(s 'SELECT count(*) FROM decide')"
    printf 'index_size_equals_relation_size=%s of %s\n' \
      "$(s 'SELECT count(*) FROM decide f WHERE f.index_size = pg_relation_size(f.idx_oid)')" \
      "$(s 'SELECT count(*) FROM decide')"
    printf 'nan_density_indexes=%s\n' "$(s 'SELECT count(*) FROM decide WHERE leaf_pages = 0')"
    printf 'nan_float8_gt_20=%s\n' "$(s "SELECT ('NaN'::float8 > 20)::text")"
    printf 'nan_numeric_gt_20=%s\n' "$(s "SELECT ('NaN'::numeric > 20)::text")"
    printf 'dedup_fixture_present=%s\n' "$(s "SELECT (to_regclass('bl.i_dedup_off') IS NOT NULL)::text")"
  } >> "$f"

  # Every refusal the cand filters exist for.
  {
    printf 'err_hash=%s\n'      "$(err "SELECT * FROM pgstatindex('bl.s_hash'::regclass)")"
    printf 'err_gin=%s\n'       "$(err "SELECT * FROM pgstatindex('bl.s_gin'::regclass)")"
    printf 'err_gist=%s\n'      "$(err "SELECT * FROM pgstatindex('bl.s_gist'::regclass)")"
    printf 'err_spgist=%s\n'    "$(err "SELECT * FROM pgstatindex('bl.s_spgist'::regclass)")"
    printf 'err_brin=%s\n'      "$(err "SELECT * FROM pgstatindex('bl.s_brin'::regclass)")"
    printf 'err_partitioned=%s\n' "$(err "SELECT * FROM pgstatindex('bl.i_part'::regclass)")"
    printf 'err_table=%s\n'     "$(err "SELECT * FROM pgstatindex('bl.t_delhead'::regclass)")"
    printf 'err_view=%s\n'      "$(err "SELECT * FROM pgstatindex('bl.s_view'::regclass)")"
    printf 'err_sequence=%s\n'  "$(err "SELECT * FROM pgstatindex('bl.s_seq'::regclass)")"
    printf 'err_stale_oid=%s\n' "$(err "SELECT * FROM pgstatindex(2147483647::oid::regclass)")"
  } >> "$f"

  # The invalid index: an error on 17, a row on 12.
  local inv
  inv=$(err "SELECT * FROM pgstatindex('bl.i_invalid'::regclass)")
  if [ -n "$inv" ]; then
    printf 'invalid_index=refused %s\n' "$inv" >> "$f"
  else
    printf 'invalid_index=row %s\n' \
      "$(s "SELECT version || '|' || tree_level || '|' || index_size || '|' || root_block_no || '|' || internal_pages || '|' || leaf_pages || '|' || empty_pages || '|' || deleted_pages || '|' || avg_leaf_density || '|' || leaf_fragmentation FROM pgstatindex('bl.i_invalid'::regclass)")" >> "$f"
  fi

  # Fresh-build density at four fillfactors, and the reported estimate.
  printf 'fresh_builds fillfactor|target_density|avg_leaf_density|est_reclaimable_pct\n' >> "$f"
  s "SELECT f.fillfactor || '|' || round(100 * f.target_density, 2) || '|' ||
            round(f.avg_leaf_density::numeric, 2) || '|' ||
            round(100 * (f.index_size - f.est_rebuilt_bytes) / f.index_size, 1)
       FROM decide f
      WHERE f.index_name IN ('i_ff100', 'i_fresh', 'i_ff50', 'i_ff10')
      ORDER BY f.fillfactor DESC" >> "$f"

  # Leaf capacity implied by two pages of known contents.  A root leaf page
  # holding one int4 entry leaves 8192 - 16 special - 24 header - 16 tuple
  # - 4 line pointer = 8128 free; an empty leaf page leaves 8148.
  printf 'implied_max_avail one_tuple|empty_leaf\n' >> "$f"
  s "SELECT round(8128 / (1 - one.d / 100)::numeric, 1) || '|' ||
            round(8148 / (1 - zero.d / 100)::numeric, 1)
       FROM (SELECT avg_leaf_density::numeric AS d FROM pgstatindex('bl.c_one_idx'::regclass)) one,
            (SELECT avg_leaf_density::numeric AS d FROM pgstatindex('bl.c_zero_idx'::regclass)) zero" >> "$f"
  printf 'known_page_densities one|zero\n' >> "$f"
  s "SELECT (SELECT round(avg_leaf_density::numeric, 2) FROM pgstatindex('bl.c_one_idx'::regclass)) || '|' ||
            (SELECT round(avg_leaf_density::numeric, 2) FROM pgstatindex('bl.c_zero_idx'::regclass))" >> "$f"

  # VACUUM does not give index pages back; REINDEX does.
  printf 'delhead_after_vacuum=%s dead_pages=%s\n' \
    "$(s "SELECT index_size FROM pgstatindex('bl.i_delhead'::regclass)")" \
    "$(s "SELECT empty_pages + deleted_pages FROM pgstatindex('bl.i_delhead'::regclass)")" >> "$f"

  # The guard fixtures the page reads as rows: the four fillfactor fixtures,
  # the dead-page fixture, the two duplicate builds and the deduplication shape.
  printf 'guard_rows index|size|leaf|dead|density|wasted_ff_pct|est_pct|notes\n' >> "$f"
  s "SELECT f.index_name || '|' || pg_size_pretty(f.index_size) || '|' || f.leaf_pages || '|' ||
            f.dead_pages || '|' ||
            coalesce(round(f.avg_leaf_density::numeric, 2)::text, 'NaN') || '|' ||
            round(100 * f.wasted_vs_fillfactor / f.index_size, 1) || '|' ||
            round(100 * (f.index_size - f.est_rebuilt_bytes) / f.index_size, 1) || '|' ||
            coalesce((SELECT r.notes FROM report_filed r WHERE r.index_name = f.index_name), '(not printed)')
       FROM decide f WHERE f.schema_name = 'bl' ORDER BY f.index_name" >> "$f"

  # Another session's temp index, called directly and left to the statement's
  # own candidate filter.  Each -c is its own transaction, so the temp relation
  # is committed and visible to this session while the sleeping one owns it.
  "$BIN/psql" -X -q -d "$DB" \
    -c "CREATE TEMP TABLE tmp_other(id int)" \
    -c "INSERT INTO tmp_other SELECT g FROM generate_series(1, 300000) g" \
    -c "CREATE INDEX tmp_other_idx ON tmp_other(id)" \
    -c "SELECT pg_sleep(25)" > /dev/null 2>&1 &
  local other=$!
  sleep 8
  {
    printf 'other_temp_error=%s\n' \
      "$(err "SELECT * FROM pgstatindex((SELECT c.oid FROM pg_class c WHERE c.relname = 'tmp_other_idx' AND c.relkind = 'i' LIMIT 1)::regclass)")"
    printf 'other_temp_index_size=%s\n' \
      "$(s "SELECT coalesce(pg_size_pretty(max(pg_relation_size(c.oid))), 'none')
              FROM pg_class c WHERE c.relname = 'tmp_other_idx' AND c.relkind = 'i'")"
    printf 'report_rows_with_other_session=%s\n' \
      "$(( $("$BIN/psql" -X -q -A -F '|' -P footer=off -v ON_ERROR_STOP=1 -d "$DB" -f "$SQLD/report.sql" 2>/dev/null | grep -c '^') - 1 ))"
  } >> "$f"
  wait "$other" 2>/dev/null
  cat "$f" >&2
}

# ----------------------------------------------------------------- cost -----
stage_cost() {
  say "what the statement costs to run"
  : > "$OUT/cost17.txt"
  local f="$OUT/cost17.txt"
  printf 'population %s\n' \
    "$(s "SELECT count(*) || ' B-tree indexes over ' ||
                 sum(pg_relation_size(c.oid)) / current_setting('block_size')::int ||
                 ' blocks, database ' || pg_size_pretty(pg_database_size(current_database()))
            FROM pg_class c JOIN pg_am a ON a.oid = c.relam
           WHERE a.amname = 'btree' AND c.relkind = 'i'")" >> "$f"
  printf 'EXPLAIN (ANALYZE, BUFFERS) of the filed text\n' >> "$f"
  # plan_lines counts only what the EXPLAIN printed, not the lines above it.
  local p0
  p0=$(grep -c '^' "$f")
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" \
    -c "SET statement_timeout = '15min'; SET lock_timeout = '5s';" \
    -c "EXPLAIN (ANALYZE, BUFFERS) $(cat "$SQLD/bare.sql")" >> "$f" 2>&1
  printf 'plan_lines=%s\n' "$(( $(grep -c '^' "$f") - p0 ))" >> "$f"
  printf 'cte_scans=%s\n' "$(grep -c 'CTE Scan' "$f")" >> "$f"
  local i a b
  # The superseded text is timed exactly as it was filed, so it still
  # prefilters at 1 MB and reads fewer indexes than the filed text does; the
  # two timings are for different populations, and the page says so.  A run
  # that fails is marked rather than timed as if it had succeeded.
  printf 'six interleaved end-to-end runs, filed text then superseded text (ms)\n' >> "$f"
  for i in 1 2 3 4 5 6; do
    a=$(date +%s%N)
    "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -o /dev/null -d "$DB" -f "$SQLD/report.sql" > /dev/null 2>&1 \
      || printf 'filed_run_failed ' >> "$f"
    b=$(date +%s%N)
    printf 'filed=%s.%s ' $(( (b - a) / 1000000 )) $(( ((b - a) / 100000) % 10 )) >> "$f"
    if [ -f "$SQLD/prev_bare.sql" ]; then
      a=$(date +%s%N)
      "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -o /dev/null -d "$DB" -f "$SQLD/prev.sql" > /dev/null 2>&1 \
        || printf 'prev_run_failed ' >> "$f"
      b=$(date +%s%N)
      printf 'prev=%s.%s' $(( (b - a) / 1000000 )) $(( ((b - a) / 100000) % 10 )) >> "$f"
    fi
    printf '\n' >> "$f"
  done
  grep -E 'population|Execution Time|plan_lines|cte_scans|filed=|Buffers: shared' "$f" | head -20 >&2
}

# ----------------------------------------------------------------- priv -----
stage_priv() {
  say "who may run it"
  : > "$OUT/priv17.txt"
  local f="$OUT/priv17.txt"
  q "DROP ROLE IF EXISTS mon; DROP ROLE IF EXISTS nomon;
     CREATE ROLE mon LOGIN; CREATE ROLE nomon LOGIN;
     GRANT pg_stat_scan_tables TO mon;" > /dev/null 2>&1 || die "role setup failed"
  # The statement passes an OID column cast to regclass, which resolves no
  # name.  Writing 'bl.i_delhead'::regclass in a test would resolve one, so the
  # OID is read here, as a number, and substituted.
  local oid
  oid=$(s "SELECT 'bl.i_delhead'::regclass::oid")
  {
    printf 'index_oid=%s\n' "$oid"
    printf 'mon_schema_usage=%s\n' \
      "$(s "SELECT has_schema_privilege('mon', 'bl', 'USAGE')::text")"
    printf 'mon_rows_from_statement=%s\n' \
      "$("$BIN/psql" -X -At -q -U mon -d "$DB" -f "$SQLD/report.sql" 2>&1 | grep -c '|')"
    printf 'mon_by_name=%s\n' \
      "$("$BIN/psql" -X -At -q -U mon -d "$DB" -c "SELECT * FROM pgstatindex('bl.i_delhead')" 2>&1 | grep -E '^(ERROR|FATAL)' | head -1)"
    printf 'mon_by_oid_leaf_pages=%s\n' \
      "$("$BIN/psql" -X -At -q -U mon -d "$DB" -c "SELECT leaf_pages FROM pgstatindex($oid::regclass)" 2>&1 | head -1)"
    printf 'nomon_by_oid=%s\n' \
      "$("$BIN/psql" -X -At -q -U nomon -d "$DB" -c "SELECT leaf_pages FROM pgstatindex($oid::regclass)" 2>&1 | head -1)"
  } >> "$f"
  q "DROP ROLE IF EXISTS mon; DROP ROLE IF EXISTS nomon;" > /dev/null
  cat "$f" >&2
}

# -------------------------------------------------------------- compare -----
# The two Follow-up sections on this page compare the filed text with the two
# texts it superseded: the alert_pct/status text and the perfect-packing
# wasted_space text.  This stage re-derives those comparisons on the population
# this run built, so nothing on the page rests on a fixture set that no longer
# exists.  Three questions per pair - what each text prints, which columns its
# internal `final` stage exposes, and whether EXCEPT in both directions over
# the shared columns returns a row - plus the two properties the fillfactor
# rebase is supposed to have: the new column never exceeds the old one and is
# never negative.
# The texts are compared as views inside one query rather than materialized
# one after another, so both sides read the same database state.  Materializing
# them in turn does not work: each pass creates and drops a relation, which
# grows the catalog's own indexes, and those are candidates too - that alone
# produced 29 and 30 differing rows in this stage's first draft.  The price is
# that every comparison reads every page of every index twice.
# Must precede score, which rebuilds every scored index.
stage_compare() {
  say "the filed text against the two texts it superseded"
  [ -f "$SQLD/report.sql" ] || die "run the texts stage first"
  # 17 or 12, taken from this leg's own data directory.
  local leg=${DATA##*/data}
  local f="$OUT/compare$leg.txt"; : > "$f"
  local t src
  for t in now prev alert; do
    case $t in now) src="$SQLD/report.sql" ;; *) src="$SQLD/$t.sql" ;; esac
    [ -f "$src" ] || { note "no $t text; its comparison is skipped"; continue; }
    gen_view "cmp_$t" < "$src" > "$SQLD/cmp_$t.sql"
    fl "$SQLD/cmp_$t.sql" > /dev/null || die "cmp_$t view failed"
    "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -P footer=off -A -F '|' \
      -d "$DB" -f "$src" > "$SQLD/out_$t.txt" 2>&1 || die "the $t text did not run"
    {
      printf '%s_rows=%s\n' "$t" "$(( $(grep -c '^' "$SQLD/out_$t.txt") - 1 ))"
      printf '%s_columns=%s\n' "$t" "$(head -1 "$SQLD/out_$t.txt" | tr '|' '\n' | grep -c '^')"
      printf '%s_bytes=%s\n' "$t" "$(wc -c < "$SQLD/out_$t.txt")"
      printf '%s_final_columns=%s\n' "$t" \
        "$(s "SELECT count(*) FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'cmp_$t'")"
    } >> "$f"
  done

  # The alert text's own verdict column, which is the thing that was removed.
  if [ -f "$SQLD/out_alert.txt" ] && [ -f "$SQLD/out_prev.txt" ]; then
    # Field 14 is status and field 15 is notes, so cutting field 14 is what
    # makes the alert output comparable with the text that dropped the column.
    cut -d'|' -f1-13,15 "$SQLD/out_alert.txt" > "$SQLD/out_alert_cut.txt"
    {
      printf 'alert_status_rebuild_candidate=%s\n' \
        "$(cut -d'|' -f14 "$SQLD/out_alert.txt" | grep -c '^rebuild candidate$')"
      printf 'alert_status_ok=%s\n' "$(cut -d'|' -f14 "$SQLD/out_alert.txt" | grep -c '^ok$')"
      printf 'alert_cut_14_sha256=%s bytes=%s\n' \
        "$(sha256sum < "$SQLD/out_alert_cut.txt" | cut -c1-16)" \
        "$(wc -c < "$SQLD/out_alert_cut.txt")"
      printf 'prev_sha256=%s bytes=%s\n' \
        "$(sha256sum < "$SQLD/out_prev.txt" | cut -c1-16)" \
        "$(wc -c < "$SQLD/out_prev.txt")"
    } >> "$f"
  fi

  # The fillfactor rebase moved presentation fields 9 and 10 and nothing else,
  # so the other twelve are compared with those two cut out of both texts.
  # The superseded text prefiltered at 1 MB and the filed text prefilters
  # nothing, so the two outputs are compared as sets rather than byte for byte:
  # every row the older text printed must appear unchanged in the filed output,
  # and the rows only the filed text prints are the ones that prefilter hid.
  if [ -f "$SQLD/out_prev.txt" ]; then
    cut -d'|' -f1-8,11-14 "$SQLD/out_prev.txt" | sort > "$SQLD/out_prev_untouched.txt"
    cut -d'|' -f1-8,11-14 "$SQLD/out_now.txt"  | sort > "$SQLD/out_now_untouched.txt"
    {
      printf 'prev_untouched_12_rows=%s sha256=%s\n' \
        "$(grep -c '^' "$SQLD/out_prev_untouched.txt")" \
        "$(sha256sum < "$SQLD/out_prev_untouched.txt" | cut -c1-16)"
      printf 'now_untouched_12_rows=%s sha256=%s\n' \
        "$(grep -c '^' "$SQLD/out_now_untouched.txt")" \
        "$(sha256sum < "$SQLD/out_now_untouched.txt" | cut -c1-16)"
      printf 'prev_rows_missing_from_now=%s\n' \
        "$(comm -23 "$SQLD/out_prev_untouched.txt" "$SQLD/out_now_untouched.txt" | grep -c '^')"
      printf 'rows_only_now_prints=%s\n' \
        "$(comm -13 "$SQLD/out_prev_untouched.txt" "$SQLD/out_now_untouched.txt" | grep -c '^')"
    } >> "$f"
  fi

  cmp_pair alert prev >> "$f"
  cmp_pair prev  now  >> "$f"

  # What the fillfactor rebase is supposed to guarantee, over every index in
  # the database, which since the size prefilter went is also every row the
  # report prints.  One query per question, so both texts read one state.
  if [ -n "$(s "SELECT to_regclass('cmp_prev') IS NOT NULL OR NULL")" ]; then
    {
      printf 'indexes_compared=%s\n' "$(s 'SELECT count(*) FROM cmp_now')"
      printf 'now_wasted_exceeds_prev=%s\n' \
        "$(s "SELECT count(*) FROM cmp_now n JOIN cmp_prev p ON p.idx_oid = n.idx_oid
               WHERE n.wasted_vs_fillfactor > p.wasted_space")"
      printf 'now_wasted_negative=%s\n' \
        "$(s 'SELECT count(*) FROM cmp_now WHERE wasted_vs_fillfactor < 0')"
      printf 'two_definitions_equal=%s\n' \
        "$(s "SELECT count(*) FROM cmp_now n JOIN cmp_prev p ON p.idx_oid = n.idx_oid
               WHERE n.wasted_vs_fillfactor = p.wasted_space")"
      printf 'leaf_term_clamped_to_zero=%s\n' \
        "$(s "SELECT count(*) FROM cmp_now
               WHERE round(leaf_bytes * target_density) - live_leaf_bytes < 0")"
      printf 'reported_rows_clamped=%s\n' \
        "$(s "SELECT count(*) FROM cmp_now c JOIN report_filed r ON r.index_name = c.index_name
               WHERE round(c.leaf_bytes * c.target_density) - c.live_leaf_bytes < 0")"
    } >> "$f"
  fi
  cat "$f" >&2
}

# cmp_pair <a> <b>: the internal `final` stage of one text against another -
# the columns only one of them exposes, and EXCEPT in both directions over
# every column both expose, evaluated in one query so that both texts read the
# same index state.  A one-for-one column swap and 0 differing rows is what
# "nothing else the statement returns moved" means.
cmp_pair() {
  local a=$1 b=$2 cols
  [ -n "$(s "SELECT to_regclass('cmp_$a') IS NOT NULL OR NULL")" ] || return 0
  [ -n "$(s "SELECT to_regclass('cmp_$b') IS NOT NULL OR NULL")" ] || return 0
  printf '%s_vs_%s only_in_%s=%s\n' "$a" "$b" "$a" \
    "$(s "SELECT coalesce(string_agg(column_name, ','), 'none') FROM (
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'cmp_$a'
            EXCEPT
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'cmp_$b') x")"
  printf '%s_vs_%s only_in_%s=%s\n' "$a" "$b" "$b" \
    "$(s "SELECT coalesce(string_agg(column_name, ','), 'none') FROM (
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'cmp_$b'
            EXCEPT
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'cmp_$a') x")"
  cols=$(s "SELECT string_agg(quote_ident(column_name), ', ' ORDER BY column_name) FROM (
              SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'cmp_$a'
              INTERSECT
              SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'cmp_$b') x")
  printf '%s_vs_%s shared_columns=%s except_both_ways=%s\n' "$a" "$b" \
    "$(s "SELECT count(*) FROM information_schema.columns c
           WHERE c.table_schema = 'public' AND c.table_name = 'cmp_$a'
             AND c.column_name IN (SELECT column_name FROM information_schema.columns
                                    WHERE table_schema = 'public'
                                      AND table_name = 'cmp_$b')")" \
    "$(s "SELECT (SELECT count(*) FROM (SELECT $cols FROM cmp_$a
                                        EXCEPT SELECT $cols FROM cmp_$b) u)
               + (SELECT count(*) FROM (SELECT $cols FROM cmp_$b
                                        EXCEPT SELECT $cols FROM cmp_$a) v)")"
}

# ---------------------------------------------------------------- score -----
# Phase 5: the oracle.  score_all() reads what the statement said about each
# churned fixture, calls pgstatindex itself, rebuilds the index and measures the
# file again; the verdicts view then applies the shared suite's four bands.
# DESTRUCTIVE: it rebuilds every scored index, so report, decide, facts, cost,
# priv and compare must all precede it.
stage_score() {
  say "score every fixture against a measured REINDEX INDEX"
  [ -n "$(s 'SELECT 1 FROM decide LIMIT 1')" ] || die "run the decide stage first"
  fl /dev/stdin <<'SQL' || die "scoring failed"
SET /* wiki_pgsi_score_statement_timeout */ statement_timeout = '900s';
SET /* wiki_pgsi_score_lock_timeout */ lock_timeout = '5s';
CALL /* wiki_pgsi_score_all */ score_all();
SQL
  local out="$OUT/verdicts17.txt"
  t "SELECT /* wiki_pgsi_verdict_rows */ num, leg, grp, idx, blocks_built,
            blocks_before, blocks_after, actual, est_pct, wasted_ff_pct,
            density, dead_pages, reported, taken_stage, taken_nofilter,
            expected_stage, want_stage, verdict, verdict_nofilter, lost_by, notes
       FROM verdicts ORDER BY num, leg" > "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_family_counts */ grp, verdict, count(*)
       FROM verdicts GROUP BY 1, 2 ORDER BY 1, 2" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_totals */ verdict, count(*)
       FROM verdicts GROUP BY 1 ORDER BY 2 DESC" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_totals_nofilter */ verdict_nofilter, count(*)
       FROM verdicts GROUP BY 1 ORDER BY 2 DESC" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_agreement */
            count(*) AS fixtures,
            count(*) FILTER (WHERE reported)                          AS reported,
            count(*) FILTER (WHERE taken_stage = 'rebuild')           AS rebuilt,
            count(*) FILTER (WHERE taken_nofilter = 'rebuild')        AS rebuilt_nofilter,
            count(*) FILTER (WHERE expected_stage = taken_nofilter)   AS instrument_agrees,
            count(*) FILTER (WHERE expected_stage <> taken_nofilter)  AS instrument_disagrees,
            count(*) FILTER (WHERE want_stage = taken_nofilter)       AS want_hit,
            count(*) FILTER (WHERE want_stage <> taken_nofilter)      AS want_miss,
            count(*) FILTER (WHERE NOT contract_ok)                   AS contract_failures,
            count(*) FILTER (WHERE NOT view_matches_report)           AS view_report_mismatch
       FROM verdicts" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_lost */ num, leg, idx, lost_by, est_pct, actual,
            density, dead_pages, blocks_before
       FROM verdicts WHERE lost_by IS NOT NULL ORDER BY num, leg" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_false_positives */ num, leg, idx, est_pct, actual,
            density, dead_pages, notes
       FROM verdicts WHERE verdict LIKE '%FALSE POSITIVE' ORDER BY num, leg" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_want_miss */ num, leg, idx, want_stage,
            taken_nofilter, taken_stage, verdict, est_pct, actual
       FROM verdicts WHERE want_stage <> taken_nofilter ORDER BY num, leg" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_rebuild_returns */
            count(*) AS rebuild_decisions,
            round(avg(actual), 1) AS mean_actual,
            min(actual) AS min_actual, max(actual) AS max_actual
       FROM verdicts WHERE taken_stage = 'rebuild'" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_error */
            count(*) AS scored,
            count(*) FILTER (WHERE abs(est_pct - actual) <= 1.0) AS within_1_point,
            count(*) FILTER (WHERE abs(est_pct - actual) <= 5.0) AS within_5_points,
            round(max(est_pct - actual), 1) AS worst_over,
            round(min(est_pct - actual), 1) AS worst_under
       FROM verdicts" >> "$out" 2>&1
  # Rule 2's post-churn shape, per fixture and in total: the distribution the
  # drain actually produced, and the fixtures predicted reclaimable whose
  # space never arrived in the file.
  t "SELECT /* wiki_pgsi_verdict_shape */ shape, want_stage, count(*)
       FROM verdicts GROUP BY 1, 2 ORDER BY 1, 2" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_shape_failed */ num, leg, idx, shape, density,
            dead_pages, est_pct, actual
       FROM verdicts WHERE shape_ok IS FALSE ORDER BY num, leg" >> "$out" 2>&1
  # The no-defeat rule's proofs, per fixture rather than per statement: the
  # page classes the maintenance left on this fixture's index, beside the
  # verdict it earned.  pageclass is read before the report, decide and oracle
  # passes, so these are the classes the statement was asked about.
  t "SELECT /* wiki_pgsi_verdict_maintenance */ v.num, v.leg, v.idx, v.verdict,
            pc.leaf_pages AS leaf_after_maint, pc.deleted_pages, pc.empty_pages,
            pc.avg_leaf_density AS density_after_maint, v.actual
       FROM verdicts v LEFT JOIN pageclass pc ON pc.idx = v.idx
      ORDER BY v.num, v.leg" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_maintenance_totals */
            count(*) AS fixtures,
            count(*) FILTER (WHERE pc.idx IS NULL) AS without_page_classes,
            count(*) FILTER (WHERE pc.deleted_pages > 0) AS with_deleted_pages,
            coalesce(sum(pc.deleted_pages), 0) AS deleted_pages_total
       FROM verdicts v LEFT JOIN pageclass pc ON pc.idx = v.idx" >> "$out" 2>&1
  note "$(s "SELECT count(*) || ' scored, ' ||
              count(*) FILTER (WHERE verdict = 'PASS') || ' PASS, ' ||
              count(*) FILTER (WHERE verdict = 'CRITICAL FALSE POSITIVE') || ' CFP, ' ||
              count(*) FILTER (WHERE verdict = 'FALSE POSITIVE') || ' FP, ' ||
              count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE') || ' FN'
                FROM verdicts")"
  tail -40 "$out" >&2
}

# ---------------------------------------------------------------- guard -----
# The guard and model fixtures get the same oracle the suite fixtures get, so
# that every number this page reports about them is measured and not modelled:
# one REINDEX INDEX per index in schema bl, the file measured before and after,
# and the statement re-read afterwards for the post-rebuild residual.  No
# verdict band is applied here, because these are not suite fixtures.
# DESTRUCTIVE: it rebuilds every index in schema bl.
stage_guard() {
  say "oracle pass over the bl guard and model fixtures"
  [ -n "$(s "SELECT 1 FROM decide WHERE schema_name = 'bl' LIMIT 1")" ] \
    || die "run the decide stage first"
  q "DROP TABLE IF EXISTS guard;
     CREATE TABLE guard AS
       SELECT /* wiki_pgsi_guard_before */
              d.index_name, d.idx_oid, d.index_size, d.leaf_pages, d.dead_pages,
              d.avg_leaf_density AS density, d.fillfactor,
              round(100 * d.target_density, 2) AS target_density,
              round(100 * d.wasted_vs_fillfactor / d.index_size, 1) AS wasted_ff_pct,
              round(100 * (d.index_size - d.est_rebuilt_bytes) / d.index_size, 1) AS est_pct,
              pg_relation_size(d.idx_oid) AS before_bytes,
              0::bigint AS after_bytes, 0::numeric AS residual_pct
         FROM decide d WHERE d.schema_name = 'bl';" > /dev/null \
    || die "guard snapshot failed"
  s "SELECT /* wiki_pgsi_guard_generator */ 'REINDEX /* wiki_pgsi_guard_reindex */ INDEX bl.' || quote_ident(index_name) || ';'
       FROM guard ORDER BY index_name" > "$SQLD/guard_reindex.sql"
  fl "$SQLD/guard_reindex.sql" > /dev/null || die "guard REINDEX pass failed"
  q "UPDATE /* wiki_pgsi_guard_after */ guard g SET after_bytes = pg_relation_size(g.idx_oid);
     UPDATE /* wiki_pgsi_guard_residual */ guard g SET residual_pct = r.pct
       FROM (SELECT f.index_name,
                    round(100 * f.wasted_vs_fillfactor / f.index_size, 1) AS pct
               FROM bloat_final f WHERE f.schema_name = 'bl') r
      WHERE r.index_name = g.index_name;" > /dev/null || die "guard after-pass failed"
  t "SELECT /* wiki_pgsi_guard_rows */ index_name, pg_size_pretty(index_size) AS size,
            leaf_pages, dead_pages, round(density::numeric, 2) AS density,
            fillfactor, target_density, wasted_ff_pct, est_pct,
            round(100 * (before_bytes - after_bytes)::numeric
                  / greatest(before_bytes, 1), 1) AS actual_pct,
            residual_pct, before_bytes, after_bytes
       FROM guard ORDER BY index_name" > "$OUT/guard17.txt" 2>&1
  t "SELECT /* wiki_pgsi_guard_error */ count(*) AS guard_indexes,
            count(*) FILTER (WHERE abs(est_pct - round(100 * (before_bytes - after_bytes)::numeric
                                        / greatest(before_bytes, 1), 1)) <= 1.0) AS within_1_point,
            round(max(est_pct - round(100 * (before_bytes - after_bytes)::numeric
                                      / greatest(before_bytes, 1), 1)), 1) AS worst_over,
            round(min(est_pct - round(100 * (before_bytes - after_bytes)::numeric
                                      / greatest(before_bytes, 1), 1)), 1) AS worst_under
       FROM guard" >> "$OUT/guard17.txt" 2>&1
  cat "$OUT/guard17.txt" >&2
}

# ------------------------------------------------------------- residual -----
# A rebuilt index must report no waste at its own fillfactor.  Reads exactly
# the population the score stage rebuilt.
stage_residual() {
  say "post-REINDEX residual of wasted_vs_fillfactor"
  [ -n "$(s 'SELECT 1 FROM res LIMIT 1')" ] || die "run the score stage first"
  q "DROP TABLE IF EXISTS residual;
     CREATE TABLE residual AS
       SELECT /* wiki_pgsi_residual */
              f.index_name, f.index_size, f.leaf_pages, f.avg_leaf_density,
              f.wasted_vs_fillfactor AS residual_bytes,
              round(100 * f.wasted_vs_fillfactor / f.index_size, 1) AS residual_pct,
              round(100 * (f.index_size - f.est_rebuilt_bytes) / f.index_size, 1) AS est_pct
         FROM bloat_final f
        WHERE f.index_name IN (SELECT idx FROM plan);" > /dev/null \
    || die "residual pass failed"
  {
    t "SELECT /* wiki_pgsi_residual_totals */
              count(*) AS rebuilt_indexes,
              count(*) FILTER (WHERE residual_bytes = 0) AS exactly_zero,
              count(*) FILTER (WHERE residual_pct <= 0.1) AS at_or_below_0_1pct,
              max(residual_pct) AS worst_residual_pct,
              max(est_pct) AS worst_est_pct
         FROM residual"
    t "SELECT /* wiki_pgsi_residual_worst */ index_name, index_size, leaf_pages,
              round(avg_leaf_density::numeric, 2) AS density, residual_bytes, residual_pct
         FROM residual ORDER BY residual_pct DESC, index_name LIMIT 8"
    t "SELECT /* wiki_pgsi_residual_over_1mb */
              count(*) AS at_or_above_1mb,
              max(residual_pct) AS worst_residual_pct
         FROM residual WHERE index_size >= 1024 * 1024"
  } > "$OUT/residual17.txt" 2>&1
  cat "$OUT/residual17.txt" >&2
}

# ----------------------------------------------------------------- race -----
# Two shapes of interference, both driven from a second session:
#   lock_timeout   an uncommitted DROP INDEX holds AccessExclusiveLock and the
#                  call is cancelled at the timeout
#   committed drop the same drop commits while the report waits, so
#                  relation_open finds nothing behind the lock
stage_race() {
  say "locking and the concurrent-drop race"
  : > "$OUT/race17.txt"
  local f="$OUT/race17.txt" a b msg
  "$BIN/psql" -X -q -d "$DB" -c \
    "BEGIN; DROP INDEX bl.i_race; SELECT pg_sleep(8); ROLLBACK;" > /dev/null 2>&1 &
  local holder=$!
  sleep 2
  a=$(date +%s%N)
  msg=$(err "SET lock_timeout = '2s'; SELECT * FROM pgstatindex('bl.i_race'::regclass)")
  b=$(date +%s%N)
  printf 'lock_timeout_error=%s\n' "$msg" >> "$f"
  printf 'lock_timeout_ms=%s.%s\n' $(( (b - a) / 1000000 )) $(( ((b - a) / 100000) % 10 )) >> "$f"
  wait "$holder" 2>/dev/null

  # Case 1: the drop commits while cand is still being materialized.  cand no
  # longer opens any relation - the size prefilter that used to absorb such a
  # drop through pg_relation_size's try_relation_open is gone - so the dropped
  # index stays in the candidate list and pgstatindex's own relation_open
  # decides the outcome.  Whatever happens is recorded, error or not.
  local before after defn
  defn=$(s "SELECT pg_get_indexdef('bl.i_race'::regclass)")
  before=$(( $("$BIN/psql" -X -q -A -F '|' -P footer=off -d "$DB" -f "$SQLD/report.sql" 2>/dev/null | grep -c '^') - 1 ))
  "$BIN/psql" -X -q -d "$DB" -c \
    "BEGIN; DROP INDEX bl.i_race; SELECT pg_sleep(3); COMMIT;" > /dev/null 2>&1 &
  local dropper=$!
  sleep 1
  a=$(date +%s%N)
  # psql prefixes an error from -f with "psql:<file>:<line>: ", so the match
  # cannot be anchored at the start of the line; the prefix is then cut.
  "$BIN/psql" -X -q -A -F '|' -P footer=off -d "$DB" -f "$SQLD/report.sql" \
    > "$OUT/race_during17.txt" 2>&1
  b=$(date +%s%N)
  wait "$dropper" 2>/dev/null
  msg=$(grep -E '(ERROR|FATAL):' "$OUT/race_during17.txt" | head -1 | sed 's/^psql:[^ ]* //')
  after=$(( $(grep -c '^' "$OUT/race_during17.txt") - 1 ))
  printf 'drop_during_cand_error=%s\n' "${msg:-none}" >> "$f"
  printf 'drop_during_cand_rows=%s (was %s)\n' "$after" "$before" >> "$f"
  printf 'drop_during_cand_ms=%s\n' $(( (b - a) / 1000000 )) >> "$f"
  q "$defn" > /dev/null 2>&1

  # Case 2: the drop lands after cand has been materialized but before
  # pgstatindex reaches that index.  Without a size check the window is the
  # whole report rather than the gap between two calls on one index, so the
  # same sweep of delays is run and whatever it lands in is recorded.
  local target d attempts=0 hit=
  target=i_race
  printf 'drop_after_cand_target=%s\n' "$target" >> "$f"
  for d in 0.005 0.02 0.05 0.1 0.2 0.4 0.8 1.2 1.6 2.0; do
    a=$(date +%s%N)
    "$BIN/psql" -X -q -d "$DB" \
      -c "SELECT pg_sleep($d)" \
      -c "BEGIN; DROP INDEX bl.$target; SELECT pg_sleep(2); COMMIT;" > /dev/null 2>&1 &
    local dp=$!
    "$BIN/psql" -X -q -d "$DB" -f "$SQLD/report.sql" > "$OUT/race_after17.txt" 2>&1
    b=$(date +%s%N)
    wait "$dp" 2>/dev/null
    attempts=$((attempts + 1))
    msg=$(grep -E '(ERROR|FATAL):' "$OUT/race_after17.txt" | head -1 | sed 's/^psql:[^ ]* //')
    q "$defn" > /dev/null 2>&1
    case $msg in
      *"could not open relation"*)
        hit="$msg after $(( (b - a) / 1000000 )) ms, drop taken ${d}s in"; break ;;
    esac
  done
  printf 'drop_after_cand_error=%s\n' "${hit:-not reproduced in $attempts attempts}" >> "$f"
  printf 'drop_after_cand_attempts=%s\n' "$attempts" >> "$f"
  cat "$f" >&2
}

# --------------------------------------------------------------- errors -----
# Every server-side error this run provokes is deliberate: the ten refusals and
# the privilege checks of the facts and priv stages, the lock timeout and the
# concurrent drop of the race stage, and - on a server that lacks a feature -
# the fixture builds the suite records as skips.  This stage counts what the
# server logged after the run mark and prints the distinct messages, so an
# error no stage asked for is visible.
stage_errors() {
  say "server-error audit"
  local log="$OUT/server17.log" from
  [ -f "$log" ] || { note "no server log"; return 0; }
  # From the last run mark only, so a re-run in the same cluster does not
  # inherit the errors of the run before it.
  from=$(grep -n 'wiki_pgsi_run_mark' "$log" | tail -1 | cut -d: -f1)
  if [ -n "${from:-}" ]; then
    sed -n "${from},\$p" "$log" > "$OUT/log_since_mark17.txt"
  else
    cp "$log" "$OUT/log_since_mark17.txt"
  fi
  {
    printf 'errors_logged=%s\n' "$(grep -c 'ERROR:' "$OUT/log_since_mark17.txt")"
    printf 'fatals_logged=%s\n' "$(grep -c 'FATAL:' "$OUT/log_since_mark17.txt")"
    printf -- '-- distinct messages\n'
    grep -oE '(ERROR|FATAL):.*' "$OUT/log_since_mark17.txt" | sort | uniq -c | sort -rn
  } > "$OUT/errors17.txt"
  cat "$OUT/errors17.txt" >&2
}

# -------------------------------------------------------------- summary -----
stage_summary() {
  say "what landed in $OUT"
  ls -la "$OUT" >&2
  local x
  for x in platform17 exact17 decide17 maint_proofs17 facts17 cost17 priv17 compare17 race17 errors17 skipped17; do
    [ -f "$OUT/$x.txt" ] && { printf '\n---- %s\n' "$x" >&2; cat "$OUT/$x.txt" >&2; }
  done
  [ -f "$OUT/verdicts17.txt" ] && { printf '\n---- verdicts17 (tail)\n' >&2; tail -40 "$OUT/verdicts17.txt" >&2; }
  [ -f "$OUT/residual17.txt" ] && { printf '\n---- residual17\n' >&2; cat "$OUT/residual17.txt" >&2; }
}

# ---------------------------------------------------------------- stop -------
stage_stop() {
  say "stop the 17 cluster"
  [ -d "$DATA" ] || { note "no data directory"; return 0; }
  if "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1 || die "pg_ctl stop failed"
  fi
  [ -f "$DATA/postmaster.pid" ] && die "postmaster.pid still present in $DATA"
  pgrep -f "postgres.*-D $DATA" > /dev/null 2>&1 && die "a postgres process still runs on $DATA"
  [ -n "$(ls -A "$SOCK" 2>/dev/null)" ] && die "socket directory $SOCK is not empty"
  note "stopped: no postmaster.pid, no process, empty socket directory"
}

stage_clean() {
  stage_stop || exit 1
  case "$SANDBOX" in
    "$WIKI_ROOT"/.wiki-runtime/tmp/?*) ;;
    *) die "refusing to delete $SANDBOX: not under $WIKI_ROOT/.wiki-runtime/tmp/" ;;
  esac
  say "delete $SANDBOX"
  rm -rf "$SANDBOX"
}

# ------------------------------------------------------------ dispatcher -----
STAGES_DEFAULT="build check cluster texts fixtures suite churn report decide facts cost priv compare score guard residual race errors summary"
run_stage() {
  case "$1" in
    build|check|cluster|texts|fixtures|suite|churn|report|decide|facts|cost|priv|compare|score|guard|residual|race|errors|summary|stop|clean)
      "stage_$1" ;;
    *) die "unknown stage: $1" ;;
  esac
}
main() {
  local st
  if [ "$#" -eq 0 ]; then set -- $STAGES_DEFAULT; fi
  # One run mark per invocation, so the error audit reads this invocation's
  # errors and not an earlier one's.  On a first run the log does not exist
  # yet and the cluster stage writes the mark instead.
  [ -f "$OUT/server17.log" ] \
    && printf -- '-- wiki_pgsi_run_mark %s\n' "$(date -u +%FT%TZ)" >> "$OUT/server17.log"
  for st in "$@"; do run_stage "$st" || die "stage $st failed"; done
  say "done: $*"
}
main "$@"
```

### The PostgreSQL 12 leg script

```sh
#!/usr/bin/env bash
#
# bloat_pgstatindex_v12.sh - the PostgreSQL 12 leg of the measurement behind
# "B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and
# 17".  Bash and SQL only: build the pinned 12 checkout out of tree, run its
# regression suites, start an isolated cluster, build the wiki's shared
# mandatory B-tree bloat suite from the same page blocks the 17 leg reads, run
# this page's statement exactly as filed, and score every fixture against a
# measured REINDEX INDEX.
#
# It answers three questions the 17 leg cannot: does the exact filed text
# still run unmodified on the oldest major this page claims, which fixtures of
# the shared suite can a 12.2 server not build at all, and - in its crossleg
# stage - how do the two majors' reports differ row by row?  Nothing here assumes
# what PostgreSQL 12 does: every fixture that needs a feature is attempted, and
# the server's own refusal is recorded as a skip.
#
# The scored fixtures are the shared suite's, not this page's own.  Its six
# families, its five phases (build, baseline, churn, decide, oracle), its
# maintenance assumption, its rule that the maintenance must not be defeated,
# its three porting rules, its REINDEX INDEX oracle and its four verdict bands
# are defined once, in the wiki's common concept page "Mandatory B-Tree Bloat
# Tests"; nothing here redefines them, and every deviation is named on the
# page.  The fixture text, the harness and the churn phase are filed as sql
# blocks 2 to 6 of the same page and are read out of it at run time, so both
# legs run the same suite.
#
# Every maintenance statement the suite issues is one VACUUM (VERBOSE, ANALYZE)
# between maint_begin() and maint_end(), in a session whose settable timeouts
# are 0, and the churn stage checks the rule's four proofs on all of them -
# completion, the VERBOSE dead-but-not-yet-removable count, the horizon holders
# and the page classes - and dies rather than score a defeated fixture.
#
# Schema bl holds what the suite does not cover and this page still measures:
# the shapes pgstatindex refuses, an index the catalog says is not valid, two
# pages of known contents and an empty table's primary key, fresh builds at
# four fillfactors, the four fillfactor-deleted fixtures, the dead-page
# fixture, the two duplicate builds, the build-with-deduplication-off shape,
# and the race stage's own index.  Those are guard and model fixtures, not
# scored fixtures.
#
# The pinned checkout is read only.  Everything this script writes lives under
# $SANDBOX, and `clean` deletes it.
#
# Usage, from the repository root:
#   bash bloat_pgstatindex_v12.sh                 # every stage, in order
#   bash bloat_pgstatindex_v12.sh score residual  # selected stages
#   bash bloat_pgstatindex_v12.sh clean           # stop, delete this leg's dirs
#
# Stages: build check cluster texts fixtures suite churn report decide facts
#         cost priv compare score guard residual race errors crossleg summary
#         stop clean
#
# Environment: WIKI_ROOT PAGE SRC12 SANDBOX PORT12 JOBS ROWS OLD_REV
#              OLD_REV_ALERT EXTRA_CFLAGS
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v17/questions/indexing/btree-bloat-with-pgstatindex.md}"
SRC12="${SRC12:-$WIKI_ROOT/raw/postgres-12}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/pgsi}"
PORT12="${PORT12:-55412}"
JOBS="${JOBS:-4}"
ROWS="${ROWS:-1000000}"
OLD_REV="${OLD_REV:-cbbbd16}"
OLD_REV_ALERT="${OLD_REV_ALERT:-0dbabb6}"
EXTRA_CFLAGS="${EXTRA_CFLAGS:--O2 -g -DTRUE=1 -DFALSE=0}"

BUILD="$SANDBOX/build12"; INST="$SANDBOX/install12"; DATA="$SANDBOX/data12"
OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql12"; SOCK="$SANDBOX/sock12"; BIN="$INST/bin"
DB=bloat12
export PGPORT="$PORT12" PGHOST="$SOCK" PGDATABASE=postgres

# SHA-256 of the sql blocks this page files, in page order.  BASE_SQL is the
# filed statement; BASE_HARNESS, BASE_GATE, BASE_SUITE, BASE_DRAIN and
# BASE_CENSUS are the shared suite's harness, its family 1 fixtures, its
# families 2 to 6, rule 2's drain and rule 3's census.  BASE_PREV is the text
# filed before wasted space was rebased on the fillfactor and BASE_ALERT the
# text filed before alert_pct and the status column were removed; both are
# recovered from git history, for the compare and cost stages.
BASE_SQL=3d4507a54b38ac3edfaffd41f29c91518d6032dd561a025f343bbeb3c0c55b5d
BASE_HARNESS=87f6a505e42ee7432c05a4f514dc43b23f9ddbceabdc782fb710347789d97321
BASE_GATE=d73fb4d599896b5e129f49ee682f57bde8eab06abdcbb085c12f201d08b614a9
BASE_SUITE=713d503da008c19f9f16278070338870389aaf3db3b87198efa1f978f2b4126a
BASE_DRAIN=72711d3ece42ec5423acd2f8e9de15ea40920463785db6aee90e57d33a1d6d83
BASE_CENSUS=9ac052745ce92bdd8b989a8610cfb7b89e5b74b14d911316e92e70ac23993d84
BASE_PREV=f5b995d3c5d51dddd1378e4e1ac31f9ad180cec0cc811a803186b86a1fb721e9
BASE_ALERT=da4f4277b24e654c0241911f3ef977bfa5d109d3986ce30fe07919b3f82c93a0

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# -X ignores ~/.psqlrc; ON_ERROR_STOP is on every helper, because without it a
# failed statement inside a -f script leaves the exit status 0.
# SESSION_OPTS gives every helper session a statement_timeout and a
# lock_timeout.  Both are PGC_USERSET, so the libpq options string applies them
# at session scope, with no reload and no restart, and a block that SETs its
# own values overrides them.  They are passed per call rather than exported,
# because pg_regress keeps an inherited PGOPTIONS and make check must not see
# them.
SESSION_OPTS="-c statement_timeout=30min -c lock_timeout=60s"
q()  { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
s()  { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
t()  { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" -c "$1"; }
fl() { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" -f "$1"; }
# err() runs a statement that is expected to fail and prints the message only.
err() { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -At -q -d "$DB" -c "$1" 2>&1 | grep -E '^(ERROR|FATAL)' | head -1; }

# The fence is assembled at run time so that this script contains no literal
# Markdown fence and can therefore live inside one.
md_block() {
  local lang=$1 want=$2 file=$3 n=0 inb=0 line tick fence
  tick=$(printf '\140'); fence="$tick$tick$tick"
  while IFS= read -r line; do
    if [ "$inb" = 1 ]; then
      if [ "$line" = "$fence" ]; then inb=0; [ "$n" = "$want" ] && return 0; continue; fi
      [ "$n" = "$want" ] && printf '%s\n' "$line"
    elif [ "$line" = "$fence$lang" ]; then
      n=$((n + 1)); inb=1
    fi
  done < "$file"
}

# block <n> <want-hash> <outfile> <label>: extract one sql block of the page
# and refuse to run on a text that is not the filed one.
block() {
  local n=$1 want=$2 file=$3 label=$4 got
  md_block sql "$n" "$PAGE" > "$file"
  [ -s "$file" ] || die "sql block $n of $PAGE is empty"
  got=$(sha256sum < "$file" | cut -d' ' -f1)
  [ "$got" = "$want" ] || die "$label (sql block $n) hashes $got, expected $want"
  note "$label: $(wc -l < "$file") lines, $(wc -c < "$file") bytes, sha256 ${got:0:12}"
}

# parse_verbose <log>: proof 2 of the shared suite's rule "The maintenance must
# not be defeated", in this server's wording.  12.2 emits one message per
# relation,
#   INFO:  "tbl": found X removable, Y nonremovable row versions in ...
#   DETAIL:  Z dead row versions cannot be removed yet, oldest xmin: ...
# so the name and the two counts come from the INFO line and the dead count
# from the DETAIL line that follows it.  Neither pattern is anchored at the
# start of the line, because psql prefixes a message it reads from a -f script
# with "psql:<file>:<line>: " and leaves the DETAIL continuation unprefixed.
# A TOAST relation's lines match no maint row and update nothing.  A table
# maintained twice keeps the larger of the two dead counts.  Bash only: no awk,
# no perl.
parse_verbose() {
  local log=$1 line cur="" rest removed remain dead
  [ -f "$log" ] || return 0
  while IFS= read -r line; do
    case $line in
      *'INFO:  "'*'": found '*' removable, '*' nonremovable row versions'*)
        rest=${line#*INFO:  \"};    cur=${rest%%\"*}
        rest=${line#*: found };     removed=${rest%% removable,*}
        rest=${rest#* removable, }; remain=${rest%% nonremovable*} ;;
      *' dead row versions cannot be removed yet'*)
        [ -n "$cur" ] || continue
        rest=${line#*DETAIL:  }; dead=${rest%% dead row versions*}
        printf "UPDATE /* wiki_pgsi_maint_verbose12 */ maint SET removed = %s, remain = %s, dead_not_removable = greatest(coalesce(dead_not_removable, 0), %s) WHERE tbl = '%s';\n" \
               "$removed" "$remain" "$dead" "$cur"
        cur="" ;;
    esac
  done < "$log"
}

# maint_skips: proof 1's other half.  A foreground VACUUM or ANALYZE that could
# not take its ShareUpdateExclusiveLock says so in the log, and a statement cut
# short by a timeout does too; either way the command returned without doing
# the work.  Only the lines after the run mark the cluster stage wrote are
# read, so a re-run does not inherit the lines of the run before it.
maint_skips() {
  local log="$OUT/server12.log" from line
  : > "$OUT/maint_skips12.txt"
  [ -f "$log" ] || return 0
  # The window the rule names: from the first churn statement, which the suite
  # stage marks, until the census has finished.  Reading from the run mark
  # instead would sweep in the race stage's deliberate lock-timeout
  # cancellation whenever the suite and churn stages are re-run on a cluster
  # that already carries one.
  from=$(grep -n 'wiki_pgsi_maint_mark' "$log" | tail -1 | cut -d: -f1)
  [ -n "${from:-}" ] || from=$(grep -n 'wiki_pgsi_run_mark' "$log" | tail -1 | cut -d: -f1)
  [ -n "${from:-}" ] || from=1
  while IFS= read -r line; do
    case $line in
      *'skipping vacuum of '*|*'skipping analyze of '*|\
      *'canceling autovacuum task'*|*'canceling statement due to'*)
        printf '%s\n' "$line" >> "$OUT/maint_skips12.txt" ;;
    esac
  done < <(sed -n "${from},\$p" "$log")
  return 0
}

# The shared suite's rule "The maintenance must not be defeated", enforced on
# this leg too: it fails the run instead of publishing a number taken under a
# defeated maintenance.  Four proofs per maintenance statement: it completed
# and no skip or cancellation line names its table; its VERBOSE "dead row
# versions cannot be removed yet" count exists and is zero; every horizon probe
# was clean; and the page classes are recorded.  This server has no
# transaction_timeout, so the timeout set it records carries three zeros and an
# n/a rather than four zeros.
maint_proofs() {
  local n bad skips=0
  q "SELECT /* wiki_pgsi_maint_after */ maint_after()" > /dev/null \
    || die "the post-maintenance counter read failed"
  n=$(s 'SELECT count(*) FROM maint')
  [ "${n:-0}" -gt 0 ] || die "no maintenance statement was recorded at all"
  bad=$(s 'SELECT count(*) FROM maint WHERE ended IS NULL')
  [ "$bad" = 0 ] || { t 'SELECT tbl, source, started FROM maint
                          WHERE ended IS NULL ORDER BY tbl' >&2
                      die "$bad maintenance statements did not complete"; }
  bad=$(s 'SELECT count(*) FROM maint WHERE dead_not_removable IS NULL')
  [ "$bad" = 0 ] || { t 'SELECT tbl, source FROM maint
                          WHERE dead_not_removable IS NULL ORDER BY tbl' >&2
                      die "$bad maintained tables have no VERBOSE count: proof 2 is missing"; }
  bad=$(s 'SELECT count(*) FROM maint WHERE dead_not_removable > 0')
  [ "$bad" = 0 ] || { t 'SELECT tbl, source, removed, remain, dead_not_removable,
                                dead_after
                           FROM maint WHERE dead_not_removable > 0
                          ORDER BY dead_not_removable DESC' >&2
                      die "$bad maintained tables kept dead tuples the horizon still covered: the maintenance was defeated, repair the fixture and re-run"; }
  bad=$(s 'SELECT count(*) FROM horizon
            WHERE xmin_holders > 0 OR open_xacts > 0
               OR slots > 0 OR prepared > 0')
  [ "$bad" = 0 ] || { t 'SELECT step, tbl, xmin_holders, open_xacts, slots,
                                prepared, detail
                           FROM horizon
                          WHERE xmin_holders > 0 OR open_xacts > 0
                             OR slots > 0 OR prepared > 0 ORDER BY at' >&2
                      die "$bad horizon probes found a holder: the maintenance ran with a pinned horizon"; }
  bad=$(s 'SELECT count(*) FROM pageclass')
  [ "${bad:-0}" -gt 0 ] || die "no page classes were recorded: proof 4 is missing"
  maint_skips
  [ -s "$OUT/maint_skips12.txt" ] && skips=$(grep -c '' "$OUT/maint_skips12.txt")
  { printf 'maintenance statements  %s, %s completed\n' "$n" \
      "$(s 'SELECT count(*) FROM maint WHERE ended IS NOT NULL')"
    printf 'by source               %s\n' \
      "$(s "SELECT string_agg(source || '=' || n, ' ' ORDER BY source)
              FROM (SELECT source, count(*) AS n FROM maint GROUP BY source) x")"
    printf 'dead but not removable  max %s over %s tables\n' \
      "$(s 'SELECT coalesce(max(dead_not_removable), -1) FROM maint')" "$n"
    printf 'dead tuples left behind max %s\n' \
      "$(s 'SELECT coalesce(max(dead_after), -1) FROM maint')"
    printf 'tuples removed          %s\n' \
      "$(s 'SELECT coalesce(sum(removed), 0) FROM maint')"
    printf 'horizon probes clean    %s of %s\n' \
      "$(s 'SELECT count(*) FROM horizon
             WHERE xmin_holders = 0 AND open_xacts = 0
               AND slots = 0 AND prepared = 0')" \
      "$(s 'SELECT count(*) FROM horizon')"
    printf 'timeout sets in force   %s: %s\n' \
      "$(s 'SELECT count(DISTINCT timeouts) FROM maint')" \
      "$(s 'SELECT DISTINCT timeouts FROM maint')"
    printf 'indexes page-classed    %s, %s with deleted pages, %s deleted pages\n' \
      "$(s 'SELECT count(*) FROM pageclass')" \
      "$(s 'SELECT count(*) FROM pageclass WHERE deleted_pages > 0')" \
      "$(s 'SELECT coalesce(sum(deleted_pages), 0) FROM pageclass')"
    printf 'skip or cancellation lines %s\n' "$skips"; } > "$OUT/maint_proofs12.txt"
  cat "$OUT/maint_proofs12.txt" >&2
  [ "$skips" = 0 ] || { cat "$OUT/maint_skips12.txt" >&2
                        die "$skips skip or cancellation line(s) in the server log: a maintenance statement did not do its work"; }
}

# ---------------------------------------------------------------- build ------
# This leg is configured --with-icu on purpose: five fixtures of the shared
# suite need ICU collations, and without them the run would only record five
# more skips.  ICU 68 dropped the TRUE/FALSE macros a 12.2 tree still uses, so
# the two defines go back in through CFLAGS; empty EXTRA_CFLAGS on a host whose
# ICU still defines them.
stage_build() {
  say "build 12.2 out of tree from $SRC12"
  [ -x "$BIN/postgres" ] && { note "already built, skipping"; return 0; }
  [ -x "$SRC12/configure" ] || die "no pinned checkout at $SRC12; set SRC12 or run from the repository root"
  mkdir -p "$BUILD" "$OUT" "$SQLD"
  ( cd "$BUILD" && "$SRC12/configure" --prefix="$INST" --enable-debug \
      --with-icu --with-readline --with-zlib CFLAGS="$EXTRA_CFLAGS" > configure.log 2>&1 ) \
    || { cp "$BUILD/configure.log" "$OUT/configure12.log" 2>/dev/null; die "configure failed, see $OUT/configure12.log"; }
  ( cd "$BUILD" && make -j"$JOBS" > make.log 2>&1 && make install > install.log 2>&1 ) \
    || { cp "$BUILD"/*.log "$OUT/" 2>/dev/null; grep -m3 'error:' "$BUILD/make.log" >&2; die "make failed"; }
  ( cd "$BUILD" && make -C contrib/pgstattuple -j"$JOBS" >> install.log 2>&1 \
      && make -C contrib/pgstattuple install >> install.log 2>&1 ) || die "contrib/pgstattuple failed"
  local l
  for l in configure make install; do cp "$BUILD/$l.log" "$OUT/${l}12.log" 2>/dev/null; done
  note "$("$BIN/postgres" --version)"
}

stage_check() {
  say "regression suites, 12.2"
  mkdir -p "$OUT"
  : > "$OUT/checks12.txt"
  ( cd "$BUILD" && make check > check_core.log 2>&1 )
  printf 'core=%s %s\n' "$?" \
    "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_core.log" | tail -1)" \
    >> "$OUT/checks12.txt"
  ( cd "$BUILD" && make -C contrib/pgstattuple check > check_pgstattuple.log 2>&1 )
  printf 'pgstattuple=%s %s\n' "$?" \
    "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_pgstattuple.log" | tail -1)" \
    >> "$OUT/checks12.txt"
  local l d
  for l in "$BUILD"/check_*.log; do [ -f "$l" ] && cp "$l" "$OUT/12_$(basename "$l")"; done
  for d in "$BUILD"/src/test/regress/regression.diffs "$BUILD"/contrib/pgstattuple/regression.diffs; do
    [ -f "$d" ] && cp "$d" "$OUT/diffs12_$(basename "$(dirname "$d")").txt"
  done
  cat "$OUT/checks12.txt" >&2
}

# -------------------------------------------------------------- cluster ------
# Cluster settings and their apply scope, all written to postgresql.conf before
# the first start, so every one of them is in force from the first connection:
#   listen_addresses, port, unix_socket_directories, shared_buffers,
#   logging_collector  -> PGC_POSTMASTER, restart
#   fsync, autovacuum                                   -> PGC_SIGHUP, reload
#   maintenance_work_mem, max_parallel_maintenance_workers -> PGC_USERSET,
#                                                          session scope
# autovacuum is off so that no background worker moves a fixture between the
# five phases, not because the fixtures model an unmaintained database: under
# the shared suite's maintenance assumption every churn ends on one bracketed
# VACUUM (VERBOSE, ANALYZE) run by the fixture text itself, and rule 3's census
# recomputes the launcher's analyze verdict for the tables no churn touched.
stage_cluster() {
  say "isolated 12.2 cluster on port $PORT12"
  mkdir -p "$OUT" "$SQLD" "$SOCK"
  if [ ! -f "$DATA/PG_VERSION" ]; then
    "$BIN/initdb" -D "$DATA" --locale=C --encoding=UTF8 > "$OUT/initdb12.log" 2>&1 \
      || die "initdb failed, see $OUT/initdb12.log"
    cat >> "$DATA/postgresql.conf" <<CONF
listen_addresses = ''
port = $PORT12
unix_socket_directories = '$SOCK'
shared_buffers = 512MB
maintenance_work_mem = 256MB
max_parallel_maintenance_workers = 0
autovacuum = off
fsync = off
logging_collector = off
CONF
  fi
  if ! "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server12.log" -w start > /dev/null 2>&1 \
      || die "server did not start, see $OUT/server12.log"
  fi
  # The error audit reads only the lines after this mark, so a re-run does not
  # inherit the errors of the run before it.
  printf -- '-- wiki_pgsi_run_mark %s\n' "$(date -u +%FT%TZ)" >> "$OUT/server12.log"
  "$BIN/psql" -X -At -q -d postgres -c "SELECT 1" > /dev/null 2>&1 || die "cannot connect"
  "$BIN/psql" -X -At -q -d postgres -c \
    "SELECT count(*) FROM pg_database WHERE datname = '$DB'" | grep -q '^1$' \
    || "$BIN/createdb" "$DB" || die "createdb failed"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null || die "pgstattuple not installed"
  {
    printf 'uname=%s\n' "$(uname -sm)"
    printf 'server_version_num=%s\n' "$(s 'SHOW server_version_num')"
    printf 'server_version=%s\n' "$(s 'SHOW server_version')"
    printf 'block_size=%s\n' "$(s 'SHOW block_size')"
    printf 'max_data_alignment=%s\n' "$("$BIN/pg_controldata" -D "$DATA" | grep -i 'maximum data alignment' | tr -s ' ' | cut -d' ' -f4)"
    printf 'pgstattuple=%s\n' "$(s "SELECT extversion FROM pg_extension WHERE extname = 'pgstattuple'")"
    printf 'autovacuum_analyze_threshold=%s\n' "$(s 'SHOW autovacuum_analyze_threshold')"
    printf 'autovacuum_analyze_scale_factor=%s\n' "$(s 'SHOW autovacuum_analyze_scale_factor')"
  } > "$OUT/platform12.txt"
  cat "$OUT/platform12.txt" >&2
}

# ---------------------------------------------------------------- texts -----
# Six texts come out of the page and one out of git history:
#   report.sql   the filed statement, byte for byte, hash-checked
#   view.sql     the same text as a view over the internal `final` stage, with
#                one edit, printed: the two SET lines dropped.  The filed text
#                prefilters nothing, so the view's population is the report's
#   harness.sql, gate.sql, suite.sql, drain.sql, census.sql
#                the shared mandatory suite, all hash-checked
#   prev.sql     the text filed before wasted space was rebased on the
#                fillfactor, recovered from OLD_REV for the cost comparison
gen_view() {                       # gen_view <view> < text
  local view=$1 line tail=0
  printf 'DROP VIEW IF EXISTS %s CASCADE;\nCREATE VIEW %s AS\n' "$view" "$view"
  while IFS= read -r line; do
    case $line in
      "SET statement_timeout"*|"SET lock_timeout"*)
        printf '   harness edit: dropped %s\n' "$line" >&2; continue ;;
      *"AS min_index_bytes"*)
        printf '   harness edit: %s -> 0\n' "$(printf '%s' "$line" | tr -s ' ')" >&2
        # The filed text has no size prefilter left to neutralise; the two
        # recovered texts still carry one, and are read at 0 so that all three
        # are compared over one population.  The superseded alert_pct text
        # carries another params entry after this one, so the trailing comma
        # has to survive the edit.
        case $line in
          *"min_index_bytes,"*)
            printf '           0::bigint AS min_index_bytes,  -- harness: score every index\n' ;;
          *)
            printf '           0::bigint AS min_index_bytes  -- harness: score every index\n' ;;
        esac
        continue ;;
      "SELECT /* wiki_btree_bloat_pgstatindex_12_17 */") tail=1; continue ;;
    esac
    [ "$tail" = 1 ] && continue
    printf '%s\n' "$line"
  done
  printf 'SELECT f.* FROM final f;\n'
}

stage_texts() {
  say "extract the statement and the shared suite from $PAGE"
  mkdir -p "$SQLD" "$OUT"
  [ -f "$PAGE" ] || die "no page at $PAGE; set PAGE or run from the repository root"
  block 1 "$BASE_SQL"     "$SQLD/report.sql"  "filed statement"
  block 2 "$BASE_HARNESS" "$SQLD/harness.sql" "suite harness"
  block 3 "$BASE_GATE"    "$SQLD/gate.sql"    "family 1 fixtures"
  block 4 "$BASE_SUITE"   "$SQLD/suite.sql"   "families 2-6 fixtures"
  block 5 "$BASE_DRAIN"   "$SQLD/drain.sql"   "rule 2 drain"
  block 6 "$BASE_CENSUS"  "$SQLD/census.sql"  "rule 3 census and forgeries"
  gen_view bloat_final < "$SQLD/report.sql" > "$SQLD/view.sql"
  # The statement alone, without the two SET lines, for EXPLAIN.
  grep -v '^SET ' "$SQLD/report.sql" > "$SQLD/bare.sql"
  old_text "$OLD_REV"       "$BASE_PREV"  prev
  old_text "$OLD_REV_ALERT" "$BASE_ALERT" alert
}

# old_text <rev> <want-hash> <name>: recover sql block 1 of this page as it
# stood at <rev>, refuse a text that is not the one recorded, and leave it in
# $SQLD/<name>.sql.  The two superseded texts are what the compare stage
# measures the filed text against, on the population this run built.
old_text() {
  local rev=$1 want=$2 name=$3 got
  local rel=wiki/v17/questions/indexing/btree-bloat-with-pgstatindex.md
  if ! git -C "$WIKI_ROOT" cat-file -e "$rev:$rel" 2>/dev/null; then
    note "no revision $rev in this repository; the $name comparison will be skipped"
    return 0
  fi
  git -C "$WIKI_ROOT" show "$rev:$rel" > "$SQLD/page_$name.md"
  md_block sql 1 "$SQLD/page_$name.md" > "$SQLD/$name.sql"
  got=$(sha256sum < "$SQLD/$name.sql" | cut -d' ' -f1)
  [ "$got" = "$want" ] || die "$name text hashes $got, expected $want"
  grep -v '^SET ' "$SQLD/$name.sql" > "$SQLD/${name}_bare.sql"
  note "$name text ($rev): $(wc -l < "$SQLD/$name.sql") lines, $(wc -c < "$SQLD/$name.sql") bytes, sha256 ${got:0:12}"
}

# ------------------------------------------------------------- fixtures -----
# Schema bl: the guard and model fixtures, which the shared suite does not
# cover and this page still measures.  Every statement is DISPOSABLE - it drops
# and rebuilds a whole schema and writes indisvalid = false into pg_index by
# hand - and is not meant for a database anyone cares about.  The two session
# GUCs are PGC_USERSET: session scope, no reload and no restart.
stage_fixtures() {
  say "guard and model fixtures in schema bl (rows=$ROWS)"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null
  cat > "$SQLD/fixtures.sql" <<'SQL'
-- DISPOSABLE guard and model fixtures for the pgstatindex bloat report.
-- Every object lives in schema bl of a throwaway database.
SET statement_timeout = '30min';   -- PGC_USERSET, session scope
SET lock_timeout      = '30s';     -- PGC_USERSET, session scope
SET client_min_messages = warning;

DROP SCHEMA IF EXISTS bl CASCADE;
CREATE SCHEMA bl;

-- 1. fresh builds at four fillfactors: the model's target density, measured.
--    i_race is the race stage's own fixture, dropped and recreated there so no
--    other fixture is disturbed.
CREATE TABLE bl.t_fresh (id int);
INSERT INTO bl.t_fresh SELECT g FROM generate_series(1, :ff_rows) g;
CREATE INDEX i_fresh ON bl.t_fresh (id);
CREATE INDEX i_ff100 ON bl.t_fresh (id) WITH (fillfactor = 100);
CREATE INDEX i_ff50  ON bl.t_fresh (id) WITH (fillfactor = 50);
CREATE INDEX i_ff10  ON bl.t_fresh (id) WITH (fillfactor = 10);
CREATE INDEX i_race  ON bl.t_fresh (id) WITH (fillfactor = 80);

-- 2. the four fillfactor fixtures: built at a stated fillfactor, then nine
--    tenths of the rows deleted and the table vacuumed.
CREATE TABLE bl.t_ffdel (id int);
INSERT INTO bl.t_ffdel SELECT g FROM generate_series(1, :ff_rows) g;
CREATE INDEX i_ff100_del90 ON bl.t_ffdel (id) WITH (fillfactor = 100);
CREATE INDEX i_ff50_del90  ON bl.t_ffdel (id) WITH (fillfactor = 50);
CREATE INDEX i_ff10_del90  ON bl.t_ffdel (id) WITH (fillfactor = 10);
DELETE FROM bl.t_ffdel WHERE id % 10 <> 0;
VACUUM bl.t_ffdel;

CREATE TABLE bl.t_ffhead (id int);
INSERT INTO bl.t_ffhead SELECT g FROM generate_series(1, :ff_rows) g;
CREATE INDEX i_ff50_delhead ON bl.t_ffhead (id) WITH (fillfactor = 50);
DELETE FROM bl.t_ffhead WHERE id <= (:ff_rows * 9) / 10;
VACUUM bl.t_ffhead;

-- 3. the dead-page fixture: a contiguous head deleted, then vacuumed, so whole
--    pages hold nothing while avg_leaf_density stays high.
CREATE TABLE bl.t_delhead (id int);
INSERT INTO bl.t_delhead SELECT g FROM generate_series(1, :rows) g;
CREATE INDEX i_delhead ON bl.t_delhead (id);
DELETE FROM bl.t_delhead WHERE id <= (:rows * 7) / 10;
VACUUM bl.t_delhead;

-- 4. duplicates, built two ways: by CREATE INDEX and by inserts.
CREATE TABLE bl.t_dup (v int);
INSERT INTO bl.t_dup SELECT g % 10 FROM generate_series(1, :rows) g;
CREATE INDEX i_dup ON bl.t_dup (v);

CREATE TABLE bl.t_dup_ins (v int);
CREATE INDEX i_dup_ins ON bl.t_dup_ins (v);
INSERT INTO bl.t_dup_ins SELECT g % 10 FROM generate_series(1, :rows) g;

-- 5. built with deduplication off, then turned back on: the pg_upgrade shape,
--    where a rebuild compresses what the current file cannot.  The reloption
--    does not exist on every major, so the fixture is attempted and its
--    absence recorded.
DO $dd$
DECLARE msg text;
BEGIN
  EXECUTE 'CREATE TABLE bl.t_dedup (v int)';
  EXECUTE 'INSERT INTO bl.t_dedup SELECT g % 10 FROM generate_series(1, ' ||
          current_setting('bl.rows') || ') g';
  BEGIN
    EXECUTE 'CREATE INDEX i_dedup_off ON bl.t_dedup (v) WITH (deduplicate_items = off)';
    EXECUTE 'ALTER INDEX bl.i_dedup_off SET (deduplicate_items = on)';
  EXCEPTION WHEN OTHERS THEN
    msg := SQLERRM;
    RAISE WARNING 'i_dedup_off skipped: %', msg;
  END;
END
$dd$;
SELECT CASE WHEN to_regclass('bl.i_dedup_off') IS NULL
            THEN 'i_dedup_off skipped' ELSE 'i_dedup_off built' END AS dedup_off_fixture;

-- 6. two pages of known contents, for the implied leaf capacity, and an empty
--    table's primary key, for the NaN density.
CREATE TABLE bl.c_one (id int);
INSERT INTO bl.c_one VALUES (1);
CREATE INDEX c_one_idx ON bl.c_one (id);

CREATE TABLE bl.c_zero (id int);
INSERT INTO bl.c_zero VALUES (1);
CREATE INDEX c_zero_idx ON bl.c_zero (id);
DELETE FROM bl.c_zero;
VACUUM bl.c_zero;

CREATE TABLE bl.t_empty (id int PRIMARY KEY);

-- 7. the shapes pgstatindex refuses, one per candidate filter.
CREATE TABLE bl.s_other (id int, v text, g_point point, r int4range);
INSERT INTO bl.s_other SELECT g, md5(g::text), point(g, g), int4range(g, g + 10)
  FROM generate_series(1, 20000) g;
CREATE INDEX s_hash   ON bl.s_other USING hash   (id);
CREATE INDEX s_gin    ON bl.s_other USING gin    (to_tsvector('simple', v));
CREATE INDEX s_gist   ON bl.s_other USING gist   (g_point);
CREATE INDEX s_spgist ON bl.s_other USING spgist (g_point);
CREATE INDEX s_brin   ON bl.s_other USING brin   (id);
CREATE VIEW  bl.s_view AS SELECT 1 AS one;
CREATE SEQUENCE bl.s_seq;

CREATE TABLE bl.t_part (id int) PARTITION BY RANGE (id);
CREATE TABLE bl.t_part_1 PARTITION OF bl.t_part FOR VALUES FROM (1) TO (100001);
CREATE TABLE bl.t_part_2 PARTITION OF bl.t_part FOR VALUES FROM (100001) TO (200001);
INSERT INTO bl.t_part SELECT g FROM generate_series(1, 200000) g;
CREATE INDEX i_part ON bl.t_part (id);

-- 8. an index the catalog says is not valid.  Only a disposable cluster may
--    have its catalog written to by hand like this.
CREATE TABLE bl.t_invalid (id int);
INSERT INTO bl.t_invalid SELECT g FROM generate_series(1, 300000) g;
CREATE INDEX i_invalid ON bl.t_invalid (id);
UPDATE pg_index SET indisvalid = false WHERE indexrelid = 'bl.i_invalid'::regclass;
SQL
  local ffrows=$((ROWS / 5))
  # psql does not substitute :variables inside a dollar-quoted body, so the
  # version-guarded fixture reads its row count from a database-level GUC.
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" \
    -c "ALTER DATABASE $DB SET bl.rows = '$ROWS'" > /dev/null || die "cannot set bl.rows"
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" \
    -v rows="$ROWS" -v ff_rows="$ffrows" \
    -f "$SQLD/fixtures.sql" > "$OUT/fixtures12.log" 2>&1 || {
      tail -5 "$OUT/fixtures12.log" >&2; die "guard fixtures failed"; }
  grep -E 'i_dedup_off (built|skipped)' "$OUT/fixtures12.log" >&2
  note "indexes in bl: $(s "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'bl' AND c.relkind IN ('i','I')")"
}

# ---------------------------------------------------------------- suite -----
# Phases 1 and 2 of the shared mandatory suite: the public schema is recreated,
# the harness installed - its event trigger is what cuts each recipe at its
# index build - then family 1 and families 2 to 6 are built and each fixture's
# build contract checked while it is still as built.
stage_suite() {
  say "the shared mandatory suite, build and baseline phases"
  [ -f "$SQLD/suite.sql" ] || die "run the texts stage first"
  # CREATE SCHEMA public grants nothing to PUBLIC, so initdb's USAGE grant is
  # restored here: without it a non-superuser cannot even see pgstatindex, and
  # the privilege stage would measure the sandbox rather than the function.
  q "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;
     GRANT USAGE ON SCHEMA public TO PUBLIC;" > /dev/null \
    || die "schema reset failed"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null || die "pgstattuple not installed"
  # The no-defeat rule's window opens at the first churn statement, which is in
  # the fixture file below; this mark is where the skip-line check starts
  # reading, so a re-run of this stage does not inherit an earlier run's lines.
  printf -- '-- wiki_pgsi_maint_mark %s\n' "$(date -u +%FT%TZ)" >> "$OUT/server12.log"
  fl "$SQLD/harness.sql" > "$OUT/suite_harness12.log" 2>&1 \
    || { tail -5 "$OUT/suite_harness12.log" >&2; die "harness install failed"; }
  # client_min_messages is debug1 for family 1 only, because
  # _bt_allequalimage logs its own verdict at that level.
  PGOPTIONS="$SESSION_OPTS -c client_min_messages=debug1" \
    "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" -f "$SQLD/gate.sql" \
    > "$OUT/gate12.log" 2>&1 || { tail -20 "$OUT/gate12.log" >&2; die "family 1 failed"; }
  grep -c 'can safely use deduplication' "$OUT/gate12.log" \
    | xargs printf 'DEBUG1 can safely use deduplication: %s\n' >&2
  grep -c 'cannot use deduplication' "$OUT/gate12.log" \
    | xargs printf 'DEBUG1 cannot use deduplication:      %s\n' >&2
  # stdout and stderr are split here, because the maintenance statements'
  # VACUUM (VERBOSE) messages arrive on stderr and the churn stage parses them
  # for proof 2 of the no-defeat rule.
  fl "$SQLD/suite.sql" > "$OUT/suite12.log" 2> "$OUT/suite_verbose12.log" \
    || { tail -20 "$OUT/suite12.log" >&2; tail -20 "$OUT/suite_verbose12.log" >&2
         die "families 2-6 failed"; }
  {
    printf -- '-- family 1 build log, tail\n'; tail -8 "$OUT/gate12.log"
    printf -- '-- families 2-6 build log, tail\n'; tail -12 "$OUT/suite12.log"
  } > "$OUT/suite_build12.txt"
  note "$(s "SELECT count(*) || ' fixtures planned, ' ||
              (SELECT count(*) FROM skipped) || ' skipped, ' ||
              (SELECT count(*) FROM snap WHERE phase = 'built') || ' baselines, ' ||
              (SELECT count(*) FROM plan
                WHERE want_rows IS NOT NULL AND built_rows <> want_rows) ||
              ' build-contract failures' FROM plan")"
  t "SELECT /* wiki_pgsi_suite_skips */ num, leg, idx, reason FROM skipped
      ORDER BY num, leg" > "$OUT/skipped12.txt" 2>&1
  t "SELECT /* wiki_pgsi_suite_families */ grp, count(*) AS fixtures,
            count(*) FILTER (WHERE want_stage = 'rebuild') AS want_rebuild
       FROM plan GROUP BY grp ORDER BY grp" >> "$OUT/skipped12.txt" 2>&1
  cat "$OUT/skipped12.txt" >&2
}

# ---------------------------------------------------------------- churn -----
# Phase 3, in the order the shared suite prescribes.  The drain runs in its own
# session and the census in another, because before PostgreSQL 15 a backend's
# pending statistics publish when it exits, and rule 3 reads them.  Between
# them the maintenance statements' VERBOSE output is turned into recorded
# numbers, and after them the four no-defeat proofs are checked: the stage dies
# rather than score a fixture whose maintenance was defeated.
stage_churn() {
  say "churn: rule 2 drain with its maintenance step, rule 3 census, forgeries last, churned snapshot"
  [ -n "$(s 'SELECT 1 FROM plan LIMIT 1')" ] || die "no plan rows; run the suite stage first"
  fl "$SQLD/drain.sql" > "$OUT/drain12.txt" 2> "$OUT/drain_verbose12.log" \
    || { tail -5 "$OUT/drain12.txt" >&2; tail -5 "$OUT/drain_verbose12.log" >&2
         die "drain failed"; }
  # Proof 2, recorded: every VERBOSE message this run produced, the fixture
  # file's statements and the drain's alike, as one UPDATE per maintained
  # table.  The UPDATEs are keyed by table and take the greatest dead count, so
  # applying them twice changes nothing.
  parse_verbose "$OUT/suite_verbose12.log" > "$SQLD/maint_verbose.sql"
  parse_verbose "$OUT/drain_verbose12.log" >> "$SQLD/maint_verbose.sql"
  [ -s "$SQLD/maint_verbose.sql" ] \
    || die "the VACUUM VERBOSE output produced no dead-row-version line: proof 2 is missing"
  fl "$SQLD/maint_verbose.sql" > /dev/null || die "recording the VERBOSE counts failed"
  sleep 1
  fl "$SQLD/census.sql" > "$OUT/census12.txt" 2>&1 || { tail -5 "$OUT/census12.txt" >&2; die "census failed"; }
  tail -40 "$OUT/census12.txt" >&2
  say "no-defeat proofs: completion, VERBOSE counts, horizon, page classes"
  maint_proofs
  # The skip list is re-dumped here because the census can add to it: test
  # 120's precondition is asserted after the census, and an unmet precondition
  # is a skip rather than a score.
  t "SELECT /* wiki_pgsi_skips_after_census */ num, leg, idx, reason FROM skipped
      ORDER BY num, leg" > "$OUT/skipped12.txt" 2>&1
  t "SELECT /* wiki_pgsi_families_after_census */ grp, count(*) AS fixtures,
            count(*) FILTER (WHERE want_stage = 'rebuild') AS want_rebuild
       FROM plan GROUP BY grp ORDER BY grp" >> "$OUT/skipped12.txt" 2>&1
  note "$(s "SELECT count(*) || ' fixtures scored after the census, ' ||
              (SELECT count(*) FROM skipped) || ' skipped' FROM plan")"
}

# --------------------------------------------------------------- report -----
# Phase 4, the decide phase, part one: the filed text exactly as filed, both
# SET lines included.  Its own output is what the reader sees, so the rows it
# prints are loaded back as report_filed and are what `reported` means.
stage_report() {
  say "run the filed statement"
  [ -f "$SQLD/report.sql" ] || die "run the texts stage first"
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -P footer=off -A -F '|' -d "$DB" \
    -f "$SQLD/report.sql" > "$OUT/report12.txt" 2> "$OUT/report12.err"
  local rc=$?
  if [ "$rc" != 0 ]; then
    printf 'exact_text=refused\n' > "$OUT/exact12.txt"
    head -5 "$OUT/report12.err" >> "$OUT/exact12.txt"
    cat "$OUT/exact12.txt" >&2
    die "the filed text did not run; see $OUT/report12.err"
  fi
  printf 'exact_text=executes\n' > "$OUT/exact12.txt"
  # footer=off leaves one header line and one line per row.
  local rows cols
  rows=$(grep -c '^' "$OUT/report12.txt"); rows=$((rows - 1))
  cols=$(head -1 "$OUT/report12.txt" | tr '|' '\n' | grep -c '^')
  {
    printf 'report_rows=%s\n' "$rows"
    printf 'report_columns=%s\n' "$cols"
    printf 'report_bytes=%s\n' "$(wc -c < "$OUT/report12.txt")"
  } >> "$OUT/exact12.txt"
  cat "$OUT/exact12.txt" >&2
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" \
    -f "$SQLD/report.sql" > "$OUT/report12_pretty.txt" 2>&1
  # Load the printed rows back.  Fields 2, 13 and 14 are index_name,
  # est_reclaimable_pct and notes; no field of this report can contain a pipe.
  q "DROP TABLE IF EXISTS report_filed;
     CREATE /* wiki_pgsi_report_filed */ TABLE report_filed(index_name text PRIMARY KEY, est_pct numeric, notes text);" \
    > /dev/null || die "report_filed failed"
  : > "$SQLD/report_rows.sql"
  local name pct notes
  while IFS='|' read -r _ name _ _ _ _ _ _ _ _ _ _ pct notes; do
    [ -n "${name:-}" ] || continue
    printf "INSERT INTO report_filed VALUES ('%s', %s, '%s');\n" \
      "${name//\'/\'\'}" "${pct:-NULL}" "${notes//\'/\'\'}" >> "$SQLD/report_rows.sql"
  done < <(tail -n +2 "$OUT/report12.txt")
  fl "$SQLD/report_rows.sql" > /dev/null || die "loading report_filed failed"
  note "report_filed rows: $(s 'SELECT count(*) FROM report_filed')"
}

# --------------------------------------------------------------- decide -----
# Phase 4, part two: the same text as a view over its internal `final` stage,
# so every scored fixture gets the statement's own arithmetic with every
# intermediate column visible.  The filed text prefilters nothing, so the
# view's population is the report's and the two must agree row for row.  One
# pass, materialized, because the view reads every page of every index.
stage_decide() {
  say "materialize the statement's reading of every index"
  fl "$SQLD/view.sql" > /dev/null || die "harness view failed"
  q "DROP TABLE IF EXISTS decide;
     CREATE TABLE decide AS SELECT /* wiki_pgsi_decide */ * FROM bloat_final;" \
    > /dev/null || die "decide failed"
  q "CREATE /* wiki_pgsi_decide_idx */ INDEX decide_idx ON decide (index_name);" > /dev/null
  {
    printf 'decide_rows=%s\n' "$(s 'SELECT count(*) FROM decide')"
    printf 'decide_fixtures=%s\n' "$(s 'SELECT count(*) FROM decide d JOIN plan p ON p.idx = d.index_name')"
    printf 'filed_rows=%s\n' "$(s 'SELECT count(*) FROM report_filed')"
    # The view differs from the filed text in its presentation SELECT only, so
    # the two must agree on every row, and the view may hold no row the report
    # did not print.
    printf 'view_disagrees_with_filed=%s\n' \
      "$(s "SELECT count(*) FROM report_filed r JOIN decide d ON d.index_name = r.index_name
             WHERE round(100 * (d.index_size - d.est_rebuilt_bytes) / d.index_size, 1) <> r.est_pct")"
    printf 'view_rows_the_report_did_not_print=%s\n' \
      "$(s "SELECT count(*) FROM decide d WHERE NOT EXISTS
             (SELECT 1 FROM report_filed r WHERE r.index_name = d.index_name)")"
    printf 'fixtures_printed=%s of %s\n' \
      "$(s "SELECT count(*) FROM plan p JOIN report_filed r ON r.index_name = p.idx")" \
      "$(s 'SELECT count(*) FROM plan')"
    printf 'fixtures_under_1mb=%s of %s\n' \
      "$(s "SELECT count(*) FROM plan p JOIN decide d ON d.index_name = p.idx
             WHERE d.index_size < 1024 * 1024")" "$(s 'SELECT count(*) FROM plan')"
  } > "$OUT/decide12.txt"
  cat "$OUT/decide12.txt" >&2
}

# ---------------------------------------------------------------- facts -----
stage_facts() {
  say "version-local facts, refusals and page arithmetic"
  : > "$OUT/facts12.txt"
  local f="$OUT/facts12.txt"
  {
    printf 'server_version_num=%s\n' "$(s 'SHOW server_version_num')"
    printf 'block_size=%s\n' "$(s 'SHOW block_size')"
    printf 'candidates=%s\n' "$(s 'SELECT count(*) FROM decide')"
    printf 'index_size_equals_relation_size=%s of %s\n' \
      "$(s 'SELECT count(*) FROM decide f WHERE f.index_size = pg_relation_size(f.idx_oid)')" \
      "$(s 'SELECT count(*) FROM decide')"
    printf 'nan_density_indexes=%s\n' "$(s 'SELECT count(*) FROM decide WHERE leaf_pages = 0')"
    printf 'nan_float8_gt_20=%s\n' "$(s "SELECT ('NaN'::float8 > 20)::text")"
    printf 'nan_numeric_gt_20=%s\n' "$(s "SELECT ('NaN'::numeric > 20)::text")"
    printf 'dedup_fixture_present=%s\n' "$(s "SELECT (to_regclass('bl.i_dedup_off') IS NOT NULL)::text")"
  } >> "$f"

  # Every refusal the cand filters exist for.
  {
    printf 'err_hash=%s\n'      "$(err "SELECT * FROM pgstatindex('bl.s_hash'::regclass)")"
    printf 'err_gin=%s\n'       "$(err "SELECT * FROM pgstatindex('bl.s_gin'::regclass)")"
    printf 'err_gist=%s\n'      "$(err "SELECT * FROM pgstatindex('bl.s_gist'::regclass)")"
    printf 'err_spgist=%s\n'    "$(err "SELECT * FROM pgstatindex('bl.s_spgist'::regclass)")"
    printf 'err_brin=%s\n'      "$(err "SELECT * FROM pgstatindex('bl.s_brin'::regclass)")"
    printf 'err_partitioned=%s\n' "$(err "SELECT * FROM pgstatindex('bl.i_part'::regclass)")"
    printf 'err_table=%s\n'     "$(err "SELECT * FROM pgstatindex('bl.t_delhead'::regclass)")"
    printf 'err_view=%s\n'      "$(err "SELECT * FROM pgstatindex('bl.s_view'::regclass)")"
    printf 'err_sequence=%s\n'  "$(err "SELECT * FROM pgstatindex('bl.s_seq'::regclass)")"
    printf 'err_stale_oid=%s\n' "$(err "SELECT * FROM pgstatindex(2147483647::oid::regclass)")"
  } >> "$f"

  # The invalid index: an error on 17, a row on 12.
  local inv
  inv=$(err "SELECT * FROM pgstatindex('bl.i_invalid'::regclass)")
  if [ -n "$inv" ]; then
    printf 'invalid_index=refused %s\n' "$inv" >> "$f"
  else
    printf 'invalid_index=row %s\n' \
      "$(s "SELECT version || '|' || tree_level || '|' || index_size || '|' || root_block_no || '|' || internal_pages || '|' || leaf_pages || '|' || empty_pages || '|' || deleted_pages || '|' || avg_leaf_density || '|' || leaf_fragmentation FROM pgstatindex('bl.i_invalid'::regclass)")" >> "$f"
  fi

  # Fresh-build density at four fillfactors, and the reported estimate.
  printf 'fresh_builds fillfactor|target_density|avg_leaf_density|est_reclaimable_pct\n' >> "$f"
  s "SELECT f.fillfactor || '|' || round(100 * f.target_density, 2) || '|' ||
            round(f.avg_leaf_density::numeric, 2) || '|' ||
            round(100 * (f.index_size - f.est_rebuilt_bytes) / f.index_size, 1)
       FROM decide f
      WHERE f.index_name IN ('i_ff100', 'i_fresh', 'i_ff50', 'i_ff10')
      ORDER BY f.fillfactor DESC" >> "$f"

  # Leaf capacity implied by two pages of known contents.  A root leaf page
  # holding one int4 entry leaves 8192 - 16 special - 24 header - 16 tuple
  # - 4 line pointer = 8128 free; an empty leaf page leaves 8148.
  printf 'implied_max_avail one_tuple|empty_leaf\n' >> "$f"
  s "SELECT round(8128 / (1 - one.d / 100)::numeric, 1) || '|' ||
            round(8148 / (1 - zero.d / 100)::numeric, 1)
       FROM (SELECT avg_leaf_density::numeric AS d FROM pgstatindex('bl.c_one_idx'::regclass)) one,
            (SELECT avg_leaf_density::numeric AS d FROM pgstatindex('bl.c_zero_idx'::regclass)) zero" >> "$f"
  printf 'known_page_densities one|zero\n' >> "$f"
  s "SELECT (SELECT round(avg_leaf_density::numeric, 2) FROM pgstatindex('bl.c_one_idx'::regclass)) || '|' ||
            (SELECT round(avg_leaf_density::numeric, 2) FROM pgstatindex('bl.c_zero_idx'::regclass))" >> "$f"

  # VACUUM does not give index pages back; REINDEX does.
  printf 'delhead_after_vacuum=%s dead_pages=%s\n' \
    "$(s "SELECT index_size FROM pgstatindex('bl.i_delhead'::regclass)")" \
    "$(s "SELECT empty_pages + deleted_pages FROM pgstatindex('bl.i_delhead'::regclass)")" >> "$f"

  # The guard fixtures the page reads as rows: the four fillfactor fixtures,
  # the dead-page fixture, the two duplicate builds and the deduplication shape.
  printf 'guard_rows index|size|leaf|dead|density|wasted_ff_pct|est_pct|notes\n' >> "$f"
  s "SELECT f.index_name || '|' || pg_size_pretty(f.index_size) || '|' || f.leaf_pages || '|' ||
            f.dead_pages || '|' ||
            coalesce(round(f.avg_leaf_density::numeric, 2)::text, 'NaN') || '|' ||
            round(100 * f.wasted_vs_fillfactor / f.index_size, 1) || '|' ||
            round(100 * (f.index_size - f.est_rebuilt_bytes) / f.index_size, 1) || '|' ||
            coalesce((SELECT r.notes FROM report_filed r WHERE r.index_name = f.index_name), '(not printed)')
       FROM decide f WHERE f.schema_name = 'bl' ORDER BY f.index_name" >> "$f"

  # Another session's temp index, called directly and left to the statement's
  # own candidate filter.  Each -c is its own transaction, so the temp relation
  # is committed and visible to this session while the sleeping one owns it.
  "$BIN/psql" -X -q -d "$DB" \
    -c "CREATE TEMP TABLE tmp_other(id int)" \
    -c "INSERT INTO tmp_other SELECT g FROM generate_series(1, 300000) g" \
    -c "CREATE INDEX tmp_other_idx ON tmp_other(id)" \
    -c "SELECT pg_sleep(25)" > /dev/null 2>&1 &
  local other=$!
  sleep 8
  {
    printf 'other_temp_error=%s\n' \
      "$(err "SELECT * FROM pgstatindex((SELECT c.oid FROM pg_class c WHERE c.relname = 'tmp_other_idx' AND c.relkind = 'i' LIMIT 1)::regclass)")"
    printf 'other_temp_index_size=%s\n' \
      "$(s "SELECT coalesce(pg_size_pretty(max(pg_relation_size(c.oid))), 'none')
              FROM pg_class c WHERE c.relname = 'tmp_other_idx' AND c.relkind = 'i'")"
    printf 'report_rows_with_other_session=%s\n' \
      "$(( $("$BIN/psql" -X -q -A -F '|' -P footer=off -v ON_ERROR_STOP=1 -d "$DB" -f "$SQLD/report.sql" 2>/dev/null | grep -c '^') - 1 ))"
  } >> "$f"
  wait "$other" 2>/dev/null
  cat "$f" >&2
}

# ----------------------------------------------------------------- cost -----
stage_cost() {
  say "what the statement costs to run"
  : > "$OUT/cost12.txt"
  local f="$OUT/cost12.txt"
  printf 'population %s\n' \
    "$(s "SELECT count(*) || ' B-tree indexes over ' ||
                 sum(pg_relation_size(c.oid)) / current_setting('block_size')::int ||
                 ' blocks, database ' || pg_size_pretty(pg_database_size(current_database()))
            FROM pg_class c JOIN pg_am a ON a.oid = c.relam
           WHERE a.amname = 'btree' AND c.relkind = 'i'")" >> "$f"
  printf 'EXPLAIN (ANALYZE, BUFFERS) of the filed text\n' >> "$f"
  # plan_lines counts only what the EXPLAIN printed, not the lines above it.
  local p0
  p0=$(grep -c '^' "$f")
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" \
    -c "SET statement_timeout = '15min'; SET lock_timeout = '5s';" \
    -c "EXPLAIN (ANALYZE, BUFFERS) $(cat "$SQLD/bare.sql")" >> "$f" 2>&1
  printf 'plan_lines=%s\n' "$(( $(grep -c '^' "$f") - p0 ))" >> "$f"
  printf 'cte_scans=%s\n' "$(grep -c 'CTE Scan' "$f")" >> "$f"
  local i a b
  # The superseded text is timed exactly as it was filed, so it still
  # prefilters at 1 MB and reads fewer indexes than the filed text does; the
  # two timings are for different populations, and the page says so.  A run
  # that fails is marked rather than timed as if it had succeeded.
  printf 'six interleaved end-to-end runs, filed text then superseded text (ms)\n' >> "$f"
  for i in 1 2 3 4 5 6; do
    a=$(date +%s%N)
    "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -o /dev/null -d "$DB" -f "$SQLD/report.sql" > /dev/null 2>&1 \
      || printf 'filed_run_failed ' >> "$f"
    b=$(date +%s%N)
    printf 'filed=%s.%s ' $(( (b - a) / 1000000 )) $(( ((b - a) / 100000) % 10 )) >> "$f"
    if [ -f "$SQLD/prev_bare.sql" ]; then
      a=$(date +%s%N)
      "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -o /dev/null -d "$DB" -f "$SQLD/prev.sql" > /dev/null 2>&1 \
        || printf 'prev_run_failed ' >> "$f"
      b=$(date +%s%N)
      printf 'prev=%s.%s' $(( (b - a) / 1000000 )) $(( ((b - a) / 100000) % 10 )) >> "$f"
    fi
    printf '\n' >> "$f"
  done
  grep -E 'population|Execution Time|plan_lines|cte_scans|filed=|Buffers: shared' "$f" | head -20 >&2
}

# ----------------------------------------------------------------- priv -----
stage_priv() {
  say "who may run it"
  : > "$OUT/priv12.txt"
  local f="$OUT/priv12.txt"
  q "DROP ROLE IF EXISTS mon; DROP ROLE IF EXISTS nomon;
     CREATE ROLE mon LOGIN; CREATE ROLE nomon LOGIN;
     GRANT pg_stat_scan_tables TO mon;" > /dev/null 2>&1 || die "role setup failed"
  # The statement passes an OID column cast to regclass, which resolves no
  # name.  Writing 'bl.i_delhead'::regclass in a test would resolve one, so the
  # OID is read here, as a number, and substituted.
  local oid
  oid=$(s "SELECT 'bl.i_delhead'::regclass::oid")
  {
    printf 'index_oid=%s\n' "$oid"
    printf 'mon_schema_usage=%s\n' \
      "$(s "SELECT has_schema_privilege('mon', 'bl', 'USAGE')::text")"
    printf 'mon_rows_from_statement=%s\n' \
      "$("$BIN/psql" -X -At -q -U mon -d "$DB" -f "$SQLD/report.sql" 2>&1 | grep -c '|')"
    printf 'mon_by_name=%s\n' \
      "$("$BIN/psql" -X -At -q -U mon -d "$DB" -c "SELECT * FROM pgstatindex('bl.i_delhead')" 2>&1 | grep -E '^(ERROR|FATAL)' | head -1)"
    printf 'mon_by_oid_leaf_pages=%s\n' \
      "$("$BIN/psql" -X -At -q -U mon -d "$DB" -c "SELECT leaf_pages FROM pgstatindex($oid::regclass)" 2>&1 | head -1)"
    printf 'nomon_by_oid=%s\n' \
      "$("$BIN/psql" -X -At -q -U nomon -d "$DB" -c "SELECT leaf_pages FROM pgstatindex($oid::regclass)" 2>&1 | head -1)"
  } >> "$f"
  q "DROP ROLE IF EXISTS mon; DROP ROLE IF EXISTS nomon;" > /dev/null
  cat "$f" >&2
}

# -------------------------------------------------------------- compare -----
# The two Follow-up sections on this page compare the filed text with the two
# texts it superseded: the alert_pct/status text and the perfect-packing
# wasted_space text.  This stage re-derives those comparisons on the population
# this run built, so nothing on the page rests on a fixture set that no longer
# exists.  Three questions per pair - what each text prints, which columns its
# internal `final` stage exposes, and whether EXCEPT in both directions over
# the shared columns returns a row - plus the two properties the fillfactor
# rebase is supposed to have: the new column never exceeds the old one and is
# never negative.
# The texts are compared as views inside one query rather than materialized
# one after another, so both sides read the same database state.  Materializing
# them in turn does not work: each pass creates and drops a relation, which
# grows the catalog's own indexes, and those are candidates too - that alone
# produced 29 and 30 differing rows in this stage's first draft.  The price is
# that every comparison reads every page of every index twice.
# Must precede score, which rebuilds every scored index.
stage_compare() {
  say "the filed text against the two texts it superseded"
  [ -f "$SQLD/report.sql" ] || die "run the texts stage first"
  # 17 or 12, taken from this leg's own data directory.
  local leg=${DATA##*/data}
  local f="$OUT/compare$leg.txt"; : > "$f"
  local t src
  for t in now prev alert; do
    case $t in now) src="$SQLD/report.sql" ;; *) src="$SQLD/$t.sql" ;; esac
    [ -f "$src" ] || { note "no $t text; its comparison is skipped"; continue; }
    gen_view "cmp_$t" < "$src" > "$SQLD/cmp_$t.sql"
    fl "$SQLD/cmp_$t.sql" > /dev/null || die "cmp_$t view failed"
    "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -P footer=off -A -F '|' \
      -d "$DB" -f "$src" > "$SQLD/out_$t.txt" 2>&1 || die "the $t text did not run"
    {
      printf '%s_rows=%s\n' "$t" "$(( $(grep -c '^' "$SQLD/out_$t.txt") - 1 ))"
      printf '%s_columns=%s\n' "$t" "$(head -1 "$SQLD/out_$t.txt" | tr '|' '\n' | grep -c '^')"
      printf '%s_bytes=%s\n' "$t" "$(wc -c < "$SQLD/out_$t.txt")"
      printf '%s_final_columns=%s\n' "$t" \
        "$(s "SELECT count(*) FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'cmp_$t'")"
    } >> "$f"
  done

  # The alert text's own verdict column, which is the thing that was removed.
  if [ -f "$SQLD/out_alert.txt" ] && [ -f "$SQLD/out_prev.txt" ]; then
    # Field 14 is status and field 15 is notes, so cutting field 14 is what
    # makes the alert output comparable with the text that dropped the column.
    cut -d'|' -f1-13,15 "$SQLD/out_alert.txt" > "$SQLD/out_alert_cut.txt"
    {
      printf 'alert_status_rebuild_candidate=%s\n' \
        "$(cut -d'|' -f14 "$SQLD/out_alert.txt" | grep -c '^rebuild candidate$')"
      printf 'alert_status_ok=%s\n' "$(cut -d'|' -f14 "$SQLD/out_alert.txt" | grep -c '^ok$')"
      printf 'alert_cut_14_sha256=%s bytes=%s\n' \
        "$(sha256sum < "$SQLD/out_alert_cut.txt" | cut -c1-16)" \
        "$(wc -c < "$SQLD/out_alert_cut.txt")"
      printf 'prev_sha256=%s bytes=%s\n' \
        "$(sha256sum < "$SQLD/out_prev.txt" | cut -c1-16)" \
        "$(wc -c < "$SQLD/out_prev.txt")"
    } >> "$f"
  fi

  # The fillfactor rebase moved presentation fields 9 and 10 and nothing else,
  # so the other twelve are compared with those two cut out of both texts.
  # The superseded text prefiltered at 1 MB and the filed text prefilters
  # nothing, so the two outputs are compared as sets rather than byte for byte:
  # every row the older text printed must appear unchanged in the filed output,
  # and the rows only the filed text prints are the ones that prefilter hid.
  if [ -f "$SQLD/out_prev.txt" ]; then
    cut -d'|' -f1-8,11-14 "$SQLD/out_prev.txt" | sort > "$SQLD/out_prev_untouched.txt"
    cut -d'|' -f1-8,11-14 "$SQLD/out_now.txt"  | sort > "$SQLD/out_now_untouched.txt"
    {
      printf 'prev_untouched_12_rows=%s sha256=%s\n' \
        "$(grep -c '^' "$SQLD/out_prev_untouched.txt")" \
        "$(sha256sum < "$SQLD/out_prev_untouched.txt" | cut -c1-16)"
      printf 'now_untouched_12_rows=%s sha256=%s\n' \
        "$(grep -c '^' "$SQLD/out_now_untouched.txt")" \
        "$(sha256sum < "$SQLD/out_now_untouched.txt" | cut -c1-16)"
      printf 'prev_rows_missing_from_now=%s\n' \
        "$(comm -23 "$SQLD/out_prev_untouched.txt" "$SQLD/out_now_untouched.txt" | grep -c '^')"
      printf 'rows_only_now_prints=%s\n' \
        "$(comm -13 "$SQLD/out_prev_untouched.txt" "$SQLD/out_now_untouched.txt" | grep -c '^')"
    } >> "$f"
  fi

  cmp_pair alert prev >> "$f"
  cmp_pair prev  now  >> "$f"

  # What the fillfactor rebase is supposed to guarantee, over every index in
  # the database, which since the size prefilter went is also every row the
  # report prints.  One query per question, so both texts read one state.
  if [ -n "$(s "SELECT to_regclass('cmp_prev') IS NOT NULL OR NULL")" ]; then
    {
      printf 'indexes_compared=%s\n' "$(s 'SELECT count(*) FROM cmp_now')"
      printf 'now_wasted_exceeds_prev=%s\n' \
        "$(s "SELECT count(*) FROM cmp_now n JOIN cmp_prev p ON p.idx_oid = n.idx_oid
               WHERE n.wasted_vs_fillfactor > p.wasted_space")"
      printf 'now_wasted_negative=%s\n' \
        "$(s 'SELECT count(*) FROM cmp_now WHERE wasted_vs_fillfactor < 0')"
      printf 'two_definitions_equal=%s\n' \
        "$(s "SELECT count(*) FROM cmp_now n JOIN cmp_prev p ON p.idx_oid = n.idx_oid
               WHERE n.wasted_vs_fillfactor = p.wasted_space")"
      printf 'leaf_term_clamped_to_zero=%s\n' \
        "$(s "SELECT count(*) FROM cmp_now
               WHERE round(leaf_bytes * target_density) - live_leaf_bytes < 0")"
      printf 'reported_rows_clamped=%s\n' \
        "$(s "SELECT count(*) FROM cmp_now c JOIN report_filed r ON r.index_name = c.index_name
               WHERE round(c.leaf_bytes * c.target_density) - c.live_leaf_bytes < 0")"
    } >> "$f"
  fi
  cat "$f" >&2
}

# cmp_pair <a> <b>: the internal `final` stage of one text against another -
# the columns only one of them exposes, and EXCEPT in both directions over
# every column both expose, evaluated in one query so that both texts read the
# same index state.  A one-for-one column swap and 0 differing rows is what
# "nothing else the statement returns moved" means.
cmp_pair() {
  local a=$1 b=$2 cols
  [ -n "$(s "SELECT to_regclass('cmp_$a') IS NOT NULL OR NULL")" ] || return 0
  [ -n "$(s "SELECT to_regclass('cmp_$b') IS NOT NULL OR NULL")" ] || return 0
  printf '%s_vs_%s only_in_%s=%s\n' "$a" "$b" "$a" \
    "$(s "SELECT coalesce(string_agg(column_name, ','), 'none') FROM (
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'cmp_$a'
            EXCEPT
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'cmp_$b') x")"
  printf '%s_vs_%s only_in_%s=%s\n' "$a" "$b" "$b" \
    "$(s "SELECT coalesce(string_agg(column_name, ','), 'none') FROM (
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'cmp_$b'
            EXCEPT
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'cmp_$a') x")"
  cols=$(s "SELECT string_agg(quote_ident(column_name), ', ' ORDER BY column_name) FROM (
              SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'cmp_$a'
              INTERSECT
              SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'cmp_$b') x")
  printf '%s_vs_%s shared_columns=%s except_both_ways=%s\n' "$a" "$b" \
    "$(s "SELECT count(*) FROM information_schema.columns c
           WHERE c.table_schema = 'public' AND c.table_name = 'cmp_$a'
             AND c.column_name IN (SELECT column_name FROM information_schema.columns
                                    WHERE table_schema = 'public'
                                      AND table_name = 'cmp_$b')")" \
    "$(s "SELECT (SELECT count(*) FROM (SELECT $cols FROM cmp_$a
                                        EXCEPT SELECT $cols FROM cmp_$b) u)
               + (SELECT count(*) FROM (SELECT $cols FROM cmp_$b
                                        EXCEPT SELECT $cols FROM cmp_$a) v)")"
}

# ---------------------------------------------------------------- score -----
# Phase 5: the oracle.  score_all() reads what the statement said about each
# churned fixture, calls pgstatindex itself, rebuilds the index and measures the
# file again; the verdicts view then applies the shared suite's four bands.
# DESTRUCTIVE: it rebuilds every scored index, so report, decide, facts, cost,
# priv and compare must all precede it.
stage_score() {
  say "score every fixture against a measured REINDEX INDEX"
  [ -n "$(s 'SELECT 1 FROM decide LIMIT 1')" ] || die "run the decide stage first"
  fl /dev/stdin <<'SQL' || die "scoring failed"
SET /* wiki_pgsi_score_statement_timeout */ statement_timeout = '900s';
SET /* wiki_pgsi_score_lock_timeout */ lock_timeout = '5s';
CALL /* wiki_pgsi_score_all */ score_all();
SQL
  local out="$OUT/verdicts12.txt"
  t "SELECT /* wiki_pgsi_verdict_rows */ num, leg, grp, idx, blocks_built,
            blocks_before, blocks_after, actual, est_pct, wasted_ff_pct,
            density, dead_pages, reported, taken_stage, taken_nofilter,
            expected_stage, want_stage, verdict, verdict_nofilter, lost_by, notes
       FROM verdicts ORDER BY num, leg" > "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_family_counts */ grp, verdict, count(*)
       FROM verdicts GROUP BY 1, 2 ORDER BY 1, 2" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_totals */ verdict, count(*)
       FROM verdicts GROUP BY 1 ORDER BY 2 DESC" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_totals_nofilter */ verdict_nofilter, count(*)
       FROM verdicts GROUP BY 1 ORDER BY 2 DESC" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_agreement */
            count(*) AS fixtures,
            count(*) FILTER (WHERE reported)                          AS reported,
            count(*) FILTER (WHERE taken_stage = 'rebuild')           AS rebuilt,
            count(*) FILTER (WHERE taken_nofilter = 'rebuild')        AS rebuilt_nofilter,
            count(*) FILTER (WHERE expected_stage = taken_nofilter)   AS instrument_agrees,
            count(*) FILTER (WHERE expected_stage <> taken_nofilter)  AS instrument_disagrees,
            count(*) FILTER (WHERE want_stage = taken_nofilter)       AS want_hit,
            count(*) FILTER (WHERE want_stage <> taken_nofilter)      AS want_miss,
            count(*) FILTER (WHERE NOT contract_ok)                   AS contract_failures,
            count(*) FILTER (WHERE NOT view_matches_report)           AS view_report_mismatch
       FROM verdicts" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_lost */ num, leg, idx, lost_by, est_pct, actual,
            density, dead_pages, blocks_before
       FROM verdicts WHERE lost_by IS NOT NULL ORDER BY num, leg" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_false_positives */ num, leg, idx, est_pct, actual,
            density, dead_pages, notes
       FROM verdicts WHERE verdict LIKE '%FALSE POSITIVE' ORDER BY num, leg" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_want_miss */ num, leg, idx, want_stage,
            taken_nofilter, taken_stage, verdict, est_pct, actual
       FROM verdicts WHERE want_stage <> taken_nofilter ORDER BY num, leg" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_rebuild_returns */
            count(*) AS rebuild_decisions,
            round(avg(actual), 1) AS mean_actual,
            min(actual) AS min_actual, max(actual) AS max_actual
       FROM verdicts WHERE taken_stage = 'rebuild'" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_error */
            count(*) AS scored,
            count(*) FILTER (WHERE abs(est_pct - actual) <= 1.0) AS within_1_point,
            count(*) FILTER (WHERE abs(est_pct - actual) <= 5.0) AS within_5_points,
            round(max(est_pct - actual), 1) AS worst_over,
            round(min(est_pct - actual), 1) AS worst_under
       FROM verdicts" >> "$out" 2>&1
  # Rule 2's post-churn shape, per fixture and in total: the distribution the
  # drain actually produced, and the fixtures predicted reclaimable whose
  # space never arrived in the file.
  t "SELECT /* wiki_pgsi_verdict_shape */ shape, want_stage, count(*)
       FROM verdicts GROUP BY 1, 2 ORDER BY 1, 2" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_shape_failed */ num, leg, idx, shape, density,
            dead_pages, est_pct, actual
       FROM verdicts WHERE shape_ok IS FALSE ORDER BY num, leg" >> "$out" 2>&1
  # The no-defeat rule's proofs, per fixture rather than per statement: the
  # page classes the maintenance left on this fixture's index, beside the
  # verdict it earned.  pageclass is read before the report, decide and oracle
  # passes, so these are the classes the statement was asked about.
  t "SELECT /* wiki_pgsi_verdict_maintenance */ v.num, v.leg, v.idx, v.verdict,
            pc.leaf_pages AS leaf_after_maint, pc.deleted_pages, pc.empty_pages,
            pc.avg_leaf_density AS density_after_maint, v.actual
       FROM verdicts v LEFT JOIN pageclass pc ON pc.idx = v.idx
      ORDER BY v.num, v.leg" >> "$out" 2>&1
  t "SELECT /* wiki_pgsi_verdict_maintenance_totals */
            count(*) AS fixtures,
            count(*) FILTER (WHERE pc.idx IS NULL) AS without_page_classes,
            count(*) FILTER (WHERE pc.deleted_pages > 0) AS with_deleted_pages,
            coalesce(sum(pc.deleted_pages), 0) AS deleted_pages_total
       FROM verdicts v LEFT JOIN pageclass pc ON pc.idx = v.idx" >> "$out" 2>&1
  note "$(s "SELECT count(*) || ' scored, ' ||
              count(*) FILTER (WHERE verdict = 'PASS') || ' PASS, ' ||
              count(*) FILTER (WHERE verdict = 'CRITICAL FALSE POSITIVE') || ' CFP, ' ||
              count(*) FILTER (WHERE verdict = 'FALSE POSITIVE') || ' FP, ' ||
              count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE') || ' FN'
                FROM verdicts")"
  tail -40 "$out" >&2
}

# ---------------------------------------------------------------- guard -----
# The guard and model fixtures get the same oracle the suite fixtures get, so
# that every number this page reports about them is measured and not modelled:
# one REINDEX INDEX per index in schema bl, the file measured before and after,
# and the statement re-read afterwards for the post-rebuild residual.  No
# verdict band is applied here, because these are not suite fixtures.
# DESTRUCTIVE: it rebuilds every index in schema bl.
stage_guard() {
  say "oracle pass over the bl guard and model fixtures"
  [ -n "$(s "SELECT 1 FROM decide WHERE schema_name = 'bl' LIMIT 1")" ] \
    || die "run the decide stage first"
  q "DROP TABLE IF EXISTS guard;
     CREATE TABLE guard AS
       SELECT /* wiki_pgsi_guard_before */
              d.index_name, d.idx_oid, d.index_size, d.leaf_pages, d.dead_pages,
              d.avg_leaf_density AS density, d.fillfactor,
              round(100 * d.target_density, 2) AS target_density,
              round(100 * d.wasted_vs_fillfactor / d.index_size, 1) AS wasted_ff_pct,
              round(100 * (d.index_size - d.est_rebuilt_bytes) / d.index_size, 1) AS est_pct,
              pg_relation_size(d.idx_oid) AS before_bytes,
              0::bigint AS after_bytes, 0::numeric AS residual_pct
         FROM decide d WHERE d.schema_name = 'bl';" > /dev/null \
    || die "guard snapshot failed"
  s "SELECT /* wiki_pgsi_guard_generator */ 'REINDEX /* wiki_pgsi_guard_reindex */ INDEX bl.' || quote_ident(index_name) || ';'
       FROM guard ORDER BY index_name" > "$SQLD/guard_reindex.sql"
  fl "$SQLD/guard_reindex.sql" > /dev/null || die "guard REINDEX pass failed"
  q "UPDATE /* wiki_pgsi_guard_after */ guard g SET after_bytes = pg_relation_size(g.idx_oid);
     UPDATE /* wiki_pgsi_guard_residual */ guard g SET residual_pct = r.pct
       FROM (SELECT f.index_name,
                    round(100 * f.wasted_vs_fillfactor / f.index_size, 1) AS pct
               FROM bloat_final f WHERE f.schema_name = 'bl') r
      WHERE r.index_name = g.index_name;" > /dev/null || die "guard after-pass failed"
  t "SELECT /* wiki_pgsi_guard_rows */ index_name, pg_size_pretty(index_size) AS size,
            leaf_pages, dead_pages, round(density::numeric, 2) AS density,
            fillfactor, target_density, wasted_ff_pct, est_pct,
            round(100 * (before_bytes - after_bytes)::numeric
                  / greatest(before_bytes, 1), 1) AS actual_pct,
            residual_pct, before_bytes, after_bytes
       FROM guard ORDER BY index_name" > "$OUT/guard12.txt" 2>&1
  t "SELECT /* wiki_pgsi_guard_error */ count(*) AS guard_indexes,
            count(*) FILTER (WHERE abs(est_pct - round(100 * (before_bytes - after_bytes)::numeric
                                        / greatest(before_bytes, 1), 1)) <= 1.0) AS within_1_point,
            round(max(est_pct - round(100 * (before_bytes - after_bytes)::numeric
                                      / greatest(before_bytes, 1), 1)), 1) AS worst_over,
            round(min(est_pct - round(100 * (before_bytes - after_bytes)::numeric
                                      / greatest(before_bytes, 1), 1)), 1) AS worst_under
       FROM guard" >> "$OUT/guard12.txt" 2>&1
  cat "$OUT/guard12.txt" >&2
}

# ------------------------------------------------------------- residual -----
# A rebuilt index must report no waste at its own fillfactor.  Reads exactly
# the population the score stage rebuilt.
stage_residual() {
  say "post-REINDEX residual of wasted_vs_fillfactor"
  [ -n "$(s 'SELECT 1 FROM res LIMIT 1')" ] || die "run the score stage first"
  q "DROP TABLE IF EXISTS residual;
     CREATE TABLE residual AS
       SELECT /* wiki_pgsi_residual */
              f.index_name, f.index_size, f.leaf_pages, f.avg_leaf_density,
              f.wasted_vs_fillfactor AS residual_bytes,
              round(100 * f.wasted_vs_fillfactor / f.index_size, 1) AS residual_pct,
              round(100 * (f.index_size - f.est_rebuilt_bytes) / f.index_size, 1) AS est_pct
         FROM bloat_final f
        WHERE f.index_name IN (SELECT idx FROM plan);" > /dev/null \
    || die "residual pass failed"
  {
    t "SELECT /* wiki_pgsi_residual_totals */
              count(*) AS rebuilt_indexes,
              count(*) FILTER (WHERE residual_bytes = 0) AS exactly_zero,
              count(*) FILTER (WHERE residual_pct <= 0.1) AS at_or_below_0_1pct,
              max(residual_pct) AS worst_residual_pct,
              max(est_pct) AS worst_est_pct
         FROM residual"
    t "SELECT /* wiki_pgsi_residual_worst */ index_name, index_size, leaf_pages,
              round(avg_leaf_density::numeric, 2) AS density, residual_bytes, residual_pct
         FROM residual ORDER BY residual_pct DESC, index_name LIMIT 8"
    t "SELECT /* wiki_pgsi_residual_over_1mb */
              count(*) AS at_or_above_1mb,
              max(residual_pct) AS worst_residual_pct
         FROM residual WHERE index_size >= 1024 * 1024"
  } > "$OUT/residual12.txt" 2>&1
  cat "$OUT/residual12.txt" >&2
}

# ----------------------------------------------------------------- race -----
# Two shapes of interference, both driven from a second session:
#   lock_timeout   an uncommitted DROP INDEX holds AccessExclusiveLock and the
#                  call is cancelled at the timeout
#   committed drop the same drop commits while the report waits, so
#                  relation_open finds nothing behind the lock
stage_race() {
  say "locking and the concurrent-drop race"
  : > "$OUT/race12.txt"
  local f="$OUT/race12.txt" a b msg
  "$BIN/psql" -X -q -d "$DB" -c \
    "BEGIN; DROP INDEX bl.i_race; SELECT pg_sleep(8); ROLLBACK;" > /dev/null 2>&1 &
  local holder=$!
  sleep 2
  a=$(date +%s%N)
  msg=$(err "SET lock_timeout = '2s'; SELECT * FROM pgstatindex('bl.i_race'::regclass)")
  b=$(date +%s%N)
  printf 'lock_timeout_error=%s\n' "$msg" >> "$f"
  printf 'lock_timeout_ms=%s.%s\n' $(( (b - a) / 1000000 )) $(( ((b - a) / 100000) % 10 )) >> "$f"
  wait "$holder" 2>/dev/null

  # Case 1: the drop commits while cand is still being materialized.  cand no
  # longer opens any relation - the size prefilter that used to absorb such a
  # drop through pg_relation_size's try_relation_open is gone - so the dropped
  # index stays in the candidate list and pgstatindex's own relation_open
  # decides the outcome.  Whatever happens is recorded, error or not.
  local before after defn
  defn=$(s "SELECT pg_get_indexdef('bl.i_race'::regclass)")
  before=$(( $("$BIN/psql" -X -q -A -F '|' -P footer=off -d "$DB" -f "$SQLD/report.sql" 2>/dev/null | grep -c '^') - 1 ))
  "$BIN/psql" -X -q -d "$DB" -c \
    "BEGIN; DROP INDEX bl.i_race; SELECT pg_sleep(3); COMMIT;" > /dev/null 2>&1 &
  local dropper=$!
  sleep 1
  a=$(date +%s%N)
  # psql prefixes an error from -f with "psql:<file>:<line>: ", so the match
  # cannot be anchored at the start of the line; the prefix is then cut.
  "$BIN/psql" -X -q -A -F '|' -P footer=off -d "$DB" -f "$SQLD/report.sql" \
    > "$OUT/race_during12.txt" 2>&1
  b=$(date +%s%N)
  wait "$dropper" 2>/dev/null
  msg=$(grep -E '(ERROR|FATAL):' "$OUT/race_during12.txt" | head -1 | sed 's/^psql:[^ ]* //')
  after=$(( $(grep -c '^' "$OUT/race_during12.txt") - 1 ))
  printf 'drop_during_cand_error=%s\n' "${msg:-none}" >> "$f"
  printf 'drop_during_cand_rows=%s (was %s)\n' "$after" "$before" >> "$f"
  printf 'drop_during_cand_ms=%s\n' $(( (b - a) / 1000000 )) >> "$f"
  q "$defn" > /dev/null 2>&1

  # Case 2: the drop lands after cand has been materialized but before
  # pgstatindex reaches that index.  Without a size check the window is the
  # whole report rather than the gap between two calls on one index, so the
  # same sweep of delays is run and whatever it lands in is recorded.
  local target d attempts=0 hit=
  target=i_race
  printf 'drop_after_cand_target=%s\n' "$target" >> "$f"
  for d in 0.005 0.02 0.05 0.1 0.2 0.4 0.8 1.2 1.6 2.0; do
    a=$(date +%s%N)
    "$BIN/psql" -X -q -d "$DB" \
      -c "SELECT pg_sleep($d)" \
      -c "BEGIN; DROP INDEX bl.$target; SELECT pg_sleep(2); COMMIT;" > /dev/null 2>&1 &
    local dp=$!
    "$BIN/psql" -X -q -d "$DB" -f "$SQLD/report.sql" > "$OUT/race_after12.txt" 2>&1
    b=$(date +%s%N)
    wait "$dp" 2>/dev/null
    attempts=$((attempts + 1))
    msg=$(grep -E '(ERROR|FATAL):' "$OUT/race_after12.txt" | head -1 | sed 's/^psql:[^ ]* //')
    q "$defn" > /dev/null 2>&1
    case $msg in
      *"could not open relation"*)
        hit="$msg after $(( (b - a) / 1000000 )) ms, drop taken ${d}s in"; break ;;
    esac
  done
  printf 'drop_after_cand_error=%s\n' "${hit:-not reproduced in $attempts attempts}" >> "$f"
  printf 'drop_after_cand_attempts=%s\n' "$attempts" >> "$f"
  cat "$f" >&2
}

# --------------------------------------------------------------- errors -----
# Every server-side error this run provokes is deliberate: the ten refusals and
# the privilege checks of the facts and priv stages, the lock timeout and the
# concurrent drop of the race stage, and - on a server that lacks a feature -
# the fixture builds the suite records as skips.  This stage counts what the
# server logged after the run mark and prints the distinct messages, so an
# error no stage asked for is visible.
stage_errors() {
  say "server-error audit"
  local log="$OUT/server12.log" from
  [ -f "$log" ] || { note "no server log"; return 0; }
  # From the last run mark only, so a re-run in the same cluster does not
  # inherit the errors of the run before it.
  from=$(grep -n 'wiki_pgsi_run_mark' "$log" | tail -1 | cut -d: -f1)
  if [ -n "${from:-}" ]; then
    sed -n "${from},\$p" "$log" > "$OUT/log_since_mark12.txt"
  else
    cp "$log" "$OUT/log_since_mark12.txt"
  fi
  {
    printf 'errors_logged=%s\n' "$(grep -c 'ERROR:' "$OUT/log_since_mark12.txt")"
    printf 'fatals_logged=%s\n' "$(grep -c 'FATAL:' "$OUT/log_since_mark12.txt")"
    printf -- '-- distinct messages\n'
    grep -oE '(ERROR|FATAL):.*' "$OUT/log_since_mark12.txt" | sort | uniq -c | sort -rn
  } > "$OUT/errors12.txt"
  cat "$OUT/errors12.txt" >&2
}

# ------------------------------------------------------------- crossleg -----
# The one comparison neither leg can make from its own server: the two reports
# side by side.  Both legs write their psql output into the shared out/, so
# this stage is pure text and needs no connection.  Fields 1 and 2 are
# schema_name and index_name, and that pair is unique inside each database, so
# it is the join key: how many keys both reports print, how many of those rows
# are identical field for field, which keys only one leg has, and the same
# counts broken down by schema, because the report now covers the catalog and
# TOAST indexes as well as the fixtures.  It runs last, because it needs the
# 17 leg's report stage to have written its file.
stage_crossleg() {
  say "the two majors' reports, side by side"
  local a="$OUT/report17.txt" b="$OUT/report12.txt" f="$OUT/crossleg.txt"
  [ -f "$b" ] || die "no $b; run this leg's report stage first"
  [ -f "$a" ] || { note "no $a yet; run the 17 leg's report stage, then this stage"; return 0; }
  : > "$f"
  # The header line is dropped, and every list is sorted under one collation so
  # that comm can be used on it.
  tail -n +2 "$a" | LC_ALL=C sort > "$SQLD/x17_rows.txt"
  tail -n +2 "$b" | LC_ALL=C sort > "$SQLD/x12_rows.txt"
  cut -d'|' -f1,2 "$SQLD/x17_rows.txt" | LC_ALL=C sort > "$SQLD/x17_keys.txt"
  cut -d'|' -f1,2 "$SQLD/x12_rows.txt" | LC_ALL=C sort > "$SQLD/x12_keys.txt"
  LC_ALL=C comm -12 "$SQLD/x17_keys.txt" "$SQLD/x12_keys.txt" > "$SQLD/x_shared_keys.txt"
  # A row counts as identical when the whole 14-field line appears in both.
  LC_ALL=C comm -12 "$SQLD/x17_rows.txt" "$SQLD/x12_rows.txt" > "$SQLD/x_same_rows.txt"
  cut -d'|' -f1,2 "$SQLD/x_same_rows.txt" | LC_ALL=C sort > "$SQLD/x_same_keys.txt"
  LC_ALL=C comm -23 "$SQLD/x_shared_keys.txt" "$SQLD/x_same_keys.txt" > "$SQLD/x_diff_keys.txt"
  LC_ALL=C comm -23 "$SQLD/x17_keys.txt" "$SQLD/x12_keys.txt" > "$SQLD/x_only17_keys.txt"
  LC_ALL=C comm -13 "$SQLD/x17_keys.txt" "$SQLD/x12_keys.txt" > "$SQLD/x_only12_keys.txt"
  {
    printf 'rows_17=%s\n' "$(grep -c '^' "$SQLD/x17_rows.txt")"
    printf 'rows_12=%s\n' "$(grep -c '^' "$SQLD/x12_rows.txt")"
    printf 'keys_both_print=%s\n' "$(grep -c '^' "$SQLD/x_shared_keys.txt")"
    printf 'rows_identical=%s\n' "$(grep -c '^' "$SQLD/x_same_rows.txt")"
    printf 'shared_keys_that_differ=%s\n' "$(grep -c '^' "$SQLD/x_diff_keys.txt")"
    printf 'keys_only_17=%s\n' "$(grep -c '^' "$SQLD/x_only17_keys.txt")"
    printf 'keys_only_12=%s\n' "$(grep -c '^' "$SQLD/x_only12_keys.txt")"
    local list
    for list in x17_keys x12_keys x_shared_keys x_same_keys x_diff_keys \
                x_only17_keys x_only12_keys; do
      printf -- '-- %s by schema\n' "$list"
      cut -d'|' -f1 "$SQLD/$list.txt" | LC_ALL=C sort | uniq -c
    done
    # Field 5 is leaf_pages, the one whole number in the output that says how
    # big the file is without a unit to parse.  Which way the differing rows
    # lean is the question deduplication and the insert-time deletion pass
    # answer, so it is counted rather than asserted.
    printf -- '-- shared keys whose rows differ: key, leaf pages 17, leaf pages 12\n'
    local k l17 l12 fewer=0 more=0 same=0
    while IFS= read -r k; do
      l17=$(grep -m1 "^$k|" "$SQLD/x17_rows.txt" | cut -d'|' -f5)
      l12=$(grep -m1 "^$k|" "$SQLD/x12_rows.txt" | cut -d'|' -f5)
      printf '%s|%s|%s\n' "$k" "$l17" "$l12"
      if   [ "$l17" -lt "$l12" ] 2>/dev/null; then fewer=$((fewer + 1))
      elif [ "$l17" -gt "$l12" ] 2>/dev/null; then more=$((more + 1))
      else same=$((same + 1)); fi
    done < "$SQLD/x_diff_keys.txt"
    printf 'differing_rows_with_fewer_leaves_on_17=%s\n' "$fewer"
    printf 'differing_rows_with_more_leaves_on_17=%s\n' "$more"
    printf 'differing_rows_with_equal_leaves=%s\n' "$same"
    printf -- '-- keys only the 17 report prints\n'
    cat "$SQLD/x_only17_keys.txt"
    printf -- '-- keys only the 12 report prints\n'
    cat "$SQLD/x_only12_keys.txt"
  } >> "$f"
  head -8 "$f" >&2
}

# -------------------------------------------------------------- summary -----
stage_summary() {
  say "what landed in $OUT"
  ls -la "$OUT" >&2
  local x
  for x in platform12 exact12 decide12 maint_proofs12 facts12 cost12 priv12 compare12 race12 errors12 skipped12 crossleg; do
    [ -f "$OUT/$x.txt" ] && { printf '\n---- %s\n' "$x" >&2; cat "$OUT/$x.txt" >&2; }
  done
  [ -f "$OUT/verdicts12.txt" ] && { printf '\n---- verdicts12 (tail)\n' >&2; tail -40 "$OUT/verdicts12.txt" >&2; }
  [ -f "$OUT/residual12.txt" ] && { printf '\n---- residual12\n' >&2; cat "$OUT/residual12.txt" >&2; }
}

# ---------------------------------------------------------------- stop -------
stage_stop() {
  say "stop the 12.2 cluster"
  [ -d "$DATA" ] || { note "no data directory"; return 0; }
  if "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1 || die "pg_ctl stop failed"
  fi
  [ -f "$DATA/postmaster.pid" ] && die "postmaster.pid still present in $DATA"
  pgrep -f "postgres.*-D $DATA" > /dev/null 2>&1 && die "a postgres process still runs on $DATA"
  [ -n "$(ls -A "$SOCK" 2>/dev/null)" ] && die "socket directory $SOCK is not empty"
  note "stopped: no postmaster.pid, no process, empty socket directory"
}

# This leg deletes only its own five directories; the 17 leg owns the shared
# out/ and removes the sandbox itself, so run its clean last.
stage_clean() {
  stage_stop || exit 1
  case "$SANDBOX" in
    "$WIKI_ROOT"/.wiki-runtime/tmp/?*) ;;
    *) die "refusing to delete under $SANDBOX: not under $WIKI_ROOT/.wiki-runtime/tmp/" ;;
  esac
  say "delete this leg's directories under $SANDBOX"
  rm -rf "$BUILD" "$INST" "$DATA" "$SOCK" "$SQLD"
}

# ------------------------------------------------------------ dispatcher -----
STAGES_DEFAULT="build check cluster texts fixtures suite churn report decide facts cost priv compare score guard residual race errors crossleg summary"
run_stage() {
  case "$1" in
    build|check|cluster|texts|fixtures|suite|churn|report|decide|facts|cost|priv|compare|score|guard|residual|race|errors|crossleg|summary|stop|clean)
      "stage_$1" ;;
    *) die "unknown stage: $1" ;;
  esac
}
main() {
  local st
  if [ "$#" -eq 0 ]; then set -- $STAGES_DEFAULT; fi
  # One run mark per invocation, so the error audit reads this invocation's
  # errors and not an earlier one's.  On a first run the log does not exist
  # yet and the cluster stage writes the mark instead.
  [ -f "$OUT/server12.log" ] \
    && printf -- '-- wiki_pgsi_run_mark %s\n' "$(date -u +%FT%TZ)" >> "$OUT/server12.log"
  for st in "$@"; do run_stage "$st" || die "stage $st failed"; done
  say "done: $*"
}
main "$@"
```


### The last run

| Fact | Value |
|---|---|
| Date | 2026-09-16, the pass that brought this page onto the concept page's rule `### The maintenance must not be defeated`. Both legs started at 20:53 UTC, one invocation each, every stage in the default order |
| Host | Linux x86_64, Ubuntu 24.04, gcc 13.3.0, ICU 74.2, 22 cores, `uname -sm` recorded into `out/platform17.txt` and `out/platform12.txt`; the host has `pkg-config`, so neither build needed `ICU_CFLAGS` or `ICU_LIBS` |
| 17 leg | 17.11 (`server_version_num` 170011) built from `786db8dcf168bd9df8f55047337525ac19118b1c`, `--enable-debug --with-icu --with-readline --with-zlib`; `make check` **All 225 tests passed**, `contrib/pgstattuple` **All 1** |
| 12 leg | 12.2 (120002) built from `45b88269a353ad93744772791feb6d01bc7e1e42`, the same flags plus `CFLAGS="-O2 -g -DTRUE=1 -DFALSE=0"`; `make check` **All 192 tests passed**, `contrib/pgstattuple` **All 1** |
| Platform facts the numbers depend on | `block_size` 8192, `max_data_alignment` 8, `initdb --locale=C --encoding=UTF8`, `pgstattuple` 1.5 on both, `autovacuum_analyze_threshold` 50, `autovacuum_analyze_scale_factor` 0.1 |
| Scored population | the shared suite, 113 numbered tests, of which this port attempts 126 fixtures: **126 planned and scored on 17.11, 117 planned and scored on 12.2** after 9 recorded skips, every one a fixture that needs a B-tree support function 4; test 120's precondition held on both legs this time; plus 18 and 17 `bl` guard fixtures with their own oracle |
| Maintenance | **67 statements per leg**, each one `VACUUM (VERBOSE, ANALYZE)` between `maint_begin()` and `maint_end()`; all completed, `dead but not yet removable` **0 on every one**, **73 of 73** horizon probes clean on each leg, one timeout set per leg, **0** skip or cancellation lines; see [The maintenance, proved not defeated](#the-maintenance-proved-not-defeated) |
| Database | 4,394 MB and 370 B-tree indexes over 151,667 blocks on 17.11; 4,416 MB and 355 over 157,249 on 12.2, both as the `cost` stage measured them before the oracle passes |
| Rows the filed text printed | **365** on 17.11 and **350** on 12.2, 14 columns and 36,740 and 35,291 bytes |
| Statement text | `sql` block 1, SHA-256 `3d4507a54b38ac3edfaffd41f29c91518d6032dd561a025f343bbeb3c0c55b5d`, 123 lines, 5,976 bytes, executed unmodified on both |
| Suite text | `sql` blocks 2 to 6, SHA-256 `87f6a505e42e…`, `d73fb4d59989…`, `713d503da008…`, `72711d3ece42…`, `9ac052745ce9…`, and 426, 184, 1,023, 73 and 201 lines, all hash-checked before the run. Four of the five changed in this revision, block 3 did not; see [How this was measured](#how-this-was-measured) |
| Superseded texts | `sql` block 1 at `cbbbd16`, SHA-256 `f5b995d3c5d5…`, 122 lines, 5,839 bytes; and at `0dbabb6`, SHA-256 `da4f4277b24e…`, 125 lines, 6,002 bytes. Both hash-checked, both executed, both compared against the filed text |
| Stages run | every stage, in the default order, on each leg, plus the 12 leg's `crossleg` |
| Runtime | both legs run concurrently at `JOBS=10`, on trees built earlier the same day: **2 minutes 42 seconds** end to end for the 17 leg and **8 minutes 27 seconds** for the 12 leg, whose `fixtures suite churn` alone took about 7 minutes 15 seconds because `wiki_flush()` has to sleep out the publish interval on that major. The stage split is read from the output files' modification times, not from a timer in the scripts |
| Server errors | 17 on 17.11 and 16 on 12.2, every one raised by a stage that asked for it; 0 `FATAL` |
| Teardown | the 12 leg's `clean` and then the 17 leg's stopped both servers with `pg_ctl -m fast -w stop`, confirmed no `postmaster.pid`, no postgres process and an empty socket directory, and deleted the sandbox; afterwards no postgres process was running and ports 55417 and 55412 were free |

Every number on this page comes from this run, except the four readings of
retired fixtures that
[The blind spot the suite stopped building](#the-blind-spot-the-suite-stopped-building)
labels as the 2026-09-12 review run's and keeps only as history, the figures the
two history subsections attribute to their own runs, and the plan shapes and
timings the two `Follow-up` sections attribute to the revisions that made those
edits. What still keeps `verified_by_agent` at `not yet` is listed under
[Open Questions](#open-questions): nothing there is a number these scripts
failed to produce, but three claims on the page are source readings the current
fixtures do not exercise — the index-vacuum bypass, the unvacuumed blind spot
the narrowing removed, and the unlogged-on-a-standby filter — and one is a
cross-version attribution this page's evidence base cannot settle.

## Context Reviewed

- `contrib/pgstattuple/pgstatindex.c` in the v17 checkout, function by
  function: the four `pgstatindex` entry points, `pgstatindex_impl`, and the
  `pgstatginindex`/`pgstathashindex` neighbours that share its guards.
- `contrib/pgstattuple/pgstattuple--1.4.sql`, `pgstattuple--1.4--1.5.sql` and
  `pgstattuple.control` in the v17 checkout. That one statement can target
  12.2 as well rests on measurement, not on a reading of the v12 files: the
  12.2 server installed the extension at version 1.5 and ran the filed text
  unmodified.
- `contrib/pgstattuple/sql/pgstattuple.sql` and `expected/pgstattuple.out`, for
  the upstream expectations on empty indexes, wrong access methods, partitioned
  indexes, views, foreign tables and sequences.
- `doc/src/sgml/pgstattuple.sgml`, for the documented column meanings and the
  `pg_stat_scan_tables` access rule.
- `src/backend/access/nbtree/nbtsort.c` and `src/include/access/nbtree.h`, for
  what a rebuild targets: `_bt_pagestate`, `_bt_buildadd`, `BTGetFillFactor`,
  `BTGetTargetPageFreeSpace`, the fillfactor constants, and the page-opaque
  layout.
- `src/backend/access/nbtree/nbtree.c`, for what a vacuum does with deleted pages,
  and the absence of any truncation call under `src/backend/access/nbtree/`.
- `src/include/storage/bufpage.h` and `src/backend/storage/page/bufpage.c`, for
  `SizeOfPageHeaderData` and the line-pointer deduction in `PageGetFreeSpace`.
- `src/include/catalog/pg_index.h`, `pg_class.h` and `src/include/utils/rel.h`,
  for the catalog columns and the temp-relation test the filters mirror.
- `src/backend/utils/misc/guc_tables.c` for the two timeout GUCs' contexts, and
  `src/backend/optimizer/util/plancat.c` for the unlogged-during-recovery rule
  that does not apply to function calls.
- The v17 checkout's own history for `13503eb5905`, and its tag list, which is
  empty, so no containing release can be named from it.
- The ten-column result tuple `pgstatindex` builds
  ([pgstatindex.c#result-tuple](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L339-L378)),
  re-read when the threshold was removed: the statement consumes eight of the ten
  (`version`, `index_size`, `internal_pages`, `leaf_pages`, `empty_pages`,
  `deleted_pages`, `avg_leaf_density`, `leaf_fragmentation`), leaves `tree_level`
  and `root_block_no` unused, and none of them was reached through the removed
  `alert_pct`.
- `src/backend/access/nbtree/nbtsplitloc.c`, re-read when wasted space was
  rebased on the fillfactor, and again in this revision for the
  split-after-new-item branch: `_bt_findsplitloc` reads `BTGetFillFactor` but
  applies it as `fillfactormult` only on a rightmost leaf or when
  `_bt_afternewitemoff` detects a localized run of ascending insertions,
  otherwise aims to balance free space, and switches to
  `BTREE_SINGLEVAL_FILLFACTOR` for a page full of one value. That is why the new column is defined against what a
  *rebuild* targets and not against how a growing index packs itself.
- `src/backend/utils/adt/dbsize.c`, read during the 2026-09-10 review for the
  one function in the statement that was not `pgstatindex`: `pg_relation_size`
  opens with `try_relation_open` and returns NULL rather than raising when the
  relation has gone, and its comment names the exact case — a `pg_class` scan
  under an MVCC snapshot racing a drop. Re-read when the size prefilter was
  removed, because that call went with it: `pgstatindex` is now the only
  function the statement measures with, and the shield the call provided is
  gone, which is what the `race` stage measures.
- `src/backend/optimizer/plan/subselect.c`, read for the plan-shape change the
  removal produced: `SS_process_ctes` inlines a `CTEMaterializeDefault` CTE
  referenced exactly once, so `params` — down to one reference now that `cand`
  no longer joins it — stops appearing as a `CTE Scan`.
- The full `guc_tables.c` entries for every setting the measurement scripts
  write, so each one's apply scope can be named: `listen_addresses`, `port`,
  `unix_socket_directories`, `shared_buffers`, `logging_collector`, `fsync`,
  `autovacuum`, `maintenance_work_mem` and
  `max_parallel_maintenance_workers`.
- `doc/src/sgml/installation.sgml`, for the VPATH build the scripts use to keep
  `raw/postgres-17/` read-only.
- This page's own git history, for the two superseded statement texts and their
  sizes, and the v17 checkout's history for the back-patch note on
  `13503eb5905`.
- On 2026-09-16 **every source citation the page carried was re-read against
  the pin, content and all**: 328 occurrences page-wide, 219 of them in the
  body, over 109 distinct ranges in 47 files, each one checked to resolve
  inside `raw/postgres-17/`, to lie within its file, and to say what its label
  claims. **None was wrong**, so this pass corrected no citation and added
  ranges instead: the body now carries 254 occurrences over 122 distinct
  ranges in 50 files, and `## Source References` was regenerated from exactly
  that set. Earlier passes checked bounds on 2026-09-13 and content on
  2026-09-10 and 2026-09-12.
- The v17 source the no-defeat rule rests on, read for this revision: the
  removal horizon `VACUUM` takes and the three kinds of holder that move it
  ([vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122),
  [procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815),
  [procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902),
  [twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26)),
  the `VERBOSE` line the proof reads
  ([vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L657-L663)),
  the two views the probe reads
  ([system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L878-L885),
  [system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017)),
  the four timeouts an autovacuum worker forces to zero
  ([autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470),
  [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642),
  [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653)),
  the lock a foreground `VACUUM` waits for
  ([vacuum.c#vacuum-lockmode](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2049-L2056)),
  and what `pgstat_report_vacuum` writes afterwards
  ([pgstat_relation.c#report_vacuum-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L233-L246)).
  `pg_stat_force_next_flush`, which `wiki_flush()` calls where it exists, was
  re-read in the catalog
  ([pg_proc.dat#pg_stat_force_next_flush](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L5916-L5920)).
- [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md),
  read in full before the 2026-09-11 revision and again for each later pass: the
  six families fixture by fixture, the five phases, the three porting rules with
  their exempt list, the four verdict bands, the two mandatory scoring columns,
  the feature gates that skip a fixture, and the named limits — including the
  dead-but-unvacuumed blind spot, which the 2026-09-12 narrowing turned from a
  limit the suite measured into one it no longer builds. Read again in full for
  the 2026-09-13 re-port, as it stands after two later changes: the retirement
  of tests 11, 11b and 38 on 2026-09-12, which leaves 113 numbered tests, and
  the maintenance assumption added on 2026-09-13, with its three parts, its
  `vacuum()` ordering argument, the launcher thresholds it records without
  applying, and the four open questions it costs the suite. Read again in full
  for this revision, for the rule it gained on 2026-09-15,
  `### The maintenance must not be defeated`: its five forbidden states, the
  four proofs a run must record per maintenance statement, the exemption it
  grants a lazy `VACUUM` and the one it refuses a disabled launcher, and its
  statement that no fixture is exempt today. The concept page was used as the
  suite's definition and was not edited on any pass.
- The v17 behaviour the suite's own rules lean on, re-read for the port: the
  autovacuum analyze threshold and its two GUCs
  ([autovacuum.c#anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3066-L3076)),
  `n_mod_since_analyze` and the `pgstat_report_analyze` reset
  ([system_views.sql#n_mod_since_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L689),
  [pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L330-L338)),
  the self item pointer the drain selects on
  ([itemptr.h#ItemPointerData](../../../../raw/postgres-17/src/include/storage/itemptr.h#L36-L40)),
  `btbulkdelete` and `_bt_pagedel` as the path that turns dead entries into
  reclaimable pages, the index-vacuum bypass in full - its four conditions, the
  strict page-fraction comparison, the 32 MB dead-item cap, and the index
  cleanup that still runs when it applies
  ([vacuumlazy.c#BYPASS_THRESHOLD_PAGES](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L85-L89),
  [vacuumlazy.c#bypass-conditions](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1899-L1934),
  [vacuumlazy.c#bypass-applies](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949)),
  `index_update_stats` as what a build and the oracle rebuild write, and
  `analyze.c`'s `tupleFract` for what the suite's partial-index families are
  about. None of it is read by the statement, which is the point.
- `src/backend/access/nbtree/nbtdedup.c`, for why the two legs' index sizes
  differ on the same fixture text, and why every differing fixture row in the
  cross-leg comparison has fewer leaf pages on 17.11.
- Re-read for the 2026-09-12 review, against the concept page's 2026-09-12
  revision:
  - `relation_needs_vacanalyze` in full, not only its threshold arithmetic: the
    reloption-or-GUC selection for both analyze parameters
    ([autovacuum.c#anl-effective-values](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3011-L3017)),
    the `AutoVacOpts` member the values arrive in
    ([rel.h#AutoVacOpts](../../../../raw/postgres-17/src/include/utils/rel.h#L308-L326)),
    the two per-table reloptions and their `ShareUpdateExclusiveLock`
    ([reloptions.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L243-L251)),
    the negative-`reltuples` clamp and the strictly-greater comparison
    ([autovacuum.c#doanalyze](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095)).
    This is what the page's census had wrong.
  - The statistics publication path, for the two points rule 3 needs:
    `pgstat_report_stat`'s force flag and its interval
    ([pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L583-L600))
    and `pgstat_report_analyze`'s reset with the comment on what it forgets
    ([pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L330-L338)).
  - `nbtsort.c`'s sorted-input contract, which is why the drain's spread across
    leaves is a fixture property rather than a guarantee
    ([nbtsort.c#sorted-build](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L4-L15)).
  - The index-vacuum bypass in full, which the page had reduced to its page
    fraction
    ([vacuumlazy.c#bypass-conditions](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1899-L1934),
    [vacuumlazy.c#bypass-applies](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949)).
  - `acquire_sample_rows`'s random block seed, for why test 120 needs an
    assertion rather than a recipe
    ([analyze.c#acquire_sample_rows-seed](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1185-L1194)).
  - The insert-time deletion path, for the one cross-major difference
    deduplication does not explain: the executor's `indexUnchanged` hint
    ([execIndexing.c#indexUnchanged](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L427-L445)),
    the gate that acts on it without an equal-image test
    ([nbtinsert.c#bottom-up-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2776)),
    and what the pass is for
    ([nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L285-L308)).
  - This page's own git history at `cbbbd16` and `0dbabb6`, for the two
    superseded statement texts the `compare` stage measures against.
- Re-read for the 2026-09-12 re-sync, against the concept page's then
  115-test suite:
  - The concept page's `What the suite does not cover` and its two open
    questions on the retirement, fixture by fixture, to establish which numbers
    this port may still report: numbers 65, 67, 69, 106, 117 and 121 and legs
    113a and 113c are retired and not reused, while the fixtures whose point is
    a missing or stale statistics row — 64, 83, 85, 97, 98, 108, 110 to 112 and
    118 — stay.
  - Every remaining fixture recipe in families 1 to 6 against the concept page's
    tables, plus rule 2's exempt list, rule 3's effective-value arithmetic and
    publication points, the four verdict bands, the two mandatory scoring
    columns, the feature gates and the forgery ordering. The only drift found
    beyond the retired fixtures was `sql` block 5's comment, which still claimed
    the drain costs every leaf an entry.
  - The `reltuples = -1` boundary family 6 must respect, which is why the census
    block now prints the catalog count beside each fixture's counted population
    ([index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2809-L2842),
    [relcache.c#RelationSetNewRelfilenumber](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3943-L3960),
    [heap.c#AddNewRelationTuple](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1004-L1016)).
  - `update_relstats_all_indexes` and `btvacuumcleanup`'s estimated-count flag,
    re-read because the retired fixtures were the ones that ended on a `VACUUM`
    and so pinned what that writer leaves behind
    ([vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3073-L3096),
    [nbtree.c#btvacuumcleanup-estimated_count](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L884-L894)).
- Re-read for the 2026-09-13 re-port, against the concept page's maintenance
  assumption and its narrowing to 113 numbered tests:
  - Every recipe in `sql` blocks 3 to 6 against the concept page's three-part
    assumption, to find each fixture that writes rows after its index build
    and does not end on `VACUUM` then `ANALYZE`: nine did, and so did the
    retired 11, 11b and 38 still being built.
  - `vacuum()`'s per-relation order, which is why two statements, `VACUUM`
    then `ANALYZE`, leave the state `VACUUM ANALYZE` would
    ([vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650)).
  - `pg_regress`'s handling of an inherited `PGOPTIONS`, which is why the
    scripts' session timeouts are passed per call rather than exported
    ([pg_regress.c#PGOPTIONS](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L785-L798)),
    and the `client_min_messages` and `maintenance_work_mem` GUC entries the
    usage section now cites.
  - The source behind claims the review found uncited or wrongly supported:
    `relation_open`'s error and `pgstatindexbyid_v1_5`'s open and close
    ([relation.c#relation_open](../../../../raw/postgres-17/src/backend/access/common/relation.c#L47-L61),
    [pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L203-L213)),
    the text entry point and the schema `USAGE` check behind a name lookup
    ([pgstatindex.c#pgstatindex_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L170-L180),
    [namespace.c#LookupExplicitNamespace](../../../../raw/postgres-17/src/backend/catalog/namespace.c#L3388-L3420)),
    the `NaN` ordering for `float8` and `numeric`
    ([float.h#NaN-aware-comparisons](../../../../raw/postgres-17/src/include/utils/float.h#L252-L258),
    [numeric.c#cmp_numerics](../../../../raw/postgres-17/src/backend/utils/adt/numeric.c#L2527-L2547)),
    the `MATERIALIZED` grammar
    ([gram.y#opt_materialized](../../../../raw/postgres-17/src/backend/parser/gram.y#L12910-L12914)),
    the invalid index a failed concurrent build leaves
    ([ref/create_index.sgml#invalid-index](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L646-L661)),
    `EXPLAIN`'s `written=` counter
    ([explain.c#shared_blks_written](../../../../raw/postgres-17/src/backend/commands/explain.c#L3782-L3784)),
    `btm_allequalimage` on a `pg_upgrade`d index
    ([nbtpage.c#_bt_metaversion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L727-L736)),
    and `configure`'s `pkg-config` lookup for ICU
    ([configure.ac#ICU](../../../../raw/postgres-17/configure.ac#L842)).

## Evidence Map

| Claim | Evidence |
|---|---|
| `pgstatindex` accepts only a B-tree index relation | [pgstatindex.c#IS_BTREE](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L228); measured errors for hash, GIN, GiST, SP-GiST, BRIN and a partitioned index on both servers |
| It refuses another session's temp index | [pgstatindex.c#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L230-L238), [rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/src/include/utils/rel.h#L652-L669); reproduced on both servers with a second session holding a 6600 kB temp index, with the report unaffected |
| 17 refuses an invalid index, 12.2 returns a row | [pgstatindex.c#indisvalid](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L240-L250); commit `13503eb5905` in this checkout's history, which carries no release tags; measured both ways |
| `index_size` is the whole file | [pgstatindex.c#index_size](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L349-L357); equal to `pg_relation_size` for 367/367 and 352/352 candidates |
| `avg_leaf_density` ignores empty and deleted pages | [pgstatindex.c#leaf-accounting](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L304-L324); `i_delhead` at 89.94% density and 69.9% reclaimable, confirmed by `REINDEX` |
| No leaf pages gives `NaN`, and `NaN` outranks every threshold | [pgstatindex.c#NaN](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L372), [pgstattuple.out#empty-index](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L44-L52); measured `NaN > 20` true for `float8` and `numeric` on both servers |
| A rebuild's leaf density is `(leaf_capacity - BLCKSZ*(100-ff)/100) / leaf_capacity` | [nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L645-L671), [nbtsort.c#_bt_buildadd](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L845-L860), [nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1145); four fillfactors measured within 0.18 points on both servers |
| Leaf capacity is `block_size - 24 - 16` | [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L211-L214), [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-17/src/include/access/nbtree.h#L62-L71), [pgstatindex.c#max_avail](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L308-L314); implied 8151.6 and 8152.1 from two known-content pages on both servers |
| `PageGetFreeSpace` deducts one line pointer | [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L898-L923); an empty leaf page reads 0.05% density, not 0.00% |
| VACUUM never returns index pages to the filesystem | no `RelationTruncate`/`smgrtruncate` under `src/backend/access/nbtree/`, [nbtree.c#RecordFreeIndexPage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1165-L1170); 1,918 dead pages survived VACUUM and disappeared on REINDEX |
| Access is `pg_stat_scan_tables`, and the OID form needs no schema `USAGE` | [pgstattuple--1.4--1.5.sql#grants](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92), [pgstattuple.sgml#access](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L15-L24); measured with two non-superuser roles on both servers |
| The call waits on `AccessExclusiveLock`; `lock_timeout` bounds the wait | [pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L204-L213), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631); cancelled at 2010.9 ms and 2011.6 ms |
| With no size prefilter, a concurrent drop that commits during the report aborts it | [pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L204-L213) uses `relation_open`, which raises, and `cand` no longer opens anything that would absorb the drop ([dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L346-L371)); measured in both windows on both servers, `could not open relation with OID 18970`/`19328` with 0 rows against 371 and 356, and `OID 19882`/`20219` at the first 5 ms delay of the sweep |
| The scan uses a 256 kB bulk-read ring | [pgstatindex.c:222](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L222), [freelist.c#GetAccessStrategy](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L540-L574) |
| Every fixture row that differs between the majors is smaller on 17.11, and two mechanisms explain it | [nbtree.h#BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1146-L1151); the `crossleg` stage measured 138 fixture keys printed by both legs, 96 rows identical field for field and 42 differing, of which two are the harness's own bookkeeping indexes and **all 40 others have fewer leaf pages on 17.11** (`i_dup` 843 against 2,733, `i_int4` 417 against 1,367). `p68` differs at a counted 50,000 distinct keys over 50,000 predicate rows, which deduplication cannot explain; the hinted bottom-up deletion pass can ([execIndexing.c#indexUnchanged](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L427-L445), [nbtinsert.c#bottom-up-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2776), [nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L285-L308)) |
| Dropping `alert_pct` and `status` changes nothing else the statement returns | measured in the current run: the amended output equals the superseded output with field 14 cut, byte for byte (10,609 and 9,506 bytes); one view per text over the internal `final` stage exposes 29 columns against 28 with `alert_pct` the only loss, and `EXCEPT` in both directions over the 28 shared columns returns **0 rows** across 354 and 369 indexes |
| Removing the column cost nothing to run | measured at that revision: identical plan shape (4 `CTE Scan` nodes; 72 and 69 plan lines) over six interleaved end-to-end runs of each text per server, 226.7-278.8 ms against 219.2-254.2 ms on 17.11 and 219.4-248.4 ms against 213.5-232.7 ms on 12.2 |
| Fillfactor is a build and rightmost-split target, not a property a growing index holds | [nbtsplitloc.c#fillfactormult](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L279-L335), [nbtsplitloc.c#SPLIT_SINGLE_VALUE](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L406-L416), [nbtree.h#BTREE_SINGLEVAL_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202) |
| Rebasing wasted space on the fillfactor moves those two fields and nothing else | re-derived in the current run, where the two texts no longer print the same rows: **0 of the 123 and 110 rows the superseded text printed** are missing from the filed output on the 12 untouched presentation fields, and the 231 and 259 extra rows are the ones its prefilter hid; the internal `final` stage exposes 28 columns either way with `wasted_space` swapped one-for-one for `wasted_vs_fillfactor`; `EXCEPT` in both directions over the 27 shared columns returns **0 rows** across 354 and 369 indexes, with 0 rows where the new column exceeds the old one and 0 where it is negative |
| At fillfactor 100 the two definitions coincide exactly | `target_free` is `BLCKSZ * 0 / 100`, so `target_density` is 1 ([nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1145)); measured equal to the byte on all three `fillfactor = 100` indexes, `i_ff100`, `i_ff100_del90` and `p54`, the second of which reads 88.6 % wasted beside an 89.5 % reclaim estimate |
| A rebuilt index reports no waste at its own fillfactor | measured after `REINDEX INDEX` over every scored fixture: exactly 0 bytes for 43 of 117 and 46 of 126, at or below 0.1% for 58 and 60, and at or below 0.3% for the 51 and 48 fixtures at or above 1 MB |
| The new column over-reports on indexes too small to fill a page, and the report prints them | measured: `c_one_idx`, one tuple on one leaf page at 0.29% density, reports 7,309 bytes and 44.6% after a rebuild on both servers, and two suite fixtures read 14.9% on two- and three-page files; with no size prefilter every such row reaches the reader, unmarked by `notes` |
| For in-page waste the new column is `(leaf_capacity - target_free) / block_size` of `est_reclaimable` | predicted 0.8951 at 8192/90; measured 0.892 on `p18` and 0.889 on `i_int4`, 1.0 on the dead-page fixtures `i_delhead` and `i_ff50_delhead`, and 0.9899, 0.4928 and 0.0953 at fillfactors 100, 50 and 10 against predicted 0.9951, 0.4951 and 0.0952 |
| Rebasing costs nothing to run | measured in the current run: six interleaved end-to-end runs of the filed text against the fillfactor-era one, timed as filed, spanning 221.4-262.5 ms against 223.2-266.6 ms on 17.11 and 228.6-306.6 ms against 211.0-250.1 ms on 12.2, with the filed text reading 259 and 231 more indexes |
| Dropping the size prefilter left `params` singly referenced, so the planner inlines it | [subselect.c#SS_process_ctes](../../../../raw/postgres-17/src/backend/optimizer/plan/subselect.c#L911-L955); measured: 2 `CTE Scan` nodes where there were 4, 62 plan lines on 17.11 and 57 on 12.2, `EXPLAIN (ANALYZE, BUFFERS)` at 258.0 ms and 250.6 ms |
| `BTPageOpaqueData` is 16 bytes across five fields | [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-17/src/include/access/nbtree.h#L62-L71), [nbtree.h:29](../../../../raw/postgres-17/src/include/access/nbtree.h#L29): two `BlockNumber`, one `uint32`, `btpo_flags` as `uint16` and `btpo_cycleid` as `BTCycleId`, itself a `uint16` |
| The invalid-index check separates these two minors, not the two majors | commit `13503eb5905` in this checkout's history ends "Back-patch to v11 (all supported versions)"; the pinned 12.2 predates it and returns a row |
| Every number this page takes from a running server has a published script | [Measurement Script](#measurement-script); both legs run end to end and were last run on 2026-09-16, one invocation each; the numbers kept from earlier runs are labelled with the run that took them |
| The scored fixtures are the wiki's shared mandatory suite, not this page's own | [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md) defines them; `sql` blocks 2 to 6 of this page are the port, hash-checked at run time; 126 fixtures scored on 17.11 and 117 on 12.2, with 0 and 9 recorded skips, against the concept page's 113 numbered tests after it retired 11, 11b, 38, 65, 67, 69, 106, 117, 121 and legs 113a and 113c |
| The port follows the maintenance assumption | [vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650); every recipe in `sql` blocks 4 and 5 that writes rows after its index build ends on one `VACUUM (VERBOSE, ANALYZE)`; measured: 67 such statements per leg, and a census that analyzed 2 of 88 tables on each, the highest share left alone rounding to 0.0 % |
| The maintenance was not defeated on either leg | the rule's four proofs, measured per statement: 67 of 67 completed with a recorded end stamp; `tuples: … are dead but not yet removable` **0 on every one** ([vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L657-L663)); **73 of 73** horizon probes found no backend `xmin`, no open transaction, no replication slot and no prepared transaction, which are the holders `GetOldestNonRemovableTransactionId` folds in ([vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122), [procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815), [procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902), [twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26)); and the page classes were recorded for all 126 and 117 planned indexes, 10,340 and 11,868 deleted pages in total |
| A maintenance session runs with the timeouts an autovacuum worker forces | [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470), [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631), [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642), [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653); measured: one timeout set in force across all 67 statements on each leg, four zeros on 17.11 and three plus `n/a` on 12.2, where the setting does not exist |
| The maintenance step removed the `b93`/`b95` under-read | measured: `b92` to `b95` read 89.1 % against a measured 89.1 % on both legs, where `b93` and `b95` read 79.3 % against 89.1 % before their counted `UPDATE` was followed by a `VACUUM` ([nbtree.c#btbulkdelete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L820-L843)) |
| Rule 3 reads each table's own analyze parameters, not the cluster GUCs | [autovacuum.c#anl-effective-values](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3011-L3017), [rel.h#AutoVacOpts](../../../../raw/postgres-17/src/include/utils/rel.h#L308-L326), [reloptions.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L243-L251); measured: 2 per-table overrides on each leg, read at effective thresholds of 100 for `b94t` and 610,000 for `b95t` rather than the cluster's defaults; under the maintenance assumption both carry 0 modifications at the census, so neither is analyzed |
| The churn must be published twice, and waiting works where forcing is unavailable | [pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L583-L600), [pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L330-L338); measured: both legs analyzed the same 2 of 88 tables, `f85t` and `x108t`, the two no churn touched that were past their threshold (8 of 89 before the maintenance step, 17 of 99 before the narrowing, and 17 against 31 before the publication fix) |
| The drain's guarantee is volume, not distribution | [nbtsort.c#sorted-build](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L4-L15), [itemptr.h#ItemPointerData](../../../../raw/postgres-17/src/include/storage/itemptr.h#L36-L40); measured per fixture as one of six post-churn shapes, with 0 failed assertions on either leg |
| Test 120's intended state is probabilistic and must be asserted | [analyze.c#acquire_sample_rows-seed](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1185-L1194), [analyze.c#tupleFract](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953); measured: `p120` read `reltuples = 0` on both legs in the current run, so it was scored on both; `6643` on 17.11 and `0` on 12.2 in the 2026-09-13 run, `6643` on 17.11 and a met precondition on 12.2 in a rehearsal of this one, and `10002`/`10031` in earlier runs — which is the point of asserting it rather than assuming it |
| A physical density reading makes no false positive on the suite | measured: 0 `CRITICAL FALSE POSITIVE` and 0 `FALSE POSITIVE` on both legs, family 3's eight constructions included, because the statement reads no catalog row count ([pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L64-L66), [analyze.c#tupleFract](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953)) |
| A dead entry no `VACUUM` has removed is the reading's one failure mode, and the narrowed suite no longer builds it | [pgstatindex.c#leaf-accounting](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L304-L324), [nbtree.c#btbulkdelete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L820-L843); measured in the 2026-09-12 review run on `p65`, `p67`, `p113a` and `p113c`, the same four on both majors, at `0.0`/`−0.1` against 89.1 % and 100.0 % — all four retired on 2026-09-12, so the claim is now a source reading plus that historical measurement, and `p113b` measures only the vacuumed counterpart at 99.9 % against 100.0 % |
| The statement prints every candidate, so the scoring loses nothing to the report | measured: 126 of 126 and 117 of 117 fixtures printed, `lost_by` empty on both legs, and `taken_stage` equal to `taken_nofilter` on every fixture; 31 of 126 and 8 of 117 fixtures are under 1 MB and would have been hidden before, the difference between the legs being deduplication ([nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L33-L56)) |
| The report now covers the catalog, including indexes the reader's own session writes | measured: 367 and 352 candidates against 365 and 350 printed rows, the two extra being `report_filed_pkey` and its TOAST index, created between the readings; and one shared row differed on 17.11, `pg_toast.pg_toast_2618_index`, the TOAST index of `pg_rewrite`, which the harness view's own creation wrote between them. No fixture differed on either leg |
| The statement agrees with its own instrument | measured: `expected_stage`, recomputed in the harness from a direct `pgstatindex` call, agreed on 126 of 126 and 117 of 117; and the filed text agreed with the harness view on every row both print |
| Neither the maintenance step nor rule 3's census can move this method's reading | [autovacuum.c#anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3066-L3076); the statement reads no row count; measured: the census analyzed 2 of 88 tables on each leg, and the scored change this page traces to the maintenance step, `b93` and `b95` moving from 79.3 % to 89.1 %, comes from the `VACUUM` removing dead index entries, not from any statistic |
| Family 6 keeps an empty population apart from an unknown catalog count | [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2809-L2842), [relcache.c#RelationSetNewRelfilenumber](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3943-L3960), [heap.c#AddNewRelationTuple](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1004-L1016); measured: the census prints each fixture's counted population beside its `pg_class.reltuples`, and in this run no fixture read `-1` — on both legs `p113b`, `p116` and `p120` read a measured zero and `p114`, `p115`, `p118` and `p119` a count |

## Open Questions

- **The unvacuumed blind spot is no longer measured by anything on this page.**
  The narrowing retired 65, 67 and legs 113a and 113c, which were the four
  fixtures that failed this statement with the report filter removed, and the
  maintenance assumption now forbids the shape outright. The concept page names
  the same loss in its own open questions: a method that misreads a
  not-yet-vacuumed index passes the suite. So this page's headline `PASS` on
  126 of 126 and 117 of 117 measures a suite that no longer contains the one
  shape `pgstatindex` cannot see. Building an undrained no-`VACUUM` fixture back
  is a change to
  [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md),
  which this page may not make; the guard fixtures in schema `bl` could carry a
  local one instead, and do not.
- **The maintenance step also removed a milder under-read, and nothing measures
  it now.** Before the 2026-09-13 revision `b93` and `b95` read 79.3 % against a
  measured 89.1 %, because their counted `UPDATE` left dead index entries that no
  `VACUUM` removed before the decide phase. With the maintenance step all four
  of 92 to 95 read 89.1 % against 89.1 %. That under-read is the same blind
  spot at a smaller scale — dead entries a partial `VACUUM` history leaves
  behind — and a production index read between autovacuum runs can be in that
  state. The suite assumes it is not, by design; this page records what that
  assumption hides.
- **Nothing pins what `VACUUM` writes as a row count any more.** Under the
  maintenance assumption every churned table gets `VACUUM` then `ANALYZE`, so
  `ANALYZE` is the last writer of every churned fixture's count
  ([vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650)),
  and the one table whose build phase ended on a `VACUUM`, `f85t`, is analyzed
  by rule 3's census before the decide phase. No fixture on either leg therefore
  reaches the decide phase with `update_relstats_all_indexes` as the last writer
  of `reltuples`
  ([vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3073-L3096),
  [nbtree.c#btvacuumcleanup-estimated_count](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L884-L894)).
  Nothing this statement reads depends on it, because it reads no row count.
- **The no-defeat proofs are reads beside the maintenance, not an interlock
  around it.** `horizon_probe()` samples `pg_stat_activity`,
  `pg_replication_slots` and `pg_prepared_xacts` immediately before each
  maintenance statement and on both sides of the census, so a session that
  opened a snapshot after a probe and closed it before the next one would leave
  no trace in the `horizon` table; what would still catch it is proof 2, the
  statement's own `dead but not yet removable` count, which is why that is the
  proof the run dies on. The concept page records the same limitation against
  its own definition. Nothing here measures how wide the gap between two probes
  can be.
- **The `bl` guard fixtures are not covered by the rule.** Schema `bl` keeps
  plain `VACUUM` statements, unbracketed and unproved, because the concept page
  governs suite fixtures and these are not. They are built in a session of
  their own with no other backend running, so the states the rule forbids are
  not present; that is an argument, not a measurement, and the guard set's
  numbers — including this page's largest miss, `i_dedup_off` at `−69.4` —
  rest on it.
- **The deduplication blind spot has no suite fixture at all.** The concept page
  retired test 11b, the off-to-on `deduplicate_items` transition, with every
  other explicit `deduplicate_items` setting, so the one condition that costs
  this statement `−69.4` points is measured only by this page's undrained
  `i_dedup_off` guard fixture. A method that misses it passes the suite. A
  fixture for it is a change to
  [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md),
  which this page may not make; it is reported here instead.
- **Which release first shrinks a churned index with no duplicate keys is not
  readable here.** `p68` differs between the two servers at 50,000 distinct
  keys, and the v17 tree's insert-time bottom-up deletion pass explains how a
  churned index can shrink without deduplication
  ([nbtinsert.c#bottom-up-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2776)).
  Attributing the difference to a release would need a second checkout, which a
  v17 page may not cite. The claim on the page is therefore the mechanism in
  this tree plus the measurement, not a history.
- **The 50 % rebuild threshold is the harness's, and nothing replaces the cost
  control the statement gave up.** The shared bands score a decision; the
  statement reports a percentage and deliberately decides nothing, so the
  harness supplies a threshold that appears nowhere in the filed text and is not
  derived from anything. Reading every index costs about a quarter of a second
  on a 1.2 GiB fixture population whose files had just been written, which says
  nothing about a terabyte of index on cold storage, and this page measures no
  such case. A caller who needs a cheaper report is pointed at predicates the
  page does not score.
- **Rule 3's recheck still differs between the majors, and the cause is not
  citable here.** Both legs analyzed the same 2 of 88 tables, `f85t` and
  `x108t`. The recheck then finds both still above their threshold on 12.2 and
  neither on 17.11. On 17 `pgstat_report_analyze` zeroes the counter in shared
  memory before the recheck reads it
  ([pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L330-L338));
  why 12.2 still shows the old counter is a v12 code path this page may not
  cite, so the difference is recorded as measured and the suite's rule, to
  record the disagreement rather than analyze again, is followed. No scored
  number moves, because this statement reads no row count.
- **Test 120's precondition flips between runs, and the suite gives no way to
  close that.** In this run `p120` read `reltuples = 0` on both legs, so it was
  scored on both; the 2026-09-13 run read `6643` on 17.11 and scored it on 12.2
  only, and a rehearsal of this run read `6643` on 17.11 again. That is exactly
  what the concept page requires
  ([analyze.c#acquire_sample_rows-seed](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1185-L1194)),
  and it means the scored population is one fixture wider or narrower from run
  to run, which is also why the 17 leg's scored count moved from 125 to 126
  between two runs of the same text. Nothing in the suite says whether a run
  should retry the `ANALYZE` until the sample misses.
- **The report's own footprint moves rows in the report, and nothing bounds
  it.** With the catalog in the population, the relations the harness creates
  between two readings add rows and can move catalog estimates: the previous run
  saw `pg_depend_depender_index` move from 10.3 % to 7.7 % between two readings
  on 12.2, and this run saw the population grow from 365 to 371 rows across the
  17 leg's stages, with one shared row — `pg_toast_2618_index`, the TOAST index
  of `pg_rewrite` — disagreeing between the two readings compared. A
  monitoring caller that stores its results in the database it measures will
  see the same effect, and this page has no fixture that says how large it can
  get or which catalog indexes are most exposed.
- **The index-vacuum bypass is a source reading here, not a measurement.** No
  fixture drives a `VACUUM` into the bypass, so the four conditions under
  [The blind spot the suite stopped building](#the-blind-spot-the-suite-stopped-building)
  are read out of `vacuumlazy.c` and not observed. Since the narrowing, neither
  half of that section is measured on the current suite: the blind spot itself
  is history, and the reason a `VACUUM` might not fix it was never observed.
- **Whether any 12 minor refuses an invalid index is not readable here.** The
  commit that added the check says "Back-patch to v11 (all supported
  versions)", which suggests that some 12.x after 12.2 behaves like 17.11. This
  checkout carries no release tags, and confirming it, or naming the minor,
  would need a v12 checkout at another pin, which this page may not cite.
- **The 12 leg's cluster settings have no citable apply scope on this page.**
  The contexts in
  [What the scripts read from the environment](#what-the-scripts-read-from-the-environment)
  come from the v17 GUC table, because a v17 page may not cite the v12
  checkout. Nothing in the run depends on them differing, and the 12 leg
  accepted every setting, but the 12.2 contexts are asserted, not cited.
- **Nothing was run on a standby, and no fixture is unlogged any more.** The
  `relpersistence <> 'u' OR NOT pg_is_in_recovery()` filter is reasoning from
  [plancat.c#recovery](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L149-L153)
  and from the absence of any recovery guard in `pgstatindex_impl`, not from a
  measurement. The retired fixture set at least contained an unlogged index on a
  primary; the current guard set does not, so that half is now untested too.
- **Only two minor versions were tested**, 12.2 and 17.11, both from this repo's
  pins. The invalid-index check's commit says it was back-patched, so a later
  12.x minor may differ from the pinned 12.2; what else may have changed in a
  later 12.x cannot be checked from this page's evidence base. Nine suite
  fixtures are skipped on 12.2 for want of B-tree support function 4, so those
  nine fixtures have one leg only.
- **One block size.** Every measurement is at `block_size` 8192, which is also
  the shared suite's own stated limit. The statement reads `block_size` from the
  server, but the 24 and 16 constants, the whole target-density model, and the
  `(leaf_capacity - target_free) / block_size` ratio between the two percentage
  columns are unverified at 4 kB, 16 kB or 32 kB.
- **The internal-page term is a proportional guess.** `round(internal_pages *
  est_leaf / leaf_pages)` was never tested against a case where the rebuilt tree
  loses a level; internal pages were a small fraction of every fixture, so the
  suite cannot distinguish a good model from a lucky one.
- **The worst over-estimate is a small-index artefact and was not analysed.**
  `p25` reads 70.0 % against a measured 60.0 % on a ten-block index on 17.11,
  `+10.0` points, and `p19` and `p31` behave the same way at 30 and 24 blocks.
  One page either way is several points at that size, which is the likely whole
  explanation, but no per-page accounting was done, and with no size prefilter
  the report prints every one of those rows.
- **Neither silent failure has an in-statement warning.** The retired `p65`,
  `p67`, `p113a` and `p113c` came back with an empty `notes` string, `0.0` or
  `0.1` wasted and `0.0` or `−0.1` reclaimable on files a rebuild emptied by
  89.1 % and 100.0 %, and `i_dedup_off` still does the same at 69.1 %. Neither
  condition is visible in any `pgstatindex` column, so closing them would
  require a second tool and would break the "pgstatindex only" constraint; the
  page documents them instead. One of the two is now measured only by a guard
  fixture, and the other by nothing.
- **The fillfactor-relative column over-reports on indexes too small to fill a
  page, and the report now shows every one of them.** A one-row index measured
  44.6 % wasted immediately after `REINDEX` on both servers, and two suite
  fixtures 14.9 % on two- and three-page files, because one tuple cannot fill
  89.95 % of a page. Until this revision the size prefilter kept those rows out
  of the output; now they reach the reader with no note attached, and no
  measurement here says what the smallest index worth reporting on is. A `notes`
  string for a file under a handful of pages is the obvious repair and has not
  been made, because it would change the output shape a second time.
- **The clamp hides how far above target an index sits.** Every index denser than
  its fillfactor target reports the same `0`, whether it is 0.05 points over like
  `i_fresh` at 90.00 % or 6 points over like `i_dup_ins` at 95.94 %, both against
  an 89.95 % target. The `denser than a rebuild would leave it` note does not
  close the gap, because it fires on `est_reclaimable_pct <= -1` rather than on
  the clamp: measured, `i_dup_ins` carries the note and `i_fresh` clamps to `0`
  with an empty `notes` string. How many rows clamp is counted again by the
  `compare` stage — 29 of 369 indexes on 17.11 and 25 of 354 on 12.2, and since
  the prefilter went every one of them is a printed row — but nothing in the
  output tells a reader which ones they are.
- **Whether both percentage columns should still exist was not settled by
  measurement.** For in-page waste the new column is a fixed multiple of
  `est_reclaimable_pct`, so on a default-fillfactor database it carries little
  independent information; at fillfactor 10 it carries a great deal, since the
  same index reads 8.3 % and 87.1 %. No reader other than the author has judged
  whether two near-proportional columns help or confuse.
- **The `−2.9` under-estimate on `i_ff10_del90` is explained but not proven.**
  The per-page high-key and line-pointer overhead that `avg_leaf_density` counts
  as payload is the plausible cause and the arithmetic is consistent with it, but
  no per-page accounting was done, and doing it needs a tool this page excludes.
  It is the worst miss of any guard fixture at a non-default fillfactor, and the
  suite's fixtures sit almost entirely at fillfactor 90, so the accuracy figures
  under [Accuracy against the oracle](#accuracy-against-the-oracle) are mostly a
  fillfactor-90 result. The suite's own worst under-estimate, `p32` at `−4.1`,
  is not explained either.
- **Removing the verdict column moves the judgement off the page.** The statement
  returns numbers only, and nothing in this repository measures what threshold is
  right for a given environment. The 20 % that the removed `status` column used
  was never derived from anything but convention, which is part of why it is
  gone, but no replacement rule was measured either.
- **The ordering has no tie-break.** `ORDER BY index_size - est_rebuilt_bytes
  DESC` left two equal-sized 12.2 rows in a different order on two earlier runs.
  It never changed a value, but a caller diffing two reports will see tied rows
  move.
- **The suite's own limits are inherited.** No concurrency: every phase runs
  alone, so two sessions racing on one index is not a fixture. No partitioned
  table end to end: leaf indexes are scored, but nothing drains a partition and
  then asks about the parent, and this statement has no roll-up, so the report
  returns one row per leaf index where a DBA wants one per parent.

## Source References

- [configure.ac#ICU](../../../../raw/postgres-17/configure.ac#L842)
- [pgstattuple.out#empty-index](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L44-L52)
- [pgstattuple.out#partitioned](../../../../raw/postgres-17/contrib/pgstattuple/expected/pgstattuple.out#L155-L171)
- [pgstatindex.c:70](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L70)
- [pgstatindex.c#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L144-L160)
- [pgstatindex.c#pgstatindex_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L162-L180)
- [pgstatindex.c#pgstatindex_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L170-L180)
- [pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L203-L213)
- [pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L204-L213)
- [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L215-L333)
- [pgstatindex.c:222](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L222)
- [pgstatindex.c#IS_BTREE](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L228)
- [pgstatindex.c#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L230-L238)
- [pgstatindex.c#indisvalid](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L240-L250)
- [pgstatindex.c#leaf-accounting](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L304-L324)
- [pgstatindex.c#max_avail](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L308-L314)
- [pgstatindex.c#fragments](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L318-L323)
- [pgstatindex.c#result-tuple](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L339-L378)
- [pgstatindex.c#index_size](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L349-L357)
- [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L367)
- [pgstatindex.c#NaN](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L372)
- [pgstatindex.c#leaf_fragmentation](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L368-L372)
- [pgstattuple--1.4--1.5.sql#pgstatindex-regclass](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)
- [pgstattuple.control:1-5](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.control#L1-L5)
- [pgstattuple.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L18-L37)
- [installation.sgml#VPATH](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L425-L436)
- [installation.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L515-L522)
- [pgstattuple.sgml#access](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L15-L24)
- [ref/create_index.sgml#invalid-index](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L646-L661)
- [regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59)
- [regress.sgml#contrib-suites](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L171-L195)
- [relation.c#relation_open](../../../../raw/postgres-17/src/backend/access/common/relation.c#L47-L61)
- [reloptions.c#btree-fillfactor](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L185-L194)
- [reloptions.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L243-L251)
- [vacuumlazy.c#BYPASS_THRESHOLD_PAGES](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L85-L89)
- [vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L657-L663)
- [vacuumlazy.c#bypass-conditions](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1899-L1934)
- [vacuumlazy.c#bypass-applies](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1936-L1949)
- [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3073-L3096)
- [nbtdedup.c#_bt_dedup_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L33-L56)
- [nbtdedup.c#_bt_bottomupdel_pass](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L285-L308)
- [nbtinsert.c#bottom-up-deletion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2757-L2776)
- [nbtpage.c#_bt_metaversion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L727-L736)
- [nbtpage.c#_bt_pagedel](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1802-L1815)
- [nbtree.c#btbulkdelete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L820-L843)
- [nbtree.c#btvacuumcleanup-estimated_count](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L884-L894)
- [nbtree.c#_bt_pendingfsm_finalize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1048-L1059)
- [nbtree.c#RecordFreeIndexPage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1165-L1170)
- [nbtsort.c#sorted-build](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L4-L15)
- [nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L645-L671)
- [nbtsort.c#_bt_buildadd](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L845-L860)
- [nbtsplitloc.c#fillfactormult](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L279-L335)
- [nbtsplitloc.c#SPLIT_SINGLE_VALUE](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L406-L416)
- [twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26)
- [heap.c#AddNewRelationTuple](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1004-L1016)
- [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2809-L2842)
- [namespace.c#RangeVarGetRelidExtended](../../../../raw/postgres-17/src/backend/catalog/namespace.c#L528-L532)
- [namespace.c#LookupExplicitNamespace](../../../../raw/postgres-17/src/backend/catalog/namespace.c#L3388-L3420)
- [system_views.sql#n_mod_since_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L689)
- [system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L878-L885)
- [system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017)
- [analyze.c#totalindexrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L648-L660)
- [analyze.c#tupleFract](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953)
- [analyze.c#acquire_sample_rows-seed](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1185-L1194)
- [explain.c#shared_blks_written](../../../../raw/postgres-17/src/backend/commands/explain.c#L3782-L3784)
- [vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650)
- [vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122)
- [vacuum.c#vacuum-lockmode](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2049-L2056)
- [execIndexing.c#indexUnchanged](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L427-L445)
- [subselect.c#SS_process_ctes](../../../../raw/postgres-17/src/backend/optimizer/plan/subselect.c#L911-L955)
- [plancat.c#recovery](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L149-L153)
- [gram.y#opt_materialized](../../../../raw/postgres-17/src/backend/parser/gram.y#L12910-L12914)
- [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470)
- [autovacuum.c#anl-effective-values](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3011-L3017)
- [autovacuum.c#anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3066-L3076)
- [autovacuum.c#doanalyze](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095)
- [freelist.c#GetAccessStrategy](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L540-L574)
- [procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815)
- [procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902)
- [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L898-L923)
- [pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L583-L600)
- [pgstat_relation.c#report_vacuum-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L233-L246)
- [pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L330-L338)
- [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L346-L371)
- [numeric.c#cmp_numerics](../../../../raw/postgres-17/src/backend/utils/adt/numeric.c#L2527-L2547)
- [relcache.c#RelationSetNewRelfilenumber](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3943-L3960)
- [guc_tables.c#fsync](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1096-L1107)
- [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457)
- [guc_tables.c#logging_collector](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1640-L1648)
- [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270)
- [guc_tables.c#port](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2393-L2401)
- [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2465-L2474)
- [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620)
- [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)
- [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642)
- [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653)
- [guc_tables.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3367-L3375)
- [guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417)
- [guc_tables.c#autovacuum_analyze_scale_factor](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3906-L3914)
- [guc_tables.c#unix_socket_directories](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4425-L4434)
- [guc_tables.c#listen_addresses](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4436-L4445)
- [guc_tables.c#client_min_messages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4776-L4784)
- [nbtree.h:29](../../../../raw/postgres-17/src/include/access/nbtree.h#L29)
- [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-17/src/include/access/nbtree.h#L62-L71)
- [nbtree.h#btm_allequalimage](../../../../raw/postgres-17/src/include/access/nbtree.h#L103-L119)
- [nbtree.h#MaxTIDsPerBTreePage](../../../../raw/postgres-17/src/include/access/nbtree.h#L185-L187)
- [nbtree.h#BTREE_SINGLEVAL_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202)
- [nbtree.h#P_ISLEAF](../../../../raw/postgres-17/src/include/access/nbtree.h#L212-L227)
- [nbtree.h#P_HIKEY](../../../../raw/postgres-17/src/include/access/nbtree.h#L348-L369)
- [nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1145)
- [nbtree.h#BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1146-L1151)
- [pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L64-L66)
- [pg_class.h#RELKIND_PARTITIONED_INDEX](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L165-L173)
- [pg_index.h#indisvalid](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L42-L45)
- [pg_proc.dat#pg_stat_force_next_flush](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L5916-L5920)
- [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L211-L214)
- [itemptr.h#ItemPointerData](../../../../raw/postgres-17/src/include/storage/itemptr.h#L36-L40)
- [float.h#NaN-aware-comparisons](../../../../raw/postgres-17/src/include/utils/float.h#L252-L258)
- [float.h#float8_gt](../../../../raw/postgres-17/src/include/utils/float.h#L315-L319)
- [rel.h#AutoVacOpts](../../../../raw/postgres-17/src/include/utils/rel.h#L308-L326)
- [rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/src/include/utils/rel.h#L652-L669)
- [pg_regress.c#PGOPTIONS](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L785-L798)

## Navigation

- [v17 index](../../index.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
- [v17 common concept: Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
- [v17: Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17](btree-index-bloat-core-sql-only.md)
- [v17: Checking Whether an Index Needs a Rebuild to Enable Deduplication After pg_upgrade](btree-deduplication-after-pg-upgrade.md)
- [v17: How CREATE INDEX CONCURRENTLY Is Implemented](create-index-concurrently.md)
- [v17: How REINDEX INDEX CONCURRENTLY Is Implemented](reindex-index-concurrently.md)
- [v17: Planner Penalties for Bloated Indexes](../query-planning/bloated-indexes-query-planner.md)
- [v12: How pgstatindex Calculates B-Tree Index Statistics](../../../v12/questions/indexing/how-pgstatindex-calculates-information.md)
- [v12: Leaf Density Versus Fragmentation for Index-Scan I/O](../../../v12/questions/indexing/leaf-density-vs-fragmentation-index-scan-io.md)
