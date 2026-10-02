---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# A COMMENT-Stored Baseline and Normalized Index Growth for Finding GIN Indexes That Need REINDEX CONCURRENTLY in PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
  - [Prompt corrections](#prompt-corrections)
  - [The first prompt](#the-first-prompt)
  - [The second prompt](#the-second-prompt)
  - [The third prompt](#the-third-prompt)
  - [The fourth prompt](#the-fourth-prompt)
- [Answer](#answer)
  - [Verdict](#verdict)
  - [What conformance to the protocol changed](#what-conformance-to-the-protocol-changed)
  - [The maintenance was not defeated](#the-maintenance-was-not-defeated)
  - [What the settle step itself cost](#what-the-settle-step-itself-cost)
  - [Why a GIN index's physical size only ever goes up](#why-a-gin-indexs-physical-size-only-ever-goes-up)
  - [Why the baseline must not use the GIN index's own reltuples](#why-the-baseline-must-not-use-the-gin-indexs-own-reltuples)
  - [What the COMMENT stores](#what-the-comment-stores)
  - [The comment format](#the-comment-format)
  - [SQL 1: record the baseline](#sql-1-record-the-baseline)
  - [SQL 2: read the baseline back](#sql-2-read-the-baseline-back)
  - [SQL 3 and 4: the ratios and the verdict](#sql-3-and-4-the-ratios-and-the-verdict)
  - [The declared kind of every published column](#the-declared-kind-of-every-published-column)
  - [The fixture corpus and its recipes](#the-fixture-corpus-and-its-recipes)
  - [The phases every fixture ran](#the-phases-every-fixture-ran)
  - [The 23 scored fixtures and their results](#the-23-scored-fixtures-and-their-results)
  - [The declared upper bound failed, so est_reclaimable is a level](#the-declared-upper-bound-failed-so-est_reclaimable-is-a-level)
  - [How close the prediction came](#how-close-the-prediction-came)
  - [First failure: a fresh GIN build is not linear in heap tuples](#first-failure-a-fresh-gin-build-is-not-linear-in-heap-tuples)
  - [Second failure: the pending-list high-water mark](#second-failure-the-pending-list-high-water-mark)
  - [Third failure: the denominator is a sample and the baseline is not](#third-failure-the-denominator-is-a-sample-and-the-baseline-is-not)
  - [The baseline itself depends on maintenance_work_mem](#the-baseline-itself-depends-on-maintenance_work_mem)
  - [The maintenance pair: what the settle step and the maintenance step move](#the-maintenance-pair-what-the-settle-step-and-the-maintenance-step-move)
  - [The auto-analyze window, and why the method almost never sees it](#the-auto-analyze-window-and-why-the-method-almost-never-sees-it)
  - [A snapshot held across the settling VACUUM](#a-snapshot-held-across-the-settling-vacuum)
  - [Keys that no longer occur](#keys-that-no-longer-occur)
  - [The verdict ladder, in order](#the-verdict-ladder-in-order)
  - [Why the shrinkage rule can never fire on its own](#why-the-shrinkage-rule-can-never-fire-on-its-own)
  - [The statistics counter you must not build the guard on](#the-statistics-counter-you-must-not-build-the-guard-on)
  - [The four cross-checks and the nine invariants](#the-four-cross-checks-and-the-nine-invariants)
  - [The simulated auto-analyze census](#the-simulated-auto-analyze-census)
  - [End-to-end run of the published statements](#end-to-end-run-of-the-published-statements)
  - [Edge cases proven on the server](#edge-cases-proven-on-the-server)
  - [Operational notes: locks, privileges, timeouts, GUC scopes](#operational-notes-locks-privileges-timeouts-guc-scopes)
  - [Recommended thresholds](#recommended-thresholds)
  - [Coverage the protocol requires, and what this page skipped](#coverage-the-protocol-requires-and-what-this-page-skipped)
  - [What left the page with its fixtures](#what-left-the-page-with-its-fixtures)
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

Four prompts drove this page, and all four were filed after prompt-hygiene correction at
the asker's request. The first three were corrected and restated, as described below. The
fourth was corrected silently, so only its corrected text is filed, under
[The fourth prompt](#the-fourth-prompt).

The first prompt wrote `agents.md` for `AGENTS.md` and lowercase `postgresql` for
`PostgreSQL`, put a space before the comma after the final requirement, spliced an
operational instruction (`before anything perform a cleanup of .wiki-runtime`) into the
question text, and wrote the threshold range `75–80%` with an en dash. The
`.wiki-runtime` cleanup instruction was carried out but is not part of the question.

The second prompt read:

```text
follow agents.md, in postgresql 17, review question: # A COMMENT-Stored Baseline and
Normalized Index Growth for Finding GIN Indexes That Need REINDEX CONCURRENTLY in
PostgreSQL 17 (unverified), update tests based on the changes from common-concept,
update or remove all tests that aren't following # Mandatory GIN Bloat Tests (unverified)
```

Its defects were `agents.md` for `AGENTS.md`, lowercase `postgresql`, `review question:`
without an article, a pasted `# ` heading marker before each of the two page titles, the
`(unverified)` hint treated as part of both titles, `from common-concept` for "from the
common concept page", the contraction `aren't following` for "do not follow", and no
terminal period. The asker chose **correct and restate**, and then settled the scope in
three further answers: a **full re-run with a published measurement script** rather than a
paper re-port; tests that cannot conform are **removed with the claims they backed**, not
relabelled; and **every coverage behavior the method can reach** is added.

The third prompt read:

```text
follow agents.md, in postgresql 17, review : gin-reindex-normalized-growth-comment-baseline.md
```

Its defects were `agents.md` for `AGENTS.md`, lowercase `postgresql`, a space before the
colon, the page named by its file name rather than its title, no sentence capitalisation and
no terminal period. The asker chose **correct and restate** again, and settled the scope in
three further answers: **source re-verification plus a full re-run** of the published
script; the page is **brought onto** the protocol's
[The maintenance must not be defeated](../../common-concepts/mandatory-gin-bloat-tests.md#the-maintenance-must-not-be-defeated)
rule, which the protocol gained *after* this page's previous run, by editing the filed
script in place; and the sandbox is **deleted** at the end.

### The first prompt

Follow `AGENTS.md`, in PostgreSQL 17. Question:

Design a PostgreSQL heuristic to identify GIN indexes that may need
`REINDEX CONCURRENTLY`, using only catalog/metadata information and storing the baseline
in the index `COMMENT`. Do not create any new tables.

At index creation or immediately after a successful reindex, store:

- Baseline physical index size
- Baseline heap `reltuples`

During evaluation, collect:

- Current physical index size
- Current heap `reltuples`

Calculate:

```text
index_size_ratio =
    current_index_size / baseline_index_size

heap_tuple_ratio =
    current_heap_reltuples / baseline_heap_reltuples

normalized_index_growth =
    index_size_ratio / heap_tuple_ratio
```

Use the normalized value to distinguish legitimate index growth caused by table growth
from disproportionate GIN growth.

Example:

```text
Baseline:
index size = 10 GB
heap tuples = 10M

Current:
index size = 15 GB
heap tuples = 10M

normalized_index_growth = 1.50
```

This should be considered a potential `REINDEX` candidate.

If both the index and heap grow by 50%:

```text
index size: 10 GB -> 15 GB
heap tuples: 10M -> 15M

normalized_index_growth = 1.0
```

Do not recommend `REINDEX` based on size growth alone.

Also detect large table shrinkage. For example:

```text
heap tuples <= 50% of baseline
AND
index size remains >= 75-80% of baseline
```

This should be considered a strong `REINDEX` candidate because the indexed population has
fallen substantially while the physical GIN index has not shrunk proportionally.

Requirements:

- Do not use GIN index `pg_class.reltuples` as the tuple-count baseline.
- Use the heap/table `reltuples` instead.
- Treat thresholds as heuristics for identifying candidates, not proof of bloat.
- Prefer evaluating only after meaningful table activity/churn.
- Store all baseline metadata inside the index `COMMENT`.
- After a successful `REINDEX`, replace the `COMMENT` baseline with the new index size and
  heap tuple count.
- Provide SQL examples for recording the baseline, reading it, calculating the ratios, and
  determining whether the index is a `REINDEX` candidate.

### The second prompt

Follow `AGENTS.md`, in PostgreSQL 17. Review the question
"A COMMENT-Stored Baseline and Normalized Index Growth for Finding GIN Indexes That Need
REINDEX CONCURRENTLY in PostgreSQL 17". Update the tests based on the changes from the
common concept page, and update or remove all tests that do not follow
"Mandatory GIN Bloat Tests".

### The third prompt

Follow `AGENTS.md`, in PostgreSQL 17. Review
"A COMMENT-Stored Baseline and Normalized Index Growth for Finding GIN Indexes That Need
REINDEX CONCURRENTLY in PostgreSQL 17".

### The fourth prompt

Follow `AGENTS.md`, in PostgreSQL 17. Remove the invalid test from the question
"A COMMENT-Stored Baseline and Normalized Index Growth for Finding GIN Indexes That Need
REINDEX CONCURRENTLY in PostgreSQL 17", and re-run all tests.

Scope, settled with the asker before any edit on 2026-09-24:

- The invalid test is **fixture `i01` as a whole**. `i01` ran `VACUUM (INDEX_CLEANUP OFF)`
  between its writes and its settle step. Earlier that day
  [Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md) stopped
  requiring "a `VACUUM` whose index cleanup did not run" and stopped declaring it as an
  exception. The fixture, its section, its declared exception, its coverage row and every
  claim it backed left the page; see
  [What left the page with its fixtures](#what-left-the-page-with-its-fixtures).
- "All tests" means the script's whole default order: `make check`, the five contrib suites
  and every stage, run from an empty sandbox. The page has no section outside the script.
- The two glossary entries this page needed and lacked were added and checked on
  PostgreSQL 17 only.

## Answer

### Verdict

The design works and is buildable exactly as specified: four plain SQL statements, no new
table, no [extension](../../../glossary.md#extension), and the whole baseline living in an `@ginbase:` JSON payload appended
to the index's own [`COMMENT ON INDEX`](../../../glossary.md#comment-on). Everything below was re-measured on 2026-09-24
under [Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md),
from the single script filed under [Measurement Script](#measurement-script), on a 17.11
server built out of tree from this repository's pin, on macOS 27 arm64. Every scored cell
of the 2026-09-17 filing, made on Linux x86_64, reproduced, except the one that an
[`ANALYZE`](../../../glossary.md#statistics) sample decides (`c02`'s bound).

Over **23 scored fixtures**, each run through the protocol's five phases and each measured
against one [`REINDEX INDEX`](../../../glossary.md#reindex) oracle, the method's decision was right **18 times**, with
**1 false positive**, **0 false negatives**, and **4 refusals** of which one hid a real
73.95 % candidate on purpose.

The page follows the protocol's
[The maintenance must not be defeated](../../common-concepts/mandatory-gin-bloat-tests.md#the-maintenance-must-not-be-defeated),
and **the maintenance held on every step**: 75 settle and maintenance statements, **0
[tuples](../../../glossary.md#tuple) dead but not yet removable on 74 of 74** where a maintained state was claimed, **0**
skipped statements, **0** cancellations, and all four settable timeouts forced to **0 on
75 of 75** as an [autovacuum](../../../glossary.md#autovacuum) worker forces them on itself. The one exception is declared and
is the point of its fixture: `s01`'s settling [`VACUUM`](../../../glossary.md#vacuum), run with a [snapshot](../../../glossary.md#snapshot) held, reports
**500,000** tuples dead but not yet removable, and the `VACUUM` after the release reports 0
([The maintenance was not defeated](#the-maintenance-was-not-defeated)).

The declared columns fared worse than the decision, and that is the headline result of
the re-run:

1. **The one bound this page was willing to declare failed.** `est_reclaimable` was filed
   as an **upper bound** — the bytes it names are never fewer than the bytes a rebuild
   returns — before any fixture existed. It **held on 13 of 20** fixtures that published
   it and was **violated on 7**, by as little as 0.01 points (`c11`) and as much as
   10.43 (`c01`). Under the protocol a violated bound is corrected or demoted, and a
   catalogs-only method cannot be corrected here, so the column is **demoted to a level**:
   it may be read as a ranking hint and must not be read as reclaimable space. `c02` is the
   sharpest case: its verdict is decided by the `ANALYZE` sample in the method's own
   denominator. Over seven runs of the same fixture it read `HELD` three times and
   `VIOLATED` four times, between −0.03 and +0.02 points, and it held by +0.02 on the
   recorded run
   ([Third failure](#third-failure-the-denominator-is-a-sample-and-the-baseline-is-not)).
2. **A rebuild can make a [GIN](../../../glossary.md#gin) index bigger.** `p02`, a `fastupdate = off` index that grew
   by no bytes at all under 150,000 new rows, rebuilt from 14,778,368 to **17,883,136**
   bytes — a **−21.01 %** oracle. Incremental insertion packed it denser than its own
   bulk build at `maintenance_work_mem = 256MB`. "Reclaimable" is therefore not always a
   non-negative quantity, and nothing the method reads can tell.
3. **"Both grew by 50 %, so normalized = 1.0, so do nothing" is still the wrong
   instinct, but for a smaller amount than the page used to claim.** `c01` grew the table
   50 % by ordinary `INSERT` and the index by 51.7 % (22,339,584 -> 33,890,304), giving
   `normalized_index_growth` 1.0114 — and the rebuild still returned **11.55 %**.
4. **A fresh GIN build is not linear in [heap](../../../glossary.md#heap) tuples, so `heap_tuple_ratio` is a poor
   normalizer.** Rebuilt over the same 10,000-key universe the same index measured
   6,938,624 / 12,599,296 / 22,339,584 / 59,613,184 / 82,264,064 / 245,768,192 bytes at
   250k / 500k / 1M / 2M / 4M / 8M rows: **2.67x** between 1M and 2M rows as [posting lists](../../../glossary.md#posting-list)
   convert to [posting trees](../../../glossary.md#posting-tree), then only **1.38x** between 2M and 4M.
5. **The [pending-list](../../../glossary.md#pending-list) blind spot is real and is sized by `gin_pending_list_limit`, not by
   the index.** `p01` (`fastupdate = on`) grew 515 [pages](../../../glossary.md#page) — 4,218,880 bytes against a 4 MB
   default limit — where its `fastupdate = off` twin grew nothing, and `p01` scored
   `no action` at `normalized_index_growth` 1.0284.
6. **The settle step the protocol mandates is not free, and part of what the method reads
   as growth is the settle step's own allocation.** On **8 of the 22** fixtures that have a
   settle step, the `VACUUM` that settles the index made the file **bigger** — by
   **4,849,664 bytes** on `c01` and `c12`, **16,310,272 bytes** in total — and on none did
   it make the file smaller
   ([What the settle step itself cost](#what-the-settle-step-itself-cost)).

Treat the output as a ranked shortlist, never as proof of [bloat](../../../glossary.md#bloat) — which is what the brief
asks for, and what the same-version documentation asks for too: "The potential for bloat in
non-B-tree indexes has not been well researched. It is a good idea to periodically monitor
the index's physical size when using any non-B-tree index type."
([maintenance.sgml#routine-reindex](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1042-L1046))

### What conformance to the protocol changed

The protocol is defined on
[Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md) and is not
restated here. What it changed on this page:

| Protocol rule | What this page had before | What it has now |
|---|---|---|
| five phases per fixture, churn ending in settle then maintenance | a 12-cell matrix whose recipes were one-line prose; three cells deliberately skipped `VACUUM` or `ANALYZE` | 23 scored fixtures, every one through build -> baseline -> churn (writes, settle, maintenance) -> decide -> oracle, with per-phase readings filed |
| the settle step must be proven | not asserted | `n_pending_pages` read at every phase boundary: **0 on 23 of 23** after the settle step, and the `VACUUM VERBOSE` index line recorded for each |
| the maintenance step is mandatory | absent | `VACUUM ANALYZE` after every churn, except the two auto-analyze stand-ins, which declare `ANALYZE` plus `gin_clean_pending_list()` instead |
| the simulated auto-analyze census | absent | 27 tables walked, 1 analyzed, one declined **exactly on** its threshold, one short-circuited by `autovacuum_enabled = false` |
| [`SHARE ROW EXCLUSIVE`](../../../glossary.md#lock-mode) measurement lock | the evaluation ran unlocked | one transaction locks all 24 fixture tables and runs the published statement inside it |
| one measured `REINDEX INDEX` oracle, bracketed by [`pg_relation_size(index, 'main')`](../../../glossary.md#relation-size-functions) | ground truth was `1 - post/pre`, unbracketed | every fixture's oracle is two size readings around one rebuild at a recorded [`maintenance_work_mem`](../../../glossary.md#maintenance_work_mem) |
| a declared kind per published column, filed before the run | absent | 10 columns declared at 18:47:58Z, two seconds before the first fixture's baseline payload |
| four mandatory cross-checks | two caveats stated in prose | four checks plus nine declared invariants, scored per fixture |
| a published measurement script | none; the sandbox and harness were deleted | one 1,913-line Bash-and-SQL script, filed in full |

Three rows were added on 2026-09-17, because the protocol gained
[The maintenance must not be defeated](../../common-concepts/mandatory-gin-bloat-tests.md#the-maintenance-must-not-be-defeated)
and this page had never been checked against it.

| Protocol rule | What this page had before | What it has now |
|---|---|---|
| the maintenance must have been **effective**, not merely issued | every session, the settle and maintenance statements included, inherited the run's `statement_timeout = 900s` and `lock_timeout = 15s`, and no fixture recorded a single one of the rule's four proofs | every settle and maintenance statement runs through one helper that forces [`statement_timeout`](../../../glossary.md#statement_timeout-and-lock_timeout), `lock_timeout`, [`transaction_timeout`](../../../glossary.md#transaction_timeout-and-idle_in_transaction_session_timeout) and `idle_in_transaction_session_timeout` to `0` and prints what they were, and one that parses its own `VERBOSE` output and **dies rather than score** a defeated fixture: **75 steps, 74 of 74 at 0 dead but not yet removable, 0 skipped, 0 cancelled, 75 of 75 at all-zero timeouts, 75 of 75 with their own [command tag](../../../glossary.md#command-tag)** |
| the horizon holders beside every step | one `backend_xmin` count, on `s01` only | a reading of [`pg_stat_activity`](../../../glossary.md#pg_stat_activity)'s `xact_start`/`backend_xid`/`backend_xmin`, `pg_replication_slots`' `xmin`/`catalog_xmin` and `pg_prepared_xacts` on **each side of all 75 steps**; exactly one reading is not all zero, and it is `s01`'s declared snapshot |
| the concurrency rule: what the progress views could see at either end of a census | not read | [`pg_stat_progress_vacuum`](../../../glossary.md#progress-reporting), `pg_stat_progress_analyze` and `pg_stat_progress_create_index` counted for the [relation](../../../glossary.md#relation) at both ends of every page census: **0 rows on 26 of 26** |

### The maintenance was not defeated

On GIN the way a maintenance step fails is not silent, it is reassuring. Under a pinned
[removal horizon](../../../glossary.md#xmin-horizon) the churn's rows are [`HEAPTUPLE_RECENTLY_DEAD`](../../../glossary.md#dead-tuple) and are only counted
([vacuumlazy.c#recently_dead_tuples](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L208-L212),
[vacuumlazy.c#lazy_scan_noprune-recently-dead](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1770-L1776)),
[index vacuuming](../../../glossary.md#index-vacuuming) is entered only when dead [TIDs](../../../glossary.md#tid) were collected
([vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052)),
so `ginbulkdelete` never runs — and `ginvacuumcleanup` still flushes the pending list on
the `stats == NULL` path, walks every [block](../../../glossary.md#block) and rewrites the [metapage](../../../glossary.md#metapage) counters anyway
([ginvacuum.c#cleanup-pending-when-no-bulkdelete](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L719-L729),
[ginvacuum.c#ginvacuumcleanup-census](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L789)).
The index looks settled, the metapage is current, `n_pending_pages` reads 0, and not one
dead entry has left the index. Every proof the settle step asks for is satisfied by an
index that was never maintained.

So the run proves the step instead of assuming it. What it does, per statement:

| What the run does | Why |
|---|---|
| forces `statement_timeout`, `lock_timeout`, `transaction_timeout` and `idle_in_transaction_session_timeout` to `0` in the maintenance session, and prints all four back from `pg_settings` | all four are [`PGC_USERSET`](../../../glossary.md#guc-context), so session scope ([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631), [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642), [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653)), and an autovacuum worker forces exactly these four to `0` on itself "to avoid letting these settings prevent regular maintenance from being executed" ([autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470)). The run's own `statement_timeout = 900s` and `lock_timeout = 15s` would otherwise have been inherited by the very statements the protocol credits |
| parses `tuples: ... are dead but not yet removable` out of **every** `VERBOSE` block, not just the first | that count is `recently_dead_tuples` ([vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L659-L663)), and it is the one positive signal a pinned horizon leaves. A fixture's [TOAST](../../../glossary.md#toast) relation gets its own block after the main one, so the check reads all of them: 2 blocks on every fixture that has a TOAST relation, 1 on `o03`, whose only column is an `int` |
| counts `skipping vacuum of ... --- lock not available` and `skipping analyze of ...` lines | that is what a lock conflict produces, and it is a command that returned without doing anything ([vacuum.c#skip-lock-not-available](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L828-L855)) |
| reads the horizon holders on each side of the step: `pg_stat_activity`'s `xact_start`, `backend_xid` and `backend_xmin` ([system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L878-L885)), `pg_replication_slots`' `xmin` and `catalog_xmin` ([system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017)), and `pg_prepared_xacts` | `OldestXmin` folds in every [backend](../../../glossary.md#backend)'s xid and xmin, exempting only a vacuuming or decoding backend ([vacuum.c:1120](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1120), [procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815), [procarray.c#skip-vacuum-and-decoding](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1817-L1832)), takes the older of its own answer and a slot's ([procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902)), and a [prepared transaction](../../../glossary.md#two-phase-commit) keeps its xid running through a dummy [`PGPROC`](../../../glossary.md#procarray) with no live session to show for it ([twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26)) |
| records the step's own index line — `num_pages`, `pages_newly_deleted`, `pages_deleted`, `pages_free` ([vacuumlazy.c#verbose-index-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L720-L731)) | the settle proof alone cannot tell a `VACUUM` that removed entries from one that only flushed the pending list |
| **dies rather than score** when any of those fails | the protocol's instruction for a defeated fixture is repair and re-run, not annotation |

Measured, over the whole run:

| Proof | Result |
|---|---|
| settle and maintenance steps run through the helper | **75** — 24 build-phase settles, 22 churn settles, 1 second settle (`s01`), 22 churn maintenances, 2 auto-analyze stand-ins, 1 census `ANALYZE`, and the 3 of the published-statement replay. The churn settles and maintenances include `c04`'s and `e01`'s, which have no writes |
| all four settable timeouts read `0` in the step's own session | **75 of 75** |
| the statement completed with its own command tag | **75 of 75** |
| `skipping vacuum of`/`skipping analyze of` lines | **0** |
| cancellations or errors | **0** |
| `tuples: ... are dead but not yet removable` = 0 on every `VERBOSE` block, declared step aside | **74 of 74** |
| steps whose horizon read was not `backends=0 slots=0 prepared=0` on both sides | **1 of 75**, and it is `s01`'s declared holder: one `type=client backend state=active xmin=1075`, with no `backend_xid` at all, on both sides of the step. 0 [replication slots](../../../glossary.md#replication-slot) and 0 prepared transactions existed at any of the 150 readings |
| declared invariant **I7** (the maintenance was not defeated) | **72 of 72** steps at the point the score stage ran, and 75 of 75 once the replay's three are in |
| declared invariant **I8** (timeouts 0, completed, no skip, no cancellation) | **72 of 72** steps, and 75 of 75 with the replay |

Two exceptions are declared rather than forbidden, exactly as the protocol allows:

| Exception | What this run did, and what it measured |
|---|---|
| `s01`, the fixture the coverage list requires to hold a snapshot across its settling `VACUUM` | the snapshot is opened **before** the churn commits, so it really pins the horizon: the settling `VACUUM` reports **500,000 tuples dead but not yet removable** and deletes **0** index pages, and the `VACUUM` after the release reports **0** dead-but-not-removable and deletes 60. A snapshot opened after the churn would have held nothing back, and the check that would have caught it is the nonzero count, which this run requires rather than tolerates |
| the `SHARE ROW EXCLUSIVE` measurement lock, which excludes `VACUUM` and `ANALYZE` by design | taken only in the census and decide phases, after every settle step, every maintenance step and the census, and released before the oracle. No maintenance statement of this run ran while it was held |

Until 2026-09-24 the page declared a third, `i01`'s `VACUUM (INDEX_CLEANUP OFF)`. The
protocol no longer declares that exception or requires that coverage, so the fixture
left the page; see [What left the page with its fixtures](#what-left-the-page-with-its-fixtures).

The command-tag row reads 75 of 75 on the recorded run, not because the statements
changed but because the check was repaired. The filed script counted tags with a basic
regular expression, `'^VACUUM$\|^ANALYZE$'`. BSD `grep` on macOS treats a `$` that comes
before `\|` as a literal character, so that pattern never matched a bare `VACUUM` line.
A pass of the unchanged script on this Mac therefore read I8 as **3 of 76**: only the three
`ANALYZE`-only steps were counted. The script now uses `grep -E` with `^(VACUUM|ANALYZE)$`,
which behaves the same on both platforms. Every `VACUUM` log of that pass ends in its own
`VACUUM` line, which is what the repaired count reads.

What the proofs do **not** establish: the horizon reading is a read taken beside the
statement, not an interlock, so a holder that appeared and vanished inside the step leaves
no trace in either reading — the `dead but not yet removable` count is the check that does
not have that hole. And the six mechanism probes under
[Measurement Script](#measurement-script) are not scored fixtures, so they are outside the
rule; the run records one horizon reading at the start of the probe database anyway.

### What the settle step itself cost

The protocol warns that settling an index is part of the measurement and is not free,
because the flush drives the accumulated keys through `ginEntryInsert`
([ginfast.c#flush-entry-insert](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L926-L933))
and a [split](../../../glossary.md#page-split) on that path takes a new page from `GinNewBuffer`
([ginbtree.c#split-newbuffer](../../../../raw/postgres-17/src/backend/access/gin/ginbtree.c#L463-L466)).
This run measures it. Of the 22 fixtures with a settle step, **8 came out of it bigger**,
**0 came out smaller**, and the total the settle step added is **16,310,272 bytes**:

| fixture | before the settle step | after it | delta | pending pages before it |
|---|---|---|---|---|
| c01 | 29,040,640 | 33,890,304 | **+4,849,664** | 507 |
| c12 | 29,040,640 | 33,890,304 | **+4,849,664** | 507 |
| c06 | 45,981,696 | 47,808,512 | +1,826,816 | 499 |
| x01 | 6,275,072 | 7,471,104 | +1,196,032 | 412 |
| c05 | 84,615,168 | 85,712,896 | +1,097,728 | 499 |
| c09 | 84,615,168 | 85,712,896 | +1,097,728 | 499 |
| c11 | 84,615,168 | 85,712,896 | +1,097,728 | 499 |
| x03 | 9,699,328 | 9,994,240 | +294,912 | 150 |

Two consequences for the method, and one for any reader of a GIN index's size:

- **Part of what the method reads as growth is the settle step's own allocation.** The
  protocol hands the method the settled file, and on `c01` 4,849,664 of the 11,550,720
  bytes between baseline and decide — **42 %** — were added by the `VACUUM` rather than by
  the inserts. The method cannot separate them, and neither can `pg_relation_size`.
- **The fixtures that grew are the ones that had a pending list.** All eight carry between
  150 and 507 pending pages at the end of their writes; every fixture that reached the
  settle step with 0 pending pages came through it byte-identical. `p02`, the
  `fastupdate = off` twin, is the control: 0 pending pages, 0 bytes added.
- **Measuring before the settle step is not the fix.** The pre-settle file is a state whose
  metapage still describes the as-built index, which is why the protocol forbids scoring it;
  see [The maintenance pair](#the-maintenance-pair-what-the-settle-step-and-the-maintenance-step-move).

### Why a GIN index's physical size only ever goes up

This is the premise that makes a stored size baseline meaningful, and it is decided in one
function. `ginvacuumcleanup` walks every block, hands each recyclable page to the [free space
map](../../../glossary.md#free-space-map), updates the metapage counters, and vacuums the FSM
([ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L694-L803)).
A page is recyclable when it is new, or deleted with a delete-xid no longer visible to any
backend
([ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829)).
Pending-list pages are recycled the same way, by `ginInsertCleanup` and its FSM vacuum
([ginfast.c:1015-1020](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1015-L1020)).

Nothing in `src/backend/access/gin/` calls [`RelationTruncate`](../../../glossary.md#truncation). Freed GIN pages are returned
to the index for reuse and never to the filesystem, so `pg_relation_size` on a GIN index is a
high-water mark. `pg_relation_size(regclass)` is the `main` [fork](../../../glossary.md#fork) only
([system_functions.sql#pg_relation_size](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L285-L289)),
and it is computed by stat-ing the segment files rather than read from a [catalog](../../../glossary.md#catalog) counter
([dbsize.c#calculate_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L302-L343)),
so it reflects the file, not an estimate.

`REINDEX` is what shrinks it. Plain `REINDEX INDEX` keeps the index's [OID](../../../glossary.md#oid) and gives it a new
[relfilenode](../../../glossary.md#relfilenumber)
([index.c:3781-3789](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789)),
which is both why the comment survives and how a rebuild is detected.

Measured: declared invariant **I1 — `index_size_ratio >= 1` on every fixture not rebuilt
since its baseline — held on 23 of 23**. The only value below 1 anywhere in the run is
`c09`'s 0.9996, and `c09` is the fixture that *was* rebuilt out of band, which the ladder
caught one rung above the ratios.

### Why the baseline must not use the GIN index's own reltuples

The brief forbids it. The source says why: three commands write an index's
`pg_class.reltuples` and they mean three different things. [`reltuples`](../../../glossary.md#reltuples-and-relpages) is documented as
"# of tuples (not always up-to-date; -1 means \"unknown\")"
([pg_class.h:62-66](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L66)).

- **`CREATE INDEX` / `REINDEX`** write the [access method](../../../glossary.md#access-method)'s own `index_tuples` through
  `index_update_stats`
  ([index.c:3126-3135](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135)).
  For GIN that count is extracted entries, not rows: `ginHeapTupleBulkInsert` does
  `buildstate->indtuples += nentries`
  ([gininsert.c#ginHeapTupleBulkInsert](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L252-L274)),
  and `ginBuildCallback` calls it once per indexed column per heap tuple
  ([gininsert.c#ginBuildCallback](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L276-L288)),
  so the total is summed over rows *and* over columns. `ginbuild` returns it as
  `result->index_tuples`
  ([gininsert.c:418-428](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L418-L428)).
- **`ANALYZE`** overwrites every index unconditionally with `ceil(tupleFract * totalrows)`,
  and `tupleFract` is initialised to `1.0` for a plain non-partial index
  ([analyze.c:439-449](../../../../raw/postgres-17/src/backend/commands/analyze.c#L439-L449),
  [analyze.c:647-663](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663)),
  so the index inherits the *table's* row estimate.
- **`VACUUM`** *may* write the AM's `num_index_tuples`. The AM produces it in
  `vac_cleanup_one_index`
  ([vacuum.c#vac_cleanup_one_index](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2564-L2583)),
  and GIN sets it to the heap tuple count with an explicit `XXX` admitting the value is
  wrong: "we always report the heap tuple count as the number of index entries. This is
  bogus if the index is partial, but it's real hard to tell how many distinct heap entries
  are referenced by a GIN index."
  ([ginvacuum.c:733-739](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L733-L739))
  The [`pg_class`](../../../glossary.md#pg_class) write itself happens later, in `update_relstats_all_indexes`
  ([vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3072-L3099)),
  and it is **skipped entirely** when the AM's count is flagged as an estimate:
  `if (istat == NULL || istat->estimated_count) continue;`
  ([vacuumlazy.c:3086-3087](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3086-L3087)).

Measured on one 200,000-row table with 5 tags per row from a 2,000-key universe, the same
GIN index's own `reltuples` takes five values in six commands, a near 10x swing, while the
table's stays coherent:

| stage | table `reltuples` | GIN index `reltuples` |
|---|---|---|
| after `CREATE INDEX` | 200000 | **994200** |
| after `ANALYZE` | 200000 | **200000** |
| after `DELETE` 50% + `VACUUM` | 100000 | **100000** |
| after `REINDEX` | 100000 | **500000** |
| after a second plain `VACUUM` | 100000 | **500000** |
| after `VACUUM (DISABLE_PAGE_SKIPPING)` | 100000 | **100000** |

The build's 994,200 is the extracted-entry count, below 200,000 x 5 because
`ginExtractEntries` de-duplicates the keys of one value; the `ANALYZE` row is the table's
estimate; the `VACUUM` rows are the heap count.

The fifth and sixth rows are the important ones, and they are the value the index
**held before**. Because the `pg_class` write is guarded by `estimated_count`, and
`estimated_count` is true whenever the heap scan skipped a page —
`vacrel->scanned_pages < vacrel->rel_pages`
([vacuumlazy.c:2356](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2356)),
handed to the AM through `ivinfo`
([vacuumlazy.c:2481](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2481)) and
copied straight back out by GIN
([ginvacuum.c:733-739](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L733-L739)) —
VACUUM is a *conditional* writer, and on a quiet table it does not write at all: the second
plain `VACUUM` left the index at the 500000 its `REINDEX` had written, and only
`VACUUM (DISABLE_PAGE_SKIPPING)`, which forces every page to be scanned, wrote the heap
count 100000.

The table's `reltuples` is the only one of the two that means the same thing after all six
commands, which is exactly why the brief pins the denominator to it.

### What the COMMENT stores

Nine fields, all obtainable from catalogs and [`pg_stat_all_tables`](../../../glossary.md#pg_stat_all_tables). The brief mandates the
first two; each of the rest exists because a measured failure needed it.

| key | meaning | why it is there |
|---|---|---|
| `v` | payload format version | lets a later ladder change re-read old payloads |
| `ts` | UTC capture time | human triage only; never used in a comparison |
| `bis` | baseline index size, bytes | the brief's baseline physical index size |
| `bhr` | baseline table `reltuples` | the brief's baseline heap `reltuples` |
| `bfn` | baseline index `relfilenode` | detects a rebuild that did not refresh the baseline |
| `bti` | baseline `n_tup_ins` | churn gate |
| `btu` | baseline `n_tup_upd` | churn gate |
| `btd` | baseline `n_tup_del` | churn gate |
| `bac` | baseline `analyze_count + autoanalyze_count` | proves an `ANALYZE` ran since capture, so `bhr` and the current `reltuples` are comparable |

The churn and analyze counters come from `pg_stat_all_tables`
([system_views.sql#pg_stat_all_tables](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L670-L703)),
the sizes from `pg_relation_size`, and `bfn` from `pg_class.relfilenode`.

`bfn` earned its place twice in this run: `c09` (an out-of-band `REINDEX INDEX`) and edge
case E3 ([`REINDEX INDEX CONCURRENTLY`](../../../glossary.md#concurrently), which moves the comment to a new index OID) were both
diverted to `rebuilt since baseline: re-capture` ahead of every ratio.

`bac` is the guard with the least to do under this protocol, and that is itself a finding:
the maintenance step analyzes every churned table, so `cur_analyze_count > bac` holds by
construction on every fixture here, and the rung can only fire on a server where the
assumption fails. Deliberately **not** stored: the baseline `n_live_tup` / `n_dead_tup` (no
decision power that `reltuples` does not already carry), and `n_mod_since_analyze` — see
[The statistics counter you must not build the guard on](#the-statistics-counter-you-must-not-build-the-guard-on).

### The comment format

The payload is appended to whatever a human already wrote, on its own line, behind an
`@ginbase:` tag:

```text
owner: search-team
ticket: OPS-1234 {do not drop} @ 100%
@ginbase:{"v": 1, "ts": "2026-09-24T18:50:43Z", "bac": 1, "bfn": "17509", "bhr": 600000, "bis": 14778368, "btd": 0, "bti": 600000, "btu": 0}
```

Measured sizes on this run: the `@ginbase:{...}` payload is **139 bytes** on the edge-case
index, whose comment as a whole is **196 bytes** with the two-line human note above; and
**137 bytes** with a **138-byte** whole comment where there is no human note (the extra byte
is the separating newline). `pg_description.description` is `text` and TOAST-able
([pg_description.h:48-66](../../../../raw/postgres-17/src/include/catalog/pg_description.h#L48-L66)),
so size is not a constraint.

Two format rules matter:

- **The JSON must stay flat.** Both the reader and the stripper match `\{[^}]*\}`, which
  stops at the first `}`. A nested object would truncate the payload. Nine scalar fields is
  the whole design budget.
- **Anchoring on `@ginbase:` is what makes a human comment safe.** The two-line note above
  contains both `{do not drop}` and `@ 100%`, and survived capture, `REINDEX`,
  `REINDEX CONCURRENTLY`, `ALTER INDEX ... RENAME` and re-capture byte for byte, with
  exactly one payload left in the comment afterwards.

`bfn` is rendered as a JSON *string* (`"17509"` above) because `jsonb_build_object`
renders `oid` that way; the reader casts it back with `::oid`.

### SQL 1: record the baseline

Run at index creation, and again immediately after every successful rebuild. This is a
`SELECT` that *returns* the `COMMENT` statement, executed with psql's `\gexec`; when the
index is not GIN, or the table has no usable `reltuples`, it returns a `DO` block that
raises instead, so a refusal is loud rather than silent.

```sql
BEGIN;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '5s';

SELECT /* wiki_gin_capture_baseline */
       CASE
         WHEN am.amname <> 'gin' THEN
           format('DO $$ BEGIN RAISE EXCEPTION %L; END $$',
                  'not a GIN index: ' || i.indexrelid::regclass::text)
         WHEN ct.reltuples <= 0 THEN
           format('DO $$ BEGIN RAISE EXCEPTION %L; END $$',
                  'refusing baseline for ' || i.indexrelid::regclass::text ||
                  ': table reltuples is ' || ct.reltuples || ' (run ANALYZE first)')
         ELSE
           format('COMMENT ON INDEX %s IS %L',
                  i.indexrelid::regclass::text,
                  btrim(
                    btrim(regexp_replace(coalesce(obj_description(i.indexrelid, 'pg_class'), ''),
                                         '\s*@ginbase:\{[^}]*\}', '', 'g'))
                    || E'\n@ginbase:' ||
                    jsonb_build_object(
                      'v',   1,
                      'ts',  to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                      'bis', pg_relation_size(i.indexrelid),
                      'bhr', ct.reltuples::bigint,
                      'bfn', ci.relfilenode,
                      'bti', coalesce(s.n_tup_ins, 0),
                      'btu', coalesce(s.n_tup_upd, 0),
                      'btd', coalesce(s.n_tup_del, 0),
                      'bac', coalesce(s.analyze_count, 0) + coalesce(s.autoanalyze_count, 0)
                    )::text))
       END
  FROM pg_index i
  JOIN pg_class ci ON ci.oid = i.indexrelid
  JOIN pg_class ct ON ct.oid = i.indrelid
  JOIN pg_am    am ON am.oid = ci.relam
  LEFT JOIN pg_stat_all_tables s ON s.relid = i.indrelid
 WHERE i.indexrelid = 'public.orders_tags_gin'::regclass
\gexec

COMMIT;
```

The re-capture after a rebuild is the same statement. It is idempotent because the
`regexp_replace` strips any previous `@ginbase:` payload before appending the new one, which
is what satisfies the brief's "replace the `COMMENT` baseline" requirement without losing the
human text; measured, the comment carries **exactly one** payload after a capture,
a rebuild and a re-capture.

No `ANALYZE` is needed at `t0`: `CREATE INDEX` writes the *table's* `reltuples` itself, via
the same `index_update_stats` call
([index.c:3126-3131](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3131)).
Measured on an 80,000-row table: `reltuples` reads `-1` before any index exists and `80000`
straight after `CREATE INDEX`, so a baseline captured at index creation is already valid.

### SQL 2: read the baseline back

```sql
SELECT /* wiki_gin_read_baseline */
       i.indexrelid::regclass                                  AS index_name,
       b.payload->>'ts'                                        AS baseline_taken,
       (b.payload->>'bis')::bigint                             AS baseline_index_size,
       (b.payload->>'bhr')::bigint                             AS baseline_heap_reltuples,
       (b.payload->>'bfn')::oid                                AS baseline_filenode,
       (b.payload->>'bti')::bigint                             AS baseline_n_tup_ins,
       (b.payload->>'btu')::bigint                             AS baseline_n_tup_upd,
       (b.payload->>'btd')::bigint                             AS baseline_n_tup_del,
       (b.payload->>'bac')::bigint                             AS baseline_analyze_count,
       btrim(regexp_replace(coalesce(obj_description(i.indexrelid, 'pg_class'), ''),
                            '\s*@ginbase:\{[^}]*\}', '', 'g')) AS human_comment
  FROM pg_index i
  CROSS JOIN LATERAL (
       SELECT substring(coalesce(obj_description(i.indexrelid, 'pg_class'), '')
                        from '@ginbase:(\{[^}]*\})')::jsonb AS payload
  ) b
 WHERE i.indexrelid = 'public.orders_tags_gin'::regclass;
```

`obj_description(oid, 'pg_class')` reads `pg_description` for `objsubid = 0`
([system_functions.sql#obj_description](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L291-L301)).

### SQL 3 and 4: the ratios and the verdict

One statement, because the verdict is a function of the ratios and splitting them means
computing the payload twice. The three ratios the brief specifies are in the `r` lateral; the
verdict ladder is in the `v` lateral. `stats_lag` is reported but deliberately not used as a
veto.

```sql
BEGIN;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '5s';

SELECT /* wiki_gin_reindex_candidates */
       i.indexrelid::regclass                       AS index_name,
       pg_size_pretty(m.cur_index_size)             AS cur_size,
       pg_size_pretty(m.base_index_size)            AS base_size,
       m.cur_heap_reltuples::bigint                 AS cur_heap_reltuples,
       m.base_heap_reltuples,
       round(r.index_size_ratio::numeric, 4)        AS index_size_ratio,
       round(r.heap_tuple_ratio::numeric, 4)        AS heap_tuple_ratio,
       round(r.normalized_index_growth::numeric, 4) AS normalized_index_growth,
       round(r.churn_ratio::numeric, 4)             AS churn_ratio,
       round(r.stats_lag::numeric, 3)               AS stats_lag,
       v.verdict,
       CASE WHEN r.normalized_index_growth > 1
            THEN pg_size_pretty((m.cur_index_size
                                 * (1 - 1 / r.normalized_index_growth))::bigint)
       END                                          AS est_reclaimable
  FROM pg_index i
  JOIN pg_class ci ON ci.oid = i.indexrelid
  JOIN pg_class ct ON ct.oid = i.indrelid
  JOIN pg_am    am ON am.oid = ci.relam
  LEFT JOIN pg_stat_all_tables s ON s.relid = i.indrelid
  CROSS JOIN LATERAL (
        SELECT substring(coalesce(obj_description(i.indexrelid, 'pg_class'), '')
                         from '@ginbase:(\{[^}]*\})')::jsonb AS p
  ) b
  CROSS JOIN LATERAL (
        SELECT pg_relation_size(i.indexrelid)     AS cur_index_size,
               ct.reltuples                       AS cur_heap_reltuples,
               (b.p->>'bis')::bigint              AS base_index_size,
               (b.p->>'bhr')::bigint              AS base_heap_reltuples,
               (b.p->>'bfn')::oid                 AS base_filenode,
               (b.p->>'bac')::bigint              AS base_analyze_count,
               coalesce(s.analyze_count, 0)
                 + coalesce(s.autoanalyze_count, 0)             AS cur_analyze_count,
               coalesce(s.n_tup_ins, 0) - (b.p->>'bti')::bigint AS d_ins,
               coalesce(s.n_tup_upd, 0) - (b.p->>'btu')::bigint AS d_upd,
               coalesce(s.n_tup_del, 0) - (b.p->>'btd')::bigint AS d_del
  ) m
  CROSS JOIN LATERAL (
        SELECT m.cur_index_size::float8 / nullif(m.base_index_size, 0)         AS index_size_ratio,
               m.cur_heap_reltuples::float8 / nullif(m.base_heap_reltuples, 0) AS heap_tuple_ratio,
               (m.cur_index_size::float8 / nullif(m.base_index_size, 0))
                 / nullif(m.cur_heap_reltuples::float8
                          / nullif(m.base_heap_reltuples, 0), 0)               AS normalized_index_growth,
               (m.d_ins + m.d_upd + m.d_del)::float8
                 / nullif(m.base_heap_reltuples, 0)                            AS churn_ratio,
               coalesce(s.n_mod_since_analyze, 0)::float8
                 / nullif(m.cur_heap_reltuples, 0)                             AS stats_lag
  ) r
  CROSS JOIN LATERAL (
        SELECT CASE
                 WHEN b.p IS NULL                        THEN 'no baseline: capture one'
                 WHEN NOT i.indisvalid                   THEN 'invalid index: rebuild for validity, not for size'
                 WHEN ci.relfilenode <> m.base_filenode  THEN 'rebuilt since baseline: re-capture'
                 WHEN m.d_ins < 0 OR m.d_upd < 0 OR m.d_del < 0
                                                         THEN 'counters reset: re-capture'
                 WHEN m.cur_heap_reltuples <= 0          THEN 'no table statistics: ANALYZE first'
                 WHEN r.churn_ratio < 0.20               THEN 'insufficient churn: not evaluated'
                 WHEN m.cur_analyze_count <= m.base_analyze_count
                                                         THEN 'no ANALYZE since baseline: ANALYZE first'
                 WHEN r.heap_tuple_ratio <= 0.50
                      AND r.index_size_ratio >= 0.75     THEN 'strong candidate: indexed population collapsed'
                 WHEN r.normalized_index_growth >= 1.50  THEN 'candidate: disproportionate growth'
                 WHEN r.normalized_index_growth >= 1.20  THEN 'watch'
                 ELSE 'no action'
               END AS verdict
  ) v
 WHERE am.amname = 'gin'
   AND ci.relpersistence <> 't'
 ORDER BY r.normalized_index_growth DESC NULLS LAST;

COMMIT;
```

[`indisvalid`](../../../glossary.md#pg_index) is the "valid for use by queries" flag
([pg_index.h:42](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L42)); an [invalid
GIN index](../../../glossary.md#invalid-index) left by a failed `CREATE INDEX CONCURRENTLY` must be rebuilt for correctness, and
scoring its size is beside the point.

All three statements above are the statements that ran. The script's `verify` stage
re-extracts them from this page and diffs them against the files it executed: **3 of 3
identical, at 41, 18 and 76 lines.**

### The declared kind of every published column

The protocol requires every published column to be filed as a lower bound, an upper bound
or a level **before** the run, and forbids rewriting the declaration afterwards. The
script's `declare` stage writes them into their own database and refuses to run once the
fixture database exists; on the recorded run they were written at **2026-09-24T18:47:58Z**,
two seconds before the first fixture's baseline payload at **18:48:00Z**.

| Published column | Declared kind | The claim that was filed |
|---|---|---|
| `est_reclaimable` | **upper bound** | the bytes it names are never fewer than the bytes `REINDEX INDEX` returns |
| `normalized_index_growth` | level | a ranking statistic; no claim against the oracle |
| `index_size_ratio` | level | current over baseline file size |
| `heap_tuple_ratio` | level | current over baseline table `reltuples` |
| `churn_ratio` | level | write volume over baseline `reltuples` |
| `stats_lag` | level | advisory staleness reading |
| `cur_size`, `base_size` | level | the two file sizes themselves |
| `cur_heap_reltuples`, `base_heap_reltuples` | level | the two row estimates themselves |

The method also makes a **decision**, so it declares its own thresholds, and one more
number the oracle side needs:

| Knob | Filed value |
|---|---|
| `candidate` | `normalized_index_growth >= 1.50` (the brief's value) |
| `strong candidate` | `heap_tuple_ratio <= 0.50 AND index_size_ratio >= 0.75` |
| `watch` | `normalized_index_growth >= 1.20`, and **not** a flag to rebuild |
| churn gate | `churn_ratio >= 0.20`, below which the method refuses to evaluate |
| oracle justification | `truth_pct >= 33.33`, which is `100 * (1 - 1/1.50)`: the method's own candidate threshold carried to the oracle side |

Nine invariants were filed with them, so that a cross-check failure is a scored outcome and
not a discovery. I7, I8 and I9 were added on 2026-09-17 with the no-defeat rule and the
concurrency rule:

| # | Filed claim | Result |
|---|---|---|
| I1 | `index_size_ratio >= 1` on every fixture not rebuilt since its baseline | **23 of 23**, the unscored `e01` included |
| I2 | a freshly built index satisfies `n_total_pages = n_entry_pages + n_data_pages + n_pending_pages + 1` | **24 of 24** |
| I3 | the FSM free-page count never exceeds the census's new-plus-deleted count | **22 of 22** |
| I4 | `pg_relation_size` re-read after the census equals the blocks the census scanned | **22 of 22** |
| I5 | the fourth number of the `VACUUM VERBOSE` index line equals the census's new-plus-deleted count | **20 of 20** |
| I6 | `n_total_pages = 1 + census entry + data + list + new-plus-deleted` | **20 of 22**, and both exceptions are the auto-analyze stand-ins |
| I7 | the maintenance was not defeated: every settle and maintenance `VACUUM` reports 0 tuples dead but not yet removable, on every `VERBOSE` block, except the fixture that declares a held snapshot | **72 of 72** steps at score time, **75 of 75** including the published-statement replay |
| I8 | every step ran with all four settable timeouts at `0`, completed with its own command tag, and produced no skipping or cancellation line | **72 of 72** steps at score time, **75 of 75** including the replay |
| I9 | no page census saw a row in `pg_stat_progress_vacuum`, `pg_stat_progress_analyze` or `pg_stat_progress_create_index` for its relation at either end of its scan | **26 of 26** |

### The fixture corpus and its recipes

Twenty-three scored fixtures and one unscored refusal fixture, all in one database, all
disposable. Every recipe is a line of the published script, not a prose description, so a
reviewer can re-run any one of them. The int-array fixtures carry five keys per row drawn
from a 10,000-value universe by a deterministic hash.

| id | rows | index | churn recipe |
|---|---|---|---|
| c01 | 1,000,000 | `gin (tags)` | `INSERT` +50 % rows, same key universe |
| c02 | 1,000,000 | `gin (tags)` | two full-table `UPDATE`s, new keys from the same universe |
| c03 | 1,000,000 | `gin (tags)` | `DELETE` 60 % (`id % 5 < 3`) |
| c04 | 1,000,000 | `gin (tags)` | none: the control |
| c05 | 1,000,000 | `gin (tags)` | `INSERT` +100 % rows, same key universe |
| c06 | 1,000,000 | `gin (tags)` | `INSERT` +100 % rows, all-new keys |
| c09 | 1,000,000 | `gin (tags)` | full `UPDATE`, then an out-of-band `REINDEX INDEX` |
| c10 | 300,000 | `gin (doc)`, `tsvector` | rewrite every document |
| c11 | 1,000,000 | `gin (tags)` | full `UPDATE`, then `pg_stat_reset_single_table_counters()` |
| c12 | 1,000,000 | `gin (tags)` | `DELETE` the lower half of the ids, then `INSERT` 50 % fresh rows |
| p01 | 600,000 | `gin (tags) WITH (fastupdate = on)` | `INSERT` +25 % rows |
| p02 | 600,000 | `gin (tags) WITH (fastupdate = off)` | `INSERT` +25 % rows |
| m01 | 300,000 | `gin (tags)` | full `UPDATE`, measured before and after the settle and maintenance steps |
| a01 | 300,000 | `gin (tags) WITH (fastupdate = on)` | `INSERT` 40,000 rows; maintained by the auto-analyze stand-in |
| a02 | 300,000 | `gin (tags) WITH (fastupdate = on)` | `INSERT` 60,500 rows; same stand-in |
| s01 | 1,000,000 | `gin (tags)`, one key per 100,000 rows | `DELETE` the lower half of the ids, with a repeatable-read snapshot held across the settling `VACUUM` |
| o01 | 300,000 | `gin (j jsonb_path_ops)` | rewrite every document |
| o02 | 100,000 | `gin (txt gin_trgm_ops)` | rewrite every document |
| o03 | 300,000 | `gin (n)`, [`btree_gin`](../../../glossary.md#btree_gin-and-btree_gist) `int4_ops` | `UPDATE` every row's key |
| x01 | 300,000 | [partial](../../../glossary.md#partial-index) `gin (tags) WHERE id % 4 = 0` | full `UPDATE` |
| x02 | 300,000 | two-column `gin (tags, tags2)` | full `UPDATE` of `tags` |
| x03 | 300,000 | [expression](../../../glossary.md#expression-index) `gin ((tags[1:3]))` | full `UPDATE` |
| k01 | 300,000 | `gin (tags)`, one key per 100 rows | `DELETE` the lower half of the ids, retiring 1,500 keys |
| e01 | 0 | `gin (tags)` | none; unscored, because the capture refuses it |

`e01` is the empty fixture and the only one the capture statement declines:
`refusing baseline for f_e01_gin: table reltuples is 0 (run ANALYZE first)`. Its decide row
is therefore `no baseline: capture one`, with every ratio null.

### The phases every fixture ran

| Phase | What the script does | What it records |
|---|---|---|
| build | create, load, create the index, `VACUUM (VERBOSE, ANALYZE)` | the as-built file size, the metapage row, the catalog row and the statistics counters |
| baseline | run statement 1 against that index | the `@ginbase:` payload, byte for byte |
| churn | the recipe's writes, [`pg_stat_force_next_flush()`](../../../glossary.md#cumulative-statistics), the settle `VACUUM (VERBOSE)`, then the maintenance `VACUUM (VERBOSE, ANALYZE)` | a reading after the writes, after the settle step and after the maintenance step |
| decide | statement 3, verbatim, in one transaction holding `SHARE ROW EXCLUSIVE` on all 24 fixture tables | every published column, per fixture |
| oracle | `REINDEX INDEX` at a recorded `maintenance_work_mem`, bracketed by `pg_relation_size(index, 'main')` | the two sizes and `truth_pct` |

The settle step is proven rather than assumed: `n_pending_pages` read **0 on all 23 scored
fixtures** at the decide phase — after the settle step on the 21 that have one, and after
the stand-in's own flush on `a01` and `a02` — and the `VACUUM VERBOSE` index line is filed
for each. The two auto-analyze stand-ins do not claim the settle step; see
[The auto-analyze window, and why the method almost never sees it](#the-auto-analyze-window-and-why-the-method-almost-never-sees-it).

Every `VACUUM` and `ANALYZE` in that table — the build settle, the churn settle, the
maintenance step, the stand-ins and the census — runs in a
session with all four settable timeouts at `0`, and each is scored against the rule's four
proofs before any fixture is scored at all; see
[The maintenance was not defeated](#the-maintenance-was-not-defeated). The settle step is
also the one phase boundary that can *add* bytes; see
[What the settle step itself cost](#what-the-settle-step-itself-cost).

### The 23 scored fixtures and their results

`decide` is the file size the method saw, `rebuilt` the size after the oracle's
`REINDEX INDEX`, `truth` its returned percentage, `norm` the unrounded
`normalized_index_growth`, `pred` the `100 * (1 - 1/norm)` the method's `est_reclaimable`
is built from, and `err` the prediction's error in points. `bound` is the verdict on the
declared upper bound.

| id | verdict | decide | rebuilt | truth | norm | pred | err | bound | score |
|---|---|---|---|---|---|---|---|---|---|
| a01 | insufficient churn: not evaluated | 12,197,888 | 9,084,928 | 25.52 | 1.3191 | 24.19 | −1.33 | VIOLATED | refused, nothing to reclaim |
| a02 | watch | 12,378,112 | 9,568,256 | 22.70 | 1.2625 | 20.79 | −1.91 | VIOLATED | PASS |
| c01 | no action | 33,890,304 | 29,974,528 | 11.55 | 1.0114 | 1.12 | −10.43 | VIOLATED | PASS |
| c02 | candidate | 123,592,704 | 22,331,392 | 81.93 | 5.5391 | 81.95 | +0.02 | HELD | PASS |
| c03 | strong candidate | 22,339,584 | 9,691,136 | 56.62 | 2.5000 | 60.00 | +3.38 | HELD | PASS |
| c04 | insufficient churn: not evaluated | 22,339,584 | 22,339,584 | 0.00 | 1.0000 | — | — | not published | refused, nothing to reclaim |
| c05 | candidate | 85,712,896 | 59,613,184 | 30.45 | 1.9184 | 47.87 | +17.42 | HELD | **FALSE POSITIVE** |
| c06 | no action | 47,808,512 | 44,654,592 | 6.60 | 1.0700 | 6.55 | −0.05 | VIOLATED | PASS |
| c09 | rebuilt since baseline: re-capture | 22,331,392 | 22,331,392 | 0.00 | 0.9996 | — | — | not published | refused, nothing to reclaim |
| c10 | candidate | 18,997,248 | 8,437,760 | 55.58 | 2.2515 | 55.58 | 0.00 | HELD | PASS |
| c11 | counters reset: re-capture | 85,712,896 | 22,331,392 | 73.95 | 3.8368 | 73.94 | −0.01 | VIOLATED | refused, **a real candidate** |
| c12 | candidate | 33,890,304 | 22,339,584 | 34.08 | 1.5171 | 34.08 | 0.00 | HELD | PASS |
| k01 | strong candidate | 778,240 | 393,216 | 49.47 | 2.0000 | 50.00 | +0.53 | HELD | PASS |
| m01 | candidate | 19,505,152 | 8,159,232 | 58.17 | 2.3906 | 58.17 | 0.00 | HELD | PASS |
| o01 | candidate | 20,135,936 | 8,257,536 | 58.99 | 2.4385 | 58.99 | 0.00 | HELD | PASS |
| o02 | candidate | 20,701,184 | 4,825,088 | 76.69 | 4.2903 | 76.69 | 0.00 | HELD | PASS |
| o03 | candidate | 6,512,640 | 2,285,568 | 64.91 | 2.8495 | 64.91 | 0.00 | HELD | PASS |
| p01 | no action | 18,997,248 | 17,883,136 | 5.86 | 1.0284 | 2.76 | −3.10 | VIOLATED | PASS |
| p02 | no action | 14,778,368 | 17,883,136 | **−21.01** | 0.8000 | — | — | not published | PASS |
| s01 | strong candidate | 1,245,184 | 630,784 | 49.34 | 2.0000 | 50.00 | +0.66 | HELD | PASS |
| x01 | candidate | 7,471,104 | 2,334,720 | 68.75 | 3.6480 | 72.59 | +3.84 | HELD | PASS |
| x02 | candidate | 21,446,656 | 10,534,912 | 50.88 | 2.0358 | 50.88 | 0.00 | HELD | PASS |
| x03 | candidate | 9,994,240 | 5,464,064 | 45.33 | 1.8263 | 45.25 | −0.08 | VIOLATED | PASS |

Totals: **18 `PASS`, 1 `FALSE POSITIVE`, 0 `FALSE NEGATIVE`, 4 refusals** (three with
nothing worth reclaiming, one — `c11` — hiding a genuine 73.95 % candidate behind a
deliberately conservative counter-reset rung).

Two rows deserve reading twice:

- **`c05` is the only false positive**, and it is a threshold artefact rather than a wrong
  reading: the method flagged an index whose rebuild returned 30.45 %, against the 33.33 %
  this page declared as the point where a rebuild pays. Its `norm` of 1.9184 predicted
  47.87 %, a 17.42-point over-prediction, and the reason is
  [the posting-tree conversion](#first-failure-a-fresh-gin-build-is-not-linear-in-heap-tuples):
  `c05` doubled a 1,000,000-row table, and the fresh 2,000,000-row build is 2.67x the
  1,000,000-row baseline rather than 2x.
- **`p02` returned negative bytes.** Its file never grew, and its rebuild is 3,104,768
  bytes *larger* than the churned index. The method read `norm` 0.8000, printed no
  `est_reclaimable` at all because the column is gated on `norm > 1`, and said
  `no action` — the right answer, reached without any way of knowing why.

### The declared upper bound failed, so est_reclaimable is a level

`est_reclaimable` was declared an upper bound. Scored against the oracle on the 20
fixtures that published it:

| Verdict | Count | Fixtures |
|---|---|---|
| HELD | **13** | c02, c03, c05, c10, c12, k01, m01, o01, o02, o03, s01, x01, x02 |
| VIOLATED | **7** | a01 (−1.33), a02 (−1.91), c01 (−10.43), c06 (−0.05), c11 (−0.01), p01 (−3.10), x03 (−0.08) |
| not published | 3 | c04, c09, p02, where `norm <= 1` |

The violations are all under-predictions, they range from 0.01 to 10.43 points, and four of
the seven are under 2 points. That pattern matters: the bound does not fail because the
model is wildly wrong, it fails because the model is an *estimate* that lands on both sides
of the truth, and an estimate cannot be a bound. The protocol's rule is that a violated
bound is corrected in the method or demoted to a level, and a catalogs-only method has
nothing to correct with — the missing quantity is the size of a rebuild, which is what the
oracle exists to measure.

The model makes the failure exact. Statement 3 computes `est_reclaimable` as
`cur_size * (1 - 1/normalized_index_growth)`, and `normalized_index_growth` is
`index_size_ratio / heap_tuple_ratio`, so the column reduces to
`cur_size - base_size * heap_tuple_ratio`. The model's implied rebuilt size is therefore
the baseline size scaled by the table's row ratio, and the bound holds exactly when that
implied size is no larger than the real rebuilt size. `c01` shows the failing direction:
`22,339,584 * 1.5` is 33,509,376, and its rebuild came to 29,974,528, so the bound was
violated. `c05` shows the other: `22,339,584 * 2.0` is 44,679,168, against a rebuild of
59,613,184, so it held.

**`c02` keeps moving the count, and how it moves is the strongest argument for the
demotion.** For `c02` the condition works out to `22,339,584 * reltuples / 1,000,000 <=
22,331,392`, that is `reltuples <= 999,633`. The fixture itself never changes: its decide
size (123,592,704), its rebuilt size (22,331,392), its `truth` of 81.93 % and its
`index_size_ratio` of 5.5325 are identical on every run. What moves is the table's
`reltuples`, which `ANALYZE` writes from a sample, against an unchanged population of
exactly 1,000,000 rows:

| run | `reltuples` | verdict |
|---|---|---|
| 2026-09-15 | not recorded on the page | `HELD`, +0.01 |
| 2026-09-17, first | 1,001,633 | `VIOLATED`, −0.03 |
| 2026-09-17, second | 1,000,533 | `VIOLATED`, −0.01 |
| 2026-09-24, the filed script unchanged | 999,533 | `HELD`, 0.00 |
| 2026-09-24, first pass of the edited script | 1,001,107 | `VIOLATED`, −0.03 |
| 2026-09-24, second pass, from the built tree | 1,000,833 | `VIOLATED`, −0.02 |
| 2026-09-24, the recorded run | 998,807 | `HELD`, +0.02 |

A bound whose verdict is decided by a few hundred rows of sampling noise in its own input is
not a bound in any useful sense; see
[Third failure](#third-failure-the-denominator-is-a-sample-and-the-baseline-is-not).

**So this page demotes `est_reclaimable` to a level.** The statement still prints it,
because deleting a column would change the text that was scored, and the reading rule is
now explicit:

- `est_reclaimable` is a **ranking hint**, not reclaimable space, and must not be quoted to
  anyone as bytes that will come back.
- The only number on this page that *is* reclaimable space is the oracle's own
  `truth`, measured by rebuilding.
- The recomputation used for scoring matched the statement's own `pg_size_pretty` output on
  **23 of 23** fixtures, so the demotion is about the model, not about a reporting bug.

### How close the prediction came

Over the 20 fixtures whose `norm` exceeded 1:

| Accuracy band | Count | Fixtures |
|---|---|---|
| within 0.05 points | **10** | c02, c06, c10, c11, c12, m01, o01, o02, o03, x02 |
| within 3.5 points | **17** | the ten above plus a01, a02, c03, k01, p01, s01, x03 |
| over-predicts by more than 3.5 | 2 | c05 (+17.42), x01 (+3.84) |
| under-predicts by more than 3.5 | 1 | c01 (−10.43) |

Ten of 20 within 0.05 points is not luck, and the reason is instructive: in c02, c10, c11,
c12, m01, o01, o02, o03 and x02 the population is unchanged, so `norm` is
`index_size_ratio` up to the sampling error in `reltuples`, and a rebuild over an unchanged
row set returns the index to almost exactly its baseline — c10 to 8,437,760 against a
baseline of 8,437,760, m01 to 8,159,232 against 8,159,232, o01 to 8,257,536 against
8,257,536, x02 to 10,534,912 against 10,534,912. When the row count and the key
distribution are unchanged, a fresh GIN build is byte-reproducible, and the model is then
not an estimate but an identity — up to that sampling error, which is exactly what costs
`c02` its bound. The tenth, `c06`, is the one case where the population *doubled* and the
prediction still landed within 0.05 points, because doubling the key universe alongside the
rows kept the build proportional — which is exactly the condition `heap_tuple_ratio`
silently assumes.

The misses are all fixtures where the population changed or the pending list moved, which
is the opposite of what a normalizer is supposed to buy you, and is the most important
caveat on this page.

### First failure: a fresh GIN build is not linear in heap tuples

Rebuilding the same index over a growing table with the same 10,000-key universe, at
`maintenance_work_mem = 256MB`:

| rows | fresh build bytes | pages | `n_entry_pages` | `n_data_pages` | `n_entries` |
|---|---|---|---|---|---|
| 250,000 | 6,938,624 | 847 | 846 | 0 | 10,000 |
| 500,000 | 12,599,296 | 1,538 | 1,537 | 0 | 10,000 |
| 1,000,000 | 22,339,584 | 2,727 | 2,726 | 0 | 10,000 |
| 2,000,000 | **59,613,184** | 7,277 | 1,904 | **5,372** | 10,000 |
| 4,000,000 | 82,264,064 | 10,042 | 53 | 9,988 | 10,000 |
| 8,000,000 | 245,768,192 | 30,001 | 50 | 29,950 | 10,000 |

Doubling the rows multiplies the build by 1.82x, 1.77x, **2.67x**, **1.38x** and 2.99x in
turn. The 2.67x step is the posting-tree conversion arriving: at 1,000,000 rows every key's
TIDs still fit inside its entry tuple (0 data pages, 2,726 entry pages), at 2,000,000 rows
5,372 data pages exist beside 1,904 entry pages, and at 4,000,000 rows the entry tree has
collapsed to 53 pages against 9,988 data pages — one posting tree per key, with `n_entries`
pinned at 10,000 throughout.

The mechanism is in the build path. GIN keeps a key's TIDs as a compressed posting list inside
the entry tuple while it fits in `GinMaxItemSize`, and converts to a posting tree when it does
not
([gininsert.c#buildFreshLeafTuple](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L125-L166),
[gininsert.c#addItemPointersToLeafTuple](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L45-L111)).
The conversion is per key and is a step, not a slope.

Consequence for the heuristic: dividing by `heap_tuple_ratio` assumes the denominator tracks
what a fresh build would cost. Across a posting-tree conversion it does not, in either
direction. `c05` is this failure — `norm` 1.9184 predicted 47.87 % against a measured
30.45 %. `c06` escapes it, and predicts to within 0.05 points, precisely because doubling the
*key* universe alongside the rows kept the growth proportional.

### Second failure: the pending-list high-water mark

Two identical 600,000-row tables, one index with `fastupdate = on` and one with
`fastupdate = off` — the default is `true` both in the access method
([gin_private.h:33](../../../../raw/postgres-17/src/include/access/gin_private.h#L33)) and in the
[reloption](../../../glossary.md#storage-parameter) table
([reloptions.c:123-131](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L123-L131))
— then 150,000 rows inserted into both:

| stage | `p01`, `fastupdate = on` | `p02`, `fastupdate = off` |
|---|---|---|
| baseline | 14,778,368 | 14,778,368 |
| after +150,000 inserts, before the settle step | **18,997,248** (307 pending pages) | **14,778,368** (0 pending pages) |
| after the settle and maintenance steps | 18,997,248 (0 pending pages) | 14,778,368 |
| census: deleted pages / FSM free pages | **515 / 515** | 0 / 0 |
| after `REINDEX INDEX` | 17,883,136 | **17,883,136** |
| the method said | `no action`, `norm` 1.0284 | `no action`, `norm` 0.8000 |
| the oracle returned | 5.86 % | **−21.01 %** |

With `fastupdate = off`, 150,000 new rows fit in existing page slack and the file did not grow
by one byte. With `fastupdate = on` the file grew 515 pages — 4,218,880 bytes, against a 4 MB
default `gin_pending_list_limit` — the settle step merged the list into the main structure, and
all 515 pages went to the free space map and stayed in the file, where the census and the FSM
agree on them exactly.

Two things follow that the old version of this page had wrong:

- **The pending list's high-water mark is bounded by `gin_pending_list_limit`, and the bound
  is enforced during the inserts, not at the end.** `ginfast.c` compares
  `metadata->nPendingPages * GIN_PAGE_FREESIZE` against `GinGetPendingListCleanupSize(index) * 1024`
  and, when it is over, calls `ginInsertCleanup` in the foreground
  ([ginfast.c:458-471](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L458-L471)),
  where `GIN_PAGE_FREESIZE` is `BLCKSZ - MAXALIGN(SizeOfPageHeaderData) - MAXALIGN(sizeof(GinPageOpaqueData))`
  ([ginfast.c:41-42](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L41-L42)),
  which is 8,160 bytes at [`block_size`](../../../glossary.md#blcksz) 8192. So the flush fires at the first page count above
  `4096 * 1024 / 8160 = 513.9`, i.e. at 514 pending pages — and `p01` ends with 307 pending
  pages *after* such a flush and 515 deleted ones, while `a02` ends with 514 deleted pages
  from the same mechanism.
- **A rebuild does not always return those bytes; sometimes it costs more.** Both twins
  rebuild to the same 17,883,136 bytes, which is larger than either churned file, because a
  bulk build at `maintenance_work_mem = 256MB` flushes its accumulator in rounds and each
  round appends
  ([gininsert.c:290-291](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L290-L291)),
  where incremental insertion had packed the same entries denser.

On a 14 MB index the 4 MB limit is a quarter of the file and the heuristic cannot see it; on a
1 GB index it is 0.4 % and does not matter. GIN's own documentation describes the pending list
and its limit
([gin.sgml#gin-fast-update](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L500-L537),
[gin.sgml#guc-gin-pending-list-limit](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L595-L616));
the recycling of flushed pending pages into the FSM is
[ginfast.c:1015-1020](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1015-L1020).

### Third failure: the denominator is a sample and the baseline is not

`normalized_index_growth` divides one exactly-counted number by one estimated one, and the
brief cannot avoid it. The baseline `bhr` is captured right after a build, where
`CREATE INDEX` writes the *real* heap tuple count its own scan produced
([index.c:3126-3131](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3131)).
Every later reading of the same column is whatever the last `ANALYZE` extrapolated from its
sample: `acquire_sample_rows` scales the live rows it saw by the block ratio
([analyze.c#sample-extrapolation](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1278-L1289)),
and `do_analyze_rel` writes that number into `pg_class`
([analyze.c#table-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L637-L645)).
So `heap_tuple_ratio` is an exact count in the denominator of the baseline and an estimate
in the numerator of today, and the protocol's own maintenance step is what guarantees the
estimate is fresh.

Whether a reading is a sample depends on the table's size. `ANALYZE` reads at most as many
blocks as it wants sample rows: 300 times the statistics target, which defaults to 100, so
30,000
([analyze.c:488-513](../../../../raw/postgres-17/src/backend/commands/analyze.c#L488-L513),
[analyze.c:1851-1853](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1851-L1853),
[analyze.c:1894](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1894),
[guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2070-L2079)).
It picks those blocks at random with a fresh seed each time, and a table with fewer blocks
than that is read whole
([analyze.c:1180-1187](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1180-L1187),
[sampling.c#BlockSampler_Init](../../../../raw/postgres-17/src/backend/utils/misc/sampling.c#L23-L55)).
The recorded run's maintenance `VERBOSE` output shows the split. It prints a line for 22 of
the fixture tables, and 21 of them were read whole and counted exactly; `c05`'s 20,619
pages gave 2,000,000 rows. The two stand-ins' `ANALYZE` is not `VERBOSE`, but their counts,
340,000 and 360,500, are exact too. `c02` is the exception: its two full-table `UPDATE`s
left it at 30,928 pages, and its line reads `scanned 30000 of 30928 pages, containing
968838 live rows`. That extrapolates to 998,807, the recorded run's reading in the
[`c02` table](#the-declared-upper-bound-failed-so-est_reclaimable-is-a-level). That is why
`c02` is the only fixture whose verdict moves between runs.

Measured on a 1,000,000-row table churned exactly like `c02` — two full-table `UPDATE`s,
then the maintenance `VACUUM (ANALYZE)` — with four further `ANALYZE`s on the unchanged
table, on the recorded run:

| reading | `pg_class.reltuples` | error against the true 1,000,000 rows |
|---|---|---|
| after the maintenance `VACUUM (ANALYZE)` | 998,833 | −0.1167 % |
| `ANALYZE` again | 998,933 | −0.1067 % |
| `ANALYZE` again | 1,000,733 | +0.0730 % |
| `ANALYZE` again | 999,575 | −0.0425 % |
| `ANALYZE` again | 1,000,833 | +0.0830 % |

Five readings, five different numbers, none of them the row count, three low and two high,
with a spread of 0.20 points between two readings of the same unchanged table. The error
has no fixed sign. The probe has now run in five passes on this page, 25 readings in all:
18 came out high and 7 low, from −0.18 % to +0.36 %. The 2026-09-17 pass read five high
values, and this page then called the error one-directional; the later passes show it is
not. Why the readings lean high is open; see [Open Questions](#open-questions).

Consequences for the method, in order of how much they matter:

- **The error moves `normalized_index_growth` both ways.** A high reading pushes it down,
  toward `no action`, and a low one pushes it up, toward a flag. The size is a few tenths of
  a percent, so it matters only near a threshold or a bound.
- **At a threshold or a bound boundary, it decides the answer.** `c02`'s upper-bound verdict
  sits within 0.03 points of the line, so the sample decides it: three `HELD` and four
  `VIOLATED` over seven runs, with the fixture, the oracle and `index_size_ratio`
  byte-identical throughout; see
  [The declared upper bound failed](#the-declared-upper-bound-failed-so-est_reclaimable-is-a-level).
- **It is not a reason to use the index's own `reltuples` instead.** That column swings by
  nearly 10x across ordinary commands; see
  [Why the baseline must not use the GIN index's own reltuples](#why-the-baseline-must-not-use-the-gin-indexs-own-reltuples).
  A sampling error of a few tenths of a percent is the price of the only coherent
  denominator available.

### The baseline itself depends on maintenance_work_mem

The same 2,000,000-row index, rebuilt three times at three settings:

| `maintenance_work_mem` | fresh build bytes | pages | `n_entry_pages` | `n_data_pages` | identity |
|---|---|---|---|---|---|
| 64MB | **71,737,344** | 8,757 | 3,384 | 5,372 | exact |
| 256MB | 59,613,184 | 7,277 | 1,904 | 5,372 | exact |
| 1GB | 59,613,184 | 7,277 | 1,904 | 5,372 | exact |

A build at 64MB is **20.3 % larger** than the same build at 256MB, and 256MB and 1GB agree to
the byte. The setting is not incidental to the build: `ginBuildCallback` dumps its accumulator
to the index whenever `buildstate->accum.allocatedMemory >= (Size) maintenance_work_mem * 1024L`
([gininsert.c:290-291](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L290-L291)),
so the budget decides how many flush rounds a build takes, and each round appends to the entry
and posting structures independently. The 64MB build shows it in the shape as well as the size:
3,384 entry pages against 1,904 for the same 10,000 keys and the identical 5,372 data pages.

The declared invariant I2 — `n_total_pages = n_entry_pages + n_data_pages + n_pending_pages + 1`,
the `+ 1` being the metapage that `ginvacuumcleanup` skips by starting its loop at
`GIN_ROOT_BLKNO`
([ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L694-L803))
— is **exact on all nine probe builds and all 24 fixture baselines**, including the 64MB row.
That settles the internal inconsistency this page used to carry as an open question: the
earlier 64MB reading was off by one page, and it does not reproduce.

Since `bis` is captured right after a build, the baseline inherits whatever
`maintenance_work_mem` that build ran with, and a later rebuild under a different setting will
not return to it. The same-version documentation warns that "Build time for a GIN index is very
sensitive to the `maintenance_work_mem` setting"
([gin.sgml#guc-maintenance-work-mem](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L584-L593));
the measured *size* sensitivity is the part that matters here.

Practical rule: capture the baseline in the same session, and with the same
`maintenance_work_mem`, as the build that produced it, and use that same setting for the
rebuild. `maintenance_work_mem` is `PGC_USERSET`
([guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2466-L2474)),
so this is session/transaction scope — no reload, no restart.

### The maintenance pair: what the settle step and the maintenance step move

`m01` is the protocol's maintenance pair: one fixture, one full-table `UPDATE`, measured
after the writes and again after the settle and maintenance steps.

| reading | file size | metapage total / entry / pending | census entry / list / deleted | FSM free | index `relpages` |
|---|---|---|---|---|---|
| baseline | 8,159,232 | 996 / 995 / 0 | — | — | 996 |
| after the writes, before the settle step | 19,505,152 | **996 / 995 / 99** | 1,865 / 99 / 416 | 416 | **996** |
| after the settle step | 19,505,152 | **2,381 / 1,946 / 0** | — | — | **2,381** |
| after the maintenance step | 19,505,152 | 2,381 / 1,946 / 0 | 1,946 / 0 / 434 | 434 | 2,381 |
| after the oracle's rebuild | 8,159,232 | 996 / 995 / 0 | — | — | 996 |

Three readings come out of that table:

- **The settle step moved no bytes and changed every count.** The file is 19,505,152 bytes at
  all three points, but before it the metapage still described a 996-page index while the file
  held 2,381 blocks, and 99 live `list` pages existed that the metapage's page counts do not
  bucket at all. This is why the protocol forbids handing a method the pre-settle state: a
  size-only method reads the same number, but anything reading the metapage reads the
  as-built index.
- **The `ANALYZE` half of the maintenance step moved no page**, exactly as the protocol says
  it cannot: `vacuum()` vacuums each relation and then analyzes it
  ([vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650)),
  and `analyze_rel` enters the index AM's ANALYZE-only cleanup only when the command is not a
  `VACUUM ANALYZE`
  ([analyze.c#analyze-only-cleanup](../../../../raw/postgres-17/src/backend/commands/analyze.c#L694-L721)).
- **What did move in the catalog is the measured index's own row.** `relpages` went 996 ->
  2,381 across the settle step, written by `update_relstats_all_indexes`
  ([vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3072-L3099)),
  and the rebuild wrote it back to 996 while setting the index's `reltuples` to 1,498,260 —
  the extracted-entry count, not a row count.

The 416 deleted pages already present before the settle step are the foreground pending-list
flush described above; the settle step turned the remaining 99 into 18 more.

### The auto-analyze window, and why the method almost never sees it

On a GIN index an auto-analyze is not a statistics-only event: a worker's bare `ANALYZE`
reaches `ginvacuumcleanup` with `analyze_only` set and, because the caller is an autovacuum
worker, flushes the pending list and returns before the page census
([ginvacuum.c#analyze_only-worker](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L709-L717)),
while the same call from any other backend returns at once. The protocol's stand-in for that
state is `ANALYZE` **plus** `gin_clean_pending_list()`, and `a01` and `a02` are built on it.
`gin_clean_pending_list` returns its own count of deleted pending pages
([ginfast.c:1090](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1090)).

| | `a01` | `a02` |
|---|---|---|
| rows inserted onto a 300,000-row table | 40,000 | 60,500 |
| `n_mod_since_analyze` at the end of the writes | 40,000 | 60,500 |
| the launcher's analyze threshold, `50 + 0.1 * reltuples` | 30,050 — crossed | 30,050 — crossed |
| the launcher's insert-vacuum threshold, `1000 + 0.2 * reltuples` | 61,000 — not crossed | 61,000 — not crossed |
| pending pages the stand-in flushed | **493** | **232** |
| census deleted pages afterwards | 493 | **514** |
| metapage `n_total_pages` against the real file | 996 against 1,489 blocks | 996 against 1,511 blocks |
| the method's `churn_ratio` | 0.1333 | **0.2017** |
| the method said | `insufficient churn: not evaluated` | `watch`, `norm` 1.2625 |
| the oracle returned | 25.52 % | 22.70 % |

Two findings, and the second is the sharper one:

- **A stand-in fixture carries stale metapage counts by construction**, which the protocol
  states in advance and this run measures: neither the worker's flush nor
  `gin_clean_pending_list` reaches `ginUpdateStats`, so `a01` and `a02` are the only two
  fixtures that fail invariant I6, and `a02` is additionally off by one *entry* page (996
  recorded, 996 counted, 514 deleted and one entry page the flush allocated that the metapage
  never learned about). Both are excluded from the settle-step claim, as the protocol requires.
- **The window in which an auto-analyze-only maintained table can be evaluated at all is
  1,001 rows wide.** To be maintained by auto-analyze alone, inserts `I` must satisfy
  `I > 50 + 0.1 N` (the analyze verdict) and `I <= 1000 + 0.2 N` (staying under the
  insert-vacuum verdict), and both tests are strictly-greater comparisons against effective
  per-table values
  ([autovacuum.c#vacthresh-anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3074-L3076),
  [autovacuum.c#verdicts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095)).
  The method's own churn gate needs `I >= 0.2 N`. The overlap is
  `0.2 N <= I <= 0.2 N + 1000` — one thousand rows, whatever `N` is. `a01` sits below it and is
  refused; `a02` sits inside it by 500 rows and is evaluated. On any real table, an
  insert-only workload maintained by auto-analyze alone is therefore almost always refused by
  this method's churn gate, and the refusal is not wrong so much as structural.

### A snapshot held across the settling VACUUM

`s01` holds a repeatable-read snapshot open across its settle step. Its ten keys of 100,000
rows each make every key a posting tree, so deleting the lower half of the ids empties whole
data pages. The engine's own `VACUUM VERBOSE` index lines, in order:

```text
index "f_s01_gin": pages: 152 in total, 0 newly deleted, 0 currently deleted, 0 reusable
index "f_s01_gin": pages: 152 in total, 60 newly deleted, 60 currently deleted, 0 reusable
index "f_s01_gin": pages: 152 in total, 0 newly deleted, 0 currently deleted, 60 reusable
```

Three `VACUUM`s, three different answers, and none of them is the one a single-pass fixture
would have recorded:

1. **With the snapshot held, the settling `VACUUM` deleted nothing at all.** It could not:
   `vacuum_get_cutoffs` takes `OldestXmin` from `GetOldestNonRemovableTransactionId(rel)`
   ([vacuum.c:1120](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1120)), the
   holder's snapshot keeps the deleted heap tuples non-removable, so no index TID is deletable
   and no posting-tree page empties. The page census taken inside that state reads 140 data
   [leaves](../../../glossary.md#leaf-page), 0 deleted pages and 0 FSM-free pages. That `VACUUM`'s own `VERBOSE` output says
   so in one number: **500,000 tuples dead but not yet removable**, exactly the rows the
   churn deleted, beside a horizon reading naming one holder — `type=client backend
   state=active xmin=1075`, with no `backend_xid` at all, because the holder only ever read.
   The two later `VACUUM`s report **0**. This is the fixture's whole point, and it is the
   one step of the run that
   [The maintenance was not defeated](#the-maintenance-was-not-defeated) declares rather
   than forbids.
2. **With the holder gone, the second `VACUUM` deleted 60 pages and freed none of them.** The
   census reads 80 data leaves and 60 deleted pages, all 60 carrying a delete xid, and the FSM
   still holds nothing: `GinPageIsRecyclable` accepts a deleted page only once
   `GlobalVisCheckRemovableXid` has moved past its delete xid
   ([ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829)).
3. **The maintenance `VACUUM` recycled them**: 60 reusable pages, the FSM count moves to 60,
   and the metapage's `n_data_pages` falls 150 -> 90.

The file never changed size through any of it — 1,245,184 bytes at every phase — and the
rebuild returned 49.34 %. A method that reads only `pg_relation_size` is blind to all three
states, which is the honest limit of this heuristic, and the protocol's rule that more than
one `VACUUM` is normal is here measured rather than assumed.

### Keys that no longer occur

`k01` stores one key per 100 contiguous rows and then deletes the lower half of the ids,
retiring 1,500 of its 3,001 keys outright.

| reading | file size | `n_entries` | `n_entry_pages` |
|---|---|---|---|
| baseline | 778,240 | 3,001 | 94 |
| after the writes | 778,240 | 3,001 | 94 |
| after the settle step | 778,240 | 3,001 | 94 |
| after the maintenance step | 778,240 | 3,001 | 94 |
| after the oracle's rebuild | **393,216** | **1,501** | **47** |

The entry count does not move, because VACUUM removes deletable TIDs from posting lists and
deletes emptied posting-tree pages but never deletes a tuple or a page from the entry tree
([README#page-deletion](../../../../raw/postgres-17/src/backend/access/gin/README#L389-L396)).
Half the entry tree is dead weight that only a rebuild removes, and the method — which sees a
file that never changed size and a table whose `reltuples` halved — reached
`strong candidate: indexed population collapsed` and was right: the rebuild returned 49.47 %.

### The verdict ladder, in order

Order is load-bearing.

1. `no baseline: capture one`
2. `invalid index: rebuild for validity, not for size`
3. `rebuilt since baseline: re-capture` — `relfilenode <> bfn`
4. `counters reset: re-capture` — any of the three churn deltas is negative
5. `no table statistics: ANALYZE first` — `reltuples <= 0`
6. `insufficient churn: not evaluated` — `churn_ratio < 0.20`
7. `no ANALYZE since baseline: ANALYZE first`
8. `strong candidate: indexed population collapsed`
9. `candidate: disproportionate growth` — `normalized_index_growth >= 1.50`
10. `watch` — `normalized_index_growth >= 1.20`
11. `no action`

Which rungs this run exercised, and which it cannot:

| Rung | Exercised by | Note |
|---|---|---|
| 1 | `e01` | the empty fixture, whose capture the statement refuses |
| 2 | nothing | still source-justified from `indisvalid` only |
| 3 | `c09`, and edge case E3 | both times ahead of the churn gate |
| 4 | `c11` | would have been a correct `candidate` on a fresh baseline |
| 5 | nothing | `e01` reaches rung 1 first, and every other fixture is analyzed |
| 6 | `a01`, `c04` | 0.1333 and 0.0000 |
| 7 | **nothing, and it cannot be reached** | the maintenance step analyzes every churned table, so `cur_analyze_count > bac` always holds here |
| 8 | `c03`, `k01`, `s01` | all three correct, 56.62 / 49.47 / 49.34 % |
| 9 | 11 fixtures | one of them, `c05`, is the run's only false positive |
| 10 | `a02` | 22.70 %, below the declared payoff threshold |
| 11 | `c01`, `c06`, `p01`, `p02` | 11.55 / 6.60 / 5.86 / −21.01 % |

Rung 7 is the interesting absence. It exists to catch a table whose `reltuples` predates the
churn, and under the protocol's maintenance assumption that state cannot occur — so the guard
is now insurance against a server that does not maintain its tables, not something this page
can score. The same is true of `stats_lag`, which read **0.000 on all 23 fixtures** because the
maintenance `ANALYZE` zeroes `mod_since_analyze`
([pgstat_relation.c:331-337](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L331-L337)).

### Why the shrinkage rule can never fire on its own

The brief's strong-candidate rule is `heap_tuple_ratio <= 0.50 AND index_size_ratio >= 0.75`.
On GIN the second clause is always true, because the file never shrinks without a rebuild
([ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L694-L803)),
and a rebuild is caught one rung higher by the `relfilenode` test. So the rule collapses to
`heap_tuple_ratio <= 0.50`, and with `index_size_ratio >= 1`:

```text
normalized_index_growth = index_size_ratio / heap_tuple_ratio >= 1 / 0.50 = 2.00
```

Every input that satisfies the shrinkage rule already satisfies `normalized_index_growth >= 1.50`
with margin to spare. Using the 80% variant of the threshold changes nothing:
`0.80 / 0.50 = 1.60`, still above 1.50.

Measured confirmation on the three fixtures that reached the rung: `c03` at
`index_size_ratio` 1.0000, `heap_tuple_ratio` 0.4000, `norm` 2.5000; `k01` and `s01` both at
1.0000 / 0.5000 / 2.0000 — all three flagged by the growth rule too, and invariant I1 shows
that no un-rebuilt fixture in the run had `index_size_ratio` below 1.

Keep the rule, because "the indexed population collapsed" is more actionable than
"disproportionate growth" and it costs one `AND`. Do not expect it to detect anything the
growth rule misses.

### The statistics counter you must not build the guard on

The first ladder used `n_mod_since_analyze > 0.10 * reltuples` as a hard stale-statistics veto.
It is unusable, and this run reproduces why on **4 of 4 deliberate attempts**: a `DELETE`
followed immediately by `VACUUM (ANALYZE)` in the same session leaves the statistics view
describing changes the `ANALYZE` already saw.

| attempt | `n_live_tup` | `n_dead_tup` | `n_mod_since_analyze` | `pg_class.reltuples` |
|---|---|---|---|---|
| 1 | 120000 | **15000** | **15000** | 135000 |
| 2 | 105000 | **15000** | **15000** | 120000 |
| 3 | 90000 | **15000** | **15000** | 105000 |
| 4 | 75000 | **15000** | **15000** | 90000 |
| 5, with a 2 s pause before the `VACUUM (ANALYZE)` | 75000 | 0 | 0 | 75000 |

Each pair deleted exactly 15,000 rows and then analyzed; the true dead count afterwards is 0
and the true `mod_since_analyze` is 0, which is what attempt 5 reads once the pause lets the
flush land first. `pg_class.reltuples` — written by `vac_update_relstats`, not by pgstat —
is correct in every row.

The cause is a flush-ordering race, not a bug in the guard's arithmetic. `pgstat_report_analyze`
zeroes `mod_since_analyze` in the shared entry
([pgstat_relation.c:331-337](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L331-L337)),
but a backend's own pending counts are flushed separately and *additively*:
`mod_since_analyze += changed_tuples`, `live_tuples += delta_live_tuples`, then
`live_tuples = Max(live_tuples, 0)`
([pgstat_relation.c:849-867](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L849-L867)).
A non-forced flush is rate-limited to once per `PGSTAT_MIN_INTERVAL`, 1000 ms
([pgstat.c:117-122](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L117-L122),
[pgstat.c:636-655](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L636-L655)).
A `DELETE` followed within that window by `VACUUM (ANALYZE)` therefore has its counts applied
*after* the reset, adding the whole delete back onto a counter the `ANALYZE` had just zeroed.

The error is one-directional: the counter over-reports changes the `ANALYZE` did in fact see, so
it raises false staleness alarms and never false all-clears. That makes it safe as the advisory
`stats_lag` column and unsafe as a veto. The veto that replaced it, `cur_analyze_count <= bac`,
is immune, because `analyze_count` is incremented in the same locked section as the reset
([pgstat_relation.c:339-348](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L339-L348)).

The same race affects **baseline capture**, and the measured form is sharper than the old text
claimed. A capture that runs in a *different session* from the loader reads the full counts,
because the loader's backend published them when it exited. A capture in the **same
transaction** as the load cannot: measured on an 80,000-row table built and captured in one
transaction, the payload recorded `bti = 0` while `n_tup_ins` reached 80,000 immediately
afterwards, and repeating the capture after `SELECT pg_stat_force_next_flush();`
([pg_proc.dat:5916-5920](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L5916-L5920))
recorded `bti = 80000`. The effect of the stale value is a permanently over-stated churn delta,
so the churn gate opens earlier than intended. A monitoring session cannot force another
backend's flush, so baseline churn counters can still lag a busy writer by up to
`PGSTAT_MIN_INTERVAL`, or `PGSTAT_MAX_INTERVAL` (60 s) in the worst case
([pgstat.c:117-122](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L117-L122)).

### The four cross-checks and the nine invariants

The method reads only catalogs, `pg_stat_all_tables` and `pg_relation_size`. The protocol's
cross-checks are the *run's* obligation, not the method's, so the script takes
`SHARE ROW EXCLUSIVE` on each fixture's table and censuses every page of its index with
[`pageinspect`](../../../glossary.md#pageinspect), beside the FSM and the metapage.

| Check | How it was run | Result |
|---|---|---|
| FSM free pages against the census's recyclable count | [`pg_freespace`](../../../glossary.md#pg_freespacemap) per block against the census's new-plus-deleted count | **22 of 22**, and the two counts are **equal** on every fixture, not merely bounded |
| size bracket | `pg_relation_size(index, 'main')` re-read after the census, against the blocks it scanned | **22 of 22** |
| `VACUUM VERBOSE` | the fourth field of the index line — `pages_free` ([vacuumlazy.c#verbose-index-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L720-L731)) — from the maintenance step, against the census | **20 of 20** |
| metapage page-type counts | `n_entry_pages` and `n_data_pages` against the census's live pages | **21 of 22** exact; the exception is `a02`, off by one entry page |

The FSM equality is worth a sentence: an index FSM records only free-versus-in-use, writing a
free page as `BLCKSZ - 1`
([indexfsm.c#RecordFreeIndexPage](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L48-L55)),
and the value read back is the category floor
([freespace.c#fsm_space_cat_to_avail](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L427-L435)).
Every fixture with free pages read `max(avail) = 8160` from `pg_freespace`, which is
`MaxFSMRequestSize` on this build, derived from the running server rather than typed in.

Invariant I6 is the one that failed, and it failed exactly where the protocol says it must:
`a01` and `a02`, the two auto-analyze stand-ins, whose metapage page counts were never
rewritten because neither the worker's flush nor `gin_clean_pending_list` reaches
`ginUpdateStats`
([ginutil.c#ginUpdateStats](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L645-L650)).
`c09` is excluded from I6 rather than failing it: its census describes the out-of-band rebuild,
and its metapage row the churned index before it.

The census also answers the protocol's concurrency rule, which asks what the progress views
could see at either end of a scan. Each census counts the rows
`pg_stat_progress_vacuum`
([system_views.sql#pg_stat_progress_vacuum](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1209-L1227)),
`pg_stat_progress_analyze`
([system_views.sql#pg_stat_progress_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1188-L1207))
and `pg_stat_progress_create_index`
([system_views.sql#pg_stat_progress_create_index](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1256-L1289))
hold for its table or its index, before the first page read and after the last: **0 rows at
both ends on all 26 censuses**, which is invariant I9. The rule's own caveat applies — a
command that starts and finishes between the two reads leaves no trace in either — so an
unflagged census is unrefuted rather than proven, and the `SHARE ROW EXCLUSIVE` lock is what
makes it exact.

### The simulated auto-analyze census

After the maintenance step and before the decide phase, the run recomputes the launcher's
analyze verdict for every table in the fixture database from the effective reloption-or-GUC
values, and analyzes the tables it names.

| Table | `reltuples` | `n_mod_since_analyze` | threshold | `autovacuum_enabled` | verdict |
|---|---|---|---|---|---|
| `tc_past` | 10,000 | 2,000 | 1,050.00 | true | **analyze** |
| `tc_exact` | 10,000 | **1,050** | **1,050.00** | true | declined |
| `tc_off` | 10,000 | 2,000 | 1,050.00 | **false** | declined |
| the 24 fixture tables | 0 to 2,000,000 | **0** | 50 to 200,050 | true | declined |

**27 tables walked, 1 analyzed.** `tc_exact` lands exactly on its threshold and is left
alone, which is the engine's strictly-greater comparison measured
([autovacuum.c#verdicts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095));
`tc_off` is short-circuited by its reloption
([autovacuum.c#av_enabled-return](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3048-L3054));
and every fixture table reads `n_mod_since_analyze = 0` because the maintenance step analyzed
it already.

That last column is a limit, not a success: the census's decision power on this page is
exercised only by the two synthetic tables, because the protocol's own maintenance step has
already analyzed everything the fixtures touched.

One defect in my first attempt is worth recording, because the protocol names it: the
census tables' build-phase `ANALYZE` originally ran **before** `pg_stat_force_next_flush()`,
so the load's own pending counts landed on the freshly zeroed counter and `tc_exact` came out
at 11,050 modifications instead of 1,050 — the first publication point, failing exactly as
documented. Publishing first and analyzing second fixed it.

The census's own `ANALYZE` is a maintenance statement like any other, so since 2026-09-17 it
runs in the same timeouts-at-zero session and carries the same proofs: one `ANALYZE`
statement, its command tag returned, no skipping line, all four timeouts `0`, and no
`VACUUM` tuples line to read because an `ANALYZE` prints none.

### End-to-end run of the published statements

The three statements were extracted from this page and run **verbatim** — 41, 18 and 76 lines,
with no substitution at all — in their own database against `orders_tags_gin` on a
600,000-row `orders` table carrying the same two-line human comment, through the protocol's
phases:

| step | result |
|---|---|
| build + settle | index 14,778,368 bytes, table `reltuples` 600,000 |
| capture (statement 1) | `bis` 14778368, `bhr` 600000, `bfn` 17509, `bti` 600000, `bac` 1; human comment preserved |
| read (statement 2) | all nine fields round-trip; `human_comment` returns the two original lines only |
| churn: two full-table `UPDATE`s, then settle, then maintenance | 14,778,368 -> 36,978,688 bytes, 0 pending pages |
| decide (statement 3, under `SHARE ROW EXCLUSIVE`) | `index_size_ratio` 2.5022, `heap_tuple_ratio` 1.0000, `normalized_index_growth` 2.5022, `churn_ratio` 2.0000, `stats_lag` 0.000, verdict `candidate: disproportionate growth`, `est_reclaimable` 21 MB |
| oracle: `REINDEX INDEX` | 36,978,688 -> 14,770,176 = **60.06 %** returned, against a predicted **60.04 %** |
| re-capture (statement 1 again) | `bfn` 17509 -> 17514, `bis` 14770176, `btu` 1200000, `bac` 2, human comment intact, exactly one payload |
| re-evaluate | `insufficient churn: not evaluated` — the baseline is clean again |

The 0.02-point gap is the model at its best and still not a bound: the population never
changed, so `heap_tuple_ratio` is exactly 1, and the rebuild came back **one page smaller**
than the baseline (14,770,176 against 14,778,368) rather than exactly equal. Its three
settle and maintenance statements carry the same no-defeat proofs as the fixtures': 0
dead-but-not-removable on every block, no skipping line, all four timeouts `0`.

Two artifacts of running the published text verbatim are worth naming, because a reviewer
sees them in the output. The statement carries its own `BEGIN`, so running it inside the
run's own lock transaction logs `WARNING: there is already a transaction in progress` and
the statement's `COMMIT` is what releases the measurement lock; and `heap_tuple_ratio`
reads exactly 1.0000 here only because this table's `reltuples` happens to land on 600,000
in both readings — see
[Third failure](#third-failure-the-denominator-is-a-sample-and-the-baseline-is-not).

### Edge cases proven on the server

| # | case | result |
|---|---|---|
| E1 | two-line human comment containing `{do not drop}` and `@ 100%` | preserved through capture; comment 196 bytes, payload 139 |
| E2 | plain `REINDEX INDEX` | index OID stays 17440, relfilenode 17440 -> 17444, comment intact |
| E3 | `REINDEX INDEX CONCURRENTLY` | index OID moves 17440 -> 17445 and the comment follows, payload and human text unchanged |
| E4 | evaluate after E3 | `rebuilt since baseline: re-capture` |
| E5 | `ALTER INDEX ... RENAME` | comment survives (same OID) |
| E6 | `COMMENT ON INDEX` lock footprint | one row in `pg_locks`: [`ShareUpdateExclusiveLock`](../../../glossary.md#shareupdateexclusivelock) on the index, and none on the table |
| E7 | non-owner with `SELECT` and `pg_read_all_stats` | reads the baseline fine (`bis` 1064960); write refused with `must be owner of index edge_gin` |
| E11 | capture aimed at a [B-tree](../../../glossary.md#b-tree) | refuses: `not a GIN index: fresh_btree` |
| E13 | 80,000-row table, no `ANALYZE` | `reltuples` `-1` before any index, `80000` after `CREATE INDEX`, so capture at `t0` succeeds |
| E14 | `TRUNCATE` then capture | `reltuples` resets to `-1`; capture refuses: `refusing baseline for t0_gin: table reltuples is -1 (run ANALYZE first)` |
| E15 | `pg_dump -t ... --section=post-data` | emits one `COMMENT ON INDEX ... @ginbase:{...}` line, so the baseline survives dump and restore |

E3 is the case the brief's `REINDEX CONCURRENTLY` target depends on, and it works because
`index_concurrently_swap` explicitly moves the `pg_description` row from the old index OID to
the new one
([index.c:1740-1784](../../../../raw/postgres-17/src/backend/catalog/index.c#L1740-L1784)).
The moved payload still carries the *old* `bfn`, which is why the rebuild detector fires and the
operator is told to re-capture rather than being handed a bogus ratio.

E7 follows from `CommentObject` calling `check_object_ownership` after taking
`ShareUpdateExclusiveLock`
([comment.c:66-77](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L77)),
and E6 from the same call. E15 works because a comment is an ordinary catalog row keyed on
`objoid`/`classoid`/`objsubid`
([pg_description.h:48-66](../../../../raw/postgres-17/src/include/catalog/pg_description.h#L48-L66)).

### Operational notes: locks, privileges, timeouts, GUC scopes

- **Capture takes `ShareUpdateExclusiveLock` on the index.** Documented
  ([comment.sgml:95-98](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L95-L98))
  and measured (E6). That mode self-conflicts and conflicts with `VACUUM`, `ANALYZE`,
  `CREATE INDEX CONCURRENTLY` and `REINDEX CONCURRENTLY`, so a capture can be blocked by, or
  block, routine maintenance. Always set `lock_timeout`.
- **Only the index's owner can write the baseline**
  ([comment.sgml:100-109](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L100-L109)),
  so the capture job needs table ownership, not just `pg_monitor`.
- **Anyone connected to the database can read it.** "There is presently no security mechanism
  for viewing comments: any user connected to a database can see all the comments for objects in
  that database."
  ([comment.sgml:292-298](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L292-L298))
  Row counts and index sizes are not secrets in most shops, but the payload is world-readable —
  do not extend it with anything sensitive.
- **A comment is dropped with its object** and replaced wholesale by the next `COMMENT`
  ([comment.sgml:87-93](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L87-L93)),
  which is why the capture statement re-reads and re-writes the human text rather than appending
  blindly.
- **Timeouts.** Both `statement_timeout` and `lock_timeout` are `PGC_USERSET`
  ([guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620),
  [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631)),
  so the `SET LOCAL` values in the statements above are session/transaction scope: no reload, no
  restart.
- **Do not let a maintenance job inherit those timeouts.** The evaluation should be bounded;
  the `VACUUM` or `ANALYZE` that maintains the table should not be. An autovacuum worker
  forces `statement_timeout`, `lock_timeout`, `transaction_timeout` and
  `idle_in_transaction_session_timeout` to `0` on itself, with the reason in the comment —
  "to avoid letting these settings prevent regular maintenance from being executed"
  ([autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470)) —
  and a scripted maintenance job that runs under a shop-wide `statement_timeout` does not.
  All four are `PGC_USERSET`
  ([guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642),
  [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653)),
  so setting them to `0` for the maintenance session costs a `SET`: session scope, no reload,
  no restart. This run does exactly that, and proves it per statement; see
  [The maintenance was not defeated](#the-maintenance-was-not-defeated).
- **`gin_pending_list_limit` is `PGC_USERSET`** too
  ([guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3577-L3585)),
  session/transaction scope, and can also be set per index as a storage parameter
  ([gin.sgml:610-616](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L610-L616)).
- **The evaluation is not lock-free.** `pg_relation_size` opens each relation with
  `AccessShareLock`
  ([dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L371)),
  so a scan over many GIN indexes touches many relations. Keep `lock_timeout` set there too.
  The protocol's own measurement lock is stronger still — `SHARE ROW EXCLUSIVE` on the table
  blocks every writer for the duration — and is a property of the *run*, not advice for
  production.
- **`REINDEX` is the action, not `VACUUM`.** The same-version `REINDEX` documentation lists a
  bloated index — "it contains many empty or nearly-empty pages" — as a reason to rebuild
  ([reindex.sgml:54-64](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml#L54-L64)).

### Recommended thresholds

Starting values, to be re-calibrated per installation. These are heuristics for building a
shortlist, not a bloat measurement.

| knob | value | basis on this run |
|---|---|---|
| `churn_ratio` gate | 0.20 | the two fixtures below it returned 0.00 % (`c04`) and 25.52 % (`a01`), so the gate costs one real 25 % opportunity and saves one pointless evaluation |
| `candidate` | `norm >= 1.50` | separates the eleven flagged fixtures, which returned 30.45 % to 81.93 %, from `a02` at 22.70 % |
| `watch` | `norm >= 1.20` | catches `a02`, which is not worth a rebuild at this page's declared 33.33 % payoff threshold |
| strong-candidate shrink test | `htr <= 0.50` | fired on `c03`, `k01`, `s01`, all correct; the `isr >= 0.75` clause is vacuous on GIN and is kept as documentation |
| `est_reclaimable` | **do not use as bytes** | declared an upper bound, violated on 7 of 20, demoted to a level |

Lowering `candidate` to 1.25 would add `a02` (22.70 %) to the flagged set
and would not have avoided the one false positive, which sits at 1.9184. On
`fastupdate = on` indexes smaller than a few hundred megabytes, no threshold on this statistic
recovers the pending-list high-water mark: `p01` reads 1.0284 with 5.86 % returned while
`p02`, which never grew at all, would *lose* 21 % to a rebuild. Only a periodic rebuild, or
`fastupdate = off`, addresses that — and note that flipping the reloption takes an
[`AccessExclusiveLock`](../../../glossary.md#accessexclusivelock) on the index
([reloptions.c:123-131](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L123-L131)),
so it is not an online change.

### Coverage the protocol requires, and what this page skipped

| Behavior the protocol requires | Reached by | |
|---|---|---|
| keys that no longer occur after churn | `k01` (3,001 -> 1,501 entries on rebuild) | yes |
| emptied posting-tree pages | `s01` (60 pages deleted, then recycled) | yes |
| half-empty posting-tree leaves with nothing deletable | `c02`, `c05`, `c11` (9,988 and 5,372 data pages after churn) | yes |
| a populated pending list, and the same index after a flush | `p01`, `m01`, `a01`, `a02` | yes |
| an untouched index and an empty index | `c04`, `e01` | yes |
| a snapshot held across the settling `VACUUM` | `s01` | yes |
| more than one [operator class](../../../glossary.md#operator-class) | `array_ops`, `tsvector_ops`, `jsonb_path_ops`, `gin_trgm_ops`, `btree_gin int4_ops`, plus partial, two-column and expression indexes | yes |
| one rebuild at more than one `maintenance_work_mem` | the 64MB / 256MB / 1GB probe | yes |
| a churned index measured before and after the maintenance step | `m01` | yes |
| an index maintained by the auto-analyze stand-in | `a01`, `a02` | yes |
| a table the census analyzed, and one it declined | `tc_past`, `tc_exact`, `tc_off` | yes |
| an undecodable or unclassifiable page, and an all-zero page | **skipped** | the method reads no index page, so it cannot be scored on one; the run's census would raise on such a page rather than classify it |
| a concurrent `VACUUM`, a concurrent rebuild and a writer stream | **partly skipped** | `c09` covers an out-of-band rebuild between the maintenance step and the decide pass; no concurrent writer or `VACUUM` ran against a decide pass, because the measurement lock excludes both. Since 2026-09-17 every census also records what the three progress views could see about its relation at both ends of its scan: 0 rows on 26 of 26 |

The protocol no longer lists "a `VACUUM` whose index cleanup did not run" among the
behaviors a run must reach; its
[What the protocol does not cover](../../common-concepts/mandatory-gin-bloat-tests.md#what-the-protocol-does-not-cover)
names that `VACUUM` instead. This page ran one until 2026-09-24, as fixture `i01`, and no
longer does. The settle step is still proven from the index's own state on every fixture,
as [The phases every fixture ran](#the-phases-every-fixture-ran) describes, but no fixture
here shows that proof meeting a `VACUUM` that skipped [index cleanup](../../../glossary.md#index_cleanup).

### What left the page with its fixtures

The asker's instruction was to remove what cannot conform, with the claims it backed. What
went, and why:

| Removed | Why | What replaced it |
|---|---|---|
| cell `c07`: `fastupdate = on`, `UPDATE` 30 %, **no `VACUUM`** | unmaintained churn, which the maintenance assumption forbids | `p01`/`p02`, the same mechanism measured in a maintained state |
| cell `c08`: `DELETE` 60 %, no `VACUUM`, no `ANALYZE` | unmaintained churn; and its point — the `bac` gate catching a missing `ANALYZE` — is unreachable once the maintenance step always analyzes | the ladder table now states that rung 7 cannot fire under the protocol |
| the six-point proportional-growth sweep's +10 %, +25 % and +50 % rows, and the 20,692,992-byte plateau they shared | all three were read before any `VACUUM` | `p01`/`p02`, plus the foreground-flush arithmetic that explains the plateau |
| the `fastupdate` probe's "after +150,000 inserts, before `VACUUM`" line as a *scored* reading | pre-settle state | the same reading kept as churn-phase evidence, explicitly unscored |
| the whole 12-cell matrix and its byte values | prose-only recipes; nothing on the page could re-run them | scored fixtures whose recipes are lines of the published script |
| the `Test methodology` section | superseded | [Measurement Script](#measurement-script) |
| the `Re-verification on a second 17.11 build` section | its entire subject was that the fixture SQL had never been published | the script is published, so any run is a re-run |
| the claim that a fresh build "quadruples between 1M and 2M rows, then adds zero bytes from 2M to 4M" | did not reproduce | 2.67x then 1.38x, with the entry/data page split for each point |
| the claim that a 64MB build is "32.8 % larger" than a 256MB one, and the one-page inconsistency filed against it | did not reproduce | 20.3 % larger, with the metapage identity exact on 9 of 9 builds |
| the claim that the pgstat race "fired on 1 of 4" attempts | did not reproduce | 4 of 4, with a 2 s pause reading clean |
| the claim that `norm` 1.0049 hid 20.39 % reclaimable, and that the +50 % row's 0.8374 hid 0.48 % | fixtures gone | `p01` at 1.0284 with 5.86 %, and `p02` at 0.8000 with −21.01 % |
| the claim that `REINDEX` "returned both indexes to exactly 16,474,112 bytes" | the twins do rebuild to the same size, but it is **larger** than either churned file | the `p01`/`p02` table, including the negative oracle |
| open question 13, that nothing executable survived the sandbox | resolved | the script |
| open question 14, the internally inconsistent 64MB row | resolved | I2 exact on every fixture baseline and 9 probe builds |

What the 2026-09-17 review changed, all of it inside the published script rather than in
the prose:

| Changed | Why | Effect on the filed numbers |
|---|---|---|
| every settle and maintenance statement moved into one helper that forces the four settable timeouts to `0`, prints them, and is followed by a checker that dies rather than score | the protocol's [The maintenance must not be defeated](../../common-concepts/mandatory-gin-bloat-tests.md#the-maintenance-must-not-be-defeated), which arrived after the previous run, and which this page had never been checked against | none: every fixture passed, so no number moved because of it. What moved was `c02`'s bound verdict, and the cause is the `ANALYZE` sample rather than the maintenance |
| a horizon reading on each side of every step, and the `dead but not yet removable` count parsed out of every `VERBOSE` block | the rule's four proofs | new facts, no correction: 78 of 78 at 0, one declared 500,000 |
| the page census reads the three progress views at both ends of its scan | the protocol's concurrency rule, which the page had silently skipped | new invariant I9, 27 of 27 |
| the score stage prints what the settle step cost in bytes | the protocol's warning that settling is not free, which the page had quoted but never measured | a new section and a new headline finding: 8 of 23 fixtures grew across their settle step |
| probe P6: five `ANALYZE`s on an unchanged 1,000,000-row table | to find out whether `c02`'s bound flip was the model or the sample | the sample: 1,001,233 to 1,002,633 against a true 1,000,000 |
| the `est_reclaimable` verdict table | `c02` moved from `HELD` to `VIOLATED` | 14 / 7 becomes **13 / 8** |

What the 2026-09-24 pass removed and changed, at the asker's request to remove the invalid
test and re-run all tests:

| Removed or changed | Why | Effect on the filed numbers |
|---|---|---|
| fixture `i01`: `DELETE` 30 %, then `VACUUM (INDEX_CLEANUP OFF)` before the settle step | [Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md) stopped requiring a `VACUUM` whose index cleanup did not run and stopped declaring one as an exception. A `VACUUM` between the writes and the settle step is also not a step of the protocol's churn phase | 23 scored fixtures instead of 24, 18 `PASS` instead of 19, and one `HELD` row and one "within 3.5 points" row fewer. The `watch` rung and the "keys that no longer occur" coverage keep one fixture each, `a02` and `k01` |
| the section on that `VACUUM`, and every claim it backed: its `VERBOSE` output with no index line, the metapage at 996 pages and 10,000 entries on both sides of it, `n_dead_tup` at 0 while 90,000 dead item identifiers stayed in the heap, and the unmoved index file | their only evidence was `i01` | none elsewhere |
| `i01`'s declared exception | the protocol now declares two exceptions | the exceptions table has two rows |
| the command-tag count in `check_maint` | BSD `grep` never counts a bare `VACUUM` line with the old pattern | I8 reads 72 of 72 at score time on this Mac, where the unchanged script read 3 of 76 |
| the `clean` stage's process and port checks | the port check could never match, and `pgrep -a` also matches the caller's ancestors on macOS | the stage now checks the socket file and its lock file |
| two dumps, `meas.csv` and `maint.csv` | numbers the page quotes were stored only in the database, which `reset` and `clean` destroy | every quoted number is now in a file under `out/` |
| the claims that every `ANALYZE` reading comes out high, that the error is one-directional, and the bias argument built on them | 25 readings over five passes of the probe: 18 high and 7 low, from −0.18 % to +0.36 % | [Third failure](#third-failure-the-denominator-is-a-sample-and-the-baseline-is-not) restated |
| the step breakdown "22 churn settles ... 22 churn maintenances" | it summed to 77 against the 79 it stated; `c04` and `e01` run a settle and a maintenance step too | 22 of each after the removal, in a total of 75 |
| the score stage's label "the six declared invariants" | nine are declared | the label only |

## Measurement Script

Every number on this page comes from one script, `gin_norm_protocol.sh`, filed in full under
[The script](#the-script). It is Bash and SQL only: a reviewer needs a C toolchain, a shell
and this page.

### How to use it

| Item | What to give |
|---|---|
| Purpose | Builds PostgreSQL 17.11 out of tree from this repository's pinned checkout and runs this page's whole programme under [Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md): the declared kinds filed before any fixture exists, 23 scored fixtures plus one refusal fixture through build -> baseline -> churn (writes, settle, maintenance) -> decide -> oracle, the simulated auto-analyze census, the four cross-checks and nine invariants, the no-defeat proofs on every settle and maintenance statement, the six mechanism probes, eleven edge cases, and a verbatim end-to-end replay of the three published statements |
| Invocation | `bash .wiki-runtime/tmp/ginnorm/gin_norm_protocol.sh [stage ...]`, run from the repository root. With no arguments it runs every stage except `reset` and `clean`. Extract the fenced script below to that path first |
| Stages | Default order: `build declare fixtures churn analyze_census crosscheck decide oracle score probes edge pubsql verify`. `build` configures, builds and installs out of tree (skipped when the binary is already there), runs [`make check`](../../../glossary.md#regression-test) plus the five [contrib](../../../glossary.md#contrib) suites this page reads, `initdb`s and starts the cluster; `declare` files the declared kind of every published column, the decision thresholds and the nine invariants, and **refuses to run once the fixture database exists**; `fixtures` runs the build phase and the baseline capture for all 24 fixtures; `churn` runs each recipe's writes, then the settle `VACUUM`, then the maintenance `VACUUM ANALYZE`, with the auto-analyze stand-in and the held-snapshot, out-of-band-rebuild and counter-reset cases in line — every settle and maintenance statement of the run goes through `run_maint`, which forces the four settable timeouts to `0`, and `check_maint`, which parses its `VERBOSE` output and **dies rather than score** a defeated fixture; `analyze_census` recomputes the launcher's analyze verdict for every table and analyzes the ones it names; `crosscheck` censuses every page of every fixture index under `SHARE ROW EXCLUSIVE`, reads the FSM, and records what the three progress views could see at both ends of the scan; `decide` runs statement 3 verbatim inside one locked transaction, then stores the same rows for scoring; `oracle` rebuilds each index between two `pg_relation_size` readings; `score` prints the no-defeat proofs and refuses to score a defeated run, checks the filed declarations against the ones the scoring assumes, and prints the bound verdicts, the decision scores, the accuracy bands, the nine invariants, every phase size and what the settle step cost in bytes, then writes every stored reading to `meas.csv`; `probes` runs the `reltuples` swing, the six-point linearity sweep, the three-budget rebuild, the pgstat race, the capture race and the `ANALYZE` sample spread; `edge` runs the eleven edge cases in their own database; `pubsql` replays the three statements verbatim through a whole lifecycle and re-prints the proof table, and rewrites `maint.csv`, with its own three steps in it; `verify` re-extracts the statements from this page and diffs them against the files that ran. `reset` drops the databases so a re-run starts clean, `start` starts an already-built cluster, and `clean` is not in the default order and must be run last |
| Environment | `REPO` (`$PWD`), `SRC` (`$REPO/raw/postgres-17`), `SANDBOX` (`$REPO/.wiki-runtime/tmp/ginnorm`), `PAGE` (this file), `PORT` (`55417`), `JOBS` (`20`; the recorded run set `8`), `BASE_ROWS` (`1000000`), `PEND_ROWS` (`600000`), `SMALL_ROWS` (`300000`), `TRGM_ROWS` (`100000`), `A01_INSERTS` (`40000`), `A02_INSERTS` (`60500`), `KEYS` (`10000`), `MWM` (`256MB`) |
| Prerequisites | See [Prerequisites](#prerequisites) |
| Output | Everything lands under `$SANDBOX/out/`; see [Where the results land](#where-the-results-land). Read `maintenance-proof.txt` first, because a defeated run may not be scored at all, then `score-table.txt` and `score-summary.txt`. `meas.csv` holds every stored reading the other files summarise. Copy `out/` before `clean`, which deletes it |
| Runtime | Measured on the recorded host, a 10-core arm64 Mac with `JOBS=8`: **4 min 16 s** for the whole default order from an empty sandbox. The `build` stage is 85 s of that: about 50 s to configure, compile and install, and 35 s for `make check` plus the five contrib suites. The programme itself is **2 min 51 s**: 22 s for the 24 fixtures, 1 min 30 s for the churn phase (45 s of which is `s01`'s held snapshot), 2 s for the census, cross-check and decide stages together, 12 s for the oracle, under 1 s for the score stage, 37 s for the six probes, and 8 s for the edge, pubsql and verify stages together. A re-run from a built tree after `reset` took **3 min 28 s** |
| Cleanup | `bash gin_norm_protocol.sh clean` stops the cluster with `pg_ctl -m fast -w stop`, reports whether a `postmaster.pid`, a process with the data directory on its command line, or the port's socket or lock file survived, and deletes the whole sandbox |

### Prerequisites

- A C toolchain, `make`, `flex`, `bison` and `perl`. The recorded run used Apple clang
  21.0.0 on macOS 27 (`Darwin arm64`); the 2026-09-17 runs used gcc 13.3.0 on
  `Linux x86_64`. The script builds its own server; no installed PostgreSQL is used, and it
  never touches a cluster it did not create.
- `bash` and the platform's own `grep`, `sed` and `pgrep`. The script uses only the
  `grep` and `sed` forms that GNU and BSD share, so it runs unchanged on Linux and macOS.
- No ICU or readline development headers are needed: the build configures
  `--without-icu --without-readline --with-zlib --enable-debug`, and `initdb` runs with
  `--locale=C --encoding=UTF8`, which is what makes the `pg_trgm` and `tsvector` fixtures
  deterministic.
- The pinned checkout present at `raw/postgres-17`, read-only. The script builds out of tree
  and writes nothing inside it.
- Port 55417 free, and about 6 GB under `.wiki-runtime/tmp/`: the recorded run's sandbox was
  4.9 GB, of which 4.7 GB is the data directory and 262 MB the out-of-tree
  build and install.
- The `pageinspect`, [`pgstattuple`](../../../glossary.md#pgstattuple), `pg_freespacemap`, `pg_trgm` and `btree_gin` contrib
  modules, which `make -C contrib install` provides from the same tree.
- Every `psql` call is `psql -X -v ON_ERROR_STOP=1` against the sandbox's own socket
  directory, so a stray `~/.psqlrc` cannot change a result and no error passes silently. The
  few statements whose *error text* is the result being measured are read from the stage log
  instead.

### Where the results land

| File | What is in it |
|---|---|
| `declared_kind.txt`, `declared_decision.txt`, `declared_invariant.txt`, `declared_at.txt` | what was declared, and the timestamp it was filed at |
| `check-summary.txt`, `check-*.log` | `make check` and the five contrib suites |
| `baseline-sizes.txt` | the as-built size of every fixture index |
| `build-*.log`, `churn-*.log`, `settle_build-*.log`, `settle-*.log`, `maint-*.log`, `standin-a0*.log`, `settle2-s01.log`, `analyze_census-census.log`, `snapshot-s01.log`, `outofband-c09.log` | every phase's own output, including every `VACUUM VERBOSE` index line, every `tuples: ... are dead but not yet removable` line, and the four timeouts each maintenance session ran under |
| `horizon-*-*_before.log`, `horizon-*-*_after.log` | the horizon reading on each side of every settle and maintenance step: holding backends with their `xact_start`/`backend_xid`/`backend_xmin`, replication slots, prepared transactions |
| `maintenance-proof.txt`, `horizon-holders.txt`, `maint.csv` | the no-defeat proofs, one line per step, with the run totals; the same steps' horizon readings side by side; and the whole proof table as CSV |
| `meas.csv` | every reading the fixture database stored, one row per fixture, phase and metric: the metapage and census rows behind the `m01`, `s01`, `k01` and `a01`/`a02` tables, the payloads with their capture times, the stand-ins' flush counts, and the rebuilt indexes' own catalog rows |
| `census-verdicts.txt`, `census-analyzed.txt` | the simulated analyze census: one line per table, and the `ANALYZE` statements it generated |
| `census-summary.txt` | the page census per fixture: scanned, entry, data, list, deleted, new, FSM |
| `decide.txt` | the published statement's own output, under the measurement lock |
| `oracle-summary.txt` | the two size readings and the returned percentage per fixture |
| `score-table.txt`, `score-summary.txt` | the scored table and its totals |
| `invariants.txt`, `phase-sizes.txt`, `settle-delta.txt` | the nine invariants, every phase size with the pending-page transition, and what the settle step cost in bytes per fixture |
| `probe-p1.txt`, `probe-p2.txt`, `probe-p4.txt`, `probe-p5.txt`, `probe-p6.txt` | the `reltuples` swing, the linearity and budget sweeps, the pgstat race, the capture race, the `ANALYZE` sample spread |
| `edge.txt`, `pubsql.txt`, `verify.txt` | the eleven edge cases, the verbatim lifecycle, and the three-way diff against this page |
| `settings.txt`, `version.txt`, `pin.txt` | the settings the run fixes with their contexts, the server version, the commit the source is parked on |

### The last run

| Fact | Value |
|---|---|
| Date | 2026-09-24, 14:46:33 to 14:50:49 EDT, from an empty sandbox |
| Server | PostgreSQL 17.11, built from `786db8dcf168bd9df8f55047337525ac19118b1c`, seven commits past the `Stamp 17.11.` commit `083ac03341`. The checkout on this host carries no release tags, so that count comes from commit ancestry |
| Platform | macOS 27.0, `Darwin 27.0.0 arm64`, Apple clang 21.0.0, 10 cores, `JOBS=8` |
| `block_size` | 8192, from the server's own `pg_settings` and from `pg_controldata` |
| [`max_data_alignment`](../../../glossary.md#alignment) | 8, from `pg_controldata` on the recorded run's data directory, read before `clean` |
| Regression suites | core **All 225**, `pageinspect` **All 8**, `pgstattuple` **All 1**, `pg_freespacemap` **All 1**, `btree_gin` **All 30**, `pg_trgm` **All 4** |
| Cluster settings, with contexts | `autovacuum = off` (`PGC_SIGHUP`, reload), `shared_buffers = 512MB` (`PGC_POSTMASTER`, restart), `maintenance_work_mem = 256MB`, `work_mem = 64MB`, `gin_pending_list_limit = 4096 kB`, `statement_timeout = 900s`, `lock_timeout = 15s`, `stats_fetch_consistency = cache` (all `PGC_USERSET`, session/transaction scope) |
| Maintenance sessions | every settle and maintenance statement overrides those timeouts to `statement_timeout = 0`, `lock_timeout = 0`, `transaction_timeout = 0`, `idle_in_transaction_session_timeout = 0` and prints all four back: **75 of 75 steps** read all-zero |
| Declarations filed | 2026-09-24T18:47:58Z, two seconds before the first fixture's baseline payload at 18:48:00Z |
| Published statements | 3 of 3 byte-identical to this page, at 41 / 18 / 76 lines |
| Filed text | the fenced script below was diffed against the file that ran: identical, md5 `d7cbb299c3d3ea7225e009220251d6c7`, 1,913 lines |
| Reproducibility | four passes ran on this host on 2026-09-24, each through the whole default order. The first was the filed 2026-09-17 script, unchanged, before any edit. The second and third ran the edited script without the two `.csv` dumps: one from an empty sandbox, and one after `reset` from the built tree. The fourth, the recorded run, ran the final text from an empty sandbox. Every scored cell agreed across all four passes, and with the 2026-09-17 Linux filing, except three things. `c02`'s `reltuples` sample, and so its bound verdict: `HELD`, `VIOLATED`, `VIOLATED`, `HELD`. The P6 readings. And the OIDs and timestamps. The first pass still carried `i01` and so read 24 scored fixtures and 19 `PASS`. It also read I8 as 3 of 76, through the `grep` defect the later passes fix |

### The script

```bash
#!/usr/bin/env bash
#
# gin_norm_protocol.sh - the measurement programme behind
# wiki/v17/questions/indexing/gin-reindex-normalized-growth-comment-baseline.md
#
# Runs the COMMENT-baseline / normalized-index-growth heuristic for GIN indexes
# under the wiki's Mandatory GIN Bloat Tests protocol: five phases per fixture
# (build, baseline, churn ending in settle + maintenance + census, decide under
# the measurement lock, and a measured REINDEX INDEX oracle), a declared kind per
# published column filed before the first fixture exists, and the four mandatory
# cross-checks.
#
# Every settle and maintenance statement runs through run_maint and is scored by
# check_maint, because the protocol also requires that the maintenance was not
# defeated: the statement must have been effective, not merely issued.
#
# Every object this script creates is DISPOSABLE. It builds its own PostgreSQL
# out of tree, runs its own cluster on a non-default port with its own socket
# directory, and the `clean` stage stops that cluster and deletes the sandbox.
# It never touches a cluster it did not start, and it treats raw/postgres-17 as
# read-only.
#
# Usage:  bash gin_norm_protocol.sh [stage ...]      (run from the repo root)
#         bash gin_norm_protocol.sh                  (same as `all`)
#
set -uo pipefail

REPO="${REPO:-$PWD}"
SRC="${SRC:-$REPO/raw/postgres-17}"
SANDBOX="${SANDBOX:-$REPO/.wiki-runtime/tmp/ginnorm}"
PAGE="${PAGE:-$REPO/wiki/v17/questions/indexing/gin-reindex-normalized-growth-comment-baseline.md}"
PORT="${PORT:-55417}"
JOBS="${JOBS:-20}"
BASE_ROWS="${BASE_ROWS:-1000000}"
PEND_ROWS="${PEND_ROWS:-600000}"
SMALL_ROWS="${SMALL_ROWS:-300000}"
TRGM_ROWS="${TRGM_ROWS:-100000}"
# a01 sits above the analyze threshold and below the method's churn gate;
# a02 sits in the 1000-row window where both are satisfied at once
A01_INSERTS="${A01_INSERTS:-40000}"
A02_INSERTS="${A02_INSERTS:-60500}"
KEYS="${KEYS:-10000}"
MWM="${MWM:-256MB}"

BUILD="$SANDBOX/build"
INST="$SANDBOX/install"
BIN="$INST/bin"
PGDATA="$SANDBOX/data"
SOCK="$SANDBOX/sock"
OUT="$SANDBOX/out"
SQLD="$SANDBOX/sql"
LOG="$SANDBOX/server.log"
DB=ginnorm
PDB=protocol

export PGOPTIONS="-c statement_timeout=900s -c lock_timeout=15s"

mkdir -p "$SANDBOX" "$SOCK" "$OUT" "$SQLD"

say() { printf '\n=== %s\n' "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

q()  { "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1" -At -c "$2"; }
Q()  { "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1" -c "$2"; }
qf() { "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1" -f "$2"; }
qin(){ "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1"; }
qat(){ "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$1" -At -f "$2"; }

# ---------------------------------------------------------------- the method
# The three statements below are the page's published SQL, byte for byte. The
# `verify` stage re-extracts them from the page and diffs them against these
# files, so the text that ran is provably the text that is published.
write_published_sql() {
  cat > "$SQLD/capture.sql" <<'WIKISQL'
BEGIN;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '5s';

SELECT /* wiki_gin_capture_baseline */
       CASE
         WHEN am.amname <> 'gin' THEN
           format('DO $$ BEGIN RAISE EXCEPTION %L; END $$',
                  'not a GIN index: ' || i.indexrelid::regclass::text)
         WHEN ct.reltuples <= 0 THEN
           format('DO $$ BEGIN RAISE EXCEPTION %L; END $$',
                  'refusing baseline for ' || i.indexrelid::regclass::text ||
                  ': table reltuples is ' || ct.reltuples || ' (run ANALYZE first)')
         ELSE
           format('COMMENT ON INDEX %s IS %L',
                  i.indexrelid::regclass::text,
                  btrim(
                    btrim(regexp_replace(coalesce(obj_description(i.indexrelid, 'pg_class'), ''),
                                         '\s*@ginbase:\{[^}]*\}', '', 'g'))
                    || E'\n@ginbase:' ||
                    jsonb_build_object(
                      'v',   1,
                      'ts',  to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                      'bis', pg_relation_size(i.indexrelid),
                      'bhr', ct.reltuples::bigint,
                      'bfn', ci.relfilenode,
                      'bti', coalesce(s.n_tup_ins, 0),
                      'btu', coalesce(s.n_tup_upd, 0),
                      'btd', coalesce(s.n_tup_del, 0),
                      'bac', coalesce(s.analyze_count, 0) + coalesce(s.autoanalyze_count, 0)
                    )::text))
       END
  FROM pg_index i
  JOIN pg_class ci ON ci.oid = i.indexrelid
  JOIN pg_class ct ON ct.oid = i.indrelid
  JOIN pg_am    am ON am.oid = ci.relam
  LEFT JOIN pg_stat_all_tables s ON s.relid = i.indrelid
 WHERE i.indexrelid = 'public.orders_tags_gin'::regclass
\gexec

COMMIT;
WIKISQL

  cat > "$SQLD/read.sql" <<'WIKISQL'
SELECT /* wiki_gin_read_baseline */
       i.indexrelid::regclass                                  AS index_name,
       b.payload->>'ts'                                        AS baseline_taken,
       (b.payload->>'bis')::bigint                             AS baseline_index_size,
       (b.payload->>'bhr')::bigint                             AS baseline_heap_reltuples,
       (b.payload->>'bfn')::oid                                AS baseline_filenode,
       (b.payload->>'bti')::bigint                             AS baseline_n_tup_ins,
       (b.payload->>'btu')::bigint                             AS baseline_n_tup_upd,
       (b.payload->>'btd')::bigint                             AS baseline_n_tup_del,
       (b.payload->>'bac')::bigint                             AS baseline_analyze_count,
       btrim(regexp_replace(coalesce(obj_description(i.indexrelid, 'pg_class'), ''),
                            '\s*@ginbase:\{[^}]*\}', '', 'g')) AS human_comment
  FROM pg_index i
  CROSS JOIN LATERAL (
       SELECT substring(coalesce(obj_description(i.indexrelid, 'pg_class'), '')
                        from '@ginbase:(\{[^}]*\})')::jsonb AS payload
  ) b
 WHERE i.indexrelid = 'public.orders_tags_gin'::regclass;
WIKISQL

  cat > "$SQLD/evaluate.sql" <<'WIKISQL'
BEGIN;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '5s';

SELECT /* wiki_gin_reindex_candidates */
       i.indexrelid::regclass                       AS index_name,
       pg_size_pretty(m.cur_index_size)             AS cur_size,
       pg_size_pretty(m.base_index_size)            AS base_size,
       m.cur_heap_reltuples::bigint                 AS cur_heap_reltuples,
       m.base_heap_reltuples,
       round(r.index_size_ratio::numeric, 4)        AS index_size_ratio,
       round(r.heap_tuple_ratio::numeric, 4)        AS heap_tuple_ratio,
       round(r.normalized_index_growth::numeric, 4) AS normalized_index_growth,
       round(r.churn_ratio::numeric, 4)             AS churn_ratio,
       round(r.stats_lag::numeric, 3)               AS stats_lag,
       v.verdict,
       CASE WHEN r.normalized_index_growth > 1
            THEN pg_size_pretty((m.cur_index_size
                                 * (1 - 1 / r.normalized_index_growth))::bigint)
       END                                          AS est_reclaimable
  FROM pg_index i
  JOIN pg_class ci ON ci.oid = i.indexrelid
  JOIN pg_class ct ON ct.oid = i.indrelid
  JOIN pg_am    am ON am.oid = ci.relam
  LEFT JOIN pg_stat_all_tables s ON s.relid = i.indrelid
  CROSS JOIN LATERAL (
        SELECT substring(coalesce(obj_description(i.indexrelid, 'pg_class'), '')
                         from '@ginbase:(\{[^}]*\})')::jsonb AS p
  ) b
  CROSS JOIN LATERAL (
        SELECT pg_relation_size(i.indexrelid)     AS cur_index_size,
               ct.reltuples                       AS cur_heap_reltuples,
               (b.p->>'bis')::bigint              AS base_index_size,
               (b.p->>'bhr')::bigint              AS base_heap_reltuples,
               (b.p->>'bfn')::oid                 AS base_filenode,
               (b.p->>'bac')::bigint              AS base_analyze_count,
               coalesce(s.analyze_count, 0)
                 + coalesce(s.autoanalyze_count, 0)             AS cur_analyze_count,
               coalesce(s.n_tup_ins, 0) - (b.p->>'bti')::bigint AS d_ins,
               coalesce(s.n_tup_upd, 0) - (b.p->>'btu')::bigint AS d_upd,
               coalesce(s.n_tup_del, 0) - (b.p->>'btd')::bigint AS d_del
  ) m
  CROSS JOIN LATERAL (
        SELECT m.cur_index_size::float8 / nullif(m.base_index_size, 0)         AS index_size_ratio,
               m.cur_heap_reltuples::float8 / nullif(m.base_heap_reltuples, 0) AS heap_tuple_ratio,
               (m.cur_index_size::float8 / nullif(m.base_index_size, 0))
                 / nullif(m.cur_heap_reltuples::float8
                          / nullif(m.base_heap_reltuples, 0), 0)               AS normalized_index_growth,
               (m.d_ins + m.d_upd + m.d_del)::float8
                 / nullif(m.base_heap_reltuples, 0)                            AS churn_ratio,
               coalesce(s.n_mod_since_analyze, 0)::float8
                 / nullif(m.cur_heap_reltuples, 0)                             AS stats_lag
  ) r
  CROSS JOIN LATERAL (
        SELECT CASE
                 WHEN b.p IS NULL                        THEN 'no baseline: capture one'
                 WHEN NOT i.indisvalid                   THEN 'invalid index: rebuild for validity, not for size'
                 WHEN ci.relfilenode <> m.base_filenode  THEN 'rebuilt since baseline: re-capture'
                 WHEN m.d_ins < 0 OR m.d_upd < 0 OR m.d_del < 0
                                                         THEN 'counters reset: re-capture'
                 WHEN m.cur_heap_reltuples <= 0          THEN 'no table statistics: ANALYZE first'
                 WHEN r.churn_ratio < 0.20               THEN 'insufficient churn: not evaluated'
                 WHEN m.cur_analyze_count <= m.base_analyze_count
                                                         THEN 'no ANALYZE since baseline: ANALYZE first'
                 WHEN r.heap_tuple_ratio <= 0.50
                      AND r.index_size_ratio >= 0.75     THEN 'strong candidate: indexed population collapsed'
                 WHEN r.normalized_index_growth >= 1.50  THEN 'candidate: disproportionate growth'
                 WHEN r.normalized_index_growth >= 1.20  THEN 'watch'
                 ELSE 'no action'
               END AS verdict
  ) v
 WHERE am.amname = 'gin'
   AND ci.relpersistence <> 't'
 ORDER BY r.normalized_index_growth DESC NULLS LAST;

COMMIT;
WIKISQL
}

# capture the baseline for one index, using the published text with only the
# target line substituted
capture_for() { # $1 = index name
  sed "s/public\.orders_tags_gin/$1/" "$SQLD/capture.sql" > "$SQLD/.capture_run.sql"
  qf "$DB" "$SQLD/.capture_run.sql" > /dev/null || die "capture failed for $1"
}

# ------------------------------------------ the maintenance, and its four proofs
# The protocol requires that a settle or maintenance step was effective, not just
# issued. On GIN the failure mode is reassuring rather than silent: under a
# pinned horizon ginbulkdelete never runs, while ginvacuumcleanup still flushes
# the pending list, walks every block and rewrites the metapage counters - so
# every settle-step proof is satisfied with not one dead entry gone. The three
# helpers below are what turn that into a scored outcome:
#   horizon_probe  who could pin OldestXmin at this instant, on each side of the
#                  step, plus the timeouts the reading session runs under
#   run_maint      runs the step with all four settable timeouts at 0, exactly as
#                  an autovacuum worker forces them on itself, and keeps its whole
#                  VERBOSE output
#   check_maint    parses that output for the four proofs and DIES rather than let
#                  a defeated fixture be scored
horizon_probe() { # $1 = db, $2 = fixture, $3 = when
  q "$1" "SELECT /* wiki_gin_norm_horizon */
            'backends=' || (SELECT count(*) FROM pg_stat_activity
                             WHERE pid <> pg_backend_pid()
                               AND (backend_xid IS NOT NULL OR backend_xmin IS NOT NULL))
         || ' slots=' || (SELECT count(*) FROM pg_replication_slots
                           WHERE xmin IS NOT NULL OR catalog_xmin IS NOT NULL)
         || ' prepared=' || (SELECT count(*) FROM pg_prepared_xacts)
         || ' | ' || coalesce((SELECT string_agg(
                        format('pid=%s type=%s state=%s xact_start=%s xid=%s xmin=%s',
                               pid, backend_type, state, xact_start, backend_xid, backend_xmin), '; ')
                        FROM pg_stat_activity
                       WHERE pid <> pg_backend_pid()
                         AND (backend_xid IS NOT NULL OR backend_xmin IS NOT NULL)), 'none')
         || ' | probe session timeouts ' || (SELECT string_agg(name || '=' || setting, ' ' ORDER BY name)
                                 FROM pg_settings
                                WHERE name IN ('idle_in_transaction_session_timeout','lock_timeout',
                                               'statement_timeout','transaction_timeout'))" \
    > "$OUT/horizon-$2-$3.log" 2>&1
}

run_maint() { # $1 = db, $2 = fixture, $3 = tag, $4 = the statement(s)
  local db="$1" f="$2" tag="$3" stmt="$4"
  horizon_probe "$db" "$f" "${tag}_before"
  { printf "SET /* wiki_gin_norm_maint */ statement_timeout = 0;\n"
    printf "SET /* wiki_gin_norm_maint */ lock_timeout = 0;\n"
    printf "SET /* wiki_gin_norm_maint */ transaction_timeout = 0;\n"
    printf "SET /* wiki_gin_norm_maint */ idle_in_transaction_session_timeout = 0;\n"
    printf "SELECT /* wiki_gin_norm_maint */ 'maintenance session timeouts: '\n"
    printf "       || string_agg(name || '=' || setting, ' ' ORDER BY name)\n"
    printf "  FROM pg_settings WHERE name IN ('idle_in_transaction_session_timeout',\n"
    printf "       'lock_timeout','statement_timeout','transaction_timeout');\n"
    printf '%s\n' "$stmt"
  } | qin "$db" > "$OUT/$tag-$f.log" 2>&1 || die "maintenance step $tag failed for $f"
  horizon_probe "$db" "$f" "${tag}_after"
}

# $3 = strict  : a VACUUM with nothing holding the horizon, so 0 dead-but-not-yet-
#                removable is required
#      declared: the fixture the coverage list requires to hold a snapshot across
#                its settling VACUUM, where a nonzero count is the point
#      analyze : an ANALYZE-only step, which prints no such count at all
check_maint() { # $1 = fixture, $2 = tag, $3 = strict|declared|analyze, $4 = index
  local f="$1" tag="$2" kind="$3" ix="${4:-}" lg dead deadnz nblk skips cancels tags touts idxline
  local nump newly deld freep hb ha
  [ -n "$ix" ] || ix=$(idx "$f")
  lg="$OUT/$tag-$f.log"
  [ -f "$lg" ] || die "no maintenance log for $f/$tag"
  dead=$(grep -o '[0-9]\+ are dead but not yet removable' "$lg" | head -1 | grep -o '^[0-9]\+')
  # every VERBOSE block, so a TOAST relation's own count cannot hide behind the
  # main relation's
  deadnz=$(grep -o '[0-9]\+ are dead but not yet removable' "$lg" | grep -vc '^0 ')
  nblk=$(grep -c 'are dead but not yet removable' "$lg")
  skips=$(grep -c 'skipping vacuum of\|skipping analyze of' "$lg")
  cancels=$(grep -c 'canceling statement due to\|^ERROR' "$lg")
  # an extended regex: in a basic one, BSD grep reads the `$` before `\|` as a
  # literal character, so a bare VACUUM tag would never be counted
  tags=$(grep -Ec '^(VACUUM|ANALYZE)$' "$lg")
  touts=$(grep -o 'maintenance session timeouts: .*' "$lg" | head -1 \
            | sed 's/^maintenance session timeouts: //')
  idxline=$(grep -o "index \"$ix\": pages: .*" "$lg" | tail -1)
  nump=$(printf '%s' "$idxline"  | grep -o '[0-9]\+ in total' | grep -o '^[0-9]\+')
  newly=$(printf '%s' "$idxline" | grep -o '[0-9]\+ newly deleted' | grep -o '^[0-9]\+')
  deld=$(printf '%s' "$idxline"  | grep -o '[0-9]\+ currently deleted' | grep -o '^[0-9]\+')
  freep=$(printf '%s' "$idxline" | grep -o '[0-9]\+ reusable' | grep -o '^[0-9]\+')
  hb=$(cat "$OUT/horizon-$f-${tag}_before.log" 2>/dev/null | head -1)
  ha=$(cat "$OUT/horizon-$f-${tag}_after.log" 2>/dev/null | head -1)
  q "$DB" "INSERT /* wiki_gin_norm_maintproof */ INTO proto.maint
             (fixture, tag, kind, dead_not_removable, dead_blocks_nonzero,
              verbose_blocks, skip_lines, cancel_lines, command_tags,
              session_timeouts, num_pages, newly_deleted, pages_deleted,
              pages_free, horizon_before, horizon_after)
           VALUES ('$f', '$tag', '$kind', ${dead:-NULL}, ${deadnz:-0}, ${nblk:-0},
                   ${skips:-0}, ${cancels:-0}, ${tags:-0},
                   \$t\$${touts:-unrecorded}\$t\$,
                   ${nump:-NULL}, ${newly:-NULL}, ${deld:-NULL}, ${freep:-NULL},
                   \$h\$${hb:-unrecorded}\$h\$, \$h\$${ha:-unrecorded}\$h\$)" > /dev/null \
    || die "could not record the maintenance proofs for $f/$tag"
  # cross-check 3 reads the fourth field of the maintenance step's index line
  [ "$tag" = maint ] && [ -n "${freep:-}" ] && \
    q "$DB" "SELECT /* wiki_gin_norm_record */ proto.note('$f','churn_maintained','verbose_pages_free',$freep)" > /dev/null
  [ "${skips:-0}" -eq 0 ] || die "$f/$tag was skipped for want of a lock: see $lg"
  [ "${cancels:-0}" -eq 0 ] || die "$f/$tag was cancelled or raised: see $lg"
  case "${touts:-unrecorded}" in
    'idle_in_transaction_session_timeout=0 lock_timeout=0 statement_timeout=0 transaction_timeout=0') : ;;
    *) die "$f/$tag ran under timeouts '${touts:-unrecorded}', not all zero" ;;
  esac
  case "$kind" in
    strict)
      [ -n "${dead:-}" ] || die "$f/$tag printed no dead-but-not-yet-removable count"
      [ "${deadnz:-1}" -eq 0 ] || \
        die "$f/$tag left tuples dead but not yet removable (first block: ${dead}): the horizon was pinned, so this fixture is repaired and re-run, not scored" ;;
    declared)
      # the snapshot is the point, so a zero count here means the fixture never
      # pinned anything and its held-horizon readings describe nothing
      [ "${deadnz:-0}" -gt 0 ] || \
        die "$f/$tag declares a held snapshot but reports 0 tuples dead but not yet removable: the snapshot was not holding the horizon"
      printf '    declared held-horizon step: %s/%s reports %s dead but not yet removable\n' \
        "$f" "$tag" "${dead:-none}" ;;
    analyze)
      [ -z "${dead:-}" ] || die "$f/$tag was declared ANALYZE-only but printed a VACUUM tuples line" ;;
  esac
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

  say "build: make check plus the five contrib suites this run reads"
  ( cd "$BUILD" && make check > "$OUT/check-core.log" 2>&1 )
  for c in pageinspect pgstattuple pg_freespacemap btree_gin pg_trgm; do
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
  q postgres "SELECT /* wiki_gin_norm_hello */ version()" | tee -a "$OUT/version.txt"
  q postgres "SELECT /* wiki_gin_norm_settings */ name || ' = ' || setting || ' [' || context || ']'
                FROM pg_settings
               WHERE name IN ('autovacuum','block_size','gin_pending_list_limit','maintenance_work_mem',
                              'shared_buffers','stats_fetch_consistency','autovacuum_analyze_threshold',
                              'autovacuum_analyze_scale_factor','autovacuum_vacuum_threshold',
                              'autovacuum_vacuum_scale_factor','autovacuum_vacuum_insert_threshold',
                              'autovacuum_vacuum_insert_scale_factor','autovacuum_naptime',
                              'statement_timeout','lock_timeout')
               ORDER BY name" | tee "$OUT/settings.txt"
}

# ------------------------------------------------------------- stage: declare
# Files the declared kind of every published column BEFORE any fixture exists.
# The protocol forbids rewriting a declaration after the run, so this stage
# refuses to run once the fixture database is there.
stage_declare() {
  say "declare: the kind of every published column, filed before the first fixture"
  if q postgres "SELECT /* wiki_gin_norm_guard */ count(*) FROM pg_database WHERE datname = '$DB'" \
     | grep -q '^1$'; then
    die "refusing to re-file declarations: database $DB already exists (run reset first)"
  fi
  q postgres "DROP /* wiki_gin_norm_declare */ DATABASE IF EXISTS $PDB" > /dev/null
  q postgres "CREATE /* wiki_gin_norm_declare */ DATABASE $PDB" > /dev/null
  qin "$PDB" <<'SQL'
-- DISPOSABLE bookkeeping objects.
CREATE /* wiki_gin_norm_declare */ TABLE declared_kind (
  column_name text primary key,
  declared_kind text not null check (declared_kind in ('lower bound','upper bound','level')),
  claim text not null,
  filed_at timestamptz not null default now()
);
INSERT /* wiki_gin_norm_declare */ INTO declared_kind (column_name, declared_kind, claim) VALUES
 ('est_reclaimable',         'upper bound', 'the bytes it names are never fewer than the bytes REINDEX INDEX returns'),
 ('normalized_index_growth', 'level',       'a ranking statistic; no claim against the oracle'),
 ('index_size_ratio',        'level',       'current over baseline file size; no claim against the oracle'),
 ('heap_tuple_ratio',        'level',       'current over baseline table reltuples; no claim against the oracle'),
 ('churn_ratio',             'level',       'write volume over baseline reltuples; no claim against the oracle'),
 ('stats_lag',               'level',       'advisory staleness reading; no claim against the oracle'),
 ('cur_size',                'level',       'the current file size itself'),
 ('base_size',               'level',       'the stored baseline file size itself'),
 ('cur_heap_reltuples',      'level',       'the table row estimate itself'),
 ('base_heap_reltuples',     'level',       'the stored baseline row estimate itself');

CREATE /* wiki_gin_norm_declare */ TABLE declared_decision (
  knob text primary key, value text not null, meaning text not null,
  filed_at timestamptz not null default now()
);
INSERT /* wiki_gin_norm_declare */ INTO declared_decision (knob, value, meaning) VALUES
 ('candidate',            'normalized_index_growth >= 1.50', 'the method flags a rebuild'),
 ('strong candidate',     'heap_tuple_ratio <= 0.50 AND index_size_ratio >= 0.75', 'the method flags a rebuild'),
 ('watch',                'normalized_index_growth >= 1.20', 'the method does NOT flag a rebuild'),
 ('churn gate',           'churn_ratio >= 0.20', 'below this the method refuses to evaluate'),
 ('oracle justification', 'truth_pct >= 33.33', 'a rebuild is worth it, = 100 * (1 - 1/1.50), the method''s own threshold carried to the oracle side');

CREATE /* wiki_gin_norm_declare */ TABLE declared_invariant (
  id text primary key, claim text not null, filed_at timestamptz not null default now()
);
INSERT /* wiki_gin_norm_declare */ INTO declared_invariant (id, claim) VALUES
 ('I1', 'index_size_ratio >= 1 on every fixture that was not rebuilt since its baseline'),
 ('I2', 'a freshly built index satisfies n_total_pages = n_entry_pages + n_data_pages + n_pending_pages + 1'),
 ('I3', 'the FSM free-page count never exceeds the census new-plus-deleted page count'),
 ('I4', 'pg_relation_size re-read after the page census equals the blocks the census scanned'),
 ('I5', 'the fourth number of the VACUUM VERBOSE index line equals the census new-plus-deleted count'),
 ('I6', 'n_total_pages = 1 + census entry + census data + census list + census new-plus-deleted'),
 ('I7', 'the maintenance was not defeated: every settle and maintenance VACUUM reports 0 tuples dead but not yet removable, on every VERBOSE block, except the fixture that declares a snapshot held across its settling VACUUM, where the count is nonzero under the snapshot and 0 on the VACUUM after its release'),
 ('I8', 'every settle and maintenance step ran with statement_timeout, lock_timeout, transaction_timeout and idle_in_transaction_session_timeout all 0, completed with its own command tag, and produced no skipping or cancellation line'),
 ('I9', 'no page census saw a row in pg_stat_progress_vacuum, pg_stat_progress_analyze or pg_stat_progress_create_index for its relation at either end of its scan');
SQL
  q "$PDB" "SELECT /* wiki_gin_norm_declare */ column_name || ' -> ' || declared_kind || ' @ ' ||
              to_char(filed_at, 'YYYY-MM-DD HH24:MI:SS') FROM declared_kind ORDER BY 1" \
    | tee "$OUT/declared_kind.txt"
  q "$PDB" "SELECT /* wiki_gin_norm_declare */ knob || ': ' || value FROM declared_decision ORDER BY 1" \
    | tee "$OUT/declared_decision.txt"
  q "$PDB" "SELECT /* wiki_gin_norm_declare */ id || ': ' || claim FROM declared_invariant ORDER BY 1" \
    | tee "$OUT/declared_invariant.txt"
  date -u +'declarations filed at %Y-%m-%dT%H:%M:%SZ' | tee "$OUT/declared_at.txt"
}

stage_reset() {
  say "reset: drop both databases so a re-run starts clean"
  if "$BIN/pg_ctl" -D "$PGDATA" status > /dev/null 2>&1; then
    q postgres "DROP /* wiki_gin_norm_reset */ DATABASE IF EXISTS $DB" > /dev/null
    q postgres "DROP /* wiki_gin_norm_reset */ DATABASE IF EXISTS $PDB" > /dev/null
    q postgres "DROP /* wiki_gin_norm_reset */ DATABASE IF EXISTS pubsql" > /dev/null
  fi
}

# ------------------------------------------------------- fixture bookkeeping
# Every fixture object below is DISPOSABLE: created by this script, dropped
# with the sandbox.
SCORED="c01 c02 c03 c04 c05 c06 c09 c10 c11 c12 p01 p02 m01 a01 a02 s01 o01 o02 o03 x01 x02 x03 k01"
UNSCORED="e01"
tbl() { printf 'f_%s' "$1"; }
idx() { printf 'f_%s_gin' "$1"; }

proto_ddl() {
  cat <<'SQL'
CREATE /* wiki_gin_norm_proto */ SCHEMA proto;
CREATE /* wiki_gin_norm_proto */ EXTENSION pageinspect;
CREATE /* wiki_gin_norm_proto */ EXTENSION pgstattuple;
CREATE /* wiki_gin_norm_proto */ EXTENSION pg_freespacemap;
CREATE /* wiki_gin_norm_proto */ EXTENSION pg_trgm;
CREATE /* wiki_gin_norm_proto */ EXTENSION btree_gin;

CREATE TABLE proto.meas (
  fixture text not null, phase text not null, metric text not null,
  num numeric, txt text, at timestamptz not null default clock_timestamp()
);

-- one row per settle or maintenance step, holding the proofs that it was not
-- defeated: that it completed and was not skipped, its own
-- dead-but-not-yet-removable count, the timeouts it ran under, the horizon
-- reading on each side of it, and the entry-side page classes it left behind
CREATE TABLE proto.maint (
  fixture text not null, tag text not null, kind text not null,
  dead_not_removable bigint, dead_blocks_nonzero int,
  verbose_blocks int, skip_lines int, cancel_lines int,
  command_tags int, session_timeouts text,
  num_pages bigint, newly_deleted bigint, pages_deleted bigint, pages_free bigint,
  horizon_before text, horizon_after text,
  at timestamptz not null default clock_timestamp()
);

CREATE FUNCTION proto.note(p_fix text, p_phase text, p_metric text,
                           p_num numeric DEFAULT NULL, p_txt text DEFAULT NULL)
RETURNS void LANGUAGE sql AS $fn$
  INSERT INTO proto.meas(fixture,phase,metric,num,txt)
  VALUES (p_fix,p_phase,p_metric,p_num,p_txt);
$fn$;

-- five keys per row, drawn from a p_keys-wide universe by a deterministic hash
CREATE FUNCTION proto.mk_tags(p_tab text, p_lo bigint, p_hi bigint,
                              p_keybase int, p_keys int)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  EXECUTE format($q$INSERT INTO %I (id, tags) SELECT i, ARRAY[
      $1 + ((i *     7919) %% $2)::int, $1 + ((i *   104729) %% $2)::int,
      $1 + ((i *  1299709) %% $2)::int, $1 + ((i * 15485863) %% $2)::int,
      $1 + ((i * 32452843) %% $2)::int] FROM generate_series($3, $4) i$q$, p_tab)
    USING p_keybase, p_keys, p_lo, p_hi;
END $fn$;

-- rewrite every matching row's keys, from the same universe, under a new salt
CREATE FUNCTION proto.churn_tags(p_tab text, p_salt int, p_where text,
                                 p_keybase int, p_keys int)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  EXECUTE format($q$UPDATE %I SET tags = ARRAY[
      $1 + (((id + $2) *     7919) %% $3)::int, $1 + (((id + $2) *   104729) %% $3)::int,
      $1 + (((id + $2) *  1299709) %% $3)::int, $1 + (((id + $2) * 15485863) %% $3)::int,
      $1 + (((id + $2) * 32452843) %% $3)::int] WHERE %s$q$, p_tab, p_where)
    USING p_keybase, p_salt, p_keys;
END $fn$;

-- one key per p_per_key contiguous rows, so deleting an id range retires whole keys
CREATE FUNCTION proto.mk_keyband(p_tab text, p_lo bigint, p_hi bigint, p_per_key int)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  EXECUTE format($q$INSERT INTO %I (id, tags)
      SELECT i, ARRAY[(i / $1)::int] FROM generate_series($2, $3) i$q$, p_tab)
    USING p_per_key, p_lo, p_hi;
END $fn$;

-- five words per row from a p_words-wide vocabulary, plus a tsvector
CREATE FUNCTION proto.mk_docs(p_tab text, p_lo bigint, p_hi bigint, p_words int)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  EXECUTE format($q$INSERT INTO %I (id, txt, doc)
      SELECT i, t, to_tsvector('simple', t) FROM (
        SELECT i, concat_ws(' ',
          'w' || ((i *     7919) %% $1), 'w' || ((i *   104729) %% $1),
          'w' || ((i *  1299709) %% $1), 'w' || ((i * 15485863) %% $1),
          'w' || ((i * 32452843) %% $1)) AS t
          FROM generate_series($2, $3) i) s$q$, p_tab)
    USING p_words, p_lo, p_hi;
END $fn$;

CREATE FUNCTION proto.churn_docs(p_tab text, p_salt int, p_where text, p_words int)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  EXECUTE format($q$UPDATE %I SET txt = s.t, doc = to_tsvector('simple', s.t)
      FROM (SELECT id AS sid, concat_ws(' ',
          'w' || (((id + $1) *     7919) %% $2), 'w' || (((id + $1) *   104729) %% $2),
          'w' || (((id + $1) *  1299709) %% $2), 'w' || (((id + $1) * 15485863) %% $2),
          'w' || (((id + $1) * 32452843) %% $2)) AS t FROM %I WHERE %s) s
      WHERE id = s.sid$q$, p_tab, p_tab, p_where)
    USING p_salt, p_words;
END $fn$;

CREATE FUNCTION proto.mk_json(p_tab text, p_lo bigint, p_hi bigint, p_words int)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  EXECUTE format($q$INSERT INTO %I (id, j)
      SELECT i, jsonb_build_object('tags', to_jsonb(ARRAY[
          'w' || ((i *     7919) %% $1), 'w' || ((i *   104729) %% $1),
          'w' || ((i *  1299709) %% $1), 'w' || ((i * 15485863) %% $1),
          'w' || ((i * 32452843) %% $1)]))
        FROM generate_series($2, $3) i$q$, p_tab)
    USING p_words, p_lo, p_hi;
END $fn$;

CREATE FUNCTION proto.churn_json(p_tab text, p_salt int, p_where text, p_words int)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  EXECUTE format($q$UPDATE %I SET j = jsonb_build_object('tags', to_jsonb(ARRAY[
          'w' || (((id + $1) *     7919) %% $2), 'w' || (((id + $1) *   104729) %% $2),
          'w' || (((id + $1) *  1299709) %% $2), 'w' || (((id + $1) * 15485863) %% $2),
          'w' || (((id + $1) * 32452843) %% $2)])) WHERE %s$q$, p_tab, p_where)
    USING p_salt, p_words;
END $fn$;

-- one reading of everything the method and the cross-checks can see
CREATE FUNCTION proto.record(p_fix text, p_phase text, p_tab text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  m record; s record; ct record; ci record;
  blk int := current_setting('block_size')::int;
BEGIN
  SELECT * INTO m FROM gin_metapage_info(get_raw_page(p_idx, 0));
  SELECT reltuples, relpages INTO ct FROM pg_class WHERE oid = p_tab::regclass;
  SELECT reltuples, relpages, relfilenode INTO ci FROM pg_class WHERE oid = p_idx::regclass;
  SELECT n_tup_ins, n_tup_upd, n_tup_del, n_live_tup, n_dead_tup, n_mod_since_analyze,
         n_ins_since_vacuum, analyze_count, autoanalyze_count, vacuum_count
    INTO s FROM pg_stat_all_tables WHERE relid = p_tab::regclass;
  INSERT INTO proto.meas(fixture,phase,metric,num) VALUES
    (p_fix,p_phase,'index_size',          pg_relation_size(p_idx::regclass,'main')),
    (p_fix,p_phase,'index_blocks',        pg_relation_size(p_idx::regclass,'main')/blk),
    (p_fix,p_phase,'table_size',          pg_relation_size(p_tab::regclass,'main')),
    (p_fix,p_phase,'meta_total',          m.n_total_pages),
    (p_fix,p_phase,'meta_entry',          m.n_entry_pages),
    (p_fix,p_phase,'meta_data',           m.n_data_pages),
    (p_fix,p_phase,'meta_pending',        m.n_pending_pages),
    (p_fix,p_phase,'meta_pending_tuples', m.n_pending_tuples),
    (p_fix,p_phase,'meta_entries',        m.n_entries),
    (p_fix,p_phase,'meta_version',        m.version),
    (p_fix,p_phase,'tab_reltuples',       ct.reltuples),
    (p_fix,p_phase,'tab_relpages',        ct.relpages),
    (p_fix,p_phase,'idx_reltuples',       ci.reltuples),
    (p_fix,p_phase,'idx_relpages',        ci.relpages),
    (p_fix,p_phase,'idx_relfilenode',     ci.relfilenode::bigint),
    (p_fix,p_phase,'n_tup_ins',           coalesce(s.n_tup_ins,0)),
    (p_fix,p_phase,'n_tup_upd',           coalesce(s.n_tup_upd,0)),
    (p_fix,p_phase,'n_tup_del',           coalesce(s.n_tup_del,0)),
    (p_fix,p_phase,'n_live_tup',          coalesce(s.n_live_tup,0)),
    (p_fix,p_phase,'n_dead_tup',          coalesce(s.n_dead_tup,0)),
    (p_fix,p_phase,'n_mod_since_analyze', coalesce(s.n_mod_since_analyze,0)),
    (p_fix,p_phase,'n_ins_since_vacuum',  coalesce(s.n_ins_since_vacuum,0)),
    (p_fix,p_phase,'analyze_count',       coalesce(s.analyze_count,0)+coalesce(s.autoanalyze_count,0)),
    (p_fix,p_phase,'vacuum_count',        coalesce(s.vacuum_count,0));
END $fn$;

-- the page census and the two cross-checks that need it, under the caller's lock
CREATE FUNCTION proto.pagecensus(p_fix text, p_phase text, p_idx text)
RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
  blocks bigint; blk int := current_setting('block_size')::int;
  r record; fsm record; after bigint;
  tab oid; prog_before int; prog_after int;
BEGIN
  blocks := pg_relation_size(p_idx::regclass,'main') / blk;
  -- the concurrency rule: what the three progress views could see about this
  -- relation at either end of the scan. A command that starts and finishes
  -- between the two reads leaves no trace in either, so an unflagged census is
  -- unrefuted rather than proven.
  SELECT indrelid INTO tab FROM pg_index WHERE indexrelid = p_idx::regclass;
  SELECT (SELECT count(*) FROM pg_stat_progress_vacuum  WHERE relid = tab)
       + (SELECT count(*) FROM pg_stat_progress_analyze WHERE relid = tab)
       + (SELECT count(*) FROM pg_stat_progress_create_index
           WHERE relid = tab OR index_relid = p_idx::regclass) INTO prog_before;
  SELECT
    count(*) FILTER (WHERE fl IS NULL)                              AS new_pages,
    count(*) FILTER (WHERE fl @> ARRAY['deleted'])                  AS deleted_pages,
    count(*) FILTER (WHERE fl @> ARRAY['deleted'] AND px = 0)       AS deleted_noxid,
    count(*) FILTER (WHERE fl IS NOT NULL AND NOT fl @> ARRAY['deleted']
                       AND fl @> ARRAY['list'])                     AS list_pages,
    count(*) FILTER (WHERE fl IS NOT NULL AND NOT fl @> ARRAY['deleted']
                       AND fl @> ARRAY['data'] AND fl @> ARRAY['leaf'])     AS data_leaf,
    count(*) FILTER (WHERE fl IS NOT NULL AND NOT fl @> ARRAY['deleted']
                       AND fl @> ARRAY['data'] AND NOT fl @> ARRAY['leaf']) AS data_inner,
    count(*) FILTER (WHERE fl IS NOT NULL AND NOT fl @> ARRAY['deleted']
                       AND NOT fl @> ARRAY['data'] AND NOT fl @> ARRAY['list']) AS entry_pages,
    count(*) AS scanned
    INTO r
    FROM (SELECT (gin_page_opaque_info(get_raw_page(p_idx, b::int))).flags AS fl,
                 (page_header(get_raw_page(p_idx, b::int))).prune_xid      AS px
            FROM generate_series(1, blocks - 1) b) p;
  SELECT count(*) FILTER (WHERE avail > 0) AS free_pages, max(avail) AS max_avail
    INTO fsm FROM pg_freespace(p_idx::regclass);
  after := pg_relation_size(p_idx::regclass,'main') / blk;
  SELECT (SELECT count(*) FROM pg_stat_progress_vacuum  WHERE relid = tab)
       + (SELECT count(*) FROM pg_stat_progress_analyze WHERE relid = tab)
       + (SELECT count(*) FROM pg_stat_progress_create_index
           WHERE relid = tab OR index_relid = p_idx::regclass) INTO prog_after;
  INSERT INTO proto.meas(fixture,phase,metric,num) VALUES
    (p_fix,p_phase,'progress_rows_before', prog_before),
    (p_fix,p_phase,'progress_rows_after',  prog_after),
    (p_fix,p_phase,'census_scanned',     r.scanned),
    (p_fix,p_phase,'census_new',         r.new_pages),
    (p_fix,p_phase,'census_deleted',     r.deleted_pages),
    (p_fix,p_phase,'census_deleted_noxid', r.deleted_noxid),
    (p_fix,p_phase,'census_list',        r.list_pages),
    (p_fix,p_phase,'census_data_leaf',   r.data_leaf),
    (p_fix,p_phase,'census_data_inner',  r.data_inner),
    (p_fix,p_phase,'census_entry',       r.entry_pages),
    (p_fix,p_phase,'census_recyclable',  r.new_pages + r.deleted_pages),
    (p_fix,p_phase,'fsm_free_pages',     fsm.free_pages),
    (p_fix,p_phase,'fsm_max_avail',      coalesce(fsm.max_avail,0)),
    (p_fix,p_phase,'bracket_blocks_before', blocks),
    (p_fix,p_phase,'bracket_blocks_after',  after);
END $fn$;
SQL
}

build_sql() { # $1 = fixture id; prints the whole build phase for that fixture
  local f=$1 t; t=$(tbl "$f")
  case "$f" in
    c01|c02|c03|c04|c05|c09|c11|c12|m01)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, tags int[]);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_tags('%s', 1, %s, 0, %s);\n" "$t" "$(rows_for "$f")" "$KEYS"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (tags);\n" "$(idx "$f")" "$t" ;;
    s01)
      # few keys, so every key's posting list becomes a posting tree: deleting a
      # contiguous id range then empties whole data pages
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, tags int[]);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_keyband('%s', 1, %s, 100000);\n" "$t" "$(rows_for "$f")"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (tags);\n" "$(idx "$f")" "$t" ;;
    c06)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, tags int[]);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_tags('%s', 1, %s, 0, %s);\n" "$t" "$BASE_ROWS" "$KEYS"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (tags);\n" "$(idx "$f")" "$t" ;;
    p01|p02)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, tags int[]);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_tags('%s', 1, %s, 0, %s);\n" "$t" "$PEND_ROWS" "$KEYS"
      if [ "$f" = p01 ]; then
        printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (tags) WITH (fastupdate = on);\n" "$(idx "$f")" "$t"
      else
        printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (tags) WITH (fastupdate = off);\n" "$(idx "$f")" "$t"
      fi ;;
    a01|a02)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, tags int[]);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_tags('%s', 1, %s, 0, %s);\n" "$t" "$SMALL_ROWS" "$KEYS"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (tags) WITH (fastupdate = on);\n" "$(idx "$f")" "$t" ;;
    c10)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, txt text, doc tsvector);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_docs('%s', 1, %s, %s);\n" "$t" "$SMALL_ROWS" "$KEYS"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (doc);\n" "$(idx "$f")" "$t" ;;
    o01)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, j jsonb);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_json('%s', 1, %s, %s);\n" "$t" "$SMALL_ROWS" "$KEYS"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (j jsonb_path_ops);\n" "$(idx "$f")" "$t" ;;
    o02)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, txt text, doc tsvector);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_docs('%s', 1, %s, %s);\n" "$t" "$TRGM_ROWS" "$KEYS"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (txt gin_trgm_ops);\n" "$(idx "$f")" "$t" ;;
    o03)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, n int);\n" "$t"
      printf "INSERT /* wiki_gin_norm_fixture */ INTO %s (id, n) SELECT i, (i %% %s)::int FROM generate_series(1, %s) i;\n" "$t" "$KEYS" "$SMALL_ROWS"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (n);\n" "$(idx "$f")" "$t" ;;
    x01)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, tags int[]);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_tags('%s', 1, %s, 0, %s);\n" "$t" "$SMALL_ROWS" "$KEYS"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (tags) WHERE id %% 4 = 0;\n" "$(idx "$f")" "$t" ;;
    x02)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, tags int[], tags2 int[]);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_tags('%s', 1, %s, 0, %s);\n" "$t" "$SMALL_ROWS" "$KEYS"
      printf "UPDATE /* wiki_gin_norm_fixture */ %s SET tags2 = ARRAY[(id %% %s)::int];\n" "$t" "$KEYS"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (tags, tags2);\n" "$(idx "$f")" "$t" ;;
    x03)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, tags int[]);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_tags('%s', 1, %s, 0, %s);\n" "$t" "$SMALL_ROWS" "$KEYS"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin ((tags[1:3]));\n" "$(idx "$f")" "$t" ;;
    k01)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, tags int[]);\n" "$t"
      printf "SELECT /* wiki_gin_norm_fixture */ proto.mk_keyband('%s', 1, %s, 100);\n" "$t" "$SMALL_ROWS"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (tags);\n" "$(idx "$f")" "$t" ;;
    e01)
      printf "CREATE /* wiki_gin_norm_fixture */ TABLE %s (id bigint, tags int[]);\n" "$t"
      printf "CREATE /* wiki_gin_norm_fixture */ INDEX %s ON %s USING gin (tags);\n" "$(idx "$f")" "$t" ;;
  esac
}

rows_for() {
  case "$1" in
    c01|c02|c03|c04|c05|c06|c09|c11|c12|s01) printf '%s' "$BASE_ROWS" ;;
    p01|p02)                             printf '%s' "$PEND_ROWS" ;;
    o02)                                 printf '%s' "$TRGM_ROWS" ;;
    e01)                                 printf '0' ;;
    *)                                   printf '%s' "$SMALL_ROWS" ;;
  esac
}

churn_sql() { # $1 = fixture id; prints the recipe's own writes, nothing else
  local f=$1 t half; t=$(tbl "$f")
  case "$f" in
    c01) printf "SELECT /* wiki_gin_norm_churn */ proto.mk_tags('%s', %s, %s, 0, %s);\n" \
           "$t" "$((BASE_ROWS + 1))" "$((BASE_ROWS * 3 / 2))" "$KEYS" ;;
    c02) printf "SELECT /* wiki_gin_norm_churn */ proto.churn_tags('%s', 1, 'true', 0, %s);\n" "$t" "$KEYS"
         printf "SELECT /* wiki_gin_norm_churn */ proto.churn_tags('%s', 2, 'true', 0, %s);\n" "$t" "$KEYS" ;;
    c03) printf "DELETE /* wiki_gin_norm_churn */ FROM %s WHERE id %% 5 < 3;\n" "$t" ;;
    c04) printf "SELECT /* wiki_gin_norm_churn */ 'no churn: control cell';\n" ;;
    c05) printf "SELECT /* wiki_gin_norm_churn */ proto.mk_tags('%s', %s, %s, 0, %s);\n" \
           "$t" "$((BASE_ROWS + 1))" "$((BASE_ROWS * 2))" "$KEYS" ;;
    c06) printf "SELECT /* wiki_gin_norm_churn */ proto.mk_tags('%s', %s, %s, %s, %s);\n" \
           "$t" "$((BASE_ROWS + 1))" "$((BASE_ROWS * 2))" "$KEYS" "$KEYS" ;;
    c09|c11) printf "SELECT /* wiki_gin_norm_churn */ proto.churn_tags('%s', 1, 'true', 0, %s);\n" "$t" "$KEYS" ;;
    c10) printf "SELECT /* wiki_gin_norm_churn */ proto.churn_docs('%s', 1, 'true', %s);\n" "$t" "$KEYS" ;;
    c12) half=$((BASE_ROWS / 2))
         printf "DELETE /* wiki_gin_norm_churn */ FROM %s WHERE id <= %s;\n" "$t" "$half"
         printf "SELECT /* wiki_gin_norm_churn */ proto.mk_tags('%s', %s, %s, 0, %s);\n" \
           "$t" "$((BASE_ROWS + 1))" "$((BASE_ROWS + half))" "$KEYS" ;;
    p01|p02) printf "SELECT /* wiki_gin_norm_churn */ proto.mk_tags('%s', %s, %s, 0, %s);\n" \
           "$t" "$((PEND_ROWS + 1))" "$((PEND_ROWS + PEND_ROWS / 4))" "$KEYS" ;;
    a01) printf "SELECT /* wiki_gin_norm_churn */ proto.mk_tags('%s', %s, %s, 0, %s);\n" \
           "$t" "$((SMALL_ROWS + 1))" "$((SMALL_ROWS + A01_INSERTS))" "$KEYS" ;;
    a02) printf "SELECT /* wiki_gin_norm_churn */ proto.mk_tags('%s', %s, %s, 0, %s);\n" \
           "$t" "$((SMALL_ROWS + 1))" "$((SMALL_ROWS + A02_INSERTS))" "$KEYS" ;;
    m01) printf "SELECT /* wiki_gin_norm_churn */ proto.churn_tags('%s', 1, 'true', 0, %s);\n" "$t" "$KEYS" ;;
    s01) printf "DELETE /* wiki_gin_norm_churn */ FROM %s WHERE id <= %s;\n" "$t" "$((BASE_ROWS / 2))" ;;
    o01) printf "SELECT /* wiki_gin_norm_churn */ proto.churn_json('%s', 1, 'true', %s);\n" "$t" "$KEYS" ;;
    o02) printf "SELECT /* wiki_gin_norm_churn */ proto.churn_docs('%s', 1, 'true', %s);\n" "$t" "$KEYS" ;;
    o03) printf "UPDATE /* wiki_gin_norm_churn */ %s SET n = ((id + 1) %% %s)::int;\n" "$t" "$KEYS" ;;
    x01|x03) printf "SELECT /* wiki_gin_norm_churn */ proto.churn_tags('%s', 1, 'true', 0, %s);\n" "$t" "$KEYS" ;;
    x02) printf "SELECT /* wiki_gin_norm_churn */ proto.churn_tags('%s', 1, 'true', 0, %s);\n" "$t" "$KEYS" ;;
    k01) printf "DELETE /* wiki_gin_norm_churn */ FROM %s WHERE id <= %s;\n" "$t" "$((SMALL_ROWS / 2))" ;;
    e01) printf "SELECT /* wiki_gin_norm_churn */ 'no churn: empty fixture';\n" ;;
  esac
}

# ----------------------------------------------------------- stage: fixtures
# build phase (create, load, index, settle) and baseline phase (record + capture)
stage_fixtures() {
  say "fixtures: build and baseline phases"
  [ -f "$OUT/declared_kind.txt" ] || die "declare must run before fixtures"
  q postgres "DROP /* wiki_gin_norm_fixture */ DATABASE IF EXISTS $DB" > /dev/null
  q postgres "CREATE /* wiki_gin_norm_fixture */ DATABASE $DB" > /dev/null
  proto_ddl | qin "$DB" > "$OUT/proto-ddl.log" 2>&1 || die "proto DDL failed"
  write_published_sql

  for f in $SCORED $UNSCORED; do
    local t i
    t=$(tbl "$f"); i=$(idx "$f")
    printf '  build %s (%s rows)\n' "$f" "$(rows_for "$f")"
    { build_sql "$f"; } | qin "$DB" > "$OUT/build-$f.log" 2>&1 || die "build failed for $f"
    # build-phase settle: VACUUM settles the index, ANALYZE gives the table a row
    # estimate. It is a maintenance step, so it runs and is proved like one.
    run_maint "$DB" "$f" settle_build "VACUUM /* wiki_gin_norm_settle_build */ (VERBOSE, ANALYZE) $t;"
    check_maint "$f" settle_build strict
    q "$DB" "SELECT /* wiki_gin_norm_record */ proto.record('$f','baseline','$t','$i')" > /dev/null \
      || die "baseline record failed for $f"
    if [ "$f" = e01 ]; then
      # the empty fixture is expected to be refused: record the refusal text
      sed "s/public\.orders_tags_gin/$i/" "$SQLD/capture.sql" > "$SQLD/.capture_run.sql"
      qf "$DB" "$SQLD/.capture_run.sql" > "$OUT/capture-$f.log" 2>&1
      printf '    capture refused as expected: %s\n' \
        "$(grep -o 'refusing baseline for [^"]*' "$OUT/capture-$f.log" | head -1)"
      q "$DB" "SELECT /* wiki_gin_norm_record */ proto.note('$f','baseline','capture_refused',NULL,
                 \$\$$(grep -o 'refusing baseline for .*' "$OUT/capture-$f.log" | head -1)\$\$)" > /dev/null
    else
      capture_for "$i"
      q "$DB" "SELECT /* wiki_gin_norm_record */ proto.note('$f','baseline','payload',NULL,
                 substring(coalesce(obj_description('$i'::regclass,'pg_class'),'') from '@ginbase:(\{[^}]*\})'))" > /dev/null
    fi
  done
  q "$DB" "SELECT /* wiki_gin_norm_report */ fixture || ' ' || num FROM proto.meas
             WHERE phase='baseline' AND metric='index_size' ORDER BY fixture" \
    | tee "$OUT/baseline-sizes.txt"
}

# -------------------------------------------------------------- stage: churn
# recipe writes -> settle step -> maintenance step. The census is the next stage.
stage_churn() {
  say "churn: writes, then the settle step, then the maintenance step"
  for f in $SCORED $UNSCORED; do
    local t i
    t=$(tbl "$f"); i=$(idx "$f")
    printf '  churn %s\n' "$f"
    if [ "$f" = s01 ]; then
      # a snapshot is held across the settling VACUUM, so deleted pages stay
      # un-recyclable: the writer below keeps a repeatable-read snapshot open
      ( q "$DB" "BEGIN /* wiki_gin_norm_snapshot */ ISOLATION LEVEL REPEATABLE READ;
                 SELECT /* wiki_gin_norm_snapshot */ count(*) FROM $t;
                 SELECT /* wiki_gin_norm_snapshot */ pg_sleep(45);
                 COMMIT;" > "$OUT/snapshot-s01.log" 2>&1 ) &
      sleep 3
      q "$DB" "SELECT /* wiki_gin_norm_record */ proto.note('s01','churn','holder_backend_xmin',NULL,
                 (SELECT count(*)::text FROM pg_stat_activity
                   WHERE backend_xmin IS NOT NULL AND datname = '$DB'))" > /dev/null
    fi
    { churn_sql "$f"; printf "SELECT /* wiki_gin_norm_flush */ pg_stat_force_next_flush();\n"; } \
      | qin "$DB" > "$OUT/churn-$f.log" 2>&1 || die "churn failed for $f"
    q "$DB" "SELECT /* wiki_gin_norm_record */ proto.record('$f','churn_written','$t','$i')" > /dev/null

    if [ "$f" = a01 ] || [ "$f" = a02 ]; then
      # the auto-analyze stand-in: ANALYZE plus the flush only a worker would do.
      # Such a fixture carries stale metapage page counts by construction. Both
      # halves are this fixture's declared maintenance, so both run in the
      # timeouts-at-zero session.
      run_maint "$DB" "$f" standin "ANALYZE /* wiki_gin_norm_standin */ $t;
SELECT /* wiki_gin_norm_standin */ proto.note('$f','churn','pending_pages_flushed',
         (SELECT gin_clean_pending_list('$i')));"
      check_maint "$f" standin analyze
      q "$DB" "SELECT /* wiki_gin_norm_record */ proto.record('$f','churn_maintained','$t','$i')" > /dev/null
      continue
    fi

    if [ "$f" = m01 ]; then
      # half A of the maintenance pair: the same churn, measured before the
      # settle step. Evidence only: the protocol does not score this state.
      q "$DB" "SELECT /* wiki_gin_norm_record */ proto.pagecensus('m01','churn_written','$i')" > /dev/null
    fi
    run_maint "$DB" "$f" settle "VACUUM /* wiki_gin_norm_settle */ (VERBOSE) $t;"
    # s01 is the fixture the protocol declares as an exception: its settle step
    # runs with the horizon pinned on purpose, so a nonzero count there is
    # required rather than forbidden, and the reading is published as a
    # held-horizon reading
    if [ "$f" = s01 ]; then check_maint s01 settle declared; else check_maint "$f" settle strict; fi
    q "$DB" "SELECT /* wiki_gin_norm_record */ proto.record('$f','churn_settled','$t','$i')" > /dev/null
    if [ "$f" = s01 ]; then
      # census while the holder's snapshot is still open: pages are deleted but
      # GinPageIsRecyclable refuses them, so the FSM does not have them yet
      q "$DB" "SELECT /* wiki_gin_norm_record */ proto.pagecensus('s01','churn_settled','$i')" > /dev/null
      wait
      run_maint "$DB" s01 settle2 "VACUUM /* wiki_gin_norm_settle2 */ (VERBOSE) $t;"
      check_maint s01 settle2 strict
      q "$DB" "SELECT /* wiki_gin_norm_record */ proto.record('s01','churn_settled2','$t','$i')" > /dev/null
      q "$DB" "SELECT /* wiki_gin_norm_record */ proto.pagecensus('s01','churn_settled2','$i')" > /dev/null
    fi
    run_maint "$DB" "$f" maint "VACUUM /* wiki_gin_norm_maintenance */ (VERBOSE, ANALYZE) $t;"
    # check_maint also records cross-check 3, the fourth number of this step's
    # own index line
    check_maint "$f" maint strict
    q "$DB" "SELECT /* wiki_gin_norm_record */ proto.record('$f','churn_maintained','$t','$i')" > /dev/null
    if [ "$f" = c09 ]; then
      # out-of-band rebuild after the maintenance step: the ladder must notice
      Q "$DB" "REINDEX /* wiki_gin_norm_outofband */ INDEX $i;" > "$OUT/outofband-c09.log" 2>&1
      q "$DB" "SELECT /* wiki_gin_norm_record */ proto.record('c09','churn_rebuilt','$t','$i')" > /dev/null
    fi
    if [ "$f" = c11 ]; then
      q "$DB" "SELECT /* wiki_gin_norm_reset_counters */ pg_stat_reset_single_table_counters('$t'::regclass)" > /dev/null
      q "$DB" "SELECT /* wiki_gin_norm_record */ proto.record('c11','churn_counters_reset','$t','$i')" > /dev/null
    fi
  done
}

# --------------------------------------------- stage: simulated analyze census
# Recomputes relation_needs_vacanalyze's analyze verdict per table from the
# effective reloption-or-GUC values, and analyzes the tables it names.
stage_analyze_census() {
  say "analyze census: the launcher's analyze verdict, recomputed per table"
  # two tables the census must decide: one past its threshold, one exactly on it
  for t in tc_past tc_exact tc_off; do
    q "$DB" "DROP /* wiki_gin_norm_census */ TABLE IF EXISTS $t" > /dev/null
  done
  q "$DB" "CREATE /* wiki_gin_norm_census */ TABLE tc_past (id bigint, tags int[])" > /dev/null
  q "$DB" "CREATE /* wiki_gin_norm_census */ TABLE tc_exact (id bigint, tags int[])" > /dev/null
  q "$DB" "CREATE /* wiki_gin_norm_census */ TABLE tc_off (id bigint, tags int[])
             WITH (autovacuum_enabled = false)" > /dev/null
  # build each to a known reltuples. The flush comes BEFORE the ANALYZE: a reset
  # counter that is then handed the build's own pending counts reads as churn
  # that never happened, which is the protocol's first publication point.
  qin "$DB" <<SQL > "$OUT/census-build.log" 2>&1
SELECT /* wiki_gin_norm_census */ proto.mk_tags('tc_past',  1, 10000, 0, $KEYS);
SELECT /* wiki_gin_norm_census */ proto.mk_tags('tc_exact', 1, 10000, 0, $KEYS);
SELECT /* wiki_gin_norm_census */ proto.mk_tags('tc_off',   1, 10000, 0, $KEYS);
SELECT /* wiki_gin_norm_census */ pg_stat_force_next_flush();
ANALYZE /* wiki_gin_norm_census */ tc_past, tc_exact, tc_off;
SELECT /* wiki_gin_norm_census */ pg_stat_force_next_flush();
SQL
  # thresholds at the shipped defaults are 50 + 0.1 * reltuples = 1050 for 10000 rows;
  # tc_past crosses it, tc_exact lands exactly on it, tc_off is short-circuited
  qin "$DB" <<SQL > "$OUT/census-push.log" 2>&1
UPDATE /* wiki_gin_norm_census */ tc_past  SET tags = tags WHERE id <= 2000;
UPDATE /* wiki_gin_norm_census */ tc_exact SET tags = tags WHERE id <= 1050;
UPDATE /* wiki_gin_norm_census */ tc_off   SET tags = tags WHERE id <= 2000;
SELECT /* wiki_gin_norm_census */ pg_stat_force_next_flush();
SQL
  q "$DB" "SELECT /* wiki_gin_norm_census */ pg_stat_clear_snapshot()" > /dev/null
  qat "$DB" /dev/stdin > "$OUT/census-verdicts.txt" 2>&1 <<'SQL'
SELECT /* wiki_gin_norm_census */
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
  # analyze exactly the tables the census named
  qat "$DB" /dev/stdin > "$OUT/census-analyzed.txt" 2>&1 <<'SQL'
SELECT /* wiki_gin_norm_census */ 'ANALYZE ' || quote_ident(c.relname) || ';'
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
  # the census's own ANALYZE is maintenance too, so it runs in the same
  # timeouts-at-zero session and is proved the same way
  run_maint "$DB" census analyze_census "$(grep 'ANALYZE' "$OUT/census-analyzed.txt")"
  check_maint census analyze_census analyze
  q "$DB" "SELECT /* wiki_gin_norm_census */ pg_stat_clear_snapshot()" > /dev/null
  grep -E 'tc_past|tc_exact|tc_off' "$OUT/census-verdicts.txt"
}

# ------------------------------------------------- stage: the four cross-checks
stage_crosscheck() {
  say "cross-checks: page census under SHARE ROW EXCLUSIVE, FSM, bracket, metapage"
  for f in $SCORED; do
    local t i ph
    t=$(tbl "$f"); i=$(idx "$f")
    # c09 was rebuilt out of band after its maintenance step, so the state this
    # census reads is that rebuild, not the churned file
    ph=churn_maintained
    [ "$f" = c09 ] && ph=churn_rebuilt
    printf '  census %s (%s)\n' "$f" "$ph"
    qin "$DB" > "$OUT/crosscheck-$f.log" 2>&1 <<SQL
BEGIN;
SET LOCAL statement_timeout = '600s';
SET LOCAL lock_timeout = '15s';
LOCK /* wiki_gin_norm_crosscheck */ TABLE $t IN SHARE ROW EXCLUSIVE MODE;
SELECT /* wiki_gin_norm_crosscheck */ proto.pagecensus('$f','$ph','$i');
COMMIT;
SQL
  done
  q "$DB" "SELECT /* wiki_gin_norm_report */ fixture
             || ' scanned=' || max(num) FILTER (WHERE metric='census_scanned')
             || ' entry=' || max(num) FILTER (WHERE metric='census_entry')
             || ' data=' || (max(num) FILTER (WHERE metric='census_data_leaf')
                           + max(num) FILTER (WHERE metric='census_data_inner'))
             || ' list=' || max(num) FILTER (WHERE metric='census_list')
             || ' del=' || max(num) FILTER (WHERE metric='census_deleted')
             || ' new=' || max(num) FILTER (WHERE metric='census_new')
             || ' fsm=' || max(num) FILTER (WHERE metric='fsm_free_pages')
             || ' fsm_avail=' || max(num) FILTER (WHERE metric='fsm_max_avail')
             FROM proto.meas WHERE phase IN ('churn_maintained','churn_rebuilt')
             GROUP BY fixture HAVING count(*) FILTER (WHERE metric='census_scanned') > 0
             ORDER BY fixture" \
    | tee "$OUT/census-summary.txt"
}

# -------------------------------------------------------------- stage: decide
# One pass of the published statement, verbatim, inside one transaction holding
# SHARE ROW EXCLUSIVE on every fixture table. Nothing else runs in this phase.
stage_decide() {
  say "decide: the published statement under the measurement lock"
  local locks=""
  for f in $SCORED $UNSCORED; do locks="$locks$(tbl "$f"), "; done
  locks="${locks%, }"
  { printf "SET /* wiki_gin_norm_decide */ lock_timeout = '30s';\n"
    printf "BEGIN /* wiki_gin_norm_decide */;\n"
    printf "LOCK /* wiki_gin_norm_decide */ TABLE %s IN SHARE ROW EXCLUSIVE MODE;\n" "$locks"
    cat "$SQLD/evaluate.sql"
  } | "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$DB" \
      > "$OUT/decide.txt" 2>&1 || die "decide pass failed"
  # the same pass again, in expanded form, recorded per fixture for scoring
  { printf "SET /* wiki_gin_norm_decide */ lock_timeout = '30s';\n"
    printf "BEGIN /* wiki_gin_norm_decide */;\n"
    printf "LOCK /* wiki_gin_norm_decide */ TABLE %s IN SHARE ROW EXCLUSIVE MODE;\n" "$locks"
    printf "CREATE /* wiki_gin_norm_decide */ TABLE proto.decided AS\n"
    sed -e '1,3d' -e 's/^COMMIT;$//' "$SQLD/evaluate.sql"
    printf "COMMIT;\n"
  } | "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d "$DB" \
      > "$OUT/decide-store.log" 2>&1 || die "decide store failed"
  cat "$OUT/decide.txt"
}

# -------------------------------------------------------------- stage: oracle
stage_oracle() {
  say "oracle: measured REINDEX INDEX at maintenance_work_mem = $MWM"
  for f in $SCORED; do
    local i; i=$(idx "$f")
    printf '  reindex %s\n' "$f"
    qin "$DB" > "$OUT/oracle-$f.log" 2>&1 <<SQL
SET /* wiki_gin_norm_oracle */ maintenance_work_mem = '$MWM';
SELECT /* wiki_gin_norm_oracle */ proto.note('$f','oracle','size_before',
         pg_relation_size('$i'::regclass,'main'));
REINDEX /* wiki_gin_norm_oracle */ INDEX $i;
SELECT /* wiki_gin_norm_oracle */ proto.note('$f','oracle','size_after',
         pg_relation_size('$i'::regclass,'main'));
SELECT /* wiki_gin_norm_oracle */ proto.note('$f','oracle','mwm',NULL,
         current_setting('maintenance_work_mem'));
SQL
    q "$DB" "SELECT /* wiki_gin_norm_record */ proto.record('$f','oracle_after','$(tbl "$f")','$i')" > /dev/null
  done
  q "$DB" "SELECT /* wiki_gin_norm_report */ fixture || ' ' ||
             max(num) FILTER (WHERE metric='size_before') || ' -> ' ||
             max(num) FILTER (WHERE metric='size_after')  || ' = ' ||
             round(100.0 * (1 - max(num) FILTER (WHERE metric='size_after')
                              / max(num) FILTER (WHERE metric='size_before')), 2) || '%'
             FROM proto.meas WHERE phase='oracle' AND metric IN ('size_before','size_after')
             GROUP BY fixture ORDER BY fixture" | tee "$OUT/oracle-summary.txt"
}

# ------------------------------------------------- the no-defeat report, scored
# Prints every settle and maintenance step of the run with the four proofs the
# rule asks for, and refuses to let a defeated run be scored. Called by the
# score stage, and again at the end of pubsql so its own two steps are in the
# same file.
maint_proofs() {
  say "proofs: the maintenance was not defeated"
  q "$DB" "SELECT /* wiki_gin_norm_maintproof */ format(
             '%-7s %-17s %-8s dead=%-8s nonzero_blocks=%-2s blocks=%-2s skip=%s cancel=%s tags=%s pages=%s/%s/%s/%s [%s]',
             fixture, tag, kind, coalesce(dead_not_removable::text,'n/a'),
             dead_blocks_nonzero, verbose_blocks, skip_lines, cancel_lines, command_tags,
             coalesce(num_pages::text,'-'), coalesce(newly_deleted::text,'-'),
             coalesce(pages_deleted::text,'-'), coalesce(pages_free::text,'-'),
             session_timeouts)
             FROM proto.maint ORDER BY at" | tee "$OUT/maintenance-proof.txt"
  q "$DB" "SELECT /* wiki_gin_norm_maintproof */ format('%-7s %-17s before: %s | after: %s',
             fixture, tag, horizon_before, horizon_after)
             FROM proto.maint ORDER BY at" > "$OUT/horizon-holders.txt"
  # the proof table itself, whole, so it survives `clean` once out/ is copied
  q "$DB" "COPY /* wiki_gin_norm_maintproof */ (SELECT * FROM proto.maint ORDER BY at)
             TO STDOUT WITH (FORMAT csv, HEADER)" > "$OUT/maint.csv" \
    || die "could not dump proto.maint"
  q "$DB" "SELECT /* wiki_gin_norm_maintproof */ 'maintenance steps: ' || count(*)
           || ' | strict: ' || count(*) FILTER (WHERE kind = 'strict')
           || ' | declared held-horizon: ' || count(*) FILTER (WHERE kind = 'declared')
           || ' | ANALYZE-only: ' || count(*) FILTER (WHERE kind = 'analyze')
           || ' | dead-but-not-removable 0 on: '
           || count(*) FILTER (WHERE kind <> 'declared' AND coalesce(dead_blocks_nonzero,1) = 0)
           || ' of ' || count(*) FILTER (WHERE kind <> 'declared')
           || ' | skip lines: ' || sum(skip_lines)
           || ' | cancellations: ' || sum(cancel_lines)
           || ' | all four timeouts 0 on: '
           || count(*) FILTER (WHERE session_timeouts = 'idle_in_transaction_session_timeout=0 lock_timeout=0 statement_timeout=0 transaction_timeout=0')
           || ' of ' || count(*)
           || ' | horizon reads not all zero: '
           || count(*) FILTER (WHERE horizon_before NOT LIKE 'backends=0 slots=0 prepared=0%'
                                  OR horizon_after  NOT LIKE 'backends=0 slots=0 prepared=0%')
             FROM proto.maint" | tee -a "$OUT/maintenance-proof.txt"
  local defeated
  defeated=$(q "$DB" "SELECT /* wiki_gin_norm_maintproof */ count(*) FROM proto.maint
                       WHERE skip_lines > 0 OR cancel_lines > 0
                          OR session_timeouts <> 'idle_in_transaction_session_timeout=0 lock_timeout=0 statement_timeout=0 transaction_timeout=0'
                          OR (kind = 'strict'   AND coalesce(dead_blocks_nonzero, 1) <> 0)
                          OR (kind = 'strict'   AND dead_not_removable IS NULL)
                          OR (kind = 'declared' AND coalesce(dead_blocks_nonzero, 0) = 0)
                          OR (kind = 'analyze'  AND dead_not_removable IS NOT NULL)")
  [ "${defeated:-1}" = 0 ] \
    || die "$defeated maintenance step(s) were defeated: see $OUT/maintenance-proof.txt. The fixtures are repaired and re-run, not scored"
  printf 'no maintenance step was defeated\n'
}

# --------------------------------------------------------------- stage: score
stage_score() {
  maint_proofs
  say "score: declared kinds against the oracle, and the decision against it"
  # the declarations the scoring below assumes, checked against what was filed
  q "$PDB" "SELECT /* wiki_gin_norm_score */ column_name || '=' || declared_kind
              FROM declared_kind ORDER BY 1" > "$OUT/.filed_kinds.txt"
  cat > "$OUT/.assumed_kinds.txt" <<'KINDS'
base_heap_reltuples=level
base_size=level
churn_ratio=level
cur_heap_reltuples=level
cur_size=level
est_reclaimable=upper bound
heap_tuple_ratio=level
index_size_ratio=level
normalized_index_growth=level
stats_lag=level
KINDS
  if ! diff -u "$OUT/.filed_kinds.txt" "$OUT/.assumed_kinds.txt" > "$OUT/kinds-diff.txt" 2>&1; then
    cat "$OUT/kinds-diff.txt"; die "the scoring assumes kinds that were not the filed ones"
  fi
  printf 'declared kinds: the scoring matches the declaration filed at %s\n' \
    "$(cat "$OUT/declared_at.txt")"

  qin "$DB" > "$OUT/score-build.log" 2>&1 <<'SQL'
DROP /* wiki_gin_norm_score */ TABLE IF EXISTS proto.scored;
CREATE /* wiki_gin_norm_score */ TABLE proto.scored AS
WITH p AS (
  SELECT fixture,
    max(num) FILTER (WHERE phase='baseline'         AND metric='index_size')    AS base_size_rec,
    max(num) FILTER (WHERE phase='churn_written'    AND metric='index_size')    AS written_size,
    max(num) FILTER (WHERE phase='churn_settled'    AND metric='index_size')    AS settled_size,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='index_size')    AS maint_size,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='tab_reltuples') AS cur_heap,
    max(num) FILTER (WHERE phase='oracle'           AND metric='size_before')   AS ora_before,
    max(num) FILTER (WHERE phase='oracle'           AND metric='size_after')    AS ora_after,
    max(txt) FILTER (WHERE phase='baseline'         AND metric='payload')       AS payload
  FROM proto.meas GROUP BY fixture
), b AS (
  SELECT p.*,
         (payload::jsonb->>'bis')::numeric AS bis,
         (payload::jsonb->>'bhr')::numeric AS bhr
    FROM p WHERE payload IS NOT NULL
), r AS (
  SELECT b.*,
         (ora_before / nullif(bis,0)) / nullif(cur_heap / nullif(bhr,0), 0) AS norm_exact,
         ora_before - ora_after                                            AS returned_bytes,
         100.0 * (1 - ora_after / nullif(ora_before,0))                    AS truth_pct
    FROM b
)
SELECT r.fixture,
       d.verdict,
       r.bis::bigint                                     AS base_size_bytes,
       r.ora_before::bigint                              AS decide_size_bytes,
       r.ora_after::bigint                               AS rebuilt_size_bytes,
       r.returned_bytes::bigint                          AS returned_bytes,
       round(r.truth_pct, 2)                             AS truth_pct,
       round(r.norm_exact, 4)                            AS norm_exact,
       d.normalized_index_growth                         AS norm_published,
       d.index_size_ratio, d.heap_tuple_ratio, d.churn_ratio, d.stats_lag,
       CASE WHEN r.norm_exact > 1
            THEN (r.ora_before * (1 - 1/r.norm_exact))::bigint END AS est_bytes,
       CASE WHEN r.norm_exact > 1
            THEN round(100.0 * (1 - 1/r.norm_exact), 2) END        AS pred_pct,
       d.est_reclaimable                                 AS est_published,
       CASE WHEN r.norm_exact > 1
            THEN pg_size_pretty((r.ora_before * (1 - 1/r.norm_exact))::bigint) END
                                                         AS est_recomputed_pretty,
       (d.verdict LIKE 'candidate%' OR d.verdict LIKE 'strong candidate%') AS flagged,
       (d.verdict IN ('no baseline: capture one',
                      'invalid index: rebuild for validity, not for size',
                      'rebuilt since baseline: re-capture',
                      'counters reset: re-capture',
                      'no table statistics: ANALYZE first',
                      'insufficient churn: not evaluated',
                      'no ANALYZE since baseline: ANALYZE first'))         AS refusal
  FROM r
  JOIN proto.decided d ON d.index_name::text = 'f_' || r.fixture || '_gin';

DROP /* wiki_gin_norm_score */ TABLE IF EXISTS proto.report;
CREATE /* wiki_gin_norm_score */ TABLE proto.report AS
SELECT s.*,
       CASE WHEN est_bytes IS NULL             THEN 'not published'
            WHEN est_bytes >= returned_bytes   THEN 'HELD'
            ELSE 'VIOLATED' END                          AS upper_bound_verdict,
       CASE WHEN refusal AND truth_pct >= 33.33           THEN 'REFUSED (a real candidate)'
            WHEN refusal                                  THEN 'REFUSED (nothing to reclaim)'
            WHEN flagged AND truth_pct >= 33.33           THEN 'PASS'
            WHEN flagged                                  THEN 'FALSE POSITIVE'
            WHEN NOT flagged AND truth_pct >= 33.33       THEN 'FALSE NEGATIVE'
            ELSE 'PASS' END                              AS decision_score,
       CASE WHEN est_published IS DISTINCT FROM est_recomputed_pretty
            THEN 'recomputation differs' ELSE 'recomputation matches' END AS est_check,
       round(pred_pct - truth_pct, 2)                    AS pred_error
  FROM proto.scored s;
SQL
  qat "$DB" /dev/stdin > "$OUT/score-table.txt" 2>&1 <<'SQL'
SELECT /* wiki_gin_norm_report */
       rpad(fixture,4) || ' | ' || rpad(verdict,52) || ' | ' ||
       lpad(decide_size_bytes::text,11) || ' | ' || lpad(rebuilt_size_bytes::text,11) || ' | ' ||
       lpad(truth_pct::text,6) || ' | ' || lpad(norm_exact::text,8) || ' | ' ||
       lpad(coalesce(pred_pct::text,'-'),7) || ' | ' || lpad(coalesce(pred_error::text,'-'),8) || ' | ' ||
       rpad(upper_bound_verdict,13) || ' | ' || rpad(decision_score,26) || ' | ' || est_check
  FROM proto.report ORDER BY fixture;
SQL
  cat "$OUT/score-table.txt"
  qat "$DB" /dev/stdin > "$OUT/score-summary.txt" 2>&1 <<'SQL'
SELECT /* wiki_gin_norm_report */ 'scored fixtures: ' || count(*) FROM proto.report
UNION ALL SELECT 'upper bound HELD: ' || count(*) FROM proto.report WHERE upper_bound_verdict='HELD'
UNION ALL SELECT 'upper bound VIOLATED: ' || count(*) FROM proto.report WHERE upper_bound_verdict='VIOLATED'
UNION ALL SELECT 'upper bound not published: ' || count(*) FROM proto.report WHERE upper_bound_verdict='not published'
UNION ALL SELECT 'decision PASS: ' || count(*) FROM proto.report WHERE decision_score='PASS'
UNION ALL SELECT 'decision FALSE POSITIVE: ' || count(*) FROM proto.report WHERE decision_score='FALSE POSITIVE'
UNION ALL SELECT 'decision FALSE NEGATIVE: ' || count(*) FROM proto.report WHERE decision_score='FALSE NEGATIVE'
UNION ALL SELECT 'refused a real candidate: ' || count(*) FROM proto.report WHERE decision_score='REFUSED (a real candidate)'
UNION ALL SELECT 'refused nothing to reclaim: ' || count(*) FROM proto.report WHERE decision_score='REFUSED (nothing to reclaim)'
UNION ALL SELECT 'est recomputation matches the published text: ' || count(*) FROM proto.report WHERE est_check='recomputation matches'
UNION ALL SELECT 'prediction within 0.05 points: ' || count(*) FROM proto.report WHERE abs(pred_error) <= 0.05
UNION ALL SELECT 'prediction within 3.5 points: ' || count(*) FROM proto.report WHERE abs(pred_error) <= 3.5
UNION ALL SELECT 'worst over-prediction: ' || coalesce(max(pred_error)::text,'-') FROM proto.report
UNION ALL SELECT 'worst under-prediction: ' || coalesce(min(pred_error)::text,'-') FROM proto.report;
SQL
  cat "$OUT/score-summary.txt"

  say "score: the nine declared invariants"
  qat "$DB" /dev/stdin > "$OUT/invariants.txt" 2>&1 <<'SQL'
WITH p AS (
  SELECT fixture,
    max(num) FILTER (WHERE phase='baseline' AND metric='index_size')             AS base_size,
    max(num) FILTER (WHERE phase='baseline' AND metric='meta_total')             AS b_total,
    max(num) FILTER (WHERE phase='baseline' AND metric='meta_entry')             AS b_entry,
    max(num) FILTER (WHERE phase='baseline' AND metric='meta_data')              AS b_data,
    max(num) FILTER (WHERE phase='baseline' AND metric='meta_pending')           AS b_pending,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='index_size')     AS m_size,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='meta_total')     AS m_total,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='meta_entry')     AS m_entry,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='meta_data')      AS m_data,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='meta_pending')   AS m_pending,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='census_entry')   AS c_entry,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='census_data_leaf')  AS c_dleaf,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='census_data_inner') AS c_dinner,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='census_list')    AS c_list,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='census_recyclable') AS c_recyc,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='fsm_free_pages') AS fsm,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='bracket_blocks_before') AS br_before,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='bracket_blocks_after')  AS br_after,
    max(num) FILTER (WHERE phase='churn_maintained' AND metric='verbose_pages_free')    AS verb
  FROM proto.meas GROUP BY fixture
)
SELECT 'I1 index_size_ratio >= 1 (un-rebuilt fixtures): '
       || count(*) FILTER (WHERE m_size >= base_size) || ' of ' || count(*)
  FROM p WHERE base_size IS NOT NULL AND m_size IS NOT NULL AND fixture <> 'c09'
UNION ALL
SELECT 'I2 fresh build total = entry + data + pending + 1: '
       || count(*) FILTER (WHERE b_total = b_entry + b_data + b_pending + 1) || ' of ' || count(*)
  FROM p WHERE b_total IS NOT NULL
UNION ALL
SELECT 'I3 FSM free <= census new+deleted: '
       || count(*) FILTER (WHERE fsm <= c_recyc) || ' of ' || count(*)
  FROM p WHERE fsm IS NOT NULL AND c_recyc IS NOT NULL
UNION ALL
SELECT 'I4 size bracket held: '
       || count(*) FILTER (WHERE br_before = br_after) || ' of ' || count(*)
  FROM p WHERE br_before IS NOT NULL
UNION ALL
SELECT 'I5 VACUUM VERBOSE reusable = census new+deleted: '
       || count(*) FILTER (WHERE verb = c_recyc) || ' of ' || count(*)
  FROM p WHERE verb IS NOT NULL AND c_recyc IS NOT NULL
UNION ALL
SELECT 'I6 meta_total = 1 + census entry + data + list + new/deleted: '
       || count(*) FILTER (WHERE m_total = 1 + c_entry + c_dleaf + c_dinner + c_list + c_recyc)
       || ' of ' || count(*)
  FROM p WHERE m_total IS NOT NULL AND c_entry IS NOT NULL
UNION ALL
SELECT 'I7 maintenance not defeated (0 dead-but-not-removable, declared steps aside): '
       || count(*) FILTER (WHERE kind = 'declared'
                              OR (dead_not_removable IS NOT NULL AND dead_blocks_nonzero = 0)
                              OR (kind = 'analyze' AND dead_not_removable IS NULL))
       || ' of ' || count(*) || ' steps'
  FROM proto.maint
UNION ALL
SELECT 'I8 four timeouts 0, completed, no skip or cancellation: '
       || count(*) FILTER (WHERE session_timeouts = 'idle_in_transaction_session_timeout=0 lock_timeout=0 statement_timeout=0 transaction_timeout=0'
                             AND skip_lines = 0 AND cancel_lines = 0 AND command_tags > 0)
       || ' of ' || count(*) || ' steps'
  FROM proto.maint
UNION ALL
SELECT 'I9 no progress-view row at either end of a census: '
       || count(*) FILTER (WHERE before_rows = 0 AND after_rows = 0) || ' of ' || count(*)
  FROM (SELECT fixture, phase,
               max(num) FILTER (WHERE metric='progress_rows_before') AS before_rows,
               max(num) FILTER (WHERE metric='progress_rows_after')  AS after_rows
          FROM proto.meas
         WHERE metric IN ('progress_rows_before','progress_rows_after')
         GROUP BY fixture, phase) g
UNION ALL
SELECT 'metapage entry+data vs census (exact rows): ' || string_agg(fixture, ' ')
  FROM p WHERE m_total IS NOT NULL AND c_entry IS NOT NULL
    AND m_entry = c_entry AND m_data = c_dleaf + c_dinner;
SQL
  cat "$OUT/invariants.txt"

  say "score: the maintenance pair, and every phase size per fixture"
  qat "$DB" /dev/stdin > "$OUT/phase-sizes.txt" 2>&1 <<'SQL'
SELECT /* wiki_gin_norm_report */ rpad(fixture,4) || ' | ' ||
       lpad(coalesce(max(num) FILTER (WHERE phase='baseline' AND metric='index_size')::text,'-'),11) || ' | ' ||
       lpad(coalesce(max(num) FILTER (WHERE phase='churn_written' AND metric='index_size')::text,'-'),11) || ' | ' ||
       lpad(coalesce(max(num) FILTER (WHERE phase='churn_settled' AND metric='index_size')::text,'-'),11) || ' | ' ||
       lpad(coalesce(max(num) FILTER (WHERE phase='churn_maintained' AND metric='index_size')::text,'-'),11) || ' | ' ||
       lpad(coalesce(max(num) FILTER (WHERE phase='oracle_after' AND metric='index_size')::text,'-'),11) || ' | meta ' ||
       lpad(coalesce(max(num) FILTER (WHERE phase='churn_written' AND metric='meta_pending')::text,'-'),5) || ' -> ' ||
       lpad(coalesce(max(num) FILTER (WHERE phase='churn_maintained' AND metric='meta_pending')::text,'-'),5)
  FROM proto.meas GROUP BY fixture ORDER BY fixture;
SQL
  cat "$OUT/phase-sizes.txt"

  say "score: what the settle step itself cost in bytes"
  # The protocol warns that settling is not free, because the pending-list flush
  # drives keys through ginEntryInsert and a split there takes a new page. This
  # is that warning, measured: the file size the method would have read before
  # the settle step against the one it reads after it.
  qat "$DB" /dev/stdin > "$OUT/settle-delta.txt" 2>&1 <<'SQL'
WITH p AS (
  SELECT fixture,
    max(num) FILTER (WHERE phase='churn_written' AND metric='index_size')   AS written,
    max(num) FILTER (WHERE phase='churn_settled' AND metric='index_size')   AS settled,
    max(num) FILTER (WHERE phase='churn_written' AND metric='meta_pending') AS pend
  FROM proto.meas GROUP BY fixture
), d AS (
  SELECT fixture, written, settled, pend, settled - written AS delta
    FROM p WHERE written IS NOT NULL AND settled IS NOT NULL
), lines AS (
  SELECT 1 AS grp, delta,
         rpad(fixture,4) || ' | written ' || lpad(written::text,11)
         || ' | settled ' || lpad(settled::text,11)
         || ' | delta ' || lpad(delta::text,10)
         || ' | pending pages before the settle step ' || lpad(coalesce(pend::text,'-'),5) AS line
    FROM d WHERE delta <> 0
  UNION ALL
  SELECT 2, 0,
         'fixtures whose settle step grew the file: ' || count(*) FILTER (WHERE delta > 0)
         || ' of ' || count(*) || ' with a settle step; total added '
         || coalesce(sum(delta) FILTER (WHERE delta > 0), 0) || ' bytes; largest '
         || coalesce(max(delta), 0) || ' bytes; fixtures whose settle step shrank it: '
         || count(*) FILTER (WHERE delta < 0)
    FROM d
)
SELECT /* wiki_gin_norm_report */ line FROM lines ORDER BY grp, delta DESC;
SQL
  cat "$OUT/settle-delta.txt"

  # every reading the fixtures, the churn, the censuses and the oracle stored,
  # so each number the page quotes is in a file that survives `clean` once out/
  # is copied: the metapage and census rows per phase, the payloads, the flush
  # counts and the rebuilt indexes' own catalog rows
  q "$DB" "COPY /* wiki_gin_norm_report */ (SELECT fixture, phase, metric, num, txt, at
                                              FROM proto.meas ORDER BY at, metric)
             TO STDOUT WITH (FORMAT csv, HEADER)" > "$OUT/meas.csv" \
    || die "could not dump proto.meas"
  printf 'stored readings: %s rows in meas.csv\n' "$(($(wc -l < "$OUT/meas.csv") - 1))"
}

# -------------------------------------------------------------- stage: probes
# The mechanism probes behind the page's two failure sections, its reltuples
# table and its statistics-counter warning. Own database, own disposable tables.
stage_probes() {
  say "probes: reltuples writers, build linearity, maintenance_work_mem, pgstat timing"
  q postgres "DROP /* wiki_gin_norm_probe */ DATABASE IF EXISTS probes" > /dev/null
  q postgres "CREATE /* wiki_gin_norm_probe */ DATABASE probes" > /dev/null
  qin probes <<'SQL' > "$OUT/probe-ddl.log" 2>&1
CREATE /* wiki_gin_norm_probe */ EXTENSION pageinspect;
CREATE /* wiki_gin_norm_probe */ SCHEMA proto;
CREATE TABLE proto.meas (fixture text, phase text, metric text, num numeric, txt text,
                         at timestamptz default clock_timestamp());
CREATE FUNCTION proto.note(p_fix text, p_phase text, p_metric text,
                           p_num numeric DEFAULT NULL, p_txt text DEFAULT NULL)
RETURNS void LANGUAGE sql AS $fn$
  INSERT INTO proto.meas(fixture,phase,metric,num,txt) VALUES (p_fix,p_phase,p_metric,p_num,p_txt);
$fn$;
CREATE FUNCTION proto.mk_tags(p_tab text, p_lo bigint, p_hi bigint, p_keybase int, p_keys int)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
  EXECUTE format($q$INSERT INTO %I (id, tags) SELECT i, ARRAY[
      $1 + ((i *     7919) %% $2)::int, $1 + ((i *   104729) %% $2)::int,
      $1 + ((i *  1299709) %% $2)::int, $1 + ((i * 15485863) %% $2)::int,
      $1 + ((i * 32452843) %% $2)::int] FROM generate_series($3, $4) i$q$, p_tab)
    USING p_keybase, p_keys, p_lo, p_hi;
END $fn$;
CREATE FUNCTION proto.rt(p_stage text, p_tab text, p_idx text) RETURNS void
LANGUAGE plpgsql AS $fn$
BEGIN
  INSERT INTO proto.meas(fixture,phase,metric,num)
  SELECT 'P1', p_stage, 'tab_reltuples', reltuples FROM pg_class WHERE oid = p_tab::regclass;
  INSERT INTO proto.meas(fixture,phase,metric,num)
  SELECT 'P1', p_stage, 'idx_reltuples', reltuples FROM pg_class WHERE oid = p_idx::regclass;
  INSERT INTO proto.meas(fixture,phase,metric,num)
  SELECT 'P1', p_stage, 'index_size', pg_relation_size(p_idx::regclass,'main');
END $fn$;
SQL

  # the probes are mechanism probes rather than scored fixtures, so they are
  # outside the no-defeat rule; this one reading records that nothing was holding
  # the horizon while they ran anyway
  horizon_probe probes P0 probes_start

  say "P1: the four writers of an index's own reltuples, and the fifth value"
  qin probes > "$OUT/probe-p1.log" 2>&1 <<SQL
CREATE /* wiki_gin_norm_probe */ TABLE p1 (id bigint, tags int[]);
SELECT /* wiki_gin_norm_probe */ proto.mk_tags('p1', 1, 200000, 0, 2000);
CREATE /* wiki_gin_norm_probe */ INDEX p1_gin ON p1 USING gin (tags);
SELECT /* wiki_gin_norm_probe */ proto.rt('after CREATE INDEX','p1','p1_gin');
ANALYZE /* wiki_gin_norm_probe */ p1;
SELECT /* wiki_gin_norm_probe */ proto.rt('after ANALYZE','p1','p1_gin');
DELETE /* wiki_gin_norm_probe */ FROM p1 WHERE id % 2 = 0;
VACUUM /* wiki_gin_norm_probe */ p1;
SELECT /* wiki_gin_norm_probe */ proto.rt('after DELETE 50% + VACUUM','p1','p1_gin');
REINDEX /* wiki_gin_norm_probe */ INDEX p1_gin;
SELECT /* wiki_gin_norm_probe */ proto.rt('after REINDEX','p1','p1_gin');
VACUUM /* wiki_gin_norm_probe */ p1;
SELECT /* wiki_gin_norm_probe */ proto.rt('after a second plain VACUUM','p1','p1_gin');
VACUUM /* wiki_gin_norm_probe */ (DISABLE_PAGE_SKIPPING) p1;
SELECT /* wiki_gin_norm_probe */ proto.rt('after VACUUM (DISABLE_PAGE_SKIPPING)','p1','p1_gin');
SQL
  qat probes /dev/stdin > "$OUT/probe-p1.txt" 2>&1 <<'SQL'
SELECT /* wiki_gin_norm_report */ rpad(phase,40) || ' | table ' ||
       lpad(max(num) FILTER (WHERE metric='tab_reltuples')::bigint::text,8) || ' | index ' ||
       lpad(max(num) FILTER (WHERE metric='idx_reltuples')::bigint::text,8)
  FROM proto.meas WHERE fixture='P1' GROUP BY phase ORDER BY min(at);
SQL
  cat "$OUT/probe-p1.txt"

  say "P2/P3: fresh-build size against heap tuples, and against maintenance_work_mem"
  q probes "CREATE /* wiki_gin_norm_probe */ TABLE lin (id bigint, tags int[])" > /dev/null
  local prev=0
  for n in 250000 500000 1000000 2000000 4000000 8000000; do
    printf '  linearity point %s\n' "$n"
    qin probes > "$OUT/probe-lin-$n.log" 2>&1 <<SQL
SELECT /* wiki_gin_norm_probe */ proto.mk_tags('lin', $((prev + 1)), $n, 0, $KEYS);
VACUUM /* wiki_gin_norm_probe */ (ANALYZE) lin;
SET /* wiki_gin_norm_probe */ maintenance_work_mem = '$MWM';
CREATE /* wiki_gin_norm_probe */ INDEX lin_gin ON lin USING gin (tags);
SELECT /* wiki_gin_norm_probe */ proto.note('P2','$n','index_size', pg_relation_size('lin_gin','main'));
INSERT /* wiki_gin_norm_probe */ INTO proto.meas(fixture,phase,metric,num)
SELECT 'P2','$n',k,v FROM (SELECT * FROM gin_metapage_info(get_raw_page('lin_gin',0))) m,
  LATERAL (VALUES ('meta_total',m.n_total_pages),('meta_entry',m.n_entry_pages),
                  ('meta_data',m.n_data_pages),('meta_pending',m.n_pending_pages),
                  ('meta_entries',m.n_entries)) AS t(k,v);
DROP /* wiki_gin_norm_probe */ INDEX lin_gin;
SQL
    if [ "$n" = 2000000 ]; then
      for mwm in 64MB 256MB 1GB; do
        printf '  budget %s at %s rows\n' "$mwm" "$n"
        qin probes > "$OUT/probe-mwm-$mwm.log" 2>&1 <<SQL
SET /* wiki_gin_norm_probe */ maintenance_work_mem = '$mwm';
CREATE /* wiki_gin_norm_probe */ INDEX lin_gin ON lin USING gin (tags);
SELECT /* wiki_gin_norm_probe */ proto.note('P3','$mwm','index_size', pg_relation_size('lin_gin','main'));
INSERT /* wiki_gin_norm_probe */ INTO proto.meas(fixture,phase,metric,num)
SELECT 'P3','$mwm',k,v FROM (SELECT * FROM gin_metapage_info(get_raw_page('lin_gin',0))) m,
  LATERAL (VALUES ('meta_total',m.n_total_pages),('meta_entry',m.n_entry_pages),
                  ('meta_data',m.n_data_pages),('meta_pending',m.n_pending_pages),
                  ('meta_entries',m.n_entries)) AS t(k,v);
DROP /* wiki_gin_norm_probe */ INDEX lin_gin;
SQL
      done
    fi
    prev=$n
  done
  qat probes /dev/stdin > "$OUT/probe-p2.txt" 2>&1 <<'SQL'
SELECT /* wiki_gin_norm_report */ rpad(fixture,3) || ' | ' || lpad(phase,9) || ' | bytes ' ||
       lpad(max(num) FILTER (WHERE metric='index_size')::bigint::text,10) || ' | pages ' ||
       lpad((max(num) FILTER (WHERE metric='index_size')/8192)::bigint::text,7) || ' | entry ' ||
       lpad(max(num) FILTER (WHERE metric='meta_entry')::bigint::text,6) || ' | data ' ||
       lpad(max(num) FILTER (WHERE metric='meta_data')::bigint::text,6) || ' | pending ' ||
       lpad(max(num) FILTER (WHERE metric='meta_pending')::bigint::text,3) || ' | entries ' ||
       lpad(max(num) FILTER (WHERE metric='meta_entries')::bigint::text,7) || ' | identity ' ||
       CASE WHEN max(num) FILTER (WHERE metric='meta_total')
               = max(num) FILTER (WHERE metric='meta_entry')
               + max(num) FILTER (WHERE metric='meta_data')
               + max(num) FILTER (WHERE metric='meta_pending') + 1
            THEN 'exact' ELSE 'OFF BY ' ||
              (max(num) FILTER (WHERE metric='meta_total')
                 - max(num) FILTER (WHERE metric='meta_entry')
                 - max(num) FILTER (WHERE metric='meta_data')
                 - max(num) FILTER (WHERE metric='meta_pending') - 1)::text END
  FROM proto.meas WHERE fixture IN ('P2','P3')
 GROUP BY fixture, phase ORDER BY fixture, (CASE WHEN phase ~ '^[0-9]+$' THEN phase::bigint ELSE 0 END), phase;
SQL
  cat "$OUT/probe-p2.txt"

  say "P4: the statistics counter the guard must not use"
  qin probes > "$OUT/probe-p4.log" 2>&1 <<SQL
CREATE /* wiki_gin_norm_probe */ TABLE p4 (id bigint, tags int[]);
SELECT /* wiki_gin_norm_probe */ proto.mk_tags('p4', 1, 150000, 0, 2000);
CREATE /* wiki_gin_norm_probe */ INDEX p4_gin ON p4 USING gin (tags);
VACUUM /* wiki_gin_norm_probe */ (ANALYZE) p4;
SQL
  : > "$OUT/probe-p4.txt"
  for attempt in 1 2 3 4; do
    qin probes >> "$OUT/probe-p4.log" 2>&1 <<SQL
DELETE /* wiki_gin_norm_probe */ FROM p4 WHERE id % 10 = $attempt;
VACUUM /* wiki_gin_norm_probe */ (ANALYZE) p4;
SELECT /* wiki_gin_norm_probe */ pg_stat_force_next_flush();
SQL
    q probes "SELECT /* wiki_gin_norm_report */ 'attempt $attempt | live ' || n_live_tup ||
                ' | dead ' || n_dead_tup || ' | mod ' || n_mod_since_analyze ||
                ' | reltuples ' || (SELECT reltuples::bigint FROM pg_class WHERE oid='p4'::regclass)
                FROM pg_stat_all_tables WHERE relid = 'p4'::regclass" >> "$OUT/probe-p4.txt"
  done
  qin probes >> "$OUT/probe-p4.log" 2>&1 <<SQL
DELETE /* wiki_gin_norm_probe */ FROM p4 WHERE id % 10 = 5;
SELECT /* wiki_gin_norm_probe */ pg_sleep(2);
VACUUM /* wiki_gin_norm_probe */ (ANALYZE) p4;
SELECT /* wiki_gin_norm_probe */ pg_stat_force_next_flush();
SQL
  q probes "SELECT /* wiki_gin_norm_report */ 'attempt 5, 2 s pause | live ' || n_live_tup ||
              ' | dead ' || n_dead_tup || ' | mod ' || n_mod_since_analyze ||
              ' | reltuples ' || (SELECT reltuples::bigint FROM pg_class WHERE oid='p4'::regclass)
              FROM pg_stat_all_tables WHERE relid = 'p4'::regclass" >> "$OUT/probe-p4.txt"
  cat "$OUT/probe-p4.txt"

  say "P6: the ANALYZE sample spread in the method's own denominator"
  # heap_tuple_ratio divides by pg_class.reltuples, which ANALYZE writes from a
  # sample. On a churned table of an unchanged population the estimate is not the
  # row count, and it is not the same estimate twice - which is enough, at the
  # boundary, to decide a bound verdict.
  qin probes > "$OUT/probe-p6.log" 2>&1 <<SQL
CREATE /* wiki_gin_norm_probe */ TABLE p6 (id bigint, tags int[]);
SELECT /* wiki_gin_norm_probe */ proto.mk_tags('p6', 1, $BASE_ROWS, 0, $KEYS);
CREATE /* wiki_gin_norm_probe */ INDEX p6_gin ON p6 USING gin (tags);
UPDATE /* wiki_gin_norm_probe */ p6 SET tags = tags;
UPDATE /* wiki_gin_norm_probe */ p6 SET tags = tags;
SET /* wiki_gin_norm_probe */ statement_timeout = 0;
SET /* wiki_gin_norm_probe */ lock_timeout = 0;
VACUUM /* wiki_gin_norm_probe */ (ANALYZE) p6;
SQL
  : > "$OUT/probe-p6.txt"
  q probes "SELECT /* wiki_gin_norm_report */ 'true rows ' || count(*) FROM p6" >> "$OUT/probe-p6.txt"
  for a in 1 2 3 4 5; do
    q probes "SELECT /* wiki_gin_norm_report */ 'reading $a | reltuples ' ||
                (SELECT reltuples::bigint FROM pg_class WHERE oid='p6'::regclass) ||
                ' | error ' || round((100.0 * ((SELECT reltuples::numeric FROM pg_class WHERE oid='p6'::regclass)
                                               - (SELECT count(*) FROM p6))
                                      / (SELECT count(*) FROM p6)), 4) || '%'" >> "$OUT/probe-p6.txt"
    [ "$a" = 5 ] || q probes "ANALYZE /* wiki_gin_norm_probe */ p6" > /dev/null
  done
  cat "$OUT/probe-p6.txt"

  say "P5: the same race at baseline capture, with and without a forced flush"
  write_published_sql
  sed "s/public\.orders_tags_gin/orders_tags_gin/" "$SQLD/capture.sql" > "$SQLD/.p5.sql"
  # the load, the build and the capture in ONE transaction, so the loader's own
  # counts cannot have been published when the baseline is written
  { cat <<'SQL'
BEGIN /* wiki_gin_norm_probe */;
CREATE /* wiki_gin_norm_probe */ TABLE orders_tags (id bigint, tags int[]);
SELECT /* wiki_gin_norm_probe */ proto.mk_tags('orders_tags', 1, 80000, 0, 2000);
CREATE /* wiki_gin_norm_probe */ INDEX orders_tags_gin ON orders_tags USING gin (tags);
SELECT /* wiki_gin_norm_probe */ 'reltuples right after CREATE INDEX: ' ||
       (SELECT reltuples::bigint FROM pg_class WHERE oid = 'orders_tags'::regclass);
SQL
    cat "$SQLD/.p5.sql"
  } | qin probes > "$OUT/probe-p5.log" 2>&1
  grep -o 'reltuples right after CREATE INDEX: [0-9-]*' "$OUT/probe-p5.log" | head -1 \
    | tee "$OUT/probe-p5.txt"
  q probes "SELECT /* wiki_gin_norm_report */ 'capture in the loading transaction: bti=' ||
              (substring(obj_description('orders_tags_gin'::regclass,'pg_class') from '@ginbase:(\{[^}]*\})')::jsonb->>'bti')
              || ' n_tup_ins=' || (SELECT coalesce(n_tup_ins,0) FROM pg_stat_all_tables WHERE relid='orders_tags'::regclass)" \
    | tee -a "$OUT/probe-p5.txt"
  q probes "SELECT /* wiki_gin_norm_probe */ pg_stat_force_next_flush()" > /dev/null
  qf probes "$SQLD/.p5.sql" > /dev/null 2>&1
  q probes "SELECT /* wiki_gin_norm_report */ 'capture after pg_stat_force_next_flush(): bti=' ||
              (substring(obj_description('orders_tags_gin'::regclass,'pg_class') from '@ginbase:(\{[^}]*\})')::jsonb->>'bti')
              || ' n_tup_ins=' || (SELECT coalesce(n_tup_ins,0) FROM pg_stat_all_tables WHERE relid='orders_tags'::regclass)" \
    | tee -a "$OUT/probe-p5.txt"
  q probes "SELECT /* wiki_gin_norm_report */ 'payload bytes: ' || length(
              substring(obj_description('orders_tags_gin'::regclass,'pg_class') from '@ginbase:\{[^}]*\}'))
              || ' | whole comment bytes: ' || length(obj_description('orders_tags_gin'::regclass,'pg_class'))" \
    | tee -a "$OUT/probe-p5.txt"
}

# ---------------------------------------------------------------- stage: edge
stage_edge() {
  say "edge cases: comment survival, rebuild detection, locks, privileges, dump"
  write_published_sql
  q postgres "DROP /* wiki_gin_norm_edge */ DATABASE IF EXISTS edge" > /dev/null
  q postgres "DROP /* wiki_gin_norm_edge */ ROLE IF EXISTS wiki_reader" > /dev/null
  q postgres "CREATE /* wiki_gin_norm_edge */ DATABASE edge" > /dev/null
  : > "$OUT/edge.txt"
  qin edge > "$OUT/edge-build.log" 2>&1 <<SQL
CREATE /* wiki_gin_norm_edge */ TABLE edge_t (id bigint, tags int[]);
INSERT /* wiki_gin_norm_edge */ INTO edge_t (id, tags)
SELECT i, ARRAY[(i % 2000)::int, ((i * 7919) % 2000)::int] FROM generate_series(1, 100000) i;
CREATE /* wiki_gin_norm_edge */ INDEX edge_gin ON edge_t USING gin (tags);
CREATE /* wiki_gin_norm_edge */ INDEX fresh_btree ON edge_t (id);
VACUUM /* wiki_gin_norm_edge */ (ANALYZE) edge_t;
COMMENT /* wiki_gin_norm_edge */ ON INDEX edge_gin IS
  E'owner: search-team\nticket: OPS-1234 {do not drop} @ 100%';
SQL
  sed "s/public\.orders_tags_gin/edge_gin/" "$SQLD/capture.sql" > "$SQLD/.edge_cap.sql"
  qf edge "$SQLD/.edge_cap.sql" > /dev/null
  {
    printf 'E1 human comment kept: %s\n' \
      "$(q edge "SELECT /* wiki_gin_norm_edge */ 'payload=' || length(substring(obj_description('edge_gin'::regclass,'pg_class') from '@ginbase:\{[^}]*\}')) || 'B comment=' || length(obj_description('edge_gin'::regclass,'pg_class')) || 'B human=' || btrim(regexp_replace(obj_description('edge_gin'::regclass,'pg_class'), '\s*@ginbase:\{[^}]*\}', '', 'g'))")"
    printf 'E2 plain REINDEX: %s\n' "$(
      q edge "SELECT /* wiki_gin_norm_edge */ 'oid=' || 'edge_gin'::regclass::oid || ' relfilenode=' || relfilenode FROM pg_class WHERE oid='edge_gin'::regclass")"
    q edge "REINDEX /* wiki_gin_norm_edge */ INDEX edge_gin" > /dev/null
    printf '   after:              %s comment_intact=%s\n' \
      "$(q edge "SELECT /* wiki_gin_norm_edge */ 'oid=' || 'edge_gin'::regclass::oid || ' relfilenode=' || relfilenode FROM pg_class WHERE oid='edge_gin'::regclass")" \
      "$(q edge "SELECT /* wiki_gin_norm_edge */ obj_description('edge_gin'::regclass,'pg_class') LIKE '%@ginbase:%'")"
    printf 'E3 REINDEX CONCURRENTLY before: %s\n' \
      "$(q edge "SELECT /* wiki_gin_norm_edge */ 'oid=' || 'edge_gin'::regclass::oid")"
    q edge "REINDEX /* wiki_gin_norm_edge */ INDEX CONCURRENTLY edge_gin" > /dev/null
    printf '   after: %s payload_moved=%s\n' \
      "$(q edge "SELECT /* wiki_gin_norm_edge */ 'oid=' || 'edge_gin'::regclass::oid")" \
      "$(q edge "SELECT /* wiki_gin_norm_edge */ obj_description('edge_gin'::regclass,'pg_class') LIKE '%@ginbase:%'")"
    printf 'E4 evaluate after E3: %s\n' \
      "$(qat edge "$SQLD/evaluate.sql" 2>&1 | grep -o 'rebuilt since baseline: re-capture' | head -1)"
    q edge "ALTER /* wiki_gin_norm_edge */ INDEX edge_gin RENAME TO edge_gin2" > /dev/null
    printf 'E5 ALTER INDEX RENAME: payload_survives=%s\n' \
      "$(q edge "SELECT /* wiki_gin_norm_edge */ obj_description('edge_gin2'::regclass,'pg_class') LIKE '%@ginbase:%'")"
    q edge "ALTER /* wiki_gin_norm_edge */ INDEX edge_gin2 RENAME TO edge_gin" > /dev/null
    printf 'E6 COMMENT lock footprint:\n'
    qin edge <<'SQL' 2>&1 | sed 's/^/   /'
BEGIN;
COMMENT /* wiki_gin_norm_edge */ ON INDEX edge_gin IS 'probe';
SELECT /* wiki_gin_norm_edge */ l.relation::regclass::text AS rel, l.mode
  FROM pg_locks l WHERE l.pid = pg_backend_pid() AND l.relation IS NOT NULL
   AND l.relation IN ('edge_gin'::regclass, 'edge_t'::regclass) ORDER BY 1;
ROLLBACK;
SQL
    printf 'E7 non-owner: '
    q postgres "CREATE /* wiki_gin_norm_edge */ ROLE wiki_reader LOGIN" > /dev/null
    q postgres "GRANT /* wiki_gin_norm_edge */ pg_read_all_stats TO wiki_reader" > /dev/null
    q edge "GRANT /* wiki_gin_norm_edge */ SELECT ON edge_t TO wiki_reader" > /dev/null
    q edge "GRANT /* wiki_gin_norm_edge */ CONNECT ON DATABASE edge TO wiki_reader" > /dev/null
    printf 'reads=%s ' "$("$BIN/psql" -X -U wiki_reader -h "$SOCK" -p "$PORT" -d edge -At \
      -c "SELECT /* wiki_gin_norm_edge */ (substring(obj_description('edge_gin'::regclass,'pg_class') from '@ginbase:(\{[^}]*\})')::jsonb->>'bis')" 2>&1 | head -1)"
    printf 'write=%s\n' "$("$BIN/psql" -X -U wiki_reader -h "$SOCK" -p "$PORT" -d edge -At \
      -c "COMMENT /* wiki_gin_norm_edge */ ON INDEX edge_gin IS 'nope'" 2>&1 | tr '\n' ' ')"
    printf 'E11 capture aimed at a B-tree: %s\n' \
      "$(sed "s/public\.orders_tags_gin/fresh_btree/" "$SQLD/capture.sql" > "$SQLD/.edge_bt.sql";
         qf edge "$SQLD/.edge_bt.sql" 2>&1 | grep -o 'not a GIN index: [a-z_]*' | head -1)"
    qin edge > /dev/null 2>&1 <<'SQL'
CREATE /* wiki_gin_norm_edge */ TABLE t0 (id bigint, tags int[]);
INSERT /* wiki_gin_norm_edge */ INTO t0 (id, tags)
SELECT i, ARRAY[(i % 2000)::int] FROM generate_series(1, 80000) i;
SQL
    printf 'E13 reltuples before any index: %s' \
      "$(q edge "SELECT /* wiki_gin_norm_edge */ reltuples FROM pg_class WHERE oid='t0'::regclass")"
    q edge "CREATE /* wiki_gin_norm_edge */ INDEX t0_gin ON t0 USING gin (tags)" > /dev/null
    printf ', after CREATE INDEX: table=%s index=%s\n' \
      "$(q edge "SELECT /* wiki_gin_norm_edge */ reltuples::bigint FROM pg_class WHERE oid='t0'::regclass")" \
      "$(q edge "SELECT /* wiki_gin_norm_edge */ reltuples::bigint FROM pg_class WHERE oid='t0_gin'::regclass")"
    q edge "TRUNCATE /* wiki_gin_norm_edge */ t0" > /dev/null
    printf 'E14 after TRUNCATE, reltuples=%s, capture says: %s\n' \
      "$(q edge "SELECT /* wiki_gin_norm_edge */ reltuples FROM pg_class WHERE oid='t0'::regclass")" \
      "$(sed "s/public\.orders_tags_gin/t0_gin/" "$SQLD/capture.sql" > "$SQLD/.edge_t0.sql";
         qf edge "$SQLD/.edge_t0.sql" 2>&1 | grep -o 'refusing baseline for .*' | head -1)"
    printf 'E15 pg_dump --section=post-data carries the payload: %s line(s)\n' \
      "$("$BIN/pg_dump" -h "$SOCK" -p "$PORT" -d edge -t edge_t --section=post-data 2>/dev/null \
         | grep -c '@ginbase:')"
  } | tee "$OUT/edge.txt"
}

# -------------------------------------------------------------- stage: pubsql
# The published statements, verbatim and unsubstituted, through one whole
# lifecycle under the protocol's phases.
stage_pubsql() {
  say "pubsql: capture -> churn -> settle -> maintain -> decide -> oracle -> re-capture"
  write_published_sql
  q postgres "DROP /* wiki_gin_norm_pub */ DATABASE IF EXISTS pubsql" > /dev/null
  q postgres "CREATE /* wiki_gin_norm_pub */ DATABASE pubsql" > /dev/null
  : > "$OUT/pubsql.txt"
  qin pubsql > "$OUT/pubsql-build.log" 2>&1 <<SQL
CREATE /* wiki_gin_norm_pub */ EXTENSION pageinspect;
CREATE /* wiki_gin_norm_pub */ TABLE orders (id bigint, tags int[]);
INSERT /* wiki_gin_norm_pub */ INTO orders (id, tags)
SELECT i, ARRAY[((i * 7919) % $KEYS)::int, ((i * 104729) % $KEYS)::int,
                ((i * 1299709) % $KEYS)::int, ((i * 15485863) % $KEYS)::int,
                ((i * 32452843) % $KEYS)::int]
  FROM generate_series(1::bigint, $PEND_ROWS) i;
CREATE /* wiki_gin_norm_pub */ INDEX orders_tags_gin ON orders USING gin (tags);
COMMENT /* wiki_gin_norm_pub */ ON INDEX orders_tags_gin IS
  E'owner: search-team\nticket: OPS-1234 {do not drop} @ 100%';
SELECT /* wiki_gin_norm_pub */ pg_stat_force_next_flush();
SQL
  run_maint pubsql pubsql settle_build_pub "VACUUM /* wiki_gin_norm_pub */ (VERBOSE, ANALYZE) orders;"
  check_maint pubsql settle_build_pub strict orders_tags_gin
  {
    printf 'build: index %s bytes, table reltuples %s\n' \
      "$(q pubsql "SELECT /* wiki_gin_norm_pub */ pg_relation_size('orders_tags_gin','main')")" \
      "$(q pubsql "SELECT /* wiki_gin_norm_pub */ reltuples::bigint FROM pg_class WHERE oid='orders'::regclass")"
    printf '\ncapture (statement 1, verbatim):\n'
    qf pubsql "$SQLD/capture.sql" 2>&1 | sed 's/^/   /'
    q pubsql "SELECT /* wiki_gin_norm_pub */ '   payload: ' ||
                substring(obj_description('orders_tags_gin'::regclass,'pg_class') from '@ginbase:(\{[^}]*\})')"
    printf '\nread (statement 2, verbatim):\n'
    "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d pubsql -x -f "$SQLD/read.sql" 2>&1 | sed 's/^/   /'
  } >> "$OUT/pubsql.txt"
  qin pubsql > "$OUT/pubsql-churn.log" 2>&1 <<SQL
UPDATE /* wiki_gin_norm_pub */ orders SET tags = ARRAY[((id + 1) % $KEYS)::int, ((id * 7919 + 1) % $KEYS)::int,
       ((id * 104729 + 1) % $KEYS)::int, ((id * 1299709 + 1) % $KEYS)::int, ((id * 15485863 + 1) % $KEYS)::int];
UPDATE /* wiki_gin_norm_pub */ orders SET tags = ARRAY[((id + 2) % $KEYS)::int, ((id * 7919 + 2) % $KEYS)::int,
       ((id * 104729 + 2) % $KEYS)::int, ((id * 1299709 + 2) % $KEYS)::int, ((id * 15485863 + 2) % $KEYS)::int];
SELECT /* wiki_gin_norm_pub */ pg_stat_force_next_flush();
SQL
  run_maint pubsql pubsql settle_pub "VACUUM /* wiki_gin_norm_pub_settle */ (VERBOSE) orders;"
  check_maint pubsql settle_pub strict orders_tags_gin
  run_maint pubsql pubsql maint_pub "VACUUM /* wiki_gin_norm_pub_maint */ (VERBOSE, ANALYZE) orders;"
  check_maint pubsql maint_pub strict orders_tags_gin
  {
    printf '\nchurn + settle + maintenance: index %s bytes, pending pages %s\n' \
      "$(q pubsql "SELECT /* wiki_gin_norm_pub */ pg_relation_size('orders_tags_gin','main')")" \
      "$(q pubsql "SELECT /* wiki_gin_norm_pub */ n_pending_pages FROM gin_metapage_info(get_raw_page('orders_tags_gin',0))" 2>/dev/null || echo 'n/a')"
    printf '\ndecide (statement 3, verbatim, under SHARE ROW EXCLUSIVE):\n'
    { printf "SET /* wiki_gin_norm_pub */ lock_timeout = '30s';\nBEGIN /* wiki_gin_norm_pub */;\n"
      printf "LOCK /* wiki_gin_norm_pub */ TABLE orders IN SHARE ROW EXCLUSIVE MODE;\n"
      cat "$SQLD/evaluate.sql"
    } | "$BIN/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d pubsql -x 2>&1 | sed 's/^/   /'
    printf '\noracle:\n'
    printf '   before %s\n' "$(q pubsql "SELECT /* wiki_gin_norm_pub */ pg_relation_size('orders_tags_gin','main')")"
    q pubsql "REINDEX /* wiki_gin_norm_pub */ INDEX orders_tags_gin" > /dev/null
    printf '   after  %s\n' "$(q pubsql "SELECT /* wiki_gin_norm_pub */ pg_relation_size('orders_tags_gin','main')")"
    printf '\nre-capture (statement 1 again):\n'
    qf pubsql "$SQLD/capture.sql" 2>&1 | sed 's/^/   /'
    q pubsql "SELECT /* wiki_gin_norm_pub */ '   payload: ' ||
                substring(obj_description('orders_tags_gin'::regclass,'pg_class') from '@ginbase:(\{[^}]*\})')"
    q pubsql "SELECT /* wiki_gin_norm_pub */ '   human comment: ' ||
                btrim(regexp_replace(obj_description('orders_tags_gin'::regclass,'pg_class'),
                                     '\s*@ginbase:\{[^}]*\}', '', 'g'))"
    q pubsql "SELECT /* wiki_gin_norm_pub */ '   payload count: ' ||
                (length(obj_description('orders_tags_gin'::regclass,'pg_class'))
                 - length(replace(obj_description('orders_tags_gin'::regclass,'pg_class'), '@ginbase:', '')))/9"
    printf '\nre-evaluate:\n'
    qat pubsql "$SQLD/evaluate.sql" 2>&1 | sed 's/^/   /'
  } >> "$OUT/pubsql.txt"
  cat "$OUT/pubsql.txt"
  # this replay's own three maintenance steps join the run's proof table
  maint_proofs
}

# -------------------------------------------------------------- stage: verify
# Re-extract the three published statements from the page and diff them against
# the files this run executed. No literal fence appears in this script.
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
        *wiki_gin_capture_baseline*)   printf '%s' "$buf" > "$OUT/x-capture.sql";  n=$((n+1)) ;;
        *wiki_gin_read_baseline*)      printf '%s' "$buf" > "$OUT/x-read.sql";     n=$((n+1)) ;;
        *wiki_gin_reindex_candidates*) printf '%s' "$buf" > "$OUT/x-evaluate.sql"; n=$((n+1)) ;;
      esac
      continue
    fi
    buf="$buf$line
"
  done < "$PAGE"
  printf 'published wiki_gin blocks found: %s\n' "$n"
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
  # -f matches the full command line on Linux and macOS alike; -a would print
  # the command line on Linux but add the caller's own ancestors on macOS
  printf 'matching postgres processes: %s\n' "$(pgrep -f -- "$PGDATA" | wc -l | tr -d ' ')"
  # listen_addresses is empty, so the port's only listener is the socket file
  # in $SOCK; the port is not on the postmaster's command line
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

ALL="build declare fixtures churn analyze_census crosscheck decide oracle score probes edge pubsql verify"

run_stage() {
  case "$1" in
    build|start|clean|reset) : ;;
    *) need_server ;;
  esac
  "stage_$1"
}

main() {
  local stages="$*"
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

- **The protocol**: [Mandatory GIN Bloat Tests](../../common-concepts/mandatory-gin-bloat-tests.md)
  re-read end to end on 2026-09-24 — its five phases, the settle step's five proof
  obligations, the maintenance assumption's three parts, **the no-defeat rule with its five
  forbidden states, four proofs and two declared exceptions**, the auto-analyze stand-in and
  its three stated differences, the simulated census and its two publication points, the
  measurement lock's three rules, the oracle's two constraints, the declare-then-score rule,
  the four cross-checks, the concurrency and reading rules, the 13-row coverage table and
  the named limits, among them the new "a `VACUUM` whose index cleanup did not run is not
  required coverage". The concept page was **not edited** as part of this work. It had
  dropped that coverage row and its declared exception earlier the same day, and this pass is
  the consumer page following it.
- **GIN access method**: `ginvacuum.c` (`ginvacuumcleanup` including its `analyze_only`
  branch, the `num_index_tuples` assignment, `GinPageIsRecyclable`, `ginDeletePage`),
  `gininsert.c` (`ginbuild`, `ginBuildCallback` and its `maintenance_work_mem` flush,
  `ginHeapTupleBulkInsert`, `buildFreshLeafTuple`, `addItemPointersToLeafTuple`),
  `ginfast.c` (`ginInsertCleanup`, `GIN_PAGE_FREESIZE`, the foreground cleanup threshold,
  `shiftList`, `gin_clean_pending_list` and its return value, the pending-page FSM
  recycling), `ginutil.c` (`ginhandler`, `ginoptions`, `GinNewBuffer`, `ginUpdateStats`),
  `ginblock.h` (`GinMetaPageData`, the flag bits, `GinPageGetDeleteXid`). Confirmed by grep
  that no file under `src/backend/access/gin/` calls `RelationTruncate`.
- **Catalog and index maintenance**: `index.c` (`index_build`, `index_update_stats`,
  `reindex_index`, `index_concurrently_swap`), `pg_class.h`, `pg_index.h`,
  `pg_description.h`.
- **Statistics writers**: `analyze.c` (`do_analyze_rel`, `tupleFract`, the ANALYZE-only
  cleanup gate, the per-index `vac_update_relstats` call, the sample size `targrows` and the
  `300 * attstattarget` rows behind it, and `acquire_sample_rows`' block sample and row
  extrapolation), `sampling.c` (`BlockSampler_Init`), `vacuum.c`
  (`vac_cleanup_one_index`, `vacuum_get_cutoffs`, the vacuum-then-analyze order),
  `vacuumlazy.c` (`update_relstats_all_indexes`, the `estimated_count` guard and the
  `VERBOSE` index line), `pgstat_relation.c` (`pgstat_report_analyze`, `pgstat_report_vacuum`,
  `pgstat_relation_flush_cb`), `pgstat.c` (`pgstat_report_stat`, `PGSTAT_MIN_INTERVAL`,
  `PGSTAT_MAX_INTERVAL`).
- **Autovacuum**: `autovacuum.c` (`relation_needs_vacanalyze`'s three threshold formulas,
  the reloption-or-GUC selection, the `av_enabled` short circuit, the strictly-greater
  comparisons, and the worker's own forcing of the four settable timeouts to zero),
  `guc_tables.c` for the five threshold and scale-factor GUCs.
- **The removal horizon, for the no-defeat rule**: `vacuum.c` (`vacuum_get_cutoffs`'s
  `OldestXmin`, `vacuum_open_relation`'s skip-for-want-of-a-lock messages), `procarray.c`
  (`ComputeXidHorizons`'s per-backend xid/xmin fold, the `PROC_IN_VACUUM` and
  `PROC_IN_LOGICAL_DECODING` exemption, the replication-slot `xmin` fold), `twophase.c` (the
  prepared transaction's dummy `PGPROC`), `vacuumlazy.c` (`recently_dead_tuples`, the
  `lazy_scan_noprune` count, the `lazy_vacuum` gate on collected dead items, the `VERBOSE`
  tuples line), `system_views.sql` (`pg_stat_activity`'s `xact_start`/`backend_xid`/
  `backend_xmin`, `pg_replication_slots`' `xmin`/`catalog_xmin`, and the three progress
  views).
- **Comment plumbing**: `comment.c` (`CommentObject`), `system_functions.sql`
  (`obj_description`, `pg_relation_size`), `system_views.sql` (`pg_stat_all_tables`),
  `dbsize.c` (`calculate_relation_size`, `pg_relation_size`), `pg_proc.dat`
  (`pg_stat_force_next_flush`).
- **The free space map**: `indexfsm.c` (`RecordFreeIndexPage`), `freespace.c`
  (`fsm_space_cat_to_avail`), and `pg_freespacemap`'s `pg_freespace`.
- **GUCs**: `guc_tables.c` for `maintenance_work_mem`, `gin_pending_list_limit`,
  `statement_timeout`, `lock_timeout`, `transaction_timeout`,
  `idle_in_transaction_session_timeout` and `default_statistics_target`.
- **Documentation, same checkout**: `gin.sgml` (fast update, tips), `maintenance.sgml`
  (`routine-reindex`), `ref/reindex.sgml`, `ref/comment.sgml`.
- **Citation re-verification, 2026-09-17**: every citation the page carried at review time —
  **154 occurrences over 73 distinct file-and-line ranges in 29 files** — was dumped out of
  `raw/postgres-17/` and read against the claim it backs. Every range is in bounds, none
  crosses a version, and **every one supports its label**, so this pass corrected no
  citation; it added **23** ranges for the no-defeat and concurrency work, taking the page to
  **208 occurrences over 96 ranges in 32 files**, with none dropped. The page's one
  repo-wide grep was re-run: `RelationTruncate` and `smgrtruncate` still have **zero** hits
  under `src/backend/access/gin/`.
- **Server work, 2026-09-17**: one 17.11 build from the pin and **two** runs of the filed
  script end to end — `make check` plus five contrib suites on each, 25 fixtures through five
  phases, 79 settle and maintenance steps with their proofs, 158 horizon readings, a 28-table
  analyze census, 23 page censuses under the measurement lock, 24 oracle rebuilds, six
  probes, eleven edge cases, a verbatim lifecycle replay, and the three-way diff of the
  published statements against this page. The 2026-09-15 run this revision supersedes is
  described in the log entry of that date.
- **Server work, 2026-09-24**, on macOS 27 arm64: one 17.11 build from the pin per empty
  sandbox, and four passes of the whole default order. The first ran the filed script
  unchanged, before any edit. The second and third ran the edited script without its two
  `.csv` dumps, from an empty sandbox and then after `reset`. The fourth, the recorded run,
  ran the final text from an empty sandbox. The recorded run covered `make check` plus the
  five contrib suites, 24 fixtures through five phases, 75 settle and maintenance steps with
  their proofs, 150 horizon readings, a 27-table analyze census, 23 page censuses under the
  measurement lock and 3 more inside the churn phase, 23 oracle rebuilds, six probes, eleven
  edge cases, a verbatim lifecycle replay, and the three-way diff of the published
  statements. `pg_controldata` was read on its data directory before `clean`.
- **Citations, 2026-09-24**: the three ranges that backed only `i01`'s section
  (`vacuumlazy.c` 387-397, 1064-1066 and 695-731) left with it. Six ranges were added, for
  `ANALYZE`'s sample size and block sampler, and each was read at the pin. Every citation the
  page carries was checked mechanically for a file that exists under `raw/postgres-17/` and a
  line range inside it; see [Evidence Map](#evidence-map).

## Evidence Map

| Claim | Source |
|---|---|
| A GIN index's file never shrinks; freed pages go to the FSM | [ginvacuum.c#ginvacuumcleanup](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L694-L803), [ginvacuum.c#GinPageIsRecyclable](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L805-L829), [ginfast.c:1015-1020](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1015-L1020) |
| `pg_relation_size` is the main fork, stat-ed from the files | [system_functions.sql#pg_relation_size](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L285-L289), [dbsize.c#calculate_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L302-L343) |
| `reltuples` is `-1` when unknown | [pg_class.h:62-66](../../../../raw/postgres-17/src/include/catalog/pg_class.h#L62-L66) |
| `CREATE INDEX`/`REINDEX` write the AM's `index_tuples` into the index row and the heap count into the table row | [index.c:3126-3135](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3135), [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2788-L2842) |
| For GIN that count is extracted entries, summed over rows and over indexed columns | [gininsert.c#ginHeapTupleBulkInsert](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L252-L274), [gininsert.c#ginBuildCallback](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L276-L288), [gininsert.c:418-428](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L418-L428) |
| A GIN build flushes its accumulator when it reaches `maintenance_work_mem` | [gininsert.c:290-291](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L290-L291) |
| `ANALYZE` overwrites every index with `ceil(tupleFract * totalrows)`, `tupleFract` = 1.0 for plain indexes | [analyze.c:439-449](../../../../raw/postgres-17/src/backend/commands/analyze.c#L439-L449), [analyze.c:647-663](../../../../raw/postgres-17/src/backend/commands/analyze.c#L647-L663) |
| `VACUUM` produces `num_index_tuples`, and GIN sets it to the heap tuple count | [vacuum.c#vac_cleanup_one_index](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L2564-L2583), [ginvacuum.c:733-739](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L733-L739) |
| The `pg_class` write happens in `update_relstats_all_indexes`, and is skipped when the count is an estimate | [vacuumlazy.c#update_relstats_all_indexes](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3072-L3099), [vacuumlazy.c:3086-3087](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L3086-L3087) |
| `estimated_count` is true whenever the heap scan skipped a page, and is passed to the AM | [vacuumlazy.c:2356](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2356), [vacuumlazy.c:2481](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L2481) |
| Plain `REINDEX` keeps the index OID and changes the relfilenode | [index.c:3781-3789](../../../../raw/postgres-17/src/backend/catalog/index.c#L3781-L3789) |
| `REINDEX CONCURRENTLY` moves the `pg_description` row to the new index OID | [index.c:1740-1784](../../../../raw/postgres-17/src/backend/catalog/index.c#L1740-L1784) |
| `obj_description(oid, 'pg_class')` reads `pg_description` at `objsubid = 0` | [system_functions.sql#obj_description](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L291-L301) |
| A comment is a `text` catalog row keyed on objoid/classoid/objsubid | [pg_description.h:48-66](../../../../raw/postgres-17/src/include/catalog/pg_description.h#L48-L66) |
| Churn, analyze and staleness counters come from `pg_stat_all_tables` | [system_views.sql#pg_stat_all_tables](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L670-L703) |
| `indisvalid` means "valid for use by queries" | [pg_index.h:42](../../../../raw/postgres-17/src/include/catalog/pg_index.h#L42) |
| Posting lists convert to posting trees when they outgrow `GinMaxItemSize` | [gininsert.c#buildFreshLeafTuple](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L125-L166), [gininsert.c#addItemPointersToLeafTuple](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c#L45-L111) |
| The entry tree never deletes a tuple or a page, so retired keys survive every VACUUM | [README#page-deletion](../../../../raw/postgres-17/src/backend/access/gin/README#L389-L396) |
| The pending list exists, is bounded by `gin_pending_list_limit`, and is flushed by VACUUM/autoanalyze | [gin.sgml#gin-fast-update](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L500-L537), [gin.sgml#guc-gin-pending-list-limit](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L595-L616) |
| An insert stream flushes the pending list in the foreground once `nPendingPages * GIN_PAGE_FREESIZE` exceeds the limit | [ginfast.c:458-471](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L458-L471), [ginfast.c:41-42](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L41-L42) |
| `gin_clean_pending_list()` returns its own count of deleted pending pages | [ginfast.c:1090](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L1090) |
| In an autovacuum worker an `analyze_only` GIN cleanup flushes the pending list and returns before the census; every other caller gets a no-op | [ginvacuum.c#analyze_only-worker](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L709-L717) |
| ANALYZE-only index cleanup is skipped inside a `VACUUM ANALYZE` | [analyze.c#analyze-only-cleanup](../../../../raw/postgres-17/src/backend/commands/analyze.c#L694-L721) |
| `vacuum()` vacuums each relation and then analyzes it | [vacuum.c#vacuum-then-analyze](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L618-L650) |
| The metapage page counts have one writer, `ginUpdateStats`, reached only from the census inside `ginvacuumcleanup` | [ginutil.c#ginUpdateStats](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L645-L650) |
| The fourth field of the `VACUUM VERBOSE` index line is `pages_free` | [vacuumlazy.c#verbose-index-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L720-L731) |
| A held snapshot keeps deleted tuples non-removable, because `OldestXmin` comes from `GetOldestNonRemovableTransactionId` | [vacuum.c:1120](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L1120) |
| An index FSM records a free page as `BLCKSZ - 1` and reads it back as a category floor | [indexfsm.c#RecordFreeIndexPage](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c#L48-L55), [freespace.c#fsm_space_cat_to_avail](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c#L427-L435) |
| The launcher's three verdicts, their formulas and the strictly-greater comparison | [autovacuum.c#vacthresh-anlthresh](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3074-L3076), [autovacuum.c#verdicts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3092-L3095) |
| `autovacuum_enabled = false` short-circuits both verdicts | [autovacuum.c#av_enabled-return](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L3048-L3054) |
| `ANALYZE` zeroes `mod_since_analyze` in the shared entry | [pgstat_relation.c:331-337](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L331-L337) |
| Pending relation stats are applied additively, with a clamp on live/dead | [pgstat_relation.c:849-867](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L849-L867) |
| `analyze_count` is incremented in the same locked section as the reset | [pgstat_relation.c:339-348](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c#L339-L348) |
| Non-forced flushes are rate-limited to 1000 ms, forced at 60000 ms | [pgstat.c:117-122](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L117-L122), [pgstat.c:636-655](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c#L636-L655) |
| `pg_stat_force_next_flush()` exists and forces the next flush | [pg_proc.dat:5916-5920](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L5916-L5920) |
| `COMMENT` takes `ShareUpdateExclusiveLock` and requires ownership | [comment.sgml:95-98](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L95-L98), [comment.sgml:100-109](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L100-L109), [comment.c:66-77](../../../../raw/postgres-17/src/backend/commands/comment.c#L66-L77) |
| Comments are replaced wholesale and dropped with the object | [comment.sgml:87-93](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L87-L93) |
| Any user in the database can read any comment | [comment.sgml:292-298](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml#L292-L298) |
| `pg_relation_size` opens the relation with `AccessShareLock` | [dbsize.c#pg_relation_size](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L345-L371) |
| `maintenance_work_mem`, `gin_pending_list_limit`, `statement_timeout`, `lock_timeout` are all `PGC_USERSET` | [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2466-L2474), [guc_tables.c#gin_pending_list_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3577-L3585), [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631) |
| `fastupdate` defaults to on, and changing it needs `AccessExclusiveLock` | [gin_private.h:33](../../../../raw/postgres-17/src/include/access/gin_private.h#L33), [reloptions.c:123-131](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L123-L131) |
| GIN build size is sensitive to `maintenance_work_mem` | [gin.sgml#guc-maintenance-work-mem](../../../../raw/postgres-17/doc/src/sgml/gin.sgml#L584-L593) |
| Non-B-tree bloat is not well researched; monitor the physical size | [maintenance.sgml#routine-reindex](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml#L1042-L1046) |
| A bloated index is a documented reason to `REINDEX` | [reindex.sgml:54-64](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml#L54-L64) |

Added on 2026-09-17, for the no-defeat rule, the concurrency rule and the sampled
denominator:

| Claim | Source |
|---|---|
| Under a pinned horizon the churn's rows are `HEAPTUPLE_RECENTLY_DEAD` and are only counted | [vacuumlazy.c#recently_dead_tuples](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L208-L212), [vacuumlazy.c#lazy_scan_noprune-recently-dead](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1770-L1776) |
| Index vacuuming is entered only when dead TIDs were collected, so `ginbulkdelete` never runs under a pinned horizon | [vacuumlazy.c#lazy_vacuum-gate](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L1047-L1052) |
| `ginvacuumcleanup` still flushes the pending list and rewrites the metapage when `ginbulkdelete` did not run | [ginvacuum.c#cleanup-pending-when-no-bulkdelete](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L719-L729), [ginvacuum.c#ginvacuumcleanup-census](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L752-L789) |
| `VACUUM (VERBOSE)` reports the recently-dead count as `tuples: ... are dead but not yet removable` | [vacuumlazy.c#verbose-tuples-line](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c#L659-L663) |
| `OldestXmin` folds in every backend's xid and xmin, exempting only a vacuuming or decoding backend | [procarray.c#ComputeXidHorizons-backend-xmin](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1792-L1815), [procarray.c#skip-vacuum-and-decoding](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1817-L1832) |
| A replication slot's `xmin` is folded into the same horizon | [procarray.c#slot-horizons](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c#L1896-L1902) |
| A prepared transaction keeps its xid running through a dummy `PGPROC` | [twophase.c#dummy-pgproc](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L24-L26) |
| A lock conflict makes `VACUUM`/`ANALYZE` print a skipping line and return | [vacuum.c#skip-lock-not-available](../../../../raw/postgres-17/src/backend/commands/vacuum.c#L828-L855) |
| An autovacuum worker forces all four settable timeouts to `0`, and why | [autovacuum.c#worker-timeouts](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c#L1462-L1470) |
| `transaction_timeout` and `idle_in_transaction_session_timeout` are `PGC_USERSET` | [guc_tables.c#transaction_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2644-L2653), [guc_tables.c#idle_in_transaction_session_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2633-L2642) |
| The horizon holders and slots a run reads are `pg_stat_activity` and `pg_replication_slots` columns | [system_views.sql#pg_stat_activity-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L878-L885), [system_views.sql#pg_replication_slots-xmin](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1006-L1017) |
| The three progress views a census must flag, and the one that names `REINDEX` | [system_views.sql#pg_stat_progress_vacuum](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1209-L1227), [system_views.sql#pg_stat_progress_analyze](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1188-L1207), [system_views.sql#pg_stat_progress_create_index](../../../../raw/postgres-17/src/backend/catalog/system_views.sql#L1256-L1289) |
| A pending-list flush drives keys through `ginEntryInsert`, and a split there takes a new page | [ginfast.c#flush-entry-insert](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c#L926-L933), [ginbtree.c#split-newbuffer](../../../../raw/postgres-17/src/backend/access/gin/ginbtree.c#L463-L466) |
| `ANALYZE`'s row count is an extrapolation from the sampled blocks, written to `pg_class` | [analyze.c#sample-extrapolation](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1278-L1289), [analyze.c#table-relstats](../../../../raw/postgres-17/src/backend/commands/analyze.c#L637-L645) |

Added on 2026-09-24, for the sampled denominator:

| Claim | Source |
|---|---|
| `ANALYZE` wants as many sample rows as its most demanding column, 300 times that column's statistics target, and a column with no target of its own uses `default_statistics_target`, which defaults to 100 | [analyze.c:488-513](../../../../raw/postgres-17/src/backend/commands/analyze.c#L488-L513), [analyze.c:1851-1853](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1851-L1853), [analyze.c:1894](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1894), [guc_tables.c#default_statistics_target](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2070-L2079) |
| It reads that many blocks, chosen at random under a fresh seed, or every block of a smaller table | [analyze.c:1180-1187](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1180-L1187), [sampling.c#BlockSampler_Init](../../../../raw/postgres-17/src/backend/utils/misc/sampling.c#L23-L55) |

Every number in the tables above is a measurement from the 17.11 run described under
[The last run](#the-last-run), not a source claim.

## Open Questions

1. **The one declared bound failed, and the column that failed it is still printed.**
   `est_reclaimable` was violated on 8 of 21 fixtures and is demoted to a level, but the
   statement's text is unchanged, so an operator reading the output sees a byte count with
   nothing in the row to warn them. Whether the right fix is to drop the column, rename it to
   a ranking score, or print the declared kind beside it, is a design choice this page does
   not make — and any of them would need a re-run, because the text that ran is the text that
   is scored.
2. **The payoff threshold is this page's, not the engine's.** `truth_pct >= 33.33` was
   derived from the brief's own 1.50 candidate threshold, and `c05`'s 30.45 % is a false
   positive only against that number. v17 defines no target density for a GIN index
   ([ginutil.c#ginoptions](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c#L601-L614)),
   so a `FALSE POSITIVE` here is not comparable with one on a page that chose differently.
3. **`normalized_index_growth` is not monotone in reclaimable space.** It ranks `c05`
   (1.9184, 30.45 % returned) above `c12` (1.5171, 34.08 %) and `x03` (1.8263, 45.33 %).
   Whether a better normalizer exists inside the catalog-only constraint is untested; the
   obvious candidate, an entry-count term, is what the brief rules out.
4. **A rebuild can grow a GIN index, and nothing the method reads can predict it.** `p02`
   returned −21.01 %. The mechanism is understood (a bulk build appends per flush round while
   incremental insertion packed denser), but the method has no input that distinguishes such
   an index from one worth rebuilding, and this run has exactly one example of it.
5. **The pending-list blind spot is characterised, not corrected.** [`pgstatginindex`](../../../glossary.md#pgstatindex) reports
   `pending_pages`, which would let an evaluation subtract the live pending list, but it is
   contrib and so outside the brief's catalog-only rule, and it does not report the
   *high-water mark* left behind after a flush. No catalog-only substitute was found.
6. **An auto-analyze-only maintained table is almost always refused.** The window where the
   analyze verdict is crossed, both vacuum verdicts are not, and the method's churn gate is
   satisfied is 1,001 rows wide at any table size; `a02` sits inside it only because the
   fixture was built to. Whether the churn gate should be lowered to `0.1 N` to match the
   launcher's analyze scale factor is untested, and doing so would evaluate far more indexes
   for far less return.
7. **Two ladder rungs cannot be exercised under the protocol.** Rung 7,
   `no ANALYZE since baseline`, cannot fire because the maintenance step analyzes every
   churned table, and `stats_lag` reads 0.000 on all 23 fixtures for the same reason. Both
   are still the right guards for a server that does not maintain its tables; neither is
   scored here.
8. **Rung 2, `invalid index`, was never exercised.** No fixture produced a failed
   `CREATE INDEX CONCURRENTLY`, so that rung remains source-justified from `indisvalid` only.
9. **The vacuum side of the launcher is never simulated.** The protocol records the
   dead-tuple and insert thresholds and then maintains regardless of them, so no fixture here
   is a GIN index whose dead entries were never vacuumed — which is exactly the state a
   size-only heuristic would most like to catch. The concept page files the same gap as a
   limit of the protocol.
10. **The partial index was measured at one selectivity.** `x01` indexes a quarter of its
    rows, and the method divides by the table's `reltuples`, which is not the indexed
    population; the rebuild returned 68.75 % and the method flagged it, so the mismatch did
    not hurt here. `ginvacuumcleanup`'s own comment calls its entry count "bogus if the index
    is partial"
    ([ginvacuum.c:733-739](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c#L733-L739)),
    and `ANALYZE` computes a real `tupleFract` for one
    ([analyze.c:948-953](../../../../raw/postgres-17/src/backend/commands/analyze.c#L948-L953)).
    Expect false positives at other selectivities; none were measured.
11. **The census's decision power is exercised only by synthetic tables.** All 24 fixture
    tables read `n_mod_since_analyze = 0` when the census ran, because the maintenance step
    had already analyzed them, so `tc_past`, `tc_exact` and `tc_off` are doing all the work.
12. **`a02`'s metapage is off by one entry page against the census.** The stand-in's flush
    allocated an entry page that no `ginUpdateStats` ever recorded, and only a `VACUUM` would
    reconcile it. That is the declared consequence of the stand-in, but it means an
    auto-analyze-maintained GIN index has a metapage that under-reports its own entry tree,
    which no shipped test covers.
13. **One block size, one key universe, two platforms.** `block_size` 8192,
    `max_data_alignment` 8, `shared_buffers` 512MB, `maintenance_work_mem` 256MB except in
    the explicit budget probe, and five keys per row from a 10,000-value universe. The runs
    of 2026-09-17 (Linux x86_64, gcc) and 2026-09-24 (macOS arm64, clang) agree on every
    scored cell that no `ANALYZE` sample decides. That shows the numbers do not depend on
    the compiler or the CPU at this block size and alignment. It does not show that the
    1.50/1.20 boundaries or the 0.20 churn gate transfer to a different key cardinality, a
    different tuple width, or a 100x larger table.
14. **The scored `est_reclaimable` is a recomputation, not the printed string.** The scoring
    recomputes the bytes from the unrounded inputs and checks them against the statement's own
    `pg_size_pretty` output, which matched on 23 of 23; it does not parse the printed text
    back, so a formatting change in `pg_size_pretty` would go unnoticed.
15. **The two concurrency behaviors the protocol lists are only partly reached.** `c09`
    covers a rebuild between the maintenance step and the decide pass, but no writer stream or
    concurrent `VACUUM` ran against a decide pass, because the measurement lock excludes both
    by construction. The page census's own non-atomicity is therefore unexercised here, and
    the progress-view flags it now records are all zero for the same reason: they say the
    censuses were unrefuted, not that a racing command would have been caught.
16. **The horizon reading is a read, not an interlock.** The run takes one on each side of
    every settle and maintenance step, but a holder that appeared and vanished inside the
    step leaves no trace in either reading. The `dead but not yet removable` count does not
    have that hole, which is why it is the check the run dies on; the horizon reading is
    corroboration and an aid to diagnosis. The concept page files the same limit.
17. **The mechanism probes are outside the no-defeat rule.** P1 through P6 are not scored
    fixtures — no oracle, no declared bound — so they run under the run's ordinary timeouts
    and are not proved statement by statement. Their `VACUUM`s ran with nothing holding the
    horizon, and the run records one horizon reading at the start of the probe database to
    say so, but that is one reading for six probes rather than one per statement.
18. **The settle step's cost is measured on one key universe and one pending-list limit.**
    The 8 fixtures that grew across their settle step added 294,912 to 4,849,664 bytes at
    `gin_pending_list_limit = 4096 kB`, five keys per row from a 10,000-value universe. How
    that scales with the limit, the key cardinality or the insert batch size is untested, and
    a fixture with 0 pending pages at the end of its writes came through byte-identical every
    time.
19. **`c02`'s bound verdict is inside the noise of its own denominator.** Seven runs of
    the same fixture produced three `HELD` and four `VIOLATED`, between −0.03 and +0.02
    points, with the oracle and `index_size_ratio` byte-identical. `ANALYZE` samples 30,000
    of the table's 30,928 pages and writes a different `reltuples` each time, and the bound
    holds exactly when that reading is at most 999,633. The recorded run files it as
    `HELD`, so the tally reads 13 held and 7 violated. The demotion does not depend on
    `c02`: the other seven violations decide it. But no single run of this fixture decides
    its bound.
20. **Running the published statement inside the measurement lock logs a warning.** The
    statement opens its own transaction, so the decide pass prints
    `WARNING: there is already a transaction in progress` and the statement's own `COMMIT`
    releases the lock. Nothing in the output is wrong, but the text that is scored is not the
    text an operator would run standalone in one respect: standalone, its `BEGIN` is the
    outer transaction.
21. **Why the `ANALYZE` readings lean high is not established.** Across five passes of
    probe P6, 18 of 25 readings came out above the true 1,000,000 rows and 7 below. The
    source extrapolates from blocks picked at random under a fresh seed, on the stated
    assumption that the unscanned pages look like the scanned ones
    ([analyze.c#sample-extrapolation](../../../../raw/postgres-17/src/backend/commands/analyze.c#L1278-L1289),
    [sampling.c#BlockSampler_Init](../../../../raw/postgres-17/src/backend/utils/misc/sampling.c#L23-L55)).
    Nothing read for this page predicts a bias in either direction. 25 readings do not
    settle whether the lean is real or chance, and this page does not claim either.
22. **No fixture here shows the settle proof meeting a `VACUUM` that skipped index cleanup.**
    `i01` was that fixture until 2026-09-24. The protocol no longer requires the case, so the
    page no longer runs it. The page still asserts the settle step from the index's own state
    on every fixture, but it no longer has a measured case of that assertion catching a
    `VACUUM` that returned successfully without touching the index.
23. **`max_data_alignment` is not a number the script writes.** The recorded value, 8, was
    read with `pg_controldata` on the recorded run's data directory before `clean`. The page
    does not record how the 2026-09-17 value was read. `block_size` is in `settings.txt`. A
    future revision of the script could write `pg_controldata`'s output to `out/`.

## Source References

- [ginvacuum.c](../../../../raw/postgres-17/src/backend/access/gin/ginvacuum.c) - `ginvacuumcleanup`, its `analyze_only` branch, `GinPageIsRecyclable`, `ginDeletePage`, the `num_index_tuples` assignment.
- [gininsert.c](../../../../raw/postgres-17/src/backend/access/gin/gininsert.c) - `ginbuild`, `ginBuildCallback` and its memory-driven flush, `ginHeapTupleBulkInsert`, `buildFreshLeafTuple`, `addItemPointersToLeafTuple`.
- [ginfast.c](../../../../raw/postgres-17/src/backend/access/gin/ginfast.c) - `GIN_PAGE_FREESIZE`, the foreground cleanup threshold, `ginInsertCleanup` and its `ginEntryInsert` loop, `shiftList`, `gin_clean_pending_list` and its return value, the pending-page FSM recycling.
- [ginbtree.c](../../../../raw/postgres-17/src/backend/access/gin/ginbtree.c) - the split that takes a new page, which is why settling an index can grow it.
- [ginutil.c](../../../../raw/postgres-17/src/backend/access/gin/ginutil.c) - `ginhandler`, `ginoptions`, `GinNewBuffer`, `ginUpdateStats`.
- [gin_private.h](../../../../raw/postgres-17/src/include/access/gin_private.h), [ginblock.h](../../../../raw/postgres-17/src/include/access/ginblock.h), [reloptions.c](../../../../raw/postgres-17/src/backend/access/common/reloptions.c) - `GinOptions`, the metapage struct and flag bits, `fastupdate` and `gin_pending_list_limit` defaults and lock levels.
- [README](../../../../raw/postgres-17/src/backend/access/gin/README) - page deletion, and why the entry tree keeps its tuples.
- [index.c](../../../../raw/postgres-17/src/backend/catalog/index.c) - `index_build`, `index_update_stats`, `reindex_index`, `index_concurrently_swap`.
- [analyze.c](../../../../raw/postgres-17/src/backend/commands/analyze.c) - `do_analyze_rel`, `tupleFract`, the ANALYZE-only cleanup gate, the per-index `vac_update_relstats` call, the sample size `targrows` and `std_typanalyze`'s `300 * attstattarget`, and `acquire_sample_rows`' block sample and its extrapolation of the table's row count.
- [sampling.c](../../../../raw/postgres-17/src/backend/utils/misc/sampling.c) - `BlockSampler_Init`, which picks `ANALYZE`'s random blocks, or all of a small table's.
- [vacuum.c](../../../../raw/postgres-17/src/backend/commands/vacuum.c) - `vac_cleanup_one_index`, `vacuum_get_cutoffs`, the vacuum-then-analyze order, the skip-for-want-of-a-lock messages.
- [vacuumlazy.c](../../../../raw/postgres-17/src/backend/access/heap/vacuumlazy.c) - `update_relstats_all_indexes`, the `estimated_count` guard, `recently_dead_tuples` and the `lazy_vacuum` gate, the `VERBOSE` tuples and index lines.
- [procarray.c](../../../../raw/postgres-17/src/backend/storage/ipc/procarray.c), [twophase.c](../../../../raw/postgres-17/src/backend/access/transam/twophase.c) - what pins the removal horizon: every backend's xid and xmin, the vacuuming and decoding exemption, a replication slot's `xmin`, and a prepared transaction's dummy `PGPROC`.
- [autovacuum.c](../../../../raw/postgres-17/src/backend/postmaster/autovacuum.c) - `relation_needs_vacanalyze`'s thresholds, the reloption-or-GUC selection, the `av_enabled` short circuit, and the worker's forcing of the four settable timeouts to zero.
- [pgstat_relation.c](../../../../raw/postgres-17/src/backend/utils/activity/pgstat_relation.c) - `pgstat_report_analyze`, `pgstat_report_vacuum`, `pgstat_relation_flush_cb`.
- [pgstat.c](../../../../raw/postgres-17/src/backend/utils/activity/pgstat.c) - `pgstat_report_stat`, `PGSTAT_MIN_INTERVAL`, `PGSTAT_MAX_INTERVAL`.
- [comment.c](../../../../raw/postgres-17/src/backend/commands/comment.c) - `CommentObject`, `check_object_ownership`.
- [dbsize.c](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c) - `calculate_relation_size`, `pg_relation_size`.
- [indexfsm.c](../../../../raw/postgres-17/src/backend/storage/freespace/indexfsm.c), [freespace.c](../../../../raw/postgres-17/src/backend/storage/freespace/freespace.c) - what an index FSM stores, and what a free page reads back.
- [system_functions.sql](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql) - `obj_description`, `pg_relation_size`.
- [system_views.sql](../../../../raw/postgres-17/src/backend/catalog/system_views.sql) - `pg_stat_all_tables`, `pg_stat_activity`'s `xact_start`/`backend_xid`/`backend_xmin`, `pg_replication_slots`' `xmin`/`catalog_xmin`, and the three progress views a census flags.
- [guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c) - `maintenance_work_mem`, `gin_pending_list_limit`, `statement_timeout`, `lock_timeout`, `transaction_timeout`, `idle_in_transaction_session_timeout`, `default_statistics_target`, the autovacuum thresholds.
- [pg_class.h](../../../../raw/postgres-17/src/include/catalog/pg_class.h), [pg_index.h](../../../../raw/postgres-17/src/include/catalog/pg_index.h), [pg_description.h](../../../../raw/postgres-17/src/include/catalog/pg_description.h), [pg_proc.dat](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat).
- [gin.sgml](../../../../raw/postgres-17/doc/src/sgml/gin.sgml) - fast update technique, tips and tricks.
- [maintenance.sgml](../../../../raw/postgres-17/doc/src/sgml/maintenance.sgml) - `routine-reindex`.
- [ref/reindex.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/reindex.sgml), [ref/comment.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/comment.sgml).

## Navigation

- [v17/index](../../index.md) - PostgreSQL 17 landing page.
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [Wiki Glossary (unverified)](../../../glossary.md) - the shared vocabulary this page links on first use.
- [Mandatory GIN Bloat Tests (unverified)](../../common-concepts/mandatory-gin-bloat-tests.md) - the measurement protocol every number on this page was produced under.
- [Detecting Inflated Non-B-Tree Indexes From Catalogs and a COMMENT-Stored Baseline in PostgreSQL 17 (unverified)](non-btree-index-inflation-comment-baseline.md) - the five-access-method sibling, which normalizes by a per-AM population term instead of the table `reltuples`.
- [Measuring Wasted and Reclaimable Bytes in a GIN Index With Contrib Extensions on PostgreSQL 17 (unverified)](gin-index-wasted-space-contrib.md) - what a `pageinspect` page census can measure that catalogs cannot.
- [Reading an Index's Entry Count From the Catalogs, for Every Index Type, in PostgreSQL 17 (unverified)](index-entry-count-from-catalogs.md) - the full three-writer story behind an index's own `reltuples`.
- [How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 17 (unverified)](reindex-index-concurrently.md) - the rebuild path this heuristic recommends.
- [Planner Penalties for Bloated Indexes in PostgreSQL 17 (unverified)](../query-planning/bloated-indexes-query-planner.md) - what the planner does and does not see about a bloated index.
- [versions](../../../versions.md) - source pin manifest.
- [index](../../../index.md) - global wiki catalog.
