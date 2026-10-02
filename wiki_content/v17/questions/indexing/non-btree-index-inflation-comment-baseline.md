---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# Detecting Inflated Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
  - [Prompt corrections](#prompt-corrections)
  - [The first prompt](#the-first-prompt)
  - [The 2026-08-25 review prompts](#the-2026-08-25-review-prompts)
  - [The 2026-09-15 review prompt](#the-2026-09-15-review-prompt)
  - [The 2026-09-16 review prompt](#the-2026-09-16-review-prompt)
  - [The 2026-09-24 prompt](#the-2026-09-24-prompt)
- [Answer](#answer)
  - [Verdict](#verdict)
  - [What conformance to the two protocols changed](#what-conformance-to-the-two-protocols-changed)
  - [The maintenance was not defeated](#the-maintenance-was-not-defeated)
  - [What a defeated VACUUM looks like, measured](#what-a-defeated-vacuum-looks-like-measured)
  - [Why REINDEX is the only thing that shrinks these five access methods](#why-reindex-is-the-only-thing-that-shrinks-these-five-access-methods)
  - [Why a current-over-baseline size ratio is the wrong question](#why-a-current-over-baseline-size-ratio-is-the-wrong-question)
  - [Three catalog facts the design depends on](#three-catalog-facts-the-design-depends-on)
  - [The baseline field set](#the-baseline-field-set)
  - [The comment format](#the-comment-format)
  - [SQL 1: capture a fresh baseline](#sql-1-capture-a-fresh-baseline)
  - [SQL 2: read the baseline back](#sql-2-read-the-baseline-back)
  - [SQL 3: evaluate](#sql-3-evaluate)
  - [Access-method-specific normalization](#access-method-specific-normalization)
  - [The declared kind of every published column](#the-declared-kind-of-every-published-column)
  - [The phases every fixture ran](#the-phases-every-fixture-ran)
  - [The 29 scored fixtures and their results](#the-29-scored-fixtures-and-their-results)
  - [The declared upper bound failed, so est_reclaim_pct is a level](#the-declared-upper-bound-failed-so-est_reclaim_pct-is-a-level)
  - [How close the prediction came](#how-close-the-prediction-came)
  - [The maintenance pair: what the maintenance step moves](#the-maintenance-pair-what-the-maintenance-step-moves)
  - [The BRIN summarization stand-in](#the-brin-summarization-stand-in)
  - [Both auto-analyze stand-ins make the method refuse](#both-auto-analyze-stand-ins-make-the-method-refuse)
  - [BRIN: desummarize plus summarize made the index bigger](#brin-desummarize-plus-summarize-made-the-index-bigger)
  - [A hash rebuild is sized from the heap, not from the index](#a-hash-rebuild-is-sized-from-the-heap-not-from-the-index)
  - [The GIN oracle is budget-dependent](#the-gin-oracle-is-budget-dependent)
  - [What an index reltuples means, re-measured](#what-an-index-reltuples-means-re-measured)
  - [The thirteen invariants](#the-thirteen-invariants)
  - [The simulated auto-analyze census](#the-simulated-auto-analyze-census)
  - [The instrument matrix, measured](#the-instrument-matrix-measured)
  - [Handling the four required edge cases](#handling-the-four-required-edge-cases)
  - [Thirteen edge cases, measured](#thirteen-edge-cases-measured)
  - [Experimental thresholds](#experimental-thresholds)
  - [Coverage the protocols require, and what this page skipped](#coverage-the-protocols-require-and-what-this-page-skipped)
  - [What left the page with its fixtures](#what-left-the-page-with-its-fixtures)
  - [Known limitations](#known-limitations)
- [Measurement Script](#measurement-script)
  - [How to use it](#how-to-use-it)
  - [Prerequisites](#prerequisites)
  - [Where the results land](#where-the-results-land)
  - [The last run](#the-last-run)
  - [The script](#the-script)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

### Prompt corrections

Every prompt on this page was filed after prompt-hygiene correction, at the asker's
request. The first prompt wrote `agents.md` for `AGENTS.md`, lowercase `postgresql`,
spaces before commas, `minmax-multi` for the `minmax_multi` opclass family, and
`DESUMMARIZE + SUMMARIZE` for the `brin_desummarize_range()` /
`brin_summarize_range()` functions. Five prompts are filed below, in the order they
arrived. For the first four the asker chose "correct and restate", so each carries its
defects and the corrected form. For the fifth the asker chose "correct silently", so only
the corrected form is filed.

### The first prompt

Follow `AGENTS.md`, in PostgreSQL 17. Question:

Design and validate a PostgreSQL heuristic that detects potentially inflated
non-B-tree indexes using only PostgreSQL catalog information, statistics,
table/index metadata, and information stored directly in the index comment. The
heuristic must estimate whether rebuilding an index would materially reduce its
physical size.

The target index access methods are HASH, GIN, GiST, SP-GiST and BRIN. B-tree
indexes are outside the scope of this work.

**Fundamental constraint.** Do not create any PostgreSQL table, metadata table,
extension-specific repository, or external persistent store for the heuristic. The
only persistent information created by this mechanism must be stored with
`COMMENT ON INDEX ...`, so the baseline must live in the existing PostgreSQL index
comment stored in `pg_description`. Existing human-readable comments must be
preserved. Use a recognizable marker such as `@idxmaint:`, and the heuristic
payload may use compact JSON.

**Baseline concept.** Capture the physical and logical characteristics of an index
immediately after it has been freshly built, that is after `CREATE INDEX`,
`REINDEX INDEX`, or `REINDEX INDEX CONCURRENTLY`. The baseline represents what the
index looked like when freshly built for this logical dataset. It must not be
continuously overwritten during normal monitoring; it remains unchanged until the
index is physically rebuilt, and after a successful `REINDEX` the old baseline is
replaced with a new one.

**Suggested baseline information.** Determine the minimum set of values required,
using catalogs and statistics such as `pg_class`, `pg_index`, `pg_am`,
`pg_namespace`, `pg_stat_all_tables`, `pg_stat_user_tables`, `pg_stat_user_indexes`,
`pg_stats`, `pg_description` and the relation-size functions. Consider storing
heuristic version, baseline timestamp, access method, relation filenode, index size,
index relpages, index reltuples, table relpages, table reltuples, `n_live_tup`,
`n_dead_tup`, `n_tup_ins`, `n_tup_upd`, `n_tup_hot_upd`, `n_tup_del`,
`vacuum_count`, `autovacuum_count`, and statistics reset information. Use
abbreviated JSON field names if appropriate to keep the comment small. Review which
fields are actually useful and remove unnecessary ones.

**Core heuristic.** Distinguish legitimate index growth from physical growth caused
by data churn that could be removed by rebuilding. Do not simply compare
`current_index_size / baseline_index_size`. Instead estimate how large a freshly
rebuilt index should be for the current logical dataset:

```text
expected_fresh_size_now = baseline_index_size
                        * current_logical_population
                        / baseline_logical_population

size_inflation = current_index_size / expected_fresh_size_now
```

For a baseline of 100M logical units at 10 GB and a current state of 120M logical
units at 18 GB, the expected fresh size is 12 GB and the size inflation is 1.50.
Interpret this as approximately 50% larger than predicted by the fresh-build
baseline, not as an exact bloat percentage.

**Churn heuristic.** From the table statistics captured at baseline and the current
cumulative statistics, calculate `delta_inserts`, `delta_non_hot_updates` as
`(current_n_tup_upd - baseline_n_tup_upd) - (current_n_tup_hot_upd -
baseline_n_tup_hot_upd)`, and `delta_deletes`; sum them into
`index_affecting_churn`, and normalize as
`churn_ratio = index_affecting_churn / current_logical_population`. Do not
recommend `REINDEX` solely because churn is high. The strongest signal should be a
combination of normalized size inflation, substantial index-affecting churn,
`VACUUM` having occurred, and a low remaining dead tuple count.

**VACUUM consideration.** Differentiate an index that contains dead entries
`VACUUM` has not yet processed from an index that remains physically inflated even
after `VACUUM`, using baseline and current `vacuum_count`, `autovacuum_count`, or
other suitable catalog/statistics information. A strong `REINDEX` candidate should
generally have high normalized size inflation AND high churn AND `VACUUM` occurred
after significant churn AND a relatively low current dead tuple ratio. This is
intended to identify post-`VACUUM` residual physical inflation.

**Access-method-specific normalization.** Do not assume one logical model works
equally well for every access method.

For HASH use approximately `logical_population = indexed tuples`. HASH should be
one of the highest-confidence access methods. Test both overflow-page growth caused
by a highly duplicated key, and high-water growth where the table/index grows
dramatically and is later reduced to its original logical population. Candidate
starting thresholds may be tested around size inflation >= 1.30 AND churn >= 0.50,
with stronger confidence around size inflation >= 1.50 AND churn >= 1.00. Do not
assume these are final production thresholds.

For GiST start with logical population = estimated indexed tuples, potentially
improved using indexed-value statistics such as average width. Test repeated
changes of indexed range values while keeping row count constant, and high-water
population growth followed by deletion back to baseline. Use built-in PostgreSQL
range types if possible so the test does not require PostGIS, for example
`int8range`. Use more conservative thresholds than HASH.

For SP-GiST use approximately `logical population = indexed tuples`, with possible
adjustment for indexed-value size. Test repeated replacement of text values with
different prefix families while row count stays constant, average text width stays
approximately constant, and indexed values change every round. The objective is to
generate substantial SP-GiST structural churn without legitimate population growth.
Also test temporary high-water growth followed by deletion back to baseline.

GIN requires a more conservative model because one heap row may generate many
indexed entries. Investigate whether normalization should incorporate row count
times average indexed-value width, or another catalog-derived approximation of
logical input mass. Test at least three workloads: (1) common-key posting growth,
using arrays where millions of rows temporarily reference the same few keys, then
deleting those temporary rows, running `VACUUM`, and comparing physical size with a
subsequent `REINDEX`; (2) key churn with constant table population, repeatedly
updating the indexed arrays so each round produces entirely different indexed keys
while row count and average indexed-value width stay approximately constant, run
over several rounds without `VACUUM` and followed by `VACUUM (ANALYZE)`; and (3) a
false-positive control for pending-list behavior, using `fastupdate = on` to
generate a significant pending list and measuring the index before and after
pending-list processing / `VACUUM`. The heuristic must not automatically recommend
`REINDEX` solely because of temporary pending-list growth, and the test should
demonstrate why post-`VACUUM` evaluation is important for GIN.

For BRIN do not use table row count as the primary logical unit. Use approximately
`logical_ranges = ceil(table_relpages / pages_per_range)`, then estimate
`expected_size = baseline_size * current_logical_ranges / baseline_logical_ranges`.
BRIN must have separate tests because it behaves fundamentally differently from
tuple-oriented indexes. BRIN test 1 is a negative control using a standard minmax
BRIN index with massive updates of the indexed values while retaining the same row
population; it should demonstrate that large table churn does not automatically
imply large BRIN physical inflation, and the heuristic should avoid recommending
`REINDEX` based solely on churn. BRIN test 2 uses `minmax_multi` with a suitable
`values_per_range`, starting with strongly correlated data, then changing values so
individual heap ranges contain widely scattered values, then returning the logical
values toward the original correlated pattern; compare after churn + `VACUUM`
against after `REINDEX`. Also investigate whether the more appropriate
recommendation for some BRIN cases is `brin_desummarize_range()` followed by
`brin_summarize_range()` rather than `REINDEX`. The final design should allow
different maintenance recommendations for BRIN.

**Partial indexes.** Partial indexes must not be normalized blindly against
whole-table row count. Use available metadata such as `pg_index.indpred` and
index/table `reltuples`. At baseline calculate an approximate fraction
`baseline_partial_fraction = baseline_index_reltuples / baseline_table_reltuples`,
and at evaluation time `current_partial_fraction = current_index_reltuples /
current_table_reltuples`. If the predicate-selected population changes
substantially, reduce confidence or suppress an automatic `REINDEX`
recommendation. Include tests where the partial-index selectivity changes
dramatically but no meaningful index inflation exists; treat this as a
false-positive test.

**Baseline validity.** Store the relation filenode at baseline. At evaluation time
compare it with `pg_relation_filenode(index_oid)`. If the current filenode differs
from the baseline filenode, assume the physical index has been rebuilt and the old
physical baseline is invalid; the mechanism should then establish a fresh baseline
in the index comment. Also detect situations where cumulative PostgreSQL statistics
have been reset. If churn counters cannot safely be compared, report
`CHURN = UNKNOWN` and do not fabricate a churn estimate; physical size evaluation
may continue, but confidence should be reduced.

**Human comments.** Do not destroy an existing index comment. The implementation
must preserve text that appears before the heuristic marker. When refreshing the
maintenance metadata, replace only the `@idxmaint:` payload.

**Test methodology.** For every inflation-producing test follow approximately:
create a disposable table; disable autovacuum on the test table for deterministic
testing; insert the baseline dataset; `CREATE INDEX`; `ANALYZE`; record the
fresh-build baseline; execute the access-method-specific churn workload; return the
logical indexed population close to baseline where applicable; `VACUUM (ANALYZE)`;
capture current measurements; evaluate the heuristic; `REINDEX INDEX`; `ANALYZE` if
required; measure the index again; and compare the heuristic prediction with the
actual reclaimed space. Do not use `VACUUM FULL` as part of the test, because the
objective is to validate index maintenance behavior, not to rewrite the table.

**Ground-truth validation.** For every test define B as the fresh baseline index
size, C as the index size after churn + `VACUUM`, and R as the index size
immediately after `REINDEX`. The heuristic predicts `estimated_fresh_size` and
`size_inflation = C / estimated_fresh_size`. Calculate
`actual_reclaimed_bytes = C - R` and `actual_reclaimed_fraction = (C - R) / C`. The
purpose of the test suite is to establish whether high heuristic inflation
correlates with significant actual space reclaimed by `REINDEX`.

**Required principal test matrix.** At minimum implement and analyze: HASH with a
highly duplicated hot key (strong physical inflation candidate); HASH growing the
population dramatically then shrinking (strong high-water inflation); GIN
common-key posting growth (possible inflation); GIN repeated complete key
replacement (possible persistent inflation); GIN pending-list-only growth
(false-positive control); GiST repeated range relocation (possible persistent
inflation); GiST population grow/shrink (high-water test); SP-GiST repeated prefix
replacement (possible persistent inflation); SP-GiST population grow/shrink
(high-water test); BRIN minmax with massive indexed-value churn (negative control);
BRIN `minmax_multi` summary expansion/degradation (BRIN-specific maintenance case);
and partial indexes with predicate population changes (false-positive control).

**Output requirements.** Produce a technical assessment of the proposed heuristic;
a description of the baseline fields that should be stored in `COMMENT ON INDEX`;
the proposed compact/versioned comment format; SQL to capture a fresh baseline; SQL
to retrieve and parse the baseline; SQL to calculate current metadata; SQL to
calculate normalized size inflation, insert delta, non-HOT update delta, delete
delta, churn ratio, dead tuple ratio, and whether `VACUUM` occurred since baseline;
access-method-specific heuristic logic for HASH, GIN, GiST, SP-GiST and BRIN;
handling for partial indexes, statistics resets, manual `REINDEX` detected through
filenode changes, and existing human comments; a complete reproducible SQL test for
each access method; positive tests that deliberately produce reclaimable index
inflation; negative/false-positive tests where `REINDEX` should not be recommended;
measurement queries to record baseline size, post-churn size, post-`VACUUM` size and
post-`REINDEX` size; a results table showing predicted inflation, actual reclaimed
bytes, actual reclaimed percentage, heuristic recommendation, and whether the
recommendation was correct; recommendations for initial thresholds, clearly
identified as experimental rather than authoritative; and known limitations and
situations where catalog-only metadata cannot reliably distinguish legitimate
structural growth from reclaimable inflation.

**Design principles.** Do not describe this as an exact bloat measurement. Use
terminology such as index inflation, estimated fresh-build size, reclaimable-space
proxy, `REINDEX` candidate, and maintenance heuristic. The primary question the
heuristic must answer is: given the current logical dataset and the characteristics
captured when this index was freshly built, is the index now materially larger than
we would expect a fresh rebuild to be, after accounting for legitimate data growth
and normal `VACUUM` cleanup? The ultimate success criterion is not whether the
heuristic reports a large number, but whether a high heuristic score reliably
predicts that `REINDEX INDEX` or `REINDEX INDEX CONCURRENTLY` will materially
reduce the physical size of the index.

### The 2026-08-25 review prompts

Both wrote `agents.md` for `AGENTS.md`, lowercase `postgresql`, and a space before a
comma; the second also wrote "run again all tests" for "run all tests again". The
asker chose "correct and restate" each time. The corrected texts are:

> Follow `AGENTS.md`, in PostgreSQL 17, review question: # Detecting Inflated
> Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17
> (unverified)

> Follow `AGENTS.md`, in PostgreSQL 17, review question: # Detecting Inflated
> Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17
> (unverified), run all tests again and check the heuristic

Those two reviews ran before this wiki had a measurement protocol for these access
methods. Their fixtures, their six-run reproducibility claim and their results table
were all produced outside one, and [What left the page with its
fixtures](#what-left-the-page-with-its-fixtures) records what happened to them.

### The 2026-09-15 review prompt

The request read:

> follow agents.md, in postgresql 17, review question: # Detecting Inflated
> Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17
> (unverified), update tests based on the changes from common-concept, update or
> remove all tests that aren't following # Mandatory Non-B-Tree, Non-GIN Bloat Tests
> (unverified) and # Mandatory GIN Bloat Tests (unverified).

The asker chose "correct and restate". The corrections are `agents.md` ->
`AGENTS.md`, lowercase `postgresql` -> `PostgreSQL`, `review question:` -> `review
the question:`, the pasted `# ` heading marker before each of the three page titles,
and `from common-concept` -> `from the common concept pages`, because two concept
pages govern this one. The corrected text is:

> Follow `AGENTS.md`, in PostgreSQL 17, review the question: # Detecting Inflated
> Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17
> (unverified), update tests based on the changes from the common concept pages,
> update or remove all tests that do not follow # Mandatory Non-B-Tree, Non-GIN
> Bloat Tests (unverified) and # Mandatory GIN Bloat Tests (unverified).

Three scoping answers were taken before any edit: a **full re-run with a published
measurement script** rather than a paper re-port; tests that cannot conform are
**removed with the claims they backed**, not relabelled; and **every coverage
behavior the method can reach** is added.

That review finished before either governing concept page carried
[`### The maintenance must not be
defeated`](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md#the-maintenance-must-not-be-defeated),
which was filed the same day. This page had never been checked against it.

### The 2026-09-16 review prompt

The request read:

> follow agents.md, in postgresql 17, review : non-btree-index-inflation-comment-baseline.md

The asker chose "correct and restate". The corrections are `agents.md` ->
`AGENTS.md`, lowercase `postgresql` -> `PostgreSQL`, the space before the colon in
`review :`, the bare filename replaced by the page's own title, the lowercase
sentence opening, and the missing terminal period. The corrected text is:

> Follow `AGENTS.md`, in PostgreSQL 17, review the question: # Detecting Inflated
> Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17
> (unverified).

Two scoping answers were taken before any edit: a **full re-run under the new rule**
rather than a paper audit, and the filed script **edited in place** rather than
replaced. What the review found, and what it changed, is
[The maintenance was not defeated](#the-maintenance-was-not-defeated).

### The 2026-09-24 prompt

Follow `AGENTS.md`, in PostgreSQL 17. Remove the invalid tests from the question
"Detecting Inflated Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in
PostgreSQL 17", and re-run all tests.

Scope, settled with the asker before any edit on 2026-09-24:

- The invalid tests are **fixtures `h06` and `n11` as a whole**. Both ran
  `VACUUM (VERBOSE, ANALYZE, INDEX_CLEANUP OFF)` as their maintenance step. Earlier that
  day both governing concept pages stopped requiring "a `VACUUM` whose index cleanup did not
  run" and stopped declaring it an exception, so neither fixture's maintenance step is the
  effective `VACUUM ANALYZE` the protocols require any more. The fixtures, their declared
  exceptions X3 and X4, their two coverage rows and every claim they backed left the page;
  see [What left the page with its fixtures](#what-left-the-page-with-its-fixtures).
- Two coverage rows this page had filed as reached are now filed as **not reached**, and no
  fixture was added for them: `g08` deletes no page while its snapshot is held, and `n04`
  holds no posting tree.
- "All tests" means the script's whole default order: `make check`, the three contrib
  suites and every stage, run from an empty sandbox. The page has no section outside the
  script.
- The four glossary entries this page needed and lacked were added and checked on
  PostgreSQL 17 only.

## Answer

### Verdict

The design still works as a **ranking and gating** heuristic, and it no longer works
as a reclaimable-space estimate. Under the wiki's two protocols - [Mandatory
Non-B-Tree, Non-GIN Bloat
Tests](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md) for the
[hash](../../../glossary.md#hash-index), [GiST](../../../glossary.md#gist), [SP-GiST](../../../glossary.md#sp-gist) and [BRIN](../../../glossary.md#brin) fixtures and [Mandatory GIN Bloat
Tests](../../common-concepts/mandatory-gin-bloat-tests.md) for the [GIN](../../../glossary.md#gin) ones - **29
scored fixtures** ran build -> baseline -> churn -> maintenance -> census -> a decide
pass under one [`SHARE ROW EXCLUSIVE`](../../../glossary.md#lock-mode) transaction -> a measured [`REINDEX INDEX`](../../../glossary.md#reindex)
oracle, from the one script filed under [Measurement Script](#measurement-script).
Every number on this page comes from a re-run on 2026-09-24 on macOS 27 arm64, after the
two fixtures that switched [index cleanup](../../../glossary.md#index_cleanup) off were removed; see [The 2026-09-24
prompt](#the-2026-09-24-prompt). On the 29 kept fixtures that run reproduced every
recommendation, decision and bound verdict of the 2026-09-16 run on Linux x86_64.

Six results, in the order they matter:

1. **The 2026-09-16 review found the two held-snapshot fixtures never pinned the
   [horizon](../../../glossary.md#xmin-horizon), and fixing them is what makes the new rule checkable.** `g08` and `n10`
   opened their [snapshot](../../../glossary.md#snapshot) *after* the churn committed, so its `xmin` was already past
   the deleting [xid](../../../glossary.md#transaction-id) and nothing was held back. Opened before the churn instead, the
   maintenance [`VACUUM`](../../../glossary.md#vacuum) now reports **240,000** and **960,000 [tuples](../../../glossary.md#tuple) dead but not yet
   removable** and deletes **no [index page](../../../glossary.md#page) at all**, and the `VACUUM` after release
   deletes 2,330 of 2,970 GiST pages and 375 of 479 GIN [posting-tree](../../../glossary.md#posting-tree) pages. See
   [What a defeated VACUUM looks like,
   measured](#what-a-defeated-vacuum-looks-like-measured).
2. **The rule holds everywhere it is not declared.** Four new invariants cover it:
   [`dead but not yet removable`](../../../glossary.md#dead-tuple) is **0 on 23 of 25** `VACUUM`s, and the other 2 are
   the declared snapshots; **0 of 31** maintenance logs were skipped or cut short and
   all four settable timeouts read `0`; **0 overlaps** between 90 census lock
   intervals and 31 maintenance intervals; and **0 [replication slots](../../../glossary.md#replication-slot) and 0 prepared
   transactions** across all 62 horizon readings, whose only [backend](../../../glossary.md#backend) holders are the
   two declared snapshots.
3. **The decision was right on all 29 fixtures**: 0 false positives, 0 false
   negatives, 14 fixtures flagged. Every flagged fixture repaid between 37.6 % and
   85.7 % of its file.
4. **The declared upper bound failed.** `est_reclaim_pct`, filed before the first
   fixture as an upper bound on what a rebuild returns, **held on 18 of 29 and was
   violated on 11**, by up to 10.71 points. It is therefore **demoted to a level**
   and must not be read as reclaimable space; see [The declared upper bound
   failed](#the-declared-upper-bound-failed-so-est_reclaim_pct-is-a-level).
5. **Both [auto-analyze](../../../glossary.md#autovacuum) stand-ins make the method refuse.** A table maintained by
   auto-analyze alone never advances [`vacuum_count`](../../../glossary.md#pg_stat_all_tables), so the method answers
   `inconclusive: no VACUUM since baseline` - on `h05` where a rebuild returned
   11.11 %, and on `n12` where it returned 11.50 %. An untouched index is refused
   too, for the other gate: `inconclusive: no ANALYZE since baseline` on all four
   no-churn fixtures.
6. **The BRIN arm is still unvalidated against a true positive**, for a sharper
   reason than before: all four BRIN fixtures reclaimed **0 bytes**, and all four sit
   below the method's own 1 MB floor. The mandatory maintenance step **grew** three
   of them, which is what the protocol says it must.

Three mechanism findings stand from the previous run and were re-measured here: a
hash rebuild is sized from the **heap's** estimate and not from the index, so forging
the heap's [`reltuples`](../../../glossary.md#reltuples-and-relpages) to 100 made the rebuild **4,775,936 bytes larger** with the
data untouched; a GIN rebuild is a function of [`maintenance_work_mem`](../../../glossary.md#maintenance_work_mem), at 46,784,512
/ 48,021,504 / 49,143,808 bytes for 4MB / 64MB / 256MB; and `brin_page_items` emits a
row for an **unused** [line pointer](../../../glossary.md#line-pointer), so a census that counts its rows over-counts
summary tuples by exactly the orphans a relocated or desummarized range left behind.

The prompt's own hypothesis is refuted again, byte for byte: `brin_desummarize_range()`
followed by `brin_summarize_range()` freed nothing and then made a churned
`minmax_multi` index **71 % larger** than it started, where `REINDEX` returned it
to where it was.

### What conformance to the two protocols changed

The page previously ran its own protocol. Bringing it onto the wiki's two changed
the method, the fixtures and the claims.

| Change | Why the protocol forced it |
|---|---|
| The **pre-`VACUUM` evaluation is gone**, with the three-run claim built on it | Both protocols forbid scoring a method against unmaintained churn, so a number produced from one is not a scored number ([Mandatory Non-B-Tree, Non-GIN Bloat Tests](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md)). The unmaintained state is still **measured** - as a size and page census at `churn_raw` - it is just never handed to the method |
| Every census now runs under **`SHARE ROW EXCLUSIVE` on the index's table** | The measurement lock is mandatory whenever a census is compared with anything, and `SHARE` is one step too weak to exclude a plain `REINDEX` ([indexcmds.c#ReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2824-L2849), [lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L64-L104)) |
| The decide pass is **one statement over every baselined index at once**, not one statement per index | "The text that is scored must be the text that is published." A per-index text with the target substituted is 31 texts; a report over a filter is one, and the `verify` stage diffs it against this page |
| A **declared kind per published column**, filed before the first baseline payload into a database that did not yet exist | Both protocols require the declaration before the run, and forbid rewriting it afterwards |
| A **`truth_pct` column** and a per-AM oracle-justification threshold | `truth_pct` is mandatory for a run to be readable, and a method that decides must declare its own threshold |
| A **simulated auto-analyze census** over all 32 tables in the fixture database | The launcher's analyze verdict is recomputed per table from the effective [reloption](../../../glossary.md#storage-parameter)-or-GUC values, not assumed |
| A **BRIN [summarization](../../../glossary.md#brin-summarization) stand-in** and a pre-maintenance BRIN reading | On BRIN the mandatory maintenance step adds index tuples, and the `autosummarize` work item `brininsert` queues is fulfilled only by an autovacuum worker ([brin.c#brininsert-autosummarize](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L379-L411)) |
| A **GIN auto-analyze stand-in** of [`ANALYZE`](../../../glossary.md#statistics) plus `gin_clean_pending_list()` | GIN is the one core AM that does work in ANALYZE-only mode, and only in an autovacuum worker ([ginvacuum.c#analyze_only-worker](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L729), [analyze.c#analyze-only-cleanup](../../../../raw/postgres-17/src/backend/commands/analyze.c#L694-L721)) |
| **Thirteen invariants and the per-AM cross-checks** | No number is published from a single reading |
| The capture statement **refuses a table that has never been analyzed**, and refreshes only the baselines that no longer describe the physical index | The `reltuples` finding below makes an un-analyzed baseline meaningless, and the prompt requires that a baseline is not continuously overwritten |
| **A horizon reading on each side of every maintenance step, the four settable timeouts forced to `0` in the maintenance session, the `dead but not yet removable` count parsed from every maintenance log, and the lock and maintenance intervals recorded so they can be shown not to overlap** | Added on 2026-09-16 for [The maintenance must not be defeated](#the-maintenance-was-not-defeated), which both concept pages gained after the previous run |
| **No fixture runs a `VACUUM` with index cleanup switched off** | Added on 2026-09-24. Both concept pages stopped requiring such a `VACUUM` as coverage and stopped declaring it an exception to the no-defeat rule, so `h06` and `n11`, whose maintenance step was `VACUUM (ANALYZE, INDEX_CLEANUP OFF)`, left the page; see [What left the page with its fixtures](#what-left-the-page-with-its-fixtures) |

One consequence is worth stating on its own. Because the published statement now
reports over the set of indexes that carry a payload, **an index with no baseline
produces no row at all** instead of a row labelled `unknown: counters reset`. The
mislabel the previous review filed as a known limitation is retired by construction.

### The maintenance was not defeated

Both protocols now carry a rule the 2026-09-15 run predates: a fixture may not carry
a state into the maintenance step that would have stopped a real server's autovacuum,
`VACUUM`, `ANALYZE` or auto-analyze from doing the work the protocol credits it with
([Mandatory Non-B-Tree, Non-GIN Bloat
Tests](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md#the-maintenance-must-not-be-defeated),
[Mandatory GIN Bloat
Tests](../../common-concepts/mandatory-gin-bloat-tests.md#the-maintenance-must-not-be-defeated)).
The maintenance assumption says the command must run; this rule says it must have
been effective. Every failure is silent.

Four things changed in the script to make the rule checkable, and all four are filed
as invariants in the `declare` stage, before any fixture exists.

| Change | Why |
|---|---|
| **The four settable timeouts are forced to `0` in the maintenance session.** The run's own [`statement_timeout = 1800s`](../../../glossary.md#statement_timeout-and-lock_timeout) and `lock_timeout = 15s` are left in place everywhere else | A timeout short enough to fire inside the step leaves a state that is neither churned nor maintained. Forcing them off is what an autovacuum launcher and worker do to themselves, in the engine's own words, "to avoid letting these settings prevent regular maintenance from being executed" ([autovacuum.c#launcher-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L518-L526), [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470)). All four are [`PGC_USERSET`](../../../glossary.md#guc-context), so session/transaction scope ([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631), [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642), [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653)) |
| **Every maintenance step is bracketed by a horizon reading** of [`pg_stat_activity`](../../../glossary.md#pg_stat_activity)'s `xact_start`, `backend_xid` and `backend_xmin`, `pg_replication_slots`' `xmin` and `catalog_xmin`, and `pg_prepared_xacts` | `VACUUM`'s `OldestXmin` comes from `GetOldestNonRemovableTransactionId` ([vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122)), which folds in every backend's `xid` and `xmin`, skipping only `PROC_IN_VACUUM` and `PROC_IN_LOGICAL_DECODING` ([procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815), [procarray.c#skip-vacuum-and-decoding](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1817-L1832)), then takes the older of its answer and any slot's `xmin` ([procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902)). A [prepared transaction](../../../glossary.md#two-phase-commit)'s dummy [`PGPROC`](../../../glossary.md#procarray) is what keeps its xid running with no live session to show for it ([twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26)); the views are [system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L878-L885), [system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017) and [system_views.sql#pg_prepared_xacts](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L421-L426) |
| **Every maintenance log is parsed for its `tuples: ... are dead but not yet removable` count**, and for a `skipping vacuum of`/`skipping analyze of` line or a cancellation | That count is the one positive signal a pinned horizon leaves ([vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L659-L663)); under a pinned horizon `lazy_scan_heap` collects no dead [TIDs](../../../glossary.md#tid), so [`lazy_vacuum`](../../../glossary.md#index-vacuuming) is never entered and the AM's `ambulkdelete` never runs ([vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052)). The skip lines are what a lock conflict produces ([vacuum.c#skip-lock-not-available](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L828-L855)) |
| **Every census records the interval it held the measurement lock**, and every maintenance step the interval it ran in | `SHARE ROW EXCLUSIVE` excludes `VACUUM` and `ANALYZE` by design ([lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L64-L104)), so the protocols allow it only in the decide phase and the censuses around it, never across a maintenance step. Recording both intervals turns that from a structural claim into a checked one |

What the run measured, over 29 fixtures, 31 maintenance steps and 62 horizon
readings:

| Invariant | Result |
|---|---|
| I10 `dead but not yet removable` is 0, or the fixture declares a held snapshot | **25 of 25** `VACUUM`s; 23 read 0, and the only nonzero counts are `g08`/`maint` at 240,000 and `n10`/`maint` at 960,000, both declared |
| I11 no maintenance step was skipped or cut short | **31 of 31** logs with no skip line, **0** cancellations, and exactly one distinct timeout set across every step: `idle_in_transaction_session_timeout=0 lock_timeout=0 statement_timeout=0 transaction_timeout=0` |
| I12 the measurement lock never spans a maintenance step | **90** census lock intervals against **31** maintenance intervals, **0** overlaps |
| I13 no undeclared horizon holder | **58 of 62** readings entirely clean; the 4 that are not are `g08` and `n10` before and after their own `VACUUM`, each naming one client backend (`pid=94456 xmin=1141`, `pid=95215 xmin=1446`). **0** replication slots and **0** prepared transactions in all 62 |

Three exceptions are declared rather than satisfied, and all three were filed with the
declarations: the held snapshot each protocol requires, once per protocol, and the
measurement lock both protocols own. A `VACUUM` whose index cleanup did not run is no longer
one of them; see [What left the page with its
fixtures](#what-left-the-page-with-its-fixtures).

| # | Fixture | Declared state | How its reading is published |
|---|---|---|---|
| X1 | `g08` | a `REPEATABLE READ` snapshot opened before the churn commits and held across the maintenance `VACUUM` | the `churn_maintained` census is a **held-horizon** reading and is never published as a maintained-state one; the `settle2` census, after release and a second `VACUUM ANALYZE`, is what the method is scored on |
| X2 | `n10` | the same, across the settling `VACUUM` | same as X1 |
| X3 | the protocol's own measurement lock | taken per census in its own transaction and released at `COMMIT` | invariant I12 checks the intervals never overlap a maintenance step |

A disabled launcher is not a defeat, and the rule does not ask the run to switch it
back on: `autovacuum` stays `off` for isolation and every table carries
`autovacuum_enabled = off`, and the fixture runs the maintenance the launcher would
have run ([autovacuum.c#AutoVacuumingActive](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3235-L3241),
[autovacuum.c#av_enabled-return](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3048-L3054)).

### What a defeated VACUUM looks like, measured

The 2026-09-15 run built `g08` and `n10` to hold a snapshot across their maintenance
`VACUUM` and reported that neither reached the deleted-but-not-recyclable state,
blaming the recipe shape. That diagnosis was half right. This review found **two**
defects, and the second is the one that mattered.

| Defect | What it did |
|---|---|
| a modulus delete, `WHERE id % 5 <> 0` | thinned every page instead of emptying any, so even a working `VACUUM` had no whole page to delete |
| **the snapshot was opened after the churn committed** | a snapshot taken then has an `xmin` past the deleting xid, so those tuples are not `HEAPTUPLE_RECENTLY_DEAD` to it and the horizon is **not pinned at all** ([procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815)) |

Both are fixed: the delete is a contiguous id band, and the snapshot opens **before**
the churn. `n10` was also rebuilt on three hot keys, because a posting *list* that
fits in one entry-tree tuple has no page to empty and the old recipe's 600,000
distinct keys produced no posting tree at all. An intermediate run, at 300,000 rows,
put the whole index at 1,024,000 bytes - under the method's own 1 MB floor - so the
fixture is sized at 1,200,000 rows to measure the method rather than the floor.

What the same fixture now reads on each side of the release:

| | `g08` (GiST, 300,000 rows, 80 % deleted) | `n10` (GIN, 1,200,000 rows on 3 hot keys, 80 % deleted) |
|---|---|---|
| `dead but not yet removable`, under the snapshot | **240,000** | **960,000** |
| `VACUUM VERBOSE` index line, under the snapshot | `2970 in total, 0 newly deleted, 0 currently deleted, 0 reusable` | `479 in total, 0 newly deleted, 0 currently deleted, 0 reusable` |
| census deleted pages, under the snapshot | 0 | 0 |
| index size, under the snapshot | 24,330,240 | 3,923,968 |
| `dead but not yet removable`, after release | **0** | **0** |
| `VACUUM VERBOSE` index line, after release | `2970 in total, 2330 newly deleted, 2330 currently deleted, 0 reusable` | `479 in total, 375 newly deleted, 375 currently deleted, 0 reusable` |
| census deleted pages / FSM free pages, after release | 2330 / **0** | 375 / **0** |
| index size, after release | 24,330,240 | 3,923,968 |
| `REINDEX INDEX` | 4,866,048 (80.00 % returned) | 827,392 (78.91 % returned) |

Three readings in that table are the point.

- **The defeated `VACUUM` succeeded and touched nothing.** Both index lines read zero
  in all three page fields, because with the horizon pinned no dead TID is collected,
  `lazy_vacuum` is never entered and neither `gistbulkdelete` nor `ginbulkdelete`
  runs ([vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052)).
  The file size never moves in either direction, on either side, because no index AM
  [truncates](../../../glossary.md#truncation).
- **After release, the deleted pages are still not free.** 2,330 and 375 pages are
  deleted and the FSM count is **0** on both, because a page deleted by *this*
  `VACUUM` carries a delete xid the cluster has not passed: each page is stamped with
  the next transaction ID at the moment it is deleted
  ([gistvacuum.c#gistdeletepage-deletexid](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L640-L656),
  [ginvacuum.c#ginDeletePage-deletexid](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L187-L192),
  [gistutil.c#gistPageRecyclable](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L885-L908),
  [ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829)).
  That is the ordinary one-`VACUUM` [recycling lag](../../../glossary.md#index-page-recycling), not a held-snapshot state: no
  snapshot was held when these pages were deleted, and under the snapshot no page was
  deleted at all. So `n10` reaches the GIN protocol's "a snapshot held across the
  settling `VACUUM`", but `g08` does not reach the GiST row "a deleted-but-not-recyclable
  page under a held snapshot"; see [Coverage the protocols require, and what this page
  skipped](#coverage-the-protocols-require-and-what-this-page-skipped).
- **On GIN the settle proof passed while nothing was removed.** Under the held
  snapshot `n10`'s [metapage](../../../glossary.md#metapage) identity held exactly - `meta(total=479, entry=1,
  data=477)` against `census(scanned=479, entry=1, data=477, deleted=0)` - and its
  `VERBOSE` `num_pages` equalled the blocks the census scanned, so **invariants I8
  and I9 both passed on a `VACUUM` that removed not one entry**. That is the GIN
  protocol's own warning reproduced: `ginvacuumcleanup` takes its `stats == NULL`
  branch, flushes the [pending list](../../../glossary.md#pending-list), walks every [block](../../../glossary.md#block) and rewrites the metapage
  counters whether or not `ginbulkdelete` ever ran
  ([ginvacuum.c#cleanup-pending-when-no-bulkdelete](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L719-L729),
  [ginvacuum.c#ginvacuumcleanup-census](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L789)).
  Only the `dead but not yet removable` count and the horizon read caught it.

### Why REINDEX is the only thing that shrinks these five access methods

The heuristic is worth building because for all five target [access methods](../../../glossary.md#access-method), `VACUUM`
never returns a block to the operating system. The only truncation code in any index
AM is disabled: `spgvacuumscan` carries a `RelationTruncate` call inside
`#ifdef NOT_USED`, with a comment saying it is unsafe due to concurrent inserts and
that "btree doesn't do this either"
([spgvacuum.c#spgvacuumscan](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L877-L900)).
What `VACUUM` does instead is record freed blocks in the index's own [free space map](../../../glossary.md#free-space-map),
which is only an allocator hint
([indexfsm.c#RecordFreeIndexPage](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L47-L55)).
`REINDEX` is different because it allocates a new [relfilenumber](../../../glossary.md#relfilenumber) and builds into it
([index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789)).

Per access method, the reason a rebuild is smaller:

| AM | Why the file grows | Why VACUUM cannot give it back |
|---|---|---|
| hash | Overflow pages per bucket, and whole [splitpoint](../../../glossary.md#hash-splitpoint) batches of bucket pages allocated at once ([hashpage.c#_hash_alloc_buckets](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L967-L1037)) | Freed overflow pages only clear a bit in the index's own bitmap ([hashovfl.c#_hash_freeovflpage](../../../../raw/postgres-17/src/backend/access/hash/hashovfl.c#L601-L642)); the README states there is no provision to shrink other than REINDEX ([hash/README](../../../../raw/postgres-17/src/backend/access/hash/README#L31-L34)) |
| gin | [Posting lists](../../../glossary.md#posting-list) outgrow the [leaf](../../../glossary.md#leaf-page) and become posting trees; pending pages | VACUUM never deletes tuples or pages from the entry tree ([gin/README](../../../../raw/postgres-17/src/backend/access/gin/README#L389-L396)), and leaf vacuum deliberately does not re-encode segments - "You'll have to REINDEX anyway" ([gindatapage.c#ginVacuumPostingTreeLeaf](../../../../raw/postgres-17/src/backend/access/gin/gindatapage.c#L797-L813)) |
| gist | [Page splits](../../../glossary.md#page-split) | Only *completely empty* leaf pages are ever deleted ([gistvacuum.c#gistvacuumpage](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L388-L403)), and the last downlink is never removed ([gistvacuum.c#gistvacuum_delete_empty_pages](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L541-L548)) |
| spgist | Deleted leaf tuples become [placeholders](../../../glossary.md#sp-gist-placeholder), not free space | Placeholders are only physically removed when they form a contiguous run at the *end* of the page ([spgvacuum.c#vacuumRedirectAndPlaceholder](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L569-L590)) |
| brin | A summary that no longer fits in place is written elsewhere and the old line pointer is orphaned ([brin_pageops.c#brin_doupdate](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L246-L262)) | `PageIndexTupleDeleteNoCompact` sets the line pointer unused but never sets `PD_HAS_FREE_LINES` ([bufpage.c#PageIndexTupleDeleteNoCompact](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L1333-L1347)), which is the only thing that makes `PageAddItem` recycle a slot ([bufpage.c#PageAddItemExtended](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L249-L258)); and `brinbulkdelete` is a no-op ([brin.c#brinbulkdelete](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1283-L1301)) |

A fresh build is also denser than incremental growth for independent reasons: a hash
rebuild sizes its bucket count from the current heap estimate
([hash.c#hashbuild](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L133-L137)),
and a [sorted GiST build](../../../glossary.md#gist-build-method) packs pages completely, explicitly ignoring [fillfactor](../../../glossary.md#fillfactor)
([gistbuild.c#gist_indexsortbuild_levelstate_add](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L462-L472)).

### Why a current-over-baseline size ratio is the wrong question

Because it cannot separate a table that grew from an index that rotted. The measured
matrix contains one fixture that makes the point without ambiguity: `h12` grew its
partial hash index from 58,736,640 to 66,568,192 bytes, a raw ratio of **1.13**, and
a `REINDEX` reclaimed **0 bytes**. The predicate-selected population had grown 9x -
the `UPDATE` moved 1,600,000 of 2,000,000 rows into `state = 'pending'` - so all of
the growth was legitimate. The population-normalized reading for the same index is
**0.126**, correctly below 1, and the partial-fraction guard suppressed the row
anyway at `pf_shift` **8.974**.

### Three catalog facts the design depends on

#### COMMENT ON INDEX survives both REINDEX forms

This is what makes a comment-resident baseline viable at all. Plain `REINDEX` keeps
the index's pg_class row and only swaps the relfilenumber
([index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789)),
so the [`pg_description`](../../../glossary.md#comment-on) row, which is keyed on the index [OID](../../../glossary.md#oid), is untouched.
`REINDEX ... CONCURRENTLY` builds a *new* index with a *new OID* and explicitly moves
the comment across in a block commented "Move comment if any"
([index.c#index_concurrently_swap](../../../../raw/postgres-17/src/backend/catalog/index.c#L1740-L1784)).
The in-tree regression test asserts both
([create_index.out#testcomment](../../../../raw/postgres-17/src/test/regress/expected/create_index.out#L2300-L2324)).

Measured on this run's cluster, on the `e_rebuild_i` edge fixture, showing that the
OID moves under [CONCURRENTLY](../../../glossary.md#concurrently) while the comment follows it:

```text
step                                     idx_oid   filenode
oid/filenode before                        16814      16814
oid/filenode after plain REINDEX           16814      16828
oid/filenode after REINDEX CONCURRENTLY    16829      16829
```

A two-line human comment containing both an `@` and a `}` survived all of it
unchanged, and the statement then reported `rebuilt since baseline` ->
`capture new baseline`. The consequence for the design is a rule: **never cache the
index OID; re-resolve it by name.** The comment itself is `text` in a [TOAST](../../../glossary.md#toast)-enabled
[catalog](../../../glossary.md#catalog)
([pg_description.h#pg_description](../../../../raw/postgres-17/src/include/catalog/pg_description.h#L48-L57))
with no length check in `CreateComments`
([comment.c#CreateComments](../../../../raw/postgres-17/src/backend/commands/comment.c#L142-L226)),
and the measured payload is 221 bytes in a 231-byte comment, or 243 in 340 once a
human comment and a `dbr` key are present, so the row stays inline either way.
`COMMENT ON` takes [`ShareUpdateExclusiveLock`](../../../glossary.md#shareupdateexclusivelock) and requires ownership
([comment.c#CommentObject](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L77)),
and its `IS` clause takes a string literal or `NULL` rather than an expression
([gram.y#CommentStmt](../../../../raw/postgres-17/src/backend/parser/gram.y#L7049-L7056),
[gram.y#comment_text](../../../../raw/postgres-17/src/backend/parser/gram.y#L7219-L7222)),
which is why both the capture statement and the edge fixtures build the text and then
apply it through `format(..., %L)`.
`obj_description(oid, 'pg_class')` is the correct reader; it filters `objsubid = 0`
([system_functions.sql#obj_description](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L291-L301)).

#### An index reltuples means three different things

This is the finding that most shaped the design. Three different code paths write an
index's [`pg_class.reltuples`](../../../glossary.md#pg_class), and they do not agree:

- `CREATE INDEX` / `REINDEX` write the AM's own `stats->index_tuples`
  ([index.c#index_build](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135)).
- `ANALYZE` overwrites it with `ceil(tupleFract * totalrows)`, and `tupleFract` is
  initialized to `1.0`
  ([analyze.c:449](../../../../raw/postgres-17/src/backend/commands/analyze.c#L449))
  and only revised for expression or [partial indexes](../../../glossary.md#partial-index), because `compute_index_stats`
  skips everything else
  ([analyze.c#compute_index_stats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L861-L863)).
  So for a plain index it becomes a copy of the *table's* row estimate
  ([analyze.c#do_analyze_rel](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663)).
- `VACUUM` writes the AM's `num_index_tuples`, but only when the count is exact
  ([vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3073-L3096)).
  For GIN that is deliberately the *heap* tuple count
  ([ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L735-L739));
  for BRIN it is the number of summarized ranges
  ([brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332)).

See [What an index reltuples means,
re-measured](#what-an-index-reltuples-means-re-measured) for this run's numbers. Two
rules follow, and both are enforced: capture the baseline **after `ANALYZE`**, and
refuse to score when no `ANALYZE` has happened since the baseline.

#### There is no per-table statistics reset timestamp

`PgStat_StatTabEntry` has no reset field
([pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-17/src/include/pgstat.h#L399-L429)),
and the [relation](../../../glossary.md#relation) stats kind registers no `reset_timestamp_cb`
([pgstat.c#pgstat_kind_builtin_infos](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L278-L290)).
`pg_stat_reset_single_table_counters()` does bump the *database* timestamp
([pgstat.c#pgstat_reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L734-L757)),
but that cannot tell you *which* table was reset. Measured on this run: after
`pg_stat_reset_single_table_counters('e_reset'::regclass)` the table read
`n_tup_ins=0 n_tup_upd=0 vacuum_count=0` with no physical change whatever, and the
published statement reported `d_ins = -300000`, `churn_ratio` NULL,
`churn_state = unknown: counters reset` and `weak: inflated, churn unknown`.

The only positive proof is therefore that a stored counter went backwards, which is
why the baseline stores the raw counters.

### The baseline field set

19 fields. Against the prompt's suggested list, `n_live_tup` and `n_dead_tup` were
**removed** and four fields were **added**.

| Key | Meaning | Why it is needed |
|---|---|---|
| `v` | payload version | lets the reader reject a format it does not understand |
| `ts` | baseline timestamp, UTC | reporting and baseline age |
| `am` | access method name | selects the normalization model; also detects an AM change |
| `fn` | `pg_relation_filenode()` | baseline validity; detects any rebuild |
| `isz` | [`pg_relation_size()`](../../../glossary.md#relation-size-functions) | the B term of the model |
| `ipg` | index `relpages` | diagnostic cross-check on `isz` |
| `itup` | index `reltuples` | logical population for hash/GiST/SP-GiST; partial-fraction numerator |
| `tpg` | table `relpages` | BRIN logical ranges |
| `ttup` | table `reltuples` | partial-fraction denominator |
| `ppr` | `pages_per_range` (BRIN only) | BRIN range arithmetic; detects a reloption change |
| `iw` | summed `pg_stats.avg_width` of the key columns (GIN only) | GIN input-mass normalization |
| `ins`, `upd`, `hot`, `del` | raw cumulative tuple counters | churn deltas, **and** the monotonicity reset check |
| `vac`, `avac` | raw `vacuum_count`, `autovacuum_count` | "did VACUUM happen", and the reset check |
| `anl` | `analyze_count + autoanalyze_count` | gates the whole reading, per the `reltuples` finding above |
| `dbr` | `pg_stat_database.stats_reset` | secondary reset warning |

Removed, with reasons: **`live`** is redundant against `ttup` for every use the model
has, and **`dead`** has no decision power at baseline - the index was just built, so
its physical state is fresh regardless of how many dead heap tuples existed. The dead
tuple ratio that the heuristic actually gates on is a *current* reading. Added
against the prompt's list: `ppr`, `iw`, `anl`, and `dbr`.

`ppr` and `iw` are emitted only for the access method that uses them;
`jsonb_strip_nulls` drops them elsewhere.

### The comment format

Three literal captures from this run: `h00`'s hash index, `b10`'s BRIN index carrying
`ppr`, and `n03`'s GIN index carrying `iw`:

```text
@idxmaint:{"v": 1, "am": "hash", "fn": "16503", "ts": "2026-09-24T19:37:49Z", "anl": 2, "del": 0, "hot": 0, "ins": 1000000, "ipg": 4098, "isz": 33570816, "tpg": 5406, "upd": 0, "vac": 0, "avac": 0, "itup": 1000000, "ttup": 1000000}

{"v": 1, "am": "brin", "fn": "16581", "ts": "2026-09-24T19:37:49Z", "anl": 2, "del": 0, "hot": 0, "ins": 2000000, "ipg": 3, "isz": 24576, "ppr": 128, "tpg": 11977, "upd": 0, "vac": 0, "avac": 0, "itup": 2000000, "ttup": 2000000}

{"v": 1, "am": "gin", "fn": "16601", "iw": 52, "ts": "2026-09-24T19:37:49Z", "anl": 2, "del": 0, "hot": 0, "ins": 600000, "ipg": 5262, "isz": 43106304, "tpg": 6818, "upd": 0, "vac": 0, "avac": 0, "itup": 600000, "ttup": 600000}
```

The hash payload is 221 bytes in a 231-byte comment. With a human comment in front
of the marker and a `dbr` key present, the same shape measured **243 bytes of payload
in a 340-byte comment**:

```text
Search index used by the application.
Second human line with an @ sign and a } brace.

@idxmaint:{"v": 1, "am": "hash", "fn": "16829", "ts": "2026-09-24T19:46:01Z", "anl": 1, "dbr": "2026-09-24T19:46:01Z", "del": 0, "hot": 0, "ins": 0, "ipg": 1026, "isz": 8404992, "tpg": 3244, "upd": 0, "vac": 0, "avac": 0, "itup": 300000, "ttup": 300000}
```

Everything before `@idxmaint:` is human text and is preserved verbatim, including the
`@` and the `}`. The payload is a single line so the marker regex is unambiguous.
Three qualifications, all measured on this run:

- **`dbr` is absent only while the database has never had its statistics reset.**
  `pg_stat_database.stats_reset` is NULL then, so `jsonb_strip_nulls` drops the key.
  The `"dbr": "2026-09-24T19:46:01Z", ` text is **31 bytes**; the two captures above
  differ by 26 because the same `pg_stat_reset()` that filed the key also zeroed the
  `ins` counter the payload stores. Budget for the larger form.
- **`jsonb` key order is canonical, so nothing moves except `ts`** - and `ts` has
  one-second resolution, so two captures are byte-identical only within the same
  clock second.
- **A statistics reset makes the capture statement refuse until the table is
  analyzed again.** Immediately after `pg_stat_reset()` the capture pass generated
  **0 statements and 4 refusals**; after one `ANALYZE` it generated **1 statement and
  3 refusals**. That is the `anl` guard working on the payload it is about to write.

### SQL 1: capture a fresh baseline

Run this after `CREATE INDEX`, `REINDEX INDEX`, or `REINDEX INDEX CONCURRENTLY`, and
**after an `ANALYZE` of the table**. It is a generator: it returns one
`COMMENT ON INDEX ...;` statement per index whose baseline is absent or no longer
describes the physical index, and one `DO ... RAISE WARNING ...;` statement per index
it refuses. Feed its output back to the server. It creates no persistent object other
than the comments. `COMMENT ON` takes `ShareUpdateExclusiveLock`
([comment.c#CommentObject](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L77)),
so the statement bounds the wait; both `SET`s are `PGC_USERSET`, session/transaction
scope
([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620),
[guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)).

Three properties of the `WHERE` clause matter, and each is measured under [Thirteen
edge cases, measured](#thirteen-edge-cases-measured):

- It **refreshes only stale baselines**, so it is idempotent: run twice in a row on
  this run's 7 edge indexes it produced 7 statements and then **0**.
- It **never files a baseline for a [B-tree](../../../glossary.md#b-tree), an [invalid index](../../../glossary.md#invalid-index) or an index with no
  storage**, so the evaluation statement's guards for those are defence in depth
  rather than the normal path.
- It **refuses a table that has never been analyzed**, because until then an index
  `reltuples` is the AM's own build count and the model would compare two different
  quantities.

```sql
SET /* wiki_idxmaint_guard */ statement_timeout = '60s';
SET /* wiki_idxmaint_guard */ lock_timeout = '5s';

SELECT /* wiki_idxmaint_capture_baseline */
       CASE
         WHEN st.analyze_count + st.autoanalyze_count = 0 THEN
           format('DO $$ BEGIN RAISE WARNING %L; END $$;',
                  'no baseline for ' || i.indexrelid::regclass::text ||
                  ': the table has never been analyzed, so an index reltuples' ||
                  ' is still a build artifact (run ANALYZE first)')
         ELSE
           format('COMMENT ON INDEX %s IS %L;',
                  i.indexrelid::regclass::text,
                  CASE WHEN human = '' THEN '' ELSE human || E'\n\n' END
                  || '@idxmaint:' || payload::text)
       END AS capture_statement
  FROM pg_index i
  JOIN pg_class ic ON ic.oid = i.indexrelid
  JOIN pg_class tc ON tc.oid = i.indrelid
  JOIN pg_namespace tn ON tn.oid = tc.relnamespace
  JOIN pg_am am ON am.oid = ic.relam
  JOIN pg_stat_all_tables st ON st.relid = i.indrelid
  CROSS JOIN (SELECT stats_reset FROM pg_stat_database
               WHERE datname = current_database()) d
  CROSS JOIN LATERAL (
       SELECT rtrim(regexp_replace(coalesce(obj_description(i.indexrelid, 'pg_class'), ''),
                                   '@idxmaint:.*$', ''), E' \t\r\n')            AS human,
              substring(obj_description(i.indexrelid, 'pg_class')
                        from '@idxmaint:(.*)$')                                 AS old_payload
  ) c
  CROSS JOIN LATERAL (
       SELECT jsonb_strip_nulls(jsonb_build_object(
                'v',    1,
                'ts',   to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                'am',   am.amname,
                'fn',   pg_relation_filenode(i.indexrelid),
                'isz',  pg_relation_size(i.indexrelid),
                'ipg',  ic.relpages,
                'itup', ic.reltuples::bigint,
                'tpg',  tc.relpages,
                'ttup', tc.reltuples::bigint,
                'ppr',  CASE WHEN am.amname = 'brin' THEN coalesce(
                               (SELECT o.option_value::int
                                  FROM pg_options_to_table(ic.reloptions) o
                                 WHERE o.option_name = 'pages_per_range'), 128)
                        END,
                'iw',   CASE WHEN am.amname = 'gin' THEN (
                               SELECT sum(s.avg_width)::int
                                 FROM unnest(i.indkey::int2[]) WITH ORDINALITY k(attnum, ord)
                                 JOIN pg_attribute a
                                   ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                                 JOIN pg_stats s
                                   ON s.schemaname = tn.nspname
                                  AND s.tablename  = tc.relname
                                  AND s.attname    = a.attname
                                WHERE k.ord <= i.indnkeyatts AND k.attnum <> 0)
                        END,
                'ins',  st.n_tup_ins,
                'upd',  st.n_tup_upd,
                'hot',  st.n_tup_hot_upd,
                'del',  st.n_tup_del,
                'vac',  st.vacuum_count,
                'avac', st.autovacuum_count,
                'anl',  st.analyze_count + st.autoanalyze_count,
                'dbr',  to_char(d.stats_reset AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
              )) AS payload
  ) p
 WHERE ic.relkind = 'i'
   AND am.amname IN ('hash', 'gist', 'spgist', 'brin', 'gin')
   AND i.indisvalid AND i.indislive
   AND tn.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
   AND pg_relation_filenode(i.indexrelid) IS NOT NULL
   -- refresh exactly the baselines that are absent or no longer describe the
   -- physical index, and leave every valid baseline untouched
   AND (c.old_payload IS NULL
        OR NOT (c.old_payload ~ '^\s*\{')
        OR (c.old_payload::jsonb ->> 'v') IS DISTINCT FROM '1'
        OR (c.old_payload::jsonb ->> 'am') IS DISTINCT FROM am.amname
        OR (c.old_payload::jsonb ->> 'fn')::oid
             IS DISTINCT FROM pg_relation_filenode(i.indexrelid))
 ORDER BY i.indexrelid::regclass::text;
```

`128` is the correct fallback for a BRIN index with no explicit reloption
([brin.h#BRIN_DEFAULT_PAGES_PER_RANGE](../../../../raw/postgres-17/src/include/access/brin.h#L39-L45)).
`pg_relation_size(regclass)` is the main [fork](../../../glossary.md#fork) only
([system_functions.sql#pg_relation_size](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L285-L289)),
which is the same set of blocks `relpages` counts and the same quantity the oracle
reads through the two-argument form
([dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L371)).

### SQL 2: read the baseline back

```sql
SELECT /* wiki_idxmaint_read_baseline */
       c.oid::regclass                                                     AS index_name,
       am.amname,
       rtrim(regexp_replace(coalesce(d.description, ''), '@idxmaint:.*$', ''),
             E' \t\r\n')                                                   AS human_comment,
       length(d.description)                                               AS comment_bytes,
       length(substring(d.description from '@idxmaint:(.*)$'))             AS payload_bytes,
       substring(d.description from '@idxmaint:(.*)$')::jsonb              AS payload,
       (substring(d.description from '@idxmaint:(.*)$')::jsonb ->> 'ts')   AS base_ts,
       (substring(d.description from '@idxmaint:(.*)$')::jsonb ->> 'am')   AS base_am,
       (substring(d.description from '@idxmaint:(.*)$')::jsonb ->> 'fn')::oid     AS base_filenode,
       pg_relation_filenode(c.oid)                                         AS cur_filenode,
       (substring(d.description from '@idxmaint:(.*)$')::jsonb ->> 'isz')::bigint AS base_index_bytes,
       pg_relation_size(c.oid)                                             AS cur_index_bytes
  FROM pg_class c
  JOIN pg_am am ON am.oid = c.relam
  LEFT JOIN pg_description d
         ON d.objoid = c.oid
        AND d.classoid = 'pg_class'::regclass
        AND d.objsubid = 0
 WHERE c.relkind = 'i'
   AND d.description LIKE '%@idxmaint:%'
 ORDER BY 1;
```

The reader deliberately does not filter on access method, so a hand-filed baseline on
an index the model does not cover is visible rather than hidden. The six built-in
index AM names are fixed in
[pg_am.dat](../../../../raw/postgres-17/src/include/catalog/pg_am.dat#L18-L35).

### SQL 3: evaluate

One statement, one row per index that carries an `@idxmaint:` payload. It computes
current metadata, the normalized inflation, the reclaimable-space proxy, all three
churn deltas, the churn and dead-tuple ratios, whether `VACUUM` occurred, and the
recommendation. It creates nothing. To evaluate a single index, add
`AND i.indexrelid = 'public.my_index'::regclass` to the `b` CTE's `WHERE` clause.

This is the text the run scored, verbatim, inside one transaction holding
`SHARE ROW EXCLUSIVE` on every fixture table. That mode excludes writers, `VACUUM`,
`ANALYZE` and both `REINDEX` forms while leaving ordinary readers alone
([lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L64-L104),
[mvcc.sgml#SHARE-ROW-EXCLUSIVE](../../../../raw/postgres-17/doc/src/sgml/mvcc.sgml#L1023-L1032)),
and the privilege it needs is `MAINTAIN`, `UPDATE`, `DELETE` or `TRUNCATE` rather
than `SELECT`
([lockcmds.c#LockTableAclCheck](../../../../raw/postgres-17/src/backend/commands/lockcmds.c#L277-L299)).

```sql
SET /* wiki_idxmaint_guard */ statement_timeout = '60s';
SET /* wiki_idxmaint_guard */ lock_timeout = '5s';

WITH /* wiki_idxmaint_evaluate */ b AS (
    SELECT i.indexrelid,
           i.indrelid,
           i.indpred IS NOT NULL                       AS is_partial,
           i.indisvalid,
           i.indislive,
           i.indkey,
           i.indnkeyatts,
           am.amname,
           tn.nspname                                  AS tschema,
           tc.relname                                  AS tname,
           ic.relpages::bigint                         AS ipg,
           ic.reltuples::numeric                       AS itup,
           tc.relpages::bigint                         AS tpg,
           tc.reltuples::numeric                       AS ttup,
           pg_relation_size(i.indexrelid)              AS isz,
           pg_relation_filenode(i.indexrelid)          AS fn,
           coalesce((SELECT o.option_value::int
                       FROM pg_options_to_table(ic.reloptions) o
                      WHERE o.option_name = 'pages_per_range'), 128) AS ppr,
           CASE WHEN pl.payload ~ '^\s*\{' THEN pl.payload::jsonb END AS j
      FROM pg_index i
      JOIN pg_class ic ON ic.oid = i.indexrelid
      JOIN pg_class tc ON tc.oid = i.indrelid
      JOIN pg_namespace tn ON tn.oid = tc.relnamespace
      JOIN pg_am am ON am.oid = ic.relam
      CROSS JOIN LATERAL (
           SELECT substring(obj_description(i.indexrelid, 'pg_class')
                            from '@idxmaint:(.*)$')    AS payload
      ) pl
     WHERE ic.relkind = 'i'
       AND pl.payload IS NOT NULL
),
cur AS (
    SELECT b.*,
           (SELECT sum(s.avg_width)::numeric
              FROM unnest(b.indkey::int2[]) WITH ORDINALITY k(attnum, ord)
              JOIN pg_attribute a ON a.attrelid = b.indrelid AND a.attnum = k.attnum
              JOIN pg_stats s ON s.schemaname = b.tschema
                             AND s.tablename  = b.tname
                             AND s.attname    = a.attname
             WHERE k.ord <= b.indnkeyatts AND k.attnum <> 0) AS iw
      FROM b
),
m AS (
    SELECT
      cur.*,
      st.n_tup_ins, st.n_tup_upd, st.n_tup_hot_upd, st.n_tup_del,
      st.n_live_tup, st.n_dead_tup,
      st.vacuum_count, st.autovacuum_count,
      st.analyze_count + st.autoanalyze_count AS anl,
      db.stats_reset,
      -- baseline validity
      CASE
        WHEN cur.j IS NULL                                 THEN 'no baseline'
        WHEN (cur.j->>'v') IS DISTINCT FROM '1'            THEN 'unsupported payload version'
        WHEN NOT cur.indislive                             THEN 'index not live'
        WHEN cur.fn IS NULL                                THEN 'no storage'
        WHEN (cur.j->>'am') IS DISTINCT FROM cur.amname    THEN 'access method changed'
        WHEN (cur.j->>'fn')::oid IS DISTINCT FROM cur.fn   THEN 'rebuilt since baseline'
        ELSE 'valid'
      END AS baseline_state,
      -- churn deltas
      st.n_tup_ins     - (cur.j->>'ins')::bigint  AS d_ins,
      st.n_tup_upd     - (cur.j->>'upd')::bigint  AS d_upd,
      st.n_tup_hot_upd - (cur.j->>'hot')::bigint  AS d_hot,
      st.n_tup_del     - (cur.j->>'del')::bigint  AS d_del,
      st.vacuum_count     - (cur.j->>'vac')::bigint  AS d_vac,
      st.autovacuum_count - (cur.j->>'avac')::bigint AS d_avac,
      st.analyze_count + st.autoanalyze_count
                          - (cur.j->>'anl')::bigint  AS d_anl,
      -- logical population, per access method
      CASE cur.amname
        WHEN 'brin' THEN ceil(GREATEST(cur.tpg, 0)::numeric / cur.ppr)
        WHEN 'gin'  THEN GREATEST(cur.itup, 0) * COALESCE(cur.iw, 1)
        ELSE             GREATEST(cur.itup, 0)
      END AS cur_pop,
      CASE (cur.j->>'am')
        WHEN 'brin' THEN ceil(GREATEST((cur.j->>'tpg')::numeric, 0) / (cur.j->>'ppr')::numeric)
        WHEN 'gin'  THEN GREATEST((cur.j->>'itup')::numeric, 0)
                           * COALESCE((cur.j->>'iw')::numeric, 1)
        ELSE             GREATEST((cur.j->>'itup')::numeric, 0)
      END AS base_pop,
      (cur.j->>'isz')::numeric AS base_isz,
      (cur.j->>'ts')           AS base_ts
      FROM cur
      JOIN pg_stat_all_tables st ON st.relid = cur.indrelid
      CROSS JOIN (SELECT stats_reset FROM pg_stat_database
                   WHERE datname = current_database()) db
),
d AS (
    SELECT m.*,
      -- statistics-reset detection: no per-table reset timestamp exists in v17,
      -- so a counter going backwards is the only positive proof.
      (d_ins < 0 OR d_upd < 0 OR d_hot < 0 OR d_del < 0 OR d_vac < 0 OR d_avac < 0)
        AS counters_went_backwards,
      (stats_reset IS DISTINCT FROM (j->>'dbr')::timestamptz) AS db_stats_reset_moved,
      CASE WHEN base_pop > 0 THEN base_isz * cur_pop / base_pop END AS expected_fresh_size,
      n_dead_tup::numeric / GREATEST(n_live_tup, 1) AS dead_ratio,
      CASE WHEN (j->>'ttup')::numeric > 0 AND ttup > 0
           THEN ((itup / ttup) / NULLIF((j->>'itup')::numeric / (j->>'ttup')::numeric, 0))
      END AS partial_fraction_shift
      FROM m
),
e AS (
    SELECT d.*,
      CASE WHEN expected_fresh_size > 0 THEN isz / expected_fresh_size END AS size_inflation,
      (d_upd - d_hot) AS d_nonhot_upd,
      (d_ins + (d_upd - d_hot) + d_del) AS churn,
      (d_vac + d_avac) > 0 AS vacuum_since_baseline
      FROM d
),
f AS (
    SELECT e.*,
      churn::numeric / GREATEST(n_live_tup, 1) AS churn_ratio,
      NOT counters_went_backwards AS churn_known
      FROM e
),
-- Experimental, per-access-method thresholds.  BRIN is deliberately the most
-- conservative: measured desummarize+summarize GREW a churned minmax_multi
-- index by 71%, and BRIN's size tracks table page count, not row churn.
-- This table is also the access-method guard: an AM with no row here is not
-- scored at all, because every threshold comparison against it would be NULL.
t AS (
    SELECT * FROM (VALUES
        ('hash',   1.30, 0.50, 1.50, 1.00),
        ('gist',   1.40, 0.75, 1.80, 1.50),
        ('spgist', 1.40, 0.75, 1.80, 1.50),
        ('gin',    1.50, 1.00, 2.00, 2.00),
        ('brin',   2.00, 1.00, 3.00, 2.00)
    ) AS v(amname, infl_cand, churn_cand, infl_strong, churn_strong)
)
SELECT
    f.indexrelid::regclass                       AS index_name,
    f.amname,
    f.is_partial,
    f.baseline_state,
    f.base_ts,
    pg_size_pretty(f.base_isz::bigint)           AS base_size,
    pg_size_pretty(f.isz)                        AS cur_size,
    pg_size_pretty(f.expected_fresh_size::bigint) AS expected_fresh,
    round(f.size_inflation, 3)                   AS size_inflation,
    -- the reclaimable-space proxy: if bytes per logical unit were invariant
    -- across the churn, a rebuild would land at cur_size / size_inflation
    GREATEST(round(100.0 * (1 - 1 / f.size_inflation), 1), 0) AS est_reclaim_pct,
    CASE f.amname WHEN 'brin' THEN 'summarized ranges'
                  WHEN 'gin'  THEN 'tuples x avg_width'
                  ELSE 'indexed tuples' END      AS pop_unit,
    round(f.base_pop, 0)                         AS base_pop,
    round(f.cur_pop, 0)                          AS cur_pop,
    f.d_ins, f.d_nonhot_upd, f.d_del,
    -- never publish a churn number derived from counters that went backwards
    CASE WHEN f.churn_known THEN round(f.churn_ratio, 3) END AS churn_ratio,
    CASE WHEN f.churn_known THEN 'known'
         ELSE 'unknown: counters reset' END      AS churn_state,
    CASE WHEN f.churn_known THEN f.vacuum_since_baseline END AS vacuum_since_baseline,
    CASE WHEN f.churn_known THEN f.d_vac + f.d_avac END      AS vacuums_since_baseline,
    round(f.dead_ratio, 4)                       AS dead_ratio,
    round(f.partial_fraction_shift, 3)           AS pf_shift,
    CASE
      -- B-tree and any other AM the model was never calibrated for.  Without
      -- this arm the LEFT JOIN leaves every threshold NULL and the CASE falls
      -- through to 'none', which reads as a verdict rather than a refusal.
      WHEN t.amname IS NULL                                THEN 'unsupported access method'
      WHEN f.baseline_state <> 'valid'                     THEN 'capture new baseline'
      WHEN NOT f.indisvalid                                THEN 'skip: index not valid'
      WHEN f.d_anl = 0                                     THEN 'inconclusive: no ANALYZE since baseline'
      WHEN f.expected_fresh_size IS NULL                   THEN 'inconclusive: no baseline population'
      WHEN f.is_partial AND (f.partial_fraction_shift < 0.7
                          OR f.partial_fraction_shift > 1.43)
                                                           THEN 'suppressed: predicate population moved'
      -- A reset zeroes vacuum_count too, so the VACUUM and dead-tuple gates
      -- below cannot be evaluated.  Report the size reading at low confidence
      -- rather than inventing a churn number.
      WHEN NOT f.churn_known AND f.size_inflation >= t.infl_cand
                                                           THEN 'weak: inflated, churn unknown'
      WHEN NOT f.churn_known                               THEN 'none (churn unknown)'
      WHEN NOT f.vacuum_since_baseline                     THEN 'inconclusive: no VACUUM since baseline'
      WHEN f.dead_ratio > 0.20                             THEN 'inconclusive: dead tuples not yet reclaimed'
      -- Nothing worth rebuilding.  BRIN indexes are normally a handful of
      -- pages, and the multiplicative model has no intercept, so a fixed
      -- metapage + revmap prefix dominates the ratio at that size.
      WHEN f.isz < 1048576                                 THEN 'none: index below 1 MB'
      WHEN f.size_inflation >= t.infl_strong
       AND f.churn_ratio >= t.churn_strong                  THEN 'strong REINDEX candidate'
      WHEN f.size_inflation >= t.infl_cand
       AND f.churn_ratio >= t.churn_cand                    THEN 'REINDEX candidate'
      ELSE 'none'
    END AS recommendation
  FROM f
  LEFT JOIN t ON t.amname = f.amname
 ORDER BY f.indexrelid::regclass::text;
```

### Access-method-specific normalization

| AM | Logical population | Rationale |
|---|---|---|
| hash | index `reltuples` | one entry per heap tuple; bucket count is sized from an estimate at build ([hash.c#hashbuild](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L133-L137), [hashpage.c#_hash_init_metabuffer](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L505-L525)) |
| gist | index `reltuples` | one entry per heap tuple |
| spgist | index `reltuples` | one entry per heap tuple |
| gin | index `reltuples` x summed `pg_stats.avg_width` | one heap row yields N entries; `ginarrayextract` returns one key per element ([ginarrayproc.c#ginarrayextract](../../../../raw/postgres-17/src/backend/access/gin/ginarrayproc.c#L32-L59)), so row count alone under-describes the input mass |
| brin | `ceil(table relpages / pages_per_range)` | the revmap is indexed by heap *block* ([brin_revmap.c#HEAPBLK_TO_REVMAP_BLK](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L35-L43)) and `brinbuildCallback` closes a range on block boundaries ([brin.c#brinbuildCallback](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L998-L1008)) |

Two deliberate deviations from the prompt:

- **`churn_ratio` is normalized by `n_live_tup`, not by the logical population.** For
  hash, GiST and SP-GiST those are the same number. For BRIN they are not: dividing
  by summarized ranges would report a single full-table update on a 2,000,000-row
  table as a churn ratio in the thousands. `n_live_tup` keeps the ratio meaning "how
  many times over did the row population turn over" for every AM. Measured, `b10`'s
  six full-table update rounds read **4.073** rather than four digits.
- **GIN's `avg_width` is a post-TOAST stored width**
  ([pg_statistic.h#stawidth](../../../../raw/postgres-17/src/include/catalog/pg_statistic.h#L40-L50)),
  so for a TOASTed column it measures an 18-byte pointer, not the datum. It is a
  usable proxy only for inline values; see [Known limitations](#known-limitations).

### The declared kind of every published column

Both protocols require every published quantity to be declared a lower bound, an
upper bound or a level **before the run**, and forbid rewriting the declaration
afterwards. This run's declarations were filed at **2026-09-24T19:36:34Z**, and the
first baseline payload carries **2026-09-24T19:37:49Z** - 75 seconds later, into a
database that did not exist when the declaration was filed. The `declare` stage
refuses to run once it does. During the 2026-09-16 review it refused twice, which is
what forced the fixture database to be dropped before the declarations could be
re-filed.

| Column | Declared kind | The claim that was scored |
|---|---|---|
| `est_reclaim_pct` | **upper bound** | the percentage it names is never less than the percentage of the file `REINDEX INDEX` returns |
| `size_inflation` | level | the population-normalized size ratio; a ranking statistic with no claim against the oracle |
| `expected_fresh` | level | the modelled fresh-build size |
| `churn_ratio` | level | index-affecting churn over live tuples |
| `dead_ratio` | level | dead over live tuples at evaluation time |
| `pf_shift` | level | the partial-predicate fraction shift; a suppression input, not a byte claim |
| `base_pop`, `cur_pop` | level | the two logical populations themselves |
| `base_size`, `cur_size` | level | the two file sizes themselves |
| `d_ins`, `d_nonhot_upd`, `d_del` | level | the raw counter deltas |
| `vacuums_since_baseline` | level | the count of VACUUMs since the baseline |

The decision thresholds were filed in the same transaction, per access method, in
both directions: the method's own candidate and strong gates, and the oracle
justification a flagged fixture has to clear. The justification is the method's own
candidate inflation carried to the oracle side as `100 * (1 - 1/infl_cand)`, so
hash needs 23.08 %, GiST and SP-GiST 28.57 %, GIN 33.33 % and BRIN 50.00 %.

### The phases every fixture ran

| Phase | What ran | What was recorded |
|---|---|---|
| build | create the table, load it, `ANALYZE`, create the scored index, `ANALYZE` again | - |
| baseline | the page census under the measurement lock, then the published capture statement over every index at once | `index_size`, `relpages`, `reltuples`, the per-AM page census, the payload |
| churn | the recipe's writes, then [`pg_stat_force_next_flush()`](../../../glossary.md#cumulative-statistics), then a census of the **unmaintained** state, then the maintenance step, then a census of the maintained state | `churn_raw` and `churn_maintained` |
| census | the simulated auto-analyze census over all 32 tables in the database | the verdict per table, and the `ANALYZE` statements it generated |
| decide | the published statement, verbatim, in one transaction holding `SHARE ROW EXCLUSIVE` on all 32 tables | one row per baselined index |
| oracle | `REINDEX INDEX` at `maintenance_work_mem = 256MB`, bracketed by `pg_relation_size(index, 'main')` | `size_before`, `size_after`, and the heap's `relpages`/`reltuples` at that moment |

The second `ANALYZE` of the build phase is what makes the baseline legal: an index
`reltuples` written by the build is the AM's own count, and for GIN and BRIN that is
not the number the model needs. The unmaintained census exists because both protocols
require the maintenance pair, and because the method must never be **evaluated** on
that state; it is a size and page reading only.

### The 29 scored fixtures and their results

Fixture sizes are 1,000,000 rows for the hash, GiST and SP-GiST families, 2,000,000
for BRIN and the partial index, 600,000 for GIN, 1,200,000 for `n10`, and 300,000 for
`g08` and `s10`.
Every table is created `WITH (autovacuum_enabled = off)`, and every recipe is in the
published script under [The script](#the-script).

| Fixture | AM | What it does | Maintenance step |
|---|---|---|---|
| `h00` | hash | no churn at all: the untouched index | none - nothing to maintain |
| `h01` | hash | 1,000,000 distinct keys collapsed onto 100 hot keys, so every duplicate lands in one bucket's overflow chain | `VACUUM ANALYZE` |
| `h02` | hash | grow 5x, then delete back to the baseline population | `VACUUM ANALYZE` |
| `h03` | hash | `fillfactor = 50`, then update half the rows | `VACUUM ANALYZE` |
| `h04` | hash | insert-only churn, 400,000 rows, so no dead tuple ever exists and `hashbulkdelete` never runs | `VACUUM ANALYZE` |
| `h05` | hash | 120,000 inserts: above the analyze threshold of 100,050 and below both vacuum thresholds | **`ANALYZE` alone**, the auto-analyze stand-in |
| `h07` | hash | an empty table and an empty index | none |
| `h08` | hash | update 1 % of rows: a negative control with the gates satisfied | `VACUUM ANALYZE` |
| `h12` | hash | partial index `WHERE state = 'pending'`, predicate population grown 9x | `VACUUM ANALYZE` |
| `g06` | gist | `int8range`, six rounds of whole-table range relocation | `VACUUM ANALYZE` |
| `g07` | gist | `int8range`, grow 4x then delete back | `VACUUM ANALYZE` |
| `g08` | gist | `int8range`, 300,000 rows, delete the top 80 % as a contiguous id band with a snapshot opened **before** the churn and held across the maintenance `VACUUM`, then a second `VACUUM` after release | `VACUUM ANALYZE`, twice; declared exception X1 |
| `g09` | gist | `point` with `point_ops`, the run's only sorted GiST build, six rounds of relocation | `VACUUM ANALYZE` |
| `s08` | spgist | six rounds of text prefix replacement at constant width | `VACUUM ANALYZE` |
| `s09` | spgist | grow 4x with a different prefix family, then delete back | `VACUUM ANALYZE` |
| `s10` | spgist | `fillfactor = 50`, delete 30 % and update 30 % | `VACUUM ANALYZE` |
| `b10` | brin | minmax, `pages_per_range = 128`, six whole-table value-churn rounds: the negative control | `VACUUM ANALYZE` |
| `b11` | brin | `int8_minmax_multi_ops(values_per_range = 64)`, correlated -> scattered -> correlated | `VACUUM ANALYZE` |
| `b12` | brin | minmax, `pages_per_range = 32`, three value-churn rounds | `VACUUM ANALYZE` |
| `b13` | brin | `autosummarize = on`, 1,000,000 appended rows leaving unsummarized ranges | the **summarization stand-in**, then `VACUUM ANALYZE` |
| `n03` | gin | `text[]`, `fastupdate = off`, 1,800,000 rows on three hot keys inserted then deleted | `VACUUM ANALYZE` |
| `n04` | gin | `text[]`, six rounds of complete key replacement | `VACUUM ANALYZE` |
| `n05` | gin | `fastupdate = on`, 300,000 inserts under `gin_pending_list_limit = 1GB` | `VACUUM ANALYZE` |
| `n06` | gin | `jsonb_path_ops`, three rounds of key replacement | `VACUUM ANALYZE` |
| `n07` | gin | `tsvector`, three rounds of document replacement | `VACUUM ANALYZE` |
| `n08` | gin | no churn at all | none |
| `n09` | gin | an empty GIN index | none |
| `n10` | gin | `text[]`, `fastupdate = off`, 1,200,000 rows on three hot keys so every key owns a posting tree, delete the top 80 % as a contiguous id band with a snapshot opened **before** the churn and held across the settling `VACUUM` | `VACUUM ANALYZE`, twice; declared exception X2 |
| `n12` | gin | 120,000 inserts with `fastupdate = on`, in the auto-analyze window | **`ANALYZE` plus `gin_clean_pending_list()`** |

Results. `B` is the as-built size, `raw` the unmaintained churned size, `C` the
maintained size the method was asked about, `R` the size immediately after
`REINDEX INDEX`, and `truth %` the oracle's own fraction of `C`. All sizes are
`pg_relation_size(index, 'main')` in bytes. On `g08` and `n10`, `C` is the `settle2`
census taken after the declared snapshot was released and a second `VACUUM ANALYZE`
had run, never the held-horizon census; see [The maintenance was not
defeated](#the-maintenance-was-not-defeated).

| Fixture | AM | B | raw | C | R | truth % | inflation | est % | churn | recommendation | bound | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `b10` | brin | 24576 | 24576 | 32768 | 32768 | 0.00 | 0.262 | 0 | 4.073 | none: index below 1 MB | HELD | PASS |
| `b11` | brin | 49152 | 57344 | 114688 | 114688 | 0.00 | 0.690 | 0 | 2.392 | none: index below 1 MB | HELD | PASS |
| `b12` | brin | 32768 | 32768 | 57344 | 57344 | 0.00 | 0.516 | 0 | 2.401 | none: index below 1 MB | HELD | PASS |
| `b13` | brin | 24576 | 24576 | 24576 | 24576 | 0.00 | 0.667 | 0 | 0.333 | none: index below 1 MB | HELD | PASS |
| `n03` | gin | 43106304 | 50659328 | 50659328 | 43106304 | 14.91 | 1.175 | 14.9 | 6.000 | none | VIOLATED | PASS |
| `n04` | gin | 43106304 | 324345856 | 324345856 | 49143808 | 84.85 | 6.537 | 84.7 | 6.015 | strong REINDEX candidate | VIOLATED | PASS |
| `n05` | gin | 43106304 | 61177856 | 85131264 | 66871296 | 21.45 | 1.317 | 24.0 | 0.333 | none | HELD | PASS |
| `n06` | gin | 43335680 | 120119296 | 123756544 | 40034304 | 67.65 | 2.538 | 60.6 | 3.000 | strong REINDEX candidate | VIOLATED | PASS |
| `n07` | gin | 43106304 | 184983552 | 188317696 | 49135616 | 73.91 | 3.865 | 74.1 | 3.000 | strong REINDEX candidate | HELD | PASS |
| `n08` | gin | 43106304 | 43106304 | 43106304 | 43106304 | 0.00 | 1.000 | 0.0 | 0.000 | inconclusive: no ANALYZE since baseline | HELD | PASS |
| `n09` | gin | 16384 | 16384 | 16384 | 16384 | 0.00 | - | 0 | 0.000 | inconclusive: no ANALYZE since baseline | HELD | PASS |
| `n10` | gin | 3923968 | 3923968 | 3923968 | 827392 | 78.91 | 5.000 | 80.0 | 4.000 | strong REINDEX candidate | HELD | PASS |
| `n12` | gin | 43106304 | 50339840 | 56655872 | 50143232 | 11.50 | 1.095 | 8.7 | 0.167 | inconclusive: no VACUUM since baseline | VIOLATED | PASS |
| `g06` | gist | 81100800 | 393871360 | 393871360 | 81100800 | 79.41 | 4.805 | 79.2 | 5.936 | strong REINDEX candidate | VIOLATED | PASS |
| `g07` | gist | 81100800 | 300523520 | 300523520 | 81100800 | 73.01 | 3.706 | 73.0 | 6.000 | strong REINDEX candidate | VIOLATED | PASS |
| `g08` | gist | 24330240 | 24330240 | 24330240 | 4866048 | 80.00 | 5.000 | 80.0 | 4.000 | strong REINDEX candidate | HELD | PASS |
| `g09` | gist | 45375488 | 451428352 | 451428352 | 70787072 | 84.32 | 10.036 | 90.0 | 6.053 | strong REINDEX candidate | HELD | PASS |
| `h00` | hash | 33570816 | 33570816 | 33570816 | 33570816 | 0.00 | 1.000 | 0.0 | 0.000 | inconclusive: no ANALYZE since baseline | HELD | PASS |
| `h01` | hash | 33570816 | 78790656 | 78790656 | 49053696 | 37.74 | 2.347 | 57.4 | 1.000 | strong REINDEX candidate | HELD | PASS |
| `h02` | hash | 33570816 | 169975808 | 169975808 | 33570816 | 80.25 | 5.063 | 80.2 | 8.000 | strong REINDEX candidate | VIOLATED | PASS |
| `h03` | hash | 41959424 | 67256320 | 67256320 | 41959424 | 37.61 | 1.603 | 37.6 | 0.500 | REINDEX candidate | VIOLATED | PASS |
| `h04` | hash | 33570816 | 46153728 | 46153728 | 41967616 | 9.07 | 0.982 | 0 | 0.286 | none | VIOLATED | PASS |
| `h05` | hash | 33570816 | 37765120 | 37765120 | 33570816 | 11.11 | 1.004 | 0.4 | 0.107 | inconclusive: no VACUUM since baseline | VIOLATED | PASS |
| `h07` | hash | 32768 | 32768 | 32768 | 32768 | 0.00 | - | 0 | 0.000 | inconclusive: no ANALYZE since baseline | HELD | PASS |
| `h08` | hash | 33570816 | 33570816 | 33570816 | 33570816 | 0.00 | 1.000 | 0.0 | 0.010 | none | HELD | PASS |
| `h12` | hash | 58736640 | 66568192 | 66568192 | 66568192 | 0.00 | 0.126 | 0 | 0.800 | suppressed: predicate population moved | HELD | PASS |
| `s08` | spgist | 33964032 | 246988800 | 246988800 | 35258368 | 85.72 | 7.194 | 86.1 | 5.936 | strong REINDEX candidate | HELD | PASS |
| `s09` | spgist | 33964032 | 134873088 | 134873088 | 33964032 | 74.82 | 3.971 | 74.8 | 6.000 | strong REINDEX candidate | VIOLATED | PASS |
| `s10` | spgist | 12582912 | 16957440 | 16957440 | 9502720 | 43.96 | 1.925 | 48.1 | 0.857 | REINDEX candidate | HELD | PASS |

The recommendation distribution over 29 fixtures: 12 `strong REINDEX candidate`,
2 `REINDEX candidate`, 4 `none`, 4 `none: index below 1 MB`, 4 `inconclusive: no
ANALYZE since baseline`, 2 `inconclusive: no VACUUM since baseline`, and 1
`suppressed: predicate population moved`. **14 fixtures were flagged, 0 wrongly**; the
least a flagged fixture repaid was `h03` at 37.61 %, against its own 23.08 % justification.

### The declared upper bound failed, so est_reclaim_pct is a level

`est_reclaim_pct` is `100 * (1 - 1/size_inflation)`, floored at zero. Filed as an
upper bound, it **held on 18 of 29 fixtures and was violated on 11**:

| Fixture | AM | est % | truth % | error, points | the row the method printed |
|---|---|---|---|---|---|
| `h05` | hash | 0.4 | 11.11 | **-10.71** | inconclusive: no VACUUM since baseline |
| `h04` | hash | 0 | 9.07 | **-9.07** | none |
| `n06` | gin | 60.6 | 67.65 | **-7.05** | strong REINDEX candidate |
| `n12` | gin | 8.7 | 11.50 | -2.80 | inconclusive: no VACUUM since baseline |
| `g06` | gist | 79.2 | 79.41 | -0.21 | strong REINDEX candidate |
| `n04` | gin | 84.7 | 84.85 | -0.15 | strong REINDEX candidate |
| `h02` | hash | 80.2 | 80.25 | -0.05 | strong REINDEX candidate |
| `s09` | spgist | 74.8 | 74.82 | -0.02 | strong REINDEX candidate |
| `h03` | hash | 37.6 | 37.61 | -0.01 | REINDEX candidate |
| `n03` | gin | 14.9 | 14.91 | -0.01 | none |
| `g07` | gist | 73.0 | 73.01 | -0.01 | strong REINDEX candidate |

Both protocols say a violated bound is corrected in the method or moved to a level,
not annotated away. It is **moved to a level**: `est_reclaim_pct` may be read as a
ranking statistic and must not be published as reclaimable space.

Two honest qualifications on the failure, neither of which rescues the bound:

- **Seven of the eleven violations are within a quarter of a point.** `g07`, `h03`
  and `n03` miss by 0.01, `s09` by 0.02, `h02` by 0.05, `n04` by 0.15 and `g06` by
  0.21. The first five are within the column's one-decimal rounding. `g06` and `n04`
  depend on an `ANALYZE` sample: in the same day's baseline pass `g06` read 79.5 and
  held, and `n04` read 84.6. A bound is a bound; the run does not re-declare it with a
  tolerance after seeing the result.
- **Two of the eleven are rows the method refused to decide.** `h04` printed `none`
  and `h05` an `inconclusive:` refusal, yet both still published a number. Whether a
  refused row should publish the column at all is filed
  under [Open Questions](#open-questions) rather than fixed after the fact.

The five largest over-estimates are the other half of the picture, and they are the
reason the column survives as a ranking statistic: `h01` +19.66, `g09` +5.68,
`s10` +4.14, `n05` +2.55, `n10` +1.09.

### How close the prediction came

Over the 27 fixtures where the method printed an inflation figure,
`est_reclaim_pct` landed **within 1 point of the oracle on 20** and **within 5 points
on 24**. The worst over-estimate is +19.66 and the worst under-estimate -10.71.

The single large over-estimate is `h01`, and its cause is the same one the previous
review found. That fixture moves 1,000,000 distinct keys onto 100 duplicated keys.
The logical population is unchanged, so the model predicts a rebuild back to the
baseline size - but a fresh build of the *new* data is legitimately larger than a
fresh build of the old data, because a hash index of 100 keys is 100 long overflow
chains rather than a wide spread of bucket pages, and the bucket is a pure function
of the hash code
([hashutil.c#_hash_hashkey2bucket](../../../../raw/postgres-17/src/backend/access/hash/hashutil.c#L121-L135)).
The model assumes bytes-per-logical-unit is invariant across the churn, and a change
in key distribution violates that. Measured: est 57.4 % against a true 37.74 %, and the
rebuild landed at 49,053,696 bytes rather than the 33,570,816 the baseline held.

### The maintenance pair: what the maintenance step moves

Both protocols require the same churn to be measured on both sides of the mandatory
maintenance step. On 22 of 29 fixtures the step moved no byte. On seven it did, and
in both directions the protocols predict:

| Fixture | AM | raw | maintained | change | why |
|---|---|---|---|---|---|
| `b10` | brin | 24576 | 32768 | **+8192** | `brinvacuumcleanup` summarizes every unsummarized range ([brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332)) |
| `b11` | brin | 57344 | 114688 | **+57344** | same, on a `minmax_multi` index whose summaries are larger |
| `b12` | brin | 32768 | 57344 | **+24576** | same, at `pages_per_range = 32`, so four times the ranges |
| `n05` | gin | 61177856 | 85131264 | **+23953408** | the settling `VACUUM` merges 2,206 pending pages into the main structure, and the merge allocates |
| `n06` | gin | 120119296 | 123756544 | +3637248 | same, 386 pending pages |
| `n07` | gin | 184983552 | 188317696 | +3334144 | same, 462 pending pages |
| `n12` | gin | 50339840 | 56655872 | **+6316032** | the auto-analyze stand-in's `gin_clean_pending_list()`, 883 pending pages |

So on seven of 29 fixtures a reading taken before the mandatory maintenance step
**understates** the file the method is asked about, by up to 39 % on `n05`. That is
the concrete reason the pre-`VACUUM` evaluation the previous review filed had to go:
it was not a conservative reading of the same index, it was a reading of a different
index.

`brinbulkdelete` explains the BRIN half: it allocates a result struct and returns,
removing nothing at all
([brin.c#brinbulkdelete](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1283-L1301)).
The declared invariant I7 - a BRIN index is never smaller after the maintenance step
than before it - held on 4 of 4.

### The BRIN summarization stand-in

`b13` is the fixture the non-B-tree protocol requires: an `autosummarize = on` index
whose work items nothing fulfils, because `brininsert` only *queues* a targeted
summarization request and only an autovacuum worker performs it
([brin.c#brininsert-autosummarize](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L379-L411),
[autovacuum.c#perform_work_item](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2635-L2641)),
and this run keeps `autovacuum` off. Measured, in one fixture:

| Reading | index size | revmap entries | live summary tuples | unused line pointers |
|---|---|---|---|---|
| baseline, 11,977 heap pages | 24576 | 94 | 94 | 0 |
| after 1,000,000 appended rows, unmaintained | 24576 | 94 | 94 | 0 |
| after the stand-in: 3 x `brin_desummarize_range()`, then `brin_summarize_range(0)` and `brin_summarize_new_values()` | 24576 | 141 | 141 | **3** |
| after the mandatory `VACUUM ANALYZE` | 24576 | 141 | 141 | 3 |

Three things in that table are worth naming. The appended rows created **47 new
unsummarized ranges that the index did not describe**, and nothing in the catalog
said so: the table's `relpages` still read 11,977 at the unmaintained census, which
is 94 ranges, because `pg_class.relpages` is refreshed by `VACUUM` and `ANALYZE` and
not by inserts. The stand-in summarized all 47 in the same file, so the
index grew by **zero bytes** - the revmap and the regular page both had room. And the
three ranges the stand-in desummarized left **exactly three unused line pointers**
behind, which `PageIndexTupleDeleteNoCompact` never marks reusable
([bufpage.c#PageIndexTupleDeleteNoCompact](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L1333-L1347)).

That last number is only visible because of a reader property the run had to
discover: **`brin_page_items` emits a row for an unused item**, with every column but
`itemoffset` NULL
([brinfuncs.c#brin_page_items](../../../../raw/postgres-17/contrib/pageinspect/brinfuncs.c#L230-L260)).
A census that counts its rows therefore over-counts summary tuples by exactly the
orphans. `b11` carried **13** such orphans after its three whole-table update rounds,
which is the protocol's "a moved summary leaves an unused line pointer behind"
cross-check, measured. The count is not fixed: the same day's baseline pass read 14.
With the census counting only rows that carry a `blknum`,
invariant I6 - the revmap entry count equals the summary tuples the regular pages
hold - held on **13 of 13** BRIN censuses.

### Both auto-analyze stand-ins make the method refuse

The two protocols differ on exactly one stand-in, and this run measured both.

On hash, GiST, SP-GiST and BRIN an `ANALYZE` touches no index page, so a foreground
`ANALYZE` is a faithful stand-in for an auto-analyze: `analyze_rel` enters the index
AM's ANALYZE-only cleanup only outside a `VACUUM ANALYZE`, and the comment there
names GIN as the only core exception
([analyze.c#analyze-only-cleanup](../../../../raw/postgres-17/src/backend/commands/analyze.c#L694-L721)).
On GIN it is not: the callback flushes the pending list, and only when the caller is
an autovacuum worker
([ginvacuum.c#analyze_only-worker](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L729)),
so the stand-in is `ANALYZE` plus an explicit `gin_clean_pending_list()`
([ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1030-L1091)).

Both fixtures sit in the window where auto-analyze is the whole of a table's
maintenance. For `h05`, 1,000,000 rows put the analyze threshold at
`50 + 0.1 * 1000000 = 100050`, the dead-tuple threshold at `50 + 0.2 * 1000000 =
200050` and the insert-vacuum threshold at `1000 + 0.2 * 1000000 = 201000`
([autovacuum.c#vacthresh-anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3074-L3076));
120,000 inserts clear the first and clear neither of the others. For `n12`, 600,000
rows put the same three at 60,050, 120,050 and 121,000, and 120,000 inserts land
**1,000 rows below** the insert-vacuum threshold.

The result is the same on both, and it is a refusal:

| Fixture | maintenance | `vacuums_since_baseline` | recommendation | truth % |
|---|---|---|---|---|
| `h05` | `ANALYZE` | 0 | inconclusive: no VACUUM since baseline | 11.11 |
| `n12` | `ANALYZE` + `gin_clean_pending_list()` | 0 | inconclusive: no VACUUM since baseline | 11.50 |

So an auto-analyze-maintained index is **outside the method's reach by construction**:
its `vacuum_count` never moves, and the gate that exists to keep the method away from
un-drained dead entries also keeps it away from this state permanently. On `n12` the
stand-in additionally left the metapage's page counts stale by construction - the
flush never reaches `ginUpdateStats`
([ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L789),
[ginutil.c#ginUpdateStats](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L645-L650)) -
and the run's own metapage cross-check records that as its single maintained-state
disagreement rather than as a defect.

The four no-churn fixtures - `h00`, `h07`, `n08`, `n09` - are refused by the other
gate, `inconclusive: no ANALYZE since baseline`, because a table nothing writes to is
never analyzed again and `d_anl` stays 0. For all four a rebuild returned 0 bytes, so
the refusal costs nothing here; what it shows is that **the method is silent on a
healthy index, not reassuring about one**.

### BRIN: desummarize plus summarize made the index bigger

The prompt asks whether `brin_desummarize_range()` + `brin_summarize_range()` is a
better recommendation than `REINDEX` for some BRIN cases. Measured on its own
2,000,000-row fixture with an `int8_minmax_multi_ops(values_per_range = 64)` index,
scattered then re-correlated, then walked range by range:

| Step | `minmax_multi` bytes |
|---|---|
| fresh build | 49152 |
| after churn + `VACUUM (ANALYZE)`, 318 ranges | 114688 |
| after `brin_desummarize_range()` on all 318 ranges | **114688** |
| after `brin_summarize_range()` on all 318 ranges | **196608** |
| after `brin_summarize_new_values()` | 196608, 0 ranges added |
| after `REINDEX INDEX` | 114688 |

Desummarizing 318 ranges freed **nothing**, and resummarizing made the index **71 %
larger** than it started. Both halves follow from source: `brinRevmapDesummarizeRange`
removes the tuple with `PageIndexTupleDeleteNoCompact` and carries the comment
`/* XXX record free space in FSM? */`
([brin_revmap.c#brinRevmapDesummarizeRange](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L395-L410)),
and because that routine never sets `PD_HAS_FREE_LINES`
([bufpage.c#PageIndexTupleDeleteNoCompact](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L1333-L1347)),
the orphaned slots cannot be reused by `PageAddItem`
([bufpage.c#PageAddItemExtended](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L249-L258)).
`summarize_range` then inserts a placeholder and updates it into the real summary,
which usually takes the relocate branch again
([brin.c#summarize_range](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1752-L1864)).

These are the same three numbers the previous review measured - 114688 -> 114688 ->
196608, with `REINDEX` returning 114688 - reproduced on a fresh fixture on a fresh
cluster. So the design does allow a different BRIN recommendation, and the evidence
points the other way: **`brin_desummarize_range()` + `brin_summarize_range()` is a
summary-quality operation, not a space-reclamation one, and it costs space.** The
BRIN arm therefore uses the highest thresholds of any AM and never emits a
resummarize recommendation.

The BRIN negative control behaved as the prompt predicted: `b10` absorbed six
full-table update rounds - a churn ratio of 4.073 against 8,203,860 non-HOT updates
on 2,000,000 rows - and grew from 3 pages to 4, with **0 bytes** reclaimable, because
a fixed-width minmax summary almost always takes the in-place branch
([brin_pageops.c#brin_can_do_samepage_update](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L319-L328)).
`b11`'s `minmax_multi` summaries are variable-width, and there the same shape of
churn moved 13 summaries to other pages.

### A hash rebuild is sized from the heap, not from the index

The non-B-tree protocol requires a run to report the inputs its oracle depended on,
and on hash that input is not the index. `hashbuild` estimates the row count from
`estimate_rel_size` on the **heap**
([hash.c#hashbuild](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L133-L137),
[plancat.c#estimate_rel_size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1064-L1078)),
and the bucket count then follows `num_tuples / ffactor` rounded up to a splitpoint
total
([hashpage.c#_hash_init_metabuffer](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L505-L525)).
Measured on `h08`, a 1,000,000-row table with 5,460 heap pages, by forging the heap's
`reltuples` and changing nothing else:

| heap `reltuples` at rebuild time | rebuilt index size |
|---|---|
| 1000000, the true value | 33570816 |
| 100, forged | **38346752** |
| 1000000 again, after `ANALYZE` | 33570816 |

A wrong heap estimate made the rebuild **4,775,936 bytes larger**, because two
buckets had to absorb a million rows as overflow chains. The consequence for this
page is a reporting rule the protocol already states: a hash oracle number without
the heap's `relpages` and `reltuples` beside it is not reproducible, so the run
records both at every `REINDEX`.

### The GIN oracle is budget-dependent

The GIN protocol requires the `maintenance_work_mem` a rebuild ran at, because the
build flushes its accumulator whenever allocated memory reaches the budget
([gininsert.c#build-flush](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L286-L292)).
Measured on `n04`, rebuilding the same index three times:

| `maintenance_work_mem` | rebuilt size |
|---|---|
| 4MB | 46784512 |
| 64MB | 48021504 |
| 256MB | 49143808 |

A 4MB budget produced an index **4.8 % smaller** than a 256MB one. Every oracle
number in the results table above was taken at **256MB**, and `truth_pct` would move
by up to 4.8 % on a GIN fixture if that budget changed.

### What an index reltuples means, re-measured

One 200,000-row table, five indexes, one index per access method, measured after each
of the three writers in turn. The `DELETE` and the `VACUUM` are separate statements,
because `VACUUM` cannot run inside a transaction block and a single `psql -c` would
roll the `DELETE` back:

| AM | after CREATE INDEX | after ANALYZE | after DELETE 10 % + VACUUM |
|---|---|---|---|
| hash | 200000 | 200000 | 180000 |
| gin | **400000** (index entries) | **200000** (rows) | 180000 (rows) |
| gist | 200000 | 200000 | 180000 |
| spgist | 200000 | 200000 | 180000 |
| brin | **43** (parallel-build artifact) | **200000** (rows) | **22** (ranges) |

The table has 2,857 heap pages, so 23 BRIN ranges at the default `pages_per_range`,
and [`pageinspect`](../../../glossary.md#pageinspect) counted **23** live summary tuples both before and after the
`VACUUM`. So a baseline captured before `ANALYZE` and evaluated after one would show
a GIN index as 2x inflated and a BRIN index as 4,651x deflated on no physical change
at all. Two things in that table are not what they look like:

- **The build-time BRIN number is a parallel-build artifact.** Each participant
  spills one summary per range it touched and bumps its private count
  ([brin.c#form_and_spill_tuple](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1996-L2015)),
  the leader adopts the shared total
  ([brin.c#_brin_parallel_heapscan](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2568-L2596)),
  and the union that follows never recounts
  ([brin.c#_brin_parallel_merge](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2610-L2720)).
  Building the same index on the same table three ways, against a true 23:
  **23** serial, **44** with one worker, **101** with four. Only the serial number is
  deterministic, and only it equals the range count: the same day's baseline pass read
  44 and 98, and the 2026-09-16 run 45 and 103.
- **The post-`VACUUM` BRIN number is one short.** `brinvacuumcleanup` reports 22
  where `pageinspect` counts 23 summary tuples, and it passes the same pointer as
  both out-parameters of `brinsummarize`
  ([brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332)).
  The one-tuple gap is filed under [Open Questions](#open-questions).

### The thirteen invariants

Thirteen invariants were filed with the declarations, before the fixtures existed,
and checked over 90 censuses, 31 maintenance steps and 62 horizon readings. I10
through I13 are new on 2026-09-16, for [The maintenance was not
defeated](#the-maintenance-was-not-defeated):

| # | Claim | Result |
|---|---|---|
| I1 | `cur_size >= base_size` on every fixture not rebuilt since its baseline | **29 of 29** |
| I2 | the size bracket: `pg_relation_size(index, 'main')` re-read after the census equals [`block_size`](../../../glossary.md#blcksz) times the blocks the census scanned | **90 of 90** |
| I3 | hash: [`pgstathashindex`](../../../glossary.md#pgstatindex) page classes plus the metapage equal the file block count | **27 of 27** |
| I4 | hash: every block `hash_bitmap_info` reports free reads back as an unused page | **27 of 27** |
| I5 | GiST: the FSM free-page count never exceeds the census deleted-plus-new count | **13 of 13**; SP-GiST n/a |
| I6 | BRIN: the revmap entry count equals the live summary tuples on the regular pages | **13 of 13** |
| I7 | BRIN: the maintained size is never smaller than the unmaintained one | **4 of 4** |
| I8 | GIN: the metapage's entry and data page counts equal the census | **23 of 28**, all five failures explained |
| I9 | the `VACUUM VERBOSE` index line agrees with the census, and hash prints no line when its cleanup returned NULL | **22 present, 7 absent**, 19 of 22 agreeing |
| I10 | every `VACUUM` reports 0 tuples dead but not yet removable, unless the fixture declares a held snapshot | **25 of 25**; the two nonzero counts are both declared |
| I11 | no maintenance step was skipped or cut short, and all four settable timeouts read 0 in its session | **31 of 31**, 0 cancellations, one distinct timeout set |
| I12 | no census lock interval overlaps a maintenance interval | **0 overlaps** across 90 x 31 |
| I13 | no undeclared horizon holder at any maintenance step | **58 of 62** clean, the other 4 the declared snapshots; 0 slots, 0 prepared |

Three of those need their failures named, because the failures are the finding.

**I5 held trivially on GiST**, because the FSM free-page count was **0 on all 13
GiST censuses** - including `g06`, `g07` and `g09`, whose maintenance `VACUUM`
deleted 23,525, 26,315 and 7,613 pages respectively, and `g08`, whose post-release
`VACUUM` deleted 2,330. A page deleted by *this* VACUUM carries a delete-XID the
cluster has not passed, so `gistPageRecyclable` refuses it and it is not recorded
free
([gistutil.c#gistPageRecyclable](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L885-L908)).
That is the one-`VACUUM` lag, and all four reach it with no snapshot held while their
pages were deleted: `g08`'s snapshot was released before its second `VACUUM`, and
`n10`'s 375 deleted pages against FSM 0 are the same lag on GIN. It is not the GiST
coverage row "a deleted-but-not-recyclable page under a held snapshot", which needs a
page deleted while a snapshot older than its delete XID is still held. No fixture here
deletes a page under a held snapshot, so that row is filed as not reached. On the
recipes before 2026-09-16 both held-snapshot fixtures produced zero deleted pages; see
[What a defeated VACUUM looks like, measured](#what-a-defeated-vacuum-looks-like-measured).

**I8's five failures are all states where the metapage is stale by construction.**
Four are unmaintained `churn_raw` readings - `n03`, `n04`, `n06`, `n07` - where the
counters still describe the as-built index because only `ginvacuumcleanup` writes
them. The fifth is `n12` at `churn_maintained`, the auto-analyze stand-in, where the
pending-list flush moved 883 pages and wrote no counter. The weaker total-page
identity, `nTotalPages = blocks scanned`, failed on the same five plus `n05` and
`n12` at `churn_raw`: **21 of 28**. On every maintained state that a `VACUUM`
produced, both identities held.

**I9's three disagreements are all BRIN, and they are an ordering fact.**
`brinvacuumcleanup` sets `stats->num_pages` from `RelationGetNumberOfBlocks` and
*then* calls `brinsummarize`, which extends the file
([brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332)).
So the `VERBOSE` line reports the block count from before the cleanup's own
summarization: 3 against a scanned 4 on `b10`, 7 against 14 on `b11`, 4 against 7 on
`b12`. `b13`, whose ranges the stand-in had already summarized, agreed at 3 and 3.

The seven absent index lines are the other half of I9, and every one is expected: four
fixtures ran no `VACUUM` at all (`h00`, `h07`, `n08`, `n09`), two ran the
auto-analyze stand-in (`h05`, `n12`), and `h04` ran a full `VACUUM ANALYZE` whose
`hashbulkdelete` never fired because the
insert-only churn left no dead tuple - so `hashvacuumcleanup` returned NULL, `VACUUM`
printed no line and wrote no index statistics
([hash.c#hashvacuumcleanup](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L647-L663),
[vacuumlazy.c#verbose-index-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L732)).
`h04` is the protocol's "an index whose `hashbulkdelete` never ran" behavior, and it
is also the fixture whose 9.07 % reclaimable space the method read as `none`.

The per-AM shapes of the `VERBOSE` line came out exactly as the protocols describe.
Hash fills only `num_pages`: `h01` printed `(9618, 0, 0, 0)`. SP-GiST sets the other
three equal by assignment
([spgvacuum.c#final-stats](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L902-L905)):
`s08` printed `(30150, 238, 238, 238)`. BRIN leaves all three zero. GIN distinguishes
them: `n05` printed `(10392, 0, 2206, 2206)` and `n03` `(6184, 912, 912, 0)` - 912
posting-tree pages deleted by that VACUUM and none of them recyclable yet.

### The simulated auto-analyze census

After the maintenance step and before the decide pass, the run recomputes
`relation_needs_vacanalyze`'s analyze verdict for **every table in the fixture
database** from the effective reloption-or-GUC values, and analyzes the tables it
names
([autovacuum.c#verdicts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095),
[autovacuum.c#anl-effective-values](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3011-L3017)).
32 tables were censused; **1 was named**. Three of them exist only to pin the
boundary, each built to 10,000 rows so the threshold is `50 + 0.1 * 10000 = 1050`:

| Table | `reltuples` | `mod_since_analyze` | threshold | `autovacuum_enabled` | verdict |
|---|---|---|---|---|---|
| `tc_past` | 10000 | 2000 | 1050.00 | true | **analyze** |
| `tc_exact` | 10000 | **1050** | 1050.00 | true | leave alone |
| `tc_off` | 10000 | 2000 | 1050.00 | **false** | leave alone |

`tc_exact` sits **exactly** on its threshold and is left alone, because the engine's
test is strictly greater. `tc_off` is short-circuited by the reloption
([autovacuum.c#av_enabled-return](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3048-L3054)).
The other 29 tables, one per fixture, were analyzed by their own maintenance step or,
for the four no-churn fixtures, by their build phase, so their counters sat below
threshold and the census declined every one - which is the
expected outcome, not a null result: it is the recheck that the counters were
published in the right order. Each churn session called
`pg_stat_force_next_flush()` before the maintenance step
([pg_proc.dat#pg_stat_force_next_flush](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L5916-L5920)),
because an unforced flush happens at most once per `PGSTAT_MIN_INTERVAL` of 1000 ms
([pgstat.c#PGSTAT_MIN_INTERVAL](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L117-L122)),
and the census discards its statistics snapshot with `pg_stat_clear_snapshot()`
before reading, because `stats_fetch_consistency` defaults to `cache`
([guc_tables.c#stats_fetch_consistency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4966-L4974)).

### The instrument matrix, measured

The method itself reads only catalogs and `pg_relation_size`, so no instrument is
part of it. The cross-checks need them, and the non-B-tree protocol's matrix of
acceptances and refusals was measured rather than assumed, one index per AM:

| AM | `pgstattuple` | `pgstatindex` | `pgstathashindex` | `pgstatginindex` |
|---|---|---|---|---|
| hash | accepted | `is not a btree index` | **accepted** | `is not a GIN index` |
| gist | accepted | `is not a btree index` | `is not a hash index` | `is not a GIN index` |
| spgist | **`index "f_s08_i" (spgist index) is not supported`** | `is not a btree index` | `is not a hash index` | `is not a GIN index` |
| brin | **`index "f_b10_i" (brin index) is not supported`** | `is not a btree index` | `is not a hash index` | `is not a GIN index` |
| gin | **`index "f_n03_i" (gin index) is not supported`** | `is not a btree index` | `is not a hash index` | **accepted** |

Every refusal comes from the one dispatch on `relam`
([pgstattuple.c#pgstat_relation](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L260-L297)),
and `pgstathashindex` is the only AM-specific reader this set has
([pgstatindex.c#pgstathashindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L579-L610)).
It starts its scan at block 1 because block 0 is the metapage
([pgstatindex.c#pgstathashindex-loop](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L636-L650)),
which is exactly why invariant I3 adds one. `pageinspect` decoded hash, GiST, BRIN
and GIN pages for this run and has **no SP-GiST function at all**, so the SP-GiST
census is `page_header` and the FSM, and every SP-GiST page-class quantity on this
page is a level by the protocol's own rule.

### Handling the four required edge cases

**Manual REINDEX via filenode.** `baseline_state` compares the stored `fn` against
`pg_relation_filenode()`. `RelationSetNewRelfilenumber` is what makes this reliable -
it writes the new relfilenumber and resets `relpages`/`reltuples` on the same
pg_class row
([relcache.c#RelationSetNewRelfilenumber](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3943-L3955)).
Measured on `e_rebuild_i`: `strong REINDEX candidate` while the baseline matched,
then `rebuilt since baseline` / `capture new baseline` after a plain `REINDEX`
changed only the filenode, and the same verdict after a `REINDEX CONCURRENTLY` that
changed the index OID as well.

**Statistics resets.** Detected by monotonicity. After
`pg_stat_reset_single_table_counters()` on a churned fixture, with no physical change
whatever, the statement read `size_inflation` 2.537, `churn_ratio` NULL,
`churn_state = unknown: counters reset`, `vacuum_since_baseline` NULL and
`weak: inflated, churn unknown`. `d_ins` is what proves the reset: it read
**-300000**, and no other catalog fact distinguishes the state.

**Partial indexes.** `pf_shift` compares the current index/table `reltuples` fraction
with the stored one, and a shift outside `[0.7, 1.43]` suppresses the recommendation.
This works because `ANALYZE` genuinely measures the predicate fraction for a partial
index - `compute_index_stats` sets `tupleFract` from the sampled rows that pass the
predicate
([analyze.c#compute_index_stats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953)).
Measured on `h12`: `pf_shift` **8.974** against a true 9.00x population move, so the
column carries the `ANALYZE` sample's error on top of the shift; the row was
suppressed, and a rebuild returned **0 bytes**, so suppressing it was right.

**Human comments.** Preserved by replacing only the marker onwards. Measured across
capture, re-capture, `REINDEX` and `REINDEX CONCURRENTLY`: a two-line human comment
containing both `@` and `}` survived all four unchanged.

### Thirteen edge cases, measured

Each edge case is unscored: none of them is a [bloat](../../../glossary.md#bloat) claim, and none is compared with
the oracle. They ran in their own database, against the same published statements.

| # | Fixture | What it exercises | Measured result |
|---|---|---|---|
| e1 | `e_noanl_i` | an index with no baseline | **no row at all** from the published statement |
| e2 | `e_btree_i` | a hand-filed baseline on a B-tree | `unsupported access method` |
| e3 | `e_invalid_i` | a hand-filed baseline on an index left `indisvalid = false` by a concurrent build whose expression divided by zero | `skip: index not valid` |
| e4 | `e_nobase_i` | a baseline with no `ANALYZE` since | `inconclusive: no ANALYZE since baseline` |
| e5 | `e_reset_i` | `pg_stat_reset_single_table_counters()` | `weak: inflated, churn unknown`, `d_ins = -300000` |
| e6 | `e_rebuild_i` | plain `REINDEX`, then `REINDEX CONCURRENTLY` | filenode 16814 -> 16828, then OID 16814 -> 16829; `rebuilt since baseline` |
| e7 | `e_rebuild_i` | a two-line human comment with `@` and `}` | survived all four operations |
| e8 | `e_rebuild_i` | the payload size with and without `dbr` | 231/221 bytes plain on `f_h00_i`, 314/217 with the human comment, 340/243 with both |
| e9 | `e_ver_i` | a payload rewritten to `"v": 2` | `unsupported payload version` -> `capture new baseline` |
| e10 | `e_am_i` | a payload whose `am` says `gist` on a hash index | `access method changed` -> `capture new baseline` |
| e11 | `e_small_i` | a 184 kB index at `size_inflation` 2.300, `est_reclaim_pct` 56.5 | `none: index below 1 MB` |
| e12 | `e_noanl` | a table that has never been analyzed | capture generated a `RAISE WARNING`, not a baseline: 7 `COMMENT` statements and 1 refusal |
| e13 | the whole database | capture run twice in a row | 7 statements, then **0** |

Two of those are worth restating because they change earlier claims. **e1 retires a
known limitation**: the previous review filed the `churn_state` mislabel on a missing
baseline as limitation 12, and a statement that reports over the payload-carrying set
cannot produce that row. **e12 and e13 are the capture guard working in both
directions**: it refuses to write a baseline it cannot trust, and it refuses to
overwrite one that is still valid, which is the prompt's own "must not be
continuously overwritten" requirement expressed as a `WHERE` clause.

### Experimental thresholds

**These are starting points from 29 fixtures, not production values.**

| AM | Candidate: inflation / churn | Strong: inflation / churn | This run |
|---|---|---|---|
| hash | 1.30 / 0.50 | 1.50 / 1.00 | 3 flagged, all correct; 3 refusals |
| gist | 1.40 / 0.75 | 1.80 / 1.50 | 4 flagged, all correct |
| spgist | 1.40 / 0.75 | 1.80 / 1.50 | 3 flagged, all correct |
| gin | 1.50 / 1.00 | 2.00 / 2.00 | 4 flagged, all correct; 2 near-threshold misses at 14.9 % and 21.5 %; 3 refusals |
| brin | 2.00 / 1.00 | 3.00 / 2.00 | 0 flagged, and nothing to flag: all four fixtures reclaimed 0 bytes |

Because `1 - 1/inflation` tracks the reclaimable fraction as a level, a threshold is
still most usefully chosen in terms of the space you want back:

| Inflation threshold | Implied reclaimable fraction |
|---|---|
| 1.15 | 13 % |
| 1.30 | 23 % |
| 1.50 | 33 % |
| 2.00 | 50 % |
| 3.00 | 67 % |

An absolute floor is also applied: no index below 1 MB is ever recommended for
rebuild, regardless of ratio. On this run that floor is what silenced all four BRIN
fixtures, and it silenced nothing that had space to give back.

### Coverage the protocols require, and what this page skipped

The coverage plan was filed with the declarations, before the fixtures existed. The
two protocols now list 31 behaviors between them, counting the non-core admission rule.
**24 were reached, 2 more only partly because no SP-GiST decoder exists, 2 were not
reached, and 3 were declared skipped in advance.** The 2026-09-24 revision took out the
row for a `VACUUM` whose index cleanup did not run, which neither concept page lists any
more, and refiled the two rows it found wrongly marked reached. The GIN held-snapshot
row is reached by `n10`, which this page rebuilt on 2026-09-16; the GiST one is not; see
[What a defeated VACUUM looks like, measured](#what-a-defeated-vacuum-looks-like-measured).

| Protocol | Behavior | Fixture | Outcome |
|---|---|---|---|
| non-B-tree | hash: an overflow chain and a freed overflow page | `h01` | reached |
| non-B-tree | hash: a splitpoint allocation | `h02` | reached: 4,098 -> 20,749 blocks |
| non-B-tree | hash: an index whose `hashbulkdelete` never ran | `h04` | reached: no `VERBOSE` line, no index statistics |
| non-B-tree | GiST: an emptied leaf deleted, and one kept as the last downlink | `g07` | reached: 26,315 pages deleted |
| non-B-tree | GiST: a deleted-but-not-recyclable page under a held snapshot | `g08`, as planned on 2026-09-16 | **not reached**: under its snapshot `g08` deletes 0 pages. The 2,330 of 2,970 pages that the `VACUUM` after the release deletes sit at FSM count 0 because of their own delete XID, the one-`VACUUM` lag that `g06`, `g07` and `g09` also show at 23,525 / 26,315 / 7,613 deleted pages. Filed as reached until 2026-09-24 |
| non-B-tree | GiST: a sorted build beside a non-sorted one | `g09` | reached: `point_ops` carries support 11, `range_ops` does not |
| non-B-tree | SP-GiST: placeholders, a trailing run removed, an interior one kept | `s09` | partly: the FSM and `VERBOSE` counters moved, but `pageinspect` has no SP-GiST decoder, so the page classes are unverifiable and every SP-GiST page quantity is a level |
| non-B-tree | SP-GiST: an emptied non-root page and the root | `s09` | same limit |
| non-B-tree | BRIN: an unsummarized range before the maintenance step, and after | `b13` | reached |
| non-B-tree | BRIN: a desummarized range, and one summarized by the stand-in | `b13` | reached: 3 orphaned line pointers |
| non-B-tree | BRIN: a same-page update beside one that moved | `b10`, `b11` | reached: 0 orphans against 13 |
| non-B-tree | BRIN: more than one `pages_per_range` | `b12` | reached: 32 against 128 |
| non-B-tree / GIN | the maintenance pair | every fixture | reached: 7 of 29 moved |
| non-B-tree | the auto-analyze stand-in, a plain `ANALYZE` | `h05` | reached; the method refuses the state |
| non-B-tree / GIN | a table the census analyzed, and one it declined | `tc_past`, `tc_exact` | reached, including the exactly-on-threshold boundary |
| non-B-tree | an empty index and an untouched index | `h07`, `h00` | reached |
| non-B-tree | a non-default `fillfactor`, or `pages_per_range` | `h03`, `s10`, `b12` | reached |
| GIN | keys that no longer occur after churn | `n04` | reached |
| GIN | emptied posting-tree pages | `n03` | reached: 912 deleted, 0 recyclable |
| GIN | half-empty posting-tree leaves with nothing deletable | `n04`, as planned on 2026-09-16 | **not reached**: `n04` holds 0 posting-tree pages before and after its churn, so it has no posting-tree leaf to half-empty. Filed as reached until 2026-09-24 |
| GIN | a populated pending list, and the same index after a flush | `n05` | reached: 2,206 pending pages |
| GIN | an untouched index and an empty index | `n08`, `n09` | reached |
| GIN | a snapshot held across the settling `VACUUM` | `n10` | **reached**: 960,000 tuples dead but not yet removable, no index page touched under the snapshot, then 375 of 479 posting-tree pages deleted at FSM count 0 |
| GIN | more than one [operator class](../../../glossary.md#operator-class) | `n06`, `n07` | reached: `jsonb_path_ops` and `tsvector_ops` beside `array_ops` |
| GIN | one rebuild at more than one `maintenance_work_mem` | probe P6 | reached: 4MB / 64MB / 256MB |
| GIN | the auto-analyze stand-in, `ANALYZE` plus `gin_clean_pending_list()` | `n12` | reached; the method refuses the state |
| GIN | an undecodable page and an all-zero page | - | **declared skipped**: the method reads no index page, so it has no page-decode path |
| GIN | a concurrent `VACUUM`, a concurrent rebuild, a writer stream | - | **declared skipped**: every measurement is single-session under the measurement lock |
| non-B-tree | a non-core access method under the admission rule | - | **declared skipped**: `contrib/bloom` is outside the five AMs the method models |

### What left the page with its fixtures

Removed, with every claim each one backed:

| What went | Why |
|---|---|
| The **13-cell matrix** `c00`-`c12` and its results table | Its protocol is not either of the wiki's two: it evaluated the method before any `VACUUM`, took no measurement lock, ran no census, declared no bound, and had no BRIN stand-in. The 31 fixtures above replace it, and 10 of them are its cells re-run under the protocols |
| The **pre-`VACUUM` evaluation** and every claim from it, including "the `ANALYZE` gate held in all 39 / 78 pre-`VACUUM` evaluations" and `c05_gin_pending`'s 1.372 | Scoring a method against unmaintained churn is forbidden by both protocols. The unmaintained state is now measured as a census, and the [maintenance pair](#the-maintenance-pair-what-the-maintenance-step-moves) shows why the old reading was not a conservative version of the new one |
| The **six-run reproducibility claim** - "all six runs produced identical quadruples on all 13 cells" | The runs it summarized were produced outside a protocol, on a sandbox deleted on 2026-08-25, and cannot be re-diffed. This page now claims reproducibility only where it re-measured it: see below |
| The **six original probes P1-P6 and the 13 review probes** | Two of them recorded their own defects (an aborted `DELETE; VACUUM` in one `psql -c`, and a filed column that could not have come from the probe that printed it). All the facts worth keeping were re-measured by probes P1-P7 of the published script |
| The **`c12_partial` raw-ratio example** of 1.63 and 2.5 % reclaimed | Re-measured on `h12`: a raw ratio of 1.13 and **0 %** reclaimed |
| The claim that **`c01_hash_dup` over-estimates by 19.7 points** | Kept, and re-measured at **+19.66** on `h01` |
| Known limitation 12, the **`churn_state` mislabel on a missing baseline** | Retired: an index with no baseline now produces no row |

The 2026-09-16 review removed nothing further. It changed two fixture recipes and
added four invariants; what it removed are two claims, both of which were wrong
rather than unsupported:

| What went | Why |
|---|---|
| "`g08` and `n10` held a snapshot for 60 s across their maintenance `VACUUM` and produced zero deleted pages, because deleting 80 % of the rows emptied no GiST leaf and no GIN posting-tree page" | Half the diagnosis. The modulus delete did thin every page rather than empty any, but the snapshot was also opened **after** the churn committed, so the horizon was never pinned. Both are fixed and the state is reached; the old open question that proposed "a contiguous key band rather than a modulus" as the next attempt is closed, and it named only the half that was not decisive |
| the two "attempted and not reached" coverage rows | Reached, with numbers |

The 2026-09-24 revision removed two fixtures, with every claim they backed, and corrected
four claims that the page's own numbers did not support:

| What went | Why |
|---|---|
| **`h06` and `n11`**, a hash and a GIN fixture that deleted a quarter of their rows and were maintained by `VACUUM (ANALYZE, INDEX_CLEANUP OFF)`, with their declared exceptions X3 and X4 | Both concept pages stopped requiring "a `VACUUM` whose index cleanup did not run" and stopped declaring it an exception, so neither fixture's maintenance step is the `VACUUM ANALYZE` the protocols require. The measurement-lock exception X5 became X3 |
| the page's **one false negative**: `h06` refused with `inconclusive: dead tuples not yet reclaimed` while a rebuild returned 36.94 %, with its own section, Verdict result 5 and known limitation 7 | backed only by `h06` |
| "one option, two verdicts": `n11` scored `PASS` on the same refusal because its 24.97 % sat below GIN's 33.33 % justification | backed only by `h06` and `n11` |
| `h06`'s bound violation of -11.94 points, the page's worst under-estimate | backed only by `h06`; the worst is now `h05` at -10.71 |
| the coverage row "a `VACUUM` whose index cleanup did not run", under both protocols | neither concept page lists it any more |
| "`g08` reached a deleted-but-not-recyclable GiST page under a held snapshot" | contradicted by the page's own table: under the snapshot `g08` deletes 0 pages. Its 2,330 pages are deleted by the `VACUUM` after the release, and they are not yet free because of their own deletion XID, the one-`VACUUM` lag, not because of a snapshot |
| "`n04` reached half-empty posting-tree leaves" | contradicted by its census: `n04` holds 0 posting-tree pages at every phase |
| "31 of the 34 behaviors reached" | the 2026-09-16 plan listed 33 behaviors: 28 filed as reached, 2 as partly reached and 3 as skipped |
| "the 26 fixtures whose churn removed rows", in the known limitation then numbered 16 and now 15 | 22 fixtures deleted or updated rows then, and 20 do now |

What reproducibility this page claims, now over five passes from the same pin. The
2026-09-15 filed run and the 2026-09-16 filed run share **29 of 31 `(B, C, R)`
triples byte-identically**, on two separate clusters built from the same commit a day
apart. The two that differ are `n10`, rebuilt on purpose, and `g09`, the sorted GiST
build. On 2026-09-24 two more passes ran from this pin on macOS 27 arm64: the
2026-09-16 script unchanged, as a baseline, and the edited script, whose run every
number on this page comes from. On the 29 kept fixtures each of them shares **28
`(B, C, R)` triples byte-identically** with the 2026-09-16 run on Linux x86_64. The
29th is `g09` again, whose churned file has now read **453,484,544**, **454,483,968**,
**454,885,376**, **456,335,360** and **451,428,352** bytes on five passes - a spread
of 1.09 % that no recipe change explains and that this page does not claim to
control. Its sorted rebuild read 70,787,072 bytes on the 2026-09-16 run and on both
2026-09-24 passes. Four `size_inflation` figures move in the third decimal across
passes because their population term is an `ANALYZE` sample: `g06`, `h12`, `n04` and
`s08` on 2026-09-24. That moved `g06`'s bound verdict to `HELD` on the baseline pass
and back to `VIOLATED` on the recorded one. **No recommendation and no decision score
differs between any two passes on the 29 kept fixtures.** Two platforms agreeing on
every size but `g09` is not a claim of byte-exactness across machines.

### Known limitations

1. **`est_reclaim_pct` is a level, not a bound.** It was declared an upper bound and
   violated on 11 of 29 fixtures, by up to 10.71 points. Read it as a ranking
   statistic.
2. **A change in key distribution breaks the model.** `h01` over-estimated by 19.66
   points. Catalog metadata records how many rows are indexed, not how they are
   shaped, so a fresh build of new data can legitimately differ in bytes-per-tuple
   from a fresh build of the old data.
3. **The model has no intercept.** `expected = base_size * pop_ratio` assumes size is
   proportional to population through the origin. Every index has fixed overhead - a
   metapage, a revmap prefix, root pages - so the ratio is wrong for small indexes.
   For BRIN, where a whole index here is 3 to 14 pages, the fixed part dominates:
   `b10` reported 0.262 where the truth is ~1.0. The 1 MB floor contains the damage
   but does not fix the arithmetic.
4. **The BRIN arm is unvalidated against a true positive.** All four BRIN fixtures
   reclaimed 0 bytes, and all four were silenced by the size floor rather than by the
   ratio.
5. **An auto-analyze-maintained index is permanently out of reach.** The
   `vacuum_since_baseline` gate can never be satisfied on a table whose only
   maintenance is auto-analyze, measured on both `h05` and `n12`, where rebuilds
   returned 11.11 % and 11.50 %.
6. **An untouched index is refused, not cleared.** All four no-churn fixtures report
   `inconclusive: no ANALYZE since baseline` forever, because nothing will analyze a
   table nothing writes to.
7. **GIN's `avg_width` is post-TOAST**
   ([pg_statistic.h#stawidth](../../../../raw/postgres-17/src/include/catalog/pg_statistic.h#L40-L50)).
   For an indexed column whose values are TOASTed out of line, `iw` measures the
   pointer and the GIN input-mass normalization degrades toward a plain row count.
8. **[Expression indexes](../../../glossary.md#expression-index) are not normalized.** `iw` is summed from `pg_stats` rows for
   the *table's* columns, and an expression key has `indkey = 0`, so it contributes
   nothing. `ANALYZE` does store expression statistics against the index relation
   ([analyze.c#compute_index_stats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L828-L863)),
   which the statement does not read.
9. **The BRIN population term lags the table by a whole maintenance cycle.** `b13`
   grew by 1,000,000 rows and 47 unsummarized ranges, and until the next `VACUUM` or
   `ANALYZE` the table's `relpages` still read 11,977 - 94 ranges - so a reading
   taken in that window describes the pre-insert table. The mandatory maintenance
   step closes the window here; on a real server with `autosummarize` on, the index
   can also sit unsummarized indefinitely, because the work item `brininsert` queues
   is fulfilled only by an autovacuum worker.
10. **`pg_relation_size()` is VOLATILE and stats the filesystem**
    ([pg_proc.dat#pg_relation_size](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7487-L7495),
    [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L371)).
    The heuristic is catalog-plus-size, not purely catalog. On hash it is also the
    logical end of file, and a splitpoint allocation writes one page and leaves a
    hole ([hashpage.c#_hash_alloc_buckets](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L967-L1037)).
11. **A partial index whose predicate fraction is stable but whose rows churn heavily
    is scored normally**, and the `[0.7, 1.43]` suppression window is still an
    unvalidated guess: the one partial fixture shifted 8.974x, far outside it.
12. **Nothing here detects a `DROP INDEX`.** The comment is destroyed with the index
    ([dependency.c#deleteOneObject](../../../../raw/postgres-17/src/backend/catalog/dependency.c#L1326-L1336)),
    so a drop-and-recreate silently starts from no baseline - which now means no row
    at all.
13. **The oracle is not a property of the index alone.** On hash it follows the
    heap's estimate; on GIN it follows `maintenance_work_mem`; on GiST it follows the
    build strategy; on BRIN it follows `pages_per_range`. Every `truth_pct` on this
    page is therefore conditional on the recorded settings.
14. **The horizon proof is a pair of reads, not an interlock.** Both protocols say so
    themselves, and this run inherits it: `pg_stat_activity` and
    `pg_replication_slots` are sampled immediately before and after each maintenance
    step, so a holder that appeared and disappeared entirely inside the step would
    leave no trace in either read. The `dead but not yet removable` count is the only
    signal that comes from inside the statement, and it is one-sided: nonzero proves a
    pinned horizon, zero proves only that nothing was pinned for that table at that
    moment
    ([vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L659-L663)).
15. **On an insert-only fixture the maintenance proof has no signal at all.** `h04`,
    `h05`, `b13`, `n05` and `n12` delete nothing, so their `dead but not yet
    removable` count is 0 or absent whether or not a horizon was held. Invariant I10
    is therefore informative on the 20 fixtures whose churn deleted or updated rows,
    vacuous on the three insert-only fixtures that ran a `VACUUM` (`h04`, `b13`,
    `n05`), and has nothing to read on the six that ran none.

## Measurement Script

Every number on this page comes from one script, `idxmaint_protocol.sh`, filed in
full under [The script](#the-script). It is Bash and SQL only: a reviewer needs a C
toolchain, a shell and this page.

### How to use it

| Item | What to give |
|---|---|
| Purpose | Builds PostgreSQL 17.11 out of tree from this repository's pinned checkout and runs this page's whole programme under **both** protocols - [Mandatory Non-B-Tree, Non-GIN Bloat Tests](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md) for the hash, GiST, SP-GiST and BRIN fixtures and [Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md) for the GIN ones: the declared kinds and the declared exceptions filed before any fixture exists, 29 scored fixtures through build -> baseline -> churn (writes, maintenance step, census) -> decide under the measurement lock -> a measured `REINDEX INDEX` oracle, the simulated auto-analyze census, thirteen invariants and the per-AM cross-checks, seven mechanism probes, and thirteen edge cases |
| Invocation | `bash .wiki-runtime/tmp/idxnb/idxmaint_protocol.sh [stage ...]`, run from the repository root. With no arguments it runs every stage except `reset`, `start` and `clean`. Extract the fenced script below to that path first |
| Stages | Default order: `build declare fixtures churn analyze_census crosscheck decide oracle score probes edge verify`. `build` configures, builds and installs out of tree (skipped when the binary is already there), runs [`make check`](../../../glossary.md#regression-test) plus the three [contrib](../../../glossary.md#contrib) suites the cross-checks read, `initdb`s and starts the cluster; `declare` files the declared kind of every published column, the decision thresholds, the thirteen invariants, the three declared exceptions of the maintenance rule and the coverage plan, and **refuses to run once the fixture database exists**; `fixtures` runs the build phase and one baseline capture for all 29 fixtures; `churn` runs each recipe's writes, then a census of the unmaintained state, then the maintenance step, then a census of the maintained state, with the BRIN summarization stand-in and the two held-snapshot fixtures in line, each maintenance step bracketed by a horizon reading and run with the four settable timeouts forced to `0`; `analyze_census` recomputes the launcher's analyze verdict for every table and analyzes the ones it names; `crosscheck` records `VACUUM`'s own index line, the maintenance-effectiveness proof parsed from every maintenance log, the horizon holders, and the instrument refusals; `decide` runs the published evaluation statement verbatim inside one locked transaction, then stores the same rows for scoring; `oracle` rebuilds each index between two `pg_relation_size` readings; `score` carries the filed declarations into the fixture database and prints the scored table, the bound verdicts, the decision scores, the thirteen invariants, the declared exceptions and every phase size; `probes` runs the seven mechanism probes; `edge` runs the thirteen edge cases in their own database; `verify` re-extracts the three published statements from this page and diffs them against the files that ran. `reset` drops the databases so a re-run starts clean - **including the declarations database, so a `reset` is always followed by `declare`** - `start` starts an already-built cluster, and `clean` is not in the default order and must be run last |
| Environment | `REPO` (`$PWD`), `SRC` (`$REPO/raw/postgres-17`), `SANDBOX` (`$REPO/.wiki-runtime/tmp/idxnb`), `PAGE` (this file), `PORT` (`55427`), `JOBS` (`20`), `BASE_ROWS` (`1000000`), `BRIN_ROWS` (`2000000`), `SMALL_ROWS` (`300000`), `GIN_ROWS` (`600000`), `HOT_ROWS` (`1200000`), `A05_INSERTS` (`120000`), `ROUNDS` (`6`), `MWM` (`256MB`) |
| Prerequisites | See [Prerequisites](#prerequisites) |
| Output | Everything lands under `$SANDBOX/out/`, 359 files on the recorded run; see [Where the results land](#where-the-results-land). Read `score-table.txt`, `score-summary.txt` and `invariants.txt` first |
| Runtime | About 11 minutes 47 seconds end to end on the recorded host, from an empty sandbox with `JOBS=8`: 2 min 19 s for `build` (configure, `make -j8`, install, `make check` and three contrib suites), then 9 min 27 s for the eleven measuring stages. Within those: 1 min 15 s for the 29 fixtures, 6 min 36 s for the churn phase, 1 min for the oracle, 27 s for the probes, and under 10 s for the census, cross-check, decide, score, edge and verify stages together. The 2026-09-16 run on Linux x86_64 took about 12 min 41 s for the measuring stages plus about 7 minutes for its build |
| Cleanup | `bash idxmaint_protocol.sh clean` stops the cluster with `pg_ctl -m fast -w stop`, reports whether a `postmaster.pid` survived, how many processes still carry the data directory on their command line, and whether the port's socket or lock file is still in the socket directory, and then deletes the whole sandbox, which the recorded run had grown to 7.1 GB |

### Prerequisites

- A C toolchain, `make`, `flex`, `bison` and `perl`. The recorded run used Apple clang
  21.0.0 on Darwin 27.0.0 arm64; the 2026-09-16 run used gcc 13.3.0 on `Linux x86_64`.
  The script builds its own server; no installed PostgreSQL is used, and it never
  touches a cluster it did not create.
- `bash` and a `grep` that takes `-E`. The recorded run used Homebrew's `bash` 5.3.15
  and the system BSD `grep` 2.6.0; it was not run under macOS's own `/bin/bash` 3.2.
- No ICU or readline development headers are needed: the build configures
  `--without-icu --without-readline --with-zlib --enable-debug`, and `initdb` runs
  with `--locale=C --encoding=UTF8`, which is what makes the SP-GiST text fixtures
  and the `tsvector` GIN fixture deterministic.
- The pinned checkout present at `raw/postgres-17`, read-only. The script builds out
  of tree and writes nothing inside it.
- Port 55427 free, and about 8 GB under `.wiki-runtime/tmp/`.
- The `pageinspect`, [`pgstattuple`](../../../glossary.md#pgstattuple) and [`pg_freespacemap`](../../../glossary.md#pg_freespacemap) contrib modules, which
  `make -C contrib install` provides from the same tree. They are used by the
  cross-checks only; the method under test reads catalogs and `pg_relation_size`.
- Every `psql` call is `psql -X -v ON_ERROR_STOP=1` against the sandbox's own socket
  directory, so a stray `~/.psqlrc` cannot change a result and no error passes
  silently. The one probe whose *error text* is the result being measured - the
  concurrent build that divides by zero - runs without `ON_ERROR_STOP`.
- Superuser on that cluster, because `pageinspect`'s raw-page functions require it
  ([rawpage.c#get_raw_page_internal](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L141-L199)).

### Where the results land

| File | What is in it |
|---|---|
| `declared_kind.txt`, `declared_decision.txt`, `declared_invariant.txt`, `declared_exception.txt`, `declared_coverage.txt`, `declared_at.txt` | what was declared, and the timestamp it was filed at |
| `check-summary.txt`, `check-*.log` | `make check` and the three contrib suites |
| `baseline-sizes.txt`, `baseline_at.txt`, `baseline-count.txt` | the as-built size and `reltuples` of every fixture index, and when the baselines were filed |
| `capture-generated.sql`, `capture-run.log`, `read-baselines.txt` | the statements the published capture generated, their execution, and the published reader's output |
| `build-*.log`, `churn-*.log`, `maint-*.log`, `settle2-*.log`, `snapshot-*.log`, `standin-b13.log` | every phase's own output, including every `VACUUM VERBOSE` index line, the `tuples: ... are dead but not yet removable` line and the maintenance session's four timeouts |
| `horizon-*-maint_before.log`, `horizon-*-maint_after.log`, `horizon-*-settle2_*.log` | the horizon reading on each side of every maintenance step |
| `maintenance-proof.txt`, `horizon-holders.txt`, `declared-exceptions.txt` | the four proofs [The maintenance must not be defeated](#the-maintenance-was-not-defeated) demands, per fixture: the parsed maintenance proof, the horizon holders, and what each declared exception read on both sides of its release |
| `census-*-baseline.log`, `census-*-churn_raw.log`, `census-*-churn_maintained.log`, `census-*-settle2.log`, `census-b13-standin.log` | one locked census per fixture per phase |
| `census-verdicts.txt`, `census-analyzed.txt` | the simulated analyze census: one line per table, and the `ANALYZE` statements it generated |
| `census-summary.txt`, `verbose-lines.txt`, `instrument-matrix.txt` | the page census per fixture and phase, `VACUUM`'s index line, and the measured instrument refusals |
| `decide.txt` | the published statement's own output, under the measurement lock |
| `oracle-*.log`, `oracle-summary.txt` | the two size readings and the returned percentage per fixture |
| `score-table.txt`, `score-summary.txt`, `score-declarations.txt` | the scored table, its totals, and the declaration timestamps the scoring used |
| `invariants.txt`, `i6-i8-detail.txt`, `i9-detail.txt`, `phase-sizes.txt`, `maintenance-pair.txt`, `coverage.txt` | the thirteen invariants with their per-fixture detail, every phase size, and the coverage plan |
| `probe-p1.txt` ... `probe-p7.txt` | the `reltuples` progression, the parallel BRIN build, desummarize/summarize, the pending-list flush, the hash heap-estimate probe, the GIN budget sweep, and the GiST sortsupport catalog check |
| `edge.txt`, `edge-*.log`, `edge-capture*.sql` | the thirteen edge cases |
| `settings.txt`, `version.txt`, `pin.txt` | the settings the run fixes with their contexts, the server version, the commit the source is parked on |

### The last run

| Fact | Value |
|---|---|
| Date | 2026-09-24, 19:34:14Z to 19:46:01Z, from an empty sandbox |
| Server | PostgreSQL 17.11, built from `786db8dcf168bd9df8f55047337525ac19118b1c`, the commit the `build` stage recorded in `pin.txt` |
| Platform | Darwin 27.0.0 arm64 (macOS 27), Apple clang 21.0.0 (`clang-2100.3.34.2`), 10 cores, `JOBS=8`, Homebrew `bash` 5.3.15 |
| `block_size` | 8192 |
| [`max_data_alignment`](../../../glossary.md#alignment) | 8 |
| Regression suites | core **All 225**, `pageinspect` **All 8**, `pgstattuple` **All 1**, `pg_freespacemap` **All 1** |
| Cluster settings, with contexts | `autovacuum = off` and [`fsync = off`](../../../glossary.md#fsync) (both `PGC_SIGHUP`, reload), [`shared_buffers = 512MB`](../../../glossary.md#shared_buffers) (`PGC_POSTMASTER`, restart), `maintenance_work_mem = 256MB`, `work_mem = 64MB`, `statement_timeout = 1800s`, `lock_timeout = 15s`, `stats_fetch_consistency = cache`, `max_parallel_maintenance_workers = 2` (all `PGC_USERSET`, session/transaction scope) |
| Maintenance sessions only | `statement_timeout`, `lock_timeout`, `transaction_timeout` and `idle_in_transaction_session_timeout` all forced to `0` (all `PGC_USERSET`, session/transaction scope), recorded per step and identical on all 31 |
| Autovacuum thresholds | left at the shipped defaults and never applied: 50 / 0.2 dead, 1000 / 0.2 insert, 50 / 0.1 analyze, naptime 60 s (all `PGC_SIGHUP`) |
| Declarations filed | 2026-09-24T19:36:34Z, 75 seconds before the first fixture's baseline payload at 2026-09-24T19:37:49Z, into a database that did not yet exist |
| Scored fixtures | 29, in one database, plus 3 census tables |
| Oracle | `REINDEX INDEX` at `maintenance_work_mem = 256MB`, bracketed by `pg_relation_size(index, 'main')` |
| Filed text | the fenced script below was compared byte for byte with the file that ran: identical, 2,621 lines, SHA-256 `fbe6b4a0a8a93b826b040b39323d31f413f941138736b766b7170c1d0873c952` |
| Published statements | 3 of 3 byte-identical to this page, re-extracted by the `verify` stage at 81, 23 and 195 lines |
| Server log | 19 `ERROR` and `FATAL` lines, all deliberate: the 16 refusals of the instrument matrix, the division by zero that leaves `e_invalid_i` invalid, and the 2 snapshot holders the run terminates |

Three things about this run a reader should know, recorded rather than tidied away.

- **It is the second of two passes on this host that day.** The first ran the
  2026-09-16 script unchanged, from its own empty sandbox, as a baseline before anything
  was edited: 12 min 10 s, exit 0, the same four suites passed, and `verify` read 3 of 3.
  It reproduced every recommendation and every decision of the 2026-09-16 Linux filing
  on all 31 fixtures it still had, and it exposed the `grep` defect below. Its numbers
  appear on this page only where the baseline pass is named.
- **Three script defects were fixed besides the removal**, all exposed by running on
  macOS.
  - BSD `grep` reads a `$` placed before `\|` as a literal character, so
    `grep -c '^VACUUM$\|^ANALYZE$'` never counted a bare `VACUUM` [command tag](../../../glossary.md#command-tag), and the
    baseline pass's proof table read 0 command tags on every `VACUUM` log. The count is
    now `grep -Ec '^(VACUUM|ANALYZE)$'`. The recorded run reads 1 on every log that ran
    a maintenance statement and 0 on the four no-churn fixtures' logs.
  - The `clean` stage's process check was `pgrep -af`, and on macOS `-a` adds the
    caller's own ancestors to the match list. It is now `pgrep -f --`.
  - The `clean` stage's port check, `pgrep -af "port=$PORT"`, could never fire on any
    platform, because the port is set in `postgresql.conf` and is on no command line.
    It now reports whether the port's socket or lock file is still in the socket
    directory.

  A fourth change is cosmetic: `wc -l` pads its count with spaces on macOS, so the
  `fixtures` stage now trims it before printing.
- **The 2026-09-16 run's history still explains two recipes.** That run was the third
  pass from this pin on Linux x86_64. Two earlier passes were abandoned: the first when
  `n10`'s rebuilt fixture landed at 1,024,000 bytes, under the method's own 1 MB floor,
  and the second when the two held-snapshot fixtures still read `0` tuples dead but not
  yet removable, which exposed the snapshot-ordering defect. `reset` drops the
  declarations database as well as the fixture database, and the `declare` stage's own
  guard refused twice during that review, once on each abandoned pass.

### The script

```bash
#!/usr/bin/env bash
#
# idxmaint_protocol.sh - the measurement programme behind
# wiki/v17/questions/indexing/non-btree-index-inflation-comment-baseline.md
#
# Runs the COMMENT-stored `@idxmaint:` baseline heuristic for hash, GiST,
# SP-GiST, BRIN and GIN indexes under BOTH of the wiki's protocols:
#   * Mandatory Non-B-Tree, Non-GIN Bloat Tests  (hash, GiST, SP-GiST, BRIN)
#   * Mandatory GIN Bloat Tests                  (the GIN fixtures)
# Five phases per scored fixture - build, baseline, churn ending in the
# settle/maintenance step and the simulated analyze census, decide under the
# SHARE ROW EXCLUSIVE measurement lock, and a measured REINDEX INDEX oracle -
# with the declared kind of every published column filed before the first
# fixture exists, and every cross-check the two protocols require.
#
# Every object this script creates is DISPOSABLE. It builds its own PostgreSQL
# out of tree, runs its own cluster on a non-default port with its own socket
# directory, and the `clean` stage stops that cluster and deletes the sandbox.
# It never touches a cluster it did not start, and it treats raw/postgres-17 as
# read-only.
#
# Usage:  bash idxmaint_protocol.sh [stage ...]      (run from the repo root)
#         bash idxmaint_protocol.sh                  (same as `all`)
#
set -uo pipefail

REPO="${REPO:-$PWD}"
SRC="${SRC:-$REPO/raw/postgres-17}"
SANDBOX="${SANDBOX:-$REPO/.wiki-runtime/tmp/idxnb}"
PAGE="${PAGE:-$REPO/wiki/v17/questions/indexing/non-btree-index-inflation-comment-baseline.md}"
PORT="${PORT:-55427}"
JOBS="${JOBS:-20}"
BASE_ROWS="${BASE_ROWS:-1000000}"
BRIN_ROWS="${BRIN_ROWS:-2000000}"
SMALL_ROWS="${SMALL_ROWS:-300000}"
GIN_ROWS="${GIN_ROWS:-600000}"
# n10's hot-key fixture is sized so that three posting trees clear the method's
# own 1 MB floor: at 300,000 rows the whole index is 1,024,000 bytes and the
# floor would silence it, which would measure the fixture rather than the method
HOT_ROWS="${HOT_ROWS:-1200000}"
# a05 sits above the analyze threshold and below both vacuum thresholds, which
# is the only window in which auto-analyze is the whole of a table's maintenance
A05_INSERTS="${A05_INSERTS:-120000}"
ROUNDS="${ROUNDS:-6}"
MWM="${MWM:-256MB}"

BUILD="$SANDBOX/build"
INST="$SANDBOX/install"
BIN="$INST/bin"
PGDATA="$SANDBOX/data"
SOCK="$SANDBOX/sock"
OUT="$SANDBOX/out"
SQLD="$SANDBOX/sql"
LOG="$SANDBOX/server.log"
DB=idxnb
PDB=protocol
EDB=edge

export PGOPTIONS="-c statement_timeout=1800s -c lock_timeout=15s"

mkdir -p "$SANDBOX" "$SOCK" "$OUT" "$SQLD"

say() { printf '\n=== %s\n' "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

q()  { "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1" -At -c "$2"; }
Q()  { "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1" -c "$2"; }
qf() { "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1" -f "$2"; }
qin(){ "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1"; }
qat(){ "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1" -At -f "$2"; }
# -q as well, so a generated statement list carries no command tags
qgen(){ "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1" -At -f "$2"; }
# the few probes whose ERROR text is the result being measured
qe() { "$BIN/psql" -X -h "$SOCK" -p "$PORT" -d "$1"; }

# ---------------------------------------------------------------- the method
# The three statements below are the page's published SQL, byte for byte. The
# `verify` stage re-extracts them from the page and diffs them against these
# files, so the text that ran is provably the text that is published.
write_published_sql() {
  cat > "$SQLD/capture.sql" <<'WIKISQL'
SET /* wiki_idxmaint_guard */ statement_timeout = '60s';
SET /* wiki_idxmaint_guard */ lock_timeout = '5s';

SELECT /* wiki_idxmaint_capture_baseline */
       CASE
         WHEN st.analyze_count + st.autoanalyze_count = 0 THEN
           format('DO $$ BEGIN RAISE WARNING %L; END $$;',
                  'no baseline for ' || i.indexrelid::regclass::text ||
                  ': the table has never been analyzed, so an index reltuples' ||
                  ' is still a build artifact (run ANALYZE first)')
         ELSE
           format('COMMENT ON INDEX %s IS %L;',
                  i.indexrelid::regclass::text,
                  CASE WHEN human = '' THEN '' ELSE human || E'\n\n' END
                  || '@idxmaint:' || payload::text)
       END AS capture_statement
  FROM pg_index i
  JOIN pg_class ic ON ic.oid = i.indexrelid
  JOIN pg_class tc ON tc.oid = i.indrelid
  JOIN pg_namespace tn ON tn.oid = tc.relnamespace
  JOIN pg_am am ON am.oid = ic.relam
  JOIN pg_stat_all_tables st ON st.relid = i.indrelid
  CROSS JOIN (SELECT stats_reset FROM pg_stat_database
               WHERE datname = current_database()) d
  CROSS JOIN LATERAL (
       SELECT rtrim(regexp_replace(coalesce(obj_description(i.indexrelid, 'pg_class'), ''),
                                   '@idxmaint:.*$', ''), E' \t\r\n')            AS human,
              substring(obj_description(i.indexrelid, 'pg_class')
                        from '@idxmaint:(.*)$')                                 AS old_payload
  ) c
  CROSS JOIN LATERAL (
       SELECT jsonb_strip_nulls(jsonb_build_object(
                'v',    1,
                'ts',   to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                'am',   am.amname,
                'fn',   pg_relation_filenode(i.indexrelid),
                'isz',  pg_relation_size(i.indexrelid),
                'ipg',  ic.relpages,
                'itup', ic.reltuples::bigint,
                'tpg',  tc.relpages,
                'ttup', tc.reltuples::bigint,
                'ppr',  CASE WHEN am.amname = 'brin' THEN coalesce(
                               (SELECT o.option_value::int
                                  FROM pg_options_to_table(ic.reloptions) o
                                 WHERE o.option_name = 'pages_per_range'), 128)
                        END,
                'iw',   CASE WHEN am.amname = 'gin' THEN (
                               SELECT sum(s.avg_width)::int
                                 FROM unnest(i.indkey::int2[]) WITH ORDINALITY k(attnum, ord)
                                 JOIN pg_attribute a
                                   ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                                 JOIN pg_stats s
                                   ON s.schemaname = tn.nspname
                                  AND s.tablename  = tc.relname
                                  AND s.attname    = a.attname
                                WHERE k.ord <= i.indnkeyatts AND k.attnum <> 0)
                        END,
                'ins',  st.n_tup_ins,
                'upd',  st.n_tup_upd,
                'hot',  st.n_tup_hot_upd,
                'del',  st.n_tup_del,
                'vac',  st.vacuum_count,
                'avac', st.autovacuum_count,
                'anl',  st.analyze_count + st.autoanalyze_count,
                'dbr',  to_char(d.stats_reset AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
              )) AS payload
  ) p
 WHERE ic.relkind = 'i'
   AND am.amname IN ('hash', 'gist', 'spgist', 'brin', 'gin')
   AND i.indisvalid AND i.indislive
   AND tn.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
   AND pg_relation_filenode(i.indexrelid) IS NOT NULL
   -- refresh exactly the baselines that are absent or no longer describe the
   -- physical index, and leave every valid baseline untouched
   AND (c.old_payload IS NULL
        OR NOT (c.old_payload ~ '^\s*\{')
        OR (c.old_payload::jsonb ->> 'v') IS DISTINCT FROM '1'
        OR (c.old_payload::jsonb ->> 'am') IS DISTINCT FROM am.amname
        OR (c.old_payload::jsonb ->> 'fn')::oid
             IS DISTINCT FROM pg_relation_filenode(i.indexrelid))
 ORDER BY i.indexrelid::regclass::text;
WIKISQL

  cat > "$SQLD/read.sql" <<'WIKISQL'
SELECT /* wiki_idxmaint_read_baseline */
       c.oid::regclass                                                     AS index_name,
       am.amname,
       rtrim(regexp_replace(coalesce(d.description, ''), '@idxmaint:.*$', ''),
             E' \t\r\n')                                                   AS human_comment,
       length(d.description)                                               AS comment_bytes,
       length(substring(d.description from '@idxmaint:(.*)$'))             AS payload_bytes,
       substring(d.description from '@idxmaint:(.*)$')::jsonb              AS payload,
       (substring(d.description from '@idxmaint:(.*)$')::jsonb ->> 'ts')   AS base_ts,
       (substring(d.description from '@idxmaint:(.*)$')::jsonb ->> 'am')   AS base_am,
       (substring(d.description from '@idxmaint:(.*)$')::jsonb ->> 'fn')::oid     AS base_filenode,
       pg_relation_filenode(c.oid)                                         AS cur_filenode,
       (substring(d.description from '@idxmaint:(.*)$')::jsonb ->> 'isz')::bigint AS base_index_bytes,
       pg_relation_size(c.oid)                                             AS cur_index_bytes
  FROM pg_class c
  JOIN pg_am am ON am.oid = c.relam
  LEFT JOIN pg_description d
         ON d.objoid = c.oid
        AND d.classoid = 'pg_class'::regclass
        AND d.objsubid = 0
 WHERE c.relkind = 'i'
   AND d.description LIKE '%@idxmaint:%'
 ORDER BY 1;
WIKISQL

  cat > "$SQLD/evaluate.sql" <<'WIKISQL'
SET /* wiki_idxmaint_guard */ statement_timeout = '60s';
SET /* wiki_idxmaint_guard */ lock_timeout = '5s';

WITH /* wiki_idxmaint_evaluate */ b AS (
    SELECT i.indexrelid,
           i.indrelid,
           i.indpred IS NOT NULL                       AS is_partial,
           i.indisvalid,
           i.indislive,
           i.indkey,
           i.indnkeyatts,
           am.amname,
           tn.nspname                                  AS tschema,
           tc.relname                                  AS tname,
           ic.relpages::bigint                         AS ipg,
           ic.reltuples::numeric                       AS itup,
           tc.relpages::bigint                         AS tpg,
           tc.reltuples::numeric                       AS ttup,
           pg_relation_size(i.indexrelid)              AS isz,
           pg_relation_filenode(i.indexrelid)          AS fn,
           coalesce((SELECT o.option_value::int
                       FROM pg_options_to_table(ic.reloptions) o
                      WHERE o.option_name = 'pages_per_range'), 128) AS ppr,
           CASE WHEN pl.payload ~ '^\s*\{' THEN pl.payload::jsonb END AS j
      FROM pg_index i
      JOIN pg_class ic ON ic.oid = i.indexrelid
      JOIN pg_class tc ON tc.oid = i.indrelid
      JOIN pg_namespace tn ON tn.oid = tc.relnamespace
      JOIN pg_am am ON am.oid = ic.relam
      CROSS JOIN LATERAL (
           SELECT substring(obj_description(i.indexrelid, 'pg_class')
                            from '@idxmaint:(.*)$')    AS payload
      ) pl
     WHERE ic.relkind = 'i'
       AND pl.payload IS NOT NULL
),
cur AS (
    SELECT b.*,
           (SELECT sum(s.avg_width)::numeric
              FROM unnest(b.indkey::int2[]) WITH ORDINALITY k(attnum, ord)
              JOIN pg_attribute a ON a.attrelid = b.indrelid AND a.attnum = k.attnum
              JOIN pg_stats s ON s.schemaname = b.tschema
                             AND s.tablename  = b.tname
                             AND s.attname    = a.attname
             WHERE k.ord <= b.indnkeyatts AND k.attnum <> 0) AS iw
      FROM b
),
m AS (
    SELECT
      cur.*,
      st.n_tup_ins, st.n_tup_upd, st.n_tup_hot_upd, st.n_tup_del,
      st.n_live_tup, st.n_dead_tup,
      st.vacuum_count, st.autovacuum_count,
      st.analyze_count + st.autoanalyze_count AS anl,
      db.stats_reset,
      -- baseline validity
      CASE
        WHEN cur.j IS NULL                                 THEN 'no baseline'
        WHEN (cur.j->>'v') IS DISTINCT FROM '1'            THEN 'unsupported payload version'
        WHEN NOT cur.indislive                             THEN 'index not live'
        WHEN cur.fn IS NULL                                THEN 'no storage'
        WHEN (cur.j->>'am') IS DISTINCT FROM cur.amname    THEN 'access method changed'
        WHEN (cur.j->>'fn')::oid IS DISTINCT FROM cur.fn   THEN 'rebuilt since baseline'
        ELSE 'valid'
      END AS baseline_state,
      -- churn deltas
      st.n_tup_ins     - (cur.j->>'ins')::bigint  AS d_ins,
      st.n_tup_upd     - (cur.j->>'upd')::bigint  AS d_upd,
      st.n_tup_hot_upd - (cur.j->>'hot')::bigint  AS d_hot,
      st.n_tup_del     - (cur.j->>'del')::bigint  AS d_del,
      st.vacuum_count     - (cur.j->>'vac')::bigint  AS d_vac,
      st.autovacuum_count - (cur.j->>'avac')::bigint AS d_avac,
      st.analyze_count + st.autoanalyze_count
                          - (cur.j->>'anl')::bigint  AS d_anl,
      -- logical population, per access method
      CASE cur.amname
        WHEN 'brin' THEN ceil(GREATEST(cur.tpg, 0)::numeric / cur.ppr)
        WHEN 'gin'  THEN GREATEST(cur.itup, 0) * COALESCE(cur.iw, 1)
        ELSE             GREATEST(cur.itup, 0)
      END AS cur_pop,
      CASE (cur.j->>'am')
        WHEN 'brin' THEN ceil(GREATEST((cur.j->>'tpg')::numeric, 0) / (cur.j->>'ppr')::numeric)
        WHEN 'gin'  THEN GREATEST((cur.j->>'itup')::numeric, 0)
                           * COALESCE((cur.j->>'iw')::numeric, 1)
        ELSE             GREATEST((cur.j->>'itup')::numeric, 0)
      END AS base_pop,
      (cur.j->>'isz')::numeric AS base_isz,
      (cur.j->>'ts')           AS base_ts
      FROM cur
      JOIN pg_stat_all_tables st ON st.relid = cur.indrelid
      CROSS JOIN (SELECT stats_reset FROM pg_stat_database
                   WHERE datname = current_database()) db
),
d AS (
    SELECT m.*,
      -- statistics-reset detection: no per-table reset timestamp exists in v17,
      -- so a counter going backwards is the only positive proof.
      (d_ins < 0 OR d_upd < 0 OR d_hot < 0 OR d_del < 0 OR d_vac < 0 OR d_avac < 0)
        AS counters_went_backwards,
      (stats_reset IS DISTINCT FROM (j->>'dbr')::timestamptz) AS db_stats_reset_moved,
      CASE WHEN base_pop > 0 THEN base_isz * cur_pop / base_pop END AS expected_fresh_size,
      n_dead_tup::numeric / GREATEST(n_live_tup, 1) AS dead_ratio,
      CASE WHEN (j->>'ttup')::numeric > 0 AND ttup > 0
           THEN ((itup / ttup) / NULLIF((j->>'itup')::numeric / (j->>'ttup')::numeric, 0))
      END AS partial_fraction_shift
      FROM m
),
e AS (
    SELECT d.*,
      CASE WHEN expected_fresh_size > 0 THEN isz / expected_fresh_size END AS size_inflation,
      (d_upd - d_hot) AS d_nonhot_upd,
      (d_ins + (d_upd - d_hot) + d_del) AS churn,
      (d_vac + d_avac) > 0 AS vacuum_since_baseline
      FROM d
),
f AS (
    SELECT e.*,
      churn::numeric / GREATEST(n_live_tup, 1) AS churn_ratio,
      NOT counters_went_backwards AS churn_known
      FROM e
),
-- Experimental, per-access-method thresholds.  BRIN is deliberately the most
-- conservative: measured desummarize+summarize GREW a churned minmax_multi
-- index by 71%, and BRIN's size tracks table page count, not row churn.
-- This table is also the access-method guard: an AM with no row here is not
-- scored at all, because every threshold comparison against it would be NULL.
t AS (
    SELECT * FROM (VALUES
        ('hash',   1.30, 0.50, 1.50, 1.00),
        ('gist',   1.40, 0.75, 1.80, 1.50),
        ('spgist', 1.40, 0.75, 1.80, 1.50),
        ('gin',    1.50, 1.00, 2.00, 2.00),
        ('brin',   2.00, 1.00, 3.00, 2.00)
    ) AS v(amname, infl_cand, churn_cand, infl_strong, churn_strong)
)
SELECT
    f.indexrelid::regclass                       AS index_name,
    f.amname,
    f.is_partial,
    f.baseline_state,
    f.base_ts,
    pg_size_pretty(f.base_isz::bigint)           AS base_size,
    pg_size_pretty(f.isz)                        AS cur_size,
    pg_size_pretty(f.expected_fresh_size::bigint) AS expected_fresh,
    round(f.size_inflation, 3)                   AS size_inflation,
    -- the reclaimable-space proxy: if bytes per logical unit were invariant
    -- across the churn, a rebuild would land at cur_size / size_inflation
    GREATEST(round(100.0 * (1 - 1 / f.size_inflation), 1), 0) AS est_reclaim_pct,
    CASE f.amname WHEN 'brin' THEN 'summarized ranges'
                  WHEN 'gin'  THEN 'tuples x avg_width'
                  ELSE 'indexed tuples' END      AS pop_unit,
    round(f.base_pop, 0)                         AS base_pop,
    round(f.cur_pop, 0)                          AS cur_pop,
    f.d_ins, f.d_nonhot_upd, f.d_del,
    -- never publish a churn number derived from counters that went backwards
    CASE WHEN f.churn_known THEN round(f.churn_ratio, 3) END AS churn_ratio,
    CASE WHEN f.churn_known THEN 'known'
         ELSE 'unknown: counters reset' END      AS churn_state,
    CASE WHEN f.churn_known THEN f.vacuum_since_baseline END AS vacuum_since_baseline,
    CASE WHEN f.churn_known THEN f.d_vac + f.d_avac END      AS vacuums_since_baseline,
    round(f.dead_ratio, 4)                       AS dead_ratio,
    round(f.partial_fraction_shift, 3)           AS pf_shift,
    CASE
      -- B-tree and any other AM the model was never calibrated for.  Without
      -- this arm the LEFT JOIN leaves every threshold NULL and the CASE falls
      -- through to 'none', which reads as a verdict rather than a refusal.
      WHEN t.amname IS NULL                                THEN 'unsupported access method'
      WHEN f.baseline_state <> 'valid'                     THEN 'capture new baseline'
      WHEN NOT f.indisvalid                                THEN 'skip: index not valid'
      WHEN f.d_anl = 0                                     THEN 'inconclusive: no ANALYZE since baseline'
      WHEN f.expected_fresh_size IS NULL                   THEN 'inconclusive: no baseline population'
      WHEN f.is_partial AND (f.partial_fraction_shift < 0.7
                          OR f.partial_fraction_shift > 1.43)
                                                           THEN 'suppressed: predicate population moved'
      -- A reset zeroes vacuum_count too, so the VACUUM and dead-tuple gates
      -- below cannot be evaluated.  Report the size reading at low confidence
      -- rather than inventing a churn number.
      WHEN NOT f.churn_known AND f.size_inflation >= t.infl_cand
                                                           THEN 'weak: inflated, churn unknown'
      WHEN NOT f.churn_known                               THEN 'none (churn unknown)'
      WHEN NOT f.vacuum_since_baseline                     THEN 'inconclusive: no VACUUM since baseline'
      WHEN f.dead_ratio > 0.20                             THEN 'inconclusive: dead tuples not yet reclaimed'
      -- Nothing worth rebuilding.  BRIN indexes are normally a handful of
      -- pages, and the multiplicative model has no intercept, so a fixed
      -- metapage + revmap prefix dominates the ratio at that size.
      WHEN f.isz < 1048576                                 THEN 'none: index below 1 MB'
      WHEN f.size_inflation >= t.infl_strong
       AND f.churn_ratio >= t.churn_strong                  THEN 'strong REINDEX candidate'
      WHEN f.size_inflation >= t.infl_cand
       AND f.churn_ratio >= t.churn_cand                    THEN 'REINDEX candidate'
      ELSE 'none'
    END AS recommendation
  FROM f
  LEFT JOIN t ON t.amname = f.amname
 ORDER BY f.indexrelid::regclass::text;
WIKISQL
}

# ---------------------------------------------------------------- stage: build
stage_build() {
  say "build: 17.11 out of tree from $SRC"
  [ -d "$SRC" ] || die "no source checkout at $SRC"
  if [ ! -x "$BIN/postgres" ]; then
    mkdir -p "$BUILD"
    ( cd "$BUILD" && "$SRC/configure" --prefix="$INST" --without-icu --without-readline \
        --with-zlib --enable-debug > "$SANDBOX/configure.log" 2>&1 ) || die "configure failed"
    ( cd "$BUILD" && make -j"$JOBS" > "$SANDBOX/make.log" 2>&1 ) || die "make failed"
    ( cd "$BUILD" && make -C contrib -j"$JOBS" > "$SANDBOX/make-contrib.log" 2>&1 ) || die "contrib make failed"
    ( cd "$BUILD" && make install > "$SANDBOX/install.log" 2>&1 ) || die "install failed"
    ( cd "$BUILD" && make -C contrib install > "$SANDBOX/install-contrib.log" 2>&1 ) || die "contrib install failed"
  fi
  "$BIN/postgres" --version | tee "$OUT/version.txt"
  ( cd "$SRC" && git log -1 --format='%H %D' ) | tee "$OUT/pin.txt"

  say "build: make check plus the three contrib suites this run reads"
  ( cd "$BUILD" && make check > "$OUT/check-core.log" 2>&1 )
  for c in pageinspect pgstattuple pg_freespacemap; do
    ( cd "$BUILD/contrib/$c" && make check > "$OUT/check-$c.log" 2>&1 )
  done
  : > "$OUT/check-summary.txt"
  for f in "$OUT"/check-*.log; do
    printf '%-28s %s\n' "$(basename "$f")" \
      "$(grep -Eo '(All [0-9]+ tests? passed|[0-9]+ of [0-9]+ tests failed)' "$f" | tail -1)" \
      >> "$OUT/check-summary.txt"
  done
  cat "$OUT/check-summary.txt"

  if [ ! -d "$PGDATA" ]; then
    "$BIN/initdb" -D "$PGDATA" --locale=C --encoding=UTF8 > "$SANDBOX/initdb.log" 2>&1 \
      || die "initdb failed"
    cat >> "$PGDATA/postgresql.conf" <<CONF
# every setting below is recorded on the page with its context and apply scope
listen_addresses = ''
unix_socket_directories = '$SOCK'
port = $PORT
shared_buffers = 512MB
maintenance_work_mem = $MWM
work_mem = 64MB
autovacuum = off
fsync = off
log_line_prefix = '%m [%p] '
CONF
  fi
  stage_start
}

stage_start() {
  if "$BIN/pg_ctl" -D "$PGDATA" status > /dev/null 2>&1; then
    say "start: already running on port $PORT"
  else
    say "start: postmaster on port $PORT, socket $SOCK"
    "$BIN/pg_ctl" -D "$PGDATA" -l "$LOG" -w start > /dev/null || die "pg_ctl start failed"
  fi
  q postgres "SELECT /* wiki_idxmaint_hello */ version()" | tee -a "$OUT/version.txt"
  q postgres "SELECT /* wiki_idxmaint_settings */ name || ' = ' || setting || ' [' || context || ']'
                FROM pg_settings
               WHERE name IN ('autovacuum','block_size','maintenance_work_mem',
                              'shared_buffers','stats_fetch_consistency','fsync',
                              'autovacuum_analyze_threshold','autovacuum_analyze_scale_factor',
                              'autovacuum_vacuum_threshold','autovacuum_vacuum_scale_factor',
                              'autovacuum_vacuum_insert_threshold',
                              'autovacuum_vacuum_insert_scale_factor','autovacuum_naptime',
                              'max_parallel_maintenance_workers','statement_timeout','lock_timeout')
               ORDER BY name" | tee "$OUT/settings.txt"
  q postgres "SELECT /* wiki_idxmaint_settings */ 'max_data_alignment = ' || max_data_alignment ||
                ' [pg_control_init]' FROM pg_control_init()" | tee -a "$OUT/settings.txt"
}

# ------------------------------------------------------------- stage: declare
# Files the declared kind of every published column, the decision thresholds,
# the cross-check invariants and the coverage plan BEFORE any fixture exists.
# Both protocols forbid rewriting a declaration after the run, so this stage
# refuses to run once the fixture database is there.
stage_declare() {
  say "declare: kinds, thresholds, invariants and coverage, before the first fixture"
  if q postgres "SELECT /* wiki_idxmaint_guard */ count(*) FROM pg_database WHERE datname = '$DB'" \
     | grep -q '^1$'; then
    die "refusing to re-file declarations: database $DB already exists (run reset first)"
  fi
  q postgres "DROP /* wiki_idxmaint_declare */ DATABASE IF EXISTS $PDB" > /dev/null
  q postgres "CREATE /* wiki_idxmaint_declare */ DATABASE $PDB" > /dev/null
  qin "$PDB" <<'SQL'
-- DISPOSABLE bookkeeping objects.
CREATE /* wiki_idxmaint_declare */ TABLE declared_kind (
  column_name text primary key,
  declared_kind text not null check (declared_kind in ('lower bound','upper bound','level')),
  claim text not null,
  filed_at timestamptz not null default now()
);
INSERT /* wiki_idxmaint_declare */ INTO declared_kind (column_name, declared_kind, claim) VALUES
 ('est_reclaim_pct',  'upper bound', 'the percentage it names is never less than the percentage of the file REINDEX INDEX returns'),
 ('size_inflation',   'level',       'the population-normalized size ratio; a ranking statistic with no claim against the oracle'),
 ('expected_fresh',   'level',       'the modelled fresh-build size; no claim against the oracle'),
 ('churn_ratio',      'level',       'index-affecting churn over live tuples; no claim against the oracle'),
 ('dead_ratio',       'level',       'dead over live tuples at evaluation time; no claim against the oracle'),
 ('pf_shift',         'level',       'the partial-predicate fraction shift; a suppression input, not a byte claim'),
 ('base_pop',         'level',       'the stored baseline logical population itself'),
 ('cur_pop',          'level',       'the current logical population itself'),
 ('base_size',        'level',       'the stored baseline file size itself'),
 ('cur_size',         'level',       'the current file size itself'),
 ('d_ins',            'level',       'raw inserted-tuple delta'),
 ('d_nonhot_upd',     'level',       'raw non-HOT update delta'),
 ('d_del',            'level',       'raw deleted-tuple delta'),
 ('vacuums_since_baseline', 'level', 'count of VACUUMs since the baseline');

CREATE /* wiki_idxmaint_declare */ TABLE declared_decision (
  knob text primary key, value text not null, meaning text not null,
  filed_at timestamptz not null default now()
);
INSERT /* wiki_idxmaint_declare */ INTO declared_decision (knob, value, meaning) VALUES
 ('hash candidate',   'size_inflation >= 1.30 AND churn_ratio >= 0.50', 'the method flags a rebuild'),
 ('hash strong',      'size_inflation >= 1.50 AND churn_ratio >= 1.00', 'the method flags a rebuild'),
 ('gist candidate',   'size_inflation >= 1.40 AND churn_ratio >= 0.75', 'the method flags a rebuild'),
 ('gist strong',      'size_inflation >= 1.80 AND churn_ratio >= 1.50', 'the method flags a rebuild'),
 ('spgist candidate', 'size_inflation >= 1.40 AND churn_ratio >= 0.75', 'the method flags a rebuild'),
 ('spgist strong',    'size_inflation >= 1.80 AND churn_ratio >= 1.50', 'the method flags a rebuild'),
 ('gin candidate',    'size_inflation >= 1.50 AND churn_ratio >= 1.00', 'the method flags a rebuild'),
 ('gin strong',       'size_inflation >= 2.00 AND churn_ratio >= 2.00', 'the method flags a rebuild'),
 ('brin candidate',   'size_inflation >= 2.00 AND churn_ratio >= 1.00', 'the method flags a rebuild'),
 ('brin strong',      'size_inflation >= 3.00 AND churn_ratio >= 2.00', 'the method flags a rebuild'),
 ('size floor',       'cur_size < 1 MB', 'below this the method never flags a rebuild, whatever the ratio'),
 ('oracle justification hash',   'truth_pct >= 23.08', 'a rebuild was worth it: 100 * (1 - 1/1.30)'),
 ('oracle justification gist',   'truth_pct >= 28.57', 'a rebuild was worth it: 100 * (1 - 1/1.40)'),
 ('oracle justification spgist', 'truth_pct >= 28.57', 'a rebuild was worth it: 100 * (1 - 1/1.40)'),
 ('oracle justification gin',    'truth_pct >= 33.33', 'a rebuild was worth it: 100 * (1 - 1/1.50)'),
 ('oracle justification brin',   'truth_pct >= 50.00', 'a rebuild was worth it: 100 * (1 - 1/2.00)');

CREATE /* wiki_idxmaint_declare */ TABLE declared_invariant (
  id text primary key, claim text not null, filed_at timestamptz not null default now()
);
INSERT /* wiki_idxmaint_declare */ INTO declared_invariant (id, claim) VALUES
 ('I1', 'cur_size >= base_size on every fixture that was not rebuilt since its baseline'),
 ('I2', 'size bracket: pg_relation_size(index, main) re-read after the census equals block_size times the blocks the census scanned'),
 ('I3', 'hash: pgstathashindex page classes plus the metapage and bitmap blocks equal the file block count'),
 ('I4', 'hash: every block hash_bitmap_info reports free reads back as an unused page'),
 ('I5', 'GiST: the FSM free-page count never exceeds the census deleted-plus-new count; on SP-GiST the same check is recorded not applicable, because pageinspect ships no SP-GiST decoder and there is no deleted-page count to compare'),
 ('I6', 'BRIN: the revmap entry count equals the summary tuples the regular pages hold'),
 ('I7', 'BRIN: the index size after the maintenance step is never smaller than before it'),
 ('I8', 'GIN: the metapage entry and data page counts equal the census, with a not-yet-recyclable deleted page counted as data and a live list page in neither bucket'),
 ('I9', 'the VACUUM VERBOSE index line agrees with the census, and hash prints no line at all when its cleanup returned NULL'),
 ('I10', 'the maintenance was not defeated: every VACUUM the maintenance step ran reports 0 tuples dead but not yet removable, except on a fixture that declares a held snapshot, where the count is nonzero while the snapshot is held and 0 on the VACUUM after its release'),
 ('I11', 'the maintenance step was neither skipped nor cut short: no maintenance log carries a "skipping vacuum of"/"skipping analyze of" line or a cancellation, and all four settable timeouts read 0 in the maintenance session'),
 ('I12', 'the measurement lock was never held across a maintenance step: no census lock interval overlaps any maintenance interval'),
 ('I13', 'no holder other than a fixture declared snapshot could have pinned the horizon: at every maintenance step the cluster carries 0 prepared transactions, 0 replication slots with an xmin, and no backend with a transaction id or xmin other than the declared one');

CREATE /* wiki_idxmaint_declare */ TABLE declared_exception (
  id text primary key, fixture text not null, state text not null,
  reading_rule text not null, filed_at timestamptz not null default now()
);
-- The two exceptions "The maintenance must not be defeated" declares rather
-- than forbids: the held snapshot, once per protocol, and the measurement
-- lock.  Filed here, before any fixture exists, because a state declared
-- after the run is an excuse rather than a declaration.
INSERT /* wiki_idxmaint_declare */ INTO declared_exception (id, fixture, state, reading_rule) VALUES
 ('X1', 'g08', 'a REPEATABLE READ snapshot opened in a second session before the churn commits and held across the maintenance VACUUM',
         'the churn_maintained reading is a held-horizon reading and is never published as a maintained-state one; the settle2 reading, taken after the snapshot is released and a second VACUUM ANALYZE has run, is the maintained state the method is scored on'),
 ('X2', 'n10', 'a REPEATABLE READ snapshot opened in a second session before the churn commits and held across the settling VACUUM',
         'same as X1: churn_maintained is held-horizon, settle2 is the maintained state'),
 ('X3', 'protocol', 'the SHARE ROW EXCLUSIVE measurement lock, which excludes VACUUM and ANALYZE by design',
         'taken per census in its own transaction and released at COMMIT, never held across a maintenance step; invariant I12 checks the intervals do not overlap');

CREATE /* wiki_idxmaint_declare */ TABLE declared_coverage (
  protocol text not null, behavior text not null, fixture text not null,
  filed_at timestamptz not null default now(),
  primary key (protocol, behavior)
);
INSERT /* wiki_idxmaint_declare */ INTO declared_coverage (protocol, behavior, fixture) VALUES
 ('non-btree','hash: an overflow chain, and a freed overflow page whose bitmap bit was cleared','h01'),
 ('non-btree','hash: a splitpoint allocation','h02'),
 ('non-btree','hash: an index whose hashbulkdelete never ran','h04'),
 ('non-btree','GiST: an emptied leaf that was deleted, and one that survived as its parent last downlink','g07'),
 ('non-btree','GiST: a deleted-but-not-recyclable page under a held snapshot','not reached: g08''s snapshot stops its maintenance VACUUM deleting any page, and the pages its VACUUM after the release deletes wait on their own deletion XID, not on a held snapshot'),
 ('non-btree','GiST: a sorted build beside a non-sorted one','g09'),
 ('non-btree','SP-GiST: redirects turned into placeholders, a trailing run removed, an interior one retained','s09'),
 ('non-btree','SP-GiST: an emptied non-root page and the root page','s09'),
 ('non-btree','BRIN: an unsummarized range measured before the maintenance step, and the same index after it','b13'),
 ('non-btree','BRIN: a desummarized range, and a range summarized by the stand-in','b13'),
 ('non-btree','BRIN: a same-page summary update beside one that moved to another page','b10 and b11'),
 ('non-btree','BRIN: more than one pages_per_range','b12'),
 ('non-btree','all: the maintenance pair, the same churn before and after the maintenance step','every scored fixture: the churn_raw census beside the churn_maintained one'),
 ('non-btree','all: an index maintained by the auto-analyze stand-in, a plain ANALYZE','h05'),
 ('non-btree','all: a table the census analyzed, and one it declined','tc_past and tc_exact'),
 ('non-btree','all: an empty index and an untouched index','h07 and h00'),
 ('non-btree','all: a non-default fillfactor, or for BRIN a non-default pages_per_range','h03, s10 and b12'),
 ('gin','keys that no longer occur after churn','n04'),
 ('gin','emptied posting-tree pages','n03'),
 ('gin','half-empty posting-tree leaves with nothing deletable','not reached: n04 holds no posting-tree page before or after its churn, so it has no posting-tree leaf to half-empty'),
 ('gin','a populated pending list, and the same index after a flush','n05'),
 ('gin','an untouched index and an empty index','n08 and n09'),
 ('gin','a snapshot held across the settling VACUUM','n10, three hot keys so posting trees exist and a contiguous id band so whole posting-tree leaves empty'),
 ('gin','more than one operator class','n06 and n07'),
 ('gin','one rebuild at more than one maintenance_work_mem','p6'),
 ('gin','a churned index whose maintenance step ran, beside the same churn before it','every GIN fixture: churn_raw beside churn_maintained'),
 ('gin','an index maintained by the auto-analyze stand-in, ANALYZE plus gin_clean_pending_list','n12'),
 ('gin','a table the census analyzed, and one it declined to analyze','tc_past and tc_exact'),
 ('gin','an undecodable or unclassifiable page, and an all-zero page','skipped: the method reads no index page, so it has no page-decode path to exercise'),
 ('gin','a concurrent VACUUM, a concurrent rebuild and a writer stream','skipped: every measurement is single-session under the measurement lock'),
 ('non-btree','a non-core access method under the four-part admission rule','skipped: contrib/bloom is outside the five AMs the method models');
SQL
  q "$PDB" "SELECT /* wiki_idxmaint_declare */ column_name || ' -> ' || declared_kind || ' @ ' ||
              to_char(filed_at, 'YYYY-MM-DD HH24:MI:SS') FROM declared_kind ORDER BY 1" \
    | tee "$OUT/declared_kind.txt"
  q "$PDB" "SELECT /* wiki_idxmaint_declare */ knob || ': ' || value FROM declared_decision ORDER BY 1" \
    | tee "$OUT/declared_decision.txt"
  q "$PDB" "SELECT /* wiki_idxmaint_declare */ id || ': ' || claim FROM declared_invariant
              ORDER BY substring(id from 2)::int" \
    | tee "$OUT/declared_invariant.txt"
  q "$PDB" "SELECT /* wiki_idxmaint_declare */ id || ' | ' || fixture || ' | ' || state
              || ' | ' || reading_rule FROM declared_exception ORDER BY 1" \
    | tee "$OUT/declared_exception.txt"
  q "$PDB" "SELECT /* wiki_idxmaint_declare */ protocol || ' | ' || behavior || ' -> ' || fixture
              FROM declared_coverage ORDER BY protocol, behavior" \
    | tee "$OUT/declared_coverage.txt"
  date -u +'declarations filed at %Y-%m-%dT%H:%M:%SZ' | tee "$OUT/declared_at.txt"
}

stage_reset() {
  say "reset: drop the databases so a re-run starts clean"
  if "$BIN/pg_ctl" -D "$PGDATA" status > /dev/null 2>&1; then
    q postgres "DROP /* wiki_idxmaint_reset */ DATABASE IF EXISTS $DB" > /dev/null
    q postgres "DROP /* wiki_idxmaint_reset */ DATABASE IF EXISTS $PDB" > /dev/null
    q postgres "DROP /* wiki_idxmaint_reset */ DATABASE IF EXISTS $EDB" > /dev/null
  fi
}

# ------------------------------------------------------- fixture bookkeeping
# Every fixture object below is DISPOSABLE: created by this script, dropped
# with the sandbox.
HASHFX="h00 h01 h02 h03 h04 h05 h07 h08 h12"
GISTFX="g06 g07 g08 g09"
SPGFX="s08 s09 s10"
BRINFX="b10 b11 b12 b13"
GINFX="n03 n04 n05 n06 n07 n08 n09 n10 n12"
SCORED="$HASHFX $GISTFX $SPGFX $BRINFX $GINFX"

tbl() { printf 'f_%s' "$1"; }
idx() { printf 'f_%s_i' "$1"; }

fx_am() {
  case "$1" in
    h*) printf 'hash' ;;
    g*) printf 'gist' ;;
    s*) printf 'spgist' ;;
    b*) printf 'brin' ;;
    n*) printf 'gin' ;;
  esac
}

proto_ddl() {
  cat <<'SQL'
CREATE /* wiki_idxmaint_proto */ SCHEMA proto;
CREATE /* wiki_idxmaint_proto */ EXTENSION pageinspect;
CREATE /* wiki_idxmaint_proto */ EXTENSION pgstattuple;
CREATE /* wiki_idxmaint_proto */ EXTENSION pg_freespacemap;

CREATE TABLE proto.meas (
  fixture text not null, phase text not null, metric text not null,
  num numeric, txt text, at timestamptz not null default clock_timestamp()
);

CREATE FUNCTION proto.note(p_fix text, p_phase text, p_metric text,
                           p_num numeric DEFAULT NULL, p_txt text DEFAULT NULL)
RETURNS void LANGUAGE sql AS $fn$
  INSERT INTO proto.meas(fixture,phase,metric,num,txt)
  VALUES (p_fix,p_phase,p_metric,p_num,p_txt);
$fn$;

-- ----------------------------------------------------------- page censuses
-- One function per access method, because the pinned tree offers a different
-- reader for each and refuses two of them outright.  Every per-block decode
-- runs inside its own exception block: a page the shipped reader will not
-- classify is counted as `unreadable` rather than failing the census.

CREATE FUNCTION proto.census_hash(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  n int; nblocks int; t text;
  c_meta int := 0; c_bucket int := 0; c_ovfl int := 0; c_bitmap int := 0;
  c_unused int := 0; c_bad int := 0;
  fb int := 0; fb_agree int := 0; fb_dis int := 0; st record; hs record;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass,'main') / blk;
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
    -- The reader refuses a metapage or bitmap block by design, so those are
    -- excluded from the comparison rather than counted as disagreements.
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
  SELECT * INTO st FROM pgstattuple(p_idx::regclass);
  INSERT INTO proto.meas(fixture,phase,metric,num) VALUES
   (p_fix,p_phase,'census_scanned',   nblocks),
   (p_fix,p_phase,'census_meta',      c_meta),
   (p_fix,p_phase,'census_bucket',    c_bucket),
   (p_fix,p_phase,'census_overflow',  c_ovfl),
   (p_fix,p_phase,'census_bitmap',    c_bitmap),
   (p_fix,p_phase,'census_unused',    c_unused),
   (p_fix,p_phase,'census_unreadable',c_bad),
   (p_fix,p_phase,'bitmap_free',      fb),
   (p_fix,p_phase,'bitmap_agree',     fb_agree),
   (p_fix,p_phase,'bitmap_disagree',  fb_dis),
   (p_fix,p_phase,'hs_bucket_pages',  hs.bucket_pages),
   (p_fix,p_phase,'hs_overflow_pages',hs.overflow_pages),
   (p_fix,p_phase,'hs_bitmap_pages',  hs.bitmap_pages),
   (p_fix,p_phase,'hs_unused_pages',  hs.unused_pages),
   (p_fix,p_phase,'hs_live_items',    hs.live_items),
   (p_fix,p_phase,'hs_dead_items',    hs.dead_items),
   (p_fix,p_phase,'hs_free_percent',  hs.free_percent),
   (p_fix,p_phase,'pgst_free_percent',st.free_percent),
   (p_fix,p_phase,'pgst_tuple_count', st.tuple_count),
   (p_fix,p_phase,'size_after_census',pg_relation_size(p_idx::regclass,'main'));
END $fn$;

CREATE FUNCTION proto.census_gist(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  n int; nblocks int; fl text[]; hdr record;
  c_leaf int := 0; c_inner int := 0; c_del int := 0; c_zero int := 0; c_bad int := 0;
  st record; fsm_free int;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass,'main') / blk;
  FOR n IN 0 .. nblocks - 1 LOOP
    BEGIN
      SELECT * INTO hdr FROM page_header(get_raw_page(p_idx, n));
      IF hdr.lower = 0 AND hdr.upper = 0 THEN
        c_zero := c_zero + 1;
        CONTINUE;
      END IF;
      SELECT flags INTO fl FROM gist_page_opaque_info(get_raw_page(p_idx, n));
      IF fl @> ARRAY['deleted'] THEN c_del := c_del + 1;
      ELSIF fl @> ARRAY['leaf']  THEN c_leaf := c_leaf + 1;
      ELSE c_inner := c_inner + 1;
      END IF;
    EXCEPTION WHEN OTHERS THEN
      c_bad := c_bad + 1;
    END;
  END LOOP;
  SELECT * INTO st FROM pgstattuple(p_idx::regclass);
  SELECT count(*) INTO fsm_free FROM pg_freespace(p_idx::regclass) WHERE avail > 0;
  INSERT INTO proto.meas(fixture,phase,metric,num) VALUES
   (p_fix,p_phase,'census_scanned',   nblocks),
   (p_fix,p_phase,'census_leaf',      c_leaf),
   (p_fix,p_phase,'census_inner',     c_inner),
   (p_fix,p_phase,'census_deleted',   c_del),
   (p_fix,p_phase,'census_new',       c_zero),
   (p_fix,p_phase,'census_unreadable',c_bad),
   (p_fix,p_phase,'fsm_free_pages',   fsm_free),
   (p_fix,p_phase,'pgst_free_percent',st.free_percent),
   (p_fix,p_phase,'pgst_tuple_count', st.tuple_count),
   (p_fix,p_phase,'size_after_census',pg_relation_size(p_idx::regclass,'main'));
END $fn$;

-- pageinspect ships no SP-GiST decoder, so this census is the page header and
-- nothing else, and every page-class quantity derived from it is a level.
CREATE FUNCTION proto.census_spgist(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  n int; nblocks int; hdr record;
  c_used int := 0; c_zero int := 0; c_bad int := 0; slack bigint := 0;
  fsm_free int;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass,'main') / blk;
  FOR n IN 0 .. nblocks - 1 LOOP
    BEGIN
      SELECT * INTO hdr FROM page_header(get_raw_page(p_idx, n));
      IF hdr.lower = 0 AND hdr.upper = 0 THEN c_zero := c_zero + 1;
      ELSE c_used := c_used + 1; slack := slack + (hdr.upper - hdr.lower);
      END IF;
    EXCEPTION WHEN OTHERS THEN c_bad := c_bad + 1;
    END;
  END LOOP;
  SELECT count(*) INTO fsm_free FROM pg_freespace(p_idx::regclass) WHERE avail > 0;
  INSERT INTO proto.meas(fixture,phase,metric,num) VALUES
   (p_fix,p_phase,'census_scanned',   nblocks),
   (p_fix,p_phase,'census_used',      c_used),
   (p_fix,p_phase,'census_new',       c_zero),
   (p_fix,p_phase,'census_unreadable',c_bad),
   (p_fix,p_phase,'census_slack',     slack),
   (p_fix,p_phase,'fsm_free_pages',   fsm_free),
   (p_fix,p_phase,'size_after_census',pg_relation_size(p_idx::regclass,'main'));
END $fn$;

CREATE FUNCTION proto.census_brin(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  n int; nblocks int; t text; k int; ph int; un int;
  c_meta int := 0; c_revmap int := 0; c_reg int := 0; c_bad int := 0;
  items bigint := 0; placeholders bigint := 0; unused bigint := 0;
  revmap_entries bigint := 0;
  fsm_free int; fsm_avail bigint;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass,'main') / blk;
  FOR n IN 0 .. nblocks - 1 LOOP
    BEGIN
      t := brin_page_type(get_raw_page(p_idx, n));
    EXCEPTION WHEN OTHERS THEN
      t := 'unreadable';
    END;
    IF t = 'meta' THEN c_meta := c_meta + 1;
    ELSIF t = 'revmap' THEN
      c_revmap := c_revmap + 1;
      SELECT count(*) INTO k FROM brin_revmap_data(get_raw_page(p_idx, n)) r
       WHERE r.pages IS NOT NULL AND (r.pages::text <> '(0,0)');
      revmap_entries := revmap_entries + k;
    ELSIF t = 'regular' THEN
      c_reg := c_reg + 1;
      BEGIN
        -- brin_page_items returns one row per (item, attnum) pair, and it
        -- emits a row with every column but itemoffset NULL for an item whose
        -- line pointer is unused - which is exactly what brin_doupdate's
        -- relocate branch and brin_desummarize_range leave behind.  So a live
        -- summary tuple is a distinct itemoffset with a blknum.
        SELECT count(DISTINCT bi.itemoffset) FILTER (WHERE bi.blknum IS NOT NULL),
               count(DISTINCT bi.itemoffset) FILTER (WHERE bi.placeholder),
               count(DISTINCT bi.itemoffset) FILTER (WHERE bi.blknum IS NULL)
          INTO k, ph, un
          FROM brin_page_items(get_raw_page(p_idx, n), p_idx::regclass) bi;
        items := items + k;
        placeholders := placeholders + ph;
        unused := unused + un;
      EXCEPTION WHEN OTHERS THEN
        c_bad := c_bad + 1;
      END;
    ELSE c_bad := c_bad + 1;
    END IF;
  END LOOP;
  SELECT count(*), coalesce(sum(avail),0) INTO fsm_free, fsm_avail
    FROM pg_freespace(p_idx::regclass) WHERE avail > 0;
  INSERT INTO proto.meas(fixture,phase,metric,num) VALUES
   (p_fix,p_phase,'census_scanned',   nblocks),
   (p_fix,p_phase,'census_meta',      c_meta),
   (p_fix,p_phase,'census_revmap',    c_revmap),
   (p_fix,p_phase,'census_regular',   c_reg),
   (p_fix,p_phase,'census_unreadable',c_bad),
   (p_fix,p_phase,'brin_items',       items),
   (p_fix,p_phase,'brin_placeholders',placeholders),
   (p_fix,p_phase,'brin_unused_items',unused),
   (p_fix,p_phase,'brin_revmap_entries', revmap_entries),
   (p_fix,p_phase,'fsm_free_pages',   fsm_free),
   (p_fix,p_phase,'fsm_avail_bytes',  fsm_avail),
   (p_fix,p_phase,'size_after_census',pg_relation_size(p_idx::regclass,'main'));
END $fn$;

CREATE FUNCTION proto.census_gin(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blk int := current_setting('block_size')::int;
  n int; nblocks int; fl text[]; hdr record; m record;
  c_entry int := 0; c_data int := 0; c_list int := 0; c_del int := 0;
  c_zero int := 0; c_bad int := 0; fsm_free int;
BEGIN
  nblocks := pg_relation_size(p_idx::regclass,'main') / blk;
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
  INSERT INTO proto.meas(fixture,phase,metric,num) VALUES
   (p_fix,p_phase,'census_scanned',   nblocks),
   (p_fix,p_phase,'census_entry',     c_entry),
   (p_fix,p_phase,'census_data',      c_data),
   (p_fix,p_phase,'census_list',      c_list),
   (p_fix,p_phase,'census_deleted',   c_del),
   (p_fix,p_phase,'census_new',       c_zero),
   (p_fix,p_phase,'census_unreadable',c_bad),
   (p_fix,p_phase,'meta_total_pages', m.n_total_pages),
   (p_fix,p_phase,'meta_entry_pages', m.n_entry_pages),
   (p_fix,p_phase,'meta_data_pages',  m.n_data_pages),
   (p_fix,p_phase,'meta_pending_pages', m.n_pending_pages),
   (p_fix,p_phase,'meta_entries',     m.n_entries),
   (p_fix,p_phase,'fsm_free_pages',   fsm_free),
   (p_fix,p_phase,'size_after_census',pg_relation_size(p_idx::regclass,'main'));
END $fn$;

CREATE FUNCTION proto.census(p_fix text, p_phase text, p_tab text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE am text;
BEGIN
  SELECT a.amname INTO am FROM pg_class c JOIN pg_am a ON a.oid = c.relam
   WHERE c.oid = p_idx::regclass;
  PERFORM proto.note(p_fix,p_phase,'size_before_census',
                     pg_relation_size(p_idx::regclass,'main'));
  CASE am
    WHEN 'hash'   THEN PERFORM proto.census_hash(p_fix,p_phase,p_idx);
    WHEN 'gist'   THEN PERFORM proto.census_gist(p_fix,p_phase,p_idx);
    WHEN 'spgist' THEN PERFORM proto.census_spgist(p_fix,p_phase,p_idx);
    WHEN 'brin'   THEN PERFORM proto.census_brin(p_fix,p_phase,p_idx);
    WHEN 'gin'    THEN PERFORM proto.census_gin(p_fix,p_phase,p_idx);
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
         n_mod_since_analyze, n_ins_since_vacuum, analyze_count, autoanalyze_count,
         vacuum_count, autovacuum_count
    INTO s FROM pg_stat_all_tables WHERE relid = p_tab::regclass;
  INSERT INTO proto.meas(fixture,phase,metric,num) VALUES
    (p_fix,p_phase,'index_size',      pg_relation_size(p_idx::regclass,'main')),
    (p_fix,p_phase,'index_relpages',  ci.relpages),
    (p_fix,p_phase,'index_reltuples', ci.reltuples),
    (p_fix,p_phase,'index_filenode',  ci.relfilenode::bigint),
    (p_fix,p_phase,'table_size',      pg_relation_size(p_tab::regclass,'main')),
    (p_fix,p_phase,'table_relpages',  ct.relpages),
    (p_fix,p_phase,'table_reltuples', ct.reltuples),
    (p_fix,p_phase,'n_tup_ins',       s.n_tup_ins),
    (p_fix,p_phase,'n_tup_upd',       s.n_tup_upd),
    (p_fix,p_phase,'n_tup_hot_upd',   s.n_tup_hot_upd),
    (p_fix,p_phase,'n_tup_del',       s.n_tup_del),
    (p_fix,p_phase,'n_live_tup',      s.n_live_tup),
    (p_fix,p_phase,'n_dead_tup',      s.n_dead_tup),
    (p_fix,p_phase,'n_mod_since_analyze', s.n_mod_since_analyze),
    (p_fix,p_phase,'n_ins_since_vacuum',  s.n_ins_since_vacuum),
    (p_fix,p_phase,'analyze_count',   s.analyze_count),
    (p_fix,p_phase,'vacuum_count',    s.vacuum_count);
END $fn$;
SQL
}

# ----------------------------------------------------------- fixture recipes
# Every statement below is DISPOSABLE fixture DDL and DML.  The build phase of
# each fixture is: create the table, load it, ANALYZE, create the scored index,
# ANALYZE again.  The second ANALYZE is what makes the baseline legal: an index
# reltuples written by the build is the AM's own count, and for GIN and BRIN
# that is not the number the model needs.
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
      # point_ops is the only core GiST opclass carrying GIST_SORTSUPPORT_PROC,
      # so this is the run's sorted build; every other GiST fixture is
      # insert-driven
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
      # three hot keys, so every key owns a posting TREE rather than a posting
      # list: a posting list that fits in one entry-tree tuple has no page to
      # empty, which is why the previous revision of this fixture reached
      # nothing.  The churn then deletes a contiguous id band, so the deleted
      # TIDs are contiguous and whole posting-tree leaves empty.
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
    # the same contiguous band, so the deleted TIDs are contiguous inside each
    # hot key's posting tree and whole posting-tree leaves empty
    n10) printf 'DELETE FROM %s WHERE id > %s;\n' "$t" "$((HOT_ROWS/5))" ;;
    n12) printf "SET gin_pending_list_limit = '1GB';\nINSERT INTO %s SELECT g, ARRAY['a'||g, 'b'||(g%%50000), 'c'||(g%%1000)]\n  FROM generate_series(%s,%s) g;\nRESET gin_pending_list_limit;\n" \
           "$t" "$((GIN_ROWS+1))" "$((GIN_ROWS+A05_INSERTS))" ;;
    *) die "no churn recipe for fixture $f" ;;
  esac
}

# The maintenance step.  The default is the mandatory VACUUM ANALYZE on every
# table the churn touched; two fixtures declare a different one, the two
# auto-analyze stand-ins, and each difference is named on the page.
fx_maint() {
  local f="$1" t i
  t=$(tbl "$f"); i=$(idx "$f")
  case "$f" in
    h00|h07|n08|n09)
      # no churn, so nothing to maintain: the build phase's ANALYZE is what
      # this fixture carries into the decide phase
      : ;;
    h05)
      # auto-analyze stand-in on a non-GIN AM: a plain ANALYZE and nothing
      # else, because all four of these AMs no-op in ANALYZE-only mode
      printf 'ANALYZE VERBOSE %s;\n' "$t" ;;
    n12)
      # auto-analyze stand-in on a GIN index: ANALYZE plus the pending-list
      # flush that only an autovacuum worker's ANALYZE performs
      printf "ANALYZE VERBOSE %s;\nSELECT gin_clean_pending_list('%s'::regclass);\n" "$t" "$i" ;;
    b13)
      # the BRIN summarization stand-in, beside the mandatory maintenance
      printf 'VACUUM (VERBOSE, ANALYZE) %s;\n' "$t" ;;
    *)
      printf 'VACUUM (VERBOSE, ANALYZE) %s;\n' "$t" ;;
  esac
}

# ------------------------------------------------------------ phase helpers
# Every census that will be compared with anything runs inside one transaction
# holding SHARE ROW EXCLUSIVE on the index's table, which is the measurement
# lock both protocols require.
census_locked() {
  local db="$1" f="$2" ph="$3" t i
  t=$(tbl "$f"); i=$(idx "$f")
  qin "$db" > "$OUT/census-$f-$ph.log" 2>&1 <<SQL
BEGIN /* wiki_idxmaint_census */;
SET LOCAL statement_timeout = '1800s';
SET LOCAL lock_timeout = '15s';
LOCK /* wiki_idxmaint_census */ TABLE $t IN SHARE ROW EXCLUSIVE MODE;
SELECT /* wiki_idxmaint_census */ proto.note('$f','$ph','lock_taken',NULL,'SHARE ROW EXCLUSIVE on $t');
-- the interval the measurement lock was held, so invariant I12 can show it
-- never overlapped a maintenance step
SELECT /* wiki_idxmaint_census */ proto.note('$f','$ph','lock_acquired',
         extract(epoch from clock_timestamp()));
SELECT /* wiki_idxmaint_census */ proto.census('$f','$ph','$t','$i');
SELECT /* wiki_idxmaint_census */ proto.record('$f','$ph','$t','$i');
SELECT /* wiki_idxmaint_census */ proto.note('$f','$ph','progress_vacuum',
         (SELECT count(*) FROM pg_stat_progress_vacuum WHERE relid = '$t'::regclass));
SELECT /* wiki_idxmaint_census */ proto.note('$f','$ph','progress_analyze',
         (SELECT count(*) FROM pg_stat_progress_analyze WHERE relid = '$t'::regclass));
SELECT /* wiki_idxmaint_census */ proto.note('$f','$ph','progress_create_index',
         (SELECT count(*) FROM pg_stat_progress_create_index WHERE relid = '$t'::regclass));
SELECT /* wiki_idxmaint_census */ proto.note('$f','$ph','lock_released',
         extract(epoch from clock_timestamp()));
COMMIT /* wiki_idxmaint_census */;
SQL
}

# Records who could have pinned the removal horizon at this instant, and the
# four settable timeouts the session runs under.  "The maintenance must not be
# defeated" requires this reading beside every maintenance step; both protocols
# also state that it is a read rather than an interlock, so the run takes one
# on each side of the statement and reports both.
#   * a backend with a transaction id or an xmin folds into OldestXmin
#   * a prepared transaction keeps its xid running with no live session
#   * a slot's xmin is taken as the older of the two horizons
horizon_probe() {
  local db="$1" f="$2" when="$3"
  qin "$db" > "$OUT/horizon-$f-$when.log" 2>&1 <<SQL
SELECT /* wiki_idxmaint_horizon */ proto.note('$f','$when','horizon_backends',
         (SELECT count(*) FROM pg_stat_activity
           WHERE pid <> pg_backend_pid()
             AND (backend_xid IS NOT NULL OR backend_xmin IS NOT NULL)));
SELECT /* wiki_idxmaint_horizon */ proto.note('$f','$when','horizon_backend_detail', NULL,
         coalesce((SELECT string_agg(format('pid=%s type=%s state=%s xact_start=%s xid=%s xmin=%s',
                                            pid, backend_type, state, xact_start,
                                            backend_xid, backend_xmin), '; ')
                     FROM pg_stat_activity
                    WHERE pid <> pg_backend_pid()
                      AND (backend_xid IS NOT NULL OR backend_xmin IS NOT NULL)), 'none'));
SELECT /* wiki_idxmaint_horizon */ proto.note('$f','$when','horizon_slots',
         (SELECT count(*) FROM pg_replication_slots
           WHERE xmin IS NOT NULL OR catalog_xmin IS NOT NULL));
SELECT /* wiki_idxmaint_horizon */ proto.note('$f','$when','horizon_prepared',
         (SELECT count(*) FROM pg_prepared_xacts));
SELECT /* wiki_idxmaint_horizon */ proto.note('$f','$when','timeouts', NULL,
         (SELECT string_agg(name || '=' || setting, ' ' ORDER BY name)
            FROM pg_settings
           WHERE name IN ('statement_timeout','lock_timeout','transaction_timeout',
                          'idle_in_transaction_session_timeout')));
SQL
}

# Runs a fixture's maintenance step and brackets it with the proofs the rule
# demands.  The four settable timeouts are forced to 0 in the maintenance
# session, which is exactly what an autovacuum launcher and worker do to
# themselves "to avoid letting these settings prevent regular maintenance from
# being executed"; leaving the run's own 1800s/15s in place would leave a
# timeout that could in principle fire inside the step.  $3 is the log
# basename, maint or settle2.
run_maint() {
  local f="$1" db="$2" tag="$3"
  horizon_probe "$db" "$f" "${tag}_before"
  q "$db" "SELECT /* wiki_idxmaint_maint */ proto.note('$f','$tag','started',
             extract(epoch from clock_timestamp()))" > /dev/null
  { printf "SET /* wiki_idxmaint_maint */ statement_timeout = 0;\n"
    printf "SET /* wiki_idxmaint_maint */ lock_timeout = 0;\n"
    printf "SET /* wiki_idxmaint_maint */ transaction_timeout = 0;\n"
    printf "SET /* wiki_idxmaint_maint */ idle_in_transaction_session_timeout = 0;\n"
    printf "SELECT /* wiki_idxmaint_maint */ 'maintenance session timeouts: '\n"
    printf "       || string_agg(name || '=' || setting, ' ' ORDER BY name)\n"
    printf "  FROM pg_settings WHERE name IN ('statement_timeout','lock_timeout',\n"
    printf "       'transaction_timeout','idle_in_transaction_session_timeout');\n"
    fx_maint "$f"
  } | qin "$db" > "$OUT/$tag-$f.log" 2>&1 || die "maintenance of $f failed"
  q "$db" "SELECT /* wiki_idxmaint_maint */ proto.note('$f','$tag','ended',
             extract(epoch from clock_timestamp()))" > /dev/null
  horizon_probe "$db" "$f" "${tag}_after"
}

# Opens a REPEATABLE READ transaction in a second session and holds its
# snapshot until release_snapshot terminates that backend.  In REPEATABLE READ
# the snapshot is fixed by the transaction's first query, so the SELECT below
# is what pins it; the caller must open this BEFORE the churn commits, because
# a snapshot taken afterwards has an xmin past the deleting xid and holds
# nothing back.
SNAP_PID=""
hold_snapshot() {
  local db="$1" secs="$2"
  ( printf "BEGIN /* wiki_idxmaint_snapshot */ ISOLATION LEVEL REPEATABLE READ;\n"
    printf "SELECT /* wiki_idxmaint_snapshot */ 'snapshot holder pid ' || pg_backend_pid();\n"
    printf "SELECT /* wiki_idxmaint_snapshot */ pg_sleep(%s);\n" "$secs"
    printf "COMMIT /* wiki_idxmaint_snapshot */;\n" ) | qin "$db" > "$OUT/snapshot-$3.log" 2>&1 &
  SNAP_PID=$!
  sleep 3
}
# Releases it by terminating the holder rather than waiting out the sleep, so
# the held window is exactly as long as the fixture needs it to be.
release_snapshot() {
  local db="$1" f="$2"
  q "$db" "SELECT /* wiki_idxmaint_snapshot */ proto.note('$f','snapshot','holders_terminated',
             (SELECT count(*) FROM pg_stat_activity
               WHERE query LIKE '%wiki_idxmaint_snapshot%' AND pid <> pg_backend_pid()))" > /dev/null
  q "$db" "SELECT /* wiki_idxmaint_snapshot */ pg_terminate_backend(pid)
             FROM pg_stat_activity
            WHERE query LIKE '%wiki_idxmaint_snapshot%' AND pid <> pg_backend_pid()" > /dev/null
  [ -n "$SNAP_PID" ] && wait "$SNAP_PID" 2>/dev/null
  SNAP_PID=""
}

# ----------------------------------------------------------- stage: fixtures
stage_fixtures() {
  say "fixtures: build phase and baseline capture for $(printf '%s\n' $SCORED | wc -l | tr -d ' ') scored fixtures"
  q postgres "SELECT /* wiki_idxmaint_guard */ count(*) FROM pg_database WHERE datname = '$PDB'" \
    | grep -q '^1$' || die "declarations are not filed: run the declare stage first"
  q postgres "DROP /* wiki_idxmaint_fixtures */ DATABASE IF EXISTS $DB" > /dev/null
  q postgres "CREATE /* wiki_idxmaint_fixtures */ DATABASE $DB" > /dev/null
  proto_ddl | qin "$DB" > "$OUT/proto-ddl.log" 2>&1 || die "proto DDL failed"

  for f in $SCORED; do
    printf '  build %-4s (%s)\n' "$f" "$(fx_am "$f")"
    fx_build "$f" | qin "$DB" > "$OUT/build-$f.log" 2>&1 || die "build of $f failed"
  done
  for f in $SCORED; do
    census_locked "$DB" "$f" baseline
  done
  q "$DB" "SELECT /* wiki_idxmaint_report */ fixture || ' ' ||
             max(num) FILTER (WHERE metric='index_size') || ' bytes, reltuples ' ||
             max(num) FILTER (WHERE metric='index_reltuples')
             FROM proto.meas WHERE phase='baseline' GROUP BY fixture ORDER BY fixture" \
    | tee "$OUT/baseline-sizes.txt"

  say "fixtures: the published capture statement, once, for every index at once"
  qgen "$DB" "$SQLD/capture.sql" > "$OUT/capture-generated.sql"
  printf 'capture statements generated: %s\n' "$(grep -c 'COMMENT ON INDEX' "$OUT/capture-generated.sql")"
  printf 'capture refusals generated:   %s\n' "$(grep -c 'RAISE WARNING' "$OUT/capture-generated.sql")"
  qin "$DB" < "$OUT/capture-generated.sql" > "$OUT/capture-run.log" 2>&1 || die "capture failed"
  date -u +'baselines filed at %Y-%m-%dT%H:%M:%SZ' | tee "$OUT/baseline_at.txt"

  say "fixtures: the published reader, over every index that now carries a baseline"
  qf "$DB" "$SQLD/read.sql" > "$OUT/read-baselines.txt" 2>&1
  q "$DB" "SELECT /* wiki_idxmaint_report */ count(*) FROM pg_description d
             JOIN pg_class c ON c.oid = d.objoid
            WHERE d.classoid = 'pg_class'::regclass AND d.objsubid = 0
              AND d.description LIKE '%@idxmaint:%'" | tee "$OUT/baseline-count.txt"
}

# -------------------------------------------------------------- stage: churn
# writes -> force the statistics flush -> census the unmaintained state ->
# maintenance step -> census the maintained state.  The unmaintained census is
# a size and page reading only: the method is never evaluated on it.
stage_churn() {
  say "churn: recipe writes, then the maintenance step, for every scored fixture"
  for f in $SCORED; do
    local t i
    t=$(tbl "$f"); i=$(idx "$f")
    printf '  churn %-4s (%s)\n' "$f" "$(fx_am "$f")"
    # Declared exceptions X1 and X2 open their snapshot BEFORE the churn, and
    # that ordering is the whole point: a snapshot opened after the DELETE
    # commits has an xmin past the deleting xid, so those tuples are removable
    # and the horizon is not pinned at all.  Opening it first makes them stay
    # HEAPTUPLE_RECENTLY_DEAD, which is the state the rule is about.
    case "$f" in g08|n10) hold_snapshot "$DB" 900 "$f" ;; esac
    { fx_churn "$f"
      printf "SELECT /* wiki_idxmaint_churn */ pg_stat_force_next_flush();\n"
    } | qin "$DB" > "$OUT/churn-$f.log" 2>&1 || die "churn of $f failed"
    census_locked "$DB" "$f" churn_raw

    case "$f" in
      g08|n10)
        # The churn_maintained reading is therefore a held-horizon reading and
        # is never published as a maintained-state one; the settle2 reading,
        # after the snapshot is released and a second VACUUM ANALYZE has run,
        # is the maintained state the method is scored on.
        run_maint "$f" "$DB" maint
        census_locked "$DB" "$f" churn_maintained
        release_snapshot "$DB" "$f"
        run_maint "$f" "$DB" settle2
        census_locked "$DB" "$f" settle2
        ;;
      b13)
        # the BRIN summarization stand-in: an autosummarize index whose work
        # items nothing fulfilled, desummarized in one place and summarized by
        # the SQL function, then handed the mandatory maintenance
        qin "$DB" > "$OUT/standin-$f.log" 2>&1 <<SQL
SELECT /* wiki_idxmaint_standin */ proto.note('$f','standin','size_before_standin',
         pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_idxmaint_standin */ brin_desummarize_range('$i'::regclass, 0);
SELECT /* wiki_idxmaint_standin */ brin_desummarize_range('$i'::regclass, 128);
SELECT /* wiki_idxmaint_standin */ brin_desummarize_range('$i'::regclass, 256);
SELECT /* wiki_idxmaint_standin */ proto.note('$f','standin','size_after_desummarize',
         pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_idxmaint_standin */ brin_summarize_range('$i'::regclass, 0);
SELECT /* wiki_idxmaint_standin */ brin_summarize_new_values('$i'::regclass);
SELECT /* wiki_idxmaint_standin */ proto.note('$f','standin','size_after_summarize',
         pg_relation_size('$i'::regclass,'main'));
SQL
        census_locked "$DB" "$f" standin
        run_maint "$f" "$DB" maint
        census_locked "$DB" "$f" churn_maintained
        ;;
      *)
        run_maint "$f" "$DB" maint
        census_locked "$DB" "$f" churn_maintained
        ;;
    esac
  done
  q "$DB" "SELECT /* wiki_idxmaint_report */ fixture || ' raw=' ||
             max(num) FILTER (WHERE phase='churn_raw' AND metric='index_size') || ' maintained=' ||
             max(num) FILTER (WHERE phase='churn_maintained' AND metric='index_size')
             FROM proto.meas WHERE metric='index_size'
             GROUP BY fixture ORDER BY fixture" | tee "$OUT/maintenance-pair.txt"
}

# --------------------------------------------- stage: simulated analyze census
# Recomputes relation_needs_vacanalyze's analyze verdict per table from the
# effective reloption-or-GUC values, and analyzes the tables it names.
stage_analyze_census() {
  say "analyze census: the launcher's analyze verdict, recomputed per table"
  for t in tc_past tc_exact tc_off; do
    q "$DB" "DROP /* wiki_idxmaint_census */ TABLE IF EXISTS $t" > /dev/null
  done
  qin "$DB" > "$OUT/census-build.log" 2>&1 <<'SQL'
CREATE /* wiki_idxmaint_census */ TABLE tc_past  (id bigint, k bigint);
CREATE /* wiki_idxmaint_census */ TABLE tc_exact (id bigint, k bigint);
CREATE /* wiki_idxmaint_census */ TABLE tc_off   (id bigint, k bigint)
  WITH (autovacuum_enabled = false);
INSERT /* wiki_idxmaint_census */ INTO tc_past  SELECT g, g FROM generate_series(1,10000) g;
INSERT /* wiki_idxmaint_census */ INTO tc_exact SELECT g, g FROM generate_series(1,10000) g;
INSERT /* wiki_idxmaint_census */ INTO tc_off   SELECT g, g FROM generate_series(1,10000) g;
SELECT /* wiki_idxmaint_census */ pg_stat_force_next_flush();
ANALYZE /* wiki_idxmaint_census */ tc_past, tc_exact, tc_off;
SELECT /* wiki_idxmaint_census */ pg_stat_force_next_flush();
SQL
  # at the shipped defaults the threshold is 50 + 0.1 * 10000 = 1050:
  # tc_past crosses it, tc_exact lands exactly on it, tc_off is short-circuited
  qin "$DB" > "$OUT/census-push.log" 2>&1 <<'SQL'
UPDATE /* wiki_idxmaint_census */ tc_past  SET k = k WHERE id <= 2000;
UPDATE /* wiki_idxmaint_census */ tc_exact SET k = k WHERE id <= 1050;
UPDATE /* wiki_idxmaint_census */ tc_off   SET k = k WHERE id <= 2000;
SELECT /* wiki_idxmaint_census */ pg_stat_force_next_flush();
SQL
  q "$DB" "SELECT /* wiki_idxmaint_census */ pg_stat_clear_snapshot()" > /dev/null
  cat > "$SQLD/census.sql" <<'SQL'
SELECT /* wiki_idxmaint_census */
       c.relname
       || ' reltuples=' || greatest(c.reltuples, 0)::bigint
       || ' mod=' || coalesce(s.n_mod_since_analyze, 0)
       || ' thresh=' || round((CASE WHEN o.analyze_threshold >= 0 THEN o.analyze_threshold
                                    ELSE current_setting('autovacuum_analyze_threshold')::numeric END)
                              + (CASE WHEN o.analyze_scale_factor >= 0 THEN o.analyze_scale_factor
                                      ELSE current_setting('autovacuum_analyze_scale_factor')::numeric END)
                                * greatest(c.reltuples, 0)::numeric, 2)
       || ' av_enabled=' || o.av_enabled
       || ' doanalyze=' || (o.av_enabled AND coalesce(s.n_mod_since_analyze, 0) >
              (CASE WHEN o.analyze_threshold >= 0 THEN o.analyze_threshold
                    ELSE current_setting('autovacuum_analyze_threshold')::numeric END)
            + (CASE WHEN o.analyze_scale_factor >= 0 THEN o.analyze_scale_factor
                    ELSE current_setting('autovacuum_analyze_scale_factor')::numeric END)
              * greatest(c.reltuples, 0)::numeric)
  FROM pg_class c
  LEFT JOIN pg_stat_all_tables s ON s.relid = c.oid
  CROSS JOIN LATERAL (
       SELECT coalesce((SELECT (regexp_match(opt, '^autovacuum_analyze_threshold=(.*)$'))[1]::numeric
                          FROM unnest(coalesce(c.reloptions, '{}')) opt
                         WHERE opt LIKE 'autovacuum_analyze_threshold=%'), -1)     AS analyze_threshold,
              coalesce((SELECT (regexp_match(opt, '^autovacuum_analyze_scale_factor=(.*)$'))[1]::numeric
                          FROM unnest(coalesce(c.reloptions, '{}')) opt
                         WHERE opt LIKE 'autovacuum_analyze_scale_factor=%'), -1)  AS analyze_scale_factor,
              NOT coalesce((SELECT (regexp_match(opt, '^autovacuum_enabled=(.*)$'))[1] = 'false'
                          FROM unnest(coalesce(c.reloptions, '{}')) opt
                         WHERE opt LIKE 'autovacuum_enabled=%'), false)            AS av_enabled
  ) o
 WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
 ORDER BY c.relname;
SQL
  qat "$DB" "$SQLD/census.sql" > "$OUT/census-verdicts.txt" 2>&1
  # analyze exactly the tables the census named
  qat "$DB" /dev/stdin > "$OUT/census-analyzed.txt" 2>&1 <<'SQL'
SELECT /* wiki_idxmaint_census */ 'ANALYZE ' || quote_ident(c.relname) || ';'
  FROM pg_class c
  LEFT JOIN pg_stat_all_tables s ON s.relid = c.oid
  CROSS JOIN LATERAL (
       SELECT coalesce((SELECT (regexp_match(opt, '^autovacuum_analyze_threshold=(.*)$'))[1]::numeric
                          FROM unnest(coalesce(c.reloptions, '{}')) opt
                         WHERE opt LIKE 'autovacuum_analyze_threshold=%'), -1)     AS analyze_threshold,
              coalesce((SELECT (regexp_match(opt, '^autovacuum_analyze_scale_factor=(.*)$'))[1]::numeric
                          FROM unnest(coalesce(c.reloptions, '{}')) opt
                         WHERE opt LIKE 'autovacuum_analyze_scale_factor=%'), -1)  AS analyze_scale_factor,
              NOT coalesce((SELECT (regexp_match(opt, '^autovacuum_enabled=(.*)$'))[1] = 'false'
                          FROM unnest(coalesce(c.reloptions, '{}')) opt
                         WHERE opt LIKE 'autovacuum_enabled=%'), false)            AS av_enabled
  ) o
 WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
   AND o.av_enabled
   AND coalesce(s.n_mod_since_analyze, 0) >
         (CASE WHEN o.analyze_threshold >= 0 THEN o.analyze_threshold
               ELSE current_setting('autovacuum_analyze_threshold')::numeric END)
       + (CASE WHEN o.analyze_scale_factor >= 0 THEN o.analyze_scale_factor
               ELSE current_setting('autovacuum_analyze_scale_factor')::numeric END)
         * greatest(c.reltuples, 0)::numeric
 ORDER BY c.relname;
SQL
  printf 'census named %s table(s) for ANALYZE\n' "$(grep -c 'ANALYZE' "$OUT/census-analyzed.txt")"
  grep 'ANALYZE' "$OUT/census-analyzed.txt" | qin "$DB" > "$OUT/census-run.log" 2>&1
  q "$DB" "SELECT /* wiki_idxmaint_census */ pg_stat_clear_snapshot()" > /dev/null
  grep -E 'tc_past|tc_exact|tc_off' "$OUT/census-verdicts.txt"
}

# ------------------------------------------------- stage: the cross-checks
# The censuses themselves were taken under the measurement lock in the churn
# stage, because the maintenance pair needs one on each side of it.  This stage
# adds the readings that do not come from a census: VACUUM's own index line,
# and the instrument refusals the protocol's matrix predicts.
stage_crosscheck() {
  say "cross-checks: VACUUM's index line, the instrument refusals, the summary"
  for f in $SCORED; do
    local i line fields
    i=$(idx "$f")
    line=$(grep -E "index \"$i\": pages: " "$OUT/maint-$f.log" 2>/dev/null | tail -1)
    if [ -n "$line" ]; then
      fields=$(printf '%s' "$line" | sed -E \
        's/.*pages: ([0-9]+) in total, ([0-9]+) newly deleted, ([0-9]+) currently deleted, ([0-9]+) reusable.*/\1 \2 \3 \4/')
      set -- $fields
      q "$DB" "SELECT /* wiki_idxmaint_crosscheck */
                 proto.note('$f','verbose','num_pages',$1),
                 proto.note('$f','verbose','pages_newly_deleted',$2),
                 proto.note('$f','verbose','pages_deleted',$3),
                 proto.note('$f','verbose','pages_free',$4),
                 proto.note('$f','verbose','index_line',NULL,'present')" > /dev/null
    else
      q "$DB" "SELECT /* wiki_idxmaint_crosscheck */
                 proto.note('$f','verbose','index_line',NULL,'absent')" > /dev/null
    fi
  done
  q "$DB" "SELECT /* wiki_idxmaint_report */ fixture || ' ' ||
             coalesce(max(txt) FILTER (WHERE metric='index_line'), '?') ||
             coalesce(' total=' || max(num) FILTER (WHERE metric='num_pages'), '') ||
             coalesce(' newly=' || max(num) FILTER (WHERE metric='pages_newly_deleted'), '') ||
             coalesce(' del='   || max(num) FILTER (WHERE metric='pages_deleted'), '') ||
             coalesce(' free='  || max(num) FILTER (WHERE metric='pages_free'), '')
             FROM proto.meas WHERE phase='verbose' GROUP BY fixture ORDER BY fixture" \
    | tee "$OUT/verbose-lines.txt"

  say "cross-checks: the maintenance was not defeated"
  # One pass over every maintenance log, for the four proofs the rule demands:
  # the statement completed and was not skipped, the `dead but not yet
  # removable` count, the timeouts it ran under, and (recorded in the churn
  # stage) the horizon holders on each side of it.  The count is read from the
  # first VERBOSE block, which is the fixture's own table; a TOAST relation
  # gets its own block after it.
  for f in $SCORED; do
    for tag in maint settle2; do
      local lg dead nblk skips cancels tags touts
      lg="$OUT/$tag-$f.log"
      [ -f "$lg" ] || continue
      dead=$(grep -o '[0-9]\+ are dead but not yet removable' "$lg" | head -1 | grep -o '^[0-9]\+')
      nblk=$(grep -c 'are dead but not yet removable' "$lg")
      skips=$(grep -c 'skipping vacuum of\|skipping analyze of' "$lg")
      cancels=$(grep -c 'canceling statement due to\|^ERROR' "$lg")
      tags=$(grep -Ec '^(VACUUM|ANALYZE)$' "$lg")
      touts=$(grep -o 'maintenance session timeouts: .*' "$lg" | head -1 \
                | sed 's/^maintenance session timeouts: //')
      q "$DB" "SELECT /* wiki_idxmaint_maintproof */
                 proto.note('$f','$tag','dead_not_removable',${dead:-NULL}),
                 proto.note('$f','$tag','verbose_blocks',${nblk:-0}),
                 proto.note('$f','$tag','skip_lines',${skips:-0}),
                 proto.note('$f','$tag','cancel_lines',${cancels:-0}),
                 proto.note('$f','$tag','command_tags',${tags:-0}),
                 proto.note('$f','$tag','session_timeouts',NULL,'${touts:-unrecorded}')" > /dev/null
    done
  done
  q "$DB" "SELECT /* wiki_idxmaint_report */ format('%-4s %-7s dead_not_removable=%-8s blocks=%-3s skipped=%-2s cancelled=%-2s tags=%-2s [%s]',
             fixture, phase,
             coalesce((max(num) FILTER (WHERE metric='dead_not_removable'))::text,'n/a'),
             max(num) FILTER (WHERE metric='verbose_blocks'),
             max(num) FILTER (WHERE metric='skip_lines'),
             max(num) FILTER (WHERE metric='cancel_lines'),
             max(num) FILTER (WHERE metric='command_tags'),
             max(txt) FILTER (WHERE metric='session_timeouts'))
             FROM proto.meas WHERE phase IN ('maint','settle2')
             GROUP BY fixture, phase ORDER BY fixture, phase" \
    | tee "$OUT/maintenance-proof.txt"
  q "$DB" "SELECT /* wiki_idxmaint_report */ format('%-4s %-14s backends=%s slots=%s prepared=%s | %s',
             fixture, phase,
             max(num) FILTER (WHERE metric='horizon_backends'),
             max(num) FILTER (WHERE metric='horizon_slots'),
             max(num) FILTER (WHERE metric='horizon_prepared'),
             max(txt) FILTER (WHERE metric='horizon_backend_detail'))
             FROM proto.meas
            WHERE phase IN ('maint_before','maint_after','settle2_before','settle2_after')
             GROUP BY fixture, phase ORDER BY fixture, phase" \
    | tee "$OUT/horizon-holders.txt"

  say "cross-checks: which instrument accepts which access method"
  : > "$OUT/instrument-matrix.txt"
  for f in h01 g06 s08 b10 n03; do
    local ix am
    ix=$(idx "$f"); am=$(fx_am "$f")
    for fn in "pgstattuple('$ix')" "pgstatindex('$ix')" "pgstathashindex('$ix')" \
              "pgstatginindex('$ix')"; do
      printf '%-8s %-34s %s\n' "$am" "${fn%%(*}" \
        "$(q "$DB" "SELECT /* wiki_idxmaint_instrument */ 'accepted' FROM $fn" 2>&1 \
            | tr '\n' ' ' | sed -e 's/^ *//' -e 's/ *$//' | cut -c1-96)" \
        >> "$OUT/instrument-matrix.txt"
    done
  done
  cat "$OUT/instrument-matrix.txt"

  q "$DB" "SELECT /* wiki_idxmaint_report */ fixture || ' [' || phase || '] scanned=' ||
             max(num) FILTER (WHERE metric='census_scanned') ||
             coalesce(' bracket=' || (max(num) FILTER (WHERE metric='size_after_census')
                                   - max(num) FILTER (WHERE metric='size_before_census')), '') ||
             coalesce(' fsm='     || max(num) FILTER (WHERE metric='fsm_free_pages'), '') ||
             coalesce(' del='     || max(num) FILTER (WHERE metric='census_deleted'), '') ||
             coalesce(' new='     || max(num) FILTER (WHERE metric='census_new'), '')
             FROM proto.meas
            WHERE phase IN ('baseline','churn_raw','standin','churn_maintained','settle2')
            GROUP BY fixture, phase
           HAVING count(*) FILTER (WHERE metric='census_scanned') > 0
            ORDER BY fixture, phase" | tee "$OUT/census-summary.txt"
}

# -------------------------------------------------------------- stage: decide
# One pass of the published statement, verbatim, inside one transaction holding
# SHARE ROW EXCLUSIVE on every fixture table.  Nothing else runs in this phase.
stage_decide() {
  say "decide: the published statement under the measurement lock"
  local locks=""
  for f in $SCORED; do locks="$locks$(tbl "$f"), "; done
  locks="${locks}tc_past, tc_exact, tc_off"
  { printf "SET /* wiki_idxmaint_decide */ lock_timeout = '30s';\n"
    printf "BEGIN /* wiki_idxmaint_decide */;\n"
    printf "LOCK /* wiki_idxmaint_decide */ TABLE %s IN SHARE ROW EXCLUSIVE MODE;\n" "$locks"
    cat "$SQLD/evaluate.sql"
    printf "COMMIT /* wiki_idxmaint_decide */;\n"
  } | "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$DB" \
      > "$OUT/decide.txt" 2>&1 || die "decide pass failed"
  # the same text again, stored per index for scoring
  { printf "SET /* wiki_idxmaint_decide */ lock_timeout = '30s';\n"
    printf "BEGIN /* wiki_idxmaint_decide */;\n"
    printf "LOCK /* wiki_idxmaint_decide */ TABLE %s IN SHARE ROW EXCLUSIVE MODE;\n" "$locks"
    printf "DROP TABLE IF EXISTS proto.decided;\n"
    printf "CREATE /* wiki_idxmaint_decide */ TABLE proto.decided AS\n"
    sed -e '1,3d' "$SQLD/evaluate.sql"
    printf "COMMIT /* wiki_idxmaint_decide */;\n"
  } | "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$DB" \
      > "$OUT/decide-store.log" 2>&1 || die "decide store failed"
  printf 'rows the published statement returned: %s\n' \
    "$(q "$DB" "SELECT /* wiki_idxmaint_report */ count(*) FROM proto.decided")"
  cat "$OUT/decide.txt"
}

# -------------------------------------------------------------- stage: oracle
stage_oracle() {
  say "oracle: measured REINDEX INDEX at maintenance_work_mem = $MWM"
  for f in $SCORED; do
    local t i
    t=$(tbl "$f"); i=$(idx "$f")
    printf '  reindex %-4s\n' "$f"
    qin "$DB" > "$OUT/oracle-$f.log" 2>&1 <<SQL
SET /* wiki_idxmaint_oracle */ maintenance_work_mem = '$MWM';
SELECT /* wiki_idxmaint_oracle */ proto.note('$f','oracle','size_before',
         pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_idxmaint_oracle */ proto.note('$f','oracle','heap_relpages',
         (SELECT relpages FROM pg_class WHERE oid = '$t'::regclass));
SELECT /* wiki_idxmaint_oracle */ proto.note('$f','oracle','heap_reltuples',
         (SELECT reltuples::numeric FROM pg_class WHERE oid = '$t'::regclass));
REINDEX /* wiki_idxmaint_oracle */ INDEX $i;
SELECT /* wiki_idxmaint_oracle */ proto.note('$f','oracle','size_after',
         pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_idxmaint_oracle */ proto.note('$f','oracle','mwm',NULL,
         current_setting('maintenance_work_mem'));
SQL
  done
  q "$DB" "SELECT /* wiki_idxmaint_report */ fixture || ' ' ||
             max(num) FILTER (WHERE metric='size_before') || ' -> ' ||
             max(num) FILTER (WHERE metric='size_after')  || ' = ' ||
             CASE WHEN max(num) FILTER (WHERE metric='size_before') > 0
                  THEN round(100.0 * (1 - max(num) FILTER (WHERE metric='size_after')
                                        / max(num) FILTER (WHERE metric='size_before')), 2)
                  ELSE 0 END || '%'
             FROM proto.meas WHERE phase='oracle' AND metric IN ('size_before','size_after')
             GROUP BY fixture ORDER BY fixture" | tee "$OUT/oracle-summary.txt"
}

# --------------------------------------------------------------- stage: score
# Carries the filed declarations into the fixture database, with their filing
# timestamps, so the scoring provably uses the declaration and not a threshold
# invented after the results.
stage_score() {
  say "score: the filed declarations against the oracle"
  qin "$DB" > "$OUT/score-ddl.log" 2>&1 <<'SQL'
DROP TABLE IF EXISTS proto.declared_kind, proto.declared_decision,
                     proto.declared_invariant, proto.declared_coverage,
                     proto.declared_exception;
CREATE TABLE proto.declared_kind      (column_name text, declared_kind text, claim text, filed_at timestamptz);
CREATE TABLE proto.declared_decision  (knob text, value text, meaning text, filed_at timestamptz);
CREATE TABLE proto.declared_invariant (id text, claim text, filed_at timestamptz);
CREATE TABLE proto.declared_coverage  (protocol text, behavior text, fixture text, filed_at timestamptz);
CREATE TABLE proto.declared_exception (id text, fixture text, state text, reading_rule text, filed_at timestamptz);
SQL
  q "$PDB" "SELECT /* wiki_idxmaint_score */ format('INSERT INTO proto.declared_kind VALUES (%L,%L,%L,%L);',
              column_name, declared_kind, claim, filed_at) FROM declared_kind" \
    | qin "$DB" > "$OUT/score-copy-kind.log" 2>&1
  q "$PDB" "SELECT /* wiki_idxmaint_score */ format('INSERT INTO proto.declared_decision VALUES (%L,%L,%L,%L);',
              knob, value, meaning, filed_at) FROM declared_decision" \
    | qin "$DB" > "$OUT/score-copy-decision.log" 2>&1
  q "$PDB" "SELECT /* wiki_idxmaint_score */ format('INSERT INTO proto.declared_invariant VALUES (%L,%L,%L);',
              id, claim, filed_at) FROM declared_invariant" \
    | qin "$DB" > "$OUT/score-copy-invariant.log" 2>&1
  q "$PDB" "SELECT /* wiki_idxmaint_score */ format('INSERT INTO proto.declared_coverage VALUES (%L,%L,%L,%L);',
              protocol, behavior, fixture, filed_at) FROM declared_coverage" \
    | qin "$DB" > "$OUT/score-copy-coverage.log" 2>&1
  q "$PDB" "SELECT /* wiki_idxmaint_score */ format('INSERT INTO proto.declared_exception VALUES (%L,%L,%L,%L,%L);',
              id, fixture, state, reading_rule, filed_at) FROM declared_exception" \
    | qin "$DB" > "$OUT/score-copy-exception.log" 2>&1
  q "$DB" "SELECT /* wiki_idxmaint_score */ 'declared_kind rows carried: ' || count(*) ||
             ', earliest filed_at ' || min(filed_at)::text FROM proto.declared_kind" \
    | tee "$OUT/score-declarations.txt"
  q "$DB" "SELECT /* wiki_idxmaint_score */ 'first baseline payload at ' ||
             min((substring(d.description from '@idxmaint:(.*)$')::jsonb ->> 'ts'))
             FROM pg_description d WHERE d.description LIKE '%@idxmaint:%'" \
    | tee -a "$OUT/score-declarations.txt"

  qin "$DB" > "$OUT/score-build.log" 2>&1 <<'SQL'
DROP TABLE IF EXISTS proto.score;
CREATE /* wiki_idxmaint_score */ TABLE proto.score AS
WITH sz AS (
  SELECT fixture,
         max(num) FILTER (WHERE phase='baseline'         AND metric='index_size') AS base_size,
         max(num) FILTER (WHERE phase='churn_raw'         AND metric='index_size') AS raw_size,
         -- On a fixture that declares a held snapshot (X1, X2) the
         -- churn_maintained census is a held-horizon reading, so the maintained
         -- state is the settle2 census taken after the snapshot was released
         -- and a second VACUUM ANALYZE had run.  Every other fixture has no
         -- settle2 census and falls back to churn_maintained.
         coalesce(max(num) FILTER (WHERE phase='settle2' AND metric='index_size'),
                  max(num) FILTER (WHERE phase='churn_maintained' AND metric='index_size')) AS maint_size,
         max(num) FILTER (WHERE phase='churn_maintained'  AND metric='index_size') AS held_size,
         max(num) FILTER (WHERE phase='settle2'           AND metric='index_size') AS settle2_size,
         max(num) FILTER (WHERE phase='oracle' AND metric='size_before')           AS oracle_before,
         max(num) FILTER (WHERE phase='oracle' AND metric='size_after')            AS oracle_after,
         max(num) FILTER (WHERE phase='oracle' AND metric='heap_relpages')         AS heap_relpages,
         max(num) FILTER (WHERE phase='oracle' AND metric='heap_reltuples')        AS heap_reltuples
    FROM proto.meas GROUP BY fixture
),
tr AS (
  SELECT sz.*,
         CASE WHEN oracle_before > 0
              THEN round(100.0 * (1 - oracle_after / oracle_before), 2) ELSE 0 END AS truth_pct,
         (oracle_before - oracle_after) AS returned_bytes
    FROM sz
),
dec AS (
  SELECT substring(index_name::text from '^f_(.*)_i$') AS fixture, d.*
    FROM proto.decided d
),
just AS (
  SELECT replace(knob, 'oracle justification ', '') AS amname,
         (regexp_match(value, 'truth_pct >= ([0-9.]+)'))[1]::numeric AS min_truth
    FROM proto.declared_decision WHERE knob LIKE 'oracle justification %'
),
kind AS (
  SELECT declared_kind FROM proto.declared_kind WHERE column_name = 'est_reclaim_pct'
)
SELECT tr.fixture,
       dec.amname,
       tr.base_size, tr.raw_size, tr.maint_size, tr.held_size, tr.settle2_size,
       tr.oracle_before, tr.oracle_after, tr.returned_bytes, tr.truth_pct,
       tr.heap_relpages, tr.heap_reltuples,
       dec.size_inflation, dec.est_reclaim_pct, dec.churn_ratio, dec.dead_ratio,
       dec.pf_shift, dec.recommendation, dec.baseline_state, dec.churn_state,
       (SELECT declared_kind FROM kind)                                AS est_declared_kind,
       CASE WHEN dec.est_reclaim_pct IS NULL THEN 'n/a'
            WHEN dec.est_reclaim_pct >= tr.truth_pct THEN 'HELD'
            ELSE 'VIOLATED' END                                       AS est_bound_verdict,
       round(dec.est_reclaim_pct - tr.truth_pct, 2)                    AS est_error_points,
       j.min_truth,
       (dec.recommendation IN ('strong REINDEX candidate','REINDEX candidate')) AS flagged,
       CASE
         WHEN dec.recommendation IN ('strong REINDEX candidate','REINDEX candidate')
              AND tr.truth_pct >= j.min_truth                         THEN 'PASS'
         WHEN dec.recommendation IN ('strong REINDEX candidate','REINDEX candidate')
                                                                      THEN 'FALSE POSITIVE'
         WHEN tr.truth_pct >= j.min_truth                             THEN 'FALSE NEGATIVE'
         ELSE 'PASS' END                                              AS decision_score
  FROM tr
  JOIN dec  ON dec.fixture = tr.fixture
  LEFT JOIN just j ON j.amname = dec.amname
 ORDER BY tr.fixture;
SQL
  q "$DB" "SELECT /* wiki_idxmaint_report */ format(
             '%-4s %-6s %10s %10s %10s %7s %8s %8s %-9s %-14s %s',
             fixture, amname, base_size, maint_size, oracle_after,
             coalesce(size_inflation::text,'-'), coalesce(est_reclaim_pct::text,'-'),
             truth_pct, est_bound_verdict, decision_score, recommendation)
             FROM proto.score ORDER BY fixture" | tee "$OUT/score-table.txt"

  { printf '\n-- bound: est_reclaim_pct, declared %s\n' \
      "$(q "$DB" "SELECT declared_kind FROM proto.declared_kind WHERE column_name='est_reclaim_pct'")"
    q "$DB" "SELECT /* wiki_idxmaint_report */ est_bound_verdict || ': ' || count(*)
               FROM proto.score GROUP BY est_bound_verdict ORDER BY est_bound_verdict"
    printf -- '-- every violation, worst first (points below truth_pct)\n'
    q "$DB" "SELECT /* wiki_idxmaint_report */ fixture || ' ' || amname || ' est=' || est_reclaim_pct
               || ' truth=' || truth_pct || ' error=' || est_error_points
               || ' [' || recommendation || ']'
               FROM proto.score WHERE est_bound_verdict = 'VIOLATED'
               ORDER BY est_error_points"
    printf -- '-- the five largest over-estimates\n'
    q "$DB" "SELECT /* wiki_idxmaint_report */ fixture || ' ' || amname || ' est=' || est_reclaim_pct
               || ' truth=' || truth_pct || ' error=+' || est_error_points
               FROM proto.score WHERE est_error_points > 0 ORDER BY est_error_points DESC LIMIT 5"
    printf -- '-- decision\n'
    q "$DB" "SELECT /* wiki_idxmaint_report */ decision_score || ': ' || count(*)
               FROM proto.score GROUP BY decision_score ORDER BY decision_score"
    q "$DB" "SELECT /* wiki_idxmaint_report */ 'flagged ' || count(*) FILTER (WHERE flagged)
               || ' of ' || count(*) || ' scored fixtures' FROM proto.score"
    q "$DB" "SELECT /* wiki_idxmaint_report */ 'false negatives: ' ||
               coalesce(string_agg(fixture || ' (truth ' || truth_pct || '%, threshold ' ||
                                   min_truth || '%)', ', '), 'none')
               FROM proto.score WHERE decision_score = 'FALSE NEGATIVE'"
    q "$DB" "SELECT /* wiki_idxmaint_report */ 'false positives: ' ||
               coalesce(string_agg(fixture || ' (truth ' || truth_pct || '%)', ', '), 'none')
               FROM proto.score WHERE decision_score = 'FALSE POSITIVE'"
    printf -- '-- recommendations\n'
    q "$DB" "SELECT /* wiki_idxmaint_report */ recommendation || ': ' || count(*)
               FROM proto.score GROUP BY recommendation ORDER BY count(*) DESC, recommendation"
    printf -- '-- accuracy of est_reclaim_pct against truth_pct\n'
    q "$DB" "SELECT /* wiki_idxmaint_report */
               'within 1 point: ' || count(*) FILTER (WHERE abs(est_error_points) <= 1) ||
               ', within 5: '     || count(*) FILTER (WHERE abs(est_error_points) <= 5) ||
               ', worst over: '   || max(est_error_points) ||
               ', worst under: '  || min(est_error_points)
               FROM proto.score WHERE est_reclaim_pct IS NOT NULL"
  } | tee "$OUT/score-summary.txt"

  say "score: the thirteen invariants"
  qat "$DB" /dev/stdin > "$OUT/invariants.txt" 2>&1 <<'SQL'
WITH c AS (
  SELECT fixture, phase,
         max(num) FILTER (WHERE metric='census_scanned')     AS scanned,
         max(num) FILTER (WHERE metric='size_before_census') AS sz_before,
         max(num) FILTER (WHERE metric='size_after_census')  AS sz_after,
         max(num) FILTER (WHERE metric='census_meta')        AS c_meta,
         max(num) FILTER (WHERE metric='census_bucket')      AS c_bucket,
         max(num) FILTER (WHERE metric='census_overflow')    AS c_ovfl,
         max(num) FILTER (WHERE metric='census_bitmap')      AS c_bitmap,
         max(num) FILTER (WHERE metric='census_unused')      AS c_unused,
         max(num) FILTER (WHERE metric='census_unreadable')  AS c_bad,
         max(num) FILTER (WHERE metric='census_deleted')     AS c_del,
         max(num) FILTER (WHERE metric='census_new')         AS c_new,
         max(num) FILTER (WHERE metric='census_entry')       AS c_entry,
         max(num) FILTER (WHERE metric='census_data')        AS c_data,
         max(num) FILTER (WHERE metric='census_list')        AS c_list,
         max(num) FILTER (WHERE metric='fsm_free_pages')     AS fsm,
         max(num) FILTER (WHERE metric='brin_items')         AS b_items,
         max(num) FILTER (WHERE metric='brin_revmap_entries')AS b_revmap,
         max(num) FILTER (WHERE metric='meta_total_pages')   AS m_total,
         max(num) FILTER (WHERE metric='meta_entry_pages')   AS m_entry,
         max(num) FILTER (WHERE metric='meta_data_pages')    AS m_data,
         max(num) FILTER (WHERE metric='hs_bucket_pages')    AS hs_bucket,
         max(num) FILTER (WHERE metric='hs_overflow_pages')  AS hs_ovfl,
         max(num) FILTER (WHERE metric='hs_bitmap_pages')    AS hs_bitmap,
         max(num) FILTER (WHERE metric='hs_unused_pages')    AS hs_unused,
         max(num) FILTER (WHERE metric='bitmap_disagree')    AS bm_dis
    FROM proto.meas
   WHERE phase IN ('baseline','churn_raw','standin','churn_maintained','settle2')
   GROUP BY fixture, phase
  HAVING count(*) FILTER (WHERE metric='census_scanned') > 0
),
am AS (SELECT fixture, amname FROM proto.score),
blk AS (SELECT current_setting('block_size')::numeric AS b)
SELECT 'I1 cur_size >= base_size: ' ||
       (SELECT count(*) FILTER (WHERE maint_size >= base_size) || ' of ' || count(*) ||
               ' (violations: ' || coalesce(string_agg(fixture, ',') FILTER (WHERE maint_size < base_size), 'none') || ')'
          FROM proto.score)
UNION ALL
SELECT 'I2 size bracket: ' ||
       (SELECT count(*) FILTER (WHERE sz_before = sz_after AND sz_after = scanned * blk.b)
               || ' of ' || count(*) || ' censuses'
          FROM c CROSS JOIN blk)
UNION ALL
SELECT 'I3 hash page classes: ' ||
       (SELECT count(*) FILTER (WHERE c_meta + c_bucket + c_ovfl + c_bitmap + c_unused + c_bad = scanned
                                  AND hs_bucket + hs_ovfl + hs_bitmap + hs_unused + 1 = scanned)
               || ' of ' || count(*) || ' hash censuses'
          FROM c JOIN am USING (fixture) WHERE am.amname = 'hash')
UNION ALL
SELECT 'I4 hash bitmap agreement: ' ||
       (SELECT count(*) FILTER (WHERE bm_dis = 0) || ' of ' || count(*) || ' hash censuses'
          FROM c JOIN am USING (fixture) WHERE am.amname = 'hash')
UNION ALL
SELECT 'I5 GiST FSM <= deleted+new: ' ||
       (SELECT count(*) FILTER (WHERE fsm <= c_del + c_new) || ' of ' || count(*) || ' GiST censuses'
          FROM c JOIN am USING (fixture) WHERE am.amname = 'gist')
       || '; SP-GiST: n/a, no decoder'
UNION ALL
SELECT 'I6 BRIN revmap = items: ' ||
       (SELECT count(*) FILTER (WHERE b_revmap = b_items) || ' of ' || count(*) || ' BRIN censuses'
          FROM c JOIN am USING (fixture) WHERE am.amname = 'brin')
UNION ALL
SELECT 'I7 BRIN maintained >= raw: ' ||
       (SELECT count(*) FILTER (WHERE maint_size >= raw_size) || ' of ' || count(*) || ' BRIN fixtures'
          FROM proto.score WHERE amname = 'brin')
UNION ALL
SELECT 'I8 GIN metapage identity: ' ||
       (SELECT count(*) FILTER (WHERE m_entry = c_entry
                                  AND m_data = c_data + greatest(c_del - fsm, 0))
               || ' of ' || count(*) || ' GIN censuses; total-page identity '
               || count(*) FILTER (WHERE m_total = scanned) || ' of ' || count(*)
          FROM c JOIN am USING (fixture) WHERE am.amname = 'gin')
UNION ALL
SELECT 'I9 VACUUM VERBOSE index line: ' ||
       (SELECT count(*) FILTER (WHERE txt = 'present') || ' present, ' ||
               count(*) FILTER (WHERE txt = 'absent') || ' absent (' ||
               coalesce(string_agg(fixture, ',') FILTER (WHERE txt = 'absent'), 'none') || ')'
          FROM proto.meas WHERE phase='verbose' AND metric='index_line')
UNION ALL
SELECT 'I10 maintenance not defeated: ' ||
       (WITH dnr AS (
          SELECT fixture, phase, max(num) AS dead
            FROM proto.meas WHERE metric='dead_not_removable' AND num IS NOT NULL
           GROUP BY fixture, phase),
        exc AS (SELECT fixture FROM proto.declared_exception WHERE id IN ('X1','X2'))
        SELECT count(*) FILTER (WHERE dead = 0 OR (phase='maint' AND fixture IN (SELECT fixture FROM exc)))
               || ' of ' || count(*) || ' VACUUMs clean or declared'
               || ' (nonzero: ' || coalesce(string_agg(fixture || '/' || phase || '=' || dead, ', ')
                                              FILTER (WHERE dead <> 0), 'none') || ')'
          FROM dnr)
UNION ALL
SELECT 'I11 neither skipped nor cut short: ' ||
       (SELECT count(DISTINCT fixture || phase) FILTER (WHERE metric='skip_lines' AND num = 0)
               || ' of ' || count(DISTINCT fixture || phase) FILTER (WHERE metric='skip_lines')
               || ' maintenance logs with no skip line; cancellations '
               || coalesce(sum(num) FILTER (WHERE metric='cancel_lines'), 0)
               || '; distinct timeout sets ' ||
               (SELECT coalesce(string_agg(DISTINCT txt, ' | '), 'none')
                  FROM proto.meas WHERE metric='session_timeouts')
          FROM proto.meas WHERE phase IN ('maint','settle2'))
UNION ALL
SELECT 'I12 lock never held across a maintenance step: ' ||
       (WITH lk AS (
          SELECT fixture, phase,
                 max(num) FILTER (WHERE metric='lock_acquired') AS t0,
                 max(num) FILTER (WHERE metric='lock_released') AS t1
            FROM proto.meas WHERE metric IN ('lock_acquired','lock_released')
           GROUP BY fixture, phase),
        mt AS (
          SELECT fixture, phase,
                 max(num) FILTER (WHERE metric='started') AS m0,
                 max(num) FILTER (WHERE metric='ended')   AS m1
            FROM proto.meas WHERE metric IN ('started','ended')
           GROUP BY fixture, phase)
        SELECT (SELECT count(*) FROM lk) || ' census lock intervals against '
               || (SELECT count(*) FROM mt) || ' maintenance intervals, overlaps '
               || (SELECT count(*) FROM lk JOIN mt ON lk.t0 < mt.m1 AND mt.m0 < lk.t1))
UNION ALL
SELECT 'I13 no undeclared horizon holder: ' ||
       (SELECT count(*) FILTER (WHERE slots = 0 AND prepared = 0 AND backends = 0)
               || ' of ' || count(*) || ' readings entirely clean; readings with a backend holding '
               || count(*) FILTER (WHERE backends > 0) || ' ('
               || coalesce(string_agg(fixture || '/' || phase, ', ') FILTER (WHERE backends > 0), 'none')
               || '); slots ' || coalesce(sum(slots), 0) || ', prepared ' || coalesce(sum(prepared), 0)
          FROM (SELECT fixture, phase,
                       max(num) FILTER (WHERE metric='horizon_backends') AS backends,
                       max(num) FILTER (WHERE metric='horizon_slots')    AS slots,
                       max(num) FILTER (WHERE metric='horizon_prepared') AS prepared
                  FROM proto.meas
                 WHERE phase IN ('maint_before','maint_after','settle2_before','settle2_after')
                 GROUP BY fixture, phase) h);
SQL
  cat "$OUT/invariants.txt"

  say "score: I6 and I8 detail, per fixture and phase"
  qat "$DB" /dev/stdin > "$OUT/i6-i8-detail.txt" 2>&1 <<'SQL'
WITH c AS (
  SELECT fixture, phase,
         max(num) FILTER (WHERE metric='census_scanned')      AS scanned,
         max(num) FILTER (WHERE metric='brin_items')          AS b_items,
         max(num) FILTER (WHERE metric='brin_unused_items')   AS b_unused,
         max(num) FILTER (WHERE metric='brin_placeholders')   AS b_ph,
         max(num) FILTER (WHERE metric='brin_revmap_entries') AS b_revmap,
         max(num) FILTER (WHERE metric='census_entry')        AS c_entry,
         max(num) FILTER (WHERE metric='census_data')         AS c_data,
         max(num) FILTER (WHERE metric='census_list')         AS c_list,
         max(num) FILTER (WHERE metric='census_deleted')      AS c_del,
         max(num) FILTER (WHERE metric='census_new')          AS c_new,
         max(num) FILTER (WHERE metric='fsm_free_pages')      AS fsm,
         max(num) FILTER (WHERE metric='meta_total_pages')    AS m_total,
         max(num) FILTER (WHERE metric='meta_entry_pages')    AS m_entry,
         max(num) FILTER (WHERE metric='meta_data_pages')     AS m_data,
         max(num) FILTER (WHERE metric='meta_pending_pages')  AS m_pending
    FROM proto.meas
   WHERE phase IN ('baseline','churn_raw','standin','churn_maintained','settle2')
   GROUP BY fixture, phase
  HAVING count(*) FILTER (WHERE metric='census_scanned') > 0
)
SELECT 'I6 ' || fixture || ' [' || phase || '] revmap=' || b_revmap || ' items=' || b_items
       || ' unused=' || b_unused || ' placeholders=' || b_ph
       || CASE WHEN b_revmap = b_items THEN ' OK' ELSE ' DISAGREES' END
  FROM c WHERE b_items IS NOT NULL
UNION ALL
SELECT 'I8 ' || fixture || ' [' || phase || '] meta(total=' || m_total || ', entry=' || m_entry
       || ', data=' || m_data || ', pending=' || m_pending || ') census(scanned=' || scanned
       || ', entry=' || c_entry || ', data=' || c_data || ', list=' || c_list
       || ', deleted=' || c_del || ', new=' || c_new || ', fsm=' || fsm || ')'
       || CASE WHEN m_entry = c_entry AND m_data = c_data + greatest(c_del - fsm, 0)
               THEN ' OK' ELSE ' DISAGREES' END
       || CASE WHEN m_total = scanned THEN ' total=OK' ELSE ' total=DISAGREES' END
  FROM c WHERE m_total IS NOT NULL
 ORDER BY 1;
SQL
  cat "$OUT/i6-i8-detail.txt"

  say "score: I9 detail, the VERBOSE line against the census"
  qat "$DB" /dev/stdin > "$OUT/i9-detail.txt" 2>&1 <<'SQL'
WITH v AS (
  SELECT fixture,
         max(num) FILTER (WHERE metric='num_pages')           AS num_pages,
         max(num) FILTER (WHERE metric='pages_newly_deleted') AS newly,
         max(num) FILTER (WHERE metric='pages_deleted')       AS del,
         max(num) FILTER (WHERE metric='pages_free')          AS free
    FROM proto.meas WHERE phase='verbose' GROUP BY fixture
),
c AS (
  SELECT fixture,
         max(num) FILTER (WHERE metric='census_scanned')  AS scanned,
         max(num) FILTER (WHERE metric='census_deleted')  AS c_del,
         max(num) FILTER (WHERE metric='fsm_free_pages')  AS fsm
    FROM proto.meas WHERE phase='churn_maintained' GROUP BY fixture
)
SELECT s.fixture || ' ' || s.amname
       || ' verbose(' || coalesce(v.num_pages::text,'-') || ',' || coalesce(v.newly::text,'-')
       || ',' || coalesce(v.del::text,'-') || ',' || coalesce(v.free::text,'-') || ')'
       || ' census(scanned=' || coalesce(c.scanned::text,'-')
       || ', deleted=' || coalesce(c.c_del::text,'-')
       || ', fsm=' || coalesce(c.fsm::text,'-') || ')'
       || CASE WHEN v.num_pages IS NULL THEN ' [no line]'
               WHEN v.num_pages = c.scanned THEN ' [num_pages = scanned]'
               ELSE ' [num_pages <> scanned]' END
  FROM proto.score s LEFT JOIN v ON v.fixture = s.fixture
                     LEFT JOIN c ON c.fixture = s.fixture
 ORDER BY s.amname, s.fixture;
SQL
  cat "$OUT/i9-detail.txt"

  say "score: every phase size, per fixture"
  q "$DB" "SELECT /* wiki_idxmaint_report */ format('%-4s %-6s base=%s raw=%s maint=%s%s reindex=%s truth=%s%%',
             fixture, amname, base_size, raw_size, maint_size,
             CASE WHEN settle2_size IS NOT NULL
                  THEN format(' (held=%s settle2=%s)', held_size, settle2_size) ELSE '' END,
             oracle_after, truth_pct)
             FROM proto.score ORDER BY amname, fixture" | tee "$OUT/phase-sizes.txt"

  say "score: the declared exceptions of the maintenance rule, and what each one read"
  { q "$DB" "SELECT /* wiki_idxmaint_report */ format('%-3s %-8s %s', id, fixture, state)
               FROM proto.declared_exception ORDER BY id"
    q "$DB" "SELECT /* wiki_idxmaint_report */ format(
               '%-4s held-horizon census=%s, dead_not_removable=%s; after release settle2=%s, dead_not_removable=%s; scored on settle2',
               s.fixture, s.held_size,
               coalesce((SELECT max(num) FROM proto.meas m
                          WHERE m.fixture = s.fixture AND m.phase='maint'
                            AND m.metric='dead_not_removable')::text,'n/a'),
               s.settle2_size,
               coalesce((SELECT max(num) FROM proto.meas m
                          WHERE m.fixture = s.fixture AND m.phase='settle2'
                            AND m.metric='dead_not_removable')::text,'n/a'))
               FROM proto.score s WHERE s.settle2_size IS NOT NULL ORDER BY s.fixture"
  } | tee "$OUT/declared-exceptions.txt"

  say "score: the coverage plan against the fixtures that ran"
  q "$DB" "SELECT /* wiki_idxmaint_report */ protocol || ' | ' || behavior || ' -> ' || fixture
             FROM proto.declared_coverage ORDER BY protocol, behavior" | tee "$OUT/coverage.txt"
}

# -------------------------------------------------------------- stage: probes
# Seven mechanism probes.  None of them scores the method; each one measures a
# fact the method or one of the two protocols depends on.  They all run after
# the oracle, so none of them can move a scored number.
stage_probes() {
  say "probes: the mechanisms behind the model"
  q "$DB" "DROP /* wiki_idxmaint_probe */ SCHEMA IF EXISTS pr CASCADE" > /dev/null
  q "$DB" "CREATE /* wiki_idxmaint_probe */ SCHEMA pr" > /dev/null

  # P1: what an index reltuples means, per AM, after each of the three writers
  qin "$DB" > "$OUT/probe-p1.log" 2>&1 <<'SQL'
CREATE /* wiki_idxmaint_probe */ TABLE pr.t1 (id bigint, k bigint, arr text[], r int8range, t text)
  WITH (autovacuum_enabled = off);
INSERT /* wiki_idxmaint_probe */ INTO pr.t1
  SELECT g, g, ARRAY['a'||g,'b'||(g%1000)], int8range(g,g+10), 'x'||g
    FROM generate_series(1,200000) g;
CREATE /* wiki_idxmaint_probe */ INDEX t1_hash   ON pr.t1 USING hash   (k);
CREATE /* wiki_idxmaint_probe */ INDEX t1_gin    ON pr.t1 USING gin    (arr);
CREATE /* wiki_idxmaint_probe */ INDEX t1_gist   ON pr.t1 USING gist   (r);
CREATE /* wiki_idxmaint_probe */ INDEX t1_spgist ON pr.t1 USING spgist (t);
CREATE /* wiki_idxmaint_probe */ INDEX t1_brin   ON pr.t1 USING brin   (k) WITH (pages_per_range = 128);
SQL
  brin_true_count() {   # $1 = index name, reachable from search_path
    q "$DB" "WITH b AS MATERIALIZED (
               SELECT g FROM generate_series(0, pg_relation_size('$1'::regclass,'main')
                                                /current_setting('block_size')::int - 1) g
                WHERE brin_page_type(get_raw_page('$1', g)) = 'regular')
             SELECT /* wiki_idxmaint_probe */ count(*)
               FROM b, LATERAL brin_page_items(get_raw_page('$1', b.g), '$1'::regclass)"
  }
  { printf -- '-- P1: an index reltuples means three different things\n'
    printf -- '-- after CREATE INDEX, no ANALYZE yet\n'
    q "$DB" "SELECT /* wiki_idxmaint_probe */ c.relname || ' ' || c.reltuples::bigint
               FROM pg_class c WHERE c.relname LIKE 't1\\_%' ORDER BY 1"
    q "$DB" "SELECT /* wiki_idxmaint_probe */ 'heap relpages=' || relpages ||
               ' blocks=' || (pg_relation_size('pr.t1'::regclass,'main')/current_setting('block_size')::int)
               FROM pg_class WHERE oid = 'pr.t1'::regclass"
    printf 'brin true summary tuples=%s\n' "$(brin_true_count pr.t1_brin)"
  } > "$OUT/probe-p1.txt"
  q "$DB" "ANALYZE /* wiki_idxmaint_probe */ pr.t1" > /dev/null
  { printf -- '-- after ANALYZE\n'
    q "$DB" "SELECT /* wiki_idxmaint_probe */ c.relname || ' ' || c.reltuples::bigint
               FROM pg_class c WHERE c.relname LIKE 't1\\_%' ORDER BY 1"
  } >> "$OUT/probe-p1.txt"
  # the DELETE and the VACUUM must not share a transaction: VACUUM cannot run
  # inside one, and a single psql -c would roll the DELETE back
  q "$DB" "DELETE /* wiki_idxmaint_probe */ FROM pr.t1 WHERE id % 10 = 0" > /dev/null
  q "$DB" "VACUUM /* wiki_idxmaint_probe */ pr.t1" > /dev/null
  { printf -- '-- after DELETE 10 percent + VACUUM, no ANALYZE\n'
    q "$DB" "SELECT /* wiki_idxmaint_probe */ c.relname || ' ' || c.reltuples::bigint
               FROM pg_class c WHERE c.relname LIKE 't1\\_%' ORDER BY 1"
    printf 'brin true summary tuples=%s\n' "$(brin_true_count pr.t1_brin)"
  } >> "$OUT/probe-p1.txt"
  cat "$OUT/probe-p1.txt"

  # P2: a parallel BRIN build's reltuples counts (participant, range) pairs
  { printf -- '\n-- P2: BRIN build reltuples, serial against parallel\n'
    for w in 0 1 4; do
      qin "$DB" > "$OUT/probe-p2-$w.log" 2>&1 <<SQL
DROP /* wiki_idxmaint_probe */ INDEX IF EXISTS pr.t1_brin2;
SET /* wiki_idxmaint_probe */ max_parallel_maintenance_workers = $w;
SET /* wiki_idxmaint_probe */ min_parallel_table_scan_size = 0;
CREATE /* wiki_idxmaint_probe */ INDEX t1_brin2 ON pr.t1 USING brin (k) WITH (pages_per_range = 128);
SQL
      printf 'max_parallel_maintenance_workers=%s reltuples=%s\n' "$w" \
        "$(q "$DB" "SELECT /* wiki_idxmaint_probe */ reltuples::bigint FROM pg_class WHERE relname='t1_brin2'")"
    done
    printf 'true summary tuples=%s\n' "$(brin_true_count pr.t1_brin2)"
  } > "$OUT/probe-p2.txt"
  cat "$OUT/probe-p2.txt"

  # P3: desummarize + summarize is not a space remedy.  Its own fixture, so it
  # measures a churned index rather than one the oracle has already rebuilt.
  { printf -- '\n-- P3: brin_desummarize_range + brin_summarize_range against REINDEX\n'
    qin "$DB" > "$OUT/probe-p3.log" 2>&1 <<SQL
CREATE /* wiki_idxmaint_probe */ TABLE pr.t3 (id bigint, v bigint)
  WITH (autovacuum_enabled = off, fillfactor = 90);
INSERT /* wiki_idxmaint_probe */ INTO pr.t3 SELECT g, g FROM generate_series(1,$BRIN_ROWS) g;
ANALYZE /* wiki_idxmaint_probe */ pr.t3;
CREATE /* wiki_idxmaint_probe */ INDEX t3_mm ON pr.t3
  USING brin (v int8_minmax_multi_ops(values_per_range = 64)) WITH (pages_per_range = 128);
ANALYZE /* wiki_idxmaint_probe */ pr.t3;
SQL
    printf 'fresh:         %s\n' "$(q "$DB" "SELECT pg_relation_size('pr.t3_mm'::regclass,'main')")"
    qin "$DB" >> "$OUT/probe-p3.log" 2>&1 <<SQL
UPDATE /* wiki_idxmaint_probe */ pr.t3 SET v = (id * 7919) % $BRIN_ROWS;
UPDATE /* wiki_idxmaint_probe */ pr.t3 SET v = (id * 104729) % $BRIN_ROWS;
UPDATE /* wiki_idxmaint_probe */ pr.t3 SET v = id;
SQL
    q "$DB" "VACUUM /* wiki_idxmaint_probe */ (ANALYZE) pr.t3" > /dev/null
    local ranges
    ranges=$(q "$DB" "SELECT /* wiki_idxmaint_probe */ ceil(relpages::numeric / 128)::int
                        FROM pg_class WHERE oid = 'pr.t3'::regclass")
    printf 'churn + VACUUM: %s  (%s ranges)\n' \
      "$(q "$DB" "SELECT pg_relation_size('pr.t3_mm'::regclass,'main')")" "$ranges"
    q "$DB" "SELECT /* wiki_idxmaint_probe */ count(*) FROM (
               SELECT brin_desummarize_range('pr.t3_mm'::regclass, g)
                 FROM generate_series(0, $ranges * 128, 128) g) s" > /dev/null
    printf 'desummarized:  %s\n' "$(q "$DB" "SELECT pg_relation_size('pr.t3_mm'::regclass,'main')")"
    q "$DB" "SELECT /* wiki_idxmaint_probe */ count(*) FROM (
               SELECT brin_summarize_range('pr.t3_mm'::regclass, g)
                 FROM generate_series(0, $ranges * 128, 128) g) s" > /dev/null
    printf 'resummarized:  %s\n' "$(q "$DB" "SELECT pg_relation_size('pr.t3_mm'::regclass,'main')")"
    printf 'summarize_new: %s ranges added\n' \
      "$(q "$DB" "SELECT brin_summarize_new_values('pr.t3_mm'::regclass)")"
    printf 'after that:    %s\n' "$(q "$DB" "SELECT pg_relation_size('pr.t3_mm'::regclass,'main')")"
    q "$DB" "REINDEX /* wiki_idxmaint_probe */ INDEX pr.t3_mm" > /dev/null
    printf 'after REINDEX: %s\n' "$(q "$DB" "SELECT pg_relation_size('pr.t3_mm'::regclass,'main')")"
  } > "$OUT/probe-p3.txt"
  cat "$OUT/probe-p3.txt"

  # P4: flushing a GIN pending list makes the index larger, not smaller
  { printf -- '\n-- P4: the GIN pending list, before and after a flush\n'
    qin "$DB" > "$OUT/probe-p4.log" 2>&1 <<SQL
CREATE /* wiki_idxmaint_probe */ TABLE pr.t4 (id bigint, arr text[]) WITH (autovacuum_enabled = off);
INSERT /* wiki_idxmaint_probe */ INTO pr.t4
  SELECT g, ARRAY['a'||g, 'b'||(g%50000), 'c'||(g%1000)] FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE /* wiki_idxmaint_probe */ pr.t4;
CREATE /* wiki_idxmaint_probe */ INDEX t4_gin ON pr.t4 USING gin (arr) WITH (fastupdate = on);
SET /* wiki_idxmaint_probe */ gin_pending_list_limit = '1GB';
INSERT /* wiki_idxmaint_probe */ INTO pr.t4
  SELECT g, ARRAY['a'||g, 'b'||(g%50000), 'c'||(g%1000)]
    FROM generate_series($((SMALL_ROWS+1)),$((SMALL_ROWS*2))) g;
SQL
    q "$DB" "SELECT /* wiki_idxmaint_probe */ 'pending pages=' || n_pending_pages ||
               ' pending tuples=' || n_pending_tuples || ' size=' ||
               pg_relation_size('pr.t4_gin'::regclass,'main')
               FROM gin_metapage_info(get_raw_page('pr.t4_gin', 0))"
    printf 'flush deleted pending pages: %s\n' \
      "$(q "$DB" "SELECT gin_clean_pending_list('pr.t4_gin'::regclass)")"
    q "$DB" "SELECT /* wiki_idxmaint_probe */ 'pending pages=' || n_pending_pages ||
               ' pending tuples=' || n_pending_tuples || ' size=' ||
               pg_relation_size('pr.t4_gin'::regclass,'main')
               FROM gin_metapage_info(get_raw_page('pr.t4_gin', 0))"
  } > "$OUT/probe-p4.txt"
  cat "$OUT/probe-p4.txt"

  # P5: on hash the oracle is not a function of the index alone.  The rebuild
  # sizes its bucket count from estimate_rel_size on the HEAP, so forging the
  # heap's relstats moves the rebuilt size with the data untouched.
  { printf -- '\n-- P5: a hash rebuild is sized from the heap estimate\n'
    local t i
    t=$(tbl h08); i=$(idx h08)
    printf 'heap relpages / reltuples: %s\n' \
      "$(q "$DB" "SELECT relpages || ' / ' || reltuples::bigint FROM pg_class WHERE oid='$t'::regclass")"
    q "$DB" "REINDEX /* wiki_idxmaint_probe */ INDEX $i" > /dev/null
    printf 'rebuild at true stats:     %s\n' "$(q "$DB" "SELECT pg_relation_size('$i'::regclass,'main')")"
    q "$DB" "UPDATE /* wiki_idxmaint_probe */ pg_class SET reltuples = 100
               WHERE oid = '$t'::regclass" > /dev/null
    q "$DB" "REINDEX /* wiki_idxmaint_probe */ INDEX $i" > /dev/null
    printf 'rebuild at reltuples=100:  %s\n' "$(q "$DB" "SELECT pg_relation_size('$i'::regclass,'main')")"
    q "$DB" "ANALYZE /* wiki_idxmaint_probe */ $t" > /dev/null
    q "$DB" "REINDEX /* wiki_idxmaint_probe */ INDEX $i" > /dev/null
    printf 'rebuild after re-ANALYZE:  %s\n' "$(q "$DB" "SELECT pg_relation_size('$i'::regclass,'main')")"
  } > "$OUT/probe-p5.txt"
  cat "$OUT/probe-p5.txt"

  # P6: the GIN oracle is budget-dependent
  { printf -- '\n-- P6: one GIN rebuild at three maintenance_work_mem values\n'
    local gi
    gi=$(idx n04)
    for m in 4MB 64MB 256MB; do
      qin "$DB" > "$OUT/probe-p6-$m.log" 2>&1 <<SQL
SET /* wiki_idxmaint_probe */ maintenance_work_mem = '$m';
REINDEX /* wiki_idxmaint_probe */ INDEX $gi;
SQL
      printf 'maintenance_work_mem=%-6s rebuilt size=%s\n' "$m" \
        "$(q "$DB" "SELECT pg_relation_size('$gi'::regclass,'main')")"
    done
  } > "$OUT/probe-p6.txt"
  cat "$OUT/probe-p6.txt"

  # P7: which GiST opclass can take the sorted build at all
  { printf -- '\n-- P7: GIST_SORTSUPPORT_PROC, per opclass this run used\n'
    q "$DB" "SELECT /* wiki_idxmaint_probe */ opc.opcname || ': support 11 ' ||
               CASE WHEN EXISTS (SELECT 1 FROM pg_amproc ap
                                  WHERE ap.amprocfamily = opc.opcfamily
                                    AND ap.amprocnum = 11)
                    THEN 'present, so the sorted build is possible'
                    ELSE 'absent, so the build is insert-driven' END
               FROM pg_opclass opc JOIN pg_am am ON am.oid = opc.opcmethod
              WHERE am.amname = 'gist' AND opc.opcname IN ('range_ops','point_ops')
              ORDER BY 1"
  } > "$OUT/probe-p7.txt"
  cat "$OUT/probe-p7.txt"
}

# ---------------------------------------------------------------- stage: edge
# Thirteen unscored edge cases, in their own database.  None of them is a bloat
# claim: each one exercises one refusal, one guard or one preservation rule, so
# none of them is scored against the oracle.
stage_edge() {
  say "edge: the refusals and the guards, in their own database"
  q postgres "DROP /* wiki_idxmaint_edge */ DATABASE IF EXISTS $EDB" > /dev/null
  q postgres "CREATE /* wiki_idxmaint_edge */ DATABASE $EDB" > /dev/null
  qin "$EDB" > "$OUT/edge-build.log" 2>&1 <<SQL
-- DISPOSABLE fixtures, one per edge case.
CREATE TABLE e_nobase (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO e_nobase SELECT g, g FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE e_nobase;
CREATE INDEX e_nobase_i ON e_nobase USING hash (k);

CREATE TABLE e_btree (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO e_btree SELECT g, g FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE e_btree;
CREATE INDEX e_btree_i ON e_btree USING btree (k);

CREATE TABLE e_invalid (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO e_invalid SELECT g, g FROM generate_series(1,1000) g;
ANALYZE e_invalid;

CREATE TABLE e_noanl (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO e_noanl SELECT g, g FROM generate_series(1,$SMALL_ROWS) g;
CREATE INDEX e_noanl_i ON e_noanl USING hash (k);

CREATE TABLE e_gate (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO e_gate SELECT g, g FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE e_gate;
CREATE INDEX e_gate_i ON e_gate USING hash (k);

CREATE TABLE e_reset (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO e_reset SELECT g, g FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE e_reset;
CREATE INDEX e_reset_i ON e_reset USING hash (k);

CREATE TABLE e_rebuild (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO e_rebuild SELECT g, g FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE e_rebuild;
CREATE INDEX e_rebuild_i ON e_rebuild USING hash (k);
COMMENT ON INDEX e_rebuild_i IS 'Search index used by the application.
Second human line with an @ sign and a } brace.';

CREATE TABLE e_small (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO e_small SELECT g, g FROM generate_series(1,2000) g;
ANALYZE e_small;
CREATE INDEX e_small_i ON e_small USING hash (k);

CREATE TABLE e_ver (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO e_ver SELECT g, g FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE e_ver;
CREATE INDEX e_ver_i ON e_ver USING hash (k);

CREATE TABLE e_am (id bigint, k bigint) WITH (autovacuum_enabled = off);
INSERT INTO e_am SELECT g, g FROM generate_series(1,$SMALL_ROWS) g;
ANALYZE e_am;
CREATE INDEX e_am_i ON e_am USING hash (k);
SQL
  # an invalid hash index, left behind by a concurrent build whose expression
  # divides by zero on one row
  qe "$EDB" > "$OUT/edge-invalid.log" 2>&1 <<'SQL'
CREATE INDEX CONCURRENTLY e_invalid_i ON e_invalid USING hash ((1 / (k - 500)));
SQL
  q "$EDB" "SELECT /* wiki_idxmaint_edge */ 'e_invalid_i indisvalid=' || indisvalid ||
              ' indislive=' || indislive FROM pg_index WHERE indexrelid = 'e_invalid_i'::regclass" \
    > "$OUT/edge-invalid.txt" 2>&1

  say "edge: the published capture statement over the edge database"
  qgen "$EDB" "$SQLD/capture.sql" > "$OUT/edge-capture-generated.sql"
  { printf -- '-- e12: capture refuses a never-analyzed table, and skips a btree\n'
    grep -c 'COMMENT ON INDEX' "$OUT/edge-capture-generated.sql" | sed 's/^/COMMENT statements: /'
    grep 'RAISE WARNING' "$OUT/edge-capture-generated.sql" | sed 's/^/  /' | cut -c1-160
    printf -- '-- indexes the capture statement named\n'
    grep -o 'COMMENT ON INDEX [a-z_]*' "$OUT/edge-capture-generated.sql" | sed 's/^/  /'
  } > "$OUT/edge.txt"
  qin "$EDB" < "$OUT/edge-capture-generated.sql" > "$OUT/edge-capture-run.log" 2>&1
  { printf -- '-- the WARNING the refusal raised, as psql reported it\n'
    grep -i 'WARNING' "$OUT/edge-capture-run.log" | sed 's/^/  /' | cut -c1-160
    printf -- '\n-- e13: capture is idempotent, so a second pass refreshes nothing\n'
  } >> "$OUT/edge.txt"
  qgen "$EDB" "$SQLD/capture.sql" > "$OUT/edge-capture2.sql"
  printf 'second pass COMMENT statements: %s\n' \
    "$(grep -c 'COMMENT ON INDEX' "$OUT/edge-capture2.sql")" >> "$OUT/edge.txt"

  # the four payloads no capture statement will ever write.  COMMENT ON takes a
  # string literal and not an expression, so each one is applied through
  # EXECUTE format(..., %L) from a DO block.
  qin "$EDB" > "$OUT/edge-handwritten.log" 2>&1 <<'SQL'
DO /* wiki_idxmaint_edge */ $edge$
DECLARE p text;
BEGIN
  -- e2: a hand-filed baseline on a btree index, which capture always skips
  SELECT '@idxmaint:' || jsonb_build_object(
           'v',1,'am','btree','fn',pg_relation_filenode('e_btree_i'::regclass),
           'ts','2026-09-15T00:00:00Z','isz',pg_relation_size('e_btree_i'::regclass),
           'ipg',(SELECT relpages FROM pg_class WHERE oid='e_btree_i'::regclass),
           'itup',(SELECT reltuples::bigint FROM pg_class WHERE oid='e_btree_i'::regclass),
           'tpg',(SELECT relpages FROM pg_class WHERE oid='e_btree'::regclass),
           'ttup',(SELECT reltuples::bigint FROM pg_class WHERE oid='e_btree'::regclass),
           'ins',0,'upd',0,'hot',0,'del',0,'vac',0,'avac',0,'anl',1)::text INTO p;
  EXECUTE format('COMMENT ON INDEX %s IS %L', 'e_btree_i', p);

  -- e3: a hand-filed baseline on an index that is not valid
  SELECT '@idxmaint:' || jsonb_build_object(
           'v',1,'am','hash','fn',pg_relation_filenode('e_invalid_i'::regclass),
           'ts','2026-09-15T00:00:00Z','isz',pg_relation_size('e_invalid_i'::regclass),
           'ipg',(SELECT relpages FROM pg_class WHERE oid='e_invalid_i'::regclass),
           'itup',1000,'tpg',(SELECT relpages FROM pg_class WHERE oid='e_invalid'::regclass),
           'ttup',1000,
           'ins',0,'upd',0,'hot',0,'del',0,'vac',0,'avac',0,'anl',1)::text INTO p;
  EXECUTE format('COMMENT ON INDEX %s IS %L', 'e_invalid_i', p);

  -- e9: a payload the reader must refuse by version
  SELECT replace(obj_description('e_ver_i'::regclass,'pg_class'), '"v": 1', '"v": 2') INTO p;
  EXECUTE format('COMMENT ON INDEX %s IS %L', 'e_ver_i', p);

  -- e10: a payload whose access method no longer matches the index
  SELECT replace(obj_description('e_am_i'::regclass,'pg_class'), '"am": "hash"', '"am": "gist"')
    INTO p;
  EXECUTE format('COMMENT ON INDEX %s IS %L', 'e_am_i', p);
END $edge$;
SQL
  q "$EDB" "SELECT /* wiki_idxmaint_edge */ count(*) || ' indexes carry a baseline after the
              hand-written payloads' FROM pg_description d
              WHERE d.classoid = 'pg_class'::regclass AND d.description LIKE '%@idxmaint:%'" \
    >> "$OUT/edge.txt"

  say "edge: churn the cases that need it, then maintain them"
  qin "$EDB" > "$OUT/edge-churn.log" 2>&1 <<SQL
UPDATE e_gate    SET k = k + $SMALL_ROWS;
UPDATE e_reset   SET k = k + $SMALL_ROWS;
UPDATE e_rebuild SET k = k + $SMALL_ROWS;
UPDATE e_small   SET k = k + 2000;
SELECT pg_stat_force_next_flush();
SQL
  for t in e_gate e_reset e_rebuild e_small; do
    q "$EDB" "VACUUM /* wiki_idxmaint_edge */ (ANALYZE) $t" > /dev/null
  done

  { printf -- '\n-- e1 e2 e3 e4 e9 e10 e11: one pass of the published statement\n'
    printf -- '-- (e_noanl carries no baseline at all, so it cannot appear)\n'
  } >> "$OUT/edge.txt"
  qf "$EDB" "$SQLD/evaluate.sql" >> "$OUT/edge.txt" 2>&1

  printf -- '\n-- e5: a statistics reset on e_reset, with no physical change\n' >> "$OUT/edge.txt"
  q "$EDB" "SELECT /* wiki_idxmaint_edge */ pg_stat_reset_single_table_counters('e_reset'::regclass)" > /dev/null
  q "$EDB" "SELECT /* wiki_idxmaint_edge */ pg_stat_clear_snapshot()" > /dev/null
  qat "$EDB" /dev/stdin >> "$OUT/edge.txt" 2>&1 <<'SQL'
SELECT /* wiki_idxmaint_edge */ 'e_reset after reset: n_tup_ins=' || n_tup_ins
       || ' n_tup_upd=' || n_tup_upd || ' vacuum_count=' || vacuum_count
  FROM pg_stat_all_tables WHERE relid = 'e_reset'::regclass;
SQL
  qf "$EDB" "$SQLD/evaluate.sql" >> "$OUT/edge.txt" 2>&1

  { printf -- '\n-- e6 e7 e8: the filenode guard, the human comment, the payload size\n'
  } >> "$OUT/edge.txt"
  qat "$EDB" /dev/stdin >> "$OUT/edge.txt" 2>&1 <<'SQL'
SELECT /* wiki_idxmaint_edge */ 'before: oid=' || 'e_rebuild_i'::regclass::oid
       || ' filenode=' || pg_relation_filenode('e_rebuild_i'::regclass)
       || ' comment_bytes=' || length(obj_description('e_rebuild_i'::regclass,'pg_class'))
       || ' payload_bytes=' || length(substring(obj_description('e_rebuild_i'::regclass,'pg_class')
                                                from '@idxmaint:(.*)$'))
       || ' has_dbr=' || (obj_description('e_rebuild_i'::regclass,'pg_class') LIKE '%"dbr"%');
SQL
  q "$EDB" "REINDEX /* wiki_idxmaint_edge */ INDEX e_rebuild_i" > /dev/null
  qat "$EDB" /dev/stdin >> "$OUT/edge.txt" 2>&1 <<'SQL'
SELECT /* wiki_idxmaint_edge */ 'after plain REINDEX: oid=' || 'e_rebuild_i'::regclass::oid
       || ' filenode=' || pg_relation_filenode('e_rebuild_i'::regclass);
SQL
  q "$EDB" "REINDEX /* wiki_idxmaint_edge */ INDEX CONCURRENTLY e_rebuild_i" > /dev/null
  qat "$EDB" /dev/stdin >> "$OUT/edge.txt" 2>&1 <<'SQL'
SELECT /* wiki_idxmaint_edge */ 'after REINDEX CONCURRENTLY: oid=' || 'e_rebuild_i'::regclass::oid
       || ' filenode=' || pg_relation_filenode('e_rebuild_i'::regclass);
SELECT /* wiki_idxmaint_edge */ 'human comment survived: ' ||
       (rtrim(regexp_replace(obj_description('e_rebuild_i'::regclass,'pg_class'),
                             '@idxmaint:.*$', ''), E' \t\r\n')
        = 'Search index used by the application.
Second human line with an @ sign and a } brace.');
SQL
  qf "$EDB" "$SQLD/evaluate.sql" >> "$OUT/edge.txt" 2>&1
  printf -- '\n-- e8: after pg_stat_reset the guard refuses until ANALYZE, then files dbr\n' \
    >> "$OUT/edge.txt"
  q "$EDB" "SELECT /* wiki_idxmaint_edge */ pg_stat_reset()" > /dev/null
  qgen "$EDB" "$SQLD/capture.sql" > "$OUT/edge-capture3.sql"
  { printf 'immediately after the reset: %s COMMENT, %s refusals\n' \
      "$(grep -c 'COMMENT ON INDEX' "$OUT/edge-capture3.sql")" \
      "$(grep -c 'RAISE WARNING' "$OUT/edge-capture3.sql")"
  } >> "$OUT/edge.txt"
  q "$EDB" "ANALYZE /* wiki_idxmaint_edge */ e_rebuild" > /dev/null
  qgen "$EDB" "$SQLD/capture.sql" > "$OUT/edge-capture4.sql"
  printf 'after ANALYZE e_rebuild:     %s COMMENT, %s refusals\n' \
    "$(grep -c 'COMMENT ON INDEX' "$OUT/edge-capture4.sql")" \
    "$(grep -c 'RAISE WARNING' "$OUT/edge-capture4.sql")" >> "$OUT/edge.txt"
  qin "$EDB" < "$OUT/edge-capture4.sql" > "$OUT/edge-capture4.log" 2>&1
  qat "$EDB" /dev/stdin >> "$OUT/edge.txt" 2>&1 <<'SQL'
SELECT /* wiki_idxmaint_edge */ 'e_rebuild_i comment_bytes=' ||
       length(obj_description('e_rebuild_i'::regclass,'pg_class'))
       || ' payload_bytes=' || length(substring(obj_description('e_rebuild_i'::regclass,'pg_class')
                                                from '@idxmaint:(.*)$'))
       || ' has_dbr=' || (obj_description('e_rebuild_i'::regclass,'pg_class') LIKE '%"dbr"%');
SQL
  printf -- '\n-- the published reader over the edge database\n' >> "$OUT/edge.txt"
  qf "$EDB" "$SQLD/read.sql" >> "$OUT/edge.txt" 2>&1
  cat "$OUT/edge.txt"
}

# -------------------------------------------------------------- stage: verify
# Re-extract the three published statements from the page and diff them against
# the files this run executed.  No literal Markdown fence appears in this file.
stage_verify() {
  say "verify: the published SQL against the SQL that ran"
  write_published_sql
  local fence line buf in_block n=0
  fence=$(printf '\140\140\140')
  in_block=0; buf=""
  rm -f "$OUT/x-capture.sql" "$OUT/x-read.sql" "$OUT/x-evaluate.sql"
  while IFS= read -r line; do
    if [ "$in_block" = 0 ]; then
      [ "$line" = "${fence}sql" ] && { in_block=1; buf=""; }
      continue
    fi
    if [ "$line" = "$fence" ]; then
      in_block=0
      case "$buf" in
        *wiki_idxmaint_capture_baseline*) printf '%s' "$buf" > "$OUT/x-capture.sql";  n=$((n+1)) ;;
        *wiki_idxmaint_read_baseline*)    printf '%s' "$buf" > "$OUT/x-read.sql";     n=$((n+1)) ;;
        *wiki_idxmaint_evaluate*)         printf '%s' "$buf" > "$OUT/x-evaluate.sql"; n=$((n+1)) ;;
      esac
      continue
    fi
    buf="$buf$line
"
  done < "$PAGE"
  printf 'published wiki_idxmaint blocks found: %s\n' "$n"
  local ok=0
  for pair in capture read evaluate; do
    if diff -u "$OUT/x-$pair.sql" "$SQLD/$pair.sql" > "$OUT/diff-$pair.txt" 2>&1; then
      printf '  %-9s identical (%s lines)\n' "$pair" "$(wc -l < "$SQLD/$pair.sql")"
      ok=$((ok+1))
    else
      printf '  %-9s DIFFERS:\n' "$pair"; sed 's/^/     /' "$OUT/diff-$pair.txt"
    fi
  done
  printf 'verbatim: %s of 3\n' "$ok" | tee "$OUT/verify.txt"
}

# --------------------------------------------------------------- stage: clean
stage_clean() {
  say "clean: stop the cluster and delete the sandbox"
  if [ -x "$BIN/pg_ctl" ] && "$BIN/pg_ctl" -D "$PGDATA" status > /dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$PGDATA" -m fast -w stop
  else
    printf 'no cluster of this sandbox is running\n'
  fi
  printf 'postmaster.pid present: %s\n' "$([ -f "$PGDATA/postmaster.pid" ] && echo yes || echo no)"
  printf 'matching postgres processes: %s\n' "$(pgrep -f -- "$PGDATA" | wc -l | tr -d ' ')"
  printf 'port %s socket or lock file present: %s\n' "$PORT" \
    "$([ -e "$SOCK/.s.PGSQL.$PORT" ] || [ -e "$SOCK/.s.PGSQL.$PORT.lock" ] && echo yes || echo no)"
  cd /
  rm -rf "$SANDBOX"
  printf 'sandbox deleted: %s\n' "$([ -d "$SANDBOX" ] && echo no || echo yes)"
}

need_server() {
  [ -x "$BIN/postgres" ] || die "no install under $INST: run the build stage first"
  "$BIN/pg_ctl" -D "$PGDATA" status > /dev/null 2>&1 || stage_start
}

ALL="build declare fixtures churn analyze_census crosscheck decide oracle score probes edge verify"

run_stage() {
  case "$1" in
    build|start|clean|reset) : ;;
    *) need_server ;;
  esac
  "stage_$1"
}

main() {
  local stages="$*"
  write_published_sql
  [ -z "$stages" ] && stages="$ALL"
  [ "$stages" = "all" ] && stages="$ALL"
  for s in $stages; do
    declare -F "stage_$s" > /dev/null || die "no such stage: $s (have: $ALL reset start clean)"
  done
  for s in $stages; do run_stage "$s"; done
  say "done: $stages"
}

main "$@"
```

## Context Reviewed

- **The two protocols**: [Mandatory Non-B-Tree, Non-GIN Bloat
  Tests](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md) for the 20
  hash, GiST, SP-GiST and BRIN fixtures, and [Mandatory GIN Bloat
  Tests](../../common-concepts/mandatory-gin-bloat-tests.md) for the 9 GIN ones.
  Both are read as protocol, not as evidence; every behavioral claim on this page
  carries its own citation into `raw/postgres-17/`. Both were re-read on 2026-09-16
  for `### The maintenance must not be defeated`, the rule they gained after the
  previous run: its five forbidden states, its four per-fixture proofs and its three
  declared exceptions, plus the GIN page's extra entry-side proof obligation and its
  distinction between a pinned horizon and the ordinary one-`VACUUM` recycling lag.
  Both were read again on 2026-09-24, after each dropped "a `VACUUM` whose index cleanup
  did not run" from its required coverage and from its declared exceptions, leaving two
  exceptions, and named that `VACUUM` under `What the protocol does not cover`.
  **Neither concept page was edited**, as the read-only rule requires.
- Pinned checkout `raw/postgres-17/` at `786db8dcf168bd9df8f55047337525ac19118b1c`
  (17.11), the only evidence base used.
- Comment storage and lifecycle: `comment.c`, `pg_description.h`, `dependency.c`,
  `system_functions.sql`, `gram.y`, and the `create_index` regression test.
- Index rebuild paths: `index.c` (`reindex_index`, `index_concurrently_swap`,
  `index_build`, `index_update_stats`), `indexcmds.c`, `relcache.c`.
- Statistics: `system_views.sql`, `pgstat.h`, `pgstat.c`, `pgstat_relation.c`,
  `pg_proc.dat`.
- Relation statistics writers: `analyze.c`, `vacuum.c`, `vacuumlazy.c`.
- Autovacuum: `autovacuum.c` (`relation_needs_vacanalyze`, `extract_autovac_opts`,
  `perform_work_item`, and the launcher's and worker's forced timeouts),
  `guc_tables.c`, `reloptions.c`.
- The removal horizon and what pins it, read on 2026-09-16 for the maintenance rule:
  `vacuum.c` (`vacuum_get_cutoffs`, the `VACOPT_SKIP_LOCKED` path and the
  `skipping vacuum of ... lock not available` errors), `vacuumlazy.c` (the
  `lazy_vacuum` gate and the `VERBOSE` tuples line), `procarray.c`
  (`ComputeXidHorizons`, the `PROC_IN_VACUUM`/`PROC_IN_LOGICAL_DECODING` skip, the
  slot horizons), `twophase.c` (the prepared transaction's dummy `PGPROC`), and
  `system_views.sql` (`pg_stat_activity`, `pg_replication_slots`,
  `pg_prepared_xacts`).
- Access methods: `hash.c`, `hashovfl.c`, `hashpage.c`, `hashutil.c`, `hash/README`;
  `gininsert.c`, `ginvacuum.c`, `ginfast.c`, `gindatapage.c`, `ginutil.c`,
  `ginarrayproc.c`, `gin/README`; `gistvacuum.c`, `gistbuild.c`, `gistutil.c`,
  `gist.h`; `spgvacuum.c`; `brin.c`, `brin_pageops.c`, `brin_revmap.c`,
  `brin_minmax_multi.c`, `brin.h`.
- Build sizing: `plancat.c` (`estimate_rel_size`), `tableam.c`, `pg_amproc.dat`
  (`GIST_SORTSUPPORT_PROC`).
- Shared page code and free space: `bufpage.c`, `indexfsm.c`, `freespace.c`.
- Locking: `lock.c`, `lockcmds.c`, `mvcc.sgml`.
- Instruments: `contrib/pgstattuple` (`pgstattuple.c`, `pgstatindex.c`),
  `contrib/pageinspect` (`brinfuncs.c`, `ginfuncs.c`, `gistfuncs.c`, `hashfuncs.c`,
  `rawpage.c`), `contrib/pg_freespacemap`.
- Exact-pin execution, 2026-09-16: an isolated 17.11 cluster built out of tree from
  this pin under `.wiki-runtime/tmp/idxnb/`, running 31 scored fixtures, 3 census
  tables, 13 edge cases and 7 probes from the one script filed above. The declaration
  pass ran at 12:27:26Z into a database that did not yet exist; the fixture pass at
  12:28:54Z; the whole measuring sequence finished at 12:40:07Z; `make check` and
  three contrib suites passed before any fixture was built. Two earlier passes of the
  same script were abandoned and contribute no number, for the reasons given under
  [The last run](#the-last-run). **That sandbox, cluster included, was stopped and
  deleted at the end of the work.**
- Exact-pin execution, 2026-09-24, on Darwin 27.0.0 arm64: two isolated 17.11 clusters,
  each built out of tree from this pin into an empty sandbox. The baseline pass ran the
  2026-09-16 script unchanged under `.wiki-runtime/tmp/idxnbbase/`, from 19:18:46Z to
  19:30:56Z. The recorded pass ran the edited script under `.wiki-runtime/tmp/idxnb/`,
  from 19:34:14Z to 19:46:01Z, with 29 scored fixtures, 3 census tables, 13 edge cases
  and 7 probes; every number on this page comes from it unless the baseline pass is
  named. Both clusters were stopped through the script's own `clean` stage and both
  sandboxes deleted, so the numbers cannot be re-diffed without re-running the script.
- Page deletion and recycling, read on 2026-09-24 for the two coverage corrections:
  `gistvacuum.c` (`gistdeletepage`), `gistutil.c` (`gistPageRecyclable`),
  `ginvacuum.c` (`ginDeletePage`, `GinPageIsRecyclable`), and `gin/README` with
  `gininsert.c` (`buildFreshLeafTuple`) for when a key has a posting tree at all.
- The 2026-09-15 run's own numbers, kept only where this run reproduced them: 29 of
  31 `(B, C, R)` triples are byte-identical across the two passes, and the two that
  are not are named under [What left the page with its
  fixtures](#what-left-the-page-with-its-fixtures).
- The previous protocol on this page, and everything it produced, is listed under
  [What left the page with its fixtures](#what-left-the-page-with-its-fixtures).

## Evidence Map

| Claim | Evidence |
|---|---|
| No index AM truncates during VACUUM | [spgvacuum.c#spgvacuumscan](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L877-L900) (`#ifdef NOT_USED`), [indexfsm.c#RecordFreeIndexPage](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L47-L55) |
| Hash cannot shrink without REINDEX | [hash/README](../../../../raw/postgres-17/src/backend/access/hash/README#L31-L34), [hashovfl.c#_hash_freeovflpage](../../../../raw/postgres-17/src/backend/access/hash/hashovfl.c#L601-L642) |
| GIN entry tree is never pruned; leaves are not re-encoded | [gin/README](../../../../raw/postgres-17/src/backend/access/gin/README#L389-L396), [gindatapage.c#ginVacuumPostingTreeLeaf](../../../../raw/postgres-17/src/backend/access/gin/gindatapage.c#L797-L813) |
| GiST deletes only fully empty leaves, and never the last downlink | [gistvacuum.c#gistvacuumpage](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L388-L403), [gistvacuum.c#last-downlink](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L541-L548) |
| A GiST page deleted by this VACUUM is not yet recyclable | [gistutil.c#gistPageRecyclable](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L885-L908) |
| SP-GiST keeps interior placeholders, and its three `pages_*` counters are equal by assignment | [spgvacuum.c#vacuumRedirectAndPlaceholder](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L569-L590), [spgvacuum.c#final-stats](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c#L902-L905) |
| BRIN orphans line pointers on relocate; bulkdelete is a no-op | [brin_pageops.c#brin_doupdate](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L246-L262), [bufpage.c#PageIndexTupleDeleteNoCompact](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c#L1333-L1347), [brin.c#brinbulkdelete](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1283-L1301) |
| BRIN cleanup summarizes every unsummarized range, and records `num_pages` before doing so | [brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332) |
| An `autosummarize` request is queued by `brininsert` and fulfilled only by a worker | [brin.c#brininsert-autosummarize](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L379-L411), [autovacuum.c#perform_work_item](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L2635-L2641) |
| Desummarize does not publish freed space | [brin_revmap.c#brinRevmapDesummarizeRange](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L395-L410) |
| Resummarizing usually relocates again | [brin.c#summarize_range](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1752-L1864), [brin_pageops.c#brin_can_do_samepage_update](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c#L319-L328) |
| `brin_page_items` emits a row for an unused line pointer | [brinfuncs.c#brin_page_items](../../../../raw/postgres-17/contrib/pageinspect/brinfuncs.c#L230-L260) |
| Comment survives plain REINDEX and is moved by REINDEX CONCURRENTLY | [index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789), [index.c#index_concurrently_swap](../../../../raw/postgres-17/src/backend/catalog/index.c#L1740-L1784), [create_index.out#testcomment](../../../../raw/postgres-17/src/test/regress/expected/create_index.out#L2300-L2324) |
| `COMMENT ON ... IS` takes a literal, not an expression | [gram.y#CommentStmt](../../../../raw/postgres-17/src/backend/parser/gram.y#L7049-L7056), [gram.y#comment_text](../../../../raw/postgres-17/src/backend/parser/gram.y#L7219-L7222) |
| ANALYZE overwrites index reltuples with the table row estimate | [analyze.c:449](../../../../raw/postgres-17/src/backend/commands/analyze.c#L449), [analyze.c#compute_index_stats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L861-L863), [analyze.c#do_analyze_rel](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663) |
| CREATE INDEX/REINDEX write the AM's own index_tuples | [index.c#index_build](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135) |
| VACUUM writes the AM's num_index_tuples when exact | [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3073-L3096) |
| GIN reports heap tuples, BRIN summarized ranges, at vacuum cleanup | [ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L735-L739), [brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332) |
| A parallel BRIN build over-counts index_tuples | [brin.c#form_and_spill_tuple](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1996-L2015), [brin.c#_brin_parallel_heapscan](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2568-L2596), [brin.c#_brin_parallel_merge](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L2610-L2720) |
| A hash rebuild is sized from the heap's estimate | [hash.c#hashbuild](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L133-L137), [plancat.c#estimate_rel_size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1064-L1078), [hashpage.c#_hash_init_metabuffer](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L505-L525) |
| A hash splitpoint allocation writes one page and leaves a hole | [hashpage.c#_hash_alloc_buckets](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c#L967-L1037) |
| Hash cleanup returns NULL when bulk delete never ran, so VACUUM prints no index line | [hash.c#hashvacuumcleanup](../../../../raw/postgres-17/src/backend/access/hash/hash.c#L647-L663), [vacuumlazy.c#verbose-index-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L718-L732) |
| A pinned removal horizon stops index vacuuming being entered, so the AM's `ambulkdelete` never runs | [vacuum.c#vacuum_get_cutoffs-OldestXmin](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1109-L1122), [vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052) |
| The horizon folds in every backend's xid and xmin, skipping only vacuum and logical decoding, then takes the older of its answer and any slot's xmin | [procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815), [procarray.c#skip-vacuum-and-decoding](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1817-L1832), [procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902) |
| A prepared transaction keeps its xid running through a dummy `PGPROC`, with no live session | [twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26) |
| `VACUUM (VERBOSE)` reports the recently-dead count as `tuples: ... are dead but not yet removable` | [vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L659-L663) |
| A `VACUUM` or `ANALYZE` that cannot take `ShareUpdateExclusiveLock` says so and skips the relation | [vacuum.c#skip-lock-not-available](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L828-L855) |
| The autovacuum launcher and worker force all four settable timeouts to 0, and all four are `PGC_USERSET` | [autovacuum.c#launcher-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L518-L526), [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470), [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631), [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642), [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653) |
| The horizon holders are readable from three views | [system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L878-L885), [system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017), [system_views.sql#pg_prepared_xacts](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L421-L426) |
| `ginvacuumcleanup` flushes the pending list, walks every block and rewrites the metapage even when `ginbulkdelete` never ran | [ginvacuum.c#cleanup-pending-when-no-bulkdelete](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L719-L729), [ginvacuum.c#ginvacuumcleanup-census](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L789) |
| A GIN page deleted by this VACUUM is not yet recyclable | [ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829) |
| A deleted GiST or GIN page is stamped with the next transaction ID when it is deleted, so it is not recyclable in the `VACUUM` that deleted it even when no snapshot is held | [gistvacuum.c#gistdeletepage-deletexid](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L640-L656), [ginvacuum.c#ginDeletePage-deletexid](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L187-L192), [gistutil.c#gistPageRecyclable](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L885-L908) |
| A GIN key's TIDs become a posting tree only when their compressed list does not fit in the entry tuple, so `n04` has no posting-tree leaf to half-empty | [gin/README:22-26](../../../../raw/postgres-17/src/backend/access/gin/README#L22-L26), [gininsert.c#buildFreshLeafTuple](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L118-L165); measured: 0 posting-tree pages in every `n04` census |
| `autovacuum = off` and `autovacuum_enabled = false` stop the launcher's verdicts, and nothing else | [autovacuum.c#AutoVacuumingActive](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3235-L3241), [autovacuum.c#av_enabled-return](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3048-L3054) |
| A GiST sorted build needs `GIST_SORTSUPPORT_PROC` in every key opclass, and ignores fillfactor | [gist.h#GIST_SORTSUPPORT_PROC](../../../../raw/postgres-17/src/include/access/gist.h#L36-L44), [gistbuild.c#build-strategy](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L205-L250), [gistbuild.c#fillfactor-ignored](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c#L462-L472), [pg_amproc.dat#point_ops-sortsupport](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L495-L497) |
| `gistchoose` breaks an exact penalty tie with a random choice, from a generator seeded differently in every process, so a GiST index grown by inserts need not repeat byte for byte | [gistutil.c#gistchoose-random-tiebreak](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L415-L420), [gistutil.c:510](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L510), [postmaster.c#InitProcessGlobals](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L2042-L2063) |
| A GIN build flushes at `maintenance_work_mem`, so the oracle is budget-dependent | [gininsert.c#build-flush](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L286-L292) |
| A GIN ANALYZE-only cleanup flushes the pending list only in an autovacuum worker | [ginvacuum.c#analyze_only-worker](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L705-L729), [analyze.c#analyze-only-cleanup](../../../../raw/postgres-17/src/backend/commands/analyze.c#L694-L721) |
| `gin_clean_pending_list` locks only the index, and is the stand-in's other half | [ginfast.c#gin_clean_pending_list](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1030-L1091) |
| The metapage page counts are written only by the cleanup census | [ginvacuum.c#ginvacuumcleanup-census](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L789), [ginutil.c#ginUpdateStats](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L645-L650) |
| No per-table statistics reset timestamp exists | [pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-17/src/include/pgstat.h#L399-L429), [pgstat.c#pgstat_kind_builtin_infos](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L278-L290), [pgstat.c#pgstat_reset](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L734-L757) |
| Churn reaches `mod_since_analyze` only through a flush, at most once a second unforced | [pgstat.c#PGSTAT_MIN_INTERVAL](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L117-L122), [pg_proc.dat#pg_stat_force_next_flush](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L5916-L5920) |
| The launcher's analyze verdict is strictly greater than an effective threshold, and `autovacuum_enabled = false` short-circuits it | [autovacuum.c#vacthresh-anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3074-L3076), [autovacuum.c#verdicts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095), [autovacuum.c#anl-effective-values](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3011-L3017), [autovacuum.c#av_enabled-return](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3048-L3054) |
| `SHARE ROW EXCLUSIVE` excludes writers, VACUUM, ANALYZE and both REINDEX forms, and needs MAINTAIN rather than SELECT | [lock.c#LockConflicts](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c#L64-L104), [mvcc.sgml#SHARE-ROW-EXCLUSIVE](../../../../raw/postgres-17/doc/src/sgml/mvcc.sgml#L1023-L1032), [lockcmds.c#LockTableAclCheck](../../../../raw/postgres-17/src/backend/commands/lockcmds.c#L277-L299), [indexcmds.c#ReindexIndex](../../../../raw/postgres-17/src/backend/commands/indexcmds.c#L2824-L2849) |
| `pgstattuple` refuses SP-GiST, BRIN and GIN; `pgstathashindex` is the only AM-specific reader and starts at block 1 | [pgstattuple.c#pgstat_relation](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c#L260-L297), [pgstatindex.c#pgstathashindex](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L579-L610), [pgstatindex.c#pgstathashindex-loop](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c#L636-L650) |
| A raw-page census needs superuser and holds no lock between pages | [rawpage.c#get_raw_page_internal](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c#L141-L199) |
| `pg_relation_size` is VOLATILE, and the one-argument form is the main fork | [pg_proc.dat#pg_relation_size](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L7487-L7495), [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L371), [system_functions.sql#pg_relation_size](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L285-L289) |
| `obj_description` filters classoid and objsubid = 0; pg_description is TOASTable text | [system_functions.sql#obj_description](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L291-L301), [pg_description.h#pg_description](../../../../raw/postgres-17/src/include/catalog/pg_description.h#L48-L57) |
| COMMENT ON takes ShareUpdateExclusiveLock, needs ownership, and has no length check | [comment.c#CommentObject](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L77), [comment.c#CreateComments](../../../../raw/postgres-17/src/backend/commands/comment.c#L142-L226) |
| DROP INDEX destroys the comment | [dependency.c#deleteOneObject](../../../../raw/postgres-17/src/backend/catalog/dependency.c#L1326-L1336) |
| A hash bucket is a pure function of the hash code | [hashutil.c#_hash_hashkey2bucket](../../../../raw/postgres-17/src/backend/access/hash/hashutil.c#L121-L135) |
| BRIN size follows heap block count; `pages_per_range` defaults to 128 | [brin_revmap.c#HEAPBLK_TO_REVMAP_BLK](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c#L35-L43), [brin.c#brinbuildCallback](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L998-L1008), [brin.h#BRIN_DEFAULT_PAGES_PER_RANGE](../../../../raw/postgres-17/src/include/access/brin.h#L39-L45) |
| GIN's `avg_width` is a post-TOAST stored width | [pg_statistic.h#stawidth](../../../../raw/postgres-17/src/include/catalog/pg_statistic.h#L40-L50) |
| One GIN array row yields one key per element | [ginarrayproc.c#ginarrayextract](../../../../raw/postgres-17/src/backend/access/gin/ginarrayproc.c#L32-L59) |
| `statement_timeout`, `lock_timeout` and `stats_fetch_consistency` are `PGC_USERSET` | [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631), [guc_tables.c#stats_fetch_consistency](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4966-L4974) |
| `gin_pending_list_limit` is `PGC_USERSET` | [guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3576-L3585) |
| The six built-in index AM names are fixed in the catalog | [pg_am.dat](../../../../raw/postgres-17/src/include/catalog/pg_am.dat#L18-L35) |
| `RelationSetNewRelfilenumber` resets relpages/reltuples with the filenode | [relcache.c#RelationSetNewRelfilenumber](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c#L3943-L3955) |
| ANALYZE measures the predicate fraction for a partial index | [analyze.c#compute_index_stats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953) |

## Open Questions

1. **`est_reclaim_pct` is a demoted level, and nothing replaces it as a bound.** An
   affine model (`expected = fixed + slope * population`) would need two baselines at
   different populations, and whether that is worth the extra comment bytes is
   untested. Until then this page publishes no bound on reclaimable space at all.
2. **Should a refused row publish the column?** Two of the eleven bound violations
   are rows the method declined to decide (`h04` at `none` and `h05` at
   `inconclusive:`), and the statement still printed a reclaim estimate for them.
   Suppressing the column on a refusal would have moved the score, which is exactly
   why it was not changed after the results were in.
3. **The BRIN arm has never been validated against a true positive.** All four BRIN
   fixtures reclaimed 0 bytes and all four were below the 1 MB floor, so the BRIN
   thresholds are still guesses and the `minmax_multi` "maintenance case" of the
   required matrix is unreproduced as a space problem.
4. **The horizon proof is a pair of reads taken beside the statement, not an
   interlock around it.** Both protocols file this as their own open question and this
   run inherits it: nothing in the engine reports "no session or slot held the horizon
   for the duration of this command". A holder that appeared and vanished entirely
   between the two reads would leave no trace, and the one signal from inside the
   statement - the `dead but not yet removable` count - is one-sided and silent on the
   five insert-only fixtures. What would close it is an interlock the engine does not
   offer; what this run has is 58 clean reads, the other 4 being the declared
   snapshots, and 23 zero counts beside the 2 declared ones.
5. **SP-GiST page classes are unverifiable from SQL.** `pageinspect` ships no
   SP-GiST decoder, so the run's SP-GiST census is `page_header` plus the FSM, and
   the protocol's placeholder behaviors are only indirectly evidenced.
6. **`brinvacuumcleanup` reported 22 summary tuples where `pageinspect` counted 23.**
   The count is written through two out-parameters that are the same pointer
   ([brin.c#brinvacuumcleanup](../../../../raw/postgres-17/src/backend/access/brin/brin.c#L1307-L1332)),
   and this run did not decompose the one-tuple gap.
7. **The auto-analyze dead end has no arm.** A table maintained only by auto-analyze
   can never satisfy `vacuum_since_baseline`, so the method is permanently
   inconclusive on it while a rebuild returns 11 %. Whether that should become its
   own recommendation - "no VACUUM has ever run; size reading only" - is a design
   choice this page does not test.
8. **The `[0.7, 1.43]` partial-index suppression window is still arbitrary.** One
   partial fixture, shifted 8.974x, far outside it. Behavior near the boundary is
   unmeasured.
9. **Only one fixture scale and one block size.** Everything is 300,000 to 2,000,000
   rows at `block_size` 8192, measured on Linux x86_64 and on macOS arm64, both with an
   8-byte `max_data_alignment`. Whether the thresholds hold at 100M rows, where the
   prompt's examples sit, is unknown.
10. **Expression and multi-column indexes were not tested at all.** The `iw` term
    silently contributes nothing for an expression key, and no fixture exercised a
    multi-column index of any AM.
11. **Concurrency was not tested, and one hole is closed by rule only.** Every
    measurement is single-session under the measurement lock. No lock available from
    SQL excludes a concurrent `gin_clean_pending_list()` by the index's owner, and
    this run simply did not run one.
12. **`REINDEX INDEX CONCURRENTLY` was never the oracle.** Ground truth is always
    plain `REINDEX INDEX`. The two should produce the same size, and that was not
    verified per fixture.
13. **The two GIN near-threshold misses remain.** `n03` at 14.91 % and `n05` at
    21.45 % were left alone by a 33.33 % justification, correctly by the declared
    threshold and arguably not by an operator's judgement. Whether
    `reltuples x avg_width` is the right mass proxy is still open: `n06`'s
    `jsonb_path_ops` fixture read `iw` from the whole `jsonb` column's average width,
    which is not the number of extracted keys.
14. **A statistics reset can leave an index with no baseline and no alarm.** After
    `pg_stat_reset()` the capture statement refuses every index until its table is
    analyzed again, and the evaluation statement reports nothing for an index with no
    baseline, so a reset plus a rebuild is a silent gap.
15. **`g09` is not byte-reproducible, across five passes now.** Its churned file has
    read 453,484,544, 454,483,968, 454,885,376, 456,335,360 and 451,428,352 bytes on
    five runs from the same pin with the same recipe, on two platforms, a 1.09 %
    spread; it is the only one of the 29 kept fixtures whose `(B, C, R)` triple moves.
    Its as-built and rebuilt sizes, both from the sorted build, read 45,375,488 and
    70,787,072 bytes on the 2026-09-16 run and on both 2026-09-24 passes, so the sorted
    build is not the cause. The variation enters with the six update rounds, whose
    inserts descend through `gistchoose`, and `gistchoose` breaks an exact penalty tie
    with a random choice from a generator seeded differently in every process
    ([gistutil.c#gistchoose-random-tiebreak](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L415-L420),
    [gistutil.c:510](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L510),
    [postmaster.c#InitProcessGlobals](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c#L2042-L2063)).
    That is the likely cause; it was not isolated.
16. **`h04` is the shape the model cannot see.** Insert-only churn left 9.07 %
    reclaimable and the method read `size_inflation` 0.982, because 400,000 new rows
    legitimately need most of the new file. Nothing in the catalog separates that
    from the 9 % a rebuild would still give back.
17. **The `anl` gate accepts only an `ANALYZE`-written population.** A `VACUUM`
    without `ANALYZE` writes an exact index count for four of the five AMs, which is
    arguably a better population term than the sampled one, and the method refuses it.
18. **Whether a fixture that declares an exception should be scored at all is a
    judgement this page made rather than derived.** The protocols say to declare the
    state and publish the reading as a held-horizon one; they do not say whether the
    same fixture may then also contribute a scored decision from a later, properly
    maintained census. This run scores `g08` and `n10` on their `settle2` state and
    says so, but a reviewer who thinks such a fixture should be unscored would read 27
    scored fixtures rather than 29.
19. **The run proves the four settable timeouts were `0` in the maintenance session,
    not that `0` is the right choice.** Forcing them off copies what a worker does to
    itself, which removes the hazard the rule names; it also means this run never
    measured what the method reads after a maintenance statement a timeout did cut
    short. That state is reachable on a real server and no fixture builds it.
20. **The measurement lock is proved not to overlap a maintenance step by comparing
    two `clock_timestamp()` readings, not by the lock manager.** `lock_acquired` is
    taken just after `LOCK TABLE` returns and `lock_released` just before `COMMIT`, so
    the interval understates the real hold by however long the commit takes. Zero
    overlaps over 90 x 31 intervals is therefore a statement about a slightly
    conservative window, and the structural argument - each census is its own
    transaction, and no maintenance statement runs inside one - is what it corroborates.
21. **No fixture reaches the dead-tuple gate any more.** `h06` and `n11` were the only
    fixtures that reached the decide pass with dead tuples left behind. Since they left,
    all 29 read `dead_ratio` 0.0000 in the decide pass, so the method's
    `inconclusive: dead tuples not yet reclaimed` arm fires on none of them. Under both
    protocols a scored fixture is decided after an effective `VACUUM ANALYZE`, so the arm
    can fire only on a state the protocols do not score, such as a pinned horizon or a
    `VACUUM` with index cleanup switched off. Whether the refusal helps or hurts there is
    no longer measured on this page. The last measurement, `h06` refused at `dead_ratio`
    0.3333 while a rebuild returned 36.94 %, is recorded under [What left the page with
    its fixtures](#what-left-the-page-with-its-fixtures).
22. **Two required coverage rows are not reached, and the fixtures as built cannot reach
    them.** No fixture was added for either in the 2026-09-24 revision, at the asker's
    choice.
    - GiST, "a deleted-but-not-recyclable page under a held snapshot": a page has to be
      deleted while a snapshot older than its delete XID is held
      ([gistvacuum.c#gistdeletepage-deletexid](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c#L640-L656),
      [gistutil.c#gistPageRecyclable](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c#L885-L908)).
      A fixture would open its snapshot *after* the delete commits, so that the
      `VACUUM` still removes the rows and deletes the emptied leaves, then run a second
      `VACUUM` while the snapshot is still held. `g08` opens its snapshot *before* the
      delete instead, so its maintenance `VACUUM` is defeated and deletes nothing while
      the snapshot is held; that defeated state is what its declared exception X1
      records.
    - GIN, "half-empty posting-tree leaves with nothing deletable": only a key whose
      TIDs do not fit in its entry tuple gets a posting tree
      ([gin/README:22-26](../../../../raw/postgres-17/src/backend/access/gin/README#L22-L26),
      [gininsert.c#buildFreshLeafTuple](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L118-L165)),
      and the delete has to thin those leaves rather than empty them. `n04` has no such
      key. `n10` has three, but deletes a contiguous id band that empties whole leaves.

## Source References

- [index.c](../../../../raw/postgres-17/src/backend/catalog/index.c) - `reindex_index`, `index_concurrently_swap`, `index_build`, `index_update_stats`.
- [comment.c](../../../../raw/postgres-17/src/backend/commands/comment.c), [pg_description.h](../../../../raw/postgres-17/src/include/catalog/pg_description.h), [gram.y](../../../../raw/postgres-17/src/backend/parser/gram.y) - the comment catalog, its lock and its grammar.
- [system_functions.sql](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql) - `obj_description`, `pg_relation_size`.
- [system_views.sql](../../../../raw/postgres-17/src/backend/catalog/system_views.sql) - `pg_stat_all_tables`, `pg_stats`, `pg_stat_database`, and the three horizon-holder views `pg_stat_activity`, `pg_replication_slots` and `pg_prepared_xacts`.
- [procarray.c](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c) - `ComputeXidHorizons`, the `PROC_IN_VACUUM`/`PROC_IN_LOGICAL_DECODING` skip, and the replication-slot horizons.
- [twophase.c](../../../../raw/postgres-17/src/backend/access/transam/twophase.c) - the prepared transaction's dummy `PGPROC`.
- [analyze.c](../../../../raw/postgres-17/src/backend/commands/analyze.c) - `do_analyze_rel`, `compute_index_stats`, the ANALYZE-only cleanup gate.
- [vacuum.c](../../../../raw/postgres-17/src/backend/commands/vacuum.c), [vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c) - `vacuum()`, `vacuum_get_cutoffs`, the `lazy_vacuum` gate, the `VERBOSE` tuples and index lines, the `skipping vacuum of ... lock not available` path, `update_relstats_all_indexes`.
- [autovacuum.c](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c) - `relation_needs_vacanalyze`, the effective reloption values, `perform_work_item`, and the launcher's and worker's forced timeouts.
- [postmaster.c](../../../../raw/postgres-17/src/backend/postmaster/postmaster.c) - `InitProcessGlobals`, which seeds the global random generator differently in every process.
- [pgstat.c](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c), [pgstat.h](../../../../raw/postgres-17/src/include/pgstat.h), [pg_proc.dat](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat) - flush intervals, the kind table, `pg_stat_force_next_flush`.
- [relcache.c](../../../../raw/postgres-17/src/backend/utils/cache/relcache.c) - `RelationSetNewRelfilenumber`.
- [hash/README](../../../../raw/postgres-17/src/backend/access/hash/README), [hash.c](../../../../raw/postgres-17/src/backend/access/hash/hash.c), [hashovfl.c](../../../../raw/postgres-17/src/backend/access/hash/hashovfl.c), [hashpage.c](../../../../raw/postgres-17/src/backend/access/hash/hashpage.c), [hashutil.c](../../../../raw/postgres-17/src/backend/access/hash/hashutil.c).
- [gin/README](../../../../raw/postgres-17/src/backend/access/gin/README), [ginvacuum.c](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c), [gindatapage.c](../../../../raw/postgres-17/src/backend/access/gin/gindatapage.c), [ginfast.c](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c), [ginutil.c](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c), [gininsert.c](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c), [ginarrayproc.c](../../../../raw/postgres-17/src/backend/access/gin/ginarrayproc.c).
- [gistvacuum.c](../../../../raw/postgres-17/src/backend/access/gist/gistvacuum.c) - `gistdeletepage`, which stamps a deleted page with the next transaction ID; [gistbuild.c](../../../../raw/postgres-17/src/backend/access/gist/gistbuild.c); [gistutil.c](../../../../raw/postgres-17/src/backend/access/gist/gistutil.c) - `gistPageRecyclable` and `gistchoose`'s random tie-break; [gist.h](../../../../raw/postgres-17/src/include/access/gist.h), [pg_amproc.dat](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat).
- [spgvacuum.c](../../../../raw/postgres-17/src/backend/access/spgist/spgvacuum.c).
- [brin.c](../../../../raw/postgres-17/src/backend/access/brin/brin.c) - `brinbulkdelete`, `brinvacuumcleanup`, `brininsert`, `summarize_range`, `brinsummarize`, and the four parallel-build routines.
- [brin_pageops.c](../../../../raw/postgres-17/src/backend/access/brin/brin_pageops.c), [brin_revmap.c](../../../../raw/postgres-17/src/backend/access/brin/brin_revmap.c), [brin_minmax_multi.c](../../../../raw/postgres-17/src/backend/access/brin/brin_minmax_multi.c), [brin.h](../../../../raw/postgres-17/src/include/access/brin.h).
- [plancat.c](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c), [tableam.c](../../../../raw/postgres-17/src/backend/access/table/tableam.c) - the heap estimate a hash rebuild is sized from.
- [bufpage.c](../../../../raw/postgres-17/src/backend/storage/page/bufpage.c), [indexfsm.c](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c), [freespace.c](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c).
- [lock.c](../../../../raw/postgres-17/src/backend/storage/lmgr/lock.c), [lockcmds.c](../../../../raw/postgres-17/src/backend/commands/lockcmds.c), [indexcmds.c](../../../../raw/postgres-17/src/backend/commands/indexcmds.c), [mvcc.sgml](../../../../raw/postgres-17/doc/src/sgml/mvcc.sgml).
- [dbsize.c](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c), [guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c), [reloptions.c](../../../../raw/postgres-17/src/backend/access/common/reloptions.c).
- [pg_am.dat](../../../../raw/postgres-17/src/include/catalog/pg_am.dat), [pg_statistic.h](../../../../raw/postgres-17/src/include/catalog/pg_statistic.h), [dependency.c](../../../../raw/postgres-17/src/backend/catalog/dependency.c).
- [pgstattuple.c](../../../../raw/postgres-17/contrib/pgstattuple/pgstattuple.c), [pgstatindex.c](../../../../raw/postgres-17/contrib/pgstattuple/pgstatindex.c) - the dispatch refusals and `pgstathashindex`.
- [brinfuncs.c](../../../../raw/postgres-17/contrib/pageinspect/brinfuncs.c), [ginfuncs.c](../../../../raw/postgres-17/contrib/pageinspect/ginfuncs.c), [gistfuncs.c](../../../../raw/postgres-17/contrib/pageinspect/gistfuncs.c), [hashfuncs.c](../../../../raw/postgres-17/contrib/pageinspect/hashfuncs.c), [rawpage.c](../../../../raw/postgres-17/contrib/pageinspect/rawpage.c).
- [pg_freespacemap.c](../../../../raw/postgres-17/contrib/pg_freespacemap/pg_freespacemap.c).
- [create_index.out](../../../../raw/postgres-17/src/test/regress/expected/create_index.out) - comment-preservation regression test.

## Navigation

- [v17/index](../../index.md) - PostgreSQL 17 landing page.
- [Mandatory Non-B-Tree, Non-GIN Bloat Tests (unverified)](../../common-concepts/mandatory-non-btree-non-gin-bloat-tests.md) - the protocol the hash, GiST, SP-GiST and BRIN fixtures ran under.
- [Mandatory GIN Bloat Tests (unverified)](../../common-concepts/mandatory-gin-bloat-tests.md) - the protocol the GIN fixtures ran under.
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [Wiki Glossary (unverified)](../../../glossary.md) - the shared vocabulary this page links on first use.
- [A COMMENT-Stored Baseline Non-B-Tree Index-Maintenance Heuristic for PostgreSQL 12 Through 17 (unverified)](non-btree-comment-baseline-maintenance-heuristic.md) - a two-test successor method, scored over this page's fixtures on 17.11 and 12.2.
- [B-Tree Bloat and Wasted Space From pgstatindex Alone, on PostgreSQL 12 and 17 (unverified)](btree-bloat-with-pgstatindex.md) - the B-tree counterpart, which uses `pgstatindex` rather than catalog-only inputs.
- [A COMMENT-Stored Baseline and Normalized Index Growth for Finding GIN Indexes That Need REINDEX CONCURRENTLY in PostgreSQL 17 (unverified)](gin-reindex-normalized-growth-comment-baseline.md) - the GIN-only comment-baseline method, scored under the GIN protocol alone.
- [How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 17 (unverified)](reindex-index-concurrently.md) - the rebuild path this heuristic recommends.
- [Planner Penalties for Bloated Indexes in PostgreSQL 17 (unverified)](../query-planning/bloated-indexes-query-planner.md) - what the planner does and does not see about a bloated index.
- [versions](../../../versions.md) - source pin manifest.
- [index](../../../index.md) - global wiki catalog.
