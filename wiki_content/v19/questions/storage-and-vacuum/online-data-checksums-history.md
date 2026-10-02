---
type: question
version: 19
pinned_commit: dae3463fa969931458f1488f9b7af11e3741cd54
verified: false
verified_by_agent: not yet
---

# History of Online Data Checksum Enabling and Disabling in PostgreSQL 19, and All Its Commits (unverified)

## Contents

- [Question](#question)
  - [Filing note](#filing-note)
- [Answer](#answer)
  - [Timeline](#timeline)
  - [How the Reverted Feature Worked](#how-the-reverted-feature-worked)
  - [How the Commit List Was Built](#how-the-commit-list-was-built)
  - [2018 to 2019: The First Attempt](#2018-to-2019-the-first-attempt)
  - [2026: Preparation and the Main Commit](#2026-preparation-and-the-main-commit)
  - [2026: Follow-Up Commits](#2026-follow-up-commits)
  - [Release-Note Commits](#release-note-commits)
  - [Tree-Wide Commits That Edited Feature Code](#tree-wide-commits-that-edited-feature-code)
  - [Translation Imports](#translation-imports)
  - [The Revert and Its Cleanups](#the-revert-and-its-cleanups)
  - [What the Pinned Tree Still Contains](#what-the-pinned-tree-still-contains)
  - [Commits Checked and Excluded](#commits-checked-and-excluded)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Follow AGENTS.md. In PostgreSQL 19, question: the history of the feature "online enabling and disabling of data checksums"; list all commits.

### Filing note

The asker chose two scope answers before drafting:

- **No fetch.** `raw/postgres-19` is a shallow clone, and the asker chose to file without deepening it. The 2018 and 2019 commits below are listed as this clone's older release tags reach them. Their ancestry to the pin, and the master commits the clone cannot see, are recorded under [Open Questions](#open-questions).
- **Glossary.** Ten new glossary terms were added, each checked on PostgreSQL 19 only.

## Answer

**At the pinned commit, PostgreSQL 19 cannot turn [data checksums](../../../glossary.md#data-checksums) on or off in a running cluster.** The feature was committed on 2026-04-03 as `f19c0eccae9`. It shipped in 19beta1, 19beta2 and 19beta3. On 2026-09-16, `c05d5ce1236` reverted it on `REL_19_STABLE`, five days before the 19beta4 stamp `b73d13c32c8`. The revert message gives the reason. The feature "saw a number of postcommit fixes during the beta period", concerns were raised that more would surface after release, and the revert avoids "shipping code which may have bugs" (`c05d5ce1236`).

What the pin offers instead:

- The read-only `data_checksums` setting is a `bool` again. Its context is `PGC_INTERNAL`, so no configuration change can set it ([guc_parameters.dat#data_checksums](../../../../raw/postgres-19/src/backend/utils/misc/guc_parameters.dat#L581-L586)).
- The docs describe only initdb-time and offline changes ([wal.sgml:246-253](../../../../raw/postgres-19/doc/src/sgml/wal.sgml#L246-L253), [wal.sgml#checksums-offline-enable-disable](../../../../raw/postgres-19/doc/src/sgml/wal.sgml#L271-L282)).
- The offline tool `pg_checksums` checks, enables or disables checksums on a stopped cluster only ([pg_checksums.c:1-5](../../../../raw/postgres-19/src/bin/pg_checksums/pg_checksums.c#L1-L5), [pg_checksums.c:584-598](../../../../raw/postgres-19/src/bin/pg_checksums/pg_checksums.c#L584-L598)).

The 2026 commit was the second attempt. Magnus Hagander committed a first version on 2018-04-05 (`1fde38beaa0`) and reverted its backend parts four days later (`a228cc13aea`). Both commits come before the 11beta1 stamp, so no release carried that version.

The full history has 85 commits:

| Group | Commits | Section |
|---|---:|---|
| 2018 attempt, its revert, and the 2019 barrier infrastructure | 6 | [2018 to 2019](#2018-to-2019-the-first-attempt) |
| 2026 preparation and main commit | 2 | [2026: Preparation](#2026-preparation-and-the-main-commit) |
| 2026 follow-up fixes, tests and docs | 51 | [2026: Follow-Up Commits](#2026-follow-up-commits) |
| Release-note commits | 7 | [Release-Note Commits](#release-note-commits) |
| Tree-wide commits that edited feature code | 12 | [Tree-Wide Commits](#tree-wide-commits-that-edited-feature-code) |
| Translation imports that carried the feature's messages | 4 | [Translation Imports](#translation-imports) |
| The revert and two cleanups | 3 | [The Revert](#the-revert-and-its-cleanups) |

The main commit and its 51 follow-ups make 52 commits. The revert names 30 of them. It does not name the other 22, but it removes their code too.
- Gustafsson committed ten of those 22: seven test-only commits, plus `75152c5dc5d`, `9eb77f9fc80` and `4afa9788b51`. Other committers made the remaining twelve.
- Only these of their lines survive:
  - the message split from `250942b0d82`;
  - the injection point from `9eb77f9fc80`;
  - the unrelated half of `d40aed55422`;
  - two reflowed docs lines from `dff11f846c4`.

[Commits Checked and Excluded](#commits-checked-and-excluded) lists 27 more commits that matched a search but are not part of the feature.

### Timeline

| Date | Event | Commit |
|---|---|---|
| 2018-04-05 | First version committed, with a launcher/worker background process and a new WAL record | `1fde38beaa0` |
| 2018-04-07 | Its flapping isolation tests switched off | `bf75fe47e44` |
| 2018-04-09 | Backend parts reverted; the offline `pg_verify_checksums` tool kept; catalog version bumped | `a228cc13aea`, `f5543d47bcb` |
| 2019-12-19 | [ProcSignal barriers](../../../glossary.md#procsignal-barrier) added. The message names "turning checksums on while the system is running" as a use. | `16a4e4aecd4` |
| 2026-03-31 | `XLOG_CHECKPOINT_REDO` given a record struct, "inspired by the online checksums patch" | `097ab69d17f` |
| 2026-04-03 | Second version committed | `f19c0eccae9` |
| 2026-04-04 to 2026-06-24 | 29 follow-up commits on master | see below |
| 2026-06-01 | 19beta1 stamped with the feature | `4b0bf0788b0` |
| 2026-06-29 | `REL_19_STABLE` branches at `9cfd19bc10a`; master is stamped 20devel | `a281a3e6dbb` |
| 2026-07-09 to 2026-09-01 | 22 follow-up commits on `REL_19_STABLE` | see below |
| 2026-07-13, 2026-08-10 | 19beta2 and 19beta3 stamped with the feature | `7873db5369b`, `3638289fb57` |
| 2026-09-16 | Feature reverted; first cleanup | `c05d5ce1236`, `4a9a6c5a69c` |
| 2026-09-17 | Second cleanup | `6b0760a10a3` |
| 2026-09-21 | 19beta4 stamped without the feature | `b73d13c32c8` |

Each beta claim comes from `git merge-base --is-ancestor` in `raw/postgres-19`. `f19c0eccae9` is an ancestor of `REL_19_BETA1` through `REL_19_BETA4`, and `c05d5ce1236` is an ancestor of `REL_19_BETA4` only. The branch point is the merge base of `a281a3e6dbb` and the pin.

### How the Reverted Feature Worked

The pinned tree no longer has this code. The references below name a commit and a path, for example `c05d5ce1236^:src/backend/postmaster/datachecksum_state.c:18-47`. Open one with `git -C raw/postgres-19 show <commit>:<path>`. `c05d5ce1236^` is the last tree before the revert.

- **SQL entry points.**
  - `pg_enable_data_checksums(cost_delay int4 DEFAULT 0, cost_limit int4 DEFAULT 100)` and `pg_disable_data_checksums()` both returned `void`. Their catalog ACL was `{POSTGRES=X}` (`c05d5ce1236^:src/include/catalog/pg_proc.dat:12363-12372`).
  - Both functions refused to run during recovery and raised "must be superuser to change data checksum state" for non-superusers (`c05d5ce1236^:src/backend/postmaster/datachecksum_state.c:551-591`).
- **Four states.** `f19c0eccae9` added `ChecksumStateType` with four values stored in the [control file](../../../glossary.md#control-file): off 0, on 1 (`PG_DATA_CHECKSUM_VERSION`), inprogress-off 2 and inprogress-on 3. It moved `PG_DATA_CHECKSUM_VERSION` out of `bufpage.h` into that enum (`f19c0eccae9`, `src/include/storage/checksum.h` and `src/include/storage/bufpage.h` hunks). `data_checksums` became an enum setting with a show hook (`c05d5ce1236^:src/backend/utils/misc/guc_parameters.dat:581-588`), which `b364828f825` documented.
- **Meaning of each state.** In inprogress-on, every write computes a checksum but reads do not verify it. Inprogress-off also writes checksums without verifying them, so backends still in "on" keep seeing valid checksums. Only "on" verifies (`c05d5ce1236^:src/backend/postmaster/datachecksum_state.c:18-27`, `:42-47`, `:56-59`).
- **State changes.**
  - `SetDataChecksumsOnInProgress()` runs inside a [critical section](../../../glossary.md#critical-section) with checkpoints held off. It writes a WAL record, updates shared memory and the control file, emits `PROCSIGNAL_BARRIER_CHECKSUM_INPROGRESS_ON`, and waits until every backend has absorbed the barrier (`c05d5ce1236^:src/backend/access/transam/xlog.c:4804-4833`).
  - `SetDataChecksumsOn()` accepts only inprogress-on as its start state. From any other state it logs a warning and disables checksums instead. Otherwise it does the same steps for "on", then forces a [checkpoint](../../../glossary.md#checkpoint) before waiting (`c05d5ce1236^:src/backend/access/transam/xlog.c:4857-4908`).
  - The barrier-absorb code accepted only nine from/to pairs (`c05d5ce1236^:src/backend/postmaster/datachecksum_state.c:238-277`).
- **WAL.** `f19c0eccae9` added a new [resource manager](../../../glossary.md#resource-manager), `XLOG2`, whose record `XLOG2_CHECKSUMS` carries the new state. It also added a checksum-state field to the checkpoint data and to the `XLOG_CHECKPOINT_REDO` record (`f19c0eccae9`, the `rmgrlist.h`, `pg_control.h` and `xlog_internal.h` hunks).
- **The worker.**
  - A launcher [background worker](../../../glossary.md#background-worker) started one worker per database.
  - Each worker read every block of every [fork](../../../glossary.md#fork) of every relation with storage and marked it dirty. It also wrote a [full-page image](../../../glossary.md#full-page-image) to WAL for each block, except in the forks of unlogged relations; their init forks were still logged (`c05d5ce1236^:src/backend/postmaster/datachecksum_state.c:707-776`).
  - Throttling reused the [vacuum cost delay](../../../glossary.md#vacuum-cost-delay) machinery (`c05d5ce1236^:src/backend/postmaster/datachecksum_state.c:788-792`).
  - Disabling needed no page writes, only the state change (`c05d5ce1236^:src/backend/postmaster/datachecksum_state.c:11-13`).
- **Not resumable.** A crash or restart during enabling left inprogress-on in the control file. Startup turned that back into off, and the user had to start again (`c05d5ce1236^:src/backend/postmaster/datachecksum_state.c:39-40`, `:95-99`, `:158-162`).
- **Monitoring.**
  - The `pg_stat_progress_data_checksums` view showed the phases enabling, disabling, waiting on temporary tables, waiting on barrier and done, plus database, relation and block counters (`c05d5ce1236^:src/backend/catalog/system_views.sql:1476-1493`).
  - The processes appeared as "datachecksums launcher" and "datachecksums worker" after `5ab239c9a90`.
- **Tests.** The `src/test/modules/test_checksums` module had eleven [TAP test](../../../glossary.md#tap-test) scripts, `001_basic.pl` through `011_standby_straddle.pl`, when the revert deleted it (`c05d5ce1236` stat). Its expensive suites ran only when [PG_TEST_EXTRA](../../../glossary.md#pg_test_extra) included `checksum` or `checksum_extended` (the `regress.sgml` hunk of `c05d5ce1236`).

Build and catalog footprint: `f19c0eccae9` bumped the [catalog version](../../../glossary.md#catalog-version) and `PG_CONTROL_VERSION` from 1901 to 1902. It also added entries to `pg_proc.dat`, `rmgrlist.h`, `lwlocklist.h`, `proctypelist.h`, `wait_event_names.txt` and `procsignal.h`. `aaf8b9989f7` later moved `PG_CONTROL_VERSION` to 1903, and the revert set it to 1905 (`git log -G'define PG_CONTROL_VERSION' -- src/include/catalog/pg_control.h`; [pg_control.h:25](../../../../raw/postgres-19/src/include/catalog/pg_control.h#L25)).

### How the Commit List Was Built

Every commit is in the history of `raw/postgres-19`. All are reachable from the pin except the 2018 and 2019 commits, whose ancestry the shallow clone cannot show. The tables use these columns:
- Dates are author dates.
- "Who" gives the committer, then the `Author:` trailer when it names someone else.
- "Named in revert" says whether `c05d5ce1236` lists the commit.
- "First beta" is the first `REL_19_BETA` tag that contains the commit.

[Context Reviewed](#context-reviewed) lists the searches.

### 2018 to 2019: The First Attempt

These six commits are in this clone's object store and are ancestors of its `REL_11_BETA1` tag, or of `REL_13_0` for `16a4e4aecd4`. The clone is shallow, so it cannot show that they are ancestors of the v19 pin (see [Open Questions](#open-questions)).

| Commit | Date | Who | Subject | What it did |
|---|---|---|---|---|
| `1fde38beaa0` | 2018-04-05 | Magnus Hagander; authors Magnus Hagander and Daniel Gustafsson | Allow on-line enabling and disabling of data checksums | Added a launcher/worker background process, `checksumhelper.c`, that recalculated every page's checksum before enabling. It also added a WAL record for the checksum state, the offline `pg_verify_checksums` tool, a standby TAP test and two isolation tests. Any failure reverted to off. |
| `3b0b4f31f73` | 2018-04-05 | Magnus Hagander | Attempt to fix win32 build of pg_verify_checksums | Used `pgwin32_is_junction()` on Windows, where `S_ISLNK` does not exist. |
| `bf75fe47e44` | 2018-04-07 | Andres Freund | Deactive flapping checksum isolation tests | Commented out the two checksum [isolation tests](../../../glossary.md#isolation-test) in `isolation_schedule`, because they "have been broken for days". |
| `a228cc13aea` | 2018-04-09 | Magnus Hagander | Revert "Allow on-line enabling and disabling of data checksums" | Reverted the backend parts and kept `pg_verify_checksums` because it "can be very valuable without the rest of the patch". |
| `f5543d47bcb` | 2018-04-09 | Magnus Hagander | catversion bump for online-checksums revert | Bumped the catalog version that the revert had missed. |
| `16a4e4aecd4` | 2019-12-19 | Robert Haas; Andres Freund and Robert Haas | Extend the ProcSignal mechanism to support barriers. | Added `EmitProcSignalBarrier()` and `WaitForProcSignalBarrier()` to coordinate global state changes, "such as turning checksums on while the system is running". The 2026 version used this mechanism. |

The offline path grew from the tool that survived the 2018 revert. These are context, not feature commits:

- `6dd263cfaa8` (2019-03-13) renamed `pg_verify_checksums` to `pg_checksums`.
- `ed308d78379` (2019-03-23) added options to enable and disable checksums in `pg_checksums`.
- `983a588e0b8` (2024-10-01) added `initdb --no-data-checksums`.
- `04bec894a04` (2024-10-16) made `initdb` enable checksums by default.

The pinned 19 tree has the results of the last two: checksums on by default ([initdb.c:167](../../../../raw/postgres-19/src/bin/initdb/initdb.c#L167)) and the `--no-data-checksums` option ([initdb.c:2544](../../../../raw/postgres-19/src/bin/initdb/initdb.c#L2544)).

### 2026: Preparation and the Main Commit

| Commit | Date | Who | Subject | What it did | Named in revert | First beta |
|---|---|---|---|---|---|---|
| `097ab69d17f` | 2026-03-31 | Daniel Gustafsson | Formalize WAL record for XLOG_CHECKPOINT_REDO | Wrapped the record's `wal_level` in an `xl_checkpoint_redo` struct so later changes can add fields. The message says the change was "inspired by the online checksums patch" but "has value on its own". It survives the revert ([xlog_internal.h#xl_checkpoint_redo](../../../../raw/postgres-19/src/include/access/xlog_internal.h#L307-L311), [xlog.c:7213-7222](../../../../raw/postgres-19/src/backend/access/transam/xlog.c#L7213-L7222)). | no | beta1 |
| `f19c0eccae9` | 2026-04-03 | Daniel Gustafsson; authors Daniel Gustafsson and Magnus Hagander, co-author Tomas Vondra | Online enabling and disabling of data checksums | Added everything described in [How the Reverted Feature Worked](#how-the-reverted-feature-worked): 80 files, 5,132 insertions, including the 1,612-line `datachecksum_state.c` and the `test_checksums` module. The message credits reviews of an earlier version and says the tests that run pgbench concurrently are gated behind `PG_TEST_EXTRA`. | yes | beta1 |

### 2026: Follow-Up Commits

Twenty-nine follow-ups landed on master before the branch point. The other 22 landed on `REL_19_STABLE` after it:
- 19 of the 22 carry a `Backpatch-through: 19` trailer.
- `e3a27cad462` carries `Backpatch-through: 18`.
- `2b6e7c0a7db` and `250942b0d82` carry none.

The 19 tree does not document the trailer. Many of these messages say the fix is a [back-patch](../../../glossary.md#back-patch); for example, `9eb77f9fc80` says "Backpatch to v19 where online checksums were introduced".

Nine follow-ups came after the 19beta3 stamp, so no beta carried them with the feature active. Several fixes answer [buildfarm](../../../glossary.md#buildfarm) failures.

**On master, before `REL_19_STABLE` branched (29):**

| Commit | Date | Who | Subject | What it changed | Named in revert | First beta |
|---|---|---|---|---|---|---|
| `0036232ba8f` | 2026-04-04 | Gustafsson | Make data checksum tests more resilient for slow machines | A test waited only for the "on" state. It now also waits in `pg_stat_activity` for the launcher to exit. An injection-point-only variable moved inside its `USE_` guard. Reported by the buildfarm. | no | beta1 |
| `d771b0a907e` | 2026-04-06 | Gustafsson | Handle checksumworker startup wait race | A worker that finished before the launcher began waiting counted as an error. The launcher now checks the result state, and the result update is locked. | yes | beta1 |
| `07009121c23` | 2026-04-06 | Gustafsson | Test stabilization for online checksums | Tests wait for launcher exit. Two injection-point tests moved to the `injection_points` extension. "on" is accepted where "inprogress-on" was expected. The server now stops before a background session that holds a temporary table. | yes | beta1 |
| `b3a37ffbc5b` | 2026-04-06 | Gustafsson; Aleksander Alekseev | Use PG_DATA_CHECKSUM_OFF instead of hardcoded value | Replaced literal `0` with `PG_DATA_CHECKSUM_OFF` in six files. The labels survive the revert. | yes | beta1 |
| `b364828f825` | 2026-04-08 | Gustafsson; Lakshmi N | doc: Fix data_checksums data type | Documented `data_checksums` as an enum with `on`, `off`, `inprogress-on` and `inprogress-off`, and pointed its link at the Data Checksums section. The link line survives. | yes | beta1 |
| `64b2b421248` | 2026-04-21 | Tom Lane | Fix not-quite-right Makefile for src/test/modules/test_checksums. | Set `TAP_TESTS = 1` and dropped hand-written check rules, so `make distclean` also removes `tmp_check`. | no | beta1 |
| `b120358c612` | 2026-04-30 | Gustafsson; Satyanarayana Narlapuram | Prevent pg_enable/disable_data_checksums() on standby | The functions lacked a recovery check, so a [hot standby](../../../glossary.md#hot-standby) could change its own state and break replay of later transitions. | yes | beta1 |
| `a0d8f4c1ae1` | 2026-04-30 | Gustafsson; Gustafsson and Tomas Vondra | Test improvements for online checksums | Fixed the reversed iteration logic for the two `PG_TEST_EXTRA` levels. The PITR test uses fast stop with longer timeouts. Logging improved and an unused helper was removed. Standby tests skip vacuum when pgbench initializes, and turn on `hot_standby_feedback`. | no | beta1 |
| `8fb8ded8895` | 2026-04-30 | Gustafsson | Handle data_checksum state changes during launcher_exit | The launcher's error exit reverts an unfinished enable to off, but the state machine lacked that transition. | yes | beta1 |
| `25b922ec582` | 2026-04-30 | Gustafsson; Tomas Vondra and Gustafsson | Fix invalid checksum state transition in checkpoints | Only the `_REDO` record now handles checksum state, instead of every checkpoint record. Barriers are emitted after control-file updates. Interrupts are held between `ProcSignalInit` and `InitLocalDataChecksumState`. The message's reference to `78e950cb8` does not resolve. | yes | beta1 |
| `381d19da153` | 2026-04-30 | Gustafsson | Typo and spelling fixups for online checksums | Comment and documentation wording from post-commit review. | yes | beta1 |
| `bf25e5571b3` | 2026-04-30 | Gustafsson | Improve handling of concurrent checksum requests | A second enable or disable call during processing now records its target in shared memory instead of starting another launcher. New cost values apply from the next relation. This fixed a wrong fall back to off. All shared-state access is under [LWLocks](../../../glossary.md#lwlock). | yes | beta1 |
| `1df361e3d82` | 2026-04-30 | Gustafsson | Improve database detection logic in datachecksumsworker | When a database failed processing, the check for whether it was dropped now also detects a partly dropped database. | yes | beta1 |
| `75152c5dc5d` | 2026-04-30 | Gustafsson | Fix data_checksum GUC show_hook | Added the show hook that `f19c0eccae9` omitted. | no | beta1 |
| `2018bd61679` | 2026-05-06 | Gustafsson; Satyanarayana Narlapuram | Skip WAL for unlogged main fork during online checksum enable | Full-page images are now written only when `RelationNeedsWAL()`. Init forks stay logged so a promoted standby can rebuild unlogged tables. Adds a [promotion](../../../glossary.md#promotion) test. | yes | beta1 |
| `9a39056c418` | 2026-05-06 | Gustafsson; Satyanarayana Narlapuram | Apply data-checksum worker throttling parameters | `cost_delay` and `cost_limit` had been silently ignored. The worker now calls `VacuumUpdateCosts()` at start and when the values change. | yes | beta1 |
| `486b9a9b9eb` | 2026-05-06 | Gustafsson | Fix regex searching for page verification failures in tests | Added the `/m` modifier so the log search anchors at every line. | no | beta1 |
| `d40aed55422` | 2026-05-26 | Michael Paquier; Baji Shaik | Adjust some error hints | Added a missing period to the online checksum hint, plus an unrelated extended-statistics hint. | no | beta1 |
| `5fee7cab1b8` | 2026-05-29 | Gustafsson | Fix checksum state transition during promotion | A standby promoted during inprogress-on reverts to off, and `StartupXLOG` now emits a barrier so running backends follow. Adds a test. | yes | beta1 |
| `cd857dec0e0` | 2026-05-29 | Gustafsson; Tomas Vondra | Improve comments in online checksums code | Spelling fixes and outdated comments rewritten. | yes | beta1 |
| `0ca1b301059` | 2026-05-29 | Gustafsson; Tomas Vondra | Use correct datatype for PID | The launcher stores a PID as `pid_t`, not `int`. | yes | beta1 |
| `5ab239c9a90` | 2026-05-29 | Gustafsson | Constistent naming for datacheckusms processes | Renamed "datachecksum worker/launcher" to "datachecksums worker/launcher" to match `data_checksums`. The subject's typos are in the original. | yes | beta1 |
| `4ae3e98c02c` | 2026-06-05 | Gustafsson | doc:  Mention online checksum enabling in pg_checksums docs | The `pg_checksums` page lists online processing as an alternative and links the Data Checksums section. Two of its lines survive. | yes | beta2 |
| `e5e1f6dc795` | 2026-06-05 | Gustafsson | Reword activity message to avoid truncation | Shortened the `pg_stat_activity` text shown while waiting for transactions, which a large XID could truncate. | yes | beta2 |
| `8d22f523245` | 2026-06-18 | Gustafsson | Fix comments on data checksum cost settings | The comments now say that a repeated enable call updates the cost values, and the values are read under a lock. | yes | beta2 |
| `0edbf72f768` | 2026-06-24 | Heikki Linnakangas | Misc cleanup in datachecksums_state.[ch] | Moved `DataChecksumsWorkerResult` into the `.c` file, made `StartDataChecksumsWorkerLauncher()` static, and corrected comments. | no | beta2 |
| `c008b7ea10a` | 2026-06-24 | Heikki Linnakangas | Avoid leaving DataChecksumState->worker_pid to an old value | Clears `worker_pid` in `launcher_exit()` and before starting a new worker. | no | beta2 |
| `c48e7b2c8bd` | 2026-06-24 | Heikki Linnakangas | Minor cleanup around checking datachecksum worker result | Renamed `success` to `worker_result`, and stopped reading it after the lock is released. | no | beta2 |
| `a4f02cab4b9` | 2026-06-24 | Heikki Linnakangas | Distinguish datacheckums worker invocations more reliably | Each launch gets a `worker_invocation` number, so an old worker cannot report success for a newer one. | no | beta2 |

**On `REL_19_STABLE`, after the branch point (22):**

| Commit | Date | Who | Subject | What it changed | Named in revert | First beta |
|---|---|---|---|---|---|---|
| `dff11f846c4` | 2026-07-09 | Fujii Masao | doc: Fix data checksum progress reporting documentation | Added `pg_stat_progress_data_checksums` to the [progress reporting](../../../glossary.md#progress-reporting) summary and documented its counters as `bigint`. | no | beta2 |
| `9d1d91a1433` | 2026-07-10 | Fujii Masao | Fix data checksum progress counter initialization | Counters start at -1 (shown as NULL) instead of 0. `blocks_done` resets for each fork. | no | beta2 |
| `c479ea58e77` | 2026-07-10 | Fujii Masao | Fix data checksum processing for temp relations and dropped databases | Waits only for temporary relations that have storage. Shared catalogs count as processed only after a worker succeeds. Before this, a dropped database could let enabling finish without processing them. | no | beta2 |
| `e3a27cad462` | 2026-07-16 | Gustafsson | doc: Fix link text for data checksums | Repaired link text that `67846550dc6` broke, in `storage.sgml`, `config.sgml` and `amcheck.sgml`; back-patched through 18. The revert names it, but all four added lines survive ([storage.sgml:800](../../../../raw/postgres-19/doc/src/sgml/storage.sgml#L800), [config.sgml:13266](../../../../raw/postgres-19/doc/src/sgml/config.sgml#L13266), [amcheck.sgml:424](../../../../raw/postgres-19/doc/src/sgml/amcheck.sgml#L424)). | yes | beta3 |
| `3aa54433b0c` | 2026-07-17 | Fujii Masao | Restrict pg_stat_io entries for data checksum processes | Taught `pgstat_tracks_io_object()` and `pgstat_tracks_io_op()` which I/O the launcher and workers can do, so [pg_stat_io](../../../glossary.md#pg_stat_io) drops rows that can never fill. | no | beta3 |
| `2b6e7c0a7db` | 2026-07-21 | Peter Eisentraut | pg_upgrade: Message wording fix | Reworded a [pg_upgrade](../../../glossary.md#pg_upgrade) refusal to "data checksums are being enabled in the old cluster". The check fires for either in-progress state, since it tests `data_checksum_version > PG_DATA_CHECKSUM_VERSION` (`c05d5ce1236^:src/bin/pg_upgrade/controldata.c:740-746`). | no | beta3 |
| `9eb77f9fc80` | 2026-07-28 | Gustafsson; Zsolt Parragi | Recheck checksum state before file_copy during CREATE DATABASE | Rechecks the state in `CreateDatabaseUsingFileCopy()` after an XID exists. Adds the injection point `createdb-before-catalog-insert`, which survives the revert. | no | beta3 |
| `e469e4784ea` | 2026-07-28 | Gustafsson; Zsolt Parragi | Handle invalid and dropped databases during checksum enable | Enabling errors out early when an invalid database exists. A worker that started and then failed gets the dropped-database check, which now locks the database. Adds tests, including `DROP DATABASE ... WITH (FORCE)`. | yes | beta3 |
| `b835cdba9aa` | 2026-07-30 | Gustafsson | Make sure to detach injection points for re-attaching | A test reused an [injection point](../../../glossary.md#injection-point) without detaching it, which failed on buildfarm member porpoise. | no | beta3 |
| `602f19c84ca` | 2026-08-01 | Gustafsson | doc: Fix glossary entry for data checksums workers | The docs glossary now calls them background workers, not auxiliary processes, in one combined entry. | yes | beta3 |
| `4afa9788b51` | 2026-08-01 | Gustafsson | Add a comment to distinguish backend types | Commented in `miscadmin.h` that the data checksums backend types are background workers. | no | beta3 |
| `343d98c3601` | 2026-08-03 | Gustafsson; Ayush Tiwari | Don't skip invalid databases when enabling data checksums | A present but invalid database now counts as existing, so enabling aborts until it is dropped. This undoes a side effect of `1df361e3d82`. | yes | beta3 |
| `01805b7d16b` | 2026-08-04 | Gustafsson; Mihail Nikalayeu | Do not reuse rd_smgr in fork loop when enabling data checksums | The fork loop calls `RelationGetSmgr()`, because a [relcache](../../../glossary.md#relcache) invalidation can reset `rd_smgr`. | yes | beta3 |
| `3a18526e8d6` | 2026-08-17 | Gustafsson; Fujii Masao | Make data checksums launcher cancel its worker at SIGINT | On SIGINT the launcher calls `TerminateBackgroundWorker()`, even while it waits for a worker to start or exit. Adds a test. | yes | beta4 |
| `abac86c7a27` | 2026-08-17 | Gustafsson; Fujii Masao | Reorder function prototypes to match definition order | Reordered prototypes before release to avoid back-patch conflicts, and added missing ones. | yes | beta4 |
| `aaf8b9989f7` | 2026-08-18 | Gustafsson | Record initial state of data checksums in controlfile | Added the control-file field `data_checksum_version_init`, so `pg_control_init()` reports the initdb-time state. The message calls this a regression dating back to offline `pg_checksums`. It survives in part. | yes | beta4 |
| `397f0fd06ed` | 2026-08-18 | Gustafsson; Ian Barwick and Gustafsson | Add data_page_checksum_version to pg_control_checkpoint | Added the column to `pg_control_checkpoint()` and documented the state-to-version mapping. `4a9a6c5a69c` removed the column; one docs line survives. | yes | beta4 |
| `0907112d388` | 2026-08-18 | Gustafsson; Zsolt Parragi | basebackup: do not verify checksums on pages from before enabling | A [base backup](../../../glossary.md#base-backup) verifies checksums only while the state is "on" and the last `XLOG2_CHECKSUMS` record predates the backup start. Replaying that record advances `minRecoveryPoint`. Adds straddling tests. | yes | beta4 |
| `c61c3ec40cb` | 2026-08-18 | Gustafsson | Minor test suite cleanup | Schema-qualified catalog queries and dropped a disable call before teardown. | no | beta4 |
| `1d28812160d` | 2026-08-18 | Gustafsson; Zsolt Parragi | Stabilize the FORCE drop test for online data checksums | The terminated session uses asynchronous commit, and the test checkpoints first, to avoid a timeout seen on buildfarm member turaco. The message names `51f55b13a4d`; on this branch the test came from `e469e4784ea`. | no | beta4 |
| `250942b0d82` | 2026-08-24 | Peter Eisentraut | Fix untranslatable message that was pasted together at run time | Split the page-verification message into two complete messages, with and without ", buffer will be zeroed". It survives ([bufpage.c#PageIsVerified](../../../../raw/postgres-19/src/backend/storage/page/bufpage.c#L149-L158)). | no | beta4 |
| `135b867a530` | 2026-09-01 | Gustafsson | Wait for checksum state transition in test | A disable-after-failure test now waits for the transition. Found on buildfarm member culicidae. | no | beta4 |

### Release-Note Commits

These commits wrote or edited the release-note item for the feature. The pinned `release-19.sgml` has no such item. Its only checksum item is the AVX2 checksum-speed entry ([release-19.sgml:2804-2814](../../../../raw/postgres-19/doc/src/sgml/release-19.sgml#L2804-L2814)).

| Commit | Date | Who | What it did to the item | First beta |
|---|---|---|---|---|
| `972c14fb913` | 2026-04-14 | Bruce Momjian | First draft: "Allow online enabling and disabling of data checksums", crediting four people. | beta1 |
| `75693dc5b72` | 2026-04-15 | Bruce Momjian | Removed "Lakshmi N" from the credits, as Gustafsson reported. | beta1 |
| `4ff61509881` | 2026-05-31 | Bruce Momjian | Linked `pg_checksums` in the item. | beta1 |
| `b45137f315b` | 2026-06-05 | Bruce Momjian | Linked "online enabling" and "data checksums". | beta2 |
| `eb77a521996` | 2026-06-07 | Bruce Momjian | Reworded the "previously" sentence. | beta2 |
| `0c57a40694d` | 2026-07-31 | Nathan Bossart | Listed the feature among the major features. | beta3 |
| `e7c1b57012b` | 2026-09-14 | Bruce Momjian | Added `397f0fd06ed` and a paragraph on the checksum state that `pg_controldata`, `pg_control_checkpoint()` and `pg_control_init()` report. | beta4 |

`c05d5ce1236` then removed the item and the major-feature line.

### Tree-Wide Commits That Edited Feature Code

These commits have wider purposes, but each changed code or data that belonged to the feature. The revert removed their feature edits along with the rest.

| Commit | Date | Who | Subject | Feature edit | First beta |
|---|---|---|---|---|---|
| `9b5acad3f40` | 2026-04-06 | Heikki Linnakangas | Convert all remaining subsystems to use the new shmem allocation API | Replaced `DataChecksumsShmemSize()`/`Init()` with shared-memory callbacks and a `subsystemlist.h` entry. | beta1 |
| `3e2a1496bae` | 2026-04-14 | Andrew Dunstan; Andres Freund and Jakub Wartak | Rework signal handler infrastructure to pass sender info as argument. | `SIG_IGN` became `PG_SIG_IGN` in the worker. | beta1 |
| `04f9ea372a2` | 2026-04-20 | Peter Eisentraut | Add missing Datum conversions | Wrapped a database OID in `ObjectIdGetDatum()`. | beta1 |
| `d3bba041543` | 2026-04-21 | Michael Paquier | Fix a set of typos and grammar issues across the tree | Comment fixes in `datachecksum_state.[ch]` and two TAP tests; removed two lines from `test_checksums.c`. | beta1 |
| `d14f69a32a1` | 2026-04-22 | Peter Geoghegan | Harmonize function parameter names for Postgres 19. | Renamed the `AbsorbDataChecksumsBarrier()` prototype parameter to `barrier`. | beta1 |
| `4f0cbc6fb5d` | 2026-04-23 | David Rowley; Chao Li | Fix new-to-v19 -Wshadow warnings | Renamed a shadowing local `launcher_running` to `running`. | beta1 |
| `d0ed9ad8b07` | 2026-05-05 | Peter Eisentraut | doc: Clean up title case use | Title-cased two headings in the feature's `wal.sgml` text. | beta1 |
| `c7cb8e5b73c` | 2026-05-13 | Tom Lane | Do pre-release housekeeping on catalog data. | Renumbered the two functions' [OIDs](../../../glossary.md#oid) from 9257/9258 to 6506/6507. | beta1 |
| `020794ee42a` | 2026-05-13 | Tom Lane | Pre-beta mechanical code beautification, step 1: run pgindent. | Re-sorted `DataChecksumsWorkerOperation` in `typedefs.list`. | beta1 |
| `719fe0779d8` | 2026-05-13 | Tom Lane | Pre-beta mechanical code beautification, step 3: run reformat-dat-files. | Reformatted the two functions' `pg_proc.dat` rows. | beta1 |
| `81aa0a2fa7c` | 2026-08-17 | Peter Eisentraut | Replace printf format %i by %d | Two worker messages changed from `%i` to `%d`. | beta4 |
| `e8601cb3d48` | 2026-09-11 | Peter Eisentraut | Remove unused global variables | Removed a `LocalMinRecoveryPointTLI` assignment, among others, from the feature's `xlog2_redo()`. | beta4 |

### Translation Imports

Each of these `Translation updates` commits by Peter Eisentraut added, changed or retired message strings that the feature defined in the backend `.po` files. Examples are "datachecksums launcher" and "unable to enable data checksums in cluster".

| Commit | Date | Feature strings in the diff | First beta |
|---|---|---|---|
| `ef6a95c7c64` | 2026-06-01 | Added strings such as "enabling data checksums was interrupted" | beta1 |
| `8055e3375aa` | 2026-07-13 | Followed the "datachecksum" to "datachecksums" rename | beta2 |
| `b330f4978df` | 2026-08-10 | Followed the pg_upgrade rewording and added the invalid-database message | beta3 |
| `b368bdd2301` | 2026-09-21 | Came after the revert, and still added feature strings to some files | beta4 |

### The Revert and Its Cleanups

| Commit | Date | Who | Subject | What it did | First beta |
|---|---|---|---|---|---|
| `c05d5ce1236` | 2026-09-16 | Daniel Gustafsson | Revert online data checksum transitions | Removed 6,673 lines in 82 files, including `datachecksum_state.[ch]` and `test_checksums`, and named 30 commits. It kept four things: the fix for `pg_control_init()` reporting the initial state, with its test moved to `pg_checksums`; the "buffer will be zeroed" note; a rewritten Data Checksums docs section; and the state enum with its `PG_DATA_CHECKSUM_OFF` label. | beta4 |
| `4a9a6c5a69c` | 2026-09-16 | Daniel Gustafsson | Fix online checksums revert leftovers | Dropped the checksum column the revert had left in `pg_control_checkpoint()`, and restored setting `data_checksum_version_init` in `InitControlFile()`. Bumped [XLOG_PAGE_MAGIC](../../../glossary.md#xlog_page_magic) from 0xD121 to 0xD122 and the catalog version. Reported by Fujii Masao, Manuel Reyes Bravo and Heikki Linnakangas. | beta4 |
| `6b0760a10a3` | 2026-09-17 | Daniel Gustafsson | Further post-revert cleanup after online checksums | Restored the "NULL if data checksums are disabled" wording for the checksum-failure columns, and removed the leftover checksum field from `xl_checkpoint_redo`. Also removed the offline checksum helpers from `Cluster.pm`, which `f19c0eccae9` had added. Left `XLOG_PAGE_MAGIC` alone, because no version had shipped since the last bump. | beta4 |

### What the Pinned Tree Still Contains

Each item cites the pin. `git blame` at the pin attributes each kept line to the commit named.

| Kept item | Where | From |
|---|---|---|
| `ChecksumStateType` with only `PG_DATA_CHECKSUM_OFF = 0` and `PG_DATA_CHECKSUM_VERSION = 1` | [checksum.h#ChecksumStateType](../../../../raw/postgres-19/src/include/storage/checksum.h#L18-L27) | `f19c0eccae9`, trimmed by `c05d5ce1236` |
| `PG_DATA_CHECKSUM_OFF` labels in bootstrap, `pg_checksums` and `pg_upgrade`, and `pg_checksums` tests that compare with `PG_DATA_CHECKSUM_VERSION` instead of `0` | [bootstrap.c:244](../../../../raw/postgres-19/src/backend/bootstrap/bootstrap.c#L244), [pg_checksums.c:584-598](../../../../raw/postgres-19/src/bin/pg_checksums/pg_checksums.c#L584-L598), [pg_checksums.c:645-648](../../../../raw/postgres-19/src/bin/pg_checksums/pg_checksums.c#L645-L648), [controldata.c:743-750](../../../../raw/postgres-19/src/bin/pg_upgrade/controldata.c#L743-L750) | `b3a37ffbc5b`; the `PG_DATA_CHECKSUM_VERSION` tests on lines 588 and 596 are from `f19c0eccae9` |
| `PIV_ZERO_BUFFERS_ON_ERROR`, which a zero-on-error read sets, and the ", buffer will be zeroed" message | [bufpage.h:499-503](../../../../raw/postgres-19/src/include/storage/bufpage.h#L499-L503), [bufmgr.c:8619-8624](../../../../raw/postgres-19/src/backend/storage/buffer/bufmgr.c#L8619-L8624), [bufpage.c#PageIsVerified](../../../../raw/postgres-19/src/backend/storage/page/bufpage.c#L149-L158) | `f19c0eccae9`, `250942b0d82` |
| `data_checksum_version_init` next to `data_checksum_version` in the control file, set at initdb and reported by `pg_control_init()` | [pg_control.h:224-231](../../../../raw/postgres-19/src/include/catalog/pg_control.h#L224-L231), [xlog.c#InitControlFile](../../../../raw/postgres-19/src/backend/access/transam/xlog.c#L4285-L4296), [pg_controldata.c:257](../../../../raw/postgres-19/src/backend/utils/misc/pg_controldata.c#L257) | `aaf8b9989f7`, `4a9a6c5a69c` |
| A test that inits without checksums, enables them offline, and checks that `pg_control_init()` still reports 0 | [002_actions.pl:94](../../../../raw/postgres-19/src/bin/pg_checksums/t/002_actions.pl#L94), [002_actions.pl:128](../../../../raw/postgres-19/src/bin/pg_checksums/t/002_actions.pl#L128), [002_actions.pl:219-222](../../../../raw/postgres-19/src/bin/pg_checksums/t/002_actions.pl#L219-L222) | `c05d5ce1236` |
| `pg_control` format version 1905 and WAL page magic 0xD122 | [pg_control.h:25](../../../../raw/postgres-19/src/include/catalog/pg_control.h#L25), [xlog_internal.h:35](../../../../raw/postgres-19/src/include/access/xlog_internal.h#L35) | `c05d5ce1236`, `4a9a6c5a69c` |
| The one-field `xl_checkpoint_redo` record | [xlog_internal.h#xl_checkpoint_redo](../../../../raw/postgres-19/src/include/access/xlog_internal.h#L307-L311) | `097ab69d17f`, `6b0760a10a3` |
| Data Checksums docs with an offline-only subsection | [wal.sgml#checksums](../../../../raw/postgres-19/doc/src/sgml/wal.sgml#L232-L283) | Blame: 15 lines from `c05d5ce1236`, 4 from `f19c0eccae9`, 1 from `397f0fd06ed`, and the rest older than this clone's history |
| Checksum-failure counts are NULL again when checksums are off. `f19c0eccae9` had removed these checks. | [pgstatfuncs.c#pg_stat_get_db_checksum_failures](../../../../raw/postgres-19/src/backend/utils/adt/pgstatfuncs.c#L1178-L1194), [pgstatfuncs.c#pg_stat_get_db_checksum_last_failure](../../../../raw/postgres-19/src/backend/utils/adt/pgstatfuncs.c#L1196-L1215), [monitoring.sgml:3900-3918](../../../../raw/postgres-19/doc/src/sgml/monitoring.sgml#L3900-L3918) | `c05d5ce1236`, `6b0760a10a3` |
| The injection point `createdb-before-catalog-insert`, which nothing else in `src/`, `doc/` or `contrib/` names | [dbcommands.c:68](../../../../raw/postgres-19/src/backend/commands/dbcommands.c#L68), [dbcommands.c:1507](../../../../raw/postgres-19/src/backend/commands/dbcommands.c#L1507) | `9eb77f9fc80` |
| Translations of removed messages: obsolete `#~` entries, and live entries in `ja.po` that still point at the deleted `datachecksum_state.c` | [de.po:35408](../../../../raw/postgres-19/src/backend/po/de.po#L35408), [ja.po:717-721](../../../../raw/postgres-19/src/backend/po/ja.po#L717-L721), [ja.po:23941](../../../../raw/postgres-19/src/backend/po/ja.po#L23941) | translation imports |

What is gone at the pin:

- The only barrier types are `SMGRRELEASE` and `UPDATE_XLOG_LOGICAL_INFO` ([procsignal.h#ProcSignalBarrierType](../../../../raw/postgres-19/src/include/storage/procsignal.h#L48-L53)).
- The resource manager list ends with `LogicalMessage`, with no `XLOG2` ([rmgrlist.h:28-49](../../../../raw/postgres-19/src/include/access/rmgrlist.h#L28-L49)).
- `DataChecksumsEnabled()` is again a plain `data_checksum_version > 0` test. It feeds hint-bit WAL logging and the `data_checksums` setting ([xlog.c#DataChecksumsEnabled](../../../../raw/postgres-19/src/backend/access/transam/xlog.c#L4666-L4674), [xlog.h:135](../../../../raw/postgres-19/src/include/access/xlog.h#L135), [xlog.c:4631-4633](../../../../raw/postgres-19/src/backend/access/transam/xlog.c#L4631-L4633)).
- Outside the backend `.po` files, no file in `src/`, `doc/` or `contrib/` names `pg_enable_data_checksums`, `datachecksum`, `XLOG2_CHECKSUMS` or `pg_stat_progress_data_checksums`.
- No test exercises online changes. The only checksum-state test left at the pin is the `pg_checksums` TAP test above.

### Commits Checked and Excluded

These commits matched a search but are not part of the feature.

| Commit | Date | Subject | Why excluded |
|---|---|---|---|
| `9af672bcb24` | 2025-09-08 | meson: build checksums with extra optimization flags. | Compiler flags for checksum computation |
| `a7c30422004` | 2025-10-20 | pg_checksums: Use new routine to retrieve data of PG_VERSION | Offline tool only |
| `5db6a344abc` | 2025-12-05 | Rename column slotsync_skip_at to slotsync_last_skip. | Mentions `checksum_last_failure` only as a naming example |
| `b9ee5f2dcba` | 2026-01-06 | doc: Fix outdated doc in pg_rewind. | Default-on checksums from 18 |
| `45f658dacb9` | 2026-01-12 | freespace: Don't modify page without any lock | Page-locking work for asynchronous writes |
| `fcb9c977aa5` | 2026-01-15 | bufmgr: Implement buffer content locks independently of lwlocks | Same work |
| `775fc014156` | 2026-02-13 | Improve error message for checksum failures in pgstat_database.c | Failure statistics |
| `82467f627bd` | 2026-03-10 | Require share-exclusive lock to set hint bits and to flush | [Hint bits](../../../glossary.md#hint-bits) locking |
| `41d3d64e87a` | 2026-03-27 | bufmgr: Don't copy pages while writing out | Same work; touches `DataChecksumsEnabled()` callers |
| `bc30c704add` | 2026-04-02 | Harden astreamer tar parsing logic against archives it can't handle. | Tar header checksums |
| `5e13b0f2403` | 2026-04-04 | Use AVX2 for calculating page checksums where available | Checksum speed |
| `8c3e22a8f8b` | 2026-04-07 | Use .h for the file containing the page checksum code fragment | Checksum code layout |
| `c06d1a4ba6b` | 2026-05-03 | Mark modified the FSM buffer as dirty during recovery | Free space map dirtying |
| `06fccab4c61` | 2026-05-12 | doc PG 19 relnotes:  remove "Optionally" for CPU optimizations | Edits only the AVX2 item |
| `b01c31eef9c` | 2026-07-15 | Fix VM clear WAL logging by registering VM blocks | Visibility map WAL |
| `db0f6dd80a0` | 2026-08-19 | Report single-page checksum failures in pg_stat_database | Base-backup failure statistics |
| `d0518cb3e40` | 2026-09-08 | Revert "Mark modified the FSM buffer as dirty during recovery" | Revert of `c06d1a4ba6b` |
| `ac58465e061` | 2026-03-10 | Introduce the REPACK command | Owns a line next to a revert hunk |
| `4881981f920` | 2026-03-19 | Add infrastructure for pg_get_*_ddl functions | Same |
| `0841b219bf0` | 2026-03-29 | Sort InternalBGWorkers list alphabetically | Same, in `bgworker.c` |
| `df6949ccf7a` | 2026-04-05 | Add tid_block() and tid_offset() accessor functions | Rewrote the shared `catversion.h` line |
| `1a5b19e447a` | 2026-06-05 | Fix pg_subscription column privileges for subwalrcvtimeout | Same |
| `3fcb7167198` | 2026-08-27 | Report next_multi_offset as bigint in pg_control_checkpoint(). | Rewrote the `pg_control_checkpoint()` row that `397f0fd06ed` had extended |
| `2b9e1aff4d3` | 2026-09-07 | Revert SQL Property Graph Queries (SQL/PGQ) | Rewrote shared `pg_proc.dat` lines |
| `db169985c10` | 2026-09-12 | Revert pg_get_role_ddl(), pg_get_tablespace_ddl(), and pg_get_database_ddl(). | Same |
| `a9d2f728240` | 2026-09-15 | Revert UPDATE/DELETE FOR PORTION OF | Rewrote the shared `catversion.h` line |
| `0ef891e5417` | 2025-08-07 | doc: Formatting improvements | The shallow clone's boundary commit, which git shows as adding every file |

## Context Reviewed

- Version, pin and history depth:
  - `raw/postgres-19` HEAD is `dae3463fa969931458f1488f9b7af11e3741cd54` (`REL_19_BETA4-17-gdae3463fa96`), with no local changes.
  - `git rev-parse --is-shallow-repository` prints `true`. `.git/shallow` holds `0ef891e5417` (2025-08-07), whose parent `466c5435fd4` is missing.
  - `git rev-list --count HEAD` is 3,292.
  - Tags `REL_11_BETA1`, `REL_11_0`, `REL_13_0`, `REL_18_0` and `REL_19_BETA1` through `REL_19_BETA4` are present.
- Searches, all in `raw/postgres-19`:
  1. `git log -i --grep=checksum HEAD`: 68 commits, plus the same search on `REL_18_0` since 2018-01-01, which returned 129.
  2. `git log HEAD --` on the feature's own paths: `datachecksum_state.[ch]`, `src/test/modules/test_checksums`, and `doc/src/sgml/images/datachecksums.{gv,svg}`.
  3. `git log -E -G'<symbols>' HEAD` over 42 feature-symbol patterns, such as `DataChecksumsNeedVerify`, `XLOG2`, `PROCSIGNAL_BARRIER_CHECKSUM` and `pg_enable_data_checksums`: 51 commits.
  4. `git log -G'hecksum' f19c0eccae9^..HEAD -- doc/`.
  5. `git blame` at `c05d5ce1236^` of all 6,673 lines the revert removed: 69 commits.
  6. For each of the 277 commits between `f19c0eccae9` and the revert that touched a feature file, a blame of the lines it removed, to find edits to lines that feature commits wrote.
  7. A `git blame` of the pin over the 247 non-`.po` files that the candidate commits touched, to find surviving lines.
- Commit messages and diffs read:
  - Full messages for the 6 commits from 2018 and 2019, the preparation and main commits, the 51 follow-ups, and the revert with its 2 cleanups.
  - The release-note, tree-wide and translation commits were classified from their subjects and the feature hunks of their diffs.
  - The 27 excluded commits were classified from their subjects, the matching lines of their messages or diffs, and the files they touched.
  - Diffs read: `f19c0eccae9` headers; `c05d5ce1236` stat and selected hunks; `4a9a6c5a69c` and `6b0760a10a3` in full; the release-note item hunks; and the translation `msgid` lines.
- Pre-revert source read at `c05d5ce1236^`: `src/backend/postmaster/datachecksum_state.c` (lines 1-285, 505-600 and 700-800), `src/backend/access/transam/xlog.c` (lines 4800-4935), and the `pg_proc.dat`, `guc_parameters.dat` and `system_views.sql` entries.
- Pinned source read: `checksum.h`, `bufpage.h`, `bufpage.c`, `bufmgr.c`, `pg_control.h`, `xlog.c`, `xlog.h`, `xlog_internal.h`, `procsignal.h`, `rmgrlist.h`, `guc_parameters.dat`, `pg_controldata.c` (both copies), `pgstatfuncs.c`, `dbcommands.c`, `pg_checksums.c`, `pg_checksums/t/002_actions.pl`, `pg_upgrade/controldata.c`, `initdb.c`, `wal.sgml`, `config.sgml`, `monitoring.sgml`, `func-info.sgml`, `storage.sgml`, `amcheck.sgml`, `release-19.sgml`, `de.po` and `ja.po`.
- Absence checks: `grep -rn` under `src/`, `doc/` and `contrib/` found `pg_enable_data_checksums` and `datachecksum` only in backend `.po` files. It found no match for `pg_disable_data_checksums`, `PROCSIGNAL_BARRIER_CHECKSUM`, `RM_XLOG2_ID`, `XLOG2_CHECKSUMS`, `pg_stat_progress_data_checksums`, `DataChecksumsNeedVerify` or `inprogress-on`. `test_checksums` appears only as an unrelated Perl function name in `pg_verifybackup/t/002_algorithm.pl`.
- Glossary entries reviewed: Data checksums, Page, WAL, Full-page image, Checkpoint, Background worker, Hot standby, Crash recovery, Fork, Relcache, Injection point, TAP test, Isolation test, Progress reporting, pg_stat_io, pg_upgrade, LWLock, OID, Critical section, Vacuum cost delay and Hint bits. Ten entries were added (see the log).
- Common concepts: PostgreSQL 19 has no `common-concepts/` pages, so none is linked.
- No server was started and nothing was measured.

## Evidence Map

| Claim | Evidence |
|---|---|
| Online transitions are absent at the pin | [guc_parameters.dat#data_checksums](../../../../raw/postgres-19/src/backend/utils/misc/guc_parameters.dat#L581-L586), [procsignal.h#ProcSignalBarrierType](../../../../raw/postgres-19/src/include/storage/procsignal.h#L48-L53), [rmgrlist.h:28-49](../../../../raw/postgres-19/src/include/access/rmgrlist.h#L28-L49), [wal.sgml:246-253](../../../../raw/postgres-19/doc/src/sgml/wal.sgml#L246-L253), and the absence checks |
| Committed 2026-04-03; reverted 2026-09-16, with reasons | `f19c0eccae9` and `c05d5ce1236` messages |
| Shipped in beta1 to beta3, not in beta4 | `git merge-base --is-ancestor` of `f19c0eccae9` and `c05d5ce1236` against the four `REL_19_BETA` tags |
| First attempt 2018, reverted before 11beta1 | `1fde38beaa0`, `a228cc13aea` and `f5543d47bcb` messages; ancestry to `REL_11_BETA1` |
| Barriers were built with online checksums in mind | `16a4e4aecd4` message |
| Four states, their meanings and transitions | `f19c0eccae9` `checksum.h` hunk; `c05d5ce1236^:src/backend/postmaster/datachecksum_state.c:18-59`, `:238-277` |
| WAL record, control-file update and barrier order | `c05d5ce1236^:src/backend/access/transam/xlog.c:4804-4908` |
| Worker page loop, full-page images, unlogged exception, throttling | `c05d5ce1236^:src/backend/postmaster/datachecksum_state.c:707-792` |
| SQL functions, defaults, superuser and recovery checks | `c05d5ce1236^:src/include/catalog/pg_proc.dat:12363-12372`; `c05d5ce1236^:src/backend/postmaster/datachecksum_state.c:551-591` |
| Progress view phases | `c05d5ce1236^:src/backend/catalog/system_views.sql:1476-1493` |
| 29 master and 22 `REL_19_STABLE` follow-ups; beta containment | Merge base `9cfd19bc10a`; ancestry checks per commit |
| Revert names 30 commits and also removes most code of the 22 it does not name | `c05d5ce1236` message; blame of the revert's removed lines; blame of the pin for surviving lines |
| Kept items at the pin | The citations in [What the Pinned Tree Still Contains](#what-the-pinned-tree-still-contains), plus the pinned blame |
| `PG_CONTROL_VERSION` 1901 to 1902 to 1903 to 1905 | `git log -G'define PG_CONTROL_VERSION'`; [pg_control.h:25](../../../../raw/postgres-19/src/include/catalog/pg_control.h#L25) |
| `XLOG_PAGE_MAGIC` 0xD121 to 0xD122 | `4a9a6c5a69c` diff; [xlog_internal.h:35](../../../../raw/postgres-19/src/include/access/xlog_internal.h#L35) |
| Checksum-failure counts NULL again when off | `f19c0eccae9` `pgstatfuncs.c` hunk; [pgstatfuncs.c#pg_stat_get_db_checksum_failures](../../../../raw/postgres-19/src/backend/utils/adt/pgstatfuncs.c#L1178-L1194); `6b0760a10a3` |
| The `e3a27cad462` fixes survive despite being named | [storage.sgml:800](../../../../raw/postgres-19/doc/src/sgml/storage.sgml#L800), [config.sgml:13266](../../../../raw/postgres-19/doc/src/sgml/config.sgml#L13266), [amcheck.sgml:424](../../../../raw/postgres-19/doc/src/sgml/amcheck.sgml#L424) |
| Leftover injection point | [dbcommands.c:1507](../../../../raw/postgres-19/src/backend/commands/dbcommands.c#L1507); `9eb77f9fc80`; the `grep -rn` absence check |
| Offline path at the pin | [pg_checksums.c:1-5](../../../../raw/postgres-19/src/bin/pg_checksums/pg_checksums.c#L1-L5), [pg_checksums.c:584-598](../../../../raw/postgres-19/src/bin/pg_checksums/pg_checksums.c#L584-L598), [initdb.c:167](../../../../raw/postgres-19/src/bin/initdb/initdb.c#L167) |

## Open Questions

- **Shallow clone.** `raw/postgres-19` stops at `0ef891e5417` (2025-08-07), and that commit's parent `466c5435fd4` is missing. Two gaps follow:
  - This clone cannot show that the six 2018 and 2019 commits are ancestors of the pin. They are reachable only through older tags (`REL_11_BETA1`, `REL_13_0` and `REL_18_0`).
  - Master commits between the `REL_18_STABLE` branch point and 2025-08-07 were never searched, so a feature-related commit there would be missing from this page.

  The asker chose not to fetch. `git -C raw/postgres-19 fetch --unshallow origin REL_19_STABLE`, followed by the searches in [Context Reviewed](#context-reviewed), would close both gaps.
- **`78e950cb8`.** The message of `25b922ec582` says this commit "added checksum state handling to all XLOG_CHECKPOINT records". The hash does not resolve in this clone. A blame of the lines `25b922ec582` changed attributes the checkpoint handling to `f19c0eccae9`, so the hash may be one that never reached the public tree. This clone cannot settle it.
- **`51f55b13a4d`.** The message of `1d28812160d` names this hash for the `DROP DATABASE ... WITH (FORCE)` test, but it is not in this clone. On `REL_19_STABLE` that test arrived with `e469e4784ea`. The local `origin/master` ref stops at 2026-07-27, so a master counterpart from after that date cannot be checked here.
- **`PG_CONTROL_VERSION` 1904.** The revert moved the version from 1903 to 1905. No commit in this clone's history sets 1904, and the revert message does not explain the skip.
- **Revert message against effect.** The message says it reverts the 30 named commits "in full, or in part". All four lines that `e3a27cad462` added are still at the pin, so that commit was not reverted at all. The message also does not mention the surviving `createdb-before-catalog-insert` injection point from `9eb77f9fc80`, which no test uses at the pin.
- **Stale comment at the pin.** The comment above `data_checksum_version_init` still says the checksum state "can be changed during runtime" ([pg_control.h:224-228](../../../../raw/postgres-19/src/include/catalog/pg_control.h#L224-L228)). At the pin, only `InitControlFile()` and the offline `pg_checksums` write `data_checksum_version` ([xlog.c#InitControlFile](../../../../raw/postgres-19/src/backend/access/transam/xlog.c#L4285-L4296), [pg_checksums.c:645-648](../../../../raw/postgres-19/src/bin/pg_checksums/pg_checksums.c#L645-L648)). `aaf8b9989f7` wrote the comment while online changes existed.
- **Leftover translations.** `ja.po` still carries live entries for removed feature messages ([ja.po:717-721](../../../../raw/postgres-19/src/backend/po/ja.po#L717-L721)). Whether a later translation import will retire them cannot be seen at this pin.
- **Out of scope.** This page lists only commits reachable from the 19 pin. It does not assess master (20devel). The master counterparts of back-patched follow-ups, such as `32e4508db27` for `3aa54433b0c`, are in the local `origin/master` history but are not v19 evidence.
- **Glossary scope.** The ten entries added for this page were checked on PostgreSQL 19 only, as the asker chose.

## Source References

- [checksum.h#ChecksumStateType](../../../../raw/postgres-19/src/include/storage/checksum.h#L18-L27)
- [bufpage.h:499-503](../../../../raw/postgres-19/src/include/storage/bufpage.h#L499-L503)
- [bufpage.c#PageIsVerified](../../../../raw/postgres-19/src/backend/storage/page/bufpage.c#L149-L158)
- [bufmgr.c:8619-8624](../../../../raw/postgres-19/src/backend/storage/buffer/bufmgr.c#L8619-L8624)
- [pg_control.h:25](../../../../raw/postgres-19/src/include/catalog/pg_control.h#L25)
- [pg_control.h:224-231](../../../../raw/postgres-19/src/include/catalog/pg_control.h#L224-L231)
- [pg_control.h:224-228](../../../../raw/postgres-19/src/include/catalog/pg_control.h#L224-L228)
- [xlog.c#InitControlFile](../../../../raw/postgres-19/src/backend/access/transam/xlog.c#L4285-L4296)
- [xlog.c#DataChecksumsEnabled](../../../../raw/postgres-19/src/backend/access/transam/xlog.c#L4666-L4674)
- [xlog.c:4631-4633](../../../../raw/postgres-19/src/backend/access/transam/xlog.c#L4631-L4633)
- [xlog.c:7213-7222](../../../../raw/postgres-19/src/backend/access/transam/xlog.c#L7213-L7222)
- [xlog.h:135](../../../../raw/postgres-19/src/include/access/xlog.h#L135)
- [xlog_internal.h:35](../../../../raw/postgres-19/src/include/access/xlog_internal.h#L35)
- [xlog_internal.h#xl_checkpoint_redo](../../../../raw/postgres-19/src/include/access/xlog_internal.h#L307-L311)
- [procsignal.h#ProcSignalBarrierType](../../../../raw/postgres-19/src/include/storage/procsignal.h#L48-L53)
- [rmgrlist.h:28-49](../../../../raw/postgres-19/src/include/access/rmgrlist.h#L28-L49)
- [guc_parameters.dat#data_checksums](../../../../raw/postgres-19/src/backend/utils/misc/guc_parameters.dat#L581-L586)
- [pg_controldata.c:257](../../../../raw/postgres-19/src/backend/utils/misc/pg_controldata.c#L257)
- [pgstatfuncs.c#pg_stat_get_db_checksum_failures](../../../../raw/postgres-19/src/backend/utils/adt/pgstatfuncs.c#L1178-L1194)
- [pgstatfuncs.c#pg_stat_get_db_checksum_last_failure](../../../../raw/postgres-19/src/backend/utils/adt/pgstatfuncs.c#L1196-L1215)
- [dbcommands.c:68](../../../../raw/postgres-19/src/backend/commands/dbcommands.c#L68)
- [dbcommands.c:1507](../../../../raw/postgres-19/src/backend/commands/dbcommands.c#L1507)
- [bootstrap.c:244](../../../../raw/postgres-19/src/backend/bootstrap/bootstrap.c#L244)
- [pg_checksums.c:1-5](../../../../raw/postgres-19/src/bin/pg_checksums/pg_checksums.c#L1-L5)
- [pg_checksums.c:584-598](../../../../raw/postgres-19/src/bin/pg_checksums/pg_checksums.c#L584-L598)
- [pg_checksums.c:645-648](../../../../raw/postgres-19/src/bin/pg_checksums/pg_checksums.c#L645-L648)
- [002_actions.pl:94](../../../../raw/postgres-19/src/bin/pg_checksums/t/002_actions.pl#L94)
- [002_actions.pl:128](../../../../raw/postgres-19/src/bin/pg_checksums/t/002_actions.pl#L128)
- [002_actions.pl:219-222](../../../../raw/postgres-19/src/bin/pg_checksums/t/002_actions.pl#L219-L222)
- [controldata.c:743-750](../../../../raw/postgres-19/src/bin/pg_upgrade/controldata.c#L743-L750)
- [initdb.c:167](../../../../raw/postgres-19/src/bin/initdb/initdb.c#L167)
- [initdb.c:2544](../../../../raw/postgres-19/src/bin/initdb/initdb.c#L2544)
- [wal.sgml#checksums](../../../../raw/postgres-19/doc/src/sgml/wal.sgml#L232-L283)
- [wal.sgml:246-253](../../../../raw/postgres-19/doc/src/sgml/wal.sgml#L246-L253)
- [wal.sgml#checksums-offline-enable-disable](../../../../raw/postgres-19/doc/src/sgml/wal.sgml#L271-L282)
- [monitoring.sgml:3900-3918](../../../../raw/postgres-19/doc/src/sgml/monitoring.sgml#L3900-L3918)
- [storage.sgml:800](../../../../raw/postgres-19/doc/src/sgml/storage.sgml#L800)
- [config.sgml:13266](../../../../raw/postgres-19/doc/src/sgml/config.sgml#L13266)
- [amcheck.sgml:424](../../../../raw/postgres-19/doc/src/sgml/amcheck.sgml#L424)
- [release-19.sgml:2804-2814](../../../../raw/postgres-19/doc/src/sgml/release-19.sgml#L2804-L2814)
- [de.po:35408](../../../../raw/postgres-19/src/backend/po/de.po#L35408)
- [ja.po:717-721](../../../../raw/postgres-19/src/backend/po/ja.po#L717-L721)
- [ja.po:23941](../../../../raw/postgres-19/src/backend/po/ja.po#L23941)

## Navigation

- [v19/index](../../index.md)
- [PostgreSQL 19 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [Wiki Glossary (unverified)](../../../glossary.md)
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
