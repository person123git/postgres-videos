# pgvideo

pgvideo makes one narrated MP4 from one Markdown page of
[person123git/postgres-llm-wiki](https://github.com/person123git/postgres-llm-wiki),
on request. An **LLM harness orchestrates every video**: it plans what to teach,
writes the narration and storyboard, cross-checks them against the wiki glossary
and the pinned PostgreSQL source, and has the result reviewed in a separate pass.
pgvideo supplies the evidence and the media tools. It snapshots the page, the
glossary, and the PostgreSQL files the page cites; parses the page and extracts
exact facts; validates every artifact the harness writes and decides the content
gate; and narrates with a local Kokoro model, times captions and scenes from the
measured audio, renders slides, and encodes, validates, and delivers the MP4.
A later request with exactly the same inputs reuses the validated video.

The Python runtime, packages, models, tools, caches, and outputs all stay inside
this directory, and every pgvideo command runs in a macOS sandbox. The harness
follows [AGENTS.md](AGENTS.md); [docs/harness.md](docs/harness.md) is its
command, evidence, and recovery reference. `plan.md` records the design and its
decisions, and [docs/llm-video-generation-proposal.md](docs/llm-video-generation-proposal.md)
the rationale for the harness workflow.

## Prerequisites

- **macOS on Apple silicon (arm64)** for the local runtime, Kokoro, FFmpeg, and
  Chromium. `scripts/setup` provisions all of them inside the project.
- **An LLM harness** that can read repository instructions, run local commands,
  write JSON files, and run a separate review pass in a fresh context (a separate
  session, subagent, or model invocation without the writer's conversation,
  reasoning, notes, or self-assessment). The harness brings its own model
  connection and credentials; pgvideo never calls a model and never sees those
  credentials. A harness that cannot keep the review separate must
  say so before production, as `AGENTS.md` requires.

## Quick start

```sh
/path/to/postgres-videos/scripts/setup
```

`setup` provisions everything the project needs and ends with an offline sample.
Then open the repository in your harness and ask for a video:

> Read this project's AGENTS.md and generate a summary video from
> wiki/v18/questions/observability/track-activity-query-size.md for a PostgreSQL
> administrator. Aim for three minutes, cross-check the glossary and pinned
> evidence, and continue through validation and delivery.

The harness runs `scripts/pgvideo prepare`, writes and imports the plan and the
storyboard, runs the separate review, and calls `scripts/pgvideo build`. It
finishes by reporting the delivered files, for example:

```text
output/<request-id>/track-activity-query-size-summary.mp4
output/<request-id>/transcript.md, captions.srt, captions.vtt, references.md,
  glossary-check.md, content-report.md, plan.md, orchestration.json,
  quality-report.json, manifest.json
```

or an actionable blocker with the saved request ID, such as a glossary conflict
that needs your decision or a plan that cannot fit the requested length. Ask the
harness to continue that request later; everything it needs is saved in
`runs/<request-id>/`.

## Commands

Run the scripts in `scripts/` directly; no shell activation is needed. Paths
given as arguments are resolved from the project root. The harness calls the
stage commands; you rarely need to, but every one of them can be run by hand.

| Command | What it does | Network |
| --- | --- | --- |
| `scripts/setup [--offline]` | Provisions the pinned Python runtime, packages, Kokoro model, fonts, FFmpeg, eSpeak NG, and Chromium inside the project, then runs `doctor --sample`. `--offline` rebuilds `.venv/` and `.runtime/` from `cache/` only. | yes, except with `--offline` |
| `scripts/pgvideo prepare --document <page> [options]` | Creates a request and runs the source snapshot, document parsing, glossary matching and cross-check, and the evidence packet. Stops before any content is written. | yes (GitHub) |
| `scripts/pgvideo status --request <id>` | Stage statuses, artifacts, unresolved issues, repair budgets, and the legal next steps. | no |
| `scripts/pgvideo plan --request <id> --file <plan.json>` | Imports and checks the harness's content plan. | no |
| `scripts/pgvideo script --request <id> --storyboard <file>` | Imports and checks the harness's storyboard. Never starts narration. | no |
| `scripts/pgvideo review --request <id> --file <review.json>` | Imports the separate semantic review and decides the content gate. | no |
| `scripts/pgvideo build --request <id> [--no-reuse] [--accept-duration]` | Narrates, checks the measured length, times, renders, validates, and delivers an accepted storyboard, reusing matching media. | no |
| `scripts/pgvideo resume --request <id>` | Repeats the glossary cross-check with the request's `resolutions.yaml`, rebuilds the evidence packet, and revalidates the saved plan, storyboard, and review. | no |
| `scripts/pgvideo replay --request <id> --from <other-id>` | Revalidates another request's accepted content for this request when the evidence, prompts, and review policy match. No new inference. | no |
| `scripts/pgvideo excerpt --request <id> --path <file> --lines <a>-<b>` | Prints lines of a PostgreSQL file from the request's snapshot with their evidence ID. | no |
| `scripts/pgvideo baseline --request <id>` | Drafts the old extractive script for comparison. It is never narrated or delivered. | no |
| `scripts/pgvideo note --request <id> --kind visual\|listening --text "…"` | Records a visual or listening check that was actually performed on the delivered video. | no |
| `scripts/pgvideo narrate`, `timing`, `render`, `validate --request <id>` | Repeat one media stage and the ones after it. The content gate applies. | no |
| `scripts/pgvideo doctor [--sample]` | Checks the local environment and writes `.runtime/environment-report.json`. `--sample` also narrates, renders, and encodes a short offline sample. | no |
| `scripts/pgvideo audit` | Repeats `setup --offline` and the sample under a sandbox profile that terminates any undocumented access outside the project. | no |
| `scripts/pgvideo test` | Runs the test suite in the offline sandbox. | no |

`<id>` is the request ID that `prepare` prints; it is also the request's
directory name under `runs/`. A command given `--request` works on that request
only and never creates one. `doctor` runs before every `scripts/pgvideo`
command, and a failed check stops the command. `scripts/pgvideo <command> --help`
lists a command's options.

The harness-facing commands (`prepare`, `status`, `plan`, `script`, `review`,
`build`, `resume`, `replay`, `excerpt`, `baseline`, `note`) take `--json`. They
then print one structured result on standard output, with `request_id`,
`stage`, `status`, `artifacts`, `issues`, `next_actions`, and a `message`
([schemas/stage-result.schema.json](schemas/stage-result.schema.json)), and keep
it as `runs/<id>/last-result.json`. Progress lines go to standard error.

### `prepare` options

| Option | Default | Meaning |
| --- | --- | --- |
| `--document` | required | A repository-relative `.md` path, or an HTTPS GitHub blob URL in `person123git/postgres-llm-wiki`. |
| `--ref` | `master` | The branch, tag, or commit for a relative path. A blob URL uses its own ref; a different `--ref` is rejected. |
| `--detail` | `standard` | `summary`: the main answer and its qualifications. `standard`: the mechanism and useful examples. `full`: every eligible section, with no duration ceiling. |
| `--audience` | PostgreSQL users and administrators who know SQL | Who the video is for; the plan and review must keep it. |
| `--target-minutes` | 3 for `summary`, 8 for `standard`, none for `full` | The duration target. The plan, the script estimate, and the measured narration must stay within ±15%. Rejected with `full`. |
| `--voice` | `af_heart` | The Kokoro voice. It must be provisioned in `tools.lock`. |
| `--language` | `a` | The Kokoro language code; `a` is American English. |
| `--speed` | `1.0` | The speaking speed, a positive number. |
| `--width`, `--height` | `1920`, `1080` | The video size in pixels, as positive even integers. |
| `--output` | `output` | The delivery directory, inside the project. The video goes to `<output>/<request-id>/`. |

The tool never chooses a page: each request narrates exactly the page named by
`--document`. `prepare` checks that the page exists on GitHub before it creates
the request, and it resolves the ref to one commit for the whole request. It
downloads `wiki/glossary.md` from that commit for every request and builds the
request's glossary index from that copy. Set `GITHUB_TOKEN` if GitHub's API rate
limit blocks a request; unauthenticated clients get 60 API calls an hour, and a
request uses two to six.

The other commands' options:

| Command | Option | Default | Meaning |
| --- | --- | --- | --- |
| `script` | `--storyboard` | none | The harness's version 2 scene file (JSON or YAML) inside the project. |
| `script` | `--drafter-command` | none | An optional adapter: an executable inside the project that reads `draft-input.json` on standard input and writes the scene file on standard output, offline. |
| `script` | `--duration-rewrite` | off | This storyboard shortens optional detail after the measured narration missed its target (one rewrite). |
| `script` | `--human-revision` | off | A person revised this storyboard after the two automatic repair rounds were used. |
| `build`, `script`, `resume` | `--no-reuse` | off | Build the narration and MP4 instead of reusing a validated video. |
| `build` | `--accept-duration` | off | You accept a measured length outside the target. The harness passes it only when you say so. |
| `note` | `--kind`, `--text` | required | `visual` or `listening`, and what was checked and found. |
| `narrate` | `--lufs` | `-16` | Integrated loudness target, from -70 to -5 LUFS. |
| `narrate` | `--true-peak` | `-1.5` | Maximum true peak, from -9 to 0 dBTP. |
| `narrate` | `--refresh-unit` | none | Synthesize a unit or sentence again even though it is cached, such as `s01-title.n1.u1`. Repeat the option for several. |
| `render` | `--crf` | `20` | H.264 constant rate factor, from 0 to 51; lower is higher quality. |
| `render` | `--audio-bitrate` | `128` | AAC bitrate, from 32 to 512 kb/s. |

### Exit status

| Status | Meaning |
| --- | --- |
| 0 | The stage passed, the video was validated and delivered, or the `setup`, `doctor`, `audit`, or `test` check passed. |
| 1 | An execution error, such as an invalid request or file, a missing local dependency, a failed download, an input that changed after it was checked, a refused content gate, or broken media. The message says what failed. |
| 2 | Invalid command-line arguments. |
| 3 | `needs_review`: the stage ran and found issues that need a repair or a decision. |

## How a request flows

```text
prepare: snapshot → parse → glossary match → cross-check → evidence packet
harness: content plan → plan checks → storyboard → storyboard checks → separate review → content gate
build:   Kokoro narration → measured-length check → timing → slides and MP4 → validation → delivery
```

1. **Evidence.** `prepare` writes `runs/<id>/evidence-packet.json`: every section
   eligible for narration with stable sentence and row IDs, tables, code, and
   caveat flags; the candidate glossary entries with their version scope; excerpts
   of the cited PostgreSQL lines at the pin, each with an evidence ID and SHA-256;
   the configuration facts parsed from the pinned GUC table; and the cross-check's
   conflicts, corrections, and resolutions.
2. **Plan.** The harness chooses the main answer, the claims to teach in order,
   the caveats that must survive, a time budget per part, and a reason for each
   section it leaves out, and assesses every claim against its evidence.
   pgvideo checks every ID, the coverage of eligible sections, Step 6
   corrections, and the budget, and records the plan in `plan.json` and
   `plan-report.md`.
3. **Storyboard.** The harness writes the scenes for speech. Every factual
   sentence names its plan claims and evidence; every diagram edge names the
   claims behind its direction. pgvideo rechecks names, numbers, versions, and
   configuration facts against the snapshot, checks screens, code, tables, and
   edge direction, and estimates the length at the Kokoro rate measured on this
   machine. `script.md` shows the result; its checks are labeled lexical.
4. **Review.** A separate pass judges every narration item, screen line, diagram
   edge, and hand-written TTS text as supported, contradicted, or lacking
   evidence, and adds editorial findings. pgvideo accepts the review only for the
   exact current storyboard and plan, writes `content-review.json` and
   `content-report.md`, and opens the content gate only when every factual target
   is supported and nothing is material.
5. **Media.** `build`, and every media command, refuses without the gate. It
   narrates, compares the measured length with the target, and then times,
   renders, validates, and delivers.

Old requests, made before this workflow, keep their extractive provenance: they
are not relabeled, and `resume`, `script`, and the media commands replay them
as before. `baseline` produces the same extractive script for any request as a
comparison.

## Common tasks

### Make a video

Ask your harness, naming one page and anything that matters to you:

> Read AGENTS.md and make a standard video of
> wiki/v18/questions/observability/track-activity-query-size.md for developers
> new to PostgreSQL monitoring, about eight minutes.

To prepare a request yourself and hand it to a harness later:

```sh
scripts/pgvideo prepare --document wiki/v18/questions/observability/track-activity-query-size.md --detail summary
scripts/pgvideo status --request <id>
```

### Choose how much detail and how long

| Level | What the harness plans | Default target |
| --- | --- | --- |
| `summary` | The main answer and the qualifications it needs. | 3 minutes |
| `standard` (default) | The mechanism and the page's useful examples, within the target. | 8 minutes |
| `full` | Every eligible section, with its tables, code, and figures. | none |

`--target-minutes` sets another target. Mandatory content and a strict target can
conflict; the harness then reports an infeasible plan instead of dropping a
caveat or overrunning. The level, audience, and target belong to the request; for
another level of the same page, prepare a new request. A summary is delivered as
`<page>-summary.mp4` and full detail as `<page>-full.mp4`.

### Continue or revise a request

Ask the harness to continue request `<id>`; it starts from `status`. To revise,
say what to change: "shorten the terminology scene of request `<id>`" or "the
review missed that the setting needs a restart; fix it." The harness writes a new
storyboard, reviews it again, and builds; unchanged narration comes from the
audio cache. What stops a request and what happens next:

| Stopped at | Report | What to do |
| --- | --- | --- |
| Source snapshot or document | `source-report.md`, `coverage.md` | The wiki page needs a fix, such as a version conflict or missing evidence. Fix the page, then prepare a new request. |
| Glossary cross-check | `glossary-check.md` | Decide each blocking issue and record it in `runs/<id>/resolutions.yaml` (the report gives a snippet for each), then ask the harness to resume, or run `scripts/pgvideo resume --request <id>`. The harness may propose a resolution, but only you record it. |
| Plan | `plan-report.md` | The harness fixes what it can. An infeasible plan, a contradicted claim, or missing evidence is reported to you: change the target or detail, or accept the omission. |
| Storyboard | `script.md` | The harness repairs the named issues and imports again. |
| Content review | `content-report.md` | The harness gets two repair rounds; then it reports the remaining findings for your decision. |
| Measured length | `status` | One rewrite of optional detail; then you may accept the length (`build --accept-duration`). |
| Media validation | `quality-report.json` | The media is valid, but loudness or silence is out of range. Repeat the narration with other settings, or revise the script. |

### Fix a pronunciation

Edit `pronunciation/en.yaml`, then ask the harness to re-import the request's
storyboard (`runs/<id>/authored/storyboard.json`) and build. A sentence can also
carry hand-written TTS text with `tts_source: manual`; the review checks it
against the display text. To synthesize one unit again without changing it:

```sh
scripts/pgvideo narrate --request <id> --refresh-unit s03-terms.n2.u1
```

Unit IDs are listed in `runs/<id>/narration/audio-map.json`.

### Use an updated glossary

Commit the change to `wiki/glossary.md` in the wiki, then prepare a new request
with a ref that contains it, such as the default `master`. Every `prepare`
downloads the glossary at the resolved commit; `resume` and the other
`--request` commands keep the glossary their request downloaded. A changed
glossary changes the evidence digest, so accepted content is not replayed and
the video is not reused.

### Replay accepted content

When `prepare` finds an earlier request whose accepted plan, storyboard, and
review were made from the same evidence, prompts, schemas, and review policy, it
lists it as `replay_available`. `scripts/pgvideo replay --request <id> --from
<earlier-id>` imports those exact files through the same validators, with no new
inference; the orchestration record says so and never claims a new generation.

### Re-encode, deliver again, or build instead of reusing

```sh
scripts/pgvideo render --request <id> --crf 18
scripts/pgvideo validate --request <id>
scripts/pgvideo build --request <id> --no-reuse
```

### Replay an older request

Requests made before the harness workflow have no plan or review. Their
original commands still work: `scripts/pgvideo resume --request <id>` repeats
the cross-check and the extractive script with the drafter the request used, and
`script --request <id> [--storyboard <file>]` redrafts or imports an edited copy
of its `storyboard.json`. They are never relabeled as LLM-generated.

### Check the environment

```sh
scripts/pgvideo doctor             # every check; runs before each command anyway
scripts/pgvideo doctor --sample    # also a short offline narration, slide, and MP4
scripts/pgvideo audit              # setup --offline and the sample under a kill-on-access profile
scripts/pgvideo test               # unit and integration tests
```

## Network and containment

Model inference happens in the harness, outside pgvideo's sandbox, with the
harness's own credentials; the project sandbox does not contain the harness.
pgvideo's commands run in the sandbox: `setup` downloads the locked runtime and
models, `prepare` reads GitHub (the wiki and the PostgreSQL mirror), and every
other command, including narration, rendering, and all validation, runs with IP
connections denied. No pgvideo command calls a model or receives inference
credentials; `--drafter-command` adapters run offline too. See
[Containment](#containment).

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| The harness does not follow the workflow | Tell it to read `AGENTS.md`; not every harness loads it automatically. |
| "not a separate review" | Use a fresh session, subagent, or model invocation with no writer conversation, reasoning, notes, or self-assessment. Changing the model alone is insufficient. Report it if this separation is unavailable. |
| The model is unavailable, or credentials or quota ran out | Progress is saved. Fix the harness's model access and ask it to continue the request; `status` shows where it stopped. |
| "does not match schemas/…" | The harness wrote malformed JSON or included fields pgvideo computes, such as statuses. It rewrites the file from the schema. |
| "insufficient_evidence" or "missing evidence" | A claim needs a file or range that is not in the pinned snapshot. The claim is left out, or you decide what to do; pgvideo never substitutes other documentation. |
| "made from other evidence", "reviews another storyboard" | A file is stale: a stage before it changed. Write it again from the current files; `status` lists the digests. |
| The repair budget is used | The remaining findings need your decision; a revision you make is imported with `--human-revision`. |
| The measured length misses the target | The harness rewrites optional detail once; then you accept the length or change the target in a new request. |
| Media checks failed | See `quality-report.json`; repeat the media stage. Content is not regenerated. |
| Command fails before starting | `scripts/pgvideo doctor` names the missing or changed local dependency; `scripts/setup --offline` restores it. |

## Where files go

| Location | Contents |
| --- | --- |
| `runs/<id>/` | One request: `request.json`, `orchestration.json`, its read-only inputs, `evidence-packet.json`, `plan.json`, `storyboard.json`, `content-review.json`, the exact files the harness submitted in `authored/`, every stage's record and report, `last-result.json`, audio, slides, and the draft MP4. It is kept after delivery so any stage can be repeated. |
| `output/<id>/` | The delivery: `<page>.mp4` (`<page>-summary.mp4` or `<page>-full.mp4` for those levels), `transcript.md`, `captions.srt`, `captions.vtt`, `references.md`, `glossary-check.md`, `content-report.md`, `plan.md`, `orchestration.json`, `quality-report.json`, and `manifest.json`. |
| `cache/` | Downloads and reusable results: source files by commit, narration units, validated videos in `cache/videos/`, and accepted harness content in `cache/content/`. |
| `.runtime/` | The local Python runtime, FFmpeg, eSpeak NG, Chromium, temporary files, and `environment-report.json`. |
| `AGENTS.md`, `prompts/`, `schemas/`, `docs/harness.md` | The harness runbook, its phase prompts, the versioned JSON Schemas, and its reference. |

`manifest.json` holds the stage statuses, which only pgvideo writes;
`orchestration.json` records the instruction version and hash, prompt and schema
hashes, what the harness reported about itself and its model (unreported values
are marked unavailable), repair rounds, and media checks. Deleting a request's
directory under `runs/` is safe; its video and content can no longer be reused.

## How it works

### Local environment

`scripts/setup` provisions a project-local Python 3.11.16 runtime and `.venv/`,
a hash-locked wheelhouse, the Kokoro model and voice, an English language model,
bundled fonts, Playwright's headless Chromium, FFmpeg, and the eSpeak NG library
and data. The current `tools.lock` supports macOS arm64. Setup downloads and
verifies the pinned Python archive, creates `.venv/`, installs every locked
artifact inside a networked project sandbox, and then runs `doctor --sample`
offline. Every download is checked against a SHA-256 digest in
`requirements.lock` or `tools.lock` and kept in `cache/wheels/` or
`cache/downloads/`, including the headless Chromium archive. After the first
setup, `scripts/setup --offline` recreates `.venv/` and `.runtime/` from those
local files; a missing artifact fails with a setup error. Setup does not install
system or user packages, does not change shell configuration, and needs no
tools from the search path: it passes with an empty `PATH`.

### Containment

The launcher replaces inherited Python, pip, cache, home, temporary, browser,
TLS, and tool paths with project-local values. It then re-executes every
command under a macOS Seatbelt profile through `/usr/bin/sandbox-exec`:

| Command | Network | File access outside the project |
| --- | --- | --- |
| `setup`, `prepare` | allowed | denied except the operating system paths below |
| `setup --offline`, `doctor`, `test`, and every other `scripts/pgvideo` command | IP connections denied | the same |
| `audit` | IP connections terminate the process | the same, except that an undocumented attempt terminates the process; see [Isolation audit](#isolation-audit) |

Sandboxed processes may read file contents only inside the project,
`/System` (excluding the data volume), `/usr/lib`, the time zone, ICU, and
locale data under `/usr/share` and `/private/var/db/timezone`, `/dev`, and the
root directory listing. They may write only inside the project and to
`/dev/null`, terminals, and inherited descriptors. They may execute only
project files and `/bin/sh` with its shell variants. Metadata lookups and Mach
IPC to system services, such as DNS and font services, remain available. A
command started by an already sandboxed process, such as the test suite, keeps
that sandbox because macOS does not allow a different profile to be applied.

Some libraries look outside the project unless configured. The controlled
environment sets `MAC_CHROMIUM_TMPDIR` because Chromium ignores `TMPDIR` on
macOS. It points `SSL_CERT_FILE` at the hash-locked `certifi` bundle, sets
`OPENSSL_CONF` to the null device, and sets `__CF_USER_TEXT_ENCODING` so that
CoreFoundation does not read the real home directory. Setup installs
`scripts/sitecustomize.py` into `.venv/`, so `mimetypes` uses Python's built-in
table instead of host files such as `/etc/apache2/mime.types`.

`doctor` runs before every command. It checks interpreter and package
locations, locked artifact hashes, FFmpeg capabilities, browser files, fonts,
and writable directories. It parses the Mach-O load commands of every project
binary and resolves `@rpath`, `@loader_path`, and absolute dependencies,
without Xcode's `otool`; each must resolve inside the project or to a macOS
system library. It also attempts four accesses that the sandbox must deny:
writing `/private/tmp`, reading `/private/etc/hosts`, running `/usr/bin/true`,
and, when offline, connecting to a TEST-NET address.

`doctor --sample` runs offline. It synthesizes a Kokoro WAV and renders a
1920 × 1080 slide with headless Chromium, then encodes an H.264/AAC MP4 with
`+faststart` and verifies it with ffprobe and a full decode. It confirms
through the DevTools protocol that the slide text used only the fonts in
`assets/fonts/`, and that every native library loaded by the sample came from
the project or macOS. Outputs stay in `.runtime/tmp/`.

Doctor writes `.runtime/environment-report.json` with the resolved paths,
versions, sandbox profile, probe results, the last sample and audit results
for the current locks and scripts, operating system requirements, and
limitations.
Each request copies this snapshot into its `manifest.json`. Explicit
`GITHUB_TOKEN`, `HF_TOKEN`, and proxy settings may pass to child processes;
they are not saved in reports.

The sandbox denies the following attempts, and setup and the offline sample
still pass. `scripts/pgvideo audit` shows that nothing else is attempted on
macOS 27.0 (arm64); see [Isolation audit](#isolation-audit).

- PyTorch's bundled OpenMP runtime lists `/private/tmp` and tries to create
  `/private/tmp/__KMP_REGISTERED_LIB_<pid>`; `/tmp` is hard-coded, and denial
  makes it fall back to an environment variable.
- Through macOS frameworks, Chromium lists `/private/etc` and reads
  `/private/etc/hosts`, `/Library/Preferences/com.apple.networkd.plist`,
  `/private/var/db/mds`, `~/Library/Keyboard Layouts`,
  `~/Library/Input Methods`, and `~/Library/Autosave Information`.
- Starting `/bin/sh` or another allowed shell, as `scripts/espeak-ng-runtime`
  does, lists `/bin` and reads the shell binaries.

The Python archive download, extraction, and `.venv/` creation in
`scripts/setup` run before the sandbox applies, using `/bin/sh`, `/bin/mkdir`,
`/usr/bin/uname`, `/usr/bin/curl`, `/usr/bin/shasum`, `/usr/bin/tar`, and
`/usr/bin/env` by absolute path. `sandbox-exec` is deprecated by Apple; if it
disappears, commands fail rather than run unconfined.

### Requests

Each `prepare` creates a new request ID of the form
`YYYYMMDDTHHMMSSZ-<12 hex>` and saves the normalized request as
`runs/<request-id>/request.json`, regardless of the working directory. The
request records the page, the requested ref, the settings (including the
audience and duration target), and its workflow: `harness`, with the version and
SHA-256 of the `AGENTS.md` it started under. `orchestration.json` starts at the
same time with the prompt and schema hashes. A request without a workflow record
was made before the harness workflow and keeps its extractive provenance. Relative output
paths are resolved from the project root, and absolute paths must also stay
inside it. The output and `runs/` paths are checked for traversal and symlink
escapes before any GitHub access and again before anything is written. Width
and height must be positive even integers for H.264 encoding, and the voice and
language must be provisioned locally; only `a`/`af_heart` is provisioned now.

### Source snapshot

After saving the request, `prepare` resolves the requested ref to a full wiki
commit SHA once. It reads the document and `wiki/glossary.md` from that same
commit, so a branch that moves during the request cannot mix versions. The
wiki's cited `raw/postgres-NN/` checkouts are not in its repository. They are
retrieved from `postgres/postgres`, GitHub's mirror of the upstream
repository, at the document's `pinned_commit`. `git.postgresql.org` is not used
because it rate-limits automated downloads. Nothing is read from another
checkout or a shared Git cache.

Every file is checked against its Git blob ID in the commit's tree. Downloads
are cached by commit and path under
`cache/sources/<owner>/<repository>/<commit>/`, and a cached file that fails
the check is downloaded again. The glossary is the exception: every request
downloads it again, even when the cache already holds it for that commit, so
no request depends on a copy that another request downloaded. If that download
fails or does not match the commit, the request fails. The run directory
receives:

| File | Contents |
| --- | --- |
| `inputs/wiki/`, `inputs/postgres/` | Read-only copies of the document, glossary, images stored in the wiki, `configure.ac` (or `configure.in` for 12), and each cited source file |
| `sources.json` | Wiki commit, front matter, title, headings, every link resolved against the document's location with its line number, glossary source pins, and the size, SHA-256, and Git blob ID of each input |
| `source-report.md` | Status, blocking issues with the action needed, warnings, notes, and an input table with commit-specific links |
| `manifest.json` | The environment snapshot, plus the wiki commit and PostgreSQL source commit kept as separate fields, and the hashes of every input |

These problems block the request before narration, and the command exits
with status 3 (`needs_review`):

- a front matter `version` that disagrees with the `wiki/vNN/` path, or no version at all;
- citations into another version's `raw/postgres-NN/` tree;
- a missing, malformed, or nonexistent `pinned_commit`, or one whose `configure.ac` reports another major version;
- no citations into the document's own source tree;
- a cited file or line range that does not exist at the pin, unless the citation appears only under
  Contents, Context Reviewed, Source References, or Navigation, in which case it is a warning;
- a missing or unreadable glossary, unreadable front matter, or a document that is not UTF-8.

Broken in-page anchors, glossary anchors, and wiki links are warnings. A
glossary checked at a different pin for the document's version, or with no
row for it, is also a warning. The report notes when the document or the
glossary declares `verified: false`. A network, integrity, or path failure
marks the manifest `failed` and exits with status 1. The run keeps the files
saved before the failure.

A request makes one GitHub API call to validate a relative path (a blob URL
may need one per possible ref/path split) and one to resolve the ref. It also
makes two for each wiki or PostgreSQL commit not yet cached, so a request
needs two to six API calls. File contents come from
`raw.githubusercontent.com`, which does not count against the API limit. Unauthenticated clients get 60 API calls an hour; set
`GITHUB_TOKEN` for more.

### Document structure and coverage map

When the snapshot passes, `prepare` parses the snapshot copy of the document.
It checks the copy's SHA-256 first and makes no network requests. For a harness
request, extraction is kept apart from editorial selection: the coverage map in
`document.json` marks every section with narratable content as eligible (the
full-detail rules below), and the harness's plan decides what is said. The map
the rules below make for the requested level is kept as `static_coverage` for
regression comparison and for `baseline`; `coverage.md` says which mode it
shows. The run
directory receives:

| File | Contents |
| --- | --- |
| `document.json` | Every section, block, and sentence with a stable ID and its lines in the original file; every link with the sentence that holds it and a commit-specific URL; the extracted subject, conclusions, terms, quantities, version mentions, examples, and open questions; and the coverage map |
| `coverage.md` | The coverage decision and reason for each section, the question, the conclusions, mentions of other PostgreSQL versions, the maintenance text left out of the narration, and linked wiki pages that the video does not cover |

Section IDs are the page's GitHub heading anchors, such as `short-answer`.
Block IDs extend them by position, such as `short-answer.2` or
`how-it-works.1.2.1` for a list item, and sentences add `.s1`, `.s2`, and so on.
Editing one section does not change the IDs in another.

Each sentence keeps display text, with inline code in backticks, and spoken
text. Both drop citation links; the sentence records them by link ID instead.
Spoken text also drops bare URLs. It is null for text that is never narrated:

- maintenance text such as `Follow AGENTS.md.` and prompt-hygiene notes;
- `Contents`, `Navigation`, and `Related Pages`;
- `Context Reviewed`, `Evidence Map`, and `Source References`;
- HTML.

Front matter is recorded as metadata, not as blocks.

A term is a setting when the cited `guc_tables.c` (`guc.c` in older versions),
`guc_parameters.dat`, or `postgresql.conf.sample` at the pinned commit defines
it. Without one of those files, the setting classification is only a hint and
is marked `setting_source: context`. Quantities keep their units and exclude
versions, dates, commit hashes, and labels such as "rule 2".

The coverage map estimates narration at 150 words per minute, plus 25 words
for each code block or image shown on screen. A table counts the words of its
rows, since the drafter reads each row aloud. The target is 6–10 minutes. When
the narratable text fits, every section is explained. For longer pages:

- the question and open questions are explained when short and summarized when long;
- a summarized section keeps its lead and most relevant sentences; a section
  that is only a table keeps the table's first rows, and one with only code or
  a figure is explained if it fits and omitted otherwise;
- sections about limitations, edge cases, or restrictions are always summarized at least;
- sections that use the question's or conclusions' terms are explained first;
- tests, history, and measurement detail are the first to be omitted;
- the measurement script is omitted, and navigation and reference lists are excluded.

Omitted sections remain in the references. A page with no narratable prose
stops with `needs_review` and exit status 3.

These are the rules of the `standard` level. The other levels of
[`--detail`](#choose-how-much-detail) change them:

- `full` explains every section except the measurement script and the
  navigation and reference lists, including long questions and follow-up
  prompts. It has no length target; a plan over 10 minutes gets a note.
- `summary` plans about 3 minutes (1–3 minutes at 150 words per minute). It
  keeps the central question, or its first sentence when it is longer than 150
  words; the page's own summary, including a Short Answer or Answer Up Front
  under `## Answer`, as prose without its tables and code; and, when the page
  has no summary section, the conclusions that open its answer. It also keeps
  the first sentence of each caveat section and the first open question, or
  all of that question when it has at most 80 words. It then adds the first
  sentence of other sections while they fit: main sections before their
  subsections, then sections that use the subject's terms, in page order, and
  then the other open questions. Follow-up prompts, tests, history, and other
  supporting detail, including subsections of such sections, are left out. A
  first sentence is the section's first narrated sentence that has at least
  three words and does not end with a colon. The coverage map records the
  sentences a summary keeps for each section it reduces, and `coverage.md`
  lists them.

### Glossary matches

When the document passes, `prepare` indexes the glossary that the source
snapshot downloaded for this request and matches the document against it,
without network access. It first checks `document.json` and the glossary's
snapshot copy against their recorded SHA-256 values. Every request builds its
own index and saves it as `runs/<id>/glossary-index.json`; an index built for
another request is never used, even for the same glossary. The command prints
the index's path and entry count, and the manifest records its path, SHA-256,
build time, and a digest of the parsing code and English lexicon that built it.

Each index entry keeps the entry's heading anchor, term, aliases, checked
versions, definition, version notes, Related entries, and evidence links, with
PostgreSQL URLs from the glossary's own Source Pins. Aliases marked
`(contrast)` name a contrasting concept, and aliases such as
`stats collector (PostgreSQL 12 and 14)` apply only to those versions.

Candidates come from glossary links in the document and from entry names,
aliases, acronyms, and identifiers in its headings, narrated sentences, tables,
and code. Matching respects identifier and word boundaries: `pg_am` does not
match `pg_amop`, and `HOT` does not match "hot" or "HOTEL". Some forms need
context before they count:

- ordinary English words such as "path", "cost", or "row" (words in Kokoro's
  English pronunciation lexicon, so jargon such as "autovacuum" does not);
- words and code values of three characters or fewer, and two-letter acronyms;
- code values such as `auto`, which must also be marked as code in the document.

Context comes from the glossary itself: a source file that the paragraph and
the entry both cite, a symbol from the entry's definition, an entry related to
it that is already matched in the paragraph, a link to the entry, or another
distinctive form of the entry in the same section. A word without context
follows the entry that the same word matched elsewhere in the document; code
values do not. Otherwise the occurrence is ambiguous, and so is a form that
several entries share when neither has more support.

The run directory receives `glossary-matches.json`:

| Field | Contents |
| --- | --- |
| `matches` | Each matched entry, ranked `central` (title, question, or conclusions), `supporting`, or `peripheral`, with every occurrence's sentence ID, line, method, and supporting evidence, the definition, and its version scope |
| `ambiguous` | Occurrences that need context or match several entries, with each candidate entry |
| `unmatched` | Settings, functions, identifiers, and other concepts in the document that no entry covers |
| `subject` | The subject's focus terms mapped to entries |
| `issues` | Version and coverage findings for the cross-check |

The version scope applies the entry's own rules for the document's version:
the main paragraph, a `Holds` note (with any exceptions it names), a `Differs`
or `Not present` note, or `unchecked` when the entry was not checked on that
version. A note that refers to another, such as "as in 18", includes that
note. Step 5 does not stop the request; the cross-check decides which
ambiguities and gaps need review.

### Glossary cross-check

When the glossary matches pass, `prepare` cross-checks the document without
network access or a language model. It first checks `document.json` and
`glossary-matches.json` against the SHA-256 values in the manifest. It reads
the cited PostgreSQL files and `configure.ac` from the run's verified snapshot
copies. The glossary declares `verified: false`, so agreement with it is only
a consistency result. Narrated claims must rest on the document's own
citations at its pinned commit.

Each matched entry, ambiguous term, and concept the glossary lacks gets one of
five results: `consistent`, `conflict`, `version_mismatch`, `ambiguous`, or
`not_in_glossary`. The checks are:

- **Version scope.** An entry whose definition applies to the document's
  version is consistent. A `Not present` entry that the document narrates is a
  version mismatch, unless the pinned source contains the name, or the
  sentence names another version, uses a historical word, or says the concept
  is absent. An alias that the glossary limits to other versions is handled
  the same way.
- **Parameter facts.** The context, default, minimum, and maximum that the
  document states for a parameter are compared with the glossary's statement
  for that version, and with the cited `guc_tables.c`, `guc.c`,
  `guc_parameters.dat`, or `postgresql.conf.sample` at the pin. Units are
  converted: `128MB` equals 16384 blocks at 8 kB `BLCKSZ`. Enum spellings come
  from the options table. The pinned source settles a disagreement. When it
  contradicts the document, a correction is recorded for the script, and the
  snapshot stays unchanged.
- **Acronyms and roles.** An expansion such as "write-ahead log (WAL)" must
  match the entry's name or aliases. A sentence such as "`pg_stat_activity` is
  a view" must give the entry's role.
- **Coverage.** A concept that the glossary lacks, or does not cover for this
  version, is allowed when its narrated mentions appear in the document's
  pinned evidence. The allowed concepts are listed as exceptions.

Every narrated sentence and displayed table row in the content is also
checked against its citations: the sentence's own, else its paragraph's, else
its section's. Its identifiers, numeric inline code, and quoted strings must
appear in the cited lines, the cited files, or another file the document
cites. Each search tries an exact match, then a case-insensitive one, so
`track_activity_query_size` is found inside `pgstat_track_activity_query_size`.
A name is not required when the asker used it in the question, when the
document's own example code defines it, or when the sentence says it does not
exist. Each such case is reported.

The run directory receives:

| File | Contents |
| --- | --- |
| `glossary-check.json` | Each result with its passages, glossary excerpt and version status, evidence links, and resolution; each claim with its citations and where every item was found; corrections, omissions, and exceptions for the script; and how each glossary definition may be used |
| `glossary-check.md` | Status; blocking issues with the evidence needed and a resolution snippet; warnings; the subject's focus terms; the entries with their version scope; parameter facts against the pinned source; corrections; uncovered concepts; ambiguous terms; and unconfirmed claims |

These problems stop the request with `needs_review` and exit status 3:

- a conflict or version mismatch in narrated text that the pinned source does
  not settle;
- a central term that two glossary entries claim equally, or an ambiguous
  subject term;
- a central claim with a name that is missing from the pinned evidence;
- a central concept that neither the glossary nor the evidence supports.

An ordinary word such as "row" that matches an entry only ambiguously is a
warning, even in a conclusion. So is a central sentence with nothing to look
up and no citation in its section, such as a verdict drawn from the page's
own measurements.

To continue, record a decision for each blocking issue in the run's
`resolutions.yaml`, then resume the same request:

```yaml
resolutions:
  - id: "entry:asynchronous-io"
    decision: use_document   # use_document, use_glossary, omit, or choose_entry
    reason: "src/backend/storage/aio/ holds read_stream.c in PostgreSQL 17."
    evidence: raw/postgres-17/src/backend/storage/aio/read_stream.c#L1-L20
```

```sh
/path/to/postgres-videos/scripts/pgvideo resume --request <request-id>
```

`use_document` and `use_glossary` need evidence from the document's own
`raw/postgres-NN/` tree at its pin. Evidence in the snapshot has its line
range checked and its excerpt saved; other evidence is recorded as not
checked. `use_glossary` adds a correction, `omit` leaves the sentence or
concept out of the narration, and `choose_entry` names the entry an ambiguous
term means. `resume` runs offline. It rejects unknown IDs, disallowed
decisions, missing reasons, YAML aliases, and a symlinked resolutions file.
The manifest records the file's SHA-256. Only the cross-check and the script
can be resumed; a source or document blocker needs a wiki fix and a new
request.

### Harness plan, storyboard, and review

After the cross-check passes, `prepare` writes `evidence-packet.json` and stops.
The packet holds every eligible section with its sentences, table rows, code,
images, caveat flag, and the old coverage map's choice (for comparison only);
each sentence's citations and its lexical lookup status, labeled as lexical; the
candidate glossary entries with their definitions, version scope, forms,
occurrences, and whether narration may use them, and every candidate meaning of
an ambiguous term; one excerpt per cited range of a PostgreSQL file, with three
lines of context, at most 80 lines, and an evidence ID such as
`pg:src/backend/utils/misc/guc_tables.c#L3769-L3784` with its SHA-256; files
cited whole or missing from the snapshot; the parsed configuration facts as
`guc:<setting>`; the cross-check's open results, corrections, omissions, and
applied resolutions; the request's audience, detail, and target; and the Kokoro
speech rate measured from earlier narration with this voice and speed (150 words
per minute until a minute of audio has been measured). Its content digest leaves
out the request ID, times, and the speech rate, so the same evidence has the same
digest in every request.

`plan` validates the harness's plan against `schemas/plan.schema.json`, then
checks that it names this request and its current evidence digest; keeps the
request's audience, detail, and target; resolves every source and evidence ID in
the snapshot; selects only eligible text that no resolution omitted; states each
Step 6 corrected value; has no selected sentence whose identifiers the pinned
evidence lacks; assesses every claim as supported with evidence (a contradicted
or unsupported claim needs review); narrates the main answer and every required
caveat; accounts for every eligible section, never omitting the question or the
page's own summary (an omitted caveat section is a warning for the review); and
budgets within the target's ±15%. An infeasible plan is recorded and reported,
never trimmed or stretched silently.

`script` validates a version 2 scene file against
`schemas/storyboard.schema.json`; derived fields such as statuses, checks, and
word counts are rejected rather than recomputed. Beyond the checks under
[Narration script and storyboard](#narration-script-and-storyboard): every factual
sentence names plan claims (whose sources it inherits) and resolvable evidence;
framing names no claim; every source is selected by the plan; every planned claim
is narrated, and the main answer and required caveats must be; a `paraphrase` is
rechecked like any rewritten sentence, and a changed negation is flagged for the
review; each diagram edge names claims from the sentence it cites, and an edge
drawn against the direction that sentence states is blocking; and the estimate at
the measured speech rate must fit the target. `script` never starts narration.

`review` validates the review against `schemas/review.schema.json` and requires
that it names the current storyboard, plan, and evidence digests; that it
declares a separate context and did not see the writer's context or
self-assessment; and that it has exactly one finding for each narration item,
line of a question, bullet, step, diagram, or image screen, diagram edge, and
hand-written TTS text (`status --json` lists them as `review_targets`). The gate
passes when every factual finding is `supported` with resolvable evidence and no
finding or editorial note is material; minor findings are delivered in
`content-report.md`. After a failed review the harness may import two repaired
storyboards, each reviewed again; the next needs `--human-revision`. The gate is
checked by narration, media reuse, timing, rendering, and validation themselves,
under review policy 1; a new policy requires a new review.

`build` compares the measured narration with the target. Outside ±15%, it stops
for one `--duration-rewrite` of optional detail, and then only for your
`--accept-duration`, which stays valid while the same storyboard measures the
same length. Validation delivers the content report, the plan report, and the
orchestration record with the media, and the quality report records the content
gate. `resume` and `replay` import the saved `authored/` files through the same
checks, so resumed and replayed content is revalidated, not trusted.

### Narration script and storyboard

This section describes the built-in extractive drafter that older requests used
and that `baseline` still runs for comparison, and the checks every storyboard
passes. A harness request's plan, storyboard, and review are described under
[Harness plan, storyboard, and review](#harness-plan-storyboard-and-review).

The built-in drafter works without network access or a language model. It first checks `document.json`,
`glossary-matches.json`, and `glossary-check.json` against the SHA-256 values
in the manifest. The run directory receives:

| File | Contents |
| --- | --- |
| `draft-input.json` | What any drafter receives: the narrated sections with their sentences, code, tables, and images, and the sentences a summary keeps; the glossary entries the document matched and whether the script may use each definition; ambiguous terms; Step 6 corrections and omissions; citations; the level of detail and length limits; and the scene schema |
| `storyboard.json` | The scenes in playback order, each with its ID, outline part, title, screen, visual description, narration, sources, glossary entries, and citations; every sentence's display text, TTS text, origin, and check; the coverage of each section; corrections; issues; and a length estimate |
| `script.md` | The storyboard for review: issues, the outline, each scene with its screen and narration, the TTS text, and the coverage table |

The built-in drafter is deterministic and extractive. It narrates the page's
own sentences in the page's order, after a title scene, the question, and the
central glossary terms, and it ends with the open questions, a recap from the
page's conclusions, and the sources. It splits long sentences at semicolons,
and at colons that start a new clause, without changing their words. Sections
that the coverage map summarizes keep their lead sentence and their most
relevant sentences within the planned word count, and so do open questions
that it summarizes. A condensed table shows and reads only the first rows the
coverage map kept, then says "The table on the page has more rows." Omitted
sections are left out. Step 6 corrections replace
the stated value, and sentences that a resolution omitted are left out.

A summary narrates exactly the sentences the coverage map kept for each section
it reduces, without the section's tables and code. If a resolution omitted a
kept sentence, the section falls back to its other sentences within the
planned word count. A summary has no recap, since it has just narrated the
page's conclusions. The opening slide of a summary shows "Summary" and says
that the video summarizes the page; a full-detail video shows "Full detail".

Screens show the first whole clause of each sentence, never cut before a
qualifier such as "unless" or "not", inside parentheses, or in the middle of a
list. Code, tables, and images stay on screen while the sentence that
introduces them and the paragraph that follows are narrated; long code and
tables are split across scenes, and table rows are read aloud. A scene whose
sentences state at least two relationships between named components, such as
"`pg_stat_activity` is a SQL view over `pg_stat_get_activity(NULL)`", shows
them as a diagram, and ordered lists become numbered steps. Framing sentences
such as "To recap." may name only what the title and question name.

Each sentence keeps its display text for the screen and captions, and TTS
text for Kokoro. `src/pgvideo/speech.py` derives the TTS text with the rules in
`pronunciation/en.yaml`: `pg_stat_activity.query` becomes "P G stat activity
dot query", `PGC_POSTMASTER` becomes "P G C postmaster", and `x * (a + b)`
becomes "x times, a plus b". The storyboard records the dictionary's SHA-256.

To change the script, edit a copy of `storyboard.json`, or write JSON or YAML
in the same shape, and import it. A scene file path is resolved from the
project root and must stay inside the project. Fields that the storyboard
derives, such as checks and word counts, are recomputed; set
`tts_source: manual` to keep a hand-written TTS text.

```sh
/path/to/postgres-videos/scripts/pgvideo script --request <request-id> --storyboard runs/<request-id>/edited.yaml
```

`--drafter-command <file>` runs an executable inside the project instead. It
receives `draft-input.json` on standard input and writes scenes on standard
output, within the offline sandbox. To draft with a text model or service
that needs the network, run it anywhere on `draft-input.json` and import its
output with `--storyboard`. Without either option, `script` redrafts with the
built-in drafter; `resume` reuses the drafter the request last used.

Every scene, whoever drafted it, is validated the same way:

- Every source must be a section, block, sentence, or row that the coverage
  map narrates; excluded text, sentences a resolution omitted, and unknown
  IDs block. Every narrated or summarized question, summary, caveat, or
  open-questions section must appear in a scene, unless `coverage_overrides`
  records why it is left out; other sections left out are warnings.
- A sentence whose letters and digits appear in order in its sources is
  unchanged and keeps its Step 6 claim status, unless the words it leaves out
  include a limiting word such as "not", "only", or "unless".
- Any other sentence is rechecked as Step 6 checked the original: its names,
  numeric code, quoted strings, numbers, and version mentions must be in its
  sources or the pinned evidence; its parameter facts must agree with the
  pinned GUC table; and it must keep its source's negation.
- A glossary sentence must be a definition that Step 6 allows for this
  version; a correction sentence must state the corrected value.
- Screen text, diagram labels, and glossary cards must come from the scene's
  narration and sources; code excerpts and tables must match their blocks.
- The opening scene must show the PostgreSQL version, and no TTS text may
  contain backticks, underscores, URLs, or symbols Kokoro would read aloud.

A blocking issue stops the request with `needs_review` and exit status 3; an
invalid scene file or a failed drafter command exits with status 1. The
manifest records the drafter, its input's SHA-256, the pronunciation
dictionary's SHA-256, and the storyboard's hash. The length estimate uses
150 spoken words per minute; spoken identifiers make a script longer than the
coverage map planned, so a script over 10 minutes is a warning for a page
that fits the target and a note for a long page. A summary's target is 1–3
minutes, so a longer summary gets a note; full detail has no target and no
length issue. Step 8 measures the real length.

### Kokoro narration

After a script passes validation, the tool splits dictionary-generated speech
at clauses and at 28-word limits. It synthesizes every Kokoro chunk in order,
caches 24 kHz mono WAV units by exact TTS text and asset versions, and inserts
sentence and scene pauses. The raw master is normalized with FFmpeg's two-pass
`loudnorm` at -16 LUFS and -1.5 dBTP by default. The run contains
`narration/units/`, `narration/master-raw.wav`, `narration/master.wav`,
`narration/audio-map.json`, and `narration/narration-report.md`. The map records
each unit's sample range on the continuous audio clock for Step 9.

To repeat the audio stage or regenerate a unit after listening:

```sh
/path/to/postgres-videos/scripts/pgvideo narrate --request <request-id>
/path/to/postgres-videos/scripts/pgvideo narrate --request <request-id> --refresh-unit s01-title.n1.u1
```

Edit `pronunciation/en.yaml` or a scene's TTS text to correct a pronunciation,
then rerun `script` so the storyboard and dictionary hash are validated before
the next narration. Manually edited TTS stays in one audio unit.

### Timing and subtitles

After narration, the tool measures the normalized master's sample count and
checks every audio unit against the storyboard. It writes `timeline.json` with
scene sample positions and contiguous 30 fps frame ranges. The last visual
frame covers any fraction of a frame after the audio ends. `captions.srt` and
`captions.vtt` use the measured spoken unit boundaries; scene and sentence
pauses remain in the timeline without subtitle text. To rebuild these files
without resynthesizing audio:

```sh
/path/to/postgres-videos/scripts/pgvideo timing --request <request-id>
```

### Rendering, validation, and delivery

After timing, Playwright renders each storyboard scene to a PNG using the
bundled fonts and a reusable slide template. It rejects overflow, missing
images, and fonts outside the bundle. The renderer holds each PNG for the
scene's measured frame count, then encodes `render/draft.mp4` with H.264 video
at 30 fps and AAC mono audio at 48 kHz. `render.json` records the input and
artifact hashes, and `references.md` links to the resolved document and
commit-specific citations. Validation fully decodes the draft, checks its
streams, timing, caption coverage, spoken units, silence, and loudness, then
copies the MP4 and accompanying files to `output/<request-id>/`. The run's
`quality-report.json` records the measurements and delivery hashes.

When a stage runs again, the manifest drops the records of every later stage,
including an earlier validation, so it never describes media that was built
from older inputs. Repeating the glossary cross-check or the script also drops
the reuse lookup, which belongs to one storyboard.

### Reuse of validated videos

After the content gate passes, `build` (and, for an older request, `resume` and
`script`) looks for a validated video with the same key before narrating. The key is the SHA-256 of every input
that decides the video:

- the page, the glossary, wiki images, and the cited PostgreSQL files, by
  SHA-256, with the wiki commit and the PostgreSQL source pin;
- the storyboard, without its request ID, time, and drafter record (and, for a
  harness storyboard, without its length estimates and statuses, which follow the
  measured speech rate). It keeps
  the page's URL and wiki commit, which the slides and references show, so a
  video is reused only for the same wiki commit, and the level of detail, so a
  video is reused only for the same level;
- the pronunciation dictionary;
- the voice, language, speed, loudness target, and true-peak limit, and the
  Kokoro model, configuration, and voice files;
- the width, height, frame rate, CRF, and audio bitrate;
- `tools.lock` and `requirements.lock`, which pin the Kokoro assets, eSpeak NG,
  FFmpeg, Chromium, fonts, and Python packages; the slide template and fonts;
  and the code of the speech, narration, timing, rendering, and validation
  modules.

A new glossary snapshot therefore never reuses a video, or the cross-check
behind it, even when the page is unchanged: every request cross-checks its own
snapshot, and the glossary's hash is part of the key.

Validation registers each delivered video as
`cache/videos/<key>/<request-id>.json`, with the SHA-256 of its audio map,
render record, unit WAVs, masters, slides, MP4, and references. It registers a
video only when the narration, timing, and render stages ran with the same
tools and code as the validation. A lookup verifies every listed file in the
earlier request's run directory, copies the narration and MP4 into the new
request, and then runs the new request's own timing and validation, so the
delivered video is checked again. An entry whose files are missing or changed
is reported, skipped, and removed from the index. If the copied narration or
MP4 cannot be used, that stage is built instead. A lookup never creates,
changes, or delivers another request.

The manifest's `reuse` record keeps the key, its components, the lookup's
result, and whether the video was registered. Reused stages name their source
request in `reused_from`, as does the quality report. Commands for one stage
(`narrate`, `timing`, `render`, and `validate`) always repeat it, although
narration units still come from the unit cache when their TTS text and
provenance match. `--no-reuse` builds a fresh video, which is registered in
turn.

### Isolation audit

`scripts/pgvideo audit` repeats `setup --offline` and the offline sample
(Kokoro synthesis, a Chromium slide, and an FFmpeg encode and decode) under a
Seatbelt profile that terminates any process that reads file contents, writes,
or runs a program outside the project and the operating system paths listed
under [Containment](#containment), or opens an IP connection. Seatbelt does not
log denials on this host, so this is how an undocumented access shows: the
audit stops, and its error names the step. Only the attempts listed under
Containment, and doctor's own denial probes, are denied without terminating.
The audit passed on macOS 27.0 (arm64), which also shows that synthesis,
rendering, and encoding make no network connections.

The result is saved as `isolation.audit` in `.runtime/environment-report.json`
and copied into each request's manifest. It stays valid until the locks or the
environment scripts change. The audit does not cover metadata lookups, Mach
IPC, the bootstrap in `scripts/setup`, or the network retrieval in `setup` and
`prepare`. If an audit fails during setup, run `scripts/setup --offline` to
restore the environment.

### Tests

```sh
/path/to/postgres-videos/scripts/pgvideo test
```

The suite runs inside the offline sandbox in about two minutes. Tests mock GitHub
access and create their temporary fixtures under `.runtime/tmp/`, including the
directories used to simulate escaping paths.

- **Environment:** the sandbox probes; the audit profile's rule order; hostile
  inherited settings, including temporary, cache, model, browser, and eSpeak NG
  paths outside the project; tools on `PATH`, and no tools on `PATH` at all; a
  missing project-local ffprobe with a decoy on `PATH`; Mach-O dependency
  resolution; archive extraction; and the bootstrap pins in `scripts/setup`.
- **Focused checks with small fixtures:** `tests/fixtures/` holds a small wiki,
  with a glossary and one page per case under `wiki/v18/checks/`, and the pinned
  PostgreSQL files that the pages cite. `test_checks.py` runs each page through
  `prepare`. Invalid requests (a missing page, a directory, a non-Markdown
  file, a glob, traversal, another repository, a conflicting or missing ref, an
  output directory outside the project, and an unprovisioned voice) fail before
  a request exists. A consistent page reaches the evidence packet, and stops
  there for the harness, from a path or a blob URL. An alias that two entries claim, a central term with no support, a
  default that contradicts the glossary, an entry not present in PostgreSQL 18,
  and missing or out-of-range evidence each stop the request before narration.
  A contradictory default that the pinned GUC table settles reaches the
  evidence packet as a correction, and the extractive baseline applies it.
- **Source snapshots** use an in-memory GitHub fake to cover single-commit
  retrieval, cache reuse and repair, a glossary downloaded again for every
  request, tampered downloads, every blocking version and evidence check, and
  cache symlink escapes.
- **Documents** are parsed through the same fake to cover block structure,
  line numbers, stable IDs, citation removal, maintenance exclusion,
  extraction, long-document coverage, summary and full-detail coverage (the
  sentences a summary keeps, its budget, a nested Short answer, and the
  conclusions of a page without a summary section), an unknown level, tables
  planned at the words of their rows and condensed to their first rows, and
  altered snapshot copies.
- **Glossary matching** covers entry parsing, alias qualifiers, version notes
  and their references, an index built for each request from its own glossary
  copy, word boundaries, short aliases that need context, alias collisions,
  version-limited aliases, unmatched terms, and altered document records and
  glossary copies.
- **Cross-checks** cover consistent entries, parameter facts against the
  glossary and a pinned GUC table, pinned-source corrections, unit and enum
  comparison, version mismatches and their qualifiers, version-limited aliases,
  acronym expansions, roles, ambiguous central terms, allowed and unsupported
  concepts outside the glossary, claim evidence, every blocking case,
  documented resolutions and their validation, altered inputs, and `prepare`
  followed by `resume`.
- **Scripts** cover the built-in draft's outline, traceability, sentence
  splitting, corrections, tables, code, diagrams, steps, caveats, and
  summaries; a summary's kept sentences, its opening, the missing recap, and a
  kept sentence that a review omits; full detail without a length target; a
  table read with exactly the planned words, and a condensed table that shows
  and reads only its first rows;
  every validation check on edited scene files; invalid scene files;
  a drafter command; resolutions followed by `resume` and `script`; altered
  inputs; and the pronunciation rules.
- **Kokoro integration:** `test_integration.py` narrates a three-scene
  storyboard with the real Kokoro model, including a hand-written unit long
  enough for several Kokoro chunks, then times, renders, and validates it. It
  checks that every chunk reaches its unit WAV, that pauses and sample positions
  add up, that normalization does not move the audio, that captions and scene
  frames follow the samples, and that the MP4's decoded audio stays within 2 ms
  of the master from the first unit to the last, with the last unit present.
  A dropped chunk, a 5 ms shift during normalization, and a 50 ms audio offset
  in the MP4 each fail it.
- **Timing, rendering, and validation** cover frame boundaries, pauses, caption
  offsets, the final tail, changed units, exact frame counts, delivery, the
  file name of each level of detail, and output directories outside the
  project. A repeated stage drops the records
  built from it.
- **Harness workflow:** `test_harness.py` uses recorded harness files, derived
  from the extractive baseline, to cover `prepare` stopping at the evidence
  packet, eligibility and the kept static map, stable evidence digests, the
  refused extractive fallback, request constraints, snapshot-only excerpts,
  every plan check, every storyboard check, derived fields and stale digests,
  the review's coverage, separation, stale and malformed reviews, material and
  unsupported findings, the bounded repair rounds and a person's revision,
  resume and replay without inference, a new instruction version, the
  measured-duration check, and older requests that are not gated. It includes
  the proposal's two semantic mutations: "uses … to read" changed to "to erase"
  still passes the lexical recheck as `verified`, and only the review's
  `contradicted` finding stops it, which then blocks `build` and a direct
  narration; a diagram edge reversed against its sentence is rejected before
  review. These tests exercise pgvideo's contracts, not a model.
- **Reuse:** `test_reuse.py` runs each request through `prepare`, recorded
  harness content, and `build`, and covers the key; an identical request that reuses
  the validated video; new builds for a changed speed, another level of
  detail, a new glossary snapshot, and `--no-reuse`, and a repeated summary
  that reuses its own video; changed or missing files; tampered index entries and an
  escaping cache; retries that reuse their own video without creating requests;
  and videos from other tools, which are not registered. It runs FFmpeg,
  Chromium, timing, and validation for real, with a deterministic stand-in for
  Kokoro.
