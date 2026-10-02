---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [The current recommended statement](#the-current-recommended-statement)
  - [Reading the output](#reading-the-output)
  - [How the model uses PostgreSQL 17](#how-the-model-uses-postgresql-17)
  - [Deduplication eligibility](#deduplication-eligibility)
  - [Widths, expression statistics and compression](#widths-expression-statistics-and-compression)
  - [Page and posting geometry](#page-and-posting-geometry)
  - [Row counts and exclusions](#row-counts-and-exclusions)
  - [Validation probes](#validation-probes)
  - [Operational and verification limits](#operational-and-verification-limits)
  - [Plan review](#plan-review)
  - [What the ten plans changed](#what-the-ten-plans-changed)
  - [The deduplication gate, scored against the current statement](#the-deduplication-gate-scored-against-the-current-statement)
  - [The collation branch, measured with ICU](#the-collation-branch-measured-with-icu)
  - [The portable extended-statistics filter](#the-portable-extended-statistics-filter)
  - [Reproducing the measurements](#reproducing-the-measurements)
  - [What remains unimplemented](#what-remains-unimplemented)
  - [Mandatory test review](#mandatory-test-review)
  - [The maintenance, proved not defeated](#the-maintenance-proved-not-defeated)
  - [The mandatory suite, re-scored under the shared protocol](#the-mandatory-suite-re-scored-under-the-shared-protocol)
  - [What still needs to be tested](#what-still-needs-to-be-tested)
- [Measurement Script](#measurement-script)
  - [How to use the suite scripts](#how-to-use-the-suite-scripts)
  - [How to run the suite against the current statement](#how-to-run-the-suite-against-the-current-statement)
  - [The two suite scripts, and the rules they follow](#the-two-suite-scripts-and-the-rules-they-follow)
  - [The PostgreSQL 17 suite script](#the-postgresql-17-suite-script)
  - [The PostgreSQL 12 leg script](#the-postgresql-12-leg-script)
  - [Reading the results of a run](#reading-the-results-of-a-run)
  - [What the no-defeat re-run measured](#what-the-no-defeat-re-run-measured)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
  - [The mandatory suite and the current statement](#the-mandatory-suite-and-the-current-statement)
  - [What the re-port removed, and what that costs](#what-the-re-port-removed-and-what-that-costs)
  - [In-index compression of wide keys](#in-index-compression-of-wide-keys)
  - [Custom operator classes](#custom-operator-classes)
  - [Multicolumn key groups without extended statistics](#multicolumn-key-groups-without-extended-statistics)
  - [Partial-index populations and zero counts](#partial-index-populations-and-zero-counts)
  - [Fixture verdicts that depend on the ANALYZE sample](#fixture-verdicts-that-depend-on-the-analyze-sample)
  - [Statistics publication and test ordering](#statistics-publication-and-test-ordering)
  - [Alert thresholds and rebuild savings](#alert-thresholds-and-rebuild-savings)
  - [Scoring column for the partial-index contract](#scoring-column-for-the-partial-index-contract)
  - [Cross-version execution of the revised statement](#cross-version-execution-of-the-revised-statement)
  - [Integer-truncated widths across an alignment boundary](#integer-truncated-widths-across-an-alignment-boundary)
  - [Fixture statements are marked disposable, not tagged](#fixture-statements-are-marked-disposable-not-tagged)
  - [The 12 leg's settings have no citable apply scope here](#the-12-legs-settings-have-no-citable-apply-scope-here)
  - [What the no-defeat proofs leave open](#what-the-no-defeat-proofs-leave-open)
  - [Untested configurations](#untested-configurations)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 17: test the SQL from the PostgreSQL 12 question "Measuring B-Tree Index Bloat With Core SQL Only in PostgreSQL 12 (unverified)" on PostgreSQL 17 and compare whether it measures bloat with the same accuracy as in version 12.

Follow-up prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, for the question "Testing the PostgreSQL 12
> Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)", review all the
> plans to fix the open questions.

The original read `follow agents.md, in postgresql 17 , for question:  Testing
the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified) ,
review all the plans to fix the open questions`: `agents.md` for AGENTS.md,
lowercase `postgresql`, a space before two commas, a double space after the
colon, and no sentence capitalisation or terminal period. The review is filed
under [Plan review](#plan-review).

Third prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, for the question "Testing the PostgreSQL 12
> Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)", implement the
> proposed fixes for the open questions and run all tests.

The original read `follow agents.md, in postgresql 17, on question:  Testing the
PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified) ,
implement the proposal fixes for openquestions , run all tests`: `agents.md` for
AGENTS.md, lowercase `postgresql`, `on question:` with a double space, a space
before a comma, `openquestions` for "open questions", `the proposal fixes` for
"the proposed fixes", and no sentence capitalisation or terminal period. The
asker chose to implement all ten plans, to build a server and run the core
regression suite, and to delete the sandbox after filing. What that work changed
in the statement is filed under
[What the ten plans changed](#what-the-ten-plans-changed); the two sections that
reported its measurements, `Measured acceptance results` and
`Calibration by insertion pattern`, were removed on 2026-09-14 with the
page-local fixtures behind them.

Fourth prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, for the question "Testing the PostgreSQL 12
> Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)", review all the
> mandatory tests, and review what still needs to be tested and how.

The original read `follow agents.md, in postgresql 17, for question: # Testing
the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified) ,
review all mandatory tests and review what needs and how to be tested.`:
`agents.md` for AGENTS.md, lowercase `postgresql`, a stray `#` before the title,
a space before a comma, and "what needs and how to be tested" for "what still
needs to be tested and how". The asker chose to read "the mandatory tests" as
the whole numbered suite this page filed and later removed — tests 1-17, tests
18-91, fixtures 92-112, test 113 and fixtures 114-121 — together with the
2026-09-08 acceptance fixtures and the engine regression runs, and chose a
review with a runnable protocol rather than a server run. The review is filed
under [Mandatory test review](#mandatory-test-review),
[What still needs to be tested](#what-still-needs-to-be-tested) and
[How to run the suite against the current statement](#how-to-run-the-suite-against-the-current-statement);
its `Expected verdicts under the current statement` section was removed on
2026-09-14, because most of the fixtures it predicted no longer exist and the
prediction now lives in each script's own `want_stage` column.

Fifth prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, review the question "Testing the
> PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17".

The original read `follow agents.md, in postgresql 17, review question: Testing
the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)`:
`agents.md` for AGENTS.md, lowercase `postgresql`, `review question:` without an
article, and no sentence capitalisation or terminal period. The `(unverified)`
suffix is this repository's title hint for an unverified page, not part of the
page title, so the restated prompt drops it. The asker chose a full claim-level
re-verification against the pin, a server build with measurement, and repair in
place. Its surviving results are filed under
[The deduplication gate, scored against the current statement](#the-deduplication-gate-scored-against-the-current-statement)
and [The collation branch, measured with ICU](#the-collation-branch-measured-with-icu),
both re-measured since; its `Re-verified on a rebuilt server` section went on
2026-09-14 with the page-local fixtures it re-verified.

Sixth prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, for the question "Testing the PostgreSQL 12
> Core-SQL B-Tree Bloat Method on PostgreSQL 17", add a section with two
> scripts, one for version 17 and one for version 12, holding all the tests, so
> that the section can be reused during reviews and improvements of the
> statement. Use Bash and SQL only.

The original read `follow agents.md, in postgresql 17,  for question: Testing
the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified) ,
add to the question a section with two scripts for version 17 and version 12
with all the tests so it can be reused during reviews and improvements of the
statement. use bash and sql only.`: `agents.md` for AGENTS.md, lowercase
`postgresql`, a double space after the first comma, `for question:` without an
article, a space before a comma, the `(unverified)` title hint treated as part
of the title, an unclear "it" for the section, and `bash and sql` for Bash and
SQL. The asker chose to build and run both legs, to cover every test family the
page names, and to keep the scripts in this page rather than in a second file.
The work is filed under
[The two suite scripts, and the rules they follow](#the-two-suite-scripts-and-the-rules-they-follow),
[The PostgreSQL 17 suite script](#the-postgresql-17-suite-script),
[The PostgreSQL 12 leg script](#the-postgresql-12-leg-script) and, for the
numbers, whichever run report is current; that pass's own report,
`What the two scripts measured on 2026-09-09`, was removed on 2026-09-14 with
the fixture set it scored.

Seventh prompt, corrected and restated with the asker's agreement:

> Also add to the section information on how to understand the results of
> running the scripts.

The original read `add to section also information on how to understand the
results of the script execution.`: no article before `section`, no sentence
capitalisation, and `also` placed mid-sentence. The asker chose a reader's
guide rather than a per-stage reference with example output. It is filed under
[Reading the results of a run](#reading-the-results-of-a-run).

Eighth prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, for the question "Testing the PostgreSQL 12
> Core-SQL B-Tree Bloat Method on PostgreSQL 17", review the measurement script
> section.

The original read `follow agents.md, in postgresql 17,  for question: Testing
the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified) ,
review the measurement script section`: `agents.md` for AGENTS.md, lowercase
`postgresql`, a double space after the first comma, `for question:` without an
article, a space before the comma after the title, the `(unverified)` title
hint treated as part of the title, and no sentence capitalisation or terminal
period. The asker chose a **read-only audit** with no server run, a
**restructure of the page to comply** with `MANDATORY Measurement Script`, and
**repair in place** for what the audit found. The review is filed under
[Measurement Script](#measurement-script), whose usage information is under
[How to use the suite scripts](#how-to-use-the-suite-scripts). Its findings
section, `Measurement-script section review`, was removed on 2026-09-14; the
repairs it made are in the filed script text and its comments.

Ninth prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, review the question "Testing the
> PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17", and propose a
> fix for the failed cross-version execution test: the exact filed statement is
> refused on the pinned 12.2 server with
> `ERROR: column se.inherited does not exist` at
> `LINE 116: AND se.inherited = false`.

The original read `follow agents.md, in postgresql 17,  review question: Testing
the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified) ,
propose a fix for :  Not a pass — PostgreSQL 12.2 / The cross-version execution
test fails outright / The exact filed statement is refused on the pinned 12.2
server:`: `agents.md` for AGENTS.md, lowercase `postgresql`, a double space
after the first comma and after `for :`, a space before the comma after the
title and before that colon, `review question:` without an article, the
`(unverified)` title hint treated as part of the title, the quoted review
pasted as three fragments, and no sentence capitalisation or terminal period.
The asker chose the single-portable-text fix over keeping the filed text beside
a documented 12-only variant, and chose to implement it and re-run the affected
stages rather than only propose it. The work is filed under
[The portable extended-statistics filter](#the-portable-extended-statistics-filter),
re-measured since; that pass's own report,
`What the 2026-09-10 targeted re-run measured`, was removed on 2026-09-14.

Tenth prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, review the question "Testing the
> PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17".

The original read `follow agents.md, in postgresql 17, review  question: #
Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
(unverified)`: `agents.md` for AGENTS.md, lowercase `postgresql`, a double
space after `review`, `review question:` without an article, a stray `#`
before the title, the `(unverified)` title hint treated as part of the title,
and no sentence capitalisation or terminal period. The asker chose a
**targeted script run** over a claim-by-claim citation pass: fix the known
script defects, re-run the stages the 2026-09-10 pass had not re-run under the
repaired script text, build and check the 12 leg so that its full runtime is
measured, and **repair in place**. The repaired `stop` stage is in the filed
script text of both legs; its two sections, `The stop stage, repaired` and
`What the 2026-09-10 full re-run measured on Darwin arm64`, were removed on
2026-09-14 with the Darwin numbers they carried.

Eleventh prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, for the question "Testing the
> PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17", review the
> last changes to the script.

The original read `follow agents.md, in postgresql 17, for  question: #
Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
(unverified), review the last changes to the script`: `agents.md` for
AGENTS.md, lowercase `postgresql`, a double space after `for`, `for
question:` without an article, a stray `#` before the title, the
`(unverified)` title hint treated as part of the title, and no sentence
capitalisation. The asker chose **review only**: file the findings and the
proposed repairs, and leave the script text unchanged. Its two sections,
`The server-error check, reviewed` and
`What the server-error check review left open`, were removed on 2026-09-14; the
check itself, and what it can and cannot see, are documented in the script
text where it is defined.

Twelfth prompt, corrected and restated with the asker's agreement:

> Repair the defects, but do not re-run anything.

The original read `repair but don't rerun anything.`: no sentence
capitalisation, `rerun` for re-run, and the object of `repair` left implicit.
The six repairs are in the filed script text of both legs, and the gap they
left - filed numbers that predated the script text - is closed by the
2026-09-14 run, which is the first to score the current text of both scripts.
The section that recorded them, `The server-error check, repaired`, was removed
with the other run reports.

Thirteenth prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, for the question "Testing the PostgreSQL
> 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17", replace this page's own
> mandatory-test definition with the tests defined on the common concept page
> "Mandatory B-Tree Bloat Tests", and keep the link to that concept page.

The original read `follow agents.md, in postgresql 17, for question: # Testing
the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified),
replace the mandatory test by tests on common-concept: # Mandatory B-Tree Bloat
Tests (unverified), keep the link with the common concept.`: `agents.md` for
AGENTS.md, lowercase `postgresql`, `for question:` without an article, a stray
`#` before each of the two titles, the `(unverified)` title hint treated as part
of both titles, `the mandatory test` for the whole suite of tests, `replace ...
by` for `replace ... with`, `on common-concept:` for "on the common concept
page", and `keep the link with the common concept` for "keep the link to that
concept page". The asker scoped the prose replacement to
[Mandatory test review](#mandatory-test-review) alone, chose to restate this
page's outstanding obligations in the shared suite's families, phases and
verdict bands while labelling the earlier results as the page's older one-shot
form, and chose to **run both legs** and re-score against the shared protocol.
The work is filed under [Mandatory test review](#mandatory-test-review) and
[The mandatory suite, re-scored under the shared protocol](#the-mandatory-suite-re-scored-under-the-shared-protocol).

Fourteenth prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, review the question "Testing the
> PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17", update the tests
> for the changes on the common concept page "Mandatory B-Tree Bloat Tests", and
> update or remove every test that does not follow it.

The original read `follow agents.md, in postgresql 17, review question: #
Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
(unverified), update tests based on the changes from common-concept, update or
remove all tests that aren't following # Mandatory B-Tree Bloat Tests
(unverified)`: `agents.md` for AGENTS.md, lowercase `postgresql`, a stray `#`
before each of the two titles, the `(unverified)` title hint treated as part of
both titles, `common-concept` for "the common concept page", the contraction
`aren't`, and no terminal period. The asker then settled the scope in four
answers: **retire and maintain** in the scripts, so the numbers that page
retired are dropped and every remaining churn ends on `VACUUM ANALYZE`; **both
legs re-run end to end** from their pins; **remove every page-local fixture**,
which took the geometry, calibration and acceptance stages; and **delete the
claims** those fixtures backed rather than keep them as history. The work is
filed under [Mandatory test review](#mandatory-test-review) and
[The mandatory suite, re-scored under the shared protocol](#the-mandatory-suite-re-scored-under-the-shared-protocol);
its own run report was superseded the same day by the fifteenth prompt's run,
under [What the no-defeat re-run measured](#what-the-no-defeat-re-run-measured).

Fifteenth prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, review the question "Testing the
> PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17", and remove the
> size filter from the recommended statement.

The original read `follow agents.md, in postgresql 17, review question: #
Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17
(unverified)` and then, after a line break, `, remove size filter from the
recommended statement`: `agents.md` for AGENTS.md, lowercase `postgresql`,
`review question:` without an article, a stray `#` before the title, the
`(unverified)` title hint treated as part of the title, a line break and a
comma splicing the second request onto the end of the title, `remove size
filter` without the article, and no sentence capitalisation or terminal
period. The asker then settled the scope in three answers: remove **both**
report-side cutoffs, the `actual_bytes > 1024 * 1024` predicate and the
`LIMIT 20`, so `NOT suppress_row` is the statement's only remaining report
filter; **keep** the probe generator's own `pg_relation_size` filter and record
that the two no longer match; and **re-run both legs end to end** from their
pins. The work is filed under
[The current recommended statement](#the-current-recommended-statement),
[Reading the output](#reading-the-output),
[The mandatory suite, re-scored under the shared protocol](#the-mandatory-suite-re-scored-under-the-shared-protocol)
and [What the no-defeat re-run measured](#what-the-no-defeat-re-run-measured).

Sixteenth prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, review the question "Testing the
> PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17".

The original read `follow agents.md, in postgresql 17, review :
btree-index-bloat-core-sql-only.md`: `agents.md` for AGENTS.md, lowercase
`postgresql`, a space before the colon, a double space after it, the file name
in place of the page title, and no sentence capitalisation or terminal period.
The asker then settled the scope in three answers: **everything** - re-read
every citation against the pin, bring both scripts onto the concept page's
rule `### The maintenance must not be defeated`, and re-run both legs end to
end; and **repair in place** for whatever the review found. The citation pass
is under [Context Reviewed](#context-reviewed), the rule work under
[The maintenance, proved not defeated](#the-maintenance-proved-not-defeated),
and the run under
[What the no-defeat re-run measured](#what-the-no-defeat-re-run-measured).

## Answer

**Every maintenance statement in both legs is now proved not to have been
defeated, and that is what this review was for.** The page was last run on
2026-09-14; the concept page it is scored against gained
`### The maintenance must not be defeated` on 2026-09-15, and this page had
never been checked against it. Both scripts were repaired rather than
re-designed: each maintenance statement is now one `VACUUM (VERBOSE, ANALYZE)`
bracketed by `maint_begin()` and `maint_end()`, issued from a session whose
four settable timeouts are `0` - the four an autovacuum worker forces on itself
for exactly this reason - and the run records, per table, that the statement
completed, its own `dead but not yet removable` count, the horizon holders at
that moment, and the page classes it left. On 17.11 that is **65 statements in
`suite`, 2 in `gate` and 1 in `xstat`, all 68 completed, every one at
`dead but not yet removable` 0 with `n_dead_tup` 0 afterwards, 76 of 76 horizon
probes entirely clean, 0 skip or cancellation lines, and one timeout set of
four zeros**; on 12.2 it is **9 statements, 9 completed, 11 of 11 probes clean
and three zeros**, because that server has no `transaction_timeout`. The churn
stage now **dies rather than score** a fixture whose maintenance was defeated.
[The maintenance, proved not defeated](#the-maintenance-proved-not-defeated),
[vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L659-L663),
[autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470).

**Nothing was found defeated, so the re-run confirms the readings rather than
replacing them.** All 717 citations on the page were re-read against the pin -
238 distinct ranges over 88 files - and every one is in bounds and supports its
claim; the estimator text is untouched by this pass and all three SHA-256
baselines matched. Both legs were then built from their pins and run end to
end: 17.11 passed `make check` **225 of 225** plus 8, 1 and 3 for
`pageinspect`, `pgstattuple` and `amcheck`; 12.2 passed **192 of 192** plus 5,
1 and 2.
[What the no-defeat re-run measured](#what-the-no-defeat-re-run-measured).

**The score moves by one fixture, and the reason is the `ANALYZE` sample rather
than the model.** The scored population is unchanged - 126 fixtures on 17.11,
25 in the deduplication gate and 101 numbered, and 13 on 12.2 - and under the
four verdict bands of
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
17.11 reads **97 `PASS`, 4 `CRITICAL FALSE POSITIVE`, 0 `FALSE POSITIVE` and 25
`FALSE NEGATIVE`**, against 96/4/0/26 on 2026-09-14. The row that moved is
`p41`, a two-column key correlated in the table and independent only in the
subset: whether the deduplication-credit term withholds it turns on a sampled
`n_distinct`, and on this run the sample left it printed, decided `rebuild`,
and repaid 75.2 % against a reading of 74.4 %. Both of this pass's full 17 runs
read it the same way, so the score is stable at 97/4/0/25 under the current
script text. 12.2 is unchanged at **11 `PASS`, 0 false positives of either
severity and 2 `FALSE NEGATIVE`**, because **no fixture on that leg is under
1 MB** - the smallest is 276 blocks.
[The mandatory suite, re-scored under the shared protocol](#the-mandatory-suite-re-scored-under-the-shared-protocol),
[Fixture verdicts that depend on the ANALYZE sample](#fixture-verdicts-that-depend-on-the-analyze-sample).

**The report shape reproduces the 2026-09-14 filing to the row.** `NOT
suppress_row` is still the only report filter: the
`actual_bytes > 1024 * 1024` predicate and the `LIMIT 20` came out on
2026-09-14. On the settled 17.11 fixture database the filed text prints **68
rows where the superseded text prints 20**, and **45 of those 68 are 1 MB or
smaller**, both identical to the previous run; on 12.2 it prints **19 rows, 6
of them 1 MB or smaller**. Keeping that identity took a repair of its own: the
three tables the proofs need carry no primary key, because the estimator's
candidate set is every B-tree index outside the system schemas, and a harness
index in `public` shows up in the report the run is scoring - it did, at 70
rows, until the two indexes came out.
[The current recommended statement](#the-current-recommended-statement),
[What the no-defeat re-run measured](#what-the-no-defeat-re-run-measured).

**The two threshold losses are unchanged, and they are still this page's
clearest defect.** `p31` at 192 KiB and `f91` at 296 KiB are printed and still
declined, because their floor readings are `-233.3` and `-248.6` - the model
predicts a *larger* rebuild - while the oracle gave back 79.2 % and 89.2 %. The
25 misses are **22 rows an exclusion term withheld** (mean reclaim 83.9 %),
**2 lost to the threshold** (84.2 %) and **1 carrying a caveat** the reading
rule refuses to promote (100.0 %). `expected_stage`, recomputed from the
internals rather than from the reported percentage, still agrees with the
decision on all 101 fixtures. The four rows a reader would have acted on and
got nothing back are unchanged: `f84` at 94.2 %, `f85` at 70.7 %, `i103` at
84.1 % and `x109` at 62.5 %, each against a measured 0.0 %.
[Where the false negatives were lost](#where-the-false-negatives-were-lost).

**The fixture set is the one the 2026-09-14 re-port left.** Eleven numbered
fixtures left the 17 leg - test 11's three `deduplicate_items = off` gate legs,
38, 65, 67, 69, 106, 117, 121's three recipes and legs 113a and 113c - and
three left the 12 leg, because the concept page retired those numbers as
explicit deduplication controls or as withheld-maintenance shapes. Ten recipes
that keep churn of their own end on the maintenance statement, which is that
page's maintenance assumption: 64, 66, 92, 93, 94, 95, 98, 115, 118 and 119.
Rule 3's census reproduced its effect on this run too - it analyzed **2 of 86
tables**, `f85t` and `x108t`, the only two that no churn touched and that were
past the threshold, and found **84 tables at zero modified rows**. On 12.2 the
census now analyzes **0 of 9** where it analyzed 2, and that is the repair
rather than a drift: the bracketed maintenance runs in its own session after
the drain's has exited, so the drain's counts reach the statistics entry
*before* the `ANALYZE` half resets them, which is the publication order the
concept page's rule 3 requires.
[Mandatory test review](#mandatory-test-review),
[pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L331-L338).

**The page-local fixtures are gone too, and so are the claims they backed.**
The geometry cells, the calibration ladder by insertion pattern and the whole
acceptance stage - fresh sorted builds, the three deterministic defect
fixtures, the compression pair, the posting-tail classes, the probe fixtures and
the publication barrier - built shapes no mandatory test defines. They were
removed at the asker's direction together with the sections that reported their
numbers, so this page no longer states a measured `0 bytes` on ten fresh
builds, 78 of 78 geometry cells, a seven-pattern calibration, a `-2625.6 %`
compression reading or a `-60.1 %` mixed-width reading. What the statement's
remaining error looks like is now whatever the suite measures, on the
`wasted_space_pct_floor` column the harness scores: worst over-estimate
`+94.2` on `f84`, worst under-estimate `-3332.4` on `f88`, and 57 of 101
fixtures within one point of the oracle.
[Reproducing the measurements](#reproducing-the-measurements),
[What remains unimplemented](#what-remains-unimplemented).

**The cross-version answer is still yes on the parse and no on the credit.**
The exact filed text executes on the pinned 12.2 server unmodified, with the 12
leg's transformer reporting `transform_edits=0`, because the `extstat` filter
reads the inherited flag through `row_to_json(se) ->> 'inherited'` rather than
naming a column that server does not have; the text filed before that fix is
still refused there with `column se.inherited does not exist` at line 116. On
17.11 the change stays inert: `EXCEPT` in both directions over every projected
column returns 0 rows in all three fixture databases, 139 rows read - three
more than the 136 of 2026-09-14, because the proof tables the rule needs took
the `xstat` database's index count from 4 to 7. All 13
fixtures on 12.2 read `equalimage = ineligible` and none is credited, which is
the support-function-4 feature gate the concept page names rather than a
defect: that server registers B-tree support procedures 1, 2 and 3 only, and
refuses `WITH (deduplicate_items = off)`.
[The portable extended-statistics filter](#the-portable-extended-statistics-filter),
[system_views.sql#pg_stats_ext-inherited](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L290),
[pg_proc.dat#row_to_json](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L8975-L8977),
[jsonfuncs.c#json_object_field_text](../../../../raw/postgres-17/src/backend/utils/adt/jsonfuncs.c#L881-L895).

Treat the output as candidate information all the same, and the wider report as
more of it rather than better of it. The model reads estimated row counts,
widths and NULL fractions out of the catalogs, so it models an index it cannot
see; the four critical false positives above, the 35 withheld rows, the two
threshold losses at `-233.3` and `-248.6` and the gate's two under-credits are
what that costs on the fixtures the suite defines. See
[Open Questions](#open-questions).

Both servers were built out of tree from their pins and checked before a
fixture existed: 17.11 passed `make check` **225 of 225** plus 8, 1 and 3 for
`pageinspect`, `pgstattuple` and `amcheck`; 12.2 passed **192 of 192** plus 5,
1 and 2. `Linux x86_64`, `max_data_alignment` 8, `database_block_size` 8192,
`autovacuum = off`, `fsync = off`. **0 unexpected server errors on either
leg**, with each leg's deliberate errors seen exactly once.
[regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59),
[installation.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L515-L522).

### The current recommended statement

This is the single operational estimator on this page. It replaces the statement
filed before 2026-09-08; that text is superseded, and it survives only as the
`old` column of the scoring pass and as the other side of the `EXCEPT`
attribution. The tag moves from
`wiki_btree_wasted_space_sweep_12_17` to `wiki_btree_wasted_space_sweep_r2` so a
log or `pg_stat_statements` row identifies which model produced a reading.

**Both report-side cutoffs came out on 2026-09-14**: the
`actual_bytes > 1024 * 1024` predicate and the `LIMIT 20`. `NOT suppress_row`
is the only report filter left, so the statement prints every candidate index
whose model it is willing to stand behind, and nothing is withheld for being
small or for ranking low. What that changed, measured on both legs, is under
[What the no-defeat re-run measured](#what-the-no-defeat-re-run-measured); the
model, the caveats and the exclusion terms are untouched. The companion probe
generator under [Validation probes](#validation-probes) kept its own
`pg_relation_size` filter, so the two texts no longer cover the same
candidates; see [Open Questions](#partial-index-populations-and-zero-counts).

Run the two timeout settings with the query in a dedicated session. They set
`statement_timeout` to 30 seconds and `lock_timeout` to 2 seconds. Both are
`PGC_USERSET`: they apply at session/transaction scope without a reload or restart.
The supplied `SET` commands affect the session.
[guc_tables.c#statement_timeout-and-lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2631).

The catalog and function definitions used by the block are mapped in
[Evidence Map](#evidence-map). The sections after it explain the model and its
limits. Every claim about the statement's behaviour below was measured on an
isolated 17.11 server built from the pin; see
[Reproducing the measurements](#reproducing-the-measurements).

```sql
SET /* wiki_btree_wasted_space_statement_timeout */ statement_timeout = '30s';
SET /* wiki_btree_wasted_space_lock_timeout */ lock_timeout = '2s';


WITH RECURSIVE
env AS (
    -- Server constants and table-level auto-analyze defaults.
    SELECT /* wiki_btree_wasted_space_sweep_r2 */
           current_setting('block_size')::int                         AS bs,
           current_setting('server_version_num')::int                 AS server_version_num,
           current_setting('autovacuum_analyze_threshold')::int       AS anl_threshold,
           current_setting('autovacuum_analyze_scale_factor')::float8 AS anl_scale_factor
),
idx AS (
    -- Candidate indexes, physical fork sizes, reloptions and row-count inputs.
    -- Negative reltuples stops the model; zero is accepted without validation.
    SELECT c.oid AS idxoid, n.nspname AS schemaname, t.relname AS tablename,
           c.relname AS indexname, t.oid AS tbloid,
           x.indkey, x.indclass, x.indcollation, x.indisunique, x.indnkeyatts,
           t.relrowsecurity                             AS tbl_rls,
           (x.indpred IS NOT NULL)                      AS is_partial,
           (x.indexprs IS NOT NULL)                     AS has_expressions,
           (x.indnatts = x.indnkeyatts)                 AS keys_only,
           e.bs, e.server_version_num, z.actual_bytes, z.fsm_bytes,
           o.fillfactor, o.dedup_on,
           c.reltuples::numeric                         AS idx_reltuples,
           coalesce(s.n_live_tup, 0)::numeric           AS tbl_live_tup,
           coalesce(s.n_dead_tup, 0)::numeric           AS tbl_dead_tup,
           coalesce(s.n_mod_since_analyze, 0)::numeric  AS tbl_mod_since_analyze,
           (o.anl_threshold
            + o.anl_scale_factor * greatest(t.reltuples, 0))::numeric
                                                        AS tbl_autoanalyze_threshold,
           greatest(s.last_analyze, s.last_autoanalyze) AS last_analyze,
           greatest(s.last_vacuum, s.last_autovacuum)   AS last_vacuum,
           CASE
             WHEN c.reltuples < 0 THEN NULL
             WHEN x.indpred IS NOT NULL THEN c.reltuples::numeric
             ELSE least(c.reltuples::numeric,
                        coalesce(nullif(s.n_live_tup, 0), c.reltuples)::numeric)
           END                                          AS live_rows
      FROM pg_class c
      JOIN pg_index x     ON x.indexrelid = c.oid
      JOIN pg_class t     ON t.oid = x.indrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_am am       ON am.oid = c.relam
      LEFT JOIN pg_stat_all_tables s ON s.relid = t.oid
      CROSS JOIN env e
      CROSS JOIN LATERAL (
            SELECT pg_relation_size(c.oid)        AS actual_bytes,
                   pg_relation_size(c.oid, 'fsm') AS fsm_bytes) z
      CROSS JOIN LATERAL (
            SELECT coalesce((SELECT option_value::int FROM pg_options_to_table(c.reloptions)
                              WHERE option_name = 'fillfactor'), 90)          AS fillfactor,
                   coalesce((SELECT option_value::bool FROM pg_options_to_table(c.reloptions)
                              WHERE option_name = 'deduplicate_items'), true) AS dedup_on,
                   coalesce((SELECT option_value::int FROM pg_options_to_table(t.reloptions)
                              WHERE option_name = 'autovacuum_analyze_threshold'
                                AND option_value::int >= 0),
                            e.anl_threshold)                                  AS anl_threshold,
                   coalesce((SELECT option_value::float8 FROM pg_options_to_table(t.reloptions)
                              WHERE option_name = 'autovacuum_analyze_scale_factor'
                                AND option_value::float8 >= 0),
                            e.anl_scale_factor)                               AS anl_scale_factor) o
     WHERE am.amname = 'btree' AND c.relkind = 'i' AND x.indisvalid
       AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
),
opc AS (
    -- One row per key attribute: its equal-image support function and collation.
    SELECT i.idxoid, k AS keyno,
           ap.amproc IS NOT NULL                          AS has_proc,
           (pl.lanname = 'internal'
            AND pr.prosrc = 'btequalimage')               AS proc_always,
           (pl.lanname = 'internal'
            AND pr.prosrc = 'btvarstrequalimage')         AS proc_varstr,
           coalesce(cl.collisdeterministic, true)         AS collation_ok
      FROM idx i
      CROSS JOIN LATERAL generate_subscripts(i.indclass, 1) k
      JOIN pg_opclass op ON op.oid = i.indclass[k]
      LEFT JOIN pg_amproc ap ON ap.amprocfamily = op.opcfamily
                            AND ap.amproclefttype = op.opcintype
                            AND ap.amprocrighttype = op.opcintype
                            AND ap.amprocnum = 4
      LEFT JOIN pg_proc pr     ON pr.oid = ap.amproc
      LEFT JOIN pg_language pl ON pl.oid = pr.prolang
      LEFT JOIN pg_collation cl ON cl.oid = i.indcollation[k]
     WHERE k < i.indnkeyatts
),
gate AS (
    -- Three-state equal-image verdict: recognized, ineligible, or unknown.
    SELECT i.idxoid,
           CASE
             WHEN NOT i.keys_only                       THEN 'ineligible'
             WHEN bool_or(NOT o.has_proc)               THEN 'ineligible'
             WHEN bool_or(o.proc_varstr
                          AND NOT o.collation_ok)       THEN 'ineligible'
             WHEN bool_and(o.proc_always OR o.proc_varstr) THEN 'recognized'
             ELSE 'unknown'
           END AS equalimage_state
      FROM idx i
      JOIN opc o ON o.idxoid = i.idxoid
     GROUP BY i.idxoid, i.keys_only
),
keyatts AS (
    -- Match extended-statistics keys by the sorted table attribute numbers.
    SELECT i.idxoid,
           string_agg(i.indkey[k]::text, ', ' ORDER BY i.indkey[k]) AS ext_key,
           count(*)         AS nkeys,
           min(i.indkey[k]) AS min_attnum
      FROM idx i, generate_subscripts(i.indkey, 1) k
     WHERE k < i.indnkeyatts
     GROUP BY i.idxoid
),
extstat AS (
    -- Use the maximum visible non-inherited whole-key distinct estimate.
    -- The inherited flag is read through row_to_json() instead of being named
    -- as a column, so one text also parses where pg_stats_ext has no inherited
    -- column: there the key is absent, ->> returns NULL, and the coalesce
    -- admits the row, which is the only ANALYZE pass such a server records.
    SELECT k.idxoid, max(e.nd) AS ext_ndistinct
      FROM keyatts k
      JOIN idx i           ON i.idxoid = k.idxoid
      JOIN pg_stats_ext se ON se.schemaname = i.schemaname
                          AND se.tablename = i.tablename
                          AND coalesce((row_to_json(se) ->> 'inherited')::boolean,
                                       false) = false
      CROSS JOIN LATERAL (
            SELECT ((se.n_distinct::text)::json ->> k.ext_key)::numeric AS nd) e
     WHERE k.nkeys > 1 AND k.min_attnum > 0 AND e.nd > 0
     GROUP BY k.idxoid
),
cols AS (
    -- Index-expression statistics, table-column statistics, then defaults.
    -- Only the non-inherited ANALYZE pass is read, and an expression
    -- attribute's visibility is tested on the index, which owns its row.
    SELECT i.idxoid, a.attnum, a.attlen, a.attalign, a.attstorage,
           (i.indkey[a.attnum - 1] = 0)                          AS is_expression,
           -- index_form_tuple() compresses a varlena key wider than
           -- TOAST_INDEX_TARGET = MaxHeapTupleSize / 16 when its storage is
           -- extended or main; ANALYZE records the uncompressed width.
           (a.attlen < 0 AND a.attstorage IN ('x', 'm')
            AND w.raw_width > (i.bs - 32) / 16)                  AS compressible,
           -- ANALYZE records VARSIZE_ANY of the sampled datum. A stored column
           -- value is already short-headed, but an index expression is computed
           -- fresh with a four-byte header, and heap_compute_data_size() stores
           -- the converted short size, three bytes less, when it fits in 127.
           CASE WHEN a.attlen > 0 THEN a.attlen::numeric
                WHEN w.from_index AND w.raw_width BETWEEN 5 AND 130
                     THEN (w.raw_width - 3)::numeric
                ELSE w.raw_width::numeric END                    AS width,
           CASE WHEN a.attlen > 0    THEN false
                WHEN w.from_index    THEN w.raw_width <= 130
                ELSE w.raw_width <= 127 END                      AS short_form,
           coalesce(se.null_frac, st.null_frac, 0)::numeric      AS null_frac,
           coalesce(se.n_distinct, st.n_distinct, 0)::numeric    AS n_distinct,
           coalesce(se.most_common_freqs, st.most_common_freqs)  AS mcf,
           (se.attname IS NULL AND st.attname IS NULL)           AS no_stats_row,
           CASE WHEN i.indkey[a.attnum - 1] = 0
                THEN NOT coalesce(has_column_privilege(i.idxoid, a.attnum, 'SELECT'),
                                  false)
                ELSE (NOT coalesce(has_column_privilege(i.tbloid, ta.attnum, 'SELECT'),
                                   has_table_privilege(i.tbloid, 'SELECT'))
                      OR (i.tbl_rls AND row_security_active(i.tbloid)))
           END                                                   AS stats_hidden,
           coalesce(CASE WHEN i.indkey[a.attnum - 1] = 0 THEN a.attstattarget
                         ELSE ta.attstattarget END, -1) = 0      AS stats_disabled
      FROM idx i
      JOIN pg_attribute a ON a.attrelid = i.idxoid AND a.attnum > 0 AND NOT a.attisdropped
      LEFT JOIN pg_stats se ON se.schemaname = i.schemaname
                           AND se.tablename = i.indexname AND se.attname = a.attname
                           AND se.inherited = false
      LEFT JOIN pg_attribute ta ON ta.attrelid = i.tbloid
                               AND ta.attnum = i.indkey[a.attnum - 1]
      LEFT JOIN pg_stats st ON st.schemaname = i.schemaname
                           AND st.tablename = i.tablename AND st.attname = ta.attname
                           AND st.inherited = false
      CROSS JOIN LATERAL (
            SELECT se.attname IS NOT NULL                AS from_index,
                   coalesce(se.avg_width, st.avg_width, 32) AS raw_width) w
),
statvis AS (
    -- Classify each missing statistics row and flag variable-width INCLUDEs.
    SELECT c.idxoid,
           bool_or(c.no_stats_row AND NOT c.stats_hidden
                   AND NOT c.stats_disabled)          AS any_no_stats,
           bool_or(c.no_stats_row AND c.stats_hidden) AS any_stats_hidden,
           bool_or(c.no_stats_row
                   AND c.stats_disabled)              AS any_stats_disabled,
           bool_or(c.attnum > i.indnkeyatts AND c.attlen < 0)
                                                      AS any_varlena_include,
           bool_or(c.compressible)                    AS any_compressible
      FROM cols c
      JOIN idx i ON i.idxoid = c.idxoid
     GROUP BY c.idxoid
),
tuple AS (
    -- Approximate datum widths, joint NULL probability and distinct key groups.
    SELECT i.*,
           (SELECT sum((1 - c.null_frac) *
                       CASE WHEN c.short_form THEN c.width
                            ELSE ceil(c.width / al.a) * al.a END)
              FROM cols c
              CROSS JOIN LATERAL (SELECT CASE c.attalign WHEN 'c' THEN 1 WHEN 's' THEN 2
                                              WHEN 'i' THEN 4 ELSE 8 END AS a) al
             WHERE c.idxoid = i.idxoid)                          AS data_size,
           (SELECT 1 - coalesce(exp(sum(ln(greatest(1 - c.null_frac, 1e-9)))), 1)
              FROM cols c WHERE c.idxoid = i.idxoid)             AS p_null,
           CASE WHEN e.ext_ndistinct IS NOT NULL
                THEN least(e.ext_ndistinct, greatest(i.live_rows, 0))
                ELSE
           (SELECT least(round(exp(sum(ln(greatest(
                       CASE WHEN c.n_distinct > 0 THEN c.n_distinct
                            WHEN c.n_distinct < 0 AND NOT i.is_partial
                                 THEN (- c.n_distinct) * greatest(i.live_rows, 0)
                            ELSE (1 - c.null_frac) * greatest(i.live_rows, 0)
                       END
                       + CASE WHEN c.null_frac > 0 THEN 1 ELSE 0 END, 1))))),
                         greatest(i.live_rows, 0))
              FROM cols c
             WHERE c.idxoid = i.idxoid AND c.attnum <= i.indnkeyatts)
           END                                                   AS key_groups,
           (e.ext_ndistinct IS NOT NULL)                         AS ext_used,
           v.any_no_stats, v.any_stats_hidden, v.any_stats_disabled,
           v.any_varlena_include, v.any_compressible
      FROM idx i
      LEFT JOIN extstat e ON e.idxoid = i.idxoid
      LEFT JOIN statvis v ON v.idxoid = i.idxoid
),
page AS (
    -- Page geometry: soft fillfactor limit, hard-fit reservation, posting cap.
    SELECT t.*, g.equalimage_state,
           s.itupsz, s.slot, f.leaf_cap, f.int_cap, f.leaf_bytes, f.dedup_applies,
           f.groups_est, f.maxposting, f.hikey_extra, p.nmax
      FROM tuple t
      JOIN gate g ON g.idxoid = t.idxoid
      CROSS JOIN LATERAL (
            SELECT ceil((8 + 8 * t.p_null + t.data_size) / 8) * 8              AS itupsz,
                   ceil((8 + 8 * t.p_null + t.data_size) / 8) * 8 + 4          AS slot) s
      CROSS JOIN LATERAL (
            SELECT greatest(least(
                     floor((t.bs - 48 - floor(t.bs * (100 - t.fillfactor) / 100)) / s.slot),
                     floor((t.bs - 48 - 8 - s.itupsz) / s.slot)), 1)           AS leaf_cap,
                   greatest(least(
                     1 + floor((t.bs - 48 - floor(t.bs * 30 / 100) - 12) / s.slot),
                     1 + floor((t.bs - 48 - 12 - s.itupsz) / s.slot)), 2)      AS int_cap,
                   (t.bs - 48 - floor(t.bs * (100 - t.fillfactor) / 100))      AS leaf_bytes,
                   (t.bs - 48 - 8)                                             AS hikey_extra,
                   (NOT t.indisunique AND t.dedup_on
                        AND g.equalimage_state = 'recognized')                 AS dedup_applies,
                   least(greatest(t.live_rows, 0), greatest(t.key_groups, 1))  AS groups_est,
                   floor(floor(t.bs * 10 / 100) / 8) * 8 - 4                   AS maxposting) f
      CROSS JOIN LATERAL (
            SELECT greatest(floor((floor(f.maxposting / 8) * 8 - s.itupsz) / 6), 1)
                                                                               AS nmax) p
),
kstat AS (
    -- Use a NULL/MCV mixture only for an eligible single-key non-partial index.
    SELECT p.idxoid,
           CASE WHEN p.is_partial THEN 0 ELSE c.null_frac END AS null_frac,
           CASE WHEN p.is_partial THEN '{}'::real[]
                ELSE coalesce(c.mcf, '{}'::real[]) END        AS mcf
      FROM page p
      JOIN cols c ON c.idxoid = p.idxoid AND c.attnum = 1
     WHERE p.indnkeyatts = 1 AND p.dedup_applies AND p.live_rows > 0
),
gclass AS (
    -- NULL run, each most-common value, remaining values, or one multicolumn class.
    SELECT p.idxoid, greatest(p.live_rows, 0) * k.null_frac AS class_rows,
           1::numeric AS class_groups
      FROM page p JOIN kstat k ON k.idxoid = p.idxoid
     WHERE k.null_frac > 0
    UNION ALL
    SELECT p.idxoid, greatest(p.live_rows, 0) * f, 1::numeric
      FROM page p JOIN kstat k ON k.idxoid = p.idxoid
      CROSS JOIN LATERAL unnest(k.mcf) f
    UNION ALL
    SELECT p.idxoid,
           greatest(greatest(p.live_rows, 0)
                    * (1 - k.null_frac
                         - coalesce((SELECT sum(f) FROM unnest(k.mcf) f), 0)), 0),
           greatest(p.groups_est
                    - CASE WHEN k.null_frac > 0 THEN 1 ELSE 0 END
                    - coalesce(array_length(k.mcf, 1), 0), 1)
      FROM page p JOIN kstat k ON k.idxoid = p.idxoid
    UNION ALL
    SELECT p.idxoid, greatest(p.live_rows, 0), p.groups_est
      FROM page p
     WHERE p.indnkeyatts > 1 AND p.dedup_applies AND p.live_rows > 0
),
classfit AS (
    -- Split each class into whole posting tuples and one tail tuple per group.
    SELECT g.idxoid, g.class_rows, g.class_groups, p.itupsz, p.slot,
           p.leaf_bytes, p.hikey_extra, p.nmax,
           u.rows_per_group,
           floor(u.rows_per_group / p.nmax)                        AS full_per_group,
           u.rows_per_group - p.nmax * floor(u.rows_per_group / p.nmax)
                                                                   AS tail_rows
      FROM gclass g
      JOIN page p ON p.idxoid = g.idxoid
      CROSS JOIN LATERAL (
            SELECT g.class_rows / greatest(g.class_groups, 1) AS rows_per_group) u
     WHERE g.class_rows > 0
),
classsize AS (
    -- Price a full posting tuple and the tail tuple separately. The build
    -- flushes one posting tuple per capacity and one shorter tail per group.
    SELECT c.*,
           CASE WHEN c.nmax > 1 THEN ceil((c.itupsz + c.nmax * 6) / 8) * 8
                ELSE c.itupsz END                                  AS full_size,
           -- A one-TID group is a plain tuple, a longer one a posting tuple,
           -- so interpolate between the integer TID counts that bracket the
           -- class's average tail rather than rounding it.
           (1 - (c.tail_rows - floor(c.tail_rows)))
             * CASE WHEN floor(c.tail_rows) > 1
                    THEN ceil((c.itupsz + floor(c.tail_rows) * 6) / 8) * 8
                    ELSE c.itupsz END
           + (c.tail_rows - floor(c.tail_rows))
             * CASE WHEN ceil(c.tail_rows) > 1
                    THEN ceil((c.itupsz + ceil(c.tail_rows) * 6) / 8) * 8
                    ELSE c.itupsz END                              AS tail_size,
           c.full_per_group
             + CASE WHEN c.tail_rows > 0 THEN 1 ELSE 0 END         AS tuples_per_group
      FROM classfit c
),
classpages AS (
    -- Convert tuple counts to leaf pages. Pages mix full and tail tuples, so
    -- the capacity uses the class's mean tuple size and mean posting credit,
    -- while the hard-fit reservation uses its largest tuple.
    SELECT c.idxoid,
           sum(c.class_groups * c.tuples_per_group / f.cap)        AS leaf_frac,
           sum(c.class_groups * c.tuples_per_group)                AS tuples_total,
           max(CASE WHEN c.full_per_group > 0 THEN c.nmax
                    ELSE greatest(c.tail_rows, 1) END)             AS max_tids
      FROM classsize c
      CROSS JOIN LATERAL (
            SELECT (c.full_per_group * c.full_size
                    + CASE WHEN c.tail_rows > 0 THEN c.tail_size ELSE 0 END)
                     / c.tuples_per_group                          AS mean_size,
                   (c.full_per_group * (c.full_size - c.itupsz)
                    + CASE WHEN c.tail_rows > 0
                           THEN c.tail_size - c.itupsz ELSE 0 END)
                     / c.tuples_per_group                          AS mean_credit) m
      CROSS JOIN LATERAL (
            SELECT greatest(least(
                     floor((c.leaf_bytes + m.mean_credit) / (m.mean_size + 4)),
                     floor((c.hikey_extra - m.mean_size) / (m.mean_size + 4))), 1)
                                                                   AS cap) f
     GROUP BY c.idxoid
),
leaves AS (
    -- Leaf-page models with and without deduplication credit. Every level
    -- keeps one page that the fillfactor limit never closes, so it holds one
    -- item more than a closed page.
    SELECT p.*, coalesce(cp.max_tids, 1) AS tids,
           CASE WHEN p.dedup_applies AND cp.leaf_frac IS NOT NULL
                THEN greatest(d.dedup_pages, 1)
                ELSE f.floor_pages
           END                                                AS leaf_pages,
           f.floor_pages                                      AS leaf_pages_floor
      FROM page p
      LEFT JOIN classpages cp ON cp.idxoid = p.idxoid
      CROSS JOIN LATERAL (
            SELECT CASE WHEN greatest(p.live_rows, 0) <= 0 THEN 0
                        WHEN greatest(p.live_rows, 0) <= p.leaf_cap + 1 THEN 1
                        ELSE 1 + ceil((greatest(p.live_rows, 0) - p.leaf_cap - 1)
                                      / p.leaf_cap)
                   END AS floor_pages) f
      CROSS JOIN LATERAL (
            SELECT CASE WHEN cp.tuples_total <= e.cap + 1 THEN 1
                        ELSE 1 + ceil((cp.tuples_total - e.cap - 1) / e.cap)
                   END AS dedup_pages
              FROM (SELECT greatest(cp.tuples_total
                                    / greatest(cp.leaf_frac, 1e-9), 1) AS cap) e) d
),
levels AS (
    -- Add internal levels recursively for both models.
    SELECT idxoid, 'dedup'::text AS variant, leaf_pages AS pages, int_cap FROM leaves
    UNION ALL
    SELECT idxoid, 'floor'::text, leaf_pages_floor, int_cap FROM leaves
    UNION ALL
    SELECT l.idxoid, l.variant,
           CASE WHEN l.pages <= l.int_cap + 1 THEN 1
                ELSE 1 + ceil((l.pages - l.int_cap - 1) / l.int_cap)
           END, l.int_cap
      FROM levels l WHERE l.pages > 1
),
modelled AS (
    -- Add the metapage and derive statistics flags and all five exclusion terms.
    SELECT l.*, b.expected_blocks, b.floor_blocks,
           w.stats_row_missing, w.dedup_credited, w.stats_stale,
           ((l.is_partial AND (w.stats_row_missing
                            OR w.dedup_credited
                            OR w.stats_stale
                            OR l.any_varlena_include))
            OR (NOT l.is_partial AND l.has_expressions
                AND w.stats_row_missing))                       AS suppress_row
      FROM leaves l
      CROSS JOIN LATERAL (
            SELECT (SELECT sum(v.pages) FROM levels v
                     WHERE v.idxoid = l.idxoid AND v.variant = 'dedup') + 1 AS expected_blocks,
                   (SELECT sum(v.pages) FROM levels v
                     WHERE v.idxoid = l.idxoid AND v.variant = 'floor') + 1 AS floor_blocks) b
      CROSS JOIN LATERAL (
            SELECT (l.any_no_stats AND l.last_analyze IS NOT NULL)          AS stats_row_missing,
                   (l.dedup_applies AND l.tids > 1)                         AS dedup_credited,
                   (l.tbl_mod_since_analyze > l.tbl_autoanalyze_threshold)  AS stats_stale) w
)
SELECT schemaname, tablename, indexname,
       pg_size_pretty(actual_bytes)                     AS index_size,
       CASE
         WHEN idx_reltuples < 0 THEN 'unmeasured: reltuples unknown'
         ELSE 'ok'
       END                                              AS status,
       CASE WHEN live_rows IS NULL THEN NULL ELSE
         round((100 * (1 - (expected_blocks * bs) / greatest(actual_bytes, 1)))::numeric, 1)
       END                                              AS wasted_space_pct,
       CASE WHEN live_rows IS NULL THEN NULL ELSE
         round((100 * (1 - (floor_blocks * bs) / greatest(actual_bytes, 1)))::numeric, 1)
       END                                              AS wasted_space_pct_floor,
       CASE WHEN live_rows IS NULL THEN NULL ELSE
         pg_size_pretty((actual_bytes - expected_blocks * bs)::numeric) END AS wasted_space,
       CASE WHEN live_rows IS NULL THEN NULL ELSE
         round(actual_bytes - expected_blocks * bs)     END AS wasted_space_bytes,
       array_to_string(array_remove(ARRAY[
         CASE WHEN last_analyze IS NULL THEN 'never analyzed' END,
         CASE WHEN any_stats_hidden
              THEN 'statistics not visible to this role' END,
         CASE WHEN any_stats_disabled
              THEN 'statistics target zero on an index column' END,
         CASE WHEN stats_row_missing
              THEN 'no statistics row for an index column' END,
         CASE WHEN live_rows = 0
              THEN 'zero modelled rows: validate with a population probe' END,
         CASE WHEN any_compressible
              THEN 'wide compressible key: stored width may be over-stated' END,
         CASE WHEN NOT is_partial
                   AND greatest(tbl_live_tup, idx_reltuples)
                       > 1.1 * greatest(least(tbl_live_tup, idx_reltuples), 1)
              THEN 'row-count sources disagree: analyze first' END,
         CASE WHEN is_partial AND (tbl_dead_tup > 0 OR last_analyze IS NULL)
              THEN 'partial: predicate subset may be stale' END,
         CASE WHEN is_partial AND stats_stale
              THEN 'partial: table changed since the last ANALYZE' END,
         CASE WHEN is_partial AND dedup_credited
              THEN 'partial: duplicates from table statistics' END,
         CASE WHEN dedup_credited THEN 'deduplication credited' END,
         CASE WHEN equalimage_state = 'unknown'
              THEN 'unrecognized equal-image support function: no credit' END,
         CASE WHEN ext_used THEN 'key groups from extended statistics' END
       ], NULL), '; ')                                  AS caveats,
       equalimage_state                                 AS equalimage,
       CASE
         WHEN last_vacuum IS NULL AND last_analyze IS NULL THEN 'build'
         WHEN last_analyze IS NULL                         THEN 'vacuum'
         WHEN last_vacuum IS NULL                          THEN 'analyze'
         WHEN last_vacuum > last_analyze                   THEN 'vacuum'
         ELSE 'analyze'
       END                                              AS reltuples_writer,
       round(key_groups)                                AS key_groups,
       round(tids::numeric, 1)                          AS tids_per_tuple,
       round(live_rows)                                 AS modelled_rows,
       round(idx_reltuples)                             AS idx_reltuples,
       fsm_bytes > 0                                    AS fsm_written_since_build,
       server_version_num
  FROM modelled
 WHERE NOT suppress_row
 ORDER BY (actual_bytes - floor_blocks * bs) DESC NULLS FIRST;
```

### Reading the output

The following definitions come from the statement's final projection and filters.
`index_size` and `wasted_space` use the core `pg_size_pretty` function, whose result
is text. The size input is the main fork returned by `pg_relation_size`; the FSM
fork is read separately. `wasted_space_bytes` is the same quantity as `numeric`,
so a consumer never has to parse the formatted string, and no projected value is
cast to `bigint`.
[The current recommended statement](#the-current-recommended-statement),
[pg_proc.dat#size-functions](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7487-L7507),
[pg_proc.dat#pg_size_pretty](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7500-L7507),
[dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L346-L371),
[dbsize.c#pg_size_pretty-sign](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L569-L600).

| Output | Meaning in this statement |
|---|---|
| `status` | `unmeasured: reltuples unknown` when the index's `reltuples` is negative; otherwise `ok`. `ok` is not a freshness or accuracy certification. |
| `wasted_space_pct` | Signed percentage difference from `expected_blocks`, the model that can credit deduplication. |
| `wasted_space_pct_floor` | Signed percentage difference from `floor_blocks`, the model without deduplication credit. Row-count and width uncertainty still apply. |
| `wasted_space` | Formatted signed `actual_bytes - expected_blocks * bs`; a negative value means the model predicts a larger rebuild. |
| `wasted_space_bytes` | The same signed difference as `numeric`, unformatted and unrounded to a unit. |
| `caveats` | Visible qualifications assembled by the query. A suppressed index has no output row and no explanation; since 2026-09-14 that is the only reason an index is missing. |
| `equalimage` | `recognized`, `ineligible` or `unknown`; see [Deduplication eligibility](#deduplication-eligibility). Only `recognized` earns deduplication credit. |
| `reltuples_writer` | `analyze`, `vacuum` or `build`, from the later of the table's ANALYZE and VACUUM timestamps. It names the likely last writer of the index's `reltuples`, not a proof. |
| `key_groups`, `tids_per_tuple` | Modelled distinct groups and posting-list occupancy. A TID is a heap tuple identifier. |
| `modelled_rows`, `idx_reltuples` | The row estimate used by the model and the index's catalog estimate, both `numeric`. Read a zero as an input requiring validation. |
| `fsm_written_since_build` | The test `fsm_bytes > 0`; it does not count free pages or establish that any page remains reusable. |
| `server_version_num` | The server's version number, reported without selecting a different formula. |

The caveat strings, and what each one means:

| Caveat | Condition | Consequence |
|---|---|---|
| `never analyzed` | no ANALYZE timestamp on the table | every statistics input is a default |
| `statistics not visible to this role` | at least one attribute's `pg_stats` row is filtered by privilege or row-level security | that attribute falls back to defaults |
| `statistics target zero on an index column` | `attstattarget = 0`, so ANALYZE skips the attribute | the row is not a missing-statistics error |
| `no statistics row for an index column` | statistics are absent, visible and enabled | ANALYZE has not covered the attribute |
| `zero modelled rows: validate with a population probe` | `live_rows = 0` | run the [population probe](#validation-probes) before believing a near-total-waste reading |
| `wide compressible key: stored width may be over-stated` | a varlena key with `extended` or `main` storage whose recorded width exceeds `TOAST_INDEX_TARGET` | the index may store the key compressed; see [Open Questions](#in-index-compression-of-wide-keys) |
| `row-count sources disagree: analyze first` | the table and index row estimates differ by more than 10 % | analyze before reading the estimate |
| `partial: ...` (four strings) | partial-index freshness and duplicate-source qualifications | the row is also suppressed for the first three |
| `deduplication credited` | the model priced posting lists | compare with `wasted_space_pct_floor` |
| `unrecognized equal-image support function: no credit` | `equalimage = unknown` | the engine may deduplicate where the model does not |
| `key groups from extended statistics` | a whole-key `pg_ndistinct` entry supplied the group count | |

For triage, read `wasted_space_pct` with `status`, `equalimage` and `caveats`. Do
not promote a reading with `never analyzed`, `row-count sources disagree: analyze
first`, `statistics not visible to this role`, `zero modelled rows` or `wide
compressible key` into a rebuild decision without the corresponding check. A wide
gap between the two percentages identifies dependence on the duplication estimate.
[The current recommended statement](#the-current-recommended-statement),
[analyze.c#compute_index_stats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L975),
[system_views.sql#pg_stats-visibility](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L268-L275).

The report excludes `suppress_row` and orders by the signed floor-model byte
difference with NULLs first. It filters on nothing else since 2026-09-14, so an
absent index is a suppressed index and `withheld_by` in a scored run names the
term that withheld it; there is no longer a size cutoff or a top-20 cut to look
for. Absence is still not a clean bill of health, because a suppressed row
carries no explanation in the report itself.
[The current recommended statement](#the-current-recommended-statement),
[What the no-defeat re-run measured](#what-the-no-defeat-re-run-measured).

Reading small indexes is now the reader's job rather than the statement's. The
percentage is scale-free: on the 2026-09-16 fixture database 31 suite fixtures
sit under 1 MB and **11 of them are printed**, the other 20 being withheld by
an exclusion term whatever their size. Of those 11, six are past the rebuild
threshold with a measured `REINDEX INDEX` repaying 75.2 % to 87.9 %; two -
`p31` at 192 KiB and `f91` at 296 KiB - carry floor readings of `-233.3` and
`-248.6` over a rebuild that gave back 79.2 % and 89.2 %; and `p120` reads
87.5 % on 64 KiB where a rebuild gave back nothing. Pair the percentage with
`wasted_space_bytes` before acting: `p19` reads 83.3 % on a 240 KiB index,
which is 200 KiB of waste.
[What the no-defeat re-run measured](#what-the-no-defeat-re-run-measured).

The index free space map (FSM) stores whether pages are free or used.
`GetFreeIndexPage` marks a returned page used through `RecordUsedIndexPage`.
The statement measures the fork's length rather than those entries, so its FSM
boolean is not a current free-page census.
[indexfsm.c#index-FSM](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L14-L65).

### How the model uses PostgreSQL 17

The query's common table expressions (CTEs) divide the calculation into the
following stages. This table describes the SQL above; the source column identifies
the engine input or build rule each stage approximates.

| Stages | Current calculation | Source boundary |
|---|---|---|
| `env`, `idx` | Read server constants, valid physical B-tree indexes, reloptions, main/FSM sizes, row-count inputs and both maintenance timestamps. | [pg_index.h#pg_index](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L26-L62), [pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L55-L66), [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L346-L371). |
| `opc`, `gate` | Resolve each key opclass's support function 4 and collation, then decide `recognized` / `ineligible` / `unknown`. | [nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5139-L5183), [pg_amproc.dat#text_ops-equalimage](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L205-L212). |
| `keyatts`, `extstat` | Look for a whole-key distinct-count entry from the non-inherited pass, identified through `row_to_json(se) ->> 'inherited'` rather than by naming the column; use the maximum matching visible estimate. | [system_views.sql#pg_stats_ext](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L277-L309), [mvdistinct.c#pg_ndistinct_out](../../../../raw/postgres-17/src/backend/statistics/mvdistinct.c#L355-L385), [The portable extended-statistics filter](#the-portable-extended-statistics-filter). |
| `cols`, `statvis`, `tuple` | Prefer index-expression statistics from the non-inherited pass, otherwise table-column statistics, then defaults; correct an expression's varlena header; classify hidden, disabled and compressible attributes; estimate tuple width and key groups. | [analyze.c#expression-attributes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L448-L478), [analyze.c#analyze_rel-passes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L249-L259), [heaptuple.c#heap_compute_data_size](../../../../raw/postgres-17/src/backend/access/common/heaptuple.c#L215-L262). |
| `page` | Approximate tuple slots, leaf and internal capacity under both the fillfactor limit and the hard-fit reservation, and the build's posting-list size cap. | [nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L645-L671), [nbtsort.c#soft-limit](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L853-L854), [nbtsort.c#posting-size-limit](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1284-L1308). |
| `kstat`, `gclass`, `classfit`, `classsize`, `classpages` | Split eligible single-key rows into NULL, most-common-value and remaining classes; use one class for multicolumn keys; price whole posting tuples and one tail per group separately; convert to pages with the class's mean size and mean posting credit. | [nbtsort.c#group-boundaries](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1310-L1349), [nbtdedup.c#_bt_dedup_save_htid-cap](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L510-L513), [nbtdedup.c#_bt_form_posting-size](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L879-L884). |
| `leaves`, `levels`, `modelled` | Estimate leaf pages, recursively add internal levels with one never-closed page per level, add a metapage, then derive suppression and caveat conditions. | [nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1062-L1128), [nbtsort.c#_bt_slideleft](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L682-L700), [nbtsort.c#BTPageState](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L229-L252). |

The engine build path is `index_build` → the access method's `ambuild` callback →
`btbuild` → `_bt_leafbuild` → `_bt_load` → `_bt_buildadd`. `BTWriteState` holds the
index and allocation state; each `BTPageState` holds the working page and a link to
its parent level. The estimator approximates this path without invoking a build.
[index.c#ambuild-call](../../../../raw/postgres-17/src/backend/catalog/index.c#L3048-L3053),
[nbtree.c#ambuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L128-L129),
[nbtsort.c#btbuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L290-L328),
[nbtsort.c#build-state](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L229-L252),
[nbtsort.c#_bt_leafbuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L535-L571),
[nbtsort.c#_bt_load](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1284-L1349),
[nbtsort.c#_bt_sort_dedup_finish_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1026-L1050).

Tuple geometry is still an approximation. `IndexTupleData` contains the TID and
size/flag word; a posting tuple adds an array of `ItemPointerData`. `PageHeaderData`
includes the line-pointer array, and `BTPageOpaqueData` holds B-tree sibling/level
metadata. Actual tuple formation omits NULL values, aligns attributes in order and
can compress variable-width values. The SQL hard-codes eight-byte alignment and uses
average widths, so those inputs do not reconstruct every physical tuple.
[itup.h#IndexTupleData](../../../../raw/postgres-17/src/include/access/itup.h#L35-L60),
[itemptr.h#ItemPointerData](../../../../raw/postgres-17/src/include/storage/itemptr.h#L25-L47),
[nbtdedup.c#_bt_form_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L864-L910),
[bufpage.h#PageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L155-L171),
[nbtree.h#BTPageOpaqueData](../../../../raw/postgres-17/src/include/access/nbtree.h#L62-L71),
[indextuple.c#index_form_tuple_context](../../../../raw/postgres-17/src/backend/access/common/indextuple.c#L94-L163).

### Deduplication eligibility

Deduplication stores one key image with several heap TIDs. For a fresh build,
`_bt_leafbuild` recomputes equal-image eligibility. `_bt_allequalimage` refuses
INCLUDE indexes outright, then retrieves each key's support function 4 and calls
it; a missing function or a false return makes the index ineligible. The sorted
build also requires a non-unique index and `deduplicate_items` enabled.
[nbtsort.c#_bt_leafbuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L557-L570),
[nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5139-L5183),
[nbtsort.c#deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1135-L1152).

The statement reports one of three states instead of a boolean:

| `equalimage` | Condition in `gate` | Model behaviour |
|---|---|---|
| `ineligible` | the index has INCLUDE columns, or some key opclass has no support function 4, or a recognized `btvarstrequalimage` key has a nondeterministic collation | no deduplication credit; the engine agrees |
| `recognized` | every key opclass has support function 4, and each is the internal `btequalimage` or `btvarstrequalimage` | deduplication credited when the index is also non-unique with `deduplicate_items` on |
| `unknown` | every key has support function 4, but at least one is not one of those two internal functions | no credit, plus the caveat `unrecognized equal-image support function: no credit` |

The determinism test now applies only to `btvarstrequalimage` keys, because
`btequalimage` returns true unconditionally while `btvarstrequalimage` returns
`pg_locale_deterministic`. Scored against the metapage flag that the build
itself writes, the three states are right on 23 of the gate's 25 fixtures and
conservative on the two custom-opclass indexes; see
[The deduplication gate, scored against the current statement](#the-deduplication-gate-scored-against-the-current-statement).
[datum.c#btequalimage](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L424-L438),
[varlena.c#btvarstrequalimage](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L2595-L2615),
[pg_locale.c#pg_locale_deterministic](../../../../raw/postgres-17/src/backend/utils/adt/pg_locale.c#L1567-L1575),
[fmgr.c#internal-function-resolution](../../../../raw/postgres-17/src/backend/utils/fmgr/fmgr.c#L216-L240),
[nbtpage.c#_bt_initmetapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L67-L84),
[nbtsort.c:1126](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1126).

### Widths, expression statistics and compression

ANALYZE records `stawidth` as the average `VARSIZE_ANY` of the sampled datum.
A stored table column is already in short-header form, so its recorded width is
what the index tuple stores. An index expression is computed fresh and carries a
four-byte header, while `heap_compute_data_size` stores the converted short size,
three bytes less, whenever the value fits in 127 bytes. The statement therefore
subtracts three bytes from an index-expression width between 5 and 130 and keeps
the value unaligned; on a freshly built `lower(txt)` index over 23-character
values that correction moved the reading from `-22.2 %` to `0.0 %`.
[analyze.c#compute_scalar_stats-width](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2420-L2426),
[analyze.c#stawidth](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2536-L2540),
[heaptuple.c#heap_compute_data_size](../../../../raw/postgres-17/src/backend/access/common/heaptuple.c#L234-L242),
[varatt.h#VARATT_CAN_MAKE_SHORT](../../../../raw/postgres-17/src/include/varatt.h#L257-L262),
[The current recommended statement](#the-current-recommended-statement).

`index_form_tuple` compresses a varlena key that is wider than
`TOAST_INDEX_TARGET` when the index attribute's storage is `extended` or `main`,
and the index attribute inherits the table column's storage. `TOAST_INDEX_TARGET`
is `MaxHeapTupleSize / 16`, which is 510 bytes at the default block size. No
catalog records the compressed width, so the model cannot see it; the statement
raises `wide compressible key: stored width may be over-stated` instead. Two
60,000-row tables of the same 900-character keys measured 367 blocks with
`extended` storage and 10,003 blocks with `plain`, both recording an
`avg_width` of 904, and the estimator read `-2625.6 %` against an exact `0.0 %`.
[indextuple.c#index_form_tuple-compression](../../../../raw/postgres-17/src/backend/access/common/indextuple.c#L116-L138),
[heaptoast.h#TOAST_INDEX_TARGET](../../../../raw/postgres-17/src/include/access/heaptoast.h#L63-L68),
[htup_details.h#MaxHeapTupleSize](../../../../raw/postgres-17/src/include/access/htup_details.h#L553-L563),
[pg_type.h#TYPSTORAGE_EXTENDED](../../../../raw/postgres-17/src/include/catalog/pg_type.h#L307-L310),
[index.c#ConstructTupleDescriptor-attstorage](../../../../raw/postgres-17/src/backend/catalog/index.c#L353-L360),
[Open Questions](#in-index-compression-of-wide-keys).

Both `pg_stats` joins and the `pg_stats_ext` join keep to the non-inherited
pass. The `pg_stats` joins say `inherited = false`; the `pg_stats_ext` join
reads the same flag as `coalesce((row_to_json(se) ->> 'inherited')::boolean,
false) = false`, so that one text parses on a server whose view has no such
column, and there admits the single pass it does record. See
[The portable extended-statistics filter](#the-portable-extended-statistics-filter).
`analyze_rel` runs the non-inherited pass and then, when the table has children,
the inherited pass, and `update_attstats` stores each under its own `stainherit`
value. Without the filter an index on an inheritance parent receives two rows per
attribute and the width, NULL and distinct inputs are counted twice; the measured
cost of that was `-550.8 %` on a freshly built index whose two rows recorded
average widths of 21 and 77 bytes.
[analyze.c#analyze_rel-passes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L249-L259),
[analyze.c#update_attstats-stainherit](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1647),
[system_views.sql#pg_stats](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L189-L211).

An expression attribute's `pg_stats` row belongs to the index, and `pg_stats`
filters rows by `has_column_privilege` on the relation that owns them. An index's
`relacl` is empty because `GRANT` refuses indexes, so the fallback builds the
default table ACL, which grants the owner alone. The statement therefore tests
`has_column_privilege(index, attnum, 'SELECT')` for expression attributes and the
table's privileges for plain keys, and it reads `attstattarget` so that a column
ANALYZE deliberately skips is reported as disabled rather than missing.
[system_views.sql#pg_stats-visibility](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L268-L275),
[acl.c#column_privilege_check](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L2538-L2569),
[acl.c#acldefault](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L813-L821),
[aclchk.c#pg_class_aclmask_ext](../../../../raw/postgres-17/src/backend/catalog/aclchk.c#L3396-L3412),
[aclchk.c#grant-refuses-indexes](../../../../raw/postgres-17/src/backend/catalog/aclchk.c#L1858-L1863),
[pg_attribute.h#attstattarget](../../../../raw/postgres-17/src/include/catalog/pg_attribute.h#L168-L176),
[analyze.c#examine_attribute](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1019-L1030).

### Page and posting geometry

A new build page reserves the high-key line pointer, and `PageGetFreeSpace`
subtracts one more line pointer; with the 24-byte page header and the 16-byte
opaque area that is the statement's 48-byte deduction. `_bt_buildadd` then closes
a page under either of two conditions, and the model now applies both:

| Rule in `_bt_buildadd` | Closed-page item count for an aligned tuple size `s` |
|---|---|
| fillfactor limit: `pgspc + last_truncextra < btps_full` | `floor((bs - 48 - btps_full) / (s + 4))` |
| hard fit: `pgspc < itupsz + MAXALIGN(sizeof(ItemPointerData))` | `floor((bs - 48 - 8 - s) / (s + 4))` |

`leaf_cap` is the smaller of the two. The published statement used the fillfactor
term alone, which is one item too high in 30 of the 78 measured cells — every
`fillfactor = 100` case and four wide-key cases at `fillfactor = 90`.
[nbtsort.c#_bt_blnewpage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L605-L629),
[bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L907-L923),
[bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L214),
[nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1147),
[nbtsort.c#soft-limit](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L853-L854),
[nbtsort.c#page-boundary](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L874-L935).

Internal levels differ in two ways the published model ignored. `_bt_sortaddtup`
truncates the first data item of every internal page to a bare `IndexTupleData`
of eight bytes, so a page carries that 12-byte slot plus its pivots; and the
rightmost page of each level is never closed by the fillfactor limit, because
`_bt_uppershutdown` finishes it and `_bt_slideleft` removes its unused high-key
line pointer. A page that is never closed keeps one item more than a closed one,
which makes the level recursion

```text
pages(M, cap) = 1                                     when M <= cap + 1
pages(M, cap) = 1 + ceil((M - cap - 1) / cap)         otherwise
```

Applied at the leaf level and at every internal level, that recursion reproduced
the exact `relpages` of all 78 measured builds; the previous form was exact in 53
and off by as much as 5 blocks.
[nbtsort.c#_bt_sortaddtup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L713-L735),
[nbtsort.c#_bt_slideleft](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L682-L700),
[nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1062-L1128),
[nbtree.h#fillfactors](../../../../raw/postgres-17/src/include/access/nbtree.h#L199-L202).

For duplicate groups the build caps a posting tuple at
`MAXALIGN_DOWN(bs * 10 / 100) - sizeof(ItemIdData)`, which is 812 bytes at the
default block size, and refuses another TID when
`MAXALIGN(basetupsize + (nhtids + 1) * sizeof(ItemPointerData))` would exceed it.
Because `basetupsize` is already aligned, the capacity is
`floor((MAXALIGN_DOWN(812) - itupsz) / 6)`, which is 132 TIDs for a four-byte
integer key. `bt_page_items` measured exactly 132 TIDs at an item length of 808
bytes on every such fixture. Each group therefore contributes
`floor(u / m)` full posting tuples and one shorter tail, and the statement prices
those two sizes separately instead of charging the tail as a full tuple.
[nbtsort.c#maxpostingsize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1304-L1305),
[nbtdedup.c#_bt_dedup_save_htid-cap](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L510-L513),
[nbtdedup.c#_bt_dedup_start_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L432-L474),
[nbtdedup.c#_bt_form_posting-size](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L879-L884),
[nbtsort.c#_bt_sort_dedup_finish_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1026-L1050).

Two details of that pricing matter. A one-TID group is a plain tuple, not a
posting tuple, so the tail size interpolates between the integer TID counts that
bracket the class's average tail rather than rounding it up; without that, an
index with 380 accidental duplicate pairs among 300,000 rows read `-40.0 %`
instead of `0.0 %`. And a page mixes full and tail tuples, so the page capacity
uses the class's mean tuple size and mean posting credit; a per-size capacity
that packs tails on tail-only pages under-counted a 500-row group's index by 5 %.

### Row counts and exclusions

The SQL treats negative index `reltuples` as unknown and takes zero at face value.
For a partial index, whose predicate selects a subset of table rows, it uses the
index's `reltuples`. For a non-partial index it takes the lesser of that estimate
and the table's nonzero `n_live_tup`, falling back to `reltuples` when the table
counter is zero. Neither input is an exact current count, and a zero now raises a
caveat pointing at the [population probe](#validation-probes).
[The current recommended statement](#the-current-recommended-statement),
[pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L55-L66),
[analyze.c#index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663),
[system_views.sql#pg_stat_all_tables](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L670-L703).

ANALYZE is not the only writer of an index's `reltuples`. A VACUUM that removed
tuples counts the live heap TIDs on each leaf page, clamps the total to the heap
count when that count is exact, and writes it through the same relation-statistics
path. A cleanup-only scan counts index tuples instead, marks the result as an
estimate, and the write is skipped. The statement now reports which maintenance
command ran last in `reltuples_writer`, derived from the later of the table's
VACUUM and ANALYZE timestamps; it is an attribution, not a proof, because a
cleanup-only VACUUM leaves a timestamp without writing the value.
[nbtree.c#btvacuumpage-counting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1347-L1362),
[nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L870-L920),
[vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3073-L3099),
[system_views.sql#pg_stat_all_tables](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L670-L703).

`ANALYZE` gives index attributes their own column statistics only for expressions.
`IndexInfo` identifies expression attributes and the predicate;
`compute_index_stats` evaluates that predicate over its sample. Plain keys and
INCLUDE columns therefore fall back to table statistics in this query, even when
the index covers only a subset.
[analyze.c#expression-attributes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L448-L478),
[analyze.c#index-statistics-write](../../../../raw/postgres-17/src/backend/commands/analyze.c#L588-L602),
[analyze.c#compute_index_stats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L845-L884),
[execnodes.h#IndexInfo](../../../../raw/postgres-17/src/include/nodes/execnodes.h#L183-L193).

Five conditions set `suppress_row`. The missing-statistics condition is now
per attribute and excludes attributes whose statistics are hidden by privilege or
disabled by `attstattarget = 0`, so those cases are reported with a caveat instead
of vanishing.
[The current recommended statement](#the-current-recommended-statement).

| Index scope | Suppression condition |
|---|---|
| Partial | At least one attribute has no returned statistics row that is neither hidden nor disabled, and a table ANALYZE timestamp exists. |
| Partial | The model credits deduplication and computes more than one TID per tuple. |
| Partial | The table's modification counter exceeds the model's auto-analyze threshold. |
| Partial | At least one INCLUDE attribute has negative `attlen`, identifying variable width. |
| Non-partial expression index | The same missing-statistics condition as the first row. |

The staleness threshold uses the auto-analyze formula, with per-table reloptions
overriding the GUC defaults: threshold plus scale factor times nonnegative table
`reltuples`. It is a table-wide scheduling threshold, not a test of an individual
predicate subset's freshness.
[autovacuum.c#analyze-reloptions](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3011-L3017),
[autovacuum.c#analyze-threshold](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3063-L3095),
[pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-17/src/include/pgstat.h#L399-L429).

### Validation probes

Two readings cannot be validated from catalogs alone: a zero row count on a
partial index, and the number of duplicate groups the build will actually form.
The generator below reads the catalogs and emits one probe statement per index
that needs one. It executes nothing itself, so the emitted text can be reviewed
before it runs; it is a companion to the estimator, not part of it.

A `population` probe is emitted for a partial index whose `reltuples` is zero or
negative. It is an `EXISTS` subquery over the predicate text from `pg_get_expr`,
so the executor stops at the first matching row, and the planner may satisfy it
from the partial index itself: on the measured empty-subset fixture it chose
`Index Only Scan using empty_open` with no filter, and on the populated fixture
it chose that index once a sequential scan was disabled.
[pg_proc.dat#pg_get_expr](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L8219-L8220),
[ruleutils.c#pg_get_expr_ext](../../../../raw/postgres-17/src/backend/utils/adt/ruleutils.c#L2648-L2662),
[nodeSubplan.c#ExecScanSubPlan-EXISTS](../../../../raw/postgres-17/src/backend/executor/nodeSubplan.c#L293-L296),
[indxpath.c#check_index_predicates](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L3244-L3350).

The generator keeps its own `pg_relation_size(c.oid) > 1024 * 1024` filter,
which the report gave up on 2026-09-14. That was the asker's decision, and it
leaves the generator narrower than the statement it validates: the rows most in
need of a population probe are the small ones the report now prints. See
[Open Questions](#partial-index-populations-and-zero-counts).

A `groups` probe is emitted only for an index that would pass the deduplication
gate with a recognized support function. The build groups adjacent sorted tuples
by `_bt_keep_natts_fast`, which compares binary images and treats two NULLs as
equal, and `GROUP BY` over the key expressions reproduces that grouping for
exactly those opclasses. For an unrecognized or ineligible opclass the generator
emits no probe, because SQL equality and binary-image equality can disagree.
[nbtsort.c#_bt_load-grouping](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1314-L1316),
[nbtutils.c#_bt_keep_natts_fast](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4875-L4905),
[datum.c:271](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L271).

```sql
-- Finding 2: generate validation probes for the rows the estimator cannot trust.
-- The generator is read-only; it emits statements for review before they run.
SET /* wiki_btree_probe_statement_timeout */ statement_timeout = '30s';
SET /* wiki_btree_probe_lock_timeout */ lock_timeout = '2s';

WITH cand AS (
    SELECT /* wiki_btree_probe_generator */
           c.oid AS idxoid, n.nspname, c.relname AS indexname,
           x.indrelid, x.indnkeyatts, c.reltuples,
           pg_get_expr(x.indpred, x.indrelid) AS pred,
           (SELECT bool_and(EXISTS (SELECT 1 FROM pg_amproc ap
                                     JOIN pg_proc pr     ON pr.oid = ap.amproc
                                     JOIN pg_language pl ON pl.oid = pr.prolang
                                    WHERE ap.amprocfamily = op.opcfamily
                                      AND ap.amproclefttype = op.opcintype
                                      AND ap.amprocrighttype = op.opcintype
                                      AND ap.amprocnum = 4
                                      AND pl.lanname = 'internal'
                                      AND pr.prosrc IN ('btequalimage',
                                                        'btvarstrequalimage')))
              FROM generate_subscripts(x.indclass, 1) k
              JOIN pg_opclass op ON op.oid = x.indclass[k]
             WHERE k < x.indnkeyatts)                     AS recognized,
           NOT x.indisunique AND x.indnatts = x.indnkeyatts
             AND coalesce((SELECT option_value::bool FROM pg_options_to_table(c.reloptions)
                            WHERE option_name = 'deduplicate_items'), true) AS gateable
      FROM pg_class c
      JOIN pg_index x     ON x.indexrelid = c.oid
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_am am       ON am.oid = c.relam
     WHERE am.amname = 'btree' AND c.relkind = 'i' AND x.indisvalid
       AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
       AND pg_relation_size(c.oid) > 1024 * 1024
)
SELECT indexname,
       CASE WHEN pred IS NOT NULL AND reltuples <= 0 THEN 'population'
            WHEN coalesce(recognized, false) AND gateable THEN 'groups'
            ELSE 'none' END AS probe_kind,
       CASE
         WHEN pred IS NOT NULL AND reltuples <= 0 THEN
           format('SELECT %L::text AS indexname, ''population''::text AS probe,'
                  ' (EXISTS (SELECT 1 FROM ONLY %s WHERE %s))::text AS result;',
                  indexname, indrelid::regclass::text, pred)
         WHEN coalesce(recognized, false) AND gateable THEN
           format('SELECT %L::text AS indexname, ''groups''::text AS probe,'
                  ' count(*)::text AS result FROM (SELECT 1 FROM ONLY %s %s GROUP BY %s) s;',
                  indexname, indrelid::regclass::text,
                  CASE WHEN pred IS NULL THEN '' ELSE 'WHERE ' || pred END,
                  (SELECT string_agg(pg_get_indexdef(idxoid, k, true), ', ' ORDER BY k)
                     FROM generate_series(1, indnkeyatts) k))
         ELSE NULL
       END AS probe_sql
  FROM cand
 ORDER BY probe_kind, indexname;
```

On the measured fixtures the generator emitted a population probe for both
partial indexes with a zero row count, a group probe for the recognized
duplicate-heavy index, and nothing for a `numeric` index. The probes then
separated a true reading from a false one: for an index whose subset really was
empty the probe returned `false`, confirming the estimator's `99.9 %`, and for an
index whose `reltuples` had been forged to zero while 300,000 rows still matched
the predicate the probe returned `true`, catching the same `99.9 %` as a lie. The
group probe counted 5,000 groups against the model's estimate of 4,997.

### Operational and verification limits

`pg_relation_size` takes and releases `AccessShareLock` on each relation. It returns
NULL if a relation has disappeared, and the file-size loop can raise a file-access
error. These calls inspect file lengths; they do not provide a single physical
snapshot of all indexes and statistics in the report. Since 2026-09-14 the
statement measures every candidate rather than only those over 1 MB, so it makes
that call for more relations and holds each lock for the same instant as before;
the exposure to a relation disappearing mid-report is wider by the same
proportion as the candidate set, on the same mechanism.
[dbsize.c#calculate_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L301-L371).

No contrib extension is needed by the recommended statement or by the probe
generator: their inputs are core catalogs, views and functions. The measurement
harness is a different matter — it uses `pageinspect` and `pgstattuple` as
oracles, in a disposable cluster only. The build-dependent constants still matter:
catalog headers include generated `_d.h` files, `genbki.pl` builds catalog outputs
from the source definitions, and `Gen_fmgrtab.pl` uses `pg_proc.dat` to generate
function lookup support. Every measurement below was taken at the default
`BLCKSZ` of 8192 and `MAXIMUM_ALIGNOF` of 8; the SQL's literal layout assumptions
need separate validation on a different build configuration.
[pg_class.h#generated-header](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L21-L22),
[pg_index.h#generated-header](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L21-L22),
[catalog/Makefile#genbki](../../../../raw/postgres-17/src/include/catalog/Makefile#L132-L143),
[utils/Makefile#Gen_fmgrtab](../../../../raw/postgres-17/src/backend/utils/Makefile#L47-L53),
[btreefuncs.c#GetBTPageStatistics](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L108-L194),
[pageinspect--1.8--1.9.sql#bt_page_stats](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L87-L124),
[pgstattuple--1.4.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4.sql#L19-L31).

The pinned regression files provide adjacent engine coverage: deduplication in
`btree_index.sql`, and statistics-setting restrictions for plain, expression and
INCLUDE attributes in `index_including.sql`. They do not constitute an accuracy
test of this wiki's estimator; the fixtures below do that.
[btree_index.sql#deduplication-tests](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L186-L213),
[index_including.sql#statistics-tests](../../../../raw/postgres-17/src/test/regress/sql/index_including.sql#L150-L158).

### Plan review

This section is the source-only review filed on 2026-09-07, before any of the
plans were implemented. Its verdicts are unchanged; what each one became in the
statement is in [What the ten plans changed](#what-the-ten-plans-changed).

| Plan | Verdict | Principal finding |
|---|---|---|
| 1. Input diagnostics | Keep, extend | Expression-attribute statistics are visible only to superusers, the index owner and the owner's role members; the statement tests the table's privileges, so other roles get `no statistics row` rather than `not visible`. |
| 2. Partial-index probes | Keep, simplify | The zero check can be an `EXISTS` probe; for gated indexes a `GROUP BY` on the key reproduces the builder's grouping; VACUUM is a second writer of index `reltuples`. |
| 3. Publication barrier | Keep, strengthen | A forced flush completes before the writer's `ReadyForQuery` outside a transaction block, so the barrier is ordered; the counter artifact has a source mechanism. |
| 4. Posting tails | Keep | The two-size formula follows the build; posting capacity varies per group for variable-width keys. |
| 5. Page geometry | Narrow | The leaf closed form reproduces the builder's soft limit for uniform tuples up to 896 bytes; residual errors are pivots, size variance and posting overhead. |
| 6. Statistics selection | Upgrade to defect | An index on an inheritance parent joins two `pg_stats` rows per attribute and double-counts the width, NULL and distinct inputs. |
| 7. Operator classes | Keep, bound | All 29 built-in B-tree support-function-4 records use the two recognized functions; pattern operator classes reject nondeterministic collations at index creation; the metapage flag is a harness oracle. |
| 8. Signed bytes | Keep, simplify | `pg_size_pretty(numeric)` exists, and the existing `bigint` casts can raise `bigint out of range`. |
| 9. Reproducibility | Keep, constrain | Builds must be out of tree; the SQL block hash baseline moved with the 2026-09-07 comment edit. |
| 10. Thresholds | Keep, refine | Insert-grown density depends on the split path: fillfactor, 50:50, or 96 percent. Calibrate per insertion pattern. |

The review's supporting evidence, in the same order: statistics visibility and the
owner-only default ACL
([acl.c#column_privilege_check](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L2538-L2569),
[acl.c#acldefault](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L813-L821),
[acl.c#aclmask](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L1388-L1445),
[aclchk.c#grant-refuses-indexes](../../../../raw/postgres-17/src/backend/catalog/aclchk.c#L1858-L1863));
`DO` and PL/pgSQL availability for a generated probe
([gram.y#DoStmt](../../../../raw/postgres-17/src/backend/parser/gram.y#L9037),
[initdb.c#load_plpgsql](../../../../raw/postgres-17/src/bin/initdb/initdb.c#L1974-L1977));
the forced-flush path
([pgstat.c#pgstat_force_next_flush](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L700-L708),
[postgres.c#idle-stats-flush](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L4634-L4705),
[pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L584-L600),
[pgstat.c#flush-intervals](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L117-L122),
[pgstat_relation.c#AtEOXact_PgStat_Relations](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L560-L574),
[pgstat_relation.c#pgstat_report_analyze](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L289-L337),
[pgstat_relation.c#pgstat_relation_flush_cb](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L857-L860),
[pgstat.c#pgstat_clear_snapshot](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L786-L800),
[pgstatfuncs.c#snapshot-and-flush-functions](../../../../raw/postgres-17/src/backend/utils/adt/pgstatfuncs.c#L1680-L1695),
[guc_tables.c#stats_fetch_consistency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4966-L4974),
[stats.sql#forced-flush](../../../../raw/postgres-17/src/test/regress/sql/stats.sql#L101-L102));
the built-in equal-image inventory and the pattern-opclass collation check
([pg_amproc.dat#bpchar_ops-equalimage](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L31-L33),
[pg_amproc.dat#text_ops-equalimage](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L205-L212),
[index.c#pattern-ops-collation-check](../../../../raw/postgres-17/src/backend/catalog/index.c#L826-L849),
[btreefuncs.c#bt_metap-allequalimage](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L916-L921));
the numeric range error
([numeric.c#bigint-out-of-range](../../../../raw/postgres-17/src/backend/utils/adt/numeric.c#L4546-L4549));
the out-of-tree build requirement
([installation.sgml#VPATH](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L427-L432),
[installation.sgml#meson-setup](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L2012-L2025));
and the split strategies
([nbtsplitloc.c#split-policy](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L278-L335),
[nbtsplitloc.c#single-value-strategy](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L406-L416),
[nbtsplitloc.c#_bt_strategy-single-value](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L1020-L1033)).

### What the ten plans changed

Each row is what the plan changed in the filed text, which the text still
carries. The fixtures that measured plans 4, 5 and 10 were page-local and were
removed on 2026-09-14, so the `Status` column records implementation, not
current evidence.

| Plan | Change in the statement or harness | Status |
|---|---|---|
| 1 | `has_column_privilege` on the index for expression attributes; `attstattarget = 0` reported as disabled; per-attribute missing/hidden/disabled classification; four new caveat strings | implemented |
| 2 | `EXISTS` population probe and `GROUP BY` group probe generated from the catalogs; `reltuples_writer` column; `zero modelled rows` caveat | implemented |
| 3 | `pg_stat_force_next_flush()` barrier before and after every fixture ANALYZE | implemented in the harness, extended on 2026-09-14 to the maintenance `VACUUM ANALYZE`, and carried since 2026-09-16 by `maint_begin()` and `maint_end()`, which flush on both sides of every one |
| 4 | Whole posting tuples and one tail per group priced separately, with fractional-TID interpolation and a class-mean page capacity | implemented; the posting-tail fixtures that measured it are retired |
| 5 | Hard-fit reservation in `leaf_cap`; minus-infinity first item in `int_cap`; the never-closed rightmost page in the level recursion | implemented; the geometry cells that measured it are retired |
| 6 | `inherited = false` on both `pg_stats` joins and on `pg_stats_ext` | implemented; since 2026-09-10 the `pg_stats_ext` half reads the flag through `row_to_json()` so one text runs on both majors |
| 7 | Three-state `equalimage` column; determinism tested only for `btvarstrequalimage`; scored against `bt_metap` | implemented |
| 8 | `pg_size_pretty(numeric)`, `numeric` projections, new `wasted_space_bytes`; no `bigint` cast anywhere | implemented |
| 9 | Out-of-tree VPATH build; block hashes re-baselined; core regression suite run | implemented |
| 10 | Seven insertion-pattern fixtures scored against `REINDEX INDEX` | implemented in 2026-09-08, retired in 2026-09-14: the calibration was page-local, and the mandatory suite defines no insertion-pattern fixture |

Two corrections the plans did not anticipate came out of the runs: the
three-byte varlena-header difference in an index expression's recorded width, and
in-index compression of wide keys. Both are covered under
[Widths, expression statistics and compression](#widths-expression-statistics-and-compression).

### The deduplication gate, scored against the current statement

**Family 1 is scored against the recommended text on every run, and on
2026-09-16 it passed outright again: 25 of 25 `PASS` under the shared bands,
with no over-credit.** The fixtures are 25 indexes on two 500,000-row tables with 5,000
distinct values per key column, in a UTF8 database so that the ICU cases can
exist. Test 11's three `deduplicate_items = off` legs are no longer among them,
because the shared suite retired that number. Two oracles run side by side:
`bt_metap().allequalimage`, the verdict the build itself computed and stored,
and a measured `REINDEX INDEX` behind the four bands.
[btreefuncs.c#bt_metap-allequalimage](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L916-L921),
[nbtpage.c#_bt_initmetapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L67-L84).

| `equalimage` | metapage | credited | Fixtures |
|---|---|---|---|
| `recognized` | true | yes, 8 | `i_int4`, `i_int8`, `i_text_det`, `i_text_det2`, `i_text_icu_det`, `i_ei_alias`, `i_multi_ok`, `i2_ok` |
| `recognized` | true | no, 1 | `i_uniq`, where uniqueness suppresses the build-time pass |
| `ineligible` | false | no, 9 | `i_numeric`, `i_float4`, `i_float8`, `i_inc`, `i_multi_bad`, `i_ei_none`, `i_expr_num`, `i_expr_lower_ci`, `i_text_nondet` |
| `unknown` | false | no, 5 | `i_ei_false`, `i_mixed_tf`, `i_mixed_ft`, `i2_tf`, `i2_ft` |
| `unknown` | true | no, 2 | `i_ei_true`, `i_squat` |

Against the pass criteria of
[How to run the suite against the current statement](#how-to-run-the-suite-against-the-current-statement):
**no index is credited that the metapage says was not deduplicated, 0 of 25**;
`equalimage` agrees with the metapage on every one of the 9 `recognized` and 9
`ineligible` rows; and the **two under-credits are `i_ei_true` and `i_squat`**,
both in the conservative direction, at `-226.4 %` and `-319.1 %` on indexes the
engine did deduplicate. The engine's own `DEBUG1` verdict is the cross-check:
the build log holds 13 `can safely use deduplication` lines and 13
`cannot use deduplication` lines, and the 13 safe ones are the 11 equal-image
fixtures plus the two TOAST indexes the two tables' own TOAST relations bring
with them, while `i_inc` produces no line at all because the `INCLUDE` refusal
returns before the message.
[nbtutils.c#_bt_allequalimage-debug](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5172-L5180),
[nbtutils.c#_bt_allequalimage-INCLUDE](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5144-L5147).

**Neither the 2026-09-14 filter removal nor the 2026-09-16 no-defeat repair
changed anything in this group.** Every gate index is at least 421 blocks, so
`under_1mb` is 0 and all 25 rows are printed; the group's verdicts, oracles and
as-built readings came out identical on both runs, and its two drained tables
are now maintained by two bracketed statements that removed 899,900 tuples and
left 714 deleted pages in one index, at `dead but not yet removable` 0.

The readings themselves are unchanged from the earlier runs of the same shapes:
`i_multi_bad` is the maximum at 28.8 %, the minimum is `-320.0 %` on
`i_multi_ok` and `i2_ok`, and the three deterministic `text` fixtures read
`-0.4 %` on the point estimate against a `-319.1 %` floor, because the floor
prices no deduplication at all where the build wrote 130 TIDs per tuple. Block
counts: 421 for `i_int4`, `i_int8`, `i_ei_alias` and `i_ei_true`, 460 for the
three deterministic `text` fixtures and `i_squat`, 459 for `i_multi_ok` and
`i2_ok`, 1,374 for `i_uniq`, 1,376 for the seven single-column ineligible
fixtures and 1,931 for the seven two-column and wide ones.

The one operational finding of the group is the two-column pair: without a
`CREATE STATISTICS ... (ndistinct)` object the model multiplies per-column
distinct counts, saturates the clamp and prices singleton tuples, which is the
`-320.0 %` above. It is filed as
[Multicolumn key groups without extended statistics](#multicolumn-key-groups-without-extended-statistics).
[system_views.sql#pg_stats_ext](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L277-L309),
[mvdistinct.c#pg_ndistinct_out](../../../../raw/postgres-17/src/backend/statistics/mvdistinct.c#L355-L385),
[fmgr.c#internal-function-resolution](../../../../raw/postgres-17/src/backend/utils/fmgr/fmgr.c#L216-L240).

`i_squat` also records a fixture-construction trap that is not a statement
defect: `FUNCTION 4 btequalimage(oid)` in `CREATE OPERATOR CLASS` resolves
through `pg_catalog` and picks up the built-in, which would make the index
`recognized` with a true metapage; only the schema-qualified
`FUNCTION 4 public.btequalimage(oid)` registers the impostor and produces the
intended `unknown`.

### The collation branch, measured with ICU

**The `ineligible` branch that reads `collisdeterministic` is no longer
source-derived only, and the gate stage re-measures it on every run.** The
first run to reach it was 2026-09-09; the 2026-09-16 run reproduced every row
below on a build configured `--with-icu` against ICU 74.2, which is
`configure`'s own default provider.
[installation.sgml#ICU-default](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L170).

| Step | Result |
|---|---|
| `CREATE COLLATION` in a `SQL_ASCII` database | `ERROR: current database's encoding is not supported with this provider`; the fixtures need `TEMPLATE template0 ENCODING 'UTF8'` |
| `CREATE COLLATION nd (provider = icu, locale = 'und-u-ks-level2', deterministic = false)` | `pg_collation.collisdeterministic` false |
| index on a `COLLATE nd` key | metapage `allequalimage` **false**; statement reads `ineligible`; build logs `index "..." cannot use deduplication` |
| index on a deterministic ICU key | metapage **true**; statement reads `recognized`; build logs `index "..." can safely use deduplication` |
| `CREATE INDEX ... (k text_pattern_ops)` on the `COLLATE nd` key | `ERROR: nondeterministic collations are not supported for operator class "text_pattern_ops"` |

So the gate's determinism test tracks the engine on both sides, and the
`text_pattern_ops` refusal this page derived from source happens verbatim; the
17 leg's server-error check expects exactly that one error and saw it once on
the run this revision files.
Nothing else about the cluster's ICU collations is exercised.
[varlena.c#btvarstrequalimage](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L2595-L2615),
[pg_locale.c#pg_locale_deterministic](../../../../raw/postgres-17/src/backend/utils/adt/pg_locale.c#L1567-L1575),
[nbtutils.c#_bt_allequalimage-debug](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5172-L5180),
[index.c#pattern-ops-collation-check](../../../../raw/postgres-17/src/backend/catalog/index.c#L826-L849).

### The portable extended-statistics filter

**One line changed, and the statement now runs unmodified on both majors.** The
`extstat` CTE used to name a column:

```text
AND se.inherited = false
```

It now reads the same flag out of the row instead:

```text
AND coalesce((row_to_json(se) ->> 'inherited')::boolean,
             false) = false
```

Nothing else about the statement moved, and the page proves that rather than
asserting it: the `extstat` stage rebuilds the previous text from the filed one
by undoing exactly this edit, and both scripts check the reconstruction against
a recorded baseline. That baseline is
`152f4172f1ee1dfd86467e525bfe37babba92a5ad036358bed0d17aa4b10594a` since the
2026-09-14 filter removal, and was
`8acd531b7bcd2f2ca679e65024d83bd61debcb4b75bb18f3834a368454d574fd` - the SHA-256
the previous text was filed under - while the report still carried its filter,
because the reconstruction is derived from whatever the current text is.
[The PostgreSQL 17 suite script](#the-postgresql-17-suite-script).

#### Why naming the column cannot work in one text

A column reference is resolved when the statement is parsed, so no runtime
guard can protect it. `current_setting('server_version_num')`, a `CASE`, or an
`OR` that is never reached all fail the same way: the server rejects the
statement before it evaluates anything. The refusal this page recorded on
2026-09-09 arrives with no row read and no fixture built.

On this version the column exists, and `pg_stats_ext` derives it from the data
row's own key:

| Piece | Where |
|---|---|
| `sd.stxdinherit AS inherited` in the view | [system_views.sql#pg_stats_ext](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L277-L309), [system_views.sql:290](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L290) |
| the catalog column, and its place in the data row's unique key | [pg_statistic_ext_data.h:35](../../../../raw/postgres-17/src/include/catalog/pg_statistic_ext_data.h#L35), [pg_statistic_ext_data.h:57](../../../../raw/postgres-17/src/include/catalog/pg_statistic_ext_data.h#L57) |
| `ANALYZE` runs the plain pass, then a second pass when the table has children | [analyze.c#analyze_rel-passes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L246-L259) |
| each pass builds extended statistics under its own `inh` flag, stored as `stxdinherit` | [analyze.c#BuildRelationExtStatistics-call](../../../../raw/postgres-17/src/backend/commands/analyze.c#L604-L606), [extended_stats.c#BuildRelationExtStatistics](../../../../raw/postgres-17/src/backend/statistics/extended_stats.c#L111-L114), [extended_stats.c#statext_store](../../../../raw/postgres-17/src/backend/statistics/extended_stats.c#L790-L791) |

Reading the base catalogs instead is not an option for this statement: an
unprivileged reader may query `pg_statistic_ext` but not
`pg_statistic_ext_data`, which the view exists to mediate.
[system_views.sql#pg_statistic_ext_data-revoke](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L382-L383).

#### Why the replacement is exact where the column exists

`row_to_json` takes a `record` and emits one JSON key per non-dropped
attribute, named by `attname`; a boolean attribute is written as bare `true` or
`false`. `->>` is `json_object_field_text`, which returns `NULL` — not an error
— when the key is absent, and `'true'`/`'false'` cast back to boolean because
`boolin` accepts exactly those spellings.

| Step | Evidence |
|---|---|
| `row_to_json(record)` returns `json`, volatility stable | [pg_proc.dat#row_to_json](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L8975-L8977) |
| one key per attribute, `attisdropped` skipped, key from `NameStr(att->attname)` | [json.c#composite_to_json](../../../../raw/postgres-17/src/backend/utils/adt/json.c#L546-L579) |
| a boolean datum is written as `true` or `false` | [json.c#datum_to_json-bool](../../../../raw/postgres-17/src/backend/utils/adt/json.c#L212-L221) |
| `->>` on `json` is `json_object_field_text` | [pg_operator.dat#json-arrow-text](../../../../raw/postgres-17/src/include/catalog/pg_operator.dat#L3160-L3162), [pg_proc.dat#json_object_field_text](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L9078-L9081) |
| a missing key yields SQL NULL | [jsonfuncs.c#json_object_field_text](../../../../raw/postgres-17/src/backend/utils/adt/jsonfuncs.c#L881-L895) |
| `'true'` and `'false'` parse to boolean | [bool.c#parse_bool_with_len](../../../../raw/postgres-17/src/backend/utils/adt/bool.c#L36-L58), [bool.c#boolin](../../../../raw/postgres-17/src/backend/utils/adt/bool.c#L126-L150) |

So where the column exists the predicate is the same predicate, and where it
does not the `coalesce` admits the row — which is the correct reading on a
server that records one `ANALYZE` pass, because that pass is the plain one. The
first half of that sentence is measured below; the second half is measured on
the 12 leg, whose server reports thirteen `pg_stats_ext` columns and none named
`inherited`; the 2026-09-14 run read that column list again and it is
`schemaname, tablename, statistics_schemaname, statistics_name,
statistics_owner, attnames, kinds, n_distinct, dependencies,
most_common_vals, most_common_val_nulls, most_common_freqs,
most_common_base_freqs`.

#### What the old transformer cost, measured

The 12 leg used to make the text run by deleting the filter line. That widened
the CTE instead of preserving it, which this page carried as an open question
until now. The `extstat` stage settles it by scoring three texts — the filed
one, the previous one, and the widened one — on four fixtures in one database,
against a measured `REINDEX INDEX`.

The mechanism first. Because `extstat` takes `max(e.nd)`, admitting the
inherited row can only raise the whole-key distinct estimate, so the widened
text can only over-state the number of key groups, under-state deduplication,
and therefore under-report bloat. The two passes the fixtures store, whole-key
`n_distinct` from each:

| Fixture | Own pass | Inherited pass |
|---|---|---|
| `xpar`, low-cardinality child | 20 | 3,483 |
| `xpar2`, the same with 60 % of the parent deleted and vacuumed | 8 | 1,404 |
| `xpar3`, high-cardinality child | 20 | 28,610 |
| `xflat`, no children | 20 | none written |

The parent's own index contains only the parent's own rows, so the own pass is
the correct input in every row of that table. Scored:

| Fixture | Measured `REINDEX` | Filed text | Previous text | Widened text | `key_groups`, filed vs widened |
|---|---|---|---|---|---|
| `xpar_ab` | 0.0 | 0.8 | 0.8 | **2.7** | 20 vs 3,483 |
| `xpar2_ab` | 59.7 | 59.7 | 59.7 | **60.1** | 8 vs 1,404 |
| `xpar3_ab` | 0.0 | 0.8 | 0.8 | **-33.7** | 20 vs 28,610 |
| `xflat_ab` | 0.0 | 0.8 | 0.8 | 0.8 | 20 vs 20 |

Those are the 2026-09-16 run's readings, and every scored cell reproduces the
2026-09-14 filing; the equivalence check beside them returned **0 rows in both
directions in all three fixture databases** - 28 rows in `gate`, 104 in `suite`
and 7 in `xstat`, with the `extstat` CTE feeding 3 rows in `suite` and 4 in
`xstat`. The `xstat` count is 7 rather than the previous 4 because the proof
tables the no-defeat rule needs live in that database too; the four fixtures
are the same four. Neither the report filter nor the proofs can move this
comparison: all three texts are read through views that drop the report's
filtering, and the fixture it scores is maintained by one bracketed statement
whose `dead but not yet removable` count is 0.

Three findings, and the third is the reason this section reports a range rather
than a headline:

1. **The filed text and the previous text agree on every row of every fixture**,
   here and in the equivalence run below.
2. **The widened text differs on every inheritance parent and on none of the
   controls**, always in the under-reporting direction.
3. **The size of that error depends on the shape, not on the size of the
   `key_groups` error.** A 174x wrong group count moves the reading by 1.9
   points on `xpar_ab`, because a posting list's TID payload dominates the
   index either way; the same fixture with a high-cardinality child moves it
   34.5 points, because there the widened estimate crosses the boundary at
   which the model stops crediting deduplication at all and prices singleton
   tuples. The inherited estimate is also sample-dependent, so the widened
   text's error is not reproducible to the decimal while the filed text's 0.8
   is: five runs of the same `xpar` fixture read 3,500, 3,481, 3,498, 3,492 and
   3,486, moving the widened reading between 2.3 and 2.7, and 3,483 on
   2026-09-16 for a widened 2.7, while the filed text read 0.8 every time.
   [analyze.c#std_typanalyze-minrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1894).

The `wspf` floor column reads `-219.8` on all three fresh fixtures under all
three texts. That is the known floor behaviour on a deduplicating index, not
an effect of this change; see
[Scoring column for the partial-index contract](#scoring-column-for-the-partial-index-contract).

#### What it costs to run

`row_to_json(se)` serialises a whole `pg_stats_ext` row, including the
`most_common_vals` arrays the view's lateral already builds, once per candidate
join. Six interleaved runs of the two exact texts on the `suite` database of the
**2026-09-14 re-port run** - 314 B-tree indexes over 64,098 blocks and three
extended-statistics objects, with the statement still carrying its 1 MB filter
and `LIMIT 20` - measured 67.9 to 72.5 ms for the text as it then stood against
62.2 to 75.6 ms for the previous one, with the ranges overlapping and the
slowest run of the twelve belonging to the previous text. On this database the
difference is inside the noise; a database with many large `pg_mcv_list` objects
would be the place to re-measure it. The filter-removal run of the same day
re-ran the stage and wrote its own pairs to `out/extstat.txt`; the removal
changed the statement's own cost by nothing measurable, which
[What it cost](#what-it-cost) reports from the `cost` stage's six pairs.
[system_views.sql#pg_stats_ext](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L301-L307).

#### What the fix does not change

The two `pg_stats` joins still name `inherited` directly, and deliberately:
`pg_stats` projects it from `pg_statistic.stainherit` on this version, the 12
leg executes those joins as filed, and the refusal was only ever raised against
`pg_stats_ext`. Changing them would add cost and risk for nothing measured. The
statement tag also stays `wiki_btree_wasted_space_sweep_r2`, through this fix
and through the 2026-09-14 filter removal, because the model is unchanged in
both; what identifies a revision of the text is its SHA-256 baseline, which the
filter removal moved from `646df923…` to `4de245c5…` and which both scripts
check before use.
[system_views.sql#pg_stats-inherited](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L189-L194).

### Reproducing the measurements

Build 17.11 out of tree from the pinned checkout, which must stay read-only, and
run `initdb` with `--locale=C`. The documentation describes the VPATH form for
`configure` and the mandatory build directory for `meson setup`.
[installation.sgml#VPATH](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L427-L432),
[installation.sgml#meson-setup](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L2012-L2025).

Everything after that is in the two scripts under
[Measurement Script](#measurement-script). They extract the statement texts from
this page, build the mandatory suite's fixtures and score them against a
measured `REINDEX INDEX`. Until 2026-09-14 this section also carried a geometry
harness and a calibration fixture block of its own, and the acceptance stage
carried fresh sorted builds, defect fixtures, a compression pair, posting-tail
classes and a publication barrier. None of those is a fixture the mandatory
suite defines, so all of them were removed with the stages that ran them and
with the measurements they backed.

Both statement texts are installed as views with three edits and nothing else:
delete the two `SET` lines, project the internals the scorer reads immediately
before `FROM modelled` — the projection needs a comma appended to
`server_version_num`, or the first added name silently becomes its alias — and
drop the report's own filtering and ordering. That last edit covers two tails:
the current text's `WHERE NOT suppress_row` plus its terminated `ORDER BY`, and
the superseded text's `WHERE actual_bytes > 1024 * 1024 AND NOT suppress_row`,
`ORDER BY` and `LIMIT 20`. Privilege cases must run the filed text rather than a
view, because a view executes with its owner's privileges and would hide exactly
the effect under test.
[The current recommended statement](#the-current-recommended-statement),
[system_views.sql#pg_stats-visibility](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L268-L275).

### What remains unimplemented

- A per-attribute diagnostic projection that reports every input's provenance.
  The caveat strings name the condition, but not which attribute produced it,
  and the `suppress_row` terms withhold the row without saying which one fired.
- A capacity model for indexes whose key width varies across groups. One
  averaged width cannot represent an index whose groups have different base
  tuple sizes, because the posting capacity follows the tuple size through
  `floor((BTMaxItemSize - itupsz) / sizeof(ItemPointerData))`. No fixture in the
  suite builds that shape, so this page no longer states its size.
  [nbtdedup.c#_bt_dedup_save_htid-cap](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L510-L513).
- Any reading of the compressed stored width of a wide key. `index_form_tuple`
  compresses a varlena key wider than `TOAST_INDEX_TARGET` whose storage is
  `extended` or `main`, and no catalog records the compressed width, so the
  statement can only warn.
  [indextuple.c#index_form_tuple-compression](../../../../raw/postgres-17/src/backend/access/common/indextuple.c#L116-L138),
  [heaptoast.h#TOAST_INDEX_TARGET](../../../../raw/postgres-17/src/include/access/heaptoast.h#L63-L68).
- A block size other than 8192, and an alignment other than 8. Every number on
  this page comes from a build whose `pg_control_init()` reports
  `database_block_size` 8192 and `max_data_alignment` 8.
- Row-count fidelity of the fixture recipes. The numbered fixtures are rebuilt
  from this page's own requirement tables rather than from the scripts that
  first filed them, so a cell whose value depends on the exact population can
  differ from the 2026-08 figures; test 36, one key group of 100,000 TIDs
  against a 132-TID cap, is the clearest case.
- A group count for a multicolumn key with correlated columns. Without a
  `CREATE STATISTICS ... (ndistinct)` object the model multiplies per-column
  distinct counts, which reads `-320.0 %` on the gate's two-column fixtures; see
  [Multicolumn key groups without extended statistics](#multicolumn-key-groups-without-extended-statistics).

### Mandatory test review

**The suite is not defined here.** Its six fixture families, its five phases,
its three porting rules, its maintenance assumption, its `REINDEX INDEX` oracle
and its four verdict bands are defined once for this version in
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md),
and the numbered fixtures this page originated are catalogued there. Read that
page for what a test *is*; this section says only what is local to this page:
which of that suite's obligations the recommended statement has met, and where
this page's own runs depart from the shared definition.

**The 2026-09-14 re-port brought the fixtures back in step with that page**, and
it removed rather than rewrote what the page had built beyond it:

| Change on the concept page | What this page did on 2026-09-14 |
|---|---|
| tests 11, 11b and 38 retired as explicit deduplication controls (2026-09-12) | dropped the gate's `i_dupoff`, `i_text_off` and `i2_off` and the partial `p38`, with their `plan_add` rows and `pd38`'s place in the drain list |
| numbers 65, 67, 69, 106, 117, 121 and legs 113a and 113c retired as withheld-maintenance shapes (2026-09-12) | dropped `p65`, `p67`, `p69`, `x106`, `p117`, `p113a`, `p113c` and 121's `nz_k`, `nzb_k` and `i_trunc` on the 17 leg, and 1010 to 1012 on the 12 leg |
| the maintenance assumption: every churn is followed by `VACUUM ANALYZE` before the decide phase (2026-09-13) | added `VACUUM` then `ANALYZE` to the ten recipes that keep churn of their own - 64, 66, 92, 93, 94, 95, 98, 115, 118 and 119 - and said so in the fixture file's header |
| nothing: page-local fixtures are this page's own | removed the geometry, calibration and acceptance stages outright, at the asker's direction, with the sections that reported their numbers |
| `### The maintenance must not be defeated` (2026-09-15) | on 2026-09-16 turned every one of those statements into one bracketed `VACUUM (VERBOSE, ANALYZE)` with all four timeouts at 0, added the `maint`, `horizon` and `pageclass` tables and the four proofs, made the churn stage die rather than score a defeated fixture, and brought the drains, the census and even the `xstat` comparison's own fixture onto the same footing; see [The maintenance, proved not defeated](#the-maintenance-proved-not-defeated) |

Retired numbers are not reused, so the population is smaller rather than
renumbered: **101 numbered fixtures and 25 gate fixtures on the 17 leg**, where
the 2026-09-11 run scored 112 and 28, and **13 on the 12 leg** where it scored
19.

Obligations, restated in the shared suite's families, as the 2026-09-16
no-defeat run left them:

| Family | Fixtures here | State for the recommended statement |
|---|---|---|
| 1, the deduplication gate | 25 indexes on two 500,000-row tables in the `gate` database | **run and passed**, 25 of 25 `PASS`, 0 over-credit, 2 under-credits ([the gate, scored](#the-deduplication-gate-scored-against-the-current-statement)) |
| 2, partial indexes | tests 18-77 less the retired 38, 65, 67 and 69: 60 indexes | **run**: 42 `PASS`, 18 `FALSE NEGATIVE`, 17 of them withheld and one the `p31` threshold loss |
| 3, false-positive constructions | tests 78-85, eight fresh indexes, none churned | **run**: 6 `PASS`, 2 `CRITICAL FALSE POSITIVE` (`f84`, `f85`) |
| 4, false-negative constructions | tests 86-91 | **run**: 1 `PASS`, 5 `FALSE NEGATIVE`, one of them the `f91` threshold loss |
| 5, the change A-D controls | tests 92-112 less the retired 106: 20 indexes | **run**: 17 `PASS`, 2 `CRITICAL FALSE POSITIVE` (`i103`, `x109`), 1 `FALSE NEGATIVE` |
| 6, the drained queue and zero counts | tests 113-120 less the retired 117, keeping only leg b of 113: 7 indexes | **run**: 6 `PASS`, 1 `FALSE NEGATIVE`, lost to one caveat |

Three deviations from the shared definition remain, and they are this page's,
not the suite's:

- **The decision rule is this harness's.** The shared bands score a decision,
  and this statement is an estimator that reports a percentage rather than
  deciding. The harness turns it into a decision with the page's own published
  reading rule - a row must be reported and free of the five caveats
  [Reading the output](#reading-the-output) refuses to promote - plus a 50 %
  threshold on `wasted_space_pct_floor` that is a harness choice and appears
  nowhere in the statement. Size left that rule on 2026-09-14 with the
  statement's own 1 MB predicate; `over_1mb` survives in the `verdicts` view as
  an observation and decides nothing.
- **Rule 1's cut is made by an event trigger.** Rather than splitting each recipe
  into a build file and a churn file, the harness takes the baseline from a
  `ddl_command_end` trigger on `CREATE INDEX`, so a recipe whose churn follows in
  the same file is cut at the same point as one whose churn is the drain stage.
- **Family 1 keeps its own second oracle.** The metapage's
  `bt_metap().allequalimage` and the build's `DEBUG1` verdict are still read
  beside every gate fixture, because the credit decision they check is not a
  rebuild decision and the shared bands cannot see it.

Two further boundaries of this port are worth stating plainly. The maintenance
assumption is read with rule 1: the concept page names six recipes outright, and
66, 115 and 119 are treated as churned here because their inserts and updates
fall after the index build, which is where rule 1 cuts. And the assumption's
first part is satisfied by a foreground `VACUUM (VERBOSE, ANALYZE)` in the
fixture file, not by a launcher; the cluster still runs `autovacuum = off`,
which is the isolation the phases need. That stand-in is faithful because an
autovacuum worker calls the same `vacuum()` the SQL command reaches, and
because that routine vacuums each relation before it analyzes it, which leaves
`ANALYZE` as the last writer of every `reltuples` on the table. Since
2026-09-16 each of those statements also carries the four proofs the no-defeat
rule asks for, so the assumption is not merely asserted here.
[vacuum.c#ExecVacuum-vacuum](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L450-L451),
[vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650),
[autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3120-L3147),
[guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1450-L1457).

The text being scored is identified by hash rather than by prose: the two
fenced SQL blocks on this page and the superseded text extracted from revision
`f2d73b4` hashed to `4de245c5…`, `bfa7721f…` and `bffd166e…` on the
2026-09-16 no-defeat run, all three matching the baselines the scripts carry,
and the estimator text is byte-identical to the one 2026-09-14 scored. The estimator's baseline moved from `646df923…` with the removal, and
the reconstructed pre-2026-09-10 text moved with it, from `8acd531b…` to
`152f4172…`; the 12 leg reproduced that second hash and still found the pinned
12.2 server refusing that text.

The engine's own suites are not a test of this statement. `make check` runs the
core regression tests against a temporary installation inside the build tree,
and each contrib module's tests run from its own directory the same way; nothing
in them reads `wasted_space_pct`. The adjacent engine coverage they do provide
is the deduplication block of `btree_index.sql`.
[regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59),
[regress.sgml#contrib-suites](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L171-L195),
[installation.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L515-L522),
[btree_index.sql#deduplication-tests](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L186-L213).

### The maintenance, proved not defeated

**The concept page's rule `### The maintenance must not be defeated` arrived on
2026-09-15, after this page's last run, and this pass is the first to check
against it.** The rule's point is that part 3 of the maintenance assumption
forbids *skipping* the maintenance, while this rule forbids *sabotaging* it: a
`VACUUM` that runs, returns success and removes nothing leaves exactly the
shape the suite retired. Five states are forbidden on every table a fixture
touches, from its first churn statement until rule 3's census has finished - an
open transaction or held snapshot anywhere in the cluster, a prepared
transaction, a replication slot holding an `xmin`, a lock conflicting with
`ShareUpdateExclusiveLock` held while the statement runs, and a timeout short
enough to fire inside it. `VACUUM`'s own removal cutoff is what makes the first
three matter: `vacuum_get_cutoffs` takes `OldestXmin` from
`GetOldestNonRemovableTransactionId`, which folds in every backend's `xmin`,
and the horizon computation then takes the older of its answer and any slot's
`xmin`.
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md),
[vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122),
[procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815),
[procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902),
[twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26),
[vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052).

**What changed in the two scripts, and why.** Nothing about the statement under
test moved; the changes are all in how its fixtures are maintained and what the
run records about that.

| Change | Where | Why |
|---|---|---|
| Every maintenance statement is one `VACUUM (VERBOSE, ANALYZE)` instead of a `VACUUM` followed by a separate `ANALYZE` | both legs' fixture files and drains | `VERBOSE` is what makes proof 2 a number rather than a hope, and one statement keeps `ANALYZE` as the last writer of every `reltuples` on the table ([vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650)) |
| All four settable timeouts are `0` in every session that issues one, and the values in force are recorded per statement | both legs | the autovacuum worker forces the same four to `0` "to avoid letting these settings prevent regular maintenance from being executed"; the 12 leg zeroes three, because `transaction_timeout` does not exist there ([guc_tables.c#statement_timeout-and-lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2631), [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642), [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653), [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470)) |
| A `maint` table, a `horizon` table, a `pageclass` table, and `horizon_probe()`, `maint_begin()` and `maint_end()` | both legs' harness | so that every number above is a row someone can re-read rather than a line in a log |
| None of the three carries a primary key | both legs' harness | the estimator's candidate set is every B-tree index outside the system schemas, so a harness index in `public` enters the report the run is scoring |
| The `VERBOSE` output is parsed per table into a recorded count, with a version-local parse on each leg | both legs | 17.11 prints `tuples: X removed, Y remain, Z are dead but not yet removable`; 12.2 words the same fact differently, so each leg reads its own server's message text |
| The server log is searched for skip and cancellation lines after the run's own mark | both legs | proof 1: a statement that could not take its lock says so and returns success anyway ([vacuum.c#skip-lock-not-available](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L828-L860)) |
| `pgstatindex` reads the page classes of every planned index after the maintenance | both legs | proof 4, and the read is read-only, so the decide phase sees the state the maintenance left ([pgstatindex.c#page-classes](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L295-L320)) |
| The churn stage dies rather than score when a proof fails | both legs | the rule says a defeated fixture is repaired and re-run, not scored |
| The `xstat` comparison's own fixture is bracketed too | 17 leg | it is a page-local fixture rather than a suite one, but it issues a `VACUUM`, and then no maintenance statement in the run is unaccounted for |

`client_min_messages` stays at `warning` in those sessions and the `VERBOSE`
output still arrives, because `INFO` is exempt from that setting by
construction: `should_output_to_client` returns true when
`elevel >= client_min_messages || elevel == INFO`.
[elog.c#should_output_to_client](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L247-L264).

**What the run recorded, per leg.** The 17 leg's three databases and the 12
leg's one, on the pass of 2026-09-16:

| Proof | 17.11 | 12.2 |
|---|---|---|
| maintenance statements, and how many completed | `suite` 65 of 65, `gate` 2 of 2, `xstat` 1 of 1 | 9 of 9 |
| by source | `suite` 36 drain, 28 fixture, 1 prebuild; `gate` 2 drain; `xstat` 1 | 5 drain, 3 fixture, 1 extstat |
| `dead but not yet removable`, per statement | **0 on all 68** | **0 on all 9** |
| dead tuples left behind afterwards | max **0** in every database | max **0** |
| tuples the statements removed | 21,557,908 + 899,900 + 180,000 | 3,568,887 |
| horizon probes entirely clean | **71 of 71**, **4 of 4**, **1 of 1** | **11 of 11** |
| skip or cancellation lines in the log | **0** | **0** |
| distinct timeout sets in force | **1**: all four zero | **1**: all three zero |
| page classes after the maintenance | `suite` 101 indexes, 28 with deleted pages, 0 half-dead, **9,626** deleted pages; `gate` 25 indexes, 1 with deleted pages, **714** | 13 indexes, 5 with deleted pages, 0 half-dead, **15,794** |

The page classes are the rule's own illustration of what a pinned horizon would
have cost: deleted pages are what `_bt_pagedel` leaves behind once the entries
are gone, and a drained fixture whose index has none is the shape a defeated
`VACUUM` produces.
[nbtree.c#btbulkdelete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L820-L832),
[nbtpage.c#_bt_pagedel](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1801-L1815).

**What these proofs do not establish.** Three limits, stated rather than
glossed:

- The horizon reading is a probe beside each statement, not an interlock around
  it. Nothing in the run holds the cluster still between the probe and the
  `VACUUM`; the probe is evidence that no holder existed at that moment, on a
  cluster where the only sessions are this script's.
  [system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L878-L885),
  [system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017),
  [system_views.sql#pg_prepared_xacts](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L421-L427).
- A clean proof set says the maintenance did its work, not that the suite
  covers a database whose horizon *is* pinned. No fixture here builds that
  state, and the concept page says none may without being filed as its own
  numbered test.
- The 12 leg's `dead_after` and `mods_after` are read after a publication poll
  rather than on demand, because that server has no
  `pg_stat_force_next_flush()`; they are the collector's values at that
  moment, and the proof that matters there is the `VERBOSE` count, which comes
  from the statement itself.

### The mandatory suite, re-scored under the shared protocol

**Every fixture the suite still defines has been run under its five phases and
scored with its four bands, on both legs, against the statement with no report
filter but `NOT suppress_row`, and under the no-defeat rule for the first
time.** On 17.11: **101 numbered fixtures, 72 `PASS`, 4 `CRITICAL FALSE
POSITIVE`, 0 `FALSE POSITIVE`, 25 `FALSE NEGATIVE`**, and **25 gate fixtures,
25 `PASS`**. On 12.2, where the exact filed text runs unmodified: **13
fixtures, 11 `PASS`, 0 false positives of either severity, 2 `FALSE
NEGATIVE`**. One numbered fixture moved from the 2026-09-14 run, `p41`, and its
move is the `ANALYZE` sample rather than the model or the bands; nothing else
about the fixtures, the statement or the scoring changed.

Both servers were built out of tree from the pins and checked before a fixture
existed: 17.11 passed `make check` 225 of 225 plus 8, 1 and 3 for `pageinspect`,
`pgstattuple` and `amcheck`; 12.2 passed 192 of 192 plus 5, 1 and 2. All three
SHA-256 baselines matched, so the text scored is the filed text.
`Linux x86_64`, `max_data_alignment` 8, `database_block_size` 8192,
`autovacuum = off`, `fsync = off`. **0 unexpected server errors on either leg**,
with the 17 leg's one deliberate error and the 12 leg's two seen exactly once
each. Both legs also pass the four no-defeat proofs on every maintenance
statement; see
[The maintenance, proved not defeated](#the-maintenance-proved-not-defeated).
[regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59),
[installation.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L515-L522).

#### What the five phases produced

| Phase | 17.11 | 12.2 |
|---|---|---|
| build | 101 numbered fixtures in `suite`, 25 in `gate`, **0 build-contract failures** on either | 13 fixtures, 0 build-contract failures |
| baseline | 101 and 25 baselines, one per index, taken at the index build | 13 baselines |
| churn | each fixture's own churn, followed by one bracketed `VACUUM (VERBOSE, ANALYZE)`; 36 `suite` tables and both `gate` tables drained nine heap blocks in ten, each ending on the same statement | 5 tables drained; the rest kept their own churn |
| decide | the filed text, unmodified, read through the three documented harness edits | the same text, 0 transformer edits |
| oracle | a measured `REINDEX INDEX` on all 126; the statement called for one on **47** of the 101, and those gave back a mean **80.4 %** (0.0 to 98.9), while the 54 it declined averaged 41.9 %; in `gate` it called for all 25, mean **88.2 %** (85.7 to 89.9) | on all 13; the statement called for 9, which gave back a mean **89.9 %** (89.1 to 90.7), against 60.1 % over the four it declined |

**Rule 3's census is where the maintenance assumption shows.** In `suite` it
censused 86 tables and analyzed **2** - `f85t` at 20.0 % of its estimated rows
modified and `x108t` at 100.0 %, the two tables no churn touched - and found
**84 tables at zero modified rows**, because the maintenance `ANALYZE` had
already reset each churned table's counter. The highest `mod_pct` it left alone
is 0.0. In `gate` it censused 2 and analyzed 0. **On 12.2 it censused 9 and
analyzed 0**, where the 2026-09-14 run analyzed 2 at 896.6 % and 899.3 %: the
bracketed maintenance runs in a session of its own, after the drain's session
has exited and published its `DELETE` counts, so the `ANALYZE` half now resets
counters that have arrived instead of counters that arrive afterwards. That is
the publication order rule 3 asks for, reached on a server with no
`pg_stat_force_next_flush()`; the leg still waits for the drained live counts
after the census, because only an `ANALYZE` repairs an `n_live_tup` the drain
left at zero.
[autovacuum.c#anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3068-L3076),
[autovacuum.c#doanalyze](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095),
[guc_tables.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3367-L3375),
[guc_tables.c#autovacuum_analyze_scale_factor](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3906-L3914),
[system_views.sql#n_mod_since_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L689),
[pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L331-L338).

The drain selects survivors by block number out of the tuple's own `ctid`, so
the index loses entries from every leaf page rather than one contiguous run, and
the `VACUUM` that follows is what turns those dead entries into pages a rebuild
can give back.
[itemptr.h#ItemPointerData](../../../../raw/postgres-17/src/include/storage/itemptr.h#L36-L40),
[sysattr.h#SelfItemPointerAttributeNumber](../../../../raw/postgres-17/src/include/access/sysattr.h#L21),
[nbtree.c#btbulkdelete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L820-L832),
[nbtpage.c#_bt_pagedel](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1801-L1815).
Fixture 84's forged index count is applied after the census and survives it at
`reltuples = 5000` against a real 100,000, which is the point of ordering the
forgeries last: an `ANALYZE` of the table rewrites `reltuples` for the table and
for every index on it.
[analyze.c#totalindexrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L662),
[index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2809-L2830),
[index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3582-L3600).

#### Where the false negatives were lost

**Two of them are the arithmetic, and they are the same two the filter removal
exposed on 2026-09-14.** `expected_stage`, which recomputes the decision from
the internals the harness projects rather than from the reported percentage,
**agreed with the statement on all 101 fixtures**, so neither is a
disagreement between the statement and its own inputs; they are a model that
reads `-233.3` and `-248.6` where a rebuild gave back 79.2 % and 89.2 %.

| Lost by | Count | Mean reclaim a rebuild gave back | Range |
|---|---|---|---|
| `withheld` by an exclusion term | 22 | 83.9 % | 60.0 to 90.7 |
| the 50 % threshold | **2** | 84.2 % | 79.2 to 89.2 |
| a caveat the reading rule refuses to promote | 1 | 100.0 % | `p113b` alone |
| a size or rank cutoff | **0** | — | the statement has none |

35 rows were withheld in total, and every one of them names the term that
withheld it: 25 by `A: duplicates from table statistics`, 5 by `C:
variable-width INCLUDE`, 3 by `D: expression, no statistics row` and 2 by `A: no
statistics row`, with `withheld_unexplained` at 0. The single caveat loss is the
drained queue `p113b`, at `zero modelled rows: validate with a population probe`
on a file the rebuild emptied completely - the caveat working as designed and
the decision being wrong anyway. Its population probe answered `false`, which
is the correct answer for an empty subset.

The 31 fixtures the removed predicate used to withhold read as follows on this
run. **11 of the 31 are printed**, one more than on 2026-09-14, and the extra
one is `p41`: the exclusion terms withhold the other 20, and size was never
their reason.

| What the 31 under-1 MB fixtures do now | Count | Which, and what the oracle said |
|---|---|---|
| printed, decided `rebuild`, all `PASS` | 6 | `p19` at 240 KiB reading 83.3 % against a measured 83.3 %; `p22`, `p34`, `p42` at 67.0 % and `p36` at 65.5 % against 87.4 to 87.9 %; and `p41` at 936 KiB reading 74.4 % against 75.2 % |
| printed, declined, and wrong to decline | 2 | `p31` at 192 KiB and `f91` at 296 KiB, the two threshold losses above |
| printed, declined, and right to decline | 3 | `f88` at `-3291.9` against 40.5 %, `p116` at 0.0 % on an 8 KiB file, and `p120` at 87.5 % on 64 KiB against a measured 0.0 %, declined by the `zero modelled rows` caveat - the reading rule earning its keep |
| withheld by an exclusion term, so invisible | 20 | 17 of them `FALSE NEGATIVE`, plus `f81`, `f82` and `i104`, which `PASS` because a withheld row is not a decision |

The four critical false positives are the four rows a reader would have acted
on, and each returned nothing:

| Fixture | Reads | A rebuild gave back | Why |
|---|---|---|---|
| `f84` | 94.2 % | 0.0 % | the forged partial-index `reltuples` of 5,000 against a real 100,000 |
| `f85` | 70.7 % | 0.0 % | table statistics that predate an `UPDATE` widening every subset row |
| `i103` | 84.1 % | 0.0 % | a wide unique key inside the subset, which no statistic describes |
| `x109` | 62.5 % | 0.0 % | `attstattarget = 0` on the key column; the caveat fires but is not one of the five the reading rule refuses |

Accuracy, beside the decision, all three figures on
`wasted_space_pct_floor`: 57 of 101 readings are within one point of the
oracle, the worst over-estimate is `+94.2` on `f84` - the forged count above -
and the worst under-estimate `-3332.4` on `f88`, whose subset is far narrower
than the table average. The two next worst under-reads are `x111` at `-613.4`
and `i104` at `-507.9`, both width-model cases rather than row-count ones.
Neither the filter removal nor the no-defeat repair moved what the model
computes; `f88`'s distance from the oracle is the one figure here that visibly
wanders with the sample, at `-3259.4` on 2026-09-14 and `-3310.8` and `-3332.4`
on this pass's two runs, against readings of `-3270.3` and `-3291.9`.

#### The shared bands against the bands this page filed

Both scorings ran on the same 101 rows, and they disagree in both directions.

| Scoring | `PASS` | `CRITICAL FALSE POSITIVE` | `FALSE POSITIVE` | `FALSE NEGATIVE` |
|---|---|---|---|---|
| shared bands, decision-based | 72 | 4 | 0 | 25 |
| the same bands on 2026-09-14 | 71 | 4 | 0 | 26 |
| this page's older `verdict_floor` | 81 | 11 | 3 | 6 |
| this page's older `verdict_point` | 82 | 12 | 4 | 3 |

The older two rows read a percentage and never ask whether the row was reported
at all. That is why they count 11 and 12 critical false positives, most of them
on rows the report never shows - among reported rows only 5 remain under either
column - and 6 or 3 false negatives, because a withheld row is a separate
column there rather than a miss.

`want_stage`, the per-fixture prediction filed in the script text before the
run, was wrong 32 times on 101 and 4 times on 13, and it is left as filed: the
predictions are the 2026-09-14 re-port's, so the one-miss change is a
measurement and not a re-prediction. 28 of the 32 predicted a rebuild the
statement declined: 25 of those are the misses above, and three - `p73`, `p76`
and `f88` - are declines the oracle agreed with. The remaining four are the
reverse case, the critical false positives predicted `leave`.

#### What the 12.2 leg adds

The exact filed text executes on the pinned 12.2 server **unmodified**, with the
transformer reporting 0 edits, and the leg's version-local facts are measured
rather than assumed: `server_version_num` 120002, `block_size` 8192,
`max_data_alignment` 8, `pg_stat_force_next_flush()` absent, thirteen
`pg_stats_ext` columns with none named `inherited`, B-tree support function
numbers `1,2,3` with no 4, and `WITH (deduplicate_items = off)` rejected. All 13
fixtures therefore read `equalimage = ineligible` and none is credited, which is
the feature gate the concept page names rather than a defect. Its two false
negatives are one caveat loss (`p1005`, a drained queue at 100.0 %) and one
withheld row (`w_inc`, a partial index with a variable-width `INCLUDE` column at
90.7 %); 11 of the 13 readings are within one point of the oracle, the worst
over-estimate `+7.5` on `w_key` and the worst under-estimate `0.0`. The
`extstat` comparison still holds on this server: the filed text and the widened
one return identical rows in both directions over 20 rows read, while the
pre-2026-09-10 text is still refused with `column se.inherited does not exist`
at line 116.

**This leg cannot exercise the filter removal, and says so with numbers.** Not
one of its 13 fixtures is under 1 MB - the smallest index is 276 blocks - so
the under-1 MB listing in `verdicts12.txt` is empty and every verdict is
identical to the 2026-09-14 run's. The report a reader sees is unchanged too:
the filed text prints **19 rows on the settled `leg12` database, 6 of them
1 MB or smaller**, where the same text with the old predicate would have
printed 13. The `LIMIT 20` never bound here in either form.

**What the no-defeat repair did change here is the census and the proofs.** The
leg's 9 maintenance statements are bracketed like the 17 leg's, all 9 completed
at `dead but not yet removable` 0 with 11 of 11 horizon probes clean, its three
settable timeouts read `0`, and its 13 fixture indexes carry **15,794 deleted
pages** after the maintenance, 5 of them with any. Rule 3's census then
analyzed **0 of 9** tables rather than 2, because the drain's counts now reach
the statistics entry before the `ANALYZE` half resets them.

#### What it cost

The two exact texts, six interleaved pairs on the settled 17.11 fixture database
of 317 B-tree indexes over 64,103 blocks: the current text 77.1 to 97.6 ms, the
superseded one 52.1 to 63.4 ms. The database is three index files and five
blocks larger than the 2026-09-14 run's 314 over 64,098, and every one of the
three is a TOAST index the proof tables brought with them - the proof tables
themselves carry no index, which is why the **report** still prints 68 rows and
not 70. The `EXCEPT` attribution, taken before the first rebuild, returned
**26 rows in each direction**, one more than the previous run's 25, and the
probe generator emitted and executed **63 statements** in `suite`: 62 group
probes and one population probe. **No fixture scored `UNMEASURED`**, so no
index's `reltuples` reached the model as the `-1` sentinel. Wall clock on this
host, with both builds run concurrently at `JOBS=10`: about 1 min 45 s per
build, then **2 min 20 s** for the 17 leg's full run from a built tree - 50 s
of it `make check` - and **1 min 10 s** for the 12 leg, 35 s of it `make
check`, read from the output files' modification times rather than from a timer
in the scripts.

### What still needs to be tested

In priority order. Items 1 through 4 are the mandatory contract; the rest are
gaps the reviews found.

1. **The numbered suite against the current text.** Done again on 2026-09-16,
   under the five phases and four bands of
   [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
   and against the fixture set that page now defines, with every maintenance
   statement proved against its no-defeat rule: 126 fixtures on 17.11 and
   13 on 12.2, with the results and the 29 standing failures under
   [The mandatory suite, re-scored under the shared protocol](#the-mandatory-suite-re-scored-under-the-shared-protocol).
   What remains is not coverage but the remedy the contract asks for, filed
   under
   [The mandatory suite and the current statement](#the-mandatory-suite-and-the-current-statement).
   The pass criteria are step 9 of the procedure below, amended by
   [The deduplication gate, scored against the current statement](#the-deduplication-gate-scored-against-the-current-statement)
   to allow two under-credits.
2. **Attribution of every moved row.** Done on every run, and the requirement
   stands: install the superseded text (`bffd166e…`) beside the current one and
   run `EXCEPT` in both directions over the columns both views project, on the
   same fixture state, before any `REINDEX`. The 2026-09-16 run returned 26
   rows in each direction, and neither the removal nor the proofs can move any:
   both texts are read through views that drop the report's filtering, so the
   comparison sees the models and not the reports. A row that moves must be
   explained by one of the five
   changes named above; an unexplained move is a defect, and reading the halves
   apart - a moved number against a moved caveat string - is still done by hand.
3. **ICU.** Measured on every run since 2026-09-09, now including the
   partial-index legs: tests 51 and 52 build a deterministic and a
   nondeterministic ICU collation over the same subset, and the gate group
   measures the `ineligible` branch, its deterministic twin and the
   `text_pattern_ops` refusal under
   [The collation branch, measured with ICU](#the-collation-branch-measured-with-icu).
   What remains is a non-C locale for the cluster rather than for one column.
   [installation.sgml#ICU-default](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L170),
   [installation.sgml#ICU_CFLAGS](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L184-L193),
   [index.c#pattern-ops-collation-check](../../../../raw/postgres-17/src/backend/catalog/index.c#L826-L849).
4. **The 12.2 leg of test 17.** Done, three times over. The text filed until
   2026-09-10 named `pg_stats_ext.inherited`, and the 12.2 server refused it;
   the filed text now reads that flag through `row_to_json()` and **executes
   there unmodified**, with the transformer reporting zero edits. The leg still
   starts by executing the exact text and recording the outcome before any
   fixture is built, and its `extstat` stage re-runs the refused text to keep
   the refusal reproducible. The v12 companion page carries that version's build
   and publication notes.
   [system_views.sql#pg_stats_ext-inherited](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L290),
   [The portable extended-statistics filter](#the-portable-extended-statistics-filter),
   [The v12 publication protocol](../../../v12/questions/indexing/btree-index-bloat-core-sql-only.md#the-v12-publication-protocol),
   [V12 catalog, build and output compatibility](../../../v12/questions/indexing/btree-index-bloat-core-sql-only.md#v12-catalog-build-and-output-compatibility).
5. **Role coverage, now untested.** `stats_hidden` decides both a caveat and
   whether the missing-statistics term fires, and `pg_stats` filters an
   expression attribute's row by the index's owner-only ACL. The fixture that
   exercised it was the acceptance stage's `wiki_reader` role, which went with
   that stage on 2026-09-14, so **no fixture now reads the statement as anything
   but the owner**. Restoring the coverage means running the expression fixtures
   (`p48` to `p50b`, `x107` to `x112`, `np97` and the gate's four `i_expr_*`
   indexes) as a role holding only `SELECT` on the tables and recording which
   rows appear and with which caveat - inside the mandatory suite this time, or
   not at all.
   [system_views.sql#pg_stats-visibility](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L268-L275),
   [acl.c#column_privilege_check](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L2538-L2569).
6. **Fixture contract.** Partly done. Every fixture asserts its intended
   population at the end of the build phase, before rule 2's drain changes it,
   and the 2026-09-14 run reports **0 build-contract failures on either leg**.
   What is still not asserted is predicate membership, deletion fraction and
   duplicate groups per fixture. `pg_stat_force_next_flush()` precedes every
   `ANALYZE` and `VACUUM` on the 17 leg, including the maintenance step the
   concept page added, and the 12 leg polls in a fresh session instead because
   that function does not exist there.
   [pgstatfuncs.c#snapshot-and-flush-functions](../../../../raw/postgres-17/src/backend/utils/adt/pgstatfuncs.c#L1680-L1695),
   [stats.sql#forced-flush](../../../../raw/postgres-17/src/test/regress/sql/stats.sql#L101-L102).
7. **The scoring column.** The partial-index contract scores
   `wasted_space_pct_floor`; the floor is known to be unusable as a lower bound
   on a deduplicating index, where it reads `-319.1 %` on a gate fixture the
   point estimate reads `-0.4 %` on. The run records both columns and classifies
   each row twice; which column carries the verdict is the asker's decision,
   filed under
   [Scoring column for the partial-index contract](#scoring-column-for-the-partial-index-contract).
8. **Untested configurations.** A `--with-blocksize=16` or `32` build, because
   every geometry constant in the statement is derived from `block_size` and no
   run has checked the arithmetic at another size; a parallel build, which
   `btbuild` starts when `ii_ParallelWorkers > 0` and which still ends in
   `_bt_leafbuild`; a `CREATE INDEX CONCURRENTLY` and a `REINDEX CONCURRENTLY`
   build, which both reach `index_build` through `index_concurrently_build`; a
   partitioned table, whose per-partition indexes enter the candidate set as
   `relkind = 'i'` while the partitioned index itself is `'I'` and excluded, and
   whose `ANALYZE` expands to the partitions; and a non-C locale.
   `MAXIMUM_ALIGNOF` other than 8 and big-endian hardware are not available in
   this environment and stay open.
   [installation.sgml#--with-blocksize](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L1472-L1482),
   [nbtsort.c#btbuild-parallel](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L389-L392),
   [nbtsort.c#_bt_leafbuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L535-L571),
   [index.c#index_concurrently_build](../../../../raw/postgres-17/src/backend/catalog/index.c#L1533-L1539),
   [indexcmds.c#DefineIndex-concurrent-build](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1682),
   [indexcmds.c#ReindexRelationConcurrently-build](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L4009),
   [pg_class.h#relkind](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L164-L173),
   [vacuum.c#expand_vacuum_rel-partitions](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L963-L982),
   [analyze.c#analyze_rel-passes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L249-L259).
9. **Platform record.** Done: `Linux x86_64`, `max_data_alignment` 8,
   `database_block_size` 8192, read from `pg_control_init()` rather than
   assumed, and written to `out/platform.txt` with `uname -sm` on every run.
   [pg_proc.dat#pg_control_init](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L11989-L11997),
   [pg_controldata.c#pg_control_init](../../../../raw/postgres-17/src/backend/utils/misc/pg_controldata.c#L204).
10. **Cost.** Measured on every run, six interleaved pairs against the
    superseded text on the settled fixture database, and filed as a range rather
    than a single number under
    [What it cost](#what-it-cost). What is still missing is a database of
    several hundred indexes that is not this suite's own fixture set, and a
    database with many large `pg_mcv_list` objects, which is where
    `row_to_json(se)` would cost the most.

## Measurement Script

Two scripts produce every number this page reports, one per version leg:
`btree_bloat_suite_v17.sh` for 17.11 and `btree_bloat_suite_v12.sh` for the
12.2 cross-version leg. Both are filed in full below, in Bash and SQL only, and
both were last run end to end from their pins on **2026-09-16, on
Linux x86_64**, under the script text filed here and against the fixture set
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
now defines.

- The 17 leg backs
  [What the no-defeat re-run measured](#what-the-no-defeat-re-run-measured),
  [The maintenance, proved not defeated](#the-maintenance-proved-not-defeated),
  [The mandatory suite, re-scored under the shared protocol](#the-mandatory-suite-re-scored-under-the-shared-protocol),
  [The deduplication gate, scored against the current statement](#the-deduplication-gate-scored-against-the-current-statement),
  [The collation branch, measured with ICU](#the-collation-branch-measured-with-icu)
  and the 17-side half of
  [The portable extended-statistics filter](#the-portable-extended-statistics-filter).
- The 12 leg backs the cross-version half of those sections and
  [Cross-version execution of the revised statement](#cross-version-execution-of-the-revised-statement).
- Both scripts build only fixtures the mandatory suite defines. The page-local
  stages they carried until 2026-09-14 - `geometry`, `calibration` and
  `acceptance` - were removed with the sections that reported their numbers, so
  no figure on this page comes from a fixture the scripts no longer build.

### How to use the suite scripts

| Item | The 17 leg, `btree_bloat_suite_v17.sh` | The 12 leg, `btree_bloat_suite_v12.sh` |
|---|---|---|
| Purpose | measures the current estimator on a 17.11 server built from this page's pin: the 101 numbered fixtures and the 25 gate fixtures under the five phases of [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md), the portable-filter comparison, attribution, probes, the scoring pass against a measured `REINDEX INDEX`, and statement cost | answers whether the exact filed text executes on the pinned 12.2 checkout, records the refusal verbatim, then transforms, fixtures, churns and scores the constructible subset under the same five phases |
| Invocation | `bash btree_bloat_suite_v17.sh [stage ...]`, run from the repository root | `bash btree_bloat_suite_v12.sh [stage ...]`, run from the repository root |
| Stages | 14 stages plus `stop` and `clean`; see [the 17 leg's stages](#the-17-legs-stages) | 11 stages plus `stop` and `clean`; see [the 12 leg's stages](#the-12-legs-stages) |
| Proofs | checks the four proofs of `### The maintenance must not be defeated` on every maintenance statement and **dies rather than score** when one fails: no end stamp, a missing or non-zero `dead but not yet removable` count, a horizon probe with a holder, or a skip or cancellation line in the log | the same, with three timeouts instead of four |
| Environment | 7 variables, all with defaults; see [what the scripts read from the environment](#what-the-scripts-read-from-the-environment) | 7 variables, all with defaults; same table |
| Prerequisites | see [Prerequisites](#prerequisites) | the same, plus `-DTRUE=1 -DFALSE=0` in `EXTRA_CFLAGS` on a host whose ICU headers no longer define those macros |
| Output | under `$SANDBOX/out`; **open `criteria.txt` first**, and see [Reading the results of a run](#reading-the-results-of-a-run) for the file map and the result tables. The build and check diagnostics are copied there too, so they survive the build tree | under the same `$SANDBOX/out`; **open `v12_facts.txt` first**, then `verdicts12.txt`; this leg's copies carry a `12` in the name |
| Runtime | about 4 min for a full run on the 2026-09-16 host at `JOBS=10` - about 1 min 45 s of it `build`, 50 s `check` and 90 s for everything after them, so roughly 2 min 20 s from a built tree | about 2 min 20 s for a full run at `JOBS=10`, about 1 min 45 s of it `build`, 35 s `check` and 35 s the rest. Both legs were built concurrently on a 22-core host; on fewer cores the two `build` stages dominate |
| Cleanup | `bash btree_bloat_suite_v17.sh clean` stops the server cleanly with `pg_ctl -m fast -w stop`, confirms the teardown (no `postmaster.pid`, no postgres process on the data directory, an empty socket directory) and only then deletes `$SANDBOX`; `stop` does the first two and keeps everything. **`out/` is inside `$SANDBOX`, so copy it out before `clean`** — nothing else preserves a run's results | `bash btree_bloat_suite_v12.sh clean` stops the 12 server the same way and deletes only that leg's `build12`, `install12`, `data12` and `sock12`, because the 17 leg owns the shared `out/` and `sql/`. Run the 17 leg's `clean` last to remove the sandbox entirely |

Save the two fenced blocks below as `btree_bloat_suite_v17.sh` and
`btree_bloat_suite_v12.sh`, then run them from the repository root, because
`WIKI_ROOT` defaults to `$PWD` and both scripts resolve this page, both pinned
checkouts and the sandbox beneath it. The 17 leg also runs `git show` inside the
repository to recover the superseded statement text.

```sh
bash btree_bloat_suite_v17.sh                       # every stage, in order
bash btree_bloat_suite_v17.sh suite score criteria  # selected stages
bash btree_bloat_suite_v12.sh exact                 # just the 12.2 parse result
bash btree_bloat_suite_v17.sh clean                 # stop and delete the sandbox
```

#### The 17 leg's stages

Every stage is idempotent and re-runnable on its own once the stages it needs
have run. The default order is the order of this table.

| Stage | What it does | Needs first |
|---|---|---|
| `build` | configures the pinned checkout out of tree under `$SANDBOX/build17`, installs into `$SANDBOX/install17`, then builds and installs `pageinspect`, `pgstattuple` and `amcheck`; skips everything when the binary already exists. It copies `configure.log`, `make.log` and `install.log` into `out/` after every step, on the failure path too, because `clean` deletes the build tree; until the 2026-09-10 repair the copy ran only after a successful build | nothing |
| `check` | `make check` plus the three contrib checks, one result line each into `out/checks.txt`, then copies every `check_*.log` into `out/` and any `regression.diffs` as `out/diffs_*.txt`; before 2026-09-10 a failed suite left only its one-line summary once the sandbox was gone | `build` |
| `cluster` | `initdb --locale=C --encoding=UTF8`, writes the settings below into `postgresql.conf`, writes the current line count of `out/server.log` to `out/server.log.mark` (the point from which the server-error check reads), starts on `PORT`, records `uname -sm`, `max_data_alignment` and `database_block_size` into `out/platform.txt`, and creates the three UTF8 databases `gate`, `suite` and `xstat` | `build` |
| `texts` | extracts the two `sql` blocks of this page and the superseded text from `OLD_REV`, checks all three SHA-256 baselines, runs both exact texts as filed and records into `out/exact_rows.txt` how many rows each printed, installs the two harness views in `gate` and `suite`, and writes `sql/harness.sql`, the shared suite's plan, snapshot, result, scoring and verdict objects | `cluster` |
| `gate` | installs the harness, builds family 1's 25 fixtures, files them as 25 plan rows, and reads the as-built gate table with `bt_metap().allequalimage` and the build's `DEBUG1` verdicts as oracles | `texts` |
| `suite` | resets the `suite` schema, reinstalls the harness and both views, and runs the build phase of the 101 numbered fixtures: their baselines come from the harness event trigger on `CREATE INDEX`, each recipe that carries churn of its own ends on one bracketed `VACUUM (VERBOSE, ANALYZE)`, and `assert_built()` records each fixture's population while it is still as built. It scores nothing, and keeps its stderr in `out/suite_verbose.log`, which is where the churn stage reads the `VERBOSE` counts from | `texts` |
| `churn` | phase 3, in the order the shared suite prescribes: rule 2's uniform drain over the 36 `suite` tables and both `gate` tables that have no churn of their own, each ending on one bracketed `VACUUM (VERBOSE, ANALYZE)`, rule 3's census, which analyzes what a server with autovacuum on would still have analyzed, the catalog forgeries last so an `ANALYZE` cannot repair them, the four no-defeat proofs over every maintenance statement in `suite` and `gate`, the page classes those statements left, and a churned snapshot of every planned index. Writes `out/drain.txt`, `out/drain_verbose.log`, `out/census.txt`, `out/census_gate.txt`, `out/forge.txt`, `out/maint_proofs.txt`, `out/maint_skips.txt`, `out/pageclass_suite.txt`, `out/pageclass_gate.txt` and `out/snapshots.txt`. It dies rather than score when a proof fails | `suite`, `gate` |
| `extstat` | installs the harness in `xstat` so its own bloated fixture is maintained and proved like every other one, rebuilds the two texts the portable `extstat` filter replaced — `est_pre`, which must hash to `BASEPRE`, and `est_wide` — runs both, then compares all three over every database and scores them on an inheritance parent, a bloated inheritance parent and a childless control, into `out/extstat.txt`. It rebuilds indexes only in `xstat`, so the `suite` fixtures are still untouched when `attribution` runs | `texts`; it follows `suite` in the default order so that its equivalence counts and cost pairs see the populated `suite` database. Until 2026-09-10 it ran right after `texts`, where a fresh full run found `suite` empty |
| `attribution` | `EXCEPT` in both directions between the two texts, taken before any rebuild | `suite` |
| `probes` | runs the probe generator on `suite` and executes every statement it emits, still before any rebuild | `suite` |
| `score` | phases 4 and 5, in `suite` and then in `gate`: `CALL score_all()` reads both views on the churned fixture, runs the measured `REINDEX INDEX` and re-reads the size, then writes `out/verdicts.txt` and `out/verdicts_gate.txt` with the shared bands per family, the `expected_stage`/`taken_stage`/`want_stage` agreement counts, every `lost_by` row, one row per fixture under 1 MB with the decision and verdict it now gets, and the older `verdict_floor`/`verdict_point` counts beside them | `suite`, `churn` |
| `cost` | six interleaved timings of the two exact texts, the size of the database they ran against, the row count each text printed on it, and the same row set split on the 1 MB boundary the removed predicate tested | `texts` |
| `criteria` | the pass-criteria blocks into `out/criteria.txt`: block 2 is the shared suite's four bands and its phase counters for both databases, with the under-1 MB counts, the accuracy summary, one row per `lost_by` class, one per `withheld_by` term, the three worst under-reads and what each decision was worth; block 2b the older bands on the same rows; block 7, which reads every `ERROR`, `FATAL` and `PANIC` line of `out/server.log` after the mark, allows the one error this suite provokes on purpose - the gate's `text_pattern_ops` refusal - only when the `STATEMENT:` line of the same log record carries the statement that provokes it, prints how often it was seen, and dies on anything left over; and block 8, the no-defeat proofs per database and per maintenance source. Every query it runs is read-only, so it can be re-run after the oracle pass | `check`, `texts`, `gate`, `churn`, `attribution`, `score` |
| `report` | lists what landed in `out/` | nothing |
| `stop` | stops the server with `pg_ctl -m fast -w stop`, so the checkpointer writes a shutdown checkpoint and the next start needs no recovery, then confirms the teardown: no `postmaster.pid`, no postgres process on the data directory, an empty socket directory. It dies rather than report a stop that did not happen. Until 2026-09-10 it used `-m immediate`, which skips the checkpoint and forces crash recovery on restart | `cluster` |
| `clean` | `stop`, then deletes `$SANDBOX` after checking it is inside `$WIKI_ROOT/.wiki-runtime/tmp/`; because `stop` dies on a failed teardown, `clean` never deletes a live cluster | nothing |

#### The 12 leg's stages

| Stage | What it does | Needs first |
|---|---|---|
| `build` | 12.2 out of tree under `$SANDBOX/build12` with `CFLAGS="$EXTRA_CFLAGS"`, plus the same three contrib modules; copies `configure.log`, `make.log` and `install.log` into `out/` as `configure12.log`, `make12.log` and `install12.log` after every step, on the failure path too | nothing |
| `check` | the 12.2 core and contrib suites into `out/checks12.txt`, then copies each `check_*.log` into `out/` as `check12_*.log` and any `regression.diffs` as `diffs12_*.txt` | `build` |
| `cluster` | `initdb --locale=C --encoding=UTF8`, the same cluster settings without `log_min_messages`, the mark `out/server12.log.mark` written the same way, started on `PORT12`, and the `leg12` database | `build` |
| `exact` | extracts `sql` block 1, checks its hash, runs the text **unmodified**, and records `exact_text=executes` or `exact_text=refused` plus the first error lines and the row count it printed in `out/v12_facts.txt`. The database is empty at this point, so that count is 0 by construction and the settled one comes from `report` | `cluster` |
| `transform` | applies one recorded edit per refused construct, re-runs, writes `transform_edits`, and installs the harness view; it dies rather than guess when a construct is still refused | `exact` |
| `facts` | records `server_version_num`, block size, alignment, whether `pg_stat_force_next_flush()` exists, the `pg_stats_ext` columns, the registered B-tree support-function numbers, and whether `WITH (deduplicate_items = off)` is accepted | `cluster` |
| `fixtures` | builds the constructible subset, one writer session per step, polling `pg_stat_all_tables` for publication instead of forcing a flush; installs the same shared-suite harness, takes each baseline from its event trigger on `CREATE INDEX`, and records every fixture's as-built population and its filed `want_stage` | `transform` |
| `churn` | phase 3 on this leg: rule 2's drain over the five shape tables that have no churn of their own, each followed by one bracketed `VACUUM (VERBOSE, ANALYZE)`, rule 3's census, a wait for the drained live counts to publish - which has to come *after* the census, because only an `ANALYZE` repairs an `n_live_tup` the drain left at zero - the page classes, the four no-defeat proofs, and the churned snapshot. Writes `out/drain12.txt`, `out/census12.txt`, `out/maint_verbose12.log`, `out/maint_proofs12.txt`, `out/maint_skips12.txt`, `out/pageclass12.txt` and `out/snapshots12.txt`. It dies rather than score when a proof fails | `fixtures` |
| `score` | the same measured-`REINDEX INDEX` scoring under the shared bands, into `out/verdicts12.txt`, with the per-family counts, the stage-agreement totals, every `lost_by` row and one row per fixture under 1 MB - a listing that is empty on this leg, because none of its fixtures is that small | `fixtures`, `churn` |
| `extstat` | rebuilds the text filed before the portable `extstat` filter, checks it against `BASEPRE`, records that this server still refuses it, then scores the filed text against the widened one on an inheritance parent, a bloated inheritance parent and a childless control, into `out/extstat12.txt`, and re-checks the no-defeat proofs because it issues a maintenance statement of its own | `transform` |
| `report` | writes `out/v12_rows.txt`: the row count the filed text prints on the settled `leg12` database, that row set split on the 1 MB boundary, the accuracy summary and what each decision was worth. Then it rewrites the `server_errors` block at the end of `out/v12_facts.txt`, dropping the one an earlier run appended, with the same paired check against `out/server12.log` after its mark; the two errors this leg provokes on purpose are allowed from their own statements, anything left over kills the run; then prints the file | `facts`, and `score` for the two summaries |
| `stop` | stops the 12 server with `pg_ctl -m fast -w stop` and confirms the same three teardown facts, dying on any of them; `-m immediate` until 2026-09-10 | `cluster` |
| `clean` | `stop`, then deletes this leg's four directories after the same containment check | nothing |

#### What the scripts read from the environment

| Variable | Default | Read by | Meaning |
|---|---|---|---|
| `WIKI_ROOT` | `$PWD` | both | the repository root; everything else is resolved beneath it |
| `PAGE` | `$WIKI_ROOT/wiki/v17/questions/indexing/btree-index-bloat-core-sql-only.md` | both | the page the `sql` blocks are extracted from |
| `SANDBOX` | `$WIKI_ROOT/.wiki-runtime/tmp/btree-suite` | both | build, install, data, socket, SQL and output directories; the only tree either script writes |
| `JOBS` | `4` | both | `make -j` parallelism |
| `SRC` | `$WIKI_ROOT/raw/postgres-17` | 17 leg | the pinned 17 checkout, read only |
| `PORT` | `55437` | 17 leg | the 17 cluster's port |
| `OLD_REV` | `f2d73b4` | 17 leg | the revision of this page holding the superseded statement |
| `SRC12` | `$WIKI_ROOT/raw/postgres-12` | 12 leg | the pinned 12 checkout, read only |
| `PORT12` | `55412` | 12 leg | the 12 cluster's port |
| `EXTRA_CFLAGS` | `-O2 -g -DTRUE=1 -DFALSE=0` | 12 leg | `CFLAGS` for the 12.2 build; the two macro definitions are only needed against ICU 68 or newer |

Both scripts export `PGPORT`, `PGHOST` and `PGDATABASE` for their own `psql`
calls; those are written, not read, so a value in the caller's environment is
overridden rather than honoured.

#### Prerequisites

- A C toolchain and `make`. The recorded run used gcc 13.3.0 on `Linux x86_64`.
  Both legs build their own server; no installed PostgreSQL is used or needed.
- Development headers for ICU, readline and zlib, because both legs configure
  `--with-icu --with-readline --with-zlib` and the gate's nondeterministic
  collation cases need ICU. On a host where ICU is off the default search path,
  pass `ICU_CFLAGS` and `ICU_LIBS` to `configure`.
  [installation.sgml#ICU_CFLAGS](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L184-L193),
  [installation.sgml#--enable-debug](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L1530-L1540).
- The two pinned checkouts, at `raw/postgres-17` and `raw/postgres-12`. Both
  stay read-only: each build is a VPATH build under `.wiki-runtime/tmp/`.
  [installation.sgml#VPATH](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L427-L432).
- `git`, with `OLD_REV` (`f2d73b4`) reachable, since the 17 leg recovers the
  superseded statement with `git show`.
- `sha256sum`, and a Bash new enough for arrays and `${var:-default}`. Nothing
  else: no Python, no `awk`, no `perl`, no `jq`.
- Free TCP ports 55437 and 55412, or `PORT`/`PORT12` set to free ones. Both
  clusters listen on a Unix socket inside the sandbox and set
  `listen_addresses = ''`, so the port is reserved but never bound on TCP.
- `pageinspect`, `pgstattuple` and `amcheck`, built and installed from the same
  tree as the server, into the disposable cluster only. The gate reads
  `bt_metap()` and `bt_page_items()`; `pgstattuple` and `amcheck` are built and
  checked but no stage reads them since the acceptance stage went, so a run that
  drops them from both `build` and `check` measures the same numbers.
  [pageinspect--1.8--1.9.sql#bt_metap](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L73-L82),
  [pgstattuple--1.4.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4.sql#L19-L31).
- `initdb --locale=C`, which the fixtures assume, and UTF8 databases, which ICU
  requires: a `SQL_ASCII` database answers
  `current database's encoding is not supported with this provider`.
  [initdb.sgml#--locale](../../../../raw/postgres-17/doc/src/sgml/ref/initdb.sgml#L281-L291),
  [installation.sgml#ICU-default](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L170).
- Disk for two source builds, two clusters and the fixtures. The 2026-09-14 run
  left 314 B-tree indexes over 64,098 blocks in the 17 leg's `suite` database
  after the scoring rebuilds.
- On a host without `pkg-config`, or with ICU off the default search path,
  export `ICU_CFLAGS` and `ICU_LIBS` before either script; `configure` reads
  both from the environment and then needs no `pkg-config`. On macOS, Apple's
  command-line tools supply the compiler, `make`, `bison`, `flex` and `perl`,
  `sha256sum` ships at `/sbin`, and the documentation's warning that System
  Integrity Protection breaks `make check` unless `make install` runs first does
  not bite, because both `build` stages install before `check` runs.
  [installation.sgml#ICU_CFLAGS](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L184-L193),
  [installation.sgml#SIP](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L3611-L3618).

Every statement either script sends is disposable. The fixtures create and drop
tables, indexes, operator classes, collations and, in the `suite` database, the
whole `public` schema; the `clean` stages delete the cluster.
Never point `PORT`, `PORT12` or `PGHOST` at a cluster anyone cares about.

### How to run the suite against the current statement

Every step below was designed against the pinned source and the harness this
page filed on 2026-08-19 and 2026-08-24. The two scripts filed under
[The PostgreSQL 17 suite script](#the-postgresql-17-suite-script) and
[The PostgreSQL 12 leg script](#the-postgresql-12-leg-script) implement this
protocol, and both were executed on 2026-09-09; run them rather than these steps
by hand. The checkout under `raw/postgres-17/` stays read-only: the build is a
VPATH build in a directory under `.wiki-runtime/tmp/`, which is the form the
documentation describes.
[installation.sgml#VPATH](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L427-L432).

**1. Build and check.** Configure with ICU, which is on by default, and with
debugging symbols; run the core suite and the three contrib suites the oracles
need. On a host where ICU is not on the default search path, pass `ICU_CFLAGS`
and `ICU_LIBS` as the documentation shows.
[installation.sgml#ICU_CFLAGS](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L184-L193),
[installation.sgml#--enable-debug](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L1530-L1540),
[regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59),
[regress.sgml#contrib-suites](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L171-L195).

```sh
mkdir -p .wiki-runtime/tmp/btree17r/build && cd .wiki-runtime/tmp/btree17r/build
../../../../raw/postgres-17/configure --prefix="$PWD/../install" \
    --enable-debug --without-readline --without-zlib
make -j8 && make check
for m in pageinspect pgstattuple amcheck; do
  make -C contrib/$m && make -C contrib/$m check
done
make install
for m in pageinspect pgstattuple amcheck; do make -C contrib/$m install; done
```

**2. Cluster.** Initialise with `--locale=C`, then start with the settings
below. The context column is each GUC's definition in the pinned table, and it
decides how a later change is applied.
[initdb.sgml#--locale](../../../../raw/postgres-17/doc/src/sgml/ref/initdb.sgml#L281-L291).

| Setting | Value | Context | Scope of a change |
|---|---|---|---|
| `autovacuum` | `off` | `PGC_SIGHUP` | reload; set before the first fixture so no background `ANALYZE` repairs one mid-test |
| `fsync` | `off` | `PGC_SIGHUP` | reload |
| `shared_buffers` | `512MB` | `PGC_POSTMASTER` | restart |
| `maintenance_work_mem` | `256MB` | `PGC_USERSET` | session or transaction |
| `max_parallel_maintenance_workers` | `0` for the suite, `2` for the parallel-build case | `PGC_USERSET` | session or transaction |
| `client_min_messages` | `debug1` around `CREATE INDEX` in the gate harness | `PGC_USERSET` | session or transaction |
| `default_statistics_target` | `1` for fixture 120 only | `PGC_USERSET` | session or transaction |
| `statement_timeout`, `lock_timeout` | `600s` and `2s` in the scoring session; **`0` in every session that issues a maintenance statement**, with `transaction_timeout` and `idle_in_transaction_session_timeout` at `0` there too | `PGC_USERSET` | session or transaction |

[guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1450-L1453),
[guc_tables.c#fsync](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1097-L1100),
[guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2262-L2265),
[guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2466-L2469),
[guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3410-L3413),
[guc_tables.c#client_min_messages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4777-L4780),
[guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2071-L2074),
[guc_tables.c#statement_timeout-and-lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2631).

**3. Statement texts.** Extract the estimator block from this page and the
superseded block from the page's previous revision, verify both hashes, and
install each as a view with the harness edits this page documents: drop the
report's filtering and ordering, project `suppress_row` instead of filtering on
it, and project the internals the scorer reads (`expected_blocks`,
`floor_blocks`, `actual_bytes`, `live_rows`, `slot`, `leaf_cap`, `nmax`,
`dedup_applies`, `is_partial`, `equalimage_state`, `stats_row_missing`,
`dedup_credited`, `stats_stale`). The two texts have different tails since
2026-09-14 - the current one ends on `WHERE NOT suppress_row` and an `ORDER BY`
line carrying the semicolon, the superseded one on the 1 MB filter, an
unterminated `ORDER BY` and `LIMIT 20;` - so `harness_view` handles both and
whichever line carries the semicolon emits it. Run each exact text once as
filed to prove it executes, and record the row count it printed: on a settled
database that count is the whole visible effect of the removal. The 2026-09-14
filter-removal run reproduced all three hashes.

Extraction is Bash only, using the same `md_block` helper the scripts define, so
no `awk` and no `shasum` — the first is forbidden by `MANDATORY Measurement
Script` and the second is a Perl program. `sha256sum` from coreutils is the
digest tool both scripts use.

```sh
# Paste the md_block function from the 17 leg script below into the shell first;
# stage_texts does exactly this, for both blocks at once.
page=wiki/v17/questions/indexing/btree-index-bloat-core-sql-only.md
md_block sql 1 "$page" > est_r2.sql
sha256sum est_r2.sql   # 4de245c5a1fb442cda800c099b8801bc72abc0c87f170384490079135fb5241d
git show "f2d73b4:$page" > old_page.md
md_block sql 1 old_page.md > est_old.sql
sha256sum est_old.sql  # bffd166e44a4e81c181df3d9a10bfb547a6dcaf7349c2cd055578f35050d1357
```

**4. Fixtures.** Build exactly the fixtures
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
defines, and no others: the numbers it retired are not built, and every recipe
that churns ends on the maintenance statement before the decide phase. That
statement is one `VACUUM (VERBOSE, ANALYZE)`, bracketed so the run can prove it
was not defeated, in a session whose four settable timeouts are `0`; see
[The maintenance, proved not defeated](#the-maintenance-proved-not-defeated).
Give every fixture an assertion of its intended population, and call
`pg_stat_force_next_flush()` before every `ANALYZE` and `VACUUM`. In
`CREATE INDEX`, `WITH (fillfactor = ...)` precedes `WHERE`.
[gram.y#IndexStmt](../../../../raw/postgres-17/src/backend/parser/gram.y#L8093-L8095).

**5. Score.** One procedure per index, in this order: assert the population,
record `pg_relation_size`, read both views, `REINDEX INDEX`, record the size
again. The `res` table is the 2026-08-19 harness's with `modelled_rows`,
`key_groups` and `idx_reltuples` as `numeric` and three added columns,
`wasted_space_bytes numeric`, `equalimage text` and `reltuples_writer text`.
The verdict query classifies each row on both columns, replaces the
2026-08-19 rule's unclassified band with an explicit five-point margin, and
adds an `alertable` column that applies this page's reading rule: a row is
alertable only when its `caveats` string contains none of `never analyzed`,
`row-count sources disagree`, `statistics not visible`, `zero modelled rows`
and `wide compressible key`.

```sql
SET /* wiki_btree_mandatory_verdict_statement_timeout */ statement_timeout = '30s';
SET /* wiki_btree_mandatory_verdict_lock_timeout */ lock_timeout = '2s';

SELECT /* wiki_btree_mandatory_verdict */
       num, idx, blocks_before, blocks_after, a.actual, wsp, wspf,
       v.verdict_point, v.verdict_floor,
       (caveats IS NULL OR caveats !~ '(never analyzed|row-count sources disagree|statistics not visible|zero modelled rows|wide compressible key)')
                                                          AS alertable,
       caveats, equalimage
  FROM res
  CROSS JOIN LATERAL (
        SELECT round(100.0 * (size_before - size_after) / greatest(size_before, 1), 1) AS actual) a
  CROSS JOIN LATERAL (
        SELECT CASE WHEN wsp IS NULL THEN 'UNMEASURED'
                    WHEN wsp >= 50 AND a.actual < 10 THEN 'CRITICAL FALSE POSITIVE'
                    WHEN wsp >= 50 AND a.actual < 45 THEN 'FALSE POSITIVE'
                    WHEN wsp >= 50 AND wsp - a.actual > 5 THEN 'FALSE POSITIVE'
                    WHEN wsp <  45 AND a.actual >= 50 THEN 'FALSE NEGATIVE'
                    ELSE 'PASS' END                        AS verdict_point,
               CASE WHEN wspf IS NULL THEN 'UNMEASURED'
                    WHEN wspf >= 50 AND a.actual < 10 THEN 'CRITICAL FALSE POSITIVE'
                    WHEN wspf >= 50 AND a.actual < 45 THEN 'FALSE POSITIVE'
                    WHEN wspf >= 50 AND wspf - a.actual > 5 THEN 'FALSE POSITIVE'
                    WHEN wspf <  45 AND a.actual >= 50 THEN 'FALSE NEGATIVE'
                    ELSE 'PASS' END                        AS verdict_floor) v
 ORDER BY num;
```

Oracles are read beside each row and never scored: `bt_metap().allequalimage`
against `equalimage`, the `DEBUG1` line from the build, `count(tids) > 0` over
`bt_page_items` for posting lists, `pgstatindex` for density, and
`bt_index_check` after any support-function mutation in test 16, because it
raises when the metapage disagrees with the current catalog.
[pageinspect--1.8--1.9.sql#bt_metap](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L73-L82),
[pageinspect--1.8--1.9.sql#bt_page_items](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L109-L118),
[btreefuncs.c#bt_metap-allequalimage](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L916-L921),
[pgstattuple--1.4.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4.sql#L19-L31),
[amcheck--1.0--1.1.sql#bt_index_check](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.0--1.1.sql#L12-L28),
[verify_nbtree.c#metapage-equalimage-check](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L380-L396).

**6. Attribution.** Before the first `REINDEX`, run `SELECT ... FROM est_r2
EXCEPT SELECT ... FROM est_old` and its reverse over the columns both views
project, and keep every returned row with the change that explains it. This is
the same proof the 2026-08-20 and 2026-08-24 runs used, and it is what turns a
new verdict table into a regression result.

**7. Probes.** Run the generator from [Validation probes](#validation-probes)
on the fixture database, execute each emitted statement, and record its result
beside the row. On 2026-09-16 it emitted 63 statements: 62 group probes, each a
count within the sampling error of `key_groups`, and one population probe, on
the drained queue `p113b`, which answered `false`.

**8. The 12.2 leg.** Build the pinned 12 checkout the same way, execute the
exact current text, and record the outcome as a result in its own right. Only
if it executes, run the transformer that drops the constructs 12 lacks and score
the constructible subset against a measured `REINDEX INDEX`.

**9. Pass criteria.** The suite passes for the current text when all of the
following hold:

- Gate group: no index is credited that the metapage says was not
  deduplicated; the under-credits are `i_ei_true` and `i_squat`; `equalimage`
  agrees with `bt_metap().allequalimage` on every `recognized` and `ineligible`
  row; no fixture reads above 30 % on either column.
- Partial group: no critical false positive among reported rows on the chosen
  column; the true detections (68, 74, 77 and the corrected 75) are reported
  within five points; every withheld row names the term that withheld it.
- Controls: 113b reads 100.0; every `modelled_rows = 0` row carries
  `zero modelled rows` and has a recorded probe result; `x109` and `i103` are
  filed as residual false positives rather than passed silently.
- Every `EXCEPT` row is attributed to one of the five changes.
- Both exact texts execute as filed, and no row raises an error.
- Report shape: the filed text prints every candidate the exclusion terms do
  not withhold, and the run records how many of those rows are 1 MB or
  smaller. A run that prints at most 20 rows, or none under 1 MB, has not
  exercised the 2026-09-14 removal and must say so.
- Every maintenance statement passes the four proofs of
  `### The maintenance must not be defeated`: it completed, its own
  `dead but not yet removable` count is zero, no horizon probe beside it found
  a backend with an `xmin`, a replication slot or a prepared transaction, and
  the page classes it left are recorded. A run with one failure scores nothing
  and says so.
- `make check` and the three contrib checks pass; both block hashes match;
  `scripts/wiki_lint` reports no new issue.

**10. Filing.** The measured verdicts are filed under
[The mandatory suite, re-scored under the shared protocol](#the-mandatory-suite-re-scored-under-the-shared-protocol),
with the platform record item 2 writes to `out/platform.txt`: `uname -sm`,
`max_data_alignment` and `database_block_size`, the three facts every geometry
constant assumes. The sandbox lives under `.wiki-runtime/tmp/` and is deleted or
kept as the asker directs.

### The two suite scripts, and the rules they follow

**Both scripts are filed in full below, and both were last run end to end on
2026-09-16.** They turn
[How to run the suite against the current statement](#how-to-run-the-suite-against-the-current-statement)
into two files. `btree_bloat_suite_v17.sh` builds 17.11 out of tree from the
pin, runs the engine suites, and then runs the mandatory suite — family 1's 25
gate fixtures, the 101 numbered fixtures, the portable-filter comparison, the
`EXCEPT` attribution, the validation probes, the scoring pass and the cost
comparison. `btree_bloat_suite_v12.sh` runs step 8, the cross-version leg,
against the pinned 12 checkout. They are Bash and SQL only: no Python, no
`awk`, no external harness, so a reviewer needs a compiler, a shell and this
page.

Sixteen rules hold in both scripts. Two were added by the measurement-script
audit of 2026-09-09, three by the 2026-09-11 re-score against the shared suite,
one by the 2026-09-14 re-port, one was rewritten the same day by the filter
removal, and the last arrived on 2026-09-16 with the no-defeat rule.

| Rule | How the scripts keep it |
|---|---|
| The pinned checkout stays read only | every artifact goes under `SANDBOX`, default `.wiki-runtime/tmp/btree-suite`, and the build is the VPATH form the documentation describes. [installation.sgml#VPATH](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L427-L432) |
| The statement under test is never retyped | `md_block` extracts a fenced block from this Markdown file in pure Bash, and `git show` recovers the superseded text from revision `f2d73b4`; all five SHA-256 baselines are checked before use |
| The exact filed text runs first | each text executes exactly as filed before any harness view exists - the current one with `NOT suppress_row` as its only filter and no `LIMIT`, the superseded one with its 1 MB filter and `LIMIT 20` - and the row count each printed is recorded |
| Only the three documented edits are applied | `harness_view` drops the two `SET` lines, projects the internals the scorer reads, and drops the report's own filtering and ordering, from either tail. Nothing else is rewritten. [The current recommended statement](#the-current-recommended-statement) |
| Statistics are published before they are read | `pg_stat_force_next_flush()` precedes every `ANALYZE` and `VACUUM` on the 17 leg, and no fixture is read inside the transaction that built it. [pgstat.c#pgstat_force_next_flush](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L700-L708), [pgstat_relation.c#pgstat_report_analyze](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L289-L337) |
| Attribution and probes run before the first rebuild | the fixture stage only builds and plans, the churn stage only disturbs; `EXCEPT` and the probe generator run next; the scoring pass is the first thing that rebuilds an index. [indexcmds.c#ReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2804-L2829), [index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3583-L3597) |
| The suite is not redefined here | the families, the five phases, the three porting rules, the `REINDEX INDEX` oracle and the four verdict bands come from [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md); the scripts implement them and name every deviation under [Mandatory test review](#mandatory-test-review) |
| Every fixture asserts its own population | the `plan` table carries a counting query and the intended row count, `assert_built()` evaluates it at the end of the build phase - before rule 2's drain changes it - and `verdicts.contract_ok` is false when they disagree |
| The baseline is taken at the index build | a `ddl_command_end` event trigger on `CREATE INDEX` writes the `built` snapshot, so rule 1's cut lands at the same point whether the churn follows in the same file or in the churn stage, and `ON CONFLICT DO NOTHING` keeps a fixture's own `REINDEX` and the oracle rebuild from overwriting it |
| Forgeries outlive the census | fixture 84's forged count is written by the churn stage after rule 3's census, because an `ANALYZE` of the table rewrites `reltuples` for the table and every index on it. [analyze.c#totalindexrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L662) |
| Oracles are read beside each row and never scored | `bt_metap().allequalimage` for the gate, the build's `DEBUG1` line, and posting lists in `bt_page_items`. [btreefuncs.c#bt_metap-allequalimage](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L916-L921), [nbtutils.c#_bt_allequalimage-debug](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5172-L5180), [pageinspect--1.8--1.9.sql#bt_page_items](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L109-L118) |
| Stages are selectable and idempotent | `bash btree_bloat_suite_v17.sh gate score` runs two stages; a second run reuses the build and the cluster, and the suite stage resets its schema and reinstalls the harness and both views before rebuilding its fixtures. The gate stage drops each custom **operator family** rather than only its operator class, because a second run of it otherwise dies on `duplicate key value violates unique constraint "pg_amproc_fam_proc_index"`; that is the defect the 2026-09-11 run hit first |
| No `psql` error passes without a non-zero status | every helper carries `-X -v ON_ERROR_STOP=1`. `-X` keeps a stray `~/.psqlrc` out of the result; `ON_ERROR_STOP` is what makes a failed statement inside a `-f` script exit non-zero at all, because `MainLoop` only sets a failure status when `die_on_error` is set from it. [mainloop.c:376](../../../../raw/postgres-17/src/bin/psql/mainloop.c#L376), [mainloop.c#die_on_error](../../../../raw/postgres-17/src/bin/psql/mainloop.c#L587-L594), [psql-ref.sgml#Exit-Status](../../../../raw/postgres-17/doc/src/sgml/ref/psql-ref.sgml#L627-L636) |
| Nothing outside the sandbox is deleted | both `clean` stages check that the directory they are about to remove is inside `$WIKI_ROOT/.wiki-runtime/tmp/` and refuse otherwise, so a stray `SANDBOX` cannot turn `rm -rf` loose |
| Only fixtures the suite defines are built | the retired numbers are not built and not reused, and each removal is recorded in place in the fixture file; every recipe that churns ends on the maintenance `VACUUM ANALYZE`, so no fixture reaches the decide phase unvacuumed or unanalyzed |
| No maintenance statement is taken on trust | each one is a single `VACUUM (VERBOSE, ANALYZE)` between `maint_begin()` and `maint_end()`, in a session with every settable timeout at `0`, and the run records its completion, its own `dead but not yet removable` count, the horizon holders when it started and the page classes it left; the churn stage dies rather than score a fixture whose maintenance was defeated. [The maintenance, proved not defeated](#the-maintenance-proved-not-defeated) |

Neither script contains a Markdown fence: `md_block` assembles the three
backticks from `printf '\140'`, so each script can live inside the fenced block
that publishes it and still extract blocks from this page.

**The order of this page's fenced `sql` blocks is load-bearing.** `md_block sql
N` counts fenced `sql` blocks from the top of the file, so block 1 is the
estimator and block 2 the probe generator. Blocks 3 and 4 used to be the
geometry and calibration harnesses; both went on 2026-09-14 with the stages that
ran them, which is why the scripts now check three baselines rather than five.
Inserting a new `sql` block above either surviving block silently repoints the
scripts at the wrong text, and the baselines are the guard: `out/hashes.txt`
shows `DIFFER` and every number below it is about a different statement. When
this page gains SQL, put the block after the probe generator, or re-baseline
deliberately.

The stages, in default order:

| Script | Stages |
|---|---|
| `btree_bloat_suite_v17.sh` | `build check cluster texts gate suite churn extstat attribution probes score cost criteria report`, plus `stop` and `clean` |
| `btree_bloat_suite_v12.sh` | `build check cluster exact transform facts fixtures churn score extstat report`, plus `stop` and `clean` |

The 17 leg's `extstat` runs after `suite` rather than right after `texts`, so
its equivalence counts and cost pairs see a populated database; `geometry`,
`calibration` and `acceptance` stood between `texts` and `suite` until
2026-09-14 and are gone from both the list and the script.

The cluster the 17 script writes uses the settings
[How to run the suite against the current statement](#how-to-run-the-suite-against-the-current-statement)
prescribes. They are written into `postgresql.conf` before the first start, so
each is in effect from startup; the apply scope below is what a *later* change
to that setting would need.

| Setting | Value | Context | Scope of a later change |
|---|---|---|---|
| `autovacuum` | `off` | `PGC_SIGHUP` | reload. [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1450-L1453) |
| `fsync` | `off` | `PGC_SIGHUP` | reload. [guc_tables.c#fsync](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1097-L1100) |
| `listen_addresses` | `''`, so the cluster is reachable only through the sandbox socket | `PGC_POSTMASTER` | restart. [guc_tables.c#listen_addresses](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4437-L4441) |
| `port` | `PORT`, default `55437`, and `PORT12`, default `55412` | `PGC_POSTMASTER` | restart. [guc_tables.c#port](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2394-L2397) |
| `logging_collector` | `off`, so `pg_ctl -l` keeps every line in one file the run can grep | `PGC_POSTMASTER` | restart. [guc_tables.c#logging_collector](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1641-L1644) |
| `shared_buffers` | `512MB` | `PGC_POSTMASTER` | restart. [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2262-L2265) |
| `maintenance_work_mem` | `256MB` | `PGC_USERSET` | session or transaction. [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2466-L2469) |
| `max_parallel_maintenance_workers` | `0` | `PGC_USERSET` | session or transaction. [guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3410-L3413) |
| `log_min_messages` | `debug1` | `PGC_SUSET` | session, and only for a superuser or a role granted `SET` on it. [guc_tables.c#log_min_messages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4873-L4877) |
| `unix_socket_directories` | the sandbox socket directory | `PGC_POSTMASTER` | restart. [guc_tables.c#unix_socket_directories](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4426-L4430) |
| `client_min_messages` | `debug1` around the gate builds | `PGC_USERSET` | session or transaction. [guc_tables.c#client_min_messages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4777-L4780) |
| `default_statistics_target` | `1` for fixture 120 only | `PGC_USERSET` | session or transaction. [guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2071-L2074) |
| `statement_timeout`, `lock_timeout` | `600s`/`900s` and `2s` in the scoring and harness sessions, and **`0` in every session that issues a maintenance statement** | `PGC_USERSET` | session or transaction. [guc_tables.c#statement_timeout-and-lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2631) |
| `transaction_timeout`, `idle_in_transaction_session_timeout` | `0` in every session that issues a maintenance statement, which is what an autovacuum worker forces on itself | `PGC_USERSET` | session or transaction. [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653), [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642), [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470) |

Every context and scope above is the PostgreSQL 17 definition, read from the
pinned 17 checkout. The 12 leg writes the same setting names except
`log_min_messages`, all of them into `postgresql.conf` before its first start,
so the run itself never needs an apply scope there; the scopes those settings
have on 12.2 are not stated on this page, because a v17 page may not cite a v12
checkout; see [Open Questions](#open-questions).

`initdb --locale=C` fixes the collation the fixtures assume, and the ICU cases
need a UTF8 database, which is why every database is created
`TEMPLATE template0 ENCODING 'UTF8'`.
[initdb.sgml#--locale](../../../../raw/postgres-17/doc/src/sgml/ref/initdb.sgml#L281-L291),
[installation.sgml#ICU-default](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L170).

### The PostgreSQL 17 suite script

Run it from the repository root. `bash btree_bloat_suite_v17.sh` runs every
stage; `bash btree_bloat_suite_v17.sh clean` stops the server and deletes the
sandbox. On the 2026-09-14 filter-removal host the whole run took about
3 min 30 s at `JOBS=10`, of which `build check` is 1 min 45 s; from a built
tree, everything after it is about the same again.

```bash
#!/usr/bin/env bash
#
# btree_bloat_suite_v17.sh - the whole test suite of the PostgreSQL 17 wiki page
# "Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17",
# in bash and SQL only.
#
# It builds 17.11 out of tree from the pinned checkout, runs the engine
# regression suites, starts an isolated cluster, installs the page's estimator
# and the superseded text as views, builds the mandatory suite's fixture
# families, scores each one against a measured REINDEX INDEX, attributes every
# moved row, runs the validation probes and prints the pass criteria.
#
# Every fixture it builds belongs to the shared mandatory suite.  The page-local
# fixtures this script carried until 2026-09-14 - the geometry cells, the
# calibration ladder by insertion pattern, and the acceptance stage's fresh
# sorted builds, defect fixtures, compression pair, posting-tail classes, probe
# fixtures and publication barrier - were removed with the claims they backed,
# so nothing here scores a method against a fixture the suite does not define.
#
# The pinned checkout is read only: everything this script writes lives under
# $SANDBOX (default .wiki-runtime/tmp/btree-suite).
#
# Usage, from the repository root:
#   bash btree_bloat_suite_v17.sh                 # all stages
#   bash btree_bloat_suite_v17.sh build check     # selected stages
#   bash btree_bloat_suite_v17.sh clean           # stop and delete the sandbox
#
# Stages: build check cluster texts gate suite churn extstat attribution
#         probes score cost criteria report stop clean
#
# The numbered fixtures run the five phases of the wiki's shared mandatory
# suite - build, baseline, churn, decide, and a measured REINDEX INDEX as the
# only oracle - and are scored with that suite's four verdict bands.  Every
# churn is followed by the suite's maintenance VACUUM ANALYZE, and the numbers
# that suite retired are not built here.  The suite is defined once, in the
# common concept page "Mandatory B-Tree Bloat Tests"; nothing here redefines
# it, and every deviation is named on this page.
#
# Since 2026-09-16 every one of those maintenance statements is also bracketed
# by the proofs that page's rule "The maintenance must not be defeated" asks
# for, because a VACUUM that ran, returned success and removed nothing leaves
# exactly the shape the suite retired.  Each statement is now a single
# VACUUM (VERBOSE, ANALYZE) between maint_begin() and maint_end(), issued from
# a session whose statement_timeout, lock_timeout, transaction_timeout and
# idle_in_transaction_session_timeout are all 0 - the four an autovacuum
# worker forces on itself for this reason - and the run records, per table,
# that the statement completed, its own "dead but not yet removable" count
# parsed out of the server's message text, the horizon holders read from
# pg_stat_activity, pg_replication_slots and pg_prepared_xacts, and the page
# classes it left in each index.  The churn stage dies rather than score a
# fixture whose maintenance was defeated.
#
# Environment: WIKI_ROOT PAGE SRC SANDBOX PORT JOBS OLD_REV
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v17/questions/indexing/btree-index-bloat-core-sql-only.md}"
SRC="${SRC:-$WIKI_ROOT/raw/postgres-17}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/btree-suite}"
PORT="${PORT:-55437}"
JOBS="${JOBS:-4}"
OLD_REV="${OLD_REV:-f2d73b4}"          # revision holding the superseded text

BUILD="$SANDBOX/build17"; INST="$SANDBOX/install17"; DATA="$SANDBOX/data17"
OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql"; SOCK="$SANDBOX/sock"; BIN="$INST/bin"
export PGPORT="$PORT" PGHOST="$SOCK" PGDATABASE=postgres

# SHA-256 baselines of the two fenced SQL blocks of the page, in page order.
# The geometry and calibration blocks, hashed here until 2026-09-14, went with
# the page-local stages that ran them.
BASE1=4de245c5a1fb442cda800c099b8801bc72abc0c87f170384490079135fb5241d  # estimator
BASE2=bfa7721f5edae40fd883b5bc0f0776e499716c48cfdbe10d191e95b9f8a3bb0d  # probes
BASEOLD=bffd166e44a4e81c181df3d9a10bfb547a6dcaf7349c2cd055578f35050d1357
# The estimator text as filed before the portable extstat filter of 2026-09-10,
# rebuilt from the current text, so this baseline moves whenever the current
# text does: it was 8acd531b7bcd2f2c until the report filter came out on
# 2026-09-14.  The extstat stage rebuilds it and must reproduce this.
BASEPRE=152f4172f1ee1dfd86467e525bfe37babba92a5ad036358bed0d17aa4b10594a

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# psql helpers.  -X ignores ~/.psqlrc; ON_ERROR_STOP is on every helper, because
# without it a failed statement inside a -f script leaves the exit status 0.
q()  { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$1" -c "$2"; }        # command
f()  { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$1" -f "$2"; }        # file
s()  { "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d "$1" -c "$2"; }    # scalar
t()  { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off \
                   -d "$1" -c "$2"; }                                 # table

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

# parse_verbose <log>: turn the maintenance statements' VACUUM (VERBOSE) output
# into one UPDATE per maintained table, so that proof 2 of the no-defeat rule -
# each statement's own "dead but not yet removable" count - is a recorded
# number rather than a line in a log.  A 17.11 server emits one message per
# relation,
#   INFO:  finished vacuuming "db.schema.tbl": index scans: N
#   tuples: X removed, Y remain, Z are dead but not yet removable
# so the relation name is carried from the header line to the tuples line, and
# the schema-qualified name is cut back to the bare table name.  INFO reaches
# the client whatever client_min_messages says, which is why the fixture
# sessions can keep theirs at warning.  A table maintained twice keeps the
# larger of the two dead counts, so neither statement can hide behind the
# other.  Bash case patterns and parameter expansion only: no awk, no perl.
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
        printf "UPDATE /* wiki_btree_maint_verbose */ maint SET removed = %s, remain = %s, dead_not_removable = greatest(coalesce(dead_not_removable, 0), %s) WHERE tbl = '%s';\n" \
               "$removed" "$remain" "$dead" "$cur"
        cur="" ;;
    esac
  done < "$log"
}

# harness_view <sql-file> <view> <extra projection>: the three documented edits.
# Drop the two SET lines, project the internals the scorer reads, and drop the
# report's own filtering and ordering.
#
# Two tails are handled, because this one function installs both texts.  The
# current text ends on " WHERE NOT suppress_row" and an ORDER BY line that
# carries the semicolon; its 1 MB filter and its LIMIT 20 came out on
# 2026-09-14.  The superseded text still ends on the 1 MB filter, an
# unterminated ORDER BY and " LIMIT 20;", so those arms stay.  Whichever line
# carries the semicolon is the one that emits it.
harness_view() {
  local file=$1 view=$2 extra=$3 line
  printf 'DROP VIEW IF EXISTS %s;\nCREATE VIEW %s AS\n' "$view" "$view"
  while IFS= read -r line; do
    case $line in
      "SET /* wiki_btree_wasted_space"*)     continue ;;
      "       server_version_num")           printf '       server_version_num,\n%s\n' "$extra"; continue ;;
      " WHERE NOT suppress_row")             continue ;;
      " WHERE actual_bytes > 1024 * 1024"*)  continue ;;
      " ORDER BY (actual_bytes"*';')         printf ';\n'; continue ;;
      " ORDER BY (actual_bytes"*)            continue ;;
      " LIMIT 20;")                          printf ';\n'; continue ;;
    esac
    printf '%s\n' "$line"
  done < "$file"
}

# Internals both texts define, and the four the current text adds.
INTERNALS='       expected_blocks, floor_blocks, actual_bytes, live_rows, slot,
       leaf_cap, int_cap, nmax, leaf_pages, tids, dedup_applies, is_partial,
       has_expressions, stats_row_missing, dedup_credited, stats_stale,
       suppress_row, ext_used, any_no_stats, any_stats_hidden,
       any_varlena_include'
INTERNALS_R2='       itupsz, any_stats_disabled, any_compressible, equalimage_state'

# --------------------------------------------------------------- harness -----
# The shared mandatory suite's harness, written once and installed in every
# database whose fixtures are scored, so that family 1 in the gate database and
# families 2 to 6 in the suite database run the same five phases and are scored
# by the same four bands.  The suite itself - its families, its phases, its
# three porting rules, its REINDEX INDEX oracle and its bands - is defined in
# the wiki's common concept page "Mandatory B-Tree Bloat Tests" and is not
# redefined here.
write_harness() {
  cat > "$SQLD/harness.sql" <<'HARNESS'
-- Disposable: every object below is created in a database of the sandbox
-- cluster and is not meant for a database anyone cares about.
SET /* wiki_btree_harness_client_min_messages */ client_min_messages = warning;
SET /* wiki_btree_harness_statement_timeout */ statement_timeout = '900s';
SET /* wiki_btree_harness_lock_timeout */ lock_timeout = '2s';

DROP EVENT TRIGGER IF EXISTS snap_on_build_trg;
DROP VIEW  IF EXISTS verdicts;
DROP TABLE IF EXISTS snap;
DROP TABLE IF EXISTS res;
DROP TABLE IF EXISTS plan;
DROP TABLE IF EXISTS maint;
DROP TABLE IF EXISTS horizon;
DROP TABLE IF EXISTS pageclass;

-- want_stage is the per-fixture prediction, filed in this script text before
-- the run and never rewritten after one; built_rows is the population measured
-- at the end of the build phase, which is what the fixture contract is about,
-- because rule 2's drain deliberately changes the population afterwards.
CREATE TABLE plan(num int, leg text DEFAULT '', grp text, req text, idx text,
                  rowsql text, want_rows bigint, built_rows bigint,
                  want_stage text, note text,
                  PRIMARY KEY (num, leg));

CREATE TABLE res(num int, leg text, req text, idx text,
                 size_before bigint, size_after bigint,
                 blocks_before int, blocks_after int,
                 status text, wsp numeric, wspf numeric, wasted_bytes numeric,
                 caveats text, equalimage text, reltuples_writer text,
                 modelled_rows numeric, key_groups numeric, tids numeric,
                 idx_reltuples numeric, exp_blocks numeric, floor_blocks numeric,
                 slot numeric, leaf_cap numeric, nmax numeric,
                 dedup_applies bool, is_partial bool, has_expressions bool,
                 suppress_row bool, stats_row_missing bool, dedup_credited bool,
                 stats_stale bool, any_varlena_include bool,
                 old_wsp numeric, old_wspf numeric,
                 true_rows bigint, want_rows bigint, note text,
                 PRIMARY KEY (num, leg));

-- Phase 2, the baseline: the file size and both row counts of one index at one
-- phase.  'built' is written the moment the index is created, 'churned' once
-- the fixture has been disturbed.
CREATE TABLE snap(phase text, idx text, bytes numeric, blocks int,
                  tbl_tuples numeric, idx_tuples numeric,
                  PRIMARY KEY (phase, idx));

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

-- ================================ the maintenance must not be defeated =====
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
-- churn, 'drain' for rule 2's uniform drain, 'prebuild' for fixture 85, whose
-- VACUUM precedes its index build and deliberately carries no ANALYZE.
-- No primary key on any of the three, deliberately: the estimator's candidate
-- set is every B-tree index outside the system schemas, so a harness index in
-- public would show up in the report the run is scoring.  maint_begin()
-- therefore deletes before it inserts instead of upserting.
CREATE TABLE maint(tbl text, ord int, source text,
                   started timestamptz, ended timestamptz,
                   removed numeric, remain numeric, dead_not_removable numeric,
                   mods_after numeric, dead_after numeric, timeouts text);

-- The horizon holders, read immediately before every maintenance statement and
-- once after the census.  These are reads beside the statement rather than an
-- interlock around it, which is the limitation the shared definition records
-- against itself.
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
-- values actually in force rather than the ones the script meant to set, and
-- stamps the start; maint_end stamps the end and reads what the statement left
-- behind.  The VERBOSE counts are filled in afterwards, from the server's own
-- message text, by the run's parse_verbose.  A table maintained twice keeps
-- one row: the delete-and-insert here and the greatest() in that UPDATE
-- together mean the row describes the last statement and the worst dead count
-- of all of them.
CREATE OR REPLACE FUNCTION maint_begin(p_tbl text, p_source text DEFAULT 'fixture')
RETURNS void LANGUAGE sql AS
$mb$ SELECT pg_stat_force_next_flush();
     DELETE FROM maint WHERE tbl = p_tbl;
     INSERT INTO maint(tbl, ord, source, started, timeouts)
     SELECT p_tbl, coalesce((SELECT max(ord) FROM maint), 0) + 1, p_source,
            clock_timestamp(),
            'statement_timeout=' || current_setting('statement_timeout') ||
            ' lock_timeout=' || current_setting('lock_timeout') ||
            ' transaction_timeout=' || current_setting('transaction_timeout') ||
            ' idle_in_transaction_session_timeout='
              || current_setting('idle_in_transaction_session_timeout');
     SELECT horizon_probe('maint', p_tbl) $mb$;

CREATE OR REPLACE FUNCTION maint_end(p_tbl text) RETURNS void LANGUAGE sql AS
$me$ SELECT pg_stat_clear_snapshot();
     UPDATE maint m
        SET ended = clock_timestamp(),
            mods_after = st.n_mod_since_analyze, dead_after = st.n_dead_tup
       FROM pg_stat_all_tables st
      WHERE st.schemaname = 'public' AND st.relname = m.tbl AND m.tbl = p_tbl;
     SELECT pg_stat_force_next_flush() $me$;

-- Rule 1 says every recipe is cut at its index build.  The cut is made by an
-- event trigger rather than by moving fixture statements, so a recipe whose
-- churn follows in the same file is cut at exactly the same point as one whose
-- churn is the drain stage.  DO NOTHING keeps the first build's snapshot, so
-- neither a fixture's own REINDEX nor the oracle rebuild can overwrite it.
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

CREATE OR REPLACE FUNCTION plan_add(n int, r text, i text, q text DEFAULT NULL,
                                    w bigint DEFAULT NULL, lg text DEFAULT '',
                                    nt text DEFAULT NULL)
RETURNS void LANGUAGE sql AS
$$ INSERT INTO plan(num, leg, req, idx, rowsql, want_rows, note)
   VALUES (n, lg, r, i, q, w, nt) $$;

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

-- Phases 4 and 5: read both texts on the churned fixture, then rebuild it and
-- measure the file again.  The rebuild is the only oracle.
CREATE OR REPLACE PROCEDURE score_all() LANGUAGE plpgsql AS $sc$
DECLARE p record; e record; sb bigint; sa bigint; tr bigint;
        ow numeric; owf numeric;
BEGIN
  FOR p IN SELECT * FROM plan ORDER BY num, leg LOOP
    tr := NULL; ow := NULL; owf := NULL;
    IF p.rowsql IS NOT NULL THEN EXECUTE p.rowsql INTO tr; END IF;
    sb := pg_relation_size(p.idx::regclass);
    SELECT * INTO e FROM est_r2 WHERE indexname = p.idx;
    IF NOT FOUND THEN RAISE EXCEPTION 'estimator returned no row for %', p.idx; END IF;
    BEGIN
      SELECT o.wasted_space_pct, o.wasted_space_pct_floor INTO ow, owf
        FROM est_old o WHERE o.indexname = p.idx;
    EXCEPTION WHEN OTHERS THEN ow := NULL; owf := NULL;
    END;
    EXECUTE format('REINDEX INDEX %I', p.idx);
    sa := pg_relation_size(p.idx::regclass);
    INSERT INTO res VALUES (p.num, p.leg, p.req, p.idx, sb, sa, sb / 8192, sa / 8192,
      e.status, e.wasted_space_pct, e.wasted_space_pct_floor, e.wasted_space_bytes,
      e.caveats, e.equalimage, e.reltuples_writer, e.modelled_rows, e.key_groups,
      e.tids_per_tuple, e.idx_reltuples, e.expected_blocks, e.floor_blocks,
      e.slot, e.leaf_cap, e.nmax, e.dedup_applies, e.is_partial, e.has_expressions,
      e.suppress_row, e.stats_row_missing, e.dedup_credited, e.stats_stale,
      e.any_varlena_include, ow, owf, tr, p.want_rows, p.note);
  END LOOP;
END $sc$;

-- The verdict view.  actual is what the rebuild of the churned file really gave
-- back and is the only oracle; verdict applies the shared suite's four bands to
-- it.  taken_stage is the decision this statement's own published reading rule
-- reaches from its own output: a row that is suppressed or carries one of the
-- five caveats the page refuses to promote is a 'leave' whatever its
-- percentage says.  Since 2026-09-14 size is not part of that rule, because
-- the statement no longer filters on it; over_1mb is kept as an observation of
-- what the removed filter used to withhold, and is read by nothing that
-- decides.  expected_stage recomputes the decision from the internals the
-- harness projects instead of from the reported percentage, so a statement
-- that disagrees with its own inputs is visible.  The 50 % rebuild threshold
-- is this harness's, not the suite's; the page says so.  verdict_point and
-- verdict_floor are the page's older bands, kept so the two scorings can be
-- compared on one row.
CREATE VIEW verdicts AS
SELECT r.num, r.leg, p.grp, r.idx, r.req,
       s.blocks AS blocks_built, r.blocks_before, r.blocks_after, a.actual,
       r.wsp, r.wspf, r.old_wsp, r.old_wspf,
       f.reported, f.alertable, f.over_1mb, d.taken_stage, d.taken_point,
       x.expected_stage, p.want_stage,
       CASE WHEN d.taken_stage = 'rebuild' AND a.actual < 10  THEN 'CRITICAL FALSE POSITIVE'
            WHEN d.taken_stage = 'rebuild' AND a.actual < 35  THEN 'FALSE POSITIVE'
            WHEN d.taken_stage = 'leave'   AND a.actual >= 50 THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END                                    AS verdict,
       CASE WHEN d.taken_stage = 'leave' AND a.actual >= 50
            THEN CASE WHEN NOT f.reported  THEN 'withheld'
                      WHEN NOT f.alertable THEN 'caveat'
                      WHEN r.wspf IS NULL  THEN 'unmeasured'
                      ELSE 'threshold' END END                 AS lost_by,
       v.verdict_point, v.verdict_floor,
       CASE WHEN NOT r.suppress_row                             THEN NULL
            WHEN r.is_partial AND r.stats_row_missing           THEN 'A: no statistics row'
            WHEN r.is_partial AND r.dedup_credited              THEN 'A: duplicates from table statistics'
            WHEN r.is_partial AND r.stats_stale                 THEN 'B: changed since ANALYZE'
            WHEN r.is_partial AND r.any_varlena_include         THEN 'C: variable-width INCLUDE'
            WHEN r.has_expressions AND r.stats_row_missing      THEN 'D: expression, no statistics row'
            ELSE 'unexplained' END                        AS withheld_by,
       (p.want_rows IS NULL OR p.built_rows = p.want_rows) AS contract_ok,
       s.tbl_tuples AS tbl_tuples_built, c.tbl_tuples AS tbl_tuples_churned,
       s.idx_tuples AS idx_tuples_built, c.idx_tuples AS idx_tuples_churned,
       p.built_rows, r.true_rows, p.want_rows, r.modelled_rows, r.idx_reltuples,
       r.status, r.caveats, r.equalimage, r.tids, r.note,
       -- The maintenance the assumption credits this fixture with, and the
       -- no-defeat proofs that went with it.  maintained is false for a
       -- fixture no churn touched, which is a state the suite defines rather
       -- than a gap: its build-phase ANALYZE is the maintenance it carries.
       ct.relname AS tbl, (m.tbl IS NOT NULL) AS maintained,
       m.source AS maint_source, m.dead_not_removable,
       m.removed AS maint_removed, m.dead_after, m.mods_after, m.timeouts,
       q.deleted_pages, q.empty_pages,
       q.avg_leaf_density AS density_after_maint
  FROM res r
  JOIN plan p ON p.num = r.num AND p.leg = r.leg
  LEFT JOIN snap s ON s.phase = 'built'   AND s.idx = r.idx
  LEFT JOIN snap c ON c.phase = 'churned' AND c.idx = r.idx
  LEFT JOIN pg_class ic ON ic.relname = r.idx AND ic.relkind = 'i'
  LEFT JOIN pg_index ix ON ix.indexrelid = ic.oid
  LEFT JOIN pg_class ct ON ct.oid = ix.indrelid
  LEFT JOIN maint m ON m.tbl = ct.relname
  LEFT JOIN pageclass q ON q.idx = r.idx
  CROSS JOIN LATERAL (
        SELECT round(100.0 * (r.size_before - r.size_after)
                     / greatest(r.size_before, 1), 1) AS actual) a
  CROSS JOIN LATERAL (
        SELECT NOT r.suppress_row                             AS reported,
               (r.caveats IS NULL OR r.caveats !~
                '(never analyzed|row-count sources disagree|statistics not visible|zero modelled rows|wide compressible key)')
                                                              AS alertable,
               -- observation only: the size the removed 1 MB filter tested
               (r.size_before > 1024 * 1024)                  AS over_1mb) f
  CROSS JOIN LATERAL (
        SELECT CASE WHEN f.reported AND f.alertable
                     AND r.wspf >= 50 THEN 'rebuild' ELSE 'leave' END AS taken_stage,
               CASE WHEN f.reported AND f.alertable
                     AND r.wsp  >= 50 THEN 'rebuild' ELSE 'leave' END AS taken_point) d
  CROSS JOIN LATERAL (
        SELECT CASE WHEN r.suppress_row OR r.floor_blocks IS NULL
                      OR NOT f.alertable                          THEN 'leave'
                    WHEN round(100.0 * (r.size_before
                                        - r.floor_blocks * current_setting('block_size')::numeric)
                               / greatest(r.size_before, 1), 1) >= 50 THEN 'rebuild'
                    ELSE 'leave' END                             AS expected_stage) x
  CROSS JOIN LATERAL (
        SELECT CASE WHEN r.wsp IS NULL                       THEN 'UNMEASURED'
                    WHEN r.wsp >= 50 AND a.actual < 10       THEN 'CRITICAL FALSE POSITIVE'
                    WHEN r.wsp >= 50 AND a.actual < 45       THEN 'FALSE POSITIVE'
                    WHEN r.wsp >= 50 AND r.wsp - a.actual > 5 THEN 'FALSE POSITIVE'
                    WHEN r.wsp <  45 AND a.actual >= 50      THEN 'FALSE NEGATIVE'
                    ELSE 'PASS' END                          AS verdict_point,
               CASE WHEN r.wspf IS NULL                      THEN 'UNMEASURED'
                    WHEN r.wspf >= 50 AND a.actual < 10      THEN 'CRITICAL FALSE POSITIVE'
                    WHEN r.wspf >= 50 AND a.actual < 45      THEN 'FALSE POSITIVE'
                    WHEN r.wspf >= 50 AND r.wspf - a.actual > 5 THEN 'FALSE POSITIVE'
                    WHEN r.wspf <  45 AND a.actual >= 50     THEN 'FALSE NEGATIVE'
                    ELSE 'PASS' END                          AS verdict_floor) v;
HARNESS
}

# ---------------------------------------------------------------- build ------
# clean deletes $BUILD, and $OUT is what a reviewer copies out, so the build
# diagnostics are copied into $OUT after every step, on the failure path too.
# Until the 2026-09-10 repair the copy sat after the last die and so never
# ran for the failed build it was meant to preserve.
keep_build_logs() {
  local l
  for l in configure make install; do
    [ -f "$BUILD/$l.log" ] && cp "$BUILD/$l.log" "$OUT/$l.log"
  done
  return 0
}
stage_build() {
  say "build 17.11 out of tree from $SRC"
  [ -x "$BIN/postgres" ] && { note "already built, skipping"; return 0; }
  [ -x "$SRC/configure" ] || die "no pinned checkout at $SRC; set SRC or run from the repository root"
  mkdir -p "$BUILD" "$OUT" "$SQLD"
  ( cd "$BUILD" && "$SRC/configure" --prefix="$INST" --enable-debug \
      --with-icu --with-readline --with-zlib > configure.log 2>&1 ) \
    || { keep_build_logs; die "configure failed, see $OUT/configure.log"; }
  ( cd "$BUILD" && make -j"$JOBS" > make.log 2>&1 && make install > install.log 2>&1 ) \
    || { keep_build_logs; die "make failed, see $OUT/make.log"; }
  local m
  for m in pageinspect pgstattuple amcheck; do
    ( cd "$BUILD" && make -C "contrib/$m" -j"$JOBS" >> install.log 2>&1 \
        && make -C "contrib/$m" install >> install.log 2>&1 ) \
      || { keep_build_logs; die "contrib/$m failed, see $OUT/install.log"; }
  done
  keep_build_logs
  note "$("$BIN/postgres" --version)"
}

# ---------------------------------------------------------------- check ------
stage_check() {
  say "engine regression suites"
  : > "$OUT/checks.txt"
  ( cd "$BUILD" && make check > check_core.log 2>&1 )
  printf 'core=%s %s\n' "$?" \
    "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_core.log" | tail -1)" \
    >> "$OUT/checks.txt"
  local m
  for m in pageinspect pgstattuple amcheck; do
    ( cd "$BUILD" && make -C "contrib/$m" check > "check_$m.log" 2>&1 )
    printf '%s=%s %s\n' "$m" "$?" \
      "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_$m.log" | tail -1)" \
      >> "$OUT/checks.txt"
  done
  # A one-line summary cannot diagnose a failure, and the logs and diffs live
  # in $BUILD, which clean deletes.  Copy both where they survive.
  cp "$BUILD"/check_*.log "$OUT/" 2>/dev/null
  local d
  for d in "$BUILD/src/test/regress" "$BUILD"/contrib/*; do
    [ -f "$d/regression.diffs" ] \
      && cp "$d/regression.diffs" "$OUT/diffs_$(basename "$d").txt"
  done
  cat "$OUT/checks.txt" >&2
}

# ---------------------------------------------------------------- cluster ----
stage_cluster() {
  say "isolated cluster on port $PORT"
  # Returning early here would skip the database loop below, so a cluster left
  # running by an earlier run would never gain a database a new stage needs.
  if [ -s "$DATA/postmaster.pid" ] && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    note "already running"
  else
    if [ ! -d "$DATA" ]; then
      mkdir -p "$SOCK"
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
log_min_messages = debug1
logging_collector = off
CONF
    fi
    # The server-error check reads the log from this mark, so a sandbox with a
    # stray error recovers with stop cluster; the earlier lines stay in the log.
    { [ -f "$OUT/server.log" ] && wc -l < "$OUT/server.log" || printf '0\n'; } \
      | tr -d ' ' > "$OUT/server.log.mark"
    "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w start > /dev/null \
      || die "server start failed"
  fi
  note "$(s postgres 'select /* wiki_btree_suite_version */ version()')"
  s postgres "select /* wiki_btree_suite_platform */
                     'max_data_alignment=' || max_data_alignment ||
              ' database_block_size=' || database_block_size from pg_control_init()" \
    | tee "$OUT/platform.txt" >&2
  printf 'uname: %s\n' "$(uname -sm)" >> "$OUT/platform.txt"
  local db
  for db in gate suite xstat; do
    s postgres "select /* wiki_btree_suite_database_exists */ 1
                  from pg_database where datname='$db'" | grep -q 1 \
      || "$BIN/createdb" -T template0 -E UTF8 --locale=C "$db"
  done
}

# ---------------------------------------------------------------- texts ------
stage_texts() {
  say "statement texts, hashes and harness views"
  [ -f "$PAGE" ] || die "no page at $PAGE; set PAGE or run from the repository root"
  md_block sql 1 "$PAGE" > "$SQLD/est_r2.sql"
  md_block sql 2 "$PAGE" > "$SQLD/probegen.sql"
  ( cd "$WIKI_ROOT" && git show "$OLD_REV:wiki/v17/questions/indexing/btree-index-bloat-core-sql-only.md" ) \
    > "$SQLD/old_page.md" 2>/dev/null || die "cannot read revision $OLD_REV"
  md_block sql 1 "$SQLD/old_page.md" > "$SQLD/est_old.sql"

  : > "$OUT/hashes.txt"
  local n f base got
  n=0
  for f in est_r2 probegen est_old; do
    n=$((n + 1))
    case $n in 1) base=$BASE1;; 2) base=$BASE2;; 3) base=$BASEOLD;; esac
    got=$(sha256sum < "$SQLD/$f.sql" | cut -d' ' -f1)
    if [ "$got" = "$base" ]; then printf '%-12s match  %s\n' "$f" "$got" >> "$OUT/hashes.txt"
    else printf '%-12s DIFFER %s (baseline %s)\n' "$f" "$got" "$base" >> "$OUT/hashes.txt"; fi
  done
  cat "$OUT/hashes.txt" >&2

  # Both exact texts must execute exactly as filed: the current one with no
  # report filter but NOT suppress_row and no LIMIT, the superseded one with
  # its 1 MB filter and its LIMIT 20.  The printed row count is recorded for
  # each, because that is the difference the removal of 2026-09-14 makes to a
  # reader; the settled count is taken again by the cost stage, on a populated
  # database.
  local db
  for db in suite; do
    f "$db" "$SQLD/est_r2.sql" > "$OUT/exact_r2_$db.txt" 2>&1 \
      && note "exact current text runs on $db" || die "exact current text failed on $db"
  done
  f suite "$SQLD/est_old.sql" > "$OUT/exact_old_suite.txt" 2>&1 \
    && note "exact superseded text runs on suite" || note "exact superseded text FAILED on suite"
  { printf 'r2  %s\n'  "$(grep -E '^\([0-9]+ rows?\)$' "$OUT/exact_r2_suite.txt"  | tail -1)"
    printf 'old %s\n' "$(grep -E '^\([0-9]+ rows?\)$' "$OUT/exact_old_suite.txt" | tail -1)"
  } > "$OUT/exact_rows.txt"
  cat "$OUT/exact_rows.txt" >&2

  harness_view "$SQLD/est_r2.sql"  est_r2  "$INTERNALS,
$INTERNALS_R2" > "$SQLD/view_r2.sql"
  harness_view "$SQLD/est_old.sql" est_old "$INTERNALS" > "$SQLD/view_old.sql"
  for db in gate suite; do
    f "$db" "$SQLD/view_r2.sql"  || die "est_r2 view failed on $db"
    f "$db" "$SQLD/view_old.sql" || die "est_old view failed on $db"
  done
  write_harness
  note "shared-suite harness written to $SQLD/harness.sql"
}

# ---------------------------------------------------------------- extstat ----
# The portable inherited filter of the extstat CTE, against the two readings it
# replaces.  Both are rebuilt from the filed text, one edit apart:
#   est_pre   the flag named as a column, AND se.inherited = false, which is
#             the text filed before 2026-09-10 and must hash to BASEPRE
#   est_wide  est_pre with that line deleted, which is what the 12 leg's
#             transformer produced before this change
# Pass: est_r2 equals est_pre row for row in every database, and est_wide
# differs on the inheritance parent, whose own ANALYZE pass is the only one
# describing the rows the parent's own index actually contains.
# In the default order this stage runs after suite, so that its equivalence
# counts and its cost pairs see the populated suite database; until 2026-09-10
# it ran right after texts, where a fresh full run found suite empty.
stage_extstat() {
  say "extstat: the portable inherited filter against the two readings it replaces"
  [ -s "$SQLD/est_r2.sql" ] || die "no $SQLD/est_r2.sql; run the texts stage first"
  local line got
  : > "$SQLD/est_pre.sql"
  while IFS= read -r line; do
    case $line in
      "    -- The inherited flag is read through row_to_json()"*) continue ;;
      "    -- as a column, so one text also parses where"*)       continue ;;
      "    -- column: there the key is absent"*)                  continue ;;
      "    -- admits the row, which is the only ANALYZE pass"*)   continue ;;
      "                          AND coalesce((row_to_json(se)"*)
        printf '                          AND se.inherited = false\n' \
          >> "$SQLD/est_pre.sql"; continue ;;
      "                                       false) = false")    continue ;;
    esac
    printf '%s\n' "$line" >> "$SQLD/est_pre.sql"
  done < "$SQLD/est_r2.sql"
  got=$(sha256sum < "$SQLD/est_pre.sql" | cut -d' ' -f1)
  : > "$SQLD/est_wide.sql"
  while IFS= read -r line; do
    [ "$line" = "                          AND se.inherited = false" ] && continue
    printf '%s\n' "$line" >> "$SQLD/est_wide.sql"
  done < "$SQLD/est_pre.sql"
  { printf 'est_pre  %s %s\n' \
      "$([ "$got" = "$BASEPRE" ] && printf match || printf DIFFER)" "$got"
    printf 'est_wide        %s\n' "$(sha256sum < "$SQLD/est_wide.sql" | cut -d' ' -f1)"
  } > "$OUT/extstat.txt"
  [ "$got" = "$BASEPRE" ] || note "est_pre does not match BASEPRE; the reconstruction is stale"

  # Both reconstructions must execute as filed on a server that has the column.
  f xstat "$SQLD/est_pre.sql"  > "$OUT/extstat_pre.txt"  2>&1 \
    || die "the reconstructed previous text does not execute here"
  f xstat "$SQLD/est_wide.sql" > "$OUT/extstat_wide.txt" 2>&1 \
    || die "the widened text does not execute here"
  harness_view "$SQLD/est_pre.sql"  est_pre  "$INTERNALS,
$INTERNALS_R2" > "$SQLD/view_pre.sql"
  harness_view "$SQLD/est_wide.sql" est_wide "$INTERNALS,
$INTERNALS_R2" > "$SQLD/view_wide.sql"
  local db
  for db in gate suite xstat; do
    f "$db" "$SQLD/view_r2.sql"   || die "est_r2 view failed on $db"
    f "$db" "$SQLD/view_pre.sql"  || die "est_pre view failed on $db"
    f "$db" "$SQLD/view_wide.sql" || die "est_wide view failed on $db"
  done

  # The xstat fixtures are page-local rather than suite fixtures, but one of
  # them deletes and vacuums, so the harness goes in here too and its
  # maintenance statement is bracketed and proved like every other one in the
  # run.  Then no VACUUM anywhere in this script is unaccounted for.
  f xstat "$SQLD/harness.sql" || die "harness install failed on xstat"
  # Disposable fixtures: the block below drops and creates tables, statistics
  # objects and indexes in the xstat database of the sandbox cluster.  It is
  # not meant for a database anyone cares about.
  f xstat /dev/stdin > "$OUT/extstat_fixtures.log" 2> "$OUT/extstat_verbose.log" <<'SQL'
SET /* wiki_btree_extstat_client_min_messages */ client_min_messages = warning;
SET /* wiki_btree_extstat_statement_timeout */ statement_timeout = 0;
SET /* wiki_btree_extstat_lock_timeout */ lock_timeout = 0;
SET /* wiki_btree_extstat_transaction_timeout */ transaction_timeout = 0;
SET /* wiki_btree_extstat_idle_timeout */ idle_in_transaction_session_timeout = 0;
DROP TABLE IF EXISTS xchi, xpar, xchi2, xpar2, xchi3, xpar3, xflat,
                     xstat_res CASCADE;

-- A. an inheritance parent carrying a whole-key ndistinct object.  ANALYZE
--    writes one pg_statistic_ext_data row per pass, and a legacy inheritance
--    parent's index holds only the parent's own rows, so the own pass is the
--    correct input and the inherited pass describes rows it does not contain.
CREATE TABLE xpar(a int, b int, c int);
CREATE TABLE xchi(a int, b int, c int) INHERITS (xpar);
CREATE STATISTICS xpar_nd (ndistinct) ON a, b FROM xpar;
INSERT INTO xpar SELECT i % 10, i % 20, i FROM generate_series(1, 300000) i;
INSERT INTO xchi SELECT i % 500, i % 700, i FROM generate_series(1, 300000) i;
CREATE INDEX xpar_ab ON xpar (a, b);
ANALYZE xpar;
SELECT pg_stat_force_next_flush();

-- B. the same shape with 60 % of the parent's rows deleted and vacuumed, so a
--    real 60 % of the index is reclaimable and every text can be scored
--    against a measured REINDEX INDEX rather than against a fresh build.
CREATE TABLE xpar2(a int, b int, c int);
CREATE TABLE xchi2(a int, b int, c int) INHERITS (xpar2);
CREATE STATISTICS xpar2_nd (ndistinct) ON a, b FROM xpar2;
INSERT INTO xpar2 SELECT i % 10, i % 20, i FROM generate_series(1, 300000) i;
INSERT INTO xchi2 SELECT i % 500, i % 700, i FROM generate_series(1, 300000) i;
CREATE INDEX xpar2_ab ON xpar2 (a, b);
DELETE FROM xpar2 WHERE c % 5 < 3;
SELECT maint_begin('xpar2', 'extstat');
VACUUM (VERBOSE, ANALYZE) xpar2;
SELECT maint_end('xpar2');

-- D. the same parent with a high-cardinality child, which is the shape that
--    makes the difference large.  The inherited pass then estimates about one
--    distinct pair per row, so a text reading it credits no deduplication at
--    all and prices singleton tuples instead of posting ones.
CREATE TABLE xpar3(a int, b int, c int);
CREATE TABLE xchi3(a int, b int, c int) INHERITS (xpar3);
CREATE STATISTICS xpar3_nd (ndistinct) ON a, b FROM xpar3;
INSERT INTO xpar3 SELECT i % 10, i % 20, i FROM generate_series(1, 300000) i;
INSERT INTO xchi3 SELECT i, i, i FROM generate_series(1, 300000) i;
CREATE INDEX xpar3_ab ON xpar3 (a, b);
ANALYZE xpar3;
SELECT pg_stat_force_next_flush();

-- C. control: the same object on a table with no children, so ANALYZE writes
--    one pass and all three texts must agree.
CREATE TABLE xflat(a int, b int, c int);
CREATE STATISTICS xflat_nd (ndistinct) ON a, b FROM xflat;
INSERT INTO xflat SELECT i % 10, i % 20, i FROM generate_series(1, 300000) i;
CREATE INDEX xflat_ab ON xflat (a, b);
ANALYZE xflat;
SELECT pg_stat_force_next_flush();

CREATE TABLE xstat_res(idx text, txt text, blocks int, wsp numeric,
                       wspf numeric, key_groups numeric, ext_used bool,
                       caveats text, actual numeric);
DO $x$
DECLARE ix text; v text; e record; sb bigint; sa bigint;
BEGIN
  FOREACH ix IN ARRAY ARRAY['xpar_ab','xpar2_ab','xpar3_ab','xflat_ab'] LOOP
    sb := pg_relation_size(ix::regclass);
    FOREACH v IN ARRAY ARRAY['est_r2','est_pre','est_wide'] LOOP
      EXECUTE format('SELECT wasted_space_pct AS wsp,
                             wasted_space_pct_floor AS wspf,
                             key_groups, ext_used, caveats
                        FROM %I WHERE indexname = %L', v, ix) INTO e;
      INSERT INTO xstat_res(idx, txt, blocks, wsp, wspf, key_groups,
                            ext_used, caveats)
        VALUES (ix, v, sb / 8192, e.wsp, e.wspf, e.key_groups, e.ext_used,
                e.caveats);
    END LOOP;
  END LOOP;
  FOREACH ix IN ARRAY ARRAY['xpar_ab','xpar2_ab','xpar3_ab','xflat_ab'] LOOP
    sb := pg_relation_size(ix::regclass);
    EXECUTE format('REINDEX INDEX %I', ix);
    sa := pg_relation_size(ix::regclass);
    UPDATE xstat_res SET actual = round(100.0 * (sb - sa) / greatest(sb, 1), 1)
     WHERE idx = ix;
  END LOOP;
END $x$;
SQL
  [ $? -eq 0 ] || { tail -5 "$OUT/extstat_verbose.log" >&2; die "xstat fixtures failed"; }
  # The same proof 2 this run records everywhere else, for the one maintenance
  # statement these fixtures issue, and then the same check over it.
  parse_verbose "$OUT/extstat_verbose.log" > "$SQLD/maint_verbose_xstat.sql"
  [ -s "$SQLD/maint_verbose_xstat.sql" ] \
    || die "the xstat VACUUM VERBOSE output produced no tuples line: proof 2 is missing"
  f xstat "$SQLD/maint_verbose_xstat.sql" > /dev/null \
    || die "recording the xstat VERBOSE counts failed"
  maint_proofs xstat

  # 1. equivalence: the filed text against the text it replaced, every column
  #    both views project, in every database the suite builds.  ext_used
  #    counts the rows the extstat CTE actually fed, because a database with
  #    no extended-statistics object cannot tell the two texts apart.
  printf 'equivalence, est_r2 against est_pre\n' >> "$OUT/extstat.txt"
  for db in gate suite xstat; do
    printf '%-6s r2_minus_pre=%s pre_minus_r2=%s rows=%s ext_used=%s\n' "$db" \
      "$(s "$db" 'SELECT /* wiki_btree_extstat_r2_minus_pre */ count(*)
                    FROM (SELECT * FROM est_r2 EXCEPT SELECT * FROM est_pre) d')" \
      "$(s "$db" 'SELECT /* wiki_btree_extstat_pre_minus_r2 */ count(*)
                    FROM (SELECT * FROM est_pre EXCEPT SELECT * FROM est_r2) d')" \
      "$(s "$db" 'SELECT /* wiki_btree_extstat_row_count */ count(*) FROM est_r2')" \
      "$(s "$db" 'SELECT /* wiki_btree_extstat_ext_used */ count(*)
                    FROM est_r2 WHERE ext_used')" \
      >> "$OUT/extstat.txt"
  done
  # 2. the two ANALYZE passes the fixture stores, and what each says.
  t xstat "SELECT /* wiki_btree_extstat_passes */
                  tablename, statistics_name, inherited,
                  ((n_distinct::text)::json ->> '1, 2')::numeric AS nd_whole_key
             FROM pg_stats_ext WHERE schemaname = 'public'
            ORDER BY tablename, inherited" >> "$OUT/extstat.txt" 2>&1
  # 3. the three texts scored against a measured REINDEX INDEX.
  t xstat "SELECT /* wiki_btree_extstat_scored */
                  idx, txt, blocks, actual, wsp, wspf, key_groups, ext_used
             FROM xstat_res ORDER BY idx, txt" >> "$OUT/extstat.txt" 2>&1
  # 4. cost: row_to_json() serialises a whole pg_stats_ext row per candidate
  #    join, so the two texts are timed interleaved on the largest database.
  printf 'cost, six interleaved pairs on suite\n' >> "$OUT/extstat.txt"
  local i
  for i in 1 2 3 4 5 6; do
    printf 'pair %s r2  %s\n' "$i" \
      "$("$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite \
           -c '\timing on' -f "$SQLD/est_r2.sql" 2>&1 \
         | grep -E '^Time:' | tail -1)" >> "$OUT/extstat.txt"
    printf 'pair %s pre %s\n' "$i" \
      "$("$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite \
           -c '\timing on' -f "$SQLD/est_pre.sql" 2>&1 \
         | grep -E '^Time:' | tail -1)" >> "$OUT/extstat.txt"
  done
  cat "$OUT/extstat.txt" >&2
}

# ---------------------------------------------------------------- gate -------
stage_gate() {
  say "deduplication gate, tests 1-17 less the retired 11, 25 fixtures on two 500,000-row tables"
  q gate 'CREATE EXTENSION IF NOT EXISTS pageinspect'
  q gate 'CREATE EXTENSION IF NOT EXISTS amcheck'
  # Family 1 runs the shared suite's five phases too, so the harness and its
  # baseline event trigger go in before the fixtures are built.
  f gate "$SQLD/harness.sql" || die "harness install failed on gate"
  # Disposable fixtures: the block below drops and recreates tables, operator
  # classes, collations and a public.btequalimage impostor in the gate database
  # of the sandbox cluster.  It is not meant for a database anyone cares about.
  PGOPTIONS='-c client_min_messages=debug1' \
    "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d gate -f /dev/stdin \
    > "$OUT/gate_build.log" 2>&1 <<'SQL'
DROP TABLE IF EXISTS t CASCADE;
DROP TABLE IF EXISTS t2 CASCADE;
-- The family, not the class.  CREATE OPERATOR CLASS with no FAMILY clause
-- creates an operator family of the same name and puts the support-function
-- rows in it; dropping only the class leaves that family and its FUNCTION 4
-- row behind, and the next run of this stage then fails with "duplicate key
-- value violates unique constraint pg_amproc_fam_proc_index".  Dropping the
-- family CASCADE takes the class with it, which is what makes the stage
-- re-runnable on a cluster where it has already run.
DROP OPERATOR FAMILY IF EXISTS int4_ei_true USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS int4_ei_false USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS int4_ei_none USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS int4_ei_alias USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS int8_ei_true USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS int8_ei_false USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS text_squat USING btree CASCADE;
DROP OPERATOR FAMILY IF EXISTS text_renamed USING btree CASCADE;

CREATE COLLATION IF NOT EXISTS ci   (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
CREATE COLLATION IF NOT EXISTS cdet (provider = icu, locale = 'und');

CREATE OR REPLACE FUNCTION ei_true(oid)  RETURNS bool LANGUAGE sql IMMUTABLE AS $$ SELECT true $$;
CREATE OR REPLACE FUNCTION ei_false(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS $$ SELECT false $$;
CREATE OR REPLACE FUNCTION ei_alias(oid) RETURNS bool LANGUAGE internal IMMUTABLE AS 'btequalimage';
-- test 16, the impostor: a SQL function wearing the built-in's name.  It must
-- be schema-qualified in the operator class or pg_catalog wins the lookup.
CREATE OR REPLACE FUNCTION public.btequalimage(oid) RETURNS bool LANGUAGE sql IMMUTABLE AS $$ SELECT true $$;
-- test 16, the rename: prosrc still names the built-in, so the gate credits it.
CREATE OR REPLACE FUNCTION ei_renamed(oid) RETURNS bool LANGUAGE internal IMMUTABLE AS 'btvarstrequalimage';

CREATE OPERATOR CLASS int4_ei_true FOR TYPE int4 USING btree AS
  OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
  OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
  FUNCTION 1 btint4cmp(int4,int4), FUNCTION 4 ei_true(oid);
CREATE OPERATOR CLASS int4_ei_false FOR TYPE int4 USING btree AS
  OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
  OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
  FUNCTION 1 btint4cmp(int4,int4), FUNCTION 4 ei_false(oid);
CREATE OPERATOR CLASS int4_ei_none FOR TYPE int4 USING btree AS
  OPERATOR 1 <(int4,int4), OPERATOR 2 <=(int4,int4), OPERATOR 3 =(int4,int4),
  OPERATOR 4 >=(int4,int4), OPERATOR 5 >(int4,int4),
  FUNCTION 1 btint4cmp(int4,int4);
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

CREATE TABLE t AS
SELECT i::int4 AS u, (i % 5000)::int4 AS a, (i % 5000)::int8 AS b,
       'key' || lpad((i % 5000)::text, 8, '0') AS s, ((i % 5000)::numeric) AS n,
       (i % 5000)::float4 AS f4, (i % 5000)::float8 AS f8, (i % 7)::int4 AS d
  FROM generate_series(1, 500000) i;
CREATE TABLE t2 AS
SELECT i::int4 AS u, (i % 5000)::int4 AS a, (i % 5000)::int8 AS b,
       'key' || lpad((i % 5000)::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;

SET client_min_messages = debug1;          -- logs the engine's own verdict
CREATE INDEX i_int4          ON t (a);                                   -- 1
CREATE INDEX i_int8          ON t (b);                                   -- 2
CREATE INDEX i_text_det      ON t (s);                                   -- 3
CREATE INDEX i_text_det2     ON t (s text_renamed);                      -- 16
CREATE INDEX i_text_icu_det  ON t (s COLLATE cdet);                      -- 3
CREATE INDEX i_text_nondet   ON t (s COLLATE ci);                        -- 4
CREATE INDEX i_numeric       ON t (n);                                   -- 5
CREATE INDEX i_float4        ON t (f4);                                  -- 6
CREATE INDEX i_float8        ON t (f8);                                  -- 6
CREATE INDEX i_multi_ok      ON t (a, b);                                -- 7
CREATE INDEX i_multi_bad     ON t (a, n);                                -- 8
CREATE INDEX i_expr_lower_ci ON t ((lower(s)) COLLATE ci);               -- 9
CREATE INDEX i_expr_num      ON t ((a::numeric));                        -- 9
CREATE INDEX i_inc           ON t (a) INCLUDE (d);                       -- 10
-- 11 built i_dupoff and i_text_off here, and i2_off on t2, all three with
-- deduplicate_items = off.  The shared suite retired 11 and its 11b transition
-- control on 2026-09-12: explicitly setting the reloption is outside it, and a
-- retired number is not reused, so nothing is built in their place.
CREATE INDEX i_ei_none       ON t (a int4_ei_none);                      -- 12
CREATE INDEX i_ei_false      ON t (a int4_ei_false);                     -- 13
CREATE INDEX i_ei_true       ON t (a int4_ei_true);                      -- 14
CREATE INDEX i_ei_alias      ON t (a int4_ei_alias);                     -- 14
CREATE INDEX i_mixed_tf      ON t (a int4_ei_true, b int8_ei_false);     -- 15
CREATE INDEX i_mixed_ft      ON t (a int4_ei_false, b int8_ei_true);     -- 15
CREATE INDEX i_squat         ON t (s text_squat);                        -- 16
CREATE UNIQUE INDEX i_uniq   ON t (u);
CREATE INDEX i2_ok           ON t2 (a, b);                               -- 7
CREATE INDEX i2_tf           ON t2 (a int4_ei_true, b int8_ei_false);    -- 15
CREATE INDEX i2_ft           ON t2 (a int4_ei_false, b int8_ei_true);    -- 15
RESET client_min_messages;
SELECT pg_stat_force_next_flush();
ANALYZE t, t2;
SELECT pg_stat_force_next_flush();
SQL
  [ $? -eq 0 ] || { tail -20 "$OUT/gate_build.log" >&2; die "gate fixtures failed"; }

  # test 4 and the pattern-opclass refusal, measured rather than derived.  The
  # refusal is the expected outcome, so the file says so above the error text;
  # a bare ERROR line at the top of a result file reads like a failure, and an
  # acceptance would be the surprise, so each branch writes its own header.
  local hdr
  if q gate "CREATE INDEX i_pattern_nondet ON t (s COLLATE ci text_pattern_ops)" \
       > "$OUT/gate_pattern.txt" 2>&1; then
    note "text_pattern_ops accepted (unexpected)"
    hdr='UNEXPECTED: test 4 expected text_pattern_ops to refuse a nondeterministic collation, and it was accepted'
  else
    note "text_pattern_ops refused as expected: $(tail -1 "$OUT/gate_pattern.txt")"
    hdr='expected: test 4, text_pattern_ops refuses a nondeterministic collation'
  fi
  { printf '%s\n' "$hdr"; cat "$OUT/gate_pattern.txt"; } > "$OUT/gate_pattern.tmp" \
    && mv "$OUT/gate_pattern.tmp" "$OUT/gate_pattern.txt"

  # The same fixtures, filed as plan rows so that family 1 is scored by the
  # shared suite's oracle and bands as well as against the metapage.  The leg
  # is the index name, because eight of the seventeen tests carry more than one
  # fixture.  Every one is a shape fixture, so rule 2 drains all of them and
  # every prediction is a rebuild.  The plan is filed before gate_res, because
  # gate_res reads it to tell a fixture index from the harness's own.
  f gate /dev/stdin <<'SQL'
SET /* wiki_btree_gateplan_client_min_messages */ client_min_messages = warning;
SET /* wiki_btree_gateplan_statement_timeout */ statement_timeout = '900s';
SET /* wiki_btree_gateplan_lock_timeout */ lock_timeout = '2s';
SELECT plan_add(1,  'int4 key, 100 rows per key',           'i_int4',          'SELECT count(*) FROM t',  500000, 'i_int4');
SELECT plan_add(2,  'int8 key, 100 rows per key',           'i_int8',          'SELECT count(*) FROM t',  500000, 'i_int8');
SELECT plan_add(3,  'text key, default collation',          'i_text_det',      'SELECT count(*) FROM t',  500000, 'i_text_det');
SELECT plan_add(3,  'text key, deterministic ICU collation','i_text_icu_det',  'SELECT count(*) FROM t',  500000, 'i_text_icu_det');
SELECT plan_add(4,  'text key, nondeterministic collation', 'i_text_nondet',   'SELECT count(*) FROM t',  500000, 'i_text_nondet');
SELECT plan_add(5,  'numeric key, no support function 4',   'i_numeric',       'SELECT count(*) FROM t',  500000, 'i_numeric');
SELECT plan_add(6,  'float4 key, no support function 4',    'i_float4',        'SELECT count(*) FROM t',  500000, 'i_float4');
SELECT plan_add(6,  'float8 key, no support function 4',    'i_float8',        'SELECT count(*) FROM t',  500000, 'i_float8');
SELECT plan_add(7,  'two equal-image key columns',          'i_multi_ok',      'SELECT count(*) FROM t',  500000, 'i_multi_ok');
SELECT plan_add(7,  'two equal-image key columns, table 2', 'i2_ok',           'SELECT count(*) FROM t2', 500000, 'i2_ok');
SELECT plan_add(8,  'one column not equal-image',           'i_multi_bad',     'SELECT count(*) FROM t',  500000, 'i_multi_bad');
SELECT plan_add(9,  'expression key, numeric result',       'i_expr_num',      'SELECT count(*) FROM t',  500000, 'i_expr_num');
SELECT plan_add(9,  'expression key, nondeterministic',     'i_expr_lower_ci', 'SELECT count(*) FROM t',  500000, 'i_expr_lower_ci');
SELECT plan_add(10, 'INCLUDE column refused before lookup', 'i_inc',           'SELECT count(*) FROM t',  500000, 'i_inc');
-- 11 is retired; its three deduplicate_items = off legs are not built.
SELECT plan_add(12, 'opclass declaring no FUNCTION 4',      'i_ei_none',       'SELECT count(*) FROM t',  500000, 'i_ei_none');
SELECT plan_add(13, 'custom FUNCTION 4 returning false',    'i_ei_false',      'SELECT count(*) FROM t',  500000, 'i_ei_false');
SELECT plan_add(14, 'custom FUNCTION 4 returning true',     'i_ei_true',       'SELECT count(*) FROM t',  500000, 'i_ei_true');
SELECT plan_add(14, 'internal alias of btequalimage',       'i_ei_alias',      'SELECT count(*) FROM t',  500000, 'i_ei_alias');
SELECT plan_add(15, 'true then false callbacks',            'i_mixed_tf',      'SELECT count(*) FROM t',  500000, 'i_mixed_tf');
SELECT plan_add(15, 'false then true callbacks',            'i_mixed_ft',      'SELECT count(*) FROM t',  500000, 'i_mixed_ft');
SELECT plan_add(15, 'true then false, table 2',             'i2_tf',           'SELECT count(*) FROM t2', 500000, 'i2_tf');
SELECT plan_add(15, 'false then true, table 2',             'i2_ft',           'SELECT count(*) FROM t2', 500000, 'i2_ft');
SELECT plan_add(16, 'SQL impostor named btequalimage',      'i_squat',         'SELECT count(*) FROM t',  500000, 'i_squat');
SELECT plan_add(16, 'renamed internal btvarstrequalimage',  'i_text_det2',     'SELECT count(*) FROM t',  500000, 'i_text_det2');
SELECT plan_add(17, 'unique index over equal-image keys',   'i_uniq',          'SELECT count(*) FROM t',  500000, 'i_uniq');
UPDATE /* wiki_btree_gateplan_families */ plan SET grp = 'gate', want_stage = 'rebuild';
CALL /* wiki_btree_gateplan_assert_built */ assert_built();
SELECT count(*) AS planned_gate_fixtures FROM plan;
SELECT count(*) AS gate_baselines FROM snap WHERE phase = 'built';
SQL
  # The as-built gate reading, taken before the drain, so the credit decisions
  # this page already filed stay reproducible.  The candidate list is the plan,
  # not every index in the schema: the harness's own primary keys are in public
  # too, and bt_page_items(idx, 1) raises on an empty one, which is what a
  # second run of this stage first hit.
  f gate /dev/stdin <<'SQL'
DROP TABLE IF EXISTS gate_res;
CREATE TABLE gate_res AS
SELECT e.indexname, e.equalimage, e.wasted_space_pct AS wsp,
       e.wasted_space_pct_floor AS wspf, e.dedup_applies, e.tids_per_tuple,
       e.actual_bytes / 8192 AS blocks, e.caveats,
       (bt_metap(e.indexname)).allequalimage AS metapage,
       EXISTS (SELECT 1 FROM bt_page_items(e.indexname, 1) bi WHERE bi.tids IS NOT NULL)
                                                              AS posting_written
  FROM est_r2 e
 WHERE e.schemaname = 'public'
   AND e.indexname IN (SELECT idx FROM plan)
 ORDER BY e.indexname;
SQL
  t gate "SELECT /* wiki_btree_gate_rows */
                 indexname, blocks, equalimage, metapage, dedup_applies AS credited,
                 posting_written, wsp, wspf, tids_per_tuple, caveats
            FROM gate_res ORDER BY indexname" > "$OUT/gate.txt" 2>&1
  t gate "SELECT /* wiki_btree_gate_counters */
                 count(*) AS fixtures,
                 count(*) FILTER (WHERE dedup_applies AND NOT metapage) AS over_credit,
                 count(*) FILTER (WHERE equalimage = 'recognized' AND NOT metapage) AS recognized_wrong,
                 count(*) FILTER (WHERE equalimage = 'ineligible' AND metapage)     AS ineligible_wrong,
                 count(*) FILTER (WHERE equalimage = 'unknown' AND metapage)        AS under_credit,
                 max(greatest(wsp, wspf)) AS worst_reading
            FROM gate_res" >> "$OUT/gate.txt" 2>&1
  grep -c 'can safely use deduplication' "$OUT/gate_build.log" \
    | xargs printf 'DEBUG1 can safely use deduplication: %s\n' >> "$OUT/gate.txt"
  grep -c 'cannot use deduplication' "$OUT/gate_build.log" \
    | xargs printf 'DEBUG1 cannot use deduplication:      %s\n' >> "$OUT/gate.txt"
  tail -14 "$OUT/gate.txt" >&2
}

# ---------------------------------------------------------------- suite ------
stage_suite() {
  say "the numbered suite, build phase: 60 partial-index fixtures and controls 92-120"
  # A clean schema makes the stage idempotent; the harness goes back in first,
  # because its event trigger is what cuts each recipe at its index build, and
  # the views next, because the fixtures are read through them.
  q suite 'DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public'
  f suite "$SQLD/harness.sql" || die "harness install failed on suite"
  f suite "$SQLD/view_r2.sql"  || die "est_r2 view failed"
  f suite "$SQLD/view_old.sql" || die "est_old view failed"
  cat > "$SQLD/fixtures_suite.sql" <<'FIXTURES'
-- The numbered suite, build phase: tests 18-91 (partial indexes) and controls
-- 92-120, every recipe up to and including the index that is scored.  Rule 1
-- cuts each recipe there, and the harness event trigger takes the baseline at
-- the cut; rule 2's drain, rule 3's census and the catalog forgeries are the
-- churn stage.  Fixtures that carry churn of their own keep it here, so the
-- cut for those is the trigger rather than a file boundary.
-- pg_stat_force_next_flush() precedes every ANALYZE and every VACUUM, and
-- WITH (fillfactor = ...) precedes WHERE in CREATE INDEX.
--
-- Two rules of the shared suite decide what is below.  The retired numbers -
-- 38 with test 11's reloption legs, and 65, 67, 69, 106, 117, 121 and legs
-- 113a and 113c with the withheld-maintenance shape - are not built, and their
-- numbers are not reused.  The maintenance assumption then applies to every
-- fixture that keeps churn of its own: after those writes the recipe runs
-- VACUUM then ANALYZE on the table the churn touched, before the decide phase,
-- because that is the state a server with autovacuum on would have left.
--
-- Since 2026-09-16 each of those is one VACUUM (VERBOSE, ANALYZE) between
-- maint_begin() and maint_end(), which is what the shared suite's rule "The
-- maintenance must not be defeated" asks for: those two calls carry the
-- flush, the horizon probe, the timeout values actually in force and the
-- start and end stamps, and VERBOSE is what turns each statement's own "dead
-- but not yet removable" count into a number this run records.  Fixture 85 is
-- the one exception, and says so in place: its VACUUM precedes its index
-- build and must not analyze, because stale table statistics are the whole
-- point of that fixture.
--
-- All four settable timeouts are 0 in this session, which is what an
-- autovacuum worker forces on itself so that these settings cannot stop
-- regular maintenance.  The values are recorded per statement rather than
-- assumed, in maint.timeouts.
--
-- Disposable fixtures.  Everything below creates and drops objects in the
-- suite database of the sandbox cluster, whose public schema stage_suite has
-- just dropped.  It is not meant for a database anyone cares about.
SET /* wiki_btree_suite_client_min_messages */ client_min_messages = warning;
SET /* wiki_btree_suite_statement_timeout */ statement_timeout = 0;
SET /* wiki_btree_suite_lock_timeout */ lock_timeout = 0;
SET /* wiki_btree_suite_transaction_timeout */ transaction_timeout = 0;
SET /* wiki_btree_suite_idle_timeout */ idle_in_transaction_session_timeout = 0;
SET /* wiki_btree_suite_maintenance_work_mem */ maintenance_work_mem = '256MB';

-- ============================================================ 18-21 =========
-- Predicate selectivity.  One 1,000,000-row table, distinct bigint keys.
CREATE TABLE pt1 AS
SELECT i::bigint AS k, (i % 100)::int AS sel FROM generate_series(1, 1000000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pt1; SELECT pg_stat_force_next_flush();
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
SELECT pg_stat_force_next_flush(); ANALYZE pd22; SELECT pg_stat_force_next_flush();
CREATE INDEX p22 ON pd22 (k) WHERE hot;
SELECT plan_add(22, 'highly duplicated subset, unique outside', 'p22',
                'SELECT count(*) FROM pd22 WHERE hot', 100000);

CREATE TABLE pd23 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE ((i / 5) % 100)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd23; SELECT pg_stat_force_next_flush();
CREATE INDEX p23 ON pd23 (k) WHERE hot;
SELECT plan_add(23, 'highly unique subset, duplicated outside', 'p23',
                'SELECT count(*) FROM pd23 WHERE hot', 100000);

CREATE TABLE pd24 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50000)::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd24; SELECT pg_stat_force_next_flush();
CREATE INDEX p24 ON pd24 (k) WHERE hot;
SELECT plan_add(24, 'n_distinct radically different in the subset', 'p24',
                'SELECT count(*) FROM pd24 WHERE hot', 100000);

CREATE TABLE pd25 AS SELECT (i % 100 = 0) AS hot,
       CASE WHEN i % 100 = 0 THEN ((i / 100) % 997)::int ELSE (i % 5)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd25; SELECT pg_stat_force_next_flush();
CREATE INDEX p25 ON pd25 (k) WHERE hot;
SELECT plan_add(25, 'MCV distribution differs inside the subset', 'p25',
                'SELECT count(*) FROM pd25 WHERE hot', 5000);

CREATE TABLE pd26 AS SELECT (i % 50 = 0) AS hot,
       CASE WHEN i % 50 = 0 THEN (1000000 + i)::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd26; SELECT pg_stat_force_next_flush();
CREATE INDEX p26 ON pd26 (k) WHERE hot;
SELECT plan_add(26, 'table-wide MCVs absent inside the subset', 'p26',
                'SELECT count(*) FROM pd26 WHERE hot', 10000);

CREATE TABLE pd27 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 AND i % 100 <> 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd27; SELECT pg_stat_force_next_flush();
CREATE INDEX p27 ON pd27 (k) WHERE hot;
SELECT plan_add(27, 'NULL-heavy subset, non-NULL outside', 'p27',
                'SELECT count(*) FROM pd27 WHERE hot', 100000);

CREATE TABLE pd28 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN i::bigint ELSE NULL END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd28; SELECT pg_stat_force_next_flush();
CREATE INDEX p28 ON pd28 (k) WHERE hot;
SELECT plan_add(28, 'NULL-free subset, NULL-heavy table (bigint)', 'p28',
                'SELECT count(*) FROM pd28 WHERE hot', 25000);

CREATE TABLE pd29 AS
SELECT CASE WHEN i % 5 = 0 THEN NULL ELSE lpad(i::text, 20, '0') END AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd29; SELECT pg_stat_force_next_flush();
CREATE INDEX p29 ON pd29 (s) WHERE s IS NULL;
SELECT plan_add(29, 'all-NULL partial index, WHERE s IS NULL', 'p29',
                'SELECT count(*) FROM pd29 WHERE s IS NULL', 100000);

CREATE TABLE pd30 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd30; SELECT pg_stat_force_next_flush();
CREATE INDEX p30 ON pd30 (s) WHERE hot;
SELECT plan_add(30, 'subset values wider than outside (13 against 204 bytes)', 'p30',
                'SELECT count(*) FROM pd30 WHERE hot', 25000);

CREATE TABLE pd31 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN lpad((i % 9)::text, 12, 'n')
            ELSE repeat('W', 190) || lpad(i::text, 10, '0') END AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd31; SELECT pg_stat_force_next_flush();
CREATE INDEX p31 ON pd31 (s) WHERE hot;
SELECT plan_add(31, 'subset values narrower than outside', 'p31',
                'SELECT count(*) FROM pd31 WHERE hot', 25000);

-- 32 is the page's published recipe, verbatim.
CREATE TABLE pw32 AS
SELECT (i % 50 = 0) AS hot,
       CASE WHEN i % 50 = 0 THEN repeat('W', 390) || lpad(i::text, 10, '0')
            ELSE repeat('n', 18) || (i % 9)::text END AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pw32; SELECT pg_stat_force_next_flush();
CREATE INDEX p32 ON pw32 (s) WHERE hot;
SELECT plan_add(32, 'extreme width mismatch (27 against 404 bytes)', 'p32',
                'SELECT count(*) FROM pw32 WHERE hot', 10000);

CREATE TABLE pd33 AS SELECT (i % 5 = 0) AS hot,
       lpad(i::text, 10 + (i % 40), 'x') AS s FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd33; SELECT pg_stat_force_next_flush();
CREATE INDEX p33 ON pd33 (s) WHERE hot;
SELECT plan_add(33, 'variable-width values, same range inside and out', 'p33',
                'SELECT count(*) FROM pd33 WHERE hot', 100000);

-- ============================================================ 34-39 =========
CREATE TABLE pd34 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd34; SELECT pg_stat_force_next_flush();
CREATE INDEX p34 ON pd34 (k) WHERE hot;
SELECT plan_add(34, 'dedup-heavy subset, 1000 rows per key', 'p34',
                'SELECT count(*) FROM pd34 WHERE hot', 100000);

CREATE TABLE pd35 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd35; SELECT pg_stat_force_next_flush();
CREATE INDEX p35 ON pd35 (k) WHERE hot;
SELECT plan_add(35, 'duplicate-heavy table, unique subset', 'p35',
                'SELECT count(*) FROM pd35 WHERE hot', 100000);

CREATE TABLE pd36 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN 42 ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd36; SELECT pg_stat_force_next_flush();
CREATE INDEX p36 ON pd36 (k) WHERE hot;
SELECT plan_add(36, 'one key group, 100,000 TIDs against a 132 cap', 'p36',
                'SELECT count(*) FROM pd36 WHERE hot', 100000);

CREATE TABLE pd37 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd37; SELECT pg_stat_force_next_flush();
CREATE INDEX p37 ON pd37 (k) WHERE hot;
SELECT plan_add(37, 'NULL deduplication, every subset key NULL', 'p37',
                'SELECT count(*) FROM pd37 WHERE hot', 100000);

-- 38 built p38 here, a partial index with deduplicate_items = off.  Retired
-- with test 11 on 2026-09-12: explicit deduplication settings are outside the
-- shared suite, and the number is not reused.

CREATE TABLE pd39 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd39; SELECT pg_stat_force_next_flush();
CREATE UNIQUE INDEX p39 ON pd39 (k) WHERE hot;
SELECT plan_add(39, 'partial UNIQUE index', 'p39',
                'SELECT count(*) FROM pd39 WHERE hot', 100000);

-- ============================================================ 40-47 =========
CREATE TABLE pd40 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 97)::int  END AS b
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd40; SELECT pg_stat_force_next_flush();
CREATE INDEX p40 ON pd40 (a, b) WHERE hot;
SELECT plan_add(40, 'two-column key correlated only in the subset', 'p40',
                'SELECT count(*) FROM pd40 WHERE hot', 100000);

CREATE TABLE pd41 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 97)::int  ELSE (i % 100)::int END AS b
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd41; SELECT pg_stat_force_next_flush();
CREATE INDEX p41 ON pd41 (a, b) WHERE hot;
SELECT plan_add(41, 'two-column key independent only in the subset', 'p41',
                'SELECT count(*) FROM pd41 WHERE hot', 100000);

CREATE TABLE pd42 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50)::int ELSE i::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 50)::int ELSE i::int END AS b
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd42; SELECT pg_stat_force_next_flush();
CREATE INDEX p42 ON pd42 (a, b) WHERE hot;
SELECT plan_add(42, 'multi-column duplicate keys in the subset', 'p42',
                'SELECT count(*) FROM pd42 WHERE hot', 100000);

CREATE TABLE pd43 AS SELECT (i % 5 = 0) AS hot, i::int AS a, (i * 2)::int AS b
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd43; SELECT pg_stat_force_next_flush();
CREATE INDEX p43 ON pd43 (a, b) WHERE hot;
SELECT plan_add(43, 'multi-column unique keys in the subset', 'p43',
                'SELECT count(*) FROM pd43 WHERE hot', 100000);

-- 44: the same correlated shape with and without a CREATE STATISTICS object.
--     Two tables, because one ANALYZE would repair both legs at once.
CREATE TABLE pd44a AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd44a; SELECT pg_stat_force_next_flush();
CREATE INDEX p44a ON pd44a (a, b) WHERE hot;
SELECT plan_add(44, 'multicolumn key, no ndistinct object', 'p44a',
                'SELECT count(*) FROM pd44a WHERE hot', 100000);
CREATE TABLE pd44b AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS pd44b_nd (ndistinct) ON a, b FROM pd44b;
SELECT pg_stat_force_next_flush(); ANALYZE pd44b; SELECT pg_stat_force_next_flush();
CREATE INDEX p44b ON pd44b (a, b) WHERE hot;
SELECT plan_add(44, 'multicolumn key, with CREATE STATISTICS (ndistinct)', 'p44b',
                'SELECT count(*) FROM pd44b WHERE hot', 100000, 'ndistinct');

CREATE TABLE pd45 AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 97)::int  ELSE (i % 100)::int END AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS pd45_nd (ndistinct) ON a, b FROM pd45;
SELECT pg_stat_force_next_flush(); ANALYZE pd45; SELECT pg_stat_force_next_flush();
CREATE INDEX p45 ON pd45 (a, b) WHERE hot;
SELECT plan_add(45, 'extended statistics wrong for the subset', 'p45',
                'SELECT count(*) FROM pd45 WHERE hot', 100000);

CREATE TABLE pd46 AS SELECT (i % 5 = 0) AS hot, i::int AS k, (i % 7)::int AS pay
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pd46; SELECT pg_stat_force_next_flush();
CREATE INDEX p46 ON pd46 (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(46, 'partial index with INCLUDE columns', 'p46',
                'SELECT count(*) FROM pd46 WHERE hot', 100000);

CREATE TABLE pi47 AS SELECT (i % 20 = 0) AS hot, i::int AS k,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS payload
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pi47; SELECT pg_stat_force_next_flush();
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
SELECT pg_stat_force_next_flush(); ANALYZE pe48; SELECT pg_stat_force_next_flush();
CREATE INDEX p48 ON pe48 (lower(name)) WHERE active;
SELECT plan_add(48, 'partial expression index, lower(name) WHERE active', 'p48',
                'SELECT count(*) FROM pe48 WHERE active', 100000);
CREATE TABLE pe48b AS SELECT (i % 5 = 0) AS active,
       CASE WHEN i % 5 = 0 THEN 'NAME' || lpad(((i / 5) % 20)::text, 6, '0')
            ELSE 'name' || lpad((i % 100)::text, 6, '0') END AS name
  FROM generate_series(1, 500000) i;
CREATE INDEX p48b ON pe48b (lower(name)) WHERE active;
SELECT pg_stat_force_next_flush(); ANALYZE pe48b; SELECT pg_stat_force_next_flush();
SELECT plan_add(48, 'the same after one ANALYZE with the index in place', 'p48b',
                'SELECT count(*) FROM pe48b WHERE active', 100000, 'after analyze');

CREATE TABLE pe49 AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pe49; SELECT pg_stat_force_next_flush();
CREATE INDEX p49 ON pe49 (upper(s)) WHERE hot;
SELECT plan_add(49, 'expression width mismatch in the subset', 'p49',
                'SELECT count(*) FROM pe49 WHERE hot', 25000);
CREATE TABLE pe49b AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX p49b ON pe49b (upper(s)) WHERE hot;
SELECT pg_stat_force_next_flush(); ANALYZE pe49b; SELECT pg_stat_force_next_flush();
SELECT plan_add(49, 'the same after one ANALYZE with the index in place', 'p49b',
                'SELECT count(*) FROM pe49b WHERE hot', 25000, 'after analyze');

CREATE TABLE pe50 AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pe50; SELECT pg_stat_force_next_flush();
CREATE INDEX p50 ON pe50 (upper(s)) WHERE hot;   -- real width 101, fallback 32
SELECT plan_add(50, 'missing expression statistics, 32-byte fallback', 'p50',
                'SELECT count(*) FROM pe50 WHERE hot', 100000);
CREATE TABLE pe50b AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX p50b ON pe50b (upper(s)) WHERE hot;
SELECT pg_stat_force_next_flush(); ANALYZE pe50b; SELECT pg_stat_force_next_flush();
SELECT plan_add(50, 'the same after one ANALYZE with the index in place', 'p50b',
                'SELECT count(*) FROM pe50b WHERE hot', 100000, 'after analyze');

CREATE COLLATION suite_det    (provider = icu, locale = 'und');
CREATE COLLATION suite_nondet (provider = icu, locale = 'und-u-ks-level2',
                               deterministic = false);
CREATE TABLE pc51 AS SELECT (i % 5 = 0) AS hot,
       'key' || lpad(((i / 5) % 100)::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pc51; SELECT pg_stat_force_next_flush();
CREATE INDEX p51 ON pc51 (s COLLATE suite_det) WHERE hot;
CREATE INDEX p52 ON pc51 (s COLLATE suite_nondet) WHERE hot;
SELECT plan_add(51, 'deterministic ICU collation', 'p51',
                'SELECT count(*) FROM pc51 WHERE hot', 100000);
SELECT plan_add(52, 'nondeterministic ICU collation', 'p52',
                'SELECT count(*) FROM pc51 WHERE hot', 100000);

CREATE TABLE pf AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pf; SELECT pg_stat_force_next_flush();
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
SELECT pg_stat_force_next_flush(); ANALYZE ps; SELECT pg_stat_force_next_flush();
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
-- 64: inserts into the subset, then the maintenance VACUUM ANALYZE.  The
-- fixture's point is what the statistics say about a grown subset; under the
-- maintenance assumption they say it after an ANALYZE, not before one.
CREATE TABLE pc64 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pc64; SELECT pg_stat_force_next_flush();
CREATE INDEX p64 ON pc64 (k) WHERE hot;
INSERT INTO pc64 SELECT true, 500000 + i FROM generate_series(1, 200000) i;
SELECT maint_begin('pc64');
VACUUM (VERBOSE, ANALYZE) pc64;
SELECT maint_end('pc64');
SELECT plan_add(64, 'inserts into the subset, then VACUUM + ANALYZE', 'p64',
                'SELECT count(*) FROM pc64 WHERE hot', 300000);

-- 65 built p65, deletes with no VACUUM, and 67 built p67, rows leaving the
-- index with no VACUUM.  Both are retired: the maintenance assumption forbids
-- churn a VACUUM never followed, and the numbers are not reused.

-- 66: rows entering the index (false -> true), then VACUUM + ANALYZE.
CREATE TABLE pc66 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pc66; SELECT pg_stat_force_next_flush();
CREATE INDEX p66 ON pc66 (k) WHERE hot;
UPDATE pc66 SET hot = true WHERE NOT hot AND k % 5 = 1;
SELECT maint_begin('pc66');
VACUUM (VERBOSE, ANALYZE) pc66;
SELECT maint_end('pc66');
SELECT plan_add(66, 'rows entering the index, then VACUUM + ANALYZE', 'p66',
                'SELECT count(*) FROM pc66 WHERE hot', 200000);

-- 68: heavy predicate churn, then VACUUM + ANALYZE.
CREATE TABLE pc68 AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pc68; SELECT pg_stat_force_next_flush();
CREATE INDEX p68 ON pc68 (k) WHERE hot;
UPDATE pc68 SET hot = true  WHERE k % 3 = 0;
UPDATE pc68 SET hot = false WHERE k % 3 = 0;
UPDATE pc68 SET hot = true  WHERE k % 3 = 1;
UPDATE pc68 SET hot = false WHERE k % 3 = 1;
UPDATE pc68 SET hot = (k % 10 = 0);
SELECT maint_begin('pc68');
VACUUM (VERBOSE, ANALYZE) pc68;
SELECT maint_end('pc68');
SELECT plan_add(68, 'heavy predicate churn, then VACUUM + ANALYZE', 'p68',
                'SELECT count(*) FROM pc68 WHERE hot', 50000);

-- 69 built p69, a VACUUM with the following ANALYZE withheld.  Retired: the
-- maintenance assumption runs both, so the shape cannot be reached, and the
-- number is not reused.

-- ============================================================ 70-77 =========
CREATE TABLE pb AS SELECT (i % 5 = 0) AS hot, i::int AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pb; SELECT pg_stat_force_next_flush();
CREATE INDEX p70 ON pb (k) WHERE hot;
SELECT plan_add(70, 'freshly created partial index', 'p70',
                'SELECT count(*) FROM pb WHERE hot', 100000);
CREATE INDEX p71 ON pb (k) WHERE hot;
REINDEX INDEX p71;
SELECT plan_add(71, 'freshly REINDEXed partial index', 'p71',
                'SELECT count(*) FROM pb WHERE hot', 100000);

CREATE TABLE pb72 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pb72; SELECT pg_stat_force_next_flush();
CREATE INDEX p72 ON pb72 (k) WHERE hot;
DELETE FROM pb72 WHERE hot AND (k / 5) % 4 = 0;
SELECT maint_begin('pb72');
VACUUM (VERBOSE, ANALYZE) pb72;
SELECT maint_end('pb72');
SELECT plan_add(72, '25% of the subset deleted', 'p72', 'SELECT count(*) FROM pb72 WHERE hot', 75000);

CREATE TABLE pb73 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pb73; SELECT pg_stat_force_next_flush();
CREATE INDEX p73 ON pb73 (k) WHERE hot;
DELETE FROM pb73 WHERE hot AND (k / 5) % 2 = 0;
SELECT maint_begin('pb73');
VACUUM (VERBOSE, ANALYZE) pb73;
SELECT maint_end('pb73');
SELECT plan_add(73, '50% of the subset deleted', 'p73', 'SELECT count(*) FROM pb73 WHERE hot', 50000);

CREATE TABLE pb74 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pb74; SELECT pg_stat_force_next_flush();
CREATE INDEX p74 ON pb74 (k) WHERE hot;
DELETE FROM pb74 WHERE hot AND (k / 5) % 4 <> 0;
SELECT maint_begin('pb74');
VACUUM (VERBOSE, ANALYZE) pb74;
SELECT maint_end('pb74');
SELECT plan_add(74, '75% of the subset deleted', 'p74', 'SELECT count(*) FROM pb74 WHERE hot', 25000);

-- 75 is the corrected recipe: 90% of the subset, not the whole of it.
CREATE TABLE pb75 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pb75; SELECT pg_stat_force_next_flush();
CREATE INDEX p75 ON pb75 (k) WHERE hot;
DELETE FROM pb75 WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('pb75');
VACUUM (VERBOSE, ANALYZE) pb75;
SELECT maint_end('pb75');
SELECT plan_add(75, '90% of the subset deleted (corrected recipe)', 'p75',
                'SELECT count(*) FROM pb75 WHERE hot', 10000);

CREATE TABLE pb76 AS SELECT (i % 5 = 0) AS hot, i::int AS k, 'x'::text AS pad
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pb76; SELECT pg_stat_force_next_flush();
CREATE INDEX p76 ON pb76 (k) WHERE hot;
UPDATE pb76 SET k = k + 1000000 WHERE hot;
SELECT maint_begin('pb76');
VACUUM (VERBOSE, ANALYZE) pb76;
SELECT maint_end('pb76');
SELECT plan_add(76, 'bloated through indexed-key UPDATEs', 'p76',
                'SELECT count(*) FROM pb76 WHERE hot', 100000);

CREATE TABLE pb77 AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE pb77; SELECT pg_stat_force_next_flush();
CREATE INDEX p77 ON pb77 (k) WHERE hot;
DELETE FROM pb77 WHERE hot AND k < 475000;          -- contiguous 95%
SELECT maint_begin('pb77');
VACUUM (VERBOSE, ANALYZE) pb77;
SELECT maint_end('pb77');
SELECT plan_add(77, 'many empty and deleted B-tree pages', 'p77',
                'SELECT count(*) FROM pb77 WHERE hot', 5001);

-- ============================================================ 78-85 =========
-- Critical-false-positive constructions.  Every index is freshly built.
CREATE TABLE f78t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 290) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f78t; SELECT pg_stat_force_next_flush();
CREATE INDEX f78 ON f78t (s) WHERE hot;
SELECT plan_add(78, 'predicate-conditioned width mismatch', 'f78',
                'SELECT count(*) FROM f78t WHERE hot', 25000);

CREATE TABLE f79t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('t', 300) || lpad(i::text, 4, '0')
            ELSE NULL END AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f79t; SELECT pg_stat_force_next_flush();
CREATE INDEX f79 ON f79t (s) WHERE hot;
SELECT plan_add(79, 'predicate-conditioned NULL mismatch', 'f79',
                'SELECT count(*) FROM f79t WHERE hot', 25000);

CREATE TABLE f80t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN i::int ELSE (i % 3)::int END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f80t; SELECT pg_stat_force_next_flush();
CREATE INDEX f80 ON f80t (k) WHERE hot;
SELECT plan_add(80, 'predicate-conditioned n_distinct mismatch', 'f80',
                'SELECT count(*) FROM f80t WHERE hot', 100000);

CREATE TABLE f81t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 20)::int ELSE 7 END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f81t; SELECT pg_stat_force_next_flush();
CREATE INDEX f81 ON f81t (k) WHERE hot;
SELECT plan_add(81, 'predicate-conditioned MCV mismatch', 'f81',
                'SELECT count(*) FROM f81t WHERE hot', 100000);

CREATE TABLE f82t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 100)::int END AS a,
       CASE WHEN i % 5 = 0 THEN ((i / 5) % 100)::int ELSE (i % 89)::int  END AS b
  FROM generate_series(1, 500000) i;
CREATE STATISTICS f82_nd (ndistinct) ON a, b FROM f82t;
SELECT pg_stat_force_next_flush(); ANALYZE f82t; SELECT pg_stat_force_next_flush();
CREATE INDEX f82 ON f82t (a, b) WHERE hot;
SELECT plan_add(82, 'predicate-conditioned multi-column correlation', 'f82',
                'SELECT count(*) FROM f82t WHERE hot', 100000);

CREATE TABLE f83t AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f83t; SELECT pg_stat_force_next_flush();
CREATE INDEX f83 ON f83t (md5(s), lower(s)) WHERE hot;    -- no statistics row
SELECT plan_add(83, 'missing index/expression statistics', 'f83',
                'SELECT count(*) FROM f83t WHERE hot', 100000);

CREATE TABLE f84t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f84t; SELECT pg_stat_force_next_flush();
CREATE INDEX f84 ON f84t (k) WHERE hot;
-- The forged count is written by the churn stage, after the rule 3 census: an
-- ANALYZE of f84t rewrites reltuples for the table and for every index on it,
-- so a forgery written here would be silently repaired and the fixture would
-- stop testing anything.
SELECT plan_add(84, 'stale partial-index reltuples', 'f84',
                'SELECT count(*) FROM f84t WHERE hot', 100000);

CREATE TABLE f85t AS SELECT (i % 5 = 0) AS hot, lpad(i::text, 8, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f85t; SELECT pg_stat_force_next_flush();
UPDATE f85t SET s = repeat('W', 200) || s WHERE hot;   -- table statistics now stale
-- VACUUM without ANALYZE, deliberately and uniquely: the UPDATE above is what
-- makes this fixture's table statistics stale, and analyzing here would repair
-- the very trap test 85 is.  It is still bracketed, so the no-defeat proofs
-- cover it too, and its source column reads 'prebuild' because it precedes the
-- index build rather than following a churn.
SELECT maint_begin('f85t', 'prebuild');
VACUUM (VERBOSE) f85t;
SELECT maint_end('f85t');
CREATE INDEX f85 ON f85t (s) WHERE hot;
SELECT plan_add(85, 'stale table statistics', 'f85',
                'SELECT count(*) FROM f85t WHERE hot', 100000);

-- ============================================================ 86-91 =========
-- Critical-false-negative constructions: genuinely bloated, VACUUMed, ANALYZEd.
CREATE TABLE f86t AS SELECT (i % 5 = 0) AS hot, ((i / 5) % 100)::int AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f86t; SELECT pg_stat_force_next_flush();
CREATE INDEX f86 ON f86t (k) WHERE hot;
DELETE FROM f86t WHERE hot AND k >= 25;
SELECT maint_begin('f86t');
VACUUM (VERBOSE, ANALYZE) f86t;
SELECT maint_end('f86t');
SELECT plan_add(86, 'duplicate concentration inside the subset', 'f86',
                'SELECT count(*) FROM f86t WHERE hot', 25000);

CREATE TABLE f87t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN NULL ELSE i::int END AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f87t; SELECT pg_stat_force_next_flush();
CREATE INDEX f87 ON f87t (k) WHERE hot;
DELETE FROM f87t WHERE hot AND k IS NOT NULL;
SELECT maint_begin('f87t');
VACUUM (VERBOSE, ANALYZE) f87t;
SELECT maint_end('f87t');
SELECT plan_add(87, 'NULL concentration inside the subset', 'f87',
                'SELECT count(*) FROM f87t WHERE hot', 25000);

CREATE TABLE f88t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN lpad((i % 9)::text, 9, '0')
            ELSE repeat('W', 390) || lpad(i::text, 10, '0') END AS s
  FROM generate_series(1, 200000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f88t; SELECT pg_stat_force_next_flush();
CREATE INDEX f88 ON f88t (s) WHERE hot;
DELETE FROM f88t WHERE hot AND s > lpad('4', 9, '0');
SELECT maint_begin('f88t');
VACUUM (VERBOSE, ANALYZE) f88t;
SELECT maint_end('f88t');
SELECT plan_add(88, 'subset narrower than table statistics', 'f88', NULL, NULL);

CREATE TABLE f89t AS SELECT (i % 5 = 0) AS hot,
       ((i / 5) % 100)::int AS a, ((i / 5) % 100)::int AS b
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f89t; SELECT pg_stat_force_next_flush();
CREATE INDEX f89 ON f89t (a, b) WHERE hot;
DELETE FROM f89t WHERE hot AND a >= 25;
SELECT maint_begin('f89t');
VACUUM (VERBOSE, ANALYZE) f89t;
SELECT maint_end('f89t');
SELECT plan_add(89, 'conditional multi-column correlation', 'f89',
                'SELECT count(*) FROM f89t WHERE hot', 25000);

CREATE TABLE f90t AS SELECT (i % 5 = 0) AS hot, ((i / 5) % 1000)::int AS k
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f90t; SELECT pg_stat_force_next_flush();
CREATE INDEX f90 ON f90t (k) WHERE hot;
DELETE FROM f90t WHERE hot AND k >= 250;
SELECT maint_begin('f90t');
VACUUM (VERBOSE, ANALYZE) f90t;
SELECT maint_end('f90t');
SELECT plan_add(90, 'real deduplication stronger than predicted', 'f90',
                'SELECT count(*) FROM f90t WHERE hot', 25000);

CREATE TABLE f91t AS SELECT (i % 5 = 0) AS hot,
       CASE WHEN i % 5 = 0 THEN lpad((i % 9)::text, 9, '0')
            ELSE repeat('W', 390) || lpad(i::text, 10, '0') END AS s,
       i::int AS ord
  FROM generate_series(1, 200000) i;
SELECT pg_stat_force_next_flush(); ANALYZE f91t; SELECT pg_stat_force_next_flush();
CREATE INDEX f91 ON f91t (s) WHERE hot;
DELETE FROM f91t WHERE hot AND ord < 190000;         -- contiguous 95%
SELECT maint_begin('f91t');
VACUUM (VERBOSE, ANALYZE) f91t;
SELECT maint_end('f91t');
SELECT plan_add(91, 'many deleted pages plus an over-predicting model', 'f91',
                'SELECT count(*) FROM f91t WHERE hot', 2001);

-- ============================================================ 92-95 =========
-- Change B threshold calibration: a genuinely reclaimable partial index,
-- disturbed by a known number of row changes, with and without reloptions.
-- Under the maintenance assumption each of the four runs VACUUM then ANALYZE
-- after its UPDATE, so all four reach the decide phase analyzed and the
-- reloption pair no longer decides what rule 3's census does to them; the
-- concept page records that cost as an open question.
CREATE TABLE b92t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE b92t; SELECT pg_stat_force_next_flush();
CREATE INDEX b92 ON b92t (k) WHERE hot;
DELETE FROM b92t WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('b92t');
VACUUM (VERBOSE, ANALYZE) b92t;
SELECT maint_end('b92t');
UPDATE b92t SET k = k WHERE k % 500 = 0;              -- 1,000 rows changed
SELECT maint_begin('b92t');
VACUUM (VERBOSE, ANALYZE) b92t;
SELECT maint_end('b92t');
SELECT plan_add(92, '1,000 rows updated under the GUC threshold', 'b92',
                'SELECT count(*) FROM b92t WHERE hot', 10000);

CREATE TABLE b93t AS SELECT (i % 5 = 0) AS hot, i::int AS k FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE b93t; SELECT pg_stat_force_next_flush();
CREATE INDEX b93 ON b93t (k) WHERE hot;
DELETE FROM b93t WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('b93t');
VACUUM (VERBOSE, ANALYZE) b93t;
SELECT maint_end('b93t');
UPDATE b93t SET k = k WHERE k % 2 = 0;                -- above the trigger
SELECT maint_begin('b93t');
VACUUM (VERBOSE, ANALYZE) b93t;
SELECT maint_end('b93t');
SELECT plan_add(93, 'rows updated above the GUC threshold', 'b93',
                'SELECT count(*) FROM b93t WHERE hot', 10000);

CREATE TABLE b94t (hot bool, k int)
  WITH (autovacuum_analyze_threshold = 100, autovacuum_analyze_scale_factor = 0);
INSERT INTO b94t SELECT (i % 5 = 0), i FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE b94t; SELECT pg_stat_force_next_flush();
CREATE INDEX b94 ON b94t (k) WHERE hot;
DELETE FROM b94t WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('b94t');
VACUUM (VERBOSE, ANALYZE) b94t;
SELECT maint_end('b94t');
UPDATE b94t SET k = k WHERE k % 500 = 0;              -- 1,000 > the reloption
SELECT maint_begin('b94t');
VACUUM (VERBOSE, ANALYZE) b94t;
SELECT maint_end('b94t');
SELECT plan_add(94, '1,000 rows updated, table reloption threshold 100', 'b94',
                'SELECT count(*) FROM b94t WHERE hot', 10000);

CREATE TABLE b95t (hot bool, k int)
  WITH (autovacuum_analyze_threshold = 200000, autovacuum_analyze_scale_factor = 1);
INSERT INTO b95t SELECT (i % 5 = 0), i FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE b95t; SELECT pg_stat_force_next_flush();
CREATE INDEX b95 ON b95t (k) WHERE hot;
DELETE FROM b95t WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('b95t');
VACUUM (VERBOSE, ANALYZE) b95t;
SELECT maint_end('b95t');
UPDATE b95t SET k = k WHERE k % 2 = 0;                -- below the reloption
SELECT maint_begin('b95t');
VACUUM (VERBOSE, ANALYZE) b95t;
SELECT maint_end('b95t');
SELECT plan_add(95, 'many rows updated, table reloption threshold 200,000', 'b95',
                'SELECT count(*) FROM b95t WHERE hot', 10000);

-- ============================================================ 96-99 =========
-- Non-partial controls: the partial-only exclusions must not reach them.
CREATE TABLE np AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE np; SELECT pg_stat_force_next_flush();
CREATE INDEX np96 ON np (k);
CREATE INDEX np97 ON np (upper(s));                   -- no statistics row
SELECT plan_add(96, 'plain index, fresh statistics', 'np96', 'SELECT count(*) FROM np', 500000);
SELECT plan_add(97, 'expression index, no statistics row', 'np97', 'SELECT count(*) FROM np', 500000);

CREATE TABLE np98t AS SELECT i::int AS k FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE np98t; SELECT pg_stat_force_next_flush();
CREATE INDEX np98 ON np98t (k);
INSERT INTO np98t SELECT 500000 + i FROM generate_series(1, 300000) i;
SELECT maint_begin('np98t');
VACUUM (VERBOSE, ANALYZE) np98t;
SELECT maint_end('np98t');
SELECT plan_add(98, 'plain index, 300,000 inserts then VACUUM + ANALYZE', 'np98',
                'SELECT count(*) FROM np98t', 800000);

-- 99: the corrected recipe.  An index and a table cannot share a name, so the
-- table is np99t and the index np99.
CREATE TABLE np99t AS SELECT (i % 1000)::int AS k FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE np99t; SELECT pg_stat_force_next_flush();
CREATE INDEX np99 ON np99t (k);
DELETE FROM np99t WHERE k >= 60;
SELECT maint_begin('np99t');
VACUUM (VERBOSE, ANALYZE) np99t;
SELECT maint_end('np99t');
SELECT plan_add(99, 'duplicate-heavy index, genuinely reclaimable', 'np99',
                'SELECT count(*) FROM np99t', 30000);

-- =========================================================== 100-105 ========
-- The variable-width INCLUDE family.
CREATE TABLE i100t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE i100t; SELECT pg_stat_force_next_flush();
CREATE INDEX i100 ON i100t (k) INCLUDE (pay) WHERE hot;
DELETE FROM i100t WHERE hot AND (k / 5) % 10 <> 0;
SELECT maint_begin('i100t');
VACUUM (VERBOSE, ANALYZE) i100t;
SELECT maint_end('i100t');
SELECT plan_add(100, 'partial + INCLUDE (text), 90% of the subset deleted', 'i100',
                'SELECT count(*) FROM i100t WHERE hot', 10000);

CREATE TABLE i101t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE i101t; SELECT pg_stat_force_next_flush();
CREATE INDEX i101 ON i101t (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(101, 'partial + INCLUDE (text), same width inside and outside', 'i101',
                'SELECT count(*) FROM i101t WHERE hot', 100000);

CREATE TABLE i102t AS SELECT i::int AS k, lpad(i::text, 60, '0') AS pay
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE i102t; SELECT pg_stat_force_next_flush();
CREATE INDEX i102 ON i102t (k) INCLUDE (pay);
SELECT plan_add(102, 'non-partial + wide INCLUDE (text), freshly built', 'i102',
                'SELECT count(*) FROM i102t', 500000);

CREATE TABLE i103t AS SELECT (i % 20 = 0) AS hot,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad(i::text, 12, 'n') END AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE i103t; SELECT pg_stat_force_next_flush();
CREATE INDEX i103 ON i103t (s) WHERE hot;
SELECT plan_add(103, 'partial + wide key column, unique values, no caveat', 'i103',
                'SELECT count(*) FROM i103t WHERE hot', 25000);

CREATE TABLE i104t AS SELECT (i % 20 = 0) AS hot, i::int AS k,
       CASE WHEN i % 20 = 0 THEN lpad((i % 9)::text, 12, 'n')
            ELSE repeat('W', 190) || lpad(i::text, 10, '0') END AS pay
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE i104t; SELECT pg_stat_force_next_flush();
CREATE INDEX i104 ON i104t (k) INCLUDE (pay) WHERE hot;
SELECT plan_add(104, 'partial + INCLUDE (text) narrower inside the subset', 'i104',
                'SELECT count(*) FROM i104t WHERE hot', 25000);

CREATE TABLE i105t AS SELECT (i % 20 = 0) AS hot, i::int AS k, (i % 7)::int AS n,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad((i % 9)::text, 12, 'n') END AS pay
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE i105t; SELECT pg_stat_force_next_flush();
CREATE INDEX i105 ON i105t (k) INCLUDE (n, pay) WHERE hot;
SELECT plan_add(105, 'partial + INCLUDE (int, text), mixed non-key widths', 'i105',
                'SELECT count(*) FROM i105t WHERE hot', 25000);

-- =========================================================== 107-112 ========
-- The expression-statistics family.  106 built x106, a 90 % delete vacuumed
-- with the following ANALYZE withheld; it is retired and its number is not
-- reused, so 107 is this family's first fixture and is the same recipe with
-- the maintenance ANALYZE the assumption requires.
CREATE TABLE x107t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE x107t; SELECT pg_stat_force_next_flush();
CREATE INDEX x107 ON x107t (upper(s));
DELETE FROM x107t WHERE k % 10 <> 0;
SELECT maint_begin('x107t');
VACUUM (VERBOSE, ANALYZE) x107t;
SELECT maint_end('x107t');
SELECT plan_add(107, 'the same, with one ANALYZE after the build', 'x107',
                'SELECT count(*) FROM x107t', 50000);

CREATE TABLE x108t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
CREATE INDEX x108 ON x108t (upper(s));                -- table never analysed
SELECT pg_stat_force_next_flush();
SELECT plan_add(108, 'expression index on a never-analysed table', 'x108',
                'SELECT count(*) FROM x108t', 500000);

CREATE TABLE x109t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
ALTER TABLE x109t ALTER COLUMN s SET STATISTICS 0;
SELECT pg_stat_force_next_flush(); ANALYZE x109t; SELECT pg_stat_force_next_flush();
CREATE INDEX x109 ON x109t (s);
SELECT plan_add(109, 'plain index, key column with SET STATISTICS 0', 'x109',
                'SELECT count(*) FROM x109t', 500000);

CREATE TABLE x110t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE x110t; SELECT pg_stat_force_next_flush();
CREATE INDEX x110 ON x110t (k, upper(s));             -- mixed key, no stats row
SELECT plan_add(110, 'mixed key (k, upper(s)), no statistics row', 'x110',
                'SELECT count(*) FROM x110t', 500000);

CREATE TABLE x111t AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE x111t; SELECT pg_stat_force_next_flush();
CREATE INDEX x111 ON x111t (left(s, 3));              -- narrow expression
SELECT plan_add(111, 'narrow expression left(s, 3), no statistics row', 'x111',
                'SELECT count(*) FROM x111t', 500000);

CREATE TABLE x112t AS SELECT (i % 5 = 0) AS hot, i::int AS k, lpad(i::text, 100, '0') AS s
  FROM generate_series(1, 500000) i;
SELECT pg_stat_force_next_flush(); ANALYZE x112t; SELECT pg_stat_force_next_flush();
CREATE INDEX x112 ON x112t (upper(s)) WHERE hot;      -- partial expression
SELECT plan_add(112, 'partial expression index, no statistics row', 'x112',
                'SELECT count(*) FROM x112t WHERE hot', 100000);

-- =========================================================== 113-120 ========
-- The drained queue.  113 had three legs; a and c ran no VACUUM and no
-- ANALYZE respectively, so both are retired and only leg b, the maintained
-- one, is built.
CREATE TABLE q113b AS SELECT i::int AS id, 'pending'::text AS state
  FROM generate_series(1, 1000000) i;
SELECT pg_stat_force_next_flush(); ANALYZE q113b; SELECT pg_stat_force_next_flush();
CREATE INDEX p113b ON q113b (id) WHERE state = 'pending';
UPDATE q113b SET state = 'done';
SELECT maint_begin('q113b');
VACUUM (VERBOSE, ANALYZE) q113b;
SELECT maint_end('q113b');
SELECT plan_add(113, 'drained queue, VACUUM + ANALYZE', 'p113b',
                'SELECT count(*) FROM q113b WHERE state = ''pending''', 0, 'b');

-- 114: a genuine, fully repaired detection on the same queue shape.
CREATE TABLE q114 AS SELECT i::int AS id, 'pending'::text AS state
  FROM generate_series(1, 1000000) i;
SELECT pg_stat_force_next_flush(); ANALYZE q114; SELECT pg_stat_force_next_flush();
CREATE INDEX p114 ON q114 (id) WHERE state = 'pending';
UPDATE q114 SET state = 'done' WHERE id % 100 <> 0;
SELECT maint_begin('q114');
VACUUM (VERBOSE, ANALYZE) q114;
SELECT maint_end('q114');
SELECT plan_add(114, 'queue drained to 1%, VACUUM + ANALYZE', 'p114',
                'SELECT count(*) FROM q114 WHERE state = ''pending''', 10000);

-- 115: index built on an analysed empty table, then loaded, then maintained.
CREATE TABLE q115(id int, state text);
SELECT pg_stat_force_next_flush(); ANALYZE q115; SELECT pg_stat_force_next_flush();
CREATE INDEX p115 ON q115 (id) WHERE state = 'pending';
INSERT INTO q115 SELECT i, 'pending' FROM generate_series(1, 1000000) i;
SELECT maint_begin('q115');
VACUUM (VERBOSE, ANALYZE) q115;
SELECT maint_end('q115');
SELECT plan_add(115, 'index built on an analysed empty table, then loaded', 'p115',
                'SELECT count(*) FROM q115 WHERE state = ''pending''', 1000000);

-- 116: a subset that is genuinely empty and was measured empty.
CREATE TABLE q116 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p116 ON q116 (id) WHERE state = 'pending';
SELECT pg_stat_force_next_flush(); ANALYZE q116; SELECT pg_stat_force_next_flush();
SELECT plan_add(116, 'subset empty from the start and measured empty', 'p116',
                'SELECT count(*) FROM q116 WHERE state = ''pending''', 0);

-- 117 built p117, a drained queue vacuumed with the following ANALYZE
-- withheld.  Retired; the number is not reused.

-- 118: the subset was empty at the last ANALYZE, then 50,000 rows arrived and
-- the maintenance VACUUM ANALYZE re-estimated the index's own count.
CREATE TABLE q118 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p118 ON q118 (id) WHERE state = 'pending';
SELECT pg_stat_force_next_flush(); ANALYZE q118; SELECT pg_stat_force_next_flush();
INSERT INTO q118 SELECT 1000000 + i, 'pending' FROM generate_series(1, 50000) i;
SELECT maint_begin('q118');
VACUUM (VERBOSE, ANALYZE) q118;
SELECT maint_end('q118');
SELECT plan_add(118, 'subset measured empty, then 50,000 rows arrive', 'p118',
                'SELECT count(*) FROM q118 WHERE state = ''pending''', 50000);

-- 119: fixture 118 after one more ANALYZE.  With the maintenance step in force
-- the two differ only by that second sample, which the concept page records as
-- an open question rather than as coverage.
CREATE TABLE q119 AS SELECT i::int AS id, 'done'::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p119 ON q119 (id) WHERE state = 'pending';
SELECT pg_stat_force_next_flush(); ANALYZE q119; SELECT pg_stat_force_next_flush();
INSERT INTO q119 SELECT 1000000 + i, 'pending' FROM generate_series(1, 50000) i;
SELECT maint_begin('q119');
VACUUM (VERBOSE, ANALYZE) q119;
SELECT maint_end('q119');
SELECT pg_stat_force_next_flush(); ANALYZE q119; SELECT pg_stat_force_next_flush();
SELECT plan_add(119, 'fixture 118 after one more ANALYZE', 'p119',
                'SELECT count(*) FROM q119 WHERE state = ''pending''', 50000);

-- 120: the ANALYZE sample missed the subset entirely.
CREATE TABLE q120 AS SELECT i::int AS id,
       CASE WHEN i <= 2000 THEN 'pending' ELSE 'done' END::text AS state
  FROM generate_series(1, 1000000) i;
CREATE INDEX p120 ON q120 (id) WHERE state = 'pending';
SET default_statistics_target = 1;
SELECT pg_stat_force_next_flush(); ANALYZE q120; SELECT pg_stat_force_next_flush();
RESET default_statistics_target;
SELECT plan_add(120, 'a 300-row sample missed a 2,000-row subset', 'p120',
                'SELECT count(*) FROM q120 WHERE state = ''pending''', 2000);

-- 121 built nz_k, nzb_k and i_trunc, three non-partial indexes reloaded with
-- the ANALYZE withheld.  All three are retired with the number: the
-- maintenance assumption forbids an unanalyzed reload, and nothing is built in
-- their place, so no fixture here reaches a stale catalog count except through
-- the forgery the churn stage writes for 84.

-- ================================================ families and predictions ==
-- The shared suite's families, and the per-fixture prediction of what this
-- statement's published reading rule will decide once the churn has run.  Both
-- are filed here, in the script text, before the run, and want_stage is never
-- rewritten after one.  'rebuild' predicts a row that is reported, alertable
-- and over the harness threshold; 'leave' predicts any other outcome,
-- including a row the exclusion terms withhold.  Size is not a term any more:
-- the statement's 1 MB filter came out on 2026-09-14, and these predictions
-- are left exactly as the run before that filed them, so the change in
-- want_miss is a measurement rather than a re-prediction.
UPDATE /* wiki_btree_suite_families */ plan SET grp =
       CASE WHEN num BETWEEN 18 AND 77  THEN 'partial'
            WHEN num BETWEEN 78 AND 85  THEN 'falsepos'
            WHEN num BETWEEN 86 AND 91  THEN 'falseneg'
            WHEN num BETWEEN 92 AND 112 THEN 'control'
            ELSE 'zero' END;

UPDATE /* wiki_btree_suite_predictions */ plan SET want_stage =
       CASE
         -- Family 3, and every other fixture whose point is that a fresh index
         -- must not be touched.  Rule 2 exempts all of them from the drain.
         WHEN num BETWEEN 78 AND 85                     THEN 'leave'
         WHEN num IN (70, 71, 96, 97, 101, 102, 103, 104, 105,
                      108, 109, 110, 111, 112, 116, 120) THEN 'leave'
         -- Family 4: reclaimable by construction, vacuumed and analyzed.
         WHEN num BETWEEN 86 AND 91                     THEN 'rebuild'
         -- Arrivals, not departures: each of these grew its index and left
         -- nothing to reclaim, and each is maintained after its churn.
         WHEN num IN (64, 66, 98, 115, 118, 119)        THEN 'leave'
         -- A quarter of the subset deleted is under the harness threshold.
         WHEN num = 72                                  THEN 'leave'
         ELSE 'rebuild' END;

CALL /* wiki_btree_suite_assert_built */ assert_built();
SELECT count(*) AS planned_fixtures FROM plan;
SELECT count(*) AS baselines_taken FROM snap WHERE phase = 'built';
SELECT count(*) AS build_contract_failures FROM plan
 WHERE want_rows IS NOT NULL AND built_rows <> want_rows;
FIXTURES
  # stderr is kept in a file of its own, because that is where the VACUUM
  # (VERBOSE, ANALYZE) messages land and the churn stage parses them for
  # proof 2 of the no-defeat rule.
  f suite "$SQLD/fixtures_suite.sql" > "$OUT/suite_build.log" \
      2> "$OUT/suite_verbose.log" || { tail -5 "$OUT/suite_verbose.log" >&2
                                       die "suite fixtures failed"; }
  tail -4 "$OUT/suite_build.log" >&2
  note "$(s suite 'SELECT count(*) || '\'' planned fixtures, '\'' ||
                   (SELECT count(*) FROM snap WHERE phase = '\''built'\'') ||
                   '\'' baselines, '\'' ||
                   (SELECT count(*) FROM plan
                     WHERE want_rows IS NOT NULL AND built_rows <> want_rows) ||
                   '\'' build-contract failures'\'' FROM plan')"
}

# --------------------------------------------- the no-defeat proof check ----
# The shared suite's rule "The maintenance must not be defeated" says a fixture
# that carried a defeating state into its maintenance statement is repaired and
# re-run rather than scored.  This function is that rule, enforced: it fails the
# run instead of publishing a number taken under a defeated maintenance.
#
# Four proofs, per maintenance statement, in one database:
#   1. the statement completed - a recorded end stamp - and the skip-line
#      check below finds no line naming its table;
#   2. its VERBOSE "dead but not yet removable" count exists and is zero;
#   3. every horizon probe found no other backend with an xmin or an open
#      transaction, no replication slot and no prepared transaction;
#   4. the page classes are recorded, which the pageclass read does.
maint_proofs() {
  local db=$1 n bad
  n=$(s "$db" 'SELECT count(*) FROM maint')
  [ "${n:-0}" -gt 0 ] || die "$db: no maintenance statement was recorded at all"
  bad=$(s "$db" 'SELECT count(*) FROM maint WHERE ended IS NULL')
  [ "$bad" = 0 ] || { t "$db" 'SELECT tbl, source, started FROM maint
                                WHERE ended IS NULL ORDER BY tbl' >&2
                      die "$db: $bad maintenance statements did not complete"; }
  bad=$(s "$db" 'SELECT count(*) FROM maint WHERE dead_not_removable IS NULL')
  [ "$bad" = 0 ] || { t "$db" 'SELECT tbl, source FROM maint
                                WHERE dead_not_removable IS NULL ORDER BY tbl' >&2
                      die "$db: $bad maintained tables have no VERBOSE count: proof 2 is missing"; }
  bad=$(s "$db" 'SELECT count(*) FROM maint WHERE dead_not_removable > 0')
  [ "$bad" = 0 ] || { t "$db" 'SELECT tbl, source, removed, remain, dead_not_removable,
                                      dead_after
                                 FROM maint WHERE dead_not_removable > 0
                                ORDER BY dead_not_removable DESC' >&2
                      die "$db: $bad maintained tables kept dead tuples the horizon still covered: the maintenance was defeated, repair the fixture and re-run"; }
  bad=$(s "$db" 'SELECT count(*) FROM horizon
                  WHERE xmin_holders > 0 OR open_xacts > 0
                     OR slots > 0 OR prepared > 0')
  [ "$bad" = 0 ] || { t "$db" 'SELECT step, tbl, xmin_holders, open_xacts, slots,
                                      prepared, detail
                                 FROM horizon
                                WHERE xmin_holders > 0 OR open_xacts > 0
                                   OR slots > 0 OR prepared > 0
                                ORDER BY at' >&2
                      die "$db: $bad horizon probes found a holder: the maintenance ran with a pinned horizon"; }
  { printf '%s\n' "$db"
    printf '  maintenance statements  %s, %s completed\n' "$n" \
      "$(s "$db" 'SELECT count(*) FROM maint WHERE ended IS NOT NULL')"
    printf '  by source               %s\n' \
      "$(s "$db" "SELECT string_agg(source || '=' || n, ' ' ORDER BY source)
                    FROM (SELECT source, count(*) AS n FROM maint GROUP BY source) x")"
    printf '  dead but not removable  max %s over %s tables\n' \
      "$(s "$db" 'SELECT coalesce(max(dead_not_removable), -1) FROM maint')" "$n"
    printf '  dead tuples left behind max %s\n' \
      "$(s "$db" 'SELECT coalesce(max(dead_after), -1) FROM maint')"
    printf '  tuples removed          %s\n' \
      "$(s "$db" 'SELECT coalesce(sum(removed), 0) FROM maint')"
    printf '  horizon probes clean    %s of %s\n' \
      "$(s "$db" 'SELECT count(*) FROM horizon
                   WHERE xmin_holders = 0 AND open_xacts = 0
                     AND slots = 0 AND prepared = 0')" \
      "$(s "$db" 'SELECT count(*) FROM horizon')"
    printf '  timeout sets in force   %s: %s\n' \
      "$(s "$db" 'SELECT count(DISTINCT timeouts) FROM maint')" \
      "$(s "$db" 'SELECT DISTINCT timeouts FROM maint')"
  } >> "$OUT/maint_proofs.txt"
}

# The skip lines the rule's proof 1 asks about.  A foreground VACUUM or ANALYZE
# that could not take its ShareUpdateExclusiveLock says so in the log, and an
# autovacuum worker cancelled by a waiting backend does too; either way the
# statement returned success without doing the work.  Only the lines after the
# mark the cluster stage wrote are read.
maint_skips() {
  local log=$1 markf=$2 mark=0 n=0 line
  : > "$OUT/maint_skips.txt"
  [ -f "$log" ] || return 0
  [ -f "$markf" ] && mark=$(tr -d ' \n' < "$markf")
  while IFS= read -r line; do
    n=$((n + 1)); [ "$n" -le "$mark" ] && continue
    case $line in
      *'skipping vacuum of '*|*'skipping analyze of '*|\
      *'canceling autovacuum task'*|*'canceling statement due to'*)
        printf '%s\n' "$line" >> "$OUT/maint_skips.txt" ;;
    esac
  done < "$log"
  return 0
}

# ---------------------------------------------------------------- churn ------
# Phase 3 of the shared mandatory suite, in the order that suite prescribes.
# Rule 2 drains every shape fixture that has no churn of its own - nine heap
# blocks in ten, then the maintenance VACUUM (VERBOSE, ANALYZE) - while the
# fixtures whose point is that a fresh index must not be touched are exempt and
# are listed nowhere below.  The fixtures that carry their own churn ran the
# same bracketed maintenance in the build file, so by the time this stage ends
# no churned table is unvacuumed or unanalyzed.  Rule 3 then analyzes whatever
# a server with autovacuum on would still have analyzed, using the engine's own
# threshold rather than a per-fixture annotation; with the maintenance
# assumption in force those are the tables no churn touched.  The catalog
# forgeries run last, because an ANALYZE of the table rewrites reltuples for
# the table and for every index on it.  The stage then records the four
# no-defeat proofs and the page classes the maintenance left, and ends by
# recording the churned state of every planned index, which is the state the
# statement is then asked about.
stage_churn() {
  say "churn: rule 2 drain, rule 3 census, forgeries last, churned snapshot"
  [ -n "$(s suite 'SELECT 1 FROM plan LIMIT 1')" ] \
    || die "no plan rows in suite; run the suite stage first"

  # -- rule 2, the uniform drain -------------------------------------------
  # The block number comes out of the tuple's own ctid, so the survivors are
  # spread across the heap and the index loses entries from every leaf page
  # instead of one contiguous run.  The statements are generated and executed
  # one at a time because VACUUM cannot run inside a transaction block.
  cat > "$SQLD/drain_suite.sql" <<'DRAIN'
-- Disposable fixtures, suite database of the sandbox cluster only.
-- All four settable timeouts are 0 here for the same reason they are 0 in the
-- fixture file: this session issues maintenance statements, and an autovacuum
-- worker forces exactly these four to 0 so that they cannot stop regular
-- maintenance.  maint.timeouts records what was actually in force.
SET /* wiki_btree_drain_client_min_messages */ client_min_messages = warning;
SET /* wiki_btree_drain_statement_timeout */ statement_timeout = 0;
SET /* wiki_btree_drain_lock_timeout */ lock_timeout = 0;
SET /* wiki_btree_drain_transaction_timeout */ transaction_timeout = 0;
SET /* wiki_btree_drain_idle_timeout */ idle_in_transaction_session_timeout = 0;
SELECT /* wiki_btree_drain_generator */ format(st.tmpl, tb.name)
  FROM (VALUES (1, 'pt1'), (2, 'pd22'), (3, 'pd23'), (4, 'pd24'), (5, 'pd25'),
               (6, 'pd26'), (7, 'pd27'), (8, 'pd28'), (9, 'pd29'), (10, 'pd30'),
               (11, 'pd31'), (12, 'pw32'), (13, 'pd33'), (14, 'pd34'),
               (15, 'pd35'), (16, 'pd36'), (17, 'pd37'),
               (19, 'pd39'), (20, 'pd40'), (21, 'pd41'), (22, 'pd42'),
               (23, 'pd43'), (24, 'pd44a'), (25, 'pd44b'), (26, 'pd45'),
               (27, 'pd46'), (28, 'pi47'), (29, 'pe48'), (30, 'pe48b'),
               (31, 'pe49'), (32, 'pe49b'), (33, 'pe50'), (34, 'pe50b'),
               (35, 'pc51'), (36, 'pf'), (37, 'ps')) tb(n, name)
 CROSS JOIN (VALUES
        (1, 'DELETE /* wiki_btree_drain */ FROM %1$I WHERE ((ctid::text::point)[0])::int %% 10 <> 0'),
        (2, 'SELECT /* wiki_btree_drain_begin */ maint_begin(%1$L, ''drain'')'),
        (3, 'VACUUM /* wiki_btree_drain */ (VERBOSE, ANALYZE) %1$I'),
        (4, 'SELECT /* wiki_btree_drain_end */ maint_end(%1$L)')) st(k, tmpl)
 ORDER BY tb.n, st.k
\gexec
DRAIN
  cat > "$SQLD/drain_gate.sql" <<'DRAING'
-- Disposable fixtures, gate database of the sandbox cluster only.  Both gate
-- tables are shape fixtures, so both are drained.
SET /* wiki_btree_draing_client_min_messages */ client_min_messages = warning;
SET /* wiki_btree_draing_statement_timeout */ statement_timeout = 0;
SET /* wiki_btree_draing_lock_timeout */ lock_timeout = 0;
SET /* wiki_btree_draing_transaction_timeout */ transaction_timeout = 0;
SET /* wiki_btree_draing_idle_timeout */ idle_in_transaction_session_timeout = 0;
SELECT /* wiki_btree_draing_generator */ format(st.tmpl, tb.name)
  FROM (VALUES (1, 't'), (2, 't2')) tb(n, name)
 CROSS JOIN (VALUES
        (1, 'DELETE /* wiki_btree_drain */ FROM %1$I WHERE ((ctid::text::point)[0])::int %% 10 <> 0'),
        (2, 'SELECT /* wiki_btree_draing_begin */ maint_begin(%1$L, ''drain'')'),
        (3, 'VACUUM /* wiki_btree_drain */ (VERBOSE, ANALYZE) %1$I'),
        (4, 'SELECT /* wiki_btree_draing_end */ maint_end(%1$L)')) st(k, tmpl)
 ORDER BY tb.n, st.k
\gexec
DRAING
  # stdout and stderr are split, because the VERBOSE messages are on stderr and
  # are parsed below for proof 2 of the no-defeat rule.
  f suite "$SQLD/drain_suite.sql" > "$OUT/drain.txt" 2> "$OUT/drain_verbose.log" \
    || { tail -5 "$OUT/drain_verbose.log" >&2; die "suite drain failed"; }
  f gate  "$SQLD/drain_gate.sql" >> "$OUT/drain.txt" 2> "$OUT/drain_gate_verbose.log" \
    || { tail -5 "$OUT/drain_gate_verbose.log" >&2; die "gate drain failed"; }
  note "drained 36 suite tables and both gate tables"

  # -- proof 2, recorded ----------------------------------------------------
  # Every VERBOSE message this run produced, turned into one UPDATE per
  # maintained table: the fixture file's statements and the drain's for the
  # suite database, the drain's alone for the gate database, whose two tables
  # have no churn of their own.
  parse_verbose "$OUT/suite_verbose.log"      > "$SQLD/maint_verbose.sql"
  parse_verbose "$OUT/drain_verbose.log"     >> "$SQLD/maint_verbose.sql"
  parse_verbose "$OUT/drain_gate_verbose.log" > "$SQLD/maint_verbose_gate.sql"
  [ -s "$SQLD/maint_verbose.sql" ] \
    || die "the VACUUM VERBOSE output produced no tuples line: proof 2 is missing"
  f suite "$SQLD/maint_verbose.sql"      > /dev/null || die "recording the suite VERBOSE counts failed"
  f gate  "$SQLD/maint_verbose_gate.sql" > /dev/null || die "recording the gate VERBOSE counts failed"

  # -- rule 3, the simulated auto-analyze -----------------------------------
  # The trigger is the engine's own test, mod_since_analyze >
  # autovacuum_analyze_threshold + autovacuum_analyze_scale_factor * reltuples,
  # read from this cluster's own settings.  autovacuum is off here, so every
  # ANALYZE below is one this rule asked for.
  cat > "$SQLD/census.sql" <<'CENSUS'
-- Disposable fixtures, sandbox cluster only.
-- The census runs ANALYZE, so it is a maintenance session too: the same four
-- timeouts are 0, and the no-defeat rule's window closes only when the census
-- has finished, which is why it is probed on both sides.
SET /* wiki_btree_census_client_min_messages */ client_min_messages = warning;
SET /* wiki_btree_census_statement_timeout */ statement_timeout = 0;
SET /* wiki_btree_census_lock_timeout */ lock_timeout = 0;
SET /* wiki_btree_census_transaction_timeout */ transaction_timeout = 0;
SET /* wiki_btree_census_idle_timeout */ idle_in_transaction_session_timeout = 0;
SELECT pg_stat_force_next_flush();
SELECT /* wiki_btree_census_horizon_before */ horizon_probe('census-before', NULL);
DROP TABLE IF EXISTS autoanl;
DROP TABLE IF EXISTS autoanl_after;
CREATE TABLE autoanl AS
SELECT /* wiki_btree_autoanalyze_census */
       c.relname                                      AS tbl,
       GREATEST(c.reltuples, 0)::numeric              AS reltuples,
       st.n_mod_since_analyze::numeric                AS mods,
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
   AND c.relname NOT IN ('plan', 'res', 'snap', 'gate_res',
                         'autoanl', 'autoanl_after',
                         'maint', 'horizon', 'pageclass');

SELECT /* wiki_btree_autoanalyze_generator */
       format('ANALYZE /* wiki_btree_autoanalyze */ %I', tbl)
  FROM autoanl WHERE would_autoanalyze ORDER BY tbl
\gexec

CREATE TABLE autoanl_after AS
SELECT /* wiki_btree_autoanalyze_recheck */
       c.relname AS tbl, st.n_mod_since_analyze::numeric AS mods,
       GREATEST(c.reltuples, 0)::numeric AS reltuples
  FROM pg_stat_all_tables st
  JOIN pg_class c ON c.oid = st.relid
 WHERE st.schemaname = 'public' AND c.relkind = 'r'
   AND c.relname IN (SELECT tbl FROM autoanl WHERE would_autoanalyze);

SELECT /* wiki_btree_census_horizon_after */ horizon_probe('census-after', NULL);
SELECT count(*) AS tables_censused,
       count(*) FILTER (WHERE would_autoanalyze) AS analyzed,
       min(mod_pct) FILTER (WHERE would_autoanalyze) AS lowest_analyzed_pct,
       max(mod_pct) FILTER (WHERE NOT would_autoanalyze) AS highest_left_alone_pct
  FROM autoanl;
CENSUS
  f suite "$SQLD/census.sql" > "$OUT/census.txt" 2>&1 || die "suite census failed"
  f gate  "$SQLD/census.sql" > "$OUT/census_gate.txt" 2>&1 || die "gate census failed"
  tail -4 "$OUT/census.txt" >&2
  tail -4 "$OUT/census_gate.txt" >&2

  # -- the forgeries, after the census --------------------------------------
  cat > "$SQLD/forge.sql" <<'FORGE'
-- Disposable catalog forgery, suite database of the sandbox cluster only.
-- Fixture 84's whole point is a partial index whose recorded entry count is
-- wrong, so the forgery has to outlive the census that would repair it.
SET /* wiki_btree_forge_client_min_messages */ client_min_messages = warning;
UPDATE /* wiki_btree_forge_84 */ pg_class SET reltuples = 5000
 WHERE relname = 'f84';
SELECT /* wiki_btree_forge_check */ relname, reltuples
  FROM pg_class WHERE relname = 'f84';
FORGE
  f suite "$SQLD/forge.sql" > "$OUT/forge.txt" 2>&1 || die "forgery failed"
  note "$(s suite "SELECT 'f84 reltuples now ' || reltuples
                     FROM pg_class WHERE relname = 'f84'")"

  # -- proof 4, and the two proofs the run has to check ---------------------
  # The page classes every index carries after the maintenance step.  Deleted
  # and half-dead pages are the visible trace of a horizon that moved, and a
  # drained fixture whose index has neither is the shape a defeated VACUUM
  # leaves behind.  pgstatindex reads every page and writes nothing, so the
  # decide phase that follows sees exactly the state the maintenance left.
  cat > "$SQLD/pageclass.sql" <<'PAGECLASS'
SET /* wiki_btree_pageclass_client_min_messages */ client_min_messages = warning;
DELETE FROM pageclass;
INSERT /* wiki_btree_pageclass */ INTO pageclass
       (idx, leaf_pages, empty_pages, deleted_pages, avg_leaf_density, index_size)
SELECT p.idx, m.leaf_pages, m.empty_pages, m.deleted_pages,
       CASE WHEN m.avg_leaf_density = 'NaN'::float8 THEN NULL
            ELSE round(m.avg_leaf_density::numeric, 2) END,
       m.index_size
  FROM plan p, LATERAL pgstatindex(p.idx::regclass) m;
SELECT /* wiki_btree_pageclass_report */
       count(*) || ' indexes read, '
       || count(*) FILTER (WHERE deleted_pages > 0) || ' with deleted pages, '
       || count(*) FILTER (WHERE empty_pages > 0) || ' with half-dead pages, '
       || coalesce(sum(deleted_pages), 0) || ' deleted pages in total'
  FROM pageclass;
PAGECLASS
  say "no-defeat proofs: completion, VERBOSE counts, horizon, page classes"
  : > "$OUT/maint_proofs.txt"
  local db
  for db in suite gate; do
    q "$db" 'CREATE EXTENSION IF NOT EXISTS pgstattuple' > /dev/null \
      || die "pgstattuple is not installed in $db; the page-class read needs it"
    f "$db" "$SQLD/pageclass.sql" > "$OUT/pageclass_$db.txt" 2>&1 \
      || die "page-class read failed on $db"
    tail -1 "$OUT/pageclass_$db.txt" >&2
    maint_proofs "$db"
  done
  maint_skips "$OUT/server.log" "$OUT/server.log.mark"
  # grep -c on an empty file prints 0 and exits 1, so the count is taken only
  # when there is something to count; an "|| printf 0" fallback here would
  # concatenate the two zeros and fail the check on a clean run.
  MAINT_SKIPS=0
  [ -s "$OUT/maint_skips.txt" ] && MAINT_SKIPS=$(grep -c '' "$OUT/maint_skips.txt")
  printf 'skip or cancellation lines %s\n' "$MAINT_SKIPS" >> "$OUT/maint_proofs.txt"
  cat "$OUT/maint_proofs.txt" >&2
  [ "$MAINT_SKIPS" = 0 ] \
    || { cat "$OUT/maint_skips.txt" >&2
         die "$MAINT_SKIPS skip or cancellation line(s) in the server log: a maintenance statement did not do its work"; }

  # -- the churned snapshot -------------------------------------------------
  cat > "$SQLD/snap_churned.sql" <<'SNAPC'
SET /* wiki_btree_snapc_client_min_messages */ client_min_messages = warning;
SET /* wiki_btree_snapc_statement_timeout */ statement_timeout = '900s';
SET /* wiki_btree_snapc_lock_timeout */ lock_timeout = '5s';
SELECT /* wiki_btree_snap_churned */ count(*) AS churned_snapshots
  FROM (SELECT snap_take('churned', idx) FROM plan ORDER BY num, leg) s;
SELECT /* wiki_btree_snap_phases */ phase, count(*) FROM snap GROUP BY phase ORDER BY phase;
SNAPC
  f suite "$SQLD/snap_churned.sql" > "$OUT/snapshots.txt" 2>&1 || die "suite snapshot failed"
  f gate  "$SQLD/snap_churned.sql" >> "$OUT/snapshots.txt" 2>&1 || die "gate snapshot failed"
  tail -12 "$OUT/snapshots.txt" >&2
}

# ------------------------------------------------------------ attribution ----
stage_attribution() {
  say "attribution: EXCEPT in both directions, before any REINDEX"
  f suite /dev/stdin > "$OUT/attribution.txt" 2>&1 <<'SQL'
\pset pager off
SELECT /* wiki_btree_attribution_r2_minus_old */ 'r2 minus old' AS direction, * FROM (
  SELECT indexname, status, wasted_space_pct, wasted_space_pct_floor, caveats,
         key_groups, modelled_rows, idx_reltuples, suppress_row
    FROM est_r2
  EXCEPT
  SELECT indexname, status, wasted_space_pct, wasted_space_pct_floor, caveats,
         key_groups, modelled_rows, idx_reltuples, suppress_row
    FROM est_old) d ORDER BY indexname;
SELECT /* wiki_btree_attribution_old_minus_r2 */ 'old minus r2' AS direction, * FROM (
  SELECT indexname, status, wasted_space_pct, wasted_space_pct_floor, caveats,
         key_groups, modelled_rows, idx_reltuples, suppress_row
    FROM est_old
  EXCEPT
  SELECT indexname, status, wasted_space_pct, wasted_space_pct_floor, caveats,
         key_groups, modelled_rows, idx_reltuples, suppress_row
    FROM est_r2) d ORDER BY indexname;
SQL
  tail -20 "$OUT/attribution.txt" >&2
}

# ---------------------------------------------------------------- probes -----
stage_probes() {
  say "validation probes, generated and executed, before any REINDEX"
  local db
  for db in suite; do
    "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d "$db" -f "$SQLD/probegen.sql" \
      > "$OUT/probes_gen_$db.txt" 2>&1
    : > "$OUT/probes_$db.txt"
    local name kind sql
    while IFS='|' read -r name kind sql; do
      [ -n "${sql:-}" ] || continue
      printf '%s|%s|%s\n' "$name" "$kind" "$(s "$db" "$sql" | tr '\n' ' ')" >> "$OUT/probes_$db.txt"
    done < "$OUT/probes_gen_$db.txt"
    note "$db: $(wc -l < "$OUT/probes_$db.txt") probes executed"
  done
  cat "$OUT/probes_suite.txt" >&2
}

# ---------------------------------------------------------------- score ------
stage_score() {
  say "score: read both texts on the churned fixture, REINDEX INDEX, re-read the size"
  local db out
  for db in suite gate; do
    [ "$db" = suite ] && out="$OUT/verdicts.txt" || out="$OUT/verdicts_gate.txt"
    f "$db" /dev/stdin <<'SQL'
SET /* wiki_btree_score_statement_timeout */ statement_timeout = '600s';
SET /* wiki_btree_score_lock_timeout */ lock_timeout = '2s';
CALL /* wiki_btree_score_all */ score_all();
SQL
    [ $? -eq 0 ] || die "scoring failed on $db"
    t "$db" "SELECT /* wiki_btree_verdict_rows */ * FROM verdicts" > "$out" 2>&1
    # The shared suite's bands, per family, and the two mandatory columns.
    t "$db" "SELECT /* wiki_btree_verdict_shared_counts */
                    grp, verdict, count(*) FROM verdicts
              GROUP BY 1, 2 ORDER BY 1, 2" >> "$out" 2>&1
    t "$db" "SELECT /* wiki_btree_verdict_shared_totals */
                    verdict, count(*) FROM verdicts GROUP BY 1 ORDER BY 2 DESC" >> "$out" 2>&1
    t "$db" "SELECT /* wiki_btree_verdict_stage_agreement */
                    count(*) AS fixtures,
                    count(*) FILTER (WHERE taken_stage = 'rebuild')            AS rebuilt,
                    count(*) FILTER (WHERE expected_stage = taken_stage)       AS gate_agrees,
                    count(*) FILTER (WHERE expected_stage <> taken_stage)      AS gate_disagrees,
                    count(*) FILTER (WHERE want_stage = taken_stage)           AS want_hit,
                    count(*) FILTER (WHERE want_stage <> taken_stage)          AS want_miss,
                    count(*) FILTER (WHERE NOT contract_ok)                    AS contract_failures
               FROM verdicts" >> "$out" 2>&1
    t "$db" "SELECT /* wiki_btree_verdict_lost */
                    num, leg, idx, lost_by, wspf, actual, caveats
               FROM verdicts WHERE lost_by IS NOT NULL ORDER BY num, leg" >> "$out" 2>&1
    t "$db" "SELECT /* wiki_btree_verdict_want_miss */
                    num, leg, idx, want_stage, taken_stage, verdict, wspf, actual
               FROM verdicts WHERE want_stage <> taken_stage ORDER BY num, leg" >> "$out" 2>&1
    # What the report filter removed on 2026-09-14 used to withhold: every
    # fixture under 1 MB, with the decision and the verdict it now gets.
    t "$db" "SELECT /* wiki_btree_verdict_under_1mb */
                    num, leg, idx, blocks_before * 8 AS kib_before,
                    wspf, actual, taken_stage, verdict
               FROM verdicts WHERE NOT over_1mb ORDER BY num, leg" >> "$out" 2>&1
    # The maintenance behind each fixture, and what it left in the index: the
    # four no-defeat proofs, per row, so a reader can check a verdict against
    # the state it was taken in rather than against a summary.
    t "$db" "SELECT /* wiki_btree_verdict_maintenance */
                    num, leg, idx, tbl, maintained, maint_source,
                    maint_removed, dead_not_removable, dead_after, mods_after,
                    deleted_pages, empty_pages, density_after_maint
               FROM verdicts ORDER BY num, leg" >> "$out" 2>&1
    # The page's older one-shot bands, on the same rows, for comparison.
    t "$db" "SELECT /* wiki_btree_verdict_floor_counts */
                    verdict_floor, count(*) FROM verdicts GROUP BY 1 ORDER BY 2 DESC" \
      >> "$out" 2>&1
    t "$db" "SELECT /* wiki_btree_verdict_point_counts */
                    verdict_point, count(*) FROM verdicts GROUP BY 1 ORDER BY 2 DESC" \
      >> "$out" 2>&1
    note "$db: $(s "$db" "SELECT count(*) || ' scored, ' ||
                          count(*) FILTER (WHERE verdict = 'PASS') || ' PASS, ' ||
                          count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE') || ' FN, ' ||
                          count(*) FILTER (WHERE verdict LIKE '%FALSE POSITIVE') || ' FP'
                            FROM verdicts")"
  done
  tail -24 "$OUT/verdicts.txt" >&2
}

# ---------------------------------------------------------------- cost -------
stage_cost() {
  say "cost: six interleaved pairs of the two exact texts"
  : > "$OUT/cost.txt"
  local i
  for i in 1 2 3 4 5 6; do
    printf 'pair %s r2  %s\n' "$i" \
      "$("$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite \
           -c '\timing on' -f "$SQLD/est_r2.sql" 2>&1 \
         | grep -E '^Time:' | tail -1)" >> "$OUT/cost.txt"
    printf 'pair %s old %s\n' "$i" \
      "$("$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d suite \
           -c '\timing on' -f "$SQLD/est_old.sql" 2>&1 \
         | grep -E '^Time:' | tail -1)" >> "$OUT/cost.txt"
  done
  s suite "select /* wiki_btree_cost_database_size */
                  count(*) || ' B-tree indexes over ' ||
           sum(pg_relation_size(c.oid)) / 8192 || ' blocks'
             from pg_class c join pg_am a on a.oid = c.relam
            where a.amname = 'btree' and c.relkind = 'i'" >> "$OUT/cost.txt"
  # How many rows each exact text prints on this settled database.  The
  # current text has neither the 1 MB filter nor the LIMIT 20 the superseded
  # one still carries, so the pair measures what the removal shows a reader.
  f suite "$SQLD/est_r2.sql"  > "$OUT/exact_r2_settled.txt"  2>&1
  f suite "$SQLD/est_old.sql" > "$OUT/exact_old_settled.txt" 2>&1
  { printf 'settled r2  %s\n' \
      "$(grep -E '^\([0-9]+ rows?\)$' "$OUT/exact_r2_settled.txt"  | tail -1)"
    printf 'settled old %s\n' \
      "$(grep -E '^\([0-9]+ rows?\)$' "$OUT/exact_old_settled.txt" | tail -1)"
  } >> "$OUT/cost.txt"
  # The same row set through the harness view, split on the size the removed
  # predicate tested, so the share of the report that only exists because the
  # filter is gone is a number this script produced.
  s suite "select /* wiki_btree_cost_report_shape */
                  count(*) || ' reported rows, ' ||
                  count(*) filter (where actual_bytes <= 1024 * 1024) ||
                  ' of them 1 MB or smaller'
             from est_r2 where not suppress_row" >> "$OUT/cost.txt"
  cat "$OUT/cost.txt" >&2
}

# ------------------------------------------------- expected server errors ---
# Every server-side error this suite provokes is deliberate, and each one is
# raised by a statement this script can name.  One remains: the gate's
# text_pattern_ops refusal of a nondeterministic collation.  The second pair,
# the superseded text's bigint overflow, went with the acceptance stage's ovf
# fixture that forged the count which raised it, so an overflow from any
# statement is now counted.  An allowed error is a pair, the message and a
# fragment of the statement that raised it, so that the same message from
# another statement is not allowed.  Every line of one error record carries
# the same "%m [%p]"
# prefix, because EmitErrorReport() captures the timestamp once per record,
# and the STATEMENT line is the record's last line, its continuation lines
# indented by a tab; that is what the pairing reads.  Only the lines after
# the mark that cluster writes when it starts the server are read, so a
# sandbox with a stray error recovers with "stop cluster"; the earlier lines
# stay in the log.  Anything else counted is a real failure.
EXPECTED_ERRORS=(
  'nondeterministic collations are not supported for operator class "text_pattern_ops"'
)
EXPECTED_STATEMENTS=(
  'CREATE INDEX i_pattern_nondet'
)
UNEXPECTED_ERRORS=0
settle_pending() {                 # only from check_server_errors, on its locals
  case $stmt in
    *"${EXPECTED_STATEMENTS[$pending]}"*) seen[$pending]=$((seen[$pending] + 1)) ;;
    *) UNEXPECTED_ERRORS=$((UNEXPECTED_ERRORS + 1))
       printf '   unexpected: %s\n      its statement does not contain "%s"\n' \
              "$pend_line" "${EXPECTED_STATEMENTS[$pending]}" ;;
  esac
  pending=-1; collecting=0; stmt=''
}
check_server_errors() {            # check_server_errors <server log> <mark file>
  local log=$1 markf=$2 mark=0 n=0 line i tab
  local pending=-1 pend_line='' pend_prefix='' stmt='' collecting=0
  local -a seen
  UNEXPECTED_ERRORS=0
  [ -f "$log" ] || { printf '   no %s to read\n' "$log"; return 0; }
  [ -f "$markf" ] && mark=$(tr -d ' \n' < "$markf")
  tab=$(printf '\t')
  for i in "${!EXPECTED_ERRORS[@]}"; do seen[i]=0; done
  while IFS= read -r line; do
    n=$((n + 1)); [ "$n" -le "$mark" ] && continue
    if [ "$collecting" = 1 ]; then
      case $line in
        "$tab"*) stmt="$stmt"$'\n'"$line"; continue ;;   # the statement goes on
      esac
      settle_pending                                     # it ended on the line before
    fi
    case $line in
      *' ERROR:  '*|*' FATAL:  '*|*' PANIC:  '*)
        if [ "$pending" -ge 0 ]; then                    # never got its STATEMENT line
          UNEXPECTED_ERRORS=$((UNEXPECTED_ERRORS + 1))
          printf '   unexpected: %s\n      no STATEMENT line follows it\n' "$pend_line"
          pending=-1
        fi
        for i in "${!EXPECTED_ERRORS[@]}"; do
          case $line in *"${EXPECTED_ERRORS[i]}"*) pending=$i; break ;; esac
        done
        if [ "$pending" -ge 0 ]; then
          pend_line=$line
          pend_prefix=${line%% ERROR:  *}; pend_prefix=${pend_prefix%% FATAL:  *}
          pend_prefix=${pend_prefix%% PANIC:  *}
        else
          UNEXPECTED_ERRORS=$((UNEXPECTED_ERRORS + 1)); printf '   unexpected: %s\n' "$line"
        fi ;;
      "$pend_prefix STATEMENT:  "*)
        [ "$pending" -ge 0 ] && { stmt=${line#"$pend_prefix STATEMENT:  "}; collecting=1; } ;;
    esac
  done < "$log"
  if [ "$collecting" = 1 ]; then settle_pending
  elif [ "$pending" -ge 0 ]; then
    UNEXPECTED_ERRORS=$((UNEXPECTED_ERRORS + 1))
    printf '   unexpected: %s\n      no STATEMENT line follows it\n' "$pend_line"
  fi
  for i in "${!EXPECTED_ERRORS[@]}"; do
    printf '   allowed %s: "%s" from a statement containing "%s": seen %s\n' \
           "$((i + 1))" "${EXPECTED_ERRORS[i]}" "${EXPECTED_STATEMENTS[i]}" "${seen[i]}"
  done
  printf '   lines read: %s after mark %s\n' "$((n - mark))" "$mark"
  printf '   allowed=%s unexpected_server_errors=%s\n' \
         "${#EXPECTED_ERRORS[@]}" "$UNEXPECTED_ERRORS"
}

# ---------------------------------------------------------------- criteria ---
stage_criteria() {
  say "pass criteria"
  { printf '1. gate group\n'
    t gate "SELECT /* wiki_btree_criteria_gate */
                   count(*) FILTER (WHERE dedup_applies AND NOT metapage) AS over_credit,
                   count(*) FILTER (WHERE equalimage = 'recognized' AND NOT metapage)
                          + count(*) FILTER (WHERE equalimage = 'ineligible' AND metapage)
                                                                          AS metapage_disagreements,
                   count(*) FILTER (WHERE equalimage = 'unknown' AND metapage) AS under_credits,
                   max(greatest(wsp, wspf))                                    AS worst_reading
              FROM gate_res"
    printf '2. the shared mandatory suite, four bands, both databases\n'
    local db
    for db in gate suite; do
      printf '   %s\n' "$db"
      t "$db" "SELECT /* wiki_btree_criteria_shared */
                      count(*)                                              AS fixtures,
                      count(*) FILTER (WHERE verdict = 'PASS')              AS pass,
                      count(*) FILTER (WHERE verdict = 'CRITICAL FALSE POSITIVE') AS crit_fp,
                      count(*) FILTER (WHERE verdict = 'FALSE POSITIVE')    AS fp,
                      count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE')    AS fn,
                      count(*) FILTER (WHERE expected_stage <> taken_stage) AS gate_disagrees,
                      count(*) FILTER (WHERE want_stage <> taken_stage)     AS want_miss,
                      count(*) FILTER (WHERE NOT contract_ok)               AS contract_failures,
                      count(*) FILTER (WHERE NOT over_1mb)                  AS under_1mb,
                      count(*) FILTER (WHERE NOT over_1mb
                                         AND taken_stage = 'rebuild')       AS under_1mb_rebuild
                 FROM verdicts"
      # Accuracy beside the decision, and one row per loss class with the
      # reclaim a rebuild actually gave back.  Both are read-only, so this
      # stage can be re-run after the oracle pass without disturbing it.
      t "$db" "SELECT /* wiki_btree_criteria_accuracy */
                      count(*) FILTER (WHERE wspf IS NOT NULL
                                         AND abs(wspf - actual) <= 1)       AS within_one_point,
                      round(max(wspf - actual), 1)                          AS worst_over,
                      round(min(wspf - actual), 1)                          AS worst_under
                 FROM verdicts"
      t "$db" "SELECT /* wiki_btree_criteria_lost_classes */
                      lost_by, count(*), round(avg(actual), 1) AS mean_reclaim,
                      min(actual) AS min_reclaim, max(actual) AS max_reclaim
                 FROM verdicts WHERE lost_by IS NOT NULL
                GROUP BY 1 ORDER BY 2 DESC"
      t "$db" "SELECT /* wiki_btree_criteria_decisions */
                      taken_stage, count(*), round(avg(actual), 1) AS mean_reclaim,
                      min(actual) AS min_reclaim, max(actual) AS max_reclaim
                 FROM verdicts GROUP BY 1 ORDER BY 1"
      t "$db" "SELECT /* wiki_btree_criteria_withheld_terms */
                      withheld_by, count(*) FROM verdicts
                WHERE NOT reported GROUP BY 1 ORDER BY 2 DESC"
      t "$db" "SELECT /* wiki_btree_criteria_worst_reads */
                      num, leg, idx, wspf, actual,
                      round(wspf - actual, 1) AS delta
                 FROM verdicts WHERE wspf IS NOT NULL
                ORDER BY (wspf - actual) LIMIT 3"
      t "$db" "SELECT /* wiki_btree_criteria_phases */
                      (SELECT count(*) FROM snap WHERE phase = 'built')     AS baselines,
                      (SELECT count(*) FROM snap WHERE phase = 'churned')   AS churned,
                      (SELECT count(*) FROM autoanl)                        AS censused,
                      (SELECT count(*) FROM autoanl WHERE would_autoanalyze) AS analyzed,
                      (SELECT max(mod_pct) FROM autoanl WHERE NOT would_autoanalyze) AS highest_left,
                      (SELECT min(mod_pct) FROM autoanl WHERE would_autoanalyze)     AS lowest_analyzed"
    done
    printf '2b. the older bands this page filed, on the same rows\n'
    t suite "SELECT /* wiki_btree_criteria_partial */
                    count(*) FILTER (WHERE reported AND verdict_floor = 'CRITICAL FALSE POSITIVE') AS crit_fp_floor,
                    count(*) FILTER (WHERE reported AND verdict_point = 'CRITICAL FALSE POSITIVE') AS crit_fp_point,
                    count(*) FILTER (WHERE verdict_floor = 'FALSE NEGATIVE')   AS false_negatives,
                    count(*) FILTER (WHERE NOT reported)                       AS withheld,
                    count(*) FILTER (WHERE NOT reported AND withheld_by IS NULL) AS withheld_unexplained,
                    count(*) FILTER (WHERE NOT contract_ok)                    AS contract_failures
               FROM verdicts"
    printf '3. drained subsets and zero rows\n'
    t suite "SELECT /* wiki_btree_criteria_zero_rows */
                    num, leg, idx, wsp, wspf, actual, modelled_rows, caveats
               FROM verdicts WHERE modelled_rows = 0 OR num IN (113, 118, 120) ORDER BY num, leg"
    printf '4. attribution\n'
    grep -c '^ ' "$OUT/attribution.txt" 2>/dev/null | xargs printf '   EXCEPT output lines: %s\n'
    printf '5. exact texts\n'
    ls -l "$OUT"/exact_*.txt | while read -r l; do printf '   %s\n' "$l"; done
    printf '6. engine and repository checks\n'
    cat "$OUT/checks.txt" 2>/dev/null
    cat "$OUT/hashes.txt" 2>/dev/null
  } > "$OUT/criteria.txt" 2>&1
  { printf '7. server errors\n'
    check_server_errors "$OUT/server.log" "$OUT/server.log.mark"; } >> "$OUT/criteria.txt" 2>&1
  { printf '8. the maintenance must not be defeated\n'
    cat "$OUT/maint_proofs.txt" 2>/dev/null
    local db2
    for db2 in suite gate; do
      t "$db2" "SELECT /* wiki_btree_criteria_maint */
                       count(*)                                          AS fixtures,
                       count(*) FILTER (WHERE maintained)                AS maintained,
                       count(*) FILTER (WHERE maintained
                                          AND dead_not_removable = 0)    AS dead_not_removable_zero,
                       count(*) FILTER (WHERE maintained
                                          AND dead_not_removable > 0)    AS defeated,
                       count(*) FILTER (WHERE deleted_pages > 0)         AS with_deleted_pages,
                       count(*) FILTER (WHERE empty_pages > 0)           AS with_half_dead_pages,
                       coalesce(sum(deleted_pages), 0)                   AS deleted_pages_total
                  FROM verdicts"
      t "$db2" "SELECT /* wiki_btree_criteria_maint_sources */
                       maint_source, count(*) AS fixtures,
                       max(dead_not_removable) AS worst_dead_not_removable
                  FROM verdicts WHERE maintained
                 GROUP BY 1 ORDER BY 1"
    done
  } >> "$OUT/criteria.txt" 2>&1
  cat "$OUT/criteria.txt" >&2
  [ "$UNEXPECTED_ERRORS" -eq 0 ] \
    || die "$UNEXPECTED_ERRORS unexpected server error(s); see block 7 of $OUT/criteria.txt"
}

# ---------------------------------------------------------------- report -----
stage_report() {
  say "report written to $OUT"
  ls -1 "$OUT" >&2
}

# ---------------------------------------------------------------- stop -------
# Shut the server down cleanly.  -m fast disconnects clients and lets the
# checkpointer write a shutdown checkpoint, so the next start needs no
# recovery; -m immediate, which this stage used until 2026-09-10, skips that
# and forces crash recovery on restart.  The stop is then confirmed the way
# the teardown rule asks, and the stage dies rather than report a stop that
# did not happen, so clean never deletes a live cluster.
stage_stop() {
  say "stop the server cleanly"
  [ -x "$BIN/pg_ctl" ] || { note "no server binary under $BIN, nothing to stop"; return 0; }
  if [ -s "$DATA/postmaster.pid" ] && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1 || die "pg_ctl -m fast stop failed"
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
  note "confirmed: no postmaster.pid, no postgres process on $DATA, socket directory empty"
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
  inside_tmp "$SANDBOX" || die "refusing to delete $SANDBOX outside $WIKI_ROOT/.wiki-runtime/tmp/"
  rm -rf "$SANDBOX"; say "sandbox deleted"
}

main() {
  local stages=("$@")
  [ ${#stages[@]} -eq 0 ] && stages=(build check cluster texts gate suite churn \
                                     extstat attribution probes score cost \
                                     criteria report)
  local st
  for st in "${stages[@]}"; do
    case $st in
      build|check|cluster|texts|extstat|gate|suite|churn|attribution|probes|\
      score|cost|criteria|report|stop|clean) "stage_$st" ;;
      *) die "unknown stage: $st" ;;
    esac
  done
}

main "$@"
```

### The PostgreSQL 12 leg script

This is step 8, and its first result is the parse outcome of the unmodified
text, recorded before any fixture exists. Nothing in the script assumes what
PostgreSQL 12 does: the server-version number, the block size and alignment,
whether `pg_stat_force_next_flush()` exists, which columns `pg_stats_ext`
exposes, which B-tree support-function numbers are registered and whether the
`deduplicate_items` reloption is accepted are all discovered at run time and
written to `out/v12_facts.txt`. Because the flush function is not available
there, the leg publishes counters the way the shipped 12 statistics test does:
the writing backend exits and the observer polls in fresh sessions until the
counter it is waiting for appears, with a timeout treated as a failed
precondition rather than as a result.

```bash
#!/usr/bin/env bash
#
# btree_bloat_suite_v12.sh - the 12.2 leg of the same suite, in bash and SQL
# only.  It is step 8 of the page's protocol: build the pinned 12 checkout,
# execute the exact current statement text, record the outcome as a result in
# its own right, and only then transform, fixture and score.
#
# Nothing here assumes what PostgreSQL 12 does.  Every version-local fact the
# leg depends on is discovered at run time and written to $OUT/v12_facts.txt:
# whether the exact text parses, which construct rejects it, whether
# pg_stat_force_next_flush() exists, and whether a B-tree operator class
# offers a support function 4.  The pinned checkouts stay read only.
#
# Every fixture it builds belongs to the shared mandatory suite, as far as a
# 12.2 server can build one.  Removed on 2026-09-14: the three fresh sorted
# builds, which were page-local geometry fixtures, and 1010 to 1012, this
# leg's legs of the retired number 121.
#
# Since 2026-09-16 this leg keeps the same rule the 17 leg does, "The
# maintenance must not be defeated": every maintenance statement is one
# VACUUM (VERBOSE, ANALYZE) between maint_begin() and maint_end(), issued by
# maintain() from a session whose statement_timeout, lock_timeout and
# idle_in_transaction_session_timeout are 0, and the run records per table that
# the statement completed, its own dead-but-not-removable count, the horizon
# holders and the page classes it left.  Three differences from the 17 leg are
# this server's, not the rule's: there is no transaction_timeout to zero, there
# is no pg_stat_force_next_flush() so publication is a poll, and the VERBOSE
# wording differs, so the parse below is this leg's own.
#
# Usage, from the repository root:
#   bash btree_bloat_suite_v12.sh                  # all stages
#   bash btree_bloat_suite_v12.sh exact            # just the parse result
#
# Stages: build check cluster exact transform facts fixtures churn score extstat
#         report stop clean
#
# Environment: WIKI_ROOT PAGE SRC12 SANDBOX PORT12 JOBS EXTRA_CFLAGS
set -uo pipefail

WIKI_ROOT="${WIKI_ROOT:-$PWD}"
PAGE="${PAGE:-$WIKI_ROOT/wiki/v17/questions/indexing/btree-index-bloat-core-sql-only.md}"
SRC12="${SRC12:-$WIKI_ROOT/raw/postgres-12}"
SANDBOX="${SANDBOX:-$WIKI_ROOT/.wiki-runtime/tmp/btree-suite}"
PORT12="${PORT12:-55412}"
JOBS="${JOBS:-4}"
# ICU dropped the TRUE/FALSE macros in ICU 68; a 12.2 tree configured
# --with-icu against a newer ICU needs them back.  Empty this variable on a
# host whose ICU still defines them, or drop --with-icu instead.
EXTRA_CFLAGS="${EXTRA_CFLAGS:--O2 -g -DTRUE=1 -DFALSE=0}"

BUILD="$SANDBOX/build12"; INST="$SANDBOX/install12"; DATA="$SANDBOX/data12"
OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql"; SOCK="$SANDBOX/sock12"; BIN="$INST/bin"
# Where every maintenance statement's VACUUM (VERBOSE, ANALYZE) output lands,
# so that proof 2 of the no-defeat rule is parsed from one file per run.
VERBOSELOG="$OUT/maint_verbose12.log"
DB=leg12
export PGPORT="$PORT12" PGHOST="$SOCK" PGDATABASE=postgres

BASE1=4de245c5a1fb442cda800c099b8801bc72abc0c87f170384490079135fb5241d
# The estimator text as filed before the portable extstat filter of 2026-09-10,
# rebuilt from the current text, so it moves whenever that text does: it was
# 8acd531b7bcd2f2c until the report filter came out on 2026-09-14.  The extstat
# stage rebuilds it, must reproduce this hash, and must find this server
# refusing it.
BASEPRE=152f4172f1ee1dfd86467e525bfe37babba92a5ad036358bed0d17aa4b10594a

say()  { printf '\n== %s\n' "$*" >&2; }
note() { printf '   %s\n' "$*" >&2; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# -X ignores ~/.psqlrc; ON_ERROR_STOP is on every helper, because without it a
# failed statement inside a -f script leaves the exit status 0.
q() { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }          # writer
s() { "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }      # scalar
t() { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -P pager=off -d "$DB" -c "$1"; }  # table
fl() { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" -f "$1"; }         # file

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

# The same three edits as the 17 leg, and the same two tails: the current text
# ends on " WHERE NOT suppress_row" and an ORDER BY line carrying the
# semicolon, the text filed before 2026-09-14 on the 1 MB filter, an
# unterminated ORDER BY and " LIMIT 20;".
harness_view() {
  local file=$1 view=$2 extra=$3 line
  printf 'DROP VIEW IF EXISTS %s;\nCREATE VIEW %s AS\n' "$view" "$view"
  while IFS= read -r line; do
    case $line in
      "SET /* wiki_btree_wasted_space"*)     continue ;;
      "       server_version_num")           printf '       server_version_num,\n%s\n' "$extra"; continue ;;
      " WHERE NOT suppress_row")             continue ;;
      " WHERE actual_bytes > 1024 * 1024"*)  continue ;;
      " ORDER BY (actual_bytes"*';')         printf ';\n'; continue ;;
      " ORDER BY (actual_bytes"*)            continue ;;
      " LIMIT 20;")                          printf ';\n'; continue ;;
    esac
    printf '%s\n' "$line"
  done < "$file"
}

INTERNALS='       expected_blocks, floor_blocks, actual_bytes, live_rows, slot,
       leaf_cap, nmax, leaf_pages, tids, dedup_applies, is_partial,
       has_expressions, stats_row_missing, dedup_credited, stats_stale,
       suppress_row, ext_used, equalimage_state'

# There is no pg_stat_force_next_flush() before PostgreSQL 15, so this leg
# publishes counters the way the shipped 12 statistics test does: the writing
# backend exits, and the observer polls in fresh sessions until the counter it
# is waiting for appears.  A timeout is a failed precondition, not a result.
wait_for() {                       # wait_for <sql returning boolean> <label>
  local i
  for i in $(seq 1 120); do
    [ "$(s "SELECT ($1)::text")" = "true" ] && return 0
    sleep 0.5
  done
  printf '!! statistics did not publish within 60s: %s\n' "$2" >&2
  return 1
}
loaded()   { wait_for "(SELECT n_live_tup FROM pg_stat_all_tables WHERE relname = '$1') >= $2" "$1 loaded"; }
analyzed() { wait_for "(SELECT last_analyze IS NOT NULL FROM pg_stat_all_tables WHERE relname = '$1')" "$1 analyzed"; }
vacuumed() { wait_for "(SELECT last_vacuum IS NOT NULL FROM pg_stat_all_tables WHERE relname = '$1')" "$1 vacuumed"; }

# maintain <table> [source]: one bracketed maintenance statement, the form the
# shared suite's no-defeat rule asks for.  The three -c options run in one
# session - each its own transaction, which is what lets VACUUM run at all -
# so the timeouts maint_begin records are the ones the VACUUM itself ran
# under.  This server has no transaction_timeout, so three are zeroed rather
# than four, and PGOPTIONS is how they are set before the first statement.
# stderr goes to the VERBOSE log the proof parse reads.  The poll afterwards is
# this leg's publication barrier, standing in for the flush function it lacks:
# the session has exited, so its VACUUM and ANALYZE counts are on their way.
maintain() {
  local tbl=$1 src=${2:-fixture}
  PGOPTIONS='-c statement_timeout=0 -c lock_timeout=0 -c idle_in_transaction_session_timeout=0' \
    "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" \
      -c "SELECT /* wiki_btree_leg12_maint_begin */ maint_begin('$tbl', '$src')" \
      -c "VACUUM /* wiki_btree_leg12_maint */ (VERBOSE, ANALYZE) $tbl" \
      -c "SELECT /* wiki_btree_leg12_maint_end */ maint_end('$tbl')" \
      2>> "$VERBOSELOG" || die "the maintenance of $tbl failed"
  vacuumed "$tbl" || die "the maintenance of $tbl did not publish"
}

# parse_verbose <log>: proof 2, in this server's wording.  12.2 emits one
# message per relation,
#   INFO:  "tbl": found X removable, Y nonremovable row versions in ...
#   DETAIL:  Z dead row versions cannot be removed yet, oldest xmin: ...
# so the name and the two counts come from the INFO line and the dead count
# from the DETAIL line that follows it.  A toast relation's lines match no
# maint row and update nothing.  Bash only: no awk, no perl.
parse_verbose() {
  local log=$1 line cur="" rest removed remain dead
  [ -f "$log" ] || return 0
  while IFS= read -r line; do
    case $line in
      'INFO:  "'*'": found '*' removable, '*' nonremovable row versions'*)
        rest=${line#INFO:  \"};     cur=${rest%%\"*}
        rest=${line#*: found };     removed=${rest%% removable,*}
        rest=${rest#* removable, }; remain=${rest%% nonremovable*} ;;
      'DETAIL:  '*' dead row versions cannot be removed yet'*)
        [ -n "$cur" ] || continue
        rest=${line#DETAIL:  }; dead=${rest%% dead row versions*}
        printf "UPDATE /* wiki_btree_maint_verbose12 */ maint SET removed = %s, remain = %s, dead_not_removable = greatest(coalesce(dead_not_removable, 0), %s) WHERE tbl = '%s';\n" \
               "$removed" "$remain" "$dead" "$cur"
        cur="" ;;
    esac
  done < "$log"
}

# ---------------------------------------------------------------- build ------
# clean deletes $BUILD, so this leg's build diagnostics are copied into $OUT
# after every step, on the failure path too; the 17 leg owns the shared out/,
# hence the 12 suffix on every copied name.
keep_build_logs() {
  local l
  for l in configure make install; do
    [ -f "$BUILD/$l.log" ] && cp "$BUILD/$l.log" "$OUT/${l}12.log"
  done
  return 0
}
stage_build() {
  say "build 12.2 out of tree from $SRC12"
  [ -x "$BIN/postgres" ] && { note "already built, skipping"; return 0; }
  [ -x "$SRC12/configure" ] || die "no pinned checkout at $SRC12; set SRC12 or run from the repository root"
  mkdir -p "$BUILD" "$OUT" "$SQLD"
  ( cd "$BUILD" && "$SRC12/configure" --prefix="$INST" --enable-debug \
      --with-icu --with-readline --with-zlib CFLAGS="$EXTRA_CFLAGS" \
      > configure.log 2>&1 ) \
    || { keep_build_logs; die "configure failed, see $OUT/configure12.log"; }
  ( cd "$BUILD" && make -j"$JOBS" > make.log 2>&1 && make install > install.log 2>&1 ) \
    || { keep_build_logs; grep -m3 'error:' "$BUILD/make.log" >&2
         die "make failed, see $OUT/make12.log"; }
  local m
  for m in pageinspect pgstattuple amcheck; do
    ( cd "$BUILD" && make -C "contrib/$m" -j"$JOBS" >> install.log 2>&1 \
        && make -C "contrib/$m" install >> install.log 2>&1 ) \
      || { keep_build_logs; die "contrib/$m failed, see $OUT/install12.log"; }
  done
  keep_build_logs
  note "$("$BIN/postgres" --version)"
}

stage_check() {
  say "engine regression suites, 12.2"
  : > "$OUT/checks12.txt"
  ( cd "$BUILD" && make check > check_core.log 2>&1 )
  printf 'core=%s %s\n' "$?" \
    "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_core.log" | tail -1)" \
    >> "$OUT/checks12.txt"
  local m
  for m in pageinspect pgstattuple amcheck; do
    ( cd "$BUILD" && make -C "contrib/$m" check > "check_$m.log" 2>&1 )
    printf '%s=%s %s\n' "$m" "$?" \
      "$(grep -Eo 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests (passed|failed)' "$BUILD/check_$m.log" | tail -1)" \
      >> "$OUT/checks12.txt"
  done
  # Same reason as the build stage: a one-line summary cannot diagnose a
  # failure, and the logs and diffs go with $BUILD.
  local l d
  for l in core pageinspect pgstattuple amcheck; do
    cp "$BUILD/check_$l.log" "$OUT/check12_$l.log" 2>/dev/null
  done
  for d in "$BUILD/src/test/regress" "$BUILD"/contrib/*; do
    [ -f "$d/regression.diffs" ] \
      && cp "$d/regression.diffs" "$OUT/diffs12_$(basename "$d").txt"
  done
  cat "$OUT/checks12.txt" >&2
}

stage_cluster() {
  say "isolated 12.2 cluster on port $PORT12"
  if "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then note "already running"
  else
    if [ ! -d "$DATA" ]; then
      mkdir -p "$SOCK"
      "$BIN/initdb" -D "$DATA" --locale=C --encoding=UTF8 > "$OUT/initdb12.log" 2>&1 \
        || die "initdb failed"
      cat >> "$DATA/postgresql.conf" <<CONF
listen_addresses = ''
unix_socket_directories = '$SOCK'
port = $PORT12
autovacuum = off
fsync = off
shared_buffers = '512MB'
maintenance_work_mem = '256MB'
max_parallel_maintenance_workers = 0
CONF
    fi
    # The mark the server-error check reads from, as in the 17 leg.
    { [ -f "$OUT/server12.log" ] && wc -l < "$OUT/server12.log" || printf '0\n'; } \
      | tr -d ' ' > "$OUT/server12.log.mark"
    "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server12.log" -w start > /dev/null || die "start failed"
  fi
  # The helpers connect to $DB, which does not exist yet on a fresh cluster, so
  # this one check connects to postgres rather than failing its way to createdb.
  "$BIN/psql" -X -At -q -v ON_ERROR_STOP=1 -d postgres \
      -c "select /* wiki_btree_leg12_database_exists */ 1
            from pg_database where datname='$DB'" | grep -q 1 \
    || "$BIN/createdb" -T template0 -E UTF8 --locale=C "$DB"
  note "$(s 'select /* wiki_btree_leg12_version */ version()')"
}

# ---------------------------------------------------------------- exact ------
# The first result of this leg is the parse outcome of the unmodified text.
stage_exact() {
  say "the exact current text, unmodified, on 12.2"
  [ -f "$PAGE" ] || die "no page at $PAGE; set PAGE or run from the repository root"
  md_block sql 1 "$PAGE" > "$SQLD/est_r2.sql"
  local got; got=$(sha256sum < "$SQLD/est_r2.sql" | cut -d' ' -f1)
  [ "$got" = "$BASE1" ] && note "text hash matches the baseline" \
                        || note "text hash DIFFERS from the baseline: $got"
  if "$BIN/psql" -X -v ON_ERROR_STOP=1 -d "$DB" -f "$SQLD/est_r2.sql" \
       > "$OUT/v12_exact.txt" 2>&1; then
    printf 'exact_text=executes\n' > "$OUT/v12_facts.txt"
    # How many rows it printed here.  Since 2026-09-14 the text has neither
    # the 1 MB filter nor the LIMIT 20, so this is every candidate index the
    # exclusion terms did not withhold.
    printf 'exact_rows=%s\n' \
      "$(grep -E '^\([0-9]+ rows?\)$' "$OUT/v12_exact.txt" | tail -1)" \
      >> "$OUT/v12_facts.txt"
    note "the exact text EXECUTES on 12.2"
  else
    printf 'exact_text=refused\n' > "$OUT/v12_facts.txt"
    grep -E 'ERROR|LINE' "$OUT/v12_exact.txt" | head -4 | while read -r l; do
      printf 'exact_error=%s\n' "$l" >> "$OUT/v12_facts.txt"; done
    note "the exact text is REFUSED: $(grep -m1 ERROR "$OUT/v12_exact.txt")"
  fi
}

# ------------------------------------------------------------- transform -----
# One documented edit per construct the server refuses, applied line by line so
# the diff against the filed text is auditable.  Each edit is recorded.
#
# Since 2026-09-10 the filed text reads pg_stats_ext.inherited through
# row_to_json() instead of naming it, so this stage has nothing left to edit
# and transform_edits comes back 0.  The rule below is kept as a regression
# guard: if a future revision names the column again, this leg records the
# edit rather than failing, and the extstat stage measures what it costs.
stage_transform() {
  say "transformer: drop the constructs this server refuses"
  local line dropped=0
  : > "$SQLD/est_v12.sql"
  while IFS= read -r line; do
    case $line in
      # A server whose pg_stats_ext exposes no inherited column refuses this
      # reference.  Dropping the line widens the extstat CTE to whatever rows
      # the view does expose, which is why the filed text no longer names it.
      "                          AND se.inherited = false")
        dropped=$((dropped + 1))
        printf -- '-- dropped: %s\n' "$line" >> "$SQLD/est_v12.sql"; continue ;;
    esac
    printf '%s\n' "$line" >> "$SQLD/est_v12.sql"
  done < "$SQLD/est_r2.sql"
  printf 'transform_edits=%s\n' "$dropped" >> "$OUT/v12_facts.txt"
  if "$BIN/psql" -X -v ON_ERROR_STOP=1 -d "$DB" -f "$SQLD/est_v12.sql" \
       > "$OUT/v12_transformed.txt" 2>&1; then
    printf 'transformed_text=executes\n' >> "$OUT/v12_facts.txt"
    note "the transformed text executes after $dropped edit(s)"
  else
    printf 'transformed_text=refused\n' >> "$OUT/v12_facts.txt"
    grep -m1 ERROR "$OUT/v12_transformed.txt" >&2
    die "the transformer is incomplete; add the next refused construct"
  fi
  harness_view "$SQLD/est_v12.sql" est12 "$INTERNALS" > "$SQLD/view_v12.sql"
  fl "$SQLD/view_v12.sql" || die "harness view failed"
}

# ---------------------------------------------------------------- facts ------
stage_facts() {
  say "version-local facts this leg depends on, measured not assumed"
  { printf 'server_version_num=%s\n' \
      "$(s "SELECT /* wiki_btree_leg12_server_version */ current_setting('server_version_num')")"
    printf 'block_size=%s max_data_alignment=%s\n' \
      "$(s "SELECT /* wiki_btree_leg12_block_size */ current_setting('block_size')")" \
      "$(s 'SELECT /* wiki_btree_leg12_alignment */ max_data_alignment FROM pg_control_init()')"
    printf 'has_force_next_flush=%s\n' \
      "$(s "SELECT /* wiki_btree_leg12_has_flush */
                   (to_regprocedure('pg_stat_force_next_flush()') IS NOT NULL)::text")"
    printf 'pg_stats_ext_columns=%s\n' \
      "$(s "SELECT /* wiki_btree_leg12_stats_ext_columns */
                   string_agg(attname, ',' ORDER BY attnum) FROM pg_attribute
             WHERE attrelid = 'pg_stats_ext'::regclass AND attnum > 0")"
    printf 'btree_support_procs=%s\n' \
      "$(s "SELECT /* wiki_btree_leg12_support_procs */
                   string_agg(DISTINCT amprocnum::text, ',' ORDER BY amprocnum::text)
              FROM pg_amproc ap JOIN pg_opfamily f ON f.oid = ap.amprocfamily
              JOIN pg_am a ON a.oid = f.opfmethod WHERE a.amname = 'btree'")"
  } >> "$OUT/v12_facts.txt"
  # Whether the reloption exists is answered by trying it, not by asserting it.
  # Disposable fixture: dedup_probe is created and dropped in the sandbox.
  q "DROP TABLE IF EXISTS dedup_probe" > /dev/null 2>&1
  q "CREATE TABLE dedup_probe(k int)" > /dev/null 2>&1
  if q "CREATE INDEX dedup_probe_i ON dedup_probe (k) WITH (deduplicate_items = off)" \
       > /dev/null 2>&1; then
    printf 'deduplicate_items_reloption=accepted\n' >> "$OUT/v12_facts.txt"
  else
    printf 'deduplicate_items_reloption=rejected\n' >> "$OUT/v12_facts.txt"
  fi
  q "DROP TABLE IF EXISTS dedup_probe" > /dev/null 2>&1
  cat "$OUT/v12_facts.txt" >&2
}

# ---------------------------------------------------------------- fixtures ---
stage_fixtures() {
  say "the constructible fixture subset, one writer session per step"
  # One VERBOSE log per run, not per stage: every maintain() appends to it and
  # the proof parse reads it whole, so it starts empty here.
  mkdir -p "$OUT"; : > "$VERBOSELOG"
  # Disposable fixtures: every statement from here to the end of the stage
  # creates or drops objects in the leg12 database of the sandbox cluster.
  fl /dev/stdin <<'SQL'
SET /* wiki_btree_leg12_client_min_messages */ client_min_messages = warning;
DROP EVENT TRIGGER IF EXISTS snap12_on_build_trg;
DROP VIEW IF EXISTS verdicts12;
DROP TABLE IF EXISTS snap12;
DROP TABLE IF EXISTS res12, plan12 CASCADE;
DROP TABLE IF EXISTS maint, horizon, pageclass;
CREATE TABLE plan12(num int, grp text, req text, idx text, rowsql text,
                    want_rows bigint, built_rows bigint, want_stage text,
                    PRIMARY KEY (num));
CREATE TABLE res12(num int, req text, idx text, size_before bigint, size_after bigint,
                   blocks_before int, blocks_after int, status text,
                   wsp numeric, wspf numeric, caveats text, equalimage text,
                   modelled_rows numeric, key_groups numeric, tids numeric,
                   idx_reltuples numeric, dedup_applies bool, is_partial bool,
                   suppress_row bool, true_rows bigint, want_rows bigint,
                   PRIMARY KEY (num));
CREATE OR REPLACE FUNCTION plan_add(n int, r text, i text, q text DEFAULT NULL,
                                    w bigint DEFAULT NULL) RETURNS void
LANGUAGE sql AS
$$ INSERT INTO plan12(num, req, idx, rowsql, want_rows)
   VALUES (n, r, i, q, w) $$;

-- Phase 2 of the shared mandatory suite, the baseline, and rule 1's cut at the
-- index build.  This leg has no pg_stat_force_next_flush(), but the baseline
-- reads pg_class and pg_relation_size, not a cumulative view, so the event
-- trigger records it with no publication wait at all.
CREATE TABLE snap12(phase text, idx text, bytes numeric, blocks int,
                    tbl_tuples numeric, idx_tuples numeric,
                    PRIMARY KEY (phase, idx));

-- The no-defeat rule's three tables and three functions, as the 17 leg has
-- them, with this server's two differences: there is no transaction_timeout to
-- record, and maint_end only stamps the end, because a 12 server publishes a
-- VACUUM's counters through its statistics collector rather than on demand, so
-- the counters are refilled by maint_after() once the churn stage has polled.
-- No primary key on any of the three, deliberately: the estimator's candidate
-- set is every B-tree index outside the system schemas, so a harness index in
-- public would show up in the report the run is scoring.  maint_begin()
-- therefore deletes before it inserts instead of upserting.
CREATE TABLE maint(tbl text, ord int, source text,
                   started timestamptz, ended timestamptz,
                   removed numeric, remain numeric, dead_not_removable numeric,
                   mods_after numeric, dead_after numeric, timeouts text);
CREATE TABLE horizon(step text, tbl text, at timestamptz, xmin_holders int,
                     open_xacts int, slots int, slot_xmins int, prepared int,
                     detail text);
CREATE TABLE pageclass(idx text, leaf_pages numeric,
                       empty_pages numeric, deleted_pages numeric,
                       avg_leaf_density numeric, index_size numeric);

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

CREATE OR REPLACE FUNCTION maint_begin(p_tbl text, p_source text DEFAULT 'fixture')
RETURNS void LANGUAGE sql AS
$mb$ DELETE FROM maint WHERE tbl = p_tbl;
     INSERT INTO maint(tbl, ord, source, started, timeouts)
     SELECT p_tbl, coalesce((SELECT max(ord) FROM maint), 0) + 1, p_source,
            clock_timestamp(),
            'statement_timeout=' || current_setting('statement_timeout') ||
            ' lock_timeout=' || current_setting('lock_timeout') ||
            ' idle_in_transaction_session_timeout='
              || current_setting('idle_in_transaction_session_timeout');
     SELECT horizon_probe('maint', p_tbl) $mb$;

CREATE OR REPLACE FUNCTION maint_end(p_tbl text) RETURNS void LANGUAGE sql AS
$me$ UPDATE maint SET ended = clock_timestamp() WHERE tbl = p_tbl $me$;

CREATE OR REPLACE FUNCTION maint_after() RETURNS void LANGUAGE sql AS
$ma$ UPDATE maint m
        SET mods_after = st.n_mod_since_analyze, dead_after = st.n_dead_tup
       FROM pg_stat_all_tables st
      WHERE st.schemaname = 'public' AND st.relname = m.tbl $ma$;

CREATE OR REPLACE FUNCTION snap_take(ph text, i text) RETURNS void
LANGUAGE sql AS
$$ INSERT INTO snap12(phase, idx, bytes, blocks, tbl_tuples, idx_tuples)
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

CREATE OR REPLACE FUNCTION snap_on_build() RETURNS event_trigger
LANGUAGE plpgsql AS $et$
DECLARE c record;
BEGIN
  FOR c IN SELECT objid FROM pg_event_trigger_ddl_commands()
            WHERE command_tag = 'CREATE INDEX' LOOP
    INSERT INTO snap12(phase, idx, bytes, blocks, tbl_tuples, idx_tuples)
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
CREATE EVENT TRIGGER snap12_on_build_trg ON ddl_command_end
  WHEN TAG IN ('CREATE INDEX') EXECUTE FUNCTION snap_on_build();

CREATE OR REPLACE PROCEDURE assert_built() LANGUAGE plpgsql AS $ab$
DECLARE p record; n bigint;
BEGIN
  FOR p IN SELECT * FROM plan12 WHERE rowsql IS NOT NULL ORDER BY num LOOP
    EXECUTE p.rowsql INTO n;
    UPDATE plan12 SET built_rows = n WHERE num = p.num;
  END LOOP;
END $ab$;
CREATE OR REPLACE PROCEDURE score_all() LANGUAGE plpgsql AS $sc$
DECLARE p record; e record; sb bigint; sa bigint; tr bigint;
BEGIN
  FOR p IN SELECT * FROM plan12 ORDER BY num LOOP
    tr := NULL;
    IF p.rowsql IS NOT NULL THEN EXECUTE p.rowsql INTO tr; END IF;
    sb := pg_relation_size(p.idx::regclass);
    SELECT * INTO e FROM est12 WHERE indexname = p.idx;
    IF NOT FOUND THEN RAISE EXCEPTION 'estimator returned no row for %', p.idx; END IF;
    EXECUTE format('REINDEX INDEX %I', p.idx);
    sa := pg_relation_size(p.idx::regclass);
    INSERT INTO res12 VALUES (p.num, p.req, p.idx, sb, sa, sb / 8192, sa / 8192,
      e.status, e.wasted_space_pct, e.wasted_space_pct_floor, e.caveats,
      e.equalimage, e.modelled_rows, e.key_groups, e.tids_per_tuple,
      e.idx_reltuples, e.dedup_applies, e.is_partial, e.suppress_row,
      tr, p.want_rows);
  END LOOP;
END $sc$;
-- The verdict view, scored by the shared mandatory suite's four bands on the
-- same decision rule as the 17 leg: a suppressed row and a row carrying one of
-- the five caveats the page refuses to promote are both 'leave', whatever the
-- percentage says.  Size left that rule on 2026-09-14 with the statement's
-- 1 MB filter; over_1mb stays as an observation and decides nothing.
-- verdict_floor is the older band set this page filed, kept on the same row
-- for comparison.
CREATE VIEW verdicts12 AS
SELECT r.num, p.grp, r.idx, r.req, s.blocks AS blocks_built,
       r.blocks_before, r.blocks_after, a.actual, r.wsp, r.wspf,
       f.reported, f.alertable, f.over_1mb, d.taken_stage, x.expected_stage,
       p.want_stage,
       CASE WHEN d.taken_stage = 'rebuild' AND a.actual < 10  THEN 'CRITICAL FALSE POSITIVE'
            WHEN d.taken_stage = 'rebuild' AND a.actual < 35  THEN 'FALSE POSITIVE'
            WHEN d.taken_stage = 'leave'   AND a.actual >= 50 THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END                                   AS verdict,
       CASE WHEN d.taken_stage = 'leave' AND a.actual >= 50
            THEN CASE WHEN NOT f.reported  THEN 'withheld'
                      WHEN NOT f.alertable THEN 'caveat'
                      WHEN r.wspf IS NULL  THEN 'unmeasured'
                      ELSE 'threshold' END END                AS lost_by,
       CASE WHEN r.wspf IS NULL                          THEN 'UNMEASURED'
            WHEN r.wspf >= 50 AND a.actual < 10          THEN 'CRITICAL FALSE POSITIVE'
            WHEN r.wspf >= 50 AND a.actual < 45          THEN 'FALSE POSITIVE'
            WHEN r.wspf >= 50 AND r.wspf - a.actual > 5  THEN 'FALSE POSITIVE'
            WHEN r.wspf <  45 AND a.actual >= 50         THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END                              AS verdict_floor,
       (p.want_rows IS NULL OR p.built_rows = p.want_rows) AS contract_ok,
       s.tbl_tuples AS tbl_tuples_built, c.tbl_tuples AS tbl_tuples_churned,
       s.idx_tuples AS idx_tuples_built, c.idx_tuples AS idx_tuples_churned,
       p.built_rows, r.true_rows, p.want_rows,
       r.equalimage, r.dedup_applies, r.modelled_rows, r.idx_reltuples,
       r.status, r.caveats,
       -- The maintenance this fixture got, and the no-defeat proofs with it.
       ct.relname AS tbl, (m.tbl IS NOT NULL) AS maintained,
       m.source AS maint_source, m.dead_not_removable,
       m.removed AS maint_removed, m.dead_after, m.mods_after, m.timeouts,
       qc.deleted_pages, qc.empty_pages,
       qc.avg_leaf_density AS density_after_maint
  FROM res12 r
  JOIN plan12 p ON p.num = r.num
  LEFT JOIN snap12 s ON s.phase = 'built'   AND s.idx = r.idx
  LEFT JOIN snap12 c ON c.phase = 'churned' AND c.idx = r.idx
  LEFT JOIN pg_class ic ON ic.relname = r.idx AND ic.relkind = 'i'
  LEFT JOIN pg_index ix ON ix.indexrelid = ic.oid
  LEFT JOIN pg_class ct ON ct.oid = ix.indrelid
  LEFT JOIN maint m ON m.tbl = ct.relname
  LEFT JOIN pageclass qc ON qc.idx = r.idx
  CROSS JOIN LATERAL (
        SELECT round(100.0 * (r.size_before - r.size_after)
                     / greatest(r.size_before, 1), 1) AS actual) a
  CROSS JOIN LATERAL (
        SELECT NOT r.suppress_row                             AS reported,
               (r.caveats IS NULL OR r.caveats !~
                '(never analyzed|row-count sources disagree|statistics not visible|zero modelled rows|wide compressible key)')
                                                              AS alertable,
               -- observation only: the size the removed 1 MB filter tested
               (r.size_before > 1024 * 1024)                  AS over_1mb) f
  CROSS JOIN LATERAL (
        SELECT CASE WHEN f.reported AND f.alertable
                     AND r.wspf >= 50 THEN 'rebuild' ELSE 'leave' END AS taken_stage) d
  CROSS JOIN LATERAL (
        SELECT CASE WHEN r.suppress_row OR NOT f.alertable THEN 'leave'
                    WHEN r.wspf >= 50 THEN 'rebuild'
                    ELSE 'leave' END                                   AS expected_stage) x;
SQL

  # Three fresh sorted builds at key widths 8, 100 and 1000 stood here as
  # numbers 8, 100 and 1000 until 2026-09-14.  They were this leg's half of the
  # page-local geometry and acceptance fixtures, which no mandatory test
  # defines, and they went with them; 1002, a freshly built partial index, is
  # this leg's fresh-index control.

  # -- 1001: duplicate-heavy index, the deduplication difference ------------
  q "DROP TABLE IF EXISTS dup CASCADE"
  q "CREATE TABLE dup AS SELECT (i % 1000)::int AS k FROM generate_series(1, 500000) i"
  loaded dup 500000; q "ANALYZE dup"; analyzed dup
  q "CREATE INDEX dup_k ON dup (k)"
  q "SELECT plan_add(1001, 'duplicate-heavy index, 500 rows per key', 'dup_k',
                     'SELECT count(*) FROM dup', 500000)"

  # -- 1002-1005: the partial family ----------------------------------------
  local f
  for f in 1002 1003 1004; do
    q "DROP TABLE IF EXISTS pb$f CASCADE"
    q "CREATE TABLE pb$f AS SELECT (i % 5 = 0) AS hot, i::int AS k
         FROM generate_series(1, 500000) i"
    loaded "pb$f" 500000; q "ANALYZE pb$f"; analyzed "pb$f"
    q "CREATE INDEX p$f ON pb$f (k) WHERE hot"
  done
  q "SELECT plan_add(1002, 'freshly built partial index', 'p1002',
                     'SELECT count(*) FROM pb1002 WHERE hot', 100000)"
  q "DELETE FROM pb1003 WHERE hot AND (k / 5) % 2 = 0"
  maintain pb1003
  q "SELECT plan_add(1003, '50% of the subset deleted', 'p1003',
                     'SELECT count(*) FROM pb1003 WHERE hot', 50000)"
  q "DELETE FROM pb1004 WHERE hot AND (k / 5) % 10 <> 0"
  maintain pb1004
  q "SELECT plan_add(1004, '90% of the subset deleted', 'p1004',
                     'SELECT count(*) FROM pb1004 WHERE hot', 10000)"

  q "DROP TABLE IF EXISTS q1005 CASCADE"
  q "CREATE TABLE q1005 AS SELECT i::int AS id, 'pending'::text AS state
       FROM generate_series(1, 1000000) i"
  loaded q1005 1000000; q "ANALYZE q1005"; analyzed q1005
  q "CREATE INDEX p1005 ON q1005 (id) WHERE state = 'pending'"
  q "UPDATE q1005 SET state = 'done'"
  maintain q1005
  q "SELECT plan_add(1005, 'drained queue, VACUUM + ANALYZE', 'p1005',
                     'SELECT count(*) FROM q1005 WHERE state = ''pending''', 0)"

  # -- 1006-1007: wide keys and a wide INCLUDE column ------------------------
  q "DROP TABLE IF EXISTS wide CASCADE"
  q "CREATE TABLE wide AS SELECT (i % 20 = 0) AS hot, i::int AS k,
       CASE WHEN i % 20 = 0 THEN repeat('W', 190) || lpad(i::text, 10, '0')
            ELSE lpad(i::text, 12, 'n') END AS s
       FROM generate_series(1, 500000) i"
  loaded wide 500000; q "ANALYZE wide"; analyzed wide
  q "CREATE INDEX w_key ON wide (s) WHERE hot"
  q "CREATE INDEX w_inc ON wide (k) INCLUDE (s) WHERE hot"
  q "SELECT plan_add(1006, 'partial index on a wide key inside the subset', 'w_key',
                     'SELECT count(*) FROM wide WHERE hot', 25000)"
  q "SELECT plan_add(1007, 'partial index with a wide INCLUDE column', 'w_inc',
                     'SELECT count(*) FROM wide WHERE hot', 25000)"

  # -- 1008-1009: expression indexes with and without statistics -------------
  q "DROP TABLE IF EXISTS ex CASCADE"
  q "CREATE TABLE ex AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
       FROM generate_series(1, 500000) i"
  loaded ex 500000; q "ANALYZE ex"; analyzed ex
  q "CREATE INDEX ex_nostats ON ex (upper(s))"
  q "SELECT plan_add(1008, 'expression index, no statistics row', 'ex_nostats',
                     'SELECT count(*) FROM ex', 500000)"
  q "DROP TABLE IF EXISTS ex2 CASCADE"
  q "CREATE TABLE ex2 AS SELECT i::int AS k, lpad(i::text, 100, '0') AS s
       FROM generate_series(1, 500000) i"
  loaded ex2 500000
  q "CREATE INDEX ex_stats ON ex2 (upper(s))"
  q "ANALYZE ex2"; analyzed ex2
  q "SELECT plan_add(1009, 'expression index, analysed after the build', 'ex_stats',
                     'SELECT count(*) FROM ex2', 500000)"

  # 1010, 1011 and 1012 built nz_k, nzb_k and i_trunc here, this leg's legs of
  # the mandatory suite's number 121: emptied, vacuumed and reloaded with the
  # ANALYZE withheld, the same plus a REINDEX while empty, and TRUNCATE then
  # reload without an ANALYZE.  121 is retired, so all three are gone and their
  # numbers are not reused.

  # -- 1013-1016: the equal-image gate, three types and a nondeterministic
  #    collation.  What the gate answers here is a result, not an assumption.
  q "DROP TABLE IF EXISTS gate CASCADE"
  q "DROP COLLATION IF EXISTS nd12"
  q "CREATE COLLATION nd12 (provider = icu, locale = 'und-u-ks-level2',
                            deterministic = false)" \
    || note "nondeterministic ICU collation refused on this build"
  q "CREATE TABLE gate AS
       SELECT (i % 5000)::int AS a, (i % 5000)::numeric AS n,
              'key' || lpad((i % 5000)::text, 8, '0') AS s
         FROM generate_series(1, 500000) i"
  loaded gate 500000; q "ANALYZE gate"; analyzed gate
  q "CREATE INDEX g_int4 ON gate (a)"
  q "CREATE INDEX g_num  ON gate (n)"
  q "CREATE INDEX g_text ON gate (s)"
  q "CREATE INDEX g_nd   ON gate (s COLLATE nd12)" \
    || note "index on a nondeterministic collation refused"
  q "SELECT plan_add(1013, 'int4 key, gate verdict', 'g_int4', 'SELECT count(*) FROM gate', 500000)"
  q "SELECT plan_add(1014, 'numeric key, gate verdict', 'g_num', 'SELECT count(*) FROM gate', 500000)"
  q "SELECT plan_add(1015, 'text key, gate verdict', 'g_text', 'SELECT count(*) FROM gate', 500000)"
  s "SELECT 1 FROM pg_class WHERE relname = 'g_nd'" | grep -q 1 && \
    q "SELECT plan_add(1016, 'nondeterministic collation, gate verdict', 'g_nd',
                       'SELECT count(*) FROM gate', 500000)"

  # The shared suite's families, as far as this leg's constructible subset
  # reaches them, and the per-fixture prediction, both filed here before the
  # run.  The freshly built partial index 1002 is this leg's fresh-index
  # control, so rule 2 exempts it from the drain and it is predicted 'leave'.
  fl /dev/stdin <<'SQL'
SET /* wiki_btree_leg12_plan_client_min_messages */ client_min_messages = warning;
UPDATE /* wiki_btree_leg12_families */ plan12 SET grp =
       CASE WHEN num BETWEEN 1002 AND 1005  THEN 'partial'
            WHEN num BETWEEN 1013 AND 1016  THEN 'gate'
            ELSE 'control' END;
UPDATE /* wiki_btree_leg12_predictions */ plan12 SET want_stage =
       CASE WHEN num = 1002 THEN 'leave'
            WHEN num = 1008 THEN 'leave'
            ELSE 'rebuild' END;
CALL /* wiki_btree_leg12_assert_built */ assert_built();
SELECT count(*) AS planned_fixtures FROM plan12;
SELECT count(*) AS baselines_taken FROM snap12
 WHERE phase = 'built' AND idx IN (SELECT idx FROM plan12);
SELECT count(*) AS build_contract_failures FROM plan12
 WHERE want_rows IS NOT NULL AND built_rows <> want_rows;
SQL
  note "$(s 'SELECT count(*) || '\'' fixtures planned, '\'' ||
             (SELECT count(*) FROM snap12 WHERE phase = '\''built'\''
                AND idx IN (SELECT idx FROM plan12)) ||
             '\'' baselines, '\'' ||
             (SELECT count(*) FROM plan12
               WHERE want_rows IS NOT NULL AND built_rows <> want_rows) ||
             '\'' build-contract failures'\'' FROM plan12')"
}

# ---------------------------------------------------------------- churn ------
# Phase 3 on this leg: rule 2's uniform drain over the shape fixtures that have
# no churn of their own, then rule 3's census, then the churned snapshot.  The
# fresh-index controls are exempt and appear nowhere below.  There is no
# pg_stat_force_next_flush() on this server, so the drain session is left to
# exit and the census reads n_mod_since_analyze from a new one a second later,
# which is how this leg publishes every other counter it reads.
stage_churn() {
  say "churn: rule 2 drain, rule 3 census, churned snapshot"
  [ -n "$(s 'SELECT 1 FROM plan12 LIMIT 1')" ] \
    || die "no plan12 rows; run the fixtures stage first"
  # The drain deletes here and the maintenance follows through maintain(), one
  # table at a time, so that each statement is bracketed and proved exactly as
  # the fixtures' own are.  The DELETEs stay in one generated file; only the
  # VACUUM ANALYZE moved out of it.
  cat > "$SQLD/drain12.sql" <<'DRAIN12'
-- Disposable fixtures, leg12 database of the sandbox cluster only.
SET /* wiki_btree_drain12_client_min_messages */ client_min_messages = warning;
SET /* wiki_btree_drain12_statement_timeout */ statement_timeout = 0;
SET /* wiki_btree_drain12_lock_timeout */ lock_timeout = 0;
SET /* wiki_btree_drain12_idle_timeout */ idle_in_transaction_session_timeout = 0;
SELECT /* wiki_btree_drain12_generator */ format(st.tmpl, tb.name)
  FROM (VALUES (1, 'dup'), (2, 'wide'), (3, 'ex'), (4, 'ex2'),
               (5, 'gate')) tb(n, name)
 CROSS JOIN (VALUES
        (1, 'DELETE /* wiki_btree_drain */ FROM %1$I WHERE ((ctid::text::point)[0])::int %% 10 <> 0')) st(k, tmpl)
 ORDER BY tb.n, st.k
\gexec
DRAIN12
  fl "$SQLD/drain12.sql" > "$OUT/drain12.txt" 2>&1 || die "drain failed"
  local dt
  for dt in dup wide ex ex2 gate; do maintain "$dt" drain; done
  note "drained and maintained 5 tables: dup, wide, ex, ex2, gate"
  sleep 1                      # the drain session has exited; let it publish
  analyzed dup || die "drain statistics did not publish"

  cat > "$SQLD/census12.sql" <<'CENSUS12'
-- The same rule 3 test as the 17 leg, read from this server's own settings.
-- The census runs ANALYZE, so its three settable timeouts are 0 too, and the
-- horizon is probed on both sides of it, because the no-defeat rule's window
-- closes only once the census has finished.
-- Disposable fixtures, leg12 database of the sandbox cluster only.
SET /* wiki_btree_census12_client_min_messages */ client_min_messages = warning;
SET /* wiki_btree_census12_statement_timeout */ statement_timeout = 0;
SET /* wiki_btree_census12_lock_timeout */ lock_timeout = 0;
SET /* wiki_btree_census12_idle_timeout */ idle_in_transaction_session_timeout = 0;
SELECT /* wiki_btree_census12_horizon_before */ horizon_probe('census-before', NULL);
DROP TABLE IF EXISTS autoanl12;
CREATE TABLE autoanl12 AS
SELECT /* wiki_btree_autoanalyze12_census */
       c.relname                                      AS tbl,
       GREATEST(c.reltuples, 0)::numeric              AS reltuples,
       st.n_mod_since_analyze::numeric                AS mods,
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
   AND c.relname NOT IN ('plan12', 'res12', 'snap12', 'xstat_res',
                         'autoanl12', 'maint', 'horizon', 'pageclass');

SELECT /* wiki_btree_autoanalyze12_generator */
       format('ANALYZE /* wiki_btree_autoanalyze */ %I', tbl)
  FROM autoanl12 WHERE would_autoanalyze ORDER BY tbl
\gexec

SELECT /* wiki_btree_census12_horizon_after */ horizon_probe('census-after', NULL);
SELECT count(*) AS tables_censused,
       count(*) FILTER (WHERE would_autoanalyze) AS analyzed,
       min(mod_pct) FILTER (WHERE would_autoanalyze) AS lowest_analyzed_pct,
       max(mod_pct) FILTER (WHERE NOT would_autoanalyze) AS highest_left_alone_pct
  FROM autoanl12;
CENSUS12
  fl "$SQLD/census12.sql" > "$OUT/census12.txt" 2>&1 || die "census failed"
  tail -4 "$OUT/census12.txt" >&2

  # The statement's row-count caveat compares n_live_tup, which lives in a
  # cumulative view, with the index's pg_class.reltuples, and this server has
  # no pg_stat_force_next_flush().  A drain that publishes its DELETE counts
  # after its own ANALYZE has reset them leaves n_live_tup at 0 beside a
  # catalog count of 50,172, and waiting does not repair that: only another
  # ANALYZE does, which is exactly what the census above just ran.  So the wait
  # belongs here, after the census, and it waits for that comparison itself.
  # Without it the decide phase reads a published zero and every drained
  # non-partial fixture raises "row-count sources disagree: analyze first",
  # which is a publication artifact rather than a reading of the index.
  wait_for "NOT EXISTS (SELECT 1 FROM pg_stat_all_tables st
                          JOIN pg_class c ON c.oid = st.relid
                         WHERE st.relname IN ('dup', 'wide', 'ex', 'ex2', 'gate')
                           AND GREATEST(st.n_live_tup, c.reltuples)
                               > 1.1 * GREATEST(LEAST(st.n_live_tup, c.reltuples), 1))" \
           "drained live counts published" \
    || die "the drained live counts did not publish within 60s"
  note "drained live counts published and within 10% of the catalog"

  # -- the no-defeat proofs, this leg's copy --------------------------------
  # The page classes first, then the four proofs.  pgstattuple comes from the
  # same build as the server; the page-class read is read-only, so the decide
  # phase that follows still sees the state the maintenance left.
  say "no-defeat proofs: completion, VERBOSE counts, horizon, page classes"
  q 'CREATE EXTENSION IF NOT EXISTS pgstattuple' > /dev/null \
    || die "pgstattuple is not installed; the page-class read needs it"
  fl /dev/stdin > "$OUT/pageclass12.txt" 2>&1 <<'SQL'
SET /* wiki_btree_pageclass12_client_min_messages */ client_min_messages = warning;
DELETE FROM pageclass;
INSERT /* wiki_btree_pageclass12 */ INTO pageclass
       (idx, leaf_pages, empty_pages, deleted_pages, avg_leaf_density, index_size)
SELECT p.idx, m.leaf_pages, m.empty_pages, m.deleted_pages,
       CASE WHEN m.avg_leaf_density = 'NaN'::float8 THEN NULL
            ELSE round(m.avg_leaf_density::numeric, 2) END,
       m.index_size
  FROM plan12 p, LATERAL pgstatindex(p.idx::regclass) m;
SELECT /* wiki_btree_pageclass12_report */
       count(*) || ' indexes read, '
       || count(*) FILTER (WHERE deleted_pages > 0) || ' with deleted pages, '
       || count(*) FILTER (WHERE empty_pages > 0) || ' with half-dead pages, '
       || coalesce(sum(deleted_pages), 0) || ' deleted pages in total'
  FROM pageclass;
SQL
  [ $? -eq 0 ] || die "page-class read failed"
  tail -1 "$OUT/pageclass12.txt" >&2
  maint_proofs12
  churned_snapshot
}

# The four proofs, checked and summarised, for every maintenance statement this
# run has issued so far.  It re-reads the whole VERBOSE log each time, so
# calling it again after a later maintenance statement - the extstat stage's -
# re-proves the earlier ones rather than forgetting them; the UPDATEs are keyed
# by table, so applying them twice changes nothing.
maint_proofs12() {
  local n bad
  parse_verbose "$VERBOSELOG" > "$SQLD/maint_verbose12.sql"
  [ -s "$SQLD/maint_verbose12.sql" ] \
    || die "the VACUUM VERBOSE output produced no dead-row-version line: proof 2 is missing"
  fl "$SQLD/maint_verbose12.sql" > /dev/null || die "recording the VERBOSE counts failed"
  q "SELECT /* wiki_btree_leg12_maint_after */ maint_after()" > /dev/null \
    || die "the post-maintenance counter read failed"
  n=$(s 'SELECT count(*) FROM maint')
  [ "${n:-0}" -gt 0 ] || die "no maintenance statement was recorded at all"
  bad=$(s 'SELECT count(*) FROM maint WHERE ended IS NULL')
  [ "$bad" = 0 ] || die "$bad maintenance statements did not complete"
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
  : > "$OUT/maint_skips12.txt"
  local mark=0 ln=0 line
  [ -f "$OUT/server12.log.mark" ] && mark=$(tr -d ' \n' < "$OUT/server12.log.mark")
  if [ -f "$OUT/server12.log" ]; then
    while IFS= read -r line; do
      ln=$((ln + 1)); [ "$ln" -le "$mark" ] && continue
      case $line in
        *'skipping vacuum of '*|*'skipping analyze of '*|\
        *'canceling autovacuum task'*|*'canceling statement due to'*)
          printf '%s\n' "$line" >> "$OUT/maint_skips12.txt" ;;
      esac
    done < "$OUT/server12.log"
  fi
  # grep -c on an empty file prints 0 and exits 1, so the count is taken only
  # when there is something to count; an "|| printf 0" fallback here would
  # concatenate the two zeros and fail the check on a clean run.
  local skips=0
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
    printf 'skip or cancellation lines %s\n' "$skips"; } > "$OUT/maint_proofs12.txt"
  cat "$OUT/maint_proofs12.txt" >&2
  [ "$skips" = 0 ] || { cat "$OUT/maint_skips12.txt" >&2
                        die "$skips skip or cancellation line(s) in the server log"; }
}

# ------------------------------------------------------- churned snapshot ----
# The end of phase 3, called by stage_churn rather than selectable on its own.
churned_snapshot() {
  say "the churned snapshot of every planned index"
  fl /dev/stdin > "$OUT/snapshots12.txt" 2>&1 <<'SQL'
SET /* wiki_btree_snapc12_client_min_messages */ client_min_messages = warning;
SELECT /* wiki_btree_snap12_churned */ count(*) AS churned_snapshots
  FROM (SELECT snap_take('churned', idx) FROM plan12 ORDER BY num) s;
SELECT /* wiki_btree_snap12_phases */ phase, count(*) FROM snap12 GROUP BY phase ORDER BY phase;
SQL
  [ $? -eq 0 ] || die "churned snapshot failed"
  tail -8 "$OUT/snapshots12.txt" >&2
}

# ---------------------------------------------------------------- score ------
stage_score() {
  say "score the 12.2 subset against a measured REINDEX INDEX"
  fl /dev/stdin <<'SQL'
SET /* wiki_btree_leg12_statement_timeout */ statement_timeout = '600s';
SET /* wiki_btree_leg12_lock_timeout */ lock_timeout = '2s';
CALL /* wiki_btree_leg12_score_all */ score_all();
SQL
  [ $? -eq 0 ] || die "scoring failed"
  t "SELECT /* wiki_btree_leg12_verdict_rows */
            num, grp, idx, blocks_built, blocks_before, blocks_after, actual,
            wsp, wspf, taken_stage, want_stage, verdict, lost_by,
            verdict_floor, reported, contract_ok, equalimage, dedup_applies,
            status, caveats FROM verdicts12 ORDER BY num" > "$OUT/verdicts12.txt" 2>&1
  t "SELECT /* wiki_btree_leg12_verdict_shared */
            grp, verdict, count(*) FROM verdicts12 GROUP BY 1, 2 ORDER BY 1, 2" \
    >> "$OUT/verdicts12.txt" 2>&1
  t "SELECT /* wiki_btree_leg12_verdict_totals */
            count(*) AS fixtures,
            count(*) FILTER (WHERE verdict = 'PASS')                 AS pass,
            count(*) FILTER (WHERE verdict = 'CRITICAL FALSE POSITIVE') AS crit_fp,
            count(*) FILTER (WHERE verdict = 'FALSE POSITIVE')       AS fp,
            count(*) FILTER (WHERE verdict = 'FALSE NEGATIVE')       AS fn,
            count(*) FILTER (WHERE expected_stage <> taken_stage)    AS gate_disagrees,
            count(*) FILTER (WHERE want_stage <> taken_stage)        AS want_miss,
            count(*) FILTER (WHERE NOT contract_ok)                  AS contract_failures
       FROM verdicts12" >> "$OUT/verdicts12.txt" 2>&1
  t "SELECT /* wiki_btree_leg12_verdict_lost */
            num, idx, lost_by, wspf, actual, caveats
       FROM verdicts12 WHERE lost_by IS NOT NULL ORDER BY num" \
    >> "$OUT/verdicts12.txt" 2>&1
  t "SELECT /* wiki_btree_leg12_verdict_under_1mb */
            num, idx, blocks_before * 8 AS kib_before, wspf, actual,
            taken_stage, verdict
       FROM verdicts12 WHERE NOT over_1mb ORDER BY num" \
    >> "$OUT/verdicts12.txt" 2>&1
  t "SELECT /* wiki_btree_leg12_verdict_counts */
            verdict_floor, count(*) FROM verdicts12 GROUP BY 1 ORDER BY 2 DESC" \
    >> "$OUT/verdicts12.txt" 2>&1
  t "SELECT /* wiki_btree_leg12_gate_summary */
            equalimage, count(*), bool_or(dedup_applies) AS any_credited
       FROM verdicts12 GROUP BY 1" >> "$OUT/verdicts12.txt" 2>&1
  cat "$OUT/verdicts12.txt" >&2
}

# --------------------------------------------------------------- extstat -----
# What the portable inherited filter buys on this server, and what naming the
# column still costs here.  Two texts are rebuilt from the filed one:
#   est_pre   AND se.inherited = false, the text filed before 2026-09-10; it
#             must hash to BASEPRE and this server must refuse it
#   est_wide  est_pre with that line deleted, the old transformer output; here
#             it should agree with the filed text, because this server records
#             one ANALYZE pass and the filter it lost had nothing to remove
stage_extstat() {
  say "extstat: the portable filter, the text it replaced, and the widened one"
  [ -s "$SQLD/est_r2.sql" ] || die "no $SQLD/est_r2.sql; run the exact stage first"
  local line got
  : > "$SQLD/est_pre.sql"
  while IFS= read -r line; do
    case $line in
      "    -- The inherited flag is read through row_to_json()"*) continue ;;
      "    -- as a column, so one text also parses where"*)       continue ;;
      "    -- column: there the key is absent"*)                  continue ;;
      "    -- admits the row, which is the only ANALYZE pass"*)   continue ;;
      "                          AND coalesce((row_to_json(se)"*)
        printf '                          AND se.inherited = false\n' \
          >> "$SQLD/est_pre.sql"; continue ;;
      "                                       false) = false")    continue ;;
    esac
    printf '%s\n' "$line" >> "$SQLD/est_pre.sql"
  done < "$SQLD/est_r2.sql"
  got=$(sha256sum < "$SQLD/est_pre.sql" | cut -d' ' -f1)
  [ "$got" = "$BASEPRE" ] && note "est_pre matches BASEPRE" \
                          || note "est_pre DIFFERS from BASEPRE: $got"
  : > "$SQLD/est_wide.sql"
  while IFS= read -r line; do
    [ "$line" = "                          AND se.inherited = false" ] && continue
    printf '%s\n' "$line" >> "$SQLD/est_wide.sql"
  done < "$SQLD/est_pre.sql"

  { printf 'extstat_pre_hash=%s\n' "$got"
    if "$BIN/psql" -X -v ON_ERROR_STOP=1 -d "$DB" -f "$SQLD/est_pre.sql" \
         > "$OUT/v12_pre.txt" 2>&1; then
      printf 'pre_text=executes\n'
    else
      printf 'pre_text=refused\n'
      printf 'pre_text_note=expected: the pre-fix text is kept to prove the refusal the filed text removed\n'
      grep -E 'ERROR|LINE' "$OUT/v12_pre.txt" | head -2 \
        | while read -r line; do printf 'pre_error=%s\n' "$line"; done
    fi
    if "$BIN/psql" -X -v ON_ERROR_STOP=1 -d "$DB" -f "$SQLD/est_wide.sql" \
         > "$OUT/v12_wide.txt" 2>&1; then
      printf 'wide_text=executes\n'
    else
      printf 'wide_text=refused\n'
    fi
  } >> "$OUT/v12_facts.txt"
  harness_view "$SQLD/est_wide.sql" est_wide12 "$INTERNALS" > "$SQLD/view_wide12.sql"
  fl "$SQLD/view_wide12.sql" || die "widened harness view failed"

  # Disposable fixtures: the statements below drop and create tables,
  # statistics objects and indexes in the leg12 database of the sandbox
  # cluster.  They are not meant for a database anyone cares about.
  q "DROP TABLE IF EXISTS xchi, xpar, x2chi, x2par, x3chi, x3par, xflat,
                          xstat_res CASCADE"
  local p
  for p in x x2; do
    q "CREATE TABLE ${p}par(a int, b int, c int)"
    q "CREATE TABLE ${p}chi(a int, b int, c int) INHERITS (${p}par)"
    q "CREATE STATISTICS ${p}par_nd (ndistinct) ON a, b FROM ${p}par"
    q "INSERT INTO ${p}par SELECT i % 10, i % 20, i FROM generate_series(1, 300000) i"
    q "INSERT INTO ${p}chi SELECT i % 500, i % 700, i FROM generate_series(1, 300000) i"
    q "CREATE INDEX ${p}par_ab ON ${p}par (a, b)"
    loaded "${p}par" 300000
  done
  q "DELETE FROM x2par WHERE c % 5 < 3"
  maintain x2par extstat
  q "ANALYZE xpar";  analyzed xpar
  q "ANALYZE x2par"; analyzed x2par
  # The high-cardinality child: the shape whose inherited pass, on a server
  # that has one, moves the reading furthest.
  q "CREATE TABLE x3par(a int, b int, c int)"
  q "CREATE TABLE x3chi(a int, b int, c int) INHERITS (x3par)"
  q "CREATE STATISTICS x3par_nd (ndistinct) ON a, b FROM x3par"
  q "INSERT INTO x3par SELECT i % 10, i % 20, i FROM generate_series(1, 300000) i"
  q "INSERT INTO x3chi SELECT i, i, i FROM generate_series(1, 300000) i"
  q "CREATE INDEX x3par_ab ON x3par (a, b)"
  loaded x3par 300000; q "ANALYZE x3par"; analyzed x3par
  q "CREATE TABLE xflat(a int, b int, c int)"
  q "CREATE STATISTICS xflat_nd (ndistinct) ON a, b FROM xflat"
  q "INSERT INTO xflat SELECT i % 10, i % 20, i FROM generate_series(1, 300000) i"
  q "CREATE INDEX xflat_ab ON xflat (a, b)"
  loaded xflat 300000; q "ANALYZE xflat"; analyzed xflat

  fl /dev/stdin <<'SQL'
CREATE TABLE xstat_res(idx text, txt text, blocks int, wsp numeric,
                       wspf numeric, key_groups numeric, ext_used bool,
                       caveats text, actual numeric);
DO $x$
DECLARE ix text; v text; e record; sb bigint; sa bigint;
BEGIN
  FOREACH ix IN ARRAY ARRAY['xpar_ab','x2par_ab','x3par_ab','xflat_ab'] LOOP
    sb := pg_relation_size(ix::regclass);
    FOREACH v IN ARRAY ARRAY['est12','est_wide12'] LOOP
      EXECUTE format('SELECT wasted_space_pct AS wsp,
                             wasted_space_pct_floor AS wspf,
                             key_groups, ext_used, caveats
                        FROM %I WHERE indexname = %L', v, ix) INTO e;
      INSERT INTO xstat_res(idx, txt, blocks, wsp, wspf, key_groups,
                            ext_used, caveats)
        VALUES (ix, v, sb / 8192, e.wsp, e.wspf, e.key_groups, e.ext_used,
                e.caveats);
    END LOOP;
  END LOOP;
  FOREACH ix IN ARRAY ARRAY['xpar_ab','x2par_ab','x3par_ab','xflat_ab'] LOOP
    sb := pg_relation_size(ix::regclass);
    EXECUTE format('REINDEX INDEX %I', ix);
    sa := pg_relation_size(ix::regclass);
    UPDATE xstat_res SET actual = round(100.0 * (sb - sa) / greatest(sb, 1), 1)
     WHERE idx = ix;
  END LOOP;
END $x$;
SQL

  { printf 'rows_per_statistics_object\n'
    t "SELECT /* wiki_btree_leg12_extstat_passes */
              tablename, statistics_name, count(*) AS view_rows,
              max(((n_distinct::text)::json ->> '1, 2')::numeric) AS nd_whole_key
         FROM pg_stats_ext WHERE schemaname = 'public'
        GROUP BY 1, 2 ORDER BY 1"
    printf 'scored against a measured REINDEX INDEX\n'
    t "SELECT /* wiki_btree_leg12_extstat_scored */
              idx, txt, blocks, actual, wsp, wspf, key_groups, ext_used
         FROM xstat_res ORDER BY idx, txt"
    printf 'filed against widened, every projected column\n'
    t "SELECT /* wiki_btree_leg12_extstat_equivalence */
              (SELECT count(*) FROM (SELECT * FROM est12
                                     EXCEPT SELECT * FROM est_wide12) d)
                AS filed_minus_wide,
              (SELECT count(*) FROM (SELECT * FROM est_wide12
                                     EXCEPT SELECT * FROM est12) d)
                AS wide_minus_filed,
              (SELECT count(*) FROM est12) AS rows_read"
  } > "$OUT/extstat12.txt" 2>&1
  cat "$OUT/extstat12.txt" >&2
  # This stage issued one maintenance statement of its own, so the four proofs
  # are re-checked over every statement the run has made, including it.
  maint_proofs12
}

# Both errors this leg provokes are deliberate and each has a statement this
# script can name: the reloption probe that discovers deduplicate_items is
# unknown here, and the pre-fix text kept to prove the refusal the filed text
# removed.  The pairing, the mark and the record layout are the 17 leg's; see
# its comment.  The second fragment is the tag every estimator text on the
# page carries, so this message is allowed from any of them, including the
# current text should a revision name the column again, which the exact and
# transform stages record as a result rather than a failure; from any other
# statement it is counted.
EXPECTED_ERRORS=(
  'unrecognized parameter "deduplicate_items"'
  'column se.inherited does not exist'
)
EXPECTED_STATEMENTS=(
  'CREATE INDEX dedup_probe_i'
  'wiki_btree_wasted_space_sweep_r2'
)
UNEXPECTED_ERRORS=0
settle_pending() {                 # only from check_server_errors, on its locals
  case $stmt in
    *"${EXPECTED_STATEMENTS[$pending]}"*) seen[$pending]=$((seen[$pending] + 1)) ;;
    *) UNEXPECTED_ERRORS=$((UNEXPECTED_ERRORS + 1))
       printf '   unexpected: %s\n      its statement does not contain "%s"\n' \
              "$pend_line" "${EXPECTED_STATEMENTS[$pending]}" ;;
  esac
  pending=-1; collecting=0; stmt=''
}
check_server_errors() {            # check_server_errors <server log> <mark file>
  local log=$1 markf=$2 mark=0 n=0 line i tab
  local pending=-1 pend_line='' pend_prefix='' stmt='' collecting=0
  local -a seen
  UNEXPECTED_ERRORS=0
  [ -f "$log" ] || { printf '   no %s to read\n' "$log"; return 0; }
  [ -f "$markf" ] && mark=$(tr -d ' \n' < "$markf")
  tab=$(printf '\t')
  for i in "${!EXPECTED_ERRORS[@]}"; do seen[i]=0; done
  while IFS= read -r line; do
    n=$((n + 1)); [ "$n" -le "$mark" ] && continue
    if [ "$collecting" = 1 ]; then
      case $line in
        "$tab"*) stmt="$stmt"$'\n'"$line"; continue ;;   # the statement goes on
      esac
      settle_pending                                     # it ended on the line before
    fi
    case $line in
      *' ERROR:  '*|*' FATAL:  '*|*' PANIC:  '*)
        if [ "$pending" -ge 0 ]; then                    # never got its STATEMENT line
          UNEXPECTED_ERRORS=$((UNEXPECTED_ERRORS + 1))
          printf '   unexpected: %s\n      no STATEMENT line follows it\n' "$pend_line"
          pending=-1
        fi
        for i in "${!EXPECTED_ERRORS[@]}"; do
          case $line in *"${EXPECTED_ERRORS[i]}"*) pending=$i; break ;; esac
        done
        if [ "$pending" -ge 0 ]; then
          pend_line=$line
          pend_prefix=${line%% ERROR:  *}; pend_prefix=${pend_prefix%% FATAL:  *}
          pend_prefix=${pend_prefix%% PANIC:  *}
        else
          UNEXPECTED_ERRORS=$((UNEXPECTED_ERRORS + 1)); printf '   unexpected: %s\n' "$line"
        fi ;;
      "$pend_prefix STATEMENT:  "*)
        [ "$pending" -ge 0 ] && { stmt=${line#"$pend_prefix STATEMENT:  "}; collecting=1; } ;;
    esac
  done < "$log"
  if [ "$collecting" = 1 ]; then settle_pending
  elif [ "$pending" -ge 0 ]; then
    UNEXPECTED_ERRORS=$((UNEXPECTED_ERRORS + 1))
    printf '   unexpected: %s\n      no STATEMENT line follows it\n' "$pend_line"
  fi
  for i in "${!EXPECTED_ERRORS[@]}"; do
    printf '   allowed %s: "%s" from a statement containing "%s": seen %s\n' \
           "$((i + 1))" "${EXPECTED_ERRORS[i]}" "${EXPECTED_STATEMENTS[i]}" "${seen[i]}"
  done
  printf '   lines read: %s after mark %s\n' "$((n - mark))" "$mark"
  printf '   allowed=%s unexpected_server_errors=%s\n' \
         "${#EXPECTED_ERRORS[@]}" "$UNEXPECTED_ERRORS"
}

stage_report() {
  say "12.2 leg written to $OUT"
  [ -f "$OUT/v12_facts.txt" ] || die "no $OUT/v12_facts.txt; run the exact stage first"
  # Idempotent: drop the block an earlier report appended before appending this
  # one, so the file never carries a stale count above a live one.
  local line
  : > "$OUT/v12_facts.tmp"
  while IFS= read -r line; do
    [ "$line" = "server_errors" ] && break
    printf '%s\n' "$line" >> "$OUT/v12_facts.tmp"
  done < "$OUT/v12_facts.txt"
  mv "$OUT/v12_facts.tmp" "$OUT/v12_facts.txt"
  # What the filed text prints on this leg's settled database.  The exact stage
  # runs before a fixture exists, so its own count is 0 by construction; this
  # one is what a reader sees now that the 1 MB filter and the LIMIT 20 are
  # gone.  It goes to its own file, overwritten on every run, so report stays
  # idempotent.
  "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$DB" -f "$SQLD/est_r2.sql" \
    > "$OUT/v12_exact_settled.txt" 2>&1
  { printf 'settled_rows=%s\n' \
      "$(grep -E '^\([0-9]+ rows?\)$' "$OUT/v12_exact_settled.txt" | tail -1)"
    printf 'settled_report_shape=%s\n' \
      "$(s "select /* wiki_btree_leg12_report_shape */
                   count(*) || ' reported rows, ' ||
                   count(*) filter (where actual_bytes <= 1024 * 1024) ||
                   ' of them 1 MB or smaller'
              from est12 where not suppress_row")"
    printf 'accuracy=%s\n' \
      "$(s "select /* wiki_btree_leg12_accuracy */
                   count(*) filter (where wspf is not null
                                      and abs(wspf - actual) <= 1)
                     || ' of ' || count(*) || ' within one point, worst over ' ||
                   round(max(wspf - actual), 1) || ', worst under ' ||
                   round(min(wspf - actual), 1)
              from verdicts12")"
    # What the decisions were worth here, read after the oracle pass.
    printf 'decisions=%s\n' \
      "$(s "select /* wiki_btree_leg12_decisions */
                   string_agg(taken_stage || '=' || n ||
                              ' mean ' || mean || ' (' || lo || ' to ' || hi || ')',
                              '; ' order by taken_stage)
              from (select taken_stage, count(*) AS n,
                           round(avg(actual), 1) AS mean,
                           min(actual) AS lo, max(actual) AS hi
                      from verdicts12 group by 1) d")"
    # The no-defeat proofs, per fixture rather than per statement, so a reader
    # sees each verdict beside the state it was taken in.
    printf 'maintenance=%s\n' \
      "$(s "select /* wiki_btree_leg12_maintenance */
                   count(*) || ' fixtures, ' ||
                   count(*) filter (where maintained) || ' maintained, ' ||
                   count(*) filter (where maintained and dead_not_removable = 0)
                     || ' at dead-not-removable 0, ' ||
                   coalesce(sum(deleted_pages), 0) || ' deleted index pages'
              from verdicts12")"
  } > "$OUT/v12_rows.txt"
  t "SELECT /* wiki_btree_leg12_maintenance_rows */
            num, idx, tbl, maintained, maint_source, maint_removed,
            dead_not_removable, dead_after, mods_after, deleted_pages,
            empty_pages, density_after_maint
       FROM verdicts12 ORDER BY num" >> "$OUT/v12_rows.txt" 2>&1
  cat "$OUT/v12_rows.txt" >&2
  { printf 'server_errors\n'
    check_server_errors "$OUT/server12.log" "$OUT/server12.log.mark"; } >> "$OUT/v12_facts.txt" 2>&1
  cat "$OUT/v12_facts.txt" >&2
  [ "$UNEXPECTED_ERRORS" -eq 0 ] \
    || die "$UNEXPECTED_ERRORS unexpected server error(s); see the end of $OUT/v12_facts.txt"
}

# Clean stop, confirmed, as in the 17 leg: -m fast rather than the -m immediate
# this stage used until 2026-09-10, then no postmaster.pid, no postgres process
# on the data directory and an empty socket directory, or the stage dies.
stage_stop() {
  say "stop the 12.2 server cleanly"
  [ -x "$BIN/pg_ctl" ] || { note "no server binary under $BIN, nothing to stop"; return 0; }
  if [ -s "$DATA/postmaster.pid" ] && "$BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -m fast -w stop > /dev/null 2>&1 || die "pg_ctl -m fast stop failed"
    tail -3 "$OUT/server12.log" 2>/dev/null | grep -q 'database system is shut down' \
      && note "server12.log: database system is shut down"
  else
    note "not running"
  fi
  [ -e "$DATA/postmaster.pid" ] && die "$DATA/postmaster.pid still exists"
  if command -v pgrep > /dev/null 2>&1 && pgrep -f -- "-D $DATA" > /dev/null 2>&1; then
    die "a postgres process still runs on $DATA"
  fi
  [ -z "$(ls -A "$SOCK" 2>/dev/null)" ] || die "socket directory $SOCK is not empty"
  note "confirmed: no postmaster.pid, no postgres process on $DATA, socket directory empty"
}

# Containment check before any rm -rf, as in the 17 leg.  This stage removes
# only this leg's four directories: out/ and sql/ belong to the 17 leg, whose
# own clean stage deletes the whole sandbox.
inside_tmp() {
  case ${1%/} in
    "$WIKI_ROOT/.wiki-runtime/tmp"/?*) return 0 ;;
    *) return 1 ;;
  esac
}
stage_clean() {
  stage_stop
  local d
  for d in "$BUILD" "$INST" "$DATA" "$SOCK"; do
    inside_tmp "$d" || die "refusing to delete $d outside $WIKI_ROOT/.wiki-runtime/tmp/"
  done
  rm -rf "$BUILD" "$INST" "$DATA" "$SOCK"
  say "12.2 build, install, data and socket directories deleted; out/ and sql/ kept"
}

main() {
  local stages=("$@")
  [ ${#stages[@]} -eq 0 ] && stages=(build check cluster exact transform facts \
                                     fixtures churn score extstat report)
  local st
  for st in "${stages[@]}"; do
    case $st in
      build|check|cluster|exact|transform|facts|fixtures|churn|score|extstat|report|stop|clean)
        "stage_$st" ;;
      *) die "unknown stage: $st" ;;
    esac
  done
}

main "$@"
```

### Reading the results of a run

**Open `out/criteria.txt` first: it is the whole verdict on one screen, and
every other file exists to explain one of its numbers.** A run writes its output
under `$SANDBOX/out`, one or more files per stage, and leaves its result tables
in the databases so they can be queried directly.

| File | Holds |
|---|---|
| `criteria.txt` | the blocks, in order: the gate counters; the shared suite's four bands and phase counters for both databases, with the under-1 MB counts, the accuracy summary, the `lost_by` and `withheld_by` breakdowns, the three worst under-reads and what each decision was worth; the older bands on the same rows as block 2b; every row whose modelled row count is zero; the size of the `EXCEPT` output; the exact-text runs; the build and hash checks; and the server-error check |
| `hashes.txt` | the three text hashes against their baselines. A `DIFFER` line means the page changed and every number below it is about a different statement |
| `checks.txt`, `checks12.txt` | `make check` and the three contrib suites, per leg |
| `configure*.log`, `make*.log`, `install*.log`, `check*_*.log`, `diffs*_*.txt` | the build and regression diagnostics, copied out of the build tree so they outlive it. A `12` in the name marks the 12 leg. `diffs*` exist only when a suite failed |
| `platform.txt` | `uname -sm`, `max_data_alignment` and `database_block_size`, which every geometry constant in the statement assumes |
| `gate.txt` | one row per gate fixture with `equalimage`, the metapage, whether credit was given and whether posting lists were written, then the counters and the two `DEBUG1` tallies |
| `gate_pattern.txt` | the `text_pattern_ops` refusal of a nondeterministic collation, under a header saying which outcome was expected |
| `verdicts.txt`, `verdicts_gate.txt` | every scored fixture of the numbered suite and of family 1, then the shared bands per family, the totals, the `expected_stage`/`want_stage` agreement counts, one row per `lost_by` loss, one row per missed prediction, and the older `verdict_floor`/`verdict_point` counts last |
| `drain.txt`, `census.txt`, `census_gate.txt`, `forge.txt`, `snapshots.txt` | the churn phase: what rule 2 drained, what rule 3's census analyzed and what it left alone with the boundary percentages, the forged count after the census, and the baseline and churned snapshot counts |
| `drain12.txt`, `census12.txt`, `snapshots12.txt` | the same three for the 12 leg |
| `maint_proofs.txt`, `maint_proofs12.txt` | the four no-defeat proofs per database: how many maintenance statements ran and completed, their sources, the worst `dead but not yet removable` count, the dead tuples left behind, the tuples removed, how many horizon probes were clean, the timeout sets in force, and the skip-line count |
| `maint_skips.txt`, `maint_skips12.txt` | every skip or cancellation line the server log carries after this run's mark. **Empty is the passing state**; a non-empty file killed the run |
| `pageclass_suite.txt`, `pageclass_gate.txt`, `pageclass12.txt` | what the maintenance left in every planned index: leaf, empty and deleted pages, `avg_leaf_density` and the index size |
| `suite_verbose.log`, `drain_verbose.log`, `drain_gate_verbose.log`, `extstat_verbose.log`, `maint_verbose12.log` | the raw `VACUUM (VERBOSE, ANALYZE)` output the proof parse reads |
| `attribution.txt` | the `EXCEPT` output in both directions, taken before the first rebuild |
| `probes_gen_*.txt`, `probes_*.txt` | the probe statements the generator emitted, and the answer each returned |
| `cost.txt` | six interleaved timings of the two exact texts, the size of the database they ran against, the row count each printed on it, and that row set split on the 1 MB boundary the removed predicate tested |
| `exact_rows.txt`, `exact_*_suite.txt`, `exact_*_settled.txt` | the row counts both exact texts printed, and their full output: once on the empty database at `texts`, once on the settled one at `cost`. The pair is the reader-visible effect of the 2026-09-14 filter removal |
| `v12_facts.txt`, `v12_exact.txt`, `v12_rows.txt`, `verdicts12.txt` | the 12 leg: the discovered facts, the verbatim parse outcome, the settled report shape with its accuracy and decision summaries, and the scored subset |
| `server.log`, `server12.log`, `gate_build.log` | server output, including the build's own `DEBUG1` deduplication verdicts |
| `server.log.mark`, `server12.log.mark` | the line count of the matching log when `cluster` last started that server; the server-error check reads only the lines after it |

The tables, and the 12 leg's `verdicts12` view, stay queryable after the run,
and each one keys its rows differently, which is worth knowing before writing
a `WHERE` clause:

| Table or view | Database | Keyed by |
|---|---|---|
| `verdicts`, `res` | `suite` | `num`, `leg`, `idx` |
| `gate_res` | `gate` | `indexname` |
| `autoanl`, `autoanl_after` | `suite` and `gate` | `tbl` |
| `xstat_res` | `xstat` | `idx`, `txt` |
| `verdicts12` | `leg12` | `num`, `idx` |

#### One scored row, column by column

Every fixture of the numbered suite produces one `verdicts` row. Read it in
this order.

| Column | What it is |
|---|---|
| `blocks_before`, `blocks_after` | the index's size in blocks before and after the scoring pass rebuilt it. `pg_relation_size` measures the main fork only. [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L346-L371) |
| `actual` | **the truth column**: `100 * (before - after) / before`, the reclaim a real `REINDEX INDEX` produced. Everything else is scored against it. [indexcmds.c#ReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2804-L2829), [index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3583-L3597) |
| `wsp`, `wspf` | what the statement said: the point estimate and the floor, read *before* the rebuild. [Reading the output](#reading-the-output) |
| `old_wsp`, `old_wspf` | the same two numbers from the superseded text, for side-by-side comparison |
| `reported` | false when an exclusion term withheld the row, so the report a reader runs would never show it |
| `withheld_by` | which term did it: `A` for a missing statistics row or duplicates taken from table statistics, `B` for a table changed since its `ANALYZE`, `C` for a variable-width `INCLUDE`, `D` for a non-partial expression index with no statistics row. `unexplained` means the row is withheld by a term this harness does not know about, which is a defect in one of the two |
| `alertable` | whether this page's own reading rule would let the row become a rebuild decision: true unless `caveats` contains `never analyzed`, `row-count sources disagree`, `statistics not visible`, `zero modelled rows` or `wide compressible key` |
| `over_1mb` | **an observation, not a term**: whether the index was larger than 1 MB before the rebuild. The statement's own predicate on that size came out on 2026-09-14, so nothing in `taken_stage`, `taken_point` or `expected_stage` reads this column; it is here so a run can count what the old report would have withheld |
| `contract_ok` | whether the fixture built what it intended. False is a **harness** fault, not an estimator result: the row's numbers describe a different fixture from the one the requirement names |
| `verdict_point`, `verdict_floor` | the classification below, computed once per column |
| `caveats`, `equalimage`, `modelled_rows`, `idx_reltuples`, `tids` | the statement's own explanation of the reading |

#### The five verdicts

Both verdict columns use the same rule, one on `wsp` and one on `wspf`:

| Verdict | Condition | What it means |
|---|---|---|
| `PASS` | none of the below | the estimate and the measured reclaim agree closely enough to act on |
| `CRITICAL FALSE POSITIVE` | estimate >= 50 and `actual` < 10 | the statement called for a rebuild that would have reclaimed nothing. This is the failure that matters operationally |
| `FALSE POSITIVE` | estimate >= 50 and `actual` < 45, or estimate exceeds `actual` by more than 5 points | the statement over-stated a real saving |
| `FALSE NEGATIVE` | estimate < 45 and `actual` >= 50 | the statement hid a rebuild worth doing |
| `UNMEASURED` | the estimate is NULL | the statement declined to model the index, which happens when `pg_class.reltuples` holds the `-1` sentinel a new relfilenode leaves. No fixture reached that state on 2026-09-16 either, because the three recipes that did were retired with number 121. [relcache.c#RelationSetNewRelfilenumber-reltuples](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3951-L3952), [index.c#index_update_stats-sentinel](../../../../raw/postgres-17/src/backend/catalog/index.c#L2835-L2836) |

A verdict is only as interesting as `reported` and `alertable` make it. A
critical false positive that is withheld costs a reader nothing; the same
verdict on a row that is both reported and alertable is a defect the statement
owes a fix for. That three-way reading — verdict, `reported`, `alertable` — is
the one this page scores itself on.

#### What a clean run looks like

| Check | Clean value |
|---|---|
| `hashes.txt` | three `match` lines |
| `checks.txt` | four `=0` lines, `All 225` on the core suite |
| Exact texts | four files under `out/exact_*`, none containing `ERROR`, and `cost.txt` showing the current text printing more rows than the superseded one on the settled database |
| Report shape | `criteria.txt` block 2 reports a non-zero `under_1mb`, so the run exercised the 2026-09-14 removal at all |
| Gate | `over_credit` 0, `metapage_disagreements` 0, `worst_reading` under 30 |
| Numbered suite | `withheld_unexplained` 0, `contract_failures` 0, `gate_disagrees` 0 |
| Census | every churned table at zero modified rows, so rule 3 analyzes only tables no churn touched. On the 12 leg that now means it analyzes none |
| No-defeat proofs | `maint_proofs.txt` and `maint_proofs12.txt` read `dead but not yet removable  max 0`, `dead tuples left behind max 0`, `horizon probes clean N of N`, one timeout set of zeros and `skip or cancellation lines 0`; `maint_skips*.txt` are empty. Any other value stops the run in the churn stage |
| Probes | one line per emitted probe, and `false` on every subset the fixture drained, `true` on every subset it refilled |
| Attribution | every `EXCEPT` row explainable by one of the five documented changes; an unexplained row is a regression |
| 12 leg | `transformed_text=executes`, and `transform_edits` no larger than the page documents |
| Server errors | block 7 of `criteria.txt` reads `unexpected_server_errors=0`, and the same line closes `v12_facts.txt` on the 12 leg; on a full run the 17 leg's one allowed pair and the 12 leg's two each read `seen 1`. Each leg allows exactly the errors it provokes on purpose, each only from the statement that provokes it, and dies on anything else, so a stray error can no longer hide among them. The check reads the log from the mark `cluster` wrote when it started the server, so a stray error is cleared by `stop cluster`, not by a bare re-run of `criteria` or `report` |

Three things that look like failures and are not. A **withheld** row is the
exclusion terms working, not a miss. A **negative** percentage is
over-prediction — the model expects the rebuild to be *larger* than the file,
which is conservative and never triggers an alert. And a **zero** `actual` on a
family 3 fixture is the point of that fixture, not a null result.

#### When something goes wrong

| Symptom | Where to look, and what it means |
|---|---|
| A stage dies with `!!` | the message names the stage. `configure`/`make` failures land in `build17/configure.log` and `build17/make.log`; a server that will not start lands in `out/server.log` |
| `DIFFER` in `hashes.txt` | the page's SQL changed since the baselines were recorded. Re-baseline deliberately; do not compare the run against older numbers |
| `estimator returned no row for X` | the scoring procedure could not find the index in the harness view. The view was not installed, or the fixture did not create the index |
| `contract_ok` false | the fixture, not the statement. Fix the recipe or the intended count before reading its verdict |
| `withheld_by = unexplained` | the statement withheld a row for a reason the harness cannot name — either a new exclusion term or a stale harness |
| A verdict that moves between runs | check `modelled_rows` first. Fixture 120 is known to flip with the `ANALYZE` sample, and 41 and 45 sit on the deduplication-credit boundary the same way; see [Fixture verdicts that depend on the ANALYZE sample](#fixture-verdicts-that-depend-on-the-analyze-sample) |
| `the maintenance was defeated` | a maintenance statement left dead tuples the horizon still covered. Read the table the message prints, then `maint_proofs.txt` and `horizon`: something held a snapshot, a slot or a prepared transaction while the fixtures ran. The rule's answer is to repair the fixture and re-run, never to score it |
| Caveats appearing on fresh fixtures | a statistics-publication ordering fault, not an estimator one: a reading taken inside the transaction that built the fixture sees the table's statistics as they were before its own `ANALYZE`. [pgstat.c#pgstat_force_next_flush](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L700-L708), [pgstat_relation.c#pgstat_report_analyze](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L289-L337) |
| The 12 leg refuses a construct the transformer does not handle | `stage_transform` stops and says so. Add the refused construct as one more documented edit; the count in `v12_facts.txt` is the honest measure of how far the text is from portable |

Two files the table above does not cover, both written by the `extstat` stages:
`out/extstat.txt` holds the 17 leg's text hashes, the per-database equivalence
counts, the two `ANALYZE` passes of each fixture, the three-text scorecard and
the timing pairs; `out/extstat12.txt` holds the 12 leg's rows per statistics
object, its two-text scorecard and its equivalence count. `out/v12_facts.txt`
gains `pre_text=`, `pre_text_note=` and `wide_text=` lines from the same stage;
the note is there because `pre_text=refused` is the expected result and reads
like a failure without it.

### What the no-defeat re-run measured

This is that reading applied to the run this revision files, the first to score
the statement with every maintenance statement proved against
`### The maintenance must not be defeated`. Every number below is in
[The mandatory suite, re-scored under the shared protocol](#the-mandatory-suite-re-scored-under-the-shared-protocol)
or [The maintenance, proved not defeated](#the-maintenance-proved-not-defeated),
and this section is the reader's index into the files behind them. It replaces
the run report of the 2026-09-14 filter removal, whose fixture set this run
re-used unchanged.

| Fact | Value |
|---|---|
| Date | 2026-09-16, the first run under the no-defeat rule. Both servers were built concurrently at `JOBS=10`, then each leg ran once, end to end, on a freshly `initdb`'d cluster |
| Host | `Linux x86_64`, Ubuntu 24.04, gcc 13.3.0, ICU 74.2, 22 cores, recorded into `out/platform.txt` with `max_data_alignment` 8 and `database_block_size` 8192 |
| 17 leg | 17.11 built from `786db8dcf168bd9df8f55047337525ac19118b1c` with `--enable-debug --with-icu --with-readline --with-zlib`; `make check` **All 225**, plus `pageinspect` 8, `pgstattuple` 1 and `amcheck` 3, every stage `=0` |
| 12 leg | 12.2 (`server_version_num` 120002) built from `45b88269a353ad93744772791feb6d01bc7e1e42` with the same flags plus `CFLAGS="-O2 -g -DTRUE=1 -DFALSE=0"`; `make check` **All 192**, plus 5, 1 and 2 |
| Cluster | `initdb --locale=C --encoding=UTF8`, `autovacuum = off`, `fsync = off`, `shared_buffers = 512MB`, `maintenance_work_mem = 256MB`, `max_parallel_maintenance_workers = 0`, ports 55437 and 55412 |
| Statement text | `sql` block 1, 466 lines, SHA-256 `4de245c5a1fb442cda800c099b8801bc72abc0c87f170384490079135fb5241d`, unchanged by this pass and executed unmodified on both servers |
| Other texts checked | the probe generator `bfa7721f…`, the superseded text from `f2d73b4` `bffd166e…`, and the reconstructed pre-2026-09-10 text `152f4172…`, which the 12 leg rebuilt and that server still refuses |
| Citations | all **717** links on the page re-read against the pin: 238 distinct ranges over 88 files, every one in bounds and supporting its label |
| Rows the filed text printed | **68** on the settled 17.11 `suite` database, 45 of them 1 MB or smaller, against **20** from the superseded text; **19** on `leg12`, 6 of them 1 MB or smaller - identical to 2026-09-14 on both legs |
| Gate | 25 fixtures, 25 `PASS`, `over_credit` 0, `metapage_disagreements` 0, `under_credits` 2, `worst_reading` 28.8, `DEBUG1` 13 safe and 13 unsafe |
| Numbered suite | 101 fixtures: **72 `PASS`, 4 `CRITICAL FALSE POSITIVE`, 0 `FALSE POSITIVE`, 25 `FALSE NEGATIVE`**; the statement called for 47 rebuilds, which repaid a mean 80.4 %; 12.2: 13 fixtures, 11 `PASS`, 2 `FALSE NEGATIVE`, 9 rebuilds at a mean 89.9 % |
| The one fixture that moved | `p41`, printed and decided `rebuild` on this run where 2026-09-14 withheld it; 74.4 % read against 75.2 % measured, and the same in both of this pass's 17 runs |
| No-defeat proofs | 17.11: **68 maintenance statements** (65 `suite`, 2 `gate`, 1 `xstat`), all completed, `dead but not yet removable` **0 on every one**, `n_dead_tup` 0 afterwards, **76 of 76** horizon probes clean, **0** skip or cancellation lines, one timeout set of four zeros, 21,557,908 + 899,900 + 180,000 tuples removed. 12.2: **9 statements**, all completed, **0** on every one, **11 of 11** probes clean, three zeros, 3,568,887 tuples removed |
| Page classes after the maintenance | `suite` 101 indexes, 28 with deleted pages, 0 half-dead, **9,626** deleted pages; `gate` 25 and **714**; `leg12` 13 indexes, 5 with deleted pages, **15,794** |
| `contract_failures`, `gate_disagrees`, `withheld_unexplained` | 0, 0, 0 on both legs |
| Census | 86 censused, 2 analyzed, 84 at zero modified rows; **9 censused and 0 analyzed** on the 12 leg, where the repaired publication order now leaves nothing for it to do |
| Probes | 63 emitted and executed, 62 group and 1 population (`p113b` -> `false`) |
| Attribution | **26 rows in each direction**, taken before the first rebuild |
| `extstat` | 0 rows in both directions in all three databases, 139 rows read; on the 12 leg the filed and widened texts are identical over 20 rows and the pre-fix text is refused at line 116 |
| Cost | the filed text 77.1 to 97.6 ms over six interleaved pairs, the superseded one 52.1 to 63.4 ms, on 317 B-tree indexes over 64,103 blocks |
| Server errors | `unexpected_server_errors=0` on both legs, the 17 leg's one allowed pair and the 12 leg's two each `seen 1` |
| Stages run | the full default order on each leg: `build check cluster texts gate suite churn extstat attribution probes score cost criteria report` and `build check cluster exact transform facts fixtures churn score extstat report`. The 17 leg ran twice under the final script text, once on the cluster the repairs were developed against and once from a fresh `initdb`; the filed numbers are the fresh run's |
| Runtime | about 1 min 45 s per build, concurrent; then 2 min 20 s for the 17 leg's full run from a built tree, 50 s of it `make check`, and 1 min 10 s for the 12 leg, 35 s of it `make check`, read from the output files' modification times |
| Teardown | both servers stopped with `pg_ctl -m fast -w stop` by the scripts' own `stop` stages, each confirming no `postmaster.pid`, no postgres process on its data directory and an empty socket directory, with `pgrep -a postgres` empty afterwards; the sandbox was then deleted |

The things worth opening a file for, in this run: `out/criteria.txt` block 2 for
the bands, the accuracy line and the `lost_by` classes and block 8 for the four
proofs, `out/maint_proofs.txt` and `out/maint_proofs12.txt` for the proofs on
their own, `out/pageclass_suite.txt` and `out/pageclass12.txt` for what the
maintenance left in each index, `out/verdicts.txt` for the 25 `lost_by` rows,
the 32 missed predictions, the 31 under-1 MB rows and the per-fixture
maintenance detail, `out/cost.txt` for the report shape, and
`out/extstat.txt` for the three-text scorecard on the inheritance parents.

## Context Reviewed

- PostgreSQL 17 pin `786db8dcf168bd9df8f55047337525ac19118b1c`; the source checkout is read-only and was never written to.
- The revised statement's catalog inputs, CTE dependencies, formulas, output projection, exclusions and timeout settings, and the superseded statement extracted from the previous revision of this page for the side-by-side runs.
- The sorted-build caller/callee path and its page arithmetic (`nbtsort.c`, `nbtdedup.c`, `bufpage.c`, `nbtree.h`), tuple formation and varlena header handling (`indextuple.c`, `heaptuple.c`, `varatt.h`, `heaptoast.h`, `htup_details.h`), index attribute construction (`index.c`), expression-statistics selection and the two ANALYZE passes (`analyze.c`), statistics visibility and privilege resolution (`system_views.sql`, `acl.c`, `aclchk.c`), cumulative-statistics flush ordering (`postgres.c`, `pgstat.c`, `pgstat_relation.c`), split strategies (`nbtsplitloc.c`), size formatting and numeric range errors (`dbsize.c`, `numeric.c`), and the generated catalog/function boundary.
- Plan review on 2026-09-07, same pin, retained above.
- Implementation and measurement run on 2026-09-08, same pin: 17.11 built out of tree under `.wiki-runtime/tmp/btree17/` (`--without-readline --without-zlib --without-icu`), an isolated cluster on port 55437 with `autovacuum = off`, `fsync = off`, `shared_buffers = 256MB` and `--locale=C`; `make check` 225 of 225 tests passed, `contrib/pageinspect` and `contrib/pgstattuple` checks passed; six fixture databases covering page geometry, fresh sorted builds, the three deterministic defects, the equal-image matrix, posting-list tails, validation probes and the insertion-pattern calibration. `pageinspect` and `pgstattuple` were installed in the disposable cluster only. The sandbox was deleted after filing, so reproducing any number means rebuilding from the pin and re-running the published SQL.
- Mandatory test review on 2026-09-09, same pin, no server built or started: the revisions of this page before the 2026-09-07 cleanup (`33fe5a4`, `f8265ad`) and before the 2026-09-08 rewrite (`f2d73b4`) for the suite's requirement tables, harnesses and fixture recipes; the log entries of 2026-08-18, 2026-08-19, 2026-08-20, 2026-08-24 and 2026-09-08 for each run's provenance; the four fenced blocks on this page hashed against their recorded baselines, and the superseded block recovered from `f2d73b4` and hashed against `bffd166e…`; the installation and regression documentation for VPATH builds, ICU, block size, `make check` and contrib suites; the GUC contexts of every cluster setting the protocol names; and the equal-image, concurrent-build, parallel-build, partition-expansion, statistics-sample and `reltuples`-sentinel paths cited in the review.
- Full re-verification on 2026-09-09, same pin: every source citation on this page re-read against `raw/postgres-17/` (476 links over 68 files, 164 distinct ranges, all resolving and all supporting their labels), every `## Contents` entry and page-internal anchor re-checked, and every measured claim re-run on a second isolated server. 17.11 was built out of tree under `.wiki-runtime/tmp/btreerev/` with `--with-icu --enable-debug --with-readline --with-zlib`; `make check` passed 225 of 225 and the `pageinspect`, `pgstattuple` and `amcheck` checks passed 8, 1 and 3; the cluster ran `--locale=C`, `autovacuum = off`, `fsync = off`, `shared_buffers = 512MB`, `maintenance_work_mem = 256MB`, `max_parallel_maintenance_workers = 0` at the default `BLCKSZ`, with eleven fixture databases covering page geometry, fresh sorted builds, the three deterministic defects read as two roles, the equal-image matrix, posting tails, the statistics barrier, the probes, in-index compression, the 27-fixture deduplication gate and the ICU collation cases. Both statement texts were extracted and hashed before use. `raw/postgres-17/` was never written to and stayed clean at the pin; the build and cluster were deleted after filing, leaving only the fixture scripts under `.wiki-runtime/tmp/btree-rev-harness/`.

- Measurement-script section review on 2026-09-09, same pin, read-only with no server built or started: `AGENTS.md`'s `MANDATORY Measurement Script`, `MANDATORY Production SQL`, `MANDATORY GUC Changes`, `MANDATORY Table of Contents` and `MANDATORY Citations` rules against this section as filed; both script bodies re-extracted from this page with their own `md_block` logic and parsed with `bash -n` (1,793 and 474 lines); the four `sql` blocks and the superseded text from revision `f2d73b4` re-hashed against all five baselines; the 37 source citations inside the section re-read against `raw/postgres-17/`, including the seven whose label token is not literally inside the range; `psql`'s exit-status handling for `-c` and `-f` actions (`startup.c`, `mainloop.c`, `psql-ref.sgml`); the GUC definitions of `listen_addresses`, `port` and `logging_collector`; and the containment guard tested against nine paths, including `/`, `$HOME`, the repository root, the `tmp` directory itself and a `tmpx` lookalike. Both pinned checkouts were clean at their pins throughout, and no sandbox, cluster or build was created.

- Suite-script run on 2026-09-09, same pin, both legs built and executed: 17.11 out of tree under `.wiki-runtime/tmp/btree-suite/build17` (`--enable-debug --with-icu --with-readline --with-zlib`), `make check` All 225 tests plus 8, 1 and 3 for `pageinspect`, `pgstattuple` and `amcheck`; a cluster at `--locale=C`, `autovacuum = off`, `fsync = off`, `shared_buffers = 512MB`, `maintenance_work_mem = 256MB`, `max_parallel_maintenance_workers = 0`, default `BLCKSZ`, with five UTF8 databases for geometry, calibration, the deduplication gate, the acceptance fixtures and the 112-fixture numbered suite. 12.2 was built out of tree from this repository's pinned 12 checkout the same way, needing `-DTRUE=1 -DFALSE=0` for this host's ICU headers, and passed All 192 core tests plus 5, 1 and 2. Both checkouts stayed read-only and clean at their pins; the two scripts, their SQL and their output lived under the git-ignored `.wiki-runtime/tmp/btree-suite/`, deleted on 2026-09-10. The estimator, probe-generator, geometry and calibration blocks were re-extracted from this page after the edit that added the two script blocks, and all four still hash to their baselines, together with the superseded text from revision `f2d73b4`.

- Full re-run of both suite scripts on 2026-09-10, same pins, on a second platform: the postmaster's fast and immediate shutdown paths, the checkpointer's shutdown checkpoint, the recovery decision at the next start, `pg_ctl`'s `stop`, `status` and `start` command construction, lock-file and socket-file removal (`postmaster.c`, `checkpointer.c`, `xlog.c`, `xlogrecovery.c`, `pg_ctl.c`, `miscinit.c`, `pqcomm.c`, `pg_ctl-ref.sgml`), and the installation notes on ICU flags and macOS System Integrity Protection. Both `stop` stages were rewritten from `pg_ctl -m immediate` to `-m fast -w` with a confirmed teardown, the 12 leg's database-existence check was pointed at `postgres`, and the 17 leg's `extstat` stage was moved after `suite`; both scripts were re-extracted from this page with their own `md_block` logic, parsed with `bash -n` (2,062 and 681 lines), and diffed against the previous extraction so that only those hunks changed. Each leg was then built from scratch and run end to end twice under `.wiki-runtime/tmp/btree-suite/` on Darwin arm64 (macOS 26.6.2, Apple clang 21.0.0, ICU 78.3 via `ICU_CFLAGS`/`ICU_LIBS`, `JOBS=8`): `make check` All 225 plus 8, 1 and 3 on 17.11 and All 192 plus 5, 1 and 2 on 12.2, all five text hashes matching, and every verdict count of the Linux run reproduced. Both servers were stopped by the repaired `stop` stages, the 8.4 GB sandbox was deleted, and both checkouts stayed read-only and clean at their pins; 1.8 MB of script copies, run logs and output text was kept under `.wiki-runtime/tmp/btree-suite-scripts/`, which later runs grew to 8.8 MB and which was deleted on 2026-09-17 when `.wiki-runtime` was purged to the venv. Nothing in it was a cluster or a data directory, and the scripts it held are published in full under `## Measurement Script` on this page.

- Portable extended-statistics filter, filed and measured on 2026-09-10, same pin: the `pg_stats_ext` and `pg_stats` view definitions and the `pg_statistic_ext_data` grant boundary (`system_views.sql`); the `stxdinherit` catalog column and its place in the data row's unique key (`pg_statistic_ext_data.h`); the two `ANALYZE` passes and the `inh` flag each one stores (`analyze.c`, `extended_stats.c`); and the whole `row_to_json` -> `->>` -> `boolean` chain, including what a missing key returns (`pg_proc.dat`, `pg_operator.dat`, `json.c`, `jsonfuncs.c`, `bool.c`). Both scripts were edited in place — one new `extstat` stage each, a new `BASEPRE` baseline, `BASE1` re-baselined to `646df923…`, an idempotent `cluster` stage, and a sixth database `xstat` — re-extracted from this page, parsed with `bash -n` (2,036 and 658 lines; this entry first recorded 2,004 and 648, corrected on 2026-09-10 by re-extracting both blocks), and run against the 17.11 and 12.2 clusters the 2026-09-09 run left in place under `.wiki-runtime/tmp/btree-suite/`: the 17 leg's `cluster texts extstat` and the 12 leg's `exact transform facts fixtures score extstat report`. Neither server was rebuilt, neither regression suite was re-run, both checkouts stayed read-only at their pins, and the sandbox was left in place for that pass, then stopped and deleted on 2026-09-10. The reconstruction of the previous statement text reproduced its filed SHA-256 exactly, which is what makes the one-line diff auditable.

- Script-change review on 2026-09-10, same pins, both legs built and run end to end under the script text of commit `641e966`: the error-emission path and what a logged line carries (`elog.c`: `errfinish`, `EmitErrorReport`, `check_log_of_query`, `errhidestmt`, `error_severity`, the `STATEMENT:` writer and the `EVALUATE_MESSAGE` translation macro), the backend's top-level `sigsetjmp` handler (`postgres.c`), the PL/pgSQL exception catch (`pl_exec.c`), the `log_min_error_statement`, `log_line_prefix` and `log_min_messages` definitions (`guc_tables.c`), `pg_ctl`'s log redirection and its start wait on the `postmaster.pid` status line (`pg_ctl.c`), the startup-time connection refusal (`backend_startup.c`), the administrator-command `FATAL` (`postgres.c`) and `initdb`'s `lc_messages` default and write (`initdb.c`); the commit's diff hunk by hunk against the scripts as filed, the nine result tables' `CREATE` statements against the new key-column table, and the stage dispatcher against the usage table; the two scripts re-extracted with `md_block`, parsed with `bash -n` and run six times, two full runs, two restart runs and two stray-error runs, then both `clean` stages.

- Script repairs on 2026-09-10, same pins, no server built or started: the per-report timestamp capture and the `%m`/`%p` prefix, and the record layout that writes the `STATEMENT:` line last and indents its continuation lines with a tab (`elog.c`: `EmitErrorReport`, `get_formatted_log_time`, `log_line_prefix`, `send_message_to_server_log`, `append_with_tabs`); the six repaired hunks of both scripts, re-extracted with `md_block`, parsed with `bash -n` and diffed against the commit's text; the repaired check function exercised nine times against the saved logs of the review run.

- Re-score against the shared mandatory suite on 2026-09-11, same pins, both legs built and run end to end: the concept page [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md) for the families, the five phases, the three porting rules, the oracle and the four bands, and this page's own reading rule for the decision the bands score; the engine paths each rule leans on, re-read against `raw/postgres-17/` — the autovacuum analyze threshold and its two GUCs (`autovacuum.c`, `guc_tables.c`), `n_mod_since_analyze` and its reset (`system_views.sql`, `pgstat_relation.c`), the item-pointer block id and the self item pointer the drain selects on (`itemptr.h`, `sysattr.h`), `btbulkdelete` and `_bt_pagedel` (`nbtree.c`, `nbtpage.c`), the index row count an `ANALYZE` and a build write (`analyze.c`, `index.c`), and `reindex_index` as the oracle (`index.c`); and the per-table analyze reloptions and their lock level (`reloptions.c`). Both scripts were edited in place — a shared harness with a plan, five-phase snapshots, an `assert_built()` contract pass, a `want_stage` prediction column and a `verdicts` view carrying the shared bands beside the older ones; a new `churn` stage per leg; 28 gate fixtures filed as plan rows; and four defect repairs — then re-extracted from this page with their own `md_block` logic and parsed with `bash -n` (2,648 and 1,048 lines). 17.11 was built out of tree under `.wiki-runtime/tmp/btree-suite/build17` with `--enable-debug --with-icu --with-readline --with-zlib` at `JOBS=16` and passed `make check` All 225 plus 8, 1 and 3; 12.2 was built the same way with `-DTRUE=1 -DFALSE=0` and passed All 192 plus 5, 1 and 2. Both clusters ran `--locale=C`, `--encoding=UTF8`, `autovacuum = off`, `fsync = off`, `shared_buffers = 512MB`, `maintenance_work_mem = 256MB`, `max_parallel_maintenance_workers = 0` at the default `BLCKSZ` on `Linux x86_64` (Ubuntu 24.04, gcc 13.3.0, ICU 74.2). Both pinned checkouts stayed read-only and clean at their pins, both servers were stopped by their own `stop` stages with the teardown confirmed, and the sandbox was deleted, so reproducing any number means re-running the two filed scripts from the pins.

- Re-port to the mandatory suite and full re-run on 2026-09-14, same pins, both legs built and run end to end: the concept page [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md) as it stands after its 2026-09-12 retirements and its 2026-09-13 maintenance assumption, read in full, and every fixture on this page checked against it; the vacuum-then-analyze order of `VACUUM ANALYZE` and the autovacuum worker's entry into the same routine (`vacuum.c`, `autovacuum.c`); rule 3's threshold arithmetic and the counter it reads (`autovacuum.c`, `guc_tables.c`, `system_views.sql`, `pgstat_relation.c`); and the `pg_stats_ext` inherited flag and its `row_to_json` read (`system_views.sql`, `pg_proc.dat`, `jsonfuncs.c`). Both scripts were edited in place - eleven retired fixtures dropped from the 17 leg and three from the 12 leg, the maintenance `VACUUM ANALYZE` added to ten recipes, the `geometry`, `calibration` and `acceptance` stages deleted with the `geo`, `cal` and `acc` databases, `BASE3`/`BASE4` and the two `sql` blocks they hashed removed, the expected-error list narrowed to one pair on the 17 leg, and the stage lists and usage tables brought into step - then re-extracted from this page with their own `md_block` logic and parsed with `bash -n` (2,332 and 1,021 lines). 17.11 was built out of tree under `.wiki-runtime/tmp/btree-suite/build17` with `--enable-debug --with-icu --with-readline --with-zlib` at `JOBS=12` and passed `make check` All 225 plus 8, 1 and 3; 12.2 was built the same way at `JOBS=8` with `-DTRUE=1 -DFALSE=0` and passed All 192 plus 5, 1 and 2. Both clusters ran `--locale=C`, `--encoding=UTF8`, `autovacuum = off`, `fsync = off`, `shared_buffers = 512MB`, `maintenance_work_mem = 256MB`, `max_parallel_maintenance_workers = 0` at the default `BLCKSZ` on `Linux x86_64` (Ubuntu 24.04, gcc 13.3.0, ICU 74.2, pkg-config present). Both pinned checkouts stayed read-only and clean at their pins; both servers were stopped by the scripts' own `clean` stages with the teardown confirmed, and the sandbox was deleted.

- Report-filter removal and full re-run on 2026-09-14, same pins, both legs built and run end to end: the statement's own projection and filters, the `pg_relation_size` size read and its missing-relation behaviour (`dbsize.c`), and the `suppress_row` terms that remain the only report filter; both leg scripts edited in place - the 1 MB predicate and the `LIMIT 20` removed from `sql` block 1, `harness_view` taught both tails so the superseded text still installs, `BASE1` re-baselined from `646df923…` to `4de245c5…` and `BASEPRE` with it from `8acd531b…` to `152f4172…`, `over_1mb` demoted from a decision term to an observation in both `verdicts` views, the `lost_by` size arm deleted, and six read-only summaries added: the printed row counts of both exact texts, the report split on the 1 MB boundary, the under-1 MB listing, the accuracy line, the `lost_by` and `withheld_by` breakdowns, the three worst under-reads and what each decision was worth - then re-extracted from this page with their own `md_block` logic and parsed with `bash -n` (2,411 and 1,077 lines). 17.11 was built out of tree under `.wiki-runtime/tmp/btree-nofilter/sb/build17` with `--enable-debug --with-icu --with-readline --with-zlib` at `JOBS=10` and passed `make check` All 225 plus 8, 1 and 3; 12.2 was built the same way with `-DTRUE=1 -DFALSE=0` and passed All 192 plus 5, 1 and 2. Both clusters ran `--locale=C`, `--encoding=UTF8`, `autovacuum = off`, `fsync = off`, `shared_buffers = 512MB`, `maintenance_work_mem = 256MB`, `max_parallel_maintenance_workers = 0` at the default `BLCKSZ` on `Linux x86_64` (Ubuntu 24.04, gcc 13.3.0, ICU 74.2). The `cost`, `criteria` and 12-leg `report` stages were re-run after the summaries were added, which is why the filed `cost.txt` timings are the second set. Both pinned checkouts stayed read-only and clean at their pins; both servers were stopped by their own `stop` stages with the teardown confirmed, and the sandbox was deleted.

- Full review, no-defeat repair and re-run on 2026-09-16, same pins, both legs built and run end to end. Read first: the concept page [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md) in full, with its `### The maintenance must not be defeated` rule of 2026-09-15 and the five forbidden states, the four proofs and the exemption list it does not have. Re-read against `raw/postgres-17/`: `VACUUM`'s removal cutoff and the proc-array and slot horizons behind it (`vacuum.c`, `procarray.c`, `twophase.c`, `vacuumlazy.c`), the `VERBOSE` tuples line the proof parse reads (`vacuumlazy.c`), the skip and lock-not-available messages and the lock level a foreground `VACUUM` and `ANALYZE` take (`vacuum.c`, `analyze.c`, `autovacuum.c`), the four timeouts an autovacuum worker forces to zero and their GUC definitions (`autovacuum.c`, `guc_tables.c`), the `INFO` exemption from `client_min_messages` (`elog.c`), the horizon views the probe reads (`system_views.sql`), and `pgstatindex`'s page classes (`pgstatindex.c`). **All 717 citation links on the page were re-read against the pin - 238 distinct ranges over 88 files - and every one is in bounds and supports its label**, with the page-relative prefix correct on all of them. Both scripts were then edited in place: the 33 maintenance statements of the 17 leg's fixture file and its two drains, the 12 leg's three fixture statements, its drain and its `extstat` fixture all became one bracketed `VACUUM (VERBOSE, ANALYZE)` each; the harness gained `maint`, `horizon` and `pageclass` - none with an index, so the report the run scores is unchanged - and `horizon_probe()`, `maint_begin()`, `maint_end()`, plus `maint_after()` on the 12 leg; both legs gained a `parse_verbose` in Bash, a proofs check that dies rather than score, a skip-line check, a page-class read, `criteria.txt` block 8 and per-fixture maintenance columns in both verdict views; the census sessions were zeroed and probed on both sides; and the `xstat` comparison's own fixture was brought onto the same footing. Both were re-extracted from this page with their own `md_block` logic and parsed with `bash -n` (2,843 and 1,357 lines). 17.11 was built out of tree under `.wiki-runtime/tmp/btree-maint/build17` with `--enable-debug --with-icu --with-readline --with-zlib` at `JOBS=10` and passed `make check` All 225 plus 8, 1 and 3; 12.2 was built the same way with `-DTRUE=1 -DFALSE=0` and passed All 192 plus 5, 1 and 2. Both clusters ran `--locale=C`, `--encoding=UTF8`, `autovacuum = off`, `fsync = off`, `shared_buffers = 512MB`, `maintenance_work_mem = 256MB`, `max_parallel_maintenance_workers = 0` at the default `BLCKSZ` on `Linux x86_64` (Ubuntu 24.04, gcc 13.3.0, ICU 74.2, 22 cores). The 17 leg ran twice under the final script text - once on the cluster the repairs were developed against, once from a fresh `initdb` - and the 12 leg once from a fresh `initdb`; the filed numbers are the fresh runs'. Two Markdown table rows whose stray leading pipe shifted every column were repaired at the same time. Both pinned checkouts stayed read-only and clean at their pins; both servers were stopped by their own `stop` stages with the teardown confirmed, and the sandbox was deleted.

## Evidence Map

| Claim group | Primary evidence |
|---|---|
| Candidate and count inputs | [pg_index.h#pg_index](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L26-L62), [pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L55-L66), [system_views.sql#pg_stat_all_tables](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L670-L703). |
| Sizes, relation locks and missing-relation behavior | [dbsize.c#calculate_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L301-L371). |
| Leaf and internal page capacity | [nbtsort.c#_bt_blnewpage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L605-L629), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L907-L923), [nbtsort.c#soft-limit](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L853-L854), [nbtsort.c#_bt_sortaddtup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L713-L735), [nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1147). |
| The never-closed rightmost page of each level | [nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1062-L1128), [nbtsort.c#_bt_slideleft](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L682-L700). |
| Posting-list capacity and sizing | [nbtsort.c#maxpostingsize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1304-L1305), [nbtdedup.c#_bt_dedup_save_htid-cap](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L510-L513), [nbtdedup.c#_bt_dedup_start_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L432-L474), [nbtdedup.c#_bt_form_posting-size](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L879-L884). |
| Equal-image eligibility and its three states | [nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5139-L5183), [datum.c#btequalimage](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L424-L438), [varlena.c#btvarstrequalimage](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L2595-L2615), [nbtpage.c#_bt_initmetapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L67-L84), [btreefuncs.c#bt_metap-allequalimage](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L916-L921). |
| Width, expression header and compression | [analyze.c#compute_scalar_stats-width](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2420-L2426), [heaptuple.c#heap_compute_data_size](../../../../raw/postgres-17/src/backend/access/common/heaptuple.c#L234-L242), [varatt.h#VARATT_CAN_MAKE_SHORT](../../../../raw/postgres-17/src/include/varatt.h#L257-L262), [indextuple.c#index_form_tuple-compression](../../../../raw/postgres-17/src/backend/access/common/indextuple.c#L116-L138), [heaptoast.h#TOAST_INDEX_TARGET](../../../../raw/postgres-17/src/include/access/heaptoast.h#L63-L68). |
| Inheritance passes and statistics visibility | [analyze.c#analyze_rel-passes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L249-L259), [analyze.c#update_attstats-stainherit](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1647), [system_views.sql#pg_stats-visibility](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L268-L275), [acl.c#column_privilege_check](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L2538-L2569), [aclchk.c#grant-refuses-indexes](../../../../raw/postgres-17/src/backend/catalog/aclchk.c#L1858-L1863). |
| Probe construction and grouping semantics | [pg_proc.dat#pg_get_expr](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L8219-L8220), [nodeSubplan.c#ExecScanSubPlan-EXISTS](../../../../raw/postgres-17/src/backend/executor/nodeSubplan.c#L293-L296), [nbtutils.c#_bt_keep_natts_fast](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4875-L4905), [indxpath.c#check_index_predicates](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L3244-L3350). |
| Flush ordering and the counter artifact | [postgres.c#idle-stats-flush](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L4634-L4705), [pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L584-L600), [pgstat_relation.c#pgstat_report_analyze](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L289-L337). |
| Output formatting, range errors and split strategies | [dbsize.c#pg_size_pretty-sign](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L569-L600), [numeric.c#bigint-out-of-range](../../../../raw/postgres-17/src/backend/utils/adt/numeric.c#L4546-L4549), [nbtsplitloc.c#_bt_strategy-single-value](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L1020-L1033). |
| Harness oracles | [btreefuncs.c#GetBTPageStatistics](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L108-L194), [pageinspect--1.8--1.9.sql#bt_page_stats](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L87-L124), [pgstattuple--1.4.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4.sql#L19-L31). |
| Clean shutdown and teardown confirmation in the suite scripts | [postmaster.c#process_pm_shutdown_request-fast](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L2266-L2305), [postmaster.c#process_pm_shutdown_request-immediate](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L2307-L2342), [xlog.c#ShutdownXLOG](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L6580-L6621), [xlogrecovery.c#not-properly-shut-down](../../../../raw/postgres-17/src/backend/access/transam/xlogrecovery.c#L922-L949), [pg_ctl.c#do_stop](../../../../raw/postgres-17/src/bin/pg_ctl/pg_ctl.c#L1015-L1065), [miscinit.c#UnlinkLockFiles](../../../../raw/postgres-17/src/backend/utils/init/miscinit.c#L1170-L1194), [pqcomm.c#RemoveSocketFiles](../../../../raw/postgres-17/src/backend/libpq/pqcomm.c#L846-L861). |
| Core-SQL contract and model-specific choices | [The current recommended statement](#the-current-recommended-statement). These expressions are the wiki's model, not a PostgreSQL engine guarantee. |
| Mandatory test inventory and what the engine suites cover | [regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59), [regress.sgml#contrib-suites](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L171-L195), [installation.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L515-L522). |
| Rule 3's threshold, its two GUCs and their reloption form | [autovacuum.c#anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3068-L3076), [autovacuum.c#doanalyze](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095), [guc_tables.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3367-L3375), [guc_tables.c#autovacuum_analyze_scale_factor](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3906-L3914), [reloptions.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L243-L251), [reloptions.c#autovacuum_analyze_scale_factor](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L416-L425). |
| The counter the census reads, and its reset | [system_views.sql#n_mod_since_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L689), [pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L331-L338). |
| What rule 2's drain selects on, and what its `VACUUM` reclaims | [itemptr.h#ItemPointerData](../../../../raw/postgres-17/src/include/storage/itemptr.h#L36-L40), [sysattr.h#SelfItemPointerAttributeNumber](../../../../raw/postgres-17/src/include/access/sysattr.h#L21), [nbtree.c#btbulkdelete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L820-L832), [nbtpage.c#_bt_pagedel](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1801-L1815). |
| Why the forgeries run after the census, and what the oracle rebuild writes | [analyze.c#totalindexrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L662), [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2809-L2830), [index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3582-L3600). |
| The cluster setting the phases depend on | [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1450-L1457). |
| Why a foreground `VACUUM ANALYZE` stands in for the launcher's maintenance, and why `ANALYZE` writes last | [vacuum.c#ExecVacuum-vacuum](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L450-L451), [vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650), [autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3120-L3147). |
| The deduplication-gate verdicts and their oracle | [nbtutils.c#_bt_allequalimage-INCLUDE](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5144-L5147), [nbtutils.c#_bt_allequalimage-debug](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5172-L5180), [fmgr.c#internal-function-resolution](../../../../raw/postgres-17/src/backend/utils/fmgr/fmgr.c#L216-L240), [nbtree.h#BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1146-L1150). |
| The control fixtures' engine behaviour | [execIndexing.c#partial-predicate-skip](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L384-L386), [relcache.c#RelationSetNewRelfilenumber-reltuples](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3951-L3952), [index.c#index_update_stats-sentinel](../../../../raw/postgres-17/src/backend/catalog/index.c#L2835-L2836), [analyze.c#std_typanalyze-minrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1894). |
| Rerun protocol: build, cluster settings and oracles | [installation.sgml#VPATH](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L427-L432), [installation.sgml#ICU_CFLAGS](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L184-L193), [installation.sgml#--enable-debug](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L1530-L1540), [initdb.sgml#--locale](../../../../raw/postgres-17/doc/src/sgml/ref/initdb.sgml#L281-L291), [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1450-L1453), [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2262-L2265), [pageinspect--1.8--1.9.sql#bt_metap](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L73-L82), [pageinspect--1.8--1.9.sql#bt_page_items](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L109-L118), [amcheck--1.0--1.1.sql#bt_index_check](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.0--1.1.sql#L12-L28), [verify_nbtree.c#metapage-equalimage-check](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L380-L396). |
| Untested build paths and relation shapes | [installation.sgml#--with-blocksize](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L1472-L1482), [nbtsort.c#btbuild-parallel](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L389-L392), [index.c#index_concurrently_build](../../../../raw/postgres-17/src/backend/catalog/index.c#L1533-L1539), [indexcmds.c#ReindexRelationConcurrently-build](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L4009), [pg_class.h#relkind](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L164-L173), [vacuum.c#expand_vacuum_rel-partitions](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L963-L982). |
| Cross-version, width and platform open questions | [system_views.sql#pg_stats_ext-inherited](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L290), [pg_statistic.h#stawidth](../../../../raw/postgres-17/src/include/catalog/pg_statistic.h#L41-L50), [analyze.c#stawidth](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2536-L2540), [pg_proc.dat#pg_control_init](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L11989-L11997). |
| The statistics-flush interval that gates the publication artifact | [pgstat.c#flush-intervals](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L117-L122), [pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L584-L600), [pgstat.c#pgstat_force_next_flush](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L700-L708). |
| Gate scoring oracle and the internal-function resolution the impostor case turns on | [btreefuncs.c#bt_metap-allequalimage](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L916-L921), [nbtpage.c#_bt_initmetapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L67-L84), [nbtutils.c#_bt_allequalimage-debug](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5172-L5180), [fmgr.c#internal-function-resolution](../../../../raw/postgres-17/src/backend/utils/fmgr/fmgr.c#L216-L240). |
| The measured nondeterministic-collation branch | [varlena.c#btvarstrequalimage](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L2595-L2615), [pg_locale.c#pg_locale_deterministic](../../../../raw/postgres-17/src/backend/utils/adt/pg_locale.c#L1567-L1575), [index.c#pattern-ops-collation-check](../../../../raw/postgres-17/src/backend/catalog/index.c#L826-L849), [installation.sgml#ICU-default](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L170). |
| Multicolumn key groups and the extended-statistics escape | [system_views.sql#pg_stats_ext](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L277-L309), [mvdistinct.c#pg_ndistinct_out](../../../../raw/postgres-17/src/backend/statistics/mvdistinct.c#L355-L385), [The current recommended statement](#the-current-recommended-statement). |
| What the scoring pass rebuilds, and under which lock | [indexcmds.c#ReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2804-L2829), [index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3583-L3597). |
| Cluster settings the scripts write, and their apply scopes | [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1450-L1453), [guc_tables.c#fsync](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1097-L1100), [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2262-L2265), [guc_tables.c#log_min_messages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4873-L4877), [guc_tables.c#unix_socket_directories](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4426-L4430), [guc_tables.c#listen_addresses](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4437-L4441), [guc_tables.c#port](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2394-L2397), [guc_tables.c#logging_collector](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1641-L1644), [initdb.sgml#--locale](../../../../raw/postgres-17/doc/src/sgml/ref/initdb.sgml#L281-L291). |
| Why every `psql` helper carries `ON_ERROR_STOP`, and what a `-c` action returns without it | [mainloop.c:376](../../../../raw/postgres-17/src/bin/psql/mainloop.c#L376), [mainloop.c#die_on_error](../../../../raw/postgres-17/src/bin/psql/mainloop.c#L587-L594), [startup.c#single-query-action](../../../../raw/postgres-17/src/bin/psql/startup.c#L377-L386), [psql-ref.sgml#Exit-Status](../../../../raw/postgres-17/doc/src/sgml/ref/psql-ref.sgml#L627-L636). |
| Where the `inherited` flag of `pg_stats_ext` comes from, and which `ANALYZE` pass writes it | [system_views.sql#pg_stats_ext](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L277-L309), [system_views.sql:290](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L290), [pg_statistic_ext_data.h:35](../../../../raw/postgres-17/src/include/catalog/pg_statistic_ext_data.h#L35), [pg_statistic_ext_data.h:57](../../../../raw/postgres-17/src/include/catalog/pg_statistic_ext_data.h#L57), [analyze.c#analyze_rel-passes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L246-L259), [analyze.c#BuildRelationExtStatistics-call](../../../../raw/postgres-17/src/backend/commands/analyze.c#L604-L606), [extended_stats.c#BuildRelationExtStatistics](../../../../raw/postgres-17/src/backend/statistics/extended_stats.c#L111-L114), [extended_stats.c#statext_store](../../../../raw/postgres-17/src/backend/statistics/extended_stats.c#L790-L791). |
| Why reading that flag through `row_to_json()` is the same predicate where the column exists, and a no-op where it does not | [pg_proc.dat#row_to_json](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L8975-L8977), [json.c#composite_to_json](../../../../raw/postgres-17/src/backend/utils/adt/json.c#L546-L579), [json.c#datum_to_json-bool](../../../../raw/postgres-17/src/backend/utils/adt/json.c#L212-L221), [pg_operator.dat#json-arrow-text](../../../../raw/postgres-17/src/include/catalog/pg_operator.dat#L3160-L3162), [pg_proc.dat#json_object_field_text](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L9078-L9081), [jsonfuncs.c#json_object_field_text](../../../../raw/postgres-17/src/backend/utils/adt/jsonfuncs.c#L881-L895), [bool.c#parse_bool_with_len](../../../../raw/postgres-17/src/backend/utils/adt/bool.c#L36-L58), [bool.c#boolin](../../../../raw/postgres-17/src/backend/utils/adt/bool.c#L126-L150). |
| Why the base catalogs are not an alternative access path, and what the view's lateral costs to serialise | [system_views.sql#pg_statistic_ext_data-revoke](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L382-L383), [system_views.sql#pg_stats_ext](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L301-L307), [system_views.sql#pg_stats-inherited](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L189-L194). |
| What the server-error check reads, and why only errors that reached the top of the backend are in the log | [elog.c#errfinish-rethrow](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L515-L546), [postgres.c#PostgresMain-error-handler](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L4446-L4485), [pl_exec.c#exec_stmt_block-catch](../../../../raw/postgres-17/src/pl/plpgsql/src/pl_exec.c#L1829-L1839), [elog.c#error_severity](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L3667-L3705), [elog.c:3194](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L3194), [elog.c#EVALUATE_MESSAGE](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L989-L1018), [initdb.c#lc_messages-default](../../../../raw/postgres-17/src/bin/initdb/initdb.c#L2424-L2425), [initdb.c#lc_messages-conf](../../../../raw/postgres-17/src/bin/initdb/initdb.c#L1292-L1293). |
| When a logged error carries its statement, and why a clean restart adds nothing the check counts | [elog.c#check_log_of_query](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L2727-L2743), [elog.c#STATEMENT-line](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L3276-L3284), [elog.c#errhidestmt](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L1406-L1420), [guc_tables.c#log_min_error_statement](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4884-L4891), [guc_tables.c#log_line_prefix](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4095-L4101), [pg_ctl.c#start_postmaster-command](../../../../raw/postgres-17/src/bin/pg_ctl/pg_ctl.c#L489-L494), [pg_ctl.c#wait_for_postmaster_start](../../../../raw/postgres-17/src/bin/pg_ctl/pg_ctl.c#L592-L699), [backend_startup.c#CAC_STARTUP](../../../../raw/postgres-17/src/backend/tcop/backend_startup.c#L265-L278), [postgres.c#administrator-command-FATAL](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L3315-L3318). |
| Why the repaired check can pair an error with its statement by log prefix, and read the statement's continuation lines | [elog.c#EmitErrorReport-timestamp-reset](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L1687-L1702), [elog.c#get_formatted_log_time](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L2654-L2686), [elog.c#log_line_prefix-%p](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L2954-L2958), [elog.c#log_line_prefix-%m](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L2989-L2998), [elog.c#send_message_to_server_log-prefix](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L3186-L3194), [elog.c#append_with_tabs](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L3719-L3729), [elog.c#STATEMENT-line](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L3276-L3284). |
| What the no-defeat rule forbids, and what makes each state defeat a `VACUUM` | [vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122), [procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815), [procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902), [twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26), [vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052), [vacuum.c#vacuum-lockmode](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2049-L2056). |
| The four proofs the run records, and where each number comes from | [vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L659-L663), [vacuum.c#skip-lock-not-available](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L828-L860), [system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L878-L885), [system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017), [system_views.sql#pg_prepared_xacts](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L421-L427), [pgstatindex.c#page-classes](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L295-L320). |
| Why the maintenance sessions zero four timeouts, and why `VERBOSE` still reaches the client | [guc_tables.c#statement_timeout-and-lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2631), [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642), [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653), [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470), [elog.c#should_output_to_client](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L247-L264). |

## Open Questions

These are the limitations the 2026-09-16 no-defeat run leaves, each with what
measured it, on the fixture set the 2026-09-14 re-port left. That re-port
removed coverage as well as fixtures, and the first two entries say so before
anything else. What this pass added is proof that the maintenance behind every
reading was not defeated; it did not add coverage, and it closed no entry
below.

### The mandatory suite and the current statement

The asker's 2026-08-18 contract says a statement that fails a mandatory test is
corrected, not reported. The whole suite has been put to the current text again,
so what is open is not coverage but **29 failures the 2026-09-16 run leaves
standing**, and none of them has a candidate fix in the statement:

- **25 false negatives, and two of them are the model rather than a filter.**
  22 rows are withheld by an exclusion term and 1 carries a caveat the reading
  rule refuses to promote, on files a rebuild emptied by a mean 83.9 % and
  100.0 %; the remedy for those would mean relaxing a term that a measured
  false positive put there, and that trade is still unresolved. The other two,
  **`p31` and `f91`, are the worse pair**: both are printed, they read `-233.3`
  and `-248.6` on `wasted_space_pct_floor`, and a rebuild gave back 79.2 % and
  89.2 %. The 1 MB predicate hid them until 2026-09-14, which is why every run
  before that could say no miss was a threshold loss. `expected_stage` still
  agrees with the statement on all 101 fixtures, so the defect is in the
  arithmetic the two agree on: the model predicts a larger rebuild than the
  current file for an index whose subset is narrow, and the floor column makes
  that worse. **No fix is proposed here, and the two rows are the clearest
  candidate for the next revision.**
- **4 critical false positives**, all reported and alertable against a measured
  0.0 %: the forged partial count `f84` at 94.2 %, the stale-statistics
  construction `f85` at 70.7 %, the wide-key partial index `i103` at 84.1 % and
  the zero-statistics-target index `x109` at 62.5 %. The first two are family 3
  constructions the suite exists to catch; the last two were predicted and
  reproduced. Neither the filter removal nor the no-defeat repair added one:
  all four are over 1 MB, and the two that are churned were maintained with
  `dead but not yet removable` 0.
- **The wider report is not a measured improvement in precision.** It printed
  68 rows instead of 20 on the fixture database, 45 of them 1 MB or smaller,
  and no fixture measures how a reader triages that list. Of the 31 under-1 MB
  fixtures 11 are visible; the other 20 are withheld by an exclusion term.
  Among the 11, six were worth acting on - `p19` is 200 KiB of waste on a
  240 KiB index - while `p120` reads 87.5 % on 64 KiB where a rebuild gave back
  nothing and is held back only by a caveat, and `f88` reads `-3291.9 %`.
  Nothing on this page measures how often a reader acts on a row like those
  anyway.

[The mandatory suite, re-scored under the shared protocol](#the-mandatory-suite-re-scored-under-the-shared-protocol),
[Mandatory test review](#mandatory-test-review),
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md).

### What the re-port removed, and what that costs

The 2026-09-14 pass deleted fixtures and the claims they backed. Three of those
losses are coverage this page used to have and now does not:

- **No fixture reads the statement as anything but the owner.** The
  `wiki_reader` role and the expression-index privilege fixtures went with the
  acceptance stage, so the `statistics not visible to this role` caveat and the
  owner-only `pg_stats` filter are source-derived again rather than measured.
  Item 5 of [What still needs to be tested](#what-still-needs-to-be-tested)
  names what restoring it would take.
- **No fixture measures the page-geometry closed forms, the insertion-pattern
  calibration, in-index compression, posting-tail capacity or the statistics
  publication barrier.** The statement still contains all of that arithmetic;
  what is gone is the evidence that it is exact. A reader who needs those
  numbers has to re-derive them, and the git history holds the harnesses that
  produced the previous figures.
- **The suite inherits the concept page's own blind spots.** No fixture builds a
  dead-but-not-vacuumed index, nothing pins the row count `VACUUM` writes,
  fixtures 92 to 95 no longer isolate the analyze threshold because all four are
  analyzed after their changes, and 118 and 119 now describe one state that
  differs only by a second sample. Those are that page's open questions, not
  this page's, and this page cannot close them by adding a fixture the suite
  does not define.

### In-index compression of wide keys

`index_form_tuple` compresses a varlena key wider than `TOAST_INDEX_TARGET`
whose storage is `extended` or `main`, and nothing in the catalogs records the
compressed width, so `pg_stats.avg_width` describes the heap datum while the
index stores something smaller. The statement warns with
`wide compressible key: stored width may be over-stated` and cannot correct the
number. A fix would need a sampled `pg_column_size` probe of the index
expression, which is not a catalog read. **No fixture in the suite builds this
shape**, so the size of the error is no longer measured on this page.
[indextuple.c#index_form_tuple-compression](../../../../raw/postgres-17/src/backend/access/common/indextuple.c#L116-L138),
[heaptoast.h#TOAST_INDEX_TARGET](../../../../raw/postgres-17/src/include/access/heaptoast.h#L63-L68).

### Custom operator classes

An opclass whose support function 4 is not one of the two internal functions
lands in `unknown` and receives no deduplication credit, even when the engine
calls it and deduplicates. The 2026-09-16 gate measured that cost again, to the
decimal of the previous run: `-226.4 %` on `i_ei_true`, whose SQL callback
returns true, and `-319.1 %` on `i_squat`, whose impostor wears a built-in's
name; the metapage says true for both. Executing the function from SQL would decide the case -
`OidFunctionCall1Coll` is what the engine does - but a catalog-only statement
must not call an arbitrary user function, so the state stays three-valued and
the answer stays conservative.
[nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5139-L5183),
[btreefuncs.c#bt_metap-allequalimage](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L916-L921),
[The deduplication gate, scored against the current statement](#the-deduplication-gate-scored-against-the-current-statement).

### Multicolumn key groups without extended statistics

**A duplicate-heavy multicolumn index whose key columns are correlated is the
statement's largest unflagged error.** For a key of more than one column the
model has no per-class split, so it takes one class of `live_rows` rows over
`groups_est` groups, and `groups_est` is the product of the per-column distinct
counts clamped to the row count. On the gate's two 500,000-row tables with 5,000
distinct values in each key column that product saturates the clamp,
`tids_per_tuple` comes back 1.0, and the model prices 500,000 separate tuples
against an index the engine deduplicated to 459 blocks: `-320.0 %` on both
`i_multi_ok` and `i2_ok`, under the current text and the superseded one alike.

The fix already exists in the statement and is not automatic. Adding
`CREATE STATISTICS ... (ndistinct)` on the key columns and analysing makes the
`extstat` stage read the whole-key entry, which raises the caveat
`key groups from extended statistics`; fixtures 44b and 45 carry such an object
and 44a does not, which is the pair that shows the difference inside the suite.
Until then, read a large negative reading on a multicolumn index as a missing
statistics object rather than as index bloat, and note that no caveat says so.
[The current recommended statement](#the-current-recommended-statement),
[system_views.sql#pg_stats_ext](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L277-L309),
[mvdistinct.c#pg_ndistinct_out](../../../../raw/postgres-17/src/backend/statistics/mvdistinct.c#L355-L385).

### Partial-index populations and zero counts

The population probe validates whether a subset is empty, but not the widths,
NULL pattern or expression results over that subset, and an empty sample remains
inconclusive about a subset that acquired rows after the last `ANALYZE`. The
four partial-index suppression conditions still drop rows from the report rather
than reporting them with a caveat, so a partial index with real savings can
still be invisible: 22 of the 25 false negatives are exactly that, and neither
the filter removal nor the no-defeat repair did anything for them, because
neither size nor a defeated `VACUUM` was ever why they were withheld. Neither
gap is closed.

**The two texts no longer filter alike, and the asker chose that on purpose.**
The report lost its `actual_bytes > 1024 * 1024` predicate on 2026-09-14; the
probe generator kept its `pg_relation_size(c.oid) > 1024 * 1024`. So the
generator is now the narrower of the two, and it is narrow exactly where
validation matters most: on 2026-09-16 it again emitted one population probe,
for `p113b`, and none for `p116` or `p120`, which also model zero rows on files
of one and eight blocks. A subset small enough to be missed by the `ANALYZE` sample
is also small enough to fall under the generator's filter, so the reading most
in need of validation is the one least likely to get a probe - and now that the
report prints those rows, a reader is more likely to meet one. Removing the
generator's filter is the obvious follow-up and is unmeasured.
[analyze.c#sample-membership](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L975),
[Validation probes](#validation-probes).

### Fixture verdicts that depend on the ANALYZE sample

Fixture 120 does not give the same answer twice. It sets
`default_statistics_target` to 1, which samples 300 rows, and whether those 300
include any of the 2,000 rows in a 1,000,000-row table decides whether the
index's modelled row count is 0 or a few thousand. Eight runs have now read
87.5 %, `-50.0 %`, 87.5 %, 87.5 %, `-50.0 %`, `-50.0 %`, `-50.0 %` and 87.5 %;
the filed 2026-09-16 run read 87.5 % with `modelled_rows` at 0, so the
fixture's precondition was met and the row scored `PASS` under the shared bands
- the caveat holds it back - while the older point-estimate band calls the same
row a `CRITICAL FALSE POSITIVE`. Both outcomes are legitimate readings of the
same physical index.

**This pass found a second fixture that does it, and the pair it belongs to
says why.** `p41` is a two-column key correlated in the table and independent
only inside the subset. Whether the model credits deduplication there turns on
a sampled `n_distinct` product, and that decides whether the row is printed at
all: 2026-09-14 withheld it by `A: duplicates from table statistics` and
counted it a `FALSE NEGATIVE`, both 2026-09-16 runs printed it, decided
`rebuild` and scored `PASS` at 74.4 % against 75.2 %. Its near-twin `p45`, the
same shape with a `CREATE STATISTICS (ndistinct)` object, stayed withheld on
every run, so the boundary is exactly the statistics object the
[multicolumn open question](#multicolumn-key-groups-without-extended-statistics)
describes. That is one fixture's verdict moving with the sample, not a change
in the model, and it is the whole difference between this run's score and the
previous one's.

The honest fix for both is the same: seed the sample, score the fixture over
repetitions, or state its verdict as a distribution. This page does neither,
and unlike the sibling page it **does not assert fixture 120's precondition
either**, so a run whose sample happens to find the subset scores the fixture
rather than recording it as unmet. No other fixture has been observed to flip,
but nothing in the harness proves that none can, and the three readings that
visibly wander - 120, 41 and `f88`'s worst-case percentage - are all sampled
inputs.
[analyze.c#std_typanalyze-minrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1894),
[guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2071-L2074).

### Statistics publication and test ordering

The 17 leg forces a flush before every `ANALYZE` and `VACUUM`, including the
maintenance step, and the 12 leg polls in a fresh session because the function
does not exist there. What is not established is how a production reader should
order itself against an unknown writer: `pg_stat_force_next_flush()` forces the
*calling* backend's pending statistics, not another session's, so a report taken
while other backends hold unflushed deltas can still mix an absolute `ANALYZE`
write with a later additive flush. The observer's own snapshot needs
`pg_stat_clear_snapshot()` only inside a transaction block. The 12 leg used to
show the cost of not having the function - two of its nine tables reached the
census at 896.6 % and 899.3 % modified - and the 2026-09-16 repair closed that
by accident rather than by design: putting each maintenance statement in its
own session after the drain's has exited makes the `DELETE` counts arrive
before the `ANALYZE` that resets them, and the census now analyzes 0 of 9. The
ordering still rests on when a session exits rather than on a barrier the leg
can force.
[pgstat.c#pgstat_force_next_flush](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L700-L708),
[pgstat.c#pgstat_clear_snapshot](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L786-L800),
[guc_tables.c#stats_fetch_consistency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4966-L4974).

### Alert thresholds and rebuild savings

The 50 % threshold that turns this estimator into a decision is the harness's
choice and appears nowhere in the filed text, so every band count on this page
moves if the threshold moves, and no sensitivity curve has been measured around
it. The filter removal widened the population that threshold judges - 11
under-1 MB fixtures now reach it, and two of them fail it - without changing the
threshold itself. Nothing here covers mixed workloads, indexes under concurrent
write load, bottom-up deletion reclaiming space between the reading and the
rebuild, or whether a saving persists after the workload resumes. The insertion-pattern
calibration that used to bound the first of those was removed on 2026-09-14.
[nbtsplitloc.c#split-policy](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L278-L335).

### Scoring column for the partial-index contract

The asker chose `wasted_space_pct_floor` as the verdict column on 2026-08-19
because that column has no duplication term. The floor is now known to be
unusable as a conservative bound on a deduplicating index: on 2026-09-16 the
three deterministic `text` gate fixtures again read `-0.4 %` on the point
estimate and `-319.1 %` on the floor as built, against a measured 0.0 %. The two rules therefore
disagree on any index that deduplicates, and the reading guidance names
`wasted_space_pct` with `equalimage` and `caveats` instead. The protocol records
both columns and both verdicts - 72 `PASS` under the shared bands on the floor,
81 and 82 under the older floor and point bands - and which one carries the
contract is the asker's decision. The filter removal sharpened the cost of that
choice: both threshold losses, `p31` and `f91`, read `-233.3` and `-248.6` on
the floor, and the point column reads the same, so neither column would have
rebuilt them.
[Reading the output](#reading-the-output).

### Cross-version execution of the revised statement

**The parse half is fixed and stays fixed.** The text filed until 2026-09-10
selected `pg_stats_ext` rows with `inherited = false`, naming a column this
version's view defines from `stxdinherit` and the pinned 12 server does not
have; it was refused before any fixture was built. The `extstat` CTE now reads
that flag with `coalesce((row_to_json(se) ->> 'inherited')::boolean, false) =
false`, and on 2026-09-16 the exact filed text was accepted unmodified on 12.2
with `transform_edits=0`, while `EXCEPT` in both directions over three databases
returned 0 rows on 17.11.
[system_views.sql#pg_stats_ext-inherited](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L290),
[The portable extended-statistics filter](#the-portable-extended-statistics-filter).

Three things stay open, none of them the parse. **The 12 leg scores 13 fixtures
against the 17 leg's 126**, so the partial-index contract is enforced on one
major only, and that leg reaches neither family 3 nor family 4. **The v12
companion page still documents its own Method A**, not this text, so a reader
following the cross-version link finds a different statement. And **only two
majors are tested**: nothing here says what the `row_to_json` read does on 13,
14, 15 or 16, where the column arrived at some release this page may not cite;
the construct is designed to be indifferent to that, but indifference is not a
measurement.
[The v12 publication protocol](../../../v12/questions/indexing/btree-index-bloat-core-sql-only.md#the-v12-publication-protocol).

### Integer-truncated widths across an alignment boundary

`stawidth` is an `int32`, and for a variable-width column `ANALYZE` assigns it
`total_width / nonnull_cnt`, so a column whose values average 4.9996 bytes
records 4. On the `(int4, numeric)` gate fixture `i_multi_bad` the model prices a
16-byte tuple where the build stores 24, and the reading was 28.8 % again on
2026-09-16, with the gate closed. A remedy would need a fractional width that no
catalog holds, or a sampled `pg_column_size`, which is not a catalog read.
[analyze.c#stawidth](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2536-L2540),
[pg_statistic.h#stawidth](../../../../raw/postgres-17/src/include/catalog/pg_statistic.h#L41-L50),
[Page and posting geometry](#page-and-posting-geometry).

### Fixture statements are marked disposable, not tagged

`MANDATORY Production SQL` asks for an inline `/* wiki_... */` tag after the
leading verb, and `MANDATORY Measurement Script` extends it to "the statements
the script sends"; the same rule separately asks that fixture statements be
marked disposable. This page reads those as two requirements for two kinds of
statement: the statements whose output it publishes carry tags, and the fixture
`CREATE`, `INSERT`, `ANALYZE`, `VACUUM`, `UPDATE` and `DROP` lines carry
disposability banners instead. That reading is not stated in the rule, and the
alternative - tagging every fixture statement - has not been adopted.

### The 12 leg's settings have no citable apply scope here

The 12 leg writes `listen_addresses`, `unix_socket_directories`, `port`,
`autovacuum`, `fsync`, `shared_buffers`, `maintenance_work_mem` and
`max_parallel_maintenance_workers` into its cluster's `postgresql.conf`, and
sets `client_min_messages`, `statement_timeout` and `lock_timeout` per session.
`MANDATORY GUC Changes` wants each one's context and apply scope from the
same-version definition, but `MANDATORY Citations` forbids a v17 page from
citing the pinned 12 checkout at all, and this page has no validated 12.2
`pg_settings` capture. The run itself is unaffected, because every file-level
setting is in place before the first start, but a reader who changes one of them
on a 12.2 server has to look up its scope elsewhere. The clean fix is a
`pg_settings` capture in the 12 leg's `facts` stage, or the same table on a v12
page.

### What the no-defeat proofs leave open

The rule is satisfied on every maintenance statement of both legs, and three
things about that are worth saying plainly rather than leaving to a reader.
**The horizon reading is a probe, not an interlock**: `horizon_probe()` runs
immediately before each statement and once after the census, and nothing holds
the cluster still in between, so it is evidence about a cluster whose only
sessions are the script's rather than a guarantee. **No fixture deliberately
pins a horizon**, so the suite still says nothing about what this statement
reads on a database whose `VACUUM` genuinely cannot remove anything - the
concept page requires such a fixture to be filed as its own numbered test, and
none exists. And **the proof tables cost the run three TOAST index files**,
which is why the cost stage counts 317 B-tree indexes where 2026-09-14 counted
314; the proof tables themselves carry no index, so the report the statement
prints is unchanged at 68 rows, but a reader comparing database sizes across
runs should know where the three came from.
[The maintenance, proved not defeated](#the-maintenance-proved-not-defeated),
[vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122),
[nbtpage.c#_bt_pagedel](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1801-L1815).

### Untested configurations

Nothing here was measured at a non-default `BLCKSZ`, at a `MAXIMUM_ALIGNOF`
other than 8, or on a big-endian machine, and parallel index builds,
`CREATE INDEX CONCURRENTLY`, `REINDEX CONCURRENTLY`, partitioned tables and a
non-C cluster locale were outside every run. Every number on this page comes
from a 17.11 build with `--locale=C` at `max_data_alignment` 8 and
`database_block_size` 8192, read from `pg_control_init()` rather than assumed,
on x86-64 Linux with gcc 13.3.0 and ICU 74.2. The
nondeterministic-collation gap is closed: the gate builds with ICU and measures
the `collisdeterministic` branch on both sides, in a UTF8 database, under
[The collation branch, measured with ICU](#the-collation-branch-measured-with-icu).
[index.c#pattern-ops-collation-check](../../../../raw/postgres-17/src/backend/catalog/index.c#L826-L849),
[pg_locale.c#pg_locale_deterministic](../../../../raw/postgres-17/src/backend/utils/adt/pg_locale.c#L1567-L1575).

## Source References

- [system_views.sql#pg_stats_ext-inherited](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L290)
- [pg_proc.dat#row_to_json](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L8975-L8977)
- [jsonfuncs.c#json_object_field_text](../../../../raw/postgres-17/src/backend/utils/adt/jsonfuncs.c#L881-L895)
- [regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59)
- [installation.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L515-L522)
- [guc_tables.c#statement_timeout-and-lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2631)
- [pg_proc.dat#size-functions](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7487-L7507)
- [pg_proc.dat#pg_size_pretty](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7500-L7507)
- [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L346-L371)
- [dbsize.c#pg_size_pretty-sign](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L569-L600)
- [analyze.c#compute_index_stats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L975)
- [system_views.sql#pg_stats-visibility](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L268-L275)
- [indexfsm.c#index-FSM](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L14-L65)
- [pg_index.h#pg_index](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L26-L62)
- [pg_class.h#reltuples](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L55-L66)
- [nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5139-L5183)
- [pg_amproc.dat#text_ops-equalimage](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L205-L212)
- [system_views.sql#pg_stats_ext](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L277-L309)
- [mvdistinct.c#pg_ndistinct_out](../../../../raw/postgres-17/src/backend/statistics/mvdistinct.c#L355-L385)
- [analyze.c#expression-attributes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L448-L478)
- [analyze.c#analyze_rel-passes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L249-L259)
- [heaptuple.c#heap_compute_data_size](../../../../raw/postgres-17/src/backend/access/common/heaptuple.c#L215-L262)
- [nbtsort.c#_bt_pagestate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L645-L671)
- [nbtsort.c#soft-limit](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L853-L854)
- [nbtsort.c#posting-size-limit](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1284-L1308)
- [nbtsort.c#group-boundaries](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1310-L1349)
- [nbtdedup.c#_bt_dedup_save_htid-cap](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L510-L513)
- [nbtdedup.c#_bt_form_posting-size](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L879-L884)
- [nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1062-L1128)
- [nbtsort.c#_bt_slideleft](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L682-L700)
- [nbtsort.c#BTPageState](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L229-L252)
- [index.c#ambuild-call](../../../../raw/postgres-17/src/backend/catalog/index.c#L3048-L3053)
- [nbtree.c#ambuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L128-L129)
- [nbtsort.c#btbuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L290-L328)
- [nbtsort.c#_bt_leafbuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L535-L571)
- [nbtsort.c#_bt_load](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1284-L1349)
- [nbtsort.c#_bt_sort_dedup_finish_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1026-L1050)
- [itup.h#IndexTupleData](../../../../raw/postgres-17/src/include/access/itup.h#L35-L60)
- [itemptr.h#ItemPointerData](../../../../raw/postgres-17/src/include/storage/itemptr.h#L25-L47)
- [nbtdedup.c#_bt_form_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L864-L910)
- [bufpage.h#PageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L155-L171)
- [nbtree.h#BTPageOpaqueData](../../../../raw/postgres-17/src/include/access/nbtree.h#L62-L71)
- [indextuple.c#index_form_tuple_context](../../../../raw/postgres-17/src/backend/access/common/indextuple.c#L94-L163)
- [nbtsort.c#_bt_leafbuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L557-L570)
- [nbtsort.c#deduplicate](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1135-L1152)
- [datum.c#btequalimage](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L424-L438)
- [varlena.c#btvarstrequalimage](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L2595-L2615)
- [pg_locale.c#pg_locale_deterministic](../../../../raw/postgres-17/src/backend/utils/adt/pg_locale.c#L1567-L1575)
- [fmgr.c#internal-function-resolution](../../../../raw/postgres-17/src/backend/utils/fmgr/fmgr.c#L216-L240)
- [nbtpage.c#_bt_initmetapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L67-L84)
- [nbtsort.c:1126](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1126)
- [analyze.c#compute_scalar_stats-width](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2420-L2426)
- [analyze.c#stawidth](../../../../raw/postgres-17/src/backend/commands/analyze.c#L2536-L2540)
- [heaptuple.c#heap_compute_data_size](../../../../raw/postgres-17/src/backend/access/common/heaptuple.c#L234-L242)
- [varatt.h#VARATT_CAN_MAKE_SHORT](../../../../raw/postgres-17/src/include/varatt.h#L257-L262)
- [indextuple.c#index_form_tuple-compression](../../../../raw/postgres-17/src/backend/access/common/indextuple.c#L116-L138)
- [heaptoast.h#TOAST_INDEX_TARGET](../../../../raw/postgres-17/src/include/access/heaptoast.h#L63-L68)
- [htup_details.h#MaxHeapTupleSize](../../../../raw/postgres-17/src/include/access/htup_details.h#L553-L563)
- [pg_type.h#TYPSTORAGE_EXTENDED](../../../../raw/postgres-17/src/include/catalog/pg_type.h#L307-L310)
- [index.c#ConstructTupleDescriptor-attstorage](../../../../raw/postgres-17/src/backend/catalog/index.c#L353-L360)
- [analyze.c#update_attstats-stainherit](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1647)
- [system_views.sql#pg_stats](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L189-L211)
- [acl.c#column_privilege_check](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L2538-L2569)
- [acl.c#acldefault](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L813-L821)
- [aclchk.c#pg_class_aclmask_ext](../../../../raw/postgres-17/src/backend/catalog/aclchk.c#L3396-L3412)
- [aclchk.c#grant-refuses-indexes](../../../../raw/postgres-17/src/backend/catalog/aclchk.c#L1858-L1863)
- [pg_attribute.h#attstattarget](../../../../raw/postgres-17/src/include/catalog/pg_attribute.h#L168-L176)
- [analyze.c#examine_attribute](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1019-L1030)
- [nbtsort.c#_bt_blnewpage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L605-L629)
- [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L907-L923)
- [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L214)
- [nbtree.h#BTGetTargetPageFreeSpace](../../../../raw/postgres-17/src/include/access/nbtree.h#L1138-L1147)
- [nbtsort.c#page-boundary](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L874-L935)
- [nbtsort.c#_bt_sortaddtup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L713-L735)
- [nbtree.h#fillfactors](../../../../raw/postgres-17/src/include/access/nbtree.h#L199-L202)
- [nbtsort.c#maxpostingsize](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1304-L1305)
- [nbtdedup.c#_bt_dedup_start_pending](../../../../raw/postgres-17/src/backend/access/nbtree/nbtdedup.c#L432-L474)
- [analyze.c#index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663)
- [system_views.sql#pg_stat_all_tables](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L670-L703)
- [nbtree.c#btvacuumpage-counting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1347-L1362)
- [nbtree.c#btvacuumcleanup](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L870-L920)
- [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3073-L3099)
- [analyze.c#index-statistics-write](../../../../raw/postgres-17/src/backend/commands/analyze.c#L588-L602)
- [analyze.c#compute_index_stats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L845-L884)
- [execnodes.h#IndexInfo](../../../../raw/postgres-17/src/include/nodes/execnodes.h#L183-L193)
- [autovacuum.c#analyze-reloptions](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3011-L3017)
- [autovacuum.c#analyze-threshold](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3063-L3095)
- [pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-17/src/include/pgstat.h#L399-L429)
- [pg_proc.dat#pg_get_expr](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L8219-L8220)
- [ruleutils.c#pg_get_expr_ext](../../../../raw/postgres-17/src/backend/utils/adt/ruleutils.c#L2648-L2662)
- [nodeSubplan.c#ExecScanSubPlan-EXISTS](../../../../raw/postgres-17/src/backend/executor/nodeSubplan.c#L293-L296)
- [indxpath.c#check_index_predicates](../../../../raw/postgres-17/src/backend/optimizer/path/indxpath.c#L3244-L3350)
- [nbtsort.c#_bt_load-grouping](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1314-L1316)
- [nbtutils.c#_bt_keep_natts_fast](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L4875-L4905)
- [datum.c:271](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L271)
- [dbsize.c#calculate_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L301-L371)
- [pg_class.h#generated-header](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L21-L22)
- [pg_index.h#generated-header](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L21-L22)
- [catalog/Makefile#genbki](../../../../raw/postgres-17/src/include/catalog/Makefile#L132-L143)
- [utils/Makefile#Gen_fmgrtab](../../../../raw/postgres-17/src/backend/utils/Makefile#L47-L53)
- [btreefuncs.c#GetBTPageStatistics](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L108-L194)
- [pageinspect--1.8--1.9.sql#bt_page_stats](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L87-L124)
- [pgstattuple--1.4.sql#pgstatindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4.sql#L19-L31)
- [btree_index.sql#deduplication-tests](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L186-L213)
- [index_including.sql#statistics-tests](../../../../raw/postgres-17/src/test/regress/sql/index_including.sql#L150-L158)
- [acl.c#aclmask](../../../../raw/postgres-17/src/backend/utils/adt/acl.c#L1388-L1445)
- [gram.y#DoStmt](../../../../raw/postgres-17/src/backend/parser/gram.y#L9037)
- [initdb.c#load_plpgsql](../../../../raw/postgres-17/src/bin/initdb/initdb.c#L1974-L1977)
- [pgstat.c#pgstat_force_next_flush](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L700-L708)
- [postgres.c#idle-stats-flush](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L4634-L4705)
- [pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L584-L600)
- [pgstat.c#flush-intervals](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L117-L122)
- [pgstat_relation.c#AtEOXact_PgStat_Relations](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L560-L574)
- [pgstat_relation.c#pgstat_report_analyze](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L289-L337)
- [pgstat_relation.c#pgstat_relation_flush_cb](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L857-L860)
- [pgstat.c#pgstat_clear_snapshot](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L786-L800)
- [pgstatfuncs.c#snapshot-and-flush-functions](../../../../raw/postgres-17/src/backend/utils/adt/pgstatfuncs.c#L1680-L1695)
- [guc_tables.c#stats_fetch_consistency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4966-L4974)
- [stats.sql#forced-flush](../../../../raw/postgres-17/src/test/regress/sql/stats.sql#L101-L102)
- [pg_amproc.dat#bpchar_ops-equalimage](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L31-L33)
- [index.c#pattern-ops-collation-check](../../../../raw/postgres-17/src/backend/catalog/index.c#L826-L849)
- [btreefuncs.c#bt_metap-allequalimage](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L916-L921)
- [numeric.c#bigint-out-of-range](../../../../raw/postgres-17/src/backend/utils/adt/numeric.c#L4546-L4549)
- [installation.sgml#VPATH](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L427-L432)
- [installation.sgml#meson-setup](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L2012-L2025)
- [nbtsplitloc.c#split-policy](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L278-L335)
- [nbtsplitloc.c#single-value-strategy](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L406-L416)
- [nbtsplitloc.c#_bt_strategy-single-value](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsplitloc.c#L1020-L1033)
- [nbtutils.c#_bt_allequalimage-debug](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5172-L5180)
- [nbtutils.c#_bt_allequalimage-INCLUDE](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5144-L5147)
- [installation.sgml#ICU-default](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L170)
- [pg_statistic_ext_data.h:35](../../../../raw/postgres-17/src/include/catalog/pg_statistic_ext_data.h#L35)
- [pg_statistic_ext_data.h:57](../../../../raw/postgres-17/src/include/catalog/pg_statistic_ext_data.h#L57)
- [analyze.c#analyze_rel-passes](../../../../raw/postgres-17/src/backend/commands/analyze.c#L246-L259)
- [analyze.c#BuildRelationExtStatistics-call](../../../../raw/postgres-17/src/backend/commands/analyze.c#L604-L606)
- [extended_stats.c#BuildRelationExtStatistics](../../../../raw/postgres-17/src/backend/statistics/extended_stats.c#L111-L114)
- [extended_stats.c#statext_store](../../../../raw/postgres-17/src/backend/statistics/extended_stats.c#L790-L791)
- [system_views.sql#pg_statistic_ext_data-revoke](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L382-L383)
- [json.c#composite_to_json](../../../../raw/postgres-17/src/backend/utils/adt/json.c#L546-L579)
- [json.c#datum_to_json-bool](../../../../raw/postgres-17/src/backend/utils/adt/json.c#L212-L221)
- [pg_operator.dat#json-arrow-text](../../../../raw/postgres-17/src/include/catalog/pg_operator.dat#L3160-L3162)
- [pg_proc.dat#json_object_field_text](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L9078-L9081)
- [bool.c#parse_bool_with_len](../../../../raw/postgres-17/src/backend/utils/adt/bool.c#L36-L58)
- [bool.c#boolin](../../../../raw/postgres-17/src/backend/utils/adt/bool.c#L126-L150)
- [analyze.c#std_typanalyze-minrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1894)
- [system_views.sql#pg_stats_ext](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L301-L307)
- [system_views.sql#pg_stats-inherited](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L189-L194)
- [vacuum.c#ExecVacuum-vacuum](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L450-L451)
- [vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650)
- [autovacuum.c#autovacuum_do_vac_analyze](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3120-L3147)
- [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1450-L1457)
- [regress.sgml#contrib-suites](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L171-L195)
- [autovacuum.c#anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3068-L3076)
- [autovacuum.c#doanalyze](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095)
- [guc_tables.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3367-L3375)
- [guc_tables.c#autovacuum_analyze_scale_factor](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3906-L3914)
- [system_views.sql#n_mod_since_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L689)
- [pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L331-L338)
- [itemptr.h#ItemPointerData](../../../../raw/postgres-17/src/include/storage/itemptr.h#L36-L40)
- [sysattr.h#SelfItemPointerAttributeNumber](../../../../raw/postgres-17/src/include/access/sysattr.h#L21)
- [nbtree.c#btbulkdelete](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L820-L832)
- [nbtpage.c#_bt_pagedel](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L1801-L1815)
- [analyze.c#totalindexrows](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L662)
- [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2809-L2830)
- [index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3582-L3600)
- [installation.sgml#ICU_CFLAGS](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L184-L193)
- [installation.sgml#--with-blocksize](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L1472-L1482)
- [nbtsort.c#btbuild-parallel](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L389-L392)
- [index.c#index_concurrently_build](../../../../raw/postgres-17/src/backend/catalog/index.c#L1533-L1539)
- [indexcmds.c#DefineIndex-concurrent-build](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L1682)
- [indexcmds.c#ReindexRelationConcurrently-build](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L4009)
- [pg_class.h#relkind](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L164-L173)
- [vacuum.c#expand_vacuum_rel-partitions](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L963-L982)
- [pg_proc.dat#pg_control_init](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L11989-L11997)
- [pg_controldata.c#pg_control_init](../../../../raw/postgres-17/src/backend/utils/misc/pg_controldata.c#L204)
- [installation.sgml#--enable-debug](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L1530-L1540)
- [pageinspect--1.8--1.9.sql#bt_metap](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L73-L82)
- [initdb.sgml#--locale](../../../../raw/postgres-17/doc/src/sgml/ref/initdb.sgml#L281-L291)
- [installation.sgml#SIP](../../../../raw/postgres-17/doc/src/sgml/installation.sgml#L3611-L3618)
- [guc_tables.c#autovacuum](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1450-L1453)
- [guc_tables.c#fsync](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1097-L1100)
- [guc_tables.c#shared_buffers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2262-L2265)
- [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2466-L2469)
- [guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3410-L3413)
- [guc_tables.c#client_min_messages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4777-L4780)
- [guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2071-L2074)
- [gram.y#IndexStmt](../../../../raw/postgres-17/src/backend/parser/gram.y#L8093-L8095)
- [pageinspect--1.8--1.9.sql#bt_page_items](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L109-L118)
- [amcheck--1.0--1.1.sql#bt_index_check](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.0--1.1.sql#L12-L28)
- [verify_nbtree.c#metapage-equalimage-check](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L380-L396)
- [indexcmds.c#ReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2804-L2829)
- [index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3583-L3597)
- [mainloop.c:376](../../../../raw/postgres-17/src/bin/psql/mainloop.c#L376)
- [mainloop.c#die_on_error](../../../../raw/postgres-17/src/bin/psql/mainloop.c#L587-L594)
- [psql-ref.sgml#Exit-Status](../../../../raw/postgres-17/doc/src/sgml/ref/psql-ref.sgml#L627-L636)
- [guc_tables.c#listen_addresses](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4437-L4441)
- [guc_tables.c#port](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2394-L2397)
- [guc_tables.c#logging_collector](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1641-L1644)
- [guc_tables.c#log_min_messages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4873-L4877)
- [guc_tables.c#unix_socket_directories](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4426-L4430)
- [relcache.c#RelationSetNewRelfilenumber-reltuples](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3951-L3952)
- [index.c#index_update_stats-sentinel](../../../../raw/postgres-17/src/backend/catalog/index.c#L2835-L2836)
- [postmaster.c#process_pm_shutdown_request-fast](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L2266-L2305)
- [postmaster.c#process_pm_shutdown_request-immediate](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L2307-L2342)
- [xlog.c#ShutdownXLOG](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L6580-L6621)
- [xlogrecovery.c#not-properly-shut-down](../../../../raw/postgres-17/src/backend/access/transam/xlogrecovery.c#L922-L949)
- [pg_ctl.c#do_stop](../../../../raw/postgres-17/src/bin/pg_ctl/pg_ctl.c#L1015-L1065)
- [miscinit.c#UnlinkLockFiles](../../../../raw/postgres-17/src/backend/utils/init/miscinit.c#L1170-L1194)
- [pqcomm.c#RemoveSocketFiles](../../../../raw/postgres-17/src/backend/libpq/pqcomm.c#L846-L861)
- [reloptions.c#autovacuum_analyze_threshold](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L243-L251)
- [reloptions.c#autovacuum_analyze_scale_factor](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L416-L425)
- [nbtree.h#BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1146-L1150)
- [execIndexing.c#partial-predicate-skip](../../../../raw/postgres-17/src/backend/executor/execIndexing.c#L384-L386)
- [pg_statistic.h#stawidth](../../../../raw/postgres-17/src/include/catalog/pg_statistic.h#L41-L50)
- [startup.c#single-query-action](../../../../raw/postgres-17/src/bin/psql/startup.c#L377-L386)
- [elog.c#errfinish-rethrow](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L515-L546)
- [postgres.c#PostgresMain-error-handler](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L4446-L4485)
- [pl_exec.c#exec_stmt_block-catch](../../../../raw/postgres-17/src/pl/plpgsql/src/pl_exec.c#L1829-L1839)
- [elog.c#error_severity](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L3667-L3705)
- [elog.c:3194](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L3194)
- [elog.c#EVALUATE_MESSAGE](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L989-L1018)
- [initdb.c#lc_messages-default](../../../../raw/postgres-17/src/bin/initdb/initdb.c#L2424-L2425)
- [initdb.c#lc_messages-conf](../../../../raw/postgres-17/src/bin/initdb/initdb.c#L1292-L1293)
- [elog.c#check_log_of_query](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L2727-L2743)
- [elog.c#STATEMENT-line](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L3276-L3284)
- [elog.c#errhidestmt](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L1406-L1420)
- [guc_tables.c#log_min_error_statement](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4884-L4891)
- [guc_tables.c#log_line_prefix](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4095-L4101)
- [pg_ctl.c#start_postmaster-command](../../../../raw/postgres-17/src/bin/pg_ctl/pg_ctl.c#L489-L494)
- [pg_ctl.c#wait_for_postmaster_start](../../../../raw/postgres-17/src/bin/pg_ctl/pg_ctl.c#L592-L699)
- [backend_startup.c#CAC_STARTUP](../../../../raw/postgres-17/src/backend/tcop/backend_startup.c#L265-L278)
- [postgres.c#administrator-command-FATAL](../../../../raw/postgres-17/src/backend/tcop/postgres.c#L3315-L3318)
- [elog.c#EmitErrorReport-timestamp-reset](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L1687-L1702)
- [elog.c#get_formatted_log_time](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L2654-L2686)
- [elog.c#log_line_prefix-%p](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L2954-L2958)
- [elog.c#log_line_prefix-%m](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L2989-L2998)
- [elog.c#send_message_to_server_log-prefix](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L3186-L3194)
- [elog.c#append_with_tabs](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L3719-L3729)
- [vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122)
- [procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815)
- [procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902)
- [twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26)
- [vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052)
- [vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L659-L663)
- [vacuum.c#vacuum-lockmode](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2049-L2056)
- [vacuum.c#skip-lock-not-available](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L828-L860)
- [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470)
- [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642)
- [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653)
- [elog.c#should_output_to_client](../../../../raw/postgres-17/src/backend/utils/error/elog.c#L247-L264)
- [system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L878-L885)
- [system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017)
- [system_views.sql#pg_prepared_xacts](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L421-L427)
- [pgstatindex.c#page-classes](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L295-L320)

## Navigation

- [v17/index](../../index.md)
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [versions](../../../versions.md)
