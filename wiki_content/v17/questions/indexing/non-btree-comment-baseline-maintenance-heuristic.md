---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# A COMMENT-Stored Baseline Non-B-Tree Index-Maintenance Heuristic for PostgreSQL 12 Through 17 (unverified)

## Contents

- [Question](#question)
  - [Scope settled before drafting](#scope-settled-before-drafting)
  - [Revision after filing](#revision-after-filing)
  - [Second revision: twelve reported defects](#second-revision-twelve-reported-defects)
  - [Third revision: the invalid tests removed](#third-revision-the-invalid-tests-removed)
- [Answer](#answer)
  - [Verdict](#verdict)
  - [What is stored, and where](#what-is-stored-and-where)
  - [Step 1: the plan](#step-1-the-plan)
  - [Step 2: carrying it out](#step-2-carrying-it-out)
  - [What step 2 locks, and what it checks under the locks](#what-step-2-locks-and-what-it-checks-under-the-locks)
  - [How to read the plan](#how-to-read-the-plan)
  - [The decision ladder, in order](#the-decision-ladder-in-order)
  - [Why the candidate filters are there](#why-the-candidate-filters-are-there)
  - [The two tests, and the states that disable them](#the-two-tests-and-the-states-that-disable-them)
  - [The comment survives both REINDEX forms](#the-comment-survives-both-reindex-forms)
  - [Privileges, locks and transactions](#privileges-locks-and-transactions)
  - [What is version-local between 12 and 17](#what-is-version-local-between-12-and-17)
  - [Who writes the table's reltuples](#who-writes-the-tables-reltuples)
  - [The ported fixtures, and the protocols they ran under](#the-ported-fixtures-and-the-protocols-they-ran-under)
  - [The maintenance was not defeated](#the-maintenance-was-not-defeated)
  - [The protocol cross-checks](#the-protocol-cross-checks)
  - [Results on 17.11](#results-on-1711)
  - [Results on 12.2](#results-on-122)
  - [Why the two tests miss where they miss](#why-the-two-tests-miss-where-they-miss)
  - [After an out-of-band rebuild](#after-an-out-of-band-rebuild)
  - [Edge cases, measured](#edge-cases-measured)
  - [Coverage the protocols require, and what this run skipped](#coverage-the-protocols-require-and-what-this-run-skipped)
  - [Known limitations](#known-limitations)
- [Measurement Script](#measurement-script)
  - [How to use the two leg scripts](#how-to-use-the-two-leg-scripts)
  - [The stages](#the-stages)
  - [The cluster settings](#the-cluster-settings)
  - [Prerequisites](#prerequisites)
  - [Where the results land](#where-the-results-land)
  - [The last run](#the-last-run)
  - [The PostgreSQL 17 leg script](#the-postgresql-17-leg-script)
  - [The PostgreSQL 12 leg script](#the-postgresql-12-leg-script)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Follow `AGENTS.md`, in PostgreSQL 17. Question:

Create a PostgreSQL non-B-tree index-maintenance heuristic that works on versions 12
through 17.

**Stored baseline.** Store two values in the index comment:

- the index size;
- its table's estimated tuple count.

Use a versioned payload (format version 2), so that a baseline in an older format is
re-initialized rather than half-read. Handle missing or invalid comment metadata safely,
and keep any existing user-written comment.

**Trigger.** Each time the heuristic runs, compare the current values with the stored
ones. Reindex the index if either of these holds:

- the index size has grown by 30% or more;
- the table tuple count has risen or fallen by 30% or more.

**Tests.** Port every numbered fixture from
[Mandatory GIN Bloat Tests (unverified)](../../common-concepts/mandatory-gin-bloat-tests.md)
and
[Mandatory Non-B-Tree, Non-GIN Bloat Tests (unverified)](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md).

- Force the `VACUUM` and `ANALYZE` sessions' timeouts to 0, and record the settings
  actually in force. If a run finds a defeated maintenance, it fails; it does not score.
- Score every decision against a measured `REINDEX INDEX`.

**Filing and measurement.**

- Keep the page in v17. Link the v12 pages instead of citing another version's source.
- Build and measure both legs, 17.11 and 12.2, end to end from their pins.
- Publish one leg script per version under `## Measurement Script`. Edit the existing
  scripts in place rather than adding new ones.

Create a plan to implement the question before implementing it.

### Scope settled before drafting

The plan was set out in the conversation first, and four answers were taken before any
file was written:

1. **Two values, not three.** The payload stores the index size and the table's
   `reltuples`, each with its own 30 % test. The index's own `reltuples` is left out; see
   [Who writes the table's reltuples](#who-writes-the-tables-reltuples) for what it
   would have measured on GIN and BRIN.
2. **The corpus is the source page's 31 fixtures.** Neither concept page defines numbered
   fixtures: each fixes a protocol and a coverage list and leaves the corpus to the page
   that runs under it. The ported corpus is the one that runs under both, the 31 numbered
   fixtures of
   [Detecting Inflated Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in
   PostgreSQL 17 (unverified)](non-btree-index-inflation-comment-baseline.md), ids and
   recipes unchanged.
3. **A rebuild pays off at 23.08 %.** That is `100 * (1 - 1/1.30)`, the share of the file
   a rebuild returns when an index that grew 30 % goes back to its baseline size. Every
   decision is scored against it.
4. **The page is new, so its two leg scripts are new.** Later revisions edit them in
   place.

### Revision after filing

After this page was filed and pushed on 2026-09-22, the asker wrote:

> remove these test scenarios: - Both false negatives are dead entries that were never cleaned. A VACUUM with index cleanup turned off left them, and neither the index size nor the row count moved enough to trip a test.

The quoted bullet summarized fixtures `h06` and `n11`, the only two whose maintenance step
was `VACUUM (ANALYZE, INDEX_CLEANUP OFF)`. Both were removed from both leg scripts, with
their recipes, their predictions and their two declared exceptions, and both legs were
re-measured end to end. Neither concept page named a fixture, but both then listed "a
`VACUUM` whose index cleanup did not run" as coverage a conforming run must reach, so that
revision declared the row skipped under both protocols. Both concept pages dropped the row
on 2026-09-24, and the third revision took it out of both scripts; see
[Third revision: the invalid tests removed](#third-revision-the-invalid-tests-removed).

### Second revision: twelve reported defects

The asker then filed a review of the page, with the request:

> Follow `AGENTS.md`, in PostgreSQL 17, for the question "A COMMENT-Stored Baseline
> Non-B-Tree Index-Maintenance Heuristic for PostgreSQL 12 Through 17 (unverified)": fix
> these issues.

Each of the twelve findings was checked against the pin before it was fixed, and each was
confirmed. They were fixed in the order the review proposed: the two leg scripts first,
then step 2 and the payload, then the protocol checks and the coverage labels, then a
re-measurement of both legs. `h06` and `n11` stay removed, and neither concept page was
changed.

| # | Finding | What changed |
|---|---|---|
| 1 | the cleanup stage accepted a sandbox path that `..` took out of `.wiki-runtime/tmp`, and stopped the cluster before it checked the path | both scripts resolve every path to its canonical form, require the sandbox to be a plain directory directly under the repository's `.wiki-runtime/tmp` that carries the marker the script writes when it creates one, and check both before they write, stop or delete anything |
| 2 | a stage that failed, a failed regression suite and a mismatch between the page and what ran did not fail the run | every stage's exit status and every required check now stops the run, which exits 1 and stops its cluster; see [The stages](#the-stages) |
| 3 | step 2 read names and human text before it held any lock, then ran its DDL by name | step 2 takes `REINDEX INDEX`'s own two locks first, checks that both names still belong to the objects it read, decides again, and reads and rewrites the comment under those locks; see [What step 2 locks, and what it checks under the locks](#what-step-2-locks-and-what-it-checks-under-the-locks) |
| 4 | one index held in `ACCESS EXCLUSIVE` elsewhere could abort step 2's whole scan | the scan reads the catalogs only, and every size read is inside the per-index exception block |
| 5 | re-running a stage appended a second set of records, and `decide score`, the documented re-run, re-decided on rebuilt indexes | one row per fixture, phase and reading, enforced by the tables; a stage that changes the fixtures runs once and in order, and a stage that only reads replaces its own records |
| 6 | a stray `@nbmaint:` marker in human prose was deleted with the rest of its line, and trailing whitespace was trimmed | the payload is one reserved line, and everything outside it is kept byte for byte; two reserved lines are a conflict, and nothing is written |
| 7 | independent searches for `"v"`, `"sz"` and `"tup"` accepted a payload whose fields sat inside another object | the reserved line must match, whole, the one grammar step 2 writes, before any value is read out of it |
| 8 | an existing install was reused with no evidence of the commit it was built from | the build refuses any commit but the pin and writes a manifest into the install; a reused install must match it file for file |
| 9 | `max_reindex` counted rebuilds that succeeded, not rebuilds started | it counts a rebuild before it starts, so a rebuild that fails uses up its place; measured in edge round G |
| 10 | the BRIN census compared a count of pages, not each page's free space; invariant I9 checked that the `VERBOSE` index line existed, not what it said; and `g08` was said to reach "deleted but not recyclable under a held snapshot" | a page-by-page BRIN free-space comparison (invariant I18); I9 now checks every count on the line against the censuses around its `VACUUM`; the `g08` row is filed as not reached |
| 11 | the score rounded the reclaimed fraction to two decimals before comparing it with the threshold | the threshold is applied to the unrounded fraction; the two decimals are display only |
| 12 | the rounding bound on the tuple test ignored that both counts are rounded, and `n05` and `n12` were called 21.45 % and 11.50 % larger than their rebuilds | both explanations corrected; see [The two tests, and the states that disable them](#the-two-tests-and-the-states-that-disable-them) and [Why the two tests miss where they miss](#why-the-two-tests-miss-where-they-miss) |

The numbers that revision's re-measurement produced were replaced by the third revision's
run.

### Third revision: the invalid tests removed

The request, on 2026-09-24:

> Follow `AGENTS.md`, in PostgreSQL 17. Remove the invalid tests from the question "A
> COMMENT-Stored Baseline Non-B-Tree Index-Maintenance Heuristic for PostgreSQL 12 Through
> 17", and re-run all tests.

Scope, settled with the asker before any edit:

- **The invalid tests are the two coverage rows for "a `VACUUM` whose index cleanup did not
  run"**, one per protocol, which both leg scripts filed before the first fixture existed.
  Earlier that day both governing concept pages stopped listing that case as required
  coverage and stopped declaring it an exception to the no-defeat rule. Its two fixtures,
  `h06` and `n11`, had left this page on 2026-09-22; see
  [Revision after filing](#revision-after-filing). The scripts still declared the case as a
  required row they skipped, and the page still called it a requirement both protocols
  make. The rows left both scripts, and every such sentence was corrected.
- **Kept:** `g08` and `n10`, whose held snapshots are the one exception both protocols
  still declare, and the `defeat` stage, which proves that a defeated maintenance step
  stops the run.
- **"All tests" is both legs' whole default order**, from empty sandboxes: the builds, the
  engine and contrib regression suites, and every stage.
- **Glossary:** the page gained its glossary links. The shared glossary gained an Isolation
  level entry, checked on PostgreSQL 17 only, and a PostgreSQL 17 check of its Back-patch
  entry, which had been checked on 19 only, so this page can link both.

**What the re-run found.** Both legs ran their whole default order three times on Darwin
27 arm64, each time from empty sandboxes and side by side: the filed scripts as a
baseline, the edited scripts, and the edited scripts again once their `score` stage also
wrote `meas.csv`. All three passes agree with the filing on every decision, score,
prediction, invariant and edge verdict, and on every size but `g09`'s, which moves on every
pass. The removal changed only what the `declare` stage files, 31 coverage rows per leg
instead of 33, and the "not built" line of each leg's criteria file. The second pass
showed that `h01`'s overflow and bitmap counts and `g07`'s leaf count, which the coverage
table quotes, were kept only in the fixture database that `clean` deletes. The `score`
stage now writes every census reading to `meas.csv`, and the third pass is the recorded
run. Every number on this page now comes from it, except the earlier passes' figures that
[The last run](#the-last-run) and [Open Questions](#open-questions) name as such.

## Answer

### Verdict

Two texts do it, and both run unchanged on 12.2 and 17.11: step 1, a read-only statement
that decides and prints the commands, and step 2, a [`DO`](../../../glossary.md#plpgsql) block that carries the decision
out, one index per transaction, deciding each index again under [`REINDEX INDEX`](../../../glossary.md#reindex)'s own two
locks before it writes. The baseline is one reserved line of about 70 bytes in the index's
own comment, `@nbmaint:{"v":2,"sz":...,"tup":...,"at":...}`, and any human text in the
comment survives every write and both `REINDEX` forms byte for byte.

Scored against a measured `REINDEX INDEX` on the ported fixtures, at the declared pay-off
of 23.08 %:

| Result | 17.11 | 12.2 |
|---|---|---|
| fixtures scored | 29 | 28; `b11` needs an [operator class](../../../glossary.md#operator-class) 12.2 lacks |
| `PASS` | **22** | **22** |
| `FALSE POSITIVE`: rebuilt, and the rebuild returned less than 23.08 % | **7** | **6** |
| `FALSE NEGATIVE`: skipped, and a rebuild would have returned 23.08 % or more | **0** | **0** |
| rebuilds ordered, and the mean share of the file they returned | 21, 48.8 % | 20, 51.2 % |
| skips, and the mean share a rebuild would have returned | 8, 3.3 % | 8, 3.3 % |
| predictions filed before the first fixture existed that held | 29 of 29 | 28 of 28 |
| step 1's action equal to the two tests recomputed independently | 29 of 29 | 28 of 28 |
| maintenance steps checked the moment they returned, and defeated | 27, 0 | 26, 0 |
| invariants filed before the run that held, cross-checks included | 18 of 18 | 18 of 18 |
| edge-case verdicts, each filed before its case ran, that held | 158 of 158 | 158 of 158 |

**The two tests measure growth, not waste, so every miss is a false positive.**

- **Every false positive is legitimate growth.** The [BRIN](../../../glossary.md#brin) indexes grow with the [heap](../../../glossary.md#heap)'s
  [block](../../../glossary.md#block) count and rebuild to the same size (`b10`, `b11`, `b12`, `b13`); `h04` grew 40 %
  by insertion; `n05` took 50 % more rows through its [pending list](../../../glossary.md#pending-list); `n12` took 20 % more
  rows and crossed 1.30x. Each rebuild returned between 0 and 21.45 % of its file.
- **No fixture left is a false negative.** The only two that were, `h06` and `n11`, were
  removed at the asker's request; see [Revision after filing](#revision-after-filing).
  Neither protocol has required their case since 2026-09-24. A [`VACUUM`](../../../glossary.md#vacuum) that skips [index
  cleanup](../../../glossary.md#index_cleanup) still leaves dead entries neither test can see; see
  [Known limitations](#known-limitations).
- **The [tuple](../../../glossary.md#tuple) test is right in one direction only.** It fired on a fall three times
  (`g08`, `n10`, `s10`) and every rebuild paid off; it fired on a rise three times (`b13`,
  `h04`, `n05`) and none did. Both legs agree.
- **The size test alone fired 15 times on 17.11 and 14 on 12.2.** Eleven paid off on each
  leg; the rest are the BRIN indexes and `n12`.

The two legs agree fixture by fixture: every as-built, maintained and rebuilt size is
byte-identical on 12.2 and 17.11 except `g09`, which is a [sorted GiST build](../../../glossary.md#gist-build-method) on 17 and an
insert-driven one on 12, and the empty [hash index](../../../glossary.md#hash-index) `h07`. On 17.11 every size also equals
the source page's own 17.11 filing except `g09`'s churned file, which that page recorded as
varying between passes.

**A rebuild done elsewhere is invisible unless it shrank the file.** Once the oracle had
rebuilt every fixture, step 1 still ordered 8 more rebuilds on 17.11 and 6 on 12.2, all
of indexes whose rebuilt file was not smaller than the as-built baseline; see
[After an out-of-band rebuild](#after-an-out-of-band-rebuild).

**The maintenance was not defeated, and the rule has teeth.** Every `VACUUM` and
[`ANALYZE`](../../../glossary.md#statistics) session of both runs read its settable timeouts back at 0, every maintenance
step outside the two declared [snapshots](../../../glossary.md#snapshot) left 0 tuples [dead but not yet removable](../../../glossary.md#dead-tuple), and a
deliberately defeated step stopped the run with exit status 1; see
[The maintenance was not defeated](#the-maintenance-was-not-defeated).

### What is stored, and where

[`COMMENT ON INDEX`](../../../glossary.md#comment-on) stores one string per index in `pg_description`, keyed by the index's
[OID](../../../glossary.md#oid), the [`pg_class`](../../../glossary.md#pg_class) class OID and `objsubid = 0`, and a new comment replaces the old one
whole ([pg_description.h#FormData](../../../../raw/postgres-17/src/include/catalog/pg_description.h#L48-L57),
[comment.c#CreateComments](../../../../raw/postgres-17/src/backend/commands/comment.c#L133-L171),
[comment.sgml#replaces](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L87-L93)).
So every write rewrites the whole comment, and keeping the human text is the method's job,
not the server's.

The payload is one **reserved line**: a whole line of the comment that begins with
`@nbmaint:{` and ends with `}`. Everything before and after that line is human text, and
step 2 writes it back byte for byte, trailing spaces and blank lines included. A comment
with no reserved line gets the payload as a new last line:

```text
Search index used by the application.
Second line: an @ sign, a { and a } brace.
@nbmaint:{"v":2,"sz":1064960,"tup":30000,"at":"2026-09-22T18:34:52+00"}
```

| Field | Meaning | Why it is there |
|---|---|---|
| `v` | payload format version, `2` | a payload of any other version is unreadable by definition, so it is re-initialized rather than half-read |
| `sz` | [`pg_relation_size(index)`](../../../glossary.md#relation-size-functions) when the baseline was written, bytes | the brief's first value; the [main fork](../../../glossary.md#fork) only ([system_functions.sql#pg_relation_size](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L285-L289)) |
| `tup` | the table's [`pg_class.reltuples`](../../../glossary.md#reltuples-and-relpages) then, rounded | the brief's second value |
| `at` | when the baseline was written | staleness is otherwise invisible; it takes no part in any decision |

What the comment holds decides what happens to it:

| The comment holds | `baseline` | What step 2 writes |
|---|---|---|
| no reserved line: no comment, or `@nbmaint:` only inside a line of prose | `absent` | the whole comment, a newline, then the payload |
| one reserved line that matches the version-2 grammar exactly | `ok` | the same comment, with that line replaced in place |
| one reserved line of any other shape: another version, a field nested in another object, a repeated or extra field, a string where a number goes | `invalid` | the same, and the baseline starts again |
| two or more reserved lines | `ambiguous` | nothing: the plan says `conflict` until a person removes one |

A reserved line is a baseline only when the whole line matches the one grammar step 2
writes: `v` equal to the format version, then `sz`, `tup` and `at`, in that order, with no
leading zeros, `tup` allowed to be `-1`, and nothing before or after. `sz` and `tup` are
read out of that single match and nowhere else, so a field inside another object, or a
field written twice, cannot supply a baseline. The lines are found in newline-sensitive
mode, the `n` flag and the `(?n)` prefix, in which `^` and `$` match at every line end and
`.` never crosses one
([regexp.c#parse_re_flags-n](../../../../raw/postgres-17/src/backend/utils/adt/regexp.c#L418-L420),
[func.sgml#newline-sensitive](../../../../raw/postgres-17/doc/src/sgml/func.sgml#L7449-L7458)).
Edge round A exercised every row of the table.

The payload is plain text, parsed with regexes rather than cast to `jsonb`. A regex that
does not match returns NULL
([regexp.c#textregexsubstr](../../../../raw/postgres-17/src/backend/utils/adt/regexp.c#L583-L604),
[regexp.c#regexp_match](../../../../raw/postgres-17/src/backend/utils/adt/regexp.c#L1367-L1390)),
while a `jsonb` cast of a malformed payload raises and aborts the statement for every
index. The guard that would make the cast safe, `pg_input_is_valid()`, exists on 17
([pg_proc.dat#pg_input_is_valid](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7202-L7204))
and was measured absent on 12.2.

A reserved line is still a claim on a line of the comment: a person who writes a line of
exactly that shape has written a payload as far as the method can tell.

### Step 1: the plan

Read-only. It decides, prints the exact commands, and writes nothing.

```sql
-- Non-B-tree index-maintenance heuristic, step 1: decide, write nothing.
-- One text, unchanged on PostgreSQL 12 through 17.
--
--   params   the two thresholds and the payload format version
--   cand     every valid non-B-tree index this session can see
--   parsed   the index's comment, cut around its one reserved @nbmaint: line
--   gate     whether that line is a usable baseline
--   decided  the size test and the table tuple-count test
--   staged   the action: the first rule that matches decides
--
-- Reindex when the index has grown by 30 % or more since its baseline, or
-- when its table's estimated tuple count has risen or fallen by 30 % or more.
-- Nothing here writes.  Step 2 carries the plan out.

SET /* wiki_nbmaint_statement_timeout */ statement_timeout = '60s';
SET /* wiki_nbmaint_lock_timeout */ lock_timeout = '5s';

WITH params AS (
    SELECT 1.30::numeric AS grow_ratio,   -- index-size test
           0.30::numeric AS tuple_ratio,  -- table tuple-count test, either way
           2::numeric    AS fmt           -- payload format version
),
cand AS MATERIALIZED (
    SELECT c.oid                   AS idx_oid,
           n.nspname               AS schema_name,
           c.relname               AS index_name,
           t.relname               AS table_name,
           a.amname                AS access_method,
           pg_get_userbyid(c.relowner) AS owner_name,
           pg_relation_size(c.oid) AS cur_bytes,
           t.reltuples::numeric    AS cur_tuples,
           d.description           AS cmt,
           pg_has_role(c.relowner, 'USAGE') AS owns_index
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_index x     ON x.indexrelid = c.oid
      JOIN pg_class t     ON t.oid = x.indrelid
      JOIN pg_am a        ON a.oid = c.relam
      LEFT JOIN pg_description d ON d.objoid = c.oid
                               AND d.classoid = 'pg_class'::regclass
                               AND d.objsubid = 0
     WHERE a.amname <> 'btree'                -- the brief's scope
       AND c.relkind = 'i'                    -- 'I', a partitioned index, has no storage
       AND x.indisvalid AND x.indisready AND x.indislive
       AND NOT pg_is_other_temp_schema(c.relnamespace)
       AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
       -- step 2 narrows the pipeline to one index by setting this for its
       -- own transaction only; in any other session it is unset, and every
       -- candidate is read
       AND (nullif(current_setting('nbmaint.only_index', true), '') IS NULL
            OR c.oid = nullif(current_setting('nbmaint.only_index', true), '')::oid)
),
parsed AS MATERIALIZED (
    -- The payload is one reserved line: a whole line of the comment that
    -- starts with "@nbmaint:{" and ends with "}".  Everything before and
    -- after that line is the human text, and is kept byte for byte.
    SELECT c.*, p.grow_ratio, p.tuple_ratio, p.fmt, r.n_reserved,
           CASE WHEN r.n_reserved = 1 THEN r.split[1] END AS before_line,
           CASE WHEN r.n_reserved = 1 THEN r.split[2] END AS reserved_line,
           CASE WHEN r.n_reserved = 1 THEN r.split[3] END AS after_line
      FROM cand c
     CROSS JOIN params p
     CROSS JOIN LATERAL (
          SELECT (SELECT count(*)
                    FROM regexp_matches(coalesce(c.cmt, ''),
                                        '^@nbmaint:\{.*\}$', 'gn'))    AS n_reserved,
                 regexp_match(coalesce(c.cmt, ''),
                              '^(.*\n)?(@nbmaint:\{[^\n]*\})(\n.*)?$') AS split) r
     WHERE c.cur_bytes IS NOT NULL            -- NULL: dropped since the catalog read
),
gate AS MATERIALIZED (
    SELECT s.*,
           CASE WHEN s.n_reserved = 0 THEN 'absent'
                WHEN s.n_reserved > 1 THEN 'ambiguous'
                WHEN v.pay IS NULL    THEN 'invalid'
                ELSE 'ok' END                                  AS baseline,
           v.pay[1]::numeric                                   AS base_bytes,
           v.pay[2]::numeric                                   AS base_tuples,
           -- where a new payload goes: in place of the one reserved line, or
           -- on a new last line of a comment that has none
           CASE WHEN s.n_reserved = 0 THEN coalesce(s.cmt || E'\n', '')
                WHEN s.n_reserved = 1 THEN coalesce(s.before_line, '') END AS keep_before,
           CASE WHEN s.n_reserved = 0 THEN ''
                WHEN s.n_reserved = 1 THEN coalesce(s.after_line, '') END  AS keep_after,
           -- reltuples is -1 on a table nothing has counted yet, from
           -- PostgreSQL 14 on; 12 and 13 store 0 there instead
           (s.cur_tuples < 0)                                  AS tuples_unknown
      FROM parsed s
     CROSS JOIN LATERAL (
          -- the whole reserved line, matched against the one grammar step 2
          -- writes; no value is read out of a line that does not match it all
          SELECT regexp_match(s.reserved_line,
                     '^@nbmaint:\{"v":' || s.fmt
                     || ',"sz":(0|[1-9][0-9]{0,24}),"tup":(-1|0|[1-9][0-9]{0,24})'
                     || ',"at":"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'
                     || '[+-][0-9]{2}(?::[0-9]{2})?"\}$')      AS pay) v
),
decided AS MATERIALIZED (
    SELECT g.*,
           CASE WHEN g.baseline = 'ok' AND g.base_bytes > 0
                THEN round(g.cur_bytes / g.base_bytes, 4) END      AS size_ratio,
           CASE WHEN g.baseline = 'ok' AND g.base_tuples > 0 AND NOT g.tuples_unknown
                THEN round(g.cur_tuples / g.base_tuples, 4) END    AS tuple_ratio_now,
           (g.baseline = 'ok' AND g.base_bytes > 0
            AND g.cur_bytes >= g.base_bytes * g.grow_ratio)       AS size_test,
           (g.baseline = 'ok' AND NOT g.tuples_unknown AND g.base_tuples >= 0
            AND CASE WHEN g.base_tuples = 0 THEN g.cur_tuples > 0
                     ELSE abs(g.cur_tuples - g.base_tuples)
                          >= g.base_tuples * g.tuple_ratio END)   AS tuple_test,
           (g.baseline = 'ok' AND g.cur_bytes < g.base_bytes)     AS shrank
      FROM gate g
),
staged AS MATERIALIZED (
    SELECT d.*,
           CASE WHEN NOT d.owns_index             THEN 'blocked'
                WHEN d.baseline = 'ambiguous'     THEN 'conflict'
                WHEN d.baseline <> 'ok'           THEN 'initialize'
                WHEN d.shrank                     THEN 'refresh'
                WHEN d.size_test OR d.tuple_test  THEN 'reindex'
                ELSE 'skip' END                   AS action
      FROM decided d
)
SELECT /* wiki_nbmaint_plan_12_17 */
       s.schema_name,
       s.index_name,
       s.table_name,
       s.access_method,
       s.action,
       s.baseline,
       pg_size_pretty(s.cur_bytes)           AS index_size,
       pg_size_pretty(s.base_bytes)          AS baseline_size,
       s.size_ratio,
       s.cur_tuples                          AS table_tuples,
       s.base_tuples                         AS baseline_tuples,
       s.tuple_ratio_now                     AS tuple_ratio,
       array_to_string(array_remove(ARRAY[
           CASE WHEN NOT s.owns_index THEN 'not the index owner: nothing can be written' END,
           CASE WHEN s.baseline = 'ambiguous'
                THEN 'more than one reserved @nbmaint: line: nothing written until one is removed' END,
           CASE WHEN s.baseline = 'invalid'
                THEN 'reserved @nbmaint: line is not a version-2 payload: replaced' END,
           CASE WHEN s.tuples_unknown THEN 'table reltuples unknown: tuple test cannot fire' END,
           CASE WHEN s.baseline = 'ok' AND s.base_tuples < 0
                THEN 'baseline tuple count unknown: tuple test cannot fire' END,
           CASE WHEN s.baseline = 'ok' AND s.base_tuples = 0
                THEN 'baseline tuple count was zero' END,
           CASE WHEN s.shrank THEN 'index smaller than its baseline: rebuilt elsewhere' END,
           CASE WHEN s.size_test THEN 'size test fired' END,
           CASE WHEN s.tuple_test THEN 'tuple test fired' END
       ], NULL), '; ')                       AS notes,
       -- The comment is written now for initialize and refresh.  A reindex
       -- row has none: its new baseline is only known after the rebuild.
       -- A printed COMMENT is only as fresh as this read; step 2 re-reads
       -- the comment under its locks before it writes one.
       CASE WHEN s.action IN ('initialize', 'refresh')
            THEN format('COMMENT ON INDEX %I.%I IS %L', s.schema_name, s.index_name,
                   s.keep_before
                   || '@nbmaint:{"v":' || s.fmt || ',"sz":' || s.cur_bytes
                   || ',"tup":' || round(GREATEST(s.cur_tuples, -1))
                   || ',"at":"' || to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SSOF') || '"}'
                   || s.keep_after) END
                                             AS comment_command,
       CASE WHEN s.action = 'reindex'
            THEN format('REINDEX INDEX %I.%I', s.schema_name, s.index_name) END
                                             AS reindex_command
  FROM staged s
 ORDER BY CASE s.action WHEN 'reindex' THEN 0 WHEN 'refresh' THEN 1
                        WHEN 'initialize' THEN 2 WHEN 'conflict' THEN 3
                        WHEN 'blocked' THEN 4 ELSE 5 END,
          s.cur_bytes DESC, s.schema_name, s.index_name;
```

[`statement_timeout`](../../../glossary.md#statement_timeout-and-lock_timeout) and `lock_timeout` are both [`PGC_USERSET`](../../../glossary.md#guc-context), so the two `SET` lines
apply at session scope and need neither a reload nor a restart
([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620),
[guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)).
Step 1 reads [catalogs](../../../glossary.md#catalog) and file sizes only; over the suite database it took 22.9 ms on
17.11 and 17.6 ms on 12.2, measured under the lock. It is one statement, and reading a
size waits for any lock that excludes `AccessShareLock`, so one candidate index held in
[`ACCESS EXCLUSIVE`](../../../glossary.md#accessexclusivelock) for longer than `lock_timeout` cancels step 1 as a whole: edge round H
measured `canceling statement due to lock timeout`, from its 5-second `lock_timeout`, on
both servers. Step 2 reads sizes one index at a time and carries on; see
[What step 2 locks, and what it checks under the locks](#what-step-2-locks-and-what-it-checks-under-the-locks).

### Step 2: carrying it out

Run it at the top level, not inside `BEGIN`. It commits once per index, and a `DO` block
can commit only when it is not inside a transaction block: [`ProcessUtility`](../../../glossary.md#utility-command) marks the
`DO` atomic otherwise, and [`_SPI_commit`](../../../glossary.md#spi) refuses an atomic context with `invalid
transaction termination`, which both servers returned when the block was run inside
`BEGIN`
([utility.c#isAtomicContext](../../../../raw/postgres-17/src/backend/tcop/utility.c#L551),
[utility.c#DoStmt](../../../../raw/postgres-17/src/backend/tcop/utility.c#L706-L708),
[spi.c#_SPI_commit](../../../../raw/postgres-17/src/backend/executor/spi.c#L227-L241)).

```sql
-- Non-B-tree index-maintenance heuristic, step 2: carry out the plan.
-- One text, unchanged on PostgreSQL 12 through 17.  Run it at the top level,
-- not inside BEGIN: it commits once per index, which a DO block can do only
-- when no transaction block is open around it.
--
-- The CTE pipeline below, from "WITH params AS (" through the end of the
-- staged CTE, is byte-identical to step 1's.  Step 2 runs it once per index,
-- narrowed to that index by the nbmaint.only_index setting: first with no
-- lock taken, to see whether the index needs anything, then again under the
-- two locks REINDEX INDEX takes, and it acts on that second answer only.
-- The comment is read and rewritten under those locks, so no other COMMENT
-- can land between the read and the write.
--
-- statement_timeout bounds the whole run, because a DO block is one
-- statement; lock_timeout bounds each lock wait, and an index whose lock
-- cannot be had in time is skipped for this run rather than failing it.
-- Every read after a lock must see what committed before the lock was
-- granted, which read committed guarantees and the stricter levels do not.

SET /* wiki_nbmaint_apply_statement_timeout */ statement_timeout = '1h';
SET /* wiki_nbmaint_apply_lock_timeout */ lock_timeout = '5s';
SET /* wiki_nbmaint_apply_isolation */ default_transaction_isolation = 'read committed';

DO /* wiki_nbmaint_apply_12_17 */ $nbmaint$
DECLARE
    dry_run     boolean := false;  -- true: report the plan, lock nothing, write nothing
    max_reindex integer := 1000;   -- cap on the rebuilds one run may start
    v_oid        oid[];
    i            integer;
    pass         integer;
    ix           record;           -- the pipeline's row for this index
    first_action text;             -- the action the unlocked pass decided
    locked       boolean;
    seen         boolean;
    done         text;
    r_oid        oid;
    r_bytes      numeric;
    r_tuples     numeric;
    n_re         integer := 0;
    n_start      integer := 0;
    n_init       integer := 0;
    n_ref        integer := 0;
    n_block      integer := 0;
    n_confl      integer := 0;
    n_fail       integer := 0;
    n_gone       integer := 0;
    n_capped     integer := 0;
    n_moved      integer := 0;
BEGIN
-- The candidates, from the catalogs alone: nothing here opens or locks an
-- index, so a lock held elsewhere cannot stop the run before it starts.  It
-- keeps every index that is not B-tree, and the pipeline applies the other
-- filters.  Largest first, by the page count the catalog last recorded.
SELECT array_agg(c.oid ORDER BY c.relpages DESC, c.oid)
  INTO v_oid
  FROM pg_class c
  JOIN pg_am a ON a.oid = c.relam
 WHERE c.relkind = 'i' AND a.amname <> 'btree';

FOR i IN 1 .. COALESCE(array_length(v_oid, 1), 0) LOOP
    first_action := NULL; locked := false; seen := false; done := NULL;
    BEGIN
        -- narrows the pipeline to this one index until this transaction ends
        PERFORM set_config('nbmaint.only_index', v_oid[i]::text, true);
        FOR pass IN 1 .. 2 LOOP
            IF pass = 2 THEN
                -- REINDEX INDEX's two locks, in its order: SHARE on the table,
                -- then ACCESS EXCLUSIVE on the index.  ALTER INDEX ... OWNER TO
                -- the owner it already has changes nothing and takes that index
                -- lock, which also holds off every other COMMENT on the index.
                EXECUTE format('LOCK TABLE %I.%I IN SHARE MODE',
                               ix.schema_name, ix.table_name);
                EXECUTE format('ALTER INDEX %I.%I OWNER TO %I',
                               ix.schema_name, ix.index_name, ix.owner_name);
                locked := true;
                -- Nothing can rename or drop either object now, so both names
                -- must still be the objects the unlocked pass read.
                SELECT c.oid INTO r_oid
                  FROM pg_class c
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = ix.schema_name AND c.relname = ix.index_name;
                IF r_oid IS DISTINCT FROM v_oid[i] OR NOT EXISTS (
                       SELECT 1
                         FROM pg_index x
                         JOIN pg_class t ON t.oid = x.indrelid
                         JOIN pg_namespace n ON n.oid = t.relnamespace
                        WHERE x.indexrelid = v_oid[i]
                          AND n.nspname = ix.schema_name
                          AND t.relname = ix.table_name) THEN
                    RAISE EXCEPTION 'renamed, dropped or re-created since it was read'
                          USING ERRCODE = 'object_not_in_prerequisite_state';
                END IF;
            END IF;
WITH params AS (
    SELECT 1.30::numeric AS grow_ratio,   -- index-size test
           0.30::numeric AS tuple_ratio,  -- table tuple-count test, either way
           2::numeric    AS fmt           -- payload format version
),
cand AS MATERIALIZED (
    SELECT c.oid                   AS idx_oid,
           n.nspname               AS schema_name,
           c.relname               AS index_name,
           t.relname               AS table_name,
           a.amname                AS access_method,
           pg_get_userbyid(c.relowner) AS owner_name,
           pg_relation_size(c.oid) AS cur_bytes,
           t.reltuples::numeric    AS cur_tuples,
           d.description           AS cmt,
           pg_has_role(c.relowner, 'USAGE') AS owns_index
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_index x     ON x.indexrelid = c.oid
      JOIN pg_class t     ON t.oid = x.indrelid
      JOIN pg_am a        ON a.oid = c.relam
      LEFT JOIN pg_description d ON d.objoid = c.oid
                               AND d.classoid = 'pg_class'::regclass
                               AND d.objsubid = 0
     WHERE a.amname <> 'btree'                -- the brief's scope
       AND c.relkind = 'i'                    -- 'I', a partitioned index, has no storage
       AND x.indisvalid AND x.indisready AND x.indislive
       AND NOT pg_is_other_temp_schema(c.relnamespace)
       AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
       -- step 2 narrows the pipeline to one index by setting this for its
       -- own transaction only; in any other session it is unset, and every
       -- candidate is read
       AND (nullif(current_setting('nbmaint.only_index', true), '') IS NULL
            OR c.oid = nullif(current_setting('nbmaint.only_index', true), '')::oid)
),
parsed AS MATERIALIZED (
    -- The payload is one reserved line: a whole line of the comment that
    -- starts with "@nbmaint:{" and ends with "}".  Everything before and
    -- after that line is the human text, and is kept byte for byte.
    SELECT c.*, p.grow_ratio, p.tuple_ratio, p.fmt, r.n_reserved,
           CASE WHEN r.n_reserved = 1 THEN r.split[1] END AS before_line,
           CASE WHEN r.n_reserved = 1 THEN r.split[2] END AS reserved_line,
           CASE WHEN r.n_reserved = 1 THEN r.split[3] END AS after_line
      FROM cand c
     CROSS JOIN params p
     CROSS JOIN LATERAL (
          SELECT (SELECT count(*)
                    FROM regexp_matches(coalesce(c.cmt, ''),
                                        '^@nbmaint:\{.*\}$', 'gn'))    AS n_reserved,
                 regexp_match(coalesce(c.cmt, ''),
                              '^(.*\n)?(@nbmaint:\{[^\n]*\})(\n.*)?$') AS split) r
     WHERE c.cur_bytes IS NOT NULL            -- NULL: dropped since the catalog read
),
gate AS MATERIALIZED (
    SELECT s.*,
           CASE WHEN s.n_reserved = 0 THEN 'absent'
                WHEN s.n_reserved > 1 THEN 'ambiguous'
                WHEN v.pay IS NULL    THEN 'invalid'
                ELSE 'ok' END                                  AS baseline,
           v.pay[1]::numeric                                   AS base_bytes,
           v.pay[2]::numeric                                   AS base_tuples,
           -- where a new payload goes: in place of the one reserved line, or
           -- on a new last line of a comment that has none
           CASE WHEN s.n_reserved = 0 THEN coalesce(s.cmt || E'\n', '')
                WHEN s.n_reserved = 1 THEN coalesce(s.before_line, '') END AS keep_before,
           CASE WHEN s.n_reserved = 0 THEN ''
                WHEN s.n_reserved = 1 THEN coalesce(s.after_line, '') END  AS keep_after,
           -- reltuples is -1 on a table nothing has counted yet, from
           -- PostgreSQL 14 on; 12 and 13 store 0 there instead
           (s.cur_tuples < 0)                                  AS tuples_unknown
      FROM parsed s
     CROSS JOIN LATERAL (
          -- the whole reserved line, matched against the one grammar step 2
          -- writes; no value is read out of a line that does not match it all
          SELECT regexp_match(s.reserved_line,
                     '^@nbmaint:\{"v":' || s.fmt
                     || ',"sz":(0|[1-9][0-9]{0,24}),"tup":(-1|0|[1-9][0-9]{0,24})'
                     || ',"at":"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'
                     || '[+-][0-9]{2}(?::[0-9]{2})?"\}$')      AS pay) v
),
decided AS MATERIALIZED (
    SELECT g.*,
           CASE WHEN g.baseline = 'ok' AND g.base_bytes > 0
                THEN round(g.cur_bytes / g.base_bytes, 4) END      AS size_ratio,
           CASE WHEN g.baseline = 'ok' AND g.base_tuples > 0 AND NOT g.tuples_unknown
                THEN round(g.cur_tuples / g.base_tuples, 4) END    AS tuple_ratio_now,
           (g.baseline = 'ok' AND g.base_bytes > 0
            AND g.cur_bytes >= g.base_bytes * g.grow_ratio)       AS size_test,
           (g.baseline = 'ok' AND NOT g.tuples_unknown AND g.base_tuples >= 0
            AND CASE WHEN g.base_tuples = 0 THEN g.cur_tuples > 0
                     ELSE abs(g.cur_tuples - g.base_tuples)
                          >= g.base_tuples * g.tuple_ratio END)   AS tuple_test,
           (g.baseline = 'ok' AND g.cur_bytes < g.base_bytes)     AS shrank
      FROM gate g
),
staged AS MATERIALIZED (
    SELECT d.*,
           CASE WHEN NOT d.owns_index             THEN 'blocked'
                WHEN d.baseline = 'ambiguous'     THEN 'conflict'
                WHEN d.baseline <> 'ok'           THEN 'initialize'
                WHEN d.shrank                     THEN 'refresh'
                WHEN d.size_test OR d.tuple_test  THEN 'reindex'
                ELSE 'skip' END                   AS action
      FROM decided d
)
            SELECT s.* INTO ix FROM staged s;
            seen := FOUND;
            EXIT WHEN NOT seen OR pass = 2;
            first_action := ix.action;
            -- nothing to lock for, or nothing this run may start
            EXIT WHEN dry_run OR ix.action IN ('skip', 'blocked', 'conflict')
                   OR (ix.action = 'reindex' AND n_start >= max_reindex);
        END LOOP;

        IF NOT seen THEN
            -- no row: dropped, or not a candidate at all, such as another
            -- session's temporary index or an invalid one
            IF locked OR NOT EXISTS (SELECT 1 FROM pg_class WHERE oid = v_oid[i]) THEN
                n_gone := n_gone + 1;
                RAISE NOTICE 'nbmaint: index % dropped or no longer a candidate, skipped',
                             v_oid[i];
            END IF;
        ELSIF ix.action = 'blocked' THEN
            n_block := n_block + 1;
            RAISE NOTICE 'nbmaint: %.% is not owned by %, nothing written',
                         ix.schema_name, ix.index_name, current_user;
        ELSIF ix.action = 'conflict' THEN
            n_confl := n_confl + 1;
            RAISE NOTICE 'nbmaint: %.% has more than one reserved @nbmaint: line, nothing written',
                         ix.schema_name, ix.index_name;
        ELSIF NOT locked AND dry_run THEN
            IF ix.action <> 'skip' THEN
                RAISE NOTICE 'nbmaint: %.% -> % (dry run, nothing written)',
                             ix.schema_name, ix.index_name, ix.action;
            END IF;
        ELSIF ix.action = 'reindex' AND n_start >= max_reindex THEN
            n_capped := n_capped + 1;
            RAISE NOTICE 'nbmaint: %.% needs a rebuild, max_reindex % reached',
                         ix.schema_name, ix.index_name, max_reindex;
        ELSIF locked THEN
            -- the answer given under the locks is the one acted on
            IF ix.action IS DISTINCT FROM first_action THEN
                n_moved := n_moved + 1;
                RAISE NOTICE 'nbmaint: %.% was % before the locks and % under them',
                             ix.schema_name, ix.index_name, first_action, ix.action;
            END IF;
            IF ix.action IN ('reindex', 'initialize', 'refresh') THEN
                r_bytes := ix.cur_bytes;
                r_tuples := ix.cur_tuples;
                IF ix.action = 'reindex' THEN
                    -- counted before it starts, so a rebuild that fails still
                    -- uses up its place under max_reindex
                    n_start := n_start + 1;
                    EXECUTE format('REINDEX /* wiki_nbmaint_reindex */ INDEX %I.%I',
                                   ix.schema_name, ix.index_name);
                    -- the new baseline is the rebuilt file, and the table
                    -- count the rebuild's own heap scan wrote
                    SELECT pg_relation_size(c.oid), t.reltuples::numeric
                      INTO r_bytes, r_tuples
                      FROM pg_class c
                      JOIN pg_index x ON x.indexrelid = c.oid
                      JOIN pg_class t ON t.oid = x.indrelid
                     WHERE c.oid = v_oid[i];
                END IF;
                EXECUTE format('COMMENT /* wiki_nbmaint_comment */ ON INDEX %I.%I IS %L',
                               ix.schema_name, ix.index_name,
                               ix.keep_before
                               || '@nbmaint:{"v":' || ix.fmt || ',"sz":' || r_bytes
                               || ',"tup":' || round(GREATEST(r_tuples, -1))
                               || ',"at":"' || to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SSOF') || '"}'
                               || ix.keep_after);
                done := ix.action;
            END IF;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        -- Everything this index's transaction did is rolled back and its
        -- locks released: it keeps its old baseline and is looked at again
        -- on the next run.
        n_fail := n_fail + 1;
        done := NULL;
        RAISE WARNING 'nbmaint: %: nothing written: % (SQLSTATE %)',
                      v_oid[i]::regclass, SQLERRM, SQLSTATE;
    END;
    COMMIT;
    IF done IS NOT NULL THEN
        CASE done
            WHEN 'reindex'    THEN n_re   := n_re + 1;
            WHEN 'initialize' THEN n_init := n_init + 1;
            ELSE                   n_ref  := n_ref + 1;
        END CASE;
        RAISE NOTICE 'nbmaint: %.% -> % (sz %, tup %)', ix.schema_name, ix.index_name,
                     done, r_bytes, round(GREATEST(r_tuples, -1));
    END IF;
END LOOP;

RAISE NOTICE 'nbmaint: reindex=% initialize=% refresh=% blocked=% conflict=% failed=% gone=% capped=% started=% changed=% dry_run=%',
             n_re, n_init, n_ref, n_block, n_confl, n_fail, n_gone, n_capped,
             n_start, n_moved, dry_run;
END
$nbmaint$;
```

The pipeline in step 2, from `WITH params AS (` through the end of the `staged` [CTE](../../../glossary.md#common-table-expression), is
byte-identical to the same region of step 1: 104 lines, SHA-256 `4e22b4c2f2757314…` in
both texts, checked by both leg scripts on every run. Only what surrounds it differs, so
the two tests, the payload grammar and the rule for keeping the human text are each
defined once.

### What step 2 locks, and what it checks under the locks

Step 2 acts on nothing it read before it held the locks it needs, and it decides each index
twice. Per index, in its own transaction:

1. **The candidate list comes from the catalogs alone.** The scan reads `pg_class` and
   `pg_am` and opens no index, so a lock held on one index elsewhere cannot stop the run
   before it starts. Reading a size is not free: `pg_relation_size` takes
   `AccessShareLock` on the relation before it looks at it
   ([dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L371),
   [relation.c#try_relation_open](../../../../raw/postgres-17/src/backend/access/common/relation.c#L88-L108)),
   and the earlier text read every candidate's size in its scan, outside any exception
   block, so one index held in `ACCESS EXCLUSIVE` elsewhere cancelled the whole run.
2. **Pass 1, unlocked.** The pipeline runs narrowed to this one index by
   `nbmaint.only_index`, a [custom setting](../../../glossary.md#guc) step 2 sets for its own transaction only
   ([pg_proc.dat#set_config](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L6270-L6273),
   [pg_proc.dat#current_setting-missing_ok](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L6268-L6269)).
   Step 1, in any other session, reads it as unset, or as empty once a transaction that
   set it has ended, and reads every candidate; both servers measured both. If the answer
   is `skip`, `blocked` or `conflict`, or the rebuild cap is spent, nothing is locked. The
   size read is inside the index's exception block, so a lock timeout there costs that
   index alone: edge round H held one index in `ACCESS EXCLUSIVE` for a whole run, and
   step 2 counted it failed with `SQLSTATE 55P03` and finished every other one.
3. **The two locks `REINDEX INDEX` takes, in its order.** `LOCK TABLE ... IN SHARE MODE`,
   then `ALTER INDEX ... OWNER TO` the owner the index already has. `ReindexIndex` locks
   the table before the index "to avoid deadlock hazard", and the plain form's pair is
   [`ShareLock`](../../../glossary.md#lock-mode) on the table and `AccessExclusiveLock` on the index
   ([indexcmds.c#ReindexIndex-lock-order](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2812-L2829),
   [indexcmds.c#RangeVarCallbackForReindexIndex-table-lockmode](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2871-L2872),
   [index.c#reindex_index-locks](../../../../raw/postgres-17/src/backend/catalog/index.c#L3601-L3614)).
   `ALTER INDEX ... OWNER TO` takes `AccessExclusiveLock`, checks ownership the way
   `COMMENT` does, and on an index whose owner does not change neither writes nor warns
   ([tablecmds.c#AlterTableGetLockLevel-ChangeOwner](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L4542-L4547),
   [tablecmds.c#RangeVarCallbackForAlterRelation-ownership](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L17904-L17906),
   [tablecmds.c#ATExecChangeOwner-index](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14543-L14562),
   [tablecmds.c#ATExecChangeOwner-noop](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14614-L14618)).
   Both servers measured it: `AccessExclusiveLock` held, nothing printed, and the index's
   `pg_class` row kept its [`xmin`](../../../glossary.md#xmin-and-xmax). Every `COMMENT` takes [`ShareUpdateExclusiveLock`](../../../glossary.md#shareupdateexclusivelock) on its
   object, which that lock excludes
   ([comment.c#CommentObject-ownership](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L76),
   [lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L64-L104)),
   so from here to the commit no other comment on the index can land. `LOCK TABLE` in
   `SHARE` mode needs `MAINTAIN`, `UPDATE`, `DELETE` or `TRUNCATE` on the table
   ([lockcmds.c#LockTableAclCheck](../../../../raw/postgres-17/src/backend/commands/lockcmds.c#L280-L299)),
   which its owner has.
4. **Identity, under the locks.** An index rename needs `ShareUpdateExclusiveLock` on the
   index and a table rename `AccessExclusiveLock` on the table
   ([tablecmds.c#RenameRelation-lockmode](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L4101-L4106)),
   and both conflict with what step 2 now holds. So the names are fixed, and step 2 checks
   that the index name still resolves to the OID the scan listed and that the table name
   is still that index's table. If a rename, or a drop and a re-create, moved either
   before the locks were granted, step 2 raises and the index's transaction rolls back.
   Edge round K renamed an index and created another under its old name while step 2
   waited: step 2 refused it with `SQLSTATE 55000`, and neither index was written.
5. **Pass 2, under the locks.** The same pipeline again, and its answer is the one step 2
   acts on. Edge round J rewrote a payload to the file's true size while step 2 waited:
   the answer went from `reindex` to `skip`, and nothing was rebuilt. Edge round I rewrote
   the human text while step 2 waited: the text written then is the text step 2 kept.
6. **The write.** `initialize` and `refresh` write the comment. `reindex` is counted
   against `max_reindex` before it starts, which a failure cannot undo because an
   exception block rolls back the database, not the block's local variables
   ([plpgsql.sgml#trapping-errors](../../../../raw/postgres-17/doc/src/sgml/plpgsql.sgml#L2856-L2860));
   then the rebuild, then the size and count read again, then the comment. One commit
   ends the index's transaction and releases both locks.

**[Read committed](../../../glossary.md#isolation-level) is required, and step 2 sets it.** Each transaction step 2 starts after a
`COMMIT` takes the default isolation level
([plpgsql.sgml#transaction-defaults](../../../../raw/postgres-17/doc/src/sgml/plpgsql.sgml#L3743-L3744)),
and only read committed takes a new snapshot for each statement; repeatable read fixes the
snapshot at the transaction's first statement, which here comes before the locks
([mvcc.sgml#read-committed](../../../../raw/postgres-17/doc/src/sgml/mvcc.sgml#L317-L333),
[mvcc.sgml#repeatable-read](../../../../raw/postgres-17/doc/src/sgml/mvcc.sgml#L508-L513)).
The third `SET` line therefore sets `default_transaction_isolation`, a `PGC_USERSET`
setting, for the session
([guc_tables.c#default_transaction_isolation](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4820-L4827)).

**What it costs.** Every index step 2 writes to is held in `ACCESS EXCLUSIVE` for its
transaction: for `initialize` and `refresh` only while the comment is written, for
`reindex` for the whole rebuild, as the plain form always holds it. While step 2 waits for
that lock, queries that would use the index wait behind it, for up to `lock_timeout`.
`ALTER INDEX` is DDL that fires [event triggers](../../../glossary.md#event-trigger), as `COMMENT` and `REINDEX` already are
([cmdtag.h#PG_CMDTAG](../../../../raw/postgres-17/src/include/tcop/cmdtag.h#L19),
[cmdtaglist.h#ALTER-INDEX](../../../../raw/postgres-17/src/include/tcop/cmdtaglist.h#L42)),
so a database with DDL event triggers sees one per index step 2 writes to.

### How to read the plan

`action` first. Everything else is the evidence behind it.

| Column | Means | Watch for |
|---|---|---|
| `access_method` | the index's `pg_am.amname` | every AM but `btree` is a candidate, including a non-core one such as `bloom` |
| `action` | `reindex`, `refresh`, `initialize`, `conflict`, `blocked`, `skip` | `blocked` means this session cannot write the comment at all; `conflict` means the comment holds more than one reserved line and step 2 will not write it |
| `baseline` | `ok`, `absent`, `invalid`, `ambiguous` | `invalid` is a reserved line that does not match the version-2 grammar whole; it is replaced, not trusted |
| `index_size`, `baseline_size`, `size_ratio` | the file now, the stored size, and the first over the second | `>= 1.30` is the size test |
| `table_tuples`, `baseline_tuples`, `tuple_ratio` | the table's `reltuples` now, stored, and the first over the second | a move of 30 % either way is the tuple test |
| `notes` | why a row looks the way it does | nine strings, listed under the ladder below |
| `comment_command`, `reindex_command` | exactly what step 2 will run | `comment_command` is NULL on a `reindex` row, because its new baseline is only known after the rebuild |

### The decision ladder, in order

The first rule that matches decides. This is the order of the `staged` CTE.

| # | Condition | Action | Writes |
|---|---|---|---|
| 1 | this session does not own the index | `blocked` | nothing |
| 2 | the comment holds more than one reserved `@nbmaint:` line | `conflict` | nothing, until a person removes one |
| 3 | no reserved line, or one that is not a version-2 payload | `initialize` | the baseline, at current values |
| 4 | the index is smaller than its stored size | `refresh` | the baseline, at current values |
| 5 | size `>= 1.30 x` stored, or table tuples moved `>= 30 %` either way | `reindex` | `REINDEX INDEX`, then the baseline read after the rebuild |
| 6 | none of the above | `skip` | nothing |

**Rule 2 keeps the human text safe.** With two reserved lines the method cannot tell which
one is its own, so it writes neither and reports the index until a person removes one.

**Rule 4 is not in the brief, and it is needed.** A `VACUUM` never shortens one of these
index files. The only call to [`RelationTruncate`](../../../glossary.md#truncation) in the hash, [GiST](../../../glossary.md#gist), [SP-GiST](../../../glossary.md#sp-gist), [GIN](../../../glossary.md#gin), BRIN and
[B-tree](../../../glossary.md#b-tree) directories of the pinned tree is SP-GiST's, and it sits inside `#ifdef NOT_USED`;
the hash README says only `REINDEX` shrinks a hash index; and GIN's cleanup re-reads the
relation length rather than shortening it
([spgvacuum.c#truncation-disabled](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L877-L900),
[README#no-shrink](../../../../raw/postgres-17/src/backend/access/hash/README#L31-L34),
[ginvacuum.c#ginvacuumcleanup-relength](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L794-L802)).
So an index smaller than its baseline was given a new file by something else, such as a
hand-run `REINDEX`, which builds into a new [relation file](../../../glossary.md#relfilenumber)
([index.c#reindex_index-rebuild](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789)).
A stored size that is now too high would hide the next 30 % of growth. Rule 4 rewrites it,
and it runs before rule 5, so an index rebuilt elsewhere is not rebuilt again. The payload
carries no relation file number, so a rebuild elsewhere that did **not** shrink the file
goes unnoticed; see [After an out-of-band rebuild](#after-an-out-of-band-rebuild).

Step 2's two knobs, `dry_run` and `max_reindex`, sit at the top of its `DECLARE` block.
`dry_run := true` prints what each index would get, and locks and writes nothing.
`max_reindex` caps the rebuilds one run may **start**: a rebuild is counted before it
begins, so one that fails still uses up its place, and an index over the cap is reported
and left for the next run. Edge round G measured it with the cap set to 1: the first
rebuild failed with `SQLSTATE 22012`, and the next index due was reported as capped, its
file and comment untouched.

Nine `notes` strings exist: `not the index owner: nothing can be written`, `more than one
reserved @nbmaint: line: nothing written until one is removed`, `reserved @nbmaint: line
is not a version-2 payload: replaced`, `table reltuples unknown: tuple test cannot fire`,
`baseline tuple count unknown: tuple test cannot fire`, `baseline tuple count was zero`,
`index smaller than its baseline: rebuilt elsewhere`, `size test fired` and `tuple test
fired`.

### Why the candidate filters are there

| Filter | Because | Evidence |
|---|---|---|
| `a.amname <> 'btree'` | the brief's scope | - |
| `c.relkind = 'i'` | a [partitioned index](../../../glossary.md#partitioned-index) (`'I'`) has no storage of its own: both servers measured its size as 0. Its leaf indexes are ordinary `'i'` indexes and are candidates themselves. `REINDEX INDEX` on the parent is refused on 12.2 (measured) and on 17 goes to `ReindexPartitions` | [indexcmds.c#ReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2803-L2850) |
| `x.indisvalid AND x.indisready AND x.indislive` | an [index left behind](../../../glossary.md#invalid-index) by a failed `CREATE INDEX CONCURRENTLY` says nothing about what a rebuild of the live index would return | measured: the edge case's failed build is never a candidate |
| `NOT pg_is_other_temp_schema(c.relnamespace)` | `REINDEX` refuses another session's temporary index | [index.c#reindex_index-other-temp](../../../../raw/postgres-17/src/backend/catalog/index.c#L3697-L3704), [namespace.c#isOtherTempNamespace](../../../../raw/postgres-17/src/backend/catalog/namespace.c#L3706-L3720) |
| `n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')` | keeps the sweep away from the installation's own objects | - |
| `c.cur_bytes IS NOT NULL` | `pg_relation_size` opens the relation with `try_relation_open` and returns NULL for one dropped since the catalog read, instead of raising | [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L371) |

### The two tests, and the states that disable them

**The size test** fires when `cur_bytes >= base_bytes * 1.30`. It is `>=` on `numeric`,
so growth of exactly 30 % fires. Measured on both servers: a stored size of
`floor(current / 1.30)` fires, and one byte more does not.

**The tuple test** fires when `abs(cur_tuples - base_tuples) >= base_tuples * 0.30`, in
either direction. Measured on both servers against a 13,000-row table: a stored 10,000
fires and a stored 10,001 does not; against a 7,000-row table, a stored 10,000 fires and a
stored 9,999 does not. Three states are handled explicitly rather than left to
arithmetic:

| State | What the text does | Why |
|---|---|---|
| stored count is 0 | any non-zero current count fires | an increase from zero has no finite ratio |
| current count is negative | the tuple test cannot fire, and `notes` says so | `reltuples` is `-1` on a table nothing has counted, from PostgreSQL 14 on; 12.2 stores `0` there instead ([pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L66)) |
| stored count is negative | the tuple test cannot fire, and `notes` says so | a baseline written while the count was unknown; the next `refresh` or `reindex` writes a known one |

Both counts pass through `float4` to `numeric`, which keeps `FLT_DIG`, six, significant
digits
([numeric.c#float4_numeric](../../../../raw/postgres-17/src/backend/utils/adt/numeric.c#L4708-L4740));
both servers measured `1234567::float4::numeric` as `1234570`. The two counts are rounded
separately - the stored one when its baseline was written, the current one now - and each
rounding can move its value by half a unit in the sixth significant digit, at most
5 x 10^-6 of it. The errors do not cancel, so the ratio the test reads can be off by up to
about 1 x 10^-5 of itself. At the rising boundary a true 1.3000 can read anywhere from
1.29999 to 1.30001, so the test can fire on a true rise of 29.9987 % or miss one of
30.0013 %; at the falling boundary a true 0.7000 can read 0.69999 to 0.70001, a band of
about 0.0007 percentage points either side of 30 %.

### The comment survives both REINDEX forms

The baseline lives in the comment, so it has to outlive the rebuild it triggers. The plain
form keeps the index's `pg_class` row and gives it a new relation file, so a comment keyed
by the index OID cannot move
([index.c#reindex_index-locks](../../../../raw/postgres-17/src/backend/catalog/index.c#L3601-L3614),
[index.c#reindex_index-rebuild](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789)).
The concurrent form builds a second index and swaps them, and the comment survives only
because `index_concurrently_swap` rewrites the `pg_description` row's `objoid` to the new
index, taking the first match and stopping
([index.c#index_concurrently_swap-comment](../../../../raw/postgres-17/src/backend/catalog/index.c#L1740-L1784)).
Measured on both servers, on an index carrying a human line and a payload: the plain form
kept the OID, gave a new file and left the comment's MD5 unchanged; the concurrent form
moved the index to a new OID with the same MD5; and step 1 then read `skip`, because a
rebuild of an unchanged table is the size the baseline recorded.

A rebuild also recounts the table. `index_build` updates the heap's `pg_class` row with
the tuples its scan counted as well as the index's own
([index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135),
[index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2789-L2842)).
That is why step 2 reads both values **after** its `REINDEX`: the baseline it stores is
the rebuilt file and a counted table, not the estimate the decision was made on.

### Privileges, locks and transactions

| Need | Rule on 17 | What the method does |
|---|---|---|
| write the comment | `COMMENT` requires ownership of the index, and a superuser passes every ownership check ([comment.c#CommentObject-ownership](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L76), [objectaddress.c#check_object_ownership](../../../../raw/postgres-17/src/backend/catalog/objectaddress.c#L2382-L2401), [aclchk.c#object_ownercheck](../../../../raw/postgres-17/src/backend/catalog/aclchk.c#L4146-L4214)) | [`pg_has_role(relowner, 'USAGE')`](../../../glossary.md#role-membership) is the same test, `has_privs_of_role`, made in SQL ([acl.c#pg_has_role_id](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L4779-L4793), [acl.c#pg_role_aclcheck](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L4877-L4900)); a row that fails it is `blocked` and nothing is attempted |
| rebuild the index | `REINDEX INDEX` checks `MAINTAIN` on the table ([indexcmds.c#RangeVarCallbackForReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2857-L2912)) | an index's owner is its table's owner: `index_create` copies it, and `ALTER INDEX ... OWNER` only warns and changes nothing ([index.c#index_create-owner](../../../../raw/postgres-17/src/backend/catalog/index.c#L1008-L1014), [tablecmds.c#ATExecChangeOwner-index](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14543-L14562)). So a session that passes the comment test owns the table as well |
| rebuild without blocking writes | not possible from step 2: [`REINDEX CONCURRENTLY`](../../../glossary.md#concurrently) inside a `DO` block is refused with `cannot be executed from a function`, measured on both servers ([indexcmds.c#ExecReindex-concurrently](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2736-L2738), [xact.c#PreventInTransactionBlock](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L3594-L3633)) | step 2 runs the plain form. To rebuild a busy table's index concurrently, run step 1, run its `reindex_command` with `CONCURRENTLY` added at the top level, and let the next run's `refresh` rewrite the baseline if the file shrank |

The plain form takes `ShareLock` on the table, which blocks every writer for the whole
rebuild, and `AccessExclusiveLock` on the index, which blocks every query that would use
it ([indexcmds.c#RangeVarCallbackForReindexIndex-table-lockmode](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2871-L2872),
[index.c#reindex_index-locks](../../../../raw/postgres-17/src/backend/catalog/index.c#L3601-L3614),
[index.c#reindex_index-index-lock](../../../../raw/postgres-17/src/backend/catalog/index.c#L3647-L3654)).
`COMMENT` takes `ShareUpdateExclusiveLock` on the index
([comment.c#CommentObject-ownership](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L76)).
Step 2 takes the plain form's two locks itself before it reads anything it will act on;
see [What step 2 locks, and what it checks under the locks](#what-step-2-locks-and-what-it-checks-under-the-locks).

**The two timeouts behave differently inside step 2, on purpose.** A `DO` block is one
statement, so `statement_timeout` bounds the whole run, and PL/pgSQL's `WHEN OTHERS`
does not catch a query cancel: it matches everything except `QUERY_CANCELED` and
`ASSERT_FAILURE`
([pl_exec.c#exception_matches_conditions](../../../../raw/postgres-17/src/pl/plpgsql/src/pl_exec.c#L1583-L1597)).
Both servers measured it: a `DO` block whose inner `WHEN OTHERS` wraps a sleep past the
timeout ended with `canceling statement due to statement timeout`. Every index step 2
committed before the timeout keeps its rebuild and its baseline. `lock_timeout` instead
fires per lock wait with `SQLSTATE 55P03`, which `WHEN OTHERS` does catch, so an index
whose size, table lock or index lock cannot be had in 5 seconds is skipped for this run
with a `WARNING`, its old baseline intact, and the loop goes on. Edge round B measured the
table lock on both servers: one index refused by a held lock, `failed=1`, five others
rebuilt and one refreshed in the same run, and the refused one rebuilt by the next run
once the lock was gone. Edge round H measured the size read, as above.

### What is version-local between 12 and 17

The two texts are identical on both servers; what differs is around them. Every row was
discovered by the scripts' `facts` stage on the running server.

| Fact | 17.11 | 12.2 | Consequence |
|---|---|---|---|
| both texts run unmodified | yes | yes | the compatibility claim; the `exact` stage ran each twice on each server |
| `WITH ... AS MATERIALIZED` | accepted | accepted | the pipeline's optimization fences |
| `pg_input_is_valid()` | 1 [`pg_proc`](../../../glossary.md#pg_proc) row | 0 | the payload is parsed by regex, not by a guarded cast |
| `regexp_match()` | 2 `pg_proc` rows | 2 | the payload grammar is matched whole, with its fields read from that one match |
| `ALTER INDEX ... OWNER TO` the owner it has | holds `AccessExclusiveLock`, prints nothing, and leaves the index's `pg_class` row with its `xmin` | the same | step 2's lock on the index |
| `nbmaint.only_index` after a transaction that set it locally, and in a fresh session | `''`, and NULL | the same | step 1 reads every candidate |
| `COMMIT` inside `DO`, top level / inside `BEGIN` | accepted / `invalid transaction termination` | the same | one transaction per index, and step 2 must run at the top level |
| plain `REINDEX` inside `DO` | accepted | accepted | step 2 can rebuild |
| `REINDEX CONCURRENTLY` inside `DO` | refused | refused | step 2 uses the plain form |
| `COMMENT ... IS 'a' \|\| 'b'` | syntax error | syntax error | step 2 builds the statement with `format(... %L)` and `EXECUTE` |
| a statement timeout inside `WHEN OTHERS` | not caught | not caught | `statement_timeout` bounds the whole of step 2 |
| `REINDEX INDEX` on a partitioned index | accepted | `REINDEX is not yet implemented for partitioned indexes` | the filter keeps `'I'` out on both |
| size of a partitioned index | 0 | 0 | the same |
| `reltuples` of a table nothing has counted | `-1` | `0` | the unknown-count note fires only from 14 on; on 12 a zero is ambiguous |
| `1234567::float4::numeric` | `1234570` | `1234570` | the same six-digit rounding on both |
| [`transaction_timeout`](../../../glossary.md#transaction_timeout-and-idle_in_transaction_session_timeout) | exists | absent | forced to 0 on 17 only |
| [`pg_stat_force_next_flush()`](../../../glossary.md#cumulative-statistics) | 1 `pg_proc` row | 0 | the 12 leg ends each churn session and waits a second instead |
| `pg_stat_progress_analyze` | exists | absent | the 12 census reads two progress views |
| `int8_minmax_multi_ops` | exists | absent | fixture `b11` is not built on 12 |
| GiST `point_ops` support function 11 | present | absent | `g09` is a sorted build on 17 and insert-driven on 12 |
| [`pgstattuple()`](../../../glossary.md#pgstattuple) on a hash index holding an all-zero [page](../../../glossary.md#page) | reads it as free space | refused: `index "..." contains unexpected zero page at block ...` | the 12 census records the refusal instead of the number |

The last row is the one this run found. On 17, `pgstat_hash_page` reads each block with
`ReadBufferExtended` and counts an all-zero page as free space
([pgstattuple.c#pgstat_hash_page](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L453-L495)).
That is the 17 branch's commit `036decbba2` of 2025-10-02, first released in 17.7, whose
message says the previous reader went through `_hash_checkpage()`, failed on empty
pages, and was fixed and [back-patched](../../../glossary.md#back-patch) down to 13. A hash index gets all-zero pages from
its [splitpoint](../../../glossary.md#hash-splitpoint) allocation, which writes only the last page of a new batch
([hashpage.c#_hash_alloc_buckets](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L967-L1037)).

The v12 side of each behavior is on the v12 pages rather than cited here, because this
page may only cite `raw/postgres-17/`:
[Calibrating a COMMENT-Stored Bytes-per-Table-Tuple REINDEX Threshold for Every
Non-B-Tree Index in PostgreSQL 12
(unverified)](../../../v12/questions/indexing/comment-stored-bytes-per-table-tuple-non-btree.md),
[Physical Index Statistics, Tuple Counts, and Bytes per Tuple in PostgreSQL 12
(unverified)](../../../v12/questions/indexing/physical-index-statistics-tuple-counts-and-bytes.md),
[How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 12
(unverified)](../../../v12/questions/indexing/reindex-index-concurrently.md),
[All Outcomes That Leave an Invalid Index in PostgreSQL 12, Including a Failed CREATE
INDEX CONCURRENTLY (unverified)](../../../v12/questions/indexing/invalid-index-outcomes.md)
and [Indexes Only on the Parent Versus Only on the Child Tables of a Declaratively
Partitioned Table in PostgreSQL 12
(unverified)](../../../v12/questions/indexing/partitioned-index-parent-vs-child.md).


### Who writes the table's reltuples

The tuple test compares two readings of the table's `pg_class.reltuples`, and that column
is an estimate written by whichever command touched the table last. The `probes` stage
measured every writer on one 200,000-row table carrying one index of each [access method](../../../glossary.md#access-method).
Where the two servers differ, a cell reads `17.11 / 12.2`:

| After | table | hash index | GIN index | GiST index | SP-GiST index | BRIN index |
|---|---|---|---|---|---|---|
| `CREATE TABLE` | -1 / 0 | - | - | - | - | - |
| `INSERT` of 200,000 rows | -1 / 0 | - | - | - | - | - |
| `CREATE INDEX`, one per access method | 200,000 | 200,000 | **400,000** | 200,000 | 200,000 | **23** |
| `ANALYZE` | 200,000 | 200,000 | 200,000 | 200,000 | 200,000 | **200,000** |
| `DELETE` of 10 %, then `VACUUM` | 180,000 | 180,000 | 180,000 | 180,000 | 180,000 | **22** |
| `TRUNCATE` | -1 / 0 | -1 / 0 | -1 / 0 | -1 / 0 | -1 / 0 | 1 |
| `INSERT` of 200,000 rows again | -1 / 0 | -1 / 0 | -1 / 0 | -1 / 0 | -1 / 0 | 1 |
| `REINDEX INDEX` of the hash index | 200,000 | 200,000 | -1 / 0 | -1 / 0 | -1 / 0 | 1 |

| Writer | What it writes into the table's `reltuples` | Evidence |
|---|---|---|
| `CREATE INDEX`, `REINDEX` | the tuples the build's heap scan counted; on an empty table whose count is `-1`, it stays `-1` | [index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135), [index.c#index_update_stats-empty-table](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842) |
| `ANALYZE` | the sample's estimate of the total | [analyze.c#table-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L632-L645) |
| `VACUUM` | the live tuples it saw, extrapolated over the pages it skipped from the old density | [vacuumlazy.c#new_live_tuples](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1034-L1037), [vacuumlazy.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L572-L575), [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1300-L1366) |
| `TRUNCATE` | `-1` on 17, measured `0` on 12.2 | [relcache.c#RelationSetNewRelfilenumber-reltuples](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3943-L3954) |

Most maintenance steps are a `VACUUM ANALYZE`, which vacuums first and analyzes second, so
the count the method compares is `ANALYZE`'s sample estimate on both sides of the
comparison. That estimate moves even when the rows do not: on the fixtures whose row count
ended where it began, the tuple ratio read between 0.9777 (`s08` on 17.11) and 1.0068 (`s08` on 12.2). Only a fixture sitting on
the 30 % boundary could flip on that, and the one that does, `s10` at a 30 % delete, is
also opened by its size test.

The same probe shows why the index's own `reltuples` was left out of the payload. A GIN
build writes the entries it inserted, 400,000 for 200,000 rows of two keys, and the next
`ANALYZE` writes rows; a serial BRIN build writes ranges, `ANALYZE` writes rows, and
`VACUUM` writes ranges again
([gininsert.c#indtuples](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L271),
[gininsert.c#index_tuples](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L425),
[brin.c#brinbuild-index_tuples](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1248-L1258),
[analyze.c#index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663),
[brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332)).
A 30 % test on that column would fire on a GIN or BRIN index whenever the last writer
changed, with no physical change at all. See also
[Reading an Index's Entry Count From the Catalogs, for Every Index Type, in PostgreSQL 17
(unverified)](index-entry-count-from-catalogs.md).

### The ported fixtures, and the protocols they ran under

The corpus is the source page's 29 numbered fixtures, recipe for recipe, with its ids and
its sizes. `h06` and `n11` left this page on 2026-09-22, see
[Revision after filing](#revision-after-filing), and left the source page on 2026-09-24,
when both protocols stopped requiring their case. The sizes are 1,000,000 rows for the
hash, GiST and SP-GiST families, 2,000,000 for BRIN
and the [partial index](../../../glossary.md#partial-index), 600,000 for GIN and 300,000 for the small ones. Every table is
created with [`autovacuum_enabled = off`](../../../glossary.md#storage-parameter), and every recipe is a line of the published
scripts.

| Fixture | AM | What its churn does | Maintenance step |
|---|---|---|---|
| `h00` | hash | nothing: the untouched index | none |
| `h01` | hash | collapses 1,000,000 distinct keys onto 100, so duplicates chain into overflow pages | `VACUUM ANALYZE` |
| `h02` | hash | grows the table 5x, then deletes back to the baseline rows | `VACUUM ANALYZE` |
| `h03` | hash | [`fillfactor = 50`](../../../glossary.md#fillfactor), updates half the keys | `VACUUM ANALYZE` |
| `h04` | hash | inserts 400,000 rows and nothing else | `VACUUM ANALYZE` |
| `h05` | hash | inserts 120,000 rows: past the analyze threshold, under the vacuum ones | `ANALYZE` alone, the [auto-analyze](../../../glossary.md#autovacuum) stand-in |
| `h07` | hash | nothing: an empty table and index | none |
| `h08` | hash | updates 1 % of the keys | `VACUUM ANALYZE` |
| `h12` | hash | partial index `WHERE state = 'pending'`, whose population grows 9x | `VACUUM ANALYZE` |
| `g06` | GiST | six rounds of `int8range` relocation | `VACUUM ANALYZE` |
| `g07` | GiST | grows the table 4x, then deletes back | `VACUUM ANALYZE` |
| `g08` | GiST | deletes the top 80 % as one id band, under a snapshot opened before the delete | `VACUUM ANALYZE` twice around the snapshot's release, declared exception X1 |
| `g09` | GiST | six rounds of `point` relocation | `VACUUM ANALYZE` |
| `s08` | SP-GiST | six rounds of text prefix replacement at constant width | `VACUUM ANALYZE` |
| `s09` | SP-GiST | grows the table 4x under a new prefix, then deletes back | `VACUUM ANALYZE` |
| `s10` | SP-GiST | `fillfactor = 50`, deletes 30 % and updates 30 % | `VACUUM ANALYZE` |
| `b10` | BRIN | minmax at `pages_per_range = 128`, six whole-table value rounds | `VACUUM ANALYZE` |
| `b11` | BRIN | `int8_minmax_multi_ops(values_per_range = 64)`, correlated, scattered, correlated again; 17 only | `VACUUM ANALYZE` |
| `b12` | BRIN | minmax at `pages_per_range = 32`, three value rounds | `VACUUM ANALYZE` |
| `b13` | BRIN | `autosummarize = on`, 1,000,000 appended rows | the [summarization](../../../glossary.md#brin-summarization) stand-in, then `VACUUM ANALYZE` |
| `n03` | GIN | 1,800,000 rows on three hot keys inserted, then deleted | `VACUUM ANALYZE` |
| `n04` | GIN | six rounds of complete key replacement | `VACUUM ANALYZE` |
| `n05` | GIN | `fastupdate = on`, 300,000 inserts under a 1 GB pending-list limit | `VACUUM ANALYZE` |
| `n06` | GIN | `jsonb_path_ops`, three rounds of key replacement | `VACUUM ANALYZE` |
| `n07` | GIN | `tsvector`, three rounds of document replacement | `VACUUM ANALYZE` |
| `n08` | GIN | nothing | none |
| `n09` | GIN | nothing: an empty index | none |
| `n10` | GIN | three hot keys over 1,200,000 rows, the top 80 % deleted as one band under a snapshot opened before the delete | `VACUUM ANALYZE` twice around the snapshot's release, declared exception X2 |
| `n12` | GIN | 120,000 inserts with `fastupdate = on`, in the auto-analyze window | `ANALYZE` plus `gin_clean_pending_list()`, the GIN auto-analyze stand-in |

The hash, GiST, SP-GiST and BRIN fixtures ran under
[Mandatory Non-B-Tree, Non-GIN Bloat Tests (unverified)](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md)
and the GIN ones under
[Mandatory GIN Bloat Tests (unverified)](../../common-concepts/mandatory-gin-bloat-tests.md).
Both pages define the five phases, the maintenance assumption, the no-defeat rule, the
stand-ins, the census, the measurement lock and the oracle, and are not restated here.
What this run did in each phase:

| Phase | What ran |
|---|---|
| build | create, load, `ANALYZE`, create the scored index, `ANALYZE` |
| baseline | a census of every fixture under `SHARE ROW EXCLUSIVE`, then **step 2's first run**, which initialized every baseline: 29 of 29 on 17.11 and 28 of 28 on 12.2 wrote a version-2 payload whose `sz` equals the census's size |
| churn | the recipe's writes, a census of the unmaintained state, the maintenance step and its checks, a census of the maintained state; then the simulated auto-analyze census over every table |
| decide | **step 1, verbatim**, in one transaction holding `SHARE ROW EXCLUSIVE` on every fixture table; nothing else ran in that phase |
| oracle | `REINDEX INDEX` at [`maintenance_work_mem = 256MB`](../../../glossary.md#maintenance_work_mem), with `pg_relation_size(index, 'main')` read before and after, and the heap's `relpages` and `reltuples` recorded because a hash rebuild is sized from them |

Filed before the first fixture existed, in their own database: the declared kind of every
column step 1 publishes, all six of them **levels**, because the method publishes a
decision and no estimate of reclaimable bytes; the method's two tests; the pay-off
threshold; one prediction per fixture, taken from the source page's 17.11 figures; 18
invariants, each scored as holding or failing, and a failure stops the run; the three
declared exceptions of the no-defeat rule; and the coverage plan. The first baseline
payload was written after all of them, and the scripts print both timestamps.

**Three differences from the source page's run.** The method under test is this page's,
not the source page's. `max_parallel_maintenance_workers` is 0 here and was 2 there, so
every build and every `VACUUM` took the serial path on both servers. And of the source
page's seven mechanism probes, three are kept - the hash oracle's dependence on the heap
estimate, the GIN oracle's dependence on `maintenance_work_mem`, and which GiST operator
classes can take a sorted build - beside one new one, the `reltuples` writers above; its
edge cases are replaced by this method's own.

### The maintenance was not defeated

Every maintenance step ran in a session that first forced every settable timeout to 0 and
read the settings back, which is what an autovacuum launcher and worker do to themselves
"to avoid letting these settings prevent regular maintenance from being executed"
([autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470),
[autovacuum.c#launcher-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L518-L526)).
All four are `PGC_USERSET`, so session scope
([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620),
[guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631),
[guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642),
[guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653)).
The same preamble opened every other session of the run that issued a `VACUUM` or an
`ANALYZE`: the build phase, the census, the probes, the edge cases.

Each step was then checked the moment it returned, against the proofs the rule asks for,
and the run dies at the first failure rather than score anything:

| Proof | 17.11 | 12.2 |
|---|---|---|
| maintenance steps checked the moment they returned | 27: the 25 churned fixtures, and the second `VACUUM` of `g08` and `n10` | 26 |
| every settable timeout read back as 0 | all 65 `VACUUM` and `ANALYZE` sessions of the run, four timeouts each | all 63, three each |
| `VERBOSE`'s "dead but not yet removable" count | 0 on all 23 checked `VACUUM`s outside the declared snapshots | 0 on all 22 |
| the two declared snapshots | 240,000 on `g08` and 960,000 on `n10` while held; 0 on the `VACUUM` after the release | the same |
| [horizon](../../../glossary.md#xmin-horizon) probes with no holder | 50 of 54; the other 4 are the declared snapshot, before and after its step | 48 of 52; the same 4 |
| [replication slots](../../../glossary.md#replication-slot) and [prepared transactions](../../../glossary.md#two-phase-commit) | 0 and 0 | 0 and 0 |
| skip, error or cancellation lines, in the session logs and the server log | 0 | 0 |
| a census's measurement lock held across a maintenance step | 0 of 91 lock intervals | 0 of 88 |

Why those proofs: `VACUUM` takes its removal horizon from
`GetOldestNonRemovableTransactionId`, which folds in every backend's `xmin`, and it enters
[index vacuuming](../../../glossary.md#index-vacuuming) only when it collected dead tuples
([vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122),
[vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052)).
Under a pinned horizon the churn's rows are only counted, in the `VERBOSE` line's "dead but
not yet removable" figure
([vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L657-L663)),
and no index entry leaves the index. For this method the failure would be quiet: the file
would not shrink, and a later rebuild would be scored against an index nobody maintained.

**The check fires.** The `defeat` stage builds a throwaway 100,000-row fixture, deletes
half of it while a snapshot opened before the delete is held, and gives it the same checked
maintenance step. Both legs printed:

```text
exit status of the checked maintenance step: 1, the run stopped, as the rule requires
FATAL: the maintenance of zz (maint) was defeated; 50000 tuples dead but not yet removable; 1 horizon holders where 0 was declared: the run stops here and scores nothing
```

The two declared snapshots are the only other place a horizon was held. On `g08` and
`n10` the maintenance `VACUUM` under the snapshot reported 240,000 and 960,000 tuples dead
but not yet removable, then a second `VACUUM` after the release reported 0 and deleted
2,330 GiST pages and 375 GIN [posting-tree](../../../glossary.md#posting-tree) pages, none of them free yet. Both fixtures are
scored on that second state.

### The protocol cross-checks

Both protocols require every number to be read more than one way. The 18 invariants,
filed before the first fixture existed, are those second readings; all 18 held on both
legs. Two of them are the protocols' own checks on `VACUUM`'s report and on BRIN's free
space map.

**`VACUUM VERBOSE`'s index line, against the census (I9).** On 17 the line reads `pages:
N in total, N newly deleted, N currently deleted, N reusable`
([vacuumlazy.c#verbose-index-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L732)).
Each maintenance `VACUUM`'s line is compared, count by count, with the censuses taken just
before and just after that `VACUUM`:

| AM | What each count is, in the pinned source | What it is checked against |
|---|---|---|
| hash | cleanup returns no statistics, and so no line, unless `hashbulkdelete` ran; when it ran, only `num_pages` is filled ([hash.c#hashvacuumcleanup](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L647-L663), [hash.c#hashbulkdelete-stats](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L631-L637)) | no line exactly where `VERBOSE` does not print `index scan needed:`, which it prints only when bulk deletion ran ([vacuumlazy.c#index-scan-needed](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L695-L700)); otherwise the census after, and three zeros |
| GiST | the scan counts a [recyclable](../../../glossary.md#index-page-recycling) or new page as deleted and reusable and records it free, a deleted page not yet recyclable as deleted, and each page it deletes as newly deleted and deleted ([gistvacuum.c#gistvacuumpage-classes](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L298-L309), [gistvacuum.c#gistdeletepage-counters](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L655-L658)) | deleted = deleted-flag plus all-zero pages after; reusable = [FSM](../../../glossary.md#free-space-map) free pages after; newly deleted = deleted-flag pages after minus before |
| SP-GiST | a page outside the [metapage](../../../glossary.md#metapage) and the two roots that is left new or empty is recorded free and counted, and the three counts are set equal ([spgvacuum.c#spgvacuumpage-fsm](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L665-L683), [spgvacuum.c#final-stats](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L902-L905), [spgist_private.h#fixed-blocks](../../../../raw/postgres-17/src/include/access/spgist_private.h#L47-L53)) | the new or empty pages after, read from page headers ([bufpage.h#PageIsEmpty](../../../../raw/postgres-17/src/include/storage/bufpage.h#L214-L224)), and FSM free pages after |
| BRIN | `num_pages` is read before the scan and the summarization, and the rest stays 0 ([brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332)) | pages in total = the census before |
| GIN | reusable is the recyclable pages the cleanup scan records free ([ginvacuum.c#ginvacuumcleanup-free](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L794)) | FSM free pages after |

Every maintenance step agreed with its censuses, count by count: 27 of 27 on 17.11, 24 of
them with an index line, and 26 of 26, 23 with a line, on 12.2. The steps with no line are `h04`'s
`VACUUM`, whose bulk deletion never ran, and the two `ANALYZE`-only stand-ins, `h05` and
`n12`. 12.2 reports the same counts in two messages, `index "X" now contains ... in P
pages` and `D index pages have been deleted, F are currently reusable`, with no
newly-deleted count; the 12 leg reads them from there, and its checks skip the count 12.2
does not print.

**BRIN's free space, page by page (I18).** The non-B-tree protocol asks for `pg_freespace`
against each regular page's own free space, not a count of pages. A BRIN page's own free
space is `PageGetFreeSpace`, or 0 on a page flagged `BRIN_EVACUATE_PAGE`
([brin_pageops.c#br_page_get_freespace](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L913-L927)),
and the FSM keeps it rounded down to a category `BLCKSZ / 256` bytes wide
([freespace.c#FSM_CATEGORIES](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L64-L66),
[freespace.c#fsm_space_avail_to_cat](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L402-L421),
[freespace.c#fsm_space_cat_to_avail](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L427-L435)).
The census reads each regular page's header and its flags out of the raw page
([brin_page.h#BrinSpecialSpace](../../../../raw/postgres-17/src/include/access/brin_page.h#L29-L60))
and compares the two for every page, on every census.

Where they must agree is narrower than "after a `VACUUM`". `brin_vacuum_scan` records every
regular page's free space
([brin.c#brin_vacuum_scan](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2154-L2193),
[brin_pageops.c#brin_page_cleanup](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L609-L661)),
but the same `VACUUM` then summarizes, and BRIN writes a page's FSM entry only when the page
is extended or a search finds it short of space, "but not every single time we add a tuple
to the page", and an extended page's entry is the space left after its first summary; a
summary that moves to another page frees space on its old page and records nothing
([brin_pageops.c#brin_getinsertbuffer-fsm-policy](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L679-L682),
[brin_pageops.c#brin_doinsert-extended-freespace](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L417-L419),
[brin_pageops.c#brin_doinsert-fsm](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L460-L464),
[brin_pageops.c#brin_doupdate-move](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L244-L313),
[brin_pageops.c#brin_getinsertbuffer-record](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L861-L865)).
So I18 scores the pages the `VACUUM` did not write, found by an [LSN](../../../glossary.md#lsn) no newer than the [WAL](../../../glossary.md#wal)
insert position read just before it began, and reports the rest.

That leaves few pages to score, because most of a BRIN index's regular pages take a
summary during its `VACUUM`. On 17.11 the two pages the `VACUUM`s did not write, one each
in `b12` and `b13`, read their exact category, and so did 13 of the 18 they wrote. Three
of the other five read higher, and each is the last page of `b10`, `b11` or `b12`, the page
that index's summarization extended it onto and went on filling. Two read lower, both on
`b11`, the one index whose summaries moved between pages: 21 [line pointers](../../../glossary.md#line-pointer) were left
behind by moves during its churn. A moved summary frees space it does not record, which
fits, but the census keeps no per-page history, so it does not show which summary left
which page. On 12.2, where `b11` is not built, the same two unwritten pages read their exact
category, and so did 4 of the 6 written ones; the other two read higher, and they are the
last pages of `b10` and `b12`, with the same free space and FSM entry as on 17.11. Every
scored page agreed on both legs.

### Results on 17.11

`B` is the as-built size, `C` the maintained size step 1 decided on, `R` the size right
after `REINDEX INDEX`, all `pg_relation_size(index, 'main')` in bytes, and `truth %` is
`100 * (1 - R / C)`. `size` is `C` over the stored size and `tuples` the table count over
the stored count. The score compares the decision with `truth %` at 23.08 %.

| Fixture | AM | B | C | R | truth % | size | tuples | test fired | action | score |
|---|---|---|---|---|---|---|---|---|---|---|
| `h00` | hash | 33,570,816 | 33,570,816 | 33,570,816 | 0.00 | 1.0000 | 1.0000 | - | skip | PASS |
| `h01` | hash | 33,570,816 | 78,790,656 | 49,053,696 | 37.74 | 2.3470 | 1.0000 | size | reindex | PASS |
| `h02` | hash | 33,570,816 | 169,975,808 | 33,570,816 | 80.25 | 5.0632 | 1.0000 | size | reindex | PASS |
| `h03` | hash | 41,959,424 | 67,256,320 | 41,959,424 | 37.61 | 1.6029 | 1.0000 | size | reindex | PASS |
| `h04` | hash | 33,570,816 | 46,153,728 | 41,967,616 | 9.07 | 1.3748 | 1.4000 | both | reindex | **FALSE POSITIVE** |
| `h05` | hash | 33,570,816 | 37,765,120 | 33,570,816 | 11.11 | 1.1249 | 1.1200 | - | skip | PASS |
| `h07` | hash | 32,768 | 32,768 | 32,768 | 0.00 | 1.0000 | - | - | skip | PASS |
| `h08` | hash | 33,570,816 | 33,570,816 | 33,570,816 | 0.00 | 1.0000 | 1.0000 | - | skip | PASS |
| `h12` | hash | 58,736,640 | 66,568,192 | 66,568,192 | 0.00 | 1.1333 | 1.0000 | - | skip | PASS |
| `g06` | GiST | 81,100,800 | 393,871,360 | 81,100,800 | 79.41 | 4.8566 | 0.9879 | size | reindex | PASS |
| `g07` | GiST | 81,100,800 | 300,523,520 | 81,100,800 | 73.01 | 3.7056 | 1.0000 | size | reindex | PASS |
| `g08` | GiST | 24,330,240 | 24,330,240 | 4,866,048 | 80.00 | 1.0000 | 0.2000 | tuples | reindex | PASS |
| `g09` | GiST | 45,375,488 | 453,828,608 | 70,787,072 | 84.40 | 10.0016 | 1.0062 | size | reindex | PASS |
| `s08` | SP-GiST | 33,964,032 | 246,988,800 | 35,258,368 | 85.72 | 7.2721 | 0.9777 | size | reindex | PASS |
| `s09` | SP-GiST | 33,964,032 | 134,873,088 | 33,964,032 | 74.82 | 3.9711 | 1.0000 | size | reindex | PASS |
| `s10` | SP-GiST | 12,582,912 | 16,957,440 | 9,502,720 | 43.96 | 1.3477 | 0.7000 | both | reindex | PASS |
| `b10` | BRIN | 24,576 | 32,768 | 32,768 | 0.00 | 1.3333 | 1.0027 | size | reindex | **FALSE POSITIVE** |
| `b11` | BRIN | 49,152 | 114,688 | 114,688 | 0.00 | 2.3333 | 0.9977 | size | reindex | **FALSE POSITIVE** |
| `b12` | BRIN | 32,768 | 57,344 | 57,344 | 0.00 | 1.7500 | 0.9955 | size | reindex | **FALSE POSITIVE** |
| `b13` | BRIN | 24,576 | 24,576 | 24,576 | 0.00 | 1.0000 | 1.5000 | tuples | reindex | **FALSE POSITIVE** |
| `n03` | GIN | 43,106,304 | 50,659,328 | 43,106,304 | 14.91 | 1.1752 | 1.0000 | - | skip | PASS |
| `n04` | GIN | 43,106,304 | 324,345,856 | 49,143,808 | 84.85 | 7.5243 | 1.0043 | size | reindex | PASS |
| `n05` | GIN | 43,106,304 | 85,131,264 | 66,871,296 | 21.45 | 1.9749 | 1.5000 | both | reindex | **FALSE POSITIVE** |
| `n06` | GIN | 43,335,680 | 123,756,544 | 40,034,304 | 67.65 | 2.8558 | 1.0000 | size | reindex | PASS |
| `n07` | GIN | 43,106,304 | 188,317,696 | 49,135,616 | 73.91 | 4.3687 | 1.0000 | size | reindex | PASS |
| `n08` | GIN | 43,106,304 | 43,106,304 | 43,106,304 | 0.00 | 1.0000 | 1.0000 | - | skip | PASS |
| `n09` | GIN | 16,384 | 16,384 | 16,384 | 0.00 | 1.0000 | - | - | skip | PASS |
| `n10` | GIN | 3,923,968 | 3,923,968 | 827,392 | 78.91 | 1.0000 | 0.2000 | tuples | reindex | PASS |
| `n12` | GIN | 43,106,304 | 56,655,872 | 50,143,232 | 11.50 | 1.3143 | 1.2000 | size | reindex | **FALSE POSITIVE** |

22 `PASS`, 7 `FALSE POSITIVE`, 0 `FALSE NEGATIVE`. The 21 rebuilds returned 48.8 % of
their files on average, and the 8 skips would have returned 3.3 %. The size test fired on
18 fixtures and the tuple test on 6, both on 3. All 29 predictions filed before the run
held, and step 1's action equalled the two tests recomputed from the harness's own
readings on 29 of 29. Every other size on this leg equals the source page's 17.11 filing;
`g09`'s churned file does not, which [Open Questions](#open-questions) explains.

### Results on 12.2

The same 29 fixtures but `b11`, on a server built from the 12.2 pin.

| Fixture | AM | B | C | R | truth % | size | tuples | test fired | action | score |
|---|---|---|---|---|---|---|---|---|---|---|
| `h00` | hash | 33,570,816 | 33,570,816 | 33,570,816 | 0.00 | 1.0000 | 1.0000 | - | skip | PASS |
| `h01` | hash | 33,570,816 | 78,790,656 | 49,053,696 | 37.74 | 2.3470 | 1.0000 | size | reindex | PASS |
| `h02` | hash | 33,570,816 | 169,975,808 | 33,570,816 | 80.25 | 5.0632 | 1.0000 | size | reindex | PASS |
| `h03` | hash | 41,959,424 | 67,256,320 | 41,959,424 | 37.61 | 1.6029 | 1.0000 | size | reindex | PASS |
| `h04` | hash | 33,570,816 | 46,153,728 | 41,967,616 | 9.07 | 1.3748 | 1.4000 | both | reindex | **FALSE POSITIVE** |
| `h05` | hash | 33,570,816 | 37,765,120 | 33,570,816 | 11.11 | 1.1249 | 1.1200 | - | skip | PASS |
| `h07` | hash | 81,920 | 81,920 | 81,920 | 0.00 | 1.0000 | - | - | skip | PASS |
| `h08` | hash | 33,570,816 | 33,570,816 | 33,570,816 | 0.00 | 1.0000 | 1.0000 | - | skip | PASS |
| `h12` | hash | 58,736,640 | 66,568,192 | 66,568,192 | 0.00 | 1.1333 | 1.0000 | - | skip | PASS |
| `g06` | GiST | 81,100,800 | 393,871,360 | 81,100,800 | 79.41 | 4.8566 | 0.9943 | size | reindex | PASS |
| `g07` | GiST | 81,100,800 | 300,523,520 | 81,100,800 | 73.01 | 3.7056 | 1.0000 | size | reindex | PASS |
| `g08` | GiST | 24,330,240 | 24,330,240 | 4,866,048 | 80.00 | 1.0000 | 0.2000 | tuples | reindex | PASS |
| `g09` | GiST | 97,976,320 | 487,448,576 | 78,086,144 | 83.98 | 4.9752 | 1.0006 | size | reindex | PASS |
| `s08` | SP-GiST | 33,964,032 | 246,988,800 | 35,258,368 | 85.72 | 7.2721 | 1.0068 | size | reindex | PASS |
| `s09` | SP-GiST | 33,964,032 | 134,873,088 | 33,964,032 | 74.82 | 3.9711 | 1.0000 | size | reindex | PASS |
| `s10` | SP-GiST | 12,582,912 | 16,957,440 | 9,502,720 | 43.96 | 1.3477 | 0.7000 | both | reindex | PASS |
| `b10` | BRIN | 24,576 | 32,768 | 32,768 | 0.00 | 1.3333 | 1.0057 | size | reindex | **FALSE POSITIVE** |
| `b12` | BRIN | 32,768 | 57,344 | 57,344 | 0.00 | 1.7500 | 0.9986 | size | reindex | **FALSE POSITIVE** |
| `b13` | BRIN | 24,576 | 24,576 | 24,576 | 0.00 | 1.0000 | 1.5000 | tuples | reindex | **FALSE POSITIVE** |
| `n03` | GIN | 43,106,304 | 50,659,328 | 43,106,304 | 14.91 | 1.1752 | 1.0000 | - | skip | PASS |
| `n04` | GIN | 43,106,304 | 324,345,856 | 49,143,808 | 84.85 | 7.5243 | 1.0064 | size | reindex | PASS |
| `n05` | GIN | 43,106,304 | 85,131,264 | 66,871,296 | 21.45 | 1.9749 | 1.5000 | both | reindex | **FALSE POSITIVE** |
| `n06` | GIN | 43,335,680 | 123,756,544 | 40,034,304 | 67.65 | 2.8558 | 1.0000 | size | reindex | PASS |
| `n07` | GIN | 43,106,304 | 188,317,696 | 49,135,616 | 73.91 | 4.3687 | 1.0000 | size | reindex | PASS |
| `n08` | GIN | 43,106,304 | 43,106,304 | 43,106,304 | 0.00 | 1.0000 | 1.0000 | - | skip | PASS |
| `n09` | GIN | 16,384 | 16,384 | 16,384 | 0.00 | 1.0000 | - | - | skip | PASS |
| `n10` | GIN | 3,923,968 | 3,923,968 | 827,392 | 78.91 | 1.0000 | 0.2000 | tuples | reindex | PASS |
| `n12` | GIN | 43,106,304 | 56,655,872 | 50,143,232 | 11.50 | 1.3143 | 1.2000 | size | reindex | **FALSE POSITIVE** |

22 `PASS`, 6 `FALSE POSITIVE`, 0 `FALSE NEGATIVE`. The 20 rebuilds returned 51.2 % of
their files on average, and the 8 skips would have returned 3.3 %. The size test fired on
17 fixtures and the tuple test on 6, both on 3. All 28 predictions held, and step 1 equalled
the recomputed tests on 28 of 28. `pgstattuple` refused the hash census 10 times, on `h01`
to `h05` after their churn, each time for an all-zero page; the census's own page classes
and `pgstathashindex` read every block regardless.

**The two legs decide identically on every fixture both built.** 26 of the 28 fixtures
built on both servers have the same `B`, `C` and `R` to the byte. `g09` differs because
17 builds it sorted and 12 cannot, and `h07`, the empty hash index, is 81,920 bytes on
12.2 against 32,768 on 17.11; both are scored `PASS` on both legs. The only score one leg
has and the other lacks is `b11`'s, which 12.2 cannot build.

### Why the two tests miss where they miss

**BRIN: the index grows with the heap, and that growth is not waste.** A BRIN index keeps
one summary per range of `pages_per_range` heap blocks, and its revmap has one slot per
range ([README#brin-summary](../../../../raw/postgres-17/src/backend/access/brin/README#L6-L13),
[brin_revmap.c#HEAPBLK_TO_REVMAP](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L40-L43),
[brin_revmap.c#brinRevmapExtend](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L108-L121)).
Six whole-table update rounds took `b10`'s heap to 61,101 blocks on 17.11 (61,102 on
12.2), and `VACUUM` summarizes every complete range the heap grew into, leaving the
partial range at the end for later
([brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332),
[brin.c#brinsummarize-partial](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1916-L1925)):
94 summaries as built and 477 after, on both legs. So the index went from 3 pages to 4,
a ratio of 1.33, and a rebuild returned nothing.
`b13` is the same story through the tuple test: 50 % more rows, not one byte to reclaim.
On these indexes every size and count change is legitimate by construction.

**Growth by insertion.** `h04`'s 40 % more rows split buckets, and a rebuild sizes its
bucket count from the heap's estimated rows, so the rebuilt index is the size of a
1,400,000-row index and returned 9.07 %
([hash.c#hashbuild-estimate](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L133-L137),
[hashpage.c#_hash_init_metabuffer](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L509-L523)).
Probe P2 shows the dependence directly, identically on both legs: rebuilding `h08`'s index
after forging its table's `reltuples` to 100 produced 38,346,752 bytes instead of
33,570,816, and a fresh `ANALYZE` put it back.
`n05` and `n12` are the GIN counterparts: rows that arrived through the pending list and
were merged by the maintenance step leave an index 27.31 % and 12.99 % larger than a fresh
build of the same rows, so a rebuild returns 21.45 % and 11.50 % of the file - the two
figures are `C / R - 1` and `1 - R / C` of the same sizes. `n05` sits 1.63 points under
the pay-off threshold.

**The tuple test, by direction.** A fall in the table's count means rows left, and on these
fixtures the entries they left behind were real waste: `g08` 80.00 %, `n10` 78.91 %, `s10`
43.96 %. A rise means rows arrived, and a rebuild of a grown table is a grown index:
`b13` 0 %, `h04` 9.07 %, `n05` 21.45 %. The brief's symmetric test is right on the first
half and wrong on the second, on both legs.

**The partial index is a warning, not a miss.** `h12`'s predicate population grew 9x while
its table's count stayed at 2,000,000, so the tuple test could not see it, and the size
test read 1.13. It scored `PASS` because a hash index on a partial predicate is sized at
build time from the whole heap's estimate, so it was already the size of an index on
2,000,000 rows and a rebuild returned nothing. On an access method whose build is sized by
the predicate, the table's count would be the wrong denominator.

### After an out-of-band rebuild

The `act` stage ran step 1 and step 2 on the state the oracle left: every fixture index
freshly rebuilt by a `REINDEX` the method never saw.

| On the state the oracle left | 17.11 | 12.2 |
|---|---|---|
| `refresh`: the rebuilt file is smaller than the baseline | 4: `g08`, `n06`, `n10`, `s10` | 5: the same four and `g09` |
| `reindex` again, straight after a rebuild | 8: `b10`, `b11`, `b12`, `b13`, `g09`, `h01`, `h04`, `n05` | 6: `b10`, `b12`, `b13`, `h01`, `h04`, `n05` |
| `skip` | 17 | 17 |
| step 2 did what step 1 printed, per index | 29 of 29 | 28 of 28 |
| a second run of step 2 | wrote nothing | wrote nothing |

Step 2 did exactly what step 1 printed, and a settled database cost nothing. What step 1
printed is the finding. The indexes whose rebuilt file was smaller than the as-built
baseline were refreshed, as rule 4 intends. Every other index whose size or table count
sat 30 % away from its as-built baseline was ordered rebuilt again: the BRIN indexes;
`h01`, whose 100 hot keys need overflow pages even in a fresh build, at 1.46x; `h04` and
`n05`, which hold 40 % and 50 % more rows; and on 17.11 `g09`, whose relocated points
rebuild to 1.56x the sorted build of the original grid, where 12.2's insert-driven
baseline was large enough for the rebuild to come in under it. The payload carries no
relation file number, so a rebuild done elsewhere counts only when it shrank the file.

### Edge cases, measured

The `edge` stage exercises the comment handling, the two tests' boundaries, the filters,
and what step 2 does when another session holds a lock, edits the comment, rewrites the
payload or renames the index while step 2 waits for its locks. Each case files its
expected result before the texts run, and any difference fails the run. **158 of
158 verdicts held on each leg.**

| Round | What it does | Result, both legs |
|---|---|---|
| A | first run over 31 candidates: no comment; a human comment with an `@`, a `{`, a `}`, trailing spaces and blank lines; `keep me` above a version-1 payload; a payload whose `sz` is a string; a payload nested inside another object; a payload with a repeated field; two reserved lines; a payload-shaped string inside a line of prose; a bare `@nbmaint:` between two human lines; a version-1 payload followed by a newline | 30 `initialize` and one `conflict`. Every comment written keeps its human text byte for byte and in place, holds exactly one reserved line, and carries `sz` and `tup` equal to the file and the table count; the nested and repeated payloads are re-initialized, not read; the two-line comment is untouched. The B-tree index, the failed concurrent build and the partitioned parent never appear |
| B | forged payloads: the size test at and one byte under 1.30x; the tuple test at 30 % up and down and one tuple inside each; a stored count of 0; a stored size twice the file; a valid payload between two human lines; an index whose table another session holds in `ROW EXCLUSIVE` | exactly the expected `reindex`, `refresh` and `skip`; the payload between two human lines replaced where it stood; the locked table's index refused after 5 seconds with `SQLSTATE 55P03`, `failed=1`, its file and comment untouched, and the rest of the run carried on |
| C | the lock released, then two more runs | the refused rebuild happens; then a run that changes no comment and no file |
| D | both texts under a role that owns nothing | every one of the 31 rows `blocked`; nothing written |
| E | `REINDEX INDEX`, then `REINDEX INDEX CONCURRENTLY`, on an index with a human comment and a payload | the plain form keeps the OID, the concurrent one moves to a new OID, the comment is byte-identical after both, and step 1 then reads `skip` |
| F | another session holds a temporary hash index | step 1 never lists it, and step 2 passes it by without counting it |
| H | another session holds one index in `ACCESS EXCLUSIVE` for the whole round | step 1 is cancelled by its 5-second `lock_timeout` with `canceling statement due to lock timeout`; step 2 counts that index `failed` with `SQLSTATE 55P03`, writes nothing to it, and finishes the others |
| I | a person rewrites the comment's human text while step 2 waits for its table lock | step 2 reads the comment again under its locks, refreshes the payload, and keeps the text written while it waited |
| J | the payload is rewritten to the file's true size while step 2 waits | `reindex` before the locks and `skip` under them, `changed=1`; no rebuild, and the comment is the one written meanwhile |
| K | the index is renamed, and a new index takes its old name, while step 2 waits | refused with `SQLSTATE 55000`, both indexes untouched; the next run rebuilds the renamed index and initializes the new one |
| G | step 2 with one documented edit, `max_reindex` set to 1; the first index due fails to rebuild with a division by zero | `started=1`, `failed=1`, `capped=1`: the failed rebuild used up the cap, and the next index due keeps its file and comment |

On 17.11 an index built on an empty table that nothing has counted reads `table
reltuples unknown` and `baseline tuple count unknown`; on 12.2 the same index reads
`baseline tuple count was zero`. Both skip it. The stored payloads were 66 to 71 bytes on
17.11 and 65 to 71 on 12.2, which stores an unknown count as `0` rather than `-1`.

Rounds I to K depend on timing in one direction only. Step 2 waits up to its own
`lock_timeout` of 5 seconds for the table lock; the stage polls `pg_locks` every 0.05
seconds until step 2 is queued, then makes its change and releases the lock. A change that
came too late would have left step 2 failing on its lock timeout, and the round's verdicts
would differ; none did. Round G's cap is the one documented edit of step 2; the stage
checks that exactly one line differs from the filed text before it runs it.

### Coverage the protocols require, and what this run skipped

The coverage plan was filed with the declarations, before any fixture existed. Every row
reads the same on both legs unless the 12.2 column says otherwise. The plan no longer has a
row for a `VACUUM` whose index cleanup did not run: both protocols dropped that row on
2026-09-24, and so did this page; see
[Third revision: the invalid tests removed](#third-revision-the-invalid-tests-removed).

| Protocol | Behavior | Fixture | 17.11 | 12.2 |
|---|---|---|---|---|
| non-B-tree | hash: an overflow chain, and a freed overflow page whose bitmap bit was cleared | `h01` | reached: 2,402 overflow pages, 46 free in the bitmap | the same |
| non-B-tree | hash: a splitpoint allocation | `h02` | reached: 4,098 blocks grew to 20,749 | the same |
| non-B-tree | hash: an index whose `hashbulkdelete` never ran | `h04` | reached: no `VERBOSE` index line | the same |
| non-B-tree | GiST: an emptied leaf deleted, and one kept as its parent's last downlink | `g07` | partly: 26,315 pages deleted beside 10,037 live leaves; a page-class census cannot tell a last-downlink leaf from any other | the same |
| non-B-tree | GiST: a deleted-but-not-recyclable page under a held snapshot | - | **not reached**: `g08`'s snapshot kept its dead rows, so the `VACUUM` under it deleted no page; the 2,330 pages the second `VACUUM` deleted came after the release, and were not yet free only because their deletion [XID](../../../glossary.md#transaction-id), taken as they were deleted, was not yet older than every snapshot's horizon; see [Open Questions](#open-questions) | the same |
| non-B-tree | GiST: a sorted build beside a non-sorted one | `g09` beside `g06` to `g08` | reached: `point_ops` has support function 11 | **not reachable**: no GiST operator class has it on 12.2 |
| non-B-tree | SP-GiST: [placeholders](../../../glossary.md#sp-gist-placeholder), a trailing run removed, an interior one kept | `s09` | partly: 109 pages freed, from `VACUUM`'s own counters; no decoder shows the page classes | the same |
| non-B-tree | SP-GiST: an emptied non-root page and the root | `s09` | partly, the same limit | the same |
| non-B-tree | BRIN: an unsummarized range before the maintenance step, and after | `b13` | reached: 94 summaries before, 141 after the stand-in and the maintenance step | the same |
| non-B-tree | BRIN: a desummarized range, and one summarized by the stand-in | `b13` | reached: 3 orphaned line pointers after three ranges were desummarized | the same |
| non-B-tree | BRIN: a same-page summary update beside one that moved | `b10` and `b11` | reached: 0 orphans on `b10`, 21 on `b11` | **not reached**: 0 orphans on `b10` and `b12`, and `b11` is not built |
| non-B-tree | BRIN: more than one `pages_per_range` | `b12` at 32 beside `b10` at 128 | reached | the same |
| both | the maintenance pair, before and after the maintenance step | every churned fixture | reached | the same |
| non-B-tree | the auto-analyze stand-in, a plain `ANALYZE` | `h05` | reached | the same |
| both | a table the census analyzed, and one it declined | `tc_past`, and `tc_exact` exactly on its threshold | reached | the same |
| non-B-tree | an empty index and an untouched index | `h07`, `h00` | reached | the same |
| non-B-tree | a non-default `fillfactor` or `pages_per_range` | `h03`, `s10`, `b12` | reached | the same |
| non-B-tree | a non-core access method under the admission rule | - | **skipped**: the ported corpus has no `bloom` fixture | the same |
| GIN | keys that no longer occur after churn | `n04` | reached: 5,261 entry pages grew to 39,592 | the same |
| GIN | emptied posting-tree pages | `n03`, `n10` | reached: 912 and 375 pages deleted | the same |
| GIN | half-empty posting-tree leaves with nothing deletable | `n04`, as declared | **not reached**: `n04` holds no posting-tree page at all, 0 data pages before and after its churn | the same |
| GIN | a populated pending list, and the same index after a flush | `n05` | reached: 2,206 pending pages before the maintenance step, 0 after | the same |
| GIN | an untouched index and an empty index | `n08`, `n09` | reached | the same |
| GIN | a snapshot held across the settling `VACUUM` | `n10` | reached: 960,000 tuples dead but not yet removable under it, and no posting-tree page deleted; the 375 pages deleted later came after the release | the same |
| GIN | more than one operator class | `n06`, `n07` | reached: `jsonb_path_ops` and `tsvector_ops` beside `array_ops` | the same |
| GIN | one rebuild at more than one `maintenance_work_mem` | probe P3 | reached: 46,784,512, 48,021,504 and 49,143,808 bytes at 4MB, 64MB and 256MB | 46,825,472, 47,980,544 and 49,143,808 |
| GIN | the GIN auto-analyze stand-in, `ANALYZE` plus `gin_clean_pending_list()` | `n12` | reached | the same |
| GIN | an undecodable or unclassifiable page, and an all-zero page | - | **skipped**: the method reads no index page | the same |
| GIN | a concurrent `VACUUM`, a concurrent rebuild and a writer stream | - | **skipped**: every measurement is single-session under the measurement lock | the same |

### Known limitations

- **It measures growth, not waste.** Both tests fire on legitimate growth, and on BRIN
  every change they can see is legitimate. A table that only grows will have its indexes
  rebuilt every 30 % for nothing. The results tables are the measurement of this.
- **The tuple test's rising half is noise on these fixtures.** Every rise it caught was a
  false positive, and every fall a true positive.
- **Dead entries that no `VACUUM` removed are invisible** until the table has shrunk 30 %.
  A `VACUUM` run with `INDEX_CLEANUP OFF` leaves them, because it switches off index
  vacuuming and index cleanup before the scan starts
  ([vacuumlazy.c#do_index_cleanup-init](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L387-L397)).
  This page does not measure that case. Its two fixtures were removed at the asker's
  request, and since 2026-09-24 neither protocol has required a run to reach it.
- **A rebuild done elsewhere counts only when it shrank the file.** Without a relation
  file number in the payload, an out-of-band `REINDEX` of a grown index is followed by a
  second one.
- **A partial index is judged by its whole table's count.** The brief's second value is
  the table's; a predicate population can move far without the table's count moving.
- **A stored count of `-1` disables the tuple test** until the next write of the baseline.
- **A whole line of the form `@nbmaint:{...}` is reserved.** A person who writes one has
  written a payload as far as the method can tell; two such lines stop the method on that
  index until one is removed. `@nbmaint:` inside a line of prose is left alone.
- **Step 2 rebuilds with the blocking form**, which stops writers on the table for the
  whole rebuild. The concurrent form has to be run from the top level.
- **Step 2 takes `ACCESS EXCLUSIVE` on every index it writes to**, even to write only a
  comment, for the length of that index's transaction; queries on that index wait behind
  it for up to `lock_timeout`, and the `ALTER INDEX` that takes it fires DDL event
  triggers.
- **Step 1 is all or nothing.** It is one statement, so one candidate index held in
  `ACCESS EXCLUSIVE` elsewhere for longer than `lock_timeout` cancels it; step 2 goes on
  without that index.
- **Step 2's `statement_timeout` bounds the whole run**, not one rebuild. Rebuilds
  already committed keep their baselines when it fires.
- **PostgreSQL 13 to 16 were not built.** The texts use nothing newer than 12, and the
  facts this page depends on were measured on 12.2 and 17.11 only.
- **A [standby](../../../glossary.md#hot-standby) can run step 1 only.** `COMMENT` is classified as not read-only, and a
  server in recovery refuses such a command, so step 2 fails at its first write
  ([utility.c#comment-not-read-only](../../../../raw/postgres-17/src/backend/tcop/utility.c#L164-L217),
  [utility.c#recovery-gate](../../../../raw/postgres-17/src/backend/tcop/utility.c#L570-L583)).

## Measurement Script

Every number on this page comes from the two scripts below, one per version leg, Bash and
SQL only. Each builds its own server from its pinned checkout and takes the page's two
filed texts out of this page, so the text that is scored is the text that is published.

### How to use the two leg scripts

| Item | 17 leg, `nbmaint_suite_v17.sh` | 12 leg, `nbmaint_suite_v12.sh` |
|---|---|---|
| Purpose | Build 17.11 out of tree, run the engine and [contrib](../../../glossary.md#contrib) [regression suites](../../../glossary.md#regression-test), start an isolated cluster, run both filed texts on an empty database, discover the version-local facts, file the declarations, build the source page's 29 fixtures, store their baselines with step 2, churn and maintain them under the no-defeat proofs, run the simulated auto-analyze census, decide with step 1 under the measurement lock, rebuild every fixture as the oracle, run step 2 on the rebuilt state, score, run four probes and the edge cases, and check the page against what ran. Every number in [Answer](#answer) that names 17.11 is one of its outputs | The same on 12.2, with 28 fixtures: `b11` also needs an operator class 12.2 does not have. Every number that names 12.2 is one of its outputs |
| Invocation | Save the block to `.wiki-runtime/tmp/nbmaint_suite_v17.sh` and run `bash .wiki-runtime/tmp/nbmaint_suite_v17.sh` from the repository root. It exits 0 only when every stage and every required check passed. To score a finished run again: `bash .wiki-runtime/tmp/nbmaint_suite_v17.sh score criteria`. To run the fixtures again, start at `fixtures`, which rebuilds the fixture database; `reset` drops every database, so a new run starts at `declare` | The same with `nbmaint_suite_v12.sh` |
| Stages | `build check cluster texts exact facts declare fixtures churn autoanalyze crosscheck decide oracle act score probes edge defeat verify criteria report`, in that default order; `start`, `stop`, `reset` and `clean` run only when named. `churn`, `autoanalyze`, `decide`, `oracle` and `act` change the fixtures: each refuses to run before the stages it depends on, and after a later one has changed what it would read. `crosscheck`, `score` and `probes` may run again, and replace their own records | the same |
| Environment | `WIKI_ROOT` (`$PWD`), `PAGE` (this page), `SRC` (`$WIKI_ROOT/raw/postgres-17`), `SANDBOX` (`$WIKI_ROOT/.wiki-runtime/tmp/nbmaint17`), `PORT` (`55417`), `JOBS` (`8`), `BASE_ROWS` (`1000000`), `BRIN_ROWS` (`2000000`), `SMALL_ROWS` (`300000`), `GIN_ROWS` (`600000`), `HOT_ROWS` (`1200000`), `A05_INSERTS` (`120000`), `ROUNDS` (`6`), `MWM` (`256MB`) | the same names; `SRC` defaults to `raw/postgres-12`, `SANDBOX` to `.wiki-runtime/tmp/nbmaint12`, `PORT` to `55412` |
| Prerequisites | See [Prerequisites](#prerequisites) | the same |
| Output | Everything under `$SANDBOX/out`. Read `criteria.txt` first, then `score-table.txt`, `score-summary.txt`, `invariants.txt` and `maintenance-proof.txt`; see [Where the results land](#where-the-results-land) | the same, under the 12 leg's sandbox |
| Runtime | 10 min 22 s from an empty sandbox on the recorded host, run alongside the 12 leg: 65 s to build, 32 s of regression suites, 59 s of fixtures, 6 min 10 s of churn, 51 s of oracle. About 9 min from a built tree | 10 min 54 s from an empty sandbox on the recorded host, run alongside the 17 leg: 60 s to build, 26 s of regression suites, 59 s of fixtures, 7 min 02 s of churn, 42 s of oracle. About 10 min from a built tree; the 12 leg's churn includes its one-second publication waits |
| Cleanup | `bash .wiki-runtime/tmp/nbmaint_suite_v17.sh clean` first checks that the sandbox resolves, with every symbolic link and `..` taken out, to a directory directly under this repository's `.wiki-runtime/tmp` that carries the marker the script wrote when it created it, and refuses anything else before it stops or deletes. It then stops the cluster with `pg_ctl -m fast -w stop`, confirms no `postmaster.pid`, no `postgres` process on the data directory and an empty socket directory, and deletes the sandbox. A run that fails stops its own cluster on the way out. **`out/` is inside the sandbox, so copy it out first** | the same; the two legs have separate sandboxes, so either can be cleaned while the other runs |

### The stages

| Stage | What it does |
|---|---|
| `build` | refuses unless the checkout is the leg's pinned commit with no tracked file changed; configures it out of tree with `--without-icu --without-readline --with-zlib --enable-debug`, builds, installs, installs [`pageinspect`](../../../glossary.md#pageinspect), `pgstattuple` and [`pg_freespacemap`](../../../glossary.md#pg_freespacemap) from the same tree, and writes `nbmaint-build-manifest.txt` into the install: the pin, the flags, a hash of the build tree's `config.status` and a hash of every installed file. An existing install is reused only when all four still match |
| `check` | checks the manifest again, then `make check`, then `make check` in each contrib module that has a suite; any suite that does not exit 0 with all its tests passed fails the run |
| `cluster` | `initdb --locale=C --encoding=UTF8`, the settings below, the start, the `scratch` database, and the settings actually in force with their contexts |
| `texts` | takes step 1 and step 2 out of this page by their tags, hashes them against the values recorded in the script, checks that their shared pipeline is byte-identical, and builds the one-edit view; a hash that differs, or a pipeline that does, fails the run |
| `exact` | runs both texts, unmodified, on a database with one hash, one GiST and one B-tree index: step 1, step 2, the comments written, step 2 again, step 1 again; a text that fails, or a second run that writes, fails the run |
| `facts` | every version-local fact the texts and the harness depend on, discovered on the running server |
| `declare` | files the declared kinds, the method's thresholds, the pay-off threshold, the 29 predictions (28 on the 12 leg), 18 invariants, 3 declared exceptions and the coverage plan into their own database, and refuses to run once the fixture database exists |
| `fixtures` | builds every fixture, takes a locked page census of each, then runs step 2 once, which must write a version-2 payload into every fixture index |
| `churn` | per fixture: the recipe's writes, a locked census of the unmaintained state, the maintenance step in a session with every timeout at 0, the no-defeat check, and a locked census of the maintained state; the BRIN stand-in and the two held-snapshot fixtures in line. **It dies at the first defeated maintenance**, so nothing after it runs |
| `autoanalyze` | the simulated auto-analyze census: the launcher's analyze verdict recomputed per table, and `ANALYZE` on the tables it names |
| `crosscheck` | `VACUUM VERBOSE`'s index line from each maintenance `VACUUM`, stored against the censuses just before and just after it; the horizon holders, the `pgstattuple` refusals, the instrument matrix, and the census summary |
| `decide` | step 1, verbatim, in one transaction holding `SHARE ROW EXCLUSIVE` on every fixture table, then the same rows through the view and the harness's own reading of every index, in that transaction |
| `oracle` | `REINDEX INDEX` on every fixture at `maintenance_work_mem = 256MB`, with `pg_relation_size(index, 'main')` and the heap's `relpages` and `reltuples` read before and after |
| `act` | step 1, step 2 and step 2 again on the state the oracle left; fails the run unless step 2 did what step 1 printed and its second run wrote nothing |
| `score` | refuses to score if any maintenance proof failed; otherwise scores every decision against the oracle and the filed predictions on the unrounded reclaimed fraction, evaluates the 18 invariants, writes every census reading to `meas.csv`, and fails the run if any declared invariant fails |
| `probes` | who writes `reltuples`, the hash oracle's dependence on the heap estimate, the GIN oracle's dependence on `maintenance_work_mem`, and which GiST operator classes can take a sorted build |
| `edge` | the comment shapes, the two tests' boundaries, the filters, the lock and concurrency rounds, a role that owns nothing, both `REINDEX` forms, another session's temporary index and the rebuild cap, each with its expected result filed first, in their own database; any difference fails the run |
| `defeat` | a throwaway fixture whose maintenance is defeated on purpose by an undeclared snapshot; fails the run if the no-defeat check does not stop that step |
| `verify` | takes both texts and this script out of the page again and compares them with what ran; any difference fails the run |
| `criteria` | collects the results a reader checks first, the timeouts in force in every `VACUUM` and `ANALYZE` session of the run, and the server-log audit; an unexpected error or a maintenance skip line fails the run |
| `report` | lists the output files |
| `start`, `stop`, `reset`, `clean` | start the built cluster; stop it cleanly and confirm the stop; drop the three databases and the edge role; stop and delete the sandbox, after the checks above |

### The cluster settings

| Setting | Value | Context | Apply scope |
|---|---|---|---|
| `listen_addresses`, `port`, `unix_socket_directories`, [`shared_buffers`](../../../glossary.md#shared_buffers) | `''`, the leg's port, the sandbox's socket directory, `512MB` | `PGC_POSTMASTER` | restart |
| `autovacuum` | `off` | `PGC_SIGHUP` | reload |
| [`fsync`](../../../glossary.md#fsync) | `off` | `PGC_SIGHUP` | reload |
| `log_timezone`, `log_line_prefix` | `UTC`, `%m [%p] ` | `PGC_SIGHUP` | reload |
| `maintenance_work_mem` | `256MB` | `PGC_USERSET` | session or transaction |
| `max_parallel_maintenance_workers` | `0` | `PGC_USERSET` | session or transaction |
| [`work_mem`](../../../glossary.md#work_mem) | `64MB` | `PGC_USERSET` | session or transaction |
| `timezone` | `UTC` | `PGC_USERSET` | session or transaction |
| `statement_timeout`, `lock_timeout` | `1800s`, `15s` through `PGOPTIONS`, and `0` in every `VACUUM` and `ANALYZE` session | `PGC_USERSET` | session or transaction |
| `transaction_timeout`, `idle_in_transaction_session_timeout` | `0` in every `VACUUM` and `ANALYZE` session; the first exists on 17 only | `PGC_USERSET` | session or transaction |

`autovacuum` is off for isolation only: every fixture runs the maintenance a launcher would
have run. `max_parallel_maintenance_workers = 0` keeps every build and every `VACUUM` on
the serial path, so the oracle is one code path on both servers; the source page's run
left it at the default of 2. The contexts come from
[guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457),
[guc_tables.c#fsync](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1096-L1107),
[guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270),
[guc_tables.c#work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2447-L2458),
[guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2465-L2474),
[guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417),
[guc_tables.c#log_timezone](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4104-L4112)
and [guc_tables.c#TimeZone](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4394-L4403),
and the running servers reported the same contexts.

### Prerequisites

- A C toolchain, `make`, `bison`, `flex` and `perl`. Each leg builds its own server; no
  installed PostgreSQL is used, and neither leg touches a cluster it did not start.
- zlib headers. ICU and readline are not needed: both legs configure `--without-icu
  --without-readline`, and `initdb` runs with `--locale=C --encoding=UTF8`, which is what
  makes the text and `tsvector` fixtures deterministic.
- The pinned checkouts at `raw/postgres-17` and `raw/postgres-12`, read only. `git` reads
  the commit each checkout is on and whether a tracked file differs from it, with
  `--no-optional-locks`, so it writes nothing into the checkout.
- `sha256sum`, `cmp`, `diff`, `find`, `sort`, `sed`, `grep`, `seq`, `pgrep`.
- `bash`, and a `grep` that takes `-E`. The recorded runs used Homebrew's `bash` 5.3.15
  and the system BSD `grep` 2.6.0; neither leg was run under macOS's own `/bin/bash` 3.2.
- The leg's port free, and about 8 GB of disk under `.wiki-runtime/tmp/` per leg. The
  sandbox must be a new directory directly under `.wiki-runtime/tmp`, or one this script
  created; the script refuses any other.
- Superuser on the sandbox cluster, which `initdb` gives the invoking user, because
  `pageinspect`'s raw-page reader requires it
  ([rawpage.c#get_raw_page_internal](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L141-L199)).

### Where the results land

| File | What is in it |
|---|---|
| `criteria.txt` | the summary a reader checks first |
| `hashes.txt`, `exact.txt`, `facts.txt` | the two texts' hashes and pipeline check, both texts on an empty database, and the version-local facts |
| `checks.txt`, `check-*.log` | the regression suites |
| `settings.txt`, `version.txt`, `pin.txt`, `timing.txt` | the settings in force with their contexts, the server version, the commit the install was built from by its manifest beside the commit the checkout is on, and each stage's duration |
| `../inst/nbmaint-build-manifest.txt` | the build manifest: pin, flags, build configuration hash, compiler, platform, and the hash of every installed file |
| `declared.txt` | every declaration, and the moment it was filed |
| `baseline-sizes.txt`, `baseline-apply.txt` | the as-built sizes, and step 2's first run |
| `maintenance-proof.txt`, `horizon-holders.txt`, `maint-*.log`, `settle2-*.log`, `standin-b13.log` | the no-defeat proofs per maintenance step, the horizon readings, and each step's own output with the timeouts it ran under |
| `census-*.log`, `census-summary.txt`, `maintenance-pair.txt` | one locked census per fixture and phase, and the size before and after each maintenance step |
| `meas.csv` | every census reading the fixture database stored, one row per fixture, phase and metric, with a header row; the only file that keeps readings no other file prints, such as a hash index's overflow pages and freed bitmap bits and a GiST index's leaf pages |
| `autoanalyze-verdicts.txt`, `autoanalyze-named.txt` | the simulated auto-analyze census |
| `verbose-lines.txt`, `instrument-matrix.txt`, `pgstattuple-refusals.txt` | `VACUUM`'s index line per maintenance `VACUUM`, which reader accepted which AM, and every `pgstattuple` refusal |
| `decide.txt`, `decide-cost.txt` | step 1's own output under the measurement lock, and its duration |
| `oracle-summary.txt`, `phase-sizes.txt` | the oracle per fixture, and every phase size |
| `score-table.txt`, `score-summary.txt`, `invariants.txt`, `invariant-detail.txt` | the scored table, its totals, the 18 invariants with whether each held, and the per-census and per-`VACUUM` detail behind I6, I8, I9 and I18 |
| `act.txt`, `plan-act.txt`, `apply-act*.log` | step 1 and step 2 on the rebuilt state |
| `probe-p1.txt` to `probe-p4.txt` | the four probes |
| `edge.txt`, `plan-edge*.txt`, `apply-edge*.log` | the edge cases, expected against observed |
| `defeat.txt`, `defeat-run.log` | the deliberately defeated maintenance step and the check that stopped it |
| `verify.txt` | the page against what ran |
| `server.log`, `server-errors-all.txt`, `server-errors-unexpected.txt` | the server log and its audit |

### The last run

Each leg ran from an empty sandbox through every default stage, with the script text
published below, on 2026-09-24, the two legs side by side. Two passes ran the same way
before it:

- a baseline pass of the scripts filed on 2026-09-22, unchanged: 10 min 30 s on the 17
  leg and 10 min 58 s on the 12 leg, both exit status 0. It reproduced every decision,
  score, prediction, invariant and edge verdict of that filing, and every size but
  `g09`'s;
- a pass of the edited scripts before their `score` stage wrote `meas.csv`: 9 min 39 s and
  10 min 27 s, both exit status 0, with the same result. It showed that two readings in
  the coverage table, `h01`'s overflow and bitmap counts and `g07`'s leaf count, lived
  only in the fixture database that `clean` deletes, which is why the stage now writes
  them out.

The recorded run matched both passes on every decision, score, prediction, invariant and
edge verdict. Only `g09`'s sizes, the `ANALYZE`-sampled tuple ratios, step 1's duration,
the timings and whether the 17 leg's census also analyzed `h00` moved between the three;
see [Open Questions](#open-questions).

| Item | 17 leg | 12 leg |
|---|---|---|
| Date | 2026-09-24, 20:44:46Z to 20:55:08Z | 2026-09-24, 20:44:46Z to 20:55:40Z, beside the 17 leg |
| Server | PostgreSQL 17.11, built from `786db8dcf168bd9df8f55047337525ac19118b1c` | PostgreSQL 12.2, built from `45b88269a353ad93744772791feb6d01bc7e1e42` |
| Build manifest | built 20:45:51Z from the pin with no tracked file changed; `config.status` `5c749f3a4554b67c…`; installed files `872a5dbd5770e291…` | built 20:45:46Z from the pin with no tracked file changed; `config.status` `6f7ecc70651c1cba…`; installed files `79499658f933bb0c…` |
| Platform | Darwin 27.0.0 arm64 (macOS 27.0), Apple clang 21.0.0, 10 cores, `JOBS=8`, Homebrew `bash` 5.3.15 | the same |
| [`block_size`](../../../glossary.md#blcksz), [`max_data_alignment`](../../../glossary.md#alignment) | 8192, 8 | 8192, 8 |
| Engine tests | core **All 225**; `pageinspect` All 8; `pgstattuple` All 1; `pg_freespacemap` All 1 | core **All 192**; `pageinspect` All 5; `pgstattuple` All 1; `pg_freespacemap` has no suite in 12.2 |
| Declarations filed, first baseline payload written | 20:46:26Z, 20:47:25Z | 20:46:16Z, 20:47:15Z |
| Text hashes | step 1 `89293844dee3972f…`, step 2 `52bcbea7214af4f8…`, both matching the values in the script; shared pipeline identical | the same |
| Script SHA-256 | `f8f2e4f00f457e4106115245f6589411565a8de87f403e354a29a2ae861931fd` | `13845e3cbb4ead75e0ed33f337243316a4be152020b9c3adea76c4223ed20a1f` |
| The page against what ran | both texts, and the script block below, byte-identical to the files that ran | the same |
| Server log | 31 `ERROR` and `FATAL` lines, all 31 deliberate; 0 maintenance skip lines | 33, all deliberate; 0 |
| Teardown | the `clean` stage: `pg_ctl -m fast` stop, no `postmaster.pid`, no `postgres` process on the data directory, empty socket directory, sandbox deleted | the same |

The timings above are from a host running both legs at once; the sizes, the decisions and
the scores do not depend on them. Every number on this page is from these two runs, except
the figures from earlier passes that this section and [Open Questions](#open-questions)
name as such.

### The PostgreSQL 17 leg script

```bash
#!/usr/bin/env bash
#
# nbmaint_suite_v17.sh - the PostgreSQL 17 leg of the measurement behind the
# wiki page "A COMMENT-Stored Baseline Non-B-Tree Index-Maintenance Heuristic
# for PostgreSQL 12 Through 17", in bash and SQL only.
#
# It builds 17.11 out of tree from the pinned checkout, runs the engine
# regression suites, starts an isolated cluster, takes the page's two filed
# texts out of the page itself - step 1, the read-only plan, and step 2, the DO
# block that carries it out - and scores them on the numbered fixtures of
# the wiki page "Detecting Inflated Non-B-Tree Indexes From Catalogs and a
# COMMENT-Stored Baseline in PostgreSQL 17", under both of the wiki's
# protocols: "Mandatory Non-B-Tree, Non-GIN Bloat Tests" for the hash, GiST,
# SP-GiST and BRIN fixtures and "Mandatory GIN Bloat Tests" for the GIN ones.
# All 29 of that page's numbered fixtures are built.  h06 and n11, whose
# VACUUM ran with INDEX_CLEANUP OFF, left this corpus on 2026-09-22 and that
# page on 2026-09-24, when both protocols stopped requiring that case.
#
# Five phases per fixture.  build: create, load, ANALYZE, create the index,
# ANALYZE.  baseline: a locked page census, then step 2's first run, which
# writes the as-built @nbmaint: payload into every fixture index's comment.
# churn: the recipe's writes, the maintenance step, the simulated auto-analyze
# census.  decide: step 1, verbatim, under SHARE ROW EXCLUSIVE on every
# fixture table.  oracle: REINDEX INDEX bracketed by pg_relation_size(index,
# 'main').  Every decision is scored against that oracle at the pay-off
# threshold the declare stage files before the first fixture exists.
#
# Every session that issues a VACUUM or an ANALYZE forces statement_timeout,
# lock_timeout, transaction_timeout and idle_in_transaction_session_timeout to
# 0 and prints the settings in force.  Every maintenance step is checked
# against the no-defeat rule as soon as it returns, and the run dies rather
# than score when one was defeated.
#
# A run fails - exit status 1, with the cluster stopped - when a stage fails,
# a regression suite fails, a required check fails, or the page differs from
# what ran.  The stages that change the fixtures run once each and in order;
# a stage that only reads or re-scores replaces its own records when it runs
# again, and every stage refuses to run before the stages it depends on.
#
# Every object this script creates is DISPOSABLE.  It runs its own cluster on
# a non-default port with its own socket directory, never touches a cluster it
# did not start, and treats raw/postgres-17 as read only.  Before it writes,
# stops or deletes anything it checks that the sandbox is a directory it
# created itself, directly under this repository's .wiki-runtime/tmp.
#
# Usage, from the repository root:
#   bash .wiki-runtime/tmp/nbmaint_suite_v17.sh                  # every stage
#   bash .wiki-runtime/tmp/nbmaint_suite_v17.sh score criteria   # re-score a run
#   bash .wiki-runtime/tmp/nbmaint_suite_v17.sh clean            # stop, delete
#
# Stages, in the default order: build check cluster texts exact facts declare
# fixtures churn autoanalyze crosscheck decide oracle act score probes edge defeat
# verify criteria report.  Not in the default order: start stop reset clean.
#
# Environment: WIKI_ROOT PAGE SRC SANDBOX PORT JOBS BASE_ROWS BRIN_ROWS
#              SMALL_ROWS GIN_ROWS HOT_ROWS A05_INSERTS ROUNDS MWM
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v17/questions/indexing/non-btree-comment-baseline-maintenance-heuristic.md}"
SRC="${SRC:-$WIKI_ROOT/raw/postgres-17}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/nbmaint17}"
PORT="${PORT:-55417}"
JOBS="${JOBS:-8}"
BASE_ROWS="${BASE_ROWS:-1000000}"
BRIN_ROWS="${BRIN_ROWS:-2000000}"
SMALL_ROWS="${SMALL_ROWS:-300000}"
GIN_ROWS="${GIN_ROWS:-600000}"
# n10 is sized so that three posting trees exist and the fixture clears the
# source page's own 1 MB floor; this method has no floor, but the recipe is
# ported unchanged
HOT_ROWS="${HOT_ROWS:-1200000}"
# h05 and n12 sit above the analyze threshold and below the vacuum thresholds,
# the one window in which an auto-analyze is the whole of a table's maintenance
A05_INSERTS="${A05_INSERTS:-120000}"
ROUNDS="${ROUNDS:-6}"
MWM="${MWM:-256MB}"

LEG=17
# The one commit this leg measures, and how it is built.  The build stage
# refuses any other commit, and an install it did not build from this commit
# with these flags - by its own manifest - is never reused.
EXPECTED_PIN=786db8dcf168bd9df8f55047337525ac19118b1c
CONFIGURE_FLAGS="--without-icu --without-readline --with-zlib --enable-debug"
DB=nbmaint; PDB=protocol; EDB=edge; XDB=scratch

# SHA-256 of the page's two filed texts as last measured.  A text that differs
# fails the texts stage: it must be re-measured and these refiled.
BASE_PLAN=89293844dee3972f60ee34c977805cf42075456f7a029d2e23c8c9e127c39f2f
BASE_APPLY=52bcbea7214af4f8e42fa09735a755a6d8c4eb414b18f22ebce3ab64980e924d

# The run's own session timeouts: they bound a census and a rebuild.  Every
# session that issues a VACUUM or an ANALYZE overrides them with zero_timeouts.
export PGOPTIONS="-c statement_timeout=1800s -c lock_timeout=15s"

HASHFX="h00 h01 h02 h03 h04 h05 h07 h08 h12"
GISTFX="g06 g07 g08 g09"
SPGFX="s08 s09 s10"
BRINFX="b10 b11 b12 b13"
GINFX="n03 n04 n05 n06 n07 n08 n09 n10 n12"
SCORED="$HASHFX $GISTFX $SPGFX $BRINFX $GINFX"
SKIPPED=""

say()  { printf '\n=== %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
# die stops the run.  Inside a subshell - a pipeline, a $(...) - exit ends
# only that subshell, so die also appends to FAILMARK, which the dispatcher
# reads after every stage.  EXPECT_DIE is set only in the one subshell that
# provokes a die on purpose and records its exit status.
die()  {
  printf 'FATAL: %s\n' "$*" >&2
  if [ -z "${EXPECT_DIE:-}" ] && [ -n "${FAILMARK:-}" ]; then
    printf '%s\n' "$*" >> "$FAILMARK" 2>/dev/null
  fi
  exit 1
}

# psql helpers.  -X ignores ~/.psqlrc and ON_ERROR_STOP is on, and every
# helper but three stops the run when psql fails.  qtry returns the failure to
# its caller, which wants the server's refusal as its result; qe runs without
# ON_ERROR_STOP for the same reason; qbg is a background session that another
# session terminates on purpose.
PSQL() { "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" "$@"; }
q()    { PSQL -d "$1" -At -c "$2" || die "psql failed on $1: ${2:0:120}"; }
qf()   { PSQL -d "$1" -f "$2" || die "psql failed on $1: file $2"; }
qin()  { PSQL -d "$1" || die "psql failed on $1: standard input"; }
qat()  { PSQL -d "$1" -At -f "$2" || die "psql failed on $1: file $2"; }
qtry() { PSQL -d "$1" -At -c "$2"; }
qe()   { "$BIN/psql" -X -h "$SOCK" -p "$PORT" -d "$1"; }
qbg()  { PSQL -d "$1"; }

# The preamble of every session that issues a VACUUM or an ANALYZE: the four
# settable timeouts forced to 0, which is what an autovacuum launcher and a
# worker do to themselves, then the settings actually in force, read back.
TIMEOUT_GUCS="'statement_timeout','lock_timeout','transaction_timeout','idle_in_transaction_session_timeout'"
zero_timeouts() {
  printf "SET /* wiki_nbmaint_zero_timeouts */ statement_timeout = 0;\n"
  printf "SET /* wiki_nbmaint_zero_timeouts */ lock_timeout = 0;\n"
  printf "SET /* wiki_nbmaint_zero_timeouts */ transaction_timeout = 0;\n"
  printf "SET /* wiki_nbmaint_zero_timeouts */ idle_in_transaction_session_timeout = 0;\n"
  printf "SELECT /* wiki_nbmaint_zero_timeouts */ 'timeouts in force: '\n"
  printf "       || string_agg(name || '=' || setting, ' ' ORDER BY name)\n"
  printf "  FROM pg_settings WHERE name IN (%s);\n" "$TIMEOUT_GUCS"
}
# qz <db>: run stdin in a session that begins with zero_timeouts
qz() { { zero_timeouts; cat; } | PSQL -d "$1" -At || die "psql failed on $1: a zero-timeout session"; }

# errf <db> <sql>: run a statement expected to fail, print the error or
# "accepted"
errf() {
  local out
  out=$(printf '%s\n' "$2" | "$BIN/psql" -X -q -v ON_ERROR_STOP=0 -h "$SOCK" -p "$PORT" \
          -d "$1" -f - 2>&1 | grep -E 'ERROR' | head -1 | sed -E 's/^psql:[^ ]* //')
  printf '%s' "${out:-accepted}"
}
# md_block_with <language> <tag> <file>: print the fenced block of that
# language which contains <tag>.  The fence is assembled from printf '\140'
# so that this script contains no literal Markdown fence.
md_block_with() {
  local lang=$1 tag=$2 file=$3 inb=0 line buf="" tick fence
  tick=$(printf '\140'); fence="$tick$tick$tick"
  while IFS= read -r line || [ -n "$line" ]; do
    if [ "$inb" = 1 ]; then
      if [ "$line" = "$fence" ]; then
        inb=0
        case "$buf" in *"$tag"*) printf '%s' "$buf"; return 0 ;; esac
        buf=""; continue
      fi
      buf="$buf$line
"
    elif [ "$line" = "$fence$lang" ]; then
      inb=1; buf=""
    fi
  done < "$file"
  return 1
}

# plan_view <step 1 file>: the one documented edit.  The two SET lines are
# dropped, because a view cannot carry them, and the rest becomes the view
# proto.plan_v, so the harness can store what the filed statement decides
# without re-typing it.
plan_view() {
  local line
  printf 'DROP VIEW IF EXISTS proto.plan_v;\nCREATE VIEW proto.plan_v AS\n'
  while IFS= read -r line; do
    case $line in
      "SET /* wiki_nbmaint_statement_timeout"*) continue ;;
      "SET /* wiki_nbmaint_lock_timeout"*)      continue ;;
    esac
    printf '%s\n' "$line"
  done < "$1"
}


sha() { sha256sum < "$1" | cut -d' ' -f1; }
tbl() { printf 'f_%s' "$1"; }
idx() { printf 'f_%s_i' "$1"; }
fx_am() {
  case "$1" in
    h*) printf 'hash' ;; g*) printf 'gist' ;; s*) printf 'spgist' ;;
    b*) printf 'brin' ;; n*) printf 'gin' ;;
  esac
}

# ------------------------------------------------------------ the sandbox ----
# SANDBOX, WIKI_ROOT and PAGE come from the environment, so nothing is written,
# stopped or deleted until they have been checked here.  WIKI_ROOT must be
# this repository; SANDBOX must resolve, with every symbolic link and every
# ".." taken out, to a plain directory directly under its .wiki-runtime/tmp;
# and an existing sandbox must carry the marker this script writes when it
# creates one, naming this leg.  From here on every path is the canonical one.
canon_dir() { ( cd -P -- "$1" 2>/dev/null && pwd -P ); }
MARKER_NAME=.nbmaint-sandbox
sandbox_guard() {   # <create|existing>
  local mode=$1 root tmp parent base
  root=$(canon_dir "$WIKI_ROOT") || die "WIKI_ROOT $WIKI_ROOT is not a directory"
  [ -f "$root/AGENTS.md" ] && [ -f "$root/wiki/versions.md" ] && [ -d "$root/raw" ] \
    || die "WIKI_ROOT $root is not the wiki repository"
  if [ ! -d "$root/.wiki-runtime/tmp" ]; then
    [ "$mode" = create ] || { SANDBOX_STATE=absent; return 0; }
    mkdir -p "$root/.wiki-runtime/tmp" || die "cannot create $root/.wiki-runtime/tmp"
  fi
  tmp=$(canon_dir "$root/.wiki-runtime/tmp") || die "no $root/.wiki-runtime/tmp"
  case "$tmp" in "$root"/*) : ;; *) die "$root/.wiki-runtime/tmp resolves outside the repository, to $tmp" ;; esac
  base=${SANDBOX%/}; base=${base##*/}
  case "$base" in
    ''|.|..|*[!A-Za-z0-9._-]*) die "refusing sandbox $SANDBOX: its last component must be a plain name" ;;
  esac
  parent=$(canon_dir "$(dirname -- "$SANDBOX")") || die "the parent of $SANDBOX does not exist"
  [ "$parent" = "$tmp" ] || die "refusing sandbox $SANDBOX: it resolves under $parent, not directly under $tmp"
  WIKI_ROOT=$root
  SANDBOX="$tmp/$base"
  if [ -L "$SANDBOX" ]; then
    die "refusing sandbox $SANDBOX: it is a symbolic link"
  elif [ -e "$SANDBOX" ]; then
    [ -d "$SANDBOX" ] || die "refusing sandbox $SANDBOX: it is not a directory"
    [ "$(cat "$SANDBOX/$MARKER_NAME" 2>/dev/null)" = "nbmaint sandbox, leg $LEG" ] \
      || die "refusing sandbox $SANDBOX: it has no $MARKER_NAME marker for leg $LEG, so this script did not create it"
    SANDBOX_STATE=ours
  elif [ "$mode" = create ]; then
    mkdir -- "$SANDBOX" || die "cannot create $SANDBOX"
    printf 'nbmaint sandbox, leg %s\n' "$LEG" > "$SANDBOX/$MARKER_NAME" || die "cannot mark $SANDBOX"
    SANDBOX_STATE=ours
  else
    SANDBOX_STATE=absent
    return 0
  fi
  BUILD="$SANDBOX/build"; INST="$SANDBOX/inst"; BIN="$INST/bin"
  DATA="$SANDBOX/data"; SOCK="$SANDBOX/sock"; OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql"
  FAILMARK="$SANDBOX/.failed-stage"
}

# On every way out: the background sessions this run opened are ended, and a
# run that failed also stops its cluster, so a failure never leaves a
# postmaster behind.  A run that succeeded leaves the cluster up for the next
# selective run; the clean stage stops it and deletes the sandbox.
on_exit() {
  local rc=$?
  trap - EXIT INT TERM
  if [ "${SANDBOX_STATE:-}" = ours ] && [ -s "$DATA/postmaster.pid" ] \
       && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/psql" -X -At -h "$SOCK" -p "$PORT" -d postgres -c \
      "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity
        WHERE pid <> pg_backend_pid()
          AND (query LIKE '%wiki_nbmaint_snapshot%' OR query LIKE '%wiki_nbmaint_edge_%')" \
      > /dev/null 2>&1
    if [ "$rc" -ne 0 ]; then
      "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1 \
        && printf 'the run failed: cluster on %s stopped\n' "$DATA" >&2
    fi
  fi
  wait 2> /dev/null
  exit "$rc"
}

# ---------------------------------------------------------------- build ------
# The checkout must be the pinned commit with no tracked file changed.  A
# build leaves a manifest in the install naming that commit, the flags, the
# build tree's configuration and a hash of every installed file; an install
# is reused only when all four still match.
install_inventory() {
  ( cd "$INST" && find . -type f ! -name nbmaint-build-manifest.txt -exec sha256sum {} + ) \
    | LC_ALL=C sort -k2 | sha256sum | cut -d' ' -f1
}
manifest_value() { sed -n "s/^$1: //p" "$INST/nbmaint-build-manifest.txt" 2>/dev/null | head -1; }
check_checkout() {
  local head
  head=$(git -C "$SRC" rev-parse HEAD 2>/dev/null) || die "$SRC is not a git checkout"
  [ "$head" = "$EXPECTED_PIN" ] || die "$SRC is at $head, not the pinned $EXPECTED_PIN"
  git -C "$SRC" --no-optional-locks diff --quiet HEAD -- \
    || die "$SRC has tracked files changed from $EXPECTED_PIN"
}
check_install() {
  [ -f "$INST/nbmaint-build-manifest.txt" ] || die "$INST has no build manifest: run clean, then build"
  [ "$(manifest_value pin)" = "$EXPECTED_PIN" ] \
    || die "the install was built from $(manifest_value pin), not $EXPECTED_PIN"
  [ "$(manifest_value configure)" = "$CONFIGURE_FLAGS" ] || die "the install was configured with other flags"
  [ "$(manifest_value build-config)" = "$(sha "$BUILD/config.status")" ] \
    || die "the build tree is not the one the install came from"
  [ "$(manifest_value inventory)" = "$(install_inventory)" ] \
    || die "the installed files differ from the ones the build left"
}
stage_build() {
  say "build: 17.11 out of tree from $SRC"
  mkdir -p "$OUT"
  check_checkout
  if [ -e "$INST" ]; then
    check_install
    note "reused, the manifest matches: $("$BIN/postgres" --version)"
  else
    [ -x "$SRC/configure" ] || die "no pinned checkout at $SRC"
    mkdir -p "$BUILD"
    ( cd "$BUILD" && "$SRC/configure" --prefix="$INST" $CONFIGURE_FLAGS > configure.log 2>&1 ) \
      || die "configure failed, see $BUILD/configure.log"
    ( cd "$BUILD" && make -j"$JOBS" -s > make.log 2>&1 ) || die "make failed, see $BUILD/make.log"
    ( cd "$BUILD" && make -s install > install.log 2>&1 ) || die "install failed"
    local m
    for m in pageinspect pgstattuple pg_freespacemap; do
      ( cd "$BUILD" && make -s -C "contrib/$m" install >> install.log 2>&1 ) \
        || die "contrib/$m install failed"
    done
    check_checkout   # the checkout did not move while it was built
    { printf 'pin: %s\n' "$EXPECTED_PIN"
      printf 'source: %s\n' "$SRC"
      printf 'configure: %s\n' "$CONFIGURE_FLAGS"
      printf 'build-config: %s\n' "$(sha "$BUILD/config.status")"
      printf 'version: %s\n' "$("$BIN/postgres" --version)"
      printf 'compiler: %s\n' "$(cc --version 2>/dev/null | head -1)"
      printf 'platform: %s\n' "$(uname -srm)"
      printf 'built: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      printf 'inventory: %s\n' "$(install_inventory)"
    } > "$INST/nbmaint-build-manifest.txt" || die "cannot write the build manifest"
    check_install
  fi
  "$BIN/postgres" --version | tee "$OUT/version.txt"
  { printf 'install built from %s, per its manifest\n' "$(manifest_value pin)"
    printf 'checkout %s is at %s\n' "$SRC" "$(git -C "$SRC" rev-parse HEAD)"
  } | tee "$OUT/pin.txt"
}

# ---------------------------------------------------------------- check ------
# Every suite must exit 0 and report all its tests passed, or the run stops.
suite_result() {
  grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$1" | tail -1
}
stage_check() {
  say "check: make check, and the three contrib suites the cross-checks read"
  mkdir -p "$OUT"; : > "$OUT/checks.txt"
  check_checkout
  check_install
  local rc m res bad=""
  ( cd "$BUILD" && make -s check > "$OUT/check-core.log" 2>&1 ); rc=$?
  res=$(suite_result "$OUT/check-core.log")
  printf 'core exit=%s %s\n' "$rc" "$res" >> "$OUT/checks.txt"
  { [ "$rc" = 0 ] && case "$res" in All*passed) true ;; *) false ;; esac; } || bad="$bad core"
  for m in pageinspect pgstattuple pg_freespacemap; do
    ( cd "$BUILD" && make -s -C "contrib/$m" check > "$OUT/check-$m.log" 2>&1 ); rc=$?
    res=$(suite_result "$OUT/check-$m.log")
    printf '%s exit=%s %s\n' "$m" "$rc" "$res" >> "$OUT/checks.txt"
    { [ "$rc" = 0 ] && case "$res" in All*passed) true ;; *) false ;; esac; } || bad="$bad $m"
  done
  cat "$OUT/checks.txt"
  [ -z "$bad" ] || die "regression suites failed:$bad (see $OUT/checks.txt)"
}
# ---------------------------------------------------------------- cluster ----
# Settings and their apply scope, written before the first start:
#   listen_addresses, port, unix_socket_directories, shared_buffers
#                                                        -> PGC_POSTMASTER, restart
#   autovacuum, fsync, log_timezone, log_line_prefix     -> PGC_SIGHUP, reload
#   maintenance_work_mem, max_parallel_maintenance_workers, work_mem, timezone
#                                                        -> PGC_USERSET, session
# autovacuum is off for isolation only: the fixture runs the maintenance the
# launcher would have run.  max_parallel_maintenance_workers = 0 keeps every
# build and every VACUUM on the serial path, so the oracle is one code path.
stage_cluster() {
  say "cluster: isolated, port $PORT, socket directory $SOCK"
  mkdir -p "$OUT" "$SQLD" "$SOCK"
  if [ ! -d "$DATA" ]; then
    "$BIN/initdb" -D "$DATA" --locale=C --encoding=UTF8 > "$OUT/initdb.log" 2>&1 \
      || die "initdb failed, see $OUT/initdb.log"
    cat >> "$DATA/postgresql.conf" <<CONF
listen_addresses = ''
unix_socket_directories = '$SOCK'
port = $PORT
shared_buffers = 512MB
maintenance_work_mem = $MWM
max_parallel_maintenance_workers = 0
work_mem = 64MB
autovacuum = off
fsync = off
timezone = 'UTC'
log_timezone = 'UTC'
log_line_prefix = '%m [%p] '
CONF
  fi
  stage_start
  q postgres "SELECT 1 FROM pg_database WHERE datname = '$XDB'" | grep -q 1 \
    || q postgres "CREATE /* wiki_nbmaint_cluster */ DATABASE $XDB" > /dev/null
  q postgres "SELECT /* wiki_nbmaint_settings */ name || ' = ' || setting ||
                coalesce(' ' || unit, '') || ' [' || context || ']'
                FROM pg_settings
               WHERE name IN ('autovacuum','block_size','fsync','maintenance_work_mem',
                              'max_parallel_maintenance_workers','shared_buffers','work_mem',
                              'stats_fetch_consistency','timezone','log_timezone',
                              'autovacuum_analyze_threshold','autovacuum_analyze_scale_factor',
                              'autovacuum_vacuum_threshold','autovacuum_vacuum_scale_factor',
                              'autovacuum_vacuum_insert_threshold',
                              'autovacuum_vacuum_insert_scale_factor','autovacuum_naptime',
                              'statement_timeout','lock_timeout','transaction_timeout',
                              'idle_in_transaction_session_timeout','gin_pending_list_limit')
               ORDER BY name" > "$OUT/settings.txt"
  q postgres "SELECT /* wiki_nbmaint_settings */ 'max_data_alignment = ' || max_data_alignment
                || ', database_block_size = ' || database_block_size FROM pg_control_init()" \
    >> "$OUT/settings.txt"
  q postgres "SELECT /* wiki_nbmaint_settings */ version()" >> "$OUT/settings.txt"
  printf 'uname = %s\n' "$(uname -srm)" >> "$OUT/settings.txt"
  cat "$OUT/settings.txt"
}

stage_start() {
  mkdir -p "$OUT" "$SOCK"
  if [ -s "$DATA/postmaster.pid" ] && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    note "already running"
  else
    "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w start > /dev/null || die "pg_ctl start failed"
  fi
}

# ---------------------------------------------------------------- texts ------
stage_texts() {
  say "texts: step 1 and step 2 out of the page, hashed, and the one-edit view"
  [ -f "$PAGE" ] || die "no page at $PAGE; set PAGE or run from the repository root"
  mkdir -p "$SQLD" "$OUT"
  md_block_with sql wiki_nbmaint_plan_12_17 "$PAGE" > "$SQLD/plan.sql" \
    || die "step 1 (wiki_nbmaint_plan_12_17) not found in $PAGE"
  md_block_with sql wiki_nbmaint_apply_12_17 "$PAGE" > "$SQLD/apply.sql" \
    || die "step 2 (wiki_nbmaint_apply_12_17) not found in $PAGE"
  local h1 h2
  h1=$(sha "$SQLD/plan.sql"); h2=$(sha "$SQLD/apply.sql")
  { printf 'plan   %s %s\n' "$h1" "$([ "$h1" = "$BASE_PLAN" ] && echo match || echo DIFFERS)"
    printf 'apply  %s %s\n' "$h2" "$([ "$h2" = "$BASE_APPLY" ] && echo match || echo DIFFERS)"
    printf 'plan   lines=%s bytes=%s\n' "$(grep -c '' "$SQLD/plan.sql")" "$(wc -c < "$SQLD/plan.sql" | tr -d ' ')"
    printf 'apply  lines=%s bytes=%s\n' "$(grep -c '' "$SQLD/apply.sql")" "$(wc -c < "$SQLD/apply.sql" | tr -d ' ')"
  } > "$OUT/hashes.txt"
  # The shared pipeline: "WITH params AS (" through the end of the staged CTE.
  # The page says this region is byte-identical in both texts; this is the
  # check that makes the claim auditable.
  sed -n '/^WITH params AS ($/,/^      FROM decided d$/p' "$SQLD/plan.sql"  > "$OUT/pipeline_plan.sql"
  sed -n '/^WITH params AS ($/,/^      FROM decided d$/p' "$SQLD/apply.sql" > "$OUT/pipeline_apply.sql"
  { printf 'pipeline plan  %s\n' "$(sha "$OUT/pipeline_plan.sql")"
    printf 'pipeline apply %s\n' "$(sha "$OUT/pipeline_apply.sql")"
    printf 'pipeline lines %s\n' "$(grep -c '' "$OUT/pipeline_plan.sql")"
    if [ -s "$OUT/pipeline_plan.sql" ] && cmp -s "$OUT/pipeline_plan.sql" "$OUT/pipeline_apply.sql"; then
      printf 'pipeline identical yes\n'
    else
      printf 'pipeline identical NO\n'
    fi
  } >> "$OUT/hashes.txt"
  plan_view "$SQLD/plan.sql" > "$SQLD/plan_view.sql"
  cat "$OUT/hashes.txt"
  ! grep -Eq 'DIFFERS|identical NO' "$OUT/hashes.txt" \
    || die "the page's texts are not the ones this script was last measured with: re-measure, then refile BASE_PLAN and BASE_APPLY"
}

# run_plan <db> <tag> [prefix-sql]: step 1, verbatim; run_apply the same for
# step 2.  The optional prefix runs first in the same session (SET ROLE).
# Both return psql's exit status, which every caller checks.
run_plan() {
  { [ -n "${3:-}" ] && printf '%s\n' "$3"; cat "$SQLD/plan.sql"; } \
    | "$BIN/psql" -X -v ON_ERROR_STOP=1 -P pager=off -h "$SOCK" -p "$PORT" -d "$1" \
      > "$OUT/plan-$2.txt" 2>&1
}
run_apply() {
  { [ -n "${3:-}" ] && printf '%s\n' "$3"; cat "${APPLY_FILE:-$SQLD/apply.sql}"; } \
    | "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1" \
      > "$OUT/apply-$2.log" 2>&1
}
apply_summary() { grep -Eo 'nbmaint: reindex=.*' "$OUT/apply-$1.log" | tail -1; }
plan_actions()  {
  grep -Eo '\| (initialize|refresh|reindex|skip|blocked|conflict) ' "$OUT/plan-$1.txt" \
    | sort | uniq -c | tr -s ' ' | tr '\n' ';'
}

# ---------------------------------------------------------------- exact ------
# Both filed texts, executed unmodified on this server before any fixture
# exists: the compatibility claim in its smallest form.  Any text that fails,
# or a second step 2 run that writes anything, fails the stage.
stage_exact() {
  say "exact: both filed texts, unmodified, on a database with no fixture in it"
  : > "$OUT/exact.txt"
  q "$XDB" 'DROP TABLE IF EXISTS zz_exact CASCADE' > /dev/null
  qz "$XDB" > "$OUT/exact-build.log" 2>&1 <<'SQL'
CREATE /* wiki_nbmaint_exact */ TABLE zz_exact AS
  SELECT i::bigint AS k, int8range(i, i + 10) AS r FROM generate_series(1, 200000) i;
ANALYZE /* wiki_nbmaint_exact */ zz_exact;
CREATE /* wiki_nbmaint_exact */ INDEX zz_exact_h ON zz_exact USING hash (k);
CREATE /* wiki_nbmaint_exact */ INDEX zz_exact_g ON zz_exact USING gist (r);
CREATE /* wiki_nbmaint_exact */ INDEX zz_exact_b ON zz_exact (k);
COMMENT /* wiki_nbmaint_exact */ ON INDEX zz_exact_h IS 'a human note that must survive';
SQL
  local rc bad=""
  run_plan "$XDB" exact1; rc=$?; [ "$rc" = 0 ] || bad="$bad step-1-first"
  printf 'step 1, first run: exit=%s, rows naming zz_exact=%s, actions: %s\n' "$rc" \
    "$(grep -c 'zz_exact_' "$OUT/plan-exact1.txt")" "$(plan_actions exact1)" >> "$OUT/exact.txt"
  run_apply "$XDB" exact1; rc=$?; [ "$rc" = 0 ] || bad="$bad step-2-first"
  printf 'step 2, first run:  exit=%s, %s\n' "$rc" "$(apply_summary exact1)" >> "$OUT/exact.txt"
  q "$XDB" "SELECT /* wiki_nbmaint_exact */ c.relname || ': ' || replace(d.description, chr(10), ' | ')
              FROM pg_description d JOIN pg_class c ON c.oid = d.objoid
             WHERE d.classoid = 'pg_class'::regclass AND c.relname LIKE 'zz_exact_%'
             ORDER BY 1" >> "$OUT/exact.txt"
  run_apply "$XDB" exact2; rc=$?; [ "$rc" = 0 ] || bad="$bad step-2-second"
  printf 'step 2, second run: exit=%s, %s\n' "$rc" "$(apply_summary exact2)" >> "$OUT/exact.txt"
  apply_summary exact2 | grep -q 'reindex=0 initialize=0 refresh=0 ' || bad="$bad second-run-wrote"
  run_plan "$XDB" exact2; rc=$?; [ "$rc" = 0 ] || bad="$bad step-1-after"
  printf 'step 1, after both: exit=%s, actions: %s\n' "$rc" "$(plan_actions exact2)" >> "$OUT/exact.txt"
  q "$XDB" 'DROP TABLE IF EXISTS zz_exact CASCADE' > /dev/null
  cat "$OUT/exact.txt"
  [ -z "$bad" ] || die "exact:$bad (see $OUT/exact.txt and $OUT/plan-exact*.txt, $OUT/apply-exact*.log)"
}

# ---------------------------------------------------------------- facts ------
# Every version-local fact the two texts and this harness depend on,
# discovered on the running server rather than assumed.
stage_facts() {
  say "facts: what this server does, discovered rather than assumed"
  : > "$OUT/facts.txt"
  fact() { printf '%-40s %s\n' "$1" "$2" >> "$OUT/facts.txt"; }
  fact server_version_num "$(q "$XDB" 'SHOW server_version_num')"
  fact materialized_cte \
    "$(errf "$XDB" 'WITH x AS MATERIALIZED (SELECT 1) SELECT count(*) FROM x;')"
  fact pg_input_is_valid_rows \
    "$(q "$XDB" "SELECT count(*) FROM pg_proc WHERE proname = 'pg_input_is_valid'")"
  fact regexp_match_rows \
    "$(q "$XDB" "SELECT count(*) FROM pg_proc WHERE proname = 'regexp_match'")"
  fact pg_stat_force_next_flush_rows \
    "$(q "$XDB" "SELECT count(*) FROM pg_proc WHERE proname = 'pg_stat_force_next_flush'")"
  fact transaction_timeout_rows \
    "$(q "$XDB" "SELECT count(*) FROM pg_settings WHERE name = 'transaction_timeout'")"
  fact minmax_multi_opclass_rows \
    "$(q "$XDB" "SELECT count(*) FROM pg_opclass WHERE opcname = 'int8_minmax_multi_ops'")"
  fact gist_point_ops_support_11 \
    "$(q "$XDB" "SELECT count(*) FROM pg_opclass opc JOIN pg_amproc ap
                   ON ap.amprocfamily = opc.opcfamily AND ap.amprocnum = 11
                 WHERE opc.opcname = 'point_ops'
                   AND opc.opcmethod = (SELECT oid FROM pg_am WHERE amname = 'gist')")"
  fact pg_stat_progress_analyze \
    "$(q "$XDB" "SELECT coalesce(to_regclass('pg_stat_progress_analyze')::text, 'absent')")"
  fact n_ins_since_vacuum_column \
    "$(q "$XDB" "SELECT count(*) FROM pg_attribute
                  WHERE attrelid = 'pg_stat_all_tables'::regclass
                    AND attname = 'n_ins_since_vacuum'")"
  fact float4_to_numeric_1234567 "$(q "$XDB" 'SELECT 1234567::float4::numeric')"
  fact to_char_OF "$(q "$XDB" "SELECT to_char(now(), 'OF')")"
  fact commit_inside_do_top_level \
    "$(errf "$XDB" 'DO $x$ BEGIN PERFORM 1; COMMIT; END $x$;')"
  fact commit_inside_do_in_begin \
    "$(errf "$XDB" 'BEGIN; DO $x$ BEGIN PERFORM 1; COMMIT; END $x$; COMMIT;')"
  # step 2 narrows its pipeline with a transaction-local custom setting; what
  # step 1 then reads in the same session, and in a fresh one
  fact custom_setting_after_local_set \
    "$(printf '%s\n' 'BEGIN;' "SELECT set_config('nbmaint.only_index', '1', true);" 'COMMIT;' \
         "SELECT 'after commit: ' || coalesce(quote_literal(current_setting('nbmaint.only_index', true)), 'NULL');" \
       | PSQL -d "$XDB" -q -At 2>&1 | tail -1)"
  fact custom_setting_fresh_session \
    "$(q "$XDB" "SELECT coalesce(quote_literal(current_setting('nbmaint.only_index', true)), 'NULL')")"
  q "$XDB" 'DROP TABLE IF EXISTS zz_f CASCADE' > /dev/null
  q "$XDB" 'CREATE TABLE zz_f (k bigint)' > /dev/null
  q "$XDB" 'INSERT INTO zz_f SELECT g FROM generate_series(1, 1000) g' > /dev/null
  q "$XDB" 'CREATE INDEX zz_f_h ON zz_f USING hash (k)' > /dev/null
  fact reindex_inside_do \
    "$(errf "$XDB" 'DO $x$ BEGIN EXECUTE $q$REINDEX INDEX zz_f_h$q$; END $x$;')"
  fact reindex_concurrently_inside_do \
    "$(errf "$XDB" 'DO $x$ BEGIN EXECUTE $q$REINDEX INDEX CONCURRENTLY zz_f_h$q$; END $x$;')"
  fact reindex_concurrently_top_level "$(errf "$XDB" 'REINDEX INDEX CONCURRENTLY zz_f_h;')"
  fact comment_with_expression "$(errf "$XDB" "COMMENT ON INDEX zz_f_h IS 'a' || 'b';")"
  fact comment_with_literal "$(errf "$XDB" "COMMENT ON INDEX zz_f_h IS 'ab';")"
  # ALTER INDEX ... OWNER TO the owner it already has, which step 2 uses as its
  # index lock: the lock it holds, anything it prints, and whether it rewrote
  # the index's pg_class row
  local x0 x1
  x0=$(q "$XDB" "SELECT xmin FROM pg_class WHERE relname = 'zz_f_h'")
  fact alter_index_owner_to_owner \
    "$(printf '%s\n' 'BEGIN;' 'ALTER INDEX zz_f_h OWNER TO CURRENT_USER;' \
         "SELECT 'held: ' || string_agg(mode, ',' ORDER BY mode) FROM pg_locks WHERE relation = 'zz_f_h'::regclass AND pid = pg_backend_pid();" \
         'COMMIT;' | PSQL -d "$XDB" -q -At 2>&1 | tr '\n' ' ' | sed -e 's/ *$//')"
  x1=$(q "$XDB" "SELECT xmin FROM pg_class WHERE relname = 'zz_f_h'")
  fact alter_index_owner_rewrote_pg_class "$([ "$x0" = "$x1" ] && echo no || echo "yes ($x0 -> $x1)")"
  # A statement timeout inside a DO block's EXCEPTION WHEN OTHERS is not
  # caught: it ends the whole block.  That is what bounds step 2 as a whole.
  fact statement_timeout_vs_others \
    "$(errf "$XDB" "SET statement_timeout = '200ms'; DO \$x\$ BEGIN BEGIN PERFORM pg_sleep(2); EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'caught'; END; END \$x\$;")"
  q "$XDB" 'DROP TABLE IF EXISTS zz_p CASCADE' > /dev/null
  q "$XDB" 'CREATE TABLE zz_p (k bigint) PARTITION BY RANGE (k)' > /dev/null
  q "$XDB" 'CREATE TABLE zz_p1 PARTITION OF zz_p FOR VALUES FROM (0) TO (1000)' > /dev/null
  q "$XDB" 'CREATE INDEX zz_p_h ON zz_p USING hash (k)' > /dev/null
  fact partitioned_index_relkind "$(q "$XDB" "SELECT relkind FROM pg_class WHERE relname = 'zz_p_h'")"
  fact partitioned_index_size "$(q "$XDB" "SELECT pg_relation_size('zz_p_h')")"
  fact reindex_partitioned_index "$(errf "$XDB" 'REINDEX INDEX zz_p_h;')"
  q "$XDB" 'DROP TABLE IF EXISTS zz_p CASCADE' > /dev/null
  q "$XDB" 'DROP TABLE IF EXISTS zz_f CASCADE' > /dev/null
  cat "$OUT/facts.txt"
}
# ---------------------------------------------------------------- declare ----
# Files the declared kind of every published column, the method's own
# thresholds, the pay-off threshold every decision is scored at, the
# per-fixture predictions, the invariants, the declared exceptions of the
# no-defeat rule and the coverage plan - all BEFORE any fixture exists.  Both
# protocols forbid rewriting a declaration after the run, so this stage refuses
# once the fixture database is there.
stage_declare() {
  say "declare: kinds, thresholds, predictions, invariants, exceptions, coverage"
  if q postgres "SELECT count(*) FROM pg_database WHERE datname = '$DB'" | grep -q '^1$'; then
    die "refusing to re-file declarations: database $DB already exists (run reset first)"
  fi
  q postgres "DROP /* wiki_nbmaint_declare */ DATABASE IF EXISTS $PDB" > /dev/null
  q postgres "CREATE /* wiki_nbmaint_declare */ DATABASE $PDB" > /dev/null
  qin "$PDB" > "$OUT/declare.log" 2>&1 <<'SQL' || die "declare failed"
-- DISPOSABLE bookkeeping objects.
CREATE /* wiki_nbmaint_declare */ TABLE declared_kind (
  column_name text PRIMARY KEY,
  declared_kind text NOT NULL CHECK (declared_kind IN ('lower bound','upper bound','level')),
  claim text NOT NULL,
  filed_at timestamptz NOT NULL DEFAULT now());
INSERT /* wiki_nbmaint_declare */ INTO declared_kind (column_name, declared_kind, claim) VALUES
 ('index_size',      'level', 'the index file now, pg_relation_size; no claim against the oracle'),
 ('baseline_size',   'level', 'the stored baseline size itself'),
 ('size_ratio',      'level', 'current size over stored size; the input to the size test, not an estimate of reclaimable bytes'),
 ('table_tuples',    'level', 'the table''s pg_class.reltuples now'),
 ('baseline_tuples', 'level', 'the stored table tuple count itself'),
 ('tuple_ratio',     'level', 'current over stored table tuple count; the input to the tuple test');

CREATE /* wiki_nbmaint_declare */ TABLE declared_decision (
  knob text PRIMARY KEY, value text NOT NULL, meaning text NOT NULL,
  filed_at timestamptz NOT NULL DEFAULT now());
INSERT /* wiki_nbmaint_declare */ INTO declared_decision (knob, value, meaning) VALUES
 ('reindex when', 'size_ratio >= 1.30, or |table tuples - stored| >= 0.30 * stored',
                  'the method flags a rebuild: the brief''s two tests, either one'),
 ('refresh when', 'index smaller than its stored size',
                  'not a decision to rebuild; the baseline is rewritten'),
 ('pay-off',      'truth_pct >= 23.08',
                  'a rebuild was worth it: 100 * (1 - 1/1.30), the reclaim a 30 % growth implies, rounded to 23.08; compared with the unrounded 100 * (1 - R / C), never with its two-decimal display'),
 ('score',        'PASS, FALSE POSITIVE, FALSE NEGATIVE',
                  'reindex and truth_pct >= pay-off, or neither: PASS; reindex below it: FALSE POSITIVE; no reindex at or above it: FALSE NEGATIVE'),
 ('cross-checks', 'a VERBOSE count and a BRIN free-space reading are compared with the censuses taken just before and just after the VACUUM that produced them',
                  'see invariants I9 and I18');

-- Predictions filed before the run, from the B, C and R figures the source
-- page filed on 17.11 on 2026-09-16.  A miss is reported, not corrected.
CREATE /* wiki_nbmaint_declare */ TABLE declared_prediction (
  fixture text PRIMARY KEY, action text NOT NULL, score text NOT NULL, why text NOT NULL,
  filed_at timestamptz NOT NULL DEFAULT now());
INSERT /* wiki_nbmaint_declare */ INTO declared_prediction (fixture, action, score, why) VALUES
 ('h00','skip',   'PASS',           'no churn'),
 ('h01','reindex','PASS',           'size 2.35x, reclaim 37.7 %'),
 ('h02','reindex','PASS',           'size 5.06x, reclaim 80.3 %'),
 ('h03','reindex','PASS',           'size 1.60x, reclaim 37.6 %'),
 ('h04','reindex','FALSE POSITIVE', 'insert-only growth: size 1.37x and tuples 1.40x, reclaim 9.1 %'),
 ('h05','skip',   'PASS',           'size 1.12x, tuples 1.12x, reclaim 11.1 %'),
 ('h07','skip',   'PASS',           'empty'),
 ('h08','skip',   'PASS',           '1 % update, nothing to reclaim'),
 ('h12','skip',   'PASS',           'partial index: size 1.13x, table count unchanged, reclaim 0 %'),
 ('g06','reindex','PASS',           'size 4.86x, reclaim 79.4 %'),
 ('g07','reindex','PASS',           'size 3.71x, reclaim 73.0 %'),
 ('g08','reindex','PASS',           'tuples 0.20x, reclaim 80.0 %'),
 ('g09','reindex','PASS',           'size 10.0x, reclaim 84.4 %'),
 ('s08','reindex','PASS',           'size 7.27x, reclaim 85.7 %'),
 ('s09','reindex','PASS',           'size 3.97x, reclaim 74.8 %'),
 ('s10','reindex','PASS',           'size 1.35x, reclaim 44.0 %'),
 ('b10','reindex','FALSE POSITIVE', 'BRIN grows with the heap: size 1.33x, reclaim 0 %'),
 ('b11','reindex','FALSE POSITIVE', 'BRIN grows with the heap: size 2.33x, reclaim 0 %'),
 ('b12','reindex','FALSE POSITIVE', 'BRIN grows with the heap: size 1.75x, reclaim 0 %'),
 ('b13','reindex','FALSE POSITIVE', 'appended rows: tuples 1.50x, reclaim 0 %'),
 ('n03','skip',   'PASS',           'size 1.18x, tuples 1.00x, reclaim 14.9 %'),
 ('n04','reindex','PASS',           'size 7.52x, reclaim 84.9 %'),
 ('n05','reindex','FALSE POSITIVE', 'pending-list inserts: size 1.97x and tuples 1.50x, reclaim 21.5 %'),
 ('n06','reindex','PASS',           'size 2.86x, reclaim 67.7 %'),
 ('n07','reindex','PASS',           'size 4.37x, reclaim 73.9 %'),
 ('n08','skip',   'PASS',           'no churn'),
 ('n09','skip',   'PASS',           'empty'),
 ('n10','reindex','PASS',           'tuples 0.20x, reclaim 78.9 %'),
 ('n12','reindex','FALSE POSITIVE', 'size 1.31x, reclaim 11.5 %');

CREATE /* wiki_nbmaint_declare */ TABLE declared_invariant (
  id text PRIMARY KEY, claim text NOT NULL, filed_at timestamptz NOT NULL DEFAULT now());
INSERT /* wiki_nbmaint_declare */ INTO declared_invariant (id, claim) VALUES
 ('I1',  'no fixture index is smaller after its churn and maintenance than as built: none of the five AMs truncates'),
 ('I2',  'size bracket: pg_relation_size(index, main) re-read after each census equals block_size times the blocks the census scanned'),
 ('I3',  'hash: the census page classes and pgstathashindex both account for every block of the file'),
 ('I4',  'hash: every block hash_bitmap_info reports free reads back as an unused page'),
 ('I5',  'GiST: the FSM free-page count never exceeds the census deleted-plus-new count; SP-GiST: it never exceeds the new or empty pages outside the metapage and the two root pages, read from page headers'),
 ('I6',  'BRIN: the revmap entry count equals the summary tuples the regular pages hold'),
 ('I7',  'BRIN: the index is never smaller after the maintenance step than before it'),
 ('I8',  'GIN: on every census whose metapage counts the build or a VACUUM wrote last, the metapage entry, data and total page counts equal the census, a not-yet-recyclable deleted page counted as data; a census taken after writes and before a VACUUM reads counts stale by construction and is reported, not scored'),
 ('I9',  'the VACUUM VERBOSE index line appears exactly where index cleanup ran and returned statistics (not for the ANALYZE-only stand-ins, not for a hash index whose bulk delete never ran), and each of its counts equals the census: pages in total = the census just after that VACUUM, except on BRIN, which counts before it summarizes, = the census just before; hash and BRIN: 0 newly deleted, 0 currently deleted, 0 reusable; GiST: currently deleted = deleted-flag plus all-zero pages after, reusable = FSM free pages after, newly deleted = deleted-flag pages after minus before; SP-GiST: newly deleted = currently deleted = reusable = the new or empty pages outside the metapage and the two roots after, = FSM free pages after; GIN: reusable = FSM free pages after'),
 ('I10', 'the maintenance was not defeated: every maintenance VACUUM reports 0 tuples dead but not yet removable, except a declared held snapshot, which must pin something and whose second VACUUM reports 0'),
 ('I11', 'every VACUUM and ANALYZE session ran with all four settable timeouts at 0, and no maintenance log carries a skip line, an error or a cancellation'),
 ('I12', 'the measurement lock was never held across a maintenance step'),
 ('I13', 'no horizon holder but a declared snapshot: 0 prepared transactions, 0 replication slots, 0 other backends with a transaction id or an xmin'),
 ('I14', 'step 2''s first run stored a version-2 payload in every fixture index, with sz equal to the baseline census size and tup equal to the table count it read'),
 ('I15', 'the method decided on the maintained state: the size step 1 saw equals the maintained census size and the oracle''s before-size'),
 ('I16', 'step 1''s action equals the same two tests recomputed independently from the stored payload and the decide-time readings'),
 ('I17', 'step 2 carried out exactly the plan step 1 printed on the same state, and a second run of step 2 wrote nothing'),
 ('I18', 'BRIN, per regular page, on every census taken just after a VACUUM: every page that VACUUM did not write - its LSN no newer than the WAL insert position read just before the VACUUM began - reads in pg_freespace exactly the FSM category floor of its own free space, pd_upper minus pd_lower less one line pointer, or 0 on a page flagged BRIN_EVACUATE_PAGE; the pages the VACUUM''s own summarization wrote are compared and reported, not scored, because BRIN writes such a page''s FSM entry only when the page is extended or a search finds it short of space');

CREATE /* wiki_nbmaint_declare */ TABLE declared_exception (
  id text PRIMARY KEY, fixture text NOT NULL, state text NOT NULL,
  reading_rule text NOT NULL, filed_at timestamptz NOT NULL DEFAULT now());
INSERT /* wiki_nbmaint_declare */ INTO declared_exception (id, fixture, state, reading_rule) VALUES
 ('X1', 'g08', 'a REPEATABLE READ snapshot opened in a second session before the churn commits and held across the maintenance VACUUM',
         'the reading under it is held-horizon; the method is scored on the settle2 state, after the release and a second VACUUM ANALYZE'),
 ('X2', 'n10', 'the same snapshot, held across the settling VACUUM of a GIN fixture',
         'the same rule as X1'),
 ('X3', 'all', 'the SHARE ROW EXCLUSIVE measurement lock, which excludes VACUUM and ANALYZE by design',
         'taken per census and for the decide phase in their own transactions, never across a maintenance step');

CREATE /* wiki_nbmaint_declare */ TABLE declared_coverage (
  protocol text NOT NULL, behavior text NOT NULL, fixture text NOT NULL,
  filed_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (protocol, behavior));
INSERT /* wiki_nbmaint_declare */ INTO declared_coverage (protocol, behavior, fixture) VALUES
 ('non-btree','hash: an overflow chain, and a freed overflow page whose bitmap bit was cleared','h01'),
 ('non-btree','hash: a splitpoint allocation','h02'),
 ('non-btree','hash: an index whose hashbulkdelete never ran','h04'),
 ('non-btree','GiST: an emptied leaf that was deleted, and one that survived as its parent''s last downlink','g07'),
 ('non-btree','GiST: a deleted-but-not-recyclable page under a held snapshot','not reached: no fixture deletes a GiST page while a snapshot is held; g08''s snapshot makes its maintenance VACUUM delete nothing, and its second VACUUM deletes pages only after the release'),
 ('non-btree','GiST: a sorted build beside a non-sorted one','g09 (point_ops) beside g06 to g08 (range_ops)'),
 ('non-btree','SP-GiST: redirects turned into placeholders, a trailing run removed, an interior one retained','s09, read from VACUUM''s counters: no SP-GiST decoder'),
 ('non-btree','SP-GiST: an emptied non-root page and the root page','s09, the same limit'),
 ('non-btree','BRIN: an unsummarized range measured before the maintenance step, and the same index after it','b13'),
 ('non-btree','BRIN: a desummarized range, and a range summarized by the stand-in','b13'),
 ('non-btree','BRIN: a same-page summary update beside one that moved to another page','b10 and b11'),
 ('non-btree','BRIN: more than one pages_per_range','b12 at 32 beside b10 at 128'),
 ('non-btree','all: the maintenance pair','every churned fixture: churn_raw beside churn_maintained'),
 ('non-btree','all: an index maintained by the auto-analyze stand-in, a plain ANALYZE','h05'),
 ('non-btree','all: a table the census analyzed, and one it declined','tc_past and tc_exact'),
 ('non-btree','all: an empty index and an untouched index','h07 and h00'),
 ('non-btree','all: a non-default fillfactor, or for BRIN a non-default pages_per_range','h03, s10 and b12'),
 ('non-btree','a non-core access method under the four-part admission rule','skipped: no bloom fixture is in the ported corpus'),
 ('gin','keys that no longer occur after churn','n04'),
 ('gin','emptied posting-tree pages','n03 and n10'),
 ('gin','half-empty posting-tree leaves with nothing deletable','n04'),
 ('gin','a populated pending list, and the same index after a flush','n05'),
 ('gin','an untouched index and an empty index','n08 and n09'),
 ('gin','a snapshot held across the settling VACUUM','n10: its maintenance VACUUM runs under the snapshot and deletes no page; its posting-tree pages are deleted by the second VACUUM, after the release'),
 ('gin','more than one operator class','n06 (jsonb_path_ops) and n07 (tsvector_ops) beside array_ops'),
 ('gin','one rebuild at more than one maintenance_work_mem','probe P3'),
 ('gin','a churned index whose maintenance step ran, beside the same churn before it','every churned GIN fixture'),
 ('gin','an index maintained by the auto-analyze stand-in, ANALYZE plus gin_clean_pending_list','n12'),
 ('gin','a table the census analyzed, and one it declined to analyze','tc_past and tc_exact'),
 ('gin','an undecodable or unclassifiable page, and an all-zero page','skipped: the method reads no index page'),
 ('gin','a concurrent VACUUM, a concurrent rebuild and a writer stream','skipped: every measurement is single-session under the measurement lock');
SQL
  { q "$PDB" "SELECT column_name || ' -> ' || declared_kind FROM declared_kind ORDER BY 1"
    q "$PDB" "SELECT knob || ': ' || value FROM declared_decision ORDER BY 1"
    q "$PDB" "SELECT fixture || ' ' || action || ' ' || score FROM declared_prediction ORDER BY 1"
    q "$PDB" "SELECT id || ': ' || claim FROM declared_invariant ORDER BY substring(id from 2)::int"
    q "$PDB" "SELECT id || ' ' || fixture || ': ' || state FROM declared_exception ORDER BY 1"
    q "$PDB" "SELECT protocol || ' | ' || behavior || ' -> ' || fixture FROM declared_coverage ORDER BY protocol, behavior"
    q "$PDB" "SELECT 'declarations filed at ' || to_char(min(filed_at) AT TIME ZONE 'UTC',
                     'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') FROM declared_kind"
  } > "$OUT/declared.txt"
  tail -1 "$OUT/declared.txt"
}

# ------------------------------------------------------- the census machinery
proto_ddl() {
  cat <<'SQL'
CREATE /* wiki_nbmaint_proto */ SCHEMA proto;
CREATE /* wiki_nbmaint_proto */ EXTENSION pageinspect;
CREATE /* wiki_nbmaint_proto */ EXTENSION pgstattuple;
CREATE /* wiki_nbmaint_proto */ EXTENSION pg_freespacemap;

-- One row per fixture, phase and metric: a stage that runs again replaces its
-- own rows, and anything that would record a second reading of the same
-- thing fails instead of doubling a score.
CREATE TABLE proto.meas (
  fixture text NOT NULL, phase text NOT NULL, metric text NOT NULL,
  num numeric, txt text, at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (fixture, phase, metric));

-- The stages that have changed the fixture database, in the order they ran.
CREATE TABLE proto.stage_log (
  stage text PRIMARY KEY, done_at timestamptz NOT NULL DEFAULT clock_timestamp());

-- The graduated FSM agreement on BRIN, page by page: the page's own free
-- space, the value its FSM category floor must read, and what pg_freespace
-- did read.
CREATE TABLE proto.brin_page (
  fixture text NOT NULL, phase text NOT NULL, blkno int NOT NULL,
  free_bytes int NOT NULL, fsm_expected int NOT NULL, fsm_read int, page_lsn numeric NOT NULL,
  evacuate boolean NOT NULL, PRIMARY KEY (fixture, phase, blkno));

CREATE FUNCTION proto.note(p_fix text, p_phase text, p_metric text,
                           p_num numeric DEFAULT NULL, p_txt text DEFAULT NULL)
RETURNS void LANGUAGE sql AS $fn$
  INSERT INTO proto.meas(fixture, phase, metric, num, txt)
  VALUES (p_fix, p_phase, p_metric, p_num, p_txt);
$fn$;

-- Every non-B-tree index in public: its file, its table's count and its
-- comment, with the payload decoded - independently of the texts, as JSON,
-- out of the comment's one reserved line.  The payloads read here were
-- written by step 2, so the jsonb cast is safe; a cast that raised would stop
-- the run.  One row per phase and index.
CREATE TABLE proto.snap (
  phase text NOT NULL, idx text NOT NULL, oid oid, filenode oid, bytes bigint,
  tbl_tuples numeric, cmt text, pv numeric, sz numeric, tup numeric,
  at timestamptz NOT NULL DEFAULT clock_timestamp(), UNIQUE (phase, idx));
CREATE FUNCTION proto.take_snap(p_phase text) RETURNS void LANGUAGE sql AS $fn$
  INSERT INTO proto.snap(phase, idx, oid, filenode, bytes, tbl_tuples, cmt, pv, sz, tup)
  SELECT p_phase, c.relname, c.oid, c.relfilenode, pg_relation_size(c.oid),
         t.reltuples::numeric, d.description,
         (substring(d.description from '(?n)^@nbmaint:(\{.*\})$')::jsonb ->> 'v')::numeric,
         (substring(d.description from '(?n)^@nbmaint:(\{.*\})$')::jsonb ->> 'sz')::numeric,
         (substring(d.description from '(?n)^@nbmaint:(\{.*\})$')::jsonb ->> 'tup')::numeric
    FROM pg_class c
    JOIN pg_index x ON x.indexrelid = c.oid
    JOIN pg_class t ON t.oid = x.indrelid
    JOIN pg_am a    ON a.oid = c.relam
    LEFT JOIN pg_description d ON d.objoid = c.oid
                             AND d.classoid = 'pg_class'::regclass AND d.objsubid = 0
   WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'i'
     AND a.amname <> 'btree';
$fn$;

-- One census per access method, because the pinned tree offers a different
-- reader for each and refuses two of them outright.  Every per-block decode
-- runs in its own exception block, so a page the shipped reader will not
-- classify is counted as unreadable instead of failing the census.
CREATE FUNCTION proto.census_hash(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  n int; nblocks int; t text;
  c_meta int := 0; c_bucket int := 0; c_ovfl int := 0; c_bitmap int := 0;
  c_unused int := 0; c_bad int := 0;
  fb int := 0; fb_agree int := 0; fb_dis int := 0; st record; hs record;
  pgst_free numeric; pgst_err text;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass, 'main') / blk;
  FOR n IN 0 .. nblocks - 1 LOOP
    BEGIN
      t := hash_page_type(get_raw_page(p_idx, n));
    EXCEPTION WHEN OTHERS THEN
      t := 'unreadable';
    END;
    CASE t
      WHEN 'metapage' THEN c_meta := c_meta + 1;
      WHEN 'bucket'   THEN c_bucket := c_bucket + 1;
      WHEN 'overflow' THEN c_ovfl := c_ovfl + 1;
      WHEN 'bitmap'   THEN c_bitmap := c_bitmap + 1;
      WHEN 'unused'   THEN c_unused := c_unused + 1;
      ELSE c_bad := c_bad + 1;
    END CASE;
    -- I4: a block the bitmap calls free must read back as an unused page.
    -- The reader refuses a metapage or a bitmap block by design, so those are
    -- excluded rather than counted as disagreements.
    BEGIN
      SELECT * INTO hs FROM hash_bitmap_info(p_idx::regclass, n);
      IF NOT hs.bitstatus THEN
        fb := fb + 1;
        IF t = 'unused' OR t = 'unreadable' THEN fb_agree := fb_agree + 1;
        ELSE fb_dis := fb_dis + 1; END IF;
      END IF;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;
  END LOOP;
  SELECT * INTO hs FROM pgstathashindex(p_idx::regclass);
  -- pgstattuple's hash reader is refused by an all-zero page on a server
  -- without commit 036decbba2, so a refusal is recorded, not fatal
  BEGIN
    SELECT * INTO st FROM pgstattuple(p_idx::regclass);
    pgst_free := st.free_percent;
  EXCEPTION WHEN OTHERS THEN
    pgst_err := SQLERRM;
  END;
  IF pgst_err IS NOT NULL THEN
    INSERT INTO proto.meas(fixture, phase, metric, txt) VALUES (p_fix, p_phase, 'pgst_refusal', pgst_err);
  END IF;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
   (p_fix, p_phase, 'census_scanned',    nblocks),
   (p_fix, p_phase, 'census_meta',       c_meta),
   (p_fix, p_phase, 'census_bucket',     c_bucket),
   (p_fix, p_phase, 'census_overflow',   c_ovfl),
   (p_fix, p_phase, 'census_bitmap',     c_bitmap),
   (p_fix, p_phase, 'census_unused',     c_unused),
   (p_fix, p_phase, 'census_unreadable', c_bad),
   (p_fix, p_phase, 'bitmap_free',       fb),
   (p_fix, p_phase, 'bitmap_agree',      fb_agree),
   (p_fix, p_phase, 'bitmap_disagree',   fb_dis),
   (p_fix, p_phase, 'hs_bucket_pages',   hs.bucket_pages),
   (p_fix, p_phase, 'hs_overflow_pages', hs.overflow_pages),
   (p_fix, p_phase, 'hs_bitmap_pages',   hs.bitmap_pages),
   (p_fix, p_phase, 'hs_unused_pages',   hs.unused_pages),
   (p_fix, p_phase, 'hs_live_items',     hs.live_items),
   (p_fix, p_phase, 'hs_dead_items',     hs.dead_items),
   (p_fix, p_phase, 'pgst_free_percent', pgst_free),
   (p_fix, p_phase, 'size_after_census', pg_relation_size(p_idx::regclass, 'main'));
END $fn$;

CREATE FUNCTION proto.census_gist(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  n int; nblocks int; fl text[]; hdr record;
  c_leaf int := 0; c_inner int := 0; c_del int := 0; c_zero int := 0; c_bad int := 0;
  fsm_free int;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass, 'main') / blk;
  FOR n IN 0 .. nblocks - 1 LOOP
    BEGIN
      SELECT * INTO hdr FROM page_header(get_raw_page(p_idx, n));
      IF hdr.lower = 0 AND hdr.upper = 0 THEN
        c_zero := c_zero + 1;
        CONTINUE;
      END IF;
      SELECT flags INTO fl FROM gist_page_opaque_info(get_raw_page(p_idx, n));
      IF fl @> ARRAY['deleted'] THEN c_del := c_del + 1;
      ELSIF fl @> ARRAY['leaf'] THEN c_leaf := c_leaf + 1;
      ELSE c_inner := c_inner + 1;
      END IF;
    EXCEPTION WHEN OTHERS THEN
      c_bad := c_bad + 1;
    END;
  END LOOP;
  SELECT count(*) INTO fsm_free FROM pg_freespace(p_idx::regclass) WHERE avail > 0;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
   (p_fix, p_phase, 'census_scanned',    nblocks),
   (p_fix, p_phase, 'census_leaf',       c_leaf),
   (p_fix, p_phase, 'census_inner',      c_inner),
   (p_fix, p_phase, 'census_deleted',    c_del),
   (p_fix, p_phase, 'census_new',        c_zero),
   (p_fix, p_phase, 'census_unreadable', c_bad),
   (p_fix, p_phase, 'fsm_free_pages',    fsm_free),
   (p_fix, p_phase, 'size_after_census', pg_relation_size(p_idx::regclass, 'main'));
END $fn$;

-- pageinspect ships no SP-GiST decoder, so this census is the page header and
-- nothing else, and every page-class quantity derived from it is a level.
-- A header does show the one class SP-GiST's VACUUM counts and frees: a page
-- that is new or holds no line pointer, outside the metapage (block 0) and
-- the two root pages (blocks 1 and 2), which VACUUM never frees.
CREATE FUNCTION proto.census_spgist(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  hdr_size int := 24;    -- SizeOfPageHeaderData: offsetof(PageHeaderData, pd_linp)
  n int; nblocks int; hdr record;
  c_used int := 0; c_zero int := 0; c_empty int := 0; c_bad int := 0; fsm_free int;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass, 'main') / blk;
  FOR n IN 0 .. nblocks - 1 LOOP
    BEGIN
      SELECT * INTO hdr FROM page_header(get_raw_page(p_idx, n));
      IF hdr.lower = 0 AND hdr.upper = 0 THEN c_zero := c_zero + 1;
      ELSE c_used := c_used + 1;
      END IF;
      -- PageIsNew or PageIsEmpty, on a block VACUUM is allowed to free
      IF n >= 3 AND hdr.lower <= hdr_size THEN c_empty := c_empty + 1; END IF;
    EXCEPTION WHEN OTHERS THEN c_bad := c_bad + 1;
    END;
  END LOOP;
  SELECT count(*) INTO fsm_free FROM pg_freespace(p_idx::regclass) WHERE avail > 0;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
   (p_fix, p_phase, 'census_scanned',      nblocks),
   (p_fix, p_phase, 'census_used',         c_used),
   (p_fix, p_phase, 'census_new',          c_zero),
   (p_fix, p_phase, 'census_new_or_empty', c_empty),
   (p_fix, p_phase, 'census_unreadable',   c_bad),
   (p_fix, p_phase, 'fsm_free_pages',      fsm_free),
   (p_fix, p_phase, 'size_after_census',   pg_relation_size(p_idx::regclass, 'main'));
END $fn$;

-- The BRIN census.  Beside the page classes and the summaries it runs the
-- graduated FSM agreement the non-B-tree protocol requires, page by page:
-- every regular page's pg_freespace against that page's own free space as
-- br_page_get_freespace computes it - pd_upper minus pd_lower less one line
-- pointer, or 0 on a page flagged BRIN_EVACUATE_PAGE - rounded down to its
-- FSM category, block_size / 256 bytes wide.  The flags and the page type are
-- read out of the raw page: BrinSpecialSpace holds MAXALIGN(1) / 2 uint16s,
-- the flags next to last and the type last, little endian on this platform,
-- and a regular page whose type does not read 0xF093 there is unreadable.
CREATE FUNCTION proto.census_brin(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  bsz int := current_setting('block_size')::int;
  step int := current_setting('block_size')::int / 256;
  ma int;
  n int; nblocks int; t text; k int; un int; raw bytea; hdr record;
  flags_w int; type_w int; free_b int; want int; got int;
  c_meta int := 0; c_revmap int := 0; c_reg int := 0; c_bad int := 0;
  items bigint := 0; unused bigint := 0; revmap_entries bigint := 0;
  fsm_free int; f_agree int := 0; f_high int := 0; f_low int := 0; f_evac int := 0;
BEGIN
  SELECT max_data_alignment INTO ma FROM pg_control_init();
  nblocks := pg_relation_size(p_idx::regclass, 'main') / bsz;
  FOR n IN 0 .. nblocks - 1 LOOP
    BEGIN
      raw := get_raw_page(p_idx, n);
      t := brin_page_type(raw);
    EXCEPTION WHEN OTHERS THEN
      t := 'unreadable';
    END;
    IF t = 'meta' THEN c_meta := c_meta + 1;
    ELSIF t = 'revmap' THEN
      c_revmap := c_revmap + 1;
      SELECT count(*) INTO k FROM brin_revmap_data(raw) r
       WHERE r.pages IS NOT NULL AND r.pages::text <> '(0,0)';
      revmap_entries := revmap_entries + k;
    ELSIF t = 'regular' THEN
      BEGIN
        -- one row per (item, attnum); an unused line pointer - what a moved
        -- summary or a desummarize leaves behind - comes back with blknum NULL
        SELECT count(DISTINCT bi.itemoffset) FILTER (WHERE bi.blknum IS NOT NULL),
               count(DISTINCT bi.itemoffset) FILTER (WHERE bi.blknum IS NULL)
          INTO k, un
          FROM brin_page_items(raw, p_idx::regclass) bi;
        SELECT * INTO hdr FROM page_header(raw);
        flags_w := get_byte(raw, hdr.special + ma - 4) + 256 * get_byte(raw, hdr.special + ma - 3);
        type_w  := get_byte(raw, hdr.special + ma - 2) + 256 * get_byte(raw, hdr.special + ma - 1);
        IF type_w <> 61587 THEN     -- BRIN_PAGETYPE_REGULAR, 0xF093
          RAISE EXCEPTION 'block % does not read as a regular BRIN page', n;
        END IF;
        c_reg := c_reg + 1;
        items := items + k;
        unused := unused + un;
        IF flags_w & 1 <> 0 THEN    -- BRIN_EVACUATE_PAGE
          free_b := 0; f_evac := f_evac + 1;
        ELSE
          free_b := greatest(hdr.upper - hdr.lower - 4, 0);   -- less one ItemIdData
        END IF;
        want := least(free_b / step, 254) * step;
        got := pg_freespace(p_idx::regclass, n);
        INSERT INTO proto.brin_page (fixture, phase, blkno, free_bytes, fsm_expected, page_lsn,
                                     fsm_read, evacuate)
             VALUES (p_fix, p_phase, n, free_b, want, hdr.lsn - '0/0'::pg_lsn, got, flags_w & 1 <> 0);
        IF got = want THEN f_agree := f_agree + 1;
        ELSIF got > want THEN f_high := f_high + 1;
        ELSE f_low := f_low + 1;
        END IF;
      EXCEPTION WHEN OTHERS THEN
        c_bad := c_bad + 1;
      END;
    ELSE c_bad := c_bad + 1;
    END IF;
  END LOOP;
  SELECT count(*) INTO fsm_free FROM pg_freespace(p_idx::regclass) WHERE avail > 0;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
   (p_fix, p_phase, 'census_scanned',      nblocks),
   (p_fix, p_phase, 'census_meta',         c_meta),
   (p_fix, p_phase, 'census_revmap',       c_revmap),
   (p_fix, p_phase, 'census_regular',      c_reg),
   (p_fix, p_phase, 'census_unreadable',   c_bad),
   (p_fix, p_phase, 'brin_items',          items),
   (p_fix, p_phase, 'brin_unused_items',   unused),
   (p_fix, p_phase, 'brin_revmap_entries', revmap_entries),
   (p_fix, p_phase, 'brin_fsm_agree',      f_agree),
   (p_fix, p_phase, 'brin_fsm_higher',     f_high),
   (p_fix, p_phase, 'brin_fsm_lower',      f_low),
   (p_fix, p_phase, 'brin_evacuate_pages', f_evac),
   (p_fix, p_phase, 'fsm_free_pages',      fsm_free),
   (p_fix, p_phase, 'size_after_census',   pg_relation_size(p_idx::regclass, 'main'));
END $fn$;

CREATE FUNCTION proto.census_gin(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  n int; nblocks int; fl text[]; hdr record; m record;
  c_entry int := 0; c_data int := 0; c_list int := 0; c_del int := 0;
  c_zero int := 0; c_bad int := 0; fsm_free int;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass, 'main') / blk;
  SELECT * INTO m FROM gin_metapage_info(get_raw_page(p_idx, 0));
  FOR n IN 1 .. nblocks - 1 LOOP
    BEGIN
      SELECT * INTO hdr FROM page_header(get_raw_page(p_idx, n));
      IF hdr.lower = 0 AND hdr.upper = 0 THEN
        c_zero := c_zero + 1;
        CONTINUE;
      END IF;
      SELECT flags INTO fl FROM gin_page_opaque_info(get_raw_page(p_idx, n));
      IF fl @> ARRAY['deleted'] THEN c_del := c_del + 1;
      ELSIF fl @> ARRAY['list'] THEN c_list := c_list + 1;
      ELSIF fl @> ARRAY['data'] THEN c_data := c_data + 1;
      ELSE c_entry := c_entry + 1;
      END IF;
    EXCEPTION WHEN OTHERS THEN c_bad := c_bad + 1;
    END;
  END LOOP;
  SELECT count(*) INTO fsm_free FROM pg_freespace(p_idx::regclass) WHERE avail > 0;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
   (p_fix, p_phase, 'census_scanned',     nblocks),
   (p_fix, p_phase, 'census_entry',       c_entry),
   (p_fix, p_phase, 'census_data',        c_data),
   (p_fix, p_phase, 'census_list',        c_list),
   (p_fix, p_phase, 'census_deleted',     c_del),
   (p_fix, p_phase, 'census_new',         c_zero),
   (p_fix, p_phase, 'census_unreadable',  c_bad),
   (p_fix, p_phase, 'meta_total_pages',   m.n_total_pages),
   (p_fix, p_phase, 'meta_entry_pages',   m.n_entry_pages),
   (p_fix, p_phase, 'meta_data_pages',    m.n_data_pages),
   (p_fix, p_phase, 'meta_pending_pages', m.n_pending_pages),
   (p_fix, p_phase, 'fsm_free_pages',     fsm_free),
   (p_fix, p_phase, 'size_after_census',  pg_relation_size(p_idx::regclass, 'main'));
END $fn$;

CREATE FUNCTION proto.census(p_fix text, p_phase text, p_tab text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE am text;
BEGIN
  SELECT a.amname INTO am FROM pg_class c JOIN pg_am a ON a.oid = c.relam
   WHERE c.oid = p_idx::regclass;
  PERFORM proto.note(p_fix, p_phase, 'size_before_census',
                     pg_relation_size(p_idx::regclass, 'main'));
  CASE am
    WHEN 'hash'   THEN PERFORM proto.census_hash(p_fix, p_phase, p_idx);
    WHEN 'gist'   THEN PERFORM proto.census_gist(p_fix, p_phase, p_idx);
    WHEN 'spgist' THEN PERFORM proto.census_spgist(p_fix, p_phase, p_idx);
    WHEN 'brin'   THEN PERFORM proto.census_brin(p_fix, p_phase, p_idx);
    WHEN 'gin'    THEN PERFORM proto.census_gin(p_fix, p_phase, p_idx);
  END CASE;
END $fn$;

-- one reading of everything the method and the cross-checks can see
CREATE FUNCTION proto.record(p_fix text, p_phase text, p_tab text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE s record; ct record; ci record;
BEGIN
  SELECT reltuples, relpages INTO ct FROM pg_class WHERE oid = p_tab::regclass;
  SELECT reltuples, relpages, relfilenode INTO ci FROM pg_class WHERE oid = p_idx::regclass;
  SELECT n_tup_ins, n_tup_upd, n_tup_hot_upd, n_tup_del, n_live_tup, n_dead_tup,
         n_mod_since_analyze, analyze_count, vacuum_count
    INTO s FROM pg_stat_all_tables WHERE relid = p_tab::regclass;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
    (p_fix, p_phase, 'index_size',          pg_relation_size(p_idx::regclass, 'main')),
    (p_fix, p_phase, 'index_relpages',      ci.relpages),
    (p_fix, p_phase, 'index_reltuples',     ci.reltuples),
    (p_fix, p_phase, 'index_filenode',      ci.relfilenode::bigint),
    (p_fix, p_phase, 'table_size',          pg_relation_size(p_tab::regclass, 'main')),
    (p_fix, p_phase, 'table_relpages',      ct.relpages),
    (p_fix, p_phase, 'table_reltuples',     ct.reltuples),
    (p_fix, p_phase, 'n_tup_ins',           s.n_tup_ins),
    (p_fix, p_phase, 'n_tup_upd',           s.n_tup_upd),
    (p_fix, p_phase, 'n_tup_hot_upd',       s.n_tup_hot_upd),
    (p_fix, p_phase, 'n_tup_del',           s.n_tup_del),
    (p_fix, p_phase, 'n_live_tup',          s.n_live_tup),
    (p_fix, p_phase, 'n_dead_tup',          s.n_dead_tup),
    (p_fix, p_phase, 'n_mod_since_analyze', s.n_mod_since_analyze),
    (p_fix, p_phase, 'analyze_count',       s.analyze_count),
    (p_fix, p_phase, 'vacuum_count',        s.vacuum_count);
END $fn$;
SQL
}

# ---------------------------------------------------------- fixture recipes --
# The source page's 29 numbered fixtures, recipe for recipe.  Every
# statement is DISPOSABLE fixture DDL and DML.  The build phase is: create the
# table, load it, ANALYZE, create the scored index, ANALYZE again.
fx_build() {
  local f="$1" t i
  t=$(tbl "$f"); i=$(idx "$f")
  case "$f" in
    h00|h01|h02|h04|h05|h08)
      cat <<SQL
CREATE TABLE $t (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, g FROM generate_series(1,$BASE_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING hash (k);
ANALYZE $t;
SQL
      ;;
    h03)
      cat <<SQL
CREATE TABLE $t (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, g FROM generate_series(1,$BASE_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING hash (k) WITH (fillfactor = 50);
ANALYZE $t;
SQL
      ;;
    h07)
      cat <<SQL
CREATE TABLE $t (id bigint, k bigint) WITH (autovacuum_enabled = off);
ANALYZE $t;
CREATE INDEX $i ON $t USING hash (k);
ANALYZE $t;
SQL
      ;;
    h12)
      cat <<SQL
CREATE TABLE $t (id bigint, state text, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, CASE WHEN g % 10 = 0 THEN 'pending' ELSE 'done' END, g
  FROM generate_series(1,$BRIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING hash (k) WHERE state = 'pending';
ANALYZE $t;
SQL
      ;;
    g06|g07)
      cat <<SQL
CREATE TABLE $t (id bigint, r int8range) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, int8range(g, g+10) FROM generate_series(1,$BASE_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gist (r);
ANALYZE $t;
SQL
      ;;
    g08)
      cat <<SQL
CREATE TABLE $t (id bigint, r int8range) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, int8range(g, g+10) FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gist (r);
ANALYZE $t;
SQL
      ;;
    g09)
      # point_ops carries GIST_SORTSUPPORT_PROC on this server, so this is the
      # run's one sorted GiST build; g06 to g08 are insert-driven
      cat <<SQL
CREATE TABLE $t (id bigint, p point) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, point((g % 100000)::float8, (g / 100000)::float8)
  FROM generate_series(1,$BASE_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gist (p);
ANALYZE $t;
SQL
      ;;
    s08|s09)
      cat <<SQL
CREATE TABLE $t (id bigint, t text) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, 'aaa' || lpad(g::text, 12, '0') FROM generate_series(1,$BASE_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING spgist (t);
ANALYZE $t;
SQL
      ;;
    s10)
      cat <<SQL
CREATE TABLE $t (id bigint, t text) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, 'aaa' || lpad(g::text, 12, '0') FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING spgist (t) WITH (fillfactor = 50);
ANALYZE $t;
SQL
      ;;
    b10)
      cat <<SQL
CREATE TABLE $t (id bigint, v bigint) WITH (autovacuum_enabled = off, fillfactor = 90);
INSERT INTO $t SELECT g, g FROM generate_series(1,$BRIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING brin (v) WITH (pages_per_range = 128);
ANALYZE $t;
SQL
      ;;
    b11)
      cat <<SQL
CREATE TABLE $t (id bigint, v bigint) WITH (autovacuum_enabled = off, fillfactor = 90);
INSERT INTO $t SELECT g, g FROM generate_series(1,$BRIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING brin (v int8_minmax_multi_ops(values_per_range = 64))
  WITH (pages_per_range = 128);
ANALYZE $t;
SQL
      ;;
    b12)
      cat <<SQL
CREATE TABLE $t (id bigint, v bigint) WITH (autovacuum_enabled = off, fillfactor = 90);
INSERT INTO $t SELECT g, g FROM generate_series(1,$BRIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING brin (v) WITH (pages_per_range = 32);
ANALYZE $t;
SQL
      ;;
    b13)
      cat <<SQL
CREATE TABLE $t (id bigint, v bigint) WITH (autovacuum_enabled = off, fillfactor = 90);
INSERT INTO $t SELECT g, g FROM generate_series(1,$BRIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING brin (v) WITH (pages_per_range = 128, autosummarize = on);
ANALYZE $t;
SQL
      ;;
    n03|n04|n08)
      cat <<SQL
CREATE TABLE $t (id bigint, arr text[]) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, ARRAY['a'||g, 'b'||(g%50000), 'c'||(g%1000)]
  FROM generate_series(1,$GIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (arr) WITH (fastupdate = off);
ANALYZE $t;
SQL
      ;;
    n05|n12)
      cat <<SQL
CREATE TABLE $t (id bigint, arr text[]) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, ARRAY['a'||g, 'b'||(g%50000), 'c'||(g%1000)]
  FROM generate_series(1,$GIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (arr) WITH (fastupdate = on);
ANALYZE $t;
SQL
      ;;
    n06)
      cat <<SQL
CREATE TABLE $t (id bigint, j jsonb) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, jsonb_build_object('a', 'a'||g, 'b', 'b'||(g%50000), 'c', 'c'||(g%1000))
  FROM generate_series(1,$GIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (j jsonb_path_ops);
ANALYZE $t;
SQL
      ;;
    n07)
      cat <<SQL
CREATE TABLE $t (id bigint, d tsvector) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, to_tsvector('simple', 'a'||g||' b'||(g%50000)||' c'||(g%1000))
  FROM generate_series(1,$GIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (d);
ANALYZE $t;
SQL
      ;;
    n09)
      cat <<SQL
CREATE TABLE $t (id bigint, arr text[]) WITH (autovacuum_enabled = off);
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (arr) WITH (fastupdate = off);
ANALYZE $t;
SQL
      ;;
    n10)
      # three hot keys, so every key owns a posting tree; the churn deletes a
      # contiguous id band, so whole posting-tree leaves empty
      cat <<SQL
CREATE TABLE $t (id bigint, arr text[]) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, ARRAY['hot1','hot2','hot3']
  FROM generate_series(1,$HOT_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (arr) WITH (fastupdate = off);
ANALYZE $t;
SQL
      ;;
    *) die "no build recipe for fixture $f" ;;
  esac
}

# The recipe's own writes.  Nothing here maintains anything: the maintenance
# step is fx_maint, and it always runs before the decide phase.
fx_churn() {
  local f="$1" t r
  t=$(tbl "$f")
  case "$f" in
    h00|h07|n08|n09) : ;;   # no churn at all
    h01) printf 'UPDATE %s SET k = %s + (id %% 100);\n' "$t" "$BASE_ROWS" ;;
    h02) printf 'INSERT INTO %s SELECT g, g FROM generate_series(%s,%s) g;\nDELETE FROM %s WHERE id > %s;\n' \
           "$t" "$((BASE_ROWS+1))" "$((BASE_ROWS*5))" "$t" "$BASE_ROWS" ;;
    h03) printf 'UPDATE %s SET k = k + %s WHERE id %% 2 = 0;\n' "$t" "$BASE_ROWS" ;;
    h04) printf 'INSERT INTO %s SELECT g, g FROM generate_series(%s,%s) g;\n' \
           "$t" "$((BASE_ROWS+1))" "$((BASE_ROWS+BASE_ROWS*2/5))" ;;
    h05) printf 'INSERT INTO %s SELECT g, g FROM generate_series(%s,%s) g;\n' \
           "$t" "$((BASE_ROWS+1))" "$((BASE_ROWS+A05_INSERTS))" ;;
    h08) printf 'UPDATE %s SET k = k + %s WHERE id %% 100 = 0;\n' "$t" "$BASE_ROWS" ;;
    h12) printf "UPDATE %s SET state = 'pending' WHERE id %% 10 BETWEEN 1 AND 8;\n" "$t" ;;
    g06) for r in $(seq 1 "$ROUNDS"); do
           printf 'UPDATE %s SET r = int8range((id * 7 + %s * 1000003) %% 100000000,\n                                 (id * 7 + %s * 1000003) %% 100000000 + 10);\n' \
             "$t" "$r" "$r"
         done ;;
    g07) printf 'INSERT INTO %s SELECT g, int8range(g, g+10) FROM generate_series(%s,%s) g;\nDELETE FROM %s WHERE id > %s;\n' \
           "$t" "$((BASE_ROWS+1))" "$((BASE_ROWS*4))" "$t" "$BASE_ROWS" ;;
    # a contiguous id band, not a modulus: the keys correlate with id, so
    # deleting the top 80 % empties whole leaves instead of thinning every one
    g08) printf 'DELETE FROM %s WHERE id > %s;\n' "$t" "$((SMALL_ROWS/5))" ;;
    g09) for r in $(seq 1 "$ROUNDS"); do
           printf 'UPDATE %s SET p = point((((id * 7 + %s * 1000003) %% 100000))::float8,\n                            (((id * 13 + %s * 1000003) %% 10000))::float8);\n' \
             "$t" "$r" "$r"
         done ;;
    s08) for r in $(seq 1 "$ROUNDS"); do
           printf "UPDATE %s SET t = chr(98 + %s) || chr(112 + %s) || chr(103 + %s)\n       || lpad(((id * 7919 + %s * 104729) %% 1000000)::text, 12, '0');\n" \
             "$t" "$r" "$r" "$r" "$r"
         done ;;
    s09) printf "INSERT INTO %s SELECT g, 'zzz' || lpad(g::text, 12, '0') FROM generate_series(%s,%s) g;\nDELETE FROM %s WHERE id > %s;\n" \
           "$t" "$((BASE_ROWS+1))" "$((BASE_ROWS*4))" "$t" "$BASE_ROWS" ;;
    s10) printf "DELETE FROM %s WHERE id %% 10 < 3;\nUPDATE %s SET t = 'bbb' || lpad(((id * 7919) %% 1000000)::text, 12, '0') WHERE id %% 10 >= 7;\n" \
           "$t" "$t" ;;
    b10) for r in $(seq 1 "$ROUNDS"); do
           printf 'UPDATE %s SET v = (id * 7919 + %s * 104729) %% %s;\n' "$t" "$r" "$BRIN_ROWS"
         done ;;
    b11) printf 'UPDATE %s SET v = (id * 7919) %% %s;\nUPDATE %s SET v = (id * 104729) %% %s;\nUPDATE %s SET v = id;\n' \
           "$t" "$BRIN_ROWS" "$t" "$BRIN_ROWS" "$t" ;;
    b12) for r in $(seq 1 3); do
           printf 'UPDATE %s SET v = (id * 7919 + %s * 104729) %% %s;\n' "$t" "$r" "$BRIN_ROWS"
         done ;;
    b13) printf 'INSERT INTO %s SELECT g, g FROM generate_series(%s,%s) g;\n' \
           "$t" "$((BRIN_ROWS+1))" "$((BRIN_ROWS+BRIN_ROWS/2))" ;;
    n03) printf "INSERT INTO %s SELECT g, ARRAY['hot1','hot2','hot3'] FROM generate_series(%s,%s) g;\nDELETE FROM %s WHERE id > %s;\n" \
           "$t" "$((GIN_ROWS+1))" "$((GIN_ROWS*4))" "$t" "$GIN_ROWS" ;;
    n04) for r in $(seq 1 "$ROUNDS"); do
           printf "UPDATE %s SET arr = ARRAY['r%sk'||id, 'r%sm'||(id%%20000), 'r%sn'||(id%%500)];\n" \
             "$t" "$r" "$r" "$r"
         done ;;
    n05) printf "SET gin_pending_list_limit = '1GB';\nINSERT INTO %s SELECT g, ARRAY['a'||g, 'b'||(g%%50000), 'c'||(g%%1000)]\n  FROM generate_series(%s,%s) g;\nRESET gin_pending_list_limit;\n" \
           "$t" "$((GIN_ROWS+1))" "$((GIN_ROWS+GIN_ROWS/2))" ;;
    n06) for r in $(seq 1 3); do
           printf "UPDATE %s SET j = jsonb_build_object('a', 'r%sa'||id, 'b', 'r%sb'||(id%%20000), 'c', 'r%sc'||(id%%500));\n" \
             "$t" "$r" "$r" "$r"
         done ;;
    n07) for r in $(seq 1 3); do
           printf "UPDATE %s SET d = to_tsvector('simple', 'r%sa'||id||' r%sb'||(id%%20000)||' r%sc'||(id%%500));\n" \
             "$t" "$r" "$r" "$r"
         done ;;
    n10) printf 'DELETE FROM %s WHERE id > %s;\n' "$t" "$((HOT_ROWS/5))" ;;
    n12) printf "SET gin_pending_list_limit = '1GB';\nINSERT INTO %s SELECT g, ARRAY['a'||g, 'b'||(g%%50000), 'c'||(g%%1000)]\n  FROM generate_series(%s,%s) g;\nRESET gin_pending_list_limit;\n" \
           "$t" "$((GIN_ROWS+1))" "$((GIN_ROWS+A05_INSERTS))" ;;
    *) die "no churn recipe for fixture $f" ;;
  esac
}

# The maintenance step.  The default is the mandatory VACUUM ANALYZE on the
# table the churn touched; two fixtures declare a different one.
fx_maint() {
  local f="$1" t i
  t=$(tbl "$f"); i=$(idx "$f")
  case "$f" in
    h05)
      # the auto-analyze stand-in on a non-GIN AM: a plain ANALYZE and nothing
      # else, because hash, GiST, SP-GiST and BRIN no-op in ANALYZE-only mode
      printf 'ANALYZE VERBOSE %s;\n' "$t" ;;
    n12)
      # the auto-analyze stand-in on GIN: ANALYZE plus the pending-list flush
      # that only an autovacuum worker's ANALYZE performs
      printf "ANALYZE VERBOSE %s;\nSELECT gin_clean_pending_list('%s'::regclass);\n" "$t" "$i" ;;
    *)
      printf 'VACUUM (VERBOSE, ANALYZE) %s;\n' "$t" ;;
  esac
}

# ------------------------------------------------------------ phase helpers --
# Every census that will be compared with anything runs in one transaction
# holding SHARE ROW EXCLUSIVE on the index's table, the measurement lock both
# protocols require, and records the interval it held it.
census_locked() {
  local db="$1" f="$2" ph="$3" t i
  t=$(tbl "$f"); i=$(idx "$f")
  qin "$db" > "$OUT/census-$f-$ph.log" 2>&1 <<SQL || die "census of $f ($ph) failed"
BEGIN /* wiki_nbmaint_census */;
SET LOCAL statement_timeout = '1800s';
SET LOCAL lock_timeout = '15s';
LOCK /* wiki_nbmaint_census */ TABLE $t IN SHARE ROW EXCLUSIVE MODE;
SELECT /* wiki_nbmaint_census */ proto.note('$f','$ph','lock_acquired',
         extract(epoch from clock_timestamp())::numeric);
SELECT /* wiki_nbmaint_census */ proto.census('$f','$ph','$t','$i');
SELECT /* wiki_nbmaint_census */ proto.record('$f','$ph','$t','$i');
SELECT /* wiki_nbmaint_census */ proto.note('$f','$ph','progress_vacuum',
         (SELECT count(*) FROM pg_stat_progress_vacuum WHERE relid = '$t'::regclass));
SELECT /* wiki_nbmaint_census */ proto.note('$f','$ph','progress_analyze',
         (SELECT count(*) FROM pg_stat_progress_analyze WHERE relid = '$t'::regclass));
SELECT /* wiki_nbmaint_census */ proto.note('$f','$ph','progress_create_index',
         (SELECT count(*) FROM pg_stat_progress_create_index WHERE relid = '$t'::regclass));
SELECT /* wiki_nbmaint_census */ proto.note('$f','$ph','lock_released',
         extract(epoch from clock_timestamp())::numeric);
COMMIT /* wiki_nbmaint_census */;
SQL
}

# Who could have pinned the removal horizon at this instant: a backend with a
# transaction id or an xmin, a replication slot, a prepared transaction.  A
# read, not an interlock, so it is taken on both sides of every step.
horizon_probe() {
  local db="$1" f="$2" when="$3"
  qin "$db" > "$OUT/horizon-$f-$when.log" 2>&1 <<SQL || die "horizon probe failed"
SELECT /* wiki_nbmaint_horizon */ proto.note('$f','$when','horizon_backends',
         (SELECT count(*) FROM pg_stat_activity
           WHERE pid <> pg_backend_pid()
             AND (backend_xid IS NOT NULL OR backend_xmin IS NOT NULL)));
SELECT /* wiki_nbmaint_horizon */ proto.note('$f','$when','horizon_backend_detail', NULL,
         coalesce((SELECT string_agg(format('pid=%s type=%s state=%s xact_start=%s xid=%s xmin=%s',
                                            pid, backend_type, state, xact_start,
                                            backend_xid, backend_xmin), '; ')
                     FROM pg_stat_activity
                    WHERE pid <> pg_backend_pid()
                      AND (backend_xid IS NOT NULL OR backend_xmin IS NOT NULL)), 'none'));
SELECT /* wiki_nbmaint_horizon */ proto.note('$f','$when','horizon_slots',
         (SELECT count(*) FROM pg_replication_slots
           WHERE xmin IS NOT NULL OR catalog_xmin IS NOT NULL));
SELECT /* wiki_nbmaint_horizon */ proto.note('$f','$when','horizon_prepared',
         (SELECT count(*) FROM pg_prepared_xacts));
SQL
}

# The no-defeat rule, enforced the moment a maintenance step returns.  Reads
# the step's own log and the horizon probe taken before it, records the proofs,
# and dies - so no later stage runs and nothing is scored - if the maintenance
# was defeated.  Proofs: every settable timeout read 0 in the session; no skip,
# error or cancellation line; the VERBOSE "dead but not yet removable" count is
# 0 (a declared held snapshot must instead pin something); no horizon holder
# but a declared one.
check_maint() {
  local f="$1" db="$2" tag="$3" lg="$OUT/$3-$1.log"
  local vac=yes hold_ok=0 dead skips errs touts holders slots prep why=""
  case "$f" in h05|n12) vac=no ;; esac
  [ "$tag" = maint ] && case "$f" in g08|n10) hold_ok=1 ;; esac
  dead=$(grep -Eo '[0-9]+ are dead but not yet removable' "$lg" | head -1 | grep -Eo '^[0-9]+')
  skips=$(grep -Ec 'skipping (vacuum|analyze) of' "$lg")
  errs=$(grep -Ec 'ERROR:|canceling statement due to' "$lg")
  touts=$(grep -Eo 'timeouts in force: .*' "$lg" | head -1 | sed 's/^timeouts in force: //')
  holders=$(q "$db" "SELECT max(num) FROM proto.meas WHERE fixture='$f' AND phase='${tag}_before' AND metric='horizon_backends'")
  slots=$(q "$db" "SELECT max(num) FROM proto.meas WHERE fixture='$f' AND phase='${tag}_before' AND metric='horizon_slots'")
  prep=$(q "$db" "SELECT max(num) FROM proto.meas WHERE fixture='$f' AND phase='${tag}_before' AND metric='horizon_prepared'")
  q "$db" "SELECT proto.note('$f','$tag','dead_not_removable',${dead:-NULL}),
                  proto.note('$f','$tag','skip_lines',${skips:-0}),
                  proto.note('$f','$tag','error_lines',${errs:-0}),
                  proto.note('$f','$tag','session_timeouts',NULL,'${touts:-unrecorded}')" > /dev/null
  [ -n "$touts" ] || why="$why; no timeouts line in the session"
  printf '%s' "$touts" | grep -Eq '=[1-9]' && why="$why; a timeout was not 0 ($touts)"
  [ "${skips:-0}" = 0 ] || why="$why; $skips skip lines"
  [ "${errs:-0}" = 0 ] || why="$why; $errs error or cancellation lines"
  if [ "$vac" = yes ]; then
    if [ -z "$dead" ]; then
      why="$why; no VERBOSE dead-but-not-yet-removable count"
    elif [ "$hold_ok" = 1 ]; then
      [ "$dead" -gt 0 ] || why="$why; the declared snapshot pinned nothing"
    else
      [ "$dead" = 0 ] || why="$why; $dead tuples dead but not yet removable"
    fi
  fi
  [ "${holders:-x}" = "$hold_ok" ] || why="$why; ${holders:-?} horizon holders where $hold_ok was declared"
  [ "${slots:-x}" = 0 ] || why="$why; ${slots:-?} replication slots holding an xmin"
  [ "${prep:-x}" = 0 ] || why="$why; ${prep:-?} prepared transactions"
  if [ -n "$why" ]; then
    printf '%-4s %-7s DEFEATED%s\n' "$f" "$tag" "$why" >> "$OUT/maintenance-proof.txt"
    die "the maintenance of $f ($tag) was defeated$why: the run stops here and scores nothing"
  fi
  printf '%-4s %-7s ok  dead_not_removable=%-8s holders=%s slots=%s prepared=%s [%s]\n' \
    "$f" "$tag" "${dead:-n/a}" "$holders" "$slots" "$prep" "$touts" >> "$OUT/maintenance-proof.txt"
}

# Runs a fixture's maintenance step in a session whose timeouts are all 0,
# brackets it with two horizon probes and two timestamps, then checks it.
# $3 is the log basename: maint, or settle2 for the second VACUUM of X1/X2.
run_maint() {
  local f="$1" db="$2" tag="$3"
  horizon_probe "$db" "$f" "${tag}_before"
  # the WAL insert position just before the step: an index page whose LSN is
  # no newer than this was not written by the step (I18)
  q "$db" "SELECT proto.note('$f','$tag','started', extract(epoch from clock_timestamp())::numeric),
                  proto.note('$f','$tag','wal_lsn_before', pg_current_wal_insert_lsn() - '0/0'::pg_lsn)" > /dev/null
  fx_maint "$f" | qz "$db" > "$OUT/$tag-$f.log" 2>&1 \
    || die "maintenance of $f ($tag) failed, see $OUT/$tag-$f.log"
  q "$db" "SELECT proto.note('$f','$tag','ended', extract(epoch from clock_timestamp())::numeric)" > /dev/null
  horizon_probe "$db" "$f" "${tag}_after"
  check_maint "$f" "$db" "$tag"
}

# Opens a REPEATABLE READ transaction in a second session and holds its
# snapshot until release_snapshot terminates that backend.  The snapshot is
# fixed by the transaction's first query, and it must be opened BEFORE the
# churn commits: a snapshot taken afterwards holds nothing back.
SNAP_PID=""
hold_snapshot() {
  local db="$1" f="$2" n=0
  ( printf "BEGIN /* wiki_nbmaint_snapshot */ ISOLATION LEVEL REPEATABLE READ;\n"
    printf "SELECT /* wiki_nbmaint_snapshot */ 'snapshot holder pid ' || pg_backend_pid();\n"
    printf "SELECT /* wiki_nbmaint_snapshot */ pg_sleep(900);\n"
    printf "COMMIT /* wiki_nbmaint_snapshot */;\n" ) | qbg "$db" > "$OUT/snapshot-$f.log" 2>&1 &
  SNAP_PID=$!
  until [ "$(q "$db" "SELECT count(*) FROM pg_stat_activity
                       WHERE query LIKE '%wiki_nbmaint_snapshot%' AND backend_xmin IS NOT NULL
                         AND pid <> pg_backend_pid()")" = 1 ]; do
    n=$((n + 1)); [ "$n" -gt 60 ] && die "the declared snapshot for $f never took hold"
    sleep 0.5
  done
}
release_snapshot() {
  local db="$1" f="$2"
  q "$db" "SELECT proto.note('$f','snapshot','holders_terminated',
             (SELECT count(*) FROM pg_stat_activity
               WHERE query LIKE '%wiki_nbmaint_snapshot%' AND pid <> pg_backend_pid()))" > /dev/null
  q "$db" "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
            WHERE query LIKE '%wiki_nbmaint_snapshot%' AND pid <> pg_backend_pid()" > /dev/null
  [ -n "$SNAP_PID" ] && wait "$SNAP_PID" 2>/dev/null
  SNAP_PID=""
}

# ------------------------------------------------------------ stage order ----
# The stages that change the fixture database log themselves in
# proto.stage_log.  Each one checks the stages it depends on before it starts,
# and refuses to run again, or after a later stage has changed what it would
# read: to repeat one of those, start again at the fixtures stage.  The stages
# that only read, cross-check or re-score replace their own records instead.
need_texts() {
  [ -s "$SQLD/plan.sql" ] && [ -s "$SQLD/apply.sql" ] && [ -s "$SQLD/plan_view.sql" ] \
    || die "the page's texts have not been taken out yet: run the texts stage first"
}
need_db() {
  [ "$(q postgres "SELECT count(*) FROM pg_database WHERE datname = '$DB'")" = 1 ] \
    || die "no fixture database: run the fixtures stage first"
}
have_stage() { [ "$(q "$DB" "SELECT count(*) FROM proto.stage_log WHERE stage = '$1'")" = 1 ]; }
need_stage() {
  local s
  for s in "$@"; do have_stage "$s" || die "run the $s stage first"; done
  return 0
}
refuse_after() {   # <this stage> <stage...>: die if any of those already ran
  local me=$1 s; shift
  for s in "$@"; do
    if have_stage "$s"; then
      if [ "$s" = "$me" ]; then die "$me already ran on this fixture database: start again at the fixtures stage"; fi
      die "$me cannot run after $s has changed the fixtures: start again at the fixtures stage"
    fi
  done
  return 0
}
stage_done() {
  q "$DB" "INSERT INTO proto.stage_log (stage) VALUES ('$1')
           ON CONFLICT (stage) DO UPDATE SET done_at = clock_timestamp()" > /dev/null
}

# ----------------------------------------------------------- stage: fixtures -
stage_fixtures() {
  say "fixtures: build phase, locked baseline census, then step 2's first run"
  q postgres "SELECT count(*) FROM pg_database WHERE datname = '$PDB'" | grep -q '^1$' \
    || die "declarations are not filed: run the declare stage first"
  need_texts
  q postgres "DROP /* wiki_nbmaint_fixtures */ DATABASE IF EXISTS $DB" > /dev/null
  q postgres "CREATE /* wiki_nbmaint_fixtures */ DATABASE $DB" > /dev/null
  proto_ddl | qin "$DB" > "$OUT/proto-ddl.log" 2>&1 || die "proto DDL failed"
  local f n
  for f in $SCORED; do
    printf '  build %-4s (%s)\n' "$f" "$(fx_am "$f")"
    fx_build "$f" | qz "$DB" > "$OUT/build-$f.log" 2>&1 || die "build of $f failed, see $OUT/build-$f.log"
  done
  for f in $SCORED; do census_locked "$DB" "$f" baseline; done
  q "$DB" "SELECT fixture || ' ' || max(num) FILTER (WHERE metric = 'index_size') || ' bytes, table reltuples '
             || max(num) FILTER (WHERE metric = 'table_reltuples')
             FROM proto.meas WHERE phase = 'baseline' GROUP BY fixture ORDER BY fixture" \
    > "$OUT/baseline-sizes.txt"
  say "baseline: step 2, verbatim, first run: every fixture index is initialized"
  run_apply "$DB" baseline || die "step 2 (baseline) failed, see $OUT/apply-baseline.log"
  apply_summary baseline | tee "$OUT/baseline-apply.txt"
  q "$DB" "SELECT proto.take_snap('baseline')" > /dev/null
  n=$(q "$DB" "SELECT count(*) FROM proto.snap WHERE phase = 'baseline' AND pv = 2 AND idx ~ '^f_.*_i\$'")
  printf '%s fixture indexes carry a version-2 payload\n' "$n" | tee -a "$OUT/baseline-apply.txt"
  [ "$n" = "$(printf '%s\n' $SCORED | grep -c .)" ] || die "step 2's first run left a fixture index without a payload"
  date -u +'baselines filed at %Y-%m-%dT%H:%M:%SZ' | tee -a "$OUT/baseline-apply.txt"
  stage_done fixtures
}

# -------------------------------------------------------------- stage: churn -
# writes -> force the statistics flush -> census of the unmaintained state ->
# maintenance step, checked -> census of the maintained state.  The
# unmaintained census is a size and page reading only; the method is never
# asked about that state.
stage_churn() {
  say "churn: recipe writes, the maintenance step, the proofs, for every fixture"
  need_db; need_stage fixtures; refuse_after churn churn
  local f t i
  : > "$OUT/maintenance-proof.txt"
  for f in $SCORED; do
    t=$(tbl "$f"); i=$(idx "$f")
    printf '  churn %-4s (%s)\n' "$f" "$(fx_am "$f")"
    # X1 and X2 open their snapshot BEFORE the churn: that ordering is the
    # whole point, because only then do the deleted rows stay recently dead
    case "$f" in g08|n10) hold_snapshot "$DB" "$f" ;; esac
    { fx_churn "$f"
      printf "SELECT /* wiki_nbmaint_churn */ pg_stat_force_next_flush();\n"
    } | qin "$DB" > "$OUT/churn-$f.log" 2>&1 || die "churn of $f failed, see $OUT/churn-$f.log"
    census_locked "$DB" "$f" churn_raw
    case "$f" in
      g08|n10)
        run_maint "$f" "$DB" maint
        census_locked "$DB" "$f" churn_maintained
        release_snapshot "$DB" "$f"
        run_maint "$f" "$DB" settle2
        census_locked "$DB" "$f" settle2
        ;;
      b13)
        # the BRIN summarization stand-in: an autosummarize index whose work
        # items no worker fulfilled, desummarized in three places and then
        # summarized by the SQL functions, before the mandatory maintenance
        qz "$DB" > "$OUT/standin-$f.log" 2>&1 <<SQL || die "stand-in of $f failed"
SELECT /* wiki_nbmaint_standin */ proto.note('$f','standin','size_before_standin',
         pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_nbmaint_standin */ brin_desummarize_range('$i'::regclass, 0);
SELECT /* wiki_nbmaint_standin */ brin_desummarize_range('$i'::regclass, 128);
SELECT /* wiki_nbmaint_standin */ brin_desummarize_range('$i'::regclass, 256);
SELECT /* wiki_nbmaint_standin */ proto.note('$f','standin','size_after_desummarize',
         pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_nbmaint_standin */ brin_summarize_range('$i'::regclass, 0);
SELECT /* wiki_nbmaint_standin */ brin_summarize_new_values('$i'::regclass);
SELECT /* wiki_nbmaint_standin */ proto.note('$f','standin','size_after_summarize',
         pg_relation_size('$i'::regclass,'main'));
SQL
        census_locked "$DB" "$f" standin
        run_maint "$f" "$DB" maint
        census_locked "$DB" "$f" churn_maintained
        ;;
      h00|h07|n08|n09)
        # no churn, so nothing to maintain: the build phase's ANALYZE is what
        # the fixture carries into the decide phase
        census_locked "$DB" "$f" churn_maintained
        ;;
      *)
        run_maint "$f" "$DB" maint
        census_locked "$DB" "$f" churn_maintained
        ;;
    esac
  done
  q "$DB" "SELECT fixture || ' raw=' ||
             max(num) FILTER (WHERE phase = 'churn_raw' AND metric = 'index_size') || ' maintained=' ||
             coalesce(max(num) FILTER (WHERE phase = 'settle2' AND metric = 'index_size'),
                      max(num) FILTER (WHERE phase = 'churn_maintained' AND metric = 'index_size'))
             FROM proto.meas WHERE metric = 'index_size'
             GROUP BY fixture ORDER BY fixture" > "$OUT/maintenance-pair.txt"
  printf 'maintenance steps checked: %s, all ok\n' "$(grep -c ' ok ' "$OUT/maintenance-proof.txt")"
  stage_done churn
}

# ----------------------------------------------------- stage: autoanalyze ----
# The simulated auto-analyze census: relation_needs_vacanalyze's analyze
# verdict recomputed per table from the effective reloption-or-GUC values,
# and ANALYZE on exactly the tables it names.
CENSUS_SQL="
SELECT c.relname AS tbl,
       greatest(c.reltuples, 0)::bigint AS reltuples,
       coalesce(s.n_mod_since_analyze, 0) AS mods,
       round((CASE WHEN o.thr >= 0 THEN o.thr ELSE current_setting('autovacuum_analyze_threshold')::numeric END)
           + (CASE WHEN o.sf >= 0 THEN o.sf ELSE current_setting('autovacuum_analyze_scale_factor')::numeric END)
             * greatest(c.reltuples, 0)::numeric, 2) AS threshold,
       o.av_enabled
  FROM pg_class c
  LEFT JOIN pg_stat_all_tables s ON s.relid = c.oid
  CROSS JOIN LATERAL (
       SELECT coalesce((SELECT (regexp_match(opt, '^autovacuum_analyze_threshold=(.*)\$'))[1]::numeric
                          FROM unnest(coalesce(c.reloptions, '{}')) opt
                         WHERE opt LIKE 'autovacuum_analyze_threshold=%'), -1) AS thr,
              coalesce((SELECT (regexp_match(opt, '^autovacuum_analyze_scale_factor=(.*)\$'))[1]::numeric
                          FROM unnest(coalesce(c.reloptions, '{}')) opt
                         WHERE opt LIKE 'autovacuum_analyze_scale_factor=%'), -1) AS sf,
              NOT coalesce((SELECT (regexp_match(opt, '^autovacuum_enabled=(.*)\$'))[1] = 'false'
                              FROM unnest(coalesce(c.reloptions, '{}')) opt
                             WHERE opt LIKE 'autovacuum_enabled=%'), false) AS av_enabled
  ) o
 WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace"
stage_autoanalyze() {
  say "autoanalyze: the launcher's analyze verdict, recomputed per table"
  need_db; need_stage churn; refuse_after autoanalyze decide
  local t
  for t in tc_past tc_exact tc_off; do q "$DB" "DROP TABLE IF EXISTS $t" > /dev/null; done
  qz "$DB" > "$OUT/autoanalyze-build.log" 2>&1 <<'SQL' || die "census tables failed"
CREATE /* wiki_nbmaint_census */ TABLE tc_past  (id bigint, k bigint);
CREATE /* wiki_nbmaint_census */ TABLE tc_exact (id bigint, k bigint);
CREATE /* wiki_nbmaint_census */ TABLE tc_off   (id bigint, k bigint) WITH (autovacuum_enabled = false);
INSERT /* wiki_nbmaint_census */ INTO tc_past  SELECT g, g FROM generate_series(1,10000) g;
INSERT /* wiki_nbmaint_census */ INTO tc_exact SELECT g, g FROM generate_series(1,10000) g;
INSERT /* wiki_nbmaint_census */ INTO tc_off   SELECT g, g FROM generate_series(1,10000) g;
SELECT /* wiki_nbmaint_census */ pg_stat_force_next_flush();
ANALYZE /* wiki_nbmaint_census */ tc_past, tc_exact, tc_off;
SELECT /* wiki_nbmaint_census */ pg_stat_force_next_flush();
SQL
  # at the shipped defaults the threshold is 50 + 0.1 * 10000 = 1050: tc_past
  # crosses it, tc_exact lands exactly on it, tc_off is short-circuited
  qin "$DB" > "$OUT/autoanalyze-push.log" 2>&1 <<'SQL' || die "census push failed"
UPDATE /* wiki_nbmaint_census */ tc_past  SET k = k WHERE id <= 2000;
UPDATE /* wiki_nbmaint_census */ tc_exact SET k = k WHERE id <= 1050;
UPDATE /* wiki_nbmaint_census */ tc_off   SET k = k WHERE id <= 2000;
SELECT /* wiki_nbmaint_census */ pg_stat_force_next_flush();
SQL
  q "$DB" "SELECT /* wiki_nbmaint_census */ format('%-10s reltuples=%-9s mods=%-8s threshold=%-10s av_enabled=%s doanalyze=%s',
             tbl, reltuples, mods, threshold, av_enabled, av_enabled AND mods > threshold)
             FROM ($CENSUS_SQL) v ORDER BY tbl" > "$OUT/autoanalyze-verdicts.txt"
  q "$DB" "SELECT /* wiki_nbmaint_census */ 'ANALYZE ' || quote_ident(tbl) || ';'
             FROM ($CENSUS_SQL) v WHERE av_enabled AND mods > threshold ORDER BY tbl" \
    > "$OUT/autoanalyze-named.txt"
  qz "$DB" < "$OUT/autoanalyze-named.txt" > "$OUT/autoanalyze-run.log" 2>&1 \
    || die "the census's ANALYZE failed"
  grep -Eq 'timeouts in force: .*' "$OUT/autoanalyze-run.log" || die "the census session printed no timeouts"
  printf 'census named %s table(s) for ANALYZE: %s\n' "$(grep -c 'ANALYZE' "$OUT/autoanalyze-named.txt")" \
    "$(tr '\n' ' ' < "$OUT/autoanalyze-named.txt")" | tee -a "$OUT/autoanalyze-verdicts.txt"
  grep -E 'tc_past|tc_exact|tc_off' "$OUT/autoanalyze-verdicts.txt"
  stage_done autoanalyze
}

# ---------------------------------------------------- stage: the cross-checks
# VACUUM VERBOSE's index line, read out of each maintenance VACUUM's own log
# and stored against the census phases on either side of that VACUUM, so the
# score stage can check every count it prints against the censuses (I9).
# Then the horizon holders, the pgstattuple refusals, the instrument matrix
# and the census summary.  A crosscheck that runs again replaces its rows.
verbose_parse() {   # <fixture> <tag> <census before> <census after>
  local f=$1 tag=$2 pre=$3 post=$4 lg="$OUT/$2-$1.log" i line fields vac scans
  [ -f "$lg" ] || return 0
  i=$(idx "$f")
  vac=0; grep -q 'vacuuming "' "$lg" && vac=1
  # "index scan needed:" is printed exactly when ambulkdelete ran
  scans=0; grep -q 'index scan needed:' "$lg" && scans=1
  q "$DB" "SELECT proto.note('$f','verbose_$tag','vacuum_ran',$vac),
                  proto.note('$f','verbose_$tag','index_scans_ran',$scans),
                  proto.note('$f','verbose_$tag','census_before',NULL,'$pre'),
                  proto.note('$f','verbose_$tag','census_after',NULL,'$post')" > /dev/null
  line=$(grep -E "index \"$i\": pages: " "$lg" | head -1)
  if [ -n "$line" ]; then
    fields=$(printf '%s' "$line" | sed -E \
      's/.*pages: ([0-9]+) in total, ([0-9]+) newly deleted, ([0-9]+) currently deleted, ([0-9]+) reusable.*/\1 \2 \3 \4/')
    set -- $fields
    [ "$#" = 4 ] || die "cannot read the VERBOSE index line of $f ($tag): $line"
    q "$DB" "SELECT proto.note('$f','verbose_$tag','num_pages',$1),
                    proto.note('$f','verbose_$tag','pages_newly_deleted',$2),
                    proto.note('$f','verbose_$tag','pages_deleted',$3),
                    proto.note('$f','verbose_$tag','pages_free',$4),
                    proto.note('$f','verbose_$tag','index_line',NULL,'present')" > /dev/null
  else
    q "$DB" "SELECT proto.note('$f','verbose_$tag','index_line',NULL,'absent')" > /dev/null
  fi
}
stage_crosscheck() {
  say "crosscheck: VACUUM's index line, the proofs, the holders, the instruments"
  need_db; need_stage churn
  q "$DB" "DELETE FROM proto.meas WHERE phase LIKE 'verbose%'" > /dev/null
  local f
  for f in $SCORED; do
    case "$f" in
      b13) verbose_parse "$f" maint standin churn_maintained ;;
      *)   verbose_parse "$f" maint churn_raw churn_maintained ;;
    esac
    verbose_parse "$f" settle2 churn_maintained settle2
  done
  q "$DB" "SELECT fixture || ' ' || substring(phase from 9) || ' ' ||
             coalesce(max(txt) FILTER (WHERE metric = 'index_line'), '?') ||
             coalesce(' total=' || max(num) FILTER (WHERE metric = 'num_pages'), '') ||
             coalesce(' newly=' || max(num) FILTER (WHERE metric = 'pages_newly_deleted'), '') ||
             coalesce(' deleted=' || max(num) FILTER (WHERE metric = 'pages_deleted'), '') ||
             coalesce(' free=' || max(num) FILTER (WHERE metric = 'pages_free'), '') ||
             ' vacuum=' || max(num) FILTER (WHERE metric = 'vacuum_ran') ||
             ' bulkdelete=' || max(num) FILTER (WHERE metric = 'index_scans_ran')
             FROM proto.meas WHERE phase LIKE 'verbose%' GROUP BY fixture, phase ORDER BY fixture, phase" \
    > "$OUT/verbose-lines.txt"
  q "$DB" "SELECT format('%-4s %-14s backends=%s slots=%s prepared=%s | %s', fixture, phase,
             max(num) FILTER (WHERE metric = 'horizon_backends'),
             max(num) FILTER (WHERE metric = 'horizon_slots'),
             max(num) FILTER (WHERE metric = 'horizon_prepared'),
             max(txt) FILTER (WHERE metric = 'horizon_backend_detail'))
             FROM proto.meas
            WHERE phase IN ('maint_before','maint_after','settle2_before','settle2_after')
            GROUP BY fixture, phase ORDER BY fixture, phase" > "$OUT/horizon-holders.txt"
  : > "$OUT/instrument-matrix.txt"
  local ix am fn
  for f in h01 g06 s08 b10 n03; do
    ix=$(idx "$f"); am=$(fx_am "$f")
    for fn in "pgstattuple('$ix')" "pgstatindex('$ix')" "pgstathashindex('$ix')" "pgstatginindex('$ix')"; do
      printf '%-7s %-16s %s\n' "$am" "${fn%%(*}" \
        "$(qtry "$DB" "SELECT 'accepted' FROM $fn" 2>&1 | tr '\n' ' ' | sed -e 's/^ *//' -e 's/ *$//' | cut -c1-90)" \
        >> "$OUT/instrument-matrix.txt"
    done
  done
  q "$DB" "SELECT fixture || ' [' || phase || '] scanned=' ||
             max(num) FILTER (WHERE metric = 'census_scanned') ||
             coalesce(' bracket=' || (max(num) FILTER (WHERE metric = 'size_after_census')
                                   - max(num) FILTER (WHERE metric = 'size_before_census')), '') ||
             coalesce(' fsm=' || max(num) FILTER (WHERE metric = 'fsm_free_pages'), '') ||
             coalesce(' deleted=' || max(num) FILTER (WHERE metric = 'census_deleted'), '') ||
             coalesce(' new=' || max(num) FILTER (WHERE metric = 'census_new'), '') ||
             coalesce(' new_or_empty=' || max(num) FILTER (WHERE metric = 'census_new_or_empty'), '') ||
             coalesce(' fsm_agree=' || max(num) FILTER (WHERE metric = 'brin_fsm_agree')
                      || '/' || max(num) FILTER (WHERE metric = 'census_regular')
                      || ' higher=' || max(num) FILTER (WHERE metric = 'brin_fsm_higher')
                      || ' lower=' || max(num) FILTER (WHERE metric = 'brin_fsm_lower'), '') ||
             coalesce(' unreadable=' || max(num) FILTER (WHERE metric = 'census_unreadable'), '') ||
             coalesce(' progress=' || (max(num) FILTER (WHERE metric = 'progress_vacuum')
                                     + coalesce(max(num) FILTER (WHERE metric = 'progress_analyze'), 0)
                                     + max(num) FILTER (WHERE metric = 'progress_create_index')), '')
             FROM proto.meas
            WHERE phase IN ('baseline','churn_raw','standin','churn_maintained','settle2')
            GROUP BY fixture, phase
           HAVING count(*) FILTER (WHERE metric = 'census_scanned') > 0
            ORDER BY fixture, phase" > "$OUT/census-summary.txt"
  q "$DB" "SELECT 'hash censuses pgstattuple refused: ' || count(*) ||
             coalesce(' (' || string_agg(DISTINCT fixture || '/' || phase, ', ') || '): ' || min(txt), '')
             FROM proto.meas WHERE metric = 'pgst_refusal'" | tee "$OUT/pgstattuple-refusals.txt"
  wc -l "$OUT/verbose-lines.txt" "$OUT/horizon-holders.txt" "$OUT/census-summary.txt" | sed 's/^/    /'
  cat "$OUT/instrument-matrix.txt"
  stage_done crosscheck
}

# -------------------------------------------------------------- stage: decide
# Step 1, verbatim, inside one transaction holding SHARE ROW EXCLUSIVE on every
# fixture table; then the same rows through the one-edit view, and the
# harness's own readings of every index, in the same transaction.  A decide
# that runs again, before the oracle, replaces its own records.
stage_decide() {
  say "decide: step 1, verbatim, under the measurement lock"
  need_texts; need_db; need_stage autoanalyze; refuse_after decide oracle
  q "$DB" "DELETE FROM proto.meas WHERE fixture = 'decide'" > /dev/null
  q "$DB" "DELETE FROM proto.snap WHERE phase = 'decide'" > /dev/null
  qf "$DB" "$SQLD/plan_view.sql" > "$OUT/plan-view.log" 2>&1 || die "the one-edit view failed"
  local locks="" f
  for f in $SCORED; do locks="$locks$(tbl "$f"), "; done
  locks="${locks}tc_past, tc_exact, tc_off"
  { printf "BEGIN /* wiki_nbmaint_decide */;\n"
    printf "LOCK /* wiki_nbmaint_decide */ TABLE %s IN SHARE ROW EXCLUSIVE MODE;\n" "$locks"
    printf "SELECT proto.note('decide','decide','lock_acquired', extract(epoch from clock_timestamp())::numeric);\n"
    cat "$SQLD/plan.sql"
    printf "SELECT proto.note('decide','decide','plan_done', extract(epoch from clock_timestamp())::numeric);\n"
    printf "DROP TABLE IF EXISTS proto.decided;\n"
    printf "CREATE TABLE proto.decided AS SELECT * FROM proto.plan_v;\n"
    printf "SELECT proto.take_snap('decide');\n"
    printf "SELECT proto.note('decide','decide','lock_released', extract(epoch from clock_timestamp())::numeric);\n"
    printf "COMMIT /* wiki_nbmaint_decide */;\n"
  } | "$BIN/psql" -X -v ON_ERROR_STOP=1 -P pager=off -h "$SOCK" -p "$PORT" -d "$DB" \
      > "$OUT/decide.txt" 2>&1 || die "decide failed, see $OUT/decide.txt"
  q "$DB" "SELECT 'rows step 1 returned: ' || count(*) || ', of them fixture indexes: ' ||
             count(*) FILTER (WHERE index_name ~ '^f_.*_i\$') FROM proto.decided"
  q "$DB" "SELECT 'step 1 took ' || round((max(num) FILTER (WHERE metric = 'plan_done')
             - max(num) FILTER (WHERE metric = 'lock_acquired')) * 1000, 1) || ' ms under the lock'
             FROM proto.meas WHERE fixture = 'decide'" | tee "$OUT/decide-cost.txt"
  q "$DB" "SELECT action || ': ' || count(*) FROM proto.decided GROUP BY action ORDER BY action"
  stage_done decide
}

# -------------------------------------------------------------- stage: oracle
stage_oracle() {
  say "oracle: REINDEX INDEX at maintenance_work_mem = $MWM, bracketed"
  need_db; need_stage decide; refuse_after oracle oracle
  local f t i
  for f in $SCORED; do
    t=$(tbl "$f"); i=$(idx "$f")
    qin "$DB" > "$OUT/oracle-$f.log" 2>&1 <<SQL || die "oracle of $f failed"
SET /* wiki_nbmaint_oracle */ maintenance_work_mem = '$MWM';
SELECT /* wiki_nbmaint_oracle */ proto.note('$f','oracle','size_before', pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_nbmaint_oracle */ proto.note('$f','oracle','heap_relpages',
         (SELECT relpages FROM pg_class WHERE oid = '$t'::regclass));
SELECT /* wiki_nbmaint_oracle */ proto.note('$f','oracle','heap_reltuples',
         (SELECT reltuples::numeric FROM pg_class WHERE oid = '$t'::regclass));
REINDEX /* wiki_nbmaint_oracle */ INDEX $i;
SELECT /* wiki_nbmaint_oracle */ proto.note('$f','oracle','size_after', pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_nbmaint_oracle */ proto.note('$f','oracle','mwm', NULL, current_setting('maintenance_work_mem'));
SQL
  done
  q "$DB" "SELECT fixture || ' ' || max(num) FILTER (WHERE metric = 'size_before') || ' -> ' ||
             max(num) FILTER (WHERE metric = 'size_after') || ' = ' ||
             CASE WHEN max(num) FILTER (WHERE metric = 'size_before') > 0
                  THEN round(100.0 * (1 - max(num) FILTER (WHERE metric = 'size_after')
                                        / max(num) FILTER (WHERE metric = 'size_before')), 2)
                  ELSE 0 END || ' %'
             FROM proto.meas WHERE phase = 'oracle' AND metric IN ('size_before','size_after')
             GROUP BY fixture ORDER BY fixture" > "$OUT/oracle-summary.txt"
  wc -l < "$OUT/oracle-summary.txt" | sed 's/^/    fixtures rebuilt: /'
  stage_done oracle
}

# ----------------------------------------------------------------- stage: act
# Step 1 then step 2 on the state the oracle left - every fixture index just
# rebuilt out of band - then step 2 again.  Not scored against the oracle: it
# checks that step 2 does what step 1 printed, and that a settled database
# costs nothing, and it fails the run when either does not hold.
stage_act() {
  say "act: step 1, step 2, step 2 again, on the rebuilt state"
  need_texts; need_db; need_stage oracle; refuse_after act act
  q "$DB" "SELECT proto.take_snap('act_before')" > /dev/null
  run_plan "$DB" act || die "step 1 (act) failed"
  q "$DB" "DROP TABLE IF EXISTS proto.act_plan;
           CREATE TABLE proto.act_plan AS SELECT * FROM proto.plan_v" > /dev/null
  run_apply "$DB" act1 || die "step 2 (act1) failed, see $OUT/apply-act1.log"
  q "$DB" "SELECT proto.take_snap('act_after')" > /dev/null
  run_apply "$DB" act2 || die "step 2 (act2) failed"
  q "$DB" "SELECT proto.take_snap('act_second')" > /dev/null
  local did same n
  n=$(q "$DB" "SELECT count(*) FROM proto.act_plan")
  did=$(q "$DB" "WITH b AS (SELECT * FROM proto.snap WHERE phase = 'act_before'),
                      a AS (SELECT * FROM proto.snap WHERE phase = 'act_after')
                 SELECT count(*) FILTER (WHERE CASE p.action
                          WHEN 'reindex' THEN a.filenode <> b.filenode AND a.pv = 2 AND a.sz = a.bytes
                                              AND a.tup = round(greatest(a.tbl_tuples, -1))
                          WHEN 'initialize' THEN a.filenode = b.filenode AND a.pv = 2 AND a.sz = a.bytes
                                              AND a.tup = round(greatest(a.tbl_tuples, -1))
                          WHEN 'refresh' THEN a.filenode = b.filenode AND a.pv = 2 AND a.sz = a.bytes
                                              AND a.tup = round(greatest(a.tbl_tuples, -1))
                          WHEN 'skip' THEN a.filenode = b.filenode AND a.cmt IS NOT DISTINCT FROM b.cmt
                          ELSE false END)
                   FROM proto.act_plan p JOIN b ON b.idx = p.index_name JOIN a ON a.idx = p.index_name")
  same=$(q "$DB" "SELECT count(*) FILTER (WHERE s.filenode = a.filenode AND s.cmt IS NOT DISTINCT FROM a.cmt)
                    FROM proto.act_plan p
                    JOIN proto.snap a ON a.phase = 'act_after'  AND a.idx = p.index_name
                    JOIN proto.snap s ON s.phase = 'act_second' AND s.idx = p.index_name")
  { printf 'step 1 plan:   %s\n' "$(q "$DB" "SELECT string_agg(action || '=' || n, ' ' ORDER BY action)
                                            FROM (SELECT action, count(*) n FROM proto.act_plan GROUP BY action) s")"
    printf 'step 2 run 1:  %s\n' "$(apply_summary act1)"
    printf 'step 2 run 2:  %s\n' "$(apply_summary act2)"
    printf 'per index, step 2 did what step 1 printed: %s of %s; unchanged by the second run: %s of %s\n' \
      "$did" "$n" "$same" "$n"
    printf -- '-- per fixture: the action on the rebuilt state, and why\n'
    q "$DB" "SELECT format('%-10s %-8s size_ratio=%s tuple_ratio=%s %s', index_name, action,
                           coalesce(size_ratio::text, '-'), coalesce(tuple_ratio::text, '-'), notes)
               FROM proto.act_plan ORDER BY index_name"
  } > "$OUT/act.txt"
  head -4 "$OUT/act.txt"
  [ "$did" = "$n" ] && [ "$same" = "$n" ] \
    || die "act: step 2 did not do what step 1 printed, or its second run wrote (see $OUT/act.txt)"
  apply_summary act2 | grep -q 'reindex=0 initialize=0 refresh=0 ' || die "act: the second run of step 2 wrote"
  stage_done act
}

# --------------------------------------------------------------- stage: score
# Pure computation over what the earlier stages recorded, so it may run again
# at any time after act; each run rebuilds its tables.  truth_pct is the
# oracle's fraction rounded for display; every comparison with the pay-off
# threshold uses the unrounded truth_exact.  Every invariant is stored with
# whether it held, and a run in which any declared invariant failed fails
# here, after every file is written.
NOCHURN="'h00','h07','n08','n09'"
stage_score() {
  say "score: every decision against the oracle, at the filed pay-off threshold"
  need_db; need_stage churn crosscheck decide oracle act
  # The run is refused a score when any maintenance proof failed.  check_maint
  # already stopped the run at the failing step; this is the same rule, read
  # back from what was recorded, for a score stage run on its own.
  ! grep -q 'DEFEATED' "$OUT/maintenance-proof.txt" 2>/dev/null \
    || die "a maintenance step was defeated: nothing is scored"
  [ "$(q "$DB" "SELECT count(*) FROM proto.meas WHERE metric = 'dead_not_removable'")" -gt 0 ] \
    || die "no maintenance proof was recorded: nothing is scored"
  local tb
  for tb in declared_kind declared_decision declared_prediction declared_invariant declared_exception declared_coverage; do
    q "$DB" "DROP TABLE IF EXISTS proto.$tb" > /dev/null
  done
  qin "$DB" > "$OUT/score-ddl.log" 2>&1 <<'SQL'
CREATE TABLE proto.declared_kind       (column_name text, declared_kind text, claim text, filed_at timestamptz);
CREATE TABLE proto.declared_decision   (knob text, value text, meaning text, filed_at timestamptz);
CREATE TABLE proto.declared_prediction (fixture text, action text, score text, why text, filed_at timestamptz);
CREATE TABLE proto.declared_invariant  (id text, claim text, filed_at timestamptz);
CREATE TABLE proto.declared_exception  (id text, fixture text, state text, reading_rule text, filed_at timestamptz);
CREATE TABLE proto.declared_coverage   (protocol text, behavior text, fixture text, filed_at timestamptz);
SQL
  for tb in declared_kind declared_decision declared_prediction declared_invariant declared_exception declared_coverage; do
    q "$PDB" "SELECT format('INSERT INTO proto.$tb SELECT (json_populate_record(NULL::proto.$tb, %L)).*;',
                            row_to_json(d)::text) FROM $tb d" \
      | qin "$DB" > "$OUT/score-copy-$tb.log" 2>&1
  done
  { q "$DB" "SELECT 'declarations carried: ' || count(*) || ' kinds, filed at ' ||
               to_char(min(filed_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') FROM proto.declared_kind"
    q "$DB" "SELECT 'first baseline payload written at ' ||
               to_char(min(at) AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')
               FROM proto.snap WHERE phase = 'baseline'"
  } | tee "$OUT/score-declarations.txt"

  qin "$DB" > "$OUT/score-build.log" 2>&1 <<'SQL'
DROP TABLE IF EXISTS proto.score;
CREATE /* wiki_nbmaint_score */ TABLE proto.score AS
WITH m AS (
  SELECT fixture,
         max(num) FILTER (WHERE phase = 'baseline'  AND metric = 'index_size') AS base_size,
         max(num) FILTER (WHERE phase = 'churn_raw' AND metric = 'index_size') AS raw_size,
         -- on X1 and X2 the maintained state is the settle2 census, after the
         -- declared snapshot was released and a second VACUUM ANALYZE ran
         coalesce(max(num) FILTER (WHERE phase = 'settle2' AND metric = 'index_size'),
                  max(num) FILTER (WHERE phase = 'churn_maintained' AND metric = 'index_size')) AS maint_size,
         max(num) FILTER (WHERE phase = 'oracle' AND metric = 'size_before')    AS oracle_before,
         max(num) FILTER (WHERE phase = 'oracle' AND metric = 'size_after')     AS oracle_after,
         max(num) FILTER (WHERE phase = 'oracle' AND metric = 'heap_relpages')  AS heap_relpages,
         max(num) FILTER (WHERE phase = 'oracle' AND metric = 'heap_reltuples') AS heap_reltuples
    FROM proto.meas GROUP BY fixture
),
bl AS (
  SELECT substring(idx from '^f_(.*)_i$') AS fixture, bytes AS capture_bytes,
         tbl_tuples AS capture_tuples, pv AS captured_v, sz AS captured_sz, tup AS captured_tup
    FROM proto.snap WHERE phase = 'baseline'
),
ds AS (
  SELECT substring(idx from '^f_(.*)_i$') AS fixture, bytes AS decide_bytes,
         tbl_tuples AS decide_tuples, sz AS stored_sz, tup AS stored_tup
    FROM proto.snap WHERE phase = 'decide'
),
dec AS (
  SELECT substring(index_name from '^f_(.*)_i$') AS fixture, access_method AS am,
         action, size_ratio, tuple_ratio, notes
    FROM proto.decided WHERE schema_name = 'public' AND index_name ~ '^f_.*_i$'
),
pay AS (
  SELECT (regexp_match(value, '([0-9]+[.][0-9]+)'))[1]::numeric AS min_truth
    FROM proto.declared_decision WHERE knob = 'pay-off'
),
base AS (
  SELECT m.fixture, dec.am, m.base_size, bl.captured_v, bl.captured_sz, bl.capture_bytes,
         bl.captured_tup, bl.capture_tuples, m.raw_size, m.maint_size, ds.decide_bytes,
         m.oracle_before, m.oracle_after, m.heap_relpages, m.heap_reltuples,
         ds.stored_sz, ds.stored_tup, ds.decide_tuples,
         -- the oracle's own fraction, unrounded: what the threshold is applied to
         CASE WHEN m.oracle_before > 0
              THEN 100.0 * (1 - m.oracle_after / m.oracle_before) ELSE 0 END AS truth_exact,
         dec.size_ratio, dec.tuple_ratio, dec.notes, dec.action,
         -- the brief's two tests, recomputed from the harness's own readings
         (ds.decide_bytes >= ds.stored_sz * 1.30) AS size_fired,
         (ds.decide_tuples >= 0 AND ds.stored_tup >= 0
          AND CASE WHEN ds.stored_tup = 0 THEN ds.decide_tuples > 0
                   ELSE abs(ds.decide_tuples - ds.stored_tup) >= ds.stored_tup * 0.30 END) AS tuple_fired,
         pay.min_truth,
         p.action AS want_action, p.score AS want_score, p.why AS want_why
    FROM m
    JOIN dec USING (fixture) JOIN bl USING (fixture) JOIN ds USING (fixture)
    CROSS JOIN pay
    LEFT JOIN proto.declared_prediction p USING (fixture)
)
SELECT b.*,
       round(b.truth_exact, 2) AS truth_pct,
       CASE WHEN b.stored_sz IS NULL THEN 'initialize'
            WHEN b.decide_bytes < b.stored_sz THEN 'refresh'
            WHEN b.size_fired OR b.tuple_fired THEN 'reindex'
            ELSE 'skip' END AS expected_action,
       (b.truth_exact >= b.min_truth) AS pays_off,
       CASE WHEN b.action = 'reindex' AND b.truth_exact >= b.min_truth THEN 'PASS'
            WHEN b.action = 'reindex'                                  THEN 'FALSE POSITIVE'
            WHEN b.truth_exact >= b.min_truth                          THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END AS score
  FROM base b;
SQL
  q "$DB" "SELECT count(*) FROM proto.score" | grep -q '^[1-9]' || die "the score table is empty (see $OUT/score-build.log)"
  q "$DB" "SELECT format('%-4s %-6s B=%-10s C=%-10s R=%-10s truth=%6s%% size=%-7s tuples=%-7s fired=%-11s action=%-7s score=%-15s predicted=%s',
             fixture, am, base_size, decide_bytes, oracle_after, truth_pct,
             coalesce(size_ratio::text, '-'), coalesce(tuple_ratio::text, '-'),
             CASE WHEN size_fired AND tuple_fired THEN 'both' WHEN size_fired THEN 'size'
                  WHEN tuple_fired THEN 'tuples' ELSE 'none' END,
             action, score,
             CASE WHEN want_action = action AND want_score = score THEN 'hit'
                  ELSE 'MISS (' || coalesce(want_action, '?') || ', ' || coalesce(want_score, '?') || ')' END)
             FROM proto.score ORDER BY am, fixture" > "$OUT/score-table.txt"
  { q "$DB" "SELECT 'pay-off threshold: truth_exact >= ' || min(min_truth) || ', on the unrounded fraction' FROM proto.score"
    q "$DB" "SELECT score || ': ' || count(*) FROM proto.score GROUP BY score ORDER BY score"
    q "$DB" "SELECT am || ': ' || string_agg(score || '=' || n, ', ' ORDER BY score)
               FROM (SELECT am, score, count(*) n FROM proto.score GROUP BY am, score) s
              GROUP BY am ORDER BY am"
    q "$DB" "SELECT 'reindex decisions: ' || count(*) FILTER (WHERE action = 'reindex') ||
               ' (size test ' || count(*) FILTER (WHERE size_fired) ||
               ', tuple test ' || count(*) FILTER (WHERE tuple_fired) ||
               ', both ' || count(*) FILTER (WHERE size_fired AND tuple_fired) ||
               ', size only ' || count(*) FILTER (WHERE size_fired AND NOT tuple_fired) ||
               ', tuples only ' || count(*) FILTER (WHERE tuple_fired AND NOT size_fired) || ')'
               FROM proto.score"
    q "$DB" "SELECT 'fixtures that paid off: ' || count(*) FILTER (WHERE pays_off) || ' of ' || count(*) ||
               '; mean truth of the rebuilt ' ||
               coalesce(round(avg(truth_exact) FILTER (WHERE action = 'reindex'), 1)::text, '-') ||
               ' %, of the skipped ' ||
               coalesce(round(avg(truth_exact) FILTER (WHERE action <> 'reindex'), 1)::text, '-') || ' %'
               FROM proto.score"
    q "$DB" "SELECT 'closest to the threshold: ' || string_agg(fixture || ' ' || round(truth_exact, 4) || ' %', ', '
               ORDER BY abs(truth_exact - min_truth)) FROM (SELECT * FROM proto.score
               ORDER BY abs(truth_exact - min_truth) LIMIT 3) s"
    q "$DB" "SELECT 'false positives: ' || coalesce(string_agg(fixture || ' (' || truth_pct || ' %, ' ||
               CASE WHEN size_fired AND tuple_fired THEN 'both' WHEN size_fired THEN 'size' ELSE 'tuples' END
               || ')', ', ' ORDER BY fixture), 'none') FROM proto.score WHERE score = 'FALSE POSITIVE'"
    q "$DB" "SELECT 'false negatives: ' || coalesce(string_agg(fixture || ' (' || truth_pct || ' %, size '
               || size_ratio || ', tuples ' || coalesce(tuple_ratio::text, '-') || ')', ', ' ORDER BY fixture), 'none')
               FROM proto.score WHERE score = 'FALSE NEGATIVE'"
    q "$DB" "SELECT 'predictions: ' || count(*) FILTER (WHERE want_action = action AND want_score = score)
               || ' of ' || count(*) || ' hit; misses: ' ||
               coalesce(string_agg(fixture || ' predicted ' || want_action || '/' || want_score ||
                                   ', measured ' || action || '/' || score, '; ')
                        FILTER (WHERE NOT (want_action = action AND want_score = score)), 'none')
               FROM proto.score"
    q "$DB" "SELECT 'the tuple test on a rise: ' ||
               coalesce(string_agg(fixture || ' ' || score, ', ' ORDER BY fixture)
                          FILTER (WHERE tuple_fired AND decide_tuples > stored_tup), 'none') ||
               '; on a fall: ' ||
               coalesce(string_agg(fixture || ' ' || score, ', ' ORDER BY fixture)
                          FILTER (WHERE tuple_fired AND decide_tuples < stored_tup), 'none')
               FROM proto.score"
    q "$DB" "SELECT 'the size test alone: ' || string_agg(score || ' ' || n || ' (' || fx || ')', '; ' ORDER BY score)
               FROM (SELECT score, count(*) n, string_agg(fixture, ',' ORDER BY fixture) fx
                       FROM proto.score WHERE size_fired AND NOT tuple_fired GROUP BY score) s"
    q "$DB" "SELECT 'the whole run, not just fixtures: step 1 returned ' || count(*) || ' rows, actions ' ||
               string_agg(DISTINCT action, ',') FROM proto.decided"
  } | tee "$OUT/score-summary.txt"

  say "score: the invariants"
  local act_line
  act_line=$(grep -h 'per index, step 2 did what step 1 printed' "$OUT/act.txt" 2>/dev/null)
  qin "$DB" > "$OUT/invariants-build.log" 2>&1 <<SQL
DROP TABLE IF EXISTS proto.invariant;
CREATE TABLE proto.invariant (id text PRIMARY KEY, reading text NOT NULL, holds boolean NOT NULL);
DROP TABLE IF EXISTS proto.census_v;
CREATE TABLE proto.census_v AS
  SELECT fixture, phase,
         max(num) FILTER (WHERE metric = 'census_scanned')      AS scanned,
         max(num) FILTER (WHERE metric = 'size_before_census')  AS sz_before,
         max(num) FILTER (WHERE metric = 'size_after_census')   AS sz_after,
         max(num) FILTER (WHERE metric = 'census_meta')         AS c_meta,
         max(num) FILTER (WHERE metric = 'census_bucket')       AS c_bucket,
         max(num) FILTER (WHERE metric = 'census_overflow')     AS c_ovfl,
         max(num) FILTER (WHERE metric = 'census_bitmap')       AS c_bitmap,
         max(num) FILTER (WHERE metric = 'census_unused')       AS c_unused,
         max(num) FILTER (WHERE metric = 'census_unreadable')   AS c_bad,
         max(num) FILTER (WHERE metric = 'census_deleted')      AS c_del,
         max(num) FILTER (WHERE metric = 'census_new')          AS c_new,
         max(num) FILTER (WHERE metric = 'census_new_or_empty') AS c_empty,
         max(num) FILTER (WHERE metric = 'census_entry')        AS c_entry,
         max(num) FILTER (WHERE metric = 'census_data')         AS c_data,
         max(num) FILTER (WHERE metric = 'census_list')         AS c_list,
         max(num) FILTER (WHERE metric = 'fsm_free_pages')      AS fsm,
         max(num) FILTER (WHERE metric = 'brin_items')          AS b_items,
         max(num) FILTER (WHERE metric = 'brin_unused_items')   AS b_unused,
         max(num) FILTER (WHERE metric = 'brin_revmap_entries') AS b_revmap,
         max(num) FILTER (WHERE metric = 'meta_total_pages')    AS m_total,
         max(num) FILTER (WHERE metric = 'meta_entry_pages')    AS m_entry,
         max(num) FILTER (WHERE metric = 'meta_data_pages')     AS m_data,
         max(num) FILTER (WHERE metric = 'meta_pending_pages')  AS m_pending,
         max(num) FILTER (WHERE metric = 'hs_bucket_pages')     AS hs_bucket,
         max(num) FILTER (WHERE metric = 'hs_overflow_pages')   AS hs_ovfl,
         max(num) FILTER (WHERE metric = 'hs_bitmap_pages')     AS hs_bitmap,
         max(num) FILTER (WHERE metric = 'hs_unused_pages')     AS hs_unused,
         max(num) FILTER (WHERE metric = 'bitmap_disagree')     AS bm_dis
    FROM proto.meas
   WHERE phase IN ('baseline','churn_raw','standin','churn_maintained','settle2')
   GROUP BY fixture, phase
  HAVING count(*) FILTER (WHERE metric = 'census_scanned') > 0;
-- One row per maintenance VACUUM: its VERBOSE counts beside the censuses
-- taken just before and just after it.
DROP TABLE IF EXISTS proto.vac_v;
CREATE TABLE proto.vac_v AS
  SELECT v.fixture, v.phase AS tag, sc.am,
         max(v.num) FILTER (WHERE v.metric = 'vacuum_ran')          AS vacuum_ran,
         max(v.num) FILTER (WHERE v.metric = 'index_scans_ran')     AS scans_ran,
         max(v.txt) FILTER (WHERE v.metric = 'index_line')          AS line,
         max(v.num) FILTER (WHERE v.metric = 'num_pages')           AS num_pages,
         max(v.num) FILTER (WHERE v.metric = 'pages_newly_deleted') AS newly,
         max(v.num) FILTER (WHERE v.metric = 'pages_deleted')       AS deleted,
         max(v.num) FILTER (WHERE v.metric = 'pages_free')          AS free,
         max(v.txt) FILTER (WHERE v.metric = 'census_before')       AS pre_phase,
         max(v.txt) FILTER (WHERE v.metric = 'census_after')        AS post_phase
    FROM proto.meas v JOIN proto.score sc ON sc.fixture = v.fixture
   WHERE v.phase LIKE 'verbose%'
   GROUP BY v.fixture, v.phase, sc.am;

INSERT INTO proto.invariant
SELECT 'I1', count(*) FILTER (WHERE maint_size >= base_size) || ' of ' || count(*) || ' (smaller: ' ||
       coalesce(string_agg(fixture, ',') FILTER (WHERE maint_size < base_size), 'none') || ')',
       bool_and(maint_size >= base_size)
  FROM proto.score;
INSERT INTO proto.invariant
SELECT 'I2', count(*) FILTER (WHERE sz_before = sz_after AND sz_after = scanned * b) || ' of ' || count(*) || ' censuses',
       bool_and(sz_before = sz_after AND sz_after = scanned * b)
  FROM proto.census_v CROSS JOIN (SELECT current_setting('block_size')::numeric AS b) blk;
INSERT INTO proto.invariant
SELECT 'I3', count(*) FILTER (WHERE c_meta + c_bucket + c_ovfl + c_bitmap + c_unused + c_bad = scanned
                                AND hs_bucket + hs_ovfl + hs_bitmap + hs_unused + 1 = scanned)
             || ' of ' || count(*) || ' hash censuses',
       bool_and(c_meta + c_bucket + c_ovfl + c_bitmap + c_unused + c_bad = scanned
                AND hs_bucket + hs_ovfl + hs_bitmap + hs_unused + 1 = scanned)
  FROM proto.census_v c JOIN proto.score s USING (fixture) WHERE s.am = 'hash';
INSERT INTO proto.invariant
SELECT 'I4', count(*) FILTER (WHERE bm_dis = 0) || ' of ' || count(*) || ' hash censuses', bool_and(bm_dis = 0)
  FROM proto.census_v c JOIN proto.score s USING (fixture) WHERE s.am = 'hash';
INSERT INTO proto.invariant
SELECT 'I5', count(*) FILTER (WHERE s.am = 'gist' AND fsm <= c_del + c_new) || ' of '
             || count(*) FILTER (WHERE s.am = 'gist') || ' GiST censuses, '
             || count(*) FILTER (WHERE s.am = 'spgist' AND fsm <= c_empty) || ' of '
             || count(*) FILTER (WHERE s.am = 'spgist') || ' SP-GiST censuses',
       bool_and(CASE s.am WHEN 'gist' THEN fsm <= c_del + c_new ELSE fsm <= c_empty END)
  FROM proto.census_v c JOIN proto.score s USING (fixture) WHERE s.am IN ('gist', 'spgist');
INSERT INTO proto.invariant
SELECT 'I6', count(*) FILTER (WHERE b_revmap = b_items) || ' of ' || count(*) || ' BRIN censuses',
       bool_and(b_revmap = b_items)
  FROM proto.census_v c JOIN proto.score s USING (fixture) WHERE s.am = 'brin';
INSERT INTO proto.invariant
SELECT 'I7', count(*) FILTER (WHERE maint_size >= raw_size) || ' of ' || count(*) || ' BRIN fixtures',
       bool_and(maint_size >= raw_size)
  FROM proto.score WHERE am = 'brin';
-- I8 is scoped to the censuses whose metapage counts the build or a VACUUM's
-- cleanup wrote last: the metapage is rewritten by nothing else, so a census
-- taken after writes and before a VACUUM reads counts stale by construction
INSERT INTO proto.invariant
SELECT 'I8', count(*) FILTER (WHERE fresh AND ok) || ' of ' || count(*) FILTER (WHERE fresh)
             || ' GIN censuses the build or a VACUUM left (disagreeing: '
             || coalesce(string_agg(fixture || '/' || phase, ',') FILTER (WHERE fresh AND NOT ok), 'none')
             || '); stale by construction, not scored: ' || count(*) FILTER (WHERE NOT fresh),
       coalesce(bool_and(ok) FILTER (WHERE fresh), true)
  FROM (SELECT c.fixture, c.phase,
               (m_entry = c_entry AND m_data = c_data + greatest(c_del - fsm, 0) AND m_total = scanned) AS ok,
               (c.phase = 'baseline' OR c.fixture IN ($NOCHURN)
                OR EXISTS (SELECT 1 FROM proto.vac_v v WHERE v.fixture = c.fixture
                             AND v.post_phase = c.phase AND v.vacuum_ran = 1)) AS fresh
          FROM proto.census_v c JOIN proto.score s USING (fixture) WHERE s.am = 'gin') g;
-- I9: VERBOSE's index line against the censuses around its own VACUUM
INSERT INTO proto.invariant
SELECT 'I9', count(*) FILTER (WHERE why = 'ok') || ' of ' || count(*)
             || ' maintenance VACUUM and ANALYZE steps agree (' || count(*) FILTER (WHERE line = 'present')
             || ' index lines; disagreeing: '
             || coalesce(string_agg(fixture || '/' || tag || ' ' || why, '; ') FILTER (WHERE why <> 'ok'), 'none')
             || ')',
       bool_and(why = 'ok')
  FROM (SELECT v.fixture, substring(v.tag from 9) AS tag, v.line,
               CASE
                 WHEN v.vacuum_ran = 0 THEN CASE WHEN v.line = 'absent' THEN 'ok' ELSE 'a line with no VACUUM' END
                 WHEN v.am = 'hash' AND v.scans_ran = 0 THEN
                      CASE WHEN v.line = 'absent' THEN 'ok' ELSE 'a hash line with no bulk delete' END
                 WHEN v.line IS DISTINCT FROM 'present' THEN 'no line'
                 WHEN v.num_pages IS DISTINCT FROM CASE WHEN v.am = 'brin' THEN pre.scanned ELSE post.scanned END
                      THEN 'total ' || v.num_pages
                 WHEN v.am IN ('hash', 'brin') AND (coalesce(v.newly, 0), v.deleted, v.free) IS DISTINCT FROM (0, 0, 0)
                      THEN 'nonzero counts'
                 WHEN v.am = 'gist' AND (v.deleted, v.free, coalesce(v.newly, post.c_del - pre.c_del))
                      IS DISTINCT FROM (post.c_del + post.c_new, post.fsm, post.c_del - pre.c_del)
                      THEN 'deleted ' || v.deleted || '/' || (post.c_del + post.c_new) || ' free ' || v.free || '/'
                           || post.fsm || ' newly ' || v.newly || '/' || (post.c_del - pre.c_del)
                 WHEN v.am = 'spgist' AND (coalesce(v.newly, post.c_empty), v.deleted, v.free, post.fsm)
                      IS DISTINCT FROM (post.c_empty, post.c_empty, post.c_empty, post.c_empty)
                      THEN 'deleted ' || v.deleted || ' free ' || v.free || ' newly ' || v.newly
                           || ' new-or-empty ' || post.c_empty || ' fsm ' || post.fsm
                 WHEN v.am = 'gin' AND v.free IS DISTINCT FROM post.fsm
                      THEN 'free ' || v.free || '/' || post.fsm
                 ELSE 'ok' END AS why
          FROM proto.vac_v v
          LEFT JOIN proto.census_v pre  ON pre.fixture  = v.fixture AND pre.phase  = v.pre_phase
          LEFT JOIN proto.census_v post ON post.fixture = v.fixture AND post.phase = v.post_phase) x;
INSERT INTO proto.invariant
SELECT 'I10', count(*) FILTER (WHERE num = 0) || ' VACUUMs at 0 dead but not yet removable, '
              || count(*) FILTER (WHERE num > 0) || ' above 0 ('
              || coalesce(string_agg(fixture || '/' || phase || '=' || num, ', ') FILTER (WHERE num > 0), 'none') || ')',
       bool_and(CASE WHEN phase = 'maint' AND fixture IN ('g08', 'n10') THEN num > 0 ELSE num = 0 END)
  FROM proto.meas WHERE metric = 'dead_not_removable' AND num IS NOT NULL;
INSERT INTO proto.invariant
SELECT 'I11', count(*) FILTER (WHERE metric = 'skip_lines') || ' maintenance sessions, skip lines '
              || coalesce(sum(num) FILTER (WHERE metric = 'skip_lines'), 0) || ', error lines '
              || coalesce(sum(num) FILTER (WHERE metric = 'error_lines'), 0) || ', timeout sets: '
              || coalesce(string_agg(DISTINCT txt, ' | ') FILTER (WHERE metric = 'session_timeouts'), '-'),
       coalesce(sum(num) FILTER (WHERE metric IN ('skip_lines', 'error_lines')), 0) = 0
       AND coalesce(bool_and(txt !~ '=[1-9]') FILTER (WHERE metric = 'session_timeouts'), false)
  FROM proto.meas WHERE metric IN ('skip_lines', 'error_lines', 'session_timeouts');
INSERT INTO proto.invariant
WITH lk AS (SELECT fixture, phase, max(num) FILTER (WHERE metric = 'lock_acquired') AS t0,
                   max(num) FILTER (WHERE metric = 'lock_released') AS t1
              FROM proto.meas WHERE metric IN ('lock_acquired','lock_released') GROUP BY fixture, phase),
     mt AS (SELECT fixture, phase, max(num) FILTER (WHERE metric = 'started') AS m0,
                   max(num) FILTER (WHERE metric = 'ended') AS m1
              FROM proto.meas WHERE metric IN ('started','ended') GROUP BY fixture, phase),
     ov AS (SELECT 1 FROM lk JOIN mt ON lk.t0 < mt.m1 AND mt.m0 < lk.t1)
SELECT 'I12', (SELECT count(*) FROM lk) || ' lock intervals, ' || (SELECT count(*) FROM mt)
              || ' maintenance intervals, overlaps ' || (SELECT count(*) FROM ov),
       (SELECT count(*) FROM ov) = 0;
INSERT INTO proto.invariant
SELECT 'I13', count(*) FILTER (WHERE slots = 0 AND prepared = 0 AND backends = 0) || ' of ' || count(*)
              || ' probes clean; holding a backend: '
              || coalesce(string_agg(fixture || '/' || phase, ', ') FILTER (WHERE backends > 0), 'none')
              || '; slots ' || coalesce(sum(slots), 0) || ', prepared ' || coalesce(sum(prepared), 0),
       bool_and(slots = 0 AND prepared = 0
                AND backends = CASE WHEN fixture IN ('g08', 'n10') AND phase LIKE 'maint_%' THEN 1 ELSE 0 END)
  FROM (SELECT fixture, phase,
               max(num) FILTER (WHERE metric = 'horizon_backends') AS backends,
               max(num) FILTER (WHERE metric = 'horizon_slots')    AS slots,
               max(num) FILTER (WHERE metric = 'horizon_prepared') AS prepared
          FROM proto.meas
         WHERE phase IN ('maint_before','maint_after','settle2_before','settle2_after')
         GROUP BY fixture, phase) h;
INSERT INTO proto.invariant
SELECT 'I14', count(*) FILTER (WHERE ok) || ' of ' || count(*) || ' version 2, sz = census size, tup = table count',
       bool_and(ok)
  FROM (SELECT captured_v = 2 AND captured_sz = base_size AND captured_sz = capture_bytes
               AND captured_tup = round(greatest(capture_tuples, -1)) AS ok FROM proto.score) s;
INSERT INTO proto.invariant
SELECT 'I15', count(*) FILTER (WHERE decide_bytes = maint_size AND decide_bytes = oracle_before) || ' of ' || count(*),
       bool_and(decide_bytes = maint_size AND decide_bytes = oracle_before)
  FROM proto.score;
INSERT INTO proto.invariant
SELECT 'I16', count(*) FILTER (WHERE action = expected_action) || ' of ' || count(*) || ' (disagreeing: '
              || coalesce(string_agg(fixture, ',') FILTER (WHERE action <> expected_action), 'none') || ')',
       bool_and(action = expected_action)
  FROM proto.score;
INSERT INTO proto.invariant
SELECT 'I17', coalesce(nullif('$act_line', ''), 'act has not run'),
       coalesce('$act_line' ~ ': ([0-9]+) of \1; unchanged by the second run: \1 of \1\$', false);
-- I18: BRIN's graduated FSM agreement, scored where the source makes it exact:
-- every regular page a VACUUM did not write, found by its LSN against the WAL
-- insert position read just before that VACUUM began.  The pages the
-- VACUUM's own summarization wrote are compared and reported, not scored.
INSERT INTO proto.invariant
SELECT 'I18', count(*) FILTER (WHERE untouched AND fsm_read = fsm_expected) || ' of '
              || count(*) FILTER (WHERE untouched)
              || ' regular pages the VACUUM did not write read their exact FSM category (failing: '
              || coalesce(string_agg(fixture || '/' || phase || '/' || blkno, ',')
                          FILTER (WHERE untouched AND fsm_read <> fsm_expected), 'none')
              || '); of the ' || count(*) FILTER (WHERE NOT untouched) || ' it wrote, '
              || count(*) FILTER (WHERE NOT untouched AND fsm_read = fsm_expected) || ' agree, '
              || count(*) FILTER (WHERE NOT untouched AND fsm_read > fsm_expected) || ' read higher and '
              || count(*) FILTER (WHERE NOT untouched AND fsm_read < fsm_expected) || ' lower, reported only',
       coalesce(bool_and(fsm_read = fsm_expected) FILTER (WHERE untouched), true)
  FROM (SELECT p.fixture, p.phase, p.blkno, p.fsm_read, p.fsm_expected,
               p.page_lsn <= w.num AS untouched
          FROM proto.brin_page p
          JOIN proto.vac_v v ON v.fixture = p.fixture AND v.post_phase = p.phase AND v.vacuum_ran = 1
          JOIN proto.meas w ON w.fixture = p.fixture AND w.phase = substring(v.tag from 9)
                           AND w.metric = 'wal_lsn_before') f;
SQL
  q "$DB" "SELECT count(*) FROM proto.invariant" | grep -q '^18$' \
    || die "the invariants did not all compute (see $OUT/invariants-build.log)"
  q "$DB" "SELECT id || ' ' || CASE WHEN holds THEN 'holds' ELSE 'FAILS' END || ': ' || reading
             FROM proto.invariant ORDER BY substring(id from 2)::int" > "$OUT/invariants.txt"
  cat "$OUT/invariants.txt"

  # I6, I8, I9 and I18 per census or per step, so every disagreement can be
  # read against the phase it happened in
  q "$DB" "SELECT 'I6 ' || fixture || ' [' || phase || '] revmap=' || b_revmap || ' items=' || b_items
             || ' unused=' || b_unused || CASE WHEN b_revmap = b_items THEN ' ok' ELSE ' DISAGREES' END
             FROM proto.census_v WHERE b_items IS NOT NULL
           UNION ALL
           SELECT 'I8 ' || fixture || ' [' || phase || '] meta(total=' || m_total || ', entry=' || m_entry
             || ', data=' || m_data || ', pending=' || m_pending || ') census(scanned=' || scanned
             || ', entry=' || c_entry || ', data=' || c_data || ', list=' || c_list
             || ', deleted=' || c_del || ', new=' || c_new || ', fsm=' || fsm || ')'
             || CASE WHEN m_entry = c_entry AND m_data = c_data + greatest(c_del - fsm, 0) AND m_total = scanned
                     THEN ' ok' ELSE ' differs' END
             FROM proto.census_v WHERE m_total IS NOT NULL
           UNION ALL
           SELECT 'I9 ' || v.fixture || ' [' || substring(v.tag from 9) || '] ' || coalesce(v.line, '?')
             || ' vacuum=' || v.vacuum_ran || ' bulkdelete=' || coalesce(v.scans_ran::text, '-')
             || coalesce(' total=' || v.num_pages || ' newly=' || v.newly || ' deleted=' || v.deleted
                         || ' free=' || v.free, '')
             || ' | before ' || coalesce(v.pre_phase, '-') || ' scanned=' || coalesce(pre.scanned::text, '-')
             || ' | after ' || coalesce(v.post_phase, '-') || ' scanned=' || coalesce(post.scanned::text, '-')
             || ' deleted=' || coalesce(post.c_del::text, '-') || ' new=' || coalesce(post.c_new::text, '-')
             || ' new_or_empty=' || coalesce(post.c_empty::text, '-') || ' fsm=' || coalesce(post.fsm::text, '-')
             FROM proto.vac_v v
             LEFT JOIN proto.census_v pre  ON pre.fixture  = v.fixture AND pre.phase  = v.pre_phase
             LEFT JOIN proto.census_v post ON post.fixture = v.fixture AND post.phase = v.post_phase
           UNION ALL
           SELECT 'I18 ' || fixture || ' [' || phase || '] ' || count(*) || ' regular pages: '
             || count(*) FILTER (WHERE fsm_read = fsm_expected) || ' agree, '
             || count(*) FILTER (WHERE fsm_read > fsm_expected) || ' higher, '
             || count(*) FILTER (WHERE fsm_read < fsm_expected) || ' lower, '
             || count(*) FILTER (WHERE evacuate) || ' flagged for evacuation'
             FROM proto.brin_page GROUP BY fixture, phase
           ORDER BY 1" > "$OUT/invariant-detail.txt"
  printf '    invariant detail lines: %s\n' "$(grep -c '' "$OUT/invariant-detail.txt")"

  q "$DB" "SELECT format('%-4s %-6s base=%s raw=%s maintained=%s rebuilt=%s truth=%s%% heap_relpages=%s heap_reltuples=%s',
             fixture, am, base_size, raw_size, maint_size, oracle_after, truth_pct, heap_relpages, heap_reltuples)
             FROM proto.score ORDER BY am, fixture" > "$OUT/phase-sizes.txt"
  q "$DB" "SELECT protocol || ' | ' || behavior || ' -> ' || fixture
             FROM proto.declared_coverage ORDER BY protocol, behavior" > "$OUT/coverage.txt"
  # Every census reading, as the census stored it: one row per fixture, phase
  # and metric.  The fixture database goes with the sandbox at clean, so this
  # file is where a reading that no other file prints - a hash index's
  # overflow pages and freed bitmap bits, a GiST index's leaf pages - survives.
  PSQL -d "$DB" -q -c "COPY (SELECT fixture, phase, metric, num, txt FROM proto.meas
                             ORDER BY fixture, phase, metric) TO STDOUT (FORMAT csv, HEADER)" \
    > "$OUT/meas.csv" || die "could not write $OUT/meas.csv"
  printf '    census readings: %s rows in meas.csv\n' "$(( $(grep -c '' "$OUT/meas.csv") - 1 ))"
  ! grep -q ' FAILS: ' "$OUT/invariants.txt" || die "a declared invariant failed (see $OUT/invariants.txt)"
}

# -------------------------------------------------------------- stage: probes
# Four mechanism probes.  None scores the method; each measures a fact the
# method or a protocol depends on.  They run after the oracle and the score.
stage_probes() {
  say "probes: who writes reltuples, the hash oracle, the GIN oracle, GiST builds"
  need_db; need_stage act
  q "$DB" "DROP SCHEMA IF EXISTS pr CASCADE" > /dev/null
  q "$DB" "CREATE SCHEMA pr" > /dev/null
  rt() {
    q "$DB" "SELECT format('%-34s table=%-8s hash=%-8s gin=%-8s gist=%-8s spgist=%-8s brin=%s', '$1',
               (SELECT reltuples FROM pg_class WHERE oid = 'pr.t1'::regclass),
               (SELECT reltuples FROM pg_class WHERE relname = 't1_hash'),
               (SELECT reltuples FROM pg_class WHERE relname = 't1_gin'),
               (SELECT reltuples FROM pg_class WHERE relname = 't1_gist'),
               (SELECT reltuples FROM pg_class WHERE relname = 't1_spgist'),
               (SELECT reltuples FROM pg_class WHERE relname = 't1_brin'))"
  }
  # P1: the table's reltuples - the tuple test's input - and each index's own,
  # after each writer in turn
  q "$DB" "CREATE TABLE pr.t1 (id bigint, k bigint, arr text[], r int8range, t text)
             WITH (autovacuum_enabled = off)" > /dev/null
  { printf -- '-- P1: reltuples after each writer, the table and one index per access method\n'
    rt 'CREATE TABLE'
    q "$DB" "INSERT INTO pr.t1 SELECT g, g, ARRAY['a'||g, 'b'||(g%1000)], int8range(g, g+10), 'x'||g
               FROM generate_series(1, 200000) g" > /dev/null
    rt 'INSERT 200,000 rows'
    qin "$DB" > "$OUT/probe-p1-build.log" 2>&1 <<'SQL'
CREATE INDEX t1_hash   ON pr.t1 USING hash   (k);
CREATE INDEX t1_gin    ON pr.t1 USING gin    (arr);
CREATE INDEX t1_gist   ON pr.t1 USING gist   (r);
CREATE INDEX t1_spgist ON pr.t1 USING spgist (t);
CREATE INDEX t1_brin   ON pr.t1 USING brin   (k) WITH (pages_per_range = 128);
SQL
    rt 'CREATE INDEX, five of them'
    printf 'ANALYZE pr.t1;\n' | qz "$DB" > "$OUT/probe-p1-analyze.log" 2>&1
    rt 'ANALYZE'
    q "$DB" "DELETE FROM pr.t1 WHERE id % 10 = 0" > /dev/null
    printf 'VACUUM pr.t1;\n' | qz "$DB" > "$OUT/probe-p1-vacuum.log" 2>&1
    rt 'DELETE 10 %, then VACUUM'
    q "$DB" "TRUNCATE pr.t1" > /dev/null
    rt 'TRUNCATE'
    q "$DB" "INSERT INTO pr.t1 SELECT g, g, ARRAY['a'||g, 'b'||(g%1000)], int8range(g, g+10), 'x'||g
               FROM generate_series(1, 200000) g" > /dev/null
    rt 'INSERT 200,000 rows again'
    q "$DB" "REINDEX INDEX pr.t1_hash" > /dev/null
    rt 'REINDEX INDEX the hash index'
    q "$DB" "SELECT 'heap blocks: ' || pg_relation_size('pr.t1') / current_setting('block_size')::int"
  } > "$OUT/probe-p1.txt" 2>&1
  cat "$OUT/probe-p1.txt"

  # P2: a hash rebuild is sized from the heap's estimate, not from the index
  local t i
  t=$(tbl h08); i=$(idx h08)
  { printf -- '\n-- P2: a hash rebuild is sized from the heap estimate (fixture h08)\n'
    printf 'heap relpages / reltuples: %s\n' "$(q "$DB" "SELECT relpages || ' / ' || reltuples FROM pg_class WHERE oid = '$t'::regclass")"
    q "$DB" "REINDEX INDEX $i" > /dev/null
    printf 'rebuilt at the true statistics: %s\n' "$(q "$DB" "SELECT pg_relation_size('$i')")"
    q "$DB" "UPDATE /* wiki_nbmaint_probe_forgery */ pg_class SET reltuples = 100 WHERE oid = '$t'::regclass" > /dev/null
    q "$DB" "REINDEX INDEX $i" > /dev/null
    printf 'rebuilt at reltuples = 100:     %s\n' "$(q "$DB" "SELECT pg_relation_size('$i')")"
    printf "ANALYZE %s;\n" "$t" | qz "$DB" > "$OUT/probe-p2-analyze.log" 2>&1
    q "$DB" "REINDEX INDEX $i" > /dev/null
    printf 'rebuilt after a fresh ANALYZE:  %s\n' "$(q "$DB" "SELECT pg_relation_size('$i')")"
  } > "$OUT/probe-p2.txt" 2>&1
  cat "$OUT/probe-p2.txt"

  # P3: the GIN oracle depends on the build's memory budget
  i=$(idx n04)
  { printf -- '\n-- P3: one GIN rebuild at three maintenance_work_mem values (fixture n04)\n'
    local mw
    for mw in 4MB 64MB 256MB; do
      printf "SET maintenance_work_mem = '%s';\nREINDEX INDEX %s;\n" "$mw" "$i" | qin "$DB" > /dev/null 2>&1
      printf 'maintenance_work_mem=%-6s rebuilt size=%s\n' "$mw" "$(q "$DB" "SELECT pg_relation_size('$i')")"
    done
  } > "$OUT/probe-p3.txt" 2>&1
  cat "$OUT/probe-p3.txt"

  # P4: which GiST operator class can take the sorted build at all
  { printf -- '\n-- P4: GIST_SORTSUPPORT_PROC (support function 11), per operator class the fixtures use\n'
    q "$DB" "SELECT opc.opcname || ': support 11 ' ||
               CASE WHEN EXISTS (SELECT 1 FROM pg_amproc ap WHERE ap.amprocfamily = opc.opcfamily
                                                           AND ap.amprocnum = 11)
                    THEN 'present, so the sorted build is possible'
                    ELSE 'absent, so the build is insert-driven' END
               FROM pg_opclass opc JOIN pg_am am ON am.oid = opc.opcmethod
              WHERE am.amname = 'gist' AND opc.opcname IN ('range_ops', 'point_ops') ORDER BY 1"
  } > "$OUT/probe-p4.txt" 2>&1
  cat "$OUT/probe-p4.txt"
}

# ---------------------------------------------------------------- stage: edge
# The comment handling, the ladder's boundaries, the candidate filters, and
# what step 2 does when another session holds a lock, edits a comment,
# rewrites a payload or renames an index while step 2 waits for its locks -
# case by case, in their own database.  Unscored: none is a bloat claim.
# Each case files what it expects before the texts run, and the stage prints
# expected against observed and fails the run on any difference.
edge_mk() {   # <table> <rows>: the build phase every edge table shares
  printf 'CREATE TABLE %s (id bigint, k bigint) WITH (autovacuum_enabled = off);\n' "$1"
  printf 'INSERT INTO %s SELECT g, g FROM generate_series(1, %s) g;\n' "$1" "$2"
  printf 'ANALYZE %s;\n' "$1"
  printf 'CREATE INDEX %s_i ON %s USING hash (k);\n' "$1" "$1"
}
edge_seen() {  # <round>: store step 1's rows through the view
  q "$EDB" "INSERT INTO proto.seen_plan (round, idx, action, notes)
              SELECT '$1', index_name, action, notes FROM proto.plan_v" > /dev/null
}
edge_snap() {  # <label>: every index's OID, file, size, table count and comment
  q "$EDB" "INSERT INTO proto.seen_cmt (label, idx, oid, filenode, bytes, tbl_tuples, cmt)
              SELECT '$1', c.relname, c.oid, c.relfilenode, pg_relation_size(c.oid),
                     t.reltuples::numeric, d.description
                FROM pg_class c JOIN pg_index x ON x.indexrelid = c.oid
                JOIN pg_class t ON t.oid = x.indrelid
                LEFT JOIN pg_description d ON d.objoid = c.oid
                      AND d.classoid = 'pg_class'::regclass AND d.objsubid = 0
               WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('i', 'I')" > /dev/null
}
edge_bg() {    # <tag> <sql...>: a background session, until edge_kill <tag>
  local tag=$1; shift
  printf '%s\n' "$@" | qbg "$EDB" > "$OUT/edge-bg-$tag.log" 2>&1 &
}
edge_kill() {
  q "$EDB" "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
             WHERE query LIKE '%wiki_nbmaint_edge_$1%' AND pid <> pg_backend_pid()" > /dev/null
  wait 2>/dev/null
}
edge_wait_lock() {  # <table> <mode> <granted>: poll until pg_locks shows it
  local n=0
  until [ "$(q "$EDB" "SELECT count(*) FROM pg_locks l JOIN pg_class c ON c.oid = l.relation
                         WHERE c.relname = '$1' AND l.mode = '$2' AND l.granted = $3")" -ge 1 ]; do
    n=$((n + 1)); [ "$n" -gt 200 ] && die "edge: no $2 (granted=$3) on $1 appeared"
    sleep 0.05
  done
}
# edge_during <round> <table> <sql>: run step 2 in the background, wait until
# it is queued for its SHARE lock on <table> - held off by a ROW EXCLUSIVE
# this function takes in another session first - then run <sql> as a third
# session, release the holder, and wait for step 2 to finish.  Step 2 waits
# up to its own lock_timeout of 5 s; the poll takes a few hundredths.
edge_during() {
  local round=$1 t=$2 sql=$3
  edge_bg "hold$round" "BEGIN;" "LOCK TABLE $t IN ROW EXCLUSIVE MODE;" \
    "SELECT /* wiki_nbmaint_edge_hold$round */ pg_sleep(300);" "COMMIT;"
  edge_wait_lock "$t" RowExclusiveLock true
  ( run_apply "$EDB" "edge$round" ) &
  local job=$!
  edge_wait_lock "$t" ShareLock false
  printf '%s\n' "$sql" | qin "$EDB" > "$OUT/edge-during-$round.log" 2>&1
  q "$EDB" "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
             WHERE query LIKE '%wiki_nbmaint_edge_hold$round%' AND pid <> pg_backend_pid()" > /dev/null
  wait "$job" || die "edge round $round: step 2 failed, see $OUT/apply-edge$round.log"
  wait 2>/dev/null
}
stage_edge() {
  say "edge: comments, boundaries, filters, locks, concurrent writers and the cap, case by case"
  need_texts
  q postgres "DROP DATABASE IF EXISTS $EDB" > /dev/null
  q postgres "DROP ROLE IF EXISTS nbmaint_other" > /dev/null
  q postgres "CREATE DATABASE $EDB" > /dev/null
  q postgres "CREATE ROLE nbmaint_other NOLOGIN" > /dev/null
  {
    printf 'CREATE SCHEMA proto;\n'
    printf 'CREATE TABLE proto.expect (round text, idx text, want text, human text, PRIMARY KEY (round, idx));\n'
    printf 'CREATE TABLE proto.seen_plan (round text, idx text, action text, notes text);\n'
    printf 'CREATE TABLE proto.seen_cmt (label text, idx text, oid oid, filenode oid, bytes bigint, tbl_tuples numeric, cmt text);\n'
    # the comment with its one reserved line's content cut out, newlines kept;
    # how many reserved lines it has; and whether that line is exactly the
    # version-2 grammar with sz and tup equal to the file and the table count
    printf '%s\n' "CREATE FUNCTION proto.human(c text) RETURNS text LANGUAGE sql IMMUTABLE AS
      \$f\$ SELECT regexp_replace(c, '^@nbmaint:\{.*\}\$', '', 'n') \$f\$;"
    printf '%s\n' "CREATE FUNCTION proto.nres(c text) RETURNS bigint LANGUAGE sql IMMUTABLE AS
      \$f\$ SELECT count(*) FROM regexp_matches(coalesce(c, ''), '^@nbmaint:\{.*\}\$', 'gn') \$f\$;"
    printf '%s\n' "CREATE FUNCTION proto.valid(c text, b numeric, t numeric) RETURNS boolean LANGUAGE sql IMMUTABLE AS
      \$f\$ SELECT coalesce((regexp_match(c, '(?n)^@nbmaint:\{\"v\":2,\"sz\":([0-9]+),\"tup\":(-?[0-9]+),\"at\":\"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}[+-][0-9]{2}(?::[0-9]{2})?\"\}\$'))[1]::numeric = b
                         AND (regexp_match(c, '(?n)^@nbmaint:\{\"v\":2,\"sz\":([0-9]+),\"tup\":(-?[0-9]+),'))[2]::numeric
                             = round(greatest(t, -1)), false) \$f\$;"
    local e
    for e in e_none e_human e_v1 e_bad e_junk e_nest e_dup e_two e_prose e_trail e_tailnl \
             e_mid e_shrink e_sz e_zero e_owner e_busy e_surv e_hold e_cedit e_cpay e_ren; do
      edge_mk "$e" 30000
    done
    edge_mk e_t13 13000
    edge_mk e_t7 7000
    edge_mk e_capok 5000
    printf 'CREATE INDEX e_sz_i2 ON e_sz USING hash (id);\n'
    printf 'CREATE INDEX e_t13_i2 ON e_t13 USING hash (id);\n'
    printf 'CREATE INDEX e_t7_i2 ON e_t7 USING hash (id);\n'
    # round G's rebuild that will fail: an expression index over an immutable
    # function that is later replaced by one that divides by zero
    printf "CREATE FUNCTION e_fail_f(bigint) RETURNS bigint LANGUAGE sql IMMUTABLE AS 'SELECT \$1';\n"
    printf 'CREATE TABLE e_capfail (id bigint, k bigint) WITH (autovacuum_enabled = off);\n'
    printf 'INSERT INTO e_capfail SELECT g, g FROM generate_series(1, 60000) g;\n'
    printf 'ANALYZE e_capfail;\n'
    printf 'CREATE INDEX e_capfail_i ON e_capfail USING hash (e_fail_f(k));\n'
    printf 'CREATE TABLE e_ren2 (id bigint, k bigint) WITH (autovacuum_enabled = off);\n'
    printf 'INSERT INTO e_ren2 SELECT g, g FROM generate_series(1, 30000) g;\n'
    printf 'ANALYZE e_none, e_human, e_v1, e_bad, e_junk, e_nest, e_dup, e_two, e_prose, e_trail, e_tailnl, e_mid, e_shrink, e_sz, e_zero, e_owner, e_busy, e_surv, e_hold, e_cedit, e_cpay, e_ren, e_ren2, e_t13, e_t7, e_capok, e_capfail;\n'
    # an index built on an empty table that nothing has counted
    printf 'CREATE TABLE e_unk (id bigint, k bigint) WITH (autovacuum_enabled = off);\n'
    printf 'CREATE INDEX e_unk_i ON e_unk USING hash (k);\n'
    # three indexes the filters must keep out
    printf 'CREATE TABLE e_btree (id bigint, k bigint);\nINSERT INTO e_btree SELECT g, g FROM generate_series(1, 30000) g;\n'
    printf 'CREATE INDEX e_btree_i ON e_btree (k);\n'
    printf 'CREATE TABLE e_invalid (id bigint, k bigint);\nINSERT INTO e_invalid SELECT g, g FROM generate_series(1, 1000) g;\n'
    printf 'CREATE TABLE e_part (k bigint) PARTITION BY RANGE (k);\n'
    printf 'CREATE TABLE e_part_1 PARTITION OF e_part FOR VALUES FROM (0) TO (100000);\n'
    printf 'INSERT INTO e_part SELECT g FROM generate_series(1, 30000) g;\n'
    printf 'CREATE INDEX e_part_i ON e_part USING hash (k);\n'
    printf 'ANALYZE e_part_1;\n'
    # the comments round A reads
    printf "COMMENT ON INDEX e_human_i IS E'Search index used by the application.\\\\nSecond line: an @ sign, a { and a } brace.\\\\n  \\\\n';\n"
    printf "COMMENT ON INDEX e_v1_i IS E'keep me\\\\n@nbmaint:{\"v\":1,\"sz\":123,\"tup\":456,\"at\":\"2020-01-01T00:00:00+00\"}';\n"
    printf "COMMENT ON INDEX e_bad_i IS '@nbmaint:{\"v\":2,\"sz\":\"big\",\"tup\":1,\"at\":\"x\"}';\n"
    printf "COMMENT ON INDEX e_junk_i IS E'above\\\\n@nbmaint: not json\\\\nbelow';\n"
    printf "COMMENT ON INDEX e_nest_i IS '@nbmaint:{\"x\":{\"v\":2,\"sz\":100,\"tup\":5}}';\n"
    printf "COMMENT ON INDEX e_dup_i IS '@nbmaint:{\"v\":2,\"sz\":1,\"tup\":1,\"at\":\"2026-01-01T00:00:00+00\",\"sz\":999}';\n"
    printf "COMMENT ON INDEX e_two_i IS E'@nbmaint:{\"v\":2,\"sz\":1,\"tup\":1,\"at\":\"2026-01-01T00:00:00+00\"}\\\\nhuman\\\\n@nbmaint:{\"v\":2,\"sz\":1,\"tup\":1,\"at\":\"2026-01-01T00:00:00+00\"}';\n"
    printf "COMMENT ON INDEX e_prose_i IS 'see @nbmaint:{\"v\":2,\"sz\":1,\"tup\":1,\"at\":\"2026-01-01T00:00:00+00\"} for the format';\n"
    printf "COMMENT ON INDEX e_trail_i IS E'human text  \\\\n\\\\n';\n"
    printf "COMMENT ON INDEX e_tailnl_i IS E'note\\\\n@nbmaint:{\"v\":1,\"sz\":1,\"tup\":1}\\\\n';\n"
    printf "COMMENT ON INDEX e_surv_i IS 'kept through both rebuilds';\n"
  } > "$SQLD/edge-build.sql"
  qz "$EDB" < "$SQLD/edge-build.sql" > "$OUT/edge-build.log" 2>&1
  # a CREATE INDEX CONCURRENTLY that fails on one row leaves an invalid index
  printf 'CREATE INDEX CONCURRENTLY e_invalid_i ON e_invalid USING hash ((1 / (k - 500)));\n' \
    | qe "$EDB" > "$OUT/edge-invalid.log" 2>&1
  qf "$EDB" "$SQLD/plan_view.sql" > /dev/null 2>&1

  # ---- round A: first run, every comment shape
  qin "$EDB" > "$OUT/edge-expect-A.log" 2>&1 <<'SQL'
INSERT INTO proto.expect (round, idx, want, human) VALUES
 ('A','e_none_i','initialize',''),
 ('A','e_human_i','initialize',E'Search index used by the application.\nSecond line: an @ sign, a { and a } brace.\n  \n\n'),
 ('A','e_v1_i','initialize',E'keep me\n'),
 ('A','e_bad_i','initialize',''),
 ('A','e_junk_i','initialize',E'above\n@nbmaint: not json\nbelow\n'),
 ('A','e_nest_i','initialize',''),
 ('A','e_dup_i','initialize',''),
 ('A','e_two_i','conflict',E'@nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"}\nhuman\n@nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"}'),
 ('A','e_prose_i','initialize',E'see @nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"} for the format\n'),
 ('A','e_trail_i','initialize',E'human text  \n\n\n'),
 ('A','e_tailnl_i','initialize',E'note\n\n'),
 ('A','e_mid_i','initialize',''),('A','e_shrink_i','initialize',''),
 ('A','e_sz_i','initialize',''),('A','e_sz_i2','initialize',''),
 ('A','e_t13_i','initialize',''),('A','e_t13_i2','initialize',''),
 ('A','e_t7_i','initialize',''),('A','e_t7_i2','initialize',''),
 ('A','e_zero_i','initialize',''),('A','e_owner_i','initialize',''),
 ('A','e_busy_i','initialize',''),('A','e_surv_i','initialize',E'kept through both rebuilds\n'),
 ('A','e_hold_i','initialize',''),('A','e_cedit_i','initialize',''),
 ('A','e_cpay_i','initialize',''),('A','e_ren_i','initialize',''),
 ('A','e_capok_i','initialize',''),('A','e_capfail_i','initialize',''),
 ('A','e_unk_i','initialize',''),('A','e_part_1_k_idx','initialize',''),
 ('A','e_btree_i','absent',''),('A','e_invalid_i','absent',''),('A','e_part_i','absent','');
SQL
  run_plan "$EDB" edgeA || die "edge round A: step 1 failed"
  edge_seen A
  edge_snap A-before
  run_apply "$EDB" edgeA || die "edge round A: step 2 failed"
  edge_snap A-after

  # ---- round B: forged payloads on the boundaries, one lock held elsewhere
  qin "$EDB" > "$OUT/edge-forge.log" 2>&1 <<'SQL'
CREATE FUNCTION proto.forge(p_idx text, p_before text, p_after text, p_sz numeric, p_tup numeric)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  EXECUTE format('COMMENT ON INDEX %I IS %L', p_idx,
    CASE WHEN p_before <> '' THEN p_before || E'\n' ELSE '' END
    || '@nbmaint:{"v":2,"sz":' || p_sz || ',"tup":' || p_tup || ',"at":"2026-01-01T00:00:00+00"}'
    || CASE WHEN p_after <> '' THEN E'\n' || p_after ELSE '' END);
END $fn$;
CREATE FUNCTION proto.cur(p_idx text) RETURNS numeric LANGUAGE sql AS
  $fn$ SELECT pg_relation_size(p_idx::regclass)::numeric $fn$;
CREATE FUNCTION proto.curtup(p_idx text) RETURNS numeric LANGUAGE sql AS
  $fn$ SELECT round(greatest(t.reltuples::numeric, -1)) FROM pg_index x
         JOIN pg_class t ON t.oid = x.indrelid WHERE x.indexrelid = p_idx::regclass $fn$;
SELECT proto.forge('e_mid_i',    'above', 'below', floor(proto.cur('e_mid_i') / 2),       proto.curtup('e_mid_i'));
SELECT proto.forge('e_shrink_i', '', '',           proto.cur('e_shrink_i') * 2,           proto.curtup('e_shrink_i'));
SELECT proto.forge('e_sz_i',     '', '',           floor(proto.cur('e_sz_i') / 1.30),     proto.curtup('e_sz_i'));
SELECT proto.forge('e_sz_i2',    '', '',           floor(proto.cur('e_sz_i2') / 1.30) + 1, proto.curtup('e_sz_i2'));
SELECT proto.forge('e_t13_i',    '', '',           proto.cur('e_t13_i'),  10000);
SELECT proto.forge('e_t13_i2',   '', '',           proto.cur('e_t13_i2'), 10001);
SELECT proto.forge('e_t7_i',     '', '',           proto.cur('e_t7_i'),   10000);
SELECT proto.forge('e_t7_i2',    '', '',           proto.cur('e_t7_i2'),  9999);
SELECT proto.forge('e_zero_i',   '', '',           proto.cur('e_zero_i'), 0);
SELECT proto.forge('e_busy_i',   '', '',           floor(proto.cur('e_busy_i') / 2), proto.curtup('e_busy_i'));
INSERT INTO e_unk SELECT g, g FROM generate_series(1, 10) g;
INSERT INTO proto.expect (round, idx, want, human) VALUES
 ('B','e_mid_i','reindex',E'above\n\nbelow'),
 ('B','e_shrink_i','refresh',''),
 ('B','e_sz_i','reindex',''),('B','e_sz_i2','skip',''),
 ('B','e_t13_i','reindex',''),('B','e_t13_i2','skip',''),
 ('B','e_t7_i','reindex',''),('B','e_t7_i2','skip',''),
 ('B','e_zero_i','reindex',''),
 ('B','e_busy_i','reindex',''),
 ('B','e_unk_i','skip',''),
 ('B','e_none_i','skip',''),('B','e_v1_i','skip',E'keep me\n'),
 ('B','e_human_i','skip',E'Search index used by the application.\nSecond line: an @ sign, a { and a } brace.\n  \n\n'),
 ('B','e_bad_i','skip',''),('B','e_junk_i','skip',E'above\n@nbmaint: not json\nbelow\n'),
 ('B','e_nest_i','skip',''),('B','e_dup_i','skip',''),
 ('B','e_two_i','conflict',E'@nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"}\nhuman\n@nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"}'),
 ('B','e_prose_i','skip',E'see @nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"} for the format\n'),
 ('B','e_trail_i','skip',E'human text  \n\n\n'),('B','e_tailnl_i','skip',E'note\n\n'),
 ('B','e_owner_i','skip',''),('B','e_surv_i','skip',E'kept through both rebuilds\n'),
 ('B','e_hold_i','skip',''),('B','e_cedit_i','skip',''),('B','e_cpay_i','skip',''),
 ('B','e_ren_i','skip',''),('B','e_capok_i','skip',''),('B','e_capfail_i','skip',''),
 ('B','e_part_1_k_idx','skip','');
SQL
  edge_bg holder "BEGIN;" "LOCK TABLE e_busy IN ROW EXCLUSIVE MODE;" \
    "SELECT /* wiki_nbmaint_edge_holder */ pg_sleep(300);" "COMMIT;"
  edge_wait_lock e_busy RowExclusiveLock true
  run_plan "$EDB" edgeB || die "edge round B: step 1 failed"
  edge_seen B
  edge_snap B-before
  run_apply "$EDB" edgeB || die "edge round B: step 2 failed"
  edge_snap B-after
  edge_kill holder

  # ---- round C: the lock is gone, so the skipped rebuild happens; then a
  # settled database: a further run writes nothing
  run_apply "$EDB" edgeC1 || die "edge round C: step 2 failed"
  edge_snap C1-after
  run_apply "$EDB" edgeC2 || die "edge round C: step 2, second run, failed"
  edge_snap C2-after

  # ---- round D: a role that owns none of the indexes
  run_plan "$EDB" edgeD 'SET ROLE nbmaint_other;' || die "edge round D: step 1 failed"
  edge_snap D-before
  run_apply "$EDB" edgeD 'SET ROLE nbmaint_other;' || die "edge round D: step 2 failed"
  edge_snap D-after

  # ---- round E: the comment survives both REINDEX forms
  edge_snap E-before
  q "$EDB" "REINDEX INDEX e_surv_i" > /dev/null
  edge_snap E-plain
  q "$EDB" "REINDEX INDEX CONCURRENTLY e_surv_i" > /dev/null
  edge_snap E-concurrent
  run_plan "$EDB" edgeE || die "edge round E: step 1 failed"
  edge_seen E

  # ---- round F: another session's temporary index is never a candidate
  edge_bg temp "CREATE TEMP TABLE e_tmp (k bigint);" \
    "INSERT INTO e_tmp SELECT g FROM generate_series(1, 1000) g;" \
    "CREATE INDEX e_tmp_i ON e_tmp USING hash (k);" \
    "SELECT /* wiki_nbmaint_edge_temp */ pg_sleep(300);"
  local n=0
  until [ "$(q "$EDB" "SELECT count(*) FROM pg_class WHERE relname = 'e_tmp_i'")" = 1 ]; do
    n=$((n + 1)); [ "$n" -gt 60 ] && die "edge: the temporary index never appeared"; sleep 0.5
  done
  run_plan "$EDB" edgeF || die "edge round F: step 1 failed"
  edge_seen F
  run_apply "$EDB" edgeF || die "edge round F: step 2 failed"
  edge_kill temp

  # ---- round H: another session holds ACCESS EXCLUSIVE on one index for the
  # whole run: step 1, one statement, is cancelled by its lock_timeout; step 2
  # counts that index failed and finishes every other one
  edge_snap H-before
  edge_bg hold "BEGIN;" "REINDEX INDEX e_hold_i;" \
    "SELECT /* wiki_nbmaint_edge_hold */ pg_sleep(300);" "COMMIT;"
  edge_wait_lock e_hold_i AccessExclusiveLock true
  local rc_h1
  run_plan "$EDB" edgeH; rc_h1=$?
  run_apply "$EDB" edgeH || die "edge round H: step 2 failed"
  edge_kill hold
  edge_snap H-after

  # ---- round I: a person rewrites the comment while step 2 waits for its
  # table lock; step 2 re-reads it under its locks and keeps the new text
  q "$EDB" "SELECT proto.forge('e_cedit_i', 'old human text', '', proto.cur('e_cedit_i') * 2,
                               proto.curtup('e_cedit_i'))" > /dev/null
  edge_snap I-before
  edge_during I e_cedit "SELECT format('COMMENT /* wiki_nbmaint_edge_edit */ ON INDEX e_cedit_i IS %L',
                           E'new human text, written while step 2 waited\n'
                           || substring(description from '(?n)^(@nbmaint:\{.*\})\$'))
                           FROM pg_description WHERE objoid = 'e_cedit_i'::regclass
                         \\gexec"
  edge_snap I-after

  # ---- round J: another run rewrites the payload to the file's true size
  # while step 2 waits; step 2's second read under the locks says skip
  q "$EDB" "SELECT proto.forge('e_cpay_i', '', '', floor(proto.cur('e_cpay_i') / 2),
                               proto.curtup('e_cpay_i'))" > /dev/null
  edge_snap J-before
  edge_during J e_cpay "SELECT proto.forge('e_cpay_i', '', '', proto.cur('e_cpay_i'), proto.curtup('e_cpay_i'));"
  edge_snap J-after

  # ---- round K: the index is renamed, and a new index takes its name, while
  # step 2 waits; step 2 finds the name no longer names the index it read
  q "$EDB" "SELECT proto.forge('e_ren_i', '', '', floor(proto.cur('e_ren_i') / 2),
                               proto.curtup('e_ren_i'))" > /dev/null
  edge_snap K-before
  edge_during K e_ren "ALTER INDEX e_ren_i RENAME TO e_ren_i_old;
                       CREATE INDEX e_ren_i ON e_ren2 USING hash (k);"
  edge_snap K-after
  run_apply "$EDB" edgeK2 || die "edge round K: the settling run of step 2 failed"
  edge_snap K2-after

  # ---- round G: max_reindex 1, and the first rebuild fails.  Step 2 runs with
  # one documented edit, that cap; the failed rebuild uses up the cap, so the
  # next index due is capped instead of rebuilt
  sed 's/^    max_reindex integer := 1000;   -- cap on the rebuilds one run may start$/    max_reindex integer := 1;      -- cap on the rebuilds one run may start/' \
    "$SQLD/apply.sql" > "$SQLD/apply-cap1.sql"
  [ "$(diff "$SQLD/apply.sql" "$SQLD/apply-cap1.sql" | grep -c '^[<>]')" = 2 ] \
    || die "edge round G: the documented edit did not change exactly one line"
  q "$EDB" "CREATE OR REPLACE FUNCTION e_fail_f(bigint) RETURNS bigint LANGUAGE sql IMMUTABLE AS
              'SELECT 1 / (\$1 - \$1)'" > /dev/null
  q "$EDB" "SELECT proto.forge('e_capfail_i', '', '', floor(proto.cur('e_capfail_i') / 2), proto.curtup('e_capfail_i')),
                   proto.forge('e_capok_i', '', '', floor(proto.cur('e_capok_i') / 2), proto.curtup('e_capok_i'))" > /dev/null
  edge_snap G-before
  APPLY_FILE="$SQLD/apply-cap1.sql" run_apply "$EDB" edgeG || die "edge round G: step 2 failed"
  edge_snap G-after

  # ---- the verdicts
  qat "$EDB" /dev/stdin > "$OUT/edge.txt" 2>&1 <<'SQL'
WITH pa AS (
  SELECT e.round, e.idx, e.want,
         coalesce((SELECT s.action FROM proto.seen_plan s WHERE s.round = e.round AND s.idx = e.idx), 'absent') AS seen
    FROM proto.expect e
)
SELECT format('plan %-2s %-16s want=%-10s seen=%-10s %s', round, idx, want, seen,
              CASE WHEN want = seen THEN 'ok' ELSE 'DIFFERS' END)
  FROM pa ORDER BY round, idx;
SQL
  qat "$EDB" /dev/stdin >> "$OUT/edge.txt" 2>&1 <<'SQL'
-- every comment step 2 wrote in round A: the human text byte for byte where
-- it was, exactly one reserved line, and a version-2 payload whose sz and
-- tup are the file and the table count; a conflict left exactly as it was
WITH b AS (SELECT * FROM proto.seen_cmt WHERE label = 'A-before'),
     a AS (SELECT * FROM proto.seen_cmt WHERE label = 'A-after'),
     e AS (SELECT * FROM proto.expect WHERE round = 'A' AND want <> 'absent')
SELECT format('write A %-15s %s', e.idx,
         CASE WHEN e.want = 'conflict' THEN
                CASE WHEN a.cmt = b.cmt AND a.cmt = e.human AND a.filenode = b.filenode
                     THEN 'ok (untouched)' ELSE 'DIFFERS: ' || coalesce(a.cmt, '<none>') END
              WHEN proto.human(a.cmt) = e.human AND proto.nres(a.cmt) = 1
                   AND proto.valid(a.cmt, a.bytes, a.tbl_tuples) AND a.filenode = b.filenode THEN 'ok'
              ELSE 'DIFFERS: ' || coalesce(replace(a.cmt, E'\n', '\n'), '<none>') END)
  FROM e JOIN a ON a.idx = e.idx JOIN b ON b.idx = e.idx
 ORDER BY e.idx;
SQL
  qat "$EDB" /dev/stdin >> "$OUT/edge.txt" 2>&1 <<'SQL'
-- round B: a rebuild changes the file and rewrites the payload in place; a
-- refresh rewrites the payload only; a skip changes nothing; the locked
-- table's index keeps its file and its forged payload
WITH b AS (SELECT * FROM proto.seen_cmt WHERE label = 'B-before'),
     a AS (SELECT * FROM proto.seen_cmt WHERE label = 'B-after'),
     e AS (SELECT * FROM proto.expect WHERE round = 'B')
SELECT format('write B %-15s want=%-8s %s', e.idx, e.want,
         CASE WHEN e.idx = 'e_busy_i' THEN
                CASE WHEN a.filenode = b.filenode AND a.cmt = b.cmt THEN 'ok (lock timed out, nothing written)' ELSE 'DIFFERS' END
              WHEN e.want = 'reindex' THEN
                CASE WHEN a.filenode <> b.filenode AND proto.human(a.cmt) = e.human
                          AND proto.human(a.cmt) = proto.human(b.cmt) AND proto.nres(a.cmt) = 1
                          AND proto.valid(a.cmt, a.bytes, a.tbl_tuples) THEN 'ok' ELSE 'DIFFERS' END
              WHEN e.want = 'refresh' THEN
                CASE WHEN a.filenode = b.filenode AND a.cmt <> b.cmt AND proto.human(a.cmt) = proto.human(b.cmt)
                          AND proto.valid(a.cmt, a.bytes, a.tbl_tuples) THEN 'ok' ELSE 'DIFFERS' END
              ELSE CASE WHEN a.filenode = b.filenode AND a.cmt IS NOT DISTINCT FROM b.cmt
                             AND (e.want = 'conflict' AND a.cmt = e.human OR proto.human(a.cmt) = e.human)
                        THEN 'ok' ELSE 'DIFFERS' END
         END)
  FROM e JOIN a ON a.idx = e.idx JOIN b ON b.idx = e.idx
 ORDER BY e.idx;
SQL
  # the run-level verdicts: each line states what it expected and ends in ok
  # or DIFFERS
  verdict() {   # <label> <expected> <observed>
    printf 'run    %-62s want=[%s] seen=[%s] %s\n' "$1" "$2" "$3" "$([ "$2" = "$3" ] && echo ok || echo DIFFERS)"
  }
  summary() { apply_summary "$1" | sed 's/^nbmaint: //'; }
  unchanged() {  # <index> <label before> <label after>: file and comment both unchanged
    q "$EDB" "SELECT coalesce(bool_and(a.cmt IS NOT DISTINCT FROM b.cmt AND a.filenode = b.filenode), false)
                FROM proto.seen_cmt a JOIN proto.seen_cmt b ON b.idx = a.idx
               WHERE a.idx = '$1' AND b.label = '$2' AND a.label = '$3'"
  }
  local ncand
  ncand=$(q "$EDB" "SELECT count(*) FROM proto.expect WHERE round = 'A' AND want <> 'absent'")
  {
    verdict 'A: step 2 counts' \
      "reindex=0 initialize=$((ncand - 1)) refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=0 changed=0 dry_run=f" \
      "$(summary edgeA)"
    verdict 'B: step 2 counts, one rebuild refused by the lock' \
      'reindex=5 initialize=0 refresh=1 blocked=0 conflict=1 failed=1 gone=0 capped=0 started=5 changed=0 dry_run=f' \
      "$(summary edgeB)"
    verdict 'B: the refused rebuild is a lock timeout, SQLSTATE 55P03' 'e_busy_i 55P03' \
      "$(grep -Eo 'nbmaint: e_busy_i: nothing written: .*SQLSTATE [0-9A-Z]+' "$OUT/apply-edgeB.log" \
           | sed -E 's/^nbmaint: (e_busy_i):.*SQLSTATE ([0-9A-Z]+)$/\1 \2/')"
    verdict 'C1: the lock is gone, so the refused rebuild happens' \
      'reindex=1 initialize=0 refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=1 changed=0 dry_run=f' \
      "$(summary edgeC1)"
    verdict 'C2: a settled database: nothing to do' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=0 changed=0 dry_run=f' \
      "$(summary edgeC2)"
    verdict 'C2: every comment and every file unchanged by that run' 't' \
      "$(q "$EDB" "SELECT bool_and(a.cmt IS NOT DISTINCT FROM b.cmt AND a.filenode = b.filenode)
                     FROM proto.seen_cmt a JOIN proto.seen_cmt b ON b.idx = a.idx
                    WHERE a.label = 'C2-after' AND b.label = 'C1-after'")"
    verdict 'D: step 1 as a role that owns nothing: every row blocked' "$ncand blocked, 0 other" \
      "$(grep -Ec '\| blocked +\|' "$OUT/plan-edgeD.txt") blocked, $(grep -Ec '\| (initialize|refresh|reindex|skip|conflict) +\|' "$OUT/plan-edgeD.txt") other"
    verdict 'D: step 2 as that role' \
      "reindex=0 initialize=0 refresh=0 blocked=$ncand conflict=0 failed=0 gone=0 capped=0 started=0 changed=0 dry_run=f" \
      "$(summary edgeD)"
    verdict 'D: nothing written by it' 't' \
      "$(q "$EDB" "SELECT bool_and(a.cmt IS NOT DISTINCT FROM b.cmt AND a.filenode = b.filenode)
                     FROM proto.seen_cmt a JOIN proto.seen_cmt b ON b.idx = a.idx
                    WHERE a.label = 'D-after' AND b.label = 'D-before'")"
    verdict 'E: REINDEX keeps OID and comment, gives a new file' 'same oid, new file, same comment' \
      "$(q "$EDB" "SELECT CASE WHEN p.oid = b.oid THEN 'same oid' ELSE 'new oid' END || ', ' ||
                          CASE WHEN p.filenode <> b.filenode THEN 'new file' ELSE 'same file' END || ', ' ||
                          CASE WHEN p.cmt = b.cmt THEN 'same comment' ELSE 'changed comment' END
                     FROM proto.seen_cmt b, proto.seen_cmt p
                    WHERE b.idx = 'e_surv_i' AND b.label = 'E-before'
                      AND p.idx = 'e_surv_i' AND p.label = 'E-plain'")"
    verdict 'E: REINDEX CONCURRENTLY moves the comment to a new OID' 'new oid, same comment' \
      "$(q "$EDB" "SELECT CASE WHEN c.oid = b.oid THEN 'same oid' ELSE 'new oid' END || ', ' ||
                          CASE WHEN c.cmt = b.cmt THEN 'same comment' ELSE 'changed comment' END
                     FROM proto.seen_cmt b, proto.seen_cmt c
                    WHERE b.idx = 'e_surv_i' AND b.label = 'E-before'
                      AND c.idx = 'e_surv_i' AND c.label = 'E-concurrent'")"
    verdict 'E: step 1 after both rebuilds of an unchanged table' 'skip' \
      "$(q "$EDB" "SELECT action FROM proto.seen_plan WHERE round = 'E' AND idx = 'e_surv_i'")"
    verdict 'F: rows naming another session'"'"'s temporary index' '0' \
      "$(q "$EDB" "SELECT count(*) FROM proto.seen_plan WHERE round = 'F' AND idx = 'e_tmp_i'")"
    verdict 'F: step 2 passes it by without counting it' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=0 changed=0 dry_run=f' \
      "$(summary edgeF)"
    verdict 'H: step 1 under a lock held on one index is cancelled' 'exit 3, canceling statement due to lock timeout' \
      "exit $rc_h1, $(grep -Eo 'canceling statement due to lock timeout' "$OUT/plan-edgeH.txt" | head -1)"
    verdict 'H: step 2 counts that index failed and finishes the others' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=1 gone=0 capped=0 started=0 changed=0 dry_run=f' \
      "$(summary edgeH)"
    verdict 'H: the failure is a lock timeout on that index' 'e_hold_i 55P03' \
      "$(grep -Eo 'nbmaint: e_hold_i: nothing written: .*SQLSTATE [0-9A-Z]+' "$OUT/apply-edgeH.log" \
           | sed -E 's/^nbmaint: (e_hold_i):.*SQLSTATE ([0-9A-Z]+)$/\1 \2/')"
    verdict 'H: nothing written to it' 't' "$(unchanged e_hold_i H-before H-after)"
    verdict 'I: step 2 refreshes the index that waited' \
      'reindex=0 initialize=0 refresh=1 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=0 changed=0 dry_run=f' \
      "$(summary edgeI)"
    verdict 'I: the text written while it waited is the text kept' 't' \
      "$(q "$EDB" "SELECT proto.human(cmt) = E'new human text, written while step 2 waited\n'
                          AND proto.nres(cmt) = 1 AND proto.valid(cmt, bytes, tbl_tuples)
                     FROM proto.seen_cmt WHERE idx = 'e_cedit_i' AND label = 'I-after'")"
    verdict 'J: the decision is taken again under the locks' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=0 changed=1 dry_run=f' \
      "$(summary edgeJ)"
    verdict 'J: reindex before the locks, skip under them' 'e_cpay_i reindex skip' \
      "$(grep -Eo 'nbmaint: public\.e_cpay_i was [a-z]+ before the locks and [a-z]+ under them' "$OUT/apply-edgeJ.log" \
           | sed -E 's/^nbmaint: public\.(e_cpay_i) was ([a-z]+) before the locks and ([a-z]+) under them$/\1 \2 \3/')"
    verdict 'J: no rebuild, and the comment is the one written meanwhile' 't' \
      "$(q "$EDB" "SELECT a.filenode = b.filenode AND a.cmt <> b.cmt AND proto.valid(a.cmt, a.bytes, a.tbl_tuples)
                          AND a.cmt ~ '\"at\":\"2026-01-01T00:00:00\+00\"'
                     FROM proto.seen_cmt a JOIN proto.seen_cmt b ON b.idx = a.idx
                    WHERE a.idx = 'e_cpay_i' AND b.label = 'J-before' AND a.label = 'J-after'")"
    verdict 'K: the renamed index is refused, and nothing else is touched' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=1 gone=0 capped=0 started=0 changed=0 dry_run=f' \
      "$(summary edgeK)"
    verdict 'K: the refusal names it under its new name, SQLSTATE 55000' 'e_ren_i_old 55000' \
      "$(grep -Eo 'nbmaint: e_ren_i_old: nothing written: renamed, dropped or re-created since it was read .SQLSTATE [0-9A-Z]+' "$OUT/apply-edgeK.log" \
           | sed -E 's/^nbmaint: (e_ren_i_old):.*SQLSTATE ([0-9A-Z]+)$/\1 \2/')"
    verdict 'K: the renamed index keeps its file and comment' 't' \
      "$(q "$EDB" "SELECT a.filenode = b.filenode AND a.cmt = b.cmt
                     FROM proto.seen_cmt a JOIN proto.seen_cmt b ON b.oid = a.oid
                    WHERE b.idx = 'e_ren_i' AND b.label = 'K-before' AND a.label = 'K-after'")"
    verdict 'K: the index that took the name was never written' 't' \
      "$(q "$EDB" "SELECT cmt IS NULL FROM proto.seen_cmt WHERE idx = 'e_ren_i' AND label = 'K-after'")"
    verdict 'K2: the next run rebuilds one and initializes the other' \
      'reindex=1 initialize=1 refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=1 changed=0 dry_run=f' \
      "$(summary edgeK2)"
    verdict 'G: a failed rebuild uses up max_reindex 1' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=1 gone=0 capped=1 started=1 changed=0 dry_run=f' \
      "$(summary edgeG)"
    verdict 'G: the failure is the rebuild itself, SQLSTATE 22012' 'e_capfail_i 22012' \
      "$(grep -Eo 'nbmaint: e_capfail_i: nothing written: .*SQLSTATE [0-9A-Z]+' "$OUT/apply-edgeG.log" \
           | sed -E 's/^nbmaint: (e_capfail_i):.*SQLSTATE ([0-9A-Z]+)$/\1 \2/')"
    verdict 'G: the next index due is capped, not rebuilt' 'e_capok_i capped, t t' \
      "$(grep -Eo 'nbmaint: public\.e_capok_i needs a rebuild, max_reindex 1 reached' "$OUT/apply-edgeG.log" \
           | sed -E 's/^nbmaint: public\.(e_capok_i) needs.*$/\1 capped/'), $(unchanged e_capok_i G-before G-after) $(unchanged e_capfail_i G-before G-after)"
    q "$EDB" "SELECT format('info   E %-11s oid=%s filenode=%s comment_md5=%s', label, oid, filenode, md5(cmt))
               FROM proto.seen_cmt WHERE idx = 'e_surv_i' AND label IN ('E-before','E-plain','E-concurrent')
              ORDER BY CASE label WHEN 'E-before' THEN 1 WHEN 'E-plain' THEN 2 ELSE 3 END"
    q "$EDB" "SELECT 'info   B e_unk_i notes: ' || notes FROM proto.seen_plan WHERE round = 'B' AND idx = 'e_unk_i'"
    q "$EDB" "SELECT 'info   B e_t13_i and e_t7_i notes: ' || string_agg(idx || ': ' || notes, '; ' ORDER BY idx)
               FROM proto.seen_plan WHERE round = 'B' AND idx IN ('e_t13_i','e_t13_i2','e_t7_i','e_t7_i2','e_sz_i','e_sz_i2')"
    q "$EDB" "SELECT 'info   payload bytes after round C: ' || min(length(substring(cmt from '(?n)^(@nbmaint:\{.*\})\$')))
               || ' to ' || max(length(substring(cmt from '(?n)^(@nbmaint:\{.*\})\$')))
               FROM proto.seen_cmt WHERE label = 'C2-after' AND proto.nres(cmt) = 1"
    q "$EDB" "SELECT 'info   e_human_i as stored: ' || replace(cmt, chr(10), ' \\n ')
               FROM proto.seen_cmt WHERE label = 'C2-after' AND idx = 'e_human_i'"
  } >> "$OUT/edge.txt" 2>&1
  local n_ok n_diff
  n_ok=$(grep -Ec ' ok( \(.*\))?$' "$OUT/edge.txt"); n_diff=$(grep -c 'DIFFERS' "$OUT/edge.txt")
  printf 'edge verdicts: %s ok, %s different\n' "$n_ok" "$n_diff" | tee -a "$OUT/edge.txt"
  q postgres "DROP DATABASE IF EXISTS $EDB" > /dev/null
  q postgres "DROP ROLE IF EXISTS nbmaint_other" > /dev/null
  [ "$n_diff" = 0 ] || die "$n_diff edge cases differ from what was filed for them (see $OUT/edge.txt)"
}

# ------------------------------------------------------------- stage: defeat
# The no-defeat rule, shown working.  A throwaway fixture's churn commits while
# an undeclared snapshot is held, and it then gets the same checked
# maintenance step every scored fixture gets.  The check must stop the run, so
# here it is called in a subshell, the one place a die is expected, and its
# exit status and message are what the stage records.  Its own database, its
# proofs under out/defeat, and nothing scored.  A check that did not fire
# fails the run.
stage_defeat() {
  say "defeat: an undeclared snapshot across one maintenance step must stop the run"
  local ddb=defeat keep=$OUT rc
  q postgres "DROP DATABASE IF EXISTS $ddb" > /dev/null
  q postgres "CREATE DATABASE $ddb" > /dev/null
  proto_ddl | qin "$ddb" > "$OUT/defeat-ddl.log" 2>&1 || die "defeat: proto DDL failed"
  qz "$ddb" > "$OUT/defeat-build.log" 2>&1 <<'SQL' || die "defeat: build failed"
CREATE TABLE f_zz (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO f_zz SELECT g, g FROM generate_series(1, 100000) g;
ANALYZE f_zz;
CREATE INDEX f_zz_i ON f_zz USING hash (k);
SQL
  hold_snapshot "$ddb" zz
  printf 'DELETE FROM f_zz WHERE id %% 2 = 0;\n' | qin "$ddb" > "$OUT/defeat-churn.log" 2>&1 \
    || die "defeat: churn failed"
  OUT="$keep/defeat"; mkdir -p "$OUT"; : > "$OUT/maintenance-proof.txt"
  ( EXPECT_DIE=1; run_maint zz "$ddb" maint ) > "$keep/defeat-run.log" 2>&1; rc=$?
  OUT=$keep
  release_snapshot "$ddb" zz
  { printf 'exit status of the checked maintenance step: %s, %s\n' "$rc" \
      "$([ "$rc" -ne 0 ] && echo 'the run stopped, as the rule requires' || echo 'NOT STOPPED: the check did not fire')"
    grep -h 'FATAL:' "$OUT/defeat-run.log"
    cat "$OUT/defeat/maintenance-proof.txt"
  } > "$OUT/defeat.txt"
  q postgres "DROP DATABASE IF EXISTS $ddb" > /dev/null
  cat "$OUT/defeat.txt"
  [ "$rc" -ne 0 ] || die "defeat: a defeated maintenance step was not caught"
}

# -------------------------------------------------------------- stage: verify
# The page against what ran: the two texts re-extracted and compared with the
# files that ran, and this script's own block with the file that is running.
# Any difference fails the run.
stage_verify() {
  say "verify: the page's texts and this script, against what ran"
  need_texts
  local x
  : > "$OUT/verify.txt"
  md_block_with sql wiki_nbmaint_plan_12_17 "$PAGE" > "$OUT/x-plan.sql"
  md_block_with sql wiki_nbmaint_apply_12_17 "$PAGE" > "$OUT/x-apply.sql"
  for x in plan apply; do
    if cmp -s "$OUT/x-$x.sql" "$SQLD/$x.sql"; then
      printf '%-6s the page text is the text that ran (%s)\n' "$x" "$(sha "$SQLD/$x.sql")" >> "$OUT/verify.txt"
    else
      printf '%-6s DIFFERS from the text that ran\n' "$x" >> "$OUT/verify.txt"
    fi
  done
  if md_block_with bash '# nbmaint_suite_v17.sh - the PostgreSQL 17 leg' "$PAGE" > "$OUT/x-script.sh"; then
    if cmp -s "$OUT/x-script.sh" "${BASH_SOURCE[0]}"; then
      printf 'script the page block is the file that ran (%s)\n' "$(sha "${BASH_SOURCE[0]}")" >> "$OUT/verify.txt"
    else
      printf 'script DIFFERS from the file that ran\n' >> "$OUT/verify.txt"
    fi
  else
    printf 'script NOT FOUND in the page\n' >> "$OUT/verify.txt"
  fi
  cat "$OUT/verify.txt"
  ! grep -Eq 'DIFFERS|NOT FOUND' "$OUT/verify.txt" || die "the page is not what ran (see $OUT/verify.txt)"
}

# ------------------------------------------------------------ stage: criteria
# The errors a run provokes on purpose.  Everything else in the server log is
# unexpected, and an unexpected error or a maintenance skip line fails the run.
DELIBERATE='invalid transaction termination|REINDEX CONCURRENTLY cannot be executed from a function|syntax error at or near "\|\|"|canceling statement due to statement timeout|canceling statement due to lock timeout|division by zero|terminating connection due to administrator command|is not a btree index|is not a GIN index|is not a hash index|is not supported|REINDEX is not yet implemented for partitioned indexes'
stage_criteria() {
  say "criteria: everything a reader checks first, in one file"
  local all unexpected skips
  grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:.]+ UTC \[[0-9]+\] (ERROR|FATAL|PANIC):' "$OUT/server.log" \
    > "$OUT/server-errors-all.txt" 2>/dev/null
  grep -Ev "$DELIBERATE" "$OUT/server-errors-all.txt" > "$OUT/server-errors-unexpected.txt"
  all=$(grep -c '' "$OUT/server-errors-all.txt"); unexpected=$(grep -c '' "$OUT/server-errors-unexpected.txt")
  grep -E 'skipping (vacuum|analyze) of|canceling autovacuum task' "$OUT/server.log" > "$OUT/server-maint-skips.txt"
  skips=$(grep -c '' "$OUT/server-maint-skips.txt")
  {
    printf '1. texts\n';            sed 's/^/   /' "$OUT/hashes.txt"
    printf '2. engine checks\n';    sed 's/^/   /' "$OUT/checks.txt"
    printf '2b. build\n';           sed 's/^/   /' "$OUT/pin.txt"
    printf '3. fixtures built: %s; not built: %s\n' "$(printf '%s\n' $SCORED | grep -c .)" "${SKIPPED:-none}"
    printf '4. maintenance proofs: %s ok, %s DEFEATED\n' \
      "$(grep -c ' ok ' "$OUT/maintenance-proof.txt")" "$(grep -c 'DEFEATED' "$OUT/maintenance-proof.txt")"
    printf '5. timeouts in force, every VACUUM and ANALYZE session of the run:\n'
    grep -h -Eo 'timeouts in force: .*' "$OUT"/*.log | sort | uniq -c | sed 's/^/   /'
    printf '6. score\n';            sed 's/^/   /' "$OUT/score-summary.txt"
    printf '7. invariants\n';       sed 's/^/   /' "$OUT/invariants.txt"
    printf '8. act\n';              head -4 "$OUT/act.txt" | sed 's/^/   /'
    printf '9. edge\n';             tail -1 "$OUT/edge.txt" | sed 's/^/   /'
    printf '10. exact\n';           sed 's/^/   /' "$OUT/exact.txt"
    printf '10b. defeat\n';         sed 's/^/   /' "$OUT/defeat.txt" 2>/dev/null
    printf '11. server log: %s ERROR/FATAL/PANIC lines, %s deliberate, %s unexpected; %s maintenance skip lines\n' \
      "$all" "$((all - unexpected))" "$unexpected" "$skips"
    sed 's/^/   unexpected: /' "$OUT/server-errors-unexpected.txt" | head -5
    printf '12. verify\n';          sed 's/^/   /' "$OUT/verify.txt" 2>/dev/null
    printf '13. stage timings (seconds)\n'; sed 's/^/   /' "$OUT/timing.txt" 2>/dev/null
  } > "$OUT/criteria.txt" 2>&1
  cat "$OUT/criteria.txt"
  [ "$unexpected" = 0 ] || die "the server log has $unexpected unexpected error lines"
  [ "$skips" = 0 ] || die "the server log has $skips maintenance skip lines"
}

stage_report() {
  say "report: the files under $OUT"
  ls -1 "$OUT" | grep -Ev '^(census|horizon|build|churn|maint|settle2|oracle|snapshot)-' | sed 's/^/    /'
  printf '    ... and %s per-fixture logs\n' "$(ls -1 "$OUT" | grep -Ec '^(census|horizon|build|churn|maint|settle2|oracle|snapshot)-')"
}

# ---------------------------------------------------------------- stop, clean
# -m fast disconnects clients and writes a shutdown checkpoint.  The stop is
# then confirmed the way the teardown rule asks, and the stage dies rather
# than report a stop that did not happen, so clean never deletes a live
# cluster.  Both run only on a sandbox the guard has checked and found to be
# this script's own.
stage_stop() {
  say "stop: the sandbox cluster, cleanly"
  if [ "$SANDBOX_STATE" != ours ]; then note "no sandbox at $SANDBOX: nothing to stop"; return 0; fi
  if [ -x "$BIN/pg_ctl" ] && [ -s "$DATA/postmaster.pid" ] \
       && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1 || die "pg_ctl -m fast stop failed"
  else
    note "not running"
  fi
  [ -e "$DATA/postmaster.pid" ] && die "$DATA/postmaster.pid still exists"
  pgrep -f -- "-D $DATA" > /dev/null 2>&1 && die "a postgres process still runs on $DATA"
  [ -z "$(ls -A "$SOCK" 2>/dev/null)" ] || die "socket directory $SOCK is not empty"
  note "confirmed: no postmaster.pid, no postgres process on $DATA, socket directory empty"
}
stage_clean() {
  if [ "$SANDBOX_STATE" != ours ]; then say "clean"; note "no sandbox at $SANDBOX: nothing to delete"; return 0; fi
  stage_stop
  # the guard ran before anything else; check once more that the path about
  # to be deleted is still the canonical, marked sandbox
  [ "$(canon_dir "$SANDBOX")" = "$SANDBOX" ] && [ -f "$SANDBOX/$MARKER_NAME" ] \
    || die "refusing to delete $SANDBOX: it is no longer the marked sandbox"
  rm -rf -- "$SANDBOX"
  [ -e "$SANDBOX" ] && die "the sandbox is still there"
  SANDBOX_STATE=absent
  note "sandbox deleted: $SANDBOX"
}
stage_reset() {
  say "reset: drop the databases and the role, so a re-run starts at declare"
  local d
  for d in "$DB" "$PDB" "$EDB" defeat; do q postgres "DROP DATABASE IF EXISTS $d" > /dev/null; done
  q postgres "DROP ROLE IF EXISTS nbmaint_other" > /dev/null
}

need_server() {
  [ -x "$BIN/postgres" ] || die "no install under $INST: run the build stage first"
  [ -d "$DATA" ] || die "no cluster under $DATA: run the cluster stage first"
  "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1 || stage_start
}

ALL="build check cluster texts exact facts declare fixtures churn autoanalyze crosscheck decide oracle act score probes edge defeat verify criteria report"

# The dispatcher: the guard first, then every stage in turn.  A stage that
# returns non-zero, or dies inside a subshell, stops the run with exit status
# 1, and the EXIT trap stops the cluster.
main() {
  local stages="$*" s t0 rc
  [ -z "$stages" ] && stages="$ALL"
  for s in $stages; do
    declare -F "stage_$s" > /dev/null || die "no such stage: $s (have: $ALL start stop reset clean)"
  done
  case " $stages " in
    " clean "|" stop "|" stop clean ") sandbox_guard existing ;;
    *) sandbox_guard create ;;
  esac
  trap on_exit EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  [ "$SANDBOX_STATE" = ours ] && rm -f -- "$FAILMARK"
  for s in $stages; do
    case "$s" in
      build|check|cluster|start|stop|clean) : ;;
      *) need_server ;;
    esac
    t0=$(date +%s)
    "stage_$s"; rc=$?
    [ "$rc" = 0 ] || die "stage $s failed with exit status $rc"
    if [ "$SANDBOX_STATE" = ours ] && [ -s "$FAILMARK" ]; then
      die "stage $s: a check inside a subshell failed: $(head -1 "$FAILMARK")"
    fi
    [ "$SANDBOX_STATE" = ours ] && [ -d "$OUT" ] \
      && printf '%-12s %s\n' "$s" "$(( $(date +%s) - t0 ))" >> "$OUT/timing.txt"
  done
  say "done: $stages"
}

main "$@"
```

### The PostgreSQL 12 leg script

```bash
#!/usr/bin/env bash
#
# nbmaint_suite_v12.sh - the PostgreSQL 12 leg of the measurement behind the
# wiki page "A COMMENT-Stored Baseline Non-B-Tree Index-Maintenance Heuristic
# for PostgreSQL 12 Through 17", in bash and SQL only.  It is the
# compatibility half of the page's claim: the two filed texts must run on a
# 12 server without one character changed.
#
# It builds 12.2 out of tree from the pinned checkout, runs the engine
# regression suites, starts an isolated cluster, takes the page's two filed
# texts out of the page itself - step 1, the read-only plan, and step 2, the DO
# block that carries it out - and scores them on the numbered fixtures of the
# v17 wiki page "Detecting Inflated Non-B-Tree Indexes From Catalogs and a
# COMMENT-Stored Baseline in PostgreSQL 17", under the same two protocols the
# 17 leg follows: "Mandatory Non-B-Tree, Non-GIN Bloat Tests" for the hash,
# GiST, SP-GiST and BRIN fixtures and "Mandatory GIN Bloat Tests" for the GIN
# ones.  28 of that page's 29 numbered fixtures are built.  b11 needs the
# minmax_multi BRIN operator classes, which a 12 server does not have, and is
# recorded as skipped.  h06 and n11, whose VACUUM ran with INDEX_CLEANUP OFF,
# left this corpus on 2026-09-22 and that page on 2026-09-24, when both
# protocols stopped requiring that case.
#
# What this server lacks, and what the leg does instead, all discovered by the
# facts stage rather than assumed:
#   * no pg_stat_force_next_flush(): every churn session exits, and the leg
#     waits a second, before anything reads or resets its counters;
#   * no transaction_timeout: the three settable timeouts it has are forced;
#   * no GiST decoder in pageinspect: the GiST census reads the page's opaque
#     flags out of the raw page bytes;
#   * no pg_stat_progress_analyze: the census reads the two progress views
#     that exist;
#   * VACUUM VERBOSE words its counts differently, and this leg parses them.
#
# Five phases per fixture.  build: create, load, ANALYZE, create the index,
# ANALYZE.  baseline: a locked page census, then step 2's first run, which
# writes the as-built @nbmaint: payload into every fixture index's comment.
# churn: the recipe's writes, the maintenance step, the simulated auto-analyze
# census.  decide: step 1, verbatim, under SHARE ROW EXCLUSIVE on every
# fixture table.  oracle: REINDEX INDEX bracketed by pg_relation_size(index,
# 'main').  Every decision is scored against that oracle at the pay-off
# threshold the declare stage files before the first fixture exists.
#
# Every session that issues a VACUUM or an ANALYZE forces statement_timeout,
# lock_timeout and idle_in_transaction_session_timeout to 0 and prints the
# settings in force.  Every maintenance step is checked against the no-defeat
# rule as soon as it returns, and the run dies rather than score when one was
# defeated.
#
# A run fails - exit status 1, with the cluster stopped - when a stage fails,
# a regression suite fails, a required check fails, or the page differs from
# what ran.  The stages that change the fixtures run once each and in order;
# a stage that only reads or re-scores replaces its own records when it runs
# again, and every stage refuses to run before the stages it depends on.
#
# Every object this script creates is DISPOSABLE.  It runs its own cluster on
# a non-default port with its own socket directory, never touches a cluster it
# did not start, and treats raw/postgres-12 as read only.  Before it writes,
# stops or deletes anything it checks that the sandbox is a directory it
# created itself, directly under this repository's .wiki-runtime/tmp.
#
# Usage, from the repository root:
#   bash .wiki-runtime/tmp/nbmaint_suite_v12.sh                  # every stage
#   bash .wiki-runtime/tmp/nbmaint_suite_v12.sh score criteria   # re-score a run
#   bash .wiki-runtime/tmp/nbmaint_suite_v12.sh clean            # stop, delete
#
# Stages, in the default order: build check cluster texts exact facts declare
# fixtures churn autoanalyze crosscheck decide oracle act score probes edge defeat
# verify criteria report.  Not in the default order: start stop reset clean.
#
# Environment: WIKI_ROOT PAGE SRC SANDBOX PORT JOBS BASE_ROWS BRIN_ROWS
#              SMALL_ROWS GIN_ROWS HOT_ROWS A05_INSERTS ROUNDS MWM
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v17/questions/indexing/non-btree-comment-baseline-maintenance-heuristic.md}"
SRC="${SRC:-$WIKI_ROOT/raw/postgres-12}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/nbmaint12}"
PORT="${PORT:-55412}"
JOBS="${JOBS:-8}"
BASE_ROWS="${BASE_ROWS:-1000000}"
BRIN_ROWS="${BRIN_ROWS:-2000000}"
SMALL_ROWS="${SMALL_ROWS:-300000}"
GIN_ROWS="${GIN_ROWS:-600000}"
# n10 is sized so that three posting trees exist and the fixture clears the
# source page's own 1 MB floor; this method has no floor, but the recipe is
# ported unchanged
HOT_ROWS="${HOT_ROWS:-1200000}"
# h05 and n12 sit above the analyze threshold and below the vacuum thresholds,
# the one window in which an auto-analyze is the whole of a table's maintenance
A05_INSERTS="${A05_INSERTS:-120000}"
ROUNDS="${ROUNDS:-6}"
MWM="${MWM:-256MB}"

LEG=12
# The one commit this leg measures, and how it is built.  The build stage
# refuses any other commit, and an install it did not build from this commit
# with these flags - by its own manifest - is never reused.
EXPECTED_PIN=45b88269a353ad93744772791feb6d01bc7e1e42
CONFIGURE_FLAGS="--without-icu --without-readline --with-zlib --enable-debug"
DB=nbmaint; PDB=protocol; EDB=edge; XDB=scratch

# SHA-256 of the page's two filed texts as last measured.  A text that differs
# fails the texts stage: it must be re-measured and these refiled.
BASE_PLAN=89293844dee3972f60ee34c977805cf42075456f7a029d2e23c8c9e127c39f2f
BASE_APPLY=52bcbea7214af4f8e42fa09735a755a6d8c4eb414b18f22ebce3ab64980e924d

# The run's own session timeouts: they bound a census and a rebuild.  Every
# session that issues a VACUUM or an ANALYZE overrides them with zero_timeouts.
export PGOPTIONS="-c statement_timeout=1800s -c lock_timeout=15s"

HASHFX="h00 h01 h02 h03 h04 h05 h07 h08 h12"
GISTFX="g06 g07 g08 g09"
SPGFX="s08 s09 s10"
BRINFX="b10 b12 b13"
GINFX="n03 n04 n05 n06 n07 n08 n09 n10 n12"
SCORED="$HASHFX $GISTFX $SPGFX $BRINFX $GINFX"
SKIPPED="b11: needs int8_minmax_multi_ops, which a 12 server does not have"

say()  { printf '\n=== %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
# die stops the run.  Inside a subshell - a pipeline, a $(...) - exit ends
# only that subshell, so die also appends to FAILMARK, which the dispatcher
# reads after every stage.  EXPECT_DIE is set only in the one subshell that
# provokes a die on purpose and records its exit status.
die()  {
  printf 'FATAL: %s\n' "$*" >&2
  if [ -z "${EXPECT_DIE:-}" ] && [ -n "${FAILMARK:-}" ]; then
    printf '%s\n' "$*" >> "$FAILMARK" 2>/dev/null
  fi
  exit 1
}

# psql helpers.  -X ignores ~/.psqlrc and ON_ERROR_STOP is on, and every
# helper but three stops the run when psql fails.  qtry returns the failure to
# its caller, which wants the server's refusal as its result; qe runs without
# ON_ERROR_STOP for the same reason; qbg is a background session that another
# session terminates on purpose.
PSQL() { "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" "$@"; }
q()    { PSQL -d "$1" -At -c "$2" || die "psql failed on $1: ${2:0:120}"; }
qf()   { PSQL -d "$1" -f "$2" || die "psql failed on $1: file $2"; }
qin()  { PSQL -d "$1" || die "psql failed on $1: standard input"; }
qat()  { PSQL -d "$1" -At -f "$2" || die "psql failed on $1: file $2"; }
qtry() { PSQL -d "$1" -At -c "$2"; }
qe()   { "$BIN/psql" -X -h "$SOCK" -p "$PORT" -d "$1"; }
qbg()  { PSQL -d "$1"; }

# The preamble of every session that issues a VACUUM or an ANALYZE: the three
# settable timeouts this server has forced to 0, which is what an autovacuum
# launcher and a worker do to themselves, then the settings actually in force,
# read back.  transaction_timeout does not exist before PostgreSQL 17.
TIMEOUT_GUCS="'statement_timeout','lock_timeout','idle_in_transaction_session_timeout'"
zero_timeouts() {
  printf "SET /* wiki_nbmaint_zero_timeouts */ statement_timeout = 0;\n"
  printf "SET /* wiki_nbmaint_zero_timeouts */ lock_timeout = 0;\n"
  printf "SET /* wiki_nbmaint_zero_timeouts */ idle_in_transaction_session_timeout = 0;\n"
  printf "SELECT /* wiki_nbmaint_zero_timeouts */ 'timeouts in force: '\n"
  printf "       || string_agg(name || '=' || setting, ' ' ORDER BY name)\n"
  printf "  FROM pg_settings WHERE name IN (%s);\n" "$TIMEOUT_GUCS"
}
# qz <db>: run stdin in a session that begins with zero_timeouts
qz() { { zero_timeouts; cat; } | PSQL -d "$1" -At || die "psql failed on $1: a zero-timeout session"; }

# errf <db> <sql>: run a statement expected to fail, print the error or
# "accepted"
errf() {
  local out
  out=$(printf '%s\n' "$2" | "$BIN/psql" -X -q -v ON_ERROR_STOP=0 -h "$SOCK" -p "$PORT" \
          -d "$1" -f - 2>&1 | grep -E 'ERROR' | head -1 | sed -E 's/^psql:[^ ]* //')
  printf '%s' "${out:-accepted}"
}
# md_block_with <language> <tag> <file>: print the fenced block of that
# language which contains <tag>.  The fence is assembled from printf '\140'
# so that this script contains no literal Markdown fence.
md_block_with() {
  local lang=$1 tag=$2 file=$3 inb=0 line buf="" tick fence
  tick=$(printf '\140'); fence="$tick$tick$tick"
  while IFS= read -r line || [ -n "$line" ]; do
    if [ "$inb" = 1 ]; then
      if [ "$line" = "$fence" ]; then
        inb=0
        case "$buf" in *"$tag"*) printf '%s' "$buf"; return 0 ;; esac
        buf=""; continue
      fi
      buf="$buf$line
"
    elif [ "$line" = "$fence$lang" ]; then
      inb=1; buf=""
    fi
  done < "$file"
  return 1
}

# plan_view <step 1 file>: the one documented edit.  The two SET lines are
# dropped, because a view cannot carry them, and the rest becomes the view
# proto.plan_v, so the harness can store what the filed statement decides
# without re-typing it.
plan_view() {
  local line
  printf 'DROP VIEW IF EXISTS proto.plan_v;\nCREATE VIEW proto.plan_v AS\n'
  while IFS= read -r line; do
    case $line in
      "SET /* wiki_nbmaint_statement_timeout"*) continue ;;
      "SET /* wiki_nbmaint_lock_timeout"*)      continue ;;
    esac
    printf '%s\n' "$line"
  done < "$1"
}


sha() { sha256sum < "$1" | cut -d' ' -f1; }
tbl() { printf 'f_%s' "$1"; }
idx() { printf 'f_%s_i' "$1"; }
fx_am() {
  case "$1" in
    h*) printf 'hash' ;; g*) printf 'gist' ;; s*) printf 'spgist' ;;
    b*) printf 'brin' ;; n*) printf 'gin' ;;
  esac
}

# ------------------------------------------------------------ the sandbox ----
# SANDBOX, WIKI_ROOT and PAGE come from the environment, so nothing is written,
# stopped or deleted until they have been checked here.  WIKI_ROOT must be
# this repository; SANDBOX must resolve, with every symbolic link and every
# ".." taken out, to a plain directory directly under its .wiki-runtime/tmp;
# and an existing sandbox must carry the marker this script writes when it
# creates one, naming this leg.  From here on every path is the canonical one.
canon_dir() { ( cd -P -- "$1" 2>/dev/null && pwd -P ); }
MARKER_NAME=.nbmaint-sandbox
sandbox_guard() {   # <create|existing>
  local mode=$1 root tmp parent base
  root=$(canon_dir "$WIKI_ROOT") || die "WIKI_ROOT $WIKI_ROOT is not a directory"
  [ -f "$root/AGENTS.md" ] && [ -f "$root/wiki/versions.md" ] && [ -d "$root/raw" ] \
    || die "WIKI_ROOT $root is not the wiki repository"
  if [ ! -d "$root/.wiki-runtime/tmp" ]; then
    [ "$mode" = create ] || { SANDBOX_STATE=absent; return 0; }
    mkdir -p "$root/.wiki-runtime/tmp" || die "cannot create $root/.wiki-runtime/tmp"
  fi
  tmp=$(canon_dir "$root/.wiki-runtime/tmp") || die "no $root/.wiki-runtime/tmp"
  case "$tmp" in "$root"/*) : ;; *) die "$root/.wiki-runtime/tmp resolves outside the repository, to $tmp" ;; esac
  base=${SANDBOX%/}; base=${base##*/}
  case "$base" in
    ''|.|..|*[!A-Za-z0-9._-]*) die "refusing sandbox $SANDBOX: its last component must be a plain name" ;;
  esac
  parent=$(canon_dir "$(dirname -- "$SANDBOX")") || die "the parent of $SANDBOX does not exist"
  [ "$parent" = "$tmp" ] || die "refusing sandbox $SANDBOX: it resolves under $parent, not directly under $tmp"
  WIKI_ROOT=$root
  SANDBOX="$tmp/$base"
  if [ -L "$SANDBOX" ]; then
    die "refusing sandbox $SANDBOX: it is a symbolic link"
  elif [ -e "$SANDBOX" ]; then
    [ -d "$SANDBOX" ] || die "refusing sandbox $SANDBOX: it is not a directory"
    [ "$(cat "$SANDBOX/$MARKER_NAME" 2>/dev/null)" = "nbmaint sandbox, leg $LEG" ] \
      || die "refusing sandbox $SANDBOX: it has no $MARKER_NAME marker for leg $LEG, so this script did not create it"
    SANDBOX_STATE=ours
  elif [ "$mode" = create ]; then
    mkdir -- "$SANDBOX" || die "cannot create $SANDBOX"
    printf 'nbmaint sandbox, leg %s\n' "$LEG" > "$SANDBOX/$MARKER_NAME" || die "cannot mark $SANDBOX"
    SANDBOX_STATE=ours
  else
    SANDBOX_STATE=absent
    return 0
  fi
  BUILD="$SANDBOX/build"; INST="$SANDBOX/inst"; BIN="$INST/bin"
  DATA="$SANDBOX/data"; SOCK="$SANDBOX/sock"; OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql"
  FAILMARK="$SANDBOX/.failed-stage"
}

# On every way out: the background sessions this run opened are ended, and a
# run that failed also stops its cluster, so a failure never leaves a
# postmaster behind.  A run that succeeded leaves the cluster up for the next
# selective run; the clean stage stops it and deletes the sandbox.
on_exit() {
  local rc=$?
  trap - EXIT INT TERM
  if [ "${SANDBOX_STATE:-}" = ours ] && [ -s "$DATA/postmaster.pid" ] \
       && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/psql" -X -At -h "$SOCK" -p "$PORT" -d postgres -c \
      "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity
        WHERE pid <> pg_backend_pid()
          AND (query LIKE '%wiki_nbmaint_snapshot%' OR query LIKE '%wiki_nbmaint_edge_%')" \
      > /dev/null 2>&1
    if [ "$rc" -ne 0 ]; then
      "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1 \
        && printf 'the run failed: cluster on %s stopped\n' "$DATA" >&2
    fi
  fi
  wait 2> /dev/null
  exit "$rc"
}

# ---------------------------------------------------------------- build ------
# The checkout must be the pinned commit with no tracked file changed.  A
# build leaves a manifest in the install naming that commit, the flags, the
# build tree's configuration and a hash of every installed file; an install
# is reused only when all four still match.
install_inventory() {
  ( cd "$INST" && find . -type f ! -name nbmaint-build-manifest.txt -exec sha256sum {} + ) \
    | LC_ALL=C sort -k2 | sha256sum | cut -d' ' -f1
}
manifest_value() { sed -n "s/^$1: //p" "$INST/nbmaint-build-manifest.txt" 2>/dev/null | head -1; }
check_checkout() {
  local head
  head=$(git -C "$SRC" rev-parse HEAD 2>/dev/null) || die "$SRC is not a git checkout"
  [ "$head" = "$EXPECTED_PIN" ] || die "$SRC is at $head, not the pinned $EXPECTED_PIN"
  git -C "$SRC" --no-optional-locks diff --quiet HEAD -- \
    || die "$SRC has tracked files changed from $EXPECTED_PIN"
}
check_install() {
  [ -f "$INST/nbmaint-build-manifest.txt" ] || die "$INST has no build manifest: run clean, then build"
  [ "$(manifest_value pin)" = "$EXPECTED_PIN" ] \
    || die "the install was built from $(manifest_value pin), not $EXPECTED_PIN"
  [ "$(manifest_value configure)" = "$CONFIGURE_FLAGS" ] || die "the install was configured with other flags"
  [ "$(manifest_value build-config)" = "$(sha "$BUILD/config.status")" ] \
    || die "the build tree is not the one the install came from"
  [ "$(manifest_value inventory)" = "$(install_inventory)" ] \
    || die "the installed files differ from the ones the build left"
}
stage_build() {
  say "build: 12.2 out of tree from $SRC"
  mkdir -p "$OUT"
  check_checkout
  if [ -e "$INST" ]; then
    check_install
    note "reused, the manifest matches: $("$BIN/postgres" --version)"
  else
    [ -x "$SRC/configure" ] || die "no pinned checkout at $SRC"
    mkdir -p "$BUILD"
    ( cd "$BUILD" && "$SRC/configure" --prefix="$INST" $CONFIGURE_FLAGS > configure.log 2>&1 ) \
      || die "configure failed, see $BUILD/configure.log"
    ( cd "$BUILD" && make -j"$JOBS" -s > make.log 2>&1 ) || die "make failed, see $BUILD/make.log"
    ( cd "$BUILD" && make -s install > install.log 2>&1 ) || die "install failed"
    local m
    for m in pageinspect pgstattuple pg_freespacemap; do
      ( cd "$BUILD" && make -s -C "contrib/$m" install >> install.log 2>&1 ) \
        || die "contrib/$m install failed"
    done
    check_checkout   # the checkout did not move while it was built
    { printf 'pin: %s\n' "$EXPECTED_PIN"
      printf 'source: %s\n' "$SRC"
      printf 'configure: %s\n' "$CONFIGURE_FLAGS"
      printf 'build-config: %s\n' "$(sha "$BUILD/config.status")"
      printf 'version: %s\n' "$("$BIN/postgres" --version)"
      printf 'compiler: %s\n' "$(cc --version 2>/dev/null | head -1)"
      printf 'platform: %s\n' "$(uname -srm)"
      printf 'built: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      printf 'inventory: %s\n' "$(install_inventory)"
    } > "$INST/nbmaint-build-manifest.txt" || die "cannot write the build manifest"
    check_install
  fi
  "$BIN/postgres" --version | tee "$OUT/version.txt"
  { printf 'install built from %s, per its manifest\n' "$(manifest_value pin)"
    printf 'checkout %s is at %s\n' "$SRC" "$(git -C "$SRC" rev-parse HEAD)"
  } | tee "$OUT/pin.txt"
}

# ---------------------------------------------------------------- check ------
# Every suite must exit 0 and report all its tests passed, or the run stops.
suite_result() {
  grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$1" | tail -1
}
stage_check() {
  say "check: make check, and the contrib suites the cross-checks read"
  mkdir -p "$OUT"; : > "$OUT/checks.txt"
  check_checkout
  check_install
  local rc m res bad=""
  ( cd "$BUILD" && make -s check > "$OUT/check-core.log" 2>&1 ); rc=$?
  res=$(suite_result "$OUT/check-core.log")
  printf 'core exit=%s %s\n' "$rc" "$res" >> "$OUT/checks.txt"
  { [ "$rc" = 0 ] && case "$res" in All*passed) true ;; *) false ;; esac; } || bad="$bad core"
  # contrib/pg_freespacemap in 12.2 declares no REGRESS target, so it has no
  # suite to run; that is checked in its Makefile rather than assumed
  if grep -q '^REGRESS' "$SRC/contrib/pg_freespacemap/Makefile"; then
    bad="$bad pg_freespacemap-has-a-suite-this-leg-does-not-run"
  else
    printf 'pg_freespacemap no suite: its Makefile declares no REGRESS\n' >> "$OUT/checks.txt"
  fi
  for m in pageinspect pgstattuple; do
    ( cd "$BUILD" && make -s -C "contrib/$m" check > "$OUT/check-$m.log" 2>&1 ); rc=$?
    res=$(suite_result "$OUT/check-$m.log")
    printf '%s exit=%s %s\n' "$m" "$rc" "$res" >> "$OUT/checks.txt"
    { [ "$rc" = 0 ] && case "$res" in All*passed) true ;; *) false ;; esac; } || bad="$bad $m"
  done
  cat "$OUT/checks.txt"
  [ -z "$bad" ] || die "regression suites failed:$bad (see $OUT/checks.txt)"
}
# ---------------------------------------------------------------- cluster ----
# Settings and their apply scope, written before the first start:
#   listen_addresses, port, unix_socket_directories, shared_buffers
#                                                        -> PGC_POSTMASTER, restart
#   autovacuum, fsync, log_timezone, log_line_prefix     -> PGC_SIGHUP, reload
#   maintenance_work_mem, max_parallel_maintenance_workers, work_mem, timezone
#                                                        -> PGC_USERSET, session
# autovacuum is off for isolation only: the fixture runs the maintenance the
# launcher would have run.  max_parallel_maintenance_workers = 0 keeps every
# build and every VACUUM on the serial path, so the oracle is one code path.
stage_cluster() {
  say "cluster: isolated, port $PORT, socket directory $SOCK"
  mkdir -p "$OUT" "$SQLD" "$SOCK"
  if [ ! -d "$DATA" ]; then
    "$BIN/initdb" -D "$DATA" --locale=C --encoding=UTF8 > "$OUT/initdb.log" 2>&1 \
      || die "initdb failed, see $OUT/initdb.log"
    cat >> "$DATA/postgresql.conf" <<CONF
listen_addresses = ''
unix_socket_directories = '$SOCK'
port = $PORT
shared_buffers = 512MB
maintenance_work_mem = $MWM
max_parallel_maintenance_workers = 0
work_mem = 64MB
autovacuum = off
fsync = off
timezone = 'UTC'
log_timezone = 'UTC'
log_line_prefix = '%m [%p] '
CONF
  fi
  stage_start
  q postgres "SELECT 1 FROM pg_database WHERE datname = '$XDB'" | grep -q 1 \
    || q postgres "CREATE /* wiki_nbmaint_cluster */ DATABASE $XDB" > /dev/null
  q postgres "SELECT /* wiki_nbmaint_settings */ name || ' = ' || setting ||
                coalesce(' ' || unit, '') || ' [' || context || ']'
                FROM pg_settings
               WHERE name IN ('autovacuum','block_size','fsync','maintenance_work_mem',
                              'max_parallel_maintenance_workers','shared_buffers','work_mem',
                              'stats_fetch_consistency','timezone','log_timezone',
                              'autovacuum_analyze_threshold','autovacuum_analyze_scale_factor',
                              'autovacuum_vacuum_threshold','autovacuum_vacuum_scale_factor',
                              'autovacuum_vacuum_insert_threshold',
                              'autovacuum_vacuum_insert_scale_factor','autovacuum_naptime',
                              'statement_timeout','lock_timeout','transaction_timeout',
                              'idle_in_transaction_session_timeout','gin_pending_list_limit')
               ORDER BY name" > "$OUT/settings.txt"
  q postgres "SELECT /* wiki_nbmaint_settings */ 'max_data_alignment = ' || max_data_alignment
                || ', database_block_size = ' || database_block_size FROM pg_control_init()" \
    >> "$OUT/settings.txt"
  q postgres "SELECT /* wiki_nbmaint_settings */ version()" >> "$OUT/settings.txt"
  printf 'uname = %s\n' "$(uname -srm)" >> "$OUT/settings.txt"
  cat "$OUT/settings.txt"
}

stage_start() {
  mkdir -p "$OUT" "$SOCK"
  if [ -s "$DATA/postmaster.pid" ] && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    note "already running"
  else
    "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w start > /dev/null || die "pg_ctl start failed"
  fi
}

# ---------------------------------------------------------------- texts ------
stage_texts() {
  say "texts: step 1 and step 2 out of the page, hashed, and the one-edit view"
  [ -f "$PAGE" ] || die "no page at $PAGE; set PAGE or run from the repository root"
  mkdir -p "$SQLD" "$OUT"
  md_block_with sql wiki_nbmaint_plan_12_17 "$PAGE" > "$SQLD/plan.sql" \
    || die "step 1 (wiki_nbmaint_plan_12_17) not found in $PAGE"
  md_block_with sql wiki_nbmaint_apply_12_17 "$PAGE" > "$SQLD/apply.sql" \
    || die "step 2 (wiki_nbmaint_apply_12_17) not found in $PAGE"
  local h1 h2
  h1=$(sha "$SQLD/plan.sql"); h2=$(sha "$SQLD/apply.sql")
  { printf 'plan   %s %s\n' "$h1" "$([ "$h1" = "$BASE_PLAN" ] && echo match || echo DIFFERS)"
    printf 'apply  %s %s\n' "$h2" "$([ "$h2" = "$BASE_APPLY" ] && echo match || echo DIFFERS)"
    printf 'plan   lines=%s bytes=%s\n' "$(grep -c '' "$SQLD/plan.sql")" "$(wc -c < "$SQLD/plan.sql" | tr -d ' ')"
    printf 'apply  lines=%s bytes=%s\n' "$(grep -c '' "$SQLD/apply.sql")" "$(wc -c < "$SQLD/apply.sql" | tr -d ' ')"
  } > "$OUT/hashes.txt"
  # The shared pipeline: "WITH params AS (" through the end of the staged CTE.
  # The page says this region is byte-identical in both texts; this is the
  # check that makes the claim auditable.
  sed -n '/^WITH params AS ($/,/^      FROM decided d$/p' "$SQLD/plan.sql"  > "$OUT/pipeline_plan.sql"
  sed -n '/^WITH params AS ($/,/^      FROM decided d$/p' "$SQLD/apply.sql" > "$OUT/pipeline_apply.sql"
  { printf 'pipeline plan  %s\n' "$(sha "$OUT/pipeline_plan.sql")"
    printf 'pipeline apply %s\n' "$(sha "$OUT/pipeline_apply.sql")"
    printf 'pipeline lines %s\n' "$(grep -c '' "$OUT/pipeline_plan.sql")"
    if [ -s "$OUT/pipeline_plan.sql" ] && cmp -s "$OUT/pipeline_plan.sql" "$OUT/pipeline_apply.sql"; then
      printf 'pipeline identical yes\n'
    else
      printf 'pipeline identical NO\n'
    fi
  } >> "$OUT/hashes.txt"
  plan_view "$SQLD/plan.sql" > "$SQLD/plan_view.sql"
  cat "$OUT/hashes.txt"
  ! grep -Eq 'DIFFERS|identical NO' "$OUT/hashes.txt" \
    || die "the page's texts are not the ones this script was last measured with: re-measure, then refile BASE_PLAN and BASE_APPLY"
}

# run_plan <db> <tag> [prefix-sql]: step 1, verbatim; run_apply the same for
# step 2.  The optional prefix runs first in the same session (SET ROLE).
# Both return psql's exit status, which every caller checks.
run_plan() {
  { [ -n "${3:-}" ] && printf '%s\n' "$3"; cat "$SQLD/plan.sql"; } \
    | "$BIN/psql" -X -v ON_ERROR_STOP=1 -P pager=off -h "$SOCK" -p "$PORT" -d "$1" \
      > "$OUT/plan-$2.txt" 2>&1
}
run_apply() {
  { [ -n "${3:-}" ] && printf '%s\n' "$3"; cat "${APPLY_FILE:-$SQLD/apply.sql}"; } \
    | "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1" \
      > "$OUT/apply-$2.log" 2>&1
}
apply_summary() { grep -Eo 'nbmaint: reindex=.*' "$OUT/apply-$1.log" | tail -1; }
plan_actions()  {
  grep -Eo '\| (initialize|refresh|reindex|skip|blocked|conflict) ' "$OUT/plan-$1.txt" \
    | sort | uniq -c | tr -s ' ' | tr '\n' ';'
}

# ---------------------------------------------------------------- exact ------
# Both filed texts, executed unmodified on this server before any fixture
# exists: the compatibility claim in its smallest form.  Any text that fails,
# or a second step 2 run that writes anything, fails the stage.
stage_exact() {
  say "exact: both filed texts, unmodified, on a database with no fixture in it"
  : > "$OUT/exact.txt"
  q "$XDB" 'DROP TABLE IF EXISTS zz_exact CASCADE' > /dev/null
  qz "$XDB" > "$OUT/exact-build.log" 2>&1 <<'SQL'
CREATE /* wiki_nbmaint_exact */ TABLE zz_exact AS
  SELECT i::bigint AS k, int8range(i, i + 10) AS r FROM generate_series(1, 200000) i;
ANALYZE /* wiki_nbmaint_exact */ zz_exact;
CREATE /* wiki_nbmaint_exact */ INDEX zz_exact_h ON zz_exact USING hash (k);
CREATE /* wiki_nbmaint_exact */ INDEX zz_exact_g ON zz_exact USING gist (r);
CREATE /* wiki_nbmaint_exact */ INDEX zz_exact_b ON zz_exact (k);
COMMENT /* wiki_nbmaint_exact */ ON INDEX zz_exact_h IS 'a human note that must survive';
SQL
  local rc bad=""
  run_plan "$XDB" exact1; rc=$?; [ "$rc" = 0 ] || bad="$bad step-1-first"
  printf 'step 1, first run: exit=%s, rows naming zz_exact=%s, actions: %s\n' "$rc" \
    "$(grep -c 'zz_exact_' "$OUT/plan-exact1.txt")" "$(plan_actions exact1)" >> "$OUT/exact.txt"
  run_apply "$XDB" exact1; rc=$?; [ "$rc" = 0 ] || bad="$bad step-2-first"
  printf 'step 2, first run:  exit=%s, %s\n' "$rc" "$(apply_summary exact1)" >> "$OUT/exact.txt"
  q "$XDB" "SELECT /* wiki_nbmaint_exact */ c.relname || ': ' || replace(d.description, chr(10), ' | ')
              FROM pg_description d JOIN pg_class c ON c.oid = d.objoid
             WHERE d.classoid = 'pg_class'::regclass AND c.relname LIKE 'zz_exact_%'
             ORDER BY 1" >> "$OUT/exact.txt"
  run_apply "$XDB" exact2; rc=$?; [ "$rc" = 0 ] || bad="$bad step-2-second"
  printf 'step 2, second run: exit=%s, %s\n' "$rc" "$(apply_summary exact2)" >> "$OUT/exact.txt"
  apply_summary exact2 | grep -q 'reindex=0 initialize=0 refresh=0 ' || bad="$bad second-run-wrote"
  run_plan "$XDB" exact2; rc=$?; [ "$rc" = 0 ] || bad="$bad step-1-after"
  printf 'step 1, after both: exit=%s, actions: %s\n' "$rc" "$(plan_actions exact2)" >> "$OUT/exact.txt"
  q "$XDB" 'DROP TABLE IF EXISTS zz_exact CASCADE' > /dev/null
  cat "$OUT/exact.txt"
  [ -z "$bad" ] || die "exact:$bad (see $OUT/exact.txt and $OUT/plan-exact*.txt, $OUT/apply-exact*.log)"
}

# ---------------------------------------------------------------- facts ------
# Every version-local fact the two texts and this harness depend on,
# discovered on the running server rather than assumed.
stage_facts() {
  say "facts: what this server does, discovered rather than assumed"
  : > "$OUT/facts.txt"
  fact() { printf '%-40s %s\n' "$1" "$2" >> "$OUT/facts.txt"; }
  fact server_version_num "$(q "$XDB" 'SHOW server_version_num')"
  fact materialized_cte \
    "$(errf "$XDB" 'WITH x AS MATERIALIZED (SELECT 1) SELECT count(*) FROM x;')"
  fact pg_input_is_valid_rows \
    "$(q "$XDB" "SELECT count(*) FROM pg_proc WHERE proname = 'pg_input_is_valid'")"
  fact regexp_match_rows \
    "$(q "$XDB" "SELECT count(*) FROM pg_proc WHERE proname = 'regexp_match'")"
  fact pg_stat_force_next_flush_rows \
    "$(q "$XDB" "SELECT count(*) FROM pg_proc WHERE proname = 'pg_stat_force_next_flush'")"
  fact transaction_timeout_rows \
    "$(q "$XDB" "SELECT count(*) FROM pg_settings WHERE name = 'transaction_timeout'")"
  fact minmax_multi_opclass_rows \
    "$(q "$XDB" "SELECT count(*) FROM pg_opclass WHERE opcname = 'int8_minmax_multi_ops'")"
  fact gist_point_ops_support_11 \
    "$(q "$XDB" "SELECT count(*) FROM pg_opclass opc JOIN pg_amproc ap
                   ON ap.amprocfamily = opc.opcfamily AND ap.amprocnum = 11
                 WHERE opc.opcname = 'point_ops'
                   AND opc.opcmethod = (SELECT oid FROM pg_am WHERE amname = 'gist')")"
  fact pg_stat_progress_analyze \
    "$(q "$XDB" "SELECT coalesce(to_regclass('pg_stat_progress_analyze')::text, 'absent')")"
  fact n_ins_since_vacuum_column \
    "$(q "$XDB" "SELECT count(*) FROM pg_attribute
                  WHERE attrelid = 'pg_stat_all_tables'::regclass
                    AND attname = 'n_ins_since_vacuum'")"
  fact float4_to_numeric_1234567 "$(q "$XDB" 'SELECT 1234567::float4::numeric')"
  fact to_char_OF "$(q "$XDB" "SELECT to_char(now(), 'OF')")"
  fact commit_inside_do_top_level \
    "$(errf "$XDB" 'DO $x$ BEGIN PERFORM 1; COMMIT; END $x$;')"
  fact commit_inside_do_in_begin \
    "$(errf "$XDB" 'BEGIN; DO $x$ BEGIN PERFORM 1; COMMIT; END $x$; COMMIT;')"
  # step 2 narrows its pipeline with a transaction-local custom setting; what
  # step 1 then reads in the same session, and in a fresh one
  fact custom_setting_after_local_set \
    "$(printf '%s\n' 'BEGIN;' "SELECT set_config('nbmaint.only_index', '1', true);" 'COMMIT;' \
         "SELECT 'after commit: ' || coalesce(quote_literal(current_setting('nbmaint.only_index', true)), 'NULL');" \
       | PSQL -d "$XDB" -q -At 2>&1 | tail -1)"
  fact custom_setting_fresh_session \
    "$(q "$XDB" "SELECT coalesce(quote_literal(current_setting('nbmaint.only_index', true)), 'NULL')")"
  q "$XDB" 'DROP TABLE IF EXISTS zz_f CASCADE' > /dev/null
  q "$XDB" 'CREATE TABLE zz_f (k bigint)' > /dev/null
  q "$XDB" 'INSERT INTO zz_f SELECT g FROM generate_series(1, 1000) g' > /dev/null
  q "$XDB" 'CREATE INDEX zz_f_h ON zz_f USING hash (k)' > /dev/null
  fact reindex_inside_do \
    "$(errf "$XDB" 'DO $x$ BEGIN EXECUTE $q$REINDEX INDEX zz_f_h$q$; END $x$;')"
  fact reindex_concurrently_inside_do \
    "$(errf "$XDB" 'DO $x$ BEGIN EXECUTE $q$REINDEX INDEX CONCURRENTLY zz_f_h$q$; END $x$;')"
  fact reindex_concurrently_top_level "$(errf "$XDB" 'REINDEX INDEX CONCURRENTLY zz_f_h;')"
  fact comment_with_expression "$(errf "$XDB" "COMMENT ON INDEX zz_f_h IS 'a' || 'b';")"
  fact comment_with_literal "$(errf "$XDB" "COMMENT ON INDEX zz_f_h IS 'ab';")"
  # ALTER INDEX ... OWNER TO the owner it already has, which step 2 uses as its
  # index lock: the lock it holds, anything it prints, and whether it rewrote
  # the index's pg_class row
  local x0 x1
  x0=$(q "$XDB" "SELECT xmin FROM pg_class WHERE relname = 'zz_f_h'")
  fact alter_index_owner_to_owner \
    "$(printf '%s\n' 'BEGIN;' 'ALTER INDEX zz_f_h OWNER TO CURRENT_USER;' \
         "SELECT 'held: ' || string_agg(mode, ',' ORDER BY mode) FROM pg_locks WHERE relation = 'zz_f_h'::regclass AND pid = pg_backend_pid();" \
         'COMMIT;' | PSQL -d "$XDB" -q -At 2>&1 | tr '\n' ' ' | sed -e 's/ *$//')"
  x1=$(q "$XDB" "SELECT xmin FROM pg_class WHERE relname = 'zz_f_h'")
  fact alter_index_owner_rewrote_pg_class "$([ "$x0" = "$x1" ] && echo no || echo "yes ($x0 -> $x1)")"
  # A statement timeout inside a DO block's EXCEPTION WHEN OTHERS is not
  # caught: it ends the whole block.  That is what bounds step 2 as a whole.
  fact statement_timeout_vs_others \
    "$(errf "$XDB" "SET statement_timeout = '200ms'; DO \$x\$ BEGIN BEGIN PERFORM pg_sleep(2); EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'caught'; END; END \$x\$;")"
  q "$XDB" 'DROP TABLE IF EXISTS zz_p CASCADE' > /dev/null
  q "$XDB" 'CREATE TABLE zz_p (k bigint) PARTITION BY RANGE (k)' > /dev/null
  q "$XDB" 'CREATE TABLE zz_p1 PARTITION OF zz_p FOR VALUES FROM (0) TO (1000)' > /dev/null
  q "$XDB" 'CREATE INDEX zz_p_h ON zz_p USING hash (k)' > /dev/null
  fact partitioned_index_relkind "$(q "$XDB" "SELECT relkind FROM pg_class WHERE relname = 'zz_p_h'")"
  fact partitioned_index_size "$(q "$XDB" "SELECT pg_relation_size('zz_p_h')")"
  fact reindex_partitioned_index "$(errf "$XDB" 'REINDEX INDEX zz_p_h;')"
  q "$XDB" 'DROP TABLE IF EXISTS zz_p CASCADE' > /dev/null
  q "$XDB" 'DROP TABLE IF EXISTS zz_f CASCADE' > /dev/null
  cat "$OUT/facts.txt"
}
# ---------------------------------------------------------------- declare ----
# Files the declared kind of every published column, the method's own
# thresholds, the pay-off threshold every decision is scored at, the
# per-fixture predictions, the invariants, the declared exceptions of the
# no-defeat rule and the coverage plan - all BEFORE any fixture exists.  Both
# protocols forbid rewriting a declaration after the run, so this stage refuses
# once the fixture database is there.
stage_declare() {
  say "declare: kinds, thresholds, predictions, invariants, exceptions, coverage"
  if q postgres "SELECT count(*) FROM pg_database WHERE datname = '$DB'" | grep -q '^1$'; then
    die "refusing to re-file declarations: database $DB already exists (run reset first)"
  fi
  q postgres "DROP /* wiki_nbmaint_declare */ DATABASE IF EXISTS $PDB" > /dev/null
  q postgres "CREATE /* wiki_nbmaint_declare */ DATABASE $PDB" > /dev/null
  qin "$PDB" > "$OUT/declare.log" 2>&1 <<'SQL' || die "declare failed"
-- DISPOSABLE bookkeeping objects.
CREATE /* wiki_nbmaint_declare */ TABLE declared_kind (
  column_name text PRIMARY KEY,
  declared_kind text NOT NULL CHECK (declared_kind IN ('lower bound','upper bound','level')),
  claim text NOT NULL,
  filed_at timestamptz NOT NULL DEFAULT now());
INSERT /* wiki_nbmaint_declare */ INTO declared_kind (column_name, declared_kind, claim) VALUES
 ('index_size',      'level', 'the index file now, pg_relation_size; no claim against the oracle'),
 ('baseline_size',   'level', 'the stored baseline size itself'),
 ('size_ratio',      'level', 'current size over stored size; the input to the size test, not an estimate of reclaimable bytes'),
 ('table_tuples',    'level', 'the table''s pg_class.reltuples now'),
 ('baseline_tuples', 'level', 'the stored table tuple count itself'),
 ('tuple_ratio',     'level', 'current over stored table tuple count; the input to the tuple test');

CREATE /* wiki_nbmaint_declare */ TABLE declared_decision (
  knob text PRIMARY KEY, value text NOT NULL, meaning text NOT NULL,
  filed_at timestamptz NOT NULL DEFAULT now());
INSERT /* wiki_nbmaint_declare */ INTO declared_decision (knob, value, meaning) VALUES
 ('reindex when', 'size_ratio >= 1.30, or |table tuples - stored| >= 0.30 * stored',
                  'the method flags a rebuild: the brief''s two tests, either one'),
 ('refresh when', 'index smaller than its stored size',
                  'not a decision to rebuild; the baseline is rewritten'),
 ('pay-off',      'truth_pct >= 23.08',
                  'a rebuild was worth it: 100 * (1 - 1/1.30), the reclaim a 30 % growth implies, rounded to 23.08; compared with the unrounded 100 * (1 - R / C), never with its two-decimal display'),
 ('score',        'PASS, FALSE POSITIVE, FALSE NEGATIVE',
                  'reindex and truth_pct >= pay-off, or neither: PASS; reindex below it: FALSE POSITIVE; no reindex at or above it: FALSE NEGATIVE'),
 ('cross-checks', 'a VERBOSE count and a BRIN free-space reading are compared with the censuses taken just before and just after the VACUUM that produced them',
                  'see invariants I9 and I18');

-- Predictions filed before the run, from the B, C and R figures the source
-- page filed on 17.11 on 2026-09-16: no 12.2 figure existed for these
-- fixtures, so the 17.11 ones are the prediction.  A miss is reported, not
-- corrected.
CREATE /* wiki_nbmaint_declare */ TABLE declared_prediction (
  fixture text PRIMARY KEY, action text NOT NULL, score text NOT NULL, why text NOT NULL,
  filed_at timestamptz NOT NULL DEFAULT now());
INSERT /* wiki_nbmaint_declare */ INTO declared_prediction (fixture, action, score, why) VALUES
 ('h00','skip',   'PASS',           'no churn'),
 ('h01','reindex','PASS',           'size 2.35x, reclaim 37.7 %'),
 ('h02','reindex','PASS',           'size 5.06x, reclaim 80.3 %'),
 ('h03','reindex','PASS',           'size 1.60x, reclaim 37.6 %'),
 ('h04','reindex','FALSE POSITIVE', 'insert-only growth: size 1.37x and tuples 1.40x, reclaim 9.1 %'),
 ('h05','skip',   'PASS',           'size 1.12x, tuples 1.12x, reclaim 11.1 %'),
 ('h07','skip',   'PASS',           'empty'),
 ('h08','skip',   'PASS',           '1 % update, nothing to reclaim'),
 ('h12','skip',   'PASS',           'partial index: size 1.13x, table count unchanged, reclaim 0 %'),
 ('g06','reindex','PASS',           'size 4.86x, reclaim 79.4 %'),
 ('g07','reindex','PASS',           'size 3.71x, reclaim 73.0 %'),
 ('g08','reindex','PASS',           'tuples 0.20x, reclaim 80.0 %'),
 ('g09','reindex','PASS',           'size 10.0x, reclaim 84.4 %'),
 ('s08','reindex','PASS',           'size 7.27x, reclaim 85.7 %'),
 ('s09','reindex','PASS',           'size 3.97x, reclaim 74.8 %'),
 ('s10','reindex','PASS',           'size 1.35x, reclaim 44.0 %'),
 ('b10','reindex','FALSE POSITIVE', 'BRIN grows with the heap: size 1.33x, reclaim 0 %'),
 ('b12','reindex','FALSE POSITIVE', 'BRIN grows with the heap: size 1.75x, reclaim 0 %'),
 ('b13','reindex','FALSE POSITIVE', 'appended rows: tuples 1.50x, reclaim 0 %'),
 ('n03','skip',   'PASS',           'size 1.18x, tuples 1.00x, reclaim 14.9 %'),
 ('n04','reindex','PASS',           'size 7.52x, reclaim 84.9 %'),
 ('n05','reindex','FALSE POSITIVE', 'pending-list inserts: size 1.97x and tuples 1.50x, reclaim 21.5 %'),
 ('n06','reindex','PASS',           'size 2.86x, reclaim 67.7 %'),
 ('n07','reindex','PASS',           'size 4.37x, reclaim 73.9 %'),
 ('n08','skip',   'PASS',           'no churn'),
 ('n09','skip',   'PASS',           'empty'),
 ('n10','reindex','PASS',           'tuples 0.20x, reclaim 78.9 %'),
 ('n12','reindex','FALSE POSITIVE', 'size 1.31x, reclaim 11.5 %');

CREATE /* wiki_nbmaint_declare */ TABLE declared_invariant (
  id text PRIMARY KEY, claim text NOT NULL, filed_at timestamptz NOT NULL DEFAULT now());
INSERT /* wiki_nbmaint_declare */ INTO declared_invariant (id, claim) VALUES
 ('I1',  'no fixture index is smaller after its churn and maintenance than as built: none of the five AMs truncates'),
 ('I2',  'size bracket: pg_relation_size(index, main) re-read after each census equals block_size times the blocks the census scanned'),
 ('I3',  'hash: the census page classes and pgstathashindex both account for every block of the file'),
 ('I4',  'hash: every block hash_bitmap_info reports free reads back as an unused page'),
 ('I5',  'GiST: the FSM free-page count never exceeds the census deleted-plus-new count; SP-GiST: it never exceeds the new or empty pages outside the metapage and the two root pages, read from page headers'),
 ('I6',  'BRIN: the revmap entry count equals the summary tuples the regular pages hold'),
 ('I7',  'BRIN: the index is never smaller after the maintenance step than before it'),
 ('I8',  'GIN: on every census whose metapage counts the build or a VACUUM wrote last, the metapage entry, data and total page counts equal the census, a not-yet-recyclable deleted page counted as data; a census taken after writes and before a VACUUM reads counts stale by construction and is reported, not scored'),
 ('I9',  'the VACUUM VERBOSE index line appears exactly where index cleanup ran and returned statistics (not for the ANALYZE-only stand-ins, not for a hash index whose bulk delete never ran), and each of its counts equals the census: pages in total = the census just after that VACUUM, except on BRIN, which counts before it summarizes, = the census just before; hash and BRIN: 0 newly deleted, 0 currently deleted, 0 reusable; GiST: currently deleted = deleted-flag plus all-zero pages after, reusable = FSM free pages after, newly deleted = deleted-flag pages after minus before; SP-GiST: newly deleted = currently deleted = reusable = the new or empty pages outside the metapage and the two roots after, = FSM free pages after; GIN: reusable = FSM free pages after'),
 ('I10', 'the maintenance was not defeated: every maintenance VACUUM reports 0 tuples dead but not yet removable, except a declared held snapshot, which must pin something and whose second VACUUM reports 0'),
 ('I11', 'every VACUUM and ANALYZE session ran with all four settable timeouts at 0, and no maintenance log carries a skip line, an error or a cancellation'),
 ('I12', 'the measurement lock was never held across a maintenance step'),
 ('I13', 'no horizon holder but a declared snapshot: 0 prepared transactions, 0 replication slots, 0 other backends with a transaction id or an xmin'),
 ('I14', 'step 2''s first run stored a version-2 payload in every fixture index, with sz equal to the baseline census size and tup equal to the table count it read'),
 ('I15', 'the method decided on the maintained state: the size step 1 saw equals the maintained census size and the oracle''s before-size'),
 ('I16', 'step 1''s action equals the same two tests recomputed independently from the stored payload and the decide-time readings'),
 ('I17', 'step 2 carried out exactly the plan step 1 printed on the same state, and a second run of step 2 wrote nothing'),
 ('I18', 'BRIN, per regular page, on every census taken just after a VACUUM: every page that VACUUM did not write - its LSN no newer than the WAL insert position read just before the VACUUM began - reads in pg_freespace exactly the FSM category floor of its own free space, pd_upper minus pd_lower less one line pointer, or 0 on a page flagged BRIN_EVACUATE_PAGE; the pages the VACUUM''s own summarization wrote are compared and reported, not scored, because BRIN writes such a page''s FSM entry only when the page is extended or a search finds it short of space');

CREATE /* wiki_nbmaint_declare */ TABLE declared_exception (
  id text PRIMARY KEY, fixture text NOT NULL, state text NOT NULL,
  reading_rule text NOT NULL, filed_at timestamptz NOT NULL DEFAULT now());
INSERT /* wiki_nbmaint_declare */ INTO declared_exception (id, fixture, state, reading_rule) VALUES
 ('X1', 'g08', 'a REPEATABLE READ snapshot opened in a second session before the churn commits and held across the maintenance VACUUM',
         'the reading under it is held-horizon; the method is scored on the settle2 state, after the release and a second VACUUM ANALYZE'),
 ('X2', 'n10', 'the same snapshot, held across the settling VACUUM of a GIN fixture',
         'the same rule as X1'),
 ('X3', 'all', 'the SHARE ROW EXCLUSIVE measurement lock, which excludes VACUUM and ANALYZE by design',
         'taken per census and for the decide phase in their own transactions, never across a maintenance step');

CREATE /* wiki_nbmaint_declare */ TABLE declared_coverage (
  protocol text NOT NULL, behavior text NOT NULL, fixture text NOT NULL,
  filed_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (protocol, behavior));
INSERT /* wiki_nbmaint_declare */ INTO declared_coverage (protocol, behavior, fixture) VALUES
 ('non-btree','hash: an overflow chain, and a freed overflow page whose bitmap bit was cleared','h01'),
 ('non-btree','hash: a splitpoint allocation','h02'),
 ('non-btree','hash: an index whose hashbulkdelete never ran','h04'),
 ('non-btree','GiST: an emptied leaf that was deleted, and one that survived as its parent''s last downlink','g07'),
 ('non-btree','GiST: a deleted-but-not-recyclable page under a held snapshot','not reached: no fixture deletes a GiST page while a snapshot is held; g08''s snapshot makes its maintenance VACUUM delete nothing, and its second VACUUM deletes pages only after the release'),
 ('non-btree','GiST: a sorted build beside a non-sorted one','skipped on 12: no GiST operator class has support function 11, so g09 is insert-driven like g06 to g08'),
 ('non-btree','SP-GiST: redirects turned into placeholders, a trailing run removed, an interior one retained','s09, read from VACUUM''s counters: no SP-GiST decoder'),
 ('non-btree','SP-GiST: an emptied non-root page and the root page','s09, the same limit'),
 ('non-btree','BRIN: an unsummarized range measured before the maintenance step, and the same index after it','b13'),
 ('non-btree','BRIN: a desummarized range, and a range summarized by the stand-in','b13'),
 ('non-btree','BRIN: a same-page summary update beside one that moved to another page','b10 and b12; b11, the source page''s moved case, is not built on 12'),
 ('non-btree','BRIN: more than one pages_per_range','b12 at 32 beside b10 at 128'),
 ('non-btree','all: the maintenance pair','every churned fixture: churn_raw beside churn_maintained'),
 ('non-btree','all: an index maintained by the auto-analyze stand-in, a plain ANALYZE','h05'),
 ('non-btree','all: a table the census analyzed, and one it declined','tc_past and tc_exact'),
 ('non-btree','all: an empty index and an untouched index','h07 and h00'),
 ('non-btree','all: a non-default fillfactor, or for BRIN a non-default pages_per_range','h03, s10 and b12'),
 ('non-btree','a non-core access method under the four-part admission rule','skipped: no bloom fixture is in the ported corpus'),
 ('gin','keys that no longer occur after churn','n04'),
 ('gin','emptied posting-tree pages','n03 and n10'),
 ('gin','half-empty posting-tree leaves with nothing deletable','n04'),
 ('gin','a populated pending list, and the same index after a flush','n05'),
 ('gin','an untouched index and an empty index','n08 and n09'),
 ('gin','a snapshot held across the settling VACUUM','n10: its maintenance VACUUM runs under the snapshot and deletes no page; its posting-tree pages are deleted by the second VACUUM, after the release'),
 ('gin','more than one operator class','n06 (jsonb_path_ops) and n07 (tsvector_ops) beside array_ops'),
 ('gin','one rebuild at more than one maintenance_work_mem','probe P3'),
 ('gin','a churned index whose maintenance step ran, beside the same churn before it','every churned GIN fixture'),
 ('gin','an index maintained by the auto-analyze stand-in, ANALYZE plus gin_clean_pending_list','n12'),
 ('gin','a table the census analyzed, and one it declined to analyze','tc_past and tc_exact'),
 ('gin','an undecodable or unclassifiable page, and an all-zero page','skipped: the method reads no index page'),
 ('gin','a concurrent VACUUM, a concurrent rebuild and a writer stream','skipped: every measurement is single-session under the measurement lock');
SQL
  { q "$PDB" "SELECT column_name || ' -> ' || declared_kind FROM declared_kind ORDER BY 1"
    q "$PDB" "SELECT knob || ': ' || value FROM declared_decision ORDER BY 1"
    q "$PDB" "SELECT fixture || ' ' || action || ' ' || score FROM declared_prediction ORDER BY 1"
    q "$PDB" "SELECT id || ': ' || claim FROM declared_invariant ORDER BY substring(id from 2)::int"
    q "$PDB" "SELECT id || ' ' || fixture || ': ' || state FROM declared_exception ORDER BY 1"
    q "$PDB" "SELECT protocol || ' | ' || behavior || ' -> ' || fixture FROM declared_coverage ORDER BY protocol, behavior"
    q "$PDB" "SELECT 'declarations filed at ' || to_char(min(filed_at) AT TIME ZONE 'UTC',
                     'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') FROM declared_kind"
  } > "$OUT/declared.txt"
  tail -1 "$OUT/declared.txt"
}

# ------------------------------------------------------- the census machinery
proto_ddl() {
  cat <<'SQL'
CREATE /* wiki_nbmaint_proto */ SCHEMA proto;
CREATE /* wiki_nbmaint_proto */ EXTENSION pageinspect;
CREATE /* wiki_nbmaint_proto */ EXTENSION pgstattuple;
CREATE /* wiki_nbmaint_proto */ EXTENSION pg_freespacemap;

-- One row per fixture, phase and metric: a stage that runs again replaces its
-- own rows, and anything that would record a second reading of the same
-- thing fails instead of doubling a score.
CREATE TABLE proto.meas (
  fixture text NOT NULL, phase text NOT NULL, metric text NOT NULL,
  num numeric, txt text, at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (fixture, phase, metric));

-- The stages that have changed the fixture database, in the order they ran.
CREATE TABLE proto.stage_log (
  stage text PRIMARY KEY, done_at timestamptz NOT NULL DEFAULT clock_timestamp());

-- The graduated FSM agreement on BRIN, page by page: the page's own free
-- space, the value its FSM category floor must read, and what pg_freespace
-- did read.
CREATE TABLE proto.brin_page (
  fixture text NOT NULL, phase text NOT NULL, blkno int NOT NULL,
  free_bytes int NOT NULL, fsm_expected int NOT NULL, fsm_read int, page_lsn numeric NOT NULL,
  evacuate boolean NOT NULL, PRIMARY KEY (fixture, phase, blkno));

CREATE FUNCTION proto.note(p_fix text, p_phase text, p_metric text,
                           p_num numeric DEFAULT NULL, p_txt text DEFAULT NULL)
RETURNS void LANGUAGE sql AS $fn$
  INSERT INTO proto.meas(fixture, phase, metric, num, txt)
  VALUES (p_fix, p_phase, p_metric, p_num, p_txt);
$fn$;

-- Every non-B-tree index in public: its file, its table's count and its
-- comment, with the payload decoded - independently of the texts, as JSON,
-- out of the comment's one reserved line.  The payloads read here were
-- written by step 2, so the jsonb cast is safe; a cast that raised would stop
-- the run.  One row per phase and index.
CREATE TABLE proto.snap (
  phase text NOT NULL, idx text NOT NULL, oid oid, filenode oid, bytes bigint,
  tbl_tuples numeric, cmt text, pv numeric, sz numeric, tup numeric,
  at timestamptz NOT NULL DEFAULT clock_timestamp(), UNIQUE (phase, idx));
CREATE FUNCTION proto.take_snap(p_phase text) RETURNS void LANGUAGE sql AS $fn$
  INSERT INTO proto.snap(phase, idx, oid, filenode, bytes, tbl_tuples, cmt, pv, sz, tup)
  SELECT p_phase, c.relname, c.oid, c.relfilenode, pg_relation_size(c.oid),
         t.reltuples::numeric, d.description,
         (substring(d.description from '(?n)^@nbmaint:(\{.*\})$')::jsonb ->> 'v')::numeric,
         (substring(d.description from '(?n)^@nbmaint:(\{.*\})$')::jsonb ->> 'sz')::numeric,
         (substring(d.description from '(?n)^@nbmaint:(\{.*\})$')::jsonb ->> 'tup')::numeric
    FROM pg_class c
    JOIN pg_index x ON x.indexrelid = c.oid
    JOIN pg_class t ON t.oid = x.indrelid
    JOIN pg_am a    ON a.oid = c.relam
    LEFT JOIN pg_description d ON d.objoid = c.oid
                             AND d.classoid = 'pg_class'::regclass AND d.objsubid = 0
   WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'i'
     AND a.amname <> 'btree';
$fn$;

-- One census per access method, because the pinned tree offers a different
-- reader for each and refuses two of them outright.  Every per-block decode
-- runs in its own exception block, so a page the shipped reader will not
-- classify is counted as unreadable instead of failing the census.
CREATE FUNCTION proto.census_hash(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  n int; nblocks int; t text;
  c_meta int := 0; c_bucket int := 0; c_ovfl int := 0; c_bitmap int := 0;
  c_unused int := 0; c_bad int := 0;
  fb int := 0; fb_agree int := 0; fb_dis int := 0; st record; hs record;
  pgst_free numeric; pgst_err text;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass, 'main') / blk;
  FOR n IN 0 .. nblocks - 1 LOOP
    BEGIN
      t := hash_page_type(get_raw_page(p_idx, n));
    EXCEPTION WHEN OTHERS THEN
      t := 'unreadable';
    END;
    CASE t
      WHEN 'metapage' THEN c_meta := c_meta + 1;
      WHEN 'bucket'   THEN c_bucket := c_bucket + 1;
      WHEN 'overflow' THEN c_ovfl := c_ovfl + 1;
      WHEN 'bitmap'   THEN c_bitmap := c_bitmap + 1;
      WHEN 'unused'   THEN c_unused := c_unused + 1;
      ELSE c_bad := c_bad + 1;
    END CASE;
    -- I4: a block the bitmap calls free must read back as an unused page.
    -- The reader refuses a metapage or a bitmap block by design, so those are
    -- excluded rather than counted as disagreements.
    BEGIN
      SELECT * INTO hs FROM hash_bitmap_info(p_idx::regclass, n);
      IF NOT hs.bitstatus THEN
        fb := fb + 1;
        IF t = 'unused' OR t = 'unreadable' THEN fb_agree := fb_agree + 1;
        ELSE fb_dis := fb_dis + 1; END IF;
      END IF;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;
  END LOOP;
  SELECT * INTO hs FROM pgstathashindex(p_idx::regclass);
  -- pgstattuple's hash reader is refused by an all-zero page on a server
  -- without commit 036decbba2, so a refusal is recorded, not fatal
  BEGIN
    SELECT * INTO st FROM pgstattuple(p_idx::regclass);
    pgst_free := st.free_percent;
  EXCEPTION WHEN OTHERS THEN
    pgst_err := SQLERRM;
  END;
  IF pgst_err IS NOT NULL THEN
    INSERT INTO proto.meas(fixture, phase, metric, txt) VALUES (p_fix, p_phase, 'pgst_refusal', pgst_err);
  END IF;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
   (p_fix, p_phase, 'census_scanned',    nblocks),
   (p_fix, p_phase, 'census_meta',       c_meta),
   (p_fix, p_phase, 'census_bucket',     c_bucket),
   (p_fix, p_phase, 'census_overflow',   c_ovfl),
   (p_fix, p_phase, 'census_bitmap',     c_bitmap),
   (p_fix, p_phase, 'census_unused',     c_unused),
   (p_fix, p_phase, 'census_unreadable', c_bad),
   (p_fix, p_phase, 'bitmap_free',       fb),
   (p_fix, p_phase, 'bitmap_agree',      fb_agree),
   (p_fix, p_phase, 'bitmap_disagree',   fb_dis),
   (p_fix, p_phase, 'hs_bucket_pages',   hs.bucket_pages),
   (p_fix, p_phase, 'hs_overflow_pages', hs.overflow_pages),
   (p_fix, p_phase, 'hs_bitmap_pages',   hs.bitmap_pages),
   (p_fix, p_phase, 'hs_unused_pages',   hs.unused_pages),
   (p_fix, p_phase, 'hs_live_items',     hs.live_items),
   (p_fix, p_phase, 'hs_dead_items',     hs.dead_items),
   (p_fix, p_phase, 'pgst_free_percent', pgst_free),
   (p_fix, p_phase, 'size_after_census', pg_relation_size(p_idx::regclass, 'main'));
END $fn$;

-- pageinspect on this server has no GiST decoder, so the page class is read
-- out of the raw page: GISTPageOpaqueData sits in the special area as nsn
-- (8 bytes), rightlink (4), flags (uint16) and gist_page_id (uint16), little
-- endian on this platform.  F_LEAF is bit 0, F_DELETED bit 1, and a page
-- whose id is not GIST_PAGE_ID (0xFF81) is counted as unreadable.
CREATE FUNCTION proto.census_gist(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  n int; nblocks int; raw bytea; fl int; pid int; hdr record;
  c_leaf int := 0; c_inner int := 0; c_del int := 0; c_zero int := 0; c_bad int := 0;
  fsm_free int;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass, 'main') / blk;
  FOR n IN 0 .. nblocks - 1 LOOP
    BEGIN
      raw := get_raw_page(p_idx, n);
      SELECT * INTO hdr FROM page_header(raw);
      IF hdr.lower = 0 AND hdr.upper = 0 THEN
        c_zero := c_zero + 1;
        CONTINUE;
      END IF;
      fl  := get_byte(raw, hdr.special + 12) + 256 * get_byte(raw, hdr.special + 13);
      pid := get_byte(raw, hdr.special + 14) + 256 * get_byte(raw, hdr.special + 15);
      IF pid <> 65409 THEN c_bad := c_bad + 1;
      ELSIF fl & 2 <> 0 THEN c_del := c_del + 1;
      ELSIF fl & 1 <> 0 THEN c_leaf := c_leaf + 1;
      ELSE c_inner := c_inner + 1;
      END IF;
    EXCEPTION WHEN OTHERS THEN
      c_bad := c_bad + 1;
    END;
  END LOOP;
  SELECT count(*) INTO fsm_free FROM pg_freespace(p_idx::regclass) WHERE avail > 0;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
   (p_fix, p_phase, 'census_scanned',    nblocks),
   (p_fix, p_phase, 'census_leaf',       c_leaf),
   (p_fix, p_phase, 'census_inner',      c_inner),
   (p_fix, p_phase, 'census_deleted',    c_del),
   (p_fix, p_phase, 'census_new',        c_zero),
   (p_fix, p_phase, 'census_unreadable', c_bad),
   (p_fix, p_phase, 'fsm_free_pages',    fsm_free),
   (p_fix, p_phase, 'size_after_census', pg_relation_size(p_idx::regclass, 'main'));
END $fn$;

-- pageinspect ships no SP-GiST decoder, so this census is the page header and
-- nothing else, and every page-class quantity derived from it is a level.
-- A header does show the one class SP-GiST's VACUUM counts and frees: a page
-- that is new or holds no line pointer, outside the metapage (block 0) and
-- the two root pages (blocks 1 and 2), which VACUUM never frees.
CREATE FUNCTION proto.census_spgist(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  hdr_size int := 24;    -- SizeOfPageHeaderData: offsetof(PageHeaderData, pd_linp)
  n int; nblocks int; hdr record;
  c_used int := 0; c_zero int := 0; c_empty int := 0; c_bad int := 0; fsm_free int;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass, 'main') / blk;
  FOR n IN 0 .. nblocks - 1 LOOP
    BEGIN
      SELECT * INTO hdr FROM page_header(get_raw_page(p_idx, n));
      IF hdr.lower = 0 AND hdr.upper = 0 THEN c_zero := c_zero + 1;
      ELSE c_used := c_used + 1;
      END IF;
      -- PageIsNew or PageIsEmpty, on a block VACUUM is allowed to free
      IF n >= 3 AND hdr.lower <= hdr_size THEN c_empty := c_empty + 1; END IF;
    EXCEPTION WHEN OTHERS THEN c_bad := c_bad + 1;
    END;
  END LOOP;
  SELECT count(*) INTO fsm_free FROM pg_freespace(p_idx::regclass) WHERE avail > 0;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
   (p_fix, p_phase, 'census_scanned',      nblocks),
   (p_fix, p_phase, 'census_used',         c_used),
   (p_fix, p_phase, 'census_new',          c_zero),
   (p_fix, p_phase, 'census_new_or_empty', c_empty),
   (p_fix, p_phase, 'census_unreadable',   c_bad),
   (p_fix, p_phase, 'fsm_free_pages',      fsm_free),
   (p_fix, p_phase, 'size_after_census',   pg_relation_size(p_idx::regclass, 'main'));
END $fn$;

-- The BRIN census.  Beside the page classes and the summaries it runs the
-- graduated FSM agreement the non-B-tree protocol requires, page by page:
-- every regular page's pg_freespace against that page's own free space as
-- br_page_get_freespace computes it - pd_upper minus pd_lower less one line
-- pointer, or 0 on a page flagged BRIN_EVACUATE_PAGE - rounded down to its
-- FSM category, block_size / 256 bytes wide.  The flags and the page type are
-- read out of the raw page: BrinSpecialSpace holds MAXALIGN(1) / 2 uint16s,
-- the flags next to last and the type last, little endian on this platform,
-- and a regular page whose type does not read 0xF093 there is unreadable.
CREATE FUNCTION proto.census_brin(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  bsz int := current_setting('block_size')::int;
  step int := current_setting('block_size')::int / 256;
  ma int;
  n int; nblocks int; t text; k int; un int; raw bytea; hdr record;
  flags_w int; type_w int; free_b int; want int; got int;
  c_meta int := 0; c_revmap int := 0; c_reg int := 0; c_bad int := 0;
  items bigint := 0; unused bigint := 0; revmap_entries bigint := 0;
  fsm_free int; f_agree int := 0; f_high int := 0; f_low int := 0; f_evac int := 0;
BEGIN
  SELECT max_data_alignment INTO ma FROM pg_control_init();
  nblocks := pg_relation_size(p_idx::regclass, 'main') / bsz;
  FOR n IN 0 .. nblocks - 1 LOOP
    BEGIN
      raw := get_raw_page(p_idx, n);
      t := brin_page_type(raw);
    EXCEPTION WHEN OTHERS THEN
      t := 'unreadable';
    END;
    IF t = 'meta' THEN c_meta := c_meta + 1;
    ELSIF t = 'revmap' THEN
      c_revmap := c_revmap + 1;
      SELECT count(*) INTO k FROM brin_revmap_data(raw) r
       WHERE r.pages IS NOT NULL AND r.pages::text <> '(0,0)';
      revmap_entries := revmap_entries + k;
    ELSIF t = 'regular' THEN
      BEGIN
        -- one row per (item, attnum); an unused line pointer - what a moved
        -- summary or a desummarize leaves behind - comes back with blknum NULL
        SELECT count(DISTINCT bi.itemoffset) FILTER (WHERE bi.blknum IS NOT NULL),
               count(DISTINCT bi.itemoffset) FILTER (WHERE bi.blknum IS NULL)
          INTO k, un
          FROM brin_page_items(raw, p_idx::regclass) bi;
        SELECT * INTO hdr FROM page_header(raw);
        flags_w := get_byte(raw, hdr.special + ma - 4) + 256 * get_byte(raw, hdr.special + ma - 3);
        type_w  := get_byte(raw, hdr.special + ma - 2) + 256 * get_byte(raw, hdr.special + ma - 1);
        IF type_w <> 61587 THEN     -- BRIN_PAGETYPE_REGULAR, 0xF093
          RAISE EXCEPTION 'block % does not read as a regular BRIN page', n;
        END IF;
        c_reg := c_reg + 1;
        items := items + k;
        unused := unused + un;
        IF flags_w & 1 <> 0 THEN    -- BRIN_EVACUATE_PAGE
          free_b := 0; f_evac := f_evac + 1;
        ELSE
          free_b := greatest(hdr.upper - hdr.lower - 4, 0);   -- less one ItemIdData
        END IF;
        want := least(free_b / step, 254) * step;
        got := pg_freespace(p_idx::regclass, n);
        INSERT INTO proto.brin_page (fixture, phase, blkno, free_bytes, fsm_expected, page_lsn,
                                     fsm_read, evacuate)
             VALUES (p_fix, p_phase, n, free_b, want, hdr.lsn - '0/0'::pg_lsn, got, flags_w & 1 <> 0);
        IF got = want THEN f_agree := f_agree + 1;
        ELSIF got > want THEN f_high := f_high + 1;
        ELSE f_low := f_low + 1;
        END IF;
      EXCEPTION WHEN OTHERS THEN
        c_bad := c_bad + 1;
      END;
    ELSE c_bad := c_bad + 1;
    END IF;
  END LOOP;
  SELECT count(*) INTO fsm_free FROM pg_freespace(p_idx::regclass) WHERE avail > 0;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
   (p_fix, p_phase, 'census_scanned',      nblocks),
   (p_fix, p_phase, 'census_meta',         c_meta),
   (p_fix, p_phase, 'census_revmap',       c_revmap),
   (p_fix, p_phase, 'census_regular',      c_reg),
   (p_fix, p_phase, 'census_unreadable',   c_bad),
   (p_fix, p_phase, 'brin_items',          items),
   (p_fix, p_phase, 'brin_unused_items',   unused),
   (p_fix, p_phase, 'brin_revmap_entries', revmap_entries),
   (p_fix, p_phase, 'brin_fsm_agree',      f_agree),
   (p_fix, p_phase, 'brin_fsm_higher',     f_high),
   (p_fix, p_phase, 'brin_fsm_lower',      f_low),
   (p_fix, p_phase, 'brin_evacuate_pages', f_evac),
   (p_fix, p_phase, 'fsm_free_pages',      fsm_free),
   (p_fix, p_phase, 'size_after_census',   pg_relation_size(p_idx::regclass, 'main'));
END $fn$;

CREATE FUNCTION proto.census_gin(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  n int; nblocks int; fl text[]; hdr record; m record;
  c_entry int := 0; c_data int := 0; c_list int := 0; c_del int := 0;
  c_zero int := 0; c_bad int := 0; fsm_free int;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass, 'main') / blk;
  SELECT * INTO m FROM gin_metapage_info(get_raw_page(p_idx, 0));
  FOR n IN 1 .. nblocks - 1 LOOP
    BEGIN
      SELECT * INTO hdr FROM page_header(get_raw_page(p_idx, n));
      IF hdr.lower = 0 AND hdr.upper = 0 THEN
        c_zero := c_zero + 1;
        CONTINUE;
      END IF;
      SELECT flags INTO fl FROM gin_page_opaque_info(get_raw_page(p_idx, n));
      IF fl @> ARRAY['deleted'] THEN c_del := c_del + 1;
      ELSIF fl @> ARRAY['list'] THEN c_list := c_list + 1;
      ELSIF fl @> ARRAY['data'] THEN c_data := c_data + 1;
      ELSE c_entry := c_entry + 1;
      END IF;
    EXCEPTION WHEN OTHERS THEN c_bad := c_bad + 1;
    END;
  END LOOP;
  SELECT count(*) INTO fsm_free FROM pg_freespace(p_idx::regclass) WHERE avail > 0;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
   (p_fix, p_phase, 'census_scanned',     nblocks),
   (p_fix, p_phase, 'census_entry',       c_entry),
   (p_fix, p_phase, 'census_data',        c_data),
   (p_fix, p_phase, 'census_list',        c_list),
   (p_fix, p_phase, 'census_deleted',     c_del),
   (p_fix, p_phase, 'census_new',         c_zero),
   (p_fix, p_phase, 'census_unreadable',  c_bad),
   (p_fix, p_phase, 'meta_total_pages',   m.n_total_pages),
   (p_fix, p_phase, 'meta_entry_pages',   m.n_entry_pages),
   (p_fix, p_phase, 'meta_data_pages',    m.n_data_pages),
   (p_fix, p_phase, 'meta_pending_pages', m.n_pending_pages),
   (p_fix, p_phase, 'fsm_free_pages',     fsm_free),
   (p_fix, p_phase, 'size_after_census',  pg_relation_size(p_idx::regclass, 'main'));
END $fn$;

CREATE FUNCTION proto.census(p_fix text, p_phase text, p_tab text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE am text;
BEGIN
  SELECT a.amname INTO am FROM pg_class c JOIN pg_am a ON a.oid = c.relam
   WHERE c.oid = p_idx::regclass;
  PERFORM proto.note(p_fix, p_phase, 'size_before_census',
                     pg_relation_size(p_idx::regclass, 'main'));
  CASE am
    WHEN 'hash'   THEN PERFORM proto.census_hash(p_fix, p_phase, p_idx);
    WHEN 'gist'   THEN PERFORM proto.census_gist(p_fix, p_phase, p_idx);
    WHEN 'spgist' THEN PERFORM proto.census_spgist(p_fix, p_phase, p_idx);
    WHEN 'brin'   THEN PERFORM proto.census_brin(p_fix, p_phase, p_idx);
    WHEN 'gin'    THEN PERFORM proto.census_gin(p_fix, p_phase, p_idx);
  END CASE;
END $fn$;

-- one reading of everything the method and the cross-checks can see
CREATE FUNCTION proto.record(p_fix text, p_phase text, p_tab text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE s record; ct record; ci record;
BEGIN
  SELECT reltuples, relpages INTO ct FROM pg_class WHERE oid = p_tab::regclass;
  SELECT reltuples, relpages, relfilenode INTO ci FROM pg_class WHERE oid = p_idx::regclass;
  SELECT n_tup_ins, n_tup_upd, n_tup_hot_upd, n_tup_del, n_live_tup, n_dead_tup,
         n_mod_since_analyze, analyze_count, vacuum_count
    INTO s FROM pg_stat_all_tables WHERE relid = p_tab::regclass;
  INSERT INTO proto.meas(fixture, phase, metric, num) VALUES
    (p_fix, p_phase, 'index_size',          pg_relation_size(p_idx::regclass, 'main')),
    (p_fix, p_phase, 'index_relpages',      ci.relpages),
    (p_fix, p_phase, 'index_reltuples',     ci.reltuples),
    (p_fix, p_phase, 'index_filenode',      ci.relfilenode::bigint),
    (p_fix, p_phase, 'table_size',          pg_relation_size(p_tab::regclass, 'main')),
    (p_fix, p_phase, 'table_relpages',      ct.relpages),
    (p_fix, p_phase, 'table_reltuples',     ct.reltuples),
    (p_fix, p_phase, 'n_tup_ins',           s.n_tup_ins),
    (p_fix, p_phase, 'n_tup_upd',           s.n_tup_upd),
    (p_fix, p_phase, 'n_tup_hot_upd',       s.n_tup_hot_upd),
    (p_fix, p_phase, 'n_tup_del',           s.n_tup_del),
    (p_fix, p_phase, 'n_live_tup',          s.n_live_tup),
    (p_fix, p_phase, 'n_dead_tup',          s.n_dead_tup),
    (p_fix, p_phase, 'n_mod_since_analyze', s.n_mod_since_analyze),
    (p_fix, p_phase, 'analyze_count',       s.analyze_count),
    (p_fix, p_phase, 'vacuum_count',        s.vacuum_count);
END $fn$;
SQL
}

# ---------------------------------------------------------- fixture recipes --
# 28 of the source page's 29 numbered fixtures, recipe for recipe: b11 is not
# built on 12.  Every
# statement is DISPOSABLE fixture DDL and DML.  The build phase is: create the
# table, load it, ANALYZE, create the scored index, ANALYZE again.
fx_build() {
  local f="$1" t i
  t=$(tbl "$f"); i=$(idx "$f")
  case "$f" in
    h00|h01|h02|h04|h05|h08)
      cat <<SQL
CREATE TABLE $t (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, g FROM generate_series(1,$BASE_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING hash (k);
ANALYZE $t;
SQL
      ;;
    h03)
      cat <<SQL
CREATE TABLE $t (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, g FROM generate_series(1,$BASE_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING hash (k) WITH (fillfactor = 50);
ANALYZE $t;
SQL
      ;;
    h07)
      cat <<SQL
CREATE TABLE $t (id bigint, k bigint) WITH (autovacuum_enabled = off);
ANALYZE $t;
CREATE INDEX $i ON $t USING hash (k);
ANALYZE $t;
SQL
      ;;
    h12)
      cat <<SQL
CREATE TABLE $t (id bigint, state text, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, CASE WHEN g % 10 = 0 THEN 'pending' ELSE 'done' END, g
  FROM generate_series(1,$BRIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING hash (k) WHERE state = 'pending';
ANALYZE $t;
SQL
      ;;
    g06|g07)
      cat <<SQL
CREATE TABLE $t (id bigint, r int8range) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, int8range(g, g+10) FROM generate_series(1,$BASE_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gist (r);
ANALYZE $t;
SQL
      ;;
    g08)
      cat <<SQL
CREATE TABLE $t (id bigint, r int8range) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, int8range(g, g+10) FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gist (r);
ANALYZE $t;
SQL
      ;;
    g09)
      # on 17 point_ops carries GIST_SORTSUPPORT_PROC and this is the sorted
      # build; on this server no GiST opclass has it, so g09 is insert-driven
      cat <<SQL
CREATE TABLE $t (id bigint, p point) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, point((g % 100000)::float8, (g / 100000)::float8)
  FROM generate_series(1,$BASE_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gist (p);
ANALYZE $t;
SQL
      ;;
    s08|s09)
      cat <<SQL
CREATE TABLE $t (id bigint, t text) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, 'aaa' || lpad(g::text, 12, '0') FROM generate_series(1,$BASE_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING spgist (t);
ANALYZE $t;
SQL
      ;;
    s10)
      cat <<SQL
CREATE TABLE $t (id bigint, t text) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, 'aaa' || lpad(g::text, 12, '0') FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING spgist (t) WITH (fillfactor = 50);
ANALYZE $t;
SQL
      ;;
    b10)
      cat <<SQL
CREATE TABLE $t (id bigint, v bigint) WITH (autovacuum_enabled = off, fillfactor = 90);
INSERT INTO $t SELECT g, g FROM generate_series(1,$BRIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING brin (v) WITH (pages_per_range = 128);
ANALYZE $t;
SQL
      ;;
    b12)
      cat <<SQL
CREATE TABLE $t (id bigint, v bigint) WITH (autovacuum_enabled = off, fillfactor = 90);
INSERT INTO $t SELECT g, g FROM generate_series(1,$BRIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING brin (v) WITH (pages_per_range = 32);
ANALYZE $t;
SQL
      ;;
    b13)
      cat <<SQL
CREATE TABLE $t (id bigint, v bigint) WITH (autovacuum_enabled = off, fillfactor = 90);
INSERT INTO $t SELECT g, g FROM generate_series(1,$BRIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING brin (v) WITH (pages_per_range = 128, autosummarize = on);
ANALYZE $t;
SQL
      ;;
    n03|n04|n08)
      cat <<SQL
CREATE TABLE $t (id bigint, arr text[]) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, ARRAY['a'||g, 'b'||(g%50000), 'c'||(g%1000)]
  FROM generate_series(1,$GIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (arr) WITH (fastupdate = off);
ANALYZE $t;
SQL
      ;;
    n05|n12)
      cat <<SQL
CREATE TABLE $t (id bigint, arr text[]) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, ARRAY['a'||g, 'b'||(g%50000), 'c'||(g%1000)]
  FROM generate_series(1,$GIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (arr) WITH (fastupdate = on);
ANALYZE $t;
SQL
      ;;
    n06)
      cat <<SQL
CREATE TABLE $t (id bigint, j jsonb) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, jsonb_build_object('a', 'a'||g, 'b', 'b'||(g%50000), 'c', 'c'||(g%1000))
  FROM generate_series(1,$GIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (j jsonb_path_ops);
ANALYZE $t;
SQL
      ;;
    n07)
      cat <<SQL
CREATE TABLE $t (id bigint, d tsvector) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, to_tsvector('simple', 'a'||g||' b'||(g%50000)||' c'||(g%1000))
  FROM generate_series(1,$GIN_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (d);
ANALYZE $t;
SQL
      ;;
    n09)
      cat <<SQL
CREATE TABLE $t (id bigint, arr text[]) WITH (autovacuum_enabled = off);
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (arr) WITH (fastupdate = off);
ANALYZE $t;
SQL
      ;;
    n10)
      # three hot keys, so every key owns a posting tree; the churn deletes a
      # contiguous id band, so whole posting-tree leaves empty
      cat <<SQL
CREATE TABLE $t (id bigint, arr text[]) WITH (autovacuum_enabled = off);
INSERT INTO $t SELECT g, ARRAY['hot1','hot2','hot3']
  FROM generate_series(1,$HOT_ROWS) g;
ANALYZE $t;
CREATE INDEX $i ON $t USING gin (arr) WITH (fastupdate = off);
ANALYZE $t;
SQL
      ;;
    *) die "no build recipe for fixture $f" ;;
  esac
}

# The recipe's own writes.  Nothing here maintains anything: the maintenance
# step is fx_maint, and it always runs before the decide phase.
fx_churn() {
  local f="$1" t r
  t=$(tbl "$f")
  case "$f" in
    h00|h07|n08|n09) : ;;   # no churn at all
    h01) printf 'UPDATE %s SET k = %s + (id %% 100);\n' "$t" "$BASE_ROWS" ;;
    h02) printf 'INSERT INTO %s SELECT g, g FROM generate_series(%s,%s) g;\nDELETE FROM %s WHERE id > %s;\n' \
           "$t" "$((BASE_ROWS+1))" "$((BASE_ROWS*5))" "$t" "$BASE_ROWS" ;;
    h03) printf 'UPDATE %s SET k = k + %s WHERE id %% 2 = 0;\n' "$t" "$BASE_ROWS" ;;
    h04) printf 'INSERT INTO %s SELECT g, g FROM generate_series(%s,%s) g;\n' \
           "$t" "$((BASE_ROWS+1))" "$((BASE_ROWS+BASE_ROWS*2/5))" ;;
    h05) printf 'INSERT INTO %s SELECT g, g FROM generate_series(%s,%s) g;\n' \
           "$t" "$((BASE_ROWS+1))" "$((BASE_ROWS+A05_INSERTS))" ;;
    h08) printf 'UPDATE %s SET k = k + %s WHERE id %% 100 = 0;\n' "$t" "$BASE_ROWS" ;;
    h12) printf "UPDATE %s SET state = 'pending' WHERE id %% 10 BETWEEN 1 AND 8;\n" "$t" ;;
    g06) for r in $(seq 1 "$ROUNDS"); do
           printf 'UPDATE %s SET r = int8range((id * 7 + %s * 1000003) %% 100000000,\n                                 (id * 7 + %s * 1000003) %% 100000000 + 10);\n' \
             "$t" "$r" "$r"
         done ;;
    g07) printf 'INSERT INTO %s SELECT g, int8range(g, g+10) FROM generate_series(%s,%s) g;\nDELETE FROM %s WHERE id > %s;\n' \
           "$t" "$((BASE_ROWS+1))" "$((BASE_ROWS*4))" "$t" "$BASE_ROWS" ;;
    # a contiguous id band, not a modulus: the keys correlate with id, so
    # deleting the top 80 % empties whole leaves instead of thinning every one
    g08) printf 'DELETE FROM %s WHERE id > %s;\n' "$t" "$((SMALL_ROWS/5))" ;;
    g09) for r in $(seq 1 "$ROUNDS"); do
           printf 'UPDATE %s SET p = point((((id * 7 + %s * 1000003) %% 100000))::float8,\n                            (((id * 13 + %s * 1000003) %% 10000))::float8);\n' \
             "$t" "$r" "$r"
         done ;;
    s08) for r in $(seq 1 "$ROUNDS"); do
           printf "UPDATE %s SET t = chr(98 + %s) || chr(112 + %s) || chr(103 + %s)\n       || lpad(((id * 7919 + %s * 104729) %% 1000000)::text, 12, '0');\n" \
             "$t" "$r" "$r" "$r" "$r"
         done ;;
    s09) printf "INSERT INTO %s SELECT g, 'zzz' || lpad(g::text, 12, '0') FROM generate_series(%s,%s) g;\nDELETE FROM %s WHERE id > %s;\n" \
           "$t" "$((BASE_ROWS+1))" "$((BASE_ROWS*4))" "$t" "$BASE_ROWS" ;;
    s10) printf "DELETE FROM %s WHERE id %% 10 < 3;\nUPDATE %s SET t = 'bbb' || lpad(((id * 7919) %% 1000000)::text, 12, '0') WHERE id %% 10 >= 7;\n" \
           "$t" "$t" ;;
    b10) for r in $(seq 1 "$ROUNDS"); do
           printf 'UPDATE %s SET v = (id * 7919 + %s * 104729) %% %s;\n' "$t" "$r" "$BRIN_ROWS"
         done ;;
    b12) for r in $(seq 1 3); do
           printf 'UPDATE %s SET v = (id * 7919 + %s * 104729) %% %s;\n' "$t" "$r" "$BRIN_ROWS"
         done ;;
    b13) printf 'INSERT INTO %s SELECT g, g FROM generate_series(%s,%s) g;\n' \
           "$t" "$((BRIN_ROWS+1))" "$((BRIN_ROWS+BRIN_ROWS/2))" ;;
    n03) printf "INSERT INTO %s SELECT g, ARRAY['hot1','hot2','hot3'] FROM generate_series(%s,%s) g;\nDELETE FROM %s WHERE id > %s;\n" \
           "$t" "$((GIN_ROWS+1))" "$((GIN_ROWS*4))" "$t" "$GIN_ROWS" ;;
    n04) for r in $(seq 1 "$ROUNDS"); do
           printf "UPDATE %s SET arr = ARRAY['r%sk'||id, 'r%sm'||(id%%20000), 'r%sn'||(id%%500)];\n" \
             "$t" "$r" "$r" "$r"
         done ;;
    n05) printf "SET gin_pending_list_limit = '1GB';\nINSERT INTO %s SELECT g, ARRAY['a'||g, 'b'||(g%%50000), 'c'||(g%%1000)]\n  FROM generate_series(%s,%s) g;\nRESET gin_pending_list_limit;\n" \
           "$t" "$((GIN_ROWS+1))" "$((GIN_ROWS+GIN_ROWS/2))" ;;
    n06) for r in $(seq 1 3); do
           printf "UPDATE %s SET j = jsonb_build_object('a', 'r%sa'||id, 'b', 'r%sb'||(id%%20000), 'c', 'r%sc'||(id%%500));\n" \
             "$t" "$r" "$r" "$r"
         done ;;
    n07) for r in $(seq 1 3); do
           printf "UPDATE %s SET d = to_tsvector('simple', 'r%sa'||id||' r%sb'||(id%%20000)||' r%sc'||(id%%500));\n" \
             "$t" "$r" "$r" "$r"
         done ;;
    n10) printf 'DELETE FROM %s WHERE id > %s;\n' "$t" "$((HOT_ROWS/5))" ;;
    n12) printf "SET gin_pending_list_limit = '1GB';\nINSERT INTO %s SELECT g, ARRAY['a'||g, 'b'||(g%%50000), 'c'||(g%%1000)]\n  FROM generate_series(%s,%s) g;\nRESET gin_pending_list_limit;\n" \
           "$t" "$((GIN_ROWS+1))" "$((GIN_ROWS+A05_INSERTS))" ;;
    *) die "no churn recipe for fixture $f" ;;
  esac
}

# The maintenance step.  The default is the mandatory VACUUM ANALYZE on the
# table the churn touched; two fixtures declare a different one.
fx_maint() {
  local f="$1" t i
  t=$(tbl "$f"); i=$(idx "$f")
  case "$f" in
    h05)
      # the auto-analyze stand-in on a non-GIN AM: a plain ANALYZE and nothing
      # else, because hash, GiST, SP-GiST and BRIN no-op in ANALYZE-only mode
      printf 'ANALYZE VERBOSE %s;\n' "$t" ;;
    n12)
      # the auto-analyze stand-in on GIN: ANALYZE plus the pending-list flush
      # that only an autovacuum worker's ANALYZE performs
      printf "ANALYZE VERBOSE %s;\nSELECT gin_clean_pending_list('%s'::regclass);\n" "$t" "$i" ;;
    *)
      printf 'VACUUM (VERBOSE, ANALYZE) %s;\n' "$t" ;;
  esac
}

# ------------------------------------------------------------ phase helpers --
# Every census that will be compared with anything runs in one transaction
# holding SHARE ROW EXCLUSIVE on the index's table, the measurement lock both
# protocols require, and records the interval it held it.
census_locked() {
  local db="$1" f="$2" ph="$3" t i
  t=$(tbl "$f"); i=$(idx "$f")
  qin "$db" > "$OUT/census-$f-$ph.log" 2>&1 <<SQL || die "census of $f ($ph) failed"
BEGIN /* wiki_nbmaint_census */;
SET LOCAL statement_timeout = '1800s';
SET LOCAL lock_timeout = '15s';
LOCK /* wiki_nbmaint_census */ TABLE $t IN SHARE ROW EXCLUSIVE MODE;
SELECT /* wiki_nbmaint_census */ proto.note('$f','$ph','lock_acquired',
         extract(epoch from clock_timestamp())::numeric);
SELECT /* wiki_nbmaint_census */ proto.census('$f','$ph','$t','$i');
SELECT /* wiki_nbmaint_census */ proto.record('$f','$ph','$t','$i');
SELECT /* wiki_nbmaint_census */ proto.note('$f','$ph','progress_vacuum',
         (SELECT count(*) FROM pg_stat_progress_vacuum WHERE relid = '$t'::regclass));
SELECT /* wiki_nbmaint_census */ proto.note('$f','$ph','progress_create_index',
         (SELECT count(*) FROM pg_stat_progress_create_index WHERE relid = '$t'::regclass));
SELECT /* wiki_nbmaint_census */ proto.note('$f','$ph','lock_released',
         extract(epoch from clock_timestamp())::numeric);
COMMIT /* wiki_nbmaint_census */;
SQL
}

# Who could have pinned the removal horizon at this instant: a backend with a
# transaction id or an xmin, a replication slot, a prepared transaction.  A
# read, not an interlock, so it is taken on both sides of every step.
horizon_probe() {
  local db="$1" f="$2" when="$3"
  qin "$db" > "$OUT/horizon-$f-$when.log" 2>&1 <<SQL || die "horizon probe failed"
SELECT /* wiki_nbmaint_horizon */ proto.note('$f','$when','horizon_backends',
         (SELECT count(*) FROM pg_stat_activity
           WHERE pid <> pg_backend_pid()
             AND (backend_xid IS NOT NULL OR backend_xmin IS NOT NULL)));
SELECT /* wiki_nbmaint_horizon */ proto.note('$f','$when','horizon_backend_detail', NULL,
         coalesce((SELECT string_agg(format('pid=%s type=%s state=%s xact_start=%s xid=%s xmin=%s',
                                            pid, backend_type, state, xact_start,
                                            backend_xid, backend_xmin), '; ')
                     FROM pg_stat_activity
                    WHERE pid <> pg_backend_pid()
                      AND (backend_xid IS NOT NULL OR backend_xmin IS NOT NULL)), 'none'));
SELECT /* wiki_nbmaint_horizon */ proto.note('$f','$when','horizon_slots',
         (SELECT count(*) FROM pg_replication_slots
           WHERE xmin IS NOT NULL OR catalog_xmin IS NOT NULL));
SELECT /* wiki_nbmaint_horizon */ proto.note('$f','$when','horizon_prepared',
         (SELECT count(*) FROM pg_prepared_xacts));
SQL
}

# The no-defeat rule, enforced the moment a maintenance step returns.  Reads
# the step's own log and the horizon probe taken before it, records the proofs,
# and dies - so no later stage runs and nothing is scored - if the maintenance
# was defeated.  Proofs: every settable timeout read 0 in the session; no skip,
# error or cancellation line; the VERBOSE "dead but not yet removable" count is
# 0 (a declared held snapshot must instead pin something); no horizon holder
# but a declared one.
check_maint() {
  local f="$1" db="$2" tag="$3" lg="$OUT/$3-$1.log"
  local vac=yes hold_ok=0 dead skips errs touts holders slots prep why=""
  case "$f" in h05|n12) vac=no ;; esac
  [ "$tag" = maint ] && case "$f" in g08|n10) hold_ok=1 ;; esac
  # this server's wording: "N dead row versions cannot be removed yet", the
  # first DETAIL line after "found X removable, Y nonremovable row versions"
  dead=$(grep -Eo '[0-9]+ dead row versions cannot be removed yet' "$lg" | head -1 | grep -Eo '^[0-9]+')
  skips=$(grep -Ec 'skipping (vacuum|analyze) of' "$lg")
  errs=$(grep -Ec 'ERROR:|canceling statement due to' "$lg")
  touts=$(grep -Eo 'timeouts in force: .*' "$lg" | head -1 | sed 's/^timeouts in force: //')
  holders=$(q "$db" "SELECT max(num) FROM proto.meas WHERE fixture='$f' AND phase='${tag}_before' AND metric='horizon_backends'")
  slots=$(q "$db" "SELECT max(num) FROM proto.meas WHERE fixture='$f' AND phase='${tag}_before' AND metric='horizon_slots'")
  prep=$(q "$db" "SELECT max(num) FROM proto.meas WHERE fixture='$f' AND phase='${tag}_before' AND metric='horizon_prepared'")
  q "$db" "SELECT proto.note('$f','$tag','dead_not_removable',${dead:-NULL}),
                  proto.note('$f','$tag','skip_lines',${skips:-0}),
                  proto.note('$f','$tag','error_lines',${errs:-0}),
                  proto.note('$f','$tag','session_timeouts',NULL,'${touts:-unrecorded}')" > /dev/null
  [ -n "$touts" ] || why="$why; no timeouts line in the session"
  printf '%s' "$touts" | grep -Eq '=[1-9]' && why="$why; a timeout was not 0 ($touts)"
  [ "${skips:-0}" = 0 ] || why="$why; $skips skip lines"
  [ "${errs:-0}" = 0 ] || why="$why; $errs error or cancellation lines"
  if [ "$vac" = yes ]; then
    if [ -z "$dead" ]; then
      why="$why; no VERBOSE dead-but-not-yet-removable count"
    elif [ "$hold_ok" = 1 ]; then
      [ "$dead" -gt 0 ] || why="$why; the declared snapshot pinned nothing"
    else
      [ "$dead" = 0 ] || why="$why; $dead tuples dead but not yet removable"
    fi
  fi
  [ "${holders:-x}" = "$hold_ok" ] || why="$why; ${holders:-?} horizon holders where $hold_ok was declared"
  [ "${slots:-x}" = 0 ] || why="$why; ${slots:-?} replication slots holding an xmin"
  [ "${prep:-x}" = 0 ] || why="$why; ${prep:-?} prepared transactions"
  if [ -n "$why" ]; then
    printf '%-4s %-7s DEFEATED%s\n' "$f" "$tag" "$why" >> "$OUT/maintenance-proof.txt"
    die "the maintenance of $f ($tag) was defeated$why: the run stops here and scores nothing"
  fi
  printf '%-4s %-7s ok  dead_not_removable=%-8s holders=%s slots=%s prepared=%s [%s]\n' \
    "$f" "$tag" "${dead:-n/a}" "$holders" "$slots" "$prep" "$touts" >> "$OUT/maintenance-proof.txt"
}

# Runs a fixture's maintenance step in a session whose timeouts are all 0,
# brackets it with two horizon probes and two timestamps, then checks it.
# $3 is the log basename: maint, or settle2 for the second VACUUM of X1/X2.
run_maint() {
  local f="$1" db="$2" tag="$3"
  horizon_probe "$db" "$f" "${tag}_before"
  # the WAL insert position just before the step: an index page whose LSN is
  # no newer than this was not written by the step (I18)
  q "$db" "SELECT proto.note('$f','$tag','started', extract(epoch from clock_timestamp())::numeric),
                  proto.note('$f','$tag','wal_lsn_before', pg_current_wal_insert_lsn() - '0/0'::pg_lsn)" > /dev/null
  fx_maint "$f" | qz "$db" > "$OUT/$tag-$f.log" 2>&1 \
    || die "maintenance of $f ($tag) failed, see $OUT/$tag-$f.log"
  q "$db" "SELECT proto.note('$f','$tag','ended', extract(epoch from clock_timestamp())::numeric)" > /dev/null
  horizon_probe "$db" "$f" "${tag}_after"
  check_maint "$f" "$db" "$tag"
}

# Opens a REPEATABLE READ transaction in a second session and holds its
# snapshot until release_snapshot terminates that backend.  The snapshot is
# fixed by the transaction's first query, and it must be opened BEFORE the
# churn commits: a snapshot taken afterwards holds nothing back.
SNAP_PID=""
hold_snapshot() {
  local db="$1" f="$2" n=0
  ( printf "BEGIN /* wiki_nbmaint_snapshot */ ISOLATION LEVEL REPEATABLE READ;\n"
    printf "SELECT /* wiki_nbmaint_snapshot */ 'snapshot holder pid ' || pg_backend_pid();\n"
    printf "SELECT /* wiki_nbmaint_snapshot */ pg_sleep(900);\n"
    printf "COMMIT /* wiki_nbmaint_snapshot */;\n" ) | qbg "$db" > "$OUT/snapshot-$f.log" 2>&1 &
  SNAP_PID=$!
  until [ "$(q "$db" "SELECT count(*) FROM pg_stat_activity
                       WHERE query LIKE '%wiki_nbmaint_snapshot%' AND backend_xmin IS NOT NULL
                         AND pid <> pg_backend_pid()")" = 1 ]; do
    n=$((n + 1)); [ "$n" -gt 60 ] && die "the declared snapshot for $f never took hold"
    sleep 0.5
  done
}
release_snapshot() {
  local db="$1" f="$2"
  q "$db" "SELECT proto.note('$f','snapshot','holders_terminated',
             (SELECT count(*) FROM pg_stat_activity
               WHERE query LIKE '%wiki_nbmaint_snapshot%' AND pid <> pg_backend_pid()))" > /dev/null
  q "$db" "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
            WHERE query LIKE '%wiki_nbmaint_snapshot%' AND pid <> pg_backend_pid()" > /dev/null
  [ -n "$SNAP_PID" ] && wait "$SNAP_PID" 2>/dev/null
  SNAP_PID=""
}

# ------------------------------------------------------------ stage order ----
# The stages that change the fixture database log themselves in
# proto.stage_log.  Each one checks the stages it depends on before it starts,
# and refuses to run again, or after a later stage has changed what it would
# read: to repeat one of those, start again at the fixtures stage.  The stages
# that only read, cross-check or re-score replace their own records instead.
need_texts() {
  [ -s "$SQLD/plan.sql" ] && [ -s "$SQLD/apply.sql" ] && [ -s "$SQLD/plan_view.sql" ] \
    || die "the page's texts have not been taken out yet: run the texts stage first"
}
need_db() {
  [ "$(q postgres "SELECT count(*) FROM pg_database WHERE datname = '$DB'")" = 1 ] \
    || die "no fixture database: run the fixtures stage first"
}
have_stage() { [ "$(q "$DB" "SELECT count(*) FROM proto.stage_log WHERE stage = '$1'")" = 1 ]; }
need_stage() {
  local s
  for s in "$@"; do have_stage "$s" || die "run the $s stage first"; done
  return 0
}
refuse_after() {   # <this stage> <stage...>: die if any of those already ran
  local me=$1 s; shift
  for s in "$@"; do
    if have_stage "$s"; then
      if [ "$s" = "$me" ]; then die "$me already ran on this fixture database: start again at the fixtures stage"; fi
      die "$me cannot run after $s has changed the fixtures: start again at the fixtures stage"
    fi
  done
  return 0
}
stage_done() {
  q "$DB" "INSERT INTO proto.stage_log (stage) VALUES ('$1')
           ON CONFLICT (stage) DO UPDATE SET done_at = clock_timestamp()" > /dev/null
}

# ----------------------------------------------------------- stage: fixtures -
stage_fixtures() {
  say "fixtures: build phase, locked baseline census, then step 2's first run"
  q postgres "SELECT count(*) FROM pg_database WHERE datname = '$PDB'" | grep -q '^1$' \
    || die "declarations are not filed: run the declare stage first"
  need_texts
  q postgres "DROP /* wiki_nbmaint_fixtures */ DATABASE IF EXISTS $DB" > /dev/null
  q postgres "CREATE /* wiki_nbmaint_fixtures */ DATABASE $DB" > /dev/null
  proto_ddl | qin "$DB" > "$OUT/proto-ddl.log" 2>&1 || die "proto DDL failed"
  local f n
  for f in $SCORED; do
    printf '  build %-4s (%s)\n' "$f" "$(fx_am "$f")"
    fx_build "$f" | qz "$DB" > "$OUT/build-$f.log" 2>&1 || die "build of $f failed, see $OUT/build-$f.log"
  done
  for f in $SCORED; do census_locked "$DB" "$f" baseline; done
  q "$DB" "SELECT fixture || ' ' || max(num) FILTER (WHERE metric = 'index_size') || ' bytes, table reltuples '
             || max(num) FILTER (WHERE metric = 'table_reltuples')
             FROM proto.meas WHERE phase = 'baseline' GROUP BY fixture ORDER BY fixture" \
    > "$OUT/baseline-sizes.txt"
  say "baseline: step 2, verbatim, first run: every fixture index is initialized"
  run_apply "$DB" baseline || die "step 2 (baseline) failed, see $OUT/apply-baseline.log"
  apply_summary baseline | tee "$OUT/baseline-apply.txt"
  q "$DB" "SELECT proto.take_snap('baseline')" > /dev/null
  n=$(q "$DB" "SELECT count(*) FROM proto.snap WHERE phase = 'baseline' AND pv = 2 AND idx ~ '^f_.*_i\$'")
  printf '%s fixture indexes carry a version-2 payload\n' "$n" | tee -a "$OUT/baseline-apply.txt"
  [ "$n" = "$(printf '%s\n' $SCORED | grep -c .)" ] || die "step 2's first run left a fixture index without a payload"
  date -u +'baselines filed at %Y-%m-%dT%H:%M:%SZ' | tee -a "$OUT/baseline-apply.txt"
  stage_done fixtures
}

# -------------------------------------------------------------- stage: churn -
# writes -> force the statistics flush -> census of the unmaintained state ->
# maintenance step, checked -> census of the maintained state.  The
# unmaintained census is a size and page reading only; the method is never
# asked about that state.
stage_churn() {
  say "churn: recipe writes, the maintenance step, the proofs, for every fixture"
  need_db; need_stage fixtures; refuse_after churn churn
  local f t i
  : > "$OUT/maintenance-proof.txt"
  for f in $SCORED; do
    t=$(tbl "$f"); i=$(idx "$f")
    printf '  churn %-4s (%s)\n' "$f" "$(fx_am "$f")"
    # X1 and X2 open their snapshot BEFORE the churn: that ordering is the
    # whole point, because only then do the deleted rows stay recently dead
    case "$f" in g08|n10) hold_snapshot "$DB" "$f" ;; esac
    fx_churn "$f" | qin "$DB" > "$OUT/churn-$f.log" 2>&1 || die "churn of $f failed, see $OUT/churn-$f.log"
    # no pg_stat_force_next_flush() on this server: the churn session has
    # exited, which sends its counts, and the collector gets a second to
    # file them before the maintenance step's ANALYZE resets them
    sleep 1
    census_locked "$DB" "$f" churn_raw
    case "$f" in
      g08|n10)
        run_maint "$f" "$DB" maint
        census_locked "$DB" "$f" churn_maintained
        release_snapshot "$DB" "$f"
        run_maint "$f" "$DB" settle2
        census_locked "$DB" "$f" settle2
        ;;
      b13)
        # the BRIN summarization stand-in: an autosummarize index whose work
        # items no worker fulfilled, desummarized in three places and then
        # summarized by the SQL functions, before the mandatory maintenance
        qz "$DB" > "$OUT/standin-$f.log" 2>&1 <<SQL || die "stand-in of $f failed"
SELECT /* wiki_nbmaint_standin */ proto.note('$f','standin','size_before_standin',
         pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_nbmaint_standin */ brin_desummarize_range('$i'::regclass, 0);
SELECT /* wiki_nbmaint_standin */ brin_desummarize_range('$i'::regclass, 128);
SELECT /* wiki_nbmaint_standin */ brin_desummarize_range('$i'::regclass, 256);
SELECT /* wiki_nbmaint_standin */ proto.note('$f','standin','size_after_desummarize',
         pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_nbmaint_standin */ brin_summarize_range('$i'::regclass, 0);
SELECT /* wiki_nbmaint_standin */ brin_summarize_new_values('$i'::regclass);
SELECT /* wiki_nbmaint_standin */ proto.note('$f','standin','size_after_summarize',
         pg_relation_size('$i'::regclass,'main'));
SQL
        census_locked "$DB" "$f" standin
        run_maint "$f" "$DB" maint
        census_locked "$DB" "$f" churn_maintained
        ;;
      h00|h07|n08|n09)
        # no churn, so nothing to maintain: the build phase's ANALYZE is what
        # the fixture carries into the decide phase
        census_locked "$DB" "$f" churn_maintained
        ;;
      *)
        run_maint "$f" "$DB" maint
        census_locked "$DB" "$f" churn_maintained
        ;;
    esac
  done
  q "$DB" "SELECT fixture || ' raw=' ||
             max(num) FILTER (WHERE phase = 'churn_raw' AND metric = 'index_size') || ' maintained=' ||
             coalesce(max(num) FILTER (WHERE phase = 'settle2' AND metric = 'index_size'),
                      max(num) FILTER (WHERE phase = 'churn_maintained' AND metric = 'index_size'))
             FROM proto.meas WHERE metric = 'index_size'
             GROUP BY fixture ORDER BY fixture" > "$OUT/maintenance-pair.txt"
  printf 'maintenance steps checked: %s, all ok\n' "$(grep -c ' ok ' "$OUT/maintenance-proof.txt")"
  stage_done churn
}

# ----------------------------------------------------- stage: autoanalyze ----
# The simulated auto-analyze census: relation_needs_vacanalyze's analyze
# verdict recomputed per table from the effective reloption-or-GUC values,
# and ANALYZE on exactly the tables it names.
CENSUS_SQL="
SELECT c.relname AS tbl,
       greatest(c.reltuples, 0)::bigint AS reltuples,
       coalesce(s.n_mod_since_analyze, 0) AS mods,
       round((CASE WHEN o.thr >= 0 THEN o.thr ELSE current_setting('autovacuum_analyze_threshold')::numeric END)
           + (CASE WHEN o.sf >= 0 THEN o.sf ELSE current_setting('autovacuum_analyze_scale_factor')::numeric END)
             * greatest(c.reltuples, 0)::numeric, 2) AS threshold,
       o.av_enabled
  FROM pg_class c
  LEFT JOIN pg_stat_all_tables s ON s.relid = c.oid
  CROSS JOIN LATERAL (
       SELECT coalesce((SELECT (regexp_match(opt, '^autovacuum_analyze_threshold=(.*)\$'))[1]::numeric
                          FROM unnest(coalesce(c.reloptions, '{}')) opt
                         WHERE opt LIKE 'autovacuum_analyze_threshold=%'), -1) AS thr,
              coalesce((SELECT (regexp_match(opt, '^autovacuum_analyze_scale_factor=(.*)\$'))[1]::numeric
                          FROM unnest(coalesce(c.reloptions, '{}')) opt
                         WHERE opt LIKE 'autovacuum_analyze_scale_factor=%'), -1) AS sf,
              NOT coalesce((SELECT (regexp_match(opt, '^autovacuum_enabled=(.*)\$'))[1] = 'false'
                              FROM unnest(coalesce(c.reloptions, '{}')) opt
                             WHERE opt LIKE 'autovacuum_enabled=%'), false) AS av_enabled
  ) o
 WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace"
stage_autoanalyze() {
  say "autoanalyze: the launcher's analyze verdict, recomputed per table"
  need_db; need_stage churn; refuse_after autoanalyze decide
  local t
  for t in tc_past tc_exact tc_off; do q "$DB" "DROP TABLE IF EXISTS $t" > /dev/null; done
  # No pg_stat_force_next_flush() on this server, so every step that must be
  # published before the next one runs in its own session, which sends its
  # counts when it exits, and the collector gets a second to file them.
  qin "$DB" > "$OUT/autoanalyze-build.log" 2>&1 <<'SQL' || die "census tables failed"
CREATE /* wiki_nbmaint_census */ TABLE tc_past  (id bigint, k bigint);
CREATE /* wiki_nbmaint_census */ TABLE tc_exact (id bigint, k bigint);
CREATE /* wiki_nbmaint_census */ TABLE tc_off   (id bigint, k bigint) WITH (autovacuum_enabled = false);
INSERT /* wiki_nbmaint_census */ INTO tc_past  SELECT g, g FROM generate_series(1,10000) g;
INSERT /* wiki_nbmaint_census */ INTO tc_exact SELECT g, g FROM generate_series(1,10000) g;
INSERT /* wiki_nbmaint_census */ INTO tc_off   SELECT g, g FROM generate_series(1,10000) g;
SQL
  sleep 1
  printf 'ANALYZE /* wiki_nbmaint_census */ tc_past, tc_exact, tc_off;\n' \
    | qz "$DB" >> "$OUT/autoanalyze-build.log" 2>&1 || die "census tables' ANALYZE failed"
  sleep 1
  # at the shipped defaults the threshold is 50 + 0.1 * 10000 = 1050: tc_past
  # crosses it, tc_exact lands exactly on it, tc_off is short-circuited
  qin "$DB" > "$OUT/autoanalyze-push.log" 2>&1 <<'SQL' || die "census push failed"
UPDATE /* wiki_nbmaint_census */ tc_past  SET k = k WHERE id <= 2000;
UPDATE /* wiki_nbmaint_census */ tc_exact SET k = k WHERE id <= 1050;
UPDATE /* wiki_nbmaint_census */ tc_off   SET k = k WHERE id <= 2000;
SQL
  sleep 1
  q "$DB" "SELECT /* wiki_nbmaint_census */ format('%-10s reltuples=%-9s mods=%-8s threshold=%-10s av_enabled=%s doanalyze=%s',
             tbl, reltuples, mods, threshold, av_enabled, av_enabled AND mods > threshold)
             FROM ($CENSUS_SQL) v ORDER BY tbl" > "$OUT/autoanalyze-verdicts.txt"
  q "$DB" "SELECT /* wiki_nbmaint_census */ 'ANALYZE ' || quote_ident(tbl) || ';'
             FROM ($CENSUS_SQL) v WHERE av_enabled AND mods > threshold ORDER BY tbl" \
    > "$OUT/autoanalyze-named.txt"
  qz "$DB" < "$OUT/autoanalyze-named.txt" > "$OUT/autoanalyze-run.log" 2>&1 \
    || die "the census's ANALYZE failed"
  grep -Eq 'timeouts in force: .*' "$OUT/autoanalyze-run.log" || die "the census session printed no timeouts"
  printf 'census named %s table(s) for ANALYZE: %s\n' "$(grep -c 'ANALYZE' "$OUT/autoanalyze-named.txt")" \
    "$(tr '\n' ' ' < "$OUT/autoanalyze-named.txt")" | tee -a "$OUT/autoanalyze-verdicts.txt"
  grep -E 'tc_past|tc_exact|tc_off' "$OUT/autoanalyze-verdicts.txt"
  stage_done autoanalyze
}

# ---------------------------------------------------- stage: the cross-checks
# VACUUM VERBOSE's index line, read out of each maintenance VACUUM's own log
# and stored against the census phases on either side of that VACUUM, so the
# score stage can check every count it prints against the censuses (I9).
# Then the horizon holders, the pgstattuple refusals, the instrument matrix
# and the census summary.  A crosscheck that runs again replaces its rows.
verbose_parse() {   # <fixture> <tag> <census before> <census after>
  local f=$1 tag=$2 pre=$3 post=$4 lg="$OUT/$2-$1.log" i np dl del free vac scans
  [ -f "$lg" ] || return 0
  i=$(idx "$f")
  vac=0; grep -q 'vacuuming "' "$lg" && vac=1
  # this server says 'scanned index "X" to remove N row versions' exactly when
  # ambulkdelete ran on that index
  scans=0; grep -q "scanned index \"$i\" to remove" "$lg" && scans=1
  q "$DB" "SELECT proto.note('$f','verbose_$tag','vacuum_ran',$vac),
                  proto.note('$f','verbose_$tag','index_scans_ran',$scans),
                  proto.note('$f','verbose_$tag','census_before',NULL,'$pre'),
                  proto.note('$f','verbose_$tag','census_after',NULL,'$post')" > /dev/null
  # This server words the index line as two messages: 'index "X" now
  # contains N row versions in P pages', then a DETAIL whose second line is
  # 'D index pages have been deleted, F are currently reusable.'  It has no
  # newly-deleted count, which PostgreSQL 14 added.
  np=$(grep -Eo "index \"$i\" now contains [0-9]+ row versions in [0-9]+ pages" "$lg" | head -1 \
         | grep -Eo '[0-9]+ pages$' | grep -Eo '^[0-9]+')
  if [ -n "$np" ]; then
    dl=$(grep -A3 -E "index \"$i\" now contains" "$lg" \
           | grep -Eo '[0-9]+ index pages have been deleted, [0-9]+ are currently reusable' | head -1)
    [ -n "$dl" ] || die "cannot read the VERBOSE index detail of $f ($tag)"
    del=${dl%% index pages*}; free=${dl#*deleted, }; free=${free%% are currently*}
    q "$DB" "SELECT proto.note('$f','verbose_$tag','num_pages',$np),
                    proto.note('$f','verbose_$tag','pages_deleted',$del),
                    proto.note('$f','verbose_$tag','pages_free',$free),
                    proto.note('$f','verbose_$tag','index_line',NULL,'present')" > /dev/null
  else
    q "$DB" "SELECT proto.note('$f','verbose_$tag','index_line',NULL,'absent')" > /dev/null
  fi
}
stage_crosscheck() {
  say "crosscheck: VACUUM's index line, the proofs, the holders, the instruments"
  need_db; need_stage churn
  q "$DB" "DELETE FROM proto.meas WHERE phase LIKE 'verbose%'" > /dev/null
  local f
  for f in $SCORED; do
    case "$f" in
      b13) verbose_parse "$f" maint standin churn_maintained ;;
      *)   verbose_parse "$f" maint churn_raw churn_maintained ;;
    esac
    verbose_parse "$f" settle2 churn_maintained settle2
  done
  q "$DB" "SELECT fixture || ' ' || substring(phase from 9) || ' ' ||
             coalesce(max(txt) FILTER (WHERE metric = 'index_line'), '?') ||
             coalesce(' total=' || max(num) FILTER (WHERE metric = 'num_pages'), '') ||
             coalesce(' newly=' || max(num) FILTER (WHERE metric = 'pages_newly_deleted'), '') ||
             coalesce(' deleted=' || max(num) FILTER (WHERE metric = 'pages_deleted'), '') ||
             coalesce(' free=' || max(num) FILTER (WHERE metric = 'pages_free'), '') ||
             ' vacuum=' || max(num) FILTER (WHERE metric = 'vacuum_ran') ||
             ' bulkdelete=' || max(num) FILTER (WHERE metric = 'index_scans_ran')
             FROM proto.meas WHERE phase LIKE 'verbose%' GROUP BY fixture, phase ORDER BY fixture, phase" \
    > "$OUT/verbose-lines.txt"
  q "$DB" "SELECT format('%-4s %-14s backends=%s slots=%s prepared=%s | %s', fixture, phase,
             max(num) FILTER (WHERE metric = 'horizon_backends'),
             max(num) FILTER (WHERE metric = 'horizon_slots'),
             max(num) FILTER (WHERE metric = 'horizon_prepared'),
             max(txt) FILTER (WHERE metric = 'horizon_backend_detail'))
             FROM proto.meas
            WHERE phase IN ('maint_before','maint_after','settle2_before','settle2_after')
            GROUP BY fixture, phase ORDER BY fixture, phase" > "$OUT/horizon-holders.txt"
  : > "$OUT/instrument-matrix.txt"
  local ix am fn
  for f in h01 g06 s08 b10 n03; do
    ix=$(idx "$f"); am=$(fx_am "$f")
    for fn in "pgstattuple('$ix')" "pgstatindex('$ix')" "pgstathashindex('$ix')" "pgstatginindex('$ix')"; do
      printf '%-7s %-16s %s\n' "$am" "${fn%%(*}" \
        "$(qtry "$DB" "SELECT 'accepted' FROM $fn" 2>&1 | tr '\n' ' ' | sed -e 's/^ *//' -e 's/ *$//' | cut -c1-90)" \
        >> "$OUT/instrument-matrix.txt"
    done
  done
  q "$DB" "SELECT fixture || ' [' || phase || '] scanned=' ||
             max(num) FILTER (WHERE metric = 'census_scanned') ||
             coalesce(' bracket=' || (max(num) FILTER (WHERE metric = 'size_after_census')
                                   - max(num) FILTER (WHERE metric = 'size_before_census')), '') ||
             coalesce(' fsm=' || max(num) FILTER (WHERE metric = 'fsm_free_pages'), '') ||
             coalesce(' deleted=' || max(num) FILTER (WHERE metric = 'census_deleted'), '') ||
             coalesce(' new=' || max(num) FILTER (WHERE metric = 'census_new'), '') ||
             coalesce(' new_or_empty=' || max(num) FILTER (WHERE metric = 'census_new_or_empty'), '') ||
             coalesce(' fsm_agree=' || max(num) FILTER (WHERE metric = 'brin_fsm_agree')
                      || '/' || max(num) FILTER (WHERE metric = 'census_regular')
                      || ' higher=' || max(num) FILTER (WHERE metric = 'brin_fsm_higher')
                      || ' lower=' || max(num) FILTER (WHERE metric = 'brin_fsm_lower'), '') ||
             coalesce(' unreadable=' || max(num) FILTER (WHERE metric = 'census_unreadable'), '') ||
             coalesce(' progress=' || (max(num) FILTER (WHERE metric = 'progress_vacuum')
                                     + coalesce(max(num) FILTER (WHERE metric = 'progress_analyze'), 0)
                                     + max(num) FILTER (WHERE metric = 'progress_create_index')), '')
             FROM proto.meas
            WHERE phase IN ('baseline','churn_raw','standin','churn_maintained','settle2')
            GROUP BY fixture, phase
           HAVING count(*) FILTER (WHERE metric = 'census_scanned') > 0
            ORDER BY fixture, phase" > "$OUT/census-summary.txt"
  q "$DB" "SELECT 'hash censuses pgstattuple refused: ' || count(*) ||
             coalesce(' (' || string_agg(DISTINCT fixture || '/' || phase, ', ') || '): ' || min(txt), '')
             FROM proto.meas WHERE metric = 'pgst_refusal'" | tee "$OUT/pgstattuple-refusals.txt"
  wc -l "$OUT/verbose-lines.txt" "$OUT/horizon-holders.txt" "$OUT/census-summary.txt" | sed 's/^/    /'
  cat "$OUT/instrument-matrix.txt"
  stage_done crosscheck
}

# -------------------------------------------------------------- stage: decide
# Step 1, verbatim, inside one transaction holding SHARE ROW EXCLUSIVE on every
# fixture table; then the same rows through the one-edit view, and the
# harness's own readings of every index, in the same transaction.  A decide
# that runs again, before the oracle, replaces its own records.
stage_decide() {
  say "decide: step 1, verbatim, under the measurement lock"
  need_texts; need_db; need_stage autoanalyze; refuse_after decide oracle
  q "$DB" "DELETE FROM proto.meas WHERE fixture = 'decide'" > /dev/null
  q "$DB" "DELETE FROM proto.snap WHERE phase = 'decide'" > /dev/null
  qf "$DB" "$SQLD/plan_view.sql" > "$OUT/plan-view.log" 2>&1 || die "the one-edit view failed"
  local locks="" f
  for f in $SCORED; do locks="$locks$(tbl "$f"), "; done
  locks="${locks}tc_past, tc_exact, tc_off"
  { printf "BEGIN /* wiki_nbmaint_decide */;\n"
    printf "LOCK /* wiki_nbmaint_decide */ TABLE %s IN SHARE ROW EXCLUSIVE MODE;\n" "$locks"
    printf "SELECT proto.note('decide','decide','lock_acquired', extract(epoch from clock_timestamp())::numeric);\n"
    cat "$SQLD/plan.sql"
    printf "SELECT proto.note('decide','decide','plan_done', extract(epoch from clock_timestamp())::numeric);\n"
    printf "DROP TABLE IF EXISTS proto.decided;\n"
    printf "CREATE TABLE proto.decided AS SELECT * FROM proto.plan_v;\n"
    printf "SELECT proto.take_snap('decide');\n"
    printf "SELECT proto.note('decide','decide','lock_released', extract(epoch from clock_timestamp())::numeric);\n"
    printf "COMMIT /* wiki_nbmaint_decide */;\n"
  } | "$BIN/psql" -X -v ON_ERROR_STOP=1 -P pager=off -h "$SOCK" -p "$PORT" -d "$DB" \
      > "$OUT/decide.txt" 2>&1 || die "decide failed, see $OUT/decide.txt"
  q "$DB" "SELECT 'rows step 1 returned: ' || count(*) || ', of them fixture indexes: ' ||
             count(*) FILTER (WHERE index_name ~ '^f_.*_i\$') FROM proto.decided"
  q "$DB" "SELECT 'step 1 took ' || round((max(num) FILTER (WHERE metric = 'plan_done')
             - max(num) FILTER (WHERE metric = 'lock_acquired')) * 1000, 1) || ' ms under the lock'
             FROM proto.meas WHERE fixture = 'decide'" | tee "$OUT/decide-cost.txt"
  q "$DB" "SELECT action || ': ' || count(*) FROM proto.decided GROUP BY action ORDER BY action"
  stage_done decide
}

# -------------------------------------------------------------- stage: oracle
stage_oracle() {
  say "oracle: REINDEX INDEX at maintenance_work_mem = $MWM, bracketed"
  need_db; need_stage decide; refuse_after oracle oracle
  local f t i
  for f in $SCORED; do
    t=$(tbl "$f"); i=$(idx "$f")
    qin "$DB" > "$OUT/oracle-$f.log" 2>&1 <<SQL || die "oracle of $f failed"
SET /* wiki_nbmaint_oracle */ maintenance_work_mem = '$MWM';
SELECT /* wiki_nbmaint_oracle */ proto.note('$f','oracle','size_before', pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_nbmaint_oracle */ proto.note('$f','oracle','heap_relpages',
         (SELECT relpages FROM pg_class WHERE oid = '$t'::regclass));
SELECT /* wiki_nbmaint_oracle */ proto.note('$f','oracle','heap_reltuples',
         (SELECT reltuples::numeric FROM pg_class WHERE oid = '$t'::regclass));
REINDEX /* wiki_nbmaint_oracle */ INDEX $i;
SELECT /* wiki_nbmaint_oracle */ proto.note('$f','oracle','size_after', pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_nbmaint_oracle */ proto.note('$f','oracle','mwm', NULL, current_setting('maintenance_work_mem'));
SQL
  done
  q "$DB" "SELECT fixture || ' ' || max(num) FILTER (WHERE metric = 'size_before') || ' -> ' ||
             max(num) FILTER (WHERE metric = 'size_after') || ' = ' ||
             CASE WHEN max(num) FILTER (WHERE metric = 'size_before') > 0
                  THEN round(100.0 * (1 - max(num) FILTER (WHERE metric = 'size_after')
                                        / max(num) FILTER (WHERE metric = 'size_before')), 2)
                  ELSE 0 END || ' %'
             FROM proto.meas WHERE phase = 'oracle' AND metric IN ('size_before','size_after')
             GROUP BY fixture ORDER BY fixture" > "$OUT/oracle-summary.txt"
  wc -l < "$OUT/oracle-summary.txt" | sed 's/^/    fixtures rebuilt: /'
  stage_done oracle
}

# ----------------------------------------------------------------- stage: act
# Step 1 then step 2 on the state the oracle left - every fixture index just
# rebuilt out of band - then step 2 again.  Not scored against the oracle: it
# checks that step 2 does what step 1 printed, and that a settled database
# costs nothing, and it fails the run when either does not hold.
stage_act() {
  say "act: step 1, step 2, step 2 again, on the rebuilt state"
  need_texts; need_db; need_stage oracle; refuse_after act act
  q "$DB" "SELECT proto.take_snap('act_before')" > /dev/null
  run_plan "$DB" act || die "step 1 (act) failed"
  q "$DB" "DROP TABLE IF EXISTS proto.act_plan;
           CREATE TABLE proto.act_plan AS SELECT * FROM proto.plan_v" > /dev/null
  run_apply "$DB" act1 || die "step 2 (act1) failed, see $OUT/apply-act1.log"
  q "$DB" "SELECT proto.take_snap('act_after')" > /dev/null
  run_apply "$DB" act2 || die "step 2 (act2) failed"
  q "$DB" "SELECT proto.take_snap('act_second')" > /dev/null
  local did same n
  n=$(q "$DB" "SELECT count(*) FROM proto.act_plan")
  did=$(q "$DB" "WITH b AS (SELECT * FROM proto.snap WHERE phase = 'act_before'),
                      a AS (SELECT * FROM proto.snap WHERE phase = 'act_after')
                 SELECT count(*) FILTER (WHERE CASE p.action
                          WHEN 'reindex' THEN a.filenode <> b.filenode AND a.pv = 2 AND a.sz = a.bytes
                                              AND a.tup = round(greatest(a.tbl_tuples, -1))
                          WHEN 'initialize' THEN a.filenode = b.filenode AND a.pv = 2 AND a.sz = a.bytes
                                              AND a.tup = round(greatest(a.tbl_tuples, -1))
                          WHEN 'refresh' THEN a.filenode = b.filenode AND a.pv = 2 AND a.sz = a.bytes
                                              AND a.tup = round(greatest(a.tbl_tuples, -1))
                          WHEN 'skip' THEN a.filenode = b.filenode AND a.cmt IS NOT DISTINCT FROM b.cmt
                          ELSE false END)
                   FROM proto.act_plan p JOIN b ON b.idx = p.index_name JOIN a ON a.idx = p.index_name")
  same=$(q "$DB" "SELECT count(*) FILTER (WHERE s.filenode = a.filenode AND s.cmt IS NOT DISTINCT FROM a.cmt)
                    FROM proto.act_plan p
                    JOIN proto.snap a ON a.phase = 'act_after'  AND a.idx = p.index_name
                    JOIN proto.snap s ON s.phase = 'act_second' AND s.idx = p.index_name")
  { printf 'step 1 plan:   %s\n' "$(q "$DB" "SELECT string_agg(action || '=' || n, ' ' ORDER BY action)
                                            FROM (SELECT action, count(*) n FROM proto.act_plan GROUP BY action) s")"
    printf 'step 2 run 1:  %s\n' "$(apply_summary act1)"
    printf 'step 2 run 2:  %s\n' "$(apply_summary act2)"
    printf 'per index, step 2 did what step 1 printed: %s of %s; unchanged by the second run: %s of %s\n' \
      "$did" "$n" "$same" "$n"
    printf -- '-- per fixture: the action on the rebuilt state, and why\n'
    q "$DB" "SELECT format('%-10s %-8s size_ratio=%s tuple_ratio=%s %s', index_name, action,
                           coalesce(size_ratio::text, '-'), coalesce(tuple_ratio::text, '-'), notes)
               FROM proto.act_plan ORDER BY index_name"
  } > "$OUT/act.txt"
  head -4 "$OUT/act.txt"
  [ "$did" = "$n" ] && [ "$same" = "$n" ] \
    || die "act: step 2 did not do what step 1 printed, or its second run wrote (see $OUT/act.txt)"
  apply_summary act2 | grep -q 'reindex=0 initialize=0 refresh=0 ' || die "act: the second run of step 2 wrote"
  stage_done act
}

# --------------------------------------------------------------- stage: score
# Pure computation over what the earlier stages recorded, so it may run again
# at any time after act; each run rebuilds its tables.  truth_pct is the
# oracle's fraction rounded for display; every comparison with the pay-off
# threshold uses the unrounded truth_exact.  Every invariant is stored with
# whether it held, and a run in which any declared invariant failed fails
# here, after every file is written.
NOCHURN="'h00','h07','n08','n09'"
stage_score() {
  say "score: every decision against the oracle, at the filed pay-off threshold"
  need_db; need_stage churn crosscheck decide oracle act
  # The run is refused a score when any maintenance proof failed.  check_maint
  # already stopped the run at the failing step; this is the same rule, read
  # back from what was recorded, for a score stage run on its own.
  ! grep -q 'DEFEATED' "$OUT/maintenance-proof.txt" 2>/dev/null \
    || die "a maintenance step was defeated: nothing is scored"
  [ "$(q "$DB" "SELECT count(*) FROM proto.meas WHERE metric = 'dead_not_removable'")" -gt 0 ] \
    || die "no maintenance proof was recorded: nothing is scored"
  local tb
  for tb in declared_kind declared_decision declared_prediction declared_invariant declared_exception declared_coverage; do
    q "$DB" "DROP TABLE IF EXISTS proto.$tb" > /dev/null
  done
  qin "$DB" > "$OUT/score-ddl.log" 2>&1 <<'SQL'
CREATE TABLE proto.declared_kind       (column_name text, declared_kind text, claim text, filed_at timestamptz);
CREATE TABLE proto.declared_decision   (knob text, value text, meaning text, filed_at timestamptz);
CREATE TABLE proto.declared_prediction (fixture text, action text, score text, why text, filed_at timestamptz);
CREATE TABLE proto.declared_invariant  (id text, claim text, filed_at timestamptz);
CREATE TABLE proto.declared_exception  (id text, fixture text, state text, reading_rule text, filed_at timestamptz);
CREATE TABLE proto.declared_coverage   (protocol text, behavior text, fixture text, filed_at timestamptz);
SQL
  for tb in declared_kind declared_decision declared_prediction declared_invariant declared_exception declared_coverage; do
    q "$PDB" "SELECT format('INSERT INTO proto.$tb SELECT (json_populate_record(NULL::proto.$tb, %L)).*;',
                            row_to_json(d)::text) FROM $tb d" \
      | qin "$DB" > "$OUT/score-copy-$tb.log" 2>&1
  done
  { q "$DB" "SELECT 'declarations carried: ' || count(*) || ' kinds, filed at ' ||
               to_char(min(filed_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') FROM proto.declared_kind"
    q "$DB" "SELECT 'first baseline payload written at ' ||
               to_char(min(at) AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')
               FROM proto.snap WHERE phase = 'baseline'"
  } | tee "$OUT/score-declarations.txt"

  qin "$DB" > "$OUT/score-build.log" 2>&1 <<'SQL'
DROP TABLE IF EXISTS proto.score;
CREATE /* wiki_nbmaint_score */ TABLE proto.score AS
WITH m AS (
  SELECT fixture,
         max(num) FILTER (WHERE phase = 'baseline'  AND metric = 'index_size') AS base_size,
         max(num) FILTER (WHERE phase = 'churn_raw' AND metric = 'index_size') AS raw_size,
         -- on X1 and X2 the maintained state is the settle2 census, after the
         -- declared snapshot was released and a second VACUUM ANALYZE ran
         coalesce(max(num) FILTER (WHERE phase = 'settle2' AND metric = 'index_size'),
                  max(num) FILTER (WHERE phase = 'churn_maintained' AND metric = 'index_size')) AS maint_size,
         max(num) FILTER (WHERE phase = 'oracle' AND metric = 'size_before')    AS oracle_before,
         max(num) FILTER (WHERE phase = 'oracle' AND metric = 'size_after')     AS oracle_after,
         max(num) FILTER (WHERE phase = 'oracle' AND metric = 'heap_relpages')  AS heap_relpages,
         max(num) FILTER (WHERE phase = 'oracle' AND metric = 'heap_reltuples') AS heap_reltuples
    FROM proto.meas GROUP BY fixture
),
bl AS (
  SELECT substring(idx from '^f_(.*)_i$') AS fixture, bytes AS capture_bytes,
         tbl_tuples AS capture_tuples, pv AS captured_v, sz AS captured_sz, tup AS captured_tup
    FROM proto.snap WHERE phase = 'baseline'
),
ds AS (
  SELECT substring(idx from '^f_(.*)_i$') AS fixture, bytes AS decide_bytes,
         tbl_tuples AS decide_tuples, sz AS stored_sz, tup AS stored_tup
    FROM proto.snap WHERE phase = 'decide'
),
dec AS (
  SELECT substring(index_name from '^f_(.*)_i$') AS fixture, access_method AS am,
         action, size_ratio, tuple_ratio, notes
    FROM proto.decided WHERE schema_name = 'public' AND index_name ~ '^f_.*_i$'
),
pay AS (
  SELECT (regexp_match(value, '([0-9]+[.][0-9]+)'))[1]::numeric AS min_truth
    FROM proto.declared_decision WHERE knob = 'pay-off'
),
base AS (
  SELECT m.fixture, dec.am, m.base_size, bl.captured_v, bl.captured_sz, bl.capture_bytes,
         bl.captured_tup, bl.capture_tuples, m.raw_size, m.maint_size, ds.decide_bytes,
         m.oracle_before, m.oracle_after, m.heap_relpages, m.heap_reltuples,
         ds.stored_sz, ds.stored_tup, ds.decide_tuples,
         -- the oracle's own fraction, unrounded: what the threshold is applied to
         CASE WHEN m.oracle_before > 0
              THEN 100.0 * (1 - m.oracle_after / m.oracle_before) ELSE 0 END AS truth_exact,
         dec.size_ratio, dec.tuple_ratio, dec.notes, dec.action,
         -- the brief's two tests, recomputed from the harness's own readings
         (ds.decide_bytes >= ds.stored_sz * 1.30) AS size_fired,
         (ds.decide_tuples >= 0 AND ds.stored_tup >= 0
          AND CASE WHEN ds.stored_tup = 0 THEN ds.decide_tuples > 0
                   ELSE abs(ds.decide_tuples - ds.stored_tup) >= ds.stored_tup * 0.30 END) AS tuple_fired,
         pay.min_truth,
         p.action AS want_action, p.score AS want_score, p.why AS want_why
    FROM m
    JOIN dec USING (fixture) JOIN bl USING (fixture) JOIN ds USING (fixture)
    CROSS JOIN pay
    LEFT JOIN proto.declared_prediction p USING (fixture)
)
SELECT b.*,
       round(b.truth_exact, 2) AS truth_pct,
       CASE WHEN b.stored_sz IS NULL THEN 'initialize'
            WHEN b.decide_bytes < b.stored_sz THEN 'refresh'
            WHEN b.size_fired OR b.tuple_fired THEN 'reindex'
            ELSE 'skip' END AS expected_action,
       (b.truth_exact >= b.min_truth) AS pays_off,
       CASE WHEN b.action = 'reindex' AND b.truth_exact >= b.min_truth THEN 'PASS'
            WHEN b.action = 'reindex'                                  THEN 'FALSE POSITIVE'
            WHEN b.truth_exact >= b.min_truth                          THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END AS score
  FROM base b;
SQL
  q "$DB" "SELECT count(*) FROM proto.score" | grep -q '^[1-9]' || die "the score table is empty (see $OUT/score-build.log)"
  q "$DB" "SELECT format('%-4s %-6s B=%-10s C=%-10s R=%-10s truth=%6s%% size=%-7s tuples=%-7s fired=%-11s action=%-7s score=%-15s predicted=%s',
             fixture, am, base_size, decide_bytes, oracle_after, truth_pct,
             coalesce(size_ratio::text, '-'), coalesce(tuple_ratio::text, '-'),
             CASE WHEN size_fired AND tuple_fired THEN 'both' WHEN size_fired THEN 'size'
                  WHEN tuple_fired THEN 'tuples' ELSE 'none' END,
             action, score,
             CASE WHEN want_action = action AND want_score = score THEN 'hit'
                  ELSE 'MISS (' || coalesce(want_action, '?') || ', ' || coalesce(want_score, '?') || ')' END)
             FROM proto.score ORDER BY am, fixture" > "$OUT/score-table.txt"
  { q "$DB" "SELECT 'pay-off threshold: truth_exact >= ' || min(min_truth) || ', on the unrounded fraction' FROM proto.score"
    q "$DB" "SELECT score || ': ' || count(*) FROM proto.score GROUP BY score ORDER BY score"
    q "$DB" "SELECT am || ': ' || string_agg(score || '=' || n, ', ' ORDER BY score)
               FROM (SELECT am, score, count(*) n FROM proto.score GROUP BY am, score) s
              GROUP BY am ORDER BY am"
    q "$DB" "SELECT 'reindex decisions: ' || count(*) FILTER (WHERE action = 'reindex') ||
               ' (size test ' || count(*) FILTER (WHERE size_fired) ||
               ', tuple test ' || count(*) FILTER (WHERE tuple_fired) ||
               ', both ' || count(*) FILTER (WHERE size_fired AND tuple_fired) ||
               ', size only ' || count(*) FILTER (WHERE size_fired AND NOT tuple_fired) ||
               ', tuples only ' || count(*) FILTER (WHERE tuple_fired AND NOT size_fired) || ')'
               FROM proto.score"
    q "$DB" "SELECT 'fixtures that paid off: ' || count(*) FILTER (WHERE pays_off) || ' of ' || count(*) ||
               '; mean truth of the rebuilt ' ||
               coalesce(round(avg(truth_exact) FILTER (WHERE action = 'reindex'), 1)::text, '-') ||
               ' %, of the skipped ' ||
               coalesce(round(avg(truth_exact) FILTER (WHERE action <> 'reindex'), 1)::text, '-') || ' %'
               FROM proto.score"
    q "$DB" "SELECT 'closest to the threshold: ' || string_agg(fixture || ' ' || round(truth_exact, 4) || ' %', ', '
               ORDER BY abs(truth_exact - min_truth)) FROM (SELECT * FROM proto.score
               ORDER BY abs(truth_exact - min_truth) LIMIT 3) s"
    q "$DB" "SELECT 'false positives: ' || coalesce(string_agg(fixture || ' (' || truth_pct || ' %, ' ||
               CASE WHEN size_fired AND tuple_fired THEN 'both' WHEN size_fired THEN 'size' ELSE 'tuples' END
               || ')', ', ' ORDER BY fixture), 'none') FROM proto.score WHERE score = 'FALSE POSITIVE'"
    q "$DB" "SELECT 'false negatives: ' || coalesce(string_agg(fixture || ' (' || truth_pct || ' %, size '
               || size_ratio || ', tuples ' || coalesce(tuple_ratio::text, '-') || ')', ', ' ORDER BY fixture), 'none')
               FROM proto.score WHERE score = 'FALSE NEGATIVE'"
    q "$DB" "SELECT 'predictions: ' || count(*) FILTER (WHERE want_action = action AND want_score = score)
               || ' of ' || count(*) || ' hit; misses: ' ||
               coalesce(string_agg(fixture || ' predicted ' || want_action || '/' || want_score ||
                                   ', measured ' || action || '/' || score, '; ')
                        FILTER (WHERE NOT (want_action = action AND want_score = score)), 'none')
               FROM proto.score"
    q "$DB" "SELECT 'the tuple test on a rise: ' ||
               coalesce(string_agg(fixture || ' ' || score, ', ' ORDER BY fixture)
                          FILTER (WHERE tuple_fired AND decide_tuples > stored_tup), 'none') ||
               '; on a fall: ' ||
               coalesce(string_agg(fixture || ' ' || score, ', ' ORDER BY fixture)
                          FILTER (WHERE tuple_fired AND decide_tuples < stored_tup), 'none')
               FROM proto.score"
    q "$DB" "SELECT 'the size test alone: ' || string_agg(score || ' ' || n || ' (' || fx || ')', '; ' ORDER BY score)
               FROM (SELECT score, count(*) n, string_agg(fixture, ',' ORDER BY fixture) fx
                       FROM proto.score WHERE size_fired AND NOT tuple_fired GROUP BY score) s"
    q "$DB" "SELECT 'the whole run, not just fixtures: step 1 returned ' || count(*) || ' rows, actions ' ||
               string_agg(DISTINCT action, ',') FROM proto.decided"
  } | tee "$OUT/score-summary.txt"

  say "score: the invariants"
  local act_line
  act_line=$(grep -h 'per index, step 2 did what step 1 printed' "$OUT/act.txt" 2>/dev/null)
  qin "$DB" > "$OUT/invariants-build.log" 2>&1 <<SQL
DROP TABLE IF EXISTS proto.invariant;
CREATE TABLE proto.invariant (id text PRIMARY KEY, reading text NOT NULL, holds boolean NOT NULL);
DROP TABLE IF EXISTS proto.census_v;
CREATE TABLE proto.census_v AS
  SELECT fixture, phase,
         max(num) FILTER (WHERE metric = 'census_scanned')      AS scanned,
         max(num) FILTER (WHERE metric = 'size_before_census')  AS sz_before,
         max(num) FILTER (WHERE metric = 'size_after_census')   AS sz_after,
         max(num) FILTER (WHERE metric = 'census_meta')         AS c_meta,
         max(num) FILTER (WHERE metric = 'census_bucket')       AS c_bucket,
         max(num) FILTER (WHERE metric = 'census_overflow')     AS c_ovfl,
         max(num) FILTER (WHERE metric = 'census_bitmap')       AS c_bitmap,
         max(num) FILTER (WHERE metric = 'census_unused')       AS c_unused,
         max(num) FILTER (WHERE metric = 'census_unreadable')   AS c_bad,
         max(num) FILTER (WHERE metric = 'census_deleted')      AS c_del,
         max(num) FILTER (WHERE metric = 'census_new')          AS c_new,
         max(num) FILTER (WHERE metric = 'census_new_or_empty') AS c_empty,
         max(num) FILTER (WHERE metric = 'census_entry')        AS c_entry,
         max(num) FILTER (WHERE metric = 'census_data')         AS c_data,
         max(num) FILTER (WHERE metric = 'census_list')         AS c_list,
         max(num) FILTER (WHERE metric = 'fsm_free_pages')      AS fsm,
         max(num) FILTER (WHERE metric = 'brin_items')          AS b_items,
         max(num) FILTER (WHERE metric = 'brin_unused_items')   AS b_unused,
         max(num) FILTER (WHERE metric = 'brin_revmap_entries') AS b_revmap,
         max(num) FILTER (WHERE metric = 'meta_total_pages')    AS m_total,
         max(num) FILTER (WHERE metric = 'meta_entry_pages')    AS m_entry,
         max(num) FILTER (WHERE metric = 'meta_data_pages')     AS m_data,
         max(num) FILTER (WHERE metric = 'meta_pending_pages')  AS m_pending,
         max(num) FILTER (WHERE metric = 'hs_bucket_pages')     AS hs_bucket,
         max(num) FILTER (WHERE metric = 'hs_overflow_pages')   AS hs_ovfl,
         max(num) FILTER (WHERE metric = 'hs_bitmap_pages')     AS hs_bitmap,
         max(num) FILTER (WHERE metric = 'hs_unused_pages')     AS hs_unused,
         max(num) FILTER (WHERE metric = 'bitmap_disagree')     AS bm_dis
    FROM proto.meas
   WHERE phase IN ('baseline','churn_raw','standin','churn_maintained','settle2')
   GROUP BY fixture, phase
  HAVING count(*) FILTER (WHERE metric = 'census_scanned') > 0;
-- One row per maintenance VACUUM: its VERBOSE counts beside the censuses
-- taken just before and just after it.
DROP TABLE IF EXISTS proto.vac_v;
CREATE TABLE proto.vac_v AS
  SELECT v.fixture, v.phase AS tag, sc.am,
         max(v.num) FILTER (WHERE v.metric = 'vacuum_ran')          AS vacuum_ran,
         max(v.num) FILTER (WHERE v.metric = 'index_scans_ran')     AS scans_ran,
         max(v.txt) FILTER (WHERE v.metric = 'index_line')          AS line,
         max(v.num) FILTER (WHERE v.metric = 'num_pages')           AS num_pages,
         max(v.num) FILTER (WHERE v.metric = 'pages_newly_deleted') AS newly,
         max(v.num) FILTER (WHERE v.metric = 'pages_deleted')       AS deleted,
         max(v.num) FILTER (WHERE v.metric = 'pages_free')          AS free,
         max(v.txt) FILTER (WHERE v.metric = 'census_before')       AS pre_phase,
         max(v.txt) FILTER (WHERE v.metric = 'census_after')        AS post_phase
    FROM proto.meas v JOIN proto.score sc ON sc.fixture = v.fixture
   WHERE v.phase LIKE 'verbose%'
   GROUP BY v.fixture, v.phase, sc.am;

INSERT INTO proto.invariant
SELECT 'I1', count(*) FILTER (WHERE maint_size >= base_size) || ' of ' || count(*) || ' (smaller: ' ||
       coalesce(string_agg(fixture, ',') FILTER (WHERE maint_size < base_size), 'none') || ')',
       bool_and(maint_size >= base_size)
  FROM proto.score;
INSERT INTO proto.invariant
SELECT 'I2', count(*) FILTER (WHERE sz_before = sz_after AND sz_after = scanned * b) || ' of ' || count(*) || ' censuses',
       bool_and(sz_before = sz_after AND sz_after = scanned * b)
  FROM proto.census_v CROSS JOIN (SELECT current_setting('block_size')::numeric AS b) blk;
INSERT INTO proto.invariant
SELECT 'I3', count(*) FILTER (WHERE c_meta + c_bucket + c_ovfl + c_bitmap + c_unused + c_bad = scanned
                                AND hs_bucket + hs_ovfl + hs_bitmap + hs_unused + 1 = scanned)
             || ' of ' || count(*) || ' hash censuses',
       bool_and(c_meta + c_bucket + c_ovfl + c_bitmap + c_unused + c_bad = scanned
                AND hs_bucket + hs_ovfl + hs_bitmap + hs_unused + 1 = scanned)
  FROM proto.census_v c JOIN proto.score s USING (fixture) WHERE s.am = 'hash';
INSERT INTO proto.invariant
SELECT 'I4', count(*) FILTER (WHERE bm_dis = 0) || ' of ' || count(*) || ' hash censuses', bool_and(bm_dis = 0)
  FROM proto.census_v c JOIN proto.score s USING (fixture) WHERE s.am = 'hash';
INSERT INTO proto.invariant
SELECT 'I5', count(*) FILTER (WHERE s.am = 'gist' AND fsm <= c_del + c_new) || ' of '
             || count(*) FILTER (WHERE s.am = 'gist') || ' GiST censuses, '
             || count(*) FILTER (WHERE s.am = 'spgist' AND fsm <= c_empty) || ' of '
             || count(*) FILTER (WHERE s.am = 'spgist') || ' SP-GiST censuses',
       bool_and(CASE s.am WHEN 'gist' THEN fsm <= c_del + c_new ELSE fsm <= c_empty END)
  FROM proto.census_v c JOIN proto.score s USING (fixture) WHERE s.am IN ('gist', 'spgist');
INSERT INTO proto.invariant
SELECT 'I6', count(*) FILTER (WHERE b_revmap = b_items) || ' of ' || count(*) || ' BRIN censuses',
       bool_and(b_revmap = b_items)
  FROM proto.census_v c JOIN proto.score s USING (fixture) WHERE s.am = 'brin';
INSERT INTO proto.invariant
SELECT 'I7', count(*) FILTER (WHERE maint_size >= raw_size) || ' of ' || count(*) || ' BRIN fixtures',
       bool_and(maint_size >= raw_size)
  FROM proto.score WHERE am = 'brin';
-- I8 is scoped to the censuses whose metapage counts the build or a VACUUM's
-- cleanup wrote last: the metapage is rewritten by nothing else, so a census
-- taken after writes and before a VACUUM reads counts stale by construction
INSERT INTO proto.invariant
SELECT 'I8', count(*) FILTER (WHERE fresh AND ok) || ' of ' || count(*) FILTER (WHERE fresh)
             || ' GIN censuses the build or a VACUUM left (disagreeing: '
             || coalesce(string_agg(fixture || '/' || phase, ',') FILTER (WHERE fresh AND NOT ok), 'none')
             || '); stale by construction, not scored: ' || count(*) FILTER (WHERE NOT fresh),
       coalesce(bool_and(ok) FILTER (WHERE fresh), true)
  FROM (SELECT c.fixture, c.phase,
               (m_entry = c_entry AND m_data = c_data + greatest(c_del - fsm, 0) AND m_total = scanned) AS ok,
               (c.phase = 'baseline' OR c.fixture IN ($NOCHURN)
                OR EXISTS (SELECT 1 FROM proto.vac_v v WHERE v.fixture = c.fixture
                             AND v.post_phase = c.phase AND v.vacuum_ran = 1)) AS fresh
          FROM proto.census_v c JOIN proto.score s USING (fixture) WHERE s.am = 'gin') g;
-- I9: VERBOSE's index line against the censuses around its own VACUUM
INSERT INTO proto.invariant
SELECT 'I9', count(*) FILTER (WHERE why = 'ok') || ' of ' || count(*)
             || ' maintenance VACUUM and ANALYZE steps agree (' || count(*) FILTER (WHERE line = 'present')
             || ' index lines; disagreeing: '
             || coalesce(string_agg(fixture || '/' || tag || ' ' || why, '; ') FILTER (WHERE why <> 'ok'), 'none')
             || ')',
       bool_and(why = 'ok')
  FROM (SELECT v.fixture, substring(v.tag from 9) AS tag, v.line,
               CASE
                 WHEN v.vacuum_ran = 0 THEN CASE WHEN v.line = 'absent' THEN 'ok' ELSE 'a line with no VACUUM' END
                 WHEN v.am = 'hash' AND v.scans_ran = 0 THEN
                      CASE WHEN v.line = 'absent' THEN 'ok' ELSE 'a hash line with no bulk delete' END
                 WHEN v.line IS DISTINCT FROM 'present' THEN 'no line'
                 WHEN v.num_pages IS DISTINCT FROM CASE WHEN v.am = 'brin' THEN pre.scanned ELSE post.scanned END
                      THEN 'total ' || v.num_pages
                 WHEN v.am IN ('hash', 'brin') AND (coalesce(v.newly, 0), v.deleted, v.free) IS DISTINCT FROM (0, 0, 0)
                      THEN 'nonzero counts'
                 WHEN v.am = 'gist' AND (v.deleted, v.free, coalesce(v.newly, post.c_del - pre.c_del))
                      IS DISTINCT FROM (post.c_del + post.c_new, post.fsm, post.c_del - pre.c_del)
                      THEN 'deleted ' || v.deleted || '/' || (post.c_del + post.c_new) || ' free ' || v.free || '/'
                           || post.fsm || ' newly ' || v.newly || '/' || (post.c_del - pre.c_del)
                 WHEN v.am = 'spgist' AND (coalesce(v.newly, post.c_empty), v.deleted, v.free, post.fsm)
                      IS DISTINCT FROM (post.c_empty, post.c_empty, post.c_empty, post.c_empty)
                      THEN 'deleted ' || v.deleted || ' free ' || v.free || ' newly ' || v.newly
                           || ' new-or-empty ' || post.c_empty || ' fsm ' || post.fsm
                 WHEN v.am = 'gin' AND v.free IS DISTINCT FROM post.fsm
                      THEN 'free ' || v.free || '/' || post.fsm
                 ELSE 'ok' END AS why
          FROM proto.vac_v v
          LEFT JOIN proto.census_v pre  ON pre.fixture  = v.fixture AND pre.phase  = v.pre_phase
          LEFT JOIN proto.census_v post ON post.fixture = v.fixture AND post.phase = v.post_phase) x;
INSERT INTO proto.invariant
SELECT 'I10', count(*) FILTER (WHERE num = 0) || ' VACUUMs at 0 dead but not yet removable, '
              || count(*) FILTER (WHERE num > 0) || ' above 0 ('
              || coalesce(string_agg(fixture || '/' || phase || '=' || num, ', ') FILTER (WHERE num > 0), 'none') || ')',
       bool_and(CASE WHEN phase = 'maint' AND fixture IN ('g08', 'n10') THEN num > 0 ELSE num = 0 END)
  FROM proto.meas WHERE metric = 'dead_not_removable' AND num IS NOT NULL;
INSERT INTO proto.invariant
SELECT 'I11', count(*) FILTER (WHERE metric = 'skip_lines') || ' maintenance sessions, skip lines '
              || coalesce(sum(num) FILTER (WHERE metric = 'skip_lines'), 0) || ', error lines '
              || coalesce(sum(num) FILTER (WHERE metric = 'error_lines'), 0) || ', timeout sets: '
              || coalesce(string_agg(DISTINCT txt, ' | ') FILTER (WHERE metric = 'session_timeouts'), '-'),
       coalesce(sum(num) FILTER (WHERE metric IN ('skip_lines', 'error_lines')), 0) = 0
       AND coalesce(bool_and(txt !~ '=[1-9]') FILTER (WHERE metric = 'session_timeouts'), false)
  FROM proto.meas WHERE metric IN ('skip_lines', 'error_lines', 'session_timeouts');
INSERT INTO proto.invariant
WITH lk AS (SELECT fixture, phase, max(num) FILTER (WHERE metric = 'lock_acquired') AS t0,
                   max(num) FILTER (WHERE metric = 'lock_released') AS t1
              FROM proto.meas WHERE metric IN ('lock_acquired','lock_released') GROUP BY fixture, phase),
     mt AS (SELECT fixture, phase, max(num) FILTER (WHERE metric = 'started') AS m0,
                   max(num) FILTER (WHERE metric = 'ended') AS m1
              FROM proto.meas WHERE metric IN ('started','ended') GROUP BY fixture, phase),
     ov AS (SELECT 1 FROM lk JOIN mt ON lk.t0 < mt.m1 AND mt.m0 < lk.t1)
SELECT 'I12', (SELECT count(*) FROM lk) || ' lock intervals, ' || (SELECT count(*) FROM mt)
              || ' maintenance intervals, overlaps ' || (SELECT count(*) FROM ov),
       (SELECT count(*) FROM ov) = 0;
INSERT INTO proto.invariant
SELECT 'I13', count(*) FILTER (WHERE slots = 0 AND prepared = 0 AND backends = 0) || ' of ' || count(*)
              || ' probes clean; holding a backend: '
              || coalesce(string_agg(fixture || '/' || phase, ', ') FILTER (WHERE backends > 0), 'none')
              || '; slots ' || coalesce(sum(slots), 0) || ', prepared ' || coalesce(sum(prepared), 0),
       bool_and(slots = 0 AND prepared = 0
                AND backends = CASE WHEN fixture IN ('g08', 'n10') AND phase LIKE 'maint_%' THEN 1 ELSE 0 END)
  FROM (SELECT fixture, phase,
               max(num) FILTER (WHERE metric = 'horizon_backends') AS backends,
               max(num) FILTER (WHERE metric = 'horizon_slots')    AS slots,
               max(num) FILTER (WHERE metric = 'horizon_prepared') AS prepared
          FROM proto.meas
         WHERE phase IN ('maint_before','maint_after','settle2_before','settle2_after')
         GROUP BY fixture, phase) h;
INSERT INTO proto.invariant
SELECT 'I14', count(*) FILTER (WHERE ok) || ' of ' || count(*) || ' version 2, sz = census size, tup = table count',
       bool_and(ok)
  FROM (SELECT captured_v = 2 AND captured_sz = base_size AND captured_sz = capture_bytes
               AND captured_tup = round(greatest(capture_tuples, -1)) AS ok FROM proto.score) s;
INSERT INTO proto.invariant
SELECT 'I15', count(*) FILTER (WHERE decide_bytes = maint_size AND decide_bytes = oracle_before) || ' of ' || count(*),
       bool_and(decide_bytes = maint_size AND decide_bytes = oracle_before)
  FROM proto.score;
INSERT INTO proto.invariant
SELECT 'I16', count(*) FILTER (WHERE action = expected_action) || ' of ' || count(*) || ' (disagreeing: '
              || coalesce(string_agg(fixture, ',') FILTER (WHERE action <> expected_action), 'none') || ')',
       bool_and(action = expected_action)
  FROM proto.score;
INSERT INTO proto.invariant
SELECT 'I17', coalesce(nullif('$act_line', ''), 'act has not run'),
       coalesce('$act_line' ~ ': ([0-9]+) of \1; unchanged by the second run: \1 of \1\$', false);
-- I18: BRIN's graduated FSM agreement, scored where the source makes it exact:
-- every regular page a VACUUM did not write, found by its LSN against the WAL
-- insert position read just before that VACUUM began.  The pages the
-- VACUUM's own summarization wrote are compared and reported, not scored.
INSERT INTO proto.invariant
SELECT 'I18', count(*) FILTER (WHERE untouched AND fsm_read = fsm_expected) || ' of '
              || count(*) FILTER (WHERE untouched)
              || ' regular pages the VACUUM did not write read their exact FSM category (failing: '
              || coalesce(string_agg(fixture || '/' || phase || '/' || blkno, ',')
                          FILTER (WHERE untouched AND fsm_read <> fsm_expected), 'none')
              || '); of the ' || count(*) FILTER (WHERE NOT untouched) || ' it wrote, '
              || count(*) FILTER (WHERE NOT untouched AND fsm_read = fsm_expected) || ' agree, '
              || count(*) FILTER (WHERE NOT untouched AND fsm_read > fsm_expected) || ' read higher and '
              || count(*) FILTER (WHERE NOT untouched AND fsm_read < fsm_expected) || ' lower, reported only',
       coalesce(bool_and(fsm_read = fsm_expected) FILTER (WHERE untouched), true)
  FROM (SELECT p.fixture, p.phase, p.blkno, p.fsm_read, p.fsm_expected,
               p.page_lsn <= w.num AS untouched
          FROM proto.brin_page p
          JOIN proto.vac_v v ON v.fixture = p.fixture AND v.post_phase = p.phase AND v.vacuum_ran = 1
          JOIN proto.meas w ON w.fixture = p.fixture AND w.phase = substring(v.tag from 9)
                           AND w.metric = 'wal_lsn_before') f;
SQL
  q "$DB" "SELECT count(*) FROM proto.invariant" | grep -q '^18$' \
    || die "the invariants did not all compute (see $OUT/invariants-build.log)"
  q "$DB" "SELECT id || ' ' || CASE WHEN holds THEN 'holds' ELSE 'FAILS' END || ': ' || reading
             FROM proto.invariant ORDER BY substring(id from 2)::int" > "$OUT/invariants.txt"
  cat "$OUT/invariants.txt"

  # I6, I8, I9 and I18 per census or per step, so every disagreement can be
  # read against the phase it happened in
  q "$DB" "SELECT 'I6 ' || fixture || ' [' || phase || '] revmap=' || b_revmap || ' items=' || b_items
             || ' unused=' || b_unused || CASE WHEN b_revmap = b_items THEN ' ok' ELSE ' DISAGREES' END
             FROM proto.census_v WHERE b_items IS NOT NULL
           UNION ALL
           SELECT 'I8 ' || fixture || ' [' || phase || '] meta(total=' || m_total || ', entry=' || m_entry
             || ', data=' || m_data || ', pending=' || m_pending || ') census(scanned=' || scanned
             || ', entry=' || c_entry || ', data=' || c_data || ', list=' || c_list
             || ', deleted=' || c_del || ', new=' || c_new || ', fsm=' || fsm || ')'
             || CASE WHEN m_entry = c_entry AND m_data = c_data + greatest(c_del - fsm, 0) AND m_total = scanned
                     THEN ' ok' ELSE ' differs' END
             FROM proto.census_v WHERE m_total IS NOT NULL
           UNION ALL
           SELECT 'I9 ' || v.fixture || ' [' || substring(v.tag from 9) || '] ' || coalesce(v.line, '?')
             || ' vacuum=' || v.vacuum_ran || ' bulkdelete=' || coalesce(v.scans_ran::text, '-')
             -- 12.2 reports no newly-deleted count, so a dash stands in for it
             || coalesce(' total=' || v.num_pages || ' newly=' || coalesce(v.newly::text, '-')
                         || ' deleted=' || v.deleted || ' free=' || v.free, '')
             || ' | before ' || coalesce(v.pre_phase, '-') || ' scanned=' || coalesce(pre.scanned::text, '-')
             || ' | after ' || coalesce(v.post_phase, '-') || ' scanned=' || coalesce(post.scanned::text, '-')
             || ' deleted=' || coalesce(post.c_del::text, '-') || ' new=' || coalesce(post.c_new::text, '-')
             || ' new_or_empty=' || coalesce(post.c_empty::text, '-') || ' fsm=' || coalesce(post.fsm::text, '-')
             FROM proto.vac_v v
             LEFT JOIN proto.census_v pre  ON pre.fixture  = v.fixture AND pre.phase  = v.pre_phase
             LEFT JOIN proto.census_v post ON post.fixture = v.fixture AND post.phase = v.post_phase
           UNION ALL
           SELECT 'I18 ' || fixture || ' [' || phase || '] ' || count(*) || ' regular pages: '
             || count(*) FILTER (WHERE fsm_read = fsm_expected) || ' agree, '
             || count(*) FILTER (WHERE fsm_read > fsm_expected) || ' higher, '
             || count(*) FILTER (WHERE fsm_read < fsm_expected) || ' lower, '
             || count(*) FILTER (WHERE evacuate) || ' flagged for evacuation'
             FROM proto.brin_page GROUP BY fixture, phase
           ORDER BY 1" > "$OUT/invariant-detail.txt"
  printf '    invariant detail lines: %s\n' "$(grep -c '' "$OUT/invariant-detail.txt")"

  q "$DB" "SELECT format('%-4s %-6s base=%s raw=%s maintained=%s rebuilt=%s truth=%s%% heap_relpages=%s heap_reltuples=%s',
             fixture, am, base_size, raw_size, maint_size, oracle_after, truth_pct, heap_relpages, heap_reltuples)
             FROM proto.score ORDER BY am, fixture" > "$OUT/phase-sizes.txt"
  q "$DB" "SELECT protocol || ' | ' || behavior || ' -> ' || fixture
             FROM proto.declared_coverage ORDER BY protocol, behavior" > "$OUT/coverage.txt"
  # Every census reading, as the census stored it: one row per fixture, phase
  # and metric.  The fixture database goes with the sandbox at clean, so this
  # file is where a reading that no other file prints - a hash index's
  # overflow pages and freed bitmap bits, a GiST index's leaf pages - survives.
  PSQL -d "$DB" -q -c "COPY (SELECT fixture, phase, metric, num, txt FROM proto.meas
                             ORDER BY fixture, phase, metric) TO STDOUT (FORMAT csv, HEADER)" \
    > "$OUT/meas.csv" || die "could not write $OUT/meas.csv"
  printf '    census readings: %s rows in meas.csv\n' "$(( $(grep -c '' "$OUT/meas.csv") - 1 ))"
  ! grep -q ' FAILS: ' "$OUT/invariants.txt" || die "a declared invariant failed (see $OUT/invariants.txt)"
}

# -------------------------------------------------------------- stage: probes
# Four mechanism probes.  None scores the method; each measures a fact the
# method or a protocol depends on.  They run after the oracle and the score.
stage_probes() {
  say "probes: who writes reltuples, the hash oracle, the GIN oracle, GiST builds"
  need_db; need_stage act
  q "$DB" "DROP SCHEMA IF EXISTS pr CASCADE" > /dev/null
  q "$DB" "CREATE SCHEMA pr" > /dev/null
  rt() {
    q "$DB" "SELECT format('%-34s table=%-8s hash=%-8s gin=%-8s gist=%-8s spgist=%-8s brin=%s', '$1',
               (SELECT reltuples FROM pg_class WHERE oid = 'pr.t1'::regclass),
               (SELECT reltuples FROM pg_class WHERE relname = 't1_hash'),
               (SELECT reltuples FROM pg_class WHERE relname = 't1_gin'),
               (SELECT reltuples FROM pg_class WHERE relname = 't1_gist'),
               (SELECT reltuples FROM pg_class WHERE relname = 't1_spgist'),
               (SELECT reltuples FROM pg_class WHERE relname = 't1_brin'))"
  }
  # P1: the table's reltuples - the tuple test's input - and each index's own,
  # after each writer in turn
  q "$DB" "CREATE TABLE pr.t1 (id bigint, k bigint, arr text[], r int8range, t text)
             WITH (autovacuum_enabled = off)" > /dev/null
  { printf -- '-- P1: reltuples after each writer, the table and one index per access method\n'
    rt 'CREATE TABLE'
    q "$DB" "INSERT INTO pr.t1 SELECT g, g, ARRAY['a'||g, 'b'||(g%1000)], int8range(g, g+10), 'x'||g
               FROM generate_series(1, 200000) g" > /dev/null
    rt 'INSERT 200,000 rows'
    qin "$DB" > "$OUT/probe-p1-build.log" 2>&1 <<'SQL'
CREATE INDEX t1_hash   ON pr.t1 USING hash   (k);
CREATE INDEX t1_gin    ON pr.t1 USING gin    (arr);
CREATE INDEX t1_gist   ON pr.t1 USING gist   (r);
CREATE INDEX t1_spgist ON pr.t1 USING spgist (t);
CREATE INDEX t1_brin   ON pr.t1 USING brin   (k) WITH (pages_per_range = 128);
SQL
    rt 'CREATE INDEX, five of them'
    printf 'ANALYZE pr.t1;\n' | qz "$DB" > "$OUT/probe-p1-analyze.log" 2>&1
    rt 'ANALYZE'
    q "$DB" "DELETE FROM pr.t1 WHERE id % 10 = 0" > /dev/null
    printf 'VACUUM pr.t1;\n' | qz "$DB" > "$OUT/probe-p1-vacuum.log" 2>&1
    rt 'DELETE 10 %, then VACUUM'
    q "$DB" "TRUNCATE pr.t1" > /dev/null
    rt 'TRUNCATE'
    q "$DB" "INSERT INTO pr.t1 SELECT g, g, ARRAY['a'||g, 'b'||(g%1000)], int8range(g, g+10), 'x'||g
               FROM generate_series(1, 200000) g" > /dev/null
    rt 'INSERT 200,000 rows again'
    q "$DB" "REINDEX INDEX pr.t1_hash" > /dev/null
    rt 'REINDEX INDEX the hash index'
    q "$DB" "SELECT 'heap blocks: ' || pg_relation_size('pr.t1') / current_setting('block_size')::int"
  } > "$OUT/probe-p1.txt" 2>&1
  cat "$OUT/probe-p1.txt"

  # P2: a hash rebuild is sized from the heap's estimate, not from the index
  local t i
  t=$(tbl h08); i=$(idx h08)
  { printf -- '\n-- P2: a hash rebuild is sized from the heap estimate (fixture h08)\n'
    printf 'heap relpages / reltuples: %s\n' "$(q "$DB" "SELECT relpages || ' / ' || reltuples FROM pg_class WHERE oid = '$t'::regclass")"
    q "$DB" "REINDEX INDEX $i" > /dev/null
    printf 'rebuilt at the true statistics: %s\n' "$(q "$DB" "SELECT pg_relation_size('$i')")"
    q "$DB" "UPDATE /* wiki_nbmaint_probe_forgery */ pg_class SET reltuples = 100 WHERE oid = '$t'::regclass" > /dev/null
    q "$DB" "REINDEX INDEX $i" > /dev/null
    printf 'rebuilt at reltuples = 100:     %s\n' "$(q "$DB" "SELECT pg_relation_size('$i')")"
    printf "ANALYZE %s;\n" "$t" | qz "$DB" > "$OUT/probe-p2-analyze.log" 2>&1
    q "$DB" "REINDEX INDEX $i" > /dev/null
    printf 'rebuilt after a fresh ANALYZE:  %s\n' "$(q "$DB" "SELECT pg_relation_size('$i')")"
  } > "$OUT/probe-p2.txt" 2>&1
  cat "$OUT/probe-p2.txt"

  # P3: the GIN oracle depends on the build's memory budget
  i=$(idx n04)
  { printf -- '\n-- P3: one GIN rebuild at three maintenance_work_mem values (fixture n04)\n'
    local mw
    for mw in 4MB 64MB 256MB; do
      printf "SET maintenance_work_mem = '%s';\nREINDEX INDEX %s;\n" "$mw" "$i" | qin "$DB" > /dev/null 2>&1
      printf 'maintenance_work_mem=%-6s rebuilt size=%s\n' "$mw" "$(q "$DB" "SELECT pg_relation_size('$i')")"
    done
  } > "$OUT/probe-p3.txt" 2>&1
  cat "$OUT/probe-p3.txt"

  # P4: which GiST operator class can take the sorted build at all
  { printf -- '\n-- P4: GIST_SORTSUPPORT_PROC (support function 11), per operator class the fixtures use\n'
    q "$DB" "SELECT opc.opcname || ': support 11 ' ||
               CASE WHEN EXISTS (SELECT 1 FROM pg_amproc ap WHERE ap.amprocfamily = opc.opcfamily
                                                           AND ap.amprocnum = 11)
                    THEN 'present, so the sorted build is possible'
                    ELSE 'absent, so the build is insert-driven' END
               FROM pg_opclass opc JOIN pg_am am ON am.oid = opc.opcmethod
              WHERE am.amname = 'gist' AND opc.opcname IN ('range_ops', 'point_ops') ORDER BY 1"
  } > "$OUT/probe-p4.txt" 2>&1
  cat "$OUT/probe-p4.txt"
}

# ---------------------------------------------------------------- stage: edge
# The comment handling, the ladder's boundaries, the candidate filters, and
# what step 2 does when another session holds a lock, edits a comment,
# rewrites a payload or renames an index while step 2 waits for its locks -
# case by case, in their own database.  Unscored: none is a bloat claim.
# Each case files what it expects before the texts run, and the stage prints
# expected against observed and fails the run on any difference.
edge_mk() {   # <table> <rows>: the build phase every edge table shares
  printf 'CREATE TABLE %s (id bigint, k bigint) WITH (autovacuum_enabled = off);\n' "$1"
  printf 'INSERT INTO %s SELECT g, g FROM generate_series(1, %s) g;\n' "$1" "$2"
  printf 'ANALYZE %s;\n' "$1"
  printf 'CREATE INDEX %s_i ON %s USING hash (k);\n' "$1" "$1"
}
edge_seen() {  # <round>: store step 1's rows through the view
  q "$EDB" "INSERT INTO proto.seen_plan (round, idx, action, notes)
              SELECT '$1', index_name, action, notes FROM proto.plan_v" > /dev/null
}
edge_snap() {  # <label>: every index's OID, file, size, table count and comment
  q "$EDB" "INSERT INTO proto.seen_cmt (label, idx, oid, filenode, bytes, tbl_tuples, cmt)
              SELECT '$1', c.relname, c.oid, c.relfilenode, pg_relation_size(c.oid),
                     t.reltuples::numeric, d.description
                FROM pg_class c JOIN pg_index x ON x.indexrelid = c.oid
                JOIN pg_class t ON t.oid = x.indrelid
                LEFT JOIN pg_description d ON d.objoid = c.oid
                      AND d.classoid = 'pg_class'::regclass AND d.objsubid = 0
               WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('i', 'I')" > /dev/null
}
edge_bg() {    # <tag> <sql...>: a background session, until edge_kill <tag>
  local tag=$1; shift
  printf '%s\n' "$@" | qbg "$EDB" > "$OUT/edge-bg-$tag.log" 2>&1 &
}
edge_kill() {
  q "$EDB" "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
             WHERE query LIKE '%wiki_nbmaint_edge_$1%' AND pid <> pg_backend_pid()" > /dev/null
  wait 2>/dev/null
}
edge_wait_lock() {  # <table> <mode> <granted>: poll until pg_locks shows it
  local n=0
  until [ "$(q "$EDB" "SELECT count(*) FROM pg_locks l JOIN pg_class c ON c.oid = l.relation
                         WHERE c.relname = '$1' AND l.mode = '$2' AND l.granted = $3")" -ge 1 ]; do
    n=$((n + 1)); [ "$n" -gt 200 ] && die "edge: no $2 (granted=$3) on $1 appeared"
    sleep 0.05
  done
}
# edge_during <round> <table> <sql>: run step 2 in the background, wait until
# it is queued for its SHARE lock on <table> - held off by a ROW EXCLUSIVE
# this function takes in another session first - then run <sql> as a third
# session, release the holder, and wait for step 2 to finish.  Step 2 waits
# up to its own lock_timeout of 5 s; the poll takes a few hundredths.
edge_during() {
  local round=$1 t=$2 sql=$3
  edge_bg "hold$round" "BEGIN;" "LOCK TABLE $t IN ROW EXCLUSIVE MODE;" \
    "SELECT /* wiki_nbmaint_edge_hold$round */ pg_sleep(300);" "COMMIT;"
  edge_wait_lock "$t" RowExclusiveLock true
  ( run_apply "$EDB" "edge$round" ) &
  local job=$!
  edge_wait_lock "$t" ShareLock false
  printf '%s\n' "$sql" | qin "$EDB" > "$OUT/edge-during-$round.log" 2>&1
  q "$EDB" "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
             WHERE query LIKE '%wiki_nbmaint_edge_hold$round%' AND pid <> pg_backend_pid()" > /dev/null
  wait "$job" || die "edge round $round: step 2 failed, see $OUT/apply-edge$round.log"
  wait 2>/dev/null
}
stage_edge() {
  say "edge: comments, boundaries, filters, locks, concurrent writers and the cap, case by case"
  need_texts
  q postgres "DROP DATABASE IF EXISTS $EDB" > /dev/null
  q postgres "DROP ROLE IF EXISTS nbmaint_other" > /dev/null
  q postgres "CREATE DATABASE $EDB" > /dev/null
  q postgres "CREATE ROLE nbmaint_other NOLOGIN" > /dev/null
  {
    printf 'CREATE SCHEMA proto;\n'
    printf 'CREATE TABLE proto.expect (round text, idx text, want text, human text, PRIMARY KEY (round, idx));\n'
    printf 'CREATE TABLE proto.seen_plan (round text, idx text, action text, notes text);\n'
    printf 'CREATE TABLE proto.seen_cmt (label text, idx text, oid oid, filenode oid, bytes bigint, tbl_tuples numeric, cmt text);\n'
    # the comment with its one reserved line's content cut out, newlines kept;
    # how many reserved lines it has; and whether that line is exactly the
    # version-2 grammar with sz and tup equal to the file and the table count
    printf '%s\n' "CREATE FUNCTION proto.human(c text) RETURNS text LANGUAGE sql IMMUTABLE AS
      \$f\$ SELECT regexp_replace(c, '^@nbmaint:\{.*\}\$', '', 'n') \$f\$;"
    printf '%s\n' "CREATE FUNCTION proto.nres(c text) RETURNS bigint LANGUAGE sql IMMUTABLE AS
      \$f\$ SELECT count(*) FROM regexp_matches(coalesce(c, ''), '^@nbmaint:\{.*\}\$', 'gn') \$f\$;"
    printf '%s\n' "CREATE FUNCTION proto.valid(c text, b numeric, t numeric) RETURNS boolean LANGUAGE sql IMMUTABLE AS
      \$f\$ SELECT coalesce((regexp_match(c, '(?n)^@nbmaint:\{\"v\":2,\"sz\":([0-9]+),\"tup\":(-?[0-9]+),\"at\":\"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}[+-][0-9]{2}(?::[0-9]{2})?\"\}\$'))[1]::numeric = b
                         AND (regexp_match(c, '(?n)^@nbmaint:\{\"v\":2,\"sz\":([0-9]+),\"tup\":(-?[0-9]+),'))[2]::numeric
                             = round(greatest(t, -1)), false) \$f\$;"
    local e
    for e in e_none e_human e_v1 e_bad e_junk e_nest e_dup e_two e_prose e_trail e_tailnl \
             e_mid e_shrink e_sz e_zero e_owner e_busy e_surv e_hold e_cedit e_cpay e_ren; do
      edge_mk "$e" 30000
    done
    edge_mk e_t13 13000
    edge_mk e_t7 7000
    edge_mk e_capok 5000
    printf 'CREATE INDEX e_sz_i2 ON e_sz USING hash (id);\n'
    printf 'CREATE INDEX e_t13_i2 ON e_t13 USING hash (id);\n'
    printf 'CREATE INDEX e_t7_i2 ON e_t7 USING hash (id);\n'
    # round G's rebuild that will fail: an expression index over an immutable
    # function that is later replaced by one that divides by zero
    printf "CREATE FUNCTION e_fail_f(bigint) RETURNS bigint LANGUAGE sql IMMUTABLE AS 'SELECT \$1';\n"
    printf 'CREATE TABLE e_capfail (id bigint, k bigint) WITH (autovacuum_enabled = off);\n'
    printf 'INSERT INTO e_capfail SELECT g, g FROM generate_series(1, 60000) g;\n'
    printf 'ANALYZE e_capfail;\n'
    printf 'CREATE INDEX e_capfail_i ON e_capfail USING hash (e_fail_f(k));\n'
    printf 'CREATE TABLE e_ren2 (id bigint, k bigint) WITH (autovacuum_enabled = off);\n'
    printf 'INSERT INTO e_ren2 SELECT g, g FROM generate_series(1, 30000) g;\n'
    printf 'ANALYZE e_none, e_human, e_v1, e_bad, e_junk, e_nest, e_dup, e_two, e_prose, e_trail, e_tailnl, e_mid, e_shrink, e_sz, e_zero, e_owner, e_busy, e_surv, e_hold, e_cedit, e_cpay, e_ren, e_ren2, e_t13, e_t7, e_capok, e_capfail;\n'
    # an index built on an empty table that nothing has counted
    printf 'CREATE TABLE e_unk (id bigint, k bigint) WITH (autovacuum_enabled = off);\n'
    printf 'CREATE INDEX e_unk_i ON e_unk USING hash (k);\n'
    # three indexes the filters must keep out
    printf 'CREATE TABLE e_btree (id bigint, k bigint);\nINSERT INTO e_btree SELECT g, g FROM generate_series(1, 30000) g;\n'
    printf 'CREATE INDEX e_btree_i ON e_btree (k);\n'
    printf 'CREATE TABLE e_invalid (id bigint, k bigint);\nINSERT INTO e_invalid SELECT g, g FROM generate_series(1, 1000) g;\n'
    printf 'CREATE TABLE e_part (k bigint) PARTITION BY RANGE (k);\n'
    printf 'CREATE TABLE e_part_1 PARTITION OF e_part FOR VALUES FROM (0) TO (100000);\n'
    printf 'INSERT INTO e_part SELECT g FROM generate_series(1, 30000) g;\n'
    printf 'CREATE INDEX e_part_i ON e_part USING hash (k);\n'
    printf 'ANALYZE e_part_1;\n'
    # the comments round A reads
    printf "COMMENT ON INDEX e_human_i IS E'Search index used by the application.\\\\nSecond line: an @ sign, a { and a } brace.\\\\n  \\\\n';\n"
    printf "COMMENT ON INDEX e_v1_i IS E'keep me\\\\n@nbmaint:{\"v\":1,\"sz\":123,\"tup\":456,\"at\":\"2020-01-01T00:00:00+00\"}';\n"
    printf "COMMENT ON INDEX e_bad_i IS '@nbmaint:{\"v\":2,\"sz\":\"big\",\"tup\":1,\"at\":\"x\"}';\n"
    printf "COMMENT ON INDEX e_junk_i IS E'above\\\\n@nbmaint: not json\\\\nbelow';\n"
    printf "COMMENT ON INDEX e_nest_i IS '@nbmaint:{\"x\":{\"v\":2,\"sz\":100,\"tup\":5}}';\n"
    printf "COMMENT ON INDEX e_dup_i IS '@nbmaint:{\"v\":2,\"sz\":1,\"tup\":1,\"at\":\"2026-01-01T00:00:00+00\",\"sz\":999}';\n"
    printf "COMMENT ON INDEX e_two_i IS E'@nbmaint:{\"v\":2,\"sz\":1,\"tup\":1,\"at\":\"2026-01-01T00:00:00+00\"}\\\\nhuman\\\\n@nbmaint:{\"v\":2,\"sz\":1,\"tup\":1,\"at\":\"2026-01-01T00:00:00+00\"}';\n"
    printf "COMMENT ON INDEX e_prose_i IS 'see @nbmaint:{\"v\":2,\"sz\":1,\"tup\":1,\"at\":\"2026-01-01T00:00:00+00\"} for the format';\n"
    printf "COMMENT ON INDEX e_trail_i IS E'human text  \\\\n\\\\n';\n"
    printf "COMMENT ON INDEX e_tailnl_i IS E'note\\\\n@nbmaint:{\"v\":1,\"sz\":1,\"tup\":1}\\\\n';\n"
    printf "COMMENT ON INDEX e_surv_i IS 'kept through both rebuilds';\n"
  } > "$SQLD/edge-build.sql"
  qz "$EDB" < "$SQLD/edge-build.sql" > "$OUT/edge-build.log" 2>&1
  # a CREATE INDEX CONCURRENTLY that fails on one row leaves an invalid index
  printf 'CREATE INDEX CONCURRENTLY e_invalid_i ON e_invalid USING hash ((1 / (k - 500)));\n' \
    | qe "$EDB" > "$OUT/edge-invalid.log" 2>&1
  qf "$EDB" "$SQLD/plan_view.sql" > /dev/null 2>&1

  # ---- round A: first run, every comment shape
  qin "$EDB" > "$OUT/edge-expect-A.log" 2>&1 <<'SQL'
INSERT INTO proto.expect (round, idx, want, human) VALUES
 ('A','e_none_i','initialize',''),
 ('A','e_human_i','initialize',E'Search index used by the application.\nSecond line: an @ sign, a { and a } brace.\n  \n\n'),
 ('A','e_v1_i','initialize',E'keep me\n'),
 ('A','e_bad_i','initialize',''),
 ('A','e_junk_i','initialize',E'above\n@nbmaint: not json\nbelow\n'),
 ('A','e_nest_i','initialize',''),
 ('A','e_dup_i','initialize',''),
 ('A','e_two_i','conflict',E'@nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"}\nhuman\n@nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"}'),
 ('A','e_prose_i','initialize',E'see @nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"} for the format\n'),
 ('A','e_trail_i','initialize',E'human text  \n\n\n'),
 ('A','e_tailnl_i','initialize',E'note\n\n'),
 ('A','e_mid_i','initialize',''),('A','e_shrink_i','initialize',''),
 ('A','e_sz_i','initialize',''),('A','e_sz_i2','initialize',''),
 ('A','e_t13_i','initialize',''),('A','e_t13_i2','initialize',''),
 ('A','e_t7_i','initialize',''),('A','e_t7_i2','initialize',''),
 ('A','e_zero_i','initialize',''),('A','e_owner_i','initialize',''),
 ('A','e_busy_i','initialize',''),('A','e_surv_i','initialize',E'kept through both rebuilds\n'),
 ('A','e_hold_i','initialize',''),('A','e_cedit_i','initialize',''),
 ('A','e_cpay_i','initialize',''),('A','e_ren_i','initialize',''),
 ('A','e_capok_i','initialize',''),('A','e_capfail_i','initialize',''),
 ('A','e_unk_i','initialize',''),('A','e_part_1_k_idx','initialize',''),
 ('A','e_btree_i','absent',''),('A','e_invalid_i','absent',''),('A','e_part_i','absent','');
SQL
  run_plan "$EDB" edgeA || die "edge round A: step 1 failed"
  edge_seen A
  edge_snap A-before
  run_apply "$EDB" edgeA || die "edge round A: step 2 failed"
  edge_snap A-after

  # ---- round B: forged payloads on the boundaries, one lock held elsewhere
  qin "$EDB" > "$OUT/edge-forge.log" 2>&1 <<'SQL'
CREATE FUNCTION proto.forge(p_idx text, p_before text, p_after text, p_sz numeric, p_tup numeric)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  EXECUTE format('COMMENT ON INDEX %I IS %L', p_idx,
    CASE WHEN p_before <> '' THEN p_before || E'\n' ELSE '' END
    || '@nbmaint:{"v":2,"sz":' || p_sz || ',"tup":' || p_tup || ',"at":"2026-01-01T00:00:00+00"}'
    || CASE WHEN p_after <> '' THEN E'\n' || p_after ELSE '' END);
END $fn$;
CREATE FUNCTION proto.cur(p_idx text) RETURNS numeric LANGUAGE sql AS
  $fn$ SELECT pg_relation_size(p_idx::regclass)::numeric $fn$;
CREATE FUNCTION proto.curtup(p_idx text) RETURNS numeric LANGUAGE sql AS
  $fn$ SELECT round(greatest(t.reltuples::numeric, -1)) FROM pg_index x
         JOIN pg_class t ON t.oid = x.indrelid WHERE x.indexrelid = p_idx::regclass $fn$;
SELECT proto.forge('e_mid_i',    'above', 'below', floor(proto.cur('e_mid_i') / 2),       proto.curtup('e_mid_i'));
SELECT proto.forge('e_shrink_i', '', '',           proto.cur('e_shrink_i') * 2,           proto.curtup('e_shrink_i'));
SELECT proto.forge('e_sz_i',     '', '',           floor(proto.cur('e_sz_i') / 1.30),     proto.curtup('e_sz_i'));
SELECT proto.forge('e_sz_i2',    '', '',           floor(proto.cur('e_sz_i2') / 1.30) + 1, proto.curtup('e_sz_i2'));
SELECT proto.forge('e_t13_i',    '', '',           proto.cur('e_t13_i'),  10000);
SELECT proto.forge('e_t13_i2',   '', '',           proto.cur('e_t13_i2'), 10001);
SELECT proto.forge('e_t7_i',     '', '',           proto.cur('e_t7_i'),   10000);
SELECT proto.forge('e_t7_i2',    '', '',           proto.cur('e_t7_i2'),  9999);
SELECT proto.forge('e_zero_i',   '', '',           proto.cur('e_zero_i'), 0);
SELECT proto.forge('e_busy_i',   '', '',           floor(proto.cur('e_busy_i') / 2), proto.curtup('e_busy_i'));
INSERT INTO e_unk SELECT g, g FROM generate_series(1, 10) g;
INSERT INTO proto.expect (round, idx, want, human) VALUES
 ('B','e_mid_i','reindex',E'above\n\nbelow'),
 ('B','e_shrink_i','refresh',''),
 ('B','e_sz_i','reindex',''),('B','e_sz_i2','skip',''),
 ('B','e_t13_i','reindex',''),('B','e_t13_i2','skip',''),
 ('B','e_t7_i','reindex',''),('B','e_t7_i2','skip',''),
 ('B','e_zero_i','reindex',''),
 ('B','e_busy_i','reindex',''),
 ('B','e_unk_i','skip',''),
 ('B','e_none_i','skip',''),('B','e_v1_i','skip',E'keep me\n'),
 ('B','e_human_i','skip',E'Search index used by the application.\nSecond line: an @ sign, a { and a } brace.\n  \n\n'),
 ('B','e_bad_i','skip',''),('B','e_junk_i','skip',E'above\n@nbmaint: not json\nbelow\n'),
 ('B','e_nest_i','skip',''),('B','e_dup_i','skip',''),
 ('B','e_two_i','conflict',E'@nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"}\nhuman\n@nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"}'),
 ('B','e_prose_i','skip',E'see @nbmaint:{"v":2,"sz":1,"tup":1,"at":"2026-01-01T00:00:00+00"} for the format\n'),
 ('B','e_trail_i','skip',E'human text  \n\n\n'),('B','e_tailnl_i','skip',E'note\n\n'),
 ('B','e_owner_i','skip',''),('B','e_surv_i','skip',E'kept through both rebuilds\n'),
 ('B','e_hold_i','skip',''),('B','e_cedit_i','skip',''),('B','e_cpay_i','skip',''),
 ('B','e_ren_i','skip',''),('B','e_capok_i','skip',''),('B','e_capfail_i','skip',''),
 ('B','e_part_1_k_idx','skip','');
SQL
  edge_bg holder "BEGIN;" "LOCK TABLE e_busy IN ROW EXCLUSIVE MODE;" \
    "SELECT /* wiki_nbmaint_edge_holder */ pg_sleep(300);" "COMMIT;"
  edge_wait_lock e_busy RowExclusiveLock true
  run_plan "$EDB" edgeB || die "edge round B: step 1 failed"
  edge_seen B
  edge_snap B-before
  run_apply "$EDB" edgeB || die "edge round B: step 2 failed"
  edge_snap B-after
  edge_kill holder

  # ---- round C: the lock is gone, so the skipped rebuild happens; then a
  # settled database: a further run writes nothing
  run_apply "$EDB" edgeC1 || die "edge round C: step 2 failed"
  edge_snap C1-after
  run_apply "$EDB" edgeC2 || die "edge round C: step 2, second run, failed"
  edge_snap C2-after

  # ---- round D: a role that owns none of the indexes
  run_plan "$EDB" edgeD 'SET ROLE nbmaint_other;' || die "edge round D: step 1 failed"
  edge_snap D-before
  run_apply "$EDB" edgeD 'SET ROLE nbmaint_other;' || die "edge round D: step 2 failed"
  edge_snap D-after

  # ---- round E: the comment survives both REINDEX forms
  edge_snap E-before
  q "$EDB" "REINDEX INDEX e_surv_i" > /dev/null
  edge_snap E-plain
  q "$EDB" "REINDEX INDEX CONCURRENTLY e_surv_i" > /dev/null
  edge_snap E-concurrent
  run_plan "$EDB" edgeE || die "edge round E: step 1 failed"
  edge_seen E

  # ---- round F: another session's temporary index is never a candidate
  edge_bg temp "CREATE TEMP TABLE e_tmp (k bigint);" \
    "INSERT INTO e_tmp SELECT g FROM generate_series(1, 1000) g;" \
    "CREATE INDEX e_tmp_i ON e_tmp USING hash (k);" \
    "SELECT /* wiki_nbmaint_edge_temp */ pg_sleep(300);"
  local n=0
  until [ "$(q "$EDB" "SELECT count(*) FROM pg_class WHERE relname = 'e_tmp_i'")" = 1 ]; do
    n=$((n + 1)); [ "$n" -gt 60 ] && die "edge: the temporary index never appeared"; sleep 0.5
  done
  run_plan "$EDB" edgeF || die "edge round F: step 1 failed"
  edge_seen F
  run_apply "$EDB" edgeF || die "edge round F: step 2 failed"
  edge_kill temp

  # ---- round H: another session holds ACCESS EXCLUSIVE on one index for the
  # whole run: step 1, one statement, is cancelled by its lock_timeout; step 2
  # counts that index failed and finishes every other one
  edge_snap H-before
  edge_bg hold "BEGIN;" "REINDEX INDEX e_hold_i;" \
    "SELECT /* wiki_nbmaint_edge_hold */ pg_sleep(300);" "COMMIT;"
  edge_wait_lock e_hold_i AccessExclusiveLock true
  local rc_h1
  run_plan "$EDB" edgeH; rc_h1=$?
  run_apply "$EDB" edgeH || die "edge round H: step 2 failed"
  edge_kill hold
  edge_snap H-after

  # ---- round I: a person rewrites the comment while step 2 waits for its
  # table lock; step 2 re-reads it under its locks and keeps the new text
  q "$EDB" "SELECT proto.forge('e_cedit_i', 'old human text', '', proto.cur('e_cedit_i') * 2,
                               proto.curtup('e_cedit_i'))" > /dev/null
  edge_snap I-before
  edge_during I e_cedit "SELECT format('COMMENT /* wiki_nbmaint_edge_edit */ ON INDEX e_cedit_i IS %L',
                           E'new human text, written while step 2 waited\n'
                           || substring(description from '(?n)^(@nbmaint:\{.*\})\$'))
                           FROM pg_description WHERE objoid = 'e_cedit_i'::regclass
                         \\gexec"
  edge_snap I-after

  # ---- round J: another run rewrites the payload to the file's true size
  # while step 2 waits; step 2's second read under the locks says skip
  q "$EDB" "SELECT proto.forge('e_cpay_i', '', '', floor(proto.cur('e_cpay_i') / 2),
                               proto.curtup('e_cpay_i'))" > /dev/null
  edge_snap J-before
  edge_during J e_cpay "SELECT proto.forge('e_cpay_i', '', '', proto.cur('e_cpay_i'), proto.curtup('e_cpay_i'));"
  edge_snap J-after

  # ---- round K: the index is renamed, and a new index takes its name, while
  # step 2 waits; step 2 finds the name no longer names the index it read
  q "$EDB" "SELECT proto.forge('e_ren_i', '', '', floor(proto.cur('e_ren_i') / 2),
                               proto.curtup('e_ren_i'))" > /dev/null
  edge_snap K-before
  edge_during K e_ren "ALTER INDEX e_ren_i RENAME TO e_ren_i_old;
                       CREATE INDEX e_ren_i ON e_ren2 USING hash (k);"
  edge_snap K-after
  run_apply "$EDB" edgeK2 || die "edge round K: the settling run of step 2 failed"
  edge_snap K2-after

  # ---- round G: max_reindex 1, and the first rebuild fails.  Step 2 runs with
  # one documented edit, that cap; the failed rebuild uses up the cap, so the
  # next index due is capped instead of rebuilt
  sed 's/^    max_reindex integer := 1000;   -- cap on the rebuilds one run may start$/    max_reindex integer := 1;      -- cap on the rebuilds one run may start/' \
    "$SQLD/apply.sql" > "$SQLD/apply-cap1.sql"
  [ "$(diff "$SQLD/apply.sql" "$SQLD/apply-cap1.sql" | grep -c '^[<>]')" = 2 ] \
    || die "edge round G: the documented edit did not change exactly one line"
  q "$EDB" "CREATE OR REPLACE FUNCTION e_fail_f(bigint) RETURNS bigint LANGUAGE sql IMMUTABLE AS
              'SELECT 1 / (\$1 - \$1)'" > /dev/null
  q "$EDB" "SELECT proto.forge('e_capfail_i', '', '', floor(proto.cur('e_capfail_i') / 2), proto.curtup('e_capfail_i')),
                   proto.forge('e_capok_i', '', '', floor(proto.cur('e_capok_i') / 2), proto.curtup('e_capok_i'))" > /dev/null
  edge_snap G-before
  APPLY_FILE="$SQLD/apply-cap1.sql" run_apply "$EDB" edgeG || die "edge round G: step 2 failed"
  edge_snap G-after

  # ---- the verdicts
  qat "$EDB" /dev/stdin > "$OUT/edge.txt" 2>&1 <<'SQL'
WITH pa AS (
  SELECT e.round, e.idx, e.want,
         coalesce((SELECT s.action FROM proto.seen_plan s WHERE s.round = e.round AND s.idx = e.idx), 'absent') AS seen
    FROM proto.expect e
)
SELECT format('plan %-2s %-16s want=%-10s seen=%-10s %s', round, idx, want, seen,
              CASE WHEN want = seen THEN 'ok' ELSE 'DIFFERS' END)
  FROM pa ORDER BY round, idx;
SQL
  qat "$EDB" /dev/stdin >> "$OUT/edge.txt" 2>&1 <<'SQL'
-- every comment step 2 wrote in round A: the human text byte for byte where
-- it was, exactly one reserved line, and a version-2 payload whose sz and
-- tup are the file and the table count; a conflict left exactly as it was
WITH b AS (SELECT * FROM proto.seen_cmt WHERE label = 'A-before'),
     a AS (SELECT * FROM proto.seen_cmt WHERE label = 'A-after'),
     e AS (SELECT * FROM proto.expect WHERE round = 'A' AND want <> 'absent')
SELECT format('write A %-15s %s', e.idx,
         CASE WHEN e.want = 'conflict' THEN
                CASE WHEN a.cmt = b.cmt AND a.cmt = e.human AND a.filenode = b.filenode
                     THEN 'ok (untouched)' ELSE 'DIFFERS: ' || coalesce(a.cmt, '<none>') END
              WHEN proto.human(a.cmt) = e.human AND proto.nres(a.cmt) = 1
                   AND proto.valid(a.cmt, a.bytes, a.tbl_tuples) AND a.filenode = b.filenode THEN 'ok'
              ELSE 'DIFFERS: ' || coalesce(replace(a.cmt, E'\n', '\n'), '<none>') END)
  FROM e JOIN a ON a.idx = e.idx JOIN b ON b.idx = e.idx
 ORDER BY e.idx;
SQL
  qat "$EDB" /dev/stdin >> "$OUT/edge.txt" 2>&1 <<'SQL'
-- round B: a rebuild changes the file and rewrites the payload in place; a
-- refresh rewrites the payload only; a skip changes nothing; the locked
-- table's index keeps its file and its forged payload
WITH b AS (SELECT * FROM proto.seen_cmt WHERE label = 'B-before'),
     a AS (SELECT * FROM proto.seen_cmt WHERE label = 'B-after'),
     e AS (SELECT * FROM proto.expect WHERE round = 'B')
SELECT format('write B %-15s want=%-8s %s', e.idx, e.want,
         CASE WHEN e.idx = 'e_busy_i' THEN
                CASE WHEN a.filenode = b.filenode AND a.cmt = b.cmt THEN 'ok (lock timed out, nothing written)' ELSE 'DIFFERS' END
              WHEN e.want = 'reindex' THEN
                CASE WHEN a.filenode <> b.filenode AND proto.human(a.cmt) = e.human
                          AND proto.human(a.cmt) = proto.human(b.cmt) AND proto.nres(a.cmt) = 1
                          AND proto.valid(a.cmt, a.bytes, a.tbl_tuples) THEN 'ok' ELSE 'DIFFERS' END
              WHEN e.want = 'refresh' THEN
                CASE WHEN a.filenode = b.filenode AND a.cmt <> b.cmt AND proto.human(a.cmt) = proto.human(b.cmt)
                          AND proto.valid(a.cmt, a.bytes, a.tbl_tuples) THEN 'ok' ELSE 'DIFFERS' END
              ELSE CASE WHEN a.filenode = b.filenode AND a.cmt IS NOT DISTINCT FROM b.cmt
                             AND (e.want = 'conflict' AND a.cmt = e.human OR proto.human(a.cmt) = e.human)
                        THEN 'ok' ELSE 'DIFFERS' END
         END)
  FROM e JOIN a ON a.idx = e.idx JOIN b ON b.idx = e.idx
 ORDER BY e.idx;
SQL
  # the run-level verdicts: each line states what it expected and ends in ok
  # or DIFFERS
  verdict() {   # <label> <expected> <observed>
    printf 'run    %-62s want=[%s] seen=[%s] %s\n' "$1" "$2" "$3" "$([ "$2" = "$3" ] && echo ok || echo DIFFERS)"
  }
  summary() { apply_summary "$1" | sed 's/^nbmaint: //'; }
  unchanged() {  # <index> <label before> <label after>: file and comment both unchanged
    q "$EDB" "SELECT coalesce(bool_and(a.cmt IS NOT DISTINCT FROM b.cmt AND a.filenode = b.filenode), false)
                FROM proto.seen_cmt a JOIN proto.seen_cmt b ON b.idx = a.idx
               WHERE a.idx = '$1' AND b.label = '$2' AND a.label = '$3'"
  }
  local ncand
  ncand=$(q "$EDB" "SELECT count(*) FROM proto.expect WHERE round = 'A' AND want <> 'absent'")
  {
    verdict 'A: step 2 counts' \
      "reindex=0 initialize=$((ncand - 1)) refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=0 changed=0 dry_run=f" \
      "$(summary edgeA)"
    verdict 'B: step 2 counts, one rebuild refused by the lock' \
      'reindex=5 initialize=0 refresh=1 blocked=0 conflict=1 failed=1 gone=0 capped=0 started=5 changed=0 dry_run=f' \
      "$(summary edgeB)"
    verdict 'B: the refused rebuild is a lock timeout, SQLSTATE 55P03' 'e_busy_i 55P03' \
      "$(grep -Eo 'nbmaint: e_busy_i: nothing written: .*SQLSTATE [0-9A-Z]+' "$OUT/apply-edgeB.log" \
           | sed -E 's/^nbmaint: (e_busy_i):.*SQLSTATE ([0-9A-Z]+)$/\1 \2/')"
    verdict 'C1: the lock is gone, so the refused rebuild happens' \
      'reindex=1 initialize=0 refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=1 changed=0 dry_run=f' \
      "$(summary edgeC1)"
    verdict 'C2: a settled database: nothing to do' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=0 changed=0 dry_run=f' \
      "$(summary edgeC2)"
    verdict 'C2: every comment and every file unchanged by that run' 't' \
      "$(q "$EDB" "SELECT bool_and(a.cmt IS NOT DISTINCT FROM b.cmt AND a.filenode = b.filenode)
                     FROM proto.seen_cmt a JOIN proto.seen_cmt b ON b.idx = a.idx
                    WHERE a.label = 'C2-after' AND b.label = 'C1-after'")"
    verdict 'D: step 1 as a role that owns nothing: every row blocked' "$ncand blocked, 0 other" \
      "$(grep -Ec '\| blocked +\|' "$OUT/plan-edgeD.txt") blocked, $(grep -Ec '\| (initialize|refresh|reindex|skip|conflict) +\|' "$OUT/plan-edgeD.txt") other"
    verdict 'D: step 2 as that role' \
      "reindex=0 initialize=0 refresh=0 blocked=$ncand conflict=0 failed=0 gone=0 capped=0 started=0 changed=0 dry_run=f" \
      "$(summary edgeD)"
    verdict 'D: nothing written by it' 't' \
      "$(q "$EDB" "SELECT bool_and(a.cmt IS NOT DISTINCT FROM b.cmt AND a.filenode = b.filenode)
                     FROM proto.seen_cmt a JOIN proto.seen_cmt b ON b.idx = a.idx
                    WHERE a.label = 'D-after' AND b.label = 'D-before'")"
    verdict 'E: REINDEX keeps OID and comment, gives a new file' 'same oid, new file, same comment' \
      "$(q "$EDB" "SELECT CASE WHEN p.oid = b.oid THEN 'same oid' ELSE 'new oid' END || ', ' ||
                          CASE WHEN p.filenode <> b.filenode THEN 'new file' ELSE 'same file' END || ', ' ||
                          CASE WHEN p.cmt = b.cmt THEN 'same comment' ELSE 'changed comment' END
                     FROM proto.seen_cmt b, proto.seen_cmt p
                    WHERE b.idx = 'e_surv_i' AND b.label = 'E-before'
                      AND p.idx = 'e_surv_i' AND p.label = 'E-plain'")"
    verdict 'E: REINDEX CONCURRENTLY moves the comment to a new OID' 'new oid, same comment' \
      "$(q "$EDB" "SELECT CASE WHEN c.oid = b.oid THEN 'same oid' ELSE 'new oid' END || ', ' ||
                          CASE WHEN c.cmt = b.cmt THEN 'same comment' ELSE 'changed comment' END
                     FROM proto.seen_cmt b, proto.seen_cmt c
                    WHERE b.idx = 'e_surv_i' AND b.label = 'E-before'
                      AND c.idx = 'e_surv_i' AND c.label = 'E-concurrent'")"
    verdict 'E: step 1 after both rebuilds of an unchanged table' 'skip' \
      "$(q "$EDB" "SELECT action FROM proto.seen_plan WHERE round = 'E' AND idx = 'e_surv_i'")"
    verdict 'F: rows naming another session'"'"'s temporary index' '0' \
      "$(q "$EDB" "SELECT count(*) FROM proto.seen_plan WHERE round = 'F' AND idx = 'e_tmp_i'")"
    verdict 'F: step 2 passes it by without counting it' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=0 changed=0 dry_run=f' \
      "$(summary edgeF)"
    verdict 'H: step 1 under a lock held on one index is cancelled' 'exit 3, canceling statement due to lock timeout' \
      "exit $rc_h1, $(grep -Eo 'canceling statement due to lock timeout' "$OUT/plan-edgeH.txt" | head -1)"
    verdict 'H: step 2 counts that index failed and finishes the others' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=1 gone=0 capped=0 started=0 changed=0 dry_run=f' \
      "$(summary edgeH)"
    verdict 'H: the failure is a lock timeout on that index' 'e_hold_i 55P03' \
      "$(grep -Eo 'nbmaint: e_hold_i: nothing written: .*SQLSTATE [0-9A-Z]+' "$OUT/apply-edgeH.log" \
           | sed -E 's/^nbmaint: (e_hold_i):.*SQLSTATE ([0-9A-Z]+)$/\1 \2/')"
    verdict 'H: nothing written to it' 't' "$(unchanged e_hold_i H-before H-after)"
    verdict 'I: step 2 refreshes the index that waited' \
      'reindex=0 initialize=0 refresh=1 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=0 changed=0 dry_run=f' \
      "$(summary edgeI)"
    verdict 'I: the text written while it waited is the text kept' 't' \
      "$(q "$EDB" "SELECT proto.human(cmt) = E'new human text, written while step 2 waited\n'
                          AND proto.nres(cmt) = 1 AND proto.valid(cmt, bytes, tbl_tuples)
                     FROM proto.seen_cmt WHERE idx = 'e_cedit_i' AND label = 'I-after'")"
    verdict 'J: the decision is taken again under the locks' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=0 changed=1 dry_run=f' \
      "$(summary edgeJ)"
    verdict 'J: reindex before the locks, skip under them' 'e_cpay_i reindex skip' \
      "$(grep -Eo 'nbmaint: public\.e_cpay_i was [a-z]+ before the locks and [a-z]+ under them' "$OUT/apply-edgeJ.log" \
           | sed -E 's/^nbmaint: public\.(e_cpay_i) was ([a-z]+) before the locks and ([a-z]+) under them$/\1 \2 \3/')"
    verdict 'J: no rebuild, and the comment is the one written meanwhile' 't' \
      "$(q "$EDB" "SELECT a.filenode = b.filenode AND a.cmt <> b.cmt AND proto.valid(a.cmt, a.bytes, a.tbl_tuples)
                          AND a.cmt ~ '\"at\":\"2026-01-01T00:00:00\+00\"'
                     FROM proto.seen_cmt a JOIN proto.seen_cmt b ON b.idx = a.idx
                    WHERE a.idx = 'e_cpay_i' AND b.label = 'J-before' AND a.label = 'J-after'")"
    verdict 'K: the renamed index is refused, and nothing else is touched' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=1 gone=0 capped=0 started=0 changed=0 dry_run=f' \
      "$(summary edgeK)"
    verdict 'K: the refusal names it under its new name, SQLSTATE 55000' 'e_ren_i_old 55000' \
      "$(grep -Eo 'nbmaint: e_ren_i_old: nothing written: renamed, dropped or re-created since it was read .SQLSTATE [0-9A-Z]+' "$OUT/apply-edgeK.log" \
           | sed -E 's/^nbmaint: (e_ren_i_old):.*SQLSTATE ([0-9A-Z]+)$/\1 \2/')"
    verdict 'K: the renamed index keeps its file and comment' 't' \
      "$(q "$EDB" "SELECT a.filenode = b.filenode AND a.cmt = b.cmt
                     FROM proto.seen_cmt a JOIN proto.seen_cmt b ON b.oid = a.oid
                    WHERE b.idx = 'e_ren_i' AND b.label = 'K-before' AND a.label = 'K-after'")"
    verdict 'K: the index that took the name was never written' 't' \
      "$(q "$EDB" "SELECT cmt IS NULL FROM proto.seen_cmt WHERE idx = 'e_ren_i' AND label = 'K-after'")"
    verdict 'K2: the next run rebuilds one and initializes the other' \
      'reindex=1 initialize=1 refresh=0 blocked=0 conflict=1 failed=0 gone=0 capped=0 started=1 changed=0 dry_run=f' \
      "$(summary edgeK2)"
    verdict 'G: a failed rebuild uses up max_reindex 1' \
      'reindex=0 initialize=0 refresh=0 blocked=0 conflict=1 failed=1 gone=0 capped=1 started=1 changed=0 dry_run=f' \
      "$(summary edgeG)"
    verdict 'G: the failure is the rebuild itself, SQLSTATE 22012' 'e_capfail_i 22012' \
      "$(grep -Eo 'nbmaint: e_capfail_i: nothing written: .*SQLSTATE [0-9A-Z]+' "$OUT/apply-edgeG.log" \
           | sed -E 's/^nbmaint: (e_capfail_i):.*SQLSTATE ([0-9A-Z]+)$/\1 \2/')"
    verdict 'G: the next index due is capped, not rebuilt' 'e_capok_i capped, t t' \
      "$(grep -Eo 'nbmaint: public\.e_capok_i needs a rebuild, max_reindex 1 reached' "$OUT/apply-edgeG.log" \
           | sed -E 's/^nbmaint: public\.(e_capok_i) needs.*$/\1 capped/'), $(unchanged e_capok_i G-before G-after) $(unchanged e_capfail_i G-before G-after)"
    q "$EDB" "SELECT format('info   E %-11s oid=%s filenode=%s comment_md5=%s', label, oid, filenode, md5(cmt))
               FROM proto.seen_cmt WHERE idx = 'e_surv_i' AND label IN ('E-before','E-plain','E-concurrent')
              ORDER BY CASE label WHEN 'E-before' THEN 1 WHEN 'E-plain' THEN 2 ELSE 3 END"
    q "$EDB" "SELECT 'info   B e_unk_i notes: ' || notes FROM proto.seen_plan WHERE round = 'B' AND idx = 'e_unk_i'"
    q "$EDB" "SELECT 'info   B e_t13_i and e_t7_i notes: ' || string_agg(idx || ': ' || notes, '; ' ORDER BY idx)
               FROM proto.seen_plan WHERE round = 'B' AND idx IN ('e_t13_i','e_t13_i2','e_t7_i','e_t7_i2','e_sz_i','e_sz_i2')"
    q "$EDB" "SELECT 'info   payload bytes after round C: ' || min(length(substring(cmt from '(?n)^(@nbmaint:\{.*\})\$')))
               || ' to ' || max(length(substring(cmt from '(?n)^(@nbmaint:\{.*\})\$')))
               FROM proto.seen_cmt WHERE label = 'C2-after' AND proto.nres(cmt) = 1"
    q "$EDB" "SELECT 'info   e_human_i as stored: ' || replace(cmt, chr(10), ' \\n ')
               FROM proto.seen_cmt WHERE label = 'C2-after' AND idx = 'e_human_i'"
  } >> "$OUT/edge.txt" 2>&1
  local n_ok n_diff
  n_ok=$(grep -Ec ' ok( \(.*\))?$' "$OUT/edge.txt"); n_diff=$(grep -c 'DIFFERS' "$OUT/edge.txt")
  printf 'edge verdicts: %s ok, %s different\n' "$n_ok" "$n_diff" | tee -a "$OUT/edge.txt"
  q postgres "DROP DATABASE IF EXISTS $EDB" > /dev/null
  q postgres "DROP ROLE IF EXISTS nbmaint_other" > /dev/null
  [ "$n_diff" = 0 ] || die "$n_diff edge cases differ from what was filed for them (see $OUT/edge.txt)"
}

# ------------------------------------------------------------- stage: defeat
# The no-defeat rule, shown working.  A throwaway fixture's churn commits while
# an undeclared snapshot is held, and it then gets the same checked
# maintenance step every scored fixture gets.  The check must stop the run, so
# here it is called in a subshell, the one place a die is expected, and its
# exit status and message are what the stage records.  Its own database, its
# proofs under out/defeat, and nothing scored.  A check that did not fire
# fails the run.
stage_defeat() {
  say "defeat: an undeclared snapshot across one maintenance step must stop the run"
  local ddb=defeat keep=$OUT rc
  q postgres "DROP DATABASE IF EXISTS $ddb" > /dev/null
  q postgres "CREATE DATABASE $ddb" > /dev/null
  proto_ddl | qin "$ddb" > "$OUT/defeat-ddl.log" 2>&1 || die "defeat: proto DDL failed"
  qz "$ddb" > "$OUT/defeat-build.log" 2>&1 <<'SQL' || die "defeat: build failed"
CREATE TABLE f_zz (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO f_zz SELECT g, g FROM generate_series(1, 100000) g;
ANALYZE f_zz;
CREATE INDEX f_zz_i ON f_zz USING hash (k);
SQL
  hold_snapshot "$ddb" zz
  printf 'DELETE FROM f_zz WHERE id %% 2 = 0;\n' | qin "$ddb" > "$OUT/defeat-churn.log" 2>&1 \
    || die "defeat: churn failed"
  OUT="$keep/defeat"; mkdir -p "$OUT"; : > "$OUT/maintenance-proof.txt"
  ( EXPECT_DIE=1; run_maint zz "$ddb" maint ) > "$keep/defeat-run.log" 2>&1; rc=$?
  OUT=$keep
  release_snapshot "$ddb" zz
  { printf 'exit status of the checked maintenance step: %s, %s\n' "$rc" \
      "$([ "$rc" -ne 0 ] && echo 'the run stopped, as the rule requires' || echo 'NOT STOPPED: the check did not fire')"
    grep -h 'FATAL:' "$OUT/defeat-run.log"
    cat "$OUT/defeat/maintenance-proof.txt"
  } > "$OUT/defeat.txt"
  q postgres "DROP DATABASE IF EXISTS $ddb" > /dev/null
  cat "$OUT/defeat.txt"
  [ "$rc" -ne 0 ] || die "defeat: a defeated maintenance step was not caught"
}

# -------------------------------------------------------------- stage: verify
# The page against what ran: the two texts re-extracted and compared with the
# files that ran, and this script's own block with the file that is running.
# Any difference fails the run.
stage_verify() {
  say "verify: the page's texts and this script, against what ran"
  need_texts
  local x
  : > "$OUT/verify.txt"
  md_block_with sql wiki_nbmaint_plan_12_17 "$PAGE" > "$OUT/x-plan.sql"
  md_block_with sql wiki_nbmaint_apply_12_17 "$PAGE" > "$OUT/x-apply.sql"
  for x in plan apply; do
    if cmp -s "$OUT/x-$x.sql" "$SQLD/$x.sql"; then
      printf '%-6s the page text is the text that ran (%s)\n' "$x" "$(sha "$SQLD/$x.sql")" >> "$OUT/verify.txt"
    else
      printf '%-6s DIFFERS from the text that ran\n' "$x" >> "$OUT/verify.txt"
    fi
  done
  if md_block_with bash '# nbmaint_suite_v12.sh - the PostgreSQL 12 leg' "$PAGE" > "$OUT/x-script.sh"; then
    if cmp -s "$OUT/x-script.sh" "${BASH_SOURCE[0]}"; then
      printf 'script the page block is the file that ran (%s)\n' "$(sha "${BASH_SOURCE[0]}")" >> "$OUT/verify.txt"
    else
      printf 'script DIFFERS from the file that ran\n' >> "$OUT/verify.txt"
    fi
  else
    printf 'script NOT FOUND in the page\n' >> "$OUT/verify.txt"
  fi
  cat "$OUT/verify.txt"
  ! grep -Eq 'DIFFERS|NOT FOUND' "$OUT/verify.txt" || die "the page is not what ran (see $OUT/verify.txt)"
}

# ------------------------------------------------------------ stage: criteria
# The errors a run provokes on purpose.  Everything else in the server log is
# unexpected, and an unexpected error or a maintenance skip line fails the run.
DELIBERATE='contains unexpected zero page|invalid transaction termination|REINDEX CONCURRENTLY cannot be executed from a function|syntax error at or near "\|\|"|canceling statement due to statement timeout|canceling statement due to lock timeout|division by zero|terminating connection due to administrator command|is not a btree index|is not a GIN index|is not a hash index|is not supported|REINDEX is not yet implemented for partitioned indexes'
stage_criteria() {
  say "criteria: everything a reader checks first, in one file"
  local all unexpected skips
  grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:.]+ UTC \[[0-9]+\] (ERROR|FATAL|PANIC):' "$OUT/server.log" \
    > "$OUT/server-errors-all.txt" 2>/dev/null
  grep -Ev "$DELIBERATE" "$OUT/server-errors-all.txt" > "$OUT/server-errors-unexpected.txt"
  all=$(grep -c '' "$OUT/server-errors-all.txt"); unexpected=$(grep -c '' "$OUT/server-errors-unexpected.txt")
  grep -E 'skipping (vacuum|analyze) of|canceling autovacuum task' "$OUT/server.log" > "$OUT/server-maint-skips.txt"
  skips=$(grep -c '' "$OUT/server-maint-skips.txt")
  {
    printf '1. texts\n';            sed 's/^/   /' "$OUT/hashes.txt"
    printf '2. engine checks\n';    sed 's/^/   /' "$OUT/checks.txt"
    printf '2b. build\n';           sed 's/^/   /' "$OUT/pin.txt"
    printf '3. fixtures built: %s; not built: %s\n' "$(printf '%s\n' $SCORED | grep -c .)" "${SKIPPED:-none}"
    printf '4. maintenance proofs: %s ok, %s DEFEATED\n' \
      "$(grep -c ' ok ' "$OUT/maintenance-proof.txt")" "$(grep -c 'DEFEATED' "$OUT/maintenance-proof.txt")"
    printf '5. timeouts in force, every VACUUM and ANALYZE session of the run:\n'
    grep -h -Eo 'timeouts in force: .*' "$OUT"/*.log | sort | uniq -c | sed 's/^/   /'
    printf '6. score\n';            sed 's/^/   /' "$OUT/score-summary.txt"
    printf '7. invariants\n';       sed 's/^/   /' "$OUT/invariants.txt"
    printf '8. act\n';              head -4 "$OUT/act.txt" | sed 's/^/   /'
    printf '9. edge\n';             tail -1 "$OUT/edge.txt" | sed 's/^/   /'
    printf '10. exact\n';           sed 's/^/   /' "$OUT/exact.txt"
    printf '10b. defeat\n';         sed 's/^/   /' "$OUT/defeat.txt" 2>/dev/null
    printf '11. server log: %s ERROR/FATAL/PANIC lines, %s deliberate, %s unexpected; %s maintenance skip lines\n' \
      "$all" "$((all - unexpected))" "$unexpected" "$skips"
    sed 's/^/   unexpected: /' "$OUT/server-errors-unexpected.txt" | head -5
    printf '12. verify\n';          sed 's/^/   /' "$OUT/verify.txt" 2>/dev/null
    printf '13. stage timings (seconds)\n'; sed 's/^/   /' "$OUT/timing.txt" 2>/dev/null
  } > "$OUT/criteria.txt" 2>&1
  cat "$OUT/criteria.txt"
  [ "$unexpected" = 0 ] || die "the server log has $unexpected unexpected error lines"
  [ "$skips" = 0 ] || die "the server log has $skips maintenance skip lines"
}

stage_report() {
  say "report: the files under $OUT"
  ls -1 "$OUT" | grep -Ev '^(census|horizon|build|churn|maint|settle2|oracle|snapshot)-' | sed 's/^/    /'
  printf '    ... and %s per-fixture logs\n' "$(ls -1 "$OUT" | grep -Ec '^(census|horizon|build|churn|maint|settle2|oracle|snapshot)-')"
}

# ---------------------------------------------------------------- stop, clean
# -m fast disconnects clients and writes a shutdown checkpoint.  The stop is
# then confirmed the way the teardown rule asks, and the stage dies rather
# than report a stop that did not happen, so clean never deletes a live
# cluster.  Both run only on a sandbox the guard has checked and found to be
# this script's own.
stage_stop() {
  say "stop: the sandbox cluster, cleanly"
  if [ "$SANDBOX_STATE" != ours ]; then note "no sandbox at $SANDBOX: nothing to stop"; return 0; fi
  if [ -x "$BIN/pg_ctl" ] && [ -s "$DATA/postmaster.pid" ] \
       && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1 || die "pg_ctl -m fast stop failed"
  else
    note "not running"
  fi
  [ -e "$DATA/postmaster.pid" ] && die "$DATA/postmaster.pid still exists"
  pgrep -f -- "-D $DATA" > /dev/null 2>&1 && die "a postgres process still runs on $DATA"
  [ -z "$(ls -A "$SOCK" 2>/dev/null)" ] || die "socket directory $SOCK is not empty"
  note "confirmed: no postmaster.pid, no postgres process on $DATA, socket directory empty"
}
stage_clean() {
  if [ "$SANDBOX_STATE" != ours ]; then say "clean"; note "no sandbox at $SANDBOX: nothing to delete"; return 0; fi
  stage_stop
  # the guard ran before anything else; check once more that the path about
  # to be deleted is still the canonical, marked sandbox
  [ "$(canon_dir "$SANDBOX")" = "$SANDBOX" ] && [ -f "$SANDBOX/$MARKER_NAME" ] \
    || die "refusing to delete $SANDBOX: it is no longer the marked sandbox"
  rm -rf -- "$SANDBOX"
  [ -e "$SANDBOX" ] && die "the sandbox is still there"
  SANDBOX_STATE=absent
  note "sandbox deleted: $SANDBOX"
}
stage_reset() {
  say "reset: drop the databases and the role, so a re-run starts at declare"
  local d
  for d in "$DB" "$PDB" "$EDB" defeat; do q postgres "DROP DATABASE IF EXISTS $d" > /dev/null; done
  q postgres "DROP ROLE IF EXISTS nbmaint_other" > /dev/null
}

need_server() {
  [ -x "$BIN/postgres" ] || die "no install under $INST: run the build stage first"
  [ -d "$DATA" ] || die "no cluster under $DATA: run the cluster stage first"
  "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1 || stage_start
}

ALL="build check cluster texts exact facts declare fixtures churn autoanalyze crosscheck decide oracle act score probes edge defeat verify criteria report"

# The dispatcher: the guard first, then every stage in turn.  A stage that
# returns non-zero, or dies inside a subshell, stops the run with exit status
# 1, and the EXIT trap stops the cluster.
main() {
  local stages="$*" s t0 rc
  [ -z "$stages" ] && stages="$ALL"
  for s in $stages; do
    declare -F "stage_$s" > /dev/null || die "no such stage: $s (have: $ALL start stop reset clean)"
  done
  case " $stages " in
    " clean "|" stop "|" stop clean ") sandbox_guard existing ;;
    *) sandbox_guard create ;;
  esac
  trap on_exit EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  [ "$SANDBOX_STATE" = ours ] && rm -f -- "$FAILMARK"
  for s in $stages; do
    case "$s" in
      build|check|cluster|start|stop|clean) : ;;
      *) need_server ;;
    esac
    t0=$(date +%s)
    "stage_$s"; rc=$?
    [ "$rc" = 0 ] || die "stage $s failed with exit status $rc"
    if [ "$SANDBOX_STATE" = ours ] && [ -s "$FAILMARK" ]; then
      die "stage $s: a check inside a subshell failed: $(head -1 "$FAILMARK")"
    fi
    [ "$SANDBOX_STATE" = ours ] && [ -d "$OUT" ] \
      && printf '%-12s %s\n' "$s" "$(( $(date +%s) - t0 ))" >> "$OUT/timing.txt"
  done
  say "done: $stages"
}

main "$@"
```

## Context Reviewed

- **Where the baseline lives.** `pg_description`'s key and text column; `CommentObject`'s
  lock and ownership check; `CreateComments`'s replace-or-insert on the same key; the
  `COMMENT` reference page's "only one comment string is stored for each object";
  `check_object_ownership` for an index, `object_ownercheck` and its superuser bypass, and
  `pg_has_role`'s `USAGE` path through `pg_role_aclcheck` to `has_privs_of_role`.
- **What a rebuild does to it.** `reindex_index`'s `ShareLock` on the table,
  `AccessExclusiveLock` on the index, other-session temp refusal, new relation file and
  `index_build`; `index_build`'s two `index_update_stats` calls and the `-1` special case;
  `index_concurrently_swap`'s comment move; `RelationSetNewRelfilenumber`'s `reltuples =
  -1`; `index_create` copying the table's owner; `ATExecChangeOwner`'s index branch.
- **Who can rebuild, and how.** `ExecReindex`'s `PreventInTransactionBlock` for
  `CONCURRENTLY`; `ReindexIndex`'s dispatch, including `ReindexPartitions` for a
  partitioned index; `RangeVarCallbackForReindexIndex`'s table lock mode and `MAINTAIN`
  check; `PreventInTransactionBlock`'s two messages.
- **Running a `DO` block that commits.** `ProcessUtility`'s atomic-context test and the
  `DoStmt` dispatch; `_SPI_commit`'s refusal in an atomic context; PL/pgSQL's
  `exception_matches_conditions` and the two conditions `OTHERS` leaves out; the timeout
  GUCs' contexts; the autovacuum launcher and worker forcing them to 0.
- **The table's count.** `do_analyze_rel`'s table and index `vac_update_relstats` calls;
  `heap_vacuum_rel`'s `vac_update_relstats` with `vac_estimate_reltuples`; the GIN and BRIN
  builds' `index_tuples`; `brinvacuumcleanup` passing `brinsummarize`'s count; the
  `pg_class.reltuples` definition and its `-1`; `float4_numeric`'s `FLT_DIG`.
- **Size.** `pg_relation_size`'s `try_relation_open` and NULL return, and the SQL wrapper
  that reads the main fork; the one `RelationTruncate` call in the six index AM
  directories, inside `#ifdef NOT_USED`; the hash README's no-shrink paragraph; GIN's
  closing length re-read; `hashbuild`'s heap estimate and `_hash_init_metabuffer`'s bucket
  count; `_hash_alloc_buckets`' zero page at the end of a splitpoint; the BRIN README,
  the revmap's per-range slot, `brinRevmapExtend`, and `brinsummarize`'s rule that a
  `VACUUM` leaves the partial range at the end unsummarized.
- **The maintenance the fixtures ran.** `VACUUM`'s `OldestXmin`, the dead-tuple gate on
  index vacuuming, `do_index_cleanup` and `INDEX_CLEANUP OFF`, and the two `VERBOSE` lines
  the checks parse; `hashvacuumcleanup`'s NULL return.
- **The instruments.** `pgstat_hash_page`, and the 17 branch's history for commit
  `036decbba2`; `gistchoose`'s random tie-break; the `pgstattuple`, `pgstatindex`,
  `pgstathashindex` and `pgstatginindex`
  refusal messages the instrument matrix provokes; `get_raw_page_internal`'s superuser
  check.
- **The reserved line.** `parse_re_flags`' `n` flag and the newline-sensitive mode the
  functions chapter describes; `textregexsubstr`'s and `regexp_match`'s NULL on no match;
  the `pg_input_is_valid` and `pg_stat_force_next_flush` catalog entries.
- **Step 2's locks, identity check and isolation.** `pg_relation_size`'s lock through
  `try_relation_open`; the `set_config` and `current_setting` catalog entries;
  `ReindexIndex`'s table-before-index order and `RangeVarCallbackForReindexIndex`'s table
  lock mode; `AlterTableGetLockLevel`'s level for an owner change,
  `RangeVarCallbackForAlterRelation`'s ownership check, and `ATExecChangeOwner`'s index
  branch and no-op path; `RenameRelation`'s two lock modes; `LockTableAclCheck`; the lock
  conflict table; the PL/pgSQL chapter on trapping errors and on the isolation level of a
  transaction started inside a procedure; the [MVCC](../../../glossary.md#mvcc) chapter's read committed and repeatable
  read; `default_transaction_isolation`'s GUC entry; the `ALTER INDEX` [command tag](../../../glossary.md#command-tag).
- **The protocol cross-checks.** The `index scan needed:` line; hash's bulk-delete
  statistics; `gistvacuumpage`'s page classes and `gistdeletepage`'s counters;
  `spgvacuumpage`'s free pages, SP-GiST's final statistics and fixed blocks, and
  `PageIsEmpty`; `brinvacuumcleanup`; `ginvacuumcleanup`'s free pages;
  `br_page_get_freespace`, the FSM's categories and their two conversions, and
  `BrinSpecialSpace`; `brin_vacuum_scan` and `brin_page_cleanup`; and the three BRIN paths
  that write or skip a page's FSM entry, in `brin_doinsert`, `brin_doupdate` and
  `brin_getinsertbuffer`.
- **The cluster settings.** The `guc_tables.c` entry of every setting the legs change.
- **The protocols as they stood on 2026-09-24.** Both concept pages' coverage lists and
  their two declared exceptions each, re-read after that day's change removed "a `VACUUM`
  whose index cleanup did not run" from both, and the source page's corpus, which dropped
  `h06` and `n11` the same day.
- **Read-only servers.** `ClassifyUtilityCommandAsReadOnly` for `COMMENT` and the
  read-only and recovery gate in `standard_ProcessUtility`.
- **Tests.** No shipped test covers a COMMENT-stored baseline or this method. The engine's
  regression suite passed on both builds, as did the suites of the contrib modules the
  cross-checks read: `pageinspect`, `pgstattuple` and `pg_freespacemap` on 17.11, and the
  first two on 12.2, whose `pg_freespacemap` declares no suite.

## Evidence Map

| Claim | Evidence |
|---|---|
| a comment is one string per object, replaced whole | [pg_description.h#FormData](../../../../raw/postgres-17/src/include/catalog/pg_description.h#L48-L57), [comment.c#CreateComments](../../../../raw/postgres-17/src/backend/commands/comment.c#L133-L171), [comment.sgml#replaces](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L87-L93) |
| writing it needs ownership of the index, which `pg_has_role(..., 'USAGE')` tests | [comment.c#CommentObject-ownership](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L76), [objectaddress.c#check_object_ownership](../../../../raw/postgres-17/src/backend/catalog/objectaddress.c#L2382-L2401), [aclchk.c#object_ownercheck](../../../../raw/postgres-17/src/backend/catalog/aclchk.c#L4146-L4214), [acl.c#pg_has_role_id](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L4779-L4793), [acl.c#pg_role_aclcheck](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L4877-L4900); measured: edge round D |
| an index's owner is its table's | [index.c#index_create-owner](../../../../raw/postgres-17/src/backend/catalog/index.c#L1008-L1014), [tablecmds.c#ATExecChangeOwner-index](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14543-L14562) |
| the comment survives both `REINDEX` forms | [index.c#reindex_index-rebuild](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789), [index.c#index_concurrently_swap-comment](../../../../raw/postgres-17/src/backend/catalog/index.c#L1740-L1784); measured: edge round E, both legs |
| a rebuild recounts the table, so step 2 reads the baseline after it | [index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135), [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2789-L2842); measured: P1 |
| `REINDEX` locks | [index.c#reindex_index-locks](../../../../raw/postgres-17/src/backend/catalog/index.c#L3601-L3614), [index.c#reindex_index-index-lock](../../../../raw/postgres-17/src/backend/catalog/index.c#L3647-L3654), [indexcmds.c#RangeVarCallbackForReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2857-L2912) |
| reading an index's size locks it, so step 2's scan reads only the catalogs | [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L371), [relation.c#try_relation_open](../../../../raw/postgres-17/src/backend/access/common/relation.c#L88-L108); measured: edge round H, both legs |
| a setting made with `set_config(..., true)` ends with its transaction, and a missing one reads as NULL | [pg_proc.dat#set_config](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L6270-L6273), [pg_proc.dat#current_setting-missing_ok](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L6268-L6269); measured: facts, both legs |
| step 2 takes `REINDEX INDEX`'s two locks, table first, before it decides | [indexcmds.c#ReindexIndex-lock-order](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2812-L2829), [indexcmds.c#RangeVarCallbackForReindexIndex-table-lockmode](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2871-L2872), [index.c#reindex_index-locks](../../../../raw/postgres-17/src/backend/catalog/index.c#L3601-L3614), [lockcmds.c#LockTableAclCheck](../../../../raw/postgres-17/src/backend/commands/lockcmds.c#L280-L299) |
| `ALTER INDEX ... OWNER TO` its current owner takes `AccessExclusiveLock`, checks ownership, and writes and prints nothing | [tablecmds.c#AlterTableGetLockLevel-ChangeOwner](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L4542-L4547), [tablecmds.c#RangeVarCallbackForAlterRelation-ownership](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L17904-L17906), [tablecmds.c#ATExecChangeOwner-index](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14543-L14562), [tablecmds.c#ATExecChangeOwner-noop](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14614-L14618); measured: facts, both legs |
| no comment and no rename lands on an index while step 2 holds its locks | [comment.c#CommentObject-ownership](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L76), [lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L64-L104), [tablecmds.c#RenameRelation-lockmode](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L4101-L4106); measured: edge rounds I, J and K, both legs |
| a rebuild that fails still uses up its place under `max_reindex` | [plpgsql.sgml#trapping-errors](../../../../raw/postgres-17/doc/src/sgml/plpgsql.sgml#L2856-L2860); measured: edge round G, both legs |
| step 2 needs read committed, and sets it for its session | [plpgsql.sgml#transaction-defaults](../../../../raw/postgres-17/doc/src/sgml/plpgsql.sgml#L3743-L3744), [mvcc.sgml#read-committed](../../../../raw/postgres-17/doc/src/sgml/mvcc.sgml#L317-L333), [mvcc.sgml#repeatable-read](../../../../raw/postgres-17/doc/src/sgml/mvcc.sgml#L508-L513), [guc_tables.c#default_transaction_isolation](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4820-L4827) |
| `ALTER INDEX` fires DDL event triggers | [cmdtag.h#PG_CMDTAG](../../../../raw/postgres-17/src/include/tcop/cmdtag.h#L19), [cmdtaglist.h#ALTER-INDEX](../../../../raw/postgres-17/src/include/tcop/cmdtaglist.h#L42) |
| `REINDEX CONCURRENTLY` cannot run from a `DO` block | [indexcmds.c#ExecReindex-concurrently](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2736-L2738), [xact.c#PreventInTransactionBlock](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L3594-L3633); measured: facts, both legs |
| a `DO` block commits only outside a transaction block | [utility.c#isAtomicContext](../../../../raw/postgres-17/src/backend/tcop/utility.c#L551), [utility.c#DoStmt](../../../../raw/postgres-17/src/backend/tcop/utility.c#L706-L708), [spi.c#_SPI_commit](../../../../raw/postgres-17/src/backend/executor/spi.c#L227-L241); measured: facts, both legs |
| `WHEN OTHERS` does not catch a statement timeout, and does catch a lock timeout | [pl_exec.c#exception_matches_conditions](../../../../raw/postgres-17/src/pl/plpgsql/src/pl_exec.c#L1583-L1597); measured: facts and edge rounds B and C, both legs |
| the other-session temp filter | [index.c#reindex_index-other-temp](../../../../raw/postgres-17/src/backend/catalog/index.c#L3697-L3704), [namespace.c#isOtherTempNamespace](../../../../raw/postgres-17/src/backend/catalog/namespace.c#L3706-L3720); measured: edge round F |
| the partitioned-index filter | [indexcmds.c#ReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2803-L2850); measured: facts, size 0 on both legs |
| a dropped index reads as NULL size | [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L371) |
| the size is the main fork | [system_functions.sql#pg_relation_size](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L285-L289) |
| none of these index files is truncated by `VACUUM` | [spgvacuum.c#truncation-disabled](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L877-L900), [README#no-shrink](../../../../raw/postgres-17/src/backend/access/hash/README#L31-L34), [ginvacuum.c#ginvacuumcleanup-relength](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L794-L802); measured: invariant I1, both legs |
| the payload is one whole line, found in newline-sensitive mode, and a regex that does not match returns NULL instead of raising | [regexp.c#parse_re_flags-n](../../../../raw/postgres-17/src/backend/utils/adt/regexp.c#L418-L420), [func.sgml#newline-sensitive](../../../../raw/postgres-17/doc/src/sgml/func.sgml#L7449-L7458), [regexp.c#textregexsubstr](../../../../raw/postgres-17/src/backend/utils/adt/regexp.c#L583-L604), [regexp.c#regexp_match](../../../../raw/postgres-17/src/backend/utils/adt/regexp.c#L1367-L1390); measured: edge round A, both legs |
| `pg_input_is_valid` exists on 17; absent on 12.2 | [pg_proc.dat#pg_input_is_valid](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7202-L7204); measured: facts |
| `reltuples` is `-1` when unknown, `TRUNCATE` writes `-1`, and a build on an empty table leaves it | [pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L66), [relcache.c#RelationSetNewRelfilenumber-reltuples](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3943-L3954), [index.c#index_update_stats-empty-table](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842); measured: P1, and `0` on 12.2 |
| `ANALYZE` and `VACUUM` write the table's count | [analyze.c#table-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L632-L645), [vacuumlazy.c#new_live_tuples](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1034-L1037), [vacuumlazy.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L572-L575), [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1300-L1366) |
| an index's own count means entries, rows or ranges depending on the writer | [gininsert.c#indtuples](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L271), [gininsert.c#index_tuples](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L425), [brin.c#brinbuild-index_tuples](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1248-L1258), [analyze.c#index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663), [brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332); measured: P1 |
| six-digit rounding of `reltuples`, applied to each of the two counts separately | [numeric.c#float4_numeric](../../../../raw/postgres-17/src/backend/utils/adt/numeric.c#L4708-L4740); measured: facts |
| the pay-off threshold is applied to the unrounded reclaimed fraction | the `score` stage of both leg scripts, under [Measurement Script](#measurement-script) |
| a BRIN index grows with its heap | [README#brin-summary](../../../../raw/postgres-17/src/backend/access/brin/README#L6-L13), [brin_revmap.c#HEAPBLK_TO_REVMAP](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L40-L43), [brin_revmap.c#brinRevmapExtend](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L108-L121), [brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332), [brin.c#brinsummarize-partial](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1916-L1925); measured: `b10` to `b13` |
| a hash rebuild is sized from the heap's estimate | [hash.c#hashbuild-estimate](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L133-L137), [hashpage.c#_hash_init_metabuffer](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L509-L523); measured: P2, `h04`, `h12` |
| `INDEX_CLEANUP OFF` leaves the index untouched | [vacuumlazy.c#do_index_cleanup-init](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L387-L397); not measured: `h06` and `n11` were removed, and neither protocol has required the case since 2026-09-24 |
| the no-defeat proofs | [vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122), [vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052), [vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L657-L663), [vacuumlazy.c#verbose-index-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L732), [hash.c#hashvacuumcleanup](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L647-L663); measured: every maintenance step, and the defeat stage |
| the `VERBOSE` index line, count by count, for each AM | [vacuumlazy.c#verbose-index-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L732), [vacuumlazy.c#index-scan-needed](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L695-L700), [hash.c#hashbulkdelete-stats](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L631-L637), [hash.c#hashvacuumcleanup](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L647-L663), [gistvacuum.c#gistvacuumpage-classes](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L298-L309), [gistvacuum.c#gistdeletepage-counters](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L655-L658), [spgvacuum.c#spgvacuumpage-fsm](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L665-L683), [spgvacuum.c#final-stats](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L902-L905), [spgist_private.h#fixed-blocks](../../../../raw/postgres-17/src/include/access/spgist_private.h#L47-L53), [bufpage.h#PageIsEmpty](../../../../raw/postgres-17/src/include/storage/bufpage.h#L214-L224), [brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332), [ginvacuum.c#ginvacuumcleanup-free](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L794); measured: invariant I9, both legs |
| a deleted GiST page stays unrecyclable until its deletion XID is older than every snapshot's horizon, so `g08` does not reach that row | [gistvacuum.c#gistdeletepage-deletexid](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L641-L656), [gistutil.c#gistPageRecyclable](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L885-L908); measured: `g08`'s two `VACUUM`s, both legs |
| a BRIN page's own free space against its FSM entry, and where the two must agree | [brin_pageops.c#br_page_get_freespace](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L913-L927), [freespace.c#FSM_CATEGORIES](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L64-L66), [freespace.c#fsm_space_avail_to_cat](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L402-L421), [freespace.c#fsm_space_cat_to_avail](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L427-L435), [brin_page.h#BrinSpecialSpace](../../../../raw/postgres-17/src/include/access/brin_page.h#L29-L60), [brin.c#brin_vacuum_scan](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2154-L2193), [brin_pageops.c#brin_page_cleanup](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L609-L661), [brin_pageops.c#brin_getinsertbuffer-fsm-policy](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L679-L682), [brin_pageops.c#brin_doinsert-extended-freespace](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L417-L419), [brin_pageops.c#brin_doinsert-fsm](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L460-L464), [brin_pageops.c#brin_doupdate-move](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L244-L313), [brin_pageops.c#brin_getinsertbuffer-record](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L861-L865); measured: invariant I18, both legs |
| timeouts forced to 0, as autovacuum does | [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470), [autovacuum.c#launcher-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L518-L526), [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631), [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642), [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653); measured: every `VACUUM` and `ANALYZE` session |
| the context of every other setting the legs change | [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457), [guc_tables.c#fsync](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1096-L1107), [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270), [guc_tables.c#work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2447-L2458), [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2465-L2474), [guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417), [guc_tables.c#log_timezone](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4104-L4112), [guc_tables.c#TimeZone](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4394-L4403); measured: `settings.txt`, both legs |
| the raw-page reader needs superuser | [rawpage.c#get_raw_page_internal](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L141-L199) |
| 17's `pgstattuple` reads an all-zero hash page as free space; 12.2 refuses it | [pgstattuple.c#pgstat_hash_page](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L453-L495), [hashpage.c#_hash_alloc_buckets](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L967-L1037), commit `036decbba2` in the 17 checkout's history; measured: 12.2's instrument matrix and hash censuses |
| `g09`'s size moves between passes | [gistutil.c#gistchoose-random](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L406-L429), [gistutil.c#gistchoose-prng](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L505-L511); measured: this run beside the run filed before the removal, an earlier pass and the source page |
| a standby can run step 1 only | [utility.c#comment-not-read-only](../../../../raw/postgres-17/src/backend/tcop/utility.c#L164-L217), [utility.c#recovery-gate](../../../../raw/postgres-17/src/backend/tcop/utility.c#L570-L583) |
| every scored number | the two leg scripts under [Measurement Script](#measurement-script), run end to end on the date in [The last run](#the-last-run) |

## Open Questions

1. **PostgreSQL 13 to 16 were not built.** The texts use nothing a 12 server lacks, and
   both ends run them unmodified, but the claim "12 through 17" is two measured points and
   a reading of what the texts call.
2. **12.2 is not the last 12 minor.** The `pgstattuple` refusal of an all-zero hash page
   was measured on 12.2 only. Commit `036decbba2`'s message says the fix went back to 13,
   which implies later 12 minors keep the refusal, but no later 12 minor was built here.
3. **The coverage row "a BRIN summary that moved to another page" is not reached on
   12.2.** On 17.11 it is reached by `b11`, which 12.2 cannot build, and `b10` and `b12`
   left no orphaned line pointer on either leg.
4. **One decision sits within 2 points of the pay-off threshold.** `n05` returned
   21.45 % against 23.08 %. The threshold was declared before the run and is not
   moved here; a reader with a different pay-off should rescore it first.
5. **Which untouched table the census analyzes depends on timing.** In the recorded run
   the census analyzed `h00` as well as `tc_past` on 17.11, and `tc_past` alone on 12.2.
   Over the three passes of 2026-09-24, the 17 leg analyzed `h00` in the baseline pass and
   the recorded run but not in the middle pass, and the 12 leg never did; the 2026-09-22
   recorded runs analyzed `tc_past` alone on both legs, after a development pass that also
   analyzed `h00`. Each time it happened, `h00`'s build-phase inserts had reached the shared
   statistics after its build-phase `ANALYZE`, so the census read 1,000,000 modifications
   against a threshold of 100,050: the publication hazard the concept pages describe. No
   decision depends on it, because `h00`'s count is the same either way, but the census's
   list of tables is not a fixed output.
6. **`g09`'s size moves between passes.** On 17.11 the recorded run of 2026-09-24 read
   `C` as 453,828,608 bytes. The same day's baseline pass of the filed script read
   454,500,352, and a pass of the edited script before its `meas.csv` dump read
   450,707,456. The three filings before this revision, from the same fixture recipe, read
   456,310,784 (commit `ddcdf74`), 453,812,224 (commit `d69c03b`) and 449,568,768 (commit
   `9b535e2`); an earlier development pass read 452,902,912; and the source page filed
   454,885,376 on 2026-09-16 and 451,428,352 on 2026-09-24. Only the insert-grown file
   moves on 17.11: the sorted build `B` and the sorted rebuild `R` were byte-identical in
   every recorded run and pass. On 12.2, where the build and the rebuild are insert-driven
   too, all three move from run to run: the recorded run read `B`, `C` and `R` as
   97,976,320, 487,448,576 and 78,086,144; the baseline pass read 97,935,360,
   481,804,288 and 78,118,912; the middle pass read 97,886,208, 482,197,504 and 78,176,256;
   `ddcdf74` read 97,902,592, 487,817,216 and 78,102,528; its first 12 run, set aside for
   its reporting defect, read 97,935,360, 488,275,968 and 78,028,800; `d69c03b` read
   97,968,128, 482,336,768 and 78,053,376; and `9b535e2` read 98,041,856, 488,620,032 and
   78,061,568. GiST's `gistchoose` breaks ties between equally good subtrees at random, so
   a GiST index grown by inserts of many equally placed keys, as `g09`'s grid of points is,
   is not the same size twice
   ([gistutil.c#gistchoose-random](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L406-L429),
   [gistutil.c#gistchoose-prng](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L505-L511)).
   That is the likely cause, and the split between the sorted files, which held still, and
   the insert-grown ones, which moved, fits it; no run isolated it. Neither the decision
   nor the score moved: `g09` read `reindex` and `PASS` on every pass, with a rebuild
   returning 83.8 to 84.5 % in the recorded runs and passes.
7. **The 12 leg's publication wait is a second, not an interlock.** Without
   `pg_stat_force_next_flush()`, each churn session exits and the leg waits one second
   before the maintenance step. The census verdicts on 12.2 came out as designed, but
   nothing proves a slower collector could not reorder them.
8. **The horizon proof is two reads, not an interlock**, as both concept pages say of
   their own proofs.
9. **Would a third stored value fix the out-of-band rebuild?** Storing the relation file
   number would let rule 3 recognize any rebuild, not only one that shrank the file, and
   would remove the second rebuild the `act` stage measured. The brief fixes the payload
   at two values, so this page does not add it.
10. **No non-core access method was scored.** The text accepts any non-B-tree index,
   `bloom` included, but the ported corpus has no `bloom` fixture.
11. **No fixture reaches a GiST page that is deleted but not recyclable under a held
   snapshot.** `g08`'s snapshot is taken before its churn commits, so the deleted rows
   stay visible to it, and the `VACUUM` under it removes none of them and deletes no page.
   A deleted page stays unrecyclable
   until its deletion XID, the next-XID counter when it was deleted, is older than every
   snapshot's horizon
   ([gistvacuum.c#gistdeletepage-deletexid](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L641-L656),
   [gistutil.c#gistPageRecyclable](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L885-L908)),
   so a snapshot taken after one `VACUUM` deletes pages and held through a second one
   would reach the row. The ported corpus has no such fixture, and this revision files the
   row as not reached instead of adding one.
12. **I18 is scored only on the BRIN pages the `VACUUM` did not write.** That was 2 pages
   on each leg, so the invariant is a narrow check. The pages the `VACUUM`'s own
   summarization wrote are compared and reported, not scored: on 17.11, 13 of 18 read
   their exact category, 3 higher and 2 lower; on 12.2, 4 of 6, 2 higher and 0 lower. The source explains both
   directions, but no run tied a page's reading to the insert or the move behind it. By the
   same reading, a second `VACUUM` with no writes since the first would record every
   regular page's free space in its scan and then summarize nothing, so a census after it
   could score every page; this run does not take one.
13. **Step 1 is one statement, so one locked index cancels the whole plan.** Edge round H
   measured it on both legs. A plan that survives it needs an exception block per index,
   which only a PL/pgSQL block has
   ([plpgsql.sgml#trapping-errors](../../../../raw/postgres-17/doc/src/sgml/plpgsql.sgml#L2856-L2860));
   this revision keeps step 1 a single read-only `SELECT` and lists the limit under
   [Known limitations](#known-limitations).

## Source References

- [pg_description.h#FormData](../../../../raw/postgres-17/src/include/catalog/pg_description.h#L48-L57)
- [comment.c#CommentObject-ownership](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L76)
- [comment.c#CreateComments](../../../../raw/postgres-17/src/backend/commands/comment.c#L133-L171)
- [comment.sgml#replaces](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L87-L93)
- [objectaddress.c#check_object_ownership](../../../../raw/postgres-17/src/backend/catalog/objectaddress.c#L2382-L2401)
- [aclchk.c#object_ownercheck](../../../../raw/postgres-17/src/backend/catalog/aclchk.c#L4146-L4214)
- [acl.c#pg_has_role_id](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L4779-L4793)
- [acl.c#pg_role_aclcheck](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L4877-L4900)
- [index.c#index_create-owner](../../../../raw/postgres-17/src/backend/catalog/index.c#L1008-L1014)
- [index.c#index_concurrently_swap-comment](../../../../raw/postgres-17/src/backend/catalog/index.c#L1740-L1784)
- [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2789-L2842)
- [index.c#index_update_stats-empty-table](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842)
- [index.c#index_build-update-stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135)
- [index.c#reindex_index-locks](../../../../raw/postgres-17/src/backend/catalog/index.c#L3601-L3614)
- [index.c#reindex_index-index-lock](../../../../raw/postgres-17/src/backend/catalog/index.c#L3647-L3654)
- [index.c#reindex_index-other-temp](../../../../raw/postgres-17/src/backend/catalog/index.c#L3697-L3704)
- [index.c#reindex_index-rebuild](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789)
- [indexcmds.c#ExecReindex-concurrently](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2736-L2738)
- [indexcmds.c#ReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2803-L2850)
- [indexcmds.c#RangeVarCallbackForReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2857-L2912)
- [indexcmds.c#RangeVarCallbackForReindexIndex-table-lockmode](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2871-L2872)
- [indexcmds.c#ReindexIndex-lock-order](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2812-L2829)
- [tablecmds.c#ATExecChangeOwner-index](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14543-L14562)
- [tablecmds.c#ATExecChangeOwner-noop](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14614-L14618)
- [tablecmds.c#AlterTableGetLockLevel-ChangeOwner](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L4542-L4547)
- [tablecmds.c#RangeVarCallbackForAlterRelation-ownership](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L17904-L17906)
- [tablecmds.c#RenameRelation-lockmode](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L4101-L4106)
- [relcache.c#RelationSetNewRelfilenumber-reltuples](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3943-L3954)
- [pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L66)
- [analyze.c#table-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L632-L645)
- [analyze.c#index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663)
- [vacuumlazy.c#do_index_cleanup-init](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L387-L397)
- [vacuumlazy.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L572-L575)
- [vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L657-L663)
- [vacuumlazy.c#verbose-index-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L732)
- [vacuumlazy.c#new_live_tuples](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1034-L1037)
- [vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052)
- [vacuumlazy.c#index-scan-needed](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L695-L700)
- [vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122)
- [vacuum.c#vac_estimate_reltuples](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1300-L1366)
- [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L371)
- [system_functions.sql#pg_relation_size](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L285-L289)
- [regexp.c#textregexsubstr](../../../../raw/postgres-17/src/backend/utils/adt/regexp.c#L583-L604)
- [regexp.c#parse_re_flags-n](../../../../raw/postgres-17/src/backend/utils/adt/regexp.c#L418-L420)
- [regexp.c#regexp_match](../../../../raw/postgres-17/src/backend/utils/adt/regexp.c#L1367-L1390)
- [numeric.c#float4_numeric](../../../../raw/postgres-17/src/backend/utils/adt/numeric.c#L4708-L4740)
- [pg_proc.dat#pg_input_is_valid](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7202-L7204)
- [pg_proc.dat#current_setting-missing_ok](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L6268-L6269)
- [pg_proc.dat#set_config](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L6270-L6273)
- [spi.c#_SPI_commit](../../../../raw/postgres-17/src/backend/executor/spi.c#L227-L241)
- [utility.c#comment-not-read-only](../../../../raw/postgres-17/src/backend/tcop/utility.c#L164-L217)
- [utility.c#isAtomicContext](../../../../raw/postgres-17/src/backend/tcop/utility.c#L551)
- [utility.c#recovery-gate](../../../../raw/postgres-17/src/backend/tcop/utility.c#L570-L583)
- [utility.c#DoStmt](../../../../raw/postgres-17/src/backend/tcop/utility.c#L706-L708)
- [xact.c#PreventInTransactionBlock](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L3594-L3633)
- [pl_exec.c#exception_matches_conditions](../../../../raw/postgres-17/src/pl/plpgsql/src/pl_exec.c#L1583-L1597)
- [namespace.c#isOtherTempNamespace](../../../../raw/postgres-17/src/backend/catalog/namespace.c#L3706-L3720)
- [guc_tables.c#fsync](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1096-L1107)
- [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457)
- [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2261-L2270)
- [guc_tables.c#work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2447-L2458)
- [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2465-L2474)
- [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620)
- [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)
- [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642)
- [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653)
- [guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417)
- [guc_tables.c#log_timezone](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4104-L4112)
- [guc_tables.c#TimeZone](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4394-L4403)
- [guc_tables.c#default_transaction_isolation](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4820-L4827)
- [autovacuum.c#launcher-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L518-L526)
- [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470)
- [spgvacuum.c#truncation-disabled](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L877-L900)
- [spgvacuum.c#final-stats](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L902-L905)
- [spgvacuum.c#spgvacuumpage-fsm](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L665-L683)
- [README#no-shrink](../../../../raw/postgres-17/src/backend/access/hash/README#L31-L34)
- [ginvacuum.c#ginvacuumcleanup-relength](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L794-L802)
- [ginvacuum.c#ginvacuumcleanup-free](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L794)
- [hash.c#hashbuild-estimate](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L133-L137)
- [hash.c#hashvacuumcleanup](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L647-L663)
- [hash.c#hashbulkdelete-stats](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L631-L637)
- [hashpage.c#_hash_init_metabuffer](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L509-L523)
- [hashpage.c#_hash_alloc_buckets](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L967-L1037)
- [README#brin-summary](../../../../raw/postgres-17/src/backend/access/brin/README#L6-L13)
- [brin_revmap.c#HEAPBLK_TO_REVMAP](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L40-L43)
- [brin_revmap.c#brinRevmapExtend](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L108-L121)
- [brin.c#brinbuild-index_tuples](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1248-L1258)
- [brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332)
- [brin.c#brinsummarize-partial](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1916-L1925)
- [brin.c#brin_vacuum_scan](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2154-L2193)
- [gininsert.c#indtuples](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L271)
- [gininsert.c#index_tuples](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L425)
- [gistutil.c#gistchoose-random](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L406-L429)
- [gistutil.c#gistchoose-prng](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L505-L511)
- [pgstattuple.c#pgstat_hash_page](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L453-L495)
- [rawpage.c#get_raw_page_internal](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L141-L199)
- [brin_page.h#BrinSpecialSpace](../../../../raw/postgres-17/src/include/access/brin_page.h#L29-L60)
- [brin_pageops.c#br_page_get_freespace](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L913-L927)
- [brin_pageops.c#brin_doinsert-extended-freespace](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L417-L419)
- [brin_pageops.c#brin_doinsert-fsm](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L460-L464)
- [brin_pageops.c#brin_getinsertbuffer-fsm-policy](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L679-L682)
- [brin_pageops.c#brin_doupdate-move](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L244-L313)
- [brin_pageops.c#brin_getinsertbuffer-record](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L861-L865)
- [brin_pageops.c#brin_page_cleanup](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L609-L661)
- [bufpage.h#PageIsEmpty](../../../../raw/postgres-17/src/include/storage/bufpage.h#L214-L224)
- [cmdtag.h#PG_CMDTAG](../../../../raw/postgres-17/src/include/tcop/cmdtag.h#L19)
- [cmdtaglist.h#ALTER-INDEX](../../../../raw/postgres-17/src/include/tcop/cmdtaglist.h#L42)
- [freespace.c#FSM_CATEGORIES](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L64-L66)
- [freespace.c#fsm_space_avail_to_cat](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L402-L421)
- [freespace.c#fsm_space_cat_to_avail](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L427-L435)
- [func.sgml#newline-sensitive](../../../../raw/postgres-17/doc/src/sgml/func.sgml#L7449-L7458)
- [gistvacuum.c#gistdeletepage-counters](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L655-L658)
- [gistvacuum.c#gistdeletepage-deletexid](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L641-L656)
- [gistvacuum.c#gistvacuumpage-classes](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L298-L309)
- [gistutil.c#gistPageRecyclable](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L885-L908)
- [lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L64-L104)
- [lockcmds.c#LockTableAclCheck](../../../../raw/postgres-17/src/backend/commands/lockcmds.c#L280-L299)
- [mvcc.sgml#read-committed](../../../../raw/postgres-17/doc/src/sgml/mvcc.sgml#L317-L333)
- [mvcc.sgml#repeatable-read](../../../../raw/postgres-17/doc/src/sgml/mvcc.sgml#L508-L513)
- [plpgsql.sgml#transaction-defaults](../../../../raw/postgres-17/doc/src/sgml/plpgsql.sgml#L3743-L3744)
- [plpgsql.sgml#trapping-errors](../../../../raw/postgres-17/doc/src/sgml/plpgsql.sgml#L2856-L2860)
- [relation.c#try_relation_open](../../../../raw/postgres-17/src/backend/access/common/relation.c#L88-L108)
- [spgist_private.h#fixed-blocks](../../../../raw/postgres-17/src/include/access/spgist_private.h#L47-L53)

## Navigation

- [v17/index](../../index.md)
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [Wiki Glossary (unverified)](../../../glossary.md) - the shared vocabulary this page links on first use.
- [Mandatory Non-B-Tree, Non-GIN Bloat Tests (unverified)](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md)
- [Mandatory GIN Bloat Tests (unverified)](../../common-concepts/mandatory-gin-bloat-tests.md)
- [Detecting Inflated Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17 (unverified)](non-btree-index-inflation-comment-baseline.md), the source of the fixtures
- [A COMMENT-Stored Baseline B-Tree Index-Maintenance Heuristic for PostgreSQL 12 Through 17 (unverified)](btree-comment-baseline-maintenance-heuristic.md), the B-tree counterpart
- [A COMMENT-Stored Baseline and Normalized Index Growth for Finding GIN Indexes That Need REINDEX CONCURRENTLY in PostgreSQL 17 (unverified)](gin-reindex-normalized-growth-comment-baseline.md)
- [Reading an Index's Entry Count From the Catalogs, for Every Index Type, in PostgreSQL 17 (unverified)](index-entry-count-from-catalogs.md)
- [How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 17 (unverified)](reindex-index-concurrently.md)
- [PostgreSQL 12 Codebase Navigation Guide (unverified)](../../../v12/codebase-navigation-guide.md)
- [Calibrating a COMMENT-Stored Bytes-per-Table-Tuple REINDEX Threshold for Every Non-B-Tree Index in PostgreSQL 12 (unverified)](../../../v12/questions/indexing/comment-stored-bytes-per-table-tuple-non-btree.md)
