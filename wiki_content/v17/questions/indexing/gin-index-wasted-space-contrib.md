---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# Measuring Wasted and Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [Plan review](#plan-review)
  - [Revised plan](#revised-plan)
  - [Deviations from the brief, and why](#deviations-from-the-brief-and-why)
  - [Why no single contrib function suffices](#why-no-single-contrib-function-suffices)
  - [The three waste classes, from GIN's own definitions](#the-three-waste-classes-from-gins-own-definitions)
  - [The procedure](#the-procedure)
  - [The declarations, filed before the run](#the-declarations-filed-before-the-run)
  - [The census statement](#the-census-statement)
  - [The guarded census statement](#the-guarded-census-statement)
  - [The derived-arithmetic statements](#the-derived-arithmetic-statements)
  - [The measurement protocol](#the-measurement-protocol)
  - [Adversarial and acceptance cases](#adversarial-and-acceptance-cases)
  - [The bloat percentage column](#the-bloat-percentage-column)
  - [Four cross-checks](#four-cross-checks)
  - [The fixtures](#the-fixtures)
  - [What the census meant against REINDEX](#what-the-census-meant-against-reindex)
  - [The maintenance step, measured](#the-maintenance-step-measured)
  - [The auto-analyze stand-in, measured](#the-auto-analyze-stand-in-measured)
  - [The simulated auto-analyze census](#the-simulated-auto-analyze-census)
  - [The failure boundary is a straight line](#the-failure-boundary-is-a-straight-line)
  - [Counting entry tuples, and what that fixes](#counting-entry-tuples-and-what-that-fixes)
  - [Whole-page waste is not a lower bound](#whole-page-waste-is-not-a-lower-bound)
  - [Entry-page slack is growth room, not waste](#entry-page-slack-is-growth-room-not-waste)
  - [The pending-list lifecycle, measured end to end](#the-pending-list-lifecycle-measured-end-to-end)
  - [Deleted pages need the horizon to move before they count](#deleted-pages-need-the-horizon-to-move-before-they-count)
  - [Concurrency: a census of a busy index is a mixed-instant reading](#concurrency-a-census-of-a-busy-index-is-a-mixed-instant-reading)
  - [Cost of the census](#cost-of-the-census)
  - [Privileges](#privileges)
  - [Refusals, silent answers, and other traps](#refusals-silent-answers-and-other-traps)
  - [Timeouts and GUC scope](#timeouts-and-guc-scope)
  - [Outside the protocol: the four statements on PostgreSQL 12](#outside-the-protocol-the-four-statements-on-postgresql-12)
  - [What this pass removed, and why](#what-this-pass-removed-and-why)
  - [Reading rules](#reading-rules)
- [Measurement Script](#measurement-script)
  - [How to use it](#how-to-use-it)
  - [Prerequisites](#prerequisites)
  - [Where the results land](#where-the-results-land)
  - [The last run](#the-last-run)
  - [The PostgreSQL 17.11 leg](#the-postgresql-1711-leg)
  - [The PostgreSQL 12.2 leg](#the-postgresql-122-leg)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Follow AGENTS.md, in PostgreSQL 17.

Question: Design an accurate procedure for measuring wasted/reclaimable bytes in a
GIN index in PostgreSQL 17 using contrib extensions.

Deliverable: one type: question page under wiki/v17/questions/indexing/, with the
question restated verbatim, the answer inline, full front matter, Contents,
Context Reviewed, Evidence Map, Open Questions, Source References, and Navigation.

Implement and validate this plan:

1. Establish from source why no single contrib function suffices: pgstattuple()
   rejects GIN (pgstattuple.c pgstat_relation), and pgstatginindex() reads only the
   metapage's version / pending_pages / pending_tuples (pgstatindex.c).

2. Define the waste classes from GIN's own source definitions:
   - whole-page waste: GIN_DELETED pages plus all-zero (PageIsNew) pages, both
     recyclable per GinPageIsRecyclable and FSM-recorded as BLCKSZ-1 by
     RecordFreeIndexPage; reusable only within the index because ginvacuumcleanup
     never truncates;
   - intra-page slack on live pages: pd_upper - pd_lower, matching
     GinDataLeafPageGetFreeSpace = PageGetExactFreeSpace, gated on
     ginVersion = 2 because pre-9.4 posting-tree pd_lower is untrustworthy;
   - pending-list pages: deferred work, reported separately, never counted as
     waste (a flush merges entries and can grow the index).

3. The procedure: install pageinspect + pgstattuple + pg_freespacemap; VACUUM the
   table (or core gin_clean_pending_list()) to settle state and refresh metapage
   stats; record pg_relation_size(main) and gin_metapage_info(get_raw_page(idx, 0));
   scan blocks 1..relpages-1 reading each raw page once and feeding the same bytea
   to page_header() and gin_page_opaque_info() via LATERAL, classifying pages by
   the flags array (NULL row = new page); report whole_page_waste,
   live_page_slack_bytes, and pending_bytes against the size denominator; cross-
   check whole-page waste with pg_freespace() = 8191 counts and VACUUM VERBOSE
   pages_free, and page-type counts against gin_metapage_info's
   n_entry_pages / n_data_pages.

4. Validate on an isolated exact-pin 17.11 server (reuse
   .wiki-runtime/tmp/pstate/install/ if still present): build GIN fixtures with
   churn, deleted pages, a populated pending list, and an empty control; run the
   full procedure; use REINDEX INDEX before/after pg_relation_size as ground truth
   for filesystem-reclaimable bytes and report how the contrib estimate bounds it.

5. Document caveats with citations: superuser-only raw-page functions versus the
   pg_stat_scan_tables grant for pgstatginindex added in pgstattuple 1.5, invalid-index and other-
   session-temp refusals, non-atomic scan races, entry-page ItemIdData overhead
   making slack an upper bound, gin_leafpage_items' exact flag requirement, and
   the absence of a GIN verifier in v17 contrib amcheck.

6. Recommend session-scoped statement_timeout and lock_timeout on every
   production-bound statement and tag each with a /* wiki_... */ comment. Anything
   not verified on the live server goes under ## Open Questions. Leave
   verified: false; set verified_by_agent only after re-checking every claim.
   Update wiki/index.md, wiki/v17/index.md, wiki/versions.md, append to
   wiki/log.md, and run scripts/wiki_lint.

Prompt corrections, agreed before drafting: the original first line read
`Follow AGENTS.md. in PostgreSQL 17.`, whose stray period left `in PostgreSQL 17`
as a lowercase fragment; and item 5 read `the pg_stat_scan_tables grant for
pgstatginindex 1.5`, where 1.5 is the *pgstattuple extension* version that added
the `pgstatginindex(regclass)` grant, not a version of the function. Everything
else is verbatim, including the `pg_freespace() = 8191` premise in item 3, which
the answer corrects on evidence.

Review prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md, in PostgreSQL 17. Review the question: Measuring Wasted and
> Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
> (unverified).

The original read `follow agents.md , in postgresql 17 , review question : ...`:
`agents.md` for AGENTS.md, lowercase `postgresql`, and a space before each comma
and before the colon. The asker chose a full review — source re-verification plus
a rebuilt server and re-measurement — with corrections made in place, and asked
that the stale sandbox pointer be corrected and the sandbox rebuilt.

What the review did: re-read every source citation on this page against the pinned
checkout (119 distinct file-and-range citations at review time, 121 when it
finished; the open-questions pass below took that to 141 over 43 files),
rebuilt PostgreSQL 17.11 from `raw/postgres-17/` because the original sandbox had
been deleted, republished the fixtures as SQL so the numbers are reproducible,
re-ran every measurement, and added a physical standby to test the one refusal the
first run could not reach. See [The fixtures](#the-fixtures) for what reproduced
and what did not.

Second follow-up prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md, in PostgreSQL 17, for the question: Measuring Wasted and
> Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
> (unverified). Review the open questions.

The original read `follow agents.md , in postgresql 17 , for question : ... ,
review open questions`: `agents.md` for AGENTS.md, lowercase `postgresql`, a space
before each comma and before the colon, and no sentence capitalisation. The asker
chose to attack the open questions with measurements rather than audit them on
paper, and ruled out the two expensive probes — no second build at a different
`BLCKSZ`, and no repeated crash runs.

What this pass did, on the same pin and the then-retained `.wiki-runtime/tmp/ginw2/`
sandbox: **three of the eleven open questions closed, six narrowed, two untouched
by request**. The page's whole fixture corpus was rebuilt from the published SQL in
two virgin databases and reproduced byte for byte; a five-point churn sweep mapped
the payload model's failure boundary to a straight line; an entry-tuple probe built
out of `pd_lower` was found to measure dead keys exactly; a second index was found
that breaks the waste-is-a-lower-bound claim; the flush-growth question got a
mechanism out of the FSM's upper levels; a concurrent VACUUM was shown to defeat
every cross-check the page recommends; and the eviction claim was corrected — a
census does not evict a hot working set, it strips one round of its usage count.
Fourteen more fixtures were scored, twenty new citations were added, and all 141
of the page's file-and-range citations were re-checked for in-bounds line ranges.

Third follow-up prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md, in PostgreSQL 17, for the question: Measuring Wasted and
> Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
> (unverified). Add a follow-up: make sure that statement runs on v12, and run all
> tests on v12 and v17.

The original read `follow agents.md , in postgresql 17 , for question : ... , add
follow up: make sure that statement run on v12 , run all test on v12 and v17`:
`agents.md` for AGENTS.md, lowercase `postgresql`, a space before each comma and
before the colon, `for question :` for `for the question:`, `add follow up:` for
`add a follow-up:`, `that statement run` for `that statement runs`, and `all test`
for `all tests`. Three scoping answers were taken before drafting: **all four**
published statements had to run on 12.2 (not just the census), the **whole** corpus
had to be re-run on both majors rather than a portable subset, and both sandboxes
were to be deleted once the page was filed.

What this pass did: built 12.2 and 17.11 from this repo's two pins by out-of-tree
builds, ported all four statements (**three edits**, one of which is not cosmetic),
and re-ran the entire measurement programme on both servers — 27 scored fixtures,
the pending-list lifecycle, the three-VACUUM horizon sequence, a held
`REPEATABLE READ` snapshot, four concurrency cases, plain and concurrent rebuilds
with and without load, privileges, refusals, timeouts, a physical standby, crash
and hand-zeroed pages, `pg_buffercache` eviction, and the cost measurements.
**26 of the 27 fixtures came out byte-identical on the two majors**, and so did every
lifecycle, horizon, flush, privilege, timeout and standby reading. The differences
are concentrated in three places: what `pageinspect` does with an all-zero page,
which refusals exist, and what a rebuild costs when the build spills. Two of the
page's headline claims were corrected on evidence — `waste + slack` is not an upper
bound when the dead-key population is large, and a census *does* evict a hot working
set once the target exceeds the cache — and open question 7 now has a mechanism.

Fourth follow-up prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md, in PostgreSQL 17, for the question: Measuring Wasted and
> Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
> (unverified). Add to the census statement a bloat percentage column based on
> information the statement already calculates.

The original read `follow agents.md, in postgresql 17, for question: ... , add to
the census statement a bloat percentage column based on the already calculated
information on the statement`: `agents.md` for AGENTS.md, lowercase `postgresql`,
`for question:` for `for the question:`, a space before the comma after the page
title, no sentence capitalisation, one comma splice where a second sentence belongs,
and `based on the already calculated information on the statement` for `based on
information the statement already calculates`; the restatement also adds the
`(unverified)` suffix the page title carries. Three scoping answers were taken
before drafting: the column reports **`waste + slack`** — the quantity the scoring
tables below already print as `waste+slack %` — rather than the honest-signal subset
or the everything-but-payload form; it had to be **verified on 12.2 as well as
17.11**; and both sandboxes were to be deleted once the page was filed.

What this pass did: added exactly one column, `bloat_pct`, as a four-line hunk in
the census statement's `SELECT` list and nothing else. The column was scored against
`REINDEX INDEX` on the seven published fixtures, rebuilt from this page's own
fixture SQL on a 17.11 server and on a 12.2 server; it reproduces the `waste+slack %`
column of the scoring table exactly, is **identical on both majors** for all seven,
and costs nothing (`EXPLAIN (ANALYZE, BUFFERS)` reads `shared hit=7568` with and
without it). It also required two of the page's own rules to be rewritten rather
than quietly contradicted — "never publish their sum as bloat" was one of them —
because a healthy index reads 48% to 50% on this column while a rebuild returns
nothing.

Fifth follow-up prompt, corrected with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, review the plan for the question:
> Measuring Wasted and Reclaimable Bytes in a GIN Index With Contrib Extensions
> on PostgreSQL 17 (unverified).

The correction fixes capitalization, spacing around punctuation, and the missing
articles in the request; the page title is unchanged. The original six-step plan
above remains the record of the brief. The 2026-09-05 review and revised plan are
filed under Answer. This pass reviewed source and the published SQL; it did not
repeat the historical database experiments or re-verify every earlier claim, so
the page's agent verification is `not yet`.

Sixth follow-up prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, review the question: Measuring Wasted and
> Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
> (unverified).

The original read `follow agents.md, in postgresql 17 , review question: # Measuring
Wasted and Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
(unverified)`: `agents.md` for AGENTS.md, lowercase `postgresql`, a space before the
second comma, `review question:` for `review the question:`, a pasted `# ` heading
marker before the title, and no sentence capitalisation or terminal period. The
asker chose the middle of three scopes: re-verify every citation and source claim
against the pin, rebuild 17.11 out of tree, implement the revised plan's query
guards and run its acceptance cases (open questions 17 through 19), without
re-running the whole 27-fixture corpus; corrections in place; the sandbox deleted
once the page is filed.

What this pass did: re-read all 422 citations on the page (202 distinct
file-and-line ranges over 60 files) against the pinned checkout, finding every
range in bounds and every cited claim supported; built 17.11 from
`raw/postgres-17/` out of tree; rebuilt the seven published fixtures and the
pending-list fixture from this page's own SQL, which returned the filed figures
byte for byte a fourth time; implemented the guards as
[The guarded census statement](#the-guarded-census-statement); and ran the
revised plan's acceptance cases, reported in
[Adversarial and acceptance cases](#adversarial-and-acceptance-cases):
five hand-corrupted index files, a `pg_stat_scan_tables`-only role, an invalid
index, both temporary-index cases, a held `REPEATABLE READ` snapshot, two bypassed
index cleanups, a concurrent VACUUM, a concurrent `REINDEX CONCURRENTLY`, an
insert stream, the seven rebuilds, and one rebuild at three memory budgets.

Seventh follow-up prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, on the question: Measuring Wasted and
> Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
> (unverified), implement the proposal fixes for the open questions and run all
> tests.

The original read `follow agents.md, in postgresql 17, on question: # Measuring
Wasted and Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
(unverified) , implement the proposal fixes for open questions , run all tests.`:
`agents.md` for AGENTS.md, lowercase `postgresql`, no sentence capitalisation, a
pasted `# ` heading marker before the title, a space before each of the two later
commas, `on question:` for `on the question:`, `for open questions` for `for the
open questions`, and a comma splice where `and` belongs. Three scoping answers were
taken before drafting: **open questions 17 through 19 only** — the three the
2026-09-07 pass left as named implementation work — the **page's own measurement
programme** as the test scope, without PostgreSQL's regression suite and without a
second `BLCKSZ` build, and the sandbox deleted once the page is filed.

What this pass did: derived every remaining literal in the published statements and
added a layout probe that *measures* the page-format constants on the running build
([The derived-arithmetic statements](#the-derived-arithmetic-statements)); replaced
after-the-fact detection with an enforced measurement protocol and measured both
what it covers and the one hole it cannot close
([The measurement protocol](#the-measurement-protocol)); and ran the acceptance
cases the previous pass could not reach — the wraparound failsafe, four real
crashes, and three new corruption shapes — plus a reproduction of the published
fixture programme
([Adversarial and acceptance cases](#adversarial-and-acceptance-cases)). The 17.11 server
was rebuilt out of tree from the pin for all of it.

Eighth follow-up prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, review the question: Measuring Wasted and
> Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
> (unverified). Update the tests based on the changes from the common concept page,
> and update or remove all tests that do not follow Mandatory GIN Bloat Tests
> (unverified).

The original read `follow agents.md, in postgresql 17, review question: # Measuring
Wasted and Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
(unverified) , update tests based on the changes from common-concept, update or
remove all tests that aren't following # Mandatory GIN Bloat Tests (unverified)`:
`agents.md` for AGENTS.md, lowercase `postgresql`, `review question:` for `review
the question:`, a pasted `# ` heading marker before each of the two page titles,
`from common-concept` for `from the common concept page`, `aren't following` for
`do not follow`, and no sentence capitalisation. Four scoping answers were taken
before any edit: the deliverable is a **full re-run with a published measurement
script**, not a paper re-port; tests that cannot be made to conform are **removed**
rather than relabelled; **all three** missing coverage fixtures are added; and the
sandbox is deleted once the page is filed.

What this pass did: built 17.11 out of tree from the pin, filed the declared kind of
every published column **before** any fixture existed, and re-ran the whole
programme under the five phases of
[Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md) -
19 scored fixtures plus 6 coverage fixtures, the simulated auto-analyze census, the
locked decide pass, a measured `REINDEX INDEX` oracle per fixture, the four
cross-checks, eight corruption shapes, four concurrency cases, a standby and the
privilege, refusal, timeout and cost cases. Every number below comes from that one
run, and the script that produced it is filed in full under
[Measurement Script](#measurement-script). Six fixture families and four whole
sections were **removed** because they cannot be re-run from anything this page
carries; see [What this pass removed, and why](#what-this-pass-removed-and-why).

Ninth follow-up prompt, corrected and restated with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, review the question: Measuring Wasted and
> Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17
> (unverified).

The original read `follow agents.md, in postgresql 17, review :
gin-index-wasted-space-contrib.md`: `agents.md` for AGENTS.md, lowercase
`postgresql`, a space before the colon and two after it, no sentence
capitalisation or terminal period, and the page named by its filename rather
than its title. Four scoping answers were taken before any edit: the scope is
**source re-verification plus a re-run of the page's published script**, not a
paper review; defects are **corrected in place**; and the sandbox is deleted once
the page is filed.

What this pass did: re-read all **605** source citations the page carried at review
time (**284** distinct file-and-line ranges over **79** files; **607 over 283** when
this pass finished) against the pin, then rebuilt
17.11 out of tree and ran the published script end to end **twice** - once as
published, once after the one script change this review made. **Every scored
number reproduced**: the 19-fixture page census, byte and percentage tables, the
oracle, the payload model, the baseline phase, the pending-list lifecycle, the
horizon sequence, the simulated census, the privilege, refusal, standby and
corruption cases all came out identical to the filed text, and the two runs
agreed with each other. Eight filed items did not survive, and they are the
edits below: a miscounted metapage cross-check, an f8 VACUUM sequence attributed
to `f5`, a standby block count from a different fixture, a shortfall list of four
described as five, four timing figures, and a `PageAddItem` credited to
`entryPreparePage`. The script change closes a `MANDATORY Measurement Script`
hole rather than a claim: the *after `REINDEX`* entry-tuple column was published
without a stage that produces it, so the probe now runs a second pass after the
oracle (`probe_after`), and it returns the filed dead-key counts exactly.

Tenth follow-up prompt, corrected with the asker's agreement:

> Follow AGENTS.md. In PostgreSQL 17, remove the invalid test from the question
> Measuring Wasted and Reclaimable Bytes in a GIN Index With Contrib Extensions on
> PostgreSQL 17 (unverified), and re-run all tests.

Two scoping answers were taken before any edit. The invalid test is **`f9c_cleanup`
alone**: the fixture that ran a `VACUUM` with index cleanup switched off, which
[Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md)
stopped requiring on 2026-09-24 and no longer declares as an exception to its rule
that no fixture may defeat the maintenance step. The rest of the script was **not**
brought onto that rule; see open question 24. And "all tests" **includes the
PostgreSQL 12.2 section**, which gained a script of its own.

What this pass did: removed `f9c_cleanup` in both its spellings, and every sentence
that still treated a `VACUUM` without index cleanup, the wraparound failsafe
included, as a protocol requirement. It fixed the published script where a run on a
second platform showed it wrong:

- `dd oflag=append`, which BSD `dd` rejects, so the appended-zero-page case ran
  without its zero pages;
- a corrupt-stage probe that never passed its `:tbl` destination, so the `s5` and
  `s7` probe results the page quoted were not produced by the filed script's last
  run;
- a teardown check that cannot fire on macOS;
- five kinds of numbers the page reported but no stage wrote to a file: the
  millisecond timestamps, the stage log, every census the build and churn phases
  stored, the census of the rebuilt indexes, and the distinct keys two tables hold.

It added a `portability` stage to the 17.11 script and a 12.2 script that runs the
same battery, and ran both legs end to end from empty sandboxes on Darwin 27 arm64,
this page's first platform other than Linux x86_64. A baseline pass of the filed
script, unchanged, ran first on the same machine.

Every scored cell of the 2026-09-16 filing reproduced in the recorded run and in the
baseline pass, so the headline verdicts stand: 17 of 19 lower bounds held, 19 of 19
upper bounds. One earlier pass the same day moved one fixture by one page, through
VACUUM's own index-vacuum bypass (open question 23). The new reports corrected one
filed number, `m1_pair`'s as-built `reltuples`, and the recount corrected two more:
the payload model's "within 3.2% on ten" fixtures, which is eleven, and the decide
pass's "28 GIN indexes and 15,201 blocks", which are the sweep stage's counts after
the rebuilds. The 12.2 leg
confirmed the section's measurements and corrected three of its claims: the
invalid-index refusal is not v17-only, because it was back-patched and reached the
12 branch in 12.17; the difference on a short `bytea` belongs to `page_header`
alone; and three "earliest tag" citations named a release tag rather than the first
beta.

Version scope, stated once: this page may cite only `raw/postgres-17/`, so every
12.2 statement below rests on exact-pin execution against a 12.2 server built from
this repo's v12 pin, plus commit history. No v12 source file is cited, and none of
the 12.2 findings should be read as v12 source analysis. Master commits are read in
either checkout; the 12 branch's back-patches only in the v12 checkout, because the
v17 checkout does not carry that branch. The 12.2 leg is **outside** the protocol,
which is a v17 protocol. Since 2026-09-24 it has a script of its own; see
[Outside the protocol: the four statements on PostgreSQL 12](#outside-the-protocol-the-four-statements-on-postgresql-12).

## Answer

[Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md) is
where this wiki defines the protocol a [GIN](../../../glossary.md#gin) waste claim is scored under: the five
phases, the settle step and its proof obligations, the maintenance step and the
simulated auto-analyze census, the measurement lock, the [`REINDEX INDEX`](../../../glossary.md#reindex) oracle, the
declare-then-score rule, the four cross-checks and the reading rules. This page is a
consumer of that page. The procedure, the four statements, the fixtures and every
number below are page-local, and the sections that used to define the protocol here
link it instead.

**Every scored number on this page, and every number dated 2026-09-24, was produced
on 2026-09-24** by the two scripts filed under [Measurement Script](#measurement-script).
The 17.11 leg ran the protocol: declarations filed first, then build, baseline, churn
ending in settle → maintenance → census, a decide pass under one [`SHARE ROW EXCLUSIVE`](../../../glossary.md#lock-mode)
transaction, and a measured rebuild. The 12.2 leg re-checked the statements'
portability. The two headline results are unchanged: the page's **upper-bound** claim
held on 19 of 19 scored fixtures and its **lower-bound** claim failed on 2 of 19 - so
`whole_page_waste_pct` is demoted to a level in [Reading rules](#reading-rules), which
is what the protocol's declare-then-score rule requires of a violated bound. Numbers
the page dates to an earlier pass are that pass's record; see open question 22.

Six full passes of the fixture programme have now run on this pin: three on Linux
x86_64 (2026-09-15, and twice on 2026-09-16) and three on Darwin 27 arm64 on
2026-09-24. Today's were a baseline pass of the filed script unchanged, a pass of the
new script before it gained its report files, and the recorded run. The recorded run
and the baseline pass both came out **identical to the 2026-09-16 numbers** in every
scored cell - the same page classes, the same slack bytes, the same `truth_pct`, the
same two violations - on a different operating system, compiler and CPU architecture
with the same [`block_size`](../../../glossary.md#blcksz) and alignment. The middle pass moved one fixture by one
[page](../../../glossary.md#page), through [VACUUM](../../../glossary.md#vacuum)'s own [index-vacuum](../../../glossary.md#index-vacuuming) bypass; see open question 23. What is *not*
stable between runs is timing: the concurrency cases, the lock-timeout cancellations
and the elapsed-time columns move, and in the writer case by a few censuses.

### Short answer

Build a **page census** from [`pageinspect`](../../../glossary.md#pageinspect), and report three separate quantities.
They describe page allocation and free gaps; they do not determine how many bytes
a rebuild will return. GIN can retain entry [tuples](../../../glossary.md#tuple) with empty [posting lists](../../../glossary.md#posting-list), while
a rebuild constructs a new index from the [heap](../../../glossary.md#heap)
([ginvacuum.c:507-558](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L507-L558),
[gininsert.c#ginbuild](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L317-L406)).

| Class | How it is measured | What it means |
|---|---|---|
| Whole-page waste | count of pages whose `gin_page_opaque_info` flags contain `deleted`, plus uninitialized pages, times `block_size` | marked-deleted or uninitialized bytes inside the file; the deleted flag alone does not establish immediate recyclability |
| Live-page slack | `page_header.upper - page_header.lower` summed over live pages, split into entry-tree and [posting-tree](../../../glossary.md#posting-tree) (data) pages | free bytes inside live pages; on entry pages this is mostly *growth room*, not waste |
| [Pending-list](../../../glossary.md#pending-list) bytes | count of pages flagged `list`, times `block_size` | deferred insert work, not waste; flushing it frees pages inside the file and can grow it |

The flags and uninitialized-page result come from `gin_page_opaque_info`;
recycling additionally tests the deletion [transaction ID](../../../glossary.md#transaction-id). Live-page gap and
pending-list definitions come from GIN's page layout and cleanup path
([ginfuncs.c#gin_page_opaque_info](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L98-L171),
[ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829),
[ginblock.h:267-287](../../../../raw/postgres-17/src/include/access/ginblock.h#L267-L287),
[ginfast.c:951-987](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L951-L987),
[ginutil.c#GinNewBuffer](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L294-L335)).

The statement also prints the first two of those as one derived percentage,
`bloat_pct`, because that sum is the quantity every scoring table below uses. Read
it as a page-accounting percentage, with no guaranteed bound on a rebuild: the
never-churned control reads **48.09** while `REINDEX` returns **nothing**, and an
index on an empty table reads **49.80**. See
[The bloat percentage column](#the-bloat-percentage-column).

**Scored on 2026-09-24 under [Mandatory GIN Bloat
Tests](../../common-concepts/mandatory-gin-bloat-tests.md)**, on an isolated 17.11
server, with the declared kind of every column filed before the first fixture
existed and `REINDEX INDEX` as the oracle over **19 fixtures**:
`whole_page_waste + live_page_slack` held as an **upper bound** on 19 of 19, and
`whole_page_waste` alone held as a **lower bound** on only 17 of 19. The two
failures are a flushed pending list (64.64% of the file dead against 58.05%
returned) and the auto-analyze stand-in (52.69% against 45.16%), and both are the
same mechanism: pending-list merges pack an aged index denser than its own rebuild,
so its dead pages overstate what a rebuild returns. The lower-bound column is
therefore a **level** from this revision on, which is what the protocol requires of
a violated bound; see [Whole-page waste is not a lower
bound](#whole-page-waste-is-not-a-lower-bound).

Two qualifications. **The upper bound is not unconditional either**: two earlier
runs broke it, on fixtures whose recipes this page never published — one censused
with a live pending list, one an 800,000-row `jsonb_path_ops` index carrying
819,770 dead entry tuples — and those fixtures were removed rather than reproduced,
so 19 of 19 means "not refuted here" (open question 13). And **the statement needs
three edits to run on PostgreSQL 12**, one of which is not cosmetic: on 12.2 the
census silently classifies an all-zero page as an entry page and reports its waste
as zero. See
[Outside the protocol](#outside-the-protocol-the-four-statements-on-postgresql-12).

### Plan review

**Keep the census approach, but revise the promises in steps 2 through 5.** The
review below uses PostgreSQL 17 pin `786db8dcf168bd9df8f55047337525ac19118b1c`.
It checks the plan against implementation source and audits the filed statement;
the existing experimental tables are historical results, not new measurements.

1. **Steps 4 and 5: remove the promised bounds on REINDEX savings.** A page gap
   measures available space on that page. The line-pointer deduction in
   `PageGetFreeSpace` says how much room an insertion needs; it establishes no
   bound on the size of a different index built later. VACUUM recreates an entry
   tuple even when its posting list becomes empty. Those retained bytes are
   outside `waste + slack`, and adding pending bytes does not account for them.
   Rebuilds scan the heap and insert accumulated entries in batches controlled by
   [`maintenance_work_mem`](../../../glossary.md#maintenance_work_mem). Report the census and measured rebuild reduction as
   distinct outputs, and report failed bound hypotheses as failures
   ([bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L898-L923),
   [ginvacuum.c:507-558](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L507-L558),
   [gininsert.c#ginBuildCallback](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L276-L314),
   [gininsert.c#ginbuild](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L378-L406)).
   The 2026-09-07 pass exercised the suppressed-slack branch by patching a scratch
   index's [metapage](../../../glossary.md#metapage) `ginVersion` to 1: the guarded statement reported
   `unsupported format: version 1` and withheld every slack-derived field, while
   the published statement printed `entry_slack` 19,372 beside a NULL `bloat_pct`.
   A genuine version-1 index with uncompressed posting-tree [leaves](../../../glossary.md#leaf-page) is still
   unproduced, so the `uncompressed_pages` class remains unexercised.

2. **Step 2: distinguish marked-deleted bytes from recyclable bytes.**
   `GinPageIsRecyclable` accepts an uninitialized page immediately. For a deleted
   page, it accepts an invalid deletion transaction ID or requires
   `GlobalVisCheckRemovableXid(NULL, delete_xid)` to succeed. This uses the most
   conservative visibility [horizon](../../../glossary.md#xmin-horizon), the boundary needed to protect older scans.
   The census does not evaluate that predicate. Its `whole_page_waste_bytes`
   therefore measures a page class, not the number of bytes immediately available
   for reuse. `GinNewBuffer` rechecks eligibility even after the [free space map](../../../glossary.md#free-space-map)
   supplies a candidate
   ([ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829),
   [procarray.c#GlobalVisHorizonKindForRel](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1966-L1991),
   [ginutil.c#GinNewBuffer](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L294-L335)).

3. **Step 3: require completed index cleanup before using VACUUM's statistics.**
   `gin_clean_pending_list` calls `ginInsertCleanup`; it does not traverse the
   entire index or refresh `n_entry_pages` and `n_data_pages`. That refresh is in
   `ginvacuumcleanup`. A table VACUUM can skip this callback when index cleanup is
   disabled, including through the table's `vacuum_index_cleanup` option, or when
   the [wraparound failsafe](../../../glossary.md#vacuum-failsafe) disables it. Thus neither a pending-list flush nor a
   successful VACUUM command alone establishes refreshed page counts. Record the
   maintenance outcome and any failsafe warning before interpreting cross-checks
   ([ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1031-L1091),
   [ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L694-L802),
   [vacuum.c:2155-2178](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2155-L2178),
   [vacuumlazy.c:392-401](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L401),
   [vacuumlazy.c:1064-1066](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1064-L1066),
   [vacuumlazy.c:2323-2335](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2335)).
   Since 2026-09-07 the size-bracket snippet and the guarded statement derive the
   [block](../../../glossary.md#block) size from `block_size`; the entry-tuple probe still divides by 8192 and
   subtracts a literal 24-byte header, and the guarded statement's 8-byte
   special-area constant is checked by the metapage decode rather than derived.
   **Closed on 2026-09-08**: the failsafe path was exercised that day, and it is the
   one bypass that VACUUM's own output *does* distinguish
   (`index scan bypassed by failsafe:`), while the census and the metapage still
   cannot tell afterwards; every remaining literal is derived or measured. See
   [The derived-arithmetic statements](#the-derived-arithmetic-statements). The
   2026-09-15 pass removed the failsafe run, and the 2026-09-24 pass removed the
   [`INDEX_CLEANUP OFF`](../../../glossary.md#index_cleanup) fixture that stood in for it, so no test on this page now
   reaches a `VACUUM` that skipped index cleanup. The finding itself still binds the
   settle step: a run must see its index cleanup happen, not assume it
   ([vacuumlazy.c:1064-1066](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1064-L1066)).

4. **Step 3: treat consistency checks as diagnostics.** `get_raw_page` opens the
   named [relation](../../../glossary.md#relation), locks and copies one buffer, then releases both locks before
   returning. Sharing its result between decoders gives one page image; it does
   not give an index-wide snapshot. The filed `census_total_pages = blocks` is
   principally an accounting identity: `generate_series` uses the captured size
   and the `CASE` assigns every generated row a class. It cannot prove stable
   contents or correct classification. The revised plan needs a controlled
   measurement interval for exact comparisons, and an explicit mixed-time status
   for an online scan. Size and metapage agreement alone cannot certify it
   ([rawpage.c#get_raw_page_internal](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L141-L198),
   [ginvacuum.c:754-789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L754-L789)).
   **Answered on 2026-09-08**: the controlled interval is a `SHARE ROW EXCLUSIVE`
   transaction, measured against eight concurrent commands and one paired
   VACUUM loop; the mixed-time status stays for the online case. See
   [The measurement protocol](#the-measurement-protocol).

5. **Step 3: correct the free-space-map cross-check and its equality condition.**
   The FSM records `BLCKSZ - 1` but decodes its highest category as
   `MaxHeapTupleSize`, or `BLCKSZ - MAXALIGN(SizeOfPageHeaderData + sizeof(ItemIdData))`.
   This gives 8160 for an 8192-byte block and 8-byte alignment, not 8191. Derive
   the value using the build's block size and alignment. Compare counts only after
   accounting for deletion horizons, maintenance completion, and intervening
   reuse. A nonrecyclable deleted data page still enters VACUUM's data-page count;
   the SQL puts it in the deleted bucket. In the v17 verbose line, `pages_free`
   appears as **reusable**
   ([indexfsm.c#RecordFreeIndexPage](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L48-L55),
   [freespace.c:398-435](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L398-L435),
   [htup_details.h#MaxHeapTupleSize](../../../../raw/postgres-17/src/include/access/htup_details.h#L563),
   [pg_controldata.c#pg_control_init](../../../../raw/postgres-17/src/backend/utils/misc/pg_controldata.c#L203-L228),
   [ginvacuum.c:766-794](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L766-L794),
   [vacuumlazy.c:718-731](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L731)).

6. **Steps 2 and 5: make unsupported-format and malformed-page handling explicit.**
   The SQL gates the combined slack fields and `bloat_pct` on version 2, but still
   prints `entry_slack`, `data_slack`, and the derived `payload_bytes` without that
   gate. Suppress or qualify every affected value. Also, `PageIsNew` tests only
   `pd_upper == 0`; a NULL GIN decoder result is not a byte-for-byte zero-page
   check. `gin_page_opaque_info` emits unknown flag bits as hexadecimal text, and
   the SQL's final `ELSE 'entry'` has no unknown-class rejection. Define explicit
   diagnostic outcomes for unknown flags, invalid headers, and a missing or
   invalid metapage before trusting numeric results. These are inspection limits,
   not a substitute for a GIN structural verifier
   ([ginblock.h:302-309](../../../../raw/postgres-17/src/include/access/ginblock.h#L302-L309),
   [bufpage.h#PageIsNew](../../../../raw/postgres-17/src/include/storage/bufpage.h#L226-L234),
   [ginfuncs.c#gin_metapage_info](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L30-L95),
   [ginfuncs.c#gin_page_opaque_info](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L98-L171),
   [amcheck/Makefile](../../../../raw/postgres-17/contrib/amcheck/Makefile#L3-L13)).
   Narrowed on 2026-09-07: the guarded statement reads [`pg_stat_progress_vacuum`](../../../glossary.md#progress-reporting),
   `pg_stat_progress_analyze` and `pg_stat_progress_create_index` before and after
   its scan and flagged every in-flight census in the re-run (3 of 3 under a
   VACUUM, 2 of 2 under a concurrent rebuild). A maintenance run that starts and
   finishes between the two reads is still invisible, several simultaneous
   vacuums were still not measured, and the worst-case error of one census is
   still unbounded.
   Narrowed again on 2026-09-08: the version and class guards are now stated in
   derived terms rather than a literal 8, a wrong metapage special area is named
   in `status`, and the probe reports `malformed_pages` and `undecoded_pages`. One
   limit is now measured rather than assumed: a page whose header breaks
   `pd_upper <= pd_special` is refused by the [buffer manager](../../../glossary.md#buffer-manager), so **no** SQL guard
   can classify it. See
   [Adversarial and acceptance cases](#adversarial-and-acceptance-cases).

7. **Step 4: name the measured size precisely.** A before/after comparison of
   [`pg_relation_size(index, 'main')`](../../../glossary.md#relation-size-functions) measures the reduction in the [main fork](../../../glossary.md#fork)'s
   file lengths. The implementation sums `stat.st_size` for that fork's segments;
   it does not measure filesystem allocation, other forks, or the rebuild's peak
   disk demand. Keep this denominator throughout the experiment, record signed
   size changes, and record the rebuild settings and data state
   ([dbsize.c#calculate_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L301-L343),
   [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L370),
   [index.c:3781-3789](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789)).

**Retain step 1 and the privilege split in step 5.** The GIN rejection in
[`pgstattuple`](../../../glossary.md#pgstattuple), the three-field metapage-only result from `pgstatginindex`, and the
superuser requirement in raw-page readers are correctly identified. The
`pg_stat_scan_tables` grant in pgstattuple 1.5 does not satisfy the raw readers'
own superuser checks. Keep the `OFFSET 0` page-read boundary: the [planner](../../../glossary.md#planner) rejects
pull-up of a subquery with an offset or a [volatile](../../../glossary.md#function-volatility) target list
([pgstattuple.c#pgstat_relation](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L260-L296),
[pgstatindex.c#pgstatginindex_internal](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L507-L577),
[pgstattuple--1.4--1.5.sql:49-57](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L49-L57),
[rawpage.c:150-173](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L150-L173),
[prepjointree.c:1689-1701](../../../../raw/postgres-17/src/backend/optimizer/prep/prepjointree.c#L1689-L1701),
[prepjointree.c:1772-1781](../../../../raw/postgres-17/src/backend/optimizer/prep/prepjointree.c#L1772-L1781)).

### Revised plan

This is the plan for the next implementation and validation pass. The source
findings above are reviewed; the additional query guards and experiments below
are not implemented by this review.

Status on 2026-09-07: step 3 is implemented as
[The guarded census statement](#the-guarded-census-statement), the step 4 cases
were run and are reported in
[Adversarial and acceptance cases](#adversarial-and-acceptance-cases),
and step 5 was run for the seven published fixtures plus one budget sweep on
`f1_churn_gin`.

Status on 2026-09-08: **all six steps are now implemented or run.** Step 3's
remaining derivation is
[The derived-arithmetic statements](#the-derived-arithmetic-statements), which
leaves no typed-in size in any statement and measures the page-format constants on
the build. Step 2's controlled interval is
[The measurement protocol](#the-measurement-protocol), a `SHARE ROW EXCLUSIVE`
transaction, with its one hole measured. Step 4's remaining adversarial cases — the
wraparound failsafe, real crashes and three more corruption shapes — plus a fifth
reproduction of the fixture programme are in
[Adversarial and acceptance cases](#adversarial-and-acceptance-cases). What is left is not
implementation work: a second `BLCKSZ`, any 12.x server, and the bound questions
themselves.

Status on 2026-09-15: **the plan is superseded by the protocol.** Step 1's outputs
are the declared columns of
[The declarations, filed before the run](#the-declarations-filed-before-the-run);
step 2's controlled interval, step 4's cases and step 5's rebuild comparisons are
what [the script](#the-postgresql-1711-leg) now runs on every fixture, under the phase
boundaries of
[Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md);
and step 6's filing checks were applied to this revision. What the plan asked for
and the protocol does not supply is unchanged: a second `BLCKSZ`, a 12.x leg, and
the bound questions themselves, which are open questions 3, 8 and 13.

Status on 2026-09-24: step 4's "disabled index cleanup" case is no longer run. The
protocol dropped it from its required coverage and now treats a fixture that
switches index cleanup off as defeating the maintenance step, so the page's one
fixture for it was removed; see
[What this pass removed, and why](#what-this-pass-removed-and-why). The 12.x leg
the plan wanted is now a script of its own, limited to statement portability; see
[Outside the protocol](#outside-the-protocol-the-four-statements-on-postgresql-12).

1. **Specify the outputs and scope.** Select one physical GIN index and record
   its identity, definition, main-fork size, block size, GIN format version, and
   installed [extension](../../../glossary.md#extension) versions. Define marked-deleted/uninitialized bytes,
   entry-page gaps, posting-tree gaps, pending bytes, and measured main-fork
   reduction separately. Keep `bloat_pct` as the existing accounting formula
   without promising a reclaimable percentage or either bound. See findings 1,
   2, and 7.
2. **Choose the measurement conditions before maintenance.** Use a controlled
   interval for the calibration experiment, covering writers, VACUUM, pending
   cleanup, and index replacement. For an online report, record that page images
   can come from different instants. Capture the pre-maintenance state; then
   record whether only pending cleanup or full index vacuum/cleanup completed.
   Allow deletion-horizon mismatches to remain unresolved instead of treating a
   fixed number of VACUUM runs as sufficient. See findings 2 through 5.
3. **Implement explicit result validity.** Preserve the single raw-page read and
   decoder sharing. Derive all block-size arithmetic, including the size bracket
   that currently divides by 8192. Add explicit handling for unsupported versions,
   untrusted slack-derived fields, unknown classes, metapage failures, and target
   changes. Keep page accounting, FSM state, and metapage comparisons as separate
   diagnostics. See findings 4 through 6.
4. **Validate ordinary and adversarial cases on the exact pin.** Run the final
   statement extracted from this page on an isolated build. Include fresh and
   empty controls, posting-tree deletions with a held old [snapshot](../../../glossary.md#snapshot), key-replacement
   churn, a live pending list, cleanup-only versus full VACUUM, and disabled index
   cleanup. Test reader privileges, invalid and temporary targets, malformed or
   uninitialized page inputs, and unsupported-format handling. Exercise concurrent
   writers and maintenance separately. Require diagnostic or withheld output for
   unsupported cases. The shipped `pageinspect` tests cover basic GIN decoding,
   error inputs, and all-zero pages; the `pgstattuple` tests cover metapage reads
   and wrong access methods. They do not validate this combined report or a
   REINDEX-savings bound
   ([pageinspect/sql/gin.sql](../../../../raw/postgres-17/contrib/pageinspect/sql/gin.sql#L1-L41),
   [pgstattuple/sql/pgstattuple.sql](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L47-L63)).
5. **Score rebuild comparisons without assuming their result.** Rebuild each
   calibration fixture with its definition and input data held constant. Record
   `maintenance_work_mem`, the before/after main-fork byte counts, and prediction
   error for each candidate metric. Include several build-memory budgets and the
   dead-key and pending-list cases that challenge the proposed bounds. GIN's
   accumulator flush and entry-page split rules make those relevant variables
   ([gininsert.c#ginBuildCallback](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L276-L314),
   [ginentrypage.c:667-691](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L667-L691)).
6. **Apply the operational and filing checks to the tested text.** Retain
   `statement_timeout = '10min'` and `lock_timeout = '2s'` as starting session
   limits for the full scan, and apply them in each session running an operational
   statement. Both settings, and any experimental `maintenance_work_mem` change,
   use session/transaction scope and need no reload or restart
   ([guc_tables.c:2611-2631](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2631),
   [guc_tables.c:2466-2474](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2466-L2474)).
   Preserve the `/* wiki_... */` tags, capture the exact tested SQL, and file
   unexecuted paths under Open Questions. Update this page's claim map, Contents,
   navigation summaries, and log; run wiki lint. Change agent verification only
   after a full claim review, and leave human verification to the user.

### Deviations from the brief, and why

Three items in the plan did not survive contact with the source or the server.

1. **`pg_freespace()` cannot return 8191.** `RecordFreeIndexPage` does record
   `BLCKSZ - 1` ([indexfsm.c#RecordFreeIndexPage](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L48-L55)),
   but the FSM stores one byte per page: `fsm_space_avail_to_cat` maps anything at
   or above `MaxFSMRequestSize` to category 255
   ([freespace.c#fsm_space_avail_to_cat](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L398-L421)),
   and `GetRecordedFreeSpace` converts 255 back to exactly `MaxFSMRequestSize`
   ([freespace.c#GetRecordedFreeSpace](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L249-L271),
   [freespace.c#fsm_space_cat_to_avail](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L423-L435)).
   `MaxFSMRequestSize` is `MaxHeapTupleSize`
   ([freespace.c:66](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L66)), which is
   `BLCKSZ - MAXALIGN(SizeOfPageHeaderData + sizeof(ItemIdData))`
   ([htup_details.h#MaxHeapTupleSize](../../../../raw/postgres-17/src/include/access/htup_details.h#L563)) —
   **8160** on the pinned build with `block_size` 8192 and 8-byte [MAXALIGN](../../../glossary.md#alignment). The
   server agrees: the FSM census of the deleted-pages fixture reads
   `avail = 8160 -> 768 blocks, avail = 0 -> 130 blocks`, and the maximum `avail`
   observed over every GIN index was 8160. The cross-check therefore tests
   `avail = 8160`, not 8191. Do not take the number from the category table's own
   comment, which is illustrative and stale: it works its example "assuming
   default 8k `BLCKSZ`, and that `MaxFSMRequestSize` is 8164 bytes"
   ([freespace.c:36-62](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L36-L62)),
   a value the macro cannot produce on this build. **Do not hardcode 8160
   either** — derive it, as [Four cross-checks](#four-cross-checks) now does,
   from `pg_control_init()`, which publishes both terms of the macro
   ([pg_controldata.c#pg_control_init](../../../../raw/postgres-17/src/backend/utils/misc/pg_controldata.c#L203-L228),
   [func.sgml#pg_control_init](../../../../raw/postgres-17/doc/src/sgml/func.sgml#L27721-L27742)).

2. **`VACUUM VERBOSE` has no field literally called `pages_free`.** v17 prints
   `index "%s": pages: %u in total, %u newly deleted, %u currently deleted, %u reusable`,
   and the fourth number is `IndexBulkDeleteResult.pages_free`
   ([vacuumlazy.c:718-731](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L731)).
   For GIN, "reusable" is the whole-index census set by `ginvacuumcleanup`
   ([ginvacuum.c:786-794](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L786-L794)), but
   "currently deleted" is **not** a census: GIN only ever increments
   `pages_deleted` for pages it deletes in this run, in `ginDeletePage`
   ([ginvacuum.c:234-235](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L234-L235)) and in
   `shiftList` ([ginfast.c:590-591](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L590-L591)).
   The server shows the difference inside one VACUUM: on the run that finally
   recycled the pages, the [B-tree](../../../glossary.md#b-tree) on the same table reported
   `551 in total, 0 newly deleted, 520 currently deleted, 520 reusable` while its
   GIN sibling reported `898 in total, 0 newly deleted, 0 currently deleted,
   768 reusable`.

3. **The `ginVersion = 2` gate is right but for a narrower reason than "posting
   tree pd_lower".** In a version-2 index every data page in the file was written
   by 9.4-or-later code, so `pd_lower` is maintained on compressed leaves
   ([gindatapage.c#dataPlaceToPageLeafRecompress](../../../../raw/postgres-17/src/backend/access/gin/gindatapage.c#L1018-L1023))
   and on internal data pages
   ([gindatapage.c#GinDataPageAddPostingItem](../../../../raw/postgres-17/src/backend/access/gin/gindatapage.c#L402-L411)) —
   both through `GinDataPageSetDataSize`, which writes `pd_lower` directly
   ([ginblock.h#GinDataPageSetDataSize](../../../../raw/postgres-17/src/include/access/ginblock.h#L310-L314)).
   The untrustworthy case is a binary-upgraded index that still holds pre-9.4
   pages, which is exactly what `ginVersion` distinguishes
   ([ginblock.h#GinMetaPageData](../../../../raw/postgres-17/src/include/access/ginblock.h#L85-L103),
   [ginblock.h:302-309](../../../../raw/postgres-17/src/include/access/ginblock.h#L302-L309)). The
   census also classifies uncompressed data leaves separately, because GIN itself
   refuses to count their free space
   ([gindatapage.c#dataBeginPlaceToPageLeaf](../../../../raw/postgres-17/src/backend/access/gin/gindatapage.c#L520-L528)).

### Why no single contrib function suffices

`pgstattuple` refuses GIN outright. `pgstat_relation` dispatches on `relam` and
the GIN arm falls straight into the "not supported" error
([pgstattuple.c#pgstat_relation](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L260-L296)):

```text
ERROR:  index "f5_deleted_gin" (gin index) is not supported
```

`pgstatginindex` accepts GIN but reads three fields from block 0 and nothing else
— `ginVersion`, `nPendingPages`, `nPendingHeapTuples`
([pgstatindex.c#pgstatginindex_internal](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L507-L577),
[pgstatindex.c#GinIndexStat](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L97-L108)). It never
reads a second page, so it cannot see a dead page, a slack byte, or even the index
size; the documentation lists exactly those three output columns
([pgstattuple.sgml#pgstatginindex](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L298-L350)).
Measured consequence: on the flushed pending-list fixture, whose file was 64.64%
dead pages, `pgstatginindex` returned `version 2 | pending_pages 0 | pending_tuples 0`.

There is no GIN equivalent of [`pgstatindex`](../../../glossary.md#pgstatindex)/`pgstathashindex`, and [`contrib/amcheck`](../../../glossary.md#amcheck)
in this checkout ships only B-tree and heap verifiers — `bt_index_check`,
`bt_index_parent_check`
([amcheck--1.0.sql:9-20](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.0.sql#L9-L20),
[amcheck--1.3--1.4.sql:11-24](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.3--1.4.sql#L11-L24)) and
`verify_heapam`
([amcheck--1.2--1.3.sql:9-21](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.2--1.3.sql#L9-L21)) — so
there is no structural verifier to borrow page counts from either.

That leaves `pageinspect`, whose three GIN functions plus `page_header` are enough,
and [`pg_freespacemap`](../../../glossary.md#pg_freespacemap) as an independent check.

### The three waste classes, from GIN's own definitions

**Whole-page waste.** A GIN page is reusable when `PageIsNew` is true, or flagged
deleted with either no deletion xid or one the whole cluster has moved past
([ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829)).
`PageIsNew` is `pd_upper == 0`
([bufpage.h#PageIsNew](../../../../raw/postgres-17/src/include/storage/bufpage.h#L226-L234)). Deleted pages
come from two places, and both keep their identity visible in the flags word:
posting-tree page deletion ORs in `GIN_DELETED` and stamps the delete xid into
`pd_prune_xid`
([ginvacuum.c#ginDeletePage](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L187-L192),
[ginblock.h:132-138](../../../../raw/postgres-17/src/include/access/ginblock.h#L132-L138)), while a
pending-list shift *replaces* the flags word with `GIN_DELETED`
([ginfast.c#shiftList](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L630-L635)) — which is why
no stale `list` pages can survive a flush and confuse the census.

`ginvacuumcleanup` then walks every block from `GIN_ROOT_BLKNO` up, records each
recyclable page in the FSM, counts the rest as entry or data pages, and reports the
recyclable count as `pages_free`
([ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L802)). Those
pages are reusable **only inside the index**: `GinNewBuffer` takes them back from
the FSM before extending the file
([ginutil.c#GinNewBuffer](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L294-L335)), and nothing
under `src/backend/access/gin/` [truncates](../../../glossary.md#truncation) a relation — a grep for `RelationTruncate`
and `smgrtruncate` across that directory returns zero hits, and `ginvacuumcleanup`
ends by re-reading, not shortening, the file length
([ginvacuum.c:796-802](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L796-L802)).

**Live-page slack.** GIN's own free-space test on a data leaf is
`GinDataLeafPageGetFreeSpace`, defined as `PageGetExactFreeSpace`
([ginblock.h:287](../../../../raw/postgres-17/src/include/access/ginblock.h#L287)), which is exactly
`pd_upper - pd_lower` with no allowance for a [line pointer](../../../glossary.md#line-pointer)
([bufpage.c#PageGetExactFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L952-L973)).
`page_header` exposes both fields
([pageinspect--1.9--1.10.sql#page_header](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.9--1.10.sql#L10-L21)),
so the same subtraction is available in SQL. On an **entry** page the comparable
engine test is `PageGetFreeSpace`, which subtracts `sizeof(ItemIdData)` because a
new tuple also needs a line pointer
([ginentrypage.c#entryIsEnoughSpace](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L458-L482),
[bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L898-L923)); the
census includes gap bytes that a future insertion would spend on line pointers.
This distinguishes physical gaps from insertion capacity; it establishes no
upper bound on what a rebuild returns.

**Pending-list pages.** With `fastupdate` on, inserts land in a linked list of
`GIN_LIST` pages whose head, tail and counts live in the metapage
([ginblock.h#GinMetaPageData](../../../../raw/postgres-17/src/include/access/ginblock.h#L55-L83),
[ginfast.c#makeSublist](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L144-L209)), and the
documentation describes them as postponed work that VACUUM, autoanalyze,
`gin_clean_pending_list()` or a `gin_pending_list_limit` overflow will merge into
the main structure
([gin.sgml#GIN-Fast-Update](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L500-L537)). They are live data,
not waste — and the flush is not free, because merging appends to entry tuples and
allocates pages through `GinNewBuffer` when it has to.

### The procedure

The protocol these eight steps implement is not defined here. [Mandatory GIN Bloat
Tests](../../common-concepts/mandatory-gin-bloat-tests.md) defines the five phases,
the settle step, the maintenance step, the census, the lock, the oracle, the
declare-then-score rule, the cross-checks and the reading rules; what follows is
this page's own instantiation, with the extension versions, the [standby](../../../glossary.md#hot-standby) and bypass
observations, and the statements that are local to it. Steps 2 and 5 through 7 are
what the 2026-09-15 re-run added: the previous six-step procedure had no maintenance
step, ran no census, and declared nothing before it scored.

1. **Install the three extensions.** `pageinspect` (1.12), `pgstattuple` (1.5) and
   `pg_freespacemap` (1.2) in this checkout
   ([pageinspect.control](../../../../raw/postgres-17/contrib/pageinspect/pageinspect.control#L1-L5),
   [pgstattuple.control](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.control#L1-L5),
   [pg_freespacemap.control](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap.control#L1-L5)).
2. **Declare every published column before you measure**, as a lower bound, an
   upper bound or a level; see
   [The declarations, filed before the run](#the-declarations-filed-before-the-run).
3. **Settle the state.** Run `VACUUM` on the table, or
   `gin_clean_pending_list(index)` for the pending list alone
   ([func.sgml#gin_clean_pending_list](../../../../raw/postgres-17/doc/src/sgml/func.sgml#L30104-L30123)). VACUUM
   is what refreshes `n_entry_pages` / `n_data_pages` / `n_total_pages` in the
   metapage ([ginvacuum.c:786-789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L786-L789)),
   and those fields are stale otherwise: before its settle step the pending
   fixture's metapage said `n_total_pages = 268` while the file held 758 blocks,
   and the census flagged it. Expect to VACUUM **twice or more** for deleted
   pages; see
   [Deleted pages need the horizon to move before they count](#deleted-pages-need-the-horizon-to-move-before-they-count).
   On a standby you cannot do this step at all — a physical replica of this run's
   cluster answered `ERROR: cannot execute VACUUM during recovery`,
   `ERROR: recovery is in progress` for `gin_clean_pending_list` and
   `ERROR: cannot execute ANALYZE during recovery`, while every census function
   kept working (`f5_deleted_gin ok blocks=898`, `f6_slack_gin ok blocks=898`,
   `pgstatginindex` `2|0|0`) — so a standby census reads whatever state replay has
   produced.
   For this step, require completed index cleanup: `INDEX_CLEANUP OFF` disables
   the callback, and the failsafe can disable it even when cleanup was requested
   ([vacuumlazy.c:392-401](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L401),
   [vacuumlazy.c:1064-1066](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1064-L1066),
   [vacuumlazy.c:2323-2335](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2335)).
4. **Record the denominator and the metapage.** `pg_relation_size(idx, 'main')`
   is the main fork only
   ([func.sgml#pg_relation_size](../../../../raw/postgres-17/doc/src/sgml/func.sgml#L29627-L29643)), which is
   the right denominator because the census counts main-fork blocks;
   `gin_metapage_info(get_raw_page(idx, 0))` supplies `version` and the pending
   counters ([ginfuncs.c#gin_metapage_info](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L30-L95)).
5. **Publish the statistics, then maintain the table.** `SELECT
   pg_stat_force_next_flush();` in every session that wrote, then
   `VACUUM (VERBOSE, ANALYZE)` on every table the churn touched. The order is not
   cosmetic: `pgstat_report_analyze` zeroes `mod_since_analyze`
   ([pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L331-L337))
   while a [backend](../../../glossary.md#backend)'s own counts reach the shared entry only when
   `pgstat_report_stat` flushes them, unforced at most once per 1000 ms
   ([pgstat.c#PGSTAT_MIN_INTERVAL](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L117-L122),
   [pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L583-L600),
   [pgstat_relation.c#mod_since_analyze](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L855-L860)).
   Getting that order wrong is measurable, and this run measures it on purpose;
   see [The simulated auto-analyze census](#the-simulated-auto-analyze-census).
6. **Run the census**: recompute the launcher's analyze verdict for every table
   the worker would have walked, and analyze the ones it names.
7. **Take the measurement lock**, then census blocks 1 .. relpages-1, reading each
   page once and passing the same `bytea` to `gin_page_opaque_info` and
   `page_header`.
8. **Cross-check four ways** before believing any number, run the entry-tuple probe
   if you intend to predict a rebuild, and **only then** compare with a rebuild.

### The declarations, filed before the run

The protocol's declare-then-score rule says every published column is filed as a
lower bound, an upper bound or a level *before* the run. This run's `declare` stage
wrote the table below into the fixture database at **13:52:33.716**, the `fixtures`
stage started only after that stage returned, and the first census of a fixture ran
at **13:52:50.295** - 16.6 seconds later - so the declaration cannot have been
written around the results. The claim column below is the `claim` text the stage
filed, shortened where a cell would not fit; the artefact is
`out/00-declarations.txt`, and the `fixtures` stage prints both timestamps to the
millisecond at the end of `out/01-fixtures.txt`.

| Column | Declared kind | The claim that was scored |
|---|---|---|
| `truth_pct` | oracle | `100 * (bytes before REINDEX − bytes after) / bytes before`, from the two `pg_relation_size(index, 'main')` readings and nothing else |
| `whole_page_waste_pct` | **lower bound** | never exceeds the share of the file a rebuild returns |
| `bloat_pct` | **upper bound** | never less than the share of the file a rebuild returns |
| `live_page_slack_pct` | level | insertion capacity on entry pages, a physical gap on data pages |
| `entry_slack` | level | entry-page gap bytes, which a fresh build also carries |
| `data_slack` | level | posting-tree gap bytes |
| `pending_pct` | level | deferred work, not waste |
| `payload_bytes` | level | size minus dead, pending and slack; carries entry tuples for keys that no longer occur |
| `payload_fill_pred` | level | `payload_bytes` over the rebuilt fill fraction, a prediction whose divisor comes from the rebuild it predicts |
| `census_total_pages` | level | accounting identity against `blocks`; proves no page was dropped, not that a class is right |

The two bounds are the page's own standing claims, declared so the run could test
them rather than assume them. Two earlier, pre-protocol runs had already recorded
lower-bound violations, and this run reproduces one of them and finds a second on a
fixture that did not exist before; the consequence for the page's rules is in
[Reading rules](#reading-rules).

### The census statement

This is the baseline text, the one every scoring table on this page carried before
the 2026-09-15 re-run. **It is no longer the scored text.** What the re-run scored
is the derived revision of it —
[The census, with the constant derived](#the-census-with-the-constant-derived) — for
the reason [the plan review](#plan-review) gives: one page with a foreign
special-area size costs this text every index in its report, and the run has eight
such pages on purpose. The two agree in every shared column on every fixture where
both ran. The timeout settings are session-scoped, and the tags are the `wiki_`
markers this repo requires.

```sql
SET /* wiki_gin_waste_guards */ statement_timeout = '10min';
SET /* wiki_gin_waste_guards */ lock_timeout = '2s';

WITH /* wiki_gin_waste_census */ gin_idx AS (
    SELECT c.oid                                  AS idx,
           c.oid::regclass::text                  AS idx_name,
           pg_relation_size(c.oid, 'main')         AS main_bytes,
           current_setting('block_size')::bigint   AS bs
    FROM pg_class c
         JOIN pg_am a    ON a.oid = c.relam
         JOIN pg_index x ON x.indexrelid = c.oid
    WHERE a.amname = 'gin'
      AND c.relkind = 'i'            -- 'I' (partitioned) has no storage
      AND x.indisvalid               -- an invalid index is still readable, see notes
      AND c.relpersistence <> 't'    -- another session's temp index is refused
),
meta AS (
    SELECT g.*, m.version, m.n_pending_pages, m.n_pending_tuples,
           m.n_total_pages, m.n_entry_pages, m.n_data_pages
    FROM gin_idx g
         CROSS JOIN LATERAL gin_metapage_info(get_raw_page(g.idx_name, 0)) m
),
pages AS (
    SELECT g.idx,
           CASE
               WHEN h.pagesize = 0                      THEN 'new'   -- all-zero page
               WHEN o.flags IS NULL                     THEN 'new'
               WHEN o.flags @> '{meta}'                 THEN 'meta'
               WHEN o.flags @> '{deleted}'              THEN 'deleted'
               WHEN o.flags @> '{list}'                 THEN 'pending'
               WHEN o.flags @> '{data,leaf,compressed}' THEN 'data_leaf'
               WHEN o.flags @> '{data,leaf}'            THEN 'data_leaf_uncompressed'
               WHEN o.flags @> '{data}'                 THEN 'data_internal'
               ELSE                                          'entry'
           END                                          AS page_class,
           COALESCE(h.upper - h.lower, 0)               AS slack
    FROM gin_idx g
         CROSS JOIN LATERAL generate_series(1, g.main_bytes / g.bs - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page(g.idx_name, b.blkno::int) AS pg
                             OFFSET 0) AS r          -- read each page exactly once
         LEFT JOIN LATERAL gin_page_opaque_info(r.pg) AS o ON true
         LEFT JOIN LATERAL page_header(r.pg)          AS h ON true
),
census AS (
    SELECT idx,
           count(*) FILTER (WHERE page_class = 'entry')                  AS entry_pages,
           count(*) FILTER (WHERE page_class = 'data_leaf')              AS data_leaf_pages,
           count(*) FILTER (WHERE page_class = 'data_internal')          AS data_internal_pages,
           count(*) FILTER (WHERE page_class = 'data_leaf_uncompressed') AS uncompressed_pages,
           count(*) FILTER (WHERE page_class = 'pending')                AS pending_pages,
           count(*) FILTER (WHERE page_class = 'deleted')                AS deleted_pages,
           count(*) FILTER (WHERE page_class = 'new')                    AS new_pages,
           count(*) FILTER (WHERE page_class = 'meta')                   AS stray_meta_pages,
           COALESCE(sum(slack) FILTER (WHERE page_class = 'entry'), 0)   AS entry_slack,
           COALESCE(sum(slack) FILTER (WHERE page_class IN ('data_leaf',
                                            'data_internal')), 0)        AS data_slack
    FROM pages
    GROUP BY idx
)
SELECT m.idx_name                                       AS index_name,
       m.version                                        AS gin_version,
       m.main_bytes                                     AS main_fork_bytes,
       m.main_bytes / m.bs                              AS blocks,
       c.entry_pages, c.data_leaf_pages, c.data_internal_pages,
       c.uncompressed_pages, c.pending_pages, c.deleted_pages, c.new_pages,
       (c.deleted_pages + c.new_pages) * m.bs           AS whole_page_waste_bytes,
       round(100.0 * (c.deleted_pages + c.new_pages) * m.bs
             / nullif(m.main_bytes, 0), 2)              AS whole_page_waste_pct,
       CASE WHEN m.version = 2 THEN c.entry_slack + c.data_slack END
                                                        AS live_page_slack_bytes,
       CASE WHEN m.version = 2
            THEN round(100.0 * (c.entry_slack + c.data_slack)
                       / nullif(m.main_bytes, 0), 2) END AS live_page_slack_pct,
       CASE WHEN m.version = 2
            THEN round(100.0 * ((c.deleted_pages + c.new_pages) * m.bs
                                + c.entry_slack + c.data_slack)
                       / nullif(m.main_bytes, 0), 2) END AS bloat_pct,
       c.entry_slack, c.data_slack,
       c.pending_pages * m.bs                           AS pending_bytes,
       round(100.0 * c.pending_pages * m.bs
             / nullif(m.main_bytes, 0), 2)              AS pending_pct,
       m.main_bytes - (c.deleted_pages + c.new_pages + c.pending_pages) * m.bs
                    - c.entry_slack - c.data_slack      AS payload_bytes,
       m.n_pending_pages                                AS meta_pending_pages,
       m.n_entry_pages                                  AS meta_entry_pages,
       m.n_data_pages                                   AS meta_data_pages,
       m.n_total_pages                                  AS meta_total_pages,
       1 + c.entry_pages + c.data_leaf_pages + c.data_internal_pages
         + c.uncompressed_pages + c.pending_pages + c.deleted_pages
         + c.new_pages + c.stray_meta_pages             AS census_total_pages
FROM meta m JOIN census c ON c.idx = m.idx
ORDER BY 1;
```

Add `AND c.oid = 'myschema.myindex'::regclass` to the `gin_idx` filter for a single
index.

Two things in that text are there so the same statement runs on PostgreSQL 12 as
well as 17: the `h.pagesize = 0` arm and the `b.blkno::int` cast. Both are no-ops on
17.11. In the 2026-09-24 run's portability stage, the text with either edit removed
returned output identical to the filed text on all four indexes of its database,
`pt_zero_gin`'s two all-zero pages included, because the `pagesize = 0` arm and the
`flags IS NULL` arm fire on exactly the same pages there. Both are load-bearing on
12.2. See
[Outside the protocol](#outside-the-protocol-the-four-statements-on-postgresql-12).

Design points that are not cosmetic:

- **`OFFSET 0` keeps the page read single.** `get_raw_page` is volatile and the
  subquery is not flattened, so the page is fetched once and the same value feeds
  both LATERAL calls. Measured with [`EXPLAIN (ANALYZE, BUFFERS)`](../../../glossary.md#explain-buffers) on the 1,236-block
  `f3_fresh_gin`: this form reports **1265** shared hits, the naive form that calls
  `get_raw_page` inside each function reports **2499** — one read per block against
  two, plus the same [catalog](../../../glossary.md#catalog) reads either way. See
  [Cost of the census](#cost-of-the-census).
- **A NULL result means `PageIsNew`, which tests `pd_upper == 0`.** This is not
  a check that every byte is zero
  ([bufpage.h#PageIsNew](../../../../raw/postgres-17/src/include/storage/bufpage.h#L226-L234)).
  Both GIN functions return NULL early on that predicate
  ([ginfuncs.c:49-50](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L49-L50),
  [ginfuncs.c:119-120](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L119-L120)); the shipped
  test asserts exactly that
  ([pageinspect/sql/gin.sql:35-39](../../../../raw/postgres-17/contrib/pageinspect/sql/gin.sql#L35-L39),
  [pageinspect/expected/gin.out:57-70](../../../../raw/postgres-17/contrib/pageinspect/expected/gin.out#L57-L70)).
  On the server, an all-zero `bytea` gave a row of NULLs from
  `gin_page_opaque_info`, NULL from `gin_metapage_info`, and
  `lower 0 | upper 0 | pagesize 0` from `page_header`, so the `COALESCE(..., 0)`
  contributes no slack. All-zero pages are reachable two ways: deterministically, by
  appending zeroed blocks to a stopped server's index file, which is what the
  corruption fixture `s5_gin` does and what this run measures
  ([Adversarial and acceptance cases](#adversarial-and-acceptance-cases)); and by a
  crash, which produced 4 and 7 of them in one superseded run and none in two
  others, a rate this page no longer carries. The mechanism is the same either way:
  GIN extends the file through `GinNewBuffer` and initializes the page afterwards
  ([ginutil.c#GinNewBuffer](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L294-L335)), so a crash
  in between leaves a zeroed block that `PageIsNew` — and therefore
  `GinPageIsRecyclable` — accepts.
- **`deleted` is tested before `data`/`list`.** A deleted posting-tree page keeps
  its `GIN_DATA` and `GIN_LEAF` bits, because `ginDeletePage` only ORs the deleted
  bit in ([ginvacuum.c:187-192](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L187-L192)); the
  server shows the resulting flag set as `{data,leaf,deleted,compressed}`.
- **`census_total_pages = blocks` checks accounting only.** The generated block
  range and exhaustive `CASE` make every scanned row count toward the total,
  including rows assigned by the fallback `ELSE`. Equality does not prove correct
  classification or an unchanged index; the raw reader locks one page at a time
  ([rawpage.c#get_raw_page_internal](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L141-L198)).
  It held on **26 of 26** censused indexes in this run, as it has in every run this
  page records. Entry-tree *internal* pages are the class that makes the
  `ELSE` arm necessary: their flags word is 0, so `gin_page_opaque_info` returns
  an empty array rather than a NULL row, and they are the difference between the
  census's `entry_pages` and the probe's `entry_leaf_pages` — on `f3_fresh_gin`,
  1,200 entry pages are 1,194 leaves plus 6 internal ones.

### The guarded census statement

This is the revised plan's step 3, implemented and run on 2026-09-07. It keeps the
published statement's single raw read per page, page classes, arithmetic and
column names, and adds a `status` column, two page classes, a second size reading
and the gating the plan review asked for. When it was filed it returned the same
value as the baseline statement in all 208 shared cells over eight fixtures and read
the same 7,892 buffers; the text that the 2026-09-15 run scored is its derived
revision, which differs from it by the seven substitutions listed under
[The census, with the constant derived](#the-census-with-the-constant-derived).

Four mechanisms carry the guards.

1. **A page that fails the header check is never handed to a GIN decoder.** Both
   decoders are declared `STRICT`, a strict function is not executed when an
   argument is null, and the executor checks the arguments before calling a
   function in `FROM`. The statement therefore passes `NULL` instead of the page
   whenever `page_header` reports `upper = 0` (the `PageIsNew` test), a `pagesize`
   other than `block_size`, or a special area that is not 8 bytes, the size of
   `GinPageOpaqueData`. Those are the inputs on which `gin_page_opaque_info` and
   `gin_metapage_info` raise errors instead of returning rows, and one such page
   aborts the whole multi-index report of the published statement
   ([pageinspect--1.5.sql:246-268](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.5.sql#L246-L268),
   [create_function.sgml#STRICT](../../../../raw/postgres-17/doc/src/sgml/ref/create_function.sgml#L395-L400),
   [execSRF.c:188-196](../../../../raw/postgres-17/src/backend/executor/execSRF.c#L188-L196),
   [bufpage.h#PageIsNew](../../../../raw/postgres-17/src/include/storage/bufpage.h#L226-L234),
   [bufpage.h#PageGetSpecialSize](../../../../raw/postgres-17/src/include/storage/bufpage.h#L314-L317),
   [ginblock.h#GinPageOpaqueData](../../../../raw/postgres-17/src/include/access/ginblock.h#L30-L37),
   [ginfuncs.c:52-67](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L52-L67),
   [ginfuncs.c:122-128](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L122-L128)).
2. **Block 0 is decoded as a metapage only when its flags are exactly `{meta}`.**
   `gin_metapage_info` errors on any other flags word, so the opaque decoder runs
   first and the metapage decoder only on a `{meta}` result. A zeroed or foreign
   block 0 yields `metapage unreadable` and NULL in every metapage-derived column;
   the page census still runs
   ([ginfuncs.c:62-67](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L62-L67)).
3. **Every page lands in a named class or in `unknown`.** The decoder names eight
   flag bits and prints any other bit in hexadecimal; a page whose flags carry
   such a value, or a combination the `CASE` does not recognize, is counted as
   `unknown` instead of falling through to `entry`. Entry pages are `{leaf}`,
   `{}` and either with `incomplete_split`. Pages that failed the header check
   are counted as `invalid`. Both counts are printed, and either one withholds
   every slack-derived field
   ([ginfuncs.c:137-160](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L137-L160)).
4. **Target changes and maintenance are checked before and after the scan.** A
   second `pg_relation_size` reading is taken in a CTE that consumes the census
   rows, so it runs after the pages were read, and is printed as
   `blocks_after_census`. `pg_stat_progress_vacuum`, `pg_stat_progress_analyze`
   and `pg_stat_progress_create_index` are read for the index's table in the
   first CTE and again afterwards. All block arithmetic uses `block_size`
   ([system_views.sql#pg_stat_progress_vacuum](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1209-L1227),
   [system_views.sql#pg_stat_progress_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1188-L1207),
   [system_views.sql#pg_stat_progress_create_index](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1256-L1289),
   [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L370)).

| `status` item | Condition | Effect on the numeric columns |
|---|---|---|
| `ok` | none of the items below | none |
| `metapage unreadable` | block 0 fails the header check, or its flags are not `{meta}` | `gin_version`, the four `meta_*` columns and the slack-derived fields are NULL |
| `unsupported format: version N` | `gin_version <> 2` | slack-derived fields are NULL |
| `N page(s) not decodable` | pages that failed the header check | counted in `invalid_pages`; slack-derived fields are NULL |
| `N page(s) of unknown class` | unrecognized flag bits or combinations | counted in `unknown_pages`; slack-derived fields are NULL |
| `size changed during scan` | the second size reading differs from the first | none; compare `blocks_after_census` with `blocks` |
| `pending count disagrees with metapage` | census `pending_pages` differs from the metapage's `n_pending_pages` | none |
| `metapage page counts predate the file length` | the metapage's `n_total_pages` differs from `blocks` | none; those counts were last written by a VACUUM cleanup or the build, before the file grew |
| `vacuum or analyze in progress` | the table appears in `pg_stat_progress_vacuum` or `pg_stat_progress_analyze` before or after the scan | none |
| `index build in progress` | the table appears in `pg_stat_progress_create_index` before or after the scan | none |

The slack-derived fields are `live_page_slack_bytes`, `live_page_slack_pct`,
`bloat_pct`, `entry_slack`, `data_slack` and `payload_bytes`. Page counts,
`whole_page_waste_*` and the pending columns are always printed, because they
depend only on flags and the block count. Several items can appear together,
separated by `; `.

```sql
SET /* wiki_gin_waste_guards */ statement_timeout = '10min';
SET /* wiki_gin_waste_guards */ lock_timeout = '2s';

WITH /* wiki_gin_waste_census_guarded */ gin_idx AS (
    SELECT c.oid                                  AS idx,
           c.oid::regclass::text                  AS idx_name,
           x.indrelid                             AS tbl,
           pg_relation_size(c.oid, 'main')         AS main_bytes,
           current_setting('block_size')::bigint   AS bs,
           EXISTS (SELECT 1 FROM pg_stat_progress_vacuum v  WHERE v.relid = x.indrelid)
             OR EXISTS (SELECT 1 FROM pg_stat_progress_analyze z WHERE z.relid = x.indrelid)
                                                  AS maint_before,
           EXISTS (SELECT 1 FROM pg_stat_progress_create_index i WHERE i.relid = x.indrelid)
                                                  AS build_before
    FROM pg_class c
         JOIN pg_am a    ON a.oid = c.relam
         JOIN pg_index x ON x.indexrelid = c.oid
    WHERE a.amname = 'gin'
      AND c.relkind = 'i'            -- 'I' (partitioned) has no storage
      AND x.indisvalid               -- an invalid index is still readable, see notes
      AND c.relpersistence <> 't'    -- another session's temp index is refused
),
meta AS (
    -- Block 0: decode the opaque area only when the header shows a GIN-sized
    -- special area (8 bytes: rightlink, maxoff, flags), and the metapage only
    -- when the flags are exactly {meta}.  Both decoders are STRICT, so a NULL
    -- page skips the call instead of raising an error.
    SELECT g.*,
           (h0.upper > 0 AND h0.pagesize = g.bs AND h0.pagesize - h0.special = 8)
                                                        AS meta_layout_ok,
           o0.flags                                     AS meta_flags,
           m.version, m.n_pending_pages, m.n_pending_tuples,
           m.n_total_pages, m.n_entry_pages, m.n_data_pages
    FROM gin_idx g
         CROSS JOIN LATERAL (SELECT get_raw_page(g.idx_name, 0) AS pg OFFSET 0) AS r0
         LEFT JOIN LATERAL page_header(r0.pg) AS h0 ON true
         LEFT JOIN LATERAL gin_page_opaque_info(
               CASE WHEN h0.upper > 0 AND h0.pagesize = g.bs AND h0.pagesize - h0.special = 8
                    THEN r0.pg END) AS o0 ON true
         LEFT JOIN LATERAL gin_metapage_info(
               CASE WHEN o0.flags = '{meta}'::text[] THEN r0.pg END) AS m ON true
),
pages AS (
    SELECT g.idx,
           CASE
               WHEN h.upper = 0                                        THEN 'new'      -- PageIsNew
               WHEN h.pagesize <> g.bs OR h.pagesize - h.special <> 8  THEN 'invalid'  -- not a GIN page layout; not decoded
               WHEN EXISTS (SELECT 1 FROM unnest(o.flags) f
                            WHERE f NOT IN ('data', 'leaf', 'deleted', 'meta', 'list',
                                            'list_fullrow', 'incomplete_split', 'compressed'))
                                                                       THEN 'unknown'  -- decoder printed an unknown bit in hex
               WHEN o.flags @> '{meta}'                 THEN 'meta'
               WHEN o.flags @> '{deleted}'              THEN 'deleted'
               WHEN o.flags @> '{list}'                 THEN 'pending'
               WHEN o.flags @> '{data,leaf,compressed}' THEN 'data_leaf'
               WHEN o.flags @> '{data,leaf}'            THEN 'data_leaf_uncompressed'
               WHEN o.flags @> '{data}'                 THEN 'data_internal'
               WHEN o.flags <@ '{leaf,incomplete_split}'::text[] THEN 'entry'  -- {leaf} or {} (entry internal)
               ELSE                                          'unknown'
           END                                          AS page_class,
           COALESCE(h.upper - h.lower, 0)               AS slack
    FROM gin_idx g
         CROSS JOIN LATERAL generate_series(1, g.main_bytes / g.bs - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page(g.idx_name, b.blkno::int) AS pg
                             OFFSET 0) AS r          -- read each page exactly once
         LEFT JOIN LATERAL page_header(r.pg)          AS h ON true
         LEFT JOIN LATERAL gin_page_opaque_info(
               CASE WHEN h.upper > 0 AND h.pagesize = g.bs AND h.pagesize - h.special = 8
                    THEN r.pg END)                   AS o ON true
),
census AS (
    SELECT idx,
           count(*) FILTER (WHERE page_class = 'entry')                  AS entry_pages,
           count(*) FILTER (WHERE page_class = 'data_leaf')              AS data_leaf_pages,
           count(*) FILTER (WHERE page_class = 'data_internal')          AS data_internal_pages,
           count(*) FILTER (WHERE page_class = 'data_leaf_uncompressed') AS uncompressed_pages,
           count(*) FILTER (WHERE page_class = 'pending')                AS pending_pages,
           count(*) FILTER (WHERE page_class = 'deleted')                AS deleted_pages,
           count(*) FILTER (WHERE page_class = 'new')                    AS new_pages,
           count(*) FILTER (WHERE page_class = 'meta')                   AS stray_meta_pages,
           count(*) FILTER (WHERE page_class = 'invalid')                AS invalid_pages,
           count(*) FILTER (WHERE page_class = 'unknown')                AS unknown_pages,
           COALESCE(sum(slack) FILTER (WHERE page_class = 'entry'), 0)   AS entry_slack,
           COALESCE(sum(slack) FILTER (WHERE page_class IN ('data_leaf',
                                            'data_internal')), 0)        AS data_slack
    FROM pages
    GROUP BY idx
),
after AS (
    -- Evaluated once the census row for the index exists: a second size
    -- reading and the maintenance progress views, for the status column.
    SELECT c.idx,
           pg_relation_size(c.idx, 'main')                                   AS main_bytes_after,
           EXISTS (SELECT 1 FROM pg_stat_progress_vacuum v
                   WHERE v.relid = (SELECT tbl FROM gin_idx g WHERE g.idx = c.idx))
             OR EXISTS (SELECT 1 FROM pg_stat_progress_analyze z
                   WHERE z.relid = (SELECT tbl FROM gin_idx g WHERE g.idx = c.idx))
                                                                             AS maint_after,
           EXISTS (SELECT 1 FROM pg_stat_progress_create_index i
                   WHERE i.relid = (SELECT tbl FROM gin_idx g WHERE g.idx = c.idx))
                                                                             AS build_after
    FROM census c
),
verdict AS (
    SELECT m.idx, m.idx_name, m.main_bytes, m.bs, m.version,
           m.n_pending_pages, m.n_entry_pages, m.n_data_pages, m.n_total_pages,
           c.*, a.main_bytes_after,
           COALESCE(NULLIF(array_to_string(array_remove(ARRAY[
             CASE WHEN NOT (m.meta_layout_ok AND m.meta_flags = '{meta}'::text[])
                  THEN 'metapage unreadable' END,
             CASE WHEN m.version IS NOT NULL AND m.version <> 2
                  THEN 'unsupported format: version ' || m.version END,
             CASE WHEN c.invalid_pages > 0
                  THEN c.invalid_pages || ' page(s) not decodable' END,
             CASE WHEN c.unknown_pages > 0
                  THEN c.unknown_pages || ' page(s) of unknown class' END,
             CASE WHEN a.main_bytes_after <> m.main_bytes
                  THEN 'size changed during scan' END,
             CASE WHEN m.n_pending_pages IS NOT NULL AND c.pending_pages <> m.n_pending_pages
                  THEN 'pending count disagrees with metapage' END,
             CASE WHEN m.n_total_pages IS NOT NULL AND m.n_total_pages <> m.main_bytes / m.bs
                  THEN 'metapage page counts predate the file length' END,
             CASE WHEN m.maint_before OR a.maint_after
                  THEN 'vacuum or analyze in progress' END,
             CASE WHEN m.build_before OR a.build_after
                  THEN 'index build in progress' END
           ], NULL), '; '), ''), 'ok')                                       AS status,
           (m.version = 2 AND c.invalid_pages = 0 AND c.unknown_pages = 0)     AS slack_trusted
    FROM meta m
         JOIN census c ON c.idx = m.idx
         JOIN after  a ON a.idx = m.idx
)
SELECT v.idx_name                                       AS index_name,
       v.status,
       v.version                                        AS gin_version,
       v.main_bytes                                     AS main_fork_bytes,
       v.main_bytes / v.bs                              AS blocks,
       v.entry_pages, v.data_leaf_pages, v.data_internal_pages,
       v.uncompressed_pages, v.pending_pages, v.deleted_pages, v.new_pages,
       v.invalid_pages, v.unknown_pages,
       (v.deleted_pages + v.new_pages) * v.bs           AS whole_page_waste_bytes,
       round(100.0 * (v.deleted_pages + v.new_pages) * v.bs
             / nullif(v.main_bytes, 0), 2)              AS whole_page_waste_pct,
       CASE WHEN v.slack_trusted THEN v.entry_slack + v.data_slack END
                                                        AS live_page_slack_bytes,
       CASE WHEN v.slack_trusted
            THEN round(100.0 * (v.entry_slack + v.data_slack)
                       / nullif(v.main_bytes, 0), 2) END AS live_page_slack_pct,
       CASE WHEN v.slack_trusted
            THEN round(100.0 * ((v.deleted_pages + v.new_pages) * v.bs
                                + v.entry_slack + v.data_slack)
                       / nullif(v.main_bytes, 0), 2) END AS bloat_pct,
       CASE WHEN v.slack_trusted THEN v.entry_slack END  AS entry_slack,
       CASE WHEN v.slack_trusted THEN v.data_slack END   AS data_slack,
       v.pending_pages * v.bs                           AS pending_bytes,
       round(100.0 * v.pending_pages * v.bs
             / nullif(v.main_bytes, 0), 2)              AS pending_pct,
       CASE WHEN v.slack_trusted
            THEN v.main_bytes - (v.deleted_pages + v.new_pages + v.pending_pages) * v.bs
                              - v.entry_slack - v.data_slack END
                                                        AS payload_bytes,
       v.n_pending_pages                                AS meta_pending_pages,
       v.n_entry_pages                                  AS meta_entry_pages,
       v.n_data_pages                                   AS meta_data_pages,
       v.n_total_pages                                  AS meta_total_pages,
       1 + v.entry_pages + v.data_leaf_pages + v.data_internal_pages
         + v.uncompressed_pages + v.pending_pages + v.deleted_pages
         + v.new_pages + v.stray_meta_pages + v.invalid_pages + v.unknown_pages
                                                        AS census_total_pages,
       v.main_bytes_after / v.bs                        AS blocks_after_census
FROM verdict v
ORDER BY 1;
```

Add `AND c.oid = 'myschema.myindex'::regclass` to the `gin_idx` filter for a single
index, as before. What the statement cannot do: it does not make the scan atomic,
which [The measurement protocol](#the-measurement-protocol) now addresses with a
lock; it cannot see a VACUUM that starts and finishes between its two progress
reads; and it does not resolve the special-area size at runtime. The literal 8 is
`MAXALIGN(sizeof(GinPageOpaqueData))` on this build, a 4-byte block number, a
2-byte offset and a 2-byte flags word, and the metapage decoder checks the same
quantity, so every index the statement reports as readable has confirmed it —
[The derived-arithmetic statements](#the-derived-arithmetic-statements) replaces
that literal with a derived and separately measured value. A dropped index still
ends the statement with an error from `get_raw_page`, which resolves the name on
every call
([rawpage.c#get_raw_page_internal](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L141-L198)).

### The derived-arithmetic statements

**Nothing in the census is a typed-in size any more, and the four page-format
constants behind it are now measured on the running build rather than assumed.**
This is open question 17's remaining work, implemented and run on 2026-09-08. The
statements return the same numbers as before: 240 of 240 cells over eight indexes,
on two independently built databases.

Separate the two kinds of constant, because only one of them can be derived from a
catalog:

| Quantity | Kind | Where it now comes from |
|---|---|---|
| `BLCKSZ` | build option | `pg_control_init().database_block_size` |
| `MAXALIGN` | build option | `pg_control_init().max_data_alignment` |
| `MAXALIGN(sizeof(GinPageOpaqueData))` = 8 | struct of fixed-width fields | derived from `max_data_alignment`, and measured |
| `SizeOfPageHeaderData` = 24 | struct of fixed-width fields | measured |
| `sizeof(ItemIdData)` = 4 | three bit-fields, 32 bits | measured |

The three struct sizes cannot vary with a build option, which is why deriving them
from `pg_control_init()` is neither possible nor necessary. `PageHeaderData` is a
`PageXLogRecPtr`, six `uint16`s and a `TransactionId` before the line-pointer array,
and `SizeOfPageHeaderData` is `offsetof(PageHeaderData, pd_linp)` over exactly those
fields; `ItemIdData` is three bit-fields totalling 32 bits; `GinPageOpaqueData` is a
4-byte `rightlink`, a 2-byte `maxoff` and a 2-byte `flags`, and GIN's own header
comment says the opaque area "is only 8 bytes and so can be reliably distinguished
by size"
([bufpage.h#PageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L155-L168),
[bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L211-L214),
[itemid.h#ItemIdData](../../../../raw/postgres-17/src/include/storage/itemid.h#L25-L30),
[ginblock.h#GinPageOpaqueData](../../../../raw/postgres-17/src/include/access/ginblock.h#L19-L37)).

#### An empty GIN index measures the page format

The probe below turns all three into observations, and it works because of what
`PageInit` writes: `pd_lower = SizeOfPageHeaderData`, and
`pd_upper = pd_special = pageSize - MAXALIGN(specialSize)`
([bufpage.c#PageInit](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L42-L60)).
`GinInitPage` passes `sizeof(GinPageOpaqueData)` as that special size
([ginutil.c#GinInitPage](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L337-L347)),
and `ginbuild` initializes the entry-tree root with
`GinInitBuffer(RootBuffer, GIN_LEAF)`
([gininsert.c:348](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L348)). So
block 1 of a GIN index on an **empty** table is `PageInit`'s own output, and its
`page_header` row reads the two constants off the build directly. Add a second index
over one single-key row and the same page carries exactly one line pointer — GIN
places one entry tuple per key with `PageAddItem`
([ginentrypage.c:561-568](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L561-L568)) —
so the difference in `pd_lower` is `sizeof(ItemIdData)`.

```sql
SET /* wiki_gin_layout_guards */ statement_timeout = '10min';
SET /* wiki_gin_layout_guards */ lock_timeout = '2s';

CREATE TEMPORARY TABLE /* wiki_gin_layout_probe */ wiki_layout_e (tags int[]);
CREATE TEMPORARY TABLE /* wiki_gin_layout_probe */ wiki_layout_1 (tags int[]);
INSERT INTO /* wiki_gin_layout_probe */ wiki_layout_1 VALUES ('{1}');
CREATE INDEX /* wiki_gin_layout_probe */ wiki_layout_ei
    ON wiki_layout_e USING gin (tags) WITH (fastupdate = off);
CREATE INDEX /* wiki_gin_layout_probe */ wiki_layout_1i
    ON wiki_layout_1 USING gin (tags) WITH (fastupdate = off);

WITH /* wiki_gin_layout_probe */ ctl AS (
    SELECT database_block_size::bigint                          AS bs,
           max_data_alignment::bigint                           AS al,
           ((8 + max_data_alignment - 1) / max_data_alignment)
             * max_data_alignment                               AS gin_special_derived
    FROM pg_control_init()          -- 8 = sizeof(GinPageOpaqueData): 4-byte rightlink,
),                                  --     2-byte maxoff, 2-byte flags
e AS (   -- block 1 of a GIN index on an empty table is PageInit's own output:
         -- pd_lower = SizeOfPageHeaderData, pd_upper = pd_special = BLCKSZ - special
    SELECT h.lower AS hdr, h.upper AS e_upper, h.special AS e_special,
           h.pagesize AS e_pagesize, h.pagesize - h.special AS gin_special_seen,
           o.flags AS e_flags
    FROM (SELECT get_raw_page('wiki_layout_ei', 1) AS pg OFFSET 0) r
         LEFT JOIN LATERAL page_header(r.pg)            AS h ON true
         LEFT JOIN LATERAL gin_page_opaque_info(r.pg)   AS o ON true
),
one AS (  -- the same page holding exactly one entry tuple: one key, no null categories
    SELECT h.lower AS one_lower, o.flags AS one_flags, h.special - h.upper AS one_tuple_bytes
    FROM (SELECT get_raw_page('wiki_layout_1i', 1) AS pg OFFSET 0) r
         LEFT JOIN LATERAL page_header(r.pg)            AS h ON true
         LEFT JOIN LATERAL gin_page_opaque_info(r.pg)   AS o ON true
)
SELECT c.bs                                              AS block_size,
       c.al                                              AS max_data_alignment,
       e.hdr                                             AS page_header_bytes,
       o.one_lower - e.hdr                               AS line_pointer_bytes,
       e.gin_special_seen                                AS gin_special_bytes,
       c.gin_special_derived,
       c.bs - ((e.hdr + (o.one_lower - e.hdr) + c.al - 1) / c.al) * c.al
                                                         AS max_fsm_request_derived,
       o.one_tuple_bytes                                 AS one_entry_tuple_bytes,
       COALESCE(NULLIF(array_to_string(array_remove(ARRAY[
         CASE WHEN e.e_pagesize <> c.bs
              THEN 'empty-root pagesize ' || e.e_pagesize || ' <> block_size' END,
         CASE WHEN e.e_upper <> e.e_special
              THEN 'empty-root page is not untouched (upper <> special)' END,
         CASE WHEN e.e_flags <> '{leaf}'::text[]
              THEN 'empty-root flags ' || e.e_flags::text || ' <> {leaf}' END,
         CASE WHEN o.one_flags <> '{leaf}'::text[]
              THEN 'one-tuple root flags ' || o.one_flags::text || ' <> {leaf}' END,
         CASE WHEN e.gin_special_seen <> c.gin_special_derived
              THEN 'GIN special area ' || e.gin_special_seen || ' <> derived '
                   || c.gin_special_derived END,
         CASE WHEN o.one_lower <= e.hdr
              THEN 'one-tuple root has no line pointer' END
       ], NULL), '; '), ''), 'ok')                       AS status
FROM ctl c CROSS JOIN e CROSS JOIN one o;
```

On the pinned build it returns one row, and every constant the other statements use
appears in it:

```text
 block_size | max_data_alignment | page_header_bytes | line_pointer_bytes
       8192 |                  8 |                24 |                  4

 gin_special_bytes | gin_special_derived | max_fsm_request_derived
                 8 |                   8 |                    8160

 one_entry_tuple_bytes | status
                    24 | ok
```

Three of those are the numbers the earlier passes typed in: the entry-tuple probe's
`24` and `4`, and the guarded statement's `8`. The fourth, **8160**, is the FSM
cross-check's `MaxFSMRequestSize`, and it now comes out of the *measured* pair
rather than the literal 28 that [Four cross-checks](#four-cross-checks) uses — two
independent derivations landing on the same number on the same build. The probe
creates two throwaway indexes, so it needs the `TEMPORARY` privilege on the
database as well as the superuser rights the raw reads already require; the census
needs neither. Treat it as an auditor to run once per build, not as part of the
census.

#### The census, with the constant derived

The tested text is [The guarded census statement](#the-guarded-census-statement)
with seven substitutions, and nothing else. **Since 2026-09-15 it is also the text
this page scores**, carried in full by [the script](#the-postgresql-1711-leg) as the `CENSUS`
variable its every stage reads, so the substitution list below is a description of
how it differs from the guarded block rather than the only copy of it:

1. the tag `wiki_gin_waste_census_guarded` becomes `wiki_gin_waste_census_derived`;
2. a new leading `ctl` CTE supplies the block size, the alignment and the GIN
   special-area size;
3. `current_setting('block_size')::bigint AS bs` in `gin_idx` becomes
   `k.bs, k.gin_special`, with `CROSS JOIN ctl k` added to its `FROM`;
4. both occurrences of `h0.pagesize - h0.special = 8` — the `meta_layout_ok` test
   and the block-0 decoder guard — become `= g.gin_special`;
5. `h.pagesize - h.special <> 8` in the page `CASE` becomes `<> g.gin_special`, and
   the per-page decoder guard's `= 8` likewise;
6. `meta` also selects `h0.pagesize - h0.special AS meta_special_seen`;
7. one new `status` item is added, immediately after `metapage unreadable`.

```sql
WITH /* wiki_gin_waste_census_derived */ ctl AS (
    -- Both build-dependent quantities come from pg_control_init(), which is
    -- executable by PUBLIC and needs no extension.  8 is sizeof(GinPageOpaqueData)
    -- -- a 4-byte rightlink, a 2-byte maxoff and a 2-byte flags word -- and
    -- PageInit stores MAXALIGN of it as BLCKSZ - pd_special.
    SELECT database_block_size::bigint                          AS bs,
           max_data_alignment::bigint                           AS al,
           ((8 + max_data_alignment - 1) / max_data_alignment)
             * max_data_alignment                               AS gin_special
    FROM pg_control_init()
),
gin_idx AS (      -- ... unchanged apart from substitution 3
```

```sql
             CASE WHEN m.meta_special_seen IS NOT NULL
                   AND m.meta_special_seen <> m.gin_special
                  THEN 'metapage special area ' || m.meta_special_seen
                       || ' bytes, expected ' || m.gin_special END,
```

That item is the one behavioural addition: where the filed guarded statement reports
`metapage unreadable` for any unreadable block 0, the derived one says which test
failed. On the two metapage corruptions below it reads
`metapage unreadable; metapage special area 16 bytes, expected 8` and
`metapage unreadable; metapage special area 0 bytes, expected 8`; see
[Adversarial and acceptance cases](#adversarial-and-acceptance-cases).

Agreement, measured when the revision was filed on 2026-09-08 over eight rebuilt
fixtures in two independently built databases: **240 of 240 cells identical** to the
guarded statement, 208 of 208 shared cells identical to the baseline statement, and
240 of 240 identical between the two databases. Every run since has scored the
derived text alone, so none has a new cell-for-cell comparison to add; what they do
add is the eight corruption shapes, where the derived text survived all seven
SQL-visible patches in one multi-index report and the baseline text cannot
([Adversarial and acceptance cases](#adversarial-and-acceptance-cases)). Its cost
on this run's database is in [Cost of the census](#cost-of-the-census): the derived
arithmetic is one extra one-row CTE.

#### The entry-tuple probe, with the constants derived

The same treatment for [the probe](#counting-entry-tuples-and-what-that-fixes),
whose literal `/ 8192`, `- 24` and `/ 4` were the last typed-in sizes on the page.
It gains two counters and loses a version-specific guard:

```sql
SET /* wiki_gin_entry_probe_guards */ statement_timeout = '10min';
SET /* wiki_gin_entry_probe_guards */ lock_timeout = '2s';

WITH /* wiki_gin_entry_probe_derived */ ctl AS (
    -- bs and al are build-dependent and come from pg_control_init().  hdr and
    -- iid are page-format constants: SizeOfPageHeaderData is
    -- offsetof(PageHeaderData, pd_linp) over fixed-width fields, and ItemIdData
    -- is three bit-fields totalling 32 bits.  The layout probe measures all
    -- four on the running build.
    SELECT database_block_size::bigint                          AS bs,
           24::bigint                                           AS hdr,
           4::bigint                                            AS iid,
           ((8 + max_data_alignment - 1) / max_data_alignment)
             * max_data_alignment                               AS gin_special
    FROM pg_control_init()
),
pages AS (
    SELECT c.hdr, c.iid, o.flags, h.lower, h.upper, h.special, h.pagesize
    FROM ctl c
         CROSS JOIN LATERAL generate_series(
               1, pg_relation_size('myschema.myindex', 'main') / c.bs - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page('myschema.myindex', b.blkno::int) AS pg
                             OFFSET 0) AS r
         LEFT JOIN LATERAL page_header(r.pg) AS h ON true
         LEFT JOIN LATERAL gin_page_opaque_info(
               CASE WHEN h.upper > 0 AND h.pagesize = c.bs
                     AND h.pagesize - h.special = c.gin_special
                    THEN r.pg END)           AS o ON true
)
SELECT count(*)                        FILTER (WHERE flags = '{leaf}') AS entry_leaf_pages,
       sum((lower - hdr) / iid)        FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuples,
       sum(special - upper)            FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuple_bytes,
       sum((lower - hdr) / iid)        FILTER (WHERE flags = '{}')     AS internal_downlinks,
       count(*) FILTER (WHERE flags <@ '{leaf,incomplete_split}'::text[]
                          AND (lower < hdr OR (lower - hdr) % iid <> 0))
                                                                       AS malformed_pages,
       count(*) FILTER (WHERE flags IS NULL)                           AS undecoded_pages
FROM pages;
```

Four things to note about it.

- **The `pagesize > 0` guard is gone, and the 12.x hazard it existed for is closed
  structurally.** The published probe needs it because on 12.2 an all-zero page
  reports `flags = '{}'` and contributes `(0 - 24) / 4 = -6` downlinks. Here the
  decoder is never called for a page whose header fails, so a zeroed page produces
  `flags IS NULL` on any server and lands in `undecoded_pages` instead. On the
  appended-zero-block index `s5_gin` it counted both zeroed blocks
  ([Adversarial and acceptance cases](#adversarial-and-acceptance-cases)); the
  published probe has no column that can report them.
- **`malformed_pages` catches a corrupted `pd_lower` that the census absorbs
  silently.** With one entry page's `pd_lower` patched up by one byte, the census
  still says `ok` and reports one byte less entry slack than its untouched twin —
  25,659 against 25,660 on the 2026-09-24 pair — and the published probe returns
  byte-identical output. The derived probe reports `malformed_pages 1`.
- **The counter is restricted to entry-class pages on purpose.** On posting-tree
  pages `pd_lower` is a data-area offset, not a line-pointer count: compressed
  segments are `SHORTALIGN`-sized and internal data pages hold 10-byte
  `PostingItem`s, so `pd_lower - 24` need not be a multiple of four
  ([ginblock.h#SizeOfGinPostingList](../../../../raw/postgres-17/src/include/access/ginblock.h#L336-L344),
  [ginblock.h#PostingItem](../../../../raw/postgres-17/src/include/access/ginblock.h#L182-L188)). An
  unrestricted test flagged 15 pages on `f1_churn_gin`, 44 on `f2_pending_gin`, 64
  on `f5_deleted_gin` and 192 on `f6_slack_gin`, every one a healthy data page with
  residue 2 — measured in the 2026-09-08 pass with an unrestricted variant of the
  probe, which the published script deliberately does not carry. The restriction to
  `{leaf}` and `{}` is what the script runs, and it read `malformed_pages` 0 on all
  19 scored fixtures of the 2026-09-24 run, and 1 on the one index whose `pd_lower`
  was patched.
- **Every published column is unchanged.** The derived probe reproduced all four
  columns of the published probe exactly when the revision was filed, and it is the
  text the 2026-09-24 run used on all 19 scored fixtures: `entry_leaf_tuples`
  100,056 on `f1_churn_gin` and 50,028 on `f3_fresh_gin`, the same two numbers the
  published probe read in every earlier run of those fixtures.

### The measurement protocol

**One lock turns the statement's after-the-fact detection into enforcement, and it
is `SHARE ROW EXCLUSIVE` on the index's table.** This is open question 18's
remaining work. The `status` column stays useful for a report you cannot serialize;
when the comparison has to be exact, take the lock instead.

```sql
-- The measurement protocol: one transaction, one table lock, then the census.
-- SHARE ROW EXCLUSIVE conflicts with ROW EXCLUSIVE (writers), SHARE UPDATE
-- EXCLUSIVE (VACUUM, ANALYZE, REINDEX CONCURRENTLY), SHARE (plain REINDEX) and
-- ACCESS EXCLUSIVE (DROP INDEX, VACUUM FULL, CLUSTER), and is compatible with
-- ACCESS SHARE and ROW SHARE, so ordinary readers are unaffected.
BEGIN;
SET LOCAL /* wiki_gin_waste_protocol */ statement_timeout = '10min';
SET LOCAL /* wiki_gin_waste_protocol */ lock_timeout = '2s';
LOCK /* wiki_gin_waste_protocol */ TABLE myschema.mytable IN SHARE ROW EXCLUSIVE MODE;
-- run the guarded census here, restricted to the indexes of that one table
COMMIT;
```

Why that mode and not a weaker one, which commands it excludes, why the census
cannot hold a lock on the index between page reads, and what privilege the lock
needs are defined under [The measurement
lock](../../common-concepts/mandatory-gin-bloat-tests.md#the-measurement-lock). What
follows is this page's measurement of that rule on its own fixtures.

Measured on `tl_lock`, a 20,000-row `fastupdate` fixture built for this case alone,
with `lock_timeout = '2s'` in the second session and the protocol lock held in the
first:

| Second session ran | Result |
|---|---|
| `INSERT INTO tl_lock VALUES (-1, '{1}')` | blocked, cancelled at **2022 ms** |
| `VACUUM tl_lock` | blocked, **2018 ms** |
| `ANALYZE tl_lock` | blocked, **2021 ms** |
| `REINDEX INDEX l1_lock_gin` | blocked, **2020 ms** |
| `REINDEX INDEX CONCURRENTLY l1_lock_gin` | blocked, **2019 ms** |
| [`VACUUM FULL tl_lock`](../../../glossary.md#vacuum-full) | blocked, **2024 ms** |
| `DROP INDEX l1_lock_gin` | blocked, **2024 ms** |
| [`CLUSTER tl_lock USING tl_lock_pkey`](../../../glossary.md#cluster) | blocked, **2021 ms** |
| `SELECT count(*) FROM tl_lock` | **succeeded**, 16 ms, 20,000 rows |
| `SELECT gin_clean_pending_list('l1_lock_gin')` | **succeeded**, 13 ms, returning 0 |

Every cancellation reported `canceling statement due to lock timeout`. The lock
experiment runs on its own fixture rather than on a scored one, because one of the
ten commands is a `DROP INDEX` and no scored number should depend on a lock actually
holding.

**The paired concurrency run is the point of the whole thing.** Two identical
898-block `f5`-shaped fixtures, each with 95% of its heap deleted and neither
vacuumed yet:

| Loop | Censuses | What they read |
|---|---|---|
| no lock, censuses back to back across one VACUUM of `tr_race` | 4 during the VACUUM, 3 after | the 4 read **four different** deleted-page counts between 0 and 768 on a file that stayed at 898 blocks, and 3 of the 4 were flagged `vacuum or analyze in progress`; the 3 after read `ok, 768` |
| protocol lock held on `tr2_race`, its VACUUM queued behind | 20 | **20 of 20 identical**, `ok` with 0 deleted pages. The queued VACUUM waited **3219 ms**, then reported `898 in total, 768 newly deleted, 768 currently deleted, 0 reusable`, and the next census read 768 |

That is the difference between detecting a mixed-instant reading and not producing
one, and the queued VACUUM shows the protocol delays maintenance rather than
breaking it.

**The one hole, and a table lock cannot close it.** `gin_clean_pending_list` opens
the *index* with `RowExclusiveLock` and never touches the table
([ginfast.c:1034](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1034)), and
`LOCK TABLE` refuses an index outright — `RangeVarCallbackForLockTable` allows only
a plain table, a partitioned table or a view
([lockcmds.c#RangeVarCallbackForLockTable](../../../../raw/postgres-17/src/backend/commands/lockcmds.c#L70-L107)).
Measured on a 303-block `fastupdate` index with 293 pending pages, from inside one
protocol transaction:

| Step | `blocks` | `pending_pages` | `deleted_pages` | `bloat_pct` | `pending_pct` |
|---|---|---|---|---|---|
| census, lock held | 303 | 293 | 0 | **1.46** | 96.70 |
| another session ran `gin_clean_pending_list()`, which returned 293 | — | — | — | — | — |
| census again, same transaction, same lock | **328** | 0 | **293** | **92.00** | 0.00 |

Neither census was flagged for the flush: each took its own before-and-after size
reading and each was internally consistent, because the flush landed *between*
them, and the only `status` item either carried was `metapage page counts predate
the file length`, which a fastupdate index in mid-growth carries anyway. So the
protocol's guarantee is precisely "no heap-mediated writer and no maintenance
command", and it needs one operational rule beside it: the index's owner must not
flush the pending list during the measurement. That function requires ownership, so
on a production box it is a matter of not running it
([ginfast.c:1061-1064](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1061-L1064)).

Two costs to weigh before using it. The lock blocks every writer on the table for
the whole census — this run's locked decide pass over 26 GIN indexes and 23,743
blocks held `ShareRowExclusiveLock` on every table in the database for **214 ms**,
but the census is one buffer read per block, so a multi-GB index is a different
proposition — so [`lock_timeout`](../../../glossary.md#statement_timeout-and-lock_timeout) and a maintenance window matter. Before 2026-09-24
this sentence gave the corpus as 28 indexes over 15,201 blocks: that is the database
after the oracle's rebuilds, the [invalid index](../../../glossary.md#invalid-index) included, as the sweep stage counts
it, not the decide pass. And the privilege
is not `SELECT`: `LockTableAclCheck` accepts `MAINTAIN`, `UPDATE`, `DELETE` or
`TRUNCATE` for every mode above `ROW EXCLUSIVE`, adding `SELECT` only at
`ACCESS SHARE`
([lockcmds.c#LockTableAclCheck](../../../../raw/postgres-17/src/backend/commands/lockcmds.c#L279-L299),
[lock.sgml#privileges](../../../../raw/postgres-17/doc/src/sgml/ref/lock.sgml#L167-L179)). In
practice the census already needs superuser for its raw reads, so this binds only a
`pgstatginindex`-only reader.

### Adversarial and acceptance cases

One section replaces the two earlier pass-by-pass records, because the cases that
survived the re-port were re-run and the ones that could not be re-run are gone. The
`VACUUM` whose index cleanup did not run left on 2026-09-24, because the protocol no
longer allows a fixture to switch index cleanup off; see
[What this pass removed, and why](#what-this-pass-removed-and-why). Every result
below is from the 2026-09-24 run described under
[Measurement Script](#measurement-script), and the statement under test is the
derived census unless a row says otherwise.

**Eight corrupted index files.** Eight 7-block scratch indexes in their own
database, patched with the server stopped, at offsets read off the live pages first:
`PageHeaderData` puts `pd_lower` at byte 12, `pd_upper` at 14 and `pd_special` at
16; the GIN opaque flags word is the last two bytes of the page; and the metapage's
`ginVersion` sits 72 bytes in, after 24 bytes of page header and 48 bytes of earlier
metapage fields
([bufpage.h#PageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L155-L168),
[ginblock.h#GinPageOpaqueData](../../../../raw/postgres-17/src/include/access/ginblock.h#L30-L37),
[ginblock.h#GinMetaPageData](../../../../raw/postgres-17/src/include/access/ginblock.h#L55-L103)).

| Index | Patch | What the derived census reported |
|---|---|---|
| `s1_gin` | `ginVersion` 2 -> 1 | `unsupported format: version 1`; every slack-derived field NULL, page counts printed |
| `s2_gin` | block 0 zeroed | `metapage unreadable; metapage special area 0 bytes, expected 8`; the four `meta_*` columns and the slack fields NULL, 6 entry pages still counted |
| `s3_gin` | flag bit `0x0100` set on block 1 | `1 page(s) of unknown class`; `unknown_pages` 1, entry pages 5 instead of 6, slack withheld |
| `s4_gin` | block 1 `pd_special` 8184 -> 8168 | `1 page(s) not decodable`; `invalid_pages` 1, slack withheld, **and the other seven indexes still reported** |
| `s5_gin` | two all-zero blocks appended | 9 blocks, `new_pages` 2, waste **22.22%**, `bloat_pct` 57.03, status `metapage page counts predate the file length` |
| `s6_gin` | block 0 `pd_upper` and `pd_special` both 8184 -> 8176 | `metapage unreadable; metapage special area 16 bytes, expected 8` |
| `s7_gin` | block 1 `pd_lower` +1 | **`ok`**, and one byte less entry slack than its twin (25,659 against 25,660) — no signal at all from the census |
| `s8_gin` | block 0 `pd_special` 8184 -> 8168, `pd_upper` left at 8184 | `ERROR: invalid page in block 0 of relation base/17536/18549` — the read never reaches any SQL guard, and it takes the whole multi-index report with it. The path is a database [OID](../../../glossary.md#oid) and a [relfilenode](../../../glossary.md#relfilenumber), so it is the one literal in this table that moves between runs |

Three things follow. The derived statement **survived all seven SQL-visible patches
in one multi-index report**, which is the difference the guards buy: the baseline
text aborts on `s4` and `s6`. `s7` is the shape no census can see, and the
[entry-tuple probe](#counting-entry-tuples-and-what-that-fixes) is what catches it —
it reported `malformed_pages 1` on `s7` where the census said `ok`. And `s8` is the
boundary of what any SQL-level guard can do: `PageIsVerifiedExtended` admits a page
only when `pd_lower <= pd_upper <= pd_special <= BLCKSZ` and `pd_special` is
`MAXALIGN`ed, so breaking `pd_upper <= pd_special` makes the buffer manager raise
before `pageinspect` sees anything
([bufpage.c#PageIsVerifiedExtended](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L88-L124)).
The only way past it is `zero_damaged_pages`, which is [`PGC_SUSET`](../../../glossary.md#guc-context) — session scope
for a superuser, no reload — and which the documentation is explicit about: it
"will destroy data, namely all the rows on the damaged page"
([guc_tables.c#zero_damaged_pages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1123-L1136)).
With it on, the same census returned
`WARNING: invalid page in block 0 ...; zeroing out page` and then
`metapage unreadable; metapage special area 0 bytes, expected 8`. Use it on a copy,
never to get a census out of a production index.

**An all-zero page, deterministically.** `s5_gin`'s two appended zero blocks are the
`PageIsNew` case, and they behave exactly as the census's NULL handling predicts: 2
`new_pages`, 16,384 bytes of whole-page waste, and `undecoded_pages 2` from the
derived probe, which is the only column on the page that can report them. The FSM
cannot see them at all.

**An invalid index, and both temporary cases.** A [`CREATE INDEX CONCURRENTLY`](../../../glossary.md#concurrently) whose
expression divided by zero on one row left `tinv_bad` with [`indisvalid`](../../../glossary.md#pg_index) false,
`indisready` false and `indislive` true. The census excludes it (0 rows), while
`gin_metapage_info(get_raw_page('tinv_bad', 0))` reads `version 2`,
`pgstatginindex` refuses with `index "tinv_bad" is not valid`, and
`gin_clean_pending_list` returns 0 on the `DEBUG1` no-op path. Another session's
temporary GIN index appeared in the catalogs as `pg_temp_74.ott_gin`: the census
excludes it, `get_raw_page` refuses with
`cannot access temporary tables of other sessions`, `pgstatginindex` with
`cannot access temporary indexes of other sessions`, and `pg_freespace` answers
anyway with 2 rows. The session's own temporary index is excluded by the
`relpersistence` filter and readable by `get_raw_page`.

### The bloat percentage column

`bloat_pct` is the added derived column — dead pages plus live-page
slack, over the main fork:

```text
bloat_pct = 100 * ((deleted_pages + new_pages) * block_size
                   + entry_slack + data_slack) / main_fork_bytes
```

Every term is already in the census, so the column reads no page the census does not
read anyway. It is gated on `gin_version = 2` exactly like the slack columns,
because `pd_lower` — which the slack term is built from — is only trustworthy in a
version-2 index
([ginblock.h#GinMetaPageData](../../../../raw/postgres-17/src/include/access/ginblock.h#L85-L103),
[ginblock.h:302-309](../../../../raw/postgres-17/src/include/access/ginblock.h#L302-L309)). On the
version-1 corruption fixture it returned NULL. The baseline statement still exposes
`entry_slack`, `data_slack` and `payload_bytes` without the version guard; do not
interpret the untrusted components as measured payload or space. The
[guarded](#the-guarded-census-statement) and
[derived](#the-census-with-the-constant-derived) statements withhold all three, and
`bloat_pct`, unless the version is 2 and every page decoded to a known class. Page
counts and pending bytes remain separate outputs.

**`bloat_pct` is the column the run declared an upper bound, and it held on 19 of
19.** The scored table is in
[What the census meant against REINDEX](#what-the-census-meant-against-reindex); the
seven core fixtures read:

| Fixture | `bloat_pct` | `whole_page_waste_pct` | REINDEX reclaimed % | over-read |
|---|---|---|---|---|
| `f1_churn_gin` | 64.12 | 0.65 | 42.38 | +21.74 |
| `f2_pending_gin` | 75.30 | 64.64 | 58.05 | +17.25 |
| `f3_fresh_gin` | 48.09 | 0.00 | 0.00 | **+48.09** |
| `f4_empty_gin` | 49.80 | 0.00 | 0.00 | **+49.80** |
| `f5_deleted_gin` | 95.22 | 85.52 | 89.09 | +6.13 |
| `f6_slack_gin` | 51.34 | 0.00 | 46.33 | +5.01 |
| `f7_reupdate_gin` | 54.15 | 9.89 | 13.26 | +40.89 |

Four things the column does not mean:

1. **It is not reclaimable space, and on a healthy index it is not close.**
   `f3_fresh_gin` was never churned: it reads **48.09** and `REINDEX` returns
   **0 bytes** — the same 10,125,312 bytes before and after. `f4_empty_gin` indexes
   an empty table — one metapage and one entry page — and reads **49.80**, because
   that entry page is 8,160 bytes empty. The floor is structural rather than
   accidental: `entrySplitPage` [splits](../../../glossary.md#page-split) a full entry page by equalizing data size, so
   a fresh build leaves its pages about half full
   ([ginentrypage.c#entrySplitPage](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L666-L691)).
   Over-read across the 19 scored fixtures ran from **+5.01 to +49.80 points**, and
   the freshly rebuilt indexes themselves read 12.04 to 56.72 with nothing left to
   take.
2. **It held as an upper bound here, and that is 19 fixtures, not a proof.** The
   corpus that produced the page's two pre-protocol upper-bound violations is gone
   from this page — the 800,000-row `jsonb_path_ops` fixture and the pending-grown
   `tsvector` one were never published in reproducible form — so the shape that
   broke it, a large dead-entry-tuple population sitting inside `payload_bytes`
   where neither term can see it, is **unrepresented** in this run
   ([README:389-396](../../../../raw/postgres-17/src/backend/access/gin/README#L389-L396)). The
   closest surviving case is `g100_gin` with about 100,000 dead entry tuples, where
   the column over-read by 10.63 points rather than failing. Treat the 19 of 19 as
   "not refuted here", and see [Open Questions](#open-questions).
3. **It excludes the pending list**, which is what step 3 of
   [the procedure](#the-procedure) is for. Censused with 490 pending pages live, the
   `f2` fixture read `bloat_pct` **16.62** beside `pending_pct` **64.64**; after the
   flush and the settle step the same file read **75.30** with no pending pages, and
   `REINDEX` then returned 58.05% of it. The lock experiment shows the same swing
   inside one transaction: 1.46 to 92.00 across a flush
   ([The measurement protocol](#the-measurement-protocol)).
4. **It is not the sum of the two rounded columns.** It rounds the summed bytes
   once, so it can land 0.01 above `whole_page_waste_pct + live_page_slack_pct`:
   `f2_pending_gin` prints 64.64 and 10.65, which add to 75.29, against a
   `bloat_pct` of **75.30**.

So the column earns its place for one job — comparing an index against its own
earlier readings, or against a rebuilt twin — and for no other. A single reading of
a single index says almost nothing, because about half of it is the fill fraction of
any GIN build.

### Four cross-checks

All four are required by [The four mandatory
cross-checks](../../common-concepts/mandatory-gin-bloat-tests.md#the-four-mandatory-cross-checks),
which defines what each one compares and in which direction it can fail. Below is
the SQL this page runs for them, and what they read in the 2026-09-24 run: the FSM
check and the identity on its 24 fixture indexes, the metapage counts on all 26
indexes the decide census saw.

**FSM.** `pg_freespace` reports the recorded value per block
([pg_freespacemap.c#pg_freespace](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap.c#L24-L50)),
and for indexes the documentation says the value is meaningful only as
in-use-versus-empty
([pgfreespacemap.sgml:61-71](../../../../raw/postgres-17/doc/src/sgml/pgfreespacemap.sgml#L61-L71)). A free index
page reads `MaxFSMRequestSize`. Its count can match `deleted + new` only when
those deleted pages are recyclable, the free pages have been recorded, and no
intervening allocation or maintenance changes the compared states
([ginvacuum.c:766-794](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L766-L794),
[ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829),
[indexfsm.c#GetFreeIndexPage](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L32-L45)). Derive
the constant rather than typing 8160 — `pg_control_init()` publishes both terms of
`BLCKSZ - MAXALIGN(SizeOfPageHeaderData + sizeof(ItemIdData))`, is executable by
`PUBLIC` (measured: a role holding only `pg_stat_scan_tables` read `8 | 8192` from
it), and needs no extension:

```sql
SELECT /* wiki_gin_waste_fsm_check */
       (SELECT database_block_size
               - ((28 + max_data_alignment - 1) / max_data_alignment)
                 * max_data_alignment          -- 28 = SizeOfPageHeaderData + sizeof(ItemIdData)
        FROM pg_control_init())                          AS free_page_avail,
       count(*) FILTER (WHERE avail = (SELECT database_block_size
               - ((28 + max_data_alignment - 1) / max_data_alignment)
                 * max_data_alignment FROM pg_control_init())) AS fsm_free_pages,
       count(*)                                          AS blocks
FROM pg_freespace('myschema.myindex');
```

On the pinned build that expression returned **8160** on all 24 indexes, equal to
the value the [layout probe](#an-empty-gin-index-measures-the-page-format) reaches
from its two measured struct sizes. Do not take the number from the category
table's own comment, which is illustrative and stale; see
[Deviations from the brief](#deviations-from-the-brief-and-why). The check is
one-directional and behaved that way: `fsm_free_pages <= deleted + new` held **24 of
24**, with exact equality on the nine fixtures whose deleted pages had all become
recyclable — `f2` 490/490, `f5` 768/768, `f8` 768/768, `f15` 197/197, `a1` 49/49,
`g25` 46/46, `g50` 39/39, `g75` 45/45, `g100` 39/39 — a partial count on `f7`,
whose FSM holds 66 of its 144 deleted pages, and a deliberate shortfall on the four
whose pages were deleted but not yet recyclable: `f1` 14 deleted against 0 free, `f12` 282 against 0, `f14` 14 against 0,
`g0` 46 against 0.

**Size bracket.** Read `pg_relation_size` again after the census and compare it
with the statement's own `blocks` column.

```sql
SELECT /* wiki_gin_waste_size_bracket */
       pg_relation_size('myschema.myindex','main') / current_setting('block_size')::bigint
       AS blocks_after_census;
```

The guarded and derived statements take this second reading themselves and print it
as `blocks_after_census`, flagging any difference in `status`. Under the protocol
lock it held on **19 of 19** scored fixtures, and the oracle's before-size equalled
the decide census's `main_fork_bytes` on 19 of 19 as well, which is the same bracket
one step wider. Without the lock it is the check that earns its place: 10 of 30
censuses taken under a writer stream were flagged `size changed during scan`; see
[Concurrency](#concurrency-a-census-of-a-busy-index-is-a-mixed-instant-reading).

**VACUUM VERBOSE.** The fourth number of the index line is `pages_free`
([vacuumlazy.c:718-731](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L731)), and
the maintenance step is a `VACUUM (VERBOSE, ANALYZE)`, so every scored fixture
produced one:

```text
index "f5_deleted_gin": pages: 898 in total, 0 newly deleted, 0 currently deleted, 768 reusable
```

Its `reusable` number agreed with the FSM count on **every** fixture that produced a
line — `f5` 768, `f2` 490, `f15` 197, `f7` 66, `g25` 46, `g50` 39, `g75` 45, `g100`
39, and 0 where the FSM held nothing — which is expected, because both come from
`ginvacuumcleanup`'s own `totFreePages`. It agrees only for the VACUUM that produced
the state: `f5`'s settle sequence printed `768 newly deleted, 768 currently deleted,
0 reusable`, then `0 / 0 / 768 reusable` from the VACUUM that followed the three
burned transaction ids, and the same line twice more; the `0 / 0 / 0` shape belongs
to `f8_horizon`, whose second VACUUM finds nothing recyclable because a snapshot is
still held ([Deleted pages need the horizon to move before they
count](#deleted-pages-need-the-horizon-to-move-before-they-count)). `f5`'s B-tree
sibling on the same table printed `551 in total, 0 newly deleted, 520 currently
deleted, 520 reusable` — the shape GIN never prints, because GIN increments
`pages_deleted` only for pages it deleted in this run.

**Metapage page-type counts.** After a VACUUM, `n_entry_pages` and `n_data_pages`
are `ginvacuumcleanup`'s own census
([ginvacuum.c:766-789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L766-L789)), so they must
match the SQL census of live pages. `n_entry_pages` matched **23 of 26** censused
indexes, and all three misses are indexes whose metapage is stale by construction —
each grew, or had its pending list flushed, after its last cleanup. Two are off by
exactly one page: the auto-analyze stand-in `a1_analyze_gin` (42 against 43) and the
census table `c1_analyzed_gin` (5 against 6). The third is the lock fixture
`l1_lock_gin` (**9 against 34**), whose 293 pending pages were flushed by
`gin_clean_pending_list()` with no VACUUM after it; that is the same mechanism as
`a1`, at a size where it is impossible to miss. The 2026-09-15 filing counted two
misses and 25 agreements, and both 2026-09-16 passes three and 24; this run, which no
longer builds `f9c_cleanup_gin`, counts three and 23.

The data-page bucket needs both of the code's caveats, and together they make an
exact identity rather than a rule of thumb. `GinPageIsRecyclable` is tested before
`GinPageIsData`, so a deleted page that is not yet recyclable is counted as a
**data** page while a recyclable one is recorded free instead
([ginvacuum.c#ginvacuumcleanup-census](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L789)).
So:

```text
n_data_pages = live data pages + (deleted_pages - fsm_free_pages)
```

That held on **24 of 24** indexes: plain agreement where nothing was deleted (`f6`
896, `m1` 480, `f5` 128), the deleted pages folded in where none was recyclable
(`f1` 63 + 14 = 77, `f12` 1401 + 282 = 1683, `f14` 63 + 14 = 77, `g0` 87 + 46 =
133), and the partial case where some were (`f7` 111 + 144 − 66 = 189). A live
`list` page is counted in no bucket at all, which is why `n_total_pages` can exceed
`1 + n_entry_pages + n_data_pages`; `n_total_pages = blocks` on **23 of 26**, failing
only on the same three stale-metapage indexes (43 against 93, 6 against 7, and 10
against 328).

### The fixtures

**19 scored fixtures and 5 coverage fixtures, and the only copy of their SQL is the
published script.** That is the change this pass made to the corpus: the recipes are
no longer prose that a reader has to reassemble, they are the `10_build.sql` and
`20_churn.sql` heredocs of
[the script](#the-postgresql-1711-leg), which is what produced every number below. The
generators are deterministic — no `random()`, no ordering dependence — and every
recipe ends in the protocol's fixed order: the writes, the settle step, then the
maintenance step, then the census.

| Fixture | What it is | Churn | Settle | Maintenance |
|---|---|---|---|---|
| `f1_churn` | `tsvector` over 200,000 rows, `fastupdate = off` | every row's term set replaced | 2 VACUUMs | `VACUUM (VERBOSE, ANALYZE)` |
| `f2_pending` | `int[]`, `fastupdate = on`, built at 150,000 rows | 50,000 rows left in the pending list, then `gin_clean_pending_list()` | 2 VACUUMs | `VACUUM (VERBOSE, ANALYZE)` |
| `f3_fresh` | untouched twin holding `f1`'s post-churn content | none | build-phase `VACUUM ANALYZE` | build-phase [`ANALYZE`](../../../glossary.md#statistics) |
| `f4_empty` | empty table | none | build-phase `VACUUM ANALYZE` | build-phase `ANALYZE` |
| `f5_deleted` | 32 keys per row over 200,000 rows, plus a B-tree sibling | first 95% of the heap deleted | 3 VACUUMs with 3 transaction ids burned between the first and second | `VACUUM (VERBOSE, ANALYZE)` |
| `f6_slack` | same shape | every other row deleted | 2 VACUUMs | `VACUUM (VERBOSE, ANALYZE)` |
| `f7_reupdate` | `tsvector`, same terms rewritten three times | three rewrite passes | a VACUUM after each pass, then one more | `VACUUM (VERBOSE, ANALYZE)` |
| `f11_json` | `jsonb_path_ops` over 200,000 rows | every key replaced | 2 VACUUMs | `VACUUM (VERBOSE, ANALYZE)` |
| `f12_trgm` | `gin_trgm_ops` over 200,000 text rows | every trigram source replaced | 2 VACUUMs | `VACUUM (VERBOSE, ANALYZE)` |
| `f13_btgin` | [`btree_gin`](../../../glossary.md#btree_gin-and-btree_gist) over `int` mod 20011 | every value moved into a disjoint range | 2 VACUUMs | `VACUUM (VERBOSE, ANALYZE)` |
| `f14_multi` | multicolumn `gin (tags, to_tsvector(...))` | both key columns replaced | 2 VACUUMs | `VACUUM (VERBOSE, ANALYZE)` |
| `f15_partial` | `gin (tags) WHERE live`, 10% of rows live | keys replaced and the predicate column rewritten | 2 VACUUMs | `VACUUM (VERBOSE, ANALYZE)` |
| `g0` `g25` `g50` `g75` `g100` | the churn sweep: keys owned by groups of four consecutive ids | 100% of rows updated, p% of the key population replaced | 2 VACUUMs | `VACUUM (VERBOSE, ANALYZE)` |
| `m1_pair` | the maintenance pair, `int[]` at 100,000 rows | every other row deleted, censused after the writes, after the settle and after the maintenance | 2 VACUUMs | `VACUUM (VERBOSE, ANALYZE)` |
| `a1_analyze` | the auto-analyze stand-in, `fastupdate = on` at 20,000 rows | 4,999 inserts, which cross the analyze verdict and neither vacuum verdict | **none — it may not claim the settle step** | `ANALYZE` + `gin_clean_pending_list()` |

The five coverage fixtures are not scored against the oracle, because each one exists
to hold a state the protocol names rather than to be measured for waste:
`f8_horizon` (a snapshot held across the settling VACUUM) and `c1_analyzed`,
`c2_declined`, `c3_boundary` and `c4_hazard` (the census's four verdict cases), plus
the `tl_lock`, `tr_race`, `tr2_race`, `tw_race`, `an_cat` and `s1`-`s8` fixtures that
belong to the lock, concurrency, catalog and corruption cases in their own sections,
and the `pt_*` and `pm_*` fixtures of the portability stage, which is outside the
protocol. A sixth coverage fixture, `f9c_cleanup`, was removed on 2026-09-24; see
[What this pass removed, and why](#what-this-pass-removed-and-why).

`f1` and `f7` are the two churn shapes that matter, and the difference is the key
population: `f1` replaces every term, so the old terms keep entry tuples with empty
posting lists, while `f7` rewrites the same terms three times and only churns their
[TIDs](../../../glossary.md#tid). They score very differently below.

**What reproduced from the superseded corpus, and what did not.** Six of the seven
core fixtures came out byte-identical to the numbers this page has carried since
2026-08-26 — `f1` at 17,571,840 churned bytes, `f2` at 2,195,456 built and 6,209,536
churned with 490 pending pages flushed, `f4` at 16,384, `f5` and `f6` at 7,356,416
with 768 and 0 deleted pages, `f7` at 11,927,552 with 144 — and so did all five
churn-sweep sizes and every rebuild but one. The exception is the pair `f3` and
`f1`'s rebuild, which came out **8,192 bytes larger** than filed (10,125,312 against
10,117,120, one entry page); they still equal each other exactly, which is the
self-check that pair exists for. The only recipe change that could account for it is
the protocol's own build-phase settle step, which the superseded recipe did not run
and which changes where `f1`'s churn puts its new heap tuples; this run does not
prove that, so it is [an open question](#open-questions). `f11`-`f15` are **new
fixtures with published recipes**, not reproductions: the numbers the page used to
carry for those names came from recipes it never published.

### What the census meant against REINDEX

`REINDEX INDEX` before/after `pg_relation_size` is the oracle, and `truth_pct` below
is computed from those two readings and nothing else. Every row was censused inside
the one locked decide transaction and rebuilt at `maintenance_work_mem = 64MB`.

| Fixture | bytes | blocks | entry / data-leaf / data-int / pending / deleted |
|---|---|---|---|
| `f1_churn_gin` | 17,571,840 | 2145 | 2067 / 49 / 14 / 0 / 14 |
| `f2_pending_gin` | 6,209,536 | 758 | 170 / 97 / 0 / 0 / 490 |
| `f3_fresh_gin` | 10,125,312 | 1236 | 1200 / 28 / 7 / 0 / 0 |
| `f4_empty_gin` | 16,384 | 2 | 1 / 0 / 0 / 0 / 0 |
| `f5_deleted_gin` | 7,356,416 | 898 | 1 / 96 / 32 / 0 / 768 |
| `f6_slack_gin` | 7,356,416 | 898 | 1 / 864 / 32 / 0 / 0 |
| `f7_reupdate_gin` | 11,927,552 | 1456 | 1200 / 102 / 9 / 0 / 144 |
| `f11_json_gin` | 20,062,208 | 2449 | 2448 / 0 / 0 / 0 / 0 |
| `f12_trgm_gin` | 17,842,176 | 2178 | 494 / 1186 / 215 / 0 / 282 |
| `f13_btgin_gin` | 4,628,480 | 565 | 564 / 0 / 0 / 0 / 0 |
| `f14_multi_gin` | 14,737,408 | 1799 | 1721 / 49 / 14 / 0 / 14 |
| `f15_partial_gin` | 2,359,296 | 288 | 90 / 0 / 0 / 0 / 197 |
| `g0_gin` | 8,323,072 | 1016 | 882 / 78 / 9 / 0 / 46 |
| `g25_gin` | 10,067,968 | 1229 | 1095 / 78 / 9 / 0 / 46 |
| `g50_gin` | 11,894,784 | 1452 | 1304 / 92 / 16 / 0 / 39 |
| `g75_gin` | 13,615,104 | 1662 | 1514 / 86 / 16 / 0 / 45 |
| `g100_gin` | 15,261,696 | 1863 | 1722 / 85 / 16 / 0 / 39 |
| `m1_pair_gin` | 3,948,544 | 482 | 1 / 448 / 32 / 0 / 0 |
| `a1_analyze_gin` | 761,856 | 93 | 43 / 0 / 0 / 0 / 49 |

The scored table. `waste %` is the declared **lower bound**, `bloat %` the declared
**upper bound**, and the two verdict columns are what the protocol asks a run to
record:

| Fixture | waste % | slack % (entry / data bytes) | bloat % | truth % | rebuilt bytes | lower bound | upper bound |
|---|---|---|---|---|---|---|---|
| `f1_churn_gin` | 0.65 | 63.47 (10,860,592 / 292,062) | 64.12 | 42.38 | 10,125,312 | HELD | HELD |
| `f2_pending_gin` | 64.64 | 10.65 (318,084 / 343,360) | 75.30 | 58.05 | 2,605,056 | **VIOLATED** | HELD |
| `f3_fresh_gin` | 0.00 | 48.09 (4,804,268 / 65,192) | 48.09 | 0.00 | 10,125,312 | HELD | HELD |
| `f4_empty_gin` | 0.00 | 49.80 (8,160 / 0) | 49.80 | 0.00 | 16,384 | HELD | HELD |
| `f5_deleted_gin` | 85.52 | 9.70 (7,520 / 706,048) | 95.22 | 89.09 | 802,816 | HELD | HELD |
| `f6_slack_gin` | 0.00 | 51.34 (7,520 / 3,769,344) | 51.34 | 46.33 | 3,948,544 | HELD | HELD |
| `f7_reupdate_gin` | 9.89 | 44.26 (4,804,900 / 474,758) | 54.15 | 13.26 | 10,346,496 | HELD | HELD |
| `f11_json_gin` | 0.00 | 51.95 (10,421,544 / 0) | 51.95 | 34.87 | 13,066,240 | HELD | HELD |
| `f12_trgm_gin` | 12.95 | 58.86 (3,175,200 / 7,325,956) | 71.80 | 62.26 | 6,733,824 | HELD | HELD |
| `f13_btgin_gin` | 0.00 | 64.62 (2,990,980 / 0) | 64.62 | 48.50 | 2,383,872 | HELD | HELD |
| `f14_multi_gin` | 0.78 | 59.79 (8,520,440 / 291,050) | 60.57 | 44.47 | 8,183,808 | HELD | HELD |
| `f15_partial_gin` | 68.40 | 20.75 (489,568 / 0) | 89.15 | 80.90 | 450,560 | HELD | HELD |
| `g0_gin` | 4.53 | 46.41 (3,579,264 / 283,496) | 50.94 | 6.89 | 7,749,632 | HELD | HELD |
| `g25_gin` | 3.74 | 50.62 (4,812,888 / 283,696) | 54.36 | 23.03 | 7,749,632 | HELD | HELD |
| `g50_gin` | 2.69 | 54.38 (6,014,148 / 454,672) | 57.07 | 34.37 | 7,806,976 | HELD | HELD |
| `g75_gin` | 2.71 | 56.04 (7,223,548 / 405,818) | 58.74 | 43.08 | 7,749,632 | HELD | HELD |
| `g100_gin` | 2.09 | 57.76 (8,416,684 / 397,790) | 59.85 | 49.22 | 7,749,632 | HELD | HELD |
| `m1_pair_gin` | 0.00 | 54.55 (7,520 / 2,146,368) | 54.55 | 46.47 | 2,113,536 | HELD | HELD |
| `a1_analyze_gin` | 52.69 | 17.83 (135,824 / 0) | 70.52 | 45.16 | 417,792 | **VIOLATED** | HELD |

**19 scored, 17 lower-bound HELD, 2 VIOLATED, 19 upper-bound HELD, 0 bracket
failures.** `f1` rebuilt to exactly its untouched twin's size and page-class census,
which is a second self-check on that pair. The two lower-bound violations share one
mechanism and get their own section:
[Whole-page waste is not a lower bound](#whole-page-waste-is-not-a-lower-bound).

**The baseline phase is what makes those numbers a before-and-after.** Each fixture
was censused as built, before its churn:

| Fixture | as-built bytes | as-built `bloat_pct` | churned bytes | growth % | churned `bloat_pct` |
|---|---|---|---|---|---|
| `f1_churn` | 10,117,120 | 48.07 | 17,571,840 | +73.68 | 64.12 |
| `f2_pending` | 2,195,456 | 47.01 | 6,209,536 | +182.84 | 75.30 |
| `f3_fresh` | 10,125,312 | 48.09 | 10,125,312 | 0.00 | 48.09 |
| `f4_empty` | 16,384 | 49.80 | 16,384 | 0.00 | 49.80 |
| `f5_deleted` | 7,356,416 | 7.90 | 7,356,416 | 0.00 | 95.22 |
| `f6_slack` | 7,356,416 | 7.90 | 7,356,416 | 0.00 | 51.34 |
| `f7_reupdate` | 10,346,496 | 47.19 | 11,927,552 | +15.28 | 54.15 |
| `f11_json` | 13,066,240 | 49.32 | 20,062,208 | +53.54 | 51.95 |
| `f12_trgm` | 6,971,392 | 26.06 | 17,842,176 | +155.93 | 71.80 |
| `f13_btgin` | 2,383,872 | 48.70 | 4,628,480 | +94.16 | 64.62 |
| `f14_multi` | 8,159,232 | 45.99 | 14,737,408 | +80.62 | 60.57 |
| `f15_partial` | 311,296 | 40.14 | 2,359,296 | +657.89 | 89.15 |
| `g0` … `g100` | 7,749,632 | 47.35 | 8.3 – 15.3 MB | +7.40 … +96.93 | 50.94 … 59.85 |
| `m1_pair` | 3,948,544 | 14.08 | 3,948,544 | 0.00 | 54.55 |
| `a1_analyze` | 352,256 | 46.92 | 761,856 | +116.28 | 70.52 |

Three readings in that table are the argument for the baseline phase. `f5`, `f6` and
`m1_pair` grew by **0.00%** — a delete-only churn returns no bytes and takes none —
so the only way to see what happened to them is to compare their `bloat_pct` against
their own as-built reading, 7.90 becoming 95.22 and 51.34, and 14.08 becoming 54.55.
And every as-built reading is between 7.90 and 49.80, which is the level a churned
reading has to be judged against rather than against zero.

The census's fourth number, `payload_bytes` (size minus dead pages minus pending
pages minus slack), is the quantity that is *supposed* to survive a rebuild.
Dividing it by the fill fraction of the rebuilt index predicts the rebuilt size
within 3.2% on eleven of the nineteen fixtures and misses by up to +50.19% on the rest:

| Prediction error | Fixtures |
|---|---|
| under ±0.2% | `f3` 0.00, `f4` 0.00, `f7` +0.07, `g0` +0.09, `f2` −0.09, `a1` −0.16 |
| ±0.2% to ±3.2% | `f5` +1.12, `f12` +1.90, `f15` +2.24, `f6` +3.07, `m1` +3.12 |
| above +12% | `g25` +12.62, `f1` +19.94, `g50` +25.16, `f14` +31.31, `f13` +33.89, `g75` +37.69, `f11` +45.58, `g100` +50.19 |

The miss has a mechanism, and it is the reason `f1` and `f7` are both here: GIN's
entry tree never deletes a tuple
([README:389-396](../../../../raw/postgres-17/src/backend/access/gin/README#L389-L396)), so after
`f1`'s churn the index still carries an entry tuple for each of the 50,028 terms
that no longer occur. The census counts those tuples as payload; the rebuild drops
them. `f7`, whose churn leaves the term set alone, is predicted to +0.07%, and the
sweep turns the whole thing into a straight line; see
[The failure boundary is a straight line](#the-failure-boundary-is-a-straight-line).
One caveat keeps this out of predictor territory: the fill fraction comes from the
rebuild it is predicting, and it is not a constant — across these nineteen rebuilds
it ran from **43.28%** (`f5`, a 98-block file) to **87.96%** (`f6`, whose
posting-tree leaves a bulk build packs), with the entry-tree-dominated ones clustered
at 50.68% to 58.94% and `pg_trgm` at 73.32%.

### The maintenance step, measured

The protocol's maintenance assumption says a churned fixture runs `VACUUM ANALYZE`
on every table its churn touched before anything reads the index. `m1_pair` exists
to measure what that step does and does not change, so the rule is not taken on
faith. One fixture, four censuses, `int[]` at 100,000 rows with every other row
deleted:

| Reading | blocks | data_slack | `bloat_pct` | index `relpages` / `reltuples` |
|---|---|---|---|---|
| baseline, as built | 482 | 548,608 | 14.08 | 482 / 100,000 |
| after the writes, before the settle step | 482 | 548,608 | **14.08** | — |
| after the settle step (2 VACUUMs) | 482 | 2,146,368 | **54.55** | 482 / 50,000 |
| after the maintenance step (`VACUUM (VERBOSE, ANALYZE)`) | 482 | 2,146,368 | **54.55** | 482 / 50,000 |

The four readings and the catalog column are read from the run's `20-phases.txt`.
Before 2026-09-24 the first catalog cell read 482 / 50,000; the as-built index covers
all 100,000 rows, and the settle step's VACUUM is what brought [`reltuples`](../../../glossary.md#reltuples-and-relpages) down to
the 50,000 that survive the delete.

Two results, and they point in opposite directions.

**A census taken before the settle step is worthless, not merely noisy.** The
deletes had committed, half the rows were gone, and the census read *exactly* the
as-built numbers: same blocks, same slack to the byte, same 14.08. Nothing in GIN
reacts to a delete until `ginbulkdelete` runs, so the 40-point difference between
14.08 and 54.55 is entirely the settle step's work. That is why the protocol puts
the settle step inside the churn phase and forbids scoring anything before it.

**The `ANALYZE` half of the maintenance step cannot un-settle the index, and here it
could not move the catalog either.** `vacuum()` vacuums then analyzes each relation
([vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650)),
and `analyze_rel` enters the [index AM](../../../glossary.md#access-method)'s ANALYZE-only cleanup **only when the command
is not a `VACUUM ANALYZE`** — the comment there names GIN as the one core index AM
that does not treat that mode as a no-op
([analyze.c#analyze-only-cleanup](../../../../raw/postgres-17/src/backend/commands/analyze.c#L694-L721)).
So under the maintenance step the GIN callback is reached by the `VACUUM` half
alone, and the page census is identical on both sides of it, as the table shows.

What the `ANALYZE` half always does write is the measured index's own [`pg_class`](../../../glossary.md#pg_class)
row, from a live `RelationGetNumberOfBlocks` and a scaled row estimate
([analyze.c#index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663),
[vacuum.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1409-L1416)).
On `m1_pair` that write changed nothing, because the settle VACUUM had already made
the same one: `lazy_cleanup_all_indexes` passes `estimated_count = scanned_pages <
rel_pages`, and `update_index_statistics` skips exactly those indexes whose result
carries it
([vacuumlazy.c#estimated_count](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2352-L2356),
[vacuumlazy.c#update_index_statistics](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3081-L3098)),
and a VACUUM that skipped no page therefore does update them. A separate fixture
shows the write when it matters — `an_cat_gin`, grown from 5,000 to 60,000 rows with
no VACUUM in between:

| Step | index `relpages` | index `reltuples` | live blocks | metapage `n_total_pages` |
|---|---|---|---|---|
| after the grow, catalog stale | 4 | 5,000 | 23 | 4 |
| after a bare `ANALYZE` | **23** | **60,000** | 23 | **4** |
| after `VACUUM (VERBOSE, ANALYZE)` | 23 | 60,000 | 23 | **23** |

So a method that reads the measured index's `relpages` or `reltuples` is reading a
value the maintenance step has just rewritten, while the metapage's page counts are
the one census an `ANALYZE` cannot refresh at all.

### The auto-analyze stand-in, measured

On a GIN index an auto-analyze is not a statistics-only event, so the protocol's
stand-in for it is `ANALYZE` **plus** `gin_clean_pending_list()`: a worker's bare
`ANALYZE` reaches `ginvacuumcleanup` with `analyze_only` set and, because the caller
is an [autovacuum](../../../glossary.md#autovacuum) worker, flushes the pending list before returning, while the same
call from any other backend returns immediately
([ginvacuum.c#analyze_only-worker](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L729)).
`a1_analyze` is the fixture: 20,000 rows, `fastupdate = on`, then 4,999 inserts and
nothing else.

The launcher's three verdicts at the moment the stand-in replaced them, recomputed
from the effective values and recorded rather than applied:

| Verdict | Counter | Threshold at the defaults | Crossed? |
|---|---|---|---|
| vacuum | `dead` 0 | `50 + 0.2 * 20000` = 4,050 | no |
| insert vacuum | `ins_since_vacuum` 4,999 | `1000 + 0.2 * 20000` = 5,000 | no, by one row |
| analyze | `mod_since_analyze` 4,999 | `50 + 0.1 * 20000` = 2,050 | **yes** |

That is the state the fixture is built to model — a table a worker would have
analyzed and not vacuumed — and the thresholds are the engine's own arithmetic
([autovacuum.c#vacthresh-anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3074-L3076),
[autovacuum.c#verdicts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095)).
What the stand-in then did:

| Reading | blocks | entry | pending | deleted | metapage pending / total / entry | `bloat_pct` |
|---|---|---|---|---|---|---|
| baseline, as built | 43 | 42 | 0 | 0 | 0 / 43 / 42 | 46.92 |
| after the 4,999 inserts | 92 | 42 | 49 | 0 | 49 / 43 / 42 | 21.93 |
| after `ANALYZE` + `gin_clean_pending_list()` (returned **49**) | 93 | 43 | 0 | 49 | 0 / **43** / **42** | 70.52 |

Three things the protocol predicts, all of them visible here.

- **The flush is the part a foreground `ANALYZE` cannot do.** The 49 pending pages
  became 49 deleted pages and the file grew by one block, because the merge
  allocates through `GinNewBuffer` and the pages it frees are invisible to the merge
  that is running.
- **The metapage counts are stale by construction.** Neither `ANALYZE` nor
  `gin_clean_pending_list` reaches `ginUpdateStats`, so the metapage still says 43
  total pages and 42 entry pages against a 93-block file with 43 entry pages, and
  the census flags it `metapage page counts predate the file length` in every later
  reading. This fixture therefore **may not claim the settle step**, its metapage
  cross-check does not apply, and it drops from four cross-checks to three.
- **It is the run's second lower-bound violation**, and it is a new one: 52.69% of
  the file was dead pages, and the rebuild returned **45.16%**. The mechanism is the
  one `f2_pending` already showed — the aged in-use core is smaller than its own
  rebuild — but it arrives here through the state a real server reaches on its own,
  with no manual flush anywhere in the recipe.

Two of the stand-in's three differences from the worker's path stand unclosed, as
the protocol says they must: `gin_clean_pending_list` passes `full_clean` true where
the worker's analyze passes false, and it holds `RowExclusiveLock` on the index
where the worker holds [`ShareUpdateExclusiveLock`](../../../glossary.md#shareupdateexclusivelock) on the table
([ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1030-L1091),
[ginfast.c#ginInsertCleanup](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L776-L783),
[analyze.c#analyze-lockmode](../../../../raw/postgres-17/src/backend/commands/analyze.c#L135-L145)). The
first is neutralised by the run's own no-concurrency rule: with no writer there is
no page past the remembered tail.

### The simulated auto-analyze census

After the maintenance step and before the decide phase, the run recomputes the
launcher's analyze verdict for every table it would have walked and analyzes the
ones it names. The rule is the engine's own strictly-greater test on the effective
[reloption](../../../glossary.md#storage-parameter)-or-[GUC](../../../glossary.md#guc) values, with `reltuples` clamped at zero and `autovacuum_enabled`
short-circuiting the whole thing
([autovacuum.c#anl-effective-values](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3011-L3017),
[autovacuum.c#census-inputs](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3063-L3072),
[autovacuum.c#av_enabled-return](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3048-L3054)),
read from [`pg_stat_all_tables`](../../../glossary.md#pg_stat_all_tables)
([system_views.sql#launcher-counters](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L688-L690))
under `stats_fetch_consistency = snapshot` with `pg_stat_clear_snapshot()` between
the two reads, which is the sequence the engine's own statistics test uses
([guc_tables.c#stats_fetch_consistency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4966-L4974),
[stats.sql#force-flush](../../../../raw/postgres-17/src/test/regress/sql/stats.sql#L101-L110)).

The census walked **101 tables** — `relkind` `r` and `m` in every schema, which is
`do_autovacuum`'s own filter, minus `pg_statistic`, which ANALYZE refuses to work
with
([autovacuum.c#do_autovacuum-relkind](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1984-L1992),
[autovacuum.c#pg_statistic](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3108-L3110))
— and analyzed **10**: four of this page's own fixture tables and six catalog tables
(`pg_amop`, `pg_amproc`, `pg_attribute`, `pg_class`, `pg_depend`, `pg_index`), which
is what a real worker would have done to a database that has just had this page's
fixture tables and indexes built in it. It recorded **0** vacuum verdicts and **3** insert-vacuum verdicts, and
applied none of them.

The four fixture tables are the four cases the protocol asks for, and the last one
is a hazard reproduced on purpose:

| Table | `reltuples` | `mod_since_analyze` | threshold | verdict |
|---|---|---|---|---|
| `tc1_analyzed` | 10,000 | 2,000 | 1,050 | **analyzed** |
| `tc2_declined` | 10,000 | 500 | 1,050 | declined |
| `tc3_boundary` | 10,000 | **1,050** | **1,050** | **declined** — the test is strictly greater |
| `tc4_hazard` | 10,000 | **10,500** | 1,050 | analyzed, for the wrong reason |

`tc4_hazard` differs from `tc2_declined` in one line: its build-phase `ANALYZE` ran
**without** a [`pg_stat_force_next_flush()`](../../../glossary.md#cumulative-statistics) in front of it. Both tables were loaded
with 10,000 rows, analyzed, then given 500 more. `tc2` reads 500 and is declined;
`tc4` reads **10,500**, because the first load was still sitting in the session's
local counts when `pgstat_report_analyze` zeroed the shared counter, and the flush
that followed added it back
([pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L331-L337),
[pgstat_relation.c#mod_since_analyze](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L855-L860)).
The same hazard put `tc4` over the insert-vacuum threshold as well. This is not a
hypothetical: the first attempt at this run had the publication point missing
everywhere, and `tc2` and `tc3` both came out above their thresholds — 10,500 and
11,050 — which is what forced the fix and then the deliberate case.

The recheck read every analyzed table at `mod_since_analyze = 0` and `doanalyze`
false, and left `tc2` and `tc3` where they were, so publishing first and analyzing
second is what the run actually did. One artefact is worth naming: the census's own
bookkeeping tables are tables in the fixture database, so `wiki.census_run` was
among the ten it analyzed and `wiki.anl_census` appeared in the recheck as a table
that would now need one.

### The failure boundary is a straight line

The five-point churn sweep holds the churn volume constant — all 200,000 rows are
updated in every variant — and varies only the share `p` of the key population that
is replaced. There is no threshold and no safe region except `p` near zero:

| Fixture | keys replaced | churned bytes | payload/fill prediction | error | dead entry tuples |
|---|---|---|---|---|---|
| `g0_gin` | 0% | 8,323,072 | 7,756,432 | **+0.09%** | 1 |
| `g25_gin` | 25% | 10,067,968 | 8,727,825 | **+12.62%** | 25,001 |
| `g50_gin` | 50% | 11,894,784 | 9,771,313 | **+25.16%** | 50,001 |
| `g75_gin` | 75% | 13,615,104 | 10,670,309 | **+37.69%** | 75,001 |
| `g100_gin` | 100% | 15,261,696 | 11,639,344 | **+50.19%** | 100,010 |

The increments are +12.53, +12.54, +12.53 and +12.50 points per 25 points of `p`,
so on this shape the model over-predicts by very close to **half a point per
percent of the key population replaced**. Every churned size, every prediction, every
error and every dead-tuple count in that table is byte-for-byte and digit-for-digit
what the superseded corpus recorded, on a cluster built from scratch, and the
2026-09-24 run on a second platform read the same again. The rebuilds are the same
too: 7,749,632 bytes for four of the five and 7,806,976 for `g50`, a difference of
exactly 57,344 bytes, or seven blocks. The one exception in six passes is the reason
this is not called deterministic: in one 2026-09-24 pass, `g50_gin` kept one more
live posting-tree page than every other pass, because VACUUM's index-vacuum bypass
left 272 dead TIDs in it; see open question 23.

### Counting entry tuples, and what that fixes

The census can detect the failure case after all, because `pd_lower` counts line
pointers. GIN entry pages are ordinary item-pointer pages — `entryExecPlaceToPage`
and `entrySplitPage` place tuples with `PageAddItem`
([ginentrypage.c:561-568](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L561-L568),
[ginentrypage.c:683-691](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L683-L691)) — so
on an entry page `pd_lower` is `SizeOfPageHeaderData + nitems * sizeof(ItemIdData)`
([bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L211-L214)),
and `page_header` exposes it. Entry **leaf** pages carry flags exactly `{leaf}` and
entry-tree internal pages exactly `{}`, which separates the two:

```sql
SET /* wiki_gin_entry_probe_guards */ statement_timeout = '10min';
SET /* wiki_gin_entry_probe_guards */ lock_timeout = '2s';

WITH /* wiki_gin_entry_probe */ pages AS (
    SELECT o.flags, h.lower, h.upper, h.special, h.pagesize
    FROM generate_series(1, pg_relation_size('myschema.myindex','main') / 8192 - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page('myschema.myindex', b.blkno::int) AS pg
                             OFFSET 0) AS r
         LEFT JOIN LATERAL gin_page_opaque_info(r.pg) AS o ON true
         LEFT JOIN LATERAL page_header(r.pg)          AS h ON true
)
SELECT count(*)                 FILTER (WHERE flags = '{leaf}') AS entry_leaf_pages,
       sum((lower - 24) / 4)    FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuples,
       sum(special - upper)     FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuple_bytes,
       sum((lower - 24) / 4)    FILTER (WHERE flags = '{}'
                                        AND pagesize > 0)       AS internal_downlinks
FROM pages;
```

The `pagesize > 0` guard on the last column is a portability fix for 12.x, where an
all-zero page reports `flags = '{}'` and contributes `(0 - 24) / 4 = -6` downlinks
each. The revision that runs in this programme derives `8192`, `24` and `4` instead
of typing them, drops that guard because its decoder is gated on the page header
instead, and counts malformed and undecodable pages
([The derived-arithmetic statements](#the-derived-arithmetic-statements)); it is the
text the numbers below came from, and it caught one page the census could not see at
all — the `s7_gin` corruption, `malformed_pages 1` against a census that said `ok`.

`entry_leaf_tuples` is the number of keys the index holds, live or dead, and the
identity is exact on the two shapes where a live key count can be computed
independently. Since 2026-09-24 the probe stage counts those keys from the tables
themselves, without the index, into `11-entry-tuple-probe.txt`:

| Index | `entry_leaf_tuples` | distinct keys in the table |
|---|---|---|
| `f3_fresh_gin` (`tsvector`) | 50,028 | 50,028 lexemes |
| `f6_slack_gin` (`int[]`) | 32 | 32 tags |

The internal-downlink count is a free structural check: `f3_fresh_gin` reads 1,199
downlinks over 6 internal pages against 1,194 leaves, which is a root of 5 plus
1,194.

Subtract the live key count and you have the dead-key population that the payload
model trips over. Since 2026-09-16 the *after* column is a second probe pass rather
than a remembered number: the `probe_after` stage runs the same text again once the
oracle has rebuilt every scored index, so `dead_entry_tuples` is
`before − after` on the same index ([the script](#the-postgresql-1711-leg), artefact
`out/18-entry-tuple-probe-after.txt`). It separates the two churn shapes exactly:

| Index | entry tuples before | after `REINDEX` | dead | model error |
|---|---|---|---|---|
| `f1_churn_gin` (term set replaced) | 100,056 | 50,028 | **50,028** | +19.94% |
| `f7_reupdate_gin` (same terms rewritten) | 50,030 | 50,029 | **1** | +0.07% |
| `g0_gin` (0% of keys replaced) | 100,011 | 100,010 | **1** | +0.09% |
| `g25_gin` | 125,020 | 100,019 | **25,001** | +12.62% |
| `g50_gin` | 150,020 | 100,019 | **50,001** | +25.16% |
| `g75_gin` | 175,020 | 100,019 | **75,001** | +37.69% |
| `g100_gin` (100% replaced) | 200,020 | 100,010 | **100,010** | +50.19% |
| `f11_json_gin` (`jsonb_path_ops`, every key replaced) | 297,385 | 148,694 | **148,691** | +45.58% |
| `f13_btgin_gin` (`btree_gin`, every value moved) | 40,022 | 20,011 | **20,011** | +33.89% |
| `f14_multi_gin` (multicolumn, both keys replaced) | 102,056 | 51,028 | **51,028** | +31.31% |
| `f15_partial_gin` (partial, keys and predicate rewritten) | 555 | 368 | **187** | +2.24% |
| `f12_trgm_gin` (`gin_trgm_ops`, trigram sources replaced) | 1,359 | 1,329 | **30** | +1.90% |

The other seven scored fixtures read **0 dead entry tuples** — `a1`, `f2`, `f3`,
`f4`, `f5`, `f6` and `m1`, none of which retires a key — and the model's error on
them runs from −0.16% to +3.12%. `f15` and `f12` are the two that break the
correlation in the other direction: a large dead share of a *small* key population
costs the model almost nothing, because the error is linear in dead **tuples**, not
in the dead fraction.

What the probe does **not** buy is a corrected prediction: a dead key's tuple is
just the key with an empty posting list while a live key's carries its TIDs, so
subtracting dead tuples at the average entry-tuple size over-corrects. The pair of
estimates brackets the truth rather than predicting it. Cost: the probe over the
whole 19-fixture corpus ran inside the same order of magnitude as the census, and
the live-key count it has to be compared against is a full table scan.

### Whole-page waste is not a lower bound

**The run declared it one and it failed on 2 of 19.** `f2_pending_gin` held 490 dead
pages out of 758 — 64.64% of the file, confirmed independently by the FSM's 490 —
and `REINDEX` returned 58.05%. `a1_analyze_gin`, the auto-analyze stand-in, held 49
of 93 — 52.69%, again confirmed by the FSM — and `REINDEX` returned 45.16%.

**The rule is an identity, not a heuristic.** Reclaimed bytes are
`size - rebuilt`, so `waste <= reclaimed` holds exactly when
`rebuilt <= size - waste`: dead pages are a lower bound on what a rebuild returns
if and only if **the aged index's in-use core is at least as big as its own
rebuild**. Both failures are that inequality going the other way, and both indexes
got there the same way — their pages were filled by pending-list merges rather than
by a build:

| Fixture | waste % | truth % | in-use bytes | rebuilt bytes | aged core fill | fresh fill | lower bound |
|---|---|---|---|---|---|---|---|
| `f2_pending_gin` | 64.64 | 58.05 | 2,195,456 | 2,605,056 | denser | 58.94% | **fails** |
| `a1_analyze_gin` | 52.69 | 45.16 | 360,448 | 417,792 | denser | 53.85% | **fails** |

A merge appends into whichever entry page already holds the key, packing it, while a
fresh build splits pages in half: `entrySplitPage` divides a full page by equalizing
data size
([ginentrypage.c#entrySplitPage](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L666-L691)),
and there is no fast-append special case. So an index whose slack has been eaten by
later inserts is denser than its own rebuild, and its dead pages then *overstate*
what a rebuild returns.

Practical consequence, and this is the run's one rule change: **do not report dead
pages as "reclaimable by REINDEX".** Report them as what the source says they are —
pages this index will reuse before extending the file
([ginutil.c#GinNewBuffer](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L294-L335)). The
protocol requires a violated bound to be corrected in the method or moved to a
level, and there is no correction available that does not need the rebuild it is
trying to predict, so `whole_page_waste_pct` is a **level** from here on; see
[Reading rules](#reading-rules).

### Entry-page slack is growth room, not waste

GIN entry tuples grow in place: the posting list for a key lives inside the entry
tuple until it outgrows `GinMaxItemSize` and becomes a posting tree
([ginblock.h#GinMaxItemSize](../../../../raw/postgres-17/src/include/access/ginblock.h#L242-L253),
[ginentrypage.c#GinFormTuple](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L96-L114)), and
the entry tree never deletes tuples or pages at all
([README:389-396](../../../../raw/postgres-17/src/backend/access/gin/README#L389-L396),
[README:26-30](../../../../raw/postgres-17/src/backend/access/gin/README#L26-L30)). Free space on an entry page
is therefore the room its existing tuples need in order to grow.

Three measurements make the point:

- The never-churned control `f3_fresh_gin` reports **48.09% slack** and `REINDEX`
  reclaims **0 bytes**, returning the same 10,125,312. A fresh GIN index looks half
  wasteful by this metric.
- The empty control `f4_empty_gin` reports **49.80%**, which is one entry page with
  8,160 bytes free and nothing in the index at all.
- Every one of the nineteen rebuilt indexes reports slack of its own, from 12.04%
  (`f6`, whose posting-tree leaves a bulk build packs) to 56.72% (`f5`), with the
  entry-tree-dominated ones at 41.06% to 49.80%.

Data-leaf slack behaves much more like waste: `f6_slack_gin`'s 51.34% (almost all
of it on posting-tree leaves) against 46.33% actually reclaimed, and `m1_pair_gin`'s
54.55% against 46.47%. Posting-tree leaves do not merge — `ginScanToDelete` deletes
only pages that are entirely empty, and never the leftmost or rightmost branch
([ginvacuum.c#ginScanToDelete](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L303-L318)) — so a
half-emptied leaf stays half-empty until new TIDs in its key range arrive. The
census sees the difference in the split: `f6` holds 3,769,344 bytes of data slack
against 7,520 bytes of entry slack, and it is one of the two fixtures whose slack
percentage lands near its reclaimed percentage.

That is why the statement reports `entry_slack` and `data_slack` separately, and why
`bloat_pct`, which sums them with the dead pages, has to be read beside that split
rather than instead of it. On an entry-tree-dominated index most of that single
number is growth room: `f3_fresh_gin`'s 48.09 is 4,804,268 bytes of entry slack
against 65,192 of data slack, and a rebuild returns none of it.

### The pending-list lifecycle, measured end to end

One fixture, four states, same statement:

| State | bytes | blocks | entry | pending | deleted | whole-page waste | entry slack | `status` |
|---|---|---|---|---|---|---|---|---|
| built, 150k rows, settled | 2,195,456 | 268 | 170 | 0 | 0 | 0 | 575,940 | `ok` |
| +50k rows into the pending list | 6,209,536 | 758 | 170 | 490 | 0 | 0 (64.64% pending) | 575,940 | metapage predates the file length |
| after `gin_clean_pending_list()`, which returned 490 | 6,209,536 | 758 | 170 | 0 | 490 | 4,014,080 (64.64%) | 318,084 | metapage predates the file length |
| after the settle and maintenance steps | 6,209,536 | 758 | 170 | 0 | 490 | 4,014,080 (64.64%) | 318,084 | **`ok`** |
| after `REINDEX INDEX` | 2,605,056 | 318 | 220 | 0 | 0 | 0 | 725,084 | `ok` |

Five things to take from it. The flush **did not shrink the file**: it converted
64.64% of it into dead pages rather than returning them (`shiftList` records each
shifted page free and `ginInsertCleanup` vacuums the FSM at the end
([ginfast.c:662-670](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L662-L670),
[ginfast.c:1014-1020](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1014-L1020))), and it can
just as easily *grow* it, because the merge allocates through `GinNewBuffer` and
extends when the FSM has nothing to give — the stand-in fixture grew by exactly one
block doing this. The settle step changed **no page count and no byte**, and changed
the `status` from a flagged metapage to `ok`, which is the cleanest demonstration on
this page of what settling is for: it does not move the [bloat](../../../glossary.md#bloat), it makes the reading
comparable. The census's `pending_pages` matched the metapage's `n_pending_pages`
exactly (490) while the list was live, which is a free correctness check on the
classification. `pgstatginindex` is blind in four of the five states. And the
maintenance VACUUM reported the freed pages as reusable **in the same run** —

```text
index "f2_pending_gin": pages: 758 in total, 0 newly deleted, 0 currently deleted, 490 reusable
```

— because `shiftList` leaves `pd_prune_xid` at 0, so `GinPageIsRecyclable` returns
true at its "delete xid is invalid" branch
([ginvacuum.c:816-822](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L816-L822)). That is
the opposite of what a posting-tree deletion does, which is the next section.

### Deleted pages need the horizon to move before they count

Posting-tree deletions behave in the opposite way, and this is the single most
surprising operational detail in the whole procedure. `ginDeletePage` stamps
`ReadNextTransactionId()` into the page
([ginvacuum.c:187-192](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L187-L192)) and
`GinPageIsRecyclable` clears the page only once
`GlobalVisCheckRemovableXid(NULL, delete_xid)` agrees
([ginvacuum.c:805-829](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829)). Passing
`NULL` for the relation selects `VISHORIZON_SHARED`, documented as the most
conservative horizon
([procarray.c#GlobalVisHorizonKindForRel](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1966-L1991),
[procarray.c#GlobalVisCheckRemovableXid](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L4294-L4306)).

`f5_deleted`'s settle step is that sequence, and it is why the protocol says to
expect more than one VACUUM:

| Step | VACUUM VERBOSE index line | FSM free pages |
|---|---|---|
| VACUUM 1 (does the deleting) | `898 in total, 768 newly deleted, 768 currently deleted, 0 reusable` | 0 |
| three `pg_current_xact_id()` calls, then VACUUM 2 | `898 in total, 0 newly deleted, 0 currently deleted, 768 reusable` | 768 |
| VACUUM 3, and the maintenance step after it | the same line again | 768 |

The census saw the pages the whole time — 768 blocks flagged
`{data,leaf,deleted,compressed}` — which is the practical argument for the page
census over the FSM cross-check: `pg_freespace` under-reports until the horizon has
moved *and* another VACUUM has run, while the flags are true immediately. The file
never shrank at any step, and stayed at 7,356,416 bytes throughout.

**One idle transaction is enough to freeze that indefinitely.** `f8_horizon_gin`
repeats the sequence with a `REPEATABLE READ` snapshot held open in a second
session, whose `backend_xmin` read 925:

| Step | VACUUM VERBOSE index line | census `deleted_pages` | FSM free pages |
|---|---|---|---|
| VACUUM 1, snapshot held | `898 in total, 768 newly deleted, 768 currently deleted, 0 reusable` | | |
| three xids, VACUUM 2, snapshot held | `898 in total, 0 newly deleted, 0 currently deleted, 0 reusable` | 768 | 0 |
| holder terminated, VACUUM 3, **no new xids** | `898 in total, 0 newly deleted, 0 currently deleted, 768 reusable` | 768 | 768 |

So consuming transaction ids is not the requirement — moving the *shared* horizon
past the stamped xid is, and the very next VACUUM after the snapshot went away
recycled all 768 pages without a single new transaction. An idle `REPEATABLE READ`
session, a forgotten `BEGIN`, or any long-running query therefore keeps every dead
GIN page unreusable, while the census keeps reporting them as dead all along.

### Concurrency: a census of a busy index is a mixed-instant reading

The non-atomic scan is not a theoretical caveat. Four cases, each a loop of censuses
run back to back while one background session worked, all on the derived statement
with its `status` column:

| Case | Censuses during the work | Flagged | What they read |
|---|---|---|---|
| A: one VACUUM deleting 768 posting-tree pages of an 898-block index | 4 | 3 of 4, `vacuum or analyze in progress` | **four different** deleted-page counts between 0 and 768 on a file that never changed size |
| B: the same deletions with the protocol lock held | 20 | 0 of 20 | **20 of 20 identical**; the VACUUM waited 3219 ms and ran after `COMMIT` |
| C: `REINDEX INDEX CONCURRENTLY` | 3 | 2 of 3, `index build in progress` | 898 blocks with 768 deleted, then the swapped-in 98-block index with 0 deleted; no error, and no census straddled the swap |
| D: a writer stream into a `fastupdate` index | 30 | **30 of 30** | the file grew 60 → 663 blocks, 20 distinct deleted-page readings; 10 censuses were flagged `size changed during scan`, 20 `pending count disagrees with metapage`, and all 30 `metapage page counts predate the file length` |

Case D does not repeat, and neither does case A's census count: the writer stream and
the VACUUM race the census loop, so how many censuses land and what they see is a
property of the machine. The two 2026-09-16 passes on Linux read 34 and 33 censuses in
case D, with 21 and 20 distinct deleted-page readings, from 58 and 59 blocks; this run
read the 30, 20 and 60 above. Case A read 5 censuses with 4 flagged, and then 4 with 4,
on those passes, and 4 with 3 here. Case B's 20 identical censuses and case C's
reading came out the same on every pass; only case B's wait moves.

Case A is the one the page used to call undetectable by every cross-check, and the
progress views do catch it whenever the VACUUM is running at either end of the scan
— here 3 of the 4 that overlapped it. The one it missed is the shape the protocol
warns about: a maintenance command that starts and finishes between the statement's
two progress reads leaves no trace in either. Case D is where the size bracket earns
its keep, and case C is a trap rather than a wrong number: `get_raw_page` resolves
the index name on every call and holds no lock between calls, so a swap landing
after the size read and before a page read would put the block number past the end
of the new, smaller file — the documented `block number ... is out of range` error.

The conclusion the protocol draws from this is the one this page now follows: **if
the comparison has to be exact, take the lock instead of reading the flags.** Case B
is the only loop of the four in which every census agreed with every other.

### Cost of the census

The scan is one buffer read per block, through the ordinary buffer manager with no
[ring buffer](../../../glossary.md#ring-buffer): `get_raw_page_internal` calls `ReadBufferExtended(..., RBM_NORMAL, NULL)`
([rawpage.c#get_raw_page_internal](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L181-L196)),
where `pgstattuple` and `pgstatindex` both allocate a `BAS_BULKREAD` strategy
([pgstattuple.c:544](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L544),
[pgstatindex.c:222](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L222)). A census of a large
index therefore pulls the whole index into [`shared_buffers`](../../../glossary.md#shared_buffers) with no limiter, which
is the one real operational cost of this approach.

Measured on the run's own database, `shared_buffers = 256MB`, everything warm:

| What | Buffers | Elapsed |
|---|---|---|
| the whole database after the oracle's rebuilds: 27 GIN indexes over 14,719 blocks, 26 of them valid and censused | `shared hit=15313` | 63.2 / 62.9 / 65.3 ms over three runs |
| one 1,236-block index, single-read form | `shared hit=1265` | 5.7 ms |
| the same index, naive form calling `get_raw_page` inside each function | `shared hit=2499` | 4.2 ms |

The buffer count is the point of the `OFFSET 0` subquery: 1,265 against 2,499 is one
read per block against two, and 15,313 over a database holding 14,719 GIN blocks is
one read per block plus the catalog. The two one-index counts are the same on every
run this page records; the whole-database count follows the corpus, and was 15,816
over 15,201 blocks while `f9c_cleanup_gin` was still built. The elapsed times do not
repeat: on the 2026-09-16 Linux passes the whole-database census took 119 to 120 ms,
and the same stage in this session's earlier pass on this machine took 141 to 147 ms,
against 63 to 65 ms in the recorded run. What the single-read form is **not** is a
time saving — on a fully cached index the naive form was the faster of the two on
every pass, because it trades a second [buffer pin](../../../glossary.md#buffer-pin) for a simpler plan. Choose the
single-read form for the I/O, not for the latency.

Two costs the run did not re-measure, and they are not the same thing. The first is
the write-blocking cost of the protocol lock, which is measured in
[The measurement protocol](#the-measurement-protocol): 214 ms for this run's
23,743-block decide pass, and one buffer read per block on anything larger. The second is
what a census does to a production cache: this pass did not re-run the
`pg_buffercache` experiment the page used to carry, because it was a synthetic
workload on a deleted sandbox and the protocol does not cover it; see
[What this pass removed, and why](#what-this-pass-removed-and-why). The source
argument stands on its own — the census takes no `BAS_BULKREAD` ring and reads each
page once, so its own pages sit at the bottom of the [clock sweep](../../../glossary.md#clock-sweep)
([bufmgr.c:2700-2705](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2700-L2705),
[freelist.c#StrategyGetBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L314-L341)).

### Privileges

| Function | Who can run it |
|---|---|
| `get_raw_page`, `page_header`, `gin_metapage_info`, `gin_page_opaque_info`, `gin_leafpage_items` | superuser only, hard-coded |
| `pgstatginindex` | superuser, or a role with `pg_stat_scan_tables`, or an explicit grant |
| `pg_freespace` | same |
| `gin_clean_pending_list` | the index owner |

Every `pageinspect` entry point is gated on `superuser()` in C, some directly and
some through a shared internal — the raw-page reader, which is where all four
`get_raw_page` variants land
([rawpage.c:150-153](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L150-L153)), `page_header`
([rawpage.c:261-264](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L261-L264)) and each GIN function
([ginfuncs.c:42-45](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L42-L45),
[ginfuncs.c:112-115](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L112-L115),
[ginfuncs.c:188-191](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L188-L191)) — which the module
documentation states as a blanket rule
([pageinspect.sgml:10-14](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L10-L14)). A `GRANT` cannot
help: the check is not an ACL. By contrast `pgstatginindex` dropped its
`superuser()` call in the 1.5 wrapper and is granted to `pg_stat_scan_tables`
([pgstattuple--1.4--1.5.sql:49-57](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L49-L57),
[pgstatindex.c:497-504](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L497-L504)), and
`pg_freespacemap` 1.2 grants both `pg_freespace` forms to the same role
([pg_freespacemap--1.1--1.2.sql:6-7](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap--1.1--1.2.sql#L6-L7)).
`gin_clean_pending_list` requires ownership, "comparable to privileges needed for
VACUUM" ([ginfast.c:1061-1064](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1061-L1064)).

Verified on 2026-09-24 with a role holding only `pg_stat_scan_tables` and `USAGE` on
the schema: on `f6_slack_gin`, `pgstatginindex` returned `2 | 0 | 0` and
`pg_freespace` returned all **898** rows, while `get_raw_page` returned
`ERROR: must be superuser to use raw page functions` at the census's first read.
`pg_control_init()`, which the FSM cross-check derives its constant from, answered
`8 | 8192` for the same role, so a `pgstatginindex`-only reader can compute the
constant but not the census.

### Refusals, silent answers, and other traps

Every row of this table is a source claim with a citation. The 2026-09-24 run
re-executed, in the 17.11 leg's main programme, `pgstattuple` on a valid GIN index,
`pgstatginindex` and `gin_clean_pending_list` on an invalid one, both temporary cases
and the recovery refusals; and, in its portability stage, `pgstattuple` on an invalid
index, `get_raw_page` on a [partitioned index](../../../glossary.md#partitioned-index) and a two-byte `bytea`. They answered
exactly as filed. The rows for `pgstatginindex` and `pg_freespace` on a partitioned
index, `get_raw_page` past the end of the index and `gin_leafpage_items` were not
re-run in this pass.

| Case | Behavior |
|---|---|
| `pgstattuple` on a valid GIN index | `ERROR: index "..." (gin index) is not supported` ([pgstattuple.c:280-296](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L280-L296)) |
| `pgstattuple` on an *invalid* GIN index | `ERROR: index "..." is not valid` — the validity check runs before the AM switch ([pgstattuple.c:263-267](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L263-L267)) |
| `pgstatginindex` on a non-GIN index | `ERROR: relation "..." is not a GIN index` ([pgstatindex.c:522-526](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L522-L526)) |
| `pgstatginindex` on an invalid index | `ERROR: index "..." is not valid` ([pgstatindex.c:538-543](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L538-L543)) |
| `pgstatginindex` on a *partitioned* GIN index | `ERROR: relation "..." is not a GIN index`, because `IS_INDEX` tests `relkind = 'i'` ([pgstatindex.c:70-73](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L70-L73)) |
| `get_raw_page` on a partitioned index | `ERROR: cannot get raw page from relation "..."`, `DETAIL: This operation is not supported for partitioned indexes.` ([rawpage.c:158-163](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L158-L163)) |
| `pg_freespace` on a partitioned index | **0 rows, no error** — the set-returning wrapper's `generate_series` is empty ([pg_freespacemap--1.1.sql:13-21](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap--1.1.sql#L13-L21)) |
| any of them on another session's temp GIN index | `pgstatginindex`: `cannot access temporary indexes of other sessions` ([pgstatindex.c:528-536](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L528-L536)); `get_raw_page`: `cannot access temporary tables of other sessions` ([rawpage.c:165-173](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L165-L173)); **`pg_freespace` answers anyway**, with no such guard in its C function ([pg_freespacemap.c:24-50](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap.c#L24-L50)) |
| `get_raw_page` past the end of the index | `ERROR: block number 100000 is out of range for relation "..."` ([rawpage.c:175-179](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L175-L179)) |
| `gin_leafpage_items` on any page that is not exactly `{data,leaf,compressed}` | `ERROR: input page is not a compressed GIN data leaf page`, `DETAIL: Flags 0002, expected 0083` — the reported flags are the page's own, so an entry leaf shows `0002` and an entry-tree internal page `0000` ([ginfuncs.c:219-226](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L219-L226)) |
| `gin_clean_pending_list` on an invalid index | returns 0, logs at `DEBUG1` ([ginfast.c:1068-1086](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1068-L1086)) |
| `gin_clean_pending_list` during recovery | `ERROR: recovery is in progress`, `HINT: GIN pending list cannot be cleaned up during recovery.`, reproduced on a physical standby of this sandbox, where `VACUUM` is also refused (`cannot execute VACUUM during recovery`) while `pgstatginindex`, `get_raw_page` and `gin_page_opaque_info` all answer ([ginfast.c:1037-1041](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1037-L1041)) |
| a `bytea` that is not one block long | `ERROR: invalid page size` ([rawpage.c#get_page_from_raw](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L214-L234)) |

Two more, from the code rather than from an error message:

- **The scan is not atomic.** `get_raw_page_internal` locks and copies **one**
  page per call ([rawpage.c:186-196](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L186-L196)), so a
  census of *N* blocks is *N* consistent page images taken at *N* different
  instants. Concurrent inserts, a VACUUM, or a pending-list flush can move pages
  between classes mid-scan, and the `census_total_pages = blocks` check does not
  notice — see
  [Concurrency: a census of a busy index is a mixed-instant reading](#concurrency-a-census-of-a-busy-index-is-a-mixed-instant-reading)
  for what that costs in practice.
- **`gin_leafpage_items` is not needed by this procedure**, and its exact-flag
  requirement is the reason: it accepts a page only when `opaq->flags` equals
  `GIN_DATA | GIN_LEAF | GIN_COMPRESSED` exactly, so a deleted or
  incompletely-split leaf is rejected. Per-TID detail is not required for a byte
  census.

Also worth knowing: an index whose `indisvalid` is false is still fully readable by
`get_raw_page`, which has no validity check. The census statement filters those
indexes out to keep its results interpretable, but dropping `AND x.indisvalid`
makes it the only working way to size the waste in a failed
`CREATE INDEX CONCURRENTLY` leftover — re-verified on 2026-09-24 against
`tinv_bad`, left `indisvalid` false, `indisready` false and `indislive` true by a
concurrent build whose expression divided by zero: the census returned no row for
it, `pgstatginindex` refused with `index "tinv_bad" is not valid`,
`gin_clean_pending_list` returned 0, and
`gin_metapage_info(get_raw_page('tinv_bad', 0))` still read `version 2`.

### Timeouts and GUC scope

| Setting | Context | Scope | Use here |
|---|---|---|---|
| `statement_timeout` | `PGC_USERSET` ([guc_tables.c:2611-2620](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620)) | session/transaction | cap the census; `10min` for a multi-GB index |
| `lock_timeout` | `PGC_USERSET` ([guc_tables.c:2622-2631](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)) | session/transaction | `2s`, so a concurrent `DROP INDEX`/`REINDEX` does not park the census |
| `gin_pending_list_limit` | `PGC_USERSET` ([guc_tables.c:3576-3585](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585)) | session/transaction | only relevant if you deliberately grow a pending list; it can also be set per index as a storage parameter ([gin.sgml#GIN-Tips](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L595-L616)) |

`lock_timeout = '2s'` was exercised ten times in this run, from the other side of
the protocol lock: every one of the eight conflicting commands was cancelled between
**2018 and 2024 ms** with `canceling statement due to lock timeout`, while
`SELECT count(*)` went through in 16 ms and `gin_clean_pending_list()` in 13 ms
([The measurement protocol](#the-measurement-protocol)). With `lock_timeout = 0` the
same kind of wait is a wait and not an error: the queued VACUUM of the race fixture
sat for **3219 ms** behind a census transaction and then ran normally. The
`statement_timeout` leg — cancelling a census mid-scan rather than mid-wait — was
not re-run in this pass.

### Outside the protocol: the four statements on PostgreSQL 12

**Read this section with a different warrant from the rest of the page.** The
protocol is a PostgreSQL 17 protocol, so nothing here is a scored GIN waste claim:
what follows is *statement portability*. Since 2026-09-24 it has a script of its
own. The [12.2 leg](#the-postgresql-122-leg) builds 12.2 from this repo's v12 pin and
runs the portability battery, and the 17.11 leg runs the same battery, byte for
byte, as its `portability` stage. So every 17.11 cell below comes from the 17.11
leg, and every 12.2 cell from the 12.2 leg, both run on 2026-09-24. The battery
builds its own fixtures in two databases of its own:

- `pt_ok_gin` and its twin `pt_zero_gin`, 4,000 `int[]` rows and 7 blocks each as
  built, with two all-zero blocks appended to `pt_zero_gin` while the server is
  stopped;
- a partitioned GIN index, and an invalid one left by a failed
  `CREATE INDEX CONCURRENTLY`;
- `pt_f5_gin`, the `f5` recipe, for `VACUUM VERBOSE`;
- in the second database, `pm_ok_gin` and `pm_meta_gin`, whose block 0 is zeroed
  the same way.

Every per-fixture 12.2 number of the superseded two-major corpus stays gone; see
[What this pass removed, and why](#what-this-pass-removed-and-why).

**Three edits make all four statements run on 12.2**, two in the census and one in
the entry-tuple probe. The FSM cross-check and the size bracket need none.

| Statement | Runs unchanged on 12.2? | Edit needed | What both legs read with the edits in place |
|---|---|---|---|
| census | no | `b.blkno::int`, and a `pagesize = 0` arm ahead of the flags tests | the same four rows on both majors, byte for byte |
| FSM check | **yes** | none | `8160 \| 0 \| 9` on `pt_zero_gin`: `pg_control_init()` has both columns on both |
| size bracket | **yes** | none | `9` on both |
| entry-tuple probe | no | `b.blkno::int`, and `AND pagesize > 0` on the `'{}'` filter | `5 \| 300 \| 22000 \| 5` on `pt_zero_gin` on both |

**Edit 1: the block number is an `int4` on 12.** Without the cast, 12.2 answers
`ERROR: function get_raw_page(text, bigint) does not exist`, or
`get_raw_page(unknown, bigint)` in the probe, whose index name is a literal. The
cause is that `generate_series` hands it a `bigint`, and `pageinspect` 1.7 on that
server declares `get_raw_page(text, int4)`. v17 declares the `int8` form. The
widening is `pageinspect--1.8--1.9.sql`, which drops the `int4` signatures and
creates `int8` ones
([pageinspect--1.8--1.9.sql#get_raw_page](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L46-L58)).
It was committed as `f18aa1b2039` "pageinspect: Change block number arguments to
bigint" on 2021-01-19, first released in `REL_14_0` (earliest tag `REL_14_BETA1`),
with no back-patch line. Its message gives the reason: block numbers are 32-bit
*unsigned*, so `bigint` is the smallest SQL type that holds them. `::int` is the
portable spelling, and it is a no-op on 17.11: there the census and the probe
without the cast returned exactly what the filed texts return. The remaining limit
is v12's own: a fork past 2^31 blocks cannot be addressed there at all.

**Edit 2: `flags IS NULL` does not mean "all-zero page" on 12.2.** On 17.11 both GIN
inspection functions return early on `PageIsNew`
([ginfuncs.c:49-50](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L49-L50),
[ginfuncs.c:119-120](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L119-L120)).
On 12.2 they do not, and the whole difference follows:

| Call, fed one all-zero `bytea` | 17.11 | 12.2 |
|---|---|---|
| `gin_page_opaque_info` | a row of NULLs | a row: `rightlink 0`, `maxoff 0`, `flags {}` |
| `gin_metapage_info` | a row of NULLs | `ERROR: input page is not a GIN metapage`, `DETAIL: Flags 0000, expected 0008` |
| `page_header` | `lower 0 / upper 0 / special 0 / pagesize 0` | identical |

So on 12.2 the census without its `pagesize = 0` arm folds zeroed blocks into the
entry-page count and reports their waste as zero. `pt_zero_gin` read **8 entry pages,
0 new pages and 0 bytes** of whole-page waste, where the filed text reads 6, 2 and
16,384 (22.22%). `census_total_pages = blocks` still passed, at 9. That is a silent
under-count of exactly `new_pages * block_size`. On 17.11 the same text returned the
filed row, because its `flags IS NULL` arm catches the page there. And **a zeroed
metapage aborts the whole multi-index report** on 12.2: the census over the second
database stopped with `input page is not a GIN metapage`. On 17.11 it returned a row
for `pm_meta_gin` with NULL metapage columns, and listed `pm_ok_gin` beside it. On
12.x, census a suspect index on its own.

The NULL behaviour is `cd4868a5700` "pageinspect: Fix handling of all-zero pages"
(2022-04-14). Its message chooses NULL over an error so that a scan of a whole
relation still returns a batch, and it carries `Backpatch-through: 10`. Its 12-branch
back-patch is `5378d55cb2f`, whose earliest `REL_12_*` tag is **`REL_12_11`**, and
this repo's v12 pin is an ancestor of it. Both facts come from the v12 checkout's
history, because the v17 checkout does not carry the 12 branch. A 12.11-or-later
server should behave like 17.11 here; that was never tested.

**Edit 3** is the same cause inside the probe. On 12.2 each all-zero page reports
`flags = '{}'` and contributes `(0 - 24) / 4 = -6` downlinks. So the probe without
its `pagesize > 0` guard read **-7** internal downlinks on `pt_zero_gin`, against 5
with the guard and 5 on its untouched twin `pt_ok_gin`. On 17.11 all three read 5.
The derived probe closes this structurally, by gating its decoder on the page header,
which is why it needs no `pagesize > 0` guard on either server: it read 5 downlinks
and `undecoded_pages 2` on `pt_zero_gin` on both.

One difference needs no edit at `block_size` 8192. `page_header` returns `lower`,
`upper`, `special` and `pagesize` as `integer` on 17.11
([pageinspect--1.9--1.10.sql#page_header](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.9--1.10.sql#L10-L21))
and as `smallint` on 12.2; both legs read the column types back. The change is
`127404fbe28` "pageinspect: Improve page_header() for pages of 32kB" (2021-07-12,
first released in `REL_15_0`, earliest tag `REL_15_BETA1`). Every value fits in a
signed 16-bit integer at 8 kB pages, so the arithmetic is unaffected. At `BLCKSZ`
32768 the 12.2 columns would overflow and the statement would need casts there.
That is untested, and in [Open Questions](#open-questions).

**Refusals that differ.** Both legs' batteries ran each case:

| Case | 17.11 | 12.2 |
|---|---|---|
| `pgstatginindex` on an **invalid** GIN index | `ERROR: index "..." is not valid` | **returns a row**: `2 \| 0 \| 0` |
| `pgstattuple` on an invalid GIN index | `ERROR: index "..." is not valid` | `ERROR: "..." (gin index) is not supported`: no validity check, so it falls through to the AM refusal |
| `get_raw_page` on a partitioned index | `ERROR: cannot get raw page from relation "..."`, `DETAIL: This operation is not supported for partitioned indexes.` | `ERROR: cannot get raw page from partitioned index "..."`, no DETAIL |
| `page_header` on a `bytea` two bytes long | `ERROR: invalid page size`, `DETAIL: Expected 8192 bytes, got 2.` | `ERROR: input page too small (2 bytes)` |
| `gin_page_opaque_info` on the same `bytea` | `ERROR: invalid page size`, `DETAIL: Expected 8192 bytes, got 2.` | identical |
| `gin_metapage_info` on an all-zero page | a row of NULLs | `ERROR: input page is not a GIN metapage` |

The short-`bytea` rows correct an older one that named no function. The difference
belongs to `page_header` alone: on 17.11 it decodes through `get_page_from_raw`, like
the GIN decoders
([rawpage.c:266](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L266),
[rawpage.c#get_page_from_raw](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L214-L234)),
while on 12.2 the GIN decoder already gave 17.11's answer and only `page_header`
answered differently.

The invalid-index refusal is the one with operational weight, and **it is not
v17-only**. Commit `13503eb5905` "Diagnose !indisvalid in more SQL functions."
(2023-10-30) added the check to `pgstatginindex` and `pgstattuple` on master
([pgstatindex.c:538-543](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L538-L543),
[pgstattuple.c:263-267](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L263-L267)),
and its earliest tag is `REL_17_BETA1`. Its message says "Back-patch to v11 (all
supported versions)". The 12-branch copy is `975ae05537`, first tagged `REL_12_17`
and a descendant of this repo's 12.2 pin, per the v12 checkout's history. So a
12.17-or-later server should refuse too; it is the pin, 12.2, that predates the
check. On 12.2 a failed `CREATE INDEX CONCURRENTLY` leftover therefore *answers*
`pgstatginindex` with a metapage reading rather than refusing: a number that looks
healthy and means nothing. Before 2026-09-24 this paragraph called the check
v17-only and gave `REL_17_0` as its earliest tag.

**The VACUUM VERBOSE cross-check has to be parsed differently.** Both legs ran the
`f5` three-VACUUM sequence on the battery's `pt_f5_gin`, 898 blocks on both. The
numbers agree: 768 pages deleted and none reusable after the first VACUUM, then 768
reusable after the second and after the third. The message does not. 12.2 prints the
counts in a `DETAIL` block under an `INFO: index "pt_f5_gin" now contains ... row
versions in 898 pages` line, as `768 index pages have been deleted, 0 are currently
reusable.`, rather than in a one-line index summary. It has no `newly deleted` versus
`currently deleted` split at all: one "have been deleted" number, which is
`pages_deleted`, the per-run counter this page warns is not a census
([ginvacuum.c:234-235](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L234-L235),
[ginfast.c:590-591](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L590-L591)).
So on 12.x the "reusable" number is the only census-like figure available
([ginvacuum.c:786-794](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L786-L794)).

Two constructs the *harness* needs are v12-relevant even though no published
statement uses them. `pg_current_xact_id()` does not exist on 12.2, which answered
`function pg_current_xact_id() does not exist`; that is why the battery burns its
three xids with `txid_current()` on both legs. And `autovacuum_vacuum_insert_threshold`,
which the census's recorded insert verdict reads, is an `unrecognized configuration
parameter` there. So the census of [the protocol](#the-simulated-auto-analyze-census)
would need its own port before it could run on 12.2 at all.

### What this pass removed, and why

The instruction the 2026-09-15 pass answered was to update or remove every test that
does not follow the protocol. Those were removed rather than updated, and the reason
is the same in every case: nothing on the page could re-run them. The last row is the
2026-09-24 pass's one removal, made for a different reason: the protocol changed.

| Removed | What it was | Why |
|---|---|---|
| `k1`-`k3` | `jsonb_ops`, `text[] array_ops` and weighted-`tsvector` fixtures | their table shapes existed only as trailing comments and their churn statement was never published; there was nothing to re-run |
| `k4`, `k5` | the same [opclass](../../../glossary.md#operator-class) at 50,000 and 800,000 rows, the scale check | the recipe was a one-line description, and `k5` was the page's headline upper-bound violation, so its loss is recorded as an open question rather than as a result |
| `fh1`-`fh3`, `fg_flush` | four pending-list-grown fixtures | recipes were one-line descriptions; `fh2` was the second lower-bound violation and `fg_flush` carried the flush-growth and round-five findings, so three sections went with them |
| `fa`, `fb`, `fz`, `fw1`-`fw4`, `f10_race`, `f16_zero` | concurrency, rebuild-comparison and crash fixtures | replaced by the four concurrency cases and the deterministic zero-page case of this run, which have published recipes |
| `tn_null` / `fn_null_gin` | the null-category entry-tuple fixture | its `+3` identity was a good finding and is not re-run; the source claim about `GinNullCategory` stands without it |
| the wraparound failsafe case | a *successful* VACUUM that never calls `ginvacuumcleanup` | reaching it needs `autovacuum_freeze_max_age` at its 100,000 minimum, which is `PGC_POSTMASTER`, plus a 120,000-transaction burn. The 2026-09-15 run reached the same kind of `VACUUM` with `INDEX_CLEANUP OFF` and the reloption instead, until that fixture went too; see the last row |
| the four crash rounds | `pg_ctl stop -m immediate` during an insert | the result was a *rate* on one machine (2 of 4, then 0 of 2), not a rule; the appended-zero-block case reaches the same page state deterministically |
| the `pg_buffercache` eviction experiment | what a census costs a hot working set | a synthetic workload, outside the protocol, and its conclusion had already been corrected once |
| every per-fixture 12.2 number | the two-major corpus comparison, including "26 of 27 byte-identical" | it compared against the superseded 17.11 corpus, which this run replaced; the statement-portability findings are kept above |
| `f9c_cleanup`, on 2026-09-24 | the `f5` recipe at 100,000 rows, vacuumed once with `INDEX_CLEANUP OFF` and once under the `vacuum_index_cleanup = off` reloption: two successful VACUUMs that never called `ginvacuumcleanup` | not a re-run problem this time. The protocol no longer requires "a `VACUUM` whose index cleanup did not run" and declares no exception for one, so a fixture that switches index cleanup off now defeats the maintenance step it is scored under ([Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md#what-the-protocol-does-not-cover)). The engine fact it showed stays in [the procedure](#the-procedure)'s step 3 |

Four sections went with them: the two pass-by-pass acceptance records (folded into
[Adversarial and acceptance cases](#adversarial-and-acceptance-cases)), *Why a flush
sometimes grows the file*, *Why round five splits the entry tree*, *Two more bound
failures*, and the 12.2 corpus and eviction sections. What survived the cut is
everything whose recipe now lives in [the script](#the-postgresql-1711-leg).

### Reading rules

The rules that bind any v17 GIN waste claim are defined under [The reading
rules](../../common-concepts/mandatory-gin-bloat-tests.md#the-reading-rules). The
list below is this page's own: the same rules as this page measured them on
2026-09-24, with the two changes the 2026-09-15 run forced and every run since
reproduced.

- **`whole_page_waste_pct` is a level, not a lower bound.** This is the change. The
  run declared it a lower bound and it failed on 2 of 19 fixtures — `f2_pending_gin`
  at 64.64% against 58.05% returned, and `a1_analyze_gin` at 52.69% against 45.16% —
  and the identity behind both failures needs the rebuild it is trying to predict,
  so there is no correction to make. Report dead pages as what the source says they
  are: pages this index will reuse before extending the file
  ([ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829),
  [ginutil.c#GinNewBuffer](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L294-L335)).
  With `W = whole_page_waste_bytes`, `B = old main-fork bytes` and
  `R = rebuilt main-fork bytes`, the comparison is exact algebra: `W > B - R` if and
  only if `B - W < R`, so whole-page waste **overstates** the size reduction
  whenever the aged in-use core is smaller than the rebuild
  ([index.c:3781-3789](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789)).
- **`bloat_pct` is an upper bound that held 19 of 19 here, and is still not a
  promise.** Report the three classes separately and keep them beside it rather than
  behind it. The single number is `waste + slack`, so it carries an entry tree's
  growth room: a never-churned index reads 48.09 and an empty one 49.80, both with
  nothing to reclaim. The corpus that broke this bound twice before is gone from the
  page, so the shape that breaks it is unrepresented rather than refuted; see
  [Open Questions](#open-questions). Adding `pending_pct` still misses retained
  empty-key entries, so it does not establish a bound either
  ([ginvacuum.c:507-558](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L507-L558)).
- **Nothing is a bound, a level or a decision until it is declared as one.** File
  the declaration before the run, as
  [The declarations, filed before the run](#the-declarations-filed-before-the-run)
  does, and publish `truth_pct` beside every scored column. A threshold or a kind
  chosen after the results is not a scored run.
- **Score nothing that has not been settled and maintained.** A census taken after
  the writes and before the settle step read the *as-built* numbers on `m1_pair` —
  14.08 against the 54.55 the same fixture reads once its settle step has run — so an
  unsettled reading is not a weak reading, it is the wrong file
  ([The maintenance step, measured](#the-maintenance-step-measured)).
- **`entry_slack` on a healthy index is a large fraction of an entry-tree-dominated
  file**: the nineteen freshly rebuilt indexes of this run read 12.04% to 56.72%
  slack while reclaiming nothing, and fresh payload fraction ran from 43.28% to
  87.96% across shapes. Treat it as a level, not a defect, and compare an index to
  its own history or to a rebuilt twin — never to another opclass.
- **`data_slack` is the honest bloat signal**: a posting-tree-dominated index with
  slack far above a fresh rebuild's has genuinely reclaimable space. `f6_slack_gin`
  and `m1_pair_gin`, the two fixtures whose slack is nearly all on data leaves, are
  also the two whose slack percentage lands nearest their reclaimed percentage
  (51.34 against 46.33, and 54.55 against 46.47).
- **If the comparison has to be exact, take a lock instead of reading a flag.** One
  `SHARE ROW EXCLUSIVE` transaction around the census blocked eight conflicting
  commands and turned a loop that read four different dead-page counts into 20
  identical censuses. Its one hole is a direct `gin_clean_pending_list()` by the
  index's owner, which locks only the index and moved `bloat_pct` from 1.46 to 92.00
  between two censuses in the same locked transaction
  ([The measurement protocol](#the-measurement-protocol)).
- **Read a busy index twice, and re-read `pg_relation_size` after the census.** The
  bracket caught 10 of 30 censuses taken under a writer stream; the progress views
  caught 3 of the 4 that overlapped a VACUUM and 2 of the 3 that overlapped a
  concurrent rebuild. A maintenance command that starts and finishes between the two
  progress reads is still invisible.
- **Publish the statistics before you analyze, or the census reads your own history
  as new churn.** `tc4_hazard` and `tc2_declined` differ by one
  `pg_stat_force_next_flush()` and read 10,500 against 500 modifications
  ([The simulated auto-analyze census](#the-simulated-auto-analyze-census)).
- **A fixture maintained by the auto-analyze stand-in carries stale metapage counts
  by construction**, so it may not claim the settle step and its metapage
  cross-check does not apply. `a1_analyze_gin` reads `n_total_pages` 43 against a
  93-block file, and the census flags it in every reading.
- **If the payload/fill model matters to your decision, run the entry-tuple probe
  beside the census.** Entry tuples far above the table's live distinct-key count
  mean the model is over-predicting the rebuild, by about half a point per percent
  of the key population that has died.
- **Dead pages that will not go away may be waiting on one idle transaction, not on
  VACUUM.** A held `REPEATABLE READ` snapshot kept 768 recyclable-looking pages out
  of the FSM across two VACUUMs, and the next VACUUM after it was gone recycled all
  768 with no new transaction ids.
- **`pending_bytes` is a `fastupdate` tuning signal, not waste.** Fix it with
  VACUUM, `gin_clean_pending_list()`, or `gin_pending_list_limit`.
- **If `gin_version <> 2`, publish the page counts and suppress the slack columns**
  — and every payload estimate derived from untrusted slack
  ([ginblock.h:302-309](../../../../raw/postgres-17/src/include/access/ginblock.h#L302-L309)).
  The baseline statement gates only the combined slack fields and `bloat_pct`; the
  guarded and derived statements withhold every slack-derived field when the version
  is not 2 or any page could not be decoded or classified, which the version-1
  corruption fixture confirms.
- **If `uncompressed_pages > 0`, the index carries pre-9.4 posting-tree leaves and
  its `data_slack` is understated.** It read 0 on all 26 censused indexes of this
  run, as it has in every run this page records.
- **Report the `maintenance_work_mem` a rebuild comparison was measured at.** The
  same churned index rebuilt to **7,880,704 bytes at 4MB** and **10,125,312 at both
  64MB and 1GB** in this run — a 22% difference from a setting, not from the data —
  so "what a rebuild would reclaim" is not a property of the index alone
  ([gininsert.c:290-291](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L290-L291)).
- **On a server older than 12.11, keep the `pagesize = 0` arm and the probe's
  `pagesize > 0` guard**, and census a suspect index on its own there, because a
  zeroed metapage aborts the whole multi-index report; see
  [Outside the protocol](#outside-the-protocol-the-four-statements-on-postgresql-12).

## Measurement Script

The page's measured numbers come from two scripts, one per version leg, both filed in
full below. `gin_waste_protocol.sh`, the
[PostgreSQL 17.11 leg](#the-postgresql-1711-leg), runs the whole protocol programme
and the 17.11 half of the portability battery. `gin_portability_12.sh`, the
[PostgreSQL 12.2 leg](#the-postgresql-122-leg), runs the same battery, byte for byte,
on 12.2. Both are Bash and SQL only: a reviewer needs a C toolchain, a shell and this
page. Numbers the page dates to an earlier pass are that pass's record, and open
question 22 says which parts of the page carry them.

### How to use it

| Item | 17.11 leg, `gin_waste_protocol.sh` | 12.2 leg, `gin_portability_12.sh` |
|---|---|---|
| Purpose | Builds PostgreSQL 17.11 out of tree from this repository's pinned checkout and runs this page's whole GIN waste programme under the five phases of [Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md): the filed declarations, 19 scored fixtures and 5 coverage fixtures, the simulated auto-analyze census, the locked decide pass, a measured `REINDEX INDEX` oracle per fixture, the four cross-checks, the entry-tuple and layout probes, eight corruption shapes, four concurrency cases, a physical standby, and the privilege, refusal, timeout, budget-sweep and cost cases. Outside the protocol, its `portability` stage is the 17.11 half of the battery that [Outside the protocol](#outside-the-protocol-the-four-statements-on-postgresql-12) reports | Builds PostgreSQL 12.2 out of tree from this repository's pinned v12 checkout and runs the same battery: the four published statements with and without the three edits, the derived probe, the decoders on an all-zero page, the refusals, `VACUUM VERBOSE`'s index report and the two harness constructs 12.2 lacks |
| Invocation | `bash .wiki-runtime/tmp/ginw5/gin_waste_protocol.sh [stage ...]`, run from the repository root. With no arguments it runs every stage except `clean`. Extract the fenced script to that path first | `bash .wiki-runtime/tmp/ginp12/gin_portability_12.sh [stage ...]`, the same way |
| Stages | Default order: `build check init declare fixtures coverage census decide crosscheck probe standby oracle probe_after score sweep race corrupt portability report`. `build` configures and installs out of tree and skips when the binary exists; `check` runs [`make check`](../../../glossary.md#regression-test) plus the five [contrib](../../../glossary.md#contrib) suites this page uses; `init` initdbs, writes the cluster settings and creates the three databases and five extensions; `declare` files the declared kind of every published column **before any fixture exists**; `fixtures` runs the build phase, the baseline census, then the churn phase (writes, settle, maintenance) and the late baseline, and writes every census and phase note it stored to `20-phases.txt`; `coverage` runs the held-snapshot, stale-catalog, privilege, refusal, measurement-lock and pending-list-hole cases; `census` recomputes the launcher's analyze verdict for every table and analyzes the ones it names; `decide` takes `SHARE ROW EXCLUSIVE` on every fixture table in one transaction and censuses inside it; `crosscheck` runs the FSM, metapage and identity checks; `probe` runs the entry-tuple probe per fixture, counts the distinct keys two tables hold without the index, and runs the layout probe once; `standby` takes a [`pg_basebackup`](../../../glossary.md#base-backup) replica and tries the three refusals on it; `oracle` rebuilds each scored index between two `pg_relation_size` readings and prints the rebuilt census; `probe_after` runs the entry-tuple probe a second time on the rebuilt indexes, so the dead-key population is `before − after`; `score` joins the declarations to the oracle and prints the verdicts; `sweep` rebuilds one index at three memory budgets and measures the census's cost; `race` runs the four concurrency cases in their own database; `corrupt` patches eight index files with the server stopped, in two cycles; `portability` runs the battery in two databases of its own, stopping the server once to patch two index files; `report` collects everything into `out/summary.txt`. `clean` is not in the default order and must be run last | Default order: `build check init portability report`. `build` configures with the same flags and installs `pageinspect`, `pgstattuple` and `pg_freespacemap`; `check` runs `make check` plus the `pageinspect` and `pgstattuple` suites, and records that `pg_freespacemap` 1.2 declares none in this tree; `init` initdbs with the 17.11 leg's settings minus the standby's; `portability` is the battery, the same stage text as the 17.11 leg's; `report` writes `out/summary.txt`. `clean` is not in the default order |
| Environment | `REPO` (`$PWD`), `SRC17` (`$REPO/raw/postgres-17`), `SANDBOX` (`$REPO/.wiki-runtime/tmp/ginw5`), `JOBS` (`8`), `PORT` (`55417`, and the standby takes `PORT + 1`), `ROWS` (`200000`), `MWM` (`64MB`), `STMT_TIMEOUT` (`600s`), `LOCK_TIMEOUT` (`2s`). `RACE_LOOPS` (`40`) is declared, but no stage reads it; each race loop stops at 300 censuses | `REPO` (`$PWD`), `SRC12` (`$REPO/raw/postgres-12`), `SANDBOX` (`$REPO/.wiki-runtime/tmp/ginp12`), `JOBS` (`8`), `PORT` (`55412`), `STMT_TIMEOUT` (`600s`), `LOCK_TIMEOUT` (`2s`) |
| Prerequisites | See [Prerequisites](#prerequisites) | the same |
| Output | Everything lands under `$SANDBOX/out/`; see [Where the results land](#where-the-results-land). Read `out/summary.txt` first | Everything lands under `$SANDBOX/out/`. Read `out/19-portability.txt` first, and compare it line by line with the 17.11 leg's |
| Runtime | About 11.5 minutes from an empty sandbox on the recorded host: 1 min 36 s for the build, 60 s for the six regression suites, 1 min 18 s for the fixtures, 34 s for the coverage cases, 3 s for the census, decide, crosscheck and probe stages together, 10 s for the oracle, 1 s for `probe_after` and `score`, 3 s for the sweep, 6 s for the race cases and a second each for `corrupt` and `portability` - and **6 min 25 s for the standby stage**. Nearly all of that is two spread [checkpoints](../../../glossary.md#checkpoint): one the churn's WAL had already started, then the one `pg_basebackup` asks for, at its default `spread` pace ([pg_basebackup.sgml:499-504](../../../../raw/postgres-17/doc/src/sgml/ref/pg_basebackup.sgml#L499-L504), [pg_basebackup.sgml:968-971](../../../../raw/postgres-17/doc/src/sgml/ref/pg_basebackup.sgml#L968-L971), [xlog.c:8940-8959](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L8940-L8959)). Skip `standby` and a run from an empty sandbox takes about 5 minutes; skip `build` as well, on a built tree, and it takes about 3.3 minutes | 2 min 13 s from an empty sandbox on the recorded host: 1 min 34 s for the build, 35 s for the three regression suites, 1 s to initdb and 3 s for the battery |
| Cleanup | `bash gin_waste_protocol.sh clean` stops the standby if one is still present, stops the primary, reports whether a `postmaster.pid` or a process with the data directory in its arguments survived, and deletes the whole sandbox | `bash gin_portability_12.sh clean` does the same for its one cluster |

### Prerequisites

- A C toolchain, `make`, `flex`, `bison` and `perl`. The recorded runs used Apple
  clang 21.0.0 on Darwin 27.0.0 arm64, with GNU Make 3.81, bison 2.3 and flex 2.6.4;
  the 2026-09-16 runs used gcc 13.3.0 on Linux x86_64. Each script builds its own
  server; no installed PostgreSQL is used, and neither touches a cluster it did not
  create.
- No ICU, readline or zlib development headers are needed: both legs configure
  `--without-icu --without-readline --without-zlib`, and `initdb` runs with
  `--locale=C --encoding=UTF8`, which is what makes the `pg_trgm` and `tsvector`
  fixtures deterministic.
- The pinned checkouts at `raw/postgres-17` and, for the 12.2 leg, `raw/postgres-12`,
  read-only. Both scripts build out of tree and write nothing inside them.
- Ports 55417 and 55418 free for the 17.11 leg and 55412 for the 12.2 leg, and about
  4 GB under `.wiki-runtime/tmp/`.
- `dd` and `printf`, which the `corrupt` and `portability` stages use to patch pages
  with the server stopped. Appends go through shell redirection, because BSD `dd`, as
  on macOS, has no `oflag=append`. `psql` is reached only through the sandbox's own
  socket directory. Every call is `psql -X -v ON_ERROR_STOP=1`, so a stray
  `~/.psqlrc` cannot change a result and no error passes silently; the statements
  whose *error text* is the result being measured go through a second wrapper
  without `ON_ERROR_STOP`.

### Where the results land

| File | What is in it |
|---|---|
| `summary.txt` | every file below, in one place; read this first |
| `00-declarations.txt` | the declared kind of every published column, with the second it was filed at |
| `01-fixtures.txt` | the fixture registry: which are scored, which claim the settle step, and what each one's maintenance was; then the declarations' and the first fixture census's timestamps to the millisecond |
| `02-census.txt` | the simulated auto-analyze census, its recheck, and the walked/analyzed/verdict counts |
| `03-decide-pages.txt`, `04-decide-bytes.txt` | the locked decide census, page classes and byte columns, plus the interval the lock was held |
| `05-oracle.txt`, `06-score.txt`, `07-payload-model.txt` | the rebuild results and the census of the rebuilt indexes, the scored bounds with their verdicts, and the payload/fill predictions |
| `08-crosscheck-fsm.txt`, `09-crosscheck-metapage.txt`, `10-crosscheck-verbose.txt` | the three cross-checks that are not the size bracket, including the `n_data_pages` identity and every `VACUUM VERBOSE` index line the churn printed |
| `11-entry-tuple-probe.txt`, `12-layout-probe.txt` | the per-fixture entry-tuple counts and the distinct keys two tables hold, and the four page-format constants measured on the build |
| `13-coverage.txt` | the held snapshot, stale catalog row, privileges, refusals, the ten locked commands and the pending-list hole |
| `14-race.txt`, `15-corrupt.txt`, `16-standby.txt`, `17-sweep.txt` | the four concurrency cases, the eight corruption shapes with the derived probe on two of them, the standby refusals, and the budget sweep with the cost measurements |
| `18-entry-tuple-probe-after.txt` | the same probe on the rebuilt indexes, with `dead_entry_tuples` as the difference |
| `19-portability.txt` | the portability battery; the 12.2 leg writes the same file |
| `20-phases.txt` | every census the build and churn phases stored (the baseline and late baseline of every fixture, and the mid-churn readings of `f2`, `m1` and `a1`), then every phase note: catalog rows, counters and metapage readings |
| `checks.txt`, `check_*.log` | the regression suites and their logs |
| `platform.txt`, `server_version.txt`, `version.txt` | `pg_control_init()`, the settings the run fixes, the installed extension versions |
| `churn.txt`, `decide.txt`, `run.log`, `server.log` | the churn phase's own output including every VERBOSE line, the decide transaction, the stage log the script writes, and the server log |
| `configure.log`, `make.log`, `install.log`, `contrib.log`, `initdb.log` | build diagnostics |

The 12.2 leg writes `19-portability.txt`, `checks.txt` and `check_*.log`,
`platform.txt`, `server_version.txt`, `version.txt`, `run.log`, `server.log`, the build
logs and `summary.txt` into its own `out/`.

### The last run

| Fact | 17.11 leg | 12.2 leg |
|---|---|---|
| Date | 2026-09-24, 13:49:56 to 14:01:15 EDT, from an empty sandbox | 2026-09-24, 13:28:49 to 13:31:02 EDT, from an empty sandbox |
| Host | Darwin 27.0.0 arm64 (macOS 27.0), Apple clang 21.0.0, 10 cores, `JOBS=8` | the same |
| Server | 17.11 from `786db8dcf168bd9df8f55047337525ac19118b1c`, `--enable-debug --without-icu --without-readline --without-zlib` | 12.2 from `45b88269a353ad93744772791feb6d01bc7e1e42`, the same flags |
| Regression | `make check` **All 225 tests passed**; `pageinspect` **All 8**, `pgstattuple` **All 1**, `pg_freespacemap` **All 1**, `btree_gin` **All 30**, `pg_trgm` **All 4** ([regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59)) | `make check` **All 192 tests passed**; `pageinspect` **All 5**, `pgstattuple` **All 1**; no `pg_freespacemap` suite |
| Platform facts | `block_size` 8192, `max_data_alignment` 8, [`data_page_checksum_version`](../../../glossary.md#data-checksums) 0, `MaxFSMRequestSize` 8160 derived and measured two ways | `block_size` 8192, `max_data_alignment` 8, `data_page_checksum_version` 0, and 8160 from the FSM check |
| Cluster | `initdb --locale=C --encoding=UTF8`; `autovacuum = off`, `fsync = off`, `shared_buffers = 256MB`, `max_wal_size = 2GB`, [`wal_level = replica`](../../../glossary.md#wal-level), `max_wal_senders = 4` set in `postgresql.conf` before the first start; port 55417, socket and data directory inside the sandbox | the same, without the two replication settings; port 55412 |
| Extensions | `pageinspect` 1.12, `pgstattuple` 1.5, `pg_freespacemap` 1.2, `btree_gin` 1.3, `pg_trgm` 1.6 | `pageinspect` 1.7, `pgstattuple` 1.5, `pg_freespacemap` 1.2 |
| Declarations | filed at 13:52:33.716; the first fixture census ran at 13:52:50.295, 16.6 seconds later | - |
| Corpus | 19 scored fixtures and 5 coverage fixtures; the decide census covered 26 GIN indexes over 23,743 blocks; the database held 27 GIN indexes over 14,719 blocks after the oracle's rebuilds, the invalid `tinv_bad` included; plus 3 GIN indexes in the race database, 8 in the corruption database and 8 in the two portability databases | the battery's 8 GIN indexes in its two databases, 6 of which a census can see: 4 in `port` and 2 in `portmeta`; the invalid and the partitioned index are excluded |
| Result | 17 lower-bound HELD / 2 VIOLATED, 19 upper-bound HELD, 0 size-bracket failures, 24 of 24 FSM checks within the census, 24 of 24 `n_data_pages` identities exact, 23 of 26 metapage entry-page counts | every portability difference the section reports, and no other line of `19-portability.txt` differs between the legs except the version strings |
| Reproduction | every scored cell equals the 2026-09-16 filing, `f9c_cleanup` aside. So did a baseline pass of the filed script on the same host, and a third pass that day moved `g50_gin` by one page (open question 23) | - |
| Script | SHA-256 `d5412b8463b653ebb963f6a653f4bcc84a32e7c4c42ecc913a2e80f73fbb8267`; the fenced block below is byte-identical to the file that ran | SHA-256 `24d248019268024b9ba1bd31679d66a993a2e93a074ccf775fac3770c064ea01`; the same |
| Teardown | the `clean` stage stopped the server and deleted the sandbox; see the log entry for the confirmation | the same |

If a script is edited after this, re-run it before changing any number it produced.

### The PostgreSQL 17.11 leg

```bash
#!/usr/bin/env bash
#
# gin_waste_protocol.sh - the PostgreSQL 17.11 leg of the measurement script
# for the wiki page
#   wiki/v17/questions/indexing/gin-index-wasted-space-contrib.md
#
# It builds PostgreSQL 17.11 out of tree from this repository's pinned
# checkout and runs that page's whole GIN waste programme under the five
# phases of
#   wiki/v17/common-concepts/mandatory-gin-bloat-tests.md
# build, baseline, churn (writes -> settle -> maintenance -> census), decide
# under the SHARE ROW EXCLUSIVE measurement lock, and a measured
# REINDEX INDEX oracle bracketed by pg_relation_size(index, 'main').
#
# Every declared kind is filed by the "declare" stage before any fixture is
# built, so the declaration cannot be rewritten after the results.
#
# The "portability" stage is outside the protocol: it is the 17.11 half of the
# page's PostgreSQL 12 portability battery, and gin_portability_12.sh, the
# 12.2 leg, runs the same stage text on a 12.2 build.
#
# Everything it creates is disposable.  It runs its own cluster, on a
# non-default port, under its own sandbox, and never touches a cluster it did
# not create.  The "clean" stage stops it and deletes the sandbox.
#
# Usage:
#   bash gin_waste_protocol.sh                 # every stage except clean
#   bash gin_waste_protocol.sh decide oracle   # selected stages, in order given
#   bash gin_waste_protocol.sh clean           # stop server, delete sandbox
#
set -uo pipefail

REPO="${REPO:-$PWD}"
SRC17="${SRC17:-$REPO/raw/postgres-17}"
SANDBOX="${SANDBOX:-$REPO/.wiki-runtime/tmp/ginw5}"
JOBS="${JOBS:-8}"
PORT="${PORT:-55417}"
ROWS="${ROWS:-200000}"
MWM="${MWM:-64MB}"
STMT_TIMEOUT="${STMT_TIMEOUT:-600s}"
LOCK_TIMEOUT="${LOCK_TIMEOUT:-2s}"
RACE_LOOPS="${RACE_LOOPS:-40}"

BUILD="$SANDBOX/build"; INST="$SANDBOX/install"; DATA="$SANDBOX/data"
BIN="$INST/bin"; SOCK="$SANDBOX/sock"; OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql"
STANDBY="$SANDBOX/standby"; SBSOCK="$SANDBOX/sbsock"; SBPORT=$((PORT + 1))
DB=waste; RACEDB=race; CORRDB=corrupt

# Both also append to $OUT/run.log, the stage log, whenever $OUT exists.
note() { local m; m=$(printf '[%s] %s' "$(date +%H:%M:%S)" "$*")
         printf '%s\n' "$m" >&2; [ -d "$OUT" ] && printf '%s\n' "$m" >>"$OUT/run.log"; return 0; }
die()  { local m; m=$(printf '[%s] FATAL: %s' "$(date +%H:%M:%S)" "$*")
         printf '%s\n' "$m" >&2; [ -d "$OUT" ] && printf '%s\n' "$m" >>"$OUT/run.log"; exit 1; }

# psql wrappers.  -X ignores ~/.psqlrc, ON_ERROR_STOP=1 lets no error pass
# silently, and both timeouts are PGC_USERSET, so session-scoped.
p() { local db="$1"; shift
  PGOPTIONS="-c statement_timeout=$STMT_TIMEOUT -c lock_timeout=$LOCK_TIMEOUT" \
  "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$db" "$@"; }
q() { local db="$1"; shift; p "$db" -At -c "$*"; }
# the same, without ON_ERROR_STOP: for the statements whose error text is the
# result being measured (refusals, timeouts, corruption)
pe() { local db="$1"; shift
  PGOPTIONS="-c statement_timeout=$STMT_TIMEOUT -c lock_timeout=$LOCK_TIMEOUT" \
  "$BIN/psql" -X -h "$SOCK" -p "$PORT" -d "$db" "$@" 2>&1; }

pgstart() { "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w -o "-p $PORT -k $SOCK" start; }
pgstop()  { [ -f "$DATA/postmaster.pid" ] && "$BIN/pg_ctl" -D "$DATA" -m fast -w stop; true; }

# ------------------------------------------------------------------ the census
#
# The scored statement: the page's derived census, verbatim, as one expression
# so a run can store it.  Every block-size and alignment constant comes from
# pg_control_init(); the only GIN literal left is sizeof(GinPageOpaqueData),
# which PageInit stores MAXALIGNed as BLCKSZ - pd_special.
read -r -d '' CENSUS <<'CENSUS_SQL'
WITH /* wiki_gin_waste_census_derived */ ctl AS (
    SELECT database_block_size::bigint                          AS bs,
           max_data_alignment::bigint                           AS al,
           ((8 + max_data_alignment - 1) / max_data_alignment)
             * max_data_alignment                               AS gin_special
    FROM pg_control_init()
),
gin_idx AS (
    SELECT c.oid                                  AS idx,
           c.oid::regclass::text                  AS idx_name,
           x.indrelid                             AS tbl,
           pg_relation_size(c.oid, 'main')         AS main_bytes,
           k.bs, k.gin_special,
           EXISTS (SELECT 1 FROM pg_stat_progress_vacuum v  WHERE v.relid = x.indrelid)
             OR EXISTS (SELECT 1 FROM pg_stat_progress_analyze z WHERE z.relid = x.indrelid)
                                                  AS maint_before,
           EXISTS (SELECT 1 FROM pg_stat_progress_create_index i WHERE i.relid = x.indrelid)
                                                  AS build_before
    FROM pg_class c
         JOIN pg_am a    ON a.oid = c.relam
         JOIN pg_index x ON x.indexrelid = c.oid
         CROSS JOIN ctl k
    WHERE a.amname = 'gin'
      AND c.relkind = 'i'            -- 'I' (partitioned) has no storage
      AND x.indisvalid               -- an invalid index is still readable, see notes
      AND c.relpersistence <> 't'    -- another session's temp index is refused
),
meta AS (
    SELECT g.*,
           (h0.upper > 0 AND h0.pagesize = g.bs
              AND h0.pagesize - h0.special = g.gin_special)     AS meta_layout_ok,
           h0.pagesize - h0.special                             AS meta_special_seen,
           o0.flags                                             AS meta_flags,
           m.version, m.n_pending_pages, m.n_pending_tuples,
           m.n_total_pages, m.n_entry_pages, m.n_data_pages
    FROM gin_idx g
         CROSS JOIN LATERAL (SELECT get_raw_page(g.idx_name, 0) AS pg OFFSET 0) AS r0
         LEFT JOIN LATERAL page_header(r0.pg) AS h0 ON true
         LEFT JOIN LATERAL gin_page_opaque_info(
               CASE WHEN h0.upper > 0 AND h0.pagesize = g.bs
                     AND h0.pagesize - h0.special = g.gin_special
                    THEN r0.pg END) AS o0 ON true
         LEFT JOIN LATERAL gin_metapage_info(
               CASE WHEN o0.flags = '{meta}'::text[] THEN r0.pg END) AS m ON true
),
pages AS (
    SELECT g.idx,
           CASE
               WHEN h.upper = 0                                        THEN 'new'
               WHEN h.pagesize <> g.bs
                     OR h.pagesize - h.special <> g.gin_special        THEN 'invalid'
               WHEN EXISTS (SELECT 1 FROM unnest(o.flags) f
                            WHERE f NOT IN ('data', 'leaf', 'deleted', 'meta', 'list',
                                            'list_fullrow', 'incomplete_split', 'compressed'))
                                                                       THEN 'unknown'
               WHEN o.flags @> '{meta}'                 THEN 'meta'
               WHEN o.flags @> '{deleted}'              THEN 'deleted'
               WHEN o.flags @> '{list}'                 THEN 'pending'
               WHEN o.flags @> '{data,leaf,compressed}' THEN 'data_leaf'
               WHEN o.flags @> '{data,leaf}'            THEN 'data_leaf_uncompressed'
               WHEN o.flags @> '{data}'                 THEN 'data_internal'
               WHEN o.flags <@ '{leaf,incomplete_split}'::text[] THEN 'entry'
               ELSE                                          'unknown'
           END                                          AS page_class,
           COALESCE(h.upper - h.lower, 0)               AS slack
    FROM gin_idx g
         CROSS JOIN LATERAL generate_series(1, g.main_bytes / g.bs - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page(g.idx_name, b.blkno::int) AS pg
                             OFFSET 0) AS r
         LEFT JOIN LATERAL page_header(r.pg)          AS h ON true
         LEFT JOIN LATERAL gin_page_opaque_info(
               CASE WHEN h.upper > 0 AND h.pagesize = g.bs
                     AND h.pagesize - h.special = g.gin_special
                    THEN r.pg END)                   AS o ON true
),
census AS (
    SELECT idx,
           count(*) FILTER (WHERE page_class = 'entry')                  AS entry_pages,
           count(*) FILTER (WHERE page_class = 'data_leaf')              AS data_leaf_pages,
           count(*) FILTER (WHERE page_class = 'data_internal')          AS data_internal_pages,
           count(*) FILTER (WHERE page_class = 'data_leaf_uncompressed') AS uncompressed_pages,
           count(*) FILTER (WHERE page_class = 'pending')                AS pending_pages,
           count(*) FILTER (WHERE page_class = 'deleted')                AS deleted_pages,
           count(*) FILTER (WHERE page_class = 'new')                    AS new_pages,
           count(*) FILTER (WHERE page_class = 'meta')                   AS stray_meta_pages,
           count(*) FILTER (WHERE page_class = 'invalid')                AS invalid_pages,
           count(*) FILTER (WHERE page_class = 'unknown')                AS unknown_pages,
           COALESCE(sum(slack) FILTER (WHERE page_class = 'entry'), 0)   AS entry_slack,
           COALESCE(sum(slack) FILTER (WHERE page_class IN ('data_leaf',
                                            'data_internal')), 0)        AS data_slack
    FROM pages
    GROUP BY idx
),
after AS (
    SELECT c.idx,
           pg_relation_size(c.idx, 'main')                                   AS main_bytes_after,
           EXISTS (SELECT 1 FROM pg_stat_progress_vacuum v
                   WHERE v.relid = (SELECT tbl FROM gin_idx g WHERE g.idx = c.idx))
             OR EXISTS (SELECT 1 FROM pg_stat_progress_analyze z
                   WHERE z.relid = (SELECT tbl FROM gin_idx g WHERE g.idx = c.idx))
                                                                             AS maint_after,
           EXISTS (SELECT 1 FROM pg_stat_progress_create_index i
                   WHERE i.relid = (SELECT tbl FROM gin_idx g WHERE g.idx = c.idx))
                                                                             AS build_after
    FROM census c
),
verdict AS (
    SELECT m.idx, m.idx_name, m.main_bytes, m.bs, m.version,
           m.n_pending_pages, m.n_entry_pages, m.n_data_pages, m.n_total_pages,
           c.*, a.main_bytes_after,
           COALESCE(NULLIF(array_to_string(array_remove(ARRAY[
             CASE WHEN NOT (m.meta_layout_ok AND m.meta_flags = '{meta}'::text[])
                  THEN 'metapage unreadable' END,
             CASE WHEN m.meta_special_seen IS NOT NULL
                   AND m.meta_special_seen <> m.gin_special
                  THEN 'metapage special area ' || m.meta_special_seen
                       || ' bytes, expected ' || m.gin_special END,
             CASE WHEN m.version IS NOT NULL AND m.version <> 2
                  THEN 'unsupported format: version ' || m.version END,
             CASE WHEN c.invalid_pages > 0
                  THEN c.invalid_pages || ' page(s) not decodable' END,
             CASE WHEN c.unknown_pages > 0
                  THEN c.unknown_pages || ' page(s) of unknown class' END,
             CASE WHEN a.main_bytes_after <> m.main_bytes
                  THEN 'size changed during scan' END,
             CASE WHEN m.n_pending_pages IS NOT NULL AND c.pending_pages <> m.n_pending_pages
                  THEN 'pending count disagrees with metapage' END,
             CASE WHEN m.n_total_pages IS NOT NULL AND m.n_total_pages <> m.main_bytes / m.bs
                  THEN 'metapage page counts predate the file length' END,
             CASE WHEN m.maint_before OR a.maint_after
                  THEN 'vacuum or analyze in progress' END,
             CASE WHEN m.build_before OR a.build_after
                  THEN 'index build in progress' END
           ], NULL), '; '), ''), 'ok')                                       AS status,
           (m.version = 2 AND c.invalid_pages = 0 AND c.unknown_pages = 0)     AS slack_trusted
    FROM meta m
         JOIN census c ON c.idx = m.idx
         JOIN after  a ON a.idx = m.idx
)
SELECT v.idx_name                                       AS index_name,
       v.status,
       v.version                                        AS gin_version,
       v.main_bytes                                     AS main_fork_bytes,
       v.main_bytes / v.bs                              AS blocks,
       v.entry_pages, v.data_leaf_pages, v.data_internal_pages,
       v.uncompressed_pages, v.pending_pages, v.deleted_pages, v.new_pages,
       v.invalid_pages, v.unknown_pages,
       (v.deleted_pages + v.new_pages) * v.bs           AS whole_page_waste_bytes,
       round(100.0 * (v.deleted_pages + v.new_pages) * v.bs
             / nullif(v.main_bytes, 0), 2)              AS whole_page_waste_pct,
       CASE WHEN v.slack_trusted THEN v.entry_slack + v.data_slack END
                                                        AS live_page_slack_bytes,
       CASE WHEN v.slack_trusted
            THEN round(100.0 * (v.entry_slack + v.data_slack)
                       / nullif(v.main_bytes, 0), 2) END AS live_page_slack_pct,
       CASE WHEN v.slack_trusted
            THEN round(100.0 * ((v.deleted_pages + v.new_pages) * v.bs
                                + v.entry_slack + v.data_slack)
                       / nullif(v.main_bytes, 0), 2) END AS bloat_pct,
       CASE WHEN v.slack_trusted THEN v.entry_slack END  AS entry_slack,
       CASE WHEN v.slack_trusted THEN v.data_slack END   AS data_slack,
       v.pending_pages * v.bs                           AS pending_bytes,
       round(100.0 * v.pending_pages * v.bs
             / nullif(v.main_bytes, 0), 2)              AS pending_pct,
       CASE WHEN v.slack_trusted
            THEN v.main_bytes - (v.deleted_pages + v.new_pages + v.pending_pages) * v.bs
                              - v.entry_slack - v.data_slack END
                                                        AS payload_bytes,
       v.n_pending_pages                                AS meta_pending_pages,
       v.n_entry_pages                                  AS meta_entry_pages,
       v.n_data_pages                                   AS meta_data_pages,
       v.n_total_pages                                  AS meta_total_pages,
       1 + v.entry_pages + v.data_leaf_pages + v.data_internal_pages
         + v.uncompressed_pages + v.pending_pages + v.deleted_pages
         + v.new_pages + v.stray_meta_pages + v.invalid_pages + v.unknown_pages
                                                        AS census_total_pages,
       v.main_bytes_after / v.bs                        AS blocks_after_census
FROM verdict v
ORDER BY 1
CENSUS_SQL

# Store one census pass under a run label.  The published text is wrapped in
# INSERT ... SELECT * FROM ( ... ) q and not otherwise edited.
census_into() {   # census_into <db> <run-label>
  p "$1" -q -c "INSERT INTO wiki.census_run SELECT '$2', clock_timestamp(), q.* FROM ( $CENSUS ) q;" \
    || die "census pass '$2' failed on database $1"
}

# ---------------------------------------------------------------- build stages

stage_build() {
  [ -x "$BIN/postgres" ] && { note "17.11 already built, skipping"; return 0; }
  [ -d "$SRC17" ] || die "no pinned checkout at $SRC17"
  mkdir -p "$BUILD" "$OUT" || die "mkdir failed"
  note "configuring 17.11 out of tree (read-only source at $SRC17)"
  ( cd "$BUILD" && "$SRC17/configure" --prefix="$INST" --enable-debug \
      --without-icu --without-readline --without-zlib ) >"$OUT/configure.log" 2>&1 \
    || die "configure failed, see $OUT/configure.log"
  note "make -j$JOBS"
  make -C "$BUILD" -j"$JOBS" >"$OUT/make.log" 2>&1 || die "make failed, see $OUT/make.log"
  make -C "$BUILD" install >"$OUT/install.log" 2>&1 || die "make install failed"
  note "make -j$JOBS contrib"
  make -C "$BUILD/contrib" -j"$JOBS" install >"$OUT/contrib.log" 2>&1 \
    || die "contrib build failed, see $OUT/contrib.log"
  "$BIN/postgres" --version | tee "$OUT/version.txt"
}

stage_check() {
  note "make check (core) plus the five contrib suites this page uses"
  : >"$OUT/checks.txt"
  make -C "$BUILD" check >"$OUT/check_core.log" 2>&1
  tail -3 "$OUT/check_core.log" | tee -a "$OUT/checks.txt"
  local c
  for c in pageinspect pgstattuple pg_freespacemap btree_gin pg_trgm; do
    make -C "$BUILD/contrib/$c" check >"$OUT/check_$c.log" 2>&1
    printf '%s: ' "$c" >>"$OUT/checks.txt"
    tail -3 "$OUT/check_$c.log" | tr -d '\n' | tee -a "$OUT/checks.txt"
    printf '\n' >>"$OUT/checks.txt"
  done
  cat "$OUT/checks.txt"
}

stage_init() {
  pgstop
  rm -rf "$DATA" "$SOCK" "$STANDBY" "$SBSOCK"
  mkdir -p "$SOCK" "$OUT" "$SQLD" || die "mkdir failed"
  "$BIN/initdb" -D "$DATA" --locale=C --encoding=UTF8 >"$OUT/initdb.log" 2>&1 \
    || die "initdb failed, see $OUT/initdb.log"
  # All four are PGC_SIGHUP or PGC_POSTMASTER, so they are set in
  # postgresql.conf before the first start: autovacuum off for isolation (the
  # maintenance it would have run is run by the fixtures), fsync off because
  # the cluster is disposable, and wal_level replica for the standby stage.
  cat >>"$DATA/postgresql.conf" <<CONF
autovacuum = off
fsync = off
shared_buffers = 256MB
max_wal_size = 2GB
wal_level = replica
max_wal_senders = 4
logging_collector = off
log_min_messages = warning
log_autovacuum_min_duration = 0
CONF
  pgstart || die "server did not start"
  local d
  for d in "$DB" "$RACEDB" "$CORRDB"; do
    q postgres "CREATE DATABASE $d" >/dev/null || die "CREATE DATABASE $d failed"
    for e in pageinspect pgstattuple pg_freespacemap btree_gin pg_trgm; do
      q "$d" "CREATE EXTENSION $e" >/dev/null || die "CREATE EXTENSION $e failed on $d"
    done
  done
  q "$DB" "SELECT version()" | tee "$OUT/server_version.txt"
  p "$DB" -c "SELECT /* wiki_gin_platform */ * FROM pg_control_init()" \
    > "$OUT/platform.txt"
  p "$DB" -c "SELECT /* wiki_gin_platform */ name, setting, source
              FROM pg_settings
              WHERE name IN ('block_size','autovacuum','fsync','maintenance_work_mem',
                             'gin_pending_list_limit','stats_fetch_consistency',
                             'autovacuum_analyze_threshold','autovacuum_analyze_scale_factor',
                             'autovacuum_vacuum_threshold','autovacuum_vacuum_scale_factor',
                             'autovacuum_vacuum_insert_threshold',
                             'autovacuum_vacuum_insert_scale_factor')
              ORDER BY 1" >> "$OUT/platform.txt"
  p "$DB" -c "SELECT /* wiki_gin_platform */ name, default_version, installed_version
              FROM pg_available_extensions
              WHERE installed_version IS NOT NULL ORDER BY 1" >> "$OUT/platform.txt"
  cat "$OUT/platform.txt"
}

# ------------------------------------------------------------- declare stage
#
# Filed before any fixture exists.  The two bound columns are the page's
# standing claims, so the run tests them instead of assuming them; everything
# else is a level, which the protocol never scores as a bound and never
# publishes as reclaimable space.
stage_declare() {
  mkdir -p "$OUT" "$SQLD"
  p "$DB" -q <<'SQL' || die "declare failed"
DROP SCHEMA IF EXISTS wiki CASCADE;
CREATE SCHEMA wiki;

CREATE TABLE wiki.declaration (
    col           text primary key,
    declared_kind text not null check (declared_kind in ('oracle','lower bound','upper bound','level')),
    claim         text not null,
    declared_at   timestamptz not null default clock_timestamp()
);
INSERT INTO wiki.declaration (col, declared_kind, claim) VALUES
 ('truth_pct',             'oracle',      '100 * (bytes before REINDEX - bytes after) / bytes before, from the two pg_relation_size(index, ''main'') readings and nothing else'),
 ('whole_page_waste_pct',  'lower bound', 'never exceeds the share of the file a rebuild returns'),
 ('bloat_pct',             'upper bound', 'never less than the share of the file a rebuild returns'),
 ('live_page_slack_pct',   'level',       'insertion capacity on entry pages and a physical gap on data pages; no relation to a rebuild'),
 ('entry_slack',           'level',       'entry-page gap bytes, which a fresh build also carries'),
 ('data_slack',            'level',       'posting-tree gap bytes'),
 ('pending_pct',           'level',       'deferred work, not waste'),
 ('payload_bytes',         'level',       'size minus dead, pending and slack; carries entry tuples for keys that no longer occur'),
 ('payload_fill_pred',     'level',       'payload_bytes / rebuilt fill fraction, a prediction whose divisor comes from the rebuild it predicts'),
 ('census_total_pages',    'level',       'accounting identity against blocks; proves no page was dropped, not that a class is right');

CREATE TABLE wiki.fixture (
    fixture text primary key,
    idx     text not null,
    tbl     text not null,
    scored  boolean not null,
    settled boolean not null,
    maintenance text not null,
    note    text not null
);

CREATE TABLE wiki.phase_note (
    fixture text, phase text, ran_at timestamptz default clock_timestamp(), note text
);

CREATE TABLE wiki.oracle (
    fixture text, idx text, mwm text,
    bytes_before bigint, bytes_after bigint, truth_pct numeric, elapsed_ms numeric
);

CREATE TABLE wiki.fsm_check (
    fixture text, idx text, free_page_avail bigint, fsm_free_pages bigint, fsm_blocks bigint
);

CREATE TABLE wiki.probe (
    fixture text, idx text, entry_leaf_pages bigint, entry_leaf_tuples bigint,
    entry_leaf_tuple_bytes bigint, internal_downlinks bigint,
    malformed_pages bigint, undecoded_pages bigint
);
SQL
  # The census result table takes its shape from the scored statement itself.
  p "$DB" -q -c "CREATE TABLE wiki.census_run AS
                 SELECT ''::text AS run, clock_timestamp() AS taken_at, q.*
                 FROM ( $CENSUS ) q WITH NO DATA;" || die "census_run shape failed"
  p "$DB" -c "SELECT /* wiki_gin_declarations */ col, declared_kind, claim,
                     to_char(declared_at, 'YYYY-MM-DD HH24:MI:SS') AS declared_at
              FROM wiki.declaration ORDER BY col" | tee "$OUT/00-declarations.txt"
}

# ----------------------------------------------------------------- SQL files
#
# Written by whichever stage needs them, so a single stage can be re-run.
write_sql_files() {
  mkdir -p "$SQLD" || die "mkdir $SQLD failed"

  # One census pass under the label in :run.  The scored statement is used
  # verbatim; only the INSERT wrapper is added.
  cat >"$SQLD/census_insert.sql" <<CI
INSERT INTO wiki.census_run SELECT :'run', clock_timestamp(), q.* FROM (
$CENSUS
) q;
CI

  cat >"$SQLD/10_build.sql" <<'SQL'
-- The build phase: create the table, load it, create the index that is
-- scored, settle it.  Every object below is disposable: the script creates
-- and drops them on a cluster of its own, and nothing here belongs in a
-- database anyone cares about.
SET /* wiki_gin_fixture_build */ statement_timeout = '600s';
SET /* wiki_gin_fixture_build */ lock_timeout = '2s';
SET /* wiki_gin_fixture_build */ maintenance_work_mem = :'mwm';
-- PGC_USERSET, session scope: without it GIN flushes a fastupdate index in
-- the foreground at 4MB and no fixture could hold a populated pending list.
SET /* wiki_gin_fixture_build */ gin_pending_list_limit = '1GB';

-- f1: entry-tree churn that replaces the key population
CREATE TABLE /* wiki_gin_fixture_build */ t1_churn (id int primary key, doc text);
INSERT INTO /* wiki_gin_fixture_build */ t1_churn
SELECT i, 'w' || (i % 50021) || ' w' || ((i * 7) % 50021) || ' w' || ((i * 13) % 50021)
          || ' w' || ((i * 17) % 50021) || ' w' || ((i * 23) % 50021)
          || ' w' || ((i * 29) % 50021) || ' hot' || (i % 7)
FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_fixture_build */ f1_churn_gin
    ON t1_churn USING gin (to_tsvector('simple', doc)) WITH (fastupdate = off);
-- Publish first, analyze second: pgstat_report_analyze zeroes
-- mod_since_analyze, and any count the session has not published yet is
-- added to the zeroed counter afterwards.  tc4_hazard below is the same
-- load with this line left out.
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t1_churn;

-- f2: fastupdate, the pending-list fixture
CREATE TABLE /* wiki_gin_fixture_build */ t2_pending (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_fixture_build */ t2_pending
SELECT i, ARRAY[i % 1000, (i * 7) % 1000, (i * 13) % 1000, i % 97]
FROM generate_series(1, (:rows * 3) / 4) i;
CREATE INDEX /* wiki_gin_fixture_build */ f2_pending_gin
    ON t2_pending USING gin (tags) WITH (fastupdate = on);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t2_pending;

-- f4: empty table
CREATE TABLE /* wiki_gin_fixture_build */ t4_empty (id int primary key, tags int[]);
CREATE INDEX /* wiki_gin_fixture_build */ f4_empty_gin
    ON t4_empty USING gin (tags) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t4_empty;

-- f5: every row carries all 32 keys, so each key gets a deep posting tree
CREATE TABLE /* wiki_gin_fixture_build */ t5_deleted (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_fixture_build */ t5_deleted
SELECT i, ARRAY(SELECT generate_series(0, 31)) FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_fixture_build */ f5_deleted_gin
    ON t5_deleted USING gin (tags) WITH (fastupdate = off);
CREATE INDEX /* wiki_gin_fixture_build */ f5_deleted_btree ON t5_deleted (id);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t5_deleted;

-- f6: same shape; every other row is deleted, so leaves go half empty with
-- nothing deletable left on them
CREATE TABLE /* wiki_gin_fixture_build */ t6_slack (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_fixture_build */ t6_slack
SELECT i, ARRAY(SELECT generate_series(0, 31)) FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_fixture_build */ f6_slack_gin
    ON t6_slack USING gin (tags) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t6_slack;

-- f7: churn that keeps the key population stable
CREATE TABLE /* wiki_gin_fixture_build */ t7_reupdate (id int primary key, doc text);
INSERT INTO /* wiki_gin_fixture_build */ t7_reupdate
SELECT i, 'w' || (i % 50021) || ' w' || ((i * 7) % 50021) || ' w' || ((i * 13) % 50021)
          || ' w' || ((i * 17) % 50021) || ' w' || ((i * 23) % 50021)
          || ' w' || ((i * 29) % 50021) || ' hot' || (i % 7) || ' tog0'
FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_fixture_build */ f7_reupdate_gin
    ON t7_reupdate USING gin (to_tsvector('simple', doc)) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t7_reupdate;

-- f11: jsonb_path_ops
CREATE TABLE /* wiki_gin_fixture_build */ t11_json (id int primary key, doc jsonb);
INSERT INTO /* wiki_gin_fixture_build */ t11_json
SELECT i, jsonb_build_object('k' || (i % 977), i % 101,
                            'k' || ((i * 7) % 977), (i * 3) % 101,
                            'tag', 'w' || (i % 50021))
FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_fixture_build */ f11_json_gin
    ON t11_json USING gin (doc jsonb_path_ops) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t11_json;

-- f12: pg_trgm
CREATE TABLE /* wiki_gin_fixture_build */ t12_trgm (id int primary key, txt text);
INSERT INTO /* wiki_gin_fixture_build */ t12_trgm
SELECT i, 'alpha' || (i % 50021) || ' bravo' || ((i * 7) % 50021)
FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_fixture_build */ f12_trgm_gin
    ON t12_trgm USING gin (txt gin_trgm_ops) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t12_trgm;

-- f13: btree_gin over int4
CREATE TABLE /* wiki_gin_fixture_build */ t13_btgin (id int primary key, n int);
INSERT INTO /* wiki_gin_fixture_build */ t13_btgin
SELECT i, i % 20011 FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_fixture_build */ f13_btgin_gin
    ON t13_btgin USING gin (n) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t13_btgin;

-- f14: multicolumn
CREATE TABLE /* wiki_gin_fixture_build */ t14_multi (id int primary key, tags int[], doc text);
INSERT INTO /* wiki_gin_fixture_build */ t14_multi
SELECT i, ARRAY[i % 1000, (i * 7) % 1000, (i * 13) % 1000],
       'w' || (i % 50021) || ' w' || ((i * 7) % 50021) || ' hot' || (i % 7)
FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_fixture_build */ f14_multi_gin
    ON t14_multi USING gin (tags, to_tsvector('simple', doc)) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t14_multi;

-- f15: partial
CREATE TABLE /* wiki_gin_fixture_build */ t15_partial (id int primary key, tags int[], live boolean);
INSERT INTO /* wiki_gin_fixture_build */ t15_partial
SELECT i, ARRAY[i % 1000, (i * 7) % 1000, (i * 13) % 1000, i % 97], (i % 10 = 0)
FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_fixture_build */ f15_partial_gin
    ON t15_partial USING gin (tags) WHERE live;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t15_partial;

-- g0 / g25 / g50 / g75 / g100: the churn sweep.  Keys are owned by groups of
-- four consecutive ids, so rewriting a contiguous id prefix kills exactly
-- that prefix's keys while every row is still updated.
CREATE TABLE /* wiki_gin_fixture_build */ s0   (id int primary key, doc text);
CREATE TABLE /* wiki_gin_fixture_build */ s25  (id int primary key, doc text);
CREATE TABLE /* wiki_gin_fixture_build */ s50  (id int primary key, doc text);
CREATE TABLE /* wiki_gin_fixture_build */ s75  (id int primary key, doc text);
CREATE TABLE /* wiki_gin_fixture_build */ s100 (id int primary key, doc text);
INSERT INTO /* wiki_gin_fixture_build */ s0
SELECT i, 'w' || (i/4) || ' x' || (i/4) || ' hot' || (i % 7) || ' tog0'
FROM generate_series(1, :rows) i;
INSERT INTO /* wiki_gin_fixture_build */ s25   SELECT * FROM s0;
INSERT INTO /* wiki_gin_fixture_build */ s50   SELECT * FROM s0;
INSERT INTO /* wiki_gin_fixture_build */ s75   SELECT * FROM s0;
INSERT INTO /* wiki_gin_fixture_build */ s100  SELECT * FROM s0;
CREATE INDEX /* wiki_gin_fixture_build */ g0_gin   ON s0   USING gin (to_tsvector('simple', doc)) WITH (fastupdate = off);
CREATE INDEX /* wiki_gin_fixture_build */ g25_gin  ON s25  USING gin (to_tsvector('simple', doc)) WITH (fastupdate = off);
CREATE INDEX /* wiki_gin_fixture_build */ g50_gin  ON s50  USING gin (to_tsvector('simple', doc)) WITH (fastupdate = off);
CREATE INDEX /* wiki_gin_fixture_build */ g75_gin  ON s75  USING gin (to_tsvector('simple', doc)) WITH (fastupdate = off);
CREATE INDEX /* wiki_gin_fixture_build */ g100_gin ON s100 USING gin (to_tsvector('simple', doc)) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE s0, s25, s50, s75, s100;

-- m1: the pair.  One fixture, censused after its writes, after its settle
-- step and after its maintenance step, so the maintenance step is measured
-- rather than assumed.
CREATE TABLE /* wiki_gin_fixture_build */ tm1_pair (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_fixture_build */ tm1_pair
SELECT i, ARRAY(SELECT generate_series(0, 31)) FROM generate_series(1, :rows / 2) i;
CREATE INDEX /* wiki_gin_fixture_build */ m1_pair_gin
    ON tm1_pair USING gin (tags) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE tm1_pair;
INSERT INTO wiki.phase_note (fixture, phase, note)
SELECT 'm1_pair', 'as-built catalog',
       'relpages=' || c.relpages || ' reltuples=' || c.reltuples
FROM pg_class c WHERE c.relname = 'm1_pair_gin';

-- a1: the auto-analyze stand-in.  Insert-only, so it stays under both vacuum
-- verdicts while crossing the analyze verdict, and fastupdate is on so the
-- inserts land in the pending list that only a worker's ANALYZE would flush.
CREATE TABLE /* wiki_gin_fixture_build */ ta1_analyze (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_fixture_build */ ta1_analyze
SELECT i, ARRAY[i % 1000, (i * 7) % 1000, (i * 13) % 1000, i % 97]
FROM generate_series(1, 20000) i;
CREATE INDEX /* wiki_gin_fixture_build */ a1_analyze_gin
    ON ta1_analyze USING gin (tags) WITH (fastupdate = on);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE ta1_analyze;

-- c1 / c2 / c3: the census tables.  Each is loaded, analyzed, then loaded
-- again, so the build phase leaves one past its analyze threshold, one below
-- it and one exactly on it.  No churn phase touches them.
CREATE TABLE /* wiki_gin_fixture_build */ tc1_analyzed (id int primary key, tags int[]);
CREATE TABLE /* wiki_gin_fixture_build */ tc2_declined (id int primary key, tags int[]);
CREATE TABLE /* wiki_gin_fixture_build */ tc3_boundary (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_fixture_build */ tc1_analyzed SELECT i, ARRAY[i % 97] FROM generate_series(1, 10000) i;
INSERT INTO /* wiki_gin_fixture_build */ tc2_declined SELECT i, ARRAY[i % 97] FROM generate_series(1, 10000) i;
INSERT INTO /* wiki_gin_fixture_build */ tc3_boundary SELECT i, ARRAY[i % 97] FROM generate_series(1, 10000) i;
CREATE INDEX /* wiki_gin_fixture_build */ c1_analyzed_gin ON tc1_analyzed USING gin (tags) WITH (fastupdate = off);
CREATE INDEX /* wiki_gin_fixture_build */ c2_declined_gin ON tc2_declined USING gin (tags) WITH (fastupdate = off);
CREATE INDEX /* wiki_gin_fixture_build */ c3_boundary_gin ON tc3_boundary USING gin (tags) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE tc1_analyzed, tc2_declined, tc3_boundary;
-- the second load, after the build-phase ANALYZE.  At the shipped defaults
-- the analyze threshold is 50 + 0.1 * reltuples = 1050 rows here.
INSERT INTO /* wiki_gin_fixture_build */ tc1_analyzed SELECT i, ARRAY[i % 97] FROM generate_series(10001, 12000) i;
INSERT INTO /* wiki_gin_fixture_build */ tc2_declined SELECT i, ARRAY[i % 97] FROM generate_series(10001, 10500) i;
INSERT INTO /* wiki_gin_fixture_build */ tc3_boundary SELECT i, ARRAY[i % 97] FROM generate_series(10001, 11050) i;

-- c4: the publication hazard on purpose.  Same two-step load as c2, and the
-- build-phase ANALYZE runs with the first load still unpublished, so the
-- counter the census reads afterwards is the whole load rather than the 500
-- rows written since the ANALYZE.
CREATE TABLE /* wiki_gin_fixture_build */ tc4_hazard (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_fixture_build */ tc4_hazard SELECT i, ARRAY[i % 97] FROM generate_series(1, 10000) i;
CREATE INDEX /* wiki_gin_fixture_build */ c4_hazard_gin ON tc4_hazard USING gin (tags) WITH (fastupdate = off);
VACUUM /* wiki_gin_fixture_build */ ANALYZE tc4_hazard;
INSERT INTO /* wiki_gin_fixture_build */ tc4_hazard SELECT i, ARRAY[i % 97] FROM generate_series(10001, 10500) i;

-- f8: the held-snapshot fixture, churned in the coverage stage
CREATE TABLE /* wiki_gin_fixture_build */ t8_horizon (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_fixture_build */ t8_horizon
SELECT i, ARRAY(SELECT generate_series(0, 31)) FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_fixture_build */ f8_horizon_gin
    ON t8_horizon USING gin (tags) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t8_horizon;

INSERT INTO wiki.fixture (fixture, idx, tbl, scored, settled, maintenance, note) VALUES
 ('f1_churn',   'f1_churn_gin',   't1_churn',   true,  true,  'VACUUM ANALYZE', 'tsvector, every term replaced'),
 ('f2_pending', 'f2_pending_gin', 't2_pending', true,  true,  'VACUUM ANALYZE', 'fastupdate, pending list filled then flushed'),
 ('f3_fresh',   'f3_fresh_gin',   't3_fresh',   true,  true,  'VACUUM ANALYZE', 'untouched twin of f1 post-churn content'),
 ('f4_empty',   'f4_empty_gin',   't4_empty',   true,  true,  'VACUUM ANALYZE', 'empty table'),
 ('f5_deleted', 'f5_deleted_gin', 't5_deleted', true,  true,  'VACUUM ANALYZE', '32 keys per row, first 95% of the heap deleted'),
 ('f6_slack',   'f6_slack_gin',   't6_slack',   true,  true,  'VACUUM ANALYZE', 'same shape, every other row deleted'),
 ('f7_reupdate','f7_reupdate_gin','t7_reupdate',true,  true,  'VACUUM ANALYZE', 'same terms rewritten three times'),
 ('f11_json',   'f11_json_gin',   't11_json',   true,  true,  'VACUUM ANALYZE', 'jsonb_path_ops'),
 ('f12_trgm',   'f12_trgm_gin',   't12_trgm',   true,  true,  'VACUUM ANALYZE', 'gin_trgm_ops'),
 ('f13_btgin',  'f13_btgin_gin',  't13_btgin',  true,  true,  'VACUUM ANALYZE', 'btree_gin int4'),
 ('f14_multi',  'f14_multi_gin',  't14_multi',  true,  true,  'VACUUM ANALYZE', 'multicolumn'),
 ('f15_partial','f15_partial_gin','t15_partial',true,  true,  'VACUUM ANALYZE', 'partial index'),
 ('g0',         'g0_gin',         's0',         true,  true,  'VACUUM ANALYZE', 'churn sweep, 0% of keys replaced'),
 ('g25',        'g25_gin',        's25',        true,  true,  'VACUUM ANALYZE', 'churn sweep, 25% of keys replaced'),
 ('g50',        'g50_gin',        's50',        true,  true,  'VACUUM ANALYZE', 'churn sweep, 50% of keys replaced'),
 ('g75',        'g75_gin',        's75',        true,  true,  'VACUUM ANALYZE', 'churn sweep, 75% of keys replaced'),
 ('g100',       'g100_gin',       's100',       true,  true,  'VACUUM ANALYZE', 'churn sweep, 100% of keys replaced'),
 ('m1_pair',    'm1_pair_gin',    'tm1_pair',   true,  true,  'VACUUM ANALYZE', 'censused after writes, after settle and after maintenance'),
 ('a1_analyze', 'a1_analyze_gin', 'ta1_analyze',true,  false, 'ANALYZE + gin_clean_pending_list()', 'auto-analyze stand-in: stale metapage counts by construction'),
 ('c1_analyzed','c1_analyzed_gin','tc1_analyzed',false,true,  'VACUUM ANALYZE (build phase)', 'census table: past its analyze threshold'),
 ('c2_declined','c2_declined_gin','tc2_declined',false,true,  'VACUUM ANALYZE (build phase)', 'census table: below its analyze threshold'),
 ('c3_boundary','c3_boundary_gin','tc3_boundary',false,true,  'VACUUM ANALYZE (build phase)', 'census table: exactly on its analyze threshold'),
 ('c4_hazard',  'c4_hazard_gin',  'tc4_hazard', false, true,  'VACUUM ANALYZE (build phase), unpublished', 'census table: the publication hazard on purpose'),
 ('f8_horizon', 'f8_horizon_gin', 't8_horizon', false, true,  'VACUUM ANALYZE', 'coverage: a snapshot held across the settling VACUUM');

SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
SQL

  cat >"$SQLD/20_churn.sql" <<'SQL'
-- The churn phase, in the order the protocol fixes: the recipe's writes, then
-- the settle step, then the maintenance step.  The census is the next stage.
SET /* wiki_gin_churn */ statement_timeout = '600s';
SET /* wiki_gin_churn */ lock_timeout = '2s';
SET /* wiki_gin_churn */ maintenance_work_mem = :'mwm';
SET /* wiki_gin_churn */ gin_pending_list_limit = '1GB';

-- f1 -------------------------------------------------------------------------
UPDATE /* wiki_gin_churn */ t1_churn SET doc =
       'v' || (id % 50021) || ' v' || ((id * 7) % 50021) || ' v' || ((id * 13) % 50021)
           || ' v' || ((id * 17) % 50021) || ' v' || ((id * 23) % 50021)
           || ' v' || ((id * 29) % 50021) || ' warm' || (id % 7);
VACUUM /* wiki_gin_settle */ t1_churn;
VACUUM /* wiki_gin_settle */ t1_churn;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) t1_churn;

-- f3: the untouched twin, built from f1's post-churn content, so its build
-- phase is here and its churn phase is empty
CREATE TABLE /* wiki_gin_fixture_build */ t3_fresh (id int primary key, doc text);
INSERT INTO /* wiki_gin_fixture_build */ t3_fresh SELECT id, doc FROM t1_churn;
CREATE INDEX /* wiki_gin_fixture_build */ f3_fresh_gin
    ON t3_fresh USING gin (to_tsvector('simple', doc)) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_fixture_build */ ANALYZE t3_fresh;

-- f2 -------------------------------------------------------------------------
INSERT INTO /* wiki_gin_churn */ t2_pending
SELECT i, ARRAY[i % 1000, (i * 7) % 1000, (i * 13) % 1000, i % 97]
FROM generate_series((:rows * 3) / 4 + 1, :rows) i;
\set run churn_f2_pending_live
\i :ci
SELECT /* wiki_gin_churn */ gin_clean_pending_list('f2_pending_gin') AS f2_pages_flushed;
\set run churn_f2_after_flush
\i :ci
VACUUM /* wiki_gin_settle */ t2_pending;
VACUUM /* wiki_gin_settle */ t2_pending;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) t2_pending;

-- f5: the three-VACUUM sequence.  A page deleted by the first VACUUM carries a
-- delete xid the cluster has not passed yet, so it counts as a data page until
-- the horizon moves.
DELETE FROM /* wiki_gin_churn */ t5_deleted WHERE id <= (:rows * 95) / 100;
VACUUM /* wiki_gin_settle */ (VERBOSE) t5_deleted;
SELECT /* wiki_gin_churn */ pg_current_xact_id();
SELECT /* wiki_gin_churn */ pg_current_xact_id();
SELECT /* wiki_gin_churn */ pg_current_xact_id();
VACUUM /* wiki_gin_settle */ (VERBOSE) t5_deleted;
VACUUM /* wiki_gin_settle */ (VERBOSE) t5_deleted;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) t5_deleted;

-- f6 -------------------------------------------------------------------------
DELETE FROM /* wiki_gin_churn */ t6_slack WHERE id % 2 = 0;
VACUUM /* wiki_gin_settle */ t6_slack;
VACUUM /* wiki_gin_settle */ t6_slack;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) t6_slack;

-- f7 -------------------------------------------------------------------------
UPDATE /* wiki_gin_churn */ t7_reupdate SET doc = replace(doc, 'tog0', 'tog1');
VACUUM /* wiki_gin_settle */ t7_reupdate;
UPDATE /* wiki_gin_churn */ t7_reupdate SET doc = replace(doc, 'tog1', 'tog0');
VACUUM /* wiki_gin_settle */ t7_reupdate;
UPDATE /* wiki_gin_churn */ t7_reupdate SET doc = replace(doc, 'tog0', 'tog1');
VACUUM /* wiki_gin_settle */ t7_reupdate;
VACUUM /* wiki_gin_settle */ t7_reupdate;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) t7_reupdate;

-- f11 through f15: every key replaced, and for f15 the predicate column too
UPDATE /* wiki_gin_churn */ t11_json SET doc =
       jsonb_build_object('z' || (id % 977), id % 101,
                          'z' || ((id * 7) % 977), (id * 3) % 101,
                          'tag', 'v' || (id % 50021));
VACUUM /* wiki_gin_settle */ t11_json;
VACUUM /* wiki_gin_settle */ t11_json;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) t11_json;

UPDATE /* wiki_gin_churn */ t12_trgm SET txt =
       'delta' || (id % 50021) || ' echo' || ((id * 7) % 50021);
VACUUM /* wiki_gin_settle */ t12_trgm;
VACUUM /* wiki_gin_settle */ t12_trgm;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) t12_trgm;

UPDATE /* wiki_gin_churn */ t13_btgin SET n = 20011 + (id % 20011);
VACUUM /* wiki_gin_settle */ t13_btgin;
VACUUM /* wiki_gin_settle */ t13_btgin;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) t13_btgin;

UPDATE /* wiki_gin_churn */ t14_multi SET
       tags = ARRAY[1000 + id % 1000, 1000 + (id * 7) % 1000, 1000 + (id * 13) % 1000],
       doc  = 'v' || (id % 50021) || ' v' || ((id * 7) % 50021) || ' warm' || (id % 7);
VACUUM /* wiki_gin_settle */ t14_multi;
VACUUM /* wiki_gin_settle */ t14_multi;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) t14_multi;

UPDATE /* wiki_gin_churn */ t15_partial SET
       tags = ARRAY[1000 + id % 1000, 1000 + (id * 7) % 1000,
                    1000 + (id * 13) % 1000, 1000 + id % 97],
       live = (id % 10 = 1);
VACUUM /* wiki_gin_settle */ t15_partial;
VACUUM /* wiki_gin_settle */ t15_partial;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) t15_partial;

-- the churn sweep: p% of the key population replaced, 100% of rows updated
UPDATE /* wiki_gin_churn */ s0 SET doc = 'v'||(id/4)||' y'||(id/4)||' warm'||(id%7)||' tog1' WHERE id <= 0;
UPDATE /* wiki_gin_churn */ s0 SET doc = 'w'||(id/4)||' x'||(id/4)||' hot' ||(id%7)||' tog1' WHERE id >  0;
UPDATE /* wiki_gin_churn */ s25 SET doc = 'v'||(id/4)||' y'||(id/4)||' warm'||(id%7)||' tog1' WHERE id <= (:rows * 25) / 100;
UPDATE /* wiki_gin_churn */ s25 SET doc = 'w'||(id/4)||' x'||(id/4)||' hot' ||(id%7)||' tog1' WHERE id >  (:rows * 25) / 100;
UPDATE /* wiki_gin_churn */ s50 SET doc = 'v'||(id/4)||' y'||(id/4)||' warm'||(id%7)||' tog1' WHERE id <= (:rows * 50) / 100;
UPDATE /* wiki_gin_churn */ s50 SET doc = 'w'||(id/4)||' x'||(id/4)||' hot' ||(id%7)||' tog1' WHERE id >  (:rows * 50) / 100;
UPDATE /* wiki_gin_churn */ s75 SET doc = 'v'||(id/4)||' y'||(id/4)||' warm'||(id%7)||' tog1' WHERE id <= (:rows * 75) / 100;
UPDATE /* wiki_gin_churn */ s75 SET doc = 'w'||(id/4)||' x'||(id/4)||' hot' ||(id%7)||' tog1' WHERE id >  (:rows * 75) / 100;
UPDATE /* wiki_gin_churn */ s100 SET doc = 'v'||(id/4)||' y'||(id/4)||' warm'||(id%7)||' tog1' WHERE id <= :rows;
UPDATE /* wiki_gin_churn */ s100 SET doc = 'w'||(id/4)||' x'||(id/4)||' hot' ||(id%7)||' tog1' WHERE id >  :rows;
VACUUM /* wiki_gin_settle */ s0, s25, s50, s75, s100;
VACUUM /* wiki_gin_settle */ s0, s25, s50, s75, s100;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) s0, s25, s50, s75, s100;

-- m1: the three readings around the settle and maintenance steps
DELETE FROM /* wiki_gin_churn */ tm1_pair WHERE id % 2 = 0;
\set run churn_m1_after_writes
\i :ci
VACUUM /* wiki_gin_settle */ tm1_pair;
VACUUM /* wiki_gin_settle */ tm1_pair;
\set run churn_m1_after_settle
\i :ci
INSERT INTO wiki.phase_note (fixture, phase, note)
SELECT 'm1_pair', 'pre-maintenance catalog',
       'relpages=' || c.relpages || ' reltuples=' || c.reltuples
FROM pg_class c WHERE c.relname = 'm1_pair_gin';
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) tm1_pair;
\set run churn_m1_after_maintenance
\i :ci
INSERT INTO wiki.phase_note (fixture, phase, note)
SELECT 'm1_pair', 'post-maintenance catalog',
       'relpages=' || c.relpages || ' reltuples=' || c.reltuples
FROM pg_class c WHERE c.relname = 'm1_pair_gin';

-- a1: the auto-analyze stand-in.  Insert-only churn, then ANALYZE plus the
-- flush that only an autovacuum worker's own ANALYZE would have performed.
INSERT INTO /* wiki_gin_churn */ ta1_analyze
SELECT i, ARRAY[i % 1000, (i * 7) % 1000, (i * 13) % 1000, i % 97]
FROM generate_series(20001, 24999) i;
\set run churn_a1_before_standin
\i :ci
INSERT INTO wiki.phase_note (fixture, phase, note)
SELECT 'a1_analyze', 'pre-standin metapage',
       'version=' || m.version || ' pending_pages=' || m.n_pending_pages
       || ' pending_tuples=' || m.n_pending_tuples || ' total=' || m.n_total_pages
       || ' entry=' || m.n_entry_pages || ' data=' || m.n_data_pages
FROM gin_metapage_info(get_raw_page('a1_analyze_gin', 0)) m;
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
-- the launcher's three verdicts for this fixture, recorded at the moment the
-- stand-in replaces them, from the effective values and nothing else
INSERT INTO wiki.phase_note (fixture, phase, note)
SELECT 'a1_analyze', 'pre-standin counters and verdicts',
       'reltuples=' || c.reltuples
       || ' mod_since_analyze=' || s.n_mod_since_analyze
       || ' dead=' || s.n_dead_tup
       || ' ins_since_vacuum=' || s.n_ins_since_vacuum
       || ' anl_thresh=' || (current_setting('autovacuum_analyze_threshold')::float8
              + current_setting('autovacuum_analyze_scale_factor')::float8 * greatest(c.reltuples, 0))
       || ' vac_thresh=' || (current_setting('autovacuum_vacuum_threshold')::float8
              + current_setting('autovacuum_vacuum_scale_factor')::float8 * greatest(c.reltuples, 0))
       || ' ins_thresh=' || (current_setting('autovacuum_vacuum_insert_threshold')::float8
              + current_setting('autovacuum_vacuum_insert_scale_factor')::float8 * greatest(c.reltuples, 0))
FROM pg_class c JOIN pg_stat_all_tables s ON s.relid = c.oid
WHERE c.relname = 'ta1_analyze';
INSERT INTO wiki.phase_note (fixture, phase, note)
SELECT 'a1_analyze', 'pre-standin index catalog',
       'relpages=' || c.relpages || ' reltuples=' || c.reltuples
       || ' live_blocks=' || (pg_relation_size('a1_analyze_gin', 'main')
                              / current_setting('block_size')::bigint)
FROM pg_class c WHERE c.relname = 'a1_analyze_gin';
ANALYZE /* wiki_gin_maintenance */ ta1_analyze;
INSERT INTO wiki.phase_note (fixture, phase, note)
SELECT 'a1_analyze', 'post-ANALYZE index catalog',
       'relpages=' || c.relpages || ' reltuples=' || c.reltuples
       || ' live_blocks=' || (pg_relation_size('a1_analyze_gin', 'main')
                              / current_setting('block_size')::bigint)
FROM pg_class c WHERE c.relname = 'a1_analyze_gin';
SELECT /* wiki_gin_maintenance */ gin_clean_pending_list('a1_analyze_gin') AS a1_pages_flushed;
\set run churn_a1_after_standin
\i :ci
INSERT INTO wiki.phase_note (fixture, phase, note)
SELECT 'a1_analyze', 'post-standin metapage',
       'version=' || m.version || ' pending_pages=' || m.n_pending_pages
       || ' pending_tuples=' || m.n_pending_tuples || ' total=' || m.n_total_pages
       || ' entry=' || m.n_entry_pages || ' data=' || m.n_data_pages
FROM gin_metapage_info(get_raw_page('a1_analyze_gin', 0)) m;

SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
SQL
}

stage_fixtures() {
  write_sql_files
  note "build phase"
  p "$DB" -q -v rows="$ROWS" -v mwm="$MWM" -f "$SQLD/10_build.sql" \
    || die "build phase failed"
  note "baseline census"
  p "$DB" -q -v run=baseline -f "$SQLD/census_insert.sql" || die "baseline census failed"
  note "churn phase: writes, settle, maintenance"
  p "$DB" -v rows="$ROWS" -v mwm="$MWM" -v ci="$SQLD/census_insert.sql" \
    -f "$SQLD/20_churn.sql" >"$OUT/churn.txt" 2>&1 || { tail -20 "$OUT/churn.txt"; die "churn phase failed"; }
  note "late baseline census, for the fixtures built during the churn stage"
  p "$DB" -q -v run=baseline_late -f "$SQLD/census_insert.sql" || die "late baseline failed"
  # every census the build and churn phases stored, and every phase note, so
  # the before-and-after readings are in a file and not only in tables the
  # clean stage deletes
  p "$DB" -c "SELECT /* wiki_gin_phases */ run, index_name, status, main_fork_bytes, blocks,
                     entry_pages, pending_pages, deleted_pages, whole_page_waste_bytes,
                     pending_pct, bloat_pct, entry_slack, data_slack,
                     meta_pending_pages, meta_entry_pages, meta_total_pages
              FROM wiki.census_run
              WHERE run IN ('baseline', 'baseline_late') OR run LIKE 'churn_%'
              ORDER BY index_name, taken_at" >"$OUT/20-phases.txt" || die "phase report failed"
  p "$DB" -c "SELECT /* wiki_gin_phases */ fixture, phase, note FROM wiki.phase_note
              WHERE fixture <> '*' ORDER BY ran_at" >>"$OUT/20-phases.txt" || die "phase notes failed"
  grep -E 'index "f5_deleted|index "m1_pair|pages_flushed|^ *[0-9]+$' "$OUT/churn.txt" \
    > "$OUT/churn_lines.txt"
  p "$DB" -c "SELECT /* wiki_gin_fixtures */ fixture, idx, scored, settled, maintenance
              FROM wiki.fixture ORDER BY fixture" | tee "$OUT/01-fixtures.txt"
  # the declare-then-score order, from the two stored timestamps
  p "$DB" -c "SELECT /* wiki_gin_fixtures */
                     (SELECT to_char(max(declared_at), 'YYYY-MM-DD HH24:MI:SS.MS') FROM wiki.declaration)
                       AS declarations_filed,
                     (SELECT to_char(min(taken_at), 'YYYY-MM-DD HH24:MI:SS.MS') FROM wiki.census_run
                       WHERE run = 'baseline') AS first_fixture_census" | tee -a "$OUT/01-fixtures.txt"
}

# ------------------------------------------------------- the simulated census
#
# Recomputes relation_needs_vacanalyze's analyze verdict for every table the
# launcher would have walked, from the effective reloption-or-GUC values, and
# analyzes the tables it names.  The vacuum and insert-vacuum verdicts are
# recorded beside it and never applied.
write_census_sql() {
  mkdir -p "$SQLD"
  cat >"$SQLD/census_anl.sql" <<'SQL'
CREATE TABLE :tbl AS
WITH /* wiki_gin_autoanalyze_census */ guc AS (
    SELECT current_setting('autovacuum_analyze_threshold')::float8            AS g_anl_thresh,
           current_setting('autovacuum_analyze_scale_factor')::float8         AS g_anl_scale,
           current_setting('autovacuum_vacuum_threshold')::float8             AS g_vac_thresh,
           current_setting('autovacuum_vacuum_scale_factor')::float8          AS g_vac_scale,
           current_setting('autovacuum_vacuum_insert_threshold')::float8      AS g_ins_thresh,
           current_setting('autovacuum_vacuum_insert_scale_factor')::float8   AS g_ins_scale
),
rel AS (
    -- do_autovacuum walks plain tables and materialized views; toast
    -- relations are a separate scan whose analyze verdict is forced false,
    -- and ANALYZE refuses to work with pg_statistic.
    SELECT c.oid, c.oid::regclass::text AS relation, c.reltuples,
           (SELECT split_part(o, '=', 2) FROM unnest(coalesce(c.reloptions, '{}'::text[])) o
             WHERE split_part(o, '=', 1) = 'autovacuum_analyze_threshold')       AS o_anl_thresh,
           (SELECT split_part(o, '=', 2) FROM unnest(coalesce(c.reloptions, '{}'::text[])) o
             WHERE split_part(o, '=', 1) = 'autovacuum_analyze_scale_factor')    AS o_anl_scale,
           (SELECT split_part(o, '=', 2) FROM unnest(coalesce(c.reloptions, '{}'::text[])) o
             WHERE split_part(o, '=', 1) = 'autovacuum_vacuum_threshold')        AS o_vac_thresh,
           (SELECT split_part(o, '=', 2) FROM unnest(coalesce(c.reloptions, '{}'::text[])) o
             WHERE split_part(o, '=', 1) = 'autovacuum_vacuum_scale_factor')     AS o_vac_scale,
           (SELECT split_part(o, '=', 2) FROM unnest(coalesce(c.reloptions, '{}'::text[])) o
             WHERE split_part(o, '=', 1) = 'autovacuum_vacuum_insert_threshold') AS o_ins_thresh,
           (SELECT split_part(o, '=', 2) FROM unnest(coalesce(c.reloptions, '{}'::text[])) o
             WHERE split_part(o, '=', 1) = 'autovacuum_vacuum_insert_scale_factor') AS o_ins_scale,
           (SELECT split_part(o, '=', 2) FROM unnest(coalesce(c.reloptions, '{}'::text[])) o
             WHERE split_part(o, '=', 1) = 'autovacuum_enabled')                 AS o_enabled
    FROM pg_class c
    WHERE c.relkind IN ('r', 'm')
      AND c.oid <> 'pg_statistic'::regclass
),
eff AS (
    SELECT r.oid, r.relation, r.reltuples AS reltuples_raw,
           GREATEST(r.reltuples, 0)::float8 AS reltuples_used,
           coalesce(r.o_enabled, 'true') = 'true' AS av_enabled,
           CASE WHEN r.o_anl_thresh IS NOT NULL AND r.o_anl_thresh::float8 >= 0
                THEN r.o_anl_thresh::float8 ELSE k.g_anl_thresh END AS anl_base,
           CASE WHEN r.o_anl_scale IS NOT NULL AND r.o_anl_scale::float8 >= 0
                THEN r.o_anl_scale::float8 ELSE k.g_anl_scale END   AS anl_scale,
           CASE WHEN r.o_vac_thresh IS NOT NULL AND r.o_vac_thresh::float8 >= 0
                THEN r.o_vac_thresh::float8 ELSE k.g_vac_thresh END AS vac_base,
           CASE WHEN r.o_vac_scale IS NOT NULL AND r.o_vac_scale::float8 >= 0
                THEN r.o_vac_scale::float8 ELSE k.g_vac_scale END   AS vac_scale,
           CASE WHEN r.o_ins_thresh IS NOT NULL AND r.o_ins_thresh::float8 >= -1
                THEN r.o_ins_thresh::float8 ELSE k.g_ins_thresh END AS ins_base,
           CASE WHEN r.o_ins_scale IS NOT NULL AND r.o_ins_scale::float8 >= 0
                THEN r.o_ins_scale::float8 ELSE k.g_ins_scale END   AS ins_scale,
           coalesce(s.n_mod_since_analyze, 0)::float8 AS mod_since_analyze,
           coalesce(s.n_dead_tup, 0)::float8          AS dead_tuples,
           coalesce(s.n_ins_since_vacuum, 0)::float8  AS ins_since_vacuum
    FROM rel r CROSS JOIN guc k
         LEFT JOIN pg_stat_all_tables s ON s.relid = r.oid
)
SELECT relation, reltuples_raw, reltuples_used, av_enabled,
       mod_since_analyze, dead_tuples, ins_since_vacuum,
       anl_base, anl_scale, anl_base + anl_scale * reltuples_used AS anl_thresh,
       vac_base + vac_scale * reltuples_used                      AS vac_thresh,
       CASE WHEN ins_base < 0 THEN NULL
            ELSE ins_base + ins_scale * reltuples_used END         AS ins_thresh,
       -- applied
       (av_enabled AND mod_since_analyze > anl_base + anl_scale * reltuples_used) AS doanalyze,
       -- recorded, never applied
       (av_enabled AND dead_tuples > vac_base + vac_scale * reltuples_used)       AS dovacuum_recorded,
       (av_enabled AND ins_base >= 0
                   AND ins_since_vacuum > ins_base + ins_scale * reltuples_used)  AS doinsvacuum_recorded
FROM eff
ORDER BY relation;
SQL
}

stage_census() {
  write_census_sql
  p "$DB" -q -c "DROP TABLE IF EXISTS wiki.anl_census, wiki.anl_census_after" || die
  # PGC_USERSET, session scope: a snapshot makes two reads of one counter
  # comparable, and pg_stat_clear_snapshot() is what discards it between them.
  p "$DB" -q -v tbl=wiki.anl_census <<SQL || die "census read failed"
SET /* wiki_gin_census_guards */ statement_timeout = '$STMT_TIMEOUT';
SET /* wiki_gin_census_guards */ lock_timeout = '$LOCK_TIMEOUT';
SET /* wiki_gin_census */ stats_fetch_consistency = 'snapshot';
SELECT /* wiki_gin_census */ pg_stat_clear_snapshot();
\i $SQLD/census_anl.sql
SQL
  note "census verdicts: $(q "$DB" "SELECT count(*) FILTER (WHERE doanalyze) || ' of ' || count(*) FROM wiki.anl_census")"
  p "$DB" -q -c "DO \$c\$
DECLARE r record;
BEGIN
  FOR r IN SELECT relation FROM wiki.anl_census WHERE doanalyze ORDER BY relation LOOP
    EXECUTE format('ANALYZE /* wiki_gin_census_analyze */ %s', r.relation);
  END LOOP;
END \$c\$;" || die "census analyze failed"
  # publish first, analyze second, then re-read
  p "$DB" -q -v tbl=wiki.anl_census_after <<SQL || die "census recheck failed"
SET /* wiki_gin_census */ stats_fetch_consistency = 'snapshot';
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
SELECT /* wiki_gin_census */ pg_stat_clear_snapshot();
\i $SQLD/census_anl.sql
SQL
  p "$DB" -c "SELECT /* wiki_gin_census_report */ c.relation, c.reltuples_used, c.mod_since_analyze,
                     c.anl_thresh, c.doanalyze, a.mod_since_analyze AS mod_after, a.doanalyze AS doanalyze_after,
                     c.dovacuum_recorded, c.doinsvacuum_recorded
              FROM wiki.anl_census c JOIN wiki.anl_census_after a USING (relation)
              WHERE c.doanalyze OR a.doanalyze OR c.dovacuum_recorded OR c.doinsvacuum_recorded
                 OR c.relation LIKE 'tc%' OR c.relation LIKE 'ta1%'
              ORDER BY c.relation" | tee "$OUT/02-census.txt"
  p "$DB" -c "SELECT /* wiki_gin_census_report */ count(*) AS tables_walked,
                     count(*) FILTER (WHERE doanalyze) AS analyzed_by_census,
                     count(*) FILTER (WHERE dovacuum_recorded) AS vacuum_verdicts_recorded,
                     count(*) FILTER (WHERE doinsvacuum_recorded) AS insert_verdicts_recorded
              FROM wiki.anl_census" | tee -a "$OUT/02-census.txt"
  p "$DB" -c "SELECT /* wiki_gin_census_report */ a.relation, a.mod_since_analyze, a.anl_thresh, a.doanalyze
              FROM wiki.anl_census_after a WHERE a.doanalyze ORDER BY 1" | tee -a "$OUT/02-census.txt"
}

# ------------------------------------------------------------- decide + oracle

stage_decide() {
  write_sql_files
  p "$DB" -q -c "DELETE FROM wiki.census_run WHERE run = 'decide'" || die
  p "$DB" -v ci="$SQLD/census_insert.sql" <<SQL >"$OUT/decide.txt" 2>&1 || { cat "$OUT/decide.txt"; die "decide failed"; }
\set run decide
BEGIN;
SET LOCAL /* wiki_gin_waste_protocol */ statement_timeout = '$STMT_TIMEOUT';
SET LOCAL /* wiki_gin_waste_protocol */ lock_timeout = '$LOCK_TIMEOUT';
INSERT INTO wiki.phase_note (fixture, phase, note)
     VALUES ('*', 'decide lock taken', clock_timestamp()::text);
DO \$l\$
DECLARE r record;
BEGIN
  FOR r IN SELECT DISTINCT quote_ident(n.nspname) || '.' || quote_ident(c.relname) AS t
           FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE c.relkind = 'r' AND n.nspname = 'public' ORDER BY 1 LOOP
    EXECUTE format('LOCK /* wiki_gin_waste_protocol */ TABLE %s IN SHARE ROW EXCLUSIVE MODE', r.t);
  END LOOP;
END \$l\$;
\i :ci
INSERT INTO wiki.phase_note (fixture, phase, note)
     VALUES ('*', 'decide lock released', clock_timestamp()::text);
COMMIT;
SQL
  p "$DB" -c "SELECT /* wiki_gin_decide */ index_name, status, gin_version, main_fork_bytes, blocks,
                     entry_pages, data_leaf_pages, data_internal_pages, pending_pages,
                     deleted_pages, new_pages, invalid_pages, unknown_pages,
                     census_total_pages, blocks_after_census
              FROM wiki.census_run WHERE run = 'decide' ORDER BY index_name" \
    | tee "$OUT/03-decide-pages.txt"
  p "$DB" -c "SELECT /* wiki_gin_decide */ index_name, whole_page_waste_pct, live_page_slack_pct,
                     bloat_pct, entry_slack, data_slack, pending_bytes, pending_pct, payload_bytes
              FROM wiki.census_run WHERE run = 'decide' ORDER BY index_name" \
    | tee "$OUT/04-decide-bytes.txt"
  p "$DB" -c "SELECT /* wiki_gin_decide */ note FROM wiki.phase_note
              WHERE phase LIKE 'decide lock%' ORDER BY ran_at" | tee -a "$OUT/03-decide-pages.txt"
}

stage_oracle() {
  write_sql_files
  p "$DB" -q -c "DELETE FROM wiki.oracle WHERE mwm = '$MWM'" || die
  local fx idx b a t0 t1 ms
  while IFS='|' read -r fx idx; do
    [ -z "$fx" ] && continue
    b=$(q "$DB" "SELECT pg_relation_size('$idx', 'main')")
    t0=$(date +%s%N)
    q "$DB" "REINDEX /* wiki_gin_oracle */ INDEX $idx" >/dev/null || die "REINDEX $idx failed"
    t1=$(date +%s%N)
    a=$(q "$DB" "SELECT pg_relation_size('$idx', 'main')")
    ms=$(( (t1 - t0) / 1000000 ))
    q "$DB" "INSERT INTO wiki.oracle (fixture, idx, mwm, bytes_before, bytes_after, truth_pct, elapsed_ms)
             VALUES ('$fx', '$idx', '$MWM', $b, $a, round(100.0 * ($b - $a) / nullif($b, 0), 2), $ms)" >/dev/null
    note "oracle $fx: $b -> $a bytes in ${ms}ms"
  done < <(q "$DB" "SELECT fixture || '|' || idx FROM wiki.fixture WHERE scored ORDER BY fixture")
  note "post-rebuild census"
  p "$DB" -q -c "DELETE FROM wiki.census_run WHERE run = 'rebuilt'" || die
  p "$DB" -q -v run=rebuilt -f "$SQLD/census_insert.sql" || die "rebuilt census failed"
  p "$DB" -c "SELECT /* wiki_gin_oracle */ fixture, bytes_before, bytes_after, truth_pct, elapsed_ms
              FROM wiki.oracle WHERE mwm = '$MWM' ORDER BY fixture" | tee "$OUT/05-oracle.txt"
  p "$DB" -c "SELECT /* wiki_gin_oracle */ index_name, status, main_fork_bytes, blocks, entry_pages,
                     data_leaf_pages, data_internal_pages, pending_pages, deleted_pages,
                     entry_slack, data_slack, bloat_pct
              FROM wiki.census_run WHERE run = 'rebuilt' ORDER BY index_name" | tee -a "$OUT/05-oracle.txt"
}

stage_score() {
  p "$DB" -q -c "DROP TABLE IF EXISTS wiki.score" || die
  p "$DB" -q <<'SQL' || die "score failed"
CREATE TABLE wiki.score AS
SELECT f.fixture,
       d.index_name,
       o.bytes_before, o.bytes_after, o.truth_pct,
       d.whole_page_waste_pct, d.bloat_pct, d.live_page_slack_pct, d.pending_pct,
       d.main_fork_bytes AS decide_bytes,
       (d.main_fork_bytes = o.bytes_before)                       AS bracket_ok,
       CASE WHEN d.whole_page_waste_pct IS NULL THEN 'WITHHELD'
            WHEN d.whole_page_waste_pct <= o.truth_pct THEN 'HELD'
            ELSE 'VIOLATED' END                                   AS lower_bound,
       CASE WHEN d.bloat_pct IS NULL THEN 'WITHHELD'
            WHEN d.bloat_pct >= o.truth_pct THEN 'HELD'
            ELSE 'VIOLATED' END                                   AS upper_bound,
       d.payload_bytes,
       r.main_fork_bytes                                          AS rebuilt_bytes,
       r.bloat_pct                                                AS rebuilt_bloat_pct,
       CASE WHEN r.payload_bytes > 0 AND r.main_fork_bytes > 0
            THEN round(d.payload_bytes
                       / (r.payload_bytes::numeric / r.main_fork_bytes), 0) END AS payload_fill_pred,
       CASE WHEN r.payload_bytes > 0 AND r.main_fork_bytes > 0 AND o.bytes_after > 0
            THEN round(100.0 * (d.payload_bytes
                       / (r.payload_bytes::numeric / r.main_fork_bytes) - o.bytes_after)
                       / o.bytes_after, 2) END                    AS payload_fill_err_pct
FROM wiki.fixture f
     JOIN wiki.oracle o ON o.fixture = f.fixture
     JOIN wiki.census_run d ON d.run = 'decide'   AND d.index_name = f.idx
     JOIN wiki.census_run r ON r.run = 'rebuilt'  AND r.index_name = f.idx
WHERE f.scored
ORDER BY f.fixture;
SQL
  p "$DB" -c "SELECT /* wiki_gin_score */ fixture, whole_page_waste_pct AS waste_pct, bloat_pct,
                     truth_pct, lower_bound, upper_bound, bracket_ok
              FROM wiki.score ORDER BY fixture" | tee "$OUT/06-score.txt"
  p "$DB" -c "SELECT /* wiki_gin_score */ count(*) AS scored,
                     count(*) FILTER (WHERE lower_bound = 'HELD')     AS lower_held,
                     count(*) FILTER (WHERE lower_bound = 'VIOLATED') AS lower_violated,
                     count(*) FILTER (WHERE upper_bound = 'HELD')     AS upper_held,
                     count(*) FILTER (WHERE upper_bound = 'VIOLATED') AS upper_violated,
                     count(*) FILTER (WHERE NOT bracket_ok)           AS bracket_failures
              FROM wiki.score" | tee -a "$OUT/06-score.txt"
  p "$DB" -c "SELECT /* wiki_gin_score */ fixture, decide_bytes, rebuilt_bytes, rebuilt_bloat_pct,
                     payload_bytes, payload_fill_pred, payload_fill_err_pct
              FROM wiki.score ORDER BY fixture" | tee "$OUT/07-payload-model.txt"
}

# ------------------------------------------------------------- cross-checks

# The scored statement with one filter line added, for a database that holds a
# page no multi-index report can survive.
# The pattern and the replacement are expanded from variables, quoted: an
# unquoted single quote inside a ${var/pat/repl} replacement is a quoting
# character, so a literal '$1' there would neither quote nor expand.
census_one_sql() {   # census_one_sql <index> -> the one-index text
  local anchor="AND c.relpersistence <> 't'"
  local repl="$anchor AND c.oid = '$1'::regclass"
  printf '%s' "${CENSUS/"$anchor"/"$repl"}"
}
census_one() {   # census_one <db> <index>
  pe "$1" -c "$(census_one_sql "$2")"
}

bootstrap_wiki_db() {   # bootstrap_wiki_db <db>
  p "$1" -q -c "DROP SCHEMA IF EXISTS wiki CASCADE; CREATE SCHEMA wiki;" || die
  p "$1" -q -c "CREATE TABLE wiki.census_run AS
                SELECT ''::text AS run, clock_timestamp() AS taken_at, q.*
                FROM ( $CENSUS ) q WITH NO DATA;" || die "census_run shape failed on $1"
}

stage_crosscheck() {
  p "$DB" -q -c "DELETE FROM wiki.fsm_check" || die
  local fx idx
  while IFS='|' read -r fx idx; do
    [ -z "$fx" ] && continue
    q "$DB" "INSERT INTO wiki.fsm_check
             SELECT '$fx', '$idx',
                    (SELECT database_block_size
                            - ((28 + max_data_alignment - 1) / max_data_alignment)
                              * max_data_alignment          -- 28 = SizeOfPageHeaderData + sizeof(ItemIdData)
                     FROM pg_control_init()),
                    count(*) FILTER (WHERE avail = (SELECT database_block_size
                            - ((28 + max_data_alignment - 1) / max_data_alignment)
                              * max_data_alignment FROM pg_control_init())),
                    count(*)
             FROM pg_freespace('$idx')" >/dev/null || die "FSM check failed for $idx"
  done < <(q "$DB" "SELECT fixture || '|' || idx FROM wiki.fixture ORDER BY fixture")
  p "$DB" -c "SELECT /* wiki_gin_waste_fsm_check */ f.fixture, f.free_page_avail, f.fsm_free_pages,
                     f.fsm_blocks, c.deleted_pages, c.new_pages,
                     (f.fsm_free_pages <= c.deleted_pages + c.new_pages) AS fsm_within_census
              FROM wiki.fsm_check f
                   JOIN wiki.census_run c ON c.run = 'decide' AND c.index_name = f.idx
              ORDER BY f.fixture" | tee "$OUT/08-crosscheck-fsm.txt"
  # metapage page-type counts against the SQL census of live pages
  p "$DB" -c "SELECT /* wiki_gin_meta_check */ index_name,
                     meta_entry_pages, entry_pages,
                     meta_data_pages, data_leaf_pages + data_internal_pages + uncompressed_pages AS census_data_pages,
                     deleted_pages, meta_total_pages, blocks,
                     (meta_entry_pages = entry_pages) AS entry_agrees,
                     (meta_data_pages = data_leaf_pages + data_internal_pages + uncompressed_pages) AS data_agrees,
                     (meta_data_pages = data_leaf_pages + data_internal_pages + uncompressed_pages + deleted_pages) AS data_agrees_with_deleted
              FROM wiki.census_run WHERE run = 'decide' ORDER BY index_name" \
    | tee "$OUT/09-crosscheck-metapage.txt"
  # the identity the two caveats add up to: ginvacuumcleanup counts a deleted
  # page as a data page unless it was recyclable, in which case it recorded it
  # free instead
  p "$DB" -c "SELECT /* wiki_gin_meta_identity */ c.index_name,
                     c.meta_data_pages,
                     c.data_leaf_pages + c.data_internal_pages + c.uncompressed_pages
                       + c.deleted_pages - f.fsm_free_pages AS live_plus_unrecyclable,
                     (c.meta_data_pages = c.data_leaf_pages + c.data_internal_pages
                        + c.uncompressed_pages + c.deleted_pages - f.fsm_free_pages) AS identity_holds
              FROM wiki.census_run c JOIN wiki.fsm_check f ON f.idx = c.index_name
              WHERE c.run = 'decide' ORDER BY 1" | tee -a "$OUT/09-crosscheck-metapage.txt"
  # the VACUUM VERBOSE index lines of the maintenance step, which is the last
  # VACUUM before the decide census
  grep -F 'index "' "$OUT/churn.txt" > "$OUT/10-crosscheck-verbose.txt"
  cat "$OUT/10-crosscheck-verbose.txt"
}

# The entry-tuple probe's text, written once and used by both probe stages:
# "probe" fills wiki.probe before the rebuild, "probe_after" fills
# wiki.probe_after after it.  :tbl is the destination, substituted by psql.
write_probe_sql() {
  cat >"$SQLD/70_probe.sql" <<'SQL'
SET /* wiki_gin_entry_probe_guards */ statement_timeout = '600s';
SET /* wiki_gin_entry_probe_guards */ lock_timeout = '2s';
INSERT INTO :tbl
WITH /* wiki_gin_entry_probe_derived */ ctl AS (
    SELECT database_block_size::bigint                          AS bs,
           24::bigint                                           AS hdr,
           4::bigint                                            AS iid,
           ((8 + max_data_alignment - 1) / max_data_alignment)
             * max_data_alignment                               AS gin_special
    FROM pg_control_init()
),
pages AS (
    SELECT c.hdr, c.iid, o.flags, h.lower, h.upper, h.special, h.pagesize
    FROM ctl c
         CROSS JOIN LATERAL generate_series(
               1, pg_relation_size(:'idx', 'main') / c.bs - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page(:'idx', b.blkno::int) AS pg
                             OFFSET 0) AS r
         LEFT JOIN LATERAL page_header(r.pg) AS h ON true
         LEFT JOIN LATERAL gin_page_opaque_info(
               CASE WHEN h.upper > 0 AND h.pagesize = c.bs
                     AND h.pagesize - h.special = c.gin_special
                    THEN r.pg END)           AS o ON true
)
SELECT :'fx', :'idx',
       count(*)                        FILTER (WHERE flags = '{leaf}') AS entry_leaf_pages,
       sum((lower - hdr) / iid)        FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuples,
       sum(special - upper)            FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuple_bytes,
       sum((lower - hdr) / iid)        FILTER (WHERE flags = '{}')     AS internal_downlinks,
       count(*) FILTER (WHERE flags <@ '{leaf,incomplete_split}'::text[]
                          AND (lower < hdr OR (lower - hdr) % iid <> 0))
                                                                       AS malformed_pages,
       count(*) FILTER (WHERE flags IS NULL)                           AS undecoded_pages
FROM pages;
SQL
}

stage_probe() {
  p "$DB" -q -c "DELETE FROM wiki.probe" || die
  write_probe_sql
  local fx idx
  while IFS='|' read -r fx idx; do
    [ -z "$fx" ] && continue
    p "$DB" -q -v tbl=wiki.probe -v fx="$fx" -v idx="$idx" -f "$SQLD/70_probe.sql" || die "probe failed for $idx"
  done < <(q "$DB" "SELECT fixture || '|' || idx FROM wiki.fixture WHERE scored ORDER BY fixture")
  p "$DB" -c "SELECT /* wiki_gin_probe */ fixture, entry_leaf_pages, entry_leaf_tuples,
                     entry_leaf_tuple_bytes, internal_downlinks, malformed_pages, undecoded_pages
              FROM wiki.probe ORDER BY fixture" | tee "$OUT/11-entry-tuple-probe.txt"
  # distinct keys the tables hold, counted without the index
  p "$DB" -c "SELECT /* wiki_gin_probe */ 'f3_fresh' AS fixture,
                     count(DISTINCT l.lexeme) AS distinct_keys_in_table
              FROM t3_fresh t CROSS JOIN LATERAL unnest(to_tsvector('simple', t.doc)) l
              UNION ALL
              SELECT 'f6_slack', count(DISTINCT k)
              FROM t6_slack t CROSS JOIN LATERAL unnest(t.tags) k" | tee -a "$OUT/11-entry-tuple-probe.txt"
  # the layout probe: the page-format constants, measured on this build
  p "$DB" <<'SQL' | tee "$OUT/12-layout-probe.txt"
SET /* wiki_gin_layout_guards */ statement_timeout = '600s';
SET /* wiki_gin_layout_guards */ lock_timeout = '2s';
CREATE TEMPORARY TABLE /* wiki_gin_layout_probe */ wiki_layout_e (tags int[]);
CREATE TEMPORARY TABLE /* wiki_gin_layout_probe */ wiki_layout_1 (tags int[]);
INSERT INTO /* wiki_gin_layout_probe */ wiki_layout_1 VALUES ('{1}');
CREATE INDEX /* wiki_gin_layout_probe */ wiki_layout_ei
    ON wiki_layout_e USING gin (tags) WITH (fastupdate = off);
CREATE INDEX /* wiki_gin_layout_probe */ wiki_layout_1i
    ON wiki_layout_1 USING gin (tags) WITH (fastupdate = off);
WITH /* wiki_gin_layout_probe */ ctl AS (
    SELECT database_block_size::bigint                          AS bs,
           max_data_alignment::bigint                           AS al,
           ((8 + max_data_alignment - 1) / max_data_alignment)
             * max_data_alignment                               AS gin_special_derived
    FROM pg_control_init()
),
e AS (
    SELECT h.lower AS hdr, h.upper AS e_upper, h.special AS e_special,
           h.pagesize AS e_pagesize, h.pagesize - h.special AS gin_special_seen,
           o.flags AS e_flags
    FROM (SELECT get_raw_page('wiki_layout_ei', 1) AS pg OFFSET 0) r
         LEFT JOIN LATERAL page_header(r.pg)            AS h ON true
         LEFT JOIN LATERAL gin_page_opaque_info(r.pg)   AS o ON true
),
one AS (
    SELECT h.lower AS one_lower, o.flags AS one_flags, h.special - h.upper AS one_tuple_bytes
    FROM (SELECT get_raw_page('wiki_layout_1i', 1) AS pg OFFSET 0) r
         LEFT JOIN LATERAL page_header(r.pg)            AS h ON true
         LEFT JOIN LATERAL gin_page_opaque_info(r.pg)   AS o ON true
)
SELECT c.bs AS block_size, c.al AS max_data_alignment, e.hdr AS page_header_bytes,
       o.one_lower - e.hdr AS line_pointer_bytes,
       e.gin_special_seen AS gin_special_bytes, c.gin_special_derived,
       c.bs - ((e.hdr + (o.one_lower - e.hdr) + c.al - 1) / c.al) * c.al AS max_fsm_request_derived,
       o.one_tuple_bytes AS one_entry_tuple_bytes,
       COALESCE(NULLIF(array_to_string(array_remove(ARRAY[
         CASE WHEN e.e_pagesize <> c.bs THEN 'empty-root pagesize ' || e.e_pagesize || ' <> block_size' END,
         CASE WHEN e.e_upper <> e.e_special THEN 'empty-root page is not untouched (upper <> special)' END,
         CASE WHEN e.e_flags <> '{leaf}'::text[] THEN 'empty-root flags ' || e.e_flags::text || ' <> {leaf}' END,
         CASE WHEN o.one_flags <> '{leaf}'::text[] THEN 'one-tuple root flags ' || o.one_flags::text || ' <> {leaf}' END,
         CASE WHEN e.gin_special_seen <> c.gin_special_derived
              THEN 'GIN special area ' || e.gin_special_seen || ' <> derived ' || c.gin_special_derived END,
         CASE WHEN o.one_lower <= e.hdr THEN 'one-tuple root has no line pointer' END
       ], NULL), '; '), ''), 'ok') AS status
FROM ctl c CROSS JOIN e CROSS JOIN one o;
SQL
}

# The same probe again, after the oracle has rebuilt every scored index, so the
# dead-key population is measured rather than inferred: entry tuples before the
# rebuild minus entry tuples after it.  Runs after "oracle" in the default
# order, and needs wiki.probe to have been filled by the probe stage.
stage_probe_after() {
  write_probe_sql
  p "$DB" -q -c "CREATE TABLE IF NOT EXISTS wiki.probe_after (LIKE wiki.probe);
                 DELETE FROM wiki.probe_after" || die
  local fx idx
  while IFS='|' read -r fx idx; do
    [ -z "$fx" ] && continue
    p "$DB" -q -v tbl=wiki.probe_after -v fx="$fx" -v idx="$idx" -f "$SQLD/70_probe.sql" \
      || die "probe_after failed for $idx"
  done < <(q "$DB" "SELECT fixture || '|' || idx FROM wiki.fixture WHERE scored ORDER BY fixture")
  p "$DB" -c "SELECT /* wiki_gin_probe_after */ b.fixture,
                     b.entry_leaf_tuples AS tuples_before,
                     a.entry_leaf_tuples AS tuples_after,
                     b.entry_leaf_tuples - a.entry_leaf_tuples AS dead_entry_tuples,
                     a.entry_leaf_pages  AS entry_leaf_pages_after,
                     a.malformed_pages, a.undecoded_pages
              FROM wiki.probe b JOIN wiki.probe_after a USING (fixture)
              ORDER BY b.fixture" | tee "$OUT/18-entry-tuple-probe-after.txt"
}

# ------------------------------------------------------------ coverage stage

stage_coverage() {
  write_sql_files
  : >"$OUT/13-coverage.txt"
  cov() { printf '\n=== %s\n' "$*" | tee -a "$OUT/13-coverage.txt"; }

  # (1) a snapshot held across the settling VACUUM ---------------------------
  cov "f8_horizon: a snapshot held across the settling VACUUM"
  q "$DB" "DELETE /* wiki_gin_coverage */ FROM t8_horizon WHERE id <= ($ROWS * 95) / 100" \
    | tee -a "$OUT/13-coverage.txt"
  PGAPPNAME=wiki_holder p "$DB" -q -c "BEGIN ISOLATION LEVEL REPEATABLE READ;
        SELECT /* wiki_gin_coverage */ pg_current_xact_id();
        SELECT /* wiki_gin_coverage */ count(*) FROM t8_horizon;
        SELECT /* wiki_gin_coverage */ pg_sleep(120);" >/dev/null 2>&1 &
  sleep 3
  q "$DB" "SELECT 'holder backend_xmin=' || coalesce(backend_xmin::text,'null')
           FROM pg_stat_activity WHERE application_name = 'wiki_holder'" | tee -a "$OUT/13-coverage.txt"
  pe "$DB" -c "VACUUM /* wiki_gin_coverage */ (VERBOSE) t8_horizon" 2>&1 \
    | grep -F 'index "f8' | tee -a "$OUT/13-coverage.txt"
  q "$DB" "SELECT pg_current_xact_id()" >/dev/null
  q "$DB" "SELECT pg_current_xact_id()" >/dev/null
  q "$DB" "SELECT pg_current_xact_id()" >/dev/null
  pe "$DB" -c "VACUUM /* wiki_gin_coverage */ (VERBOSE) t8_horizon" 2>&1 \
    | grep -F 'index "f8' | tee -a "$OUT/13-coverage.txt"
  p "$DB" -q -v run=f8_snapshot_held -f "$SQLD/census_insert.sql"
  q "$DB" "SELECT 'snapshot held: deleted_pages=' || deleted_pages || ' fsm_free=' ||
                  (SELECT count(*) FROM pg_freespace('f8_horizon_gin')
                    WHERE avail = (SELECT database_block_size
                            - ((28 + max_data_alignment - 1) / max_data_alignment)
                              * max_data_alignment FROM pg_control_init()))
           FROM wiki.census_run WHERE run = 'f8_snapshot_held' AND index_name = 'f8_horizon_gin'" \
    | tee -a "$OUT/13-coverage.txt"
  q "$DB" "SELECT 'terminated=' || pg_terminate_backend(pid) FROM pg_stat_activity
           WHERE application_name = 'wiki_holder'" | tee -a "$OUT/13-coverage.txt"
  wait 2>/dev/null
  pe "$DB" -c "VACUUM /* wiki_gin_coverage */ (VERBOSE) t8_horizon" 2>&1 \
    | grep -F 'index "f8' | tee -a "$OUT/13-coverage.txt"
  p "$DB" -q -v run=f8_snapshot_gone -f "$SQLD/census_insert.sql"
  q "$DB" "SELECT 'holder gone: deleted_pages=' || deleted_pages || ' fsm_free=' ||
                  (SELECT count(*) FROM pg_freespace('f8_horizon_gin')
                    WHERE avail = (SELECT database_block_size
                            - ((28 + max_data_alignment - 1) / max_data_alignment)
                              * max_data_alignment FROM pg_control_init()))
           FROM wiki.census_run WHERE run = 'f8_snapshot_gone' AND index_name = 'f8_horizon_gin'" \
    | tee -a "$OUT/13-coverage.txt"
  q "$DB" "SELECT pg_stat_force_next_flush()" >/dev/null
  pe "$DB" -c "VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) t8_horizon" 2>&1 \
    | grep -F 'index "f8' | tee -a "$OUT/13-coverage.txt"

  # (2) does the ANALYZE half rewrite the measured index's catalog row? ------
  cov "the ANALYZE half of the maintenance step, against a stale index catalog row"
  q "$DB" "DROP TABLE IF EXISTS tan_cat" >/dev/null
  p "$DB" -q <<'SQL'
SET /* wiki_gin_coverage */ gin_pending_list_limit = '1GB';
CREATE TABLE /* wiki_gin_coverage */ tan_cat (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_coverage */ tan_cat SELECT i, ARRAY[i % 97] FROM generate_series(1, 5000) i;
CREATE INDEX /* wiki_gin_coverage */ an_cat_gin ON tan_cat USING gin (tags) WITH (fastupdate = off);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_coverage */ ANALYZE tan_cat;
-- grow the index with no VACUUM and no ANALYZE, so its pg_class row goes stale
INSERT INTO /* wiki_gin_coverage */ tan_cat SELECT i, ARRAY[i % 97] FROM generate_series(5001, 60000) i;
SQL
  q "$DB" "SELECT 'stale: relpages=' || c.relpages || ' reltuples=' || c.reltuples
                  || ' live_blocks=' || (pg_relation_size('an_cat_gin','main')
                                         / current_setting('block_size')::bigint)
           FROM pg_class c WHERE c.relname = 'an_cat_gin'" | tee -a "$OUT/13-coverage.txt"
  q "$DB" "ANALYZE /* wiki_gin_coverage */ tan_cat" >/dev/null
  q "$DB" "SELECT 'after ANALYZE: relpages=' || c.relpages || ' reltuples=' || c.reltuples
                  || ' live_blocks=' || (pg_relation_size('an_cat_gin','main')
                                         / current_setting('block_size')::bigint)
           FROM pg_class c WHERE c.relname = 'an_cat_gin'" | tee -a "$OUT/13-coverage.txt"
  q "$DB" "SELECT 'metapage after the bare ANALYZE: pending_pages=' || m.n_pending_pages
                  || ' n_total_pages=' || m.n_total_pages || ' vs blocks='
                  || (pg_relation_size('an_cat_gin','main') / current_setting('block_size')::bigint)
           FROM gin_metapage_info(get_raw_page('an_cat_gin', 0)) m" | tee -a "$OUT/13-coverage.txt"
  q "$DB" "SELECT pg_stat_force_next_flush()" >/dev/null
  pe "$DB" -c "VACUUM /* wiki_gin_maintenance */ (VERBOSE, ANALYZE) tan_cat" 2>&1 \
    | grep -F 'index "an_cat' | tee -a "$OUT/13-coverage.txt"
  q "$DB" "SELECT 'metapage after VACUUM ANALYZE: pending_pages=' || m.n_pending_pages
                  || ' n_total_pages=' || m.n_total_pages || ' vs blocks='
                  || (pg_relation_size('an_cat_gin','main') / current_setting('block_size')::bigint)
           FROM gin_metapage_info(get_raw_page('an_cat_gin', 0)) m" | tee -a "$OUT/13-coverage.txt"

  # (3) privileges and refusals ---------------------------------------------
  cov "privileges: a role holding only pg_stat_scan_tables"
  q "$DB" "DROP ROLE IF EXISTS wiki_scan" >/dev/null
  q "$DB" "CREATE ROLE wiki_scan LOGIN IN ROLE pg_stat_scan_tables" >/dev/null
  q "$DB" "GRANT USAGE ON SCHEMA public TO wiki_scan" >/dev/null
  pe "$DB" -c "SET ROLE wiki_scan; SELECT get_raw_page('f6_slack_gin', 0) IS NOT NULL" 2>&1 \
    | head -3 | tee -a "$OUT/13-coverage.txt"
  pe "$DB" -c "SET ROLE wiki_scan; SELECT * FROM pgstatginindex('f6_slack_gin')" 2>&1 \
    | head -4 | tee -a "$OUT/13-coverage.txt"
  pe "$DB" -c "SET ROLE wiki_scan; SELECT count(*) AS fsm_rows FROM pg_freespace('f6_slack_gin')" 2>&1 \
    | head -4 | tee -a "$OUT/13-coverage.txt"
  pe "$DB" -c "SET ROLE wiki_scan; SELECT max_data_alignment, database_block_size FROM pg_control_init()" 2>&1 \
    | head -4 | tee -a "$OUT/13-coverage.txt"

  cov "refusals: pgstattuple on GIN, an invalid index, and both temporary cases"
  pe "$DB" -c "SELECT * FROM pgstattuple('f6_slack_gin')" 2>&1 | head -2 | tee -a "$OUT/13-coverage.txt"
  q "$DB" "DROP TABLE IF EXISTS t_inv" >/dev/null
  q "$DB" "CREATE TABLE t_inv (id int, v int); INSERT INTO t_inv VALUES (1,2),(2,1)" >/dev/null
  pe "$DB" -c "CREATE INDEX CONCURRENTLY tinv_bad ON t_inv USING gin ((ARRAY[10/(v-1)]))" 2>&1 \
    | head -2 | tee -a "$OUT/13-coverage.txt"
  q "$DB" "SELECT 'tinv_bad: indisvalid=' || indisvalid || ' indisready=' || indisready
                  || ' indislive=' || indislive FROM pg_index WHERE indexrelid = 'tinv_bad'::regclass" \
    | tee -a "$OUT/13-coverage.txt"
  q "$DB" "SELECT 'census sees tinv_bad: ' || count(*) FROM wiki.census_run
           WHERE run = 'decide' AND index_name = 'tinv_bad'" | tee -a "$OUT/13-coverage.txt"
  pe "$DB" -c "SELECT version FROM gin_metapage_info(get_raw_page('tinv_bad', 0))" 2>&1 \
    | head -4 | tee -a "$OUT/13-coverage.txt"
  pe "$DB" -c "SELECT * FROM pgstatginindex('tinv_bad')" 2>&1 | head -2 | tee -a "$OUT/13-coverage.txt"
  pe "$DB" -c "SELECT gin_clean_pending_list('tinv_bad')" 2>&1 | head -3 | tee -a "$OUT/13-coverage.txt"
  # one -c per statement: psql runs a multi-statement -c in a single
  # transaction, and an uncommitted temporary index is invisible to the
  # session that is supposed to be refused access to it.
  PGAPPNAME=wiki_temp p "$DB" -q \
        -c "CREATE TEMP TABLE ott (tags int[])" \
        -c "INSERT INTO ott VALUES ('{1,2}')" \
        -c "CREATE INDEX ott_gin ON ott USING gin (tags)" \
        -c "SELECT pg_sleep(60)" >/dev/null 2>&1 &
  sleep 3
  local otemp
  otemp=$(q "$DB" "SELECT c.oid::regclass::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                   WHERE c.relname = 'ott_gin' AND n.nspname LIKE 'pg_temp%'")
  printf 'other session temp index: %s\n' "${otemp:-not found}" | tee -a "$OUT/13-coverage.txt"
  if [ -n "$otemp" ]; then
    pe "$DB" -c "SELECT get_raw_page('$otemp', 0) IS NOT NULL" 2>&1 | head -2 | tee -a "$OUT/13-coverage.txt"
    pe "$DB" -c "SELECT * FROM pgstatginindex('$otemp')" 2>&1 | head -2 | tee -a "$OUT/13-coverage.txt"
    pe "$DB" -c "SELECT count(*) AS fsm_rows FROM pg_freespace('$otemp')" 2>&1 | head -4 | tee -a "$OUT/13-coverage.txt"
  fi
  q "$DB" "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='wiki_temp'" >/dev/null
  wait 2>/dev/null
  pe "$DB" -c "CREATE TEMP TABLE own (tags int[]);
               INSERT INTO own VALUES ('{1,2}');
               CREATE INDEX own_gin ON own USING gin (tags);
               SELECT 'own temp index readable: ' || (get_raw_page('own_gin', 0) IS NOT NULL)" 2>&1 \
    | tail -3 | tee -a "$OUT/13-coverage.txt"

  # (4) the measurement lock, and what it holds off --------------------------
  # On its own fixture, because one of the commands below is a DROP INDEX and
  # a scored fixture must not depend on the lock actually holding.
  cov "the measurement lock: what SHARE ROW EXCLUSIVE holds off, lock_timeout 2s"
  q "$DB" "DROP TABLE IF EXISTS tl_lock" >/dev/null
  p "$DB" -q <<'SQL'
CREATE TABLE /* wiki_gin_coverage */ tl_lock (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_coverage */ tl_lock SELECT i, ARRAY[i % 97] FROM generate_series(1, 20000) i;
CREATE INDEX /* wiki_gin_coverage */ l1_lock_gin ON tl_lock USING gin (tags) WITH (fastupdate = on);
SELECT /* wiki_gin_publish */ pg_stat_force_next_flush();
VACUUM /* wiki_gin_coverage */ ANALYZE tl_lock;
SQL
  PGAPPNAME=wiki_locker p "$DB" -q -c "BEGIN;
        LOCK /* wiki_gin_waste_protocol */ TABLE tl_lock IN SHARE ROW EXCLUSIVE MODE;
        SELECT pg_sleep(45);" >/dev/null 2>&1 &
  sleep 3
  local cmd t0 t1 res
  while IFS= read -r cmd; do
    [ -z "$cmd" ] && continue
    t0=$(date +%s%N)
    res=$(pe "$DB" -c "$cmd" </dev/null 2>&1 | grep -E 'ERROR|ROLLBACK|^ *[0-9]+$|^REINDEX|^VACUUM|^ANALYZE|^DROP|^CLUSTER|^INSERT' | head -1)
    t1=$(date +%s%N)
    printf '%-52s %6s ms  %s\n' "$cmd" "$(( (t1 - t0) / 1000000 ))" "${res:-ok}" \
      | tee -a "$OUT/13-coverage.txt"
  done <<'CMDS'
INSERT INTO tl_lock VALUES (-1, '{1}')
VACUUM tl_lock
ANALYZE tl_lock
REINDEX INDEX l1_lock_gin
VACUUM FULL tl_lock
DROP INDEX l1_lock_gin
CLUSTER tl_lock USING tl_lock_pkey
SELECT count(*) FROM tl_lock
SELECT gin_clean_pending_list('l1_lock_gin')
CMDS
  t0=$(date +%s%N)
  res=$(pe "$DB" -c "REINDEX INDEX CONCURRENTLY l1_lock_gin" </dev/null 2>&1 | head -1)
  t1=$(date +%s%N)
  printf '%-52s %6s ms  %s\n' "REINDEX INDEX CONCURRENTLY l1_lock_gin" "$(( (t1 - t0) / 1000000 ))" "$res" \
    | tee -a "$OUT/13-coverage.txt"
  q "$DB" "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='wiki_locker'" >/dev/null
  wait 2>/dev/null

  # (5) the one hole a table lock cannot close ------------------------------
  cov "the hole: an owner's gin_clean_pending_list() between two censuses in one locked transaction"
  p "$DB" -q <<'SQL'
SET /* wiki_gin_coverage */ gin_pending_list_limit = '1GB';
-- refill the pending list, so the flush below has something to move
INSERT INTO /* wiki_gin_coverage */ tl_lock
SELECT i, ARRAY[i % 97, (i * 7) % 97] FROM generate_series(20001, 80000) i;
SQL
  { printf 'BEGIN;\n'
    printf "SET LOCAL /* wiki_gin_waste_protocol */ statement_timeout = '%s';\n" "$STMT_TIMEOUT"
    printf 'LOCK /* wiki_gin_waste_protocol */ TABLE tl_lock IN SHARE ROW EXCLUSIVE MODE;\n'
    printf '\\set run hole_before_flush\n\\i %s\n' "$SQLD/census_insert.sql"
    printf 'SELECT pg_sleep(6);\n'
    printf '\\set run hole_after_flush\n\\i %s\n' "$SQLD/census_insert.sql"
    printf 'COMMIT;\n'
  } >"$SQLD/55_hole.sql"
  ( p "$DB" -q -f "$SQLD/55_hole.sql" >/dev/null 2>&1 ) &
  local holepid=$!
  sleep 2
  q "$DB" "SELECT 'the owner flushed ' || gin_clean_pending_list('l1_lock_gin')
                  || ' pending pages from another session'" | tee -a "$OUT/13-coverage.txt"
  wait "$holepid" 2>/dev/null
  p "$DB" -c "SELECT /* wiki_gin_coverage */ run, status, blocks, pending_pages, deleted_pages, bloat_pct, pending_pct
              FROM wiki.census_run WHERE run IN ('hole_before_flush','hole_after_flush')
                AND index_name = 'l1_lock_gin' ORDER BY taken_at" | tee -a "$OUT/13-coverage.txt"
}

# --------------------------------------------------------------- sweep stage
#
# Runs after the oracle, because it rebuilds a scored index.
stage_sweep() {
  : >"$OUT/17-sweep.txt"
  printf '=== the oracle is budget-dependent: f1_churn_gin rebuilt at three budgets\n' \
    >>"$OUT/17-sweep.txt"
  local m sz
  for m in 4MB 64MB 1GB; do
    sz=$(PGOPTIONS="-c maintenance_work_mem=$m" "$BIN/psql" -X -v ON_ERROR_STOP=1 \
         -h "$SOCK" -p "$PORT" -d "$DB" -At \
         -c "REINDEX /* wiki_gin_oracle_sweep */ INDEX f1_churn_gin" \
         -c "SELECT pg_relation_size('f1_churn_gin','main')" | tail -1)
    printf 'maintenance_work_mem=%-5s -> %s bytes\n' "$m" "$sz" >>"$OUT/17-sweep.txt"
    q "$DB" "INSERT INTO wiki.oracle (fixture, idx, mwm, bytes_before, bytes_after, truth_pct, elapsed_ms)
             VALUES ('f1_churn_sweep','f1_churn_gin','$m', NULL, $sz, NULL, NULL)" >/dev/null
  done
  printf '\n=== cost of the census: EXPLAIN (ANALYZE, BUFFERS), three warm runs\n' \
    >>"$OUT/17-sweep.txt"
  local i
  q "$DB" "SELECT 'GIN indexes in the database: ' || count(*) || ', blocks: '
                  || sum(pg_relation_size(c.oid,'main') / current_setting('block_size')::bigint)
           FROM pg_class c JOIN pg_am a ON a.oid = c.relam
           WHERE a.amname = 'gin' AND c.relkind = 'i'" >>"$OUT/17-sweep.txt"
  for i in 1 2 3; do
    # the first Buffers line is the top node's own total
    p "$DB" -At -c "EXPLAIN (ANALYZE, BUFFERS, TIMING ON) $CENSUS" \
      | grep -E 'Buffers: shared|Execution Time' | head -1 | tr -d ' ' >>"$OUT/17-sweep.txt"
    p "$DB" -At -c "EXPLAIN (ANALYZE, BUFFERS, TIMING ON) $CENSUS" \
      | grep -F 'Execution Time' >>"$OUT/17-sweep.txt"
  done
  printf '\n=== the same census with the naive two-read form, for comparison\n' \
    >>"$OUT/17-sweep.txt"
  p "$DB" -At -c "EXPLAIN (ANALYZE, BUFFERS)
      SELECT count(*) FROM (
        SELECT g.oid,
               (gin_page_opaque_info(get_raw_page(g.oid::regclass::text, b.blkno::int))).flags,
               (page_header(get_raw_page(g.oid::regclass::text, b.blkno::int))).upper
        FROM pg_class g JOIN pg_am a ON a.oid = g.relam
             CROSS JOIN LATERAL generate_series(1, pg_relation_size(g.oid,'main')
                   / current_setting('block_size')::bigint - 1) AS b(blkno)
        WHERE a.amname = 'gin' AND g.relkind = 'i' AND g.relname = 'f3_fresh_gin'
      ) z" | grep -E 'Buffers: shared|Execution Time' >>"$OUT/17-sweep.txt"
  printf '\n=== the single-read form on the same one index\n' >>"$OUT/17-sweep.txt"
  local one_sql
  one_sql=$(census_one_sql f3_fresh_gin)
  p "$DB" -At -c "EXPLAIN (ANALYZE, BUFFERS) $one_sql" \
    | grep -E 'Buffers: shared|Execution Time' >>"$OUT/17-sweep.txt"
  cat "$OUT/17-sweep.txt"
}

# ---------------------------------------------------------------- race stage

stage_race() {
  write_sql_files
  bootstrap_wiki_db "$RACEDB"
  note "race fixture"
  p "$RACEDB" -q -v rows="$ROWS" <<'SQL' || die "race fixture failed"
SET /* wiki_gin_race */ statement_timeout = '600s';
DROP TABLE IF EXISTS tr_race, tw_race;
CREATE TABLE /* wiki_gin_race */ tr_race (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_race */ tr_race
SELECT i, ARRAY(SELECT generate_series(0, 31)) FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_race */ r1_race_gin ON tr_race USING gin (tags) WITH (fastupdate = off);
VACUUM /* wiki_gin_race */ ANALYZE tr_race;
DELETE FROM /* wiki_gin_race */ tr_race WHERE id <= (:rows * 95) / 100;
-- a second copy of the same fixture, deleted and deliberately not vacuumed,
-- so case B's queued VACUUM has the same page deletions to do that case A's
-- unlocked VACUUM did
CREATE TABLE /* wiki_gin_race */ tr2_race (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_race */ tr2_race
SELECT i, ARRAY(SELECT generate_series(0, 31)) FROM generate_series(1, :rows) i;
CREATE INDEX /* wiki_gin_race */ r2_race_gin ON tr2_race USING gin (tags) WITH (fastupdate = off);
VACUUM /* wiki_gin_race */ ANALYZE tr2_race;
DELETE FROM /* wiki_gin_race */ tr2_race WHERE id <= (:rows * 95) / 100;
CREATE TABLE /* wiki_gin_race */ tw_race (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_race */ tw_race
SELECT i, ARRAY[i % 1000, (i * 7) % 1000] FROM generate_series(1, 20000) i;
CREATE INDEX /* wiki_gin_race */ w1_race_gin ON tw_race USING gin (tags) WITH (fastupdate = on);
VACUUM /* wiki_gin_race */ ANALYZE tw_race;
SQL
  local vacpid n i

  # case A: censuses back to back across one VACUUM, no lock
  note "race A: censuses across one VACUUM, no lock"
  ( PGAPPNAME=wiki_vac p "$RACEDB" -q -c "VACUUM /* wiki_gin_race */ tr_race" >/dev/null 2>&1 ) &
  vacpid=$!
  n=0
  while kill -0 "$vacpid" 2>/dev/null && [ "$n" -lt 300 ]; do
    p "$RACEDB" -q -v run=race_nolock -f "$SQLD/census_insert.sql" >/dev/null 2>&1
    n=$((n + 1))
  done
  wait "$vacpid" 2>/dev/null
  for i in 1 2 3; do
    p "$RACEDB" -q -v run=race_after -f "$SQLD/census_insert.sql" >/dev/null 2>&1
  done
  note "race A: $n censuses during the VACUUM"

  # case B: the same deletions, vacuumed while the protocol lock is held
  note "race B: the protocol lock held, the VACUUM queued behind it"
  { printf 'BEGIN;\n'
    printf "SET LOCAL /* wiki_gin_waste_protocol */ statement_timeout = '%s';\n" "$STMT_TIMEOUT"
    printf "SET LOCAL /* wiki_gin_waste_protocol */ lock_timeout = '%s';\n" "$LOCK_TIMEOUT"
    printf 'LOCK /* wiki_gin_waste_protocol */ TABLE tr2_race IN SHARE ROW EXCLUSIVE MODE;\n'
    printf 'SELECT pg_sleep(4);\n'
    for i in $(seq 1 20); do
      printf '\\set run race_lock\n'
      printf '\\i %s\n' "$SQLD/census_insert.sql"
    done
    printf 'COMMIT;\n'
  } >"$SQLD/50_race_lock.sql"
  ( p "$RACEDB" -q -f "$SQLD/50_race_lock.sql" >/dev/null 2>&1 ) &
  local lockpid=$!
  sleep 1
  local t0 t1
  t0=$(date +%s%N)
  PGOPTIONS="-c lock_timeout=0" "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" \
    -d "$RACEDB" -q -c "VACUUM /* wiki_gin_race */ (VERBOSE) tr2_race" >"$OUT/race_queued_vacuum.txt" 2>&1
  t1=$(date +%s%N)
  wait "$lockpid" 2>/dev/null
  printf 'queued VACUUM waited %s ms then ran\n' "$(( (t1 - t0) / 1000000 ))" >"$OUT/14-race.txt"
  grep -F 'index "r2' "$OUT/race_queued_vacuum.txt" >>"$OUT/14-race.txt"
  p "$RACEDB" -q -v run=race_lock_after -f "$SQLD/census_insert.sql" >/dev/null 2>&1

  # case C: a concurrent rebuild
  note "race C: censuses across REINDEX INDEX CONCURRENTLY"
  ( PGAPPNAME=wiki_ric "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$RACEDB" -q \
      -c "REINDEX /* wiki_gin_race */ INDEX CONCURRENTLY r1_race_gin" >/dev/null 2>&1 ) &
  local ricpid=$!
  n=0
  while kill -0 "$ricpid" 2>/dev/null && [ "$n" -lt 300 ]; do
    p "$RACEDB" -q -v run=race_ric -f "$SQLD/census_insert.sql" >/dev/null 2>&1
    n=$((n + 1))
  done
  wait "$ricpid" 2>/dev/null
  note "race C: $n censuses during the rebuild"

  # case D: a writer stream into a fastupdate index
  note "race D: censuses under a writer stream"
  ( for b in $(seq 1 30); do
      p "$RACEDB" -q -c "INSERT /* wiki_gin_race */ INTO tw_race
          SELECT i, ARRAY[i % 1000, (i * 7) % 1000]
          FROM generate_series($(( b * 10000 + 10001 )), $(( b * 10000 + 20000 ))) i" >/dev/null 2>&1
    done ) &
  local wpid=$!
  n=0
  while kill -0 "$wpid" 2>/dev/null && [ "$n" -lt 300 ]; do
    p "$RACEDB" -q -v run=race_writer -f "$SQLD/census_insert.sql" >/dev/null 2>&1
    n=$((n + 1))
  done
  wait "$wpid" 2>/dev/null
  note "race D: $n censuses under the writer stream"

  p "$RACEDB" -c "SELECT /* wiki_gin_race_report */ run, index_name, count(*) AS censuses,
                         count(*) FILTER (WHERE status <> 'ok') AS flagged,
                         count(DISTINCT deleted_pages) AS distinct_deleted_readings,
                         min(deleted_pages) AS min_deleted, max(deleted_pages) AS max_deleted,
                         count(DISTINCT blocks) AS distinct_block_counts,
                         min(blocks) AS min_blocks, max(blocks) AS max_blocks
                  FROM wiki.census_run GROUP BY run, index_name ORDER BY run, index_name" \
    | tee -a "$OUT/14-race.txt"
  p "$RACEDB" -c "SELECT /* wiki_gin_race_report */ run, status, count(*) AS censuses
                  FROM wiki.census_run GROUP BY run, status ORDER BY run, count(*) DESC" \
    | tee -a "$OUT/14-race.txt"
}

# ------------------------------------------------------------- corrupt stage

stage_corrupt() {
  write_sql_files
  bootstrap_wiki_db "$CORRDB"
  note "corruption fixtures"
  p "$CORRDB" -q <<'SQL' || die "corrupt fixtures failed"
SET /* wiki_gin_corrupt */ statement_timeout = '600s';
DO $f$
DECLARE i int;
BEGIN
  FOR i IN 1..8 LOOP
    EXECUTE format('DROP TABLE IF EXISTS cs%s', i);
    EXECUTE format('CREATE TABLE cs%s (id int, tags int[])', i);
    EXECUTE format('INSERT INTO cs%s SELECT g, ARRAY[g %% 300, (g * 7) %% 300] FROM generate_series(1, 4000) g', i);
    EXECUTE format('CREATE INDEX s%s_gin ON cs%s USING gin (tags) WITH (fastupdate = off)', i, i);
  END LOOP;
END $f$;
VACUUM /* wiki_gin_corrupt */ ANALYZE;
SQL
  # read what the patches need from the live pages before the server stops
  local lower7 s
  lower7=$(q "$CORRDB" "SELECT lower FROM page_header(get_raw_page('s7_gin', 1))")
  : >"$OUT/15-corrupt.txt"
  p "$CORRDB" -c "SELECT /* wiki_gin_corrupt */ c.relname,
                         pg_relation_size(c.oid,'main') / current_setting('block_size')::int AS blocks
                  FROM pg_class c WHERE c.relname ~ '^s[0-9]_gin' ORDER BY 1" \
    | tee -a "$OUT/15-corrupt.txt"
  declare -A path
  for s in 1 2 3 4 5 6 7 8; do
    path[$s]="$DATA/$(q "$CORRDB" "SELECT pg_relation_filepath('s${s}_gin')")"
  done
  pgstop
  # every offset below was read off the live pages first: PageHeaderData puts
  # pd_lower at 12, pd_upper at 14 and pd_special at 16; the GIN opaque flags
  # word is the last two bytes of the page; and the metapage's ginVersion sits
  # 72 bytes in (24 bytes of page header, then 48 bytes of earlier fields).
  printf '\001'    | dd of="${path[1]}" bs=1 seek=72    conv=notrunc status=none   # ginVersion 2 -> 1
  dd if=/dev/zero of="${path[2]}" bs=8192 count=1 seek=0 conv=notrunc status=none  # block 0 zeroed
  printf '\001'    | dd of="${path[3]}" bs=1 seek=16383 conv=notrunc status=none   # unknown flag bit on block 1
  printf '\350'    | dd of="${path[4]}" bs=1 seek=8208  conv=notrunc status=none   # block 1 pd_special 8184 -> 8168
  # two all-zero blocks, appended by the shell: BSD dd, as on macOS, has no oflag=append
  dd if=/dev/zero bs=8192 count=2 status=none >>"${path[5]}"
  printf '\360'    | dd of="${path[6]}" bs=1 seek=14    conv=notrunc status=none   # block 0 pd_upper -> 8176
  printf '\360'    | dd of="${path[6]}" bs=1 seek=16    conv=notrunc status=none   # block 0 pd_special -> 8176
  printf "\\$(printf '%03o' $((lower7 + 1)))" \
                   | dd of="${path[7]}" bs=1 seek=8204  conv=notrunc status=none   # block 1 pd_lower +1
  # s8 is patched in a second cycle: its block 0 breaks pd_upper <= pd_special,
  # which the buffer manager refuses before any SQL guard runs, and that error
  # would otherwise hide what the other seven do to a multi-index report.
  pgstart || die "server did not restart after patching"
  printf '\n=== the multi-index report over the seven SQL-visible patches\n' >>"$OUT/15-corrupt.txt"
  pe "$CORRDB" -c "$CENSUS" 2>&1 | tail -8 >>"$OUT/15-corrupt.txt"
  for s in 1 2 3 4 5 6 7; do
    printf '\n=== s%s_gin alone\n' "$s" >>"$OUT/15-corrupt.txt"
    census_one "$CORRDB" "s${s}_gin" 2>&1 \
      | grep -E 'index_name|status|ERROR|DETAIL|^ s[0-9]_gin|-\[ RECORD|blocks |new_pages' \
      | head -12 >>"$OUT/15-corrupt.txt"
    printf -- '--- status only: ' >>"$OUT/15-corrupt.txt"
    one_sql=$(census_one_sql "s${s}_gin")
    pe "$CORRDB" -At -c "SELECT status FROM ( $one_sql ) z" 2>&1 \
      | head -2 | tr '\n' ' ' >>"$OUT/15-corrupt.txt"
    printf '\n' >>"$OUT/15-corrupt.txt"
  done
  # the second cycle: the patch no SQL guard can reach
  pgstop
  printf '\350' | dd of="${path[8]}" bs=1 seek=16 conv=notrunc status=none  # block 0 pd_special only
  pgstart || die "server did not restart after the s8 patch"
  printf '\n=== s8_gin: pd_special moved with pd_upper left behind\n' >>"$OUT/15-corrupt.txt"
  one_sql=$(census_one_sql s8_gin)
  pe "$CORRDB" -At -c "SELECT status FROM ( $one_sql ) z" 2>&1 | head -3 >>"$OUT/15-corrupt.txt"
  printf '\n=== the multi-index report with s8 in the database\n' >>"$OUT/15-corrupt.txt"
  pe "$CORRDB" -At -c "SELECT index_name || ' | ' || status FROM ( $CENSUS ) z" 2>&1 \
    | head -10 >>"$OUT/15-corrupt.txt"
  printf '\n=== s8_gin with zero_damaged_pages = on (PGC_SUSET, session scope)\n' >>"$OUT/15-corrupt.txt"
  pe "$CORRDB" -At -c "SET zero_damaged_pages = on;
                       SELECT status FROM ( $one_sql ) z" 2>&1 \
    | head -4 >>"$OUT/15-corrupt.txt"
  printf '\n=== the derived entry-tuple probe on the appended-zero-page index s5_gin\n' >>"$OUT/15-corrupt.txt"
  p "$CORRDB" -q -c "CREATE SCHEMA IF NOT EXISTS wiki" 2>/dev/null
  p "$CORRDB" -q -c "CREATE TABLE IF NOT EXISTS wiki.probe (fixture text, idx text,
        entry_leaf_pages bigint, entry_leaf_tuples bigint, entry_leaf_tuple_bytes bigint,
        internal_downlinks bigint, malformed_pages bigint, undecoded_pages bigint)" 2>/dev/null
  # the probe's text inserts into :tbl, so the destination is passed like the
  # two probe stages pass it; a failure here stops the run instead of leaving
  # an empty table behind
  write_probe_sql
  p "$CORRDB" -q -v tbl=wiki.probe -v fx=s5 -v idx=s5_gin -f "$SQLD/70_probe.sql" \
    || die "probe failed for s5_gin"
  p "$CORRDB" -q -v tbl=wiki.probe -v fx=s7 -v idx=s7_gin -f "$SQLD/70_probe.sql" \
    || die "probe failed for s7_gin"
  p "$CORRDB" -c "SELECT * FROM wiki.probe ORDER BY fixture" >>"$OUT/15-corrupt.txt" 2>&1
  cat "$OUT/15-corrupt.txt"
}

# ------------------------------------------------------------- standby stage

stage_standby() {
  note "standby: the settle step cannot run there"
  rm -rf "$STANDBY" "$SBSOCK"; mkdir -p "$SBSOCK"
  "$BIN/pg_basebackup" -D "$STANDBY" -h "$SOCK" -p "$PORT" -R -X stream \
    >"$OUT/basebackup.log" 2>&1 || die "pg_basebackup failed, see $OUT/basebackup.log"
  cat >>"$STANDBY/postgresql.conf" <<CONF
port = $SBPORT
unix_socket_directories = '$SBSOCK'
hot_standby = on
CONF
  "$BIN/pg_ctl" -D "$STANDBY" -l "$OUT/standby.log" -w start >/dev/null || die "standby did not start"
  : >"$OUT/16-standby.txt"
  sb() { PGOPTIONS="-c statement_timeout=$STMT_TIMEOUT" "$BIN/psql" -X -h "$SBSOCK" -p "$SBPORT" -d "$DB" "$@" 2>&1; }
  sb -At -c "SELECT 'in recovery: ' || pg_is_in_recovery()" | tee -a "$OUT/16-standby.txt"
  sb -c "VACUUM /* wiki_gin_standby */ t6_slack" | head -2 | tee -a "$OUT/16-standby.txt"
  sb -c "SELECT /* wiki_gin_standby */ gin_clean_pending_list('f6_slack_gin')" | head -3 | tee -a "$OUT/16-standby.txt"
  sb -c "ANALYZE /* wiki_gin_standby */ t6_slack" | head -2 | tee -a "$OUT/16-standby.txt"
  sb -At -c "SELECT 'census on the standby: ' || index_name || ' ' || status || ' blocks=' || blocks
             FROM ( $CENSUS ) z WHERE index_name IN ('f6_slack_gin','f5_deleted_gin')" \
    | tee -a "$OUT/16-standby.txt"
  sb -At -c "SELECT 'pgstatginindex on the standby: ' || version || '|' || pending_pages || '|' || pending_tuples
             FROM pgstatginindex('f6_slack_gin')" | tee -a "$OUT/16-standby.txt"
  "$BIN/pg_ctl" -D "$STANDBY" -m fast -w stop >/dev/null || note "standby stop returned non-zero"
  rm -rf "$STANDBY" "$SBSOCK"
  note "standby stopped and its data directory removed"
}

# ------------------------------------------------------- portability stage
#
# Outside the protocol, and the same text in both leg scripts: the 17.11 leg
# runs it as its "portability" stage, the 12.2 leg as its only measuring stage,
# so the two out/19-portability.txt files compare line by line.  It carries the
# page's four published statements and the derived entry-tuple probe verbatim,
# runs them with and without the three edits the page made for PostgreSQL 12,
# and adds the decoders' answers on an all-zero page, the refusals that differ
# between majors, VACUUM VERBOSE's index report and the two harness constructs
# 12.2 lacks.  It builds everything it reads in two databases of its own,
# "port" and "portmeta"; every object in them is disposable.

read -r -d '' PUB_CENSUS <<'PUB_CENSUS_SQL'
WITH /* wiki_gin_waste_census */ gin_idx AS (
    SELECT c.oid                                  AS idx,
           c.oid::regclass::text                  AS idx_name,
           pg_relation_size(c.oid, 'main')         AS main_bytes,
           current_setting('block_size')::bigint   AS bs
    FROM pg_class c
         JOIN pg_am a    ON a.oid = c.relam
         JOIN pg_index x ON x.indexrelid = c.oid
    WHERE a.amname = 'gin'
      AND c.relkind = 'i'            -- 'I' (partitioned) has no storage
      AND x.indisvalid               -- an invalid index is still readable, see notes
      AND c.relpersistence <> 't'    -- another session's temp index is refused
),
meta AS (
    SELECT g.*, m.version, m.n_pending_pages, m.n_pending_tuples,
           m.n_total_pages, m.n_entry_pages, m.n_data_pages
    FROM gin_idx g
         CROSS JOIN LATERAL gin_metapage_info(get_raw_page(g.idx_name, 0)) m
),
pages AS (
    SELECT g.idx,
           CASE
               WHEN h.pagesize = 0                      THEN 'new'   -- all-zero page
               WHEN o.flags IS NULL                     THEN 'new'
               WHEN o.flags @> '{meta}'                 THEN 'meta'
               WHEN o.flags @> '{deleted}'              THEN 'deleted'
               WHEN o.flags @> '{list}'                 THEN 'pending'
               WHEN o.flags @> '{data,leaf,compressed}' THEN 'data_leaf'
               WHEN o.flags @> '{data,leaf}'            THEN 'data_leaf_uncompressed'
               WHEN o.flags @> '{data}'                 THEN 'data_internal'
               ELSE                                          'entry'
           END                                          AS page_class,
           COALESCE(h.upper - h.lower, 0)               AS slack
    FROM gin_idx g
         CROSS JOIN LATERAL generate_series(1, g.main_bytes / g.bs - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page(g.idx_name, b.blkno::int) AS pg
                             OFFSET 0) AS r          -- read each page exactly once
         LEFT JOIN LATERAL gin_page_opaque_info(r.pg) AS o ON true
         LEFT JOIN LATERAL page_header(r.pg)          AS h ON true
),
census AS (
    SELECT idx,
           count(*) FILTER (WHERE page_class = 'entry')                  AS entry_pages,
           count(*) FILTER (WHERE page_class = 'data_leaf')              AS data_leaf_pages,
           count(*) FILTER (WHERE page_class = 'data_internal')          AS data_internal_pages,
           count(*) FILTER (WHERE page_class = 'data_leaf_uncompressed') AS uncompressed_pages,
           count(*) FILTER (WHERE page_class = 'pending')                AS pending_pages,
           count(*) FILTER (WHERE page_class = 'deleted')                AS deleted_pages,
           count(*) FILTER (WHERE page_class = 'new')                    AS new_pages,
           count(*) FILTER (WHERE page_class = 'meta')                   AS stray_meta_pages,
           COALESCE(sum(slack) FILTER (WHERE page_class = 'entry'), 0)   AS entry_slack,
           COALESCE(sum(slack) FILTER (WHERE page_class IN ('data_leaf',
                                            'data_internal')), 0)        AS data_slack
    FROM pages
    GROUP BY idx
)
SELECT m.idx_name                                       AS index_name,
       m.version                                        AS gin_version,
       m.main_bytes                                     AS main_fork_bytes,
       m.main_bytes / m.bs                              AS blocks,
       c.entry_pages, c.data_leaf_pages, c.data_internal_pages,
       c.uncompressed_pages, c.pending_pages, c.deleted_pages, c.new_pages,
       (c.deleted_pages + c.new_pages) * m.bs           AS whole_page_waste_bytes,
       round(100.0 * (c.deleted_pages + c.new_pages) * m.bs
             / nullif(m.main_bytes, 0), 2)              AS whole_page_waste_pct,
       CASE WHEN m.version = 2 THEN c.entry_slack + c.data_slack END
                                                        AS live_page_slack_bytes,
       CASE WHEN m.version = 2
            THEN round(100.0 * (c.entry_slack + c.data_slack)
                       / nullif(m.main_bytes, 0), 2) END AS live_page_slack_pct,
       CASE WHEN m.version = 2
            THEN round(100.0 * ((c.deleted_pages + c.new_pages) * m.bs
                                + c.entry_slack + c.data_slack)
                       / nullif(m.main_bytes, 0), 2) END AS bloat_pct,
       c.entry_slack, c.data_slack,
       c.pending_pages * m.bs                           AS pending_bytes,
       round(100.0 * c.pending_pages * m.bs
             / nullif(m.main_bytes, 0), 2)              AS pending_pct,
       m.main_bytes - (c.deleted_pages + c.new_pages + c.pending_pages) * m.bs
                    - c.entry_slack - c.data_slack      AS payload_bytes,
       m.n_pending_pages                                AS meta_pending_pages,
       m.n_entry_pages                                  AS meta_entry_pages,
       m.n_data_pages                                   AS meta_data_pages,
       m.n_total_pages                                  AS meta_total_pages,
       1 + c.entry_pages + c.data_leaf_pages + c.data_internal_pages
         + c.uncompressed_pages + c.pending_pages + c.deleted_pages
         + c.new_pages + c.stray_meta_pages             AS census_total_pages
FROM meta m JOIN census c ON c.idx = m.idx
ORDER BY 1;
PUB_CENSUS_SQL
read -r -d '' PUB_PROBE <<'PUB_PROBE_SQL'
WITH /* wiki_gin_entry_probe */ pages AS (
    SELECT o.flags, h.lower, h.upper, h.special, h.pagesize
    FROM generate_series(1, pg_relation_size('myschema.myindex','main') / 8192 - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page('myschema.myindex', b.blkno::int) AS pg
                             OFFSET 0) AS r
         LEFT JOIN LATERAL gin_page_opaque_info(r.pg) AS o ON true
         LEFT JOIN LATERAL page_header(r.pg)          AS h ON true
)
SELECT count(*)                 FILTER (WHERE flags = '{leaf}') AS entry_leaf_pages,
       sum((lower - 24) / 4)    FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuples,
       sum(special - upper)     FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuple_bytes,
       sum((lower - 24) / 4)    FILTER (WHERE flags = '{}'
                                        AND pagesize > 0)       AS internal_downlinks
FROM pages;
PUB_PROBE_SQL
read -r -d '' DER_PROBE <<'DER_PROBE_SQL'
WITH /* wiki_gin_entry_probe_derived */ ctl AS (
    -- bs and al are build-dependent and come from pg_control_init().  hdr and
    -- iid are page-format constants: SizeOfPageHeaderData is
    -- offsetof(PageHeaderData, pd_linp) over fixed-width fields, and ItemIdData
    -- is three bit-fields totalling 32 bits.  The layout probe measures all
    -- four on the running build.
    SELECT database_block_size::bigint                          AS bs,
           24::bigint                                           AS hdr,
           4::bigint                                            AS iid,
           ((8 + max_data_alignment - 1) / max_data_alignment)
             * max_data_alignment                               AS gin_special
    FROM pg_control_init()
),
pages AS (
    SELECT c.hdr, c.iid, o.flags, h.lower, h.upper, h.special, h.pagesize
    FROM ctl c
         CROSS JOIN LATERAL generate_series(
               1, pg_relation_size('myschema.myindex', 'main') / c.bs - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page('myschema.myindex', b.blkno::int) AS pg
                             OFFSET 0) AS r
         LEFT JOIN LATERAL page_header(r.pg) AS h ON true
         LEFT JOIN LATERAL gin_page_opaque_info(
               CASE WHEN h.upper > 0 AND h.pagesize = c.bs
                     AND h.pagesize - h.special = c.gin_special
                    THEN r.pg END)           AS o ON true
)
SELECT count(*)                        FILTER (WHERE flags = '{leaf}') AS entry_leaf_pages,
       sum((lower - hdr) / iid)        FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuples,
       sum(special - upper)            FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuple_bytes,
       sum((lower - hdr) / iid)        FILTER (WHERE flags = '{}')     AS internal_downlinks,
       count(*) FILTER (WHERE flags <@ '{leaf,incomplete_split}'::text[]
                          AND (lower < hdr OR (lower - hdr) % iid <> 0))
                                                                       AS malformed_pages,
       count(*) FILTER (WHERE flags IS NULL)                           AS undecoded_pages
FROM pages;
DER_PROBE_SQL
read -r -d '' FSM_CHECK <<'FSM_CHECK_SQL'
SELECT /* wiki_gin_waste_fsm_check */
       (SELECT database_block_size
               - ((28 + max_data_alignment - 1) / max_data_alignment)
                 * max_data_alignment          -- 28 = SizeOfPageHeaderData + sizeof(ItemIdData)
        FROM pg_control_init())                          AS free_page_avail,
       count(*) FILTER (WHERE avail = (SELECT database_block_size
               - ((28 + max_data_alignment - 1) / max_data_alignment)
                 * max_data_alignment FROM pg_control_init())) AS fsm_free_pages,
       count(*)                                          AS blocks
FROM pg_freespace('myschema.myindex');
FSM_CHECK_SQL
read -r -d '' SIZE_BRACKET <<'SIZE_BRACKET_SQL'
SELECT /* wiki_gin_waste_size_bracket */
       pg_relation_size('myschema.myindex','main') / current_setting('block_size')::bigint
       AS blocks_after_census;
SIZE_BRACKET_SQL

# swap <text> <old> <new>: one literal substitution, refused if <old> is absent,
# so a later edit of a published text cannot turn a variant into a copy
swap() {
  local t="$1" old="$2" new="$3"
  case "$t" in *"$old"*) ;; *) die "portability: text to replace not found: $old" ;; esac
  printf '%s' "${t/"$old"/"$new"}"
}
on_index() { local t="$1" ix="$2"; printf '%s' "${t//myschema.myindex/$ix}"; }

stage_portability() {
  local PDB=port MDB=portmeta out="$OUT/19-portability.txt" bs d f zero_path meta_path
  local arm guard census_no_cast census_no_arm probe_no_guard probe_no_cast
  arm="               WHEN h.pagesize = 0                      THEN 'new'   -- all-zero page"
  guard=$'\n'"                                        AND pagesize > 0)"
  census_no_cast=$(swap "$PUB_CENSUS" "b.blkno::int" "b.blkno") || exit 1
  census_no_arm=$(swap "$PUB_CENSUS" "$arm"$'\n' "") || exit 1
  probe_no_guard=$(swap "$PUB_PROBE" "$guard" ")") || exit 1
  probe_no_cast=$(swap "$PUB_PROBE" "b.blkno::int" "b.blkno") || exit 1
  : >"$out"
  sec() { printf '\n=== %s\n' "$*" >>"$out"; }
  for d in "$PDB" "$MDB"; do
    q postgres "DROP DATABASE IF EXISTS $d" >/dev/null || die "DROP DATABASE $d failed"
    q postgres "CREATE DATABASE $d" >/dev/null || die "CREATE DATABASE $d failed"
    for e in pageinspect pgstattuple pg_freespacemap; do
      q "$d" "CREATE EXTENSION $e" >/dev/null || die "CREATE EXTENSION $e failed on $d"
    done
  done
  note "portability fixtures"
  p "$PDB" -q <<'SQL' || die "portability fixtures failed"
SET /* wiki_gin_portability */ statement_timeout = '600s';
SET /* wiki_gin_portability */ lock_timeout = '2s';
-- Disposable fixtures: created and read here, on a cluster the script owns.
CREATE TABLE /* wiki_gin_portability */ pt_ok (id int, tags int[]);
INSERT INTO /* wiki_gin_portability */ pt_ok
SELECT g, ARRAY[g % 300, (g * 7) % 300] FROM generate_series(1, 4000) g;
CREATE INDEX /* wiki_gin_portability */ pt_ok_gin ON pt_ok USING gin (tags) WITH (fastupdate = off);
-- the twin that gets two all-zero blocks appended with the server stopped
CREATE TABLE /* wiki_gin_portability */ pt_zero (id int, tags int[]);
INSERT INTO /* wiki_gin_portability */ pt_zero
SELECT g, ARRAY[g % 300, (g * 7) % 300] FROM generate_series(1, 4000) g;
CREATE INDEX /* wiki_gin_portability */ pt_zero_gin ON pt_zero USING gin (tags) WITH (fastupdate = off);
-- a partitioned GIN index, relkind 'I', which has no storage of its own
CREATE TABLE /* wiki_gin_portability */ pt_part (id int, tags int[]) PARTITION BY RANGE (id);
CREATE TABLE /* wiki_gin_portability */ pt_part_1 PARTITION OF pt_part FOR VALUES FROM (0) TO (100000);
INSERT INTO /* wiki_gin_portability */ pt_part SELECT g, ARRAY[g % 300] FROM generate_series(1, 1000) g;
CREATE INDEX /* wiki_gin_portability */ pt_part_gin ON pt_part USING gin (tags);
-- the table whose concurrent build is made to fail below
CREATE TABLE /* wiki_gin_portability */ pt_inv (id int, v int);
INSERT INTO /* wiki_gin_portability */ pt_inv VALUES (1, 2), (2, 1);
-- the f5 recipe: every row carries all 32 keys
CREATE TABLE /* wiki_gin_portability */ pt_f5 (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_portability */ pt_f5
SELECT i, ARRAY(SELECT generate_series(0, 31)) FROM generate_series(1, 200000) i;
CREATE INDEX /* wiki_gin_portability */ pt_f5_gin ON pt_f5 USING gin (tags) WITH (fastupdate = off);
VACUUM /* wiki_gin_portability */ ANALYZE pt_ok, pt_zero, pt_f5;
SQL
  # CREATE INDEX CONCURRENTLY cannot run inside psql's -c transaction with
  # other statements, and the division by zero is the point: it leaves the
  # index invalid
  pe "$PDB" -c "CREATE INDEX /* wiki_gin_portability */ CONCURRENTLY pt_inv_gin
                ON pt_inv USING gin ((ARRAY[10 / (v - 1)]))" >/dev/null 2>&1
  p "$MDB" -q <<'SQL' || die "portmeta fixtures failed"
SET /* wiki_gin_portability */ statement_timeout = '600s';
SET /* wiki_gin_portability */ lock_timeout = '2s';
CREATE TABLE /* wiki_gin_portability */ pm_ok (id int, tags int[]);
INSERT INTO /* wiki_gin_portability */ pm_ok
SELECT g, ARRAY[g % 300, (g * 7) % 300] FROM generate_series(1, 4000) g;
CREATE INDEX /* wiki_gin_portability */ pm_ok_gin ON pm_ok USING gin (tags) WITH (fastupdate = off);
-- the twin whose block 0, the metapage, is zeroed with the server stopped
CREATE TABLE /* wiki_gin_portability */ pm_meta (id int, tags int[]);
INSERT INTO /* wiki_gin_portability */ pm_meta
SELECT g, ARRAY[g % 300, (g * 7) % 300] FROM generate_series(1, 4000) g;
CREATE INDEX /* wiki_gin_portability */ pm_meta_gin ON pm_meta USING gin (tags) WITH (fastupdate = off);
SQL

  sec "server and extensions"
  q "$PDB" "SELECT version()" >>"$out"
  pe "$PDB" -A -c "SELECT extname, extversion FROM pg_extension ORDER BY 1" >>"$out"

  # every index line is kept: 12.2 prints the page counts on DETAIL lines that
  # carry no index name, so they are read against the INFO line above them
  sec "VACUUM VERBOSE on the f5 recipe: 95% deleted, VACUUM, three xids, VACUUM twice"
  q "$PDB" "DELETE /* wiki_gin_portability */ FROM pt_f5 WHERE id <= 190000" >>"$out"
  for f in 1 2 3; do
    if [ "$f" = 2 ]; then
      q "$PDB" "SELECT txid_current()" >/dev/null
      q "$PDB" "SELECT txid_current()" >/dev/null
      q "$PDB" "SELECT txid_current()" >/dev/null
    fi
    printf -- '--- VACUUM %s\n' "$f" >>"$out"
    pe "$PDB" -c "VACUUM /* wiki_gin_portability */ (VERBOSE) pt_f5" \
      | grep -E 'index "|index row versions|index pages' >>"$out"
  done

  # the two patches, with the server stopped: two all-zero blocks appended to
  # pt_zero_gin, and block 0 of pm_meta_gin zeroed
  bs=$(q "$PDB" "SELECT current_setting('block_size')")
  zero_path="$DATA/$(q "$PDB" "SELECT pg_relation_filepath('pt_zero_gin')")"
  meta_path="$DATA/$(q "$MDB" "SELECT pg_relation_filepath('pm_meta_gin')")"
  pgstop
  dd if=/dev/zero bs="$bs" count=2 status=none >>"$zero_path" || die "append to pt_zero_gin failed"
  dd if=/dev/zero of="$meta_path" bs="$bs" count=1 seek=0 conv=notrunc status=none \
    || die "zeroing block 0 of pm_meta_gin failed"
  pgstart || die "server did not restart after the portability patches"

  sec "the published census, as filed: the ::int cast and the pagesize = 0 arm in place"
  pe "$PDB" -A -c "$PUB_CENSUS" >>"$out"
  sec "the published census without the ::int cast, the pre-edit form"
  pe "$PDB" -A -c "$census_no_cast" >>"$out"
  sec "the published census without the pagesize = 0 arm"
  pe "$PDB" -A -c "$census_no_arm" >>"$out"
  sec "the published census over portmeta, whose pm_meta_gin has an all-zero block 0"
  pe "$MDB" -A -c "$PUB_CENSUS" >>"$out"
  sec "the FSM check on pt_zero_gin, as filed"
  pe "$PDB" -A -c "$(on_index "$FSM_CHECK" pt_zero_gin)" >>"$out"
  sec "the size bracket on pt_zero_gin, as filed"
  pe "$PDB" -A -c "$(on_index "$SIZE_BRACKET" pt_zero_gin)" >>"$out"
  for f in pt_ok_gin pt_zero_gin; do
    sec "the published entry-tuple probe on $f, as filed"
    pe "$PDB" -A -c "$(on_index "$PUB_PROBE" "$f")" >>"$out"
    sec "the published entry-tuple probe on $f without the pagesize > 0 guard"
    pe "$PDB" -A -c "$(on_index "$probe_no_guard" "$f")" >>"$out"
    sec "the published entry-tuple probe on $f without the ::int cast"
    pe "$PDB" -A -c "$(on_index "$probe_no_cast" "$f")" >>"$out"
    sec "the derived entry-tuple probe on $f, as filed"
    pe "$PDB" -A -c "$(on_index "$DER_PROBE" "$f")" >>"$out"
  done

  sec "the three decoders on one all-zero page"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM gin_page_opaque_info(
                     decode(repeat('00', current_setting('block_size')::int), 'hex'))" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM gin_metapage_info(
                     decode(repeat('00', current_setting('block_size')::int), 'hex'))" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ lower, upper, special, pagesize FROM page_header(
                     decode(repeat('00', current_setting('block_size')::int), 'hex'))" >>"$out"
  sec "page_header's column types"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ pg_typeof(lower), pg_typeof(upper),
                          pg_typeof(special), pg_typeof(pagesize)
                   FROM page_header(get_raw_page('pt_ok_gin', 0))" >>"$out"

  sec "refusals"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ indisvalid, indisready, indislive
                   FROM pg_index WHERE indexrelid = 'pt_inv_gin'::regclass" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM pgstatginindex('pt_inv_gin')" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM pgstattuple('pt_inv_gin')" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ get_raw_page('pt_part_gin', 0) IS NOT NULL" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM gin_page_opaque_info(decode('0000', 'hex'))" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM page_header(decode('0000', 'hex'))" >>"$out"

  sec "the two constructs the harness needs"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ pg_current_xact_id() IS NOT NULL AS has_pg_current_xact_id" >>"$out"
  pe "$PDB" -A -c "SHOW autovacuum_vacuum_insert_threshold" >>"$out"
  cat "$out"
}

# ------------------------------------------------------------ report + clean

stage_report() {
  local f
  : >"$OUT/summary.txt"
  {
    printf '=== gin_waste_protocol.sh summary\n'
    printf 'date: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'host: %s\n' "$(uname -srm)"
    printf 'server: %s\n' "$("$BIN/postgres" --version)"
    printf 'pin: %s\n' "$(git -C "$SRC17" rev-parse HEAD 2>/dev/null)"
    printf 'rows: %s  maintenance_work_mem: %s  port: %s\n\n' "$ROWS" "$MWM" "$PORT"
  } >>"$OUT/summary.txt"
  for f in "$OUT"/0*.txt "$OUT"/1*.txt "$OUT"/2*.txt "$OUT"/checks.txt "$OUT"/platform.txt; do
    [ -f "$f" ] || continue
    printf '\n\n########## %s\n\n' "$(basename "$f")" >>"$OUT/summary.txt"
    cat "$f" >>"$OUT/summary.txt"
  done
  note "summary at $OUT/summary.txt ($(wc -l <"$OUT/summary.txt") lines)"
}

stage_clean() {
  if [ -d "$STANDBY" ]; then
    "$BIN/pg_ctl" -D "$STANDBY" -m fast -w stop >/dev/null 2>&1
  fi
  pgstop
  sleep 1
  if [ -f "$DATA/postmaster.pid" ]; then
    note "WARNING: $DATA/postmaster.pid still present"
  else
    note "no postmaster.pid in $DATA"
  fi
  # pgrep -f matches the whole argument list on Linux and on macOS alike, and a
  # postmaster keeps the -D data directory pg_ctl started it with; pgrep -a
  # prints command lines on Linux only.
  if pgrep -f -- "$DATA|$STANDBY" >/dev/null; then
    note "WARNING: a sandbox postgres process survived: $(pgrep -f -- "$DATA|$STANDBY" | tr '\n' ' ')"
  else
    note "no process with $DATA or $STANDBY in its arguments (pgrep -f)"
  fi
  rm -rf "$SANDBOX"
  [ -d "$SANDBOX" ] && note "WARNING: $SANDBOX still exists" || note "sandbox deleted: $SANDBOX"
}

# ------------------------------------------------------------------ dispatch

DEFAULT_STAGES="build check init declare fixtures coverage census decide crosscheck probe standby oracle probe_after score sweep race corrupt portability report"
STAGES="${*:-$DEFAULT_STAGES}"
mkdir -p "$OUT" "$SQLD" 2>/dev/null
note "stages: $STAGES"
for st in $STAGES; do
  case "$st" in
    build|check|init|declare|fixtures|coverage|census|decide|crosscheck|probe|probe_after|oracle|score|sweep|race|corrupt|portability|standby|report|clean)
      note "--- stage $st"
      "stage_$st" || die "stage $st failed" ;;
    *) die "unknown stage: $st" ;;
  esac
done
note "done: $STAGES"
```

### The PostgreSQL 12.2 leg

```bash
#!/usr/bin/env bash
#
# gin_portability_12.sh - the PostgreSQL 12.2 leg of the measurement script for
#   wiki/v17/questions/indexing/gin-index-wasted-space-contrib.md
#
# It builds PostgreSQL 12.2 out of tree from this repository's pinned v12
# checkout and runs the page's portability battery: the four published
# statements with and without the three edits the page made for 12, the
# derived entry-tuple probe, the decoders on an all-zero page, the refusals
# that differ between majors, VACUUM VERBOSE's index report, and the two
# harness constructs 12.2 lacks.  The 17.11 leg, gin_waste_protocol.sh, runs
# the same battery, byte for byte, as its "portability" stage, so the two
# legs' out/19-portability.txt files compare line by line.  Nothing here is
# scored under the v17 protocol.
#
# Everything it creates is disposable.  It runs its own cluster, on a
# non-default port, under its own sandbox, and never touches a cluster it did
# not create.  The "clean" stage stops it and deletes the sandbox.
#
# Usage:
#   bash gin_portability_12.sh                # every stage except clean
#   bash gin_portability_12.sh portability    # selected stages, in order given
#   bash gin_portability_12.sh clean          # stop server, delete sandbox
#
set -uo pipefail

REPO="${REPO:-$PWD}"
SRC12="${SRC12:-$REPO/raw/postgres-12}"
SANDBOX="${SANDBOX:-$REPO/.wiki-runtime/tmp/ginp12}"
JOBS="${JOBS:-8}"
PORT="${PORT:-55412}"
STMT_TIMEOUT="${STMT_TIMEOUT:-600s}"
LOCK_TIMEOUT="${LOCK_TIMEOUT:-2s}"

BUILD="$SANDBOX/build"; INST="$SANDBOX/install"; DATA="$SANDBOX/data"
BIN="$INST/bin"; SOCK="$SANDBOX/sock"; OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql"

# Both also append to $OUT/run.log, the stage log, whenever $OUT exists.
note() { local m; m=$(printf '[%s] %s' "$(date +%H:%M:%S)" "$*")
         printf '%s\n' "$m" >&2; [ -d "$OUT" ] && printf '%s\n' "$m" >>"$OUT/run.log"; return 0; }
die()  { local m; m=$(printf '[%s] FATAL: %s' "$(date +%H:%M:%S)" "$*")
         printf '%s\n' "$m" >&2; [ -d "$OUT" ] && printf '%s\n' "$m" >>"$OUT/run.log"; exit 1; }

# psql wrappers.  -X ignores ~/.psqlrc, ON_ERROR_STOP=1 lets no error pass
# silently, and both timeouts are PGC_USERSET, so session-scoped.
p() { local db="$1"; shift
  PGOPTIONS="-c statement_timeout=$STMT_TIMEOUT -c lock_timeout=$LOCK_TIMEOUT" \
  "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$db" "$@"; }
q() { local db="$1"; shift; p "$db" -At -c "$*"; }
# the same, without ON_ERROR_STOP: for the statements whose error text is the
# result being measured (refusals and the pre-edit statements)
pe() { local db="$1"; shift
  PGOPTIONS="-c statement_timeout=$STMT_TIMEOUT -c lock_timeout=$LOCK_TIMEOUT" \
  "$BIN/psql" -X -h "$SOCK" -p "$PORT" -d "$db" "$@" 2>&1; }

pgstart() { "$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w -o "-p $PORT -k $SOCK" start; }
pgstop()  { [ -f "$DATA/postmaster.pid" ] && "$BIN/pg_ctl" -D "$DATA" -m fast -w stop; true; }

# ---------------------------------------------------------------- build stages

stage_build() {
  [ -x "$BIN/postgres" ] && { note "12.2 already built, skipping"; return 0; }
  [ -d "$SRC12" ] || die "no pinned checkout at $SRC12"
  mkdir -p "$BUILD" "$OUT" || die "mkdir failed"
  note "configuring 12.2 out of tree (read-only source at $SRC12)"
  ( cd "$BUILD" && "$SRC12/configure" --prefix="$INST" --enable-debug \
      --without-icu --without-readline --without-zlib ) >"$OUT/configure.log" 2>&1 \
    || die "configure failed, see $OUT/configure.log"
  note "make -j$JOBS"
  make -C "$BUILD" -j"$JOBS" >"$OUT/make.log" 2>&1 || die "make failed, see $OUT/make.log"
  make -C "$BUILD" install >"$OUT/install.log" 2>&1 || die "make install failed"
  note "make -j$JOBS the three contrib modules the battery uses"
  local c
  for c in pageinspect pgstattuple pg_freespacemap; do
    make -C "$BUILD/contrib/$c" -j"$JOBS" install >>"$OUT/contrib.log" 2>&1 \
      || die "contrib $c build failed, see $OUT/contrib.log"
  done
  "$BIN/postgres" --version | tee "$OUT/version.txt"
}

stage_check() {
  note "make check (core) plus the contrib suites the battery's modules ship"
  : >"$OUT/checks.txt"
  make -C "$BUILD" check >"$OUT/check_core.log" 2>&1
  tail -3 "$OUT/check_core.log" | tee -a "$OUT/checks.txt"
  local c
  for c in pageinspect pgstattuple; do
    make -C "$BUILD/contrib/$c" check >"$OUT/check_$c.log" 2>&1
    printf '%s: ' "$c" >>"$OUT/checks.txt"
    tail -3 "$OUT/check_$c.log" | tr -d '\n' | tee -a "$OUT/checks.txt"
    printf '\n' >>"$OUT/checks.txt"
  done
  # pg_freespacemap 1.2 in this tree declares no REGRESS target
  grep -q '^REGRESS' "$SRC12/contrib/pg_freespacemap/Makefile" \
    && note "pg_freespacemap declares a suite; add it to this list" \
    || printf 'pg_freespacemap: no suite, its Makefile declares no REGRESS\n' >>"$OUT/checks.txt"
  cat "$OUT/checks.txt"
}

stage_init() {
  pgstop
  rm -rf "$DATA" "$SOCK"
  mkdir -p "$SOCK" "$OUT" "$SQLD" || die "mkdir failed"
  "$BIN/initdb" -D "$DATA" --locale=C --encoding=UTF8 >"$OUT/initdb.log" 2>&1 \
    || die "initdb failed, see $OUT/initdb.log"
  # The same cluster settings as the 17.11 leg, minus the standby's: all are
  # PGC_SIGHUP or PGC_POSTMASTER, so they go in postgresql.conf before the
  # first start.
  cat >>"$DATA/postgresql.conf" <<CONF
autovacuum = off
fsync = off
shared_buffers = 256MB
max_wal_size = 2GB
logging_collector = off
log_min_messages = warning
CONF
  pgstart || die "server did not start"
  q postgres "SELECT version()" | tee "$OUT/server_version.txt"
  p postgres -c "SELECT /* wiki_gin_platform */ * FROM pg_control_init()" >"$OUT/platform.txt"
  p postgres -c "SELECT /* wiki_gin_platform */ name, setting, source
                 FROM pg_settings
                 WHERE name IN ('block_size','autovacuum','fsync','shared_buffers')
                 ORDER BY 1" >>"$OUT/platform.txt"
  cat "$OUT/platform.txt"
}

# ------------------------------------------------------- portability stage
#
# Outside the protocol, and the same text in both leg scripts: the 17.11 leg
# runs it as its "portability" stage, the 12.2 leg as its only measuring stage,
# so the two out/19-portability.txt files compare line by line.  It carries the
# page's four published statements and the derived entry-tuple probe verbatim,
# runs them with and without the three edits the page made for PostgreSQL 12,
# and adds the decoders' answers on an all-zero page, the refusals that differ
# between majors, VACUUM VERBOSE's index report and the two harness constructs
# 12.2 lacks.  It builds everything it reads in two databases of its own,
# "port" and "portmeta"; every object in them is disposable.

read -r -d '' PUB_CENSUS <<'PUB_CENSUS_SQL'
WITH /* wiki_gin_waste_census */ gin_idx AS (
    SELECT c.oid                                  AS idx,
           c.oid::regclass::text                  AS idx_name,
           pg_relation_size(c.oid, 'main')         AS main_bytes,
           current_setting('block_size')::bigint   AS bs
    FROM pg_class c
         JOIN pg_am a    ON a.oid = c.relam
         JOIN pg_index x ON x.indexrelid = c.oid
    WHERE a.amname = 'gin'
      AND c.relkind = 'i'            -- 'I' (partitioned) has no storage
      AND x.indisvalid               -- an invalid index is still readable, see notes
      AND c.relpersistence <> 't'    -- another session's temp index is refused
),
meta AS (
    SELECT g.*, m.version, m.n_pending_pages, m.n_pending_tuples,
           m.n_total_pages, m.n_entry_pages, m.n_data_pages
    FROM gin_idx g
         CROSS JOIN LATERAL gin_metapage_info(get_raw_page(g.idx_name, 0)) m
),
pages AS (
    SELECT g.idx,
           CASE
               WHEN h.pagesize = 0                      THEN 'new'   -- all-zero page
               WHEN o.flags IS NULL                     THEN 'new'
               WHEN o.flags @> '{meta}'                 THEN 'meta'
               WHEN o.flags @> '{deleted}'              THEN 'deleted'
               WHEN o.flags @> '{list}'                 THEN 'pending'
               WHEN o.flags @> '{data,leaf,compressed}' THEN 'data_leaf'
               WHEN o.flags @> '{data,leaf}'            THEN 'data_leaf_uncompressed'
               WHEN o.flags @> '{data}'                 THEN 'data_internal'
               ELSE                                          'entry'
           END                                          AS page_class,
           COALESCE(h.upper - h.lower, 0)               AS slack
    FROM gin_idx g
         CROSS JOIN LATERAL generate_series(1, g.main_bytes / g.bs - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page(g.idx_name, b.blkno::int) AS pg
                             OFFSET 0) AS r          -- read each page exactly once
         LEFT JOIN LATERAL gin_page_opaque_info(r.pg) AS o ON true
         LEFT JOIN LATERAL page_header(r.pg)          AS h ON true
),
census AS (
    SELECT idx,
           count(*) FILTER (WHERE page_class = 'entry')                  AS entry_pages,
           count(*) FILTER (WHERE page_class = 'data_leaf')              AS data_leaf_pages,
           count(*) FILTER (WHERE page_class = 'data_internal')          AS data_internal_pages,
           count(*) FILTER (WHERE page_class = 'data_leaf_uncompressed') AS uncompressed_pages,
           count(*) FILTER (WHERE page_class = 'pending')                AS pending_pages,
           count(*) FILTER (WHERE page_class = 'deleted')                AS deleted_pages,
           count(*) FILTER (WHERE page_class = 'new')                    AS new_pages,
           count(*) FILTER (WHERE page_class = 'meta')                   AS stray_meta_pages,
           COALESCE(sum(slack) FILTER (WHERE page_class = 'entry'), 0)   AS entry_slack,
           COALESCE(sum(slack) FILTER (WHERE page_class IN ('data_leaf',
                                            'data_internal')), 0)        AS data_slack
    FROM pages
    GROUP BY idx
)
SELECT m.idx_name                                       AS index_name,
       m.version                                        AS gin_version,
       m.main_bytes                                     AS main_fork_bytes,
       m.main_bytes / m.bs                              AS blocks,
       c.entry_pages, c.data_leaf_pages, c.data_internal_pages,
       c.uncompressed_pages, c.pending_pages, c.deleted_pages, c.new_pages,
       (c.deleted_pages + c.new_pages) * m.bs           AS whole_page_waste_bytes,
       round(100.0 * (c.deleted_pages + c.new_pages) * m.bs
             / nullif(m.main_bytes, 0), 2)              AS whole_page_waste_pct,
       CASE WHEN m.version = 2 THEN c.entry_slack + c.data_slack END
                                                        AS live_page_slack_bytes,
       CASE WHEN m.version = 2
            THEN round(100.0 * (c.entry_slack + c.data_slack)
                       / nullif(m.main_bytes, 0), 2) END AS live_page_slack_pct,
       CASE WHEN m.version = 2
            THEN round(100.0 * ((c.deleted_pages + c.new_pages) * m.bs
                                + c.entry_slack + c.data_slack)
                       / nullif(m.main_bytes, 0), 2) END AS bloat_pct,
       c.entry_slack, c.data_slack,
       c.pending_pages * m.bs                           AS pending_bytes,
       round(100.0 * c.pending_pages * m.bs
             / nullif(m.main_bytes, 0), 2)              AS pending_pct,
       m.main_bytes - (c.deleted_pages + c.new_pages + c.pending_pages) * m.bs
                    - c.entry_slack - c.data_slack      AS payload_bytes,
       m.n_pending_pages                                AS meta_pending_pages,
       m.n_entry_pages                                  AS meta_entry_pages,
       m.n_data_pages                                   AS meta_data_pages,
       m.n_total_pages                                  AS meta_total_pages,
       1 + c.entry_pages + c.data_leaf_pages + c.data_internal_pages
         + c.uncompressed_pages + c.pending_pages + c.deleted_pages
         + c.new_pages + c.stray_meta_pages             AS census_total_pages
FROM meta m JOIN census c ON c.idx = m.idx
ORDER BY 1;
PUB_CENSUS_SQL
read -r -d '' PUB_PROBE <<'PUB_PROBE_SQL'
WITH /* wiki_gin_entry_probe */ pages AS (
    SELECT o.flags, h.lower, h.upper, h.special, h.pagesize
    FROM generate_series(1, pg_relation_size('myschema.myindex','main') / 8192 - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page('myschema.myindex', b.blkno::int) AS pg
                             OFFSET 0) AS r
         LEFT JOIN LATERAL gin_page_opaque_info(r.pg) AS o ON true
         LEFT JOIN LATERAL page_header(r.pg)          AS h ON true
)
SELECT count(*)                 FILTER (WHERE flags = '{leaf}') AS entry_leaf_pages,
       sum((lower - 24) / 4)    FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuples,
       sum(special - upper)     FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuple_bytes,
       sum((lower - 24) / 4)    FILTER (WHERE flags = '{}'
                                        AND pagesize > 0)       AS internal_downlinks
FROM pages;
PUB_PROBE_SQL
read -r -d '' DER_PROBE <<'DER_PROBE_SQL'
WITH /* wiki_gin_entry_probe_derived */ ctl AS (
    -- bs and al are build-dependent and come from pg_control_init().  hdr and
    -- iid are page-format constants: SizeOfPageHeaderData is
    -- offsetof(PageHeaderData, pd_linp) over fixed-width fields, and ItemIdData
    -- is three bit-fields totalling 32 bits.  The layout probe measures all
    -- four on the running build.
    SELECT database_block_size::bigint                          AS bs,
           24::bigint                                           AS hdr,
           4::bigint                                            AS iid,
           ((8 + max_data_alignment - 1) / max_data_alignment)
             * max_data_alignment                               AS gin_special
    FROM pg_control_init()
),
pages AS (
    SELECT c.hdr, c.iid, o.flags, h.lower, h.upper, h.special, h.pagesize
    FROM ctl c
         CROSS JOIN LATERAL generate_series(
               1, pg_relation_size('myschema.myindex', 'main') / c.bs - 1) AS b(blkno)
         CROSS JOIN LATERAL (SELECT get_raw_page('myschema.myindex', b.blkno::int) AS pg
                             OFFSET 0) AS r
         LEFT JOIN LATERAL page_header(r.pg) AS h ON true
         LEFT JOIN LATERAL gin_page_opaque_info(
               CASE WHEN h.upper > 0 AND h.pagesize = c.bs
                     AND h.pagesize - h.special = c.gin_special
                    THEN r.pg END)           AS o ON true
)
SELECT count(*)                        FILTER (WHERE flags = '{leaf}') AS entry_leaf_pages,
       sum((lower - hdr) / iid)        FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuples,
       sum(special - upper)            FILTER (WHERE flags = '{leaf}') AS entry_leaf_tuple_bytes,
       sum((lower - hdr) / iid)        FILTER (WHERE flags = '{}')     AS internal_downlinks,
       count(*) FILTER (WHERE flags <@ '{leaf,incomplete_split}'::text[]
                          AND (lower < hdr OR (lower - hdr) % iid <> 0))
                                                                       AS malformed_pages,
       count(*) FILTER (WHERE flags IS NULL)                           AS undecoded_pages
FROM pages;
DER_PROBE_SQL
read -r -d '' FSM_CHECK <<'FSM_CHECK_SQL'
SELECT /* wiki_gin_waste_fsm_check */
       (SELECT database_block_size
               - ((28 + max_data_alignment - 1) / max_data_alignment)
                 * max_data_alignment          -- 28 = SizeOfPageHeaderData + sizeof(ItemIdData)
        FROM pg_control_init())                          AS free_page_avail,
       count(*) FILTER (WHERE avail = (SELECT database_block_size
               - ((28 + max_data_alignment - 1) / max_data_alignment)
                 * max_data_alignment FROM pg_control_init())) AS fsm_free_pages,
       count(*)                                          AS blocks
FROM pg_freespace('myschema.myindex');
FSM_CHECK_SQL
read -r -d '' SIZE_BRACKET <<'SIZE_BRACKET_SQL'
SELECT /* wiki_gin_waste_size_bracket */
       pg_relation_size('myschema.myindex','main') / current_setting('block_size')::bigint
       AS blocks_after_census;
SIZE_BRACKET_SQL

# swap <text> <old> <new>: one literal substitution, refused if <old> is absent,
# so a later edit of a published text cannot turn a variant into a copy
swap() {
  local t="$1" old="$2" new="$3"
  case "$t" in *"$old"*) ;; *) die "portability: text to replace not found: $old" ;; esac
  printf '%s' "${t/"$old"/"$new"}"
}
on_index() { local t="$1" ix="$2"; printf '%s' "${t//myschema.myindex/$ix}"; }

stage_portability() {
  local PDB=port MDB=portmeta out="$OUT/19-portability.txt" bs d f zero_path meta_path
  local arm guard census_no_cast census_no_arm probe_no_guard probe_no_cast
  arm="               WHEN h.pagesize = 0                      THEN 'new'   -- all-zero page"
  guard=$'\n'"                                        AND pagesize > 0)"
  census_no_cast=$(swap "$PUB_CENSUS" "b.blkno::int" "b.blkno") || exit 1
  census_no_arm=$(swap "$PUB_CENSUS" "$arm"$'\n' "") || exit 1
  probe_no_guard=$(swap "$PUB_PROBE" "$guard" ")") || exit 1
  probe_no_cast=$(swap "$PUB_PROBE" "b.blkno::int" "b.blkno") || exit 1
  : >"$out"
  sec() { printf '\n=== %s\n' "$*" >>"$out"; }
  for d in "$PDB" "$MDB"; do
    q postgres "DROP DATABASE IF EXISTS $d" >/dev/null || die "DROP DATABASE $d failed"
    q postgres "CREATE DATABASE $d" >/dev/null || die "CREATE DATABASE $d failed"
    for e in pageinspect pgstattuple pg_freespacemap; do
      q "$d" "CREATE EXTENSION $e" >/dev/null || die "CREATE EXTENSION $e failed on $d"
    done
  done
  note "portability fixtures"
  p "$PDB" -q <<'SQL' || die "portability fixtures failed"
SET /* wiki_gin_portability */ statement_timeout = '600s';
SET /* wiki_gin_portability */ lock_timeout = '2s';
-- Disposable fixtures: created and read here, on a cluster the script owns.
CREATE TABLE /* wiki_gin_portability */ pt_ok (id int, tags int[]);
INSERT INTO /* wiki_gin_portability */ pt_ok
SELECT g, ARRAY[g % 300, (g * 7) % 300] FROM generate_series(1, 4000) g;
CREATE INDEX /* wiki_gin_portability */ pt_ok_gin ON pt_ok USING gin (tags) WITH (fastupdate = off);
-- the twin that gets two all-zero blocks appended with the server stopped
CREATE TABLE /* wiki_gin_portability */ pt_zero (id int, tags int[]);
INSERT INTO /* wiki_gin_portability */ pt_zero
SELECT g, ARRAY[g % 300, (g * 7) % 300] FROM generate_series(1, 4000) g;
CREATE INDEX /* wiki_gin_portability */ pt_zero_gin ON pt_zero USING gin (tags) WITH (fastupdate = off);
-- a partitioned GIN index, relkind 'I', which has no storage of its own
CREATE TABLE /* wiki_gin_portability */ pt_part (id int, tags int[]) PARTITION BY RANGE (id);
CREATE TABLE /* wiki_gin_portability */ pt_part_1 PARTITION OF pt_part FOR VALUES FROM (0) TO (100000);
INSERT INTO /* wiki_gin_portability */ pt_part SELECT g, ARRAY[g % 300] FROM generate_series(1, 1000) g;
CREATE INDEX /* wiki_gin_portability */ pt_part_gin ON pt_part USING gin (tags);
-- the table whose concurrent build is made to fail below
CREATE TABLE /* wiki_gin_portability */ pt_inv (id int, v int);
INSERT INTO /* wiki_gin_portability */ pt_inv VALUES (1, 2), (2, 1);
-- the f5 recipe: every row carries all 32 keys
CREATE TABLE /* wiki_gin_portability */ pt_f5 (id int primary key, tags int[]);
INSERT INTO /* wiki_gin_portability */ pt_f5
SELECT i, ARRAY(SELECT generate_series(0, 31)) FROM generate_series(1, 200000) i;
CREATE INDEX /* wiki_gin_portability */ pt_f5_gin ON pt_f5 USING gin (tags) WITH (fastupdate = off);
VACUUM /* wiki_gin_portability */ ANALYZE pt_ok, pt_zero, pt_f5;
SQL
  # CREATE INDEX CONCURRENTLY cannot run inside psql's -c transaction with
  # other statements, and the division by zero is the point: it leaves the
  # index invalid
  pe "$PDB" -c "CREATE INDEX /* wiki_gin_portability */ CONCURRENTLY pt_inv_gin
                ON pt_inv USING gin ((ARRAY[10 / (v - 1)]))" >/dev/null 2>&1
  p "$MDB" -q <<'SQL' || die "portmeta fixtures failed"
SET /* wiki_gin_portability */ statement_timeout = '600s';
SET /* wiki_gin_portability */ lock_timeout = '2s';
CREATE TABLE /* wiki_gin_portability */ pm_ok (id int, tags int[]);
INSERT INTO /* wiki_gin_portability */ pm_ok
SELECT g, ARRAY[g % 300, (g * 7) % 300] FROM generate_series(1, 4000) g;
CREATE INDEX /* wiki_gin_portability */ pm_ok_gin ON pm_ok USING gin (tags) WITH (fastupdate = off);
-- the twin whose block 0, the metapage, is zeroed with the server stopped
CREATE TABLE /* wiki_gin_portability */ pm_meta (id int, tags int[]);
INSERT INTO /* wiki_gin_portability */ pm_meta
SELECT g, ARRAY[g % 300, (g * 7) % 300] FROM generate_series(1, 4000) g;
CREATE INDEX /* wiki_gin_portability */ pm_meta_gin ON pm_meta USING gin (tags) WITH (fastupdate = off);
SQL

  sec "server and extensions"
  q "$PDB" "SELECT version()" >>"$out"
  pe "$PDB" -A -c "SELECT extname, extversion FROM pg_extension ORDER BY 1" >>"$out"

  # every index line is kept: 12.2 prints the page counts on DETAIL lines that
  # carry no index name, so they are read against the INFO line above them
  sec "VACUUM VERBOSE on the f5 recipe: 95% deleted, VACUUM, three xids, VACUUM twice"
  q "$PDB" "DELETE /* wiki_gin_portability */ FROM pt_f5 WHERE id <= 190000" >>"$out"
  for f in 1 2 3; do
    if [ "$f" = 2 ]; then
      q "$PDB" "SELECT txid_current()" >/dev/null
      q "$PDB" "SELECT txid_current()" >/dev/null
      q "$PDB" "SELECT txid_current()" >/dev/null
    fi
    printf -- '--- VACUUM %s\n' "$f" >>"$out"
    pe "$PDB" -c "VACUUM /* wiki_gin_portability */ (VERBOSE) pt_f5" \
      | grep -E 'index "|index row versions|index pages' >>"$out"
  done

  # the two patches, with the server stopped: two all-zero blocks appended to
  # pt_zero_gin, and block 0 of pm_meta_gin zeroed
  bs=$(q "$PDB" "SELECT current_setting('block_size')")
  zero_path="$DATA/$(q "$PDB" "SELECT pg_relation_filepath('pt_zero_gin')")"
  meta_path="$DATA/$(q "$MDB" "SELECT pg_relation_filepath('pm_meta_gin')")"
  pgstop
  dd if=/dev/zero bs="$bs" count=2 status=none >>"$zero_path" || die "append to pt_zero_gin failed"
  dd if=/dev/zero of="$meta_path" bs="$bs" count=1 seek=0 conv=notrunc status=none \
    || die "zeroing block 0 of pm_meta_gin failed"
  pgstart || die "server did not restart after the portability patches"

  sec "the published census, as filed: the ::int cast and the pagesize = 0 arm in place"
  pe "$PDB" -A -c "$PUB_CENSUS" >>"$out"
  sec "the published census without the ::int cast, the pre-edit form"
  pe "$PDB" -A -c "$census_no_cast" >>"$out"
  sec "the published census without the pagesize = 0 arm"
  pe "$PDB" -A -c "$census_no_arm" >>"$out"
  sec "the published census over portmeta, whose pm_meta_gin has an all-zero block 0"
  pe "$MDB" -A -c "$PUB_CENSUS" >>"$out"
  sec "the FSM check on pt_zero_gin, as filed"
  pe "$PDB" -A -c "$(on_index "$FSM_CHECK" pt_zero_gin)" >>"$out"
  sec "the size bracket on pt_zero_gin, as filed"
  pe "$PDB" -A -c "$(on_index "$SIZE_BRACKET" pt_zero_gin)" >>"$out"
  for f in pt_ok_gin pt_zero_gin; do
    sec "the published entry-tuple probe on $f, as filed"
    pe "$PDB" -A -c "$(on_index "$PUB_PROBE" "$f")" >>"$out"
    sec "the published entry-tuple probe on $f without the pagesize > 0 guard"
    pe "$PDB" -A -c "$(on_index "$probe_no_guard" "$f")" >>"$out"
    sec "the published entry-tuple probe on $f without the ::int cast"
    pe "$PDB" -A -c "$(on_index "$probe_no_cast" "$f")" >>"$out"
    sec "the derived entry-tuple probe on $f, as filed"
    pe "$PDB" -A -c "$(on_index "$DER_PROBE" "$f")" >>"$out"
  done

  sec "the three decoders on one all-zero page"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM gin_page_opaque_info(
                     decode(repeat('00', current_setting('block_size')::int), 'hex'))" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM gin_metapage_info(
                     decode(repeat('00', current_setting('block_size')::int), 'hex'))" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ lower, upper, special, pagesize FROM page_header(
                     decode(repeat('00', current_setting('block_size')::int), 'hex'))" >>"$out"
  sec "page_header's column types"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ pg_typeof(lower), pg_typeof(upper),
                          pg_typeof(special), pg_typeof(pagesize)
                   FROM page_header(get_raw_page('pt_ok_gin', 0))" >>"$out"

  sec "refusals"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ indisvalid, indisready, indislive
                   FROM pg_index WHERE indexrelid = 'pt_inv_gin'::regclass" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM pgstatginindex('pt_inv_gin')" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM pgstattuple('pt_inv_gin')" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ get_raw_page('pt_part_gin', 0) IS NOT NULL" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM gin_page_opaque_info(decode('0000', 'hex'))" >>"$out"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ * FROM page_header(decode('0000', 'hex'))" >>"$out"

  sec "the two constructs the harness needs"
  pe "$PDB" -A -c "SELECT /* wiki_gin_portability */ pg_current_xact_id() IS NOT NULL AS has_pg_current_xact_id" >>"$out"
  pe "$PDB" -A -c "SHOW autovacuum_vacuum_insert_threshold" >>"$out"
  cat "$out"
}

# ------------------------------------------------------------ report + clean

stage_report() {
  local f
  : >"$OUT/summary.txt"
  {
    printf '=== gin_portability_12.sh summary\n'
    printf 'date: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'host: %s\n' "$(uname -srm)"
    printf 'server: %s\n' "$("$BIN/postgres" --version)"
    printf 'pin: %s\n' "$(git -C "$SRC12" rev-parse HEAD 2>/dev/null)"
    printf 'port: %s\n\n' "$PORT"
  } >>"$OUT/summary.txt"
  for f in "$OUT"/1*.txt "$OUT"/checks.txt "$OUT"/platform.txt; do
    [ -f "$f" ] || continue
    printf '\n\n########## %s\n\n' "$(basename "$f")" >>"$OUT/summary.txt"
    cat "$f" >>"$OUT/summary.txt"
  done
  note "summary at $OUT/summary.txt ($(wc -l <"$OUT/summary.txt") lines)"
}

stage_clean() {
  pgstop
  sleep 1
  if [ -f "$DATA/postmaster.pid" ]; then
    note "WARNING: $DATA/postmaster.pid still present"
  else
    note "no postmaster.pid in $DATA"
  fi
  # pgrep -f matches the whole argument list on Linux and on macOS alike, and a
  # postmaster keeps the -D data directory pg_ctl started it with.
  if pgrep -f -- "$DATA" >/dev/null; then
    note "WARNING: a sandbox postgres process survived: $(pgrep -f -- "$DATA" | tr '\n' ' ')"
  else
    note "no process with $DATA in its arguments (pgrep -f)"
  fi
  rm -rf "$SANDBOX"
  [ -d "$SANDBOX" ] && note "WARNING: $SANDBOX still exists" || note "sandbox deleted: $SANDBOX"
}

# ------------------------------------------------------------------ dispatch

DEFAULT_STAGES="build check init portability report"
STAGES="${*:-$DEFAULT_STAGES}"
mkdir -p "$OUT" "$SQLD" 2>/dev/null
note "stages: $STAGES"
for st in $STAGES; do
  case "$st" in
    build|check|init|portability|report|clean)
      note "--- stage $st"
      "stage_$st" || die "stage $st failed" ;;
    *) die "unknown stage: $st" ;;
  esac
done
note "done: $STAGES"
```

## Context Reviewed

- **2026-09-24 pass:** re-read at the pin the source behind every new or reworded
  claim. That is the index-cleanup gate and the three ways it is cleared
  ([vacuum.c:2155-2178](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2155-L2178),
  [vacuumlazy.c:392-401](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L401),
  [vacuumlazy.c:1064-1066](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1064-L1066),
  [vacuumlazy.c:2323-2335](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2335)),
  the index-vacuum bypass, the cleanup-lock fallback and its VERBOSE report, the
  backup checkpoint's `spread` default and `page_header`'s decode path. It read the
  history of the five commits the 12.2 section cites: master commits in either
  checkout, the 12-branch back-patches `5378d55cb2f` and `975ae05537` only in the v12
  one, each with its earliest tag. Then three full passes on Darwin 27 arm64 with
  Apple clang 21: the filed script unchanged, the edited script before its report
  files, and the recorded run of the script filed now. The 12.2 leg ran from an
  empty sandbox as well. The recorded run's scored output files were diffed one by
  one against the baseline pass's, and both fenced scripts were compared byte for
  byte with the files that ran. The concept page
  [Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md)
  was read, as changed on 2026-09-24, and not edited.
- **2026-09-16 review:** re-read every source citation the page carried at review
  time against the pin - **605 citations over 284 distinct file-and-line ranges in
  79 files**, and **607 over 283** once this pass had added two and merged one - by
  dumping each cited range out of `raw/postgres-17/` and checking it against the
  claim it backs. Every range is in bounds, none crosses a version, and every
  one supports its claim; the two repo-wide checks were re-run too
  (`pages_deleted` is incremented in exactly two places under
  `src/backend/access/gin/`, and `RelationTruncate`/`smgrtruncate` have zero hits
  there). Four label-level defects came out of it and are fixed: a `PageAddItem`
  credited to `entryPreparePage` when it belongs to `entryExecPlaceToPage`, the
  same symbol in `## Source References`, one function cited as both `L507-L576`
  and `L507-L577`, and a `## Contents`-adjacent Markdown heading with no blank
  line before it. Then rebuilt 17.11 out of tree from the pin and ran the whole
  published programme **twice**; see [Measurement Script](#measurement-script) and
  [The last run](#the-last-run).
- **2026-09-15 protocol re-run:** re-read the maintenance, census and stand-in
  source chain in the pinned checkout before drafting - `vacuum()`'s
  vacuum-then-analyze order, `analyze_rel`'s ANALYZE-only cleanup gate and its
  per-index `vac_update_relstats` call, `ginvacuumcleanup`'s `analyze_only` branch
  and the `ginInsertCleanup` signature behind it, `gin_clean_pending_list`'s four
  refusals, `relation_needs_vacanalyze`'s effective-value selection, clamp,
  short circuit and three verdicts, `do_autovacuum`'s relkind filter and its
  `pg_statistic` exception, `extract_autovac_opts` and `AutoVacOpts`,
  `pgstat_report_analyze`'s reset, `pgstat_report_stat`'s flush interval, the
  `pg_stat_all_tables` counter columns, `pg_stat_force_next_flush` and
  `pg_stat_clear_snapshot` in `pg_proc.dat`, `stats_fetch_consistency`, the shipped
  `stats.sql` force-flush sequence, `lazy_cleanup_all_indexes`'s `estimated_count`
  and the `update_index_statistics` skip it drives, and the six autovacuum
  reloptions and five GUCs with their contexts. Then built 17.11 out of tree from
  the pin and ran the whole programme; see
  [Measurement Script](#measurement-script).
- **2026-09-05 plan review:** rechecked the seven findings in
  [Plan review](#plan-review) against the pinned v17 implementation, and audited
  the original six steps plus the published census and cross-check statements.
  No database server was built or started; the historical observations below
  were not rerun. SQL code blocks were preserved during this review.
- **Caller and data-structure context for this review:** core `ginhandler`
  installs `ginbulkdelete` and `ginvacuumcleanup`; the index AM dispatcher calls
  those callbacks, with `IndexVacuumInfo` supplied by the heap vacuum path.
  Contrib readers and GIN use the shared `GinPageOpaqueData`, `GinMetaPageData`,
  and page-header definitions, rather than an extension-specific page layout
  ([ginutil.c#ginhandler](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L36-L69),
  [indexam.c:748-777](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L748-L777),
  [vacuumlazy.c#lazy_cleanup_one_index](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2469-L2499),
  [ginfuncs.c:10-22](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L10-L22),
  [gin_private.h:13-21](../../../../raw/postgres-17/src/include/access/gin_private.h#L13-L21),
  [ginblock.h:30-138](../../../../raw/postgres-17/src/include/access/ginblock.h#L30-L138),
  [bufpage.h#PageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L155-L168)).
- **Build and SQL interfaces for this review:** the `pageinspect` build links
  `ginfuncs` and `rawpage` and installs the extension SQL upgrades. The core
  catalog-header build generates `*_d.h`, including the catalog header included
  by `gin_private.h`; those headers are build products, not evidence files to
  manufacture in `raw/`. Block size comes from configuration, and the extension's
  SQL version controls argument/result widths: `get_raw_page` takes `int8` in
  1.9, while `page_header` exposes integer offsets from 1.10. The source-only
  revision requires no core catalog, parser, or header edits
  ([pageinspect/Makefile](../../../../raw/postgres-17/contrib/pageinspect/Makefile#L3-L35),
  [catalog/Makefile:86-88](../../../../raw/postgres-17/src/include/catalog/Makefile#L86-L88),
  [catalog/Makefile:126-143](../../../../raw/postgres-17/src/include/catalog/Makefile#L126-L143),
  [gin_private.h:13-21](../../../../raw/postgres-17/src/include/access/gin_private.h#L13-L21),
  [configure.ac:267-288](../../../../raw/postgres-17/configure.ac#L267-L288),
  [pageinspect--1.8--1.9.sql:46-58](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L46-L58),
  [pageinspect--1.9--1.10.sql:10-21](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.9--1.10.sql#L10-L21)).
- **Additional boundaries reviewed:** maintenance-option parsing and callback
  suppression, core function signatures, source GUC contexts, per-call raw-page
  locks, the decoder's unknown-bit handling, the planner's subquery pull-up
  restrictions, and the shipped contrib tests. The `SET`, `VACUUM (...)`, and
  `REINDEX` grammar and the core function catalog entries were checked; no new
  executable SQL is introduced by this review
  ([gram.y:1663-1681](../../../../raw/postgres-17/src/backend/parser/gram.y#L1663-L1681),
  [gram.y#ReindexStmt](../../../../raw/postgres-17/src/backend/parser/gram.y#L9189-L9202),
  [gram.y:11821-11829](../../../../raw/postgres-17/src/backend/parser/gram.y#L11821-L11829),
  [pg_proc.dat:7487-7495](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7487-L7495),
  [pg_proc.dat:9513-9516](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L9513-L9516),
  [pg_proc.dat:11989-11996](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L11989-L11996)).
- Contrib limits: `pgstat_relation`'s AM switch, `pgstatginindex_internal`, the
  `GinIndexStat` struct, the 1.5 grant script, and the `BAS_BULKREAD` strategy
  that `pgstattuple`/`pgstatindex` use and `pageinspect` does not.
- `pageinspect`: `get_raw_page_internal`, `get_page_from_raw`, `page_header`, all
  three GIN functions, the `page_header` signature added in 1.10, and the shipped
  GIN test including its all-zero-page expectations.
- `pg_freespacemap`: the C function, both SQL forms, the 1.2 grants, and the
  documentation's index-specific note.
- GIN on-disk structures: `GinPageOpaqueData` and every flag, `GinMetaPageData`,
  the page-type and delete-xid macros, `GinMaxItemSize`, the posting-tree layout
  comment, `GinDataLeafPageGetFreeSpace`, and the `pd_lower` trust note.
- GIN vacuum: `ginbulkdelete`, `ginvacuumcleanup`, `GinPageIsRecyclable`,
  `ginDeletePage`, `ginScanToDelete`, `ginVacuumPostingTreeLeaves`, and the
  README's page-deletion and entry-tree sections.
- GIN fast update: `writeListPage`, `makeSublist`, `ginHeapTupleFastInsert`,
  `shiftList`, `ginInsertCleanup`, `gin_clean_pending_list`.
- Page and FSM primitives: `PageIsNew`, `PageGetFreeSpace`,
  `PageGetExactFreeSpace`, `indexfsm.c` in full, the FSM category arithmetic,
  `GetRecordedFreeSpace`, and `MaxHeapTupleSize`.
- Visibility: `GlobalVisHorizonKindForRel`, `GlobalVisCheckRemovableXid`.
- Adjacent code: `GinNewBuffer`, `GinInitMetabuffer`, `ginUpdateStats`,
  `entryIsEnoughSpace`, `entrySplitPage`, `GinDataPageAddPostingItem`,
  `dataPlaceToPageLeaf`, and `vacuumlazy.c`'s per-index verbose line.
- Docs and GUCs: `pgstattuple.sgml`, `pageinspect.sgml`, `pgfreespacemap.sgml`,
  `gin.sgml` fast-update and tips sections, `func.sgml` for `pg_relation_size` and
  `gin_clean_pending_list`, and `gin_pending_list_limit`, `statement_timeout` and
  `lock_timeout` in `guc_tables.c`.
- Test surfaces: the `pageinspect` GIN test, the `pg_freespacemap` test, and the
  `amcheck` SQL scripts that show no GIN verifier exists.
- Live measurements on an isolated 17.11 cluster built from the pinned checkout by
  a VPATH build that leaves `raw/` untouched (`.wiki-runtime/tmp/ginw2/`, port
  55432, `autovacuum = off`, `fsync = off`, `shared_buffers = 256MB`): the seven
  fixtures published above, a partitioned GIN index, an invalid GIN index, another
  session's temp GIN index, a `pg_stat_scan_tables`-only role, a physical standby
  built with `pg_basebackup` for the recovery refusals, `REINDEX INDEX` ground
  truth, `EXPLAIN (ANALYZE, BUFFERS)` read counts, cold/warm timings across a
  restart, and both timeout cancellations. The first run's sandbox
  (`.wiki-runtime/tmp/ginw`) and the 17.11 install it borrowed no longer exist,
  which is why the server was rebuilt and the fixtures republished. **`ginw2` no
  longer exists either**: it was deleted on 2026-08-26 at the user's instruction,
  so reproducing anything below means rebuilding 17.11 from `raw/postgres-17/`
  again. Every fixture needed to do that is published above as SQL, and the
  open-questions pass already proved that path returns the filed numbers byte for
  byte.
- Follow-up experiments on the same cluster, with `pg_trgm` 1.6, `btree_gin` 1.3
  and `pg_buffercache` 1.5 additionally installed from the pinned tree: a held
  `REPEATABLE READ` snapshot against page recyclability, `REINDEX INDEX
  CONCURRENTLY` as an alternative ground truth, 25 censuses of a 1,000,000-row
  index under concurrent inserts and flushes, an autoanalyze-only pending-list
  flush with `autovacuum = on` reloaded, five other opclasses and index shapes
  built then churned, `pg_buffercache` accounting at `shared_buffers = 64MB`, and
  two `pg_ctl stop -m immediate` crashes during a bulk insert.
- Review re-verification: all 119 source citations the page carried at review time
  re-read against the pinned checkout, plus three repo-wide checks — `RelationTruncate` and
  `smgrtruncate` have zero hits under `src/backend/access/gin/`, `pages_deleted`
  is incremented in exactly two places
  ([ginvacuum.c:234-235](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L234-L235),
  [ginfast.c:590-591](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L590-L591)), and
  `contrib/amcheck` declares only `bt_index_check`, `bt_index_parent_check` and
  `verify_heapam` across all its SQL scripts.
- Open-questions pass, source side: the FSM's write and search paths and the
  asymmetry between them (`RecordPageWithFreeSpace`, `fsm_set_and_search`,
  `fsm_search` from `FSM_ROOT_ADDRESS`, `GetPageWithFreeSpace`,
  `FreeSpaceMapVacuum`, the FSM README's account of when upper nodes are updated),
  the index FSM wrappers (`GetFreeIndexPage`, `RecordFreeIndexPage`,
  `IndexFreeSpaceMapVacuum`) and `GinNewBuffer`'s use of them; `pg_control_init`
  and its documented output columns; `SizeOfPageHeaderData` and the entry-page
  `PageAddItem` call sites in `ginentrypage.c`; `GinNullCategory` and its five
  category constants; and the buffer-replacement path — `PinBuffer`'s usage-count
  increment, `BM_MAX_USAGE_COUNT`, and `StrategyGetBuffer`'s clock sweep.
- Open-questions pass, server side, all on the same sandbox
  (`.wiki-runtime/tmp/ginw2/`, exact-pin 17.11, port 55432): the published fixture
  SQL re-run unmodified in two freshly created databases and scored again; a
  five-point churn sweep; an entry-tuple probe validated against
  `count(DISTINCT ...)` on three shapes including one with NULL and empty arrays;
  three fixtures grown entirely through the pending list; a five-round
  insert-and-flush experiment with `pg_freespace` and per-class slack captured at
  every step; four concurrency cases (a VACUUM deleting posting-tree pages, four
  writers, an insert-and-flush loop, a `REINDEX INDEX CONCURRENTLY`) with each
  census bracketed by separate size readings; plain and concurrent rebuilds of
  identical fixtures with and without a 100,000-row insert stream; four more
  opclasses plus the same opclass at 50,000 and 800,000 rows; and a
  `pg_buffercache` eviction experiment at `shared_buffers = 128MB` with a hot and a
  cold working set, restored to 256MB afterwards.
- Two-major pass, source side: the `pageinspect` extension scripts that changed the
  three signatures this statement depends on (`get_raw_page`'s block-number type in
  1.9, `page_header`'s column types in 1.10) and the `PageIsNew` early returns in
  `ginfuncs.c`; the GIN build path's memory rule (`ginBuildCallback`'s
  `maintenance_work_mem` comparison, `BuildAccumulator.allocatedMemory`, the
  `GetMemoryChunkSpace` accounting in `ginbulk.c`, and `GetMemoryChunkSpace`'s own
  definition and comment in `mcxt.c`); `maintenance_work_mem` and
  `autovacuum_vacuum_insert_threshold` in `guc_tables.c`; the `indisvalid` checks in
  `pgstatindex.c` and `pgstattuple.c`; and this checkout's own commit history for
  `f18aa1b2039`, `127404fbe28`, `cd4868a5700` (with its `REL_12_11` backport
  `5378d55cb2f`), `13503eb5905`, `c6e0fe1f2a0` and `2c2eb0d6b27`, plus the GIN
  commits between `REL_12_0` and the pin that touch `ginbulk.c`, `gininsert.c`,
  `ginentrypage.c` and `gindatapage.c`.
- Two-major pass, server side: two isolated clusters built out of tree from this
  repo's own pins — **12.2** (`server_version_num` 120002, port 55412) and **17.11**
  (170011, port 55417), both `--without-readline --without-zlib`, `block_size` 8192,
  `autovacuum = off`, `fsync = off`, `shared_buffers = 256MB`, `pageinspect`,
  `pgstattuple`, `pg_freespacemap`, `pg_trgm`, `btree_gin` and `pg_buffercache`
  installed from their own trees (1.7/1.5/1.2/1.4/1.3/1.3 on 12.2 and
  1.12/1.5/1.2/1.6/1.3/1.5 on 17.11). Run on both: all four published statements
  verbatim and portable; 27 scored fixtures with `REINDEX INDEX` ground truth; the
  `f2` lifecycle; the `f5` three-VACUUM sequence with `VACUUM VERBOSE` and FSM
  captures; a held `REPEATABLE READ` snapshot; five insert-and-flush rounds; plain
  and concurrent rebuilds with and without a 100,000-row insert stream; four
  concurrency cases with per-census size brackets (100 censuses in total); an
  autoanalyze-only flush with and without `autovacuum_vacuum_insert_threshold`; a
  `pg_stat_scan_tables`-only role; the refusal matrix including a failed
  `CREATE INDEX CONCURRENTLY` leftover and another session's temp index; both
  timeout cancellations; a `pg_basebackup` standby each; a `-m immediate` crash
  during a bulk insert; two hand-appended all-zero blocks and a `dd`-zeroed
  metapage; a `maintenance_work_mem` sweep from 4MB to 1GB with parallel-worker
  controls;
  `EXPLAIN (ANALYZE, BUFFERS)` single-read proofs; cold and warm cost after a
  restart; and a `pg_buffercache` eviction experiment at `shared_buffers = 64MB`,
  restored to 256MB. Both sandboxes were deleted when this page was filed, at the
  asker's instruction, so reproducing any of it means rebuilding both servers from
  this repo's two pinned checkouts and re-running the SQL printed here.
- `bloat_pct` pass, source side: the version gate the column inherits
  (`GinMetaPageData` and the `pd_lower` trust note in `ginblock.h`) and
  `entrySplitPage`, which is why a fresh build's fill sets the column's floor. No new
  source surface was needed, because the column is arithmetic over terms the census
  already computes.
- `bloat_pct` pass, server side: two fresh clusters, both deleted when this page was
  filed. **17.11** at `.wiki-runtime/tmp/ginpct17/` (port 55437, VPATH build from
  `raw/postgres-17/`, `autovacuum = off`, `fsync = off`, `shared_buffers = 256MB`,
  `pageinspect` 1.12 / `pgstattuple` 1.5 / `pg_freespacemap` 1.2) carrying the seven
  published fixtures built from this page's own fixture SQL plus its documented
  three-VACUUM sequence for `f5`, in an aged database and a rebuilt one. **12.2** at
  `.wiki-runtime/tmp/ginpct12/` (port 55412, binaries from the retained
  `.wiki-runtime/tmp/pta12/pg` install of this repo's v12 pin, with `pageinspect` 1.7
  and `pg_freespacemap` 1.2 built from the same tree and removed again afterwards,
  same server settings), carrying the same fixtures with `txid_current()` in place of
  `pg_current_xact_id()`. Run on both: the filed census text and the amended text
  compared cell by cell, the amended text scored against `REINDEX INDEX` over all
  seven fixtures, a `fastupdate` fixture censused with a live 246-page pending list
  and then rebuilt, and `EXPLAIN (ANALYZE, BUFFERS)` on both texts. The amended text
  published above was extracted from this page's own Markdown and re-run on both
  servers; on 17.11 it returned the aged corpus's table byte for byte. The 17.11
  aged corpus was then rebuilt index by index and landed on the same seven byte
  counts as the separately rebuilt database and as the 12.2 rebuilds, which is what
  the `REINDEX reclaimed %` column above rests on.
- Version scope of the 12.2 column: measurement plus this checkout's history only.
  No v12 source file is cited on this page, and the v12-side source analysis is not
  filed anywhere yet.
- Sixth pass (2026-09-07), source side: every one of the page's 422 citations
  (202 distinct ranges over 60 files) re-read against the pin, all in bounds and
  all supporting their claims; the `STRICT` declarations of the `pageinspect`
  decoders and the executor's null-argument skip for functions in `FROM`; the
  special-size and flags checks that make the decoders error; the three progress
  views; `PageGetSpecialSize`; the `INDEX_CLEANUP` and reloption paths and the
  `index scan bypassed` messages; and `GinPageOpaqueData`, `GinMetaPageData` and
  `PageHeaderData` for the byte offsets the corruption cases patched.
- Sixth pass, server side: one isolated cluster built out of tree from
  `raw/postgres-17/` (`.wiki-runtime/tmp/ginw3/`, 17.11, port 55433,
  `--without-readline --without-zlib --without-icu`, `autovacuum = off`,
  `fsync = off`, `shared_buffers = 256MB`, the six contrib modules from the same
  tree). Run: the published fixtures `f1`-`f7` with the `f5` VACUUM sequence and
  `p1`, censused by the published and the guarded statements and compared cell by
  cell; `EXPLAIN (ANALYZE, BUFFERS)` and warm timings for both; five scratch
  indexes patched with the server stopped; a `pg_stat_scan_tables`-only role; an
  invalid index from a failed `CREATE INDEX CONCURRENTLY`; another session's and
  the session's own temporary index; the `f5` recipe with a held `REPEATABLE READ`
  snapshot; the `f5` recipe at 100,000 rows under `INDEX_CLEANUP OFF` and the
  `vacuum_index_cleanup` reloption; 60 censuses across a VACUUM of a 600,000-row
  `f5`-shaped table, 60 across its `REINDEX CONCURRENTLY`, and 40 under a
  200,000-row insert stream into `p1`; `REINDEX INDEX` of `f1`-`f7` and of `p1`;
  and `f1` rebuilt at 4MB, 64MB and 1GB. The 27-fixture corpus was not re-run.
  The sandbox was deleted when this page was filed, so reproducing any of it means
  rebuilding from the pin and re-running the SQL printed here.
- Seventh pass (2026-09-08), source side: the lock manager's conflict table and
  lock-mode numbering; `LOCK TABLE`'s relkind restriction and its privilege check,
  plus the reference page's privilege paragraph and `mvcc.sgml`'s
  `SHARE ROW EXCLUSIVE` entry; the table lock modes taken by VACUUM, `VACUUM FULL`,
  ANALYZE, `REINDEX` and `REINDEX CONCURRENTLY`, and the index-only
  `RowExclusiveLock` that `gin_clean_pending_list` takes; `PageInit` and
  `GinInitPage`/`GinInitBuffer` and `ginbuild`'s root initialization, for the
  page-format derivation; `PageHeaderData`, `SizeOfPageHeaderData`, `ItemIdData`,
  `GinPageOpaqueData` and its "only 8 bytes" comment, `SizeOfGinPostingList` and
  `PostingItem`, for which offsets are line-pointer counts and which are not;
  `PageIsVerifiedExtended`'s header-sanity test and the `zero_damaged_pages` GUC;
  and the failsafe path end to end — `vacuum_xid_failsafe_check`'s
  `Max(vacuum_failsafe_age, autovacuum_freeze_max_age * 1.05)` floor,
  `lazy_check_wraparound_failsafe`'s three cleared flags and WARNING, the
  `VacuumFailsafeActive` branch that picks the `index scan bypassed by failsafe:`
  message, and both GUCs' contexts.
- Seventh pass, server side: one isolated cluster built out of tree from
  `raw/postgres-17/` (`.wiki-runtime/tmp/ginw4/`, 17.11, port 55434,
  `--without-readline --without-zlib --without-icu`, `--locale=C`,
  `autovacuum = off`, `fsync = off`, `shared_buffers = 256MB`, the six contrib
  modules from the same tree), and nine databases in it. Run: `f1`-`f7` with the
  `f5` VACUUM sequence and `p1`, censused by the published, the guarded and the
  derived statements and compared cell by cell, then `REINDEX`-scored and censused
  again; the same fixtures rebuilt in a second database for the cross-database
  comparison, `EXPLAIN (ANALYZE, BUFFERS)` and warm timings; the five-point churn
  sweep with the entry-tuple probe and its rebuild predictions; the extended
  recipes `f11`-`f15`, `k4`, `k5` and `fn_null` scored against `REINDEX`; the
  layout probe; the protocol under eight concurrent commands, `pg_locks`, a queued
  VACUUM, and a `gin_clean_pending_list()` flush inside a locked transaction; 40
  unlocked and 20 locked censuses across one VACUUM of a 2,594-block index (a
  fixture the 2026-09-15 run replaced); the
  `f5` recipe at 100,000 rows under the wraparound failsafe after 120,000
  transaction ids, with a plain VACUUM as the control; four
  `pg_ctl stop -m immediate` crashes during a 600,000-row insert; and three new
  hand-patched corruption shapes with `zero_damaged_pages` on the one the buffer
  manager refuses. Two restarts were needed for `autovacuum_freeze_max_age`. The
  sandbox was deleted when this page was filed.

## Evidence Map

| Claim | Evidence |
|---|---|
| A `VACUUM ANALYZE` vacuums then analyzes each relation, so the GIN callback is reached by the `VACUUM` half alone | [vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650), [analyze.c#analyze-only-cleanup](../../../../raw/postgres-17/src/backend/commands/analyze.c#L694-L721); run: `m1_pair` identical on both sides of the maintenance step |
| GIN is the one core index AM whose `amvacuumcleanup` is not a no-op in ANALYZE-only mode, and it flushes only in an autovacuum worker | [analyze.c#analyze-only-cleanup](../../../../raw/postgres-17/src/backend/commands/analyze.c#L694-L721), [ginvacuum.c#analyze_only-worker](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L729) |
| The stand-in's flush passes `full_clean` true where a worker's analyze passes false, and holds `RowExclusiveLock` on the index | [ginfast.c#ginInsertCleanup](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L776-L783), [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1030-L1091), [analyze.c#analyze-lockmode](../../../../raw/postgres-17/src/backend/commands/analyze.c#L135-L145) |
| Neither `ANALYZE` nor `gin_clean_pending_list` reaches `ginUpdateStats`, so a stand-in fixture carries stale metapage counts | [ginvacuum.c#analyze_only-worker](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L729), [ginvacuum.c#ginvacuumcleanup-census](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L789), [ginutil.c#ginUpdateStats](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L645-L650); run: `a1_analyze_gin` metapage 43 total against 93 blocks |
| The `ANALYZE` half rewrites the measured index's `relpages`/`reltuples`, while a VACUUM that skipped a page does not | [analyze.c#index-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663), [vacuum.c#vac_update_relstats](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1409-L1416), [vacuumlazy.c#estimated_count](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2352-L2356), [vacuumlazy.c#update_index_statistics](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3081-L3098); run: `an_cat_gin` 4 -> 23 relpages |
| The census's analyze test is strictly greater, on reloption-or-GUC values with `reltuples` clamped at zero | [autovacuum.c#anl-effective-values](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3011-L3017), [autovacuum.c#census-inputs](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3063-L3072), [autovacuum.c#vacthresh-anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3074-L3076), [autovacuum.c#verdicts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095); run: `tc3_boundary` at 1,050 against 1,050 declined |
| `autovacuum_enabled = false` short-circuits both verdicts, and the reloptions arrive as `AutoVacOpts` where an unset member reads below zero | [autovacuum.c#av_enabled-return](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3048-L3054), [autovacuum.c#extract_autovac_opts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2704-L2723), [rel.h#AutoVacOpts](../../../../raw/postgres-17/src/include/utils/rel.h#L308-L326), [reloptions.c#autovacuum_enabled](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L105-L113) |
| The launcher walks plain tables and matviews only, and never analyzes `pg_statistic` | [autovacuum.c#do_autovacuum-relkind](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1984-L1992), [autovacuum.c#pg_statistic](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3108-L3110); run 2026-09-24: 101 tables walked |
| Churn reaches `mod_since_analyze` only on a flush, and `ANALYZE` zeroes the counter, so publication order decides what the census reads | [pgstat.c#PGSTAT_MIN_INTERVAL](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L117-L122), [pgstat.c#pgstat_report_stat](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L583-L600), [pgstat_relation.c#mod_since_analyze](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L855-L860), [pgstat_relation.c#report_analyze-reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L331-L337), [pg_proc.dat#pg_stat_force_next_flush](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L5916-L5920); run: `tc4_hazard` 10,500 against `tc2_declined` 500 |
| The census reads `n_mod_since_analyze` from `pg_stat_all_tables` under a snapshot it discards between reads | [system_views.sql#launcher-counters](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L688-L690), [guc_tables.c#stats_fetch_consistency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4966-L4974), [pg_proc.dat#pg_stat_clear_snapshot](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L5911-L5915), [stats.sql#force-flush](../../../../raw/postgres-17/src/test/regress/sql/stats.sql#L101-L110) |
| `n_data_pages` equals live data pages plus deleted-but-not-recyclable ones, because recyclability is tested first | [ginvacuum.c#ginvacuumcleanup-census](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L789); run 2026-09-24: the identity held on 24 of 24 indexes |
| A metapage's entry-page count goes stale on any growth or flush its last cleanup did not see | [ginvacuum.c:786-789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L786-L789), [ginutil.c#ginUpdateStats](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L645-L650); run 2026-09-24: `n_entry_pages` matched 23 of 26, missing on `a1_analyze_gin` 42/43, `c1_analyzed_gin` 5/6 and `l1_lock_gin` 9/34 |
| The dead-key population is the difference between two probe passes, not an inference | run 2026-09-24 (`probe_after`), as on 2026-09-16: `f1` 100,056 → 50,028, `f14` 102,056 → 51,028, `f11` 297,385 → 148,694, `g100` 200,020 → 100,010, against `f7` 50,030 → 50,029 and seven fixtures at 0 |
| Whole-page waste is not a lower bound on what a rebuild returns | [index.c:3781-3789](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789), [ginentrypage.c#entrySplitPage](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L666-L691); run: `f2_pending` 64.64 against 58.05 and `a1_analyze` 52.69 against 45.16 |
| A page that breaks `pd_upper <= pd_special` is refused by the buffer manager before any SQL guard | [bufpage.c#PageIsVerifiedExtended](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L88-L124), [guc_tables.c#zero_damaged_pages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1123-L1136); run: `s8_gin` |
| Waste is a lower bound only when the in-use core is at least the rebuild | server 2026-09-15: `f2_pending_gin` 64.64% dead against 58.05% returned with a 2,195,456-byte core under a 2,605,056-byte rebuild, and `a1_analyze_gin` 52.69% against 45.16% with 360,448 under 417,792 |
| A concurrent VACUUM can make a census read anything between 0 and the truth | server 2026-09-24: four censuses across one VACUUM of an unchanging 898-block file read four different deleted-page counts from 0 to 768; three of the four were flagged, one was not |
| The protocol lock removes that case | server 2026-09-24: 20 censuses inside one `SHARE ROW EXCLUSIVE` transaction were identical, and the queued VACUUM waited 3219 ms and then deleted 768 pages |
| The corpus reproduces from the published script | server 2026-09-15: `f1` 17,571,840 churned, `f2` 2,195,456 then 6,209,536 with 490 pending flushed, `f4` 16,384, `f5` and `f6` 7,356,416, `f7` 11,927,552, and all five churn-sweep sizes and dead-tuple counts, byte for byte and digit for digit against the superseded corpus; `f3` and `f1`'s rebuild came out one entry page larger |
| The whole scored corpus reproduces across clusters and platforms | server 2026-09-16: two full passes on two freshly initdb'd Linux x86_64 clusters returned the same 27-index page census, byte and percentage columns, 19 `truth_pct` values and two lower-bound violations as 2026-09-15; server 2026-09-24: the recorded run on Darwin 27 arm64 and a baseline pass of the filed script there returned the same scored cells again, `f9c_cleanup_gin` aside, while a third pass that day moved `g50_gin` by one page (open question 23); the movements are elapsed times, the lock-timeout cancellations, the queued-VACUUM wait and concurrency cases A and D |
| VACUUM skips index vacuuming when fewer than 2% of heap pages carry dead line pointers, and those TIDs stay in the index | [vacuumlazy.c:89](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L89), [vacuumlazy.c:1899-1948](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1899-L1948); server 2026-09-24, one pass, earlier script revision: `s50`'s maintenance VACUUM printed `index scan bypassed: 2 pages from table (0.07% of total) have 272 dead item identifiers`, ANALYZE counted 272 dead rows, and `g50_gin` read 93 / 38 data-leaf / deleted pages against 92 / 39 |
| A VACUUM that cannot take a page's cleanup lock leaves that page's dead tuples unpruned, and says so only when VERBOSE | [vacuumlazy.c:923-952](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L923-L952), [vacuumlazy.c:1761-1768](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1761-L1768), [vacuumlazy.c:664-668](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L664-L668) |
| The standby stage's time is two spread checkpoints, not the copy | [pg_basebackup.sgml:499-504](../../../../raw/postgres-17/doc/src/sgml/ref/pg_basebackup.sgml#L499-L504), [pg_basebackup.sgml:968-971](../../../../raw/postgres-17/doc/src/sgml/ref/pg_basebackup.sgml#L968-L971), [xlog.c:8940-8959](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L8940-L8959); server 2026-09-24: a WAL-triggered checkpoint ran 13:53:55 to 13:58:25, the backup's `force wait` checkpoint 13:58:25 to 14:00:50, and the stage 13:54:28 to 14:00:53 |
| `page_header` checks a short `bytea` through `get_page_from_raw` on 17.11 | [rawpage.c:266](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L266), [rawpage.c#get_page_from_raw](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L214-L234); run 2026-09-24: `invalid page size` from both `page_header` and `gin_page_opaque_info` on 17.11, `input page too small (2 bytes)` from `page_header` alone on 12.2 |
| Plan review: page gaps exclude retained empty-key entry tuples; a rebuild builds from the heap | [ginvacuum.c:507-558](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L507-L558), [gininsert.c#ginbuild](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L317-L406) |
| Plan review: a pending flush does not perform the full metapage-count refresh | [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1031-L1091), [ginvacuum.c:754-802](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L754-L802) |
| Plan review: disabled cleanup and the failsafe can prevent the GIN cleanup callback | [vacuum.c:2155-2178](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2155-L2178), [vacuumlazy.c:392-401](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L401), [vacuumlazy.c:1064-1066](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1064-L1066), [vacuumlazy.c:2323-2335](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2335) |
| Plan review: a raw-page copy releases its locks before the next call | [rawpage.c#get_raw_page_internal](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L141-L198) |
| Plan review: `PageIsNew` tests one header field; the GIN opaque decoder reports unknown bits | [bufpage.h#PageIsNew](../../../../raw/postgres-17/src/include/storage/bufpage.h#L226-L234), [ginfuncs.c:119-159](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L119-L159) |
| Plan review: the version gate must cover every value derived from untrusted data-page offsets | [ginblock.h:302-309](../../../../raw/postgres-17/src/include/access/ginblock.h#L302-L309); static audit of the filed SELECT list: the component slack and payload expressions have no version guard |
| Plan review: the offset and volatile-target checks preserve the raw-read subquery boundary | [prepjointree.c:1689-1701](../../../../raw/postgres-17/src/backend/optimizer/prep/prepjointree.c#L1689-L1701), [prepjointree.c:1772-1781](../../../../raw/postgres-17/src/backend/optimizer/prep/prepjointree.c#L1772-L1781) |
| Plan review: the rebuild comparison measures main-fork file lengths | [dbsize.c#calculate_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L301-L343), [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L370) |
| `pgstattuple` rejects GIN | [pgstattuple.c#pgstat_relation](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L260-L296); server: `index "f5_deleted_gin" (gin index) is not supported` |
| `pgstattuple` checks validity before the AM | [pgstattuple.c:263-267](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L263-L267); server: invalid GIN index reported `is not valid` |
| `pgstatginindex` reads only three metapage fields | [pgstatindex.c#pgstatginindex_internal](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L507-L577), [pgstattuple.sgml:298-350](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L298-L350); server: `0 / 0` on a 64.64%-dead index |
| No GIN verifier in v17 contrib amcheck | [amcheck--1.0.sql:9-20](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.0.sql#L9-L20), [amcheck--1.2--1.3.sql:9-21](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.2--1.3.sql#L9-L21), [amcheck--1.3--1.4.sql:11-24](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.3--1.4.sql#L11-L24) |
| Recyclable = new or deleted-and-past-the-horizon | [ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829), [bufpage.h#PageIsNew](../../../../raw/postgres-17/src/include/storage/bufpage.h#L226-L234) |
| Recyclability uses the most conservative horizon | [procarray.c#GlobalVisHorizonKindForRel](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1966-L1991), [procarray.c#GlobalVisCheckRemovableXid](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L4294-L4306); server: 0 reusable on two VACUUMs, 768 after three xids were consumed |
| Deleted pages keep their data/leaf flags | [ginvacuum.c:187-192](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L187-L192); server flag set `{data,leaf,deleted,compressed}` |
| Flushed pending pages become `deleted`, not stale `list` | [ginfast.c#shiftList](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L630-L635); server: 490 `pending` became 490 `deleted`, flags exactly `{deleted}` |
| Flushed pending pages are immediately reusable | [ginvacuum.c:816-822](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L816-L822); server: `490 currently deleted, 490 reusable` in one VACUUM |
| Free pages are recorded as `BLCKSZ - 1` but read back as 8160 | [indexfsm.c:48-55](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L48-L55), [freespace.c:398-435](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L398-L435), [htup_details.h:563](../../../../raw/postgres-17/src/include/access/htup_details.h#L563); server: `avail = 8160` on 768 and 490 pages, max `avail` 8160 over every GIN index |
| Free pages are reused in-index, never truncated | [ginutil.c#GinNewBuffer](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L294-L335), [ginvacuum.c:796-802](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L796-L802); server: file size never shrank across any VACUUM or flush, and 491 dead pages absorbed 50k rows' pending list for +26 blocks |
| GIN's own slack measure is `pd_upper - pd_lower` | [ginblock.h:287](../../../../raw/postgres-17/src/include/access/ginblock.h#L287), [bufpage.c#PageGetExactFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L952-L973) |
| Entry-page slack over-states usable space by a line pointer | [ginentrypage.c#entryIsEnoughSpace](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L458-L482), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L898-L923) |
| Version 2 is the right gate for trusting `pd_lower` | [ginblock.h:85-103](../../../../raw/postgres-17/src/include/access/ginblock.h#L85-L103), [ginblock.h:302-309](../../../../raw/postgres-17/src/include/access/ginblock.h#L302-L309), [gindatapage.c:520-528](../../../../raw/postgres-17/src/backend/access/gin/gindatapage.c#L520-L528) |
| Entry tree never loses tuples or pages | [README:389-396](../../../../raw/postgres-17/src/backend/access/gin/README#L389-L396), [README:26-30](../../../../raw/postgres-17/src/backend/access/gin/README#L26-L30) |
| Entry pages split in half, so fresh builds are far from full | [ginentrypage.c#entrySplitPage](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L666-L691); server payload fraction after rebuild: 51.95 / 58.94 / 51.95 / 50.20 / 43.28 / 87.96 / 52.81% |
| Only entirely empty posting-tree pages are deleted | [ginvacuum.c#ginScanToDelete](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L303-L318); server: uniform deletes gave 0 deleted pages and 51.34% slack |
| `n_entry_pages`/`n_data_pages` are a VACUUM-time census | [ginvacuum.c:766-789](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L766-L789); server: matched the SQL census on every fixture; `n_total_pages` 268 against 758 real blocks before a VACUUM; `meta_data_pages 77` counted 14 not-yet-recyclable deleted pages as data |
| GIN's `pages_deleted` is per-run, `pages_free` is a census | [ginvacuum.c:234-235](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L234-L235), [ginfast.c:590-591](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L590-L591), [ginvacuum.c:786-794](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L786-L794), [vacuumlazy.c:718-731](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L731); server: GIN `0 currently deleted, 768 reusable` beside B-tree `520 currently deleted, 520 reusable` in the same VACUUM |
| All-zero pages return NULL from the GIN functions | [ginfuncs.c:49-50](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L49-L50), [ginfuncs.c:119-120](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L119-L120), [pageinspect/expected/gin.out:57-70](../../../../raw/postgres-17/contrib/pageinspect/expected/gin.out#L57-L70); server: row of NULLs, `pagesize 0` |
| Raw-page functions are superuser-only | [rawpage.c:150-153](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L150-L153), [ginfuncs.c:42-45](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L42-L45), [pageinspect.sgml:10-14](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L10-L14); server: `must be superuser to use raw page functions` |
| `pgstatginindex` and `pg_freespace` reach `pg_stat_scan_tables` | [pgstattuple--1.4--1.5.sql:49-57](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L49-L57), [pg_freespacemap--1.1--1.2.sql:6-7](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap--1.1--1.2.sql#L6-L7); server: both worked for such a role |
| `gin_clean_pending_list` needs ownership | [ginfast.c:1061-1064](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1061-L1064); server: `must be owner of index f6_slack_gin` |
| `pg_freespace` has no other-session-temp guard | [pg_freespacemap.c:24-50](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap.c#L24-L50); server: returned rows where the other two refused |
| The scan is page-at-a-time, not a snapshot | [rawpage.c:186-196](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L186-L196) |
| `gin_leafpage_items` needs an exact flag match | [ginfuncs.c:219-226](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L219-L226); server: `Flags 0002, expected 0083` |
| The census reads no ring buffer, unlike pgstattuple | [rawpage.c:181-196](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L181-L196), [pgstattuple.c:544](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L544), [pgstatindex.c:222](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L222); server: cold run read 1262 blocks for a 1263-block index |
| `gin_clean_pending_list` and VACUUM are refused during recovery | [ginfast.c:1037-1041](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1037-L1041); standby: `recovery is in progress` and `cannot execute VACUUM during recovery`, while the census functions answered |
| `gin_pending_list_limit` is session-scoped | [guc_tables.c:3576-3585](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585) |
| `pg_relation_size` with one argument is the main fork | [func.sgml:29627-29643](../../../../raw/postgres-17/doc/src/sgml/func.sgml#L29627-L29643) |
| A flush merges entries and never shrinks the file | [ginfast.c#ginInsertCleanup](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1014-L1020), [ginutil.c#GinNewBuffer](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L294-L335); server: 6,209,536 -> 6,209,536 bytes with 490 pages turned dead, entry slack 575,940 -> 318,084 |
| The payload/fill model breaks when churn replaces the key set | [README:389-396](../../../../raw/postgres-17/src/backend/access/gin/README#L389-L396); server: +19.94% on `f1` and +18.12% on the multicolumn `f14` (keys replaced) against +0.07% on `f7` and +0.00% to +1.49% on the other opclasses |
| One idle snapshot blocks recyclability indefinitely | [ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829), [procarray.c#GlobalVisHorizonKindForRel](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1966-L1991); server: 0 reusable across three VACUUMs and 6 xids with a `REPEATABLE READ` snapshot held at `backend_xmin` 870 = the pages' `prune_xid`, then 768 reusable on the next VACUUM after release with no new xids |
| The self-check does not detect a concurrent writer | [rawpage.c:186-196](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L186-L196); server: `census_total_pages = blocks` held 25 of 25 while `pending_pages` disagreed with `meta_pending_pages` in 19 of 25 and the block count went stale by up to 664 blocks |
| Autoanalyze alone flushes the pending list | [ginvacuum.c:705-717](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L717), [guc_tables.c:1449-1457](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457); server: 491 pending pages -> 0 in under 10 s with `last_autovacuum` still null, the file growing 836 -> 958 blocks |
| The census has no ring buffer, a seq scan does | [rawpage.c:181-196](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L181-L196), [heapam.c:434-458](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L434-L458); server at 8,192 buffers: a 6,665-block census left all 6,665 pages resident and later lost 2,942 of them to the next censuses, while a 4,092-block seq scan left 98 |
| Real all-zero pages exist after a crash | [ginutil.c#GinNewBuffer](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L294-L335), [bufpage.h#PageIsNew](../../../../raw/postgres-17/src/include/storage/bufpage.h#L226-L234); server: 4 and 7 all-zero pages after two `-m immediate` crashes during a bulk insert |
| `REINDEX CONCURRENTLY` gives the same size as `REINDEX` | server: 7,356,416 -> 3,948,544 bytes either way on the same fixture recipe, 379 ms against 151 ms, and 3,276,800 -> 2,662,400 either way under a 100,000-row insert stream (1901 ms against 2013 ms) |
| The published fixtures reproduce across runs | server: the published SQL re-run in two virgin databases gave all seven filed sizes, page-class counts, slack bytes, lifecycle states and `REINDEX` results byte for byte; only `f5`'s `prune_xid` moved (953 against 791 and 870) |
| Entry-leaf `pd_lower` counts the index's keys | [ginentrypage.c:561-568](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L561-L568), [ginentrypage.c:683-691](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L683-L691), [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L211-L214); run 2026-09-24: 50,028 entry tuples against 50,028 distinct lexemes and 32 against 32 tags, both key counts taken from the tables without the index; the 53 = 50 tags + 3 null categories reading is from a fixture removed on 2026-09-15 ([ginblock.h#GinNullCategory](../../../../raw/postgres-17/src/include/access/ginblock.h#L204-L213)) |
| The payload model's error is linear in the dead-key share | [README:389-396](../../../../raw/postgres-17/src/backend/access/gin/README#L389-L396); server: +0.09 / +12.62 / +25.16 / +37.69 / +50.19% at 0 / 25 / 50 / 75 / 100% of the key population replaced, increments of +12.53, +12.54, +12.53, +12.50 |
| Dead entry tuples are smaller than live ones, so the average over-corrects | server: average entry tuple 32.0 bytes at `p = 0` falling to 24.0 at `p = 100`, putting dead tuples at 16 bytes; corrected estimate −7.48 to −18.44% on the sweep and −36.80% on `f1` |
| A pending list is built from the FSM's free stock, the merge is not | [ginutil.c#GinNewBuffer](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L299-L328), [indexfsm.c#GetFreeIndexPage](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L37-L46); server: 0 free pages -> the file grew by exactly the 736 pending pages, 736 free -> zero growth on four consecutive rounds, and `pg_freespace` read 0 at every flush |
| A flush cannot reuse the pages it frees | [freespace.c#RecordPageWithFreeSpace](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L186-L204), [freespace.c#fsm_search](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L684-L691), [ginfast.c:1014-1020](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1014-L1020) |
| Flush growth is not a function of total slack | server: +194 blocks at 2,326,056 bytes of slack against +0 at 3,197,144 and +649 at 1,885,966 |
| The size bracket beats the metapage cross-check on writers | server: 13 of 14 against 0 of 14 under four concurrent writers, with the statement's self-check passing 14 of 14 |
| A census strips usage count rather than evicting a hot set | [bufmgr.c:2700-2705](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2700-L2705), [buf_internals.h#BM_MAX_USAGE_COUNT](../../../../raw/postgres-17/src/include/storage/buf_internals.h#L72-L79), [freelist.c#StrategyGetBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L314-L341); server at 16,384 buffers: a 26,195-block census left a hot 3,704-page set fully resident at usagecount 1 (from 5) and destroyed a once-read set of the same size; a second census took the hot set too |
| The FSM free-page value is derivable, not a constant to type | [pg_controldata.c#pg_control_init](../../../../raw/postgres-17/src/backend/utils/misc/pg_controldata.c#L203-L228), [func.sgml#pg_control_init](../../../../raw/postgres-17/doc/src/sgml/func.sgml#L27721-L27742), [htup_details.h#MaxHeapTupleSize](../../../../raw/postgres-17/src/include/access/htup_details.h#L563); server: the derived expression returned 8160, equal to the largest `avail` over 3,478 free GIN pages, and `pg_control_init()` is executable by `PUBLIC` |
| Fresh-build fill is opclass-dependent but scale-insensitive | server: 50.16% to 72.11% across nine opclasses and shapes, while the same opclass at 50,000 and 800,000 rows read 51.12% and 50.92% with model errors of +33.18% and +33.60% |
| The census statement needs a block-number cast to run on 12 | [pageinspect--1.8--1.9.sql#get_raw_page](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L46-L58) (`f18aa1b2039`, first released in `REL_14_0`, earliest tag `REL_14_BETA1`); run 2026-09-24, both legs: 12.2 `ERROR: function get_raw_page(text, bigint) does not exist` without the cast, and with it the four-row census of the `port` database byte-identical on 12.2 and 17.11 |
| `page_header`'s width columns are narrower on 12 | [pageinspect--1.9--1.10.sql#page_header](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.9--1.10.sql#L10-L21) (`127404fbe28`, first released in `REL_15_0`, earliest tag `REL_15_BETA1`); run 2026-09-24: `pg_typeof` read `smallint` for `lower`, `upper`, `special` and `pagesize` on 12.2 and `integer` on 17.11, harmless at `block_size` 8192 |
| 12.2 does not return NULL for an all-zero page | [ginfuncs.c:49-50](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L49-L50), [ginfuncs.c:119-120](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L119-L120); `cd4868a5700` carries `Backpatch-through: 10`, and its 12-branch back-patch `5378d55cb2f` is first tagged `REL_12_11`, after this repo's 12.2 pin (v12 checkout history); run 2026-09-24: on one all-zero `bytea`, 12.2's `gin_page_opaque_info` returned `0 \| 0 \| {}` where 17.11 returned a row of NULLs |
| Without the `pagesize` guard the 12.2 census hides zeroed pages | run 2026-09-24: with two appended all-zero blocks, the census without its `pagesize = 0` arm read `pt_zero_gin` as 6 entry / 2 new / 16,384 waste bytes on 17.11 and 8 entry / 0 new / 0 bytes on 12.2, `census_total_pages = blocks` = 9 on both; the probe without its guard read -7 internal downlinks on 12.2 against 5 on 17.11 |
| A zeroed metapage aborts the whole census on 12.2 | run 2026-09-24, the `portmeta` database: 12.2 stopped with `ERROR: input page is not a GIN metapage`, `DETAIL: Flags 0000, expected 0008`; 17.11 returned NULL metapage columns for `pm_meta_gin` and listed `pm_ok_gin` |
| `pgstatginindex` answers for an invalid index on 12.2, and the check that refuses it was back-patched | [pgstatindex.c:538-543](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L538-L543), [pgstattuple.c:263-267](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L263-L267) (`13503eb5905`, earliest tag `REL_17_BETA1`, "Back-patch to v11"; the 12-branch copy `975ae05537` is first tagged `REL_12_17` and descends from the 12.2 pin, per v12 checkout history); run 2026-09-24: 17.11 `index "pt_inv_gin" is not valid`, 12.2 returned `2 \| 0 \| 0` for the failed-CIC leftover |
| 26 of 27 fixtures score identically on the two majors | server: identical size, rebuilt size, waste, slack, pending, reclaimed, both bound verdicts, fill, model error and dead-tuple counts; identical tallies of 24 / 25 / 26 of 27 for the lower bound, upper bound and upper-plus-pending |
| A fresh GIN build's size is a function of `maintenance_work_mem` | [gininsert.c:290-291](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L290-L291), [gin_private.h:434](../../../../raw/postgres-17/src/include/access/gin_private.h#L434), [ginbulk.c:139](../../../../raw/postgres-17/src/backend/access/gin/ginbulk.c#L139), [mcxt.c#GetMemoryChunkSpace](../../../../raw/postgres-17/src/backend/utils/mmgr/mcxt.c#L718-L730), [guc_tables.c:2466-2474](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2466-L2474); server: one index rebuilt to 34,611,200 at 64MB and 50,814,976 at 96MB and above, on both majors, with payload constant at about 25.6 MB and all the movement in `entry_slack` |
| The build divergence is a spill effect, not parallelism | server: `max_parallel_maintenance_workers` 0, 2 and 4 gave identical bytes; both majors returned exactly 50,814,976 once the build fitted one flush; v12 at 68MB and 70MB brackets v17 at 64MB |
| 12.2 prints the VACUUM cross-check differently | [vacuumlazy.c:718-731](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L731), [ginvacuum.c:786-794](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L786-L794); run 2026-09-24 on `pt_f5_gin`, 898 blocks on both: 12.2 printed `768 index pages have been deleted, 0 are currently reusable.` in a DETAIL block with no "newly deleted" split, and both legs read the same 768 / 0 / 768 sequence |
| Which race detector wins depends on the writer | server: under four writers the metapage check caught 23 of 25 (17.11) and 22 of 25 (12.2) where the size bracket caught 4 and 3; under an insert-and-flush loop 12 and 11 against 11 and 12; the self-check never fired in any census of any case on either server |
| The round-five split cascade is slack exhaustion | [ginentrypage.c#entrySplitPage](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L666-L691); server: `entry_slack` fell 2,126,732 -> 1,735,572 -> 1,340,484 -> 945,372 -> 538,900 with the entry tree fixed at 572 pages, then round five added 255 entry pages and slack jumped to 2,223,216 — identical on both majors |
| A census evicts a hot set once the target exceeds the cache | [bufmgr.c:2700-2705](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2700-L2705), [freelist.c#StrategyGetBuffer](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L314-L341), [heapam.c:434-458](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L434-L458); server at 8,192 buffers: a 9,616-block census took a 1,862-page hot set from `usagecount` 3 to 80 resident pages (17.11) and to 0 (12.2), while a 16k-block seq scan left it intact on both |
| `autovacuum_vacuum_insert_threshold` does not exist on 12.2 | [guc_tables.c:3359-3366](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3359-L3366); run 2026-09-24: 12.2 `unrecognized configuration parameter "autovacuum_vacuum_insert_threshold"`, 17.11 `1000`; `pg_current_xact_id()` exists on 17.11 and not on 12.2 |
| Rebuild equivalence holds on both majors | server: `f9` 7,356,416 -> 3,948,544 by either form; of four identical fixtures the two rebuilt under a 100,000-row insert stream both ended at 2,605,056 and the two rebuilt idle both stayed at 1,261,568, all ending valid/ready/live |
| `bloat_pct` changes nothing else in the statement | server: the filed text and the amended text returned identical values in all 25 pre-existing columns over 7 indexes (175 of 175 cells), the amended text adding only `bloat_pct` |
| The column reads no extra page | server: `EXPLAIN (ANALYZE, BUFFERS)` reported `shared hit=7568` for both texts over the same seven-index census |
| `bloat_pct` reproduces the page's `waste+slack %` scoring column | server: 64.12 / 75.30 / 48.05 / 49.80 / 95.22 / 51.34 / 54.15 on `f1`-`f7`, the same seven values the scoring table prints |
| A healthy GIN index reads about half its file as `bloat_pct` | [ginentrypage.c#entrySplitPage](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L666-L691); server: `f3_fresh_gin` 48.05 with `REINDEX` returning 0 bytes, `f4_empty_gin` 49.80 over one entry page holding 8,160 free bytes |
| `bloat_pct` bounded the rebuild on all seven fixtures, loosely | server: over-read +5.01 to +49.80 points against `REINDEX` truths of 42.42 / 58.05 / 0.00 / 0.00 / 89.09 / 46.33 / 13.26% |
| A live pending list makes the column under-read badly | server: 246 pending pages gave `bloat_pct` 8.66 and `pending_pct` 81.73 while `REINDEX` took the index 2,465,792 -> 794,624 bytes (67.77%), identical on 12.2; the sum, 90.39, bounds it |
| The amended text needs no further edit on 12.2 | server: it ran there unchanged and returned 178 of 182 identical cells over the seven fixtures, the four differences being `f7`'s known 128-and-10-byte slack gap, with `bloat_pct` identical on all seven and the 12.2 rebuilds landing on the same seven byte counts |
| Rounding the sum is not summing the rounded columns | server: `f2_pending_gin` prints 64.64 and 10.65 against a `bloat_pct` of 75.30 |
| A NULL page argument skips a `STRICT` decoder instead of erroring | [pageinspect--1.5.sql:246-268](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.5.sql#L246-L268), [create_function.sgml#STRICT](../../../../raw/postgres-17/doc/src/sgml/ref/create_function.sgml#L395-L400), [execSRF.c:188-196](../../../../raw/postgres-17/src/backend/executor/execSRF.c#L188-L196); server: `s4_gin` reported as `1 page(s) not decodable` where the published statement failed with `Expected special size 8, got 24.` |
| The decoders error on a wrong special-area size, and the metapage decoder on any flags but `{meta}` | [ginfuncs.c:52-67](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L52-L67), [ginfuncs.c:122-128](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L122-L128), [bufpage.h#PageGetSpecialSize](../../../../raw/postgres-17/src/include/storage/bufpage.h#L314-L317), [ginblock.h#GinPageOpaqueData](../../../../raw/postgres-17/src/include/access/ginblock.h#L30-L37); server: the published statement aborted on `s4_gin`; the guarded one reported `s2_gin` as `metapage unreadable` |
| The progress views expose an in-flight VACUUM, ANALYZE or index build for the index's table | [system_views.sql#pg_stat_progress_vacuum](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1209-L1227), [system_views.sql#pg_stat_progress_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1188-L1207), [system_views.sql#pg_stat_progress_create_index](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1256-L1289); server: 3 of 3 censuses flagged under a VACUUM that read 0, 1,098 and 2,368 deleted pages on an unchanging file, 2 of 2 under a concurrent rebuild |
| Index cleanup runs only while `do_index_cleanup` is set, and `INDEX_CLEANUP` off, as an option or as the `vacuum_index_cleanup` reloption, and the wraparound failsafe each clear it | [vacuum.c:2155-2178](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2155-L2178), [vacuumlazy.c:392-401](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L401), [vacuumlazy.c:1064-1066](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1064-L1066), [vacuumlazy.c:2323-2335](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2335); source only since 2026-09-24, when the `f9c_cleanup` fixture that measured it was removed |
| The guarded statement changes no number the published one prints | server: 208 of 208 shared cells identical over `f1`-`f7` and `p1`, 7,892 shared buffers for both, and the seven filed `REINDEX` results reproduced |
| A small build budget packs an entry-tree index tighter | [gininsert.c:290-291](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L290-L291), [ginentrypage.c#entrySplitPage](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L666-L691); server: `f1_churn_gin` rebuilt to 7,880,704 bytes at 4MB against 10,117,120 at 64MB and 1GB |
| An empty GIN index's root measures `SizeOfPageHeaderData` and the GIN special-area size on the running build | [bufpage.c#PageInit](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L42-L60), [ginutil.c#GinInitPage](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L337-L347), [gininsert.c:348](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L348); server: `page_header_bytes 24`, `gin_special_bytes 8`, `pd_upper = pd_special`, flags `{leaf}` |
| One line pointer on that root measures `sizeof(ItemIdData)` | [itemid.h#ItemIdData](../../../../raw/postgres-17/src/include/storage/itemid.h#L25-L30), [ginentrypage.c:561-568](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L561-L568); server: `pd_lower` 24 empty against 28 with one single-key row, so `line_pointer_bytes 4` |
| The page-header and GIN opaque sizes are format constants, not build options | [bufpage.h#PageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L155-L168), [bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-17/src/include/storage/bufpage.h#L211-L214), [ginblock.h#GinPageOpaqueData](../../../../raw/postgres-17/src/include/access/ginblock.h#L19-L37) |
| Deriving the arithmetic changes no number and costs nothing | server: 240 of 240 cells against the guarded statement and 208 of 208 against the published one, on two databases; `shared hit=7890` for all three texts; warm 73.1-77.9 ms against 54.1-76.2 ms |
| `pd_lower` is not a line-pointer count on posting-tree pages | [ginblock.h#SizeOfGinPostingList](../../../../raw/postgres-17/src/include/access/ginblock.h#L336-L344), [ginblock.h#PostingItem](../../../../raw/postgres-17/src/include/access/ginblock.h#L182-L188); server: an unrestricted `(lower - 24) % 4` test flagged 15 / 44 / 64 / 192 healthy data pages on `f1` / `f2` / `f5` / `f6`, all with residue 2 |
| `SHARE ROW EXCLUSIVE` is the weakest mode that excludes every writer of an index's pages | [lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L59-L104), [lockdefs.h:36-48](../../../../raw/postgres-17/src/include/storage/lockdefs.h#L36-L48), [mvcc.sgml#SHARE-ROW-EXCLUSIVE](../../../../raw/postgres-17/doc/src/sgml/mvcc.sgml#L1023-L1044), [vacuum.c:2049-2056](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2049-L2056), [analyze.c:135-145](../../../../raw/postgres-17/src/backend/commands/analyze.c#L135-L145), [indexcmds.c:678-679](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L678-L679); server: INSERT, VACUUM, ANALYZE, both `REINDEX` forms, `VACUUM FULL`, `DROP INDEX` and `CLUSTER` all cancelled at `lock_timeout`, `SELECT count(*)` unaffected |
| A plain `REINDEX INDEX` would slip past a `SHARE` lock | [indexcmds.c:678-679](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L678-L679), [indexcmds.c#RangeVarCallbackForReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2860-L2872), [lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L59-L104) |
| A table lock cannot stop a pending-list flush | [ginfast.c:1034](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1034), [lockcmds.c#RangeVarCallbackForLockTable](../../../../raw/postgres-17/src/backend/commands/lockcmds.c#L70-L107); server: inside one locked transaction the same index read `bloat_pct` 8.66 with 246 pending pages, then 82.74 with 246 deleted, neither census flagged |
| Every lock mode above `ROW EXCLUSIVE` needs MAINTAIN, UPDATE, DELETE or TRUNCATE | [lockcmds.c#LockTableAclCheck](../../../../raw/postgres-17/src/backend/commands/lockcmds.c#L279-L299), [lock.sgml#privileges](../../../../raw/postgres-17/doc/src/sgml/ref/lock.sgml#L167-L179) |
| The wraparound failsafe needs both GUCs and a real xid burn | [vacuum.c#vacuum_xid_failsafe_check](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1251-L1298), [guc_tables.c:2706-2714](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2706-L2714), [guc_tables.c:3376-3387](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3376-L3387); server 2026-09-08, in a run since removed: `vacuum_failsafe_age = 0` plus `autovacuum_freeze_max_age = 100000` and 120,000 consumed xids |
| A failsafe VACUUM skips index cleanup, and the census cannot tell afterwards | [vacuumlazy.c#lazy_check_wraparound_failsafe](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2299-L2348); server 2026-09-08, in a run since removed: `f9c_cleanup_gin` unchanged at 0 deleted pages and metapage 480 / 482 while `vacuum_count` went 0 -> 1, the control VACUUM then deleting 352 |
| Only the failsafe bypass is distinguishable in VACUUM's output | [vacuumlazy.c:705-711](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L705-L711); server 2026-09-08, in a run since removed: `index scan bypassed by failsafe: 2210 pages ... have 95000 dead item identifiers` against the reloption path's `index scan bypassed: ` |
| A crash leaves all-zero pages at the tail of the file, invisible to the FSM | [ginutil.c#GinNewBuffer](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L294-L335), [bufpage.h#PageIsNew](../../../../raw/postgres-17/src/include/storage/bufpage.h#L226-L234); server: 4 crashes gave 0, 0, 2 and 6 zeroed pages; round 4's six were blocks 1307-1312, byte-for-byte zero, with `pg_freespace` reporting 0 free pages |
| A page that breaks `pd_upper <= pd_special` is refused before any SQL guard runs | [bufpage.c#PageIsVerifiedExtended](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L88-L124), [guc_tables.c#zero_damaged_pages](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1123-L1136); server: `ERROR: invalid page in block 0` from all three statements, becoming `metapage special area 0 bytes, expected 8` with `zero_damaged_pages = on` |
| A self-consistent 16-byte special area on block 0 kills the published statement | [ginfuncs.c:52-67](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L52-L67); server: `ERROR: input page is not a valid GIN metapage`, `Expected special size 8, got 16.`, where the derived statement reported it and kept going |
| A corrupted entry-page `pd_lower` is invisible to the census | server: `pd_lower` 32 -> 33 left `status ok` and one byte less slack (14,231 against 14,232), while the derived probe read `malformed_pages 1` and the published probe was byte-identical |

## Open Questions

Renumbered on 2026-09-15, when the page was re-run under the protocol. Entries 1
through 12 are the gaps that survived the re-run; 13 through 18 are new, and five of
them exist because the re-run **removed** a fixture that used to answer something.
The two entries the previous list ended on are closed and recorded as 19 and 20.
Entry 21 is what the 2026-09-16 review added. Entries 22 to 24 are what the
2026-09-24 pass added, and it revised 5, 8, 15, 17, 20 and 21. The numbering of 1
through 21 is unchanged so that the references to it in the body still resolve.

1. **The `ginVersion <> 2` path is untested except by hand.** v17 always writes
   `GIN_CURRENT_VERSION = 2`
   ([ginutil.c:355-382](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L355-L382)), so no
   fixture can exercise the suppressed-slack branch or an uncompressed posting-tree
   leaf on data a server produced. `uncompressed_pages` was 0 and `gin_version` 2 on
   all 26 censused indexes of this run, as in every earlier one. The only version-1
   reading on the page comes from patching a byte in a scratch index file.
2. **The payload-and-fill model can be diagnosed but not corrected.** The
   entry-tuple probe measures the dead-key population exactly — since 2026-09-16 as
   a measured difference between two probe passes rather than an inference — and the
   error is linear in it, but turning that into a corrected prediction needs the
   *size* of a dead entry tuple, which no contrib function exposes. The fill fraction is also
   still taken from the rebuild it predicts, and this run widens the problem: across
   nineteen rebuilds it ran from 43.28% to 87.96%, and the same index rebuilt at
   4MB is 22% smaller than at 64MB, so the divisor is a property of the rebuild
   rather than of the index.
3. **One page size and one alignment.** The FSM cross-check derives
   `MaxFSMRequestSize` from `pg_control_init()` and the layout probe measures
   `SizeOfPageHeaderData` as 24 and `sizeof(ItemIdData)` as 4 on the running build,
   and both reached 8160 again on this cluster. But everything was measured at
   `block_size` 8192 with `MAXALIGN` 8, and no build at another `BLCKSZ` was made,
   so the general correctness of the derived expressions off the default is argued
   rather than measured. The known risk there is 12.2's `smallint` `page_header`
   columns, which would overflow at `BLCKSZ` 32768.
4. **The lower bound now has a rule and the rule needs a rebuild to evaluate.**
   `waste <= reclaimed` holds exactly when the aged in-use core is at least as big
   as the rebuild, and both of this run's violations are that inequality going the
   other way on an index whose pages were packed by pending-list merges. There is
   still no way to evaluate the rule in advance on an index you have not rebuilt,
   which is why the column is now a level.
5. **A concurrent VACUUM can still produce an arbitrary reading, and the progress
   views only usually catch it.** Four censuses across one VACUUM read four
   different dead-page counts between 0 and 768 on an unchanging file; three were
   flagged and one was not. Nothing was measured for several simultaneous vacuums,
   for a census straddling a `REINDEX CONCURRENTLY` swap (in three attempts here and
   22 across two earlier servers it always landed between censuses, never inside
   one), or for how wrong a single unflagged census can get in the worst case.
   The 2026-09-16 review adds a bound on how repeatable the case itself is: on one
   pass the unlocked loop read 5 censuses with 4 flagged, on the other 4 with 4
   flagged and a maximum of 721 rather than 768 dead pages, and the 2026-09-24 run
   read 4 with 3 flagged. So "three of four" is one machine's arrival pattern and
   not a property of the engine.
6. **The opclass sweep is one fixture per opclass.** Six shapes were scored here —
   `array_ops` on `int[]`, `jsonb_path_ops`, `gin_trgm_ops`, `btree_gin`, plain
   `tsvector`, multicolumn and partial. Untested: `jsonb_ops`, `text[]`, weighted
   `tsvector`, collation-dependent text keys, and any opclass under a *mixture* of
   surviving and dying keys other than the five-point `tsvector` sweep.
7. **The exact commit behind the 12.2/17.11 build-memory divergence was never
   identified**, and this run did not revisit it: the effect was measured in the
   two-major pass and the mechanism is in the source (`GetMemoryChunkSpace` includes
   allocator overhead in the budget), but attributing it to a release would need
   per-major builds of the intermediate versions.
8. **Only 12.2 and 17.11 have ever been run, so every cross-major difference is a
   range, not a boundary.** v13 through v16 were not built. The 12.2 leg has had its
   own script since 2026-09-24 and was re-run that day, but as a portability battery,
   not the corpus. The two most consequential untested inferences are that a
   12.11-or-later server behaves like 17.11 on all-zero pages, which follows from
   `cd4868a5700`'s `Backpatch-through: 10` and the `REL_12_11` tag on its 12-branch
   back-patch, and that a 12.17-or-later server refuses `pgstatginindex` on an
   invalid index, which follows from `13503eb5905`'s back-patch `975ae05537` and its
   `REL_12_17` tag. Neither was executed.
9. **The census of the protocol has no 12.x port.** It reads
   `autovacuum_vacuum_insert_threshold`, which does not exist on 12.2, and uses
   `pg_current_xact_id()` in the horizon sequence beside it, which does not either.
   What the simulated auto-analyze census would decide on that server is unknown.
10. **`bloat_pct` has no actionable threshold.** No reading of it is known to mean
    "rebuild this index": its floor is a fresh build's fill, which ran from 43.28%
    to 87.96% here and moves with the rebuild's `maintenance_work_mem`, so a
    threshold would have to be per-opclass and per-budget. What a baseline reading
    costs to establish — a rebuilt twin, or a stored history of the same index — is
    still unmeasured.
11. **The protocol's own hole is open by design.** No lock available from SQL
    excludes a direct `gin_clean_pending_list()` by the index's owner, and this run
    measured what that costs: `bloat_pct` 1.46 to 92.00 between two censuses in one
    locked transaction, neither of them flagged for it. Also untested: whether
    autovacuum is cancelled or merely queued when the protocol lock is requested
    while it runs, the protocol under several simultaneous vacuums, and the
    write-blocking cost on a multi-GB index, where the 214 ms measured here is not a
    guide.
12. **A standby is outside the protocol and stays a spot check.** The three
    refusals were reproduced on a `pg_basebackup` replica and the census answered
    there, but the settle step cannot run on a standby at all, so no standby number
    is scored and no standby fixture exists.
13. **The shape that breaks the upper bound is no longer on the page.** The two
    pre-protocol upper-bound violations lived on fixtures whose recipes were never
    published — an 800,000-row `jsonb_path_ops` index carrying 819,770 dead entry
    tuples, and a pending-list-grown `tsvector` index — so this run's 19 of 19 is
    "not refuted" rather than "held". A conforming fixture that reproduces a large
    dead-entry-tuple population at scale is the missing test, and until it exists
    the upper bound is weaker than its verdict column suggests.
14. **Four findings went out with their fixtures.** The flush-growth rules (the
    pending list is built from the FSM's free stock; a flush cannot reuse the pages
    it is freeing), the round-five entry-tree cascade, the second lower-bound
    violation, and the null-category entry-tuple identity were each measured on a
    fixture this page cannot rebuild. The source arguments behind them are intact
    and cited elsewhere on the page; the measurements are gone. Re-deriving any of
    them needs a new fixture with a published recipe.
15. **The crash path is not re-run, and no test reaches a `VACUUM` that skipped
    index cleanup.** The crash path produced zeroed pages in 2 of 4 attempts once and
    0 of 2 on another machine, which is a rate and not a rule; the appended-zero-block
    case reaches the same page state deterministically, so what is unknown is only
    whether a real crash still leaves such pages as filed. Since 2026-09-24 the
    protocol requires no "`VACUUM` whose index cleanup did not run" in any of its
    three spellings - `INDEX_CLEANUP OFF`, the `vacuum_index_cleanup` reloption, or the
    wraparound failsafe - and this page's fixture for the first two was removed. What
    that leaves unmeasured on this pin is the claim the fixture used to carry: that a
    census and the metapage cannot tell afterwards that such a `VACUUM` ran. The page
    now states it from source alone: the cleanup call is made only while
    `do_index_cleanup` is set, and both spellings of `INDEX_CLEANUP` off and the
    failsafe clear it
    ([vacuum.c:2155-2178](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2155-L2178),
    [vacuumlazy.c:392-401](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L401),
    [vacuumlazy.c:1064-1066](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1064-L1066),
    [vacuumlazy.c:2323-2335](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2335)).
16. **What a census costs a production cache is unmeasured on this pin.** The
    `pg_buffercache` experiment was removed as a synthetic workload outside the
    protocol. The source argument stands — no ring buffer, one read per page, so the
    census's own pages are the cheapest victims in the clock sweep — and the cost
    numbers this page does carry are buffer counts and elapsed times, not eviction.
17. **One pair of numbers did not reproduce, and the cause is inferred.** `f3_fresh`
    and `f1`'s rebuild came out 8,192 bytes larger than the superseded corpus
    (10,125,312 against 10,117,120, one entry page), while `f1`'s churned size and
    every other core fixture matched to the byte. The only recipe change that could
    account for it is the protocol's build-phase settle step, which moves where
    `f1`'s churn puts its new heap tuples and therefore which TIDs a later fresh
    build sees. That was not tested by holding the settle step out, so it is an
    inference. The 2026-09-16 review and the 2026-09-24 passes make the *new* number
    the stable one - every pass since has read 10,125,312 - which rules out a one-off
    and leaves the mechanism still untested.
18. **The `statement_timeout` leg was not re-run.** This run exercised
    `lock_timeout` ten times from the other side of the protocol lock, but not a
    census cancelled mid-scan, which is the case that matters on a multi-GB index.
19. **Closed: the published SQL now reproduces the page.** Every fixture recipe,
    every published statement and every stage of the programme lives in
    [the script](#the-postgresql-1711-leg), so the corpus is rebuildable from this page alone.
    Two fixture families that could not be expressed that way were removed rather
    than described; see
    [What this pass removed, and why](#what-this-pass-removed-and-why).
20. **Closed: the page is scored under the shared protocol.** [Mandatory GIN Bloat
    Tests](../../common-concepts/mandatory-gin-bloat-tests.md) defines the phases,
    the settle and maintenance steps, the census, the lock, the oracle, the
    declare-then-score rule and the cross-checks, and the 2026-09-15, 2026-09-16 and
    2026-09-24 runs performed all of them: declarations filed before the first fixture existed, a recorded
    baseline per fixture, the churn phase ending in settle → maintenance → census, a
    decide pass under one `SHARE ROW EXCLUSIVE` transaction, and a measured rebuild
    with `truth_pct` published beside every scored column. What conformance does
    **not** claim: the protocol's vacuum side is recorded and never simulated, two
    of the stand-in's three differences from an autovacuum worker stand, and the
    coverage row for a second `maintenance_work_mem` is satisfied by one index
    rather than by the corpus, and the page has not adopted the protocol's no-defeat
    rule (open question 24).
21. **Run-to-run stability is now measured on two platforms.** Six full passes of
    the fixture programme have run on this pin: three on Linux x86_64 (2026-09-15, and
    two on 2026-09-16) and three on Darwin 27 arm64 (2026-09-24). The recorded
    2026-09-24 run agrees with the 2026-09-16 filing on every scored cell, and so did
    that day's baseline pass of the filed script, so at `block_size` 8192 and
    `MAXALIGN` 8 the fixture sizes did not depend on the operating system, compiler,
    CPU architecture or core count. One pass moved one fixture by one page; see open
    question 23. What moves between passes is elapsed time, the lock-timeout
    cancellations, the queued VACUUM's wait and concurrency cases A and D. Two limits
    stand: the baseline and middle passes ran earlier revisions of the script - the
    filed one, and one before its report files - so their numbers predate the script
    text filed now and only the recorded run's come from it; and a second `BLCKSZ`,
    which open question 3 wants, is still unbuilt.
22. **Numbers from earlier passes stay on the page without a script.** The sections
    kept as history - *Plan review*, *Deviations from the brief*, the guarded and
    derived statements' agreement counts, the *Context Reviewed* bullets - and many
    Evidence Map rows whose evidence is a `server:` note from an earlier pass report
    numbers that no script on this page reproduces, because their fixtures or
    experiments were removed. They are that pass's record, not re-measured claims.
    Scripting or removing each of them is a larger revision than this pass made.
23. **One pass in six moved `g50_gin` by one page, and why is not established.** In
    the middle 2026-09-24 pass, whose fixture recipes are the ones filed below, the
    maintenance step's VACUUM of `s50` printed `index scan bypassed: 2 pages from table
    (0.07% of total) have 272 dead item identifiers`, and its ANALYZE then counted 272
    dead rows. So the two settle VACUUMs had left dead line pointers on two heap pages,
    and each later VACUUM skipped index vacuuming because fewer than 2% of the table's
    pages held them
    ([vacuumlazy.c:89](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L89),
    [vacuumlazy.c:1899-1948](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1899-L1948)).
    The bypass keeps index cleanup, so the settle step's proofs still pass, but the
    272 TIDs stayed in `g50_gin`. It read 93 data-leaf and 38 deleted pages against
    92 and 39 on every other pass, `bloat_pct` 57.05 against 57.07 and a payload-model
    error of +25.23% against +25.16%; its rebuilt size, its `truth_pct` of 34.37 and
    both bound verdicts did not move. The baseline and recorded passes' maintenance
    VACUUM of `s50` read `index scan not needed`. A settle VACUUM that could not take a cleanup lock
    on two heap pages would explain it: it processes such a page without pruning and
    counts its dead tuples as missed, leaving them for the next VACUUM to turn into
    dead line pointers
    ([vacuumlazy.c:923-952](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L923-L952),
    [vacuumlazy.c:1761-1768](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1761-L1768)).
    But only a VERBOSE VACUUM prints the `tuples missed` line that would show it
    ([vacuumlazy.c:664-668](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L664-L668)), and
    the settle VACUUMs are not VERBOSE. Those numbers come from a script revision
    earlier than the one filed below, whose churn is the same.
24. **The page has not adopted the protocol's no-defeat rule.** [Mandatory GIN Bloat
    Tests](../../common-concepts/mandatory-gin-bloat-tests.md) gained *The maintenance
    must not be defeated* on 2026-09-15, after this page's last protocol re-port. The
    other consumer pages adopted it on 2026-09-16 and 2026-09-17; on 2026-09-24 the
    asker scoped this pass to removing the one test the rule's newest revision
    forbids. So the script's settle and maintenance statements still run in sessions
    with `statement_timeout = 600s` and `lock_timeout = 2s`, and the run records none
    of the rule's four proofs per fixture: the completed statement with no skip line,
    VERBOSE's `dead but not yet removable` count, the horizon holders, and an
    entry-side reading. The recorded run's churn output does show `0 are dead but not
    yet removable` on all 37 of its VERBOSE VACUUMs, but the script neither checks
    that nor fails on it.

## Source References

- [src/backend/catalog/index.c](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789) — replacement storage and rebuild in `reindex_index`.
- [src/backend/access/gin/ginvacuum.c](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L507-L558) — reconstructing an entry tuple after deleting all posting-list items.
- [src/backend/access/gin/gininsert.c](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L276-L406) — memory-triggered accumulator flush and heap-scan build.
- [src/backend/access/index/indexam.c](../../../../raw/postgres-17/src/backend/access/index/indexam.c#L748-L777) — index vacuum callback dispatch.
- [src/backend/access/heap/vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L401) and [vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2323-L2335) — disabled cleanup and failsafe paths.
- [src/backend/commands/vacuum.c](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2155-L2178) — the table cleanup option.
- [src/backend/utils/adt/dbsize.c](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L301-L370) — fork-specific file-length calculation.
- [src/backend/optimizer/prep/prepjointree.c](../../../../raw/postgres-17/src/backend/optimizer/prep/prepjointree.c#L1689-L1701) and [prepjointree.c](../../../../raw/postgres-17/src/backend/optimizer/prep/prepjointree.c#L1772-L1781) — subquery pull-up restrictions.
- [contrib/pageinspect/Makefile](../../../../raw/postgres-17/contrib/pageinspect/Makefile#L3-L35) — decoder objects, SQL upgrades, and regression targets.
- [contrib/amcheck/Makefile](../../../../raw/postgres-17/contrib/amcheck/Makefile#L3-L13) — heap and B-tree verification objects and tests.
- [src/include/catalog/Makefile](../../../../raw/postgres-17/src/include/catalog/Makefile#L126-L143) — generated catalog-header dependency rules.
- [configure.ac](../../../../raw/postgres-17/configure.ac#L267-L288) — configured block sizes.
- [contrib/pgstattuple/pgstattuple.c](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L236-L308) — `pgstat_relation`'s relkind/AM dispatch and the GIN refusal.
- [contrib/pgstattuple/pgstattuple.c:544](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L544) — `BAS_BULKREAD` for index scans.
- [contrib/pgstattuple/pgstatindex.c](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L484-L577) — `pgstatginindex` and its metapage-only read.
- [contrib/pgstattuple/pgstattuple--1.4--1.5.sql](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L49-L57) — the `pg_stat_scan_tables` grant for `pgstatginindex(regclass)`.
- [contrib/pageinspect/rawpage.c](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L141-L234) — `get_raw_page_internal` and `get_page_from_raw`.
- [contrib/pageinspect/ginfuncs.c](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L30-L285) — all three GIN inspection functions.
- [contrib/pageinspect/pageinspect--1.9--1.10.sql](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.9--1.10.sql#L10-L21) — the `page_header` signature in use, `int` where 12.2 has `smallint`.
- [contrib/pageinspect/pageinspect--1.8--1.9.sql](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.8--1.9.sql#L46-L58) — `get_raw_page`'s block number widened to `int8`, which is why 12.2 needs the `::int` cast.
- [contrib/pageinspect/sql/gin.sql](../../../../raw/postgres-17/contrib/pageinspect/sql/gin.sql#L35-L39) and [contrib/pageinspect/expected/gin.out](../../../../raw/postgres-17/contrib/pageinspect/expected/gin.out#L57-L70) — the all-zero-page expectations.
- [contrib/pg_freespacemap/pg_freespacemap.c](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap.c#L18-L50) — `pg_freespace`.
- [contrib/pg_freespacemap/pg_freespacemap--1.1.sql](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap--1.1.sql#L6-L25) — both SQL forms and the initial revokes.
- [contrib/amcheck/amcheck--1.0.sql](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.0.sql#L9-L24) — the only verifiers amcheck ships for indexes.
- [src/include/access/ginblock.h](../../../../raw/postgres-17/src/include/access/ginblock.h#L29-L138) — opaque data, flags, metapage, delete xid.
- [src/include/access/ginblock.h](../../../../raw/postgres-17/src/include/access/ginblock.h#L242-L314) — `GinMaxItemSize`, posting-tree layout, `GinDataLeafPageGetFreeSpace`, the `pd_lower` trust note, `GinDataPageSetDataSize`.
- [src/backend/access/gin/ginvacuum.c](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L126-L338) — `ginDeletePage` and `ginScanToDelete`.
- [src/backend/access/gin/ginvacuum.c](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L694-L829) — `ginvacuumcleanup` and `GinPageIsRecyclable`.
- [src/backend/access/gin/ginfast.c](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L547-L671) — `shiftList`.
- [src/backend/access/gin/ginfast.c](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1014-L1091) — the end of `ginInsertCleanup` and `gin_clean_pending_list`.
- [src/backend/access/gin/ginutil.c](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L294-L382) — `GinNewBuffer`, `GinInitPage`, `GinInitMetabuffer`.
- [src/backend/access/gin/ginentrypage.c](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L458-L692) — `entryIsEnoughSpace` and `entrySplitPage`.
- [src/backend/access/gin/gindatapage.c](../../../../raw/postgres-17/src/backend/access/gin/gindatapage.c#L396-L528) — `pd_lower` maintenance and the compressed-only free-space rule.
- [src/backend/access/gin/README](../../../../raw/postgres-17/src/backend/access/gin/README#L389-L412) — the page-deletion design.
- [src/backend/storage/freespace/indexfsm.c](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L14-L74) — the index FSM's used/unused convention, `GetFreeIndexPage` and `RecordFreeIndexPage`.
- [src/backend/storage/freespace/freespace.c](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L36-L66) — the FSM category table and `MaxFSMRequestSize`.
- [src/backend/storage/freespace/freespace.c](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L118-L204) — `GetPageWithFreeSpace` and `RecordPageWithFreeSpace`'s bottom-level-only warning.
- [src/backend/storage/freespace/freespace.c](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L648-L691) — `fsm_set_and_search` and `fsm_search`, which starts at the root.
- [src/backend/storage/freespace/README](../../../../raw/postgres-17/src/backend/storage/freespace/README#L183-L188) — when upper-level FSM nodes are brought up to date.
- [src/backend/storage/page/bufpage.c](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L898-L973) — `PageGetFreeSpace` and `PageGetExactFreeSpace`.
- [src/include/storage/bufpage.h](../../../../raw/postgres-17/src/include/storage/bufpage.h#L211-L234) — `SizeOfPageHeaderData` and `PageIsNew`.
- [src/backend/storage/buffer/freelist.c](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L314-L341) — the clock sweep that decrements usage counts and takes the first zero.
- [src/include/storage/buf_internals.h](../../../../raw/postgres-17/src/include/storage/buf_internals.h#L72-L79) — `BM_MAX_USAGE_COUNT` and why it is small.
- [src/backend/storage/buffer/bufmgr.c](../../../../raw/postgres-17/src/backend/storage/buffer/bufmgr.c#L2700-L2705) — `PinBuffer` raising the usage count on an unstrategised read.
- [src/backend/utils/misc/pg_controldata.c](../../../../raw/postgres-17/src/backend/utils/misc/pg_controldata.c#L203-L228) — `pg_control_init`, source of `max_data_alignment` and `database_block_size`.
- [src/backend/access/gin/gininsert.c](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L283-L303) — `ginBuildCallback` dumping the accumulator when `maintenance_work_mem` is reached.
- [src/include/access/gin_private.h](../../../../raw/postgres-17/src/include/access/gin_private.h#L425-L440) — `BuildAccumulator`, including the `allocatedMemory` the flush rule tests.
- [src/backend/access/gin/ginbulk.c](../../../../raw/postgres-17/src/backend/access/gin/ginbulk.c#L120-L190) — the accumulator's `GetMemoryChunkSpace` accounting.
- [src/backend/utils/mmgr/mcxt.c](../../../../raw/postgres-17/src/backend/utils/mmgr/mcxt.c#L718-L730) — `GetMemoryChunkSpace`, which counts allocation overhead inside the build budget.
- [src/backend/utils/misc/guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2466-L2474) — `maintenance_work_mem`, `PGC_USERSET`, default 65536 kB.
- [src/backend/utils/misc/guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3359-L3366) — `autovacuum_vacuum_insert_threshold`, `PGC_SIGHUP`, absent on 12.2.
- [src/backend/access/heap/vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L731) — the per-index VACUUM VERBOSE line.
- [src/backend/access/heap/heapam.c](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L434-L458) — the `NBuffers / 4` seq-scan ring-buffer rule the census does not have.
- [src/backend/storage/ipc/procarray.c](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1966-L1991) — horizon selection when the relation is NULL.
- [src/backend/utils/misc/guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585) — `gin_pending_list_limit`.
- [src/backend/utils/misc/guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1449-L1457) — `autovacuum` is `PGC_SIGHUP`, so a reload turns the pending-list flusher on.
- [doc/src/sgml/gin.sgml](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L500-L537) — GIN fast update.
- [doc/src/sgml/pgstattuple.sgml](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L298-L350) — `pgstatginindex` output columns.
- [doc/src/sgml/pageinspect.sgml](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L634-L712) — the documented GIN functions.
- [doc/src/sgml/pgfreespacemap.sgml](../../../../raw/postgres-17/doc/src/sgml/pgfreespacemap.sgml#L61-L71) — what the FSM means for indexes.
- [doc/src/sgml/func.sgml](../../../../raw/postgres-17/doc/src/sgml/func.sgml#L30104-L30123) — `gin_clean_pending_list`.
- [contrib/pageinspect/pageinspect--1.5.sql](../../../../raw/postgres-17/contrib/pageinspect/pageinspect--1.5.sql#L246-L268) — the two GIN decoders are declared `STRICT`.
- [doc/src/sgml/ref/create_function.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/create_function.sgml#L395-L400) — a strict function is not executed on a null argument.
- [src/backend/executor/execSRF.c](../../../../raw/postgres-17/src/backend/executor/execSRF.c#L188-L196) — the executor's null-argument check before calling a function in `FROM`.
- [src/include/storage/bufpage.h](../../../../raw/postgres-17/src/include/storage/bufpage.h#L314-L317) — `PageGetSpecialSize`, the quantity both decoders check.
- [contrib/pageinspect/ginfuncs.c](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L52-L67) — the metapage decoder's special-size and flags errors.
- [contrib/pageinspect/ginfuncs.c](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L122-L128) — the opaque decoder's special-size error.
- [contrib/pageinspect/ginfuncs.c](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c#L137-L160) — the eight named flag bits and the hexadecimal fallback.
- [src/backend/catalog/system_views.sql](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1188-L1207) — `pg_stat_progress_analyze`.
- [src/backend/catalog/system_views.sql](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1209-L1227) — `pg_stat_progress_vacuum`.
- [src/backend/catalog/system_views.sql](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1256-L1289) — `pg_stat_progress_create_index`.
- [src/backend/catalog/system_views.sql](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L670-L703) — `pg_stat_all_tables`, including `last_vacuum` and `vacuum_count`.
- [src/backend/access/heap/vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L392-L396) — `INDEX_CLEANUP OFF` disables index vacuuming and cleanup up front.
- [src/backend/access/heap/vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L696-L712) — the `index scan bypassed` messages.
- [src/backend/access/gin/gininsert.c](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L290-L291) — the accumulator flush at `maintenance_work_mem`.
- [src/backend/utils/adt/dbsize.c](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L370) — `pg_relation_size(regclass, text)`, the second size reading.
- [src/backend/storage/lmgr/lock.c](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L59-L104) — the lock-mode conflict table the protocol is chosen from.
- [src/include/storage/lockdefs.h](../../../../raw/postgres-17/src/include/storage/lockdefs.h#L28-L48) — the eight lock modes and their numbering.
- [src/backend/commands/lockcmds.c](../../../../raw/postgres-17/src/backend/commands/lockcmds.c#L70-L107) — `LOCK TABLE`'s relkind restriction, which is why an index cannot be locked.
- [src/backend/commands/lockcmds.c](../../../../raw/postgres-17/src/backend/commands/lockcmds.c#L279-L299) — `LockTableAclCheck`, the privileges each mode needs.
- [src/backend/commands/vacuum.c](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2049-L2056) — VACUUM's table lock mode, and `AccessExclusiveLock` for FULL.
- [src/backend/commands/analyze.c](../../../../raw/postgres-17/src/backend/commands/analyze.c#L135-L145) — ANALYZE's `ShareUpdateExclusiveLock`.
- [src/backend/commands/indexcmds.c](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L672-L680) — `reindex_index`'s table lock: `ShareLock`, or `ShareUpdateExclusiveLock` when concurrent.
- [src/backend/commands/indexcmds.c](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2860-L2872) — the matching lock level in the `REINDEX` name-lookup callback.
- [src/backend/access/gin/ginfast.c](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1031-L1041) — `gin_clean_pending_list` opening the index at `RowExclusiveLock`, the protocol's one hole.
- [src/backend/storage/page/bufpage.c](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L42-L60) — `PageInit`, which writes the two constants the layout probe reads back.
- [src/backend/storage/page/bufpage.c](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L88-L124) — `PageIsVerifiedExtended`'s header-sanity test, the limit of any SQL guard.
- [src/include/storage/bufpage.h](../../../../raw/postgres-17/src/include/storage/bufpage.h#L143-L172) — the page-size constraints and `PageHeaderData`'s fixed-width fields.
- [src/include/storage/itemid.h](../../../../raw/postgres-17/src/include/storage/itemid.h#L25-L32) — `ItemIdData`, three bit-fields totalling 32 bits.
- [src/include/access/ginblock.h](../../../../raw/postgres-17/src/include/access/ginblock.h#L19-L37) — the "only 8 bytes" comment and `GinPageOpaqueData`.
- [src/include/access/ginblock.h](../../../../raw/postgres-17/src/include/access/ginblock.h#L180-L188) — `PostingItem`, 10 bytes on an internal data page.
- [src/include/access/ginblock.h](../../../../raw/postgres-17/src/include/access/ginblock.h#L336-L344) — `GinPostingList` and its `SHORTALIGN`ed segment size.
- [src/backend/access/gin/ginentrypage.c](../../../../raw/postgres-17/src/backend/access/gin/ginentrypage.c#L555-L568) — `entryExecPlaceToPage`'s `PageAddItem`, one line pointer per entry tuple.
- [src/backend/commands/vacuum.c](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1244-L1298) — `vacuum_xid_failsafe_check` and its `autovacuum_freeze_max_age * 1.05` floor.
- [src/backend/access/heap/vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2299-L2348) — `lazy_check_wraparound_failsafe`: three flags cleared, one WARNING.
- [src/backend/access/heap/vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L705-L711) — `VacuumFailsafeActive` choosing `index scan bypassed by failsafe:`.
- [src/backend/utils/misc/guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2706-L2714) — `vacuum_failsafe_age`, `PGC_USERSET`.
- [src/backend/utils/misc/guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3376-L3387) — `autovacuum_freeze_max_age`, `PGC_POSTMASTER`, minimum 100000.
- [src/backend/utils/misc/guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L1123-L1136) — `zero_damaged_pages`, `PGC_SUSET`, and what it destroys.
- [doc/src/sgml/mvcc.sgml](../../../../raw/postgres-17/doc/src/sgml/mvcc.sgml#L1023-L1044) — the `SHARE ROW EXCLUSIVE` conflict set.
- [doc/src/sgml/ref/lock.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/lock.sgml#L167-L179) — the privileges `LOCK TABLE` requires per mode.
- [src/backend/postmaster/autovacuum.c](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2993-L3110) — the effective reloption-or-GUC values, the `autovacuum_enabled` short circuit, the three thresholds and the strictly-greater verdicts the census recomputes, plus `do_autovacuum`'s relkind filter and `extract_autovac_opts`.
- [src/include/utils/rel.h](../../../../raw/postgres-17/src/include/utils/rel.h#L308-L326) — `AutoVacOpts`, where an unset per-table setting reads back below zero.
- [src/backend/access/common/reloptions.c](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L105-L113) — `autovacuum_enabled` and the lock an `ALTER TABLE` takes to set it; the `vacuum_index_cleanup` enum is at [#L509-L520](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L509-L520).
- [src/backend/utils/activity/pgstat.c](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L117-L122) and [pgstat.c](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L583-L600) — the unforced flush interval, and the flush that publishes a backend's table counts.
- [src/backend/utils/activity/pgstat_relation.c](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L331-L337) and [pgstat_relation.c](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L855-L860) — `pgstat_report_analyze`'s reset of `mod_since_analyze`, and the flush that adds to it.
- [src/include/catalog/pg_proc.dat](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L5911-L5920) — `pg_stat_clear_snapshot` and `pg_stat_force_next_flush`.
- [src/test/regress/sql/stats.sql](../../../../raw/postgres-17/src/test/regress/sql/stats.sql#L101-L110) — the engine's own force-flush-then-read sequence under `stats_fetch_consistency = snapshot`.
- [src/include/access/htup_details.h](../../../../raw/postgres-17/src/include/access/htup_details.h#L563) — `MaxHeapTupleSize`, which is what `MaxFSMRequestSize` resolves to.
- [contrib/pageinspect/pageinspect.control](../../../../raw/postgres-17/contrib/pageinspect/pageinspect.control#L1-L5), [contrib/pgstattuple/pgstattuple.control](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.control#L1-L5), [contrib/pg_freespacemap/pg_freespacemap.control](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap.control#L1-L5) — the three extension versions this procedure installs.
- [contrib/pg_freespacemap/pg_freespacemap--1.1--1.2.sql](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap--1.1--1.2.sql#L6-L7) — the `pg_stat_scan_tables` grant on both `pg_freespace` forms.
- [contrib/amcheck/amcheck--1.2--1.3.sql](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.2--1.3.sql#L9-L21) and [amcheck--1.3--1.4.sql](../../../../raw/postgres-17/contrib/amcheck/amcheck--1.3--1.4.sql#L11-L24) — the heap and B-tree verifiers, and the absence of a GIN one.
- [contrib/pgstattuple/sql/pgstattuple.sql](../../../../raw/postgres-17/contrib/pgstattuple/sql/pgstattuple.sql#L47-L63) — the shipped `pgstattuple` tests, which cover metapage reads and wrong access methods and not this report.
- [doc/src/sgml/regress.sgml](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59) — `make check`, which the measurement script runs on the build it measures.
- [src/backend/parser/gram.y](../../../../raw/postgres-17/src/backend/parser/gram.y#L12305-L12320) — the `LOCK TABLE` grammar the measurement protocol uses.
- [src/backend/access/heap/vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L89) and [vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1899-L1948) — `BYPASS_THRESHOLD_PAGES` and the index-vacuum bypass that keeps index cleanup.
- [src/backend/access/heap/vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L923-L952), [vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1761-L1768) and [vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L664-L668) — the cleanup-lock fallback, the dead tuples it leaves unpruned, and the `tuples missed` line only VERBOSE prints.
- [doc/src/sgml/ref/pg_basebackup.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/pg_basebackup.sgml#L499-L504) and [pg_basebackup.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/pg_basebackup.sgml#L968-L971) — `--checkpoint`'s `spread` default, and the idle wait for the starting checkpoint.
- [src/backend/access/transam/xlog.c](../../../../raw/postgres-17/src/backend/access/transam/xlog.c#L8940-L8959) — `do_pg_backup_start` requests an immediate checkpoint only when asked for a fast one.
- [contrib/pageinspect/rawpage.c](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L266) — `page_header` decodes its input through `get_page_from_raw`.

## Navigation

- [v17/index](../../index.md)
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
- [Wiki Glossary (unverified)](../../../glossary.md) - the shared vocabulary this page links on first use
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [v17 common concept: Mandatory GIN Bloat Tests (unverified)](../../common-concepts/mandatory-gin-bloat-tests.md) — the protocol every number on this page was scored under
- [Detecting Inflated Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17 (unverified)](non-btree-index-inflation-comment-baseline.md)
- [B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17 (unverified)](btree-bloat-with-pgstatindex.md)
- [PostgreSQL 17 Contrib Extensions (unverified)](../server-administration/contrib-extensions.md)
- [v12/index](../../../v12/index.md) — the pin the 12.2 column was measured against
- [v12: Physical Index Statistics, Tuple Counts, and Bytes per Tuple (unverified)](../../../v12/questions/indexing/physical-index-statistics-tuple-counts-and-bytes.md) — the v12-side GIN page and metapage fields, cited against the v12 checkout
