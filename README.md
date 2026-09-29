# pgvideo

pgvideo makes one narrated MP4 from one Markdown page of
[person123git/postgres-llm-wiki](https://github.com/person123git/postgres-llm-wiki),
on request. For each request it snapshots the page, the wiki glossary, and the
PostgreSQL source files that the page cites. It cross-checks the page's terms
and claims against the glossary and that source, drafts a narration script and
storyboard, and narrates it with a local Kokoro model. It then times captions
and scenes from the measured audio, renders slides, and encodes, validates, and
delivers the MP4 with its transcript, captions, references, and reports. A later
request with exactly the same inputs reuses the validated video.

The Python runtime, packages, models, tools, caches, and outputs all stay
inside this directory, and every command runs in a macOS sandbox. Steps 1–13 of
`plan.md` are implemented; `plan.md` records the design and its decisions.

## Quick start

pgvideo runs on macOS with Apple silicon (arm64). From any working directory:

```sh
/path/to/postgres-videos/scripts/setup
/path/to/postgres-videos/scripts/pgvideo generate \
  --document wiki/v18/questions/observability/track-activity-query-size.md
```

`setup` provisions everything the project needs and ends with an offline
sample. `generate` prints the result of each stage and ends with the path of the
video, `output/<request-id>/track-activity-query-size.mp4`, and its
accompanying files. On the Mac used for development, this 14-minute video took
about two minutes to build with its narration units already cached, and 33
seconds when an identical second request reused the validated video.

Add `--detail summary` for a short video of the page's key points (3.7 minutes
for this page) or `--detail full` for every section; see
[Choose how much detail](#choose-how-much-detail).

## Commands

Run the scripts in `scripts/` directly; no shell activation is needed. Paths
given as arguments are resolved from the project root, not from the working
directory.

| Command | What it does | Network |
| --- | --- | --- |
| `scripts/setup [--offline]` | Provisions the pinned Python runtime, packages, Kokoro model, fonts, FFmpeg, eSpeak NG, and Chromium inside the project, then runs `doctor --sample`. `--offline` rebuilds `.venv/` and `.runtime/` from `cache/` only. | yes, except with `--offline` |
| `scripts/pgvideo generate --document <page> [options]` | Creates a request for one page and runs every stage through delivery. Each request downloads the wiki glossary again and builds its own glossary index. | yes (GitHub) |
| `scripts/pgvideo resume --request <id> [--no-reuse]` | Repeats the glossary cross-check with the request's `resolutions.yaml`, then the script and every later stage. It uses the glossary that the request downloaded. | no |
| `scripts/pgvideo script --request <id> [--storyboard <file> \| --drafter-command <file>] [--no-reuse]` | Redrafts the script, or validates an edited scene file or a drafter's output, then every later stage. | no |
| `scripts/pgvideo narrate --request <id> [--lufs <target>] [--true-peak <limit>] [--refresh-unit <id>]` | Repeats the narration, then timing, rendering, and validation. | no |
| `scripts/pgvideo timing --request <id>` | Repeats timing and captions, then rendering and validation. | no |
| `scripts/pgvideo render --request <id> [--crf <n>] [--audio-bitrate <kb/s>]` | Repeats the slides and encoding, then validation. | no |
| `scripts/pgvideo validate --request <id>` | Repeats the media checks and delivery. | no |
| `scripts/pgvideo doctor [--sample]` | Checks the local environment and writes `.runtime/environment-report.json`. `--sample` also narrates, renders, and encodes a short offline sample. | no |
| `scripts/pgvideo audit` | Repeats `setup --offline` and the sample under a sandbox profile that terminates any undocumented access outside the project. | no |
| `scripts/pgvideo test` | Runs the test suite in the offline sandbox. | no |

`<id>` is the request ID that `generate` prints; it is also the request's
directory name under `runs/`. A command given `--request` repeats its stage and
every stage after it for that request only, and never creates a request.
`doctor` runs before every `scripts/pgvideo` command, and a failed check stops
the command. `scripts/pgvideo <command> --help` lists a command's options.

### `generate` options

| Option | Default | Meaning |
| --- | --- | --- |
| `--document` | required | A repository-relative `.md` path, or an HTTPS GitHub blob URL in `person123git/postgres-llm-wiki`. |
| `--ref` | `master` | The branch, tag, or commit for a relative path. A blob URL uses its own ref; a different `--ref` is rejected. |
| `--voice` | `af_heart` | The Kokoro voice. It must be provisioned in `tools.lock`. |
| `--language` | `a` | The Kokoro language code; `a` is American English. |
| `--speed` | `1.0` | The speaking speed, a positive number. |
| `--detail` | `standard` | How much of the page to narrate: `summary`, `standard`, or `full`. See [Choose how much detail](#choose-how-much-detail). |
| `--width`, `--height` | `1920`, `1080` | The video size in pixels, as positive even integers. |
| `--output` | `output` | The delivery directory, inside the project. The video goes to `<output>/<request-id>/`. |
| `--no-reuse` | off | Build the narration and MP4 even when a validated video with the same inputs exists. |

The tool never chooses a page: each request narrates exactly the page named by
`--document`. `generate` checks that the page exists on GitHub before it creates
the request, and it resolves the ref to one commit for the whole request. It
downloads `wiki/glossary.md` from that commit for every request, even when an
earlier request already downloaded it, and builds the request's glossary index
from that copy. With the default ref, each new request therefore checks the page
against the glossary as it is on `master` when the request starts. Set
`GITHUB_TOKEN` if GitHub's API rate limit blocks a request; unauthenticated
clients get 60 API calls an hour, and a request uses two to six.

The other commands' options:

| Command | Option | Default | Meaning |
| --- | --- | --- | --- |
| `narrate` | `--lufs` | `-16` | Integrated loudness target, from -70 to -5 LUFS. |
| `narrate` | `--true-peak` | `-1.5` | Maximum true peak, from -9 to 0 dBTP. |
| `narrate` | `--refresh-unit` | none | Synthesize a unit or sentence again even though it is cached, such as `s01-title.n1.u1` or `s01-title.n1`. Repeat the option for several. |
| `render` | `--crf` | `20` | H.264 constant rate factor, from 0 to 51; lower is higher quality. |
| `render` | `--audio-bitrate` | `128` | AAC bitrate, from 32 to 512 kb/s. |
| `script` | `--storyboard` | none | A JSON or YAML scene file inside the project, such as an edited copy of `storyboard.json`. |
| `script` | `--drafter-command` | none | An executable inside the project that reads `draft-input.json` on standard input and writes scenes to standard output. |
| `generate`, `resume`, `script` | `--no-reuse` | off | Build the narration and MP4 instead of reusing a validated video. |

### Exit status

| Status | Meaning |
| --- | --- |
| 0 | The video was validated and delivered, or the `setup`, `doctor`, `audit`, or `test` check passed. |
| 1 | An error, such as an invalid request, a missing local dependency, a failed download, an input that changed after it was checked, or broken media. The message says what failed. |
| 2 | Invalid command-line arguments for `setup` or a request command. |
| 3 | `needs_review`: the request stopped at a report that needs a decision. |

## Common tasks

### Make a video

```sh
scripts/pgvideo generate --document wiki/v18/questions/observability/track-activity-query-size.md
scripts/pgvideo generate --document https://github.com/person123git/postgres-llm-wiki/blob/master/wiki/v18/questions/observability/track-activity-query-size.md
scripts/pgvideo generate --document <page> --ref <tag-or-commit> --output output/review --speed 1.1
```

Each `generate` creates a new request. If a validated video has the same inputs,
the request reuses it and still runs its own timing and validation; otherwise it
builds the video.

### Choose how much detail

```sh
scripts/pgvideo generate --document <page> --detail summary
scripts/pgvideo generate --document <page> --detail full
```

| Level | What the video narrates | Length |
| --- | --- | --- |
| `summary` | The question; the page's own summary, such as its Short Answer, without its tables and code, or else the conclusions that open its answer; the key terms; one sentence from each caveat section; the first open question, reduced to one sentence when it is long; then the first sentence of as many main sections as fit. Follow-up prompts, tests, history, and the recap are left out. | About 3 minutes of planned narration, a video of about 2–6 minutes. The example page's summary runs 3.7 minutes. |
| `standard` (default) | Every section of a page that fits the 6–10-minute target. A longer page is condensed around its subject; see [Document structure and coverage map](#document-structure-and-coverage-map). | Up to about 10 minutes of planned narration. Spoken identifiers make the video longer: 14 minutes for the example page. |
| `full` | Every section, with its tables, code, and figures, and no length target. | As long as the page: 3.7 to 538 minutes of planned narration (median 32) across the wiki's 82 content pages at commit `ba57f08`. |

Every level leaves out measurement scripts, navigation, and citation lists,
which stay in the references. `--speed` changes only how fast Kokoro speaks.

The level belongs to the request. For another level of the same page, make a
new request; `resume`, `script`, and the other `--request` commands keep the
request's level. `generate` prints the level and the planned minutes after the
coverage map, and `runs/<id>/coverage.md` shows each section's decision and,
for a summary, the sentences it keeps. A full-detail request for a long page
makes a long video; stop it with Ctrl-C if the planned minutes are more than
you want, and delete its `runs/<id>/` directory.

A summary is delivered as `<page>-summary.mp4` and full detail as
`<page>-full.mp4`, so videos of different levels can sit side by side. A video
is reused only for a request at the same level.

### Continue a request that needs review

A request that stops with exit status 3 names the report to read and the
command to run next:

| Stopped at | Report | What to do |
| --- | --- | --- |
| Source snapshot | `runs/<id>/source-report.md` | The wiki page needs a fix, such as a version conflict, a missing pin, or missing evidence. Fix the page, then make a new request. |
| Coverage map | `runs/<id>/coverage.md` | The page has no prose to narrate; choose another page. |
| Glossary cross-check | `runs/<id>/glossary-check.md` | Record a decision for each blocking issue in `runs/<id>/resolutions.yaml` (the report gives a snippet for each), then run `scripts/pgvideo resume --request <id>`. If the glossary itself is wrong, fix it in the wiki and make a new request instead; see [Use an updated glossary](#use-an-updated-glossary). |
| Script | `runs/<id>/script.md` | Copy `runs/<id>/storyboard.json`, fix the scenes it lists, then run `scripts/pgvideo script --request <id> --storyboard <copy>`. |
| Validation | `runs/<id>/quality-report.json` | The media is valid, but its loudness or silence is out of range. Repeat the narration with other settings, or fix the script. |

### Use an updated glossary

Commit the change to `wiki/glossary.md` in the wiki, then make a new request
with a ref that contains it, such as the default `master`:

```sh
scripts/pgvideo generate --document <page>
```

Every `generate` resolves the ref again and downloads the glossary at that
commit, never a copy that an earlier request downloaded, and builds a new
glossary index from it. `resume`, `script`, and the other `--request` commands
keep the glossary their request downloaded, so they do not pick up the change.
A changed glossary also changes the reuse key, so the video is built again
rather than reused.

### Change the script

Copy `runs/<id>/storyboard.json`, edit the scenes, and validate the copy:

```sh
scripts/pgvideo script --request <id> --storyboard runs/<id>/edited.yaml
```

The copy may be JSON or YAML. Every scene is checked against the page again,
as described under [Narration script and storyboard](#narration-script-and-storyboard).
`resume` reuses the drafter the request last used, including an edited file.

### Fix a pronunciation

Edit `pronunciation/en.yaml`, or set a sentence's `tts` text with
`tts_source: manual` in an edited storyboard. Then run `script` so that the new
TTS text is checked, which also narrates it. Without options, `script` redrafts
with the built-in drafter; give `--storyboard <file>` again for a request that
uses an edited scene file.

```sh
scripts/pgvideo script --request <id>
```

To synthesize a unit again without changing its text, for example after
listening to it:

```sh
scripts/pgvideo narrate --request <id> --refresh-unit s03-terms.n2.u1
```

Unit IDs are listed in `runs/<id>/narration/audio-map.json`.

### Re-encode or deliver again

```sh
scripts/pgvideo render --request <id> --crf 18
scripts/pgvideo validate --request <id>
```

### Build instead of reusing

```sh
scripts/pgvideo generate --document <page> --no-reuse
scripts/pgvideo resume --request <id> --no-reuse
```

A fresh build is registered for reuse like any other.

### Check the environment

```sh
scripts/pgvideo doctor             # every check; runs before each command anyway
scripts/pgvideo doctor --sample    # also a short offline narration, slide, and MP4
scripts/pgvideo audit              # setup --offline and the sample under a kill-on-access profile
scripts/pgvideo test               # unit and integration tests
```

## Where files go

| Location | Contents |
| --- | --- |
| `runs/<id>/` | One request: its read-only inputs, every stage's record and report, audio, slides, and the draft MP4. It is kept after delivery so that any stage can be repeated. |
| `output/<id>/` | The delivery: `<page>.mp4` (`<page>-summary.mp4` or `<page>-full.mp4` for those levels), `transcript.md`, `captions.srt`, `captions.vtt`, `references.md`, `glossary-check.md`, `quality-report.json`, and `manifest.json`. |
| `cache/` | Downloads and reusable results: source files by commit, narration units, and the index of validated videos in `cache/videos/`. |
| `.runtime/` | The local Python runtime, FFmpeg, eSpeak NG, Chromium, temporary files, and `environment-report.json`. |

Deleting a request's directory under `runs/` is safe. Its video can no longer
be reused, and the next lookup removes its entry from the index.

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
| `setup`, `generate` | allowed | denied except the operating system paths below |
| `setup --offline`, `doctor`, `test`, `resume`, `script`, `narrate`, `timing`, `render`, `validate` | IP connections denied | the same |
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

Each `generate` creates a new request ID of the form
`YYYYMMDDTHHMMSSZ-<12 hex>` and saves the normalized request as
`runs/<request-id>/request.json`, regardless of the working directory. The
request records the page, the requested ref, and the settings. Relative output
paths are resolved from the project root, and absolute paths must also stay
inside it. The output and `runs/` paths are checked for traversal and symlink
escapes before any GitHub access and again before anything is written. Width
and height must be positive even integers for H.264 encoding, and the voice and
language must be provisioned locally; only `a`/`af_heart` is provisioned now.

### Source snapshot

After saving the request, `generate` resolves the requested ref to a full wiki
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

When the snapshot passes, `generate` parses the snapshot copy of the document.
It checks the copy's SHA-256 first and makes no network requests. The run
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

When the document passes, `generate` indexes the glossary that the source
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

When the glossary matches pass, `generate` cross-checks the document without
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

### Narration script and storyboard

When the cross-check passes, `generate` drafts the script without network
access or a language model. It first checks `document.json`,
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

After a script passes, `generate`, `resume`, and `script` look for a validated
video with the same key before narrating. The key is the SHA-256 of every input
that decides the video:

- the page, the glossary, wiki images, and the cited PostgreSQL files, by
  SHA-256, with the wiki commit and the PostgreSQL source pin;
- the storyboard, without its request ID, time, and drafter record. It keeps
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
`generate`. If an audit fails during setup, run `scripts/setup --offline` to
restore the environment.

### Tests

```sh
/path/to/postgres-videos/scripts/pgvideo test
```

The suite runs inside the offline sandbox in about a minute. Tests mock GitHub
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
  `generate`. Invalid requests (a missing page, a directory, a non-Markdown
  file, a glob, traversal, another repository, a conflicting or missing ref, an
  output directory outside the project, and an unprovisioned voice) fail before
  a request exists. A consistent page reaches narration from a path or a blob
  URL. An alias that two entries claim, a central term with no support, a
  default that contradicts the glossary, an entry not present in PostgreSQL 18,
  and missing or out-of-range evidence each stop the request before narration.
  A contradictory default that the pinned GUC table settles is corrected in the
  script.
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
  documented resolutions and their validation, altered inputs, and `generate`
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
- **Reuse:** `test_reuse.py` covers the key; an identical request that reuses
  the validated video; new builds for a changed speed, another level of
  detail, a new glossary snapshot, and `--no-reuse`, and a repeated summary
  that reuses its own video; changed or missing files; tampered index entries and an
  escaping cache; retries that reuse their own video without creating requests;
  and videos from other tools, which are not registered. It runs FFmpeg,
  Chromium, timing, and validation for real, with a deterministic stand-in for
  Kokoro.
