---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# A COMMENT-Stored Baseline B-Tree Index-Maintenance Heuristic for PostgreSQL 12 Through 17 (unverified)

## Contents

- [Question](#question)
  - [Prompt corrections](#prompt-corrections)
  - [The follow-up prompt](#the-follow-up-prompt)
  - [The 2026-09-14 re-port prompt](#the-2026-09-14-re-port-prompt)
  - [The 2026-09-16 review prompt](#the-2026-09-16-review-prompt)
- [Answer](#answer)
  - [Verdict](#verdict)
  - [What is stored, and where](#what-is-stored-and-where)
  - [Step 1: the plan](#step-1-the-plan)
  - [Step 2: carrying it out](#step-2-carrying-it-out)
  - [How to read the plan](#how-to-read-the-plan)
  - [The decision ladder, in order](#the-decision-ladder-in-order)
  - [Why every candidate filter is there](#why-every-candidate-filter-is-there)
  - [The three gates and the four states that disable them](#the-three-gates-and-the-four-states-that-disable-them)
  - [The index's own entry count, and who writes it](#the-indexs-own-entry-count-and-who-writes-it)
  - [The simulated auto-analyze the tests now run](#the-simulated-auto-analyze-the-tests-now-run)
  - [How wasted space is computed](#how-wasted-space-is-computed)
  - [What the gate can and cannot see](#what-the-gate-can-and-cannot-see)
  - [The blind spot that left with its fixtures](#the-blind-spot-that-left-with-its-fixtures)
  - [The comment survives both REINDEX forms](#the-comment-survives-both-reindex-forms)
  - [Privileges: measure, rebuild, write the baseline](#privileges-measure-rebuild-write-the-baseline)
  - [Locks, transactions and the two commands a DO block cannot reach](#locks-transactions-and-the-two-commands-a-do-block-cannot-reach)
  - [What it costs to run](#what-it-costs-to-run)
  - [What the 2026-09-14 re-port changed, and why](#what-the-2026-09-14-re-port-changed-and-why)
  - [What the 2026-09-16 review changed, and why](#what-the-2026-09-16-review-changed-and-why)
  - [Two defects the first revision's suite found](#two-defects-the-first-revisions-suite-found)
  - [What is version-local between 12 and 17](#what-is-version-local-between-12-and-17)
  - [The ported mandatory suite](#the-ported-mandatory-suite)
  - [The maintenance the suite now runs](#the-maintenance-the-suite-now-runs)
  - [Proving the maintenance was not defeated](#proving-the-maintenance-was-not-defeated)
  - [Results on 17.11](#results-on-1711)
  - [Results on 12.2](#results-on-122)
  - [Fixture 120's precondition, now asserted](#fixture-120s-precondition-now-asserted)
  - [Filed predictions against measured verdicts](#filed-predictions-against-measured-verdicts)
  - [Mandatory test review](#mandatory-test-review)
  - [What still needs to be tested](#what-still-needs-to-be-tested)
- [Measurement Script](#measurement-script)
  - [How to use the two leg scripts](#how-to-use-the-two-leg-scripts)
  - [The stages, both legs](#the-stages-both-legs)
  - [What the scripts read from the environment](#what-the-scripts-read-from-the-environment)
  - [Prerequisites](#prerequisites)
  - [Last run](#last-run)
  - [The PostgreSQL 17 leg script](#the-postgresql-17-leg-script)
  - [The PostgreSQL 12 leg script](#the-postgresql-12-leg-script)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

### Prompt corrections

Filed after prompt-hygiene correction, at the asker's request. The original prompt
wrote `agents.md` for `AGENTS.md`, lowercase `postgresql` for `PostgreSQL`, `btree`
for `B-tree`, `question Create` without the colon, `add all mandatory test from
question` for `Add all mandatory tests from the question`, and put a space before
the closing full stop. The asker chose "correct and restate", and chose to port
the full numbered suite, to build and measure both version legs, and to keep the
page in v17 while linking the v12 pages rather than citing another version's
source. The corrected text is below.

The 2026-09-11 follow-up prompt was corrected the same way, again at the asker's
request: it wrote `pg_statindex` for `pgstatindex()`, `store also index tuples`
for `also store the index's own tuple count`, `change more 10%` for `change more
than **10%**`, lowercase `analyze` for the `ANALYZE` command, began two sentences
in lower case, and put a space before a comma. Three scoping answers were taken
before drafting: **re-run both legs** rather than one, **bump the payload format
version to 2** so an old baseline is re-initialized rather than half-read, and
**apply the `ANALYZE` rule everywhere**, writing the deliberate catalog forgeries
after it so they survive, and recording which fixtures lose their original point.

Follow `AGENTS.md`, in PostgreSQL 17. Question:

Create a PostgreSQL B-tree index-maintenance heuristic compatible with versions
**12 through 17**.

Store the index size and its table's estimated tuple count in the index comment.
Each time the heuristic runs, compare the current values with the stored values
and run `pgstatindex()` if either:

- The index size has increased by **20% or more**; or
- The table tuple count has increased or decreased by **20% or more**.

Use `pgstatindex()` to calculate the index's wasted-space percentage. If wasted
space is **greater than 40%**, trigger a reindex. If wasted space is **40% or
less**, do not reindex; instead, update the index comment with the current index
size and table tuple count.

After a successful reindex, update or initialize the index comment with the new
index size and current table tuple count.

The heuristic should safely handle missing or invalid comment metadata, preserve
any existing user-defined comment, and work with PostgreSQL versions 12 through 17.

Add all mandatory tests from the question [Testing the PostgreSQL 12 Core-SQL
B-Tree Bloat Method on PostgreSQL 17
(unverified)](btree-index-bloat-core-sql-only.md).

### The follow-up prompt

Filed 2026-09-11, after the corrections above:

Follow `AGENTS.md`, in PostgreSQL 17, for question: A COMMENT-Stored Baseline
B-Tree Index-Maintenance Heuristic for PostgreSQL 12 Through 17 (unverified).
Update the heuristic to also store the index's own tuple count, and have the
**20%** up-and-down trigger for `pgstatindex()` apply to it as well. Update the
mandatory tests so that a test changing more than **10%** of the heap tuples
calls `ANALYZE`, to simulate an auto-analyze.

### The 2026-09-14 re-port prompt

Corrected the same way, again at the asker's request. The original wrote
`agents.md` for `AGENTS.md`, lowercase `postgresql`, `review question:` without
an article, a stray `#` before each of the two page titles, the `(unverified)`
hint as part of both titles, a line break and a comma splicing the second
instruction onto the title, `common-concept` for "the common concept page", the
contraction `aren't`, and no terminal period. Four scoping answers were taken
before any edit: **retire only** — delete the fixtures the concept page retired
but do **not** add its maintenance `VACUUM ANALYZE`; **re-run both legs** end to
end from their pins; and **remove every page-local fixture**, deleting the
claims they backed. The corrected text:

Follow `AGENTS.md`, in PostgreSQL 17. Review the question "A COMMENT-Stored
Baseline B-Tree Index-Maintenance Heuristic for PostgreSQL 12 Through 17".
Update the tests based on the changes from the common concept page, and update
or remove all tests that are not following
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md).

### The 2026-09-16 review prompt

Corrected the same way, again at the asker's request. The original wrote
`agents.md` for `AGENTS.md`, lowercase `postgresql` for `PostgreSQL`, put a
space before the colon in `review :` and two after it, named the page by its
bare filename rather than its title, opened the sentence in lower case, and
left off the terminal period. Four scoping answers were taken before any edit:
**re-run both legs end to end** rather than audit the filed text; **adopt the
concept page's maintenance step**, which the 2026-09-14 pass had deliberately
skipped; **assert fixture 120's precondition** and score nothing from that
fixture when it is unmet; and edit the two filed leg scripts **in place**. The
corrected text:

Follow `AGENTS.md`, in PostgreSQL 17. Review the question "A COMMENT-Stored
Baseline B-Tree Index-Maintenance Heuristic for PostgreSQL 12 Through 17".

## Answer

### Verdict

Two texts do it, and both run unchanged on 12.2 and 17.11: a read-only statement
that decides, and a `DO` block that carries the decision out. The baseline lives
in an 86-byte `@btmaint:` payload appended to the index's own comment, which
survives `REINDEX INDEX` because the comment is keyed by the index's OID, and
survives `REINDEX INDEX CONCURRENTLY` because `index_concurrently_swap` moves the
`pg_description` row to the new index
([index.c#index_concurrently_swap-comment](../../../../raw/postgres-17/src/backend/catalog/index.c#L1740-L1784),
[pg_description.h#FormData](../../../../raw/postgres-17/src/include/catalog/pg_description.h#L44-L57)).

**The 2026-09-16 review is the first run of this page under the concept page's
maintenance assumption in full, and under the newer rule that a fixture may not
defeat the maintenance it issued.** The 2026-09-14 pass had skipped the
maintenance step at the asker's direction, which this page recorded as a
departure; that departure is now closed. Every churned table is vacuumed and
analyzed before the method is asked anything, and the four proofs the rule asks
for are recorded per table. Both legs were rebuilt from their pins and re-run end
to end, `make check` included, and **neither filed text changed** — both SQL
blocks still hash to their 2026-09-11 values.

| Result | 17.11 | 12.2 | 2026-09-14 run, 17.11 |
|---|---|---|---|
| Numbered fixtures built | **126** | **112** | 126 |
| Scored, after the fixture-120 precondition check | **125** | **112** | 126, with 120 wrongly credited |
| Gate decision equal to the same arithmetic done independently | 126 of 126 | 112 of 112 | 126 of 126 |
| `PASS` | **125** | **112** | 126 |
| `FALSE NEGATIVE` | **0** | **0** | 0 |
| `CRITICAL FALSE POSITIVE`, `FALSE POSITIVE` | 0 | 0 | 0 |
| `UNMET PRECONDITION`, scoring nothing | **1** | 0 | not checked |
| Indexes rebuilt, and their mean measured reclaim | 95, 86.2 % | 81, 87.1 % | 95, 86.2 % |
| Fresh indexes wrongly rebuilt (the eight false-positive constructions) | 0 of 8 | 0 of 8 | 0 of 8 |
| Stored index count equal to the catalog's at baseline time | 126 of 126 | 112 of 112 | 126 of 126 |
| Tables maintained, and their `dead but not yet removable` count | 66, all **0** | 65, all **0** | no maintenance step |
| Horizon probes entirely clean | 69 of 69 | 68 of 68 | not taken |

**The score did not move, and that is the finding.** Adding the maintenance step
changed the state of ten recipes that used to reach the decide phase
unmaintained, and changed no verdict: 95 rebuilds at the same 86.2 % mean reclaim
on 17.11, 81 at 87.1 % on 12.2, no false negative and no false positive of either
severity on either leg. What it did change is the readings on the four
threshold-calibration controls, whose trailing `UPDATE` nobody had vacuumed:
`b93` and `b95` used to under-read the oracle by 18.2 points and now under-read
it by **9.4** (79.7 % against 89.1 %), because the dead entries their update left
are now removed before `pgstatindex` counts pages.

**The clean sheet is still not the heuristic improving.** The fixtures this
method fails — a file whose entries are dead but physically present — left the
suite on 2026-09-14 and have not come back; `pgstatindex` still reports such a
file as dense. See
[The blind spot that left with its fixtures](#the-blind-spot-that-left-with-its-fixtures).

**The three gates still earn their place.** Of 104 measured fixtures on 17.11 the
index-count test fired on 103, the table-count test on 79 and the size test on 8;
**20 were measured that the two-gate form would have skipped**, 15 of them
genuinely bloated at a mean measured reclaim of 86.7 %, and not one measurement
was lost. One fixture is opened by the size test alone — `p76`, bloated by
updating an indexed key, whose file doubled at `size_ratio` 1.9964 while its entry
count barely moved, `idx_tuple_ratio` 0.9980 on 17.11 and 1.0000 on 12.2 — and no
fixture on either leg
is opened by the table count alone. The 12.2 leg agrees: 89 measured, 19 newly
measured, 15 of them bloated at a mean 86.3 %.

Where the gate fires, the reading is close: over the 103 scored measurements on
17.11 `wasted_pct` under-estimates the reclaim a rebuild gave back by a mean of
7.6 points (min `-2.0`, max `+19.5`), **101 of 103 within 15 points**, and 7
over-estimates. The worst under-read is `p55`, the fillfactor-70 fixture, at
69.9 % against a measured 89.4 %; the worst over-read is `f88` at 42.5 % against
40.5 %, so **no scored fixture over-states waste by more than 2.0 points**. The
104th measurement is `p120`, which reads 5.9 % against 0.0 % and scores nothing,
because its precondition was not met on this leg.

### What is stored, and where

`COMMENT ON INDEX` stores one string per index in `pg_description`, keyed by
`(objoid, classoid, objsubid)` with `objsubid = 0`, and a new comment replaces the
old one whole - there is no append
([pg_description.h#FormData](../../../../raw/postgres-17/src/include/catalog/pg_description.h#L44-L57),
[comment.c#CreateComments](../../../../raw/postgres-17/src/backend/commands/comment.c#L133-L171),
[comment.sgml#replaces](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L89-L93)).
So the heuristic has to rewrite the whole comment on every write, and preserving
the human text is its job, not the server's.

The payload is one line, appended after any human text:

```text
hand-written note kept by the DBA
@btmaint:{"v":2,"sz":4513792,"tup":200000,"itup":200000,"at":"2026-09-11T15:11:43-04"}
```

| Field | Meaning | Why it is there |
|---|---|---|
| `v` | payload format version, now `2` | a change of shape must not be read as a baseline; a mismatch is treated as unreadable |
| `sz` | `pg_relation_size(index)` at baseline time, bytes | the question's first input; main fork only ([system_functions.sql#pg_relation_size](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L285-L289)) |
| `tup` | the table's `pg_class.reltuples`, rounded | the question's second input |
| `itup` | the index's own `pg_class.reltuples`, rounded | the follow-up's input: a partial index's population is not its table's ([pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L66)) |
| `at` | when the baseline was written | staleness is otherwise invisible; it takes no part in any decision |

Measured length: **86 bytes** for the payload the 12 leg's `exact` stage saw
written on the index of a 200,000-row table, printed in full in that stage's
output:

```text
@btmaint:{"v":2,"sz":4521984,"tup":200000,"itup":200000,"at":"2026-09-14T15:54:51-04"}
```

The exact length follows from the digits in the three numbers, so it is a
property of that fixture rather than of the format. The payload is plain text,
not `jsonb`, and it is read with
`substring(... from '...')` rather than a cast, for a reason that is
version-local: casting a malformed payload to `jsonb` raises, one raised error
aborts the whole statement, and the guard that would prevent it,
`pg_input_is_valid()`, exists on 17 and not on 12 - measured, 1 matching `pg_proc`
row against 0. A regex `substring` returns NULL instead of raising, and each
field's pattern ends in `[,}]`, so a number longer than the pattern allows fails
to match rather than silently truncating.

**Version 1 baselines are re-initialized, not half-read.** The `baseline` test
treats a missing `itup` exactly as it treats a missing `sz`: unreadable, so the
row takes the `initialize` branch and the payload is rewritten whole. The cost of
the upgrade is therefore one comment write per index on the first run, with no
rebuild and no measurement, and the third gate is live from the second run on.
The alternative, accepting a v1 payload and running two gates for that index, was
rejected: it would leave a database in which two indexes with the same comment
shape are gated differently, and nothing in the comment would say so. The
2026-09-14 pass **removed the fixtures that measured this**, along with every
other page-local acceptance fixture; the branch is now a reading of the filed
text rather than a measured outcome, and the loss is filed under
[Open Questions](#open-questions).

### Step 1: the plan

Read-only. It decides, prints the exact commands, and writes nothing.

```sql
-- B-tree index-maintenance heuristic, step 1: decide, write nothing.
-- One text, unchanged on PostgreSQL 12 through 17.
--
--   params   thresholds, the comment marker and the two page-layout constants
--   cand     every B-tree index this session may both measure and comment on
--   parsed   the @btmaint: payload pulled out of the index's own comment
--   gate     the three 20 % tests, and the states that bypass them
--   meas     one pgstatindex() call per gated index, and none for the rest
--   wasted   free bytes beyond a rebuild at this index's own fillfactor
--   plan     the action, and the exact commands that carry it out
--
-- Gate: measure when the index has grown by 20 % or more, when the table's
-- estimated tuple count has moved by 20 % or more in either direction, or when
-- the index's own estimated entry count has moved by 20 % or more in either
-- direction.
-- Decide: wasted_pct > 40 -> reindex; 40 or less -> just refresh the baseline.
-- Nothing here writes.  Step 2 applies the plan.

SET /* wiki_btmaint_statement_timeout */ statement_timeout = '15min';
SET /* wiki_btmaint_lock_timeout */ lock_timeout = '5s';

WITH params AS (
    SELECT current_setting('block_size')::numeric AS bs,
           24::numeric        AS page_header,     -- SizeOfPageHeaderData
           16::numeric        AS btree_special,   -- MAXALIGN(BTPageOpaqueData)
           1.20::numeric      AS grow_ratio,      -- index-size gate
           0.20::numeric      AS tuple_ratio,     -- tuple-count gate, table and index
           40::numeric        AS wasted_max,      -- reindex above this percent
           0::numeric         AS min_index_bytes, -- ignore anything smaller
           2::numeric         AS fmt              -- payload format version
),
cand AS MATERIALIZED (
    SELECT c.oid                  AS idx_oid,
           n.nspname              AS schema_name,
           c.relname              AS index_name,
           t.relname              AS table_name,
           pg_relation_size(c.oid) AS cur_bytes,
           t.reltuples::numeric   AS cur_tuples,
           c.reltuples::numeric   AS cur_idx_tuples,
           (SELECT o.option_value::int
              FROM pg_options_to_table(c.reloptions) o
             WHERE o.option_name = 'fillfactor')      AS fillfactor_opt,
           d.description          AS cmt,
           pg_has_role(c.relowner, 'USAGE')           AS owns_index,
           pg_has_role(t.relowner, 'USAGE')           AS owns_table
      FROM pg_class c
      JOIN pg_namespace n   ON n.oid = c.relnamespace
      JOIN pg_index x       ON x.indexrelid = c.oid
      JOIN pg_class t       ON t.oid = x.indrelid
      JOIN pg_am a          ON a.oid = c.relam
      LEFT JOIN pg_description d ON d.objoid = c.oid
                               AND d.classoid = 'pg_class'::regclass
                               AND d.objsubid = 0
     CROSS JOIN params p
     WHERE a.amname = 'btree'                    -- pgstatindex takes no other AM
       AND c.relkind = 'i'                       -- 'I' has no storage
       AND x.indisvalid AND x.indisready AND x.indislive
       AND NOT pg_is_other_temp_schema(c.relnamespace)
       AND (c.relpersistence <> 'u' OR NOT pg_is_in_recovery())
       AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
       AND pg_relation_size(c.oid) >= p.min_index_bytes
),
parsed AS MATERIALIZED (
    SELECT c.*,
           pay.payload,
           substring(pay.payload from '"v":([0-9]{1,6})[,}]')::numeric      AS pv,
           substring(pay.payload from '"sz":([0-9]{1,25})[,}]')::numeric    AS base_bytes,
           substring(pay.payload from
                     '"tup":(-?[0-9]{1,25}(?:[.][0-9]{1,10})?)[,}]')::numeric AS base_tuples,
           substring(pay.payload from
                     '"itup":(-?[0-9]{1,25}(?:[.][0-9]{1,10})?)[,}]')::numeric AS base_idx_tuples,
           substring(pay.payload from '"at":"([^"]{1,40})"')            AS base_at,
           -- Two passes, in this order: a well-formed payload goes first, so
           -- that human text on the same line survives, and only a leftover
           -- marker is then removed to the end of its line.
           regexp_replace(
             regexp_replace(coalesce(c.cmt, ''),
                            '[[:space:]]*@btmaint:\{[^}]*\}', '', 'g'),
                            '[[:space:]]*@btmaint:[^\n]*', '', 'g')      AS user_cmt
      FROM cand c
      CROSS JOIN LATERAL (
           SELECT substring(c.cmt from '@btmaint:(\{[^}]*\})') AS payload) pay
),
gate AS MATERIALIZED (
    SELECT s.*,
           p.bs, p.grow_ratio, p.tuple_ratio, p.wasted_max,
           p.bs - p.page_header - p.btree_special AS leaf_cap,
           COALESCE(s.fillfactor_opt, 90)         AS fillfactor,
           CASE WHEN s.cmt IS NULL OR s.cmt !~ '@btmaint:'   THEN 'absent'
                WHEN s.pv IS DISTINCT FROM p.fmt
                  OR s.base_bytes IS NULL
                  OR s.base_tuples IS NULL
                  OR s.base_idx_tuples IS NULL               THEN 'invalid'
                ELSE 'ok' END                                AS baseline,
           -- reltuples is -1 on a relation no ANALYZE, VACUUM or index build
           -- has counted since PostgreSQL 14; 12 and 13 leave 0 there instead
           (s.cur_tuples < 0)                                AS tuples_unknown,
           (s.cur_idx_tuples < 0)                            AS idx_tuples_unknown
      FROM parsed s CROSS JOIN params p
),
decided AS MATERIALIZED (
    SELECT g.*,
           CASE WHEN g.base_bytes > 0
                THEN round(g.cur_bytes / g.base_bytes, 4) END AS size_ratio,
           CASE WHEN g.base_tuples > 0 AND NOT g.tuples_unknown
                THEN round(g.cur_tuples / g.base_tuples, 4) END AS tuple_ratio_now,
           CASE WHEN g.base_idx_tuples > 0 AND NOT g.idx_tuples_unknown
                THEN round(g.cur_idx_tuples / g.base_idx_tuples, 4) END
                                                              AS idx_tuple_ratio_now,
           (g.baseline = 'ok' AND g.base_bytes > 0
            AND g.cur_bytes >= g.base_bytes * g.grow_ratio)     AS size_gate,
           (g.baseline = 'ok' AND NOT g.tuples_unknown
            AND g.base_tuples >= 0
            AND (CASE WHEN g.base_tuples = 0
                      THEN g.cur_tuples > 0
                      ELSE abs(g.cur_tuples - g.base_tuples)
                           >= g.base_tuples * g.tuple_ratio END))  AS tuple_gate,
           -- The index's own entry count, gated exactly like the table's.  A
           -- partial index's population is not its table's population, which
           -- is the whole reason this test is separate.
           (g.baseline = 'ok' AND NOT g.idx_tuples_unknown
            AND g.base_idx_tuples >= 0
            AND (CASE WHEN g.base_idx_tuples = 0
                      THEN g.cur_idx_tuples > 0
                      ELSE abs(g.cur_idx_tuples - g.base_idx_tuples)
                           >= g.base_idx_tuples * g.tuple_ratio END)) AS idx_tuple_gate,
           (g.baseline = 'ok' AND g.base_bytes > 0
            AND g.cur_bytes < g.base_bytes)                     AS shrank
      FROM gate g
),
staged AS MATERIALIZED (
    SELECT d.*,
           CASE WHEN NOT d.owns_index                    THEN 'blocked'
                WHEN d.baseline <> 'ok'                  THEN 'initialize'
                WHEN d.shrank                            THEN 'refresh'
                WHEN d.size_gate OR d.tuple_gate
                  OR d.idx_tuple_gate                    THEN 'measure'
                ELSE 'skip' END                          AS stage
      FROM decided d
),
gated AS MATERIALIZED (
    SELECT s.* FROM staged s WHERE s.stage = 'measure'
),
meas AS MATERIALIZED (
    -- One pgstatindex() call per gated index, and none at all for the rest.
    -- The function's input relation is the gated rows themselves, so an index
    -- that did not pass the gate is never opened.  A WHERE or an ON clause
    -- would not do: a set-returning function in FROM is executed first and
    -- filtered afterwards, which read every candidate index end to end.
    SELECT g.*, m.index_size, m.leaf_pages, m.empty_pages, m.deleted_pages,
           m.avg_leaf_density, m.leaf_fragmentation, m.version AS meta_version
      FROM gated g, LATERAL pgstatindex(g.idx_oid::regclass) m
),
merged AS (
    SELECT * FROM meas
    UNION ALL
    SELECT s.*, NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint,
           NULL::float8, NULL::float8, NULL::int
      FROM staged s WHERE s.stage <> 'measure'
),
wasted AS (
    SELECT m.*,
           (m.leaf_cap - (m.bs * (100 - m.fillfactor)) / 100) / m.leaf_cap AS target_density,
           CASE WHEN m.leaf_pages > 0 AND m.avg_leaf_density <> 'NaN'::float8
                THEN (m.avg_leaf_density / 100)::numeric
                ELSE 0::numeric END                                       AS density,
           COALESCE(m.empty_pages, 0) + COALESCE(m.deleted_pages, 0)       AS dead_pages
      FROM merged m
),
scored AS (
    SELECT w.*,
           CASE WHEN w.stage <> 'measure' THEN NULL
                ELSE GREATEST(round(w.leaf_pages * w.leaf_cap * w.target_density)
                              - round(w.leaf_pages * w.leaf_cap * w.density), 0)
                     + w.dead_pages * w.bs END AS wasted_bytes
      FROM wasted w
),
plan AS (
    SELECT s.*,
           CASE WHEN s.stage <> 'measure' OR s.index_size = 0 THEN NULL
                ELSE round(100 * s.wasted_bytes / s.index_size, 1) END AS wasted_pct,
           CASE WHEN s.stage <> 'measure' THEN s.stage
                WHEN s.index_size = 0     THEN 'skip'
                WHEN round(100 * s.wasted_bytes / s.index_size, 1) > s.wasted_max
                     THEN 'reindex'
                ELSE 'update' END                                      AS action
      FROM scored s
)
SELECT /* wiki_btmaint_plan_12_17 */
       p.schema_name,
       p.index_name,
       p.table_name,
       p.action,
       p.baseline,
       pg_size_pretty(p.cur_bytes) AS index_size,
       pg_size_pretty(p.base_bytes::bigint) AS baseline_size,
       p.size_ratio,
       p.cur_tuples AS table_tuples,
       p.base_tuples AS baseline_tuples,
       p.tuple_ratio_now,
       p.cur_idx_tuples AS index_tuples,
       p.base_idx_tuples AS baseline_index_tuples,
       p.idx_tuple_ratio_now,
       CASE WHEN p.stage = 'measure' THEN round(p.avg_leaf_density::numeric, 2) END
           AS avg_leaf_density,
       CASE WHEN p.stage = 'measure' THEN p.dead_pages END AS dead_pages,
       p.wasted_pct,
       array_to_string(array_remove(ARRAY[
           CASE WHEN NOT p.owns_index THEN 'not the index owner: no comment can be written' END,
           CASE WHEN p.owns_index AND NOT p.owns_table THEN 'not the table owner: REINDEX may be refused' END,
           CASE WHEN p.baseline = 'invalid' THEN 'unreadable @btmaint: payload, replaced' END,
           CASE WHEN p.tuples_unknown THEN 'table reltuples unknown: table tuple gate cannot fire' END,
           CASE WHEN p.idx_tuples_unknown THEN 'index reltuples unknown: index tuple gate cannot fire' END,
           CASE WHEN p.baseline = 'ok' AND p.base_tuples = 0 THEN 'baseline table tuple count was zero' END,
           CASE WHEN p.baseline = 'ok' AND p.base_idx_tuples = 0 THEN 'baseline index tuple count was zero' END,
           CASE WHEN p.shrank THEN 'index smaller than its baseline: rebuilt elsewhere' END,
           CASE WHEN p.size_gate THEN 'size gate fired' END,
           CASE WHEN p.tuple_gate THEN 'table tuple gate fired' END,
           CASE WHEN p.idx_tuple_gate THEN 'index tuple gate fired' END,
           CASE WHEN p.stage = 'measure' AND p.leaf_pages = 0 THEN 'no leaf pages' END,
           CASE WHEN p.stage = 'measure' AND p.leaf_fragmentation >= 30
                THEN 'fragmented, not wasted space' END,
           CASE WHEN p.fillfactor <> 90 THEN 'fillfactor ' || p.fillfactor END
       ], NULL), '; ') AS notes,
       -- The comment is written now for every action but 'reindex', whose new
       -- baseline is only known after the rebuild; step 2 writes that one.
       CASE WHEN p.action IN ('initialize', 'refresh', 'update')
            THEN format('COMMENT ON INDEX %I.%I IS %L', p.schema_name, p.index_name,
                   CASE WHEN length(btrim(p.user_cmt)) > 0
                        THEN btrim(p.user_cmt) || E'\n' ELSE '' END
                   || '@btmaint:{"v":2,"sz":' || p.cur_bytes
                   || ',"tup":' || round(GREATEST(p.cur_tuples, -1))
                   || ',"itup":' || round(GREATEST(p.cur_idx_tuples, -1))
                   || ',"at":"' || to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SSOF') || '"}') END
           AS comment_command,
       CASE WHEN p.action = 'reindex'
            THEN format('REINDEX INDEX %I.%I', p.schema_name, p.index_name) END
           AS reindex_command
  FROM plan p
 ORDER BY CASE p.action WHEN 'reindex' THEN 0 WHEN 'update' THEN 1
                        WHEN 'initialize' THEN 2 WHEN 'refresh' THEN 3
                        WHEN 'blocked' THEN 4 ELSE 5 END,
          p.cur_bytes DESC, p.schema_name, p.index_name;
```

It needs `CREATE EXTENSION pgstattuple` in the database being examined; both
checkouts ship the same 1.5 control file and the same `pgstatindex(regclass)`
declaration, revoked from `PUBLIC` and granted to `pg_stat_scan_tables`
([pgstattuple--1.4--1.5.sql#pgstatindex-regclass](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)).
`statement_timeout` and `lock_timeout` are both `PGC_USERSET`, so the two `SET`
lines apply at session scope and need neither reload nor restart
([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2612-L2620),
[guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2623-L2631)).

### Step 2: carrying it out

Run it at the top level, not inside `BEGIN`: it commits once per index, and a
`DO` block cannot commit inside an explicit transaction block - measured,
`ERROR: invalid transaction termination` on both servers.

```sql
-- B-tree index-maintenance heuristic, step 2: carry out the plan.
-- One text, unchanged on PostgreSQL 12 through 17.  Run it at the top level:
-- it commits once per index, which no DO block can do inside BEGIN ... END.
--
-- The CTE pipeline below, from "WITH params AS (" to the line before its final
-- SELECT, is byte-identical to the pipeline of step 1.  Only the final SELECT
-- differs: step 1 presents the plan to a reader, step 2 hands five parallel
-- arrays to the driver.  Everything after the snapshot is re-read per index,
-- because a snapshot older than one lock is not a safe thing to act on.
SET /* wiki_btmaint_apply_statement_timeout */ statement_timeout = '15min';
SET /* wiki_btmaint_apply_lock_timeout */ lock_timeout = '5s';

DO /* wiki_btmaint_apply_12_17 */ $btmaint$
DECLARE
    dry_run     boolean := false;  -- true: measure and report, write nothing
    wasted_max  numeric := 40;     -- reindex above this percent; matches step 1
    max_reindex integer := 1000;   -- cap on rebuilds per run; 1 is conservative
    v_oid     oid[];
    v_stage   text[];
    v_leafcap numeric[];
    v_ff      numeric[];
    v_bs      numeric[];
    i         integer;
    n_re      integer := 0;
    n_upd     integer := 0;
    n_init    integer := 0;
    n_ref     integer := 0;
    n_block   integer := 0;
    n_err     integer := 0;
    r_nsp     text;
    r_idx     text;
    r_bytes   numeric;
    r_tuples  numeric;
    r_itup    numeric;
    r_user    text;
    r_tdens   numeric;
    r_wasted  numeric;
    r_act     text;
    r_cmt     text;
BEGIN
WITH params AS (
    SELECT current_setting('block_size')::numeric AS bs,
           24::numeric        AS page_header,     -- SizeOfPageHeaderData
           16::numeric        AS btree_special,   -- MAXALIGN(BTPageOpaqueData)
           1.20::numeric      AS grow_ratio,      -- index-size gate
           0.20::numeric      AS tuple_ratio,     -- tuple-count gate, table and index
           40::numeric        AS wasted_max,      -- reindex above this percent
           0::numeric         AS min_index_bytes, -- ignore anything smaller
           2::numeric         AS fmt              -- payload format version
),
cand AS MATERIALIZED (
    SELECT c.oid                  AS idx_oid,
           n.nspname              AS schema_name,
           c.relname              AS index_name,
           t.relname              AS table_name,
           pg_relation_size(c.oid) AS cur_bytes,
           t.reltuples::numeric   AS cur_tuples,
           c.reltuples::numeric   AS cur_idx_tuples,
           (SELECT o.option_value::int
              FROM pg_options_to_table(c.reloptions) o
             WHERE o.option_name = 'fillfactor')      AS fillfactor_opt,
           d.description          AS cmt,
           pg_has_role(c.relowner, 'USAGE')           AS owns_index,
           pg_has_role(t.relowner, 'USAGE')           AS owns_table
      FROM pg_class c
      JOIN pg_namespace n   ON n.oid = c.relnamespace
      JOIN pg_index x       ON x.indexrelid = c.oid
      JOIN pg_class t       ON t.oid = x.indrelid
      JOIN pg_am a          ON a.oid = c.relam
      LEFT JOIN pg_description d ON d.objoid = c.oid
                               AND d.classoid = 'pg_class'::regclass
                               AND d.objsubid = 0
     CROSS JOIN params p
     WHERE a.amname = 'btree'                    -- pgstatindex takes no other AM
       AND c.relkind = 'i'                       -- 'I' has no storage
       AND x.indisvalid AND x.indisready AND x.indislive
       AND NOT pg_is_other_temp_schema(c.relnamespace)
       AND (c.relpersistence <> 'u' OR NOT pg_is_in_recovery())
       AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
       AND pg_relation_size(c.oid) >= p.min_index_bytes
),
parsed AS MATERIALIZED (
    SELECT c.*,
           pay.payload,
           substring(pay.payload from '"v":([0-9]{1,6})[,}]')::numeric      AS pv,
           substring(pay.payload from '"sz":([0-9]{1,25})[,}]')::numeric    AS base_bytes,
           substring(pay.payload from
                     '"tup":(-?[0-9]{1,25}(?:[.][0-9]{1,10})?)[,}]')::numeric AS base_tuples,
           substring(pay.payload from
                     '"itup":(-?[0-9]{1,25}(?:[.][0-9]{1,10})?)[,}]')::numeric AS base_idx_tuples,
           substring(pay.payload from '"at":"([^"]{1,40})"')            AS base_at,
           -- Two passes, in this order: a well-formed payload goes first, so
           -- that human text on the same line survives, and only a leftover
           -- marker is then removed to the end of its line.
           regexp_replace(
             regexp_replace(coalesce(c.cmt, ''),
                            '[[:space:]]*@btmaint:\{[^}]*\}', '', 'g'),
                            '[[:space:]]*@btmaint:[^\n]*', '', 'g')      AS user_cmt
      FROM cand c
      CROSS JOIN LATERAL (
           SELECT substring(c.cmt from '@btmaint:(\{[^}]*\})') AS payload) pay
),
gate AS MATERIALIZED (
    SELECT s.*,
           p.bs, p.grow_ratio, p.tuple_ratio, p.wasted_max,
           p.bs - p.page_header - p.btree_special AS leaf_cap,
           COALESCE(s.fillfactor_opt, 90)         AS fillfactor,
           CASE WHEN s.cmt IS NULL OR s.cmt !~ '@btmaint:'   THEN 'absent'
                WHEN s.pv IS DISTINCT FROM p.fmt
                  OR s.base_bytes IS NULL
                  OR s.base_tuples IS NULL
                  OR s.base_idx_tuples IS NULL               THEN 'invalid'
                ELSE 'ok' END                                AS baseline,
           -- reltuples is -1 on a relation no ANALYZE, VACUUM or index build
           -- has counted since PostgreSQL 14; 12 and 13 leave 0 there instead
           (s.cur_tuples < 0)                                AS tuples_unknown,
           (s.cur_idx_tuples < 0)                            AS idx_tuples_unknown
      FROM parsed s CROSS JOIN params p
),
decided AS MATERIALIZED (
    SELECT g.*,
           CASE WHEN g.base_bytes > 0
                THEN round(g.cur_bytes / g.base_bytes, 4) END AS size_ratio,
           CASE WHEN g.base_tuples > 0 AND NOT g.tuples_unknown
                THEN round(g.cur_tuples / g.base_tuples, 4) END AS tuple_ratio_now,
           CASE WHEN g.base_idx_tuples > 0 AND NOT g.idx_tuples_unknown
                THEN round(g.cur_idx_tuples / g.base_idx_tuples, 4) END
                                                              AS idx_tuple_ratio_now,
           (g.baseline = 'ok' AND g.base_bytes > 0
            AND g.cur_bytes >= g.base_bytes * g.grow_ratio)     AS size_gate,
           (g.baseline = 'ok' AND NOT g.tuples_unknown
            AND g.base_tuples >= 0
            AND (CASE WHEN g.base_tuples = 0
                      THEN g.cur_tuples > 0
                      ELSE abs(g.cur_tuples - g.base_tuples)
                           >= g.base_tuples * g.tuple_ratio END))  AS tuple_gate,
           -- The index's own entry count, gated exactly like the table's.  A
           -- partial index's population is not its table's population, which
           -- is the whole reason this test is separate.
           (g.baseline = 'ok' AND NOT g.idx_tuples_unknown
            AND g.base_idx_tuples >= 0
            AND (CASE WHEN g.base_idx_tuples = 0
                      THEN g.cur_idx_tuples > 0
                      ELSE abs(g.cur_idx_tuples - g.base_idx_tuples)
                           >= g.base_idx_tuples * g.tuple_ratio END)) AS idx_tuple_gate,
           (g.baseline = 'ok' AND g.base_bytes > 0
            AND g.cur_bytes < g.base_bytes)                     AS shrank
      FROM gate g
),
staged AS MATERIALIZED (
    SELECT d.*,
           CASE WHEN NOT d.owns_index                    THEN 'blocked'
                WHEN d.baseline <> 'ok'                  THEN 'initialize'
                WHEN d.shrank                            THEN 'refresh'
                WHEN d.size_gate OR d.tuple_gate
                  OR d.idx_tuple_gate                    THEN 'measure'
                ELSE 'skip' END                          AS stage
      FROM decided d
)
SELECT /* wiki_btmaint_snapshot_12_17 */
       array_agg(s.idx_oid  ORDER BY s.cur_bytes DESC, s.idx_oid),
       array_agg(s.stage    ORDER BY s.cur_bytes DESC, s.idx_oid),
       array_agg(s.leaf_cap ORDER BY s.cur_bytes DESC, s.idx_oid),
       array_agg(s.fillfactor::numeric ORDER BY s.cur_bytes DESC, s.idx_oid),
       array_agg(s.bs       ORDER BY s.cur_bytes DESC, s.idx_oid)
  INTO v_oid, v_stage, v_leafcap, v_ff, v_bs
  FROM staged s
 WHERE s.stage <> 'skip';

FOR i IN 1 .. COALESCE(array_length(v_oid, 1), 0) LOOP
    -- Re-read the index under its own lock-free catalog snapshot.  A row that
    -- has gone is a dropped index, and a dropped index is not an error here.
    SELECT n.nspname, c.relname, pg_relation_size(c.oid), t.reltuples::numeric,
           c.reltuples::numeric,
           regexp_replace(
             regexp_replace(COALESCE(d.description, ''),
                            '[[:space:]]*@btmaint:\{[^}]*\}', '', 'g'),
                            '[[:space:]]*@btmaint:[^\n]*', '', 'g')
      INTO r_nsp, r_idx, r_bytes, r_tuples, r_itup, r_user
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_index x     ON x.indexrelid = c.oid
      JOIN pg_class t     ON t.oid = x.indrelid
      LEFT JOIN pg_description d ON d.objoid = c.oid
                               AND d.classoid = 'pg_class'::regclass
                               AND d.objsubid = 0
     WHERE c.oid = v_oid[i];
    IF NOT FOUND OR r_bytes IS NULL THEN
        RAISE NOTICE 'btmaint: index % gone since the snapshot, skipped', v_oid[i];
        CONTINUE;
    END IF;

    r_act := v_stage[i];
    IF r_act = 'blocked' THEN
        n_block := n_block + 1;
        RAISE NOTICE 'btmaint: %.% not owned by %, no comment written',
                     r_nsp, r_idx, current_user;
        CONTINUE;
    END IF;

    IF r_act = 'measure' THEN
        r_tdens := (v_leafcap[i] - (v_bs[i] * (100 - v_ff[i])) / 100) / v_leafcap[i];
        BEGIN
            SELECT round(100 * (GREATEST(round(s.leaf_pages * v_leafcap[i] * r_tdens)
                                         - round(s.leaf_pages * v_leafcap[i] *
                                            CASE WHEN s.leaf_pages > 0
                                                  AND s.avg_leaf_density <> 'NaN'::float8
                                                 THEN (s.avg_leaf_density / 100)::numeric
                                                 ELSE 0::numeric END), 0)
                                + (s.empty_pages + s.deleted_pages) * v_bs[i])
                       / NULLIF(s.index_size, 0), 1)
              INTO r_wasted
              FROM pgstatindex(v_oid[i]::regclass) s;
        EXCEPTION WHEN OTHERS THEN
            n_err := n_err + 1;
            RAISE WARNING 'btmaint: pgstatindex(%.%) failed: %', r_nsp, r_idx, SQLERRM;
            CONTINUE;
        END;
        IF r_wasted IS NOT NULL AND r_wasted > wasted_max THEN
            r_act := 'reindex';
        ELSE
            r_act := 'update';
        END IF;
        RAISE NOTICE 'btmaint: %.% wasted % %% -> %', r_nsp, r_idx,
                     COALESCE(r_wasted::text, 'null'), r_act;
    END IF;

    IF r_act = 'reindex' THEN
        IF n_re >= max_reindex THEN
            RAISE NOTICE 'btmaint: %.% needs a rebuild, max_reindex % reached',
                         r_nsp, r_idx, max_reindex;
            CONTINUE;
        END IF;
        IF NOT dry_run THEN
            EXECUTE format('REINDEX /* wiki_btmaint_reindex */ INDEX %I.%I', r_nsp, r_idx);
            -- The rebuild resized the file and recounted both the heap and the
            -- index, so all three baseline values are re-read after it, not
            -- before.
            SELECT pg_relation_size(c.oid), t.reltuples::numeric, c.reltuples::numeric
              INTO r_bytes, r_tuples, r_itup
              FROM pg_class c
              JOIN pg_index x ON x.indexrelid = c.oid
              JOIN pg_class t ON t.oid = x.indrelid
             WHERE c.oid = v_oid[i];
        END IF;
        n_re := n_re + 1;
    ELSIF r_act = 'initialize' THEN n_init := n_init + 1;
    ELSIF r_act = 'refresh'    THEN n_ref  := n_ref  + 1;
    ELSE                            n_upd  := n_upd  + 1;
    END IF;

    r_cmt := CASE WHEN length(btrim(r_user)) > 0 THEN btrim(r_user) || E'\n' ELSE '' END
             || '@btmaint:{"v":2,"sz":' || r_bytes
             || ',"tup":' || round(GREATEST(r_tuples, -1))
             || ',"itup":' || round(GREATEST(r_itup, -1))
             || ',"at":"' || to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SSOF') || '"}';
    IF NOT dry_run THEN
        EXECUTE format('COMMENT /* wiki_btmaint_comment */ ON INDEX %I.%I IS %L',
                       r_nsp, r_idx, r_cmt);
        COMMIT;
    END IF;
END LOOP;

RAISE NOTICE 'btmaint: reindex=% update=% initialize=% refresh=% blocked=% failed=% dry_run=%',
             n_re, n_upd, n_init, n_ref, n_block, n_err, dry_run;
END
$btmaint$;
```

The pipeline in step 2, from `WITH params AS (` through the end of the `staged`
CTE, is byte-identical to the same region of step 1 - 100 lines, SHA-256
`62225bce7d3e31b9…` in both texts, checked by the scripts on every run. Only the
final `SELECT` differs: step 1 presents the plan to a reader, step 2 hands five
parallel arrays to its driver. The gate is therefore defined once.

### How to read the plan

`action` first. Everything else is the evidence behind it.

| Column | Means | Watch for |
|---|---|---|
| `action` | `reindex`, `update`, `refresh`, `initialize`, `skip`, `blocked` | `blocked` means this session cannot write the comment at all |
| `baseline` | `ok`, `absent`, `invalid` | `invalid` is a marker that could not be parsed; it is replaced, not trusted |
| `size_ratio` | current bytes over stored bytes | `>= 1.20` is the first gate |
| `tuple_ratio_now` | current table `reltuples` over stored | a move of 20 % either way is the second gate |
| `index_tuples`, `baseline_index_tuples`, `idx_tuple_ratio_now` | the index's own `pg_class.reltuples`, now and at baseline, and their ratio | a move of 20 % either way is the third gate; this is the column that sees a partial index drain |
| `avg_leaf_density`, `dead_pages` | straight from `pgstatindex`, present only for measured rows | density is blind to pages holding nothing; `dead_pages` is 100 % waste |
| `wasted_pct` | free bytes beyond a rebuild at this index's own fillfactor, plus every empty and deleted page, over the file | `> 40` is the rebuild decision |
| `notes` | why a row looks odd, and which gates fired | fourteen strings, listed in the ladder below |
| `comment_command`, `reindex_command` | exactly what step 2 will run | `comment_command` is NULL for a `reindex` row, because its new baseline is only known after the rebuild |

### The decision ladder, in order

The first rule that matches decides. This is the order in the `staged` CTE, and
the suite scores it against the same arithmetic computed independently: 126 of
126 agreed on 17.11 and 112 of 112 on 12.2.

| # | Condition | Action | Measures? | Writes? |
|---|---|---|---|---|
| 1 | this session does not own the index | `blocked` | no | no |
| 2 | no readable `@btmaint:` payload, including any v1 payload | `initialize` | no | baseline |
| 3 | the index is *smaller* than its stored baseline | `refresh` | no | baseline |
| 4 | size ratio `>= 1.20`, or table tuples moved `>= 20 %`, or index tuples moved `>= 20 %` | `measure` | one `pgstatindex()` call | see below |
| 5 | none of the above | `skip` | no | no |
| 4a | measured `wasted_pct > 40` | `reindex` | - | `REINDEX`, then the post-rebuild baseline |
| 4b | measured `wasted_pct <= 40` | `update` | - | baseline at current values |

The three tests in rule 4 are an `OR`, so the order among them does not matter,
and each is disabled separately when its input is unusable: a `reltuples` of `-1`
disables that count's test and says so in `notes`, while a stored count of zero
makes any non-zero current count a fire, because an increase from zero has no
finite ratio.

Rule 3 is not in the brief and is needed: something else rebuilt or truncated the
index, the stored size is now too high, and a high baseline can hide real growth
for a long time. It is also how a rebuild gets its new baseline when a
`REINDEX INDEX CONCURRENTLY` was run by hand outside step 2. **No fixture now
exercises it.** The one that did was fixture 121's `nzb_k`, rebuilt while its
table was empty and then reloaded, and 121 is retired; on this run the `refresh`
action count is 0 on both legs. The branch stays in the filed text, and the gap
is filed under [Open Questions](#open-questions).

Rule 4b is the brief's own instruction, and it has a consequence worth saying out
loud: **the baseline ratchets upward**. An index measured at 35 % wasted is not
rebuilt, and its baseline is then reset to the larger current size, so the next
20 % of growth is counted from there. Over several runs a slowly bloating index
needs progressively more absolute growth to be looked at again.

Fourteen `notes` strings exist, and each one is a fact the reader would otherwise
have to guess: `not the index owner: no comment can be written`, `not the table
owner: REINDEX may be refused`, `unreadable @btmaint: payload, replaced`, `table
reltuples unknown: table tuple gate cannot fire`, `index reltuples unknown: index
tuple gate cannot fire`, `baseline table tuple count was zero`, `baseline index
tuple count was zero`, `index smaller than its baseline: rebuilt elsewhere`, `size
gate fired`, `table tuple gate fired`, `index tuple gate fired`, `no leaf pages`,
`fragmented, not wasted space`, and `fillfactor N`. The three "gate fired" strings
replace the previous revision's single `both gates fired`: with three tests, which
one opened the measurement is the interesting part, and every measured row now
names its own reason.

### Why every candidate filter is there

`pgstatindex` raises on four shapes, and one raised error aborts the whole
statement, so each one is excluded before the function is ever reached. The
refusal each filter avoids is in the function's own entry checks:

| Excluded by | Because | Refusal in source |
|---|---|---|
| `a.amname = 'btree'` | the function opens the relation and demands a B-tree index | `relation "%s" is not a btree index` ([pgstatindex.c#IS_BTREE](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L228)) |
| `c.relkind = 'i'` | a partitioned index has no storage, and fails the same test | the same message, through the relkind macro ([pgstatindex.c#IS_INDEX](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L70-L71)) |
| `NOT pg_is_other_temp_schema(...)` | another session's local buffers are not visible | `cannot access temporary tables of other sessions` ([pgstatindex.c#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L230-L238)) |
| `x.indisvalid AND x.indisready AND x.indislive` | an index that is not ready can report a size too low for the table | `index "%s" is not valid` ([pgstatindex.c#indisvalid](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L240-L250)) |

**None of the four refusals is measured any more.** The five non-B-tree indexes, a
partitioned index and its leaf, another session's temporary index and a forged
`indisvalid = false` were page-local acceptance fixtures, removed on 2026-09-14
with the rest; the filters stay in the filed text and the refusals they avoid are
read from source. The loss is filed under [Open Questions](#open-questions),
and it costs one version-local fact the previous run had measured: that the same
`pgstatindex` call which raises on an invalid index in 17.11 returns a row on
12.2.

Two further filters are not about refusals: `nspname NOT IN ('pg_catalog',
'information_schema', 'pg_toast')` keeps the sweep away from catalogs whose
comments are part of the installation, and `(relpersistence <> 'u' OR NOT
pg_is_in_recovery())` keeps it off unlogged indexes on a standby. `pg_relation_size`
itself is safe against a concurrent drop: it opens with `try_relation_open` and
returns NULL rather than raising, so a dropped index leaves the candidate set
quietly ([dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L346-L368)).

### The three gates and the four states that disable them

All three gates are `>=` comparisons on `numeric`, so a ratio of exactly 1.20
fires, and the brief's "20 % or more" is implemented as written on each input.
Four edge states are handled explicitly in the filed text rather than left to
arithmetic: a stored count of zero, on either counter, makes any non-zero current
count a fire, because an increase from zero has no finite ratio; and
`reltuples < 0` - the `-1` that means "no ANALYZE, VACUUM or index build has
counted this relation yet" from PostgreSQL 14 on
([pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L66)) -
disables that counter's gate and says so in `notes`, once for the table's count
and once for the index's own.

**These four states are no longer measured.** Ten forged baselines sat exactly on
and just under each threshold, and two more forged a `reltuples` of `-1` on a
table and on an index; all twelve were page-local acceptance fixtures and the
2026-09-14 pass removed them with the rest. What the numbered suite still shows is
the gate working in aggregate — 126 of 126 decisions on 17.11 equal to the same
arithmetic recomputed independently from the recorded baseline, and 112 of 112 on
12.2 — but no fixture now sits on a boundary, and no fixture now carries an
unknown count. Both losses are filed under [Open Questions](#open-questions).

### The index's own entry count, and who writes it

The third gate is only as fresh as the last writer of `pg_class.reltuples` for the
index, and there are exactly three of them. All three were measured on both
servers, on one 10,000-row table carrying a plain index and a partial index whose
predicate selects one row in five:

| Step | table | plain index | partial index | Writer |
|---|---|---|---|---|
| after both `CREATE INDEX` | - | 10000 | **2000** | `index_update_stats`, an exact count from the build's own scan ([index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2788-L2812)) |
| after `ANALYZE` | 10000 | 10000 | **2000** | `do_analyze_rel`'s per-index update, `ceil(tupleFract * totalrows)` ([analyze.c#same-for-indexes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663)) |
| after deleting 98 % of the subset, then `VACUUM` | 8200 | 8200 | **200** | `update_relstats_all_indexes`, from the AM's own `num_index_tuples` ([vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099)) |
| after a second `ANALYZE` | 8200 | 8200 | 200 | the sample agreed with the exact count |
| after a 10-row `UPDATE` and another `VACUUM` | 8200 | 8200 | 200 | nothing: see the estimated-count rule below |
| after `REINDEX INDEX` on the partial index | - | - | 200 | `index_update_stats` again |

Three properties of those writers decide what the gate can see:

- **ANALYZE estimates a partial index from its sample, and a plain index from the
  table.** `tupleFract` starts at 1.0 for every index and is only refined for an
  index `compute_index_stats` processes, which it does when the index has
  statistics columns *or* a predicate
  ([analyze.c#tupleFract-init](../../../../raw/postgres-17/src/backend/commands/analyze.c#L443-L449),
  [analyze.c#compute_index_stats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L827-L863)).
  For a partial index the fraction is the share of sampled rows that pass the
  predicate, `numindexrows / numrows`
  ([analyze.c#tupleFract-from-sample](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953)).
  So for a plain index the third gate carries no information the second one does
  not; for a partial index it is the only catalog number that moves at all.
- **VACUUM writes an exact count, but only when it is exact.**
  `update_relstats_all_indexes` skips any index whose result came back with
  `estimated_count` set, and `btvacuumcleanup` sets exactly that whenever it runs
  as a cleanup-only scan, because it then counts index items per page rather than
  live TIDs
  ([nbtree.c#btvacuumcleanup-estimated](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L874-L892),
  [nbtree.c#btvacuumpage-counting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1345-L1362)).
  `lazy_cleanup_all_indexes` also marks the count estimated when the heap scan
  skipped pages
  ([vacuumlazy.c#lazy_cleanup_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2349-L2360)).
  The measured 10-row `UPDATE` above is that case: a `VACUUM` ran, and no count
  moved.
- **A VACUUM can skip index vacuuming entirely.** When fewer than
  `BYPASS_THRESHOLD_PAGES`, 2 % of heap pages, hold dead items, `lazy_vacuum`
  bypasses index vacuuming and does cleanup only
  ([vacuumlazy.c#BYPASS_THRESHOLD_PAGES](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L85-L89),
  [vacuumlazy.c#lazy_vacuum-bypass](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1899-L1940)),
  which by the rule above leaves the index's count where it was.

The suite checks the value the heuristic stores against the value the catalog
holds at baseline time, independently of the filed text: **126 of 126 agree on
17.11 and 112 of 112 on 12.2**, and every acted row wrote an `itup` back.

### The simulated auto-analyze the tests now run

The follow-up's second instruction is a property of the *tests*, not of the
heuristic: a fixture that changes more than 10 % of a table's heap tuples must
`ANALYZE` it, because on a server with autovacuum on the launcher would have. The
suite's cluster runs `autovacuum = off` so that nothing moves a fixture between
the baseline, the churn, the decision and the rebuild oracle, so the `ANALYZE`
has to be supplied. This instruction is now rule 3 of the shared suite
definition, and applies to every method scored against it:
[Rule 3 the simulated auto-analyze](../../common-concepts/mandatory-btree-bloat-tests.md#rule-3-the-simulated-auto-analyze).
What this section reports is what the rule did on these two servers.

It is not hand-written per fixture. The new step reads the engine's own counter
and applies the engine's own test:

```text
n_mod_since_analyze > autovacuum_analyze_threshold
                      + autovacuum_analyze_scale_factor * reltuples
```

That is `relation_needs_vacanalyze`'s `doanalyze` verbatim
([autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3060-L3096),
[autovacuum.c#anl-thresholds](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3005-L3018)),
and at the shipped defaults of 50 tuples and 0.1 it is "50 rows plus 10 % of the
table"
([guc_tables.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3367-L3375),
[guc_tables.c#autovacuum_analyze_scale_factor](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3906-L3914),
[config.sgml#autovacuum_analyze_scale_factor](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L8832-L8850)).
Both defaults were read back from each running server: 50 and 0.1 on 12.2 and on
17.11. The counter itself is `pg_stat_all_tables.n_mod_since_analyze`
([system_views.sql#n_mod_since_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L689)),
which the flush adds to and `pgstat_report_analyze` resets
([pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L328-L338),
[pgstat_relation.c#flush-mod_since_analyze](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L845-L860)).

What that decided, per leg, on the 2026-09-16 run, with the maintenance step now
in front of the census:

| | 17.11 | 12.2 |
|---|---|---|
| Fixture tables considered | 88 | 87 |
| Analyzed, because the counter still read past the threshold | **12** | **4** |
| Left alone | 76 | 83 |
| Counter back to zero afterwards | 12 of 12 | 4 of 4 |
| Smallest modified share analyzed | **99.7 %** | **20.0 %** |
| Largest modified share left alone | **0.0 %** | **0.0 %** |
| Analyzed on the 2026-09-14 run, before the maintenance step existed | 66 | 45 |

The census no longer decides the churned tables, because the maintenance step
analyzed them first: not one of the tables it still analyzes was churned. They
are the tables whose build-phase writes reached the shared statistics entry
*after* their build-phase `ANALYZE` reset the counter — `q120` at 99.7 %, `f85t`
at 120.0 % (its build-phase `UPDATE` of 100,000 rows counted twice over),
`f79t`, `f80t`, `f82t` and `f84t` at 100.0 %, the three `INCLUDE` controls
`i101t`, `i103t` and `i105t`, `np` and `pb`, and `x108t`, which no recipe ever
analyzes. The 12.2 leg analyzes four of the same shapes, the smallest of them
`f85t` at 20.0 %. The recheck then re-reads the counter from a new session a
second later, which is how the run proves the `ANALYZE` fired rather than
reporting an intention: **12 of 12 and 4 of 4 back to zero**.

Two honest caveats about the census, both visible in its own output:

- **The counter it reads can be a lap behind.** A backend flushes pending table
  statistics at most once per `PGSTAT_MIN_INTERVAL`, 1000 ms
  ([pgstat.c#PGSTAT_MIN_INTERVAL](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L110-L122),
  [pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L636-L655)),
  and `pgstat_report_analyze` zeroes it while forgetting anything committed
  during the `ANALYZE`
  ([pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L328-L338)).
  That is why 12 tables with no churn at all still read 99.7 % to 120 %
  modified: their `CREATE TABLE AS` or `UPDATE` counts were published after
  their own `ANALYZE`. The census applies the engine's own test to whatever the counter
  says, which is what rule 3 requires, and this page reports the consequence
  rather than tuning it away. The same staleness is why the recheck runs in its
  own session a second later: read immediately, a 12 server's collector file
  still describes the state from before the `ANALYZE`, and an earlier pass of
  this review duly reported "0 of 6 counters reset" on a census that had just
  reset six.
- **It still re-analyzes five of the eight false-positive fixtures** on 17.11,
  and two on 12.2. Their
  point is misleading *statistics*, and a second `ANALYZE` at the default target
  recomputes them; the fixtures survive as shapes because none of them is
  measured anyway - all seven skipped fixtures stay skipped, and the eighth is
  fixture 84, whose catalog forgery is written after the census so that no
  `ANALYZE` can repair it.

### How wasted space is computed

`pgstatindex` reports one density number for the whole index: `100 - free_space /
max_avail * 100` over live leaf pages only, where `max_avail` is
`BLCKSZ - (BLCKSZ - pd_special + SizeOfPageHeaderData)` per leaf page, and
`NaN` when there are no leaf pages at all
([pgstatindex.c#avg_leaf_density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L372),
[pgstatindex.c#max_avail](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L308-L324)).
Wasted space is therefore built from three measured quantities, and measured
against a rebuild at the index's *own* fillfactor, so a correctly built index
reports no waste whatever its fillfactor:

```text
leaf_cap       = block_size - 24 - 16                     -- header, special area
target_density = (leaf_cap - block_size * (100 - fillfactor) / 100) / leaf_cap
wasted_bytes   = GREATEST(leaf_pages * leaf_cap * target_density
                          - leaf_pages * leaf_cap * density, 0)
                 + (empty_pages + deleted_pages) * block_size
wasted_pct     = 100 * wasted_bytes / index_size
```

The two constants are the page header and the B-tree special area, and the target
is the same `BLCKSZ * (100 - fillfactor) / 100` the builder itself leaves on a leaf
page ([nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1145),
[nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L645-L671)).
The leaf term is clamped at zero because an index denser than its target is not
holding negative waste, while empty and deleted pages count in full - they hold
nothing at any fillfactor. `index_size` is `pgstatindex`'s own count of every
page including the metapage
([pgstatindex.c#index_size](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L350-L357),
[pgstattuple.sgml#metapage](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L268-L273)).
This is the definition the sibling page
[B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17
(unverified)](btree-bloat-with-pgstatindex.md#follow-up-wasted-space-measured-against-the-fillfactor)
settled on, reused here unchanged so the two pages measure the same thing.

**The nine-point curve that used to calibrate this threshold is gone.** Nine
500,000-row tables drained by a known fraction, each with a stored baseline, put
`wasted_pct` at `0.888 × fraction deleted` across the range and placed the 40 %
decision at 45.0 % of entries deleted. Those nine tables were page-local
acceptance fixtures, removed on 2026-09-14, so the page no longer measures where
the threshold lands; the formula above is a reading of the filed text and of
`pgstatindex`, and the calibration behind the 40 % choice is filed under
[Open Questions](#open-questions). What the numbered suite still gives is the
scatter around it: 103 scored measurements on 17.11, mean error `+7.6` points
against the rebuild oracle, 101 of them within 15.

### What the gate can and cannot see

The index-count gate is what makes the difference on a partial index, and the
numbered suite still measures that. Recomputing the two-gate form on the same
fixtures, **20 of 126 on 17.11 and 19 of 112 on 12.2 are measured that two gates
would have skipped**, and 15 of them on each leg are genuinely reclaimable, at a
mean measured reclaim of 86.7 % and 86.3 %:

| Family the two-gate form would lose | Fixtures | Why | `idx_tuple_ratio` | Outcome now |
|---|---|---|---|---|
| The subset drained, the table did not | `p113b`, `p114` | `tuple_ratio` 1.0000 on both | 0.0000, 0.0103 | rebuilt at 100.0 % and 98.9 % measured reclaim |
| The table moved 15-19 %, the index lost 75-95 % | `p73`-`p75`, `p77`, `f86`-`f91`, `i100`, `b92`-`b95` | the table's count moved 18 %, two points under the gate | 0.0484 to 0.5664 | all measured; all rebuilt, 40.5 % to 94.2 % |
| The subset shrank by a quarter | `p72` | the same arithmetic, smaller | 0.7478 | measured, 22.2 % wasted, correctly left alone |
| A forged or resampled count | `f84`, `p120` | 84's forged index count, 120's resampled partial estimate | 0.0500, - | measured, 0.1 % and 5.9 % wasted, both left alone; 120 scores nothing on this leg |

The second family is the sharpest illustration of why the table's count is the
wrong input: deleting 90 % of a subset that is 20 % of the table moves the
table's count by exactly 18 %, and the gate needs 20 %. Four of those fixtures
(`b92`-`b95`) are the suite's own threshold-calibration controls, built to sit
just under a threshold, and the index's own count moves from 1.0000 to about 0.10
on exactly the same churn.

### The blind spot that left with its fixtures

What the gate cannot fix is a file whose entries are dead but still physically
present. `pgstatindex` counts item pointers, not live tuples, so such a file reads
dense and `wasted_pct` reads near zero while a rebuild would empty it. The
previous run measured exactly that on four fixtures — `p113a`, `p113c`, `p65` and
`p67`, opened by the index-count gate, read at 0.0 % to 0.1 % wasted, rebuilt at
89.1 % to 100.0 % — and scored them `FALSE NEGATIVE`.

All four are retired. The concept page's maintenance assumption rules the shape
out of the suite: every churn is followed by maintenance, the fixtures that
withheld it are retired, and it "scores no method against an index whose dead
entries were never vacuumed"
([Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md#interactions-with-other-concepts)).
The concept page files the consequence as an open question of its own: a method
that misreads a not-yet-vacuumed index now passes the suite.

This heuristic is such a method, and this page says so rather than reporting a
clean sheet. Nothing in either filed text changed; `pgstatindex` has no output
column that separates a dead entry from a live one, so no threshold on its numbers
can catch the shape; and the fourth input that could — the stored entry count
against the leaf-page capacity the file implies, or `n_dead_tup` on the table — is
not in the brief and is not implemented. The state is still reachable in
production, under a `VACUUM` that declined to remove the entries: the index-vacuum
bypass applies when fewer than 2 % of heap pages hold dead items, among three
other conditions
([vacuumlazy.c#BYPASS_THRESHOLD_PAGES](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L85-L89),
[vacuumlazy.c#lazy_vacuum-bypass](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1899-L1940)).

### The comment survives both REINDEX forms

**The measurement behind this section is gone.** Two indexes on one table carried
the same comment through `REINDEX INDEX` and `REINDEX INDEX CONCURRENTLY`, with
the OIDs and the comment md5 recorded before and after on both servers: the plain
form kept its OID, the concurrent form moved from 18147 to 18149 on 17.11 and from
17415 to 17417 on 12.2, and the comment md5 was unchanged in all four cases. Those
were page-local acceptance fixtures, removed on 2026-09-14. The claim now rests on
source, and the loss is filed under [Open Questions](#open-questions) — it matters
more than most, because comment survival is what makes a comment-stored baseline
viable at all.

The plain form keeps the same `pg_class` row and only swaps the relfilenode, so a
comment keyed by the index OID cannot move
([index.c#reindex_index-locks](../../../../raw/postgres-17/src/backend/catalog/index.c#L3600-L3612),
[index.c#reindex_index-index_build](../../../../raw/postgres-17/src/backend/catalog/index.c#L3786-L3790)).
The concurrent form builds a new index and swaps, and the comment survives only
because `index_concurrently_swap` explicitly rewrites the `pg_description` row's
`objoid` under `RowExclusiveLock`, taking the first match and stopping
([index.c#index_concurrently_swap-comment](../../../../raw/postgres-17/src/backend/catalog/index.c#L1740-L1784)).
The OID change the retired fixture recorded is what proved it was the second path.

One thing the rebuild does that the brief does not mention: it refreshes both row
counts. `index_build` calls `index_update_stats` twice, once for the heap with the
tuples its scan counted and once for the index
([index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3129-L3134),
[index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2788-L2812)).
Measured on both servers: the table's `reltuples` reads `-1` on 17.11 (`0` on
12.2) after `CREATE TABLE` and after 1,000 inserts, then **1000 after `CREATE
INDEX`**, 1000 after `ANALYZE`, `-1` again on 17.11 (`0` on 12.2) after
`TRUNCATE`, and **2000 after `REINDEX`** once 1,000 more rows were added. The
index's own count behaves the same way and is exact after either build: a partial
index reads 2000 of a 10,000-row table after `CREATE INDEX`, and 200 after a
`REINDEX` that followed a drain. That is why step 2 re-reads **all three** values
*after* the rebuild rather than before: the post-rebuild baseline it stores is
two counted numbers and a file size, not an estimate.

### Privileges: measure, rebuild, write the baseline

Three different permissions, and they do not line up:

| Operation | Requirement | Where that comes from |
|---|---|---|
| `pgstatindex()` | `EXECUTE`, revoked from `PUBLIC`, granted to `pg_stat_scan_tables` | [pgstattuple--1.4--1.5.sql#pgstatindex-grant](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L91-L92) |
| `REINDEX INDEX` | `MAINTAIN` on the table from v16; ownership before | [indexcmds.c#RangeVarCallbackForReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2905-L2912) |
| `COMMENT ON INDEX` | ownership of the index, always | [objectaddress.c#check_object_ownership](../../../../raw/postgres-17/src/backend/catalog/objectaddress.c#L2387-L2400) |
| The heuristic's own verdict | `owns_index` | the filed statement's rule 1, `blocked / not the index owner: no comment can be written` |

**No non-owner role is created any more.** A role holding only `SELECT` on the
table plus `EXECUTE` on `pgstatindex` measured every cell of that table on both
servers, including the `permission denied for index` that turned into an accepted
`REINDEX` after `GRANT MAINTAIN` while `COMMENT` stayed refused, and it was a
page-local acceptance fixture removed on 2026-09-14. Whether `MAINTAIN` exists at
all is still measured, by `stage_facts`: accepted on 17.11, `unrecognized
privilege type: "MAINTAIN"` on 12.2. The rest of the loss is filed under
[Open Questions](#open-questions).

So on 17 a `MAINTAIN` grantee can rebuild an index it may not comment on, which
would rebuild the file and then lose the new baseline; the heuristic refuses the
whole row instead and says why. The asymmetry is in the source: `REINDEX` checks
`pg_class_aclcheck(table, ACL_MAINTAIN)`
([indexcmds.c#RangeVarCallbackForReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2905-L2912),
[reindex.sgml#MAINTAIN](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml#L300-L316)),
while `COMMENT` calls `check_object_ownership`, which for an index is
`object_ownercheck(RelationRelationId, ...)`
([comment.c#CommentObject](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L78),
[objectaddress.c#check_object_ownership](../../../../raw/postgres-17/src/backend/catalog/objectaddress.c#L2387-L2400),
[comment.sgml#owner](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L100-L102)).

The text also carries an `owns_table` test, which cannot differ from `owns_index`
in practice: `ALTER INDEX ... OWNER TO` refuses to change an index's owner, with
the hint to change the table's ownership instead
([tablecmds.c#ATExecChangeOwner-index](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14544-L14561)).
The retired acceptance fixtures measured that warning and counted zero
owner-mismatched indexes in either database; the test stays as a cheap guard, not
because it is reachable.

### Locks, transactions and the two commands a DO block cannot reach

| Statement | Lock it takes | Source |
|---|---|---|
| `COMMENT ON INDEX` | `ShareUpdateExclusiveLock` on the index, held to commit | [comment.c#CommentObject](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L78), [comment.sgml#lock](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L95-L98) |
| `REINDEX INDEX` | `AccessExclusiveLock` on the index, `ShareLock` on the table | [index.c#reindex_index-locks](../../../../raw/postgres-17/src/backend/catalog/index.c#L3600-L3612), [indexcmds.c#ReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2822-L2829) |

The `pg_locks` probe that read `ShareUpdateExclusiveLock on e_none` back inside an
open transaction was a page-local acceptance fixture and is gone; both rows are
now source only.

`ShareUpdateExclusiveLock` conflicts with itself and with everything above it, so
two concurrent runs of step 2 serialize on the comment rather than corrupting it,
and a run blocks behind `VACUUM` or `CREATE INDEX CONCURRENTLY` on the same index
([lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L76-L80)).
`lock_timeout = '5s'` is what turns that wait into a reported failure instead of a
stall.

Three refusals shape step 2's design, all measured identically on 12.2 and 17.11:

- `REINDEX INDEX CONCURRENTLY` inside a `DO` block: `REINDEX CONCURRENTLY cannot
  be executed from a function`. Plain `REINDEX INDEX` is accepted. The concurrent
  form is refused because `ExecReindex` calls `PreventInTransactionBlock`
  ([indexcmds.c#ExecReindex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2736-L2738)),
  so an operator who needs the online form runs the `reindex_command` column of
  step 1 at the top level and lets the next run's rule 3 store the new baseline.
- `VACUUM` inside a `DO` block: `VACUUM cannot be executed from a function`.
  That is why the suite's own drains are generated and executed one statement at
  a time rather than looped inside a procedure.
- `COMMENT ON INDEX x IS 'a' || 'b'`: `syntax error at or near "||"`. The comment
  text is a string literal in the grammar, never an expression
  ([gram.y#comment_text](../../../../raw/postgres-17/src/backend/parser/gram.y#L7219-L7222)),
  which is the whole reason step 1 cannot write a post-rebuild baseline and step 2
  has to build the literal in PL/pgSQL and `EXECUTE` it.

### What it costs to run

Measured six times in each state on a database holding 133 B-tree indexes and
521 MB of index files on 17.11, 119 indexes and 534 MB on 12.2. The gated state
is forged by halving every stored `sz` while leaving both counts current, so it
isolates one gate and reads every gated index end to end:

| State | Gated indexes | Wall time, six runs | Buffers |
|---|---|---|---|
| Settled, 17.11 | 0 of 133 | 27.5 - 35.8 ms | 3,305 hit, 0 read |
| Every baseline halved, 17.11 | 126 of 133 | 153.8 - 179.4 ms | 15,810 hit, 54,442 read |
| Settled, 12.2 | 0 of 119 | 22.4 - 25.5 ms | 2,333 hit, 0 read |
| Every baseline halved, 12.2 | 112 of 119 | 121.9 - 157.9 ms | 14,350 hit, 56,371 read |

The third gate costs no data-page reads, which is the structural point: it reads
one more column from a `pg_class` row the statement already has. The settled
readings are **0 reads** on both servers, at 3,305 buffer hits on 17.11 and 2,333
on 12.2 for a sweep of 133 and 119 indexes - seven of them the harness's own
primary keys, which is four more than the 2026-09-14 run swept because this
revision added four bookkeeping tables. The fully gated state touches about
70,000 buffers on each leg, and the hit/read split moves between runs with what
shared buffers already held; the wall times are higher than the 2026-09-14 run's
because the two legs were measured while sharing 22 cores. `pgstatindex` reads
every page of every index it is called on, through a `BAS_BULKREAD` strategy ring
([pgstatindex.c#bstrategy](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L215-L222),
[pgstatindex.c#scan-loop](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L278-L331)).
A scheduled run in a healthy database is therefore a catalog query, and the
expensive path is entered only for indexes that moved.

### What the 2026-09-14 re-port changed, and why

**Neither filed text changed.** Both SQL blocks hashed to the same SHA-256 values
this page has carried since 2026-09-11, and both leg scripts re-checked that
before running. Everything below is a change to the tests or to the page.

| Change | Where | Why |
|---|---|---|
| Tests 11, 38, 65, 67, 69, 106, 117 and 121, and legs 113a and 113c, deleted with their recipes | both leg scripts | the concept page retired them; explicit deduplication settings are outside the suite, and withheld maintenance is no longer a fixture shape |
| `churn_v13.sql` deleted | both leg scripts | its only content was test 38's drain |
| The whole page-local acceptance stage deleted: `stage_edge`, its four SQL files, the `edge` database, and its section of the criteria file | both leg scripts | the asker's direction, "remove them all" |
| The maintenance assumption **not** applied | both leg scripts | the asker's direction, "retire only"; the departure is named in [The ported mandatory suite](#the-ported-mandatory-suite) and filed under [Open Questions](#open-questions) |
| `check_server_errors` repaired | both leg scripts | its pattern looked for the severity straight after the log time zone, which the default `%m [%p] ` prefix never produces, so it matched nothing and reported a clean log unconditionally |
| The allowed-error list rewritten, and the matched-line count reported | both leg scripts | with the acceptance fixtures gone the deliberate errors are only the `stage_facts` probes and the two feature-gated fixture files; printing the total makes a check that matches nothing visible |
| Every claim backed by a removed fixture deleted or demoted to source | this page | a measurement whose fixture no longer exists is not a measurement |

### What the 2026-09-16 review changed, and why

**Neither filed text changed again.** Both SQL blocks hash to the same SHA-256
values as on 2026-09-11, and both leg scripts re-check that before running.
Everything below is a change to the tests, to the harness, or to this page.

| Change | Where | Why |
|---|---|---|
| A maintenance step: `VACUUM (VERBOSE, ANALYZE)` on every table the churn touched, between the churn and the census | both leg scripts | the concept page's maintenance assumption, which the 2026-09-14 pass did not apply |
| The churned-table set computed from `pg_stat_all_tables` write counters taken before and after the churn phase | both leg scripts | "the tables its churn touched" has to be the engine's record, not a list a new fixture can fall out of |
| The uniform drain's own `VACUUM` and `ANALYZE` removed from the churn file | both leg scripts | they were the maintenance; it now happens in one place where its timeouts, horizon and output are recorded |
| A horizon probe before every maintenance statement and around the census, reading `pg_stat_activity`, `pg_replication_slots` and `pg_prepared_xacts` | both leg scripts | proof 3 of the no-defeat rule |
| The `VERBOSE` output parsed per table into a recorded `dead but not yet removable` count, with a version-local parse on each leg | both leg scripts | proof 2, and the 12 server words it differently |
| `pgstatindex` page classes recorded for every fixture index after the maintenance | both leg scripts | proof 4, the visible trace of what the maintenance did |
| Every session that issues a `VACUUM` or an `ANALYZE` forces its timeouts to 0, and the settings in force are recorded | both leg scripts | the fifth forbidden state; the previous run's churn sessions ran at `lock_timeout = '5s'` |
| A run that finds a defeated maintenance now **fails** instead of scoring | both leg scripts | the rule says such a fixture is repaired and re-run, not scored |
| Fixture 120's precondition asserted, and an `UNMET PRECONDITION` verdict that every scored count excludes | both leg scripts | the concept page's own requirement for that fixture, which the previous run did not check |
| A publication invariant that excludes tables a recipe analyzed itself | both leg scripts | its first form failed the run on nine tables whose own recipe had consumed the counter legitimately; see below |
| `stage_check` creates its output directory | both leg scripts | starting from a built tree skipped `stage_build`'s `mkdir`, so a `check` run wrote every result into a directory that did not exist and reported an empty check section |
| The harness gained `churn_seen`, `maint`, `horizon`, `pageclass` and `precond`, and the verdict view gained `scored`, `maintained` and the proof columns | both leg scripts | so that every number above is a row someone can re-read, not a line in a log |

**The publication invariant is the one place this review had to change its own
mind.** The first form failed any maintained table whose `n_mod_since_analyze`
was zero, on the theory that the churn had not been published. It fired on six
tables on 17.11 and nine on 12.2 — `pc68`, `pb76`, `np99t`, `q113b`, `q114`,
`f90t` and friends — and every one of them was a recipe that runs its own
`VACUUM` and `ANALYZE` after its own writes, so the counter had been published
and then consumed, exactly as `pgstat_report_analyze` does
([pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L328-L338)).
Membership of the maintained set is itself the publication proof, because that
set comes from write counters only a flush can move; what the check now adds is
the narrower case of a table with neither a published counter nor an `ANALYZE`
of its own. **23 tables on each leg** are in the recipe-analyzed class, and the
invariant passes on both.

### Two defects the first revision's suite found

**The gate did not gate.** The first filed text measured with
`LEFT JOIN LATERAL (SELECT * FROM pgstatindex(...) WHERE stage = 'measure')`,
which reads correctly and is wrong: a set-returning function in `FROM` is
executed into a tuplestore and the qualification is applied to the rows it
produced, not before it runs
([nodeFunctionscan.c#FunctionNext](../../../../raw/postgres-17/src/backend/executor/nodeFunctionscan.c#L59-L112),
[execScan.c#ExecScan](../../../../raw/postgres-17/src/backend/executor/execScan.c#L164-L205)).
The cost stage caught it: a *settled* database, with nothing to do, read 57,964
buffers. The repair makes the gated rows the lateral's input relation - a
`MATERIALIZED` CTE of the rows whose stage is `measure`, joined laterally, with
the rest added back by `UNION ALL` - and the settled reading fell to 3,542 hits
and zero reads.

**A malformed marker was kept as if it were a human note.** The payload stripper
matched `@btmaint:\{[^}]*\}` only, so a payload with no closing brace, and
`@btmaint:not json at all`, survived the rewrite and were carried forward as the
user's own text. The repair is two passes in one expression: a well-formed payload
is removed first, so human text on the same line survives, and only then is any
leftover marker removed to the end of its line.

Both repairs are in the filed texts. The fixtures that found the second one, and
the byte counts they measured, were page-local acceptance fixtures and were
removed on 2026-09-14, so the repair is now visible only in the published text of
step 2; that is the largest single item under
[Open Questions](#open-questions). The 2026-09-11 re-measurement found no new
defect in the two texts; it did find one in the census step, a
`round(double precision, integer)` error from multiplying a `numeric` scale factor
by a `real` `reltuples`, which aborted the first census run and is fixed by
casting the count in both leg scripts. The 2026-09-14 pass found one more, in the
harness rather than in the texts: see `check_server_errors` in
[What the 2026-09-14 re-port changed, and why](#what-the-2026-09-14-re-port-changed-and-why).

### What is version-local between 12 and 17

The two texts are identical on both servers; what differs is around them. Every
row was discovered by the scripts on the running server, not assumed:

| Fact | 17.11 | 12.2 | Consequence for the design |
|---|---|---|---|
| Filed texts execute unmodified | yes | **yes**, exit 0, two baselines written, second run a no-op | the compatibility claim |
| `WITH ... AS MATERIALIZED` | accepted | accepted | the gate's optimization fences |
| `pg_input_is_valid()` | 1 `pg_proc` row | **0** | payload is parsed by regex, not by a guarded cast |
| `MAINTAIN` privilege | exists | `unrecognized privilege type: "MAINTAIN"` | no privilege name may appear in the portable text |
| `deduplicate_items` reloption | accepted | `unrecognized parameter` | no fixture depends on it since tests 11 and 38 were retired |
| B-tree support function 4 | accepted | `invalid function number 4, must be between 1 and 3` | nine fixtures skipped on 12 |
| ICU collations | accepted | `ICU is not supported in this build` | five fixtures skipped on 12 |
| `reltuples` on an uncounted table | `-1` | `0` | the `tuples_unknown` branch fires only from v14; on 12 a zero is ambiguous |
| `COMMIT` inside `DO` at top level | accepted | accepted | one transaction per index |
| `pgstattuple` extension version | 1.5 | 1.5 | same `pgstatindex(regclass)` signature |
| Index `reltuples` after `CREATE INDEX`, plain and partial | 10000, 2000 | 10000, 2000 | the third gate's baseline is an exact count on both |
| Index `reltuples` after `ANALYZE`, plain and partial | 10000, 2000 | 10000, 2000 | a partial index is estimated from the sample on both |
| Index `reltuples` after a drain and `VACUUM` | 8200, 200 | 8200, 200 | the third gate sees the drain on both |
| `autovacuum_analyze_threshold`, `autovacuum_analyze_scale_factor` | 50, 0.1 | 50, 0.1 | the 10 % test the mandatory tests simulate is the same on both |
| `pg_stat_force_next_flush()` | 1 `pg_proc` row | **0** | the census waits a second and reads from a new session instead |

The v12 side of each source claim is on the v12 pages rather than cited here, as
this page may only cite `raw/postgres-17/`: [How pgstatindex Calculates B-Tree
Index Statistics in PostgreSQL 12
(unverified)](../../../v12/questions/indexing/how-pgstatindex-calculates-information.md),
[All Outcomes That Leave an Invalid Index in PostgreSQL 12, Including a Failed
CREATE INDEX CONCURRENTLY
(unverified)](../../../v12/questions/indexing/invalid-index-outcomes.md),
[Physical Index Statistics, Tuple Counts, and Bytes per Tuple in PostgreSQL 12
(unverified)](../../../v12/questions/indexing/physical-index-statistics-tuple-counts-and-bytes.md),
and [Calibrating a COMMENT-Stored Bytes-per-Table-Tuple REINDEX Threshold for
Every Non-B-Tree Index in PostgreSQL 12
(unverified)](../../../v12/questions/indexing/comment-stored-bytes-per-table-tuple-non-btree.md).

### The ported mandatory suite

The suite itself - its six fixture families, its three porting rules, its
`REINDEX INDEX` oracle and its four verdict bands - is defined once for this
version in
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md),
and is not restated here. What follows is only what is local to this page: which
of that suite's fixtures this heuristic was scored on, and where this run departs
from the shared definition.

**Every numbered test the concept page still defines is ported**, recipe by
recipe, and scored against this heuristic instead of against an estimator: tests
1-17, 18-91 and controls 92-120, less the numbers that page retired. Rule 1 (split
each recipe at the index build) is carried out by the filed apply block, which
stores the as-built baseline in every comment between the build file and the churn
file. Rule 2 (the uniform heap-block drain, with 70-71, 78-85, 96-97, 101-105,
108-112, 116 and 120 exempt) and rule 3 (the simulated auto-analyze, applied
through the engine's own threshold; see
[The simulated auto-analyze the tests now run](#the-simulated-auto-analyze-the-tests-now-run))
are applied as the concept page specifies, with no fixture-level exceptions beyond
that exempt list.

**What the 2026-09-14 pass retired.** Fourteen fixture indexes left the 17 leg and
ten left the 12 leg, each deleted with its recipe rather than skipped, and the
numbers are not reused:

| Retired | Fixtures here | Why the concept page retired it |
|---|---|---|
| 11 | `i_dupoff`, `i_text_off`, `i2_off` | explicitly setting `deduplicate_items` is outside the suite |
| 38 | `p38` | the same, on a partial index |
| 65, 67 | `p65`, `p67` | rows left the index with no `VACUUM` after them |
| 69, 106, 117 | `p69`, `x106`, `p117` | the recipe ended on a `VACUUM` with no `ANALYZE` |
| 113a, 113c | `p113a`, `p113c` | a drained queue with no `VACUUM`, and one with an `ANALYZE` only |
| 121 | `nz_k`, `nzb_k`, `i_trunc` | three ways to leave a stale count, each withholding a maintenance command |

Tests 11 and 38 were the only fixtures on either leg that needed the
`deduplicate_items` reloption, so the 12 leg's skip list is down from 18 fixtures
to 14: nine for B-tree support function 4 and five for ICU.

**The departure the previous run recorded is closed.** The concept page's
[maintenance assumption](../../common-concepts/mandatory-btree-bloat-tests.md#the-maintenance-assumption)
requires every fixture to run `VACUUM ANALYZE` on the tables its churn touched
before the decide phase, and the 2026-09-14 pass did not do it. This run does:
see [The maintenance the suite now runs](#the-maintenance-the-suite-now-runs).
The ten recipes that used to reach the decide phase with an unmaintained tail —
64, 66, 92 to 95, 98, 115, 118 and 119 — are maintained like every other churned
fixture, and the suite as run is now the concept page's fixture *set* under its
rules 1 to 3 **and** its maintenance assumption, with the no-defeat rule proved
rather than assumed.

Rule 3 still costs coverage, and the cost is named here rather than hidden. Every
surviving fixture whose point was a stale count is now analyzed by the
maintenance step itself, not by the census: 64 `stale statistics after inserts
into the subset`, 85 `stale table statistics`, 98 `plain index, stale row counts
after 300,000 inserts` and 115 `index built on an analysed empty table, then
loaded`. Those fixtures test the heuristic against *fresh* statistics, which is
what a production server with autovacuum on would give it. One stale-count shape
survives by forgery — fixture 84's partial-index count, written after the census,
which no `ANALYZE` can repair — and one survives on its own: `pb72` deleted
25,000 of 475,000 rows and is vacuumed, but its 5.3 % modification share stays
under rule 3's threshold, so the maintenance `ANALYZE` is the only thing that
re-reads it. The two forged `reltuples = -1` fixtures that used to cover the
unknown-count shape were page-local and are gone.

### The maintenance the suite now runs

One step, between the churn and the census, on every table the churn touched.
Three properties matter, and each is a decision this page made rather than
inherited:

| Property | What the step does | Why |
|---|---|---|
| Which tables | every table whose `n_tup_ins`, `n_tup_upd` or `n_tup_del` moved across the churn phase, read from `pg_stat_all_tables` before the first churn statement and after the last ([system_views.sql#n_tup_del](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L680-L682)) | the concept page says "the tables it touched are the ones whose rows it inserted, deleted or updated"; taking that from the engine's own counters means a fixture added later cannot fall out of a hand-written list. **66 tables on 17.11, 65 on 12.2**, of 88 and 87 fixture tables |
| Which statement | `VACUUM (VERBOSE, ANALYZE)` per table, one statement at a time, because `VACUUM` cannot run inside a transaction block | `VACUUM ANALYZE` leaves `ANALYZE` as the last writer of every `reltuples` on the table, which is what the concept page's assumption credits; `VERBOSE` is what makes proof 2 below a number rather than a hope |
| Which tables are left alone | every table with no churn: the whole of family 3, the fresh controls, 70 and 71 | an extra `ANALYZE` would repair the deliberately stale statistics those fixtures exist to build, and an extra `VACUUM` would disturb a deliberately fresh index. The concept page says so too: a fixture with no churn carries its build-phase `ANALYZE` into the decide phase |

What the step removed, measured: **18,066,916 dead tuples over 66 tables** on
17.11 and **17,617,051 over 65** on 12.2, the largest single statement being
`pt1` at 899,915 tuples in 0.41 s. The step takes **6.4 s** end to end on the 17
leg and **6.9 s** on the 12 leg.
The uniform 90 % drain no longer carries its own `VACUUM` and `ANALYZE`: those
were the maintenance, and the maintenance now happens here, where its timeouts,
its horizon and its output are recorded.

**Rule 3's census is now what the concept page says it should be**, a decision
about the tables no churn touched: 14 of 88 tables on 17.11 and 6 of 87 on 12.2,
down from 66 and 45 when the census was the only thing analyzing anything. Every
table it still analyzes is a table whose build-phase inserts were published to
the shared statistics entry *after* its build-phase `ANALYZE` had reset the
counter — including seven of the eight family-3 fixtures and control 108, whose
table is never analyzed by its recipe at all. That is the publication hazard the
concept page describes, and the census applying the engine's own test to it is
the behavior the rule asks for, not a defect in the fixtures.

### Proving the maintenance was not defeated

The concept page's
[no-defeat rule](../../common-concepts/mandatory-btree-bloat-tests.md#the-maintenance-must-not-be-defeated)
forbids five states from the first churn statement to the end of the census, and
asks a run to record four proofs per fixture. This is the first run of this page
against it. All four are recorded, and the run fails rather than publishes a
number if any of them comes out wrong:

| Proof | How it is taken | 17.11 | 12.2 |
|---|---|---|---|
| The statement completed, and no skip line names the table | every maintenance statement is timed with `clock_timestamp()` on both sides, and the server log is searched for `skipping vacuum of`, `skipping analyze of` and cancellations ([vacuum.c#skip-lock-not-available](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L828-L860)) | 66 of 66 completed, **0** skip or cancellation lines | 65 of 65, **0** |
| `VACUUM (VERBOSE)`'s `tuples: ... are dead but not yet removable` count | parsed out of the server's own message text per table ([vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L659-L663)) | **0 on all 66**, and `n_dead_tup` 0 on all 66 afterwards | **0 on all 65** |
| The horizon holders at that moment | `pg_stat_activity`'s `xact_start` and `backend_xmin`, `pg_replication_slots`' `xmin`/`catalog_xmin` and `pg_prepared_xacts`, read immediately before each statement and once after the census ([system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L877-L885), [system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017), [system_views.sql#pg_prepared_xacts](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L421-L427)) | **69 of 69 probes entirely clean**: 0 other backends with an xmin or an open transaction, 0 slots, 0 prepared transactions | **68 of 68** |
| The page classes the maintenance left | `pgstatindex` over every fixture index after the step ([pgstatindex.c#page-classes](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L295-L320)) | 29 of 126 indexes hold deleted pages, **10,340** deleted and 0 half-dead | 32 of 112, **11,868** and 0 |

The fifth forbidden state is a timeout short enough to fire inside the
maintenance statement. Every session that issues a `VACUUM` or an `ANALYZE` —
the churn file, the maintenance step and the census — now sets its timeouts to
zero, which is exactly what the autovacuum launcher and worker do to themselves
"to avoid letting these settings prevent regular maintenance from being
executed"
([autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470),
[autovacuum.c#launcher-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L518-L526)).
The settings in force are recorded per statement rather than assumed, and both
legs report exactly one distinct set: `statement_timeout=0 lock_timeout=0
transaction_timeout=0 idle_in_transaction_session_timeout=0` on 17.11, and the
same without `transaction_timeout` on 12.2, where that GUC does not exist
([guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653)).
All four are `PGC_USERSET`, so session scope, no reload and no restart.

Why each state would matter here, from the pinned tree: `VACUUM` takes its
removal horizon from `GetOldestNonRemovableTransactionId`
([vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122)),
which folds in every backend's `xmin` and every replication slot's
([procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815),
[procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902));
a prepared transaction keeps its xid running through a dummy `PGPROC`
([twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26));
and index vacuuming is entered only when dead TIDs were collected, so under a
pinned horizon `btbulkdelete` never runs at all
([vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052)).
For this heuristic that failure would be invisible in the worst way: the leaves
would stay as dense as the build left them, and `wasted_pct` would read near
zero on a file a rebuild empties.

Two limits of these proofs, stated rather than glossed. The horizon reading is a
pair of reads beside the statement, not an interlock around it — the concept page
files the same one-sidedness as its own open question — and `VERBOSE` output has
to be parsed out of message text, which is version-local: 17.11 prints `tuples: X
removed, Y remain, Z are dead but not yet removable` while 12.2 prints `Z dead
row versions cannot be removed yet`, so each leg script carries its own parse.
`client_min_messages = warning` does not hide either, because `INFO` is sent to
the client whatever that setting says
([elog.c#should_output_to_client](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L249-L264)).

`pg_stat_force_next_flush()` is still not called anywhere, unlike the original
recipes, because this heuristic reads `pg_class.reltuples` and never a cumulative
statistics view - and the same fixture text then runs on a 12 server, which has no
such function (measured, 0 `pg_proc` rows). The census reads
`n_mod_since_analyze` instead, one second after the churn sessions have exited,
which is what makes their pending statistics visible on both servers.

The oracle, the four verdict bands and the two mandatory scoring columns are the
shared ones, unchanged:
[The oracle and the verdict bands](../../common-concepts/mandatory-btree-bloat-tests.md#the-oracle-and-the-verdict-bands).
A measured `REINDEX INDEX` runs on every fixture after the heuristic has had its
turn, so `actual_pct` - the reclaim a rebuild of the churned file really gave
back - is the only oracle; `expected_stage` recomputes this heuristic's gate
arithmetic independently from the recorded baseline, and `want_stage` is the
per-fixture prediction filed before the first run and left untouched since. The
20 % gates and the 40 % rebuild threshold are the method under test, not part of
the suite.

### Results on 17.11

126 fixtures, 133 B-tree indexes swept (the seven extra are the harness's own
primary keys), `make check` 225 of 225 with `pgstattuple` 1, `pageinspect` 8 and
`amcheck` 3, and **0 unexpected server errors out of 4 logged**, all four
deliberate probes from `stage_facts`. **0 skip or cancellation lines** in the
log, which is proof 1 of the no-defeat rule.

| Group | Fixtures | Maintained | Rebuilt | Updated | Skipped | Refreshed | False negatives | Mean `wasted_pct` | Mean actual |
|---|---|---|---|---|---|---|---|---|---|
| `gate` (1-17) | 25 | 25 | 25 | 0 | 0 | 0 | 0 | 78.4 | 88.2 |
| `partial` (18-77) | 60 | 58 | 55 | 3 | 2 | 0 | 0 | 74.1 | 79.6 |
| `falsepos` (78-85) | 8 | 0 | 0 | 1 | 7 | 0 | 0 | 0.1 | 0.0 |
| `falseneg` (86-91) | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 73.5 | 73.0 |
| `control` (92-112) | 20 | 8 | 7 | 1 | 12 | 0 | 0 | 71.2 | 31.5 |
| `zero` (113-120) | 7 | 5 | 2 | 4 | 1 | 0 | 0 | 32.3 | 28.4 |

- All 25 surviving deduplication-gate shapes were measured and rebuilt after the
  90 % drain, and every one was right to rebuild: mean reclaim 88.2 %. The
  equal-image class of the key made no difference to the decision, which is the
  answer this group gives for a heuristic that reads physical density rather than
  modelling keys. The three `deduplicate_items = off` shapes that used to sit
  beside them are retired.
- **The six false-negative constructions are all caught.** The index-count gate
  opened every one, and all six were rebuilt at 40.5 % to 89.9 % measured reclaim.
- The eight false-positive constructions - predicate-conditioned width, NULL,
  `n_distinct` and MCV mismatches, a missing statistics row, a forged partial
  `reltuples`, stale table statistics - are **not rebuilt**, and a rebuild of each
  would have returned 0.0 %. **None of the eight is maintained**, because none
  has churn, so their statistics are the ones their recipes built. Seven are
  skipped outright. The eighth is fixture 84, whose forged index count of 5,000
  against a real 100,000 opens the gate: it is measured, reads 0.1 % wasted, and
  is left alone. One wasted `pgstatindex()` call is the whole price of a forged
  count.
- Accuracy of the decision input against the oracle, over the 103 scored
  measurements: mean error `+7.6` points (the reading under-estimates), min
  `-2.0`, max `+19.5`, 101 of 103 within 15 points, 7 over-estimates. The worst
  under-read is `p55` at fillfactor 70 (`+19.5`); `b93`/`b95`, which used to
  under-read by `+18.2`, now read `+9.4` because the maintenance step removes
  the dead entries their trailing `UPDATE` left behind.
- Which gate opened each measurement: size 8, table count 79, index count 103, and
  20 measured by the index count alone. One fixture, `p76`, is opened by the size
  test alone. No fixture is opened by the table count alone, and no measured
  fixture had no gate fire.
- Payload health after the run: 126 of 126 readable, 0 unparseable, 0 without a
  marker, and 126 of 126 stored index counts equal to the catalog's.
- `refresh` was taken 0 times, because the fixture that produced it is retired.

### Results on 12.2

112 fixtures (14 skipped for the missing features listed above: nine for B-tree
support function 4, five for ICU), 119 indexes swept, `make check` 192 of 192 with
`pgstattuple` 1, `pageinspect` 5 and `amcheck` 2, and **0 unexpected server errors
out of 8 logged**, the extra four being the feature refusals this server gives.
**0 skip or cancellation lines** here too.

| Group | Fixtures | Maintained | Rebuilt | Updated | Skipped | Refreshed | False negatives | Mean `wasted_pct` | Mean actual |
|---|---|---|---|---|---|---|---|---|---|
| `gate` | 13 | 13 | 13 | 0 | 0 | 0 | 0 | 80.1 | 89.9 |
| `partial` | 58 | 56 | 53 | 3 | 2 | 0 | 0 | 75.5 | 80.7 |
| `falsepos` | 8 | 0 | 0 | 1 | 7 | 0 | 0 | 0.1 | 0.0 |
| `falseneg` | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 72.1 | 72.5 |
| `control` | 20 | 8 | 7 | 1 | 12 | 0 | 0 | 71.2 | 31.5 |
| `zero` | 7 | 5 | 2 | 3 | 2 | 0 | 0 | 37.6 | 28.4 |

The two servers agree on every structural result: `PASS` on every scored fixture,
0 gate disagreements, 19 newly measured of which 15 bloated at a mean 86.3 %
reclaim, 112 of 112 stored index counts equal to the catalog's, and an accuracy
profile inside a point of the 17 leg's (89 measured, mean error `+7.4`, min
`-0.3`, max `+19.5`, 87 of 89 within 15, 5 over-estimates). The gate attribution
has the same shape: size 8, table count 65, index count 88, 19 by the index count
alone, and `p76` the only fixture opened by the size test alone. The one place
the legs differ is fixture 120, whose precondition held here and not on 17.11;
see [Fixture 120's precondition, now asserted](#fixture-120s-precondition-now-asserted).

`p118` is no longer opened by the size test alone on this leg, which is a
maintenance-step consequence worth naming: its 50,000 inserts are churn, so the
step analyzes `q118`, and the partial index's estimated entry count moves from 0
to 50,000 - an increase from zero, which the filed text treats as a fire. Before
the maintenance step this leg left that count at 0 and only the 139-fold size
change opened the measurement.

### Fixture 120's precondition, now asserted

The concept page makes test 120 the suite's one probabilistic fixture and puts a
precondition on it: after the census the partial index's own `reltuples` must read
0, and "a run that finds a non-zero estimate records an unmet fixture precondition
for 120 and scores nothing from it"
([Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md#family-6-the-drained-queue-and-zero-row-counts)).
**The 2026-09-14 run never checked it and counted a `PASS` on both legs.** That
is fixed: the run now reads the estimate after the census, records it, and the
verdict view reports `UNMET PRECONDITION` for a fixture whose state did not
arrive, which every scored count then excludes.

| Leg, this run | Estimate after the census | Verdict | What the method did |
|---|---|---|---|
| 17.11 | **1,600** | **UNMET PRECONDITION**, scores nothing | the low-target sample caught subset rows, so the state never arrived; the heuristic measured the index, read 5.9 % wasted and left it alone |
| 12.2 | **0** | scored | the 300-row sample missed the subset, the fixture reached its state, and the heuristic correctly **skipped** the index - the prediction filed for it |

The fixture is genuinely probabilistic, and this review watched it move: over the
five complete passes it took, the post-census estimate read **2,034, 1,667, 0,
1,800 and 1,600** on 17.11 and **0, 13,335, 3,334, 0 and 0** on 12.2, from
identical fixture text on the same pins, so the state arrived on **4 of 10
fixture builds**. **That is the argument for asserting the precondition rather
than scoring the fixture**:
with the check in place a run either measures the state the concept page defines
or says it did not have it, and the previous run's `PASS` was neither. The scored
totals on the published pass are therefore 125 of 126 on 17.11 and 112 of 112 on
12.2.

### Filed predictions against measured verdicts

A `want_stage` was filed for every fixture before the first run and has never been
rewritten, because a prediction rewritten after the fact proves nothing. On 17.11
it is right for **119 of 126** and on 12.2 for **106 of 112**. Every miss on both
legs runs the same way — predicted `skip`, measured `measure` — which is the third
gate doing its job on fixtures whose predictions were written when only two gates
existed. Nothing predicted `measure` was skipped.

| Prediction | Fixtures on 17.11 | What the measurement then decided |
|---|---|---|
| `skip`, measured `reindex` | `p29`, `p113b`, `p114` | 77.6 % to 99.9 % wasted, 87.4 % to 100.0 % actually reclaimed - correct rebuilds |
| `skip`, measured `update` | `f84`, `p118`, `p119`, `p120` | 0.1 % to 5.9 % wasted against a 0.0 % oracle - healthy indexes correctly left alone, at one `pgstatindex()` call each |

The 12.2 leg is the same list without `p120`, which that leg skipped because its
subset estimate really was 0, and `p29` reads 79.2 % wasted against 89.6 %
reclaimed there rather than 77.6 % against 87.4 %. Four of the seven misses on
17.11 are the price of the third gate: a forged count, two empty-subset indexes
that filled up and one resampled estimate, each costing a single measurement and
no rebuild. `p120`'s miss is also the one that scores nothing, because its
precondition failed on that leg.

### Mandatory test review

One row per family of
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md),
with what each family did against this heuristic on each server. The `Fixtures
and oracle` column states what this run built; the family's purpose and the
engine behavior it targets are on the concept page.

| Group | Tests | Fixtures and oracle | 17.11 | 12.2 |
|---|---|---|---|---|
| Deduplication gate | 1-17, less 11 | 25 indexes on two 500,000-row tables, drained 90 %; measured `REINDEX INDEX` | run, 25 of 25 `PASS` | run, 13 of 13 `PASS`, 12 skipped for missing features |
| Partial indexes | 18-77, less 38, 65, 67, 69 | 60 indexes, each with its own churn or the uniform drain | run, 60 of 60 `PASS` | run, 58 of 58 `PASS`, 2 skipped for ICU |
| False-positive constructions | 78-85 | 8 freshly built indexes that must not be touched | run, 8 of 8 left un-rebuilt (7 skipped, 1 measured and updated) | the same |
| False-negative constructions | 86-91 | 6 genuinely bloated, vacuumed and analysed | run, 6 of 6 `PASS`, all rebuilt | the same |
| Change A-D controls | 92-112, less 106 | threshold calibration 92-95, non-partial 96-99, `INCLUDE` 100-105, expression statistics 107-112 | run, 20 of 20 `PASS` | the same |
| Drained queue and change E | 113b, 114-120 | one 1,000,000-row table per state, `reltuples = 0` shapes | run, 6 of 6 `PASS`, 120 an unmet precondition scoring nothing | run, 7 of 7 `PASS` with 120's precondition met |
| Simulated auto-analyze | rule 3 | every fixture table, gated on the engine's own threshold | run, 12 of 88 analyzed, all of them tables no churn touched, 12 of 12 counters reset | run, 4 of 87 analyzed, same reason, 4 of 4 reset |
| The maintenance assumption | the concept page's own | **applied**: 66 tables vacuumed and analyzed after their churn, 18,066,916 dead tuples removed | **applied**: 65 tables, 17,617,051 removed |
| The maintenance must not be defeated | the concept page's own | **proved**, four proofs per table: 66 of 66 completed, all at `dead but not yet removable` 0, 69 of 69 horizon probes clean, 0 skip lines, one timeout set of four zeros | **proved**: 65 of 65, 68 of 68 probes, 0 skip lines, three zeros |
| Engine regression | `make check` plus `pgstattuple`, `pageinspect`, `amcheck` | temporary installation in the build tree | 225, 1, 8, 3 - all passed | 192, 1, 5, 2 - all passed |
| Repository checks | `scripts/wiki_lint`, block hashes, pipeline identity, Contents anchors | this repository | pass | pass |

The contract the suite sets is that a statement failing a mandatory test is
corrected, not merely reported. Two defects were found and corrected in the filed
texts of the first revision; see
[Two defects the first revision's suite found](#two-defects-the-first-revisions-suite-found).
**This pass corrects nothing in either text either, because nothing in the
surviving suite failed — including under the maintenance the previous pass had
withheld.** That is a stronger statement than the 2026-09-14 one and still not a
clean bill of health: the fixtures this method fails were retired rather than
fixed, and this page says so in
[The blind spot that left with its fixtures](#the-blind-spot-that-left-with-its-fixtures)
instead of claiming credit for them. The three defects this pass fixed are all in
the harness: the missing fixture-120 precondition check, a publication invariant
that mistook a recipe's own `ANALYZE` for an unpublished counter, and a `check`
stage that wrote its results into a directory that did not exist yet; see
[What the 2026-09-16 review changed, and why](#what-the-2026-09-16-review-changed-and-why).

### What still needs to be tested

1. **A fourth input for the unvacuumed case.** A file full of dead index entries
   reads dense to `pgstatindex`. Neither a stored entry count against leaf-page
   capacity nor `pg_stat_all_tables.n_dead_tup` has been tried as a further gate
   or as a correction to `wasted_pct`, and the suite no longer builds a fixture
   that would catch the gap.
2. **Concurrent rebuilds end to end.** A run where step 1 emits the concurrent
   command, an operator executes it at the top level, and the next run stores the
   baseline through rule 3, has not been scored as a loop.
3. **A second block size.** Every geometry constant is derived from
   `block_size`, and both legs ran at 8192 with `max_data_alignment` 8. A
   `--with-blocksize=16` build has not been tried.
4. **13, 14, 15 and 16.** The claim is "12 through 17" and the measured legs are
   12.2 and 17.11. The intermediate majors are covered only by the feature facts
   the two legs discovered, not by a run.
5. **A non-C locale and a non-UTF8 encoding**, and an ICU-enabled 12 build, which
   would let the five ICU fixtures run on both legs instead of one.
6. **Two sessions racing on one index.** The lock modes are read from source; the
   behaviour of two overlapping step-2 runs, and of a step-2 run against a
   concurrent `DROP INDEX`, is not measured.
7. **A partitioned table end to end.** No fixture drains a partition and watches
   the parent, and since 2026-09-14 no fixture even checks that a partitioned
   index is excluded while its leaf is not.
8. **Standby behaviour.** The `relpersistence <> 'u' OR NOT pg_is_in_recovery()`
   filter has never been exercised on a real standby, and no part of the heuristic
   can write a comment there.
9. **How often sampling noise opens the third gate.** Fixture 120 is the only
   fixture that touches it, and its state arrived on three of the eight
   fixture builds this review watched. No fixture family sweeps subset
   selectivity against `default_statistics_target`, which is what would turn
   that coin-flip into a curve.
10. **A run with autovacuum actually on.** The tests now run the maintenance the
    launcher would have run, and they still do not let the launcher run it: the
    `VACUUM ANALYZE` is issued at a fixed point rather than when the launcher's
    thresholds would have fired, and the vacuum verdict is not simulated at all.
    The concept page says a run may not claim otherwise.
11. **A fixture whose point is a defeated maintenance.** The no-defeat rule is
    proved negatively here - nothing pinned the horizon, so nothing was
    defeated. Whether this heuristic reads a genuinely pinned-horizon database
    as clean is exactly the blind spot under item 1, and no numbered fixture
    builds that state today.
12. **Everything the removed acceptance fixtures used to cover**, listed in
    [Open Questions](#open-questions): comment parsing and preservation, the
    candidate filters, the gate boundaries, the unknown-count states, the
    threshold curve, comment survival across both `REINDEX` forms, privileges,
    the `COMMENT` lock, dry runs, idempotence and `pg_dump`.

## Measurement Script

Every number on this page comes from the two scripts below: one per version leg,
Bash and SQL only, each self-contained apart from the two texts it takes out of
this page.

| Item | This suite |
|---|---|
| Purpose | Build the pinned checkout, run the engine regression suites, start an isolated cluster, take this page's two texts out of this page, port every numbered fixture the mandatory suite still defines, store an as-built baseline in every index comment, churn each fixture, **maintain every table the churn touched and prove the maintenance was not defeated**, simulate the auto-analyze the churn would have triggered, **assert the preconditions the shared definition puts on a fixture**, apply the catalog forgery an `ANALYZE` would have repaired, record the page classes the maintenance left, run the heuristic, score every decision against a measured `REINDEX INDEX`, and time the statement in a settled and in a fully gated database. Every figure in [Verdict](#verdict) through [What still needs to be tested](#what-still-needs-to-be-tested) is one of its outputs, except where the text says a measurement was removed with the page-local fixtures on 2026-09-14. |
| Invocation | From the repository root: `bash btmaint_suite_v17.sh` and `bash btmaint_suite_v12.sh`. Selected stages: `bash btmaint_suite_v17.sh suite score`. |
| Stages | 17 leg: `build check cluster sql texts facts suite cost score criteria report`, in that default order, plus `stop` and `clean`. The 12 leg inserts `exact` between `texts` and `facts`. The churn census, the maintenance step, the simulated auto-analyze, the precondition check, the forgery and the page-class read are steps inside `suite`, not stages of their own, because a decision taken without any of them would be a decision on a state no production server would have had. |
| Environment | `WIKI_ROOT` (default `$PWD`), `PAGE` (default this page), `SRC` (default `raw/postgres-17` or `raw/postgres-12`), `SANDBOX` (default `.wiki-runtime/tmp/btmaint`), `PORT` (55417 / 55412), `JOBS` (8). |
| Prerequisites | A C toolchain, `make`, and the two pinned checkouts. The 17 leg configures `--with-icu`, the 12 leg `--without-icu`. `pgstattuple` is installed from the same build. No installed PostgreSQL is used. |
| Output | Everything under `$SANDBOX/out` (17) and `$SANDBOX/out12` (12). Read `criteria.txt` first; then `counters.txt`, `verdicts.txt`, `maintenance.txt`, `maint_proofs.txt`, `precond.txt`, `pageclass.txt`, `want_miss.txt`, `newly_measured.txt`, `lost.txt`, `disagree.txt`, `autoanalyze.txt`, `cost.txt`, `facts.txt`, `maint_skips.txt` and `server_errors_all.txt`. |
| Runtime | Both legs were run concurrently on 22 cores at `JOBS=10` each, with `fsync = off` in the sandbox cluster: the published pass ran from 14:21:32Z to 14:25:43Z on the 17 leg and from 20 s later to 14:25:55Z on the 12 leg, **4 min 11 s and 4 min 03 s** from an empty sandbox, `configure`, `make`, `make check` and the three contrib suites included. From a built tree a leg is about 2 min 15 s. The maintenance step itself is 6.4 s and 6.9 s. The shared sandbox holds about 9 GB, most of it the two data directories. |
| Cleanup | **Stop both legs first, then clean once**: `bash btmaint_suite_v17.sh stop`, `bash btmaint_suite_v12.sh stop`, then `bash btmaint_suite_v17.sh clean`. Each `stop` uses `pg_ctl -m fast -w stop` and confirms no `postmaster.pid`, no matching process and an empty socket directory; `clean` refuses to delete anything outside `.wiki-runtime/tmp/` and then removes the sandbox. The order matters because **the two legs share `$SANDBOX`**: `clean` on either leg deletes the other leg's data directory and binaries as well, so running it while the other server is up pulls the rug out from under a live postmaster. An earlier teardown in this review learned that; see [Open Questions](#open-questions). |

### How to use the two leg scripts

Save each block to a file of the name in its first comment line, in the
repository root, and run it from there. Nothing outside `$SANDBOX` is written, and
the pinned checkouts are read only: both builds are VPATH builds in directories
under `.wiki-runtime/tmp/`.

The scripts take the two texts under test out of this page, by fence order:
block 1 is [Step 1: the plan](#step-1-the-plan) and block 2 is
[Step 2: carrying it out](#step-2-carrying-it-out). Each is hashed against a
baseline recorded in the script, so editing this page's SQL without re-measuring
is visible in the output:

```text
report 93b64e2dd33d411951ceffd9d665a3e3e8ce3a71fde60bbca9e61c219febd0e9 match
apply  7427d62d2ca3bb43dd2f7c5a8aa97c27fc8111d65d3066594660c2808d47992d match
report lines=243 bytes=13167
apply  lines=267 bytes=13028
pipeline report 39a2e57379dde00ba6eb64edb38b1d81d68f594aa349e2bc3cdb0aafbdc4ef02
pipeline apply  39a2e57379dde00ba6eb64edb38b1d81d68f594aa349e2bc3cdb0aafbdc4ef02
pipeline lines  118
pipeline identical yes
```

Both legs printed those eight lines on the 2026-09-16 run, unchanged from
2026-09-14 and from 2026-09-11: neither text was edited, and the shared pipeline
is byte-identical in the two of them.

`stage_texts` also builds the one harness object the suite needs from step 1: a
view over the filed statement, with exactly one documented edit - the two `SET`
lines dropped, because a view cannot carry them. Nothing else is touched, so the
view decides exactly what the filed statement decides, and the scorer reads
decisions without re-typing them.

### The stages, both legs

| Stage | What it does |
|---|---|
| `build` | Configures and builds the pinned checkout out of tree, installs it plus `pgstattuple`, `pageinspect` and `amcheck` under `$SANDBOX/inst/NN`. Skipped if the binary is already there. |
| `check` | `make check` and the three contrib suites, with the pass counts and any `regression.diffs` copied where `clean` will not delete them. |
| `cluster` | `initdb --locale=C --encoding=UTF8`, writes the cluster settings, starts the server, records `version()` and `pg_control_init()`, creates the `suite` database with `pgstattuple`. Idempotent. |
| `sql` | Writes every SQL file the suite uses: the harness, the fixture build and churn files, the PostgreSQL 13 and ICU fixture files, the two-phase churn census, the maintenance step and its post-read, the simulated auto-analyze and its recheck, the precondition check, the page-class read, and the forgery file. |
| `texts` | Extracts, hashes and line-counts the two texts, checks that their shared pipeline region is byte-identical, and builds the one-edit view. |
| `exact` (12 leg) | Executes both filed texts verbatim on this server before any fixture exists, and records the outcome, the comment written, and what a second run does. |
| `facts` | Discovers every version-local fact the texts depend on, on the running server, including who writes an index's `reltuples` and the two auto-analyze defaults. |
| `suite` | Builds the numbered fixtures, runs the filed apply block to store as-built baselines, records the write counters, churns, **maintains every table the churn touched and checks the four no-defeat proofs**, runs the simulated auto-analyze and its recheck, **asserts fixture 120's precondition**, applies fixture 84's catalog forgery, records the page classes, records the filed report's decisions, runs the filed apply block again to act, then rebuilds every fixture as the oracle. It dies rather than score if a maintenance statement did not complete, kept dead tuples the horizon still covered, has no `VERBOSE` count, or ran while any probe found an xmin holder, a slot or a prepared transaction. |
| `cost` | Settles the database with one apply run, times the filed report six times and reads its buffer counts, then halves every stored `sz`, leaving both counts current, so the size gate alone fires everywhere, and repeats. |
| `score` | Writes the verdict rows, the verdict and action counts, the per-group table, the accuracy row, the gate-agreement row, the per-gate attribution, the two-gate counterfactual, the newly-measured detail, the stored-index-count check, the lost-fixture detail, the payload-health row, the per-fixture and per-table maintenance detail with its page classes, the horizon readings, and the precondition rows. |
| `criteria` | Collects the pass criteria into one file, audits the server log for any error the suite did not deliberately provoke, reporting the matched, deliberate and unexpected counts separately, and counts the log's maintenance skip and cancellation lines. |
| `report` | Lists the output directory. |
| `stop` | `pg_ctl -m fast -w stop`, then confirms the teardown and dies rather than report a stop that did not happen. |
| `clean` | `stop`, then refuses to delete anything outside `.wiki-runtime/tmp/` before removing the sandbox. |

### What the scripts read from the environment

| Variable | Default | Effect |
|---|---|---|
| `WIKI_ROOT` | `$PWD` | Repository root; also the containment boundary `clean` checks. |
| `PAGE` | `wiki/v17/questions/indexing/btree-comment-baseline-maintenance-heuristic.md` | Where the two texts come from. |
| `SRC` | `$WIKI_ROOT/raw/postgres-17` or `raw/postgres-12` | The pinned checkout to build. |
| `SANDBOX` | `$WIKI_ROOT/.wiki-runtime/tmp/btmaint` | Everything written lives here. |
| `PORT` | 55417 (17), 55412 (12) | Non-default port; the socket directory is inside the sandbox. |
| `JOBS` | 8 | `make -j`. |

Cluster settings and their apply scope, all written before the first start:
`listen_addresses`, `port`, `unix_socket_directories`, `shared_buffers` and
`logging_collector` are `PGC_POSTMASTER`, so they need a restart and are set
before one; `fsync` and `autovacuum` are `PGC_SIGHUP`, so a reload;
`maintenance_work_mem` and `max_parallel_maintenance_workers` are `PGC_USERSET`,
session scope. `autovacuum` is off so that no background vacuum moves a fixture
between the baseline, the churn, the decision and the oracle.

Both scripts mark their fixture statements as disposable. They create, forge and
drop tables, indexes, operator classes, collations and one `pg_class` row in the
sandbox cluster's `suite` database, and are not meant for a database anyone cares
about. The one surviving forgery, fixture 84's index `reltuples`, is applied
*after* the simulated auto-analyze, in `forge.sql`, because an `ANALYZE` of the
table rewrites `reltuples` for the table and for every index on it, which would
repair exactly the state that fixture exists to create.

### Prerequisites

- A C toolchain and `make`. Both legs build their own server.
- Development headers for ICU for the 17 leg; the 12 leg is configured
  `--without-icu` and records its five ICU fixtures as skipped.
- The two pinned checkouts at `raw/postgres-17` and `raw/postgres-12`.
- `sha256sum`, `cmp`, `diff`, `grep`, `sed`, `cut`, `tr`, `wc` and `pgrep`.

### Last run

| Item | 17 leg | 12 leg |
|---|---|---|
| Date | 2026-09-16 | 2026-09-16 |
| Wall clock | 14:21:32Z to 14:25:43Z, cluster up at 14:23:50Z | started 20 s later, cluster up at 14:24:05Z, finished 14:25:55Z |
| Server version | 17.11 | 12.2 |
| Pin | `786db8dcf168bd9df8f55047337525ac19118b1c` | `45b88269a353ad93744772791feb6d01bc7e1e42` |
| `database_block_size` | 8192 | 8192 |
| `max_data_alignment` | 8 | 8 |
| Platform | Linux x86_64, Ubuntu 24.04 on a WSL2 kernel, gcc 13.3.0, ICU 74.2, 22 cores, `JOBS=10` | Linux x86_64, Ubuntu 24.04 on a WSL2 kernel, gcc 13.3.0, 22 cores, `JOBS=10` |
| Locale, encoding | C, UTF8 | C, UTF8 |
| `autovacuum_analyze_threshold`, `autovacuum_analyze_scale_factor` | 50, 0.1 | 50, 0.1 |
| Engine tests | 225 core, `pgstattuple` 1, `pageinspect` 8, `amcheck` 3 | 192 core, `pgstattuple` 1, `pageinspect` 5, `amcheck` 2 |
| Logged server errors, deliberate, unexpected | 4, 4, **0** | 8, 8, **0** |
| Maintenance skip or cancellation lines | **0** | **0** |
| Text hashes | `93b64e2d…` report, `7427d62d…` apply | the same two |
| Script SHA-256 | `311d9f25a3fa76b6a88c5be3e27d5ba5ccdd6adda4a67454b231af4f82010c3f` | `d942054276d8131b6736ad02cfb3b5a2c1dc7e54c2dacf02cff25e40249d7230` |

Every figure on this page comes from that pair of runs, both taken in one pass
from `build` to `report` with the script text published below, extracted from this
page by fence order and diffed byte for byte against what was run. Both servers
were then stopped by the scripts' own `stop` stage and the 9 GB sandbox deleted by
`clean`, with no `postmaster.pid`, no matching process and an empty socket
directory confirmed for each.

**Run-to-run stability, on two clusters built from the same pins.** This review
took five complete passes, and the published one agrees almost exactly with an
earlier pass run on a separate cluster: of the per-fixture
`(number, index, action, wasted_pct, actual_pct)` tuples, **125 of 126 are
identical on 17.11 and 112 of 112 on 12.2**. The single exception is `p120`,
whose subset estimate is a sampling outcome rather than a fixture constant; see
[Fixture 120's precondition, now asserted](#fixture-120s-precondition-now-asserted).
The earlier passes contribute no published number: the first stopped in the
maintenance step when the publication invariant fired on nine recipe-analyzed
tables, two more were superseded by the `check`-stage and census-recheck
repairs, and the fourth was superseded when a stale comment in the fixture
build file - still claiming the maintenance assumption was not applied - was
corrected, which is why the script published below is the one that produced
these numbers rather than a later edit of it.

### The PostgreSQL 17 leg script

```bash
#!/usr/bin/env bash
#
# btmaint_suite_v17.sh - the whole test suite of the PostgreSQL 17 wiki page
# "A COMMENT-Stored Baseline B-Tree Index-Maintenance Heuristic for PostgreSQL
# 12 Through 17", in bash and SQL only.
#
# It builds 17.11 out of tree from the pinned checkout, runs the engine
# regression suites, starts an isolated cluster, takes the page's two texts out
# of the page itself, ports every numbered fixture the wiki's shared definition
# "Mandatory B-Tree Bloat Tests" still defines (tests 1-17, 18-91 and controls
# 92-120, less the retired 11, 38, 65, 67, 69, 106, 117, 121 and legs 113a and
# 113c), stores an as-built baseline in each index comment, churns each
# fixture, maintains every table the churn touched, simulates the auto-analyze
# that churn would have triggered on a server with autovacuum on, runs the
# heuristic, and scores every decision against a measured REINDEX INDEX.
#
# The shared definition's maintenance assumption is applied in full as of the
# 2026-09-16 revision: the maintenance step inside stage_suite runs
# VACUUM (VERBOSE, ANALYZE) on every table the churn inserted, updated or
# deleted a row in - the set comes from
# the engine's own pg_stat_all_tables counters across the churn phase, not
# from a hand-written list - and it runs before the rule 3 census and the
# decide phase.  A table no churn touched is not maintained, because draining or
# re-analyzing a deliberately fresh or deliberately stale fixture would destroy
# the shape it exists to build.
#
# The same revision carries out the shared definition's newer rule, "the
# maintenance must not be defeated".  Four proofs are recorded per maintained
# table: that the statement ran to completion with no skip line naming the
# table, its VERBOSE "dead but not yet removable" count, the horizon holders
# read from pg_stat_activity, pg_replication_slots and pg_prepared_xacts
# immediately before it, and the index page classes after it.  Every session
# that issues a VACUUM or an ANALYZE forces statement_timeout, lock_timeout,
# transaction_timeout and idle_in_transaction_session_timeout to 0, which is
# what the autovacuum launcher and worker do to themselves for this exact
# reason, and the timeouts in force are recorded rather than assumed.
#
# Fixture 120's precondition is asserted rather than assumed: the shared
# definition says a run that finds a non-zero post-census estimate for its
# partial index scores nothing from the fixture, so the precondition step
# records the observed estimate and the scorer reports that fixture as UNMET
# PRECONDITION and excludes it from every scored count.
#
# The simulated auto-analyze is the mandatory-test rule that any fixture moving
# more than 10 % of a table's heap tuples must ANALYZE it.  It is not
# hand-annotated per fixture: the census reads the engine's own
# n_mod_since_analyze counter and applies the engine's own threshold,
# autovacuum_analyze_threshold + autovacuum_analyze_scale_factor * reltuples
# (50 + 0.1 * reltuples at the defaults), so the tables it analyzes are exactly
# the tables an autovacuum launcher would have analyzed.  Every table it
# considered, with its counter, its threshold and the verdict, is recorded.
# With the maintenance step in front of it the census now finds every churned
# table freshly analyzed, so what it decides is the tables no churn touched -
# which is what the shared definition says it should decide.
#
# The pinned checkout is read only: everything this script writes lives under
# $SANDBOX (default .wiki-runtime/tmp/btmaint).
#
# Usage, from the repository root:
#   bash btmaint_suite_v17.sh                  # every stage, in order
#   bash btmaint_suite_v17.sh suite score      # selected stages
#   bash btmaint_suite_v17.sh clean            # stop and delete the sandbox
#
# Stages: build check cluster sql texts facts suite cost score criteria
#         report stop clean
#
# Environment: WIKI_ROOT PAGE SRC SANDBOX PORT JOBS
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v17/questions/indexing/btree-comment-baseline-maintenance-heuristic.md}"
SRC="${SRC:-$WIKI_ROOT/raw/postgres-17}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/btmaint}"
PORT="${PORT:-55417}"
JOBS="${JOBS:-8}"

BUILD="$SANDBOX/build/17"; INST="$SANDBOX/inst/17"; DATA="$SANDBOX/data17"
OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql"; SOCK="$SANDBOX/sock"; BIN="$INST/bin"
export PGPORT="$PORT" PGHOST="$SOCK" PGDATABASE=postgres

# SHA-256 baselines of the two fenced SQL blocks of the page, in page order:
# the report statement and the apply block.  A changed text must be re-measured
# and the hash refiled; that is the point of recording them here.
BASE_REPORT=93b64e2dd33d411951ceffd9d665a3e3e8ce3a71fde60bbca9e61c219febd0e9
BASE_APPLY=7427d62d2ca3bb43dd2f7c5a8aa97c27fc8111d65d3066594660c2808d47992d

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# psql helpers.  -X ignores ~/.psqlrc; ON_ERROR_STOP is on every helper, because
# without it a failed statement inside a -f script leaves the exit status 0.
q()  { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$1" -c "$2"; }        # command
f()  { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$1" -f "$2"; }        # file
# fv() is f() with one psql variable, for the two-phase churn census.
fv() { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -v "$2" -d "$1" -f "$3"; }
s()  { "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d "$1" -c "$2"; }    # scalar
t()  { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off \
                   -d "$1" -c "$2"; }                                 # table
# err() runs a statement that is expected to fail and prints the message only.
err() { "$BIN/psql" -X -q -v ON_ERROR_STOP=0 -d "$1" -c "$2" 2>&1 \
        | grep -E '^(ERROR|psql:.*ERROR)' | head -1; }
# errf() sends a statement through a file, so that a body full of quotes and
# dollar signs reaches the server exactly as written, and reports the first
# error line or "accepted".
errf() {
  local db=$1 out
  out=$(printf '%s\n' "$2" | "$BIN/psql" -X -q -v ON_ERROR_STOP=0 -d "$db" -f - 2>&1 \
        | grep -E 'ERROR' | head -1)
  printf '%s' "${out:-accepted}"
}

# md_block <fence-language> <n> <file>: print the nth fenced block, bash only.
# The fence is assembled from printf '\140' so that this script contains no
# literal Markdown fence and can therefore live inside one.
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

# parse_verbose <log> : turn the maintenance step's VACUUM (VERBOSE) output
# into one UPDATE per maintained table, so that each statement's own "dead but
# not yet removable" count is a recorded number rather than a line in a log.
# A 17 server prints
#   INFO:  finished vacuuming "db.schema.tbl": index scans: N
#   tuples: X removed, Y remain, Z are dead but not yet removable
# as one message, so the table name is carried from the header line to the
# tuples line.  Bash case patterns and parameter expansion only: no awk, no
# perl.
parse_verbose() {
  local log=$1 line cur="" rest removed remain dead
  while IFS= read -r line; do
    case $line in
      *'finished vacuuming "'*)
        rest=${line#*finished vacuuming \"}; rest=${rest%%\"*}; cur=${rest##*.} ;;
      'tuples: '*' are dead but not yet removable'*)
        [ -n "$cur" ] || continue
        rest=${line#tuples: };    removed=${rest%% removed,*}
        rest=${rest#* removed, }; remain=${rest%% remain,*}
        rest=${rest#* remain, };  dead=${rest%% are dead*}
        printf "UPDATE /* wiki_btmaint_maint_verbose */ maint SET removed = %s, remain = %s, dead_not_removable = %s WHERE tbl = '%s';\n" \
               "$removed" "$remain" "$dead" "$cur"
        cur="" ;;
    esac
  done < "$log"
}

# plan_view <report-text> : the one documented edit.  Drop the two SET lines,
# which a view cannot carry, and wrap the rest in CREATE VIEW plan_v.  Nothing
# else is touched, so the view computes exactly what the filed statement does.
plan_view() {
  local file=$1 line
  printf 'DROP VIEW IF EXISTS plan_v;\nCREATE VIEW plan_v AS\n'
  while IFS= read -r line; do
    case $line in
      "SET /* wiki_btmaint_statement_timeout"*) continue ;;
      "SET /* wiki_btmaint_lock_timeout"*)      continue ;;
    esac
    printf '%s\n' "$line"
  done < "$file"
}

# ---------------------------------------------------------------- build ------
stage_build() {
  say "build 17.11 out of tree from $SRC"
  if [ -x "$BIN/postgres" ]; then
    note "already built: $("$BIN/postgres" --version)"; return 0
  fi
  [ -x "$SRC/configure" ] || die "no pinned checkout at $SRC"
  mkdir -p "$BUILD" "$OUT" "$SQLD"
  ( cd "$BUILD" && "$SRC/configure" --prefix="$INST" --with-icu \
      > configure.log 2>&1 ) || { cp "$BUILD/configure.log" "$OUT/" 2>/dev/null
                                  die "configure failed, see $OUT/configure.log"; }
  ( cd "$BUILD" && make -j"$JOBS" -s > make.log 2>&1 \
      && make -s install > install.log 2>&1 ) \
    || { cp "$BUILD"/*.log "$OUT/" 2>/dev/null; die "make failed"; }
  local m
  for m in pgstattuple pageinspect amcheck; do
    ( cd "$BUILD" && make -C "contrib/$m" -s install >> install.log 2>&1 ) \
      || die "contrib/$m install failed"
  done
  cp "$BUILD"/configure.log "$BUILD"/make.log "$BUILD"/install.log "$OUT/" 2>/dev/null
  note "$("$BIN/postgres" --version)"
}

# ---------------------------------------------------------------- check ------
stage_check() {
  say "engine regression suites"
  # $OUT is created here rather than assumed: stage_build returns early when
  # the binary is already there, so a run that starts from a built tree would
  # otherwise write every check result into a directory that does not exist and
  # report an empty check section.
  mkdir -p "$OUT"
  : > "$OUT/checks.txt"
  ( cd "$BUILD" && make -s check > check_core.log 2>&1 )
  printf 'core=%s %s\n' "$?" \
    "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' \
        "$BUILD/check_core.log" | tail -1)" >> "$OUT/checks.txt"
  local m
  for m in pgstattuple pageinspect amcheck; do
    ( cd "$BUILD" && make -s -C "contrib/$m" check > "check_$m.log" 2>&1 )
    printf '%s=%s %s\n' "$m" "$?" \
      "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' \
          "$BUILD/check_$m.log" | tail -1)" >> "$OUT/checks.txt"
  done
  cp "$BUILD"/check_*.log "$OUT/" 2>/dev/null
  local d
  for d in "$BUILD/src/test/regress" "$BUILD"/contrib/*; do
    [ -f "$d/regression.diffs" ] \
      && cp "$d/regression.diffs" "$OUT/diffs_$(basename "$d").txt"
  done
  cat "$OUT/checks.txt" >&2
}

# ---------------------------------------------------------------- cluster ----
# Cluster settings and their apply scope, all written before the first start:
#   listen_addresses, port, unix_socket_directories, shared_buffers,
#   logging_collector                                  -> PGC_POSTMASTER, restart
#   fsync, autovacuum                                  -> PGC_SIGHUP, reload
#   maintenance_work_mem, max_parallel_maintenance_workers
#                                                      -> PGC_USERSET, session
# autovacuum is off so that no background vacuum moves a fixture between the
# baseline, the churn, the decision and the rebuild oracle.
stage_cluster() {
  say "isolated cluster on port $PORT"
  mkdir -p "$OUT" "$SQLD" "$SOCK"
  if [ -s "$DATA/postmaster.pid" ] && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    note "already running"
  else
    if [ ! -d "$DATA" ]; then
      "$BIN/initdb" -D "$DATA" --locale=C --encoding=UTF8 > "$OUT/initdb.log" 2>&1 \
        || die "initdb failed"
      cat >> "$DATA/postgresql.conf" <<CONF
listen_addresses = ''
unix_socket_directories = '$SOCK'
port = $PORT
autovacuum = off
fsync = off
shared_buffers = '512MB'
maintenance_work_mem = '256MB'
max_parallel_maintenance_workers = 0
logging_collector = off
CONF
    fi
    "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w start > /dev/null \
      || die "server start failed"
  fi
  note "$(s postgres 'SELECT /* wiki_btmaint_version */ version()')"
  s postgres "SELECT /* wiki_btmaint_platform */
                     'max_data_alignment=' || max_data_alignment ||
              ' database_block_size=' || database_block_size FROM pg_control_init()" \
    | tee "$OUT/platform.txt" >&2
  printf 'uname: %s\n' "$(uname -sm)" >> "$OUT/platform.txt"
  # One database, the suite's.  The page-local acceptance database this stage
  # used to create beside it is gone with the fixtures that lived in it.
  local db
  for db in suite; do
    s postgres "SELECT /* wiki_btmaint_database_exists */ 1
                  FROM pg_database WHERE datname = '$db'" | grep -q 1 \
      || "$BIN/createdb" -T template0 -E UTF8 --locale=C "$db"
    q "$db" 'CREATE EXTENSION IF NOT EXISTS pgstattuple' || die "pgstattuple failed"
  done
}

# ------------------------------------------------------------------ sql ------
# Every SQL file this suite uses, written out from here so that the script is
# self-contained.  The two texts under test are NOT here: they come out of the
# page itself, in stage_texts.
stage_sql() {
  say "write the suite's SQL files to $SQLD"
  mkdir -p "$SQLD"
  cat > "$SQLD/harness.sql" <<'HARNESS'
-- Harness for the ported numbered suite.  Disposable: every object below is
-- created in the sandbox cluster's suite database and is not meant for a
-- database anyone cares about.  The harness never touches the heuristic's own
-- two texts; it only records, snapshots and scores.
SET /* wiki_btmaint_harness_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_harness_statement_timeout */ statement_timeout = '900s';
SET /* wiki_btmaint_harness_lock_timeout */ lock_timeout = '5s';

DROP TABLE IF EXISTS plan CASCADE;
DROP TABLE IF EXISTS snap CASCADE;
DROP TABLE IF EXISTS truth CASCADE;
DROP TABLE IF EXISTS churn_seen CASCADE;
DROP TABLE IF EXISTS maint CASCADE;
DROP TABLE IF EXISTS horizon CASCADE;
DROP TABLE IF EXISTS pageclass CASCADE;
DROP TABLE IF EXISTS precond CASCADE;
DROP VIEW IF EXISTS verdicts CASCADE;

-- One row per numbered fixture index.
CREATE TABLE plan(num int, leg text DEFAULT '', grp text, req text, idx text,
                  want_stage text, note text,
                  PRIMARY KEY (num, leg));

-- One row per index per phase.  phase is 'built', 'init', 'churned', 'applied'.
-- idx_tuples is the index's own pg_class.reltuples, which the heuristic now
-- reads as its third gate input; base_idx_tuples is the itup field of the
-- stored payload, parsed here independently of the filed text.
CREATE TABLE snap(phase text, idx text, idx_oid oid, bytes bigint,
                  tbl_tuples numeric, idx_tuples numeric, cmt text, payload text,
                  base_bytes numeric, base_tuples numeric, base_idx_tuples numeric,
                  PRIMARY KEY (phase, idx));

-- What the heuristic decided, and what a rebuild actually gave back.
CREATE TABLE truth(idx text PRIMARY KEY, action text, baseline text,
                   wasted_pct numeric, notes text,
                   bytes_churned bigint, bytes_applied bigint, bytes_fresh bigint,
                   reindexed_by_heuristic bool, cmd_report text, cmd_written text);

CREATE OR REPLACE FUNCTION plan_add(n int, g text, r text, i text,
                                    w text DEFAULT NULL, lg text DEFAULT '',
                                    nt text DEFAULT NULL)
RETURNS void LANGUAGE sql AS
$$ INSERT INTO plan(num, leg, grp, req, idx, want_stage, note)
   VALUES (n, lg, g, r, i, w, nt) $$;

-- The write counters of every fixture table, recorded before the first churn
-- statement and again after the last, so that "the tables the churn touched"
-- is the engine's own record rather than a hand-written list.  The maintenance
-- assumption of the shared definition is then applied to exactly the tables
-- whose insert, update or delete counter moved.
CREATE TABLE churn_seen(phase text, tbl text, ins numeric, upd numeric,
                        del numeric, mods numeric, dead numeric,
                        last_analyze timestamptz,
                        PRIMARY KEY (phase, tbl));

-- One row per maintenance statement: the VACUUM (VERBOSE, ANALYZE) that the
-- assumption credits with maintaining the churn, and the proofs the no-defeat
-- rule asks for.  dead_not_removable is the VERBOSE line's own count, parsed
-- out of the server's message text; a non-zero value on a churned table means
-- a horizon was pinned and the fixture is repaired rather than scored.
CREATE TABLE maint(tbl text PRIMARY KEY, ord int, ins numeric, upd numeric,
                   del numeric, mods_before numeric, dead_before numeric,
                   analyzed_in_churn bool,
                   started timestamptz, ended timestamptz,
                   removed numeric, remain numeric, dead_not_removable numeric,
                   mods_after numeric, dead_after numeric, timeouts text);

-- The horizon holders, read immediately before each maintenance statement and
-- once after the census.  These are reads beside the statement, not an
-- interlock around it, which is the limitation the shared definition records
-- against itself.
CREATE TABLE horizon(step text, tbl text, at timestamptz, xmin_holders int,
                     open_xacts int, slots int, slot_xmins int, prepared int,
                     detail text);

-- The page classes of every fixture index after the maintenance step: the
-- deleted and half-dead pages a drain leaves behind, which is the visible
-- trace of a horizon that did or did not move.
CREATE TABLE pageclass(idx text PRIMARY KEY, leaf_pages numeric,
                       empty_pages numeric, deleted_pages numeric,
                       avg_leaf_density numeric, index_size numeric);

-- Preconditions the shared definition puts on a numbered fixture.  A fixture
-- whose precondition is not met scores nothing: the verdict view reports it as
-- UNMET PRECONDITION and every scored count excludes it.
CREATE TABLE precond(num int, leg text DEFAULT '', requirement text,
                     observed text, met bool, PRIMARY KEY (num, leg));

-- horizon_probe records who could be holding back a removal horizon at the
-- moment it is called: any other backend with a transaction open or an xmin
-- published, any replication slot, and any prepared transaction.  VACUUM's
-- OldestXmin folds in exactly those, so a clean reading on both sides of a
-- maintenance statement is the evidence that nothing pinned the horizon while
-- it ran.  The probe's own backend is excluded by pid: it is the session
-- issuing the maintenance, and its INSERT commits before the VACUUM begins.
CREATE OR REPLACE FUNCTION horizon_probe(p_step text, p_tbl text)
RETURNS void LANGUAGE sql AS $hp$
INSERT INTO horizon(step, tbl, at, xmin_holders, open_xacts, slots,
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
       (SELECT COALESCE(string_agg(a.pid || ':' || COALESCE(a.state, '?')
                                   || ':xmin=' || COALESCE(a.backend_xmin::text, '-'),
                                   ', ' ORDER BY a.pid), 'none')
          FROM pg_stat_activity a
         WHERE a.pid <> pg_backend_pid()
           AND (a.backend_xmin IS NOT NULL OR a.xact_start IS NOT NULL))
$hp$;

-- take_snap records, for every planned index, the facts the heuristic reads:
-- the file size, the table's estimated tuple count, and the baseline stored in
-- the index's own comment.  It parses the payload the same way the filed text
-- does, independently, so a disagreement is visible.
CREATE OR REPLACE PROCEDURE take_snap(ph text) LANGUAGE plpgsql AS $sn$
BEGIN
  DELETE FROM snap WHERE phase = ph;
  INSERT INTO snap
  SELECT ph, p.idx, c.oid, pg_relation_size(c.oid), t.reltuples::numeric,
         c.reltuples::numeric, d.description,
         substring(d.description from '@btmaint:(\{[^}]*\})'),
         substring(d.description from '"sz":([0-9]{1,25})[,}]')::numeric,
         substring(d.description from
                   '"tup":(-?[0-9]{1,25}(?:[.][0-9]{1,10})?)[,}]')::numeric,
         substring(d.description from
                   '"itup":(-?[0-9]{1,25}(?:[.][0-9]{1,10})?)[,}]')::numeric
    FROM plan p
    JOIN pg_class c ON c.relname = p.idx AND c.relkind = 'i'
    JOIN pg_index x ON x.indexrelid = c.oid
    JOIN pg_class t ON t.oid = x.indrelid
    LEFT JOIN pg_description d ON d.objoid = c.oid
                              AND d.classoid = 'pg_class'::regclass
                              AND d.objsubid = 0;
END $sn$;

-- ground_truth rebuilds every planned index and records the fresh size.  It is
-- the oracle: what REINDEX INDEX actually gives back on the churned file.
CREATE OR REPLACE PROCEDURE ground_truth() LANGUAGE plpgsql AS $gt$
DECLARE p record;
BEGIN
  FOR p IN SELECT idx FROM plan ORDER BY num, leg LOOP
    EXECUTE format('REINDEX /* wiki_btmaint_oracle */ INDEX %I', p.idx);
    UPDATE truth SET bytes_fresh = pg_relation_size(p.idx::regclass)
     WHERE idx = p.idx;
  END LOOP;
END $gt$;

-- The verdict view. actual_pct is what the rebuild of the churned file gave
-- back, measured, and is the only oracle. expected_stage recomputes the gate
-- from the recorded baseline, independently of the filed text.
CREATE OR REPLACE VIEW verdicts AS
SELECT p.num, p.leg, p.grp, p.idx, p.req, p.want_stage,
       ct.relname                                            AS tbl,
       -- A fixture whose shared-definition precondition was not met scores
       -- nothing; every count below that says "scored" filters on this.
       (pc.met IS DISTINCT FROM false)                        AS scored,
       pc.observed                                            AS precond_observed,
       -- The maintenance the assumption credits, and the no-defeat proofs.
       (m.tbl IS NOT NULL)                                    AS maintained,
       m.dead_not_removable, m.removed AS maint_removed,
       m.dead_after, m.mods_before, m.mods_after, m.timeouts,
       q.deleted_pages, q.empty_pages, q.avg_leaf_density AS density_after_maint,
       t.action, t.baseline, t.wasted_pct, t.reindexed_by_heuristic,
       bu.bytes AS bytes_built, ic.bytes AS bytes_init,
       t.bytes_churned, t.bytes_applied, t.bytes_fresh,
       round(100.0 * (t.bytes_churned - t.bytes_fresh)
             / GREATEST(t.bytes_churned, 1), 1)                  AS actual_pct,
       round(100.0 * (t.bytes_churned - t.bytes_applied)
             / GREATEST(t.bytes_churned, 1), 1)                  AS applied_pct,
       ic.base_bytes AS base_bytes, ic.base_tuples AS base_tuples,
       ch.tbl_tuples AS churned_tuples,
       CASE WHEN ic.base_bytes > 0
            THEN round(ch.bytes / ic.base_bytes, 4) END          AS size_ratio,
       CASE WHEN ic.base_tuples > 0
            THEN round(ch.tbl_tuples / ic.base_tuples, 4) END    AS tuple_ratio,
       -- The index's own entry count: the baseline the payload stored, the
       -- count the catalog holds after the churn, and their ratio.  The
       -- payload value is what the heuristic reads; ic.idx_tuples is the live
       -- catalog value at baseline time, so the two must agree.
       ic.base_idx_tuples, ch.idx_tuples AS churned_idx_tuples,
       (ic.base_idx_tuples = round(ic.idx_tuples))               AS itup_stored_matches,
       CASE WHEN ic.base_idx_tuples > 0
            THEN round(ch.idx_tuples / ic.base_idx_tuples, 4) END AS idx_tuple_ratio,
       -- Which of the three gates fires, each recomputed here from the
       -- recorded baseline, independently of the filed text.
       (ic.base_bytes > 0 AND ch.bytes >= ic.base_bytes * 1.20)  AS size_gate_fires,
       (ch.tbl_tuples >= 0 AND ic.base_tuples >= 0
        AND (CASE WHEN ic.base_tuples = 0 THEN ch.tbl_tuples > 0
                  ELSE abs(ch.tbl_tuples - ic.base_tuples)
                       >= ic.base_tuples * 0.20 END))            AS tbl_gate_fires,
       (ch.idx_tuples >= 0 AND ic.base_idx_tuples >= 0
        AND (CASE WHEN ic.base_idx_tuples = 0 THEN ch.idx_tuples > 0
                  ELSE abs(ch.idx_tuples - ic.base_idx_tuples)
                       >= ic.base_idx_tuples * 0.20 END))        AS idx_gate_fires,
       -- The sz the report proposed to store, against the sz that was stored.
       substring(t.cmd_report from '"sz":([0-9]+)')::numeric      AS sz_reported,
       substring(t.cmd_written from '"sz":([0-9]+)')::numeric     AS sz_written,
       substring(t.cmd_written from '"itup":(-?[0-9]+)')::numeric AS itup_written,
       CASE WHEN ic.payload IS NULL                              THEN 'initialize'
            WHEN ic.base_bytes IS NULL OR ic.base_tuples IS NULL
              OR ic.base_idx_tuples IS NULL                      THEN 'initialize'
            WHEN ic.base_bytes > 0 AND ch.bytes < ic.base_bytes  THEN 'refresh'
            WHEN ic.base_bytes > 0 AND ch.bytes >= ic.base_bytes * 1.20
                                                                 THEN 'measure'
            WHEN ch.tbl_tuples >= 0 AND ic.base_tuples > 0
             AND abs(ch.tbl_tuples - ic.base_tuples) >= ic.base_tuples * 0.20
                                                                 THEN 'measure'
            WHEN ch.tbl_tuples >= 0 AND ic.base_tuples = 0 AND ch.tbl_tuples > 0
                                                                 THEN 'measure'
            WHEN ch.idx_tuples >= 0 AND ic.base_idx_tuples > 0
             AND abs(ch.idx_tuples - ic.base_idx_tuples) >= ic.base_idx_tuples * 0.20
                                                                 THEN 'measure'
            WHEN ch.idx_tuples >= 0 AND ic.base_idx_tuples = 0 AND ch.idx_tuples > 0
                                                                 THEN 'measure'
            ELSE 'skip' END                                      AS expected_stage,
       -- The two-gate form this page filed before the index count was stored,
       -- recomputed on the same fixtures so the change can be quantified.
       CASE WHEN ic.payload IS NULL                              THEN 'initialize'
            WHEN ic.base_bytes IS NULL OR ic.base_tuples IS NULL THEN 'initialize'
            WHEN ic.base_bytes > 0 AND ch.bytes < ic.base_bytes  THEN 'refresh'
            WHEN ic.base_bytes > 0 AND ch.bytes >= ic.base_bytes * 1.20
                                                                 THEN 'measure'
            WHEN ch.tbl_tuples >= 0 AND ic.base_tuples > 0
             AND abs(ch.tbl_tuples - ic.base_tuples) >= ic.base_tuples * 0.20
                                                                 THEN 'measure'
            WHEN ch.tbl_tuples >= 0 AND ic.base_tuples = 0 AND ch.tbl_tuples > 0
                                                                 THEN 'measure'
            ELSE 'skip' END                                      AS two_gate_stage,
       CASE WHEN t.action IN ('reindex', 'update') THEN 'measure'
            ELSE t.action END                                    AS taken_stage,
       -- The rebuild oracle against the 40 % decision.  A fixture whose
       -- precondition was not met is reported and not scored, which is what
       -- the shared definition requires of test 120.
       CASE WHEN pc.met = false                                  THEN 'UNMET PRECONDITION'
            WHEN t.action IS NULL                                THEN 'ABSENT'
            WHEN t.action = 'reindex'
             AND round(100.0 * (t.bytes_churned - t.bytes_fresh)
                       / GREATEST(t.bytes_churned, 1), 1) < 10    THEN 'CRITICAL FALSE POSITIVE'
            WHEN t.action = 'reindex'
             AND round(100.0 * (t.bytes_churned - t.bytes_fresh)
                       / GREATEST(t.bytes_churned, 1), 1) < 35    THEN 'FALSE POSITIVE'
            WHEN t.action <> 'reindex'
             AND round(100.0 * (t.bytes_churned - t.bytes_fresh)
                       / GREATEST(t.bytes_churned, 1), 1) >= 50   THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END                                      AS verdict,
       -- Where a false negative was lost: the gate never measured, or the
       -- measurement read 40 % or less on a file a rebuild did shrink.
       CASE WHEN t.action IN ('skip', 'initialize', 'refresh')
             AND round(100.0 * (t.bytes_churned - t.bytes_fresh)
                       / GREATEST(t.bytes_churned, 1), 1) >= 50   THEN 'gate'
            WHEN t.action = 'update'
             AND round(100.0 * (t.bytes_churned - t.bytes_fresh)
                       / GREATEST(t.bytes_churned, 1), 1) >= 50   THEN 'threshold'
            ELSE NULL END                                        AS lost_by,
       t.notes, p.note
  FROM plan p
  LEFT JOIN truth t ON t.idx = p.idx
  LEFT JOIN snap bu ON bu.phase = 'built'   AND bu.idx = p.idx
  LEFT JOIN snap ic ON ic.phase = 'init'    AND ic.idx = p.idx
  LEFT JOIN snap ch ON ch.phase = 'churned' AND ch.idx = p.idx
  -- The fixture's table, so that the maintenance row can be joined to it.  A
  -- plain REINDEX keeps the index's pg_class row, so these names still resolve
  -- after the oracle has rebuilt every fixture.
  LEFT JOIN pg_class ci ON ci.relname = p.idx AND ci.relkind = 'i'
  LEFT JOIN pg_index xi ON xi.indexrelid = ci.oid
  LEFT JOIN pg_class ct ON ct.oid = xi.indrelid
  LEFT JOIN maint m     ON m.tbl = ct.relname
  LEFT JOIN pageclass q ON q.idx = p.idx
  LEFT JOIN precond pc  ON pc.num = p.num AND pc.leg = p.leg;
HARNESS
  cat > "$SQLD/fixtures_build.sql" <<'FIXTURES_BUILD'
-- The numbered suite, build phase: every fixture up to and including the
-- creation of the index that is scored.  The churn file carries the rest of
-- each recipe, so that the heuristic can store a baseline for a freshly built
-- index and then be asked about the same index after it has been disturbed.
--
-- Disposable fixtures.  Everything below creates, forges and drops objects in
-- the suite database of the sandbox cluster.  It is not meant for a database
-- anyone cares about.
--
-- The recipes are the numbered fixtures of the wiki's shared definition,
-- "Mandatory B-Tree Bloat Tests": tests 1-17 (deduplication gate), 18-91
-- (partial indexes) and controls 92-120, less the numbers that page retired -
-- 11, 38, 65, 67, 69, 106, 117 and 121, and legs 113a and 113c.  Retired
-- numbers are not reused and their recipes are gone from this file.
--
-- Two deviations, both deliberate: pg_stat_force_next_flush() is not called,
-- because this heuristic reads pg_class.reltuples and never a cumulative
-- statistics view; and the support-function-4 and ICU fixtures live in their
-- own files, because those features do not exist in every server this text has
-- to run on.  The shared definition's maintenance assumption is applied, but
-- not here: this file ends at each CREATE INDEX, the churn file carries the
-- writes, and the maintenance step that follows it vacuums and analyzes every
-- table those writes touched.
SET /* wiki_btmaint_fixtures_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_fixtures_statement_timeout */ statement_timeout = '900s';
SET /* wiki_btmaint_fixtures_lock_timeout */ lock_timeout = '5s';
SET /* wiki_btmaint_fixtures_maintenance_work_mem */ maintenance_work_mem = '256MB';

-- ======================================================== tests 1-17 ========
-- The deduplication gate's two 500,000-row tables and its custom operator
-- classes.  For this heuristic the group asks a different question than it did
-- for the estimator: every equal-image class must survive the same 90 % drain
-- and be measured, and the 40 % decision must agree with a rebuild.
--
-- Every fixture that needs a B-tree support function 4 lives in the
-- PostgreSQL 13 file, because support function 4 is the deduplication
-- equal-image callback: a 12 server answers "invalid function number 4, must
-- be between 1 and 3" and the whole file would abort here.  What stays is the
-- one custom operator class that declares no support function 4 at all.
CREATE OPERATOR CLASS int4_ei_none FOR TYPE int4 USING btree AS
  OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
  OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
  FUNCTION 1 btint4cmp(int4,int4);

CREATE TABLE t AS
SELECT i::int4 AS u, (i % 5000)::int4 AS a, (i % 5000)::int8 AS b,
       'key' || lpad((i % 5000)::text, 8, '0') AS s, ((i % 5000)::numeric) AS n,
       (i % 5000)::float4 AS f4, (i % 5000)::float8 AS f8, (i % 7)::int4 AS d
  FROM generate_series(1, 500000) i;
CREATE TABLE t2 AS
SELECT i::int4 AS u, (i % 5000)::int4 AS a, (i % 5000)::int8 AS b,
       'key' || lpad((i % 5000)::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE t;
ANALYZE t2;

CREATE INDEX i_int4          ON t (a);
CREATE INDEX i_int8          ON t (b);
CREATE INDEX i_text_det      ON t (s);
CREATE INDEX i_numeric       ON t (n);
CREATE INDEX i_float4        ON t (f4);
CREATE INDEX i_float8        ON t (f8);
CREATE INDEX i_multi_ok      ON t (a, b);
CREATE INDEX i_multi_bad     ON t (a, n);
CREATE INDEX i_expr_num      ON t ((a::numeric));
CREATE INDEX i_inc           ON t (a) INCLUDE (d);
CREATE INDEX i_ei_none       ON t (a int4_ei_none);
CREATE UNIQUE INDEX i_uniq   ON t (u);
CREATE INDEX i2_ok           ON t2 (a, b);

SELECT plan_add(1,  'gate', 'int4 key, 100 rows per key', 'i_int4', 'measure', 'i_int4');
SELECT plan_add(2,  'gate', 'int8 key, 100 rows per key', 'i_int8', 'measure', 'i_int8');
SELECT plan_add(3,  'gate', 'text key, deterministic default collation', 'i_text_det', 'measure', 'i_text_det');
SELECT plan_add(5,  'gate', 'numeric key, no equal-image support', 'i_numeric', 'measure', 'i_numeric');
SELECT plan_add(6,  'gate', 'float4 key', 'i_float4', 'measure', 'i_float4');
SELECT plan_add(6,  'gate', 'float8 key', 'i_float8', 'measure', 'i_float8');
SELECT plan_add(7,  'gate', 'two equal-image key columns', 'i_multi_ok', 'measure', 'i_multi_ok');
SELECT plan_add(8,  'gate', 'one non-equal-image key column', 'i_multi_bad', 'measure', 'i_multi_bad');
SELECT plan_add(9,  'gate', 'expression key, numeric', 'i_expr_num', 'measure', 'i_expr_num');
SELECT plan_add(10, 'gate', 'INCLUDE column refuses deduplication', 'i_inc', 'measure', 'i_inc');
SELECT plan_add(12, 'gate', 'opclass with no support function 4', 'i_ei_none', 'measure', 'i_ei_none');
SELECT plan_add(17, 'gate', 'unique key control; carried to the 12 leg as test 17', 'i_uniq', 'measure', 'i_uniq');
SELECT plan_add(7,  'gate', 'second table, two equal-image columns', 'i2_ok', 'measure', 'i2_ok');

-- ======================================================= tests 18-21 ========
CREATE TABLE pt1 AS
SELECT i::bigint AS k, (i % 100)::int AS sel FROM generate_series(1, 1000000) i;
ANALYZE pt1;
CREATE INDEX p18 ON pt1 (k) WHERE sel < 20;
CREATE INDEX p19 ON pt1 (k) WHERE sel < 1;
CREATE INDEX p20 ON pt1 (k) WHERE sel < 10;
CREATE INDEX p21 ON pt1 (k) WHERE sel < 80;
SELECT plan_add(18, 'partial', 'baseline, subset distribution = table (20%)', 'p18', 'measure');
SELECT plan_add(19, 'partial', 'very selective, ~1%', 'p19', 'measure');
SELECT plan_add(20, 'partial', 'moderately selective, ~10%', 'p20', 'measure');
SELECT plan_add(21, 'partial', 'large subset, ~80%', 'p21', 'measure');

-- ======================================================= tests 22-33 ========
CREATE TABLE pd22 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd22;
CREATE INDEX p22 ON pd22 (k) WHERE hot;
SELECT plan_add(22, 'partial', 'highly duplicated subset, unique outside', 'p22', 'measure');

CREATE TABLE pd23 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE ((i / 5) % 100)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd23;
CREATE INDEX p23 ON pd23 (k) WHERE hot;
SELECT plan_add(23, 'partial', 'highly unique subset, duplicated outside', 'p23', 'measure');

CREATE TABLE pd24 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50000)::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd24;
CREATE INDEX p24 ON pd24 (k) WHERE hot;
SELECT plan_add(24, 'partial', 'n_distinct radically different in the subset', 'p24', 'measure');

CREATE TABLE pd25 AS SELECT (i % 100 = 0) AS hot,
       CASE WHEN i % 100 = 0 THEN ((i / 100) % 997)::int ELSE (i % 5)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd25;
CREATE INDEX p25 ON pd25 (k) WHERE hot;
SELECT plan_add(25, 'partial', 'MCV distribution differs inside the subset', 'p25', 'measure');

CREATE TABLE pd26 AS SELECT (i % 50 = 0) AS hot,
       CASE WHEN i % 50 = 0 THEN (1000000 + i)::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd26;
CREATE INDEX p26 ON pd26 (k) WHERE hot;
SELECT plan_add(26, 'partial', 'table-wide MCVs absent inside the subset', 'p26', 'measure');

CREATE TABLE pd27 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 AND i % 100 <> 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd27;
CREATE INDEX p27 ON pd27 (k) WHERE hot;
SELECT plan_add(27, 'partial', 'NULL-heavy subset, non-NULL outside', 'p27', 'measure');

CREATE TABLE pd28 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN i::bigint ELSE NULL END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd28;
CREATE INDEX p28 ON pd28 (k) WHERE hot;
SELECT plan_add(28, 'partial', 'NULL-free subset, NULL-heavy table (bigint)', 'p28', 'measure');

CREATE TABLE pd29 AS
SELECT CASE WHEN i % 5 = 0 THEN NULL ELSE lpad(i::text, 20, '0') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE pd29;
CREATE INDEX p29 ON pd29 (s) WHERE s IS NULL;
SELECT plan_add(29, 'partial', 'all-NULL partial index, WHERE s IS NULL', 'p29', 'skip');

CREATE TABLE pd30 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE pd30;
CREATE INDEX p30 ON pd30 (s) WHERE hot;
SELECT plan_add(30, 'partial', 'subset values wider than outside (13 against 204 bytes)', 'p30', 'measure');

CREATE TABLE pd31 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN lpad((i % 9)::text, 12, 'n')
            ELSE repeat('W', 190) || lpad(i::text, 10, '0') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE pd31;
CREATE INDEX p31 ON pd31 (s) WHERE hot;
SELECT plan_add(31, 'partial', 'subset values narrower than outside', 'p31', 'measure');

CREATE TABLE pw32 AS
SELECT (i % 50 = 0) AS hot,
       CASE WHEN i % 50 = 0 THEN repeat('W', 390) || lpad(i::text, 10, '0')
            ELSE repeat('n', 18) || (i % 9)::text END AS s
  FROM generate_series(1, 500000) i;
ANALYZE pw32;
CREATE INDEX p32 ON pw32 (s) WHERE hot;
SELECT plan_add(32, 'partial', 'extreme width mismatch (27 against 404 bytes)', 'p32', 'measure');

CREATE TABLE pd33 AS SELECT (i % 5 = 0) AS hot,
       lpad(i::text, 10 + (i % 40), 'x') AS s FROM generate_series(1, 500000) i;
ANALYZE pd33;
CREATE INDEX p33 ON pd33 (s) WHERE hot;
SELECT plan_add(33, 'partial', 'variable-width values, same range inside and out', 'p33', 'measure');

-- ======================================================= tests 34-39 ========
CREATE TABLE pd34 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd34;
CREATE INDEX p34 ON pd34 (k) WHERE hot;
SELECT plan_add(34, 'partial', 'dedup-heavy subset, 1000 rows per key', 'p34', 'measure');

CREATE TABLE pd35 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd35;
CREATE INDEX p35 ON pd35 (k) WHERE hot;
SELECT plan_add(35, 'partial', 'duplicate-heavy table, unique subset', 'p35', 'measure');

CREATE TABLE pd36 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN 42 ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd36;
CREATE INDEX p36 ON pd36 (k) WHERE hot;
SELECT plan_add(36, 'partial', 'one key group, 100,000 TIDs against a 132 cap', 'p36', 'measure');

CREATE TABLE pd37 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd37;
CREATE INDEX p37 ON pd37 (k) WHERE hot;
SELECT plan_add(37, 'partial', 'NULL deduplication, every subset key NULL', 'p37', 'measure');

CREATE TABLE pd39 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd39;
CREATE UNIQUE INDEX p39 ON pd39 (k) WHERE hot;
SELECT plan_add(39, 'partial', 'partial UNIQUE index', 'p39', 'measure');

-- ======================================================= tests 40-47 ========
CREATE TABLE pd40 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 97)::int  END AS b
  FROM generate_series(1, 500000) i;
ANALYZE pd40;
CREATE INDEX p40 ON pd40 (a, b) WHERE hot;
SELECT plan_add(40, 'partial', 'two-column key correlated only in the subset', 'p40', 'measure');

CREATE TABLE pd41 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 97)::int  ELSE (i % 100)::int END AS b
  FROM generate_series(1, 500000) i;
ANALYZE pd41;
CREATE INDEX p41 ON pd41 (a, b) WHERE hot;
SELECT plan_add(41, 'partial', 'two-column key independent only in the subset', 'p41', 'measure');

CREATE TABLE pd42 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50)::int ELSE i::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50)::int ELSE i::int END AS b
  FROM generate_series(1, 500000) i;
ANALYZE pd42;
CREATE INDEX p42 ON pd42 (a, b) WHERE hot;
SELECT plan_add(42, 'partial', 'multi-column duplicate keys in the subset', 'p42', 'measure');

CREATE TABLE pd43 AS SELECT (i % 5 = 0) AS hot, i::int AS a, (i * 2)::int AS b
  FROM generate_series(1, 500000) i;
ANALYZE pd43;
CREATE INDEX p43 ON pd43 (a, b) WHERE hot;
SELECT plan_add(43, 'partial', 'multi-column unique keys in the subset', 'p43', 'measure');

CREATE TABLE pd44a AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
ANALYZE pd44a;
CREATE INDEX p44a ON pd44a (a, b) WHERE hot;
SELECT plan_add(44, 'partial', 'multicolumn key, no ndistinct object', 'p44a', 'measure', 'a');
CREATE TABLE pd44b AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS pd44b_nd (ndistinct) ON a, b FROM pd44b;
ANALYZE pd44b;
CREATE INDEX p44b ON pd44b (a, b) WHERE hot;
SELECT plan_add(44, 'partial', 'multicolumn key, with CREATE STATISTICS (ndistinct)', 'p44b', 'measure', 'b');

CREATE TABLE pd45 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 97)::int  ELSE (i % 100)::int END AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS pd45_nd (ndistinct) ON a, b FROM pd45;
ANALYZE pd45;
CREATE INDEX p45 ON pd45 (a, b) WHERE hot;
SELECT plan_add(45, 'partial', 'extended statistics wrong for the subset', 'p45', 'measure');

CREATE TABLE pd46 AS SELECT (i % 5 = 0) AS hot, i::int AS k, (i % 7)::int AS pay
  FROM generate_series(1, 500000) i;
ANALYZE pd46;
CREATE INDEX p46 ON pd46 (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(46, 'partial', 'partial index with INCLUDE columns', 'p46', 'measure');

CREATE TABLE pi47 AS SELECT (i % 20 = 0) AS hot, i::int AS k,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS payload
  FROM generate_series(1, 500000) i;
ANALYZE pi47;
CREATE INDEX p47 ON pi47 (k) INCLUDE (payload) WHERE hot;
SELECT plan_add(47, 'partial', 'wide INCLUDE values inside the subset', 'p47', 'measure');

-- ======================================================= tests 48-55 ========
CREATE TABLE pe48 AS SELECT (i % 5 = 0) AS active,
       CASE WHEN i % 5 = 0 THEN 'NAME' || lpad(((i / 5) % 20)::text, 6, '0')
            ELSE 'name' || lpad((i % 100)::text, 6, '0') END AS name
  FROM generate_series(1, 500000) i;
ANALYZE pe48;
CREATE INDEX p48 ON pe48 (lower(name)) WHERE active;
SELECT plan_add(48, 'partial', 'partial expression index, lower(name) WHERE active', 'p48', 'measure');
CREATE TABLE pe48b AS SELECT (i % 5 = 0) AS active,
       CASE WHEN i % 5 = 0 THEN 'NAME' || lpad(((i / 5) % 20)::text, 6, '0')
            ELSE 'name' || lpad((i % 100)::text, 6, '0') END AS name
  FROM generate_series(1, 500000) i;
CREATE INDEX p48b ON pe48b (lower(name)) WHERE active;
ANALYZE pe48b;
SELECT plan_add(48, 'partial', 'the same after one ANALYZE with the index in place', 'p48b', 'measure', 'b');

CREATE TABLE pe49 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE pe49;
CREATE INDEX p49 ON pe49 (upper(s)) WHERE hot;
SELECT plan_add(49, 'partial', 'expression width mismatch in the subset', 'p49', 'measure');
CREATE TABLE pe49b AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX p49b ON pe49b (upper(s)) WHERE hot;
ANALYZE pe49b;
SELECT plan_add(49, 'partial', 'the same after one ANALYZE with the index in place', 'p49b', 'measure', 'b');

CREATE TABLE pe50 AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE pe50;
CREATE INDEX p50 ON pe50 (upper(s)) WHERE hot;
SELECT plan_add(50, 'partial', 'missing expression statistics, 32-byte fallback', 'p50', 'measure');
CREATE TABLE pe50b AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX p50b ON pe50b (upper(s)) WHERE hot;
ANALYZE pe50b;
SELECT plan_add(50, 'partial', 'the same after one ANALYZE with the index in place', 'p50b', 'measure', 'b');

CREATE TABLE pf AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pf;
CREATE INDEX p53 ON pf (k) WHERE hot;
CREATE INDEX p54 ON pf (k) WITH (fillfactor = 100) WHERE hot;
CREATE INDEX p55 ON pf (k) WITH (fillfactor = 70)  WHERE hot;
SELECT plan_add(53, 'partial', 'default fillfactor 90', 'p53', 'measure');
SELECT plan_add(54, 'partial', 'fillfactor = 100', 'p54', 'measure');
SELECT plan_add(55, 'partial', 'fillfactor = 70', 'p55', 'measure');

-- ======================================================= tests 56-63 ========
CREATE TABLE ps AS
SELECT (i % 5 = 0) AS flag,
       CASE WHEN i % 5 = 0 THEN 'OPEN' ELSE 'CLOSED' END AS status,
       timestamptz '2020-01-01' + (i * interval '1 minute') AS created,
       CASE WHEN i % 5 = 0 THEN NULL ELSE i::int END AS nk,
       i::int AS k, (i % 1000)::int AS k2
  FROM generate_series(1, 500000) i;
ANALYZE ps;
CREATE INDEX p56 ON ps (k) WHERE flag;
CREATE INDEX p57 ON ps (k) WHERE status = 'OPEN';
CREATE INDEX p58 ON ps (k) WHERE created >= timestamptz '2020-09-01';
CREATE INDEX p59 ON ps (k) WHERE nk IS NULL;
CREATE INDEX p60 ON ps (k) WHERE nk IS NOT NULL;
CREATE INDEX p61 ON ps (k) WHERE flag AND status = 'OPEN';
CREATE INDEX p62 ON ps (k) WHERE k < 100000;
CREATE INDEX p63 ON ps (k2) WHERE k >= 400000;
SELECT plan_add(56, 'partial', 'boolean predicate, WHERE flag', 'p56', 'measure');
SELECT plan_add(57, 'partial', 'equality predicate, status = OPEN', 'p57', 'measure');
SELECT plan_add(58, 'partial', 'range predicate, created >= ...', 'p58', 'measure');
SELECT plan_add(59, 'partial', 'IS NULL predicate on a non-key column', 'p59', 'measure');
SELECT plan_add(60, 'partial', 'IS NOT NULL predicate', 'p60', 'measure');
SELECT plan_add(61, 'partial', 'multi-column predicate', 'p61', 'measure');
SELECT plan_add(62, 'partial', 'predicate correlated with the indexed value', 'p62', 'measure');
SELECT plan_add(63, 'partial', 'predicate negatively correlated with the value', 'p63', 'measure');

-- ==================================================== tests 64, 66, 68 ======
-- 65, 67 and 69 are retired by the shared definition: each withheld a VACUUM,
-- or the ANALYZE after one, and withheld maintenance is no longer a fixture
-- shape.  Their numbers are not reused.
CREATE TABLE pc64 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pc64;
CREATE INDEX p64 ON pc64 (k) WHERE hot;
SELECT plan_add(64, 'partial', 'stale statistics after inserts into the subset', 'p64', 'measure');

CREATE TABLE pc66 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pc66;
CREATE INDEX p66 ON pc66 (k) WHERE hot;
SELECT plan_add(66, 'partial', 'rows entering the index (false -> true)', 'p66', 'measure');

CREATE TABLE pc68 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pc68;
CREATE INDEX p68 ON pc68 (k) WHERE hot;
SELECT plan_add(68, 'partial', 'heavy predicate churn, then VACUUM + ANALYZE', 'p68', 'measure');

-- ======================================================= tests 70-77 ========
CREATE TABLE pb AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pb;
CREATE INDEX p70 ON pb (k) WHERE hot;
SELECT plan_add(70, 'partial', 'freshly created partial index', 'p70', 'skip');
CREATE INDEX p71 ON pb (k) WHERE hot;
SELECT plan_add(71, 'partial', 'freshly REINDEXed partial index', 'p71', 'skip');

CREATE TABLE pb72 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE pb72;
CREATE INDEX p72 ON pb72 (k) WHERE hot;
SELECT plan_add(72, 'partial', '25% of the subset deleted', 'p72', 'measure');

CREATE TABLE pb73 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE pb73;
CREATE INDEX p73 ON pb73 (k) WHERE hot;
SELECT plan_add(73, 'partial', '50% of the subset deleted', 'p73', 'measure');

CREATE TABLE pb74 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE pb74;
CREATE INDEX p74 ON pb74 (k) WHERE hot;
SELECT plan_add(74, 'partial', '75% of the subset deleted', 'p74', 'measure');

CREATE TABLE pb75 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE pb75;
CREATE INDEX p75 ON pb75 (k) WHERE hot;
SELECT plan_add(75, 'partial', '90% of the subset deleted (corrected recipe)', 'p75', 'measure');

CREATE TABLE pb76 AS SELECT (i % 5 = 0) AS hot, i::int AS k, 'x'::text AS pad
  FROM generate_series(1, 500000) i;
ANALYZE pb76;
CREATE INDEX p76 ON pb76 (k) WHERE hot;
SELECT plan_add(76, 'partial', 'bloated through indexed-key UPDATEs', 'p76', 'measure');

CREATE TABLE pb77 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE pb77;
CREATE INDEX p77 ON pb77 (k) WHERE hot;
SELECT plan_add(77, 'partial', 'many empty and deleted B-tree pages', 'p77', 'measure');

-- ======================================================= tests 78-85 ========
CREATE TABLE f78t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 290) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE f78t;
CREATE INDEX f78 ON f78t (s) WHERE hot;
SELECT plan_add(78, 'falsepos', 'predicate-conditioned width mismatch', 'f78', 'skip');

CREATE TABLE f79t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('t', 300) || lpad(i::text, 4, '0')
            ELSE NULL END AS s
  FROM generate_series(1, 500000) i;
ANALYZE f79t;
CREATE INDEX f79 ON f79t (s) WHERE hot;
SELECT plan_add(79, 'falsepos', 'predicate-conditioned NULL mismatch', 'f79', 'skip');

CREATE TABLE f80t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE f80t;
CREATE INDEX f80 ON f80t (k) WHERE hot;
SELECT plan_add(80, 'falsepos', 'predicate-conditioned n_distinct mismatch', 'f80', 'skip');

CREATE TABLE f81t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 20)::int ELSE 7 END AS k
  FROM generate_series(1, 500000) i;
ANALYZE f81t;
CREATE INDEX f81 ON f81t (k) WHERE hot;
SELECT plan_add(81, 'falsepos', 'predicate-conditioned MCV mismatch', 'f81', 'skip');

CREATE TABLE f82t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 89)::int  END AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS f82_nd (ndistinct) ON a, b FROM f82t;
ANALYZE f82t;
CREATE INDEX f82 ON f82t (a, b) WHERE hot;
SELECT plan_add(82, 'falsepos', 'predicate-conditioned multi-column correlation', 'f82', 'skip');

CREATE TABLE f83t AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE f83t;
CREATE INDEX f83 ON f83t (md5(s), lower(s)) WHERE hot;
SELECT plan_add(83, 'falsepos', 'missing index/expression statistics', 'f83', 'skip');

CREATE TABLE f84t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE f84t;
CREATE INDEX f84 ON f84t (k) WHERE hot;
SELECT plan_add(84, 'falsepos', 'stale partial-index reltuples', 'f84', 'skip');

CREATE TABLE f85t AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE f85t;
UPDATE f85t SET s = repeat('W', 200) || s WHERE hot;
VACUUM f85t;
CREATE INDEX f85 ON f85t (s) WHERE hot;
SELECT plan_add(85, 'falsepos', 'stale table statistics', 'f85', 'skip');

-- ======================================================= tests 86-91 ========
CREATE TABLE f86t AS SELECT (i % 5 = 0) AS hot, ((i / 5) % 100)::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE f86t;
CREATE INDEX f86 ON f86t (k) WHERE hot;
SELECT plan_add(86, 'falseneg', 'duplicate concentration inside the subset', 'f86', 'measure');

CREATE TABLE f87t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE f87t;
CREATE INDEX f87 ON f87t (k) WHERE hot;
SELECT plan_add(87, 'falseneg', 'NULL concentration inside the subset', 'f87', 'measure');

CREATE TABLE f88t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN lpad((i % 9)::text, 9, '0')
            ELSE repeat('W', 390) || lpad(i::text, 10, '0') END AS s
  FROM generate_series(1, 200000) i;
ANALYZE f88t;
CREATE INDEX f88 ON f88t (s) WHERE hot;
SELECT plan_add(88, 'falseneg', 'subset narrower than table statistics', 'f88', 'measure');

CREATE TABLE f89t AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
ANALYZE f89t;
CREATE INDEX f89 ON f89t (a, b) WHERE hot;
SELECT plan_add(89, 'falseneg', 'conditional multi-column correlation', 'f89', 'measure');

CREATE TABLE f90t AS SELECT (i % 5 = 0) AS hot, ((i / 5) % 1000)::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE f90t;
CREATE INDEX f90 ON f90t (k) WHERE hot;
SELECT plan_add(90, 'falseneg', 'real deduplication stronger than predicted', 'f90', 'measure');

CREATE TABLE f91t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN lpad((i % 9)::text, 9, '0')
            ELSE repeat('W', 390) || lpad(i::text, 10, '0') END AS s,
       i::int AS ord
  FROM generate_series(1, 200000) i;
ANALYZE f91t;
CREATE INDEX f91 ON f91t (s) WHERE hot;
SELECT plan_add(91, 'falseneg', 'many deleted pages plus an over-predicting model', 'f91', 'measure');

-- ====================================================== tests 92-95 =========
CREATE TABLE b92t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE b92t;
CREATE INDEX b92 ON b92t (k) WHERE hot;
SELECT plan_add(92, 'control', '1,000 rows updated under the old GUC threshold', 'b92', 'measure');

CREATE TABLE b93t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE b93t;
CREATE INDEX b93 ON b93t (k) WHERE hot;
SELECT plan_add(93, 'control', 'rows updated above the old GUC threshold', 'b93', 'measure');

CREATE TABLE b94t (hot bool, k int)
  WITH (autovacuum_analyze_threshold = 100, autovacuum_analyze_scale_factor = 0);
INSERT INTO b94t SELECT (i % 5 = 0), i FROM generate_series(1, 500000) i;
ANALYZE b94t;
CREATE INDEX b94 ON b94t (k) WHERE hot;
SELECT plan_add(94, 'control', '1,000 rows updated, table reloption threshold 100', 'b94', 'measure');

CREATE TABLE b95t (hot bool, k int)
  WITH (autovacuum_analyze_threshold = 200000, autovacuum_analyze_scale_factor = 1);
INSERT INTO b95t SELECT (i % 5 = 0), i FROM generate_series(1, 500000) i;
ANALYZE b95t;
CREATE INDEX b95 ON b95t (k) WHERE hot;
SELECT plan_add(95, 'control', 'many rows updated, table reloption threshold 200,000', 'b95', 'measure');

-- ====================================================== tests 96-99 =========
CREATE TABLE np AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE np;
CREATE INDEX np96 ON np (k);
CREATE INDEX np97 ON np (upper(s));
SELECT plan_add(96, 'control', 'plain index, fresh statistics', 'np96', 'skip');
SELECT plan_add(97, 'control', 'expression index, no statistics row', 'np97', 'skip');

CREATE TABLE np98t AS SELECT i::int AS k FROM generate_series(1, 500000) i;
ANALYZE np98t;
CREATE INDEX np98 ON np98t (k);
SELECT plan_add(98, 'control', 'plain index, stale row counts after 300,000 inserts', 'np98', 'measure');

CREATE TABLE np99t AS SELECT (i % 1000)::int AS k FROM generate_series(1, 500000) i;
ANALYZE np99t;
CREATE INDEX np99 ON np99t (k);
SELECT plan_add(99, 'control', 'duplicate-heavy index, genuinely reclaimable', 'np99', 'measure');

-- ===================================================== tests 100-105 ========
CREATE TABLE i100t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
ANALYZE i100t;
CREATE INDEX i100 ON i100t (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(100, 'control', 'partial + INCLUDE (text), 90% of the subset deleted', 'i100', 'measure');

CREATE TABLE i101t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
ANALYZE i101t;
CREATE INDEX i101 ON i101t (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(101, 'control', 'partial + INCLUDE (text), same width inside and outside', 'i101', 'skip');

CREATE TABLE i102t AS SELECT i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
ANALYZE i102t;
CREATE INDEX i102 ON i102t (k) INCLUDE (pay);
SELECT plan_add(102, 'control', 'non-partial + wide INCLUDE (text), freshly built', 'i102', 'skip');

CREATE TABLE i103t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad(i::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE i103t;
CREATE INDEX i103 ON i103t (s) WHERE hot;
SELECT plan_add(103, 'control', 'partial + wide key column, unique values', 'i103', 'skip');

CREATE TABLE i104t AS SELECT (i % 20 = 0) AS hot, i::int AS k,
       CASE WHEN i % 20 = 0 THEN lpad((i % 9)::text, 12, 'n')
            ELSE repeat('W', 190) || lpad(i::text, 10, '0') END AS pay
  FROM generate_series(1, 500000) i;
ANALYZE i104t;
CREATE INDEX i104 ON i104t (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(104, 'control', 'partial + INCLUDE (text) narrower inside the subset', 'i104', 'skip');

CREATE TABLE i105t AS SELECT (i % 20 = 0) AS hot, i::int AS k, (i % 7)::int AS n,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS pay
  FROM generate_series(1, 500000) i;
ANALYZE i105t;
CREATE INDEX i105 ON i105t (k) INCLUDE (n, pay) WHERE hot;
SELECT plan_add(105, 'control', 'partial + INCLUDE (int, text), mixed non-key widths', 'i105', 'skip');

-- ===================================================== tests 107-112 ========
-- 106 is retired by the shared definition: its recipe ended on a VACUUM with
-- no ANALYZE after it.  Its number is not reused.
CREATE TABLE x107t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE x107t;
CREATE INDEX x107 ON x107t (upper(s));
SELECT plan_add(107, 'control', 'the same, with one ANALYZE after the build', 'x107', 'measure');

CREATE TABLE x108t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX x108 ON x108t (upper(s));
SELECT plan_add(108, 'control', 'expression index on a never-analysed table', 'x108', 'skip');

CREATE TABLE x109t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ALTER TABLE x109t ALTER COLUMN s SET STATISTICS 0;
ANALYZE x109t;
CREATE INDEX x109 ON x109t (s);
SELECT plan_add(109, 'control', 'plain index, key column with SET STATISTICS 0', 'x109', 'skip');

CREATE TABLE x110t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE x110t;
CREATE INDEX x110 ON x110t (k, upper(s));
SELECT plan_add(110, 'control', 'mixed key (k, upper(s)), no statistics row', 'x110', 'skip');

CREATE TABLE x111t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE x111t;
CREATE INDEX x111 ON x111t (left(s, 3));
SELECT plan_add(111, 'control', 'narrow expression left(s, 3), no statistics row', 'x111', 'skip');

CREATE TABLE x112t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE x112t;
CREATE INDEX x112 ON x112t (upper(s)) WHERE hot;
SELECT plan_add(112, 'control', 'partial expression index, no statistics row', 'x112', 'skip');

-- ===================================================== tests 113-120 ========
-- Legs 113a and 113c, and numbers 117 and 121, are retired by the shared
-- definition: 113a and 117 drained an index without vacuuming it, 113c and
-- 121 left the count a VACUUM or a TRUNCATE wrote with no ANALYZE after it.
-- Only leg 113b remains, and the retired numbers are not reused.
CREATE TABLE q113b AS SELECT i::int AS id, 'pending'::text AS state
  FROM generate_series(1, 1000000) i;
ANALYZE q113b;
CREATE INDEX p113b ON q113b (id) WHERE state = 'pending';
SELECT plan_add(113, 'zero', 'drained queue, VACUUM + ANALYZE', 'p113b', 'skip', 'b');

CREATE TABLE q114 AS SELECT i::int AS id, 'pending'::text AS state
  FROM generate_series(1, 1000000) i;
ANALYZE q114;
CREATE INDEX p114 ON q114 (id) WHERE state = 'pending';
SELECT plan_add(114, 'zero', 'queue drained to 1%, VACUUM + ANALYZE', 'p114', 'skip');

CREATE TABLE q115(id int, state text);
ANALYZE q115;
CREATE INDEX p115 ON q115 (id) WHERE state = 'pending';
SELECT plan_add(115, 'zero', 'index built on an analysed empty table, then loaded', 'p115', 'measure');

CREATE TABLE q116 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p116 ON q116 (id) WHERE state = 'pending';
ANALYZE q116;
SELECT plan_add(116, 'zero', 'subset empty from the start and measured empty', 'p116', 'skip');

CREATE TABLE q118 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p118 ON q118 (id) WHERE state = 'pending';
ANALYZE q118;
SELECT plan_add(118, 'zero', 'subset measured empty, then 50,000 rows arrive', 'p118', 'skip');

CREATE TABLE q119 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p119 ON q119 (id) WHERE state = 'pending';
ANALYZE q119;
SELECT plan_add(119, 'zero', 'fixture 118 after one ANALYZE', 'p119', 'skip');

CREATE TABLE q120 AS SELECT i::int AS id,
       CASE WHEN i <= 2000 THEN 'pending' ELSE 'done' END::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p120 ON q120 (id) WHERE state = 'pending';
SET default_statistics_target = 1;
ANALYZE q120;
RESET default_statistics_target;
SELECT plan_add(120, 'zero', 'a 300-row sample missed a 2,000-row subset', 'p120', 'skip');

SELECT count(*) AS planned_fixtures FROM plan;
FIXTURES_BUILD
  cat > "$SQLD/fixtures_v13.sql" <<'FIXTURES_V13'
-- Build phase, every fixture that needs a feature PostgreSQL 12 does not have.
-- One family is left: B-tree support function 4, the deduplication
-- equal-image callback.  A 12 server refuses "FUNCTION 4" in CREATE OPERATOR
-- CLASS outright, and has no btequalimage or btvarstrequalimage to alias, so
-- tests 13, 14, 15 and 16 are skipped there.
--
-- The deduplicate_items fixtures that used to share this file, test 11 and
-- test 38, are retired by the shared definition: explicitly enabling or
-- disabling deduplication is outside the mandatory suite.  Their numbers are
-- not reused, and the reloption is now probed by stage_facts only.
--
-- This file runs only where server_version_num >= 130000; otherwise the
-- fixtures are recorded as skipped and the suite is scored without them.
-- Disposable fixtures, in the sandbox cluster's suite database only.
SET /* wiki_btmaint_v13_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_v13_statement_timeout */ statement_timeout = '900s';
SET /* wiki_btmaint_v13_lock_timeout */ lock_timeout = '5s';
SET /* wiki_btmaint_v13_maintenance_work_mem */ maintenance_work_mem = '256MB';

CREATE OR REPLACE FUNCTION ei_true(oid)  RETURNS bool LANGUAGE sql IMMUTABLE AS $$ SELECT true $$;
CREATE OR REPLACE FUNCTION ei_false(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS $$ SELECT false $$;
CREATE OR REPLACE FUNCTION ei_alias(oid) RETURNS bool LANGUAGE internal IMMUTABLE AS 'btequalimage';
CREATE OR REPLACE FUNCTION ei_renamed(oid) RETURNS bool LANGUAGE internal IMMUTABLE AS 'btvarstrequalimage';
-- test 16, the impostor: a SQL function wearing the built-in's name.  It must
-- be schema-qualified in the operator class or pg_catalog wins the lookup.
CREATE OR REPLACE FUNCTION public.btequalimage(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS $$ SELECT true $$;

CREATE OPERATOR CLASS int4_ei_true FOR TYPE int4 USING btree AS
  OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
  OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
  FUNCTION 1 btint4cmp(int4,int4), FUNCTION 4 ei_true(oid);
CREATE OPERATOR CLASS int4_ei_false FOR TYPE int4 USING btree AS
  OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
  OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
  FUNCTION 1 btint4cmp(int4,int4), FUNCTION 4 ei_false(oid);
CREATE OPERATOR CLASS int4_ei_alias FOR TYPE int4 USING btree AS
  OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
  OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
  FUNCTION 1 btint4cmp(int4,int4), FUNCTION 4 ei_alias(oid);
CREATE OPERATOR CLASS int8_ei_true FOR TYPE int8 USING btree AS
  OPERATOR 1 <(int8,int8), OPERATOR 2 <=(int8,int8), OPERATOR 3 =(int8,int8),
  OPERATOR 4 >=(int8,int8), OPERATOR 5 >(int8,int8),
  FUNCTION 1 btint8cmp(int8,int8), FUNCTION 4 ei_true(oid);
CREATE OPERATOR CLASS int8_ei_false FOR TYPE int8 USING btree AS
  OPERATOR 1 <(int8,int8), OPERATOR 2 <=(int8,int8), OPERATOR 3 =(int8,int8),
  OPERATOR 4 >=(int8,int8), OPERATOR 5 >(int8,int8),
  FUNCTION 1 btint8cmp(int8,int8), FUNCTION 4 ei_false(oid);
CREATE OPERATOR CLASS text_squat FOR TYPE text USING btree AS
  OPERATOR 1 <(text,text), OPERATOR 2 <=(text,text), OPERATOR 3 =(text,text),
  OPERATOR 4 >=(text,text), OPERATOR 5 >(text,text),
  FUNCTION 1 bttextcmp(text,text), FUNCTION 4 public.btequalimage(oid);
CREATE OPERATOR CLASS text_renamed FOR TYPE text USING btree AS
  OPERATOR 1 <(text,text), OPERATOR 2 <=(text,text), OPERATOR 3 =(text,text),
  OPERATOR 4 >=(text,text), OPERATOR 5 >(text,text),
  FUNCTION 1 bttextcmp(text,text), FUNCTION 4 ei_renamed(oid);

CREATE INDEX i_ei_false  ON t (a int4_ei_false);
CREATE INDEX i_ei_true   ON t (a int4_ei_true);
CREATE INDEX i_ei_alias  ON t (a int4_ei_alias);
CREATE INDEX i_mixed_tf  ON t (a int4_ei_true, b int8_ei_false);
CREATE INDEX i_mixed_ft  ON t (a int4_ei_false, b int8_ei_true);
CREATE INDEX i_squat     ON t (s text_squat);
CREATE INDEX i_text_det2 ON t (s text_renamed);
CREATE INDEX i2_tf       ON t2 (a int4_ei_true, b int8_ei_false);
CREATE INDEX i2_ft       ON t2 (a int4_ei_false, b int8_ei_true);
SELECT plan_add(13, 'gate', 'support function 4 returns false', 'i_ei_false', 'measure', 'i_ei_false');
SELECT plan_add(14, 'gate', 'support function 4 returns true by design', 'i_ei_true', 'measure', 'i_ei_true');
SELECT plan_add(14, 'gate', 'internal alias of btequalimage', 'i_ei_alias', 'measure', 'i_ei_alias');
SELECT plan_add(15, 'gate', 'mixed true/false support functions', 'i_mixed_tf', 'measure', 'i_mixed_tf');
SELECT plan_add(15, 'gate', 'mixed false/true support functions', 'i_mixed_ft', 'measure', 'i_mixed_ft');
SELECT plan_add(16, 'gate', 'SQL impostor named btequalimage', 'i_squat', 'measure', 'i_squat');
SELECT plan_add(16, 'gate', 'renamed internal support function 4', 'i_text_det2', 'measure', 'i_text_det2');
SELECT plan_add(15, 'gate', 'second table, mixed true/false', 'i2_tf', 'measure', 'i2_tf');
SELECT plan_add(15, 'gate', 'second table, mixed false/true', 'i2_ft', 'measure', 'i2_ft');
FIXTURES_V13
  cat > "$SQLD/fixtures_icu.sql" <<'FIXTURES_ICU'
-- Build phase, the four ICU fixtures: tests 3, 4, 9 and 51-52.  A server built
-- --without-icu cannot create these collations, so this file runs only where
-- CREATE COLLATION (provider = icu) succeeds and the fixtures are otherwise
-- recorded as skipped.
-- Disposable fixtures, in the sandbox cluster's suite database only.
SET /* wiki_btmaint_icu_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_icu_statement_timeout */ statement_timeout = '900s';
SET /* wiki_btmaint_icu_lock_timeout */ lock_timeout = '5s';

CREATE COLLATION ci   (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
CREATE COLLATION cdet (provider = icu, locale = 'und');

CREATE INDEX i_text_icu_det  ON t (s COLLATE cdet);
CREATE INDEX i_text_nondet   ON t (s COLLATE ci);
CREATE INDEX i_expr_lower_ci ON t ((lower(s)) COLLATE ci);
SELECT plan_add(3, 'gate', 'text key, deterministic ICU collation', 'i_text_icu_det', 'measure', 'i_text_icu_det');
SELECT plan_add(4, 'gate', 'text key, nondeterministic ICU collation', 'i_text_nondet', 'measure', 'i_text_nondet');
SELECT plan_add(9, 'gate', 'expression key under a nondeterministic collation', 'i_expr_lower_ci', 'measure', 'i_expr_lower_ci');

CREATE COLLATION suite_det    (provider = icu, locale = 'und');
CREATE COLLATION suite_nondet (provider = icu, locale = 'und-u-ks-level2',
                               deterministic = false);
CREATE TABLE pc51 AS SELECT (i % 5 = 0) AS hot,
       'key' || lpad(((i / 5) % 100)::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE pc51;
CREATE INDEX p51 ON pc51 (s COLLATE suite_det) WHERE hot;
CREATE INDEX p52 ON pc51 (s COLLATE suite_nondet) WHERE hot;
SELECT plan_add(51, 'partial', 'deterministic ICU collation', 'p51', 'measure');
SELECT plan_add(52, 'partial', 'nondeterministic ICU collation', 'p52', 'measure');
FIXTURES_ICU
  cat > "$SQLD/fixtures_churn.sql" <<'FIXTURES_CHURN'
-- The numbered suite, churn phase: everything each recipe does after its index
-- exists, run after the heuristic has stored an as-built baseline in every
-- index comment.  Two kinds of churn:
--
--   1. the recipe's own, transcribed verbatim from the numbered fixtures;
--   2. a uniform 90 % block drain for the shape fixtures that have no churn of
--      their own, because a fixture designed for a one-shot estimator never
--      needed a "before" and an "after".
--
-- The fixtures whose whole point is that a fresh index must not be touched are
-- deliberately left alone: 70-71, 78-85, 96-97, 101-105, 108-112, 116 and 120.
--
-- The maintenance the assumption credits is NOT here: the drain below deletes
-- and stops, and every churned table is vacuumed and analyzed by the
-- maintenance step that follows this file, in a session whose timeouts are all
-- zero and whose VERBOSE output is captured.  A recipe's own VACUUM or ANALYZE
-- stays where the numbered fixture put it, because that is the recipe.
--
-- All four settable timeouts are zero for the same reason the autovacuum
-- launcher and worker set them to zero on themselves: this file issues
-- maintenance statements, and a timeout firing inside one would leave a
-- fixture neither churned nor maintained, which the shared definition's
-- no-defeat rule forbids.  The trade-off is that a runaway statement here has
-- no guard but the run's own supervision.
--
-- Disposable fixtures, in the sandbox cluster's suite database only.
SET /* wiki_btmaint_churn_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_churn_statement_timeout */ statement_timeout = 0;
SET /* wiki_btmaint_churn_lock_timeout */ lock_timeout = 0;
SET /* wiki_btmaint_churn_transaction_timeout */ transaction_timeout = 0;
SET /* wiki_btmaint_churn_idle_timeout */ idle_in_transaction_session_timeout = 0;

-- ---------------------------------------------------------- recipe churn ----
-- 64: stale statistics after inserts into the subset.
INSERT INTO pc64 SELECT true, 500000 + i FROM generate_series(1, 200000) i;

-- 66: rows entering the index (false -> true).
UPDATE pc66 SET hot = true WHERE NOT hot AND k % 5 = 1;

-- 68: heavy predicate churn, then VACUUM + ANALYZE.
UPDATE pc68 SET hot = true  WHERE k % 3 = 0;
UPDATE pc68 SET hot = false WHERE k % 3 = 0;
UPDATE pc68 SET hot = true  WHERE k % 3 = 1;
UPDATE pc68 SET hot = false WHERE k % 3 = 1;
UPDATE pc68 SET hot = (k % 10 = 0);
VACUUM pc68;
ANALYZE pc68;

-- 71: a REINDEX nobody told the heuristic about.
REINDEX INDEX p71;

-- 72-75: a quarter, a half, three quarters and nine tenths of the subset.
DELETE FROM pb72 WHERE hot AND (k / 5) % 4 = 0;
VACUUM pb72;
ANALYZE pb72;
DELETE FROM pb73 WHERE hot AND (k / 5) % 2 = 0;
VACUUM pb73;
ANALYZE pb73;
DELETE FROM pb74 WHERE hot AND (k / 5) % 4 <> 0;
VACUUM pb74;
ANALYZE pb74;
DELETE FROM pb75 WHERE hot AND (k / 5) % 10 <> 0;
VACUUM pb75;
ANALYZE pb75;

-- 76: bloated through indexed-key UPDATEs.
UPDATE pb76 SET k = k + 1000000 WHERE hot;
VACUUM pb76;
ANALYZE pb76;

-- 77: many empty and deleted B-tree pages, contiguous 95 %.
DELETE FROM pb77 WHERE hot AND k < 475000;
VACUUM pb77;
ANALYZE pb77;

-- 84's forged partial-index reltuples has moved to forge.sql, which runs after
-- the simulated auto-analyze, because an ANALYZE of its table would overwrite
-- the forgery and the fixture would stop testing anything.

-- 86-91: genuinely bloated, VACUUMed and ANALYZEd.
DELETE FROM f86t WHERE hot AND k >= 25;
VACUUM f86t;
ANALYZE f86t;
DELETE FROM f87t WHERE hot AND k IS NOT NULL;
VACUUM f87t;
ANALYZE f87t;
DELETE FROM f88t WHERE hot AND s > lpad('4', 9, '0');
VACUUM f88t;
ANALYZE f88t;
DELETE FROM f89t WHERE hot AND a >= 25;
VACUUM f89t;
ANALYZE f89t;
DELETE FROM f90t WHERE hot AND k >= 250;
VACUUM f90t;
ANALYZE f90t;
DELETE FROM f91t WHERE hot AND ord < 190000;
VACUUM f91t;
ANALYZE f91t;

-- 92-95: a reclaimable partial index, then a known number of row changes.
DELETE FROM b92t WHERE hot AND (k / 5) % 10 <> 0;
VACUUM b92t;
ANALYZE b92t;
UPDATE b92t SET k = k WHERE k % 500 = 0;
DELETE FROM b93t WHERE hot AND (k / 5) % 10 <> 0;
VACUUM b93t;
ANALYZE b93t;
UPDATE b93t SET k = k WHERE k % 2 = 0;
DELETE FROM b94t WHERE hot AND (k / 5) % 10 <> 0;
VACUUM b94t;
ANALYZE b94t;
UPDATE b94t SET k = k WHERE k % 500 = 0;
DELETE FROM b95t WHERE hot AND (k / 5) % 10 <> 0;
VACUUM b95t;
ANALYZE b95t;
UPDATE b95t SET k = k WHERE k % 2 = 0;

-- 98: 300,000 inserts and no ANALYZE.
INSERT INTO np98t SELECT 500000 + i FROM generate_series(1, 300000) i;

-- 99: duplicate-heavy, genuinely reclaimable.
DELETE FROM np99t WHERE k >= 60;
VACUUM np99t;
ANALYZE np99t;

-- 100: partial + INCLUDE, 90 % of the subset deleted.
DELETE FROM i100t WHERE hot AND (k / 5) % 10 <> 0;
VACUUM i100t;
ANALYZE i100t;

-- 107: an expression index, 90 % deleted, then VACUUM and ANALYZE.
DELETE FROM x107t WHERE k % 10 <> 0;
VACUUM x107t;
ANALYZE x107t;

-- 113b: the drained queue, vacuumed and analyzed.  Legs a and c are retired.
UPDATE q113b SET state = 'done';
VACUUM q113b;
ANALYZE q113b;

-- 114: drained to 1 %.
UPDATE q114 SET state = 'done' WHERE id % 100 <> 0;
VACUUM q114;
ANALYZE q114;

-- 115: an index built on an analysed empty table, then loaded.
INSERT INTO q115 SELECT i, 'pending' FROM generate_series(1, 1000000) i;

-- 118, 119: the subset was empty at the last ANALYZE, then rows arrived.
INSERT INTO q118 SELECT 1000000 + i, 'pending' FROM generate_series(1, 50000) i;
INSERT INTO q119 SELECT 1000000 + i, 'pending' FROM generate_series(1, 50000) i;
ANALYZE q119;

-- ------------------------------------------------------- the uniform drain ---
-- 90 % of the heap blocks of every shape fixture that has no churn of its own.
-- The maintenance VACUUM and ANALYZE that turn those dead entries into empty
-- and deleted index pages are no longer here: they are the maintenance step
-- that runs after this file, over every table these deletes touched, with its
-- timeouts at zero and its VERBOSE output recorded.  The deletes are still
-- generated and executed one statement at a time, because the drain predicate
-- has to be applied per table.
SELECT /* wiki_btmaint_drain_generator */ format(st.tmpl, tb.name)
  FROM (VALUES (1, 't'), (2, 't2'), (3, 'pt1'), (4, 'pd22'), (5, 'pd23'),
               (6, 'pd24'), (7, 'pd25'), (8, 'pd26'), (9, 'pd27'), (10, 'pd28'),
               (11, 'pd29'), (12, 'pd30'), (13, 'pd31'), (14, 'pw32'),
               (15, 'pd33'), (16, 'pd34'), (17, 'pd35'), (18, 'pd36'),
               (19, 'pd37'), (20, 'pd39'), (21, 'pd40'), (22, 'pd41'),
               (23, 'pd42'), (24, 'pd43'), (25, 'pd44a'), (26, 'pd44b'),
               (27, 'pd45'), (28, 'pd46'), (29, 'pi47'), (30, 'pe48'),
               (31, 'pe48b'), (32, 'pe49'), (33, 'pe49b'), (34, 'pe50'),
               (35, 'pe50b'), (36, 'pf'), (37, 'ps')) tb(n, name)
 CROSS JOIN (VALUES
        (1, 'DELETE /* wiki_btmaint_drain */ FROM %I WHERE ((ctid::text::point)[0])::int %% 10 <> 0')) st(k, tmpl)
 ORDER BY tb.n, st.k
\gexec
FIXTURES_CHURN
  cat > "$SQLD/churn_icu.sql" <<'CHURN_ICU'
-- Churn phase for the ICU fixtures, drained like the other shape fixtures.
-- The maintenance VACUUM ANALYZE is the maintenance step's, not this file's.
-- Disposable, suite database of the sandbox cluster only.
SET /* wiki_btmaint_churnicu_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_churnicu_statement_timeout */ statement_timeout = 0;
SET /* wiki_btmaint_churnicu_lock_timeout */ lock_timeout = 0;
SELECT /* wiki_btmaint_drainicu_generator */ format(st.tmpl, tb.name)
  FROM (VALUES (1, 'pc51')) tb(n, name)
 CROSS JOIN (VALUES
        (1, 'DELETE /* wiki_btmaint_drain */ FROM %I WHERE ((ctid::text::point)[0])::int %% 10 <> 0')) st(k, tmpl)
 ORDER BY tb.n, st.k
\gexec
CHURN_ICU
  cat > "$SQLD/churn_seen.sql" <<'CHURN_SEEN'
-- Every fixture table's write counters at one point in the run, recorded once
-- before the first churn statement and once after the last.  Run with
-- -v phase=before and -v phase=after.  The difference is what defines "the
-- tables the churn touched", which is the set the maintenance assumption
-- applies to; using the engine's own counters keeps the set out of a
-- hand-written list that a new fixture could silently fall out of.
SET /* wiki_btmaint_churnseen_client_min_messages */ client_min_messages = warning;
DELETE FROM churn_seen WHERE phase = :'phase';
INSERT /* wiki_btmaint_churn_seen */ INTO churn_seen(phase, tbl, ins, upd, del,
                                                    mods, dead, last_analyze)
SELECT :'phase', c.relname, st.n_tup_ins, st.n_tup_upd, st.n_tup_del,
       st.n_mod_since_analyze, st.n_dead_tup, st.last_analyze
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
 WHERE st.schemaname = 'public'
   AND c.relkind = 'r'
   AND c.relname NOT IN ('plan', 'snap', 'truth', 'autoanl', 'autoanl_after',
                         'churn_seen', 'maint', 'horizon', 'pageclass',
                         'precond');
SELECT /* wiki_btmaint_churn_seen_count */
       :'phase' || ': ' || count(*) || ' tables recorded'
  FROM churn_seen WHERE phase = :'phase';
CHURN_SEEN
  cat > "$SQLD/maint.sql" <<'MAINT'
-- The maintenance step: the VACUUM ANALYZE the shared definition's maintenance
-- assumption requires after every churn, on every table the churn touched, and
-- the four proofs its no-defeat rule asks for.
--
-- The table set is computed, not listed: a table is maintained when its
-- insert, update or delete counter moved across the churn phase.  A fixture
-- with no churn is therefore not touched here, which matters - an extra
-- ANALYZE would repair the deliberately stale statistics of family 3 and of
-- controls 108 to 112, and an extra VACUUM would change a deliberately fresh
-- index.  Those fixtures carry their build-phase ANALYZE into the decide phase
-- instead, exactly as the shared definition says they do.
--
-- All four settable timeouts are zero, which is what the autovacuum launcher
-- and worker do to themselves so that these settings cannot stop regular
-- maintenance.  The values in force are recorded per row rather than assumed.
-- VERBOSE is on so that each statement's own "dead but not yet removable"
-- count is in the output; INFO messages reach the client whatever
-- client_min_messages says.
-- Disposable fixtures, suite database of the sandbox cluster only.
SET /* wiki_btmaint_maint_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_maint_statement_timeout */ statement_timeout = 0;
SET /* wiki_btmaint_maint_lock_timeout */ lock_timeout = 0;
SET /* wiki_btmaint_maint_transaction_timeout */ transaction_timeout = 0;
SET /* wiki_btmaint_maint_idle_timeout */ idle_in_transaction_session_timeout = 0;

DELETE FROM maint;
INSERT /* wiki_btmaint_maint_rows */ INTO maint
       (tbl, ord, ins, upd, del, mods_before, dead_before, analyzed_in_churn,
        timeouts)
SELECT a.tbl,
       row_number() OVER (ORDER BY a.tbl)::int,
       a.ins - b.ins, a.upd - b.upd, a.del - b.del, a.mods, a.dead,
       -- A recipe that analyzed its own table after its own writes leaves the
       -- modification counter at zero legitimately: the churn was published
       -- and then consumed.  Recording which tables those are is what keeps a
       -- zero counter from being read as a churn that never reached the
       -- statistics entry at all.
       (a.last_analyze IS NOT NULL
        AND (b.last_analyze IS NULL OR a.last_analyze > b.last_analyze)),
       'statement_timeout=' || current_setting('statement_timeout') ||
       ' lock_timeout=' || current_setting('lock_timeout') ||
       ' transaction_timeout=' || current_setting('transaction_timeout') ||
       ' idle_in_transaction_session_timeout='
         || current_setting('idle_in_transaction_session_timeout')
  FROM churn_seen a
  JOIN churn_seen b ON b.tbl = a.tbl AND b.phase = 'before'
 WHERE a.phase = 'after'
   AND (a.ins - b.ins) + (a.upd - b.upd) + (a.del - b.del) > 0;

SELECT /* wiki_btmaint_maint_planned */ count(*) || ' tables to maintain, '
       || count(*) FILTER (WHERE analyzed_in_churn)
       || ' already analyzed by their own recipe, '
       || count(*) FILTER (WHERE COALESCE(mods_before, 0) = 0
                             AND NOT analyzed_in_churn)
       || ' with an unpublished churn counter'
  FROM maint;

-- One probe, one start stamp, one VACUUM (VERBOSE, ANALYZE) and one end stamp
-- per table, generated and executed one statement at a time because VACUUM
-- cannot run inside a transaction block.
SELECT /* wiki_btmaint_maint_generator */ format(st.tmpl, m.tbl)
  FROM maint m
 CROSS JOIN (VALUES
        (1, 'SELECT /* wiki_btmaint_horizon_before */ horizon_probe(''maint'', %1$L)'),
        (2, 'UPDATE /* wiki_btmaint_maint_start */ maint SET started = clock_timestamp() WHERE tbl = %1$L'),
        (3, 'VACUUM /* wiki_btmaint_maint */ (VERBOSE, ANALYZE) %1$I'),
        (4, 'UPDATE /* wiki_btmaint_maint_end */ maint SET ended = clock_timestamp() WHERE tbl = %1$L')
       ) st(k, tmpl)
 ORDER BY m.ord, st.k
\gexec
MAINT
  cat > "$SQLD/maint_after.sql" <<'MAINT_AFTER'
-- What the maintenance left behind, read from a new session a second later so
-- that a 12 server's statistics collector has published the VACUUM and the
-- ANALYZE.  dead_after is the dead-tuple count the engine reports for the
-- table; mods_after is the modification counter the ANALYZE half reset.
SET /* wiki_btmaint_maintafter_client_min_messages */ client_min_messages = warning;
UPDATE /* wiki_btmaint_maint_after */ maint m
   SET mods_after = st.n_mod_since_analyze,
       dead_after = st.n_dead_tup
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
 WHERE st.schemaname = 'public' AND c.relname = m.tbl;
SELECT /* wiki_btmaint_horizon_after_maint */ horizon_probe('post-maint', NULL);
SELECT /* wiki_btmaint_maint_summary */
       'maintained ' || count(*) || ' tables, '
       || count(*) FILTER (WHERE ended IS NOT NULL) || ' completed, '
       || count(*) FILTER (WHERE COALESCE(dead_after, 0) > 0)
       || ' still holding dead tuples, '
       || count(*) FILTER (WHERE COALESCE(mods_after, 0) > 0)
       || ' with a non-zero modification counter'
  FROM maint;
MAINT_AFTER
  cat > "$SQLD/precond.sql" <<'PRECOND'
-- The preconditions the shared definition puts on a numbered fixture, checked
-- after the census rather than assumed.  Test 120 is the suite's one
-- probabilistic fixture: its point is a 300-row sample that missed a 2,000-row
-- subset, so its partial index's own reltuples must still read 0 when the
-- method is asked.  A run that finds a non-zero estimate scores nothing from
-- the fixture, which is what the shared definition says, and what the previous
-- run of this page counted as a PASS.
SET /* wiki_btmaint_precond_client_min_messages */ client_min_messages = warning;
DELETE FROM precond;
INSERT /* wiki_btmaint_precond_120 */ INTO precond(num, leg, requirement, observed, met)
SELECT 120, '', 'post-census reltuples of p120 must be 0',
       'p120 reltuples = ' || c.reltuples::text, (c.reltuples = 0)
  FROM pg_class c WHERE c.relname = 'p120';
SELECT /* wiki_btmaint_precond_report */
       num || ': ' || requirement || ' -> ' || observed ||
       ' (' || CASE WHEN met THEN 'met' ELSE 'NOT MET, scores nothing' END || ')'
  FROM precond ORDER BY num, leg;
PRECOND
  cat > "$SQLD/pageclass.sql" <<'PAGECLASS'
-- The page classes of every fixture index after the maintenance step.  Deleted
-- and half-dead pages are the visible trace of what the maintenance did, and a
-- drained fixture whose index has neither is the shape a defeated VACUUM
-- leaves behind.  Read-only: pgstatindex opens every page of every index it is
-- called on and writes nothing, so the decide phase that follows sees exactly
-- the state the maintenance left.
SET /* wiki_btmaint_pageclass_client_min_messages */ client_min_messages = warning;
DELETE FROM pageclass;
INSERT /* wiki_btmaint_pageclass */ INTO pageclass
       (idx, leaf_pages, empty_pages, deleted_pages, avg_leaf_density, index_size)
SELECT p.idx, m.leaf_pages, m.empty_pages, m.deleted_pages,
       CASE WHEN m.avg_leaf_density = 'NaN'::float8 THEN NULL
            ELSE round(m.avg_leaf_density::numeric, 2) END,
       m.index_size
  FROM plan p, LATERAL pgstatindex(p.idx::regclass) m;
SELECT /* wiki_btmaint_pageclass_report */
       count(*) || ' indexes read, '
       || count(*) FILTER (WHERE deleted_pages > 0) || ' with deleted pages, '
       || count(*) FILTER (WHERE empty_pages > 0) || ' with half-dead pages, '
       || COALESCE(sum(deleted_pages), 0) || ' deleted pages in total'
  FROM pageclass;
PAGECLASS
  cat > "$SQLD/autoanalyze.sql" <<'AUTOANALYZE'
-- The simulated auto-analyze, and the mandatory-test rule behind it: a fixture
-- that changes more than 10 % of a table's heap tuples must ANALYZE it, because
-- on a server with autovacuum on the launcher would have.
--
-- The trigger is not hand-written per fixture.  It is the engine's own test,
-- n_mod_since_analyze > autovacuum_analyze_threshold +
-- autovacuum_analyze_scale_factor * reltuples, which is exactly what
-- relation_needs_vacanalyze() compares; at the defaults that is 50 + 10 % of
-- the table's estimated row count.  autovacuum is off in this cluster, so no
-- background worker can have analyzed anything, and every ANALYZE below is one
-- this fixture set asked for.
--
-- Both counter states are recorded: autoanl holds what the churn left behind,
-- autoanl_after holds the same counters once the ANALYZEs have run, which is
-- how the run proves the simulation actually fired.
--
-- With the maintenance step in front of it, this census finds every churned
-- table freshly analyzed, so the tables it decides are the ones no churn
-- touched - a table whose build left it past the threshold, such as the
-- never-analysed table of control 108.  It is also the recheck that the
-- maintenance step's counters were published in the right order.
--
-- The census issues ANALYZE, which is a maintenance command, so its timeouts
-- are zero for the same reason the maintenance step's are, and it probes the
-- horizon on both sides of itself.
-- Disposable fixtures, suite database of the sandbox cluster only.
SET /* wiki_btmaint_autoanl_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_autoanl_statement_timeout */ statement_timeout = 0;
SET /* wiki_btmaint_autoanl_lock_timeout */ lock_timeout = 0;
SET /* wiki_btmaint_autoanl_transaction_timeout */ transaction_timeout = 0;
SET /* wiki_btmaint_autoanl_idle_timeout */ idle_in_transaction_session_timeout = 0;

SELECT /* wiki_btmaint_horizon_before_census */ horizon_probe('census-before', NULL);

DROP TABLE IF EXISTS autoanl;
DROP TABLE IF EXISTS autoanl_after;
CREATE TABLE autoanl AS
SELECT /* wiki_btmaint_autoanalyze_census */
       c.relname                                   AS tbl,
       GREATEST(c.reltuples, 0)::numeric           AS reltuples,
       st.n_mod_since_analyze::numeric             AS mods,
       round(current_setting('autovacuum_analyze_threshold')::numeric
             + current_setting('autovacuum_analyze_scale_factor')::numeric
               * GREATEST(c.reltuples, 0)::numeric, 1) AS threshold,
       round(100 * st.n_mod_since_analyze
             / GREATEST(c.reltuples, 1)::numeric, 1)   AS mod_pct,
       (st.n_mod_since_analyze
        > current_setting('autovacuum_analyze_threshold')::numeric
          + current_setting('autovacuum_analyze_scale_factor')::numeric
            * GREATEST(c.reltuples, 0)::numeric)       AS would_autoanalyze
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
 WHERE st.schemaname = 'public'
   AND c.relkind = 'r'
   AND c.relname NOT IN ('plan', 'snap', 'truth', 'autoanl', 'autoanl_after',
                         'churn_seen', 'maint', 'horizon', 'pageclass',
                         'precond');

SELECT /* wiki_btmaint_autoanalyze_generator */
       format('ANALYZE /* wiki_btmaint_autoanalyze */ %I', tbl)
  FROM autoanl WHERE would_autoanalyze ORDER BY tbl
\gexec

AUTOANALYZE
  cat > "$SQLD/autoanalyze_after.sql" <<'AUTOANALYZE_AFTER'
-- The census's own recheck, in a session of its own a second later.  The delay
-- is not cosmetic: this file has to be able to see the counters the census's
-- ANALYZEs reset, and on a 12 server the statistics a reader sees come from a
-- collector file that is written at most every half second, so a recheck run
-- immediately after the ANALYZE reads the state from before it.  A run that
-- reports "0 of 6 counters reset" is reporting that staleness, not a census
-- that did nothing.
SET /* wiki_btmaint_autoanlafter_client_min_messages */ client_min_messages = warning;
DROP TABLE IF EXISTS autoanl_after;
CREATE TABLE autoanl_after AS
SELECT /* wiki_btmaint_autoanalyze_recheck */
       c.relname AS tbl, st.n_mod_since_analyze::numeric AS mods,
       GREATEST(c.reltuples, 0)::numeric AS reltuples
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
 WHERE st.schemaname = 'public' AND c.relkind = 'r'
   AND c.relname IN (SELECT tbl FROM autoanl WHERE would_autoanalyze);

SELECT /* wiki_btmaint_horizon_after_census */ horizon_probe('census-after', NULL);
AUTOANALYZE_AFTER
  cat > "$SQLD/forge.sql" <<'FORGE'
-- The numbered suite's catalog forgeries, applied after the simulated
-- auto-analyze so that an ANALYZE cannot overwrite them.  Fixture 84 is a
-- partial index whose recorded entry count is deliberately wrong, which is now
-- an input the heuristic reads rather than one it ignores.
-- Disposable catalog forgery, suite database of the sandbox cluster only.
SET /* wiki_btmaint_forge_client_min_messages */ client_min_messages = warning;
UPDATE /* wiki_btmaint_forge_84 */ pg_class SET reltuples = 5000
 WHERE relname = 'f84';
SELECT /* wiki_btmaint_forge_check */ 'f84 reltuples now ' || reltuples
  FROM pg_class WHERE relname = 'f84';
FORGE
  note "$(ls -1 "$SQLD" | tr "\n" " ")"
}

# ---------------------------------------------------------------- texts ------
stage_texts() {
  say "the page's two texts, hashed, and the one-edit harness view"
  [ -f "$PAGE" ] || die "no page at $PAGE; set PAGE or run from the repository root"
  md_block sql 1 "$PAGE" > "$SQLD/report.sql"
  md_block sql 2 "$PAGE" > "$SQLD/apply.sql"
  [ -s "$SQLD/report.sql" ] || die "block 1 of $PAGE is empty"
  [ -s "$SQLD/apply.sql" ]  || die "block 2 of $PAGE is empty"
  : > "$OUT/hashes.txt"
  local h1 h2
  h1=$(sha256sum < "$SQLD/report.sql" | cut -d' ' -f1)
  h2=$(sha256sum < "$SQLD/apply.sql"  | cut -d' ' -f1)
  printf 'report %s %s\n' "$h1" \
    "$([ "$h1" = "$BASE_REPORT" ] && echo match || echo DIFFERS)" >> "$OUT/hashes.txt"
  printf 'apply  %s %s\n' "$h2" \
    "$([ "$h2" = "$BASE_APPLY" ] && echo match || echo DIFFERS)" >> "$OUT/hashes.txt"
  printf 'report lines=%s bytes=%s\n' "$(grep -c '' "$SQLD/report.sql")" \
    "$(wc -c < "$SQLD/report.sql")" >> "$OUT/hashes.txt"
  printf 'apply  lines=%s bytes=%s\n' "$(grep -c '' "$SQLD/apply.sql")" \
    "$(wc -c < "$SQLD/apply.sql")" >> "$OUT/hashes.txt"
  # The shared pipeline: from "WITH params AS (" through the end of the staged
  # CTE, which is where the two texts part company - step 1 goes on to measure
  # in SQL, step 2 hands the snapshot to its driver.  The page claims this
  # region is byte-identical in both; this is the check that makes the claim
  # auditable.
  sed -n '/^WITH params AS ($/,/^      FROM decided d$/p' \
      "$SQLD/report.sql" > "$OUT/pipeline_report.sql"
  sed -n '/^WITH params AS ($/,/^      FROM decided d$/p' \
      "$SQLD/apply.sql" > "$OUT/pipeline_apply.sql"
  printf 'pipeline report %s\npipeline apply  %s\npipeline lines  %s\n' \
    "$(sha256sum < "$OUT/pipeline_report.sql" | cut -d' ' -f1)" \
    "$(sha256sum < "$OUT/pipeline_apply.sql" | cut -d' ' -f1)" \
    "$(grep -c '' "$OUT/pipeline_report.sql")" >> "$OUT/hashes.txt"
  if cmp -s "$OUT/pipeline_report.sql" "$OUT/pipeline_apply.sql"; then
    printf 'pipeline identical yes\n' >> "$OUT/hashes.txt"
  else
    printf 'pipeline identical NO\n' >> "$OUT/hashes.txt"
    diff "$OUT/pipeline_report.sql" "$OUT/pipeline_apply.sql" > "$OUT/pipeline_diff.txt"
  fi
  plan_view "$SQLD/report.sql" > "$SQLD/plan_view.sql"
  cat "$OUT/hashes.txt" >&2
}

# ---------------------------------------------------------------- facts ------
# Every version-local fact the two texts depend on, discovered on the running
# server rather than assumed.  The 12 leg runs the same stage, which is how the
# two servers are compared.
stage_facts() {
  say "version-local facts"
  : > "$OUT/facts.txt"
  local fact
  fact() { printf '%-34s %s\n' "$1" "$2" >> "$OUT/facts.txt"; }
  fact server_version_num "$(s suite 'SHOW server_version_num')"
  fact block_size "$(s suite 'SHOW block_size')"
  fact materialized_cte_accepted \
    "$(s suite 'WITH x AS MATERIALIZED (SELECT 1) SELECT count(*) FROM x' 2>&1 | tail -1)"
  fact pgstatindex_version \
    "$(s suite "SELECT extversion FROM pg_extension WHERE extname = 'pgstattuple'")"
  fact has_pg_input_is_valid \
    "$(s suite "SELECT count(*) FROM pg_proc WHERE proname = 'pg_input_is_valid'")"
  fact has_force_next_flush \
    "$(s suite "SELECT count(*) FROM pg_proc WHERE proname = 'pg_stat_force_next_flush'")"
  q suite 'DROP TABLE IF EXISTS zz_d' > /dev/null 2>&1
  q suite 'CREATE TABLE zz_d(k int)' > /dev/null
  fact deduplicate_items_reloption \
    "$(errf suite 'CREATE INDEX zz_di ON zz_d (k) WITH (deduplicate_items = off)')"
  q suite 'DROP TABLE IF EXISTS zz_d' > /dev/null 2>&1
  fact maintain_privilege \
    "$(errf suite "SELECT has_table_privilege('pg_class', 'MAINTAIN')")"
  fact icu_collation \
    "$(errf suite "CREATE COLLATION zz_icu (provider = icu, locale = 'und')")"
  q suite 'DROP COLLATION IF EXISTS zz_icu' > /dev/null 2>&1
  # reltuples on a table nothing has counted, and after each writer.
  q suite 'DROP TABLE IF EXISTS zz_rt' > /dev/null 2>&1
  q suite 'CREATE TABLE zz_rt(k int)' > /dev/null
  fact reltuples_after_create "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  q suite 'INSERT INTO zz_rt SELECT i FROM generate_series(1,1000) i' > /dev/null
  fact reltuples_after_insert "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  q suite 'CREATE INDEX zz_rt_k ON zz_rt (k)' > /dev/null
  fact reltuples_after_create_index "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  q suite 'ANALYZE zz_rt' > /dev/null
  fact reltuples_after_analyze "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  q suite 'TRUNCATE zz_rt' > /dev/null
  fact reltuples_after_truncate "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  q suite 'INSERT INTO zz_rt SELECT i FROM generate_series(1,2000) i' > /dev/null
  q suite 'REINDEX INDEX zz_rt_k' > /dev/null
  fact reltuples_after_reindex "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  # The index's own reltuples, which is the third gate input: who writes it,
  # what each writer writes, and what a partial index gets.  A plain index and
  # a partial index on the same 10,000-row table, where the predicate selects
  # exactly one row in five.
  fact autovacuum_analyze_threshold "$(s suite 'SHOW autovacuum_analyze_threshold')"
  fact autovacuum_analyze_scale_factor "$(s suite 'SHOW autovacuum_analyze_scale_factor')"
  q suite 'DROP TABLE IF EXISTS zz_it' > /dev/null 2>&1
  q suite 'CREATE TABLE zz_it AS SELECT i::int AS k, (i % 5 = 0) AS hot
             FROM generate_series(1,10000) i' > /dev/null
  q suite 'CREATE INDEX zz_it_all ON zz_it (k)' > /dev/null
  q suite 'CREATE INDEX zz_it_part ON zz_it (k) WHERE hot' > /dev/null
  local ir
  ir() { s suite "SELECT reltuples FROM pg_class WHERE relname='$1'"; }
  fact idx_reltuples_after_build "plain=$(ir zz_it_all) partial=$(ir zz_it_part)"
  q suite 'ANALYZE zz_it' > /dev/null
  fact idx_reltuples_after_analyze \
    "table=$(ir zz_it) plain=$(ir zz_it_all) partial=$(ir zz_it_part)"
  q suite 'DELETE FROM zz_it WHERE hot AND k % 50 <> 0' > /dev/null
  q suite 'VACUUM zz_it' > /dev/null
  fact idx_reltuples_after_vacuum \
    "table=$(ir zz_it) plain=$(ir zz_it_all) partial=$(ir zz_it_part)"
  q suite 'ANALYZE zz_it' > /dev/null
  fact idx_reltuples_after_analyze2 \
    "table=$(ir zz_it) plain=$(ir zz_it_all) partial=$(ir zz_it_part)"
  # A VACUUM with nothing to delete is cleanup-only, and an index AM that
  # reports an estimated count leaves pg_class alone: the count can therefore
  # be older than the last VACUUM.
  q suite 'UPDATE zz_it SET k = k + 100000 WHERE k % 1000 = 0' > /dev/null
  q suite 'VACUUM zz_it' > /dev/null
  fact idx_reltuples_after_small_vacuum \
    "table=$(ir zz_it) plain=$(ir zz_it_all) partial=$(ir zz_it_part)"
  q suite 'REINDEX INDEX zz_it_part' > /dev/null
  fact idx_reltuples_after_reindex "partial=$(ir zz_it_part)"
  q suite 'DROP TABLE IF EXISTS zz_it' > /dev/null 2>&1
  # Transaction control inside DO, which the apply block needs for its COMMIT,
  # and the two commands that cannot be reached from inside one.
  fact commit_inside_do \
    "$(errf suite 'DO $x$ BEGIN PERFORM 1; COMMIT; END $x$;')"
  fact commit_inside_do_in_xact \
    "$(errf suite 'BEGIN; DO $x$ BEGIN PERFORM 1; COMMIT; END $x$; COMMIT;')"
  fact reindex_plain_inside_do \
    "$(errf suite 'DO $x$ BEGIN EXECUTE $q$REINDEX INDEX zz_rt_k$q$; END $x$;')"
  fact reindex_conc_inside_do \
    "$(errf suite 'DO $x$ BEGIN EXECUTE $q$REINDEX INDEX CONCURRENTLY zz_rt_k$q$; END $x$;')"
  fact reindex_conc_top_level "$(errf suite 'REINDEX INDEX CONCURRENTLY zz_rt_k;')"
  fact vacuum_inside_do \
    "$(errf suite 'DO $x$ BEGIN EXECUTE $q$VACUUM zz_rt$q$; END $x$;')"
  fact comment_expression \
    "$(errf suite "COMMENT ON INDEX zz_rt_k IS 'a' || 'b';")"
  fact comment_literal "$(errf suite "COMMENT ON INDEX zz_rt_k IS 'ab';")"
  q suite 'DROP TABLE IF EXISTS zz_rt' > /dev/null 2>&1
  cat "$OUT/facts.txt" >&2
}

# ----------------------------------------------- the no-defeat proofs --------
# The shared definition's rule "the maintenance must not be defeated" says a
# fixture may not carry a state into its maintenance VACUUM ANALYZE that would
# have stopped a real server's autovacuum from doing the work the assumption
# credits it with, and that a fixture which did is repaired and re-run rather
# than scored.  This function is that rule, enforced: it fails the run instead
# of publishing a number taken under a defeated maintenance.
#
# Four proofs, per maintained table:
#   1. the statement completed, and no skip line in the server log names it;
#   2. its VERBOSE "dead but not yet removable" count is zero;
#   3. no other backend held a transaction or an xmin, no replication slot
#      held one and no prepared transaction existed when it started;
#   4. the index page classes it left behind, recorded for the report.
# The publication check comes with them: a table whose churn counter was still
# unpublished when its ANALYZE ran would have had its churn forgotten.
suite_maint_proofs() {
  local n bad
  n=$(s suite 'SELECT count(*) FROM maint')
  [ "$n" -gt 0 ] || die "the maintenance step maintained no table at all"
  bad=$(s suite 'SELECT count(*) FROM maint WHERE ended IS NULL')
  [ "$bad" = 0 ] || die "$bad maintenance statements did not complete"
  bad=$(s suite 'SELECT count(*) FROM maint WHERE dead_not_removable IS NULL')
  [ "$bad" = 0 ] \
    || { t suite 'SELECT tbl FROM maint WHERE dead_not_removable IS NULL ORDER BY tbl' >&2
         die "$bad maintained tables have no VERBOSE count: proof 2 is missing"; }
  # Membership of the maintained set is itself the publication proof: the set
  # comes from write counters that only a flush can move.  What this check adds
  # is the one case a zero modification counter could otherwise hide - a churn
  # that never reached the statistics entry - by excluding the tables whose own
  # recipe analyzed them after their own writes and consumed the counter.
  bad=$(s suite 'SELECT count(*) FROM maint
                  WHERE COALESCE(mods_before, 0) = 0 AND NOT analyzed_in_churn')
  [ "$bad" = 0 ] \
    || { t suite 'SELECT tbl, ins, upd, del, mods_before, analyzed_in_churn
                    FROM maint
                   WHERE COALESCE(mods_before, 0) = 0 AND NOT analyzed_in_churn
                   ORDER BY tbl' >&2
         die "$bad churned tables reached their ANALYZE with an unpublished counter"; }
  bad=$(s suite 'SELECT count(*) FROM maint WHERE dead_not_removable > 0')
  [ "$bad" = 0 ] \
    || { t suite 'SELECT tbl, removed, remain, dead_not_removable, dead_after
                    FROM maint WHERE dead_not_removable > 0
                   ORDER BY dead_not_removable DESC' >&2
         die "$bad maintained tables kept dead tuples the horizon still covered: the maintenance was defeated, repair the fixture and re-run"; }
  bad=$(s suite 'SELECT count(*) FROM horizon
                  WHERE xmin_holders > 0 OR open_xacts > 0
                     OR slots > 0 OR prepared > 0')
  [ "$bad" = 0 ] \
    || { t suite 'SELECT step, tbl, xmin_holders, open_xacts, slots, prepared, detail
                    FROM horizon
                   WHERE xmin_holders > 0 OR open_xacts > 0
                      OR slots > 0 OR prepared > 0 ORDER BY at' >&2
         die "$bad horizon probes found a holder: the maintenance ran with a pinned horizon"; }
  { printf 'maintained tables        %s\n' "$n"
    printf 'statements completed     %s\n' \
      "$(s suite 'SELECT count(*) FROM maint WHERE ended IS NOT NULL')"
    printf 'analyzed by own recipe   %s, all with a published churn counter\n' \
      "$(s suite 'SELECT count(*) FROM maint WHERE analyzed_in_churn')"
    printf 'dead but not removable   max %s over %s tables\n' \
      "$(s suite 'SELECT COALESCE(max(dead_not_removable), -1) FROM maint')" "$n"
    printf 'dead tuples left behind  max %s\n' \
      "$(s suite 'SELECT COALESCE(max(dead_after), -1) FROM maint')"
    printf 'tuples removed           %s over %s tables\n' \
      "$(s suite 'SELECT COALESCE(sum(removed), 0) FROM maint')" "$n"
    printf 'horizon probes clean     %s of %s\n' \
      "$(s suite 'SELECT count(*) FROM horizon
                   WHERE xmin_holders = 0 AND open_xacts = 0
                     AND slots = 0 AND prepared = 0')" \
      "$(s suite 'SELECT count(*) FROM horizon')"
    printf 'distinct timeout sets    %s: %s\n' \
      "$(s suite 'SELECT count(DISTINCT timeouts) FROM maint')" \
      "$(s suite 'SELECT DISTINCT timeouts FROM maint')"; } \
    > "$OUT/maint_proofs.txt"
  cat "$OUT/maint_proofs.txt" >&2
}

# ---------------------------------------------------------------- suite ------
# The ported numbered suite, in eleven steps: build, baseline, churn,
# maintenance, auto-analyze, preconditions, forge, page classes, decide, act,
# oracle.  The baseline and act steps run the page's apply block exactly as
# filed.
stage_suite() {
  say "the ported numbered suite: tests 1-17, 18-91 and controls 92-120"
  q suite 'DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public' > /dev/null
  q suite 'CREATE EXTENSION IF NOT EXISTS pgstattuple' > /dev/null
  f suite "$SQLD/harness.sql"        || die "harness failed"
  f suite "$SQLD/fixtures_build.sql" > "$OUT/suite_build.log" 2>&1 \
    || { tail -5 "$OUT/suite_build.log" >&2; die "build fixtures failed"; }
  local have13=no haveicu=no
  if [ "$(s suite 'SHOW server_version_num')" -ge 130000 ]; then
    f suite "$SQLD/fixtures_v13.sql" >> "$OUT/suite_build.log" 2>&1 \
      && have13=yes || note "v13 fixtures failed, skipped"
  else
    note "server is older than 13: the support function 4 fixtures are skipped"
  fi
  if f suite "$SQLD/fixtures_icu.sql" >> "$OUT/suite_build.log" 2>&1; then
    haveicu=yes
  else
    note "no ICU in this build: the five ICU fixtures are skipped"
  fi
  printf 'v13_fixtures=%s icu_fixtures=%s\n' "$have13" "$haveicu" > "$OUT/suite_groups.txt"
  note "$(s suite 'SELECT count(*) || $$ planned fixtures$$ FROM plan')"

  q suite 'CALL take_snap($$built$$)' || die "snapshot built failed"
  say "baseline: the filed apply block, first run"
  f suite "$SQLD/apply.sql" > "$OUT/apply_init.log" 2>&1 \
    || { tail -5 "$OUT/apply_init.log" >&2; die "apply (init) failed"; }
  grep -c 'initialize=' "$OUT/apply_init.log" > /dev/null
  tail -1 "$OUT/apply_init.log" >&2
  q suite 'CALL take_snap($$init$$)' || die "snapshot init failed"

  # The write counters before the first churn statement.  Their movement across
  # the churn phase is what defines the tables the maintenance step maintains.
  fv suite phase=before "$SQLD/churn_seen.sql" >&2 || die "churn census (before) failed"

  say "churn"
  f suite "$SQLD/fixtures_churn.sql" > "$OUT/suite_churn.log" 2>&1 \
    || { tail -5 "$OUT/suite_churn.log" >&2; die "churn failed"; }
  # The support function 4 fixtures are indexes on t and t2, which the uniform
  # drain above already covers, so this group needs no churn file of its own
  # now that the deduplicate_items fixtures are retired.
  [ "$haveicu" = yes ] && f suite "$SQLD/churn_icu.sql" >> "$OUT/suite_churn.log" 2>&1

  # The maintenance assumption of the shared definition: VACUUM ANALYZE on
  # every table the churn touched, before the census and the decide phase.  The
  # churn ran in psql processes that have now exited, so their statistics are
  # flushed; one second of grace covers the collector interval of the older
  # server, whose reader also waits for a fresh file.
  sleep 1
  fv suite phase=after "$SQLD/churn_seen.sql" >&2 || die "churn census (after) failed"
  say "maintenance: VACUUM (VERBOSE, ANALYZE) on every churned table"
  f suite "$SQLD/maint.sql" > "$OUT/maint.log" 2> "$OUT/maint_verbose.log" \
    || { tail -5 "$OUT/maint_verbose.log" >&2; die "maintenance step failed"; }
  note "$(head -2 "$OUT/maint.log" | tail -1)"
  # Proof 2 of the no-defeat rule: each statement's own VERBOSE counts, parsed
  # out of the message text and stored per table.
  parse_verbose "$OUT/maint_verbose.log" > "$SQLD/maint_verbose.sql"
  [ -s "$SQLD/maint_verbose.sql" ] \
    || die "the VACUUM VERBOSE output produced no tuples line: the proof is missing"
  f suite "$SQLD/maint_verbose.sql" > /dev/null || die "recording the VERBOSE counts failed"
  sleep 1
  f suite "$SQLD/maint_after.sql" >&2 || die "post-maintenance read failed"
  suite_maint_proofs

  # Rule 3 of the shared definition: a fixture that moved more than 10 % of a
  # table's heap tuples gets an ANALYZE, because autovacuum would have run one.
  # With the maintenance step in front of it the census finds every churned
  # table freshly analyzed, so what it decides now is the tables no churn
  # touched, and it doubles as the recheck that the counters were published in
  # the right order.
  say "simulated auto-analyze: the engine's own threshold on its own counters"
  f suite "$SQLD/autoanalyze.sql" > "$OUT/autoanalyze.log" 2>&1 \
    || { tail -5 "$OUT/autoanalyze.log" >&2; die "simulated auto-analyze failed"; }
  # The recheck waits a second and reads from a new session, so that it can see
  # the counters the census just reset on either server.
  sleep 1
  f suite "$SQLD/autoanalyze_after.sql" >> "$OUT/autoanalyze.log" 2>&1 \
    || { tail -5 "$OUT/autoanalyze.log" >&2; die "census recheck failed"; }
  t suite "SELECT /* wiki_btmaint_autoanalyze_report */ tbl, reltuples, mods,
                  threshold, mod_pct, would_autoanalyze
             FROM autoanl ORDER BY would_autoanalyze DESC, mods DESC, tbl" \
    > "$OUT/autoanalyze.txt" 2>&1
  { printf 'tables considered  %s\n' \
      "$(s suite 'SELECT count(*) FROM autoanl')"
    printf 'analyzed           %s\n' \
      "$(s suite 'SELECT count(*) FROM autoanl WHERE would_autoanalyze')"
    printf 'left alone         %s\n' \
      "$(s suite 'SELECT count(*) FROM autoanl WHERE NOT would_autoanalyze')"
    printf 'counters reset     %s of %s\n' \
      "$(s suite 'SELECT count(*) FROM autoanl_after WHERE mods = 0')" \
      "$(s suite 'SELECT count(*) FROM autoanl_after')"
    printf 'mod_pct of those analyzed, min/median/max %s\n' \
      "$(s suite "SELECT min(mod_pct) || ' / ' ||
                         percentile_disc(0.5) WITHIN GROUP (ORDER BY mod_pct) || ' / ' ||
                         max(mod_pct) FROM autoanl WHERE would_autoanalyze")"
    printf 'largest mod_pct left alone %s\n' \
      "$(s suite "SELECT COALESCE(max(mod_pct)::text, 'none')
                    FROM autoanl WHERE NOT would_autoanalyze")"; } \
    >> "$OUT/autoanalyze.txt"
  # The guard the old "no table crossed the threshold" check was really making
  # - that the churn counters were visible at all - now lives in
  # suite_maint_proofs, which fails when a maintained table reached its VACUUM
  # ANALYZE with an unpublished counter.  A census that analyzes nothing is a
  # legitimate outcome once every churned table has just been analyzed, so it
  # is reported rather than fatal.
  tail -6 "$OUT/autoanalyze.txt" >&2

  say "preconditions: what the shared definition requires of a numbered fixture"
  f suite "$SQLD/precond.sql" > "$OUT/precond.txt" 2>&1 || die "precondition check failed"
  cat "$OUT/precond.txt" >&2

  say "forge: the catalog forgeries an ANALYZE would have overwritten"
  f suite "$SQLD/forge.sql" > "$OUT/forge.log" 2>&1 || die "forge failed"
  cat "$OUT/forge.log" >&2

  # Proof 4 of the no-defeat rule: the page classes the maintenance left in
  # every fixture index.  Read-only, so the decide phase sees the same state.
  say "page classes: what the maintenance left in each index"
  f suite "$SQLD/pageclass.sql" > "$OUT/pageclass.txt" 2>&1 || die "page-class read failed"
  tail -1 "$OUT/pageclass.txt" >&2
  q suite 'CALL take_snap($$churned$$)' || die "snapshot churned failed"

  say "decide: the filed report statement, as filed and through the one-edit view"
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d suite -f "$SQLD/report.sql" \
    > "$OUT/report_churned.txt" 2>&1 || die "filed report failed"
  f suite "$SQLD/plan_view.sql" || die "plan_v failed"
  f suite /dev/stdin <<'SQL' || die "recording the plan failed"
DELETE FROM truth;
INSERT INTO truth(idx, action, baseline, wasted_pct, notes, bytes_churned, cmd_report)
SELECT v.index_name, v.action, v.baseline, v.wasted_pct, v.notes, s.bytes,
       v.comment_command
  FROM plan_v v
  JOIN snap s ON s.phase = 'churned' AND s.idx = v.index_name;
SQL
  note "$(s suite 'SELECT count(*) || $$ decisions recorded$$ FROM truth')"

  say "act: the filed apply block, second run"
  f suite "$SQLD/apply.sql" > "$OUT/apply_act.log" 2>&1 \
    || { tail -20 "$OUT/apply_act.log" >&2; die "apply (act) failed"; }
  tail -1 "$OUT/apply_act.log" >&2
  q suite 'CALL take_snap($$applied$$)' || die "snapshot applied failed"
  f suite /dev/stdin <<'SQL' || die "recording the applied state failed"
UPDATE truth t
   SET bytes_applied = a.bytes,
       cmd_written = a.cmt,
       reindexed_by_heuristic = (a.bytes < t.bytes_churned)
  FROM snap a
 WHERE a.phase = 'applied' AND a.idx = t.idx;
SQL

  say "oracle: REINDEX INDEX on every fixture"
  f suite /dev/stdin <<'SQL' || die "ground truth failed"
SET /* wiki_btmaint_oracle_statement_timeout */ statement_timeout = '900s';
CALL ground_truth();
SQL
  note "$(s suite 'SELECT count(*) || $$ fixtures with an oracle$$ FROM truth WHERE bytes_fresh IS NOT NULL')"
}

# ---------------------------------------------------------------- cost -------
# What a run costs, in the two states an operator actually meets: a settled
# database where every index is skipped, and one where the size gate fires
# everywhere, which is the worst case because pgstatindex reads every page of
# every gated index.  The gated state is forged by halving each stored sz; the
# suite has already been scored by the time this stage runs, and the forgery is
# recorded so no later stage reads those comments as real baselines.
stage_cost() {
  say "cost: the filed report in a settled and in a fully gated database"
  : > "$OUT/cost.txt"
  local i
  # Settle first: the oracle's rebuilds left many indexes smaller than their
  # stored baseline, which is a refresh, not a skip.  One apply run takes those
  # back to a state where the report has nothing to do, which is the state an
  # operator's scheduled run meets almost every time.
  f suite "$SQLD/apply.sql" > "$OUT/cost_settle.log" 2>&1
  printf 'settled state\n' >> "$OUT/cost.txt"
  s suite "SELECT '  gated indexes: ' || count(*) FILTER (WHERE action <> 'skip') ||
                  ' of ' || count(*) FROM plan_v" >> "$OUT/cost.txt"
  for i in 1 2 3 4 5 6; do
    printf '  run %s %s\n' "$i" \
      "$("$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite -c '\timing on' \
           -f "$SQLD/report.sql" 2>&1 | grep -E '^Time:' | tail -1)" >> "$OUT/cost.txt"
  done
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite \
    -c 'EXPLAIN (ANALYZE, BUFFERS) SELECT count(*) FROM plan_v' 2>&1 \
    | grep -m 1 -E 'Buffers: shared' | sed 's/^ */  total /' >> "$OUT/cost.txt"
  printf 'fully gated state (every stored sz halved)\n' >> "$OUT/cost.txt"
  # Only the size input is forged: both tuple counts are written at their
  # current values, so the fully gated reading isolates one gate rather than
  # three, and the worst case it measures is still every gated index read end
  # to end.
  f suite /dev/stdin > /dev/null 2>&1 <<'SQL'
DO $fg$
DECLARE r record;
BEGIN
  FOR r IN SELECT p.idx, pg_relation_size(p.idx::regclass) AS b,
                  c.reltuples::numeric AS itup, t.reltuples::numeric AS tup
             FROM plan p
             JOIN pg_class c ON c.relname = p.idx AND c.relkind = 'i'
             JOIN pg_index x ON x.indexrelid = c.oid
             JOIN pg_class t ON t.oid = x.indrelid LOOP
    EXECUTE format('COMMENT /* wiki_btmaint_cost_forgery */ ON INDEX %I IS %L',
                   r.idx, '@btmaint:{"v":2,"sz":' || (r.b / 2)::bigint
                          || ',"tup":' || round(GREATEST(r.tup, -1))
                          || ',"itup":' || round(GREATEST(r.itup, -1))
                          || ',"at":"2026-01-01T00:00:00+00"}');
  END LOOP;
END $fg$;
SQL
  s suite "SELECT '  gated indexes: ' || count(*) FILTER (WHERE action <> 'skip') ||
                  ' of ' || count(*) FROM plan_v" >> "$OUT/cost.txt"
  for i in 1 2 3 4 5 6; do
    printf '  run %s %s\n' "$i" \
      "$("$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite -c '\timing on' \
           -f "$SQLD/report.sql" 2>&1 | grep -E '^Time:' | tail -1)" >> "$OUT/cost.txt"
  done
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite \
    -c 'EXPLAIN (ANALYZE, BUFFERS) SELECT count(*) FROM plan_v' 2>&1 \
    | grep -m 1 -E 'Buffers: shared' | sed 's/^ */  total /' >> "$OUT/cost.txt"
  s suite "SELECT '  total index bytes: ' ||
                  pg_size_pretty(sum(pg_relation_size(idx::regclass))) FROM plan" \
    >> "$OUT/cost.txt"
  cat "$OUT/cost.txt" >&2
}

# ---------------------------------------------------------------- score ------
stage_score() {
  say "score"
  t suite "SELECT /* wiki_btmaint_verdict_rows */ num, leg, grp, idx, action,
                  wasted_pct, actual_pct, applied_pct, verdict, lost_by,
                  expected_stage, taken_stage, two_gate_stage, want_stage,
                  size_ratio, tuple_ratio, idx_tuple_ratio
             FROM verdicts ORDER BY num, leg" > "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_verdict_counts */ verdict, count(*)
             FROM verdicts GROUP BY 1 ORDER BY 2 DESC" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_group_counts */ grp,
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE NOT scored) AS unscored,
                  count(*) FILTER (WHERE action = 'reindex') AS reindexed,
                  count(*) FILTER (WHERE action = 'update')  AS updated,
                  count(*) FILTER (WHERE action = 'skip')    AS skipped,
                  count(*) FILTER (WHERE action = 'refresh') AS refreshed,
                  count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE') AS false_neg,
                  round(avg(wasted_pct), 1) AS avg_wasted,
                  round(avg(actual_pct), 1) AS avg_actual
             FROM verdicts GROUP BY grp ORDER BY grp" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_accuracy */
                  count(*) AS measured,
                  round(avg(actual_pct - wasted_pct), 1)  AS mean_error,
                  round(min(actual_pct - wasted_pct), 1)  AS min_error,
                  round(max(actual_pct - wasted_pct), 1)  AS max_error,
                  count(*) FILTER (WHERE abs(actual_pct - wasted_pct) <= 15) AS within_15,
                  count(*) FILTER (WHERE wasted_pct > actual_pct) AS over_estimates
             FROM verdicts WHERE wasted_pct IS NOT NULL AND scored" \
    >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_action_counts */ action, count(*),
                  round(avg(actual_pct), 1) AS avg_actual
             FROM verdicts GROUP BY 1 ORDER BY 2 DESC" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_gate_agreement */
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE expected_stage = taken_stage) AS gate_agrees,
                  count(*) FILTER (WHERE want_stage IS NOT NULL
                                     AND want_stage = taken_stage) AS want_hit,
                  count(*) FILTER (WHERE want_stage IS NOT NULL
                                     AND want_stage <> taken_stage) AS want_miss
             FROM verdicts" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_lost */ num, leg, idx, action, wasted_pct,
                  actual_pct, lost_by, size_ratio, tuple_ratio
             FROM verdicts WHERE lost_by IS NOT NULL ORDER BY actual_pct DESC" \
    > "$OUT/lost.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_disagree */ num, leg, idx, expected_stage,
                  taken_stage, baseline, size_ratio, tuple_ratio, notes
             FROM verdicts WHERE expected_stage <> taken_stage ORDER BY num, leg" \
    > "$OUT/disagree.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_want_miss */ num, leg, idx, want_stage,
                  taken_stage, action, wasted_pct, actual_pct, req
             FROM verdicts WHERE want_stage IS NOT NULL AND want_stage <> taken_stage
            ORDER BY num, leg" > "$OUT/want_miss.txt" 2>&1
  # Did step 2 store the baseline step 1 said it would?  For every action but
  # reindex the two sz values are the same state and must agree; for reindex
  # step 1 prints no command and the stored size must be the post-rebuild one.
  t suite "SELECT /* wiki_btmaint_cmd_match */ action,
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE sz_reported IS NOT NULL) AS reported,
                  count(*) FILTER (WHERE sz_reported = sz_written) AS sz_agrees,
                  count(*) FILTER (WHERE sz_written = bytes_applied) AS sz_is_current
             FROM verdicts GROUP BY action ORDER BY action" >> "$OUT/verdicts.txt" 2>&1
  # Which gate opened each measured fixture, and what the third one changed.
  t suite "SELECT /* wiki_btmaint_gate_attribution */
                  count(*) FILTER (WHERE taken_stage = 'measure') AS measured,
                  count(*) FILTER (WHERE taken_stage = 'measure'
                                     AND size_gate_fires) AS by_size,
                  count(*) FILTER (WHERE taken_stage = 'measure'
                                     AND tbl_gate_fires) AS by_table_tuples,
                  count(*) FILTER (WHERE taken_stage = 'measure'
                                     AND idx_gate_fires) AS by_index_tuples,
                  count(*) FILTER (WHERE taken_stage = 'measure'
                                     AND idx_gate_fires AND NOT size_gate_fires
                                     AND NOT tbl_gate_fires) AS index_gate_only,
                  count(*) FILTER (WHERE taken_stage = 'measure'
                                     AND NOT size_gate_fires AND NOT tbl_gate_fires
                                     AND NOT idx_gate_fires) AS no_gate
             FROM verdicts" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_two_gate_delta */
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE two_gate_stage = taken_stage) AS same_as_two_gate,
                  count(*) FILTER (WHERE two_gate_stage = 'skip'
                                     AND taken_stage = 'measure') AS newly_measured,
                  count(*) FILTER (WHERE two_gate_stage = 'skip'
                                     AND taken_stage = 'measure'
                                     AND actual_pct >= 50) AS newly_measured_bloated,
                  count(*) FILTER (WHERE two_gate_stage = 'skip'
                                     AND taken_stage = 'measure'
                                     AND actual_pct < 50) AS newly_measured_healthy,
                  count(*) FILTER (WHERE two_gate_stage = 'measure'
                                     AND taken_stage <> 'measure') AS lost_measurements
             FROM verdicts" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_newly_measured */ num, leg, idx, action,
                  wasted_pct, actual_pct, verdict, idx_tuple_ratio, req
             FROM verdicts WHERE two_gate_stage = 'skip' AND taken_stage = 'measure'
            ORDER BY actual_pct DESC" > "$OUT/newly_measured.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_itup_stored */
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE itup_stored_matches) AS itup_matches_catalog,
                  count(*) FILTER (WHERE base_idx_tuples IS NULL) AS itup_missing,
                  count(*) FILTER (WHERE itup_written IS NOT NULL) AS itup_written_back
             FROM verdicts" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_lost_detail */ num, leg, idx, actual_pct,
                  size_ratio, tuple_ratio, idx_tuple_ratio,
                  size_gate_fires, tbl_gate_fires, idx_gate_fires, req
             FROM verdicts WHERE lost_by IS NOT NULL
            ORDER BY actual_pct DESC" >> "$OUT/lost.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_payload_health */
                  count(*) AS indexes,
                  count(*) FILTER (WHERE payload IS NOT NULL) AS with_payload,
                  count(*) FILTER (WHERE base_bytes IS NULL) AS unparseable,
                  count(*) FILTER (WHERE cmt !~ '@btmaint:') AS no_marker
             FROM snap WHERE phase = 'applied'" >> "$OUT/verdicts.txt" 2>&1
  # The maintenance assumption and the no-defeat rule, fixture by fixture and
  # then per table, so that a reader can see which fixture was maintained, what
  # its VACUUM removed, what it could not remove, and the page classes left in
  # the index the method was then asked about.
  t suite "SELECT /* wiki_btmaint_maint_by_fixture */ num, leg, idx, tbl,
                  maintained, maint_removed, dead_not_removable, dead_after,
                  deleted_pages, empty_pages, density_after_maint,
                  wasted_pct, actual_pct, verdict
             FROM verdicts ORDER BY num, leg" > "$OUT/maintenance.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_maint_by_table */ ord, tbl, ins, upd, del,
                  mods_before, analyzed_in_churn, dead_before, removed, remain,
                  dead_not_removable, mods_after, dead_after,
                  round(extract(epoch FROM ended - started)::numeric, 2) AS secs
             FROM maint ORDER BY ord" >> "$OUT/maintenance.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_maint_aggregate */
                  count(*) AS maintained_tables,
                  count(*) FILTER (WHERE ended IS NOT NULL) AS completed,
                  count(*) FILTER (WHERE dead_not_removable = 0) AS horizon_clean,
                  count(*) FILTER (WHERE dead_not_removable > 0) AS horizon_pinned,
                  COALESCE(sum(removed), 0) AS tuples_removed,
                  COALESCE(max(dead_after), 0) AS max_dead_left,
                  count(DISTINCT timeouts) AS timeout_sets
             FROM maint" >> "$OUT/maintenance.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_horizon_rows */ step, tbl, xmin_holders,
                  open_xacts, slots, slot_xmins, prepared, detail
             FROM horizon
            WHERE xmin_holders > 0 OR open_xacts > 0 OR slots > 0
               OR prepared > 0 OR tbl IS NULL
            ORDER BY at" >> "$OUT/maintenance.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_pageclass_by_group */ grp,
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE maintained) AS maintained,
                  count(*) FILTER (WHERE deleted_pages > 0) AS with_deleted_pages,
                  COALESCE(sum(deleted_pages), 0) AS deleted_pages,
                  COALESCE(sum(empty_pages), 0) AS empty_pages,
                  round(avg(density_after_maint), 1) AS avg_density
             FROM verdicts GROUP BY grp ORDER BY grp" >> "$OUT/maintenance.txt" 2>&1
  # The precondition the shared definition puts on a numbered fixture, and what
  # this run observed.  A fixture reported here scores nothing.
  t suite "SELECT /* wiki_btmaint_precond_rows */ p.num, p.leg, p.requirement,
                  p.observed, p.met
             FROM precond p ORDER BY p.num, p.leg" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_scored */ count(*) AS fixtures,
                  count(*) FILTER (WHERE scored) AS scored,
                  count(*) FILTER (WHERE NOT scored) AS unmet_precondition,
                  count(*) FILTER (WHERE scored AND verdict = 'PASS') AS pass,
                  count(*) FILTER (WHERE maintained) AS maintained
             FROM verdicts" >> "$OUT/verdicts.txt" 2>&1
  tail -40 "$OUT/verdicts.txt" >&2
}

# ------------------------------------------------- expected server errors ---
# Every server-side error this suite provokes is deliberate, and after the
# page-local acceptance fixtures were removed they all come from stage_facts
# and from the two feature-gated fixture files a 12 server refuses.
#
# The line pattern is the default log_line_prefix, "%m [%p] ": a date, a time
# with milliseconds, the log time zone, the backend pid in brackets, and then
# the severity.  An earlier revision of this function looked for the severity
# immediately after the time zone, which that prefix never produces, so it
# matched nothing and reported a clean log whatever the server had logged.
# The count of matched lines is now reported beside the unexpected ones, so a
# check that matches nothing is visible as such.
UNEXPECTED_ERRORS=0
check_server_errors() {
  local log=$1 total
  [ -f "$log" ] || { note "no server log"; return 0; }
  grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:.]+ [A-Z]+ \[[0-9]+\] (ERROR|FATAL|PANIC):' \
    "$log" > "$OUT/server_errors_all.txt"
  total=$(grep -c '' "$OUT/server_errors_all.txt")
  grep -Ev 'REINDEX CONCURRENTLY cannot run inside a transaction block|cannot be executed from a function|unrecognized parameter "deduplicate_items"|ICU is not supported|unrecognized privilege type|invalid function number 4|invalid transaction termination|syntax error at or near "\|\|"' \
    "$OUT/server_errors_all.txt" > "$OUT/server_errors.txt"
  UNEXPECTED_ERRORS=$(grep -c '' "$OUT/server_errors.txt")
  printf 'logged errors: %s, deliberate: %s, unexpected: %s\n' \
    "$total" "$((total - UNEXPECTED_ERRORS))" "$UNEXPECTED_ERRORS"
  [ "$UNEXPECTED_ERRORS" -gt 0 ] && head -5 "$OUT/server_errors.txt"
  return 0
}

# Proof 1 of the no-defeat rule, from the log side: a maintenance command that
# was skipped for want of the lock, or cancelled part-done, says so in the
# server log.  A foreground VACUUM without SKIP_LOCKED waits rather than
# skipping, and nothing in this suite holds a conflicting lock, so the expected
# count is zero on both counts; the check exists because a zero it never looked
# for would prove nothing.
MAINT_SKIPS=0
check_maintenance_skips() {
  local log=$1
  [ -f "$log" ] || { note "no server log"; return 0; }
  grep -E 'skipping vacuum of|skipping analyze of|canceling statement due to|canceling autovacuum task' \
    "$log" > "$OUT/maint_skips.txt"
  MAINT_SKIPS=$(grep -c '' "$OUT/maint_skips.txt")
  printf 'maintenance skip or cancellation lines: %s\n' "$MAINT_SKIPS"
  [ "$MAINT_SKIPS" -gt 0 ] && head -5 "$OUT/maint_skips.txt"
  return 0
}

# ---------------------------------------------------------------- criteria ---
stage_criteria() {
  say "pass criteria"
  # Every counter comes through a file, not through -c: a dollar-quoted string
  # inside a double-quoted shell argument would have $$ replaced by the shell's
  # own process id before psql ever saw it.
  "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d suite -f - > "$OUT/counters.txt" 2>&1 <<'SQL'
SELECT 'planned=' || count(*) FROM plan;
SELECT '  ' || verdict || '=' || count(*) FROM verdicts GROUP BY verdict ORDER BY verdict;
SELECT '  gate agree=' || count(*) FILTER (WHERE expected_stage = taken_stage) ||
       ' disagree='    || count(*) FILTER (WHERE expected_stage <> taken_stage) ||
       ' want_hit='    || count(*) FILTER (WHERE want_stage = taken_stage) ||
       ' want_miss='   || count(*) FILTER (WHERE want_stage <> taken_stage)
  FROM verdicts;
SELECT '  action ' || action || '=' || count(*) FROM verdicts GROUP BY action ORDER BY action;
SELECT '  payload with=' || count(*) FILTER (WHERE payload IS NOT NULL) ||
       ' unparseable='   || count(*) FILTER (WHERE base_bytes IS NULL) ||
       ' no_marker='     || count(*) FILTER (WHERE cmt !~ '@btmaint:')
  FROM snap WHERE phase = 'applied';
SELECT '  false negatives=' || count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE') ||
       ' of which the index tuple gate opened=' ||
       count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE' AND idx_gate_fires)
  FROM verdicts;
SELECT '  measured=' || count(*) FILTER (WHERE taken_stage = 'measure') ||
       ' by size='   || count(*) FILTER (WHERE taken_stage = 'measure' AND size_gate_fires) ||
       ' by table='  || count(*) FILTER (WHERE taken_stage = 'measure' AND tbl_gate_fires) ||
       ' by index='  || count(*) FILTER (WHERE taken_stage = 'measure' AND idx_gate_fires) ||
       ' index only='|| count(*) FILTER (WHERE taken_stage = 'measure' AND idx_gate_fires
                                          AND NOT size_gate_fires AND NOT tbl_gate_fires)
  FROM verdicts;
SELECT '  versus the two-gate form: same=' ||
       count(*) FILTER (WHERE two_gate_stage = taken_stage) ||
       ' newly measured=' || count(*) FILTER (WHERE two_gate_stage = 'skip'
                                                AND taken_stage = 'measure') ||
       ' of those bloated=' || count(*) FILTER (WHERE two_gate_stage = 'skip'
                                                 AND taken_stage = 'measure'
                                                 AND actual_pct >= 50) ||
       ' healthy=' || count(*) FILTER (WHERE two_gate_stage = 'skip'
                                        AND taken_stage = 'measure'
                                        AND actual_pct < 50)
  FROM verdicts;
SELECT '  itup stored = catalog count: ' ||
       count(*) FILTER (WHERE itup_stored_matches) || ' of ' || count(*)
  FROM verdicts;
SELECT '  simulated auto-analyze: ' ||
       count(*) FILTER (WHERE would_autoanalyze) || ' of ' || count(*) ||
       ' tables analyzed, largest left alone ' ||
       COALESCE(max(mod_pct) FILTER (WHERE NOT would_autoanalyze)::text, 'none') || ' %'
  FROM autoanl;
SELECT '  scored=' || count(*) FILTER (WHERE scored) ||
       ' unmet precondition=' || count(*) FILTER (WHERE NOT scored) ||
       ' maintained=' || count(*) FILTER (WHERE maintained) ||
       ' of ' || count(*)
  FROM verdicts;
SELECT '  maintenance: ' || count(*) || ' tables, ' ||
       count(*) FILTER (WHERE ended IS NOT NULL) || ' completed, ' ||
       count(*) FILTER (WHERE dead_not_removable = 0) ||
       ' with nothing dead but not yet removable, ' ||
       count(*) FILTER (WHERE COALESCE(dead_after, 0) = 0) ||
       ' with no dead tuple left, timeout sets=' || count(DISTINCT timeouts)
  FROM maint;
SELECT '  timeouts in force during maintenance: ' || timeouts
  FROM maint GROUP BY timeouts ORDER BY timeouts;
SELECT '  horizon probes: ' || count(*) || ' taken, ' ||
       count(*) FILTER (WHERE xmin_holders = 0 AND open_xacts = 0
                          AND slots = 0 AND prepared = 0) || ' entirely clean, ' ||
       COALESCE(sum(slots), 0) || ' replication slots, ' ||
       COALESCE(sum(prepared), 0) || ' prepared transactions seen'
  FROM horizon;
SELECT '  page classes after maintenance: ' ||
       count(*) FILTER (WHERE deleted_pages > 0) || ' of ' || count(*) ||
       ' indexes hold deleted pages, ' || COALESCE(sum(deleted_pages), 0) ||
       ' deleted and ' || COALESCE(sum(empty_pages), 0) || ' half-dead in total'
  FROM pageclass;
SELECT '  precondition ' || num || ': ' || observed || ' -> ' ||
       CASE WHEN met THEN 'met' ELSE 'NOT MET, scores nothing' END
  FROM precond ORDER BY num, leg;
SQL
  { printf '1. texts\n'; cat "$OUT/hashes.txt" 2>/dev/null
    printf '2. engine checks\n'; cat "$OUT/checks.txt" 2>/dev/null
    printf '3. fixture groups\n'; cat "$OUT/suite_groups.txt" 2>/dev/null
    printf '4. counters\n'; sed 's/^/   /' "$OUT/counters.txt" 2>/dev/null
    printf '5. cost\n'; sed 's/^/   /' "$OUT/cost.txt" 2>/dev/null
    printf '5a. simulated auto-analyze\n'
    sed 's/^/   /' "$OUT/autoanalyze.txt" 2>/dev/null
    printf '5b. the maintenance and the no-defeat proofs\n'
    sed 's/^/   /' "$OUT/maint_proofs.txt" 2>/dev/null
    printf '6. facts\n'; sed 's/^/   /' "$OUT/facts.txt" 2>/dev/null
  } > "$OUT/criteria.txt" 2>&1
  { printf '7. server errors\n'; check_server_errors "$OUT/server.log"
    printf '8. maintenance skips and cancellations\n'
    check_maintenance_skips "$OUT/server.log"; } >> "$OUT/criteria.txt" 2>&1
  tail -60 "$OUT/criteria.txt" >&2
  note "full criteria in $OUT/criteria.txt"
}

# ---------------------------------------------------------------- report -----
stage_report() {
  say "report written to $OUT"
  ls -1 "$OUT" >&2
}

# ---------------------------------------------------------------- stop -------
# -m fast disconnects clients and lets the checkpointer write a shutdown
# checkpoint, so the next start needs no recovery.  The stop is then confirmed
# the way the teardown rule asks, and the stage dies rather than report a stop
# that did not happen, so clean never deletes a live cluster.
stage_stop() {
  say "stop the server cleanly"
  [ -x "$BIN/pg_ctl" ] || { note "no server binary under $BIN"; return 0; }
  if [ -s "$DATA/postmaster.pid" ] && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1 \
      || die "pg_ctl -m fast stop failed"
    tail -3 "$OUT/server.log" 2>/dev/null | grep -q 'database system is shut down' \
      && note "server.log: database system is shut down"
  else
    note "not running"
  fi
  [ -e "$DATA/postmaster.pid" ] && die "$DATA/postmaster.pid still exists"
  if command -v pgrep > /dev/null 2>&1 && pgrep -f -- "-D $DATA" > /dev/null 2>&1; then
    die "a postgres process still runs on $DATA"
  fi
  [ -z "$(ls -A "$SOCK" 2>/dev/null)" ] || die "socket directory $SOCK is not empty"
  note "confirmed: no postmaster.pid, no postgres process on $DATA, socket empty"
}

# Containment check before any rm -rf: SANDBOX comes from the environment, so
# refuse to delete anything outside this repository's .wiki-runtime/tmp tree.
inside_tmp() {
  case ${1%/} in
    "$WIKI_ROOT/.wiki-runtime/tmp"/?*) return 0 ;;
    *) return 1 ;;
  esac
}
stage_clean() {
  stage_stop
  inside_tmp "$SANDBOX" || die "refusing to delete $SANDBOX outside .wiki-runtime/tmp/"
  rm -rf "$SANDBOX"; say "sandbox deleted"
}

main() {
  local stages=("$@")
  [ ${#stages[@]} -eq 0 ] && stages=(build check cluster sql texts facts suite \
                                     cost score criteria report)
  local st
  for st in "${stages[@]}"; do
    case $st in
      build|check|cluster|sql|texts|facts|suite|cost|score|criteria|report|stop|clean)
        "stage_$st" ;;
      *) die "unknown stage: $st" ;;
    esac
  done
}

main "$@"
```

### The PostgreSQL 12 leg script

```bash
#!/usr/bin/env bash
#
# btmaint_suite_v12.sh - the PostgreSQL 12 leg of the suite behind the wiki page
# "A COMMENT-Stored Baseline B-Tree Index-Maintenance Heuristic for PostgreSQL
# 12 Through 17", in bash and SQL only.  It is the compatibility half of the
# page's claim: the two texts the page files must run on a 12 server without
# one character changed.
#
# The leg starts with stage_exact, which executes both filed texts verbatim and
# records the outcome as a result in its own right, before any fixture exists.
# Everything else version-local is discovered on the running server rather than
# assumed: stage_facts asks the questions the 17 leg asks, and the fixture
# groups needing a feature this server lacks - B-tree support function 4 of
# PostgreSQL 13, and ICU collations in a build configured --without-icu - are
# skipped and recorded as skipped.
#
# It builds 12.2 out of tree from the pinned checkout, runs the engine
# regression suites, starts an isolated cluster, takes the page's two texts out
# of the page itself, ports every numbered fixture the wiki's shared definition
# "Mandatory B-Tree Bloat Tests" still defines (tests 1-17, 18-91 and controls
# 92-120, less the retired 11, 38, 65, 67, 69, 106, 117, 121 and legs 113a and
# 113c), stores an as-built baseline in each index comment, churns each
# fixture, maintains every table the churn touched, simulates the auto-analyze
# that churn would have triggered on a server with autovacuum on, runs the
# heuristic, and scores every decision against a measured REINDEX INDEX.
#
# The shared definition's maintenance assumption is applied in full as of the
# 2026-09-16 revision: the maintenance step inside stage_suite runs
# VACUUM (VERBOSE, ANALYZE) on every table the churn inserted, updated or
# deleted a row in - the set comes from
# the engine's own pg_stat_all_tables counters across the churn phase, not
# from a hand-written list - and it runs before the rule 3 census and the
# decide phase.  A table no churn touched is not maintained, because draining or
# re-analyzing a deliberately fresh or deliberately stale fixture would destroy
# the shape it exists to build.
#
# The same revision carries out the shared definition's newer rule, "the
# maintenance must not be defeated".  Four proofs are recorded per maintained
# table: that the statement ran to completion with no skip line naming the
# table, the count of dead row versions its VERBOSE output says cannot be
# removed yet - this server's wording for the same number - the horizon holders
# read from pg_stat_activity, pg_replication_slots and pg_prepared_xacts
# immediately before it, and the index page classes after it.  Every session
# that issues a VACUUM or an ANALYZE forces statement_timeout, lock_timeout and
# idle_in_transaction_session_timeout to 0, which is what the autovacuum
# launcher and worker do to themselves for this exact reason; this server has
# no transaction_timeout to force, that GUC arriving in PostgreSQL 17.  The
# timeouts in force are recorded rather than assumed.
#
# Fixture 120's precondition is asserted rather than assumed: the shared
# definition says a run that finds a non-zero post-census estimate for its
# partial index scores nothing from the fixture, so the precondition step
# records the observed estimate and the scorer reports that fixture as UNMET
# PRECONDITION and excludes it from every scored count.
#
# The simulated auto-analyze is the mandatory-test rule that any fixture moving
# more than 10 % of a table's heap tuples must ANALYZE it.  It is not
# hand-annotated per fixture: the census reads the engine's own
# n_mod_since_analyze counter and applies the engine's own threshold,
# autovacuum_analyze_threshold + autovacuum_analyze_scale_factor * reltuples
# (50 + 0.1 * reltuples at the defaults), so the tables it analyzes are exactly
# the tables an autovacuum launcher would have analyzed.  Every table it
# considered, with its counter, its threshold and the verdict, is recorded.
# With the maintenance step in front of it the census now finds every churned
# table freshly analyzed, so what it decides is the tables no churn touched -
# which is what the shared definition says it should decide.
#
# The pinned checkout is read only: everything this script writes lives under
# $SANDBOX (default .wiki-runtime/tmp/btmaint).
#
# Usage, from the repository root:
#   bash btmaint_suite_v12.sh                  # every stage, in order
#   bash btmaint_suite_v12.sh suite score      # selected stages
#   bash btmaint_suite_v12.sh clean            # stop and delete the sandbox
#
# Stages: build check cluster sql texts exact facts suite cost score
#         criteria report stop clean
#
# Environment: WIKI_ROOT PAGE SRC SANDBOX PORT JOBS
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v17/questions/indexing/btree-comment-baseline-maintenance-heuristic.md}"
SRC="${SRC:-$WIKI_ROOT/raw/postgres-12}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/btmaint}"
PORT="${PORT:-55412}"
JOBS="${JOBS:-8}"

BUILD="$SANDBOX/build/12"; INST="$SANDBOX/inst/12"; DATA="$SANDBOX/data12"
OUT="$SANDBOX/out12"; SQLD="$SANDBOX/sql12"; SOCK="$SANDBOX/sock12"; BIN="$INST/bin"
export PGPORT="$PORT" PGHOST="$SOCK" PGDATABASE=postgres

# SHA-256 baselines of the two fenced SQL blocks of the page, in page order:
# the report statement and the apply block.  A changed text must be re-measured
# and the hash refiled; that is the point of recording them here.
BASE_REPORT=93b64e2dd33d411951ceffd9d665a3e3e8ce3a71fde60bbca9e61c219febd0e9
BASE_APPLY=7427d62d2ca3bb43dd2f7c5a8aa97c27fc8111d65d3066594660c2808d47992d

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# psql helpers.  -X ignores ~/.psqlrc; ON_ERROR_STOP is on every helper, because
# without it a failed statement inside a -f script leaves the exit status 0.
q()  { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$1" -c "$2"; }        # command
f()  { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$1" -f "$2"; }        # file
# fv() is f() with one psql variable, for the two-phase churn census.
fv() { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -v "$2" -d "$1" -f "$3"; }
s()  { "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d "$1" -c "$2"; }    # scalar
t()  { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off \
                   -d "$1" -c "$2"; }                                 # table
# err() runs a statement that is expected to fail and prints the message only.
err() { "$BIN/psql" -X -q -v ON_ERROR_STOP=0 -d "$1" -c "$2" 2>&1 \
        | grep -E '^(ERROR|psql:.*ERROR)' | head -1; }
# errf() sends a statement through a file, so that a body full of quotes and
# dollar signs reaches the server exactly as written, and reports the first
# error line or "accepted".
errf() {
  local db=$1 out
  out=$(printf '%s\n' "$2" | "$BIN/psql" -X -q -v ON_ERROR_STOP=0 -d "$db" -f - 2>&1 \
        | grep -E 'ERROR' | head -1)
  printf '%s' "${out:-accepted}"
}

# md_block <fence-language> <n> <file>: print the nth fenced block, bash only.
# The fence is assembled from printf '\140' so that this script contains no
# literal Markdown fence and can therefore live inside one.
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

# parse_verbose <log> : turn the maintenance step's VACUUM (VERBOSE) output
# into one UPDATE per maintained table, so that each statement's own count of
# rows it could not remove is a recorded number rather than a line in a log.
# This server words the same fact differently from a 17 server, and puts it in
# two messages rather than one:
#   INFO:  "tbl": found X removable, Y nonremovable row versions in A out of B pages
#   DETAIL:  Z dead row versions cannot be removed yet, oldest xmin: N
# so the table name is carried from the INFO line to the DETAIL line that
# follows it.  Bash case patterns and parameter expansion only: no awk, no
# perl.
parse_verbose() {
  local log=$1 line cur="" rest removed remain dead
  while IFS= read -r line; do
    case $line in
      *'": found '*' removable, '*' nonremovable row versions in '*)
        rest=${line#*\"}; cur=${rest%%\"*}
        rest=${line#*: found };   removed=${rest%% removable,*}
        rest=${rest#* removable, }; remain=${rest%% nonremovable*} ;;
      *' dead row versions cannot be removed yet'*)
        [ -n "$cur" ] || continue
        rest=${line#*DETAIL:  }; dead=${rest%% dead row versions*}
        printf "UPDATE /* wiki_btmaint_maint_verbose */ maint SET removed = %s, remain = %s, dead_not_removable = %s WHERE tbl = '%s';\n" \
               "$removed" "$remain" "$dead" "$cur"
        cur="" ;;
    esac
  done < "$log"
}

# plan_view <report-text> : the one documented edit.  Drop the two SET lines,
# which a view cannot carry, and wrap the rest in CREATE VIEW plan_v.  Nothing
# else is touched, so the view computes exactly what the filed statement does.
plan_view() {
  local file=$1 line
  printf 'DROP VIEW IF EXISTS plan_v;\nCREATE VIEW plan_v AS\n'
  while IFS= read -r line; do
    case $line in
      "SET /* wiki_btmaint_statement_timeout"*) continue ;;
      "SET /* wiki_btmaint_lock_timeout"*)      continue ;;
    esac
    printf '%s\n' "$line"
  done < "$file"
}

# ---------------------------------------------------------------- build ------
stage_build() {
  say "build 12.2 out of tree from $SRC"
  if [ -x "$BIN/postgres" ]; then
    note "already built: $("$BIN/postgres" --version)"; return 0
  fi
  [ -x "$SRC/configure" ] || die "no pinned checkout at $SRC"
  mkdir -p "$BUILD" "$OUT" "$SQLD"
  ( cd "$BUILD" && "$SRC/configure" --prefix="$INST" --without-icu \
      > configure.log 2>&1 ) || { cp "$BUILD/configure.log" "$OUT/" 2>/dev/null
                                  die "configure failed, see $OUT/configure.log"; }
  ( cd "$BUILD" && make -j"$JOBS" -s > make.log 2>&1 \
      && make -s install > install.log 2>&1 ) \
    || { cp "$BUILD"/*.log "$OUT/" 2>/dev/null; die "make failed"; }
  local m
  for m in pgstattuple pageinspect amcheck; do
    ( cd "$BUILD" && make -C "contrib/$m" -s install >> install.log 2>&1 ) \
      || die "contrib/$m install failed"
  done
  cp "$BUILD"/configure.log "$BUILD"/make.log "$BUILD"/install.log "$OUT/" 2>/dev/null
  note "$("$BIN/postgres" --version)"
}

# ---------------------------------------------------------------- check ------
stage_check() {
  say "engine regression suites"
  # $OUT is created here rather than assumed: stage_build returns early when
  # the binary is already there, so a run that starts from a built tree would
  # otherwise write every check result into a directory that does not exist and
  # report an empty check section.
  mkdir -p "$OUT"
  : > "$OUT/checks.txt"
  ( cd "$BUILD" && make -s check > check_core.log 2>&1 )
  printf 'core=%s %s\n' "$?" \
    "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' \
        "$BUILD/check_core.log" | tail -1)" >> "$OUT/checks.txt"
  local m
  for m in pgstattuple pageinspect amcheck; do
    ( cd "$BUILD" && make -s -C "contrib/$m" check > "check_$m.log" 2>&1 )
    printf '%s=%s %s\n' "$m" "$?" \
      "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' \
          "$BUILD/check_$m.log" | tail -1)" >> "$OUT/checks.txt"
  done
  cp "$BUILD"/check_*.log "$OUT/" 2>/dev/null
  local d
  for d in "$BUILD/src/test/regress" "$BUILD"/contrib/*; do
    [ -f "$d/regression.diffs" ] \
      && cp "$d/regression.diffs" "$OUT/diffs_$(basename "$d").txt"
  done
  cat "$OUT/checks.txt" >&2
}

# ---------------------------------------------------------------- cluster ----
# Cluster settings and their apply scope, all written before the first start:
#   listen_addresses, port, unix_socket_directories, shared_buffers,
#   logging_collector                                  -> PGC_POSTMASTER, restart
#   fsync, autovacuum                                  -> PGC_SIGHUP, reload
#   maintenance_work_mem, max_parallel_maintenance_workers
#                                                      -> PGC_USERSET, session
# autovacuum is off so that no background vacuum moves a fixture between the
# baseline, the churn, the decision and the rebuild oracle.
stage_cluster() {
  say "isolated cluster on port $PORT"
  mkdir -p "$OUT" "$SQLD" "$SOCK"
  if [ -s "$DATA/postmaster.pid" ] && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    note "already running"
  else
    if [ ! -d "$DATA" ]; then
      "$BIN/initdb" -D "$DATA" --locale=C --encoding=UTF8 > "$OUT/initdb.log" 2>&1 \
        || die "initdb failed"
      cat >> "$DATA/postgresql.conf" <<CONF
listen_addresses = ''
unix_socket_directories = '$SOCK'
port = $PORT
autovacuum = off
fsync = off
shared_buffers = '512MB'
maintenance_work_mem = '256MB'
max_parallel_maintenance_workers = 0
logging_collector = off
CONF
    fi
    "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w start > /dev/null \
      || die "server start failed"
  fi
  note "$(s postgres 'SELECT /* wiki_btmaint_version */ version()')"
  s postgres "SELECT /* wiki_btmaint_platform */
                     'max_data_alignment=' || max_data_alignment ||
              ' database_block_size=' || database_block_size FROM pg_control_init()" \
    | tee "$OUT/platform.txt" >&2
  printf 'uname: %s\n' "$(uname -sm)" >> "$OUT/platform.txt"
  # One database, the suite's.  The page-local acceptance database this stage
  # used to create beside it is gone with the fixtures that lived in it.
  local db
  for db in suite; do
    s postgres "SELECT /* wiki_btmaint_database_exists */ 1
                  FROM pg_database WHERE datname = '$db'" | grep -q 1 \
      || "$BIN/createdb" -T template0 -E UTF8 --locale=C "$db"
    q "$db" 'CREATE EXTENSION IF NOT EXISTS pgstattuple' || die "pgstattuple failed"
  done
}

# ------------------------------------------------------------------ sql ------
# Every SQL file this suite uses, written out from here so that the script is
# self-contained.  The two texts under test are NOT here: they come out of the
# page itself, in stage_texts.
stage_sql() {
  say "write the suite's SQL files to $SQLD"
  mkdir -p "$SQLD"
  cat > "$SQLD/harness.sql" <<'HARNESS'
-- Harness for the ported numbered suite.  Disposable: every object below is
-- created in the sandbox cluster's suite database and is not meant for a
-- database anyone cares about.  The harness never touches the heuristic's own
-- two texts; it only records, snapshots and scores.
SET /* wiki_btmaint_harness_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_harness_statement_timeout */ statement_timeout = '900s';
SET /* wiki_btmaint_harness_lock_timeout */ lock_timeout = '5s';

DROP TABLE IF EXISTS plan CASCADE;
DROP TABLE IF EXISTS snap CASCADE;
DROP TABLE IF EXISTS truth CASCADE;
DROP TABLE IF EXISTS churn_seen CASCADE;
DROP TABLE IF EXISTS maint CASCADE;
DROP TABLE IF EXISTS horizon CASCADE;
DROP TABLE IF EXISTS pageclass CASCADE;
DROP TABLE IF EXISTS precond CASCADE;
DROP VIEW IF EXISTS verdicts CASCADE;

-- One row per numbered fixture index.
CREATE TABLE plan(num int, leg text DEFAULT '', grp text, req text, idx text,
                  want_stage text, note text,
                  PRIMARY KEY (num, leg));

-- One row per index per phase.  phase is 'built', 'init', 'churned', 'applied'.
-- idx_tuples is the index's own pg_class.reltuples, which the heuristic now
-- reads as its third gate input; base_idx_tuples is the itup field of the
-- stored payload, parsed here independently of the filed text.
CREATE TABLE snap(phase text, idx text, idx_oid oid, bytes bigint,
                  tbl_tuples numeric, idx_tuples numeric, cmt text, payload text,
                  base_bytes numeric, base_tuples numeric, base_idx_tuples numeric,
                  PRIMARY KEY (phase, idx));

-- What the heuristic decided, and what a rebuild actually gave back.
CREATE TABLE truth(idx text PRIMARY KEY, action text, baseline text,
                   wasted_pct numeric, notes text,
                   bytes_churned bigint, bytes_applied bigint, bytes_fresh bigint,
                   reindexed_by_heuristic bool, cmd_report text, cmd_written text);

CREATE OR REPLACE FUNCTION plan_add(n int, g text, r text, i text,
                                    w text DEFAULT NULL, lg text DEFAULT '',
                                    nt text DEFAULT NULL)
RETURNS void LANGUAGE sql AS
$$ INSERT INTO plan(num, leg, grp, req, idx, want_stage, note)
   VALUES (n, lg, g, r, i, w, nt) $$;

-- The write counters of every fixture table, recorded before the first churn
-- statement and again after the last, so that "the tables the churn touched"
-- is the engine's own record rather than a hand-written list.  The maintenance
-- assumption of the shared definition is then applied to exactly the tables
-- whose insert, update or delete counter moved.
CREATE TABLE churn_seen(phase text, tbl text, ins numeric, upd numeric,
                        del numeric, mods numeric, dead numeric,
                        last_analyze timestamptz,
                        PRIMARY KEY (phase, tbl));

-- One row per maintenance statement: the VACUUM (VERBOSE, ANALYZE) that the
-- assumption credits with maintaining the churn, and the proofs the no-defeat
-- rule asks for.  dead_not_removable is the VERBOSE line's own count, parsed
-- out of the server's message text; a non-zero value on a churned table means
-- a horizon was pinned and the fixture is repaired rather than scored.
CREATE TABLE maint(tbl text PRIMARY KEY, ord int, ins numeric, upd numeric,
                   del numeric, mods_before numeric, dead_before numeric,
                   analyzed_in_churn bool,
                   started timestamptz, ended timestamptz,
                   removed numeric, remain numeric, dead_not_removable numeric,
                   mods_after numeric, dead_after numeric, timeouts text);

-- The horizon holders, read immediately before each maintenance statement and
-- once after the census.  These are reads beside the statement, not an
-- interlock around it, which is the limitation the shared definition records
-- against itself.
CREATE TABLE horizon(step text, tbl text, at timestamptz, xmin_holders int,
                     open_xacts int, slots int, slot_xmins int, prepared int,
                     detail text);

-- The page classes of every fixture index after the maintenance step: the
-- deleted and half-dead pages a drain leaves behind, which is the visible
-- trace of a horizon that did or did not move.
CREATE TABLE pageclass(idx text PRIMARY KEY, leaf_pages numeric,
                       empty_pages numeric, deleted_pages numeric,
                       avg_leaf_density numeric, index_size numeric);

-- Preconditions the shared definition puts on a numbered fixture.  A fixture
-- whose precondition is not met scores nothing: the verdict view reports it as
-- UNMET PRECONDITION and every scored count excludes it.
CREATE TABLE precond(num int, leg text DEFAULT '', requirement text,
                     observed text, met bool, PRIMARY KEY (num, leg));

-- horizon_probe records who could be holding back a removal horizon at the
-- moment it is called: any other backend with a transaction open or an xmin
-- published, any replication slot, and any prepared transaction.  VACUUM's
-- OldestXmin folds in exactly those, so a clean reading on both sides of a
-- maintenance statement is the evidence that nothing pinned the horizon while
-- it ran.  The probe's own backend is excluded by pid: it is the session
-- issuing the maintenance, and its INSERT commits before the VACUUM begins.
CREATE OR REPLACE FUNCTION horizon_probe(p_step text, p_tbl text)
RETURNS void LANGUAGE sql AS $hp$
INSERT INTO horizon(step, tbl, at, xmin_holders, open_xacts, slots,
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
       (SELECT COALESCE(string_agg(a.pid || ':' || COALESCE(a.state, '?')
                                   || ':xmin=' || COALESCE(a.backend_xmin::text, '-'),
                                   ', ' ORDER BY a.pid), 'none')
          FROM pg_stat_activity a
         WHERE a.pid <> pg_backend_pid()
           AND (a.backend_xmin IS NOT NULL OR a.xact_start IS NOT NULL))
$hp$;

-- take_snap records, for every planned index, the facts the heuristic reads:
-- the file size, the table's estimated tuple count, and the baseline stored in
-- the index's own comment.  It parses the payload the same way the filed text
-- does, independently, so a disagreement is visible.
CREATE OR REPLACE PROCEDURE take_snap(ph text) LANGUAGE plpgsql AS $sn$
BEGIN
  DELETE FROM snap WHERE phase = ph;
  INSERT INTO snap
  SELECT ph, p.idx, c.oid, pg_relation_size(c.oid), t.reltuples::numeric,
         c.reltuples::numeric, d.description,
         substring(d.description from '@btmaint:(\{[^}]*\})'),
         substring(d.description from '"sz":([0-9]{1,25})[,}]')::numeric,
         substring(d.description from
                   '"tup":(-?[0-9]{1,25}(?:[.][0-9]{1,10})?)[,}]')::numeric,
         substring(d.description from
                   '"itup":(-?[0-9]{1,25}(?:[.][0-9]{1,10})?)[,}]')::numeric
    FROM plan p
    JOIN pg_class c ON c.relname = p.idx AND c.relkind = 'i'
    JOIN pg_index x ON x.indexrelid = c.oid
    JOIN pg_class t ON t.oid = x.indrelid
    LEFT JOIN pg_description d ON d.objoid = c.oid
                              AND d.classoid = 'pg_class'::regclass
                              AND d.objsubid = 0;
END $sn$;

-- ground_truth rebuilds every planned index and records the fresh size.  It is
-- the oracle: what REINDEX INDEX actually gives back on the churned file.
CREATE OR REPLACE PROCEDURE ground_truth() LANGUAGE plpgsql AS $gt$
DECLARE p record;
BEGIN
  FOR p IN SELECT idx FROM plan ORDER BY num, leg LOOP
    EXECUTE format('REINDEX /* wiki_btmaint_oracle */ INDEX %I', p.idx);
    UPDATE truth SET bytes_fresh = pg_relation_size(p.idx::regclass)
     WHERE idx = p.idx;
  END LOOP;
END $gt$;

-- The verdict view. actual_pct is what the rebuild of the churned file gave
-- back, measured, and is the only oracle. expected_stage recomputes the gate
-- from the recorded baseline, independently of the filed text.
CREATE OR REPLACE VIEW verdicts AS
SELECT p.num, p.leg, p.grp, p.idx, p.req, p.want_stage,
       ct.relname                                            AS tbl,
       -- A fixture whose shared-definition precondition was not met scores
       -- nothing; every count below that says "scored" filters on this.
       (pc.met IS DISTINCT FROM false)                        AS scored,
       pc.observed                                            AS precond_observed,
       -- The maintenance the assumption credits, and the no-defeat proofs.
       (m.tbl IS NOT NULL)                                    AS maintained,
       m.dead_not_removable, m.removed AS maint_removed,
       m.dead_after, m.mods_before, m.mods_after, m.timeouts,
       q.deleted_pages, q.empty_pages, q.avg_leaf_density AS density_after_maint,
       t.action, t.baseline, t.wasted_pct, t.reindexed_by_heuristic,
       bu.bytes AS bytes_built, ic.bytes AS bytes_init,
       t.bytes_churned, t.bytes_applied, t.bytes_fresh,
       round(100.0 * (t.bytes_churned - t.bytes_fresh)
             / GREATEST(t.bytes_churned, 1), 1)                  AS actual_pct,
       round(100.0 * (t.bytes_churned - t.bytes_applied)
             / GREATEST(t.bytes_churned, 1), 1)                  AS applied_pct,
       ic.base_bytes AS base_bytes, ic.base_tuples AS base_tuples,
       ch.tbl_tuples AS churned_tuples,
       CASE WHEN ic.base_bytes > 0
            THEN round(ch.bytes / ic.base_bytes, 4) END          AS size_ratio,
       CASE WHEN ic.base_tuples > 0
            THEN round(ch.tbl_tuples / ic.base_tuples, 4) END    AS tuple_ratio,
       -- The index's own entry count: the baseline the payload stored, the
       -- count the catalog holds after the churn, and their ratio.  The
       -- payload value is what the heuristic reads; ic.idx_tuples is the live
       -- catalog value at baseline time, so the two must agree.
       ic.base_idx_tuples, ch.idx_tuples AS churned_idx_tuples,
       (ic.base_idx_tuples = round(ic.idx_tuples))               AS itup_stored_matches,
       CASE WHEN ic.base_idx_tuples > 0
            THEN round(ch.idx_tuples / ic.base_idx_tuples, 4) END AS idx_tuple_ratio,
       -- Which of the three gates fires, each recomputed here from the
       -- recorded baseline, independently of the filed text.
       (ic.base_bytes > 0 AND ch.bytes >= ic.base_bytes * 1.20)  AS size_gate_fires,
       (ch.tbl_tuples >= 0 AND ic.base_tuples >= 0
        AND (CASE WHEN ic.base_tuples = 0 THEN ch.tbl_tuples > 0
                  ELSE abs(ch.tbl_tuples - ic.base_tuples)
                       >= ic.base_tuples * 0.20 END))            AS tbl_gate_fires,
       (ch.idx_tuples >= 0 AND ic.base_idx_tuples >= 0
        AND (CASE WHEN ic.base_idx_tuples = 0 THEN ch.idx_tuples > 0
                  ELSE abs(ch.idx_tuples - ic.base_idx_tuples)
                       >= ic.base_idx_tuples * 0.20 END))        AS idx_gate_fires,
       -- The sz the report proposed to store, against the sz that was stored.
       substring(t.cmd_report from '"sz":([0-9]+)')::numeric      AS sz_reported,
       substring(t.cmd_written from '"sz":([0-9]+)')::numeric     AS sz_written,
       substring(t.cmd_written from '"itup":(-?[0-9]+)')::numeric AS itup_written,
       CASE WHEN ic.payload IS NULL                              THEN 'initialize'
            WHEN ic.base_bytes IS NULL OR ic.base_tuples IS NULL
              OR ic.base_idx_tuples IS NULL                      THEN 'initialize'
            WHEN ic.base_bytes > 0 AND ch.bytes < ic.base_bytes  THEN 'refresh'
            WHEN ic.base_bytes > 0 AND ch.bytes >= ic.base_bytes * 1.20
                                                                 THEN 'measure'
            WHEN ch.tbl_tuples >= 0 AND ic.base_tuples > 0
             AND abs(ch.tbl_tuples - ic.base_tuples) >= ic.base_tuples * 0.20
                                                                 THEN 'measure'
            WHEN ch.tbl_tuples >= 0 AND ic.base_tuples = 0 AND ch.tbl_tuples > 0
                                                                 THEN 'measure'
            WHEN ch.idx_tuples >= 0 AND ic.base_idx_tuples > 0
             AND abs(ch.idx_tuples - ic.base_idx_tuples) >= ic.base_idx_tuples * 0.20
                                                                 THEN 'measure'
            WHEN ch.idx_tuples >= 0 AND ic.base_idx_tuples = 0 AND ch.idx_tuples > 0
                                                                 THEN 'measure'
            ELSE 'skip' END                                      AS expected_stage,
       -- The two-gate form this page filed before the index count was stored,
       -- recomputed on the same fixtures so the change can be quantified.
       CASE WHEN ic.payload IS NULL                              THEN 'initialize'
            WHEN ic.base_bytes IS NULL OR ic.base_tuples IS NULL THEN 'initialize'
            WHEN ic.base_bytes > 0 AND ch.bytes < ic.base_bytes  THEN 'refresh'
            WHEN ic.base_bytes > 0 AND ch.bytes >= ic.base_bytes * 1.20
                                                                 THEN 'measure'
            WHEN ch.tbl_tuples >= 0 AND ic.base_tuples > 0
             AND abs(ch.tbl_tuples - ic.base_tuples) >= ic.base_tuples * 0.20
                                                                 THEN 'measure'
            WHEN ch.tbl_tuples >= 0 AND ic.base_tuples = 0 AND ch.tbl_tuples > 0
                                                                 THEN 'measure'
            ELSE 'skip' END                                      AS two_gate_stage,
       CASE WHEN t.action IN ('reindex', 'update') THEN 'measure'
            ELSE t.action END                                    AS taken_stage,
       -- The rebuild oracle against the 40 % decision.  A fixture whose
       -- precondition was not met is reported and not scored, which is what
       -- the shared definition requires of test 120.
       CASE WHEN pc.met = false                                  THEN 'UNMET PRECONDITION'
            WHEN t.action IS NULL                                THEN 'ABSENT'
            WHEN t.action = 'reindex'
             AND round(100.0 * (t.bytes_churned - t.bytes_fresh)
                       / GREATEST(t.bytes_churned, 1), 1) < 10    THEN 'CRITICAL FALSE POSITIVE'
            WHEN t.action = 'reindex'
             AND round(100.0 * (t.bytes_churned - t.bytes_fresh)
                       / GREATEST(t.bytes_churned, 1), 1) < 35    THEN 'FALSE POSITIVE'
            WHEN t.action <> 'reindex'
             AND round(100.0 * (t.bytes_churned - t.bytes_fresh)
                       / GREATEST(t.bytes_churned, 1), 1) >= 50   THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END                                      AS verdict,
       -- Where a false negative was lost: the gate never measured, or the
       -- measurement read 40 % or less on a file a rebuild did shrink.
       CASE WHEN t.action IN ('skip', 'initialize', 'refresh')
             AND round(100.0 * (t.bytes_churned - t.bytes_fresh)
                       / GREATEST(t.bytes_churned, 1), 1) >= 50   THEN 'gate'
            WHEN t.action = 'update'
             AND round(100.0 * (t.bytes_churned - t.bytes_fresh)
                       / GREATEST(t.bytes_churned, 1), 1) >= 50   THEN 'threshold'
            ELSE NULL END                                        AS lost_by,
       t.notes, p.note
  FROM plan p
  LEFT JOIN truth t ON t.idx = p.idx
  LEFT JOIN snap bu ON bu.phase = 'built'   AND bu.idx = p.idx
  LEFT JOIN snap ic ON ic.phase = 'init'    AND ic.idx = p.idx
  LEFT JOIN snap ch ON ch.phase = 'churned' AND ch.idx = p.idx
  -- The fixture's table, so that the maintenance row can be joined to it.  A
  -- plain REINDEX keeps the index's pg_class row, so these names still resolve
  -- after the oracle has rebuilt every fixture.
  LEFT JOIN pg_class ci ON ci.relname = p.idx AND ci.relkind = 'i'
  LEFT JOIN pg_index xi ON xi.indexrelid = ci.oid
  LEFT JOIN pg_class ct ON ct.oid = xi.indrelid
  LEFT JOIN maint m     ON m.tbl = ct.relname
  LEFT JOIN pageclass q ON q.idx = p.idx
  LEFT JOIN precond pc  ON pc.num = p.num AND pc.leg = p.leg;
HARNESS
  cat > "$SQLD/fixtures_build.sql" <<'FIXTURES_BUILD'
-- The numbered suite, build phase: every fixture up to and including the
-- creation of the index that is scored.  The churn file carries the rest of
-- each recipe, so that the heuristic can store a baseline for a freshly built
-- index and then be asked about the same index after it has been disturbed.
--
-- Disposable fixtures.  Everything below creates, forges and drops objects in
-- the suite database of the sandbox cluster.  It is not meant for a database
-- anyone cares about.
--
-- The recipes are the numbered fixtures of the wiki's shared definition,
-- "Mandatory B-Tree Bloat Tests": tests 1-17 (deduplication gate), 18-91
-- (partial indexes) and controls 92-120, less the numbers that page retired -
-- 11, 38, 65, 67, 69, 106, 117 and 121, and legs 113a and 113c.  Retired
-- numbers are not reused and their recipes are gone from this file.
--
-- Two deviations, both deliberate: pg_stat_force_next_flush() is not called,
-- because this heuristic reads pg_class.reltuples and never a cumulative
-- statistics view; and the support-function-4 and ICU fixtures live in their
-- own files, because those features do not exist in every server this text has
-- to run on.  The shared definition's maintenance assumption is applied, but
-- not here: this file ends at each CREATE INDEX, the churn file carries the
-- writes, and the maintenance step that follows it vacuums and analyzes every
-- table those writes touched.
SET /* wiki_btmaint_fixtures_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_fixtures_statement_timeout */ statement_timeout = '900s';
SET /* wiki_btmaint_fixtures_lock_timeout */ lock_timeout = '5s';
SET /* wiki_btmaint_fixtures_maintenance_work_mem */ maintenance_work_mem = '256MB';

-- ======================================================== tests 1-17 ========
-- The deduplication gate's two 500,000-row tables and its custom operator
-- classes.  For this heuristic the group asks a different question than it did
-- for the estimator: every equal-image class must survive the same 90 % drain
-- and be measured, and the 40 % decision must agree with a rebuild.
--
-- Every fixture that needs a B-tree support function 4 lives in the
-- PostgreSQL 13 file, because support function 4 is the deduplication
-- equal-image callback: a 12 server answers "invalid function number 4, must
-- be between 1 and 3" and the whole file would abort here.  What stays is the
-- one custom operator class that declares no support function 4 at all.
CREATE OPERATOR CLASS int4_ei_none FOR TYPE int4 USING btree AS
  OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
  OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
  FUNCTION 1 btint4cmp(int4,int4);

CREATE TABLE t AS
SELECT i::int4 AS u, (i % 5000)::int4 AS a, (i % 5000)::int8 AS b,
       'key' || lpad((i % 5000)::text, 8, '0') AS s, ((i % 5000)::numeric) AS n,
       (i % 5000)::float4 AS f4, (i % 5000)::float8 AS f8, (i % 7)::int4 AS d
  FROM generate_series(1, 500000) i;
CREATE TABLE t2 AS
SELECT i::int4 AS u, (i % 5000)::int4 AS a, (i % 5000)::int8 AS b,
       'key' || lpad((i % 5000)::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE t;
ANALYZE t2;

CREATE INDEX i_int4          ON t (a);
CREATE INDEX i_int8          ON t (b);
CREATE INDEX i_text_det      ON t (s);
CREATE INDEX i_numeric       ON t (n);
CREATE INDEX i_float4        ON t (f4);
CREATE INDEX i_float8        ON t (f8);
CREATE INDEX i_multi_ok      ON t (a, b);
CREATE INDEX i_multi_bad     ON t (a, n);
CREATE INDEX i_expr_num      ON t ((a::numeric));
CREATE INDEX i_inc           ON t (a) INCLUDE (d);
CREATE INDEX i_ei_none       ON t (a int4_ei_none);
CREATE UNIQUE INDEX i_uniq   ON t (u);
CREATE INDEX i2_ok           ON t2 (a, b);

SELECT plan_add(1,  'gate', 'int4 key, 100 rows per key', 'i_int4', 'measure', 'i_int4');
SELECT plan_add(2,  'gate', 'int8 key, 100 rows per key', 'i_int8', 'measure', 'i_int8');
SELECT plan_add(3,  'gate', 'text key, deterministic default collation', 'i_text_det', 'measure', 'i_text_det');
SELECT plan_add(5,  'gate', 'numeric key, no equal-image support', 'i_numeric', 'measure', 'i_numeric');
SELECT plan_add(6,  'gate', 'float4 key', 'i_float4', 'measure', 'i_float4');
SELECT plan_add(6,  'gate', 'float8 key', 'i_float8', 'measure', 'i_float8');
SELECT plan_add(7,  'gate', 'two equal-image key columns', 'i_multi_ok', 'measure', 'i_multi_ok');
SELECT plan_add(8,  'gate', 'one non-equal-image key column', 'i_multi_bad', 'measure', 'i_multi_bad');
SELECT plan_add(9,  'gate', 'expression key, numeric', 'i_expr_num', 'measure', 'i_expr_num');
SELECT plan_add(10, 'gate', 'INCLUDE column refuses deduplication', 'i_inc', 'measure', 'i_inc');
SELECT plan_add(12, 'gate', 'opclass with no support function 4', 'i_ei_none', 'measure', 'i_ei_none');
SELECT plan_add(17, 'gate', 'unique key control; carried to the 12 leg as test 17', 'i_uniq', 'measure', 'i_uniq');
SELECT plan_add(7,  'gate', 'second table, two equal-image columns', 'i2_ok', 'measure', 'i2_ok');

-- ======================================================= tests 18-21 ========
CREATE TABLE pt1 AS
SELECT i::bigint AS k, (i % 100)::int AS sel FROM generate_series(1, 1000000) i;
ANALYZE pt1;
CREATE INDEX p18 ON pt1 (k) WHERE sel < 20;
CREATE INDEX p19 ON pt1 (k) WHERE sel < 1;
CREATE INDEX p20 ON pt1 (k) WHERE sel < 10;
CREATE INDEX p21 ON pt1 (k) WHERE sel < 80;
SELECT plan_add(18, 'partial', 'baseline, subset distribution = table (20%)', 'p18', 'measure');
SELECT plan_add(19, 'partial', 'very selective, ~1%', 'p19', 'measure');
SELECT plan_add(20, 'partial', 'moderately selective, ~10%', 'p20', 'measure');
SELECT plan_add(21, 'partial', 'large subset, ~80%', 'p21', 'measure');

-- ======================================================= tests 22-33 ========
CREATE TABLE pd22 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd22;
CREATE INDEX p22 ON pd22 (k) WHERE hot;
SELECT plan_add(22, 'partial', 'highly duplicated subset, unique outside', 'p22', 'measure');

CREATE TABLE pd23 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE ((i / 5) % 100)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd23;
CREATE INDEX p23 ON pd23 (k) WHERE hot;
SELECT plan_add(23, 'partial', 'highly unique subset, duplicated outside', 'p23', 'measure');

CREATE TABLE pd24 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50000)::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd24;
CREATE INDEX p24 ON pd24 (k) WHERE hot;
SELECT plan_add(24, 'partial', 'n_distinct radically different in the subset', 'p24', 'measure');

CREATE TABLE pd25 AS SELECT (i % 100 = 0) AS hot,
       CASE WHEN i % 100 = 0 THEN ((i / 100) % 997)::int ELSE (i % 5)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd25;
CREATE INDEX p25 ON pd25 (k) WHERE hot;
SELECT plan_add(25, 'partial', 'MCV distribution differs inside the subset', 'p25', 'measure');

CREATE TABLE pd26 AS SELECT (i % 50 = 0) AS hot,
       CASE WHEN i % 50 = 0 THEN (1000000 + i)::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd26;
CREATE INDEX p26 ON pd26 (k) WHERE hot;
SELECT plan_add(26, 'partial', 'table-wide MCVs absent inside the subset', 'p26', 'measure');

CREATE TABLE pd27 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 AND i % 100 <> 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd27;
CREATE INDEX p27 ON pd27 (k) WHERE hot;
SELECT plan_add(27, 'partial', 'NULL-heavy subset, non-NULL outside', 'p27', 'measure');

CREATE TABLE pd28 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN i::bigint ELSE NULL END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd28;
CREATE INDEX p28 ON pd28 (k) WHERE hot;
SELECT plan_add(28, 'partial', 'NULL-free subset, NULL-heavy table (bigint)', 'p28', 'measure');

CREATE TABLE pd29 AS
SELECT CASE WHEN i % 5 = 0 THEN NULL ELSE lpad(i::text, 20, '0') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE pd29;
CREATE INDEX p29 ON pd29 (s) WHERE s IS NULL;
SELECT plan_add(29, 'partial', 'all-NULL partial index, WHERE s IS NULL', 'p29', 'skip');

CREATE TABLE pd30 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE pd30;
CREATE INDEX p30 ON pd30 (s) WHERE hot;
SELECT plan_add(30, 'partial', 'subset values wider than outside (13 against 204 bytes)', 'p30', 'measure');

CREATE TABLE pd31 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN lpad((i % 9)::text, 12, 'n')
            ELSE repeat('W', 190) || lpad(i::text, 10, '0') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE pd31;
CREATE INDEX p31 ON pd31 (s) WHERE hot;
SELECT plan_add(31, 'partial', 'subset values narrower than outside', 'p31', 'measure');

CREATE TABLE pw32 AS
SELECT (i % 50 = 0) AS hot,
       CASE WHEN i % 50 = 0 THEN repeat('W', 390) || lpad(i::text, 10, '0')
            ELSE repeat('n', 18) || (i % 9)::text END AS s
  FROM generate_series(1, 500000) i;
ANALYZE pw32;
CREATE INDEX p32 ON pw32 (s) WHERE hot;
SELECT plan_add(32, 'partial', 'extreme width mismatch (27 against 404 bytes)', 'p32', 'measure');

CREATE TABLE pd33 AS SELECT (i % 5 = 0) AS hot,
       lpad(i::text, 10 + (i % 40), 'x') AS s FROM generate_series(1, 500000) i;
ANALYZE pd33;
CREATE INDEX p33 ON pd33 (s) WHERE hot;
SELECT plan_add(33, 'partial', 'variable-width values, same range inside and out', 'p33', 'measure');

-- ======================================================= tests 34-39 ========
CREATE TABLE pd34 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd34;
CREATE INDEX p34 ON pd34 (k) WHERE hot;
SELECT plan_add(34, 'partial', 'dedup-heavy subset, 1000 rows per key', 'p34', 'measure');

CREATE TABLE pd35 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd35;
CREATE INDEX p35 ON pd35 (k) WHERE hot;
SELECT plan_add(35, 'partial', 'duplicate-heavy table, unique subset', 'p35', 'measure');

CREATE TABLE pd36 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN 42 ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd36;
CREATE INDEX p36 ON pd36 (k) WHERE hot;
SELECT plan_add(36, 'partial', 'one key group, 100,000 TIDs against a 132 cap', 'p36', 'measure');

CREATE TABLE pd37 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd37;
CREATE INDEX p37 ON pd37 (k) WHERE hot;
SELECT plan_add(37, 'partial', 'NULL deduplication, every subset key NULL', 'p37', 'measure');

CREATE TABLE pd39 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pd39;
CREATE UNIQUE INDEX p39 ON pd39 (k) WHERE hot;
SELECT plan_add(39, 'partial', 'partial UNIQUE index', 'p39', 'measure');

-- ======================================================= tests 40-47 ========
CREATE TABLE pd40 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 97)::int  END AS b
  FROM generate_series(1, 500000) i;
ANALYZE pd40;
CREATE INDEX p40 ON pd40 (a, b) WHERE hot;
SELECT plan_add(40, 'partial', 'two-column key correlated only in the subset', 'p40', 'measure');

CREATE TABLE pd41 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 97)::int  ELSE (i % 100)::int END AS b
  FROM generate_series(1, 500000) i;
ANALYZE pd41;
CREATE INDEX p41 ON pd41 (a, b) WHERE hot;
SELECT plan_add(41, 'partial', 'two-column key independent only in the subset', 'p41', 'measure');

CREATE TABLE pd42 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50)::int ELSE i::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50)::int ELSE i::int END AS b
  FROM generate_series(1, 500000) i;
ANALYZE pd42;
CREATE INDEX p42 ON pd42 (a, b) WHERE hot;
SELECT plan_add(42, 'partial', 'multi-column duplicate keys in the subset', 'p42', 'measure');

CREATE TABLE pd43 AS SELECT (i % 5 = 0) AS hot, i::int AS a, (i * 2)::int AS b
  FROM generate_series(1, 500000) i;
ANALYZE pd43;
CREATE INDEX p43 ON pd43 (a, b) WHERE hot;
SELECT plan_add(43, 'partial', 'multi-column unique keys in the subset', 'p43', 'measure');

CREATE TABLE pd44a AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
ANALYZE pd44a;
CREATE INDEX p44a ON pd44a (a, b) WHERE hot;
SELECT plan_add(44, 'partial', 'multicolumn key, no ndistinct object', 'p44a', 'measure', 'a');
CREATE TABLE pd44b AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS pd44b_nd (ndistinct) ON a, b FROM pd44b;
ANALYZE pd44b;
CREATE INDEX p44b ON pd44b (a, b) WHERE hot;
SELECT plan_add(44, 'partial', 'multicolumn key, with CREATE STATISTICS (ndistinct)', 'p44b', 'measure', 'b');

CREATE TABLE pd45 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 97)::int  ELSE (i % 100)::int END AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS pd45_nd (ndistinct) ON a, b FROM pd45;
ANALYZE pd45;
CREATE INDEX p45 ON pd45 (a, b) WHERE hot;
SELECT plan_add(45, 'partial', 'extended statistics wrong for the subset', 'p45', 'measure');

CREATE TABLE pd46 AS SELECT (i % 5 = 0) AS hot, i::int AS k, (i % 7)::int AS pay
  FROM generate_series(1, 500000) i;
ANALYZE pd46;
CREATE INDEX p46 ON pd46 (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(46, 'partial', 'partial index with INCLUDE columns', 'p46', 'measure');

CREATE TABLE pi47 AS SELECT (i % 20 = 0) AS hot, i::int AS k,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS payload
  FROM generate_series(1, 500000) i;
ANALYZE pi47;
CREATE INDEX p47 ON pi47 (k) INCLUDE (payload) WHERE hot;
SELECT plan_add(47, 'partial', 'wide INCLUDE values inside the subset', 'p47', 'measure');

-- ======================================================= tests 48-55 ========
CREATE TABLE pe48 AS SELECT (i % 5 = 0) AS active,
       CASE WHEN i % 5 = 0 THEN 'NAME' || lpad(((i / 5) % 20)::text, 6, '0')
            ELSE 'name' || lpad((i % 100)::text, 6, '0') END AS name
  FROM generate_series(1, 500000) i;
ANALYZE pe48;
CREATE INDEX p48 ON pe48 (lower(name)) WHERE active;
SELECT plan_add(48, 'partial', 'partial expression index, lower(name) WHERE active', 'p48', 'measure');
CREATE TABLE pe48b AS SELECT (i % 5 = 0) AS active,
       CASE WHEN i % 5 = 0 THEN 'NAME' || lpad(((i / 5) % 20)::text, 6, '0')
            ELSE 'name' || lpad((i % 100)::text, 6, '0') END AS name
  FROM generate_series(1, 500000) i;
CREATE INDEX p48b ON pe48b (lower(name)) WHERE active;
ANALYZE pe48b;
SELECT plan_add(48, 'partial', 'the same after one ANALYZE with the index in place', 'p48b', 'measure', 'b');

CREATE TABLE pe49 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE pe49;
CREATE INDEX p49 ON pe49 (upper(s)) WHERE hot;
SELECT plan_add(49, 'partial', 'expression width mismatch in the subset', 'p49', 'measure');
CREATE TABLE pe49b AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX p49b ON pe49b (upper(s)) WHERE hot;
ANALYZE pe49b;
SELECT plan_add(49, 'partial', 'the same after one ANALYZE with the index in place', 'p49b', 'measure', 'b');

CREATE TABLE pe50 AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE pe50;
CREATE INDEX p50 ON pe50 (upper(s)) WHERE hot;
SELECT plan_add(50, 'partial', 'missing expression statistics, 32-byte fallback', 'p50', 'measure');
CREATE TABLE pe50b AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX p50b ON pe50b (upper(s)) WHERE hot;
ANALYZE pe50b;
SELECT plan_add(50, 'partial', 'the same after one ANALYZE with the index in place', 'p50b', 'measure', 'b');

CREATE TABLE pf AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pf;
CREATE INDEX p53 ON pf (k) WHERE hot;
CREATE INDEX p54 ON pf (k) WITH (fillfactor = 100) WHERE hot;
CREATE INDEX p55 ON pf (k) WITH (fillfactor = 70)  WHERE hot;
SELECT plan_add(53, 'partial', 'default fillfactor 90', 'p53', 'measure');
SELECT plan_add(54, 'partial', 'fillfactor = 100', 'p54', 'measure');
SELECT plan_add(55, 'partial', 'fillfactor = 70', 'p55', 'measure');

-- ======================================================= tests 56-63 ========
CREATE TABLE ps AS
SELECT (i % 5 = 0) AS flag,
       CASE WHEN i % 5 = 0 THEN 'OPEN' ELSE 'CLOSED' END AS status,
       timestamptz '2020-01-01' + (i * interval '1 minute') AS created,
       CASE WHEN i % 5 = 0 THEN NULL ELSE i::int END AS nk,
       i::int AS k, (i % 1000)::int AS k2
  FROM generate_series(1, 500000) i;
ANALYZE ps;
CREATE INDEX p56 ON ps (k) WHERE flag;
CREATE INDEX p57 ON ps (k) WHERE status = 'OPEN';
CREATE INDEX p58 ON ps (k) WHERE created >= timestamptz '2020-09-01';
CREATE INDEX p59 ON ps (k) WHERE nk IS NULL;
CREATE INDEX p60 ON ps (k) WHERE nk IS NOT NULL;
CREATE INDEX p61 ON ps (k) WHERE flag AND status = 'OPEN';
CREATE INDEX p62 ON ps (k) WHERE k < 100000;
CREATE INDEX p63 ON ps (k2) WHERE k >= 400000;
SELECT plan_add(56, 'partial', 'boolean predicate, WHERE flag', 'p56', 'measure');
SELECT plan_add(57, 'partial', 'equality predicate, status = OPEN', 'p57', 'measure');
SELECT plan_add(58, 'partial', 'range predicate, created >= ...', 'p58', 'measure');
SELECT plan_add(59, 'partial', 'IS NULL predicate on a non-key column', 'p59', 'measure');
SELECT plan_add(60, 'partial', 'IS NOT NULL predicate', 'p60', 'measure');
SELECT plan_add(61, 'partial', 'multi-column predicate', 'p61', 'measure');
SELECT plan_add(62, 'partial', 'predicate correlated with the indexed value', 'p62', 'measure');
SELECT plan_add(63, 'partial', 'predicate negatively correlated with the value', 'p63', 'measure');

-- ==================================================== tests 64, 66, 68 ======
-- 65, 67 and 69 are retired by the shared definition: each withheld a VACUUM,
-- or the ANALYZE after one, and withheld maintenance is no longer a fixture
-- shape.  Their numbers are not reused.
CREATE TABLE pc64 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pc64;
CREATE INDEX p64 ON pc64 (k) WHERE hot;
SELECT plan_add(64, 'partial', 'stale statistics after inserts into the subset', 'p64', 'measure');

CREATE TABLE pc66 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pc66;
CREATE INDEX p66 ON pc66 (k) WHERE hot;
SELECT plan_add(66, 'partial', 'rows entering the index (false -> true)', 'p66', 'measure');

CREATE TABLE pc68 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pc68;
CREATE INDEX p68 ON pc68 (k) WHERE hot;
SELECT plan_add(68, 'partial', 'heavy predicate churn, then VACUUM + ANALYZE', 'p68', 'measure');

-- ======================================================= tests 70-77 ========
CREATE TABLE pb AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE pb;
CREATE INDEX p70 ON pb (k) WHERE hot;
SELECT plan_add(70, 'partial', 'freshly created partial index', 'p70', 'skip');
CREATE INDEX p71 ON pb (k) WHERE hot;
SELECT plan_add(71, 'partial', 'freshly REINDEXed partial index', 'p71', 'skip');

CREATE TABLE pb72 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE pb72;
CREATE INDEX p72 ON pb72 (k) WHERE hot;
SELECT plan_add(72, 'partial', '25% of the subset deleted', 'p72', 'measure');

CREATE TABLE pb73 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE pb73;
CREATE INDEX p73 ON pb73 (k) WHERE hot;
SELECT plan_add(73, 'partial', '50% of the subset deleted', 'p73', 'measure');

CREATE TABLE pb74 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE pb74;
CREATE INDEX p74 ON pb74 (k) WHERE hot;
SELECT plan_add(74, 'partial', '75% of the subset deleted', 'p74', 'measure');

CREATE TABLE pb75 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE pb75;
CREATE INDEX p75 ON pb75 (k) WHERE hot;
SELECT plan_add(75, 'partial', '90% of the subset deleted (corrected recipe)', 'p75', 'measure');

CREATE TABLE pb76 AS SELECT (i % 5 = 0) AS hot, i::int AS k, 'x'::text AS pad
  FROM generate_series(1, 500000) i;
ANALYZE pb76;
CREATE INDEX p76 ON pb76 (k) WHERE hot;
SELECT plan_add(76, 'partial', 'bloated through indexed-key UPDATEs', 'p76', 'measure');

CREATE TABLE pb77 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE pb77;
CREATE INDEX p77 ON pb77 (k) WHERE hot;
SELECT plan_add(77, 'partial', 'many empty and deleted B-tree pages', 'p77', 'measure');

-- ======================================================= tests 78-85 ========
CREATE TABLE f78t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 290) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE f78t;
CREATE INDEX f78 ON f78t (s) WHERE hot;
SELECT plan_add(78, 'falsepos', 'predicate-conditioned width mismatch', 'f78', 'skip');

CREATE TABLE f79t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('t', 300) || lpad(i::text, 4, '0')
            ELSE NULL END AS s
  FROM generate_series(1, 500000) i;
ANALYZE f79t;
CREATE INDEX f79 ON f79t (s) WHERE hot;
SELECT plan_add(79, 'falsepos', 'predicate-conditioned NULL mismatch', 'f79', 'skip');

CREATE TABLE f80t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE f80t;
CREATE INDEX f80 ON f80t (k) WHERE hot;
SELECT plan_add(80, 'falsepos', 'predicate-conditioned n_distinct mismatch', 'f80', 'skip');

CREATE TABLE f81t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 20)::int ELSE 7 END AS k
  FROM generate_series(1, 500000) i;
ANALYZE f81t;
CREATE INDEX f81 ON f81t (k) WHERE hot;
SELECT plan_add(81, 'falsepos', 'predicate-conditioned MCV mismatch', 'f81', 'skip');

CREATE TABLE f82t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 89)::int  END AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS f82_nd (ndistinct) ON a, b FROM f82t;
ANALYZE f82t;
CREATE INDEX f82 ON f82t (a, b) WHERE hot;
SELECT plan_add(82, 'falsepos', 'predicate-conditioned multi-column correlation', 'f82', 'skip');

CREATE TABLE f83t AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE f83t;
CREATE INDEX f83 ON f83t (md5(s), lower(s)) WHERE hot;
SELECT plan_add(83, 'falsepos', 'missing index/expression statistics', 'f83', 'skip');

CREATE TABLE f84t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE f84t;
CREATE INDEX f84 ON f84t (k) WHERE hot;
SELECT plan_add(84, 'falsepos', 'stale partial-index reltuples', 'f84', 'skip');

CREATE TABLE f85t AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE f85t;
UPDATE f85t SET s = repeat('W', 200) || s WHERE hot;
VACUUM f85t;
CREATE INDEX f85 ON f85t (s) WHERE hot;
SELECT plan_add(85, 'falsepos', 'stale table statistics', 'f85', 'skip');

-- ======================================================= tests 86-91 ========
CREATE TABLE f86t AS SELECT (i % 5 = 0) AS hot, ((i / 5) % 100)::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE f86t;
CREATE INDEX f86 ON f86t (k) WHERE hot;
SELECT plan_add(86, 'falseneg', 'duplicate concentration inside the subset', 'f86', 'measure');

CREATE TABLE f87t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
ANALYZE f87t;
CREATE INDEX f87 ON f87t (k) WHERE hot;
SELECT plan_add(87, 'falseneg', 'NULL concentration inside the subset', 'f87', 'measure');

CREATE TABLE f88t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN lpad((i % 9)::text, 9, '0')
            ELSE repeat('W', 390) || lpad(i::text, 10, '0') END AS s
  FROM generate_series(1, 200000) i;
ANALYZE f88t;
CREATE INDEX f88 ON f88t (s) WHERE hot;
SELECT plan_add(88, 'falseneg', 'subset narrower than table statistics', 'f88', 'measure');

CREATE TABLE f89t AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
ANALYZE f89t;
CREATE INDEX f89 ON f89t (a, b) WHERE hot;
SELECT plan_add(89, 'falseneg', 'conditional multi-column correlation', 'f89', 'measure');

CREATE TABLE f90t AS SELECT (i % 5 = 0) AS hot, ((i / 5) % 1000)::int AS k
  FROM generate_series(1, 500000) i;
ANALYZE f90t;
CREATE INDEX f90 ON f90t (k) WHERE hot;
SELECT plan_add(90, 'falseneg', 'real deduplication stronger than predicted', 'f90', 'measure');

CREATE TABLE f91t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN lpad((i % 9)::text, 9, '0')
            ELSE repeat('W', 390) || lpad(i::text, 10, '0') END AS s,
       i::int AS ord
  FROM generate_series(1, 200000) i;
ANALYZE f91t;
CREATE INDEX f91 ON f91t (s) WHERE hot;
SELECT plan_add(91, 'falseneg', 'many deleted pages plus an over-predicting model', 'f91', 'measure');

-- ====================================================== tests 92-95 =========
CREATE TABLE b92t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE b92t;
CREATE INDEX b92 ON b92t (k) WHERE hot;
SELECT plan_add(92, 'control', '1,000 rows updated under the old GUC threshold', 'b92', 'measure');

CREATE TABLE b93t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
ANALYZE b93t;
CREATE INDEX b93 ON b93t (k) WHERE hot;
SELECT plan_add(93, 'control', 'rows updated above the old GUC threshold', 'b93', 'measure');

CREATE TABLE b94t (hot bool, k int)
  WITH (autovacuum_analyze_threshold = 100, autovacuum_analyze_scale_factor = 0);
INSERT INTO b94t SELECT (i % 5 = 0), i FROM generate_series(1, 500000) i;
ANALYZE b94t;
CREATE INDEX b94 ON b94t (k) WHERE hot;
SELECT plan_add(94, 'control', '1,000 rows updated, table reloption threshold 100', 'b94', 'measure');

CREATE TABLE b95t (hot bool, k int)
  WITH (autovacuum_analyze_threshold = 200000, autovacuum_analyze_scale_factor = 1);
INSERT INTO b95t SELECT (i % 5 = 0), i FROM generate_series(1, 500000) i;
ANALYZE b95t;
CREATE INDEX b95 ON b95t (k) WHERE hot;
SELECT plan_add(95, 'control', 'many rows updated, table reloption threshold 200,000', 'b95', 'measure');

-- ====================================================== tests 96-99 =========
CREATE TABLE np AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE np;
CREATE INDEX np96 ON np (k);
CREATE INDEX np97 ON np (upper(s));
SELECT plan_add(96, 'control', 'plain index, fresh statistics', 'np96', 'skip');
SELECT plan_add(97, 'control', 'expression index, no statistics row', 'np97', 'skip');

CREATE TABLE np98t AS SELECT i::int AS k FROM generate_series(1, 500000) i;
ANALYZE np98t;
CREATE INDEX np98 ON np98t (k);
SELECT plan_add(98, 'control', 'plain index, stale row counts after 300,000 inserts', 'np98', 'measure');

CREATE TABLE np99t AS SELECT (i % 1000)::int AS k FROM generate_series(1, 500000) i;
ANALYZE np99t;
CREATE INDEX np99 ON np99t (k);
SELECT plan_add(99, 'control', 'duplicate-heavy index, genuinely reclaimable', 'np99', 'measure');

-- ===================================================== tests 100-105 ========
CREATE TABLE i100t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
ANALYZE i100t;
CREATE INDEX i100 ON i100t (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(100, 'control', 'partial + INCLUDE (text), 90% of the subset deleted', 'i100', 'measure');

CREATE TABLE i101t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
ANALYZE i101t;
CREATE INDEX i101 ON i101t (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(101, 'control', 'partial + INCLUDE (text), same width inside and outside', 'i101', 'skip');

CREATE TABLE i102t AS SELECT i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
ANALYZE i102t;
CREATE INDEX i102 ON i102t (k) INCLUDE (pay);
SELECT plan_add(102, 'control', 'non-partial + wide INCLUDE (text), freshly built', 'i102', 'skip');

CREATE TABLE i103t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad(i::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
ANALYZE i103t;
CREATE INDEX i103 ON i103t (s) WHERE hot;
SELECT plan_add(103, 'control', 'partial + wide key column, unique values', 'i103', 'skip');

CREATE TABLE i104t AS SELECT (i % 20 = 0) AS hot, i::int AS k,
       CASE WHEN i % 20 = 0 THEN lpad((i % 9)::text, 12, 'n')
            ELSE repeat('W', 190) || lpad(i::text, 10, '0') END AS pay
  FROM generate_series(1, 500000) i;
ANALYZE i104t;
CREATE INDEX i104 ON i104t (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(104, 'control', 'partial + INCLUDE (text) narrower inside the subset', 'i104', 'skip');

CREATE TABLE i105t AS SELECT (i % 20 = 0) AS hot, i::int AS k, (i % 7)::int AS n,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS pay
  FROM generate_series(1, 500000) i;
ANALYZE i105t;
CREATE INDEX i105 ON i105t (k) INCLUDE (n, pay) WHERE hot;
SELECT plan_add(105, 'control', 'partial + INCLUDE (int, text), mixed non-key widths', 'i105', 'skip');

-- ===================================================== tests 107-112 ========
-- 106 is retired by the shared definition: its recipe ended on a VACUUM with
-- no ANALYZE after it.  Its number is not reused.
CREATE TABLE x107t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE x107t;
CREATE INDEX x107 ON x107t (upper(s));
SELECT plan_add(107, 'control', 'the same, with one ANALYZE after the build', 'x107', 'measure');

CREATE TABLE x108t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX x108 ON x108t (upper(s));
SELECT plan_add(108, 'control', 'expression index on a never-analysed table', 'x108', 'skip');

CREATE TABLE x109t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ALTER TABLE x109t ALTER COLUMN s SET STATISTICS 0;
ANALYZE x109t;
CREATE INDEX x109 ON x109t (s);
SELECT plan_add(109, 'control', 'plain index, key column with SET STATISTICS 0', 'x109', 'skip');

CREATE TABLE x110t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE x110t;
CREATE INDEX x110 ON x110t (k, upper(s));
SELECT plan_add(110, 'control', 'mixed key (k, upper(s)), no statistics row', 'x110', 'skip');

CREATE TABLE x111t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE x111t;
CREATE INDEX x111 ON x111t (left(s, 3));
SELECT plan_add(111, 'control', 'narrow expression left(s, 3), no statistics row', 'x111', 'skip');

CREATE TABLE x112t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE x112t;
CREATE INDEX x112 ON x112t (upper(s)) WHERE hot;
SELECT plan_add(112, 'control', 'partial expression index, no statistics row', 'x112', 'skip');

-- ===================================================== tests 113-120 ========
-- Legs 113a and 113c, and numbers 117 and 121, are retired by the shared
-- definition: 113a and 117 drained an index without vacuuming it, 113c and
-- 121 left the count a VACUUM or a TRUNCATE wrote with no ANALYZE after it.
-- Only leg 113b remains, and the retired numbers are not reused.
CREATE TABLE q113b AS SELECT i::int AS id, 'pending'::text AS state
  FROM generate_series(1, 1000000) i;
ANALYZE q113b;
CREATE INDEX p113b ON q113b (id) WHERE state = 'pending';
SELECT plan_add(113, 'zero', 'drained queue, VACUUM + ANALYZE', 'p113b', 'skip', 'b');

CREATE TABLE q114 AS SELECT i::int AS id, 'pending'::text AS state
  FROM generate_series(1, 1000000) i;
ANALYZE q114;
CREATE INDEX p114 ON q114 (id) WHERE state = 'pending';
SELECT plan_add(114, 'zero', 'queue drained to 1%, VACUUM + ANALYZE', 'p114', 'skip');

CREATE TABLE q115(id int, state text);
ANALYZE q115;
CREATE INDEX p115 ON q115 (id) WHERE state = 'pending';
SELECT plan_add(115, 'zero', 'index built on an analysed empty table, then loaded', 'p115', 'measure');

CREATE TABLE q116 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p116 ON q116 (id) WHERE state = 'pending';
ANALYZE q116;
SELECT plan_add(116, 'zero', 'subset empty from the start and measured empty', 'p116', 'skip');

CREATE TABLE q118 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p118 ON q118 (id) WHERE state = 'pending';
ANALYZE q118;
SELECT plan_add(118, 'zero', 'subset measured empty, then 50,000 rows arrive', 'p118', 'skip');

CREATE TABLE q119 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p119 ON q119 (id) WHERE state = 'pending';
ANALYZE q119;
SELECT plan_add(119, 'zero', 'fixture 118 after one ANALYZE', 'p119', 'skip');

CREATE TABLE q120 AS SELECT i::int AS id,
       CASE WHEN i <= 2000 THEN 'pending' ELSE 'done' END::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p120 ON q120 (id) WHERE state = 'pending';
SET default_statistics_target = 1;
ANALYZE q120;
RESET default_statistics_target;
SELECT plan_add(120, 'zero', 'a 300-row sample missed a 2,000-row subset', 'p120', 'skip');

SELECT count(*) AS planned_fixtures FROM plan;
FIXTURES_BUILD
  cat > "$SQLD/fixtures_v13.sql" <<'FIXTURES_V13'
-- Build phase, every fixture that needs a feature PostgreSQL 12 does not have.
-- One family is left: B-tree support function 4, the deduplication
-- equal-image callback.  A 12 server refuses "FUNCTION 4" in CREATE OPERATOR
-- CLASS outright, and has no btequalimage or btvarstrequalimage to alias, so
-- tests 13, 14, 15 and 16 are skipped there.
--
-- The deduplicate_items fixtures that used to share this file, test 11 and
-- test 38, are retired by the shared definition: explicitly enabling or
-- disabling deduplication is outside the mandatory suite.  Their numbers are
-- not reused, and the reloption is now probed by stage_facts only.
--
-- This file runs only where server_version_num >= 130000; otherwise the
-- fixtures are recorded as skipped and the suite is scored without them.
-- Disposable fixtures, in the sandbox cluster's suite database only.
SET /* wiki_btmaint_v13_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_v13_statement_timeout */ statement_timeout = '900s';
SET /* wiki_btmaint_v13_lock_timeout */ lock_timeout = '5s';
SET /* wiki_btmaint_v13_maintenance_work_mem */ maintenance_work_mem = '256MB';

CREATE OR REPLACE FUNCTION ei_true(oid)  RETURNS bool LANGUAGE sql IMMUTABLE AS $$ SELECT true $$;
CREATE OR REPLACE FUNCTION ei_false(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS $$ SELECT false $$;
CREATE OR REPLACE FUNCTION ei_alias(oid) RETURNS bool LANGUAGE internal IMMUTABLE AS 'btequalimage';
CREATE OR REPLACE FUNCTION ei_renamed(oid) RETURNS bool LANGUAGE internal IMMUTABLE AS 'btvarstrequalimage';
-- test 16, the impostor: a SQL function wearing the built-in's name.  It must
-- be schema-qualified in the operator class or pg_catalog wins the lookup.
CREATE OR REPLACE FUNCTION public.btequalimage(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS $$ SELECT true $$;

CREATE OPERATOR CLASS int4_ei_true FOR TYPE int4 USING btree AS
  OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
  OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
  FUNCTION 1 btint4cmp(int4,int4), FUNCTION 4 ei_true(oid);
CREATE OPERATOR CLASS int4_ei_false FOR TYPE int4 USING btree AS
  OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
  OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
  FUNCTION 1 btint4cmp(int4,int4), FUNCTION 4 ei_false(oid);
CREATE OPERATOR CLASS int4_ei_alias FOR TYPE int4 USING btree AS
  OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
  OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
  FUNCTION 1 btint4cmp(int4,int4), FUNCTION 4 ei_alias(oid);
CREATE OPERATOR CLASS int8_ei_true FOR TYPE int8 USING btree AS
  OPERATOR 1 <(int8,int8), OPERATOR 2 <=(int8,int8), OPERATOR 3 =(int8,int8),
  OPERATOR 4 >=(int8,int8), OPERATOR 5 >(int8,int8),
  FUNCTION 1 btint8cmp(int8,int8), FUNCTION 4 ei_true(oid);
CREATE OPERATOR CLASS int8_ei_false FOR TYPE int8 USING btree AS
  OPERATOR 1 <(int8,int8), OPERATOR 2 <=(int8,int8), OPERATOR 3 =(int8,int8),
  OPERATOR 4 >=(int8,int8), OPERATOR 5 >(int8,int8),
  FUNCTION 1 btint8cmp(int8,int8), FUNCTION 4 ei_false(oid);
CREATE OPERATOR CLASS text_squat FOR TYPE text USING btree AS
  OPERATOR 1 <(text,text), OPERATOR 2 <=(text,text), OPERATOR 3 =(text,text),
  OPERATOR 4 >=(text,text), OPERATOR 5 >(text,text),
  FUNCTION 1 bttextcmp(text,text), FUNCTION 4 public.btequalimage(oid);
CREATE OPERATOR CLASS text_renamed FOR TYPE text USING btree AS
  OPERATOR 1 <(text,text), OPERATOR 2 <=(text,text), OPERATOR 3 =(text,text),
  OPERATOR 4 >=(text,text), OPERATOR 5 >(text,text),
  FUNCTION 1 bttextcmp(text,text), FUNCTION 4 ei_renamed(oid);

CREATE INDEX i_ei_false  ON t (a int4_ei_false);
CREATE INDEX i_ei_true   ON t (a int4_ei_true);
CREATE INDEX i_ei_alias  ON t (a int4_ei_alias);
CREATE INDEX i_mixed_tf  ON t (a int4_ei_true, b int8_ei_false);
CREATE INDEX i_mixed_ft  ON t (a int4_ei_false, b int8_ei_true);
CREATE INDEX i_squat     ON t (s text_squat);
CREATE INDEX i_text_det2 ON t (s text_renamed);
CREATE INDEX i2_tf       ON t2 (a int4_ei_true, b int8_ei_false);
CREATE INDEX i2_ft       ON t2 (a int4_ei_false, b int8_ei_true);
SELECT plan_add(13, 'gate', 'support function 4 returns false', 'i_ei_false', 'measure', 'i_ei_false');
SELECT plan_add(14, 'gate', 'support function 4 returns true by design', 'i_ei_true', 'measure', 'i_ei_true');
SELECT plan_add(14, 'gate', 'internal alias of btequalimage', 'i_ei_alias', 'measure', 'i_ei_alias');
SELECT plan_add(15, 'gate', 'mixed true/false support functions', 'i_mixed_tf', 'measure', 'i_mixed_tf');
SELECT plan_add(15, 'gate', 'mixed false/true support functions', 'i_mixed_ft', 'measure', 'i_mixed_ft');
SELECT plan_add(16, 'gate', 'SQL impostor named btequalimage', 'i_squat', 'measure', 'i_squat');
SELECT plan_add(16, 'gate', 'renamed internal support function 4', 'i_text_det2', 'measure', 'i_text_det2');
SELECT plan_add(15, 'gate', 'second table, mixed true/false', 'i2_tf', 'measure', 'i2_tf');
SELECT plan_add(15, 'gate', 'second table, mixed false/true', 'i2_ft', 'measure', 'i2_ft');
FIXTURES_V13
  cat > "$SQLD/fixtures_icu.sql" <<'FIXTURES_ICU'
-- Build phase, the four ICU fixtures: tests 3, 4, 9 and 51-52.  A server built
-- --without-icu cannot create these collations, so this file runs only where
-- CREATE COLLATION (provider = icu) succeeds and the fixtures are otherwise
-- recorded as skipped.
-- Disposable fixtures, in the sandbox cluster's suite database only.
SET /* wiki_btmaint_icu_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_icu_statement_timeout */ statement_timeout = '900s';
SET /* wiki_btmaint_icu_lock_timeout */ lock_timeout = '5s';

CREATE COLLATION ci   (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
CREATE COLLATION cdet (provider = icu, locale = 'und');

CREATE INDEX i_text_icu_det  ON t (s COLLATE cdet);
CREATE INDEX i_text_nondet   ON t (s COLLATE ci);
CREATE INDEX i_expr_lower_ci ON t ((lower(s)) COLLATE ci);
SELECT plan_add(3, 'gate', 'text key, deterministic ICU collation', 'i_text_icu_det', 'measure', 'i_text_icu_det');
SELECT plan_add(4, 'gate', 'text key, nondeterministic ICU collation', 'i_text_nondet', 'measure', 'i_text_nondet');
SELECT plan_add(9, 'gate', 'expression key under a nondeterministic collation', 'i_expr_lower_ci', 'measure', 'i_expr_lower_ci');

CREATE COLLATION suite_det    (provider = icu, locale = 'und');
CREATE COLLATION suite_nondet (provider = icu, locale = 'und-u-ks-level2',
                               deterministic = false);
CREATE TABLE pc51 AS SELECT (i % 5 = 0) AS hot,
       'key' || lpad(((i / 5) % 100)::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;
ANALYZE pc51;
CREATE INDEX p51 ON pc51 (s COLLATE suite_det) WHERE hot;
CREATE INDEX p52 ON pc51 (s COLLATE suite_nondet) WHERE hot;
SELECT plan_add(51, 'partial', 'deterministic ICU collation', 'p51', 'measure');
SELECT plan_add(52, 'partial', 'nondeterministic ICU collation', 'p52', 'measure');
FIXTURES_ICU
  cat > "$SQLD/fixtures_churn.sql" <<'FIXTURES_CHURN'
-- The numbered suite, churn phase: everything each recipe does after its index
-- exists, run after the heuristic has stored an as-built baseline in every
-- index comment.  Two kinds of churn:
--
--   1. the recipe's own, transcribed verbatim from the numbered fixtures;
--   2. a uniform 90 % block drain for the shape fixtures that have no churn of
--      their own, because a fixture designed for a one-shot estimator never
--      needed a "before" and an "after".
--
-- The fixtures whose whole point is that a fresh index must not be touched are
-- deliberately left alone: 70-71, 78-85, 96-97, 101-105, 108-112, 116 and 120.
--
-- The maintenance the assumption credits is NOT here: the drain below deletes
-- and stops, and every churned table is vacuumed and analyzed by the
-- maintenance step that follows this file, in a session whose timeouts are all
-- zero and whose VERBOSE output is captured.  A recipe's own VACUUM or ANALYZE
-- stays where the numbered fixture put it, because that is the recipe.
--
-- Every settable timeout this server has is zero, for the same reason the
-- autovacuum launcher and worker set them to zero on themselves: this file
-- issues maintenance statements, and a timeout firing inside one would leave a
-- fixture neither churned nor maintained, which the shared definition's
-- no-defeat rule forbids.  There are three here rather than four, because
-- transaction_timeout arrived in PostgreSQL 17.  The trade-off is that a
-- runaway statement here has no guard but the run's own supervision.
--
-- Disposable fixtures, in the sandbox cluster's suite database only.
SET /* wiki_btmaint_churn_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_churn_statement_timeout */ statement_timeout = 0;
SET /* wiki_btmaint_churn_lock_timeout */ lock_timeout = 0;
SET /* wiki_btmaint_churn_idle_timeout */ idle_in_transaction_session_timeout = 0;

-- ---------------------------------------------------------- recipe churn ----
-- 64: stale statistics after inserts into the subset.
INSERT INTO pc64 SELECT true, 500000 + i FROM generate_series(1, 200000) i;

-- 66: rows entering the index (false -> true).
UPDATE pc66 SET hot = true WHERE NOT hot AND k % 5 = 1;

-- 68: heavy predicate churn, then VACUUM + ANALYZE.
UPDATE pc68 SET hot = true  WHERE k % 3 = 0;
UPDATE pc68 SET hot = false WHERE k % 3 = 0;
UPDATE pc68 SET hot = true  WHERE k % 3 = 1;
UPDATE pc68 SET hot = false WHERE k % 3 = 1;
UPDATE pc68 SET hot = (k % 10 = 0);
VACUUM pc68;
ANALYZE pc68;

-- 71: a REINDEX nobody told the heuristic about.
REINDEX INDEX p71;

-- 72-75: a quarter, a half, three quarters and nine tenths of the subset.
DELETE FROM pb72 WHERE hot AND (k / 5) % 4 = 0;
VACUUM pb72;
ANALYZE pb72;
DELETE FROM pb73 WHERE hot AND (k / 5) % 2 = 0;
VACUUM pb73;
ANALYZE pb73;
DELETE FROM pb74 WHERE hot AND (k / 5) % 4 <> 0;
VACUUM pb74;
ANALYZE pb74;
DELETE FROM pb75 WHERE hot AND (k / 5) % 10 <> 0;
VACUUM pb75;
ANALYZE pb75;

-- 76: bloated through indexed-key UPDATEs.
UPDATE pb76 SET k = k + 1000000 WHERE hot;
VACUUM pb76;
ANALYZE pb76;

-- 77: many empty and deleted B-tree pages, contiguous 95 %.
DELETE FROM pb77 WHERE hot AND k < 475000;
VACUUM pb77;
ANALYZE pb77;

-- 84's forged partial-index reltuples has moved to forge.sql, which runs after
-- the simulated auto-analyze, because an ANALYZE of its table would overwrite
-- the forgery and the fixture would stop testing anything.

-- 86-91: genuinely bloated, VACUUMed and ANALYZEd.
DELETE FROM f86t WHERE hot AND k >= 25;
VACUUM f86t;
ANALYZE f86t;
DELETE FROM f87t WHERE hot AND k IS NOT NULL;
VACUUM f87t;
ANALYZE f87t;
DELETE FROM f88t WHERE hot AND s > lpad('4', 9, '0');
VACUUM f88t;
ANALYZE f88t;
DELETE FROM f89t WHERE hot AND a >= 25;
VACUUM f89t;
ANALYZE f89t;
DELETE FROM f90t WHERE hot AND k >= 250;
VACUUM f90t;
ANALYZE f90t;
DELETE FROM f91t WHERE hot AND ord < 190000;
VACUUM f91t;
ANALYZE f91t;

-- 92-95: a reclaimable partial index, then a known number of row changes.
DELETE FROM b92t WHERE hot AND (k / 5) % 10 <> 0;
VACUUM b92t;
ANALYZE b92t;
UPDATE b92t SET k = k WHERE k % 500 = 0;
DELETE FROM b93t WHERE hot AND (k / 5) % 10 <> 0;
VACUUM b93t;
ANALYZE b93t;
UPDATE b93t SET k = k WHERE k % 2 = 0;
DELETE FROM b94t WHERE hot AND (k / 5) % 10 <> 0;
VACUUM b94t;
ANALYZE b94t;
UPDATE b94t SET k = k WHERE k % 500 = 0;
DELETE FROM b95t WHERE hot AND (k / 5) % 10 <> 0;
VACUUM b95t;
ANALYZE b95t;
UPDATE b95t SET k = k WHERE k % 2 = 0;

-- 98: 300,000 inserts and no ANALYZE.
INSERT INTO np98t SELECT 500000 + i FROM generate_series(1, 300000) i;

-- 99: duplicate-heavy, genuinely reclaimable.
DELETE FROM np99t WHERE k >= 60;
VACUUM np99t;
ANALYZE np99t;

-- 100: partial + INCLUDE, 90 % of the subset deleted.
DELETE FROM i100t WHERE hot AND (k / 5) % 10 <> 0;
VACUUM i100t;
ANALYZE i100t;

-- 107: an expression index, 90 % deleted, then VACUUM and ANALYZE.
DELETE FROM x107t WHERE k % 10 <> 0;
VACUUM x107t;
ANALYZE x107t;

-- 113b: the drained queue, vacuumed and analyzed.  Legs a and c are retired.
UPDATE q113b SET state = 'done';
VACUUM q113b;
ANALYZE q113b;

-- 114: drained to 1 %.
UPDATE q114 SET state = 'done' WHERE id % 100 <> 0;
VACUUM q114;
ANALYZE q114;

-- 115: an index built on an analysed empty table, then loaded.
INSERT INTO q115 SELECT i, 'pending' FROM generate_series(1, 1000000) i;

-- 118, 119: the subset was empty at the last ANALYZE, then rows arrived.
INSERT INTO q118 SELECT 1000000 + i, 'pending' FROM generate_series(1, 50000) i;
INSERT INTO q119 SELECT 1000000 + i, 'pending' FROM generate_series(1, 50000) i;
ANALYZE q119;

-- ------------------------------------------------------- the uniform drain ---
-- 90 % of the heap blocks of every shape fixture that has no churn of its own.
-- The maintenance VACUUM and ANALYZE that turn those dead entries into empty
-- and deleted index pages are no longer here: they are the maintenance step
-- that runs after this file, over every table these deletes touched, with its
-- timeouts at zero and its VERBOSE output recorded.  The deletes are still
-- generated and executed one statement at a time, because the drain predicate
-- has to be applied per table.
SELECT /* wiki_btmaint_drain_generator */ format(st.tmpl, tb.name)
  FROM (VALUES (1, 't'), (2, 't2'), (3, 'pt1'), (4, 'pd22'), (5, 'pd23'),
               (6, 'pd24'), (7, 'pd25'), (8, 'pd26'), (9, 'pd27'), (10, 'pd28'),
               (11, 'pd29'), (12, 'pd30'), (13, 'pd31'), (14, 'pw32'),
               (15, 'pd33'), (16, 'pd34'), (17, 'pd35'), (18, 'pd36'),
               (19, 'pd37'), (20, 'pd39'), (21, 'pd40'), (22, 'pd41'),
               (23, 'pd42'), (24, 'pd43'), (25, 'pd44a'), (26, 'pd44b'),
               (27, 'pd45'), (28, 'pd46'), (29, 'pi47'), (30, 'pe48'),
               (31, 'pe48b'), (32, 'pe49'), (33, 'pe49b'), (34, 'pe50'),
               (35, 'pe50b'), (36, 'pf'), (37, 'ps')) tb(n, name)
 CROSS JOIN (VALUES
        (1, 'DELETE /* wiki_btmaint_drain */ FROM %I WHERE ((ctid::text::point)[0])::int %% 10 <> 0')) st(k, tmpl)
 ORDER BY tb.n, st.k
\gexec
FIXTURES_CHURN
  cat > "$SQLD/churn_icu.sql" <<'CHURN_ICU'
-- Churn phase for the ICU fixtures, drained like the other shape fixtures.
-- The maintenance VACUUM ANALYZE is the maintenance step's, not this file's.
-- Disposable, suite database of the sandbox cluster only.
SET /* wiki_btmaint_churnicu_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_churnicu_statement_timeout */ statement_timeout = 0;
SET /* wiki_btmaint_churnicu_lock_timeout */ lock_timeout = 0;
SELECT /* wiki_btmaint_drainicu_generator */ format(st.tmpl, tb.name)
  FROM (VALUES (1, 'pc51')) tb(n, name)
 CROSS JOIN (VALUES
        (1, 'DELETE /* wiki_btmaint_drain */ FROM %I WHERE ((ctid::text::point)[0])::int %% 10 <> 0')) st(k, tmpl)
 ORDER BY tb.n, st.k
\gexec
CHURN_ICU
  cat > "$SQLD/churn_seen.sql" <<'CHURN_SEEN'
-- Every fixture table's write counters at one point in the run, recorded once
-- before the first churn statement and once after the last.  Run with
-- -v phase=before and -v phase=after.  The difference is what defines "the
-- tables the churn touched", which is the set the maintenance assumption
-- applies to; using the engine's own counters keeps the set out of a
-- hand-written list that a new fixture could silently fall out of.
SET /* wiki_btmaint_churnseen_client_min_messages */ client_min_messages = warning;
DELETE FROM churn_seen WHERE phase = :'phase';
INSERT /* wiki_btmaint_churn_seen */ INTO churn_seen(phase, tbl, ins, upd, del,
                                                    mods, dead, last_analyze)
SELECT :'phase', c.relname, st.n_tup_ins, st.n_tup_upd, st.n_tup_del,
       st.n_mod_since_analyze, st.n_dead_tup, st.last_analyze
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
 WHERE st.schemaname = 'public'
   AND c.relkind = 'r'
   AND c.relname NOT IN ('plan', 'snap', 'truth', 'autoanl', 'autoanl_after',
                         'churn_seen', 'maint', 'horizon', 'pageclass',
                         'precond');
SELECT /* wiki_btmaint_churn_seen_count */
       :'phase' || ': ' || count(*) || ' tables recorded'
  FROM churn_seen WHERE phase = :'phase';
CHURN_SEEN
  cat > "$SQLD/maint.sql" <<'MAINT'
-- The maintenance step: the VACUUM ANALYZE the shared definition's maintenance
-- assumption requires after every churn, on every table the churn touched, and
-- the four proofs its no-defeat rule asks for.
--
-- The table set is computed, not listed: a table is maintained when its
-- insert, update or delete counter moved across the churn phase.  A fixture
-- with no churn is therefore not touched here, which matters - an extra
-- ANALYZE would repair the deliberately stale statistics of family 3 and of
-- controls 108 to 112, and an extra VACUUM would change a deliberately fresh
-- index.  Those fixtures carry their build-phase ANALYZE into the decide phase
-- instead, exactly as the shared definition says they do.
--
-- Every settable timeout this server has is zero, which is what the autovacuum
-- launcher and worker do to themselves so that these settings cannot stop
-- regular maintenance.  There are three rather than four: transaction_timeout
-- arrived in PostgreSQL 17.  The values in force are recorded per row rather
-- than assumed.  VERBOSE is on so that each statement's own count of dead row
-- versions that cannot be removed yet is in the output; INFO messages reach
-- the client whatever client_min_messages says.
-- Disposable fixtures, suite database of the sandbox cluster only.
SET /* wiki_btmaint_maint_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_maint_statement_timeout */ statement_timeout = 0;
SET /* wiki_btmaint_maint_lock_timeout */ lock_timeout = 0;
SET /* wiki_btmaint_maint_idle_timeout */ idle_in_transaction_session_timeout = 0;

DELETE FROM maint;
INSERT /* wiki_btmaint_maint_rows */ INTO maint
       (tbl, ord, ins, upd, del, mods_before, dead_before, analyzed_in_churn,
        timeouts)
SELECT a.tbl,
       row_number() OVER (ORDER BY a.tbl)::int,
       a.ins - b.ins, a.upd - b.upd, a.del - b.del, a.mods, a.dead,
       -- A recipe that analyzed its own table after its own writes leaves the
       -- modification counter at zero legitimately: the churn was published
       -- and then consumed.  Recording which tables those are is what keeps a
       -- zero counter from being read as a churn that never reached the
       -- statistics entry at all.
       (a.last_analyze IS NOT NULL
        AND (b.last_analyze IS NULL OR a.last_analyze > b.last_analyze)),
       'statement_timeout=' || current_setting('statement_timeout') ||
       ' lock_timeout=' || current_setting('lock_timeout') ||
       ' idle_in_transaction_session_timeout='
         || current_setting('idle_in_transaction_session_timeout')
  FROM churn_seen a
  JOIN churn_seen b ON b.tbl = a.tbl AND b.phase = 'before'
 WHERE a.phase = 'after'
   AND (a.ins - b.ins) + (a.upd - b.upd) + (a.del - b.del) > 0;

SELECT /* wiki_btmaint_maint_planned */ count(*) || ' tables to maintain, '
       || count(*) FILTER (WHERE analyzed_in_churn)
       || ' already analyzed by their own recipe, '
       || count(*) FILTER (WHERE COALESCE(mods_before, 0) = 0
                             AND NOT analyzed_in_churn)
       || ' with an unpublished churn counter'
  FROM maint;

-- One probe, one start stamp, one VACUUM (VERBOSE, ANALYZE) and one end stamp
-- per table, generated and executed one statement at a time because VACUUM
-- cannot run inside a transaction block.
SELECT /* wiki_btmaint_maint_generator */ format(st.tmpl, m.tbl)
  FROM maint m
 CROSS JOIN (VALUES
        (1, 'SELECT /* wiki_btmaint_horizon_before */ horizon_probe(''maint'', %1$L)'),
        (2, 'UPDATE /* wiki_btmaint_maint_start */ maint SET started = clock_timestamp() WHERE tbl = %1$L'),
        (3, 'VACUUM /* wiki_btmaint_maint */ (VERBOSE, ANALYZE) %1$I'),
        (4, 'UPDATE /* wiki_btmaint_maint_end */ maint SET ended = clock_timestamp() WHERE tbl = %1$L')
       ) st(k, tmpl)
 ORDER BY m.ord, st.k
\gexec
MAINT
  cat > "$SQLD/maint_after.sql" <<'MAINT_AFTER'
-- What the maintenance left behind, read from a new session a second later so
-- that a 12 server's statistics collector has published the VACUUM and the
-- ANALYZE.  dead_after is the dead-tuple count the engine reports for the
-- table; mods_after is the modification counter the ANALYZE half reset.
SET /* wiki_btmaint_maintafter_client_min_messages */ client_min_messages = warning;
UPDATE /* wiki_btmaint_maint_after */ maint m
   SET mods_after = st.n_mod_since_analyze,
       dead_after = st.n_dead_tup
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
 WHERE st.schemaname = 'public' AND c.relname = m.tbl;
SELECT /* wiki_btmaint_horizon_after_maint */ horizon_probe('post-maint', NULL);
SELECT /* wiki_btmaint_maint_summary */
       'maintained ' || count(*) || ' tables, '
       || count(*) FILTER (WHERE ended IS NOT NULL) || ' completed, '
       || count(*) FILTER (WHERE COALESCE(dead_after, 0) > 0)
       || ' still holding dead tuples, '
       || count(*) FILTER (WHERE COALESCE(mods_after, 0) > 0)
       || ' with a non-zero modification counter'
  FROM maint;
MAINT_AFTER
  cat > "$SQLD/precond.sql" <<'PRECOND'
-- The preconditions the shared definition puts on a numbered fixture, checked
-- after the census rather than assumed.  Test 120 is the suite's one
-- probabilistic fixture: its point is a 300-row sample that missed a 2,000-row
-- subset, so its partial index's own reltuples must still read 0 when the
-- method is asked.  A run that finds a non-zero estimate scores nothing from
-- the fixture, which is what the shared definition says, and what the previous
-- run of this page counted as a PASS.
SET /* wiki_btmaint_precond_client_min_messages */ client_min_messages = warning;
DELETE FROM precond;
INSERT /* wiki_btmaint_precond_120 */ INTO precond(num, leg, requirement, observed, met)
SELECT 120, '', 'post-census reltuples of p120 must be 0',
       'p120 reltuples = ' || c.reltuples::text, (c.reltuples = 0)
  FROM pg_class c WHERE c.relname = 'p120';
SELECT /* wiki_btmaint_precond_report */
       num || ': ' || requirement || ' -> ' || observed ||
       ' (' || CASE WHEN met THEN 'met' ELSE 'NOT MET, scores nothing' END || ')'
  FROM precond ORDER BY num, leg;
PRECOND
  cat > "$SQLD/pageclass.sql" <<'PAGECLASS'
-- The page classes of every fixture index after the maintenance step.  Deleted
-- and half-dead pages are the visible trace of what the maintenance did, and a
-- drained fixture whose index has neither is the shape a defeated VACUUM
-- leaves behind.  Read-only: pgstatindex opens every page of every index it is
-- called on and writes nothing, so the decide phase that follows sees exactly
-- the state the maintenance left.
SET /* wiki_btmaint_pageclass_client_min_messages */ client_min_messages = warning;
DELETE FROM pageclass;
INSERT /* wiki_btmaint_pageclass */ INTO pageclass
       (idx, leaf_pages, empty_pages, deleted_pages, avg_leaf_density, index_size)
SELECT p.idx, m.leaf_pages, m.empty_pages, m.deleted_pages,
       CASE WHEN m.avg_leaf_density = 'NaN'::float8 THEN NULL
            ELSE round(m.avg_leaf_density::numeric, 2) END,
       m.index_size
  FROM plan p, LATERAL pgstatindex(p.idx::regclass) m;
SELECT /* wiki_btmaint_pageclass_report */
       count(*) || ' indexes read, '
       || count(*) FILTER (WHERE deleted_pages > 0) || ' with deleted pages, '
       || count(*) FILTER (WHERE empty_pages > 0) || ' with half-dead pages, '
       || COALESCE(sum(deleted_pages), 0) || ' deleted pages in total'
  FROM pageclass;
PAGECLASS
  cat > "$SQLD/autoanalyze.sql" <<'AUTOANALYZE'
-- The simulated auto-analyze, and the mandatory-test rule behind it: a fixture
-- that changes more than 10 % of a table's heap tuples must ANALYZE it, because
-- on a server with autovacuum on the launcher would have.
--
-- The trigger is not hand-written per fixture.  It is the engine's own test,
-- n_mod_since_analyze > autovacuum_analyze_threshold +
-- autovacuum_analyze_scale_factor * reltuples, which is exactly what
-- relation_needs_vacanalyze() compares; at the defaults that is 50 + 10 % of
-- the table's estimated row count.  autovacuum is off in this cluster, so no
-- background worker can have analyzed anything, and every ANALYZE below is one
-- this fixture set asked for.
--
-- Both counter states are recorded: autoanl holds what the churn left behind,
-- autoanl_after holds the same counters once the ANALYZEs have run, which is
-- how the run proves the simulation actually fired.
--
-- With the maintenance step in front of it, this census finds every churned
-- table freshly analyzed, so the tables it decides are the ones no churn
-- touched - a table whose build left it past the threshold, such as the
-- never-analysed table of control 108.  It is also the recheck that the
-- maintenance step's counters were published in the right order.
--
-- The census issues ANALYZE, which is a maintenance command, so its timeouts
-- are zero for the same reason the maintenance step's are, and it probes the
-- horizon on both sides of itself.
-- Disposable fixtures, suite database of the sandbox cluster only.
SET /* wiki_btmaint_autoanl_client_min_messages */ client_min_messages = warning;
SET /* wiki_btmaint_autoanl_statement_timeout */ statement_timeout = 0;
SET /* wiki_btmaint_autoanl_lock_timeout */ lock_timeout = 0;
SET /* wiki_btmaint_autoanl_idle_timeout */ idle_in_transaction_session_timeout = 0;

SELECT /* wiki_btmaint_horizon_before_census */ horizon_probe('census-before', NULL);

DROP TABLE IF EXISTS autoanl;
DROP TABLE IF EXISTS autoanl_after;
CREATE TABLE autoanl AS
SELECT /* wiki_btmaint_autoanalyze_census */
       c.relname                                   AS tbl,
       GREATEST(c.reltuples, 0)::numeric           AS reltuples,
       st.n_mod_since_analyze::numeric             AS mods,
       round(current_setting('autovacuum_analyze_threshold')::numeric
             + current_setting('autovacuum_analyze_scale_factor')::numeric
               * GREATEST(c.reltuples, 0)::numeric, 1) AS threshold,
       round(100 * st.n_mod_since_analyze
             / GREATEST(c.reltuples, 1)::numeric, 1)   AS mod_pct,
       (st.n_mod_since_analyze
        > current_setting('autovacuum_analyze_threshold')::numeric
          + current_setting('autovacuum_analyze_scale_factor')::numeric
            * GREATEST(c.reltuples, 0)::numeric)       AS would_autoanalyze
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
 WHERE st.schemaname = 'public'
   AND c.relkind = 'r'
   AND c.relname NOT IN ('plan', 'snap', 'truth', 'autoanl', 'autoanl_after',
                         'churn_seen', 'maint', 'horizon', 'pageclass',
                         'precond');

SELECT /* wiki_btmaint_autoanalyze_generator */
       format('ANALYZE /* wiki_btmaint_autoanalyze */ %I', tbl)
  FROM autoanl WHERE would_autoanalyze ORDER BY tbl
\gexec

AUTOANALYZE
  cat > "$SQLD/autoanalyze_after.sql" <<'AUTOANALYZE_AFTER'
-- The census's own recheck, in a session of its own a second later.  The delay
-- is not cosmetic: this file has to be able to see the counters the census's
-- ANALYZEs reset, and on this server the statistics a reader sees come from a
-- collector file that is written at most every half second, so a recheck run
-- immediately after the ANALYZE reads the state from before it.  A run that
-- reports "0 of 6 counters reset" is reporting that staleness, not a census
-- that did nothing.
SET /* wiki_btmaint_autoanlafter_client_min_messages */ client_min_messages = warning;
DROP TABLE IF EXISTS autoanl_after;
CREATE TABLE autoanl_after AS
SELECT /* wiki_btmaint_autoanalyze_recheck */
       c.relname AS tbl, st.n_mod_since_analyze::numeric AS mods,
       GREATEST(c.reltuples, 0)::numeric AS reltuples
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
 WHERE st.schemaname = 'public' AND c.relkind = 'r'
   AND c.relname IN (SELECT tbl FROM autoanl WHERE would_autoanalyze);

SELECT /* wiki_btmaint_horizon_after_census */ horizon_probe('census-after', NULL);
AUTOANALYZE_AFTER
  cat > "$SQLD/forge.sql" <<'FORGE'
-- The numbered suite's catalog forgeries, applied after the simulated
-- auto-analyze so that an ANALYZE cannot overwrite them.  Fixture 84 is a
-- partial index whose recorded entry count is deliberately wrong, which is now
-- an input the heuristic reads rather than one it ignores.
-- Disposable catalog forgery, suite database of the sandbox cluster only.
SET /* wiki_btmaint_forge_client_min_messages */ client_min_messages = warning;
UPDATE /* wiki_btmaint_forge_84 */ pg_class SET reltuples = 5000
 WHERE relname = 'f84';
SELECT /* wiki_btmaint_forge_check */ 'f84 reltuples now ' || reltuples
  FROM pg_class WHERE relname = 'f84';
FORGE
  note "$(ls -1 "$SQLD" | tr "\n" " ")"
}

# ---------------------------------------------------------------- texts ------
stage_texts() {
  say "the page's two texts, hashed, and the one-edit harness view"
  [ -f "$PAGE" ] || die "no page at $PAGE; set PAGE or run from the repository root"
  md_block sql 1 "$PAGE" > "$SQLD/report.sql"
  md_block sql 2 "$PAGE" > "$SQLD/apply.sql"
  [ -s "$SQLD/report.sql" ] || die "block 1 of $PAGE is empty"
  [ -s "$SQLD/apply.sql" ]  || die "block 2 of $PAGE is empty"
  : > "$OUT/hashes.txt"
  local h1 h2
  h1=$(sha256sum < "$SQLD/report.sql" | cut -d' ' -f1)
  h2=$(sha256sum < "$SQLD/apply.sql"  | cut -d' ' -f1)
  printf 'report %s %s\n' "$h1" \
    "$([ "$h1" = "$BASE_REPORT" ] && echo match || echo DIFFERS)" >> "$OUT/hashes.txt"
  printf 'apply  %s %s\n' "$h2" \
    "$([ "$h2" = "$BASE_APPLY" ] && echo match || echo DIFFERS)" >> "$OUT/hashes.txt"
  printf 'report lines=%s bytes=%s\n' "$(grep -c '' "$SQLD/report.sql")" \
    "$(wc -c < "$SQLD/report.sql")" >> "$OUT/hashes.txt"
  printf 'apply  lines=%s bytes=%s\n' "$(grep -c '' "$SQLD/apply.sql")" \
    "$(wc -c < "$SQLD/apply.sql")" >> "$OUT/hashes.txt"
  # The shared pipeline: from "WITH params AS (" through the end of the staged
  # CTE, which is where the two texts part company - step 1 goes on to measure
  # in SQL, step 2 hands the snapshot to its driver.  The page claims this
  # region is byte-identical in both; this is the check that makes the claim
  # auditable.
  sed -n '/^WITH params AS ($/,/^      FROM decided d$/p' \
      "$SQLD/report.sql" > "$OUT/pipeline_report.sql"
  sed -n '/^WITH params AS ($/,/^      FROM decided d$/p' \
      "$SQLD/apply.sql" > "$OUT/pipeline_apply.sql"
  printf 'pipeline report %s\npipeline apply  %s\npipeline lines  %s\n' \
    "$(sha256sum < "$OUT/pipeline_report.sql" | cut -d' ' -f1)" \
    "$(sha256sum < "$OUT/pipeline_apply.sql" | cut -d' ' -f1)" \
    "$(grep -c '' "$OUT/pipeline_report.sql")" >> "$OUT/hashes.txt"
  if cmp -s "$OUT/pipeline_report.sql" "$OUT/pipeline_apply.sql"; then
    printf 'pipeline identical yes\n' >> "$OUT/hashes.txt"
  else
    printf 'pipeline identical NO\n' >> "$OUT/hashes.txt"
    diff "$OUT/pipeline_report.sql" "$OUT/pipeline_apply.sql" > "$OUT/pipeline_diff.txt"
  fi
  plan_view "$SQLD/report.sql" > "$SQLD/plan_view.sql"
  cat "$OUT/hashes.txt" >&2
}

# ---------------------------------------------------------------- exact ------
# Step 8 of the sibling page's protocol, applied here: execute the exact filed
# texts on this server and record what happens, before any fixture exists and
# before anything is transformed.  Two small fixtures are created first, because
# a text that returns no rows proves nothing about whether its expressions ran.
stage_exact() {
  say "the exact filed texts, on this server, unmodified"
  : > "$OUT/exact.txt"
  q suite 'DROP TABLE IF EXISTS zz_exact CASCADE' > /dev/null 2>&1
  f suite /dev/stdin > /dev/null 2>&1 <<'SQL'
CREATE TABLE zz_exact AS SELECT i::int AS k, (i % 997)::int AS d
  FROM generate_series(1, 200000) i;
ANALYZE zz_exact;
CREATE INDEX zz_exact_k ON zz_exact (k);
CREATE INDEX zz_exact_d ON zz_exact (d);
COMMENT ON INDEX zz_exact_d IS 'a human note that must survive';
SQL
  local rc
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d suite -f "$SQLD/report.sql" \
    > "$OUT/exact_report.txt" 2>&1; rc=$?
  printf 'report exit=%s rows=%s\n' "$rc" \
    "$(grep -c '^ public' "$OUT/exact_report.txt")" >> "$OUT/exact.txt"
  grep -E 'ERROR|LINE' "$OUT/exact_report.txt" | head -3 >> "$OUT/exact.txt"
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite -f "$SQLD/apply.sql" \
    > "$OUT/exact_apply.txt" 2>&1; rc=$?
  printf 'apply  exit=%s %s\n' "$rc" "$(tail -1 "$OUT/exact_apply.txt")" >> "$OUT/exact.txt"
  grep -E 'ERROR|LINE' "$OUT/exact_apply.txt" | head -3 >> "$OUT/exact.txt"
  printf 'comment written: %s\n' \
    "$(s suite "SELECT replace(obj_description('zz_exact_d'::regclass, 'pg_class'),
                               chr(10), ' | ')")" >> "$OUT/exact.txt"
  printf 'second run: %s\n' \
    "$(f suite "$SQLD/apply.sql" 2>&1 | tail -1)" >> "$OUT/exact.txt"
  q suite 'DROP TABLE IF EXISTS zz_exact CASCADE' > /dev/null 2>&1
  cat "$OUT/exact.txt" >&2
}

# ---------------------------------------------------------------- facts ------
# Every version-local fact the two texts depend on, discovered on the running
# server rather than assumed.  The 12 leg runs the same stage, which is how the
# two servers are compared.
stage_facts() {
  say "version-local facts"
  : > "$OUT/facts.txt"
  local fact
  fact() { printf '%-34s %s\n' "$1" "$2" >> "$OUT/facts.txt"; }
  fact server_version_num "$(s suite 'SHOW server_version_num')"
  fact block_size "$(s suite 'SHOW block_size')"
  fact materialized_cte_accepted \
    "$(s suite 'WITH x AS MATERIALIZED (SELECT 1) SELECT count(*) FROM x' 2>&1 | tail -1)"
  fact pgstatindex_version \
    "$(s suite "SELECT extversion FROM pg_extension WHERE extname = 'pgstattuple'")"
  fact has_pg_input_is_valid \
    "$(s suite "SELECT count(*) FROM pg_proc WHERE proname = 'pg_input_is_valid'")"
  fact has_force_next_flush \
    "$(s suite "SELECT count(*) FROM pg_proc WHERE proname = 'pg_stat_force_next_flush'")"
  q suite 'DROP TABLE IF EXISTS zz_d' > /dev/null 2>&1
  q suite 'CREATE TABLE zz_d(k int)' > /dev/null
  fact deduplicate_items_reloption \
    "$(errf suite 'CREATE INDEX zz_di ON zz_d (k) WITH (deduplicate_items = off)')"
  q suite 'DROP TABLE IF EXISTS zz_d' > /dev/null 2>&1
  fact maintain_privilege \
    "$(errf suite "SELECT has_table_privilege('pg_class', 'MAINTAIN')")"
  fact icu_collation \
    "$(errf suite "CREATE COLLATION zz_icu (provider = icu, locale = 'und')")"
  q suite 'DROP COLLATION IF EXISTS zz_icu' > /dev/null 2>&1
  # reltuples on a table nothing has counted, and after each writer.
  q suite 'DROP TABLE IF EXISTS zz_rt' > /dev/null 2>&1
  q suite 'CREATE TABLE zz_rt(k int)' > /dev/null
  fact reltuples_after_create "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  q suite 'INSERT INTO zz_rt SELECT i FROM generate_series(1,1000) i' > /dev/null
  fact reltuples_after_insert "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  q suite 'CREATE INDEX zz_rt_k ON zz_rt (k)' > /dev/null
  fact reltuples_after_create_index "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  q suite 'ANALYZE zz_rt' > /dev/null
  fact reltuples_after_analyze "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  q suite 'TRUNCATE zz_rt' > /dev/null
  fact reltuples_after_truncate "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  q suite 'INSERT INTO zz_rt SELECT i FROM generate_series(1,2000) i' > /dev/null
  q suite 'REINDEX INDEX zz_rt_k' > /dev/null
  fact reltuples_after_reindex "$(s suite "SELECT reltuples FROM pg_class WHERE relname='zz_rt'")"
  # The index's own reltuples, which is the third gate input: who writes it,
  # what each writer writes, and what a partial index gets.  A plain index and
  # a partial index on the same 10,000-row table, where the predicate selects
  # exactly one row in five.
  fact autovacuum_analyze_threshold "$(s suite 'SHOW autovacuum_analyze_threshold')"
  fact autovacuum_analyze_scale_factor "$(s suite 'SHOW autovacuum_analyze_scale_factor')"
  q suite 'DROP TABLE IF EXISTS zz_it' > /dev/null 2>&1
  q suite 'CREATE TABLE zz_it AS SELECT i::int AS k, (i % 5 = 0) AS hot
             FROM generate_series(1,10000) i' > /dev/null
  q suite 'CREATE INDEX zz_it_all ON zz_it (k)' > /dev/null
  q suite 'CREATE INDEX zz_it_part ON zz_it (k) WHERE hot' > /dev/null
  local ir
  ir() { s suite "SELECT reltuples FROM pg_class WHERE relname='$1'"; }
  fact idx_reltuples_after_build "plain=$(ir zz_it_all) partial=$(ir zz_it_part)"
  q suite 'ANALYZE zz_it' > /dev/null
  fact idx_reltuples_after_analyze \
    "table=$(ir zz_it) plain=$(ir zz_it_all) partial=$(ir zz_it_part)"
  q suite 'DELETE FROM zz_it WHERE hot AND k % 50 <> 0' > /dev/null
  q suite 'VACUUM zz_it' > /dev/null
  fact idx_reltuples_after_vacuum \
    "table=$(ir zz_it) plain=$(ir zz_it_all) partial=$(ir zz_it_part)"
  q suite 'ANALYZE zz_it' > /dev/null
  fact idx_reltuples_after_analyze2 \
    "table=$(ir zz_it) plain=$(ir zz_it_all) partial=$(ir zz_it_part)"
  # A VACUUM with nothing to delete is cleanup-only, and an index AM that
  # reports an estimated count leaves pg_class alone: the count can therefore
  # be older than the last VACUUM.
  q suite 'UPDATE zz_it SET k = k + 100000 WHERE k % 1000 = 0' > /dev/null
  q suite 'VACUUM zz_it' > /dev/null
  fact idx_reltuples_after_small_vacuum \
    "table=$(ir zz_it) plain=$(ir zz_it_all) partial=$(ir zz_it_part)"
  q suite 'REINDEX INDEX zz_it_part' > /dev/null
  fact idx_reltuples_after_reindex "partial=$(ir zz_it_part)"
  q suite 'DROP TABLE IF EXISTS zz_it' > /dev/null 2>&1
  # Transaction control inside DO, which the apply block needs for its COMMIT,
  # and the two commands that cannot be reached from inside one.
  fact commit_inside_do \
    "$(errf suite 'DO $x$ BEGIN PERFORM 1; COMMIT; END $x$;')"
  fact commit_inside_do_in_xact \
    "$(errf suite 'BEGIN; DO $x$ BEGIN PERFORM 1; COMMIT; END $x$; COMMIT;')"
  fact reindex_plain_inside_do \
    "$(errf suite 'DO $x$ BEGIN EXECUTE $q$REINDEX INDEX zz_rt_k$q$; END $x$;')"
  fact reindex_conc_inside_do \
    "$(errf suite 'DO $x$ BEGIN EXECUTE $q$REINDEX INDEX CONCURRENTLY zz_rt_k$q$; END $x$;')"
  fact reindex_conc_top_level "$(errf suite 'REINDEX INDEX CONCURRENTLY zz_rt_k;')"
  fact vacuum_inside_do \
    "$(errf suite 'DO $x$ BEGIN EXECUTE $q$VACUUM zz_rt$q$; END $x$;')"
  fact comment_expression \
    "$(errf suite "COMMENT ON INDEX zz_rt_k IS 'a' || 'b';")"
  fact comment_literal "$(errf suite "COMMENT ON INDEX zz_rt_k IS 'ab';")"
  q suite 'DROP TABLE IF EXISTS zz_rt' > /dev/null 2>&1
  cat "$OUT/facts.txt" >&2
}

# ----------------------------------------------- the no-defeat proofs --------
# The shared definition's rule "the maintenance must not be defeated" says a
# fixture may not carry a state into its maintenance VACUUM ANALYZE that would
# have stopped a real server's autovacuum from doing the work the assumption
# credits it with, and that a fixture which did is repaired and re-run rather
# than scored.  This function is that rule, enforced: it fails the run instead
# of publishing a number taken under a defeated maintenance.
#
# Four proofs, per maintained table:
#   1. the statement completed, and no skip line in the server log names it;
#   2. its VERBOSE "dead but not yet removable" count is zero;
#   3. no other backend held a transaction or an xmin, no replication slot
#      held one and no prepared transaction existed when it started;
#   4. the index page classes it left behind, recorded for the report.
# The publication check comes with them: a table whose churn counter was still
# unpublished when its ANALYZE ran would have had its churn forgotten.
suite_maint_proofs() {
  local n bad
  n=$(s suite 'SELECT count(*) FROM maint')
  [ "$n" -gt 0 ] || die "the maintenance step maintained no table at all"
  bad=$(s suite 'SELECT count(*) FROM maint WHERE ended IS NULL')
  [ "$bad" = 0 ] || die "$bad maintenance statements did not complete"
  bad=$(s suite 'SELECT count(*) FROM maint WHERE dead_not_removable IS NULL')
  [ "$bad" = 0 ] \
    || { t suite 'SELECT tbl FROM maint WHERE dead_not_removable IS NULL ORDER BY tbl' >&2
         die "$bad maintained tables have no VERBOSE count: proof 2 is missing"; }
  # Membership of the maintained set is itself the publication proof: the set
  # comes from write counters that only a flush can move.  What this check adds
  # is the one case a zero modification counter could otherwise hide - a churn
  # that never reached the statistics entry - by excluding the tables whose own
  # recipe analyzed them after their own writes and consumed the counter.
  bad=$(s suite 'SELECT count(*) FROM maint
                  WHERE COALESCE(mods_before, 0) = 0 AND NOT analyzed_in_churn')
  [ "$bad" = 0 ] \
    || { t suite 'SELECT tbl, ins, upd, del, mods_before, analyzed_in_churn
                    FROM maint
                   WHERE COALESCE(mods_before, 0) = 0 AND NOT analyzed_in_churn
                   ORDER BY tbl' >&2
         die "$bad churned tables reached their ANALYZE with an unpublished counter"; }
  bad=$(s suite 'SELECT count(*) FROM maint WHERE dead_not_removable > 0')
  [ "$bad" = 0 ] \
    || { t suite 'SELECT tbl, removed, remain, dead_not_removable, dead_after
                    FROM maint WHERE dead_not_removable > 0
                   ORDER BY dead_not_removable DESC' >&2
         die "$bad maintained tables kept dead tuples the horizon still covered: the maintenance was defeated, repair the fixture and re-run"; }
  bad=$(s suite 'SELECT count(*) FROM horizon
                  WHERE xmin_holders > 0 OR open_xacts > 0
                     OR slots > 0 OR prepared > 0')
  [ "$bad" = 0 ] \
    || { t suite 'SELECT step, tbl, xmin_holders, open_xacts, slots, prepared, detail
                    FROM horizon
                   WHERE xmin_holders > 0 OR open_xacts > 0
                      OR slots > 0 OR prepared > 0 ORDER BY at' >&2
         die "$bad horizon probes found a holder: the maintenance ran with a pinned horizon"; }
  { printf 'maintained tables        %s\n' "$n"
    printf 'statements completed     %s\n' \
      "$(s suite 'SELECT count(*) FROM maint WHERE ended IS NOT NULL')"
    printf 'analyzed by own recipe   %s, all with a published churn counter\n' \
      "$(s suite 'SELECT count(*) FROM maint WHERE analyzed_in_churn')"
    printf 'dead but not removable   max %s over %s tables\n' \
      "$(s suite 'SELECT COALESCE(max(dead_not_removable), -1) FROM maint')" "$n"
    printf 'dead tuples left behind  max %s\n' \
      "$(s suite 'SELECT COALESCE(max(dead_after), -1) FROM maint')"
    printf 'tuples removed           %s over %s tables\n' \
      "$(s suite 'SELECT COALESCE(sum(removed), 0) FROM maint')" "$n"
    printf 'horizon probes clean     %s of %s\n' \
      "$(s suite 'SELECT count(*) FROM horizon
                   WHERE xmin_holders = 0 AND open_xacts = 0
                     AND slots = 0 AND prepared = 0')" \
      "$(s suite 'SELECT count(*) FROM horizon')"
    printf 'distinct timeout sets    %s: %s\n' \
      "$(s suite 'SELECT count(DISTINCT timeouts) FROM maint')" \
      "$(s suite 'SELECT DISTINCT timeouts FROM maint')"; } \
    > "$OUT/maint_proofs.txt"
  cat "$OUT/maint_proofs.txt" >&2
}

# ---------------------------------------------------------------- suite ------
# The ported numbered suite, in eleven steps: build, baseline, churn,
# maintenance, auto-analyze, preconditions, forge, page classes, decide, act,
# oracle.  The baseline and act steps run the page's apply block exactly as
# filed.
stage_suite() {
  say "the ported numbered suite: tests 1-17, 18-91 and controls 92-120"
  q suite 'DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public' > /dev/null
  q suite 'CREATE EXTENSION IF NOT EXISTS pgstattuple' > /dev/null
  f suite "$SQLD/harness.sql"        || die "harness failed"
  f suite "$SQLD/fixtures_build.sql" > "$OUT/suite_build.log" 2>&1 \
    || { tail -5 "$OUT/suite_build.log" >&2; die "build fixtures failed"; }
  local have13=no haveicu=no
  if [ "$(s suite 'SHOW server_version_num')" -ge 130000 ]; then
    f suite "$SQLD/fixtures_v13.sql" >> "$OUT/suite_build.log" 2>&1 \
      && have13=yes || note "v13 fixtures failed, skipped"
  else
    note "server is older than 13: the support function 4 fixtures are skipped"
  fi
  if f suite "$SQLD/fixtures_icu.sql" >> "$OUT/suite_build.log" 2>&1; then
    haveicu=yes
  else
    note "no ICU in this build: the five ICU fixtures are skipped"
  fi
  printf 'v13_fixtures=%s icu_fixtures=%s\n' "$have13" "$haveicu" > "$OUT/suite_groups.txt"
  note "$(s suite 'SELECT count(*) || $$ planned fixtures$$ FROM plan')"

  q suite 'CALL take_snap($$built$$)' || die "snapshot built failed"
  say "baseline: the filed apply block, first run"
  f suite "$SQLD/apply.sql" > "$OUT/apply_init.log" 2>&1 \
    || { tail -5 "$OUT/apply_init.log" >&2; die "apply (init) failed"; }
  grep -c 'initialize=' "$OUT/apply_init.log" > /dev/null
  tail -1 "$OUT/apply_init.log" >&2
  q suite 'CALL take_snap($$init$$)' || die "snapshot init failed"

  # The write counters before the first churn statement.  Their movement across
  # the churn phase is what defines the tables the maintenance step maintains.
  fv suite phase=before "$SQLD/churn_seen.sql" >&2 || die "churn census (before) failed"

  say "churn"
  f suite "$SQLD/fixtures_churn.sql" > "$OUT/suite_churn.log" 2>&1 \
    || { tail -5 "$OUT/suite_churn.log" >&2; die "churn failed"; }
  # The support function 4 fixtures are indexes on t and t2, which the uniform
  # drain above already covers, so this group needs no churn file of its own
  # now that the deduplicate_items fixtures are retired.
  [ "$haveicu" = yes ] && f suite "$SQLD/churn_icu.sql" >> "$OUT/suite_churn.log" 2>&1

  # The maintenance assumption of the shared definition: VACUUM ANALYZE on
  # every table the churn touched, before the census and the decide phase.  The
  # churn ran in psql processes that have now exited, so their statistics are
  # flushed; one second of grace covers the collector interval of the older
  # server, whose reader also waits for a fresh file.
  sleep 1
  fv suite phase=after "$SQLD/churn_seen.sql" >&2 || die "churn census (after) failed"
  say "maintenance: VACUUM (VERBOSE, ANALYZE) on every churned table"
  f suite "$SQLD/maint.sql" > "$OUT/maint.log" 2> "$OUT/maint_verbose.log" \
    || { tail -5 "$OUT/maint_verbose.log" >&2; die "maintenance step failed"; }
  note "$(head -2 "$OUT/maint.log" | tail -1)"
  # Proof 2 of the no-defeat rule: each statement's own VERBOSE counts, parsed
  # out of the message text and stored per table.
  parse_verbose "$OUT/maint_verbose.log" > "$SQLD/maint_verbose.sql"
  [ -s "$SQLD/maint_verbose.sql" ] \
    || die "the VACUUM VERBOSE output produced no tuples line: the proof is missing"
  f suite "$SQLD/maint_verbose.sql" > /dev/null || die "recording the VERBOSE counts failed"
  sleep 1
  f suite "$SQLD/maint_after.sql" >&2 || die "post-maintenance read failed"
  suite_maint_proofs

  # Rule 3 of the shared definition: a fixture that moved more than 10 % of a
  # table's heap tuples gets an ANALYZE, because autovacuum would have run one.
  # With the maintenance step in front of it the census finds every churned
  # table freshly analyzed, so what it decides now is the tables no churn
  # touched, and it doubles as the recheck that the counters were published in
  # the right order.
  say "simulated auto-analyze: the engine's own threshold on its own counters"
  f suite "$SQLD/autoanalyze.sql" > "$OUT/autoanalyze.log" 2>&1 \
    || { tail -5 "$OUT/autoanalyze.log" >&2; die "simulated auto-analyze failed"; }
  # The recheck waits a second and reads from a new session, so that it can see
  # the counters the census just reset on either server.
  sleep 1
  f suite "$SQLD/autoanalyze_after.sql" >> "$OUT/autoanalyze.log" 2>&1 \
    || { tail -5 "$OUT/autoanalyze.log" >&2; die "census recheck failed"; }
  t suite "SELECT /* wiki_btmaint_autoanalyze_report */ tbl, reltuples, mods,
                  threshold, mod_pct, would_autoanalyze
             FROM autoanl ORDER BY would_autoanalyze DESC, mods DESC, tbl" \
    > "$OUT/autoanalyze.txt" 2>&1
  { printf 'tables considered  %s\n' \
      "$(s suite 'SELECT count(*) FROM autoanl')"
    printf 'analyzed           %s\n' \
      "$(s suite 'SELECT count(*) FROM autoanl WHERE would_autoanalyze')"
    printf 'left alone         %s\n' \
      "$(s suite 'SELECT count(*) FROM autoanl WHERE NOT would_autoanalyze')"
    printf 'counters reset     %s of %s\n' \
      "$(s suite 'SELECT count(*) FROM autoanl_after WHERE mods = 0')" \
      "$(s suite 'SELECT count(*) FROM autoanl_after')"
    printf 'mod_pct of those analyzed, min/median/max %s\n' \
      "$(s suite "SELECT min(mod_pct) || ' / ' ||
                         percentile_disc(0.5) WITHIN GROUP (ORDER BY mod_pct) || ' / ' ||
                         max(mod_pct) FROM autoanl WHERE would_autoanalyze")"
    printf 'largest mod_pct left alone %s\n' \
      "$(s suite "SELECT COALESCE(max(mod_pct)::text, 'none')
                    FROM autoanl WHERE NOT would_autoanalyze")"; } \
    >> "$OUT/autoanalyze.txt"
  # The guard the old "no table crossed the threshold" check was really making
  # - that the churn counters were visible at all - now lives in
  # suite_maint_proofs, which fails when a maintained table reached its VACUUM
  # ANALYZE with an unpublished counter.  A census that analyzes nothing is a
  # legitimate outcome once every churned table has just been analyzed, so it
  # is reported rather than fatal.
  tail -6 "$OUT/autoanalyze.txt" >&2

  say "preconditions: what the shared definition requires of a numbered fixture"
  f suite "$SQLD/precond.sql" > "$OUT/precond.txt" 2>&1 || die "precondition check failed"
  cat "$OUT/precond.txt" >&2

  say "forge: the catalog forgeries an ANALYZE would have overwritten"
  f suite "$SQLD/forge.sql" > "$OUT/forge.log" 2>&1 || die "forge failed"
  cat "$OUT/forge.log" >&2

  # Proof 4 of the no-defeat rule: the page classes the maintenance left in
  # every fixture index.  Read-only, so the decide phase sees the same state.
  say "page classes: what the maintenance left in each index"
  f suite "$SQLD/pageclass.sql" > "$OUT/pageclass.txt" 2>&1 || die "page-class read failed"
  tail -1 "$OUT/pageclass.txt" >&2
  q suite 'CALL take_snap($$churned$$)' || die "snapshot churned failed"

  say "decide: the filed report statement, as filed and through the one-edit view"
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d suite -f "$SQLD/report.sql" \
    > "$OUT/report_churned.txt" 2>&1 || die "filed report failed"
  f suite "$SQLD/plan_view.sql" || die "plan_v failed"
  f suite /dev/stdin <<'SQL' || die "recording the plan failed"
DELETE FROM truth;
INSERT INTO truth(idx, action, baseline, wasted_pct, notes, bytes_churned, cmd_report)
SELECT v.index_name, v.action, v.baseline, v.wasted_pct, v.notes, s.bytes,
       v.comment_command
  FROM plan_v v
  JOIN snap s ON s.phase = 'churned' AND s.idx = v.index_name;
SQL
  note "$(s suite 'SELECT count(*) || $$ decisions recorded$$ FROM truth')"

  say "act: the filed apply block, second run"
  f suite "$SQLD/apply.sql" > "$OUT/apply_act.log" 2>&1 \
    || { tail -20 "$OUT/apply_act.log" >&2; die "apply (act) failed"; }
  tail -1 "$OUT/apply_act.log" >&2
  q suite 'CALL take_snap($$applied$$)' || die "snapshot applied failed"
  f suite /dev/stdin <<'SQL' || die "recording the applied state failed"
UPDATE truth t
   SET bytes_applied = a.bytes,
       cmd_written = a.cmt,
       reindexed_by_heuristic = (a.bytes < t.bytes_churned)
  FROM snap a
 WHERE a.phase = 'applied' AND a.idx = t.idx;
SQL

  say "oracle: REINDEX INDEX on every fixture"
  f suite /dev/stdin <<'SQL' || die "ground truth failed"
SET /* wiki_btmaint_oracle_statement_timeout */ statement_timeout = '900s';
CALL ground_truth();
SQL
  note "$(s suite 'SELECT count(*) || $$ fixtures with an oracle$$ FROM truth WHERE bytes_fresh IS NOT NULL')"
}

# ---------------------------------------------------------------- cost -------
# What a run costs, in the two states an operator actually meets: a settled
# database where every index is skipped, and one where the size gate fires
# everywhere, which is the worst case because pgstatindex reads every page of
# every gated index.  The gated state is forged by halving each stored sz; the
# suite has already been scored by the time this stage runs, and the forgery is
# recorded so no later stage reads those comments as real baselines.
stage_cost() {
  say "cost: the filed report in a settled and in a fully gated database"
  : > "$OUT/cost.txt"
  local i
  # Settle first: the oracle's rebuilds left many indexes smaller than their
  # stored baseline, which is a refresh, not a skip.  One apply run takes those
  # back to a state where the report has nothing to do, which is the state an
  # operator's scheduled run meets almost every time.
  f suite "$SQLD/apply.sql" > "$OUT/cost_settle.log" 2>&1
  printf 'settled state\n' >> "$OUT/cost.txt"
  s suite "SELECT '  gated indexes: ' || count(*) FILTER (WHERE action <> 'skip') ||
                  ' of ' || count(*) FROM plan_v" >> "$OUT/cost.txt"
  for i in 1 2 3 4 5 6; do
    printf '  run %s %s\n' "$i" \
      "$("$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite -c '\timing on' \
           -f "$SQLD/report.sql" 2>&1 | grep -E '^Time:' | tail -1)" >> "$OUT/cost.txt"
  done
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite \
    -c 'EXPLAIN (ANALYZE, BUFFERS) SELECT count(*) FROM plan_v' 2>&1 \
    | grep -m 1 -E 'Buffers: shared' | sed 's/^ */  total /' >> "$OUT/cost.txt"
  printf 'fully gated state (every stored sz halved)\n' >> "$OUT/cost.txt"
  # Only the size input is forged: both tuple counts are written at their
  # current values, so the fully gated reading isolates one gate rather than
  # three, and the worst case it measures is still every gated index read end
  # to end.
  f suite /dev/stdin > /dev/null 2>&1 <<'SQL'
DO $fg$
DECLARE r record;
BEGIN
  FOR r IN SELECT p.idx, pg_relation_size(p.idx::regclass) AS b,
                  c.reltuples::numeric AS itup, t.reltuples::numeric AS tup
             FROM plan p
             JOIN pg_class c ON c.relname = p.idx AND c.relkind = 'i'
             JOIN pg_index x ON x.indexrelid = c.oid
             JOIN pg_class t ON t.oid = x.indrelid LOOP
    EXECUTE format('COMMENT /* wiki_btmaint_cost_forgery */ ON INDEX %I IS %L',
                   r.idx, '@btmaint:{"v":2,"sz":' || (r.b / 2)::bigint
                          || ',"tup":' || round(GREATEST(r.tup, -1))
                          || ',"itup":' || round(GREATEST(r.itup, -1))
                          || ',"at":"2026-01-01T00:00:00+00"}');
  END LOOP;
END $fg$;
SQL
  s suite "SELECT '  gated indexes: ' || count(*) FILTER (WHERE action <> 'skip') ||
                  ' of ' || count(*) FROM plan_v" >> "$OUT/cost.txt"
  for i in 1 2 3 4 5 6; do
    printf '  run %s %s\n' "$i" \
      "$("$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite -c '\timing on' \
           -f "$SQLD/report.sql" 2>&1 | grep -E '^Time:' | tail -1)" >> "$OUT/cost.txt"
  done
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite \
    -c 'EXPLAIN (ANALYZE, BUFFERS) SELECT count(*) FROM plan_v' 2>&1 \
    | grep -m 1 -E 'Buffers: shared' | sed 's/^ */  total /' >> "$OUT/cost.txt"
  s suite "SELECT '  total index bytes: ' ||
                  pg_size_pretty(sum(pg_relation_size(idx::regclass))) FROM plan" \
    >> "$OUT/cost.txt"
  cat "$OUT/cost.txt" >&2
}

# ---------------------------------------------------------------- score ------
stage_score() {
  say "score"
  t suite "SELECT /* wiki_btmaint_verdict_rows */ num, leg, grp, idx, action,
                  wasted_pct, actual_pct, applied_pct, verdict, lost_by,
                  expected_stage, taken_stage, two_gate_stage, want_stage,
                  size_ratio, tuple_ratio, idx_tuple_ratio
             FROM verdicts ORDER BY num, leg" > "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_verdict_counts */ verdict, count(*)
             FROM verdicts GROUP BY 1 ORDER BY 2 DESC" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_group_counts */ grp,
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE NOT scored) AS unscored,
                  count(*) FILTER (WHERE action = 'reindex') AS reindexed,
                  count(*) FILTER (WHERE action = 'update')  AS updated,
                  count(*) FILTER (WHERE action = 'skip')    AS skipped,
                  count(*) FILTER (WHERE action = 'refresh') AS refreshed,
                  count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE') AS false_neg,
                  round(avg(wasted_pct), 1) AS avg_wasted,
                  round(avg(actual_pct), 1) AS avg_actual
             FROM verdicts GROUP BY grp ORDER BY grp" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_accuracy */
                  count(*) AS measured,
                  round(avg(actual_pct - wasted_pct), 1)  AS mean_error,
                  round(min(actual_pct - wasted_pct), 1)  AS min_error,
                  round(max(actual_pct - wasted_pct), 1)  AS max_error,
                  count(*) FILTER (WHERE abs(actual_pct - wasted_pct) <= 15) AS within_15,
                  count(*) FILTER (WHERE wasted_pct > actual_pct) AS over_estimates
             FROM verdicts WHERE wasted_pct IS NOT NULL AND scored" \
    >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_action_counts */ action, count(*),
                  round(avg(actual_pct), 1) AS avg_actual
             FROM verdicts GROUP BY 1 ORDER BY 2 DESC" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_gate_agreement */
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE expected_stage = taken_stage) AS gate_agrees,
                  count(*) FILTER (WHERE want_stage IS NOT NULL
                                     AND want_stage = taken_stage) AS want_hit,
                  count(*) FILTER (WHERE want_stage IS NOT NULL
                                     AND want_stage <> taken_stage) AS want_miss
             FROM verdicts" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_lost */ num, leg, idx, action, wasted_pct,
                  actual_pct, lost_by, size_ratio, tuple_ratio
             FROM verdicts WHERE lost_by IS NOT NULL ORDER BY actual_pct DESC" \
    > "$OUT/lost.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_disagree */ num, leg, idx, expected_stage,
                  taken_stage, baseline, size_ratio, tuple_ratio, notes
             FROM verdicts WHERE expected_stage <> taken_stage ORDER BY num, leg" \
    > "$OUT/disagree.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_want_miss */ num, leg, idx, want_stage,
                  taken_stage, action, wasted_pct, actual_pct, req
             FROM verdicts WHERE want_stage IS NOT NULL AND want_stage <> taken_stage
            ORDER BY num, leg" > "$OUT/want_miss.txt" 2>&1
  # Did step 2 store the baseline step 1 said it would?  For every action but
  # reindex the two sz values are the same state and must agree; for reindex
  # step 1 prints no command and the stored size must be the post-rebuild one.
  t suite "SELECT /* wiki_btmaint_cmd_match */ action,
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE sz_reported IS NOT NULL) AS reported,
                  count(*) FILTER (WHERE sz_reported = sz_written) AS sz_agrees,
                  count(*) FILTER (WHERE sz_written = bytes_applied) AS sz_is_current
             FROM verdicts GROUP BY action ORDER BY action" >> "$OUT/verdicts.txt" 2>&1
  # Which gate opened each measured fixture, and what the third one changed.
  t suite "SELECT /* wiki_btmaint_gate_attribution */
                  count(*) FILTER (WHERE taken_stage = 'measure') AS measured,
                  count(*) FILTER (WHERE taken_stage = 'measure'
                                     AND size_gate_fires) AS by_size,
                  count(*) FILTER (WHERE taken_stage = 'measure'
                                     AND tbl_gate_fires) AS by_table_tuples,
                  count(*) FILTER (WHERE taken_stage = 'measure'
                                     AND idx_gate_fires) AS by_index_tuples,
                  count(*) FILTER (WHERE taken_stage = 'measure'
                                     AND idx_gate_fires AND NOT size_gate_fires
                                     AND NOT tbl_gate_fires) AS index_gate_only,
                  count(*) FILTER (WHERE taken_stage = 'measure'
                                     AND NOT size_gate_fires AND NOT tbl_gate_fires
                                     AND NOT idx_gate_fires) AS no_gate
             FROM verdicts" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_two_gate_delta */
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE two_gate_stage = taken_stage) AS same_as_two_gate,
                  count(*) FILTER (WHERE two_gate_stage = 'skip'
                                     AND taken_stage = 'measure') AS newly_measured,
                  count(*) FILTER (WHERE two_gate_stage = 'skip'
                                     AND taken_stage = 'measure'
                                     AND actual_pct >= 50) AS newly_measured_bloated,
                  count(*) FILTER (WHERE two_gate_stage = 'skip'
                                     AND taken_stage = 'measure'
                                     AND actual_pct < 50) AS newly_measured_healthy,
                  count(*) FILTER (WHERE two_gate_stage = 'measure'
                                     AND taken_stage <> 'measure') AS lost_measurements
             FROM verdicts" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_newly_measured */ num, leg, idx, action,
                  wasted_pct, actual_pct, verdict, idx_tuple_ratio, req
             FROM verdicts WHERE two_gate_stage = 'skip' AND taken_stage = 'measure'
            ORDER BY actual_pct DESC" > "$OUT/newly_measured.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_itup_stored */
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE itup_stored_matches) AS itup_matches_catalog,
                  count(*) FILTER (WHERE base_idx_tuples IS NULL) AS itup_missing,
                  count(*) FILTER (WHERE itup_written IS NOT NULL) AS itup_written_back
             FROM verdicts" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_lost_detail */ num, leg, idx, actual_pct,
                  size_ratio, tuple_ratio, idx_tuple_ratio,
                  size_gate_fires, tbl_gate_fires, idx_gate_fires, req
             FROM verdicts WHERE lost_by IS NOT NULL
            ORDER BY actual_pct DESC" >> "$OUT/lost.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_payload_health */
                  count(*) AS indexes,
                  count(*) FILTER (WHERE payload IS NOT NULL) AS with_payload,
                  count(*) FILTER (WHERE base_bytes IS NULL) AS unparseable,
                  count(*) FILTER (WHERE cmt !~ '@btmaint:') AS no_marker
             FROM snap WHERE phase = 'applied'" >> "$OUT/verdicts.txt" 2>&1
  # The maintenance assumption and the no-defeat rule, fixture by fixture and
  # then per table, so that a reader can see which fixture was maintained, what
  # its VACUUM removed, what it could not remove, and the page classes left in
  # the index the method was then asked about.
  t suite "SELECT /* wiki_btmaint_maint_by_fixture */ num, leg, idx, tbl,
                  maintained, maint_removed, dead_not_removable, dead_after,
                  deleted_pages, empty_pages, density_after_maint,
                  wasted_pct, actual_pct, verdict
             FROM verdicts ORDER BY num, leg" > "$OUT/maintenance.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_maint_by_table */ ord, tbl, ins, upd, del,
                  mods_before, analyzed_in_churn, dead_before, removed, remain,
                  dead_not_removable, mods_after, dead_after,
                  round(extract(epoch FROM ended - started)::numeric, 2) AS secs
             FROM maint ORDER BY ord" >> "$OUT/maintenance.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_maint_aggregate */
                  count(*) AS maintained_tables,
                  count(*) FILTER (WHERE ended IS NOT NULL) AS completed,
                  count(*) FILTER (WHERE dead_not_removable = 0) AS horizon_clean,
                  count(*) FILTER (WHERE dead_not_removable > 0) AS horizon_pinned,
                  COALESCE(sum(removed), 0) AS tuples_removed,
                  COALESCE(max(dead_after), 0) AS max_dead_left,
                  count(DISTINCT timeouts) AS timeout_sets
             FROM maint" >> "$OUT/maintenance.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_horizon_rows */ step, tbl, xmin_holders,
                  open_xacts, slots, slot_xmins, prepared, detail
             FROM horizon
            WHERE xmin_holders > 0 OR open_xacts > 0 OR slots > 0
               OR prepared > 0 OR tbl IS NULL
            ORDER BY at" >> "$OUT/maintenance.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_pageclass_by_group */ grp,
                  count(*) AS fixtures,
                  count(*) FILTER (WHERE maintained) AS maintained,
                  count(*) FILTER (WHERE deleted_pages > 0) AS with_deleted_pages,
                  COALESCE(sum(deleted_pages), 0) AS deleted_pages,
                  COALESCE(sum(empty_pages), 0) AS empty_pages,
                  round(avg(density_after_maint), 1) AS avg_density
             FROM verdicts GROUP BY grp ORDER BY grp" >> "$OUT/maintenance.txt" 2>&1
  # The precondition the shared definition puts on a numbered fixture, and what
  # this run observed.  A fixture reported here scores nothing.
  t suite "SELECT /* wiki_btmaint_precond_rows */ p.num, p.leg, p.requirement,
                  p.observed, p.met
             FROM precond p ORDER BY p.num, p.leg" >> "$OUT/verdicts.txt" 2>&1
  t suite "SELECT /* wiki_btmaint_scored */ count(*) AS fixtures,
                  count(*) FILTER (WHERE scored) AS scored,
                  count(*) FILTER (WHERE NOT scored) AS unmet_precondition,
                  count(*) FILTER (WHERE scored AND verdict = 'PASS') AS pass,
                  count(*) FILTER (WHERE maintained) AS maintained
             FROM verdicts" >> "$OUT/verdicts.txt" 2>&1
  tail -40 "$OUT/verdicts.txt" >&2
}

# ------------------------------------------------- expected server errors ---
# Every server-side error this suite provokes is deliberate, and after the
# page-local acceptance fixtures were removed they all come from stage_facts
# and from the two feature-gated fixture files a 12 server refuses.
#
# The line pattern is the default log_line_prefix, "%m [%p] ": a date, a time
# with milliseconds, the log time zone, the backend pid in brackets, and then
# the severity.  An earlier revision of this function looked for the severity
# immediately after the time zone, which that prefix never produces, so it
# matched nothing and reported a clean log whatever the server had logged.
# The count of matched lines is now reported beside the unexpected ones, so a
# check that matches nothing is visible as such.
UNEXPECTED_ERRORS=0
check_server_errors() {
  local log=$1 total
  [ -f "$log" ] || { note "no server log"; return 0; }
  grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:.]+ [A-Z]+ \[[0-9]+\] (ERROR|FATAL|PANIC):' \
    "$log" > "$OUT/server_errors_all.txt"
  total=$(grep -c '' "$OUT/server_errors_all.txt")
  grep -Ev 'REINDEX CONCURRENTLY cannot run inside a transaction block|cannot be executed from a function|unrecognized parameter "deduplicate_items"|ICU is not supported|unrecognized privilege type|invalid function number 4|invalid transaction termination|syntax error at or near "\|\|"' \
    "$OUT/server_errors_all.txt" > "$OUT/server_errors.txt"
  UNEXPECTED_ERRORS=$(grep -c '' "$OUT/server_errors.txt")
  printf 'logged errors: %s, deliberate: %s, unexpected: %s\n' \
    "$total" "$((total - UNEXPECTED_ERRORS))" "$UNEXPECTED_ERRORS"
  [ "$UNEXPECTED_ERRORS" -gt 0 ] && head -5 "$OUT/server_errors.txt"
  return 0
}

# Proof 1 of the no-defeat rule, from the log side: a maintenance command that
# was skipped for want of the lock, or cancelled part-done, says so in the
# server log.  A foreground VACUUM without SKIP_LOCKED waits rather than
# skipping, and nothing in this suite holds a conflicting lock, so the expected
# count is zero on both counts; the check exists because a zero it never looked
# for would prove nothing.
MAINT_SKIPS=0
check_maintenance_skips() {
  local log=$1
  [ -f "$log" ] || { note "no server log"; return 0; }
  grep -E 'skipping vacuum of|skipping analyze of|canceling statement due to|canceling autovacuum task' \
    "$log" > "$OUT/maint_skips.txt"
  MAINT_SKIPS=$(grep -c '' "$OUT/maint_skips.txt")
  printf 'maintenance skip or cancellation lines: %s\n' "$MAINT_SKIPS"
  [ "$MAINT_SKIPS" -gt 0 ] && head -5 "$OUT/maint_skips.txt"
  return 0
}

# ---------------------------------------------------------------- criteria ---
stage_criteria() {
  say "pass criteria"
  # Every counter comes through a file, not through -c: a dollar-quoted string
  # inside a double-quoted shell argument would have $$ replaced by the shell's
  # own process id before psql ever saw it.
  "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d suite -f - > "$OUT/counters.txt" 2>&1 <<'SQL'
SELECT 'planned=' || count(*) FROM plan;
SELECT '  ' || verdict || '=' || count(*) FROM verdicts GROUP BY verdict ORDER BY verdict;
SELECT '  gate agree=' || count(*) FILTER (WHERE expected_stage = taken_stage) ||
       ' disagree='    || count(*) FILTER (WHERE expected_stage <> taken_stage) ||
       ' want_hit='    || count(*) FILTER (WHERE want_stage = taken_stage) ||
       ' want_miss='   || count(*) FILTER (WHERE want_stage <> taken_stage)
  FROM verdicts;
SELECT '  action ' || action || '=' || count(*) FROM verdicts GROUP BY action ORDER BY action;
SELECT '  payload with=' || count(*) FILTER (WHERE payload IS NOT NULL) ||
       ' unparseable='   || count(*) FILTER (WHERE base_bytes IS NULL) ||
       ' no_marker='     || count(*) FILTER (WHERE cmt !~ '@btmaint:')
  FROM snap WHERE phase = 'applied';
SELECT '  false negatives=' || count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE') ||
       ' of which the index tuple gate opened=' ||
       count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE' AND idx_gate_fires)
  FROM verdicts;
SELECT '  measured=' || count(*) FILTER (WHERE taken_stage = 'measure') ||
       ' by size='   || count(*) FILTER (WHERE taken_stage = 'measure' AND size_gate_fires) ||
       ' by table='  || count(*) FILTER (WHERE taken_stage = 'measure' AND tbl_gate_fires) ||
       ' by index='  || count(*) FILTER (WHERE taken_stage = 'measure' AND idx_gate_fires) ||
       ' index only='|| count(*) FILTER (WHERE taken_stage = 'measure' AND idx_gate_fires
                                          AND NOT size_gate_fires AND NOT tbl_gate_fires)
  FROM verdicts;
SELECT '  versus the two-gate form: same=' ||
       count(*) FILTER (WHERE two_gate_stage = taken_stage) ||
       ' newly measured=' || count(*) FILTER (WHERE two_gate_stage = 'skip'
                                                AND taken_stage = 'measure') ||
       ' of those bloated=' || count(*) FILTER (WHERE two_gate_stage = 'skip'
                                                 AND taken_stage = 'measure'
                                                 AND actual_pct >= 50) ||
       ' healthy=' || count(*) FILTER (WHERE two_gate_stage = 'skip'
                                        AND taken_stage = 'measure'
                                        AND actual_pct < 50)
  FROM verdicts;
SELECT '  itup stored = catalog count: ' ||
       count(*) FILTER (WHERE itup_stored_matches) || ' of ' || count(*)
  FROM verdicts;
SELECT '  simulated auto-analyze: ' ||
       count(*) FILTER (WHERE would_autoanalyze) || ' of ' || count(*) ||
       ' tables analyzed, largest left alone ' ||
       COALESCE(max(mod_pct) FILTER (WHERE NOT would_autoanalyze)::text, 'none') || ' %'
  FROM autoanl;
SELECT '  scored=' || count(*) FILTER (WHERE scored) ||
       ' unmet precondition=' || count(*) FILTER (WHERE NOT scored) ||
       ' maintained=' || count(*) FILTER (WHERE maintained) ||
       ' of ' || count(*)
  FROM verdicts;
SELECT '  maintenance: ' || count(*) || ' tables, ' ||
       count(*) FILTER (WHERE ended IS NOT NULL) || ' completed, ' ||
       count(*) FILTER (WHERE dead_not_removable = 0) ||
       ' with nothing dead but not yet removable, ' ||
       count(*) FILTER (WHERE COALESCE(dead_after, 0) = 0) ||
       ' with no dead tuple left, timeout sets=' || count(DISTINCT timeouts)
  FROM maint;
SELECT '  timeouts in force during maintenance: ' || timeouts
  FROM maint GROUP BY timeouts ORDER BY timeouts;
SELECT '  horizon probes: ' || count(*) || ' taken, ' ||
       count(*) FILTER (WHERE xmin_holders = 0 AND open_xacts = 0
                          AND slots = 0 AND prepared = 0) || ' entirely clean, ' ||
       COALESCE(sum(slots), 0) || ' replication slots, ' ||
       COALESCE(sum(prepared), 0) || ' prepared transactions seen'
  FROM horizon;
SELECT '  page classes after maintenance: ' ||
       count(*) FILTER (WHERE deleted_pages > 0) || ' of ' || count(*) ||
       ' indexes hold deleted pages, ' || COALESCE(sum(deleted_pages), 0) ||
       ' deleted and ' || COALESCE(sum(empty_pages), 0) || ' half-dead in total'
  FROM pageclass;
SELECT '  precondition ' || num || ': ' || observed || ' -> ' ||
       CASE WHEN met THEN 'met' ELSE 'NOT MET, scores nothing' END
  FROM precond ORDER BY num, leg;
SQL
  { printf '1. texts\n'; cat "$OUT/hashes.txt" 2>/dev/null
    printf '2. engine checks\n'; cat "$OUT/checks.txt" 2>/dev/null
    printf '3. fixture groups\n'; cat "$OUT/suite_groups.txt" 2>/dev/null
    printf '4. counters\n'; sed 's/^/   /' "$OUT/counters.txt" 2>/dev/null
    printf '5. cost\n'; sed 's/^/   /' "$OUT/cost.txt" 2>/dev/null
    printf '5a. simulated auto-analyze\n'
    sed 's/^/   /' "$OUT/autoanalyze.txt" 2>/dev/null
    printf '5b. the maintenance and the no-defeat proofs\n'
    sed 's/^/   /' "$OUT/maint_proofs.txt" 2>/dev/null
    printf '6. facts\n'; sed 's/^/   /' "$OUT/facts.txt" 2>/dev/null
  } > "$OUT/criteria.txt" 2>&1
  { printf '7. server errors\n'; check_server_errors "$OUT/server.log"
    printf '8. maintenance skips and cancellations\n'
    check_maintenance_skips "$OUT/server.log"; } >> "$OUT/criteria.txt" 2>&1
  tail -60 "$OUT/criteria.txt" >&2
  note "full criteria in $OUT/criteria.txt"
}

# ---------------------------------------------------------------- report -----
stage_report() {
  say "report written to $OUT"
  ls -1 "$OUT" >&2
}

# ---------------------------------------------------------------- stop -------
# -m fast disconnects clients and lets the checkpointer write a shutdown
# checkpoint, so the next start needs no recovery.  The stop is then confirmed
# the way the teardown rule asks, and the stage dies rather than report a stop
# that did not happen, so clean never deletes a live cluster.
stage_stop() {
  say "stop the server cleanly"
  [ -x "$BIN/pg_ctl" ] || { note "no server binary under $BIN"; return 0; }
  if [ -s "$DATA/postmaster.pid" ] && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1 \
      || die "pg_ctl -m fast stop failed"
    tail -3 "$OUT/server.log" 2>/dev/null | grep -q 'database system is shut down' \
      && note "server.log: database system is shut down"
  else
    note "not running"
  fi
  [ -e "$DATA/postmaster.pid" ] && die "$DATA/postmaster.pid still exists"
  if command -v pgrep > /dev/null 2>&1 && pgrep -f -- "-D $DATA" > /dev/null 2>&1; then
    die "a postgres process still runs on $DATA"
  fi
  [ -z "$(ls -A "$SOCK" 2>/dev/null)" ] || die "socket directory $SOCK is not empty"
  note "confirmed: no postmaster.pid, no postgres process on $DATA, socket empty"
}

# Containment check before any rm -rf: SANDBOX comes from the environment, so
# refuse to delete anything outside this repository's .wiki-runtime/tmp tree.
inside_tmp() {
  case ${1%/} in
    "$WIKI_ROOT/.wiki-runtime/tmp"/?*) return 0 ;;
    *) return 1 ;;
  esac
}
stage_clean() {
  stage_stop
  inside_tmp "$SANDBOX" || die "refusing to delete $SANDBOX outside .wiki-runtime/tmp/"
  rm -rf "$SANDBOX"; say "sandbox deleted"
}

main() {
  local stages=("$@")
  [ ${#stages[@]} -eq 0 ] && stages=(build check cluster sql texts exact facts suite \
                                     cost score criteria report)
  local st
  for st in "${stages[@]}"; do
    case $st in
      build|check|cluster|sql|texts|exact|facts|suite|cost|score|criteria|report|stop|clean)
        "stage_$st" ;;
      *) die "unknown stage: $st" ;;
    esac
  done
}

main "$@"
```

## Context Reviewed

- `contrib/pgstattuple/pgstatindex.c`: the `IS_INDEX`/`IS_BTREE` macros, all four
  refusals, the `BAS_BULKREAD` strategy, the block-by-block classification of
  leaf, internal, empty and deleted pages, `max_avail` and `free_space`, the
  `index_size` arithmetic including the metapage, and the two `NaN` branches.
- `contrib/pgstattuple/pgstattuple--1.4--1.5.sql` and `pgstattuple.control`: the
  `pgstatindex(regclass)` and `pgstatindex(text)` declarations, the
  `REVOKE ... FROM PUBLIC` and the `GRANT ... TO pg_stat_scan_tables`.
- `doc/src/sgml/pgstattuple.sgml`: the output-column table and the metapage note.
- `src/backend/commands/comment.c`: `CommentObject`'s
  `get_object_address(..., ShareUpdateExclusiveLock)` and
  `check_object_ownership`, and `CreateComments`'s replace-or-delete behaviour
  including the empty-string reduction to NULL.
- `src/backend/catalog/objectaddress.c`: `check_object_ownership` for
  `OBJECT_INDEX`, and the relkind check that rejects a non-index.
- `src/include/catalog/pg_description.h`: the catalog's three-column key and the
  `objsubid = 0` rule for a whole-object comment.
- `src/backend/catalog/index.c`: `index_concurrently_swap`'s comment move,
  `index_update_stats` and its empty-table `reltuples` hack, both
  `index_update_stats` calls in `index_build`, and `reindex_index`'s `ShareLock`
  on the heap with `AccessExclusiveLock` on the index.
- `src/backend/commands/indexcmds.c`: `ExecReindex`'s
  `PreventInTransactionBlock("REINDEX CONCURRENTLY")`, `ReindexIndex`'s lock
  modes, and `RangeVarCallbackForReindexIndex`'s `ACL_MAINTAIN` check.
- `src/include/catalog/pg_class.h`: the `reltuples` definition and its `-1`
  sentinel.
- `src/include/access/nbtree.h` and `src/backend/access/nbtree/nbtsort.c`:
  `BTGetFillFactor`, `BTGetTargetPageFreeSpace` and `_bt_pagestate`'s leaf-page
  fill target.
- `src/backend/catalog/system_functions.sql`: `pg_relation_size(regclass)`
  defaulting to the main fork, and `obj_description(oid, name)`.
- `src/backend/utils/adt/dbsize.c`: `pg_relation_size`'s `try_relation_open` and
  its NULL return for an already-dropped relation.
- `src/backend/utils/misc/guc_tables.c`: `statement_timeout` and `lock_timeout`
  as `PGC_USERSET`.
- `src/backend/storage/lmgr/lock.c`: the `LockConflicts` row for
  `ShareUpdateExclusiveLock`.
- `src/backend/parser/gram.y`: `comment_text` as `Sconst | NULL_P`.
- `src/backend/executor/nodeFunctionscan.c` and `src/backend/executor/execScan.c`:
  a set-returning function materialized into a tuplestore, and the qualification
  applied to the rows it produced.
- `src/backend/commands/vacuum.c` and `src/backend/commands/analyze.c`:
  `vac_update_relstats` as the writer VACUUM and ANALYZE share, its `relpages`
  and `reltuples` assignments, `do_analyze_rel`'s per-index `vac_update_relstats`
  loop and its `ceil(tupleFract * totalrows)`, the `tupleFract = 1.0`
  initialization, `compute_index_stats`'s "no columns to analyze and not partial"
  skip, and the `numindexrows / numrows` fraction it computes for a partial index.
- `src/backend/access/heap/vacuumlazy.c`: `update_relstats_all_indexes` and its
  `estimated_count` skip, `lazy_cleanup_all_indexes`'s
  `scanned_pages < rel_pages` test, `BYPASS_THRESHOLD_PAGES` and the
  `lazy_vacuum` bypass decision.
- `src/backend/access/nbtree/nbtree.c`: `btvacuumcleanup`'s cleanup-only branch
  and its `estimated_count = true`, the heap-count clamp, and `btvacuumpage`'s two
  ways of counting (`nhtidslive` with a callback, items per page without).
- `src/backend/postmaster/autovacuum.c`: `relation_needs_vacanalyze`'s
  `anl_base_thresh`/`anl_scale_factor` resolution and the
  `doanalyze = (anltuples > anlthresh)` test the mandatory tests now simulate,
  the launcher's and the worker's four `SetConfigOption(..., "0", ...)` timeout
  overrides and the comment that explains them, and the `VACOPT_SKIP_LOCKED`
  a non-wraparound worker is given.
- `src/backend/commands/vacuum.c`: `vacuum_get_cutoffs`'s `OldestXmin` from
  `GetOldestNonRemovableTransactionId`, and the four `skipping vacuum of` /
  `skipping analyze of` messages a skipped maintenance command logs.
- `src/backend/storage/ipc/procarray.c`: `ComputeXidHorizons`'s fold of every
  backend's `xid` and `xmin`, its `PROC_IN_VACUUM`/`PROC_IN_LOGICAL_DECODING`
  exemption, and the replication-slot `xmin` it takes the older of.
- `src/backend/access/transam/twophase.c`: the dummy `PGPROC` that keeps a
  prepared transaction's xid considered running.
- `src/backend/access/heap/vacuumlazy.c`: the `VERBOSE` summary buffer,
  including the `tuples: ... are dead but not yet removable` line this run
  parses, and the `dead_items_info->num_items > 0` gate that decides whether
  index vacuuming runs at all.
- `src/backend/utils/error/elog.c`: `should_output_to_client`'s
  `elevel == INFO` clause, which is why `client_min_messages = warning` does not
  hide `VACUUM (VERBOSE)` output.
- `src/backend/catalog/system_views.sql`: the `n_tup_ins`/`n_tup_upd`/`n_tup_del`
  and `last_analyze` columns of `pg_stat_all_tables`, `pg_stat_activity`'s
  `xact_start` and `backend_xmin`, `pg_replication_slots`' `xmin` and
  `catalog_xmin`, and `pg_prepared_xacts`.
- `src/backend/utils/misc/guc_tables.c`: `transaction_timeout` and
  `idle_in_transaction_session_timeout` beside the two this page already cited,
  all four `PGC_USERSET`.
- `src/backend/utils/activity/pgstat_relation.c` and
  `src/backend/utils/activity/pgstat.c`: `pgstat_report_analyze`'s
  `mod_since_analyze = 0` reset, the pending-stats flush that adds
  `changed_tuples` to the same counter, and `PGSTAT_MIN_INTERVAL`.
- `src/backend/catalog/system_views.sql`: `pg_stat_all_tables`'s
  `n_mod_since_analyze` column.
- `doc/src/sgml/config.sgml`: the two autovacuum analyze parameters, their
  defaults and their per-table overrides.
- `doc/src/sgml/ref/comment.sgml` and `doc/src/sgml/ref/reindex.sgml`: the
  one-comment-per-object rule, the `SHARE UPDATE EXCLUSIVE` lock, the
  owner-only rule, and `REINDEX`'s `MAINTAIN` requirement.
- `src/backend/commands/tablecmds.c`: `ATExecChangeOwner`'s index branch, which
  warns and does nothing rather than changing an index's owner.
- [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
  as it stands after the 2026-09-12 retirements, the 2026-09-13 maintenance
  assumption and the 2026-09-15 rule `The maintenance must not be defeated`: the
  fixture set, the five phases, the assumption's three parts, the no-defeat
  rule's five forbidden states, four proof obligations and "no fixture is exempt
  today", rules 1 to 3 including rule 2's drain guarantees and rule 3's two
  publication points, the oracle and the four verdict bands, family 6's
  treatment of test 120, the retirement list under `What the suite does not
  cover`, and the `VACUUM` boundaries under `Interactions with Other Concepts`.
  Read as the definition this page ports; **not edited**, as
  `MANDATORY Common Concept Documents` requires.
- The 2026-09-16 review run itself: both legs rebuilt from their pins and run
  end to end on Linux x86_64, `make check` and the three contrib suites
  included, with the maintenance step applied, the four no-defeat proofs
  recorded, fixture 120's precondition asserted, and 4 and 8 logged errors, all
  deliberate. Two earlier passes of the same review, one stopped by its own
  publication invariant and one superseded by two harness repairs, were read for
  what they showed and are not a source of published numbers.
- The 2026-09-14 re-port run, for the numbers this page compares against: 126
  and 112 fixtures, 95 and 81 rebuilds, the `+18.2` under-read on `b93`/`b95`,
  and 66 and 45 census decisions.
- The sibling pages this one reuses or contrasts with:
  [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
  (unverified)](btree-index-bloat-core-sql-only.md), which ports the same suite to
  an estimator,
  [B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17
  (unverified)](btree-bloat-with-pgstatindex.md) for the wasted-space definition
  and the candidate filters, and
  [Detecting Inflated Non-B-Tree Indexes From Catalogs and a COMMENT-Stored
  Baseline in PostgreSQL 17
  (unverified)](non-btree-index-inflation-comment-baseline.md) for the
  comment-stored baseline pattern on the other access methods.

## Evidence Map

| Claim | Evidence |
|---|---|
| `pgstatindex` refuses a non-B-tree relation, another session's temp index and an invalid index, and one raised error aborts the statement | [pgstatindex.c#refusals](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L224-L250); the fixtures that measured all six refusals were removed on 2026-09-14 |
| `avg_leaf_density` is live-leaf-page density only, and `NaN` with no leaf pages | [pgstatindex.c#avg_leaf_density](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L363-L372) |
| `index_size` counts every page including the metapage | [pgstatindex.c#index_size](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L350-L357), [pgstattuple.sgml#metapage](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L268-L273) |
| The rebuild target is `BLCKSZ * (100 - fillfactor) / 100` free per leaf page | [nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1145), [nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L645-L671) |
| A comment is one string per object, keyed by OID, replaced whole | [pg_description.h#FormData](../../../../raw/postgres-17/src/include/catalog/pg_description.h#L44-L57), [comment.c#CreateComments](../../../../raw/postgres-17/src/backend/commands/comment.c#L133-L171), [comment.sgml#replaces](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L89-L93) |
| `COMMENT ON INDEX` takes `ShareUpdateExclusiveLock` and requires ownership | [comment.c#CommentObject](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L78), [objectaddress.c#check_object_ownership](../../../../raw/postgres-17/src/backend/catalog/objectaddress.c#L2387-L2400), [comment.sgml#lock](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L95-L98); the `pg_locks` probe and the non-owner role that measured both were removed on 2026-09-14 |
| `ALTER INDEX ... OWNER TO` warns and changes nothing | [tablecmds.c#ATExecChangeOwner-index](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14544-L14561) |
| The comment text is a literal, never an expression | [gram.y#comment_text](../../../../raw/postgres-17/src/backend/parser/gram.y#L7219-L7222); measured `syntax error at or near "||"` |
| A concurrent rebuild moves the comment to the new index | [index.c#index_concurrently_swap-comment](../../../../raw/postgres-17/src/backend/catalog/index.c#L1740-L1784); the fixture that measured OID 18147 -> 18149 with the comment md5 unchanged was removed on 2026-09-14 |
| A rebuild refreshes both `reltuples` values from its own scans | [index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3129-L3134), [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2788-L2812); measured 1000 after `CREATE INDEX` and 2000 after `REINDEX` on the table, 2000 then 200 on a partial index |
| `reltuples = -1` means uncounted from v14 | [pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L66); measured `-1` on 17.11 and `0` on 12.2 for the same sequence |
| ANALYZE writes an index's `reltuples` as `ceil(tupleFract * totalrows)`, with the fraction refined only for an index with statistics columns or a predicate | [analyze.c#same-for-indexes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663), [analyze.c#tupleFract-init](../../../../raw/postgres-17/src/backend/commands/analyze.c#L443-L449), [analyze.c#compute_index_stats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L827-L863), [analyze.c#tupleFract-from-sample](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953); measured 2000 for a partial index on a 10,000-row table, and 10000 for the plain index beside it, on both servers |
| VACUUM writes an index's `reltuples` only when the AM's count is not estimated, and `btvacuumcleanup` marks a cleanup-only count estimated | [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3069-L3099), [vacuumlazy.c#lazy_cleanup_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2349-L2360), [nbtree.c#btvacuumcleanup-estimated](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L874-L892), [nbtree.c#btvacuumpage-counting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1345-L1362); measured 200 after a drain plus `VACUUM`, and unchanged after a 10-row `UPDATE` plus `VACUUM` |
| A VACUUM skips index vacuuming when under 2 % of heap pages hold dead items | [vacuumlazy.c#BYPASS_THRESHOLD_PAGES](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L85-L89), [vacuumlazy.c#lazy_vacuum-bypass](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1899-L1940) |
| Autovacuum analyzes when `n_mod_since_analyze` exceeds `50 + 0.1 * reltuples` at the defaults, which is the rule the mandatory tests simulate | [autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3060-L3096), [autovacuum.c#anl-thresholds](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3005-L3018), [guc_tables.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3367-L3375), [guc_tables.c#autovacuum_analyze_scale_factor](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3906-L3914), [config.sgml#autovacuum_analyze_scale_factor](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L8832-L8850); both defaults read back as 50 and 0.1 on each server, and with the maintenance step in front of it the census analyzed 12 of 88 tables on 17.11 and 4 of 87 on 12.2, every one of them a table no churn touched |
| A maintenance `VACUUM` removes nothing the removal horizon still covers, and index vacuuming is entered only when dead TIDs were collected, so a pinned horizon leaves the dense-leaf, dead-entry shape this method misreads | [vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122), [procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815), [procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902), [twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26), [vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052); measured as `dead but not yet removable` 0 on all 66 maintained tables on 17.11 and all 65 on 12.2, with 69 and 68 horizon probes entirely clean |
| `VACUUM (VERBOSE)` reports that count in its own output, and a client sees it whatever `client_min_messages` says | [vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L659-L663), [elog.c#should_output_to_client](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L249-L264); parsed per table on both legs, with 12.2's `dead row versions cannot be removed yet` wording handled by its own parse |
| A maintenance command that could not take its lock, or was cancelled, says so in the log; a foreground `VACUUM` without `SKIP_LOCKED` waits instead | [vacuum.c#skip-lock-not-available](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L828-L860), [autovacuum.c#skip-locked](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2825-L2830); measured 0 such lines on both legs |
| An autovacuum launcher and worker force `statement_timeout`, `transaction_timeout`, `lock_timeout` and `idle_in_transaction_session_timeout` to 0 so that these settings cannot prevent maintenance, and all four are session-scoped | [autovacuum.c#launcher-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L518-L526), [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470), [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2612-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2623-L2631), [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642), [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653); every maintenance statement on 17.11 ran under exactly one recorded set of four zeros, and on 12.2 under three, that server having no `transaction_timeout` |
| The tables a churn touched are the ones whose insert, update or delete counters moved, and the horizon holders are readable from three catalog views | [system_views.sql#n_tup_del](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L680-L682), [system_views.sql#last_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L693), [system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L877-L885), [system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017), [system_views.sql#pg_prepared_xacts](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L421-L427); 66 tables of 88 on 17.11 and 65 of 87 on 12.2, 23 of them on each leg already analyzed by their own recipe |
| `mod_since_analyze` is reset by ANALYZE and added to by a later flush, so it can outlive the ANALYZE that reset it | [pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L328-L338), [pgstat_relation.c#flush-mod_since_analyze](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L845-L860), [pgstat.c#PGSTAT_MIN_INTERVAL](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L110-L122), [pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L636-L655); measured on the 2026-09-14 run as `f88t` reading 9.8 % modified on 12.2 and 0.0 % on 17.11 after the same recipe, and on 2026-09-16 as 12 unchurned tables reading 99.7 % to 120 % modified because their build-phase writes were published after their build-phase `ANALYZE` |
| The counter the census reads is `pg_stat_all_tables.n_mod_since_analyze` | [system_views.sql#n_mod_since_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L689) |
| `REINDEX INDEX` needs `MAINTAIN` on the table in v17, and takes `AccessExclusiveLock` on the index with `ShareLock` on the table | [indexcmds.c#RangeVarCallbackForReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2905-L2912), [indexcmds.c#ReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2822-L2829), [index.c#reindex_index-locks](../../../../raw/postgres-17/src/backend/catalog/index.c#L3600-L3612), [reindex.sgml#MAINTAIN](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml#L300-L316); the role that measured `permission denied for index`, then acceptance after `GRANT MAINTAIN` while `COMMENT` stayed refused, was removed on 2026-09-14; `stage_facts` still measures that the privilege name exists on 17.11 and not on 12.2 |
| `REINDEX CONCURRENTLY` cannot run from a `DO` block | [indexcmds.c#ExecReindex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2736-L2738); measured `REINDEX CONCURRENTLY cannot be executed from a function` on both servers |
| A set-returning function in `FROM` runs before its qualification | [nodeFunctionscan.c#FunctionNext](../../../../raw/postgres-17/src/backend/executor/nodeFunctionscan.c#L59-L112), [execScan.c#ExecScan](../../../../raw/postgres-17/src/backend/executor/execScan.c#L164-L205); measured 57,964 buffer reads in a settled database before the repair, 0 after |
| `pg_relation_size` returns NULL for a dropped relation instead of raising | [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L346-L368) |
| `ShareUpdateExclusiveLock` conflicts with itself | [lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L76-L80) |
| Both timeouts are session-scoped | [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2612-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2623-L2631) |
| VACUUM and ANALYZE share one `reltuples` writer | [vacuum.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1404-L1417), [analyze.c#vac_update_relstats-call](../../../../raw/postgres-17/src/backend/commands/analyze.c#L637-L645) |

## Open Questions

1. **The suite no longer contains the fixtures this heuristic fails.** `p113a`,
   `p113c`, `p65` and `p67` were the four `FALSE NEGATIVE` rows of the 2026-09-11
   run, and the concept page has retired all four. The heuristic is unchanged and
   would still read 0.0 % to 0.1 % wasted on a dead-but-unvacuumed file, so the
   `PASS` on 125 of 126 is a clean sheet against a suite that stopped asking. The
   fourth input that would fix it - the stored entry count against the leaf-page
   capacity the file implies, or `n_dead_tup` on the table - is still not in the
   brief and still not implemented. **The no-defeat rule sharpens this rather
   than settling it**: the rule keeps the suite from building that state by
   accident, and a production server can still reach it under a held snapshot or
   the index-vacuum bypass, where this method would read the file as dense.

2. **The horizon proof is a pair of reads, not an interlock.** Each maintenance
   statement is preceded by one read of `pg_stat_activity`,
   `pg_replication_slots` and `pg_prepared_xacts`, and the run also reads the
   statement's own `dead but not yet removable` count afterwards. A holder that
   appeared and vanished between the probe and the statement would be invisible
   to the first check, and only the `VERBOSE` count would catch it. The concept
   page files the same one-sidedness against itself; this page inherits it.

3. **Fixture 120's state is a coin flip, and the page now says so instead of
   scoring it.** Its precondition held on 4 of the 10 fixture builds this review
   watched, so the suite's one probabilistic fixture contributes a score on some
   runs and an `UNMET PRECONDITION` on others. The concept page's other
   option - exempting `q120` from rule 3's census so the low-target sample
   survives - is not implemented here, because that would change the shared
   definition's fixture rather than this page's harness.

4. **What the removal of the page-local fixtures cost.** The whole acceptance
   stage is gone, and with it every measurement of the heuristic's own surface.
   Named, so nothing is quietly lost: the fifteen comment shapes, including the v1
   payload and the missing-`itup` migration cases and the quoting and
   8,000-character round trips; the eleven candidate-filter shapes and the four
   `pgstatindex` refusals; the ten gate-boundary fixtures; the two forged
   `reltuples = -1` states; the nine-point threshold curve; comment survival
   across both `REINDEX` forms; the privilege matrix including `GRANT MAINTAIN`;
   the `pg_locks` reading for `COMMENT`; `dry_run`; three consecutive runs proving
   idempotence and readback; and the `pg_dump` check. Each of those claims is now
   either deleted or demoted to a reading of source and of the filed text. Comment
   survival and the readback are the two that matter most, because a
   comment-stored baseline that does not survive a rebuild, or that cannot be read
   back, would fail silently.

5. **No fixture exercises the `refresh` branch.** Rule 3 of the decision ladder
   fires when an index is smaller than its stored baseline. Fixture 121 was the
   only one that produced it, and it is retired; the `refresh` count is 0 on both
   legs.

6. **The third gate can fire on sampling noise.** ANALYZE estimates a partial
   index's entry count from the same sample it uses for column statistics, so a
   small or skewed subset can move the stored count without the index moving. The
   suite has one fixture that touches this, 120, whose precondition was unmet on
   both legs, so the effect is currently unmeasured.

7. **The v1-to-v2 migration is no longer measured at all.** The two fixtures that
   proved an old payload re-initializes cleanly went with the acceptance stage.

8. **The baseline ratchets upward on every `update`.** An index measured at 35 %
   wasted is not rebuilt and its baseline is reset to the larger size, so the next
   20 % is counted from there. The multi-run drift is unmeasured, and since the
   threshold curve was removed the page no longer measures where the single step
   lands either.

9. **A stale-high baseline from a restored dump.** `pg_dump` carries the payload,
   so restoring an old dump restores an old baseline; that dump check is also gone
   with the acceptance stage. Rule 3 handles the shrink direction; the case where
   a restored baseline is *lower* than reality was not constructed.

10. **The 13, 14, 15 and 16 majors were not run.** The compatibility claim rests
    on two measured legs plus the feature facts those legs discovered.

11. **One platform, one block size.** Both legs ran on Linux x86_64 at
    `database_block_size` 8192 and `max_data_alignment` 8. The two page-layout
    constants in the text (24 and 16) are derived from that layout.

12. **The uniform 90 % drain is this page's port of rule 2.** Most surviving
    fixtures had no churn of their own, so they are drained by heap block number
    to give the heuristic an "after" state; a differently shaped drain could move
    the `skip`/`measure` boundary for those rows.

13. **`max_reindex` defaults to 1000 in the filed text.** The published run let it
    rebuild 95 indexes in one invocation, one transaction per index. A production
    setting of 1 is recommended in the text's own comment but was not the setting
    measured.

14. **No concurrency test.** Two overlapping runs, and a run racing a
    `DROP INDEX`, are unmeasured; the lock modes are known but the outcomes are
    not.

15. **The simulated auto-analyze over-triggers, and can under-trigger.** A
    backend's pending statistics can be flushed after the `ANALYZE` that reset the
    counter, or before it, so the census's verdict for a given fixture is not
    reproducible between legs: `f88t` read 9.8 % on 12.2 and 0.0 % on 17.11 on
    the 2026-09-14 run, and on 2026-09-16 twelve unchurned tables read 99.7 % to
    120 % modified. The census is also a single pass, where a real launcher
    re-checks every `autovacuum_naptime`.

16. **Forcing the timeouts to zero removes a hazard and leaves a state
    unmeasured.** Every session that issues a `VACUUM` or an `ANALYZE` now runs
    with all its timeouts at 0, which is what the rule asks for and what an
    autovacuum worker does to itself. What no fixture measures is the state the
    rule forbids: a maintenance statement cut short part-done. The churn file
    also lost its `statement_timeout` guard in the process, so a runaway churn
    statement there would now hang rather than fail.

17. **The maintained set is derived from counters, which is a choice with an
    edge.** A table whose churn inserted and deleted the same rows inside one
    statement, or whose writes were rolled back, still moves
    `n_tup_ins`/`n_tup_del` and would be maintained; a table churned only by a
    `TRUNCATE` would not be, because `TRUNCATE` moves no tuple counter. No
    current fixture is in either class, and the run does not check for one.

18. **`clean` is not leg-local, which an earlier teardown in this review found
    the hard way.** Both legs share `$SANDBOX`, so `bash btmaint_suite_v17.sh
    clean` stops the 17 server, confirms that stop, and then deletes the whole
    sandbox - including the 12 leg's data directory and binaries. Cleaning up a
    superseded pass that way left the 12 postmaster unstopped by `pg_ctl`: it
    died with its files, and nothing survived, but that shutdown was not a clean
    one. The published pass was torn down in the order the Cleanup row now
    gives - `stop` on each leg, both confirmed with `database system is shut
    down`, no `postmaster.pid`, no matching process and an empty socket
    directory, and only then one `clean` - so the sandbox this page's numbers
    came from was deleted with nothing running in it. Making `clean` refuse
    while the other leg's cluster is up is a script change for the next run, not
    a retrofit to the text that produced these numbers.

## Source References

- [pgstatindex.c](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c)
- [pgstattuple--1.4--1.5.sql](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql)
- [pgstattuple.control](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.control)
- [pgstattuple.sgml](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml)
- [comment.c](../../../../raw/postgres-17/src/backend/commands/comment.c)
- [objectaddress.c](../../../../raw/postgres-17/src/backend/catalog/objectaddress.c)
- [pg_description.h](../../../../raw/postgres-17/src/include/catalog/pg_description.h)
- [index.c](../../../../raw/postgres-17/src/backend/catalog/index.c)
- [indexcmds.c](../../../../raw/postgres-17/src/backend/commands/indexcmds.c)
- [tablecmds.c](../../../../raw/postgres-17/src/backend/commands/tablecmds.c)
- [pg_class.h](../../../../raw/postgres-17/src/include/catalog/pg_class.h)
- [nbtree.h](../../../../raw/postgres-17/src/include/access/nbtree.h)
- [nbtsort.c](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c)
- [system_functions.sql](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql)
- [dbsize.c](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c)
- [guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c)
- [lock.c](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c)
- [gram.y](../../../../raw/postgres-17/src/backend/parser/gram.y)
- [nodeFunctionscan.c](../../../../raw/postgres-17/src/backend/executor/nodeFunctionscan.c)
- [execScan.c](../../../../raw/postgres-17/src/backend/executor/execScan.c)
- [vacuum.c](../../../../raw/postgres-17/src/backend/commands/vacuum.c)
- [analyze.c](../../../../raw/postgres-17/src/backend/commands/analyze.c)
- [vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c)
- [nbtree.c](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c)
- [autovacuum.c](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c)
- [pgstat_relation.c](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c)
- [pgstat.c](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c)
- [procarray.c](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c)
- [twophase.c](../../../../raw/postgres-17/src/backend/access/transam/twophase.c)
- [elog.c](../../../../raw/postgres-17/src/backend/utils/error/elog.c)
- [system_views.sql](../../../../raw/postgres-17/src/backend/catalog/system_views.sql)
- [config.sgml](../../../../raw/postgres-17/doc/src/sgml/config.sgml)
- [comment.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml)
- [reindex.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml)

## Navigation

- [v17/index](../../index.md)
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
- [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)](btree-index-bloat-core-sql-only.md)
- [B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17 (unverified)](btree-bloat-with-pgstatindex.md)
- [Detecting Inflated Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17 (unverified)](non-btree-index-inflation-comment-baseline.md)
- [A COMMENT-Stored Baseline and Normalized Index Growth for Finding GIN Indexes That Need REINDEX CONCURRENTLY in PostgreSQL 17 (unverified)](gin-reindex-normalized-growth-comment-baseline.md)
- [How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 17 (unverified)](reindex-index-concurrently.md)
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
