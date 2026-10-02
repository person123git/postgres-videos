---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# How Accurate Is the pgstatindex REINDEX_SCORE B-Tree Maintenance Heuristic, on PostgreSQL 17 and 12 (unverified)

## Contents

- [Question](#question)
  - [Prompt corrections](#prompt-corrections)
  - [Follow-up: the NaN cases](#follow-up-the-nan-cases)
  - [Review after filing](#review-after-filing)
- [Answer](#answer)
  - [The verdict](#the-verdict)
  - [The statement](#the-statement)
  - [Why the formula is accurate](#why-the-formula-is-accurate)
  - [The two readings the formula does not supply](#the-two-readings-the-formula-does-not-supply)
  - [Where it errs, and in which direction](#where-it-errs-and-in-which-direction)
  - [The NaN defect, and the guard that closes it](#the-nan-defect-and-the-guard-that-closes-it)
  - [What the guard fixtures show](#what-the-guard-fixtures-show)
  - [The threshold](#the-threshold)
  - [What the two majors do differently](#what-the-two-majors-do-differently)
  - [What this run does not settle](#what-this-run-does-not-settle)
- [Measurement Script](#measurement-script)
  - [How to use the two leg scripts](#how-to-use-the-two-leg-scripts)
  - [The stages, both legs](#the-stages-both-legs)
  - [What the scripts read from the environment](#what-the-scripts-read-from-the-environment)
  - [The cluster settings](#the-cluster-settings)
  - [The PostgreSQL 17 leg script](#the-postgresql-17-leg-script)
  - [The PostgreSQL 12 leg script](#the-postgresql-12-leg-script)
  - [The shared suite's harness](#the-shared-suites-harness)
  - [Family 1, the deduplication gate](#family-1-the-deduplication-gate)
  - [Families 2 to 6, tests 18 to 120](#families-2-to-6-tests-18-to-120)
  - [Rule 2, the uniform drain](#rule-2-the-uniform-drain)
  - [Rule 3, the census, and the forgeries](#rule-3-the-census-and-the-forgeries)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Follow `AGENTS.md`, in PostgreSQL 17, for this question:

Test how accurate this B-tree maintenance heuristic is. The formula, computed
from a `pgstatindex` execution, is:

```text
REINDEX_SCORE =
(
    deleted_pages
  + empty_pages
  + leaf_pages *
      max(0, 1 - avg_leaf_density / fillfactor)
)
/
total_pages
```

Use `REINDEX_SCORE >= 50%` as the conservative automatic `REINDEX` signal. Use
and link the common concept
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md).
Test with B-tree indexes only, for versions 17 and 12.

### Prompt corrections

Filed after prompt-hygiene correction, at the asker's request. The original
prompt read:

> follow  agents.md, in postgresql 17, question : test how acurate is this
> heuristic to reindex btree B-tree maintenance heuristic formula from
> pgstatindex execution is: [formula] Use REINDEX_SCORE >= 50% as the
> conservative automatic REINDEX signal. , use and link the common-concept
> # Mandatory B-Tree Bloat Tests (unverified), tests only with btree indexes
> for version 17 and 12.

It wrote `agents.md` for `AGENTS.md` with a double space after `follow`,
lowercase `postgresql` for `PostgreSQL`, a space before the colon in
`question :`, `acurate` for `accurate`, doubled the subject as `reindex btree
B-tree maintenance heuristic` and doubled `heuristic` in a sentence that then
ended `... formula from pgstatindex execution is:`, put a stray comma after the
full stop in `signal. ,`, wrote `btree` for `B-tree`, and wrote `version 17 and
12` for `versions 17 and 12`. The asker chose "correct and restate".

Four scoping answers were taken before drafting, and all four are part of what
was scored:

1. **`total_pages` is `index_size / block_size`.** `pgstatindex` returns no such
   column, so the reading had to be fixed before the score was computable. This
   one counts the metapage and matches the file a `REINDEX` shrinks. The asker
   rejected the alternative, the sum of the four page classes, which the run
   also measured; see
   [The two readings the formula does not supply](#the-two-readings-the-formula-does-not-supply).
2. **`fillfactor` is the index's own reloption, 90 where unset.** Also not a
   `pgstatindex` column. This is the value the engine itself resolves for an
   index.
3. **One page, filed under v17.** PostgreSQL 12 has no
   `wiki/v12/common-concepts/` directory, and `AGENTS.md` forbids creating a
   common concept page as a side effect of a question page, or linking another
   version's concept page. So the v17 leg links the concept page and the v12 leg
   states inline which of the concept page's rules it followed.
4. **Both legs were re-run before filing**, rather than filed from the earlier
   same-day run of the same scripts at the same pins.

### Follow-up: the NaN cases

Follow-up prompt, corrected and restated with the asker's agreement:

> Follow `AGENTS.md`. Change the formula to add `CASE` expressions mapping a
> `NaN` value to 0.

The original read `change formula add cases for values when 'NaN' THEN 0`: it
omitted the article before `formula`, omitted the verb connector after it, wrote
`add cases for values when 'NaN' THEN 0` for "add `CASE` expressions mapping a
`NaN` value to 0", and carried no sentence capitalisation or terminal period.
The asker chose "correct and restate".

Two scoping answers were taken before the edit:

1. **Guard every `NaN`-capable value**, not just one place: the
   `avg_leaf_density` input *and* the score itself. The scoping answer was
   taken on the reasoning that the two placements could disagree on an index
   whose pages had all been deleted. The measurement since shows they cannot,
   because the engine does not produce that shape, so both guards are kept for
   the reason the answer gave and neither is load-bearing against the other.
   See
   [What a NaN density means, and why the two guards agree](#what-a-nan-density-means-and-why-the-two-guards-agree).
2. **Rebuild and re-run both legs.** The sandbox had been deleted, so this meant
   a full compile of 12.2 and 17.11 rather than a re-run, and every number below
   is from that run.

`AGENTS.md` requires the page's script to be edited in place and re-run when the
statement changes, so `BASE_SQL` was updated in both leg scripts and both legs
were re-run end to end. No second script was added.

### Review after filing

Review prompt:

> Follow `AGENTS.md`, in PostgreSQL 17, review the question "How Accurate Is
> the pgstatindex REINDEX_SCORE B-Tree Maintenance Heuristic, on PostgreSQL 17
> and 12 (unverified)".

The review reproduced every headline number and reported 26 defects in the text
and the scripts around them. The asker chose to have all of them fixed: both
leg scripts were corrected in place, three of the six `sql` blocks changed with
them, and both legs were re-run from an empty sandbox. Every number on this page
is from that re-run.

## Answer

### The verdict

**With the `NaN` cases added, the heuristic is correct on every fixture the suite
scores, on both majors: no false positives and no false negatives, and no
fixture where the signal and a measured `REINDEX INDEX` disagree. 50 % is inside
the range of thresholds that achieve that, though the fixtures cannot show it is
the best point in that range. The arithmetic was always good, and the `NaN` guard
removed its only undefined input. What still stands between the statement and an
unattended job is not the formula: one index it cannot lock or open ends the
whole run; see [Open Questions](#open-questions).**

Scored against the numbered fixtures of
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md),
whose only oracle is a measured `REINDEX INDEX`. Test 120's precondition is a
random `ANALYZE` sample missing a subset, so it is scored on some runs and not
others. In this run it was met on the 17 leg, where `p120` is the worst
over-estimate, and not on the 12 leg, whose sample found the subset, so every
figure it moves is given twice and the two 12.2 columns coincide:

| | 17.11 | 17.11 without `p120` | 12.2 | 12.2 without `p120` |
|---|---|---|---|---|
| fixtures scored for accuracy | 126 | 125 | 116 | 116 |
| mean absolute error, points | **0.99** | **0.94** | **0.75** | **0.75** |
| median absolute error, points | 0.50 | 0.50 | 0.45 | 0.45 |
| worst over-estimate, points | +6.6 | +6.5 | +3.8 | +3.8 |
| worst under-estimate, points | −9.8 | −9.8 | −9.8 | −9.8 |
| correlation with the oracle | **0.9990** | **0.9991** | **0.9994** | **0.9994** |
| within 1 point of the oracle | 97 | — | 101 | — |
| within 5 points | 119 | — | 112 | — |
| within 10 points | **126 of 126** | — | **116 of 116** | — |
| at 50 %: true pos / **false pos** / true neg / **false neg** | 92 / **0** / 34 / **0** | — | 83 / **0** / 33 / **0** | — |
| fixtures where the signal and the oracle disagree | **none** | — | **none** | — |

The score is not a loose heuristic. It is a first-order model of what a rebuild
does to the file, and the residual is not a mood: it decomposes exactly into
three named terms. The internal levels pulled the score down wherever a rebuild
moved them and, in this run, never pushed it up; the leaf term cannot be negative on any index
a rebuild writes back at the same number of leaves, so there it only ever
over-reads; and pages a rebuild left dead were zero everywhere. See
[Why the formula is accurate](#why-the-formula-is-accurate) and
[Where it errs, and in which direction](#where-it-errs-and-in-which-direction).

What the guard changed is visible at cluster scale rather than on the fixture
set, where it moved exactly one verdict. Both columns below come from the same
run: the harness recomputes the unguarded statement beside the filed one over
the same candidates, so "before" and "after" are two readings of one population.

| | 17.11 before | 17.11 after | 12.2 before | 12.2 after |
|---|---|---|---|---|
| candidates measured | 363 | 363 | 349 | 349 |
| signalled for rebuild | 233 | **95** | 219 | **86** |
| whose score is `NaN` | 138 | **0** | 133 | **0** |
| metapage-only indexes | 138 | 138 | 133 | 133 |
| metapage-only indexes signalled | 138 | **0 of 138** | 133 | **0 of 133** |
| verdicts the guards moved | — | **138** | — | **133** |
| finite scores the guards changed | — | **0** | — | **0** |

`233 − 138 = 95` and `219 − 133 = 86`, exactly. **The guards removed precisely
the `NaN` rows and changed no other row's score or signal** — they suppressed
59 % of the rebuild orders on 17.11 and 61 % on 12.2, every one of them an
8,192-byte metapage-only file a rebuild cannot shrink. See
[The NaN defect, and the guard that closes it](#the-nan-defect-and-the-guard-that-closes-it).
The filed statement itself printed 361 and 347 rows and signalled 95 and 86; the
two extra candidates per leg are indexes the harness created between the two
reads.

### The statement
```sql
-- The REINDEX_SCORE heuristic under test, computed from pgstatindex alone.
-- Runs unchanged on PostgreSQL 12 and 17.
--
--   REINDEX_SCORE = ( deleted_pages
--                   + empty_pages
--                   + leaf_pages * max(0, 1 - avg_leaf_density / fillfactor) )
--                   / total_pages
--
--   signal: REINDEX_SCORE >= 0.5, the conservative automatic REINDEX signal.
--
-- Two readings the formula does not supply are fixed here, and both are part
-- of what is being scored:
--
--   total_pages   pgstatindex has no such column.  It is index_size /
--                 block_size, which is how pgstatindex builds index_size in
--                 the first place, so it counts the metapage and is never 0
--                 for an index that exists.
--   fillfactor    the index's own fillfactor reloption, 90 where unset, which
--                 is the value BTGetFillFactor resolves for that index.
--
-- Every NaN-capable value is mapped to 0 by a CASE, in two places:
--
--   inner   avg_leaf_density is NaN whenever pgstatindex scanned no leaf page,
--           which is every index whose file is just a metapage, and only
--           those: nbtree never deletes the rightmost page of a level, so a
--           file that ever held an entry keeps at least one live leaf.
--   outer   the score itself, so that nothing NaN can reach the >= comparison
--           whatever a later edit does to the terms above.
--
-- The inner guard is the one that fires.  Because leaf_pages = 0 implies
-- deleted_pages = empty_pages = 0, the whole numerator is 0 there and the two
-- placements agree on every index that can exist; the outer CASE is a
-- backstop against a later edit, not a second correctness rule.
--
-- The test is `= 'NaN'::float8`, not a self-inequality: PostgreSQL defines
-- NaN = NaN as true, so the C-style `x <> x` test never fires here.  The
-- guards are needed because NaN sorts above every number in this type, so an
-- unguarded NaN satisfies `>= 0.5` and orders a rebuild that returns nothing.
--
--   cand      every index pgstatindex can be called on without raising
--   measured  one pgstatindex() call per candidate
--   guarded   total_pages, and the NaN-guarded density
--   final     the score, NaN-guarded again
--
-- The statement prints one row per candidate, signalled or not, so a reader
-- sees the score behind every verdict.  Filtering to the signal alone is
-- WHERE f.reindex_signal on the last SELECT.
--
-- pgstatindex opens every candidate with AccessShareLock, so one index held
-- in ACCESS EXCLUSIVE for longer than lock_timeout, or dropped between the
-- cand read and its own pgstatindex call, raises and ends the whole
-- statement: an unattended run gets every row or none.

SET /* wiki_reindex_score_12_17 */ statement_timeout = '15min';
SET /* wiki_reindex_score_12_17 */ lock_timeout = '5s';

WITH /* wiki_reindex_score_12_17 */ cand AS MATERIALIZED (
    SELECT c.oid       AS idx_oid,
           n.nspname   AS schema_name,
           c.relname   AS index_name,
           t.relname   AS table_name,
           -- BTGetFillFactor: the index's reloption, else BTREE_DEFAULT_FILLFACTOR
           COALESCE((SELECT o.option_value::int
                       FROM pg_options_to_table(c.reloptions) o
                      WHERE o.option_name = 'fillfactor'), 90) AS fillfactor
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
guarded AS (
    SELECT m.*,
           (m.index_size / current_setting('block_size')::bigint) AS total_pages,
           -- inner NaN case: no leaf page was scanned, so read the density as 0
           CASE WHEN m.avg_leaf_density = 'NaN'::float8
                THEN 0::float8
                ELSE m.avg_leaf_density
           END                                       AS density
      FROM measured m
),
final AS (
    SELECT g.*,
           -- outer NaN case: nothing undefined may reach the >= comparison
           CASE WHEN raw.score = 'NaN'::float8
                THEN 0::float8
                ELSE raw.score
           END                                       AS reindex_score
      FROM guarded g
      CROSS JOIN LATERAL (
          SELECT ( g.deleted_pages
                 + g.empty_pages
                 + g.leaf_pages * GREATEST(0::float8,
                                           1 - g.density / g.fillfactor)
                 )
                 / g.total_pages::float8             AS score
      ) raw
)
SELECT f.schema_name,
       f.index_name,
       f.table_name,
       pg_size_pretty(f.index_size)                AS index_size,
       f.total_pages,
       f.leaf_pages,
       f.empty_pages,
       f.deleted_pages,
       CASE WHEN f.leaf_pages > 0 THEN round(f.avg_leaf_density::numeric, 2) END
           AS avg_leaf_density,
       f.fillfactor,
       round(f.reindex_score::numeric, 4)          AS reindex_score,
       round(100 * f.reindex_score::numeric, 1)    AS reindex_score_pct,
       (f.reindex_score >= 0.5)                    AS reindex_signal
  FROM final f
 ORDER BY f.reindex_score DESC, f.index_size DESC;
```

### Why the formula is accurate

The score is not an analogy for bloat. It is an estimate of the very quantity
the oracle measures, and the algebra shows why.

A fresh serial build aims each leaf page at the index's fillfactor, leaving
`BLCKSZ * (100 - fillfactor) / 100` free on it, and aims every level above the
leaf level at a fixed fillfactor of 70 %, leaving `BLCKSZ * 30 / 100` free
there
([nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L660-L666),
[nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1144-L1145),
[nbtree.h:201](../../../../raw/postgres-17/src/include/access/nbtree.h#L201)).
So for an index currently holding `leaf_pages` leaves at `avg_leaf_density`, the
same entries repacked to `fillfactor` need about `leaf_pages * density /
fillfactor` leaves. Rearranged, the leaf level gives back

```text
leaf_pages * (1 - avg_leaf_density / fillfactor)
```

pages, floored at zero. The floor is the formula's choice, not the engine's: an
index packed above its fillfactor, for instance by page splits that aim a leaf
page holding a single value at 96 %
([nbtsplitloc.c#SPLIT_SINGLE_VALUE](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L406-L413)),
rebuilds into more leaves than it had, and the formula credits it with nothing
rather than with a negative reclaim. No fixture reaches that shape: the
`accuracy` stage counts every leaf level a rebuild grew, and there were none.
Empty and deleted pages hold nothing at any fillfactor and come back whole
([pgstatindex.c#page-classes](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L326)).
Divide the sum of the three terms by the file's page count and the result is the
fraction of the file a rebuild returns — which is exactly what
`(size_before - size_after) / size_before` measures after the oracle's
`REINDEX INDEX`. The formula and the oracle are estimating the same number,
which is why the error is small; it is not zero, and the three places the model
is deliberately coarser than the engine are named and measured under
[Where it errs, and in which direction](#where-it-errs-and-in-which-direction).

Two of those three are already visible in the paragraph above. **The fillfactor
is a target, not a guarantee.** `_bt_buildadd` starts a new page when the
current one is short of room for the next tuple *or* when its free space has
fallen below the fillfactor threshold and it already holds at least two items,
so a page is finished at whatever boundary the tuple widths happen to fall on
([nbtsort.c#_bt_buildadd-full](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L844-L855)).
Finishing it moves the page's last item onto the new page and leaves only a
truncated copy behind as the old page's high key
([nbtsort.c#_bt_buildadd-last-item](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L873-L884)),
so a build of wide posting-list tuples can finish a page well short of the
target, and the last page of each level is written holding whatever the input
had left
([nbtsort.c#_bt_uppershutdown-rightmost](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1109-L1115)).
The 96 % that `nbtree.h` also defines is not a build target at all: it is the fill
a page *split* aims at when a leaf page holds a single value
([nbtree.h#fillfactor-comment](../../../../raw/postgres-17/src/include/access/nbtree.h#L190-L197),
[nbtree.h:202](../../../../raw/postgres-17/src/include/access/nbtree.h#L202),
[nbtsplitloc.c#SPLIT_SINGLE_VALUE](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L406-L413)),
and a sorted build never splits a page; it starts a new one.
**And the result is a whole number of pages.** A model that predicts 1.35
leaves is measured against a rebuild that writes 2.

`avg_leaf_density` is the right input for that term because it is itself a
leaf-only ratio: `pgstatindex` accumulates `free_space` and `max_avail` over leaf
pages and reports `100 - free_space / max_avail * 100`
([pgstatindex.c#avg_leaf_density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L366)).

### The two readings the formula does not supply

`pgstatindex` returns ten columns — `version`, `tree_level`, `index_size`,
`root_block_no`, `internal_pages`, `leaf_pages`, `empty_pages`, `deleted_pages`,
`avg_leaf_density`, `leaf_fragmentation`. The statement passes a `regclass`, so
the overload it calls is the `regclass` one, which the extension declares with
the same ten columns as the `text` one and which version 1.5 redefines onto
`pgstatindexbyid_v1_5` and takes away from `PUBLIC`
([pgstattuple--1.4.sql#pgstatindex-regclass](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4.sql#L62-L74),
[pgstattuple--1.4--1.5.sql#pgstatindex-regclass](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)).
Neither `total_pages` nor `fillfactor` is among the ten, so the formula is not
computable until both are defined, and each definition is part of what was
scored.

**`total_pages`.** The asker chose `index_size / block_size`. That is not merely
one option among many: `index_size` is *constructed* from the four page classes
plus the metapage, under a comment saying so
([pgstatindex.c#index_size](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L357)):

```text
index_size = (1 + leaf_pages + internal_pages + deleted_pages + empty_pages) * BLCKSZ
```

So the two candidate denominators differ by **exactly one page, always** — the
metapage — and the difference is provable rather than empirical. The run scored
both. The page-class sum:

| Reading | Fixtures scored | Undefined | Rebuild orders | Worst gap vs the filed reading |
|---|---|---|---|---|
| `index_size / block_size`, as filed | 126 / 116 | 0 | 92 / 83 | — |
| `internal + leaf + empty + deleted` | 126 / 116 | **1** | 92 / 83 | **7.30** / **5.30 points** |

The page-class sum is zero for an index whose file is only a metapage, and
`float8_div` raises `division by zero` on a zero divisor unless the dividend is
already `NaN`
([float.h#float8_div](../../../../raw/postgres-17/src/include/utils/float.h#L237-L251)).
So that reading is undefined on exactly the rows the `NaN` guard is about, and
the guard does not rescue it: a zero denominator raises rather than producing a
`NaN` for a `CASE` to catch. The filed reading never divides by zero, because
the metapage always counts. **The asker's choice is the safer one, and it is
the only one of the two that is total.**

The harness computes the variant through `NULLIF`, so the run records that row
as undefined rather than dying on it. The `division by zero` lines in the error
audits come from the `facts` stage instead, which reads both halves of the rule
on purpose. On 17.11 `'NaN'::float8 / 0` returns `NaN`, because `float8_div`
raises on a zero divisor only when the dividend is not already `NaN`, and
`0::float8 / 0` raises, so the 17 leg logs one such line; the 12.2 server raised
on both, so the 12 leg logs two.

**`fillfactor`.** The asker chose the index's own reloption with 90 where unset,
which is what the engine resolves for that index: `BTGetFillFactor` reads
`BTOptions.fillfactor` when `rd_options` is set and falls back to
`BTREE_DEFAULT_FILLFACTOR`, which is 90
([nbtree.h#BTGetFillFactor](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1143),
[nbtree.h:200](../../../../raw/postgres-17/src/include/access/nbtree.h#L200)).
This matters to the suite, which builds fixtures at 70, 90 and 100: a hardcoded
90 would misread every one of them.

### Where it errs, and in which direction

The error is not a mood of the formula. It is the sum of exactly three terms,
and the run reports each of them per fixture rather than describing them.
Writing `m` for the leaf fraction the statement predicts survives a rebuild,
`LEAST(1, density / fillfactor)`, the identity is

```text
err x total_pages = (leaves_after  - leaf_pages * m)   the leaf model's own error
                  + (internal_after - internal_pages)  the levels it never models
                  + (empty_after + deleted_after)      dead pages the rebuild kept
```

It is an identity, not a fit: substituting `total_pages = 1 + internal + leaf +
empty + deleted` into `score - actual` cancels everything else. The `accuracy`
stage prints the three terms beside `err` and the largest residual across all
fixtures, which is **0.1 points** on both legs — the rounding of three
one-decimal columns against a fourth, and nothing more.

| Term | What it is | Sign | Measured on 17.11 |
|---|---|---|---|
| **leaf** | the leaf level repacked to a whole number of pages at a density the build only approximates | either in general; **never negative** where a rebuild writes back as many leaves as it found | mean **−0.13**, worst +6.6 (`p120`) and −3.6 (`p32`); ≥ 0 on all **31** fixtures whose rebuild wrote the same number of leaves, positive on 15 |
| **internal** | every level above the leaf level: in the denominator, never in the numerator | **≤ 0 on every fixture measured**, not by construction | mean **−0.34**, worst −6.3 (`p32`); **47** of 126 fixtures shrank an internal level, **0** grew one |
| **dead** | `empty` and `deleted` pages a rebuild failed to reclaim | ≥ 0 | **0.00 on every fixture, both legs** — a rebuild left no dead page anywhere |

Four consequences follow, and each replaces a plausible story with a
measurement.

**The larger bias is the internal term, and it is conservative.** A rebuild
shrinks the upper levels roughly in proportion to the leaf level, and the
numerator credits the rebuild with none of that, so the score reads low on any
index deep enough to have upper levels worth counting. It is the larger part of
the worst under-estimate: `p32` scores 79.8 against a measured 89.6, and of
those 9.8 points, **6.3 are internal pages** — 46 internal pages before the
rebuild, 6 after — against 3.6 from the leaf model. It is not a size effect;
`x107`, at 8,105 pages the largest churned fixture (`x110`, at 8,507, is larger
and untouched), errs by −3.4. Nothing in the engine makes this term one-signed.
A sorted build packs every level above the leaf level to the fixed 70 % and does
not choose its page boundaries for shorter separator keys, while an insert-grown
index's internal pages fill past 70 % between splits and its split points are
chosen for truncation
([nbtsort.c#truncation-not-biased](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L912-L915),
[nbtsplitloc.c#nonleaf-fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L285)),
so a rebuild can write more internal pages than it found. In this run it never
did, on either leg.

**The leaf term leans the other way wherever a rebuild keeps the leaf count.**
When a rebuild writes back as many leaves as it found, the leaf term is exactly the
score's own leaf component, and the `GREATEST(0, ...)` floor keeps that at zero
or above: the formula can read such an index as partly reclaimable, never as
fuller than it is. 31 fixtures on 17.11 and 29 on 12.2 are in that set; the
leaf term is positive on 15 and 14 of them, up to +6.6 on `p120` on 17.11 and
+0.7 on 12.2, and negative on none. That is a one-signed lean toward
rebuilding, the unsafe direction, bounded by about one leaf page per file, which
is why it only shows on small files.

**The over-estimates are whole pages, not the metapage.** The metapage and the
root survive a rebuild, so they sit in `total_pages` on both sides of it and
cancel in the identity above: they contribute nothing to the error. What pushes
the score up is that a rebuild writes an integer number of leaves. `p25` holds 8
leaves at density 15.23, so the model predicts 1.35 leaves
survive and the rebuild writes **2**: 0.65 of a 10-page file is 6.5 points, and
the leaf term accounts for all of it. `p120` predicts 5.47 and the rebuild
writes 6. On a small file one page is a large fraction, which is why every
over-estimate above 2 points is on a file of 91 pages or fewer.

**One over-estimate is not rounding, and it is version-specific.** `f82` is a
freshly built, never-churned index of 89 leaves whose rebuild returns nothing,
and the statement scores it 5.1 rather than 0. Its density is 85.28 against a
fillfactor of 90, so the model believes 5 % of the leaf level is recoverable
when the build already packed it as tightly as this server packs it. The cause
is deduplication: a build that merges duplicates aims at the fillfactor through
a posting-list size cap and lands near, not on, it, and the code says so in as
many words — the cap exists to "get close to fillfactor% space utilization when
there happen to be a great many duplicates"
([nbtsort.c#maxpostingsize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1288-L1308)).
With posting-list tuples of up to a tenth of a page, the item a finished page
hands on to the next one is a large share of the page
([nbtsort.c#_bt_buildadd-last-item](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L873-L884)).
The same fixture on 12.2, where nothing deduplicates, builds **274 leaves in a
278-page file** against 89 leaves in 91 pages, and errs by **+0.1**.

The under-estimate is the safe direction for a rebuild signal and it is the
larger of the two. No over-estimate reached a false-positive band on any
fixture.

By family, the error is flat — no family is systematically mispriced:

| Family | Fixtures, 17 | Mean abs error, 17 | Fixtures, 12 | Mean abs error, 12 |
|---|---|---|---|---|
| gate (family 1) | 25 | 0.88 | 16 | 0.92 |
| partial (family 2) | 60 | 1.25 | 60 | 1.03 |
| falsepos (family 3) | 8 | **0.85** | 8 | **0.13** |
| falseneg (family 4) | 6 | 1.27 | 6 | 0.52 |
| control (family 5) | 20 | 0.27 | 20 | 0.28 |
| zero (family 6) | 7 | 1.11 | 6, `p120` unscored | 0.20 |

Family 3 exists to make "rebuild everything" fail, and the heuristic left all
eight alone on both majors, scoring every one of them between 0.0 and 5.1 against
a measured rebuild of 0.0.

The one family whose error differs between the majors is family 3, at 0.85
against 0.13, and the cause is the `f82` effect above. Family 6 differs in this
run only because `p120` was scored on one leg: its other six fixtures err
identically on both majors, 0.20 points on average. Family 3's fixtures are
fresh builds, so their density is whatever the build achieved, and three of the
eight build a smaller file on 17.11 than on 12.2 — `f79` at 336 pages against
1,207, `f81` at 87 against 278, `f82` at 91 against 278 — because their subsets
are duplicate-heavy and 17.11 deduplicates them. Two of those three carry the
whole difference in error: `f81` at 0.9 against 0.1, and `f82` at 5.1 against
0.1.

That is the substantive cross-version difference this page found, and it runs
the opposite way to the one a reader might expect: on fresh duplicate-heavy
indexes the formula is slightly *less* accurate on the newer major, because the
newer major writes them into fewer pages of wide posting-list tuples that end
short of the fillfactor, and the formula reads that shortfall as reclaimable
space. The size is harmless — it over-estimates by at most 5.1 points on an
index the oracle says is already optimal, nowhere near a rebuild order — but it
leans the unsafe way, toward rebuilding, it is a real asymmetry, and it is not
visible in the headline numbers.

Family 4 exists to make "rebuild nothing" fail, and the heuristic rebuilt **five
of the six** on both majors. It left `f88` alone — score 43.1 against an actual
40.5 on 17.11, and 44.1 against 43.6 on 12.2. That is scored `PASS` rather than
`FALSE NEGATIVE`, because the band triggers only at an actual of 50 or more, so
the heuristic and the oracle agree that this index is not worth rebuilding. It
does mean the fixture does not exercise what family 4 was built for; see
[Open Questions](#open-questions).

### The NaN defect, and the guard that closes it

**Before the guard, an index with no leaf pages scored `NaN`, and `NaN >= 0.5` is
true, so the heuristic ordered a rebuild that cannot return a byte. The two
`CASE` expressions map that `NaN` to 0 and the defect is gone.**

Four engine facts compose into the defect:

1. `pgstatindex` reports `avg_leaf_density` as the literal string `NaN` when
   `max_avail` is zero, which is exactly when no leaf page was scanned
   ([pgstatindex.c#avg_leaf_density-NaN](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L367)).
2. `NaN` propagates through the arithmetic. The addition, subtraction,
   multiplication and division are the inline `float8_pl`, `float8_mi`,
   `float8_mul` and `float8_div`. Each computes in C, where a `NaN` operand
   yields a `NaN` result, and then checks only for overflow, underflow or a zero
   divisor, none of which a `NaN` result trips. The one place a `NaN` operand is
   treated specially, `float8_div`'s zero-divisor test, only ever spares a `NaN`
   dividend from raising
   ([float.h#float8_pl](../../../../raw/postgres-17/src/include/utils/float.h#L157-L167),
   [float.h#float8_mi](../../../../raw/postgres-17/src/include/utils/float.h#L181-L191),
   [float.h#float8_mul](../../../../raw/postgres-17/src/include/utils/float.h#L207-L219),
   [float.h#float8_div](../../../../raw/postgres-17/src/include/utils/float.h#L237-L251)).
   So `1 - NaN/90` is `NaN` and `0 * NaN` is `NaN`.
3. `GREATEST(0, NaN)` is `NaN`, because `NaN` sorts after every non-`NaN`
   value. That ordering is decided in one place. `GREATEST` is a `MinMaxExpr`,
   which `ExecInitExprRec` compiles against the type's **B-tree comparison
   function**
   ([execExpr.c#MinMaxExpr](../../../../raw/postgres-17/src/backend/executor/execExpr.c#L2194-L2201)).
   `ExecEvalMinMax` holds the first argument, `0`, and calls that function with
   the held value on the left and the next argument, `NaN`, on the right,
   adopting the right-hand value when the result is negative
   ([execExprInterp.c#ExecEvalMinMax-compare](../../../../raw/postgres-17/src/backend/executor/execExprInterp.c#L3158-L3170)).
   For `float8` that function is `btfloat8cmp`, which is `float8_cmp_internal`
   ([float.c#btfloat8cmp](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L966-L973),
   [float.c#float8_cmp_internal](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L903-L909)).
   There `float8_gt(0, NaN)` is false and `float8_lt(0, NaN)` is true, because
   `float8_lt` is true whenever its right argument is `NaN` and its left is not,
   so the comparison returns −1 and `NaN` is kept
   ([float.h#float8_lt](../../../../raw/postgres-17/src/include/utils/float.h#L291-L295),
   [float.h#float8_gt](../../../../raw/postgres-17/src/include/utils/float.h#L315-L319)).
   The header states the rule both comparators implement: all `NaN`s are equal
   and larger than any non-`NaN`
   ([float.h#NaN-ordering](../../../../raw/postgres-17/src/include/utils/float.h#L255-L259)),
   and the window-function code restates it
   ([float.c#NaN-sorts-after](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L1038-L1041)).
4. The comparison `NaN >= 0.5` is **true** for the same reason, and its own
   implementation says so without any appeal to the ordering: the `>=` operator
   on `float8` is `float8ge`
   ([float.c#float8ge](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L957-L964)),
   which returns `float8_ge`, and `float8_ge` returns true on a `NaN` left
   argument before it ever looks at the right one
   ([float.h#float8_ge](../../../../raw/postgres-17/src/include/utils/float.h#L327-L331)).
   So `reindex_signal` is set.

The suite has a fixture for precisely this shape — test 116, "the subset empty
from the start and measured empty" — and the unguarded statement fails it on
both majors, as the single `CRITICAL FALSE POSITIVE` in each confusion matrix.
With the guards it scores 0.0 against a measured 0.0 and passes. Both columns
come from the same run, the unguarded one recomputed by the harness beside the
filed one:

| num | fixture | total_pages | leaf_pages | score unguarded | score as filed | actual | verdict as filed |
|---|---|---|---|---|---|---|---|
| 116 | `p116` | 1 | 0 | `NaN` | **0.0** | 0.0 | `PASS` |

It is also the one fixture on which the two denominator readings part company:
the page-class sum is 0 there, so that variant is undefined rather than wrong,
and it is the `nometa_undefined = 1` the `accuracy` stage reports on each leg.

**One fixture understates the problem, which is why the cluster-scale numbers
matter more.** Before the guards, 138 of the 233 rows the 17 leg would have
ordered rebuilt and 133 of 219 on the 12 leg scored `NaN`, every one an index
whose entire file is the 8,192-byte metapage. Most are the empty TOAST and
catalog indexes of a fresh cluster: on 17.11, 92 in `pg_toast` and 40 in
`pg_catalog`, among them `pg_default_acl_role_nsp_obj_index`,
`pg_replication_origin_roname_index`, `pg_transform_type_lang_index` and
`pg_trigger_tgconstraint_index`. The other six are objects this run created:
`p116`, the guard fixtures `i_empty`, `t_empty_pkey` and `t_part_1_id_idx`, and
the empty primary keys of two harness tables, `res_pkey` and `skipped_pkey`.
On 12.2 the 133 are 95 in `pg_toast`, 33 in `pg_catalog` and five of the run's
own, the same objects less `skipped_pkey`, whose table holds that leg's skips.
With the guards each of them scores `0.0000` and is not signalled:
**0 of 138** on 17.11 and **0 of 133** on 12.2.

The population is a property of a new cluster rather than of the defect, and the
page says so under [Open Questions](#open-questions). What is not a property of
the population is the shape of the failure: every one of these files is a single
metapage, so a rebuild of any of them returns nothing, and an unguarded
automatic signal would have issued a rebuild for each on every run, forever.

#### What a NaN density means, and why the two guards agree

**A `NaN` density means the file is one metapage, and nothing else.** That is
the fact that decides how much the guard's placement matters, and in normal
operation it is an engine invariant rather than a property of this run's
population. The one exception is the residue of a crash, described below.

`avg_leaf_density` is `NaN` exactly when `max_avail` is zero, which is exactly
when the scan classified no page as a leaf. The tempting reading is that this
covers two shapes — an empty index, and an index whose pages have all been
deleted — and that they want opposite verdicts. **The second shape does not
exist.** `_bt_pagedel` refuses to delete a page that is rightmost on its level
or is the root, and it rechecks that on every iteration
([nbtpage.c#_bt_pagedel-refusals](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1877-L1905));
page deletion only ever begins at an empty leaf, and the README states the
restriction as an invariant of the algorithm
([README#never-delete-rightmost](../../../../raw/postgres-17/src/backend/access/nbtree/README#L236-L245),
[README#tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L365-L367)).
So an index that ever held an entry keeps at least one live leaf page however
much is vacuumed out of it, and `leaf_pages` never reaches 0 while
`deleted_pages` is above 0.

The only way to a leaf-free file is to have no entries to build a leaf from.
`_bt_uppershutdown` writes the metapage pointing at `P_NONE` when the build had
no data at all
([nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1118-L1128)),
and `pgstatindex`'s per-block loop starts at block 1, so a one-block file is
classified as nothing at all
([pgstatindex.c#block-loop](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L279-L283)).

The exception is an all-zero page. A backend can extend an index by a page and
crash before it logs the page's initialization, and nbtree reuses such a page
when it later finds it
([nbtpage.c#all-zero-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L911-L923)).
`pgstatindex`'s B-tree loop has no test for one: it reads every page's flags
through the page's special space and buckets whatever is not deleted,
half-dead or a leaf as internal
([pgstatindex.c#page-classes](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L326)),
where the same file's hash reader counts a new page as unused
([pgstatindex.c#pgstathashindex-new-page](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L655-L656)).
On an all-zero page the special-space offset is zero
([bufpage.h#PageGetSpecialPointer](../../../../raw/postgres-17/src/include/storage/bufpage.h#L336-L341)),
so the flags read as zero and the page counts as an internal page: never a
leaf, and never credited as reclaimable, although a rebuild drops it. No fixture
builds one, because it takes a crash; see [Open Questions](#open-questions).

Guard fixture `i_alldel` measures the boundary: 200,000 rows, every row
deleted, vacuumed twice. Both majors leave the same shape, and it is not the
`NaN` shape.

| `rs.i_alldel` | `total_pages` | `internal` | `leaf` | `deleted` | `density` | score | measured rebuild |
|---|---|---|---|---|---|---|---|
| after the deletes and two `VACUUM`s | 551 | 2 | **1** | 547 | 0.05 | 99.5 | 99.8 |
| after `REINDEX INDEX`, so with no entries at all | 1 | 0 | **0** | 0 | `NaN` | 0.0 | — |

The consequence for the statement is that `leaf_pages = 0` implies
`deleted_pages = empty_pages = 0`, so on a `NaN` row the whole numerator is
zero whichever guard is applied, and **the inner and the outer `CASE` reach the
same verdict on every index that can exist**. The inner one is the one that
fires; the outer one never does once the inner one is in place. Both are kept:
the inner because it is the natural place to say what a missing density means,
and the outer as a backstop against a later edit reintroducing an undefined
value into the numerator. Neither is load-bearing against the other, and the
run checks the claim rather than assuming it — the `facts` stage counts rows
where `leaf_pages = 0` and `total_pages = 1` disagree, and rows with a `NaN`
density and live leaves, and both counts are **0** on both legs.

One detail the test itself depends on: the predicate must be
`density = 'NaN'::float8`. PostgreSQL defines `NaN = NaN` as **true**: the `=`
operator on `float8` is `float8eq`
([float.c#float8eq](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L912-L919)),
which returns `float8_eq`, and `float8_eq` answers `isnan(val2)` when its left
argument is `NaN` instead of falling through to the C `==`
([float.h#float8_eq](../../../../raw/postgres-17/src/include/utils/float.h#L267-L271));
the window-function `in_range` path states the same rule in a comment
([float.c#NaN-equals-NaN](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L1043-L1047)).
The `<>` operator is `float8ne`, which returns `float8_ne`, and that answers
`!isnan(val2)` when its left argument is `NaN`, so it is false for two `NaN`s
([float.c#float8ne](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L921-L928),
[float.h#float8_ne](../../../../raw/postgres-17/src/include/utils/float.h#L279-L283)).
So the C-style `density <> density` idiom never fires and would leave the defect
in place while looking like a guard.

The guards are not a tuning change. They remove an undefined value from a
comparison and nothing else, and the run checks that claim rather than asserting
it. On the fixture set they moved exactly one verdict, `p116`'s, taking the
rebuild orders from 93 to 92 on 17.11 and from 84 to 83 on 12.2 and leaving the
rest untouched. Over the whole candidate population they moved 138 and 133
verdicts, every one a metapage-only file, and changed **no finite score at all**
— `finite_scores_that_differ` is 0 on both legs.

### What the guard fixtures show

Schema `rs` is not part of the shared suite and carries no verdict band. It
exists to put the statement's edges under the same oracle, and four of its
readings bear on the answer. Every row below pairs the statement's score with a
measured `REINDEX INDEX` on 17.11:

| Fixture | Shape | `density` / `fillfactor` | score | measured rebuild |
|---|---|---|---|---|
| `i_fresh` | a fresh build, fillfactor unset | 90.00 / 90 | 0.0 | 0.0 |
| `i_ff50` | a fresh build at fillfactor 50 | 49.81 / 50 | 0.4 | 0.0 |
| `i_ff10` | a fresh build at fillfactor 10 | 9.62 / 10 | 3.8 | 0.0 |
| `i_ff100` | a fresh build at fillfactor 100 | 99.82 / 100 | 0.2 | 0.0 |
| `i_dup` | 100 rows per key, untouched | **91.38 / 90** | 0.0 | 0.0 |
| `i_sparse` | nine tenths of the rows deleted and vacuumed | 9.26 / 90 | 89.1 | 89.7 |
| `i_head` | the leading nine tenths of the key range deleted | 87.91 / 90 | 89.5 | 89.7 |
| `i_alldel` | **every** row deleted and vacuumed twice | 0.05 / 90 | 99.5 | **99.8** |
| `i_one` | one entry, two pages | 0.29 / 90 | **49.8** | **0.0** |
| `i_empty` | an index on an empty table | `NaN` / 90 | 0.0 | 0.0 |

**The score reads a correctly built index as correctly built, at every
fillfactor.** That is the control the formula has to pass before its
high scores mean anything, and it passes at 90, 50, 10 and 100 with at most 3.8
points of noise. It is also where the `fillfactor` reading earns its keep: a
statement that hardcoded 90 would read `i_ff10` as 89 % reclaimable and order a
rebuild of an index that is exactly as its owner asked for it.

**`i_alldel` is the emptiest shape a live B-tree reaches**, and the statement
prices it at 99.5 against a measured 99.8. It is also the fixture that bounds
what the `NaN` guards can be tested against; see
[What a NaN density means, and why the two guards agree](#what-a-nan-density-means-and-why-the-two-guards-agree).

**`i_dup` sits above its own fillfactor**, at 91.38 against 90. That is the
soft-limit behaviour named under
[Why the formula is accurate](#why-the-formula-is-accurate) rather than an
anomaly, and it is why the statement's `GREATEST(0, ...)` floor is load-bearing:
without it this index would score a negative reclaim.

**`i_one` is the sharpest edge on the page, and the formula survives it by 0.2
points.** A two-page index holding a single entry has a leaf 0.29 % full, so the
leaf term claims essentially the whole leaf page, which is half the file — a
score of 49.8 against a rebuild that returns nothing. It does not signal,
because 49.8 is below 50, and no one-entry index can do worse: a build or a
rebuild of a single entry always writes these same two pages, and a larger file
still holding one entry carries internal or deleted pages that a rebuild does
return. The edge belongs to files of a few pages holding a few entries, where
the one leaf a rebuild cannot avoid writing is a large share of the file. An
automatic signal that also skipped indexes below a handful of pages would not
lose anything this page measured.

**Who can run it, and what it costs.** `pgstattuple` 1.5 revokes `EXECUTE` on
both `pgstatindex` overloads from `PUBLIC` and grants it to
`pg_stat_scan_tables`
([pgstattuple--1.4--1.5.sql#pgstatindex-text](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L37),
[pgstattuple--1.4--1.5.sql#pgstatindex-regclass](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)),
and the run confirms both halves for each overload, calling the `regclass` one
the statement uses as well as the `text` one an unadorned string literal
resolves to: a role with no grant is refused with `permission denied for
function pgstatindex` by both, and a member of `pg_stat_scan_tables` reads the
index through both. An automatic signal therefore needs a role with that
membership or an explicit grant. The statement also reads every page of every
B-tree it scores — 363 indexes, 136,482 pages, 1,066 MB on the 17.11 sandbox and
349 indexes, 141,488 pages, 1,105 MB on 12.2, counts that move by a few dozen
pages between runs with the catalogs — so it is a full scan of the index population each
time it runs, which is the cost that decides how often it can be scheduled
rather than the wall clock, which on a `fsync = off` disposable cluster is not a
durability-realistic figure.

### The threshold

**50 % is inside the admissible range on both majors, and two fixtures' scores
decide how wide that range is.** That is a weaker claim than "50 % is optimal",
and it is the one the measurement supports. Two scorings of the same sweep say
why.

**By the suite's own bands**, a threshold is acceptable when no fixture lands in
a false-positive or false-negative band. Every threshold from **35 % to 65 %**
on 17.11, and from **35 % to 70 %** on 12.2, has zero violations, so the run
cannot separate them: 40 % would have scored exactly as well as 50 %. A
threshold is band-clean when it sits above the score of every fixture whose
rebuild returned under 35 % and at or below the score of every fixture whose
rebuild returned 50 % or more, so the range is set by two scores, which the
`accuracy` stage prints with the fixtures that hold them:

| Edge | 17.11 | 12.2 |
|---|---|---|
| highest score among rebuilds under 35 % | `p66`, 33.0 against a measured 33.2 | `p66`, 33.0 against 33.2 |
| lowest score among rebuilds of 50 % or more | `p25`, **66.5** against a measured **60.0** | `f86`, `f87`, `f89` and `f90`, 73.9 against 74.5 |

The lower half of the range, 35 to 50 %, exists because the bands penalize
neither rebuilding nor keeping an index whose rebuild returns 35 to 50 %; it is a
property of the bands rather than of the fixtures. The upper edge on 17.11 sits
6.5 points above the rebuild that fixes it, because `p25` is one of the
whole-page over-estimates described under
[Where it errs, and in which direction](#where-it-errs-and-in-which-direction);
on 12.2, where `p25` scores 78.8 against 75.0, the edge is where the rebuilds
themselves resume.

**By agreement with a 50 % cut on the measured rebuild**, agreement peaks at
50 %. That is this page's own construct rather than one of the suite's bands,
and it cannot do otherwise: the score tracks the measured rebuild to about a
point, so asking how often `score >= t` matches `actual >= 50` is bound to peak
at `t = 50`. It measures calibration, and it is reported as that rather than as
the reason to choose 50.

What the population does bound is the resolution. No fixture's rebuild lands
between **49.9 %** and **60.0 %** on 17.11, or between **49.9 %** and **74.3 %**
on 12.2, and only three land between 35 % and 50 % on either, so a threshold in
those gaps is scored on almost nothing; see [Open Questions](#open-questions).

Sweeping the threshold over the guarded formula's fixtures:

| Threshold | Critical false pos | False pos | False neg | **Band violations** | Rebuilt | Agrees with a 50 % cut |
|---|---|---|---|---|---|---|
| 5 % | 2 | 4 | 0 | 4 | 99 | 119 |
| 10–20 % | 0 | 2 | 0 | 2 | 97 | 121 |
| 25–30 % | 0 | 1 | 0 | 1 | 96 | 122 |
| **35–40 %** | 0 | 0 | 0 | **0** | 95 | 123 |
| **45 %** | 0 | 0 | 0 | **0** | 94 | 124 |
| **50–65 %** | **0** | **0** | **0** | **0** | 92 | **126 of 126** |
| 70 % | 0 | 0 | 1 | 1 | 91 | 125 |
| 75 % | 0 | 0 | 5 | 5 | 87 | 121 |
| 80 % | 0 | 0 | 9 | 9 | 83 | 117 |
| 85 % | 0 | 0 | 18 | 18 | 74 | 108 |
| 90 % | 0 | 0 | 87 | 87 | 5 | 39 |
| 95 % | 0 | 0 | 90 | 90 | 2 | 36 |

The `False pos` column counts every fixture rebuilt below the 35 % band, so it
includes the critical ones; `Band violations` is that column plus `False neg`,
and it is the column the suite's contract is written against.

Read by bands, the table is flat from 35 % to 65 % and the choice of 50 % inside
that range is not something this run decided. Read by agreement with a 50 % cut,
it peaks at 50 through 65 — which, as above, it was always going to. **What the
table does establish is the shape of the failure on each side**: below 35 % the
method starts rebuilding indexes the oracle says are not worth rebuilding —
`p66` from 30 %, and `p72` too from 20 % — and it buys nothing by it, because
there is no false negative at 50 % to recover; at 70 % it starts leaving a
reclaimable index alone, `p25`. The 12 leg's sweep has the same shape with the
upper edge one step further out, band-clean from 35 % through **70 %**, with the
first false negatives at 75 %.

Note what the guards did to this table: the `CRITICAL FALSE POSITIVE` that used
to sit at *every* threshold, and which no threshold could fix because `NaN`
satisfies every comparison, is gone. The two rows left in the critical column at
5 % are `p120`, an 8-page file scored 6.6, and `f82`, the 91-page deduplicated
build scored 5.1, both against a measured 0.0: over-estimates of a fresh build,
not undefined values. The asker's description of 50 % as *conservative* is
borne out in both directions rather than one.

### What the two majors do differently

At the level of the headline the two majors are indistinguishable — over the
deterministic fixtures 0.94 and 0.75 points of mean error, 0.9991 and 0.9994
correlation, zero false positives and zero false negatives on both. That is
unsurprising: the formula reads page
counts and a density ratio, and neither is a version-specific quantity.

Underneath it, two things do differ, and both come from deduplication.

**The formula is slightly less accurate on 17.11, on fresh duplicate-heavy
indexes**, for the reason given under
[Where it errs, and in which direction](#where-it-errs-and-in-which-direction):
a deduplicating build lands near rather than on the fillfactor, and the formula
reads the shortfall as reclaimable. Family 3's mean error is 0.85 on 17.11
against 0.13 on 12.2, and the guard fixture `i_dup` shows the size effect
directly — 169 pages on 17.11 against 552 on 12.2 for the same 200,000 rows at
100 rows per key, a file about three tenths the size, scored 0.0 against a
measured rebuild of 0.0 on both.

**Two engine behaviours the run records differ too.** Both majors agree that
`NaN >= 0.5` is true, that `GREATEST(0, NaN)` is `NaN` and that `0 * NaN` is
`NaN`, so the defect and its guard behave identically. They disagree about
`'NaN'::float8 / 0`: 17.11 returns `NaN`, because `float8_div` raises on a zero
divisor only when the dividend is not already `NaN`
([float.h#float8_div](../../../../raw/postgres-17/src/include/utils/float.h#L237-L251)),
while the 12.2 server raised `division by zero` on the same expression. It
changes nothing about the filed statement, whose denominator is never zero, and
it is why the 12 leg's error audit records two `division by zero` lines where
the 17 leg records one. They also disagree about an index the catalog marks not
valid: 17.11's `pgstatindex` refuses it with `index "i_invalid" is not valid`
([pgstatindex.c#indisvalid-refusal](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L240-L250)),
while the 12.2 server read `rs.i_invalid` without an error, so the 12 leg's
error audit has no such line. The filed statement never reaches that case
either: its candidate filter requires `indisvalid`.

What differs most is what the *suite* could build:

| | 17.11 | 12.2 |
|---|---|---|
| fixtures in the plan, after the skips | 126 | 116 |
| skipped as unbuildable | 0 | **9** |
| skipped for an unmet precondition, `p120` | 0 | 1, this run only |
| family 1 fixtures scored | 25 | 16 |
| `_bt_allequalimage` `DEBUG1` verdicts logged | 11 safe, 13 unsafe | **0, none exist** |

All nine skips are family 1 fixtures 13 to 16, each refused with
`operator class "..." does not exist for access method "btree"`, because the
operator classes those fixtures index through could not be created in the first
place: B-tree support function 4 and the equal-image callbacks they register do
not exist on the 12.2 server. The run records each refusal in the server's own
words rather than asserting the cause, which is what the concept page's feature
gate asks for; see
[Feature gates that skip a fixture](../../common-concepts/mandatory-btree-bloat-tests.md#feature-gates-that-skip-a-fixture).

**Why that gate falls where it does** is a matter of the v17 checkout's own
history, not of the v12 source, which this page may not cite. Support function
4 is `BTEQUALIMAGE_PROC`, defined as `4` in the pinned tree
([nbtree.h#BTEQUALIMAGE_PROC](../../../../raw/postgres-17/src/include/access/nbtree.h#L703-L710)),
and it arrived one commit before deduplication itself. Commit `612a1ab767`
(2020-02-26, "Add equalimage B-Tree support functions.") adds the amproc number,
the `btequalimage` and `btvarstrequalimage` builtins and `_bt_allequalimage`;
its child, `0d861bbb70` ("Add deduplication to nbtree."), adds
`src/backend/access/nbtree/nbtdedup.c`. Both descend from `615cebc94b`
(2019-07-01, "Stamp HEAD as 13devel") and are ancestors of `d10b19e224`
("Stamp HEAD as 14devel"), so both landed inside the PostgreSQL 13 development
cycle and first shipped in 13 — after the 12.2 server this page's other leg
runs. On the 12 leg the family's engine-side oracle is therefore silent rather
than wrong.

For how `pgstatindex` computes its columns on the 12.2 pin, see
[How pgstatindex Calculates Its Information in PostgreSQL 12 (unverified)](../../../v12/questions/indexing/how-pgstatindex-calculates-information.md);
this page cites v17 source only, per `AGENTS.md`.

**What the 12 leg followed, stated here because PostgreSQL 12 has no concept
page.** The 12 leg runs the same six `sql` blocks as the 17 leg, read out of
this page and hash-checked before use, so the suite it ran is the v17 concept
page's suite verbatim rather than a port of it: the six families, rule 1's cut
at the index build through the `snap_on_build` event trigger, rule 2's uniform
drain over the same 38 tables, rule 3's census recomputing the launcher's
analyze verdict from the engine's own effective per-table values, the catalog
forgeries after the census, the maintenance assumption's bracketed
`VACUUM (VERBOSE, ANALYZE)` after every churn, the no-defeat rule's four proofs,
the `REINDEX INDEX` oracle and the four verdict bands. The two legs differ in
three places, each forced by the older server and each recorded rather than
worked around: the nine feature-gated skips above; `wiki_flush()` waiting out
the statistics publish interval where `pg_stat_force_next_flush()` does not
exist; and `parse_verbose()` reading 12.2's wording of the `VACUUM (VERBOSE)`
dead-tuple line. Nothing else in the protocol is version-conditional.

Run over each whole cluster, the two reports overlap but are not identical:

| Cross-leg comparison | Value |
|---|---|
| rows the 17 report prints | 361 |
| rows the 12 report prints | 347 |
| index names both print | 291 |
| rows identical field for field | 193 |
| shared names whose rows differ | 98 |
| of those, in `pg_catalog` / `pg_toast` / `public` / `rs` | 55 / 2 / 40 / 1 |
| of those, scoring higher on 17 / lower on 17 / the same | 22 / 72 / 4 |
| of those, whose **signal** differs | **0** |
| names only the 17 report prints | 70 |
| names only the 12 report prints | 56 |

The comparison is made at the precision the report prints, a tenth of a point.
Of the 98 differing rows, 57 are catalog and TOAST indexes whose page counts
differ between the two majors' own system catalogs, and 41 are objects this run
created: suite fixtures whose files differ because 17.11 deduplicates them or
churns them into a different shape — `f82` scores 5.1 against 0.1, `f87` 89.9
against 73.9, `p25` 66.5 against 78.8, `p41` 75.3 against 88.3, `i_int4` 85.1
against 89.0 — the guard fixture `rs.i_dup`, and three harness bookkeeping
indexes whose tables hold different rows on the two legs. The run does not
attribute a cause to any single row. **All 98 agree on the signal.** The
catalog and TOAST keys make these counts a property of each run rather than of
the fixtures: the 2026-09-21 filing of this page, over the same fixtures, had
285 shared names, 187 identical rows, a 21 / 74 / 3 split and 76 and 62 names
printed by one report only.

The `crossleg` stage compares the two filed reports, so it says nothing about
what the cross-leg picture looked like before the guards; that comparison is not
part of this run. What each leg does measure is that the guards moved only its
own metapage-only rows and changed no finite score, so a cross-leg signal
disagreement could only ever have come from an index that is metapage-only on
one major and not on the other.

### What this run does not settle

The suite's own limits carry over, and three of them bite here. The suite fixes
one block size, runs no concurrency, and has no partitioned-table fixture, so
none of those is evidence either way for this formula; see
[What the suite does not cover](../../common-concepts/mandatory-btree-bloat-tests.md#what-the-suite-does-not-cover).
Beyond those, the limits specific to this page are filed under
[Open Questions](#open-questions). The two that bear hardest on the result are
about the population rather than the arithmetic. **The fixtures leave gaps
around the cut**: no fixture's rebuild lands between 49.9 % and 60.0 % on 17.11,
or between 49.9 % and 74.3 % on 12.2, so the sweep tests almost nothing inside
those gaps, and the band-clean range it reports is set by two fixtures' scores
rather than by the method's tolerance. And **the whole-cluster figures come from
two freshly `initdb`-ed clusters** rather than from any production population,
so the share of metapage-only indexes they report is a property of a new
cluster, and the counts move a little from run to run with the catalogs.

The others are that the deduplication interaction is scored only where the
suite's fixtures happen to exercise it, that `want_stage` predictions are
judgements rather than derivations, that test 120 is probabilistic and moves
between runs, that family 4's `f88` does not reach the band it was built to
test, that the statement returns every row or none when a candidate cannot be
locked or opened, and that a crash can leave all-zero pages `pgstatindex`
counts as internal.

## Measurement Script

Two scripts produce every number on this page, one per version leg:
`reindex_score_v17.sh` for 17.11 and `reindex_score_v12.sh` for 12.2. Both are
filed below in full, in Bash and SQL only.

**Last run: 2026-09-22**, both legs end to end from an empty sandbox, every
stage in one invocation per leg, the two legs side by side. The pins:

| Leg | Checkout | Commit |
|---|---|---|
| 17.11 | `raw/postgres-17` | `786db8dcf168bd9df8f55047337525ac19118b1c`, the pin in this page's front matter |
| 12.2 | `raw/postgres-12` | `45b88269a353ad93744772791feb6d01bc7e1e42`, the v12 pin in `wiki/versions.md` |

Each leg's `build` and `check` stages refuse any other commit and any changed
tracked file, the `build` stage writes the pin beside the install it made, and
the `cluster` stage copies it into the leg's platform file, where this run
recorded both commits above. The platform facts the numbers depend on:

| | Value |
|---|---|
| host | Darwin arm64 (macOS 27.0), Apple clang 21.0.0 |
| server | 17.11 (`server_version_num` 170011) and 12.2 (120002), built out of tree from `raw/postgres-17` and `raw/postgres-12` |
| `block_size` | 8192 on both |
| `max_data_alignment` | 8 on both |
| extension | `pgstattuple` 1.5 on both |
| regression suites | **All 225 tests passed** on 17.11, **All 192 tests passed** on 12.2, each with exit status 0, alongside **All 1 tests passed** for the `pgstattuple` check on each leg |
| wall clock | 4 minutes 45 seconds for the 17 leg and 10 minutes 25 seconds for the 12 leg, each from an empty sandbox with its build and regression suites included, the two run side by side at `JOBS=8` |

Earlier versions of the two scripts ran at the same pins on a Linux x86_64 host,
and on this host on 2026-09-21 and during this page's review on 2026-09-22.
Every fixture figure agreed across all of them except the probabilistic `p120`,
which the page reports both with and without; the whole-cluster and cross-leg
counts move a little between runs, because they are read over each run's own
catalog and TOAST indexes rather than over the fixtures. On a host
whose ICU has no `pkg-config` entry, as this one does not, `configure
--with-icu` needs `ICU_CFLAGS` and `ICU_LIBS` exported before either leg's
`build` stage.

**Every number on this page comes from that one run**, including the "before"
column of the guard comparison. The unguarded statement is no longer quoted
from an earlier run: the harness recomputes it beside the filed one from the
same `pgstatindex` output, as `nan_pct` and `nan_signal`, so before and after
are two readings of one population rather than two runs. When the statement
itself changed, `BASE_SQL` was updated in both scripts and both legs were re-run
end to end, per `AGENTS.md`'s requirement that the page's script be edited in
place and re-run rather than duplicated.

**The fixtures they score are the shared suite's, not this page's own.** The six
families, the five phases, the maintenance assumption, the rule that the
maintenance must not be defeated, the three porting rules, the `REINDEX INDEX`
oracle and the four verdict bands are defined once for this version in
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md).
Nothing in either script redefines them. The suite's harness, its fixture text
and its churn phase are filed here as `sql` blocks 2 to 6 and read out of this
page at run time, so both legs run the same suite and a text that does not hash
to the filed one stops the run.

The no-defeat rule's proofs were recorded on both legs and are clean. The
`maint` table holds one row per maintained table rather than one per statement,
so "67" below counts tables:

| Proof | 17.11 | 12.2 |
|---|---|---|
| tables carrying a maintenance statement, and how many completed | 67, all 67 | 67, all 67 |
| by source | `drain=38 fixture=28 prebuild=1` | `drain=38 fixture=28 prebuild=1` |
| worst "dead but not yet removable" count over those tables | **0** | **0** |
| tuples removed | 22,457,808 | 22,457,692 |
| horizon probes clean | 73 of 73 | 73 of 73 |
| skip or cancellation lines naming a fixture's table | **0** | **0** |

Schema `rs` holds 19 guard fixtures the suite does not cover and this page still
measures: the shapes `pgstatindex` refuses, an index the catalog says is not
valid, fresh builds at four fillfactors, an index on an empty table, a two-page
index, a sparse index, an index whose leading key range was deleted, an index
every entry was deleted from, and a duplicate-heavy index. Thirteen of the
nineteen are B-tree indexes the statement scores; the rest exist to be refused
or filtered out. No verdict band is applied to any of them.

### How to use the two leg scripts

| Item | The 17 leg | The 12 leg |
|---|---|---|
| Purpose | builds 17.11 from this page's pin out of tree, runs its regression suites, starts an isolated cluster, builds the shared mandatory suite, executes the filed heuristic exactly as filed, and scores every fixture against a measured `REINDEX INDEX` | the same on 12.2 from the v12 pin, plus a `crossleg` stage that compares the two legs' reports row by row out of the shared `out/` |
| Invocation | `bash reindex_score_v17.sh [stage ...]`, from the repository root | `bash reindex_score_v12.sh [stage ...]`, from the repository root |
| Stages | 17 stages plus `stop` and `clean`; with no argument every stage runs in the order below | the same, plus `crossleg` before `summary` |
| Environment | 7 variables, all with defaults: `WIKI_ROOT`, `PAGE`, `SANDBOX`, `JOBS`, `ROWS`, and this leg's own `SRC` and `PORT` | 8, all with defaults: the five shared ones, plus `SRC12`, `PORT12` and `EXTRA_CFLAGS`. It does not read `SRC` or `PORT` |
| Prerequisites | a C toolchain, ICU, readline and zlib headers, `sha256sum`, `git`, and the checkout at `raw/postgres-17` at the pin, which `build` and `check` verify with `git rev-parse` and `git status` | the same, against `raw/postgres-12` at the v12 pin. ICU 68 and later also need `EXTRA_CFLAGS` |
| Output | under `$SANDBOX/out`; **read `accuracy17.txt` first**, then `verdicts17.txt`, `maint_proofs17.txt`, `decide17.txt`, `report17.txt`, `skipped17.txt`, `census17.txt`, `facts17.txt`, `guard17.txt`, `errors17_summary.txt` | the same with `12` in every name, plus `crossleg.txt` |
| Runtime | about 5 minutes from an empty sandbox, build and `make check` included | about 10.5 minutes from an empty sandbox; the suite and churn stages sleep out the statistics publish interval because 12.2 has no `pg_stat_force_next_flush()` |
| Cleanup | `bash reindex_score_v17.sh clean` checks first that `$SANDBOX` resolves to a directory directly inside this repository's `.wiki-runtime/tmp` and carries the mark the script wrote when it created it, and refuses while the 12 leg's data directory is still there; only then does it stop the server, confirm the teardown and delete the sandbox. **`out/` is inside `$SANDBOX`, so copy it out first** | `clean` makes the same check, stops the 12 server and deletes only this leg's directories; run it before the 17 leg's `clean`, which refuses otherwise |

### The stages, both legs

Every stage but two can be re-run on its own once the stages it needs have run.
`score` and `guard` rebuild what they measure, so each refuses to run a second
time on the same fixtures: to score again, re-run every stage from `suite`
onward, and to run `guard` again, re-run `fixtures`, `report` and `decide` first.
The order matters in one place: `score` rebuilds every scored index, so
`report`, `decide`, `facts`, `cost` and `priv` must precede it, and `accuracy`
follows it. Any run that asks for a stage other than `stop` and `clean` first
creates or accepts the sandbox, and refuses one that is not directly inside
`.wiki-runtime/tmp` or that exists, is not empty and carries no mark.

| Stage | What it does |
|---|---|
| `build` | checks the checkout is at the pin with no tracked file changed, configures it out of tree, installs, then builds and installs `contrib/pgstattuple`, and writes the pin beside the install; skips when the binary exists and was built from the same pin, and stops when it was not |
| `check` | checks the pin again, runs `make check` and the `pgstattuple` check, and records one result line each; **stops the run** unless both exit 0 with an `All N tests passed` line |
| `cluster` | `initdb --locale=C --encoding=UTF8`, writes the settings below, starts on `PORT`, creates the database and the extension, records the platform facts and the pin |
| `texts` | extracts `sql` blocks 1 to 6 from this page and checks each one's SHA-256 against the constant at the top of the script; generates the harness view from block 1 with its `SET` lines dropped, printed, and its presentation `SELECT` replaced |
| `fixtures` | drops and rebuilds schema `rs`, the 19 guard fixtures, and drops the guard oracle's results with them |
| `suite` | phases 1 and 2 of the shared suite: the harness of block 2, family 1 from block 3 under `client_min_messages = debug1`, families 2 to 6 from block 4, then every fixture's build contract while it is still as built |
| `churn` | phase 3: rule 2's drain from block 5 with its maintenance step, then rule 3's census, the catalog forgeries and the churned snapshot from block 6, then the no-defeat rule's four proofs, which **die rather than score** a defeated fixture |
| `report` | phase 4: runs the filed heuristic **as filed**, both `SET` lines included, and records whether it executed, how many rows and columns it returned, and how many it signalled |
| `decide` | materializes the same text over its internal `final` stage so every intermediate column is visible; reports how far that reading agrees with the printed report, the fixture rows exactly and the whole population with the catalog drift between the two reads named; and prints the whole-cluster before-and-after of the two `CASE` guards, the unguarded score recomputed beside the filed one |
| `facts` | the version-local facts: candidate count, `total_pages` against both `pg_relation_size` and the page classes plus one, the `NaN` comparisons, the `leaf_pages = 0` against `total_pages = 1` identity, the metapage-only files by schema and by name outside the system schemas, the AM refusals, the invalid index, fresh-build density at four fillfactors, and the guard fixtures |
| `cost` | the B-tree population and size, and `EXPLAIN (ANALYZE, BUFFERS)` of the filed text |
| `priv` | calls both `pgstatindex` overloads, the `regclass` one the statement uses and the `text` one, as a role with no grant and as a member of `pg_stat_scan_tables`, and prints the `EXECUTE` privileges `pgstattuple` ships with, per overload |
| `score` | phase 5, the oracle: per fixture, reads what the statement said, calls `pgstatindex` itself, runs `REINDEX INDEX`, measures the file again, **and calls `pgstatindex` once more on the rebuilt file**, which is what the error decomposition is computed from. Writes the verdict tables, including the rows behind every contract count. **Destructive**, and refuses to run when these fixtures were already rebuilt |
| `accuracy` | the error of the score against the measured rebuild: the summary row, the per-family breakdown, the confusion matrix at 50 %, every disagreement, the threshold sweep scored both by the suite's bands and by a 50 % cut, where the fixtures' own rebuild sizes fall, the two scores that bound the band-clean range, the fixtures behind every violation up to 80 %, the two denominators beside the unguarded statement, the error decomposed into its three exact terms with the internal and leaf levels a rebuild shrank or grew, the leaf term wherever a rebuild kept the leaf count, family 3 as built, and the headline over the deterministic fixtures beside the headline including `p120` |
| `guard` | the same oracle over schema `rs`, with no verdict band applied. **Destructive**, and refuses to run when schema `rs` was already rebuilt |
| `errors` | the error audit: counts what the server logged after this run's mark and prints the distinct messages |
| `crossleg` | **12 leg only.** The two reports side by side out of the shared `out/`, with the differing rows counted by schema; it needs no server and skips itself with a note when the 17 leg has not written its report |
| `summary` | prints what landed in `out/` and the small result files |
| `stop` | checks the sandbox as `clean` does, then `pg_ctl -m fast -w stop`, then confirms no `postmaster.pid`, no postgres process on the data directory and an empty socket directory. It dies rather than report a stop that did not happen |
| `clean` | checks the sandbox before it touches anything — resolved, directly inside `.wiki-runtime/tmp`, carrying the script's mark, and on the 17 leg with no 12 data directory left in it — then `stop`, then deletes the sandbox (17 leg) or this leg's directories (12 leg) |

### What the scripts read from the environment

**The two legs do not share the names of their checkout and port variables**,
because both legs write into one sandbox and a single `SRC` or `PORT` would
point both of them at the same tree or the same port. The 17 leg reads `SRC`
and `PORT`; the 12 leg reads `SRC12` and `PORT12` and ignores `SRC` and `PORT`
entirely. The 12 leg reads one variable the 17 leg has no use for.

| Variable | Leg | Default | Meaning |
|---|---|---|---|
| `WIKI_ROOT` | both | `$PWD` | the repository root; everything else resolves beneath it |
| `PAGE` | both | this page's path | the file the six `sql` blocks are extracted from |
| `SANDBOX` | both | `$WIKI_ROOT/.wiki-runtime/tmp/rscore` | build, install, data, socket, SQL and output directories; the only tree either script writes |
| `JOBS` | both | `4` | `make -j` parallelism |
| `ROWS` | both | `200000` | the schema `rs` guard-fixture size. The shared suite's own fixture sizes are in its `sql` blocks and are not parameterised |
| `SRC` | 17 only | `$WIKI_ROOT/raw/postgres-17` | the pinned checkout, read only |
| `PORT` | 17 only | `55417` | the cluster's port |
| `SRC12` | 12 only | `$WIKI_ROOT/raw/postgres-12` | the pinned checkout, read only |
| `PORT12` | 12 only | `55412` | the cluster's port |
| `EXTRA_CFLAGS` | 12 only | `-O2 -g -DTRUE=1 -DFALSE=0` | ICU 68 dropped the `TRUE`/`FALSE` macros a 12.2 tree still uses, so the two defines go back in through `CFLAGS`. On a host whose ICU still defines them, set this to `-O2 -g` rather than to the empty string: `configure` treats an empty `CFLAGS` as set and then builds without optimisation |

The commit each leg is built from is not an environment variable: each script
carries it as the constant `PIN`, beside the six block hashes, so changing it
means editing the filed script. Both scripts export `PGPORT`, `PGHOST` and
`PGDATABASE` for their own `psql` calls, so a value in the caller's environment
is overridden rather than honoured.
Every helper call passes `PGOPTIONS="-c statement_timeout=30min -c
lock_timeout=60s"` per call rather than exported, because `pg_regress` keeps an
inherited `PGOPTIONS` and appends its own to it
([pg_regress.c#PGOPTIONS](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L783-L799)),
so an exported value would reach `make check`.

Every `psql` runs with `-X`, so a stray `~/.psqlrc` cannot change a reading.
Every `psql` that must succeed also runs with `-v ON_ERROR_STOP=1`, because
without it a failed statement inside a `-f` script still exits 0. Five call
sites per script deliberately omit it, and all five are places where the
server's refusal **is** the measurement: the `err()` and `val_or_err()` helpers,
which print the message a statement raised; the two connectivity probes in the
`cluster` stage, which are tested on their exit status instead; and the `priv`
stage's `pgstatindex` call, one call site that a loop runs for both roles and
both overloads, where the refusal of the role with no grant is the reading.

### The cluster settings

Each `cluster` stage writes these to `postgresql.conf` before the first start, so
every one is in force from the first connection and none is changed while the
cluster is up. These are disposable measurement clusters, not a configuration
recommendation. Each context is the one the pinned 17 checkout declares.

| Setting | Value | Context | Apply scope | Definition |
|---|---|---|---|---|
| `listen_addresses` | `''` | `PGC_POSTMASTER` | restart | [guc_tables.c#listen_addresses](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4436-L4445) |
| `port` | `55417` / `55412` | `PGC_POSTMASTER` | restart | [guc_tables.c#port](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2393-L2401) |
| `unix_socket_directories` | inside the sandbox | `PGC_POSTMASTER` | restart | [guc_tables.c#unix_socket_directories](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4425-L4434) |
| `shared_buffers` | `512MB` | `PGC_POSTMASTER` | restart | [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270) |
| `maintenance_work_mem` | `256MB` | `PGC_USERSET` | session or transaction | [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2465-L2474) |
| `max_parallel_maintenance_workers` | `0` | `PGC_USERSET` | session or transaction | [guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417) |
| `autovacuum` | `off` | `PGC_SIGHUP` | reload | [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457) |
| `fsync` | `off` | `PGC_SIGHUP` | reload | [guc_tables.c#fsync](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1096-L1107) |
| `logging_collector` | `off` | `PGC_POSTMASTER` | restart | [guc_tables.c#logging_collector](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1640-L1648) |

The scripts and the `sql` blocks also set these per session, with `SET`, `RESET`
or the libpq options string. Every one is `PGC_USERSET`, so each reaches only the
session that sets it, with no reload and no restart:

| Setting | Where it is set | Definition |
|---|---|---|
| `statement_timeout` | `30min` for every helper session through `PGOPTIONS` and for the guard fixtures; `15min` in the filed statement; `900s` in the harness and family 1; `0` in the maintenance sessions of blocks 4 to 6 | [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620) |
| `lock_timeout` | `60s` through `PGOPTIONS`; `5s` in the filed statement, the harness and family 1; `30s` for the guard fixtures; `0` in the maintenance sessions | [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631) |
| `idle_in_transaction_session_timeout` | `0` in the maintenance sessions of blocks 4 to 6 | [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642) |
| `client_min_messages` | `warning` in blocks 2 to 6 and for the guard fixtures; `debug1` for family 1, through `PGOPTIONS` and a `SET` | [guc_tables.c#client_min_messages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4776-L4785) |
| `maintenance_work_mem` | `256MB` again in family 1 and in block 4 | [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2465-L2474) |
| `default_statistics_target` | `1` for test 120's `ANALYZE` only, then `RESET` | [guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2070-L2079) |

`autovacuum` is off for isolation only, so no background worker moves a fixture
between phases; the maintenance it would have run is run by each fixture itself,
under the concept page's maintenance assumption. `fsync = off` makes the timings
on this page unusable as durability-realistic figures, which is why no timing is
quoted as a headline result.

### The PostgreSQL 17 leg script
```sh
#!/usr/bin/env bash
#
# reindex_score_v17.sh - the PostgreSQL 17 leg of the measurement behind "How
# Accurate Is the pgstatindex REINDEX_SCORE B-Tree Maintenance Heuristic, on
# PostgreSQL 17 and 12".  Bash and SQL only: build the pinned 17 checkout out
# of tree, run its regression suites, start an isolated cluster, build the
# wiki's shared mandatory B-tree bloat suite, run the heuristic exactly as
# filed, and score every fixture against a measured REINDEX INDEX.
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
# Schema rs holds what the suite does not cover and this page still measures:
# the shapes pgstatindex refuses, an index the catalog says is not valid, fresh
# builds at four fillfactors, an index on an empty table, a two-page index, a
# sparse index, an index whose leading key range was deleted, an index every
# entry was deleted from, and a duplicate-heavy index.  Those are guard
# fixtures, not scored fixtures, and no verdict band is applied to them.
#
# The pinned checkout is read only, and the build and check stages refuse to
# run unless it is at $PIN with no tracked file changed.  Everything this
# script writes lives under $SANDBOX, which must be a directory directly
# inside this repository's .wiki-runtime/tmp; main() marks it when it creates
# it, and stop and clean touch nothing that does not carry that mark.
#
# Usage, from the repository root:
#   bash reindex_score_v17.sh                  # every stage, in order
#   bash reindex_score_v17.sh score accuracy   # selected stages
#   bash reindex_score_v17.sh clean            # stop and delete the sandbox
#
# Stages: build check cluster texts fixtures suite churn report decide facts
#         cost priv score accuracy guard errors summary stop clean
#
# Environment: WIKI_ROOT PAGE SRC SANDBOX PORT JOBS ROWS
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v17/questions/indexing/btree-reindex-score-heuristic.md}"
SRC="${SRC:-$WIKI_ROOT/raw/postgres-17}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/rscore}"
PORT="${PORT:-55417}"
JOBS="${JOBS:-4}"
ROWS="${ROWS:-200000}"

# The commit this leg is built from, the one the page's front matter pins, and
# the file main() writes into a sandbox it created.
PIN=786db8dcf168bd9df8f55047337525ac19118b1c
MARKER=.reindex-score-sandbox

BUILD="$SANDBOX/build17"; INST="$SANDBOX/install17"; DATA="$SANDBOX/data17"
OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql17"; SOCK="$SANDBOX/sock17"; BIN="$INST/bin"
DB=score17
export PGPORT="$PORT" PGHOST="$SOCK" PGDATABASE=postgres

# SHA-256 of the sql blocks this page files, in page order.  BASE_SQL is the
# filed heuristic; BASE_HARNESS, BASE_GATE, BASE_SUITE, BASE_DRAIN and
# BASE_CENSUS are the shared suite's harness, its family 1 fixtures, its
# families 2 to 6, rule 2's drain and rule 3's census.  A text that does not
# hash to its constant stops the run: the scored text must be the filed text.
BASE_SQL=ffa9d4fa697e2b15c96e056b91c3774d5558f12e71b6c9d48e58c2d4beaf7822
BASE_HARNESS=6d33108ac87feb6b901f853b45edc8a130fa9a743cbc9d84c66401e54973a119
BASE_GATE=9d49596f780958fcae8982d19c168da9d6c87ad75c1b40c910dc34c135325e49
BASE_SUITE=5a29c8d84224fc3ca30062373f82940d9f41046e23a8ac74e8a4803277f00930
BASE_DRAIN=0d36f4980d9ee918ada8f24dffe8e0fc2566728d3079a35ebfdc373075a0d794
BASE_CENSUS=e3e1a0ae28599887c79482b4b3eda8a3ac4292c6bb089a01a45e723dcf0b09ec

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# check_pin: the build and the regression suites must come from exactly the
# commit the page records, with no tracked file changed.  Untracked files, such
# as a Finder .DS_Store, are not part of the build and are not checked.
check_pin() {
  local head dirty
  head=$(git -C "$SRC" rev-parse HEAD 2>/dev/null) || die "$SRC is not a git checkout"
  [ "$head" = "$PIN" ] || die "$SRC is at $head, not at the pinned $PIN"
  dirty=$(git -C "$SRC" status --porcelain --untracked-files=no 2>/dev/null) \
    || die "git status failed in $SRC"
  [ -z "$dirty" ] || die "$SRC has changed tracked files, so a build would not be the pin"
}

# make_sandbox: create $SANDBOX, or accept one this script created before, only
# when it is a directory directly inside this repository's .wiki-runtime/tmp
# once .. and symbolic links are resolved, and mark it as this script's.  An
# existing directory that is not empty and carries no mark is refused.
make_sandbox() {
  local tmp parent base
  mkdir -p "$WIKI_ROOT/.wiki-runtime/tmp" || die "cannot create $WIKI_ROOT/.wiki-runtime/tmp"
  tmp=$(cd "$WIKI_ROOT/.wiki-runtime/tmp" && pwd -P) || die "cannot resolve .wiki-runtime/tmp"
  base=$(basename "$SANDBOX")
  case "$base" in ''|.|..) die "refusing sandbox $SANDBOX: it names no directory of its own" ;; esac
  parent=$(cd "$(dirname "$SANDBOX")" 2>/dev/null && pwd -P) \
    || die "refusing sandbox $SANDBOX: its parent directory does not exist"
  [ "$parent" = "$tmp" ] || die "refusing sandbox $SANDBOX: it is not directly inside $tmp"
  if [ -e "$SANDBOX" ] && [ ! -f "$SANDBOX/$MARKER" ] \
     && [ -n "$(ls -A "$SANDBOX" 2>/dev/null)" ]; then
    die "refusing sandbox $SANDBOX: it exists, is not empty, and this script did not create it"
  fi
  mkdir -p "$SANDBOX" && : > "$SANDBOX/$MARKER" || die "cannot create $SANDBOX"
}

# sandbox_guard: the check stop and clean make before they touch anything.  The
# sandbox must resolve to a directory directly inside this repository's
# .wiki-runtime/tmp and carry make_sandbox()'s mark.  SANDBOX_REAL is the
# resolved path, and it is the only path clean deletes.
sandbox_guard() {
  local tmp
  tmp=$(cd "$WIKI_ROOT/.wiki-runtime/tmp" 2>/dev/null && pwd -P) \
    || die "refusing: $WIKI_ROOT/.wiki-runtime/tmp does not exist"
  SANDBOX_REAL=$(cd "$SANDBOX" 2>/dev/null && pwd -P) || die "refusing: cannot resolve $SANDBOX"
  [ "$(dirname "$SANDBOX_REAL")" = "$tmp" ] \
    || die "refusing: $SANDBOX_REAL is not directly inside $tmp"
  [ -f "$SANDBOX_REAL/$MARKER" ] \
    || die "refusing: $SANDBOX_REAL carries no $MARKER, so this script did not create it"
}

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
# val_or_err() runs a statement that answers on one major and raises on the
# other, and prints whichever came back.  ON_ERROR_STOP is deliberately absent:
# the refusal is the reading.
val_or_err() { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -At -q -d "$DB" -c "$1" 2>&1 | head -1; }

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
        printf "UPDATE /* wiki_rs_maint_verbose */ maint SET removed = %s, remain = %s, dead_not_removable = greatest(coalesce(dead_not_removable, 0), %s) WHERE tbl = '%s';\n" \
               "$removed" "$remain" "$dead" "$cur"
        cur="" ;;
    esac
  done < "$log"
}

# maint_skips: proof 1's other half.  A foreground VACUUM or ANALYZE that could
# not take its ShareUpdateExclusiveLock says so in the log, and a statement cut
# short by a timeout does too; either way the command returned without doing
# the work.  Only the lines after the churn mark are read, so a re-run does not
# inherit the lines of the run before it.
maint_skips() {
  local log="$OUT/server17.log" from line
  : > "$OUT/maint_skips17.txt"
  [ -f "$log" ] || return 0
  from=$(grep -n 'wiki_rs_maint_mark' "$log" | tail -1 | cut -d: -f1)
  [ -n "${from:-}" ] || from=$(grep -n 'wiki_rs_run_mark' "$log" | tail -1 | cut -d: -f1)
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
  q "SELECT /* wiki_rs_maint_after */ maint_after()" > /dev/null \
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
  # when there is something to count.
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
  [ -x "$SRC/configure" ] || die "no pinned checkout at $SRC; set SRC or run from the repository root"
  check_pin
  # An install is reused only when this script built it from the same pin.
  if [ -x "$BIN/postgres" ]; then
    [ "$(cat "$INST/.wiki_pin" 2>/dev/null)" = "$PIN" ] \
      || die "the install under $INST was not built from $PIN; run clean, then build"
    note "already built from $PIN, skipping"; return 0
  fi
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
  printf '%s\n' "$PIN" > "$INST/.wiki_pin"
  note "$("$BIN/postgres" --version), built from $PIN"
}

# A suite that fails stops the run: nothing is measured on a server whose own
# regression tests did not pass.  Both the exit status and the result line
# must say so.
stage_check() {
  say "regression suites, 17"
  check_pin
  mkdir -p "$OUT"
  : > "$OUT/checks17.txt"
  local rc_core rc_pgst line_core line_pgst l d
  ( cd "$BUILD" && make check > check_core.log 2>&1 ); rc_core=$?
  line_core=$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_core.log" | tail -1)
  printf 'core=%s %s\n' "$rc_core" "$line_core" >> "$OUT/checks17.txt"
  ( cd "$BUILD" && make -C contrib/pgstattuple check > check_pgstattuple.log 2>&1 ); rc_pgst=$?
  line_pgst=$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_pgstattuple.log" | tail -1)
  printf 'pgstattuple=%s %s\n' "$rc_pgst" "$line_pgst" >> "$OUT/checks17.txt"
  for l in "$BUILD"/check_*.log; do [ -f "$l" ] && cp "$l" "$OUT/17_$(basename "$l")"; done
  for d in "$BUILD"/src/test/regress/regression.diffs "$BUILD"/contrib/pgstattuple/regression.diffs; do
    [ -f "$d" ] && cp "$d" "$OUT/diffs17_$(basename "$(dirname "$d")").txt"
  done
  cat "$OUT/checks17.txt" >&2
  case "$rc_core:$line_core" in
    "0:All "*) : ;;
    *) die "make check did not pass (${line_core:-no result line}); see $OUT/17_check_core.log" ;;
  esac
  case "$rc_pgst:$line_pgst" in
    "0:All "*) : ;;
    *) die "the pgstattuple check did not pass (${line_pgst:-no result line}); see $OUT/17_check_pgstattuple.log" ;;
  esac
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
  printf -- '-- wiki_rs_run_mark %s\n' "$(date -u +%FT%TZ)" >> "$OUT/server17.log"
  "$BIN/psql" -X -At -q -d postgres -c "SELECT 1" > /dev/null 2>&1 || die "cannot connect"
  "$BIN/psql" -X -At -q -d postgres -c \
    "SELECT count(*) FROM pg_database WHERE datname = '$DB'" | grep -q '^1$' \
    || "$BIN/createdb" "$DB" || die "createdb failed"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null || die "pgstattuple not installed"
  {
    printf 'uname=%s\n' "$(uname -sm)"
    printf 'pin=%s\n' "$(cat "$INST/.wiki_pin" 2>/dev/null)"
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
# Six texts come out of the page:
#   report.sql   the filed heuristic, byte for byte, hash-checked
#   view.sql     the same text as a view over the internal `final` stage, with
#                one edit, printed: the two SET lines dropped.  The filed text
#                prefilters nothing, so the view's population is the report's
#   harness.sql, gate.sql, suite.sql, drain.sql, census.sql
#                the shared mandatory suite, all hash-checked
gen_view() {                       # gen_view <view> < text
  local view=$1 line tail=0
  printf 'DROP VIEW IF EXISTS %s CASCADE;\nCREATE VIEW %s AS\n' "$view" "$view"
  # The presentation SELECT is the one line of the filed text that starts with
  # SELECT at column 0; every SELECT inside the CTE chain is indented.
  while IFS= read -r line; do
    case $line in
      "SET "*)
        printf '   harness edit: dropped %s\n' "$line" >&2; continue ;;
      "SELECT"*) tail=1; continue ;;
    esac
    [ "$tail" = 1 ] && continue
    printf '%s\n' "$line"
  done
  printf 'SELECT f.* FROM final f;\n'
}

stage_texts() {
  say "extract the heuristic and the shared suite from $PAGE"
  mkdir -p "$SQLD" "$OUT"
  [ -f "$PAGE" ] || die "no page at $PAGE; set PAGE or run from the repository root"
  block 1 "$BASE_SQL"     "$SQLD/report.sql"  "filed heuristic"
  block 2 "$BASE_HARNESS" "$SQLD/harness.sql" "suite harness"
  block 3 "$BASE_GATE"    "$SQLD/gate.sql"    "family 1 fixtures"
  block 4 "$BASE_SUITE"   "$SQLD/suite.sql"   "families 2-6 fixtures"
  block 5 "$BASE_DRAIN"   "$SQLD/drain.sql"   "rule 2 drain"
  block 6 "$BASE_CENSUS"  "$SQLD/census.sql"  "rule 3 census and forgeries"
  gen_view score_final < "$SQLD/report.sql" > "$SQLD/view.sql"
  grep -v '^SET ' "$SQLD/report.sql" > "$SQLD/bare.sql"
}

# ------------------------------------------------------------- fixtures -----
# Schema rs: the guard fixtures, which the shared suite does not cover and this
# page still measures.  Every statement is DISPOSABLE - it drops and rebuilds a
# whole schema and writes indisvalid = false into pg_index by hand - and is not
# meant for a database anyone cares about.  The three session GUCs it sets are
# PGC_USERSET: session scope, no reload and no restart.
stage_fixtures() {
  say "guard fixtures in schema rs (rows=$ROWS)"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null
  cat > "$SQLD/fixtures.sql" <<'SQL'
-- DISPOSABLE guard fixtures for the REINDEX_SCORE heuristic.
-- Every object lives in schema rs of a throwaway database.
SET statement_timeout = '30min';   -- PGC_USERSET, session scope
SET lock_timeout      = '30s';     -- PGC_USERSET, session scope
SET client_min_messages = warning; -- PGC_USERSET, session scope

-- The guard oracle's results go with the fixtures they measured: guard_res
-- exists only between a guard stage and the next build of schema rs, which is
-- how the guard stage knows not to rebuild these fixtures a second time.
DROP TABLE IF EXISTS public.guard_res;
DROP SCHEMA IF EXISTS rs CASCADE;
CREATE SCHEMA rs;

-- 1. fresh builds at four fillfactors: what a rebuild leaves, measured, and
--    therefore what the score of a just-rebuilt index is.
CREATE TABLE rs.t_fresh (id int);
INSERT INTO rs.t_fresh SELECT g FROM generate_series(1, :rows) g;
CREATE INDEX i_fresh ON rs.t_fresh (id);
CREATE INDEX i_ff100 ON rs.t_fresh (id) WITH (fillfactor = 100);
CREATE INDEX i_ff50  ON rs.t_fresh (id) WITH (fillfactor = 50);
CREATE INDEX i_ff10  ON rs.t_fresh (id) WITH (fillfactor = 10);

-- 2. the empty index: pgstatindex reports NaN for avg_leaf_density when there
--    are no leaf pages at all, which is the input both CASE guards exist for.
CREATE TABLE rs.t_empty (id int PRIMARY KEY);
CREATE INDEX i_empty ON rs.t_empty (id);

-- 3. a two-page index: one metapage and one leaf page holding a single entry,
--    the smallest non-empty shape, and the one where the metapage in
--    total_pages decides the verdict.
CREATE TABLE rs.t_one (id int);
INSERT INTO rs.t_one VALUES (1);
CREATE INDEX i_one ON rs.t_one (id);

-- 4. sparse leaves: nine tenths of the rows deleted and vacuumed, so the
--    entries that remain are spread over every leaf page.
CREATE TABLE rs.t_sparse (id int);
INSERT INTO rs.t_sparse SELECT g FROM generate_series(1, :rows) g;
CREATE INDEX i_sparse ON rs.t_sparse (id);
DELETE FROM rs.t_sparse WHERE id % 10 <> 0;
VACUUM rs.t_sparse;

-- 5. deleted pages: a contiguous head of the key range deleted, so whole leaf
--    pages empty out and _bt_pagedel marks them deleted.
CREATE TABLE rs.t_head (id int);
INSERT INTO rs.t_head SELECT g FROM generate_series(1, :rows) g;
CREATE INDEX i_head ON rs.t_head (id);
DELETE FROM rs.t_head WHERE id <= (:rows * 9) / 10;
VACUUM rs.t_head;

-- 6. duplicates: a key with 100 rows per value, dense and untouched.  The
--    file a server that deduplicates writes is about a third of the one a
--    server that does not writes, so this fixture prices the build rather than
--    the rebuild; on both majors the score reads 0 and a rebuild of a file
--    already written that way returns nothing.
CREATE TABLE rs.t_dup (k int);
INSERT INTO rs.t_dup SELECT g % (:rows / 100) FROM generate_series(1, :rows) g;
CREATE INDEX i_dup ON rs.t_dup (k);

-- 6b. every entry removed: the emptiest shape a live B-tree reaches.  nbtree
--     never deletes the rightmost page of a level, so this index keeps its
--     rightmost leaf, and the internal pages above it, however much is
--     vacuumed out of it, and avg_leaf_density stays a number rather than
--     becoming NaN.  The facts stage prints the shape it reached.  This is the
--     fixture behind the page's claim that leaf_pages = 0 means a metapage and
--     nothing else: an emptied index does not reach that state, and only a
--     rebuilt or never-filled one does.
CREATE TABLE rs.t_alldel (id int);
INSERT INTO rs.t_alldel SELECT g FROM generate_series(1, :rows) g;
CREATE INDEX i_alldel ON rs.t_alldel (id);
DELETE FROM rs.t_alldel;
VACUUM rs.t_alldel;
VACUUM rs.t_alldel;

-- 7. the shapes pgstatindex refuses, and the ones the candidate filter drops.
CREATE TABLE rs.t_other (id int, txt text, arr int[], pt point);
INSERT INTO rs.t_other
SELECT g, g::text, ARRAY[g], point(g, g) FROM generate_series(1, 1000) g;
CREATE INDEX i_hash  ON rs.t_other USING hash (id);
CREATE INDEX i_gin   ON rs.t_other USING gin (arr);
CREATE INDEX i_gist  ON rs.t_other USING gist (pt);   -- gist over int needs btree_gist
CREATE INDEX i_brin  ON rs.t_other USING brin (id);
CREATE VIEW  rs.v_other AS SELECT * FROM rs.t_other;
CREATE SEQUENCE rs.s_other;
CREATE MATERIALIZED VIEW rs.m_other AS SELECT * FROM rs.t_other;
CREATE INDEX i_matview ON rs.m_other (id);

-- a partitioned index has relkind 'I' and no storage of its own
CREATE TABLE rs.t_part (id int) PARTITION BY RANGE (id);
CREATE TABLE rs.t_part_1 PARTITION OF rs.t_part FOR VALUES FROM (1) TO (1000);
CREATE INDEX i_part ON rs.t_part (id);

-- an index the catalog says is not valid: 17's pgstatindex refuses it, and the
-- facts stage records what the server under test does with it
CREATE TABLE rs.t_invalid (id int);
INSERT INTO rs.t_invalid SELECT g FROM generate_series(1, 1000) g;
CREATE INDEX i_invalid ON rs.t_invalid (id);
UPDATE pg_index SET indisvalid = false
 WHERE indexrelid = 'rs.i_invalid'::regclass;

ANALYZE rs.t_fresh, rs.t_empty, rs.t_one, rs.t_sparse, rs.t_head, rs.t_dup,
        rs.t_alldel, rs.t_other, rs.t_invalid;
SQL
  PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" \
    -v rows="$ROWS" -f "$SQLD/fixtures.sql" > "$OUT/fixtures17.log" 2>&1 \
    || { tail -10 "$OUT/fixtures17.log" >&2; die "guard fixtures failed"; }
  note "guard indexes: $(s "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'rs' AND c.relkind IN ('i','I')")"
}

# ---------------------------------------------------------------- suite -----
stage_suite() {
  say "the shared mandatory suite, build and baseline phases"
  [ -f "$SQLD/suite.sql" ] || die "run the texts stage first"
  # CREATE SCHEMA public grants nothing to PUBLIC, so initdb's USAGE grant is
  # restored here.
  q "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;
     GRANT USAGE ON SCHEMA public TO PUBLIC;" > /dev/null \
    || die "schema reset failed"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null || die "pgstattuple not installed"
  # The no-defeat rule's window opens at the first churn statement, which is in
  # the fixture file below; this mark is where the skip-line check starts
  # reading, so a re-run of this stage does not inherit an earlier run's lines.
  printf -- '-- wiki_rs_maint_mark %s\n' "$(date -u +%FT%TZ)" >> "$OUT/server17.log"
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
  t "SELECT /* wiki_rs_suite_skips */ num, leg, idx, reason FROM skipped
      ORDER BY num, leg" > "$OUT/skipped17.txt" 2>&1
  t "SELECT /* wiki_rs_suite_families */ grp, count(*) AS fixtures,
            count(*) FILTER (WHERE want_stage = 'rebuild') AS want_rebuild
       FROM plan GROUP BY grp ORDER BY grp" >> "$OUT/skipped17.txt" 2>&1
  cat "$OUT/skipped17.txt" >&2
}

# ---------------------------------------------------------------- churn -----
stage_churn() {
  say "churn: rule 2 drain with its maintenance step, rule 3 census, forgeries last, churned snapshot"
  [ -n "$(s 'SELECT 1 FROM plan LIMIT 1')" ] || die "no plan rows; run the suite stage first"
  fl "$SQLD/drain.sql" > "$OUT/drain17.txt" 2> "$OUT/drain_verbose17.log" \
    || { tail -5 "$OUT/drain17.txt" >&2; tail -5 "$OUT/drain_verbose17.log" >&2
         die "drain failed"; }
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
  t "SELECT /* wiki_rs_skips_after_census */ num, leg, idx, reason FROM skipped
      ORDER BY num, leg" > "$OUT/skipped17.txt" 2>&1
  t "SELECT /* wiki_rs_families_after_census */ grp, count(*) AS fixtures,
            count(*) FILTER (WHERE want_stage = 'rebuild') AS want_rebuild
       FROM plan GROUP BY grp ORDER BY grp" >> "$OUT/skipped17.txt" 2>&1
  note "$(s "SELECT count(*) || ' fixtures scored after the census, ' ||
              (SELECT count(*) FROM skipped) || ' skipped' FROM plan")"
}

# --------------------------------------------------------------- report -----
# Phase 4, the decide phase, part one: the filed text exactly as filed, both
# SET lines included.  Its own output is what a reader sees, so the rows it
# prints are loaded back as report_filed and are what `reported` means.
stage_report() {
  say "run the filed heuristic"
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
  local rows cols
  rows=$(grep -c '^' "$OUT/report17.txt"); rows=$((rows - 1))
  cols=$(head -1 "$OUT/report17.txt" | tr '|' '\n' | grep -c '^')
  {
    printf 'report_rows=%s\n' "$rows"
    printf 'report_columns=%s\n' "$cols"
    printf 'report_bytes=%s\n' "$(wc -c < "$OUT/report17.txt")"
    printf 'report_signalled=%s\n' "$(cut -d'|' -f13 "$OUT/report17.txt" | grep -c '^t$')"
  } >> "$OUT/exact17.txt"
  cat "$OUT/exact17.txt" >&2
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" \
    -f "$SQLD/report.sql" > "$OUT/report17_pretty.txt" 2>&1
  # Load the printed rows back.  Fields 2, 12 and 13 are index_name,
  # reindex_score_pct and reindex_signal; no field of this report can contain a
  # pipe.  A NaN percentage is quoted, because that is how numeric NaN is
  # written as a literal.
  q "DROP TABLE IF EXISTS report_filed;
     CREATE /* wiki_rs_report_filed */ TABLE report_filed(index_name text PRIMARY KEY, reindex_score_pct numeric, reindex_signal bool);" \
    > /dev/null || die "report_filed failed"
  : > "$SQLD/report_rows.sql"
  local name pct sig
  while IFS='|' read -r _ name _ _ _ _ _ _ _ _ _ pct sig; do
    [ -n "${name:-}" ] || continue
    case ${pct:-} in NaN) pct="'NaN'" ;; '') pct=NULL ;; esac
    case ${sig:-} in t) sig=true ;; f) sig=false ;; *) sig=NULL ;; esac
    printf "INSERT INTO report_filed VALUES ('%s', %s, %s);\n" \
      "${name//\'/\'\'}" "$pct" "$sig" >> "$SQLD/report_rows.sql"
  done < <(tail -n +2 "$OUT/report17.txt")
  fl "$SQLD/report_rows.sql" > /dev/null || die "loading report_filed failed"
  note "report_filed rows: $(s 'SELECT count(*) FROM report_filed')"
}

# --------------------------------------------------------------- decide -----
stage_decide() {
  say "materialize the heuristic's reading of every index"
  fl "$SQLD/view.sql" > /dev/null || die "harness view failed"
  q "DROP TABLE IF EXISTS decide;
     CREATE TABLE decide AS SELECT /* wiki_rs_decide */ * FROM score_final;" \
    > /dev/null || die "decide failed"
  q "CREATE /* wiki_rs_decide_idx */ INDEX decide_idx ON decide (index_name);" > /dev/null
  {
    printf 'decide_rows=%s\n' "$(s 'SELECT count(*) FROM decide')"
    printf 'decide_fixtures=%s\n' "$(s 'SELECT count(*) FROM decide d JOIN plan p ON p.idx = d.index_name')"
    printf 'filed_rows=%s\n' "$(s 'SELECT count(*) FROM report_filed')"
    # The view differs from the filed text in its presentation SELECT only, but
    # the two are not two readings of one state: the report ran first, the view
    # ran second, and between them this stage created its own tables, so the
    # catalog and TOAST indexes of the fixture database have moved.  The
    # fixtures have not, which is why the fixture rows are the comparison that
    # must come out at zero and the whole-population count is printed beside it
    # as context rather than as a check.  IS DISTINCT FROM, so that a row
    # missing on one side counts as a difference.
    printf 'view_disagrees_with_filed_fixtures=%s\n' \
      "$(s "SELECT count(*) FROM plan p
              JOIN report_filed r ON r.index_name = p.idx
              JOIN decide d       ON d.index_name = p.idx
             WHERE round(100 * d.reindex_score::numeric, 1) IS DISTINCT FROM r.reindex_score_pct")"
    printf 'view_disagrees_with_filed_all=%s (catalog drift between the two reads)\n' \
      "$(s "SELECT count(*) FROM report_filed r JOIN decide d ON d.index_name = r.index_name
             WHERE round(100 * d.reindex_score::numeric, 1) IS DISTINCT FROM r.reindex_score_pct")"
    printf 'signal_disagrees_with_filed=%s\n' \
      "$(s "SELECT count(*) FROM report_filed r JOIN decide d ON d.index_name = r.index_name
             WHERE (d.reindex_score >= 0.5) IS DISTINCT FROM r.reindex_signal")"
    printf 'view_rows_the_report_did_not_print=%s\n' \
      "$(s "SELECT count(*) FROM decide d WHERE NOT EXISTS
             (SELECT 1 FROM report_filed r WHERE r.index_name = d.index_name)")"
    printf 'fixtures_printed=%s of %s\n' \
      "$(s "SELECT count(*) FROM plan p JOIN report_filed r ON r.index_name = p.idx")" \
      "$(s 'SELECT count(*) FROM plan')"
    printf 'nan_scores=%s\n' \
      "$(s "SELECT count(*) FROM decide WHERE reindex_score = 'NaN'::float8")"
    printf 'nan_scores_signalled=%s\n' \
      "$(s "SELECT count(*) FROM decide WHERE reindex_score = 'NaN'::float8
              AND reindex_score >= 0.5")"
    # The whole-cluster before-and-after, both halves from this run.  "before"
    # is the same statement with the two CASE guards removed, recomputed here
    # from the columns the statement itself kept, so the page's before column
    # is not a quotation from an earlier run.  u.nan is the unguarded score.
    printf -- '-- the guards, over every candidate: unguarded (before) beside filed (after)\n'
    t "SELECT /* wiki_rs_guard_effect */
              count(*)                                              AS rows_printed,
              count(*) FILTER (WHERE u.nan >= 0.5)                  AS signalled_before,
              count(*) FILTER (WHERE d.reindex_score >= 0.5)        AS signalled_after,
              count(*) FILTER (WHERE u.nan = 'NaN'::float8)         AS nan_before,
              count(*) FILTER (WHERE d.reindex_score = 'NaN'::float8) AS nan_after,
              count(*) FILTER (WHERE d.total_pages = 1)             AS metapage_only,
              count(*) FILTER (WHERE d.total_pages = 1
                                 AND u.nan >= 0.5)                  AS metapage_only_before,
              count(*) FILTER (WHERE d.total_pages = 1
                                 AND d.reindex_score >= 0.5)        AS metapage_only_after,
              count(*) FILTER (WHERE (u.nan >= 0.5)
                                  <> (d.reindex_score >= 0.5))      AS verdicts_the_guards_moved,
              count(*) FILTER (WHERE u.nan <> 'NaN'::float8
                                 AND round(u.nan::numeric, 6)
                                     <> round(d.reindex_score::numeric, 6)) AS finite_scores_that_differ
         FROM decide d
         CROSS JOIN LATERAL (
              SELECT (d.deleted_pages + d.empty_pages
                      + d.leaf_pages * GREATEST(0::float8,
                                                1 - d.avg_leaf_density / d.fillfactor))
                     / d.total_pages::float8 AS nan) u"
    # leaf_pages = 0 and total_pages = 1 must be the same set of rows: that is
    # the claim that a NaN density means a metapage and nothing else.
    printf -- '-- leaf_pages = 0 against total_pages = 1, and what those rows hold\n'
    t "SELECT /* wiki_rs_metapage_only */
              count(*) FILTER (WHERE leaf_pages = 0)                AS no_leaf,
              count(*) FILTER (WHERE total_pages = 1)               AS one_page,
              count(*) FILTER (WHERE (leaf_pages = 0) <> (total_pages = 1))
                                                                    AS the_two_disagree,
              count(*) FILTER (WHERE leaf_pages = 0
                                 AND deleted_pages + empty_pages > 0)
                                                                    AS no_leaf_but_dead_pages,
              count(*) FILTER (WHERE avg_leaf_density = 'NaN'::float8
                                 AND leaf_pages > 0)                AS nan_with_leaves
         FROM decide"
  } > "$OUT/decide17.txt"
  cat "$OUT/decide17.txt" >&2
}

# ---------------------------------------------------------------- facts -----
# The version-local and heuristic-local facts, none of them destructive, all of
# them taken before the oracle rebuilds anything.
stage_facts() {
  say "the heuristic's own edges: NaN, the metapage, the fillfactor, the refusals"
  {
    printf -- '-- NaN, as the engine compares it\n'
  } > "$OUT/facts17.txt"
  # The three readings every major answers.  They are in one statement because
  # they are one claim: a NaN score is not filtered out by >= 0.5, it passes it.
  t "SELECT /* wiki_rs_nan */ 'NaN'::float8 >= 0.5 AS nan_ge_half,
            greatest(0::float8, 'NaN'::float8)   AS greatest_zero_nan,
            0::bigint * 'NaN'::float8            AS zero_times_nan" \
    >> "$OUT/facts17.txt" 2>&1
  # This one is version-local and is read on its own, because a major that
  # raises here would otherwise take the three readings above down with it.
  printf -- '-- NaN over zero, the no-metapage denominator of an empty index\n' >> "$OUT/facts17.txt"
  printf 'nan_over_zero  %s\n' "$(val_or_err "SELECT 'NaN'::float8 / 0::float8")" >> "$OUT/facts17.txt"
  printf -- '-- and the same denominator under a guarded numerator\n' >> "$OUT/facts17.txt"
  printf 'zero_over_zero %s\n' "$(val_or_err "SELECT 0::float8 / 0::float8")" >> "$OUT/facts17.txt"
  printf -- '-- the score of every guard fixture, before any rebuild\n' >> "$OUT/facts17.txt"
  t "SELECT /* wiki_rs_guard_scores */ d.index_name, d.total_pages, d.internal_pages,
            d.leaf_pages, d.empty_pages, d.deleted_pages,
            round(d.avg_leaf_density::numeric, 2) AS density, d.fillfactor,
            round(100 * d.reindex_score::numeric, 1) AS score_pct,
            d.reindex_score >= 0.5 AS signal
       FROM decide d
      WHERE d.schema_name = 'rs'
      ORDER BY d.index_name" >> "$OUT/facts17.txt" 2>&1
  printf -- '-- the whole database, as the heuristic sees it\n' >> "$OUT/facts17.txt"
  t "SELECT /* wiki_rs_population */ count(*) AS indexes,
            count(*) FILTER (WHERE reindex_score = 'NaN'::float8) AS nan_score,
            count(*) FILTER (WHERE reindex_score >= 0.5) AS signalled,
            count(*) FILTER (WHERE reindex_score >= 0.5
                               AND reindex_score <> 'NaN'::float8) AS signalled_not_nan,
            count(*) FILTER (WHERE total_pages = 1) AS one_page,
            count(*) FILTER (WHERE total_pages = 2) AS two_page,
            max(reindex_score) FILTER (WHERE reindex_score <> 'NaN'::float8) AS max_finite_score
       FROM decide" >> "$OUT/facts17.txt" 2>&1
  # The metapage-only files are where a NaN density comes from.  The guards
  # leave no NaN score to count, so the files are counted instead, by schema,
  # and the ones outside the system schemas - objects this run created - are
  # named.
  printf -- '-- the metapage-only files, by schema\n' >> "$OUT/facts17.txt"
  t "SELECT /* wiki_rs_metapage_by_schema */ schema_name, count(*) AS indexes,
            count(*) FILTER (WHERE total_pages = 1)      AS metapage_only,
            count(*) FILTER (WHERE reindex_score >= 0.5) AS signalled
       FROM decide GROUP BY schema_name ORDER BY schema_name" >> "$OUT/facts17.txt" 2>&1
  printf -- '-- the metapage-only files outside pg_catalog and pg_toast\n' >> "$OUT/facts17.txt"
  t "SELECT /* wiki_rs_metapage_own */ schema_name, index_name, table_name
       FROM decide
      WHERE total_pages = 1 AND schema_name NOT IN ('pg_catalog', 'pg_toast')
      ORDER BY schema_name, index_name" >> "$OUT/facts17.txt" 2>&1
  # The filed denominator against the file itself.  pgstatindex builds
  # index_size from the four page classes plus the metapage, and its scan
  # covers every block of the relation, so index_size / block_size must equal
  # the page count pg_relation_size reports - which is the file a REINDEX
  # shrinks, and therefore the denominator the oracle measures against.
  printf -- '-- total_pages against the file: index_size / block_size vs pg_relation_size\n' >> "$OUT/facts17.txt"
  t "SELECT /* wiki_rs_denominator */ count(*) AS rows_read,
            count(*) FILTER (WHERE d.total_pages
                                   <> pg_relation_size(d.idx_oid)
                                      / current_setting('block_size')::bigint)
                AS total_pages_differs_from_the_file,
            count(*) FILTER (WHERE d.total_pages
                                   <> 1 + d.internal_pages + d.leaf_pages
                                        + d.empty_pages + d.deleted_pages)
                AS total_pages_differs_from_the_classes_plus_one
       FROM decide d" >> "$OUT/facts17.txt" 2>&1
  printf -- '-- the ceiling: (total_pages - 1 - internal_pages) / total_pages\n' >> "$OUT/facts17.txt"
  t "SELECT /* wiki_rs_ceiling */ count(*) AS finite_rows,
            count(*) FILTER (WHERE reindex_score
                                   > (total_pages - 1 - internal_pages)::float8
                                     / total_pages) AS above_ceiling,
            count(*) FILTER (WHERE total_pages <= 2 AND reindex_score >= 0.5)
                AS small_and_signalled
       FROM decide WHERE reindex_score <> 'NaN'::float8" >> "$OUT/facts17.txt" 2>&1
  printf -- '-- what pgstatindex refuses, one line per shape\n' >> "$OUT/facts17.txt"
  local shape
  for shape in "rs.i_hash" "rs.i_gin" "rs.i_gist" "rs.i_brin" "rs.i_part" \
               "rs.i_invalid" "rs.t_other" "rs.v_other" "rs.s_other" "rs.m_other"; do
    printf '%-14s %s\n' "$shape" "$(err "SELECT * FROM pgstatindex('$shape')")" \
      >> "$OUT/facts17.txt"
  done
  printf -- '-- and how many of them the candidate filter drops before the call\n' >> "$OUT/facts17.txt"
  t "SELECT /* wiki_rs_filtered */
            (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'rs' AND c.relkind IN ('i','I'))         AS rs_indexes,
            (SELECT count(*) FROM decide WHERE schema_name = 'rs')       AS rs_scored" \
    >> "$OUT/facts17.txt" 2>&1
  printf -- '-- the fillfactor the heuristic reads, against the one the index was built at\n' >> "$OUT/facts17.txt"
  t "SELECT /* wiki_rs_fillfactor */ d.index_name, d.fillfactor AS read_by_the_score,
            coalesce((SELECT o.option_value FROM pg_options_to_table(c.reloptions) o
                       WHERE o.option_name = 'fillfactor'), 'unset') AS reloption,
            round(d.avg_leaf_density::numeric, 2) AS density_as_built,
            round(100 * d.reindex_score::numeric, 2) AS score_pct
       FROM decide d JOIN pg_class c ON c.relname = d.index_name
      WHERE d.index_name IN ('i_fresh','i_ff100','i_ff50','i_ff10')
      ORDER BY d.fillfactor" >> "$OUT/facts17.txt" 2>&1
  cat "$OUT/facts17.txt" >&2
}

# ----------------------------------------------------------------- cost -----
# What it costs to ask.  pgstatindex reads every page of every index it is
# called on, so an automatic signal pays for the whole B-tree population each
# time it runs.  Three end-to-end runs, then one EXPLAIN (ANALYZE, BUFFERS).
# Not destructive, and it must precede the oracle like facts does.
stage_cost() {
  say "what the heuristic costs to run"
  {
    printf -- '-- the population it reads\n'
    t "SELECT /* wiki_rs_population_size */ count(*) AS btree_indexes,
              pg_size_pretty(sum(pg_relation_size(idx_oid))) AS total_index_bytes,
              sum(total_pages) AS total_pages
         FROM decide"
    printf -- '-- three end-to-end runs of the filed text, as filed\n'
    local i t0 t1
    for i in 1 2 3; do
      t0=$(date +%s%N)
      PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off \
        -d "$DB" -f "$SQLD/report.sql" > /dev/null 2>&1
      t1=$(date +%s%N)
      printf 'run_%s_ms=%s\n' "$i" "$(( (t1 - t0) / 1000000 ))"
    done
    printf -- '-- EXPLAIN (ANALYZE, BUFFERS) of the same text without its SET lines\n'
    PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" \
      -c "EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF) $(cat "$SQLD/bare.sql")" \
      2>&1 | grep -E 'Buffers|Execution Time|Planning Time|rows='
  } > "$OUT/cost17.txt" 2>&1
  cat "$OUT/cost17.txt" >&2
}

# ----------------------------------------------------------------- priv -----
# Who can run it.  pgstattuple 1.5 revokes EXECUTE on its functions from
# PUBLIC, so an automatic signal needs a role that has been granted it, or
# membership in pg_stat_scan_tables.  Both roles are dropped again at the end.
stage_priv() {
  say "the privileges an automatic signal would need"
  q "DROP OWNED BY rs_plain, rs_scan;" > /dev/null 2>&1
  q "DROP ROLE IF EXISTS rs_plain; DROP ROLE IF EXISTS rs_scan;" > /dev/null 2>&1
  q "CREATE ROLE rs_plain LOGIN; CREATE ROLE rs_scan LOGIN;
     GRANT pg_stat_scan_tables TO rs_scan;
     GRANT USAGE ON SCHEMA rs TO rs_plain, rs_scan;" > /dev/null \
    || die "creating the probe roles failed"
  # Each overload is called by name: an unadorned string literal resolves to
  # the text overload, while the filed statement passes an oid::regclass and
  # so calls the regclass one.
  {
    printf -- '-- pgstatindex, called by a role with no grant and by a pg_stat_scan_tables member,\n'
    printf -- '-- through the regclass overload the filed statement calls and through the text one\n'
    local r o
    for r in rs_plain rs_scan; do
      for o in regclass text; do
        printf '%-9s %-9s %s\n' "$r" "$o" "$(PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -At -q -U "$r" \
          -d "$DB" -c "SELECT leaf_pages FROM pgstatindex('rs.i_fresh'::$o)" 2>&1 | head -1)"
      done
    done
    printf -- '-- the EXECUTE privileges pgstattuple ships with, per overload\n'
    t "SELECT /* wiki_rs_acl */ p.oid::regprocedure AS function, p.proacl
         FROM pg_proc p WHERE p.proname = 'pgstatindex' ORDER BY p.oid"
  } > "$OUT/priv17.txt" 2>&1
  # The schema grant is a dependency on the role, so it goes first: a bare
  # DROP ROLE would fail and leave both roles behind.
  q "DROP OWNED BY rs_plain, rs_scan;" > /dev/null || die "dropping the probe roles' grants failed"
  q "DROP ROLE rs_plain; DROP ROLE rs_scan;" > /dev/null || die "dropping the probe roles failed"
  cat "$OUT/priv17.txt" >&2
}

# ---------------------------------------------------------------- score -----
# Phase 5, the oracle: for every fixture in the plan, read what the heuristic
# said, call pgstatindex again from the harness, rebuild, and measure the file.
# Destructive: it rebuilds every scored index, so it runs once per build of the
# fixtures.  The suite stage installs res empty; a res that already holds rows
# means these fixtures were rebuilt, and scoring them again would measure a
# rebuild of a rebuild.  To score again, re-run every stage from suite onward.
stage_score() {
  say "the oracle: REINDEX INDEX on every scored fixture"
  [ -n "$(s 'SELECT 1 FROM decide LIMIT 1')" ] || die "no decide rows; run the decide stage first"
  [ "$(s 'SELECT count(*) FROM res')" = 0 ] \
    || die "the oracle has already rebuilt these fixtures; re-run the stages from suite onward to score again"
  q "CALL /* wiki_rs_score_all */ score_all();" > /dev/null || die "scoring failed"
  {
    t "SELECT /* wiki_rs_verdict_counts */ verdict, count(*) FROM verdicts
        GROUP BY verdict ORDER BY verdict"
    t "SELECT /* wiki_rs_verdict_by_family */ grp, count(*) AS fixtures,
              count(*) FILTER (WHERE verdict = 'PASS')                    AS pass,
              count(*) FILTER (WHERE verdict = 'CRITICAL FALSE POSITIVE') AS crit_fp,
              count(*) FILTER (WHERE verdict = 'FALSE POSITIVE')          AS fp,
              count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE')          AS fn
         FROM verdicts GROUP BY grp ORDER BY grp"
    t "SELECT /* wiki_rs_contract */
              count(*) FILTER (WHERE NOT contract_ok)            AS build_contract_failures,
              count(*) FILTER (WHERE NOT view_matches_report)    AS view_report_disagreements,
              count(*) FILTER (WHERE NOT signal_matches_report)  AS signal_disagreements,
              count(*) FILTER (WHERE taken_stage <> taken_nofilter) AS hidden_by_the_report,
              count(*) FILTER (WHERE taken_nofilter <> expected_stage) AS statement_vs_instrument,
              count(*) FILTER (WHERE shape_ok IS FALSE)          AS shape_failures,
              count(*) FILTER (WHERE want_stage <> taken_nofilter) AS want_stage_misses
         FROM verdicts"
    t "SELECT /* wiki_rs_want_misses */ num, idx, grp, want_stage, taken_nofilter,
              score_pct, actual, verdict
         FROM verdicts WHERE want_stage <> taken_nofilter ORDER BY num"
    # The concept page calls expected_stage mandatory, so the rows behind the
    # count are printed rather than left as a number: a statement that
    # disagrees with its own instrument has to be readable fixture by fixture.
    t "SELECT /* wiki_rs_instrument_misses */ num, idx, grp, score_pct,
              expected_stage, taken_nofilter, density, leaf_pages, dead_pages,
              total_pages
         FROM verdicts WHERE taken_nofilter <> expected_stage ORDER BY num"
    t "SELECT /* wiki_rs_bad_verdicts */ num, idx, grp, score_pct, actual, err,
              density, leaf_pages, dead_pages, total_pages, verdict
         FROM verdicts WHERE verdict <> 'PASS' ORDER BY verdict, num"
    t "SELECT /* wiki_rs_all_verdicts */ num, idx, grp, blocks_built, blocks_before,
              blocks_after, score_pct, actual, err, verdict, want_stage, shape
         FROM verdicts ORDER BY num, leg"
  } > "$OUT/verdicts17.txt" 2>&1
  head -30 "$OUT/verdicts17.txt" >&2
}

# ------------------------------------------------------------- accuracy -----
# The question this page asks: how close is REINDEX_SCORE to what a rebuild
# really gives back, and is >= 50 % the right place to cut?
stage_accuracy() {
  say "accuracy: the score against the measured rebuild"
  [ -n "$(s 'SELECT 1 FROM res LIMIT 1')" ] || die "no res rows; run the score stage first"
  {
    printf -- '-- the error of the score against the measured rebuild, in points\n'
    t "SELECT /* wiki_rs_error */ count(*) AS fixtures,
              round(avg(abs(err)), 2)                        AS mean_abs_err,
              round(percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(err))::numeric, 2)
                                                             AS median_abs_err,
              round(max(err), 1)                             AS worst_over,
              round(min(err), 1)                             AS worst_under,
              count(*) FILTER (WHERE abs(err) <= 1)          AS within_1_point,
              count(*) FILTER (WHERE abs(err) <= 5)          AS within_5_points,
              count(*) FILTER (WHERE abs(err) <= 10)         AS within_10_points,
              round(corr(score_pct::float8, actual::float8)::numeric, 4) AS correlation
         FROM verdicts WHERE score_pct IS NOT NULL AND score_pct <> 'NaN'::numeric"
    printf -- '-- the same, by family\n'
    t "SELECT /* wiki_rs_error_by_family */ grp, count(*) AS fixtures,
              round(avg(abs(err)), 2) AS mean_abs_err,
              round(max(err), 1) AS worst_over, round(min(err), 1) AS worst_under
         FROM verdicts WHERE score_pct IS NOT NULL AND score_pct <> 'NaN'::numeric
        GROUP BY grp ORDER BY grp"
    printf -- '-- the confusion matrix at the filed threshold of 50 %%\n'
    t "SELECT /* wiki_rs_confusion */
              count(*) FILTER (WHERE taken_nofilter = 'rebuild' AND actual >= 50) AS true_positive,
              count(*) FILTER (WHERE taken_nofilter = 'rebuild' AND actual <  50) AS false_positive_band,
              count(*) FILTER (WHERE taken_nofilter = 'leave'   AND actual <  50) AS true_negative,
              count(*) FILTER (WHERE taken_nofilter = 'leave'   AND actual >= 50) AS false_negative,
              count(*) AS fixtures
         FROM verdicts"
    printf -- '-- every fixture the signal and the oracle disagree about\n'
    t "SELECT /* wiki_rs_disagreements */ num, idx, grp, score_pct, actual, err,
              density, leaf_pages, dead_pages, total_pages, verdict
         FROM verdicts
        WHERE (taken_nofilter = 'rebuild') <> (actual >= 50)
        ORDER BY abs(err) DESC"
    # The sweep, scored two ways, because they answer different questions.
    # band_violations is the shared suite's own test: a threshold is acceptable
    # when no fixture lands in a false-positive or false-negative band, and
    # every threshold with a zero there is equally acceptable to the suite.
    # agrees_with_50 instead asks how often the signal matches a 50 % cut on
    # the measured rebuild, which is this page's own construct, not a band -
    # and because the score tracks the actual closely it necessarily peaks at
    # 50, so it measures calibration and may not be read as choosing 50.
    printf -- '-- what a different threshold would have cost, over the same fixtures\n'
    t "SELECT /* wiki_rs_sweep */ th AS threshold_pct,
              count(*) FILTER (WHERE score_pct >= th AND actual < 10) AS critical_false_pos,
              count(*) FILTER (WHERE score_pct >= th AND actual < 35) AS false_pos,
              count(*) FILTER (WHERE score_pct <  th AND actual >= 50) AS false_neg,
              count(*) FILTER (WHERE score_pct >= th AND actual < 35)
              + count(*) FILTER (WHERE score_pct < th AND actual >= 50)
                                                                      AS band_violations,
              count(*) FILTER (WHERE score_pct >= th) AS rebuilt,
              count(*) FILTER (WHERE (score_pct >= th) = (actual >= 50)) AS agrees_with_50
         FROM verdicts, generate_series(5, 95, 5) th
        GROUP BY th ORDER BY th"
    # Where the fixtures actually sit.  A threshold is band-clean when it is
    # above the score of every fixture whose rebuild returned under 35 % and at
    # or below the score of every fixture whose rebuild returned 50 % or more,
    # so the band-clean range is bounded by two scores, not by the gap between
    # the measured rebuilds: both edges, and the fixtures behind every
    # violation in the sweep, are printed after the histogram.
    printf -- '-- the measured rebuilds, bucketed, and the gap around the cut\n'
    t "SELECT /* wiki_rs_actual_histogram */ width_bucket(actual, 0, 100, 10) * 10 - 10
                AS actual_from_pct,
              count(*) AS fixtures, round(min(actual), 1) AS lowest,
              round(max(actual), 1) AS highest
         FROM verdicts GROUP BY 1 ORDER BY 1"
    t "SELECT /* wiki_rs_band_gap */
              round(max(actual) FILTER (WHERE actual < 50), 1)  AS highest_below_50,
              round(min(actual) FILTER (WHERE actual >= 50), 1) AS lowest_at_or_above_50,
              count(*) FILTER (WHERE actual >= 35 AND actual < 50) AS between_35_and_50,
              count(*) FILTER (WHERE actual >= 50 AND actual < 70) AS between_50_and_70
         FROM verdicts"
    printf -- '-- the two scores that bound the band-clean range, and the fixtures that hold them\n'
    t "SELECT /* wiki_rs_band_edges */ e.edge, v.idx, v.total_pages, v.score_pct,
              v.actual, v.err
         FROM (SELECT 'highest score, rebuild under 35 %' AS edge,
                      max(score_pct) AS score, false AS at_or_above
                 FROM verdicts WHERE actual < 35
               UNION ALL
               SELECT 'lowest score, rebuild 50 % or more',
                      min(score_pct), true
                 FROM verdicts WHERE actual >= 50) e
         JOIN verdicts v ON v.score_pct = e.score
                        AND (v.actual >= 50) = e.at_or_above
                        AND (e.at_or_above OR v.actual < 35)
        ORDER BY e.edge, v.idx"
    printf -- '-- the fixtures behind every band violation in the sweep, up to 80 %%\n'
    t "SELECT /* wiki_rs_sweep_rows */ th AS threshold_pct,
              CASE WHEN score_pct >= th AND actual < 10 THEN 'critical false positive'
                   WHEN score_pct >= th AND actual < 35 THEN 'false positive'
                   ELSE 'false negative' END AS band,
              count(*) AS fixtures,
              string_agg(idx || ' ' || score_pct || '/' || actual, ', ' ORDER BY idx)
                AS score_over_actual
         FROM verdicts, generate_series(5, 80, 5) th
        WHERE (score_pct >= th AND actual < 35) OR (score_pct < th AND actual >= 50)
        GROUP BY 1, 2 ORDER BY 1, 2"
    printf -- '-- the two denominators and the unguarded statement, side by side\n'
    t "SELECT /* wiki_rs_variants */
              count(*) AS fixtures,
              count(*) FILTER (WHERE verdict = 'PASS')       AS filed_pass,
              count(*) FILTER (WHERE verdict_nan = 'PASS')   AS unguarded_pass,
              count(*) FILTER (WHERE score_pct  >= 50)       AS filed_rebuilds,
              count(*) FILTER (WHERE nan_signal)             AS unguarded_rebuilds,
              count(*) FILTER (WHERE nan_pct = 'NaN'::numeric) AS unguarded_nan,
              count(*) FILTER (WHERE nometa_pct >= 50)       AS nometa_rebuilds,
              count(*) FILTER (WHERE nometa_pct IS NULL)     AS nometa_undefined,
              round(max(nometa_pct - score_pct), 2)          AS worst_nometa_gap
         FROM verdicts"
    printf -- '-- the fixtures where the three readings do not agree\n'
    t "SELECT /* wiki_rs_variant_rows */ num, idx, total_pages, leaf_pages,
              score_pct, nometa_pct, nan_pct, actual
         FROM verdicts
        WHERE (score_pct >= 50) IS DISTINCT FROM (nometa_pct >= 50)
           OR (score_pct >= 50) IS DISTINCT FROM nan_signal
        ORDER BY num"
    # The error, split into the three terms it is made of.  The identity is
    # exact: err = leaf_term + internal_term + dead_term, so a fixture's error
    # is attributable rather than narrated.  leaf_term is what the leaf model
    # itself got wrong, which on a small index is mostly the whole page a
    # rebuild cannot avoid writing; where a rebuild writes back as many leaves
    # as it found, leaf_term is the score's own leaf component and cannot be
    # negative.  internal_term is the levels above the leaf level, which the
    # numerator never models, so its sign is whatever the rebuild did to them:
    # both directions are counted here, from the page counts, not assumed.
    printf -- '-- the error decomposed: leaf model, internal levels, dead pages left\n'
    t "SELECT /* wiki_rs_decomposition */ count(*) AS fixtures,
              round(avg(leaf_term), 2)     AS mean_leaf_term,
              round(avg(internal_term), 2) AS mean_internal_term,
              round(avg(dead_term), 2)     AS mean_dead_term,
              round(max(abs(err - (leaf_term + internal_term + dead_term))), 1)
                                           AS worst_residual,
              count(*) FILTER (WHERE aft_internal < internal_pages) AS shrank_internal_levels,
              count(*) FILTER (WHERE aft_internal > internal_pages) AS grew_internal_levels,
              count(*) FILTER (WHERE aft_leaf > leaf_pages)         AS grew_leaf_levels,
              count(*) FILTER (WHERE dead_term <> 0)    AS kept_dead_pages
         FROM verdicts"
    printf -- '-- the leaf term where the rebuild wrote back as many leaves as it found\n'
    t "SELECT /* wiki_rs_leaf_term_same_leaves */ count(*) AS fixtures,
              count(*) FILTER (WHERE leaf_term > 0) AS over,
              count(*) FILTER (WHERE leaf_term = 0) AS exact,
              count(*) FILTER (WHERE leaf_term < 0) AS under,
              max(leaf_term) AS largest
         FROM verdicts WHERE aft_leaf = leaf_pages"
    printf -- '-- the same, for every fixture whose error exceeds one point\n'
    t "SELECT /* wiki_rs_decomposition_rows */ num, idx, grp, total_pages,
              internal_pages, leaf_pages, density, aft_internal, aft_leaf,
              score_pct, actual, err, leaf_term, internal_term, dead_term
         FROM verdicts WHERE abs(err) > 1 ORDER BY err"
    printf -- '-- family 3 as built: the page classes a rebuild of each fresh index wrote back\n'
    t "SELECT /* wiki_rs_family3 */ num, idx, total_pages, internal_pages, leaf_pages,
              round(density::numeric, 2) AS density, fillfactor, aft_internal,
              aft_leaf, score_pct, actual, err
         FROM verdicts WHERE grp = 'falsepos' ORDER BY num"
    # The headline both ways.  Test 120 is the suite's one probabilistic
    # fixture: its precondition is a sample miss, so it is scored on some runs
    # and not others, and any statistic that includes it moves between runs.
    # Both populations are printed so the page can report the stable one and
    # name what the other adds.
    printf -- '-- the headline over the deterministic fixtures, and with p120 included\n'
    t "SELECT /* wiki_rs_headline */ scope, count(*) AS fixtures,
              round(avg(abs(err)), 2) AS mean_abs_err,
              round(percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(err))::numeric, 2)
                                      AS median_abs_err,
              round(max(err), 1) AS worst_over, round(min(err), 1) AS worst_under,
              round(corr(score_pct::float8, actual::float8)::numeric, 4) AS correlation
         FROM (SELECT v.*, 'all scored'  AS scope FROM verdicts v
               UNION ALL
               SELECT v.*, 'without p120' AS scope FROM verdicts v WHERE v.num <> 120) z
        GROUP BY scope ORDER BY scope"
    printf -- '-- the ten largest over-estimates and the ten largest under-estimates\n'
    t "SELECT /* wiki_rs_worst_over */ num, idx, grp, score_pct, actual, err, density,
              leaf_pages, dead_pages
         FROM verdicts WHERE err IS NOT NULL ORDER BY err DESC LIMIT 10"
    t "SELECT /* wiki_rs_worst_under */ num, idx, grp, score_pct, actual, err, density,
              leaf_pages, dead_pages
         FROM verdicts WHERE err IS NOT NULL ORDER BY err ASC LIMIT 10"
  } > "$OUT/accuracy17.txt" 2>&1
  cat "$OUT/accuracy17.txt" >&2
}

# ---------------------------------------------------------------- guard -----
# The same oracle over schema rs: one REINDEX INDEX per guard fixture, the file
# measured before and after.  No verdict band is applied, because these are not
# suite fixtures.  Destructive, so it runs once per build of schema rs: the
# fixtures stage drops guard_res with the fixtures, and a guard_res that is
# still here means these fixtures were already rebuilt.  To run it again, re-run
# fixtures, report and decide first.
stage_guard() {
  say "the oracle over the guard fixtures in schema rs"
  [ -z "$(s "SELECT to_regclass('public.guard_res')")" ] \
    || die "the guard oracle has already rebuilt schema rs; re-run fixtures, report and decide first"
  q "CREATE /* wiki_rs_guard_res */ TABLE guard_res(idx text PRIMARY KEY,
       score_pct numeric, signal bool, before_bytes bigint, after_bytes bigint,
       density numeric, leaf_pages int, dead_pages int, total_pages bigint);" > /dev/null
  q "DO /* wiki_rs_guard_oracle */ \$g\$
     DECLARE r record; sb bigint; sa bigint;
     BEGIN
       FOR r IN SELECT d.* FROM decide d WHERE d.schema_name = 'rs' ORDER BY d.index_name LOOP
         sb := pg_relation_size(('rs.' || quote_ident(r.index_name))::regclass);
         EXECUTE format('REINDEX INDEX rs.%I', r.index_name);
         sa := pg_relation_size(('rs.' || quote_ident(r.index_name))::regclass);
         INSERT INTO guard_res VALUES (r.index_name,
           round(100 * r.reindex_score::numeric, 1), r.reindex_score >= 0.5,
           sb, sa, CASE WHEN r.leaf_pages > 0
                        THEN round(r.avg_leaf_density::numeric, 2) END,
           r.leaf_pages, r.empty_pages + r.deleted_pages, r.total_pages);
       END LOOP;
     END \$g\$;" > /dev/null || die "guard oracle failed"
  t "SELECT /* wiki_rs_guard_report */ idx, total_pages, leaf_pages, dead_pages,
            density, score_pct, signal, before_bytes, after_bytes,
            round(100.0 * (before_bytes - after_bytes) / greatest(before_bytes, 1), 1)
                AS actual
       FROM guard_res ORDER BY idx" > "$OUT/guard17.txt" 2>&1
  cat "$OUT/guard17.txt" >&2
}

# --------------------------------------------------------------- errors -----
stage_errors() {
  say "errors the server logged during this run"
  local log="$OUT/server17.log" from
  [ -f "$log" ] || { note "no server log"; return 0; }
  from=$(grep -n 'wiki_rs_run_mark' "$log" | tail -1 | cut -d: -f1)
  [ -n "${from:-}" ] || from=1
  sed -n "${from},\$p" "$log" | grep -E '(ERROR|FATAL|PANIC)' > "$OUT/errors17.txt"
  {
    printf 'logged_error_lines=%s\n' "$(grep -c '' "$OUT/errors17.txt")"
    printf -- '-- distinct messages\n'
    sed -E 's/.*(ERROR|FATAL|PANIC)/\1/' "$OUT/errors17.txt" | sort | uniq -c | sort -rn
  } > "$OUT/errors17_summary.txt"
  cat "$OUT/errors17_summary.txt" >&2
}

# -------------------------------------------------------------- summary -----
stage_summary() {
  say "what landed in $OUT"
  ls -la "$OUT" >&2
  local x
  for x in platform17 checks17 exact17 decide17 maint_proofs17 cost17 priv17 accuracy17 errors17_summary; do
    [ -f "$OUT/$x.txt" ] && { printf -- '-- %s\n' "$x" >&2; cat "$OUT/$x.txt" >&2; }
  done
  return 0
}

# ---------------------------------------------------------------- stop -------
# stop runs sandbox_guard before it stops anything, so it can only ever stop the
# cluster this script started inside its own marked sandbox.
stage_stop() {
  say "stop the 17 cluster"
  [ -d "$SANDBOX" ] || { note "no sandbox at $SANDBOX"; return 0; }
  sandbox_guard
  [ -d "$DATA" ] || { note "no data directory"; return 0; }
  "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1
  [ -f "$DATA/postmaster.pid" ] && die "postmaster.pid still present in $DATA"
  pgrep -f "postgres.*$DATA" > /dev/null 2>&1 && die "a postgres process still runs on $DATA"
  [ -n "$(ls -A "$SOCK" 2>/dev/null)" ] && die "socket directory $SOCK is not empty"
  note "stopped: no postmaster.pid, no process, empty socket directory"
}

# clean checks the sandbox before it stops or deletes anything, and deletes only
# the resolved path sandbox_guard approved.  The 12 leg shares this sandbox and
# deletes only its own directories, so clean refuses while that leg's data
# directory is still here: deleting it under a running 12 cluster would leave
# that postmaster running on a deleted data directory.
stage_clean() {
  [ -d "$SANDBOX" ] || { note "no sandbox at $SANDBOX, nothing to delete"; return 0; }
  sandbox_guard
  [ -e "$SANDBOX_REAL/data12" ] \
    && die "refusing: $SANDBOX_REAL/data12 still exists; run the 12 leg's clean first"
  stage_stop
  say "delete $SANDBOX_REAL"
  rm -rf "$SANDBOX_REAL"
}

# ------------------------------------------------------------ dispatcher -----
STAGES_DEFAULT="build check cluster texts fixtures suite churn report decide facts cost priv score accuracy guard errors summary"
run_stage() {
  case "$1" in
    build|check|cluster|texts|fixtures|suite|churn|report|decide|facts|cost|priv|score|accuracy|guard|errors|summary|stop|clean)
      "stage_$1" ;;
    *) die "unknown stage: $1" ;;
  esac
}

# A run that asks for any stage but stop and clean needs a sandbox, and
# make_sandbox() checks where it is before it creates or marks anything.  A
# run of stop or clean alone creates nothing.
main() {
  local stages="$*" st needs=0
  [ -n "$stages" ] || stages="$STAGES_DEFAULT"
  for st in $stages; do
    case "$st" in stop|clean) ;; *) needs=1 ;; esac
  done
  [ "$needs" = 1 ] && make_sandbox
  for st in $stages; do run_stage "$st" || die "stage $st failed"; done
  say "done: $stages"
}

main "$@"
```

### The PostgreSQL 12 leg script

```sh
#!/usr/bin/env bash
#
# reindex_score_v12.sh - the PostgreSQL 12 leg of the measurement behind "How
# Accurate Is the pgstatindex REINDEX_SCORE B-Tree Maintenance Heuristic, on
# PostgreSQL 17 and 12".  Bash and SQL only: build the pinned 12 checkout out
# of tree, run its regression suites, start an isolated cluster, build the same
# shared mandatory B-tree bloat suite the 17 leg reads out of the same page
# blocks, run the heuristic exactly as filed, and score every fixture against a
# measured REINDEX INDEX.
#
# It answers three questions the 17 leg cannot: does the exact filed text still
# run unmodified on the oldest major this page claims, which fixtures of the
# shared suite can a 12.2 server not build at all, and - in its crossleg stage -
# how do the two majors' scores differ index by index?  Nothing here assumes
# what PostgreSQL 12 does: every fixture that needs a feature is attempted, and
# the server's own refusal is recorded as a skip.  The one behaviour this leg
# exists to price is deduplication, which arrived in PostgreSQL 13: a 12.2
# rebuild cannot compress duplicate keys into posting lists, so the gap between
# what REINDEX_SCORE predicts and what a rebuild gives back is a different gap
# here.
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
# Schema rs holds what the suite does not cover and this page still measures:
# the shapes pgstatindex refuses, an index the catalog says is not valid, fresh
# builds at four fillfactors, an index on an empty table, a two-page index, a
# sparse index, an index whose leading key range was deleted, an index every
# entry was deleted from, and a duplicate-heavy index.  Those are guard
# fixtures, not scored fixtures, and no verdict band is applied to them.
#
# The pinned checkout is read only, and the build and check stages refuse to
# run unless it is at $PIN with no tracked file changed.  Everything this
# script writes lives under $SANDBOX, which must be a directory directly
# inside this repository's .wiki-runtime/tmp; main() marks it when it creates
# it, and stop and clean touch nothing that does not carry that mark.
#
# Usage, from the repository root:
#   bash reindex_score_v12.sh                  # every stage, in order
#   bash reindex_score_v12.sh score accuracy   # selected stages
#   bash reindex_score_v12.sh clean            # stop and delete the sandbox
#
# Stages: build check cluster texts fixtures suite churn report decide facts
#         cost priv score accuracy guard errors crossleg summary stop clean
#
# Environment: WIKI_ROOT PAGE SRC12 SANDBOX PORT12 JOBS ROWS EXTRA_CFLAGS
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v17/questions/indexing/btree-reindex-score-heuristic.md}"
SRC12="${SRC12:-$WIKI_ROOT/raw/postgres-12}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/rscore}"
PORT12="${PORT12:-55412}"
JOBS="${JOBS:-4}"
ROWS="${ROWS:-200000}"
# ICU 68 dropped the TRUE/FALSE macros a 12.2 tree still uses, so the two
# defines go back in through CFLAGS.  Set this to -O2 -g, not to the empty
# string, on a host whose ICU still defines them: configure treats an empty
# CFLAGS as set and then builds without optimisation.
EXTRA_CFLAGS="${EXTRA_CFLAGS:--O2 -g -DTRUE=1 -DFALSE=0}"

# The commit this leg is built from, the v12 pin in wiki/versions.md, and the
# file main() writes into a sandbox it created.
PIN=45b88269a353ad93744772791feb6d01bc7e1e42
MARKER=.reindex-score-sandbox

BUILD="$SANDBOX/build12"; INST="$SANDBOX/install12"; DATA="$SANDBOX/data12"
OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql12"; SOCK="$SANDBOX/sock12"; BIN="$INST/bin"
DB=score12
export PGPORT="$PORT12" PGHOST="$SOCK" PGDATABASE=postgres

# SHA-256 of the sql blocks this page files, in page order.  BASE_SQL is the
# filed heuristic; BASE_HARNESS, BASE_GATE, BASE_SUITE, BASE_DRAIN and
# BASE_CENSUS are the shared suite's harness, its family 1 fixtures, its
# families 2 to 6, rule 2's drain and rule 3's census.  A text that does not
# hash to its constant stops the run: the scored text must be the filed text.
BASE_SQL=ffa9d4fa697e2b15c96e056b91c3774d5558f12e71b6c9d48e58c2d4beaf7822
BASE_HARNESS=6d33108ac87feb6b901f853b45edc8a130fa9a743cbc9d84c66401e54973a119
BASE_GATE=9d49596f780958fcae8982d19c168da9d6c87ad75c1b40c910dc34c135325e49
BASE_SUITE=5a29c8d84224fc3ca30062373f82940d9f41046e23a8ac74e8a4803277f00930
BASE_DRAIN=0d36f4980d9ee918ada8f24dffe8e0fc2566728d3079a35ebfdc373075a0d794
BASE_CENSUS=e3e1a0ae28599887c79482b4b3eda8a3ac4292c6bb089a01a45e723dcf0b09ec

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# check_pin: the build and the regression suites must come from exactly the
# commit the page records, with no tracked file changed.  Untracked files, such
# as a Finder .DS_Store, are not part of the build and are not checked.
check_pin() {
  local head dirty
  head=$(git -C "$SRC12" rev-parse HEAD 2>/dev/null) || die "$SRC12 is not a git checkout"
  [ "$head" = "$PIN" ] || die "$SRC12 is at $head, not at the pinned $PIN"
  dirty=$(git -C "$SRC12" status --porcelain --untracked-files=no 2>/dev/null) \
    || die "git status failed in $SRC12"
  [ -z "$dirty" ] || die "$SRC12 has changed tracked files, so a build would not be the pin"
}

# make_sandbox: create $SANDBOX, or accept one this script created before, only
# when it is a directory directly inside this repository's .wiki-runtime/tmp
# once .. and symbolic links are resolved, and mark it as this script's.  An
# existing directory that is not empty and carries no mark is refused.
make_sandbox() {
  local tmp parent base
  mkdir -p "$WIKI_ROOT/.wiki-runtime/tmp" || die "cannot create $WIKI_ROOT/.wiki-runtime/tmp"
  tmp=$(cd "$WIKI_ROOT/.wiki-runtime/tmp" && pwd -P) || die "cannot resolve .wiki-runtime/tmp"
  base=$(basename "$SANDBOX")
  case "$base" in ''|.|..) die "refusing sandbox $SANDBOX: it names no directory of its own" ;; esac
  parent=$(cd "$(dirname "$SANDBOX")" 2>/dev/null && pwd -P) \
    || die "refusing sandbox $SANDBOX: its parent directory does not exist"
  [ "$parent" = "$tmp" ] || die "refusing sandbox $SANDBOX: it is not directly inside $tmp"
  if [ -e "$SANDBOX" ] && [ ! -f "$SANDBOX/$MARKER" ] \
     && [ -n "$(ls -A "$SANDBOX" 2>/dev/null)" ]; then
    die "refusing sandbox $SANDBOX: it exists, is not empty, and this script did not create it"
  fi
  mkdir -p "$SANDBOX" && : > "$SANDBOX/$MARKER" || die "cannot create $SANDBOX"
}

# sandbox_guard: the check stop and clean make before they touch anything.  The
# sandbox must resolve to a directory directly inside this repository's
# .wiki-runtime/tmp and carry make_sandbox()'s mark.  SANDBOX_REAL is the
# resolved path, and clean deletes only this leg's directories inside it.
sandbox_guard() {
  local tmp
  tmp=$(cd "$WIKI_ROOT/.wiki-runtime/tmp" 2>/dev/null && pwd -P) \
    || die "refusing: $WIKI_ROOT/.wiki-runtime/tmp does not exist"
  SANDBOX_REAL=$(cd "$SANDBOX" 2>/dev/null && pwd -P) || die "refusing: cannot resolve $SANDBOX"
  [ "$(dirname "$SANDBOX_REAL")" = "$tmp" ] \
    || die "refusing: $SANDBOX_REAL is not directly inside $tmp"
  [ -f "$SANDBOX_REAL/$MARKER" ] \
    || die "refusing: $SANDBOX_REAL carries no $MARKER, so this script did not create it"
}

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
# val_or_err() runs a statement that answers on one major and raises on the
# other, and prints whichever came back.  ON_ERROR_STOP is deliberately absent:
# the refusal is the reading.  This leg is the one that raises.
val_or_err() { PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -At -q -d "$DB" -c "$1" 2>&1 | head -1; }

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
# maintained twice keeps the larger of the two dead counts.  Bash case patterns
# and parameter expansion only: no awk, no perl.
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
        printf "UPDATE /* wiki_rs_maint_verbose */ maint SET removed = %s, remain = %s, dead_not_removable = greatest(coalesce(dead_not_removable, 0), %s) WHERE tbl = '%s';\n" \
               "$removed" "$remain" "$dead" "$cur"
        cur="" ;;
    esac
  done < "$log"
}

# maint_skips: proof 1's other half.  A foreground VACUUM or ANALYZE that could
# not take its ShareUpdateExclusiveLock says so in the log, and a statement cut
# short by a timeout does too; either way the command returned without doing
# the work.  Only the lines after the churn mark are read, so a re-run does not
# inherit the lines of the run before it.
maint_skips() {
  local log="$OUT/server12.log" from line
  : > "$OUT/maint_skips12.txt"
  [ -f "$log" ] || return 0
  from=$(grep -n 'wiki_rs_maint_mark' "$log" | tail -1 | cut -d: -f1)
  [ -n "${from:-}" ] || from=$(grep -n 'wiki_rs_run_mark' "$log" | tail -1 | cut -d: -f1)
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
  q "SELECT /* wiki_rs_maint_after */ maint_after()" > /dev/null \
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
  # when there is something to count.
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
stage_build() {
  say "build 12 out of tree from $SRC12"
  [ -x "$SRC12/configure" ] || die "no pinned checkout at $SRC12; set SRC12 or run from the repository root"
  check_pin
  # An install is reused only when this script built it from the same pin.
  if [ -x "$BIN/postgres" ]; then
    [ "$(cat "$INST/.wiki_pin" 2>/dev/null)" = "$PIN" ] \
      || die "the install under $INST was not built from $PIN; run clean, then build"
    note "already built from $PIN, skipping"; return 0
  fi
  mkdir -p "$BUILD" "$OUT" "$SQLD"
  # --with-icu on purpose: five fixtures of the shared suite need ICU
  # collations, and without them the run would only record five more skips.
  ( cd "$BUILD" && "$SRC12/configure" --prefix="$INST" --enable-debug \
      --with-icu --with-readline --with-zlib CFLAGS="$EXTRA_CFLAGS" > configure.log 2>&1 ) \
    || { cp "$BUILD/configure.log" "$OUT/configure12.log" 2>/dev/null; die "configure failed, see $OUT/configure12.log"; }
  ( cd "$BUILD" && make -j"$JOBS" > make.log 2>&1 && make install > install.log 2>&1 ) \
    || { cp "$BUILD"/*.log "$OUT/" 2>/dev/null; grep -m3 'error:' "$BUILD/make.log" >&2; die "make failed"; }
  ( cd "$BUILD" && make -C contrib/pgstattuple -j"$JOBS" >> install.log 2>&1 \
      && make -C contrib/pgstattuple install >> install.log 2>&1 ) || die "contrib/pgstattuple failed"
  local l
  for l in configure make install; do cp "$BUILD/$l.log" "$OUT/${l}12.log" 2>/dev/null; done
  printf '%s\n' "$PIN" > "$INST/.wiki_pin"
  note "$("$BIN/postgres" --version), built from $PIN"
}

# A suite that fails stops the run: nothing is measured on a server whose own
# regression tests did not pass.  Both the exit status and the result line
# must say so.
stage_check() {
  say "regression suites, 12"
  check_pin
  mkdir -p "$OUT"
  : > "$OUT/checks12.txt"
  local rc_core rc_pgst line_core line_pgst l d
  ( cd "$BUILD" && make check > check_core.log 2>&1 ); rc_core=$?
  line_core=$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_core.log" | tail -1)
  printf 'core=%s %s\n' "$rc_core" "$line_core" >> "$OUT/checks12.txt"
  ( cd "$BUILD" && make -C contrib/pgstattuple check > check_pgstattuple.log 2>&1 ); rc_pgst=$?
  line_pgst=$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_pgstattuple.log" | tail -1)
  printf 'pgstattuple=%s %s\n' "$rc_pgst" "$line_pgst" >> "$OUT/checks12.txt"
  for l in "$BUILD"/check_*.log; do [ -f "$l" ] && cp "$l" "$OUT/12_$(basename "$l")"; done
  for d in "$BUILD"/src/test/regress/regression.diffs "$BUILD"/contrib/pgstattuple/regression.diffs; do
    [ -f "$d" ] && cp "$d" "$OUT/diffs12_$(basename "$(dirname "$d")").txt"
  done
  cat "$OUT/checks12.txt" >&2
  case "$rc_core:$line_core" in
    "0:All "*) : ;;
    *) die "make check did not pass (${line_core:-no result line}); see $OUT/12_check_core.log" ;;
  esac
  case "$rc_pgst:$line_pgst" in
    "0:All "*) : ;;
    *) die "the pgstattuple check did not pass (${line_pgst:-no result line}); see $OUT/12_check_pgstattuple.log" ;;
  esac
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
  say "isolated 12 cluster on port $PORT12"
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
  printf -- '-- wiki_rs_run_mark %s\n' "$(date -u +%FT%TZ)" >> "$OUT/server12.log"
  "$BIN/psql" -X -At -q -d postgres -c "SELECT 1" > /dev/null 2>&1 || die "cannot connect"
  "$BIN/psql" -X -At -q -d postgres -c \
    "SELECT count(*) FROM pg_database WHERE datname = '$DB'" | grep -q '^1$' \
    || "$BIN/createdb" "$DB" || die "createdb failed"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null || die "pgstattuple not installed"
  {
    printf 'uname=%s\n' "$(uname -sm)"
    printf 'pin=%s\n' "$(cat "$INST/.wiki_pin" 2>/dev/null)"
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
# Six texts come out of the page:
#   report.sql   the filed heuristic, byte for byte, hash-checked
#   view.sql     the same text as a view over the internal `final` stage, with
#                one edit, printed: the two SET lines dropped.  The filed text
#                prefilters nothing, so the view's population is the report's
#   harness.sql, gate.sql, suite.sql, drain.sql, census.sql
#                the shared mandatory suite, all hash-checked
gen_view() {                       # gen_view <view> < text
  local view=$1 line tail=0
  printf 'DROP VIEW IF EXISTS %s CASCADE;\nCREATE VIEW %s AS\n' "$view" "$view"
  # The presentation SELECT is the one line of the filed text that starts with
  # SELECT at column 0; every SELECT inside the CTE chain is indented.
  while IFS= read -r line; do
    case $line in
      "SET "*)
        printf '   harness edit: dropped %s\n' "$line" >&2; continue ;;
      "SELECT"*) tail=1; continue ;;
    esac
    [ "$tail" = 1 ] && continue
    printf '%s\n' "$line"
  done
  printf 'SELECT f.* FROM final f;\n'
}

stage_texts() {
  say "extract the heuristic and the shared suite from $PAGE"
  mkdir -p "$SQLD" "$OUT"
  [ -f "$PAGE" ] || die "no page at $PAGE; set PAGE or run from the repository root"
  block 1 "$BASE_SQL"     "$SQLD/report.sql"  "filed heuristic"
  block 2 "$BASE_HARNESS" "$SQLD/harness.sql" "suite harness"
  block 3 "$BASE_GATE"    "$SQLD/gate.sql"    "family 1 fixtures"
  block 4 "$BASE_SUITE"   "$SQLD/suite.sql"   "families 2-6 fixtures"
  block 5 "$BASE_DRAIN"   "$SQLD/drain.sql"   "rule 2 drain"
  block 6 "$BASE_CENSUS"  "$SQLD/census.sql"  "rule 3 census and forgeries"
  gen_view score_final < "$SQLD/report.sql" > "$SQLD/view.sql"
  grep -v '^SET ' "$SQLD/report.sql" > "$SQLD/bare.sql"
}

# ------------------------------------------------------------- fixtures -----
# Schema rs: the guard fixtures, which the shared suite does not cover and this
# page still measures.  Every statement is DISPOSABLE - it drops and rebuilds a
# whole schema and writes indisvalid = false into pg_index by hand - and is not
# meant for a database anyone cares about.  The three session GUCs it sets are
# PGC_USERSET: session scope, no reload and no restart.
stage_fixtures() {
  say "guard fixtures in schema rs (rows=$ROWS)"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null
  cat > "$SQLD/fixtures.sql" <<'SQL'
-- DISPOSABLE guard fixtures for the REINDEX_SCORE heuristic.
-- Every object lives in schema rs of a throwaway database.
SET statement_timeout = '30min';   -- PGC_USERSET, session scope
SET lock_timeout      = '30s';     -- PGC_USERSET, session scope
SET client_min_messages = warning; -- PGC_USERSET, session scope

-- The guard oracle's results go with the fixtures they measured: guard_res
-- exists only between a guard stage and the next build of schema rs, which is
-- how the guard stage knows not to rebuild these fixtures a second time.
DROP TABLE IF EXISTS public.guard_res;
DROP SCHEMA IF EXISTS rs CASCADE;
CREATE SCHEMA rs;

-- 1. fresh builds at four fillfactors: what a rebuild leaves, measured, and
--    therefore what the score of a just-rebuilt index is.
CREATE TABLE rs.t_fresh (id int);
INSERT INTO rs.t_fresh SELECT g FROM generate_series(1, :rows) g;
CREATE INDEX i_fresh ON rs.t_fresh (id);
CREATE INDEX i_ff100 ON rs.t_fresh (id) WITH (fillfactor = 100);
CREATE INDEX i_ff50  ON rs.t_fresh (id) WITH (fillfactor = 50);
CREATE INDEX i_ff10  ON rs.t_fresh (id) WITH (fillfactor = 10);

-- 2. the empty index: pgstatindex reports NaN for avg_leaf_density when there
--    are no leaf pages at all, which is the input both CASE guards exist for.
CREATE TABLE rs.t_empty (id int PRIMARY KEY);
CREATE INDEX i_empty ON rs.t_empty (id);

-- 3. a two-page index: one metapage and one leaf page holding a single entry,
--    the smallest non-empty shape, and the one where the metapage in
--    total_pages decides the verdict.
CREATE TABLE rs.t_one (id int);
INSERT INTO rs.t_one VALUES (1);
CREATE INDEX i_one ON rs.t_one (id);

-- 4. sparse leaves: nine tenths of the rows deleted and vacuumed, so the
--    entries that remain are spread over every leaf page.
CREATE TABLE rs.t_sparse (id int);
INSERT INTO rs.t_sparse SELECT g FROM generate_series(1, :rows) g;
CREATE INDEX i_sparse ON rs.t_sparse (id);
DELETE FROM rs.t_sparse WHERE id % 10 <> 0;
VACUUM rs.t_sparse;

-- 5. deleted pages: a contiguous head of the key range deleted, so whole leaf
--    pages empty out and _bt_pagedel marks them deleted.
CREATE TABLE rs.t_head (id int);
INSERT INTO rs.t_head SELECT g FROM generate_series(1, :rows) g;
CREATE INDEX i_head ON rs.t_head (id);
DELETE FROM rs.t_head WHERE id <= (:rows * 9) / 10;
VACUUM rs.t_head;

-- 6. duplicates: a key with 100 rows per value, dense and untouched.  The
--    file a server that deduplicates writes is about a third of the one a
--    server that does not writes, so this fixture prices the build rather than
--    the rebuild; on both majors the score reads 0 and a rebuild of a file
--    already written that way returns nothing.
CREATE TABLE rs.t_dup (k int);
INSERT INTO rs.t_dup SELECT g % (:rows / 100) FROM generate_series(1, :rows) g;
CREATE INDEX i_dup ON rs.t_dup (k);

-- 6b. every entry removed: the emptiest shape a live B-tree reaches.  nbtree
--     never deletes the rightmost page of a level, so this index keeps its
--     rightmost leaf, and the internal pages above it, however much is
--     vacuumed out of it, and avg_leaf_density stays a number rather than
--     becoming NaN.  The facts stage prints the shape it reached.  This is the
--     fixture behind the page's claim that leaf_pages = 0 means a metapage and
--     nothing else: an emptied index does not reach that state, and only a
--     rebuilt or never-filled one does.
CREATE TABLE rs.t_alldel (id int);
INSERT INTO rs.t_alldel SELECT g FROM generate_series(1, :rows) g;
CREATE INDEX i_alldel ON rs.t_alldel (id);
DELETE FROM rs.t_alldel;
VACUUM rs.t_alldel;
VACUUM rs.t_alldel;

-- 7. the shapes pgstatindex refuses, and the ones the candidate filter drops.
CREATE TABLE rs.t_other (id int, txt text, arr int[], pt point);
INSERT INTO rs.t_other
SELECT g, g::text, ARRAY[g], point(g, g) FROM generate_series(1, 1000) g;
CREATE INDEX i_hash  ON rs.t_other USING hash (id);
CREATE INDEX i_gin   ON rs.t_other USING gin (arr);
CREATE INDEX i_gist  ON rs.t_other USING gist (pt);   -- gist over int needs btree_gist
CREATE INDEX i_brin  ON rs.t_other USING brin (id);
CREATE VIEW  rs.v_other AS SELECT * FROM rs.t_other;
CREATE SEQUENCE rs.s_other;
CREATE MATERIALIZED VIEW rs.m_other AS SELECT * FROM rs.t_other;
CREATE INDEX i_matview ON rs.m_other (id);

-- a partitioned index has relkind 'I' and no storage of its own
CREATE TABLE rs.t_part (id int) PARTITION BY RANGE (id);
CREATE TABLE rs.t_part_1 PARTITION OF rs.t_part FOR VALUES FROM (1) TO (1000);
CREATE INDEX i_part ON rs.t_part (id);

-- an index the catalog says is not valid: 17's pgstatindex refuses it, and the
-- facts stage records what the server under test does with it
CREATE TABLE rs.t_invalid (id int);
INSERT INTO rs.t_invalid SELECT g FROM generate_series(1, 1000) g;
CREATE INDEX i_invalid ON rs.t_invalid (id);
UPDATE pg_index SET indisvalid = false
 WHERE indexrelid = 'rs.i_invalid'::regclass;

ANALYZE rs.t_fresh, rs.t_empty, rs.t_one, rs.t_sparse, rs.t_head, rs.t_dup,
        rs.t_alldel, rs.t_other, rs.t_invalid;
SQL
  PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" \
    -v rows="$ROWS" -f "$SQLD/fixtures.sql" > "$OUT/fixtures12.log" 2>&1 \
    || { tail -10 "$OUT/fixtures12.log" >&2; die "guard fixtures failed"; }
  note "guard indexes: $(s "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'rs' AND c.relkind IN ('i','I')")"
}

# ---------------------------------------------------------------- suite -----
stage_suite() {
  say "the shared mandatory suite, build and baseline phases"
  [ -f "$SQLD/suite.sql" ] || die "run the texts stage first"
  # CREATE SCHEMA public grants nothing to PUBLIC, so initdb's USAGE grant is
  # restored here.
  q "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;
     GRANT USAGE ON SCHEMA public TO PUBLIC;" > /dev/null \
    || die "schema reset failed"
  q "CREATE EXTENSION IF NOT EXISTS pgstattuple;" > /dev/null || die "pgstattuple not installed"
  # The no-defeat rule's window opens at the first churn statement, which is in
  # the fixture file below; this mark is where the skip-line check starts
  # reading, so a re-run of this stage does not inherit an earlier run's lines.
  printf -- '-- wiki_rs_maint_mark %s\n' "$(date -u +%FT%TZ)" >> "$OUT/server12.log"
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
  t "SELECT /* wiki_rs_suite_skips */ num, leg, idx, reason FROM skipped
      ORDER BY num, leg" > "$OUT/skipped12.txt" 2>&1
  t "SELECT /* wiki_rs_suite_families */ grp, count(*) AS fixtures,
            count(*) FILTER (WHERE want_stage = 'rebuild') AS want_rebuild
       FROM plan GROUP BY grp ORDER BY grp" >> "$OUT/skipped12.txt" 2>&1
  cat "$OUT/skipped12.txt" >&2
}

# ---------------------------------------------------------------- churn -----
stage_churn() {
  say "churn: rule 2 drain with its maintenance step, rule 3 census, forgeries last, churned snapshot"
  [ -n "$(s 'SELECT 1 FROM plan LIMIT 1')" ] || die "no plan rows; run the suite stage first"
  fl "$SQLD/drain.sql" > "$OUT/drain12.txt" 2> "$OUT/drain_verbose12.log" \
    || { tail -5 "$OUT/drain12.txt" >&2; tail -5 "$OUT/drain_verbose12.log" >&2
         die "drain failed"; }
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
  t "SELECT /* wiki_rs_skips_after_census */ num, leg, idx, reason FROM skipped
      ORDER BY num, leg" > "$OUT/skipped12.txt" 2>&1
  t "SELECT /* wiki_rs_families_after_census */ grp, count(*) AS fixtures,
            count(*) FILTER (WHERE want_stage = 'rebuild') AS want_rebuild
       FROM plan GROUP BY grp ORDER BY grp" >> "$OUT/skipped12.txt" 2>&1
  note "$(s "SELECT count(*) || ' fixtures scored after the census, ' ||
              (SELECT count(*) FROM skipped) || ' skipped' FROM plan")"
}

# --------------------------------------------------------------- report -----
# Phase 4, the decide phase, part one: the filed text exactly as filed, both
# SET lines included.  Its own output is what a reader sees, so the rows it
# prints are loaded back as report_filed and are what `reported` means.
stage_report() {
  say "run the filed heuristic"
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
  local rows cols
  rows=$(grep -c '^' "$OUT/report12.txt"); rows=$((rows - 1))
  cols=$(head -1 "$OUT/report12.txt" | tr '|' '\n' | grep -c '^')
  {
    printf 'report_rows=%s\n' "$rows"
    printf 'report_columns=%s\n' "$cols"
    printf 'report_bytes=%s\n' "$(wc -c < "$OUT/report12.txt")"
    printf 'report_signalled=%s\n' "$(cut -d'|' -f13 "$OUT/report12.txt" | grep -c '^t$')"
  } >> "$OUT/exact12.txt"
  cat "$OUT/exact12.txt" >&2
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" \
    -f "$SQLD/report.sql" > "$OUT/report12_pretty.txt" 2>&1
  # Load the printed rows back.  Fields 2, 12 and 13 are index_name,
  # reindex_score_pct and reindex_signal; no field of this report can contain a
  # pipe.  A NaN percentage is quoted, because that is how numeric NaN is
  # written as a literal.
  q "DROP TABLE IF EXISTS report_filed;
     CREATE /* wiki_rs_report_filed */ TABLE report_filed(index_name text PRIMARY KEY, reindex_score_pct numeric, reindex_signal bool);" \
    > /dev/null || die "report_filed failed"
  : > "$SQLD/report_rows.sql"
  local name pct sig
  while IFS='|' read -r _ name _ _ _ _ _ _ _ _ _ pct sig; do
    [ -n "${name:-}" ] || continue
    case ${pct:-} in NaN) pct="'NaN'" ;; '') pct=NULL ;; esac
    case ${sig:-} in t) sig=true ;; f) sig=false ;; *) sig=NULL ;; esac
    printf "INSERT INTO report_filed VALUES ('%s', %s, %s);\n" \
      "${name//\'/\'\'}" "$pct" "$sig" >> "$SQLD/report_rows.sql"
  done < <(tail -n +2 "$OUT/report12.txt")
  fl "$SQLD/report_rows.sql" > /dev/null || die "loading report_filed failed"
  note "report_filed rows: $(s 'SELECT count(*) FROM report_filed')"
}

# --------------------------------------------------------------- decide -----
stage_decide() {
  say "materialize the heuristic's reading of every index"
  fl "$SQLD/view.sql" > /dev/null || die "harness view failed"
  q "DROP TABLE IF EXISTS decide;
     CREATE TABLE decide AS SELECT /* wiki_rs_decide */ * FROM score_final;" \
    > /dev/null || die "decide failed"
  q "CREATE /* wiki_rs_decide_idx */ INDEX decide_idx ON decide (index_name);" > /dev/null
  {
    printf 'decide_rows=%s\n' "$(s 'SELECT count(*) FROM decide')"
    printf 'decide_fixtures=%s\n' "$(s 'SELECT count(*) FROM decide d JOIN plan p ON p.idx = d.index_name')"
    printf 'filed_rows=%s\n' "$(s 'SELECT count(*) FROM report_filed')"
    # The view differs from the filed text in its presentation SELECT only, but
    # the two are not two readings of one state: the report ran first, the view
    # ran second, and between them this stage created its own tables, so the
    # catalog and TOAST indexes of the fixture database have moved.  The
    # fixtures have not, which is why the fixture rows are the comparison that
    # must come out at zero and the whole-population count is printed beside it
    # as context rather than as a check.  IS DISTINCT FROM, so that a row
    # missing on one side counts as a difference.
    printf 'view_disagrees_with_filed_fixtures=%s\n' \
      "$(s "SELECT count(*) FROM plan p
              JOIN report_filed r ON r.index_name = p.idx
              JOIN decide d       ON d.index_name = p.idx
             WHERE round(100 * d.reindex_score::numeric, 1) IS DISTINCT FROM r.reindex_score_pct")"
    printf 'view_disagrees_with_filed_all=%s (catalog drift between the two reads)\n' \
      "$(s "SELECT count(*) FROM report_filed r JOIN decide d ON d.index_name = r.index_name
             WHERE round(100 * d.reindex_score::numeric, 1) IS DISTINCT FROM r.reindex_score_pct")"
    printf 'signal_disagrees_with_filed=%s\n' \
      "$(s "SELECT count(*) FROM report_filed r JOIN decide d ON d.index_name = r.index_name
             WHERE (d.reindex_score >= 0.5) IS DISTINCT FROM r.reindex_signal")"
    printf 'view_rows_the_report_did_not_print=%s\n' \
      "$(s "SELECT count(*) FROM decide d WHERE NOT EXISTS
             (SELECT 1 FROM report_filed r WHERE r.index_name = d.index_name)")"
    printf 'fixtures_printed=%s of %s\n' \
      "$(s "SELECT count(*) FROM plan p JOIN report_filed r ON r.index_name = p.idx")" \
      "$(s 'SELECT count(*) FROM plan')"
    printf 'nan_scores=%s\n' \
      "$(s "SELECT count(*) FROM decide WHERE reindex_score = 'NaN'::float8")"
    printf 'nan_scores_signalled=%s\n' \
      "$(s "SELECT count(*) FROM decide WHERE reindex_score = 'NaN'::float8
              AND reindex_score >= 0.5")"
    # The whole-cluster before-and-after, both halves from this run.  "before"
    # is the same statement with the two CASE guards removed, recomputed here
    # from the columns the statement itself kept, so the page's before column
    # is not a quotation from an earlier run.  u.nan is the unguarded score.
    printf -- '-- the guards, over every candidate: unguarded (before) beside filed (after)\n'
    t "SELECT /* wiki_rs_guard_effect */
              count(*)                                              AS rows_printed,
              count(*) FILTER (WHERE u.nan >= 0.5)                  AS signalled_before,
              count(*) FILTER (WHERE d.reindex_score >= 0.5)        AS signalled_after,
              count(*) FILTER (WHERE u.nan = 'NaN'::float8)         AS nan_before,
              count(*) FILTER (WHERE d.reindex_score = 'NaN'::float8) AS nan_after,
              count(*) FILTER (WHERE d.total_pages = 1)             AS metapage_only,
              count(*) FILTER (WHERE d.total_pages = 1
                                 AND u.nan >= 0.5)                  AS metapage_only_before,
              count(*) FILTER (WHERE d.total_pages = 1
                                 AND d.reindex_score >= 0.5)        AS metapage_only_after,
              count(*) FILTER (WHERE (u.nan >= 0.5)
                                  <> (d.reindex_score >= 0.5))      AS verdicts_the_guards_moved,
              count(*) FILTER (WHERE u.nan <> 'NaN'::float8
                                 AND round(u.nan::numeric, 6)
                                     <> round(d.reindex_score::numeric, 6)) AS finite_scores_that_differ
         FROM decide d
         CROSS JOIN LATERAL (
              SELECT (d.deleted_pages + d.empty_pages
                      + d.leaf_pages * GREATEST(0::float8,
                                                1 - d.avg_leaf_density / d.fillfactor))
                     / d.total_pages::float8 AS nan) u"
    # leaf_pages = 0 and total_pages = 1 must be the same set of rows: that is
    # the claim that a NaN density means a metapage and nothing else.
    printf -- '-- leaf_pages = 0 against total_pages = 1, and what those rows hold\n'
    t "SELECT /* wiki_rs_metapage_only */
              count(*) FILTER (WHERE leaf_pages = 0)                AS no_leaf,
              count(*) FILTER (WHERE total_pages = 1)               AS one_page,
              count(*) FILTER (WHERE (leaf_pages = 0) <> (total_pages = 1))
                                                                    AS the_two_disagree,
              count(*) FILTER (WHERE leaf_pages = 0
                                 AND deleted_pages + empty_pages > 0)
                                                                    AS no_leaf_but_dead_pages,
              count(*) FILTER (WHERE avg_leaf_density = 'NaN'::float8
                                 AND leaf_pages > 0)                AS nan_with_leaves
         FROM decide"
  } > "$OUT/decide12.txt"
  cat "$OUT/decide12.txt" >&2
}

# ---------------------------------------------------------------- facts -----
# The version-local and heuristic-local facts, none of them destructive, all of
# them taken before the oracle rebuilds anything.
stage_facts() {
  say "the heuristic's own edges: NaN, the metapage, the fillfactor, the refusals"
  {
    printf -- '-- NaN, as the engine compares it\n'
  } > "$OUT/facts12.txt"
  # The three readings every major answers.  They are in one statement because
  # they are one claim: a NaN score is not filtered out by >= 0.5, it passes it.
  t "SELECT /* wiki_rs_nan */ 'NaN'::float8 >= 0.5 AS nan_ge_half,
            greatest(0::float8, 'NaN'::float8)   AS greatest_zero_nan,
            0::bigint * 'NaN'::float8            AS zero_times_nan" \
    >> "$OUT/facts12.txt" 2>&1
  # This one is version-local and is read on its own, because this major
  # raises here and would otherwise take the three readings above down with it.
  printf -- '-- NaN over zero, the no-metapage denominator of an empty index\n' >> "$OUT/facts12.txt"
  printf 'nan_over_zero  %s\n' "$(val_or_err "SELECT 'NaN'::float8 / 0::float8")" >> "$OUT/facts12.txt"
  printf -- '-- and the same denominator under a guarded numerator\n' >> "$OUT/facts12.txt"
  printf 'zero_over_zero %s\n' "$(val_or_err "SELECT 0::float8 / 0::float8")" >> "$OUT/facts12.txt"
  printf -- '-- the score of every guard fixture, before any rebuild\n' >> "$OUT/facts12.txt"
  t "SELECT /* wiki_rs_guard_scores */ d.index_name, d.total_pages, d.internal_pages,
            d.leaf_pages, d.empty_pages, d.deleted_pages,
            round(d.avg_leaf_density::numeric, 2) AS density, d.fillfactor,
            round(100 * d.reindex_score::numeric, 1) AS score_pct,
            d.reindex_score >= 0.5 AS signal
       FROM decide d
      WHERE d.schema_name = 'rs'
      ORDER BY d.index_name" >> "$OUT/facts12.txt" 2>&1
  printf -- '-- the whole database, as the heuristic sees it\n' >> "$OUT/facts12.txt"
  t "SELECT /* wiki_rs_population */ count(*) AS indexes,
            count(*) FILTER (WHERE reindex_score = 'NaN'::float8) AS nan_score,
            count(*) FILTER (WHERE reindex_score >= 0.5) AS signalled,
            count(*) FILTER (WHERE reindex_score >= 0.5
                               AND reindex_score <> 'NaN'::float8) AS signalled_not_nan,
            count(*) FILTER (WHERE total_pages = 1) AS one_page,
            count(*) FILTER (WHERE total_pages = 2) AS two_page,
            max(reindex_score) FILTER (WHERE reindex_score <> 'NaN'::float8) AS max_finite_score
       FROM decide" >> "$OUT/facts12.txt" 2>&1
  # The metapage-only files are where a NaN density comes from.  The guards
  # leave no NaN score to count, so the files are counted instead, by schema,
  # and the ones outside the system schemas - objects this run created - are
  # named.
  printf -- '-- the metapage-only files, by schema\n' >> "$OUT/facts12.txt"
  t "SELECT /* wiki_rs_metapage_by_schema */ schema_name, count(*) AS indexes,
            count(*) FILTER (WHERE total_pages = 1)      AS metapage_only,
            count(*) FILTER (WHERE reindex_score >= 0.5) AS signalled
       FROM decide GROUP BY schema_name ORDER BY schema_name" >> "$OUT/facts12.txt" 2>&1
  printf -- '-- the metapage-only files outside pg_catalog and pg_toast\n' >> "$OUT/facts12.txt"
  t "SELECT /* wiki_rs_metapage_own */ schema_name, index_name, table_name
       FROM decide
      WHERE total_pages = 1 AND schema_name NOT IN ('pg_catalog', 'pg_toast')
      ORDER BY schema_name, index_name" >> "$OUT/facts12.txt" 2>&1
  # The filed denominator against the file itself.  pgstatindex builds
  # index_size from the four page classes plus the metapage, and its scan
  # covers every block of the relation, so index_size / block_size must equal
  # the page count pg_relation_size reports - which is the file a REINDEX
  # shrinks, and therefore the denominator the oracle measures against.
  printf -- '-- total_pages against the file: index_size / block_size vs pg_relation_size\n' >> "$OUT/facts12.txt"
  t "SELECT /* wiki_rs_denominator */ count(*) AS rows_read,
            count(*) FILTER (WHERE d.total_pages
                                   <> pg_relation_size(d.idx_oid)
                                      / current_setting('block_size')::bigint)
                AS total_pages_differs_from_the_file,
            count(*) FILTER (WHERE d.total_pages
                                   <> 1 + d.internal_pages + d.leaf_pages
                                        + d.empty_pages + d.deleted_pages)
                AS total_pages_differs_from_the_classes_plus_one
       FROM decide d" >> "$OUT/facts12.txt" 2>&1
  printf -- '-- the ceiling: (total_pages - 1 - internal_pages) / total_pages\n' >> "$OUT/facts12.txt"
  t "SELECT /* wiki_rs_ceiling */ count(*) AS finite_rows,
            count(*) FILTER (WHERE reindex_score
                                   > (total_pages - 1 - internal_pages)::float8
                                     / total_pages) AS above_ceiling,
            count(*) FILTER (WHERE total_pages <= 2 AND reindex_score >= 0.5)
                AS small_and_signalled
       FROM decide WHERE reindex_score <> 'NaN'::float8" >> "$OUT/facts12.txt" 2>&1
  printf -- '-- what pgstatindex refuses, one line per shape\n' >> "$OUT/facts12.txt"
  local shape
  for shape in "rs.i_hash" "rs.i_gin" "rs.i_gist" "rs.i_brin" "rs.i_part" \
               "rs.i_invalid" "rs.t_other" "rs.v_other" "rs.s_other" "rs.m_other"; do
    printf '%-14s %s\n' "$shape" "$(err "SELECT * FROM pgstatindex('$shape')")" \
      >> "$OUT/facts12.txt"
  done
  printf -- '-- and how many of them the candidate filter drops before the call\n' >> "$OUT/facts12.txt"
  t "SELECT /* wiki_rs_filtered */
            (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'rs' AND c.relkind IN ('i','I'))         AS rs_indexes,
            (SELECT count(*) FROM decide WHERE schema_name = 'rs')       AS rs_scored" \
    >> "$OUT/facts12.txt" 2>&1
  printf -- '-- the fillfactor the heuristic reads, against the one the index was built at\n' >> "$OUT/facts12.txt"
  t "SELECT /* wiki_rs_fillfactor */ d.index_name, d.fillfactor AS read_by_the_score,
            coalesce((SELECT o.option_value FROM pg_options_to_table(c.reloptions) o
                       WHERE o.option_name = 'fillfactor'), 'unset') AS reloption,
            round(d.avg_leaf_density::numeric, 2) AS density_as_built,
            round(100 * d.reindex_score::numeric, 2) AS score_pct
       FROM decide d JOIN pg_class c ON c.relname = d.index_name
      WHERE d.index_name IN ('i_fresh','i_ff100','i_ff50','i_ff10')
      ORDER BY d.fillfactor" >> "$OUT/facts12.txt" 2>&1
  cat "$OUT/facts12.txt" >&2
}

# ----------------------------------------------------------------- cost -----
# What it costs to ask.  pgstatindex reads every page of every index it is
# called on, so an automatic signal pays for the whole B-tree population each
# time it runs.  Three end-to-end runs, then one EXPLAIN (ANALYZE, BUFFERS).
# Not destructive, and it must precede the oracle like facts does.
stage_cost() {
  say "what the heuristic costs to run"
  {
    printf -- '-- the population it reads\n'
    t "SELECT /* wiki_rs_population_size */ count(*) AS btree_indexes,
              pg_size_pretty(sum(pg_relation_size(idx_oid))) AS total_index_bytes,
              sum(total_pages) AS total_pages
         FROM decide"
    printf -- '-- three end-to-end runs of the filed text, as filed\n'
    local i t0 t1
    for i in 1 2 3; do
      t0=$(date +%s%N)
      PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off \
        -d "$DB" -f "$SQLD/report.sql" > /dev/null 2>&1
      t1=$(date +%s%N)
      printf 'run_%s_ms=%s\n' "$i" "$(( (t1 - t0) / 1000000 ))"
    done
    printf -- '-- EXPLAIN (ANALYZE, BUFFERS) of the same text without its SET lines\n'
    PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" \
      -c "EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF) $(cat "$SQLD/bare.sql")" \
      2>&1 | grep -E 'Buffers|Execution Time|Planning Time|rows='
  } > "$OUT/cost12.txt" 2>&1
  cat "$OUT/cost12.txt" >&2
}

# ----------------------------------------------------------------- priv -----
# Who can run it.  pgstattuple 1.5 revokes EXECUTE on its functions from
# PUBLIC, so an automatic signal needs a role that has been granted it, or
# membership in pg_stat_scan_tables.  Both roles are dropped again at the end.
stage_priv() {
  say "the privileges an automatic signal would need"
  q "DROP OWNED BY rs_plain, rs_scan;" > /dev/null 2>&1
  q "DROP ROLE IF EXISTS rs_plain; DROP ROLE IF EXISTS rs_scan;" > /dev/null 2>&1
  q "CREATE ROLE rs_plain LOGIN; CREATE ROLE rs_scan LOGIN;
     GRANT pg_stat_scan_tables TO rs_scan;
     GRANT USAGE ON SCHEMA rs TO rs_plain, rs_scan;" > /dev/null \
    || die "creating the probe roles failed"
  # Each overload is called by name: an unadorned string literal resolves to
  # the text overload, while the filed statement passes an oid::regclass and
  # so calls the regclass one.
  {
    printf -- '-- pgstatindex, called by a role with no grant and by a pg_stat_scan_tables member,\n'
    printf -- '-- through the regclass overload the filed statement calls and through the text one\n'
    local r o
    for r in rs_plain rs_scan; do
      for o in regclass text; do
        printf '%-9s %-9s %s\n' "$r" "$o" "$(PGOPTIONS="$SESSION_OPTS" "$BIN/psql" -X -At -q -U "$r" \
          -d "$DB" -c "SELECT leaf_pages FROM pgstatindex('rs.i_fresh'::$o)" 2>&1 | head -1)"
      done
    done
    printf -- '-- the EXECUTE privileges pgstattuple ships with, per overload\n'
    t "SELECT /* wiki_rs_acl */ p.oid::regprocedure AS function, p.proacl
         FROM pg_proc p WHERE p.proname = 'pgstatindex' ORDER BY p.oid"
  } > "$OUT/priv12.txt" 2>&1
  # The schema grant is a dependency on the role, so it goes first: a bare
  # DROP ROLE would fail and leave both roles behind.
  q "DROP OWNED BY rs_plain, rs_scan;" > /dev/null || die "dropping the probe roles' grants failed"
  q "DROP ROLE rs_plain; DROP ROLE rs_scan;" > /dev/null || die "dropping the probe roles failed"
  cat "$OUT/priv12.txt" >&2
}

# ---------------------------------------------------------------- score -----
# Phase 5, the oracle: for every fixture in the plan, read what the heuristic
# said, call pgstatindex again from the harness, rebuild, and measure the file.
# Destructive: it rebuilds every scored index, so it runs once per build of the
# fixtures.  The suite stage installs res empty; a res that already holds rows
# means these fixtures were rebuilt, and scoring them again would measure a
# rebuild of a rebuild.  To score again, re-run every stage from suite onward.
stage_score() {
  say "the oracle: REINDEX INDEX on every scored fixture"
  [ -n "$(s 'SELECT 1 FROM decide LIMIT 1')" ] || die "no decide rows; run the decide stage first"
  [ "$(s 'SELECT count(*) FROM res')" = 0 ] \
    || die "the oracle has already rebuilt these fixtures; re-run the stages from suite onward to score again"
  q "CALL /* wiki_rs_score_all */ score_all();" > /dev/null || die "scoring failed"
  {
    t "SELECT /* wiki_rs_verdict_counts */ verdict, count(*) FROM verdicts
        GROUP BY verdict ORDER BY verdict"
    t "SELECT /* wiki_rs_verdict_by_family */ grp, count(*) AS fixtures,
              count(*) FILTER (WHERE verdict = 'PASS')                    AS pass,
              count(*) FILTER (WHERE verdict = 'CRITICAL FALSE POSITIVE') AS crit_fp,
              count(*) FILTER (WHERE verdict = 'FALSE POSITIVE')          AS fp,
              count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE')          AS fn
         FROM verdicts GROUP BY grp ORDER BY grp"
    t "SELECT /* wiki_rs_contract */
              count(*) FILTER (WHERE NOT contract_ok)            AS build_contract_failures,
              count(*) FILTER (WHERE NOT view_matches_report)    AS view_report_disagreements,
              count(*) FILTER (WHERE NOT signal_matches_report)  AS signal_disagreements,
              count(*) FILTER (WHERE taken_stage <> taken_nofilter) AS hidden_by_the_report,
              count(*) FILTER (WHERE taken_nofilter <> expected_stage) AS statement_vs_instrument,
              count(*) FILTER (WHERE shape_ok IS FALSE)          AS shape_failures,
              count(*) FILTER (WHERE want_stage <> taken_nofilter) AS want_stage_misses
         FROM verdicts"
    t "SELECT /* wiki_rs_want_misses */ num, idx, grp, want_stage, taken_nofilter,
              score_pct, actual, verdict
         FROM verdicts WHERE want_stage <> taken_nofilter ORDER BY num"
    # The concept page calls expected_stage mandatory, so the rows behind the
    # count are printed rather than left as a number: a statement that
    # disagrees with its own instrument has to be readable fixture by fixture.
    t "SELECT /* wiki_rs_instrument_misses */ num, idx, grp, score_pct,
              expected_stage, taken_nofilter, density, leaf_pages, dead_pages,
              total_pages
         FROM verdicts WHERE taken_nofilter <> expected_stage ORDER BY num"
    t "SELECT /* wiki_rs_bad_verdicts */ num, idx, grp, score_pct, actual, err,
              density, leaf_pages, dead_pages, total_pages, verdict
         FROM verdicts WHERE verdict <> 'PASS' ORDER BY verdict, num"
    t "SELECT /* wiki_rs_all_verdicts */ num, idx, grp, blocks_built, blocks_before,
              blocks_after, score_pct, actual, err, verdict, want_stage, shape
         FROM verdicts ORDER BY num, leg"
  } > "$OUT/verdicts12.txt" 2>&1
  head -30 "$OUT/verdicts12.txt" >&2
}

# ------------------------------------------------------------- accuracy -----
# The question this page asks: how close is REINDEX_SCORE to what a rebuild
# really gives back, and is >= 50 % the right place to cut?
stage_accuracy() {
  say "accuracy: the score against the measured rebuild"
  [ -n "$(s 'SELECT 1 FROM res LIMIT 1')" ] || die "no res rows; run the score stage first"
  {
    printf -- '-- the error of the score against the measured rebuild, in points\n'
    t "SELECT /* wiki_rs_error */ count(*) AS fixtures,
              round(avg(abs(err)), 2)                        AS mean_abs_err,
              round(percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(err))::numeric, 2)
                                                             AS median_abs_err,
              round(max(err), 1)                             AS worst_over,
              round(min(err), 1)                             AS worst_under,
              count(*) FILTER (WHERE abs(err) <= 1)          AS within_1_point,
              count(*) FILTER (WHERE abs(err) <= 5)          AS within_5_points,
              count(*) FILTER (WHERE abs(err) <= 10)         AS within_10_points,
              round(corr(score_pct::float8, actual::float8)::numeric, 4) AS correlation
         FROM verdicts WHERE score_pct IS NOT NULL AND score_pct <> 'NaN'::numeric"
    printf -- '-- the same, by family\n'
    t "SELECT /* wiki_rs_error_by_family */ grp, count(*) AS fixtures,
              round(avg(abs(err)), 2) AS mean_abs_err,
              round(max(err), 1) AS worst_over, round(min(err), 1) AS worst_under
         FROM verdicts WHERE score_pct IS NOT NULL AND score_pct <> 'NaN'::numeric
        GROUP BY grp ORDER BY grp"
    printf -- '-- the confusion matrix at the filed threshold of 50 %%\n'
    t "SELECT /* wiki_rs_confusion */
              count(*) FILTER (WHERE taken_nofilter = 'rebuild' AND actual >= 50) AS true_positive,
              count(*) FILTER (WHERE taken_nofilter = 'rebuild' AND actual <  50) AS false_positive_band,
              count(*) FILTER (WHERE taken_nofilter = 'leave'   AND actual <  50) AS true_negative,
              count(*) FILTER (WHERE taken_nofilter = 'leave'   AND actual >= 50) AS false_negative,
              count(*) AS fixtures
         FROM verdicts"
    printf -- '-- every fixture the signal and the oracle disagree about\n'
    t "SELECT /* wiki_rs_disagreements */ num, idx, grp, score_pct, actual, err,
              density, leaf_pages, dead_pages, total_pages, verdict
         FROM verdicts
        WHERE (taken_nofilter = 'rebuild') <> (actual >= 50)
        ORDER BY abs(err) DESC"
    # The sweep, scored two ways, because they answer different questions.
    # band_violations is the shared suite's own test: a threshold is acceptable
    # when no fixture lands in a false-positive or false-negative band, and
    # every threshold with a zero there is equally acceptable to the suite.
    # agrees_with_50 instead asks how often the signal matches a 50 % cut on
    # the measured rebuild, which is this page's own construct, not a band -
    # and because the score tracks the actual closely it necessarily peaks at
    # 50, so it measures calibration and may not be read as choosing 50.
    printf -- '-- what a different threshold would have cost, over the same fixtures\n'
    t "SELECT /* wiki_rs_sweep */ th AS threshold_pct,
              count(*) FILTER (WHERE score_pct >= th AND actual < 10) AS critical_false_pos,
              count(*) FILTER (WHERE score_pct >= th AND actual < 35) AS false_pos,
              count(*) FILTER (WHERE score_pct <  th AND actual >= 50) AS false_neg,
              count(*) FILTER (WHERE score_pct >= th AND actual < 35)
              + count(*) FILTER (WHERE score_pct < th AND actual >= 50)
                                                                      AS band_violations,
              count(*) FILTER (WHERE score_pct >= th) AS rebuilt,
              count(*) FILTER (WHERE (score_pct >= th) = (actual >= 50)) AS agrees_with_50
         FROM verdicts, generate_series(5, 95, 5) th
        GROUP BY th ORDER BY th"
    # Where the fixtures actually sit.  A threshold is band-clean when it is
    # above the score of every fixture whose rebuild returned under 35 % and at
    # or below the score of every fixture whose rebuild returned 50 % or more,
    # so the band-clean range is bounded by two scores, not by the gap between
    # the measured rebuilds: both edges, and the fixtures behind every
    # violation in the sweep, are printed after the histogram.
    printf -- '-- the measured rebuilds, bucketed, and the gap around the cut\n'
    t "SELECT /* wiki_rs_actual_histogram */ width_bucket(actual, 0, 100, 10) * 10 - 10
                AS actual_from_pct,
              count(*) AS fixtures, round(min(actual), 1) AS lowest,
              round(max(actual), 1) AS highest
         FROM verdicts GROUP BY 1 ORDER BY 1"
    t "SELECT /* wiki_rs_band_gap */
              round(max(actual) FILTER (WHERE actual < 50), 1)  AS highest_below_50,
              round(min(actual) FILTER (WHERE actual >= 50), 1) AS lowest_at_or_above_50,
              count(*) FILTER (WHERE actual >= 35 AND actual < 50) AS between_35_and_50,
              count(*) FILTER (WHERE actual >= 50 AND actual < 70) AS between_50_and_70
         FROM verdicts"
    printf -- '-- the two scores that bound the band-clean range, and the fixtures that hold them\n'
    t "SELECT /* wiki_rs_band_edges */ e.edge, v.idx, v.total_pages, v.score_pct,
              v.actual, v.err
         FROM (SELECT 'highest score, rebuild under 35 %' AS edge,
                      max(score_pct) AS score, false AS at_or_above
                 FROM verdicts WHERE actual < 35
               UNION ALL
               SELECT 'lowest score, rebuild 50 % or more',
                      min(score_pct), true
                 FROM verdicts WHERE actual >= 50) e
         JOIN verdicts v ON v.score_pct = e.score
                        AND (v.actual >= 50) = e.at_or_above
                        AND (e.at_or_above OR v.actual < 35)
        ORDER BY e.edge, v.idx"
    printf -- '-- the fixtures behind every band violation in the sweep, up to 80 %%\n'
    t "SELECT /* wiki_rs_sweep_rows */ th AS threshold_pct,
              CASE WHEN score_pct >= th AND actual < 10 THEN 'critical false positive'
                   WHEN score_pct >= th AND actual < 35 THEN 'false positive'
                   ELSE 'false negative' END AS band,
              count(*) AS fixtures,
              string_agg(idx || ' ' || score_pct || '/' || actual, ', ' ORDER BY idx)
                AS score_over_actual
         FROM verdicts, generate_series(5, 80, 5) th
        WHERE (score_pct >= th AND actual < 35) OR (score_pct < th AND actual >= 50)
        GROUP BY 1, 2 ORDER BY 1, 2"
    printf -- '-- the two denominators and the unguarded statement, side by side\n'
    t "SELECT /* wiki_rs_variants */
              count(*) AS fixtures,
              count(*) FILTER (WHERE verdict = 'PASS')       AS filed_pass,
              count(*) FILTER (WHERE verdict_nan = 'PASS')   AS unguarded_pass,
              count(*) FILTER (WHERE score_pct  >= 50)       AS filed_rebuilds,
              count(*) FILTER (WHERE nan_signal)             AS unguarded_rebuilds,
              count(*) FILTER (WHERE nan_pct = 'NaN'::numeric) AS unguarded_nan,
              count(*) FILTER (WHERE nometa_pct >= 50)       AS nometa_rebuilds,
              count(*) FILTER (WHERE nometa_pct IS NULL)     AS nometa_undefined,
              round(max(nometa_pct - score_pct), 2)          AS worst_nometa_gap
         FROM verdicts"
    printf -- '-- the fixtures where the three readings do not agree\n'
    t "SELECT /* wiki_rs_variant_rows */ num, idx, total_pages, leaf_pages,
              score_pct, nometa_pct, nan_pct, actual
         FROM verdicts
        WHERE (score_pct >= 50) IS DISTINCT FROM (nometa_pct >= 50)
           OR (score_pct >= 50) IS DISTINCT FROM nan_signal
        ORDER BY num"
    # The error, split into the three terms it is made of.  The identity is
    # exact: err = leaf_term + internal_term + dead_term, so a fixture's error
    # is attributable rather than narrated.  leaf_term is what the leaf model
    # itself got wrong, which on a small index is mostly the whole page a
    # rebuild cannot avoid writing; where a rebuild writes back as many leaves
    # as it found, leaf_term is the score's own leaf component and cannot be
    # negative.  internal_term is the levels above the leaf level, which the
    # numerator never models, so its sign is whatever the rebuild did to them:
    # both directions are counted here, from the page counts, not assumed.
    printf -- '-- the error decomposed: leaf model, internal levels, dead pages left\n'
    t "SELECT /* wiki_rs_decomposition */ count(*) AS fixtures,
              round(avg(leaf_term), 2)     AS mean_leaf_term,
              round(avg(internal_term), 2) AS mean_internal_term,
              round(avg(dead_term), 2)     AS mean_dead_term,
              round(max(abs(err - (leaf_term + internal_term + dead_term))), 1)
                                           AS worst_residual,
              count(*) FILTER (WHERE aft_internal < internal_pages) AS shrank_internal_levels,
              count(*) FILTER (WHERE aft_internal > internal_pages) AS grew_internal_levels,
              count(*) FILTER (WHERE aft_leaf > leaf_pages)         AS grew_leaf_levels,
              count(*) FILTER (WHERE dead_term <> 0)    AS kept_dead_pages
         FROM verdicts"
    printf -- '-- the leaf term where the rebuild wrote back as many leaves as it found\n'
    t "SELECT /* wiki_rs_leaf_term_same_leaves */ count(*) AS fixtures,
              count(*) FILTER (WHERE leaf_term > 0) AS over,
              count(*) FILTER (WHERE leaf_term = 0) AS exact,
              count(*) FILTER (WHERE leaf_term < 0) AS under,
              max(leaf_term) AS largest
         FROM verdicts WHERE aft_leaf = leaf_pages"
    printf -- '-- the same, for every fixture whose error exceeds one point\n'
    t "SELECT /* wiki_rs_decomposition_rows */ num, idx, grp, total_pages,
              internal_pages, leaf_pages, density, aft_internal, aft_leaf,
              score_pct, actual, err, leaf_term, internal_term, dead_term
         FROM verdicts WHERE abs(err) > 1 ORDER BY err"
    printf -- '-- family 3 as built: the page classes a rebuild of each fresh index wrote back\n'
    t "SELECT /* wiki_rs_family3 */ num, idx, total_pages, internal_pages, leaf_pages,
              round(density::numeric, 2) AS density, fillfactor, aft_internal,
              aft_leaf, score_pct, actual, err
         FROM verdicts WHERE grp = 'falsepos' ORDER BY num"
    # The headline both ways.  Test 120 is the suite's one probabilistic
    # fixture: its precondition is a sample miss, so it is scored on some runs
    # and not others, and any statistic that includes it moves between runs.
    # Both populations are printed so the page can report the stable one and
    # name what the other adds.
    printf -- '-- the headline over the deterministic fixtures, and with p120 included\n'
    t "SELECT /* wiki_rs_headline */ scope, count(*) AS fixtures,
              round(avg(abs(err)), 2) AS mean_abs_err,
              round(percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(err))::numeric, 2)
                                      AS median_abs_err,
              round(max(err), 1) AS worst_over, round(min(err), 1) AS worst_under,
              round(corr(score_pct::float8, actual::float8)::numeric, 4) AS correlation
         FROM (SELECT v.*, 'all scored'  AS scope FROM verdicts v
               UNION ALL
               SELECT v.*, 'without p120' AS scope FROM verdicts v WHERE v.num <> 120) z
        GROUP BY scope ORDER BY scope"
    printf -- '-- the ten largest over-estimates and the ten largest under-estimates\n'
    t "SELECT /* wiki_rs_worst_over */ num, idx, grp, score_pct, actual, err, density,
              leaf_pages, dead_pages
         FROM verdicts WHERE err IS NOT NULL ORDER BY err DESC LIMIT 10"
    t "SELECT /* wiki_rs_worst_under */ num, idx, grp, score_pct, actual, err, density,
              leaf_pages, dead_pages
         FROM verdicts WHERE err IS NOT NULL ORDER BY err ASC LIMIT 10"
  } > "$OUT/accuracy12.txt" 2>&1
  cat "$OUT/accuracy12.txt" >&2
}

# ---------------------------------------------------------------- guard -----
# The same oracle over schema rs: one REINDEX INDEX per guard fixture, the file
# measured before and after.  No verdict band is applied, because these are not
# suite fixtures.  Destructive, so it runs once per build of schema rs: the
# fixtures stage drops guard_res with the fixtures, and a guard_res that is
# still here means these fixtures were already rebuilt.  To run it again, re-run
# fixtures, report and decide first.
stage_guard() {
  say "the oracle over the guard fixtures in schema rs"
  [ -z "$(s "SELECT to_regclass('public.guard_res')")" ] \
    || die "the guard oracle has already rebuilt schema rs; re-run fixtures, report and decide first"
  q "CREATE /* wiki_rs_guard_res */ TABLE guard_res(idx text PRIMARY KEY,
       score_pct numeric, signal bool, before_bytes bigint, after_bytes bigint,
       density numeric, leaf_pages int, dead_pages int, total_pages bigint);" > /dev/null
  q "DO /* wiki_rs_guard_oracle */ \$g\$
     DECLARE r record; sb bigint; sa bigint;
     BEGIN
       FOR r IN SELECT d.* FROM decide d WHERE d.schema_name = 'rs' ORDER BY d.index_name LOOP
         sb := pg_relation_size(('rs.' || quote_ident(r.index_name))::regclass);
         EXECUTE format('REINDEX INDEX rs.%I', r.index_name);
         sa := pg_relation_size(('rs.' || quote_ident(r.index_name))::regclass);
         INSERT INTO guard_res VALUES (r.index_name,
           round(100 * r.reindex_score::numeric, 1), r.reindex_score >= 0.5,
           sb, sa, CASE WHEN r.leaf_pages > 0
                        THEN round(r.avg_leaf_density::numeric, 2) END,
           r.leaf_pages, r.empty_pages + r.deleted_pages, r.total_pages);
       END LOOP;
     END \$g\$;" > /dev/null || die "guard oracle failed"
  t "SELECT /* wiki_rs_guard_report */ idx, total_pages, leaf_pages, dead_pages,
            density, score_pct, signal, before_bytes, after_bytes,
            round(100.0 * (before_bytes - after_bytes) / greatest(before_bytes, 1), 1)
                AS actual
       FROM guard_res ORDER BY idx" > "$OUT/guard12.txt" 2>&1
  cat "$OUT/guard12.txt" >&2
}

# --------------------------------------------------------------- errors -----
stage_errors() {
  say "errors the server logged during this run"
  local log="$OUT/server12.log" from
  [ -f "$log" ] || { note "no server log"; return 0; }
  from=$(grep -n 'wiki_rs_run_mark' "$log" | tail -1 | cut -d: -f1)
  [ -n "${from:-}" ] || from=1
  sed -n "${from},\$p" "$log" | grep -E '(ERROR|FATAL|PANIC)' > "$OUT/errors12.txt"
  {
    printf 'logged_error_lines=%s\n' "$(grep -c '' "$OUT/errors12.txt")"
    printf -- '-- distinct messages\n'
    sed -E 's/.*(ERROR|FATAL|PANIC)/\1/' "$OUT/errors12.txt" | sort | uniq -c | sort -rn
  } > "$OUT/errors12_summary.txt"
  cat "$OUT/errors12_summary.txt" >&2
}

# ------------------------------------------------------------- crossleg -----
# The one comparison neither leg can make from its own server: the two legs'
# scores side by side.  Both legs write their psql output into the shared out/,
# so this stage is pure text and needs no connection.  Fields 1 and 2 are
# schema_name and index_name, and that pair is unique inside each database, so
# it is the join key.  It runs last, because it needs the 17 leg's report stage
# to have written its file.
stage_crossleg() {
  say "the two majors' scores, side by side"
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
    # Field 12 is reindex_score_pct and field 13 is reindex_signal: the two
    # numbers this page is about, per shared key, on each major.
    printf -- '-- shared keys whose rows differ: key, score 17, score 12, signal 17, signal 12\n'
    # The two scores are compared at the precision the report prints them at.
    # reindex_score_pct is round(..., 1), so each value is an integer number of
    # tenths once the decimal point is removed, and comparing those integers is
    # an exact comparison of what the reader sees.  Comparing ${p%%.*} instead
    # would compare integer parts and call 49.6 and 49.1 the same score.
    local k p17 p12 s17 s12 a b higher=0 lower=0 same=0 sigdiff=0
    while IFS= read -r k; do
      p17=$(grep -m1 -F "$k|" "$SQLD/x17_rows.txt" | cut -d'|' -f12)
      p12=$(grep -m1 -F "$k|" "$SQLD/x12_rows.txt" | cut -d'|' -f12)
      s17=$(grep -m1 -F "$k|" "$SQLD/x17_rows.txt" | cut -d'|' -f13)
      s12=$(grep -m1 -F "$k|" "$SQLD/x12_rows.txt" | cut -d'|' -f13)
      printf '%s|%s|%s|%s|%s\n' "$k" "$p17" "$p12" "$s17" "$s12"
      [ "$s17" = "$s12" ] || sigdiff=$((sigdiff + 1))
      case "$p17|$p12" in
        NaN*|*\|NaN) same=$((same + 1)) ;;
        *) a=$((10#${p17/./})); b=$((10#${p12/./}))
           if   [ "$a" -gt "$b" ]; then higher=$((higher + 1))
           elif [ "$a" -lt "$b" ]; then lower=$((lower + 1))
           else same=$((same + 1)); fi ;;
      esac
    done < "$SQLD/x_diff_keys.txt"
    printf 'differing_rows_scoring_higher_on_17=%s\n' "$higher"
    printf 'differing_rows_scoring_lower_on_17=%s\n' "$lower"
    printf 'differing_rows_scoring_the_same=%s\n' "$same"
    printf 'differing_rows_whose_signal_differs=%s\n' "$sigdiff"
    # Which kind of object the differing rows are: the system catalogs'
    # indexes, TOAST indexes, or objects this run created in public and rs.
    printf -- '-- shared keys whose rows differ, by schema\n'
    cut -d'|' -f1 "$SQLD/x_diff_keys.txt" | LC_ALL=C sort | uniq -c
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
  for x in platform12 checks12 exact12 decide12 maint_proofs12 cost12 priv12 accuracy12 crossleg errors12_summary; do
    [ -f "$OUT/$x.txt" ] && { printf -- '-- %s\n' "$x" >&2; cat "$OUT/$x.txt" >&2; }
  done
  return 0
}

# ---------------------------------------------------------------- stop -------
# stop runs sandbox_guard before it stops anything, so it can only ever stop the
# cluster this script started inside its own marked sandbox.
stage_stop() {
  say "stop the 12 cluster"
  [ -d "$SANDBOX" ] || { note "no sandbox at $SANDBOX"; return 0; }
  sandbox_guard
  [ -d "$DATA" ] || { note "no data directory"; return 0; }
  "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1
  [ -f "$DATA/postmaster.pid" ] && die "postmaster.pid still present in $DATA"
  pgrep -f "postgres.*$DATA" > /dev/null 2>&1 && die "a postgres process still runs on $DATA"
  [ -n "$(ls -A "$SOCK" 2>/dev/null)" ] && die "socket directory $SOCK is not empty"
  note "stopped: no postmaster.pid, no process, empty socket directory"
}

# This leg deletes only its own five directories, inside the resolved path
# sandbox_guard approved; the 17 leg owns the shared out/ and removes the
# sandbox itself, and its clean refuses to run while this leg's data directory
# is still there.
stage_clean() {
  [ -d "$SANDBOX" ] || { note "no sandbox at $SANDBOX, nothing to delete"; return 0; }
  sandbox_guard
  stage_stop
  say "delete this leg's directories under $SANDBOX_REAL"
  rm -rf "$SANDBOX_REAL/build12" "$SANDBOX_REAL/install12" "$SANDBOX_REAL/data12" \
         "$SANDBOX_REAL/sock12" "$SANDBOX_REAL/sql12"
}

# ------------------------------------------------------------ dispatcher -----
STAGES_DEFAULT="build check cluster texts fixtures suite churn report decide facts cost priv score accuracy guard errors crossleg summary"
run_stage() {
  case "$1" in
    build|check|cluster|texts|fixtures|suite|churn|report|decide|facts|cost|priv|score|accuracy|guard|errors|crossleg|summary|stop|clean)
      "stage_$1" ;;
    *) die "unknown stage: $1" ;;
  esac
}

# A run that asks for any stage but stop and clean needs a sandbox, and
# make_sandbox() checks where it is before it creates or marks anything.  A
# run of stop or clean alone creates nothing.
main() {
  local stages="$*" st needs=0
  [ -n "$stages" ] || stages="$STAGES_DEFAULT"
  for st in $stages; do
    case "$st" in stop|clean) ;; *) needs=1 ;; esac
  done
  [ "$needs" = 1 ] && make_sandbox
  for st in $stages; do run_stage "$st" || die "stage $st failed"; done
  say "done: $stages"
}

main "$@"
```

### The shared suite's harness

```sql
-- The shared mandatory suite's harness for the REINDEX_SCORE heuristic.  It is
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
SET /* wiki_rs_harness_client_min_messages */ client_min_messages = warning;
SET /* wiki_rs_harness_statement_timeout */ statement_timeout = '900s';
SET /* wiki_rs_harness_lock_timeout */ lock_timeout = '5s';

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

-- Phases 4 and 5, one row per fixture: what the heuristic said about the
-- churned file, what pgstatindex says when the harness calls it itself, and
-- what the rebuild then gave back.  score is kept as float8 rather than
-- numeric because the NaN the formula can produce is the point: it has to
-- survive into the comparison the verdict bands make.
-- The aft_* columns are the same ten pgstatindex columns read again after the
-- oracle's REINDEX.  They are what turns the error into an identity rather
-- than a narrative: err * total_pages is exactly
--   (aft_leaf - leaf * LEAST(1, density / fillfactor))  the leaf model's error
-- + (aft_internal - internal)                           the levels it omits
-- + (aft_empty + aft_deleted)                           dead pages kept
-- so every point of every fixture's error lands in one of three named terms.
CREATE TABLE res(num int, leg text, req text, idx text,
                 size_before bigint, size_after bigint,
                 blocks_before int, blocks_after int,
                 reported bool, score float8, score_pct numeric,
                 rep_score_pct numeric, rep_signal bool, signal bool,
                 total_pages bigint,
                 raw_size bigint, raw_internal int, raw_leaf int,
                 raw_empty int, raw_deleted int,
                 raw_density float8, raw_frag float8, fillfactor int,
                 aft_size bigint, aft_internal int, aft_leaf int,
                 aft_empty int, aft_deleted int, aft_density float8,
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
-- filed text itself printed, which is where rep_score_pct and rep_signal come
-- from.  The raw pgstatindex call below is the harness reading the instrument
-- itself, so the verdict view can recompute REINDEX_SCORE independently of the
-- statement's own CTE chain.  The REINDEX is the only oracle, and it runs
-- after both readings.
CREATE OR REPLACE PROCEDURE score_all() LANGUAGE plpgsql AS $sc$
DECLARE p record; d record; x record; y record; sb bigint; sa bigint;
        tr bigint; rep record;
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
    -- The rebuilt file's own page classes, which is what the error
    -- decomposition on the res table above is computed from.
    SELECT * INTO y FROM pgstatindex(p.idx::regclass);
    INSERT INTO res VALUES (p.num, p.leg, p.req, p.idx, sb, sa,
      (sb / current_setting('block_size')::int)::int,
      (sa / current_setting('block_size')::int)::int,
      rep.index_name IS NOT NULL,
      d.reindex_score, round(100 * d.reindex_score::numeric, 1),
      rep.reindex_score_pct, rep.reindex_signal,
      d.reindex_score >= 0.5, d.total_pages,
      x.index_size, x.internal_pages, x.leaf_pages, x.empty_pages,
      x.deleted_pages, x.avg_leaf_density, x.leaf_fragmentation,
      d.fillfactor,
      y.index_size, y.internal_pages, y.leaf_pages, y.empty_pages,
      y.deleted_pages, y.avg_leaf_density,
      tr, p.want_rows, p.note);
  END LOOP;
END $sc$;

-- The verdict view.  actual is what the rebuild of the churned file really
-- gave back and is the only oracle; verdict applies the shared suite's four
-- bands to it.  taken_stage is the decision a reader takes from the filed
-- statement's own output: a fixture the statement never prints is a 'leave'
-- whatever its arithmetic says.  taken_nofilter is the same threshold applied
-- to every index whether the report printed it or not, so the two columns
-- coincide exactly when the statement hides nothing, and they are kept side by
-- side as the check on that.  expected_stage recomputes REINDEX_SCORE from the
-- harness's own pgstatindex call, guards included, so a statement that
-- disagrees with its own instrument is visible.  It tracks the filed text: if
-- the statement's guards change, this recomputation changes with them, or the
-- check silently reports the difference between two formulas instead.
--
-- The 50 % threshold here is the heuristic's own - the signal the question
-- proposes.  The suite's FALSE NEGATIVE band happens to sit at the same 50 %;
-- they are different numbers with the same value, one the method's threshold
-- and one the band's.
--
-- Two further readings are computed beside the filed one, because the formula
-- does not say which denominator is meant and because the page reports what
-- the guards bought:
--   score_meta     total_pages = index_size / block_size, the filed reading
--   score_nometa   total_pages = internal + leaf + empty + deleted, which is
--                  the same count without the metapage, and is 0 for an index
--                  that holds only a metapage, so it is division by zero there
--   score_nan      the filed reading with both CASE guards removed, which is
--                  the statement as it stood before them.  It is what the
--                  page's "before" column reports, computed in the same run as
--                  the "after" column rather than quoted from an earlier one.
CREATE VIEW verdicts AS
SELECT r.num, r.leg, p.grp, r.idx, r.req,
       s.blocks AS blocks_built, r.blocks_before, r.blocks_after, a.actual,
       r.score_pct, v.nometa_pct, v.nan_pct,
       round((r.score_pct - a.actual), 1)                       AS err,
       -- The error decomposition, in points, exact by construction:
       -- err = leaf_term + internal_term + dead_term, to the rounding of each.
       -- The leaf term carries the statement's own floor.  GREATEST(0, 1 - d/ff)
       -- is 1 - LEAST(1, d/ff), so the leaf count the statement predicts is
       -- leaf * LEAST(1, d/ff): an index already denser than its fillfactor is
       -- predicted to keep every leaf it has, not to grow.  Dropping the floor
       -- here would charge such a fixture an error the statement never made.
       round(100 * (r.aft_leaf - r.raw_leaf
                    * LEAST(1::float8,
                            CASE WHEN r.raw_density = 'NaN'::float8 THEN 0::float8
                                 ELSE r.raw_density END / r.fillfactor))::numeric
             / r.total_pages, 1)                                AS leaf_term,
       round(100 * (r.aft_internal - r.raw_internal)::numeric
             / r.total_pages, 1)                                AS internal_term,
       round(100 * (r.aft_empty + r.aft_deleted)::numeric
             / r.total_pages, 1)                                AS dead_term,
       r.aft_internal, r.aft_leaf, r.aft_density,
       r.raw_density AS density,
       r.raw_empty + r.raw_deleted AS dead_pages, r.raw_leaf AS leaf_pages,
       r.raw_internal AS internal_pages,
       r.total_pages, r.reported, d.taken_stage, d.taken_nofilter,
       x.expected_stage, p.want_stage,
       CASE WHEN d.taken_stage = 'rebuild' AND a.actual < 10  THEN 'CRITICAL FALSE POSITIVE'
            WHEN d.taken_stage = 'rebuild' AND a.actual < 35  THEN 'FALSE POSITIVE'
            WHEN d.taken_stage = 'leave'   AND a.actual >= 50 THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END                                   AS verdict,
       CASE WHEN d.taken_nofilter = 'rebuild' AND a.actual < 10  THEN 'CRITICAL FALSE POSITIVE'
            WHEN d.taken_nofilter = 'rebuild' AND a.actual < 35  THEN 'FALSE POSITIVE'
            WHEN d.taken_nofilter = 'leave'   AND a.actual >= 50 THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END                                   AS verdict_nofilter,
       CASE WHEN v.nan_signal AND a.actual < 10  THEN 'CRITICAL FALSE POSITIVE'
            WHEN v.nan_signal AND a.actual < 35  THEN 'FALSE POSITIVE'
            WHEN NOT v.nan_signal AND a.actual >= 50 THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END                                   AS verdict_nan,
       v.nan_signal,
       CASE WHEN d.taken_stage = 'leave' AND a.actual >= 50
            THEN CASE WHEN r.score IS NULL     THEN 'unmeasured'
                      WHEN NOT r.reported      THEN 'not printed'
                      ELSE 'threshold' END END                AS lost_by,
       -- The filed text and the harness view must agree wherever the filed
       -- text prints a row at all; the view differs from it in its
       -- presentation SELECT only.
       (NOT r.reported OR r.score_pct IS NOT DISTINCT FROM r.rep_score_pct)
                                                               AS view_matches_report,
       (NOT r.reported OR r.signal IS NOT DISTINCT FROM r.rep_signal)
                                                               AS signal_matches_report,
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
       r.raw_frag AS leaf_fragmentation, r.note
  FROM res r
  JOIN plan p ON p.num = r.num AND p.leg = r.leg
  LEFT JOIN snap s ON s.phase = 'built'   AND s.idx = r.idx
  LEFT JOIN snap c ON c.phase = 'churned' AND c.idx = r.idx
  CROSS JOIN LATERAL (
        SELECT round(100.0 * (r.size_before - r.size_after)
                     / greatest(r.size_before, 1), 1) AS actual) a
  CROSS JOIN LATERAL (
        SELECT CASE WHEN r.reported AND r.score >= 0.5
                    THEN 'rebuild' ELSE 'leave' END AS taken_stage,
               CASE WHEN r.score >= 0.5
                    THEN 'rebuild' ELSE 'leave' END AS taken_nofilter) d
  -- The shape test's own geometry: leaf capacity is
  -- block_size - SizeOfPageHeaderData - MAXALIGN(sizeof(BTPageOpaqueData)) and
  -- the target free space is block_size * (100 - fillfactor) / 100.  dens is
  -- guarded here because this is the harness's own reading, not the
  -- heuristic's.
  CROSS JOIN LATERAL (
        SELECT current_setting('block_size')::numeric AS bs) b
  CROSS JOIN LATERAL (
        SELECT b.bs - 24 - 16                                     AS leaf_cap,
               (b.bs * (100 - r.fillfactor)) / 100                AS target_free,
               CASE WHEN r.raw_leaf > 0 AND r.raw_density <> 'NaN'::float8
                    THEN (r.raw_density / 100)::numeric ELSE 0 END AS dens) g
  -- expected_stage: REINDEX_SCORE recomputed from the ten columns pgstatindex
  -- returned to the harness, exactly as the filed text computes it, both CASE
  -- guards included.  gd is the filed text's inner guard and the outer CASE is
  -- applied to the quotient, so a difference between this column and the
  -- statement's own verdict is a difference in the data, not in the formula.
  CROSS JOIN LATERAL (
        SELECT CASE WHEN r.raw_density = 'NaN'::float8 THEN 0::float8
                    ELSE r.raw_density END                        AS gd) e
  CROSS JOIN LATERAL (
        SELECT (r.raw_deleted + r.raw_empty
                + r.raw_leaf * GREATEST(0::float8,
                                        1 - e.gd / r.fillfactor))
               / (r.raw_size / b.bs::bigint)::float8              AS raw_exp) h0
  CROSS JOIN LATERAL (
        SELECT CASE WHEN h0.raw_exp = 'NaN'::float8 THEN 0::float8
                    ELSE h0.raw_exp END                           AS exp_score) h
  CROSS JOIN LATERAL (
        SELECT CASE WHEN h.exp_score >= 0.5 THEN 'rebuild' ELSE 'leave' END
                                                                  AS expected_stage) x
  -- The two variant readings.  The no-metapage denominator is NULL rather than
  -- zero for an index that holds only a metapage, because that is the one row
  -- where the variant is undefined and the point is to count it, not to kill
  -- the run; the facts stage reads what the bare division does instead.
  CROSS JOIN LATERAL (
        SELECT round((100 * (r.raw_deleted + r.raw_empty
                     + r.raw_leaf * GREATEST(0::float8,
                                             1 - r.raw_density / r.fillfactor))
               / NULLIF(r.raw_internal + r.raw_leaf + r.raw_empty
                        + r.raw_deleted, 0)::float8)::numeric, 1) AS nometa_pct,
               round((100 * (r.raw_deleted + r.raw_empty
                     + r.raw_leaf * GREATEST(0::float8,
                                             1 - r.raw_density / r.fillfactor))
               / (r.raw_size / b.bs::bigint)::float8)::numeric, 1) AS nan_pct,
               ((r.raw_deleted + r.raw_empty
                 + r.raw_leaf * GREATEST(0::float8,
                                         1 - r.raw_density / r.fillfactor))
                / (r.raw_size / b.bs::bigint)::float8) >= 0.5      AS nan_signal) v;
```

### Family 1, the deduplication gate

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
SET /* wiki_rs_gate_client_min_messages */ client_min_messages = warning;
SET /* wiki_rs_gate_statement_timeout */ statement_timeout = '900s';
SET /* wiki_rs_gate_lock_timeout */ lock_timeout = '5s';
SET /* wiki_rs_gate_maintenance_work_mem */ maintenance_work_mem = '256MB';

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
SELECT /* wiki_rs_gate_collations */ 'cdet: ' ||
       coalesce(try_ddl($c$CREATE COLLATION cdet (provider = icu, locale = 'und')$c$), 'created')
       AS icu_deterministic,
       'ci: ' ||
       coalesce(try_ddl($c$CREATE COLLATION ci (provider = icu, locale = 'und-u-ks-level2', deterministic = false)$c$), 'created')
       AS icu_nondeterministic;

-- The callbacks tests 12 to 16 register as B-tree support function 4.  The two
-- LANGUAGE internal aliases exist only where the engine has the builtins, so
-- both are attempted rather than assumed.
SELECT /* wiki_rs_gate_callbacks */
       coalesce(try_ddl($c$CREATE OR REPLACE FUNCTION ei_true(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS 'SELECT true'$c$), 'ok') AS ei_true,
       coalesce(try_ddl($c$CREATE OR REPLACE FUNCTION ei_false(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS 'SELECT false'$c$), 'ok') AS ei_false,
       coalesce(try_ddl($c$CREATE OR REPLACE FUNCTION ei_alias(oid) RETURNS bool LANGUAGE internal IMMUTABLE AS 'btequalimage'$c$), 'ok') AS ei_alias,
       coalesce(try_ddl($c$CREATE OR REPLACE FUNCTION public.btequalimage(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS 'SELECT true'$c$), 'ok') AS impostor,
       coalesce(try_ddl($c$CREATE OR REPLACE FUNCTION ei_renamed(oid) RETURNS bool LANGUAGE internal IMMUTABLE AS 'btvarstrequalimage'$c$), 'ok') AS renamed_builtin;

-- The eight operator classes.  int4_ei_none declares no FUNCTION 4 at all and
-- is therefore constructible on every major; the other seven are not.
SELECT /* wiki_rs_gate_opclasses */ name,
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
SELECT /* wiki_rs_gate_pattern */
       coalesce(try_ddl('CREATE INDEX i_pattern_nondet ON t (s COLLATE ci text_pattern_ops)'),
                'UNEXPECTED: the build was accepted') AS text_pattern_ops_nondeterministic;

-- Every gate fixture is a shape fixture, so rule 2 drains all of them and
-- every prediction is a rebuild: a 500,000-entry index that keeps one heap
-- block in ten cannot stay dense whatever its keys are.
UPDATE /* wiki_rs_gate_families */ plan
   SET grp = 'gate', want_stage = 'rebuild'
 WHERE num <= 17;
SELECT /* wiki_rs_gate_counts */
       (SELECT count(*) FROM plan WHERE grp = 'gate')      AS gate_fixtures,
       (SELECT count(*) FROM skipped WHERE num <= 17)      AS gate_skipped,
       (SELECT count(*) FROM snap WHERE phase = 'built')   AS baselines_taken;
SELECT /* wiki_rs_gate_skips */ num, idx, reason FROM skipped WHERE num <= 17 ORDER BY num, idx;
```

### Families 2 to 6, tests 18 to 120

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
SET /* wiki_rs_suite_client_min_messages */ client_min_messages = warning;
SET /* wiki_rs_suite_statement_timeout */ statement_timeout = 0;
SET /* wiki_rs_suite_lock_timeout */ lock_timeout = 0;
SET /* wiki_rs_suite_idle_timeout */ idle_in_transaction_session_timeout = 0;
SET /* wiki_rs_suite_maintenance_work_mem */ maintenance_work_mem = '256MB';

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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) pc64;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) pc66;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) pc68;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) pb72;
SELECT maint_end('pb72');
SELECT plan_add(72, '25% of the subset deleted', 'p72', 'SELECT count(*) FROM pb72 WHERE hot', 75000);

CREATE TABLE pb73 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb73; SELECT wiki_flush();
CREATE INDEX p73 ON pb73 (k) WHERE hot;
DELETE FROM pb73 WHERE hot AND (k / 5) % 2 = 0;
SELECT maint_begin('pb73');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) pb73;
SELECT maint_end('pb73');
SELECT plan_add(73, '50% of the subset deleted', 'p73', 'SELECT count(*) FROM pb73 WHERE hot', 50000);

CREATE TABLE pb74 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb74; SELECT wiki_flush();
CREATE INDEX p74 ON pb74 (k) WHERE hot;
DELETE FROM pb74 WHERE hot AND (k / 5) % 4 <> 0;
SELECT maint_begin('pb74');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) pb74;
SELECT maint_end('pb74');
SELECT plan_add(74, '75% of the subset deleted', 'p74', 'SELECT count(*) FROM pb74 WHERE hot', 25000);

-- 75 is the corrected recipe: 90% of the subset, not the whole of it.
CREATE TABLE pb75 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb75; SELECT wiki_flush();
CREATE INDEX p75 ON pb75 (k) WHERE hot;
DELETE FROM pb75 WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('pb75');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) pb75;
SELECT maint_end('pb75');
SELECT plan_add(75, '90% of the subset deleted (corrected recipe)', 'p75',
                'SELECT count(*) FROM pb75 WHERE hot', 10000);

CREATE TABLE pb76 AS SELECT (i % 5 = 0) AS hot, i::int AS k, 'x'::text AS pad
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb76; SELECT wiki_flush();
CREATE INDEX p76 ON pb76 (k) WHERE hot;
UPDATE pb76 SET k = k + 1000000 WHERE hot;
SELECT maint_begin('pb76');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) pb76;
SELECT maint_end('pb76');
SELECT plan_add(76, 'bloated through indexed-key UPDATEs', 'p76',
                'SELECT count(*) FROM pb76 WHERE hot', 100000);

CREATE TABLE pb77 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE pb77; SELECT wiki_flush();
CREATE INDEX p77 ON pb77 (k) WHERE hot;
DELETE FROM pb77 WHERE hot AND k < 475000;          -- contiguous 95%
SELECT maint_begin('pb77');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) pb77;
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
VACUUM /* wiki_rs_maint */ (VERBOSE) f85t;   -- no ANALYZE: that is the fixture
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) f86t;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) f87t;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) f88t;
SELECT maint_end('f88t');
SELECT plan_add(88, 'subset narrower than table statistics', 'f88', NULL, NULL);

CREATE TABLE f89t AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f89t; SELECT wiki_flush();
CREATE INDEX f89 ON f89t (a, b) WHERE hot;
DELETE FROM f89t WHERE hot AND a >= 25;
SELECT maint_begin('f89t');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) f89t;
SELECT maint_end('f89t');
SELECT plan_add(89, 'conditional multi-column correlation', 'f89',
                'SELECT count(*) FROM f89t WHERE hot', 25000);

CREATE TABLE f90t AS SELECT (i % 5 = 0) AS hot, ((i / 5) % 1000)::int AS k
  FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE f90t; SELECT wiki_flush();
CREATE INDEX f90 ON f90t (k) WHERE hot;
DELETE FROM f90t WHERE hot AND k >= 250;
SELECT maint_begin('f90t');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) f90t;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) f91t;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) b92t;
SELECT maint_end('b92t');
UPDATE b92t SET k = k WHERE k % 500 = 0;              -- 1,000 rows changed
SELECT maint_begin('b92t');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) b92t;
SELECT maint_end('b92t');
SELECT plan_add(92, '1,000 rows updated under the GUC threshold', 'b92',
                'SELECT count(*) FROM b92t WHERE hot', 10000);

CREATE TABLE b93t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT wiki_flush(); ANALYZE b93t; SELECT wiki_flush();
CREATE INDEX b93 ON b93t (k) WHERE hot;
DELETE FROM b93t WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('b93t');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) b93t;
SELECT maint_end('b93t');
UPDATE b93t SET k = k WHERE k % 2 = 0;                -- above the trigger
SELECT maint_begin('b93t');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) b93t;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) b94t;
SELECT maint_end('b94t');
UPDATE b94t SET k = k WHERE k % 500 = 0;              -- 1,000 > the reloption
SELECT maint_begin('b94t');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) b94t;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) b95t;
SELECT maint_end('b95t');
UPDATE b95t SET k = k WHERE k % 2 = 0;                -- below the reloption
SELECT maint_begin('b95t');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) b95t;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) np98t;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) np99t;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) i100t;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) x107t;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) q113b;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) q114;
SELECT maint_end('q114');
SELECT plan_add(114, 'queue drained to 1%, VACUUM + ANALYZE', 'p114',
                'SELECT count(*) FROM q114 WHERE state = ''pending''', 10000);

-- 115: index built on an analysed empty table, then loaded.
CREATE TABLE q115(id int, state text);
SELECT wiki_flush(); ANALYZE q115; SELECT wiki_flush();
CREATE INDEX p115 ON q115 (id) WHERE state = 'pending';
INSERT INTO q115 SELECT i, 'pending' FROM generate_series(1, 1000000) i;
SELECT maint_begin('q115');
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) q115;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) q118;
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
VACUUM /* wiki_rs_maint */ (VERBOSE, ANALYZE) q119;
SELECT maint_end('q119');
ANALYZE q119; SELECT wiki_flush();                    -- the one more ANALYZE
SELECT plan_add(119, 'fixture 118 after one more ANALYZE', 'p119',
                'SELECT count(*) FROM q119 WHERE state = ''pending''', 50000);

-- 120: the ANALYZE sample missed the subset entirely.
CREATE TABLE q120 AS SELECT i::int AS id,
       CASE WHEN i <= 2000 THEN 'pending' ELSE 'done' END::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p120 ON q120 (id) WHERE state = 'pending';
-- default_statistics_target is PGC_USERSET: this SET reaches this session only,
-- with no reload and no restart, and the RESET after the ANALYZE ends it.
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
UPDATE /* wiki_rs_suite_families */ plan SET grp =
       CASE WHEN num BETWEEN 18 AND 77  THEN 'partial'
            WHEN num BETWEEN 78 AND 85  THEN 'falsepos'
            WHEN num BETWEEN 86 AND 91  THEN 'falseneg'
            WHEN num BETWEEN 92 AND 112 THEN 'control'
            ELSE 'zero' END
 WHERE num >= 18;

UPDATE /* wiki_rs_suite_predictions */ plan SET want_stage =
       CASE
         -- Family 3, and every other fixture whose point is that a fresh index
         -- must not be touched.  Rule 2 exempts all of them from the drain, so
         -- their leaves are still packed to the build target and pgstatindex
         -- has nothing to report.  A physical reading is expected to pass all
         -- twenty-four, including the two - f84's forged index count and f85's
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

CALL /* wiki_rs_suite_assert_built */ assert_built();
SELECT count(*) AS planned_fixtures FROM plan;
SELECT count(*) AS fixtures_skipped FROM skipped;
SELECT count(*) AS baselines_taken FROM snap WHERE phase = 'built';
SELECT count(*) AS build_contract_failures FROM plan
 WHERE want_rows IS NOT NULL AND built_rows <> want_rows;
SELECT num, leg, idx, reason FROM skipped ORDER BY num, leg;
```

### Rule 2, the uniform drain

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
SET /* wiki_rs_churn_client_min_messages */ client_min_messages = warning;
SET /* wiki_rs_churn_statement_timeout */ statement_timeout = 0;
SET /* wiki_rs_churn_lock_timeout */ lock_timeout = 0;
SET /* wiki_rs_churn_idle_timeout */ idle_in_transaction_session_timeout = 0;

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
SELECT /* wiki_rs_drain_generator */ format(st.tmpl, tb.name)
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
        (1, 'DELETE /* wiki_rs_drain */ FROM %1$I WHERE ((ctid::text::point)[0])::int %% 10 <> 0'),
        (2, 'SELECT /* wiki_rs_drain_begin */ maint_begin(%1$L, ''drain'')'),
        (3, 'VACUUM /* wiki_rs_drain_maint */ (VERBOSE, ANALYZE) %1$I'),
        (4, 'SELECT /* wiki_rs_drain_end */ maint_end(%1$L)')) st(k, tmpl)
 ORDER BY tb.n, st.k
\gexec

SELECT /* wiki_rs_drain_count */ count(*) AS tables_drained
  FROM (VALUES ('pt1'), ('pd22'), ('pd23'), ('pd24'), ('pd25'), ('pd26'),
               ('pd27'), ('pd28'), ('pd29'), ('pd30'), ('pd31'), ('pw32'),
               ('pd33'), ('pd34'), ('pd35'), ('pd36'), ('pd37'),
               ('pd39'), ('pd40'), ('pd41'), ('pd42'), ('pd43'), ('pd44a'),
               ('pd44b'), ('pd45'), ('pd46'), ('pi47'), ('pe48'), ('pe48b'),
               ('pe49'), ('pe49b'), ('pe50'), ('pe50b'), ('pc51'), ('pf'),
               ('ps'), ('t'), ('t2')) d(name);
```

### Rule 3, the census, and the forgeries

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
SET /* wiki_rs_census_client_min_messages */ client_min_messages = warning;
SET /* wiki_rs_census_statement_timeout */ statement_timeout = 0;
SET /* wiki_rs_census_lock_timeout */ lock_timeout = 0;
SET /* wiki_rs_census_idle_timeout */ idle_in_transaction_session_timeout = 0;
SELECT wiki_flush();
SELECT /* wiki_rs_census_horizon_before */ horizon_probe('census-before', NULL);

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
-- so every ANALYZE below is one this rule asked for.  Only the suite's own
-- schema is censused; the guard fixtures in schema rs are not suite fixtures
-- and are left alone.
DROP TABLE IF EXISTS autoanl;
DROP TABLE IF EXISTS autoanl_after;
CREATE TABLE autoanl AS
SELECT /* wiki_rs_autoanalyze_census */
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

SELECT /* wiki_rs_autoanalyze_generator */
       format('ANALYZE /* wiki_rs_autoanalyze */ %I', tbl)
  FROM autoanl WHERE would_autoanalyze ORDER BY tbl
\gexec

-- The read side of rule 3: a view read may be served from a cached snapshot,
-- so the recheck discards it before reading the counter again.  A table the
-- recheck still finds above its own threshold is recorded as a disagreement
-- rather than analyzed a second time.
SELECT /* wiki_rs_autoanalyze_clear_snapshot */ pg_stat_clear_snapshot();
CREATE TABLE autoanl_after AS
SELECT /* wiki_rs_autoanalyze_recheck */
       c.relname AS tbl, st.n_mod_since_analyze::numeric AS mods,
       GREATEST(c.reltuples, 0)::numeric AS reltuples,
       a.threshold,
       (st.n_mod_since_analyze > a.threshold) AS still_above
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
  JOIN autoanl a ON a.tbl = c.relname
 WHERE st.schemaname = 'public' AND c.relkind = 'r'
   AND a.would_autoanalyze;

SELECT /* wiki_rs_autoanalyze_boundary */
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
SELECT /* wiki_rs_autoanalyze_overrides */ tbl, reltuples, mods,
       base_thresh, scale_factor, threshold, would_autoanalyze
  FROM autoanl WHERE per_table_override ORDER BY tbl;

-- The forgeries, after the census.  Fixture 84's whole point is a partial index
-- whose recorded entry count is wrong, and an ANALYZE of the table rewrites
-- reltuples for the table and for every index on it, so a forgery written
-- during the build would have been silently repaired.
UPDATE /* wiki_rs_forge_84 */ pg_class SET reltuples = 5000
 WHERE relname = 'f84';
SELECT /* wiki_rs_forge_check */ relname, reltuples AS forged_reltuples
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
SELECT /* wiki_rs_120_precondition */ c.relname AS idx,
       c.reltuples AS idx_reltuples, (c.reltuples = 0) AS precondition_met
  FROM pg_class c WHERE c.relname = 'p120';

INSERT /* wiki_rs_120_unmet */ INTO skipped(num, leg, idx, reason)
SELECT 120, '', 'p120',
       'unmet precondition: the ANALYZE sample found the subset, p120 reltuples = '
       || c.reltuples
  FROM pg_class c WHERE c.relname = 'p120' AND c.reltuples <> 0
    ON CONFLICT (num, leg) DO NOTHING;

DELETE /* wiki_rs_120_unscored */ FROM plan
 WHERE num = 120
   AND EXISTS (SELECT 1 FROM skipped s WHERE s.num = 120 AND s.idx = 'p120');

UPDATE /* wiki_rs_120_met */ plan
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
SELECT /* wiki_rs_family6_counts */ p.num, p.leg, p.idx,
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
INSERT /* wiki_rs_pageclass */ INTO pageclass
       (idx, leaf_pages, empty_pages, deleted_pages, avg_leaf_density, index_size)
SELECT p.idx, m.leaf_pages, m.empty_pages, m.deleted_pages,
       CASE WHEN m.avg_leaf_density = 'NaN'::float8 THEN NULL
            ELSE round(m.avg_leaf_density::numeric, 2) END,
       m.index_size
  FROM plan p, LATERAL pgstatindex(p.idx::regclass) m;

SELECT /* wiki_rs_pageclass_report */
       count(*) AS indexes_read,
       count(*) FILTER (WHERE deleted_pages > 0) AS with_deleted_pages,
       count(*) FILTER (WHERE empty_pages > 0)   AS with_half_dead_pages,
       coalesce(sum(deleted_pages), 0)           AS deleted_pages_total
  FROM pageclass;

SELECT /* wiki_rs_census_horizon_after */ horizon_probe('census-after', NULL);

-- The churned snapshot: the state the statement is about to be asked about.
SELECT /* wiki_rs_snap_churned */ count(*) AS churned_snapshots
  FROM (SELECT snap_take('churned', idx) FROM plan ORDER BY num, leg) s;
SELECT /* wiki_rs_snap_phases */ phase, count(*) AS snapshots
  FROM snap GROUP BY phase ORDER BY phase;
```

## Context Reviewed

- `contrib/pgstattuple`'s B-tree reader end to end: `pgstatindex_impl`'s entry
  checks — the `IS_INDEX`/`IS_BTREE` refusal, the other-session temp refusal and
  the `indisvalid` refusal — its per-block page-class bucketing of deleted,
  half-dead, leaf and internal pages, the `max_avail` and `free_space`
  accumulation that only leaf pages contribute to, the `index_size` expression
  that adds the metapage to the four classes, and both `NaN` branches, for
  `avg_leaf_density` and for `leaf_fragmentation`.
- Both `pgstatindex` overloads as the extension scripts declare them across 1.4
  and the 1.4-to-1.5 upgrade, the C entry points 1.5 binds them to, which one a
  `regclass` argument and an unadorned string literal each resolve to, the
  `REVOKE`/`GRANT` pair 1.5 applies to each, and the `AccessShareLock`
  `pgstatindexbyid_v1_5` opens the index with. The ten output columns are what
  fixes the set of inputs the formula may read.
- The B-tree fillfactor path: `BTGetFillFactor`'s reloption-or-default
  resolution, its `BTOptions` member, `BTGetTargetPageFreeSpace`, the four
  fillfactor constants — `BTREE_MIN_FILLFACTOR`, `BTREE_DEFAULT_FILLFACTOR`,
  the fixed non-leaf `BTREE_NONLEAF_FILLFACTOR` and the single-value
  `BTREE_SINGLEVAL_FILLFACTOR` — and the header comment that says what each
  governs, with `BTREE_SINGLEVAL_FILLFACTOR` traced to its only users, the
  split-point code in `nbtsplitloc.c` and `nbtdedup.c`.
- The build geometry the fillfactor target describes, and the sense in which it
  is a target: `_bt_pagestate`'s leaf and non-leaf fill targets, `nbtsort.c`'s
  sorted-input contract, `_bt_buildadd`'s page-full test, where the fillfactor
  is the soft half of a two-part condition that also requires the page to hold
  two items already, the move of a finished page's last item onto the next page,
  `_bt_uppershutdown`'s write of each level's rightmost page with whatever it
  holds, the build's note that it does not bias page boundaries toward suffix
  truncation, and `nbtsplitloc.c`'s use of the fixed non-leaf fillfactor for
  rightmost internal splits only.
- The page-deletion invariants that decide what a `NaN` density can mean:
  `_bt_pagedel`'s refusal to delete a rightmost, root, non-empty or
  incompletely-split page, the `README`'s statement of the same restriction and
  of its consequence for tree height, and `_bt_uppershutdown`'s no-data path,
  which writes a metapage pointing at `P_NONE`; and the exception, the all-zero
  page a crash can leave, which `nbtpage.c` reuses, `pgstatindex`'s B-tree
  reader has no test for and its hash reader counts as unused, read through
  `PageGetSpecialPointer`.
- Float arithmetic and comparison semantics, operator by operator: the inline
  `float8_pl`, `float8_mi`, `float8_mul` and `float8_div` the score's own
  arithmetic runs through, of which only `float8_div` treats a `NaN` operand
  specially, and only to spare a `NaN` dividend its zero-divisor error; the
  SQL-level `float8eq`, `float8ne` and `float8ge`; the inline `float8_eq`,
  `float8_ne`, `float8_lt`, `float8_gt` and `float8_ge` of `utils/float.h`, where
  `NaN = NaN`, `NaN <> NaN` and `NaN >= 0.5` are each decided before any C
  comparison runs; `btfloat8cmp` and `float8_cmp_internal`, which sort by those
  inline comparators; `ExecInitExprRec`'s `MinMaxExpr` case and
  `ExecEvalMinMax`'s selection loop, which passes the held value on the left
  and the next argument on the right; and the header comment and the two
  `in_range` comment blocks that state the ordering rule. Together they are what
  make `GREATEST(0, NaN)` and `NaN >= 0.5` behave as they do.
- This checkout's own history for the one version-history claim the page makes:
  the commit that added `BTEQUALIMAGE_PROC`, the equal-image builtins and
  `_bt_allequalimage`, its child that added `nbtdedup.c`, and the two
  version-stamp commits that bracket both into the PostgreSQL 13 cycle.
- `guc_tables.c`'s entry for every setting the scripts and blocks write, which is
  where each context in [The cluster settings](#the-cluster-settings) comes from.
- `pg_regress`'s handling of an inherited `PGOPTIONS`, which is why the scripts
  pass session options per call rather than exporting them.
- The shared suite in full, as
  [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
  defines it: the six families, the five phases, the maintenance assumption, the
  rule that the maintenance must not be defeated, the three porting rules, the
  `REINDEX INDEX` oracle, the four verdict bands, and the feature gates that
  skip a fixture rather than rewrite it.

## Evidence Map

| Claim | Evidence |
|---|---|
| `pgstatindex` returns ten columns, and neither `total_pages` nor `fillfactor` is one of them; the statement calls the `regclass` overload | [pgstattuple--1.4.sql#pgstatindex-regclass](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4.sql#L62-L74), [pgstattuple--1.4--1.5.sql#pgstatindex-regclass](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92) |
| `index_size` is the four page classes plus the metapage, so the two candidate denominators differ by exactly one page | [pgstatindex.c#index_size](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L357) |
| `avg_leaf_density` is `100 - free_space / max_avail * 100`, accumulated over leaf pages only | [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L366), [pgstatindex.c#page-classes](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L326) |
| `avg_leaf_density` is `NaN` exactly when no leaf page was scanned | [pgstatindex.c#avg_leaf_density-NaN](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L367) |
| A `NaN` density means a metapage-only file, because nbtree never deletes a rightmost or root page, so an index that ever held an entry keeps a live leaf | [nbtpage.c#_bt_pagedel-refusals](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1877-L1905), [README#never-delete-rightmost](../../../../raw/postgres-17/src/backend/access/nbtree/README#L236-L245), [README#tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L365-L367) |
| A build with no data writes only a metapage, and the page scan starts at block 1, so such a file classifies as nothing at all | [nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1118-L1128), [pgstatindex.c#block-loop](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L279-L283) |
| `NaN` propagates through the score's addition, subtraction, multiplication and division; only `float8_div` treats a `NaN` operand specially, and only to spare a `NaN` dividend its zero-divisor error | [float.h#float8_pl](../../../../raw/postgres-17/src/include/utils/float.h#L157-L167), [float.h#float8_mi](../../../../raw/postgres-17/src/include/utils/float.h#L181-L191), [float.h#float8_mul](../../../../raw/postgres-17/src/include/utils/float.h#L207-L219), [float.h#float8_div](../../../../raw/postgres-17/src/include/utils/float.h#L237-L251) |
| A zero `float8` divisor raises unless the dividend is already `NaN`, which is why the page-class denominator is undefined rather than `NaN` | [float.h#float8_div](../../../../raw/postgres-17/src/include/utils/float.h#L237-L251) |
| `GREATEST` compares through the type's B-tree comparison function, which for `float8` is `float8_cmp_internal`, with the held value on the left and the next argument on the right, and adopts the next argument when the result is negative | [execExpr.c#MinMaxExpr](../../../../raw/postgres-17/src/backend/executor/execExpr.c#L2194-L2201), [execExprInterp.c#ExecEvalMinMax-compare](../../../../raw/postgres-17/src/backend/executor/execExprInterp.c#L3158-L3170), [float.c#btfloat8cmp](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L966-L973) |
| `float8_cmp_internal(0, NaN)` is −1, because `float8_lt` is true whenever its right argument is `NaN` and its left is not, so `GREATEST(0, NaN)` is `NaN` | [float.c#float8_cmp_internal](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L903-L909), [float.h#float8_lt](../../../../raw/postgres-17/src/include/utils/float.h#L291-L295), [float.h#float8_gt](../../../../raw/postgres-17/src/include/utils/float.h#L315-L319), [float.h#NaN-ordering](../../../../raw/postgres-17/src/include/utils/float.h#L255-L259), [float.c#NaN-sorts-after](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L1038-L1041) |
| `NaN >= 0.5` is true, which is what turns an unguarded `NaN` into a rebuild order | [float.c#float8ge](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L957-L964), [float.h#float8_ge](../../../../raw/postgres-17/src/include/utils/float.h#L327-L331) |
| `NaN = NaN` is true and `NaN <> NaN` is false, so the guard must test `= 'NaN'::float8` and `x <> x` never fires | [float.c#float8eq](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L912-L919), [float.h#float8_eq](../../../../raw/postgres-17/src/include/utils/float.h#L267-L271), [float.c#float8ne](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L921-L928), [float.h#float8_ne](../../../../raw/postgres-17/src/include/utils/float.h#L279-L283), [float.c#NaN-equals-NaN](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L1043-L1047) |
| A rebuild aims leaves at the index's fillfactor and every level above it at a fixed 70 %, which is what the density term models | [nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L660-L666), [nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1144-L1145), [nbtree.h:201](../../../../raw/postgres-17/src/include/access/nbtree.h#L201) |
| That target is a soft limit, so a rebuilt leaf level does not land exactly on the fillfactor: a page is finished at a tuple boundary once it holds two items and hands its last item to the next page, and the last page of each level keeps whatever is left | [nbtsort.c#_bt_buildadd-full](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L844-L855), [nbtsort.c#_bt_buildadd-last-item](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L873-L884), [nbtsort.c#_bt_uppershutdown-rightmost](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1109-L1115) |
| The 96 % single-value fillfactor is a page-split target, which a sorted build never uses; an index packed above its fillfactor that way rebuilds into more leaves, and the score's floor credits it with nothing | [nbtree.h#fillfactor-comment](../../../../raw/postgres-17/src/include/access/nbtree.h#L190-L197), [nbtree.h:202](../../../../raw/postgres-17/src/include/access/nbtree.h#L202), [nbtsplitloc.c#SPLIT_SINGLE_VALUE](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L406-L413); the run's `grew_leaf_levels`, 0 on both legs |
| The internal term is not one-signed by construction: a build packs non-leaf levels at a fixed 70 % without choosing its boundaries for truncation, while insert-time splits use 70 % only on the rightmost page | [nbtsort.c#truncation-not-biased](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L912-L915), [nbtsplitloc.c#nonleaf-fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L285); the run's `grew_internal_levels`, 0 on both legs |
| The engine resolves an index's fillfactor as its reloption, else 90 | [nbtree.h#BTGetFillFactor](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1143), [nbtree.h:200](../../../../raw/postgres-17/src/include/access/nbtree.h#L200) |
| B-tree support function 4 is `BTEQUALIMAGE_PROC`, and this checkout's history introduced it one commit before deduplication, both inside the PostgreSQL 13 cycle | [nbtree.h#BTEQUALIMAGE_PROC](../../../../raw/postgres-17/src/include/access/nbtree.h#L703-L710); commit `612a1ab767` (2020-02-26, "Add equalimage B-Tree support functions."), parent of `0d861bbb70` ("Add deduplication to nbtree."), both descendants of `615cebc94b` ("Stamp HEAD as 13devel") and ancestors of `d10b19e224` ("Stamp HEAD as 14devel") |
| `pgstatindex` refuses any access method but B-tree, which bounds the population the heuristic can score, and 17.11's refuses an index the catalog marks not valid | [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L216-L250), [pgstatindex.c#indisvalid-refusal](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L240-L250) |
| The `regclass` overload opens each index with `AccessShareLock`, so one candidate held in `ACCESS EXCLUSIVE` past `lock_timeout`, or dropped before its call, ends the whole statement | [pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L204-L213) |
| An all-zero page a crash left is counted as internal: nbtree reuses such pages, the B-tree reader has no test for them, and the special-space offset of an all-zero page is zero | [nbtpage.c#all-zero-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L911-L923), [pgstatindex.c#page-classes](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L326), [pgstatindex.c#pgstathashindex-new-page](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L655-L656), [bufpage.h#PageGetSpecialPointer](../../../../raw/postgres-17/src/include/storage/bufpage.h#L336-L341) |
| `pgstattuple` 1.5 revokes `EXECUTE` on both `pgstatindex` overloads from `PUBLIC` and grants it to `pg_stat_scan_tables` | [pgstattuple--1.4--1.5.sql#pgstatindex-text](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L37), [pgstattuple--1.4--1.5.sql#pgstatindex-regclass](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92) |
| Every setting the scripts write has the context and apply scope the settings tables give | the fourteen `guc_tables.c` entries cited in [The cluster settings](#the-cluster-settings) |
| An inherited `PGOPTIONS` reaches `make check`, so the scripts pass session options per call | [pg_regress.c#PGOPTIONS](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L783-L799) |
| Every accuracy, error-decomposition, confusion-matrix, threshold-sweep, band-edge, denominator, guard, privilege, cross-leg and whole-cluster number on this page | the 2026-09-22 run of the two scripts in [Measurement Script](#measurement-script); `out/accuracy17.txt`, `out/accuracy12.txt`, `out/verdicts17.txt`, `out/verdicts12.txt`, `out/decide17.txt`, `out/decide12.txt`, `out/facts17.txt`, `out/facts12.txt`, `out/guard17.txt`, `out/guard12.txt`, `out/priv17.txt`, `out/priv12.txt`, `out/cost17.txt`, `out/cost12.txt`, `out/errors17_summary.txt`, `out/errors12_summary.txt`, `out/report17.txt`, `out/report12.txt`, `out/crossleg.txt` |
| The error decomposition is an identity rather than a fit | derived above from `total_pages = 1 + internal + leaf + empty + deleted`, and checked by the run: the largest `err - (leaf_term + internal_term + dead_term)` over all fixtures is 0.1 points on both legs, which is the rounding of the four columns |

## Open Questions

- **The whole-cluster figures come from two freshly `initdb`-ed clusters.** The
  138-of-233 and 133-of-219 `NaN` shares the guards removed, and the 95 and 86
  rebuild orders that remain, are the figures for a new cluster carrying the
  suite's fixtures and nothing else, where empty TOAST indexes are abundant. On a
  long-lived production database the shares would differ, in an unmeasured
  direction, and nothing here predicts them. Neither the defect nor the guard
  depends on the share.
- **The whole-cluster and cross-leg counts move between runs; the fixture figures
  do not.** They are read over each run's own catalog and TOAST indexes: this
  run's 17.11 population is 136,482 pages against the 2026-09-21 filing's
  136,517, and its cross-leg comparison has 291 shared names and 193 identical
  rows against 285 and 187. The run does not isolate why; the keys that differ
  are catalog and TOAST names, which the fixtures do not create.
- **Test 120 is probabilistic, and it moves the headline rather than one cell.**
  `ANALYZE` samples randomly, so `p120`'s precondition — a 300-row sample
  missing a 2,000-row subset — is met on some runs and not on others, and the
  fixture is scored only when it is met. In this run it was met on the 17 leg
  and not on the 12 leg, where the census found the index's own count at 3,334
  and recorded the fixture as an unmet precondition; the earlier 2026-09-22
  review run met it on both legs, and so did the 2026-09-21 filing. Because
  `p120` is the worst over-estimate wherever it is scored, including it moves
  the fixture count, the mean and worst error, the correlation and the family-6
  row. Every headline on this page is therefore given twice, over the 125 and
  116 deterministic fixtures and over everything scored, 126 and 116 this time;
  no other fixture has moved between runs. A reader reproducing this page should
  expect the `p120` row to be present or absent and the deterministic figures to
  match.
- **The deduplication interaction is scored only incidentally.** Family 1 pins
  which indexes *may* deduplicate, not how much a page-level merge saves, and the
  concept page says so. A rebuild of a deduplicating index can return more than
  the density term predicts, and the under-estimates listed here are consistent
  with that, but no fixture isolates the effect. The 12 leg cannot help, because
  deduplication does not exist there.
- **`want_stage` predictions are judgements.** The suite records disagreement
  between a filed prediction and the measurement but has no rule for which is at
  fault, so the `want_rebuild` column of the family table is context rather than
  a scored result. All three prediction-versus-decision disagreements on each
  leg — `p73`, `p76` and `f88` — are cases where the prediction said `rebuild`
  and both the heuristic **and** the oracle said leave, so the prediction was
  the thing that was wrong. There were four before the guards, the fourth being
  `p116`, where the prediction was right and the unguarded statement was wrong.
- **Family 4's `f88` does not reach the band it was built to test.** The concept
  page describes family 4 as six indexes that "really are reclaimable" and that
  "all six must be rebuilt", but `f88`'s measured rebuild returns 40.5 % on
  17.11 and 43.6 % on 12.2, below the suite's own 50 % `FALSE NEGATIVE` trigger.
  So a method that leaves `f88` alone scores `PASS`, and the fixture cannot fail
  a method the way the other five can. Whether `f88`'s churn should be deepened
  until its rebuild clears 50 %, or the family's description narrowed, is a
  change to
  [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
  and therefore its own task; this page only records the measurement.
- **Two fixtures sit within a point of the false-negative band.** `p73` and
  `p76` were left alone at a score of 49.6 apiece, against measured rebuilds of
  49.6 and 49.9, so the "no false negatives" result has **0.4** and **0.1**
  points of margin on those two. The margin is benign rather than lucky — the
  score tracks the actual to within 0.3 there, so both cross 50 % at nearly the
  same moment — but the suite contains no fixture whose actual lands just above
  50 while its score lands just below, which is the shape that would produce a
  false negative. Both figures are identical on the two legs.
- **Neither guard is tested against the other, because the engine does not
  produce the shape that would separate them.** `leaf_pages = 0` with
  `deleted_pages > 0` is the only shape on which guarding the density and
  guarding the score would disagree, and nbtree cannot reach it: the rightmost
  page of a level is never deleted, so an index that ever held an entry keeps a
  live leaf. Guard fixture `i_alldel` measures the boundary — 200,000 rows,
  every one deleted and vacuumed twice, leaving 1 leaf beside 547 deleted pages
  — and the `facts` stage counts zero rows where `leaf_pages = 0` and
  `total_pages = 1` disagree. The two placements therefore agree on every index
  that can exist, and the outer `CASE` never fires once the inner one is in
  place. This is a bound on what the run can distinguish, not a defect: no
  fixture added to the suite could separate them either, so the earlier request
  for an all-pages-deleted fixture is withdrawn rather than left open against
  [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md).
- **The threshold range is set by two fixtures' scores, and the rebuilds leave
  gaps around the cut.** By the suite's own bands every threshold from 35 % to
  65 % on 17.11, and 35 % to 70 % on 12.2, produces zero violations, so the run
  cannot distinguish them and does not establish 50 % as better than 40 %. The
  range runs from just above `p66`'s score of 33.0 on both legs to `p25`'s 66.5
  on 17.11, 6.5 points above its own rebuild of 60.0, and to the 73.9 of `f86`,
  `f87`, `f89` and `f90` on 12.2. Its lower half exists because the bands treat
  a rebuild returning 35 to 50 % as neither a false positive nor a false
  negative. Separately, no fixture's measured rebuild lands between **49.9 %**
  and **60.0 %** on 17.11, or between **49.9 %** and **74.3 %** on 12.2, and only
  three land between 35 % and 50 %, so a threshold in those gaps is scored on
  almost nothing. Narrowing either would need fixtures whose rebuilds land in the
  gaps, which is a change to the shared suite and therefore its own task.
- **The statement returns every row or none.** `pgstatindex` opens each
  candidate with `AccessShareLock`
  ([pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L204-L213)),
  so one index held in `ACCESS EXCLUSIVE` — by a concurrent `REINDEX` or
  `DROP INDEX` — for longer than the filed 5 s `lock_timeout`, or one dropped
  between the `cand` read and its own call, raises and ends the statement for
  every other index too. The suite runs no concurrency, so this is untested
  here. An unattended job would need to call `pgstatindex` per index inside its
  own exception handling, which is a different statement from the one filed.
- **All-zero pages are counted as internal.** A crash between extending an index
  and logging the new page leaves an all-zero page that nbtree reuses later
  ([nbtpage.c#all-zero-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L911-L923)),
  and `pgstatindex`'s B-tree reader, unlike its hash reader, has no test for one,
  so it lands in `internal_pages`: never credited as reclaimable, and on an
  index holding nothing but the metapage and such pages, a leafless file of more
  than one page. No fixture builds one, because it takes a crash.
- **The internal term's sign is measured, not guaranteed.** It never grew on any
  fixture of either leg, but a sorted build packs non-leaf pages at a fixed 70 %
  without choosing its boundaries for truncation
  ([nbtsort.c#truncation-not-biased](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L912-L915)),
  so an insert-grown index with dense, well-truncated internal pages and a leaf
  level a rebuild barely shrinks could come back with more internal pages. The
  suite has no fixture aimed at that shape.
- **No v12 source citation appears on this page.** The page is `version: 17`, and
  `AGENTS.md` forbids citing another version's checkout, so every 12.2 statement
  here is either a measurement, a link to a v12 page, or — for the one
  version-history claim — the v17 checkout's own commit history. The claim that
  B-tree support function 4 does not exist on 12.2 is filed as the nine
  `operator class ... does not exist` refusals the run recorded, not as a source
  reading of the 12.2 tree.
- **PostgreSQL 12 has no `mandatory-btree-bloat-tests` concept page.** The 12 leg
  ran the v17 concept page's protocol, which is the only written form of it, and
  states that inline. A v12 concept page is its own task and needs the user's
  go-ahead; until it exists, the v12 leg's protocol compliance rests on this
  page's prose rather than on a version-local concept document.
- **`fsync = off` on both clusters.** No timing on this page is durability
  realistic, which is why none is quoted as a result. The page counts, densities
  and rebuild sizes the verdicts rest on are unaffected.

## Source References

- [pgstatindex.c#pgstatindexbyid_v1_5](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L204-L213)
- [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L216-L250)
- [pgstatindex.c#indisvalid-refusal](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L240-L250)
- [pgstatindex.c#block-loop](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L279-L283)
- [pgstatindex.c#page-classes](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L298-L326)
- [pgstatindex.c#index_size](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L352-L357)
- [pgstatindex.c#avg_leaf_density-NaN](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L367)
- [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L366)
- [pgstatindex.c#pgstathashindex-new-page](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L655-L656)
- [pgstattuple--1.4.sql#pgstatindex-regclass](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4.sql#L62-L74)
- [pgstattuple--1.4--1.5.sql#pgstatindex-text](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L37)
- [pgstattuple--1.4--1.5.sql#pgstatindex-regclass](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)
- [nbtree.h#fillfactor-comment](../../../../raw/postgres-17/src/include/access/nbtree.h#L190-L197)
- [nbtree.h:200](../../../../raw/postgres-17/src/include/access/nbtree.h#L200)
- [nbtree.h:201](../../../../raw/postgres-17/src/include/access/nbtree.h#L201)
- [nbtree.h:202](../../../../raw/postgres-17/src/include/access/nbtree.h#L202)
- [nbtree.h#BTEQUALIMAGE_PROC](../../../../raw/postgres-17/src/include/access/nbtree.h#L703-L710)
- [nbtree.h#BTGetFillFactor](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1143)
- [nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1144-L1145)
- [nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L660-L666)
- [nbtsort.c#_bt_buildadd-full](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L844-L855)
- [nbtsort.c#_bt_buildadd-last-item](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L873-L884)
- [nbtsort.c#truncation-not-biased](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L912-L915)
- [nbtsort.c#_bt_uppershutdown-rightmost](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1109-L1115)
- [nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1118-L1128)
- [nbtsort.c#maxpostingsize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1288-L1308)
- [nbtsplitloc.c#nonleaf-fillfactor](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L280-L285)
- [nbtsplitloc.c#SPLIT_SINGLE_VALUE](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L406-L413)
- [nbtpage.c#all-zero-page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L911-L923)
- [nbtpage.c#_bt_pagedel-refusals](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1877-L1905)
- [README#never-delete-rightmost](../../../../raw/postgres-17/src/backend/access/nbtree/README#L236-L245)
- [README#tree-height](../../../../raw/postgres-17/src/backend/access/nbtree/README#L365-L367)
- [bufpage.h#PageGetSpecialPointer](../../../../raw/postgres-17/src/include/storage/bufpage.h#L336-L341)
- [float.c#float8_cmp_internal](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L903-L909)
- [float.c#float8eq](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L912-L919)
- [float.c#float8ne](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L921-L928)
- [float.c#float8ge](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L957-L964)
- [float.c#btfloat8cmp](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L966-L973)
- [float.c#NaN-sorts-after](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L1038-L1041)
- [float.c#NaN-equals-NaN](../../../../raw/postgres-17/src/backend/utils/adt/float.c#L1043-L1047)
- [float.h#float8_pl](../../../../raw/postgres-17/src/include/utils/float.h#L157-L167)
- [float.h#float8_mi](../../../../raw/postgres-17/src/include/utils/float.h#L181-L191)
- [float.h#float8_mul](../../../../raw/postgres-17/src/include/utils/float.h#L207-L219)
- [float.h#float8_div](../../../../raw/postgres-17/src/include/utils/float.h#L237-L251)
- [float.h#NaN-ordering](../../../../raw/postgres-17/src/include/utils/float.h#L255-L259)
- [float.h#float8_eq](../../../../raw/postgres-17/src/include/utils/float.h#L267-L271)
- [float.h#float8_ne](../../../../raw/postgres-17/src/include/utils/float.h#L279-L283)
- [float.h#float8_lt](../../../../raw/postgres-17/src/include/utils/float.h#L291-L295)
- [float.h#float8_gt](../../../../raw/postgres-17/src/include/utils/float.h#L315-L319)
- [float.h#float8_ge](../../../../raw/postgres-17/src/include/utils/float.h#L327-L331)
- [execExpr.c#MinMaxExpr](../../../../raw/postgres-17/src/backend/executor/execExpr.c#L2194-L2201)
- [execExprInterp.c#ExecEvalMinMax-compare](../../../../raw/postgres-17/src/backend/executor/execExprInterp.c#L3158-L3170)
- [guc_tables.c#fsync](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1096-L1107)
- [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457)
- [guc_tables.c#logging_collector](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1640-L1648)
- [guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2070-L2079)
- [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270)
- [guc_tables.c#port](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2393-L2401)
- [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2465-L2474)
- [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620)
- [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)
- [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642)
- [guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417)
- [guc_tables.c#unix_socket_directories](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4425-L4434)
- [guc_tables.c#listen_addresses](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4436-L4445)
- [guc_tables.c#client_min_messages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4776-L4785)
- [pg_regress.c#PGOPTIONS](../../../../raw/postgres-17/src/test/regress/pg_regress.c#L783-L799)

## Navigation

- [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
- [B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17 (unverified)](btree-bloat-with-pgstatindex.md)
- [A COMMENT-Stored Baseline B-Tree Index-Maintenance Heuristic for PostgreSQL 12 Through 17 (unverified)](btree-comment-baseline-maintenance-heuristic.md)
- [How pgstatindex Calculates Its Information in PostgreSQL 12 (unverified)](../../../v12/questions/indexing/how-pgstatindex-calculates-information.md)
- [v17/index](../../index.md)
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
